"""Probe LIVE #1175 -- le marqueur `HatefulAssault_AlreadyAttacked` sur le NATIF, pas sur le port.

CE QU'IL FAUT MESURER (et pourquoi le decompile ne suffit pas) : la fabrique de 1175 appelle un corps
de `.ctor` PARTAGE par DEUX classes soeurs -- `IdunBattle.Entities.Effects.Loki.UntilOfEndTurnEffect`
(retrait `On(0x17 TurnEnd)`) et `...UntilOfEndPhaseEffect` (retrait `On(0x3a PhaseEnd)`). Le slot
`Il2CppClass*` de 1175 est UNIQUE mais ne se resout pas statiquement en un NOM (les deux slots ne sont
lus que par leur propre lambda -- aucun xref discriminant). L'inconnue restante est donc une IDENTITE
RUNTIME : on MESURE (skill `tacticus-re-port` §1.2 C.4), on ne devine pas.

TROIS QUESTIONS, chacune rend une observation :

  A. POSE      -- `blackTerminator` frappe-t-il l'unite qui S'ECARTE d'un hex adjacent, et 1175
                  apparait-il sur elle ? (HP avant/apres + `decisionView.units[].effects`)
  B. EXPIRATION-- a quel evenement 1175 quitte-t-il `decisionView` ? On echantillonne l'etat APRES
                  CHAQUE `endturn` : disparition au 1er `endturn` => `TurnEnd` ; survie a un tour
                  adverse complet puis disparition => `PhaseEnd`.
  C. TEMOIN    -- une unite qui bouge SANS partir d'un hex adjacent ne doit ni etre frappee ni etre
                  marquee. Sans ce bras, une pose observee ne prouve pas que c'est CE mecanisme.

MONTAGE : `blackTerminator` est mis cote ADVERSE (`--a-units`) -- c'est le seul moyen de PILOTER
l'unite qui bouge (on ne commande que sa propre equipe). Nos unites recoivent `--hp-player` eleve
pour survivre aux 2 coups Power et pouvoir rejouer le scenario plusieurs tours.
⚠ Angrax porte `TeleportStrike` : il commence en Deep Strike, donc NON CIBLABLE -- et
`IsAdjacent(..., OnlyAliveAndTargetable)` echoue tant qu'il n'a pas agi. Le probe laisse donc l'IA
adverse jouer jusqu'a ce qu'il soit pose, puis approche.

Usage (depuis scripts/python) :
    python probe_1175_live_marker.py --state-file <ABSOLU hors data/> [--board MC1_67] [--seed 777]
                                     [--turns 14] [--keep]

ASCII only (console cp1252). Ne (re)injecte JAMAIS -- il consomme la session existante.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
CARRIER = "blackTerminator"                 # Angrax -- HERO, dans `rl_duel build --list-pool`
ALREADY_ATTACKED = 1175                     # 0x497
TELEPORTING_IN = 1035                       # `TeleportStrike_TeleportingIn` -- le Deep Strike


def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def eff_count(s: int, rid: int) -> int:
    """Nombre d'ENTITES de type `Effect` sur le plateau (`observeBattle.counts.effects`).

    C'est le SEUL capteur qui voie un effet INACTIF : `AddEffectOperation$$AddNewEffect` n'ecrit
    jamais `EffectComponent.IsActive @+0x5c` (l'effet nait faux, cf. `hateful_assault.py`), et la
    projection `decisionView` FILTRE les inactifs. Un marqueur absent de `decisionView` peut donc
    etre bien POSE : sans ce compteur, on lirait le verdict d'un outil comme une mesure."""
    ob = rpc(s, "observeBattle", {"runnerId": rid}, 90) or {}
    return int(((ob.get("counts") or {}).get("effects")) or 0)


def snap(s: int, rid: int) -> dict:
    # `includeInactive` : demande explicite des effets INACTIFS. Si la projection ne connait pas
    # l'option elle l'ignore -- cout nul, et le compteur d'entites-effet reste l'arbitre.
    dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                                 "includeInactive": True}, 120)
    return {
        "currentPlayer": dv.get("currentPlayer"), "turn": dv.get("turn"),
        "toActivate": list(dv.get("toActivate") or []),
        "units": {u["id"]: {
            "visualId": u.get("visualId"), "owner": u.get("owner"), "alive": u.get("alive"),
            "pos": u.get("pos"), "hp": u.get("hp"), "hasAction": u.get("hasAction"),
            "ctrl": u.get("ctrl"),
            "effects": [{"t": e.get("effectType"), "n": e.get("name"), "rem": e.get("remaining")}
                        for e in (u.get("effects") or [])],
        } for u in (dv.get("units") or [])},
    }


def has_eff(u: dict, t: int) -> bool:
    return any(e["t"] == t for e in (u.get("effects") or []))


