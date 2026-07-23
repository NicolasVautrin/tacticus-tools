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
from .loki import (ThunderousAssaultAbility, ScarabHiveAbility,
                   ScarabSummonAbility, GetEmRuntzAbility, CrushingClawsAbility, ValkyrieStrikeAbility,
                   PlasmaGrenadeAbility, StikkbombAbility, FragstormAbility, ScythingTalonsAbility,
                   SpiritLeechAbility, ArmoriumCherubAbility, DoctrinaImperativesAbility,
                   MV71SniperDroneSquadAttackAbility, MasterOfTheTutelariesAbility, BlackRageAbility)
from .genestealer import CultDemagogueAbility, HeroicFusilladeAbility

# Registre ActiveAbilityType (int) -> classe d'ability portée. À ÉTENDRE au roster.
ABILITY_CLASSES: dict[int, type[ActiveAbility]] = {
    ThunderousAssaultAbility.ABILITY_TYPE: ThunderousAssaultAbility,   # 1043 (validé live)
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
    CultDemagogueAbility.ABILITY_TYPE: CultDemagogueAbility,           # 1179 (Isaak : pose decoys + summon Neophytes moitié + tour AI immédiat)
    HeroicFusilladeAbility.ABILITY_TYPE: HeroicFusilladeAbility,       # 1180 (Judh : move + 6x Projectile splash cible+voisins + crit-per-free-hex)
    DoctrinaImperativesAbility.ABILITY_TYPE: DoctrinaImperativesAbility,  # 1118 (Tan Gi'da : toggle Protector<->Conqueror ; Protector +FixedArmor self)
    MV71SniperDroneSquadAttackAbility.ABILITY_TYPE: MV71SniperDroneSquadAttackAbility,  # 1076 (Sho'syl : summon drone + attaque commandee + Markerlight, #61bis)
    MasterOfTheTutelariesAbility.ABILITY_TYPE: MasterOfTheTutelariesAbility,  # 1096 (Abraxas : effet 1197 + summon Pink Horror tile-target + Screamer sur Psychic, #202-C)
    BlackRageAbility.ABILITY_TYPE: BlackRageAbility,                   # 1163 (Lucien bloodDeathCompany : setHealth 30% + 3 self-buffs + charge + attaque normale, #217)
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
            # #139 : les FLAGS de tour sont poses par le natif pour TOUTE ability executee, independamment
            # de sa behaviour -> on les mirror MEME quand la behaviour n'est pas portee (turn-flow fidele).
            self.last["flags"] = self._add_flags_after_execution(msg)
            return                            # ability non portée → behaviour no-op (présent ≠ exécuté)
        ability = klass()
        diag = ability.execute_behaviour(self.state, msg.caster_id, msg.target_id) or {}
        self.last = {"ability_type": msg.ability_type, "ported": True,
                     "caster": msg.caster_id, "target": msg.target_id, **diag}
        self.last["flags"] = self._add_flags_after_execution(msg, ability)

    def _add_flags_after_execution(self, msg, ability=None) -> dict:
        """#139 — queue d'`ActiveAbilityOperation.ExecuteInternal` @180e44ec0 :
            skipEndTurn     = `GetSkipEndTurnFlag` @180e47120   = !ability.SetsEndTurnFlags().Evaluate(...)
            skipAbilityUsed = `GetSkipAbilityUsedFlag` @180e46f60 = !ability.SetsActiveAbilityUsedFlag(...)
            -> `AddFlagsAfterAbilityExecution` @180e447f0 (flag 2 + FinishUnitTurn -> flags 1+3).
        Les overrides `options.skip*Flag` du message natif (ActiveAbilityOptions+0x49/+0x4b, sous-abilities/
        derived) ne sont pas transportes par notre ActiveAbilityMessage offline -> defaut false (aucun skip
        force par le caller), fidele au cast top-level."""
        from ..operations.turnflow import add_flags_after_ability_execution
        from .base import sets_end_turn_flags_for, sets_active_ability_used_flag_for
        caster = int(msg.caster_id)
        if ability is not None:
            sets_end = ability.sets_end_turn_flags(self.state, caster)
            sets_used = ability.sets_active_ability_used_flag(self.state, caster)
        else:
            sets_end = sets_end_turn_flags_for(int(msg.ability_type), self.state, caster)
            sets_used = sets_active_ability_used_flag_for(int(msg.ability_type), self.state, caster)
        return add_flags_after_ability_execution(
            self.state, caster, skip_ability_used=not sets_used, skip_end_turn=not sets_end)
