"""DERIVER les taux de change entre devises, depuis les prix boutique du gameconfig.

    python scripts/python/taux_devises.py
    python scripts/python/taux_devises.py --numeraire gems --min-appuis 5

LE PONT. Chaque creneau marchand (`shop.merchants[*].products[*][*]`) porte un `reward` et un
`cost {type, amount}`. Un MEME reward vendu dans deux boutiques a deux devises differentes donne
un taux DIRECT, sans hypothese. On agrege ces observations en un graphe de devises.

⚠ NOMS : deux devises ne portent PAS le nom qu'on leur donne en jeu. `gems` EST le Blackstone
(`UI/ResourcesBar_Gems_Tooltip_Title`) et `elderShopCurrency` EST l'Archeotech
(`UI/ResourcesBar_ElderShopCurrency_Tooltip_Title`). Les confondre ferait chercher une devise
`blackstone` qui n'existe pas dans le config.

⚠ CE N'EST PAS UN MARCHE, ET C'EST LA LIMITE DE L'EXERCICE. Les prix sont FIXES par boutique,
pas decouverts par l'echange : rien n'oblige deux boutiques a etre coherentes. Un taux n'a donc
de sens que si les observations CONCORDENT. D'ou deux mesures publiees a chaque paire :
  * la DISPERSION (rapport max/min sur les rewards partages) -- un facteur 3 dit qu'il n'y a pas
    de taux, juste des prix ;
  * la FERMETURE DES TRIANGLES -- si un scalaire existe, A->B->C doit retomber sur A->C. C'est le
    seul controle qui puisse REFUTER l'existence d'une regle de conversion, et c'est pour ca
    qu'il est ici. Une mediane bien serree sur chaque paire mais des triangles ouverts signifie
    que les prix sont poses boutique par boutique.

⚠ ON MEDIANE, ON NE MOYENNE PAS. Les prix boutique portent des promotions (`freeOffer`,
`bannerTextKey` de remise) et des paliers de rarete : une moyenne se fait tirer par un extreme.

ASCII only en sortie (console Windows cp1252).
"""
import argparse
import collections
import itertools
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gameconfig                                          # noqa: E402

# Le nom AFFICHE, lu dans `data/i2_en.json`. Ecrit ici parce que la table de localisation ne
# nomme pas les devises par leur identifiant de config -- la correspondance a du etre etablie
# a la main, une fois, et elle est citee dans la docstring.
NOMS = {
    "gold": "Gold",
    "gems": "Blackstone",
    "elderShopCurrency": "Archeotech",
    "guildCredits": "Guild Credits",
    "guildWarCurrency": "Guild War Credits",
    "crusadeCurrency": "Crusade Credits",
    "loyaltyCurrency": "Loyalty",
    "raidTicket": "Raid Ticket",
}

# Les devises d'EVENEMENT SAISONNIER sont datees (`...June2026`, `...August2026`) : elles
# meurent avec leur evenement. Elles restent dans le graphe (elles relient beaucoup de paires)
# mais on ne les propose pas comme numeraire.
def est_saisonniere(c):
    return "seasonalEvent" in c or "hreCurrency" in c


def observations():
    """[(reward, devise, prix UNITAIRE)] -- toutes les offres marchandes du config."""
    cfg = gameconfig._cfg()
    marchands = ((cfg.get("shop") or {}).get("merchants") or {})
    if not marchands:
        return None                       # ⚠ tri-etat : None = PAS LU, jamais une liste vide
    obs = []
    for nom, mc in marchands.items():
        for creneau in (mc.get("products") or []):
            for v in (creneau if isinstance(creneau, list) else [creneau]):
                cout = v.get("cost") or {}
                t, a, r = cout.get("type"), cout.get("amount"), v.get("reward")
                if not (t and a and r):
                    continue
                # `reward` s'ecrit `<id>` ou `<id>:<quantite>` -- on ramene au prix UNITAIRE,
                # sinon `shards_x:5` et `shards_x:10` compteraient comme deux biens distincts.
                p = str(r).split(":")
                q = float(p[1]) if len(p) > 1 and p[1].replace(".", "").isdigit() else 1.0
                if q <= 0:
                    continue
                obs.append((p[0], t, float(a) / q, nom))
    return obs


