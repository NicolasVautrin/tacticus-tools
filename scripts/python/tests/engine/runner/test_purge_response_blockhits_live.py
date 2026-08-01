"""CLIQUET `#366-r1-blockhits-purgeresponse` -- `PurgeResponse` (1538) sur `votanSmnSteeljack`.

SECOND et DERNIER implementeur natif de `IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction`
(le premier, `1117 InescapableAccuracy_overrideHits`, est garde par
`test_inescapable_accuracy_override_hits_live.py`). Son trigger, LU A L'ASSEMBLEUR --
`IdunBattle.Entities.Effects.Loki.PurgeResponseEffect$$CreateBlockHitReductionTrigger`, un seul
`call` vers `DSLTriggers`, aucun `IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd` :

    TriggeringAbilityIs( AbilityOrEffect( EffectType 0x3f1 = 1009 Overwatch_AutoAttack ) )

**Aucun `get_OwnerIsCaster`** : le trigger ne lit RIEN du porteur. C'est le fait porteur de la
tranche, et il a deux consequences que ce fichier garde separement :

  * CANAL      -- une instance ACTIVE de 1538 n'importe ou sur le board eteint les REDUCTIONS de
                  coups de TOUTE attaque declenchee par `Overwatch_AutoAttack` ;
  * BALAYAGE   -- `block_hits_reduction_from_effects` doit donc parcourir TOUT le board (mirror de
                  `IdunBattle.Core.Services.EffectsQuery$$GetActiveEffectsWithBonuses`, qui ne prend
                  aucun argument de portee), et non les seuls effets de l'ATTAQUANT. Le
                  `get_OwnerIsCaster` de 1117, jusqu'ici RENDU par le balayage etroit, a migre dans
                  sa classe. `test_widening_is_load_bearing` est la garde qui rougit si le balayage
                  se re-retrecit.

VOIE SUMMON (gate de confrontabilite) : aucune unite `LeaguesOfVotann` n'est dans le pool, et le
porteur est un SUMMON. On injecte donc l'INVOCATEUR (`votanMemnyr`, `catalog_inject`) et on lui fait
CASTER `IronkinSteeljack` (1219) sur un hex LIBRE **ADJACENT** -- l'adjacence est la marche de
case-92 §5, un hex non adjacent rend `ok:true / mutated:false / spawned:0`. Le summon se projette
sous le `visualId` **`votanNpc2Steeljack`** (piege #427).

MONTAGE, et pourquoi il est CHOISI : le porteur du flag est MON summon, l'ATTAQUANT est l'ennemi
overwatcher, la CIBLE est mon mover. Le porteur n'est donc NI l'attaquant NI la cible, et il est
dans l'AUTRE camp que l'attaquant : un flag gate `get_OwnerIsCaster` ne pourrait PAS s'armer. Le
compte de la salve est donc, a lui seul, la mesure de l'absence de ce noeud.

Probe de mesure : `probe_366_r1_blockhits_purgeresponse.py` (foyer unique du montage -- `build`,
`stage`, `strike`, `replay`, `carried`, `shot_regime` sont IMPORTES ici plutot que re-transcrits).

ASCII only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _charge_regime import ChargeRegimeHarness                       # noqa: E402

from engine.entities.effect_type import EffectType                   # noqa: E402
from engine.entities.effects import (                                # noqa: E402
    block_hits_reduction_from_effects, board_effect_carriers)
from engine.entities.effects.factory import EFFECT_CLASSES           # noqa: E402
from engine.entities.effects.loki import (                           # noqa: E402
    InescapableAccuracyOverrideHitsEffect, PurgeResponseEffect)
from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.services.attack_hits_formula import attack_hits_with_modifiers   # noqa: E402
from probe_366_r1_blockhits_purgeresponse import (                   # noqa: E402
    EFFECT_NAME, EFFECT_TYPE, MOVER, OVERWATCHER, SUMMONER, SUMMON_VISUAL,
    build, carried, replay, shot_regime, stage, strike)


class _Args:
    """Le namespace que `probe.build` attend (meme surface que son argparse)."""

    def __init__(self, board="MC1_67", seed="777", overwatcher=OVERWATCHER):
        self.board, self.seed, self.overwatcher, self.extra = board, seed, overwatcher, []


def _measure(rpc, arm, board="MC1_67", seed="777", overwatcher=OVERWATCHER):
    """Monte le bras (`ON` / `OFF`), tire, rend `(h, rec, live, dispose)`. ECHEC FORT si le regime
    n'est pas atteint -- un `skip` VERT mentirait sur une garde qui n'a rien garde."""
    a = _Args(board=board, seed=seed, overwatcher=overwatcher)
    rid, sf, bc = build(a, arm)
    assert rid is not None, "build du runner %s (%s/%s) KO -- cf. la sortie du probe" % (arm, board,
                                                                                          seed)

    def dispose():
        rpc("disposeRunner", {"runnerId": rid}, 30)
        for p in (sf, bc):
            if p:
                Path(p).unlink(missing_ok=True)

    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = stage(h, arm, overwatcher=overwatcher)
        assert rec is not None, "regime NON ATTEINT (%s, %s/%s) : %s" % (arm, board, seed, why)
        live, why = strike(h, rec)
        assert live is not None, "salve d'overwatch non mesurable (%s) : %s" % (arm, why)
        _d, whits, red = shot_regime(overwatcher)
        want = whits if arm == "ON" else whits - red
        assert len(live) == want, (
            "le natif a joue %d coup(s), %d attendus pour le bras %s (arme %d, Camouflage -%d) -- "
            "le regime n'est PAS celui que le bras promet (reduction absente ? overwatch consomme ? "
            "mauvaise arme ?)" % (len(live), want, arm, whits, red))
        return h, rec, live, dispose
    except BaseException:
        dispose()
        raise


@pytest.fixture(scope="module")
def pr_on(rpc):
    """BRAS ON -- le summon porteur de `PurgeResponse` est sur le board (dans MON camp), l'ennemi
    overwatcher tire sur mon mover `Camouflage` : la reduction est ETEINTE, salve PLEINE."""
    h, rec, live, dispose = _measure(rpc, "ON")
    try:
        yield h, rec, live
    finally:
        dispose()


@pytest.fixture(scope="module")
def pr_off(rpc):
    """BRAS OFF -- MEME montage, summon NON caste : aucun porteur de 1538, la reduction s'applique."""
    h, rec, live, dispose = _measure(rpc, "OFF")
    try:
        yield h, rec, live
    finally:
        dispose()


