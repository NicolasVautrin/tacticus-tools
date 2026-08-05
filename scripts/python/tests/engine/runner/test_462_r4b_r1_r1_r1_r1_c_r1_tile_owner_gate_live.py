"""#462-r4b-r1-r1-r1-r1-c-r1 -- le gate d'owner d'`evaluate_trigger_operation` et les TUILES.

Le residu de la tranche `-c` accusait `collect_effect_triggers` d'etre << structurellement aveugle
aux effets de TUILE >>. La mesure DEPLACE l'accusation, et ce fichier la GARDE :

  * `EffectsState.by_unit` est clee par id d'ENTITE -- une tuile y a sa place, et le collecteur
    INSTANCIE bien son trigger (bras 1, controle positif) ;
  * c'est le gate d'owner qui le JETAIT, parce que son critere etait l'attribut de CLASSE
    `owner_is_tile` alors que la nature du porteur est une propriete de l'INSTANCE d'effet.

Cote natif (build `rnca9r7q6c`) le seul discriminant est
`IdunBattle.Entities.EntityExtensions$$IsUnit(owner)` :

  * `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` -- `IsUnit` VRAI ->
    `UnitExtensions$$IsAlive` + `UnitExtensions$$IsTriggersDisabled` ; FAUX -> aucun gate ;
  * `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetEffectTrigger` et la branche EFFET
    d'`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityOrEffectTrigger` --
    AUCUN appel a `IsUnit` ni a `IsAlive` : leur premier gate est un corps DEDUPLIQUE `return 1`.

LE BRAS QUI MORD (`test_le_dot_du_feu_survit_a_la_perte_de_owner_is_tile_live`) porte sur un effet
REEL et OBSERVABLE -- le `FireEffect` (5) d'une tuile en feu et son DoT de 20 % des PV max -- monte
sur un BOARD et des UNITES reels tires du harnais. Il retire a `FireTileDoT` son attribut de classe
`owner_is_tile` : AVANT le correctif, le DoT disparait ; APRES, il tient, parce que le gate lit
desormais la NATURE du porteur. La contre-epreuve du meme test neutralise `_owner_is_tile_entity`
et le DoT redisparait -- c'est ce qui ATTRIBUE le passage au nouveau predicat, et non a autre chose.

⚠ CE N'EST PAS UN PORTEUR NATUREL, et le dire fait partie de la mesure : `--step registre` du probe
etablit qu'AUCUN `effect_type` servi par une classe NUE n'est aujourd'hui pose sur une tuile (les
cinq familles d'effet de tuile a triggers -- Fire 5, Ghost 1186/1284, Contaminated 1244,
DespoiledGround 1476 -- declarent toutes `TileEffectTrigger`). Le trou est donc LATENT : il ne
change aucun observable aujourd'hui, et c'est exactement pourquoi il a survecu a trois rencontres.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import gameconfig as GC                                                    # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402
from engine.runner.state import State                                      # noqa: E402
from engine.runner.components import HealthComponent, PositionComponent    # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.entities.effects_state import EffectsState                     # noqa: E402
from engine.entities.effects import EffectFactory                          # noqa: E402
from engine.runner.operations.triggers.base import (EffectTrigger,         # noqa: E402
                                                    TriggerEvent, TileEffectTrigger)
from engine.runner.operations.triggers.dispatch import core as CORE        # noqa: E402
from engine.runner.operations.triggers.dispatch import registry as REG     # noqa: E402
from engine.runner.operations.triggers.loki import (FIRE_TILE,             # noqa: E402
                                                    FIRE_DMG_PCT_KEY, FireTileDoT)
from engine.dsl.event_trigger_type import EventTriggerType                 # noqa: E402

TICK_ENV = int(EventTriggerType.TurnStart_EnvironmentEffects)   # `On(0x14)` -- le vecteur du DoT
_TUILE_SYNTH = 900001


# ─────────────────────────────────────────────────────────── sonde (bras de MECANISME)

class _SondeTrigger(EffectTrigger):
    """Effet-trigger NU (surtout PAS `TileEffectTrigger`) qui NOTE s'il a ete evalue.

    Il ne mute rien : `matches` enregistre le passage puis rend `False`. C'est le capteur du gate --
    si `evaluate_trigger_operation` l'ecarte AVANT `matches`, la liste reste vide."""
    event_id = 2
    vus: list = []

    def matches(self, state, ev) -> bool:
        _SondeTrigger.vus.append(int(self.owner_id))
        return False

    def execute_behaviour(self, state, ev):
        return None


