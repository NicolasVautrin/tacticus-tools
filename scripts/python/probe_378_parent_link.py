"""#378 -- le lien enfant -> SUMMONER (`ChildComponent.ParentId`) est-il PUBLIE, et le port le
LIT-il ?

RE (decompile = verite). Le lien enfant -> parent vit sur
`IdunBattle.Entities.Components.ChildComponent`, champ `ParentId` (`BEntityId` = int32 @+0x10).
C'est ce champ que lit `IdunBattle.Entities.UnitExtensions$$GetParent` --
`TryGetComponent<ChildComponent>(child)` puis `state.GetEntity(comp.ParentId)`, la recursion vers
la RACINE etant conditionnee a son 3e argument `root`. Il est le foyer de
`IdunBattle.Entities.Selectors.ParentSelector$$Select` (noeud DSL
`IdunBattleLogic.Entities.DSLSelectors$$Parent`) et du gate
`IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook$$IsFriendlyKell`
(`*(int *)(comp + 0x10) == EntityId(caster)` puis `UnitExtensions$$IsFriend`).

⚠ CE N'EST PAS `IdunBattle.Entities.Components.ParentComponent`. Le residu de #372 nommait
« ParentComponent, id @+0x10 » : c'est l'AUTRE bout du lien. `ParentComponent+0x10` est
`ChildrenIds`, une `List` -- son `$$.ctor` y construit une liste et son `$$ToString` la formate
par `EnumerableExtensions$$ToStringIncludingContent`. Verifie sur `rnca9r7q6c` par DEUX sources
independantes : le RPC `classFields` (`ChildComponent.ParentId`, offset 16, type `BEntityId` ;
`ParentComponent.ChildrenIds`, offset 16, type `List`) et le decompile de
`IdunBattle.Entities.Components.ChildComponent$$ToString` (`il2cpp_value_box(Int32,
*(int *)(this + 0x10))`).

CE QU'IL A DEJA ETABLI (run du 2026-07-31, runner 264, MC1_67/777, capteur #378 PAS encore charge
-- ces trois faits viennent du hook COURANT et du decompile, pas du capteur en attente) :

  1. `ParentId == 0` VAUT « pas de parent ». `IdunBattle.Entities.Components.MatchComponent$$NextId`
     est un PRE-incrementeur (`*(int *)(this + 0x10) += 1 ; return`) sur un champ zeroe, et c'est la
     source UNIQUE des ids d'entite (ses xrefs sont exactement les `Add*Operation$$Execute` : unite,
     machine, plateforme, tuile, effet, joueur, ability d'environnement). Le premier id emis est
     donc `1`. Confirme live : `dumpEntityComponents(entityId: 0)` rend `entity 0 not found`, et le
     roster porte `parentId = 0` la ou les deux `orksOrkBoys` invoques portent `83` (le warboss).
     Le capteur normalise donc `0 -> null` -- mirror du `state.GetEntity(0) -> null` que
     `UnitExtensions$$GetParent` produit, puisqu'il ne gate PAS sur zero.
  2. CHAQUE unite porte `ChildComponent` ET `ParentComponent` (l'ECS les cree systematiquement) :
     la branche « composant absent » du capteur ne se declenche pas en pratique. On la garde parce
     qu'elle mirrore la sortie `TryGetComponent == false` de `GetParent`.
  3. Le hook COURANT publie deja `parentId` cote `decisionView` (depuis `3b9a3b79`) mais SANS
     discriminant et SANS normalisation -- d'ou `0` sur le roster. C'est exactement ce que #378
     ferme : `combatSnapshot` ne le portait pas du tout, et le `0` se serait propage dans
     `parent_by_id` comme un id d'entite.

CE QUE CE PROBE MESURE, par etages :

  E0 canal    -- `combatSnapshot.units[]` porte-t-il `parentMeasured` ? Sinon le capteur #378 n'est
                 pas charge -> NON CONFRONTE, et AUCUN etage suivant ne conclut quoi que ce soit.
  E1 spawn    -- `orksWarboss` caste `Waaagh`(1058) -> un `orksOrkBoys` apparait. C'est le seul
                 moyen d'obtenir un lien parent NON NUL en live : aucune unite du roster initial
                 n'a de `ChildComponent`.
  E2 lecture  -- `combatSnapshot` rend-il `parentId == warboss` sur le summon, et
                 `parentMeasured=True` + `parentId=None` sur les unites du roster ?
  E3 coherence-- `decisionView.units[]` rend-il LE MEME couple ? Les deux canaux partagent le
                 lecteur `readParentLink` : une divergence denoncerait un fork de la source unique.
  E4 seed     -- `load_state(decision, observe, snapshot)` puis `components.parent_of(state, summon)`
                 rend-il le warboss ? C'est la face COMBAT du residu de #372 : sans ce seed, un etat
                 hydrate d'une capture posterieure au spawn repartait a `parent_id = None`.

Les VERDICTS sont des fonctions PURES (`check_channel`, `check_link`, `check_agreement`,
`check_seed`), pour que les gardes offline
(`tests/engine/test_378_parent_link_offline.py`) exercent la logique de decision SANS live -- y
compris la detection du hook anterieur, qui est precisement ce qu'un test live ne saurait pas
distinguer d'un vrai « pas de summon ».

Usage (depuis scripts/python) :
    python probe_378_parent_link.py --state-file <ABSOLU> [--board MC1_67] [--seed 777]
                                    [--turns 25] [--keep]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

import requests
from sibling_script import sibling_script

HOST = "http://127.0.0.1:8765"
CASTER = "orksWarboss"
ALLY = "orksNob"
ENEMIES = "darkaCompanion,tyranWingedPrime,ultraInceptorSgt"
WAAAGH = 1058

HOOK_NOT_REINJECTED = (
    "NON CONFRONTE -- le capteur #378 n'est PAS charge : aucune ligne de `combatSnapshot.units[]` "
    "ne porte `parentMeasured`. Le correctif vit dans `frida/hooks/*` (rpc-snapshot.ts + "
    "projection.ts) et reste INERTE tant que le bundle n'a pas ete rebuilde ET reinjecte. Rien "
    "n'est conclu du natif : ni « pas de summon », ni « lien absent ».")


# ------------------------------------------------------------------ verdicts (fonctions PURES)

def check_channel(snapshot: dict) -> dict:
    """Le capteur #378 est-il charge ? On regarde la PRESENCE de la cle `parentMeasured`, pas sa
    valeur : un hook anterieur ne la connait pas du tout, alors qu'un capteur charge la pose sur
    CHAQUE ligne (fut-ce a `False` si `ChildComponent` etait irresoluble).

    ⚠ On ne peut PAS discriminer sur `parentId`, que l'ancien `readParentId` publiait deja cote
    `decisionView` -- et qui vaut `null` dans les deux mondes pour une unite sans parent. C'est
    exactement l'ambiguite que le champ `parentMeasured` existe pour fermer."""
    units = (snapshot or {}).get("units")
    if not units:
        return {"status": "no-units",
                "message": "combatSnapshot ne rend AUCUNE unite -- montage KO, rien n'est conclu"}
    if not any("parentMeasured" in u for u in units):
        return {"status": "not_reinjected", "message": HOOK_NOT_REINJECTED}
    return {"status": "measured",
            "message": "capteur #378 charge (%d/%d lignes portent parentMeasured)"
                       % (sum(1 for u in units if "parentMeasured" in u), len(units))}


