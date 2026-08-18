"""GARDE #936-r1 (OFFLINE PURE) -- une expiration par TIMER passe par le FOYER de retrait, elle
n'est pas une MARQUE.

CE QUE CE FICHIER PROTEGE, et pourquoi la regression est MUETTE :

`EffectsState.on_turn_end` posait `consumed = True` en direct sur l'echeance. Consequences, toutes
SILENCIEUSES (ni erreur, ni crash, ni test rouge) :

  * aucun des trois vecteurs de `IdunBattle.Operations.RemoveEffectOperation$$Execute` ne sortait
    -- `On(0x3f = PreEffectRemoved)`, `On(0x40 = EffectRemoved)`, et sous son gate de TYPE
    `On(0x3b = UnitBecameTargetable)`. Le dernier a un consommateur PORTE
    (`WrathfulDevotionAbility` face B, #936) : un porteur dont l'Untargetable EXPIRE au lieu d'etre
    retire par un trigger redevenait ciblable sans que personne ne le voie ;
  * le NOM de l'effet restait colle a l'`EffectsOwnedComponent` du porteur (`unregister_name`
    n'etait jamais appele) -- canal LU par la couche DECISION ;
  * la revocation ne passait pas par `<Effect>.RevertInternal` complet mais par les trois foyers
    << colles au tick >> de `turnflow`, qui ne couvrent ni les modifications d'ability ni les
    stat-OVERRIDES.

LA CHAINE NATIVE EST LUE, PAS DEDUITE (etage 1, re-derive du PE a chaque passe) :

    IdunBattle.Operations.EndTurnOperation$$RefreshEffects
        foreach entite-effet : if (!Removed@+0x5f && HasTurns@+0x5d)
                                   EffectComponent$$RemoveOneTurn        <- le DECREMENT, seul
        RefreshEffectOptions(trigger = RefreshEffectTrigger.TurnChanged = 6)
        processor.<slot 0x2f>(options)
            -> IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect
                 if (EffectComponent$$ShouldBeRemoved) {
                     RefreshEffectsOperation$$DeactivateEffect(...)       <- le REVERT
                     actions.Add(new Action(<>c__DisplayClass9_0.<RemoveEffect>b__0))
                 }

et `RefreshEffectsOperation.<>c__DisplayClass9_0$$<RemoveEffect>b__0` n'a QU'UN corps :
`processor.<slot 0x11>(this.effectEntity)` -- le MEME slot que
`IdunBattle.Operations.RemoveEffectsOperation$$Execute` appelle, donc le MEME
`RemoveEffectOperation$$Execute`. L'echeance et le retrait explicite convergent sur UN corps.

ASCII only. Aucune VA en dur (les adresses sont resolues par `data/symbols/<build>/ghidra/functions.tsv`).
"""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

import pe_symboles as PE
import hexgeo
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.effect_type import EffectType
from engine.entities.effects import aura_selectors as AURA
from engine.entities.effects.base import BaseEffect
from engine.entities.effects_state import EffectsState
from engine.entities.pathfinding.board import Board
from engine.runner.components import EffectsOwnedComponent
from engine.runner.operations import turnflow as TF
from engine.runner.operations.triggers.dispatch import move_death as MD
from engine.runner.snapshot import load_state

