# Case #184 — bloodMephiston normal-attack over-prediction (~1.49x) = DaughterOfTheAbyss (Atlacoya) -33% Psychic team aura, PAS un écart de hit-count

**Status: RÉSOLU (fable-solver). Cause racine = `DaughterOfTheAbyss_FriendlyDmgReductionPctEffect`
(passif d'Atlacoya `custoAtlacoya`) : le dégât PSYCHIQUE reçu par les alliés d'Atlacoya à ≤2 hexes
est réduit de `dmgReductionPct[lvl]`% (=33 @L50) → ×0.67, soit 1/0.67 = 1.4926 = le ~1.49x observé.
La sélection d'arme du port (candidate-tile adjacency) était DÉJÀ fidèle : natif ET port prédisent
3 coups mêlée à la tuile candidate. Le « HIT COUNT engine 3 vs oracle 2 » des sessions précédentes
était une FACTORISATION ERRONÉE d'un même total (2016,3024 = 2×[806,1210]×1.25 == 3×1003×1.25×
[0.8,1.2]×0.67 — sous-détermination d'un scalaire). L'hypothèse ORIGINELLE de la tâche (« -33%
modifier missing ») était la bonne — mal attribuée à l'attaquant, réfutée à tort via worldExecutions
(u91 attaque en Power, l'aura ne gate que Psychic → bit-exact trivialement).**

## Chaîne de preuve (mesures par étage, seed 2024 MC1_67, session 18)

1. **Harnais apples-to-apples vérifié** : `decisionView.attackPlans[].evals[].ranked[]` (projection.ts)
   calcule le dmg du candidat normal via `GetAllPredictions(unit, CANDIDATE_tile, ability)` — la même
   tuile que `predict_samples` passe à l'offline. Pas d'artefact tuile-courante-vs-candidate.
2. **Sweep par tuile** (`aiPredict` fresh, u89→81 sur 27 tuiles movable) : natif = 2016,3024
   appliedHits=3 PARTOUT (adjacent OU PAS, Δelev 0..3) sauf (4,6)/(3,7) = 1344,2016 appliedHits=2.
   → position-INDÉPENDANT pour le total ; per-hit CONSTANT = [672,1008] = 840×[0.8,1.2].
3. **Décomposition** : engine base = GetStat(Attack)=1003, mods=[×1.25 RapidAssault], hits=3
   → 3006,4515. Natif = 1003×1.25×[0.8,1.2]×3×**0.67** = 2016.03, 3024.05 EXACT.
4. **Cible discriminante** : `combatSnapshot.normalAttack` (paire vs ALLIÉ de Mephiston, hors aura
   ennemie) = 3009,4515 = la valeur engine → le ×0.67 n'existe QUE vs les alliés d'Atlacoya.
   u91 (worldExecutions, profil Power) : bit-exact sans réduction → gate PROFIL Psychic.
5. **Identification** : `decisionView.effects` d'u77 (Atlacoya, (6,8)) porte
   `DaughterOfTheAbyss_{ExtraDamagePct,OwnerDmgReduction,FriendlyDmgReductionPct}` (1417/1418/1419) ;
   les 4 cibles (79/81/83/85) sont à ≤2 hexes d'elle ; AUCUNE ne porte l'effet elle-même (aura
   évaluée à la calc, JAMAIS matérialisée sur les amis — même famille aveugle que #49).
   i2 : « Atlacoya takes -1892 Psychic Damage. Psychic Damage dealt to other friendly units within
   2 hexes of Atlacoya is reduced by 33%. Enemy Psykers within 2 hexes receive +20% Damage. »
   gameconfig `DaughterOfTheAbyss.variables.dmgReductionPct[L50]=33` (hors rarityBonus), `range=2`.

## RE natif (VAs gqfc5mff6c)

- `DaughterOfTheAbyssAbility.CreateBehaviour @180e1f540` : AddEffect(0x589)+AddEffect(0x58a)+
  AddEffect(0x58b) sur le CASTER (les 3 effets vivent sur Atlacoya).
- `DaughterOfTheAbyss_FriendlyDmgReductionPctEffect.CreateEffectDamageMalusForDefense @180f3cde0` :
  `(OwnerIsTarget & DamageProfileIs(0xd=Psychic)) → -ConfigVar(0x46=dmgReductionPct, abilityState)`.
- `DaughterOfTheAbyss_OwnerDmgReductionEffect.CreateEffectDamageMalusForDefense @180f3d070` :
  `(OwnerIsTarget & DamageProfileIs(0xd)) → Multiply(ConfigVar(0x12=dmgReduction), Direct(-1)@+0xd8)`
  (plat, rarity-scalé).
- `DaughterOfTheAbyss_ExtraDamagePctEffect.CreateEffectDamageBonusForAttack @180f3cb60` +
  `CreateTargetSelector @180f3cd00` : `SurroundingEnemies(owner, ConfigConst 0x16=range) &
  UnitsWithTrait(0x3ea=Psyker)` → +extraDmgPct%.
- Application state-wide : `CalculateDefenderModifiersForPrediction @181002c30` boucle « TOUS les
  EffectWithTarget actifs × leurs cibles » (cf. case-68) — le malus d'un effet porté par un TIERS
  atteint la cible via le TargetSelector de l'effet (SurroundingFriends rayon 2), PAS via la liste
  d'effets de la cible. Le COMBAT passe par la MÊME boucle (`CalculateAbilityDamage @18102cb50`
  slot 0xf → 2-args @181002a70 → 3-args @181002c30).

## Port (fix)

- `engine/entities/effects/base.py` : nouveau canal `create_aura_defense_damage_malus_for_ally(ctx)`
  (famille EffectWithTarget projetée HORS du porteur, côté défense).
- `engine/entities/effects/__init__.py` : agrégateur `aura_defense_damage_malus_from_units(carriers,
  ctx)` (symétrique défenseur de `aura_attack_damage_malus_from_enemies`).
- `engine/entities/effects/loki.py` : `DaughterOfTheAbyssFriendlyDmgReductionPctEffect` (aura -pct%
  Psychic amis rayon 2, exclut porteur), `DaughterOfTheAbyssOwnerDmgReductionEffect` (flat Psychic
  sur le porteur, canal défenseur standard, routage Nightshroud), `DaughterOfTheAbyssExtraDamagePctEffect`
  (aura +pct% Psykers ennemis rayon 2, gate trait cible).
- Câblage : `prediction._add_positional_and_defender_mods` (normal + spéciales) ET
  `runner/damage_model.defender_modifiers` (combat, symétrie décider/exécuter).

## Validation (avant → après)

- Seed 2024 : u89→81/85 = 2016,3024 EXACT (avant 3006,4515) ; u89→79 = 1410,2118 EXACT
  (×0.67 aura × ×0.70 Terrifying-mêlée déjà porté) ; att87/91/93 inchangés bit-exact.
- Audit 7 seeds MC1_67 (2024/777/500/42/31337/123/999) : voir PR — baseline 68/74.
- La sélection d'arme candidate-tile N'A PAS été touchée (elle était déjà fidèle → zéro risque
  de régression seed 500 att91 / seed 42 att89, le flip-flop venait du fix compensatoire
  « current-pos » qui simulait ×2/3 ≈ ×0.67 par accident).

## Gaps LATENTS découverts en chemin (hors périmètre #184, non codés ici)

1. **`MovementUtil.AreTilesAdjacent @18109d740` folde l'ÉLÉVATION** : `IsNeighbour(connectivité)
   && |Δelev| < 2`. Le port `battle_query.are_tiles_adjacent` ne teste que le voisinage graphe.
   Sans effet ici (Δelev=0 sur les paires du cas), mais la sélection d'arme mêlée/ranged (et tout
   consommateur d'adjacence « IsAdjacentTo ») divergera sur les bords de falaise. NB : `TileExtensions.
   IsNeighbourOf @180ec6030` = voisinage BRUT (sans élévation) — deux primitives distinctes, le port
   n'en a qu'une ; `TileExtensions.IsAdjacentTo @180ec5a50` = alias de MovementUtil (élévation incluse).
2. **Fallback de portée dans la sélection d'arme** : sweep (2) — le natif choisit l'arme RANGED
   uniquement depuis les tuiles d'où la cible est DANS LA PORTÉE de l'arme ranged ((4,6)/(3,7),
   hex-dist 2 = Range) et retombe sur MÊLÉE partout ailleurs (`GetAttackWeaponForDefaultNormalAttack
   @18105ea60` queue : `FindRangedWeapon(..., dist)` → null si hors portée → FindMeleeWeapon).
   Le port choisit ranged dès que non-adjacent. Sans effet sur les rows d'audit (candidats best =
   tuiles d'attaque légales), mais divergerait sur une prédiction hors-portée.

## Anciennes pistes (statut final)

- « per-unit AttackRangeType » : REFUTÉ (confirmé — `GetAbilityAttackRangeType @181059fe0` keyed par
  TYPE seul, constante =3 MeleeOrRanged pour l'attaque normale 69).
- « position/adjacency de la sélection d'arme » : REFUTÉ comme cause du 1.49x (sweep étape 2 :
  total position-indépendant ; hits natifs = 3 = port à la tuile candidate).
- « UnitFlag 21 = ForceRangedAttack » (`HasFlag(0x15)` @18105ec36) : existe dans le dispatch natif
  mais RIEN ne le pose sur Mephiston (xrefs DSLFactory.AddFlag : aucun call-site Mephiston) — piste
  écartée par la mesure (per-hit constant, pas un choix d'arme).
- BlessingsOfKhorne ×0.70 (#185) : le résidu tgt79 était en réalité Terrifying_ExtraDefense (-30%
  mêlée, DÉJÀ porté) × l'aura ×0.67 — avec le fix, u89→79 est EXACT. #185 à re-examiner : le x0.70
  attribué à BlessingsOfKhorne sur CE sample était l'aura Terrifying, pas BoK.
