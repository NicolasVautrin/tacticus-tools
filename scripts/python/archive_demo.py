"""Archive une demo self-play COMPACTE depuis les 2 state-files, AVANT leur rm.

Le self-play est censé produire un dataset IL two-sided-expert. Les démonstrations =
les TRAJECTOIRES (action_log par camp), PAS le résumé prose du journal. Le teardown
supprimait les state-files (donc jetait les trajectoires) en ne gardant qu'une narration.
Ce script extrait la trajectoire compacte AVANT la suppression.

Lecture seule (aucune session Frida / RPC) : il ne lit que les state-files JSON
(`{runnerId, bc, seed, myTeam, action_log}`) et écrit data/selfplay-logs/sp_<seed>_<ts>.json.

On NE stocke PAS le BC géant : seulement seed + rosters (best-effort) + action_log des 2
camps + outcome. La démo reste REJOUABLE via le seed (build --seed N déterministe → mêmes
entity ids → on rederive le mapping entityId→unitId en replay si besoin).

Usage :
  python scripts/python/archive_demo.py --a data/_sp_<seed>_A.json --b data/_sp_<seed>_B.json \
      --ts "<ts>" --winner team1|team2|no-winner|uncertain [--out data/selfplay-logs]
"""
import argparse
import json
import os
import re


def _load(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return json.load(f)


# PlayerId -> team label. team1 = humain (TeamId 1), team2 = IA (TeamId 2).
PLAYER_ID_HUMAN = 11
PLAYER_ID_AI = 12


def _team_key(pid):
    if pid == PLAYER_ID_HUMAN:
        return "team1"
    if pid == PLAYER_ID_AI:
        return "team2"
    return f"player{pid}"


def _bare(uid):
    """unitId nu, sans suffixe éventuel (`:pvp`, `:6`, ...)."""
    return uid.split(":")[0] if isinstance(uid, str) else uid


def _rosters(sa, sb, bc):
    """Rosters {team1, team2} reconstruits depuis les DEUX sources :
    - team IA : bc.PredefinedUnits ([{Id:playerId, Units:[{UnitId}]}]) — typiquement le
      seul groupe présent (Id=12).
    - team joueur : state-file `playerUnits` ([{unitId, playerId}]) — le camp humain
      n'est JAMAIS dans PredefinedUnits (ajouté via AddUnit), d'où l'ancien team1 vide.
    Clés normalisées team1/team2 (et non par playerId), suffixes d'unitId strippés."""
    out = {}
    # 1) groupes PredefinedUnits (IA) — map playerId -> team1/team2.
    if isinstance(bc, dict):
        for pu in (bc.get("PredefinedUnits") or []):
            key = _team_key(pu.get("Id"))
            units = [_bare(u.get("UnitId") or u.get("Id"))
                     for u in (pu.get("Units") or [])]
            units = [u for u in units if u]
            if units:
                out[key] = units
    # 2) playerUnits du state-file (camp joueur) — autoritatif pour son team.
    pu_list = sa.get("playerUnits") or sb.get("playerUnits") or []
    if pu_list:
        key = _team_key((pu_list[0] or {}).get("playerId", PLAYER_ID_HUMAN))
        units = [_bare(u.get("unitId") or u.get("UnitId")) for u in pu_list]
        units = [u for u in units if u]
        if units:
            out[key] = units
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="state-file team1 (player A)")
    ap.add_argument("--b", required=True, help="state-file team2 (player B)")
    ap.add_argument("--ts", default="", help="timestamp de la vague")
    ap.add_argument("--winner", default="unknown",
                    help="team1|team2|no-winner|uncertain (authoritative_winner)")
    ap.add_argument("--out", default="data/selfplay-logs")
    a = ap.parse_args()

    sa = _load(a.a)
    sb = _load(a.b)
    bc = sa.get("bc") or sb.get("bc")
    seed = sa.get("seed")
    if seed is None:
        seed = sb.get("seed")

    traj_a = sa.get("action_log") or []
    traj_b = sb.get("action_log") or []

    demo = {
        "seed": seed,
        "ts": a.ts,
        "winner": a.winner,
        "source": "self-play",            # vs oracle-vs-IA (rl_collect_batch)
        "rosters": _rosters(sa, sb, bc),  # team1 (playerUnits) + team2 (PredefinedUnits)
        "trajectory": {                   # LA démonstration : actions ordonnées par camp
            "team1": traj_a,
            "team2": traj_b,
        },
        "action_counts": {"team1": len(traj_a), "team2": len(traj_b)},
        "replayable_via_seed": True,      # build --seed <seed> + rejoue trajectory
    }

    os.makedirs(a.out, exist_ok=True)
    safe_ts = re.sub(r"[^0-9A-Za-z_-]", "_", a.ts) or "nots"
    path = os.path.join(a.out, f"sp_{seed}_{safe_ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(demo, f, ensure_ascii=False)

    print(f"[archive-demo] {path}  (team1={len(traj_a)} actions, "
          f"team2={len(traj_b)} actions, winner={a.winner}, "
          f"rosters={len(demo['rosters'])} teams)")


if __name__ == "__main__":
    main()
