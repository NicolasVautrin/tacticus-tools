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
    """Identité d'unité — `UnitComponent` @180facf20 / `BaseUnitComponent` @180f96380.
    `visual_id` = id visuel (ex. 'necroNpc1Warrior'), `alive` = vivante.

    `ai_controlled` = l'unité est jouée par l'IA au turn-start de sa team, MÊME sur une team
    par ailleurs contrôlée par le joueur (cas des SUMMONS). Mirroir du flag per-unité runtime lu par
    `IdunGameViews.IsPlayerAiControlled` @1804d7b10 (SortedDictionary +0x18==1 → AI-contrôlé ; posé
    quand l'unité est invoquée). N'est PAS un trait gameconfig — c'est un état runtime posé au spawn
    (cf. `SpawnUnitOperation`). Une unité d'une team entièrement-IA est de toute façon jouée par l'IA
    (type player 2) ; ce flag cible le cas summon-sur-team-joueur.

    `turn_defeated` = valeur de `state.turn_counts[owner_player]` AU MOMENT de la mort (G3 Ambush) —
    mirror du `TurnDefeated` que `GetUnitsEligibleForResurrect @180f79b90` lit dans
    `AmountIsEqual(Difference(CurrentPlayerTurnsStarted, TurnDefeated(u)), @0xc0=1)`. None tant que
    l'unité n'est pas morte. Posé par `Ambush_SummonAbility` (trigger On(UnitDefeated))."""
    __slots__ = ("visual_id", "alive", "ai_controlled", "turn_defeated")

    def __init__(self, visual_id: Optional[str], alive: bool, ai_controlled: bool = False):
        self.visual_id = visual_id
        self.alive = alive
        self.ai_controlled = ai_controlled
        self.turn_defeated = None


class OwnerComponent(Component):
    """Propriétaire — `OwnerComponent` @180fa64c0. `team` = équipe (1/2) ; `player` = id du player
    (≠ team : team 1 = player 3, team 2 = player 4 ; un summon hérite team ET player du caster via
    `SpawnUnitOptions.CopyOwner`, cf. project_summon_team_model). `player` None si non capté."""
    __slots__ = ("team", "player")

    def __init__(self, team: Optional[int], player: Optional[int] = None):
        self.team = team
        self.player = player


class PositionComponent(Component):
    """Position sur le board — `PositionComponent` @180fa6db0 (et `UnitFootComponent`
    @180fad890 : UnitId@0x10, TileId@0x14). Coordonnées hex (col,row)."""
    __slots__ = ("col", "row")

    def __init__(self, col: int, row: int):
        self.col = col
        self.row = row


class HealthComponent(Component):
    """PV — `HealthComponent` @180f9f1b0. `hp` courant, `hp_max` plafond."""
    __slots__ = ("hp", "hp_max")

    def __init__(self, hp: Optional[int], hp_max: Optional[int]):
        self.hp = hp
        self.hp_max = hp_max


