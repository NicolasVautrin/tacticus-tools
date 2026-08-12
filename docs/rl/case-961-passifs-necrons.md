# case-961 — `TimesplinterMantle` (1534) et `LivingLightning` (1007 + 1020)

Les deux DERNIERS items manquants de leurs kits : `necroChronomancer` « Thothmek » (actif
`Chronometron` 1226 déjà porté) et `necroPlasmancer` « Thutmose » (actif `HarbingerOfDestruction`
1008 déjà porté + validé).

Build de RE : `rnca9r7q6c`. Toutes les surcharges sont tranchées par l'**adresse du `call`**
(`probe_951_call_targets.py`), jamais à l'œil.

---

## 1. Recensement — slots totaux / corps propres

Fait par la **colonne « classe déclarante »** de `frida/methods.tsv` et par la table de méthodes,
jamais par grep de texte libre. Base LUE dans `frida/classes.tsv`.

| classe native | base | corps propres |
|---|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimesplinterMantleAbility` | `BaseTriggeredAbility` | 4 (`CreateTrigger`, `CreateBehaviour`, `GetTargets`, `GetAddOrActivateEffect`) |
| `IdunBattle.Entities.Effects.Loki.TimesplinterMantle_DamageReductionEffect` | `ADamageDefenseModifierAbilityEffect` | 3 (`.ctor`, `CreateDamageDefenseModifier`, `CreateRemoveEffectTrigger`) |
| `IdunBattle.AI.Playbook.Loki.TimesplinterMantlePlaybook` | `AdjacentUnitPreferenceTriggeredAbilityPlaybook\`1` | 3 — face DÉCISION, **hors tranche** |
| `IdunBattleLogic.Playbook.Triggered.Loki.TimesplinterMantleNonOwnerPlaybook` | `AdjacentToOwnerNonOwnerPlaybook\`1` | 3 — **DÉJÀ PORTÉ** (`engine/playbook/non_owner.py`) |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.LivingLightningAbility` | `BaseTriggeredAbility` | 4 (`CreateTrigger`, `CreateBehaviour`, `GetPossibleTargets`, `GetEnemiesInRange`) |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.LivingLightningMoveEffectAbility` | `BaseTriggeredAbility` | 3 (`CreateTrigger`, `CreateBehaviour`, `TargetTilesHasAdjacentEnemies`) |
| `IdunBattle.Entities.Effects.Loki.LivingLightning_MovingEffect` | `BaseEffect` | 1 (`CreateRemoveEffectTrigger`) |

**Total : 21 corps propres** (dont 3 `View.AbilityConfigs.*Visuals`, hors périmètre, non comptés).

⚠ **Le NAMESPACE ne dit pas la famille** : les DEUX classes `LivingLightning*` vivent sous
`...Abilities.**Active**.Loki.` et dérivent de `BaseTriggeredAbility` — ce sont des **PASSIFS**.
Elles entrent dans `ABILITY_TRIGGERS`, jamais dans `handler.ABILITY_CLASSES` : ni
`TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` ne s'appliquent.

⚠ **Trois « corps propres » sont des helpers C# INLINÉS** (aucune xref CODE, seulement les entrées
de la table de méthodes) : `GetTargets` + `GetAddOrActivateEffect` (recopiés dans `CreateBehaviour`)
et `TargetTilesHasAdjacentEnemies` (recopié dans `CreateTrigger`). `GetEnemiesInRange`, lui, est le
corps de `GetPossibleTargets` avec le rayon en paramètre.

### Chaque événement de trigger a-t-il un émetteur côté port ?

| événement | émetteur porté | état |
|---|---|---|
| `On(0x12 = TurnStart_EffectActivation)` | `dispatch/turn.py::tile_tick_triggers` | ✅ existant |
| `On(0x17 = TurnEnd)` | `dispatch/turn.py::end_turn_summon_triggers` | ✅ existant |
| `On(9 = Attack)` | `FinishAttackOperation` porté (after-hit normale + ability) | ✅ existant |
| `On(0x1c = ArrivedAtFinalTile)` | `dispatch/move_death.py::arrived_at_final_tile_triggers` | ✅ existant |
| `On(0x1f = PreUnitMove)` | `dispatch/move_death.py::pre_move_triggers` | ✅ existant |