DECLENCHEUR = {
    "chemins": (
        # le tick lui-meme, et l'appelant de production qui lui passe `state`
        "scripts/python/engine/entities/effects_state.py",
        "scripts/python/engine/runner/operations/turnflow.py",
        # le foyer par lequel l'echeance route desormais, et le module qui construit les vecteurs
        "scripts/python/engine/runner/operations/remove_effects.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        # le domaine du gate de TYPE (`is UntargetableEffect`) que le 3e vecteur consulte
        "scripts/python/engine/entities/effects/aura_selectors.py",
        # le canal des NOMS que le foyer nettoie (`unregister_name`)
        "scripts/python/engine/runner/operations/effects.py",
        # les mirrors d'enum dont ce fichier FIGE les ordinaux
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        # la cascade que `load_state` tire
        "scripts/python/engine/runner/snapshot.py",
    ),
    # Etage 1 : il LIT `GameAssembly.dll` (les octets du lambda differe), HORS de l'arbre.
    "build": True,
    "toujours": False,
    "raison": "Il grave que l'ECHEANCE et le RETRAIT EXPLICITE convergent sur UN corps natif "
              "(`RemoveEffectOperation$$Execute`), donc que les trois vecteurs de retrait sortent "
              "aussi sur la voie du TIMER. Le collapse inverse (`consumed = True` en direct) ne "
              "leve rien et n'est visible d'aucun test de duree.",
}

ROOT = Path(__file__).resolve().parents[4].parent          # racine du depot
COLS, ROWS = 7, 7
CARRIER, FOE = 10, 20

#: Le slot de `Core.Services.OperationProcessor` que le lambda differe appelle -- LU au
#: desassemblage (`mov ecx, 0x11`), et deja documente comme `RemoveEffectOperation$$Execute` par
#: l'en-tete de `engine/runner/operations/remove_effects.py`.
SLOT_REMOVE_EFFECT = 0x11
#: Le symbole du lambda que `RefreshEffect` enfile quand `ShouldBeRemoved` est vrai.
LAMBDA_REMOVE = ("IdunBattle.Operations.RefreshEffectsOperation.u003Cu003Ec__DisplayClass9_0$$"
                 "u003CRemoveEffectu003Eb__0")


# ============================================================================== etage 1 : le PE

# #10026-r1 -- CES HELPERS DELEGUENT AU FOYER (`pe_symboles`, #10028). Ils etaient RECOPIES dans
# TROIS fichiers, avec trois corps differents, et deux d'entre eux rendaient la PREMIERE VA portant
# le nom -- verts PAR CHANCE (leurs symboles n'ont qu'une VA sur ce build), pas par construction.
# Trois copies, c'est trois dates de peremption. Depuis, `va_du_symbole` REFUSE un nom partage.
#
# ⚠ CE SONT DES WRAPPERS, PAS DES LIAISONS. `_va_of = PE.va_du_symbole` gelerait la fonction a
# l'import (forme A) et NE MORDRAIT PAS sous `monkeypatch.setattr("pe_symboles.va_du_symbole", …)`.
# Un wrapper resout l'attribut A CHAQUE APPEL -- c'est la forme B que le CLAUDE.md prescrit.
def _build_hash():
    return PE.build_avec_dll()


def _va_of(build, symbole):
    return PE.va_du_symbole(build, symbole)


def _vas_of(build, symbole):
    return PE.vas_du_symbole(build, symbole)


def _read_at_va(dll, va, size):
    return PE.lire_a_la_va(dll, va, size)


def test_le_lambda_differe_de_l_echeance_appelle_le_SLOT_DE_RETRAIT():
    """ETAGE BINAIRE -- re-derive DU PE, jamais recopie.

    `RefreshEffectsOperation$$RefreshEffect`, sur `ShouldBeRemoved`, n'appelle PAS le retrait : il
    enfile une `System.Action` sur `<>c__DisplayClass9_0.<RemoveEffect>b__0`. C'est CE corps qui
    porte le retrait, et il tient en un appel : `processor.<slot 0x11>(effectEntity)`.

    Si un build futur deplacait ce slot, ou faisait de l'echeance un retrait BRUT (sans repasser par
    `RemoveEffectOperation$$Execute`), l'etage rougirait -- et le routage porte par cette tranche
    deviendrait a re-lire."""
    build = _build_hash()
    if build is None:
        pytest.skip("aucun build avec table `ghidra/functions.tsv` ET GameAssembly.dll installee")
    dll = PE.chemin_dll(build)                 # meme foyer que `_build_hash` (#10026-r1)
    va = _va_of(build, LAMBDA_REMOVE)
    assert va is not None, f"symbole absent de la table du build {build} : {LAMBDA_REMOVE}"
    blob = _read_at_va(dll, va, 0x60)
    assert blob, "lecture PE vide -- traduction VA -> offset a re-deriver"
    # `mov ecx, <slot>` = `B9 <imm32>`. Le corps n'en porte qu'UN, et c'est le slot de retrait.
    slots = [struct.unpack_from("<I", blob, i + 1)[0]
             for i in range(len(blob) - 5) if blob[i] == 0xB9]
    assert slots, "aucun `mov ecx, imm32` dans le corps du lambda -- forme d'appel a re-lire"
    assert slots[0] == SLOT_REMOVE_EFFECT, (
        f"le lambda differe de l'echeance appelle le slot {slots[0]:#x}, pas "
        f"{SLOT_REMOVE_EFFECT:#x} -- l'echeance ne converge plus sur "
        "`RemoveEffectOperation$$Execute`")


