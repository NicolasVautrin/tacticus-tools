"""#221 -- STRUCTURE de la liste de `BlockChanceInfo` : ordre des tirages + identite des sources.

Ce fichier est OFFLINE et l'assume : il ne gele aucune valeur mesuree, il garde deux proprietes
STRUCTURELLES lues au decompile, que le pool d'unites actuel ne permet PAS de discriminer en live
(aucune unite Daemon spawnable ne porte en plus une source de block scalaire ou un 2e ExtraBlock --
`blackObliterator` et `worldEightbound` sont les deux seuls Daemon du pool, et ni l'un ni l'autre
n'a de `blockChance` de base). Sans ce garde, ces deux lignes de mirror seraient du port muet.

PROPRIETE 1 -- ORDRE. `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` termine
par `list.Sort(DamageCalculations.<>c.<CalculateBlockChances>b__15_0)`. Le corps de ce comparateur
est `mov eax,[r8+8] ; sub eax,[rdx+8] ; ret` = `b.blockDamage - a.blockDamage` (champ @+0x8 de
`BlockChanceInfo` = le blockDamage, cf. `ApplyRandomBlockDamage` qui lit `chance` en @+0x4 et
`amount` en @+0x8) => tri DECROISSANT par AMOUNT. Et c'est cet ordre que
`IdunBattle.Core.Services.DamageCalculations$$ApplyRandomBlockDamage` parcourt : il fixe donc l'ordre
des `NextBool` -- deux sources presentes, c'est la plus GROSSE qui est tentee la premiere.

PROPRIETE 2 -- IDENTITE. Le failed-id est le `BEntityId` de la source (`failedBlockIds:
System.Collections.Generic.List<IdunBattle.Core.BEntityId>`, pousse par
`IdunBattle.Core.Services.BlockDamageInfo$$AddFailedBlockId`), PAS la chance. L'entree PAR DEFAUT de
`IdunBattle.Entities.Components.MultiValueStatComponent$$GetAllValues` (le scalaire GetStat(7/8))
porte l'entite **0** ; chaque effet porte la sienne. Deux sources de MEME chance doivent donc rester
DISTINGUABLES : sinon l'exclusion inter-coups (`Contains(failedBlockIds, entityId)`) en retirerait
deux pour un seul echec, et un tirage disparaitrait des le 2e coup.
"""
from __future__ import annotations

from engine.entities.effects.loki.hits import DaemonExtraBlockEffect
from engine.runner.operations.damage import AttackDamageOperation
from engine.services.damage_combat import BlockSource, apply_random_block_damage


class _Ctx:
    """UnitContext minimal : uniquement ce que `_block_sources` lit sur `tsc.ctx`."""

    def __init__(self, block_chance, block_damage, attack):
        self.block_chance = block_chance
        self.block_damage = block_damage
        self.attack = attack


class _Tsc:
    def __init__(self, ctx):
        self.ctx = ctx


class _Rng:
    """PRNG scripte : rend les `next_bool` de la liste, dans l'ordre, et journalise les chances vues."""

    def __init__(self, results):
        self.results = list(results)
        self.seen = []

    def next_bool(self, chance):
        self.seen.append(int(chance))
        return self.results.pop(0)


def _daemon_effect(effect_type=1034):
    e = DaemonExtraBlockEffect(name="Daemon_ExtraBlock", effect_type=effect_type)
    return e


def test_block_sources_sorted_by_amount_descending():
    """Base (scalaire) et source Daemon coexistent -> la plus GROSSE passe devant, quel que soit
    l'ordre de construction (base d'abord, effets ensuite)."""
    # Attack 2000 x 50% = 1000 pour le Daemon ; base = 300 -> le Daemon doit passer devant.
    tsc = _Tsc(_Ctx(block_chance=25, block_damage=300, attack=2000))
    srcs = AttackDamageOperation._block_sources(tsc, [_daemon_effect()], 0)
    assert [s.amount for s in srcs] == sorted([s.amount for s in srcs], reverse=True), \
        f"liste non triee par amount decroissant : {srcs}"
    assert srcs[0].amount > srcs[1].amount, f"tri inoperant : {srcs}"

    # Base PLUS GROSSE que le Daemon -> c'est elle qui doit passer devant (le tri n'est pas
    # « les effets d'abord » deguise).
    tsc2 = _Tsc(_Ctx(block_chance=25, block_damage=5000, attack=2000))
    srcs2 = AttackDamageOperation._block_sources(tsc2, [_daemon_effect()], 0)
    assert srcs2[0].amount == 5000 and srcs2[1].amount == 1000, \
        f"la base (5000) devrait etre tentee avant le Daemon (1000) : {srcs2}"


def test_block_source_ids_distinguish_same_chance_sources():
    """Base et Daemon a la MEME chance (25) : leurs `block_id` doivent differer -- 0 pour l'entree
    par defaut de `GetAllValues`, l'entite-effet (offline : l'effect_type) pour l'effet."""
    tsc = _Tsc(_Ctx(block_chance=25, block_damage=300, attack=2000))
    srcs = AttackDamageOperation._block_sources(tsc, [_daemon_effect()], 0)
    ids = {s.block_id for s in srcs}
    assert len(ids) == len(srcs), (
        f"deux sources de meme chance partagent un block_id ({[(s.chance, s.block_id) for s in srcs]}) "
        f"-- l'exclusion inter-coups en retirerait deux pour un seul echec")
    base = next(s for s in srcs if s.amount == 300)
    daemon = next(s for s in srcs if s.amount == 1000)
    assert base.block_id == 0, f"l'entree par defaut doit porter l'entite 0, pas {base.block_id}"
    assert daemon.block_id == 1034, f"la source Daemon doit porter son effect_type, pas {daemon.block_id}"


def test_apply_random_block_damage_fails_only_the_source_that_missed():
    """`ApplyRandomBlockDamage` : un `NextBool` par source jusqu'a la 1re reussite ; la source ratee
    (et ELLE SEULE) part dans `failedBlockIds`."""
    tsc = _Tsc(_Ctx(block_chance=25, block_damage=300, attack=2000))
    srcs = AttackDamageOperation._block_sources(tsc, [_daemon_effect()], 0)
    rng = _Rng([False, True])                      # la 1re (Daemon, 1000) rate, la 2e (base) passe
    info = apply_random_block_damage(rng, srcs, 4000)
    assert rng.seen == [25, 25], f"un tirage par source tentee attendu, vu {rng.seen}"
    assert info.did_block is True
    assert info.damage == 4000 - 300, f"c'est l'amount de la source REUSSIE qui s'applique : {info}"
    assert info.failed_block_ids == [1034], (
        f"seule la source ratee doit etre marquee : {info.failed_block_ids}")


def test_zero_amount_source_consumes_no_draw():
    """Une source d'amount 0 est SAUTEE sans tirage (gate `0 < local_30` d'ApplyRandomBlockDamage)."""
    rng = _Rng([True])
    info = apply_random_block_damage(rng, [BlockSource(chance=25, amount=0, block_id=7)], 100)
    assert rng.seen == [], "une source d'amount 0 ne doit consommer aucun tirage"
    assert info.did_block is False and info.damage == 100
