"""GARDE #936-r1-r2 (OFFLINE PURE) -- les ENFANTS d'un composite expire passent EUX AUSSI par le
FOYER de retrait ; la cascade `parent_type` n'est plus une MARQUE.

## L'ecart, et pourquoi il n'etait PAS << inobservable >>

#936-r1 a fait passer l'echeance du PARENT par `remove_effect_instance`. La cascade `parent_type`
qui suit, elle, posait encore `consumed = True` en direct sur les enfants dont le parent venait de
disparaitre. Le natif, lui, les retire par
`IdunBattle.Operations.RemoveEffectOperation$$RemoveSubEffects`, dont le corps est un appel au slot
0x11 sur CHAQUE enfant -- donc le MEME `RemoveEffectOperation$$Execute`, recursivement.

⚠ **LA FICHE DU RESIDU ANNONCAIT << INOBSERVABLE EN L'ETAT >>, ET C'EST FAUX SUR UN CANAL QU'ELLE
N'A PAS REGARDE.** Son raisonnement ne portait que sur les trois VECTEURS (aucun consommateur porte
d'`On(0x3f)`/`On(0x40)` ; le seul d'`On(0x3b)` est `WrathfulDevotion`, et aucun enfant permanent
porte n'est untargetable). Mais `remove_effect_instance` appelle AUSSI `unregister_name`, et les
enfants SONT inscrits a l'`EffectsOwnedComponent` a la pose -- `AddEffectOperation._spawn_sub_effects`
fait `_register_name(state, child_target, child.name)`, une ligne par enfant. Un enfant seulement
MARQUE gardait donc son NOM COLLE sur le porteur, sur le canal que LIT la couche DECISION
(`ai/state_bridge.py`, `playbook/scene.py`) -- exactement la fuite que #936-r1 a corrigee pour le
PARENT, et qu'elle nomme explicitement.

C'est l'etage `test_l_enfant_DECOLLE_son_nom...` qui mesure ce fait ; il est la raison pour laquelle
cette tranche vaut mieux qu'un nettoyage de forme.

## Pourquoi la cascade SUBSISTE a cote de `_remove_sub_effects`

Le foyer appelle deja `_remove_sub_effects` sur le parent, mais celui-ci DERIVE les enfants de
`parent.sub_effects_on_apply()` et sort immediatement si le parent n'en declare AUCUN. Les liens
reconstruits a l'hydratation (`snapshot._load_effect_parent_links`) n'ont pas de specs : la cascade
est leur SEUL chemin. Les deux domaines se recouvrent partiellement, et l'idempotence de
`remove_effect_instance` (gates `+0x5f`/`+0x5e`) rend le recouvrement inoffensif.

ASCII only (console cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.dsl.event_trigger_type import EventTriggerType                 # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.effects import aura_selectors as AURA                 # noqa: E402
from engine.entities.effects.base import BaseEffect                        # noqa: E402
from engine.entities.effects_state import EffectsState                     # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.components import EffectsOwnedComponent                 # noqa: E402
from engine.runner.operations import turnflow as TF                        # noqa: E402
from engine.runner.operations.triggers.dispatch import move_death as MD    # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects_state.py",
        "scripts/python/engine/runner/operations/turnflow.py",
        "scripts/python/engine/runner/operations/remove_effects.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        "scripts/python/engine/entities/effects/aura_selectors.py",
        # le canal des NOMS -- il porte `_register_name` (pose des enfants) ET `unregister_name`
        # (ce que le routage declenche). C'est le foyer de l'observable de cette tranche.
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "scripts/python/engine/runner/snapshot.py",
    ),
    "build": False,
    "toujours": False,
    "raison": ("100 % offline : la chaine native (`RemoveSubEffects` -> slot 0x11) est deja gravee "
               "par l'etage binaire de `test_936r1_expiry_removal_offline`, et la redoubler ici "
               "serait la duplication que #531 interdit. Ce fichier mesure le PORT."),
}

COLS, ROWS = 7, 7
CARRIER, FOE = 10, 20

#: Parent a TIMER et enfant PERMANENT -- le regime exact du residu (l'enfant a timer propre, lui,
#: arrive a echeance dans la MEME boucle et passait deja par le foyer).
ET_PARENT = 7701
ET_ENFANT = 7702
#: Un type du domaine `UNTARGETABLE_EFFECT_TYPES`, pour exercer le 3e vecteur sur un ENFANT.
UNTARGETABLE = int(EffectType.FearOfTheUnseen_TeleportingIn)      # 1238


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    import hexgeo
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


@pytest.fixture
def state():
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": CARRIER, "visualId": "tyranDeathleaper", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 0, "row": 3}, "effects": []},
        {"id": FOE, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 6, "row": 6}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 1000, "movement": 3, "turnsStarted": 0},
                           "healthMax": 1000, "traits": [], "unitFlags": [],
                           "unitConfig": {"visualId": u["visualId"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in decision["units"]]}
    st = load_state(decision, observe, snapshot, board=board, ability_states=False)
    if st.effects is None:
        st.effects = EffectsState()
    return st


def _pose(st, effect_type: int, name: str, *, duration=None, parent_type=None) -> BaseEffect:
    """Une instance sur le porteur, plus son NOM dans l'`EffectsOwnedComponent` -- ce que fait
    `_register_name`, POUR LES ENFANTS AUSSI (`_spawn_sub_effects` l'appelle par enfant)."""
    eff = BaseEffect(name=name, effect_type=int(effect_type),
                     remaining_turns=(None if duration is None else int(duration)),
                     target=CARRIER, active=True)
    eff.parent_type = None if parent_type is None else int(parent_type)
    st.effects.add_effect(CARRIER, eff)
    ent = st.get_entity(CARRIER)
    comp = ent.get_component(EffectsOwnedComponent)
    if comp is None:
        comp = EffectsOwnedComponent([])
        ent.add_component(comp)
    comp.effects.append(name)
    return eff


def _composite(st, *, enfant_type=ET_ENFANT, enfant_nom="Enfant"):
    """Parent a `remaining = 1` (il expire au prochain tick) + enfant PERMANENT qui le pointe."""
    parent = _pose(st, ET_PARENT, "Parent", duration=1)
    enfant = _pose(st, enfant_type, enfant_nom, duration=None, parent_type=ET_PARENT)
    return parent, enfant


class _Espion:
    """Substitue les TROIS emetteurs du foyer et journalise leurs appels. On substitue le MODULE
    (`move_death`), pas le symbole importe : `remove_effects` le lie en forme B exactement pour que
    cette substitution morde."""

    def __init__(self, monkeypatch):
        self.vus: list = []
        for nom, ev in (("pre_effect_removed_triggers", EventTriggerType.PreEffectRemoved),
                        ("effect_removed_triggers", EventTriggerType.EffectRemoved),
                        ("unit_became_targetable_triggers",
                         EventTriggerType.UnitBecameTargetable)):
            monkeypatch.setattr(MD, nom, self._faire(int(ev)))

    def _faire(self, event_id: int):
        def _f(state, target_id, effect_type):
            self.vus.append((event_id, int(target_id), int(effect_type)))
            return []
        return _f

    def pour(self, effect_type: int) -> list:
        return [e for (e, _t, x) in self.vus if x == int(effect_type)]


# ------------------------------------------ etage 0 : le montage emprunte bien la voie CASCADE

def test_le_montage_passe_par_la_CASCADE_et_non_par_RemoveSubEffects(state):
    """CONTROLE DE NON-DEGENERESCENCE, et il est load-bearing.

    `remove_effect_instance` appelle deja `_remove_sub_effects` sur le parent -- mais ce dernier
    derive ses enfants de `parent.sub_effects_on_apply()`. Si le parent de ce montage en declarait,
    les etages suivants seraient verts SANS RIEN MESURER de la cascade : ils mesureraient l'autre
    chemin, celui qui marchait deja."""
    parent, enfant = _composite(state)
    assert parent.sub_effects_on_apply() == [], (
        "le parent du montage DECLARE des sous-effets -- `_remove_sub_effects` prendrait les "
        "enfants et la cascade ne serait plus exercee")
    assert enfant.parent_type == ET_PARENT and enfant.remaining_turns is None, (
        "l'enfant doit etre PERMANENT et pointer le parent : c'est le regime du residu")


# ------------------------------------------------------- etage 1 : LE FIX (les trois vecteurs)

def test_l_enfant_d_un_composite_expire_publie_ses_vecteurs(state, monkeypatch):
    """LE FIX. Le parent expire au tick ; son enfant PERMANENT est retire PAR LE FOYER, donc il
    publie ses PROPRES `On(0x3f)` / `On(0x40)`.

    TEMOIN NON DEGENERE : on verifie que le PARENT publie les siens aussi (acquis de #936-r1) et que
    l'enfant en publie SEPAREMENT -- sinon un test qui compterait les vecteurs globaux serait vert
    sur les seuls vecteurs du parent."""
    parent, enfant = _composite(state)
    espion = _Espion(monkeypatch)
    state.effects.on_turn_end(CARRIER, attacked=False, state=state)

    assert parent.consumed and enfant.consumed
    assert espion.pour(ET_PARENT) == [int(EventTriggerType.PreEffectRemoved),
                                      int(EventTriggerType.EffectRemoved)], espion.vus
    assert espion.pour(ET_ENFANT) == [int(EventTriggerType.PreEffectRemoved),
                                      int(EventTriggerType.EffectRemoved)], (
        "l'ENFANT ne publie pas ses vecteurs -- la cascade pose encore la marque en direct : %s"
        % espion.vus)


def test_un_enfant_UNTARGETABLE_publie_aussi_le_TROISIEME_vecteur(state, monkeypatch):
    """`On(0x3b = UnitBecameTargetable)` est sous un gate de TYPE. Aucun enfant permanent PORTE n'est
    aujourd'hui untargetable -- c'est ce qui rendait l'ecart discret -- mais le mecanisme doit etre
    la le jour ou un composite en pose un, sinon le porteur redeviendrait ciblable en silence.

    C'est la raison pour laquelle ce vecteur est exerce ICI, sur un montage, et non attendu d'un
    porteur reel."""
    assert UNTARGETABLE in {int(t) for t in AURA.UNTARGETABLE_EFFECT_TYPES}
    _composite(state, enfant_type=UNTARGETABLE, enfant_nom="FearOfTheUnseen_TeleportingIn")
    espion = _Espion(monkeypatch)
    state.effects.on_turn_end(CARRIER, attacked=False, state=state)
    assert espion.pour(UNTARGETABLE) == [int(EventTriggerType.PreEffectRemoved),
                                         int(EventTriggerType.EffectRemoved),
                                         int(EventTriggerType.UnitBecameTargetable)], espion.vus


# ------------------------------------- etage 2 : L'OBSERVABLE que la fiche disait inexistant

def test_l_enfant_DECOLLE_son_nom_de_l_EffectsOwnedComponent(state):
    """L'OBSERVABLE REEL de cette tranche, et il CONTREDIT le << inobservable en l'etat >> de la
    fiche.

    Les enfants sont inscrits au canal des NOMS a la pose (`_spawn_sub_effects` ->
    `_register_name`), et ce canal est LU par la couche DECISION. Un enfant seulement MARQUE gardait
    son nom colle : la fuite etait donc visible bien avant qu'un consommateur de vecteur existe."""
    _composite(state)
    comp = state.get_entity(CARRIER).get_component(EffectsOwnedComponent)
    assert {"Parent", "Enfant"} <= set(comp.effects)          # pose : les deux noms sont la
    state.effects.on_turn_end(CARRIER, attacked=False, state=state)
    assert "Parent" not in comp.effects, "acquis de #936-r1 perdu"
    assert "Enfant" not in comp.effects, (
        "le NOM de l'enfant reste COLLE a l'`EffectsOwnedComponent` -- la couche decision continue "
        "de voir un effet retire : %s" % comp.effects)


def test_le_REPLI_sans_state_laisse_les_deux_noms_COLLES(state):
    """CONTRE-EPREUVE de l'etage precedent : sans `state`, les deux noms restent. C'est bien le
    ROUTAGE qui les decolle, pas un effet de bord du montage -- et c'est aussi la garantie que le
    repli reste le comportement STRICTEMENT anterieur."""
    _, enfant = _composite(state)
    comp = state.get_entity(CARRIER).get_component(EffectsOwnedComponent)
    state.effects.on_turn_end(CARRIER, attacked=False)
    assert enfant.consumed is True, "le repli doit quand meme CONSOMMER l'enfant"
    assert {"Parent", "Enfant"} <= set(comp.effects), (
        "le repli ne doit RIEN decoller (comportement anterieur) : %s" % comp.effects)


# --------------------------------------------------- etage 3 : LE POINT FIXE ET SA TERMINAISON

def test_la_cascade_descend_sur_PLUSIEURS_niveaux(state):
    """Point fixe : parent -> enfant -> petit-enfant. Chaque niveau doit passer par le foyer.

    Le chainage est ce qui rend la boucle necessaire ; un routage qui ne traiterait que le premier
    niveau laisserait le petit-enfant derriere lui."""
    _pose(state, ET_PARENT, "Parent", duration=1)
    _pose(state, ET_ENFANT, "Enfant", duration=None, parent_type=ET_PARENT)
    petit = _pose(state, 7703, "PetitEnfant", duration=None, parent_type=ET_ENFANT)
    comp = state.get_entity(CARRIER).get_component(EffectsOwnedComponent)
    state.effects.on_turn_end(CARRIER, attacked=False, state=state)
    assert petit.consumed, "le petit-enfant survit -- le point fixe ne descend pas"
    assert not ({"Parent", "Enfant", "PetitEnfant"} & set(comp.effects)), comp.effects


def test_la_cascade_TERMINE_meme_si_le_foyer_REFUSE(state, monkeypatch):
    """TERMINAISON. `changed` est desormais pilote par le RESULTAT du foyer ; un foyer qui rendrait
    `False` sans consommer ferait boucler indefiniment. On substitue un foyer qui refuse TOUT et on
    exige que l'appel rende la main -- la garde se termine, elle ne se relache pas.

    (`pytest` n'a pas de timeout par defaut : sans ce cran, la regression serait un HANG de la passe
    entiere, pas un rouge.)"""
    import engine.runner.operations.remove_effects as REM
    _, enfant = _composite(state)
    monkeypatch.setattr(REM, "remove_effect_instance", lambda *a, **k: False)
    state.effects.on_turn_end(CARRIER, attacked=False, state=state)
    assert enfant.consumed is True, (
        "un foyer qui refuse doit quand meme terminer la cascade (sinon : boucle infinie)")


def test_un_enfant_DEJA_consomme_n_est_pas_re_retire(state, monkeypatch):
    """Idempotence : le recouvrement avec `_remove_sub_effects` (qui traite les enfants DECLARES par
    le parent) ne doit pas produire un second retrait, donc pas un second jeu de vecteurs."""
    _, enfant = _composite(state)
    enfant.consumed = True
    espion = _Espion(monkeypatch)
    state.effects.on_turn_end(CARRIER, attacked=False, state=state)
    assert espion.pour(ET_ENFANT) == [], (
        "un enfant deja consomme a republie ses vecteurs : %s" % espion.vus)


# ------------------------------------------------------------- etage 4 : LE CHEMIN DE PRODUCTION

def test_le_chemin_de_PRODUCTION_fait_cascader_par_le_foyer(state, monkeypatch):
    """Comme pour #936-r1 : ce n'est pas `on_turn_end` qui doit savoir emettre, c'est
    `EndTurnOperation` qui doit lui passer `state`. Un appelant qui l'oublierait re-fabriquerait le
    collapse sur les enfants sans qu'aucun etage ci-dessus ne bouge."""
    _composite(state)
    espion = _Espion(monkeypatch)
    TF.EndTurnOperation.execute(state, advance=False)
    assert espion.pour(ET_ENFANT) == [int(EventTriggerType.PreEffectRemoved),
                                      int(EventTriggerType.EffectRemoved)], espion.vus
