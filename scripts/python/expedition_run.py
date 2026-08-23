"""Pipeline complet des Operations (Expeditions) : lire, resoudre, envoyer, confronter.

    python scripts/python/expedition_run.py              # plan seul, RIEN n'est envoye
    python scripts/python/expedition_run.py --envoyer    # plan PUIS envoi

L'ORDRE

  1. `expeditionDispatchArm`
  2. lire le plateau, le roster, les seuils
  3. resoudre hors ligne
  4. envoyer, en RE-ARMANT entre chaque
  5. confronter au plateau

⛔ ON NE PASSE PLUS PAR L'INTERFACE, ET CE N'EST PAS UNE OPTION. Il y avait ici une etape 2
<< afficher l'ecran d'Operations >>, qui sortait de l'ecran courant et y revenait a coups
d'`uiClick` -- avec tout ce que ca traine : le jeu devait etre sur l'accueil ou la carte
Crusade (sinon PANNE), il fallait armer AVANT de naviguer (l'ordre inverse laissait les
methodes ancrees deja tirees), et chaque clic devait etre valide par son EFFET parce que
`interactable` precede la fin de l'animation. Surtout, elle FAISAIT DISPARAITRE L'UI du
joueur.

Elle a ete SUPPRIMEE, pas rendue facultative : les hooks lisent les porteurs sur
`ViewCommandExecutor`, par une seule racine `_expeditionProgression` qui declare `<Board>`,
`<Level>`, `<UnitEligibility>` et `<GameEvents>`. Mesure du 2026-08-15, build `t6dpr4k06g` :
les cinq porteurs rendent leur classe CONCRETE sans qu'aucun ecran d'Operations soit
affiche, ni aucun clic emis. Le circuit qui rendait la voie CIRCULAIRE
(`ExpeditionGameEvents` ne se capte au vol qu'a un envoi, or il faut l'instance POUR
envoyer) est donc coupe a la racine, et non plus contourne.

⚠ RE-ARMER ENTRE CHAQUE ENVOI. Le module detache ses portes a l'emission -- il ancre la
methode qu'il invoque et se bloquerait sur lui-meme. Sans re-armement, le 2e envoi echoue.

⚠ UN ENVOI PART MEME SI LE JEU MEURT OU GELE (#600). D'ou la garde d'entree : on lit le
plateau AVANT, et toute operation deja en `status != 0` est ECARTEE du plan d'envoi. Ne
jamais retenter a l'aveugle en croyant que << ca n'a pas marche >>.

⚠ LE RETOUR D'UN ENVOI NE PROUVE RIEN : on confronte au plateau.

Le solveur, lui, est 100 % hors ligne (`expedition_solver`). Ce script ne fait que
l'alimenter en donnees fraiches et jouer sa sortie.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))
import expedition_solver as ES  # noqa: E402

HOTE = "http://127.0.0.1:8765"
# ⚠ Les trois `BTN_*` de navigation ont ete SUPPRIMES avec `ecran_operations()` : plus aucun
# bouton n'est cherche, clique, ni meme nomme. Voir le pave a leur ancienne place.


class Panne(RuntimeError):
    """Rendue au lieu d'un resultat : une donnee non mesuree ne doit jamais passer pour 0."""


