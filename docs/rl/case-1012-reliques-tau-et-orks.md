# #1012 — Reliques Tau et Orks : `Dw02AdvancedBurstCannon` (1476) et `HeadwoppasKillchoppa` (1549)

> Build `rnca9r7q6c`. Deux reliques de la voie `item` (`items[*].abilityId` + `allowedUnits`), deux
> porteurs de **factions différentes**, donc **deux harnais live distincts**. La première est
> **PORTÉE et CONFRONTÉE 3 bras / 3** ; la seconde a sa **RE complète écrite ici** et reste
> **NON PORTÉE** — résidu `#1012-r1`.

| id | ability | porteur | verdict |
|---|---|---|---|
| 1476 | `Dw02AdvancedBurstCannon` | `tauCrisis` « Re'vas » (HERO, pool rank 17) | **PORTÉE + CONFRONTÉE** |
| 1549 | `HeadwoppasKillchoppa` | `orksWarboss` « Gulgortz » (HERO, pool rank 17) | **RE COMPLÈTE, NON PORTÉE** (`#1012-r1`) |

Les deux sont des `TriggeredAbilityType` : elles n'entrent **ni** dans `ABILITY_CLASSES`, **ni**
dans `TARGETING_OPTIONS`, **ni** dans `ABILITY_ATTACK_TYPE`.

---

## 1. `Dw02AdvancedBurstCannon` (1476) — PORTÉE, CONFRONTÉE 3 bras / 3

i2 (`Abilities/Dw02AdvancedBurstCannon_CurrentLevelDescription`) : « Each time Re'vas attacks, she
gains +{[extraPierceRatio]}% pierce ratio. After attacking {[nrOfAttacks]} times, this bonus is
reset, and Re'vas can use her active ability again. »