def check_link(snapshot: dict, child_id: int, expected_parent: int) -> dict:
    """Le lien LU est-il celui attendu ? Trois issues distinctes -- et `parentMeasured=False` n'est
    JAMAIS lu comme « pas de parent »."""
    row = next((u for u in ((snapshot or {}).get("units") or [])
                if u.get("entityId") == child_id), None)
    if row is None:
        return {"status": "absent",
                "message": "u%s absent de combatSnapshot -- montage KO" % child_id}
    if row.get("parentMeasured") is not True:
        return {"status": "not-measured",
                "message": ("u%s : parentMeasured=%r -- la mesure n'a PAS eu lieu (classe "
                            "`ChildComponent` irresolue ou lecture KO). Le `parentId=%r` qui "
                            "l'accompagne ne veut RIEN dire."
                            % (child_id, row.get("parentMeasured"), row.get("parentId")))}
    got = row.get("parentId")
    if got != expected_parent:
        return {"status": "wrong",
                "message": ("u%s : parentId=%r, attendu u%s (le summoner qui vient de le faire "
                            "apparaitre)" % (child_id, got, expected_parent))}
    return {"status": "ok", "message": "u%s -> parent u%s (LU)" % (child_id, got)}


def check_roster_has_no_parent(snapshot: dict, roster_ids) -> dict:
    """Contre-epreuve : les unites du roster INITIAL n'ont pas de `ChildComponent`, donc le capteur
    doit y rendre `parentMeasured=True` + `parentId=None`. Sans cet etage, un capteur qui poserait
    `parentMeasured=True` partout ET un id constant passerait l'etage E2."""
    bad = []
    for u in ((snapshot or {}).get("units") or []):
        if u.get("entityId") not in set(roster_ids):
            continue
        if u.get("parentMeasured") is not True or u.get("parentId") is not None:
            bad.append((u.get("entityId"), u.get("parentMeasured"), u.get("parentId")))
    if bad:
        return {"status": "wrong",
                "message": ("des unites du roster initial portent un parent : %s -- attendu "
                            "(measured=True, parentId=None) partout" % bad)}
    return {"status": "ok",
            "message": "roster initial : parentMeasured=True + parentId=None (mesure PLEINE)"}


