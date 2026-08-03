# case-448-r1 — `StormboyzStrike_FallbackAbility`, `_MissAbility` et l'effet `1179 _AlreadyUsedTile`

Résidu nommé en §7.2/§7.5 de `docs/rl/case-366-r1-tunneling-horror-pending-summon.md` (PR #448).
Build `rnca9r7q6c`.

> **PORTÉ + CONFRONTÉ LIVE (2026-08-03).** Les deux abilities sont au registre, l'accord avec le
> natif est **bit-exact sur le flux PRNG**, sur deux bras. Sur les quatre « pièces natives
> manquantes » que cette fiche annonçait, **deux n'étaient pas à écrire** (l'une périmée, l'autre
> inexistante — un ctor dédupliqué mal lu) ; la confrontation en a trouvé **une cinquième, qu'on ne
> cherchait pas** : un gate manquant de `TriggerAbility`, invisible sur tout observable d'état. Tout
> le détail : **§6 à §8**.

L'inventaire annonçait trois items indépendants. Le décompilé en fait **un seul mécanisme** : les
trois classes triggered partagent le même `TriggeredAbilityType`, et `1179` est le lien entre elles.

## 1. Les TROIS classes sont UNE seule ability — mesure, pas hypothèse

`TriggeredAbilityType` ne contient **qu'un** `StormboyzStrike` (**1141**), et
`IdunBattle.Core.Services.AbilitiesDatabase$$InitializeTriggeredAbilities` n'a **qu'une** entrée
pour `0x475`. Son builder — `AbilitiesDatabase.u003Cu003Ec$$u003CInitializeTriggeredAbilitiesu003Eb__28_134`,
identifié par l'offset de son champ de cache `<>9__28_N` — construit une `List` de **TROIS**
instances, là où le builder voisin de `FullThrottle` (`b__28_137`) n'en construit qu'une.

⇒ **greffer le passif `StormboyzStrike` monte les trois d'un coup.** La confrontabilité de tout le
kit est donc celle, déjà acquise, de #366-r1 §7.3 : porteur unique `orksNpc6Stormboy` (**npc**, trait
`Flying`), aucun summoner ⇒ recours 3 de `case-92` §5bis, `catalog_inject.graft_passive_ability`.
Condition vérifiée : `gameconfig.ability("StormboyzStrike")` n'a **aucune variable**, sa seule
constante `chance = 20` n'est lue que par `_MissAbility`, et ni trigger ni behaviour ne lisent stat,
trait ou arme du caster.

## 2. `StormboyzStrike_FallbackAbility` — le filet « fin de tour encore hors plateau »

    $$CreateTrigger  = On(0x28 = UnitFinishedTurn) & get_OwnerIsActor
                     & HasEffect( Owner@Sel+0x30, 0x474, onlyActive: false, targetType: 6 )

    $$CreateBehaviour = MoveUnitBehaviour( Caster@Sel+0x48,
                            First( SortTilesByUtility( CanAddUnit(<Sel+0x18>), Caster@Sel+0x48,
                                                       UtilityDefinition(6), null ), Direct(1) ),
                            <options 0x40 octets à ZÉRO> )
                      & AddEffect( 0x49b = 1179, AbilityStateReference,
                                   targets: <la tuile choisie>, turns: Nullable<int>(1) )
                      & PerformAIMovementBehaviour(
                            AmountIsEqual( Tiles(Caster@Sel+0x48), <DSLFormulas+0x18> = Direct(0) ),
                            RemoveEffect(Owner@Sel+0x30, Nullable(0x474)) & Kill(Caster, ForDirectKill),
                            null )

Deux slots lus, pas devinés :

* **`<Sel+0x18>` = `IdunBattle.Entities.Selectors.AllTilesSelector`** —
  `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` l'y écrit NOMMÉMENT (seul slot dont le
  ctor n'est pas mislabellé). Le pool est donc le **plateau entier**, pas un voisinage.