### 1.1 RE — UNE classe native, deux corps, tous deux dans les tables

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Dw02AdvancedBurstCannonAbility` (parent
`IdunBattle.Entities.Abilities.BaseTriggeredAbility`, `frida/classes.tsv`). Contrairement à
`DaemonfleshPlateAbility`, **rien n'est dédupliqué ici** : les deux corps sont nommés.

`...Dw02AdvancedBurstCannonAbility$$CreateTrigger` :

    On( 9 = EventTriggerType.Attack, ownerNeedsToBeAlive = 1 )
  & get_OwnerIsCaster
  & NOT IsSpecialActiveAbility

`...Dw02AdvancedBurstCannonAbility$$CreateBehaviour(abilityState, triggerType)` :

    counter = GetPersistentData( AbilityOrEffect(Dw02AdvancedBurstCannon), Owner@DSLSelectors+0x30,
                                 Get(<littéral de chaîne>) )
    cond    = AmountIsEqualOrGreater( counter,
                                      Subtract( ConfigVar(0x4e = nrOfAttacks, abilityState, config),
                                                <DSLFormulas+0x20> = Direct(1) ) )
    THEN    = (   RemoveEffect( Owner@+0x30, Nullable(0x5be = Dw02AdvancedBurstCannon_ExtraPierceRatio) )
                & ResetActiveAbility( Owner@+0x30, allowUseless = true ) )
              & ClearPersistentData( AbilityOrEffect(Dw02AdvancedBurstCannon), Owner@+0x30, Get(<littéral>) )
    ELSE    = AddStaticStatModifierEffect( targets = Caster@DSLSelectors+0x48,
                                           0x5be = Dw02AdvancedBurstCannon_ExtraPierceRatio,
                                           stat   = 0x1a = StatType.ExtraPierce,
                                           amount = ConfigVar(0x3f = extraPierceRatio),
                                           turns  = null, isHidden = false )
              & AddPersistentData( AbilityOrEffect(Dw02AdvancedBurstCannon), Owner@+0x30,
                                   Get(<littéral>), <DSLFormulas+0x20> = Direct(1) )
    return    If( cond, THEN, ELSE )

**L'ORDRE EST LU, ET C'EST CELUI DE `DaemonfleshPlate`, PAS CELUI DE `VolummsMasterArtifice`.** Le
dernier appel du corps est `DSLBehaviors$$If(cond, THEN, ELSE)` : le `If` est la RACINE, donc le
compteur est testé AVANT tout incrément et le seuil est `nrOfAttacks - 1`.
`VolummsMasterArtifice`, lui, place son `AddPersistentData` à GAUCHE d'un `op_BitwiseAnd` dont le
`If` est le terme DROIT — seuil sur le compteur DÉJÀ incrémenté. Recopier le mauvais voisin
décalerait le reset d'une attaque **et** ajouterait une pile.

**DEUX écarts avec `DaemonfleshPlate`, tous deux LUS et tous deux observables** :

1. le re-armement de l'active est **IMMÉDIAT** — `ResetActiveAbility` est DANS la branche THEN.
   `DaemonfleshPlate` pose un marqueur (effet 1491) et attend son `On(0x3a = PhaseEnd)`. Il n'y a
   donc ici **ni seconde classe native, ni second effet** ;
2. le gate `NOT IsSpecialActiveAbility`, absent de `DaemonfleshPlate` (§1.2).

### 1.2 `IsSpecialActiveAbility` — la sémantique vient de l'AUTRE call-site, pas du nom de classe

`IdunBattleLogic.Entities.DSLTriggers$$IsSpecialActiveAbility` :

    <A>( TriggeringAbility@DSLSelectors+0x90 )  &  NOT <B>( TriggeringAbility@DSLSelectors+0x90 )

Les deux opérandes lisent le MÊME slot `<DSLSelectors+0x90>` = le canal `TriggeringAbility`
(`AbilityEntities+0x98`, cf. la table de `engine/runner/state.py`). `<B>` est la classe que
`DSLTriggers$$IsNormalAttackOrHealOrRepair`, `$$IsTriggeringAbilityNormalAttackOrHealOrRepair` et
`$$IsActiveAbilityCountedAsUsed` allouent aussi (même slot de metadata `1833a8370`) ; `<A>`
(`1833a84b8`) **n'est alloué que par cette fonction**, donc aucun `DSLTriggers$$X` nommé ne le
nomme — son NOM PROPRE reste un résidu (les tables ne portent que cinq
`Entities.Triggers.Ability*Trigger$$ShouldTrigger`, et leurs `.ctor` sont dédupliqués sur
`UnityEngine.Scripting.RequiredByNativeCodeAttribute$$.ctor`).

**Ce qui tranche, c'est le SECOND call-site.** Le prédicat n'a que **deux** xrefs `CALL` dans tout
le binaire : ce `CreateTrigger`, et
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicPowerFistAbility$$CreateBehaviour`, dont
l'i2 dit mot pour mot : « These chances are doubled **if the attack is an active ability**. »
⇒ `IsSpecialActiveAbility` = « l'ability déclenchante est une ability ACTIVE **autre que** l'attaque
normale ».

⚠ **CE GATE EST INERTE SUR LE SEUL PORTEUR AUTORISÉ, ET C'EST MESURÉ.** La relique est
`isUniqueRelic` avec `allowedUnits = ["tauCrisis"]` ; l'unique active de Re'vas est
`EarlyWarningOverride` (1077), qui summone des drones et pose de l'Overwatch — elle ne porte AUCUNE
attaque, donc aucun `On(9 = Attack)` ne peut arriver avec elle en ability déclenchante. Le gate est
porté quand même, parce que le natif le porte ; il ne peut se manifester que sur une GREFFE.

Côté port, le canal est `TriggerEvent.ability_type` (`None` sur la voie NORMALE, l'id de l'ability
sur la voie ABILITY). « Est-ce une ACTIVE ? » se lit sur les actives RÉELLEMENT MONTÉES du caster
(`UnitContext.active_ability_levels`) — l'ORDINAL SEUL ne trancherait rien, `TriggeredAbilityType` et
`ActiveAbilityType` partageant 233 valeurs. Trois dégradations nommées dans
`_is_special_active_ability` (voie normale, marqueur de kind `0x3f5 = 1013`, canal non mesuré).

### 1.3 Ce que la mécanique fait, étage par étage

