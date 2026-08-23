"""TOUS les ennemis qu'un tier Onslaught peut faire apparaitre -- lus dans `tierWaves`.

    python scripts/python/onslaught_ennemis.py --tier 18
    python scripts/python/onslaught_ennemis.py --tier 18 --cibles

⚠ POURQUOI PAS DEPUIS UNE BC FORGEE. `sandbox_mode.py bc --onslaught-tier N` TIRE un echantillon
pondere (`weight`) des vagues du tier : une bataille ne voit qu'un sous-ensemble. Mesure du
2026-08-23 sur le tier 21 -- la BC forgee rend **5** types d'ennemis, `tierWaves` en porte **17**
sur ses 40 entrees. Enumerer depuis une BC raterait donc 12 types sur 17, en silence.

C'est la meme faute de forme que `bc_apparitions.py` corrige ailleurs : un recensement qui ne
visite qu'un echantillon rend un zero qui se lit comme une absence.

⚠ ET LE NIVEAU FAIT PARTIE DE L'IDENTITE. Le tier 18 melange des `:33`, `:34`, `:35`, `:36`,
`:20`, `:21` sur les MEMES `PureId` -- `tyranNpc4Warrior:33` et `tyranNpc4Warrior:35` sont deux
cles distinctes pour `UnitConfigId$$op_Equality`. Ecrire le mauvais suffixe n'apparie RIEN, sans
erreur (cf. `docs/rl/case-10046-debuff-d-environnement.md` §5bis).

⚠ LES 3 VOIES (Imperial / Chaos / Xenos) PARTAGENT LES MEMES VAGUES. `tierWaves` ne porte aucune
cle d'alliance ; seul `rewards` est ventile, et il est CROISE
(`rewards.Imperial = "abilityTokenCommon_Chaos"`). Le tier suffit donc a enumerer les ennemis :
l'alliance ne change que le butin.
"""
import argparse
import io
import json
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def config(build=None):
    if build is None:
        p = os.path.join(RACINE, "data", "symbols", "CURRENT")
        if not os.path.exists(p):
            return None, "data/symbols/CURRENT absent"
        build = io.open(p, encoding="utf-8").read().strip()
    f = os.path.join(RACINE, "data", "symbols", build, "gameconfig.json")
    if not os.path.exists(f):
        return None, "%s absent" % f
    brut = json.load(io.open(f, encoding="utf-8"))
    # ⚠ `fullConfig` est un BOOLEEN sur ce build, pas un objet -- la config vit sous
    #   `clientGameConfig`. Un `.get("fullConfig")` rend `False` et casse tout en aval.
    cfg = brut.get("clientGameConfig")
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    if not isinstance(cfg, dict):
        return None, "clientGameConfig illisible (%s)" % type(cfg).__name__
    return cfg, build


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", type=int, required=True)
    ap.add_argument("--cibles", action="store_true",
                    help="n'imprimer que la liste prete a coller dans --enhancement")
    ap.add_argument("--build", default=None)
    a = ap.parse_args()

    cfg, build = config(a.build)
    if cfg is None:
        print("REFUS : %s" % build)
        return 1
    ons = (cfg.get("battles") or {}).get("onslaught") or {}
    tw = ons.get("tierWaves") or []
    if not tw:
        # TRI-ETAT : une table vide n'est PAS << ce tier n'a pas d'ennemis >>.
        print("REFUS : `battles.onslaught.tierWaves` VIDE ou absent -- rien a enumerer.")
        return 1

    entrees = [e for e in tw if str(e.get("tier")) == str(a.tier)]
    if not entrees:
        tiers = sorted({str(e.get("tier")) for e in tw}, key=lambda x: (len(x), x))
        print("REFUS : aucune vague pour le tier %d. Tiers connus : %s"
              % (a.tier, ", ".join(tiers)))
        return 1

    # `parRonde` : quel type apparait a quel round -- utile pour comprendre une pose tardive.
    parunite = {}
    for e in entrees:
        for u in (e.get("enemies") or []):
            d = parunite.setdefault(u, {"rondes": set(), "n": 0})
            d["rondes"].add(e.get("round"))
            d["n"] += 1

    if a.cibles:
        print(",".join(sorted(parunite)))
        return 0

    print("build %s   tier %d   %d entree(s) de vague" % (build, a.tier, len(entrees)))
    print("%d type(s) d'ennemi distinct(s)" % len(parunite))
    print()
    print("  %-34s %-8s %s" % ("unitId (a ECRIRE tel quel)", "occur.", "rondes"))
    for u in sorted(parunite):
        d = parunite[u]
        print("  %-34s %-8d %s"
              % (u, d["n"], ",".join(str(r) for r in sorted(x for x in d["rondes"]
                                                            if x is not None))))
    # Le meme PureId a plusieurs niveaux : c'est LA cause de non-appariement silencieux.
    pur = {}
    for u in parunite:
        pur.setdefault(u.split(":")[0], []).append(u)
    multi = {p: v for p, v in pur.items() if len(v) > 1}
    if multi:
        print()
        # ASCII SEUL : la console Windows est en cp1252, un `print` non-ASCII leve
        # `UnicodeEncodeError` et fait passer un recensement JUSTE pour un script casse.
        print("(!) MEME PureId A PLUSIEURS NIVEAUX -- chacun est une CLE DISTINCTE :")
        for p, v in sorted(multi.items()):
            print("   %-28s %s" % (p, ", ".join(sorted(v))))
    print()
    print("A COLLER : --enhancement 'EnhancementDamageBoost=<sortie de --cibles>'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