* **`UtilityDefinition(6)` = `UtilityType.UnitMovement`** — tranché par **XREF ENTRANTE**, pas à
  l'œil : `$$CreateBehaviour` appelle la surcharge `UtilityDefinition..ctor(this, utilityType)`, la
  même que `DSLSelectors$$SortTilesByUtility` utilise pour envelopper son argument `int`. (Les deux
  autres surcharges — `(bucket)` et `(utility)` — ont des appelants disjoints.)

C'est **le même score que l'IA emploie pour choisir où se déplacer**, et `TileEffects` en est une
feuille : voilà par où `1179` mord (§4).

`turns: Nullable<int>(1)` = une durée **déjà en TOURS** (surcharge `turns` de
`DSLBehaviors$$AddEffect` → `Direct(n)` rangé tel quel), pas un `TurnsFromRounds`.

## 3. `StormboyzStrike_MissAbility` — les 20 % de rater son hex

    $$CreateTrigger  = On(0x1f = PreUnitMove) & get_OwnerIsActor
                     & HasEffect( Owner@Sel+0x30, 0x474, onlyActive: false, targetType: 6 )

    $$CreateBehaviour = Inform( { 0x79 : EntityId(<Sel+0x78>) } )
                      & If( Maybe( GetNumberConstant(0x2a = 'chance') ),
                            OverrideUnitMovementTarget( Owner@Sel+0x30,
                                PickRandomly( CanAddUnit( AdjacentTiles(<Sel+0x78>) ),
                                              1, null, 0x7fffffff, false ) ),
                            null )
                      & RemoveEffect( Caster@Sel+0x48, Nullable(0x474), null )
                      & TriggerAbility( Caster@Sel+0x48, 0x46e, Caster, Caster, null, null, 3, … )

* `<Sel+0x78>` = **les tuiles de DESTINATION** du mouvement — le même slot que
  `HatefulAssaultAbility$$CreateTrigger` compare à la tuile courante, déjà établi côté port
  (`TriggerEvent.dest_tile`).
* `0x46e` = **`TriggeredAbilityType.FullThrottle` (1134)** — c'est mot pour mot le « This fly-in
  counts as a movement for *Full Throttle* » de l'i2, et le porteur natif porte bien les deux
  passifs (`orksNpc6Stormboy.passiveAbilities = ['StormboyzStrike', 'FullThrottle']`).
* `Inform{0x79: …}` est un canal de **VUE** : `StormboyzStrikeVisuals$$GetFinalTile` lit
  `GetStepMessage(0x25)` puis, à défaut, `GetInfoMessage(0)`, et en extrait la clé `0x79`. Le
  `0x25`/`0x79` est aussi ce qu'émet `OverrideMovementTargetOperation$$Execute` — les deux voies
  alimentent le même affichage.

**Ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE`** pour l'une comme pour l'autre : ce sont des
`BaseTriggeredAbility`, elles ne traversent jamais `ActiveAbilityOperation` (même lecture que #448
pour 1141).

## 4. `1179 StormboyzStrike_AlreadyUsedTile` — qui le LIT, et pour quoi

### 4.1 Aucun lecteur par IMMÉDIAT — recensement exhaustif

Désassemblage capstone linéaire des **154 176** fonctions de `data/symbols/rnca9r7q6c/ghidra/functions.tsv` :
**7** instructions dans tout `GameAssembly.dll` portent `0x49b`.

| site | rôle |
|---|---|
| `…StormboyzStrike_FallbackAbility$$CreateBehaviour` | **le POSEUR** |
| `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` | l'ENREGISTREMENT |
| `…AbilitiesDatabase$$InitializeActiveAbilities`, `…AI.Playbook.Loki.CultDemagoguePlaybook$$.ctor`, `…AI.PlaybookDatabase$$InitializePlaybookBuilders` | homonymes `ActiveAbilityType.CultDemagogue` |
| `…AbilitiesDatabase$$InitializeTriggeredAbilities`, `…Effects.Loki.PsychicStalk_VisualEffectEffect$$.ctor` | homonymes `TriggeredAbilityType.PsychicStalk` |

⇒ **zéro lecteur de l'`EffectType` 1179 par immédiat.**

⚠ **Le piège de méthode, vécu ici.** Une recherche d'OCTETS + heuristique d'opcode rate la forme
`mov dword ptr [rbp+disp32], imm32` — et c'est exactement sous cette forme qu'est écrit
l'enregistrement dans `InitializeEffects`. L'heuristique concluait « 1179 n'est même pas
enregistré », ce qui est **faux**. Ne recenser un immédiat qu'au **désassembleur**.

### 4.2 Aucune contribution de COMBAT

`InitializeEffects` associe `1179` au builder `EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_197`
(identifié par son cache `<>9__14_N`, N = (0x630−8)/8 = 197 ; contrôle : `b__14_139` rend bien le
`TunnelingHorror_PendingSummonEffect` de #366-r1). Ce builder construit un
**`IdunBattle.Entities.Effects.NoneEffect`** — la classe même que `EffectsDatabase$$GetEffect`
fabrique en dernier recours pour un type inconnu. `classes.tsv` ne contient **aucune** classe
`*AlreadyUsedTile*`. L'effet est donc **INERTE côté combat, par construction et volontairement**.

### 4.3 LE lecteur : le poids IA, par NOM

    BC.Utilities.Default.TileEffects["StormboyzStrike_AlreadyUsedTile"] = -100

`IdunBattle.AI.Utilities.TileEffectsUtility` (`UtilityType.TileEffects = 10`) fait, pour chaque effet
de la tuile, `Enum.ToString(effectType)` → `HasUtilityValue(name)` → `GetUtilityValue(name)`. La
lecture est **générique par nom** : c'est pourquoi aucun immédiat n'apparaît.

**−100 est le poids le plus négatif de toute la catégorie** (20 clés ; les marqueurs de
pending-attack sont à −40, Fire/Ice/SpiderWeb à −25). Et `TileEffects` est une feuille du bucket
`UtilityType.UnitMovement` — celui-là même que le Fallback interroge (§2). Le marqueur, posé **1
tour**, écarte donc la tuile pour les Stormboyz suivants du même tour : deux d'entre eux ne
retombent pas au même endroit.

### 4.4 Le multiplicateur de durée ne l'atteint pas

`TileEffectsUtility.<EvaluateMovementInSteps>d__1$$MoveNext` ne multiplie un poids par
`$$GetStatusEffectMultiplier` que si `StaticBattleRules.Effect$$IsTileStatusEffect(type)`. Cet
`OrderedSet` est peuplé par immédiats dans le `.cctor` et vaut **{5 Fire, 17 Ice, 58 Darkness,
1244 Contaminated, 1476 DespoiledGround}**. `1179` n'y est pas ⇒ **poids brut** ⇒ la limite
« multiplicateur non porté » du docstring de `engine/utilities/tile.py` est **INERTE ici**.

### 4.5 État du port : déjà fidèle — mais le canal ne l'alimente pas

`engine/utilities/tile.py::TileEffectsUtility` lit déjà la clé génériquement et rend **−100.0**
(mesuré). **Rien à corriger** ; c'est désormais VERROUILLÉ par
`tests/engine/test_448_r1_already_used_tile_offline.py` (6 gardes, dont le contre-bras « tuile non
marquée → 0 » et la domination du poids dans sa catégorie).

Le poids est **atteignable** par le port : `engine/ai/context.py` seede `effects_by_pos` depuis le
RPC `tileMeta`, et `tileMeta` publie bien cet effet.

> ⚠ **Cet alinéa portait un « RÉSIDU DE CANAL » — il est RÉFUTÉ (#425).** Il concluait de la mesure
> du §5 que `tileMeta` ne publiait pas l'effet, donc que le −100 était « inatteignable en pratique »
> et qu'un capteur restait à poser (voie `targetIds`, reinject requis). **Aucun étage de code
> n'était en cause** : capteur, décodeur, transport RPC et ingestion sont sains. La cause était le
> MONTAGE — un roster allié d'UNE unité, dont le `finish` clôture le tour d'équipe et consomme la
> marque `turns: 1` dans le même `applyAction`. Avec un allié, `tileMeta` publie
> `(0,3) → 1179, remaining=1`. Mesure, contre-épreuve et gardes :
> **`docs/rl/case-425-canal-effet-de-tuile.md`**.

## 5. La mesure live — `probe_448_r1_stormboyz_fallback_miss.py`

Montage : greffe de `StormboyzStrike` sur `orksNob`, board `MC1_67`, seed 777, rank 17, un adversaire
— **et un ALLIÉ, obligatoire (#425)** : avec le seul porteur, son `finish` clôture le tour d'équipe et
la marque `turns: 1` est consommée dans le même `applyAction`.

**Volet A (offline)** re-dérive les §4.1 à §4.5 sans session.

**Volet B (live)** — `applyAction {kind:"finish"}` sur le porteur, qui émet `On(0x28 UnitFinishedTurn)` :

| | avant | après |
|---|---|---|
| `pos` du porteur | `null` (hors plateau) | **(1,3)** |
| effet `1140` | `remaining = 2` | **absent** |
| présence dans `observeBattle.units` | **non** | oui |
| entités `EntityType.Effect` | 20 | **21** |
| tuiles marquées `1179` (`tileMeta`, `includeInactive`) | aucune | **(0,3), `remaining=1`** |
| owner de l'entité `1179` (`effectAbilityStates.source`) | — | **15 = la tuile (0,3)** |

⇒ **le Fallback a firé** (rien d'autre ne repose sur une tuile une unité hors plateau au
`UnitFinishedTurn`), **une entité Effect a été créée**, et **elle marque une tuile**.

⚠ **La tuile marquée (0,3) n'est PAS la tuile d'atterrissage (1,3)** — quirk natif établi par #425 :
`MoveUnitBehaviour` et `AddEffect` partagent le MÊME objet-nœud sélecteur, mais `&` les exécute EN
SÉQUENCE, donc à la ré-évaluation le caster occupe déjà la meilleure tuile et `CanAddUnit` l'exclut.
La ligne B3 de l'en-tête de ce probe affirmait l'inverse ; elle était **fausse** et n'avait jamais
été confrontée (les deux colonnes rendaient « aucune »).

Le retrait de `1140`, lui, ne vient PAS du `RemoveEffect` du Fallback — celui-ci est
sous le gate `Tiles(Caster) == 0`, faux ici : il vient du 3ᵉ trigger propre de
`ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal` (`On(0x28) & OwnerIsActor & HasTile(Owner)`),
qui devient vrai dès que le `MoveUnitBehaviour` a redonné une tuile au porteur. Les deux lectures se
recoupent exactement.

> Ce trigger est le T3 de **`#448-r2b`** (`docs/rl/case-448-r2-ateleporting-effect-family.md`), qui
> le note NON PORTÉ pour `1140` et relève que ce régime est **le seul qui exerce son gate
> `HasTile(Owner)`**. La mesure ci-dessus le montre en action : c'est exactement le pas où
> le porteur repasse de « sans tuile » à « sur (1,3) ».

