# #1015-r1 — `BeastSnagga` porté, et `TwoManTeam` reclassé : deux « non couverts » qui n'étaient pas le même problème

Build `rnca9r7q6c`. Les deux derniers traits de `NON_COUVERTS_MESURES` hors `Healer`. Ils sortaient
du recenseur par le même symptôme — `trait_channels.canaux(t) == []` — et il a fallu deux verdicts
opposés : l'un était un **port manquant**, l'autre un **verdict terminal**.

---

## 1. `BeastSnagga` — un port manquant, et le mirror le disait déjà

`EffectType.BeastSnagga_ExtraDmg` (1080) et `BeastSnagga_ExtraBlock` (1081) existaient dans le
mirror **sans aucune classe derrière** : le port nommait la donnée sans exécuter la mécanique.
Même signature que `InstinctiveBehaviour_BlockMovement` la veille.

### 1.1 La chaîne native, LUE

```
UnitTrait.BeastSnagga = 0x406 = 1030
  -> StaticBattleRules.Trait$$.cctor, dict statique +0x00 : cle 0x406 -> valeur 0x43c
  -> AddTraitOperation$$AddDerivedAbilities monte TriggeredAbilityType.BeastSnagga = 0x43c = 1084

IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSnaggaAbility
  $$CreateTrigger   = DSLTriggers.OnOwnerSpecificAbilityInit( 0x43c )
  $$CreateBehaviour =
      blockChance = GetNumberConstant( AbilityConstantType.blockChance = 0x2d )
      blockDmgPct = GetNumberConstant( AbilityConstantType.blockDmgPct = 0x36 )
      extraBlock  = AddExtraBlockEffectToOwner(
                        0x439 = 1081,
                        blockChance : Direct( blockChance ),
                        blockDamage : PercentageOf( StatAmount(Owner@<DSLSelectors+0x30>,
                                                               statType 0x5 = Health,
                                                               statPart 0x2 = Maximum),
                                                    Direct( blockDmgPct ) ),
                        turns       : null )
      extraDmg    = AddEffect( 0x438 = 1080, AbilityStateReference,
                               targets = Owner@<DSLSelectors+0x30>, turns = null )
      return op_BitwiseAnd( extraDmg, extraBlock )     // execution : extraDmg PUIS extraBlock

IdunBattle.Entities.Effects.Loki.BeastSnagga_ExtraDmgEffect
  $$.ctor                = DamageModifierAbilityEffect..ctor( this, 0x43c, 0 )
  $$CreateDamageModifier = ForPercentIncrease(
        get_OwnerIsCaster & IsMeleeAttack
      & ( HasTrait(Target@<DSLSelectors+0x60>, 0x405 = Vehicle)
        | HasTrait(Target@<DSLSelectors+0x60>, 0x3f9 = BigTarget) ),
        ConfigConst( AbilityConstantType.extraDmgPct = 0xf, config@this+0x60 ) )
```