**5 émetteurs sur 5 déjà portés ⇒ aucun étage amont à porter**, et c'est ce qui a fait le coût réel
de la tranche (prédiction tenue).

---

## 2. `TimesplinterMantle` — RE

    ...TimesplinterMantleAbility$$CreateTrigger
        = DSLTriggers.On(EventTriggerType.TurnStart_EffectActivation = 0x12,
                         ownerNeedsToBeAlive: true)

**UN SEUL nœud** — le corps est un `jmp` vers `On`, il n'y a AUCUN `op_BitwiseAnd`. En particulier
**PAS d'`IsTurnOf(Owner)`**, là où son voisin immédiat `RelentlessMarchAbility$$CreateTrigger` (le
seul autre passif Necron turn-start) en porte un. Recopier le voisin de forme aurait restreint la
pose au seul tour du porteur.

    ...TimesplinterMantleAbility$$CreateBehaviour(abilityState, triggerType)
        targets = AdjacentUnits(Owner@DSLSelectors+0x30, unique: 1, selectionType: 3)
                  |> Friends(of: Owner@+0x30, _, 3)
                  |> MechanicalUnits(_, 3)
                  |> NonSteppableUnits(_, 3)
                  op_Addition  Owner@+0x30
        return Foreach(targets,
                   AddEffect(0x60f = EffectType.TimesplinterMantle_DamageReduction,
                             AbilityStateReference, source = Owner@+0x30,
                             targets = ActiveTarget@+0x68,
                             options = Nullable<AddEffectBehaviourOptions> VIDE))

  * `NonSteppableUnits(e, sel)` = `op_BitwiseAnd(e, UnitsWithoutTrait(e, 0x1b = Steppable, sel))` —
    factory mirrorée telle quelle (`entities/selectors/units.py::non_steppable_units`) ;
  * la surcharge d'`AddEffect` retenue est la **5-args** `(effectType, abilityState, source,
    targets, options)` — la source est donc EXPLICITE (`Owner`), contrairement à la 4-args qui
    retombe sur la cible ;
  * `1551` est absent de `StaticBattleRules.Effect$$DefaultAmountOfRounds` ⇒ l'effet est PERMANENT
    jusqu'à son trigger.

    ...TimesplinterMantle_DamageReductionEffect$$.ctor
        = DamageModifierAbilityEffect..ctor(this, 0x5fe = TriggeredAbilityType 1534, 0)

    ...$$CreateDamageDefenseModifier
        = EffectBonus.ForSubtraction( get_OwnerIsTarget & IsUnit(Caster@+0x48),
                                      ConfigVar(0x12 = dmgReduction, GetAbilityState(effect), config),
                                      AbilityOrEffect(TriggeredAbilityType 1534) )

    ...$$CreateRemoveEffectTrigger
        = ( BaseEffect.On(9 = Attack) & get_OwnerIsTarget & IsUnit(Caster@+0x48) )
          op_BitwiseOr  BaseEffect.On(0x17 = TurnEnd)

Le trigger de retrait est greffé par `BaseEffect$$CreateHandleTriggerAbilities`, qui ajoute
`Triggered(CreateRemoveEffectTrigger(), DSLBehaviors.RemoveEffect(Effect@DSLSelectors+0x38))` à
l'`ArraySet` de l'effet quand le virtuel rend non nul.

**Sémantique de jeu** : une couverture PLATE ré-armée **au début de CHAQUE tour, les deux camps
compris**, consommée par la PREMIÈRE attaque reçue et de toute façon balayée à la fin du tour
courant.

### Carte des slots `DSLSelectors` de ce build, ÉTABLIE et non interpolée

Chaque getter NOMMÉ de `DSLTriggers` est un `AreEqual` de deux slots :
`get_OwnerIsActor = (+0x30, +0x40)`, `get_OwnerIsCaster = (+0x30, +0x48)`,
`get_OwnerIsTarget = (+0x30, +0x60)` ⇒ `Owner 0x30 · Effect 0x38 · Actor 0x40 · Caster 0x48 ·
CasterTile 0x50 · CasterTiles 0x58 · Target 0x60 · ActiveTarget 0x68 · PreviousActiveTarget 0x70 ·
TargetTiles 0x78 · UnitFeetTiles 0x80`. Le nom de `TargetTiles` est confirmé indépendamment par
`...LivingLightningMoveEffectAbility$$**TargetTiles**HasAdjacentEnemies`, qui lit `+0x78`.

---

## 3. `LivingLightning` — RE

    ...LivingLightningAbility$$GetPossibleTargets(targetAmount)
        radius = DSLFormulas.If( AmountIsGreaterThanZero(                       # surcharge SELECTEUR
                                     AdjacentEnemies(Caster@+0x48, unique: 1, sel: 3) ),
                                 <DSLFormulas+0x20> = Direct(1),
                                 Get(GetNumberConstant(0x16 = range)) )
        return SurroundingTiles(CasterTile@+0x50, includeCenter: 0, radius, onlyMovable: 0)
               |> UnobscuredTiles(fromAnyTiles: CasterTile@+0x50, _)
               |> Units(_, unique: 1, sel: 3)
               |> Enemies(of: Caster@+0x48, _, sel: 3)
               |> Damageable(_)
               |> PickRandomly(_, targetAmount, 0, 0x7fffffff, 0)

⚠ **L'i2 DIT « adjacent » et le décompilé dit AUTRE CHOSE.** Le tooltip
(« deals … to one random **adjacent** enemy ») ne décrit que la branche `then`. S'il n'y a AUCUN
ennemi adjacent, le rayon devient `constants.range` = **2** et l'éclair part quand même. Recopier
le tooltip aurait rendu l'ability muette dans ce régime — **mesuré live** : à distance 2 le natif
inflige bien 3693.

    ...LivingLightningAbility$$CreateTrigger
        = On(0x1c = ArrivedAtFinalTile, ownerNeedsToBeAlive: true)
          & get_OwnerIsActor
          & op_LogicalNot( AmountIsZero( GetPossibleTargets(Direct(1)) ) )

    ...LivingLightningAbility$$CreateBehaviour
        = AttackWithAttackDamage( caster = Caster@+0x48,
                                  target = GetPossibleTargets(Direct(1)),
                                  amount = MinMaxDamage(abilityState)
                                         = RandomAmount(GetVariableForLevel(0xc = minDmg),
                                                        GetVariableForLevel(0xd = maxDmg)),
                                  damageProfile = DamageProfileFromConfig(config),
                                  hits = Direct(GetNumberConstant(0x2f = nrOfHits)),
                                  abilityOrEffect = AbilityOrEffect(<this+0x10> = 1007),
                                  options = Nullable VIDE,
                                  selectionType = 2 = OnlyTargetable )

`<this+0x10>` est lu par un getter au corps `mov eax,[rcx+0x10] ; ret` que ghidra nomme
`CenterSpace.Free.MersenneTwister$$get_Count` — corps DÉDUPLIQUÉ, le nom est celui d'un
propriétaire arbitraire. La signature d'`AbilityOrEffect$$op_Implicit` qui le consomme
(`triggeredAbility : TriggeredAbilityType`) tranche.

`On(0x1c)` porte les DEUX moitiés du tooltip : le vecteur porté a deux émetteurs natifs, le
`MoveUnitOperation$$Execute` (après un déplacement) **et** la clôture de tour d'une unité qui n'a
pas bougé — tous deux gardés par le même flag `UnitFlag.ArrivedAtFinalTile`. Rien à ajouter.

### La dérivée 1020 et son chemin de montage

    ...LivingLightningMoveEffectAbility$$CreateTrigger
        = On(0x1f = PreUnitMove, alive) & get_OwnerIsActor
          & AmountIsEqualOrGreater( Enemies(of: Owner@+0x30,
                                            Units(AdjacentTiles(TargetTiles@+0x78), 1, 3), 3),
                                    Direct(1) )
    ...$$CreateBehaviour = AddEffect(0x3fc = 1020, AbilityStateReference, targets = Owner@+0x30,
                                     turns = Nullable<int> VIDE)
    ...LivingLightning_MovingEffect$$CreateRemoveEffectTrigger
        = On(0x1c = ArrivedAtFinalTile, alive) & get_OwnerIsActor

1020 est monté par `StaticBattleRules.**TriggeredAbility**$$GetDerivedTriggeredAbilities`
(`<statics>+0x88`, DEUX entrées seulement : `0x3ef -> [0x3fc]` et `0x48e -> [0x491]`), un dict
**DISTINCT** de `StaticBattleRules.**ActiveAbility**$$GetDerivedTriggeredAbilities`
(`<statics>+0x30`) que mirroire `ACTIVE_ABILITY_TRIGGERS` et qui est indexé par `ActiveAbilityType`.
Côté port les deux chemins convergent sur la même clé — le nom `units.passiveAbilities` — donc
inscrire les DEUX classes sous `ABILITY_TRIGGERS["LivingLightning"]` monte exactement l'ensemble
natif. `ACTIVE_ABILITY_TRIGGERS` serait faux : l'active de `necroPlasmancer` est
`HarbingerOfDestruction`.

---

## 4. Le nœud `UnobscuredTiles` — un résidu débloqué par sa DEUXIÈME bouche

Le résidu `#287-r11-r2-r1-r3` déclarait le nœud non matérialisable, et le motif était **littéralement
cette tranche** : « les trois call-sites natifs sont `MV71SniperDroneSquadAttackAbility$$PickTile`,
`LivingLightningAbility$$GetPossibleTargets` et `$$GetEnemiesInRange` ; les deux `LivingLightning`
ne sont pas portés, donc aucun second consommateur ne peut justifier le nœud seul ».

