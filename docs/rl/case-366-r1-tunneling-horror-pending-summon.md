# case-366-r1 — `1113 TunnelingHorror_PendingSummon` : PORTÉ (effet), vecteur de pose en RÉSIDU

Le marqueur que `TunnelingHorror` (`ActiveAbilityType` 0x3f3 = 1011, `necroSmnDestroyer`
« Ophydian Destroyer ») laisse **sur la tuile de destination** pendant que l'unité est sous terre.
i2 : « This unit may use tunnelling to move. It is then removed from the battlefield and emerges in
its chosen hex at the start of its next turn, pushing any unit in that hex aside. It is then able to
immediately attack any adjacent enemy in melee. »

L'inventaire du gisement l'annonçait « marqueur de summon pending ». Le corps natif dit plus que
ça : c'est un **bond dont les TROIS conditions de retrait automatique sont éteintes**, et c'est
exactement ce qui le distingue des 13 autres bonds du binaire.

## 1. L'artefact natif (build `rnca9r7q6c`)

### 1.1 La classe — et pourquoi Ghidra ment sur son parent

`IdunBattle.Entities.Effects.Loki.TunnelingHorror_PendingSummonEffect`, fabriquée par
`IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_139`
(unique appelant du `$$.ctor`).

Le `$$.ctor` appelle un corps que Ghidra nomme **`IdunBattle.Entities.Effects.BaseEffect$$.ctor`**.
C'est un **corps DÉDUPLIQUÉ** : la surcharge à 4 arguments d'`IdunBattle.Entities.Effects.ABondEffect`
est instruction pour instruction celle de la base, IL2CPP n'en garde qu'un exemplaire et la table
l'attribue à `BaseEffect`. Le parent RÉEL n'est lisible que dans la table VERSIONNÉE :

    data/symbols/rnca9r7q6c/frida/classes.tsv
    IdunBattle.Entities.Effects.Loki.TunnelingHorror_PendingSummonEffect  1152
        IdunBattle.Entities.Effects.ABondEffect

C'est la troisième forme du piège « le nom du `$$.ctor` ne fait pas l'identité » (#411 / #421 / #423) :
ici ce n'est pas la CLASSE qui est mal attribuée, c'est la **BASE**.

Arguments, lus à l'octet (`mov edx, 0x3f3` puis la surcharge d'`IdunBattle.Core.AbilityOrEffect$$op_Implicit`
qui appelle `IdunBattle.Core.AbilityOrEffect$$set_ActiveAbility` — donc `ActiveAbilityType`, pas
`EffectType` ni `TriggeredAbilityType`, tous trois ayant une surcharge homonyme) :

    .ctor() = ABondEffect( hasAutomaticActivation: true,
                           unitEffectType: 0,
                           sourceAbility: AbilityOrEffect(ActiveAbilityType.TunnelingHorror = 1011) )

### 1.2 Les trois surcharges — et ce qu'elles éteignent

La classe ne définit que **quatre** méthodes (bloc contigu de la table `methodPointers` du PE,
entre `TrophyTaker_ExtraCritDamageEffect` et `TwistedScience_ExtraDmgEffect`) : le `.ctor` et
**trois getters à corps trivial**. Les tables de symboles dédupliquent ces corps (`xor eax,eax ; ret`)
et ne les nomment donc pas — ils ont été relevés au RUNTIME par le RPC `resolveMethodPtr`
(lecture pure, aucun hook) :

| getter | corps | famille |
|---|---|---|
| `get_Adjacent` | `false` | idem 14/16 |
| `get_Range` | `Nullable<int>` sans valeur | idem 10/16 |
| `get_RemoveOnBondedEntityDeath` | **`false`** | **2/16** |

Ces trois getters sont les **seuls** paramètres lus par
`IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal`, qui construit
l'`ArraySet` des triggered-abilities portées par l'effet — une par condition VRAIE, chacune de la
forme `Triggered(<cond>, RemoveEffect(EffectSelf))` :

    RemoveOnBondedEntityDeath ->  NOT AmountIsZero(BondedEntityFromEffect)
                               &  ( On(0x2) | On(0x25) )
                               &  IsEntityWithIdTarget(BondedEntityFromEffect)
    Range.HasValue            ->  NOT IsInRange(Owner, BondedEntity, Direct(Range))
                               &  NOT AmountIsZero(BondedEntity) & On(0x1d)
    Adjacent                  ->  NOT IsAdjacent(Owner, BondedEntity, 3)
                               &  NOT AmountIsZero(BondedEntity) & On(0x1d)