# ====================================================================== etages 2+ : le port

def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
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


def _pose(st, effect_type: int, name: str, duration: int) -> BaseEffect:
    """Une instance a TIMER sur le porteur, plus son NOM dans l'`EffectsOwnedComponent` (ce que fait
    `_register_name` a la pose)."""
    eff = BaseEffect(name=name, effect_type=int(effect_type), remaining_turns=int(duration),
                     target=CARRIER, active=True)
    st.effects.add_effect(CARRIER, eff)
    ent = st.get_entity(CARRIER)
    comp = ent.get_component(EffectsOwnedComponent)
    if comp is None:
        comp = EffectsOwnedComponent([])
        ent.add_component(comp)
    comp.effects.append(name)
    return eff


class _Espion:
    """Substitue les TROIS emetteurs du foyer et journalise leurs appels. On substitue le MODULE
    (`move_death`), pas le symbole importe : `remove_effects` le lie en forme B exactement pour
    que cette substitution morde."""

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

    def events(self) -> list:
        return [e for (e, _t, _x) in self.vus]


UNTARGETABLE = int(EffectType.FearOfTheUnseen_TeleportingIn)      # 1238


def test_le_domaine_du_3e_vecteur_porte_bien_l_effet_de_ce_montage():
    """CONTROLE DE NON-DEGENERESCENCE : si `1238` sortait de `UNTARGETABLE_EFFECT_TYPES`, l'etage
    suivant n'observerait plus que DEUX vecteurs et passerait pour un vert."""
    assert UNTARGETABLE == 1238
    assert UNTARGETABLE in {int(t) for t in AURA.UNTARGETABLE_EFFECT_TYPES}


def test_l_echeance_publie_les_TROIS_vecteurs(state, monkeypatch):
    """LE FIX. Un `1238 FearOfTheUnseen_TeleportingIn` a `remaining = 1` qui arrive a echeance au
    tick de fin de tour publie `On(0x3f)`, `On(0x40)` et `On(0x3b)` -- ce dernier sous son gate de
    TYPE -- exactement comme un retrait explicite."""
    _pose(state, UNTARGETABLE, "FearOfTheUnseen_TeleportingIn", duration=1)
    espion = _Espion(monkeypatch)
    retires = state.effects.on_turn_end(CARRIER, attacked=False, state=state)
    assert retires == [UNTARGETABLE]
    assert espion.events() == [int(EventTriggerType.PreEffectRemoved),
                               int(EventTriggerType.EffectRemoved),
                               int(EventTriggerType.UnitBecameTargetable)]
    assert all(t == CARRIER and x == UNTARGETABLE for (_e, t, x) in espion.vus)


def test_le_tick_NE_publie_PAS_avant_l_echeance(state, monkeypatch):
    """CONTRE-EPREUVE MORDANTE : le meme tick sur une instance a `remaining = 2` DECREMENTE (l'etat
    change, donc la mutation a bien mordu) et n'emet RIEN."""
    eff = _pose(state, UNTARGETABLE, "FearOfTheUnseen_TeleportingIn", duration=2)
    espion = _Espion(monkeypatch)
    retires = state.effects.on_turn_end(CARRIER, attacked=False, state=state)
    assert eff.remaining_turns == 1 and eff.consumed is False    # la mutation A mordu
    assert retires == [] and espion.vus == []


