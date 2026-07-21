# Case #59 — Camouflage_HitReduction (effet 1134, trait Camouflage 1037, admecRuststalker)

> Verdict re-expert 2026-07-22, relu orchestrateur. Port livré + smoke live 4/4 ; acceptance = validator.

Jumeau RANGED de LightCover/Parry : canal défenseur `CreateEffectHitsBonusForAttack` (slot 0x23,
`OwnerIsTarget & IsRangedAttack`, plancher 1 hit).

## Natif

`Camouflage_HitReductionEffect.CreateEffectHitsBonusForAttack @181107180` :

```
EffectBonus.ForAdditionWithMinimum(
  trigger = OwnerIsTarget & IsRangedAttack,
  amount  = ConditionalAmount(
              HasTile(TilesWithTriggeredAbility(Tiles(Target@0x178), 0x39=57)),      -> Direct(-const 0x4d)
              ConditionalAmount(AmountIsGreater(AverageDistance(Caster@0x160, Target@0x178), Direct(2)),
                                Direct(-const 0x4b),    -> dist > 2
                                Direct(-const 0x2c))),  -> dist <= 2
  minimum = Direct(1))
```

- **Consommateur** : `AdditionalHitsFromEffects.GetAdditionalHitsFromEffectsInternal @180e59150`
  (itération globale des effets, slot 0x23 par effet, trigger OwnerIsTarget/OwnerIsCaster discrimine
  défenseur/attaquant) → formule PARTAGÉE `AttackHitsWithModifiersFormula.Calculate @180f0bf50`,
  consommée par les DEUX façades `DamagePrediction.GetAttackHits @18102f240` ET
  `AttackDamageOperation.GetAttackHits @180e613d0`. **→ PAS predOptimistic** : la réduction de coups
  s'applique en prédiction ET en combat.
- **Constantes** (gameconfig `traitVariables` — l'ability `Camouflage` n'existe PAS dans
  `gameconfig.abilities`, les slots numberConstant du config triggered sont seedés depuis les vars
  de trait) : `camouflageHitReduction_1`=1 (dist≤2, const 0x2c), `_2`=2 (dist>2, const 0x4b),
  `_3`=3 (Tall Grass, const 0x4d). i2 : « -1 hit ; -2 if >2 hexes ; -3 in Tall Grass ; min 1 ».
- **Tuile 0x39=57 = `TriggeredAbilityType.DryBushFireSpread`** = tuile DryBush (« Tall Grass » UI).
  Prouvé live : sur (3,2) MC1_67, DryBushFireSpread(57) et LightCoverAbility COEXISTENT (le porteur
  a `LightCover` ET `Camouflage_HitReduction`). HYPOTHÈSE (non lue) : co-localisation 57↔LightCover
  sur toute tuile Tall Grass → le port réutilise le flag `defender_on_cover` pour la branche -3.

## Port (arbre principal)

`CamouflageHitReductionEffect.create_effect_hits_malus_for_defense` (hits.py) — 3 branches
(`defender_on_cover`→-3 ; `dist>2`→-2 ; sinon -1 ; mêlée→None), `for_addition(True, -n)` plancher 1
chez le consommateur. Param `dist` ajouté au canal (base.py + `hits_malus_from_defender_effects` +
calcul `hexgeo.distance(attack_pos, t_pos)` dans `attack_hits_formula.py` — les deux façades
peuplent déjà `board`/positions → aucun call-site à éditer). Factory : `"Camouflage_HitReduction"`.

## Validation live (smoke re-expert, MC1_67, necroDestroyer 6h Gauss R2 + blackObliterator 6h HeavyRound R3 vs admecRuststalker)

| scénario | natif (UnitDamaged, coups d'arme) | offline | branche |
|---|---|---|---|
| mêlée dist 1 | 6 | 6 | gate IsRangedAttack → None |
| ranged dist 2 | 5 | 6−1 | dist ≤ 2 |
| ranged dist 3 | 4 | 6−2 | dist > 2 |
| ranged DryBush dist 2 | 1 | 6−3−2 (LightCover + plancher) | Tall Grass |

4/4 exact, chaque branche discriminante.

## Flags validator / suites

1. **GAP prédiction-DryBush** (tâche #62) : le call-site PRÉDICTION passe `defender_on_cover=None`
   → branche -3 dégradée en -1/-2 quand le porteur est sur DryBush (le combat est exact, terrain
   threadé). Fix : threader le terrain au board de prédiction comme le combat.
2. Branche -3 non isolée (toujours confondue avec LightCover) — lire la définition de tuile DryBush
   pour prouver la co-localisation 57↔LightCover.
3. `AverageDistance` ≈ `hexgeo.distance` mono-tuile — non exercé multi-tuiles (le natif moyenne sur
   les tuiles occupées).
4. Confrontation end-to-end `engine_validate.py` sur scénario Camouflage (le smoke = combat réel vs
   logique offline, pas le pipeline prédiction complet).
