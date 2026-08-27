"""CE QU'IL FAUT FARMER POUR ATTEINDRE UN OBJECTIF -- derive du jeu, SANS le planner.

    python scripts/python/plan_objectif.py --objectif "shiron:Gold 3"
    python scripts/python/plan_objectif.py --objectif "shiron:Gold 3" --objectif "Tigurius:Silver 1"
    python scripts/python/plan_objectif.py --objectifs data/objectifs.json
    python scripts/python/plan_objectif.py --lister-rangs

L'OBJECTIF EST UNE ENTREE, JAMAIS UNE CONSTANTE. Plusieurs objectifs se cumulent et PARTAGENT
le stock : deux heros qui reclament le meme composant ne le comptent pas deux fois chacun.

LA CHAINE, ET ELLE EST ENTIEREMENT DANS LE JEU
----------------------------------------------
    objectif (unite -> rang cible)
      -> units.lineup[<id>].upgrades[rang]     6 materiaux par rang, 20 rangs
      -> upgrades[<id>].crafting               explosion recursive, stock deduit A CHAQUE ETAGE
      -> battles.campaigns[].battles[].loot    taux par passe, par noeud
      -> staminaCost / maxAttempts             energie par passe, plafond de jetons par JOUR
      = composants a farmer, energie, or, jours

⚠ LE TAUX D'UN NOEUD = `loot.base` (verse a CHAQUE passe) + P(`loot.chanceOf`).
Ne lire que `chanceOf` SOUS-COMPTE LES ELITE D'UN FACTEUR ~13 et inverse l'arbitrage : mesure du
2026-08-26, `elite4 26` porte `base: [gold, upgArmR039]` ET `chanceOf: upgArmR039%1/12`, donc
1,083/passe et non 0,083. Consequence contre-intuitive : l'Elite est MOINS CHER a l'unite malgre
son cout d'energie double (9,2 contre 12 pour le Mirror equivalent). Temoin : 11 passes reelles
-> attendu 11,9, mesure +12 ; l'ancien modele predisait 0,9.
⚠ `loot.star1/star2/star3` sont des recompenses de PREMIERE obtention -- one-shot, elles n'entrent
PAS dans un calcul de farm.

⚠ `rank` (0-based) EST LE RANG, `progressionIndex` NE L'EST PAS. Confondre les deux a place une
unite 11 crans trop haut (Silver 3 au lieu de Stone 1) et rendu un plan a 152 d'energie au lieu de
1 530 -- facteur 10. `progressionIndex` est l'axe ETOILES/RARETE. Et `upgrades` liste les slots
DEJA POSES au rang courant : ne pas les deduire recompte un rang entier.

⚠ LES MACHINES OF WAR NE SE CALCULENT PAS AINSI, et ce script REFUSE de leur appliquer le modele
des heros. Elles n'ont ni rang ni materiaux : leur `lineup` n'a AUCUN `upgrades`, et en jeu elles
portent `rank: 0`, `upgrades: []`, `xpLevel: 1`, `progressionIndexDirectionAscension: null`. Leurs
deux axes sont ETOILES (`heroProgressionStepsMoW`) et NIVEAUX D'ABILITY (`abilityUpgradeCostsMoW`).
Leurs devises se DERIVENT de ce que porte la config -- 14 cles distinctes cote ability, 7 cote
etoiles -- et surtout PAS d'une liste ecrite ici : une premiere version en enumerait 4 et en
laissait tomber 10 EN SILENCE. Aucun de ces couts n'est de l'ENERGIE : on ne les additionne
jamais a ceux d'un heros, on les rend a part.

ASCII only en sortie (console Windows cp1252).
"""
import argparse
import collections
import json
import math
import re
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gameconfig as GCFG                          # noqa: E402
from sandbox_boss import session_vivante           # noqa: E402
from sandbox_mode import Jeu                       # noqa: E402

HOTE = "http://127.0.0.1:8765"

# Les 21 rangs, 0-based. `build_asset_manifest.extract_ranks` en extrait 21 icones
# (Stone 1-3 -> Mythic 1-3) indexees par `unit.Rank` : c'est la meme indexation.
# 21 rangs => 20 transitions, ce qui est exactement la longueur de `lineup[].upgrades`.
TIERS = ("Stone", "Iron", "Bronze", "Silver", "Gold", "Diamond", "Mythic")
RANGS = ["%s %d" % (t, i) for t in TIERS for i in (1, 2, 3)]

