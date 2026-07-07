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
from .loki import (ThunderousAssaultAbility, GravitonRifleAbility, ScarabSummonAbility,
                   CrushingClawsAbility, ValkyrieStrikeAbility, PlasmaGrenadeAbility,
                   StikkbombAbility, FragstormAbility, ScythingTalonsAbility)

# Registre ActiveAbilityType (int) -> classe d'ability portée. À ÉTENDRE au roster.
ABILITY_CLASSES: dict[int, type[ActiveAbility]] = {
    ThunderousAssaultAbility.ABILITY_TYPE: ThunderousAssaultAbility,   # 1043 (validé live)
    GravitonRifleAbility.ABILITY_TYPE: GravitonRifleAbility,           # 1206 (pattern documenté)
    ScarabSummonAbility.ABILITY_TYPE: ScarabSummonAbility,             # 1007 ScarabHive (summon, validé live)
    CrushingClawsAbility.ABILITY_TYPE: CrushingClawsAbility,           # 1105 (Tyrant Guard : attaque+Taunt+Suppress+splash)
    ValkyrieStrikeAbility.ABILITY_TYPE: ValkyrieStrikeAbility,         # 1018 (airstrike différé — EXCLUT le sur-tir générique)
    PlasmaGrenadeAbility.ABILITY_TYPE: PlasmaGrenadeAbility,           # 1098 (splash Plasma adjacent-cible)
    StikkbombAbility.ABILITY_TYPE: StikkbombAbility,                   # 1051 (splash Blast adjacent-cible)
    FragstormAbility.ABILITY_TYPE: FragstormAbility,                   # 1078 (splash Blast pick-random <=4)
    ScythingTalonsAbility.ABILITY_TYPE: ScythingTalonsAbility,         # 1065 (splash Bio adjacent-both)
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
