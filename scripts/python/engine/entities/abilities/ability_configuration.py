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
    rarity_affected: frozenset = frozenset()   # _variablesAffectedByRarityBonus (natif this+0x28)

    @classmethod
    def from_gameconfig(cls, name: str, cfg: dict | None) -> "AbilityConfiguration | None":
        if not cfg:
            return None
        return cls(name=name, variables=cfg.get("variables") or {},
                   constants=cfg.get("constants") or {},
                   rarity_affected=frozenset(cfg.get("variablesAffectedByRarityBonus") or ()))

    def get_variable_for_level(self, var_name: str, level: int,
                               fallback_to_default: int = 0,
                               multiplier: int | None = None) -> int:
        """AbilityConfiguration.GetVariableForLevel (@181576fb0) : variable au niveau `level`,
        sinon constante, sinon `fallback_to_default`. INDEXATION 1-BASED : le natif
        (`TryGetVariableArrayForLevel @181577510`) convertit via `Idun.Shared.Level.ToZeroBasedIndex`
        = **level − 1**, clampé [0, len−1] — cohérent avec `ability_var` (magnitude.py) et les
        ancres bit-exactes (PowerTrip armorIgnored L50=277→499, FR dmgReduction L65=582,
        PlasmaCannon minDmg L50=665 → sh_min natif 2873). L'ancien index direct = off-by-one.

        `multiplier` = AbilityState.VariableMultiplierPercentage (per-ability, capteur #100) :
        le natif scale CHAQUE entrée DANS TryGetVariableArrayForLevel @181577510 —
        `Fix64.Round(v × mult/100)` (round, PAS floor : 886×1.8 = 1594.8 → 1595, validé
        varLevelDumps) — SSI `var_name ∈ _variablesAffectedByRarityBonus` (this+0x28).
        None = pas de scaling (comportement historique des call-sites qui scalent eux-mêmes)."""
        arr = self.variables.get(var_name)
        v = None
        if arr:
            i = max(0, min(level - 1, len(arr) - 1))
            try:
                v = int(arr[i])
            except (TypeError, ValueError):
                return fallback_to_default
        elif var_name in self.constants:
            try:
                v = int(self.constants[var_name])
            except (TypeError, ValueError):
                return fallback_to_default
        if v is None:
            return fallback_to_default
        if multiplier is not None and multiplier != 100 and var_name in self.rarity_affected:
            v = round(v * multiplier / 100)   # Fix64.Round (half-even, comme round() Python)
        return v

    def has_variable(self, var_name: str) -> bool:
        return var_name in self.variables or var_name in self.constants
