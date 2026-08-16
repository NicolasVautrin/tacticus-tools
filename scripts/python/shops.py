"""Le tour des boutiques -- et surtout les offres GRATUITES encore disponibles.

    python scripts/python/shops.py            # les gratuites + le resume par boutique
    python scripts/python/shops.py --tout     # + le detail de chaque offre payante

LE CRITERE DE GRATUITE EST STRUCTUREL, PAS UN NOM. Un produit gratuit ne porte AUCUNE cle
`cost` -- mesure sur le war shop, dont la premiere entree est `draft_machinesOfWarTokens` x10
avec `purchasesLeft: 1` et rien d'autre. Le cas `cost.amount == 0` est traite aussi, mais il
n'a PAS ete observe : il est couvert par prudence et COMPTE a part, pour qu'on sache lequel des
deux existe vraiment.

!! GRATUIT NE VEUT PAS DIRE DISPONIBLE. `purchasesLeft` tombe a 0 une fois l'offre prise, et
l'entree RESTE dans la liste -- exactement comme un envoi reclame reste en boite. Attester par
la presence rendrait donc un faux positif a chaque passage. Le tri se fait sur
`purchasesLeft > 0`, et les gratuites deja prises sont comptees separement.

!! LE `slotCount` N'EST PAS LE NOMBRE DE PRODUITS. Il decrit la grille d'affichage. On compte
les produits, jamais les cases.

!! LECTURE SEULE, ET C'EST VOULU. Cet outil ne DECLENCHE aucun achat : il dit ou aller. Un
achat est un geste qui depense une ressource du compte, et il n'a pas a etre l'effet de bord
d'un inventaire.

Source : `user_progression.json` (ecrit en continu par le jeu) + i2 pour les libelles.
ASCII only en sortie (console Windows cp1252).
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))
D = (Path(os.environ.get("USERPROFILE", Path.home())) / "AppData" / "LocalLow"
     / "Snowprint" / "Warhammer 40,000_ Tacticus")

ap = argparse.ArgumentParser(description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--tout", action="store_true", help="lister aussi les offres payantes")
ap.add_argument("--progression", default=str(D / "user_progression.json"))
a = ap.parse_args()

SRC = Path(a.progression)
if not SRC.is_file():
    print("progression INTROUVABLE : %s" % SRC)
    print("NON MESURE -- aucune boutique n'est rendue (une liste vide se lirait comme")
    print("<< aucune offre gratuite >>, ce qui est l'inverse de << pas mesure >>).")
    sys.exit(2)

I2 = json.loads((REPO / "data" / "i2_en.json").read_text(encoding="utf-8"))
t = SRC.read_text(encoding="utf-8", errors="replace")
J = json.loads(t[t.find("{"):])
MAINTENANT = time.time()
BALISE = re.compile(r"<[^>]*>")


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def horodate(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v / 1000.0
    m = re.search(r"(\d{10,})", str(v))
    return int(m.group(1)) / 1000.0 if m else None


def reste(fin):
    """`?` = PAS D'ECHEANCE LUE. Jamais rendu comme `illimite`."""
    if fin is None:
        return "?"
    d = fin - MAINTENANT
    if d <= 0:
        return "EXPIRE"
    if d < 48 * 3600:
        return "%dh" % (d / 3600)
    return "%dj" % (d / 86400)


def nom_i2(rid, *gabarits):
    for g in gabarits:
        v = I2.get(g % rid)
        if v:
            return BALISE.sub("", v)
    return None


def _chests():
    """`.loot.chests` du gameconfig, ou {} s'il est illisible.

    Le gameconfig est un CONFORT ici, pas une dependance : sans lui on rend l'id brut du
    coffre. Un outil qui refuserait de lister les gratuites parce qu'un libelle manque
    echangerait une information utile contre une cosmetique."""
    try:
        import gameconfig as GC
        return (GC._cfg().get("loot") or {}).get("chests") or {}
    except Exception:
        return {}


CHESTS = _chests()


