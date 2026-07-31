# case-366-r1 — `1345`/`1346 VisionsOfHeresy_ExtraPierce{Melee,Ranged}` : le canal PERÇAGE est une STAT

**Question, binaire.** Le port compte-t-il le perçage supplémentaire comme le natif, sur les DEUX
axes (mêlée ET distance) ? Mesuré dans un régime où le perçage MORD — cible à `--armor-target 6000`,
donc branche PERÇAGE dominante du plancher
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`.

**Réponse : OUI, sur les deux axes, après trois câblages.** Porteur `bloodDeathCompany` («Lucien»),
HERO **au pool** (`rl_duel build --list-pool` : 97 unités régulières, il y figure).

## 1. UNE classe native, DEUX `EffectType` — tranché par le SLOT

`probe_366_inventaire_effets_forme_b.py --csv` rend pour `1345` et `1346` **le même slot
`Il2CppClass*`** et le même `$$.ctor`
(`Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.VisionsOfHeresy_ExtraPierceEffect`), slot
**distinct** de celui de l'instance générique `IdunBattle.Entities.Effects.StaticStatModifierEffect`
(celui de `1171`/`1251`/`1256`, lot G1 de case-371). C'est donc une classe DÉDIÉE, qui dérive de
`StaticStatModifierEffect` (son `$$.ctor` l'appelle) et n'ajoute qu'une `CreateActiveCondition`.

Le discriminant mêlée/distance n'est PAS dans la classe : c'est le `statType` que passe le poseur.
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.VisionsOfHeresy_ExtraPierceAbility$$CreateBehaviour` :

    amount = ConfigVar(0x3f = extraPierceRatio, <abilityState>, <config>)
      AddStaticStatModifierEffect(Owner, 0x541 = 1345, statType 0x15 = 21 EXTRA_PIERCE_MELEE,
                                  amount, turns = NULL, isHidden)
    & AddStaticStatModifierEffect(Owner, 0x542 = 1346, statType 0x16 = 22 EXTRA_PIERCE_RANGED,
                                  amount, turns = NULL, isHidden)
    (combinés par `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd`)

`turns = NULL` ⇒ **PERMANENTS** : ce qui les éteint est la CONDITION, pas une durée. Le `$$.ctor` de
l'effet écrit `mov edx, 0x4f0` avant `AbilityOrEffect$$op_Implicit` ⇒ `EffectSource` = ability
**1264 `VisionsOfHeresy`** (passive, cf. `GC.unit("bloodDeathCompany").passiveAbilities`).

## 2. Le CANAL : une STAT, pas un `EffectBonus`

C'est le point qui commande tout le port — se tromper de canal donne un port qui a l'air juste et
reste INERTE. `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` (décompilé) :

    extra    = GetStat(attacker, 0x1a = 26 ExtraPierce)
    extraDir = GetStat(attacker, isMelee ? 0x15 = 21 : 0x16 = 22)
    base     = GetPiercingRatio(damageProfile, GetTraits(attacker))
    return Min(100, Max(base > 0, extraDir + extra + defMod + attMod + base))

⇒ ni `EffectBonus.ForPiercing` (canal de `GravitonRifle_ExtraPierce` / `Hailstrike_ExtraPierce`, qui
entre en `attackModifier`/`defenderModifier`), ni un groupe #179 : une **stat-modification** sur
21/22, posée/retirée par `AStatModifierEffect.ApplyModification`/`RevertModification`.

## 3. Active-condition — `HealthPct <= healthPct`

`...VisionsOfHeresy_ExtraPierceEffect$$CreateActiveCondition` = `HealthPctIsBelowOrEqual(Owner,
ConfigConst(0x4f = healthPct))`. La surcharge de `IdunBattle.Entities.Formulas.ConfigAmount$$.ctor`
est tranchée **par ses xrefs entrantes** : c'est celle qu'appelle
`IdunBattleLogic.Entities.DSLFormulas$$ConfigConst` ⇒ `0x4f` est un **AbilityConstantType**
(`constants["healthPct"] = 50`), pas une variable.
`IdunBattleLogic.Entities.DSLTriggers$$HealthPctIsBelowOrEqual` alloue un
`IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger` sur la stat **5 =
HEALTH** ; son `$$ShouldTrigger` compare `GetStat(5, part 0 CURRENT) / GetStat(5, part 2 MAXIMUM)
<= pct/100` en Fix64 — **inclusif**. Port : `100*hp <= pct*max` (entier exact).

