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

1. ~~**GAP prédiction-DryBush** (tâche #62)~~ **RÉSOLU** — cf. section #62 ci-dessous.
2. Branche -3 non isolée (toujours confondue avec LightCover) — lire la définition de tuile DryBush
   pour prouver la co-localisation 57↔LightCover.
3. `AverageDistance` ≈ `hexgeo.distance` mono-tuile — non exercé multi-tuiles (le natif moyenne sur
   les tuiles occupées).
4. ~~Confrontation end-to-end sur scénario Camouflage~~ **FAIT** — agreement per-tuile oracle natif
   (cf. #62 ci-dessous ; plus discriminant qu'`engine_validate` : chaque tuile candidate confrontée).

## #62 — RÉSOLU : terrain threadé au board de prédiction (`defender_on_cover`)

Fix (`engine/playbook/prediction.py`, `make_normal_attack_predictions`) :
`_on_cover = (scene.board.terrain_at(*t_pos) == LIGHT_COVER_TILE_ID)` (None si board KO), passé à
`attack_hits_with_modifiers` — mirror exact du call-site combat (`runner/operations/damage.py`).
Le natif évalue les gates TUILE aussi en prédiction (formule PARTAGÉE @180f0bf50) : LightCover
`AreEqual(coverPatch,target)` @180f556b0 et branche Camouflage -3 `HasTile(...57)` @181107180.
LightCover prédiction : même flag → même trou fermé (en single-step la présence de l'effet ⟺
sur-tuile, donc gate no-op en pratique — mais désormais fidèle, plus d'applique-sur-présence).

Validation live (`probe_62_campred.py`, seed 62001, MC1_67, session 71) : admecRuststalker (p-unit)
drivé sur (3,2) DryBush + bloodSanguinary (contrôle hors-cover) ; attaquants IA necroDestroyer
(6h Gauss R2) + astraOrdnance (3h Blast R3). Oracle = `decisionView.attackPlans[].ranked[]` NATIF
au tour IA vs offline per-tuile (TOL 3) :

- **24 lignes (18 DryBush + 6 contrôle) : 23/24 exactes.** La 24e = +748 FLAT (spread identique
  543 → même nb de coups, face #62 saine) = aura alliée `SpotterReworked` non portée → tâche #66.
  **#66 PORTÉ depuis** (SpotterReworked*Effect, extra_damage.py) : re-run du probe = **24/24**.
- Lignes discriminantes : u77 ranged dist≤2 → 6−3−2 plancher 1 (1088,1631) EXACT ; (3,3) mêlée
  adjacente → 6 coups pleins (gates IsRangedAttack/!IsMeleeAttack) EXACT ; u79 3h → plancher 1
  avec élévation par-tuile EXACT ; contrôle hors-cover EXACT.
- Counterfactuel pré-fix (`terrain_at`→None) : 7/18 lignes divergent = EXACTEMENT les ranged
  6-coups déclampées (6−1−2=3 vs 6−3−2=1 ; les 3-coups planchent à 1 des deux côtés, la mêlée ne
  touche pas au cover) → cas discriminant prouvé.
- **Piège `predOptimistic`** : le tag decisionView (regex `/Reduce(Dmg|Damage|Hits)|HitReduction/`,
  projection.ts) est SUR-LARGE pour `Camouflage_HitReduction` — le canal hits-malus EST foldé dans
  la prédiction native (verdict §Natif) → les lignes taguées restent comparables (le test aura #153,
  qui skippe ces lignes, ne peut PAS servir tel quel pour un porteur *_HitReduction).

Régression : stages 12345 = 100 % partout (préd 9/9, util 9/9, ability 10/10, move 15/15) ;
2468 = baseline exacte (2 résiduels structurels connus). Découvertes hors-scope du probe :
tâche #65 (FleshmetalGuns = groupes additional-hits attaquant cycliques de Volk non portés,
mesuré 3.2× sur u79 blackObliterator avant remplacement par astraOrdnance) et tâche #66
(SpotterReworked ci-dessus).