Compteur `c` dans le `PersistentDataComponent` du porteur, clé
`(GetPersistentDataId(AbilityOrEffect(1476)), <littéral>)`. `AddPersistentData` **ACCUMULE**.
Avec `N = nrOfAttacks` (**8** aux niveaux 1-5, **7** aux niveaux 6-10) et `p = extraPierceRatio`
(3 / 4 / 5 / **6** selon le palier) :

    attaques 1..N-1 : `c >= N-1` faux -> ELSE : +1 pile de `+p` ExtraPierce, `c += 1`
    attaque  N      : `c = N-1 >= N-1` VRAI -> THEN : les N-1 piles retirées d'un coup,
                      l'active RE-ARMÉE dans la foulée, compteur vidé

Le maximum est `(N-1) × p`, **pas** `N × p`.

### 1.4 Le port

* `engine/runner/operations/triggers/loki/dw02_advanced_burst_cannon.py` — `CreateTrigger` collapsé
  dans `matches`, `CreateBehaviour` en ARBRE DSL (doctrine #149), magnitude et seuil résolus par
  `triggered_ability_state` + `ability_var` ;
* `engine/entities/effects/loki/dw02_advanced_burst_cannon.py` — l'effet **1470**
  (`Dw02AdvancedBurstCannon_ExtraPierceRatio`), `stacks_stat_mod_on_add = True`,
  `StatType.ExtraPierce` ;
* `RELIC_ABILITY_TRIGGERS["Dw02AdvancedBurstCannon"]` et
  `EFFECT_CLASSES["Dw02AdvancedBurstCannon_ExtraPierceRatio"]`, **dans le même commit**.

⚠ **L'ORDINAL 1470 est ambigu et les deux membres nommés sont obligatoires** : `EffectType` 1470 =
`Dw02AdvancedBurstCannon_ExtraPierceRatio`, mais `TriggeredAbilityType` 1470 = `Vitarus` (une AUTRE
relique, portée). Symétriquement `EffectType` 1476 = `DespoiledGround`.

⚠ **Le canal du bonus est un STAT-MOD, pas un `EffectBonus`** : `AddStaticStatModifierEffect(...,
stat = ExtraPierce)`, pas la patte `PiercingBonusForAttack` de `RelicBoltPistol_ExtraPierce`. Les
deux finissent dans la même somme de
`IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` (avant le `Min(100, ...)`),
par deux chemins distincts.

### 1.5 Confrontation LIVE — `probe_1012_dw02_burst_cannon.py`, 3 bras / 3, rc = 0

Montage : `rl_duel build --equip-relic "tauCrisis:Dw02AdvancedBurstCannon:<lvl>" --hp-target 900000
--hp-player 900000 --no-ai --crit 0,0 --block-target 0,0`, board `MC1_67`, seed 777, cible
`astraBullgryn`.

⚠ **DEUX pièges de montage MESURÉS, aucun des deux hérité de #916** :

1. **Monter les PV ne sauve pas la série.** En MÉLÉE, Re'vas tue la cible à la 6ᵉ action quelle que
   soit sa santé : `900000` PV → **189 389** de dégât par action ; `9000000` PV → **1 809 389**. Les
   deux points donnent `dégât = 0,20 × maxHP + 9 389` — une composante en POURCENTAGE des PV MAX
   (son arme de mêlée est `Flame` + trait `OnFire`), donc **5 actions pour tuer, à n'importe quel
   niveau de PV**. La série se joue donc **À DISTANCE 2** (`Pulse`, aucun trait) : ~8 500 par action.
   Le `CreateTrigger` de la relique ne porte aucun gate de nature de coup, donc ce choix ne touche
   aucun étage mesuré.
2. **L'active du porteur n'est PAS une attaque** (elle summone deux Shield Drones + Overwatch) :
   elle est castée **hors série**, dans `stage`, contrairement à #916 dont le cast d'active EST
   offensif et COMPTE dans le décompte. La consommer est ce qui rend `ResetActiveAbility`
   observable — `BattleQuery$$EntityCanHaveActiveAbilityReset` refuse de ré-armer une active déjà
   utilisable.

Résultats (natif == port == attendu sur les deux canaux, dans les trois bras) :

| bras | niveau | (p, N) | perçage natif |
|---|---|---|---|
| NOMINAL | 3 | (4, 8) | `[4, 8, 12, 16, 20, 24, 28, 0, 4, 8]` |
| NIVEAU6 | 6 | (5, 7) | `[5, 10, 15, 20, 25, 30, 0, 5, 10]` |
| SPECTATEUR | 3 | (4, 8) | `[0] × 10` |

Canal ACTIVE : `[False × 7, True × 3]` (NOMINAL), `[False × 6, True × 3]` (NIVEAU6),
`[False × 10]` (SPECTATEUR) — natif et port identiques.

**Le niveau 3 est choisi parce qu'il SÉPARE le palier tertiaire du palier clampé** (le dernier vaut
`(6, 7)`) : un port qui lirait le niveau PASSIF (50 sur tout runner normalisé) se trahirait sur les
DEUX variables. Le mutant `NIVEAU_PASSIF` le montre : `[6, 12, 18, 24, 30, 36, 0, 6, 12, 18]`.