def check_agreement(snapshot: dict, decision: dict) -> dict:
    """`combatSnapshot` et `decisionView` partagent le lecteur `readParentLink` : leurs couples
    (parentId, parentMeasured) doivent coincider sur toute unite presente des deux cotes. Un
    desaccord denonce un FORK de la source unique, pas un etat de jeu."""
    dv = {u.get("id"): (u.get("parentId"), u.get("parentMeasured"))
          for u in ((decision or {}).get("units") or [])}
    diffs = []
    for u in ((snapshot or {}).get("units") or []):
        eid = u.get("entityId")
        if eid not in dv:
            continue
        mine = (u.get("parentId"), u.get("parentMeasured"))
        if mine != dv[eid]:
            diffs.append((eid, mine, dv[eid]))
    if diffs:
        return {"status": "fork",
                "message": ("les DEUX canaux divergent sur %d unite(s) (snapshot vs decisionView) "
                            ": %s -- la source unique `readParentLink` a fourche"
                            % (len(diffs), diffs[:6]))}
    return {"status": "ok",
            "message": "combatSnapshot == decisionView sur le couple (parentId, parentMeasured)"}


def check_seed(state, child_id: int, expected_parent: int) -> dict:
    """Le port a-t-il INGERE le lien ? C'est la face COMBAT du residu de #372 : `load_state` doit
    poser `UnitComponent.parent_id`, sinon `parent_of` / `children_of` / le selecteur DSL `Parent`
    / `build_hits_board.parent_by_id` restent aveugles sur tout etat hydrate."""
    from engine.runner.components import parent_of
    par = parent_of(state, child_id)
    got = None if par is None else int(par.id)
    if got != expected_parent:
        return {"status": "wrong",
                "message": ("load_state : parent_of(u%s) = %r, attendu u%s -- le seed "
                            "`_load_unit_parent` n'a pas mordu" % (child_id, got, expected_parent))}
    return {"status": "ok", "message": "load_state : parent_of(u%s) = u%s" % (child_id, got)}


# ------------------------------------------------------------------ transport