@pytest.fixture(scope="module")
def pr_alt(rpc):
    """GENERALISATION -- autre board (`C1_25`, a elevation), autre seed (31337), autre overwatcher
    (`admecDestroyer` : 4 coups a portee 3, donc l'AUTRE branche de `Camouflage_HitReduction`,
    `AverageDistance > 2` -> -2)."""
    h, rec, live, dispose = _measure(rpc, "ON", board="C1_25", seed="31337",
                                     overwatcher="admecDestroyer")
    try:
        yield h, rec, live
    finally:
        dispose()


# --------------------------------------------------------------------------------------------- #
# OFFLINE -- identite de classe, noeud unique, et le BALAYAGE.
# --------------------------------------------------------------------------------------------- #
def test_registry_binds_purge_response():
    """Garde STRUCTURELLE (offline, sans jeu) : 1538 a sa PROPRE classe, distincte de celle de 1117.

    Les DEUX implementeurs de `BlockHitsReduction` ont des triggers SANS AUCUN noeud commun ; les
    confondre ferait heriter a l'un le gate de l'autre."""
    assert EFFECT_CLASSES.get(EFFECT_NAME) is PurgeResponseEffect
    assert PurgeResponseEffect is not InescapableAccuracyOverrideHitsEffect
    assert int(EffectType.PurgeResponse) == EFFECT_TYPE


