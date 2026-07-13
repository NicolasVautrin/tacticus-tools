"""Système de stats natif porté offline — `IdunBattle.Entities.Components.{StatComponent,
ValueModification, ValueOverride, FillUpStatComponent}` + `UnitExtensions.GetStat`.

But (directive « porter GetStat offline et toutes ses dépendances ») : **calculer**
`GetStat = Initial + Σ(stat-modifications actives)`, clampé — au lieu de **figer** la valeur
Current captée (combatSnapshot). Rend le moteur autonome ET modifiable (patch d'un stat/mod au
bon endroit, comme le jeu). Mirror 1:1 (classe → homonyme natif, `# NomNatif @VA`).

Cf. `docs/rl/stat-system.md` (spec RE complète : layout, offsets, résolution, seeding).
"""
from __future__ import annotations

from enum import IntEnum
from typing import Dict, Optional


class StatType(IntEnum):
    """`StatType` natif — mirror COMPLET (dump.cs TypeDefIndex 24354 ; index du `switch` de
    `GetStatComponent @180ed20c0` / `GetStatOverride @180ed2800` + `STAT_IDS` du RPC combatSnapshot).
    Convention port = UPPER_CASE (le natif est PascalCase). #157 : complété 15/18-26 (avant : trous
    comblés par des constantes hex mortes STAT_EXTRA_* éparses, retirées)."""
    ATTACK = 0
    MOVEMENT = 1
    RANGE = 2              # [Obsolete] Idun Concept
    DEFENSE = 3
    ARMOR = 4             # [Obsolete] Idun Concept
    HEALTH = 5              # « fill-up » (FillUpStatComponent)
    SHIELD = 6            # [Obsolete] Old shield system
    BLOCK_CHANCE = 7
    BLOCK_DAMAGE = 8
    CRIT_CHANCE = 9
    CRIT_DAMAGE = 10
    UNUSED_1 = 11
    TURNS_STARTED = 12      # 0xc — compteur per-unit `UnitComponent.turnsStarted@+0x58` (incr. StartTurn) ;
                            # exposé via `UnitTurnsStartedFormula.Calculate @180f2d6c0` = `GetStat(unit,0xc)`.
                            # Base des hits Executioner (RoundsStarted). Capté par combatSnapshot (#122).
    PASSIVE_ABILITY_LEVEL = 13
    PASSIVE_ABILITY_VARIABLE_MULTIPLIER_PERCENTAGE = 14
    EVASION_CHANCE = 15   # [Obsolete] Idun Concept
    FIXED_ARMOR = 16        # 0x10
    EXTRA_HITS = 17         # 0x11
    ACTIVE_ABILITY_LEVEL = 18
    ACTIVE_ABILITY_VARIABLE_MULTIPLIER_PERCENTAGE = 19
    NUMBER_OF_MEMBERS = 20
    EXTRA_PIERCE_MELEE = 21    # 0x15
    EXTRA_PIERCE_RANGED = 22   # 0x16
    EXTRA_HITS_MELEE = 23      # 0x17
    EXTRA_RANGE = 24
    EXTRA_MAX_DAMAGE = 25
    EXTRA_PIERCE = 26          # 0x1a


class StatPart(IntEnum):
    """`StatPart` natif — mirror COMPLET (dump.cs TypeDefIndex 24355 ; `StatComponent.GetStatPart
    @180fa8bb0`). CURRENT=0 = résolu (Initial+Σmods) ; INITIAL=3 = base ; MODIFICATION=5 = total des
    mods ; OVERRIDE=7."""
    CURRENT = 0
    CURRENT_PCT = 1
    MAXIMUM = 2
    INITIAL = 3
    MISSING = 4
    MODIFICATION = 5
    RESET_MODIFICATION = 6
    OVERRIDE = 7
    REMOVE_OVERRIDE = 8
    MULTIPLIER_MODIFICATION = 9


