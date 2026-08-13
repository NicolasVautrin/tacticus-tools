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
    `IdunBattle.Entities.UnitExtensions$$GetStatComponent` / `IdunBattle.Entities.UnitExtensions$$GetStatOverride` + `STAT_IDS` du RPC combatSnapshot).
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
                            # exposé via `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate` = `GetStat(unit,0xc)`.
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
    """`StatPart` natif — mirror COMPLET (dump.cs TypeDefIndex 24355 ; `IdunBattle.Entities.Components.StatComponent$$GetStatPart`). CURRENT=0 = résolu (Initial+Σmods) ; INITIAL=3 = base ; MODIFICATION=5 = total des
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
    par source** (`IdunBattle.Entities.Components.ValueModification$$Modify` / `IdunBattle.Entities.Components.ValueModification$$ReverseModification` /
    `IdunBattle.Entities.Components.ValueModification$$GetModificationFromEntity` / `IdunBattle.Entities.Components.ValueModification$$get_Modifications`).

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
        """`IdunBattle.Entities.Components.ValueModification$$Modify` (branche additive) : SET la contribution de `source`
        à `amount` (nouvelle source → ajout ; existante → remplacement), `total = total - old + amount`.

        ISO natif : le natif garde `if (param_3 != 0)` ⇒ `Modify(*, 0)` est un **no-op** (retirer une
        source passe par `reverse_modification`, jamais par `Modify(*, 0)` ; confirmé
        `IdunBattle.Entities.Components.ValueModification$$ReverseModification`). La branche **MultiplyModifier** native (`isMult`/`multVal`,
        param_4/param_5) n'est PAS portée — additif seulement (couvre les stat-mods seedés + additifs)."""
        amount = int(amount)
        if amount == 0:                              # garde native `if (param_3 != 0)` -> no-op
            return
        old = self.per_source.get(source, 0)
        self.per_source[source] = amount
        self.total += amount - old

    def reverse_modification(self, source: object) -> None:
        """`IdunBattle.Entities.Components.ValueModification$$ReverseModification` : retire la contribution d'UNE source
        (`total -= sa value`)."""
        old = self.per_source.pop(source, 0)
        self.total -= old

    def get_modification_from_entity(self, source: object) -> int:
        """`IdunBattle.Entities.Components.ValueModification$$GetModificationFromEntity` : contribution d'une source
        (0 si absente)."""
        return self.per_source.get(source, 0)


class ValueOverride:
    """`IdunBattle.Entities.Components.ValueOverride` — valeur d'override optionnelle + flag
    modifiable (`IdunBattle.Entities.Components.ValueOverride$$GetOverrideValueWithModification`, `IdunBattle.Entities.Components.ValueOverride$$SetOverride`,
    `IdunBattle.Entities.Components.ValueOverride$$RemoveOverride`). `override = None` → pas d'override (cas normal)."""
    __slots__ = ("override", "is_modifiable")

    def __init__(self, override: Optional[int] = None, is_modifiable: bool = True):
        self.override = override
        self.is_modifiable = is_modifiable

    def has_value(self) -> bool:
        return self.override is not None

    def get_override_value_with_modification(self, mod_total: int) -> Optional[int]:
        """`IdunBattle.Entities.Components.ValueOverride$$GetOverrideValueWithModification` :
        `override + (isModifiable ? mod_total : 0)`, ou `None` si pas d'override."""
        if self.override is None:
            return None
        return int(self.override) + (int(mod_total) if self.is_modifiable else 0)


