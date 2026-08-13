"""#982-r5 / #966-r3 -- `decisionView` publie-t-il `1212 HealingBalms_Heal` sur Baldr, et PAS `18` ?

## La question binaire

Le §SWAP de `engine/runner/abilities/loki/healing_balms.py` affirme que le port n'a AUCUNE entree
de registre pour `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HealingBalmsAbility$$CreateBehaviour`
(`AddFlag(0x17) + RemoveActiveAbility(0x12 = Heal) + AddActiveAbility(0x4bc = 1212)`) parce que
**le substrat le livre DEJA fait** : le runner natif joue `AbilityInit` au spawn, donc `decisionView`
publierait sur `spaceWolfPriest` l'active `1212` et PAS `18`.

C'est la PREMISSE la plus chargee du dossier et elle n'a jamais ete tranchee -- si elle est fausse,
c'est tout le §SWAP qui tombe, et le port devrait poser le swap lui-meme.

## Ce que ce probe mesure, et ce qu'il refuse de conclure

  1. `combatSnapshot.units[].unitFlags` sur Baldr : le flag `23 CanHealFullHealthUnits` est-il POSE
     par le natif au spawn ? (etage deja mesure par #982-r5, re-joue ici comme temoin d'armement)
  2. `decisionView.units[<Baldr>].abilities` : contient-il `1212` ? contient-il `18` ?
  3. Le PORT, sur le meme etat recharge : `state.get_entity(baldr)` porte-t-il le flag, et le
     `UnitContext.active_abilities` porte-t-il `1212` ?

⚠ PIEGE D'APPARIEMENT, paye en mesure (#982-r5) : `combatSnapshot.units[].entityId` est le
`squadId` d'`observeBattle`, PAS son `entityId`. Un lecteur qui apparie par `observeBattle.entityId`
lit `flags = None` sur TOUTES les unites et conclut faussement que rien n'est seede. Ce probe
apparie par `visualId`, qui est le seul identifiant commun aux trois canaux.

Usage :
    python probe_982r5_swap_decisionview.py --state-file <ABSOLU>.json [--runner N]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

BOARD = "MC1_67"
SEED = "777"
PORTEUR = "spaceWolfPriest"           # Baldr -- SEUL porteur du passif `HealingBalms` (1502)
ALLIE = "ultraCalgar"                 # la cible de soin (a PV PLEINS au spawn)
HEAL_GENERIQUE = 18                   # `ActiveAbilityType.Heal` -- ce que le SWAP doit RETIRER
HEALING_BALMS_HEAL = 1212             # `ActiveAbilityType.HealingBalms_Heal` -- ce qu'il AJOUTE
FLAG_CAN_HEAL_FULL = 23               # `UnitFlag.CanHealFullHealthUnits`


def build(state_file: str) -> int:
    """`spaceWolfPriest` est ABSENT du pool (mesure #982-r5 : 97 regulieres + 8 MoW au rank 17) ->
    injection catalogue OBLIGATOIRE, puis `build --seed-bc`."""
    bc = os.path.splitext(state_file)[0] + ".seedbc.json"
    p = subprocess.run([sys.executable, "catalog_inject.py", "--units", PORTEUR, "--out", bc],
                       cwd=_HERE, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"catalog_inject a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-600:]}")
    argv = [sys.executable, "rl_duel.py", "build", "--seed-bc", bc, "--board", BOARD,
            "--seed", SEED, "--state-file", state_file,
            "--p-units", f"{PORTEUR},{ALLIE}", "--a-units", "necroWarden,tauCrisis"]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-900:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--runner", type=int, default=None)
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=120):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = args.runner if args.runner is not None else build(args.state_file)
    print(f"board {BOARD} seed {SEED} | porteur {PORTEUR} | runner {rid}")
    bad = []
    try:
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90) or {}
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180) or {}
        ob = rpc("observeBattle", {"runnerId": rid}, 90) or {}

        # --- etage 1 : le FLAG au spawn (`AddFlagBehaviour$$Execute`, ecriture ECS silencieuse)
        # ⚠ `combatSnapshot.units[]` ne porte PAS de `visualId` : l'appariement passe par
        # `observeBattle`, dont le `squadId` EST l'`entityId` du snapshot (piege paye en mesure).
        vis_by_sq = {}
        for u in (ob.get("units") or []):
            for k in ("squadId", "entityId"):
                if u.get(k) is not None:
                    vis_by_sq.setdefault(int(u[k]), u.get("visualId") or u.get("unitId"))
        by_vis_snap = {}
        for u in (snap.get("units") or []):
            v = u.get("visualId") or vis_by_sq.get(int(u.get("entityId") or -1))
            if v is not None:
                by_vis_snap[v] = u
        b_snap = by_vis_snap.get(PORTEUR)
        if b_snap is None:
            raise RuntimeError(f"{PORTEUR} absent de `combatSnapshot` -- montage NON INSTALLE "
                               f"(unites vues : {sorted(x for x in by_vis_snap if x)} ; cles d'une "
                               f"entree snapshot : "
                               f"{sorted((snap.get('units') or [{}])[0].keys())})")
        flags = list(b_snap.get("unitFlags") or [])
        autres = {v: list((u.get("unitFlags") or [])) for v, u in by_vis_snap.items()
                  if v and v != PORTEUR}
        print(f"  [etage 1] unitFlags {PORTEUR} = {flags} | autres = {autres}")
        if FLAG_CAN_HEAL_FULL not in flags:
            bad.append(f"etage 1 : le flag {FLAG_CAN_HEAL_FULL} n'est PAS pose sur {PORTEUR} au "
                       f"spawn ({flags}) -- `AddFlagBehaviour$$Execute` n'a pas joue")
        if any(FLAG_CAN_HEAL_FULL in v for v in autres.values()):
            bad.append(f"etage 1 : le flag {FLAG_CAN_HEAL_FULL} est aussi sur une AUTRE unite "
                       f"({autres}) -- le temoin serait DEGENERE")

        # --- etage 2 : le SWAP D'ACTIVE, cote `decisionView`
        by_vis_dv = {}
        for u in (dv.get("units") or []):
            v = u.get("visualId") or vis_by_sq.get(int(u.get("id") or -1))
            if v is not None:
                by_vis_dv[v] = u
        b_dv = by_vis_dv.get(PORTEUR)
        if b_dv is None:
            raise RuntimeError(f"{PORTEUR} absent de `decisionView` (unites : "
                               f"{sorted(x for x in by_vis_dv if x)})")
        ids = [a.get("id") for a in (b_dv.get("abilities") or [])]
        print(f"  [etage 2] decisionView.abilities {PORTEUR} = {ids}")
        if HEALING_BALMS_HEAL not in ids:
            bad.append(f"etage 2 : `decisionView` NE publie PAS {HEALING_BALMS_HEAL} sur {PORTEUR} "
                       f"({ids}) -- la premisse du SS SWAP de `runner/abilities/loki/"
                       f"healing_balms.py` (<< le substrat le livre DEJA fait >>) est FAUSSE, et le "
                       f"port doit poser le swap lui-meme")
        if HEAL_GENERIQUE in ids:
            bad.append(f"etage 2 : `decisionView` publie ENCORE le {HEAL_GENERIQUE} generique sur "
                       f"{PORTEUR} ({ids}) -- le `RemoveActiveAbility(0x12)` du natif n'a pas joue, "
                       f"ou le canal ne le reflete pas")

        # --- etage 3 : ce que le PORT relit du meme etat
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        ast = rpc("unitAbilityStates", {"runnerId": rid}, 90)
        from engine.entities.pathfinding.board import Board
        from engine.runner.snapshot import load_state
        from engine.runner.components import StatsComponent, UnitFlagsComponent
        st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"),
                        ability_states=ast)
        eid = b_snap.get("entityId")
        e = st.get_entity(eid)
        fl = e.get_component(UnitFlagsComponent) if e is not None else None
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = sc.ctx if sc is not None else None
        # ⚠ `UnitContext.active_abilities` porte des NOMS gameconfig, PAS des ordinaux (mesure :
        # `['RitesOfMorkai', ...]`) -- un `int(x)` y leve. On l'imprime tel quel.
        act = sorted(str(x) for x in (getattr(ctx, "active_abilities", None) or ()))
        print(f"  [etage 3] PORT  flags={sorted(fl.flags) if fl is not None else None} "
              f"actives={act}")
        if fl is None or not fl.has(FLAG_CAN_HEAL_FULL):
            bad.append(f"etage 3 : le PORT ne relit PAS le flag {FLAG_CAN_HEAL_FULL} sur {PORTEUR} "
                       f"-- `snapshot._load_unit_flags` n'a pas seede le `UnitFlagsComponent`")
    finally:
        if args.runner is None:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass
    if bad:
        print("[982-r5] ECHEC")
        for b in bad:
            print("   - " + b)
        return 1
    print("[982-r5] OK -- le natif pose le flag 23 au spawn ET publie 1212 (sans 18) : le SS SWAP "
          "du port est fonde, et le port relit bien le flag")
    return 0


if __name__ == "__main__":
    sys.exit(main())