def nom_coffre(cid):
    """Le libelle d'un coffre. `defaultWoodChest` n'a AUCUNE cle i2 directe -- son nom passe
    par le `locaKey` que porte sa definition gameconfig (`Chests/DefaultWood`). Mesure : les
    gabarits `Chests/<id>` et `Chests/<id>_Name` rendent zero cle."""
    paliers = CHESTS.get(cid)
    if isinstance(paliers, list) and paliers:
        loca = paliers[0].get("locaKey")
        nom = BALISE.sub("", I2.get(loca, "")) if loca else ""
        if nom:
            return "%s (coffre, %d paliers selon progression)" % (nom, len(paliers))
    return "%s (coffre)" % cid


def libelle_produit(p):
    """Ce que le produit DONNE. Deux formes existent, mesurees :

        `reward`  : {id, amount, type|resourceCategory}   -- la plus courante
        `chestId` : un coffre, SANS `reward` ni `amount`  -- c'est la forme de la gratuite
                    quotidienne du shop `default` (`defaultWoodChest`)

    La premiere version ne connaissait que `reward` et rendait `None` sur la seconde : une
    offre gratuite dont on ne sait pas dire le contenu. Elle l'a AFFICHE au lieu d'inventer,
    et c'est ce qui a montre la forme manquante. Une 3e forme sortirait de meme en `FORME
    INCONNUE`, jamais en silence."""
    if p.get("chestId"):
        return nom_coffre(p["chestId"])
    r = p.get("reward")
    if not isinstance(r, dict):
        return "FORME INCONNUE : %s" % json.dumps(
            sorted(k for k in p if k not in ("id", "purchasesLeft", "maxPurchases")))
    rid, montant = r.get("id"), r.get("amount")
    cat, typ = r.get("resourceCategory"), r.get("type")
    nom = nom_i2(rid, "Units/%s_ShortName", "Units/%s_Name", "Resources/%s",
                 "Items/%s_Name", "Loot/%s") or str(rid)
    qualif = ""
    if cat == "Shards":
        qualif = " (fragments)"
    elif typ:
        qualif = " (%s)" % typ
    elif cat and cat != "Global":
        qualif = " (%s)" % cat
    return "%s x%s%s" % (nom, montant, qualif)


def cout(p):
    """(texte, est_gratuit, forme). `forme` distingue les DEUX gratuites possibles : celle
    SANS cle `cost` (la seule observee) et celle a `cost.amount == 0` (jamais vue).

    !! `cost` peut ne porter AUCUN `resourceType` (ex. `{"amount": 60}`). La devise implicite
    n'est PAS lue ici -- on ecrit `?` plutot que de supposer les gemmes. C'est sans effet sur
    la detection des gratuites, qui ne depend que de la PRESENCE de `cost`."""
    c = p.get("cost")
    if c is None:
        return "GRATUIT", True, "sans cle cost"
    if isinstance(c, dict) and c.get("amount") in (0, 0.0):
        return "GRATUIT", True, "cost.amount == 0"
    if isinstance(c, dict):
        return "%s %s" % (c.get("amount"), c.get("resourceType") or "?"), False, None
    return json.dumps(c, ensure_ascii=False)[:40], False, None


def boutiques():
    """Toutes les boutiques, d'ou qu'elles viennent -- le marchand principal ET celles qu'un
    evenement embarque dans un composant. Un balayage limite a `products.merchants` raterait
    les secondes, qui sont des boutiques a part entiere.

    !! MAIS LES DEUX CHEMINS SE RECOUVRENT. Mesure : `August2026Week2EventShop` est atteint
    par les deux, en DEUX OBJETS DISTINCTS de contenu IDENTIQUE (memes 24 ids de produits).
    Compter les deux doublait sa gratuite. On deduplique donc sur (nom, ids des produits) --
    pas sur l'identite memoire, qui dit `False` sur deux copies du meme JSON."""
    vus, out = set(), []
    sources = [(nom, m, None)
               for nom, m in ((J.get("products") or {}).get("merchants") or {}).items()]
    for ev in (J.get("liveEvents") or {}).get("liveEvents") or []:
        for c in ev.get("components") or []:
            for nom, m in ((c.get("products") or {}).get("merchants") or {}).items():
                sources.append((nom, m, ev.get("liveEventConfigId")))
    for nom, m, ev in sources:
        if not isinstance(m, dict):
            continue
        cle = (nom, tuple(p.get("id") for p in m.get("products") or []))
        if cle in vus:
            continue
        vus.add(cle)
        out.append((nom, m, ev))
    return out


