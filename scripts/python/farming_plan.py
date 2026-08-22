"""L'ORDRE DES NOEUDS A FARMER -- par le BESOIN RESTANT qu'ils servent, pas par leur position.

    python scripts/python/farming_plan.py

Croise trois entrees : le plan du planner (`logs/planner-raids.json`) pour QUI DROPPE QUOI,
l'inventaire VIVANT du jeu pour le besoin restant, et `data/replays/campaign/` pour savoir
quels noeuds sont rejouables. Rend la liste des noeuds, du plus utile au moins utile, avec la
commande de boucle prete a jouer.

(!)LE BESOIN SE PREND SUR LE STOCK VIF, PAS SUR LE NOMBRE DU PLANNER. Celui-ci est
`min(inventaire, requis)` -- un PLAFOND (cf. `farming_suivi.py`). Et il s'AGREGE par identifiant :
un materiau peut occuper plusieurs lignes du plan pour un seul stock.

(!)UN NOEUD SERT PLUSIEURS MATERIAUX. Son utilite est la somme des besoins restants qu'il
touche -- c'est ce qui le classe. On ne divise pas par le nombre de materiaux : farmer un noeud
qui en sert trois avance sur les trois a la fois.

(!)UN BESOIN N'EST PAS UNE DISPONIBILITE -- ET CE SCRIPT L'A CONFONDU (2026-08-22). Il classait
sur le seul besoin, donc il mettait en tete des noeuds EPUISES : `campaign1` 28 y trone avec
27 d'utilite alors qu'il est a 0 jeton sur 10. La commande imprimee ne pouvait que se faire
refuser -- une liste de tete qui n'est pas jouable, et un aller-retour par noeud pour s'en
apercevoir. Les jetons sont donc LUS (`--jetons`, defaut) et un noeud sans jeton sort de la
liste des commandes en le DISANT.

⚠ TRI-ETAT SUR LES JETONS : `None` = PAS MESURE, jamais rabattu sur 0. Un noeud dont la lecture
echoue reste PROPOSE -- c'est la boucle qui tranchera, elle relit de toute facon. L'inverse
ferait disparaitre un noeud jouable pour une panne de lecture.

⛔ CE SCRIPT NE JOUE RIEN. Il imprime des commandes ; c'est l'appelant qui les lance, une par
une, en verifiant entre chacune.
"""
import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from campagne_rejeu_boucle import jetons_restants          # noqa: E402
from farming_suivi import couvert_du_plan, lire_plan       # noqa: E402
from raids_plan import replays_connus, table_des_campagnes  # noqa: E402
from sandbox_boss import session_vivante                    # noqa: E402
from sandbox_mode import Jeu                                # noqa: E402

