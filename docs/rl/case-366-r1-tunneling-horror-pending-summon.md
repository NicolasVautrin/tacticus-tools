# case-366-r1 — `1113 TunnelingHorror_PendingSummon` + son VECTEUR DE POSE (actif `1011`) : PORTÉS

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

Le corps porte **DEUX** refus, pas un (relu en entier au portage) :

    if ( HasEffect( Get(target), 0x459, onlyActive: false, targetType: 6 ) )   return 2;   # (a)
    foreach (t in casterTiles)
        if ( IdunBattle.Entities.TileExtensions$$IsTemporary(t) )              return 2;   # (b)
    return 0;

(a) Une tuile **déjà marquée** est une cible INVALIDE. C'est le seul consommateur du marqueur côté
ciblage, et c'est ce qui rend l'effet observable sans hook (cf. § 2, E3).
(b) Un caster **debout sur une tuile TEMPORAIRE** ne peut pas creuser. `IsTemporary` lit le booléen
`@+0x2c` du `TileComponent`.

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

**PORTÉ — le VECTEUR DE POSE (active 1011).** Trois pièces, dans l'ordre de la frontière #149 :

1. `IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute` (surcharge UNITÉ) →
   `engine/runner/operations/remove_unit_from_tiles.py`.
2. Les deux feuilles DSL → `engine/runner/abilities/behaviours/lifecycle.py` :
   `RemoveUnitFromItsTiles` (`…Behaviours.RemoveUnitFromItsTilesBehaviour$$Execute`) et
   `RemoveAllForcedAttackTargets` (`…Behaviours.RemoveForcedAttackTargetBehaviour$$Execute`).
3. `TunnelingHorrorAbility` → `engine/runner/abilities/necrons.py`, au registre avec ses deux
   littéraux de ctor (`TARGETING_OPTIONS = 0x8000000001042`, `ABILITY_ATTACK_TYPE = Others`).

**Le vrai coût n'était pas la primitive, c'était l'ÉTAT qu'elle crée** — une UNITÉ sans position.
Deux choses le rendaient piégeux, et une seule a demandé du travail :

* **L'ÉCRIVAIN.** `set_unit_feet` est l'écrivain unique de l'empreinte ; sa branche « liste vide »
  n'existait pas. Pire, elle *semblait* exister : `set_unit_feet(state, uid, [])` retombait sur
  `if len(uc.feet) <= 1: uc.feet = None`, donc rendait l'unité mono-tuile **et laissait la
  `PositionComponent` en place**. L'opération aurait « réussi » sans que l'unité quitte le plateau.
  La branche pose désormais `feet = []` MATÉRIALISÉ **et** retire la `PositionComponent` — les deux
  ensemble, sans quoi `get_unit_feet` (qui retombe sur la position quand `feet is None`) et le
  composant divergeraient.