lots = boutiques()
gratuites_dispo, gratuites_prises, formes = [], [], defaultdict(int)
resume = []

for nom, m, ev in lots:
    if not isinstance(m, dict):
        continue
    prods = m.get("products") or []
    fin = horodate(m.get("availableUntil")) or horodate(m.get("merchantExpiresOn"))
    n_grat = 0
    for p in prods:
        txt, gratuit, forme = cout(p)
        if not gratuit:
            continue
        n_grat += 1
        formes[forme] += 1
        # ⚠ une gratuite DEJA PRISE reste listee, `purchasesLeft` a 0
        entree = (nom, ev, fin, p)
        if (p.get("purchasesLeft") or 0) > 0:
            gratuites_dispo.append(entree)
        else:
            gratuites_prises.append(entree)
    resume.append((nom, ev, len(prods), n_grat, fin, m.get("dailyRefreshes"),
                   m.get("slotCount")))

print("=== BOUTIQUES : %d ===" % len(resume))
print("  %-30s %-22s %5s %5s %-8s %s"
      % ("boutique", "evenement", "prod", "grat", "reste", "refresh/jour"))
for nom, ev, n, ng, fin, refr, slots in sorted(resume, key=lambda r: (r[0], r[1] or "")):
    print("  %-30s %-22s %5d %5d %-8s %s"
          % (nom[:30], (ev or "-")[:22], n, ng, reste(fin), refr))
print()

print("=" * 92)
print("=== OFFRES GRATUITES ENCORE DISPONIBLES : %d ===" % len(gratuites_dispo))
print()
if not gratuites_dispo:
    print("  aucune. (%d gratuite(s) reperee(s) mais DEJA PRISE(S) -- cf. plus bas)"
          % len(gratuites_prises))
for nom, ev, fin, p in sorted(gratuites_dispo, key=lambda x: (x[0], str(x[3].get("id")))):
    print("  %-24s %-8s  %s"
          % (nom[:24], reste(fin), ascii_(libelle_produit(p))))
    print("      restant %s/%s   %s"
          % (p.get("purchasesLeft"), p.get("maxPurchases"), p.get("id")))
print()

if gratuites_prises:
    print("=== gratuites DEJA PRISES (elles restent listees, c'est normal) : %d ==="
          % len(gratuites_prises))
    for nom, ev, fin, p in sorted(gratuites_prises, key=lambda x: x[0]):
        print("  %-24s %-8s %s"
              % (nom[:24], reste(fin), ascii_(libelle_produit(p))))
    print()

print("=== par quelle FORME la gratuite s'exprime ===")
for f, n in sorted(formes.items(), key=lambda kv: -kv[1]):
    print("  %-22s %d" % (f, n))
print("  (si `cost.amount == 0` reste a 0, c'est que l'absence de cle est la SEULE forme)")
print()

if a.tout:
    print("=" * 92)
    print("=== DETAIL DE TOUTES LES OFFRES ===")
    for nom, m, ev in sorted(lots, key=lambda x: x[0]):
        if not isinstance(m, dict):
            continue
        print()
        print("--- %s%s ---" % (nom, (" [%s]" % ev) if ev else ""))
        for p in m.get("products") or []:
            txt, gratuit, _ = cout(p)
            print("  %-16s %-3s/%-3s  %s"
                  % (txt, p.get("purchasesLeft"), p.get("maxPurchases"),
                     ascii_(libelle_produit(p))))
