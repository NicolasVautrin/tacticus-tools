# Fusionne un CATALOGUE d'unites dans une BC, sans toucher a son plateau.
#
# POURQUOI (mesure du 2026-08-17) : une BC de campagne embarque tout le roster deployable
# (`Units` = 177, dont les unites qu'on veut drafter, AUCUNE sur le plateau), alors qu'une BC
# de sandbox ne catalogue que ce que le montage a declare (68-70). Le draft de campagne marche
# pour cette seule raison. Controle a tuile EGALE : catalogue 68 -> rien n'apparait ;
# catalogue 177 -> l'unite est reelle.
#
# ON NE TOUCHE NI `PredefinedUnits` (le plateau) NI le board : uniquement `Units` et les tables
# d'abilities qu'il reference.
#
# SOURCE DU CATALOGUE -- deux formes acceptees, detectees automatiquement :
#   * sortie de `buildCampaignConfig` : la BC est a la RACINE          <- source VIVANTE, preferee
#   * replay decode                   : la BC est sous `BattleConfiguration`
# La source vivante est preferable : elle est toujours fraiche et conforme au roster reel, alors
# qu'un fichier de replay vit dans un repertoire qui TOURNE sur 10 entrees.
#
# Sortie console : ASCII uniquement (console Windows cp1252).

import json
import sys

SC = sys.argv[1] if len(sys.argv) > 1 else "."
f_cible = sys.argv[2] if len(sys.argv) > 2 else "bc-start-nue.json"
f_sortie = sys.argv[3] if len(sys.argv) > 3 else "bc-start-catalogue.json"
f_source = sys.argv[4] if len(sys.argv) > 4 else "bc-campagne-live.json"


def charger_bc(chemin):
    """Rend (bc, forme). `forme` NOMME d'ou la BC a ete tiree -- on ne devine pas en silence."""
    with open(chemin, "r", encoding="utf-8") as f:
        o = json.load(f)
    if isinstance(o, dict) and isinstance(o.get("BattleConfiguration"), dict):
        return o["BattleConfiguration"], "replay (sous BattleConfiguration)"
    if isinstance(o, dict) and "Units" in o:
        return o, "BC a la racine"
    raise SystemExit("ni `BattleConfiguration` ni `Units` dans %s -- ce n'est pas une BC"
                     % chemin)


src, forme_src = charger_bc(SC + "/" + f_source)
dst, forme_dst = charger_bc(SC + "/" + f_cible)
print("source  : %-28s (%s)" % (f_source, forme_src))
print("cible   : %-28s (%s)" % (f_cible, forme_dst))


def fusion_liste_par_id(base, ajout, cle="Id"):
    """Union : les entrees de `base` GAGNENT, celles de `ajout` completent."""
    vus = {u.get(cle) for u in base}
    return base + [u for u in ajout if u.get(cle) not in vus], \
        len([u for u in ajout if u.get(cle) not in vus])


def fusion_dict(base, ajout):
    n = 0
    for k, v in ajout.items():
        if k not in base:
            base[k] = v
            n += 1
    return base, n


avant = len(dst.get("Units") or [])
dst["Units"], n_units = fusion_liste_par_id(dst.get("Units") or [], src.get("Units") or [])
print("Units                : %d -> %d  (+%d)" % (avant, len(dst["Units"]), n_units))

for cle in ("ActiveAbilities", "PassiveAbilities", "Traits", "EnvironmentAbilities"):
    a = (dst.get("Abilities") or {}).get(cle)
    b = (src.get("Abilities") or {}).get(cle)
    if isinstance(a, dict) and isinstance(b, dict):
        n0 = len(a)
        dst["Abilities"][cle], n = fusion_dict(a, b)
        print("%-20s : %d -> %d  (+%d)" % (cle, n0, len(dst["Abilities"][cle]), n))

with open(SC + "/" + f_sortie, "w", encoding="utf-8") as f:
    json.dump(dst, f, ensure_ascii=False, separators=(",", ":"))

# Le plateau ne doit PAS avoir bouge : c'est un ajout de CATALOGUE, pas de lineup.
pred = dst.get("PredefinedUnits") or []
print("PredefinedUnits INCHANGE : %d joueur(s) -> %s" % (len(pred), [p.get("Id") for p in pred]))
print("ecrit : " + f_sortie)
