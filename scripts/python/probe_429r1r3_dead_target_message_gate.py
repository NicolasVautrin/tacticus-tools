"""#429-r1-r3 -- LA DERNIERE DIVERGENCE DU GATE CIBLE-MORTE : `GreatFrostAxe` (1089).

CE QUE CE PROBE MESURE, ET POURQUOI L'OBSERVABLE N'EST PAS CELUI DE #429-r1
--------------------------------------------------------------------------
1089 est l'unique porteur du bit 38 `AllowDeadTarget` : il ECHAPPE, CORRECTEMENT, au gate
d'OPERATION `IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility`
(#429-r1). Le natif le refuse quand meme -- mais un CRAN PLUS HAUT, au rang du MESSAGE :

    IdunBattle.Messages.InputMessageProcessor$$Visit(ActiveAbilityMessage)
        caster = state.GetEntity(message.CasterId@0x10)
        target = state.GetEntity(message.TargetId@0x14)
        if (!UnitExtensions.IsAliveAndNotFled(caster) || !IsAliveAndNotFled(target)) return;
        RunPhase(6, () => { OpenGroup(0xc User_UseAbility); OperationProcessor.ActiveAbility(...) })

Ce gate NE LIT NI l'ability NI ses `TargetingOptions` : aucune derogation possible, donc 1089 y
tombe comme les 103 autres.

⚠ LES TIRAGES RNG NE DISCRIMINENT RIEN POUR 1089, et c'est le piege de cette tranche : son arbre
est `op_and(AddEffect(Ice), If(IsAlive(target), attaque))` -- sur un cadavre la garde `IsAlive`
eteint deja l'attaque, donc **0 tirage des DEUX cotes**, gate ou pas. L'observable qui mord est la
GLACE (le port en posait 6 tuiles) et les FLAGS DE TOUR (le port consommait le tour du caster).

VOLETS
------
  `signature` (LIVE) -- L'ATTRIBUTION D'ETAGE. Le compte d'EVENEMENTS DE STREAM separe les deux
        rangs, parce que le groupe `User_UseAbility` est ouvert par la lambda du Visit, donc APRES
        son gate et AVANT l'operation. Bras temoin OBLIGATOIRE : un refus au rang de l'OPERATION
        (cast hors portee sur une cible VIVANTE) OUVRE le groupe. Sans lui, « 0 evenement » ne
        prouverait rien.
  `port`      (LIVE) -- natif vs port sur le meme etat, avec CONTRE-EPREUVE : le meme cast avec
        `engine.runner.components.is_alive_and_not_fled` neutralise (le FOYER reel, resolu a chaque
        appel par l'import paresseux du handler -- pas un nom recopie dans le probe).
  `offline`         -- `is_alive_and_not_fled` sur les quatre entrees qui le separent d'`unit_is_dead`.

USAGE (ASCII only)
------------------
    python scripts/python/probe_429r1r3_dead_target_message_gate.py --volet offline
    python scripts/python/probe_429r1r3_dead_target_message_gate.py --volet signature --state-file <ABSOLU>
    python scripts/python/probe_429r1r3_dead_target_message_gate.py --volet port --state-file <ABSOLU>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sibling_script import sibling_script  # noqa: E402

HOST = "http://127.0.0.1:8765"
# `spaceWulfen` porte `GreatFrostAxe` (1089), l'UNIQUE porteur du bit 38 -- c'est lui qui caste sur
# le cadavre. `ultraInceptorSgt` TUE (il est adjacent a la victime, pas au caster).
P_UNITS = "spaceWulfen,ultraInceptorSgt"
# DEUX ennemis : tuer l'unique adversaire TERMINE la bataille et les vues cessent de publier le
# cadavre (mesure #429-r1). Le second sert AUSSI de bras temoin HORS PORTEE.
A_UNITS = "tyranWingedPrime,tauDarkstrider"
PLACES = ("--place", "spaceWulfen:3,3", "--place", "ultraInceptorSgt:1,3",
          "--a-place", "tyranWingedPrime:2,3", "--a-place", "tauDarkstrider:2,5")
ABILITY_GREAT_FROST_AXE = 1089        # IdunBattle.Entities.Enum.ActiveAbilityType.GreatFrostAxe
ABILITY_DEATH_FROM_ABOVE = 1003       # IdunBattle.Entities.Enum.ActiveAbilityType.DeathFromAbove
STREAM_GROUP_USER_USE_ABILITY = 0xc   # le groupe ouvert par la lambda de `Visit`


def sid() -> int:
    return int(requests.get("%s/api/admin/status" % HOST, timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    r = requests.post("%s/api/scripts/%d/rpc" % (HOST, s),
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def build(state_file: str, seed: str, board: str) -> dict:
    out = subprocess.run([sys.executable, sibling_script("rl_duel.py"), "build",
                          "--seed", seed, "--board", board, "--state-file", state_file,
                          "--p-units", P_UNITS, "--a-units", A_UNITS, "--hp-target", "1",
                          *PLACES], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("BUILD rc=%d\n%s\n%s" % (out.returncode, out.stdout[-1200:],
                                                    out.stderr[-1200:]))
    return json.loads(Path(state_file).read_text(encoding="utf-8"))


def _ids(dv):
    return {u.get("visualId"): u.get("id") for u in (dv.get("units") or [])}


def _normal_id(dv, uid):
    for u in (dv.get("units") or []):
        if u.get("id") == uid:
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal":
                    return ab.get("id")
    return None


def _shot(s, rid, action):
    """UN `applyAction`, reduit a ce qui separe les deux rangs de refus."""
    s0 = rpc(s, "dumpRng", {"runnerId": rid}, 30)
    r = rpc(s, "applyAction", {"runnerId": rid, "action": action}, 40)
    s1 = rpc(s, "dumpRng", {"runnerId": rid}, 30)
    a, b = (s0 or {}).get("mti"), (s1 or {}).get("mti")
    act = ((r or {}).get("actions") or [{}])[0]
    evs = act.get("events") or []
    return {"events": act.get("eventCount"), "mutated": act.get("mutated"),
            "action_consumed": act.get("actionConsumed"),
            "draws": (b - a + (624 if b < a else 0)) if None not in (a, b) else None,
            "groups": [e.get("group") for e in evs if e.get("kind") == "group"]}


# ------------------------------------------------------------------------------------------
def volet_offline() -> int:
    """OFFLINE PUR : les quatre entrees qui separent `is_alive_and_not_fled` d'`unit_is_dead`."""
    from engine.runner.components import (HealthComponent, UnitFlagsComponent,
                                          is_alive_and_not_fled, unit_is_dead)
    from engine.runner.state import Entity

    def ent(hp=None, fled=False):
        """Ni l'un ni l'autre predicat ne lit le `UnitComponent` : on ne monte que ce qu'ils LISENT
        (`HealthComponent` pour la mort, `UnitFlagsComponent` pour le flag 9)."""
        e = Entity(1)
        if hp is not None:
            e.add_component(HealthComponent(hp, 100))
        e.add_component(UnitFlagsComponent([UnitFlagsComponent.FLED] if fled else None))
        return e

    cas = [("None (entite non resolue)", None),
           ("unite VIVANTE  (hp=10)", ent(hp=10)),
           ("unite MORTE    (hp=0)", ent(hp=0)),
           ("unite FLED     (hp=0, flag 9)", ent(hp=0, fled=True)),
           ("unite FLED     (hp=10, flag 9)", ent(hp=10, fled=True)),
           ("entite SANS HealthComponent", ent(hp=None))]
    print("%-32s %-22s %s" % ("entree", "is_alive_and_not_fled", "unit_is_dead"))
    for nom, e in cas:
        print("%-32s %-22s %s" % (nom, is_alive_and_not_fled(e), unit_is_dead(e)))
    print("")
    print("Les deux ne sont PAS complementaires : une unite FLED est refusee par le gate de")
    print("MESSAGE (IsAliveAndNotFled=False) alors qu'`IsDead` l'exclut EXPRESSEMENT de la mort.")
    return 0