⚠ **`$$CreateDamageModifier` est IDENTIQUE, instruction pour instruction, à celui de
`BeastSlayer_ExtraDmgEffect`** (seul écart : le drapeau d'init de classe). Ce n'est donc pas « le
voisin de forme » — c'est le même artefact, lu des deux côtés. `BeastSnagga_ExtraBlock`, lui,
**diverge** : `StatAmount(Health, Maximum)` là où `BeastSlayerAbility$$GetBlockDamage` lit
`StatAmount(0x10 = FixedArmor)`.

⚠ **`0x406` apparaît DEUX fois dans le même dict, une fois de chaque côté** : comme clé
(`BeastSnagga -> 1084`) et comme **valeur** de la clé `0x3f9` (`BigTarget -> TriggeredAbilityType`
1030). Deux enums, même ordinal : `Trait$$GetTraitForTriggeredAbility(0x406)` rend **`BigTarget`**.

### 1.2 La source des valeurs, et pourquoi l'ordinal ne suffit pas

`GC.ability("BeastSnagga")` rend `null` — l'ability n'est pas dans `units.abilities`. La config que
lit `ConfigConst` est synthétisée depuis `globalValues.traitVariables`, et la BC la publie :

| `AbilityConstantType` | `BC.Abilities.PassiveAbilities.BeastSnagga.Constants` | `globalValues.traitVariables` |
|---|---|---|
| `extraDmgPct` (0xf)  | 20 | `beastSnaggaDmgBonus` = 20 |
| `blockChance` (0x2d) | 10 | `beastSnaggaBlockChance` = 10 |
| `blockDmgPct` (0x36) | 20 | `beastSnaggaDmgAsMaxHpPct` = 20 |

⚠ **`extraDmgPct` et `blockDmgPct` valent TOUS DEUX 20** : la valeur ne discrimine pas. Ce qui
tranche est le **nom** (`DmgBonus` vs `DmgAsMaxHpPct`) et l'**arbre** (le second est l'argument du
`PercentageOf(StatAmount(Health, Maximum))`). Chez `BeastSlayer` les deux diffèrent (20 / 100) et
l'inversion se serait vue ; ici elle serait **silencieuse** sur l'axe dégât.

### 1.3 Le port