Le nœud est donc créé (`entities/selectors/tiles.py::UnobscuredTiles`) et **consommé**. Mirror lu :

    UnobscuredTilesSelector$$.ctor(state, movementQuery, fromTile, targetTiles)
        +0x20 = fromTile ; +0x18 = targetTiles ; +0x28 = movementQuery
    $$Select   : tiles = <+0x18>.Select(entities) ; caster = <+0x20>.SelectUnit(entities)
                 foreach t in tiles : if (!IsObscured(caster, t)) result.Add(t)
    $$IsObscured(caster, targetTile) :
        foreach c in IterateTiles(caster)
            if (<IMovementQuery slot 16>(c, targetTile, 6, 2).Count == 0)  return false;
        return true;

⇒ une tuile est GARDÉE dès qu'**UNE SEULE** tuile du référent la voit (d'où `fromAnyTiles`), et une
liste source VIDE rend `true` = obscurci ⇒ retirée.

**L'import est DIFFÉRÉ et sa classe est MESURÉE** : en process frais,
`import engine.services.movement_query` charge DÉJÀ `engine.entities.selectors.tiles`
(146 modules `engine.*`) — un import au niveau module fermerait le cycle. Différé **PORTEUR**,
forme B.

Le REBRANCHEMENT de la décision impérative de `runner/abilities/loki/mv71.py` sur ce nœud reste
ouvert : c'est le foyer d'un autre résidu, pas de celui-ci.

