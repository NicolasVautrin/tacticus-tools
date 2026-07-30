"""#311 -- LE CONTROLE QUI TRANCHE : `boardGraph.mowPositions` lit-il la DECLARATION du plateau,
ou le REPLI natif a-t-il tire ?

Pourquoi ce probe existe
------------------------
Le capteur `mowPositions` (livre le 2026-07-30) invoque
`IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer(player)` par joueur. Sa premiere
mesure live a rendu `2 / 1 / 0` pour trois joueurs -- des valeurs **IDENTIQUES a celles que le repli
natif produirait** sur ce meme plateau. L'accord ne prouvait donc RIEN : on ne pouvait pas
distinguer

    (a) « le capteur lit la declaration du groupe de spawn »   [ce qu'on veut]
    (b) « aucun groupe n'a ete trouve et le repli a tire »      [un capteur aveugle a la config]

C'est exactement la forme d'un lot ou les DEUX hypotheses donnent le meme resultat : il ne conclut
rien, et le dire vaut mieux que de le compter comme une validation.

La cascade native, mirroree dans `engine.services.machine_of_war_position` :

    grp = spawnPointSet@+0x78.GroupForPlayer(teamIndex, playerNr)
    if (grp != null) return grp.<+0x14>            // la DECLARATION du plateau
    if (teamIndex != 1) return (teamIndex == 2) ? 1 : 0     // le REPLI
    return 2

Le montage discriminant
-----------------------
Deux plateaux de meme geometrie, dont les declarations DIVERGENT :

  * `MC1_67` (SpawnPointSetIndex 1) declare `(TWPI 0 -> 2, TWPI 1 -> 1)`
        -> declaration == repli. **Ne discrimine pas.** C'est le bras de reference.
  * `C1_03`  declare `(TWPI 0 -> 0, TWPI 1 -> 0)` pour les DEUX camps
        -> declaration (0, 0) CONTRE repli (2, 1). **C'est lui qui tranche.**

Balayage des 675 boards du depot (cf. `engine.services.machine_of_war_position`) : 502 declarent
(0, 0) et 173 declarent (2, 1) -- le repli serait donc faux sur ~74 % des plateaux, ce qui est
precisement pourquoi un capteur qui retomberait dessus serait inutilisable.

Verdict rendu
-------------
  * `mowPositions` == declaration sur les DEUX bras, et != repli sur `C1_03` -> le capteur lit la
    declaration. #311 est tranche.
  * `mowPositions` == repli sur `C1_03` -> le capteur ne voit pas la config : #311 est REFUTE, et le
    residu doit etre rouvert.

Usage : `python scripts/python/probe_311_mow_declaration_control.py`
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"

SEED = 909
RANK = "17"
P_UNITS = "deathTyphus,deathPutrifier"
A_UNITS = "orksWarboss,necroWarden,astraCreed"

# (nom du bras, board, ce que la BC declare, discriminant ?)
ARMS = (
    ("REFERENCE", "MC1_67", "declaration == repli -> ne discrimine PAS", False),
    ("DISCRIMINANT", "C1_03", "declaration (0,0) CONTRE repli (2,1)", True),
)


def _rpc(method, args=None, timeout=120000):
    import probe_27_3_live as L
    return L._rpc(method, args, timeout)


def _build(board: str, state: Path) -> int:
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", str(SEED), "--board", board,
                    "--rank", RANK, "--p-units", P_UNITS, "--a-units", A_UNITS,
                    "--state-file", str(state)],
                   cwd=str(HERE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if not state.exists():
        raise SystemExit("build echoue sur %s : pas de state-file" % board)
    return int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])


def _declared_groups(state: Path):
    """Les `SpawnPointGroups` du SpawnPointSet ACTIF de la BC que le runner EXECUTE -- la VERITE
    TERRAIN de ce probe. `rl_duel build` ecrit la BC normalisee dans son state-file : c'est
    litteralement l'objet que `buildRunner` a consomme, donc la meme structure que
    `BattleQuery+0x78`."""
    from engine.services.machine_of_war_position import spawn_groups_from_battle_config
    return spawn_groups_from_battle_config(json.loads(state.read_text(encoding="utf-8")).get("bc")
                                           or {})


def _arm(name: str, board: str, note: str, discriminant: bool) -> dict:
    from engine.services.machine_of_war_position import (machine_of_war_position_for_player,
                                                         group_for_player)
    LOGS.mkdir(parents=True, exist_ok=True)
    state = LOGS / ("rs_311_%s.json" % board.lower())
    rid = _build(board, state)
    try:
        groups = _declared_groups(state)
        graph = _rpc("boardGraph", [{"runnerId": rid}])
        rows = graph.get("mowPositions")
        out = {"arm": name, "board": board, "note": note, "discriminant": discriminant,
               "rid": rid, "groups": groups, "rows": rows, "per_player": []}
        if rows is None:
            out["error"] = "mowPositions ABSENT de boardGraph (capteur non deploye ?)"
            return out
        for r in rows:
            team = r.get("teamId")
            grp = group_for_player(groups, int(team)) if team is not None else None
            # DECLARATION : ce que le groupe du plateau porte (None = aucun groupe pour ce team).
            declared = None if grp is None else int(grp.get("MachineOfWarPosition") or 0)
            # REPLI : ce que le natif rendrait s'il n'avait TROUVE aucun groupe.
            fallback = (machine_of_war_position_for_player([], int(team))
                        if team is not None else None)
            out["per_player"].append({
                "playerId": r.get("playerId"), "teamId": team,
                "measured": r.get("machineOfWarPosition"), "declared": declared,
                "fallback": fallback, "error": r.get("error")})
        return out
    finally:
        try:
            _rpc("disposeRunner", [{"runnerId": rid}])
        except Exception:                                       # noqa: BLE001
            pass


def _print(a: dict) -> None:
    print("\n=== bras %s : board %s (runner %s) ===" % (a["arm"], a["board"], a["rid"]))
    print("  %s" % a["note"])
    print("  SpawnPointGroups declares = %s"
          % ([(g.get("TeamWithPlayerIndex"), g.get("MachineOfWarPosition"))
              for g in (a["groups"] or [])] or "NON LUS"))
    if a.get("error"):
        print("  X %s" % a["error"])
        return
    print("  %-9s %-7s %-9s %-10s %-9s" % ("playerId", "teamId", "MESUREE", "declaree", "repli"))
    for p in a["per_player"]:
        print("  %-9s %-7s %-9s %-10s %-9s%s"
              % (p["playerId"], p["teamId"], p["measured"],
                 "(aucun grp)" if p["declared"] is None else p["declared"], p["fallback"],
                 ("  <- " + p["error"]) if p.get("error") else ""))


def _verdict(arms) -> int:
    print("\n=== VERDICT #311 ===")
    rc = 0
    for a in arms:
        if a.get("error"):
            print("  %-12s : NON CONCLUANT -- %s" % (a["arm"], a["error"]))
            rc = 1
            continue
        # Sur un groupe ABSENT, declaration et repli se confondent par construction : le natif
        # RETOMBE alors sur le repli, c'est son comportement, pas un defaut du capteur.
        expected = [(p["fallback"] if p["declared"] is None else p["declared"])
                    for p in a["per_player"]]
        measured = [p["measured"] for p in a["per_player"]]
        fallbacks = [p["fallback"] for p in a["per_player"]]
        ok = measured == expected
        print("  %-12s (%s) : mesuree=%s attendue=%s repli=%s -> %s"
              % (a["arm"], a["board"], measured, expected, fallbacks, "OK" if ok else "ECART"))
        if not ok:
            rc = 1
        if a["discriminant"]:
            # Le seul bras qui porte de l'information : les deux hypotheses y different.
            if expected == fallbacks:
                print("    X CE BRAS NE DISCRIMINE PAS : declaration et repli coincident. Le"
                      " montage est a refaire, il ne conclut rien.")
                rc = 1
            elif ok:
                print("    OK le capteur suit la DECLARATION la ou le repli aurait rendu %s"
                      " -> #311 TRANCHE" % fallbacks)
            elif measured == fallbacks:
                print("    X le capteur a rendu le REPLI : il ne voit pas la config -> #311 REFUTE")
    return rc


def main() -> int:
    sys.path.insert(0, str(HERE))
    arms = []
    for name, board, note, disc in ARMS:
        a = _arm(name, board, note, disc)
        arms.append(a)
        _print(a)
    return _verdict(arms)


if __name__ == "__main__":
    raise SystemExit(main())
