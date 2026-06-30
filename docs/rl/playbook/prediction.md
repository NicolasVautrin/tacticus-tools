# Prédiction de dégât / soin (état faithful)

But : reconstituer offline, fidèlement, le moteur de **prédiction** de dégât du jeu
(`DamagePrediction`) — la valeur min/max qu'un coup infligerait — qui alimente le scoring de
l'IA. Recalcul depuis les entrées (gameconfig + état capté), pas un cache d'outputs. Oracle de
validation = `aiPredict` live.

Frères : [architecture](architecture.md) · [scoring](scoring.md) · [pathfinding](pathfinding.md) ·
[playbooks](playbooks.md) · [status](status.md).

---

## 1. Prédiction OFFLINE depuis gameconfig — le DSL n'est PAS requis

Le DSL (`IdunBattle.DSL.*` / `Entities.Formulas.*`) est un vrai langage d'expression, mais ses
PROGRAMMES (arbres de formule) sont du C# construit en code, **pas** des données sérialisées.
`StatAmountFormula.Calculate` @180f22d40 ne stocke qu'un `statId` (ctor @180f230f0) et fait
`Σ GetStat(unit, statId)` → le DSL ne fait que **lire des stats**.

On n'a pas besoin du DSL : ses sorties résolues sont déjà des **données par niveau** dans
gameconfig (`AbilityConfigDto`) :

| Source | Contenu |
|---|---|
| `variables[clé][niveau]` | `minDmg / maxDmg / hpToHeal / hpToRepair / extraDmg / pierceRatio / armorIgnored …` |
| `constants` | `nrOfHits / nrOfTargets / damageProfile / armorReduction / HealPercentage / extraHit …` |
| `BC.Damage` (constantes de combat) | `ArmorPercentage 50, ElevationBonus 50, ClassBonus 25, AffinityBonus 50, DamageSpreadPercentage 20, RangedInMeleeReduction -50, TrenchReduction -50, OverkillDmgPctOfHealth 100, DamageProfiles[p].PiercingDamageRatio` |

⇒ « prédiction offline » = un **lecteur de données gameconfig** + une **scenario-math** validée contre
l'oracle. Soin/repair inclus (variables `hpToHeal`/`hpToRepair`), mais la scenario-math heal/repair
elle-même n'est pas encore RE'd (cf. BLOQUÉ).

---

## 2. Pipeline `PredictAttackRaw` @181032fb0 (ordre exact)

Noyau où convergent les 3 chemins (aiPredict / combatSnapshot / scorer). Lu en entier.

**Signature** : `PredictAttackRaw(state param_2, Scenario* param_3) → DamagePredictionResult* param_1`.
- `param_3` (AttackScenario, ~0xc8 o) : `[10]`=target, `[0xb]`=damage(Nullable), `[0xc]`=DamageProfile,
  `+0x84`=armorOverride(Nullable), `+0x7c`=Nullable, flags byte dans `[0xd]`/`[0x17]`.
- `param_2` : `+0x20`=match/registry, `+0x40`=attacker entity, `+0x10`=rules, `+0x48/0x50`=services.
- `param_1` (out, 0xc0) : `0x58` AccurateHealthDamage MinMax(`0x60`/`0x64`) ; `0x88` TotalDamage
  MinMax(`0x90`/`0x94`) ; `0x50` List<ProbableDamageEvent> (1 Add/coup) ; `0x98` List<HitDamage> ;
  `0xb1` MightCrit ; `0xb3` HasFlag(0x13) ; `0xbc` AppliedHits.

Ordre :
1. `base = max(0, scenario.damage)`, écrasé par variable d'ability `maxDmg` (id 0xd) si présente.
2. **MinMax base** : flag spread=0 → point `{base,base}` ; sinon `GetBaseDamageFix64` @181030ba0 =
   `{base − spread, base + spread + ExtraMaxDamage}` — spread = ±`DamageSpreadPercentage`(20 %),
   `ExtraMaxDamage` = asymétrie HAUT côté attaquant. Plancher `minDmg`.
3. **Armure** : `armorOverride = scenario.+0x84 ?? 0`, piercing par bout.
4. **Bonus plat** = variable d'ability `0xe`, ajouté identiquement aux 2 bouts.
5. **Tous modificateurs** : `CalculateBaseDamageWithAllModifiers` @18102d3f0 sur min ET max (§3),
   plancher minDmg + MathMax, puis `ApplyTraitDamageLimitsToDamage` @18102c650.