---

## 5. Ce que la validation LIVE établit

Montage `probe_961_necron_passives.py`, positions **DRIVÉES** et géométrie **assertionnée contre le
`boardGraph`** (l'adjacence stockée, pas seulement `hexgeo.distance`). Garde :
`tests/engine/runner/test_961_necron_passives_live.py` — **11/11**.

### TimesplinterMantle — 3 bordures + contre-épreuve + 4 contrefactuels

  * l'ensemble couvert live == port sur **3/3 bordures**, et il est mesuré **dans les deux sens de
    tour** (joueur 3→4 et 4→3) : c'est ce qui prouve l'absence d'`IsTurnOf(Owner)` ;
  * **NON DÉGÉNÉRÉ** : le port rejoue la bordure COMPLÈTE, et l'ensemble juste après `On(0x17)` est
    **VIDE** — l'accord n'est donc pas un héritage de la capture ;
  * l'ensemble couvert EST discriminant : `necroChronomancer` (l'`op_Addition Owner`) +
    `admecRuststalker` (Mechanical adjacent), et EUX SEULS — `astraBullgryn` (organique adjacent),
    `admecManipulus` (Mechanical à distance 2) et `orksKillaKan` (ennemi **Mechanical** adjacent)
    en sont exclus, chacun par un gate différent ;
  * contrefactuels sur les MÊMES captures : `mechanical` **3/3**, `friends` **3/3**, `adjacent`
    **3/3**, `owner` **3/3**. `steppable` reste **inerte** (aucune unité `Steppable` au montage) et
    c'est DIT, pas compté pour un succès ;
  * contre-épreuve NÉGATIVE : une attaque sur une unité couverte retire 1551 de CELLE-LÀ et d'elle
    seule, live comme port.

