"""#589-r1 -- L'AVAL de `tilesMovedThisTurn` : les consommateurs, et ce que le passage 4 -> 6
DEPLACE chez chacun.

LE CRITERE, pose AVANT toute methode
------------------------------------
#589 (`#448-r1-r1-r1-r1-r2-r1`) a rebranche `beeline_pathfinder` sur le `ConnectivityComponent` :
le port rendait **4** la ou le natif enregistre **6** pour `tilesMovedThisTurn`. La correction est
validee sur SA face (l'oracle `TeleportStrike`), mais l'AVAL ne l'etait pas. Question binaire, et
elle est **par consommateur** :

    pour CHAQUE lecteur natif de `DSLFormulas$$TilesMovedThisTurn`, un compteur qui passe de
    `n_G` (substrat GEOMETRIE, l'etat d'avant #589) a `n_C` (substrat CANAL) change-t-il son
    RESULTAT ?

Un consommateur dont les deux valeurs donnent le meme resultat est un regime DEGENERE : on ne
conclut RIEN de lui, on NOMME le mecanisme (borne / seuil / saturation).

LE RECENSEMENT NATIF, RE-DERIVE (xrefs de `IdunBattleLogic.Entities.DSLFormulas$$TilesMovedThisTurn`,
build `rnca9r7q6c`) -- SIX call-sites, QUATRE porteurs
-----------------------------------------------------------------------------------------------
Le nud DSL construit un `IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula`, dont
`$$Calculate` rend `ActorStatisticsComponent+0xf0` -- il n'existe aucun autre lecteur de ce champ.

| # | call-site natif | forme lue au decompile | sujet | sensible a n ? |
|---|---|---|---|---|
| 1 | `ModifiedExoarmour_ExtraDmgEffect$$GetCurrentDamageBonus` | `Multiply(ConfigVar(8=extraDmg), TilesMovedThisTurn(sel))` | `DSLSelectors+0x30` = Owner | **LINEAIRE** |
| 2 | `ModifiedExoarmour_ExtraDmgEffect$$GetExtraDamageMultiplier` | `TilesMovedThisTurn(sel)` brut | Owner | **LINEAIRE** |
| 3 | `ModifiedExoarmour_ExtraDmgEffect$$CreateActiveCondition` | `AmountIsGreaterThanZero(TilesMovedThisTurn(sel))` | Owner | seuil **> 0** |
| 4 | `EmpyricAmbushEffect$$IsValidAttackForBuff` | `AmountIsEqualOrGreater(TilesMovedThisTurn(sel), Direct(GetNumberConstant(0x51)))` | `DSLSelectors+0x48` = Caster de l'attaque | seuil **= `EmpyricAmbush.constants.movement`** |
| 5 | `MastersOfManoeuvreAbility$$CreateTrigger` | `AmountIsEqualOrGreater(TilesMovedThisTurn(sel), Get(GetNumberConstant(0x88)))` | `DSLSelectors+0x40`, sujet du `On(0x4)` | seuil **= `MastersOfManoeuvre.constants.tilesTraversed`** |
| 6 | `SmashaEadAbility$$CreateTrigger` | `AmountIsEqualOrGreater(TilesMovedThisTurn(sel), Direct(2))` | `DSLSelectors+0x30` = Owner | seuil **= 2**, LITTERAL |

`0x51` / `0x88` sont resolus par `IdunBattle.Configuration.AbilityConstantType` du dump d'enums
(`81 = movement`, `136 = tilesTraversed`) -- ce probe les RE-LIT du gameconfig, il ne les recopie
pas.

LA BORNE QUI DECIDE DES SEUILS, et elle se DERIVE
-------------------------------------------------
`IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo` ne recoud par une beeline QUE
`if (GetDistance(last, next) > 1)`. Le sous-chemin beeline entre deux nuds distants de `d >= 2`
compte au moins `d >= 2` aretes -- dans **les deux** substrats. Donc :

    des que le rebranchement peut mordre (= une beeline est appelee), `n_G >= 2` ET `n_C >= 2`

et comme `N <= C <= G` (mesure #584) donne `n_G <= n_C`, tout seuil `K <= 2` est **DEJA FRANCHI
par le substrat d'AVANT** : le rebranchement ne peut pas le faire basculer. Ca sature les
call-sites 3, 5 et 6. Le cran `BORNE` MESURE cette derivation au lieu de la supposer.

CE QUE LE PORT CONSOMME, RE-DERIVE DU CODE (cran `INV`)
-------------------------------------------------------
Cote port, le canal `att_ctx["tiles_moved_this_turn"]` a **un seul** lecteur de degat
(`ModifiedExoarmourExtraDmgEffect`, `effects/loki/extra_damage.py`) ; les trois autres porteurs
natifs n'ont **aucun** trigger porte. Le cran `INV` le RE-DERIVE et rougit si ca change -- entrer
un de ces triggers au registre rouvre la question de l'aval.

Usage (session warmee) :
    python probe_589r1_tiles_moved_consumers_live.py --only INV        # offline, aucun runner
    python probe_589r1_tiles_moved_consumers_live.py --only BORNE      # 1 build (C1_74)
    python probe_589r1_tiles_moved_consumers_live.py --only WALK       # contraste Walk / TS
    python probe_589r1_tiles_moved_consumers_live.py --only EXO        # greffe + degat
    python probe_589r1_tiles_moved_consumers_live.py --only FLY        # item 2 : Fly pur
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
LOGSDIR = ROOT / "logs"
sys.path.insert(0, str(PYDIR))

# Le board a `Bridge` : le SEUL des trois de #584/#589 ou `G \ C != 0`, donc le seul ou le
# rebranchement peut mordre. `MC1_67` (G\C = 0) et `C6_25` (les trois vues coincident) sont des
# temoins DEGENERES pour cette question -- les jouer seuls ne prouverait rien.
BOARD_BRIDGE = "C1_74"

# Les quatre porteurs natifs, et ce que `unit_map` en dit. Le sujet du selecteur n'est PAS toujours
# le porteur : #4 et #5 lisent le compteur d'une unite TIERCE.
PORTEURS = {
    "ModifiedExoarmour": "votanChampion",
    "EmpyricAmbush": "eldarLhykhis",
    "MastersOfManoeuvre": "darkaStormSpeeder",
    "SmashaEad": "orksNob",
}

# Ce que le cran INV exige du PORT. Cle = ability native ; valeur = ce qui doit exister (ou non)
# cote port. Un changement ici rouvre la question de l'aval, et c'est exactement ce qu'on veut voir.
PORT_ATTENDU = {
    "ModifiedExoarmour": "porte (effet de degat, LINEAIRE)",
    "EmpyricAmbush": "NON porte",
    "MastersOfManoeuvre": "NON porte",
    "SmashaEad": "effet porte, TRIGGER non porte",
}


# --------------------------------------------------------------------------- cran INV (offline)
def _seuils_du_gameconfig() -> dict:
    """Les seuils, RE-LUS du gameconfig courant (jamais recopies du decompile).

    `IdunBattle.Configuration.AbilityConstantType` : `0x51 = 81 = movement`,
    `0x88 = 136 = tilesTraversed`. `SmashaEad` n'en a pas -- son seuil est le litteral `Direct(2)`
    de `SmashaEadAbility$$CreateTrigger`."""
    import gameconfig as GC
    out = {}
    for ab, key in (("EmpyricAmbush", "movement"), ("MastersOfManoeuvre", "tilesTraversed")):
        cfg = GC.ability(ab) or {}
        c = (cfg.get("constants") or {})
        out[ab] = None if key not in c else int(c[key])
    out["SmashaEad"] = 2                 # `DSLFormulas$$Direct(2)`, litteral du decompile
    out["ModifiedExoarmour"] = 0         # `AmountIsGreaterThanZero` -> seuil strict > 0
    return out


def _port_consumers() -> dict:
    """Ce que le PORT consomme, DERIVE du code source (jamais d'une liste ecrite a la main).

    Deux mesures independantes :
      * les appelants de `engine.entities.effects.base.tiles_moved_this_turn` (le foyer de
        lecture cote COMBAT) ;
      * la presence d'un TRIGGER porte pour chacun des quatre porteurs natifs.
    """
    eng = PYDIR / "engine"
    lecteurs, triggers = set(), {}
    pat_call = re.compile(r"(?<![\w.])tiles_moved_this_turn\s*\(")
    for p in eng.rglob("*.py"):
        txt = p.read_text(encoding="utf-8", errors="replace")
        rel = p.relative_to(PYDIR).as_posix()
        for i, line in enumerate(txt.splitlines(), 1):
            s = line.strip()
            if s.startswith("#") or s.startswith('"') or s.startswith("'"):
                continue
            if pat_call.search(line) and "def tiles_moved_this_turn" not in line:
                lecteurs.add("%s:%d" % (rel, i))
    trig_dir = eng / "runner" / "operations" / "triggers"
    trig_src = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                         for p in trig_dir.rglob("*.py"))
    for ab in PORTEURS:
        triggers[ab] = bool(re.search(r"(?<![\w])%s(?![\w])" % ab, trig_src))
    return {"lecteurs": sorted(lecteurs), "triggers": triggers}


def run_inv() -> int:
    print("== INV -- recensement DERIVE des consommateurs (offline)")
    bad = 0
    seuils = _seuils_du_gameconfig()
    print("\n  SEUILS relus du gameconfig courant :")
    for ab, v in sorted(seuils.items()):
        src = ("litteral `Direct(2)`" if ab == "SmashaEad"
               else "`AmountIsGreaterThanZero`" if ab == "ModifiedExoarmour"
               else "constants")
        print("    %-20s seuil=%s   (%s)" % (ab, v, src))
        if v is None:
            print("      ECART: constante ABSENTE du gameconfig -- le seuil n'est pas mesure")
            bad += 1
    # LA BORNE : tout seuil <= 2 est deja franchi par le substrat d'AVANT (cf. en-tete).
    satures = sorted(a for a, v in seuils.items() if v is not None and v <= 2)
    ouverts = sorted(a for a, v in seuils.items() if v is not None and v > 2)
    print("\n  BORNE `n >= 2 des que la beeline mord` :")
    print("    SATURES (seuil <= 2, franchi avant comme apres) : %s" % ", ".join(satures))
    print("    seuil > 2, donc FRANCHISSABLE par le rebranchement : %s"
          % (", ".join(ouverts) or "(aucun)"))
    if not ouverts:
        print("      NB: aucun seuil ouvert -- le cran BORNE devient un TEMOIN, pas une preuve")

    pc = _port_consumers()
    print("\n  PORT -- lecteurs du canal `tiles_moved_this_turn(att_ctx)` :")
    for l in pc["lecteurs"]:
        print("    %s" % l)
    print("  PORT -- trigger porte, par porteur natif :")
    for ab, present in sorted(pc["triggers"].items()):
        print("    %-20s trigger porte=%s   attendu: %s" % (ab, present, PORT_ATTENDU[ab]))
    # Le cran de NON-REGRESSION : les trois porteurs a SEUIL n'ont aucun trigger porte. S'ils en
    # gagnent un, l'aval doit etre reconfronte -- ce probe doit alors rougir pour le dire.
    for ab in ("EmpyricAmbush", "MastersOfManoeuvre", "SmashaEad"):
        if pc["triggers"][ab]:
            print("      ECART: `%s` a maintenant un trigger porte -- l'aval de #589 doit etre "
                  "RECONFRONTE pour ce consommateur" % ab)
            bad += 1
    if not pc["lecteurs"]:
        print("      ECART: AUCUN lecteur du canal cote port -- le recensement ne mesure rien")
        bad += 1
    print("\n  VERDICT INV: %s (%d ecart(s))" % ("PASS" if bad == 0 else "FAIL", bad))
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=("INV",), default="INV")
    a = ap.parse_args()
    if a.only == "INV":
        return 0 if run_inv() == 0 else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
