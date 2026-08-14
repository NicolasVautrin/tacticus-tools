# case-1077 — `FiringPosition` et `MischiefMakers` : deux `GAP-MENTION` dont les BASES étaient déjà portées

Deux passifs `S?=1 N=1` de `passive-ability-coverage.md`, section « GAPS non confrontables ».
`GAP-MENTION` ne voulait pas dire « à moitié porté » : **par exécution des sept registres, les deux
étaient ABSENTS partout**. La mention venait de trois docstrings et de membres d'enum — et d'un
faux positif qu'il fallait écarter (§1).

Effet sur l'audit régénéré : **PORTES 152 → 154**, **GAPS 46 → 44** (`GAP-MENTION` 19 → 17).

## 1. Ce qui existait déjà, PAR EXÉCUTION — et le faux positif d'ordinal

Balayage des sept registres de `triggers/dispatch/registry.py` + `TRIGGERED_ABILITY_BEHAVIOURS`,
`EFFECT_CLASSES`, `ABILITY_INIT_OWNER_EFFECTS`, `CUSTOM_NORMAL_ATTACK_BY_PASSIVE`,
`ABILITY_CLASSES` : **une seule « présence », et elle est FAUSSE**.

    ABILITY_CLASSES[1144] -> BioMinefieldAbility

`ABILITY_CLASSES` est indexé par `ActiveAbilityType`, où **1144 = `BioMinefield`** ; `1144` en
`TriggeredAbilityType` est `FiringPosition`. Les deux ordinaux sont valides, aucune erreur n'est
levée : c'est le piège d'enum, rencontré **avant même** d'avoir commencé le RE.

Ce qui existait vraiment, en revanche, c'est la **BASE NATIVE des deux** — et c'est tout le sujet :

