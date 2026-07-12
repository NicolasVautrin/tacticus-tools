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
from .loki import (ThunderousAssaultAbility, GravitonRifleAbility, ScarabHiveAbility,
                   ScarabSummonAbility, GetEmRuntzAbility, CrushingClawsAbility, ValkyrieStrikeAbility,
                   PlasmaGrenadeAbility, StikkbombAbility, FragstormAbility, ScythingTalonsAbility,
                   SpiritLeechAbility, ArmoriumCherubAbility)

# Registre ActiveAbilityType (int) -> classe d'ability portée. À ÉTENDRE au roster.
ABILITY_CLASSES: dict[int, type[ActiveAbility]] = {
    ThunderousAssaultAbility.ABILITY_TYPE: ThunderousAssaultAbility,   # 1043 (validé live)
    GravitonRifleAbility.ABILITY_TYPE: GravitonRifleAbility,           # 1206 (pattern documenté)
    ScarabHiveAbility.ABILITY_TYPE: ScarabHiveAbility,                 # 1007 ScarabHive (summoner necroSpyder, validé live)
    ScarabSummonAbility.ABILITY_TYPE: ScarabSummonAbility,             # 1047 ScarabSummon (auto-dédoublement du scarab)
    GetEmRuntzAbility.ABILITY_TYPE: GetEmRuntzAbility,                 # 1045 GetEmRuntz (summoner orksRuntherd -> grots)
    CrushingClawsAbility.ABILITY_TYPE: CrushingClawsAbility,           # 1105 (Tyrant Guard : attaque+Taunt+Suppress+splash)
    ValkyrieStrikeAbility.ABILITY_TYPE: ValkyrieStrikeAbility,         # 1018 (airstrike différé — EXCLUT le sur-tir générique)
    PlasmaGrenadeAbility.ABILITY_TYPE: PlasmaGrenadeAbility,           # 1098 (splash Plasma adjacent-cible)
    StikkbombAbility.ABILITY_TYPE: StikkbombAbility,                   # 1051 (splash Blast adjacent-cible)
    FragstormAbility.ABILITY_TYPE: FragstormAbility,                   # 1078 (splash Blast pick-random <=4)
    ScythingTalonsAbility.ABILITY_TYPE: ScythingTalonsAbility,         # 1065 (splash Bio adjacent-both)
    SpiritLeechAbility.ABILITY_TYPE: SpiritLeechAbility,               # 1104 (Neurothrope : attaque Psychic config + Suppress ; lifesteal #94)
    ArmoriumCherubAbility.ABILITY_TYPE: ArmoriumCherubAbility,         # 1014 (Vindicta : 4x Flame ranged + feu + passif FireOfAbsolution)
}


class AbilityHandler:
    """Visiteur des `ActiveAbilityMessage` (mirror du handler natif lançant `AActiveAbility.Execute`)."""
    __slots__ = ("state", "last", "unported")

    def __init__(self, state: State):
        self.state = state
        self.last: Optional[dict] = None     # diagnostic du dernier cast
        # DURCISSEMENT HARNAIS (leçon SpiritLeech #93) : ActiveAbilityType tombés sur no-op (registry combat
        # incomplet) ACCUMULÉS ici — un cast d'ability non portée ne DEAL/POSE rien mais ne lève AUCUNE erreur.
        # Sans cette trace, la divergence est SILENCIEUSE (attribuée à tort au bruit). Le harnais replay-diff /
        # self-play doit LIRE `unported` (et un test qui FORCE une ability assert `last["ported"] is True`).
        self.unported: set[int] = set()

    def visit_ActiveAbilityMessage(self, msg) -> None:
        klass = ABILITY_CLASSES.get(int(msg.ability_type))
        if klass is None:
            self.unported.add(int(msg.ability_type))   # #93/#95 : rend le no-op VISIBLE (plus muet)
            self.last = {"ability_type": msg.ability_type, "ported": False}
            return                            # ability non portée → no-op (présent ≠ exécuté)
        diag = klass().execute_behaviour(self.state, msg.caster_id, msg.target_id) or {}
        self.last = {"ability_type": msg.ability_type, "ported": True,
                     "caster": msg.caster_id, "target": msg.target_id, **diag}