# 288 = 1 point / 5 min sur 24 h ; 220 = le refill quotidien par blackstone.
# ⚠ Le refill n'est pas un detail : sur un plan de 1 530 d'energie il fait passer de 6 jours a 4.
# C'est un CHOIX du joueur, d'ou le drapeau -- ne pas le figer.
ENERGIE_JOUR = 288 + 220


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def index_de_rang(nom):
    """`Gold 3` / `gold3` / `14` -> 14. Rend None si illisible -- on ne devine pas."""
    t = str(nom).strip()
    if t.isdigit():
        i = int(t)
        return i if 0 <= i < len(RANGS) else None
    plat = t.lower().replace(" ", "").replace("-", "")
    for i, r in enumerate(RANGS):
        if r.lower().replace(" ", "") == plat:
            return i
    return None


def or_par_passe(b):
    """L'or rendu par une passe -- `loot.base` porte `gold:<min>-<max>`, on prend la moyenne.

    ⛔ L'OR EST UN REVENU, PAS SEULEMENT UN COUT, et l'ignorer a fait choisir des noeuds
    STRICTEMENT DOMINES. Mesure du 2026-08-27 : a energie EGALE (60), `eliteMirror3 21` rend
    909 d'or la ou `mirror1 24` en rend 590 -- 319 d'or perdus pour rien. Sur le plan complet,
    l'or gagne (18 900 a 24 700) DEPASSE l'or de craft (16 100) : le plan se paie tout seul, et
    l'annoncer comme un cout net est faux.
    """
    for e in ((b.get("loot") or {}).get("base") or []):
        m = re.match(r"^gold:(\d+)(?:-(\d+))?$", str(e))
        if m:
            a = int(m.group(1))
            z = int(m.group(2) or a)
            return (a + z) / 2.0
    return 0.0


def candidats_par_materiau(cfg, upgrades):
    """TOUS les noeuds qui droppent chaque materiau -- on ne pre-selectionne PAS.

    Le choix depend du critere ET de la quantite voulue (le nombre de passes est un `ceil`),
    donc il ne peut pas etre fige ici. Une version precedente rendait << le moins cher en
    energie/unite >> et perdait l'or a chaque egalite.

    `debit` (somme sur tous les noeuds du materiau) sert a la borne JETONS : on peut farmer
    les trois le meme jour. Le choix de noeud, lui, n'en concerne qu'un.
    """
    best = {}
    for typ, lst in (cfg.get("battles") or {}).get("campaigns", {}).items():
        # Les campagnes d'EVENEMENT sont temporaires : les compter promettrait un debit qui
        # disparait a la fin de l'evenement.
        if typ == "Event":
            continue
        for c in lst:
            for b in c.get("battles") or []:
                lo = b.get("loot") or {}
                st, mx = b.get("staminaCost"), b.get("maxAttempts")
                if st is None or mx is None:
                    continue
                taux = collections.defaultdict(float)
                for e in (lo.get("base") or []):
                    mid = str(e).split(":")[0]
                    if mid in upgrades:
                        taux[mid] += 1.0
                ch = lo.get("chanceOf")
                if ch and "%" in ch:
                    mid, fr = ch.split("%")
                    if mid in upgrades:
                        taux[mid] += float(Fraction(fr))
                for mid, t in taux.items():
                    cur = best.setdefault(mid, {"debit": 0.0, "noeuds": []})
                    cur["debit"] += t * mx
                    cur["noeuds"].append({"camp": c["id"], "n": b["battleId"], "typ": typ,
                                          "stam": st, "taux": t, "max": mx,
                                          "or": or_par_passe(b)})
    return best