**Trois pièges de canal, mesurés, à ne pas relire comme des trous de moteur** :
1. le porteur sous `1140` est **absent d'`observeBattle.units[]`** ;
2. dans `decisionView` il sort avec `visualId`, `team` ET `pos` à `null` — on ne peut pas le
   retrouver par son `visualId`, seulement par `pos is None` ;
3. `tileMeta` ne publie **pas** d'id d'entité de tuile (`boardGraph.tiles[].id` le porte).

**TRANCHÉ depuis #425** : le `+1` d'entité Effect est **nominatif**, et l'arbitre n'est pas
`dumpEntityComponents` (qui rend la STRUCTURE, pas les VALEURS) mais **`effectAbilityStates`** — il
balaie toutes les entités `EntityType.Effect` sans filtre d'appartenance et publie
`{effectId, effectType, name, source, active}`. Comme la surcharge
`IdunBattleLogic.Entities.DSLBehaviors$$AddEffect(effectType, abilityState, targets, turns)` passe
`source = NULL`, `AddEffectBehaviour$$Execute` retombe sur la cible et **`SourceUnitId == OwnerId`** :
`source` désigne donc directement l'entité-tuile marquée.

## 6. LE PORT — les quatre « pièces manquantes », dont DEUX n'existaient pas

L'inventaire de cette fiche annonçait quatre pièces natives à mirrorer. Le décompilé en invalide
**deux**, et c'est la partie la plus utile de la tranche :

