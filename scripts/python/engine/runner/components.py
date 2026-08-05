"""Composants ECS concrets — port FIDÈLE (noms 1:1 du natif, VA citée).

`IdunBattle.Entities.Components.*Component`. Tranche 0 : seuls les composants de
l'ÉTAT D'UNITÉ diffé (position/HP/owner/identité/effets) sont posés, avec les champs
qu'on peut peupler depuis la vérité live (decisionView/observeBattle, qui lisent
ces composants natifs). Les OFFSETS exacts (layout) seront RE'd quand une operation
les ÉCRIRA (tranche move/damage/effects) ; ici on porte la sémantique des champs.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Dict, Hashable, Iterator, List, Optional

from .state import Component

if TYPE_CHECKING:
    from ..entities import UnitContext


class UnitComponent(Component):
    """Identité d'unité — `UnitComponent` IdunBattle.Entities.Components.UnitComponent$$.ctor / `BaseUnitComponent` IdunBattle.Entities.Components.BaseUnitComponent$$.ctor.
    `visual_id` = id visuel (ex. 'necroNpc1Warrior'), `alive` = vivante.

    `ai_controlled` = l'unité est jouée par l'IA au turn-start de sa team, MÊME sur une team
    par ailleurs contrôlée par le joueur (cas des SUMMONS). Mirroir du flag per-unité runtime lu par
    `IdunBattle.View.Game.IdunGameViews$$IsPlayerAiControlled (SortedDictionary +0x18==1 → AI-contrôlé ; posé
    quand l'unité est invoquée). N'est PAS un trait gameconfig — c'est un état runtime posé au spawn
    (cf. `SpawnUnitOperation`). Une unité d'une team entièrement-IA est de toute façon jouée par l'IA
    (type player 2) ; ce flag cible le cas summon-sur-team-joueur.

    `turn_defeated` = valeur de `state.turn_counts[owner_player]` AU MOMENT de la mort (G3 Ambush) —
    mirror du `TurnDefeated` que `IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$GetUnitsEligibleForResurrect` lit dans
    `AmountIsEqual(Difference(CurrentPlayerTurnsStarted, TurnDefeated(u)), @0xc0=1)`. None tant que
    l'unité n'est pas morte. Posé par `Ambush_SummonAbility` (trigger On(UnitDefeated)).

    `turns_finished` = mirror EXACT du champ `UnitComponent + 0x5c` — le compteur PER-UNITÉ des
    tours que CETTE unité a TERMINÉS. À ne pas confondre avec ses deux voisins :
      * `UnitComponent + 0x58` = `turnsStarted`, incrémenté par
        `IdunBattle.Operations.StartTurnOperation$$Execute`, EXPOSÉ comme `StatType` 12 (`GetStat(unit,
        0xc)` -> `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate`) — porté dans le
        `StatsComponent`, PAS ici ;
      * `TurnComponent + 0x38` = le dictionnaire PAR JOUEUR (`GetAmountOfTurnsStartedByPlayer`) —
        porté par `State.turn_counts`, granularité JOUEUR.
    ÉCRITURE : `IdunBattle.Operations.EndTurnOperation$$Execute` fait `*(int *)(unitComp + 0x5c) += 1`
    pour chaque id de `PlayerComponent.CurrentlyOwnedUnitIds` du joueur qui finit son tour (2 sites :
    les unités, puis la Machine of War du joueur — même offset, `GetTurnsFinished` a les DEUX branches
    d'`EntityType`, 1 = Unit et 6 = Machine). Les unités MORTES en sont exclues :
    `PlayerComponent$$get_CurrentlyOwnedUnitIds` termine par un `RemoveAll` du prédicat
    `PlayerComponent$$u003Cget_CurrentlyOwnedUnitIdsu003Eb__17_0` = « l'id est dans la liste
    @+0x40 (défaits) ».
    LECTURE : `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished` (rend `comp + 0x5c`).
    Consommateurs natifs : `IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger`
    (le nœud `IdunBattleLogic.Entities.DSLFactory$$OwnerHasFinishedMinTurns`, gate de PileIn),
    `IdunBattle.AI.Playbook.Loki.DutyEternalPlaybook$$GetUseProbability` et
    `IdunBattle.AI.Playbook.Loki.InstrumentsOfVengeancePlaybook$$GetUseProbability`.
    ⚠ `turns_finished` n'est PAS dérivable de `turnsStarted` : une unité APPARUE PENDANT le tour de
    son propriétaire (tout summon — grot de `GetEmRuntz`, réplique de `PileIn`) rate le bump de
    `StartTurn` mais prend celui d'`EndTurn`, et garde donc `turns_finished == turnsStarted + 1`
    pour le reste de la bataille.

    `times_attacked_this_turn` = nb d'attaques REÇUES par l'unité pendant le tour COURANT (G6
    HypersensoryAbilities) — source du prédicat DSL `IdunBattleLogic.Entities.DSLFactory$$HasBeenAttackedAmountThisTurnIsEqualOrGreater (compteur natif lu @+0x34 via `TotalTimesAttackedFormula`-family). Incrémenté quand l'unité
    est la CIBLE d'une attaque (pas d'un DoT), remis à 0 au `start_turn` de chaque tour. Gate de l'ActiveCondition
    du HP-floor (`IsEnemyTurn & Not(attacked>=1)` = 1re attaque du tour ennemi) et du trigger MoveAndSpawnDecoy.

    `received_damage_this_turn` (#202) = Dictionary {profil de dégât (int DamageProfileType) → nb
    d'instances} des dégâts REÇUS pendant le tour COURANT — mirror du dict `receivedDamageThisTurn`
    de l'`ActorStatisticsComponent` natif @+0x80 (écrit par `IdunBattle.Operations.RegisterDamageOperation$$Execute`
    → `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterReceivedDamage` : TryAdd(profil,1) sinon +1 ; reset par-unité du joueur
    ENTRANT par `IdunBattle.Operations.StartTurnOperation$$ResetUnit` → `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetReceivedDamageThisTurn`).
    Consommé par le sélecteur `UnitsThatTakenDamageThisTurn` (WeaverOfFate : ContainsKey(Psychic=13)).
    NB : logé ici (comme `times_attacked_this_turn`) alors que le foyer natif est un composant
    ActorStatistics dédié — résidu structurel documenté (case-202 §6).

    `last_hit_damage_taken_this_turn` / `last_hit_damage_taken_last_turn` = mirror des DEUX champs
    `ActorStatisticsComponent @+0x6c` et `@+0x70` (memes offsets, meme composant que le dict
    `received_damage_this_turn` @+0x80 ci-dessus).
      * ECRITURE, PAR COUP : `IdunBattle.Operations.ApplyDamageOperation$$Execute` ecrit
        `stats[0x68] = stats[0x6c] = (int)*param_1` sur la VICTIME, ou `(int)*param_1` = 1er champ du
        `DamageAppliedResult` = la SOMME des reductions REELLEMENT appliquees par CE coup
        (`FillUpStatComponent.Reduce` sante + 2e pool + `ApplyDamageOperation$$ReduceShield`).
        C'est donc le total du DERNIER COUP (PV + bouclier + armure-pool), PAS le total de l'attaque.
      * ROULEMENT, au turn-start du PROPRIETAIRE : `IdunBattle.Operations.StartTurnOperation$$ResetUnit`
        fait `stats[0x70] = stats[0x6c] ; stats[0x6c] = 0` JUSTE APRES
        `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetReceivedDamageThisTurn`.
        (`ActorStatisticsComponent$$ResetThisTurn` ne touche NI 0x6c NI 0x70.)
      * LECTURE : `IdunBattle.Entities.Formulas.LastHitDamageTakenLastTurnFormula$$Calculate` rend
        `*(int *)(comp + 0x70)` -> noeud DSL `IdunBattleLogic.Entities.DSLFactory$$LastHitDamageTakenLastTurn`.
        Consommateur porte : la regen `TimeFlux` de `thousTerminator` (« plus an additional amount
        equal to the Damage of the last hit he received in the last enemy turn »).

    `revive_used_this_turn` = gate ONCE-PER-TURN du passif revive-en-place (`ReviveEffect`, ex.
    TaintedNarthecium de deathRotbone / Narthecium de l'Apothicaire, case-66). Mirror de la
    DÉSACTIVATION de l'effet (`DeactivateEffect`, 2e volet du `IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour`
    exécuté APRÈS un revive réussi) : une fois l'effet désactivé, son trigger ne fire plus jusqu'à
    RÉACTIVATION au début de tour. Posé à True par la feuille `ConsumeReviveGate` (revive.py), remis à
    False pour TOUTES les unités au turn-start (`reset_revive_gates`, comme `times_attacked_this_turn`).
    i2 « Can only be triggered once per turn ».

    `pending_revive` = mirror du champ `UnitComponent + 0xa8` = **`Nullable<ReviveData>`** (le champ
    IMMÉDIATEMENT après le `Nullable<AttackHit>` @+0x98, cf. `IdunBattle.Entities.Components.UnitComponent$$Copy` qui teste le
    `hasValue` du Nullable @+0x98 par le MÊME helper `thunk_FUN_1801f3000(ptr, fieldInfo)`). Trois
    fonctions natives le manipulent, et c'est LA pièce centrale du sous-système REVIVE :
      * ÉCRITURE  `IdunBattle.Entities.Behaviours.ReviveBehaviour$$Execute` — la feuille DSL `Revive` n'exécute AUCUNE mutation :
        elle POSE la `ReviveData` (amount/healType/sourceId/priority) sur `unitComponent + 0xa8..0xe8`,
        après le gate `IdunBattle.Entities.Behaviours.ReviveBehaviour$$IsPreferredRevive` ;
      * GARDE    `IdunBattle.Operations.KillUnitOperation$$Execute` @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e : `if (!pendingRevive.HasValue)` —
        tout le RESTE de la mort (`On(PreUnitDeath_2)`, `On(UnitDeath)`, `On(UnitDefeated)`, `On(PostUnitKill)`, Remove(flag 0xf)/Add(flag 6),
        `RemoveEffects`, `RegisterDefeatedUnit`) est SOUS cette garde. Un revive posé pendant `On(PreUnitDeath)`
        ANNULE donc la mort (cf. `damage.py::_fire_death_if_killed`) ;
      * LECTURE+PURGE `IdunBattle.Operations.ReviveUnitOperation$$Execute` : lit les 9 qwords @0xa8..0xe8, refuse
        (log d'erreur + return) si `!HasValue` @IdunBattle.Operations.ReviveUnitOperation$$Execute+0x2ba, applique le revive, puis REMET LES 9 QWORDS
        À 0 @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+ (donc APRÈS l'émission de `On(UnitRevived=0x2d)`).
    Port : `None` = pas de revive en attente ; sinon un dict `{amount, heal_type, source, priority}`
    (cf. `operations/revive.py`).

    `current_turn_start_tile` = mirror du champ `UnitComponent + 0x18c` (un `int` d'id de TUILE).
    ECRIT par `IdunBattle.Operations.StartTurnOperation$$Execute`, dans la boucle sur
    `PlayerComponent.CurrentlyOwnedUnitIds` du joueur ENTRANT et juste apres le bump de
    `turnsStarted@+0x58` : `mainTile = EntityExtensions.GetMainTile(unit) ; comp[0x18c] =
    (mainTile != null) ? mainTile.Id : 0`. C'est donc la tuile ou l'unite se trouvait au DEBUT DE SON
    PROPRE TOUR -- PAS la tuile qu'elle vient de quitter. RELU par
    `IdunBattle.Entities.Selectors.CurrentTurnStartTileSelector$$Select` (`IdunBattleLogic.Entities.
    DSLFactory$$CurrentTurnStartTile`), qui rend une liste VIDE quand le champ vaut 0 -- ce que le
    port represente par `None`. Consommateur porte : `GhostReviveAbility`/`TimeFluxReviveAbility`
    (le time-ghost de `thousTerminator` est pose sur CETTE tuile, cf. `triggers/loki/ghost_revive.py`).

    `revived_by_abilities` = mirror du `HashSet<AbilityOrEffect>` @`ActorStatisticsComponent + 0xe0`.
    ECRIT par `IdunBattle.Operations.ReviveUnitOperation$$Execute` : si la `ReviveData` porte un
    `sourceId` (`Nullable<AbilityOrEffect>`), l'operation l'AJOUTE a ce set juste apres `SetHealth`
    et AVANT les flags. RELU par `Idun.Source.IdunBattle.Logic.Entities.Triggers.
    HasBeenRevivedAbilityTrigger$$ShouldTrigger` (`IdunBattleLogic.Entities.DSLFactory$$
    HasBeenRevivedByAbility(unit, source)`) = `set.Contains(source)`. AUCUN reset natif (ni
    turn-start, ni phase) -> c'est un registre de BATAILLE : le gate « une seule resurrection par
    ability » de `GhostEffect` et de `GhostReviveAbility`. Port : set d'ids `AbilityOrEffect`
    (l'`EffectType` 1186 pour le ghost).

    `parent_id` = mirror du lien enfant -> SUMMONER natif : `IdunBattle.Entities.Components.
    ChildComponent`, champ `ParentId` (`BEntityId` = int32 @+0x10 ; observable live `Unit_Parent_Id`
    emis au spawn d'un summon). C'est ce que lit `IdunBattle.Entities.UnitExtensions$$GetParent`
    (`TryGetComponent<ChildComponent>` puis `state.GetEntity(ParentId)` ; la recursion vers la
    RACINE n'a lieu que si son 3e argument `root` est vrai), foyer du selecteur
    `IdunBattle.Entities.Selectors.ParentSelector$$Select`, consomme par
    `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$CreateTargetSelector` (`Parent(Self)`
    = le SUMMONER) et par le gate `IsFriendlyKell` du playbook SupremeCommander.
    ⚠ Ce n'est PAS `IdunBattle.Entities.Components.ParentComponent`, dont le `+0x10` est
    `ChildrenIds` (une `List`, sens parent -> enfants -- cf. son `$$.ctor` et son `$$ToString`) :
    c'est l'autre bout du lien, et l'ancrage que nommait le residu de #372.
    None = unite sans parent (toute unite du roster initial). Pose par `SpawnUnitOperation`
    (`_spawn_config_grot`, mirror `SpawnUnitOptions` -> `Unit_Parent_Id = casterId`) et, sur un etat
    HYDRATE, seede depuis `combatSnapshot.units[].parentId` par `snapshot._load_unit_parent` (#378).

    Le lien RECIPROQUE (parent -> enfants) n'est PAS materialise : le port le derive en balayant
    `state.entities` (cf. `children_of`), la ou le natif tient la liste `ParentComponent.ChildrenIds`
    (@+0x10, construite par `IdunBattle.Entities.Components.ParentComponent$$.ctor`).

    `death_source` = mirror du `Nullable<IdunBattle.Operations.DamageSource>` @`UnitComponent+0x108`,
    ECRIT par `IdunBattle.Operations.KillUnitOperation$$RecordDeathReason(killer, killed,
    killedUnitComponent, deathReason)` (call-site : `IdunBattle.Operations.KillUnitOperation$$Execute`,
    AVANT le `On(PreUnitDeath=1)` -- ordre LU au decompile) et RELU par
    `IdunBattle.Entities.Triggers.HasDeathReasonTrigger$$ShouldTrigger` (qui resout SON selecteur, prend
    le `UnitComponent` de chaque unite selectionnee, lit ce champ et delegue a
    `...$$IsMatchingDeathReason`). Structure de la `DamageSource` LUE au decompile :
    `+0x00 KillerId` · `+0x14 DamageReason` (0=Ability, 1=Knockback, 2=Steppable) ·
    `+0x18 Nullable<AbilityOrEffect>` (lu par `IdunBattle.Operations.DamageSource$$IsFromAbility`).
    Cote port : `(killer_id, damage_reason, ability_or_effect|None)`, None tant que l'unite est vivante.

    `damaged_units_this_phase` = mirror de la `List<BEntityId>` @`ActorStatisticsComponent + 0x48`
    (l'ATTAQUANT y accumule les unites auxquelles il a inflige des degats pendant la PHASE courante).
    C'est LA source du selecteur `IdunBattle.Entities.Formulas.UnitsDamagedThisPhaseSelector$$Select`
    (`IdunBattleLogic.Entities.DSLFactory$$UnitsDamagedThisPhase(attacker)`), qui resout son selecteur
    `attacker`, prend ce composant sur chaque attaquant et rend les ENTITES correspondantes.
    Le champ 0x48 est REMIS A ZERO par `IdunBattle.Operations.EndPhaseOperation$$ResetEntityPhase` --
    la MEME fonction, la MEME boucle d'entites, que le `TriggeredAbilityComponent$$ResetPhase` deja
    porte : le port mappe donc le boundary de phase au MEME endroit (`State.reset_trigger_phases`,
    appelee par `Runner.apply` sur chaque action top-level). Consommateur : le volet OVERKILL de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$ExecuteBehaviour`.
    NB : loge ici (comme `times_attacked_this_turn`/`received_damage_this_turn`) alors que le foyer
    natif est l'`ActorStatisticsComponent` -- MEME residu structurel documente (case-202 §6).

    `tiles_moved_this_battle` / `tiles_moved_this_turn` / `tiles_moved_last_turn` = mirror des TROIS
    champs `ActorStatisticsComponent @+0xec` / `@+0xf0` / `@+0xf4` (case-322-r1).
    ⚠ Le composant natif est bien l'`ActorStatisticsComponent`, PAS le `UnitComponent` : le getter
    de `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` et celui de
    `IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate` resolvent le MEME composant
    que `IdunBattle.Operations.StartTurnOperation$$ResetUnit` passe a
    `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetAttacksReceivedThisTurn`. Loges
    ici comme `received_damage_this_turn` / `last_hit_damage_taken_*` -- MEME residu structurel
    documente (case-202 SS6).
      * ECRITURE : `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved(unit, tiles, state)` =
        `if (tiles < 1) return; comp[0xec] += tiles; comp[0xf0] += tiles;` -- un `+=`, PAS une
        affectation, et un no-op silencieux pour `tiles <= 0`. QUATRE call-sites natifs :
        les DEUX branches d'`IdunBattle.Operations.MoveUnitOperation$$Execute` (simulation et
        reelle), `IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition` et
        `IdunBattle.Operations.DisplaceUnitOperation$$AddTilesMoved`.
      * ROULEMENT, a la FIN de CHAQUE tour :
        `IdunBattle.Operations.EndTurnOperation$$Execute` itere `GetAllUnits` et appelle
        `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn(comp, wasOwnTurn)` =
        `if (wasOwnTurn) comp[0xf4] = comp[0xf0]; comp[0xf0] = 0;`. Le reset de `+0xf0` est donc
        INCONDITIONNEL et GLOBAL (toutes les unites, pas seulement celles du joueur finissant) ;
        `wasOwnTurn` = `PlayerComponent.CurrentlyOwnedUnitIds` du joueur qui finit CONTIENT l'unite.
        ⚠ Ce n'est PAS `StartTurnOperation$$ResetUnit` (qui, lui, ne touche ni 0xf0 ni 0xf4).
      * LECTURE : `TilesMovedThisTurnFormula$$Calculate` rend `+0xf0`,
        `IdunBattle.Entities.Formulas.TilesMovedLastTurnFormula$$Calculate` rend `+0xf4`. Le noeud
        DSL `IdunBattleLogic.Entities.DSLFormulas$$TilesMovedThisTurn` a SIX consommateurs natifs :
        `ModifiedExoarmour_ExtraDmgEffect$$CreateActiveCondition` / `$$GetCurrentDamageBonus` /
        `$$GetExtraDamageMultiplier`, `IdunBattle.Entities.Effects.Loki.EmpyricAmbushEffect$$IsValidAttackForBuff`,
        `MastersOfManoeuvreAbility$$CreateTrigger` et `SmashaEadAbility$$CreateTrigger`.
        `tiles_moved_this_battle` (+0xec) n'a AUCUN lecteur porte : il est ecrit pour rester le
        mirror exact du `+=` double de `RecordTilesMoved`, jamais lu.

    `blocks_made_this_turn` (#366-r1) = mirror de `ActorStatisticsComponent @+0x8c`, le compteur de
    coups BLOQUES par cette unite depuis le debut de son tour. Loge ici comme
    `received_damage_this_turn` / `tiles_moved_*` -- MEME residu structurel documente (case-202 SS6 :
    le foyer natif est l'`ActorStatisticsComponent`).
      * ECRITURE : `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterBlockMade`
        (`+0x8c += 1`), atteinte par `IdunBattle.Operations.RegisterBlockOperation$$Execute` <- slot
        `IOperationProcessor` 0x4c <- `IdunBattle.Operations.ADamageOperation$$RegisterBlocks`, que
        `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` appelle **PAR COUP**, au retour
        d'`ExecuteHit` -- donc APRES l'emission de `On(UnitBlocked)` par
        `ADamageOperation$$EvaluateAfterHitTriggers`. Cet ORDRE est ce qui rend le gate
        `NOT HasBlockedThisTurn` vrai au premier coup bloque du tour.
      * RESET : `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetBlocksMadeThisTurn`
        (`+0x8c = 0`), appele par `IdunBattle.Operations.StartTurnOperation$$ResetUnit` dans la MEME
        sequence que `ResetAttacksReceivedThisTurn` / `ResetReceivedDamageThisTurn` -> portee = les
        unites du joueur ENTRANT (cf. `operations/turnflow.py`).
      * LECTURE : `IdunBattle.Entities.Triggers.TimesBlockedThisTurnFormula$$Calculate` rend `+0x8c` ;
        `IdunBattleLogic.Entities.DSLTriggers$$HasBlockedThisTurn` = `AmountIsGreaterThanZero` de
        cette formule. UNIQUE consommateur porte : le gate de
        `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HarlequinsPanoplyAbility$$CreateTrigger`.

    `blocks_made_this_battle` (#393-r1) = mirror de `ActorStatisticsComponent @+0x88`. MEME forme que
    `tiles_moved_this_battle` : `RegisterBlockMade` pousse les DEUX compteurs (`+0x8c` ce tour,
    `+0x88` la bataille) et `ResetBlocksMadeThisTurn` n'en remet qu'UN a zero (`+0x8c`) -- verifie au
    decompile. AUCUN lecteur porte : le seul consommateur natif est
    `IdunBattle.Core.Services.BattleStatisticQuery$$GetTotalBlocksMadeByUnit` (statistiques de fin de
    bataille, recursif sur les unites ENFANTS quand `IncludeAttackerChildren`), sans pendant porte --
    donc aucun observable de COMBAT ne le distingue. Ecrit quand meme, pour rester le mirror exact du
    `+=` double, exactement comme `tiles_moved_this_battle`.

    `feet` (#R30) = mirror de `UnitComponent._feet` @+0x78 -- l'`OrderedSet<int>` des ids des
    ENTITES-PIEDS de l'unite (`Blueprints.UnitFoot`, chacune portant un `UnitFootComponent
    {UnitId@0x10, TileId@0x14}`), rempli par `IdunBattle.Operations.AddUnitOperation$$Execute`
    (`UnitComponent$$ClearFeet` puis un `UnitComponent$$AddFoot` PAR TUILE, dans l'ordre de la
    liste de tuiles recue). Le port n'ayant ni entite-tuile ni entite-pied, la chaine
    `pied -> UnitFootComponent.TileId -> tuile` est COLLAPSEE en un `(col,row)` (meme collapse
    que `PositionComponent`) : `feet` = la liste ORDONNEE des tuiles de l'empreinte.

      * `None` = unite a UN pied -- le cas NOMINAL de tout le moteur : l'empreinte est alors
        `[PositionComponent]` et rien ne change (cf. `get_unit_feet`). On ne materialise la liste
        que pour les unites MULTI-HEX, ce qui garde les ~200 sites qui lisent `PositionComponent`
        strictement inchanges.
      * `feet[0]` est la MAIN TILE (`IdunBattle.Entities.EntityExtensions$$GetMainTileId` prend
        `_feet[0]` puis lit le `TileId` de CE pied), et c'est l'INVARIANT que `set_unit_feet`
        maintient : `feet[0] == (PositionComponent.col, PositionComponent.row)`.
      * tailles supportees = **1, 3, 7**, declarees par l'enum `IdunBattle.Core.Services.
        TargetingRule` (`CasterHas1/3/7Tiles`, `TargetHas1/3/7Tiles`) et imposees par
        `IdunBattle.Core.Services.MovementQuery$$IsValidUnitFeetList`. Seul le **3** a un
        producteur dans ce build (`DSLFactory.ThreeTileUnitSpawnShape` <- `DutyEternalAbility` /
        `AetherStrideAbility`).
    """
    __slots__ = ("visual_id", "alive", "ai_controlled", "turn_defeated", "turns_finished",
                 "times_attacked_this_turn",
                 "received_damage_this_turn", "revive_used_this_turn", "pending_revive", "parent_id",
                 "death_source", "last_hit_damage_taken_this_turn",
                 "last_hit_damage_taken_last_turn", "feet", "damaged_units_this_phase",
                 "charged_unit_ids", "current_turn_start_tile", "revived_by_abilities",
                 "tiles_moved_this_battle", "tiles_moved_this_turn", "tiles_moved_last_turn",
                 "blocks_made_this_turn", "blocks_made_this_battle",
                 "movement_target_override")

    def __init__(self, visual_id: Optional[str], alive: bool, ai_controlled: bool = False,
                 parent_id: Optional[int] = None):
        self.visual_id = visual_id
        self.alive = alive
        self.ai_controlled = ai_controlled
        self.feet: Optional[List[tuple]] = None      # `_feet` @+0x78 ; None = 1 pied (cf. docstring)
        self.turn_defeated = None
        # `UnitComponent + 0x5c` — cf. la docstring de classe (bloc `turns_finished`). 0 a la
        # creation, exactement comme le champ natif d'une entite fraichement construite : une unite
        # deployee au setup comme un summon apparu en cours de partie partent tous les deux de 0,
        # et c'est `EndTurnOperation` qui les fait diverger.
        self.turns_finished = 0
        self.times_attacked_this_turn = 0
        self.received_damage_this_turn: dict = {}
        self.revive_used_this_turn = False
        # `ActorStatisticsComponent @+0x6c` / `@+0x70` — cf. la docstring de classe (bloc
        # `last_hit_damage_taken_*`). Loges ici comme `received_damage_this_turn` (meme residu
        # structurel : le foyer natif est l'ActorStatisticsComponent).
        self.last_hit_damage_taken_this_turn = 0
        self.last_hit_damage_taken_last_turn = 0
        self.pending_revive = None            # `Nullable<ReviveData>` @UnitComponent+0xa8
        self.parent_id = parent_id            # `ParentComponent` id @+0x10 (summoner)
        self.death_source = None              # `Nullable<DamageSource>` @UnitComponent+0x108
        self.damaged_units_this_phase: list = []   # `ActorStatisticsComponent+0x48` (cf. docstring)
        # `List<int>` @UnitComponent+0x190 — les unites que CETTE unite a CHARGEES (cf.
        # `update_charging` / `IdunBattle.Core.Services.BattleQuery$$IsCharging`). Videe par
        # `FinishUnitTurnOperation` (fin d'activation) -> semantique « charge CE TOUR ».
        self.charged_unit_ids: list = []
        # `int` @UnitComponent+0x18c — cf. la docstring de classe (bloc `current_turn_start_tile`).
        # None = aucun turn-start n'a encore tourne pour cette unite (mirror du 0 natif : le
        # selecteur `CurrentTurnStartTile` rend alors une liste VIDE).
        self.current_turn_start_tile: Optional[int] = None
        # `HashSet<AbilityOrEffect>` @ActorStatisticsComponent+0xe0 — cf. la docstring de classe
        # (bloc `revived_by_abilities`). Loge ici comme `last_hit_damage_taken_*` (meme residu
        # structurel : le foyer natif est l'ActorStatisticsComponent).
        self.revived_by_abilities: set = set()
        # `ActorStatisticsComponent @+0xec/+0xf0/+0xf4` — cf. la docstring de classe (bloc
        # `tiles_moved_*`). 0 a la creation, comme les champs `int` d'un composant natif frais.
        self.tiles_moved_this_battle = 0
        self.tiles_moved_this_turn = 0
        self.tiles_moved_last_turn = 0
        # `ActorStatisticsComponent @+0x8c` / `@+0x88` — cf. la docstring de classe (blocs
        # `blocks_made_this_turn` et `blocks_made_this_battle`).
        self.blocks_made_this_turn = 0
        self.blocks_made_this_battle = 0
        # `Nullable<UnitPositionId>` a `+0xa8` du composant que `IdunBattle.Operations.
        # MoveUnitOperation$$Execute` ET `IdunBattle.Operations.OverrideMovementTargetOperation$$
        # Execute` recuperent tous DEUX par la MEME paire de caches (#448-r1) -- la DESTINATION
        # EFFECTIVE du mouvement en cours. Ce n'est PAS un champ « libre » : c'est un canal
        # in/out d'UNE SEULE Operation, et sa duree de vie tient dans un `MoveUnitOperation` :
        #
        #     MoveUnitOperation$$Execute :
        #         comp.MovementTargetOverride = Nullable(UnitPositionId(position))   # POSE
        #         SetReservation(unit, position)
        #         if (!options.skipPreMoveTriggers) {                                # +0x12
        #             publish On(0x1f = PreUnitMove)          <- un trigger peut ECRASER le champ
        #             if (!TilesAreEmpty(unit, position)) { RemoveReservation ; return }
        #         }
        #         ovr = comp.MovementTargetOverride ; comp.MovementTargetOverride = null  # CONSOMME
        #         if (!ovr.HasValue || IsDead(unit)) { RemoveReservation ; return }
        #         if (ovr.Value.ToUnitPosition() != position) {
        #             RemoveReservation(position) ; options.skipPreMoveTriggers = true
        #             return Execute(unit, <la nouvelle position>, trig, options)   # RECURSION
        #         }
        #         ... suite normale du mouvement ...
        #
        # SEUL ECRIVAIN EXTERNE : `OverrideMovementTargetOperation$$Execute`, elle-meme atteinte
        # par la SEULE feuille `IdunBattleLogic.Entities.DSLBehaviors$$OverrideUnitMovementTarget`
        # (`OverrideUnitMovementTargetBehaviour$$Execute`, vslot 0x49 du processor). Son unique
        # call-site du build est `...StormboyzStrike_MissAbility$$CreateBehaviour`.
        # `None` = aucun mouvement en cours (l'etat au repos) ; `(col, row)` = la destination.
        # ⚠ L'identite NOMMEE du composant natif porteur n'est PAS resolue : le `Copy` de
        # `IdunBattle.Entities.Components.UnitComponent` ne montre pas ce champ (il est value-type,
        # donc deja couvert par le `MemberwiseClone`), mais son `Nullable<AttackHit>` occupe
        # exactement `+0x98..+0xa7`, ce qui laisse `+0xa8` libre pour un `Nullable` de 16 octets.
        # Le port le loge ici comme il loge deja `ActorStatisticsComponent` (meme residu
        # structurel) ; `pending_revive` ci-dessus cite le MEME offset pour un AUTRE composant --
        # les deux paires de caches natives sont distinctes, il n'y a pas de collision.
        self.movement_target_override: Optional[tuple] = None

    def add_foot(self, tile: tuple) -> None:
        """`IdunBattle.Entities.Components.UnitComponent$$AddFoot(footId)` = `_feet.Add(footId)`
        (`OrderedSet` -> pas de doublon, ORDRE d'insertion conserve) + invalidation du cache
        d'enumerateur @+0x80. Le port ajoute la TUILE du pied (collapse documente en tete)."""
        t = (int(tile[0]), int(tile[1]))
        if self.feet is None:
            self.feet = []
        if t not in self.feet:                       # OrderedSet.Add : idempotent
            self.feet.append(t)

    def clear_feet(self) -> None:
        """`IdunBattle.Entities.Components.UnitComponent$$ClearFeet` = `_feet.Clear()` +
        invalidation du cache @+0x80. Appele par `AddUnitOperation$$Execute` AVANT de reposer les
        pieds. Ici : liste VIDE (et non `None` -- `None` veut dire « un seul pied a la
        PositionComponent », ce qui n'est pas la meme chose qu'une unite sans pied)."""
        self.feet = []


class OwnerComponent(Component):
    """Propriétaire — `OwnerComponent` IdunBattle.Entities.Components.OwnerComponent$$.ctor. `team` = équipe (1/2) ; `player` = id du player
    (≠ team : team 1 = player 3, team 2 = player 4 ; un summon hérite team ET player du caster via
    `SpawnUnitOptions.CopyOwner`, cf. project_summon_team_model). `player` None si non capté."""
    __slots__ = ("team", "player")

    def __init__(self, team: Optional[int], player: Optional[int] = None):
        self.team = team
        self.player = player


class MachineComponent(Component):
    """MACHINE OF WAR — `IdunBattle.Entities.Components.MachineComponent` (entité `EntityType.Machine`
    = 6, créée par `IdunBattle.Operations.AddMachineOperation$$Execute`). Comme `UnitComponent`, dérive de
    `BaseUnitComponent IdunBattle.Entities.Components.BaseUnitComponent$$.ctor` (d'où `VisualId`@0x20 valide sur les deux) ; son champ propre est
    `Position` @0x78 = `MachineOfWarPosition` (enum None=0 / Top=1 / Bottom=2), le SLOT de déploiement
    hors-plateau (le board doit l'offrir : `IdunBattle.Configuration.BoardConfiguration$$HasMachineOfWarPosition`).

    C'est le DISCRIMINANT « cette entité est une MoW » : une MoW n'a **ni `PositionComponent` ni
    `HealthComponent`** (mesuré via `dumpEntityComponents` sur l'entité Machine vivante) — elle n'est
    pas sur la grille et n'a pas de PV. Ses plateformes (`EntityType.MachinePlatform` = 7) portent le
    lien retour `MachinePlatformComponent.MachineId` (Nullable @+0x14 hasValue / @+0x18 value).

    Le port n'a pas de type d'entité : `UnitComponent` porte l'identité (rôle `BaseUnitComponent`) et
    CE composant marque la nature Machine + le slot.

    `removed` (#91) = la MoW a été RETIRÉE de la bataille par
    `IdunBattle.Operations.RemoveMachineOperation$$Execute` (`RemoveMachineFromPlatform` + event
    `0x2e` + `RemoveEffects`). Le natif ne détruit pas l'entité : il la détache de sa plateforme, ce
    qui la rend indisponible pour le reste du combat (i2 `DutyEternal` : « Galatian can no longer be
    used as a Machine of War for the rest of the battle »). Le port matérialise ce détachement par
    ce drapeau — c'est le pendant `MachineComponent` du `alive=False` d'une unité."""
    __slots__ = ("slot", "removed")
    SLOT_NONE = 0
    SLOT_TOP = 1
    SLOT_BOTTOM = 2

    def __init__(self, slot: Optional[int] = None, removed: bool = False):
        self.slot = slot
        self.removed = bool(removed)


def is_machine_of_war(entity) -> bool:
    """True si l'entité est une MACHINE OF WAR (porte un `MachineComponent`). Mirror du test natif
    de type d'entité (`EntityType.Machine` = 6) — le port n'ayant pas de champ `type` sur l'entité,
    la PRÉSENCE du composant Machine joue ce rôle (le natif ne le pose que sur les Machines)."""
    return entity is not None and entity.get_component(MachineComponent) is not None


class PositionComponent(Component):
    """Position sur le board — `PositionComponent` IdunBattle.Entities.Components.PositionComponent$$.ctor (et `UnitFootComponent`
    IdunBattle.Entities.Components.UnitFootComponent$$.ctor : UnitId@0x10, TileId@0x14). Coordonnées hex (col,row)."""
    __slots__ = ("col", "row")

    def __init__(self, col: int, row: int):
        self.col = col
        self.row = row


class HealthComponent(Component):
    """PV — `HealthComponent` IdunBattle.Entities.Components.HealthComponent$$.ctor. `hp` courant, `hp_max` plafond.

    `minimal_health` = **plancher de PV** courant (`Nullable<int>` natif @+0x1c ; None = pas de plancher).
    Posé/effacé par le HP-floor `HypersensoryAbilities_MinimalHealthEffect` (Apply IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$ApplyInternal / Revert
    IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$RevertInternal) — quand présent, `reduce()` empêche les PV de descendre sous `min(hp, minimal_health)`
    (mirror du clamp de `IdunBattle.Entities.Components.FillUpStatComponent$$Reduce`).

    `over_reduce` = **l'accumulateur de sur-reduction** `FillUpStatComponent+0x24` (#462-r4e-o-r1) :
    `Reduce` y ajoute `Math.Max(0, damage - applied)` -- le degat qui n'a PAS pu etre retire faute de
    PV. Son NOM vient du natif : `IdunBattle.Entities.Components.FillUpStatComponent$$ResetOverReduce`
    est la seule autre fonction qui le touche (`this+0x24 = 0`), et elle n'a **AUCUN xref de code**
    (table de methodes seule) -> le compteur n'est JAMAIS remis a zero en bataille. Il n'est de toute
    facon non nul que sur une unite deja tombee a 0 PV (tant qu'elle encaisse, `damage == applied`).

    Il est LOAD-BEARING, et c'est une MESURE : la surcharge d'instance d'
    `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` l'AJOUTE au degat compare
    (`accum += (targetHealthBeforeAttack - GetStat(Health)) + healthComponent@+0x24`). Sans lui, le
    port pose `UnitFlag.Overkilled` un coup TROP TARD -- mesure live MC1_67/31337 `--hp-target 4000` :
    natif `[3583, 417, 0]`, port `[3583, 417, 0, 0]`.

    ⚠ `Reduce` **saute** l'accumulation quand le plancher `Minimum` est pose ET `> 0` (branche
    `if (0 < minimum) goto LAB_18107e699`) -- le meme gate qui rend `IsOverkill` faux sous plancher."""
    __slots__ = ("hp", "hp_max", "minimal_health", "over_reduce")

    def __init__(self, hp: Optional[int], hp_max: Optional[int], minimal_health: Optional[int] = None,
                 over_reduce: int = 0):
        self.hp = hp
        self.hp_max = hp_max
        self.minimal_health = minimal_health
        self.over_reduce = int(over_reduce or 0)

    def reduce(self, amount: int, *, ignore_minimal: bool = False) -> int:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$Reduce` — retire `amount` PV, borné : jamais > PV courant (pas de
        PV négatifs) et, si `minimal_health` est posé et `ignore_minimal` est faux (param_3 natif = flag de
        bypass), jamais sous `min(hp, minimal_health)` (le HP-floor Hypersensory). Renvoie la réduction RÉELLE
        appliquée (`iVar3`). No-op (0) si `hp` non capté. Mute `self.hp` — **et `self.over_reduce`**
        (#462-r4e-o-r1) : la queue de `Reduce` fait `this[0x24] += Math.Max(0, damage - applied)`,
        SAUF si le plancher `Minimum` est posé et `> 0` (le `goto LAB_18107e699` du décompilé)."""
        if self.hp is None:
            return 0
        amount = max(0, int(amount))                    # Max(0, param_2)
        red = min(amount, self.hp)                       # Min(iVar2, current) — pas de PV négatifs
        if not ignore_minimal and self.minimal_health is not None:
            floor = min(self.hp, int(self.minimal_health))   # Min(current, minimalHealth.Value)
            red = min(self.hp - floor, red)              # Min(current - floor, iVar3) — clamp au plancher
        self.hp -= red
        if not (self.minimal_health is not None and int(self.minimal_health) > 0):
            self.over_reduce = int(self.over_reduce or 0) + max(0, amount - red)
        return red


class EffectsOwnedComponent(Component):
    """Effets actifs portés — `EffectsOwnedComponent` IdunBattle.Entities.Components.EffectsOwnedComponent$$.ctor (chaque effet =
    `EffectComponent` IdunBattle.Entities.Components.EffectComponent$$.ctor). Ici : liste des NOMS d'effets actifs (vue pour le
    diff structurel). Le détail STRUCTURÉ (type/durée/params, matérialisé + évoluable)
    vit dans `State.effects` (`EffectsState`), source des modifiers de dégât."""
    __slots__ = ("effects",)

    def __init__(self, effects: List[str]):
        self.effects = effects


class ShieldInstance:
    """Une instance de bouclier (élément de la liste d'un `ShieldComponent`). Offsets natifs (RE
    `ShieldComponent.*`) : `id`@+0x10, source `AbilityOrEffect`@+0x14, `amount`@+0x30, `remaining`
    Nullable<int>@+0x3c (**None = permanent** = pas de durée → non tické par `RemoveOneTurn`).
    `source` = identité de l'ability/effet source (nom ; sert au merge `AddOrUpdateShield` ; None pour les
    boucliers CAPTÉS dont la source n'est pas lue)."""
    __slots__ = ("shield_id", "amount", "remaining", "source")

    def __init__(self, shield_id: int, amount: int, remaining: Optional[int], source=None):
        self.shield_id = shield_id
        self.amount = int(amount)
        self.remaining = remaining        # None = permanent
        self.source = source


class ShieldComponent(Component):
    """`IdunBattle.Entities.Components.ShieldComponent` IdunBattle.Entities.Components.ShieldComponent$$.ctor — pool de boucliers de l'unité
    (liste d'instances @+0x10 + compteur d'id @+0x18). Un bouclier ABSORBE le dégât AVANT les PV
    (`CalculateDamageOperation` : shield-first, sur le coup déjà réduit par l'armure fixe), et perd 1
    tour à chaque `EndTurn` (`RemoveOneTurnOnShields` → `RemoveOneTurn`). `GetTotalShield` = somme des
    `amount` (>0)."""
    __slots__ = ("shields", "next_id")

    def __init__(self, shields: Optional[List["ShieldInstance"]] = None, next_id: int = 0):
        self.shields: List[ShieldInstance] = shields if shields is not None else []
        self.next_id = next_id

    def get_total_shield(self) -> int:
        """`IdunBattle.Entities.Components.ShieldComponent$$GetTotalShield = Σ des `amount` des instances."""
        return sum(int(s.amount) for s in self.shields if s.amount > 0)

    def remove_one_turn(self) -> dict:
        """`IdunBattle.Entities.Components.ShieldComponent$$RemoveOneTurn : pour chaque instance À DURÉE (remaining non-None ;
        les permanentes sont sautées, gate `HasValue` @+0x3c), décrémente `remaining` ; si 0 → l'instance
        EXPIRE (retirée). Renvoie {removed:[ids], decremented:[ids]} (= `ShieldChanges`)."""
        removed: List[int] = []
        decremented: List[int] = []
        for s in list(self.shields):
            if s.remaining is None:                  # permanent → non tické
                continue
            s.remaining -= 1
            if s.remaining <= 0:
                removed.append(s.shield_id)
                self.shields.remove(s)
            else:
                decremented.append(s.shield_id)
        return {"removed": removed, "decremented": decremented}

    def add_or_update_shield(self, amount: int, source=None,
                             remaining: Optional[int] = None) -> Optional["ShieldInstance"]:
        """`IdunBattle.Entities.Components.ShieldComponent$$AddOrUpdateShield : accorde un bouclier. Si une instance de MÊME
        source ET MÊME durée restante existe → **cumule** l'`amount` (stack, branche `+= param_2`) ; sinon
        crée une nouvelle instance (id auto-incrémenté @+0x18). No-op si `amount<=0`. Renvoie l'instance.
        (Le tri d'insertion par durée croissante + la branche replace sans-durée = raffinements ;
        l'essentiel — id unique, stack même-source, total — est porté.)"""
        amount = int(amount)
        if amount <= 0:
            return None
        for s in self.shields:
            if s.source == source and s.remaining == remaining:
                s.amount += amount
                return s
        inst = ShieldInstance(self.next_id, amount, remaining, source=source)
        self.shields.append(inst)
        self.next_id += 1
        return inst

    def deplete(self, amount: int) -> int:
        """Absorption : retire jusqu'à `amount` PV de bouclier des instances. Le TOTAL absorbé est exact
        (= `min(amount, GetTotalShield)`) ; l'ATTRIBUTION par instance = ordre de liste (le natif insère
        trié par durée croissante ; l'ordre de déplétion exact = `ApplyDamageOperation`, non RE → front,
        approximation documentée n'affectant que QUELLE instance expire la première). Renvoie l'absorbé."""
        left = int(amount)
        for s in self.shields:
            if left <= 0:
                break
            take = min(s.amount, left)
            s.amount -= take
            left -= take
        self.shields = [s for s in self.shields if s.amount > 0]
        return int(amount) - left


class ForcedAttackTargetsComponent(Component):
    """`IdunBattle.Entities.Components` — cibles d'attaque FORCÉES de l'unité (liste d'ids d'entité).

    Posé/maj par `IdunBattle.Entities.Behaviours.AddForcedAttackTargetBehaviour$$Execute / retiré par
    `IdunBattle.Entities.Behaviours.RemoveForcedAttackTargetBehaviour$$Execute (le natif stocke des entity-ids dans une liste
    de composant bond @+0x50/+0x58). LU par `IdunBattle.Entities.Selectors.UnitForcedAttackTargetsSelector$$Select
    et surtout par `IdunBattle.Entities.UnitExtensions$$GetOnlyTargets` — le lecteur qu'interrogent
    la RÈGLE DE CIBLAGE `TargetIsAllowedForCaster` (bit 23, cf.
    `engine/runner/abilities/targeting.py::get_only_targets`), `TargetingQuery$$GetPossibleTargetsForOptions`
    et `MovementActionGenerator.<FindClosestEnemy>d__8$$MoveNext` (l'IA **doit** cibler ces unités ;
    cf. `GetAttackTarget` priorité `ForcedAttackTargets > nearest-enemy`, triggers.py).

    QUATRE ÉCRIVAINS NATIFS, relus (#436) :
      1. `IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` — **liste := [BondedEntityId]**
         (REMPLACE, ne fusionne pas). C'est le TAUNT (effet 27 `Taunted_OnlySpecificTargets`).
      2. `IdunBattle.Entities.Effects.TauntedEffect$$RevertInternal` — **liste := []** (vidée).
      3. `AddForcedAttackTargetBehaviour$$Execute` — `Add` incrémental (unique constructeur :
         `InstinctiveBehaviour_UpdateTargetAbility$$CreateBehaviour`, non porté).
      4. `RemoveForcedAttackTargetBehaviour$$Execute` — `Remove` (porté : `RemoveAllForcedAttackTargets`).

    `written_by` = l'INSTANCE d'effet dont l'écriture (voie 1) a produit la liste courante. Le port
    matérialise ce lien parce que le NET natif « effet 27 retiré ⇒ liste vidée » (voies 1+2) est
    maintenu côté natif par `DeactivateEffect -> RevertInternal`, par où passe TOUT retrait ; côté
    port un effet peut disparaître par plusieurs chemins (`remove_effect_instance`, l'expiration de
    timer d'`EffectsState.on_turn_end`, une poignée de `consumed = True` ad hoc) dont un seul est un
    foyer. Une mutation posée au seul foyer serait DÉSYNCHRONISÉE, et une liste fantôme fait REFUSER
    un cast que le natif accepte — dégradation RESTRICTIVE, l'exact inverse de la convention
    permissive du gate de cible. `get()` honore donc `written_by.consumed`, ce qui rend le
    `RevertInternal` quel que soit le chemin de retrait.

    ⚠ ÉCART NOMMÉ : `RevertInternal` natif VIDE la liste entière (y compris ce qu'un `Add` de la
    voie 3 y aurait mis) ; ici seule l'écriture de CET effet est annulée. Aucun porteur — la voie 3
    n'a aucun écrivain porté (ses 23 porteurs sont les summons Tyranides à trait
    `InstinctiveBehaviour`), donc les deux voies ne coexistent nulle part offline.

    On clé par id d'UNITÉ (== ECS), comme le reste du runner."""
    __slots__ = ("targets", "written_by")

    def __init__(self, targets: Optional[List[int]] = None, written_by=None):
        self.targets: List[int] = list(targets) if targets else []
        self.written_by = written_by

    def add(self, target_id: int) -> bool:
        """Ajoute une cible forcée (idempotent). Renvoie True si ajoutée (absente avant).
        Mirror de la voie 3 (`AddForcedAttackTargetBehaviour`) : écriture INCRÉMENTALE, non liée à un
        effet -> `written_by` reste ce qu'il est (aucun écrivain-effet ne coexiste, cf. l'écart nommé)."""
        if target_id in self.targets:
            return False
        self.targets.append(int(target_id))
        return True

    def remove(self, target_id: int) -> bool:
        """Retire une cible forcée. Renvoie True si présente."""
        if target_id in self.targets:
            self.targets.remove(target_id)
            return True
        return False

    def set_only(self, target_ids: List[int]) -> dict:
        """Remplace l'ensemble des cibles forcées (mirror du net `Remove(old−new) + Add(new−old)` de
        `InstinctiveBehaviour_UpdateTargetAbility.CreateBehaviour`). Renvoie {added, removed}."""
        new = [int(t) for t in (target_ids or [])]
        added = [t for t in new if t not in self.targets]
        removed = [t for t in self.targets if t not in new]
        self.targets = new
        return {"added": added, "removed": removed}

    def set_from_effect(self, effect, target_ids: List[int]) -> None:
        """`IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal`, queue VERBATIM :

            comp = target.GetComponent<ForcedAttackTargetsComponent>();
            list = new List<int>();
            list.Add(<displayClass+0x18> = ABondEffect.BondedEntityId(effect));
            comp.<+0x50> = list;                     // REMPLACE la liste

        `effect` = l'instance qui écrit (cf. `written_by`)."""
        self.targets = [int(t) for t in (target_ids or [])]
        self.written_by = effect

    def clear(self) -> List[int]:
        """Vide la liste ET délie l'écrivain-effet. Renvoie ce qui a été retiré.

        Deux call-sites natifs distincts convergent ici : `TauntedEffect$$RevertInternal`
        (`comp.<+0x50> = new List<int>()`) et le `Remove` de tous les ids par
        `RemoveForcedAttackTargetBehaviour$$Execute`. Délier `written_by` est LOAD-BEARING pour le
        second : après un `RemoveAllForcedAttackTargets`, l'effet 27 peut être ENCORE actif et sa
        liste ne doit PAS repousser (le natif n'a pas de re-écriture — `ApplyInternal` ne se rejoue
        pas)."""
        removed = list(self.targets)
        self.targets = []
        self.written_by = None
        return removed

    def get(self) -> List[int]:
        """La liste EFFECTIVE. Rend `[]` si l'effet écrivain a disparu (mirror de `RevertInternal`,
        cf. `written_by`)."""
        if self.written_by is not None and getattr(self.written_by, "consumed", False):
            return []
        return list(self.targets)


class UnitFlagsComponent(Component):
    """`IdunBattle.Entities.Components.UnitFlagsComponent` IdunBattle.Entities.Components.UnitFlagsComponent$$.ctor — drapeaux booléens de l'unité
    (un `OrderedSet<int>` @+0x10 ; `Add`/`Remove`/`Has`/`TurnEnded`/`RemoveTurnFlags`). Valeurs = enum
    `IdunBattle.Entities.Enum.UnitFlag` (dump symbols.json) ; on porte le set d'ints (sémantique 1:1).

    Flags de TOUR (mission #139 — cycle posé/appliqué/reset, VAs) :
      • `TURN_FINISHED (3)` : le tour de l'UNITE est fini — posé par `IdunBattle.Operations.FinishUnitTurnOperation$$Execute (déclenché après une ability qui « termine le tour », cf. abilities/handler.py) ; lu par
        `IdunBattle.Entities.Components.UnitFlagsComponent$$TurnEnded (= Contains(3)) via `VerifyUnitsTurnFinishedOperation.
        IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded et `IdunBattle.Core.Services.AttackQuery$$CanAttackAnyUnitFromAnyTileWithAnyAbility+0xec.
      • `ACTIVE_ABILITY_USED (2)` : une ability active a été utilisée ce tour — posé par
        `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution ; base du trigger DSL
        `HasOwnersActiveAbilityBeenUsed` (DSLFactory+0x110).
      • `ARRIVED_AT_FINAL_TILE (1)` : posé avec TURN_FINISHED par FinishUnitTurnOperation.
      • `NO_ACTION_AVAILABLE (4)` : auto-fin (rien à faire) — posé par `MarkUnitAsNoActionAvailableOperation`
        IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation$$Execute+0xdc ; ré-ouvert par VerifyUnitTurnEnded (slot 0x77) si l'unité regagne des options.
      • `FLED (9)` : « a fui » (FleeOperation ; re-testé NOT HasFlag(self,9) par BattleFatigue).
      • `TURN_FINISHED_FORCED (27 = 0x1b)` : posé par FinishUnitTurnOperation quand `forced` (hors enum du
        dump — ajout post-dump ; nom descriptif, structure lue IdunBattle.Operations.FinishUnitTurnOperation$$Execute/IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags)."""
    __slots__ = ("flags",)
    MOVED = 0                   # UnitFlag.Moved (posé par IdunBattle.Entities.UnitExtensions$$SetMovedFlag)
    ARRIVED_AT_FINAL_TILE = 1   # UnitFlag.ArrivedAtFinalTile
    ACTIVE_ABILITY_USED = 2     # UnitFlag.ActiveAbilityUsed
    TURN_FINISHED = 3           # UnitFlag.TurnFinished
    NO_ACTION_AVAILABLE = 4     # UnitFlag.NoActionAvailable
    FLED = 9                    # UnitFlag.Fled — « a fui » ce tour
    OVERKILLED = 8              # UnitFlag.Overkilled — pose par `IdunBattle.Operations.ApplyDamageOperation$$Execute`
                                # +0x17d5 (`if (result.didOverkill) UnitFlagsComponent.Add(target, 8)` — le
                                # `mov edx,8` precede immediatement le call, lu au desassemblage) ; RETIRE par
                                # `IdunBattle.Operations.ReviveUnitOperation$$Execute+0x7e0` (Remove(8)).
                                # Lu par `IdunBattleLogic.Entities.DSLFactory$$HasFlag(unit, 8)` — volet
                                # OVERKILL de `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$ExecuteBehaviour`.
    TELEPORTED = 12             # UnitFlag.Teleported
    AMBUSH_CONSUMED = 14        # flag 0xe (UnitPostAbility) — G3 : Ambush ré-suscité UNE fois ; posé par
                                # `ResurrectUnitOperation` (Add 0xe), testé `Not(HasFlag 0xe)` par les 2 triggers
                                # Ambush → résurrection one-shot. PERMANENT : survit à `remove_turn_flags` (pas un
                                # flag de tour), donc re-mourir ne re-déclenche PAS une 2e résurrection.
    PREVENT_OVERKILL = 19       # flag 0x13 (`UnitFlag.PreventOverkill`, enums.tsv) — pose par
                                # `IdunBattle.Entities.Effects.Loki.FuelledByFury_BlockOverkillEffect$$
                                # ApplyInternal` (`UnitFlagsComponent.Add(u, 0x13)`) et retire par son
                                # `$$RevertInternal`. Lu par la surcharge d'INSTANCE de
                                # `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` (`suppress`) :
                                # tant qu'il est pose, la cible ne peut pas etre overkillee (ultraTitus,
                                # i2 « the first time each turn that Titus is defeated he cannot be
                                # Overkilled »). Offline il est DERIVE de l'effet porteur — cf.
                                # `unit_prevents_overkill`.
    REMOVED = 26                # flag 0x1a (`UnitFlag.Removed`, enums.tsv) — l'unite a ete RETIREE du
                                # plateau (despawn, PAS une mort : ni PV touches ni flag `Dead`).
                                # Pose par `IdunBattle.Operations.RemoveUnitOperation$$Execute` juste
                                # AVANT sa publication d'`On(0x25 = UnitRemoved)`, et relu en TETE de
                                # la meme fonction comme gate anti-double-retrait
                                # (`IdunBattle.Entities.UnitExtensions$$HasFlag(entity, 0x1a)`).
                                # RETIRE par `IdunBattle.Operations.ResurrectUnitOperation$$Execute`
                                # (`Remove(6)/Remove(0xf)/Remove(8)/**Remove(0x1a)**/Remove(9)`).
                                # Cf. `runner/operations/remove_unit.py`.
    TURN_FINISHED_FORCED = 27   # flag 0x1b (FinishUnitTurnOperation forced=True ; hors enum dump)

    def __init__(self, flags=None):
        self.flags = set(int(f) for f in flags) if flags else set()

    def add(self, flag: int) -> None:
        self.flags.add(int(flag))

    def remove(self, flag: int) -> None:
        self.flags.discard(int(flag))

    def has(self, flag: int) -> bool:
        return int(flag) in self.flags

    def turn_ended(self) -> bool:
        """`IdunBattle.Entities.Components.UnitFlagsComponent$$TurnEnded = Contains(TurnFinished=3). Lu par le turn-flow natif
        (IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded) et par l'AttackQuery pour exclure les unités finies."""
        return self.TURN_FINISHED in self.flags

    def remove_turn_flags(self, include_no_action: bool = False, new_activation: bool = True) -> set:
        """`IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags : retire TOUJOURS {ActiveAbilityUsed(2),
        TurnFinished(3), 27} ; + {NoActionAvailable(4)} si `include_no_action` (param_3 natif) ;
        + {Moved(0), Teleported(12), ArrivedAtFinalTile(1)} si `new_activation` (param_4 natif).
        `IdunBattle.Operations.StartTurnOperation$$Execute l'appelle (0, 1) pour chaque unité du joueur entrant.

        RETOUR = les flags EFFECTIVEMENT retirés (ceux qui étaient présents). Le natif rend une STRUCT
        de 7 bools (`IdunBattle.Entities.Components.UnitFlagsComponent$$Remove rend « était présent » ; offsets +5=Moved(0), +0=Teleported(0xc),
        +6=ArrivedAtFinalTile(1), +1=NoActionAvailable(4), +2=ActiveAbilityUsed(2), +3=TurnFinished(3),
        +4=TurnFinishedForced(0x1b)) — struct consommée par `IdunBattle.Operations.ComputerActionOperation$$SetUnitTurnsFlags qui les RE-POSE une à une (restauration exacte du turn-state après une action AI
        forcée, cf. `runner/operations/summon_ai.py`). Le port rend le SET des flags retirés (la struct
        n'est qu'un bitset « était présent » ; l'ordre des `Add` de la restauration est indifférent).
        Les appelants historiques ignorent le retour (aucun changement de comportement)."""
        removed: set = set()

        def _rm(f):
            if f in self.flags:
                self.flags.discard(f)
                removed.add(f)

        if new_activation:
            for f in (self.MOVED, self.TELEPORTED, self.ARRIVED_AT_FINAL_TILE):
                _rm(f)
        if include_no_action:
            _rm(self.NO_ACTION_AVAILABLE)
        for f in (self.ACTIVE_ABILITY_USED, self.TURN_FINISHED, self.TURN_FINISHED_FORCED):
            _rm(f)
        return removed


class StatsComponent(Component):
    """Bloc de stats de combat RÉSOLUES de l'unité (Attack, FixedArmor, ExtraHits,
    ExtraPierce, crit/block, AbilityVariablesMultiplier, niveau d'ability…) + config
    d'arme de l'attaque normale. Porte le `UnitContext` validé (`engine.entities`),
    assemblé depuis `combatSnapshot` (stats one-shot) + gameconfig.

    C'est la SOURCE de la plage de tirage de dégât (`base = stat Attack`, spread BC),
    qui rend le runner autonome (calcul de la plage sans relecture live). Natif : les
    stats sont stockées sur l'unité (StatComponents) et lues par `BattleQuery`."""
    __slots__ = ("ctx",)

    def __init__(self, ctx: "UnitContext"):
        self.ctx = ctx


class TriggeredAbilityState:
    """Une entrée du `TriggeredAbilityComponent` (une ability/trigger de l'unité). Offsets natifs
    (RE `IdunBattle.Entities.Components.TriggeredAbilityComponent$$MarkAsTriggered / `IdunBattle.Entities.Components.TriggeredAbilityComponent$$GetTimesTriggeredThisPhase) :
    `has_triggered`@+0x2c (bool, `HasBeenTriggered`), `total`@+0x30 (compteur cumulé toutes phases),
    `times_this_phase`@+0x34 (compteur de la phase courante ; lu par le cap `<51`, remis à 0 par
    `ResetPhase`). (Le natif porte aussi la clé/config-id @+0x10.. et le niveau @+0x38 ; ici on ne modèle
    que les 3 compteurs — le seul état lu par le gate de trigger.)"""
    __slots__ = ("has_triggered", "total", "times_this_phase")

    def __init__(self):
        self.has_triggered = False
        self.total = 0
        self.times_this_phase = 0


class TriggeredAbilityComponent(Component):
    """`IdunBattle.Entities.Components.TriggeredAbilityComponent` IdunBattle.Entities.Components.TriggeredAbilityComponent$$.ctor — registre par-unité des
    ability-triggers, avec leur compteur de déclenchements. Native = `KeyedCollection` @+0x18 indexée par
    l'ability-type (config-id) ; chaque entrée porte `has_triggered`/`total`/`times_this_phase`
    (cf. `TriggeredAbilityState`).

    RÔLE : le natif GATE chaque déclenchement de trigger à `GetTimesTriggeredThisPhase(key) < 0x33`
    (=51) dans `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger (cap anti-emballement d'une
    PHASE = une activation d'unité) ; `MarkAsTriggered` incrémente au fire ; `ResetPhase` (via
    `IdunBattle.Operations.EndPhaseOperation$$ResetEntityPhase, à la fin de chaque activation) remet
    `times_this_phase` à 0 (PAS `total`). Sans ce cap, une chaîne de triggers générateurs d'attaque
    (splash Psyker qui re-déclenche le splash Psyker via le vecteur after-hit) récurserait sans borne.

    Peuplé au build de l'unité pour CHAQUE ability (natif `UnitFactory.Add*Abilities` → `IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd). Offline : clé = un identifiant stable d'ability-type (cf. Slice 2). Population +
    gate + reset = slices #142/#143/#144."""
    __slots__ = ("entries",)

    def __init__(self, entries: Optional[Dict[Hashable, "TriggeredAbilityState"]] = None):
        self.entries: Dict[Hashable, TriggeredAbilityState] = entries if entries is not None else {}

    def try_add(self, key: Hashable) -> bool:
        """`IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd : enregistre l'ability `key` si absente (compteurs à 0). No-op (renvoie
        False) si déjà présente ; True si ajoutée."""
        if key in self.entries:
            return False
        self.entries[key] = TriggeredAbilityState()
        return True

    def get_times_triggered_this_phase(self, key: Hashable) -> int:
        """`IdunBattle.Entities.Components.TriggeredAbilityComponent$$GetTimesTriggeredThisPhase : compteur de la phase courante pour `key` ; **0 si
        la clé est absente** (TryGetValue échoue → 0)."""
        e = self.entries.get(key)
        return e.times_this_phase if e is not None else 0

    def mark_as_triggered(self, key: Hashable) -> None:
        """`IdunBattle.Entities.Components.TriggeredAbilityComponent$$MarkAsTriggered : `has_triggered=True`, `total += 1`, `times_this_phase += 1`.
        **No-op si la clé est absente** (le natif TryGetValue échoue et `return`)."""
        e = self.entries.get(key)
        if e is None:
            return
        e.has_triggered = True
        e.total += 1
        e.times_this_phase += 1

    def has_been_triggered(self, key: Hashable) -> bool:
        """`IdunBattle.Entities.Components.TriggeredAbilityComponent$$HasBeenTriggered : True si l'ability a déjà été déclenchée (any phase). False si
        clé absente."""
        e = self.entries.get(key)
        return bool(e.has_triggered) if e is not None else False

    def reset_phase(self) -> None:
        """`IdunBattle.Entities.Components.TriggeredAbilityComponent$$ResetPhase : remet `times_this_phase` à 0 pour TOUTES les entrées (le `total` et
        `has_triggered` sont conservés). Appelé au boundary d'activation (`EndPhaseOperation`)."""
        for e in self.entries.values():
            e.times_this_phase = 0


class ActiveAbility:
    """`IdunBattle.Entities.Components.ActiveAbility` -- UNE entree d'ability active de l'unite. Champs
    portes = ceux que le canal live expose (`readAbilityState`, `frida/hooks/features/ai-step/
    internals.ts`, offsets resolus PAR NOM sur la classe native) :

        CanStillBeUsed         @0x28  -> `can_still_be_used`   (l'ability a-t-elle encore une charge ?)
        RemainingCooldownTurns @0x2c  -> `remaining_cooldown`  (Nullable<int> ; None = pas de cooldown)
        IsDisabled             @0x35  -> `disabled`
        AmmoCost               @0x38  -> `ammo_cost`           (Nullable<int> ; None = pas de cout)
        HasEnoughAmmo          @0x40  -> `has_ammo`
        AbilityName            @0x44  -> `ability_type`        (ActiveAbilityType concret)
        _abilityState          @0x4c  -> `level` / `multiplier` (AbilityState PER-ABILITY, #100)

    `is_in_cooldown` = `IdunBattle.Entities.Components.ActiveAbility$$get_IsInCooldown` =
    `RemainingCooldownTurns.HasValue && Value > 0`."""
    __slots__ = ("ability_type", "kind", "can_still_be_used", "remaining_cooldown", "disabled",
                 "ammo_cost", "has_ammo", "level", "multiplier")

    def __init__(self, ability_type: int, kind: str = "active", can_still_be_used: bool = True,
                 remaining_cooldown=None, disabled: bool = False, level=None, multiplier=None,
                 ammo_cost=None, has_ammo: bool = True):
        self.ability_type = int(ability_type)
        self.kind = kind
        self.can_still_be_used = bool(can_still_be_used)
        self.remaining_cooldown = remaining_cooldown
        self.disabled = bool(disabled)
        self.ammo_cost = ammo_cost
        self.has_ammo = bool(has_ammo)
        self.level, self.multiplier = level, multiplier

    def is_in_cooldown(self) -> bool:
        """`IdunBattle.Entities.Components.ActiveAbility$$get_IsInCooldown` : `HasValue && Value > 0`."""
        return self.remaining_cooldown is not None and int(self.remaining_cooldown) > 0

    def can_currently_be_used(self) -> bool:
        """`IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed` -- la propriete
        COMPOSITE que le generateur d'action natif teste (`<GenerateActions>d__7`), a NE PAS confondre
        avec `CanStillBeUsed`@0x28 (le seul champ que le canal live nomme `usable`) :

            CanStillBeUsed(@0x28) && !IsDisabled(@0x35)
              && (!RemainingCooldownTurns(@0x2c).HasValue || Value < 1)
              && (!AmmoCost(@0x38).HasValue || HasEnoughAmmo(@0x40))

        Le 4e terme (MUNITIONS) n'a de mordant que sur les MACHINES OF WAR : leurs abilities portent
        un `munitionsCost` et le stock vit dans `BC.Player.Players[].MachineOfWarAmmo` (0 dans le seed
        BC). Mesure live (runner MoW `adeptExorcist`, session 4) : `1187` = `usable:true, hasAmmo:false`
        -> le natif ne la propose PAS et caste `1188` a la place. Sans ce terme, le port proposerait
        1187.

        CONFIRME le 2026-07-29 (`docs/rl/case-mow-ammo-gauge.md`) -- et le gate est bien DECISION-ONLY :
        a `MachineOfWarAmmo = 0`, un cast force par `applyAction` s'execute quand meme et pose ses
        effets (`SpendAmmoOperation$$Execute` echoue silencieusement). Le stock vit dans
        `PlayerComponent+0x6c`, il est pose UNE fois par `AddPlayerOperation$$Execute` depuis la BC et
        **aucune operation native ne l'incremente** : il ne remonte jamais en cours de bataille. Pour
        un scenario qui a besoin de munitions, patcher `MachineOfWarAmmo` dans un seed BC ecrit hors
        `data/`. ⚠ `usable` = `CanStillBeUsed@0x28` SEUL : il vaut `true` alors meme que l'ability est
        en cooldown initial -- ne jamais s'en servir comme composite."""
        if not self.can_still_be_used or self.disabled:
            return False
        if self.remaining_cooldown is not None and int(self.remaining_cooldown) >= 1:
            return False
        if self.ammo_cost is not None and not self.has_ammo:
            return False
        return True

    def __repr__(self) -> str:                                        # pragma: no cover
        return (f"ActiveAbility({self.ability_type}, {self.kind}, usable={self.can_still_be_used}, "
                f"cd={self.remaining_cooldown}, ammo={self.ammo_cost}/{self.has_ammo})")


class ActiveAbilitiesComponent(Component):
    """`IdunBattle.Entities.Components.ActiveAbilityComponent` -- la COLLECTION d'abilities actives de
    l'unite (`KeyedCollection<ActiveAbilityType, ActiveAbility>` @+0x20, iteree par
    `IdunBattle.Core.Services.BattleQuery$$EntityCanHaveActiveAbilityReset` et par
    `IdunBattle.Operations.ResetActiveAbilityOperation$$Execute`).

    SEEDE depuis `decisionView.units[].abilities` (canal `unitAbilityTypes` + `readAbilityState`, qui
    lit litteralement ces champs sur l'objet natif) -- les entrees `kind == "normal"` (l'attaque
    normale, poussee depuis `NormalAttackType` SANS objet `ActiveAbility`) sont EXCLUES : le natif les
    exclut aussi de la boucle de reset (`ActiveAbility.IsRegularAttack`). Le canal n'est peuple que si
    l'appelant demande `allAbilities: true` -> composant ABSENT sinon (degradation fidele et VISIBLE :
    les consommateurs rendent None plutot qu'un faux verdict, cf. `entity_can_have_active_ability_reset`)."""
    __slots__ = ("abilities",)

    def __init__(self, abilities=None):
        self.abilities: List["ActiveAbility"] = list(abilities or [])

    def get(self, ability_type: int) -> Optional["ActiveAbility"]:
        return next((a for a in self.abilities if a.ability_type == int(ability_type)), None)


class ActiveAbilityModificationsComponent(Component):
    """`IdunBattle.Entities.Components.ActiveAbilityModificationsComponent` IdunBattle.Entities.Components.ActiveAbilityModificationsComponent$$.ctor (.ctor) — registre
    par-unite des MODIFICATIONS de constantes/variables d'ability apportees par des sources TIERCES
    (`Dictionary<AbilityVarOrConst, ModificationConfig>` @+0x10).

      • `IdunBattle.Entities.Components.ActiveAbilityModificationsComponent$$Add(key, delta) : TryGetValue(key) -> `IdunBattle.Entities.Components.ActiveAbilityModificationsComponent.ModificationConfig$$Add(delta)
        (`value += delta` puis CLAMP `if (cap.HasValue && cap < value) value = cap` -- `cap` = le
        `Nullable<int>` @+4 de la struct, JAMAIS pose par les sources lues dans ce build -> None) ;
        cle absente -> cree une entree ZERO (`set_Item(key, default)`) puis re-appelle `Add`.
      • `IdunBattle.Entities.Components.ActiveAbilityModificationsComponent$$Get(key) : `TryGetValue(key) ? config.value : 0` -- **0 quand la cle est absente**.

    SOURCE NATIVE unique lue dans ce build : `IdunBattle.Operations.AddUnitActiveAbilityModificationOperation$$Execute` (= `Core.Services.OperationProcessor$$AddUnitActiveAbilityModification), appelee par
    `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$ApplyInternal (+ `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$RevertInternal, meme appel en
    `-value`) -- le passif de `astraSmnKell` qui buffe le SupremeCommander de son parent Creed.

    La chaine de POSE est desormais portee de bout en bout (#95-RESTE2) : `SwornProtector` (passif de
    `astraCreed`) fait apparaitre Kell -> `ListenUpMaggotsAbility` (`On(AbilityInit)`) pose l'effet
    0x426 sur Kell -> `ListenUpMaggotsEffect.ApplyInternal` ecrit les DEUX modifications sur
    `Parent(Kell)` = Creed. Le dict n'est donc plus condamne a rester vide.

    GROUND TRUTH LIVE (runner MC1_67, Creed attaque par `necroSpyder`, session 78) : Kell apparait
    VIVANT en portant `ListenUpMaggotsEffect`, et le cast SupremeCommander suivant spawne **3** gardes
    (= `nrOfSummons 2` + modification `+1`). L'ancienne note « meme avec Kell vivant le natif summon 2
    gardes » etait FAUSSE (les probes d'alors n'avaient pas de Kell survivant/effet applique).

    Les deux semantiques de CONSOMMATION restent distinctes (additive pour `nrOfSummons`, OVERRIDE si
    non nulle pour `range`, cf. `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour)."""
    __slots__ = ("modifications",)

    def __init__(self, modifications=None):
        self.modifications: dict = dict(modifications or {})

    def add(self, key, delta: int, cap=None) -> int:
        """`IdunBattle.Entities.Components.ActiveAbilityModificationsComponent$$Add + `IdunBattle.Entities.Components.ActiveAbilityModificationsComponent.ModificationConfig$$Add."""
        value = int(self.modifications.get(key, 0)) + int(delta)
        if cap is not None and int(cap) < value:      # clamp `Nullable<int>` @+4 (jamais pose in-build)
            value = int(cap)
        self.modifications[key] = value
        return value

    def get(self, key) -> int:
        """`IdunBattle.Entities.Components.ActiveAbilityModificationsComponent$$Get : valeur de la modification, 0 si absente."""
        return int(self.modifications.get(key, 0))


class PersistentDataComponent(Component):
    """`IdunBattle.Entities.Components.PersistentDataComponent` (.IdunBattle.Entities.Components.PersistentDataComponent$$.ctor) — sac de donnees
    persistantes PAR ENTITE, indexe par une cle composite. Natif = `Dictionary<key, value>` @+0x10 :
      • `PersistData<T>(key, value)` IdunBattle.Entities.Components.PersistentDataComponent$$PersistDatau003C__Il2CppFullySharedGenericStructTypeu003E / `TryGetPersistData<T>(key, out)` IdunBattle.Entities.Components.PersistentDataComponent$$TryGetPersistDatau003C__Il2CppFullySharedGenericStructTypeu003E ;
      • `IdunBattle.Entities.Components.PersistentDataComponent$$ClearPersistentData(key) = `Dictionary.Remove(key)` ;
      • `IdunBattle.Entities.Components.PersistentDataComponent$$ClearAllPersistentData() (appele par `IdunBattle.Operations.ResurrectUnitOperation$$ResetPersistentData+0x91 et `IdunBattle.Entities.Behaviours.ClearPersistentDataBehaviour$$ExecuteClearAll+0x1d).

    Cote DSL, les noeuds qui l'adressent sont `DSLFactory.SetPersistentData` (IdunBattleLogic.Entities.DSLFactory$$SetPersistentData et overloads),
    `IdunBattleLogic.Entities.DSLFactory$$IsPersistentData` (= `AmountIsEqualOrGreater(GetPersistentDataFormula(key,
    entity, dataKey) IdunBattle.Entities.Triggers.GetPersistentDataFormula$$Calculate, Direct(0)@0xb8)` -> « la cle est posee ») et
    `DSLFactory.ClearPersistentData` (IdunBattleLogic.Entities.DSLFactory$$ClearPersistentData/IdunBattleLogic.Entities.DSLFactory$$ClearPersistentData).

    Le port modelise le sac comme un dict `{cle: valeur}` sur l'unite. La CLE offline = le tuple
    `(abilityOrEffect, dataKey)` (mirror de la cle composite native : l'`AbilityOrEffect` passe a
    `SetPersistentData` + le `Get(<champ statique de l'ability>)` qui nomme la donnee).

    Consommateur porte : `LetTheGalaxyBurnAbility` (`runner/operations/triggers/loki/
    let_the_galaxy_burn.py`) — flag INTRA-ATTAQUE arme au `On(PreAttack=5)` et efface par
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour` en fin d'attaque."""
    __slots__ = ("data",)

    def __init__(self, data=None):
        self.data: dict = dict(data or {})

    def persist_data(self, key, value=1) -> None:
        """`PersistentDataComponent.PersistData<T>` IdunBattle.Entities.Components.PersistentDataComponent$$PersistDatau003C__Il2CppFullySharedGenericStructTypeu003E : pose/ecrase `key -> value`."""
        self.data[key] = value

    def try_get_persist_data(self, key):
        """`TryGetPersistData<T>` IdunBattle.Entities.Components.PersistentDataComponent$$TryGetPersistDatau003C__Il2CppFullySharedGenericStructTypeu003E : la valeur, ou None si la cle est absente."""
        return self.data.get(key)

    def clear_persistent_data(self, key) -> None:
        """`IdunBattle.Entities.Components.PersistentDataComponent$$ClearPersistentData(key) = `Dictionary.Remove(key)` (no-op si absente)."""
        self.data.pop(key, None)

    def clear_all_persistent_data(self, ability_or_effect=None) -> None:
        """Les DEUX overloads natifs de `ClearAllPersistentData` :
          * SANS argument (`IdunBattle.Entities.Components.PersistentDataComponent$$ClearAllPersistentData`,
            appele par `IdunBattle.Operations.ResurrectUnitOperation$$ResetPersistentData+0x91`) = vide
            TOUT le sac (resurrection) ;
          * AVEC un `abilityId` (l'autre overload, appele par
            `IdunBattle.Entities.Behaviours.ClearPersistentDataBehaviour$$ExecuteClearAll`) =
            `Dictionary.Remove(abilityId)` sur le dict @+0x10.

        ⚠ MODELE : le sac natif est un dict a DEUX niveaux (`abilityId -> (dataKey -> valeur)`), d'ou
        un `Remove(abilityId)` qui emporte TOUTES les dataKeys de cette ability -- c'est ce que dit
        « ClearAll ». Le port APLATIT en cle composite `(abilityOrEffect, dataKey)` ; l'overload a un
        argument balaie donc toutes les cles dont le PREMIER membre vaut `ability_or_effect`, ce qui
        est le meme observable."""
        if ability_or_effect is None:
            self.data.clear()
            return
        aid = int(ability_or_effect)
        for k in [k for k in self.data
                  if isinstance(k, tuple) and k and k[0] == aid]:
            self.data.pop(k, None)

    # --- Variante LISTE (#354) : `PersistDataList<T>` / `TryGetPersistDataList<T>` -----------------
    # Le natif range SOUS LA MEME cle composite un `List<T>` au lieu d'un scalaire ; les deux familles
    # de methodes coexistent sur le MEME `Dictionary` @+0x10. Le port les distingue par le TYPE de la
    # valeur (list vs scalaire), pas par un second sac -- mirror direct.
    def persist_data_list(self, key, values) -> None:
        """`IdunBattle.Entities.Components.PersistentDataComponent$$PersistDataListu003C__Il2CppFullySharedGenericStructTypeu003E`
        : pose/ecrase `key -> List<T>`. Le natif range la MEME instance de liste qu'il vient de muter."""
        self.data[key] = list(values)

    def try_get_persist_data_list(self, key):
        """`IdunBattle.Entities.Components.PersistentDataComponent$$TryGetPersistDataListu003C__Il2CppFullySharedGenericStructTypeu003E`
        : la liste, ou None si la cle est absente. Les TROIS consommateurs natifs
        (`AddToPersistentDataListBehaviour$$Execute`, `IsInPersistentDataListTrigger$$ShouldTrigger`,
        `EntitiesFromPersistentDataListSelector$$Select`) enchainent tous sur `?? new List<T>()`."""
        v = self.data.get(key)
        return v if isinstance(v, list) else None


def persistent_data_list(entity, key) -> list:
    """`TryGetPersistDataList<T>(key) ?? new List<T>()` — la liste persistante rangee sous `key` sur
    `entity`. Entite/composant/cle absents -> `[]` (le natif materialise lui aussi une liste NEUVE
    dans ce cas, cf. les trois consommateurs). Lu par l'accesseur `ctx.persistent_data_list`."""
    if entity is None:
        return []
    comp = entity.get_component(PersistentDataComponent)
    if comp is None:
        return []
    return list(comp.try_get_persist_data_list(key) or ())


def persistent_data_keys(entity) -> frozenset:
    """Cles persistantes POSEES sur l'entite (mirror de l'ensemble des cles du dict natif) — lu par le
    noeud `IsPersistentData` cote EFFET (`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`), qui
    n'a acces qu'a l'etat, pas au composant. Entite/composant absent -> frozenset() (= sac vide)."""
    if entity is None:
        return frozenset()
    comp = entity.get_component(PersistentDataComponent)
    return frozenset(comp.data.keys()) if comp is not None else frozenset()


def get_ability_stat_modification(entity, key) -> int:
    """`IdunBattle.Entities.UnitExtensions$$GetAbilityStatModification =
    `unit.GetComponent<ActiveAbilityModificationsComponent>().Get(key)`.

    `key` = un `AbilityVarOrConst` (natif : `AbilityVarOrConst.op_Implicit(Nullable<AbilityConstant>)`
    replie la constante en une cle 4 octets -- ex. `0x10` = nrOfSummons, `0x16` = range). Le port passe
    directement l'index de constante (int), MEME domaine de cle que `add`.

    Unite sans composant (cas NOMINAL offline : aucune source de modification portee) -> 0, identique au
    `Get` natif sur un dict vide. Consommateurs natifs (xrefs EXHAUSTIVES du build gqfc5mff6c) : les DEUX
    call-sites de `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour (IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour+0x16b cle 0x10 nrOfSummons,
    IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour+0x24a cle 0x16 range) -- AUCUN autre appelant."""
    if entity is None:
        return 0
    comp = entity.get_component(ActiveAbilityModificationsComponent)
    return comp.get(key) if comp is not None else 0


# --- EMPREINTE MULTI-HEX (`UnitComponent._feet` + `UnitFootComponent`) --------------------------- #
# Mirror des accesseurs natifs de l'empreinte. Ils sont la SEULE porte d'entree du port sur « quelles
# tuiles cette entite occupe » ; la geometrie qui les consomme (distance min-sur-les-pieds, validite
# d'une liste de pieds, positions de mouvement) vit dans `engine.services.movement_query`.

def get_unit_feet(state, unit_id) -> List[tuple]:
    """`IdunBattle.Entities.UnitExtensions$$GetUnitFeet(entity, state)` (== la liste que rend
    `IdunBattle.Entities.EntityExtensions$$GetTiles` / `$$IterateTiles`) : les TUILES des pieds de
    l'unite, DANS L'ORDRE des pieds.

    Natif : `GetUnitFeetIds` iterate `UnitComponent.GetFeetEnumerator()` (= `_feet` @+0x78) et rend
    l'id de chaque pied ; `GetUnitFeet` les resout en entites. `IterateTiles` fait le meme parcours
    et rend la TUILE de chaque pied (`UnitFootComponent.TileId`), en sautant les pieds sans tuile.

    Port :
      * `UnitComponent.feet` materialise (unite MULTI-HEX) -> la liste telle quelle ;
      * `feet is None` (cas NOMINAL, un pied) -> `[(col,row)]` du `PositionComponent` ;
      * ni l'un ni l'autre (entite sans position : MACHINE OF WAR hors plateau, entite non-unite)
        -> `[]`, exactement comme le natif (`GetUnitFeetIds` rend une liste vide si l'entite n'est
        pas une unite, et une MoW porte un `MachineComponent`, pas un `UnitComponent`).

    Accepte un id d'entite OU une `Entity` (le natif prend l'`IEntity`)."""
    e = state.get_entity(int(unit_id)) if isinstance(unit_id, int) else unit_id
    if e is None:
        return []
    uc = e.get_component(UnitComponent)
    feet = getattr(uc, "feet", None) if uc is not None else None
    if feet is not None:
        return list(feet)
    pc = e.get_component(PositionComponent)
    return [] if pc is None else [(pc.col, pc.row)]


def get_feet_count(state, unit_id) -> int:
    """`IdunBattle.Entities.UnitExtensions$$GetFeetCount(entity, state)` =
    `GetUnitFeetIds(entity, state).Count`. **C'est un compte COURANT** (le nombre de pieds
    reellement poses), pas une propriete de config : aucun champ de gameconfig ne porte la taille
    d'une unite -- elle est fixee au spawn par la liste de tuiles passee a `AddUnitOperation`.

    Lecteurs natifs (xrefs) : `MovementQuery$$GetMovablePositionsFor`,
    `TargetingQuery$$GetInvalidTargetReason` / `$$GetInvalidCasterReason` (les regles
    `CasterHas1/3/7Tiles` et `TargetHas1/3/7Tiles`), `BattleQuery$$IsTileInRangeOfAnyAbility`,
    `BasePlaybook$$GetEligibleTargetsEntities`, `DislikeStartingTilesUtility`,
    `ResurrectUnitOperation`, `TheQuickeningAbility$$GetDynamicInvalidTargetReason`."""
    return len(get_unit_feet(state, unit_id))


def get_main_tile(state, unit_id) -> Optional[tuple]:
    """`IdunBattle.Entities.EntityExtensions$$GetMainTileId(entity, state)` -> la tuile, mirror :

        if (entity == null) return 0;
        if (entity.TryGetComponent<UnitFootComponent>(out foot)) return foot.TileId;   // un PIED
        if (entity.TryGetComponent<UnitComponent>(out unit)) {
            if (unit._feet == null || unit._feet.Count == 0) return 0;
            return GetMainTileId(state.GetEntity(unit._feet[0]), state);               // recursion
        }
        if (EntityExtensions.IsTile(entity)) return entity.Id;                          // une TUILE
        return 0;

    => **la main tile est la tuile du PREMIER pied**. Le port lit `feet[0]` s'il existe, sinon la
    `PositionComponent` (identiques par construction, cf. `set_unit_feet`). `None` = pas de tuile
    (l'entite n'est pas sur le plateau)."""
    feet = get_unit_feet(state, unit_id)
    return feet[0] if feet else None


def set_unit_feet(state, unit_id: int, feet) -> List[tuple]:
    """Pose l'empreinte COMPLETE d'une unite — mirror de la boucle de pose de
    `IdunBattle.Operations.AddUnitOperation$$Execute` :

        unitComponent.ClearFeet();
        foreach (tile in tiles) {
            foot = Blueprints.UnitFoot(nextId); state.AddEntity(foot);
            unitComponent.AddFoot(foot.Id);
            foot.GetComponent<UnitFootComponent>().UnitId = unit.Id;
        }

    ECRIVAIN UNIQUE de l'empreinte cote port : il pose `UnitComponent.feet` **et** recale la
    `PositionComponent` sur `feet[0]` (la main tile), pour que les deux representations ne puissent
    pas diverger. Une liste d'UN element repose `feet = None` -> l'unite redevient exactement une
    unite mono-tuile (aucun etat multi-hex residuel apres, p.ex., un retrait de pieds).
    Renvoie l'empreinte posee.

    LISTE VIDE = « l'unite N'OCCUPE PLUS AUCUNE TUILE » (#366-r1). C'est le seul cas ou l'ecrivain
    RETIRE la `PositionComponent` au lieu de la recaler, et il materialise `feet = []` (surtout PAS
    `None`, qui veut dire « un pied, a la `PositionComponent` »). Mirror du collapse de
    `IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute` : le natif met a zero le `TileId`
    de CHAQUE `UnitFootComponent`, et `IdunBattle.Entities.EntityExtensions$$IterateTiles` saute les
    pieds sans tuile -> `GetUnitPosition` (= `$$GetTiles`) rend une liste VIDE. Cote port, la chaine
    `pied -> tuile` etant COLLAPSEE en un `(col,row)`, « pied sans tuile » n'a d'autre representation
    que l'absence du couple. L'etat « unite sans position » n'est PAS inedit : le chemin de
    CHARGEMENT le produit deja (`snapshot._load_units` ne pose la `PositionComponent` que si
    `pos.col is not None`, et `decisionView` rend `pos = null` pour l'unite sous terre) ; les 148
    call-sites `get_component(PositionComponent)` du moteur gardent tous le `None` (balayage AST du
    2026-08-01). Seul l'ECRIVAIN manquait."""
    e = state.get_entity(int(unit_id))
    if e is None:
        return []
    tiles = [(int(t[0]), int(t[1])) for t in (feet or [])]
    uc = e.get_component(UnitComponent)
    if uc is None:
        uc = e.add_component(UnitComponent(visual_id=None, alive=True))
    uc.clear_feet()
    for t in tiles:
        uc.add_foot(t)
    if not tiles:
        # AUCUNE tuile : `feet = []` MATERIALISE (get_unit_feet rend [] sans retomber sur la
        # PositionComponent) + retrait de la position. Les deux vont ENSEMBLE : laisser l'un des
        # deux ferait diverger `get_unit_feet` et `PositionComponent`, exactement ce que cet
        # ecrivain unique existe pour empecher.
        e.remove_component(PositionComponent)
        return []
    if len(uc.feet) <= 1:
        uc.feet = None                       # un pied = cas NOMINAL, pas de liste materialisee
    pc = e.get_component(PositionComponent)
    if pc is None:
        e.add_component(PositionComponent(tiles[0][0], tiles[0][1]))
    else:
        pc.col, pc.row = tiles[0]            # main tile = feet[0] (`GetMainTileId`)
    return get_unit_feet(state, unit_id)


# --- Lien PARENT / ENFANTS (`ChildComponent.ParentId` / `ParentComponent.ChildrenIds`) ----------- #
def parent_of(state, unit_id):
    """`IdunBattle.Entities.UnitExtensions$$GetParent(unit, state, root = false)` (lu par
    `IdunBattle.Entities.Selectors.ParentSelector$$Select`) : l'entite PARENTE DIRECTE (le summoner),
    ou None. Le natif y lit `ChildComponent.ParentId` puis `state.GetEntity(...)` ; il ne remonte
    a la RACINE que si son 3e argument `root` est vrai, ce que ce port ne demande jamais.
    Le port lit `UnitComponent.parent_id` (pose au spawn, ou seede du live par
    `snapshot._load_unit_parent`)."""
    e = state.get_entity(unit_id) if unit_id is not None else None
    uc = e.get_component(UnitComponent) if e is not None else None
    pid = getattr(uc, "parent_id", None) if uc is not None else None
    return state.get_entity(pid) if pid is not None else None


def children_of(state, unit_id, alive_only: bool = True) -> list:
    """Enfants (summons) de `unit_id` — mirror de `ParentComponent.ChildrenIds` (la `List` @+0x10 que
    construit `IdunBattle.Entities.Components.ParentComponent$$.ctor`), DERIVE ici par
    balayage de `state.entities` (le port ne materialise que le lien enfant -> parent). `alive_only`
    reflete `IdunBattle.Entities.Selectors.AllAliveMachinesSelector` (le selecteur `DSLFactory.Children`
    ne rend que des unites VIVANTES) ; le gate `IsFriendlyKell` du playbook SupremeCommander, lui,
    accepte les MORTS (`baseSelector + AllDeadUnits()`) -> `alive_only=False`."""
    out = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is None or getattr(uc, "parent_id", None) != unit_id:
            continue
        if alive_only and not uc.alive:
            continue
        out.append(int(eid))
    return out


# --- Predicat de LIVENESS d'unite (#70) -------------------------------------------------------- #
# Mirror des primitives natives lues par le gate acteur-mort de `ActiveAbilityOperation.
# IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` : `if (EntityExtensions.IsUnit(caster) && UnitExtensions.IsDead(caster))
# return 0;` — un caster MORT rend l'ability (attaque normale INCLUSE, #139) un NO-OP complet (0 tirage
# RNG, aucun effet, aucun flag) AVANT toute execution. Ces helpers portent la semantique de mort utilisee
# par CE gate (cf. engine/runner/operations/damage.py::visit_AttackUnitMessage et
# abilities/handler.py::visit_ActiveAbilityMessage).

def unit_is_alive(entity) -> bool:
    """`IdunBattle.Entities.Components.HealthComponent$$IsAlive` — vivant SSI `hp >= 1` (le natif teste FillUpStat.CurrentValue
    @+0x18 >= 1). hp INCONNU (None, ex. replay charge sans observeBattle) -> vivant (retro-compat : on ne
    gate jamais sur un etat de PV non capte). La branche exotique du natif (hp<1 && max<1 && nullable
    revive @+0x1c == -1 -> vivant) n'est pas portee : non exercee (une unite a plancher de PV a hp>=1)."""
    if entity is None:
        return True
    hc = entity.get_component(HealthComponent)
    if hc is None or hc.hp is None:
        return True
    return hc.hp >= 1


# Effets dont la presence (owner OU target) fait qu'un move est un TELEPORT (cf. `set_moved_flag`) :
# TeleportStrike_TeleportingIn(0x40b=1035)/TeleportStrike_Moving(0x40c=1036) et
# FearOfTheUnseen_TeleportingIn(0x4d6=1238)/FearOfTheUnseen_Moving(0x4d9=1241).
_TELEPORT_MOVE_EFFECTS = (0x40c, 0x40b, 0x4d9, 0x4d6)


def is_teleporting(state, unit_id: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsTeleporting(unit, state)` — mirror 1:1 :

        IsOwnerOfEffect (unit, state, 0x40c, 0) || IsTargetOfEffect(unit, state, 0x40c)
     || IsOwnerOfEffect (unit, state, 0x40b, 0) || IsTargetOfEffect(unit, state, 0x40b)
     || IsOwnerOfEffect (unit, state, 0x4d9, 0) || IsTargetOfEffect(unit, state, 0x4d9)
     || IsOwnerOfEffect (unit, state, 0x4d6, 0) || IsTargetOfEffect(unit, state, 0x4d6)

    C'est le predicat « l'unite est en DEEP STRIKE / en cours de teleportation ». Les quatre types,
    DANS CET ORDRE, sont exactement `_TELEPORT_MOVE_EFFECTS` : `IdunBattle.Entities.UnitExtensions$$SetMovedFlag`
    INLINE la meme chaine (verifie au decompile : memes quatre litteraux, meme ordre, memes deux
    roles), donc les deux lecteurs du port partagent UNE source -- une 2e liste divergerait au
    premier effet ajoute.

    `onlyActive = 0` sur la branche OWNER -> aucune lecture d'`EffectComponent.IsActive @+0x5c` :
    la simple PRESENCE suffit, ce que rend `EffectsState.has_effect` (meme convention que
    `set_moved_flag`, ou les roles owner/target sont confondus offline -- l'`EffectsState` du port
    stocke par-PORTEUR).

    CONSOMMATEURS : `set_moved_flag` (flag `Teleported`), et la regle-delegue CASTER de 1115
    `FearOfTheUnseenAbility$$GetDynamicInvalidCasterReason` (#447)."""
    if state is None or getattr(state, "effects", None) is None:
        return False
    return any(state.effects.has_effect(int(unit_id), effect_type=t)
               for t in _TELEPORT_MOVE_EFFECTS)


def set_moved_flag(state, unit_id: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$SetMovedFlag` — mirror 1:1, appele par
    `IdunBattle.Operations.MoveUnitOperation$$Execute` (SEUL chemin de pose du flag avec
    `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile`) :

        added = UnitFlagsComponent.Add(unit, UnitFlag.Moved=0)
        if added and (IsOwnerOfEffect|IsTargetOfEffect (unit, 0x40c|0x40b|0x4d9|0x4d6)):
            UnitFlagsComponent.Add(unit, UnitFlag.Teleported=0xc)

    `Add` natif rend « etait ABSENT » -> le flag Teleported n'est pose qu'au PREMIER move du tour
    (fidele : un 2e move ne re-teste pas les effets de teleport). Roles owner/target confondus offline
    (l'`EffectsState` stocke par-porteur ; meme convention que `is_attack_max_out_damage`).
    Cree le `UnitFlagsComponent` au besoin (le natif le resout par `GetComponent` sur une entite qui
    l'a toujours). Renvoie « le flag Moved vient d'etre pose »."""
    e = state.get_entity(unit_id)
    if e is None:
        return False
    fl = e.get_component(UnitFlagsComponent)
    if fl is None:
        fl = e.add_component(UnitFlagsComponent())
    added = not fl.has(UnitFlagsComponent.MOVED)
    fl.add(UnitFlagsComponent.MOVED)
    if added and is_teleporting(state, unit_id):
        fl.add(UnitFlagsComponent.TELEPORTED)                 # Add(0xc) — le move etait un teleport
    return added


def unit_has_moved(state, unit_id: int) -> bool:
    """`HasFlag(unit, UnitFlag.Moved=0)` (`IdunBattleLogic.Entities.DSLFactory$$HasFlag` ->
    `IdunBattle.Entities.Conditions.HasFlagAbilityTrigger$$ShouldTrigger` = `UnitFlagsComponent.Has`).
    LECTEUR UNIQUE du fait « a bouge ce tour » cote port : le natif n'a QU'UN store (le
    `UnitFlagsComponent`), pose par `set_moved_flag` et purge par `RemoveTurnFlags(new_activation=1)`
    du `StartTurnOperation` — PAR JOUEUR ENTRANT, pas globalement. Consommateurs : le gate no-move de
    `HeavyWeapon_ExtraDmg`/`CrushingStrike` (via `attacker_modifiers`), la branche fin-de-tour de
    `RadSaturation`, le `GetHits` d'HarvesterOfSouls. Composant absent = flag absent = n'a pas bouge.

    ⚠ FICHE CORRIGEE (2026-07-28, #210) : sur un etat CHARGE, `load_state` SEEDE desormais ce flag
    (`snapshot._load_unit_flags` <- `combatSnapshot.units[].unitFlags`, introduit par `f02e30f`) -- la
    mention anterieure « le RPC n'expose pas les UnitFlags -> une fixture qui SAIT que l'unite a bouge
    doit poser le flag » est PERIMEE. MESURE : `probe_210_blackrage_targeting.py` cas `S4a` (Lucien
    bouge live, capture, etat charge) -> le port rend `CasterHasNotMoved` en accord avec le natif,
    SANS pose manuelle. La pose manuelle (`set_moved_flag`) ne reste necessaire que sur un etat
    construit hors snapshot."""
    e = state.get_entity(unit_id)
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    return bool(fl is not None and fl.has(UnitFlagsComponent.MOVED))


def record_tiles_moved(state, unit_id: int, tiles: int) -> int:
    """`IdunBattle.Entities.UnitExtensions$$RecordTilesMoved(unit, tiles, state)` — mirror 1:1 :

        if ((int)tiles < 1) return;                 // no-op silencieux, 0 et negatifs compris
        comp = GetComponent<ActorStatisticsComponent>(unit);
        comp[0xec] += tiles;                        // cumul BATAILLE
        comp[0xf0] += tiles;                        // cumul CE TOUR

    Les DEUX champs prennent le MEME increment ; c'est un `+=`, jamais une affectation, ce qui est
    exactement ce qui permet a la face DECISION de voir « compteur reel + tuiles du pas simule »
    quand `SimulateEffectsOperation$$DoActionInSimulatedTile` rejoue un `MoveUnitOperation`
    (cf. `playbook/prediction/_shared.py::prediction_tiles_moved_this_turn`).

    Renvoie le nombre EFFECTIVEMENT enregistre (0 si le garde `< 1` a coupe) — diagnostic."""
    if tiles is None:
        return 0
    n = int(tiles)
    if n < 1:                                       # `if (iVar2 < 1) return;`
        return 0
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None:
        return 0
    uc.tiles_moved_this_battle = int(uc.tiles_moved_this_battle or 0) + n
    uc.tiles_moved_this_turn = int(uc.tiles_moved_this_turn or 0) + n
    return n


def unit_tiles_moved_this_turn(state, unit_id: int) -> int:
    """`IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate` = le champ
    `ActorStatisticsComponent + 0xf0` du porteur -- LECTEUR UNIQUE du canal cote COMBAT.

    C'est ce que resout le noeud DSL `IdunBattleLogic.Entities.DSLFormulas$$TilesMovedThisTurn`,
    dont le consommateur porte est `ModifiedExoarmour_ExtraDmgEffect` (magnitude `V x n` ET
    `CreateActiveCondition`). Composant absent = 0, comme un composant natif frais."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    return int(uc.tiles_moved_this_turn or 0) if uc is not None else 0


def reset_tiles_moved_this_turn(state, unit_id: int, was_own_turn: bool) -> None:
    """Volet TUILES de `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn(
    comp, wasOwnTurn)`, appele par `IdunBattle.Operations.EndTurnOperation$$Execute` sur CHAQUE
    unite de `GetAllUnits` :

        if (wasOwnTurn) comp[0xf4] = comp[0xf0];    // TilesMovedLastTurn
        comp[0xf0] = 0;                             // reset INCONDITIONNEL

    `was_own_turn` = l'unite appartient au joueur qui FINIT son tour (le natif le derive de
    `PlayerComponent.CurrentlyOwnedUnitIds` de ce joueur, teste par `List.Contains`).
    Les autres champs que `ResetThisTurn` roule (0x78/0x7c, 0xe4/0xe8, 0x58/0x5c, 0xa0/0xa4 et le
    dict par-entite) ne sont pas suivis offline -- residu DEJA documente en tete de `turnflow.py`."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None:
        return
    if was_own_turn:
        uc.tiles_moved_last_turn = int(uc.tiles_moved_this_turn or 0)
    uc.tiles_moved_this_turn = 0


def unit_has_teleported(state, unit_id: int) -> bool:
    """`HasFlag(unit, UnitFlag.Teleported = 0xc)` — pendant de `unit_has_moved`, pose par
    `set_moved_flag` quand le deplacement etait un TELEPORT (et par le capteur O5 de
    `combatSnapshot.unitFlags` sur un etat recharge, cf. `snapshot._load_unit_flags`).

    UNIQUE consommateur porte : la branche `| HasFlag(Self@0x148, 0xc)` du trigger de
    `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier`, lue verbatim :

        OwnerIsCaster & IsRangedAttack
          & ((df@0xa0 & !HasFlag(Self, 3 = TurnFinished)) | !df@0xa0)
          & (!HasFlag(Self, 0 = Moved) | HasFlag(Self, 0xc = Teleported))

    -> un porteur `HeavyWeapon` qui s'est TELEPORTE garde son +25% ranged, alors qu'un deplacement
    ordinaire le lui retire. A NE PAS generaliser : la condition soeur
    `IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateActiveCondition` est
    `!HasFlag(Self, 0)` **seul**, sans branche Teleported (decompile relu)."""
    e = state.get_entity(unit_id)
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    return bool(fl is not None and fl.has(UnitFlagsComponent.TELEPORTED))


def unit_has_used_active_ability(state, unit_id: int) -> bool:
    """`HasFlag(unit, UnitFlag.ActiveAbilityUsed = 2)` — l'unite a consomme son ACTION ce tour.

    Meme store que `unit_has_moved` (le `UnitFlagsComponent` unique) : pose par la queue de cast
    (`AActiveAbility.SetsActiveAbilityUsedFlag` -> `UnitFlags.Add(2)`, cf.
    `runner/abilities/base.py`), purge a l'entree de tour par
    `IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags`, et seede depuis le live
    par `snapshot._load_unit_flags`.

    CONSOMMATEUR : le gate d'entree du generateur d'abilities de l'IA
    (`IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`,
    1re instruction : `if (HasFlag(unit, 2)) return 0`). Composant absent = flag absent = n'a pas
    encore agi."""
    e = state.get_entity(unit_id)
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    return bool(fl is not None and fl.has(UnitFlagsComponent.ACTIVE_ABILITY_USED))


def update_charging(state, unit_id: int, old_pos, new_pos) -> list:
    """`IdunBattle.Operations.MoveUnitOperation$$UpdateCharging(this, unit, newPosition, oldPosition,
    unitComponent)` — MIRROR du decompile :

        before = query.GetAdjacentUnits(oldPosition, unit)      # vide si oldPosition n'a pas de MainTile
        after  = query.GetAdjacentUnits(newPosition, unit)
        foreach u in after:
            if (!before.Contains(u))                            # NOUVELLEMENT adjacente
                if (!unitComponent.ChargedUnitIds.Contains(u.Id))
                    unitComponent.ChargedUnitIds.Add(u.Id)      # +0x190

    => « charger » = arriver AU CONTACT d'une unite qui ne l'etait pas avant CE pas de deplacement.
    Le natif n'y filtre NI l'equipe NI la vie : la liste retient toute unite nouvellement adjacente
    (le filtre ennemi/vivant vit chez le consommateur). Appele DEUX fois dans
    `IdunBattle.Operations.MoveUnitOperation$$Execute` (branche « no-automatic-turns » et branche
    normale), toujours AVANT `SetMovedFlag`.

    `old_pos`/`new_pos` = (col,row) ; `old_pos=None` (unite sans position avant le move, ex. spawn)
    -> `before` vide, mirror du `MainTile == null` natif. Renvoie les ids AJOUTES (diag).

    ⚠ « ADJACENT » Y EST `IterateAdjacentTiles`, PAS `hexgeo.distance == 1` (#433-r4-r1-r4-r2-r1).
    `IdunBattle.Core.Services.BattleQuery$$GetAdjacentUnits(from, ...)` est LU comme
    `IterateAdjacentTiles(from, ...)` puis `GetUnitsOnTiles(...)`, et
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` enumere la
    liste STOCKEE du `ConnectivityComponent` (`+0x10`) avant d'appliquer la porte `|dElev| < 2`.
    D'ou la delegation a `battle_query.is_adjacent`, foyer des DEUX etages : ce mirror ECS et son
    jumeau PREDICTION (`battle_query.newly_adjacent_ids`) portent le MEME natif et doivent voir le
    MEME graphe, sinon `IsCharging` diverge d'une face a l'autre alors que le natif n'a qu'un seul
    `IBattleQuery` -- meme exigence que `Board.walk_maps_by_pos` sur `TilesMovedThisTurn`.
    Canaux derives du board (tri-etat) : `state.board` absent -> repli GEOMETRIQUE nomme
    d'`is_adjacent`, c'est-a-dire exactement le comportement d'avant.

    La liste est videe par `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` (cf.
    `FinishUnitTurnOperation.execute`) -> sa duree de vie est L'ACTIVATION de l'unite, ce qui donne au
    predicat `IsCharging` sa semantique « a charge cette cible CE TOUR ». Aucun autre site natif
    n'ecrit ce champ (xrefs de `UpdateCharging` : les 2 call-sites de `Execute` ; le seul autre
    lecteur est `BattleQuery$$IsCharging`)."""
    from ..battle_query import is_adjacent
    from ..entities.pathfinding.board import adjacent_neigh_by_pos, elevations_by_pos
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or new_pos is None:
        return []
    board = getattr(state, "board", None)
    elev_by_pos = elevations_by_pos(board)
    neigh_by_pos = adjacent_neigh_by_pos(board)

    def _adjacent_ids(pos):
        if pos is None:
            return set()
        out = set()
        for oid, other in state.entities.items():
            if oid == unit_id:
                continue
            opc = other.get_component(PositionComponent)
            if opc is None:
                continue
            if is_adjacent(tuple(pos), (opc.col, opc.row), elev_by_pos, neigh_by_pos):
                out.add(int(oid))
        return out

    before = _adjacent_ids(old_pos)
    added = []
    for oid in sorted(_adjacent_ids(new_pos) - before):
        if oid not in uc.charged_unit_ids:
            uc.charged_unit_ids.append(oid)
            added.append(oid)
    return added


def charged_unit_ids(state, unit_id: int) -> set:
    """Les ids que `unit_id` a CHARGES (liste `UnitComponent + 0x190`). Composant absent -> vide."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    return set(int(i) for i in (uc.charged_unit_ids or ())) if uc is not None else set()


def can_be_overkilled(entity) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$CanBeOverkilled` = `!BaseUnitComponent.HasTrait(u, 0x1b)`
    (0x1b = 27 = `UnitTrait.Steppable`) ; unite SANS `BaseUnitComponent` -> True (le natif retourne 1
    quand `GetBaseUnitComponent` rend null). C'est le PREMIER gate de la surcharge d'instance de
    `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` : une unite Steppable n'est JAMAIS overkillee,
    quel que soit le degat.

    Porteurs Steppable ATTEIGNABLES en runner (donc gate vivant, pas du code mort) : les DEUX summons
    `astarSmnHaywireMine` (Cyrus) et `genesSmnDecoy` -- ce dernier est pose par `Ambush_SummonAbility`
    a la mort de tout porteur du trait `Ambush` (genesPrimus/genesKelermorph/genesMagus/genesBiophagus,
    tous dans le pool) --, plus les objets de terrain npc (loot/powerups).

    Les noms de traits viennent de `StatsComponent.ctx.traits` (NOMS gameconfig), meme convention que
    tous les `HasTrait(target, ...)` portes ; ctx absent -> pas de trait connu -> True (degradation
    fidele : le natif rend True quand le composant de base manque)."""
    from ..entities.traits.unit_trait import UnitTrait, has_trait
    if entity is None:
        return True
    sc = entity.get_component(StatsComponent)
    traits = getattr(getattr(sc, "ctx", None), "traits", None) if sc is not None else None
    return not has_trait(traits, UnitTrait.Steppable)


def unit_is_overkilled(entity) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasFlag(target, 8 = UnitFlag.Overkilled)` -- la GARDE
    D'ENTREE du SITE (A) d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` :

        cVar15 = UnitExtensions__HasFlag(target, 8);
        if (cVar15 != '\\0') { RecordHitStatistics ; AddLeftoverHit(.., 1) ; return; }

    Un coup porte sur une cible DEJA marquee overkillee n'applique RIEN et **n'emet aucun
    evenement** -- ni `On(0x39)`, ni `On(0xf)`, ni `On(0x10)`, ni le `UnitDamaged` porteur du tag
    `Amount`. Le flag est pose par le MEME `Execute`, au coup ou `didOverkill` devient vrai
    (`IdunBattle.Entities.Components.UnitFlagsComponent$$Add(flags, 8)` sous
    `dar.didOverkill && UnitExtensions.CanBeOverkilled(target)`), et RETIRE par
    `IdunBattle.Operations.ReviveUnitOperation$$Execute`.

    Lecture PURE (aucune mutation) : le port pose le flag, lui, dans `_fire_death_if_killed`."""
    if entity is None:
        return False
    fl = entity.get_component(UnitFlagsComponent)
    return bool(fl is not None and fl.has(UnitFlagsComponent.OVERKILLED))


PREVENT_OVERKILL_EFFECT = 1354      # `EffectType.FuelledByFury_BlockOverkill` (0x54a)


def effects_prevent_overkill(active_effects) -> bool:
    """Volet EFFET de `UnitExtensions.HasFlag(target, 0x13)` : une instance ACTIVE de l'effet 1354
    est-elle portee ? FOYER UNIQUE de cette derivation -- `unit_prevents_overkill` (face ECS,
    composant d'abord) et `Scene.prevents_overkill` (face PREDICTION, ou l'etat n'est pas un
    `State`) l'appellent tous deux, pour qu'il n'existe pas DEUX ports d'un meme flag natif.
    L'appelant fournit deja les effets ACTIFS (gate `EffectComponent.IsActive` + condition), qui
    est exactement l'invariant du couple `ApplyInternal`/`RevertInternal` -- cf.
    `unit_prevents_overkill` pour la demonstration."""
    return any(int(getattr(e, "effect_type", -1) or -1) == PREVENT_OVERKILL_EFFECT
               for e in (active_effects or []))


def unit_prevents_overkill(state, unit_id) -> bool:
    """`UnitExtensions.HasFlag(target, 0x13)` — le `suppress` de la surcharge d'instance de
    `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` (`UnitFlag.PreventOverkill`, cf.
    `UnitFlagsComponent.PREVENT_OVERKILL`).

    Le flag est LU ici et DERIVE de l'effet qui le pose. Le binaire n'a qu'UN couple ecrivain, et il
    ENCADRE exactement la duree de vie de l'effet :
      * `IdunBattle.Entities.Effects.Loki.FuelledByFury_BlockOverkillEffect$$ApplyInternal`
        -> `UnitFlagsComponent.Add(target, 0x13)` ;
      * `IdunBattle.Entities.Effects.Loki.FuelledByFury_BlockOverkillEffect$$RevertInternal`
        -> `UnitFlagsComponent.Remove(target, 0x13)`.
    (Recherche litterale au decompile : `UnitFlagsComponent__Add(...,0x13,0)` n'a QUE cette occurrence.)
    L'effet lui-meme est active/desactive par ses propres triggers
    (`...$$CreateHandleTriggerAbilitiesInternal` : `On(0x21)&OwnerIsActor -> ActivateEffect`,
    `On(0x12) -> ActivateEffect`, `On(0x2d = UnitRevived)&OwnerIsTarget -> DeactivateEffect`) -> le flag vaut
    exactement « une instance ACTIVE de l'effet 1354 est portee ». Offline, `EffectsState.active_effects`
    applique DEJA le meme couple flag `EffectComponent.IsActive` + `CreateActiveCondition` : la
    derivation est donc le MEME invariant, pas une approximation (meme schema que
    `group_unit_stat_part`, qui derive le champ « membres restants » de l'etat PV).

    Le composant reste interroge en PREMIER pour tout futur poseur imperatif du flag.

    MESURE LIVE (#178) : `ultraTitus` (i2 << The first time each turn that Titus is defeated he cannot
    be Overkilled >>) porte `FuelledByFury_BlockOverkill` des le deploiement ; un coup de 1452 sur
    400 PV le TUE sans le marquer overkill (le crescendo de son tueur ne monte pas), la ou la MEME
    attaque sur `genesPrimus` (400 PV) le marque."""
    entity = state.get_entity(int(unit_id)) if state is not None else None
    if entity is None:
        return False
    fl = entity.get_component(UnitFlagsComponent)
    if fl is not None and fl.has(UnitFlagsComponent.PREVENT_OVERKILL):
        return True
    eff = getattr(state, "effects", None)
    if eff is None:
        return False
    return effects_prevent_overkill(
        eff.active_effects(int(unit_id), unit_state_for_effects(state, int(unit_id))))


def unit_is_dead(entity) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsDead` — mort SSI `!IsAlive(u) && !HasFlag(u, Fled=9)` : une unite
    RETIREE du board (flag 9, `UnitFlag.Fled`) n'est PAS « morte » au sens de ce predicat. Restreint aux
    UNITES (mirror du garde `EntityExtensions.IsUnit` d'ExecuteInternal) : une source non-unite (tuile/env,
    sans `HealthComponent`) est TOUJOURS vivante -> jamais gated. Inerte (False) sur tout attaquant/caster
    vivant -> le port du gate ne peut sur-immuniser aucune attaque legitime."""
    if entity is None or unit_is_alive(entity):
        return False
    fl = entity.get_component(UnitFlagsComponent)
    if fl is not None and fl.has(UnitFlagsComponent.FLED):
        return False
    return True


# ── Contexte d'évaluation des `CreateActiveCondition` (#208) ──────────────────────────────────────
# `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` évalue l'arbre mémoïsé de l'effet
# (`BaseEffect$$CreateActiveConditionAndCache`, champ `+0x90`) contre un CONTEXTE de 0x130 octets,
# et rend le booléen qu'il écrit dans `EffectComponent.IsActive @+0x5c`. Côté port, la condition est
# ré-évaluée A LA LECTURE (`EffectsState.active_effects` -> `BaseEffect.is_active(unit_state)`) : le
# `unit_state` ci-dessous EST ce contexte. Il n'y a donc QU'UN constructeur — tout appelant d'
# `active_effects` passe par lui (doctrine anti-fork « 1 nœud natif -> 1 porte offline »).
#
# ⚠ POURQUOI CE FOYER EXISTE (#208, régression MESURÉE). Les appelants construisaient chacun un
# `{"hp": ...}` ad hoc : les clés MANQUANTES (`traits`, `max_hp`, `enemy_psykers_alive`) dégradent
# CHAQUE prédicat en VRAI, donc un effet dont la condition est FAUSSE contribuait quand même. C'est
# exactement ce qui obligeait `PinnedEffect` à collapser sa `CreateActiveCondition` dans le gate
# d'IMMUNITÉ (`entity_is_immune_to_effect`) — un mécanisme faux qui rendait le bon observable.


def enemy_psykers_alive(state, unit_id: int) -> Optional[int]:
    """`Enemies( Owner, UnitsWithTrait(AllUnits@0x80, 0x3ea = 1002 Psyker, 3) )` — le CARDINAL du
    sélecteur natif que `AmountIsEqualOrGreater(…, One@0xc0)` compare à 1 dans la
    `CreateActiveCondition` de `DestroyTheWitch_ExtraMove`/`_ExtraDamage` (corps FONDU, cf.
    `entities/effects/loki/destroy_the_witch.py`).

    `AllUnits@0x80` = le sélecteur battlefield-wide (`DSLFactory$$InitializeShared` +0x80,
    identifié par `WarHowlAbility$$OtherBuffTargets` = `Friends(owner, @0x80 − owner)` = « tous les
    AUTRES alliés du plateau »). `Enemies(owner, …)` filtre `team != team(owner)` ; les unités
    MORTES ne sont plus sur le plateau. None si l'équipe du porteur est inconnue (clé alors ABSENTE
    du `unit_state` ⇒ prédicat dégradé en VRAI, cf. `_enemy_psyker_on_battlefield`)."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    if oc is None:
        return None
    n = 0
    for uid, e in state.entities.items():
        eoc = e.get_component(OwnerComponent)
        if eoc is None or eoc.team == oc.team:              # Enemies(owner, …)
            continue
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            continue
        sc = e.get_component(StatsComponent)
        traits = (sc.ctx.traits if (sc is not None and getattr(sc, "ctx", None) is not None)
                  else None) or ()
        if "Psyker" in traits:                              # UnitsWithTrait(0x3ea)
            n += 1
    return n


def has_effect_of_type(state, unit_id: int, effect_type: int) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$HasEffect(sel, effectType, onlyActive, effectTargetType)`
    -> `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects(entity, query, [effectType],
    onlyActive, targetType)` -- la branche « l'entite PORTE cet effet ».

    ⚠ **`onlyActive = 0`** au call-site porte (`CamoCloak_DmgReductionEffect$$HasValidEffectTrigger`) :
    le natif ne consulte PAS `EffectComponent.IsActive @+0x5c`. Le mirror est donc
    `EffectsState.has_effect` (qui ne filtre que `consumed`) et **pas** `active_effects` -- ce
    dernier appelle `BaseEffect.is_active`, et l'appeler ICI bouclerait (ce lecteur alimente
    justement le `unit_state` des `is_active`).

    `targetType = 6` (= 2|4 = owned | targeted) : cote port les deux branches coincident, l'
    `EffectsState` etant indexee par ENTITE PORTEUSE (`by_unit`), qui est la cible de l'`AddEffect`."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return False
    return bool(eff.has_effect(int(unit_id), int(effect_type)))


class _RunnerEffectTargetWorld:
    """Substrat ECS de `entities.effect_targets.EffectTargetWorld` (le pendant DECISION est
    `playbook/scene.py::_SceneEffectTargetWorld`). Un noeud natif, deux substrats."""
    __slots__ = ("state",)

    def __init__(self, state):
        self.state = state

    def unit_ids(self):
        return list(self.state.entities.keys())

    def carries(self, uid: int, effect_type: int) -> bool:
        return has_effect_of_type(self.state, int(uid), int(effect_type))

    def _ent(self, uid: int):
        return self.state.get_entity(int(uid))

    def pos(self, uid: int):
        e = self._ent(uid)
        pc = e.get_component(PositionComponent) if e is not None else None
        if pc is None or pc.col is None or pc.row is None:
            return None
        return (pc.col, pc.row)

    def team(self, uid: int):
        e = self._ent(uid)
        oc = e.get_component(OwnerComponent) if e is not None else None
        return oc.team if oc is not None else None

    def alive(self, uid: int) -> bool:
        e = self._ent(uid)
        uc = e.get_component(UnitComponent) if e is not None else None
        return True if uc is None else bool(uc.alive)

    def traits(self, uid: int):
        e = self._ent(uid)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = getattr(sc, "ctx", None) if sc is not None else None
        return (getattr(ctx, "traits", None) or ()) if ctx is not None else ()


def is_effect_target(state, unit_id: int, effect_type: int) -> Optional[bool]:
    """`IdunBattleLogic.Entities.DSLTriggers$$IsEffectTarget(sel, effectType)`, face COMBAT.

    Delegue au foyer unique `engine.entities.effect_targets.is_effect_target` : la geometrie de la
    liste `EffectComponent.Targets @+0x48` vient du `<Effect>$$CreateTargetSelector` de CHAQUE
    effectType, jamais d'un defaut. `None` = type non porte / substrat manquant -> l'appelant
    degrade explicitement (cf. la docstring du foyer)."""
    from ..entities.effect_targets import is_effect_target as _iet
    ent = state.get_entity(int(unit_id))
    pc = ent.get_component(PositionComponent) if ent is not None else None
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    if pc is None or pc.col is None or pc.row is None or oc is None:
        return None                                    # sujet hors plateau -> inconnu
    return _iet(_RunnerEffectTargetWorld(state), int(unit_id), int(effect_type))


def is_target_of_adjacent_friend_aura(state, unit_id: int, effect_type: int) -> Optional[bool]:
    """Alias HISTORIQUE de `is_effect_target` (case-366-r1 / `1014 CamoCloak` l'appelle avec `1026`).

    Le nom encodait la geometrie d'UN effet (`AdjacentFriends`) alors que le noeud natif n'en connait
    aucune : depuis case-418-r1 la geometrie est indexee PAR effectType dans
    `entities/effect_targets.py`. Conserve tel quel pour ses deux appelants ; tout NOUVEL appelant
    passe par `is_effect_target`."""
    return is_effect_target(state, unit_id, effect_type)


def contagions_of_nurgle_amount(state, unit_id: int, source_id) -> Optional[int]:
    """`IdunBattle.Entities.Triggers.ContagionsOfNurgleAmountFormula$$Calculate` — le nœud
    `IdunBattleLogic.Entities.DSLFormulas$$ContagionsOfNurgleAmount(team, unit)`, lu VERBATIM :

        entity = <selecteur team>.SelectSingle(entities) ;  if (entity == null) return 0
        teamId = EntityExtensions.GetCurrentTeamId(entity, state)
        target = <selecteur unit>.SelectSingle(entities) ;  if (target == null) return 0
        return battleQuery.<slot 0x95>(effectType /* fige a 0x42f par le ctor */, teamId, target,
                                       returnFirst: false)

    Le slot `0x95` d'`IBattleQuery` est `IdunBattle.Core.Services.BattleQuery$$GetInRangeAuraAmount`
    (signature `(effectType, team, target, returnFirst)`, MEME ordre d'arguments) — DEJA porte par
    case-224 dans `engine/battle_query.py`. Ce foyer DELEGUE donc, il ne re-derive rien :

      * le comparateur est **INCLUSIF** (`dist <= GetCurrentRange(porteur)`), PAS le strict de
        `IsInUnitContagionsOfNurgleAura` — c'est la version d'EQUIPE du prédicat, et c'est elle que
        `CreateActiveCondition` consomme ;
      * le filtre d'appartenance est `GetCurrentTeamId(porteur) == team(<EffectSource>)` — donc
        « porteurs ALLIES DE LA SOURCE de l'effet », pas « ennemis du porteur de l'effet ». Les deux
        coincident sur tous les montages mesures, mais seule la premiere est ce que le natif ecrit.

    `source_id` = `EffectSource(Effect@0x150)` = `EffectComponent.SourceUnit @+0x10` = `eff.source`.
    `None` (source inconnue, entite disparue) => la clé est ABSENTE du `unit_state`, ce que la
    `CreateActiveCondition` consommatrice traite en dégradation (cf.
    `ContagionsOfNurgleArmorReductionEffect.is_active`) — jamais un 0 inventé, qui rendrait
    l'instance inactive et ferait remonter l'armure sans raison native."""
    from ..battle_query import get_in_range_aura_amount
    from ..entities.effect_type import EffectType
    from ..entities.stats import StatType
    src = state.get_entity(int(source_id)) if source_id is not None else None
    soc = src.get_component(OwnerComponent) if src is not None else None
    if soc is None or soc.team is None:
        return None                                   # `SelectSingle` null -> le natif rend 0 ; ici
                                                      # « inconnu » (cf. docstring)
    target = None
    units: List[dict] = []
    for uid, ent in state.entities.items():
        pc = ent.get_component(PositionComponent)
        if pc is None:
            continue
        oc = ent.get_component(OwnerComponent)
        uc = ent.get_component(UnitComponent)
        sc = ent.get_component(StatsComponent)
        hc = ent.get_component(HealthComponent)
        ctx = getattr(sc, "ctx", None) if sc is not None else None
        us = getattr(ctx, "stats", None) if ctx is not None else None
        # `hp` est LU par le mirror (`GetSurroundingUnits` ne rend que des unites vivantes : une
        # unite morte est retiree du board par `KillUnit`) -> l'omettre exclurait TOUT le monde.
        d = {"id": int(uid), "pos": {"col": pc.col, "row": pc.row},
             "team": (None if oc is None else oc.team),
             "alive": True if uc is None else bool(uc.alive),
             "hp": (int(hc.hp) if hc is not None and hc.hp is not None else 1),
             "_traits": (getattr(ctx, "traits", None) or ()) if ctx is not None else (),
             "_turns_started": (int(us.get_stat(int(StatType.TURNS_STARTED), 0) or 0)
                                if us is not None else 0)}
        if int(uid) == int(unit_id):
            target = d
        units.append(d)
    if target is None:
        return None                                   # cible sans tuile -> aucun voisinage
    from ..entities.traits import UnitTrait as _UT, has_trait as _has_trait

    def _unit_has_trait(u, trait_id) -> bool:
        """`UnitExtensions.HasTrait(unit, aura.GetTrait())` — le trait natif est un ID d'enum, le
        substrat du port des NOMS gameconfig (même convention que tous les `HasTrait` portés)."""
        try:
            enum = _UT(int(trait_id))
        except ValueError:
            return False
        return _has_trait(u.get("_traits"), enum)

    return get_in_range_aura_amount(
        int(EffectType.ContagionsOfNurgle_ArmorReduction1),      # 0x42f, fige par le ctor du noeud
        int(soc.team), target, units, _unit_has_trait,
        lambda u: u.get("_turns_started"), return_first=False)


_STRUCTURAL_ANALYSER_TAU = "Tau"          # UnitFaction.Tau = 9 (`UnitsFromFaction(..., 9)`)


def structural_analyser_friends(state, unit_id: int) -> Optional[int]:
    """`Unique( AdjacentFriends(Owner) + UnitsFromFaction(SurroundingFriends(Owner, Direct(2)), 9) )`
    -- le CARDINAL du selecteur natif
    `IdunBattle.Entities.Effects.Loki.StructuralAnalyserAdjacentEffect$$CreateTargetSelector`, que
    `IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreaterThanZero` compare a 0 dans
    `IdunBattle.Entities.Effects.Loki.StructuralAnalyser_VisualEffect$$CreateActiveCondition`
    (case-366-r1).

    DEUX tiers, et le second est filtre par FACTION :
      * `AdjacentFriends` : allie a distance 1, **toute faction** ;
      * `UnitsFromFaction(SurroundingFriends(range = Direct(2)), Tau)` : allie T'au a distance <= 2.
    Le PORTEUR n'y entre pas -- MESURE (case-366-r1) : Darkstrider seul, sans aucun allie proche,
    a `StructuralAnalyser_Visual.active == false`. C'est le meme selecteur d'aura que
    `DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector` (partage x4 : StructuralAnalyser /
    SereneUnifier / DotGG / WayOfTheShortBlade, cf. `docs/rl/case-220/tau.md`), d'ou la meme forme
    `d == 1 or (d <= 2 and faction == Tau)` que `aura_selector_covers`.

    `None` si le porteur n'a ni equipe ni tuile (cle alors ABSENTE du `unit_state` => predicat
    degrade en VRAI, cf. `StructuralAnalyserVisualEffect.is_active`) -- jamais un 0 invente."""
    import hexgeo
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from ..ai.action_generators import _faction               # FactionId gameconfig par visualId
    here = (pc.col, pc.row)
    n = 0
    for uid, e in state.entities.items():
        if int(uid) == int(unit_id):                          # le porteur n'est pas son propre ami
            continue
        eoc = e.get_component(OwnerComponent)
        if eoc is None or eoc.team != oc.team:                # Friends(owner, ...)
            continue
        euc = e.get_component(UnitComponent)
        if euc is None or not euc.alive:                      # une unite morte quitte le plateau
            continue
        epc = e.get_component(PositionComponent)
        if epc is None:
            continue
        d = hexgeo.distance(here, (epc.col, epc.row))
        if d == 1:                                            # AdjacentFriends (toute faction)
            n += 1
        elif d <= 2 and _faction(euc.visual_id) == _STRUCTURAL_ANALYSER_TAU:
            n += 1                                            # UnitsFromFaction(Surrounding(2), Tau)
    return n


def adjacent_friendly_summons_and_decoys_count(state, unit_id: int) -> Optional[int]:
    """`Count( UnitsWithTrait(AdjacentFriends(Owner, 1, 3), 0x2 = Summon)
    op_Addition UnitsWithTrait(AdjacentFriends(Owner, 1, 3), 0x41d = Decoy) )` -- le cardinal que
    `IdunBattle.Entities.Effects.Loki.AmuletOfTheVoidwyrm_CritDamageReductionEffect$$
    GetAdjacentFriendlySummonsAndDecoysCount` calcule pour le PORTEUR de l'effet.

    DEUX consommateurs natifs, un seul foyer ici (le natif appelle LA MEME methode des deux cotes) :
      * `...$$CreateActiveCondition` = `AmountIsGreaterThanZero(<ce compteur>)` ;
      * `...$$GetCritDmgReductionAmount` = `Multiply(ConfigVar(0x97), <ce compteur>)`.

    L'ARBRE est celui de la classe d'effet (`entities/effects/loki/amulet_of_the_voidwyrm.py::
    adjacent_friendly_summons_and_decoys_selector`, doctrine #149 : l'artefact natif est un
    SELECTEUR) ; ce qu'on fait ICI, c'est lui donner son `AbilityEntities` -- `entities_from_state(
    state, unit_id)` pose `caster = owner = le porteur`, `board = state.board` et `has_trait`.

    ⚠ SUBSTRAT D'ADJACENCE, **MESURE** et non suppose (#589-r1-r1-r2-r1). Le foyer DSL partage
    (`dsl/base.py::_within`, `order='adjacent'`) filtre l'ENSEMBLE par `hexgeo.distance <= radius`
    et ne se sert de `board.neighbours_native` que pour l'ORDRE d'enumeration. C'est le
    comportement du NATIF sur ce chemin : sur `C3_14`, porteur en `(5,4)` et compagnon en `(5,3)`
    -- meme elevation 4, arete absente de `boardGraph.neighbours` ET de `connectivity`, DANS LES
    DEUX SENS -- le natif ACTIVE l'effet et retranche `critDmgReduction x 1`. Le probe de cette
    tranche avait ecrit sa garde a l'envers et la mesure l'a retourne. C'est le meme fait que
    `runner/operations/triggers/base.py::_adjacent_damageable_enemies` avait deja mesure sur
    l'AUTRE consommateur du meme sous-arbre (`Units(AdjacentTiles(...))` du splash de FragBomb),
    ici recoupe par un canal INDEPENDANT (l'activite d'un effet).
    ⇒ `AdjacentTilesSelector` (le chemin DSL) et `BattleQuery$$IterateAdjacentTiles` (celui
    d'`IsCharging` / des comptages `GetAdjacent*`, mirror `battle_query.is_adjacent`) NE LISENT PAS
    le meme substrat, et le port suit chacun a sa place.

    `None` si le porteur n'a ni equipe ni tuile (cle alors ABSENTE du `unit_state` => la
    `CreateActiveCondition` degrade en VRAI, et le canal crit ne contribue RIEN) -- jamais un 0
    invente, qui annulerait le produit et ferait passer une reduction reelle pour une absence."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from ..entities.effects.loki.amulet_of_the_voidwyrm import (
        adjacent_friendly_summons_and_decoys_selector)
    from .abilities.behaviours import entities_from_state
    return int(adjacent_friendly_summons_and_decoys_selector()
               .calculate(entities_from_state(state, int(unit_id))))


class UnitEffectStateView(Mapping):
    """Le `unit_state` d'une unité — vue MAPPING PARESSEUSE sur l'ECS (`unit_state_for_effects`).

    Clés (chacune n'est PRÉSENTE que si l'ECS peut la renseigner — une clé ABSENTE = « donnée
    inconnue », et c'est ce que chaque `is_active` traite en dégradation fidèle) :

      * `hp` / `max_hp` — `HealthComponent` ; lus par les conditions `StatAmount(Self, HEALTH,
        CURRENT/CURRENT_PCT)` (`AnvilShield_BlockChanceBelowHealthCap`, `PowerTrip_FullHealth`) ;
      * `traits` — `StatsComponent.ctx.traits` (NOMS gameconfig, même convention que tous les
        `HasTrait(...)` portés) ; lus par les conditions de TRAIT
        (`PinnedEffect$$CreateActiveCondition` = `Not(HasTrait(Self, 0x40f = TerminatorArmour))`) ;
      * `enemy_psykers_alive` — cardinal battlefield-wide, PARESSEUX (O(entités), cf.
        `enemy_psykers_alive`) : il n'est calculé que si un effet le LIT réellement. La clé est
        présente dès que l'équipe du porteur est connue, absente sinon.
      * `tiles_moved_this_turn` — `ActorStatisticsComponent+0xf0` (`unit_tiles_moved_this_turn`) ;
        lu par `ModifiedExoarmour_ExtraDmgEffect$$CreateActiveCondition` =
        `AmountIsGreaterThanZero(TilesMovedThisTurn(Self))`. La cle n'est presente que si l'entite
        a un `UnitComponent` : cote COMBAT le compteur est DESORMAIS mesure (`record_tiles_moved`
        est appele par `MoveUnitOperation`), donc `is_active` rend le gate natif VERBATIM au lieu
        de la degradation « non mesure -> on ne ferme pas ». Cote DECISION la `Scene` ne pose PAS
        cette cle : elle evalue l'etat SIMULE et le compte y vient du `att_ctx`, pas du porteur.
      * `has_moved` — `HasFlag(Self, 0 = UnitFlag.Moved)` (`unit_has_moved`, LECTEUR UNIQUE du
        `UnitFlagsComponent`) ; lu par `InescapableAccuracy_ExtraCritChanceEffect$$
        CreateActiveCondition` = `op_LogicalNot(HasFlag(Owner, 0))`. La cle n'est presente que si
        l'entite existe ; le composant absent vaut « n'a pas bouge » (comme le natif, dont le
        `UnitFlagsComponent$$Has` sur un set vide rend faux).
      * `is_turn_of_owner` — `IsTurnOf(Owner)` = `<DSLTriggers+0x28>`, MEME noeud natif que le canal
        `att_ctx["is_turn_of_owner"]` (foyer `entities/effects/base.py::is_turn_of_owner`) : ici
        `OwnerComponent.player == State.current_player_id`, mirror de
        `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer`. Lu par
        `MartialSuperiority_VisualEffect$$CreateActiveCondition` = `op_LogicalNot(...)`. La cle
        n'est presente que si le proprietaire ET le joueur courant sont connus ; absente = « non
        mesure » -> la condition degrade en VRAI.
      * `has_effect_light_cover` / `is_target_of_big_target_adjacent` — les DEUX membres du
        `op_BitwiseOr` de `IdunBattle.Entities.Effects.Loki.CamoCloak_DmgReductionEffect$$
        HasValidEffectTrigger` (`HasEffect(sel, 1013, onlyActive=0, 6)` /
        `IsEffectTarget(sel, 1026)`), lus par la `CreateActiveCondition` de `1014
        CamoCloak_DmgReduction`. PARESSEUX (chacun balaie : `EffectsState` pour le premier, les
        entites ring-1 pour le second). Le premier est present des que le state porte une
        `EffectsState`, le second des que l'unite est SUR le plateau (le selecteur natif est un
        `AdjacentFriends`, il n'a pas de sens hors position). Cle absente = donnee non threadee ->
        `camo_cloak_cover` degrade en VRAI (« present == actif »), jamais en FAUX.
      * `contagions_of_nurgle_amount` — **un CALLABLE** `(source_unit_id) -> int | None`, et non une
        valeur : le nœud natif `ContagionsOfNurgleAmount(team, unit)` prend l'EFFECT SOURCE en
        entrée, donc le cardinal dépend de l'INSTANCE d'effet qui l'interroge, pas seulement du
        porteur. Paresseux par construction (rien n'est calculé tant qu'aucune instance n'appelle),
        et présent dès que l'unité a une position.
      * `structural_analyser_friends` — cardinal battlefield-wide, PARESSEUX (O(entités), cf.
        `structural_analyser_friends`) : le sélecteur `AdjacentFriends + UnitsFromFaction(
        SurroundingFriends(2), Tau)` que `AmountIsGreaterThanZero` compare à 0 dans
        `IdunBattle.Entities.Effects.Loki.StructuralAnalyser_VisualEffect$$CreateActiveCondition`
        (case-366-r1). La clé est présente dès que le porteur a une équipe ET une tuile.
      * `adjacent_friendly_summons_and_decoys` — cardinal PARESSEUX (O(entités), cf.
        `adjacent_friendly_summons_and_decoys_count`) : l'arbre `Count(UnitsWithTrait(
        AdjacentFriends(Owner), Summon) + UnitsWithTrait(AdjacentFriends(Owner), Decoy))` que
        `AmountIsGreaterThanZero` compare à 0 dans
        `IdunBattle.Entities.Effects.Loki.AmuletOfTheVoidwyrm_CritDamageReductionEffect$$
        CreateActiveCondition` (#589-r1-r1-r2-r1). MÊME gate de présence que la clé ci-dessus
        (sélecteur géométrique ET par équipe) : présente dès que le porteur a une équipe ET une tuile.
      * `turns_started` — `RoundsStarted(Owner@DSLSelectors+0x30)` =
        `IdunBattle.Entities.Formulas.RoundsStartedFormula$$Calculate` (somme de
        `UnitComponent.turnsStarted@+0x58` sur le sélecteur, ici mono-unité = le porteur), MÊME
        grandeur que `GetStat(unit, 0xc = TURNS_STARTED)` — le compteur qu'incrémente
        `StartTurnOperation` (`runner/operations/turnflow.py`). Lu par
        `IdunBattle.Entities.Effects.Loki.ReinforcedHiveNode_ExtraArmorEffect$$CreateActiveCondition`
        (corps FONDU avec celui d'`..._ExtraBlockEffect`) =
        `AmountIsOdd(Sum(RoundsStarted(Owner), Direct(1)))`. EAGER (lecture de stat). La clé n'est
        présente que si l'entité porte un `StatsComponent` avec son `UnitContext`.

    La paresse n'est pas une optimisation gratuite : `active_effects` est appelé dans des boucles
    par-porteur des chemins de dégât (auras), donc un cardinal EAGER y serait quadratique."""

    __slots__ = ("_state", "_uid", "_eager", "_has_psy", "_psy", "_has_pos",
                 "_has_effstate", "_lc", "_bta", "_has_sa", "_sa", "_asd")

    def __init__(self, state, unit_id: int) -> None:
        self._state = state
        self._uid = int(unit_id)
        ent = state.get_entity(self._uid) if state is not None else None
        eager: Dict[str, object] = {}
        hc = ent.get_component(HealthComponent) if ent is not None else None
        if hc is not None:
            eager["hp"], eager["max_hp"] = hc.hp, hc.hp_max
        sc = ent.get_component(StatsComponent) if ent is not None else None
        traits = (sc.ctx.traits if (sc is not None and getattr(sc, "ctx", None) is not None)
                  else None) or []
        if traits:
            eager["traits"] = traits
        # `TilesMovedThisTurn(Self)` = `ActorStatisticsComponent+0xf0` (cf. la docstring de classe).
        # EAGER : c'est un simple champ int deja materialise, aucun balayage.
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is not None:
            eager["tiles_moved_this_turn"] = int(uc.tiles_moved_this_turn or 0)
        # `HasFlag(Self, 0 = UnitFlag.Moved)` (cf. la docstring de classe). EAGER : `unit_has_moved`
        # est une lecture de set sur le `UnitFlagsComponent`, aucun balayage. C'est le MEME store
        # que le gate no-move deja porte sur l'axe DEGAT (`CrushingStrike`), donc les deux axes ne
        # peuvent pas diverger.
        if ent is not None:
            eager["has_moved"] = unit_has_moved(state, self._uid)
        # `RoundsStarted(Owner@DSLSelectors+0x30)` (cf. la docstring de classe). EAGER : simple
        # lecture du `StatComponent` deja materialise, aucun balayage.
        if sc is not None and getattr(sc, "ctx", None) is not None:
            from ..entities.stats import StatType as _ST
            eager["turns_started"] = int(sc.ctx.get_stat(int(_ST.TURNS_STARTED), 0) or 0)
        oc = ent.get_component(OwnerComponent) if ent is not None else None
        # `IsTurnOf(Owner)` (`<DSLTriggers+0x28>`) — MEME noeud natif que le canal
        # `att_ctx["is_turn_of_owner"]` (foyer `entities/effects/base.py::is_turn_of_owner`), donc
        # MEME lecture : `OwnerComponent.player == State.current_player_id`, mirror de
        # `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer`. Lu par la
        # `CreateActiveCondition` de `1255 MartialSuperiority_Visual`
        # (`op_LogicalNot(<DSLTriggers+0x28>)`). EAGER : deux lectures de champ, aucun balayage.
        # Cle ABSENTE si le proprietaire ou le joueur courant n'est pas connu = « non mesure » ->
        # la condition degrade en VRAI (on ne masque pas l'effet a tort).
        # ⚠ `oc.player` peut etre `None` MEME quand l'`OwnerComponent` existe : c'est le cas de
        # toute unite HORS PLATEAU sous un `ATeleportingEffect` (1035/1140/1238/1573), que
        # `decisionView` publie avec `visualId`, `team` ET `pos` a `null` (mesure #425/#448-r1) --
        # le seed n'a alors PAS de joueur a poser. C'est exactement le « proprietaire non connu »
        # que la ligne ci-dessus decrit : la cle doit rester ABSENTE, pas lever un `TypeError`
        # (trouve en portant `StormboyzStrike_FallbackAbility`, dont le porteur EST dans cet etat).
        cur = getattr(state, "current_player_id", None) if state is not None else None
        if oc is not None and oc.player is not None and cur is not None:
            eager["is_turn_of_owner"] = (int(oc.player) == int(cur))
        self._eager = eager
        self._has_psy = oc is not None            # `Enemies(Owner, …)` calculable
        self._psy: Optional[int] = None
        # `ContagionsOfNurgleAmount(team, unit)` : le natif `SelectSingle` la cible et sort a 0 si
        # elle n'a pas de tuile (`GetInRangeAuraAmount` deref `MainTile`) -> la cle n'existe que si
        # l'unite est SUR le plateau.
        self._has_pos = (ent is not None and ent.get_component(PositionComponent) is not None)
        # `HasEffect(sel, 1013 LightCover, onlyActive=0, 6)` : calculable des que le state porte une
        # `EffectsState` ; `IsEffectTarget(sel, 1026)` exige EN PLUS une position (selecteur ring-1).
        self._has_effstate = getattr(state, "effects", None) is not None
        self._lc: Optional[bool] = None
        self._bta: Optional[bool] = None
        # `AdjacentFriends + UnitsFromFaction(SurroundingFriends(2), Tau)` : selecteur GEOMETRIQUE
        # ET par equipe -> la cle n'existe que si le porteur a une tuile ET une equipe.
        self._has_sa = (self._has_pos and oc is not None and oc.team is not None)
        self._sa: Optional[int] = None
        # `AdjacentFriends(Owner) filtre Summon/Decoy` : MEME gate que ci-dessus (selecteur
        # geometrique ET par equipe) -> la cle n'existe que si le porteur a une tuile ET une equipe.
        self._asd: Optional[int] = None

    def __getitem__(self, key):
        if key in self._eager:
            return self._eager[key]
        if key == "enemy_psykers_alive" and self._has_psy:
            if self._psy is None:
                self._psy = enemy_psykers_alive(self._state, self._uid)
            return self._psy
        if key == "contagions_of_nurgle_amount" and self._has_pos:
            state, uid = self._state, self._uid
            return lambda source_id: contagions_of_nurgle_amount(state, uid, source_id)
        # `CamoCloak_DmgReductionEffect$$HasValidEffectTrigger` (case-366-r1) — les DEUX membres du
        # `op_BitwiseOr`, PARESSEUX (chacun balaie, on ne paie que si une instance 1014 les lit).
        if key == "has_effect_light_cover" and self._has_effstate:
            from ..entities.effect_type import EffectType
            if self._lc is None:
                self._lc = has_effect_of_type(self._state, self._uid, int(EffectType.LightCover))
            return self._lc
        if key == "is_target_of_big_target_adjacent" and self._has_pos:
            from ..entities.effect_type import EffectType
            if self._bta is None:
                self._bta = is_target_of_adjacent_friend_aura(
                    self._state, self._uid, int(EffectType.BigTarget_AdjacentEffect))
            return self._bta
        if key == "structural_analyser_friends" and self._has_sa:
            if self._sa is None:
                self._sa = structural_analyser_friends(self._state, self._uid)
            return self._sa
        if key == "adjacent_friendly_summons_and_decoys" and self._has_sa:
            if self._asd is None:
                self._asd = adjacent_friendly_summons_and_decoys_count(self._state, self._uid)
            return self._asd
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        yield from self._eager
        if self._has_psy:
            yield "enemy_psykers_alive"
        if self._has_pos:
            yield "contagions_of_nurgle_amount"
            yield "is_target_of_big_target_adjacent"
        if self._has_effstate:
            yield "has_effect_light_cover"
        if self._has_sa:
            yield "structural_analyser_friends"
            yield "adjacent_friendly_summons_and_decoys"

    def __len__(self) -> int:
        return (len(self._eager) + (1 if self._has_psy else 0) + (2 if self._has_pos else 0)
                + (1 if self._has_effstate else 0) + (2 if self._has_sa else 0))

    def __repr__(self) -> str:                    # diagnostic (ASCII)
        return "UnitEffectStateView(u%d, %s)" % (self._uid, sorted(self))


def unit_state_for_effects(state, unit_id: int) -> UnitEffectStateView:
    """LE constructeur du `unit_state` passé à `EffectsState.active_effects` / `BaseEffect.is_active`
    (mirror du contexte d'évaluation de `RefreshEffectsOperation$$ShouldBeActive`). Tout appelant
    runner l'utilise — aucun `{"hp": ...}` ad hoc, sinon les conditions non-HP se dégradent en VRAI
    en silence (#208).

    LECTURE SEULE, et le périmètre est CLOS : `HealthComponent`, `StatsComponent.ctx.traits` (+ son
    `UnitStats`, pour la clé `turns_started` = `GetStat(., 0xc)`),
    `OwnerComponent`, `UnitComponent.alive`/`visual_id`, `PositionComponent` (les deux clés
    PARESSEUSES `contagions_of_nurgle_amount` et `structural_analyser_friends`, dont le corps ne
    s'exécute que si une instance d'effet les lit), et — depuis case-366-r1 — le
    `UnitFlagsComponent` en LECTURE SEULE via
    `unit_has_moved` (clé `has_moved`, exigée par la `CreateActiveCondition`
    `NOT HasFlag(Owner, Moved)` d'`InescapableAccuracy_extraCritChance`). Cette vue n'ÉCRIT rien :
    le seed de flags de `load_state` (`snapshot._load_unit_flags`, case-o10) reste le seul
    producteur, il n'y a donc ni double écriture ni contrainte d'ordre d'init.
    L'autre point de contact est `unit_prevents_overkill` ci-dessus, qui interroge le composant de
    flags d'ABORD et ne retombe sur la dérivation par l'effet 1354 qu'ensuite : le seed rend ce repli
    moins fréquent, il ne le rend pas faux — et il reste indispensable pour un effet posé OFFLINE en
    cours de bataille, que le snapshot n'a jamais vu."""
    return UnitEffectStateView(state, unit_id)