def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--turns", type=int, default=25)
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    if not a.reuse:
        out = subprocess.run([sys.executable, sibling_script("rl_duel.py"), "build", "--seed", a.seed,
                              "--board", a.board, "--state-file", a.state_file,
                              "--p-units", f"{CASTER},{ALLY}", "--a-units", ENEMIES],
                             capture_output=True, text=True)
        if out.returncode != 0:
            print("BUILD FAILED rc=%d" % out.returncode)
            print((out.stdout or "")[-1200:])
            print((out.stderr or "")[-1200:])
            return 1
    rid = json.loads(Path(a.state_file).read_text(encoding="utf-8"))["runnerId"]
    s = sid()
    print("runnerId=%s board=%s seed=%s session=%s" % (rid, a.board, a.seed, s))
    verdicts: list = []
    try:
        # ---- E0 : LE CANAL est-il charge ? ------------------------------------------------- #
        snap0 = rpc(s, "combatSnapshot", {"runnerId": rid}, 90)
        v0 = check_channel(snap0)
        print("E0 canal   [%s] %s" % (v0["status"], v0["message"]))
        verdicts.append(v0)
        channel_live = (v0["status"] == "measured")

        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
        me = next((u.get("owner") for u in (dv.get("units") or [])
                   if u.get("visualId") == CASTER), None)
        wb_id = next((u["id"] for u in (dv.get("units") or [])
                      if u.get("visualId") == CASTER and u.get("alive")), None)
        if wb_id is None:
            print("VERDICT montage: warboss absent")
            return 2
        roster0 = [u["id"] for u in (dv.get("units") or [])]
        print("   me=%s warboss=u%s roster=%d unites" % (me, wb_id, len(roster0)))

        # ---- E1 : APPROCHE puis CAST -------------------------------------------------------- #
        from engine.entities.pathfinding.board import Board
        bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")

        def tile_of(u):
            p = u.get("pos") or {}
            return (board.id_at(p.get("col"), p.get("row"))
                    if p.get("col") is not None else None)

        def bfs(src):
            dist, q = {src: 0}, deque([src])
            while q:
                x = q.popleft()
                for n in board.neighbours(x):
                    if n not in dist and (n == src or board.walkable(n)):
                        dist[n] = dist[x] + 1
                        q.append(n)
            return dist

        legal = None
        for t in range(a.turns):
            dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
            units = {u["id"]: u for u in (dv.get("units") or [])}
            if dv.get("currentPlayer") != me:
                rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            if not units.get(wb_id, {}).get("alive"):
                print("VERDICT montage: warboss mort avant le cast")
                return 3
            at = rpc(s, "abilityTargets", {"runnerId": rid, "unitId": wb_id,
                                           "allAbilities": True}, 90)
            tg = []
            for unit in (at.get("units") or []):
                if unit.get("unitId") != wb_id:
                    continue
                for ab in (unit.get("abilities") or []):
                    if ab.get("abilityId") == WAAAGH:
                        tg = ab.get("fromHere") or []
            if tg:
                legal = tg[0]
                break
            ens = [u for u in units.values() if u.get("owner") != me and u.get("alive")]
            if not ens:
                print("VERDICT montage: plus d'ennemi")
                return 4
            dgoal = bfs(tile_of(ens[0]))
            mt = rpc(s, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == wb_id), None)
            reach = {board.id_at(ti["col"], ti["row"]): (ti["col"], ti["row"])
                     for ti in ((cmt or {}).get("tiles") or [])}
            pool = [ti for ti in reach if ti in dgoal]
            if pool:
                col, row = reach[min(pool, key=lambda x: dgoal[x])]
                rpc(s, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": wb_id, "to": {"col": col, "row": row}}}, 60)
            rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        if legal is None:
            print("VERDICT montage: aucune cible legale de Waaagh en %d tours" % a.turns)
            return 5

        act = {"kind": "ability", "casterId": wb_id, "abilityType": WAAAGH}
        if legal.get("kind") == "unit":
            act["targetId"] = legal.get("targetId")
        else:
            act["to"] = {"col": legal.get("col"), "row": legal.get("row")}
        res = rpc(s, "applyAction", {"runnerId": rid, "action": act}, 120)
        a0 = (res.get("actions") or [{}])[0]
        dv2 = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
        newborn = sorted(set(u["id"] for u in (dv2.get("units") or [])) - set(roster0))
        print("E1 cast    ok=%s spawned=%s -> unites APPARUES = %s"
              % (a0.get("ok"), a0.get("spawned"), newborn))
        if not newborn:
            print("VERDICT montage: aucun summon apparu -> le lien parent n'existe nulle part")
            return 6
        child = newborn[0]

        # ---- E2/E3/E4 : LECTURE, COHERENCE, SEED --------------------------------------------- #
        snap1 = rpc(s, "combatSnapshot", {"runnerId": rid}, 90)
        obs = rpc(s, "observeBattle", {"runnerId": rid}, 60)
        for tag, v in (("E2 lien   ", check_link(snap1, child, wb_id)),
                       ("E2 roster ", check_roster_has_no_parent(snap1, roster0)),
                       ("E3 accord ", check_agreement(snap1, dv2))):
            print("%s [%s] %s" % (tag, v["status"], v["message"]))
            verdicts.append(v)

        from engine.runner.snapshot import load_state
        st = load_state(dv2, obs, snap1)
        v4 = check_seed(st, child, wb_id)
        print("E4 seed    [%s] %s" % (v4["status"], v4["message"]))
        verdicts.append(v4)

        # ---- SYNTHESE ------------------------------------------------------------------------ #
        if not channel_live:
            print("\nVERDICT: %s" % HOOK_NOT_REINJECTED)
            print("Le MONTAGE, lui, est PRET et discriminant : le summon u%s existe (cast de "
                  "Waaagh par u%s), les quatre etages sont cables. Il ne manque que la fenetre."
                  % (child, wb_id))
            return 7
        bad = [v for v in verdicts if v["status"] != "ok" and v["status"] != "measured"]
        if bad:
            print("\nVERDICT: %d etage(s) en ECHEC -- %s"
                  % (len(bad), " | ".join(v["message"] for v in bad)))
            return 8
        print("\nVERDICT: OK -- le lien enfant -> summoner est PUBLIE (combatSnapshot ET "
              "decisionView, meme couple) et le port l'INGERE (load_state -> parent_of).")
        return 0
    finally:
        if not a.keep:
            try:
                subprocess.run([sys.executable, sibling_script("rl_duel.py"), "dispose",
                                "--state-file", a.state_file], capture_output=True, text=True)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
