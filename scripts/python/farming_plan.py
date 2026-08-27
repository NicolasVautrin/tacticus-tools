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

(!)MAIS L'UTILITE EST UN BESOIN, PAS UN GAIN -- ET ELLE NE CLASSE QUE SI LE JETON EST LA RESSOURCE
RARE. Un noeud a besoin 17 ne rend pas 17 par passe : il rend son TAUX (`loot.base`, verse a
CHAQUE passe, + P(`chanceOf`)). Des que l'ENERGIE est plus rare que les jetons -- le cas courant :
150 d'energie pour 68 jetons le 2026-08-27 -- le bon classement est taux_du_materiau_VISE /
`staminaCost`, et c'est ce que fait `--energie N`. Mesure du meme jour : le classement par
utilite mettait `elite4` 26 en 3e position alors que `eliteMirror2` 9 rend 50 % de plus par
energie. ⚠ Et le taux se prend sur le materiau VISE : `loot.base` porte aussi `gold:<min>-<max>`,
donc le compter sans filtrer sur la table des upgrades ajoute un faux drop a chaque noeud.

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
from fractions import Fraction
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gameconfig                                          # noqa: E402
from campagne_rejeu_boucle import jetons_restants          # noqa: E402
from farming_suivi import couvert_du_plan, lire_plan       # noqa: E402
from plan_objectif import or_par_passe                     # noqa: E402
from raids_plan import replays_connus, table_des_campagnes  # noqa: E402
from sandbox_boss import session_vivante                    # noqa: E402
from sandbox_mode import Jeu                                # noqa: E402

HOTE = "http://127.0.0.1:8765"


def _norme_id(x):
    # `battleId` n'est PAS toujours un entier : le gameconfig porte des `03B`. Normaliser en
    # CHAINE (zeros de tete retires) plutot que forcer un `int`, qui leve.
    return str(x).strip().lstrip("0").upper() or "0"


def _index_batailles():
    cfg = gameconfig._cfg()
    up = cfg.get("upgrades") or {}
    upgrades = {u["id"] for u in up} if isinstance(up, list) else set(up)
    ix = {}
    for _typ, lst in (cfg.get("battles") or {}).get("campaigns", {}).items():
        for c in lst:
            for b in c.get("battles") or []:
                ix[(str(c["id"]).lower(), _norme_id(b["battleId"]))] = b
    return ix, upgrades


def _taux_par_materiau(b, upgrades):
    """Le taux de drop PAR MATERIAU d'une bataille : `base` a CHAQUE passe + P(`chanceOf`).

    ⚠ `loot.base` porte AUSSI l'or (`gold:<min>-<max>`). Le compter comme un materiau gonfle le
    taux d'un cran entier sur tous les noeuds -- d'ou le filtre sur la table des upgrades.
    """
    lo = b.get("loot") or {}
    t = {}
    for e in (lo.get("base") or []):
        mid = str(e).split(":")[0]
        if mid in upgrades:
            t[mid] = t.get(mid, 0.0) + 1.0
    ch = lo.get("chanceOf")
    if ch and "%" in ch:
        mid, fr = ch.split("%")
        if mid in upgrades:
            t[mid] = t.get(mid, 0.0) + float(Fraction(fr))
    return t


# Le taux du jeu : ~18,1 or par energie. MESURE -- moyenne des 10 meilleurs noeuds de campagne
# (`loot.base` `gold:<min>-<max>` / `staminaCost`). C'est l'etalon qui permet de convertir l'or
# et les materiaux dans la meme unite ; re-deriver plutot que citer si les tables bougent.
OR_PAR_ENERGIE = 18.1