def _effect_type_a_classes_nues() -> int:
    """Un `effect_type` du registre dont TOUTES les classes sont des `EffectTrigger` nus.

    DERIVE du registre, jamais recopie : si le port cablait un jour toutes ses classes en
    `TileEffectTrigger`, ce helper ferait ECHOUER le test au lieu de le rendre sans objet."""
    for et, classes in sorted(REG.EFFECT_TRIGGERS.items()):
        if classes and not any(issubclass(c, TileEffectTrigger) for c in classes):
            return int(et)
    pytest.fail("aucun effect_type a classes exclusivement nues : le montage n'a plus d'objet")


def _state_tuile(effect_type: int, avec_board: bool = True):
    """`State` + BOARD d'une tuile + un effet porte par cette entite-TUILE (absente de
    `state.entities`, comme toute tuile)."""
    st = State()
    st.effects = EffectsState()
    if avec_board:
        st.board = Board([{"id": _TUILE_SYNTH, "col": 0, "row": 0, "walkable": True,
                           "elevation": 0, "neighbours": []}], adjacency="evenq")
    st.effects.add_effect(_TUILE_SYNTH, EffectFactory.create(
        {"name": "SondeTileEffect", "effectType": int(effect_type), "remaining": 0},
        100, None, None))
    return st


def _passages_sonde(et: int, avec_board: bool) -> list:
    st = _state_tuile(et, avec_board=avec_board)
    sauf = REG.EFFECT_TRIGGERS.get(et)
    _SondeTrigger.vus = []
    try:
        REG.EFFECT_TRIGGERS[et] = [_SondeTrigger]      # le dict EST celui que lit `collect_*`
        CORE.evaluate_trigger_operation(
            st, TriggerEvent(2, _TUILE_SYNTH, _TUILE_SYNTH, ranged=False, profile=None))
    finally:
        if sauf is None:
            REG.EFFECT_TRIGGERS.pop(et, None)
        else:
            REG.EFFECT_TRIGGERS[et] = sauf
    return list(_SondeTrigger.vus)


def test_le_collecteur_voit_deja_les_effets_de_tuile():
    """CONTROLE POSITIF, et refutation de la premisse du residu.

    `collect_effect_triggers` itere `state.effects.by_unit`, dont les cles sont des ids d'ENTITE --
    tuiles comprises (`TileEffectTrigger` le dit, `EndTurnOperation$$RefreshEffects` #102 aussi, et
    `snapshot._load_tile_effects` charge par ce meme chemin). Il INSTANCIE donc bien le trigger d'un
    effet de tuile, avec l'id de tuile en `owner_id`. Le residu accusait le mauvais etage."""
    et = _effect_type_a_classes_nues()
    st = _state_tuile(et)
    trigs = CORE.collect_effect_triggers(st)
    assert trigs, ("collect_effect_triggers n'instancie RIEN pour un effet de tuile "
                   "(effect_type=%d) -- la premisse du residu serait alors vraie" % et)
    assert {int(t.owner_id) for t in trigs} == {_TUILE_SYNTH}, \
        "l'owner du trigger collecte doit etre l'ID DE TUILE : %s" % [t.owner_id for t in trigs]


def test_le_gate_laisse_passer_un_trigger_nu_porte_par_une_tuile():
    """LE MECANISME. Un `EffectTrigger` NU porte par une TUILE doit atteindre son `matches`.

    Mirror de la face EFFET du natif, qui n'applique AUCUN gate d'owner
    (`CanGetEffectTrigger` commence par un corps `return 1`), et de `CanGetAbilityTrigger`, qui ne
    gate que si `EntityExtensions$$IsUnit(owner)` est VRAI."""
    et = _effect_type_a_classes_nues()
    assert _passages_sonde(et, avec_board=True), (
        "le gate d'owner JETTE le trigger d'un porteur TUILE (effect_type=%d) -- c'est le trou "
        "#462-r4b-r1-r1-r1-r1-c-r1" % et)


