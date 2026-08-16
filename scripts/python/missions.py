"""Tes missions OUVERTES -- libelle officiel, avancement, echeance, et ce qu'elles exigent.

    python scripts/python/missions.py                  # hors mythiques
    python scripts/python/missions.py --avec-mythic    # tout

TROIS SOURCES, comptees SEPAREMENT (un total agrege cacherait qu'une source est vide ou
n'a pas ete lue) :

    quests.quests[].tasks[]                                (heros, intro, laundryList)
    liveEvents[].components[].quests.quests[].tasks[]      (battle pass, evenements)
    guilds.guildState.Quests[].tasks[]                     (guilde)

Les MYTHIQUES (`mythic_*`) sont ECARTEES par defaut -- et leur compte est DIT, jamais tu.

!! LA SOURCE EST LE FICHIER QUE LE JEU ECRIT, pas un RPC : `user_progression.json` sous
`%USERPROFILE%\\AppData\\LocalLow\\Snowprint\\...`. Il est reecrit en continu (mesure : 34 s
d'age en cours de partie), donc il est frais TANT QUE LE JEU TOURNE -- et perime des qu'il
est ferme. L'age du fichier est IMPRIME pour que ce soit visible, jamais suppose.

!! UNE TACHE PERIMEE RESTE DANS LE FICHIER. Mesure du 2026-08-16 : 8 taches y portaient un
`validUntil` deja PASSE (les quotidiennes et hebdos de la veille, non balayees). Elles sont
COMPTEES A PART et exclues des listes d'action -- les melanger ferait viser des cibles mortes.

!! Les libelles viennent d'i2 (`Quests/<localizationKey>`), pas d'une table recopiee ici : un
miroir fige se perimerait en silence. Un placeholder qu'on ne sait pas remplir est LAISSE
VISIBLE et COMPTE -- un texte tronque se lirait comme une phrase complete.

ASCII only en sortie (console Windows cp1252).
"""
import argparse
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

from engine.entities.effect_type import EffectType  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--avec-mythic", action="store_true", help="ne PAS ecarter les mythiques")
ap.add_argument("--progression", default=str(D / "user_progression.json"))
ap.add_argument("--sortie", default=str(REPO / "logs" / "missions.json"))
a = ap.parse_args()

# ⚠ ABSENT != VIDE. Sans le fichier on ne rend AUCUN chiffre -- un rapport a zero mission se
#   lirait comme << tout est fait >>, ce qui est exactement l'inverse de << pas mesure >>.
SRC = Path(a.progression)
if not SRC.is_file():
    print("progression INTROUVABLE : %s" % SRC)
    print("NON MESURE -- aucun compte n'est rendu. Le jeu a-t-il deja tourne sur ce poste ?")
    sys.exit(2)

I2 = json.loads((REPO / "data" / "i2_en.json").read_text(encoding="utf-8"))
t = SRC.read_text(encoding="utf-8", errors="replace")
J = json.loads(t[t.find("{"):])

BALISE = re.compile(r"<[^>]*>")
PLURIEL = re.compile(r"\[i2p_Plural\](.*?)(?=\[i2p_|$)", re.S)


