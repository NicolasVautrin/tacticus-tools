"""#462-r4b-r1-r1-r1-r1-c-r1 -- les effets de TUILE dans la collecte / le dispatch d'effet-triggers.

Le residu de la tranche `-c` accusait `collect_effect_triggers` d'etre << structurellement aveugle
aux effets de TUILE >>. Ce probe MESURE, et la mesure DEPLACE l'accusation :

  --step registre  : l'inventaire du registre `EFFECT_TRIGGERS` -- quelles classes declarent
                     `owner_is_tile` (`TileEffectTrigger`) et quelles classes sont des
                     `EffectTrigger` NUS. C'est le discriminant du gate, pas le collecteur.
  --step collecte  : `collect_effect_triggers` VOIT-IL un effet porte par une TUILE ? (mesure
                     directe sur un `State` monte a la main, sans runner)
  --step gate      : le trigger collecte SURVIT-IL au gate d'owner de `evaluate_trigger_operation` ?
                     C'est LA ou le trou vit.
  --step poses     : quels `effect_type` le port POSE-t-il sur une TUILE (balayage des sites), et
                     lesquels ont un trigger enregistre par une classe NON-Tile.

Sortie ASCII (console cp1252). Aucun runner, aucun RPC : 100 % offline.
"""
from __future__ import annotations

import argparse
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.runner.state import State                                    # noqa: E402
from engine.runner.operations.triggers.base import (EffectTrigger,       # noqa: E402
                                                    TileEffectTrigger, TriggerEvent)
from engine.runner.operations.triggers.dispatch import registry as REG   # noqa: E402
from engine.runner.operations.triggers.dispatch import core as CORE      # noqa: E402


def _classes_par_effet():
    """`{effect_type: [(nom, est_tile), ...]}` -- derive du registre, jamais recopie."""
    out = {}
    for et, classes in REG.EFFECT_TRIGGERS.items():
        out[int(et)] = [(c.__name__, issubclass(c, TileEffectTrigger)) for c in classes]
    return out


def step_registre() -> int:
    par_effet = _classes_par_effet()
    nus, tuiles = [], []
    for et in sorted(par_effet):
        for nom, est_tile in par_effet[et]:
            (tuiles if est_tile else nus).append((et, nom))
    print("[registre] EFFECT_TRIGGERS : %d effect_type, %d classes"
          % (len(par_effet), len(nus) + len(tuiles)))
    print("[registre] classes TileEffectTrigger (owner_is_tile=True) : %d" % len(tuiles))
    print("[registre] classes EffectTrigger NUES (gate d'owner applique) : %d" % len(nus))
    # Une MEME classe peut servir plusieurs effect_type (ex. BondRemoveOnBondedEntityDeath) : c'est
    # exactement le cas ou un attribut de CLASSE ne peut pas decrire la nature du porteur.
    multi = {}
    for et, nom in nus + tuiles:
        multi.setdefault(nom, []).append(et)
    partagees = {n: e for n, e in multi.items() if len(e) > 1}
    print("[registre] classes servant PLUSIEURS effect_type : %d" % len(partagees))
    for n in sorted(partagees):
        print("   %-46s -> %s" % (n, sorted(partagees[n])))
    return 0


def _state_avec_tuile(effect_type: int, tile_id: int = 900001, avec_board: bool = True):
    """`State` + BOARD d'une tuile + un effet porte par cette entite-TUILE.

    C'est le montage minimal du regime litigieux : `EffectsState.by_unit` est clee par id
    d'ENTITE (cf. `TileEffectTrigger` : << boardGraph t.id = entity id, disjoint des ids
    d'unite >>), donc une tuile y a sa place ; mais `state.get_entity(tile_id)` rend `None`.
    Le BOARD est ce qui rend la tuile RECONNAISSABLE (`board.by_id`) -- sans lui, un id
    introuvable reste un id introuvable, et c'est voulu."""
    from engine.entities.effects_state import EffectsState
    from engine.entities.effects import EffectFactory
    from engine.entities.pathfinding.board import Board
    st = State()
    st.effects = EffectsState()
    if avec_board:
        st.board = Board([{"id": tile_id, "col": 0, "row": 0, "walkable": True,
                           "elevation": 0, "neighbours": []}], adjacency="evenq")
    st.effects.add_effect(tile_id, EffectFactory.create(
        {"name": "ProbeTileEffect", "effectType": int(effect_type), "remaining": 0}, 100, None, None))
    return st, tile_id


def _un_effect_type_non_tile() -> int:
    """Un `effect_type` du registre dont TOUTES les classes sont des `EffectTrigger` nus.

    Derive du registre : si le port cablait un jour toutes ses classes en `TileEffectTrigger`, ce
    pas le DIRAIT (rc 2) au lieu de rendre un vert sans objet."""
    for et, classes in sorted(_classes_par_effet().items()):
        if classes and not any(t for _, t in classes):
            return et
    return -1


def step_collecte() -> int:
    et = _un_effect_type_non_tile()
    if et < 0:
        print("[collecte] AUCUN effect_type a classes exclusivement nues -- rien a mesurer")
        return 2
    st, tid = _state_avec_tuile(et)
    trigs = CORE.collect_effect_triggers(st)
    noms = sorted(type(t).__name__ for t in trigs)
    print("[collecte] effect_type %d porte par la TUILE %d" % (et, tid))
    print("[collecte] collect_effect_triggers rend %d trigger(s) : %s" % (len(trigs), noms))
    print("[collecte] owner_id du/des trigger(s) : %s" % sorted(int(t.owner_id) for t in trigs))
    print("[collecte] VERDICT : le collecteur %s les effets de tuile"
          % ("VOIT" if trigs else "N'INSTANCIE RIEN pour"))
    return 0 if trigs else 1