class ValueModification:
    """`IdunBattle.Entities.Components.ValueModification` — modifications de stat **attribuées
    par source** (`Modify @180fadfc0` / `ReverseModification @180fae2d0` /
    `GetModificationFromEntity @180fadf10` / `get_Modifications @180fae5a0`).

    Layout natif : `total`(+0x0, int) = Σ sur les sources ; `per_source`(+0x8) =
    `Dict<sourceEntity, Modifier>`. Chaque source contribue une valeur ; `total` en est la somme.
    L'attribution par source rend une modification **droppable individuellement** (`reverse`) —
    c'est ce qui permet, offline, de retirer un buff conditionnel/expiré et recalculer Current
    sans lui.

    NB : la branche multiplicative native (`MultiplyModifier`, `isMult`/`multVal`) n'est pas
    portée — les modifications seedées depuis la capture sont des deltas additifs déjà résolus.
    """
    __slots__ = ("total", "per_source")

    def __init__(self, total: int = 0, per_source: Optional[Dict[object, int]] = None):
        self.total = int(total)
        self.per_source: Dict[object, int] = dict(per_source) if per_source else {}

    def modify(self, source: object, amount: int) -> None:
        """`ValueModification.Modify @180fadfc0` (branche additive) : SET la contribution de `source`
        à `amount` (nouvelle source → ajout ; existante → remplacement), `total = total - old + amount`.

        ISO natif : le natif garde `if (param_3 != 0)` ⇒ `Modify(*, 0)` est un **no-op** (retirer une
        source passe par `reverse_modification`, jamais par `Modify(*, 0)` ; confirmé
        `ReverseModification @180fae2d0`). La branche **MultiplyModifier** native (`isMult`/`multVal`,
        param_4/param_5) n'est PAS portée — additif seulement (couvre les stat-mods seedés + additifs)."""
        amount = int(amount)
        if amount == 0:                              # garde native `if (param_3 != 0)` -> no-op
            return
        old = self.per_source.get(source, 0)
        self.per_source[source] = amount
        self.total += amount - old

    def reverse_modification(self, source: object) -> None:
        """`ValueModification.ReverseModification @180fae2d0` : retire la contribution d'UNE source
        (`total -= sa value`)."""
        old = self.per_source.pop(source, 0)
        self.total -= old

    def get_modification_from_entity(self, source: object) -> int:
        """`ValueModification.GetModificationFromEntity @180fadf10` : contribution d'une source
        (0 si absente)."""
        return self.per_source.get(source, 0)


class ValueOverride:
    """`IdunBattle.Entities.Components.ValueOverride` — valeur d'override optionnelle + flag
    modifiable (`GetOverrideValueWithModification @180fae700`, `SetOverride @180faea70`,
    `RemoveOverride @180fae930`). `override = None` → pas d'override (cas normal)."""
    __slots__ = ("override", "is_modifiable")

    def __init__(self, override: Optional[int] = None, is_modifiable: bool = True):
        self.override = override
        self.is_modifiable = is_modifiable

    def has_value(self) -> bool:
        return self.override is not None

    def get_override_value_with_modification(self, mod_total: int) -> Optional[int]:
        """`ValueOverride.GetOverrideValueWithModification @180fae700` :
        `override + (isModifiable ? mod_total : 0)`, ou `None` si pas d'override."""
        if self.override is None:
            return None
        return int(self.override) + (int(mod_total) if self.is_modifiable else 0)


class StatComponent:
    """`IdunBattle.Entities.Components.StatComponent` — un stat résolu d'une unité.

    Layout natif : `+0x48`=Initial (base), `+0x10`=ValueModification (`modification`),
    `+0x20`=ValueOverride (`override`), clamp via virtuels GetMin/GetMaxValue (`+0x1b8/+0x1c8`).
    `get_current_value @180fa91d0` : `override ?? (Initial + modTotal)`, puis `GetClampedValue`.
    """
    __slots__ = ("initial", "modification", "override", "min_value", "max_value")

    def __init__(self, initial: int = 0, min_value: Optional[int] = 0,
                 max_value: Optional[int] = None,
                 modification: Optional[ValueModification] = None,
                 override: Optional[ValueOverride] = None):
        self.initial = int(initial)
        self.modification = modification if modification is not None else ValueModification()
        self.override = override if override is not None else ValueOverride()
        self.min_value = min_value
        self.max_value = max_value

    def get_clamped_value(self, raw: int) -> int:
        """`StatComponent.GetClampedValue @180fa8aa0` = `Min(max, Max(min, raw))` (min/max =
        virtuels par-stat ; la plupart min=0, max=+inf)."""
        v = int(raw)
        if self.min_value is not None:
            v = max(int(self.min_value), v)
        if self.max_value is not None:
            v = min(int(self.max_value), v)
        return v

    def get_current_value(self) -> int:
        """`StatComponent.get_CurrentValue @180fa91d0`."""
        mod = self.modification.total
        ovr = self.override.get_override_value_with_modification(mod)
        raw = ovr if ovr is not None else (self.initial + mod)
        return self.get_clamped_value(raw)

    def get_stat_part(self, part: int, source: object = None) -> int:
        """`StatComponent.GetStatPart @180fa8bb0`. Current(0/2)→CurrentValue ; Initial(3)→Initial ;
        5/9→total des modifications (ou contribution d'une `source` si fournie) ; 7→override ;
        4→0."""
        p = int(part)
        if p in (0, 2):
            return self.get_current_value()
        if p == 3:
            return self.initial
        if p in (5, 9):
            if source is not None:
                return self.modification.get_modification_from_entity(source)
            return self.modification.total
        if p == 7:
            return int(self.override.override or 0)
        if p == 4:
            return 0
        raise ValueError(f"StatPart {p} non implemente (StatComponent)")

    def modify(self, source: object, amount: int) -> None:
        """`ChangeStat` (apply, part 5/9) → `ValueModification.Modify @180fadfc0` : écrit `amount`
        (delta additif) attribué à `source` dans la modification du stat."""
        self.modification.modify(source, int(amount))

    def revert(self, source: object) -> None:
        """`ChangeStat` (revert, part 6) → `ValueModification.ReverseModification @180fae2d0` : retire
        la contribution de `source`."""
        self.modification.reverse_modification(source)


