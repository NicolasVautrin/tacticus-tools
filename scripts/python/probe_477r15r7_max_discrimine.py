#!/usr/bin/env python3
"""#477-r15-r7 -- LES DEUX MAXIMUMS DISCRIMINENT-ILS ? Sortir du regime degenere.

    python probe_477r15r7_max_discrimine.py [--session N] [--board MC1_67]
                                            [--p-units ...] [--a-units ...]
                                            [--tours 12]

CE QU'IL MESURE, ET POURQUOI IL EXISTE
--------------------------------------
`probe_477r15a_stream_conformance.py` confronte le flux du groupe `System_GameSetup`. Deux de ses
tags lisent un `IdunBattle.Entities.Components.FillUpStatComponent` par son ACCESSEUR :

    Tag=UnitStats_MaxHealth  (9)   <- `FillUpStatComponent$$get_CurrentMaximumValue()` (sante)
    Tag=UnitStats_MaxArmor  (13)   <- le meme accesseur, sur le composant d'ARMURE

Jusqu'a #477-r15-r7 le port ne les MESURAIT pas : il prenait `observeBattle.hpMax` / `.armorMax`,
c'est-a-dire le champ BRUT `MaximumValue(+0x14)` du meme composant. Les deux coincident au
deploiement PAR CONSTRUCTION, pas par chance -- l'accesseur vaut

    get_CurrentMaximumValue() = MaximumValue(+0x14)
                                + clamp(Modification(+0x28), -Initial(+0x10), IntMax - Initial)

(ou l'override de `IdunBattle.Entities.Components.ValueOverride$$GetOverrideValueWithModification`
lu en `+0x38`, quand il en porte un), et ces deux termes sont NULS tant qu'aucune operation n'est
intercalee. Un accord dans ce regime est donc vide de sens (doctrine du depot : « accord en regime
DEGENERE = zero preuve »).

Ce probe-ci etablit le cran DU DESSOUS : que les deux canaux sont deux LECTURES DISTINCTES, qui
SE SEPARENT des que l'etat les separe. Sans lui, `combatSnapshot.healthMax` / `.armorMax`
pourraient etre des alias du champ brut et personne ne le verrait -- l'egalite du flux resterait
verte a l'identique.

LE MONTAGE POUR LA SANTE, ET POURQUOI CELUI-LA
----------------------------------------------
Il faut une unite dont le MAXIMUM de PV bouge en cours de bataille. Le vecteur est nomme par son
propre texte de kit (`gameconfig.py ability TwistedScience`) :

    « Units healed by Hollan, other than himself, are affected by Twisted Science until they are
      defeated. Hollan can heal other unaffected units EVEN IF THEY ARE AT FULL HEALTH. Affected
      units immediately gain 2183 Health and THEIR MAXIMUM HEALTH INCREASES BY THE SAME AMOUNT. »

Le porteur est `genesBiophagus` (Hollan), VERIFIE present dans `rl_duel build --list-pool`. Deux
proprietes rendent le montage atteignable sans coup de chance : le heal ne demande PAS que la
cible soit blessee, et l'effet est PERMANENT (jusqu'a la mort). On met donc Hollan avec des allies
de sa faction et on laisse l'IA jouer les deux camps.

⚠ CE N'EST PAS LA VALEUR 2183 QUI EST TESTEE ICI, c'est l'ECART entre deux lectures. Le probe ne
fitte aucun scalaire : il demande seulement `StatPart.Maximum != MaximumValue@0x14` au moins une
fois.

L'ARMURE N'A PAS DE VECTEUR CONNU, ET C'EST UN RESULTAT
-------------------------------------------------------
Aucun vecteur equivalent n'a ete trouve pour le pool d'ARMURE (`StatType.Armor` = 4, le
`FillUpStatComponent` d'armure). Ce qui a ete ELIMINE, et ce qui reste ouvert, est imprime par le
probe lui-meme en fin de run -- pas laisse a la memoire du lecteur. Le verdict de l'armure est
donc attendu NON DISCRIMINE, et il est rendu AVEC SES TEMOINS (combien d'unites portaient une
armure non nulle, sur combien de tours). Un NON DISCRIMINE n'est pas un echec : c'est la borne du
corpus, dite au lieu d'etre tue.

⚠ TEMOIN DU TEMOIN : une grandeur qui vaut ZERO partout est egale des deux cotes quoi qu'on lise.
Le probe compte donc les unites a valeur NON NULLE, par grandeur, et refuse de rendre
« NON DISCRIMINE » comme un constat sur le canal quand le corpus n'a rien a montrer.

⚠ EXIGE LE CAPTEUR #477-r15-r7 (`combatSnapshot.armorMax`) pour le volet ARMURE, donc une fenetre
de reinject. Sans lui le volet armure rend MESURE IMPOSSIBLE et le NOMME -- il ne retombe pas sur
`observeBattle.armorMax`, ce qui produirait exactement l'alias qu'il doit pouvoir refuter. Le
volet SANTE, lui, n'exige AUCUN capteur neuf (`combatSnapshot.healthMax` existe depuis #45b') et
se joue donc sans fenetre.

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

#: Hollan (`genesBiophagus`) porte `TwistedScience`, le seul vecteur MESURE de bump du MAXIMUM de
#: PV. On lui adjoint deux allies de sa faction : le texte du kit accorde +364 de degat aux
#: unites Genestealer Cults affectees, donc l'IA a une raison de les cibler en priorite. Les trois
#: `unitId` sont VERIFIES presents dans `rl_duel build --list-pool`.
P_UNITS_DEFAUT = "genesBiophagus,genesKelermorph,genesPrimus"
#: En face, des kits banals : ce cote-la n'a rien a prouver, il doit seulement faire durer la
#: bataille assez longtemps pour que Hollan agisse.
A_UNITS_DEFAUT = "blackTerminator,astraBullgryn"
#: Board LARGE : les deux camps doivent pouvoir se rejoindre en quelques tours.
BOARD_DEFAUT = "MC1_67"
SEED = 777

#: Ce que la recherche du vecteur ARMURE a ELIMINE. Imprime a chaque run : un « non trouve » qui
#: ne dit pas ou il a cherche ne vaut rien, et se relit comme une preuve d'inexistence.
PORTEE_RECHERCHE_ARMURE = (
    "les 558 `statType` du gameconfig sont les UPGRADES de meta-jeu (hp/dmg/fixedArmor), pas des "
    "stat-modifiers de combat -- ce canal ne conclut RIEN",
    "aucun site du port (`engine/**`) n'emet de `ChangeStat` sur `StatType.ARMOR` (4) ; les "
    "effets nommes `*_ExtraArmor` visent tous `StatType.FIXED_ARMOR` (16), qui est un "
    "`StatComponent`, pas le `FillUpStatComponent` d'armure",
    "RESTE OUVERT : le port ne couvre qu'une partie des abilities natives -- un "
    "`CreateBehaviour` non porte peut appeler `FillUpStatComponent$$ModifyMax`/`OverrideMax` sur "
    "l'armure sans que rien du depot ne le montre",
)


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


def lire_maximums(session: int, rid: int, exiger_armure: bool) -> list[dict]:
    """Les DEUX lectures de CHAQUE maximum, pour chaque unite vivante, en TRI-ETAT STRICT.

    `effectif` = `combatSnapshot.<x>Max` = `GetStat(unit, <StatType>, StatPart.Maximum)`
                 -> `FillUpStatComponent$$GetStatPart` case 2 = `get_CurrentMaximumValue()`
    `brut`     = `observeBattle.<x>Max` = champ `MaximumValue(+0x14)` lu par le projecteur
                 (`frida/hooks/game/match-state.ts::projectSquadStats`)

    Un `healthMax`/`armorMax` a `null` cote `combatSnapshot` fait LEVER : c'est le capteur qui
    n'a pas parle, et le rabattre sur la lecture brute fabriquerait l'egalite que ce probe doit
    pouvoir refuter."""
    cs = rpc(session, "combatSnapshot", {"runnerId": rid})
    obs = rpc(session, "observeBattle", {"runnerId": rid})
    par_obs = {}
    for u in (obs.get("units") or []):
        if u.get("squadId") is not None:
            par_obs[int(u["squadId"])] = u
    unites = cs.get("units")
    if unites is None:
        raise MesureImpossible("combatSnapshot ne rend aucune unite")
    if not par_obs:
        raise MesureImpossible("observeBattle ne rend aucune unite avec un `squadId`")
    out = []
    for u in unites:
        eid = u.get("entityId")
        if eid is None or int(eid) not in par_obs:
            continue                    # entite hors du projecteur (Machine, p.ex.) -- ignoree
        o = par_obs[int(eid)]
        if "healthMax" not in u:
            raise MesureImpossible(
                "combatSnapshot ne publie pas `healthMax` -- capteur #45b' absent (bundle "
                "tres anterieur)")
        if exiger_armure and "armorMax" not in u:
            raise MesureImpossible(
                "combatSnapshot ne publie pas `armorMax` -- capteur #477-r15-r7 absent "
                "(bundle anterieur a la fenetre de reinject)")
        ligne = {"entityId": int(eid)}
        for nom, cle_cs, cle_obs in (("sante", "healthMax", "hpMax"),
                                     ("armure", "armorMax", "armorMax")):
            eff, brut = u.get(cle_cs), o.get(cle_obs)
            # `null` d'un cote OU de l'autre = PAS MESURE sur cette entite : ni accord, ni
            # desaccord. C'est le regime des Machines of War, que `GetStat` refuse pour ces
            # `StatType` (2e liste du switch de garde, `EntityType.Unit` exige).
            ligne[nom] = (None if eff is None or brut is None
                          else {"effectif": int(eff), "brut": int(brut)})
        out.append(ligne)
    return out


def _verdict(nom: str, ecarts: list, non_nuls: set, vues: set, tours: int,
             exercable: bool) -> tuple:
    """Rend `(rc_partiel, lignes)` -- TROIS etats, et le troisieme distingue deux causes."""
    lignes = []
    if ecarts:
        lignes.append("  %-7s DISCRIMINE : les deux lectures SE SEPARENT (%d observation(s)). "
                      "`StatPart.Maximum` n'est donc pas un alias de `MaximumValue@0x14`."
                      % (nom.upper(), len(ecarts)))
        for e in ecarts[:6]:
            lignes.append("      tour %-3d entite %-5s effectif=%d brut=%d (delta %+d)"
                          % (e["tour"], e["entityId"], e["effectif"], e["brut"],
                             e["effectif"] - e["brut"]))
        return 0, lignes
    if not exercable:
        lignes.append("  %-7s NON DISCRIMINE -- ET LE CORPUS NE POUVAIT PAS L'ETRE : la grandeur "
                      "vaut ZERO sur les %d entite(s) vues en %d tour(s). Deux zeros sont egaux "
                      "quelle que soit la lecture ; ce corpus ne teste AUCUN canal sur ce tag."
                      % (nom.upper(), len(vues), tours))
        return 3, lignes
    lignes.append("  %-7s NON DISCRIMINE : %d entite(s) portaient une valeur NON NULLE, mais "
                  "aucune n'a vu son maximum modifie en %d tour(s). Les deux canaux restent "
                  "indissocies SUR CE CORPUS -- c'est un resultat, pas un accord."
                  % (nom.upper(), len(non_nuls), tours))
    return 3, lignes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--board", default=BOARD_DEFAUT)
    ap.add_argument("--p-units", default=P_UNITS_DEFAUT)
    ap.add_argument("--a-units", default=A_UNITS_DEFAUT)
    ap.add_argument("--tours", type=int, default=12,
                    help="nombre de tours d'equipe joues par l'IA (les DEUX camps)")
    ap.add_argument("--sans-armure", action="store_true",
                    help="volet SANTE seul -- a jouer AVANT la fenetre de reinject, ou le "
                         "capteur `armorMax` n'existe pas encore")
    args = ap.parse_args()

    try:
        session = args.session if args.session is not None else session_courante()
    except MesureImpossible as e:
        print("[477-r15-r7] MESURE IMPOSSIBLE : %s" % e)
        return 2

    exiger_armure = not args.sans_armure
    print("[477-r15-r7] session=%d board=%s p=%s a=%s tours=%d armure=%s"
          % (session, args.board, args.p_units, args.a_units, args.tours,
             "OUI" if exiger_armure else "non (--sans-armure)"))
    state = OUT / ("state-477r15r7-%s.json" % args.board)
    state.parent.mkdir(parents=True, exist_ok=True)

    #: TEMOINS -- ce sont eux qui donnent son sens au verdict. Un « 0 ecart » sans eux se lirait
    #: comme un accord alors qu'il peut vouloir dire « rien n'a ete visite ».
    ecarts = {"sante": [], "armure": []}
    non_nuls = {"sante": set(), "armure": set()}
    vues = {"sante": set(), "armure": set()}
    tours_joues = 0

    def absorber(pas: int) -> None:
        for m in lire_maximums(session, rid, exiger_armure):
            for nom in ("sante", "armure"):
                v = m.get(nom)
                if v is None:
                    continue            # PAS MESURE sur cette entite
                vues[nom].add(m["entityId"])
                if v["effectif"] != 0 or v["brut"] != 0:
                    non_nuls[nom].add(m["entityId"])
                if v["effectif"] != v["brut"]:
                    ecarts[nom].append({"tour": pas, "entityId": m["entityId"], **v})

    try:
        rid = build(args.board, state, args.p_units, args.a_units)
        print("  runner %d monte" % rid)
        for pas in range(args.tours):
            absorber(pas)
            r = rpc(session, "aiPlayByUnit", {"runnerId": rid, "maxTurns": 1})
            tours_joues += 1
            if r.get("ok") is False:
                print("  arret au tour %d : %s" % (pas, r.get("error")))
                break
            if r.get("finished") or r.get("winner") is not None:
                print("  bataille terminee au tour %d (winner=%s)" % (pas, r.get("winner")))
                break
        # Derniere lecture APRES le dernier tour joue -- sans elle, l'effet du tour final serait
        # invisible, et c'est justement le tour ou l'ecart a le plus de chances d'exister.
        absorber(tours_joues)
    except MesureImpossible as e:
        print("[477-r15-r7] MESURE IMPOSSIBLE : %s" % e)
        dispose(state)
        return 2
    finally:
        dispose(state)

    print("")
    print("=== TEMOINS (sans eux, un zero ne veut rien dire) ===")
    print("  tours d'equipe joues                    : %d" % tours_joues)
    for nom in ("sante", "armure"):
        print("  %-7s entites avec les DEUX lectures  : %-3d  dont valeur non nulle : %d"
              % (nom, len(vues[nom]), len(non_nuls[nom])))

    print("")
    print("=== VERDICT (3 etats, PAR GRANDEUR) ===")
    rc = 0
    grandeurs = ("sante",) if args.sans_armure else ("sante", "armure")
    for nom in grandeurs:
        partiel, lignes = _verdict(nom, ecarts[nom], non_nuls[nom], vues[nom], tours_joues,
                                   bool(non_nuls[nom]))
        for ligne in lignes:
            print(ligne)
        rc = max(rc, partiel)
    if args.sans_armure:
        print("  ARMURE  NON JOUEE (--sans-armure) : le capteur #477-r15-r7 n'est pas dans le "
              "bundle charge. Ce n'est PAS un verdict sur le canal.")
        rc = max(rc, 3)

    print("")
    print("=== PORTEE DE LA RECHERCHE DU VECTEUR ARMURE ===")
    for ligne in PORTEE_RECHERCHE_ARMURE:
        print("  - %s" % ligne)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