**Les 7 mutants mordent exactement là où le RE le prédit** (attentes DÉRIVÉES, pas observées) :
`SEUIL_N` (les deux canaux), `NOCLEAR` (perçage seul), `INCREMENT_2` (les deux), `NORESET` (active
seule), `NOSTACK` (perçage seul), `NIVEAU_PASSIF` (dérivé du gameconfig), `OWNERISCASTER_OFF`
(aucun canal dans les bras nominaux — contrôle négatif ; les DEUX canaux dans le bras SPECTATEUR).

⚠ **`stacks_stat_mod_on_add = True` est une MESURE**, pas une déduction d'un nom de slot : la série
`4, 8, 12, …` l'établit. Un effet rafraîchi rendrait `4, 4, 4, …` (mutant `NOSTACK`).

Cliquet : `tests/engine/runner/test_1012_dw02_burst_cannon_live.py` (4 tests, montage et attendus
IMPORTÉS du probe).

---

## 2. `HeadwoppasKillchoppa` (1549) — RE COMPLÈTE, NON PORTÉE (résidu `#1012-r1`)

**Aucun texte i2 n'existe pour cette ability** (ni `_CurrentLevelDescription`, ni
`_NextLevelDescription`) : seul `Items/R_Crit_HeadwoppasKillchoppa_name` est traduit. La mécanique
ci-dessous est donc **entièrement lue au décompilé**, sans aucun appui sur un tooltip.

gameconfig : `variables.extraDmg = [195, 206, 216, 227, 237, 248, 258, 269, 279, 290]` (10 paliers de
RELIQUE), `constants.unitId = "orksNpc2OrkBoy"`.
item : `R_Crit_HeadwoppasKillchoppa`, `isUniqueRelic`, `allowedUnits = ["orksWarboss"]`.

### 2.1 L'ability — un owner-effect posé à l'init

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeadwoppasKillchoppaAbility` (parent
`IdunBattle.Entities.Abilities.BaseTriggeredAbility`).

`...HeadwoppasKillchoppaAbility$$CreateTrigger` — **ABSENT des deux tables**, corps DÉDUPLIQUÉ.
L'appartenance est établie **slot à slot dans le bloc `methodPointers` du PE** (même méthode que
#916 / #910) : le groupe de la classe s'y lit entre deux occurrences du corps partagé
`UnityEngine.Scripting.RequiredByNativeCodeAttribute$$.ctor` (le `.ctor` trivial dédupliqué qui sert
de séparateur de fait), et vaut, dans l'ordre :

    <sep>  CreateTrigger  CreateBehaviour  <sep>

où `CreateTrigger` pointe sur le corps que la table attribue à
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WayOfTheShortBlade_InitAbility$$CreateTrigger` —
c'est-à-dire :

    OnOwnerSpecificAbilityInit( this.<AbilityType> )

(le corps est GÉNÉRIQUE : il lit le type d'ability sur l'instance, d'où le partage légitime. Le
groupe voisin, contrôle de la lecture, est celui de `HealingBalmsAbility`, dont le `CreateTrigger`
partage le corps de `SummaryExecutionAddBaseEffectAbility$$CreateTrigger`.)