def test_purge_response_gates_offline():
    """`TriggeringAbilityIs(AbilityOrEffect(EffectType 1009))` -- UN noeud, et rien d'autre.

    ⚠ QUALIFICATION D'ENUM : `1009` est ici un **EffectType** (`Overwatch_AutoAttack`), parce que
    l'`op_Implicit` appele par le trigger est la surcharge qui ecrit le slot `Effect`
    (`IdunBattle.Core.AbilityOrEffect$$set_Effect`). Le meme entier vaut `ActiveAbilityType`
    `ResurrectionOrb`, `TriggeredAbilityType` `WhipcoilBody` et `UnitTrait` `Resilient` -- le port
    COLLAPSE les trois `Nullable` de l'`AbilityOrEffect` en un entier, ce qui reste exact tant que
    le seul producteur de la cle sur l'axe COUPS est le vecteur OVERWATCH."""
    e = PurgeResponseEffect(name=EFFECT_NAME, effect_type=EFFECT_TYPE, level=1, ability_level=50)
    assert PurgeResponseEffect.TRIGGERING_EFFECT_TYPE == int(EffectType.Overwatch_AutoAttack)
    assert e.block_hits_reduction(None) is False                       # ctx absent
    assert e.block_hits_reduction({}) is False                         # pas de declencheur
    assert e.block_hits_reduction({"trigger_ability_type": None}) is False
    assert e.block_hits_reduction({"trigger_ability_type": 1009}) is True
    assert e.block_hits_reduction({"trigger_ability_type": 17}) is False, \
        "un autre declencheur ne doit RIEN bloquer"
    # AUCUN autre conjoint : ni nature du coup, ni mouvement, ni identite du porteur.
    for extra in ({"is_melee": True}, {"is_melee": None}, {"has_moved": True},
                  {"owner_id": 3, "att_id": 9}, {"owner_id": None, "att_id": None}):
        assert e.block_hits_reduction({"trigger_ability_type": 1009, **extra}) is True, (
            "le trigger natif n'a QU'UN noeud -- %s ne doit pas le fermer" % (extra,))


def test_widened_sweep_offline():
    """LE BALAYAGE, verrouille sur la FORMULE (la ou le natif le fait) et dans les DEUX sens.

    (a) `PurgeResponse` porte par un TIERS -- ni l'attaquant, ni la cible -- eteint la reduction :
        c'est l'univers natif de `EffectsQuery$$GetActiveEffectsWithBonuses`, qui n'a aucun
        argument de portee.
    (b) `1117` porte par ce MEME tiers n'eteint RIEN : son `get_OwnerIsCaster` a migre du canal
        vers sa classe quand le balayage s'est elargi. Sans cette migration, l'elargissement
        aurait rendu 1117 PERMISSIF -- un bug silencieux, exactement de la forme que la doctrine
        appelle « degradation permissive »."""
    def mk(name, et):
        return EFFECT_CLASSES[name]({"name": name, "effectType": et}, 100, 50, None)

    pr = mk(EFFECT_NAME, EFFECT_TYPE)
    ia = mk("InescapableAccuracy_overrideHits", 1117)
    cam = mk("Camouflage_HitReduction", 1134)
    board = {"att_id": 1, "tgt_id": 2, "attack_pos": (0, 0), "t_pos": (3, 0), "tgt_team": 1,
             "is_melee": False, "pos_by_id": {1: (0, 0), 2: (3, 0), 3: (9, 9)},
             "team_by_id": {1: 0, 2: 1, 3: 0}, "has_moved": False,
             "trigger_ability_type": int(EffectType.Overwatch_AutoAttack)}

    def hits(bd, third_effects):
        return attack_hits_with_modifiers(
            weapon_hits=6, extra_hits=0, extra_hits_melee=0, attacker_effects=[],
            trait_objects=[], target_effects=[cam],
            aura_sources=[(3, (9, 9), 0, third_effects)], board=bd,
            is_melee=False, damage_profile="Physical")

    assert hits(board, []) == 4, "Camouflage a d=3 retire 2 coups (branche `dist > 2`)"
    assert hits(board, [pr]) == 6, \
        "(a) le porteur TIERS eteint la reduction -- le balayage doit etre BOARD-WIDE"
    assert hits({**board, "trigger_ability_type": None}, [pr]) == 4, \
        "hors overwatch, `TriggeringAbilityIs` est FAUX et la reduction revient"
    assert hits(board, [ia]) == 4, \
        "(b) 1117 porte par un TIERS ne bloque RIEN : `get_OwnerIsCaster` vit dans sa classe"

    # L'agregateur lui-meme, sur son univers : le porteur est un tiers, l'attaquant est u1.
    ctx = {"att_id": 1, "trigger_ability_type": int(EffectType.Overwatch_AutoAttack)}
    carriers = board_effect_carriers(1, [], 2, [cam], [(3, (9, 9), 0, [pr])])
    assert [c[0] for c in carriers] == [1, 2, 3], "l'univers = attaquant + cible + tous les autres"
    assert block_hits_reduction_from_effects(carriers, ctx) is True
    assert block_hits_reduction_from_effects([(1, []), (2, [cam])], ctx) is False, \
        "sans le porteur tiers dans l'univers, le flag ne s'arme pas"