def test_un_effet_NON_untargetable_n_emet_que_les_DEUX_premiers(state, monkeypatch):
    """Le gate de TYPE du 3e vecteur est un GATE : un effet a timer hors
    `UNTARGETABLE_EFFECT_TYPES` publie `On(0x3f)` et `On(0x40)`, jamais `On(0x3b)`."""
    autre = int(EffectType.Stunned)
    assert autre not in {int(t) for t in AURA.UNTARGETABLE_EFFECT_TYPES}
    _pose(state, autre, "Stunned", duration=1)
    espion = _Espion(monkeypatch)
    state.effects.on_turn_end(CARRIER, attacked=False, state=state)
    assert espion.events() == [int(EventTriggerType.PreEffectRemoved),
                               int(EventTriggerType.EffectRemoved)]


def test_le_REPLI_sans_state_reste_le_comportement_anterieur(state, monkeypatch):
    """`state is None` = un `EffectsState` SANS `OperationProcessor` (la face DECISION). Il pose la
    marque et n'emet rien -- c'est la forme ANTERIEURE, conservee telle quelle et nommee."""
    eff = _pose(state, UNTARGETABLE, "FearOfTheUnseen_TeleportingIn", duration=1)
    espion = _Espion(monkeypatch)
    retires = state.effects.on_turn_end(CARRIER, attacked=False)
    assert eff.consumed is True and retires == [UNTARGETABLE]
    assert espion.vus == []


def test_l_echeance_DECOLLE_le_nom_de_l_EffectsOwnedComponent(state):
    """`RemoveEffectOperation$$Execute` retire l'id de `EffectsOwnedComponent.ActiveEffectIds` --
    cote port, `unregister_name`. Le collapse laissait le nom COLLE, et ce canal est LU par la
    couche DECISION : la fuite y etait observable."""
    _pose(state, UNTARGETABLE, "FearOfTheUnseen_TeleportingIn", duration=1)
    comp = state.get_entity(CARRIER).get_component(EffectsOwnedComponent)
    assert "FearOfTheUnseen_TeleportingIn" in comp.effects        # pose : le nom est la
    state.effects.on_turn_end(CARRIER, attacked=False, state=state)
    assert "FearOfTheUnseen_TeleportingIn" not in comp.effects


def test_le_REPLI_lui_laisse_le_nom_COLLE(state):
    """CONTRE-EPREUVE de l'etage precedent : sans `state`, le nom reste -- c'est bien le ROUTAGE qui
    le decolle, pas un effet de bord du montage."""
    _pose(state, UNTARGETABLE, "FearOfTheUnseen_TeleportingIn", duration=1)
    comp = state.get_entity(CARRIER).get_component(EffectsOwnedComponent)
    state.effects.on_turn_end(CARRIER, attacked=False)
    assert "FearOfTheUnseen_TeleportingIn" in comp.effects


def test_le_chemin_de_PRODUCTION_passe_state(state, monkeypatch):
    """LE CRAN QUI COMPTE : ce n'est pas `on_turn_end` qui doit savoir emettre, c'est
    `EndTurnOperation` qui doit lui passer `state`. Un appelant qui l'oublierait re-fabriquerait le
    collapse sans qu'aucun etage ci-dessus ne bouge."""
    _pose(state, UNTARGETABLE, "FearOfTheUnseen_TeleportingIn", duration=1)
    espion = _Espion(monkeypatch)
    TF.EndTurnOperation.execute(state, advance=False)
    assert espion.events() == [int(EventTriggerType.PreEffectRemoved),
                               int(EventTriggerType.EffectRemoved),
                               int(EventTriggerType.UnitBecameTargetable)]
