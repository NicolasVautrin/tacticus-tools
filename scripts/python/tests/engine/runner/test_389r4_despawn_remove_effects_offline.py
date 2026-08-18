"""GARDE #389-r4 (OFFLINE PURE) -- le DESPAWN retire les effets PAR LE FOYER, pas par une marque.

## L'ecart, et pourquoi il restait

`IdunBattle.Operations.RemoveUnitOperation$$RemoveEffects` n'a AUCUNE xref CODE (deux entrees DATA
de tables de methodes) : son appel reel est **INLINE** dans
`IdunBattle.Operations.RemoveUnitOperation$$Execute`, sous `if (removeEffects != 0)`. Son corps est
LU, et il tient en deux ecritures avant l'appel du slot 0x5a :

    local_18 = 0     ->  `Nullable<KillUnitStep>` SANS valeur  ->  AUCUN filtre par step
    local_10 = 0     ->  `options.<+0x08>` = 0                 ->  gate `KeepOnRevive` NON arme

⇒ il retire TOUT l'inventaire du porteur en passant par `RemoveEffectOperation$$Execute`, donc avec
revert des modifications, retrait RECURSIF des sous-effets, decollage du NOM et publication de
`On(0x3f)` / `On(0x40)`. Le port posait `consumed = True` en direct.

#389-r2 avait laisse cet ecart NOMME pour borner son rayon -- pas parce que le natif s'en
dispensait.

## Le regime est ATTEIGNABLE, et la fiche exigeait de l'etablir AVANT de brancher

`remove_effects=True` a DEUX call-sites de production : la feuille DSL `RemoveUnit`
(`abilities/behaviours/lifecycle.py`) et l'eviction MV71 (`abilities/loki/mv71.py`). La voie MORT,
elle, passe `False` -- `KillUnitOperation$$Execute` appelle le slot 6 avec `removeEffects: 0`, la
sequence de mort etant servie par les TROIS `KillUnitOperation$$RemoveEffects` qui l'entourent.
Ce raccord ne touche donc PAS la mort, et l'etage 2 ci-dessous le grave.

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
from engine.entities.effects.base import BaseEffect, SubEffectSpec         # noqa: E402
from engine.entities.effects_state import EffectsState                     # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.components import EffectsOwnedComponent                 # noqa: E402
import engine.runner.operations.remove_effects as REM                      # noqa: E402
import engine.runner.operations.remove_unit as RU                          # noqa: E402
from engine.runner.operations.triggers.dispatch import move_death as MD    # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/remove_unit.py",
        "scripts/python/engine/runner/operations/remove_effects.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/runner/snapshot.py",
    ),
    "build": False,
    "toujours": False,
    "raison": ("100 % offline : la lecture du corps natif (slot 0x5a, `local_18 = 0`, "
               "`local_10 = 0`) est gravee par la table des sept producteurs de "
               "`test_547r13_cadavre_sans_effet_offline` ; ce fichier mesure le PORT."),
}

COLS, ROWS = 7, 7
PORTEUR, AUTRUI = 10, 20
ET_SIMPLE, ET_GARDE, ET_PARENT, ET_ENFANT = 8801, 8802, 8803, 8804


class _CompositeSurAutrui(BaseEffect):
    """Parent dont le sous-effet vit sur l'entite BONDEE -- le regime que la fiche demandait de
    mesurer (<< une unite despawnee dont un effet portait un stat-mod sur AUTRUI >>).

    Patron natif : `IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect$$ApplyInternal` pose trois
    de ses quatre enfants sur l'entite bondee."""

    def sub_effects_on_apply(self) -> list:
        return [SubEffectSpec(ET_ENFANT, "EnfantSurAutrui", on_bonded_entity=True)]