# --------------------------------------------------------------------------------------------- #
# LIVE -- le carre.
# --------------------------------------------------------------------------------------------- #
def test_block_matches_native(pr_on):
    """CAS ROUGE AVANT LE FIX -- la salve d'overwatch garde ses coups pleins parce qu'un summon
    ALLIE A LA CIBLE porte `PurgeResponse` ; un port sans le canal en compte un (ou deux) de moins.

    C'est aussi la mesure de l'absence de `get_OwnerIsCaster` : le porteur n'est ni l'attaquant ni
    la cible, et il est dans l'autre camp que l'attaquant."""
    h, rec, live = pr_on
    off, st = replay(h, rec)
    assert rec["summon_id"] is not None, "le bras ON doit avoir monte le summon"
    assert carried(rec, st), \
        "1538 n'est pas materialise offline sur le summon -- le test comparerait deux absences"
    assert len(off) == len(live), (
        "CANAL : le port ne bloque pas la reduction de coups -- live n=%d %s / offline n=%d %s"
        % (len(live), live, len(off), off))


def test_channel_actually_bites(pr_on):
    """Le bras ON EXERCE bien le canal -- sinon le test precedent passerait pour une raison
    TRIVIALE (aucune reduction nulle part, deux comptes qui s'accordent).

    Mutation ADVERSARIALE : l'inscription est retiree d'`EFFECT_CLASSES`, l'effet capte retombe sur
    `BaseEffect` (dont `block_hits_reduction` rend False)."""
    h, rec, live = pr_on
    ref, _ = replay(h, rec)
    mut, _ = replay(h, rec, mutate="NOCHANNEL")
    assert len(mut) < len(ref), (
        "l'inscription retiree ne reduit PAS le compte (ref n=%d, mut n=%d) -- cette salve n'exerce "
        "pas le canal" % (len(ref), len(mut)))


def test_widening_is_load_bearing(pr_on):
    """LA GARDE DE L'ELARGISSEMENT -- celle qui rougit si le balayage se re-retrecit.

    Mutation ADVERSARIALE : `board_effect_carriers` est remplacee par l'univers d'AVANT cette
    tranche (les seuls effets de l'ATTAQUANT). Le porteur etant un tiers, le flag ne s'arme plus et
    le compte DOIT retomber -- c'est exactement la vue rouge que ce cas a ouverte."""
    h, rec, live = pr_on
    ref, _ = replay(h, rec)
    mut, _ = replay(h, rec, mutate="NOWIDEN")
    assert len(mut) < len(ref), (
        "balayage restreint a l'ATTAQUANT : le compte ne descend pas (ref n=%d, mut n=%d) -- cette "
        "salve ne prouve pas que l'elargissement porte" % (len(ref), len(mut)))


def test_trigger_node_is_load_bearing(pr_on):
    """Le noeud `TriggeringAbilityIs` est CHARGE UTILE, pas decoratif.

    Mutation ADVERSARIALE : `trigger_ability_type` est FORCEE a None dans l'`att_ctx`. Ce gate est
    BINAIRE (pas tri-etat), donc forcer et retirer coincident -- et le desarmement va bien dans le
    sens qui EFFACE le blocage ; l'assertion le verifie plutot que de le supposer (#422 : une
    mutation VERTE sur une contre-epreuve est le resultat SUSPECT)."""
    h, rec, live = pr_on
    ref, _ = replay(h, rec)
    mut, _ = replay(h, rec, mutate="NOTRIGGER")
    assert len(mut) < len(ref), (
        "`TriggeringAbilityIs` desarme : le compte ne descend pas (ref n=%d, mut n=%d)"
        % (len(ref), len(mut)))


