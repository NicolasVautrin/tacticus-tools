"""Pipeline complet des Operations (Expeditions) : lire, resoudre, envoyer, confronter.

    python scripts/python/expedition_run.py              # plan seul, RIEN n'est envoye
    python scripts/python/expedition_run.py --envoyer    # plan PUIS envoi

POURQUOI CE SCRIPT EXISTE PLUTOT QU'UNE PROCEDURE ECRITE. L'ordre des gestes n'est pas
intuitif et se relit mal sous pression -- une prose qui dit << arme avant de naviguer >> a
deja ete lue a l'envers, ce qui a coute une heure et une conclusion fausse (<< il faut un
envoi manuel pour amorcer >>). Ici l'ordre est EXECUTE, pas recommande.

L'ORDRE, ET CE QU'IL RESOUT

  1. `expeditionDispatchArm` -- EN PREMIER, avant toute navigation.
  2. Ecran Operations affiche (on sort et on y revient si besoin).
  3. lire le plateau, le roster, les seuils
  4. resoudre hors ligne
  5. envoyer, en RE-ARMANT entre chaque
  6. confronter au plateau

⛔ L'ETAPE 1 AVANT L'ETAPE 2, ET C'EST TOUT LE SUJET. `ExpeditionGameEvents` ne se capte au
vol qu'a un envoi -- or il faut l'instance POUR envoyer : la voie est CIRCULAIRE. La sortie
est que `ExpeditionProgression` la porte en champ `<GameEvents>k__BackingField`, et que ce
porteur-la se capte des qu'un ecran d'Operations s'affiche, via `CanRefreshBoard` /
`IsCrusadeEventActive` ancrees A L'ARMEMENT. Armer APRES avoir navigue laisse ces deux
methodes deja tirees : plus rien ne passe, et le RPC repond << AUCUN ExpeditionGameEvents
joignable >>. Ce n'est pas une panne, c'est un ordre inverse.

⚠ RE-ARMER ENTRE CHAQUE ENVOI. Le module detache ses portes a l'emission -- il ancre la
methode qu'il invoque et se bloquerait sur lui-meme. Sans re-armement, le 2e envoi echoue.

⚠ UN ENVOI PART MEME SI LE JEU MEURT OU GELE (#600). D'ou la garde d'entree : on lit le
plateau AVANT, et toute operation deja en `status != 0` est ECARTEE du plan d'envoi. Ne
jamais retenter a l'aveugle en croyant que << ca n'a pas marche >>.

⚠ LE RETOUR D'UN CLIC NE PROUVE RIEN, celui d'un envoi non plus : on confronte au plateau.

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
#: Les deux methodes ancrees par l'armement ne tirent qu'a l'AFFICHAGE de l'ecran. Si le jeu
#: y est deja, il faut en sortir et y revenir -- d'ou ces deux boutons.
BTN_CRUSADE = "button_special_Crusade"
BTN_EXPEDITIONS = "Button_Expeditions"
BTN_RETOUR = "button_special_back_specified"


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


def ecran_operations(sid: int) -> None:
    """ETAPE 2 -- faire AFFICHER l'ecran, meme si le jeu y est deja.

    On sort puis on revient : c'est l'AFFICHAGE qui fait passer le porteur, pas sa presence.
    Chaque clic est valide par son EFFET (le bouton suivant existe), jamais par son retour --
    `interactable` precede la fin de l'animation, et un clic emis dans cette fenetre est
    perdu EN RAPPORTANT `ok: true`.
    """
    def boutons() -> dict[str, str]:
        r = rpc(sid, "uiList", {}) or {}
        return {b.get("name"): b.get("path") for b in (r.get("buttons") or []) if b.get("name")}

    b = boutons()
    if BTN_RETOUR in b:                      # deja sur Operations -> on en sort
        rpc(sid, "uiClick", b[BTN_RETOUR])
        time.sleep(3)
        b = boutons()
    if BTN_EXPEDITIONS not in b:             # pas sur la carte Crusade -> y aller
        if BTN_CRUSADE not in b:
            raise Panne("ni `%s` ni `%s` a l'ecran : le jeu n'est pas sur l'accueil ni sur "
                        "la carte Crusade." % (BTN_CRUSADE, BTN_EXPEDITIONS))
        rpc(sid, "uiClick", b[BTN_CRUSADE])
        time.sleep(3)
        b = boutons()
        if BTN_EXPEDITIONS not in b:
            raise Panne("le clic sur Crusade n'a pas porte (effet absent).")
    rpc(sid, "uiClick", b[BTN_EXPEDITIONS])
    time.sleep(4)
    if BTN_RETOUR not in boutons():
        raise Panne("le clic sur Expeditions n'a pas porte (effet absent).")


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

    # 1 PUIS 2 -- l'ordre EST le correctif quand on passe par l'ECRAN, cf. docstring.
    #
    # ⚠ L'ECRAN N'EST PLUS REQUIS, et c'est pour ca que son echec ne fait plus tomber la
    # passe. Les hooks lisent desormais les porteurs sur `ViewCommandExecutor` -- une seule
    # racine, `_expeditionProgression`, qui declare `<Board>`, `<Level>`, `<UnitEligibility>`
    # et `<GameEvents>`. Mesure du 2026-08-15 (build `t6dpr4k06g`) : les cinq porteurs ont
    # rendu leur classe CONCRETE alors que le jeu etait EN BATAILLE, sans qu'aucun ecran
    # d'Operations soit affiche. La navigation reste TENTEE parce qu'elle ne coute rien et
    # qu'un `this` capte au vol est l'instance que le jeu utilise VRAIMENT a cet instant ;
    # elle n'est plus qu'un CONFORT.
    arm = armer(sid)
    print("arme : %s porte(s)" % arm.get("armes"))
    try:
        ecran_operations(sid)
        arm = armer(sid)
    except Panne as exc:
        print("ecran NON ouvert (%s)" % exc)
        print("  -> on continue : les porteurs se lisent sur le ViewCommandExecutor.")
    if not arm.get("instanceVue"):
        print("porteur non capte a l'ecran -- il sera resolu par l'executeur a la demande.")
    else:
        print("porteur capte via %s" % arm.get("source"))

    etat = lire_plateau(sid)
    board = etat["board"]
    possedes, details = lire_roster(sid)
    seuils = lire_seuils(sid)
    print("plateau %d operations | niveau %s | %d unites possedees"
          % (len(board), etat.get("level"), len(possedes)))

    # GARDE ANTI-DOUBLE-ENVOI, DEUX VOLETS -- et le second a ete oublie une fois.
    #   a) une operation deja partie sort du perimetre ;
    #   b) ses unites sont IMMOBILISEES et doivent quitter le roster. Sans (b) le plan
    #      proposait `adeptCanoness`, `admecMarshall`, `admecRuststalker` alors qu'elles
    #      etaient en expedition -- injouable, et rien ne le disait.
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
