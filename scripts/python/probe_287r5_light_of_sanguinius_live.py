"""#287-r5 -- BASCULE LIVE de la regle dynamique 1177 `LightOfSanguinius`, contre l'oracle NATIF.

CE QUE CE PROBE MESURE.
`IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$GetDynamicInvalidTargetReason`
et son lambda `...u003Cu003Ec__DisplayClass2_0$$u003CGetDynamicInvalidTargetReasonu003Eb__0` :

    range = Configuration.GetNumberConstant(0x16 range);          // = 5 au gameconfig
    tiles = battleQuery.GetFreeAdjacentTiles(targetTiles);
    if (tiles.Count == 0) return 0x20;                            // TargetHasFreeAdjacentTile
    return tiles.Any(t => battleQuery.GetDistance(t, casterTile) <= range) ? 0 : 0x20;

⚠ CETTE REGLE NE REND PAS `TargetMatchesDynamicRule`. Elle refuse par `0x20`, un bit que le masque
statique de 1177 (`0x102004032`) porte DEJA. Deux consequences de mesure, et c'est tout l'enjeu du
probe :

  (a) le TEMOIN DE NON-VACUITE de `probe_287r4r1_generalisation_live.py` -- « le natif a-t-il refuse
      avec le bit dynamique ? » -- serait VIDE ici, et son vert ne dirait rien. Le temoin est donc
      le CODE `0x20`, pas le bit `0x2` ;
  (b) un refus `0x20` peut venir du volet STATIQUE (« la cible n'a aucune tuile adjacente libre »)
      AUSSI BIEN que de la regle dynamique (« aucune de ses tuiles libres n'est a `range` du
      caster »). Les confondre rendrait un vert sur un port qui n'evalue rien. Le probe les separe
      de DEUX facons independantes : par DESARMEMENT (l'attribution), et par DECOMPOSITION -- il
      imprime, pour chaque cible, le nombre de tuiles adjacentes libres et leur distance MINIMALE au
      caster, donc l'entree et la sortie de chaque etage natif.

MONTAGE. `bloodDante` (pool regulier, rank 17) contre DEUX ennemis qui ne different que par leur
DISTANCE : l'un a portee, l'autre a l'autre bout de `MC1_67`. Le masque de 1177 ne porte PAS
`TargetIsInRange` -- cette regle dynamique EST le gate de portee de l'ability, ce qui rend la
bascule observable sans qu'un autre etage ne la masque. Les positions sont FORCEES (`--place` /
`--a-place`) : aux SpawnPoints les deux ennemis seraient du meme cote.

Usage (session warmee ; le probe monte et DISPOSE son propre runner) :
    python scripts/python/probe_287r5_light_of_sanguinius_live.py
ASCII only ; exit 0 = les deux verdicts natifs sont reproduits, et le desarmement les efface.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import probe_27_custom_utility_inventory as INV                            # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.targeting import (                            # noqa: E402
    entity_tiles, get_free_adjacent_tiles, is_invalid_target,
)
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.services.movement_query import get_distance                    # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

LOGS = HERE.parents[1] / "logs"
LOS = int(ActiveAbilityType.LightOfSanguinius)        # 1177
PORTEUR = "bloodDante"
REFUS = int(TR.TargetHasFreeAdjacentTile)             # 0x20 -- le code que CETTE regle rend


def _rpc(method, body, timeout=90000):
    return INV.rpc(INV._session_id(), method, [body], timeout)


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r5 : bascule live de 1177 LightOfSanguinius")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--state-file", default="rs_287r5_los_live.json")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    state_file = LOGS / a.state_file
    _run(["build", "--seed", str(a.seed), "--board", a.board, "--rank", "17",
          "--p-units", PORTEUR, "--a-units", "orksWarboss,thousTzaangor",
          "--place", "%s:0,0" % PORTEUR,
          "--a-place", "orksWarboss:2,1",        # PROCHE  -> attendu 0
          "--a-place", "thousTzaangor:6,8",      # LOINTAIN -> attendu 0x20
          "--state-file", str(state_file)])
    if not state_file.exists():
        print("[287r5-los] PAS MESURE : build KO (state-file absent)")
        return 2
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])

    try:
        dec = _rpc("decisionView", {"runnerId": rid, "allAbilities": True})
        ob = _rpc("observeBattle", {"runnerId": rid}, 40000)
        snap = _rpc("combatSnapshot", {"runnerId": rid}, 60000)
        bg = _rpc("boardGraph", {"runnerId": rid}, 60000)
        board = Board(bg["tiles"], adjacency="evenq")
        state = load_state(dec, ob, snap, board=board)
        units = [u for u in (dec.get("units") or []) if u.get("alive")]
        caster = next((u for u in units if u.get("visualId") == PORTEUR), None)
        if caster is None:
            print("[287r5-los] PAS MESURE : porteur %s absent du montage" % PORTEUR)
            return 2
        cibles = [u for u in units if u["id"] != caster["id"]]
        if len(cibles) < 2:
            print("[287r5-los] PAS MESURE : il faut DEUX cibles (proche / lointaine)")
            return 2

        ab = P._porteur(LOS)
        caster_tiles = entity_tiles(state, int(caster["id"]))
        lignes = []
        for u in cibles:
            r = _rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                       "abilityType": LOS, "targetId": u["id"]}, 60000) or {}
            nat = int((r.get("targetReason") or {}).get("hex") or "0x0", 16)
            port = int(is_invalid_target(state, int(caster["id"]), int(u["id"]), ab) or 0)
            with P.desarme(LOS):
                sans = int(is_invalid_target(state, int(caster["id"]), int(u["id"]), ab) or 0)
            # DECOMPOSITION PAR ETAGE : entree et sortie de chaque etage natif, pas un scalaire.
            libres = get_free_adjacent_tiles(state, int(u["id"]))
            dmin = min([get_distance([t], caster_tiles) for t in libres], default=None)
            lignes.append((u["id"], u.get("visualId"), nat, port, sans, len(libres), dmin))
    finally:
        if not a.keep:
            _run(["dispose", "--state-file", str(state_file)])

    print("[287r5-los] board=%s seed=%d runner=%d -- porteur %s u%s (range gameconfig = 5)"
          % (a.board, a.seed, rid, PORTEUR, caster["id"]))
    print("  %-6s %-16s %-12s %-12s %-12s %-10s %s"
          % ("cible", "visualId", "natif", "port", "port DESARME", "tiles libres", "dist min"))
    for tid, vis, nat, port, sans, n, dmin in lignes:
        print("  u%-5s %-16s %-12s %-12s %-12s %-10d %s"
              % (tid, vis, hex(nat), hex(port), hex(sans), n,
                 "-" if dmin is None else dmin))

    accepte = [l for l in lignes if l[2] == 0]
    refuse = [l for l in lignes if l[2] & REFUS]
    reproduits = all(l[3] == l[2] for l in lignes)
    # ATTRIBUTION : le refus doit DISPARAITRE au desarmement -- sinon il vient du volet STATIQUE
    # (« aucune tuile adjacente libre »), et ce probe ne prouverait rien de la regle dynamique.
    imputables = [l for l in refuse if l[4] == 0]
    print("[287r5-los] BASCULE")
    print("  cible(s) ACCEPTEE(S) par le natif (0)                : %d" % len(accepte))
    print("  cible(s) REFUSEE(S) par le natif (TargetHasFreeAdjacentTile) : %d" % len(refuse))
    print("  le port reproduit le masque natif sur TOUTES les cibles      : %s" % reproduits)
    print("[287r5-los] ATTRIBUTION -- le refus DISPARAIT-il au desarmement ? %d / %d"
          % (len(imputables), len(refuse)))
    for l in refuse:
        if l[4] != 0:
            print("     u%s : le port refuse ENCORE (%s) regle DESARMEE -- ce refus vient du volet "
                  "STATIQUE du masque, pas de la regle dynamique" % (l[0], hex(l[4])))
    print("[287r5-los] DECOMPOSITION -- ce que chaque etage natif a rendu")
    print("  etage 1 `GetFreeAdjacentTiles` : compte de tuiles libres, ci-dessus (0 => refus des")
    print("           l'etage 1, la distance n'est jamais evaluee)")
    print("  etage 2 `GetDistance(t, casterTiles) <= 5` : distance MINIMALE, ci-dessus")

    ok = (bool(accepte) and bool(refuse) and reproduits
          and len(imputables) == len(refuse))
    print("[287r5-los] VERDICT : %s" % ("OK" if ok else "FAUTES"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