class _SondeTrigger(EffectTrigger):
    """Effet-trigger NU (pas `TileEffectTrigger`) qui NOTE s'il a ete evalue.

    Il ne modifie rien : son `matches` enregistre le passage et rend False. C'est le capteur du
    gate d'owner -- si `evaluate_trigger_operation` l'ecarte AVANT `matches`, le compteur reste a 0."""
    event_id = 2
    vus: list = []

    def matches(self, state, ev) -> bool:
        _SondeTrigger.vus.append(int(self.owner_id))
        return False

    def execute_behaviour(self, state, ev):
        return None


def _mesure_gate(et: int, avec_board: bool) -> list:
    st, tid = _state_avec_tuile(et, avec_board=avec_board)
    sauf = REG.EFFECT_TRIGGERS.get(et)
    _SondeTrigger.vus = []
    try:
        REG.EFFECT_TRIGGERS[et] = [_SondeTrigger]                 # MUTATION du dict partage
        CORE.evaluate_trigger_operation(st, TriggerEvent(2, tid, tid, ranged=False, profile=None))
    finally:
        if sauf is None:
            REG.EFFECT_TRIGGERS.pop(et, None)
        else:
            REG.EFFECT_TRIGGERS[et] = sauf
    return list(_SondeTrigger.vus)


def step_gate() -> int:
    et = _un_effect_type_non_tile()
    if et < 0:
        print("[gate] AUCUN effect_type a classes exclusivement nues -- rien a mesurer")
        return 2
    avec = _mesure_gate(et, avec_board=True)
    sans = _mesure_gate(et, avec_board=False)
    print("[gate] effect_type %d porte par une TUILE, trigger NU (pas TileEffectTrigger) inscrit" % et)
    print("[gate] AVEC board (la tuile est reconnaissable)  : `matches` appele %d fois" % len(avec))
    print("[gate] SANS board (l'id reste introuvable)       : `matches` appele %d fois" % len(sans))
    print("[gate] VERDICT : le gate d'owner %s le trigger d'un porteur TUILE"
          % ("LAISSE PASSER" if avec else "JETTE"))
    # Le second bras est le CONTROLE : il doit rester a 0. S'il passait, le correctif aurait
    # supprime le gate au lieu de le rendre dependant de la NATURE du porteur.
    if sans:
        print("[gate] CONTROLE ROUGE : un owner introuvable SANS board passe -- gate supprime, "
              "pas conditionne")
        return 2
    return 0 if avec else 1


# Sites du port qui POSENT un effet sur une TUILE. Deux formes, toutes deux balayees par AST :
#   * imperative : `AddEffectOperation.execute(..., target=<expr contenant 'tile'/'tid'>)`
#   * declarative : noeud DSL `AddEffect(<ET>, <nom>, Tiles(...), ...)`
# Le balayage rend les SITES ; la classification effect_type <- constante est faite par le lecteur.
def step_poses() -> int:
    racine = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine")
    sites = []
    for base, _dirs, fichiers in os.walk(racine):
        for f in fichiers:
            if not f.endswith(".py"):
                continue
            chemin = os.path.join(base, f)
            try:
                arbre = ast.parse(open(chemin, encoding="utf-8").read())
            except SyntaxError:
                continue
            for n in ast.walk(arbre):
                if not isinstance(n, ast.Call):
                    continue
                nom = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
                if nom == "AddEffect":
                    # noeud DSL : cible = 3e positionnel (ou `targets=`)
                    args = list(n.args) + [k.value for k in n.keywords]
                    if any(isinstance(a, ast.Call)
                           and (getattr(a.func, "id", None) == "Tiles"
                                or getattr(a.func, "attr", None) == "Tiles") for a in args):
                        sites.append((chemin, n.lineno, "DSL AddEffect(..., Tiles(...))",
                                      ast.unparse(n.args[0]) if n.args else "?"))
                elif nom == "execute" and getattr(getattr(n.func, "value", None), "id",
                                                  None) == "AddEffectOperation":
                    cible = None
                    for k in n.keywords:
                        if k.arg == "target":
                            cible = ast.unparse(k.value)
                    if cible is None and len(n.args) >= 3:
                        cible = ast.unparse(n.args[2])
                    if cible and ("tile" in cible.lower() or cible in ("tid", "nid")):
                        et_txt = None
                        for k in n.keywords:
                            if k.arg == "effect_type":
                                et_txt = ast.unparse(k.value)
                        if et_txt is None and len(n.args) >= 4:
                            et_txt = ast.unparse(n.args[3])
                        sites.append((chemin, n.lineno,
                                      "imperatif target=%s" % cible, et_txt or "?"))
    rel = os.path.dirname(os.path.abspath(__file__))
    print("[poses] %d site(s) de pose sur TUILE" % len(sites))
    for chemin, ligne, forme, et_txt in sorted(sites):
        print("   %-56s:%-5d %-34s effect_type=%s"
              % (os.path.relpath(chemin, rel).replace("\\", "/"), ligne, forme, et_txt))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--step", required=True,
                   choices=["registre", "collecte", "gate", "poses"])
    a = p.parse_args()
    return {"registre": step_registre, "collecte": step_collecte,
            "gate": step_gate, "poses": step_poses}[a.step]()


if __name__ == "__main__":
    raise SystemExit(main())