Les trois étant faux/absents, **l'`ArraySet` est VIDE** : cet effet ne porte AUCUN trigger de
retrait automatique.

**Balayage de la famille** (`resolveMethodPtr` sur les 16 classes dont `classes.tsv` donne
`ABondEffect` pour parent, 2026-08-01) : `get_RemoveOnBondedEntityDeath` rend **true** chez 13
d'entre elles (corps trivial partagé), un calcul chez `IdunBattle.Entities.Effects.APendingAttackEffect`,
et **false** chez exactement DEUX — `TunnelingHorror_PendingSummonEffect` et son jumeau
`IdunBattle.Entities.Effects.Loki.CallRipperSwarms_PendingSummonEffect` (EffectType 1094). Les deux
marqueurs de « summon en attente » sont donc les seuls bonds que la mort de l'unité bondée ne casse
pas. (`get_Adjacent` : `false` partout sauf `HolyDuel_TauntEffect` = `true` et
`HazeOfCorruption_DamageTransferEffect` = corps propre.)

### 1.3 La pose — `TunnelingHorrorAbility$$ExecuteBehaviour` (active 1011)

`IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorrorAbility$$ExecuteBehaviour` exécute
TROIS behaviours successifs :

    RemoveUnitFromItsTiles( Caster, removeTileFromUnit: true )
    RemoveAllForcedAttackTargets( Caster )
    AddBondEffect( 0x459 = 1113, AbilityStateReference,
                   source: Caster, targets: TargetTiles, bondedEntity: Caster,
                   <options SANS TurnsFromRounds> )

⚠ **`docs/rl/summon-abilities-port-spec.md` annonçait « default → 1 round » : RÉFUTÉ.** Aucun
`TurnsFromRounds` n'est passé et le canal live rend `remaining = 0` — l'effet est **PERMANENT**
jusqu'à son retrait explicite.

`$$.ctor` = `AActiveAbility(<opts>, 2 = AbilityAttackType.Others)` avec
`IdunBattle.Core.Services.TargetingOptions$$.ctor(isSelfCasting: false, range: <statique>,
forceMeleeTarget: 1, rules: 0x8000000001042, null, null)` — **forme DIRECTE** (6 arguments), donc le
littéral EST le masque effectif :

    0x2    TargetMatchesDynamicRule      0x40   TargetIsTile
    0x1000 TargetTileIsFree              1<<51  TargetIsNotSteppable

### 1.4 La lecture — `TunnelingHorrorAbility$$GetDynamicInvalidTargetReason`

    HasEffect( Get(target), 0x459, ... )  ->  return 2 (TargetMatchesDynamicRule)

Une tuile **déjà marquée** est une cible INVALIDE. C'est le seul consommateur du marqueur côté
ciblage, et c'est ce qui rend l'effet observable sans hook (cf. § 2, E3).

### 1.5 Le retrait — `TunnelingHorror_AppearAbility$$ExecuteBehaviour` (active 1060)

    bond = First( EffectTarget( BondEffects(all, 0x459, bondedEntity: Owner) ), 1 )   # la TUILE marquée
    ...  CanAddUnit / Randomize / SortByFormula(ConditionalAmount(HasAdjacentEnemies, Get(1), Get(0)))
    ...  PushToPrioritizedTiles(Owner, Units(bond, ...), <voisines libres>)            # « pushing aside »
         If( NOT AmountIsZero(CanAddUnit(bond)), MoveUnit(Owner, bond), MoveUnit(Owner, <repli>) )
       + PerformAIAttackFromCurrentPosition(Owner)                                     # « attack any adjacent »
       + RemoveEffect( <bond> )                                                        # <- le retrait
       + FinishTurn(Owner)
         If( Count(CanAddUnit(all)) > <seuil>, <ci-dessus>, Kill(Owner) )               # plus aucune tuile libre