def ascii_(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def nom_heros(uid):
    if not uid:
        return None
    return I2.get("Units/%s_ShortName" % uid) or I2.get("Units/%s_Name" % uid) or uid


def nom_effet(i):
    try:
        return EffectType(int(i)).name
    except (ValueError, TypeError):
        return "effet#%s" % i


def libelle(tache):
    """Le texte officiel du jeu, placeholders remplis quand on SAIT les remplir."""
    cle = tache.get("localizationKey")
    brut = I2.get("Quests/%s" % cle) if cle else None
    if not brut:
        return None
    m = PLURIEL.search(brut)
    if m:
        brut = m.group(1)
    p = tache.get("taskParameters") or {}
    remp = {
        "TARGET_AMOUNT": tache.get("target"),
        "AMOUNT": tache.get("target"),
        "HERO_NAME": nom_heros(p.get("heroId")),
        "UNIT_NAME": nom_heros(p.get("heroId")),
        "FACTION_NAME": I2.get("Factions/%s" % p.get("factionId")) or p.get("factionId"),
        "EFFECT_NAME": (I2.get("Effects/%s_Name" % p.get("unitEffect"))
                        or (nom_effet(p["unitEffect"]) if p.get("unitEffect") is not None else None)),
        "TRAIT_NAME": I2.get("Traits/%s_Name" % p.get("trait")) or p.get("trait"),
        "GAME_MODE": p.get("gameMode"),
        "FACTION_TRAIT": p.get("factionTrait"),
        "GAME_MODES": ", ".join(p["gameModes"]) if p.get("gameModes") else None,
    }
    for k, v in remp.items():
        if v is not None:
            brut = brut.replace("{[%s]}" % k, str(v))
    return BALISE.sub("", brut).replace("\n", " ").strip()


# ⚠ Un placeholder NON REMPLI reste dans le texte. On le COMPTE et on le DIT plutot que de le
#   masquer : un libelle tronque se lirait comme une phrase complete.
RESTE_PLACEHOLDER = re.compile(r"\{\[([A-Z_]+)\]\}")


def horodate(v):
    """`/Date(<ms>)/` ou un entier ms -> epoch secondes. None si on ne sait pas lire."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v / 1000.0
    m = re.search(r"(\d{10,})", str(v))
    return int(m.group(1)) / 1000.0 if m else None


MAINTENANT = time.time()


def reste(fin):
    """Le temps restant, en clair. `?` = PAS D'ECHEANCE LUE -- jamais lu comme `illimite`."""
    if fin is None:
        return "?"
    d = fin - MAINTENANT
    if d <= 0:
        return "EXPIREE"
    if d < 48 * 3600:
        return "%dh" % (d / 3600)
    if d < 400 * 24 * 3600:
        return "%dj" % (d / 86400)
    return "lointaine"


def contrainte(tache):
    p = tache.get("taskParameters") or {}
    bouts = []
    if p.get("heroId"):
        bouts.append("HEROS %s" % nom_heros(p["heroId"]))
    if p.get("unitEffect") is not None:
        bouts.append("EFFET %s" % nom_effet(p["unitEffect"]))
    if p.get("trait"):
        bouts.append("TRAIT %s" % p["trait"])
    if p.get("factionId"):
        bouts.append("FACTION %s" % p["factionId"])
    if p.get("gameMode"):
        bouts.append("MODE %s" % p["gameMode"])
    # `autres`, pas `reste` : `reste()` est la fonction d'echeance ci-dessus, et un shadow
    # local sur un nom de fonction du module est exactement le genre de piege silencieux.
    autres = {k: v for k, v in p.items()
              if k not in ("heroId", "unitEffect", "trait", "factionId", "gameMode")}
    if autres:
        bouts.append(ascii_(json.dumps(autres, ensure_ascii=False)))
    return " | ".join(bouts)


def recolte(quetes, source, ecarte_mythic, echeance=None):
    """Rend (taches ouvertes, nb quetes mythiques ecartees).

    `echeance` = fin de l'evenement porteur, en secondes epoch. La quete peut porter son
    propre `validUntil`, qui PRIME (il est plus specifique).
    """
    out, mythic = [], 0
    for q in quetes or []:
        nom = q.get("name") or ""
        if ecarte_mythic and nom.startswith("mythic"):
            mythic += 1
            continue
        fin = horodate(q.get("validUntil")) or echeance
        for x in q.get("tasks") or []:
            av, ci = x.get("amount") or 0, x.get("target")
            if ci is not None and av >= ci:
                continue                               # deja fini
            p = x.get("taskParameters") or {}
            lib = libelle(x)
            out.append({
                "source": source, "quete": nom, "type": x.get("type"),
                "amount": av, "target": ci,
                "libelle": lib, "contrainte": contrainte(x), "fin": fin,
                "trous": RESTE_PLACEHOLDER.findall(lib or ""),
                "hero": p.get("heroId"), "mode": p.get("gameMode"),
                "effet": p.get("unitEffect"), "trait": p.get("trait"),
                "faction": p.get("factionId"),
                "recompenses": q.get("rewards") or [],
            })
    return out, mythic


ecarte = not a.avec_mythic
taches, comptes, mythic_total = [], [], 0

lot, m = recolte(J.get("quests", {}).get("quests"), "quetes", ecarte)
taches += lot
mythic_total += m
comptes.append(("quests.quests (heros / intro / laundryList)", len(lot)))

par_ev = defaultdict(int)
n = 0
for ev in (J.get("liveEvents") or {}).get("liveEvents") or []:
    nom_ev = ev.get("liveEventConfigId") or ev.get("liveEventId") or "?"
    fin_ev = horodate(ev.get("visibleUntil"))
    for comp in ev.get("components") or []:
        lot, m = recolte(((comp.get("quests") or {}).get("quests")), "ev:%s" % nom_ev,
                         ecarte, fin_ev)
        taches += lot
        mythic_total += m
        n += len(lot)
        par_ev[nom_ev] += len(lot)
comptes.append(("liveEvents (%s)" % ", ".join(sorted(k for k, v in par_ev.items() if v)), n))

lot, m = recolte((J.get("guilds", {}).get("guildState") or {}).get("Quests"), "guilde", ecarte)
taches += lot
mythic_total += m
comptes.append(("guilds.guildState.Quests", len(lot)))

print("=== MISSIONS OUVERTES (les terminees sont ECARTEES) ===")
for k, v in comptes:
    print("  %-58s %3d tache(s)" % (k[:58], v))
print("  %-58s %3d" % ("TOTAL", len(taches)))
if ecarte:
    print("  %-58s %3d quete(s)   (--avec-mythic pour les voir)"
          % ("MYTHIQUES mises de cote", mythic_total))
mortes = [x for x in taches if x["fin"] is not None and x["fin"] <= MAINTENANT]
if mortes:
    print("  %-58s %3d tache(s)  (leur propre `validUntil` est PASSE)"
          % ("dont PERIMEES, encore dans le fichier local", len(mortes)))
print()

# ---------------------------------------------------------------- quasi finies
# Le levier le plus rentable n'est pas le pourcentage : c'est le RESTE ABSOLU. Une tache a
# 42 % de 42 500 000 est hors de portee ; une a 96 % de 50 se finit en une bataille.
print("=" * 100)
print("=== A DEUX DOIGTS D'ETRE FINIES (reste <= 12 unites, perimees exclues) ===")
print()
proches = [x for x in taches
           if x["target"] and x not in mortes and 0 < (x["target"] - x["amount"]) <= 12]
for x in sorted(proches, key=lambda y: y["target"] - y["amount"]):
    print("  RESTE %-4s  %-11s %-38s %s"
          % (x["target"] - x["amount"], reste(x["fin"]),
             ascii_(x["libelle"] or x["type"])[:38], x["quete"][:34]))
if not proches:
    print("  aucune.")
print()

# ---------------------------------------------------------------- par source
for src_pref, titre in (("quetes", "QUETES DE HEROS / PROGRESSION"),
                        ("ev:", "EVENEMENTS ET BATTLE PASS"),
                        ("guilde", "GUILDE")):
    lot = [x for x in taches if x["source"].startswith(src_pref)]
    if not lot:
        continue
    print("=" * 100)
    print("=== %s -- %d tache(s) ===" % (titre, len(lot)))
    print()
    for x in sorted(lot, key=lambda y: (y["quete"] or "", y["type"] or "")):
        pct = (100.0 * x["amount"] / x["target"]) if x["target"] else 0.0
        print("  [%3d%%] %5s/%-5s  %-11s %s"
              % (pct, x["amount"], x["target"], reste(x["fin"]),
                 ascii_(x["libelle"] or x["type"])))
        detail = "         %-34s %s" % (x["quete"][:34], x["contrainte"])
        print(ascii_(detail.rstrip()))
    print()

# ---------------------------------------------------------------- co-satisfaction
print("=" * 100)
print("=== CE QU'UNE MEME BATAILLE FAIT AVANCER ENSEMBLE ===")
print()

par_hero = defaultdict(list)
for x in taches:
    if x["hero"]:
        par_hero[x["hero"]].append(x)
print("--- amener CE HEROS fait avancer N taches ---")
for h, lot in sorted(par_hero.items(), key=lambda kv: (-len(kv[1]), kv[0])):
    quoi = ", ".join(sorted({x["type"] for x in lot}))
    print("  %-22s %-20s %2d : %s" % (h, ascii_(str(nom_heros(h)))[:20], len(lot), quoi[:52]))
print()

# Le regroupement par PATRON est celui qui montre le lot : `WinBattlesWithHero` demande que le
# heros soit DEPLOYE et SURVIVE -- or une equipe porte plusieurs unites, donc N de ces taches
# avancent DANS LA MEME BATAILLE. Le regroupement par heros, lui, ne peut pas le montrer.
par_type = defaultdict(list)
for x in taches:
    if x["hero"]:
        par_type[x["type"]].append(x)
print("--- MEME PATRON : ces taches se cumulent dans une seule bataille ---")
for ty, lot in sorted(par_type.items(), key=lambda kv: -len(kv[1])):
    besoins = sorted({(y["target"] or 0) - y["amount"] for y in lot})
    print("  %-22s %2d heros concernes   reste par tache : %s"
          % (ty, len(lot), ", ".join(str(b) for b in besoins)[:52]))
    print("      %s" % ascii_(", ".join(sorted(str(nom_heros(y["hero"])) for y in lot)))[:88])
print()

par_effet = defaultdict(list)
for x in taches:
    if x["effet"] is not None:
        par_effet[int(x["effet"])].append(x)
print("--- appliquer CET EFFET fait avancer N taches ---")
for e, lot in sorted(par_effet.items(), key=lambda kv: (-len(kv[1]), kv[0])):
    porteurs = sorted({str(nom_heros(x["hero"])) for x in lot if x["hero"]})
    print("  %-6s %-32s %2d : %s" % (e, nom_effet(e), len(lot), ascii_(", ".join(porteurs))[:46]))
print()

libres = [x for x in taches
          if not (x["hero"] or x["effet"] is not None or x["trait"] or x["mode"] or x["faction"])]
print("--- SANS CONTRAINTE : %d tache(s) -- n'importe quelle bataille les avance ---" % len(libres))
for x in sorted(libres, key=lambda y: -(y["amount"] / y["target"] if y["target"] else 0)):
    pct = (100.0 * x["amount"] / x["target"]) if x["target"] else 0.0
    print("  [%3d%%] %5s/%-5s %-34s %s"
          % (pct, x["amount"], x["target"], x["type"], x["source"][:30]))

# ---------------------------------------------------------------- pistes de recompenses
# ⚠ UNE PISTE N'EST PAS UNE TACHE, et aucun critere bati sur `tasks` ne peut la voir.
#   `arsenal_of_war` et `conflict_operations` n'ont AUCUNE tache : ce sont des points + des
#   paliers. Un balayage qui prouve << mes 3 chemins couvrent 100 % des `tasks` >> rend donc un
#   vert parfaitement rassurant et parfaitement incomplet. C'est l'utilisateur qui l'a signale.
#
# ⚠ CHAQUE PISTE NOMME SA PROPRE SOURCE DE POINTS (`pointsSourceComponentId`, un uuid de
#   composant) -- il n'y a PAS un compteur par evenement. Mesure : attribuer a toutes les
#   pistes le `points` de l'evenement rendait `se_progress_chests` a << 5 pris pour 2
#   debloques >>, ce qui est impossible ; sa vraie source est le MAGASIN de l'evenement
#   (`currencyAmountSpent` = 225), pas les 90 points. Un resultat impossible est ce qui a
#   revele l'erreur -- sans lui le chiffre passait pour bon.
CHAMPS_POINTS = ("points", "currencyAmountSpent", "progressPoints")


def points_de(comp):
    """Le compteur porte par un composant, et SOUS QUEL NOM. (None, None) si aucun."""
    for k in CHAMPS_POINTS:
        v = comp.get(k)
        if isinstance(v, (int, float)):
            return v, k
    return None, None


def seuil_palier(p):
    """Le seuil d'un palier. Le nom REEL est `requiredProgress` -- mesure : mes six premiers
    noms devines etaient tous faux, et c'est le refus de conclure qui les a affiches."""
    if not isinstance(p, dict):
        return None
    for k in ("requiredProgress", "pointsRequired", "requiredPoints", "threshold"):
        if k in p:
            return p[k]
    return None


def pistes():
    try:
        sys.path.insert(0, str(REPO / "scripts" / "python"))
        import gameconfig as GC
        TIERS = (GC._cfg().get("loot") or {}).get("tieredProgressRewards") or {}
    except Exception as e:
        print("  gameconfig ILLISIBLE (%s) -- les paliers ne sont PAS mesures." % type(e).__name__)
        return
    for ev in (J.get("liveEvents") or {}).get("liveEvents") or []:
        fin = horodate(ev.get("visibleUntil"))
        if fin is not None and fin <= MAINTENANT:
            continue
        comps = ev.get("components") or []
        par_uuid = {c.get("uuid"): c for c in comps if c.get("uuid")}
        rangs = [c for c in comps if c.get("progressRewardsConfigId")]
        if not rangs:
            continue
        entete = False
        for c in rangs:
            cid = c["progressRewardsConfigId"]
            pris = len(c.get("claimedIndices") or [])
            conf = TIERS.get(cid)
            src = par_uuid.get(c.get("pointsSourceComponentId"))
            if src is None:                       # pas de source nommee -> celle de l'event
                src = next((x for x in comps if points_de(x)[0] is not None), None)
            pts, nom_champ = points_de(src) if src else (None, None)
            if not entete:
                print("  %-34s fin %-10s" % ((ev.get("liveEventConfigId") or "?")[:34],
                                             reste(fin)))
                entete = True
            if conf is None:
                print("      %-36s pris=%-3d  config ABSENTE du gameconfig -- NON MESURE"
                      % (cid[:36], pris))
                continue
            seuils = [seuil_palier(p) for p in conf]
            if pts is None or any(s is None for s in seuils):
                print("      %-36s pris=%-3d / %-3d paliers  -- points ou seuil NON MESURE"
                      % (cid[:36], pris, len(conf)))
                continue
            ouverts = sum(1 for s in seuils if s <= pts)
            dispo = ouverts - pris
            note = ""
            if dispo > 0:
                note = "  <<< %d A RECLAMER" % dispo
            elif dispo < 0:
                note = "  <<< INCOHERENT (pris > ouverts) : source de points suspecte"
            else:
                # `ouverts=0` ne renseigne pas : c'est la DISTANCE au prochain palier qui dit
                # si la piste est a portee ou hors de portee dans le temps restant.
                suivant = min((s for s in seuils if s > pts), default=None)
                if suivant is not None:
                    note = "  (prochain palier a %s, reste %s)" % (suivant, suivant - pts)
                else:
                    note = "  (piste terminee)"
            print("      %-36s pris=%-3d ouverts=%-3d / %-3d  %s=%s%s"
                  % (cid[:36], pris, ouverts, len(conf), nom_champ, pts, note))
        if entete:
            print()


print("=" * 100)
print("=== PISTES DE RECOMPENSES (points + paliers) -- ce ne sont PAS des taches ===")
print()
pistes()
print("  NB les pistes `premium` s'ouvrent a la meme progression mais exigent d'AVOIR le pass.")
print("     Cette possession n'est PAS lue ici : un << a reclamer >> premium reste a verifier.")
print()

print("=" * 100)
print("=== CE QUI TOMBE EN PREMIER ===")
print()
datees = [x for x in taches if x["fin"] is not None]
print("  %d tache(s) portent une echeance ; %d n'en portent AUCUNE (permanentes ou non lue)"
      % (len(datees), len(taches) - len(datees)))
expirees = [x for x in datees if x["fin"] <= MAINTENANT]
if expirees:
    print("  !! %d tache(s) DEJA EXPIREE(S) et toujours en progression :" % len(expirees))
    for x in expirees:
        print("      %-36s %s" % (x["quete"][:36], x["type"]))
print()
for x in sorted([x for x in datees if x["fin"] > MAINTENANT], key=lambda y: y["fin"])[:14]:
    pct = (100.0 * x["amount"] / x["target"]) if x["target"] else 0.0
    print("  %-9s [%3d%%] %8s/%-8s %-34s %s"
          % (reste(x["fin"]), pct, x["amount"], x["target"],
             x["quete"][:34], ascii_(str(x["type"]))))

trous = [x for x in taches if x["trous"]]
if trous:
    print()
    print("  !! %d libelle(s) gardent un placeholder NON REMPLI -- le texte est INCOMPLET :"
          % len(trous))
    for x in trous:
        print("      %-36s %s" % (x["quete"][:36], ",".join(x["trous"])))

Path(a.sortie).write_text(json.dumps(taches, ensure_ascii=False, indent=1), encoding="utf-8")
print()
print("detail json : %s" % a.sortie)