class FillUpStatComponent:
    """`IdunBattle.Entities.Components.FillUpStatComponent` — stat « qui se remplit » (Health=5,
    et l'index 4), layout distinct de `StatComponent` : `current`(+0x18), `maximum` via
    `get_CurrentMaximumValue`. `GetStatPart @180f9b3a0` : 0→current, 1→pourcentage
    (`round(max(0, current/max) * 100)`), 2→max, 4→max-current, 3→modTotal, 7→override.

    Pour la reproduction de la valeur Current (part 0), un `StatComponent` générique suffirait ;
    cette classe est fournie pour la fidélité des parts spécifiques (pourcentage, max)."""
    __slots__ = ("current", "maximum", "modification", "override")

    def __init__(self, current: int = 0, maximum: int = 0,
                 modification: Optional[ValueModification] = None,
                 override: Optional[ValueOverride] = None):
        self.current = int(current)
        self.maximum = int(maximum)
        self.modification = modification if modification is not None else ValueModification()
        self.override = override if override is not None else ValueOverride()

    def get_current_value(self) -> int:
        return self.current

    def get_stat_part(self, part: int, source: object = None) -> int:
        """`FillUpStatComponent.GetStatPart @180f9b3a0`."""
        p = int(part)
        if p in (0, 2) and p == 0:
            return self.current
        if p == 1:
            if self.maximum <= 0:
                return 0
            return round(max(0.0, self.current / self.maximum) * 100)
        if p == 2:
            return self.maximum
        if p == 4:
            return self.maximum - self.current
        if p == 3:
            return self.modification.total
        if p == 7:
            return int(self.override.override or 0)
        raise ValueError(f"StatPart {p} non implemente (FillUpStatComponent)")