class EffectsOwnedComponent(Component):
    """Effets actifs portés — `EffectsOwnedComponent` @180f99a50 (chaque effet =
    `EffectComponent` @180f61990). Ici : liste des NOMS d'effets actifs (vue pour le
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
    """`IdunBattle.Entities.Components.ShieldComponent` @180fa8770 — pool de boucliers de l'unité
    (liste d'instances @+0x10 + compteur d'id @+0x18). Un bouclier ABSORBE le dégât AVANT les PV
    (`CalculateDamageOperation` : shield-first, sur le coup déjà réduit par l'armure fixe), et perd 1
    tour à chaque `EndTurn` (`RemoveOneTurnOnShields` → `RemoveOneTurn`). `GetTotalShield` = somme des
    `amount` (>0)."""
    __slots__ = ("shields", "next_id")

    def __init__(self, shields: Optional[List["ShieldInstance"]] = None, next_id: int = 0):
        self.shields: List[ShieldInstance] = shields if shields is not None else []
        self.next_id = next_id

    def get_total_shield(self) -> int:
        """`ShieldComponent.GetTotalShield` @180fa7f30 = Σ des `amount` des instances."""
        return sum(int(s.amount) for s in self.shields if s.amount > 0)

    def remove_one_turn(self) -> dict:
        """`ShieldComponent.RemoveOneTurn` @180fa8080 : pour chaque instance À DURÉE (remaining non-None ;
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
        """`ShieldComponent.AddOrUpdateShield` @180fa7290 : accorde un bouclier. Si une instance de MÊME
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

    Posé/maj par `AddForcedAttackTargetBehaviour.Execute` @180fb5800 / retiré par
    `RemoveForcedAttackTargetBehaviour.Execute` @180fcd890 (le natif stocke des entity-ids dans une liste
    de composant bond @+0x50/+0x58). LU par `UnitForcedAttackTargetsSelector.Select` @180eff450
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
    """`IdunBattle.Entities.Components.UnitFlagsComponent` @180fad640 — drapeaux booléens de l'unité
    (un `OrderedSet<int>` @+0x10 ; `Add`/`Remove`/`Has`/`TurnEnded`/`RemoveTurnFlags`). Valeurs = enum
    `IdunBattle.Entities.Enum.UnitFlag` (dump symbols.json) ; on porte le set d'ints (sémantique 1:1).

    Flags de TOUR (mission #139 — cycle posé/appliqué/reset, VAs) :
      • `TURN_FINISHED (3)` : le tour de l'UNITE est fini — posé par `FinishUnitTurnOperation.Execute`
        @180e72140 (déclenché après une ability qui « termine le tour », cf. abilities/handler.py) ; lu par
        `UnitFlagsComponent.TurnEnded` @180fad510 (= Contains(3)) via `VerifyUnitsTurnFinishedOperation.
        VerifyUnitTurnEnded` @180eded20 et `AttackQuery.CanAttackAnyUnitFromAnyTileWithAnyAbility` @181054ccc.
      • `ACTIVE_ABILITY_USED (2)` : une ability active a été utilisée ce tour — posé par
        `ActiveAbilityOperation.AddFlagsAfterAbilityExecution` @180e447f0 ; base du trigger DSL
        `HasOwnersActiveAbilityBeenUsed` (DSLFactory+0x110).
      • `ARRIVED_AT_FINAL_TILE (1)` : posé avec TURN_FINISHED par FinishUnitTurnOperation.
      • `NO_ACTION_AVAILABLE (4)` : auto-fin (rien à faire) — posé par `MarkUnitAsNoActionAvailableOperation`
        @180e78c0c ; ré-ouvert par VerifyUnitTurnEnded (slot 0x77) si l'unité regagne des options.
      • `FLED (9)` : « a fui » (FleeOperation ; re-testé NOT HasFlag(self,9) par BattleFatigue).
      • `TURN_FINISHED_FORCED (27 = 0x1b)` : posé par FinishUnitTurnOperation quand `forced` (hors enum du
        dump — ajout post-dump ; nom descriptif, structure lue @180e72140/@180fad310)."""
    __slots__ = ("flags",)
    MOVED = 0                   # UnitFlag.Moved (posé par UnitExtensions.SetMovedFlag @180ed9890)
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
        """`UnitFlagsComponent.TurnEnded` @180fad510 = Contains(TurnFinished=3). Lu par le turn-flow natif
        (VerifyUnitTurnEnded @180eded20) et par l'AttackQuery pour exclure les unités finies."""
        return self.TURN_FINISHED in self.flags

    def remove_turn_flags(self, include_no_action: bool = False, new_activation: bool = True) -> None:
        """`UnitFlagsComponent.RemoveTurnFlags` @180fad310 : retire TOUJOURS {ActiveAbilityUsed(2),
        TurnFinished(3), 27} ; + {NoActionAvailable(4)} si `include_no_action` (param_3 natif) ;
        + {Moved(0), Teleported(12), ArrivedAtFinalTile(1)} si `new_activation` (param_4 natif).
        `StartTurnOperation.Execute` @180ea3fb0 l'appelle (0, 1) pour chaque unité du joueur entrant."""
        if new_activation:
            for f in (self.MOVED, self.TELEPORTED, self.ARRIVED_AT_FINAL_TILE):
                self.flags.discard(f)
        if include_no_action:
            self.flags.discard(self.NO_ACTION_AVAILABLE)
        for f in (self.ACTIVE_ABILITY_USED, self.TURN_FINISHED, self.TURN_FINISHED_FORCED):
            self.flags.discard(f)


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
    (RE `TriggeredAbilityComponent.MarkAsTriggered`@180fab0e0 / `GetTimesTriggeredThisPhase`@180faafc0) :
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
    """`IdunBattle.Entities.Components.TriggeredAbilityComponent` @180faba40 — registre par-unité des
    ability-triggers, avec leur compteur de déclenchements. Native = `KeyedCollection` @+0x18 indexée par
    l'ability-type (config-id) ; chaque entrée porte `has_triggered`/`total`/`times_this_phase`
    (cf. `TriggeredAbilityState`).

    RÔLE : le natif GATE chaque déclenchement de trigger à `GetTimesTriggeredThisPhase(key) < 0x33`
    (=51) dans `EvaluateTriggerOperation.EvaluateAbilityTrigger` @180e6d650 (cap anti-emballement d'une
    PHASE = une activation d'unité) ; `MarkAsTriggered` incrémente au fire ; `ResetPhase` (via
    `EndPhaseOperation.ResetEntityPhase` @180e6a210, à la fin de chaque activation) remet
    `times_this_phase` à 0 (PAS `total`). Sans ce cap, une chaîne de triggers générateurs d'attaque
    (splash Psyker qui re-déclenche le splash Psyker via le vecteur after-hit) récurserait sans borne.

    Peuplé au build de l'unité pour CHAQUE ability (natif `UnitFactory.Add*Abilities` → `TryAdd`
    @180fab7a0). Offline : clé = un identifiant stable d'ability-type (cf. Slice 2). Population +
    gate + reset = slices #142/#143/#144."""
    __slots__ = ("entries",)

    def __init__(self, entries: Optional[Dict[Hashable, "TriggeredAbilityState"]] = None):
        self.entries: Dict[Hashable, TriggeredAbilityState] = entries if entries is not None else {}

    def try_add(self, key: Hashable) -> bool:
        """`TryAdd` @180fab7a0 : enregistre l'ability `key` si absente (compteurs à 0). No-op (renvoie
        False) si déjà présente ; True si ajoutée."""
        if key in self.entries:
            return False
        self.entries[key] = TriggeredAbilityState()
        return True

    def get_times_triggered_this_phase(self, key: Hashable) -> int:
        """`GetTimesTriggeredThisPhase` @180faafc0 : compteur de la phase courante pour `key` ; **0 si
        la clé est absente** (TryGetValue échoue → 0)."""
        e = self.entries.get(key)
        return e.times_this_phase if e is not None else 0

    def mark_as_triggered(self, key: Hashable) -> None:
        """`MarkAsTriggered` @180fab0e0 : `has_triggered=True`, `total += 1`, `times_this_phase += 1`.
        **No-op si la clé est absente** (le natif TryGetValue échoue et `return`)."""
        e = self.entries.get(key)
        if e is None:
            return
        e.has_triggered = True
        e.total += 1
        e.times_this_phase += 1

    def has_been_triggered(self, key: Hashable) -> bool:
        """`HasBeenTriggered` @180fab050 : True si l'ability a déjà été déclenchée (any phase). False si
        clé absente."""
        e = self.entries.get(key)
        return bool(e.has_triggered) if e is not None else False

    def reset_phase(self) -> None:
        """`ResetPhase` @180fab1e0 : remet `times_this_phase` à 0 pour TOUTES les entrées (le `total` et
        `has_triggered` sont conservés). Appelé au boundary d'activation (`EndPhaseOperation`)."""
        for e in self.entries.values():
            e.times_this_phase = 0
