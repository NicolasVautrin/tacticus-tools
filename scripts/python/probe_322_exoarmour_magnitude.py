"""probe #322 -- le MODELE DE MAGNITUDE de `ModifiedExoarmour_ExtraDmgEffect`, et sa REFUTATION.

LE CRITERE, pose AVANT toute methode
------------------------------------
> Existe-t-il UN modele qui explique 624 ET 4306, et qui tombe juste sur les SIX tuiles de melee ?

#312 avait laisse DEUX residus (case-312 SS 5) :
  R1 -- aucune combinaison simple de `extraDmg[50]` x mult 180 ne rend 624 ;
  R2 -- la tuile (4,0) mesure 4306 la ou `624 x n x M` donne 4308 (ecart STRUCTUREL de -2).

Ce probe ne fitte RIEN : il DERIVE la magnitude de la chaine native, puis REJOUE la chaine de
degat DEJA PORTEE avec cette magnitude, et confronte tuile par tuile.

LA CHAINE NATIVE, lue au decompile (build `rnca9r7q6c`)
-------------------------------------------------------
```
ModifiedExoarmour_ExtraDmgEffect$$GetCurrentDamageBonus
    = DSLFormulas.Multiply( ConfigVar(8 = extraDmg), TilesMovedThisTurn(Self) )

IdunBattle.Entities.Formulas.MultiplyAmount$$Calculate  ->  (int)a * (int)b     # produit d'ENTIERS
IdunBattle.Entities.Formulas.ConfigAmount$$Calculate    ->  AbilityConfiguration$$GetVariableForLevel
IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel :
    v = int(arr[clamp(level-1)]) ; si varType est dans `_variablesAffectedByRarityBonus`
    v = (int) Fix64.Round( Fix64(multiplierPct) / 100 * v )
```
=> `bonus = V * n` avec **`V = Round(mult% / 100 * extraDmg[level-1])`, UN ENTIER**, et
`n = TilesMovedThisTurn`.

LE PLACEMENT, lu au decompile puis rejoue par le port
------------------------------------------------------
`CreateEffectDamageBonusForAttack = EffectBonus.ForAddition(OwnerIsCaster & IsMeleeAttack, bonus)`
-> canal `DamageModifiers.additive @+0x10` -> `attacker_additive_pre=True`, deja porte (#75/#70) :
l'additif s'ajoute a la base PAR COUP **AVANT** percage/armure, puis traverse le %-list.

C'est CE placement qui ferme les deux residus, et l'un et l'autre pour la MEME raison : #312
raisonnait sur l'ecart APRES coup (`624 x n x M`), donc arrondissait au mauvais etage. Le natif
arrondit **une fois par coup**, sur `(base_percee + additif_perce) x M`.

Usage :
    python probe_322_exoarmour_magnitude.py                 # modele pur, aucun live
    python probe_322_exoarmour_magnitude.py --live          # + confrontation aiPlaybookPredict
ASCII only.
"""
from __future__ import annotations

import sys

# ---------------------------------------------------------------- ancrage de la fixture #312
# Les six tuiles de MELEE de `MDA_FIXTURE` (board MC1_67, seed 909, Damage=1000), telles que
# `probe_312_votan_prediction_gap.py` les MESURE. `M` = produit du %-list (1.25 a plat ; x1.5 de
# plus sur une tuile en surplomb). `n` = `path.Count - 1` (= `BattleQuery$$GetNumTilesMoved`).
# ATTENTION : ce sont des MESURES, pas des parametres a ajuster.
MELEE_TILES = [
    # (tuile,   n, M,     natif min, natif max)
    ((2, 0), 1, 1.25,   1624, 2124),
    ((2, 1), 2, 1.25,   2248, 2748),
    ((3, 2), 3, 1.25,   2872, 3372),
    ((4, 1), 4, 1.25,   3496, 3996),
    ((3, 0), 2, 1.875,  3372, 4122),
    ((4, 0), 3, 1.875,  4306, 5056),
]
# Regime de reference : Damage=1000 -> bornes de base (spread 20 %) 800/1200 ; le percage/armure
# de la cible les ramene a 400/600 (facteur 0.5, mesure #312 SS 5 "base per-coup post-percage").
BASE_LO, BASE_HI = 800, 1200
PIERCE_FACTOR = 0.5
HITS = 2

# Les trois regimes de CONFIG mesures par #312 SS 5 (levier `unit_stats` de `MDA.build_fixture`),
# ecart par tuile parcourue sur une tuile a %-list [1.25] :
#   (PassiveAbilityLevel, AbilityVariablesMultiplierPercentage, ecart mesure pour n, extraDmg brut)
CONFIG_REGIMES = [
    (50, 180, 1, 624, 277),
    (50, 100, 1, 346, 277),
    (10, 180, 1,  34,  15),
    (1,  180, 1,  12,   5),
    (1,  180, 2,  22,   5),   # le bras dit "non lineaire" par #312 -- il ne l'est pas
]


