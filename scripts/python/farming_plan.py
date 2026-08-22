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

⛔ CE SCRIPT NE JOUE RIEN. Il imprime des commandes ; c'est l'appelant qui les lance, une par
une, en verifiant entre chacune.
"""
import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    args = ap.parse_args()

    _, mats = lire_plan(args.plan)
    ids = sorted({m["id"] for m in mats if m.get("id")})

    # --- le besoin RESTANT, par identifiant --------------------------------------------------
    vif = {}
    if not args.hors_ligne:
        sid = session_vivante(args.hote)
        if sid is None:
            print("(!) aucune session vivante -- classement sur le besoin BRUT du plan.")
        else:
            r = Jeu(args.hote, sid).rpc("inventaireUpgrades", [{"ids": ids}], 240000) or {}
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
            ident, _typ, _ord = table[nom]
            e = noeuds.setdefault((ident, n["noeud"]), {"sert": {}, "abrege": n.get("abrege")})
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
        lignes.append((util, ident, noeud, rep, e["sert"]))
    lignes.sort(key=lambda x: (-x[0], x[1], x[2]))

    print("%-14s %-5s %6s  %-42s %s" % ("campagne", "noeud", "utile", "sert", "replay"))
    print("-" * 108)
    total = 0
    for util, ident, noeud, rep, sert in lignes:
        total += util
        detail = ", ".join("%s %d" % (k[:18], v) for k, v in
                           sorted(sert.items(), key=lambda kv: -kv[1]) if v > 0)
        print("%-14s %-5s %6d  %-42s %s"
              % (ident, noeud, util, detail[:42] or "(besoin couvert)",
                 rep or "AUCUN"))

    print()
    utiles = [x for x in lignes if x[0] > 0 and x[3]]
    print("%d noeud(s) encore UTILE(S) et rejouable(s) ; %d sans replay ; %d deja couverts"
          % (len(utiles), sum(1 for x in lignes if x[0] > 0 and not x[3]),
             sum(1 for x in lignes if x[0] == 0)))
    print()
    print("--- commandes, dans l'ordre d'utilite (une par une, en verifiant entre chacune)")
    for util, ident, noeud, rep, _s in utiles:
        print("python scripts/python/campagne_rejeu_boucle.py --replay data/replays/campaign/%s "
              "--armer     # %s %s, utile %d" % (rep.split()[0], ident, noeud, util))
    return 0


if __name__ == "__main__":
    sys.exit(main())