def reconcilier(entete, mats, reste):
    """L'extraction a-t-elle rapporte TOUTES les lignes du plan ? Compare a `energieTotale`.

    ⚠ CE GARDE EXISTE PARCE QU'UN EN-TETE COMPLET PEUT COIFFER DES LIGNES PARTIELLES, et que
    c'est la combinaison la plus trompeuse qui soit : le total a l'air de valider la liste qu'il
    contredit. Mesure du 2026-08-27 -- `Locator Beacon` etait planifie mais absent de l'export
    (il vit dans l'onglet << extra energy >>, que le scrape d'alors ne visitait pas), et les
    lignes rapportees ne reconstituaient que ~866 d'energie sur les 1573 annoncees. Rien ne le
    disait : `farming_plan` proposait sereinement un besoin ampute.

    ⚠ L'ESTIMATION EST GROSSIERE, ET C'EST ASSUME. On re-choisit le noeud nous-memes, donc notre
    energie n'est pas celle du planner -- l'ecart normal se compte en dizaines de pour cent. Ce
    garde ne mesure PAS un cout, il detecte une AMPUTATION : on ne crie que sur un manque franc.

    Rend `None` quand `energieTotale` n'est pas dans l'en-tete -- PAS MESURE n'est pas ZERO.
    """
    # ⚠ `lire_plan` rend le DOCUMENT ENTIER, pas l'en-tete : `energieTotale` vit sous
    #   `doc["entete"]`. Chercher a plat rendait `None`, donc << completude NON VERIFIABLE >> --
    #   un garde qui s'excuse au lieu de mordre, exactement le faux vert qu'il doit empecher.
    #   On accepte les deux formes plutot que de parier sur celle que l'appelant passe.
    e = (entete or {})
    total = e.get("energieTotale") or (e.get("entete") or {}).get("energieTotale")
    if not total:
        return None
    ix, upgrades = _index_batailles()
    table = table_des_campagnes()
    somme, resolus, muets = 0, 0, 0
    for m in mats:
        mid = m.get("id")
        besoin = reste.get(mid, 0) if mid else 0
        if besoin <= 0:
            continue
        n = (m.get("noeuds") or [None])[0]
        if not n or n.get("campagne") not in table:
            muets += 1
            continue
        ident, _lib, _typ = table[n["campagne"]]
        b = ix.get((str(ident).lower(), _norme_id(n["noeud"])))
        if b is None or b.get("staminaCost") is None:
            muets += 1
            continue
        t = _taux_par_materiau(b, upgrades).get(mid)
        if not t:
            muets += 1
            continue
        import math
        somme += math.ceil(besoin / t) * b["staminaCost"]
        resolus += 1
    return {"annonce": total, "reconstitue": somme, "resolus": resolus, "muets": muets,
            "part": (somme / total) if total else None}


