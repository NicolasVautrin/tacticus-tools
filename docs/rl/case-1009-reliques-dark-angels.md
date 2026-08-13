# #1009 — reliques DARK ANGELS : `MonsterSlayerOfCaliban` (1527) et `RelicPowerFist` (1466)

Couple de reliques de la voie `item`, deux porteurs du MÊME roster (`darkaCompanion` « Forcas »,
`darkaTerminator` « Baraqiel », tous deux Dark Angels et HERO du pool rank 17) : **un seul
montage** (`rl_duel build --equip-relic`, état 2 des trois états d'une relique, #237). Les deux ids
sont des `TriggeredAbilityType` — aucune n'entre dans `ABILITY_CLASSES`, aucune ne pose de
`TARGETING_OPTIONS` ni d'`ABILITY_ATTACK_TYPE`.

Build de lecture : `rnca9r7q6c`.

⚠ **`RelicPowerFist` TRAVERSE TROIS FACTIONS** — `allowedUnits = [templAggressor,
bloodIntercessor, darkaTerminator]`. Cette tranche la confronte sur `darkaTerminator` seulement ;
les deux autres porteurs sont **NON CONFRONTÉS** (résidu `#1009-r2`).

## 1. Les artefacts natifs, et le canal de chacun

| classe native | canal de port |
|---|---|
| `Triggered.Loki.MonsterSlayerofCalibanAbility` | **`ABILITY_INIT_OWNER_EFFECTS["MonsterSlayerOfCaliban"]`** |
| `Effects.Loki.MonsterSlayerofCaliban_ExtraDmgEffect` (1539) | `EFFECT_CLASSES["MonsterSlayerOfCaliban_ExtraDmg"]` |
| *(aucune classe native pour 1540)* | `EFFECT_CLASSES["MonsterSlayerOfCaliban_ExtraBlock"]` |
| `Triggered.Loki.RelicPowerFistAbility` | `RELIC_ABILITY_TRIGGERS["RelicPowerFist"]` |

**UNE seule classe native par clé** — contraste `DaemonfleshPlate` / `Lakrimae` / `ChaliceOfBaal`,
qui en portent deux. Et le nom natif écrit `MonsterSlayer**o**f` (o minuscule) là où l'`EffectType`
écrit `MonsterSlayer**O**f` : la voie NOM de `probe_437r1r1r1_effect_face_table.py` échoue par
construction sur ce couple, c'est la citation VERBATIM du symbole dans la classe du port qui
l'apparie.

## 2. `MonsterSlayerOfCaliban` — deux effets posés à l'init, un seul `&`

    $$CreateTrigger  = OnOwnerSpecificAbilityInit( 0x5f7 = 1527 )

    $$CreateBehaviour =
        extraBlock = AddExtraBlockEffectToOwner( 1540,
                         blockChance : Direct(GetVariableForLevel(0x15 = blockChance)),
                         blockDamage : Direct(GetVariableForLevel(0x14 = blockDmg)),
                         turns       : null )
        extraDmg   = AddEffect( 1539, AbilityStateReference,
                                targets = Owner@<DSLSelectors+0x30>, turns : Nullable<int>(null) )
        return op_BitwiseAnd( extraDmg, extraBlock )

    ...MonsterSlayerofCaliban_ExtraDmgEffect$$CreateDamageModifier =
        EffectBonus.ForAddition(
            get_OwnerIsCaster
          & ( HasTrait(Target@<+0x60>, UnitTrait.Vehicle = 0x405)
            | HasTrait(Target@<+0x60>, UnitTrait.BigTarget = 0x3f9) ),
            ConfigVar( AbilityVariableType.extraDmg = 8, GetAbilityState(this), config@this+0x60 ) )

⚠ **L'ORDRE D'EXÉCUTION EST L'INVERSE DE L'ORDRE DE CONSTRUCTION.** Le natif CONSTRUIT
`AddExtraBlockEffectToOwner` d'abord (registre `pvVar6`), puis `AddEffect`, et ne les compose qu'au
`op_BitwiseAnd(AddEffect, AddExtraBlock)` final — or `CombinedBehaviour` exécute GAUCHE puis
DROITE. Lire l'ordre du pseudo-C au lieu de celui des arguments du `&` est exactement la faute que
`VolummsMasterArtifice` a payée (#1001). Ici les deux poses sont idempotentes, donc **sans
observable** ; l'ordre est écrit parce qu'il est LU, et gardé par le cliquet offline.

⚠ **LA SURCHARGE D'`AddExtraBlockEffectToOwner` EST `(effectType, blockChance, blockDamage,
turns)`** (`frida/methods.tsv`, paramètres NOMMÉS). Les deux variables sont VOISINES dans l'enum
(`0x14 blockDmg`, `0x15 blockChance`) et les inverser donnerait « 10 points de dégât bloqués avec
1470 % de chance » — silencieux côté port, les deux champs étant des `int`.

⚠ **NE PAS RECOPIER `BeastSlayer_ExtraDmgEffect`**, qui porte la MÊME paire de traits cible : il a
un `IsMeleeAttack` et rend un `ForPercentIncrease`. Celui-ci n'a **aucun** gate de nature (ni
mêlée, ni normale) et rend un `ForAddition`. Recopier le voisin aurait éteint deux régimes ET
changé le canal d'accumulation.

`1540` n'a **aucune classe d'effet dédiée** dans le build (`frida/classes.tsv`) : c'est le
`MultiValueStatEntryEffect` générique d'`AddExtraBlockEffectToOwner`, dont les deux valeurs sont
figées à la pose. Le port suit le patron `PsychicFortressExtraBlockEffect` / `BeastSlayerExtraBlock
Effect` — une classe qui RELIT la config au niveau de l'`AbilityState`. Les deux arguments natifs
étant des `Direct(<config>)`, la source ne lit **aucune stat du défenseur** (contraste
`BeastSlayer` : `PercentageOf(FixedArmor)` ; `Daemon` : `PercentageOf(Attack)`).

## 3. `RelicPowerFist` — deux `Maybe`, deux tirages, et un doublement

    $$CreateTrigger =
        On( EventTriggerType.Attack = 9, ownerNeedsToBeAlive = true )
      & get_OwnerIsCaster
      & CurrentAttackDamageProfilesContain( DamageProfileType.Power = 0xe,
                                            includeNotApplied = true )

    $$CreateBehaviour =
        special = IsSpecialActiveAbility()
        return op_BitwiseAnd(
            Maybe( AddEffect(1065 Pinned,  AbilityStateReference, source = Owner@<+0x30>,
                             targets = Target@<+0x60>, options = <struct ZÉROÉE>),
                   ConditionalAmount(special, Double(ConfigVar(0x3a = chance)),   ConfigVar(0x3a)) ),
            Maybe( AddEffect(1162 Stunned, AbilityStateReference, source = Owner@<+0x30>,
                             targets = Target@<+0x60>, options = <struct ZÉROÉE>),
                   ConditionalAmount(special, Double(ConfigVar(0x3b = chance_2)), ConfigVar(0x3b)) ) )

* **DEUX tirages INDÉPENDANTS, `Pinned` PUIS `Stunned`.** `MaybeBehaviour$$Execute` tire UNE fois
  AVANT son enfant, `CombinedBehaviour` exécute gauche puis droite. **C'est l'observable le plus
  dur de la tranche, et il est invisible des dégâts** : les fusionner (ou les inverser)
  désynchronise le PRNG de toute la bataille sans qu'aucun coup ne bouge. Gardé par l'état du
  MT19937 (`dumpRng.mti` natif contre `state.rng.mti` port), pas par les valeurs.
* **`Double(x) = x * 2`, SANS plafond** — aucun `Min(.., 100)` dans l'arbre. Au palier 10
  (`chance = 50`) une active porte donc 100 %.
* **`chance` et `chance_2` sont DEUX variables** (`0x3a` / `0x3b`), même si le gameconfig leur donne
  aujourd'hui les mêmes dix paliers (33..50).
* **`includeNotApplied = true`** : `DamageProfilesContainsTrigger$$ShouldTrigger` lit DEUX listes
  distinctes de l'`AbilityEntities` selon ce drapeau — `+0xc8` (tous les profils) quand il vaut
  `true`, `+0xd0` (les profils APPLIQUÉS) sinon. `FinishAttackOperation$$Execute` les remplit
  depuis le composant d'attaque courant (`+0x58` → `+0xc8`, `+0x60` → `+0xd0`).

### `IsSpecialActiveAbility` — ce qui est LU, et ce qui ne l'est pas

    IdunBattleLogic.Entities.DSLTriggers$$IsSpecialActiveAbility =
        sel = <DSLSelectors+0x90>                     // le selecteur d'ability
        return <TypeA>(sel) & op_LogicalNot( <TypeB>(sel) )

Les deux conjoints ont un `.ctor` trivial **FONDU par l'ICF** (ghidra affiche
`UnityEngine.Scripting.RequiredByNativeCodeAttribute$$.ctor` pour les deux) : seul le `Il2CppClass*`
du cache de metadata les distingue, et ce slot est **non résoluble à froid** — il est rempli par
`il2cpp_codegen_initialize_runtime_metadata`, et il est **propre à chaque méthode**, donc la
comparaison inter-méthodes ne tranche rien non plus (contrôle fait : les DAT de
`DSLTriggers$$IsNormalAttack` sont différents de ceux d'`IsSpecialActiveAbility` alors que la
classe pourrait être la même). Ce qui EST lu : la FORME `A & !B` sur le canal d'ability, le NOM de
la méthode DSL, et le fait qu'`IsActiveAbilityTrigger$$ShouldTrigger` **rend `false` sur un
`Nullable` vide** (branche `if (*pcVar13 == '\0')`). Le port évalue donc `ctx.attack_ability_type` :
`None` → faux, `NORMAL_ATTACK_KIND` → faux, sinon vrai. Résidu `#1009-r3`.

## 4. LE BUG TROUVÉ : le couple TERTIAIRE n'atteignait PAS les owner-effects captés LIVE

**Le port divergeait de lui-même**, et c'est ce que la confrontation a mis au jour :

* la voie OFFLINE (`spawn.py::_seed_ability_owner_effects`) passe déjà le couple TERTIAIRE quand
  l'ability est `ctx.tertiary_ability` (#1005/#1007) ;
* la voie LIVE (`decisionView.effects` → `EffectsState.seed`) est clée par PORTEUR et ne connaît
  que le couple PASSIF — **et c'est ELLE qui gagne**, parce que `_materialize_owner_effect` est
  idempotent (`has_effect` → no-op dès que l'effet est déjà capté).

Sur un runner live, un owner-effect de relique arrivait donc TOUJOURS au niveau des passifs (50),
c'est-à-dire au dernier palier après clamp. **Mesuré** sur `darkaCompanion`, relique niveau 3 :

| grandeur | palier 3 (juste) | lu avant le fix | écart |
|---|---|---|---|
| `extraDmg` | **543** | 728 | +185 par coup |
| `blockDmg` | **1629** | 2184 | +555 par block |

Et le replay bit-exact le montrait sans ambiguïté : per-hit port `[3196, 920, 944, 829, 1040, 875]`
contre live `[2974, 772, 734, 860, 747, 863]`.

**Réparation** : `snapshot._rebake_tertiary_owner_effects(state)` — mirror du bake natif
(`AddEffectBehaviour$$DefaultEffectBuilder` copie l'`AbilityStateReference` dans
`EffectComponent+0x18`, et `BaseEffect$$GetAbilityStateReference` relit ce champ et rien d'autre).

⚠ **SA PLACE EST LE FIX, PAS SON CORPS.** Posé dans `_load_stats_and_effects`, il voyait
`tertiary_ability = None` sur toutes les unités et ne mordait sur RIEN : `_load_tertiary_abilities`
tourne **APRÈS**. Il est donc appelé depuis `load_state`, juste après elle, et son compte entre
dans `state.ability_states_seed["rebakedTertiaryOwnerEffects"]`.

**PORTÉE STRICTE** : ne sont réécrits que les effets dont le NOM figure dans
`ABILITY_INIT_OWNER_EFFECTS[<ability TERTIAIRE de CETTE unité>]`. Une unité sans relique, un
`tertiary_ability_level` à 0 (= « verrouillé »), un effet homonyme d'un autre canal : intacts. Le
rayon RÉEL est donc `Vitarus` (#1005) et cette tranche — et pour `Vitarus` la valeur devient juste
par les DEUX voies (son canal `att_ctx`/`relic_ability_state` donnait déjà la bonne).

## 5. Ce que la confrontation a mesuré

Montage `probe_1009_reliques_dark_angels.py`, board `MC1_67`, placements explicites (Forcas
adjacent au `Vehicle`, Baraqiel adjacent au `BigTarget`), reliques au **niveau 3** — choisi parce
qu'il SÉPARE le palier tertiaire du palier clampé (`543`/`728`, `1629`/`2184`, `36`/`50`). Seule
`blockChance` ne sépare pas : elle est CONSTANTE (10) sur les dix paliers du gameconfig.

* le NATIF pose bien `1539` **et** `1540` sur Forcas **au déploiement**, sans qu'aucune attaque
  n'ait eu lieu → le canal est `ABILITY_INIT_OWNER_EFFECTS`, jamais `RELIC_ABILITY_TRIGGERS` ;
* attaque de Forcas contre le `Vehicle`, rejouée RNG-seedée : per-hit et PV **bit-exacts** ;
* attaque de Baraqiel : per-hit et PV bit-exacts, **et `mti` natif == `mti` port** (16 == 16, contre
  16 vs **14** tant que le trigger ne firait pas) — les deux `next_bool` sont bien consommés ;
* au seed `4242`, le premier `Maybe` PASSE : le natif pose `Pinned`, le port pose **le même** ;
* TÉMOIN sans relique : aucun des deux effets, aucun `Pinned`/`Stunned`, et bit-exact lui aussi.

Un écart subsiste et **ne regarde pas ce port** : `1515 RangedSpecialist` disparaît de
`decisionView.effects` côté natif quand l'attaquant devient adjacent (sa `CreateActiveCondition`
s'éteint) et le port, qui ne la modélise pas, le garde. La comparaison d'effets est donc restreinte
à `{Pinned, Stunned}`, l'observable de la tranche.

## 6. Résidus

* **`#1009-r1`** — la face BLOCK de `1540` n'est pas confrontée LIVE : `blockChance = 10 %` et
  aucun block n'est survenu dans le montage. Le port est gardé OFFLINE (valeur, identité de la
  source, indépendance aux stats du défenseur).
* **`#1009-r2`** — `bloodIntercessor` (Blood Angels) et `templAggressor` (Black Templars), les deux
  autres `allowedUnits` de `RelicPowerFist`, ne sont pas confrontés. **La branche `Double` est
  INATTEIGNABLE sur `darkaTerminator`** : sa seule active (`PlasmaCannon`) a pour constante
  `damageProfile = Plasma`, que le conjoint `CurrentAttackDamageProfilesContain(Power)` refuse.
* **`#1009-r3`** — l'appariement NOMINAL des deux conjoints d'`IsSpecialActiveAbility` (cf. §3).