`$$.ctor` = `TargetingOptions(isSelfCasting: true, ..., rules: 0x80008000000000)` =
`TargetIsCaster` (1<<39) | `CasterHasNoTile` (1<<55) — cohérent au bit près avec la mesure live :
la cible unique de 1060 est le caster lui-même, et il n'a pas de tuile.

## 2. Le montage live, et ce qu'il a mesuré

### 2.1 Confrontabilité : un SUMMON **sans invocateur d'unité**

`necroSmnDestroyer` porte `TunnelingHorror` en `activeAbilities`. Balayage du gameconfig (127 lineup
+ 491 npc + 65 summons) : la seule référence à `necroSmnDestroyer` hors de sa propre entrée est
`abilities["EnvFactionSummons:Necrons"].constants.unitId` — une ability d'**ENVIRONNEMENT** que
**aucune** unité ne porte (`activeAbilities`/`passiveAbilities` : 0 porteur). Le recours 1 de
`case-92` §5bis (spawner l'invocateur) est donc fermé, le recours 2 (vérifier qu'il n'y en a pas)
est fait, et on passe au **recours 3 : GREFFE de l'ability sur des héros DU POOL**.

Légitime ici, condition vérifiée : `gameconfig.ability("TunnelingHorror")` n'a **aucune variable ni
constante**, et le behaviour ne lit ni stat, ni trait, ni arme du caster (il ne lit que la position
du caster et la tuile visée). Greffons : `necroDestroyer` et `necroOverlord`
(`ActiveAbilities = [1011]` dans une COPIE du seed BC, jamais le seed partagé).

### 2.2 Les cinq mesures — `probe_366_r1_tunneling_horror.py`

Board `MC1_67`, seed 777, rank 17. Cible = la tuile légale la plus éloignée des deux casters
(5,8) ; témoin = (4,8).

**E1 — la pose.** Cascade d'events du `applyAction ability(1011)` :

    [User_UseAbility e=81 «TunnelingHorror»]
      ChangeStats e=81  UnitStats_ActionsAvailable=0
      [Ability_Power e=81 «TunnelingHorror»]
        RemoveUnitFromTiles e=81  Clear_Unit_Tiles=1
        [Effect_Refresh e=100 «TunnelingHorror_PendingSummon»]
          ActivateEffect e=45  Effect_Id=100
          ReceiveEffect  e=45  BondEffect_BondedId=81 Effect_SourceId=81
                               Effect_SourceActiveAbility=1011 Effect_CurrentLevel=1
      ChangeStats e=81  UnitStats_TurnFinished=1

`e=45` est l'**entité-TUILE** (3,6) du premier montage / (5,8) du probe. `tileMeta` rend
`{name: TunnelingHorror_PendingSummon, effectType: 1113, source: 81, remaining: 0, level: 1}` sur
CETTE tuile et **aucune autre**. Le caster passe à `pos = null`, `alive = true` : il est **hors
plateau**, pas mort.
⚠ `rl_duel` affiche « u81 TUÉ (hp 8032 -> 0) » : c'est son heuristique qui lit `hp = null` comme 0 —
faux positif d'affichage, l'unité est vivante (`alive: true`, et elle réapparaît en E5).
⚠ `decisionView` est **aveugle aux effets de TUILE** (case-92) : la seule lecture est `tileMeta`.

**E2 — le seed offline.** `load_state(dec, ob, snap, board=board, tiles=tileMeta)` matérialise sur
l'entité-tuile une instance de `TunnelingHorrorPendingSummonEffect` (la classe du registre), avec
`source = 81`. `bonded = None` : le canal `tileMeta` publie `{name, effectType, source, remaining,
level}` et **PAS** le `BondEffect_BondedId` — limite de CANAL, pas trou de port (le flux d'events, lui,
le porte).

**E3 — le DISCRIMINANT.** Le second porteur greffé (`necroOverlord`) a **58** cibles légales pour
1011 ; la tuile marquée **(5,8) en est exclue**, le témoin (4,8) y est. C'est
`GetDynamicInvalidTargetReason` = `HasEffect(target, 0x459)` qui s'exerce : la présence de l'effet
CHANGE un résultat observable.

**E4 — la persistance.** Après `endturn` + `aiturn` (tour adverse complet), l'effet est toujours sur
(5,8), `remaining = 0`. Ni `Range` ni `Adjacent` ne le retirent — cohérent avec les deux getters
éteints, et le porteur du bond est hors plateau donc à distance indéfinie.

**E5 — le retrait.** Cast de 1060 :

    [Ability_Power e=81 «TunnelingHorror_Appear»]
      ChangePosition e=81  Unit_Foot_Tile_Id_1=45 Is_Last_Tile=1
      [Ability_Power e=45 «LightCover»] ...
      [Effect_Refresh e=100 «TunnelingHorror_PendingSummon»]
        LoseEffect e=45 · DeactivateEffect e=45
      ChangeStats e=81  UnitStats_TurnFinished=1

La tuile est nettoyée, le caster est SUR la tuile bondée.

**Le tour d'après**, l'unité hors plateau EST dans `decisionView.toActivate` avec `hasAction = true`
et `pos = null` ; `abilityTargets(1060)` rend UNE cible, elle-même, avec `pos = {col:-1, row:-1}`.
(Ce n'est pas le cas summon de #291 : ici l'unité n'apparaît pas pendant le tour de quelqu'un
d'autre, elle a juste perdu sa tuile.)

## 3. Ce qui est porté, et ce qui ne l'est pas

**PORTÉ** — `TunnelingHorrorPendingSummonEffect` (`engine/entities/effects/loki/status.py`), inscrite
à `EFFECT_CLASSES["TunnelingHorror_PendingSummon"]`. Marqueur PUR : aucune contribution sur aucun
canal. Les trois getters d'`ABondEffect` sont transcrits en attributs de classe INERTES
(`BOND_ADJACENT` / `BOND_RANGE` / `BOND_REMOVE_ON_BONDED_ENTITY_DEATH`) pour que la **NON-inscription
de 1113 dans `EFFECT_TRIGGERS` se lise comme une mesure et pas comme un oubli** — le port ne mirror
pas `CreateHandleTriggerAbilitiesInternal` génériquement, chaque effet déclare ses triggers.

**RÉSIDU NOMMÉ — le VECTEUR DE POSE (active 1011) n'est PAS porté.** Conséquence exacte : offline, un
cast de 1011 est un **no-op silencieux**, et l'effet n'arrive dans `State.effects` que par le chemin
de CHARGEMENT (`runner/snapshot.py::_load_tile_effects`), jamais par une pose offline.

Ce qui manque, nommément :

1. `IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute` — pour chaque pied : si
   `<tuile>.<occupant> == unit.Id`, l'effacer ; puis (si `removeTileFromUnit`) effacer le lien
   `pied -> tuile`. Côté port : `set_unit_feet(state, uid, [])` **et** retrait du `PositionComponent`
   (l'état « unité sans position » existe déjà pour les MoW hors-plateau, mais **jamais pour une
   UNITÉ** — c'est le vrai coût, il touche un foyer que ~200 sites lisent). Le natif mémorise en plus
   la dernière `UnitPositionId` (`+0x88..0xa4`), sans consommateur offline connu.
2. La feuille DSL `RemoveUnitFromItsTiles` + `RemoveAllForcedAttackTargets` (ce dernier a un
   composant côté port, `ForcedAttackTargetsComponent` ; il n'a émis AUCUN event dans les mesures,
   la liste étant vide).
3. `ABILITY_CLASSES[1011]` + `TARGETING_OPTIONS = 0x8000000001042` + `ABILITY_ATTACK_TYPE = Others`
   (les deux littéraux sont **déjà lus**, cf. §1.3 — les reprendre tels quels).

L'ability 1060 (`TunnelingHorror_Appear`) est un arbre nettement plus gros (§1.5) et n'a **aucune
config au gameconfig** ; elle est hors périmètre de ce résidu.

**NON COUVERT (et probablement inatteignable par construction)** : la conséquence de
`get_RemoveOnBondedEntityDeath = false`. La seule fenêtre où le bond existe est celle où l'unité
bondée est HORS PLATEAU — donc intargetable. Seul un DoT posé AVANT le tunnel pourrait la tuer sous
le bond ; montage non joué.

## 4. Reproduction

    python scripts/python/probe_366_r1_tunneling_horror.py          # 5 mesures live
    python -m pytest scripts/python/tests/engine/test_366_r1_tunneling_horror_pending_summon_offline.py
