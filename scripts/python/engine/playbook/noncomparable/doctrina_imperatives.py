"""DoctrinaImperativesPlaybook — decision NonComparable self-cast (Tan Gi'da, toggle Protector/Conqueror)."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first


class DoctrinaImperativesPlaybook(NonComparablePlaybook):
    """`DoctrinaImperativesPlaybook` (RE @18112ccf0, ctor `NonComparablePlaybook(0x45e=1118)`).

    - cctor @18112cc80 : `MIN_UTILITY = Fix64.FromInt(1)` (gate Bucket.AddAction).
    - `GetUseProbability @18112cbf0` : `Fix64(1)` (100%) si `HasUsedAbilityThisTurn == false`, sinon `Fix64(0)`
      -> l'IA n'active DoctrinaImperatives qu'UNE fois par tour (le once-per-turn est reflete cote driver par
      `usable is False` une fois utilise, comme les autres actives -- non re-modelise ici).
    - `EvaluateNonComparable @18112c8d0` : bucket base=MIN_UTILITY(1) sur les cibles d'attaque normale ;
      `GenerateAction(..., Fix64.FromInt(100))` -> **utilite finale = 100**. L'IA ne CHOISIT pas d'Imperative
      (le toggle est deterministe cote behaviour) : elle score l'usage a 100 des que disponible.

    SELF-cast (comme NovaBoost/heals #76/#80) : la cible = self, position-independante -> le generateur
    `<GenerateActions>d__7` gate les tuiles de move par `HasValidTargets` (self position-independant -> aucune
    tuile motivee) et garde le 1er ajoute (NullPosition = cast EN PLACE) -> le natif RESTE EN PLACE
    (`_sweep_origin_first` -> to=None)."""
    ABILITY_ID = int(ActiveAbilityType.DoctrinaImperatives)   # 1118
    MIN_UTILITY = 1.0
    PRIORITY = 0          # get_Priority de base NonComparable (aucun override lu)
    UTILITY = 100.0       # GenerateAction(..., Fix64.FromInt(100)) @18112c8d0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if not self._usable(ctx):
            return []
        to = next(iter(_sweep_origin_first(ctx)), None)
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,
                 "to": (to if to != ctx.origin else None), "pred": self.UTILITY}]

    def _usable(self, ctx: NCContext) -> bool:
        """Ability disponible pour le caster ? Le driver filtre deja `usable is False` (encode le
        `GetUseProbability`=0 apres usage / once-per-turn) ; permissif si `ability_targets` indispo."""
        if ctx.ability_targets is None:
            return True
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == self.ABILITY_ID:
                    return bool(a.get("targets") or a.get("usable", True))
        return True