def achats_directs():
    """Les produits dont le reward est UNE SEULE devise -- la conversion, sans intermediaire.

    C'est la source la plus forte : le produit EST le taux de change, pas une inference par
    appariement de biens. Les BUNDLES (plusieurs rewards) sont ECARTES -- on ne sait pas quelle
    part du prix va a quoi, et une attribution arbitraire fabriquerait un taux faux.
    """
    cfg = gameconfig._cfg()
    prods = ((cfg.get("shop") or {}).get("products") or {})
    out = collections.defaultdict(list)
    for pid, p in prods.items():
        cout = p.get("cost") or {}
        paye, montant = cout.get("type"), cout.get("amount")
        # ⚠ La cle est `rewards` (pluriel) dans `shop.products`, `reward` (singulier) dans
        #   `shop.merchants[*].products`. Ne lire que la premiere rendait cette section VIDE --
        #   et une section vide se lit comme << pas d'achat direct >>, ce qui est faux.
        rw = p.get("rewards", p.get("reward"))
        if isinstance(rw, str):
            rw = [rw]
        if not (paye and montant and isinstance(rw, list) and len(rw) == 1):
            continue
        bits = str(rw[0]).split(":")
        if len(bits) != 2 or not bits[1].replace(".", "").isdigit():
            continue
        gagne, q = bits[0], float(bits[1])
        if gagne not in NOMS or gagne == paye or q <= 0 or montant <= 0:
            continue
        out[(gagne, paye)].append((pid, montant, q / float(montant)))
    return out


def prix_par_bien(obs):
    """bien -> devise -> prix unitaire MEDIAN (un bien peut apparaitre plusieurs fois)."""
    brut = collections.defaultdict(lambda: collections.defaultdict(list))
    for bien, dev, prix, _m in obs:
        brut[bien][dev].append(prix)
    return {b: {d: statistics.median(v) for d, v in dd.items()} for b, dd in brut.items()}


def taux_paires(prix, min_appuis):
    """(A,B) -> {taux mediane A par B, appuis, dispersion max/min}. Que les paires ASSEZ vues."""
    ratios = collections.defaultdict(list)
    for _bien, dd in prix.items():
        for a, b in itertools.combinations(sorted(dd), 2):
            if dd[b] > 0:
                ratios[(a, b)].append(dd[a] / dd[b])
    out = {}
    for (a, b), lst in ratios.items():
        if len(lst) < min_appuis:
            continue
        out[(a, b)] = {"taux": statistics.median(lst), "n": len(lst),
                       "dispersion": (max(lst) / min(lst)) if min(lst) > 0 else float("inf")}
    return out


def triangles(taux, seuil_ecart):
    """Le controle qui peut REFUTER : A->B->C doit retomber sur A->C."""
    direct = {}
    for (a, b), d in taux.items():
        direct[(a, b)] = d["taux"]
        direct[(b, a)] = 1.0 / d["taux"] if d["taux"] else float("inf")
    devises = sorted({x for p in taux for x in p})
    res = []
    for a, b, c in itertools.combinations(devises, 3):
        if (a, b) in direct and (b, c) in direct and (a, c) in direct:
            via = direct[(a, b)] * direct[(b, c)]
            dr = direct[(a, c)]
            if dr > 0:
                ecart = max(via / dr, dr / via)
                res.append((a, b, c, dr, via, ecart, ecart <= seuil_ecart))
    return res