* **LES LECTEURS.** Balayage exhaustif des **cinq** portes du foyer —
  `probe_366r1_position_readers_census.py`, 2026-08-01 : `get_component(PositionComponent)` **148**
  call-sites, `unit["pos"]` **83**, `_pos(…)` **47**, `get_unit_feet` **12**, `get_main_tile` **1**
  — soit **291**, dont **0** déréférence une position nulle sans garde. L'heuristique en signale
  **4** ; les quatre ont été LUS et sont gardés (deux par `_enemies`, un par un filtre en ligne
  précédente, un in-line), et le probe les porte en **exemptions NOMMÉES** plutôt qu'en seuil
  numérique — un cinquième site le ferait rougir, une exemption périmée aussi.
  L'état n'était donc pas inédit : le chemin de CHARGEMENT le produit déjà
  (`snapshot._load_units` ne pose la `PositionComponent` que si `pos.col is not None`, et
  `decisionView` rend `pos = null` pour l'unité sous terre). **Seul l'écrivain manquait.**

**Ce que le port ne mirror PAS, nommément** (aucun est un oubli) :

* `remove_tile_from_unit = False` — les deux boucles natives (tuile→pied, puis pied→tuile) sont
  **la même arête** après le collapse `pied → UnitFootComponent.TileId → tuile` en un `(col,row)`,
  et l'occupation du port est DÉRIVÉE. « Les tuiles sont libérées mais l'unité y reste » n'est donc
  pas représentable : l'Operation ne mute rien et le DIT (`applied: False`). Aucune régression —
  l'unique appelant natif qui passe `false` est l'étape 6 de `RemoveUnitOperation$$Execute`, dont le
  port collapse déjà le retrait de tuiles en `alive = False`.
* Les deux `Nullable<UnitPositionId>` (`UnitComponent @+0x88` et `@+0x98`) que le natif écrit avec
  la position d'avant — **aucun lecteur porté**. Le seul candidat natif est le repli
  `MoveUnit(Owner, <repli>)` de `TunnelingHorror_AppearAbility$$ExecuteBehaviour` : à porter EN MÊME
  TEMPS que 1060, pas avant.
* ⚠ **AJOUT #366-r1 tranche 1** — le port ACCEPTAIT un second cast de 1011 depuis une unité déjà
  sous terre (aucune règle CASTER dans son masque, et la clause TUILE-NULLE générique n'était pas
  portée). Régression PERMISSIVE fermée par la tranche 1 : cf. §5.4.
* Le refus (b) de `GetDynamicInvalidTargetReason` (`IsTemporary` sur les tuiles du caster, §1.4) —
  le port ne matérialise pas `isTemporary` côté RUNNER (`state.board` ne porte que la géométrie et
  `walkable` ; le canal `tileMeta.isTemporary` n'est seedé que côté DÉCISION,
  `engine/ai/context.py::is_temporary_by_pos`). Dégradation PERMISSIVE, jamais un refus inventé.
* Le STEP de vue (`RemoveUnitFromTilesStepHandler`) et l'event de match `0x1b` — le port n'a ni flux
  de vue ni journal de match, comme partout ailleurs dans `operations/`.
* Le natif LÈVE une NRE sur une entité qui n'est pas une unité ; le port rend un refus TRACÉ
  (`None`), aligné sur `RemoveUnitOperation`.

L'ability 1060 (`TunnelingHorror_Appear`) est un arbre nettement plus gros (§1.5) et n'a **aucune
config au gameconfig** ; elle reste hors périmètre — RÉSIDU NOMMÉ.

**La primitive DÉBLOQUE trois autres call-sites natifs** (xrefs EXHAUSTIVES de
`IdunBattleLogic.Entities.DSLBehaviors$$RemoveUnitFromItsTiles`, build `rnca9r7q6c`) — aucun n'est
porté, tous le sont désormais SANS nouvelle primitive :

| appelant natif | ability | état du port |
|---|---|---|
| `…Abilities.Active.Loki.BurrowersAbility$$ExecuteBehaviour` | `1023 Burrowers` (+ `1024 Burrowers_Appear`, effet `1040 Burrowers_Hidden`) | **PORTÉ + confronté live** (§5). ⚠ « jumeau exact de 1011 » était l'hypothèse d'entrée : **RÉFUTÉE** sur trois points, cf. §5.1 |
| `…Abilities.Active.Loki.GrapnelLauncherAbility$$ExecuteBehaviour` | `1090 GrapnelLauncher` | **PORTÉ + confronté live** (§6). ⚠ il n'appelle PAS `RemoveUnitFromItsTiles` sur le CASTER mais sur la CIBLE, et seulement si elle est MORTE sur sa tuile d'origine |
| `…Abilities.Triggered.Loki.StormboyzStrike_TeleportAbility$$CreateBehaviour` | `1141 StormboyzStrike` (effets `1140 _TeleportingIn`, `1179 _AlreadyUsedTile`) | non porté |

**NON COUVERT (et probablement inatteignable par construction)** : la conséquence de
`get_RemoveOnBondedEntityDeath = false`. La seule fenêtre où le bond existe est celle où l'unité
bondée est HORS PLATEAU — donc intargetable. Seul un DoT posé AVANT le tunnel pourrait la tuer sous
le bond ; montage non joué.

## 4. Reproduction

    python scripts/python/probe_366_r1_tunneling_horror.py          # confrontation + 5 mesures live
    python scripts/python/probe_366r1_position_readers_census.py    # recensement du foyer (offline)
    python -m pytest scripts/python/tests/engine/test_366_r1_tunneling_horror_pending_summon_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_366_r1_tunneling_horror_cast_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_366_r1_tunneling_horror_live.py

---

# 5. `#366-r1-tunnel-family` tranche 1 — `1023 Burrowers` : PORTÉE

i2 : « This unit may burrow in its turn, disappearing from the battlefield. In its following turn it
must surface and may do so in any free hex. If adjacent to an enemy unit, it may attack in melee
immediately. »

## 5.1 Ce que « jumeau exact de 1011 » disait, et ce que le décompilé dit

L'inventaire §3 annonçait 1023 comme le **jumeau exact** de 1011 (seul autre appelant à prendre
AUSSI `RemoveAllForcedAttackTargets`). L'appariement des deux premiers étages est juste ; **les trois
autres points sont faux**, et chacun change le port :