def choisir(noeuds, q, critere):
    """Le noeud a jouer pour obtenir `q` unites, selon le critere DEMANDE.

    Les deux criteres departagent par l'OR, et ce n'est pas cosmetique : c'est ce qui evite de
    prendre un noeud domine a cout egal.
      `energie` -- minimise l'energie ; a energie egale, le plus riche en or.
      `passes`  -- minimise le nombre de raids ; a passes egales, le plus riche en or.
                   Mesure : +52 d'energie (3 %, ~0,1 jour) pour +5 830 d'or sur le plan Shiron.
                   C'est le critere que le planner semble suivre, et il domine l'autre des que
                   l'energie n'est pas la ressource rare.
    """
    def cle(n):
        p = math.ceil(q / n["taux"])
        primaire = p * n["stam"] if critere == "energie" else p
        return (primaire, -p * n["or"])
    return min(noeuds, key=cle)


def exploser(mid, q, stock, feuilles, gold, upgrades, prof=0):
    """MRP : on soustrait le stock A CHAQUE ETAGE, pas seulement aux feuilles.

    Un intermediaire craftable deja en poche ne se re-craft pas -- et c'est ce que ferait une
    explosion qui ne deduirait qu'au bout. `stock` est MUTE : c'est ce qui fait que plusieurs
    objectifs partagent le meme stock au lieu de le compter chacun.
    """
    dispo = min(stock.get(mid, 0), q)
    stock[mid] = stock.get(mid, 0) - dispo
    reste = q - dispo
    if reste <= 0:
        return
    d = upgrades.get(mid) or {}
    cr = d.get("crafting")
    if cr and prof < 8:
        gold[0] += reste * (d.get("gold") or 0)
        for ing in cr:
            exploser(ing["id"], reste * ing["amount"], stock, feuilles, gold, upgrades, prof + 1)
    else:
        feuilles[mid] += reste


def est_mow(cfg, uid):
    """Une MoW n'a AUCUN `upgrades` dans `lineup` -- c'est le discriminant de CONFIG.

    Il en existe trois autres, live et concordants (`rank` 0, `upgrades` vide, `xpLevel` 1,
    `progressionIndexDirectionAscension` nul), mais celui-ci se lit sans session."""
    d = ((cfg.get("units") or {}).get("lineup") or {}).get(uid) or {}
    return not d.get("upgrades")


def cout_mow(cfg, uid, etat, cible):
    """Les DEUX axes d'une MoW, rendus SEPAREMENT -- ils ne sont pas commensurables.

    `cible` : dict optionnel {stars: N, active: N, passive: N}. Ce qui n'est pas demande n'est
    pas chiffre : on ne suppose pas que le joueur veut tout monter.

    ⛔ LES DEVISES SE DERIVENT, ELLES NE S'ENUMERENT PAS. Une premiere version sommait une LISTE
    BLANCHE de quatre cles (`gold`, `abilityTokenCommon`, `machinesOfWarToken`, `dust`) et
    laissait tomber les DIX autres EN SILENCE -- mesure du 2026-08-27 : `abilityUpgradeCostsMoW`
    porte 14 cles distinctes (dont `abilityTokenUncommon/Rare/Epic/Legendary/Mythic` et les
    `itemAscensionResource_*`) et `heroProgressionStepsMoW.costs` en porte 7 (dont
    `heroAscensionOrb*` et `mythicShards`). Un recenseur ne peut pas rendre zero sur ce qu'il ne
    visite pas : on accumule TOUTE cle rencontree.
    """
    u = cfg["units"]
    pas = u.get("heroProgressionStepsMoW") or []
    abil = u.get("abilityUpgradeCostsMoW") or []
    out = collections.Counter()
    non_mesure = []
    depart = etat.get("progressionIndex") if etat else None
    if cible.get("stars") is not None:
        if depart is None:
            non_mesure.append("progressionIndex (palier d'etoiles) NON MESURE")
        else:
            for i in range(depart, min(int(cible["stars"]), len(pas))):
                for k, v in ((pas[i] or {}).get("costs") or {}).items():
                    out[k] += v
    for champ in ("active", "passive"):
        if cible.get(champ) is None:
            continue
        cur = (etat or {}).get(champ)
        if cur is None:
            non_mesure.append("%s (niveau d'ability) NON MESURE" % champ)
            continue
        for lvl in range(cur, min(int(cible[champ]), len(abil))):
            for k, v in (abil[lvl] or {}).items():
                out[k] += v
    return out, non_mesure