* `BeastSnaggaExtraDmgEffect` — `engine/entities/effects/loki/extra_damage.py`
* `BeastSnaggaExtraBlockEffect` — `engine/entities/effects/loki/hits.py`
* `factory.TRAIT_DERIVED_ABILITIES["BeastSnagga"] = ["BeastSnagga"]`
* `factory.ABILITY_INIT_OWNER_EFFECTS["BeastSnagga"] = ["BeastSnagga_ExtraDmg", "BeastSnagga_ExtraBlock"]`
  (ordre d'**exécution**, l'inverse de l'ordre de construction du pseudo-C)

**Un TROISIÈME substrat entre au hook de block.** `create_effect_block_source_for_defense` portait
`defender_fixed_armor` (#72, BeastSlayer) et `defender_attack` (#221, Daemon) ; il porte désormais
`defender_max_health` = `GetStat(cible, Health = 5, StatPart.Maximum = 2)`. Threadé sur les deux
faces : combat (`_block_sources`, appelé par `normal` / `normal_like` / `ability`) et prédiction
(`playbook/prediction/_shared`, via `scene.hpmax` = `combatSnapshot.healthMax`, qui **est**
`GetStat(e, 5, 2)`). Non threadé ⇒ la source rend `None` — jamais un amount deviné : la faire
disparaître ferait sauter un jet de block que le natif roule, et désynchroniserait tout le RNG aval
(signature exacte du trou #221).

### 1.4 Confrontation live — `probe_1015r1_beast_snagga.py`

Deux runners, `MC1_67` / seed 777, mêmes unités et mêmes stats ; seul écart : le trait du porteur.
Le porteur du kit (`tauNpcFarsight`, npc) est hors pool ⇒ **greffe** sur `astraBullgryn` (héros du
pool, arme mêlée unique) — légitime au sens de `case-92` §5bis : l'effet ne lit **ni les stats ni
les traits du caster**.

| cran | AVEC trait | SANS trait |
|---|---|---|
| 1. kit (`unitAbilityStates`) | `[1028, 1030, 1084]` | `[1028, 1030]` |
| 2. effets (`decisionView.effects`) | `[1025, 1026, 1080, 1081]` | `[1025, 1026]` |
| 3. natif vs `astraCreed` (BigTarget) | `(4324, 9037)` | `(3604, 8420)` → **×1,1998** |
| 3'. natif vs `adeptCanoness` (ni l'un ni l'autre) | `(5204, 8533)` | `(5204, 8533)` → **inchangé** |
| 4. port | **égal au natif sur les 8 mesures** (4 couples × 2 régimes) | |

**Le second témoin est le vrai discriminant.** Le gate natif n'est pas « le porteur a le trait »
mais `HasTrait(CIBLE, …)` : sans la cible non-`BigTarget`, on mesurerait « le trait fait quelque
chose », pas « il fait *ce* quelque chose-là ».

⚠ **Le clamp aux PV rend un ratio indécidable, et le taire fabrique un faux ÉCHEC.** Premier run :
borne haute 8420 → 9037 (= les PV d'`astraCreed`), soit un ratio apparent de **1,0733** alors que
le bonus est bien de +20 % (borne basse : 3604 → 4324). Le probe **écarte** une borne clampée **en
le disant**, plutôt que d'élargir la tolérance.

### 1.5 Généralisation — quatre montages, 32 mesures

| # | montage | résultat |
|---|---|---|
| 1 | `MC1_67` / 777 / cible `BigTarget` | ×1,1998 (borne min ; max clampée) |
| 2 | `MC1_67` / 777 / cible **`Vehicle`** | identique — la **seconde** branche du `op_BitwiseOr` |
| 3 | **`C1_74`** / 31337 / `BigTarget` | 6 couples, même résultat : le verdict ne tient pas à la géométrie d'UN board |
| 4 | `MC1_67` / 777 / `--hp-cible 60000` | **les deux bornes décidables** : 12032 → 14440 (×1,20016) et 16848 → 20216 (×1,19990) |

Le port rend **exactement** le natif sur les 32 mesures, dans les deux régimes.

⚠ **GARDE DE MORSURE (étage 0), et elle vient d'une faute réelle.** Le premier `--hp-cible` passait
par `--unit-stat <vis>:Health=<n>` : le build **imprime** `Health=60000`, la BC le **porte** — et
les PV en bataille **ne bougent pas** (9037). Le probe rendait alors `VERDICT : OK` sur un montage
qui n'avait pas mordu. Le levier qui mord est `--hp-target` ; l'étage 0 **constate** désormais les
PV mesurés et **refuse de conclure** s'ils n'atteignent pas la valeur demandée.

**Non couvert** : la **valeur** du block (`BeastSnagga_ExtraBlock`) n'est confrontée qu'en **pose**.
Elle n'entre ni dans `dmgMin/dmgMax` (le block est un scénario séparé,
`DamagePredictionResult` list[0]@0x50) ni dans le scalaire `GetStat(7/8)` — par construction,
puisque c'est une entrée de `GetMultiValueStat(7)`. Résidu `#1015-r5`.

---

## 2. `TwoManTeam` — le natif ne lit jamais ce trait, et c'est une MESURE

Trois lectures indépendantes sur `rnca9r7q6c` :

| # | lecture | résultat |
|---|---|---|
| a | symboles portant le nom, sur les 154 177 fonctions de `ghidra/functions.tsv` | **0** (`BeastSnagga` en a 4, `BeastSlayer` 11, `CloseCombatWeakness` 18) |
| b | clés des **8** conteneurs statiques de `StaticBattleRules.Trait$$.cctor` | `0x3fa` **absente** — elle n'y est qu'en **valeur** de la clé `0x3ef`, où elle désigne une `TriggeredAbilityType` 1018 |
| c | arguments de `HasTrait` | ni `0x3fa` ni `1018` : les 12 fonctions portant `0x3fa` et les 25 portant `1018` sont des flottants, de l'UI/meta et les deux `.cctor` |

Ce que le tooltip décrit — « max 50 % des PV max d'un seul coup, hors Blast ; sous 50 %, plus
soignable au-dessus » — **est porté**, mais keyé sur `nrOfMembers` (les 6 porteurs sont tous à
`nrOfMembers == 2`) :

* cap par coup — `services/trait_damage_limits.apply_group_unit_damage_limit`, câblé par
  `damage._target_limits` (voie ATTAQUE, `member_count = nrOfMembers`), par
  `damage_ops/normal_like` (dégât DIRECT) et par `transfer_damage` ;
* plafond de soin — `get_group_unit_heal_limit`, câblé par `operations/heal.py`,
  `operations/repair.py` et `ai/action_generators.py`.

⇒ **Le trait n'a pas de canal, et c'est correct.** Le retirer de `NON_COUVERTS_MESURES`
demanderait au port de *nommer* un trait que le natif ne lit pas — une `lecture` fabriquée,
c'est-à-dire le faux positif exact que `trait_channels` existe pour éviter.

### 2.1 Le troisième état, et son cran

`NON_COUVERTS_MESURES` mélangeait « le port ne sait pas encore l'évaluer » (un **port à faire**) et
« il n'y a rien à évaluer » (un **verdict terminal**). Rien ne les distinguait, donc le résidu
restait ouvert sur le second sans que personne puisse le fermer.

`SANS_ARTEFACT_NATIF` (sous-ensemble de `NON_COUVERTS_MESURES`) porte le verdict, avec l'étage 6 de
`test_1015_trait_channels_offline.py` — **exécutable et offline**, contre la table Ghidra
versionnée. Il ne démontre pas le verdict : il en garde la **péremption**. Un `TwoManTeamAbility`
au prochain build le fait rougir, et les trois lectures se re-instruisent.

⚠ Il s'assertionne contre sa propre vacuité (un chemin de table cassé ferait rendre `0` à tout le
monde) : le contre-témoin est `BeastSnagga`, dont ce même travail a mesuré les 4 symboles.
Contre-épreuve jouée dans les deux sens — `BeastSlayer` dans l'ensemble le fait rougir, un ensemble
vide aussi.

⚠ **L'absence de symbole homonyme ne prouve pas l'absence de lecture** (IL2CPP déduplique les corps
triviaux, cf. CLAUDE.md ; `Diminutive` n'a pas de symbole et passe par le dict trait → ability).
C'est pourquoi (a) seul ne suffit pas, et pourquoi (b) et (c) sont citées ici.

---

## 3. Le gisement que la tranche a ouvert — et refermé

Ajouter un paramètre au hook de block **casse tout site qui le redéfinit ou le substitue**. Trois
l'étaient : `tests/engine/runner/test_daemon_extra_block_live.py` (`TypeError`, **vu par la
banque**) et **deux probes** — `probe_221_daemon_normal_attack.py`,
`probe_brazier_daemon_offset.py` — que la banque ne joue pas, où la faute aurait dormi jusqu'au
prochain run manuel.

Les trois stubs **recopient** le paramètre plutôt que d'absorber par `**_` : un `**kwargs`
passerait tous les contrôles et serait **pire**, puisqu'il masquerait la disparition d'un substrat
côté agrégateur.

Cran : étage 7 de `tests/engine/test_1015r1_beast_snagga_offline.py` — balayage de **tout**
`scripts/python/**` (périmètre **dérivé**, pas de liste blanche), les trois substrats exigés
**nommés** à chaque site, et une assertion de non-vacuité (≥ 8 sites). Contre-épreuve jouée :
remettre un seul site à l'ancienne signature le fait rougir en le **nommant**.

---

## 4. Ce qui n'est PAS couvert

* la **valeur** du block `BeastSnagga_ExtraBlock` en live (pose seule confrontée) — `#1015-r5` ;
* la face **combat** du bonus de dégât : le probe confronte la **prédiction** native
  (`attackPlans.ranked`), pas un coup résolu. Le port passe par le même
  `create_effect_damage_bonus_for_attack` sur les deux faces, et la limite `target_traits` sur le
  chemin d'attaque d'**ability** est celle, partagée, de `BeastSlayer`/`MartialKatah`/
  `CondemnorStake` (`runner/operations/damage.py`) — pas propre à ce port ;
* `Healer`, dernier membre de `NON_COUVERTS_MESURES` avec `TwoManTeam` — tranche séparée.
