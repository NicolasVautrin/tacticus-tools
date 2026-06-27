"""Résolution OFFLINE de la magnitude d'un effet depuis gameconfig (Option A, doc §17.11).

= miroir de `ConfigAmount.Calculate` @180f171c0 SANS l'instance native : l'`AbilityConfiguration` d'un
effet n'étant qu'un **miroir live de gameconfig** indexé `key`+`level`, on lit gameconfig directement,
**indexé par le level capté de l'effet** (la dimension d'état qui distingue les instances) :
  • trait   → `gameconfig.trait(name).variables[var_key]`              (scalaire global)
  • ability → `gameconfig.ability(id).variables[var_key][level-1]`     (tableau per-niveau)
              | `.constants[var_key]`                                   (scalaire)
La clé gameconfig (`var_key`) = le nom camelCase de la clé `AbilityVariableType` native (l'enum
clé→nom étant absent du dump, on résout par nom, confirmé cas par cas — ex. RapidAssault key 0xf =
`rapidAssaultExtraDmgPct`=25). Import paresseux (gameconfig = source offline autorisée, cf. UnitContext).
"""
from __future__ import annotations


def trait_var(trait_name: str, var_key: str) -> int | None:
    """Variable de trait (`globalValues.traitVariables`) — scalaire global (pas de dimension niveau)."""
    try:
        import gameconfig as _GC
    except Exception:
        return None
    v = (_GC.trait(trait_name).get("variables") or {}).get(var_key)
    return int(v) if v is not None else None


def ability_var(ability_id: str, var_key: str, level: int | None = None,
                is_constant: bool = False, multiplier_pct: int = 100) -> int | None:
    """Variable/constante d'ability. Constante = scalaire ; variable = tableau per-niveau indexé `level`
    (1-based → idx level-1, clampé).

    `multiplier_pct` = `AbilityVariablesMultiplierPercentage` de l'unité (BC `Units[*]`, dérivé de la
    progression via `UnitConfigUtil.GetAbilityVariablesMultiplierPercentageForProgressionIndex`
    @181696230, défaut 100). Appliqué (RÈGLE GÉNÉRALE §17.21, config-driven) SEULEMENT aux variables
    listées dans `variablesAffectedByRarityBonus` (= BC `VariablesAffectedByUnitRarityMultiplier`) :
    `effective = round(base[level] × multiplier_pct/100)`. Le natif bake ce scaling dans la config
    par-unité au chargement de la BC ; on lit gameconfig (base) + applique le scaling offline.
    Vérifié u90 : PowerTrip.armorIgnored[L50]=277 × 180/100 = round(498.6) = 499 = pénétration live.
    Constantes (ex. extraHit) NON scalées (hors `variablesAffectedByRarityBonus`)."""
    try:
        import gameconfig as _GC
    except Exception:
        return None
    a = _GC.ability(ability_id) or {}
    if is_constant:
        v = (a.get("constants") or {}).get(var_key)
        return int(v) if v is not None else None
    arr = (a.get("variables") or {}).get(var_key)
    if arr is None:
        return None
    if isinstance(arr, list):
        if not arr:
            return None
        idx = (level - 1) if (level and level > 0) else 0
        idx = max(0, min(idx, len(arr) - 1))
        base = int(arr[idx])
    else:
        base = int(arr)
    # Scaling rareté/progression : seulement si la variable est flaggée affectée + multiplier ≠ 100.
    if multiplier_pct and multiplier_pct != 100 \
            and var_key in (a.get("variablesAffectedByRarityBonus") or []):
        return round(base * multiplier_pct / 100)
    return base