| pièce annoncée | verdict, après lecture |
|---|---|
| vecteur `On(0x28 = UnitFinishedTurn)` | **PÉRIMÉ** — il est émis depuis #448-r2 (`dispatch/turn.py::unit_finished_turn_triggers`, appelé par `turnflow.py` sous son gate natif). La fiche datait d'avant. |
| `PerformAIMovementBehaviour$$Execute` | **N'EXISTE PAS dans ce kit** — cf. §6.1. |
| `OverrideMovementTargetOperation$$Execute` | **VRAIE pièce**, portée — cf. §6.2. |
| `TriggeredAbilityType.FullThrottle` (1134) | **VRAIE pièce**, son `CreateBehaviour` est porté ; son `CreateTrigger` reste un résidu NOMMÉ — cf. §6.3. |

### 6.1 Le 3ᵉ terme du Fallback est un `IfBehaviour`, pas un `PerformAIMovementBehaviour`

La classe allouée par `StormboyzStrike_FallbackAbility$$CreateBehaviour` est **celle qu'alloue
`IdunBattleLogic.Entities.DSLBehaviors$$If`** — identité tranchée par les **XREFS du cache de
classe** (les quatre lectures du même cache viennent de `DSLBehaviors$$If` ×3 et de ce
`CreateBehaviour`), jamais à l'œil. Et `IdunBattle.Entities.Behaviours.IfBehaviour$$Execute` lit
exactement les trois champs que le ctor pose : `+0x50` la condition (via `ShouldTrigger`), `+0x58`
la branche VRAIE, `+0x60` la branche FAUSSE — résultat VIDE si elle est nulle.

Le `$$.ctor` que les tables nomment `PerformAIMovementBehaviour$$.ctor` est un **corps DÉDUPLIQUÉ**
(trois champs `+0x50/+0x58/+0x60`), et ses noms de paramètres — `unit, range, overrideUtility` — ne
collent à AUCUN des arguments passés ici (un trigger, un behaviour, `null`). Le VRAI
`PerformAIMovementBehaviour$$Execute` lit CINQ champs (`+0x50` sélecteur d'unités, `+0x58` formule,
`+0x68`, `+0x70` délégué, et **écrit** `+0x60`) : il n'a rien à voir avec ce call-site.

⇒ le nœud est un `If`, déjà porté. **Une des quatre pièces annoncées n'était pas à écrire.**

### 6.2 `OverrideMovementTargetOperation` — et son lecteur, qui est `MoveUnitOperation` lui-même

L'Operation écrit `Nullable<UnitPositionId>` à `+0xa8` du composant qu'elle récupère par la MÊME
paire de caches que `MoveUnitOperation$$Execute` — c'est un canal in/out d'**une seule** Operation,
dont voici la boucle complète (lue verbatim) :

    MoveUnitOperation$$Execute :
        comp.<+0xa8> = Nullable(UnitPositionId(position))     # POSE, avant tout
        SetReservation(unit, position)
        if (!options.skipPreMoveTriggers)  {                  # l'octet +0x12
            publish On(0x1f = PreUnitMove)                    # <- un trigger peut ECRASER le champ
            if (!TilesAreEmpty(unit, position)) { RemoveReservation ; return }
        }
        ovr = comp.<+0xa8> ; comp.<+0xa8> = null              # RELECTURE + CONSOMMATION
        if (!ovr.HasValue || IsDead(unit)) { RemoveReservation ; return }
        if (ovr.Value.ToUnitPosition() != position) {
            RemoveReservation(position) ; options.skipPreMoveTriggers = true
            return Execute(unit, <la nouvelle position>, trig, options)     # RELANCE
        }
        ... suite normale ...