| | `1011 TunnelingHorror` | `1023 Burrowers` |
|---|---|---|
| étage 3 | `AddBondEffect(0x459, …, targets: TargetTiles, bondedEntity: Caster)` → effet sur la **TUILE** | `AddEffect(0x410, stateRef, targets: Caster, turns: null)` → effet sur le **CASTER** |
| gate | `$$GetDynamicInvalid**Target**Reason`, littéral **2** | `$$GetDynamicInvalid**Caster**Reason`, littéral **4** |
| ctor | overload FLAGS DIRECTS 6 args, `rules = 0x8000000001042`, TILE-TARGET plateau entier | **AUCUN ctor** : recopie du preset statique `<TargetingOptions statics>+0x280` → SELF-CAST, portée 0, `rules = 0x8004` |

L'étage 3 passe la surcharge à 5 arguments d'`IdunBattleLogic.Entities.DSLBehaviors$$AddEffect`
(`effectType, abilityState, targets, turns`), qui passe littéralement `0` en 5ᵉ argument
d'`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor` — le sélecteur **SOURCE**. Le fallback
natif d'`AddEffectBehaviour$$Execute` est alors « la source EST la cible ».

`turns` est un `Nullable<int>` VIDE → pas d'override →
`idun…StaticBattleRules.Effect$$DefaultAmountOfRounds`, dont le switch relu en entier ne connaît que
`{5, 0x11, 0x12, 0x3a, 0x4dc, 0x5c4} → 2`, `{0x429, 0x48a} → 1`, `{0x4f} → 3` : **0x410 n'y est
pas** → `remaining = 0` = **PERMANENT**. Retrait explicite par le
`RemoveEffect(Owner, Nullable(0x410))` de `…BurrowersAbility_Appear$$ExecuteBehaviour`.

**Aucune classe d'effet dédiée pour 1040**, et c'est une MESURE : `frida/classes.tsv` ne contient
aucune `Burrowers*Effect` (13 lignes `Burrower*`, toutes `Ability`/`Playbook`/`Visuals`). Le port
laisse donc 1040 hors d'`EFFECT_CLASSES` → `BaseEffect` nu, symétrie exacte.

Le masque `0x8004` se décompose sans bit résiduel : `CasterMatchesDynamicRule` (0x4) |
`CasterIsPossibleTarget` (0x8000, déclaratif). Même preset et même masque que `1045 GetEmRuntz`.
`AActiveAbility..ctor(this, &opts, 2)` → `ABILITY_ATTACK_TYPE = Others`.

Le gate, VERBATIM : `casterTiles` nul ou vide → **4** ; sinon une tuile `TileExtensions$$IsTemporary`
→ **4** ; sinon 0.

## 5.2 Confrontabilité

`unit_map.py find --ability Burrowers` → **6** unités : le SUMMON `tyranSmnRipperSwarm` (traits
`Summon`, `InstinctiveBehaviour`, `Swarm`, `BattleFatigue`) et cinq NPC `tyranNpc2RipperSwarm*`. Le
summon a bien deux invocateurs (`ItItches`, `BarbedOvipositor`, `constants.unitId`) mais il
s'**observe** et ne se **commande** pas (#291) → recours 3 de `case-92` §5bis : GREFFE de 1023 sur
`tyranParasite` + `tyranNeurothrope` (pool rank 17), dans une COPIE du seed BC. Condition vérifiée :
`gameconfig.ability("Burrowers")` = `{upgrades: null, variables: {}}` et le behaviour ne lit ni stat,
ni trait, ni arme du caster — seulement ses TUILES.

## 5.3 Les mesures (`probe_366_r1_burrowers.py`, 2 couples board/seed)

**CONFRONT** — même état de départ, cast rejoué OFFLINE par la voie complète puis LIVE, états finaux
comparés terme à terme. `MC1_67`/777 et `C3_26`/31337, identiques des deux côtés :

    avant  {pos: (1,0), feet: [(1,0)], alive: True,  hidden: []}
    après  {pos: None,  feet: [],      alive: True,  hidden: [(1040, None)]}

L'effet est sur le CASTER, permanent, et le caster est HORS PLATEAU — pas mort.