def _state():
    import hexgeo
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [c * ROWS + r + 1 for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": col * ROWS + row + 1, "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    decision = {"currentPlayer": 1, "units": [
        {"id": PORTEUR, "visualId": "orksNob", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 1}, "effects": []},
        {"id": AUTRUI, "visualId": "ultraTitus", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 3, "row": 3}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    st = load_state(decision, observe, board=Board(tiles, adjacency="evenq"))
    if st.effects is None:
        st.effects = EffectsState()
    return st


def _pose(st, uid, effect_type, name, *, cls=BaseEffect, keep=None, bonded=None):
    eff = cls(name=name, effect_type=int(effect_type), target=int(uid), active=True)
    if keep is not None:
        eff.keep_on_revive = keep
    if bonded is not None:
        eff.bonded = int(bonded)
    st.effects.add_effect(int(uid), eff)
    ent = st.get_entity(int(uid))
    comp = ent.get_component(EffectsOwnedComponent)
    if comp is None:
        comp = EffectsOwnedComponent([])
        ent.add_component(comp)
    comp.effects.append(name)
    return eff


def _noms(st, uid) -> list:
    comp = st.get_entity(int(uid)).get_component(EffectsOwnedComponent)
    return sorted(comp.effects) if comp is not None else []


class _Espion:
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


# ---------------------------------------------------- etage 1 : LE FIX (foyer + vecteurs + noms)

def test_le_despawn_retire_PAR_LE_FOYER(monkeypatch):
    """`removeEffects = 1` -> le slot 0x5a, donc `RemoveEffectOperation$$Execute` par effet : les
    deux vecteurs sortent ET le nom est decolle. Le port posait une marque muette."""
    st = _state()
    _pose(st, PORTEUR, ET_SIMPLE, "EffetSimple")
    espion = _Espion(monkeypatch)
    out = RU.RemoveUnitOperation.execute(st, PORTEUR, remove_effects=True)

    assert out is not None and out["effects_consumed"] == [ET_SIMPLE], out
    assert espion.pour(ET_SIMPLE) == [int(EventTriggerType.PreEffectRemoved),
                                      int(EventTriggerType.EffectRemoved)], espion.vus
    assert "EffetSimple" not in _noms(st, PORTEUR), (
        "le NOM reste colle a l'`EffectsOwnedComponent` -- canal LU par la couche decision : %s"
        % _noms(st, PORTEUR))


def test_le_despawn_retire_AUSSI_le_sous_effet_pose_sur_AUTRUI(monkeypatch):
    """LE REGIME QUE LA FICHE EXIGEAIT DE MESURER avant de brancher.

    `RemoveEffectOperation$$Execute` appelle `RemoveSubEffects`, qui retire les enfants
    RECURSIVEMENT -- et la liste native `SubEffects@+0x78` porte des ids d'ENTITE-EFFET, sans notion
    de porteur : un enfant peut vivre sur une AUTRE unite. Une marque posee sur le seul inventaire
    du despawne ne pouvait structurellement pas l'atteindre."""
    st = _state()
    parent = _pose(st, PORTEUR, ET_PARENT, "ParentComposite",
                   cls=_CompositeSurAutrui, bonded=AUTRUI)
    enfant = _pose(st, AUTRUI, ET_ENFANT, "EnfantSurAutrui")
    enfant.parent_type = ET_PARENT
    assert parent.sub_effects_on_apply(), "montage : le parent doit DECLARER un sous-effet"

    espion = _Espion(monkeypatch)
    RU.RemoveUnitOperation.execute(st, PORTEUR, remove_effects=True)

    assert parent.consumed, "le parent n'a pas ete retire"
    assert enfant.consumed, (
        "le sous-effet pose sur AUTRUI a SURVECU au despawn de son porteur -- c'est exactement "
        "l'ecart que la marque en direct ne pouvait pas voir")
    assert espion.pour(ET_ENFANT) == [int(EventTriggerType.PreEffectRemoved),
                                      int(EventTriggerType.EffectRemoved)], espion.vus
    assert "EnfantSurAutrui" not in _noms(st, AUTRUI), _noms(st, AUTRUI)


# ------------------------------------------- etage 2 : LA VOIE MORT N'EST PAS TOUCHEE

def test_remove_effects_False_ne_retire_RIEN(monkeypatch):
    """`KillUnitOperation$$Execute` appelle le slot 6 avec `removeEffects: 0`, et c'est
    LOAD-BEARING : la sequence de mort retire les effets EN TROIS TEMPS autour de ce retrait, par
    `KillUnitOperation$$RemoveEffects(killed, step)`. Si le despawn en consommait au passage, les
    steps `AfterUnitRemove` / `AfterDeathTrigger` trouveraient un inventaire deja vide et les
    triggers qui LISENT un effet du mourant (cf. #911-r1) redeviendraient impossibles."""
    st = _state()
    eff = _pose(st, PORTEUR, ET_SIMPLE, "EffetSimple")
    espion = _Espion(monkeypatch)
    out = RU.RemoveUnitOperation.execute(st, PORTEUR, remove_effects=False)
    assert out is not None and out["effects_consumed"] == []
    assert not eff.consumed, "la voie MORT a consomme un effet"
    assert espion.vus == []
    assert "EffetSimple" in _noms(st, PORTEUR)


# ------------------------------------------- etage 3 : LE GATE `KeepOnRevive` N'EST PAS ARME

def test_le_gate_KeepOnRevive_n_est_PAS_arme_au_despawn(monkeypatch):
    """`local_10 = 0` : des SEPT `$$RemoveEffects` du binaire, seul `ReviveUnitOperation` arme ce
    gate (#547-r13). Un effet a `keep_on_revive = True` doit donc partir au despawn.

    TEMOIN NON DEGENERE : deux effets, l'un declarant le flag, l'autre non -- les DEUX partent."""
    st = _state()
    garde = _pose(st, PORTEUR, ET_GARDE, "GardeAuRevive", keep=True)
    nu = _pose(st, PORTEUR, ET_SIMPLE, "EffetSimple")
    RU.RemoveUnitOperation.execute(st, PORTEUR, remove_effects=True)
    assert garde.consumed and nu.consumed, (
        "un effet a `keep_on_revive = True` a survecu au DESPAWN : le gate a ete arme a tort")


# --------------------------------------------------------------- etage 4 : LE RANG NATIF

def test_On_UnitRemoved_part_AVANT_le_retrait_des_effets(monkeypatch):
    """Etape 13 PUIS etape 14. C'est load-bearing : les consommateurs d'`On(0x25 = UnitRemoved)`
    doivent voir l'unite retiree PORTANT ENCORE ses effets.

    On observe l'inventaire DEPUIS le vecteur `On(0x25)` : si le retrait passait avant, il serait
    deja vide."""
    st = _state()
    _pose(st, PORTEUR, ET_SIMPLE, "EffetSimple")
    vu = {}

    def espion_removed(state, unit_id, *a, **k):
        vu["restants"] = [int(e.effect_type)
                          for e in state.effects.by_unit.get(int(unit_id), []) if not e.consumed]
        return []

    monkeypatch.setattr(MD, "unit_removed_triggers", espion_removed)
    RU.RemoveUnitOperation.execute(st, PORTEUR, remove_effects=True)
    assert vu.get("restants") == [ET_SIMPLE], (
        "au moment d'`On(0x25)`, l'unite ne porte plus ses effets : le retrait a ete avance : %s"
        % vu)


# ------------------------------------------------- etage 5 : IDEMPOTENCE ET GATE ANTI-DOUBLE

def test_un_second_despawn_ne_republie_rien(monkeypatch):
    """Le gate `Removed` (0x1a) refuse le second retrait : aucune re-publication, aucun re-revert."""
    st = _state()
    _pose(st, PORTEUR, ET_SIMPLE, "EffetSimple")
    RU.RemoveUnitOperation.execute(st, PORTEUR, remove_effects=True)
    espion = _Espion(monkeypatch)
    again = RU.RemoveUnitOperation.execute(st, PORTEUR, remove_effects=True)
    assert again is None, "le gate anti-double-retrait n'a pas refuse"
    assert espion.vus == []


def test_le_foyer_est_bien_CELUI_du_module_partage(monkeypatch):
    """Le raccord doit passer par `remove_effects.remove_effects_operation` -- pas par une seconde
    implementation locale. On SUBSTITUE le foyer sur le MODULE (forme B) et on exige qu'il soit
    appele avec les DEUX options LUES au decompile.

    Sans ce cran, une re-implementation qui poserait les memes marques rendrait tous les etages
    precedents verts."""
    st = _state()
    _pose(st, PORTEUR, ET_SIMPLE, "EffetSimple")
    vus = []

    def faux(state, owner_id, *, step=None, keep_on_revive_gate=False):
        vus.append((int(owner_id), step, keep_on_revive_gate))
        return []

    monkeypatch.setattr(REM, "remove_effects_operation", faux)
    RU.RemoveUnitOperation.execute(st, PORTEUR, remove_effects=True)
    assert vus == [(PORTEUR, None, False)], (
        "le despawn n'appelle pas le foyer partage avec les options lues "
        "(`step` SANS valeur, gate NON arme) : %s" % vus)
