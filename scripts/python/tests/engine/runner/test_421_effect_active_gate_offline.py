"""#421 -- CONTRE-EPREUVE des quatre gates `EffectComponent.IsActive @+0x5c` poses, 100 % OFFLINE.

Ce que ces cliquets verrouillent, et POURQUOI ils existent SEPAREMENT de `probe_229` : le probe
verifie que le `matches` de chaque classe LIT le flag (analyse AST). Il ne verifie PAS que la
lecture PILOTE le verdict. Une lecture decorative (`_ = e.active`) le rendrait vert. Ici on MESURE
le verdict, instance ACTIVE contre instance INACTIVE, sur le meme etat par ailleurs identique.

Les quatre classes sont toutes du rail TARGETS, c'est-a-dire evaluees par
`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets`, qui lit le flag
PAR CIBLE (sur l'`EffectComponent` RE-FETCH depuis l'entite-effet) AVANT `ShouldTrigger`. Les
triggers du rail ArraySet (`...$$EvaluateEffectTriggerEffectAbilities`) n'ont AUCUN gate : le
dernier test verifie qu'on ne leur en a pas ajoute un par contagion.

Chaque cas est un COUPLE : le bras ACTIF doit rendre True (sinon le test ne prouverait rien --
il pourrait passer parce qu'un AUTRE gate refuse), le bras INACTIF doit rendre False.
ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                              # noqa: E402
from engine.entities.effects.factory import EffectFactory                  # noqa: E402
from engine.runner.components import HealthComponent, UnitComponent        # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent            # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                 # noqa: E402
from engine.runner.operations.triggers.loki.ghost_revive import (          # noqa: E402
    TimeFluxGhostEffectRevive, EchoesFromTheWarpGhostEffectRevive,
    TimeFluxGhostRemoveOnSourceRemoved,
    TIME_FLUX_GHOST_EFFECT, ECHOES_GHOST_EFFECT)
from engine.runner.operations.triggers.loki.harlequins_panoply import (    # noqa: E402
    HarlequinsPanoplyIgnoreHitsRemove, HARLEQUINS_PANOPLY_IGNORE_HITS)
from engine.runner.operations.triggers.loki.ramming_speed import (         # noqa: E402
    RammingSpeedExtraExplodeRemove, RAMMING_SPEED_EXTRA_EXPLODE)

COLS, ROWS = 5, 5
CARRIER_ID, ATTACKER_ID = 10, 20
HP = 50000


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _state():
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    decision = {"currentPlayer": 1, "units": [
        {"id": CARRIER_ID, "visualId": "eldarAutarch", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 2}, "effects": []},
        {"id": ATTACKER_ID, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 3, "row": 2}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": HP, "hpMax": HP} for u in decision["units"]]}
    return load_state(decision, observe, board=Board(tiles, adjacency="evenq"))


def _seed_effect(state, owner_id: int, name: str, effect_type: int, *, active: bool,
                 source=None) -> None:
    """Pose une instance d'effet sur `owner_id` par le MEME chemin que le seed live :
    `EffectFactory.create`, qui lit la cle `active` publiee par le canal
    `decisionView { includeInactive: true }` (#219)."""
    if state.effects is None:                      # aucun effet au seed -> `load_state` laisse None
        from engine.entities.effects_state import EffectsState
        state.effects = EffectsState.seed({})
    inst = EffectFactory.create({"name": name, "effectType": int(effect_type),
                                 "active": bool(active), "source": source})
    state.effects.by_unit.setdefault(int(owner_id), []).append(inst)


def _kill(state, uid: int) -> None:
    e = state.get_entity(uid)
    e.get_component(HealthComponent).hp = 0
    uc = e.get_component(UnitComponent)
    if uc is not None:
        uc.alive = False


# ═══ 1098 RammingSpeed_ExtraExplode -- `CreateTargetTrigger` = `On(0x3a = PhaseEnd)` nu ═════════

def _ramming_verdict(active: bool) -> bool:
    st = _state()
    _seed_effect(st, CARRIER_ID, "RammingSpeed_ExtraExplode", RAMMING_SPEED_EXTRA_EXPLODE,
                 active=active)
    trg = RammingSpeedExtraExplodeRemove(CARRIER_ID)
    ev = TriggerEvent(int(EventTriggerType.PhaseEnd), CARRIER_ID, CARRIER_ID,
                      ranged=False, profile=None)
    return bool(trg.matches(st, ev))


def test_1098_fires_when_active():
    """L'arbre natif n'a AUCUN predicat -- le bras ACTIF doit donc rendre True sans condition.
    C'est ce bras qui rend le bras INACTIF probant."""
    assert _ramming_verdict(active=True) is True


def test_1098_is_gated_when_inactive():
    """Rail TARGETS -> `EvaluateEffectTriggerTargets` gate sur `IsActive`. Sans le gate, un 1098
    seede INERTE se ferait quand meme retirer -- et surtout le port divergerait du natif sur le
    seul etat que le canal `includeInactive` sait fabriquer."""
    assert _ramming_verdict(active=False) is False


# ═══ 1227 HarlequinsPanoply_IgnoreHits -- `CreateTargetTrigger` = `On(9) & OwnerIsTarget` ═══════

def _panoply_verdict(active: bool) -> bool:
    st = _state()
    _seed_effect(st, CARRIER_ID, "HarlequinsPanoply_IgnoreHits", HARLEQUINS_PANOPLY_IGNORE_HITS,
                 active=active)
    trg = HarlequinsPanoplyIgnoreHitsRemove(CARRIER_ID)
    ev = TriggerEvent(int(EventTriggerType.Attack), ATTACKER_ID, CARRIER_ID,
                      ranged=False, profile="Physical")
    return bool(trg.matches(st, ev))


def test_1227_fires_when_active_and_owner_is_target():
    assert _panoply_verdict(active=True) is True


def test_1227_is_gated_when_inactive():
    """Le porteur est une UNITE : l'etat inerte est SEEDABLE (`includeInactive`). Sans gate, un
    marqueur inerte annulait quand meme la cloture d'attaque -- degradation permissive."""
    assert _panoply_verdict(active=False) is False


def test_1227_owner_is_target_still_gates_when_active():
    """Anti-confond : le gate `IsActive` ne doit pas AVALER `get_OwnerIsTarget`. Une attaque du
    porteur contre quelqu'un d'autre ne retire pas son marqueur, meme actif."""
    st = _state()
    _seed_effect(st, CARRIER_ID, "HarlequinsPanoply_IgnoreHits", HARLEQUINS_PANOPLY_IGNORE_HITS,
                 active=True)
    trg = HarlequinsPanoplyIgnoreHitsRemove(CARRIER_ID)
    ev = TriggerEvent(int(EventTriggerType.Attack), CARRIER_ID, ATTACKER_ID,
                      ranged=False, profile="Physical")
    assert trg.matches(st, ev) is False


# ═══ 1186 / 1284 GhostEffect -- `CreateTargetTrigger` = `OnPreDeath & AreEqual(EffectSource, target)`

def _ghost_verdict(cls, name: str, effect_type: int, active: bool) -> bool:
    """Le porteur du ghost est une TUILE ; `owner_id` est un id de `boardGraph`, et le poseur
    (`EffectSource`) est l'unite qui meurt."""
    st = _state()
    tile = _tid(0, 0)
    _seed_effect(st, tile, name, effect_type, active=active, source=CARRIER_ID)
    _kill(st, CARRIER_ID)
    trg = cls(tile)
    ev = TriggerEvent(int(EventTriggerType.PreUnitDeath), CARRIER_ID, CARRIER_ID,
                      ranged=False, profile=None,
                      killer_id=ATTACKER_ID, dying_id=CARRIER_ID)
    return bool(trg.matches(st, ev))


def test_1186_ghost_revive_fires_when_active():
    assert _ghost_verdict(TimeFluxGhostEffectRevive, "TimeFlux_Revive",
                          TIME_FLUX_GHOST_EFFECT, True) is True


def test_1186_ghost_revive_is_gated_when_inactive():
    """LE cas que `case-229` decrivait comme « ecart structurellement lisible » : sur la mort du
    poseur, le natif oppose DEUX branches EXCLUSIVES -- la resurrection (rail TARGETS, gatee par
    `IsActive`) et le retrait n.4 (`NOT IsEffectActive`). Sans ce gate le port faisait LES DEUX."""
    assert _ghost_verdict(TimeFluxGhostEffectRevive, "TimeFlux_Revive",
                          TIME_FLUX_GHOST_EFFECT, False) is False


def test_1284_echoes_revive_fires_when_active():
    assert _ghost_verdict(EchoesFromTheWarpGhostEffectRevive, "EchoesFromTheWarp_Revive",
                          ECHOES_GHOST_EFFECT, True) is True


def test_1284_echoes_revive_is_gated_when_inactive():
    """#366-r1 a SCINDE `GhostEffectRevive` en deux instanciations. Le gap d'`EXPECTED_GAPS` n'a
    donc pas ete resorbe : il a DOUBLE, sous un nom que le probe ne regardait plus."""
    assert _ghost_verdict(EchoesFromTheWarpGhostEffectRevive, "EchoesFromTheWarp_Revive",
                          ECHOES_GHOST_EFFECT, False) is False


def test_the_two_branches_are_exclusive_on_source_death():
    """La propriete NATIVE, mesuree des deux cotes a la fois : sur `On(PreUnitDeath)` du poseur,
    EXACTEMENT une des deux branches mord. Ghost actif -> resurrection ; ghost inactif -> retrait.
    C'est cette exclusivite que l'absence de gate cassait."""
    for active in (True, False):
        st = _state()
        tile = _tid(0, 0)
        _seed_effect(st, tile, "TimeFlux_Revive", TIME_FLUX_GHOST_EFFECT,
                     active=active, source=CARRIER_ID)
        _kill(st, CARRIER_ID)
        ev = TriggerEvent(int(EventTriggerType.PreUnitDeath), CARRIER_ID, CARRIER_ID,
                          ranged=False, profile=None,
                          killer_id=ATTACKER_ID, dying_id=CARRIER_ID)
        revive = TimeFluxGhostEffectRevive(tile).matches(st, ev)
        # Le retrait n.4 lit `NOT IsEffectActive` -- sa face complementaire.
        from engine.runner.operations.triggers.loki.ghost_revive import (
            TimeFluxGhostRemoveOnSourceDeathInactive)
        removal = TimeFluxGhostRemoveOnSourceDeathInactive(tile).matches(
            st, TriggerEvent(int(EventTriggerType.UnitDeath), CARRIER_ID, CARRIER_ID,
                             ranged=False, profile=None,
                             killer_id=ATTACKER_ID, dying_id=CARRIER_ID))
        assert bool(revive) != bool(removal), \
            "branches non exclusives pour active=%s (revive=%s removal=%s)" % (
                active, revive, removal)


# ═══ garde ArraySet : on ne gate PAS ce que le natif ne gate pas ═════════════════════════════════

def test_the_probe_rail_covers_the_whole_registry():
    """CLIQUET DE COUVERTURE -- meme forme que `test_ability_registry_ratchet` (#167), et pour la
    meme raison : c'est un gisement que notre PROPRE cadence de portage alimente.

    `probe_229` verifie la conformite des classes qu'il CONNAIT ; il ne peut rien dire d'une classe
    absente de son `RAIL` saisi a la main. Au 2026-08-01, **19 des 46 classes inscrites** y
    manquaient -- dont QUATRE portant un gate absent. Pire, `EXPECTED_GAPS` citait un nom mort
    (`GhostEffectRevive`, scinde par #366-r1) : le probe imprimait « gap resorbe » pour un gap qui
    avait DOUBLE.

    Ce test double `probe_421_rail_covers_registry.py` (meme verdict, ~1,7 s) pour que la garde soit
    jouee par la SUITE, sans dependre de la discipline d'appel d'un probe."""
    from probe_229_effect_triggers_active import RAIL, EXPECTED_GAPS, ARRAYSET_READS_BY_TREE
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    registered = {c.__name__ for classes in EFFECT_TRIGGERS.values() for c in classes}
    # ⚠ LE NON-VIDE D'ABORD (#941-r3). Les quatre assertions qui suivent ne savent dire qu'une
    # chose : « cette DIFFERENCE d'ensembles est vide ». Deux ensembles VIDES la rendent vide
    # aussi -- un `EFFECT_TRIGGERS` effondre (import casse, registre vide) plus un `RAIL` vide
    # feraient passer les quatre. Le second test de ce bloc est PIRE : `missing == EXPECTED_GAPS`
    # avec les deux a `[]` est un vert PUR. Les bornes sont MESUREES le 2026-08-13
    # (47 types / 90 classes / 90 entrees RAIL) et ecrites BASSES : elles gardent l'effondrement,
    # pas la cadence -- le registre ne fait que croitre.
    assert len(EFFECT_TRIGGERS) >= 40 and len(registered) >= 80, (
        "population effondree : %d types d'effet / %d classes inscrites -- les differences "
        "d'ensembles ci-dessous seraient vides SANS RIEN AVOIR VISITE"
        % (len(EFFECT_TRIGGERS), len(registered)))
    assert len(RAIL) >= 80, (
        "`probe_229.RAIL` est tombe a %d entrees -- le cliquet compare le registre a un rail "
        "vide, donc il ne compare rien" % len(RAIL))
    assert not (registered - set(RAIL)), \
        "classe(s) inscrite(s) sans rail declare dans probe_229.RAIL : %s" % sorted(
            registered - set(RAIL))
    assert not (set(RAIL) - registered), \
        "entree(s) RAIL orpheline(s) (classe renommee/supprimee) : %s" % sorted(
            set(RAIL) - registered)
    assert not (set(EXPECTED_GAPS) - registered), \
        "EXPECTED_GAPS cite une classe non inscrite : %s" % sorted(
            set(EXPECTED_GAPS) - registered)
    assert not (set(ARRAYSET_READS_BY_TREE) - registered), \
        "ARRAYSET_READS_BY_TREE cite une classe non inscrite : %s" % sorted(
            set(ARRAYSET_READS_BY_TREE) - registered)


def test_no_targets_rail_trigger_is_left_without_its_gate():
    """Le verdict de `probe_229` lui-meme, en test : AUCUNE classe du rail TARGETS/APPLY_REVERT ne
    doit etre sans lecture du flag, et aucune classe du rail ArraySet ne doit en avoir une hors
    noeud d'arbre. `EXPECTED_GAPS` est VIDE depuis #421 -- ce test le maintient a zero."""
    import probe_229_effect_triggers_active as p
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    missing, extra = [], []
    vus = 0
    for etype, classes in EFFECT_TRIGGERS.items():
        for cls in classes:
            rail, _sym = p.RAIL.get(cls.__name__, ("?", "?"))
            reads = p._reads_active(cls)
            if rail in (p.TARGETS, p.APPLY_REVERT):
                vus += 1
            if rail in (p.TARGETS, p.APPLY_REVERT) and not reads:
                missing.append((etype, cls.__name__))
            if rail == p.ARRAYSET and reads and cls.__name__ not in p.ARRAYSET_READS_BY_TREE:
                extra.append((etype, cls.__name__))
    # ⚠ LE NON-VIDE, ET C'EST ICI QU'IL EST LE PLUS NECESSAIRE (#941-r3) : `EXPECTED_GAPS` est
    # VIDE, donc l'assertion qui suit s'ecrit `[] == []` des que la boucle ne visite RIEN. Un
    # registre effondre, ou un `RAIL` dont plus aucune entree ne porte le rail TARGETS, rendrait
    # ce test VERT sans avoir evalue un seul gate.
    # ⚠ LA BORNE EST MESUREE, PAS SUPPOSEE, et la premiere valeur ecrite ici (60) etait FAUSSE --
    # elle venait d'un « la plupart des 90 », pas d'un comptage. Ventilation REELLE du
    # 2026-08-13 : ARRAYSET 77, TARGETS 17, ENV_ABILITY 2, APPLY_REVERT 1 -- soit **18** classes
    # sur le rail garde ici, et non 86. La borne est ecrite BASSE (12) : elle garde
    # l'effondrement, pas la cadence.
    assert vus >= 12, (
        "la boucle n'a visite que %d classe(s) du rail TARGETS/APPLY_REVERT -- `missing == "
        "EXPECTED_GAPS` serait alors `[] == []`, un vert qui n'a rien mesure" % vus)
    assert sorted(n for _e, n in missing) == sorted(p.EXPECTED_GAPS), \
        "gate(s) `IsActive` manquant(s) sur le rail TARGETS : %s" % sorted(missing)
    assert not extra, \
        "gate `IsActive` sur le rail ArraySet (infidelite symetrique) : %s" % sorted(extra)


def test_arrayset_removal_is_NOT_gated_on_active():
    """`GhostEffect$$CreateHandleTriggerAbilitiesInternal` -> rail ArraySet ->
    `...$$EvaluateEffectTriggerEffectAbilities`, qui n'accede JAMAIS a `+0x5c`. Gater ces triggers
    serait l'infidelite SYMETRIQUE (c'est ce rail qui porte les `ActivateEffect` capables de
    rallumer un effet eteint). `OnSourceRemoved` doit donc mordre sur un ghost INACTIF aussi."""
    for active in (True, False):
        st = _state()
        tile = _tid(0, 0)
        _seed_effect(st, tile, "TimeFlux_Revive", TIME_FLUX_GHOST_EFFECT,
                     active=active, source=CARRIER_ID)
        ev = TriggerEvent(int(EventTriggerType.UnitRemoved), CARRIER_ID, CARRIER_ID,
                          ranged=False, profile=None, dying_id=CARRIER_ID)
        assert TimeFluxGhostRemoveOnSourceRemoved(tile).matches(st, ev) is True, \
            "le retrait ArraySet ne doit PAS dependre du flag (active=%s)" % active
