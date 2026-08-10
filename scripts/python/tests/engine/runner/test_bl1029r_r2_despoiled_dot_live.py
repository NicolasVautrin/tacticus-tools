"""#BL-1029r-r2 -- le DoT de tuile `DespoiledGround` (1476) et le buff 1478, garde LIVE.

⚠ **LA PREMISSE DU RESIDU ETAIT FAUSSE, ET CE FICHIER LA GARDE REFUTEE.** Le backlog disait
<< Cote port, AUCUN `TileEffectTrigger` n'est enregistre pour 1476 >>. Or les deux volets sont
portes depuis #85 (`769b965a`, 2026-07-28), DOUZE jours avant l'ouverture du residu. Ce qui
manquait n'etait pas le port : c'etait la CONFRONTATION. Le probe de `#BL-1029r-r1` mesurait bien
`Effect_Type: 1476` cote LIVE, mais il ECARTAIT de sa comparaison tout evenement portant un
`Effect_Type` -- le tick n'a jamais ete oppose au port, ni dans un sens ni dans l'autre.

`IdunBattleLogic.Entities.Abilities.Active.Loki.EnvDespoiledGroundTileAbility$$CreateBehaviour`
(corps LU sur `rnca9r7q6c`) fait DEUX choses par occupant, et la seconde est gatee :

    Foreach( UnitsWithoutTraits(., [0x1b = 27 Steppable, 0x19 = 25 Immune], 3)
             & Units(EntitiesWithAnyEffect(., 0x5c4 = 1476, 2), 1, 1),
        AttackWithAbilityDamage(Tiles(elem), elem,
                                RandomAmount(PercentageOf(StatAmount(elem, Health, Max), EffectConfig(9)),
                                             PercentageOf(StatAmount(elem, Health, Max), EffectConfig(10))),
                                AbilityOrEffect(0x5c4), Direct(Nullable(0xf = DirectDamage)))
      + If( IsTurnOf(elem) & HasTrait(elem, 0x7ea = 2026 Chaos) & NOT HasTrait(elem, 0x19 = Immune),
            AddEffect(0x5c6 = 1478, AbilityStateReference, elem, <DSLFormulas+0x20 = Const(1)>) ) )

CE QUE CE FICHIER GARDE :

  1. **LE REGISTRE** (OFFLINE, derive) -- `EFFECT_TRIGGERS[1476]` porte un trigger, et les DEUX
     classes d'effet sont au registre. C'est la premisse du residu, gardee REFUTEE.
  2. **LE DoT EST BIT-EXACT** -- il consomme UN tirage `RandomAmount` ; le port part du MEME etat
     et du MEME etat de PRNG (`dumpRng`), donc l'accord est exigible A L'UNITE, pas en enveloppe.
  3. **LE BUFF 1478 EST POSE DES DEUX COTES** -- la cible du montage est un HERO **CHAOS**
     (`worldKharn`) : sur un Necron le volet 1478 serait STRUCTURELLEMENT inatteignable et son
     accord vide de sens. Le test EXIGE donc que la cible soit Chaos, et que le buff soit ABSENT
     avant le tick.

⚠ PIEGE DE MONTAGE, NOMME DANS LE PROBE : appeler `tile_tick_triggers(state)` directement rend
`1478 : False` cote port -- l'etat capture porte encore MON `current_player_id`, et `IsTurnOf` est
donc faux. Le natif emet `On(0x14)` depuis `StartTurnOperation`, APRES le flip. Le port est pilote
par `EndTurnMessage(advance=True)`, qui rejoue la MEME sequence.

ASCII only. Probe jumeau : `scripts/python/probe_bl1029r_r2_despoiled_dot.py`.
"""
from __future__ import annotations

import pytest

import probe_bl1029r_r2_despoiled_dot as P
from engine.entities.effect_type import EffectType