6. **Boucle multi-coups** (§4).
7. **Outcome dominant** (proba `remaining`) → `CalculateDamagePredictionScenario(prevHits=0)` → `param_1[3..9]`.
8. `TotalDamage`(0x88) = postArmor + armure absorbée ; `MightCrit`(0xb1) via vtable IsCrit ;
   `AppliedHits`(0xbc) = nrOfHits ; conversions Nullable→MinMax→ApplyCap.
9. **Flag ignore-armure / true-damage** (@2227 du .c COMPLET) : `HasTrait(attaquant, 0x420=1056) &
   HasEffect(attaquant, 0x59a=1434)` → scenario flag.
   > Résolu : §17.5 (« flag absent ») était FAUX — grep sur le `.compact.c` LOSSY ; le `.c` complet
   > l'a. **Ne jamais conclure « absent » depuis le décompilé compacté.**

### `CalculateBaseDamageWithAllModifiers` @18102d3f0
```
d = GetBaseDamageWithFixedPiercedArmor(state, Fix64(raw), critA.f0, critB.f0, target, comp, p5,
                                       flag8, flag9, critA.f8 + critB.f8)   # @181030d10
if critA: d = applyModif(slot 0x11, critA);  if critB: d = applyModif(slot 0x11, critB)
if critA: d = applyModif(slot 0x10, critA.f8); if critB: d = applyModif(slot 0x10, critB.f8)
if critB (+ sous-cond): d = critB.Value
```
Extrait des DEUX `DamageModifiers` (attaquant `@181000590` + défenseur `@181002c30`) : **pierce-extra**
(@0x20) et **armor-penetration** (@0x28, sommés att+def) → `GetBaseDamageWithFixedPiercedArmor` :
`pierce_eff = clamp(pierce + extra, 0, 100)` ; **`armor_eff = max(FixedArmor − penetration, 0)`**.
⇒ ignore-armure = une **pénétration**, et le scalaire `%-list`/additif s'applique APRÈS le perçage
(`ApplyCappedModifiers` @181000020, appelé à `+0x3d9` de @18102d3f0 — confirmé live `modifier-observe`).

### `CalculateDamagePredictionScenario` @18102ed00 (cœur par-outcome, porté tel quel)
```
eff.min = max(0, Fix64(dmgMM.min) − Fix64(prevHits))      # dmgMM @+0x10=min, @+0x18=max
eff.max = max(0, Fix64(dmgMM.max) − Fix64(prevHits))
shieldAbs = absorbShield(eff)                             # interface slot 0xb
healthDmg = max(0, eff − shieldAbs)
if target.FillUpStatComponent: healthDmg = MaxReduceByMinimum(healthDmg) → overkill
return { +0=prob%, +4=healthDmg MinMax(ApplyCap), +0x14=shieldAbs MinMax, +0x24=armorMM MinMax }
```
`prevHits` = previousHitsPrediction : chaque coup retire le dégât cumulé → ne compte que sur la santé
restante (explique les plages larges, ex. u80 4 coups 2136-6416).

---

## 3. Boucle multi-coups (@2390 de PredictAttackRaw)

- `perHitList = service.<slot0>(attacker)` : `Count(+0x18) = nrOfHits`, chaque élément 8 o
  `{lo32=hitDmg, hi32=critChance%}`.
- si `DamageProfile.HasTrait(0)` → SKIP la boucle. `remaining = Fix64(1)`.
- `for i in range(Count)` : `w = remaining × critChance%/100` ;
  `ev = CalculateDamagePredictionScenario(dmgMM=local_8c8, armorMM, prevHits=cumul, prob=w×100)` ;
  `result.events.Add(ev)` ; `remaining ×= (1 − w)`.

**Nombre de coups** = `GetDefaultAttackHits` @181032520 = `Max(0, nrOfHits + GetStat(17 ExtraHits) +
[melee? GetStat(23 ExtraHitsMelee)])`. Les bonus de coups de PRÉDICTION (PowerTrip +1, GetStuckIn +N)
s'ajoutent au-dessus (cf. §6/§7). `GenerateMultiHitAttackPredictions` @181409da0 boucle sur les
**membres de squad** (Blast/multi-membres), pas les coups, et rappelle ce noyau par membre.

---

## 4. La couche MODIFIER (`DamageModifiers`)