⚠ **`friends` ne mordait PAS avec un ennemi ORGANIQUE** (`blackTerminator`, 0/3) : `MechanicalUnits`
l'écartait déjà, donc le montage était AVEUGLE à ce gate. Il faut un ennemi **Mechanical**
(`orksKillaKan`) pour que `Friends` soit le SEUL exclusif.

⚠⚠ **La contre-épreuve exige un tour adverse OUVERT, et c'est le montage qui a d'abord menti.**
Avec un ennemi SEUL, son attaque termine sa team ⇒ `EndTurn` + `StartTurn` s'enchaînent dans le même
`applyAction`, `On(0x17)` retire les 1551 et `On(0x12)` les re-pose TOUS. On lisait alors « l'effet
n'a pas été consommé » — mesure du 2026-08-12 : les **deux** instances remplacées (`effectId`
111→114 et 112→115), alors qu'un témoin à deux lectures sans action montrait l'`effectId` STABLE.
Un second ennemi EXILÉ garde le tour ouvert ; `currentPlayer` inchangé est ASSERTIONNÉ, et le
retrait devient visible : `115 -> None` sur la cible, `116 -> 116` sur le porteur.

### LivingLightning — trois régimes, et un tirage MT qui manquait

| régime | distance de l'ennemi à la destination | live | port | tirages MT |
|---|---|---|---|---|
| `adjacent` | 1 | −3967 | −4546 | 6 / 6 |
| `range2` | 2 (branche que l'i2 tait) | −3693 | −3693 | 6 / 6 |
| `none` | ≥ 3 | rien | rien | 0 / 0 |

**LE POINT DU CAS.** Avant correction, le régime `adjacent` rendait **6 tirages live contre 5 côté
port** et un dégât divergent À CIBLE IDENTIQUE. La cause n'est pas une magnitude : le natif appelle
`GetPossibleTargets` **DEUX FOIS** — une dans l'`AmountIsZero` du `CreateTrigger`, une dans le
`CreateBehaviour` — et `PickRandomAmountSelector$$Select` **TIRE même sur un pool qui tient déjà
dans `amount`**. Un `matches` qui n'évaluait que le POOL rendait la même valeur de vérité et
laissait le flux MT en retard d'un cran. Le gate évalue donc désormais le `PickRandomly` : **6/6
tirages**, et le régime `range2` est **BIT-EXACT**.

C'est la décomposition par étage qui l'a donné — le compteur `mti` de `dumpRng` avant/après —, pas
un ajustement de scalaire.

---

## 6. Ce qui n'est PAS couvert

  * **`#961-r1`** — à **distance 1**, le dégât diverge d'un facteur **CONSTANT** : le natif rend
    **87,27 %** de ce que rend le port (3967/4546 et 5951/6819, deux configurations d'élévation
    différentes, ratio identique à 5·10⁻⁵ près), alors que la CIBLE et le NOMBRE DE TIRAGES
    concordent, et que la distance 2 est bit-exacte. Étage NON localisé ; l'hypothèse
    « classification mêlée/ranged » est **RÉFUTÉE** (forcer `is_melee=True` ne change rien) et
    l'hypothèse « élévation » aussi (le ratio est le même que le bonus s'applique ou non).
  * **`#961-r2`** — `necroPlasmancer` est l'UNIQUE entrée d'`rl_collect_batch.UNSPAWNABLE_FALLBACK`.
    RE-MESURE (`probe_961_plasmancer_spawn.py`) : **il SPAWNE** sur ce build — la liste héritée est
    PÉRIMÉE. Elle n'est pas modifiée ici : c'est le substrat de TOUT roster tiré au hasard, et un
    porteur qui entre au pool change les builds seedés de tous les tests.
  * **la MAGNITUDE de 1551** (`ConfigVar(dmgReduction) × mult`, canal `flat_reductions`) n'est pas
    confrontée : le montage mesure QUI est couvert et QUAND la charge part, pas de combien le dégât
    baisse. Le résidu `#961-r1` doit être fermé d'abord — confronter une magnitude sur un vecteur
    dont le dégât diverge déjà ne prouverait rien.
  * **`IsUnit(Caster@+0x48)` de la face DÉGÂT** : TAUTOLOGIQUE sur le canal
    `create_effect_damage_malus_for_defense` du port (seul le pipeline d'attaque le parcourt). Le
    régime discriminant — un dégât de TUILE/ENVIRONNEMENT reçu par un porteur de 1551 — n'est pas
    atteignable dans un duel sans board à effets de tuile. Le même nœud EST porté explicitement sur
    le trigger de retrait, où l'acteur est connu.
  * **l'effet 1020 `LivingLightning_MoveEffect`** est posé et retiré fidèlement mais n'a AUCUN
    lecteur : son unique consommateur natif est `IdunBattle.View.AbilityConfigs.Loki.
    LivingLightningVisuals`. Non confronté live (la fenêtre `PreUnitMove` → `ArrivedAtFinalTile` est
    intérieure à une seule opération, donc invisible d'un snapshot).
  * **`IdunBattle.AI.Playbook.Loki.TimesplinterMantlePlaybook`** (face DÉCISION, 3 corps propres) —
    hors périmètre. La face NON-OWNER est déjà portée.
  * `selectionType = 2` du 8ᵉ argument d'`AttackWithAttackDamage` : le nœud porté ne l'expose pas
    (foyer partagé).
  * `MechanicalUnits` côté port ignore son `selection_type` (foyer partagé, hors tranche).
  * `Damageable` côté port filtre `alive & hp > 0` là où le natif fait
    `UnitsWithoutTrait(Invincible, sel: 3)` — écart PRÉEXISTANT du nœud partagé, pas introduit ici.

## 7. La recette d'injection SE GÉNÉRALISE

`necroChronomancer` est l'une des 21 unités `lineup` absentes du catalogue `BC.Units` :
`catalog_inject.write_augmented_seed_bc(<out>, ["necroChronomancer"])` puis
`rl_duel build --seed-bc <out>` le fait entrer au pool (**97 → 98**). Aucun piège spécifique aux
Necrons : `catalog_inject` pose l'unité ET ses configs d'ability (`Chronometron`,
`TimesplinterMantle`), ce qui est exactement ce qui manque pour éviter le « system error » au
déploiement d'un passif. Les DEUX autres passifs de factions voisines cités au brief passeront par
le même montage, avec pour seule question préalable : « le porteur est-il dans les 21, ou seulement
hors pool ? » — `python catalog_inject.py --missing` répond.

**Le cas `necroPlasmancer` est DIFFÉRENT et il faut savoir le distinguer** : il est AU catalogue et
il PASSE la normalisation ; ce qui l'écartait est une **liste écrite** (`UNSPAWNABLE_FALLBACK`), pas
une limite du jeu. Un « hors pool » se ventile donc en trois causes — absent du catalogue (injecter),
recalé par la formule de stats (rank / `--explicit-stats`), ou **listé** — et seule la troisième
demande de re-mesurer avant de conclure quoi que ce soit.