class StatComponent:
    """`IdunBattle.Entities.Components.StatComponent` — un stat résolu d'une unité.

    Layout natif : `+0x48`=Initial (base), `+0x10`=ValueModification (`modification`),
    `+0x20`=ValueOverride (`override`), clamp via virtuels GetMin/GetMaxValue (`+0x1b8/+0x1c8`).
    `get_current_value IdunBattle.Entities.Components.StatComponent$$get_CurrentValue` : `override ?? (Initial + modTotal)`, puis `GetClampedValue`.
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
        """`IdunBattle.Entities.Components.StatComponent$$GetClampedValue` = `Min(max, Max(min, raw))` (min/max =
        virtuels par-stat ; la plupart min=0, max=+inf)."""
        v = int(raw)
        if self.min_value is not None:
            v = max(int(self.min_value), v)
        if self.max_value is not None:
            v = min(int(self.max_value), v)
        return v

    def get_current_value(self) -> int:
        """`IdunBattle.Entities.Components.StatComponent$$get_CurrentValue`."""
        mod = self.modification.total
        ovr = self.override.get_override_value_with_modification(mod)
        raw = ovr if ovr is not None else (self.initial + mod)
        return self.get_clamped_value(raw)

    def get_stat_part(self, part: int, source: object = None) -> int:
        """`IdunBattle.Entities.Components.StatComponent$$GetStatPart`. Current(0/2)→CurrentValue ; Initial(3)→Initial ;
        5/9→total des modifications (ou contribution d'une `source` si fournie) ; 7→override ;
        4→0."""
        p = int(part)
        if p in (0, 2):
            return self.get_current_value()
        if p == 3:
            return self.initial
        # #270-r1-r1 : le tuple porte des `StatPart` (mirror STRICT, verbatim du build) --
        # `5 = Modification`, `9 = MultiplierModification`. #270-r4 : les deux comparaisons
        # voisines (role COMPARAISON) sont nommees de meme -- `p` EST un `StatPart`, le nom
        # du parametre le dit et les branches deja nommees le confirment.
        if p in (StatPart.MODIFICATION, StatPart.MULTIPLIER_MODIFICATION):
            if source is not None:
                return self.modification.get_modification_from_entity(source)
            return self.modification.total
        if p == StatPart.OVERRIDE:                 # 7
            return int(self.override.override or 0)
        if p == StatPart.MISSING:                  # 4 -- pas de « manquant » sur un stat simple
            return 0
        raise ValueError(f"StatPart {p} non implemente (StatComponent)")

    def modify(self, source: object, amount: int) -> None:
        """`ChangeStat` (apply, part 5/9) → `IdunBattle.Entities.Components.ValueModification$$Modify` : écrit `amount`
        (delta additif) attribué à `source` dans la modification du stat."""
        self.modification.modify(source, int(amount))

    def revert(self, source: object) -> None:
        """`ChangeStat` (revert, part 6) → `IdunBattle.Entities.Components.ValueModification$$ReverseModification` : retire
        la contribution de `source`."""
        self.modification.reverse_modification(source)

    def apply_override(self, value: int, is_modifiable: bool = True) -> None:
        """`IdunBattle.Entities.Components.StatComponent$$ApplyModifier` part **7 = OVERRIDE** → `IdunBattle.Entities.Components.ValueOverride$$SetOverride` : pose la valeur d'override du stat. `is_modifiable=True` (cas MV71 InitialDmg,
        flag +0x7c du ChangeStat mode 4) ⇒ `Current = override + modTotal` — les modifications du
        PORTEUR (buffs) continuent de s'appliquer par-dessus l'override (i2 « buffs are taken from
        the Drone »)."""
        self.override.override = int(value)
        self.override.is_modifiable = bool(is_modifiable)

    def remove_override(self) -> None:
        """`IdunBattle.Entities.Components.StatComponent$$ApplyModifier` part **8 = REMOVE_OVERRIDE** →
        `IdunBattle.Entities.Components.ValueOverride$$RemoveOverride` : retire l'override — `Current` redevient
        `Initial + modTotal` (les modifications par-source sont intactes)."""
        self.override.override = None


class FillUpStatComponent:
    """`IdunBattle.Entities.Components.FillUpStatComponent` — stat « qui se remplit », layout
    distinct de `StatComponent`. **TROIS** composants natifs en héritent, et ce sont exactement les
    trois cases du switch d'`IdunBattle.Entities.UnitExtensions$$ApplyStatModifier` (xref UNIQUE
    d'`ApplyModifier`) qui vont à `IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier` —
    hiérarchie LUE dans `data/symbols/<build>/frida/classes.tsv`, pas déduite :

        case 4  `StatType.Armor`           -> `IdunBattle.Entities.Components.ArmorComponent`
        case 5  `StatType.Health`          -> `IdunBattle.Entities.Components.HealthComponent`
        case 20 `StatType.NumberOfMembers` -> `IdunBattle.Entities.Components.NumberOfMembersComponent`

    ⚠ **`GroupUnitComponent` N'EXISTE PAS** dans le build `rnca9r7q6c` (0 ligne dans `classes.tsv`) :
    le nom porté par le port jusqu'à #572-r3 était FAUX. Seules des FONCTIONS portent ce préfixe
    (`IdunBattle.Core.Services.DamageCalculations$$GetGroupUnitRemainingMemberCount`, …).

    Layout natif (offsets LUS dans `FillUpStatComponent$$GetStatPart` / `$$ApplyModifier`) :
    `initial`(+0x10), `base`(+0x14), `current`(+0x18), `modification`(+0x28, `ValueModification`),
    `override`(+0x38, `ValueOverride`). `IdunBattle.Entities.Components.FillUpStatComponent$$Initialize`
    pose `+0x10 = +0x14 = +0x18`.

    `IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart` — mirror 1:1 :
    0→`+0x18` ; 1→`round(max(0, current/CurrentMaximumValue) * 100)` ; **2→`get_CurrentMaximumValue()`** ;
    **3→`+0x10`** ; 4→`CurrentMaximumValue − current` ; 5/9→`+0x28` (avec `source` →
    `ValueModification.GetModificationFromEntity`) ; **7→`override ?? +0x14`**.

    ⚠ **Les parts 2 et 3 NE COÏNCIDENT PAS**, et les confondre est le piège de #873 transposé :
    elles sont égales au déploiement (`Initialize` les égalise) et divergent dès qu'une
    modification ou un override existe. (#60 : l'ancien mapping du port 3→modTotal était une
    transcription erronée ; part 3 lit `*(comp+0x10)` — c'est ce part 3 que
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour` lit sur le
    `NumberOfMembersComponent` = nrOfMembers.)"""
    __slots__ = ("current", "initial", "base", "modification", "override")

    #: `Math.Min(0x7fffffff - initial, ...)` de `get_CurrentMaximumValue` — borne `int.MaxValue`
    #: du natif, un vrai scalaire (elle ne désigne rien).
    _INT32_MAX = 0x7fffffff

    def __init__(self, current: int = 0, maximum: int = 0, initial: Optional[int] = None,
                 modification: Optional[ValueModification] = None,
                 override: Optional[ValueOverride] = None):
        self.current = int(current)
        # `maximum` = le champ BASE `+0x14`. `initial` (`+0x10`) le suit par défaut, ce qui est
        # exactement l'état que pose `FillUpStatComponent$$Initialize` (`+0x10 = +0x14 = +0x18`) ;
        # le séparer n'a de sens qu'après un `ApplyModifier` case 2 (qui écrit les deux) ou un
        # seeding qui capte les deux canaux.
        self.base = int(maximum)
        self.initial = int(maximum) if initial is None else int(initial)
        self.modification = modification if modification is not None else ValueModification()
        self.override = override if override is not None else ValueOverride()

    def get_current_value(self) -> int:
        return self.current

    def get_current_maximum_value(self) -> int:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$get_CurrentMaximumValue` — MIRROR 1:1
        (même transcription que `runner.components.HealthComponent.current_maximum_value`) :

            var o = override.GetOverrideValueWithModification(modification);   // +0x38, +0x28
            if (o.HasValue) return o.Value;
            return Math.Min(int.MaxValue - initial, Math.Max(-initial, modTotal)) + base;
        """
        ovr = self.override.get_override_value_with_modification(self.modification.total)
        if ovr is not None:
            return int(ovr)
        initial = int(self.initial)
        m = max(-initial, int(self.modification.total))       # Math.Max(-initial, modTotal)
        m = min(self._INT32_MAX - initial, m)                 # Math.Min(int.MaxValue - initial, .)
        return m + int(self.base)

    #: `maximum` reste LISIBLE (et assignable) pour les appelants historiques : c'est le champ
    #: BASE `+0x14`, celui qu'écrit `ApplyModifier` case 2 (`+0x14 = +0x10 = value`).
    @property
    def maximum(self) -> int:
        return self.base

    @maximum.setter
    def maximum(self, value: int) -> None:
        self.base = int(value)
        self.initial = int(value)

    def get_stat_part(self, part: int, source: object = None) -> int:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart` — mirror 1:1 (cf. la
        table de la docstring de classe)."""
        p = int(part)
        mx = self.get_current_maximum_value()
        if p == StatPart.CURRENT:                  # 0
            return self.current
        if p == StatPart.CURRENT_PCT:              # 1
            if mx <= 0:
                return 0
            return round(max(0.0, self.current / mx) * 100)
        if p == StatPart.MAXIMUM:                  # 2 -> get_CurrentMaximumValue()
            return mx
        if p == StatPart.INITIAL:                  # 3 -> champ `+0x10`
            return int(self.initial)
        if p == StatPart.MISSING:                  # 4
            return mx - self.current
        # #270-r1-r1 : meme tuple de `StatPart` que `StatComponent.get_stat_part`.
        if p in (StatPart.MODIFICATION, StatPart.MULTIPLIER_MODIFICATION):
            if source is not None:
                return self.modification.get_modification_from_entity(source)
            return self.modification.total
        if p == StatPart.OVERRIDE:                 # 7 -> `override ?? +0x14` (PAS 0)
            ovr = self.override.override
            return int(ovr) if ovr is not None else int(self.base)
        raise ValueError(f"StatPart {p} non implemente (FillUpStatComponent)")

    def modify_max(self, source: object, amount: int) -> None:
        """`ApplyModifier` part `StatPart.MODIFICATION` -> `IdunBattle.Entities.Components.
        FillUpStatComponent$$ModifyMax` = `ValueModification.Modify(+0x28, entityId, modification,
        isMultiplier, initialValue = +0x10)`. C'est le MAXIMUM qui bouge, jamais `+0x18`."""
        self.modification.modify(source, int(amount))

    def reverse_max_modification(self, source: object) -> None:
        """`ApplyModifier` part `StatPart.RESET_MODIFICATION` -> `ValueModification.
        ReverseModification(+0x28, entityId)`."""
        self.modification.reverse_modification(source)

    def override_max(self, value: int, is_modifiable: bool = True) -> None:
        """`ApplyModifier` part `StatPart.OVERRIDE` -> `ValueOverride.SetOverride(+0x38, ...)`."""
        self.override.override = int(value)
        self.override.is_modifiable = bool(is_modifiable)

    def remove_max_override(self) -> None:
        """`ApplyModifier` part `StatPart.REMOVE_OVERRIDE` -> `ValueOverride.RemoveOverride(+0x38)`."""
        self.override.override = None


class UnitStats:
    """Bloc de stats d'une unité : `StatType → composant`. `get_stat` = `IdunBattle.Entities.UnitExtensions$$GetStat` (dispatch StatType → composant → `get_stat_part(part)`). Porté par `UnitContext`,
    partagé par la prédiction ET le runner."""
    __slots__ = ("components",)

    def __init__(self, components: Optional[Dict[int, object]] = None):
        # clé = int(StatType) ; valeur = StatComponent | FillUpStatComponent
        self.components: Dict[int, object] = dict(components) if components else {}

    def get_stat(self, stat_type: int, stat_part: int = StatPart.CURRENT,
                 source: object = None) -> int:
        """`IdunBattle.Entities.UnitExtensions$$GetStat`. Renvoie 0 si le StatType n'a pas de composant
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
                initial=int(initial), min_value=_stat_min(idx), max_value=STAT_CLAMP_MAX.get(idx))

    def change_stat(self, stat_type: int, source: object, amount: int) -> None:
        """`DSLFactory.ChangeStat` (Position(statType, part 5/9) = apply) : ajoute `amount` (delta
        additif) attribué à `source` dans la modification du StatType. Crée un `StatComponent(initial=0)`
        si absent (le natif suppose le composant présent ; offline on le tolère)."""
        idx = int(stat_type)
        comp = self.components.get(idx)
        if comp is None:
            comp = StatComponent(initial=0, min_value=_stat_min(idx))
            self.components[idx] = comp
        comp.modification.modify(source, int(amount))

    def revert_stat(self, stat_type: int, source: object) -> None:
        """`DSLFactory.ChangeStat` (Position(statType, part 6) = revert) : retire la contribution de
        `source` sur le StatType."""
        comp = self.components.get(int(stat_type))
        if comp is not None:
            comp.modification.reverse_modification(source)

    def set_stat_override(self, stat_type: int, value: int, is_modifiable: bool = True) -> None:
        """`ChangeStat` mode 4 + `Position(statType, part 7 = OVERRIDE)` → `IdunBattle.Entities.Components.StatComponent$$ApplyModifier` case 7 → `IdunBattle.Entities.Components.ValueOverride$$SetOverride`. Crée le composant si absent
        (StatType non seedé → base 0, l'override prime de toute façon). Usage : effet MV71
        `InitialDmg` (4 stats du drone overridées aux valeurs CURRENT du parent)."""
        idx = int(stat_type)
        comp = self.components.get(idx)
        if comp is None:
            comp = StatComponent(initial=0, min_value=_stat_min(idx), max_value=STAT_CLAMP_MAX.get(idx))
            self.components[idx] = comp
        if not isinstance(comp, StatComponent):
            raise TypeError(f"set_stat_override: stat {idx} n'est pas un StatComponent "
                            f"({type(comp).__name__})")
        comp.apply_override(int(value), is_modifiable)

    def remove_stat_override(self, stat_type: int) -> None:
        """`ChangeStat` mode 4 + `Position(statType, part 8 = REMOVE_OVERRIDE)` → `IdunBattle.Entities.Components.StatComponent$$ApplyModifier` case 8 → `IdunBattle.Entities.Components.ValueOverride$$RemoveOverride`. No-op si composant absent."""
        comp = self.components.get(int(stat_type))
        if comp is not None and isinstance(comp, StatComponent):
            comp.remove_override()

    def has_negative_modifier(self, stat_types) -> bool:
        """`IdunBattle.Entities.Triggers.HasNegativeModifier$$ShouldTrigger` — True si l'une des
        stats de `stat_types` (le FILTRE natif) porte AU MOINS UNE modification per-source NEGATIVE (<0).
        Le natif itere le `Dictionary<source, ValueModification>` de la stat de la cible et renvoie true au
        1er `value(@+0x14) < 0` dont le stat(@+0x10) est dans le filtre. Foyer du gate `ConquerorImperative`
        (IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect$$CreateDamageModifier : filtre array {4, 16} = ARMOR + FIXED_ARMOR = "cible a l'armure REDUITE"). No-op (False)
        pour une stat absente ou sans modification. Le residu de capture (`CAPTURED_SOURCE`) NEGATIF (cible
        deja debuffee au snapshot, Current < Initial) declenche correctement le gate = fidele."""
        for st in stat_types:
            comp = self.components.get(int(st))
            if comp is None:
                continue
            mod = getattr(comp, "modification", None)
            if mod is None:
                continue
            if any(int(v) < 0 for v in mod.per_source.values()):
                return True
        return False

    def negative_stat_modification(self, stat_type: int) -> int:
        """`IdunBattle.Entities.Formulas.NegativeStatModificationFormula$$Calculate` -- la SOMME des
        VALEURS ABSOLUES des modifications per-source strictement NEGATIVES d'UNE stat (donc un
        nombre >= 0). Corps natif, transcrit :

            total = 0
            for (source, modifier) in GetStatComponent(unit, statType).Modifications:
                if modifier.<amount> < 0:  total -= modifier.<amount>
            return total

        C'est le PENDANT QUANTITATIF d'`has_negative_modifier` ci-dessus (qui est le predicat
        `IdunBattle.Entities.Triggers.HasNegativeModifier$$ShouldTrigger`) : MEME dictionnaire
        per-source, MEME signe teste, mais on ACCUMULE au lieu de rendre `true` au premier. Les deux
        lisent `ValueModification.per_source`, jamais `total` -- une stat dont les mods se compensent
        (`-40` + `+40`, total 0) rend bien `40` ici, comme le natif.

        ⚠ Le natif LEVE quand `GetStatComponent` rend null (`FUN_1801f51f0` = le throw IL2CPP) ; le
        port rend 0, comme partout ailleurs dans ce module (`get_stat` mirrore le `default -> 0` du
        switch natif). Un arbre valide n'interroge cette formule que sur une stat qui existe.

        Consommateur porte : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.OrbsOfDecayAbility$$
        GetTriggerForAttack` (#1003), qui en fait un RATIO contre `StatAmount(part Initial)`."""
        comp = self.components.get(int(stat_type))
        if comp is None:
            return 0
        mod = getattr(comp, "modification", None)
        if mod is None:
            return 0
        return sum(-int(v) for v in mod.per_source.values() if int(v) < 0)

    def increment_base(self, stat_type: int, by: int = 1, base_if_absent: int = 0) -> None:
        """Incrémente la valeur de BASE (Initial) d'un stat-compteur BRUT. Mirror du bump inline de
        `IdunBattle.Operations.StartTurnOperation$$Execute` : `*(int*)(unitComp+0x58) += 1` par unité du joueur
        courant (compteur PER-UNIT `turnsStarted`, stat 12 = `GetStat(unit, 0xc)`). Le natif écrit le
        CHAMP BRUT du compteur (PAS une `ValueModification`) → on bump l'`initial` du `StatComponent`,
        pas sa modification. Seede un `StatComponent(base_if_absent)` si le stat est absent (summon frais /
        capture sans le stat → base 0). Réservé aux compteurs SANS stat-modification (le clamp par-stat
        s'applique à la lecture via `get_current_value`)."""
        idx = int(stat_type)
        comp = self.components.get(idx)
        if comp is None:
            comp = StatComponent(initial=int(base_if_absent), min_value=_stat_min(idx),
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

# ─── #270-r1-r1 / #270-r3 : ces trois tables DÉSIGNENT des `StatType`, elles ne comptent pas ──────
#
# DÉCISION EXPLICITE SUR `StatType`, parce qu'elle n'est pas neutre. Son mirror est inscrit
# `strict=False` au registre de `probe_313` : le port RECONVENTIONNE les noms (`CRIT_CHANCE` pour
# `CriticalChance`, UPPER_CASE partout), donc `StatType.CRIT_CHANCE` nomme le PORT, pas le build.
# On convertit QUAND MÊME, et voici pourquoi ce n'est pas un contournement de la règle :
#   * ce que la règle vise est la PÉREMPTION SILENCIEUSE d'un ordinal. `strict=False` relâche les
#     NOMS, jamais les VALEURS : `probe_313` confronte les 27 valeurs de `StatType` au build à
#     chaque passe. Écrire le membre fait donc re-dériver l'ordinal d'une table SOUS CLIQUET ;
#     laisser `7` ne protège de rien du tout ;
#   * l'écart de nom est DÉCLARÉ (docstring du mirror + `raison=` du registre), pas silencieux.
# L'alternative — renommer les membres du port en verbatim du jeu, la voie retenue pour
# `KillUnitStep` (#427) — a un rayon de souffle MESURÉ : 553 références `StatType.<MEMBRE>` dans
# 169 fichiers Python suivis. Hors périmètre de cette tranche -> résidu #270-r1-r1-r2.

# StatTypes « fill-up » : les TROIS cases du switch d'`IdunBattle.Entities.UnitExtensions$$
# ApplyStatModifier` qui appellent `IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier`
# (toutes les autres vont à `StatComponent$$ApplyModifier`). Table LUE au décompilé, #572-r3 :
# ARMOR -> `ArmorComponent`, HEALTH -> `HealthComponent`, NUMBER_OF_MEMBERS ->
# `NumberOfMembersComponent` — les trois héritent de `FillUpStatComponent` (`classes.tsv`).
_FILLUP_STATS = frozenset({StatType.ARMOR,               # 4
                           StatType.HEALTH,              # 5
                           StatType.NUMBER_OF_MEMBERS})  # 20

# Plafonds par-stat (virtuel GetMaxValue) : les pourcentages BlockChance/CritChance sont clampés à 100
# par `IdunBattle.Entities.Components.StatComponent$$GetClampedValue` (le reste = pas de plafond). Sert au clamp de `get_current_value`.
# ⚠ Les CLÉS désignent (`StatType`), les VALEURS comptent (100 = un pourcentage, un vrai scalaire).
STAT_CLAMP_MAX = {StatType.BLOCK_CHANCE: 100,   # 7
                  StatType.CRIT_CHANCE: 100}    # 9

# Planchers par-stat (virtuel GetMinValue) : le port seedait TOUT à min 0, mais EXTRA_HITS(17) est
# NÉGATIF live — preuve #60 (probe_60_swarm) : scarab 3 membres morts → GetStat(17, Current) natif
# = −3 (stat-mod Swarm_HitReduction IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour). Le `Max(0)` natif vit à la FIN de la formule hits
# (`IdunBattle.Core.Services.DamagePrediction$$GetDefaultAttackHits` : Math.Max(hits, 0)), PAS dans le clamp du stat. None = pas de
# plancher ; les stats absentes gardent le min 0 historique (aucun contre-exemple mesuré).
STAT_CLAMP_MIN = {StatType.EXTRA_HITS: None}   # 17 — négatif (Swarm_HitReduction, #60)


def _stat_min(idx: int) -> "Optional[int]":
    return STAT_CLAMP_MIN.get(int(idx), 0)

# Filtre natif du trigger HasNegativeModifier de ConquerorImperative (IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect$$CreateDamageModifier : array inline {4, 16}) =
# les DEUX stats d'armure — ARMOR(4, "Idun Concept" obsolete, en pratique absente) + FIXED_ARMOR(16, live).
# "Armure REDUITE" = l'une de ces stats porte >=1 modification per-source <0 (cf. UnitStats.has_negative_modifier).
ARMOR_STAT_TYPES = (StatType.ARMOR, StatType.FIXED_ARMOR)

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
                    attributed: "Optional[Dict[int, Dict[object, int]]]" = None,
                    overrides: "Optional[Dict[int, tuple]]" = None) -> UnitStats:
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

    `overrides` (optionnel) = `{idxStatType: (valeur, isModifiable)}` = les OVERRIDES (part 7,
    `IdunBattle.Entities.Components.ValueOverride$$SetOverride`) posés par les effets actifs
    (`effects.stat_overrides_by_stat`). C'est un canal SÉPARÉ du delta : `IdunBattle.Entities.
    Components.StatComponent$$get_CurrentValue` rend `override + (isModifiable ? modTotal : 0)` et
    IGNORE la base. Verser `d` d'un stat OVERRIDÉ dans `CAPTURED_SOURCE` laisserait donc une
    modification FANTÔME — invisible tant que l'override est là, et qui REVIENDRAIT dès que le
    driver (`refresh_stat_modifier_effects`) exécute le `RemoveOverride` (part 8). Le résidu se
    mesure ici sur ce que le modèle ne reproduit PAS de `Current`, jamais sur `d`.

    `StatType.HEALTH` reste seedée en `StatComponent` générique : son réservoir RÉEL est le
    `HealthComponent` du runner (#572-r1), que `UnitExtensions$$GetStat` court-circuite déjà côté
    port. `StatType.ARMOR` n'est jamais seedée ici (la clé `armor` n'est PAS dans `COMBAT_STAT_IDS`,
    seulement dans `STAT_IDS_MAX_SEUL`) — mesuré nulle sur tout le corpus confronté (#572-r3).

    ⚠ **`StatType.NUMBER_OF_MEMBERS` est seedée en `FillUpStatComponent`, et c'est une CORRECTION
    (#572-r3), pas un raffinement.** Sous `StatComponent`, `GetStatPart` rend `get_CurrentValue()`
    pour les parts 0 ET 2 — donc `StatPart.Maximum` rendait les membres RESTANTS là où le natif rend
    `nrOfMembers`. MESURE live (`probe_572r3_membres_et_armure.py`, MC1_67/777, deux swarms à 5
    membres) : **14 observations discriminantes, 14 écarts**, jusqu'à `natif=5 / port=1`. Le natif
    SÉPARE les deux sans qu'aucune stat-modification n'existe, parce que son champ courant est
    ENTRETENU — `IdunBattle.Operations.UpdateUnitMembersOperation$$Execute` pose
    `NumberOfMembersComponent+0x18 = IBattleQuery.<slot 184 GetGroupUnitRemainingMemberCount>(unit,
    null)`, appelé après chaque dégât par `IdunBattle.Operations.ApplyDamageOperation$$
    UpdateNumberOfMembersStat`.

    ⚠ Le `statDelta` d'un fill-up N'EST PAS une `ValueModification` : le hook publie
    `GetStat(Current) − GetStat(Initial)` = `+0x18 − +0x10`, sans rapport avec `+0x28`. Il ne part
    donc PAS dans la modification (ce qui rendrait `Maximum` faux à nouveau) : il sert seulement à
    reconstruire `Initial = Current − delta`. Faute de canal pour `+0x14`, `base` suit `initial` —
    reconstruction VÉRIFIÉE exacte sur le corpus (0 divergence `Initial` reconstruit vs `Maximum`
    natif, ce que le probe compte explicitement)."""
    delta = stat_delta or {}
    attributed = attributed or {}
    overrides = overrides or {}
    us = UnitStats()
    for name, idx in (stat_ids or {}).items():
        cur = stats.get(name)
        if cur is None:
            continue
        idx = int(idx)
        d = int(delta.get(name, 0) or 0)
        if idx == int(StatType.NUMBER_OF_MEMBERS):
            us.set_component(idx, FillUpStatComponent(current=int(cur), maximum=int(cur) - d))
            continue
        comp = StatComponent(initial=int(cur) - d, min_value=_stat_min(idx), max_value=STAT_CLAMP_MAX.get(idx))
        for src, amt in (attributed.get(idx) or {}).items():
            comp.modification.modify(src, int(amt))
        ovr = overrides.get(idx)
        if ovr is None:
            residual = d - comp.modification.total                # part inexpliquée par les effets
            if residual != 0:
                comp.modification.modify(CAPTURED_SOURCE, residual)
        else:
            value, modifiable = ovr
            comp.apply_override(int(value), bool(modifiable))
            # Résidu = ce que le modèle ne reproduit pas de `Current` (et NON `d`, cf. ci-dessus).
            residual = int(cur) - comp.get_current_value()
            if residual != 0 and modifiable:
                comp.modification.modify(CAPTURED_SOURCE, residual)
            # `isModifiable == 0` : l'override DOMINE `get_CurrentValue`, aucune modification ne
            # peut absorber un résidu. Un résidu non nul y est donc IRRÉDUCTIBLE — c'est le signe
            # que la valeur re-dérivée est FAUSSE, et il doit rester VISIBLE (`get_stat(Current)`
            # ≠ Current) plutôt que d'être maquillé en modification fantôme.
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
        parts = ["current", "initial"]
        # ⚠ `modification` n'est comparable QUE sur un `StatComponent`, et le critère est DÉRIVÉ du
        # composant, pas d'une liste de StatTypes. `native_stat_parts` appelle « modification » le
        # `statDelta` du hook, c'est-à-dire `GetStat(Current) − GetStat(Initial)` — or l'identité
        # « delta == modTotal » est une propriété de `IdunBattle.Entities.Components.StatComponent$$
        # get_CurrentValue` (`Current = override ?? Initial + modTotal`), et d'ELLE SEULE. Sur un
        # `FillUpStatComponent`, `+0x18` (Current) et `+0x10` (Initial) sont deux champs INDÉPENDANTS
        # de `+0x28` : leur écart mesure les membres morts / les PV manquants, pas une
        # `ValueModification`. Comparer les deux y confondrait deux grandeurs (#572-r3).
        comp = unit_stats.components.get(int(idx))
        if isinstance(comp, StatComponent):
            parts.append("modification")
        got = {p: unit_stats.get_stat(idx, {"current": StatPart.CURRENT,
                                            "initial": StatPart.INITIAL,
                                            "modification": StatPart.MODIFICATION}[p])
               for p in parts}
        for part in parts:
            if got[part] != exp[part]:
                out.append(f"{exp['name']}(idx {idx}).{part}: offline {got[part]} "
                           f"!= native {exp[part]}")
    return out