def _axial(p):
    """(col, row) evenq -> coordonnees CUBE, pour une distance hex fiable."""
    col, row = int(p["col"]), int(p["row"])
    x = col
    z = row - (col + (col & 1)) // 2
    return (x, -x - z, z)


def hexdist(a, b) -> int:
    if not a or not b:
        return 99
    ca, cb = _axial(a), _axial(b)
    return max(abs(ca[0] - cb[0]), abs(ca[1] - cb[1]), abs(ca[2] - cb[2]))


def build(state_file: str, board: str, seed: str, p_units: str, a_units: str) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
            "--state-file", state_file, "--p-units", p_units, "--a-units", a_units,
            "--hp-player", "400000"]
    out = subprocess.run(argv, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("[1175] build KO rc=%d\n%s\n%s"
                         % (out.returncode, out.stdout[-2000:], out.stderr[-2000:]))
    return int(json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"])


def move(s: int, rid: int, uid: int, col: int, row: int, events: bool = False):
    return rpc(s, "applyAction", {"runnerId": rid, "captureEvents": bool(events), "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def endturn(s: int, rid: int):
    return rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)


def movable(s: int, rid: int, uid: int):
    """Tuiles legales de `uid` (`GetMovableTilesFor`). ⚠ la cle d'unite est `unitId`, pas `id` --
    et le RPC ne rend QUE les unites CONTROLEES (`side: friendly`)."""
    r = rpc(s, "aiMovableTiles", {"runnerId": rid}, 120) or {}
    for u in (r.get("units") or []):
        if int(u.get("unitId", -1)) == int(uid):
            return [(int(t["col"]), int(t["row"])) for t in (u.get("tiles") or [])]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--p-units", default="templSwordBrother,ultraTitus")
    ap.add_argument("--a-units", default="blackTerminator,necroWarden")
    ap.add_argument("--turns", type=int, default=14)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    s = sid()
    rid = build(a.state_file, a.board, a.seed, a.p_units, a.a_units)
    print("[1175] runner %d  board=%s  seed=%s" % (rid, a.board, a.seed))
    verdict = 4
    try:
        sn = snap(s, rid)
        angrax = next((uid for uid, u in sn["units"].items()
                       if u["visualId"] == CARRIER), None)
        if angrax is None:
            print("[1175] %s ABSENT du runner -- montage KO" % CARRIER)
            return 3
        # `ctrl` = les unites que le runner me laisse COMMANDER (`aiMovableTiles` = `side: friendly`
        # ne rend qu'elles). C'est le seul critere -- `owner == currentPlayer` designe aussi le camp
        # ADVERSE quand c'est son tour, et on ne peut pas le piloter.
        my_player = next((u["owner"] for u in sn["units"].values() if u.get("ctrl")), None)
        mine = [uid for uid, u in sn["units"].items() if u.get("ctrl")]
        print("[1175] angrax=%s  monPlayer=%s  mes unites=%s" % (angrax, my_player, mine))

        approached = None            # l'unite a moi, adjacente a Angrax, qui va s'ecarter
        for t in range(a.turns):
            sn = snap(s, rid)
            au = sn["units"].get(angrax) or {}
            deep = has_eff(au, TELEPORTING_IN)
            mine = [uid for uid, u in sn["units"].items()
                    if u.get("ctrl") and u["alive"] and u["hasAction"]]
            print("  t%02d turn=%s player=%s angrax pos=%s deepStrike=%s hp=%s | mes actifs=%s"
                  % (t, sn["turn"], sn["currentPlayer"], au.get("pos"), deep, au.get("hp"), mine))
            if sn["currentPlayer"] != my_player or not mine:
                endturn(s, rid)      # tour ADVERSE : on ne le joue pas (Angrax reste en place)
                continue

            # (A) une de mes unites est-elle DEJA adjacente a Angrax ? -> on l'ECARTE : c'est le bras
            #     qui doit declencher HatefulAssault.
            adj = [uid for uid in mine
                   if hexdist((sn["units"][uid] or {}).get("pos"), au.get("pos")) == 1]
            if adj and not deep:
                mover = adj[0]
                before = dict(sn["units"][mover])
                tiles = [t2 for t2 in movable(s, rid, mover)
                         if hexdist({"col": t2[0], "row": t2[1]}, au.get("pos")) >= 2]
                if tiles:
                    print("    -> BRAS POSE : %s (%s) s'ecarte de l'hex adjacent vers %s"
                          % (mover, before["visualId"], tiles[0]))
                    n0 = eff_count(s, rid)
                    res = move(s, rid, mover, tiles[0][0], tiles[0][1], events=True)
                    n1 = eff_count(s, rid)
                    print("    == A. entites-effet sur le plateau : %d -> %d (delta %+d)"
                          % (n0, n1, n1 - n0))
                    sn2 = snap(s, rid)
                    after = sn2["units"].get(mover) or {}
                    dmg = int(before.get("hp") or 0) - int(after.get("hp") or 0)
                    marked = has_eff(after, ALREADY_ATTACKED)
                    print("    == A. POSE : degat subi=%d  marqueur 1175=%s  effets=%s"
                          % (dmg, marked, after.get("effects")))
                    # ATTRIBUTION : c'est la trace d'EVENTS qui dit QUELLE ability a frappe -- pas le
                    # chiffre du HP (plusieurs canaux peuvent produire un delta plausible).
                    evs = (res or {}).get("events") or (res or {}).get("captured") or []
                    print("    == A. events (%d) : %s"
                          % (len(evs), json.dumps(evs)[:1500] if evs else "(aucun)"))
                    # Ou est 1175 ? sur une AUTRE entite ? -> on le DIT au lieu de conclure a l'absence.
                    where = {uid2: [e for e in (u2.get("effects") or [])
                                    if e["t"] == ALREADY_ATTACKED]
                             for uid2, u2 in sn2["units"].items()}
                    print("    == A. 1175 par unite : %s"
                          % {k: v for k, v in where.items() if v} or "(nulle part)")
                    if not marked and (n1 - n0) <= 0:
                        print("    !! marqueur ABSENT de decisionView ET aucune entite-effet creee"
                              " -> le trigger n'a PAS pose 1175. Verdict A = ECHEC.")
                        verdict = 5
                        break
                    if not marked:
                        print("    (marqueur absent de decisionView mais %+d entite(s)-effet creee(s)"
                              " : effet POSE et INACTIF -- limite du CAPTEUR, pas une absence.)"
                              % (n1 - n0))
                    # (B) EXPIRATION : on echantillonne apres CHAQUE endturn.
                    approached = mover
                    seen = []
                    base = n1
                    for k in range(6):
                        endturn(s, rid)
                        sk = snap(s, rid)
                        nk = eff_count(s, rid)
                        uk = sk["units"].get(mover) or {}
                        # DEUX capteurs, et on exige leur ACCORD : la vue projetee (qui filtre les
                        # inactifs) ET le compte d'entites-effet (qui ne filtre rien). Le marqueur est
                        # PARTI quand il a quitte la vue ET que le compte est redescendu.
                        still = has_eff(uk, ALREADY_ATTACKED) or nk >= base
                        seen.append((k, sk["turn"], sk["currentPlayer"], still))
                        print("    == B. apres endturn #%d : turn=%s player=%s  1175 en vue=%s"
                              "  entites-effet=%d (pose a %d)"
                              % (k, sk["turn"], sk["currentPlayer"],
                                 has_eff(uk, ALREADY_ATTACKED), nk, base))
                        if not still:
                            break
                    gone = next((x for x in seen if not x[3]), None)
                    print("    == B. VERDICT : 1175 disparait apres %s endturn(s) -> %s"
                          % ((gone[0] + 1) if gone else ">6",
                             "TurnEnd" if (gone and gone[0] == 0) else
                             ("PhaseEnd ou autre" if gone else "JAMAIS (marqueur A VIE)")))
                    verdict = 0 if gone else 6
                    break
                print("    (adjacent mais aucune tuile d'ecart atteignable)")

            # (C) sinon : on APPROCHE (ce move ne part pas d'un hex adjacent -> bras TEMOIN).
            best, bestd = None, 99
            for uid in mine:
                for (c, r) in movable(s, rid, uid):
                    d = hexdist({"col": c, "row": r}, au.get("pos"))
                    if d < bestd:
                        best, bestd = (uid, c, r), d
            if best is not None and bestd < 99:
                u0 = dict(sn["units"][best[0]])
                move(s, rid, best[0], best[1], best[2])
                u1 = snap(s, rid)["units"].get(best[0]) or {}
                dmg = int(u0.get("hp") or 0) - int(u1.get("hp") or 0)
                print("    -> TEMOIN : %s approche a d=%d ; degat subi=%d ; 1175=%s"
                      % (best[0], bestd, dmg, has_eff(u1, ALREADY_ATTACKED)))
                if has_eff(u1, ALREADY_ATTACKED):
                    print("    !! TEMOIN MARQUE -- le trigger fire sur un move qui ne part PAS"
                          " d'un hex adjacent. Verdict C = ECHEC.")
                    verdict = 7
                    break
            endturn(s, rid)
        if approached is None and verdict == 4:
            print("[1175] NON CONFRONTE : aucune de mes unites n'a pu s'ecarter d'un hex adjacent"
                  " en %d tours (montage a rejouer avec un autre board/seed)." % a.turns)
    finally:
        if not a.keep:
            try:
                rpc(s, "disposeRunner", {"runnerId": rid}, 30)
                print("[1175] runner %d dispose" % rid)
            except Exception as e:
                print("[1175] dispose KO: %s" % str(e)[:200])
    return verdict


if __name__ == "__main__":
    sys.exit(main())