def test_control_without_carrier(pr_off):
    """CONTROLE LIVE -- sans porteur sur le board, le natif SUBIT la reduction, et le port aussi.

    C'est ce bras qui prouve que la reduction EXISTE dans ce montage : sans lui, un accord
    live == offline sur le bras ON ne dirait rien (deux comptes pleins pour cause d'absence de
    reduction). Il est aussi BIT-EXACT quand l'overwatcher n'a pas de bonus de degat non porte."""
    h, rec, live = pr_off
    off, _ = replay(h, rec)
    assert rec["summon_id"] is None, "le bras OFF ne doit AUCUN summon"
    assert len(off) == len(live), (
        "CONTROLE : live n=%d %s / offline n=%d %s" % (len(live), live, len(off), off))


def test_other_board(pr_alt):
    """GENERALISATION : autre board (`C1_25`, a ELEVATION), autre seed (31337), autre overwatcher
    (`admecDestroyer`, portee 3 -> branche `-2` de Camouflage, salve de 4 coups).

    Ce couple est BIT-EXACT jusqu'a la VALEUR : `admecDestroyer` n'a pas de bonus de degat
    d'overwatch non porte, contrairement a `necroDestroyer` (`InescapableDeath` = +655/coup quand
    l'attaque est declenchee par l'Overwatch, effet 1018 NON inscrit au registre)."""
    h, rec, live = pr_alt
    off, st = replay(h, rec)
    assert carried(rec, st), "1538 doit etre materialise offline sur le summon"
    assert len(off) == len(live), (
        "C1_25/31337 : live n=%d %s / offline n=%d %s" % (len(live), live, len(off), off))
    assert off == live, (
        "couple SANS bonus de degat non porte : les valeurs doivent etre bit-exactes -- live %s / "
        "offline %s" % (live, off))
    mut, _ = replay(h, rec, mutate="NOWIDEN")
    assert len(mut) < len(off), \
        "C1_25/31337 : le balayage restreint ne change rien -- ce bras n'exerce pas le mecanisme"


def test_montage_units_are_the_right_ones():
    """Les trois roles du montage sont CHOISIS, pas tombes du ciel -- et chaque choix est une mesure
    fausse evitee. Cette garde rougit si le gameconfig change sous nos pieds."""
    import gameconfig as GC
    ow = GC.unit(OVERWATCHER) or {}
    mv = GC.unit(MOVER) or {}
    smn = GC.unit(SUMMONER) or {}
    assert "Overwatch" in (ow.get("traits") or []), \
        "%s doit porter le trait Overwatch (il EST l'attaquant de la salve)" % OVERWATCHER
    assert "InescapableAccuracy" not in ((ow.get("passiveAbilities") or [])
                                         + (ow.get("activeAbilities") or [])), \
        "un overwatcher porteur de 1117 bloquerait les reductions TOUT SEUL (eldarMauganRa)"
    assert "Camouflage" in (mv.get("traits") or []), \
        "%s doit porter Camouflage -- c'est LA reduction que le canal doit eteindre" % MOVER
    assert "Infiltrate" not in (mv.get("traits") or []), \
        ("Infiltrate IMMUNISE le mover a l'overwatch (`AdditionalTriggers` = NOT HasEffect(mover, "
         "1048)) -- aucune salve, donc rien a mesurer")
    assert "IronkinSteeljack" in (smn.get("activeAbilities") or []), \
        "%s n'est plus l'invocateur du porteur" % SUMMONER
    assert (GC.ability("IronkinSteeljack") or {}).get("constants", {}).get("unitId") \
        == "votanSmnSteeljack", "l'ability 1219 ne summone plus le Steeljack"
    assert "PurgeResponse" in ((GC.unit("votanSmnSteeljack") or {}).get("passiveAbilities") or []), \
        "le summon ne porte plus le passif PurgeResponse"
    assert SUMMON_VISUAL != "votanSmnSteeljack", \
        "le summon se projette sous le visualId du NPC jumeau (piege #427)"