def lire_etat(jeu):
    """L'etat des unites, par la voie SURE : chemin de champs NOMMES depuis l'executeur.

    ⛔ NE JAMAIS passer par `mapRanks` / `findProgInstances` : ce sont des SONDES qui font un
    `findInstanceByHeapScan` ET un invoke manage hors pompe. Elles ont tue le jeu deux fois le
    2026-08-26. Le chemin ci-dessous n'ancre rien, ne scanne rien, et passe par
    `queueOnMainThread` comme tout RPC de vue.

    Tri-etat : rend None quand ce n'est PAS MESURE -- jamais un dict vide, qui se lirait comme
    << aucune unite >>.
    """
    f = jeu.rpc("viewField", [{"cible": "executor",
                               "chemin": "_unitProgression._unitProgressionData"}], 60000) or {}
    if not f.get("ok"):
        return None, "viewField a REFUSE : %s" % ascii_(json.dumps(f, ensure_ascii=False))[:200]
    r = jeu.rpc("viewJson", [{"surPointeur": f["pointeur"], "chemin": "units",
                              "max": 800000}], 180000) or {}
    if not r.get("ok") or not r.get("json"):
        return None, "viewJson a REFUSE : %s" % ascii_(json.dumps(r, ensure_ascii=False))[:200]
    if r.get("tronque"):
        return None, "viewJson TRONQUE -- un JSON coupe se relit comme un roster incomplet"
    try:
        return json.loads(r["json"]), None
    except ValueError as e:
        return None, "JSON illisible : %s" % e


