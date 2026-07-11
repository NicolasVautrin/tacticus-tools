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
- **LOCUS de l'additif = PER-COUP (verdict #70, RE 2026-07-09).** L'additif plat (`Add`@+0x10) est
  appliqué DANS `CalculateBaseDamageWithAllModifiers @18102d3f0` (slot 0x10 `ApplyAdditive`, APRÈS le
  `%-list`) sur la BASE D'UN COUP. Or `BattleQuery.GetMultiHitAttackPrediction @181066080` = la boucle
  multi-coups appelle `GetAttackPrediction`→`PredictAttackRaw` **par coup** puis `DamagePredictionResult.Add`,
  et **N'A AUCUNE application d'additif post-boucle** (lu intégralement : `return param_1` direct après la
  boucle). ⇒ **le natif applique l'additif ×hits (une fois par coup), PAS une fois sur l'agrégat.** Le port
  (`damage_prediction.py`) fait l'INVERSE : strip additif du chemin per-coup (`predict_attack_raw` l.248
  `replace(mods, additive=0.0)`) + application UNE FOIS sur l'agrégat (l.332-337) — étape SANS contrepartie
  native (artefact probable d'avant le refactor #51 qui a déplacé la boucle multi-coups hors de PredictAttackRaw).
  **Divergence LATENTE côté attaquant** (`CalculateAttackerModifiersForPrediction` renvoie additive=0.0 sur
  les cas mesurés, cf. §7bis) ; **ACTIVE côté défenseur** (une réduction plate `DamageReduction` = additif
  négatif, ex. −582, serait soustraite ×hits par le natif, une seule fois par le port ⇒ port SUR-prédit le
  dégât sur cible à réduction-plate multi-coups). FIX (à valider live AVANT commit — carrier = défenseur à
  réduction plate + attaquant multi-coups, `aiPredict` discrimine ×hits vs ×1) : ne PAS strip l'additif dans
  `predict_attack_raw` (le passer à `apply_pierce_and_modifiers` par coup, ordre %-list→additif déjà fidèle)
  + RETIRER le bloc agrégat l.332-337. ⚠ per-coup ≠ trivialement `×hits` : l'additif per-coup interagit avec
  le plancher `max(0,…)`, le split bouclier et le cap overkill PAR COUP (peut différer de l'agrégat quand un
  cap mord).
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
   `CalculateAttackerModifiersForPrediction`). **TILE-EFFECTS ÉCARTÉS (dbg49_tilemeta.py)** : (6,4) réduite SANS effet ; (4,6) réduite AVEC
   `BlockEnteringUnits`+`Thorns_DefenseReduction` ; (5,5)/(4,5) pleines sans rien → 2 tuiles réduites, une avec
   effet une sans → l'effet de hex n'est PAS le discriminant (ni isWall/isTemporary/isTerritory, tous False). Le
   discriminant géométrique reste introuvable (élévation/move-cost/adjacence/tile-effects tous réfutés) → la
   source est en AMONT (setter de `context[+0x58]`). **CHECKS DÉCISIFS
   (agent)** : (1) hook `GetBaseDamageFix64 @181030ba0` lire `param_3`(rdx=base Fix64) sur les 4 tuiles + tuile
   → 3011 vs 4309 confirme base-level ; (2) lire `IsTrench` des 4 tuiles d'attaque (board live) → si {(6,4),(4,6)}
   trench et {(5,5),(4,5)} non → trench ; sinon écarter → **RE du setup `context[+0x58]`** (base par-tuile posée
   en AMONT, dans `MakeDamagePredictions @181372730` / scenario setup) ; (3) impl. concrète interface `DAT_183287db8`
   slot 0xd (gshared, non décompilée) = maillon qui dirait si la base est recalculée positionnellement.
8. **CLÔTURE (2026-07-04, agent-suite + vérif magnitude) — modificateur = VALEUR 30 (−30%), trench RÉFUTÉ.**
   Mécanisme PROUVÉ (décompilé) : base réduite = `Round(base × mult)` PRÉ-spread (`CalculateBaseDamageWithModifiers
   @1810021c0`), `mult` produit par `GetMultiplierFromDamageBonus @181005210` depuis une **valeur ENTIÈRE**. Vérif
   chiffrée : `mult=×0.70` (val **30**) → base 3016 → dmgMin ~1518 ≈ 1503 observé ✓ ; `×0.50` (trench `-50`) → base
   2155 → dmgMin ~972 ✗. Donc **trench `TrenchReductionPercentage=-50` (×0.5) RÉFUTÉ par magnitude** (comme
   RangedInMelee −50), MÊME si les tuiles sont des tranchées (`IsTrench` = type de tuile, non lu live mais
   non-décisif car ×0.5 exclu). L'agent avait raison que je n'ai pas lu `IsTrench` (le check tile-effects ne le
   couvre pas), mais la magnitude ferme : la valeur cherchée = **30**, pas 50. **Aucun champ BC.Damage = 30**
   (ElevationBonus 50, ClassBonus 25, AffinityBonus 50, Knockback 20…). Tous les leaves NOMMÉS de
   `CalculateAttackerModifiersForPrediction @181000590` (StatModifications non-positionnel, RangedInMelee −50, Trench
   −50) écartés → la **valeur 30 tile-dépendante vient du chemin gshared/vtable** (override `profileMethod_0xd` OU
   `context[+0x58]` posé par le playbook concret). **OUTIL DÉCISIF RESTANT** : fixer le hook `scorerBonusTraceDump`
   (`GetMultiplierFromDamageBonus`) — bugs actuels casterTile=(-1,-1) (poser via `curCaster` du onEnter
   `MakeDamagePredictions`) + `bonus=1` (mauvais offset ; attendu 30 sur tuiles réduites) + stack att/déf — puis
   re-run : capte le −30 + sa source par tuile. État : mécanisme (`Round(base×0.70)`) + magnitude (val 30) PROUVÉS ;
   SOURCE du 30 = gshared, non tranchée.
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

