# case-448-r1 — `StormboyzStrike_FallbackAbility`, `_MissAbility` et l'effet `1179 _AlreadyUsedTile`

Résidu nommé en §7.2/§7.5 de `docs/rl/case-366-r1-tunneling-horror-pending-summon.md` (PR #448).
Build `rnca9r7q6c`.

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

## 6. Ce qui N'EST PAS porté — résidus nommés

Les deux abilities restent **NON PORTÉES**, et ce n'est pas faute de porteur : la greffe les monte
(§1). Ce qui manque est **nommé, et c'est du natif à mirrorer**, pas de la spéculation :

| pièce native manquante | ce qu'elle fait | conséquence |
|---|---|---|
| vecteur `On(0x28 = UnitFinishedTurn)` | non émis par le port (`triggers/dispatch/turn.py` n'émet que `On(0x29 UnitFinishedTurnNormally)`, et le dit) | le trigger du Fallback n'a pas d'entrée |
| `IdunBattle.Entities.Behaviours.PerformAIMovementBehaviour$$Execute` | évalue une condition, sélectionne une cible, puis appelle le vslot `+0x36` du processor par unité | 3ᵉ étage du Fallback |
| `IdunBattle.Operations.OverrideMovementTargetOperation$$Execute` | écrit `Nullable<UnitPositionId>` dans **`UnitComponent @+0xa8`** (un TROISIÈME slot, distinct des `+0x88`/`+0x98` de #366-r1) + un step de vue `0x25` | le « miss » du Miss |
| `TriggeredAbilityType.FullThrottle` (1134) | seule l'entrée d'enum existe côté port | le `TriggerAbility` final du Miss serait un no-op |

Porter l'un de ces étages à moitié produirait exactement la dégradation **silencieuse** que la
doctrine proscrit — un mouvement qui « marche » sans jamais dévier, ou un fallback qui repose
l'unité sans marquer sa tuile.

## 7. Reproduction

    python scripts/python/probe_448_r1_stormboyz_fallback_miss.py            # volet A (offline)
    python scripts/python/probe_448_r1_stormboyz_fallback_miss.py --live     # A + B (1 runner)
    python -m pytest scripts/python/tests/engine/test_448_r1_already_used_tile_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_425_tile_effect_channel_live.py
