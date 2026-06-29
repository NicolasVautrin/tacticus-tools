"""Registre d'abilities + handler (visiteur) du `ActiveAbilityMessage`.

`AbilityHandler` route un `ActiveAbilityMessage` vers la classe d'ability correspondante
(`ABILITY_CLASSES[ability_type]`) et exécute sa behaviour-seq (mirror `AActiveAbility.Execute` →
`<Ability>.ExecuteBehaviour`). C'est le point d'entrée du wiring : `Runner.apply(ActiveAbilityMessage)`
→ l'engine DÉRIVE les effets/mutations de l'ability. Ability non portée → no-op (dégradation fidèle,
comme un effet non porté = BaseEffect).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from .base import ActiveAbility
from .loki import ThunderousAssaultAbility, GravitonRifleAbility

# Registre ActiveAbilityType (int) -> classe d'ability portée. À ÉTENDRE au roster.
ABILITY_CLASSES: dict[int, type[ActiveAbility]] = {
    ThunderousAssaultAbility.ABILITY_TYPE: ThunderousAssaultAbility,   # 1043 (validé live)
    GravitonRifleAbility.ABILITY_TYPE: GravitonRifleAbility,           # 1206 (pattern documenté)
}


class AbilityHandler:
    """Visiteur des `ActiveAbilityMessage` (mirror du handler natif lançant `AActiveAbility.Execute`)."""
    __slots__ = ("state", "last")

    def __init__(self, state: State):
        self.state = state
        self.last: Optional[dict] = None     # diagnostic du dernier cast

    def visit_ActiveAbilityMessage(self, msg) -> None:
        klass = ABILITY_CLASSES.get(int(msg.ability_type))
        if klass is None:
            self.last = {"ability_type": msg.ability_type, "ported": False}
            return                            # ability non portée → no-op (présent ≠ exécuté)
        diag = klass().execute_behaviour(self.state, msg.caster_id, msg.target_id) or {}
        self.last = {"ability_type": msg.ability_type, "ported": True,
                     "caster": msg.caster_id, "target": msg.target_id, **diag}
