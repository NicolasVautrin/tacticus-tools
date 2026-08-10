"""Capte le pool ELIGIBLE a UNE operation, depuis son ecran de dispatch.

⚠ CE N'EST PAS UN ROSTER, ET LA MESURE L'A TRANCHE. Cet outil a d'abord ete presente
comme un capteur de roster : c'etait faux. L'ecran annonce 51 Imperial eligibles la ou
`UnitProgression$$HasUnitUnlocked` en compte 49 possedes -- les deux ne mesurent pas la
meme chose. L'eligibilite melange possession, alliance, rarete et niveau, et elle est
PROPRE A L'OPERATION : deux operations Imperial du meme plateau rendent 32 et 34
eligibles la ou une troisieme en montrait 51.

  - Pour le ROSTER POSSEDE (toutes alliances, sans ecran ni defilement) : RPC
    `rosterOwned` du module `frida/hooks/features/roster-owned.ts`, qui pose la question
    au jeu unite par unite et se recoupe avec `AmountOfUnlockedUnits()`.
  - Pour l'ELIGIBILITE d'une operation precise : cet outil, ou le RPC
    `expeditionEligibility` (qui en rend le COMPTE pour toutes les operations rendues).

Ce qui suit reste vrai, et l'outil garde son usage -- il repond a << qui peut partir sur
CETTE operation >>, pas a << que possede le joueur >>.


POURQUOI CE N'EST PAS UN FICHIER, ET POURQUOI C'EST UN OUTIL SEPARE.

Un roster stocke PERIME EN SILENCE : tu debloques un personnage, le solveur continue
de raisonner sur l'ancien pool et rend un plan valide-en-apparence qui rate la
meilleure solution, sans rien signaler. Comme la capture ne coute qu'un `uiList`, la
re-derivation est toujours preferable a la conservation. Cet outil IMPRIME, il
n'ecrit rien.

Et il est SEPARE de `expedition_solver.py` a dessein : le solveur est 100 % hors
ligne (aucune session Frida), et c'est une propriete qu'on ne veut pas perdre. La
composition se fait par la ligne de commande, `--roster` acceptant aussi bien un
chemin qu'une liste litterale :

    python scripts/python/expedition_roster.py > /tmp/pool.txt
    python scripts/python/expedition_solver.py solve --roster /tmp/pool.txt ...

    # ou, sans fichier du tout (PowerShell) :
    $pool = python scripts/python/expedition_roster.py
    python scripts/python/expedition_solver.py solve --roster $pool ...

SEPARATION DES FLUX : stdout ne porte QUE les identifiants, pour que la composition
marche. Tout le reste -- comptes, qualification, avertissements -- part sur stderr.

CE QUE LA CAPTURE VAUT, ET CE QU'ELLE NE VAUT PAS (mesure du 2026-08-10, session 34)

  - Les portraits ACTIFS sont les personnages dispatchables : 51 releves.
  - Les portraits INACTIFS ne sont PAS un roster : `uiListAll --inclureInactifs` en
    rend 127, soit EXACTEMENT le nombre de kits `lineup` du gameconfig. La grille
    instancie tout le catalogue et n'active que les eligibles. Prendre les inactifs
    pour une collection rendrait un pool faux de 76 unites.
  - Le pool est SCOPE PAR L'OPERATION ouverte (son `grandAlliance`). Un ecran d'une
    operation Imperial ne dit RIEN des Chaos/Xenos.
  - Les MACHINES OF WAR sont exclues STRUCTURELLEMENT : sur les 4 MoW Imperial du
    gameconfig, 0 etait active. Leur absence n'est donc pas un defaut de possession.

REFUS PLUTOT QUE VIDE. Si l'ecran courant n'est pas un ecran de dispatch, l'outil
REFUSE (rc != 0) au lieu d'imprimer une liste vide. Un zero silencieux se lirait
<< tu ne possedes rien >>, et c'est precisement le defaut que ce depot proscrit.
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, __file__.rsplit("expedition_roster.py", 1)[0] or ".")

from gamenav.transport import Hote  # noqa: E402

PREFIXE_PORTRAIT = "ButtonPortrait_"


def extraire(boutons: list[dict]) -> list[str]:
    """Identifiants des portraits, dedupliques et tries. Fonction PURE."""
    ids = {b.get("name", "")[len(PREFIXE_PORTRAIT):]
           for b in boutons
           if str(b.get("name", "")).startswith(PREFIXE_PORTRAIT)}
    return sorted(i for i in ids if i)


def qualifier(ids: list[str], kits: dict | None) -> dict:
    """Croise le pool capte avec le gameconfig. Rend un verdict AUDITABLE.

    `kits` a None = gameconfig NON LU : la qualification est alors annoncee comme
    NON MESUREE, jamais rabattue sur << rien a signaler >>."""
    v: dict = {"n": len(ids), "vide": not ids}
    if kits is None:
        v["qualification"] = None
        return v
    connus = [i for i in ids if i in kits]
    v["inconnus"] = [i for i in ids if i not in kits]
    alliances: dict[str, int] = {}
    for i in connus:
        a = kits[i].get("alliance") or "?"
        alliances[a] = alliances.get(a, 0) + 1
    v["alliances"] = alliances
    v["mow_captees"] = [i for i in connus
                        if "MachineOfWar" in (kits[i].get("traits") or [])]
    # Ce que le gameconfig connait pour les alliances CAPTEES, donc ce qui manque.
    portee = {a for a in alliances}
    v["absents_de_la_capture"] = sorted(
        i for i, k in kits.items()
        if k.get("alliance") in portee and i not in ids)
    v["qualification"] = True
    return v


def _kits_ou_none() -> dict | None:
    try:
        import unit_map
        return {k["id"]: k for k in unit_map.all_kits() if k.get("kind") == "lineup"}
    except Exception as ex:                                            # noqa: BLE001
        print("gameconfig NON LU (%s) -- qualification indisponible" % str(ex)[:80],
              file=sys.stderr)
        return None


def _ouvrir_dispatch(h: Hote) -> str | None:
    """Tente d'ouvrir un ecran de dispatch. Rend un motif de refus, ou None si OK.

    ⚠ Ce geste DEPLACE l'UI du jeu : on demande d'abord a `Hote.calme()` s'il est
    licite de bouger. Un runner vivant appartient a quelqu'un qui valide."""
    motif = h.calme()
    if motif:
        return "refus de deplacer l'UI : %s" % motif
    r = h.rpc("uiList", [{}]) or {}
    chemins = [b.get("path") for b in (r.get("buttons") or [])
               if b.get("name") == "button_dispatch"]
    if not chemins:
        return ("aucun `button_dispatch` sur l'ecran courant -- ouvre l'ecran "
                "Operations (Crusade -> Operations) d'abord")
    # Les exemplaires partagent un chemin : ce sont des widgets POOLES et la
    # plupart sont recycles (donnee liee morte -> `onClick.Invoke threw`). On
    # essaie donc chaque index et on dit lequel a mordu.
    for i in range(len(chemins)):
        rep = h.rpc("uiClick", [{"path": chemins[0], "index": i}]) or {}
        if rep.get("ok"):
            print("ecran de dispatch ouvert (exemplaire %d sur %d ; les autres sont "
                  "des widgets recycles)" % (i, len(chemins)), file=sys.stderr)
            return None
    return ("aucun des %d exemplaires de `button_dispatch` n'a repondu -- "
            "ouvre l'ecran a la main" % len(chemins))


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="expedition_roster",
        description="Imprime les identifiants dispatchables lus sur l'ecran de "
                    "dispatch d'une Operation. N'ECRIT RIEN : la fraicheur vaut "
                    "mieux que la conservation.")
    p.add_argument("--ouvrir", action="store_true",
                   help="tente d'ouvrir un ecran de dispatch (DEPLACE l'UI ; refuse "
                        "si des runners sont vivants). Jamais de dispatch reel.")
    p.add_argument("--format", choices=("liste", "lignes", "json"), default="liste")
    p.add_argument("--sans-qualification", action="store_true",
                   help="ne pas lire le gameconfig (plus rapide, moins bavard)")
    a = p.parse_args(argv)

    h = Hote()
    if h.session() is None:
        print("REFUS : session Frida NON MESUREE (host injoignable ou aucune "
              "session vivante). Rien n'est imprime -- une liste vide se lirait "
              "comme un roster vide.", file=sys.stderr)
        return 2

    if a.ouvrir:
        motif = _ouvrir_dispatch(h)
        if motif:
            print("REFUS : %s" % motif, file=sys.stderr)
            return 3

    r = h.rpc("uiList", [{}]) or {}
    ids = extraire(r.get("buttons") or [])
    kits = None if a.sans_qualification else _kits_ou_none()
    v = qualifier(ids, kits)

    if v["vide"]:
        print("REFUS : aucun portrait sur l'ecran courant -- ce n'est pas un ecran "
              "de dispatch d'Operation. Relance avec --ouvrir, ou navigue a la main "
              "(Crusade -> Operations -> Dispatch).", file=sys.stderr)
        return 3

    print("%d personnage(s) dispatchable(s)" % v["n"], file=sys.stderr)
    if v.get("qualification"):
        print("alliances presentes : %s" % v["alliances"], file=sys.stderr)
        if v["inconnus"]:
            print("ATTENTION -- %d id(s) absents du gameconfig : %s"
                  % (len(v["inconnus"]), ", ".join(v["inconnus"][:8])), file=sys.stderr)
        print("Machines of War captees : %d (exclusion structurelle attendue)"
              % len(v["mow_captees"]), file=sys.stderr)
        if v["absents_de_la_capture"]:
            print("absents de la capture, alliances captees : %s"
                  % ", ".join(v["absents_de_la_capture"]), file=sys.stderr)
        print("PORTEE : ce pool est SCOPE par l'operation ouverte -- il ne dit RIEN "
              "des autres alliances.", file=sys.stderr)

    if a.format == "json":
        print(json.dumps({"ids": ids, "qualification": v}, ensure_ascii=True, indent=2))
    elif a.format == "lignes":
        for i in ids:
            print(i)
    else:
        print(",".join(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