def scenario_signature(state_file: str, seed: str = "777", board: str = "MC1_67",
                       verbose: bool = True) -> dict:
    """L'ATTRIBUTION D'ETAGE, en LIVE. Quatre bras sur le MEME montage, dont un TEMOIN dont le
    refus est connu pour venir de l'OPERATION (hors portee) -- c'est lui qui rend « 0 evenement »
    interpretable.

    `why` non vide = montage NON INSTALLE (jamais un skip vert)."""
    st_json = build(state_file, seed, board)
    s, rid = sid(), int(st_json["runnerId"])
    res: dict = {"rid": rid}
    try:
        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ids = _ids(dv)
        wulfen, sgt = ids.get("spaceWulfen"), ids.get("ultraInceptorSgt")
        prime, dark = ids.get("tyranWingedPrime"), ids.get("tauDarkstrider")
        if None in (wulfen, sgt, prime, dark):
            return {"why": "roster incomplet : %s" % sorted(ids)}
        nid = _normal_id(dv, sgt)
        nid_w = _normal_id(dv, wulfen)
        if nid is None or nid_w is None:
            return {"why": "attaque normale introuvable (sgt=%s wulfen=%s)" % (nid, nid_w)}
        # --- BRAS TEMOINS, cible VIVANTE : ils doivent OUVRIR le groupe `User_UseAbility` --------
        res["vivant_hors_portee"] = _shot(s, rid, {
            "kind": "ability", "casterId": wulfen, "targetId": dark,
            "abilityType": ABILITY_GREAT_FROST_AXE})
        # --- on TUE la cible ------------------------------------------------------------------
        rpc(s, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": sgt, "targetId": prime, "abilityType": nid}}, 40)
        dv1 = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        cible = next((u for u in (dv1.get("units") or []) if u.get("id") == prime), {})
        res["cadavre_alive"] = cible.get("alive")
        res["cadavre_hp"] = cible.get("hp")
        res["cadavre_pos"] = cible.get("pos")
        if cible.get("alive") or cible.get("pos") is None:
            return {"why": "la cible n'est pas un cadavre POSITIONNE -- montage non installe", **res}
        # --- BRAS CADAVRE : le gate de MESSAGE, qui n'ouvre AUCUN groupe -----------------------
        res["cadavre_1089"] = _shot(s, rid, {
            "kind": "ability", "casterId": wulfen, "targetId": prime,
            "abilityType": ABILITY_GREAT_FROST_AXE})
        res["cadavre_normale"] = _shot(s, rid, {
            "kind": "ability", "casterId": wulfen, "targetId": prime, "abilityType": nid_w})
        # --- BRAS TUILE : `IsAliveAndNotFled` rend VRAI sur une entite sans HealthComponent ----
        res["cadavre_tuile_1089"] = _shot(s, rid, {
            "kind": "ability", "casterId": wulfen, "abilityType": ABILITY_GREAT_FROST_AXE,
            "to": {"col": int(cible["pos"]["col"]), "row": int(cible["pos"]["row"])}})
        res["cadavre_1003"] = _shot(s, rid, {
            "kind": "ability", "casterId": sgt, "targetId": prime,
            "abilityType": ABILITY_DEATH_FROM_ABOVE})
        res["why"] = ""
    finally:
        try:
            rpc(s, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:                                          # noqa: BLE001
            pass
    if verbose:
        for k in ("vivant_hors_portee", "cadavre_1089", "cadavre_normale", "cadavre_tuile_1089",
                  "cadavre_1003"):
            print("  %-20s %s" % (k, res.get(k)))
    return res


def scenario_port(state_file: str, seed: str = "777", board: str = "MC1_67",
                  verbose: bool = True) -> dict:
    """NATIF vs PORT sur le MEME etat, plus la CONTRE-EPREUVE (gate neutralise au FOYER).

    Observable = la GLACE et les FLAGS de tour, PAS les tirages (cf. l'en-tete)."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.entities.pathfinding.board import Board

    st_json = build(state_file, seed, board)
    s, rid = sid(), int(st_json["runnerId"])
    res: dict = {"rid": rid}
    try:
        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ids = _ids(dv)
        wulfen, sgt, prime = ids.get("spaceWulfen"), ids.get("ultraInceptorSgt"), \
            ids.get("tyranWingedPrime")
        if None in (wulfen, sgt, prime):
            return {"why": "roster incomplet : %s" % sorted(ids)}
        nid = _normal_id(dv, sgt)
        if nid is None:
            return {"why": "attaque normale de ultraInceptorSgt introuvable"}
        rpc(s, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": sgt, "targetId": prime, "abilityType": nid}}, 40)
        ob0 = rpc(s, "observeBattle", {"runnerId": rid}, 40)
        dv1 = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        cible = next((u for u in (dv1.get("units") or []) if u.get("id") == prime), {})
        res["cadavre_alive"] = cible.get("alive")
        res["cadavre_pos"] = cible.get("pos")
        if cible.get("alive") or cible.get("pos") is None:
            return {"why": "la cible n'est pas un cadavre POSITIONNE -- montage non installe", **res}
        snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 40)
        bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
        s0 = rpc(s, "dumpRng", {"runnerId": rid}, 30)
        # --- NATIF ---------------------------------------------------------------------------
        res["natif"] = _shot(s, rid, {"kind": "ability", "casterId": wulfen, "targetId": prime,
                                      "abilityType": ABILITY_GREAT_FROST_AXE})
        dv2 = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        res["natif_caster_has_action"] = next(
            (u.get("hasAction") for u in (dv2.get("units") or []) if u.get("id") == wulfen), None)

        def _monter():
            st = load_state(dv1, ob0, snap)
            if isinstance(bg, dict) and "tiles" in bg:
                st.board = Board(bg["tiles"], adjacency="native_sym")
            if isinstance(s0, dict) and s0.get("mt"):
                rng = IntBasedMersenneTwister()
                rng.mt = list(s0["mt"])
                rng.mti = s0["mti"]
                st.rng = rng
            return st

        def _caster(st):
            runner = Runner(st).install_default_handlers(20)
            runner.apply(ActiveAbilityMessage(wulfen, prime, ABILITY_GREAT_FROST_AXE))
            return runner.ability_handler.last

        # --- PORT ----------------------------------------------------------------------------
        st = _monter()
        last = _caster(st) or {}
        res["port_last"] = last
        res["port_iced"] = len(last.get("iced_tiles") or [])
        res["port_flags"] = bool(last.get("flags"))
        res["port_gate_role"] = last.get("not_alive_and_not_fled")
        # --- CONTRE-EPREUVE : le FOYER neutralise (import paresseux -> la substitution MORD) ----
        import engine.runner.components as C                        # noqa: PLC0415
        garde = C.is_alive_and_not_fled
        C.is_alive_and_not_fled = lambda *_a, **_k: True
        try:
            sans = _caster(_monter()) or {}
        finally:
            C.is_alive_and_not_fled = garde
        res["port_sans_gate_last"] = sans
        res["port_sans_gate_iced"] = len(sans.get("iced_tiles") or [])
        res["port_sans_gate_flags"] = bool(sans.get("flags"))
        res["why"] = ""
    finally:
        try:
            rpc(s, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:                                          # noqa: BLE001
            pass
    if verbose:
        for k in sorted(res):
            if k not in ("port_last", "port_sans_gate_last"):
                print("  %-26s %s" % (k, res[k]))
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--volet", choices=("offline", "signature", "port"), default="offline")
    ap.add_argument("--state-file", default=None, help="chemin ABSOLU, hors data/")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()
    if a.volet == "offline":
        return volet_offline()
    if not a.state_file:
        print("--state-file (ABSOLU) requis pour ce volet")
        return 2
    fn = scenario_signature if a.volet == "signature" else scenario_port
    r = fn(a.state_file, a.seed, a.board)
    if r.get("why"):
        print("MONTAGE NON INSTALLE : %s" % r["why"])
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
