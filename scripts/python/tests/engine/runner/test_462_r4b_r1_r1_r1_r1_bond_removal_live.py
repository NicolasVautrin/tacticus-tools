"""#462-r4b-r1-r1-r1-r1 -- le RETRAIT herite d'`ABondEffect`, confronte au natif.

LE CRITERE DISCRIMINANT, ENONCE AVANT LE MONTAGE
------------------------------------------------
Le trigger (a) d'`IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal` est
gate par le virtuel `<klass+0x748> get_RemoveOnBondedEntityDeath`. Confronter le retrait sur UN seul
porteur ne prouverait rien : un port qui retirerait TOUS les bonds a la mort du bonde -- ou qui
n'en retirerait AUCUN -- passerait la moitie des lignes. Il faut donc DEUX porteurs qui POSENT tous
deux leur bond et DIVERGENT sur le retrait, c'est-a-dire deux valeurs OPPOSEES du meme virtuel :

  A. `Neuroparasite` (1218) -- `IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect`,
     `get_RemoveOnBondedEntityDeath = true`. Le parasite est PERMANENT (options d'`AddBondEffect`
     vides -> pas de `DefaultAmountOfRounds`), donc rien d'autre ne peut le faire disparaitre. On
     TUE le Neurothrope (le BONDE, pas le porteur) : l'effet doit tomber.
     CONTROLE dans le meme runner : la mort d'une unite TIERCE ne doit RIEN retirer -- c'est le
     conjoint `IsEntityWithIdTarget(BondedEntity)`, et sans lui la mesure ne distinguerait pas le
     trigger d'un nettoyage declenche par n'importe quelle mort.

  B. `TunnelingHorror_PendingSummon` (1113) -- `TunnelingHorror_PendingSummonEffect`,
     `get_RemoveOnBondedEntityDeath = FALSE`. Ce bras est structurellement DISCRIMINANT et gratuit :
     le cast 1011 RETIRE son propre caster du plateau (`RemoveUnitFromItsTiles(Caster, true)`) dans
     le geste MEME qui pose le marqueur, et le caster EST le `bondedEntity`. L'event `On(0x25 =
     UnitRemoved)` part donc sur le bonde immediatement. Si le trigger etait construit ici, le
     marqueur serait detruit a la pose et le kit s'auto-detruirait. Le marqueur DOIT survivre.

Un port qui ignorerait le virtuel echoue forcement sur A ou sur B.

CE QUI N'EST PAS COUVERT ICI : les triggers (b) `<+0x728> get_Range` et (c) `<+0x738>
get_Adjacent`. Ils ne sont pas portes -- aucun porteur confrontable, cf. `bond_removal.py` §4.

⚠ NE PAS JOUER EN PARALLELE DE `test_366_r1_tunneling_horror_live.py`. Le bras B delegue son
montage a `probe_366_r1_tunneling_horror`, dont le state-file et le seed BC greffe sont des
LITTERAUX de module (`STATE`, `SEED_BC`) : deux passes concurrentes ecrivent le meme chemin et se
detruisent mutuellement. MESURE du 2026-08-04 -- les deux fichiers en parallele rendent
`1 failed` ici et `5 errors` la-bas ; joues EN SERIE, `4 passed` et `5 passed`. C'est le piege du
`CLAUDE.md` (« deux probes lances ENSEMBLE qui portent le meme litteral de state-file se marchent
dessus »), et il ne se lit PAS comme une regression du port.

ASCII only. Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PYDIR))

from engine.entities.effect_type import EffectType                              # noqa: E402
from engine.runner.operations.triggers.bond_removal import (                    # noqa: E402
    BOND_REMOVAL_GATES, BondRemoveOnBondedEntityDeath)
from engine.runner.operations.triggers.dispatch import (                        # noqa: E402
    pre_unit_death_2_triggers, unit_removed_triggers)
from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS  # noqa: E402

NEUROPARASITE = int(EffectType.Neuroparasite)                 # 1218 = 0x4c2
PENDING_SUMMON = int(EffectType.TunnelingHorror_PendingSummon)  # 1113 = 0x459
THIRD_UNIT = "ultraCalgar"


def _sid():
    from rl_collect_batch import _resolve_session
    return _resolve_session()


def _instances(state, uid, effect_type):
    eff = getattr(state, "effects", None)
    if eff is None:
        return []
    return [e for e in eff.by_unit.get(int(uid), [])
            if not e.consumed and int(e.effect_type) == int(effect_type)]


# ================================================================================================
# BRAS A -- `Neuroparasite` : `get_RemoveOnBondedEntityDeath = true`
# ================================================================================================
@pytest.fixture(scope="module")
def bras_a():
    """Runner UNIQUE du bras A : le montage est multi-tours par nature (poser, puis tuer)."""
    import probe_112_darkangels as PR
    import probe_462_r4b_r1_r1_defender_additive_carriers as P0

    sid = _sid()
    layout = P0._enemy_layout(sid, [P0.NEURO_CARRIER, THIRD_UNIT], [P0.NEURO_VICTIM])
    if P0.NEURO_VICTIM not in layout:
        pytest.fail("montage : victime absente du layout adverse (%s)" % sorted(layout))
    patch = {P0.NEURO_CARRIER: {"Health": 1000, "RemainingHealth": 1000},
             THIRD_UNIT: {"Health": 1000, "RemainingHealth": 1000},
             P0.NEURO_VICTIM: {"Health": 300000, "RemainingHealth": 300000, "Damage": 400000}}
    rid = P0._build(sid, [P0.NEURO_CARRIER, THIRD_UNIT], [P0.NEURO_VICTIM],
                    armor=P0.ARMOR_FLAT, unit_patch=patch,
                    anchor=layout[P0.NEURO_VICTIM], occupied=list(layout.values()))
    try:
        yield sid, rid
    finally:
        PR.dispose(sid, rid)


@pytest.fixture(scope="module")
def bras_a_pose(bras_a):
    """Pose le parasite, PUIS capture l'etat offline AVANT toute mort.

    L'ORDRE est load-bearing : le bras natif TUE le bonde, donc un etat capture apres lui ne
    porterait plus le parasite et les assertions PORT s'auto-skipperaient -- un vert qui ne mesure
    rien (le vice #455). On capture donc UNE fois, ici, et les deux faces partent du MEME etat."""
    import probe_112_darkangels as PR
    import probe_462_r4b_r1_r1_defender_additive_carriers as P0
    import probe_462_r4b_r1_r1_r1_neuroparasite_pose as P1
    import probe_462_r4b_r1_terminator_commanded_attack as R1

    sid, rid = bras_a
    dvv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    bv = PR.units_by_visual(dvv)
    for need in (P0.NEURO_CARRIER, P0.NEURO_VICTIM, THIRD_UNIT):
        assert need in bv, "roster incomplet : %s" % sorted(bv)
    neuro, tgt = int(bv[P0.NEURO_CARRIER]["id"]), int(bv[P0.NEURO_VICTIM]["id"])
    third = int(bv[THIRD_UNIT]["id"])
    normal_id = P0._normal_attack_id(dvv, neuro)
    pos = PR.positions(dvv)
    ok, dvv = P0._move_within(sid, rid, dvv, neuro, pos[tgt], P0.NEURO_RANGE, min_dist=2)
    assert ok and tgt in PR.legal_from_here(sid, rid, neuro, normal_id), (
        "montage : le Neurothrope ne peut pas frapper la victime en PSYCHIQUE")
    PR.act(sid, rid, {"kind": "ability", "casterId": neuro, "targetId": tgt,
                      "abilityType": normal_id})
    dvv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    assert P1._live_parasite(dvv, tgt)[0], "montage : le parasite 1218 n'est pas pose"
    board, dv2, ob, cs = R1._snapshot(sid, rid)
    # DEUX etats INDEPENDANTS depuis le MEME snapshot : le premier test PORT consomme l'instance,
    # et le vecteur `UnitRemoved` doit repartir d'un etat qui la porte encore. Les reconstruire ici
    # plutot qu'a la demande evite un `skip` VERT qui ne mesurerait rien (#455) -- le test natif,
    # qui s'execute entre les deux, a deja tue le bonde cote runner.
    return {"sid": sid, "rid": rid, "neuro": neuro, "tgt": tgt, "third": third,
            "state_death": R1._seeded_state(sid, rid, board, dv2, ob, cs),
            "state_removed": R1._seeded_state(sid, rid, board, dv2, ob, cs)}


def test_a_natif_retire_le_parasite_a_la_mort_du_bonde(bras_a_pose):
    """NATIF. Mort d'une TIERCE -> parasite present ; mort du BONDE -> parasite absent.

    Le retrait n'est attribuable a aucun autre chemin :
    `IdunBattle.Operations.RemoveEffectsOperation$$Execute` -- la voie de
    `IdunBattle.Operations.KillUnitOperation$$RemoveEffects` et de l'etape 14 de
    `IdunBattle.Operations.RemoveUnitOperation$$Execute` -- ne consomme que les effets PORTES par
    l'unite qui meurt, lus sur SON composant d'effets. Le parasite, lui, est porte par la VICTIME,
    qui survit. Il n'existe aucun nettoyage natif << par SOURCE >>."""
    import probe_462_r4b_r1_r1_r1_r1_bond_removal as PB

    c = bras_a_pose
    _dead3, pres3 = PB._kill_via(c["sid"], c["rid"], c["tgt"], c["third"], "CTRL mort TIERCE")
    assert pres3, ("CONTROLE ROUGE : la mort d'une unite TIERCE a deja retire le parasite -- le "
                   "retrait ne serait pas attribuable a `IsEntityWithIdTarget(BondedEntity)`")
    deadN, presN = PB._kill_via(c["sid"], c["rid"], c["tgt"], c["neuro"], "mort du BONDE")
    assert deadN, "le Neurothrope n'a pas pu etre tue"
    assert not presN, "NATIF : le parasite survit a la mort du bonde"


def test_a_port_retire_le_parasite_sur_le_vecteur_de_mort(bras_a_pose):
    """PORT, sur l'etat capture AVANT la mort. `On(2 = PreUnitDeath_2)` avec `target = le bonde`
    consomme l'instance 1218 ; le meme vecteur avec une TIERCE ne la touche pas."""
    c = bras_a_pose
    st, neuro, tgt = c["state_death"], c["neuro"], c["tgt"]
    inst = _instances(st, tgt, NEUROPARASITE)
    assert inst, "l'etat capture ne porte pas le parasite -- la mesure PORT serait vide"
    assert int(getattr(inst[0], "bonded", -1)) == neuro, "le bond ne pointe pas le Neurothrope"

    pre_unit_death_2_triggers(st, c["third"], tgt)
    assert _instances(st, tgt, NEUROPARASITE), (
        "PORT : une mort TIERCE a retire le parasite -- `IsEntityWithIdTarget` ne mord pas")
    pre_unit_death_2_triggers(st, neuro, tgt)
    assert not _instances(st, tgt, NEUROPARASITE), (
        "PORT : le parasite survit a `On(PreUnitDeath_2)` sur le bonde")


def test_a_port_retire_aussi_sur_unit_removed(bras_a_pose):
    """PORT. Le second `On()` de l'`op_BitwiseOr` natif : `On(0x25 = UnitRemoved)`. Le perdre
    rendrait le port aveugle a tout despawn SANS mort.

    Etat INDEPENDANT construit par la fixture depuis le meme snapshot : le test precedent a deja
    consomme l'instance du sien."""
    c = bras_a_pose
    st = c["state_removed"]
    assert _instances(st, c["tgt"], NEUROPARASITE), "l'etat capture ne porte pas le parasite"
    unit_removed_triggers(st, c["neuro"])
    assert not _instances(st, c["tgt"], NEUROPARASITE), (
        "PORT : le parasite survit a `On(UnitRemoved)` sur le bonde")


# ================================================================================================
# BRAS B -- `TunnelingHorror_PendingSummon` : `get_RemoveOnBondedEntityDeath = FALSE`
# ================================================================================================
def test_b_le_marqueur_survit_au_retrait_de_son_bonde():
    """Les DEUX faces, sur le porteur a virtuel FAUX.

    NATIF : apres le cast 1011 -- qui RETIRE le caster (= le `bondedEntity`) du plateau -- la tuile
    porte toujours 1113. PORT : rejouer `On(0x25 = UnitRemoved)` sur ce meme caster ne retire rien.
    C'est la ligne que casserait un port qui appliquerait le retrait a TOUS les bonds."""
    import probe_366_r1_tunneling_horror as P366

    assert not BOND_REMOVAL_GATES[PENDING_SUMMON].remove_on_bonded_entity_death, (
        "table : `TunnelingHorror_PendingSummonEffect` doit porter le virtuel a FAUX")

    rid = P366.build()
    try:
        us = P366.units_by_vid(rid)
        caster = next(i for i, u in us.items() if u["vid"] == P366.GRAFT_A)
        caster_b = next(i for i, u in us.items() if u["vid"] == P366.GRAFT_B)
        _us, _pa, _pb, target, _witness = P366.pick_target(rid, caster, caster_b)
        pre, _ = P366.pending_tiles(rid)
        assert not pre, "pre-etat pollue : 1113 deja present sur %r" % (sorted(pre),)
        P366.rpc("applyAction", {"runnerId": rid,
                                 "action": {"kind": "ability", "casterId": caster,
                                            "abilityType": P366.TUNNELING,
                                            "to": {"col": target[0], "row": target[1]}}}, 120)
        after, _ = P366.pending_tiles(rid)
        assert after, ("NATIF : le marqueur 1113 a disparu -- le cast retire son propre "
                       "`bondedEntity`, donc le trigger (a) l'aurait detruit a la pose")

        # PORT. ⚠ CE QUI MORD ICI EST LE CABLAGE, PAS UN REJEU D'EVENEMENT -- et c'est mesure :
        # la contre-epreuve << cabler TOUS les bonds >> laisse le rejeu de `unit_removed_triggers`
        # au VERT, parce que 1113 vit sur une TUILE et que `collect_effect_triggers` itere
        # `effects.by_unit`. Un compteur d'instances avant/apres serait donc vacuously vrai : il
        # se lirait comme une mesure et n'en serait pas une. On assertionne l'ABSENCE au registre,
        # qui elle rougit sur la mutation.
        assert BondRemoveOnBondedEntityDeath not in EFFECT_TRIGGERS.get(PENDING_SUMMON, []), (
            "PORT : `BondRemoveOnBondedEntityDeath` est inscrit pour 1113 alors que le virtuel "
            "`get_RemoveOnBondedEntityDeath` est FAUX -- le cablage ignore le gate")
        # Le rejeu reste joue : il ne prouve rien a lui seul (cf. ci-dessus) mais il garde la
        # non-regression le jour ou 1113 passerait par `by_unit`.
        st, _board = P366.offline_state(P366.capture(rid))
        before = sum(len(_instances(st, u, PENDING_SUMMON))
                     for u in list(getattr(st.effects, "by_unit", {}) or {}))
        unit_removed_triggers(st, int(caster))
        now = sum(len(_instances(st, u, PENDING_SUMMON))
                  for u in list(getattr(st.effects, "by_unit", {}) or {}))
        assert now == before, ("PORT : `On(UnitRemoved)` sur le bonde a retire %d marqueur(s) 1113"
                               % (before - now))
    finally:
        P366.rpc("disposeRunner", {"runnerId": rid}, 60)