def main():
    # (!)LA DOCSTRING PORTE DES MARQUEURS NON-ASCII, ET `--help` LES IMPRIMERAIT.
    # Sur la console Windows (cp1252) ca leve `UnicodeEncodeError` : `--help` planterait au lieu
    # d'aider. On translittere donc a l'entree d'argparse, pas dans la docstring -- elle reste
    # lisible a la lecture du fichier, ou rien ne l'imprime.
    ap = argparse.ArgumentParser(description=__doc__.encode("ascii", "replace").decode("ascii"),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--objectif", action="append", default=[], metavar="SPEC",
                    help="'<unite>:<cible>', repetable. Heros -> cible = un RANG "
                         "('Gold 3', 'gold3', ou l'index). MoW -> 'stars=N[,active=N][,passive=N]'.")
    ap.add_argument("--objectifs", default=None, metavar="FICHIER",
                    help="JSON {\"<unite>\": \"<cible>\", ...} -- meme grammaire que --objectif.")
    ap.add_argument("--critere", choices=("energie", "passes"), default="passes",
                    help="ce qu'on minimise. `passes` (defaut) = le nombre de raids ; "
                         "`energie` = l'energie totale. Les deux departagent par l'OR. "
                         "Mesure du 2026-08-27 sur Shiron -> Gold 3 : `passes` coute 52 "
                         "d'energie de plus (3 %%, ~0,1 jour) et rapporte 5 830 d'or de plus. "
                         "D'ou le defaut : l'or est la ressource rare, pas l'energie.")
    ap.add_argument("--energie-jour", type=int, default=ENERGIE_JOUR,
                    help="defaut %d (288 de regen a 1/5 min + 220 de refill blackstone). "
                         "Sans le refill : 288." % ENERGIE_JOUR)
    ap.add_argument("--hote", default=HOTE)
    ap.add_argument("--lister-rangs", action="store_true")
    a = ap.parse_args()

    if a.lister_rangs:
        print("les 21 rangs, index 0-based (`rank` en jeu) :")
        for i, r in enumerate(RANGS):
            print("  %2d  %s" % (i, r))
        return 0

    demandes = {}
    if a.objectifs:
        p = Path(a.objectifs)
        if not p.exists():
            print("REFUS : %s introuvable." % p)
            return 2
        demandes.update(json.loads(p.read_text(encoding="utf-8")))
    for spec in a.objectif:
        u, sep, c = spec.partition(":")
        if not sep:
            print("REFUS : --objectif attend '<unite>:<cible>', recu %r" % spec)
            return 2
        demandes[u.strip()] = c.strip()
    if not demandes:
        print("REFUS : aucun objectif. `--objectif` ou `--objectifs` -- il n'y a pas de defaut,")
        print("        et c'est voulu : un objectif en dur serait faux des le lendemain.")
        return 2

    cfg = GCFG._cfg()
    upgrades = cfg.get("upgrades") or {}
    noms = {k: (v.get("name") or k) for k, v in upgrades.items()}

    sid = session_vivante(a.hote)
    if sid is None:
        print("REFUS : aucune session Frida vivante -- ni le rang courant ni l'inventaire ne")
        print("        peuvent etre lus, et on ne les rabat PAS sur zero.")
        return 2
    jeu = Jeu(a.hote, sid)
    print("session %d   gameconfig %s" % (sid, GCFG.identity().get("clientGameConfigVersion")))

    etats, err = lire_etat(jeu)
    if etats is None:
        print("REFUS : etat des unites NON MESURE -- %s" % err)
        return 1

    # --- resolution des objectifs -------------------------------------------------------------
    heros, mows, refus = [], [], []
    for q, cible in demandes.items():
        uid = GCFG.resolve_unit_id(q) or (q if q in (cfg["units"]["lineup"]) else None)
        if uid is None:
            refus.append("%s : unite INTROUVABLE" % q)
            continue
        etat = etats.get(uid)
        if etat is None:
            refus.append("%s (%s) : ABSENTE du roster -- non possedee ?" % (q, uid))
            continue
        if est_mow(cfg, uid):
            opts = {}
            for kv in str(cible).split(","):
                k, s2, v = kv.partition("=")
                if not s2 or k.strip() not in ("stars", "active", "passive"):
                    refus.append("%s est une MACHINE OF WAR : cible attendue "
                                 "'stars=N[,active=N][,passive=N]', recu %r" % (q, cible))
                    opts = None
                    break
                opts[k.strip()] = int(v)
            if opts:
                mows.append((q, uid, etat, opts))
            continue
        idx = index_de_rang(cible)
        if idx is None:
            refus.append("%s : rang cible illisible %r (voir --lister-rangs)" % (q, cible))
            continue
        heros.append((q, uid, etat, idx))

    for r in refus:
        print("  (!) %s" % r)

    # --- le BRUT, tous heros confondus --------------------------------------------------------
    brut = collections.Counter()
    for q, uid, etat, cible in heros:
        dep = etat.get("rank")
        if dep is None:
            print("  (!) %s : `rank` NON MESURE -- ecarte plutot que suppose." % q)
            continue
        if dep >= cible:
            print("  %-18s deja a %s (>= %s) -- rien a faire" % (q, RANGS[dep], RANGS[cible]))
            continue
        rec = cfg["units"]["lineup"][uid]["upgrades"]
        faits = set(etat.get("upgrades") or [])
        restants = [i for i in range(6) if i not in faits]
        for i in restants:
            brut[rec[dep][i]] += 1
        for r in range(dep + 1, cible):
            brut.update(rec[r])
        print("  %-18s %-9s -> %-9s  %d slot(s)  (%d deja pose(s) au rang courant)"
              % (q, RANGS[dep], RANGS[cible], len(restants) + 6 * (cible - dep - 1), len(faits)))

    if not brut and not mows:
        print("\nRIEN A FARMER.")
        return 0

    # --- l'INVENTAIRE, demande UNE fois pour tous les ids touches ------------------------------
    vus, pile = set(), list(brut)
    while pile:
        mid = pile.pop()
        if mid in vus:
            continue
        vus.add(mid)
        for ing in (upgrades.get(mid) or {}).get("crafting") or []:
            pile.append(ing["id"])
    stock = {}
    if vus:
        r = jeu.rpc("inventaireUpgrades", [{"ids": sorted(vus)}], 240000) or {}
        if not r.get("ok"):
            print("REFUS : inventaireUpgrades NON MESURE -- on ne rabat PAS sur zero.")
            print("        %s" % ascii_(json.dumps(r, ensure_ascii=False))[:250])
            return 1
        stock = dict(r.get("quantites") or {})

    feuilles, gold = collections.Counter(), [0]
    reste_stock = dict(stock)
    for mid, q in brut.items():
        exploser(mid, q, reste_stock, feuilles, gold, upgrades)

    best = candidats_par_materiau(cfg, upgrades)
    print()
    print("critere de choix : %s" % a.critere)
    print("%-28s %6s %7s %8s %9s %6s  %s"
          % ("composant a FARMER", "qte", "passes", "energie", "or gagne", "jours", "noeud"))
    print("-" * 104)
    e_tot, or_gagne, jours, absents = 0, 0.0, 0, []
    for mid, q in sorted(feuilles.items(), key=lambda kv: -kv[1]):
        cand = best.get(mid)
        if not cand or not cand["noeuds"]:
            absents.append(mid)
            continue
        n = choisir(cand["noeuds"], q, a.critere)
        # ⛔ UNE PASSE EST INDIVISIBLE. Compter `qte x energie/unite` rend un nombre de passes
        # FRACTIONNAIRE, donc une energie SOUS-ESTIMEE : mesure du 2026-08-27 sur Shiron ->
        # Gold 3, 1 530 en fractionnaire contre 1 586 en passes entieres (le planner dit 1 573).
        # Le cout par unite reste utile pour CHOISIR le noeud ; il ne vaut rien pour CHIFFRER.
        passes = math.ceil(q / n["taux"])
        e = passes * n["stam"]
        g = passes * n["or"]
        e_tot += e
        or_gagne += g
        jours = max(jours, math.ceil(q / cand["debit"]))
        print("%-28s %6d %7d %8d %9.0f %6d  %s %s (%s)"
              % (ascii_(noms.get(mid, mid))[:28], q, passes, e, g,
                 math.ceil(q / cand["debit"]), n["camp"], n["n"], n["typ"]))
    print("-" * 104)
    print("ENERGIE        %8d" % e_tot)
    print("OR de craft    %8d   (a payer)" % gold[0])
    print("OR gagne       %8.0f   (chaque passe en rend -- `loot.base`)" % or_gagne)
    print("OR NET         %+8.0f   %s"
          % (or_gagne - gold[0],
             "-- le plan se paie tout seul" if or_gagne >= gold[0] else "-- IL MANQUE DE L'OR"))
    print("BORNE JETONS   %8d jour(s)   -- aucun materiau ne plafonne au-dela" % jours)
    # (!)PAS DE VERDICT SUR UN ENSEMBLE VIDE. Sans composant a farmer (objectifs deja atteints,
    # ou uniquement des MoW), un << 0 JOUR(S), borne par l'ENERGIE >> se lit comme une mesure
    # alors que rien n'a ete mesure.
    if a.energie_jour > 0 and feuilles:
        jr = math.ceil(e_tot / a.energie_jour)
        print("BORNE ENERGIE  %8d jour(s)   -- a %d/jour, HORS stock d'energie courant"
              % (jr, a.energie_jour))
        print()
        print("=> %d JOUR(S), borne par %s."
              % (max(jours, jr), "l'ENERGIE" if jr >= jours else "les JETONS"))
    if absents:
        print()
        print("(!) %d composant(s) qu'AUCUN noeud de campagne ne droppe : %s"
              % (len(absents), ", ".join(ascii_(noms.get(m, m)) for m in absents)))
        print("    (chest, boutique, evenement -- ce script ne sait pas les chiffrer, il le DIT)")

    # --- les MoW, a part, parce que leurs couts ne sont pas de l'energie -----------------------
    for q, uid, etat, opts in mows:
        c, non_mesure = cout_mow(cfg, uid, etat, opts)
        print()
        print("MACHINE OF WAR %s (%s) -- axes SEPARES, aucun cout en energie :" % (q, uid))
        print("   etoiles %s -> %s" % (etat.get("progressionIndex"), opts.get("stars", "-")))
        print("   ability active %s -> %s | passive %s -> %s"
              % (etat.get("active"), opts.get("active", "-"),
                 etat.get("passive"), opts.get("passive", "-")))
        if not c:
            print("   (rien a payer)")
        for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
            print("   %-34s %d" % (k, v))
        for nm in non_mesure:
            print("   (!) %s" % nm)

    print()
    print("(!) NON COUVERT : le filtre sur les noeuds DEBLOQUES. Un noeud non atteint gonfle le")
    print("    debit et rend le cout optimiste -- verifier les noeuds cites avant de s'y fier.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