class UnitStats:
    """Bloc de stats d'une unité : `StatType → composant`. `get_stat` = `UnitExtensions.GetStat
    @180ed30d0` (dispatch StatType → composant → `get_stat_part(part)`). Porté par `UnitContext`,
    partagé par la prédiction ET le runner."""
    __slots__ = ("components",)

    def __init__(self, components: Optional[Dict[int, object]] = None):
        # clé = int(StatType) ; valeur = StatComponent | FillUpStatComponent
        self.components: Dict[int, object] = dict(components) if components else {}

    def get_stat(self, stat_type: int, stat_part: int = StatPart.CURRENT,
                 source: object = None) -> int:
        """`UnitExtensions.GetStat @180ed30d0`. Renvoie 0 si le StatType n'a pas de composant
        (mirror du `default → return 0` natif)."""
        comp = self.components.get(int(stat_type))
        if comp is None:
            return 0
        return comp.get_stat_part(int(stat_part), source)

    def set_component(self, stat_type: int, component: object) -> None:
        self.components[int(stat_type)] = component

    def ensure_seeded(self, stat_type: int, initial: int) -> None:
        """Seede un `StatComponent(initial)` **identité** (ni delta ni modification) pour `stat_type`
        s'il est ABSENT. Idempotent : ne touche PAS un composant déjà seedé (garde son delta/attribution
        issu de `seed_unit_stats`). Sert à garantir que les 8 stats « de base » (`CORE_STAT_FIELDS`) sont
        toujours présentes — summon offline, ou gap `combatSnapshot` — pour que les propriétés
        `UnitContext.<stat>` (= `get_stat(Current)`) ne retombent jamais sur 0 faute de composant."""
        idx = int(stat_type)
        if idx not in self.components:
            self.components[idx] = StatComponent(
                initial=int(initial), min_value=0, max_value=STAT_CLAMP_MAX.get(idx))

    def change_stat(self, stat_type: int, source: object, amount: int) -> None:
        """`DSLFactory.ChangeStat` (Position(statType, part 5/9) = apply) : ajoute `amount` (delta
        additif) attribué à `source` dans la modification du StatType. Crée un `StatComponent(initial=0)`
        si absent (le natif suppose le composant présent ; offline on le tolère)."""
        idx = int(stat_type)
        comp = self.components.get(idx)
        if comp is None:
            comp = StatComponent(initial=0, min_value=0)
            self.components[idx] = comp
        comp.modification.modify(source, int(amount))

    def revert_stat(self, stat_type: int, source: object) -> None:
        """`DSLFactory.ChangeStat` (Position(statType, part 6) = revert) : retire la contribution de
        `source` sur le StatType."""
        comp = self.components.get(int(stat_type))
        if comp is not None:
            comp.modification.reverse_modification(source)

    def increment_base(self, stat_type: int, by: int = 1, base_if_absent: int = 0) -> None:
        """Incrémente la valeur de BASE (Initial) d'un stat-compteur BRUT. Mirror du bump inline de
        `StartTurnOperation.Execute @180ea3fb0` : `*(int*)(unitComp+0x58) += 1` par unité du joueur
        courant (compteur PER-UNIT `turnsStarted`, stat 12 = `GetStat(unit, 0xc)`). Le natif écrit le
        CHAMP BRUT du compteur (PAS une `ValueModification`) → on bump l'`initial` du `StatComponent`,
        pas sa modification. Seede un `StatComponent(base_if_absent)` si le stat est absent (summon frais /
        capture sans le stat → base 0). Réservé aux compteurs SANS stat-modification (le clamp par-stat
        s'applique à la lecture via `get_current_value`)."""
        idx = int(stat_type)
        comp = self.components.get(idx)
        if comp is None:
            comp = StatComponent(initial=int(base_if_absent), min_value=0,
                                 max_value=STAT_CLAMP_MAX.get(idx))
            self.components[idx] = comp
        if not isinstance(comp, StatComponent):
            raise TypeError(f"increment_base: stat {idx} n'est pas un StatComponent brut "
                            f"({type(comp).__name__})")
        comp.initial += int(by)


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Seeding depuis la capture live (combatSnapshot)
# ─────────────────────────────────────────────────────────────────────────────────────────────

# Source opaque pour la modification seedée depuis la capture (delta Current-Initial non encore
# attribué à un effet/setup connu). Quand une source réelle est portée (effet stat-mod ou
# ModifyUnit* setup), remplacer cette contribution par la contribution calculée.
CAPTURED_SOURCE = "captured"

# StatTypes « fill-up » (résolus par FillUpStatComponent côté natif).
_FILLUP_STATS = frozenset({4, 5})

# Plafonds par-stat (virtuel GetMaxValue) : les pourcentages BlockChance/CritChance sont clampés à 100
# par `GetClampedValue @180fa8aa0` (le reste = pas de plafond). Sert au clamp de `get_current_value`.
STAT_CLAMP_MAX = {7: 100, 9: 100}      # BlockChance / CritChance

# Les 8 StatTypes « de base » exposés comme propriétés lecture-seule de `UnitContext`
# (`ctx.attack` == `get_stat(ATTACK, Current)`, etc.) : nom de propriété -> StatType. Source unique
# de vérité pour le seeding — `UnitContext` (propriétés), `from_snapshot` (gap-fill via `ensure_seeded`)
# et `spawn.build_summon_context` (seed summon) s'y alignent. Le seeding systématique de ces 8 stats
# supprime tout stockage plat (plus de champ ni de fallback `_FLAT_FIELD`).
CORE_STAT_FIELDS = {
    "attack": StatType.ATTACK, "health": StatType.HEALTH,
    "block_chance": StatType.BLOCK_CHANCE, "block_damage": StatType.BLOCK_DAMAGE,
    "crit_chance": StatType.CRIT_CHANCE, "crit_damage": StatType.CRIT_DAMAGE,
    "fixed_armor": StatType.FIXED_ARMOR, "extra_hits": StatType.EXTRA_HITS,
}