@pytest.fixture(scope="module")
def dg(build_runner, rpc):
    rid = build_runner(seed=str(P.SEED), extra=list(P.BUILD_ARGS))["rid"]
    try:
        return P.measure(rpc, rid)
    except P.MontageError as e:
        pytest.fail("montage non exerce : %s" % e, pytrace=False)


def test_registry_carries_both_volets():
    """(1) OFFLINE, DERIVE -- la premisse du residu `#BL-1029r-r2`, gardee REFUTEE.

    Si ce test rougissait, c'est que quelqu'un a DESINSCRIT le tick ou une classe d'effet : ce
    fichier deviendrait alors une mesure de rien, et les deux tests live ci-dessous mentiraient."""
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    from engine.entities.effects.factory import EFFECT_CLASSES
    trig = EFFECT_TRIGGERS.get(int(EffectType.DespoiledGround))
    assert trig, ("`EFFECT_TRIGGERS[%d %s]` est VIDE : le tick de tuile n'est plus dispatche"
                  % (int(EffectType.DespoiledGround), EffectType.DespoiledGround.name))
    for et in (EffectType.DespoiledGround, EffectType.DespoiledGround_ExtraDamagePct):
        assert et.name in EFFECT_CLASSES, (
            "`EFFECT_CLASSES[%r]` a disparu : l'effet redevient inerte" % et.name)


def test_target_is_chaos_so_the_1478_volet_exists(dg):
    """(3a) DISCRIMINANCE DU MONTAGE : sans une cible CHAOS, le volet 1478 est structurellement
    inatteignable et son accord ne prouve rien. Et le buff doit etre ABSENT avant le tick."""
    import gameconfig as GC
    kit = GC.unit(P.TARGET) or {}
    assert kit, "cible %s absente du gameconfig" % P.TARGET
    assert EffectType.DespoiledGround_ExtraDamagePct.name not in (dg["effects_before"] or []), (
        "la cible portait DEJA 1478 avant le tick : l'accord de (3b) serait vide de sens")


def test_tile_dot_is_bit_exact(dg):
    """(2) Le DoT du tick, A L'UNITE. MESURE a la fermeture : offline == live == **35902** sur une
    cible a 500 000 PV (soit 7,18 % de la PV MAX, dans les bornes BC
    `[DespoiledGroundMinDmgPct, DespoiledGroundMaxDmgPct]` = 6..9 %)."""
    assert dg["dot_live"], (
        "le NATIF n'inflige AUCUN degat au tick (dPV = %r) : la tuile n'etait pas despoilee, ou le "
        "tick n'a pas eu lieu -- montage non exerce" % (dg["dot_live"],))
    assert dg["dot_offline"] == dg["dot_live"], (
        "le DoT de tuile diverge : offline = %r, live = %r (cible %r, PV avant = %r). UN tirage "
        "`RandomAmount` est consomme des deux cotes depuis le MEME etat de PRNG -- un ecart est un "
        "bug de port, pas du bruit."
        % (dg["dot_offline"], dg["dot_live"], dg["target"], dg["hp_before"]))


def test_1478_buff_is_applied_on_both_sides(dg):
    """(3b) Le 2e volet : `AddEffect(1478)` sur l'occupant CHAOS, a SON tour."""
    assert dg["buff_live"], (
        "le NATIF ne pose pas 1478 (effets cible : %r) -- le gate `IsTurnOf & HasTrait(Chaos) & "
        "NOT HasTrait(Immune)` n'a pas ete exerce" % (dg["effects_live"],))
    assert dg["buff_offline"], (
        "le PORT ne pose pas 1478 alors que le natif le fait (effets offline : %r). Verifier "
        "d'abord le MONTAGE : le port ne doit PAS etre pilote par `tile_tick_triggers` direct, qui "
        "laisse `current_player_id` sur le joueur PRECEDENT et rend `IsTurnOf` faux."
        % (dg["effects_offline"],))
