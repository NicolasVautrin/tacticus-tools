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
    (cf. `operations/revive.py`)."""
    __slots__ = ("visual_id", "alive", "ai_controlled", "turn_defeated", "times_attacked_this_turn",
                 "received_damage_this_turn", "revive_used_this_turn", "pending_revive")

    def __init__(self, visual_id: Optional[str], alive: bool, ai_controlled: bool = False):
        self.visual_id = visual_id
        self.alive = alive
        self.ai_controlled = ai_controlled
        self.turn_defeated = None
        self.times_attacked_this_turn = 0
        self.received_damage_this_turn: dict = {}
        self.revive_used_this_turn = False
        self.pending_revive = None            # `Nullable<ReviveData>` @UnitComponent+0xa8


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
    TELEPORTED = 12             # UnitFlag.Teleported
    AMBUSH_CONSUMED = 14        # flag 0xe (UnitPostAbility) — G3 : Ambush ré-suscité UNE fois ; posé par
                                # `ResurrectUnitOperation` (Add 0xe), testé `Not(HasFlag 0xe)` par les 2 triggers
                                # Ambush → résurrection one-shot. PERMANENT : survit à `remove_turn_flags` (pas un
                                # flag de tour), donc re-mourir ne re-déclenche PAS une 2e résurrection.
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

    ⚠ RESIDU : cette source (effet 0x426 `ListenUpMaggots`, trigger IdunBattleLogic.Entities.Abilities.Active.Loki.ListenUpMaggotsAbility$$CreateTrigger) n'est PAS portee -> le
    dict reste VIDE offline et `get_ability_stat_modification` rend 0. C'est l'etat CONFRONTE live
    (2 probes : meme avec Kell VIVANT en jeu au moment du cast, le natif summon 2 gardes = modification
    nulle) -- pas une degradation silencieuse. Le composant + les deux semantiques de CONSOMMATION
    (additive pour nrOfSummons, OVERRIDE pour range, cf. `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour) sont portes 1:1 et exerces offline en injectant une modification."""
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