def config_value(raw: int, mult_pct: int) -> int:
    """`AbilityConfiguration$$TryGetVariableArrayForLevel` : `(int) Fix64.Round(mult/100 * v)`.
    Foyer PARTAGE avec le port (`AbilityConfiguration.get_variable_for_level`) -- ici on le
    re-derive a la main pour que le probe ne depende d'AUCUNE de nos couches."""
    return int(round(raw * mult_pct / 100.0))


def predict_tile(base: int, add: int, mult: float, hits: int = HITS,
                 pierce_factor: float = PIERCE_FACTOR) -> int:
    """La chaine `predict_attack_raw` reduite a ce que ce regime exerce, PAR COUP :
        d = base + additif                       # attacker_additive_pre : AVANT percage
        d = d * pierce_factor                    # GetDamageWithPiercing
        d = d * M                                # %-list (ApplyCappedModifiers)
        materialisation = Fix64.Round(d)         # _materialize, une fois PAR COUP
    puis somme des coups (`GetMultiHitAttackPrediction` appelle PredictAttackRaw par coup)."""
    per_hit = _round_half_even((base + add) * pierce_factor * mult)
    return per_hit * hits


def _round_half_even(x: float) -> int:
    """`FixMath.NET.Fix64$$Round` -- arrondi au plus proche. Les six tuiles ne portent que deux
    midpoints exacts (1747.5 et 1997.5), sur lesquels half-even et half-away coincident : ce
    probe ne les DISCRIMINE pas, et ne pretend pas le faire."""
    return int(round(x))       # round() Python = half-even


def report_config() -> bool:
    print("\n  R1 -- MAGNITUDE : V = Round(mult%% / 100 x extraDmg[level-1]), un ENTIER")
    print("  %-6s %-6s %-4s %-10s %10s %10s %8s" % ("level", "mult", "n", "extraDmg", "V", "ecart",
                                                    "verdict"))
    ok = True
    for lvl, mult, n, gap_meas, raw in CONFIG_REGIMES:
        v = config_value(raw, mult)
        # tuile a plat (%-list 1.25) : ecart = prediction AVEC additif - prediction SANS
        got = predict_tile(BASE_LO, v * n, 1.25) - predict_tile(BASE_LO, 0, 1.25)
        good = (got == gap_meas)
        ok = ok and good
        print("  %-6d %-6d %-4d %-10d %10d %10d %8s"
              % (lvl, mult, n, raw, v, gap_meas, "OK" if good else "KO (port=%d)" % got))
    return ok


def report_tiles() -> bool:
    print("\n  R2 -- LES SIX TUILES DE MELEE (V = 499 : level 50, mult 180, extraDmg[49] = 277)")
    v = config_value(277, 180)
    print("  %-8s %-3s %-7s %11s %11s %8s" % ("tuile", "n", "M", "natif min/max",
                                              "modele min/max", "verdict"))
    ok = True
    for tile, n, m, nat_lo, nat_hi in MELEE_TILES:
        lo = predict_tile(BASE_LO, v * n, m)
        hi = predict_tile(BASE_HI, v * n, m)
        good = (lo == nat_lo and hi == nat_hi)
        ok = ok and good
        print("  %-8s %-3d %-7s %11s %11s %8s"
              % (str(tile), n, m, "%d/%d" % (nat_lo, nat_hi), "%d/%d" % (lo, hi),
                 "OK" if good else "KO"))
    # Le modele REFUTE de #312, rejoue pour montrer OU il tombe -- une refutation vaut par son
    # contre-cas, pas par son intention.
    print("\n  modele #312 `ecart = 624 x n x M` (REFUTE) :")
    for tile, n, m, nat_lo, _ in MELEE_TILES:
        old = predict_tile(BASE_LO, 0, m) + int(624 * n * (m / 1.25))
        print("     %-8s -> %5d   (natif %5d)%s" % (str(tile), old, nat_lo,
                                                    "" if old == nat_lo else "   <- ECART"))
    return ok


def main() -> int:
    print("=== probe #322 -- modele de magnitude ModifiedExoarmour_ExtraDmg ===")
    ok1 = report_config()
    ok2 = report_tiles()
    ok = ok1 and ok2
    print("\n%s" % ("PROBE OK -- un seul modele explique les 4 regimes de config ET les 6 tuiles"
                    if ok else "PROBE KO -- le modele ne ferme pas, voir les lignes ci-dessus"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