**Deux confirmations indépendantes de `0x4f = healthPct`** : (a) le jumeau structurel déjà porté
`HammerOfWrath_ConditionalDamageEffect` (même helper, même constante, même comparaison) ;
(b) **élimination sur les QUATRE constantes** de `VisionsOfHeresy` — `damageProfile` = 4,
`range` = 0x16 et `nrOfHits` = 0x2f sont lus par `VisionsOfHeresy_AttackAbility$$SelectTarget` /
`$$GetAttackHits`, il ne reste que `healthPct`.

**Magnitude** : `ConfigVar(0x3f)` = `variables["extraPierceRatio"][level]` (65 niveaux, 10 → **20**
au niveau normalisé 50), indexée par le niveau de la **PASSIVE**. `extraPierceRatio` n'est **pas**
dans `variablesAffectedByRarityBonus` (qui ne contient que `minDmg`/`maxDmg`) ⇒ **aucun scaling de
rareté**. i2 : « If Lucien is at or below {healthPct}% Health, all of his attacks have
+{extraPierceRatio}% pierce ratio. »

## 4. Ce que le port a dû câbler — TROIS choses, dont une hors du fichier d'effet

1. **Les deux classes** (`entities/effects/loki/visions_of_heresy.py`) + leur inscription au
   registre `EFFECT_CLASSES`.