**E-SWAP — le piège de lecture de ce cas.** La matrice 2×2 des `casterReason` natifs est **CROISÉE** :

    1023 sur l'ENFOUI -> 0x1   |  1023 sur le TÉMOIN -> 0
    1024 sur l'ENFOUI -> 0     |  1024 sur le TÉMOIN -> 0x1

Le `0x1` ne vient PAS de la cascade de ciblage : `IdunBattle.Core.Services.AttackQuery$$GetInvalidCasterReason`
(l'étage qu'interroge le RPC `abilityReason`, AU-DESSUS de `TargetingQuery`) rend
`GenericBrokenTargetingRule(1)` dès que `ActiveAbilityComponent$$GetOrNull(baseUnit, type)` est nul,
que `ActiveAbility$$get_CanCurrentlyBeUsed` est faux ou que `+0x44 == 0`. **Le natif remplace 1023
par 1024 sur le caster pendant l'enfouissement** — la matrice tient encore au tour suivant, avec
`hasAction = true` : ce n'est donc pas la consommation d'action. Cette couche n'est **pas portée**
(le port n'a aucune notion de disponibilité d'ability) — RÉSIDU NOMMÉ.
⚠ Cette matrice ne SÉPARE PAS l'échange d'ability de la règle `HasEffect(caster, 0x410)` de
`…BurrowersAbility_Appear$$GetDynamicInvalidCasterReason` : les deux la prédisent, les deux rendent
le littéral 1. La PRÉSENCE de l'effet est établie ailleurs, sans ambiguïté, par CONFRONT.

**E-GATE — discriminant de VERDICT**, après un tour complet (anti-confond) : natif et port refusent
tous deux un second 1023 sur l'unité enfouie, acceptent tous deux sur le témoin — à des **étages
différents**, tous deux lus au décompilé (natif : `AttackQuery`, échange d'ability ; port : clause
tuile-nulle, `0x40000000`).

## 5.4 La clause TUILE-NULLE — trouvée par la confrontation, portée ici

`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`, verbatim :

    if ( !(rules & AllowNullCasterTile) && !(rules & CasterHasNoTile)
         && CollectionExtensions.IsNullOrEmpty(casterTiles) )
        return GenericBrokenTargetingRule(AllowNullCasterTile);   // 0x40000000

Elle précède l'invocation de la règle-déléguée `CasterMatchesDynamicRule`, donc **la clause (a) de
`BurrowersAbility$$GetDynamicInvalidCasterReason` est PRÉEMPTÉE** sur le chemin
`ActiveAbilityOperation$$ExecuteInternal` (le mirror est conservé quand même : le natif porte bien ce
test, et le rang de la cascade générique n'est pas une propriété de cette ability).

Elle était NON PORTÉE, et ce choix était **juste jusqu'à #438** : le seul caster sans tuile était la
MACHINE OF WAR, et la porter n'aurait fait qu'inventer un refus. Depuis que
`RemoveUnitFromTilesOperation` produit une UNITÉ ordinaire sans tuile, son absence est une régression
**PERMISSIVE** : le port acceptait un second cast de 1011 **comme** de 1023 depuis une unité sous
terre. Portée au rang natif dans `get_invalid_caster_reason`.
Argument MoW **re-mesuré** : les 17 abilities MoW du registre posent TOUTES `AllowNullCasterTile` —
contre-bras testé (`test_the_null_tile_clause_spares_abilities_that_allow_it`). Clause 4b
(`CasterHasNoTile` + tuiles non vides) : **0 porteur au registre**, non portée.

## 5.5 Ce qui n'est PAS couvert

* le 2ᵉ refus du gate (`TileExtensions$$IsTemporary` sur les tuiles du caster) — `isTemporary` n'est
  pas seedé côté RUNNER (`state.board` ne porte que géométrie et `walkable`) ; même résidu que 1011,
  dégradation PERMISSIVE ;
* `RemoveAllForcedAttackTargets` sur un caster **réellement** sous Taunt / `InstinctiveBehaviour` —
  exercé OFFLINE (liste non vide) mais pas en live ;
* l'échange d'ability 1023 → 1024 (couche `ActiveAbilityComponent`) ;
* l'ability `1024 Burrowers_Appear` elle-même (arbre `Enemies → AdjacentTiles → CanAddUnit → Unique`
  `Otherwise` `First(SortTilesByUtility(…, 7))`, puis `PerformAIAbility` /
  `If(!AmountIsEqualOrGreater, MoveUnit)` / `If(…, Kill)` / `RemoveEffect(0x410)`, aucune config au
  gameconfig). Son ctor : `rules = 0x8040000004` = `CasterMatchesDynamicRule` | `AllowNullCasterTile`
  | `TargetIsCaster`, `RANGE_SELF`, `AbilityAttackType.Others` ; son
  `$$GetDynamicInvalidCasterReason` = `HasEffect(caster, 0x410, onlyActive: false) ? 0 : 1`.