def test_le_gate_reste_ferme_sur_un_owner_qui_n_est_ni_unite_ni_tuile():
    """CONTRE-EPREUVE de portee : le correctif CONDITIONNE le gate, il ne le SUPPRIME pas.

    Meme montage, board retire : l'id du porteur ne designe alors plus rien de connu, et l'entree
    doit rester ecartee. Si ce bras passait, `_owner_is_tile_entity` rendrait `True` pour n'importe
    quel id absent -- ce qui ferait entrer, entre autres, les porteurs RETIRES du state."""
    et = _effect_type_a_classes_nues()
    assert not _passages_sonde(et, avec_board=False), (
        "un owner introuvable ET hors board passe le gate : le gate a ete supprime, pas conditionne")


def test_le_gate_alive_reste_pose_sur_un_porteur_unite():
    """NON-REGRESSION du SURPLUS documente (`#462-r4b-r1-r1-r1-r1-c-r2`).

    Le correctif ne touche QUE les porteurs non-unite. Un effet porte par une unite MORTE reste
    ecarte comme avant -- c'est un surplus du port par rapport au natif (qui ne gate pas la face
    effet), nomme en residu et volontairement NON eleve ici : l'elargir demanderait sa propre
    confrontation."""
    from engine.runner.components import UnitComponent
    et = _effect_type_a_classes_nues()
    st = State()
    st.effects = EffectsState()
    ent = st.add_entity()
    uid = int(ent.id)
    ent.add_component(UnitComponent(visual_id="sonde", alive=False))
    st.effects.add_effect(uid, EffectFactory.create(
        {"name": "SondeUnitEffect", "effectType": int(et), "remaining": 0}, 100, None, None))
    sauf = REG.EFFECT_TRIGGERS.get(et)
    _SondeTrigger.vus = []
    try:
        REG.EFFECT_TRIGGERS[et] = [_SondeTrigger]
        CORE.evaluate_trigger_operation(st, TriggerEvent(2, uid, uid, ranged=False, profile=None))
    finally:
        if sauf is None:
            REG.EFFECT_TRIGGERS.pop(et, None)
        else:
            REG.EFFECT_TRIGGERS[et] = sauf
    assert not _SondeTrigger.vus, \
        "le gate `owner vivant` a saute pour un porteur UNITE morte -- hors perimetre du correctif"


# ─────────────────────────────────────────────── le bras qui MORD : un effet de tuile REEL

def _tuile_occupee(state: State):
    """`(tile_id, unit_id)` d'une unite VIVANTE posee sur une tuile du board. `(None, None)` si
    l'etat charge n'en offre aucune (traite comme un ECHEC par l'appelant, jamais un skip)."""
    board = state.board
    if board is None:
        return None, None
    for uid, e in state.entities.items():
        pc = e.get_component(PositionComponent)
        hc = e.get_component(HealthComponent)
        if pc is None or hc is None or not hc.hp_max:
            continue
        tid = board.id_at(pc.col, pc.row)
        if tid is not None:
            return int(tid), int(uid)
    return None, None


def _dot_dispatche(state: State, tile_id: int) -> int:
    """Somme des DoT rendus par le dispatch de `On(0x14)` pour la tuile `tile_id`. 0 = le trigger
    n'a rien fait (jete par le gate, ou occupant introuvable)."""
    res = CORE.evaluate_trigger_operation(
        state, TriggerEvent(TICK_ENV, tile_id, tile_id, ranged=False, profile=None))
    return sum(int(r.get("dot") or 0) for r in res
               if isinstance(r, dict) and r.get("tile_effect") == "Fire")