def allouer_energie(jouables, reste, energie, critere="passes", or_par_item=None):
    """Repartir `energie` sur les noeuds jouables -- gloutonnement, au meilleur GAIN par energie.

    ⚠ CE QU'UNE PASSE RAPPORTE EST LE TAUX, PAS L'UTILITE. L'utilite est le besoin RESTANT : un
    noeud a besoin 17 ne rend pas 17 par passe. Classer par utilite est juste quand la ressource
    rare est le JETON (le classement par defaut de ce script) ; des que c'est l'ENERGIE, il faut
    le taux du materiau VISE divise par le `staminaCost`.

    Rend `[(ligne, passes, cout)]`, ou None si le gameconfig ne permet pas de conclure -- jamais
    une allocation partielle silencieuse.
    """
    ix, upgrades = _index_batailles()
    cands, muets = [], []
    for L in jouables:
        util, ident, noeud, rep, sert, typ, jet = L
        b = ix.get((str(ident).lower(), _norme_id(noeud)))
        if b is None or b.get("staminaCost") is None:
            muets.append("%s %s" % (ident, noeud))
            continue
        tx = {mid: t for mid, t in _taux_par_materiau(b, upgrades).items()
              if reste.get(mid, 0) > 0}
        if not tx:
            continue
        # ⚠ Tri-etat sur les jetons : `None` = PAS MESURE. Ni 0 (ca supprimerait un noeud
        #   jouable) ni l'infini (ca planifierait des passes refusees) : on borne au
        #   `maxAttempts` du gameconfig, que la boucle re-borne de toute facon.
        cands.append({"L": L, "stam": b["staminaCost"], "taux": tx, "or": or_par_passe(b),
                      "jet": jet if jet is not None else (b.get("maxAttempts") or 0)})
    if muets:
        print("(!) %d noeud(s) INTROUVABLE(S) au gameconfig, ecarte(s) de l'allocation : %s"
              % (len(muets), ", ".join(muets)))
    if not cands:
        return []

    # LE POIDS DE L'OR -- combien d'OR vaut UN materiau vise. Sans lui, l'or ne pesait que par
    # une bande d'equivalence : deux reglages qui se recouvrent, et un choix qui basculait d'un
    # coup au bord de la bande. Avec, or et materiaux vivent sur la MEME echelle et le
    # classement est un seul scalaire.
    #
    # Il se DERIVE, il ne se decrete pas : farmer un materiau coute `stam / taux` d'energie, et
    # le jeu paie l'energie `OR_PAR_ENERGIE`. La mediane sur les candidats donne donc le prix en
    # or d'un materiau, sans constante inventee.
    if or_par_item is None:
        couts = sorted(c["stam"] / sum(c["taux"].values()) for c in cands)
        or_par_item = couts[len(couts) // 2] * OR_PAR_ENERGIE
        print("poids de l'or DERIVE : 1 materiau = %.0f or "
              "(%.2f energie/materiau x %.1f or/energie)"
              % (or_par_item, couts[len(couts) // 2], OR_PAR_ENERGIE))
    else:
        print("poids de l'or IMPOSE : 1 materiau = %.0f or" % or_par_item)
    if or_par_item <= 0:
        print("(!) poids de l'or NUL ou negatif -- l'or est ignore dans le classement.")

    def valeur(c, besoin):
        """Ce qu'une PASSE de `c` rapporte, materiaux ET or, en equivalent-materiau."""
        g = sum(min(t, besoin.get(mid, 0)) for mid, t in c["taux"].items())
        return g + (c["or"] / or_par_item if or_par_item > 0 else 0.0), g

    besoin = dict(reste)
    passes = {}
    while True:
        best, bestv = None, 0.0
        for c in cands:
            cle = id(c)
            if c["stam"] > energie or passes.get(cle, 0) >= c["jet"]:
                continue
            val, gain = valeur(c, besoin)
            if gain <= 0:
                continue          # plus rien a servir ici : l'or seul ne justifie pas la passe
            # `passes` -- ce qu'une PASSE rapporte. `energie` -- ce qu'une ENERGIE rapporte.
            # ⚠ C'est ce choix qui fait pencher vers l'ELITE : il coute 10 d'energie contre 5,
            #   mais rend ~1,08 materiau par passe contre ~0,67, et surtout 175 d'or contre 12.
            #   Par ENERGIE le noeud bon marche gagne ; par PASSE l'Elite domine largement.
            v = val if critere == "passes" else val / c["stam"]
            if best is None or v > bestv + 1e-12:
                best, bestv = c, v
        if best is None:
            break
        passes[id(best)] = passes.get(id(best), 0) + 1
        energie -= best["stam"]
        for mid, t in best["taux"].items():
            besoin[mid] = max(0.0, besoin.get(mid, 0) - t)

    out = [(c, passes[id(c)], passes[id(c)] * c["stam"]) for c in cands if passes.get(id(c))]
    out.sort(key=lambda x: -sum(min(t, reste.get(mid, 0))
                                for mid, t in x[0]["taux"].items()) / x[0]["stam"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(RACINE / "logs" / "planner-raids.json"))
    ap.add_argument("--hote", default=HOTE)
    ap.add_argument("--hors-ligne", action="store_true",
                    help="ne pas lire le jeu : classer par le besoin BRUT du plan")
    ap.add_argument("--sans-jetons", action="store_true",
                    help="ne PAS lire les jetons (plus rapide, mais la liste de tete peut "
                         "contenir des noeuds epuises)")
    ap.add_argument("--seuil-reconciliation", dest="seuil_reconciliation", type=float,
                    default=0.80,
                    help="part MINIMALE de `energieTotale` que les lignes extraites doivent "
                         "reconstituer avant qu'on crie a l'amputation (defaut 0.80). REGLAGE : "
                         "notre re-choix de noeud SURESTIME l'energie, donc un export sain passe "
                         "au-dessus de 1.0 ; l'export ampute du 2026-08-27 valait 0.55.")
    ap.add_argument("--energie", type=int, default=None,
                    help="repartir N d'energie sur les noeuds : classe par le TAUX au lieu de "
                         "l'utilite brute, et borne les commandes a --passes (`energie.py` lit "
                         "l'energie disponible).")
    ap.add_argument("--critere", choices=("passes", "energie"), default="passes",
                    help="`passes` (defaut) : ce qu'une PASSE rapporte -- favorise les Elite, "
                         "plus chers mais bien plus riches. `energie` : ce qu'une ENERGIE "
                         "rapporte -- favorise les noeuds bon marche.")
    ap.add_argument("--or-par-item", dest="or_par_item", type=float, default=None,
                    help="le POIDS de l'or : combien d'or vaut UN materiau vise. Par defaut "
                         "DERIVE (cout median en energie d'un materiau x %.1f or/energie), pas "
                         "invente. Le BAISSER privilegie l'or, le monter privilegie le "
                         "materiau ; 0 ignore l'or." % OR_PAR_ENERGIE)
    args = ap.parse_args()

    entete, mats = lire_plan(args.plan)
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

    # --- L'EXTRACTION EST-ELLE COMPLETE ? -----------------------------------------------------
    rec = reconcilier(entete, mats, reste)
    if rec is None:
        print("(!) `energieTotale` absente de l'en-tete -- COMPLETUDE NON VERIFIABLE.")
        print("    Re-extraire avec `scripts/planner/extraire-raids.js` a jour.")
    elif rec["part"] is not None and rec["part"] < args.seuil_reconciliation:
        print("=" * 78)
        print("(!) EXTRACTION VRAISEMBLABLEMENT AMPUTEE -- le besoin ci-dessous est INCOMPLET.")
        print("    le plan annonce %d d'energie ; les lignes extraites n'en reconstituent que"
              % rec["annonce"])
        print("    %d (%.0f %%), sur %d ligne(s) resolue(s) et %d non resolue(s)."
              % (rec["reconstitue"], 100 * rec["part"], rec["resolus"], rec["muets"]))
        print("    Cause connue : le planner a PLUSIEURS ONGLETS et le DOM ne porte que l'actif.")
        print("    Re-extraire avec `scripts/planner/extraire-raids.js` (il les parcourt tous),")
        print("    et verifier `entete.onglets` dans le JSON produit.")
        print("=" * 78)
    else:
        print("completude : %d d'energie reconstituee sur %d annoncee (%.0f %%), %d ligne(s)"
              % (rec["reconstitue"], rec["annonce"], 100 * rec["part"], rec["resolus"]))
    print()

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
    if args.energie is None:
        print("--- commandes, dans l'ordre d'utilite (une par une, en verifiant entre chacune)")
        for util, ident, noeud, rep, _s, _t, jet in jouables:
            print("python scripts/python/campagne_rejeu_boucle.py --replay "
                  "data/replays/campaign/%s --armer --entree start"
                  "     # %s %s, utile %d, %s jeton(s)"
                  % (rep.split()[0], ident, noeud, util, "?" if jet is None else jet))
        return 0

    alloc = allouer_energie(jouables, reste, args.energie, args.critere, args.or_par_item)
    if not alloc:
        print("--- AUCUNE allocation possible avec %d d'energie." % args.energie)
        return 0
    print("--- %d d'energie, critere `%s` (l'utilite est un besoin, pas un gain)"
          % (args.energie, args.critere))
    print("%-14s %-5s %6s %5s %7s %10s %9s %8s" %
          ("campagne", "noeud", "passes", "stam", "cout", "taux/passe", "taux/nrj", "or"))
    print("-" * 75)
    depense, tot_or = 0, 0
    for c, p, cout in alloc:
        _u, ident, noeud, _r, _s, _t, _j = c["L"]
        g = sum(min(t, reste.get(mid, 0)) for mid, t in c["taux"].items())
        depense += cout
        tot_or += p * c["or"]
        print("%-14s %-5s %6d %5d %7d %10.3f %9.3f %8d"
              % (ident, noeud, p, c["stam"], cout, g, g / c["stam"], p * c["or"]))
    print()
    print("TOTAL : %d passe(s), %d energie sur %d (reste %d), ~%d or"
          % (sum(p for _, p, _ in alloc), depense, args.energie, args.energie - depense, tot_or))
    print()
    print("--- commandes, dans l'ordre (une par une, en verifiant entre chacune)")
    for c, p, _cout in alloc:
        _u, ident, noeud, rep, _s, _t, _j = c["L"]
        print("python scripts/python/campagne_rejeu_boucle.py --replay "
              "data/replays/campaign/%s --armer --entree start --passes %d"
              "     # %s %s" % (rep.split()[0], p, ident, noeud))
    return 0


if __name__ == "__main__":
    sys.exit(main())
