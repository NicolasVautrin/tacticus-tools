"""Port FIDÈLE de `IdunBattle.Configuration.AbilityConfiguration` (gqfc5mff6c).

Le natif lit les variables d'ability via `GetVariableForLevel(AbilityVariableType, level)` depuis
un registre `BattleQuery@0x48 = Dict<ActiveAbilityType, AbilityConfiguration>` (RE @18105a530).
Ce registre EST le contenu de `gameconfig-abilities.json` (le dump offline des mêmes configs) —
donc on source la config offline depuis gameconfig (autorisé : config d'arme), structure identique.

`AbilityVariableType` (dump.cs @865192) : les variables par-niveau (minDmg=12, maxDmg=13, …) sont
sous `variables[<nom>][niveau]` ; les constantes (nrOfHits=47, damageProfile, …) sous `constants`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AbilityConfiguration:
    """Config d'une ability (wrappe l'entrée gameconfig-abilities `AbilityConfigDto`)."""
    name: str
    variables: dict        # nom -> liste par niveau (str/int)
    constants: dict        # nom -> valeur

    @classmethod
    def from_gameconfig(cls, name: str, cfg: dict | None) -> "AbilityConfiguration | None":
        if not cfg:
            return None
        return cls(name=name, variables=cfg.get("variables") or {},
                   constants=cfg.get("constants") or {})

    def get_variable_for_level(self, var_name: str, level: int,
                               fallback_to_default: int = 0) -> int:
        """AbilityConfiguration.GetVariableForLevel (@181576fb0) : variable au niveau `level`
        (clamp aux bornes du tableau), sinon constante, sinon `fallback_to_default`."""
        arr = self.variables.get(var_name)
        if arr:
            i = max(0, min(level, len(arr) - 1))
            try:
                return int(arr[i])
            except (TypeError, ValueError):
                return fallback_to_default
        if var_name in self.constants:
            try:
                return int(self.constants[var_name])
            except (TypeError, ValueError):
                return fallback_to_default
        return fallback_to_default

    def has_variable(self, var_name: str) -> bool:
        return var_name in self.variables or var_name in self.constants
