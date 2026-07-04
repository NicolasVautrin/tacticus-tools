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

## 7bis. Prédiction PAR-CIBLE = la sélection de cible (mesuré seed 777, TARGET-MISS)

**Découverte** : les mismatches de *sélection de cible* (même ability, mauvaise cible ; 6/20 sur seed
777) ne viennent PAS d'une feuille d'utilité manquante — c'est la **fidélité de prédiction dégât
par-cible**. `DamageDealt` pondère le dégât ; si l'offline sort un dégât PLAT par-cible, le classement
de cible est faux. Le natif prédit le dégât par-cible correctement et frappe la cible qu'il endommage
le plus.

Preuve (step 22, u96 darkaTerminator normal → **82**, TOUTES les cibles attaquées depuis la MÊME tuile
caster (5,4) donc pas un effet de position/no-move ; Defense=100 identique, donc pas la défense) :

| cible | mon offline | aiPredict natif | ratio /baseline | Grand Alliance | effet |
|---|---|---|---|---|---|
| 80 darkstrider | [2121,3183] | (2124,3183) | **×1.00** baseline (= plancher perçage 40 %) | Xenos | — |
| 78 MauganRa | [2121,3183] | (1485,2229) | **×0.70** | Xenos | `Terrifying_ExtraDefense` (réduction défenseur) |
| 82 worldTerminator ←NAT | [2121,3183] | (3183,4776) | **×1.50** | Chaos | `BlessingsOfKhorne` (mais offensif → n'explique PAS) |

- **80** = plancher perçage pur (`bout×40 %`, armure haute) → mon offline matche → **baseline correct**.
- **78** ×0.70 = **modifier défenseur** (Terrifying). C'est le chemin §4 `CalculateDefenderModifiers-
  ForPrediction` → `GetMultiplierFromDamageBonus` (`1 − 30/100`). **NON porté offline** : `predict_normal`
  ne construit QUE les modifiers ATTAQUANT (`build_attacker_modifiers_from_effects`), jamais défenseur.
- **82** ×1.50 = amplification **+50 %**, source **NON identifiée** et à NE PAS deviner :
  - RÉFUTÉ : boss (`BossUnit=None` arène) ; CrushingStrike no-move (§ géométrie : les 3 candidats
    BOUGENT) ; Deathwing (plat +2 au niveau Uncommon, gated-block) ; affinité/Grand-Alliance anti-Chaos
    (§4 : « Pas d'affinité ni de classe dans le dégât de combat ») ; `BlessingsOfKhorne` (offensif +
    réduction *Psychique* seulement) ; `TerminatorArmour` (réduction premier coup, pas amplification).
  - Correspond exactement à l'**angle mort §7** : un modifier qui NE pose PAS d'effet-entité nommé
    (absent de `ActiveEffectIds`) → à capturer via l'**axe stat-modification** (`CalculateModifiersFrom-
    StatModifications` @181004380 = `CurrentValue − BaseValue` d'un stat « damage bonus », défenseur
    négaté). Le nommer exige une **capture du modifier** (probe sur le chemin modifier, pas un fit).

### Primitives RE (généricité) — cf. §4

- `GetMultiplierFromDamageBonus(b)` @181005210 = **`1 + b/100`** (b<1 → réduction, b≥1 → bonus). VALIDÉ
  numériquement : 78 = −30 → ×0.70, 82 = +50 → ×1.50.
- `CalculateDefenderModifiersForPrediction` @181002c30 : Σ sur (a) `CalculateModifiersFromStatModi-
  fications` (stat-mods du défenseur, **négatés**), (b) boucle sur les abilities du défenseur → entrées
  modifier conditionnelles (types 0x19/0x1a/0x1b) évaluées avec contexte → `GetMultiplierFromDamageBonus`
  → `DamageModifiers.Add`. Bonus plats accumulés en `param_1[4]/[5]` (Fix64).
- `CalculateModifiersFromStatModifications` @181004380 : si `StatComponent.CurrentValue != BaseValue`,
  pour chaque `Modifications` → montant `v` ; `isDefender ? −v : +v` → liste de bonus.

### Plan d'implémentation (couche générique, choisi par l'utilisateur)

1. **Axe stat-modification (source de vérité offline)** : capturer par-unité, dans `combatSnapshot`, le
   delta `CurrentValue − BaseValue` du/des stat(s) « damage bonus/reduction » (le stat lu par
   `CalculateModifiersFromStatModifications` — à identifier : slot `DAT_1831fb970`). C'est l'entrée, pas
   la sortie native → conforme doctrine (on recalcule `1 + delta/100`).
2. **`build_defender_modifiers`** (miroir de l'attaquant) : depuis les effets défenseur + le delta stat
   (négaté). Combiner attaquant + défenseur dans `get_attack_prediction(mods=...)`.
3. **Traits conditionnels** (Deathwing anti-Chaos/adjacence, etc.) via la boucle ability + contexte
   (faction cible, moved-this-turn) — après (1)/(2).
4. **Valider** : agreement (78/82 → bon dégât par-cible → steps 11/22/5 remontent) + par-valeur vs
   aiPredict (80 déjà exact ; 78→×0.70 ; 82→×1.50).

### Capture stat-mod axis — RÉSULTAT (2026-07-01)

`combatSnapshot` étendu (`statDelta` = `Current − Initial` par StatType). Probe step 22 (78/80/82) :
**seul `health` a un delta** (= dégât subi). AUCUN delta Attack/Defense/FixedArmor. Donc les modifiers
×0.70/×1.50 **ne sont PAS des stat-modifications** (`CalculateModifiersFromStatModifications` : sa garde
`CurrentValue != BaseValue` ne fire pas) → ils viennent de la **boucle conditionnelle effet/ability** de
`Calculate{Attacker,Defender}ModifiersForPrediction` (EffectBonus.DamageBonus), pas de l'axe stat.
`statDelta` reste capturé (input légitime pour les futurs effets stat-modifiants).

- **78 ×0.70** = `Terrifying_ExtraDefense` (effet défenseur nommé, dans `decisionView.effects`).
- **82 ×1.50** : `darkaTerminator` (u96) porte l'effet ACTIF **`CrushingStrike`** (+50 % mêlée si non-bougé)
  — que `predict_normal` IGNORE. MAIS l'application par-candidat ne se résout PAS simplement : (a) le natif
  BOUGE pour attaquer 82 (`(6,3)->(5,4)` puis attaque) → CrushingStrike « non-bougé » devrait s'éteindre ;
  (b) **78 et 82 sont prédits depuis la MÊME tuile (5,4)** avec des ratios différents (×0.70 vs ×1.50) →
  la différence est **par-cible**, pas par-tuile/move. Incohérent avec une règle CrushingStrike simple.
- **CAVEAT MÉTHODO** : le référentiel par-cible ici = `aiPredict` (= `GetAllPredictions`), qui **N'EST PAS**
  le prédicteur du scorer (`MakeDamagePredictions`, cf. §début) et a des quirks de re-validation
  tuile/portée. Les ratios ×0.70/×1.50 peuvent porter ces quirks. **Avant de porter, capturer le dégât
  par-candidat RÉEL du scorer** (`MakeDamagePredictions` vtable+0x358, ou hook des modifiers
  `Calculate{Attacker,Defender}ModifiersForPrediction` détail@0x38) = la vraie référence.

### Capture SCORER (ProbableDamageEvent.ctor) — RÉSULTAT (2026-07-01) — RÉFÉRENCE FIABLE

Hook `ProbableDamageEvent..ctor @181135500` (`features/scorer-damage-trace.ts`, gated `trace.on`, RPC
`scorerDamageTrace{On,Off,Dump,Clear}`) = point d'étranglement de TOUS les `MakeDamagePredictions`
(vtable+0x358). Struct (dump 12292) : `Target(IEntity)@0x0, DamagePrediction(DamagePredictionResult)@0x8,
Probability@0xC8, Weight@0xD0` ; DamagePredictionResult `AccurateHealthDamage Min@0x60/Max@0x64,
AppliedHits@0xBC` ; IEntity `id@+0x10, type@+0x14`. Capturé pendant `aiStepDryRun` = le dégât par-candidat
RÉEL du scorer (≠ aiPredict). **Step 22 seed 777** (native → 82) :

| cible | events du scorer | lecture |
|---|---|---|
| 78 MauganRa | **2** : (1485,2229) ET (2229,3342) | (1485,2229)=Terrifying ×0.70 ; (2229,3342)=×1.50 de la base réduite (**CrushingStrike**) |
| 80 darkstrider | **1** : (2124,3183) | base seule (ni boost ni réduction) |
| 82 worldTerminator ←NAT | **2** : (2124,3183) ET (3183,4776) | (3183,4776)=(2124,3183)×**1.50** = **CrushingStrike** (+50 % mêlée) |

**Découverte clé** : le scorer évalue chaque cible depuis **PLUSIEURS tuiles candidates** (n=2 events) et le
dégât **VARIE par tuile** ; `CrushingStrike` (+50 % mêlée, attaquant, effet ACTIF sur darkaTerminator) fire
sur les tuiles qualifiantes → le MAX par cible pilote `DamageDealt`. Le max de 82 (×1.5) le rend
top-cible ⇒ pick natif. **Mon offline plat mono-tuile rate CrushingStrike (attaquant, per-tuile) ET la
réduction défenseur (Terrifying).** aiPredict était donc trompeur (il renvoyait ~le max/une tuile, pas la
distribution par-tuile du scorer). `scorer-damage-trace` = la **référence de validation** désormais.

### RÉFUTATION DÉCISIVE — le dégât N'EXPLIQUE PAS le pick 82 (2026-07-01)

Vérifié **avec le code moteur** `damage_composite` sur le dégât RÉEL du scorer (CrushingStrike ×1.5 inclus)
+ maxHP/HP courants observeBattle :

| candidat | DamageDealt |
|---|---|
| **78 MauganRa (CS)** | **43.52** ← MAX |
| 82 worldTerminator (CS) | 41.97 |
| 80 darkstrider | 38.24 |

**`DamageDealt(78) > DamageDealt(82)` MÊME avec CrushingStrike** (82 a un maxHP plus haut → fraction
`dmg/combinedMax` plus basse ; 78 est plus entamé → u_remaining plus haut). Or le natif prend **82**.
⇒ **Le port dégât (a)+(b)+(c) est INSUFFISANT** : le pick 82 n'est PAS piloté par la fidélité de dégât.
Le scorer-trace a évité de porter la mauvaise chose. Discriminateur réel ∈ { **légalité de candidat**
(quelle tuile CS est ATTEIGNABLE — 78-CS peut être un candidat illégal élagué tandis que 82-CS est légal),
**feuille situationnelle** (1 des 10 non-portées du composite Damage(34)), **terme de tuile** Tile(7),
**scoring joint tuile×cible** }. **PAS le dégât.**

**Prochaine capture = l'UTILITÉ par-candidat** (pas le dégât) : `CalculateActionUtility` (gshared) ou au
minimum la tuile caster par-event (bloqué : `MakeDamagePredictions` gshared non-résolu par `findMethod` —
la classe se trouve mais pas le corps gshared ; piste = `GetNormalAttackPrediction` concret, mais retour
sret complique l'ABI). La tuile caster par-candidat trancherait la légalité + la condition CrushingStrike.

### DISCRIMINATEUR TROUVÉ = scoring JOINT (tuile,cible) + feuille Élévation MAL CALIBRÉE (2026-07-01)

Capture de l'**utilité TOTALE par-candidat** via hook RVA sur `CalculateActionUtility` (@181406ee0,
gshared → RVA build-spécifique) dans `features/scorer-damage-trace.ts` (`scorerUtilTraceDump`) + backtrace.
**Chemin RE (stacks)** : `CalculateNextActionForPlayer` → coroutine → `Bucket<UnitAction>.Evaluate(caster,
casterPosition, UtilityDef)` @111df40 → `ComparablePlaybook.EvaluateInternal` @181408980 → `Calculate-
ActionUtility` PAR CANDIDAT (tuile,cible) → bucket → argmax. **C'est un scoring JOINT (tuile,cible)**, et
`CalculateActionUtility` somme **damage-utility + tile-utility** (Tile(7)).

Utilité totale native par-candidat (step 22, `curCaster` propage la tuile aux ProbableDamageEvents) :

| tuile caster | cible | util TOTAL natif | dégât scorer | tile-term natif (=total−dd) |
|---|---|---|---|---|
| **(5,4) elev3** | **82** | **72.98 (MAX)** | (3183,4776) CS | 31.0 |
| (5,3) elev4 | 78 | 69.52 | (2229,3342) CS | 26.0 |
| (5,3) elev4 | 80 | 64.24 | (2124,3183) | 26.0 |
| (5,4) elev3 | 78 | 61.31 | (1485,2229) Terrif | 31.0 |
| (5,5) elev2 | 82 | 49.07 | (2124,3183) | 21.0 |

**Validation offline `damage_composite(dégât scorer) + tile_term(tuile)` vs natif** : match à **~1 pt** sur
(5,4)/(5,5) MAIS **+24 d'excès sur (5,3) elev4** → **ma feuille Élévation rend 50 pour elev4, le natif 26**.
Cette sur-valorisation de la tuile haute de 78 fait basculer mon pick vers 78. **Avec le bon tile-term,
82@(5,4)=71.97 > 78@(5,3)=69.52 → 82 gagne = natif.**

**⇒ Le dégât N'ÉTAIT PAS écarté** : c'est le scoring **JOINT (tuile,cible)** ; mon erreur d'analyse était
de comparer le meilleur-dégât PAR CIBLE sans le tile-term. La structure `dd + tile_term` de mon moteur est
BONNE (match ~1pt sur 3/5), le bug = **la feuille Élévation** (tile.py, elev4→50 vs 26) + un **~+1 constant**
manquant. Tile-term natif non-monotone en élévation (elev2→21, elev3→31, elev4→26) → **RE
`CalculateUtilityFromTilePrediction` + la feuille Elevation** pour recalibrer.

**FIX À FAIRE** : (1) RE + recaler la feuille **Elevation** (`engine/utilities/tile.py`) sur le natif ;
(2) CS per-tuile dans `predict_normal` (le dégât scorer VARIE par tuile via CrushingStrike) ; (3) balayage
JOINT (tuile,cible) dans `engine_decide` (déjà partiel) prenant l'argmax de `dd+tile`. Validation
event-par-event via `scorerUtilTraceDump` (util totale) + `scorerDamageTraceDump` (dégât).

**Statut** : discriminateur TROUVÉ (scoring joint + feuille Élévation mal calibrée). Outils bâtis :
`scorer-damage-trace` (dégât + util totale + tuile + backtrace, RVA-based diagnostic). Reste = les 3 fix
ci-dessus, validés contre les traces.

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

## 8bis. Cas d'étude u92 (bloodDeathCompany, « Lucien ») — OUVERT (#49)

> **Écrit pour ne JAMAIS re-dériver.** Le gap est réduit à UN seul nombre (base 4309 vs 3011).

**Repro (durable)** : `predict_samples.build_samples(seed=31337)` puis filtrer `att == 92`. u92 est mon
carry (team 1) → il apparaît dans mes `attackPlans`. Dump prêt : `scratchpad/dbg49_dump.py` (rows
port-vs-oracle + visualId attaquant + ratio ; recette = build seed → `decisionView` pour le map
id→visualId → `build_samples`). ⚠ `test_predict_live` **PASSE malgré #49** : les rows u92 sur cibles
armure-lourdes sont taguées `predOptimistic` (exclues du critère exact) OU leur max est capé à hp → le gap
MIN est masqué. Ne jamais conclure « #49 fermé » depuis un test vert.

**Ground truth (seed 31337 ; Blast pierce 15, hits 3, ×1.25 RapidAssault) :**

| cible | armor | oracle (min,max) | offline PORT (min,max) | per-coup oracle | per-coup PORT |
|---|---|---|---|---|---|
| u82 bloodMephiston | 2008 | (1503, 6018) | (5397, 9537*) | (501, 2006) | (1799, 3954) |
| u84 eldarAutarch | 1707 | (2634, 7149) | (6525, 8034*) | (878, 2383) | (2175, 4330) |
| u86 astraPrimarisPsy | 2008 | (2256, 5522) | (5397, 5522*) | (752, ~1841) | (1799, 3954) |

`*` = max capé à hp cible. Ratio min port/oracle ≈ 3.6× (u82).

**LOCALISATION (reverse-eng de l'oracle, pas de fitting)** : per-coup oracle u82 = `reduce(spread(B),15,
2008)×1.25` avec **B natif = 3011** (spread {2409,3613}) ; idem u84 (B=3011, indépendant de l'armure). Le
PORT prend **base = 4309 = le stat Attack BRUT** (`combatSnapshot.stats.attack=4309`, level 50,
abilityVariablesMultiplier=180). **Seul écart = la base : port 4309 vs natif 3011** (×0.699, ou −1298 flat) ;
pierce/armure/hits/×1.25 identiques. Les autres attaquants matchent (u88 base 2811 ✓, u96 base 3011 ✓ = leur
stat Attack) → **seul u92 diverge, uniquement par la base.**

**3-WAY DÉCISIF (aiPredict pos-courante / attackPlan meilleure-tuile / port) — REFRAME = c'est POSITIONNEL :**

| cible | attackPlan | aiPredict (pos 5,5) | port | lecture |
|---|---|---|---|---|
| u80 | (858,2109) | (858,2109) | (3885,9537) | natifs AGREENT → **port faux** |
| u82 | (1503,6018) | (1503,6018) | (5397,9537) | natifs AGREENT → **port faux** |
| u86 | (2256,5522) | **(5397,5522)** | (5397,5522) | natifs DIFFÈRENT ; **port = aiPredict** |

Sur u86 : `aiPredict` (pos courante (5,5), PAS de move, cible à portée 2) = **5397 = exactement le port** (base
4309) ; `attackPlan` (meilleure tuile) = 2256 (base 3011). Sur u82 : les DEUX oracles = 1503 (base 3011),
port faux. ⇒ **le port calcule la base juste POUR LA POSITION COURANTE (4309 = aiPredict) mais rate un
modificateur de base DÉPENDANT DE LA TUILE** à la meilleure tuile d'attaque (base 3011). Effet de POSITION
(probablement moved-ranged / pénalité de tuile, lié à #60 has_moved) : le port thread `_hm` dans les mods MAIS
u92 n'a aucun effet gated has_moved → aucune réduction ; la pénalité native est un modifier de BASE, pas un
effet. `predict_samples` ancre `attack_pos = ranked[0].tile` → il DEVRAIT voir la pénalité, mais ne l'applique pas.

**MOVE CONFIRMÉ (dbg49_pos.py — tuiles + élévations) :** non-moved (pos courante (5,5), u86 à portée 2) base
**4309** ; TOUTES les meilleures tuiles (MOVED : u86=(6,4), u82=(4,6), u84=(2,7)) base **3011**. Ratio
4309/3011 = 1.431 (+43%). L'ÉLÉVATION est un axe SÉPARÉ correctement identifié : u86 moved (6,4 elev3 → u86
elev2, attaquant +haut) per-coup **752 = 501 × 1.5** (le +50% élévation) vs u82 moved (elev égal) 501 — donc le
« 2ᵉ axe » u82-vs-u86 = **ÉLÉVATION, pas un modifier défenseur** (corrige la note #50 ci-dessus pour ce cas).

**Source du modificateur MOVE — PAS ENCORE trouvée (RE post-compact) :** ce N'EST PAS RapidAssault (réfuté,
calc-time +25% constant) ni HeavyWeapon/RangedSpecialist (u92 ne les a PAS ; kit = Hero/RapidAssault/Resilient/
Unstoppable). Le port GATE correctement no-move pour les effets qu'il PORTE (`HeavyWeaponExtraDmgEffect` :
`if has_moved: return None`, loki.py) mais u92 n'a aucun effet no-move → base 4309 partout. Le modificateur
natif est donc bâti HORS-EFFET (pattern PowerTrip @CalculateAttackerModifiersForPrediction). MAIS
`CalculateAttackerModifiersForPrediction @181000590` (57K, noms génériques) = grep NÉGATIF sur
Moved/HasFlag/Movement/ForPercent → pas confirmé là. **NEXT** : (1) capter la liste de modifiers NATIVE de
l'attaque MOVED de u92 (trace ground-truth, PAS grind du 57K) ; OU (2) xref du getter du flag `HasMoved` pour
trouver qui applique le −43%. Ratio 1.431 = pas un % propre connu → possiblement config-based.

**Confirmé / écarté :**
- PAS un double-buff RapidAssault : 4309 ≠ 3011×1.25 (=3764). Le natif applique bien ×1.25 SUR base 3011.
- Le stat brut EST 4309 (combatSnapshot). Donc c'est le NATIF qui part d'une base < stat Attack pour ce Blast.
- Chaîne natif : `ALoki_NormalAttackAbility.PredictAttack @1811afa50` → `GetAttackHitPrediction @1811af4e0`
  (délègue au prédicteur générique via slot 0x26 — pas de base spéciale visible là) →
  `GetAdditionalHitsFromEffectsForPrediction` + `AddAdditionalHitsToPrediction`.
- Le « 1799 » des vieux résumés = per-coup PORT (armor 2008), PAS VisionsOfHeresy. VisionsOfHeresy (follow-up
  Bolter 1819-2619) est un event SÉPARÉ, non modélisé côté port — hors sujet pour ce gap.

**OUVERT — d'où vient 3011 (≈ Attack×0.7) ?**
- ~~(c) RapidAssault double-compté (stat 4309 bufflé + `mods`)~~ **RÉFUTÉ (RE 2026-07-04)** :
  `RapidAssault_ExtraDamageEffect.CreateEffectDamageBonusForAttack @180f67940` = `EffectBonus.ForPercent-
  Increase(OwnerIsCaster, ConfigConst(0xf), …)` = modifier de dégât PERCENT **CALC-TIME**, PAS un stat-mod
  sur Attack. Donc `combatSnapshot.attack=4309` = stat BRUT (non bufflé), RapidAssault appliqué 1× via `mods
  =[1.25]`. **Pas de double-compte.** (`RapidAssault_RemoveExtraDamageEffectAbility` @181224a50 = le retire
  après l'attaque ; c'est bien un effet, pas un stat permanent.)
- (a) le normal-attack Loki lit une base de CONFIG d'ability au lieu du stat Attack (à vérifier) ;
- (b) un modifier ranged/Blast (BC Damage, cf. `RangedInMelee=-50` / #61) non appliqué par le port.

**Trancher = capter la base per-coup NATIVE** via le hook `allmods` (`CalculateBaseDamageWithAllModifiers.
input`) de `scorer_trace_capture` sur l'attaque de u92 (vérité terrain : input min ≈ 2409 si base 3011 vs
3447 si base 4309), OU RE du prédicteur générique (slot 0x26 depuis `GetAttackHitPrediction`) pour ce Blast.
NE PAS deviner. Note : le ×0.699 n'est pas un ratio propre (pas ×0.5/×0.7/×0.75) → probablement une base de
config, pas un simple scalaire.

**MAJ 2026-07-04 (session 2, post-compact) — RangedInMelee ÉCARTÉ (géométrie), re-localisation `has_moved` :**

1. **RangedInMelee/Trench WIRÉS** (prediction.py `_add_positional_and_defender_mods`) : feuilles positionnelles
   de `CalculateAttackerModifiersForPrediction @181000590` (callgraph `called` = StatModifications +
   GetMultiplierFromDamageBonus + ShouldApplyRangedInMelee + Trench ; PAS d'élévation ici). Config native
   `RangedInMeleeReductionPercentage=-50` → magnitude 50 passée à `calculate_ranged_in_melee_reduction` →
   `EffectBonus PercentDecrease` → **×0.5** (`GetMultiplierFromDamageBonus @181005210` décompilé confirme :
   `value<1 → 1−|value|/100`). Staging POST-armure (`GetBaseDamageWithFixedPiercedArmor @181030d10` n'applique
   QUE perçage+armure ; les %-modifiers sont les `op 0x10/0x11` APRÈS, dans `CalculateBaseDamageWithAllModifiers`).
2. **MESURE RÉSIDU (dbg49_wired.py, seed 31337) : RangedInMelee ne FIRE PAS** → port inchangé (base 4309,
   mods=[1.25], sur-préd identique). Géométrie (dbg49_pos.py) : **`minEnemyDist(atk) ≥ 2` à TOUTES les tuiles
   d'attaque** (u80/u82 atk (4,6) dist2 ; u84 atk (2,7) dist3 ; u86 atk (6,4) dist3) → AUCUN ennemi adjacent →
   ShouldApplyRangedInMelee=False, correct. **RangedInMelee n'est PAS la cause de #49** (le wiring reste juste,
   ferme #61, zéro faux positif ici).
3. **RE-LOCALISATION = `has_moved` (#60), PAS défenseur ni élévation.** Le SEUL cas NON réduit = **u86 attaqué
   depuis la tuile COURANTE (5,5) = NON déplacé → base 4309** (port == oracle `aiPredict` = 5397). TOUTE attaque
   depuis une tuile MOVED → base 3011, **y compris à élévation ÉGALE** (u82 atk (4,6) elev1 = u82 elev1 ;
   u84 atk (2,7) elev1 = u84 elev1). Donc l'élévation N'EST PAS le discriminant (u82 égal-elev réduit, u86 égal-
   elev non réduit) → **le discriminant est déplacé-vs-pas** (u86-depuis-(5,5) = seul non-déplacé, tous les
   autres déplacés). `TilesMovedThisTurn` ÉCARTÉ : xrefs = `MastersOfManoeuvre`/`SmashaEad` uniquement (PAS le
   kit u92).
4. **SCÉNARIO CRAFTÉ → (A) CONFIRMÉ (2026-07-04) : réduction position-gated RÉELLE, PAS artefact display.**
   Preuve 1 (`dbg49_craft.py`, `decisionView.attackPlan` = chemin SCORING) : la MÊME attaque u92→u86 (toutes
   tuiles hexToTgt=2 = ranged Blast) donne **base 4309** aux tuiles {(5,5),(4,5)} et **base 3011** aux tuiles
   {(6,4),(4,6)}. Preuve 2 (`dbg49_trace.py/2`, hook `allmods` = `CalculateBaseDamageWithAllModifiers.input`
   pendant l'`aiStepDryRun` réel) : **les DEUX bases coexistent** — spread de 3011 (2409/3613) ET spread de 4309
   (3447/5170) présents. Donc le vrai scoring calcule bien 4309 à certaines tuiles et 3011 à d'autres. NON-`has_moved`
   binaire : (4,5) est DÉPLACÉE et garde 4309.
5. **DISCRIMINANT tile = NON géométrique (tout écarté offline) + base décidée EN AMONT du spread.** Écartés :
   move-cost (pathfinder : (4,5) et (6,4) tous deux move-level 1, base différente), élévation absolue ((4,5)e1→4309
   vs (4,6)e1→3011), élévation relative, RangedInMelee (minEnemyDist≥2), défenseur (base 3011 identique pour u82
   ET u86 depuis (4,6) = propriété de la TUILE d'attaque, pas de la cible). Le hook `allmods` montre l'`input`
   **déjà spreadé** (2409=3011×0.8) → la base 3011-vs-4309 est décidée **avant le spread**, dans le calcul de base
   de l'ability (`scenario.damage`), **PAS** dans la couche modifier post-base. **NEXT** : RE du chemin de base de
   l'ability `ALoki_NormalAttackAbility.PredictAttack @1811afa50` → `GetAttackHitPrediction @1811af4e0` (slot 0x26)
   pour trouver ce qui rend `scenario.damage` **tile-dépendant** (4309 vs 3011) — feuille positionnelle inconnue,
   probablement un état/flag de tuile non capturé (LOS/cover/tile-flag ? à identifier au décompilé, PAS deviner).
   Le hook `scorerBonusTraceDump` n'a pas aidé (casterTile=(-1,-1), stack non symbolisée).
7. **VERDICT AGENT re-expert (2026-07-04, `PredictAttackRaw @181032fb0` LU intégralement) — réduction PRÉ-SPREAD
   dans `local_9a8`, PAS un scaling inline.** Base pré-spread = `local_9a8` (lignes ~1483-1512) =
   `GetValueOrDefault(context[+0x58])` (Nullable) avec **override optionnel** `profileMethod_0xd`
   (`local_9a8 = op_Explicit(profileMethod_0xd.Value)`). `GetBaseDamageFix64 @181030ba0` = pur spread ±20%
   (`CalculateMinDamage @181004300 = base − CalculateDamageSpread`), **ZÉRO terme positionnel** (extraMax =
   `GetStat(att,0x19)` sur le MAX seulement) → `{2409,3613}=3011×{.8,1.2}`, `{3447,5170}=4309×{.8,1.2}` = deux
   bases pré-spread. Aucun `op_Multiply`/`op_Subtraction` positionnel entre lecture-base et spread (vérifié ligne
   à ligne). Élévation `@181003ea0` = additif, seulement si attaquant plus haut = axe séparé. Seul modificateur
   positionnel-tuile candidat = `CalculateTrenchReduction @181004830` (via `CalculateAttackerModifiersForPrediction
   @181000590`, interface dispatch invisible au callgraph statique ; gate `IsTrench(attackTile)` +
   `!IsNeighbour(attackTile,targetTile)`). **MAGNITUDE ≈ −30%** : `3011/4309 = 0.6988 ≈ 0.70` → **modificateur −30%** (l'écart 3011-vs-3016 ≈ 5
   = bruit d'arrondi Fix64/ordre d'ops, PAS bloquant). C'est un **modificateur %-entier −30% positionnel**. `Trench=-50`
   (×0.5→2154) NE colle PAS → trench écarté par magnitude (comme RangedInMelee) ; il reste un modificateur −30%
   (source exacte à confirmer : override `profileMethod_0xd` base-recomputée OU un modifier attaquant −30% via
   `CalculateAttackerModifiersForPrediction`). **CHECKS DÉCISIFS
   (agent)** : (1) hook `GetBaseDamageFix64 @181030ba0` lire `param_3`(rdx=base Fix64) sur les 4 tuiles + tuile
   → 3011 vs 4309 confirme base-level ; (2) lire `IsTrench` des 4 tuiles d'attaque (board live) → si {(6,4),(4,6)}
   trench et {(5,5),(4,5)} non → trench ; sinon écarter → **RE du setup `context[+0x58]`** (base par-tuile posée
   en AMONT, dans `MakeDamagePredictions @181372730` / scenario setup) ; (3) impl. concrète interface `DAT_183287db8`
   slot 0xd (gshared, non décompilée) = maillon qui dirait si la base est recalculée positionnellement.
6. **RE du chemin de base de l'ability (2026-07-04, décompilé)** : `ALoki_NormalAttackAbility.GetAttackHitPrediction
   @1811af4e0` fixe la base = **`GetStat(attacker, 5)`** (stat 5 = Attack = 4309, **TILE-INDÉPENDANT**), wrappée
   Nullable et passée au **prédicteur générique via slot 0x26** avec la position caster (`local_2c8` ← param_7).
   Donc la base ENTRANTE est uniforme 4309 → **la réduction à 3011 est appliquée DANS le prédicteur générique
   (`PredictAttackRaw @181032fb0`)**, pré-spread. Callgraph `called` de PredictAttackRaw : lit la position
   (`GetUnitPosition`@7, `UnitPosition.get_MainTile`@12), élévation INLINE (pas d'appel `CalculateElevationBonus`),
   `GetBaseDamageFix64`, `IsAttackMaxOutDamage`, `CalculateBaseDamageWithAllModifiers`, `ApplyTraitDamageLimits`.
   **AUCUNE feuille nommée cover/LOS/position→base.** `IsAttackMaxOutDamage @180ed7a50` ÉCARTÉ (dépend de l'effet
   `0x4a1` owner/target OU triggered-ability `0x5d6` ; u92 n'a NI l'un NI l'autre → false uniforme). ⇒ la
   réduction tile-dépendante 4309→3011 est dans la **logique position/élévation INLINE de `PredictAttackRaw`**
   (corps 3037 lignes), PAS une fonction nommée. **NEXT** : deep-read de la section position/base de
   `PredictAttackRaw` (grind lourd — candidat agent re-expert worktree) OU capter la base per-tuile via un hook
   `CalculateDamagePredictionScenario` (rawMin/rawMax + targetId) corrélé à la tuile caster.

**2ᵉ axe (séparé = #50)** : à armure égale (u82/u86 = 2008), per-coup oracle diffère (501 vs 752) → modifier
DÉFENSEUR par-cible. **MAJ** : pour u86, le 752 = 501×1.5 (ÉLÉVATION depuis (6,4) elev3), pas un modif défenseur
→ ce cas u82/u86 est ÉLÉVATION, pas #50 (cf. bloc MOVE CONFIRMÉ).

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

## 9bis. Prédiction de RÉPARATION (repair) — RE complet + port offline

Répare les **machines** (Adeptus Mechanicus / Necron). Chaîne **entièrement RE'd et offline-calculable**,
portée 1:1 dans `engine/predict.py` (PARTIE 4). Quasi identique au soin, mais sur **DEUX** stats
fill-up — `Health` (id 5) **et** `Armor` (id 4) — d'où une **utilité à deux termes**.

| Étape native | VA | Formule |
|---|---|---|
| `DamagePrediction.PredictRepair` | `@181038280` | `repairAmount = floor((floor(modAdd) + base) × modMul)` [RepairModifier caster] → caps group/boss → `MaxFillUp` ×2 |
| `FillUpStatComponent.MaxFillUp` | `@180f9b790` | `fill_i = min(repairAmount, GetStat(i,Maximum) − GetStat(i,Current))` sur Health **et** Armor |
| `RepairedAmountUtility.EvaluateRepairInSteps` | méthode `@1810e06f0`, iter `@1810e45b0` | `U = (fill_hp/(maxHP+1) × 100 + fill_armor/(maxArmor+1) × 50) × bossMod` |
| `RepairedAmountUtility.cctor` (poids) | `@1810e08b0` | `W[0]=Fix64.FromInt(100)` (HP), `W[1]=Fix64.FromInt(0x32=50)` (Armor) |
| `GetMaxHealth` (denom PV) | `@1810e0760` | `GetStat(Health,Maximum)+1` (boss → const config `0xa9`) |
| `GetUnitUtilityModifier` | `@1810e0820` | `bossMod = 2` si cible boss, sinon `1` |

- **PAS de friendSign** (≠ soin) : on ne répare que ses **propres** machines → jamais d'utilité négative.
- `base` = magnitude brute de l'ability de réparation (`StatAmount × max(hits,1)`, source gameconfig
  `hpToRepair` par level × mult), transformée par le RepairModifier `(add, mul)` côté caster (no-op par
  défaut : `add=0, mul=1.0`).
- `StatType` (dump.cs @863349) : `Armor=4`, `Health=5`. `StatPart` : `Current=0`, `Maximum=2`, `Initial=3`.

**Porté + sanity-check** : `repair_amount`/`predict_repair_effective`/`RepairPrediction`/`repair_utility`
(cohérence math vs RE OK : modifier `(50+800)×1.25=1062`, `fill_hp=min(800,2000)=800`,
`fill_armor=min(800,400)=400`, `U=59.94`, boss×2=119.87). **RESTE** (wiring, idem heal) : brancher
`repair_utility` dans `RepairPlaybook`/`engine_decide` + **agreement LIVE** (caster Loki + machine alliée
endommagée). Boss : dénominateur PV via const config `0xa9` non lue (cas-bord, hors port).

## 9ter. Pose d'EFFET (added effect) — RE complet + port offline

Dernière brique non-dégât (`engine/predict.py` PARTIE 5). Contrairement au soin/repair, **pas de
« magnitude » d'effet** : l'utilité est un **poids PLAT par TYPE d'effet, 100 % piloté par le BC** —
la magnitude d'un DoT/réduction passe, elle, par le chemin **dégât** (`ProbableDamageEvent`).

| Étape native | VA | Formule |
|---|---|---|
| `AddedEffectUtility.EvaluateAttackInSteps` | iter `@1810f6e70` | `0` si cible a déjà l'effet ; sinon `Weight[name] + signe × Weight["Unit_on_"+name]` |
| `BaseUtility.HasUtilityValue` | `@1810cd700` | `name in weights` (`Dict<string,int>` @this+0x58) |
| `BaseUtility.GetUtilityValue` | `@1810cd3c0` | `Fix64.FromInt(weights.get(name, 0))` (clé absente → 0) |

- `name = Enum.ToString(EffectType)` (ex. `"Fire"`, `"SpiderWeb"`, `"Ice"`).
- `signe = −1` si la cible est un **ALLIÉ** du caster (`UnitExtensions.IsFriend`), `+1` sinon → poser un
  effet hostile sur son propre camp = utilité négative.
- `weights` = un dict de catégorie du BC `Utilities.Default` (déjà capturé), p.ex. `AddedTileEffects` :
  `Fire=10, Unit_on_Fire=15, Ice=5, Unit_on_Ice=0`. **Fire sous un ennemi = 10+15 = 25 ; sous un
  allié = 10−15 = −5.** Préfixe `"Unit_on_"` **confirmé empiriquement** par les clés BC.

> Ce lookup `BaseUtility.GetUtilityValue(name)` est le **même moteur de poids data-driven** que tout
> le scorer natif (catégories `KillUnit` 50/100, `TileEffects`, `TriggeredAbilities`, `ActiveAbilities`,
> … ~50 catégories dans `Default`). La pose d'effet n'en est qu'**une feuille** ; l'assemblage
> inter-catégorie = [`status.md`](status.md) §3.2 / #38.

**Porté + sanity-check** (vs vrais poids BC) : `utility_value`/`added_effect_utility` — `Fire(ennemi)=25`,
`Fire(allié)=−5`, `Ice=5`, déjà-présent→0, clé inconnue→0. **RESTE** : wiring dans le scorer d'attaque +
mapper l'`EffectType` enum → nom de clé BC (déjà aligné : `Enum.ToString`).

## 10. État de validation

- **Agreement seed-777 = 11/11** (xmod 1.00 partout), sourcé LIVE (multiplier + PassiveAbilityLevel par
  entité via `combatSnapshot.unitConfig`, plus de dépendance BC-offline). 0 régression.
- u94 RapidAssault +25 % (trait-sourcé, `traitVariables.rapidAssaultExtraDmgPct`) = EXACT.
- Résidus d'arrondi ±1..3 sur branche plancher-perçage = `//100` vs Fix64, PAS une erreur de mécanisme.

### BLOQUÉ / RESTE

- **Prédiction NON-dégât offline** : heal (§9) **et** repair (§9bis) sont désormais **RE'd + portés**
  (`PredictHeal`/`PredictRepair` + utilités). RESTE : (a) pose d'**EFFET** (magnitude/utilité d'un effet
  appliqué) non RE'd ; (b) **wiring** des utilités heal/repair dans les playbooks + agreement LIVE.
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