Accumulateur (offsets) : `additif`@0x10 (Fix64), `%-list`@0x18 (`List<{mult,cap}>`), `mult`@0x30
(Fix64=One), `detail`@0x38, **pierce-extra**@0x20, **armor-penetration**@0x28. `Empty` @181006370.

- `Add` @181005f10 `(acc, entry, extraNullable)` : `additif += FromInt(entry.DamageBonus)` (+5) ;
  `additif -= FromInt(entry.DamageReduction)` (+6) ; si `entry[+9]` → `%-list.Add(1 + round(v/100*100)/100)`
  avec cap (+10). **Ne route que additif/soustraction/percent** — pierce/pénétration viennent d'autres
  slots d'interface (attaquant 0x16/0x18, défenseur 0x19/0x1a/0x1b).
- `GetMultiplierFromDamageBonus` @181005210 = `1 + b/100` si `b≥1`, sinon `1 − |b|/100`.
- `ApplyCappedModifiers` @181000020 `(acc, value)` : pour chaque `{mult,cap}` de la `%-list` :
  `value = Clamp(Round(value × mult, 1), −cap, +cap)`.
- Construction : `Calculate{Attacker,Defender}ModifiersForPrediction` itèrent les EFFETS de l'unité
  (param_5 = collection d'effets actifs, dispatch interface slot 9) + `CalculateModifiersFromStat-
  Modifications` @181004380, et par effet appellent `GetDamageBonusForAttack` → `DamageBonus` →
  `GetMultiplierFromDamageBonus` → `Add`. **Pas d'affinité ni de classe dans le dégât de combat**
  (l'affinité est UI/méta). Leaves positionnels : Élévation (@181003ea0, sauté si effet 0x423),
  Ranged-in-melee (@181004700), Trench (@181004830).

**Placement = APRÈS perçage, PAR COUP** (preuve numérique u94 ×1.25 sur 2 armures différentes :
`[803,1206]×1.25×3 = 3012-4524` EXACT vs deux cibles ; un modifier-sur-base donnerait des nombres faux).

> Résolu : §16.5 plaçait le modifier `base × mod` AVANT spread — FAUX. Le scalaire s'applique
> post-perçage par coup (`ApplyCappedModifiers` dans @18102d3f0), pas sur la base.

---

## 5. Magnitude d'une variable = scaling par-unité (la grande découverte)

| Type de variable | Source | Scaling |
|---|---|---|
| **Variable d'ABILITY** (`ability.variables[level]`) | gameconfig, indexée par le **PassiveAbilityLevel** | `round(base[level] × AbilityVariablesMultiplierPercentage / 100)` |
| **Variable de TRAIT** (`traitVariables`) | `gameconfig.trait(name).variables` | **globale, NON scalée** |
| **Constante** (`GetNumberConstant`) | gameconfig `constants` | **NON scalée** |

- Le **multiplier** `AbilityVariablesMultiplierPercentage` est un champ BC par-unité, dérivé de la
  progression par `UnitConfigUtil.GetAbilityVariablesMultiplierPercentageForProgressionIndex`
  @181696230 (table per-progression-index, défaut 100). Seules les variables listées dans
  `variablesAffectedByRarityBonus` (= BC `VariablesAffectedByUnitRarityMultiplier`) sont scalées.
- `GetVariableForLevel` @181576fb0 rend la base brute ; le scaling est appliqué au build config
  par-unité (BC→runtime). `GetNumberConstant` @181576af0 = `GetStringConstant`→`Int32.Parse`.
- **Option A (offline)** : magnitude = gameconfig indexée par le `level` capté, read-only, zéro
  invocation native. L'`AbilityConfiguration` live n'est que le miroir par-instance de gameconfig.
  Seuls les effets **dynamiques** (stacks) exigent une lecture live (`dynamic` au cas par cas).
- **GOTCHA `level`** : `decisionView.effects[].level = 1` = **stack level**, PAS le niveau d'ability.
  Les variables d'ability sont indexées par le **PassiveAbilityLevel (=50)** → champ
  `BaseEffect.ability_level` distinct, seedé depuis l'unité.

**Capture per-entité (live, source de vérité)** : `AbilityVariablesMultiplierPercentage` vit sur
`UnitConfiguration` (`Id@0x10, VisualId@0x18, mult@0x74, tertiaryMult@0x78, Level@0x7C,
ActiveAbilityLevel@0xB8, PassiveAbilityLevel@0xBC`), PAS sur l'entité. Registre runtime =
`BattleQuery.GetUnitConfig(unitId)` ; `combatSnapshot` expose `unitConfig` par unité. Per-entité réel
confirmé : mult VARIE (u88=160, u94=200, autres=180).

---

## 6. Traits exploités DIRECTEMENT dans rawDamagePrediction

Au-delà du chemin effet→DamageModifiers, les traits sont lus **directement** par `PredictAttackRaw` et
ses helpers via `HasTrait`/`HasEffect`/`GetTraits`/`TryGetAbility`/`HasTriggeredAbility`. Contrat
(fonctions nommées) à auditer pour ne rien louper :

| Lieu | Trait / mécanisme |
|---|---|
| `GetBaseDamageWithFixedPiercedArmor` @181030d10 | `HasTrait(cible, 0x3f5=1013)` → hit-twice (×2) ; `GetPiercingRatio(profil, GetTraits)` → pierce trait ; `TryGetAbility(cible, 0x4b6=1206)`+var 0x51 → triple-hit |
| PredictAttackRaw @2227 | `HasTrait(att, 0x420=1056) & HasEffect(att, 0x59a=1434)` → ignore-armure / true-damage |
| `ApplyTraitDamageLimitsToDamage` @18102c650 | `ApplyGroupUnitDamageLimit` (×2) + `ApplyResilientTraitDamageLimit` (**Resilient**, cap/coup) + `ApplyImperviousTraitDamageLimit` (**Impervious**) + cap `HasTriggeredAbility(cible, 0x5d4)` → dmg ≤ `MaxHP × GetNumberConstant(0x12)/100` |
| PredictAttackRaw @2385 | `DamageProfile.HasTrait` |

---

## 7. Matérialisation des effets et des traits (framework offline)

Mirror fidèle du modèle natif « 1 classe par effet/trait ».

- **`engine/entities/effects/`** : `base.py::BaseEffect` (contrat = `create_effect_damage_bonus_for_attack`
  @180f0f5e0 / `create_effect_hits_bonus_for_attack` @180f12a30 / `get_armor_penetration` / `is_active`
  + cycle de vie) ; `loki.py` = 1 sous-classe par effet (RapidAssaultExtraDamageEffect @180f67940,
  PowerTripFullHealthEffect @180f64cf0 / cond @180f64cb0, PowerTripIgnoreArmorEffect @180f64fa0 no-op,
  KanOpenerEffect @180f65100) ; `magnitude.py` (résolution gameconfig, Option A) ; `factory.py`
  (`EFFECT_CLASSES`, inconnu→BaseEffect no-op). `EffectsState` = matérialisation seed one-shot +
  évolution (`active_effects` = non-consommés / non-expirés / is_active ; `on_attack` one-shot ;
  `on_turn_end` retrait RapidAssault si attaqué + décrément timers).
  > GOTCHA : `RemainingTurns=0` pour TOUS les effets seed-777 (passifs/aura, retrait par TRIGGER, pas
  > timer). `rem=0 → None` (permanent) ; seul `rem>0` est chronométré, sinon régression 8/11.
- **`engine/entities/traits/`** : `BaseTrait` (contrat §6 : `as_attacker_bonus_hits` /
  `as_attacker_pierce_bonus` / `as_attacker_ignores_armor` / `as_target_hit_multiplier` /
  `as_target_damage_cap`) ; `combat.py::GetStuckInTrait` (confirmé) + Resilient/Impervious (scaffold) ;
  `TraitFactory`. Traits = innés/statiques (`gameconfig.unit().traits`, jamais retirés).
- **Magnitude DSL native** : `ConfigAmount.Calculate` @180f171c0 ré-évalue par décision depuis
  l'instance d'effet (cfg = `AbilityConfiguration` via `effect.+0x48`, `key` = enum, `level` =
  `effect.+0x60`). On reproduit via Option A (gameconfig indexée level) — 2 écarts par conception :
  magnitude offline vs DSL live ; effets seed one-shot vs ECS temps réel.
- **Garde-fou EFFECT RECON (§17.4)** : un effet nommé « DmgBonus » n'implique PAS un bonus appliqué
  (peut être inactif, ou ExtraMaxDamage). Porter via statut-actif + magnitude recalculée, JAMAIS le
  nom. **Angle mort** : un trait qui contribue un modifier SANS poser d'effet-entité n'apparaît pas
  dans `ActiveEffectIds` → passer par l'axe stat-modification.

---

## 8. Cas d'étude u90 (orksKillaKan) — FERMÉ, agreement 11/11

Énigme « enveloppe oracle 2048-7592 » (ratio 3.7×, asymétrique). Démontée pièce par pièce, sans fitting
(value-dump live = confirmation) :

| Pièce | Valeur | Source |
|---|---|---|
| **Arme** | Projectile, **pierce 15**, RANGED (≠ Chain 20) | `FindAttackWeapon` @1811aeb80 ; sélection par PORTÉE/atteignabilité |
| **Pénétration** | **499** = `round(armorIgnored[50]=277 × 1.80)` | PowerTrip (var ability scalée par mult 180), champ @0x28 attaquant |
| **Coups** | **6** = 3 Projectile + 1 PowerTrip (PV pleins) + 2 GetStuckIn (`floor(hits/2)`) | GetDefaultAttackHits + PowerTrip_FullHealth + GetStuckIn |
| **Position** | ancrée à `decisionView.attackPlans[].ranked[0]` = (5,4), dist 2 | la prédiction est relative à UNE position d'attaque |

- per-bout `[1850,2774] − (2008−499)` = `[341,1265]` ×6 = **[2046,7590] ≈ oracle [2048,7592]** (±2 Fix64).
- **GetStuckIn = prédiction OPTIMISTE** : `GetStuckInAbility` @180f83280 / trigger @180f83350
  (`On(8) & CurrentHitIndex.IsOdd & OwnerIsCaster & !(MinDistance>2)`) / chance @180f83460
  (ConfigConst 0x2a=30 / 0x33=100). À la position d'attaque (within range 2), la condition de CHANCE
  réelle est 30 % (1 seul ami adjacent), mais l'oracle compte les +2 coups à dmgMin ET dmgMax → le
  moteur résout `Maybe(GetBonusHitChance)` comme « atterrit » (tag `predOptimistic`).
  `GetStuckInTrait.as_attacker_bonus_hits` = `+floor(hits/2)` sur **within_range2 seul**, sans gate sur
  la chance.
- PowerTrip RE'd : `PowerTrip_FullHealthEffect.CreateEffectHitsBonusForAttack` @180f64cf0 =
  `ForAddition(extraHit=1)` gaté présence d'effet (PV pleins) → +1 coup ; `PowerTrip_OnAttackAbility`
  @181111e40 = réduction d'armure STATEFUL de la cible (pas un modifier de prédiction) ;
  `PowerTrip_IgnoreArmorEffect.CreateEffectDamageBonusForAttack` @180f64fa0 = no-op (la pénétration est
  bâtie DIRECTEMENT dans `CalculateAttackerModifiersForPrediction` qui lit la config PowerTrip).

> Résolus (pour éviter les re-erreurs) :
> - arme Chain → **Projectile** (la sélection d'arme dépend du contexte mêlée/ranged à la position, pas
>   du 1er match `hits==normal_hits`).
> - « 6 coups = BigTarget » → **FAUX, c'est GetStuckIn** (`BigTargetAdjacentEffect` @180f33ac0 =
>   condition `OwnerIsTarget & IsRangedAttack` sur friends adjacents → N/A ici).
> - GetStuckIn « ×2 doubling » → **FAUX** : vrai = `+floor(hits_post_PowerTrip / 2)` = floor(4/2)=2.
> - défenseur u86 contribue **ZÉRO** modifier (`CalculateDefenderModifiersForPrediction` @181002c30 :
>   ses effets n'ont aucune méthode de défense).

⇒ **AGREEMENT 11/11** (les 4 cibles à réduction restent hors compte propre = OPT). RIEN COMMITÉ.

---

## 9. Prédiction de SOIN (heal) — RE complet + port offline

La chaîne soin est **entièrement RE'd et offline-calculable** (manque #1 / [`status.md`](status.md) §3.1
débloqué côté heal). Tout est dans `engine/predict.py` (PARTIE 3), porté 1:1.

| Étape native | VA | Formule |
|---|---|---|
| `HealAbility.HealAmount` | `@180e345b0` | `healAmount = StatAmount(weapon) × max(WeaponHighestHits, 1)` |
| `DamagePrediction.PredictHeal` | `@181037180` | accumule bonus-soin d'effets → caps group/boss → `MaxFillUp` |
| `FillUpStatComponent.MaxFillUp` | `@180f9b790` | `effective = min(healAmount, maxHP − curHP)` (soin effectif, plafonné aux PV manquants) |
| `HealUtility.Evaluate` (Weight[Heal=44]) | iter `@1810e16f0`, W via `.cctor @1810cfd10` | `U = (effective / (maxHP + 1)) × 100 × friendSign × bossMod` |
| `GetUnitUtilityModifier` | `@1810cfc80` | `bossMod = 2` si cible boss, sinon `1` |
| `ProbableHealEvent..ctor` | `@1811359a0` | `{target@0, (curHP, effective)@8, Probability@0x10 = 1.0}` |
| `Playbook.CalculateUtilityFromHealEvent` | `@1814aac80` | `Σ_cibles  Probability × U` |

- `friendSign = +1` si la cible est ALLIÉE du caster, `−1` sinon (soigner un ennemi = utilité négative).
- `W_heal = 100` (`HealUtility.cctor`, `Fix64.FromInt(100)`).
- `StatAmount`/`WeaponHighestHits` = builders DSL (`StatAmountFormula`) lisant la stat de l'arme de
  l'ability soin → **sourçables du gameconfig** comme le dégât (§1 ; magnitude scalée par
  `AbilityVariablesMultiplierPercentage` comme §5 si la variable y est soumise).
- Soin **négatif** (= dégât) : branche `MaxReduce`, non portée (cas rare).

**Porté + sanity-check** : `heal_amount`/`predict_heal_effective`/`heal_utility`/`heal_action_utility`
(cohérence math vs RE OK : `amount(1819,2)=3638`, cap `min(heal,missing)`, full HP→0, ennemi<0, boss×2).
**RESTE** (wiring) : (a) sourcer `StatAmount×hits` du gameconfig de l'ability soin (par level × mult,
comme le dégât) ; (b) brancher `heal_utility` dans `HealPlaybook`/`engine_decide` à la place du proxy
missing-HP ; (c) **agreement LIVE** sur un scénario healer-vs-alliés-endommagés (la validation est sur
la DÉCISION : le moteur soigne la même cible que le natif).

## 10. État de validation

- **Agreement seed-777 = 11/11** (xmod 1.00 partout), sourcé LIVE (multiplier + PassiveAbilityLevel par
  entité via `combatSnapshot.unitConfig`, plus de dépendance BC-offline). 0 régression.
- u94 RapidAssault +25 % (trait-sourcé, `traitVariables.rapidAssaultExtraDmgPct`) = EXACT.
- Résidus d'arrondi ±1..3 sur branche plancher-perçage = `//100` vs Fix64, PAS une erreur de mécanisme.

### BLOQUÉ / RESTE

- **Prédiction NON-dégât (heal / repair / pose d'effet) offline** : les montants existent en gameconfig
  (`hpToHeal`/`hpToRepair`), mais la **scenario-math heal/repair** n'est pas RE'd → prédiction de soin
  non portée. Débloque les playbooks communs Heal/Repair.
- **`perHitList`** (contenu hitDmg/critChance par coup) : dispatch interface, **service source non
  identifié** ; slots crit 0x10/0x11, `absorbShield`, `FillUpStat.MaxReduceByMinimum` = à calibrer
  vs aiPredict.
- **Chemin code GetStuckIn en PRÉDICTION non localisé** : `AddBonusHitsToCurrentHitGroupBehaviour.Execute`
  @180f93410 fires=0 pendant le decisionView → les +2 coups passent par un chemin prédiction-spécifique
  encore non trouvé (le port reproduit le résultat, pas la voie exacte).
- **Formules de cap par trait** `ApplyResilientTraitDamageLimit` / `ApplyImperviousTraitDamageLimit`
  (scaffold) : à RE.
- **Couche trait-direct du raw prediction** (hit-twice 0x3f5, lasCannon-pierce, triple-hit 0x4b6/var 0x51,
  GroupUnit caps) : cartographiée (§6) mais **non portée** dans `get_attack_prediction`.
- **Arrays statiques** : enum `AbilityVariableType` ABSENT du dump `enums.json` (7 groupes seulement) →
  re-dériver une variable par index positionnel hors gameconfig est impraticable (raison du choix
  Option A : indexer par level depuis gameconfig).
- **`param_5` (obj du slot-9)** : l'`obj` ligne 1239 est droppé par le décompilateur (registre r8 non
  tracké) → entité-attaquant vs service `state.+0x48` non tranché statiquement (sans impact port).
- **Robustesse capture** : duplicates même VisualId mais Id unique en bataille non-miroir → clé Id
  requise (non bloquant en arène-miroir). Câblage live `combatSnapshot.effects` one-shot = TODO
  (seed depuis `decisionView` en attendant).