## 5.6 Reproduction (tranche 1)

    python scripts/python/probe_366_r1_burrowers.py
    python -m pytest scripts/python/tests/engine/runner/test_366_r1_burrowers_cast_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_366_r1_burrowers_live.py

---

# 6. `#366-r1-tunnel-family` tranche 2 — `1090 GrapnelLauncher` (face COMBAT) : PORTÉE

i2 : « Targets an enemy unit within 3 hexes and deals 1x <dmg> Physical Damage to it. If Tjark is not
already adjacent to the target, it is then pulled 1 hex towards Tjark if possible, and can be pulled
over any elevation but not through impassable terrain. Tjark then moves to occupy the hex the target
originally occupied if it's free, or a free adjacent hex if it is not. If there are no free hexes,
then Tjark does not move. »

## 6.1 L'arbre, et les deux points où il contredit l'i2

`IdunBattleLogic.Entities.Abilities.Active.Loki.GrapnelLauncherAbility$$ExecuteBehaviour`, un seul
`AActiveAbility$$Execute` sur quatre `op_Addition` :

    cache = Cache( Tiles(Target@0x60), matchAbilityEntities: true )
    pick  = PickRandomly( CanAddUnit(AdjacentTiles(cache)), Direct(1), null, 0x7fffffff, false )

    PullUnitOneTile( Caster@0x48, Units(cache), Nullable(GetNumberConstant(0x5b = knockbackRange)) )
  + If( NOT IsDead(Target@0x60), AttackWithAttackDamage(…, GetNumberConstant(0x2f = nrOfHits)) )
  + If( IsDead(Target@0x60) & AreEqual(TargetTiles@0x78, cache),
        KillDeadUnits(Owner@0x30, Target@0x60) + If( IsDead(Target), RemoveUnitFromItsTiles(Target, true) ) )
  + If( IsCanAddUnit(First(cache)), FlyUnit(Caster@0x48, First(cache)),
        If( AmountIsGreaterThanZero(pick), FlyUnit(Caster@0x48, pick) ) )

1. **Le PULL PRÉCÈDE l'ATTAQUE.** L'i2 dit l'inverse. `op_Addition(left@+0x50, right@+0x58)` et
   `IdunBattle.DSL.CombinedBehaviour$$Execute` exécutent gauche puis droite ; et le gate
   `If(NOT IsDead(Target))` devant l'attaque n'aurait aucun sens dans l'autre ordre — il n'existe que
   parce que le pull PEUT tuer (knockback).
2. **Le `Cache` est LOAD-BEARING** (même rôle qu'#27) : primé par le pull, il fige la tuile
   d'ORIGINE ; le `AreEqual` (« la cible n'a pas bougé, donc le pull a échoué »), le `First` du vol
   et l'`AdjacentTiles` du repli la relisent tous.