def _curl(url: str, payload: dict, timeout: int = 180) -> dict:
    r = subprocess.run(
        ["curl.exe", "-s", "--max-time", str(timeout), "-X", "POST",
         "-H", "Content-Type: application/json", "-d", json.dumps(payload), url],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not r.stdout.strip():
        raise Panne("curl rc=%d : %s" % (r.returncode, (r.stderr or "")[:200]))
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        raise Panne("reponse non-JSON : %s" % r.stdout[:200])


def session_vivante() -> int:
    """`.session` au SINGULIER -- le pluriel n'existe pas, et l'avoir lu a tue une session."""
    r = subprocess.run(["curl.exe", "-s", "--max-time", "15", HOTE + "/api/admin/status"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not r.stdout.strip():
        raise Panne("host injoignable sur %s -- il n'est pas demarre ?" % HOTE)
    s = (json.loads(r.stdout) or {}).get("session")
    if not s or s.get("status") != "running":
        raise Panne("aucune session Frida vivante. Ce script n'injecte PAS : c'est le role "
                    "de l'orchestrateur.")
    return int(s["id"])


def rpc(sid: int, methode: str, corps: dict | str | None = None, timeout: int = 180):
    args = [] if corps is None else [corps]
    out = _curl("%s/api/scripts/%d/rpc" % (HOTE, sid),
                {"method": methode, "args": args, "timeout": timeout * 1000}, timeout + 30)
    if "error" in out:
        raise Panne("%s : %s" % (methode, out["error"]))
    return out.get("result")


# --------------------------------------------------------------------------- etapes
def armer(sid: int) -> dict:
    """ETAPE 1 -- AVANT toute navigation. N'installe que de l'OBSERVATION."""
    return rpc(sid, "expeditionDispatchArm")


# ⚠ `ecran_operations()` VIVAIT ICI, ET ELLE EST SUPPRIMEE -- pas rendue facultative.
#
# Elle sortait de l'ecran d'Operations puis y revenait a coups d'`uiClick`, parce que c'est
# l'AFFICHAGE qui faisait passer le porteur : les hooks ne captaient `ExpeditionProgression`
# et consorts que par interception de methodes qui ne tirent qu'a l'ecran (`CanRefreshBoard`,
# `IsCrusadeEventActive`, `get_Points`, `GetCurrentLevel`, ...). De la venait l'ordre non
# intuitif << armer AVANT de naviguer >>, et tout le pavement de pieges qui l'entourait.
#
# Les hooks lisent desormais les porteurs sur `ViewCommandExecutor`, par une seule racine
# `_expeditionProgression` qui declare `<Board>`, `<Level>`, `<UnitEligibility>` et
# `<GameEvents>`. Il n'y a donc PLUS RIEN a afficher, et garder la navigation << au cas ou >>
# aurait ete pire que l'enlever : elle FAIT DISPARAITRE L'UI du joueur (elle sort de l'ecran
# courant), pour un porteur que la lecture rend de toute facon.
#
# Ce que ca supprime, en plus des clics : la dependance a l'ecran de depart (le jeu devait
# etre sur l'accueil ou la carte Crusade -- sinon PANNE), les trois `time.sleep` d'animation,
# et la validation de chaque clic par son effet.


def lire_plateau(sid: int) -> dict:
    r = rpc(sid, "expeditionBoardRead", {}) or {}
    if not r.get("ok") or not r.get("json"):
        raise Panne("plateau illisible : %s" % json.dumps(r)[:220])
    return json.loads(r["json"])["expeditionState"]


def lire_roster(sid: int) -> tuple[list[str], dict]:
    """`rosterOwned` EXIGE des ids explicites -- il n'enumere pas. On lui donne le lineup."""
    import gameconfig
    ids = gameconfig.all_unit_ids()["lineup"]
    rpc(sid, "rosterOwnedArm")
    r = rpc(sid, "rosterOwned", {"ids": ids, "details": True}) or {}
    if not r.get("ok"):
        raise Panne("roster illisible : %s" % json.dumps(r)[:220])
    return list(r.get("possedes") or []), dict(r.get("details") or {})


def lire_seuils(sid: int) -> dict:
    r = rpc(sid, "expeditionRankRequirements") or {}
    if not r.get("ok") or not r.get("seuils"):
        raise Panne("seuils illisibles : %s" % json.dumps(r)[:220])
    return r["seuils"]


def motif_non_partante(op: dict, kits: dict, tout_le_roster: list[str],
                       libres: list[str], details: dict, seuils: dict) -> str:
    """Pourquoi cette operation ne part pas -- sur le POOL DE L'OPERATION, JAMAIS sur la
    taille du roster.

    Le 2026-08-12 le motif affichait << 106 unites libres au roster >> pour une Mythic dont
    le pool eligible TOTAL vaut 3 pour 5 places. Ca se lit << il y a du monde, c'est le bonus
    qui coince >> et ca a fait conclure << attendre le retour des parties >>. Or les deux
    causes appellent des gestes OPPOSES -- attendre, ou monter des raretes -- donc elles sont
    SEPAREES ici, et chacune publie le compte qui l'etablit.

    `tout_le_roster` = AVANT retrait des immobilisees ; `libres` = apres. Leur ECART est la
    seule chose qui distingue << parties >> de << pas assez eligibles en soi >>."""
    besoin = int(op.get("participants") or 0)
    tous, _ = ES.pool_eligible(op, kits, tout_le_roster, details, seuils)
    libre, _ = ES.pool_eligible(op, kits, libres, details, seuils)
    if len(tous) < besoin:
        return ("pool eligible INSUFFISANT en soi -- attendre ne sert a RIEN "
                "(%d eligibles au total pour %d places)" % (len(tous), besoin))
    if len(libre) < besoin:
        return ("unites eligibles PARTIES -- attendre leur retour "
                "(%d eligibles dont %d libres, pour %d places)"
                % (len(tous), len(libre), besoin))
    return ("bonus hors d'atteinte et remplissage impossible "
            "(%d eligibles libres pour %d places)" % (len(libre), besoin))


def envoyer(sid: int, exp_id: str, unites: list[str]) -> dict:
    """RE-ARME AVANT CHAQUE ENVOI -- le module detache ses portes a l'emission."""
    armer(sid)
    return rpc(sid, "expeditionDispatch", {
        "expeditionId": exp_id, "unitIds": unites, "participants": len(unites),
        "bonusFulfilled": True, "confirmer": True})


# --------------------------------------------------------------------------- pilote
def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="expedition_run", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--envoyer", action="store_true",
                   help="ENVOIE le plan (immobilise les unites). Sans lui : plan seul.")
    a = p.parse_args(argv)

    sid = session_vivante()
    print("session %d" % sid)

    # AUCUNE NAVIGATION. Les porteurs se LISENT sur le `ViewCommandExecutor`.
    arm = armer(sid)
    print("arme : %s porte(s)" % arm.get("armes"))

    etat = lire_plateau(sid)
    board = etat["board"]
    possedes, details = lire_roster(sid)
    seuils = lire_seuils(sid)
    print("plateau %d operations | niveau %s | %d unites possedees"
          % (len(board), etat.get("level"), len(possedes)))

    # GARDE ANTI-DOUBLE-ENVOI, DEUX VOLETS -- et le second a ete oublie une fois.
    #   a) une operation deja partie sort du perimetre ;
    #   b) ses unites quittent le roster SOUMIS AU SOLVEUR. Sans (b) le plan proposait
    #      `adeptCanoness`, `admecMarshall`, `admecRuststalker` pour une SECONDE operation
    #      alors qu'elles etaient deja parties -- refuse par le jeu, et rien ne le disait.
    #
    # ⛔ LA PORTEE EST L'AXE EXPEDITION, ET RIEN D'AUTRE. Une unite partie reste PARFAITEMENT
    # DISPONIBLE POUR LES BATAILLES (campagne, farm, PvP, guerre de guilde) : le seul interdit
    # est de l'envoyer sur une DEUXIEME operation. Le mot << immobilisee >> employe ici a ete
    # lu comme un verrou global le 2026-08-23, ce qui a fait ecarter deux noeuds de farm
    # parfaitement jouables (52 points d'utilite). Le compte etait juste, la portee inventee.
    # Le champ est `units` (mesure) : `dispatchedUnits` existe mais vaut `null`.
    libres, immobilisees = ES.deja_parties(board)
    tout_le_roster = list(possedes)      # AVANT retrait des immobilisees -- sert a ventiler
                                         # << parties >> contre << pas assez eligibles >>.
    deja = [o["id"] for o in board if o.get("status")]
    if deja:
        print("DEJA PARTIES, ecartees du plan : %s" % ", ".join(deja))
    if immobilisees:
        print("IMMOBILISEES, retirees du roster : %d unite(s)" % len(immobilisees))
        possedes = [u for u in possedes if u not in set(immobilisees)]
    if not libres:
        print("rien a envoyer : toutes les operations sont deja parties.")
        return 0

    # MIRROR EXACT de `cmd_board` : meme vocabulaire, meme normalisation. Fabriquer la chaine
    # d'objectif a la main ici ferait diverger le pilote du solveur au premier format neuf.
    kits = ES._charger_kits()
    factions, traits, alliances, degats = ES._vocabulaire(kits)
    ops = []
    for o in libres:
        o = dict(o)
        o["_objs"] = [ES.resoudre_objectif(ES.normaliser_objectif_brut(t),
                                           factions, traits, alliances, degats)
                      for t in (o.get("bonusObjectives") or [])]
        ops.append(o)
    r = ES.resoudre_plateau(ops, kits, possedes, progression=details, seuils=seuils)
    print("PARTANTES : %d / %d (dont %d avec bonus)"
          % (r["partantes"], len(ops), r["couvertes"]))

    envois = [(p["op"].get("expeditionId"), p["op"].get("id"), p["equipe"])
              for p in r["plan"] if p.get("equipe")]
    for _, nom, eq in envois:
        print("  %-26s %s" % (nom, ", ".join(eq)))

    # UN ZERO DOIT PORTER SA RAISON. << 0 partante >> se lit comme << rien a faire >>, alors
    # que c'est presque toujours << pas assez d'unites libres >> -- l'information utile.
    for i in r.get("incompletes") or []:
        print("  %-26s ECARTEE : besoin %d, couvrant %d, pool libre %d"
              % (i["op"], i["besoin"], i["couvrant"], i["pool_libre"]))
    for p in r["plan"]:
        if p.get("equipe"):
            continue
        print("  %-26s NON PARTANTE : %s"
              % (p["op"].get("id"),
                 motif_non_partante(p["op"], kits, tout_le_roster, possedes, details, seuils)))

    if not a.envoyer:
        print("\n(plan seul -- relance avec --envoyer pour jouer)")
        return 0

    print("")
    for exp_id, nom, eq in envois:
        out = envoyer(sid, exp_id, eq)
        print("  %-26s ok=%s" % (nom, (out or {}).get("ok")))
        if not (out or {}).get("ok"):
            print("     %s" % json.dumps(out)[:240])
            break
        time.sleep(3)

    # CONFRONTATION -- le retour d'un envoi ne prouve rien, le plateau si.
    apres = {o["id"]: o.get("status") for o in lire_plateau(sid)["board"]}
    print("\netat confronte :")
    for _, nom, _eq in envois:
        print("  %-26s status=%s" % (nom, apres.get(nom)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Panne as e:
        print("PANNE : %s" % e)
        raise SystemExit(2)
