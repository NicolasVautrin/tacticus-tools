"""ScarabSummonPlaybook — auto-dedoublement NonComparable (spawn ring-1)."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class ScarabSummonPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.ScarabSummonPlaybook$$EvaluateNonComparable` (auto-DÉDOUBLEMENT du scarab, id 0x417=1047).
    Pour CHAQUE cible éligible (`GetEligibleTargetsSelectable(MainTile(caster))` = tuiles de spawn ring-1
    libres adjacentes à SOI), `GenerateAction` à utilité CONSTANTE `Fix64.FromIntFraction(3,2)=1.5`.
    IdunBattle.AI.Playbook.Loki.ScarabSummonPlaybook$$.cctor : MIN_UTILITY=1 (`Fix64.FromInt(1)`). IdunBattle.AI.Playbook.Loki.ScarabSummonPlaybook$$.ctor : `NonComparablePlaybook(0x417)`
    SANS priorité -> get_Priority=**0** (défaut). Le caster NE bouge PAS (spawn adjacent à soi, pas de move).

    GAP : `IdunBattle.AI.Playbook.Loki.ScarabSummonPlaybook$$GetUseProbability` (1.0 ou 1/2 selon un compteur runtime = `chance:50` gameconfig) =
    gate RNG NON modélisé offline -> le port décide TOUJOURS de se dédoubler dès qu'une tuile ring-1 est
    libre (le natif ~50%). Idem cap de duplication (`UnitDuplicationLimitSelector`) non porté."""
    ABILITY_ID = int(ActiveAbilityType.ScarabSummon)  # 1047
    MIN_UTILITY = 1.0
    _UTILITY = 1.5   # Fix64.FromIntFraction(3,2) — CONSTANTE par cible éligible

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        # GetEligibleTargetsSelectable = tuiles de spawn ring-1 libres (kind="tile" via ability_targets offline).
        if ctx.ability_targets is None or self._UTILITY < self.MIN_UTILITY:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        has_tile = any(
            t.get("kind") == "tile"
            for u in (at.get("units") or [])
            for a in (u.get("abilities") or [])
            if a.get("abilityId") == self.ABILITY_ID
            for t in (a.get("targets") or []))
        if not has_tile:
            return []                                  # aucune tuile ring-1 libre -> pas de dédoublement
        # Utilité CONSTANTE 1.5 ; caster ne bouge pas (to=None) ; target=None (spawn adjacent-soi au runtime).
        return [{"target": None, "ability": self.ABILITY_ID, "to": None, "pred": self._UTILITY}]