`...HeadwoppasKillchoppaAbility$$CreateBehaviour(abilityState, triggerType)` :

    AddEffect( 0x620 = 1568 HeadwoppasKillchoppa_ExtraDmg,
               abilityState = BaseTriggeredAbility$$get_AbilityStateReference,
               source  = Owner@DSLSelectors+0x30,
               targets = Owner@DSLSelectors+0x30,
               options = Nullable<AddEffectBehaviourOptions>{ +0x00 = null, +0x08 = null,
                                                              +0x10 = <DSLFormulas+0x18> = Direct(0) } )

⇒ canal `ABILITY_INIT_OWNER_EFFECTS["HeadwoppasKillchoppa"] = ["HeadwoppasKillchoppa_ExtraDmg"]`
(patron `ToughToKill` / `Vitarus` / `Skullsmasher`), **mais par un `CreateBehaviour` PROPRE**, pas par
la base `AOwnerEffectTriggeredAbility` — la classe dérive de `BaseTriggeredAbility`.

⚠ **UNE FOURCHE NON TRANCHÉE, ET ELLE EST LOAD-BEARING** : le 3ᵉ champ des `options` vaut
`Direct(0)`. Est-ce la **durée** (⇒ effet PERMANENT, patron « turns = `<zeroe>` » des owner-effects)
ou le **niveau initial** (⇒ effet posé à **level 0**) ? L'argument STRUCTUREL penche pour le niveau :
la `CreateActiveCondition` de l'effet est `AmountIsGreaterThanZero(EffectLevel)`, ce qui serait
mort-né si l'effet naissait au niveau 1 (patron `Skullsmasher`, dont l'`ActiveCondition` est
`AmountIsGreaterThanZero(GetMissingHealthSteps())`). **La mesure qui tranche** : lire
`decisionView.effects` (avec `includeInactive: true`) sur un Gulgortz fraîchement monté avec la
relique, AVANT toute mort — niveau 0 ⇒ c'est le niveau ; niveau 1 et effet actif ⇒ c'est la durée.

### 2.2 L'effet 1568 — `IdunBattle.Entities.Effects.Loki.HeadwoppasKillchoppaEffect`

Parent `IdunBattle.Entities.Effects.BaseEffect`, taille 1152 (`frida/classes.tsv`).

`...HeadwoppasKillchoppaEffect$$.ctor` — le littéral est RELU AUX OCTETS (le pseudo-C le perd, il
part par `edx`) :

    ba 0d 06 00 00              ; mov  edx, 0x60d = 1549
    e8 <rel32>                  ; call IdunBattle.Core.AbilityOrEffect$$op_Implicit
    41 b0 01                    ; mov  r8b, 1  = hasAutomaticActivation
    e8 <rel32>                  ; call IdunBattle.Entities.Effects.BaseEffect$$.ctor

⇒ la config lue par tous les `ConfigVar` de l'effet est **`HeadwoppasKillchoppa`** (paliers de
RELIQUE), pas une config d'active.

    ...$$GetCurrentDamageBonus =
        Multiply( ConfigVar(0x8 = extraDmg, GetAbilityState(this), config@this+0x60),
                  EffectLevel( Effect@DSLSelectors+0x38 ) )

    ...$$GetCurrentDamageBonusMultiplier =
        EffectLevel( Effect@DSLSelectors+0x38 )          # le SEUL terme, sans ConfigVar

    ...$$CreateEffectDamageBonusForAttack =
        EffectBonus.ForAddition( IsMeleeAttack & get_OwnerIsCaster,
                                 GetCurrentDamageBonus() )

    ...$$CreateActiveCondition =
        AmountIsGreaterThanZero( EffectLevel( Effect@+0x38 ) )

    ...$$CreateTargetSelector =
        Owner@DSLSelectors+0x30
      + Friends( Owner@+0x30,
                 UnitsWithVisualId( ConfigConstString( TriggeredAbilityConfigId(...), 0 ), 1 ),
                 3 )

    ...$$CreateHandleTriggerAbilitiesInternal = ArraySet{
        DSLFactory.Triggered(
            trigger   = BaseEffect$$On( 0x36 = 54 EventTriggerType.UnitDefeated )
                      & NOT IsSteppableUnit( Targets@DSLSelectors+0x60 )
                      & AreEqual( DSLSelectors$$Attacker(), Owner@+0x30 ),
            behaviour = IncreaseEffectLevel( Owner@+0x30, <this.effectType @+0x10>,
                                             cap = null ),
            null ) }

