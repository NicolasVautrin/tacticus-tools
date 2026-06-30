"""Messages = data + pattern Visiteur (RE, cf. docs/rl/runner-engine.md §1.2).

`IdunBattle.Messages.*Message` portent leurs données et un `Accept(visitor)` qui
route vers `visitor.visit_<type>(self)`. Les handlers (pre/post) sont des visiteurs
qui lancent des Operations.

⚠ STUB : seuls la base + les messages des premières tranches sont posés ; le
catalogue complet (`*Message$$Accept`) sera porté au fil des tranches.
"""
from __future__ import annotations

from typing import Optional, Tuple


class Message:
    """Base de tout message appliqué via `Runner.apply`."""
    __slots__ = ()

    @property
    def name(self) -> str:
        return type(self).__name__

    def accept(self, visitor) -> None:
        """Visiteur : route vers la méthode `visit_<ClassName>` du handler si elle
        existe (sinon no-op pour ce handler)."""
        fn = getattr(visitor, f"visit_{type(self).__name__}", None)
        if fn is not None:
            fn(self)


class MoveUnitMessage(Message):
    """`IdunBattle.Messages.MoveUnitMessage` (get_To @180ebef20). Tranche #24.
    `to` = position cible (col,row) ; `unit_id` = entité qui bouge."""
    __slots__ = ("unit_id", "to")

    def __init__(self, unit_id: int, to: Tuple[int, int]):
        self.unit_id = unit_id
        self.to = to


class AttackUnitMessage(Message):
    """Attaque dirigée (attaque normale) — `attacker_id` frappe `target_id`. Déclenche
    `AttackDamageOperation` (tirage de dégât par coup + réduction → mutation HP). Mirror
    simplifié de l'`ActiveAbilityMessage` (attaque normale) côté tranche DAMAGE."""
    __slots__ = ("attacker_id", "target_id")

    def __init__(self, attacker_id: int, target_id: int):
        self.attacker_id = attacker_id
        self.target_id = target_id


class ActiveAbilityMessage(Message):
    """`IdunBattle.Messages.ActiveAbilityMessage` (.ctor @180eb1560) — cast d'une ability ACTIVE.
    `caster_id` lance `ability_type` sur `target_id`. Déclenche l'exécution de la behaviour-seq de
    l'ability (mirror `AActiveAbility.Execute`→`<Ability>.ExecuteBehaviour`) : attaque + AddEffect +
    déplacements, etc. — l'engine DÉRIVE les effets posés (cf. `engine/runner/abilities/`)."""
    __slots__ = ("caster_id", "target_id", "ability_type")

    def __init__(self, caster_id: int, target_id: Optional[int], ability_type: int):
        self.caster_id = caster_id
        self.target_id = target_id
        self.ability_type = ability_type


class FinishUnitTurnMessage(Message):
    """`IdunBattle.Messages.FinishUnitTurnMessage` — clôt l'activation d'une unité."""
    __slots__ = ("unit_id",)

    def __init__(self, unit_id: Optional[int] = None):
        self.unit_id = unit_id


class EndTurnMessage(Message):
    """`IdunBattle.Messages.EndTurnMessage` (.ctor @180eb4c60, Accept @180eb4b30) — clôt le tour du
    JOUEUR courant (toute l'équipe). Déclenche `EndTurnOperation` (tick effets + cooldowns) puis, si
    `advance`, `ChangeTurnOperation` (flip vers le joueur suivant) + `StartTurnOperation` (vecteur début
    de tour). `advance=False` = fin de tour SANS changer de joueur (cas natif `param_2==0`)."""
    __slots__ = ("advance",)

    def __init__(self, advance: bool = True):
        self.advance = advance