Trois lectures load-bearing : le champ est posé **par l'Operation de mouvement elle-même** (donc
`HasValue` est vrai même sans override) ; la relance porte `skipPreMoveTriggers = true`, ce qui
**borne la récursion à un niveau par trigger déviant** ; et le second bras du gate — `IsDead(unit)`
— n'est pas théorique, puisque le Miss finit par `TriggerAbility(FullThrottle)` → `Kill(Caster)`.

Porté : `UnitComponent.movement_target_override`, `OverrideMovementTargetOperation` (`operations/
movement.py`), la feuille DSL `OverrideUnitMovementTarget` (`behaviours/movement.py`) et la boucle
ci-dessus dans `MoveUnitOperation.execute`.
**NON porté, résidu NOMMÉ** : le gate `TilesAreEmpty` entre (b) et (c) — le port n'a ni réservation
ni abandon de mouvement. Il mordrait si un trigger `PreUnitMove` faisait OCCUPER la tuile d'arrivée,
ce qu'aucun consommateur porté ne fait.

### 6.3 `FullThrottle` (1134) — le `CreateBehaviour` porté, le `CreateTrigger` non

    $$CreateTrigger   = On(0x24) & get_OwnerIsActor
                      & AmountIsEqualOrGreater( MovementSteps(),
                                                Direct(GetNumberConstant(0x51 = 'movement')) )
    $$CreateBehaviour = If( Maybe(GetNumberConstant(0x2a = 'chance')),
                            Kill(Caster, Caster, ForDirectKill), null )

