"""CE QUE LA CHAINE D'ONSLAUGHT LIT -- le tier joue par le compte, et les ennemis d'un tier.

Deux lecteurs, aucune ecriture, aucun RPC. Ils vivent dans un module a part parce que ce sont des
lectures de SUBSTRAT (progression du compte, gameconfig) et non de la conduite de bataille : les
melanger a `onslaught_reel.py` ferait dependre toute lecture offline d'un module qui parle au jeu.

ASCII SEUL (console Windows en cp1252).
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import onslaught_ennemis as OE  # noqa: E402

VOIES = ("Imperial", "Xenos", "Chaos")

# `Idun.Source.IdunMeta.Logic.UserProgress.Units.GrandAllianceType`, lu dans `enums.tsv`.
# (!) LE NOM EST LE SEUL CANAL OU LA FAUTE SE VOIT. Le natif recoit un `Int32` qu'il ne validera
# pas : un ordinal juste aujourd'hui et faux au renumerotage suivant lancerait la MAUVAISE VOIE,
# sans erreur -- et sur la chaine reelle ca coute un jeton.
ORDINAL_ALLIANCE = {"Imperial": 0, "Xenos": 1, "Chaos": 2}


def progression_du_compte(voie):
    """(tier, board, ennemis TIRES, age) pour une voie -- ou `None` en le DISANT.

    (!) LE TIER NE S'ECRIT PAS EN DUR. Les trois voies etaient a 18 le 2026-08-23 ; le figer le
    rendrait faux a la premiere progression, EN SILENCE. Il se lit dans `user_progression.json`,
    comme le fait deja `sandbox_mode.dto_du_compte` pour construire son DTO de vagues.

    (!) LE TIRAGE EST DEJA FAIT, ET IL EST DANS CE FICHIER. Le tier 18 porte 12 types d'ennemis
    dans `tierWaves` ; le compte, lui, n'en a tire que 4. Les deux sont rendus : le tirage dit ce
    qui va REELLEMENT apparaitre, le sur-ensemble dit ce qui POURRAIT apparaitre.

    ⚠ CE FICHIER VIT HORS DU DEPOT (AppData) ET N'EST FRAIS QUE SI LE JEU TOURNE. On rend `None`
    plutot que de deviner, et on publie son age -- un tier lu dans une progression vieille de
    plusieurs heures peut ne plus etre celui du compte."""
    f = (Path(os.environ.get("USERPROFILE", Path.home())) / "AppData" / "LocalLow"
         / "Snowprint" / "Warhammer 40,000_ Tacticus" / "user_progression.json")
    if not f.exists():
        print("  (!) progression du compte INTROUVABLE (%s)" % f)
        return None
    age = time.time() - f.stat().st_mtime
    try:
        prog = json.loads(f.read_text(encoding="utf-8"))
    except ValueError as e:                                    # noqa: BLE001
        print("  (!) progression ILLISIBLE : %s" % e)
        return None
    par_alliance = ((prog.get("onslaught") or {}).get("data") or {})
    if voie not in par_alliance:
        print("  (!) voie `%s` absente de la progression. Presentes : %s"
              % (voie, ", ".join(sorted(par_alliance)) or "(aucune)"))
        return None
    batailles = (par_alliance[voie].get("battles") or {})
    dispo = sorted(int(k) for k in batailles if str(k).isdigit())
    if not dispo:
        print("  (!) aucune bataille enregistree pour `%s`" % voie)
        return None
    tier = dispo[-1]
    b = batailles[str(tier)]

    cfg, build = OE.config()
    tires = set()
    if cfg is not None:
        index = {}
        for w in ((cfg.get("battles") or {}).get("onslaught") or {}).get("tierWaves") or []:
            index[(str(w.get("tier")), w.get("round"), str(w.get("waveId")))] = w
        for v in (b.get("waves") or []):
            w = index.get((str(tier), v.get("round"), str(v.get("waveId"))))
            if w:
                tires.update(w.get("enemies") or [])
    return {"tier": tier, "board": (b.get("board") or {}).get("boardId"),
            "rounds": len(b.get("waves") or []), "tires": sorted(tires),
            "age": age, "tiers": dispo, "build": build}


def ennemis_du_tier(tier):
    """(types du tier, build) -- le SUR-ENSEMBLE, pas le tirage. `(None, motif)` si NON MESURE.

    (!) LE NIVEAU FAIT PARTIE DE LA CLE. `tyranNpc4Warrior:33` et `:35` sont deux cles distinctes
    pour `UnitConfigId$$op_Equality` : ecrire le mauvais suffixe n'apparie RIEN, sans erreur. On
    recopie donc les chaines de `tierWaves` telles quelles."""
    cfg, build = OE.config()
    if cfg is None:
        return None, build
    tw = ((cfg.get("battles") or {}).get("onslaught") or {}).get("tierWaves") or []
    types = set()
    for e in tw:
        if str(e.get("tier")) == str(tier):
            types.update(e.get("enemies") or [])
    return sorted(types), build