⇒ **la mécanique, en clair** : la relique donne à Gulgortz **et à ses Ork Boyz alliés** (sélecteur
par `visualId` — `orksOrkBoys`, le summon de son active `Waaagh` 1058, a bien
`visualId = "orksNpc2OrkBoy"`, le `constants.unitId` de la relique) un bonus de dégât de MÊLÉE de
`extraDmg × <niveau de l'effet>`, et ce niveau monte de **+1 à chaque unité non-`Steppable` abattue
par le porteur de l'instance** (`AreEqual(Attacker(), Owner)`). Sans cap : `IncreaseEffectLevel` est
appelée avec `cap = null`, contrairement à `Neuroparasite` (`$$GetMaximumLevel`).

`ConfigConstString` lit `constants.unitId` de la config `HeadwoppasKillchoppa`, soit
`"orksNpc2OrkBoy"` ; le 3ᵉ argument de `Friends` est un `UnitTeamSelectionType` (mirror #963-r1) dont
la valeur `3` **n'est pas dans le mirror à deux membres du build** (`0 = ByCurrentTeam`,
`1 = ByOriginalTeam`) — à re-dériver avant de porter.

### 2.3 Pourquoi ce n'est PAS porté ici, et ce qu'il reste à faire

Quatre étages manquent, et aucun n'est une variante d'un étage déjà porté :

1. **la classe d'effet 1568** — patte `create_effect_damage_bonus_for_attack` gatée
   `IsMeleeAttack & get_OwnerIsCaster`, magnitude `extraDmg × EffectLevel` ;
2. **l'AURA** — `CreateTargetSelector` projette l'effet sur les Ork Boyz alliés, donc chaque
   récipiendaire a SA propre instance, dont l'`Owner` est LUI. Conséquence lue, contre-intuitive :
   un Ork Boy qui tue monte **son propre** niveau, pas celui de Gulgortz ;
3. **le trigger interne de l'effet** (`CreateHandleTriggerAbilitiesInternal`) — patron
   `NeuroparasiteEffect`, déjà porté ailleurs, mais jamais sur `On(0x36 = UnitDefeated)` ;
4. **l'entrée `ABILITY_INIT_OWNER_EFFECTS`** et la fourche `options` du §2.1.

**Le montage live est écrit et il n'a pas de bloqueur connu** : `orksWarboss` est **dans le pool
rank 17** (vérifié `rl_duel build --list-pool`), la relique s'équipe par
`rl_duel build --equip-relic "orksWarboss:HeadwoppasKillchoppa:<lvl>"` (état 2 de #237, `allowedUnits`
satisfait). Il faut **des morts** pour faire monter le niveau : `--a-units` avec plusieurs cibles
FRAGILES (`--hp-target` bas) que Gulgortz abat au contact, puis mesure du dégât de mêlée AVANT/APRÈS
chaque kill. `Waaagh` (1058) summone les deux Ork Boyz qui exercent la face AURA.

⚠ **Le piège de mesure de #1012 vaut ici aussi, en sens inverse** : Gulgortz frappe en `Eviscerate`
(mêlée, `PiercingRatio` 50) — il faut des cibles qui SURVIVENT quand on mesure le bonus et qui
MEURENT quand on veut incrémenter. Deux populations distinctes de cibles, pas une.

Résidu : **`#1012-r1`**.

---

## 3. Ce qui n'est PAS couvert

* `Dw02AdvancedBurstCannon` — le gate `NOT IsSpecialActiveAbility` est **INERTE sur le seul porteur
  autorisé** (§1.2) : il est porté et non exercé. Le confronter demanderait une GREFFE de la relique
  sur une unité dont une active OFFENSIVE existe (`--allow-unlisted-relic`), montage non joué ici.
* Le NOM de la classe `<A>` d'`IsSpecialActiveAbility` reste non résolu (§1.2) ; c'est la SÉMANTIQUE
  qui est tranchée, par le second call-site.
* `HeadwoppasKillchoppa` — RE complète, **aucun** étage porté, **aucune** mesure live (§2.3).