def seed_unit_stats(stats: Dict[str, Optional[int]],
                    stat_delta: Optional[Dict[str, int]],
                    stat_ids: Dict[str, int],
                    attributed: "Optional[Dict[int, Dict[object, int]]]" = None) -> UnitStats:
    """Construit `UnitStats` depuis `combatSnapshot` d'une unité.

    `stats` = {nom→Current}, `stat_delta` = {nom→(Current-Initial)} (émis seulement ≠0),
    `stat_ids` = {nom→index StatType} (`STAT_IDS` du RPC). Pour chaque stat : `initial = Current - delta`.

    `attributed` (optionnel) = `{idxStatType: {source: amount}}` = contributions stat-mod DÉJÀ
    calculées par la couche effets (cf. `effects.stat_modifications_by_source`). Si fourni, on applique
    d'abord ces contributions **attribuées par source**, puis le **résidu** inexpliqué
    (`delta − Σ attribuées`) en source `CAPTURED_SOURCE`. Dans tous les cas `get_stat(Current)`
    **reproduit exactement** Current (zéro régression) ; mais la modification devient attribuée →
    `résidu == 0` quand les effets modélisés expliquent tout le delta = **validation non-circulaire**
    (Σ magnitudes config == delta natif). Sans `attributed`, tout le delta reste opaque (`CAPTURED_SOURCE`).

    Les stats « fill-up » (Health/4) sont seedées en `StatComponent` générique (part Current
    identique) ; le `FillUpStatComponent` spécifique (max/pourcentage) est posé au besoin (HP courant
    vit déjà dans `HealthComponent`)."""
    delta = stat_delta or {}
    attributed = attributed or {}
    us = UnitStats()
    for name, idx in (stat_ids or {}).items():
        cur = stats.get(name)
        if cur is None:
            continue
        idx = int(idx)
        d = int(delta.get(name, 0) or 0)
        comp = StatComponent(initial=int(cur) - d, min_value=0, max_value=STAT_CLAMP_MAX.get(idx))
        for src, amt in (attributed.get(idx) or {}).items():
            comp.modification.modify(src, int(amt))
        residual = d - comp.modification.total                    # part inexpliquée par les effets
        if residual != 0:
            comp.modification.modify(CAPTURED_SOURCE, residual)
        us.set_component(idx, comp)
    return us


def native_stat_parts(stats: Dict[str, Optional[int]],
                      stat_delta: Optional[Dict[str, int]],
                      stat_ids: Dict[str, int]) -> Dict[int, Dict[str, int]]:
    """Extrait, depuis un `combatSnapshot` d'unité (= oracle natif, `UnitExtensions.GetStat` par
    stat), les 3 parts par StatType : `current`(=stats[k]), `initial`(=stats[k]-delta[k]),
    `modification`(=delta[k]). Renvoie `{idxStatType: {current, initial, modification, name}}`."""
    delta = stat_delta or {}
    out: Dict[int, Dict[str, int]] = {}
    for name, idx in (stat_ids or {}).items():
        cur = stats.get(name)
        if cur is None:
            continue
        d = int(delta.get(name, 0) or 0)
        out[int(idx)] = {"current": int(cur), "initial": int(cur) - d,
                         "modification": d, "name": name}
    return out


def compare_unit_stats(unit_stats: "UnitStats", stats: Dict[str, Optional[int]],
                       stat_delta: Optional[Dict[str, int]],
                       stat_ids: Dict[str, int]) -> list:
    """Confronte `unit_stats.get_stat` (offline) à l'oracle natif (`combatSnapshot`) pour une
    unité, sur les parts Current(0)/Initial(3)/modification(5). Renvoie la liste des écarts
    (chaînes lisibles ; vide = agrément).

    C'est la primitive « comparer offline↔natif À TOUT MOMENT » demandée : `combatSnapshot` relit
    le natif `GetStat` à chaque appel, donc on peut la ré-appeler sur un état ÉVOLUÉ (après une
    mutation offline + la même mutation live) → confrontation **non-circulaire** de la STAT
    calculée offline vs recalculée par le jeu. Sur un état fraîchement seedé depuis la capture,
    l'égalité tient par construction (garde-fou wiring/index/arithmétique/clamp du port)."""
    native = native_stat_parts(stats, stat_delta, stat_ids)
    out = []
    for idx, exp in native.items():
        got = {
            "current": unit_stats.get_stat(idx, StatPart.CURRENT),
            "initial": unit_stats.get_stat(idx, StatPart.INITIAL),
            "modification": unit_stats.get_stat(idx, StatPart.MODIFICATION),
        }
        for part in ("current", "initial", "modification"):
            if got[part] != exp[part]:
                out.append(f"{exp['name']}(idx {idx}).{part}: offline {got[part]} "
                           f"!= native {exp[part]}")
    return out