def vers_numeraire(taux, num):
    """Prix de chaque devise en `num`, par le chemin au MEILLEUR APPUI (Dijkstra sur -log(n))."""
    adj = collections.defaultdict(list)
    for (a, b), d in taux.items():
        adj[a].append((b, d["taux"], d["n"]))
        adj[b].append((a, 1.0 / d["taux"] if d["taux"] else float("inf"), d["n"]))
    val = {num: (1.0, float("inf"), [num])}
    vus = set()
    while True:
        cand = [c for c in val if c not in vus]
        if not cand:
            break
        # On etend d'abord le chemin dont le MAILLON LE PLUS FAIBLE est le plus fort.
        cur = max(cand, key=lambda c: val[c][1])
        vus.add(cur)
        for nxt, r, n in adj[cur]:
            appui = min(val[cur][1], n)
            if nxt not in val or appui > val[nxt][1]:
                val[nxt] = (val[cur][0] * r, appui, val[cur][2] + [nxt])
    return val


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--numeraire", default="gems",
                    help="devise de reference (defaut `gems` = Blackstone : c'est la seule qui "
                         "ait un prix en argent reel, donc un ancrage absolu)")
    ap.add_argument("--min-appuis", dest="min_appuis", type=int, default=4,
                    help="nombre minimal de biens partages pour publier une paire (defaut 4)")
    ap.add_argument("--seuil-triangle", dest="seuil_triangle", type=float, default=1.25,
                    help="ecart tolere sur la fermeture d'un triangle (defaut 1.25 = 25 %%)")
    a = ap.parse_args()

    obs = observations()
    if obs is None:
        print("REFUS : `shop.merchants` NON LU au gameconfig -- on ne derive rien d'un vide.")
        return 2
    print("offres marchandes lues : %d" % len(obs))

    prix = prix_par_bien(obs)
    taux = taux_paires(prix, a.min_appuis)
    if not taux:
        print("REFUS : aucune paire de devises n'atteint %d appuis." % a.min_appuis)
        return 1

    echelles = achats_directs()
    if echelles:
        print()
        print("=== ACHATS DIRECTS (une devise CONTRE une autre) -- taux EXACTS, pas medianes ===")
        print("Bien plus fiable qu'un appariement de biens : le produit EST la conversion.")
        print("%-14s %-14s %9s %9s %9s %6s" %
              ("on obtient", "on paie", "min", "median", "max", "paliers"))
        print("-" * 68)
        for (gagne, paye), lst in sorted(echelles.items(), key=lambda kv: -len(kv[1])):
            r = sorted(x[2] for x in lst)
            print("%-14s %-14s %9.2f %9.2f %9.2f %6d"
                  % (NOMS.get(gagne, gagne)[:14], NOMS.get(paye, paye)[:14],
                     r[0], statistics.median(r), r[-1], len(r)))
        print()
        print("(!) L'ECART min->max EST LE SUJET, pas du bruit : les gros lots sont remises. Il")
        print("    n'existe donc pas UN taux, mais une echelle -- citer le palier, pas la mediane.")

    print()
    print("=== PAIRES DEDUITES (mediane sur les biens vendus dans les DEUX devises) ===")
    # ⚠ SENS DE LECTURE. Pour un meme bien, prix_A * valeur_A = prix_B * valeur_B, donc
    #   prix_A / prix_B = valeur_B / valeur_A. Le ratio se lit donc << 1 B vaut <taux> A >>,
    #   PAS l'inverse -- l'en-tete disait le contraire au premier jet, et c'est le genre de
    #   faute qui ne se voit qu'en recoupant avec le tableau en numeraire.
    print("%-22s %-22s %12s %6s %11s"
          % ("1 unite de B...", "...vaut en A", "taux", "appuis", "dispersion"))
    print("-" * 78)
    for (x, y), d in sorted(taux.items(), key=lambda kv: -kv[1]["n"]):
        if est_saisonniere(x) or est_saisonniere(y):
            continue
        print("%-22s %-22s %12.4f %6d %10.1fx"
              % (NOMS.get(y, y), NOMS.get(x, x), d["taux"], d["n"], d["dispersion"]))

    print()
    print("=== FERMETURE DES TRIANGLES (le controle qui peut REFUTER) ===")
    tri = triangles(taux, a.seuil_triangle)
    if not tri:
        print("aucun triangle complet -- le graphe est un arbre, la coherence n'est PAS testable.")
    else:
        ok = sum(1 for t in tri if t[6])
        print("%d / %d triangles ferment a moins de %.0f %% d'ecart"
              % (ok, len(tri), 100 * (a.seuil_triangle - 1)))
        pires = sorted(tri, key=lambda t: -t[5])[:6]
        print()
        print("%-58s %9s %9s %7s" % ("triangle", "direct", "via", "ecart"))
        print("-" * 86)
        for x, y, z, dr, via, ec, bon in pires:
            print("%-58s %9.4f %9.4f %6.2fx%s"
                  % ("%s -> %s -> %s" % (NOMS.get(x, x)[:16], NOMS.get(y, y)[:16],
                                         NOMS.get(z, z)[:16]),
                     dr, via, ec, "" if bon else "  <-- OUVERT"))

    print()
    print("=== EN %s ===" % NOMS.get(a.numeraire, a.numeraire).upper())
    val = vers_numeraire(taux, a.numeraire)
    lignes = [(c, v) for c, v in val.items() if not est_saisonniere(c)]
    for c, (r, appui, chemin) in sorted(lignes, key=lambda kv: -kv[1][0]):
        if r <= 0:
            continue
        print("  1 %-20s = %10.4f %-12s  (appui %s, %s)"
              % (NOMS.get(c, c), r, NOMS.get(a.numeraire, a.numeraire),
                 "inf" if appui == float("inf") else int(appui),
                 " -> ".join(NOMS.get(x, x)[:12] for x in chemin)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
