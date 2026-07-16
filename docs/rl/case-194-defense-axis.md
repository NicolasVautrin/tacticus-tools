# Case #194 — Axe DEFENSE (stat 3) : stat-mods → %-list de prédiction (tuile Thorns ×1.5)

**Status : RESOLVED côté PRÉDICTION (session 23) — face DÉFENSEUR portée + validée live
(max BIT-EXACT 6774, min à −3 = résidu d'arrondi min par-coup pré-existant ±1-3, indépendant
de ce port). Faces attaquant + combat/runner = tâches de suivi (#196/#197).**

## Symptôme mesuré
C2_19 seed 777, meph mêlée → worldJakhal debout sur la tuile **(2,2) [TileId Swamp]** :
oracle = engine × **1.5020 / 1.5003** ; disparaît dès que le jakhal quitte la tuile.
Réfutés par mesure : élévation (toggles inertes), effet-unité du jakhal (ne porte que
Skullsmasher/BoK — l'effet Thorns vit sur la TUILE, jamais posté sur l'occupant).

## Ground truth live (probes 194_stat, session 23)
- `combatSnapshot` jakhal@(2,2) : `defense = 50`, `statDelta.defense = −50` → **base Defense = 100**
  (contrôle : meph defense=100 sans mod). Constante Thorns `GetNumberConstant(config, 0x14)` = **50**.
- `statModSources` jakhal defense : `total=−50, residual=0`, source unique = entité 85
  (`sourceIsUnit=false` = l'entité-effet de la tuile).
- Arithmétique per-hit : oracle min/hit 1505 = round(1003×1.5), max/hit 2258 = round(1505×1.5)
  → conversion **POURCENT** (flat +50 donnerait 1053/1555 — exclu).

## Mécanisme natif (RE complète, VAs gqfc5mff6c)
1. **Pose** : `ThornsBlockMovementAbility.CreateBehaviour @1811c8d70` =
   `AddBlockEnteringUnitsEffect & AddStaticStatModifierEffectToOwner(effectType 0xb=11, stat 3=DEFENSE,
   Direct(GetNumberConstant(config, 0x14)))` ; selector `ThornsDefenseReductionEffect.CreateTargetSelector
   @180f47ea0` = `UnitsWithoutTrait(Units(tile, kind 1), 0x19=25=Immune)` → modification −50 sur le
   `DefenseComponent` des occupants non-Immune. La config tuile vient des **assets Unity**
   (`IdunUniverse.GetTileConfigurations @1807a7d60` = Map sur les `IdunVisualTileConfiguration`) —
   PAS du gameconfig client ni de la BC (vérifié : aucune ability de tuile dans `units.abilities`,
   la BC ne porte que les TileIds + les poids AI `Utilities.TileEffects`).
2. **Stockage** : `StatComponent` (DefenseComponent cctor @180f991c0) : `+0x48`=Initial(100),
   `+0x10`=ValueModification total, `get_Modifications` = Dict<sourceEntity, IModifier>
   (`Modify @180fadfc0` ; `GetValue()` = slot 0 interface = montant effectif, même lecture que
   `GetModificationFromEntity @180fadf10`).
3. **Consommation (PRÉDICTION)** : `CalculateDefenderModifiersForPrediction @181002c30` fetch le
   **DefenseComponent de la CIBLE** (call-site @181003066) →
   `CalculateModifiersFromStatModifications @181004380` :
   - gate `get_CurrentValue @180fa91d0 != Initial(+0x48)` (⟺ mods ≠ 0) ;
   - pour chaque (source → IModifier) : `v = GetValue()`, **négé** (param_3=1 côté défenseur) →
     entrée struct `{cond=1 @0x00, Nullable<int> v @0x20}` ;
   - le caller folde chaque entrée via `GetMultiplierFromDamageBonus @181005210` (lit le Nullable
     @0x20) = `1 + v/100` (`v<1 → 1 − (−v)/100`) → `DamageModifiers.Add` + `List.AddRange(
     damageModifiers@0x38, entries)` = **la %-list**, comme un EffectBonus d'effet.
   Thorns : −50 → negate → +50 → ×1.5 ✓ (= la mesure, exactement).
4. **Face ATTAQUANT** (@181000590, call @181000cac) : symétrique sur l'**AttackComponent**
   (cctor @180f95c80) de l'attaquant, negate=**0**, gated `contexte@0x08 != null` + interface
   slot 3 (`DAT_1831b7f78`, non élucidé). **Prouvée INERTE sur le chemin normal-attack** :
   #49 (aura Calgar +1298 Attack présente sur l'attaquant) validé bit-exact SANS cette
   contribution (+1298% aurait explosé la prédiction). NON câblée → tâche #196.
5. **Hors chemin** : `GetBaseDamageWithFixedPiercedArmor @181030d10` (pierce stats 0x1a/0x16/0x15 +
   `GetPiercingRatio @181559a40`, armure 0x10, boucle `GetDamageWithPiercing @1815598b0` =
   max(dmg×pierce/100, dmg−armor, plancher)) ne lit PAS le stat 3 — la Defense passe UNIQUEMENT
   par la conversion stat-mods→%-list ci-dessus.

## Correction du port (#49 avait la sémantique FLAT — code mort, jamais activé)
`engine/services/damage_modifiers.py::calculate_modifiers_from_stat_modifications` existait
(écrit pour #49) avec une interprétation **flat** (`ForSubtraction`/`ForAddition`, « debuff
Current→Initial ») — **fausse** (le natif pose la valeur dans le slot POURCENT @0x20). Sans
régression possible : le seul call-site (`calculate_attacker_modifiers_for_prediction`) est gaté
`apply_stat_mod_debuff=False` partout. Corrigée en entrées `PercentIncrease` signées
(le fold `get_multiplier_from_damage_bonus` porte déjà la formule 1±v/100 des deux signes).

## Port (prédiction, face défenseur)
- `engine/services/damage_modifiers.py` : sémantique corrigée (ci-dessus).
- `engine/playbook/scene.py` : `Scene.defstat_by_id` + `defense_stat(uid)` ; capture
  `_defense_stats_from_snapshot` (combatSnapshot : `initial = defense − statDelta.defense`,
  modification = 1 pseudo-source « live » = statDelta) dans `build_predictor` ET
  `refresh_shields` (DYNAMIQUE : la mod suit l'occupation de tuile → refresh par-pas, comme
  boucliers/armure). `from_state` (runner offline) : non alimenté → axe inerte (suivi #197).
- `engine/playbook/prediction.py::_add_positional_and_defender_mods` : fold
  `calculate_modifiers_from_stat_modifications(scene.defense_stat(tgt), negate=True)` → %-list.
- ⚠ Limitation documentée : capteur = statDelta (TOTAL) → 1 pseudo-entrée. Le natif folde
  CHAQUE source (produit des (1±vᵢ/100)) : exact à 1 source (le cas tuile), approximation si ≥2
  mods defense simultanées (rare) — `statModSources` par unité donnerait le per-source au prix
  d'un scan entités par pas.

## Validation live (session 23)
- **probe_194_stat** (géométrie pilotée, jakhal ramené sur (2,2)) : engine (4512, **6774**) vs
  oracle (4515, **6774**) — **max BIT-EXACT**, min −3 = résidu min par-coup PRÉ-EXISTANT
  (pré-fold : engine 3006 vs oracle 3009, déjà visible dans les samples ADJ/NOGATE, cf. #179) —
  PAS un artefact du port Defense.
- **probe_182 sweep** (mêmes classes de géométrie Trench, refresh par-pas) : ADJ 2/2, CASE3 2/2,
  NOGATE 3/3 MATCH — zéro régression.

## Même famille (couverte par construction côté prédiction)
`SpiderWeb_DefenseReduction` (33), `DryBush_DefenseBonus` (35), `ShrubBonusDefense`
(ctor @180f46ee0, cf. #126) : toutes = stat-mods DEFENSE sur occupants → le fold porté les
prend dès que la modification apparaît dans le statDelta live (aucun code par-effet requis).
Le PATHFINDING Thorns (BlockEnteringUnits) reste #131.

## Suivi
- **#196** : face ATTAQUANT — élucider le gate (provenance contexte@0x08, interface
  `DAT_1831b7f78` slot 3) avant tout câblage (+1298% naïf casserait #49).
- **#197** : face COMBAT/runner — mesurer si le dégât RÉEL (pas la prédiction) applique la
  Defense (site de consommation combat à RE : `CalculateModifiersFromStatModifications` est
  xref-prédiction-only) + tracking runner des mods defense on-enter/leave (compléter #128).
