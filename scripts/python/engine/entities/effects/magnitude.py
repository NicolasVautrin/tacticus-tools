"""Résolution OFFLINE de la magnitude d'un effet depuis gameconfig (Option A, doc §17.11).

= miroir de `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate SANS l'instance native : l'`AbilityConfiguration` d'un
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


def global_value(key: str) -> int | None:
    """Scalaire global de combat (`clientGameConfig.globalValues[key]`) — magnitude d'effets
    non rattachés à une ability d'unité (ex. `lightCoverHitReduction`=2 pour LightCoverAbility,
    ability de TUILE absente de `units.abilities`)."""
    try:
        import gameconfig as _GC
    except Exception:
        return None
    v = _GC.global_value(key)
    return int(v) if v is not None else None


_BC_EFFECT_CFG: dict | None = None


def bc_effect_config(key: str, default: int | None = None) -> int | None:
    """Entrée NOMMÉE de la section `Effect` de la BattleConfiguration — la table que
    `IdunBattleLogic.Entities.DSLFactory$$EffectConfig` (-> `EffectConfigAmount`) et `IdunBattle.Core.Services.BattleQuery$$GetEffectConfig` (Dict peuplé par `IdunBattle.Core.Services.BattleQuery$$InitEffectConfig`) indexent par enum. Source unique =
    `weights.DEFAULT_BC` (même pattern que `CONTAMINATED_ARMOR_REDUCTION_PCT`, effect_triggers.py).
    Ex. `StunnedDmgReductionPct`=50 (EffectConfig(2), Stunned_DamageModifierEffect IdunBattle.Entities.Effects.Loki.Stunned_DamageModifierEffect$$CreateEffectDamageMalusForDefense),
    `PinnedDmgReductionPct`=30, `IceCritDmgBonusPct`=25. Cache module (BC statique par bataille)."""
    global _BC_EFFECT_CFG
    if _BC_EFFECT_CFG is None:
        try:
            import json as _json
            from ... import weights as _weights
            _BC_EFFECT_CFG = (_json.loads(_weights.DEFAULT_BC.read_text(encoding="utf-8"))
                              .get("Effect", {}) if _weights.DEFAULT_BC.exists() else {})
        except Exception:
            _BC_EFFECT_CFG = {}
    v = _BC_EFFECT_CFG.get(key, default)
    return int(v) if v is not None else None


def _lookup_config_key(table: dict, key: str):
    """Resolution d'une cle de `constants`/`variables` du gameconfig, avec repli TRIMME.

    POURQUOI : le natif n'indexe PAS ces tables par CHAINE. `IdunBattle.Configuration.
    AbilityConfiguration$$GetStringConstant` fait un `Dictionary<AbilityConstantType, string>.
    TryGetValue` -- la conversion `chaine du gameconfig -> membre d'enum` a lieu AU CHARGEMENT, et
    `Enum.Parse` **TRIM les blancs**. Une cle a espace parasite est donc INVISIBLE cote natif ; cote
    port, qui lit le JSON par nom, elle rate silencieusement (`None`).

    MESURE (2026-08-01, gameconfig `rnca9r7q6c`, 572 abilities) : **6** cles concernees --
    `GrapnelLauncher."knockbackRange "`, `ReanimationBeam."initialCooldownTurns "` /
    `."munitionsCost "`, `DeathOnTheWind` (les deux memes), et la VARIABLE
    `HarbingerOfDestruction."nrOfUnits "`.

    Le repli n'est tente QUE si la cle exacte est absente (aucun changement pour les 566 autres), et
    il exige une correspondance UNIQUE apres `strip()` -- une ambiguite rend `None` plutot que de
    choisir. `GetStringConstant` LEVE sur cle absente ; le port, lui, se degrade en `None` (le
    contrat de tous ses appelants)."""
    if key in table:
        return table[key]
    k = key.strip()
    hits = [v for kk, v in table.items() if kk.strip() == k]
    return hits[0] if len(hits) == 1 else None


def ability_var_array(ability_id: str, var_key: str, level: int | None = None,
                      multiplier_pct: int = 100) -> list[int] | None:
    """`IdunBattle.Configuration.AbilityConfiguration$$GetVariableArrayForLevel(type, abilityState,
    fallback)` -- la variante VECTORIELLE d'`ability_var` ci-dessous, pour les variables dont UNE
    cellule de niveau porte PLUSIEURS valeurs.

    Le natif rend un `int[]` (le call-site lit sa longueur en `+0x18` et ses elements a partir de
    `+0x20`) ; le gameconfig, lui, encode cette cellule comme une chaine SEPAREE PAR DES VIRGULES --
    ex. `Loki_SwoopingHawk.dmg[16] == "164,128,91"` = les degats des 3 tuiles de la vague. Passer une
    telle cellule a `ability_var` leve (`int("164,128,91")`), d'ou cet accesseur distinct plutot
    qu'un elargissement silencieux du scalaire.

    MEME indexation 1-based que le scalaire (`Idun.Shared.Level$$ToZeroBasedIndex` = `level - 1`,
    clampe `[0, len-1]`) et MEME regle de scaling : le natif applique
    `Fix64.Round(v x mult/100)` **a CHAQUE entree du tableau**, et seulement si la variable est
    listee dans `variablesAffectedByRarityBonus` (`AbilityConfiguration+0x28`) -- ce qui est le cas
    de `dmg`. Une cellule mono-valeur rend une liste d'un element (aucun cas particulier).

    Retour `None` (jamais `[]`) quand la variable est absente ou illisible : c'est le contrat de
    tous les appelants du module, et il distingue « pas de config » de « tableau vide »."""
    try:
        import gameconfig as _GC
    except Exception:
        return None
    a = _GC.ability(ability_id) or {}
    arr = _lookup_config_key(a.get("variables") or {}, var_key)
    if arr is None:
        return None
    cell = arr
    if isinstance(arr, list):
        if not arr:
            return None
        idx = (level - 1) if (level and level > 0) else 0     # ToZeroBasedIndex, clampe
        cell = arr[max(0, min(idx, len(arr) - 1))]
    try:
        vals = [int(tok) for tok in str(cell).split(",") if str(tok).strip() != ""]
    except (TypeError, ValueError):
        return None
    if not vals:
        return None
    if multiplier_pct and multiplier_pct != 100 \
            and var_key in (a.get("variablesAffectedByRarityBonus") or []):
        return [round(v * multiplier_pct / 100) for v in vals]   # scaling PAR ENTREE, comme le natif
    return vals


def ability_var(ability_id: str, var_key: str, level: int | None = None,
                is_constant: bool = False, multiplier_pct: int = 100) -> int | None:
    """Variable/constante d'ability. Constante = scalaire ; variable = tableau per-niveau indexé `level`
    (1-based → idx level-1, clampé).

    `multiplier_pct` = `AbilityVariablesMultiplierPercentage` de l'unité (BC `Units[*]`, dérivé de la
    progression via `IdunMetaLogic.UserProgress.UnitConfigUtil$$GetAbilityVariablesMultiplierPercentageForProgressionIndex, défaut 100). Appliqué (RÈGLE GÉNÉRALE §17.21, config-driven) SEULEMENT aux variables
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
        v = _lookup_config_key(a.get("constants") or {}, var_key)
        # ⚠ Axe NUMERIQUE : une constante de type CHAINE (`affectedUnitId`, `affectedUnitIds`...)
        # leve `ValueError` ici, et c'est VOULU -- `ability_const_str` est l'accesseur a utiliser.
        # Le natif a lui aussi DEUX foyers distincts (`IdunBattle.Configuration.
        # AbilityConfiguration$$GetNumberConstant` / `$$GetStringConstant`), lus par DEUX noeuds DSL
        # distincts (`IdunBattleLogic.Entities.DSLFormulas$$ConfigConst` / `$$ConfigConstString`).
        return int(v) if v is not None else None
    arr = _lookup_config_key(a.get("variables") or {}, var_key)
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


def ability_const_str(ability_id: str, const_key: str) -> "str | None":
    """Constante d'ability de type CHAINE -- l'axe que `ability_var` ne couvre PAS.

    Mirror d'`IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant`, le foyer que le
    noeud `IdunBattleLogic.Entities.DSLFormulas$$ConfigConstString` appelle (a distinguer de
    `$$ConfigConst`, qui passe par `$$GetNumberConstant` -- deux methodes natives DIFFERENTES,
    deux noeuds DSL DIFFERENTS).

    ⚠ **AUCUN niveau, AUCUN multiplicateur** : une constante n'est pas indexee par palier, et le
    scaling de rarete ne s'applique qu'aux `variables` listees dans `variablesAffectedByRarityBonus`.
    Premier consommateur : `BookOfFate` (`affectedUnitId = "thousSmnDaemonPrince"`, #1008) -- avant
    lui, appeler `ability_var(..., is_constant=True)` sur une constante-chaine levait un
    `ValueError` au lieu de rendre la chaine (trouve par le test offline de la tranche)."""
    try:
        import gameconfig as _GC
    except Exception:
        return None
    a = _GC.ability(ability_id) or {}
    v = _lookup_config_key(a.get("constants") or {}, const_key)
    return None if v is None else str(v)