Les deux constantes sortent du gameconfig sans ambiguïté (`FullThrottle.constants =
{movement: 3, chance: 30}`). Le `CreateBehaviour` est porté comme entrée de
`TRIGGERED_ABILITY_BEHAVIOURS[1134]`, parce que c'est EXACTEMENT la face que le Miss exerce : son
dernier terme est `TriggerAbility(Caster, 0x46e)`, et `TriggerTriggeredAbilityOperation$$
TriggerAbility` va **directement** au slot `Execute` de l'ability déclenchée (`triggerType = 0x20 =
Custom`) **sans jamais évaluer son `ShouldTrigger`**.

Le `CreateTrigger` (le passif autonome) reste **NON PORTÉ**, avec sa cause exacte :
`IdunBattleLogic.Entities.DSLFormulas$$MovementSteps()` alloue une classe dont le `.ctor` ne prend
QU'UN argument (un champ mis à `0`) et dont **aucun nom n'apparaît dans les tables** — ce n'est ni
`TilesMovedThisTurnFormula` ni `TilesMovedLastTurnFormula` (leurs `DSLFormulas$$TilesMoved*Turn`
allouent des classes DIFFÉRENTES, avec un ctor à DEUX arguments dont un sélecteur d'unité), et la
seule xref de son cache de classe est `MovementSteps` elle-même. Il faudrait lire son slot
`Calculate` au RUNTIME. Supposer « les tuiles parcourues ce tour » serait une invention ; supposer
le gate toujours vrai tuerait 30 % des Stormboyz à chaque pas.
⇒ **Rayon de souffle nul** : `unit_map find --ability FullThrottle` rend **1** unité,
`orksNpc6Stormboy` (npc, voie `passive`) — le même et unique porteur que `StormboyzStrike`.

### 6.4 CE QUE LA MESURE A TROUVÉ — un gate manquant de `TriggerAbility`, invisible autrement

La confrontation du flux PRNG (§8) a rendu **PORT 3 tirages, NATIF 2**, alors que *tous* les
observables d'état concordaient : même tuile d'atterrissage, même tuile marquée, mêmes PV.

Cause, lue dans `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` :

    abilityState = ignoreUnitHavingAbility ? new Nullable<AbilityState>(default)
                                           : UnitExtensions.GetAbilityState(entity);
    if (abilityState.HasValue) { ... Execute(...) ... }

Le nom du paramètre le dit : **`ignoreUnitHavingAbility`**, et les DEUX call-sites portés le passent
à `false`. Une cible qui ne PORTE pas l'ability ne voit donc rien s'exécuter — **et ne consomme
aucun tirage**. Or le porteur greffé n'a que `passiveAbilities = [1141]` (la greffe REMPLACE la
liste) : il ne porte pas `FullThrottle`, et le port tirait son `Maybe(chance = 30)` pour rien.

Le gate porte sur l'**exécution**, pas sur la résolution du sélecteur : côté natif la liste
`targets` est déjà résolue par `TriggerAbilityBehaviour$$Execute` avant l'appel de l'Operation. Le
port publie donc `targets` inchangé et journalise à part les cibles écartées (`notCarrying`).
**Rayon de souffle mesuré : NUL** — `TRIGGERED_ABILITY_BEHAVIOURS` était VIDE avant cette tranche,
donc la boucle des autres call-sites (`BattleFatigue`, `SwornProtector_Protect`, …) était déjà un
no-op ; `test_cosmic_horror_live`, `test_black_legion_1029_1020_live` et
`test_fear_of_the_unseen_live` rejoués VERTS.

### 6.5 Deux dépendances qu'il a fallu ouvrir

* **`UTILITY_BY_TYPE[6 = UnitMovement]`** n'existait pas (le Fallback est le premier call-site porté
  à demander `UtilityDefinition(6)`). Sur ce chemin le composite **VAUT `Tile(7)`** : la feuille
  `MinDistanceToClosestEnemy(17)` y est court-circuitée par son **gate 3**, lu verbatim des deux
  côtés — la lambda `SortTilesByUtilitySelector.<>c__DisplayClass8_0$$<Select>b__1` construit
  `new UtilityMovementCase(dc.unit, _tile, closestEnemy: NULL, abilityType: NULL, dc.parent, NULL)`
  (le 3ᵉ argument est littéralement `0`, et le ctor nommé le range en `case+0x20`), et
  `MinDistanceToClosestEnemyUtility.<EvaluateMovementInSteps>d__2$$MoveNext` rend `Fix64.FromInt(0)`
  dès que `case.<+0x20> == null`. Ce n'est donc PAS une approximation.
* **`UnitContext` levait un `TypeError`** sur `int(oc.player)` : une unité hors plateau sous un
  `ATeleportingEffect` sort de `decisionView` avec `visualId`, `team` ET `pos` à `null`. La ligne
  au-dessus décrivait pourtant déjà ce cas (« clé ABSENTE si le propriétaire n'est pas connu ») —
  la garde manquait.

### 6.6 Le nœud `SortTilesByUtility` devait être un VRAI nœud

Les call-sites portés jusqu'ici collapsaient `First(SortTilesByUtility(...), 1)` en un helper
impératif (`first_tile_by_utility`) parce que leur résultat n'était consommé qu'une fois. Le
Fallback ne le peut pas : il passe **le MÊME objet-nœud** à `MoveUnitBehaviour` ET à `AddEffect`, et
l'`op_BitwiseAnd` les exécute EN SÉQUENCE — d'où le quirk §4 (la tuile marquée n'est pas celle
d'atterrissage). Un collapse le perdrait, silencieusement. D'où le nœud
`entities/selectors/tiles.py::SortTilesByUtility`, qui délègue au foyer unique par l'accesseur
`ctx.sort_tiles_by_utility` (aucun second port du calcul d'utilité).

⚠ **`First(source, Direct(1))` est un COUNT, pas un index.** Le paramètre natif s'appelle `amount` ;
la surcharge `int` de `DSLSelectors$$First` construit `Direct(amount)` et délègue à la surcharge
objet, qui alloue un `PickFirstNSelector` (« les `amount` premiers »). `PickAtIndexSelector` est une
classe DISTINCTE, d'une autre factory. Côté port : `PickFirstN`, pas `First`.

## 7. Confrontation LIVE — accord BIT-EXACT, sur DEUX bras

`tests/engine/runner/test_448_r1_stormboyz_port_live.py` — montage de #425 (greffe sur `orksNob`,
board `MC1_67`, seed 777, **un allié obligatoire**), un `applyAction {kind:"finish"}` sur le porteur,
et le MÊME pas rejoué côté port depuis l'état d'AVANT, **PRNG aligné par `dumpRng`**.

| garde | ce qu'elle confronte | mesure |
|---|---|---|
| L1 | tuile d'ATTERRISSAGE | port == natif |
| L2 | tuile MARQUÉE `1179` | port == natif |
| L3 | quirk §4, **des DEUX côtés** | marquée ≠ atterrissage |
| L4 | retrait de `1140` | absent des deux côtés |
| L5 | flux PRNG (`mti` **et** `mt`) | **2 tirages == 2**, MT identique |
| L6 | gate `GetAbilityState`, ses DEUX bras | sans FullThrottle 2, **avec** 3 — natif comme port |

Le pas mesuré fait travailler tout le kit d'un coup : `On(0x28)` → Fallback → `MoveUnit` →
`On(0x1f)` → Miss → `Maybe(20)` → `OverrideUnitMovementTarget` → relance du mouvement →
`RemoveEffect(1140)` → `TriggerAbility(FullThrottle)`, puis `AddEffect(1179)` sur le nœud
ré-évalué. Les deux tirages du bras 1 sont `Maybe(20) = True` (le miss PASSE) puis
`PickRandomly(0, 4)`.

**Contre-épreuves obtenues par MESURE, pas par construction** — trois rouges réels pendant la mise
au point : sans le gate `GetAbilityState`, L5 rouge (3 vs 2) ; sans `UTILITY_BY_TYPE[6]`, `KeyError`
sur tout le vecteur ; sans la garde `oc.player is not None`, `TypeError` au chargement d'état.
Le bras L6 est une **généralisation** (second seed BC, `replace=False`), pas une mutation : il
exerce le bras « la cible PORTE l'ability », que le bras 1 ne peut pas atteindre.

## 8. Ce qui reste NON COUVERT

* `FullThrottle$$CreateTrigger` — cf. §6.3 (`MovementSteps` non résolue offline). Le passif autonome
  est INERTE côté port ; seul son déclenchement par le Miss est porté.
* Le gate `TilesAreEmpty` de `MoveUnitOperation` — cf. §6.2.
* La branche `Kill` du Fallback (`Count(Tiles(Caster)) == 0`) n'est **pas exercée LIVE** : elle
  demande un plateau où AUCUNE tuile n'est libre. Elle est gardée offline (O6, les trois gates de
  `KillUnitBehaviour` + l'idempotence) et sa feuille est le mirror du foyer de mort déjà validé.
* Le canal de VUE (`Inform{0x79}`, step `0x25`, clés `0x79/0x7a/0x7b`) — le runner n'a pas de flux
  de vue, comme partout ailleurs dans `operations/`.
* L'override sur une unité MULTI-PIEDS : `UnitPositionId` en porte jusqu'à trois, le port ne
  matérialise que la main tile. Aucun call-site du build n'est dans ce cas.

## 9. Reproduction

    python scripts/python/probe_448_r1_stormboyz_fallback_miss.py            # volet A (offline)
    python scripts/python/probe_448_r1_stormboyz_fallback_miss.py --live     # A + B (1 runner)
    python -m pytest scripts/python/tests/engine/test_448_r1_already_used_tile_offline.py
    python -m pytest scripts/python/tests/engine/test_448_r1_stormboyz_port_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_425_tile_effect_channel_live.py
    python -m pytest scripts/python/tests/engine/runner/test_448_r1_stormboyz_port_live.py