@pytest.fixture(scope="module")
def etat_avec_tuile_en_feu(rpc, build_runner):
    """Un BOARD et des UNITES reels (harnais), plus un `FireEffect` (5) pose sur la tuile d'un
    occupant. Le feu est pose OFFLINE par le meme append que le natif
    (`EffectsState.add_effect(tile_id, ...)`, mirror d'`AddEffectOperation$$AddNewEffect`, qui ne
    regarde jamais l'`EntityType` de la cible) : ce qui est sous test est le GATE, pas la voie de
    pose -- et l'allumer live couterait huit rounds de drive pour le meme etat.

    Portee MODULE : un seul runner pour tout le fichier (budget partage)."""
    rid = build_runner("777")["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indisponible -- montage non installe"
    board = Board(bg["tiles"], adjacency="native_sym")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    st = load_state(dec, ob, snap, board=board, tiles=tm)
    tile_id, uid = _tuile_occupee(st)
    assert tile_id is not None, "aucune unite posee sur une tuile du board -- montage non installe"
    st.effects.add_effect(tile_id, EffectFactory.create(
        {"name": "Fire", "effectType": int(FIRE_TILE), "level": 1, "remaining": 4}, 100, None, None))
    return {"state": st, "tile": tile_id, "unit": uid, "rid": rid, "tiles": tm}


def test_le_dot_du_feu_survit_a_la_perte_de_owner_is_tile_live(etat_avec_tuile_en_feu, monkeypatch):
    """LE BRAS QUI MORD, sur un effet REEL. Trois mesures sur le MEME etat :

      A. `FireTileDoT` intact (`owner_is_tile = True`)   -> DoT applique  (chemin historique)
      B. attribut de classe RETIRE                       -> DoT applique  (le gate lit la NATURE)
      C. B + `_owner_is_tile_entity` neutralise          -> DoT NUL       (attribution)

    A est le controle positif : il dit que le montage brule vraiment. B est l'invariant : AVANT le
    correctif il rendait 0, parce que le gate ne savait reconnaitre un porteur-tuile que par un
    attribut de CLASSE. C attribue le passage de B au nouveau predicat et a lui seul."""
    assert GC.global_value(FIRE_DMG_PCT_KEY), "fireDmgPct absent du gameconfig -- montage inexploitable"
    st, tile_id = etat_avec_tuile_en_feu["state"], etat_avec_tuile_en_feu["tile"]

    dot_a = _dot_dispatche(st, tile_id)
    assert dot_a > 0, ("A : le DoT du feu ne s'applique pas MEME avec `owner_is_tile` -- le montage "
                       "ne brule pas, la suite ne prouverait rien (tuile=%d)" % tile_id)

    monkeypatch.setattr(FireTileDoT, "owner_is_tile", False, raising=False)
    dot_b = _dot_dispatche(st, tile_id)
    assert dot_b > 0, ("B : prive de son attribut de CLASSE, le trigger d'un effet de tuile REEL "
                       "est jete -- c'est le trou #462-r4b-r1-r1-r1-r1-c-r1 (A=%d)" % dot_a)

    monkeypatch.setattr(CORE, "_owner_is_tile_entity", lambda state, owner_id: False)
    dot_c = _dot_dispatche(st, tile_id)
    assert dot_c == 0, ("C : le DoT passe encore alors que le predicat de nature est neutralise -- "
                        "le passage de B n'est PAS attribuable a `_owner_is_tile_entity` (C=%d)"
                        % dot_c)


def test_aucun_effect_type_de_tuile_du_registre_n_a_de_classe_nue_live(etat_avec_tuile_en_feu):
    """LE GISEMENT, mesure et non suppose : quels `effect_type` sont REELLEMENT portes par des
    tuiles dans une bataille, et lesquels ont un trigger servi par une classe NUE ?

    Ce test ne garde pas le correctif -- il garde l'ENONCE << le trou est latent >>. S'il rougit un
    jour, c'est qu'un porteur NATUREL est apparu : le correctif devient alors observable, et le
    bras precedent cesse d'etre le seul temoin. C'est un signal, pas une regression."""
    tm = etat_avec_tuile_en_feu["tiles"]
    rows = (tm.get("tiles") if isinstance(tm, dict) else tm) or []
    types_live = {int(e.get("effectType")) for t in rows for e in (t.get("effects") or [])
                  if isinstance(e, dict) and e.get("effectType") is not None}
    nues = {int(et) for et, classes in REG.EFFECT_TRIGGERS.items()
            if classes and not any(issubclass(c, TileEffectTrigger) for c in classes)}
    croise = sorted(types_live & nues)
    print("\n[gisement] effect_type portes par des TUILES (live) : %s" % sorted(types_live))
    print("[gisement] effect_type du registre a classes NUES : %d" % len(nues))
    print("[gisement] intersection (porteurs NATURELS du trou) : %s" % croise)
    assert not croise, (
        "un effect_type porte par une TUILE est servi par une classe NUE : %s -- le trou n'est "
        "plus latent, ce porteur doit etre confronte" % croise)