`$$.ctor` = forme FLAGS DIRECTS 6 args : `TargetingOptions..ctor(&opts, 0, <TargetingRange
statics+0x18> = RANGE_FROM_CONFIG, 1, rules = 0x8004000, 0, 0)` puis `AActiveAbility..ctor(this,
&opts, 0)`. `0x8004000` = `TargetIsEnemy` | `TargetIsInRange`, **0 bit résiduel** ; ni
`TargetMatchesDynamicRule` ni `CasterMatchesDynamicRule` → aucun gate dynamique (cohérent : la classe
n'a aucun corps `GetDynamicInvalid*Reason`). `ABILITY_ATTACK_TYPE` = 0 = `DirectTargetAttack`.

## 6.2 Le pull — géométrie et **le quirk que l'i2 tait**

`PullUnitOneTile` → `DisplaceUnitBehaviour(direction = 6)` → `IdunBattle.Operations.
DisplaceUnitOperation$$FindTileToPullOnce` → `BattleQuery$$GetMinimumTiles180Front(caster, target,
isReachable: 0)` = l'arc **AVANT** (vers le tireur) à un hex de la cible — le symétrique EXACT de
l'arc arrière du push, au signe des vecteurs près. Aligné → 1 candidate ; non aligné → 2, puis
`Random(0, n)`. Mirror : `engine/battle_query.py::get_minimum_tiles_180_front`.

`AddNewTileToList(…, checkWalkability = 1, checkElevation = 0)` → `TileUtil$$IsTileValidForList` teste
`IsWalkable` et **saute** le gate `|Δelev| < 2` : c'est mot pour mot « over any elevation but not
through impassable terrain ».

⚠ **`FindTileToPullOnce` n'applique son filtre `IsEmptyOrSteppable` que si la liste a PLUS d'une
tuile.** Cible DÉJÀ ADJACENTE → l'arc se réduit à la **tuile du caster**, rendue telle quelle,
occupée → la queue commune part sur `ApplyKnockbackTo(caster, target, doIt)`, avec `doIt` =
`options+0x11` que `PullUnitOneTile` pose à **1**. Donc : **cible au contact = pas de pull, mais
`ceil(hp_max × BC.Damage.KnockbackPercentage / 100)` en plus de l'attaque.**

## 6.3 Confrontabilité

`unit_map.py find --ability GrapnelLauncher` → **1** unité : `spaceHound` (« Tjark »), **HERO**,
**présent** au pool rank 17. Aucune greffe, aucune injection catalogue.

## 6.4 Les mesures (`probe_366_r1_grapnel_launcher.py`, 2 couples board/seed)

Positions : accord **terme à terme** des deux côtés (pull d'exactement 1 hex vers le tireur ; caster
sur la tuile d'origine libérée). Discriminant du quirk, à DEUX BRAS :

| couple | Δhp natif ADJ | Δhp natif FAR | écart | knockback attendu |
|---|---|---|---|---|
| `MC1_67`/777 | 2777 | 1301 | 1476 | 1707 |
| `C3_26`/31337 | 2547 | 628 | **1919** | **1908** |

Le bras FAR (pull réussi, aucun knockback) donne l'attaque seule ; le bras ADJ y ajoute le knockback,
et le port prédit sa composante **à l'unité près** (Δport = 1707 / 1908 = le knockback exact).

⚠ **Le `hp` n'est PAS comparable terme à terme** : sur un état rechargé le MT natif n'est pas
reproductible (aucun canal ne l'expose à mi-bataille), donc le port n'inflige pas le dégât
d'ATTAQUE. Même limite pour la branche `PickRandomly` du vol (le probe y compare la PROPRIÉTÉ —
voisine de la tuile d'origine — pas la tuile).

## 6.5 Ce qui n'est PAS couvert

* le **steppable-crush** (`IsFilled && IsSteppable(occupant)` → `KillUnit(ForSteppable)` puis le move
  a lieu) — même résidu que le push ;
* la garde `TileComponent+0x2c` (tuile TEMPORAIRE) sur la destination — `state.board` est statique ;
* la **sémantique** du `Nullable(3)` que `DSLBehaviors$$FlyUnit` pose à `MoveUnitBehaviourOptions
  +0x08` (aucun lecteur lu) : le port rend le même déplacement que `MoveUnit`, sans traversée
  particulière — le pas est de toute façon d'AU PLUS 1 hex ici ;
* le knockback de **dénivelé** (`elevationDifferenceForKnockback` = 2) est porté et testé OFFLINE,
  mais NON exercé live (aucun dénivelé ≥ 2 sur les deux boards joués).

## 6.6 Effet de bord mesuré — 6 clés de config à espace parasite

`GrapnelLauncher.constants` porte `"knockbackRange "` (espace FINAL). Le natif ne le voit pas : son
dictionnaire est indexé par `AbilityConstantType` et `Enum.Parse` **trim**. Le port, qui lit le JSON
par nom, rendait `None` → knockback de dénivelé éteint EN SILENCE. Repli trimmé (exact d'abord,
correspondance UNIQUE ensuite) dans `engine/entities/effects/magnitude.py::_lookup_config_key`.
Balayage des **572** abilities : **6** clés concernées — `GrapnelLauncher."knockbackRange "`,
`ReanimationBeam` et `DeathOnTheWind` (`"initialCooldownTurns "`, `"munitionsCost "`), et la variable
`HarbingerOfDestruction."nrOfUnits "`.

## 6.7 Reproduction (tranche 2)

    python scripts/python/probe_366_r1_grapnel_launcher.py
    python -m pytest scripts/python/tests/engine/runner/test_366_r1_grapnel_launcher_cast_offline.py
