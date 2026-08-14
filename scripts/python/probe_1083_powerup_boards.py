"""probe #1083 -- quels boards du disque PLACENT une unite `powup*`, et sous quel MODE ?

Mesure l'axe de confrontabilite des passifs `PowerUp_*` : ce ne sont PAS des passifs
portes par une unite du POOL, ce sont des power-ups de TERRAIN poses par le BOARD
(cf. `docs/rl/npc-registry.md`, categorie `tile`). Leur gate de confrontabilite est
donc `rl_duel build --board <id>`, pas `--list-pool`.

Voie exacte, LUE dans les fichiers (pas devinee) :
    board.SpawnPointSets[i].GameModeTiles[j].PowerUpUnits[k].UnitId

`GameModeTiles[j]` porte un champ `Mode` : le power-up n'est pose que si la bataille
tourne dans CE mode. Un board qui NOMME un `powup*` ne le POSE donc pas
necessairement dans le mode ou nos runners tournent -- ce probe ventile par mode.

DEUX PIEGES DE MESURE, tous deux mesures ici plutot que redoutes :
  1. chercher `powerUp|powup|ActivationTile` d'un bloc gonfle le compte -- les signaux
     voisins (`DoorActivationTiles`, `TileEffectSpawnPoints`) ne comptent pas la meme
     chose. Ils sont comptes SEPAREMENT ci-dessous, jamais OU-es.
  2. `Path.stem` n'identifie PAS un board : `data/boards/` a trois sous-dossiers
     (global/pvp/syncPvp) et les noms y collisionnent. L'identifiant est le chemin
     RELATIF. Sans ca, le compte de boards est sous-evalue et les comptes par unite
     depassent le total (symptome observe : 36 boards mais 64 pour powupDamage).

Usage :
    python probe_1083_powerup_boards.py                 # ventilation complete
    python probe_1083_powerup_boards.py --json
    python probe_1083_powerup_boards.py --for powupHits # boards qui posent cette unite
    python probe_1083_powerup_boards.py --mode Campaign # filtre sur un Mode
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

_RACINE = Path(__file__).resolve().parents[2]
_BOARDS = _RACINE / "data" / "boards"

_RE_POWUP = re.compile(r"powup[A-Za-z0-9_]*")

# Signaux VOISINS -- mesures a part pour montrer qu'ils ne comptent pas la meme chose.
_VOISINS = ("DoorActivationTiles", "TileEffectSpawnPoints", "TerritoryTiles",
            "Player0SummonTiles", "Player1SummonTiles")


def _boards():
    for chemin in sorted(_BOARDS.rglob("*.json")):
        # identifiant = chemin RELATIF (les stems collisionnent entre sous-dossiers)
        yield chemin.relative_to(_BOARDS).as_posix()[:-len(".json")], chemin


def _compte_voisin(valeur) -> int:
    if isinstance(valeur, (list, dict)):
        return 1 if valeur else 0
    return 0


def mesurer():
    total = 0
    # (board_rel) -> {unite -> set(modes)}
    place_par_board: dict[str, dict[str, set]] = {}
    par_unite: dict[str, set] = defaultdict(set)
    par_unite_mode: dict[tuple, set] = defaultdict(set)
    modes = Counter()
    temoin_voisins = Counter()
    # boards qui NOMMENT un powup ailleurs que dans PowerUpUnits (controle : doit rester vide)
    hors_voie: dict[str, list] = {}

    for board_id, chemin in _boards():
        total += 1
        brut = chemin.read_text(encoding="utf-8")
        try:
            donnee = json.loads(brut)
        except Exception:
            continue
        board = donnee.get("board") or {}

        vus_par_la_voie: set = set()
        for sps in board.get("SpawnPointSets") or []:
            if not isinstance(sps, dict):
                continue
            for voisin in _VOISINS:
                temoin_voisins[voisin] += _compte_voisin(sps.get(voisin))
            for gmt in sps.get("GameModeTiles") or []:
                if not isinstance(gmt, dict):
                    continue
                mode = gmt.get("Mode")
                for voisin in _VOISINS:
                    temoin_voisins[voisin] += _compte_voisin(gmt.get(voisin))
                for pu in gmt.get("PowerUpUnits") or []:
                    if not isinstance(pu, dict):
                        continue
                    unite = pu.get("UnitId")
                    if not unite:
                        continue
                    vus_par_la_voie.add(unite)
                    place_par_board.setdefault(board_id, {}).setdefault(unite, set()).add(mode)
                    par_unite[unite].add(board_id)
                    par_unite_mode[(unite, mode)].add(board_id)
                    modes[mode] += 1

        # controle : tout `powup*` du texte brut doit avoir ete vu par la voie structuree
        bruts = set(_RE_POWUP.findall(brut))
        manquants = bruts - vus_par_la_voie
        if manquants:
            hors_voie[board_id] = sorted(manquants)

    return {
        "total_boards": total,
        "place_par_board": place_par_board,
        "par_unite": {k: sorted(v) for k, v in par_unite.items()},
        "par_unite_mode": {"%s|%s" % (u, m): sorted(v) for (u, m), v in par_unite_mode.items()},
        "modes": modes,
        "temoin_voisins": temoin_voisins,
        "hors_voie": hors_voie,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--for", dest="pour", default=None)
    ap.add_argument("--mode", default=None)
    args = ap.parse_args()

    if not _BOARDS.is_dir():
        print("[1083] data/boards absent -- `python dump_boards.py` pour le regenerer")
        return 2

    m = mesurer()

    if args.pour:
        retenus = []
        for board_id, unites in sorted(m["place_par_board"].items()):
            if args.pour not in unites:
                continue
            modes = unites[args.pour]
            if args.mode and args.mode not in modes:
                continue
            retenus.append((board_id, sorted(str(x) for x in modes)))
        if args.json:
            print(json.dumps([{"board": b, "modes": md} for b, md in retenus], indent=2))
        else:
            print("[1083] %s%s : %d board(s)"
                  % (args.pour, (" mode=%s" % args.mode) if args.mode else "", len(retenus)))
            for b, md in retenus:
                print("   %-44s modes=%s" % (b, ",".join(md)))
        return 0 if retenus else 1

    if args.json:
        print(json.dumps({
            "total_boards": m["total_boards"],
            "boards_qui_posent": len(m["place_par_board"]),
            "unites": {k: len(v) for k, v in m["par_unite"].items()},
            "par_unite": m["par_unite"],
            "par_unite_mode": {k: len(v) for k, v in m["par_unite_mode"].items()},
            "modes": dict(m["modes"]),
            "hors_voie": m["hors_voie"],
        }, indent=2))
        return 0

    print("[1083] boards balayes : %d" % m["total_boards"])
    print("[1083] boards qui POSENT au moins un `powup*` (voie "
          "board.SpawnPointSets[].GameModeTiles[].PowerUpUnits[].UnitId) : %d"
          % len(m["place_par_board"]))
    print("[1083] unites `powup*` NOMMEES par au moins un board : %d" % len(m["par_unite"]))
    for nom, boards in sorted(m["par_unite"].items(), key=lambda kv: -len(kv[1])):
        detail = []
        for cle, bs in sorted(m["par_unite_mode"].items()):
            u, _, mode = cle.partition("|")
            if u == nom:
                detail.append("%s=%d" % (mode, len(bs)))
        print("   %-20s %4d board(s)   par mode: %s" % (nom, len(boards), " ".join(detail)))
    print("[1083] Mode des GameModeTiles porteurs (occurrences) : %s"
          % ", ".join("%s=%d" % (k, v) for k, v in m["modes"].most_common()))
    print("[1083] CONTROLE -- boards nommant un `powup*` HORS de cette voie : %d %s"
          % (len(m["hors_voie"]), sorted(m["hors_voie"])[:5] if m["hors_voie"] else ""))
    print("[1083] TEMOIN -- signaux VOISINS, comptes SEPAREMENT (jamais OU-es) :")
    for voisin in _VOISINS:
        print("   %-24s non vide %5d fois" % (voisin, m["temoin_voisins"].get(voisin, 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
