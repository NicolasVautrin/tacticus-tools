"""Composants ECS concrets — port FIDÈLE (noms 1:1 du natif, VA citée).

`IdunBattle.Entities.Components.*Component`. Tranche 0 : seuls les composants de
l'ÉTAT D'UNITÉ diffé (position/HP/owner/identité/effets) sont posés, avec les champs
qu'on peut peupler depuis la vérité live (decisionView/observeBattle, qui lisent
ces composants natifs). Les OFFSETS exacts (layout) seront RE'd quand une operation
les ÉCRIRA (tranche move/damage/effects) ; ici on porte la sémantique des champs.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Hashable, List, Optional

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
        tout le RESTE de la mort (`On(2)`, `On(0)`, `On(55)`, `On(54)`, Remove(flag 0xf)/Add(flag 6),
        `RemoveEffects`, `RegisterDefeatedUnit`) est SOUS cette garde. Un revive posé pendant `On(1)`
        ANNULE donc la mort (cf. `damage.py::_fire_death_if_killed`) ;
      * LECTURE+PURGE `IdunBattle.Operations.ReviveUnitOperation$$Execute` : lit les 9 qwords @0xa8..0xe8, refuse
        (log d'erreur + return) si `!HasValue` @IdunBattle.Operations.ReviveUnitOperation$$Execute+0x2ba, applique le revive, puis REMET LES 9 QWORDS
        À 0 @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+ (donc APRÈS l'émission de `On(UnitRevived=0x2e)`).
    Port : `None` = pas de revive en attente ; sinon un dict `{amount, heal_type, source, priority}`
    (cf. `operations/revive.py`).

    `parent_id` = mirror du lien PARENT natif (`ParentComponent`, champ id @+0x10 ; observable live
    `Unit_Parent_Id` emis au spawn d'un summon). C'est ce que lit le selecteur
    `IdunBattle.Entities.Selectors.ParentSelector$$Select` (-> `IdunBattle.Entities.UnitExtensions$$GetParent`),
    consomme par `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$CreateTargetSelector`
    (`Parent(Self)` = le SUMMONER) et par le gate `IsFriendlyKell` du playbook SupremeCommander.
    None = unite sans parent (toute unite du roster initial). Pose par `SpawnUnitOperation`
    (`_spawn_config_grot`, mirror `SpawnUnitOptions` -> `Unit_Parent_Id = casterId`).

    Le lien RECIPROQUE (parent -> enfants) n'est PAS materialise : le port le derive en balayant
    `state.entities` (cf. `children_of`), la ou le natif tient une liste `ParentComponent.children`.

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
                 "charged_unit_ids")

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
    CE composant marque la nature Machine + le slot."""
    __slots__ = ("slot",)
    SLOT_NONE = 0
    SLOT_TOP = 1
    SLOT_BOTTOM = 2

    def __init__(self, slot: Optional[int] = None):
        self.slot = slot


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
    (mirror du clamp de `IdunBattle.Entities.Components.FillUpStatComponent$$Reduce`)."""
    __slots__ = ("hp", "hp_max", "minimal_health")

    def __init__(self, hp: Optional[int], hp_max: Optional[int], minimal_health: Optional[int] = None):
        self.hp = hp
        self.hp_max = hp_max
        self.minimal_health = minimal_health

    def reduce(self, amount: int, *, ignore_minimal: bool = False) -> int:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$Reduce` — retire `amount` PV, borné : jamais > PV courant (pas de
        PV négatifs) et, si `minimal_health` est posé et `ignore_minimal` est faux (param_3 natif = flag de
        bypass), jamais sous `min(hp, minimal_health)` (le HP-floor Hypersensory). Renvoie la réduction RÉELLE
        appliquée (`iVar3`). No-op (0) si `hp` non capté. Mute `self.hp`."""
        if self.hp is None:
            return 0
        amount = max(0, int(amount))                    # Max(0, param_2)
        red = min(amount, self.hp)                       # Min(iVar2, current) — pas de PV négatifs
        if not ignore_minimal and self.minimal_health is not None:
            floor = min(self.hp, int(self.minimal_health))   # Min(current, minimalHealth.Value)
            red = min(self.hp - floor, red)              # Min(current - floor, iVar3) — clamp au plancher
        self.hp -= red
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
    """`IdunBattle.Entities.Components` — cibles d'attaque FORCÉES de l'unité (liste d'ids d'unité).

    Posé/maj par `IdunBattle.Entities.Behaviours.AddForcedAttackTargetBehaviour$$Execute / retiré par
    `IdunBattle.Entities.Behaviours.RemoveForcedAttackTargetBehaviour$$Execute (le natif stocke des entity-ids dans une liste
    de composant bond @+0x50/+0x58). LU par `IdunBattle.Entities.Selectors.UnitForcedAttackTargetsSelector$$Select
    (`GetOnlyTargets` → liste des cibles forcées) = le point où l'IA **doit** cibler ces unités en priorité
    (cf. `GetAttackTarget` priorité `ForcedAttackTargets > nearest-enemy`, triggers.py). Deux sources :
    Taunt (la cible est forcée d'attaquer le tauntant) et Instinctive Behaviour (hors Synapse → forcée
    d'attaquer l'ennemi le plus proche). On clé par id d'UNITÉ (== ECS), comme le reste du runner."""
    __slots__ = ("targets",)

    def __init__(self, targets: Optional[List[int]] = None):
        self.targets: List[int] = list(targets) if targets else []

    def add(self, target_id: int) -> bool:
        """Ajoute une cible forcée (idempotent). Renvoie True si ajoutée (absente avant)."""
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

    def get(self) -> List[int]:
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
        1187."""
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

    def clear_all_persistent_data(self) -> None:
        """`IdunBattle.Entities.Components.PersistentDataComponent$$ClearAllPersistentData() : vide le sac (resurrection)."""
        self.data.clear()


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
    Renvoie l'empreinte posee."""
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
    if len(uc.feet) <= 1:
        uc.feet = None                       # un pied = cas NOMINAL, pas de liste materialisee
    if tiles:
        pc = e.get_component(PositionComponent)
        if pc is None:
            e.add_component(PositionComponent(tiles[0][0], tiles[0][1]))
        else:
            pc.col, pc.row = tiles[0]        # main tile = feet[0] (`GetMainTileId`)
    return get_unit_feet(state, unit_id)


# --- Lien PARENT / ENFANTS (`ParentComponent`) --------------------------------------------------- #
def parent_of(state, unit_id):
    """`IdunBattle.Entities.UnitExtensions$$GetParent(unit)` (lu par
    `IdunBattle.Entities.Selectors.ParentSelector$$Select`) : l'entite PARENTE (le summoner), ou None.
    Le port lit `UnitComponent.parent_id` pose au spawn."""
    e = state.get_entity(unit_id) if unit_id is not None else None
    uc = e.get_component(UnitComponent) if e is not None else None
    pid = getattr(uc, "parent_id", None) if uc is not None else None
    return state.get_entity(pid) if pid is not None else None


def children_of(state, unit_id, alive_only: bool = True) -> list:
    """Enfants (summons) de `unit_id` — mirror de `ParentComponent.children` cote natif, DERIVE ici par
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
    if added and state.effects is not None and any(
            state.effects.has_effect(unit_id, effect_type=t) for t in _TELEPORT_MOVE_EFFECTS):
        fl.add(UnitFlagsComponent.TELEPORTED)                 # Add(0xc) — le move etait un teleport
    return added


def unit_has_moved(state, unit_id: int) -> bool:
    """`HasFlag(unit, UnitFlag.Moved=0)` (`IdunBattleLogic.Entities.DSLFactory$$HasFlag` ->
    `IdunBattle.Entities.Conditions.HasFlagAbilityTrigger$$ShouldTrigger` = `UnitFlagsComponent.Has`).
    LECTEUR UNIQUE du fait « a bouge ce tour » cote port : le natif n'a QU'UN store (le
    `UnitFlagsComponent`), pose par `set_moved_flag` et purge par `RemoveTurnFlags(new_activation=1)`
    du `StartTurnOperation` — PAR JOUEUR ENTRANT, pas globalement. Consommateurs : le gate no-move de
    `HeavyWeapon_ExtraDmg`/`CrushingStrike` (via `attacker_modifiers`), la branche fin-de-tour de
    `RadSaturation`, le `GetHits` d'HarvesterOfSouls. Composant absent = flag absent = n'a pas bouge
    (etat charge par `load_state` : le RPC n'expose pas les UnitFlags -> une fixture qui SAIT que
    l'unite a bouge doit poser le flag, cf. tests live)."""
    e = state.get_entity(unit_id)
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    return bool(fl is not None and fl.has(UnitFlagsComponent.MOVED))


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

    La liste est videe par `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` (cf.
    `FinishUnitTurnOperation.execute`) -> sa duree de vie est L'ACTIVATION de l'unite, ce qui donne au
    predicat `IsCharging` sa semantique « a charge cette cible CE TOUR ». Aucun autre site natif
    n'ecrit ce champ (xrefs de `UpdateCharging` : les 2 call-sites de `Execute` ; le seul autre
    lecteur est `BattleQuery$$IsCharging`)."""
    import hexgeo
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or new_pos is None:
        return []

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
            if hexgeo.distance(tuple(pos), (opc.col, opc.row)) == 1:
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
    `On(0x12) -> ActivateEffect`, `On(0x2e)&OwnerIsTarget -> DeactivateEffect`) -> le flag vaut
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
    hc = entity.get_component(HealthComponent)
    return effects_prevent_overkill(
        eff.active_effects(int(unit_id), {"hp": hc.hp if hc is not None else None}))


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