HOTE = "http://127.0.0.1:8765"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(RACINE / "logs" / "planner-raids.json"))
    ap.add_argument("--hote", default=HOTE)
    ap.add_argument("--hors-ligne", action="store_true",
                    help="ne pas lire le jeu : classer par le besoin BRUT du plan")
    ap.add_argument("--sans-jetons", action="store_true",
                    help="ne PAS lire les jetons (plus rapide, mais la liste de tete peut "
                         "contenir des noeuds epuises)")
    args = ap.parse_args()

    _, mats = lire_plan(args.plan)
    ids = sorted({m["id"] for m in mats if m.get("id")})

    # --- le besoin RESTANT, par identifiant --------------------------------------------------
    vif, jeu = {}, None
    if not args.hors_ligne:
        sid = session_vivante(args.hote)
        if sid is None:
            print("(!) aucune session vivante -- classement sur le besoin BRUT du plan.")
        else:
            jeu = Jeu(args.hote, sid)
            r = jeu.rpc("inventaireUpgrades", [{"ids": ids}], 240000) or {}
            if r.get("ok"):
                vif = r.get("quantites") or {}
            else:
                print("(!) `inventaireUpgrades` NON MESURE -- besoin BRUT.")

    requis = {}
    for m in mats:
        requis[m.get("id")] = requis.get(m.get("id"), 0) + (m.get("requis") or 0)
    reste = {}
    for i, req in requis.items():
        q = vif.get(i)
        # Sans mesure, le besoin BRUT -- jamais un zero invente.
        reste[i] = req if q is None else max(0, req - q)

    # --- l'utilite d'un NOEUD = la somme des restes qu'il touche -------------------------------
    table = table_des_campagnes()
    noeuds = {}
    for m in mats:
        r = reste.get(m.get("id"), 0)
        for n in m.get("noeuds") or []:
            nom = n.get("campagne")
            if nom not in table:
                continue
            # ⚠ `table_des_campagnes` rend `(ident, LIBELLE, type)` -- le 2e est le nom affiche
            #   (<< Elite >>), le 3e le `campaignType` ENTIER attendu par le jeu. Les confondre
            #   fait rendre NON MESURE a chaque noeud, en silence.
            ident, _libelle, typ = table[nom]
            e = noeuds.setdefault((ident, n["noeud"]),
                                  {"sert": {}, "abrege": n.get("abrege"), "type": typ})
            # Un meme materiau peut revenir par deux lignes du plan : on garde son reste AGREGE
            # une seule fois, sinon un noeud qui sert `Pile of Salvage` compterait 36 deux fois.
            e["sert"][m["nom"]] = r

    # `replays_connus` rend une LISTE de noms par couple -- un noeud peut porter plusieurs
    # replays. On prend le premier et on DIT quand il y en a plusieurs, plutot que d'en choisir
    # un en silence.
    vus = replays_connus()
    lignes = []
    for (ident, noeud), e in noeuds.items():
        util = sum(e["sert"].values())
        noms = vus.get((ident, noeud)) or []
        rep = noms[0] if noms else None
        if len(noms) > 1:
            rep += "  (+%d autre(s))" % (len(noms) - 1)
        lignes.append([util, ident, noeud, rep, e["sert"], e["type"], None])
    lignes.sort(key=lambda x: (-x[0], x[1], x[2]))

    # --- les JETONS, et seulement la ou ca sert -----------------------------------------------
    # On ne les lit que pour les noeuds UTILES ET REJOUABLES : lire les autres couterait quatre
    # RPC chacun pour une ligne qu'on ne proposera de toute facon pas.
    if jeu is not None and not args.sans_jetons:
        for L in lignes:
            if L[0] <= 0 or not L[3]:
                continue
            L[6] = jetons_restants(jeu, L[1], L[5], L[2])[0]

    print("%-14s %-5s %6s %7s  %-38s %s"
          % ("campagne", "noeud", "utile", "jetons", "sert", "replay"))
    print("-" * 112)
    for util, ident, noeud, rep, sert, _typ, jet in lignes:
        detail = ", ".join("%s %d" % (k[:18], v) for k, v in
                           sorted(sert.items(), key=lambda kv: -kv[1]) if v > 0)
        print("%-14s %-5s %6d %7s  %-38s %s"
              % (ident, noeud, util,
                 "-" if jet is None else jet, detail[:38] or "(besoin couvert)",
                 rep or "AUCUN"))

    print()
    utiles = [x for x in lignes if x[0] > 0 and x[3]]
    # ⚠ `None` (NON MESURE) RESTE PROPOSE -- seul un ZERO LU ecarte. La boucle relit de toute
    #   facon ; ecarter sur une panne de lecture ferait perdre un noeud jouable.
    epuises = [x for x in utiles if x[6] == 0]
    jouables = [x for x in utiles if x[6] != 0]
    print("%d noeud(s) encore UTILE(S) et rejouable(s) ; %d sans replay ; %d deja couverts"
          % (len(utiles), sum(1 for x in lignes if x[0] > 0 and not x[3]),
             sum(1 for x in lignes if x[0] == 0)))
    if epuises:
        print("dont %d EPUISE(S) aujourd'hui (0 jeton), ecarte(s) des commandes : %s"
              % (len(epuises), ", ".join("%s %s" % (x[1], x[2]) for x in epuises)))
    print()
    if not jouables:
        print("--- AUCUN noeud utile ET pourvu en jetons. Rien a farmer maintenant.")
        return 0
    print("--- commandes, dans l'ordre d'utilite (une par une, en verifiant entre chacune)")
    for util, ident, noeud, rep, _s, _t, jet in jouables:
        print("python scripts/python/campagne_rejeu_boucle.py --replay data/replays/campaign/%s "
              "--armer --entree start     # %s %s, utile %d, %s jeton(s)"
              % (rep.split()[0], ident, noeud, util, "?" if jet is None else jet))
    return 0


if __name__ == "__main__":
    sys.exit(main())