2. **Le SEED à l'init** — `ABILITY_INIT_OWNER_EFFECTS["VisionsOfHeresy"]`. Les deux effets sont
   ABSENTS de `decisionView.effects` tant que Lucien est au-dessus du seuil (canal ACTIF-ONLY,
   ground truth #100) : sans ce seed, le bonus n'apparaîtrait **jamais** dans un runner qui démarre
   Lucien à pleins PV. Même motif qu'`AnvilShield_BlockChanceBelowHealthCap` / `HammerOfWrath`.
3. **La LECTURE de la stat** — `ctx.extra_pierce`, `extra_pierce_melee`, `extra_pierce_ranged`
   étaient des **champs plats** figés à la capture. Le natif, lui, fait `GetStat(0x1a)` /
   `GetStat(0x15|0x16)` à chaque coup. Ce sont désormais des **propriétés adossées à
   `get_stat(Current)`**, comme les 8 stats de base. **Sans ce câblage le port est INERTE** : les
   deux classes seraient déclarées, le driver `refresh_stat_modifier_effects` poserait bien la
   stat-mod… et le perçage lu ne bougerait pas d'un point. Mesuré (mutation §6-b).
   Pendant : `clone_stats` de `spawn.py` cloné explicitement (le clone Decoy héritait des champs
   plats par `dataclasses.replace`).

## 5. Mesures live — deux couples (board, seed), deux axes

Montage : `probe_366_visions_of_heresy.py` (build 1v1, drive des DEUX camps, pilonnage de Lucien
sous le seuil par l'ennemi, captures, rejeux offline sur le MÊME flux MT).
`--armor-target 6000` + `--crit 0,0` + `--block-target 0,0` : une seule variable bouge.

| | mêlée `MC1_67`/31337 | distance `MC1_67`/31337 | mêlée `C4_09`/4242 | distance `C4_09`/4242 |
|---|---|---|---|---|
| E1 canal ACTIF à 100 % PV | absent | absent | absent | absent |
| E1 canal `includeInactive` | présent, `active: false` | idem | idem | idem |
| E2 stat native (haut → bas) | 0 → **20** | 0 → **20** | 0 → **20** | 0 → **20** |
| E2 port (haut → bas) | 0 → 20 | 0 → 20 | 0 → 20 | 0 → 20 |
| E2 **discriminant** (capture pleins PV, PV descendus OFFLINE) | **20** | **20** | **20** | **20** |
| E2 bascule inverse (« soin » offline) | **0** | **0** | **0** | **0** |
| ratio de perçage du port | 1 → 21 | 15 → 35 | 1 → 21 | 15 → 35 |
| E3 dégât live == port, régime HAUT | `[41,42,45]` | `[633,621,641]` | `[35,42,45]` | `[565]` |
| E3 dégât live == port, régime BAS | `[546,602,589]` | `[1060,888,860]` | `[720,726,586]` | `[1234]` |
| E3 contre-épreuve (BAS **sans** les effets) | `[35,34,35]` | `[463,371,476]` | `[34,30,24]` | `[512]` |

La contre-épreuve est ce qui rend la mesure opposable : sans elle, « port == live » ne prouverait
pas que le perçage y change quoi que ce soit. Sur `C4_09` le nombre de coups diffère (`DryBush` =
LightCover, −2 coups ranged) — le port suit, ce qui est exactement l'intérêt du second couple.

**Le seul régime discriminant est « l'effet s'ACTIVE APRÈS la capture ».** Capture prise sous le
seuil, la stat native est déjà dans `combatSnapshot` et un port à champ plat serait juste : c'est
pourquoi la ligne E2-discriminant part d'une capture à PLEINS PV, où le canal live ne livre RIEN.

## 6. Mutations adversariales — la garde est ROUGE quand on la casse

* **(a) inscription `EFFECT_CLASSES` retirée** → les deux `EffectType` retombent sur `BaseEffect`
  (donc `is_active → True`, aucun stat-mod) :
  `AssertionError: le port rend un effet ACTIF a 100.0% PV (seuil 50%)`, et
  `discriminant: 0`, `sans_effet == hits_port`. **2 failed** (les deux axes).
* **(b) propriétés de perçage remises en CHAMPS PLATS** (état d'avant ce cas) :
  `AssertionError: DISCRIMINANT : depuis une capture a pleins PV […] le port rend melee = 0, le
  natif mesure 20`, `assert 0 == 20`. **1 failed** — c'est la preuve que le câblage §4-3 est
  porteur, pas cosmétique.

## 7. Ce qui n'est PAS couvert

* **`VisionsOfHeresy_AttackAbility` n'est pas portée** (résidu NOMMÉ, hors périmètre de ce cas — ce
  n'est pas un `EffectType` du gisement des 96). RE faite :
  `$$CreateBehaviour` = `AttackWithAttackDamage(Owner, SelectTarget(...), MinMaxDamage,
  GetDamageProfileOrDefault(4) = Bolter, ConfigConst(0x2f = nrOfHits = 2), ...)` ;
  `$$SelectTarget` = `If(IsInAttackRange & IsAlive, <cible du trigger>,
  First(SortTargetsByDamagePredictionSelector(ValidNormalAttackTargets(Owner, ConfigConst(0x16 =
  range = 2))), 1))`. Elle est VISIBLE dans toutes les mesures ci-dessus : la queue live non portée
  (`[828,779]` puis `[1356,1220]` sur `MC1_67`) est ce second tir. Le montage l'isole par la
  cardinalité du groupe d'arme.
* **La face DÉCISION ne bascule pas.** `playbook/scene.py` construit ses `UnitContext` avec
  `effects=None` et ne joue pas `refresh_stat_modifier_effects` : elle LIT la stat 21/22 **captée**
  (donc juste à l'instant de la capture, comme avant), mais un Lucien qui passerait sous le seuil
  pendant la simulation ne verrait pas son perçage monter. Ces deux effets n'ont pas de
  `seed_witness_effect` utilisable : les DEUX volets portent la MÊME condition, il n'existe donc
  aucun frère inconditionnel pour servir de témoin.
* **Le régime `extraPierce` (stat 26)** n'est exercé par aucun de ces montages (il reste à 0 des
  deux côtés) ; sa conversion en propriété est couverte par les gardes perçage existantes
  (`test_offbyone_armor_38_live.py`, `test_hailstrike_phase2_live.py`,
  `test_damage_normal_armored_live.py`), re-jouées vertes.
* **Aucune mesure de l'expiration** : `turns = NULL`, il n'y a pas d'échéance à observer.

## 8. Artefacts

| quoi | où |
|---|---|
| classes d'effet | `scripts/python/engine/entities/effects/loki/visions_of_heresy.py` |
| registre + seed d'init | `scripts/python/engine/entities/effects/factory.py` |
| lecture de la stat (canal) | `scripts/python/engine/entities/unit_context.py` (3 propriétés), `runner/operations/spawn.py` (`clone_stats`) |
| montage live | `scripts/python/probe_366_visions_of_heresy.py` |
| gardes | `scripts/python/tests/engine/runner/test_visions_of_heresy_pierce_live.py` (4 : 2 axes × 2 couples) |
