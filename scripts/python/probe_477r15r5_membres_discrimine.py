#!/usr/bin/env python3
"""#477-r15-r5 -- LE CANAL DES MEMBRES DISCRIMINE-T-IL ? Sortir du regime degenere.

    python probe_477r15r5_membres_discrimine.py [--session N] [--board MC1_67]
                                                [--p-units ...] [--a-units ...]
                                                [--tours 12]

CE QU'IL MESURE, ET POURQUOI IL EXISTE
--------------------------------------
`probe_477r15a_stream_conformance.py` confronte le flux du groupe `System_GameSetup`. Deux de
ses tags lisent LE MEME composant par DEUX accesseurs differents de
`IdunBattle.Entities.Components.FillUpStatComponent` :

    Tag=UnitStats_InitAliveMembers (4)   <- champ BRUT `RemainingValue(+0x18)`
    Tag=UnitStats_MaxMembers      (17)   <- `FillUpStatComponent$$get_CurrentMaximumValue()`

⚠ AU DEPLOIEMENT LES DEUX VALENT LA MEME CHOSE -- aucun membre n'est mort, aucune modification
n'est posee. Le flux ne peut donc PAS les separer, quel que soit le canal : c'est une propriete
du REGIME `System_GameSetup`, pas du port. Un accord y est vide de sens (doctrine du depot :
« accord en regime DEGENERE = zero preuve »).

Ce que ce probe-ci etablit est le cran DU DESSOUS, et il est atteignable : que les deux CANAUX
publies par `combatSnapshot` sont deux LECTURES DISTINCTES, qui SE SEPARENT des que l'etat les
separe. Sans lui, `numberOfMembersMax` pourrait etre un alias de `stats.numberOfMembers` et
personne ne le verrait -- l'egalite du flux resterait verte a l'identique.

    stats.numberOfMembers  = GetStat(unit, NumberOfMembers, StatPart.Current)
                             -> `FillUpStatComponent$$GetStatPart` case 0 = `*(int*)(this+0x18)`
    numberOfMembersMax     = GetStat(unit, NumberOfMembers, StatPart.Maximum)
                             -> case 2 = `get_CurrentMaximumValue()`

LE MONTAGE, ET POURQUOI CELUI-LA
--------------------------------
Il faut une unite a PLUSIEURS membres qui en PERD un. Mesure offline sur le gameconfig du build
`rnca9r7q6c` : **17** configurations portent `nrOfMembers > 1`, et **toutes** sont des `summons`
ou des `npc` -- AUCUN heros, AUCUNE Machine of War. La gate de confrontabilite du depot tranche
alors : un summon compte, on l'amene en bataille en spawnant son SUMMONER.

    necroSpyder   (Aleph-Null, pool)  --ScarabHive-->  necroSmnSwarm        (5 membres)
    tyranParasite (Parasite,  pool)   --ItItches----->  tyranSmnRipperSwarm  (5 membres)

Les deux summoners sont dans `rl_duel build --list-pool` (verifie). On les met des DEUX cotes et
on laisse l'IA jouer les deux camps (`aiPlayByUnit` pilote le `currentTurnPlayer`, quel qu'il
soit) : les summons apparaissent, le combat les use, et on relit `combatSnapshot` a chaque tour.

⚠ ON N'ATTEND PAS DE L'IA QU'ELLE COOPERE. Le verdict est a TROIS etats et le troisieme est un
RESULTAT : si aucun summon multi-membres n'a perdu de membre, le probe le DIT (avec ses temoins
-- combien d'unites multi-membres vues, sur combien de tours) au lieu de rendre un vert. C'est
le meme choix que la borne (c) du probe frere : non mesure != egal.

⚠ EXIGE LE CAPTEUR #477-r15-r5 (`combatSnapshot.numberOfMembersMax`), donc une fenetre de
reinject. Sans lui, le probe rend MESURE IMPOSSIBLE et le NOMME -- il ne retombe pas sur
`stats.numberOfMembers`, ce qui produirait exactement l'alias qu'il est charge de refuter.

DISCIPLINE : un runner a la fois, dispose dans le `finally`, state-file sous `logs/`.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ROOT = HERE.parents[1]
OUT = ROOT / "logs"
HOST = "http://127.0.0.1:8765"

#: Les deux summoners de summons multi-membres qui sont AU POOL (mesure du gameconfig
#: `rnca9r7q6c` croisee avec `rl_duel build --list-pool`). Un de chaque cote : chaque camp a
#: alors une chance de sortir son swarm, et chaque swarm une chance de se faire user.
#: (Les quatre `unitId` sont VERIFIES presents dans `--list-pool` -- `ultraInceptorSgt` et non
#: `ultraInceptor`, qui n'y est pas : un roster faux ferait echouer le build, pas la mesure.)
P_UNITS_DEFAUT = "necroSpyder,ultraInceptorSgt"
A_UNITS_DEFAUT = "tyranParasite,blackTerminator"
#: Board LARGE : les deux camps doivent pouvoir se rejoindre en quelques tours.
BOARD_DEFAUT = "MC1_67"
SEED = 777


class MesureImpossible(RuntimeError):
    """Une source manque -- on le DIT, on ne rend pas un verdict."""


def rpc(session: int, method: str, args: dict, timeout: int = 180) -> dict:
    body = json.dumps({"method": method, "args": [args], "timeout": 150000}).encode()
    req = urllib.request.Request("%s/api/scripts/%d/rpc" % (HOST, session), data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()).get("result") or {}
    except (urllib.error.URLError, OSError) as e:
        raise MesureImpossible("RPC %s injoignable : %s" % (method, e)) from e


def session_courante() -> int:
    try:
        with urllib.request.urlopen("%s/api/admin/status" % HOST, timeout=10) as r:
            st = json.loads(r.read().decode())
    except (urllib.error.URLError, OSError) as e:
        raise MesureImpossible("host injoignable : %s" % e) from e
    sid = ((st.get("session") or {}).get("id"))
    if sid is None:
        raise MesureImpossible("aucune session Frida vivante")
    return int(sid)


def build(board: str, state_file: Path, p_units: str, a_units: str) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(SEED), "--board", board,
           "--p-units", p_units, "--a-units", a_units,
           "--no-ai", "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    if not state_file.is_file():
        raise MesureImpossible("build %s echoue : %s" % (board, (p.stderr or p.stdout)[-500:]))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def dispose(state_file: Path) -> None:
    subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state_file)],
                   cwd=str(HERE), capture_output=True, text=True, timeout=180)


def lire_membres(session: int, rid: int) -> list[dict]:
    """`{entityId, courant, maximum}` de CHAQUE unite vivante, en TRI-ETAT STRICT.

    Un `numberOfMembersMax` a `null` fait LEVER : c'est le capteur qui n'a pas parle, et le
    rabattre sur `stats.numberOfMembers` fabriquerait l'egalite que ce probe doit pouvoir
    refuter."""
    rep = rpc(session, "combatSnapshot", {"runnerId": rid})
    unites = rep.get("units")
    if unites is None:
        raise MesureImpossible("combatSnapshot ne rend aucune unite")
    out = []
    for u in unites:
        stats = u.get("stats") or {}
        if "numberOfMembersMax" not in u:
            raise MesureImpossible(
                "combatSnapshot ne publie pas `numberOfMembersMax` -- capteur #477-r15-r5 "
                "absent (bundle anterieur a la fenetre de reinject)")
        courant, maximum = stats.get("numberOfMembers"), u.get("numberOfMembersMax")
        if courant is None or maximum is None:
            continue                    # PAS MESURE sur cette entite (Machine, p.ex.) -- ni
            #                             compte comme accord, ni comme desaccord.
        out.append({"entityId": u.get("entityId"), "courant": int(courant),
                    "maximum": int(maximum)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--board", default=BOARD_DEFAUT)
    ap.add_argument("--p-units", default=P_UNITS_DEFAUT)
    ap.add_argument("--a-units", default=A_UNITS_DEFAUT)
    ap.add_argument("--tours", type=int, default=12,
                    help="nombre de tours d'equipe joues par l'IA (les DEUX camps)")
    args = ap.parse_args()

    try:
        session = args.session if args.session is not None else session_courante()
    except MesureImpossible as e:
        print("[477-r15-r5] MESURE IMPOSSIBLE : %s" % e)
        return 2

    print("[477-r15-r5] session=%d board=%s p=%s a=%s tours=%d"
          % (session, args.board, args.p_units, args.a_units, args.tours))
    state = OUT / ("state-477r15r5-%s.json" % args.board)
    state.parent.mkdir(parents=True, exist_ok=True)

    #: TEMOINS -- ce sont eux qui donnent son sens au verdict. Un « 0 divergence » sans eux se
    #: lirait comme un accord alors qu'il peut vouloir dire « rien n'a ete visite ».
    multi_vus: set = set()          # entites dont le MAXIMUM est > 1 (les seules separables)
    separees: list[dict] = []       # entites ou courant < maximum, au moins une fois
    tours_joues = 0
    unites_vues: set = set()

    try:
        rid = build(args.board, state, args.p_units, args.a_units)
        print("  runner %d monte" % rid)
        for pas in range(args.tours):
            for m in lire_membres(session, rid):
                unites_vues.add(m["entityId"])
                if m["maximum"] > 1:
                    multi_vus.add(m["entityId"])
                if m["courant"] != m["maximum"]:
                    separees.append({"tour": pas, **m})
            r = rpc(session, "aiPlayByUnit", {"runnerId": rid, "maxTurns": 1})
            tours_joues += 1
            if r.get("ok") is False:
                print("  arret au tour %d : %s" % (pas, r.get("error")))
                break
            if r.get("finished") or r.get("winner") is not None:
                print("  bataille terminee au tour %d (winner=%s)" % (pas, r.get("winner")))
                break
        # Derniere lecture APRES le dernier tour joue -- sans elle, l'effet du tour final
        # serait invisible.
        for m in lire_membres(session, rid):
            unites_vues.add(m["entityId"])
            if m["maximum"] > 1:
                multi_vus.add(m["entityId"])
            if m["courant"] != m["maximum"]:
                separees.append({"tour": tours_joues, **m})
    except MesureImpossible as e:
        print("[477-r15-r5] MESURE IMPOSSIBLE : %s" % e)
        dispose(state)
        return 2
    finally:
        dispose(state)

    print("")
    print("=== TEMOINS (sans eux, un zero ne veut rien dire) ===")
    print("  tours d'equipe joues                    : %d" % tours_joues)
    print("  entites vues avec les deux lectures     : %d" % len(unites_vues))
    print("  entites a PLUSIEURS membres (max > 1)   : %d %s"
          % (len(multi_vus), sorted(multi_vus)))
    print("  observations ou courant != maximum      : %d" % len(separees))
    for s in separees[:10]:
        print("      tour %-3d entite %-5s courant=%d maximum=%d"
              % (s["tour"], s["entityId"], s["courant"], s["maximum"]))

    print("")
    print("=== VERDICT (3 etats) ===")
    if separees:
        print("  DISCRIMINE : les deux lectures SE SEPARENT (%d observation(s)). "
              "`numberOfMembersMax` n'est donc pas un alias de `stats.numberOfMembers`, et "
              "l'accord mesure par probe_477r15a sur `UnitStats_MaxMembers` porte sur deux "
              "canaux reellement distincts." % len(separees))
        return 0
    if not multi_vus:
        print("  NON DISCRIMINE -- ET LE CORPUS NE POUVAIT PAS L'ETRE : aucune entite a "
              "plusieurs membres n'est apparue en %d tour(s). Les summons multi-membres "
              "dependent d'un cast de leur summoner, que l'IA n'est pas tenue de faire. "
              "Relancer avec plus de --tours, ou un autre board/roster." % tours_joues)
        return 3
    print("  NON DISCRIMINE : %d entite(s) a plusieurs membres ont ete vues, mais aucune n'a "
          "perdu de membre en %d tour(s). Les deux canaux restent indissocies SUR CE CORPUS -- "
          "c'est un resultat, pas un accord." % (len(multi_vus), tours_joues))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