| passif | classe native | base | état de la base côté port |
|---|---|---|---|
| `FiringPosition` (1144) | `...Triggered.Loki.FiringPositionAbility` | `AOwnerEffectTriggeredAbility` | portée (`ABILITY_INIT_OWNER_EFFECTS`, patron `InescapableDeath` #924) |
| son effet 1150 | `...Effects.Loki.FiringPosition_ReactivateOverwatchEffect` | `AReactivateOverwatchEffect` | **portée** (`AReactivateOverwatch` + `...HitReductionPurge`, #114/#924) |
| `MischiefMakers` (1471) | `...Triggered.Loki.MischiefMakersAbility` | `BaseTriggeredAbility` | — |
| son effet 1469 | `...Effects.Loki.MischiefMakersEffect` | `HealBlockingEffect` | **portée** (#927), et 1469 y était nommé **résidu ouvert** |

Les deux tranches se réduisent donc à des **sous-classes** + leur câblage. Le résidu nommé de #927
(« `MischiefMakersEffect` est le SECOND porteur de cette base, pas inscrit ») est **fermé ici**.

## 2. Les porteurs, ventilés — et la voie d'arrivée

| passif | summon | npc jumeau (`visualId`) | invocateur du summon | voie retenue |
|---|---|---|---|---|
| `FiringPosition` | `blackSmnHavoc` | `blackNpc4Havoc` | `EnvFactionSummons:EmperorsChildren` — ability d'**ENVIRONNEMENT** du live-event *Faction War* (`liveEvents.idunLiveEventConfigs[].factionWarData.factions[].abilityId`), portée par AUCUNE unité | **voie 2** → npc, `--explicit-stats blackNpc4Havoc:45` |
| `MischiefMakers` | `deathSmnNurglings` | `deathNpc3Nurglings` | `EnvFactionSummons:DeathGuard` — **n'apparaît NULLE PART** hors de sa propre définition et de `units.abilityPowerModifiers` : ni unité, ni live-event | **voie 3** → npc, `--explicit-stats deathNpc3Nurglings:45` |

Balayage **EXHAUSTIF** du gameconfig (toute chaîne de l'arbre, pas seulement `constants.unitId*`) :
c'est ce qui sépare « trouvé » de « conclu à tort à l'absence ». Les deux npc portent leurs
**45 paliers** `units.npc[].stats[]` ⇒ confrontables avec LEURS stats, LEURS traits, LEURS armes.
Le Havoc porte le trait `Overwatch`, donc l'effet 1009 — sans lui le passif serait inatteignable.

## 3. RE — ce qui ne se devine pas

### `FiringPosition` — la 3ᵉ sous-classe de `AReactivateOverwatchEffect`

`FiringPositionAbility` **ne déclare qu'UNE méthode** — son bloc `methodPointers` fait une entrée,
encadrée par `FinalVengeance_UnitEffect` avant et `UnityEngine...RequiredByNativeCodeAttribute`
après — `$$GetEffectType`, de corps entier `return 0x47e` (1150). Tout le reste vient de la base :
`CreateTrigger = OnOwnerSpecificAbilityInit(this@0x10)`, `CreateBehaviour = If(CreateCondition(),
AddEffect(GetEffectType(), AbilityState(Owner), source = Owner@<DSLSelectors+0x30>, targets =
Owner@<+0x30>, turns = <Nullable ZÉROÉ>))` → owner-effect **PERMANENT** posé à l'init.

⚠ **`FiringPosition_ReactivateOverwatchEffect$$GetHitReductionEffectType` N'EXISTE PAS comme
symbole**, et c'est l'ICF : son corps `mov eax,0x47f ; ret` est **fondu** avec
`...Loki.NeedsMoreDakka_PendingAttackEffect$$GetTriggeredAbilityType`, qui rend le même `0x47f` lu
en `TriggeredAbilityType` (= `NeedsMoreDakka_Attack`). La table, indexée par ADRESSE, n'en nomme
donc qu'UN propriétaire — et c'est l'autre. **L'appartenance vient du SLOT** : le corps a deux
xrefs DATA, dont l'une est l'entrée qui suit IMMÉDIATEMENT le `.ctor` de cette classe. L'entrée
d'après appartient à `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId` ⇒ le bloc fait
**exactement 2 entrées**, donc la classe **n'override NI `LegitDeathReasons` NI `HitReductionValue`
NI `GetOverwatchExtraDamage`**.

⚠ **L'overload du ctor de base est tranché par la CIBLE DU `jmp`, pas par l'ordinal** : la base en
déclare deux (`baseAbility:ActiveAbilityType` et `:TriggeredAbilityType`), et c'est le second qui
est appelé. Donc `0x478` = **1144 `TriggeredAbilityType.FiringPosition`** ; le lire en
`ActiveAbilityType` aurait nommé `BioMinefield` — le faux positif du §1, en miroir.

Conséquence portée : `LegitDeathReasons` = le corps de la BASE, **un seul terme**
(`HasDeathReason(dying, Ability, 1009)`), là où la sœur 1145 en a deux. Recopier le voisin de forme
aurait ré-armé l'overwatch sur des morts que le natif refuse. Et `HitReductionValue()` lit
`GetNumberConstant(config, 0x2c = hitsReduction)` sur la config de `FiringPosition` ⇒ **2**
(i2 : « retaining 2 fewer hits »), là où ses deux sœurs valent 1.

### `MischiefMakers` — un bloqueur de soin inconditionnel + un tirage

    $$CreateTrigger  = On(Attack = 9, ownerNeedsToBeAlive) & get_OwnerIsActor & IsNormalAttack

    $$CreateBehaviour = op_BitwiseAnd(
        AddEffect_TURNS  (1469 MischiefMakers, AbilityStateReference,
                          source = Owner@<DSLSelectors+0x30>, targets = Target@<+0x60>,
                          turns = TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds))),
        Maybe( AddEffect_OPTIONS(1065 Pinned, AbilityStateReference, mêmes sélecteurs,
                                 options = <struct ZÉROÉE 0x20>),
               Get(GetNumberConstant(0x2a = chance)) ) )

⚠ **LES DEUX `AddEffect` DU MÊME CORPS SONT DEUX SURCHARGES DIFFÉRENTES**, et le pseudo-C les
affiche à l'identique. Tranché par les **xrefs entrantes**, jamais par la forme :

* `...MischiefMakersAbility$$CreateBehaviour+0xdd` → `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect`
  surcharge `(effectType, abilityState, source, targets, **options**)` — la pose de `Pinned` ;
* `...MischiefMakersAbility$$CreateBehaviour+0x178` → `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect`
  surcharge `(effectType, abilityState, source, targets, **turns**)` — la pose de `MischiefMakers`.

Les confondre aurait passé le `Nullable` de 32 octets zéros en `turns` (une durée NULLE explicite)
au lieu d'`options`, et inversement jeté le `TurnsFromRounds`. Les deux corps ont été relus : celui
à `turns` construit un `Nullable<>` AUTOUR du pointeur reçu, celui à `options` RECOPIE 0x20 octets
depuis l'adresse.

⚠ **L'ORDRE D'EXÉCUTION est l'INVERSE de l'ordre de CONSTRUCTION** : le pseudo-C construit
l'`AddEffect(Pinned)` en premier, mais l'`op_BitwiseAnd` final reçoit `(AddEffect(1469), Maybe(…))`
et `CombinedBehaviour$$Execute` va gauche puis droite. Contrairement à `BeastSnagga` (#1015-r1) et
`MonsterSlayerOfCaliban` (#1009), **ce n'est pas inerte ici** : le `Maybe` consomme un `next_bool`.

⚠ **Le blocage de soin n'est PAS sous le `Maybe`** — seul le `Pinned` est tiré (25 %).

## 4. La cause racine trouvée en route : le vecteur `On(9)` ne portait AUCUN canal de nature

Le port était muet **avant même** `matches` ? Non : la décomposition par étage a montré la classe
bien MONTÉE sur l'unité (`collect_triggered_abilities`), donc l'échec était plus bas. Le seul
appelant de `finish_attack_triggers` (`damage_ops/normal.py`) **ne threadait aucun canal de nature
d'attaque** : le gate `IsNormalAttack` ne pouvait jamais être satisfait, et le passif restait muet
offline — **sans erreur, sans test rouge**.

**Le canal posé est le BOOLÉEN `is_normal_attack`, PAS l'ordinal `ability_type`**, et ce choix est
mesuré, pas esthétique :

| canal | rayon de souffle sur les **34** consommateurs de `On(9)` | effet |
|---|---|---|
| `ability_type = 1013` | **7** le lisent | casse `LordOfTempestsAddIceAbility` (qui gate *exactement* `kind == 1013`) et `VitarusAbility` (dont `_current_ability_is_accepted` code `None` comme PROXY de « voie normale ») |
| `is_normal_attack = True` | **1** le lit — `MischiefMakersAbility` | aucun autre effet |

La docstring de `finish_attack_triggers` documentait déjà pourquoi `ability_type` reste `None` ici.
Le booléen est le même fait natif (`IsNormalAttack(CurrentAbility@DSLSelectors+0x88)`), au même
littéral que le `is_normal_attack=True` déjà passé à `attack_damage_attack_triggers` — les deux
events sortent du **même** `FinishAttackOperation$$Execute`.

## 5. Confrontation live (`probe_1077_firing_position_mischief_makers.py`)

**`MischiefMakers`** — `deathNpc3Nurglings:45` attaque `orksNob` :

| observable | live | port AVEC | port SANS l'ability | port SANS la classe d'effet |
|---|---|---|---|---|
| effet 1469 posé sur la cible | oui | oui | **non** | oui |
| `has_heal_blockers(cible)` | — | **True** | False | **False** |
| `mti` du MT19937 après | **7** | **7** | **6** | 7 |

Les **trois** régimes séparent, et la mutation du registre `EFFECT_CLASSES` isole à elle seule
l'inscription : l'effet est POSÉ mais matérialisé en `BaseEffect` nu ⇒ la cible reste **soignable**,
la dégradation permissive exacte que #927 avait nommée.

⚠ **Le témoin PRNG est ce qui rend la mesure non dégénérée** : le tirage à 25 % **n'est pas tombé**
sur ce montage. Sans le `mti`, un port ayant purement OUBLIÉ le `Maybe` serait vert 3 fois sur 4.
`7` avec l'ability contre `6` sans ⇒ **exactement un `next_bool`**, au bon rang.

**`FiringPosition`** — `blackNpc4Havoc:45` (placé en (3,3)) ; une victime à 1 PV en (3,6) entre
dans son rayon :

| observable | live | port AVEC | port SANS (mutation `EFFECT_TRIGGERS.pop(1150)`) |
|---|---|---|---|
| effets du porteur à l'INIT | `1008, 1009, 1150, 1477` | idem (capture) | idem |
| PV de la victime | 1 → **0** | 1 → **0** | 1 → 0 |
| effets du porteur après le kill | `…, 1150, **1151**, …` | **idem** | pas de 1151 |
| reste en overwatch (1009) | oui | oui | oui |
| `EXTRA_HITS` | — | **−2** | 0 |

**Le `−2` est le discriminant** : les deux classes sœurs déjà portées valent −1 (1146 pour
`EarlyWarningOverride`, 1019 pour `InescapableDeath`). Un port recopié du voisin aurait rendu −1.

### Trois pièges de MONTAGE, tous mesurés

* `--hp-target` vise les **a-units** (donc le Havoc), pas la victime → `--hp-player`/`--unit-stat` ;
* aux SpawnPoints les deux unités sont à **7** hexes : la victime ne peut pas entrer dans le rayon
  (Range 2) en un tour, et le scénario ne se produit **jamais** → géométrie PILOTÉE (`--place` /
  `--a-place`), jamais subie ;
* avec **un seul** p-unit, son kill vide le camp, la bataille se termine et `decisionView` ne rend
  plus le porteur (`hav2 is None`) → une seconde unité, posée loin et intacte.

### Une faute d'instrumentation du probe, corrigée

`get_component` rend le **même objet** avant et après : `hc0.hp` relu dans le `return` valait déjà
le hp d'APRÈS, et le probe affichait `hp_victime = [0, 0]` sur un montage où le natif publie 1 puis
0 — un faux « la victime était déjà morte », donc un scénario qu'on aurait cru vide. **Capturer la
VALEUR, pas la référence.**

## 6. Le test de garde a été validé PAR MUTATION — et il portait DEUX faux verts

`test_1077_…_offline.py` (11 tests) a été soumis à **9 mutations**. Trois ne le faisaient pas
rougir ; deux étaient de vrais trous du test :

* `SOURCE_ABILITY` basculé sur celui d'une sœur restait VERT — le test n'exerçait que la
  **fonction** `_hit_reduction_value("FiringPosition")`, jamais l'attribut de la CLASSE ;
* le canal `is_normal_attack` mis à `None` restait VERT — le test cherchait la chaîne
  `is_normal_attack=True` dans la fenêtre du site d'appel, **et le commentaire qui documente ce
  site cite ce même littéral**. C'est « un catalogue n'est pas un câblage » retourné contre un
  test. Réparé **par AST** (nœud `Call` + ses `keywords`), la seule lecture qui ignore la prose.

Après réparation : **9/9 mutations rougissent**.

## 7. Résidus

* **`#1077-r1`** — le SECOND site d'émission de `On(9)` (`after_hit_ability_attack`, voie
  ability/splash) ne thread pas `is_normal_attack` : il reste à `None`, donc `MischiefMakers` s'y
  TAIT (tri-état restrictif, nommé). Correct aujourd'hui — cette voie n'est pas l'attaque normale —
  mais son commentaire parle d'une voie « normal-like » que la tranche n'a pas qualifiée. Si une
  attaque normale y passait, le passif s'y tairait à tort. Poser `False` en dur y serait une
  affirmation non mesurée ; c'est la qualification des appelants qui manque.
* **`#1077-r2`** — le `Pinned` (1065) de `MischiefMakers` n'a **pas** été confronté dans un régime
  où le tirage TOMBE : `chance = 25`, et il n'est pas tombé sur le montage joué. L'accord `mti`
  (7 vs 6) établit que le tirage est consommé, au bon rang et en un seul exemplaire ; la POSE de
  `Pinned` elle-même, sa durée (`options` ZÉROÉES → `DefaultAmountOfRounds`) et son interaction
  avec l'immunité restent NON OBSERVÉES live.
