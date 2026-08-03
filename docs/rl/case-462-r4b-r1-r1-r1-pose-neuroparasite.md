# #462-r4b-r1-r1-r1 — la POSE de `Neuroparasite`, et pourquoi une magnitude juste ne suffit pas

#462-r4b-r1-r1 (PR #553) a rendu la MAGNITUDE de l'additif défenseur de `Neuroparasite` exacte en
combat (port 4448 == natif 4448, bornes `(4392, 5461)`). Mais cette mesure n'a été possible que parce
que **le parasite venait du NATIF et que l'état était seedé**. En self-play 100 % porté il
n'apparaissait jamais, et tous les bras étaient au **niveau 1** — or l'additif est `× EffectLevel`.

Un effet dont la magnitude est juste mais que rien ne pose est un **canal mort** : aucun test ne
rougit, aucune erreur ne sort, et le moteur diverge silencieusement dès qu'il joue seul.

## 1. Les trois artefacts natifs (build `rnca9r7q6c`)

Slots `DSLSelectors` : `+0x30 Owner · +0x38 Effect · +0x40 Actor · +0x48 Caster · +0x60 Target`.
Slots `DSLFormulas` (lus dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor`) :
`+0x18 Direct(0) · +0x20 Direct(1) · +0x28 Direct(2) · +0x30 Direct(100) · +0x38 Direct(-1)`.

### a. La POSE — `IdunBattleLogic.Entities.Abilities.Triggered.Loki.NeuroparasiteAbility`

```
$$CreateTrigger   = On(9 = Attack, 1) & get_OwnerIsCaster
                    & NOT HasEffect(Target@0x60, 0x4c2, onlyActive: 0, 6)
                    & IsUnit(Target@0x60)
                    & CurrentAttackDamageProfilesContain(0xd = Psychic, 0)
                    & NOT (get_OwnerIsActor & get_OwnerIsTarget)

$$CreateBehaviour = AddBondEffect(0x4c2 = 1218,
                                  abilityState = get_AbilityStateReference(this),
                                  source       = Owner@0x30,
                                  targets      = Target@0x60,
                                  bondedEntity = Owner@0x30,
                                  options      = <struct 0x20 ZERO-initialisée>)
```

Les options sont un `Nullable` **vide** — `IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect` en
tire un `GetValueOrDefault` nul, donc aucune durée : `DefaultAmountOfRounds(0x4c2)` est absente ⇒
effet **PERMANENT** (`remaining = 0`).

### b. La MONTÉE — `IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect`

`$$CreateHandleTriggerAbilitiesInternal` ajoute **DEUX** `Triggered()` à l'`ArraySet` hérité
d'`IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal`, tous deux vers le
**même** behaviour :

```
Triggered( On(9)     & $$GetDamageTakenTrigger(),     $$GetIncreaseLevelBehaviour() )
Triggered( On(0x3d)  & $$GetPreEffectAddedTrigger(),  $$GetIncreaseLevelBehaviour() )

$$GetDamageTakenTrigger    = get_OwnerIsTarget & CurrentAttackDamageProfilesContain(0xd)
$$GetPreEffectAddedTrigger = get_OwnerIsTarget & TriggeringEffectIs(0x429 = 1065 Pinned)
$$GetIncreaseLevelBehaviour = IncreaseEffectLevel(Effect@0x38, Direct(1)@0x20, $$GetMaximumLevel())
```

⚠ **Le premier n'a AUCUN gate sur l'auteur du coup** : n'importe quelle attaque psychique subie par
la victime monte le parasite. C'est lu, pas simplifié — et c'est un écart assumé avec l'ADDITIF, qui
est bien gaté `AreEqual(BondedEntity, damageSource)`. Les deux faces du même effet ne portent pas les
mêmes conditions.

### c. Le CAP — `$$GetMaximumLevel`

```
Sum( ConfigVar(0x4c, GetAbilityState(effect), <config@effet+0x60>),
     If( ActorHasTriggeredAbility(ABondEffect$$BondedEntitySelector, 0x5d7),
         ConfigConst(0x5d7, ABondEffect$$BondedEntitySelector, 0x73),
         Direct(0)@0x18 ) )
```

Les deux clés sont qualifiées **par exclusion sur la config réellement servie**, pas sur le seul
gameconfig :

* `ConfigVar(0x4c, …)` vise la surcharge `(variableType, abilityState, config)`, donc la config de
  l'EFFET. `data/seed-bc.json` → `Abilities.PassiveAbilities.Neuroparasite.Variables` a **exactement
  deux entrées**, `extraDmg` (index 8, attesté bit-exact par #86 puis #553) et `buffMaxLevel` ⇒
  **`0x4c = buffMaxLevel`** (`[L50] = 15`). `Neuroparasite` est d'ailleurs la **seule** ability du BC
  à porter `buffMaxLevel` en VARIABLE — ailleurs c'est une CONSTANTE (`GetNumberConstant(0x62)`).
* `ConfigConst(0x5d7, unit, 0x73)` vise `(abilityType, unit, variableType)` : la config lue est celle
  de l'ability `0x5d7`. **`0x5d7 = 1495 = TriggeredAbilityType.NornCrown`** — à qualifier, car
  `EffectType.HunterOfSouls_ExtraDamage` vaut 1495 aussi ; le nœud est `ActorHasTriggeredAbility`,
  donc c'est bien le kit DÉCLENCHÉ. `gameconfig.NornCrown.constants` n'a **qu'une entrée**,
  `effectLevel = 1` ⇒ **`0x73 = effectLevel`**.

## 2. Le port

`scripts/python/engine/runner/operations/triggers/loki/neuroparasite.py` — trois classes, une par
`Triggered()` natif, inscrites dans `ABILITY_TRIGGERS["Neuroparasite"]` et `EFFECT_TRIGGERS[1218]`.

Frontière #149 : les `CreateTrigger` **collapsent** dans `matches` (doctrine `BarbedOvipositor` /
`SwornProtector`) ; les deux behaviours sont des **arbres DSL** rendus par des **usines**
(`neuroparasite_bond_tree`, `neuroparasite_increase_level_tree`, patron
`barbed_ovipositor_spawn_tree`).

**`AddBondEffect` gagne `scale_from_source`** = le **3e argument natif** `abilityState`, que la
factory transmet à `AddEffectBehaviour$$.ctor` : l'entité-effet BAKE l'état d'ability du poseur, et
c'est lui que relit `GetAbilityState(effect)` dans `GetMaximumLevel`. Le paramètre n'existait pas sur
cette feuille (seul son jumeau `AddEffect` l'avait) parce qu'aucun call-site porté n'en avait besoin.
Défaut `False` ⇒ les trois call-sites existants (`MalleusRocketLauncher`, `TunnelingHorror`,
`GetEmRuntz`) sont inchangés.

## 3. L'usine n'est pas une coquetterie : sans elle le garde ne pouvait pas rougir

La première écriture du garde offline faisait
`"scale_from_source=True" in inspect.getsource(execute_behaviour)`. La contre-épreuve
`True → False` est passée **au VERT** : le COMMENTAIRE voisin contenait la même chaîne, et
`getsource` ne distingue pas le code de sa prose. C'est le vice #439 — **trouvé par la mutation, pas
à l'œil**, et l'audit visuel de l'écriture initiale ne l'avait pas vu.

Extraire l'arbre en usine le rend **inspectable comme objet** : le garde lit `effect_type`,
`scale_from_source`, `duration_rounds`, les types des sélecteurs `source`/`bonded`/`target`, et
l'incrément `Direct(1)`. Il mord désormais.

## 4. Mesures (runner `MC1_67`, seed 112112, `probe_462_r4b_r1_r1_r1_neuroparasite_pose.py`)

| bras | ce qu'il sépare | port | natif |
|---|---|---|---|
| `pose` — attaque 1 PSYCHIQUE | l'existence même du parasite | **1** posé, `level 1`, `bonded = u79`, `remaining` permanent, `ability_level 50 × mult 180` | **1**, `level 1` |
| `pose` — attaque 2, niveau | `$$GetIncreaseLevelBehaviour` (`On(9)`) | 1 → **2**, cap calculé **15** | 1 → **2** |
| `pose` — attaque 2, dégât | non-régression de #553 | **4448** | **4448** |
| `melee` — CONTRÔLE NÉGATIF | le gate `CurrentAttackDamageProfilesContain(0xd)` | profil `Physical`, **0** posé | **0** posé |
| `pinned` — `On(0x3d)` | la SECONDE voie de montée | profil `Bolter`, 1 → **2** | 1 → **2** |

Le bras `pinned` est **discriminant** : `templAggressor` (trait `SuppressiveFire`) frappe la cible
parasitée avec une arme RANGED **non psychique**, donc le gate de l'autre trigger reste fermé. Un
port qui l'aurait oublié rendrait **3** au lieu de 2.

**BORNE, pas confirmation** : `Psychic` a `PiercingRatio = 100`, donc le plancher
`max(d × pierce%, d − armure)` est l'IDENTITÉ et l'axe PERÇAGE est **structurellement fermé** à ce
carrier, quelle que soit l'armure. Rien de mesuré ici ne dit quoi que ce soit du PLACEMENT de
l'additif — cet axe reste gardé par `test_462_r4b_r1_r1_defender_additive_carriers_live.py`, et par
lui seul.

## 5. Contre-épreuves (toutes vérifiées MORDANTES, arbre restauré)

| mutation | rouges |
|---|---|
| A — `ABILITY_TRIGGERS["Neuroparasite"]` désinscrit | **3** (POSE live, état baké live, cliquet offline) |
| B — `EFFECT_TRIGGERS[1218]` vidé | **3** (les deux voies de montée live, cliquet offline) |
| C — `scale_from_source=True → False` | **2** (état baké live, garde d'arbre offline) |
| D — gate profil retiré de `…OnPsychicHit` | **1** (bras `pinned` : 3 au lieu de 2) |

La mutation C est celle qui a démasqué le garde incapable de rougir (§3) : au premier jeu elle ne
rendait **qu'un** rouge, le live — le garde offline passait au vert.

## 6. Ce qui n'est PAS couvert

* **Les TROIS triggers de RETRAIT hérités d'`ABondEffect`** ne sont pas portés. Leur `ArraySet` les
  construit sous des VIRTUELS de la classe d'effet (slots de vtable `+0x748` bool, `+0x728`
  `Nullable<int>` de portée, `+0x738` bool d'adjacence) :

  ```
  (a) Triggered( NOT AmountIsZero(BondedEntity) & (On(2) | On(0x25))
                 & IsEntityWithIdTarget(BondedEntity),          RemoveEffect(Effect) )
  (b) Triggered( NOT IsInRange(Owner@0x30, BondedEntity, Direct(v)) & NOT AmountIsZero(…)
                 & On(0x1d),                                    RemoveEffect(Effect) )
  (c) Triggered( NOT IsAdjacent(Owner@0x30, BondedEntity, 3) & NOT AmountIsZero(…)
                 & On(0x1d),                                    RemoveEffect(Effect) )
  ```

  Aucun de ces virtuels n'apparaît sous `NeuroparasiteEffect$$*` dans les tables — **ce qui ne prouve
  rien** (corps triviaux dédupliqués : `xor eax,eax ; ret` pour un bool faux, un `Nullable` vide).
  Trancher exige de lire les slots de vtable sur l'instance. Conséquence offline : un parasite posé
  n'est jamais retiré. Sur les montages confrontés aucun des trois ne mord.
* **Le CAP ne mord pas** : il faudrait `buffMaxLevel` = 15 frappes qualifiantes. La VALEUR calculée
  (15) est assertionnée live ; le clamp lui-même est celui, déjà porté et testé, d'
  `IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute` (quirk `max < cur` inclus).
* **La branche `NornCrown`** de `$$GetMaximumLevel` n'est pas confrontable live (elle ne déplace le
  cap que d'un cran, et le cap ne mord pas) — gardée **offline uniquement**.
* **`ability_level` absent** ⇒ le port rend un cap `None` = « pas de cap ». Dégradation PERMISSIVE
  assumée et gardée offline.
* Les résidus de #462-r4b-r1-r1 restent ouverts tels quels : branche `IsOverwatchAttack` d'
  `ExemplarOfHate_Target`, bord `ability_level == 0`, régime `TimesEffectApplied > 1`.