9. **CORRECTION MAJEURE (2026-07-04, hook `GetMultiplierFromDamageBonus` CORRIGÉ + re-run all-fresh) — les points
   7/8 sont RÉFUTÉS : la réduction N'EST PAS un modificateur −30% via `GetMultiplierFromDamageBonus`.** Le hook a été
   corrigé (single overload @181005210 uniquement — la variante LIST @1810053e0 à 2 args lisait `args[2]` parasite
   = `bonus=1` ; gate sur le **multiplicateur de SORTIE** `retval`=Fix64, le `Nullable<int>` d'entrée est gshared
   non-lisible directement). Re-run seed 31337 `aiDryRunAllUnits` (dbg49_bonus4.py) :
   - **`GetMultiplierFromDamageBonus` ne renvoie QUE du no-value** (344 appels, tous `mult=0`) pendant le scoring —
     AUCUN `mult=0.70`. Il n'applique donc PAS de −30%.
   - **`allmods` (input = base AVANT modifiers) diffère par tuile** : tuiles (5,6)/(6,5) attribuées → `input∈{2409,3613}`
     = **base 3011** ; bucket non-attribué → aussi `{3447,5171}` = **base 4309**. Comme `attMods`/`GetMult` sont
     appliqués APRÈS et que l'`input` d'`allmods` = base PRÉ-modifier, la réduction est **en AMONT de toute la chaîne
     modifier** → structurellement NE PEUT PAS venir de `GetMultiplierFromDamageBonus`. Le fit `×0.70` (3016 vs 3011,
     off de 5) était une COÏNCIDENCE, pas le mécanisme. **`context[+0x58]`/`profileMethod_0xd` (point 6) confirmé.**
   - **Vraie piste = ARME BLAST + base PAR (tuile, cible).** u92 « Lucien » a **2 armes** (gameconfig) : Melee (4 hits,
     pierce 1, Physical, range 0) et **Ranged Blast** (3 hits, pierce 15, `HitsMultipleMembers`, range 2). Corrélation
     DmgEvent par tuile caster → cible u86 (6,6) : hexdist=1 → MELEE 4 hits ; hexdist=2 → RANGED 3 hits.
   - **La base est PAR (tuile caster, cible), pas par tuile** (dbg49_multitarget.py, attackPlan de u92) : dans UN MÊME
     eval touchant 3 cibles, `dmgMin` diffère par cible — ex. `[(2256,5522),(5397,5522),(5397,5522)]` = **2 cibles base
     pleine 4309 (5397) + 1 cible réduite (2256)** ; autre eval `[(1503,6018),(1404,5616),(1404,5616)]` = 3 réduites ;
     eval single-cible = `(5397)` = 4309. Donc ce n'est **NI un −30% générique, NI "nombre de cibles → tout réduit",
     NI un axe positionnel de la tuile** : c'est une **réduction de base PAR CIBLE au sein de l'AoE Blast** (primaire vs
     éclaboussure / distance de splash / membre). `dmgMax` = cap santé de la cible (u86=5522, u82=6018…).
     → **HYPOTHÈSE (à LIRE au décompilé, PAS fitter) : la Blast `MakeDamagePredictions` produit un event PRINCIPAL
     (base pleine) + des events AoE/splash à base RÉDUITE** (falloff par distance-au-centre ou règle multi-membre) ;
     le port `predict_normal` applique la base pleine 4309 à toutes les cibles.
   - **VERDICT re-expert (2026-07-04, worktree) — mécanisme LOCALISÉ PROUVÉ, formule bloquée gshared.** Point EXACT de
     l'override (lu dans `PredictAttackRaw @181032fb0`) : `@181034898 slot0xd = interfaceCall(DAT_183287db8, idx 0xd)`
     → `local_838` (Nullable<Fix64>) ; `@1810348dd local_9a8 = GetValueOrDefault(context[+0x58])` = 4309 ; `@181034957
     if local_838.HasValue: @181034976 local_9a8 = op_Explicit(local_838.Value)` = **OVERRIDE base**. En AMONT de
     `GetBaseDamageFix64` (spread), de `CalculateBaseDamageWithAllModifiers` et des trait-limits → cohérent avec
     « allmods input déjà 3011 ». Analog COMBAT : `CalculateAbilityDamage @18102cb50` utilise **slot 0xf** de la même
     interface `DAT_183287db8`. RÉFUTÉ additionnel : member-cap (`ApplyGroupUnitDamageLimit @18102bfe0` `return` si
     `HasTrait(2=HitsMultipleMembers)` → SKIPPÉ pour Blast) ; aucune clé Blast/splash dans BC.Damage.
   - **GAP PORT confirmé (point unique)** : `damage_prediction.py::predict_attack_raw` n'a **AUCUN chemin d'override**
     `profileMethod_0xd`/`context[+0x58]` — il prend `initial_damage` (4309) tel quel. `prediction.py::make_normal_attack_predictions`
     (l.143) passe `ctx.attack`=4309 plat. Fix = point PARTAGÉ (service appelé par prédiction ET runner combat
     `runner/damage_model.py`), pas forké.
   - **BLOQUANT = formule numérique gshared.** L'override invoque, dans `GetAttackHitPrediction @1811af4e0`, un des 2
     délégués créés : `<GetAttackHitPrediction>b__0 @1811c9d10` = `ability.vtable+0x4d8` (méthode virtuelle slot 58) ;
     `b__1 @1811c9e50` = interface `DAT_18327ff80` **idx 0xb4** `(target, position, abilityOrEffect)` (signature
     per-(cible,position)). Ces slots vtable/interface sont **résolus au RUNTIME → ghidra ne les mappe pas offline**
     (vérifié : `AttackAmount @1811ae260` = pur `DSLFactory.NormalAttackDamage`=stat 4309, PAS l'override). La formule
     EXACTE reste NON LUE.
   - **RÉSOLUTION LIVE (2026-07-04, résolveur b__0/b__1 dans scorer-damage-trace.ts) — b__0/b__1 = RED HERRINGS.**
     Résolus live : **b__0 (`vtable+0x4d8`) → `AttackAmount @1811ae260`** (base 4309, tile-indep) ; **b__1 (`iface
     DAT_18327ff80 idx 0xb4`) → `BattleQuery.GetAttackHits @18105d8d0`** (compteur de coups). Ni base-override, ni
     tile-dépendant. Le VRAI override = l'appel `local_838 = FUN_180031950(receiver, idx=0xd, DAT_183287db8)`
     @181034898 (lu dans `predictraw.c` l.1473 : `FUN_180031950(out, idx, iface, RECEIVER=param_4=R9, ., args, .)`),
     Nullable gaté `HasValue` → `op_Explicit(Value)` remplace la base. Sibling `idx 0xe` @181796 (extraMax probable).
     Le **receiver est en R9 (perdu par le décompilo)** → non résoluble statiquement (les méthodes NOMMÉES de
     `DamageCalculations` n'ont pas d'override base-par-profil/position évident ; receiver pas forcément
     `DamageCalculations`).
   - **DERNIER HOP RÉSOLU LIVE (2026-07-05, résolveur idx-0xd FUN_180031950 site-filtré @181034898)** :
     `override idx13 recv=DamageCalculations -> il2cpp+0x1000590` = **`CalculateAttackerModifiersForPrediction
     @181000590`** (idx 0xd de l'interface `IDamageCalculations` = `DAT_183287db8`). **Plus aucun hop gshared** : c'est
     une fonction NOMMÉE déjà décompilée (`attmods.c`). Le **base-override = le 1er champ `Nullable<Fix64>` (offset 0)
     du `DamageModifiers` retourné** ; `PredictAttackRaw` le lit `HasValue`→`op_Explicit(Value)` pour REMPLACER la base
     4309 (pré-spread). (Les délégués b__0=`AttackAmount`, b__1=`GetAttackHits` étaient des red herrings ; l'interface
     `DAT_18327ff80` de b__1 ≠ `IDamageCalculations`.)
   - **SOURCE du base-override = la boucle STAT-MODIFICATIONS de `CalculateAttackerModifiersForPrediction`** (attmods.c
     l.660-1040) : construit `AbilityEntities` (l.682) puis, par groupe de `param_5`, évalue **3 formules DSL de
     l'ability via interface idx 0x16 (@799), 0x17 (@934), 0x18 (@1022 via FUN_180024fa0)** → accumule des flats
     (`iVar31`, `iVar30`) + un `Nullable` (`local_618` @880) ; puis les modifiers % (GetMult, l.1073+, prouvés
     no-value). Le override est donc **EFFET/ABILITY-driven** (pas positionnel générique). **Kit u92 « Lucien »
     (gameconfig) = complexe 3-profils** : normal Melee(4h) + Ranged Blast(3h) ; **VisionsOfHeresy** (attaque de suivi
     2×Bolter pierce20, +20% pierce si HP<=50%) ; **BlackRage** (charge mêlée conditionnelle « if not moved -> set 50%
     HP + +728 Damage when charging »). Le 4309-vs-3011 vient très probablement de l'une de ces stat-modifications
     conditionnelles évaluées par la boucle (à confirmer : capturer `CalculateAttackerModifiersForPrediction` return[0]
     par tuile/ability, ou lire l'assemblage DSL idx 0x16/0x17/0x18). ⚠ NE PAS re-fitter `×0.70`/`-1298`.
     **ÉTAT** : chaîne résolue jusqu'à la fonction nommée `CalculateAttackerModifiersForPrediction`.
   - **CAPTURE return[0] (2026-07-05, hook findMethod `CalculateAttackerModifiersForPrediction`) — HYPOTHÈSE
     OVERRIDE RÉFUTÉE/INCONCLUSIVE.** Les 423 events lisent `return[0] = (i0=0,hv4=0,f0=0,hv8=0)` — TOUJOURS vide,
     y compris tuiles (5,6)/(6,5) attribuées — alors que les DmgEvents montrent 3011 (hMin 1503) qui reproduit. Donc
     soit (1) le base-override `return[0]` est génuinement vide → l'override idx-0xd N'EST PAS la source du 3011 ;
     soit (2) `CalculateAttackerModifiersForPrediction` a DEUX out-params (`param_1` zéro-init l.253-260 ET
     `return puVar20`=param_4) → `retval[0]` lit peut-être le mauvais struct (inconclusif). **Dans les deux cas : le
     3011 est le BASE fed to `PredictAttackRaw` via `context[+0x58]` LUI-MÊME (tile-dépendant), PAS l'override.**
   - **MÉCANISMES ÉCARTÉS (cumul)** : GetMultiplierFromDamageBonus (no-value), member-cap (skip Blast), base-override
     idx-0xd (return[0] vide).
   - **CAPTURE `context[+0x58]` (2026-07-05, hook PredictAttackRaw onEnter, Fix64 @ args[2]+0x58) — TRANCHE
     DÉFINITIVEMENT.** `f58` (la base pré-spread fed to PredictAttackRaw) = valeurs PROPRES ; tuiles attribuées
     **(5,6)/(6,5) = 3011** exact (hv60 set). Donc **le 3011 EST la valeur de base à l'ENTRÉE de PredictAttackRaw**
     — PAS un modifier ni un override interne. Distribution multi-unités (698/1003/1408/2107/2507/2811/3011/3915…) =
     bases des 10 unités du dry-run ; u92 attribué = 3011. **La réduction est dans la base elle-même**, posée EN AMONT
     par le setup du scenario / `GetAttackHitPrediction` (base = `GetStat(attacker, 5)`). ⇒ **le 4309-vs-3011 est très
     probablement `GetStat(5)` CONDITIONNEL** (stat de dégât effective incluant un buff move/position-dépendant :
     not-moved/charge → 4309 ; moved → 3011 brut) — cohérent avec `BlackRage` (« if not moved → +Damage when
     charging »). Le PORT prend `combatSnapshot.attack=4309` (valeur bufflée courante) pour TOUTES les tuiles.
   - **RÉSOLUTION FINALE (2026-07-05) — base = `GetStat(5)` recalculée par-position + effet `RapidAssault_ExtraDamage`.**
     Chaîne native tracée intégralement : `GenerateMultiHitAttackPredictions @181409da0` (itère cibles, appelle slot
     0x27 = `PredictAttack` avec la POSITION candidate `local_res18`) → `PredictAttack @1811afa50` → `FindAttackWeapon
     @1811aeb80` (sélection d'arme par position) → `GetAttackHitPrediction @1811af4e0` (base = `GetStat(attacker, 5)`)
     → `PredictAttackRaw` (`context+0x58`). **`GetStat(5)` est recalculée par prédiction avec l'état d'attaque** →
     résout les effets de dégât CONDITIONNELS. `decisionView` : u92 porte `RapidAssault_ExtraDamage` (effectType 1229)
     + `RapidAssault_Movement` (1228) actifs ; gameconfig `RapidAssault = {rapidAssaultExtraDmgPct:25}` (« 1ère attaque
     du combat + suivantes du même tour +25% Damage »). La base statique `combatSnapshot.attack=4309` inclut ce buff ;
     les prédictions moved donnent 3011 (base sans le buff conditionnel). ⚠ 4309/3011=1.431 ≠ 1.25 seul → décomposition
     numérique exacte (raw stat + valeur effet) encore à confirmer (hook `GetStat`/lire le stat-breakdown snapshot).
   - **PATH MATÉRIALISÉ OFFLINE = À MOITIÉ.** `prediction.py::make_normal_attack_predictions` : ✅ weapon-select
     par-position (service partagé #57), ✅ `has_moved` threadé dans `build_attacker_modifiers_from_effects` (l.128-129),
     ❌ **BASE = `ctx.attack` STATIQUE (l.144 `initial_damage=ctx.attack`), PAS recalculée par-position via `GetStat`.**
     Le port gate le buff dans les `mods` mais ne l'ôte PAS de la base `ctx.attack` (4309, buff inclus) → sur-préd aux
     tuiles moved (natif=3011). **FIX** : recalculer la base par-position (résoudre les effets dégât conditionnels type
     RapidAssault selon l'état d'attaque prédit) au lieu du `ctx.attack` figé ; ou ôter le buff conditionnel de la base
     quand `has_moved`/état-consommé. **NEXT concret** : confirmer si `ctx.attack` contient RapidAssault (double-count)
     + la valeur exacte du buff → wirer la base conditionnelle. Lié à #60 (has_moved runner).
   - **★ RÉSOLUTION EXACTE (2026-07-05, capture décomposition aiPredict col/row + combatSnapshot) ★.** Base BRUTE de
     u92 = **3011** = `combatSnapshot.stats.attack (4309) − statDelta.attack (1298)` (EXACT, zéro arrondi). Le **+1298**
     = buff conditionnel actif (`statDelta.attack=1298`, `statDelta.movement=1` = `RapidAssault_Movement`). Confirmé
     LIVE via `aiPredict{col,row}` (position hypothétique, base propre par tuile) : tuiles melee-adjacentes (6,5)/(5,6)
     = **3011 exact** (base brute, buff exclu). Le natif **recalcule `GetStat(5)` par prédiction** → brut 3011 quand le
     buff ne s'applique pas à l'attaque prédite (melee/moved), 4309 (bufflé) sinon. **GAP PORT = `unit_context.py:108`
     `attack=g("attack")` prend `stats.attack`=4309 BUFFLÉ pour TOUTES les tuiles, ignore `statDelta`.** Ratio base
     4309/3011=1.43 → 1.7-2.4× sur PV après armure/perçage = le gap #49. **Boucle la boucle** : ni GetMult, ni
     member-cap, ni override idx-0xd, ni arme (armes partagent Damage=30) — c'est la **stat bufflée figée** vs la stat
     BRUTE + buff conditionnel recalculé par-position (natif `GenerateMultiHitAttackPredictions → PredictAttack(POSITION)
     → FindAttackWeapon → GetAttackHitPrediction → GetStat`). **FIX** : baser la prédiction sur la stat BRUTE
     (`stats.attack − partie conditionnelle de statDelta`) + réappliquer le buff conditionnel via la couche effet/mod
     (le port a déjà `RapidAssaultExtraDamageEffect` + `has_moved` threadé) ; NE PAS partir de `stats.attack` bufflé.
     ⚠ Nuance : `statDelta` peut mêler buffs PERMANENTS (à garder dans la base) et CONDITIONNELS (à exclure/recalculer)
     — identifier la part conditionnelle (RapidAssault_ExtraDamage) et n'exclure QUE celle-là selon l'état d'attaque
     prédit. Reste : la condition exacte d'application du +1298 (RapidAssault dit « toutes attaques du tour » mais moved
     l'exclut → consommation/gate à confirmer) + le mapping effect→statDelta.
   - **#49 (2026-07-05)** après ~9 cycles reinject. **Acquis durable** : diagnostic INVERSÉ (PAS un −30% GetMult) ;
     mécanismes écartés (GetMult, member-cap, override idx-0xd) ; **base = valeur 3011 directe à l'entrée
     PredictAttackRaw (`context[+0x58]`), posée en amont via `GetStat(5)` conditionnel**. **Reste (rouvrable)** :
     identifier le buff conditionnel exact (hook `GetStat`/`GetAttackHitPrediction @1811af4e0` onLeave par tuile, OU
     recon des effets move-conditionnels de u92) → le PORT doit résoudre `GetStat(5)` par-position (ne pas appliquer le
     buff not-moved aux tuiles moved). ⚠ NE PAS re-fitter `×0.70`/`-1298`. Infra hooks (résolveurs + attMod + predBase)
     dans scorer-damage-trace.ts pour rouvrir.
10. **CORRECTION (2026-07-05, décompilé `GetAttackHitPrediction @1811af4e0` LU directement) — la ★ résolution
    « GetStat(5) recalculée par-position » est RÉFUTÉE ; `GetStat` N'EST PAS positionnel.** La ligne de base est
    `uVar16 = UnitExtensions.GetStat(*(context+0x38), 5, 0, 0, 0)` = **`GetStat(attacker, statType=5, part=0=Current)`,
    lecture stat PLATE — AUCUN argument de position**. Chaîne : `PredictAttack @1811afa50` → `FindAttackWeapon`
    (choix d'arme par position) → `GetAttackHitPrediction` lit `GetStat(5)` sur l'entité caster RÉELLE du scénario
    (`context+0x38` = attaquant issu d'`AbilityEntities`, pas un clone par-tuile) → **4309, POSITION-INDÉPENDANT**.
    La position candidate (`param_7`) est threadée SÉPARÉMENT dans le prédicteur générique (slot 0x26 de l'interface
    `DAT_18327ff80`), avec la base Nullable(4309). ⇒ **la base injectée dans le prédicteur = Current(4309) pour TOUTES
    les positions** ; le **3011 naît EN AVAL** (dans le générique / `PredictAttackRaw`), piloté par la position — PAS
    dans la base stat. Reconfirme le **point 6** (« GetStat(5)=4309 tile-indep »), REFUTE le point ★. **Le compact avait
    propagé le mauvais mécanisme** (re-vérif post-compact = user a rattrapé).
    - **Conséquence PORT** : le fix « base = Initial(3011) quand moved » (via la couche stats #63) serait du **FITTING
      sur coïncidence** — `3011 = Current − statDelta` égale `Initial`, MAIS le décompilé montre base injectée = Current
      partout. NE PAS porter ça tel quel. ⚠ La coïncidence `3011 = Initial` EXACTE (zéro arrondi) reste **suggestive** :
      possible que le générique, sous condition positionnelle, bascule `Current → Initial` (retire les modifications) OU
      soustraie exactement le total-modification — **HYPOTHÈSE à LIRE, pas à porter**.
    - **VRAIE question rouverte** : OÙ, dans le prédicteur générique (slot 0x26 → `PredictAttackRaw`, corps 3037 l.),
      la base 4309 est réduite à 3011 en fonction de la position. Candidats DÉJÀ écartés (pts 7/8/9) : GetMult (no-value),
      member-cap (skip Blast), override idx-0xd (return[0] vide), trench/RangedInMelee (magnitude −50 ≠). **NEXT** :
      deep-read du slot-0x26 (résoudre l'interface `DAT_18327ff80` idx 0x26 → fonction nommée) + de la section base de
      `PredictAttackRaw`, en cherchant un SECOND `GetStat` (part Initial/3 ?) ou une soustraction du mod-total gaté
      position/attack-state. Candidat **agent re-expert worktree** (grind lourd, lecture seule).
    - **TRACE AMONT FRAÎCHE (2026-07-05, décompilé LU) — la réduction N'EST PAS en amont de `PredictAttackRaw`** :
      `GenerateMultiHitAttackPredictions @181409da0` **itère les tuiles candidates** (`FUN_180025220(…,param_5,…)`)
      et délègue CHAQUE tuile à `ability.PredictAttack(candidatePos)` (interface `DAT_18327ff80` **slot 0x27**), puis
      bâtit un `ProbableDamageEvent` du retour — **aucun calcul de base**. `ALoki_NormalAttackAbility.PredictAttack
      @1811afa50` : `FindAttackWeapon(pos)` (choix arme mêlée/tir par tuile) → `GetAttackHitPrediction`
      (`GetStat(5)=4309` plat) → prédicteur générique **slot 0x26** avec la POSITION. `DamagePrediction.PredictAttack`
      (@181036ab0/@181036e30, les 2 overloads) : ne fait que **marshaller le scénario + résoudre la position**
      (`GetUnitPosition` si Nullable vide) puis dispatch `FUN_180031370` → `PredictAttackRaw`. **AUCUN transform de base
      dans toute cette chaîne.** ⇒ **le 4309→3011 est DANS `PredictAttackRaw`, piloté par la position** (ou par l'arme
      mêlée-vs-tir choisie par `FindAttackWeapon(pos)` — 2ᵉ candidat à écarter/confirmer : les 2 armes partagent
      Damage=30, mais base per-(tuile,cible) observée). **NEXT = deep-read `PredictAttackRaw` (locus confirmé)**, ciblé
      sur : la base pré-spread `context+0x58` (=3011 capturé) est-elle FED (depuis quel champ scénario) ou CALCULÉE
      intra-fonction depuis la position ? + réconcilier avec l'arg base Nullable(4309). Candidat **agent re-expert**.

11. **★ MÉCANISME TROUVÉ (2026-07-05, décompilé LU) — le `4309→3011` = `CalculateModifiersFromStatModifications
    @181004380`, un debuff = −Σ(stat-modifications), PAS un effet/ability spécial. ★** Chaîne : prédiction et combat
    sont DEUX chemins natifs séparés (interface `IDamageCalculations` = `DAT_183287db8`) — prédiction `PredictAttackRaw`
    via **slot idx 0xd** = `CalculateAttackerModifiersForPrediction @181000590` ; combat `CalculateAbilityDamage
    @18102cb50` via **slot idx 0xf**. Les deux partagent les feuilles (`CalculateBaseDamageWithAllModifiers`,
    `ApplyTraitDamageLimits`) mais diffèrent sur le calcul des modifiers attaquant. `CalculateAttackerModifiersForPrediction`
    appelle **`CalculateModifiersFromStatModifications @181004380`** dont le corps (LU) :
    ```
    Current = StatComponent.get_CurrentValue()                 // 4309
    if (Current != StatComponent[+0x48]=Initial /*3011*/):     // garde : "il y a des modifications"
        for (source, modifier) in StatComponent.get_Modifications():   // dict ValueModification per-source (= #63)
            amount = modifier.value ; if (param_3) amount = -amount    // <-- param_3 => NÉGATION = debuff
            list.Add(flat DamageModifier(amount))
    ```
    ⇒ **`param_3=true` produit −Σ(stat-mods) = le debuff** : base `4309 + (−1298) = 3011 = Initial`. La différenciation
    n'est PAS par-buff : ça retire TOUT le delta `Current−Initial` uniformément (source par source) ; la **condition**
    (négocier ou non) est dans l'appelant `CalculateAttackerModifiersForPrediction` selon l'attaque prédite. RapidAssault
    (+25 %) est SÉPARÉ (effet calc-time `CreateEffectDamageBonusForAttack`, ré-appliqué par-dessus). Colle aux chiffres :
    per-coup oracle = `spread(3011)×1.25` = base ramenée à Initial + RapidAssault. **RÉPONSE à « effet ou ability » :
    NI l'un NI l'autre — la couche STAT-MODIFICATION** (`ValueModification` per-source sur `StatComponent`).
    - **PORT (branche direct sur #63)** : le port a `get_stat(Initial)=3011`, `get_stat(Current)=4309`, `ValueModification.
      per_source` → `CalculateModifiersFromStatModifications` portable tel quel (énumérer per_source → émettre ±flat).
    - **DIVERGENCE STRUCTURELLE PORT (racine #49)** : le port FUSIONNE prédiction+combat (`runner/damage_model.py` importe
      `services.damage_prediction.get_attack_prediction` + même `build_attacker_modifiers_from_effects` que la prédiction).
      Le natif SÉPARE (slot 0xd préd / 0xf combat). Le port n'applique PAS `CalculateModifiersFromStatModifications` côté
      prédiction → base pleine 4309 partout → sur-préd #49. **Fix = dé-fusionner** : couche modifiers-attaquant PRÉDICTION
      (0xd, avec le debuff stat-mods) distincte du COMBAT (0xf).
    - **RESTE (2 inconnues)** : (a) la CONDITION dans `CalculateAttackerModifiersForPrediction` qui décide `param_3`
      (négocier) selon l'attaque prédite (moved ? consommé ?) ; (b) le slot COMBAT 0xf appelle-t-il AUSSI
      `CalculateModifiersFromStatModifications` (→ combat réduit aussi) ou garde-t-il 4309 (→ debuff prédiction-only) ?
      Trancher (b) = confronter live u92 PRÉDIT (`aiPredict`) vs RÉELLEMENT dealé (`UnitDamaged`).
    - **SÉPARATION FAITE (2026-07-05, structurelle, ZÉRO régression)** : xref PROUVE le debuff prédiction-only
      (`CalculateModifiersFromStatModifications @181004380` appelé QUE par `Calculate{Attacker,Defender}Modifiers
      ForPrediction`). Port dé-fusionné : (1) `damage_modifiers.calculate_modifiers_from_stat_modifications`
      (homonyme @181004380 — per-source ±flat, garde Current!=Initial) ; (2) `effects.calculate_attacker_modifiers_
      for_prediction` (homonyme @181000590 = boucle effets partagée `_attacker_effect_bonuses` + debuff GATÉ
      `apply_stat_mod_debuff`, défaut OFF) ; (3) `build_attacker_modifiers_from_effects` = COMBAT (effets seuls,
      runner inchangé) ; (4) prédiction `playbook/prediction.py:130/182` routée sur `..._for_prediction`. Smoke :
      debuff OFF == ancien chemin (byte-identique) ; debuff ON = −Σmods (−1298 sur u92). **FIT restant (task #64)** :
      passer `attack_stat` + la CONDITION `param_3` (quand négocier) + placement pré-spread vs additif-agrégat.

12. **★★ LIVE TRANCHÉ (2026-07-05, hooks statMods/attMod/predBase/Modify) — le `4309→3011` = la BASE
    `GetStat(Attack,Current)` avec le `+1298` conditionnel, PAS un modifier. ★★** Capture seed 31337 (drive,
    session 11) :
    - **`negate`** (`CalculateModifiersFromStatModifications` args[2], hook FONCTION = non-ambigu) : **attaquant=0
      (ADD)**, défenseur=1 (SUB) — split 415/415. (Mon seam utilisait subtract côté attaquant = mauvaise direction.)
    - **RED HERRING** : `CalculateAttackerModifiersForPrediction` retourne `additive (retval+0x10) = 0.0` sur les
      415 appels → le `+1298` produit par `CalculateModifiersFromStatModifications` (listCount=1) **NE SURVIT PAS**
      dans le DamageModifiers appliqué. Ce n'est donc PAS le canal du gap.
    - **LA BASE est le canal** : `predBase.f58` (base pré-spread fed to PredictAttackRaw = `GetStat(Attack,Current)`)
      prend pour u92 **3011 ET 4309** (4309 = Initial 3011 + mod 1298 ; AUCUN autre unit n'a Initial 3011 ni 4309 →
      les deux sont u92). Et `statMods` voit le MÊME stat Attack u92 (Initial=3011) avec **`mod10 (ValueModification.
      total) = 0` (→3011) OU `= 1298` (→4309)**, une seule source (listCount=1).
    - **PAS togglé via `Modify`** : hook `ValueModification.Modify(|amount|>=500)` = **0 event**. Donc le `+1298`
      n'est PAS écrit/retiré sur le stat réel pendant la prédiction → les 2 états viennent de **stat objects
      DIFFÉRENTS / une ré-évaluation CONTEXTE** : la prédiction évalue `GetStat` contre un **état d'attaque
      hypothétique** où le buff RapidAssault-family (statDelta.movement=1 co-occurre) est **présent OU CONSOMMÉ**
      (post-move). not-moved → buff → 4309 ; moved (buff consommé) → 3011.
    - **BLOQUÉ** : `curCaster=(-1,-1)` sur toute la capture (le hook RVA `CalculateActionUtility` n'a pas posé la
      tuile sur le chemin de scoring du drive) → corrélation exacte tuile/arme non obtenue cette passe.
    - **FIT (redirigé, task #64)** : le fix N'EST PAS un debuff modifier (mon seam `apply_stat_mod_debuff` = mauvais
      axe, reste OFF). Le fix est sur **la BASE de `predict_attack_raw` (chemin PRÉDICTION)** : base par-candidat =
      `GetStat(Attack)` résolvant la modif conditionnelle — `Current` (4309, buff) quand il s'applique, base sans la
      source conditionnelle (`Initial`-like 3011) quand l'attaque prédite le consomme. Pile la couche #63
      (`get_stat(Initial)` + per-source). Gate ≈ `has_moved` (déjà threadé) — 1er jet, à raffiner via agreement
      `aiPredict{col,row}` par-tuile (le doc note (4,5) moved garde 4309 → gate pas binaire pur). La séparation
      des branches (préd/combat) reste JUSTE — c'est bien le chemin prédiction qui porte le base-conditionnel.

13. **★ TUILE CORRÉLÉE (2026-07-05, curCaster réparé via scan du context PredictAttackRaw, sessions 12-13) ★.**
    `curCaster` (via `CalculateActionUtility`) était `(-1,-1)` car les prédictions sont DÉCOUPLÉES du scoring
    (predict-then-score). Fix : `predBase` (PredictAttackRaw onEnter) **scanne le context (args[2]) pour la
    UnitPosition candidate** → tuile robuste, propagée aux hooks nestés. Mesure (seed 31337) :
    - **u92 base=4309 (buff) UNIQUEMENT aux tuiles `{(5,5),(4,5)}`** (courante + 1 adjacente) ; **base=3011
      (raw) à CES tuiles AUSSI + partout ailleurs**. Donc la tuile caster seule N'EST PAS le discriminant :
      à (5,5)/(4,5), les DEUX bases coexistent → c'est **per-(tuile, cible/arme)**, pas per-tuile.
    - **Les prédictions 4309 n'ont AUCUN scenario per-coup** (`CalculateDamagePredictionScenario`) ; seules
      les 3011 en ont (rawMax=3613=3011×1.2). Cohérent avec **4309 = MÊLÉE** (`DamageProfile.HasTrait(0)`
      SKIP la boucle per-coup, cf. §2) et **3011 = Ranged Blast** (per-coup).
    - **HYPOTHÈSE FORTE (mesurée mais pas 100% isolée — join base↔arme bruité car (tuile,cible) non-unique
      à u92)** : le buff `+1298` s'applique à l'attaque **MÊLÉE** (base 4309), PAS au **Ranged Blast** (base
      3011). #49 porte justement sur le Blast ranged → **base ranged = Initial 3011 (buff exclu)** ; le port
      prend Current 4309 → sur-prédit. Mêlée seulement géométriquement possible près de la position courante
      (ennemi adjacent) → explique 4309 confiné à (5,5)/(4,5).
    - **FIX #49 (mesuré pour le cas ranged) :** la prédiction du Ranged Blast doit partir de la base **RAW
      (Initial-like, buff conditionnel exclu)**, pas de Current. Généralement : base par-candidat = GetStat
      résolvant le buff conditionnel PAR ARME (mêlée buffée / ranged raw). Reste à confirmer proprement l'axe
      arme (1 capture ciblée : target ajouté à predBase) + identifier la source exacte du +1298 (listCount=1).
      NE PAS fitter has_moved (réfuté : (4,5) déplacée garde 4309 côté mêlée).

14. **★★★ #49 RÉSOLU (2026-07-05, option A — aiPredict ORACLE + décomposition numérique + snapshot PORT). RÉFUTE
    l'hypothèse mêlée/ranged du point 13. ★★★** La base de l'attaque NORMALE de u92 = **Attack INITIAL (3011) pour
    LES DEUX armes** ; l'écart per-coup mêlée(1404)/ranged(2006) du point 13 était une **MAUVAISE ATTRIBUTION** — il
    vient du **PERÇAGE (mêlée p1 vs ranged p15)**, PAS de la base (l'armure `after_armor=d−armor` domine le plancher
    perçage → ranged pierce+haut passe plus). Preuve DÉCISIVE (aiPredict, armure 2008, ×1.25 RapidAssault) :
    - base **3011** + spread ±20 % + `GetDamageWithPiercing` + ×1.25 reproduit l'oracle **EXACT** : u82 ranged
      `(1503,6018)`, u82 mêlée idem chaîne, u84 `(2634,7146)≈(2634,7149)`, u86 `=×1.5 ÉLÉVATION` → `1503×1.5=2256`
      = oracle `2256`. base **4309** donne `(5397,11862)` = la SUR-PRÉDICTION du port.
    - **Snapshot PORT confirmé** (`ctx.stats.get_stat`) : u92 Attack `Initial(part3)=3011`, `mod(part5)=+1298`,
      `Current(part0)=4309`. `ctx.stat(ATTACK)` (ce que la prédiction utilise) = **4309** → sur-préd.
    - **Effets live u92** (`decisionView.effects`) = **UNIQUEMENT RapidAssault** (Movement eff130 + ExtraDamage
      eff131 = le +25 % = le ×1.25 déjà capturé en `mods`). AUCUN effet n'ajoute +1298 Attack → le `+1298` est une
      **ValueModification en-bataille (conditionnelle, non-effet)** que la prédiction native EXCLUT de la base.
    - **Mécanisme RE** (`CalculateModifiersFromStatModifications @181004380`, LU) : garde `if Current != Initial(+0x48)`,
      puis boucle la Dict `ValueModification.Modifications` PAR SOURCE → émet un modifier `{kind=1, ±amount}`
      (`param_3=0` → `+`, sinon `−`). En prédiction, le stat-context est PROPRE (`Current==Initial`) → émet 0 ; la
      base `context+0x58` reçue par `PredictAttackRaw` = **Initial (3011)** (mesuré `predBase.f58`). Le port a un
      snapshot SALE (`Current=4309`, mod +1298) → il doit partir d'**Initial**, PAS re-jouer `CalcModsFromStatMods`
      dessus (sinon +1298 recompté).
    - **FIX APPLIQUÉ (oracle-validé) : la base de l'attaque NORMALE en PRÉDICTION = `GetStat(Attack, Initial)`**, pas
      `Current`. Reproduit l'oracle EXACT sur les plans TOP-rankés u82/u84 ; seed777 CLEAN=11/0. Ne change QUE
      `Current!=Initial`. ⚠ **VOIR POINT 15 — c'est un FIT, PAS le mécanisme fidèle.**

15. **⚠⚠ CORRECTION (2026-07-05, challenge utilisateur « tu as RE ça ? ») — le fix point 14 (`base=Initial`) est un
    FIT, le mécanisme natif N'EST PAS « Initial ». ⚠⚠** RE poussée révèle :
    - **Chemin scoring** (`aiPredict` = `DamagePredictionQuery.GetAllPredictions` → `GetNormalAttackPrediction @181092b60`
      → `FUN_18000cdc0` → `ability.PredictAttack` → `ALoki_NormalAttackAbility.GetAttackHitPrediction @1811af4e0`) LIT
      la base = **`GetStat(Attack, statType=5, part=0=Current)` = 4309**, PAS Initial. (`GetAttackHitPrediction` idem
      pour le display.) Donc le natif part de **Current**, pas Initial.
    - **Réconciliation** : `statMods` a mesuré (probe49_clean, MÊME passe de scoring) le stat Attack de u92
      (`Initial=3011`) avec **`mod_total` VARIABLE par candidat = `{0, 400, 898, 1298}`** (Current = `{3011, 3411,
      3909, 4309}`). ⇒ **`Current` est RÉ-ÉVALUÉ PAR CANDIDAT** : une modification Attack **conditionnelle**
      (source flat +400/+898/+1298 NON identifiée ; PAS RapidAssault qui est le ×1.25 %) qui s'applique selon le
      scénario du candidat (tuile/état). Le plan ranged scoré avait `mod=0` → base `Current=3011` (== Initial par
      coïncidence). `base=Initial` matche u92 SEULEMENT parce que le buff conditionnel est INACTIF sur les plans scorés.
    - **Conséquence (le caveat de l'utilisateur est JUSTE)** : un buff Attack **inconditionnel** (toujours dans
      Current, ré-évalué actif à chaque candidat) serait INCLUS par le natif (base = Current buffé) mais EXCLU par
      `base=Initial` → **sous-prédiction**. `base=Initial` n'est donc PAS fidèle en général ; il fit le cas
      u92 (conditionnel-inactif-sur-plans-scorés).
    - **VRAI mécanisme (hypothèse à confirmer)** : base = `GetStat(Attack, Current)` **ré-évalué pour le scénario du
      candidat** (modifs conditionnelles appliquées per-candidat). Le port a un snapshot STATIQUE (Current figé au
      moment du snapshot, buff actif → 4309) → il ne peut pas ré-évaluer sans modéliser la/les modif(s)
      conditionnelle(s). **RESTE À RE** : (1) identifier la source du flat conditionnel +400/+898/+1298 sur Attack
      u92 (per-candidat) ; (2) LIRE où/comment `ability.PredictAttack`→`PredictAttackRaw` obtient `context+0x58=3011`
      alors que `GetAttackHitPrediction` lit `GetStat(Current)` — la réduction 4309→3011 par candidat (via
      `CalculateAttackerModifiersForPrediction`/`CalcModsFromStatMods` négate, ou re-résolution de la condition).
    - **STATUT** : #49 ré-ouvert. Le fix `base=Initial` reste EN PLACE comme **amélioration** (réduit la sur-préd,
      oracle-matche les plans scorés, no-régression) mais **TAGGÉ FIT** — à remplacer par la ré-évaluation
      conditionnelle une fois RE. NE PAS considérer #49 clos.

16. **★★★ VERDICT re-expert (2026-07-05, décompilé LU, worktree sur `6cc3fec`) — CONFIRME le point 15 : base =
    `GetStat(Current)` ré-évalué par candidat, PAS de réduction. ★★★**
    - **Q2 tranché** : `ALoki_NormalAttackAbility.GetAttackHitPrediction @1811af4e0` injecte la base = `GetStat(
      attacker, damageStat=5, part0=Current)` **telle quelle** dans le prédicteur générique (slot 0x26 →
      `PredictAttackRaw` `context+0x58`). AUCUNE lecture d'Initial, AUCUN `op_Subtraction`, AUCUN override dans ce
      chemin. `get_CurrentValue @180fa91d0` = `clamp(Initial[+0x48] + Σ modifications per-source[+0x10])`. ⇒ **4309
      et 3011 = deux valeurs de `Current` différentes** (mods présents/absents selon le candidat), PAS une réduction.
    - **Réponse au caveat (CONFIRMÉ)** : un buff Attack **INCONDITIONNEL** (toujours dans `Current`) EST inclus dans
      la base ⇒ **`base=Initial` est faux en général** (jette TOUS les mods, même permanents). Le fit u92 ne marche
      que parce que son `+1298` est absent (`mod=0`) sur les plans ranged/moved scorés.
    - **+1298 = un `ValueModification` per-source** (StatComponent+0x10 dict), PAS les effets calc-time nommés :
      `RapidAssault_ExtraDamageEffect.CreateEffectDamageBonusForAttack @180f67940` = `EffectBonus.ForPercentIncrease`
      (le ×1.25) ; `BlackRage_ExtraDamageEffect @180f340e0` = trigger DSL `IsCharging & IsNormalAttack` → `ConfigVar(8)`
      (+728) — **les deux sont des modifiers post-base, PAS la base**. `CalculateModifiersFromStatModifications
      @181004380` = producteur de `List<DamageModifier>` post-base (mesuré non-survivant, additive=0), **orthogonal
      à la base** — le laisser OFF.
    - **Lead source (hypothèse, bloqué statiquement par dispatch virtuel + pas de roster)** : `BlackRageAbility.
      ExecuteBehaviour @1811b9c20` applique `AddStaticStatModifierEffect(0x53e, ConfigConst(0xe))` = un stat-mod PLAT
      (famille BlackRage/kit) — candidat pour le `+1298` (=400+898, >=2 sources) présent dans les états simulés
      near-current/charge-mêlée, absent pour le Blast ranged depuis une tuile moved. `has_moved` binaire RÉFUTÉ
      ((4,5) moved garde 4309).
    - **FIX FIDÈLE (à coder après probe)** : `make_normal_attack_predictions` base per-candidat = `Initial +
      Σ(ValueModifications ACTIFS pour ce candidat)` — décomposer le `Current` figé (4309) en `Initial + deltas
      per-source` (socle #63 : `get_stat(Current/Initial)`, `ValueModification.per_source`) puis gate `is_active`
      par candidat (arme mêlée/tir via weapon-select partagé #57, has_moved, charge). NE PAS basculer sur Initial.
    - **PROBE LIVE REQUIS pour lever l'hypothèse** (avant de coder le gate) : (A) hook `StatComponent.get_Modifications`
      (ou le predBase existant) → dumper par candidat {tuile, arme, chaque source `AbilityOrEffect id` + amount} ;
      (B) dumper le dict Modifications du stat de dégât u92 dans l'état COURANT sans simulation : `+1298` présent →
      mod réel actif (identifier source) ; absent → introduit en simulation (BlackRage-family) → `base=Initial`
      safe pour l'attaque normale de u92. Tranche source + gate exact.
    - **Alerte port relevée par re-expert** : incohérence d'index de stat (`stats.py ATTACK=0/HEALTH=5` vs
      `damage_combat.py STAT_HEALTH=4/STAT_ARMOR=5`) = probablement 2 enums natifs distincts. La VALEUR 4309 est
      juste (probe #63 confirmé) ; l'étiquette d'index peut mentir — à vérifier avant de toucher la base.

17. **#58 ÉLÉVATION — mécanisme CONFIRMÉ + wiring (2026-07-05).** `CalculateElevationBonusModifier @181003ea0` LU :
    bonus `+ElevationBonus` si `attackerTile.elev > GetMainTile(cible).elev` ; SAUTÉ si attaquant OU cible a l'effet
    `0x423` (effectType 1059). **PER-TUILE CANDIDATE** (mesuré aiPredict u90→u86 seed777 : tuile (5,4)elev3 →
    (2048,7592) vs tuile (3,5)elev2 → (1364,5060) = **×1.5 EXACT**). Le port `_add_positional_and_defender_mods`
    avait le modifier câblé mais `elev_by_pos` VIDE (jamais peuplé) → élévation no-op. **FIX** : `scene.build_elev_by_pos`
    (RPC `boardGraph`, statique 1×/runner) peuple `elev_by_pos` dans `build_predictor` ; `from_predictor_sctx` le
    propage ; gate `0x423` câblé (via `_has_effect_type`, effectType 1059 — non testé, absent des seeds). VALIDÉ :
    u92→u86 seed31337 = (2256,5522) EXACT (`mods=[1.25,1.5]`). Résidus u90→u86 (seed777) / u96→u86 = **PAS
    élévation** (base flat / armure-PowerTrip / défenseur #50 — l'élévation ×1.5 est appliquée IDENTIQUEMENT des 2
    côtés ; l'écart est dans la base flat). Chaîne COMBAT (runner) = fork déféré (cf. #58 desc).

18. **★★★ #49 SOURCE NAILÉE (2026-07-05, probe gate + recon) : le `+1298` = AURA `RitesOfBattle` (Calgar), PAS
    BlackRage. ★★★** Probe base(predBase.f58)↔tuile pour u92 (seed 31337) : **base=4309 (buff) aux tuiles
    adjacentes à Calgar `(4,4)`** ((5,5)/(4,5)), **3011 ailleurs**. Recon : **u88=ultraCalgar @(4,4)** porte
    `RitesOfBattle_ExtraDmg` (effets 1002 Basic + 1003 Imperial). `gameconfig RitesOfBattle` = « Adjacent friendly
    units gain +655 Damage. **Imperial** units gain +946 instead ». u92 (bloodDeathCompany = BloodAngels/**Imperial**)
    adjacent → buff (+946 base, ~+1298 au niveau réel de Calgar). ⇒ **le `+1298` est une `ValueModification` sur
    l'Attack de u92 émise par l'AURA de Calgar, RÉ-ÉVALUÉE PAR TUILE (adjacence à la source)** : u92 s'éloigne de
    Calgar → perd le buff → 3011. C'est exactement la « re-résolution par candidat » du point 16.
    - **Pourquoi le port rate ça** : la buff RitesOfBattle sur u92 N'EST PAS dans `decisionView.effects(u92)` (qui
      ne montre que RapidAssault) — elle est appliquée comme `ValueModification` brute (aura), donc le port la voit
      seulement comme `statDelta` opaque non-attribué (Current figé 4309). Le port A la classe
      `RitesOfBattleExtraDmgEffect` (loki.py, stat-mod Attack) MAIS elle est pilotée par un effet CAPTURÉ sur l'unité
      buffée — u92 n'a pas d'effet RitesOfBattle capté → non instanciée, non ré-évaluée par tuile.
    - **FIX FIDÈLE (= tranche AURA, plus gros que #49)** : modéliser les auras `+dégât` d'allié adjacent
      (RitesOfBattle, et génériques `SurroundingUnits`/`GetOtherTargets`) comme **stat-mods PER-CANDIDAT** : pour
      chaque tuile d'attaque candidate, re-tester l'adjacence de l'attaquant à chaque allié porteur d'aura et
      ajouter/retirer le delta à la base. Le socle #63 (`ValueModification.per_source`) + la géométrie hex
      (`are_tiles_adjacent`) sont là. `base=Initial` reste un FIT stopgap (marche pour les plans ranged scorés qui
      s'éloignent de Calgar ; sous-prédirait une attaque mêlée où u92 RESTE adjacent à Calgar → natif 4309).
    - **Reste à confirmer bit-exact (optionnel)** : le montant précis (+946 vs +1298 = scaling niveau Calgar ; +655
      Basic vs +946 Imperial → quelle variante `extraDmg`/`extraDmg_2`) + la portée exacte de l'aura (adjacence pure
      d1 ou range) via aiPredict par-tuile propre (predBase tile-scan bruité). Source/mécanisme = ACQUIS.

19. **★★★ #49 IMPLÉMENTÉ + VALIDÉ (2026-07-05, re-expert @181225340 + oracle). ★★★** Spec native prouvée
    (re-expert, décompilé) : `RitesOfBattleAbility.CreateBehaviour @181225340` → 2 `DynamicStatModifierEffect`
    permanents sur Calgar ; `CreateTargetSelector` = `AdjacentUnits(1) @180de8320` (source exclue) →
    `Friends @180df0040` → `With/WithoutTrait(0x1a=26)` (26 = Imperial, `GrandAlliance.GetTrait @1815647a0`,
    ABSENT de gameconfig.traits → dérivé de GrandAllianceId) ; montant = `GetVariableForLevel(idx8→extraDmg |
    idx9→extraDmg_2, niveau SOURCE) × mult SOURCE`. Mutuellement exclusifs ("instead"). **PORT (fidèle)** :
    `RitesOfBattleExtraDmgEffect.create_aura_attack_bonus` (loki.py, SOURCE-side, gate adjacence+équipe+
    faction, variant via `self.name` Basic/Imperial) ; agrégateur `aura_attack_bonus_from_allies`
    (effects/__init__.py, mirror `aura_hits_malus_for_defense`) ; `make_normal_attack_predictions` base =
    `GetStat(Attack, INITIAL) + Σ aura` (per-candidat). Factory : enregistrer les noms EXACTS
    `RitesOfBattle_ExtraDmgBasic`/`...Imperial` (l'ancien `RitesOfBattle_ExtraDmg` ne matchait jamais →
    effets = BaseEffect morts). Retiré `get_stat_modification_*` target-side (mauvais modèle : le porteur ne
    se self-buff pas). **VALIDÉ** : u92 adj-Calgar base=4309, far=3011 (extraDmg_2[L50]×1.8=1298 EXACT) ;
    Calgar own base=2811=Initial (pas de self-buff) ; seed31337 CLEAN=8/0 ; seed777 no-régression (résidu
    u90→u86 = PowerTrip/armure, séparé). Généralisation restante (re-expert) : `Spotter_ExtraDmg`
    (SurroundingUnits range config, trait 1001) même patron ; `StandVigil_ExtraDmg` à confirmer ; le `+400`
    = une 2e aura non identifiée. `base=Initial` FIT SUPERSÉDÉ.

20. **★★★ POST-MORTEM #49 — 2 leçons de diag (pourquoi ~8 h sur l'aura) + outillage (2026-07-05). ★★★**
    - **Leçon RECON** : un écart de base (`statDelta`) **non expliqué par le kit PROPRE de l'unité** (traits +
      abilities gameconfig) doit faire **suspecter une AURA d'allié adjacent**, PAS une erreur d'agrégation dégât ni
      un weapon-split. Le `+1298` de u92 a été cherché dans son kit, puis dans le multi-coup, puis dans le split
      mêlée/ranged (3011↔4309) — c'était Calgar (RitesOfBattle) adjacent. **`decisionView.effects` est AVEUGLE aux
      auras** : les stat-mods d'aura sont posés comme `ValueModification` **bruts** sur le stat du buffé (Dict keyé
      par l'entité SOURCE), **jamais** matérialisés en `EffectComponent` sur le buffé → une analyse effet-centrique
      ne peut PAS les voir. Le natif les ré-inclut via `GetStat(Current) = Initial + Σ(ValueModifications actives)`,
      ré-évalué par tuile candidate (adjacence recalculée). Réflexe : recon kit complet (cf.
      `feedback_recon_full_kit_not_captured_effects`) → si inexpliqué, chercher un **porteur d'aura adjacent**
      (RitesOfBattle=Calgar, Spotter, PathOfCommand, StandVigil-self…).
    - **Leçon OUTILLAGE** : sourcer un `statDelta` opaque doit être une **LECTURE**, pas une triangulation
      (base↔tuile + recon allié + gameconfig). RPC **`statModSources`** (rpc-view.ts, à côté de `combatSnapshot`)
      lit la décomposition **par source** de la `ValueModification` d'un stat : `{source: entityId, amount, self,
      sourceIsUnit}` + `total` + `residual`. Mécanisme (décompilé-vérifié) = `GetStat(entity, statType,
      StatPart=5, Nullable<BEntityId>=src)` → `StatComponent.GetStatPart @180fa8bb0` case 5/9 : src null →
      `*(int*)(comp+0x10)` total ; src fournie → `ValueModification.GetModificationFromEntity(comp+0x10, srcId)
      @180fadf10` (Dict keyé par l'entité **EFFET** qui a posé la modif — `sourceIsUnit=false` ; mapper effet→owner
      pour remonter au porteur UNIT). On scanne les entités comme sources candidates ; `residual = total − Σ` : 0 =
      tout attribué à des entités (aura/self) ; non-nul = source non-entité (setup `ModifyUnit*`). **Limite** : ne
      montre l'aura d'adjacence QUE si l'unité est **actuellement adjacente** au porteur (sinon la `ValueModification`
      ne la contient pas — cf. re-éval par position). Chaîne stat native complète : [`../stat-system.md`](../stat-system.md) §3.
    - **★ VALIDÉ LIVE (démo #49, 2026-07-05) ★** : runner `ultraCalgar`(u80,(1,0)) + `bloodDeathCompany`(u82,(0,0)) team 1,
      adjacents. `statModSources(u82)` → `attack{total:1298, residual:0, bySource:[{source:97 (effet
      RitesOfBattle_ExtraDmgImperial), amount:1298, sourceIsUnit:false}]}` (= `extraDmg_2[L50]×1.8`, exact #49) ; cross-check
      `combatSnapshot` u82 attack=4309 statDelta.attack=1298 (concorde), Calgar attack=2811 statDelta={} (pas de self-buff).
      `decisionView.effects(u82)` ne montre PAS l'aura (seulement RapidAssault) — cécité confirmée. Puis **u82 déplacé (0,0)→(0,3)
      hors adjacence → l'aura attack DISPARAÎT** (statModSources ne rend plus que `movement:+1` self) = preuve causale + démonstration
      de la ré-éval par position. **Statut** : implémenté + build + décompilé-vérifié + VALIDÉ LIVE. NON commité. (Note harnais :
      le « buildRunner system error » vu au smoke initial n'était PAS un wedge PID mais `getLiveBattleConfig` rendant un
      `_currentBattle` PvP stale = `JPropertyKeyedCollection` qui masquait la BC campagne valide → corrigé par type-guard
      `BattleConfiguration` dans battle-config.ts.)

21. **★★★ #67 CORRECTION (2026-07-09, verdict re-expert acf1a624 + fix + validé) — l'aura n'est PAS
    ré-évaluée par TUILE CANDIDATE : elle est bakée à la POSITION RÉELLE. ★★★** Les points 16/18/19/20
    disaient « aura ré-évaluée PAR TUILE CANDIDATE » (le port ajoutait le delta d'aura à chaque
    `attack_pos` candidate en re-testant l'adjacence attaquant↔porteur). **C'était le bug #67** :
    sur les ~24/28 tuiles candidates NON hex-adjacentes à Calgar le port donnait `base=3011` (aura
    absente), alors que l'oracle DISPLAY donne 4309 sur TOUTES les tuiles.
    - **RE** : `GetAttackHitPrediction @1811af4e0` lit `GetStat(Attack, Current)` **SANS argument de
      position**. L'aura (`DynamicStatModifierEffect @181225340`) est **bakée dans le StatComponent** du
      bénéficiaire, refresh **EVENT-DRIVEN** (`RefreshValueInternal @180f09220` — déploiement + entrée/
      sortie de ring sur un **MOVE RÉEL**), **PAS re-testée à chaque `GetStat`**. La prédiction déplace
      l'attaquant virtuellement pour la GÉOMÉTRIE seule (élévation/distance/arme, slot 0x26), **jamais**
      pour re-baker Attack. ⇒ la valeur bakée à la **position réelle** s'applique **IDENTIQUEMENT** à
      toutes les tuiles candidates. **Distinguer** : « re-éval par POSITION RÉELLE » (moves réels,
      event-driven — CORRECT, cf. point 20 `statModSources` : l'aura disparaît quand u82 **bouge**
      réellement hors adjacence) ≠ « re-éval par tuile candidate DISPLAY » (ce que le port faisait à
      tort).
    - **FIX (prediction.py ~179)** : aura évaluée à `scene.pos(att_id)` (position réelle), **jamais** à
      `attack_pos` (tuile candidate). 1 ligne. Bénéficie à PathOfCommand (même funnel
      `aura_attack_bonus_from_allies`). Combat (runner) intact (lit `GetStat` réel). #64 (debuff stat-mod)
      non touché.
    - **VALIDÉ** : `tests/engine/test_aura_position_live.py` (ultraCalgar + bloodDeathCompany=u82/u92) —
      attaquant adjacent au porteur → `base` CONSTANT = Initial+aura sur TOUTES les tuiles candidates
      (**3011+1298=4309**, y compris la tuile far où le bug donnait 3011) ; attaquant éloigné → `base`
      CONSTANT = Initial bare (**3011**). No-rég : deep_strike + predict_live 3/3. Le résidu (6,4)=2256 =
      axe élévation/arme SÉPARÉ, hors #67 (case-49 : NE PAS le fitter).

**2ᵉ axe (séparé = #50)** : à armure égale (u82/u86 = 2008), per-coup oracle diffère (501 vs 752) → modifier
DÉFENSEUR par-cible. **MAJ** : pour u86, le 752 = 501×1.5 (ÉLÉVATION depuis (6,4) elev3), pas un modif défenseur
→ ce cas u82/u86 est ÉLÉVATION, pas #50 (cf. bloc MOVE CONFIRMÉ).

---

## 9. Prédiction de SOIN (heal) — RE complet + port offline

La chaîne soin est **entièrement RE'd et offline-calculable** (manque #1 / [`status.md`](status.md) §3.1
débloqué côté heal). Tout est dans `engine/predict.py` (PARTIE 3), porté 1:1.

---

## 10. VERDICT RE (2026-07-11, agent re-expert worktree) — `PredictAttackRaw @181032fb0` lu intégralement : Q1/Q2/Q3

Scratch de travail : `.../scratchpad/predictattackraw.c` (3037 l.). Chaîne native mirrorée :
```
GetMultiHitAttackPrediction @181066080 -> get_multi_hit_attack_prediction  (boucle xhits + prev + Add)
  \ GetAttackPrediction @18105e090   (dispatch vtable ability, litteral hits=1)
     \ PredictAttack @181036ab0 (box request) -> PredictAttackRaw @181032fb0 -> predict_attack_raw (UN coup)
        - base : GetValueOrDefault(param_3+0x58) [L1483] + override nullable idx0xd [L1500] + max(0) [L1491]
                 -> flag@+0x6a==0 ? min=max=d [L1548] : GetBaseDamageFix64 @181030ba0 [L1642]
        - additif : base_int + Addition(+0x10 mods#1[idx0xd]) + Addition(+0x10 mods#2[idx0xe]) [L1940/L2062, PRE-percage]
                 -> CalculateBaseDamageWithAllModifiers @18102d3f0 (ne lit PAS Addition@+0x10, acquis #75)
        - scenarios : CalculateDamagePredictionScenario @18102ed00 [L2476/L2566]
  \ DamagePredictionResult.Add @18102a710 (Somme champ-par-champ + ApplyCap)
```

### Q2 — Agregat multi-coups : CONFIRME (port fidele, AUCUN changement)
Le xhits est HORS de PredictAttackRaw. `GetMultiHitAttackPrediction @181066080` : coup 1 prev zero-init ;
boucle `hits-1` fois avec `get_DefaultBlockScenario` cumule -> `Nullable<>` -> prev ; `Add` a chaque iter.
`GetAttackPrediction @18105e090` dispatch vtable avec **litteral hits=1** (PredictAttackRaw = UN coup).
`Add @18102a710` = somme champ-par-champ + ApplyCap : `AccurateHealthDamage@0x58 = Sigma per-coup`,
`AppliedHits@0xBC` accumule. Confiance HAUTE, entierement lu.

### Q3 — Additif (Addition@+0x10) en PREDICTION : PRE-percage (comme le combat #75) — ACTIONNABLE
Les 2 appels CBDWAM (MIN L1940, MAX L2062) recoivent `param_2 = base + Addition(mods#1@+0x10) + Addition(mods#2@+0x10)`.
`Addition = puVar34[2] = champ +0x10` des 2 structs DamageModifiers (idx 0xd L1473, idx 0xe L1796).
CBDWAM @18102d3f0 ne consomme QUE l'int base + Override/Multiplier (idx 0x10/0x11), **jamais Addition@+0x10**
(acquis #75 confirme mot pour mot). AUCUN re-add d'additif apres CBDWAM (resultat -> ApplyTraitDamageLimits
-> CDS). => **Le natif place l'additif PRE-percage en prediction, identique au combat.**
- **Port** : BASCULER le defaut du chemin prediction a `attacker_additive_pre=True` (branche deja presente
  L245-252 de damage_prediction.py : `d = round(d + mods.additive)` avant `get_damage_with_piercing`, puis
  `apply_capped_modifiers` SEUL). Aujourd'hui la prediction est en POST-percage (`False`).
- **Reconciliation #88** (Neuroparasite -582, pierce 100) : additif pre-percage avec pierce 100 -> survit
  entier dans la base (pas d'armure) = comportement natif. Coherent.
- **RISQUE regression** : #49/#64 etaient "valides" en POST-percage. La bascule change leurs bornes SSI
  l'ability porte un additif != 0 ET pierce<100/armure>0. Re-confronter #49/#64/#88 apres bascule (validator,
  `damage_decomp.py`, decompo PAR ETAGE). Le natif est sans ambiguite ; toute regression = capture
  additif/pierce erronee, PAS le placement. HYPOTHESE mineure sans impact : mods#1(idx0xd)=attaquant vs
  mods#2(idx0xe)=defenseur additives (les 2 Additions sont sommees identiquement min/max -> le port qui
  additionne `mods.additive` total est correct).

### Q1 — Chemin "special"/predefinedRange : le facteur `2.2` est une INVENTION (a retirer)
Le natif ne produit JAMAIS `(ceil(0.8*d/hits), ceil(2.2*d/hits))`. La base `dmgMM` (local_938) d'UN coup :
1. `d = Nullable<int>.GetValueOrDefault(param_3+0x58)` [@1810348dd] = **scalaire de damage PAR COUP** (0 si absent).
2. Optionnel : `Nullable<Fix64>` idx 0xd [L1473] -> si HasValue, **ecrase** d (`op_Explicit` L1500-1512).
3. `d = max(0, d)` [L1491].
4. Selon un **byte flag @param_3+0x6a** (`(char)(param_3[0xd] >> 0x10)`, teste L1547) :
   - **flag == 0** -> `dmgMM.min = dmgMM.max = FromInt(d)` [L1548-1564] : **range DEGENERE, min==max==d, PAS de spread**.
   - **flag != 0** -> `GetBaseDamageFix64(d, ...)` [L1642] : **spread standard ±20% + ExtraMaxDamage** (chemin normal).
`GetBaseDamageFix64 @181030ba0` (lu) : min=f8(weapon,d) slot8, max=f9(weapon,d)+FromInt(ExtraMaxDamage) slot9.
Ni 0.8 ni 2.2 nulle part. Le "predefinedRange" +0x58 = **Nullable<int> SCALAIRE (pas {min,max})** ; le range
{min,max} est CONSTRUIT en aval par l'un des 2 chemins. Setter : `<Ability>Playbook.MakeDamagePredictions` ->
`GenerateMultiHitAttackPredictions @181409da0` construit le request (ex. `PlasmaCannonPlaybook @181150b10`
pose damageFormula/hits/Nullable<int> + un `param_10` fraction-provider AoE-falloff).
- **Port** : SUPPRIMER le `(0.8/2.2)` (L376-379 damage_prediction.py). Remplacer par un gate `ignore_spread`
  (byte @+0x6a) : `ignore_spread -> MinMaxDamage(d,d)` sinon `get_base_damage_fix64(d, extra_max, spread, is_max_out)`.
- **HYPOTHESES a confirmer LIVE avant de porter** (n'affectent pas "2.2 est faux") : (1) semantique exacte du
  flag @+0x6a (nom plausible `IgnoreDamageSpread`, `CachedDamagePrediction$$get_IgnoreDamageSpread @180e304a0`
  lit +0x10 ; PAS relie bit-a-bit au byte +0x6a) ; (2) +0x58 stocke le damage TOTAL (a /hits) ou DEJA par-coup.
  Trancher via `damage_decomp.py` sur une special a range fixe (PlasmaCannon/BasiliskBarrage/HellfireShells) :
  lire `dmgMM` per-coup, comparer a d et d/hits, NE PAS fitter. Enumeration complete des abilities posant le
  flag no-spread = tache de fidelite ouverte.

#### MAJ #96 REVERTÉ + #98 RÉSOLU (2026-07-11) — le piège aiPredict, CrushingStrike×Élévation, composition %-list

**⚠⚠ #96 REVERTÉ — la « preuve bit-exacte » `aiPredict(1150) == aiPredict(69) == [11940,17907]` était un
ARTEFACT DE MESURE, pas un mécanisme.** Élucidation (session Fable) :
- `aiPredict` invoque `DamagePredictionQuery.GetAllPredictions(unit, tile, ability) @181090f50` (via le wrapper
  `CachedDamagePredictionQuery @180e2d990`, clé = {unitId, tileId, abilityType} — l'ability EST dans la clé, le
  cache n'était PAS le coupable). Vérifié avec le nouveau `aiPredict {fresh:true}` (query interne @+0x10, sans
  cache) : PlasmaCannon fresh == normale fresh == `[11940,17907]`. **C'est la SÉMANTIQUE de GetAllPredictions :
  un PREVIEW decisionView dont le dégât est Attack-based quel que soit l'abilityType — PAS le dégât per-ability
  du PLAYBOOK de décision.** Toute « preuve » par égalité aiPredict(special)==aiPredict(normale) est invalide.
- **La vérité PLAYBOOK** (ce que le port mirror) = les évaluations FRAÎCHES du tour de décision IA, captées
  modifier-observe PENDANT le remplissage du cache (`aiPlayByUnit` observé) : PlasmaCannon y est **CONFIG-based**
  — bouts per-coup `1117/1675` = `maxDmg[65]=1164 × mult 120% = 1396 ± 20%` (`minDmg` IGNORÉ : base =
  `predefinedRange` SCALAIRE = var maxDmg id 0xd, RE Étape-0 #52), ×mods ranged `×1.875 = HeavyWeapon(1.25) ×
  Élévation(1.5)` visibles dans `predCalcDumps`. → PlasmaCannon **retiré** de `_PREDICT_VIA_NORMAL_ATTACK` ;
  base spéciale du port = maxDmg (plus l'avg). SpiritLeech reste routé (RE de SA chaîne playbook #92, indépendant
  d'aiPredict) — re-vérification artefact-aware = #101. GAP restant : niveau/mult PER-ABILITY de la base spéciale
  (snapshot lvl50×180 vs natif maxDmg[65]×120) = **#100**.
- **GARDÉ de #96** : suppression du chemin mort 0.8/2.2 (`get_multi_hit_attack_prediction(damage=...)` /
  `predefined` / `shield_raw`) — le 2.2 n'existe pas dans le natif (RE PredictAttackRaw).

**#98 RÉSOLU BIT-EXACT** (port `[11940,17907]` == natif, u80 darkaTerminator→u78 seed777 r1 depuis (6,6) ;
tuiles déplacées `[5307,7959]` == natif) : le ×2.25 = **CrushingStrike(+50%) × ÉlévationBonus(+50%)**, composition
%-list **multiplicative sans arrondi intermédiaire**. Trois fixes moteur :
1. **CrushingStrikeEffect porté** (`entities/effects/loki.py`, effet 0x4a2=1186) : `ForPercentIncrease(
   OwnerIsCaster & IsNormalAttack & IsMeleeAttack, crushingStrikeExtraDmgPct=50)` @180f3ad90 (constante PLATE
   `GetNumberConstant` idx 0xf, non rarity-scalée) + ActiveCondition not-moved @180f3ad50. `is_normal_attack`
   threadé dans `create_effect_damage_bonus_for_attack` (le gate IsNormalAttack exclut les spéciales mêlée).
2. **Élévation RÉACTIVÉE en prédiction** (`_add_positional_and_defender_mods`) : le verdict #67 « pas d'élévation
   en préd » est **RÉFUTÉ PAR LECTURE** du builder `CalculateAttackerModifiersForPrediction @181000590`
   (read-L1161-1192) : l'élévation y est **INLINÉE** (gate `!HasEffect(0x423)` att+cible, `GetMainTile(cible)`,
   `tgt.elev < attackTile.elev` → +config.ElevationBonus) — AUCUN appel à la feuille @181003ea0, d'où le
   xref-check #67 aveugle. Évaluée à la **TUILE CANDIDATE** (mesuré : (6,6) elev2>1 ×1.5 ; (5,7) elev égale ×1.0
   exact). Le builder FIRE bien en prédiction (33×/tour de décision, compteur `attackerMods`) — le « misnomer
   ForPrediction » de #58 est aussi réfuté. Anomalies historiques u88/u90 (#67) à re-vérifier artefact-aware.
3. **`apply_capped_modifiers` : composition sans arrondi int intermédiaire** (`services/damage_modifiers.py`) :
   le natif compose les entrées %-list en Fix64 et ne matérialise l'int qu'une fois — round-par-entrée divergeait
   de ±1/coup dès 2 mults (bouts natifs `3980/5969` = `round(1769×2.25)/round(2653×2.25)` ; par-entrée donnait
   `3981/5970`). Mono-mult strictement inchangé (tous les cas validés préservés).

**MÉTHODE (harnais — reproduire pour tout écart de prédiction)** : (1) recon kit complet (`gameconfig.py <unit>`) ;
(2) lire le builder @181000590 (les gates) ; (3) `modifierObserveInstall` → `modifierObserveReset` →
`aiPlayByUnit` (tour de décision OBSERVÉ = la seule fenêtre fiable) → `modifierObserveStatus` : `multDumps`
(chaque multiplicateur composé, ×1000), `predCalcDumps` (in→out per-bout = le ×k par étage), `valueDumps`
(bouts post-perçage, ring 200), `varLevelDumps` (variables d'ability niveau×mult) ; (4) tuiles candidates
séparatrices ((6,6) not-moved+élévation vs (5,7) moved+plate) ; (5) `aiPredict {fresh:true}` + `queryClass`
pour dissiper les doutes de cache — en gardant à l'esprit que GetAllPredictions ≠ oracle playbook.

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
- **Cap Resilient (#56) — PORTÉ + VALIDÉ bit-exact (chemin réel, porte `IsOverkill` INCLUSE).** RE complète
  (`ApplyResilientTraitDamageLimit @18102c3a0` : cape à `curHP-1` si `HasTrait(0x3f1)` & `maxHP>1` & `curHP>0`
  & **PAS overkill**) + confirmation live (build gqfc5mff6c, attaquant single-hit `custoVexilusPraetor` vs cible
  `astraDreir` Resilient à PV forcés, hpmax injecté comme le vrai moteur) :
  - **Cap appliqué (over-kill MODÉRÉ)** : dmgMin 4658 < curHP (PV 4700/6000/6900) → non-létal → cap → natif ET
    port cappent à **PV-1** (4699/5999/6899) ; contrôle non-Resilient à **PV**. `scene.hpmax` doit être peuplé.
  - **Cap BYPASSÉ (over-kill MASSIF)** : PV=10 vs dmg ~6988 (~70000 %) → `IsOverkill` renvoie 1 → natif ET port
    donnent **10** (l'unité meurt). Avant la porte, le port donnait 9 (MISMATCH) ; APRÈS, bit-exact.
  - **Porte `IsOverkill` portée** : `compute_prediction_overkill` (`trait_damage_limits.py`) = mirror de
    `IsOverkill @181032db0` appelée par `ApplyTraitDamageLimitsToDamage @18102c650` — `accum = (maxHP-curHP)+
    dmgMin`, flag calculé UNE fois depuis la borne **min** et appliqué aux 2 bornes ; `cond=1/default=0/allow=0/
    global-override absent` (défauts bataille réelle, VERDICT RE agent). **Seuil = `gameconfig.overkillDmgPctOf
    Health` (=100)** = même global que le `is_overkill` death-riposte (FinalJustice) → dérivable offline, pas de
    hardcode (identité config-DI `comp@0x34` == overkillDmgPctOfHealth = HYPOTHÈSE forte, les deux valent 100 ;
    borné live à (33,101]). Wiring dans `predict_attack_raw` (`overkill=_ovk` aux 2 apply). `suppress` (flag
    BlockOverkill 0x13, `FuelledByFury_BlockOverkillEffect @180f4a7c0`) = no-op par défaut (dérivable via effets
    si roster Loki). ⚠ **Inerte dans le harnais de sonde `predict_samples`** (`scene.hpmax=None`→`max_health=0`),
    ACTIF dans le vrai moteur (`engine/ai/context.py::build` injecte `hpmax_by_id` via `observeBattle`).
- **`ApplyImperviousTraitDamageLimit`** (scaffold) : formule RE'd (charge < 1 OU < 100 -> dégât 0) mais
  charge Impervious non captée offline -> no-op.
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
