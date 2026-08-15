"""Effets `Effects.Loki` — famille STATUT / COMPOSITE / STAT-MOD : effets qui mutent une stat
(`get_stat_modification_*`, HP-floor, ActOfFaith crit), les composites qui spawnent des sous-effets
(`sub_effects_on_apply` : Stunned, Taunted) et les modificateurs multi-axes (BlessingsOfKhorne).
1 classe par effet natif (VA citée). Cf. `loki/__init__.py`."""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import (EffectBonus, for_addition, for_subtraction,
                                       for_percent_decrease, for_percent_increase,
                                       for_percent_subtraction_capped)
from ..base import BaseEffect, SubEffectSpec, SAME_TURNS, is_melee_attack
from ..magnitude import ability_var, bc_effect_config, global_value, trait_var
from ...traits.unit_trait import UnitTrait, has_any_trait, has_trait
from ...kill_unit_step import KillUnitStep   # feuille pure (#1088)
from ...effect_type import EffectType   # #270-r3 : cles de `ContagionsOfNurgle...CTOR_ARGS`
# #998 : le litteral 0x5b4 teste par `ActorHasTriggeredAbility` dans le multiplicateur
# `GetMultiplierBasedOnDefeatedInMelee` est un `TriggeredAbilityType`, PAS un `EffectType`
# (1460 y nomme `AmuletOfTheVoidwyrm_CritDamageReduction` -- deux objets, meme ordinal).
from ...triggered_ability_type import TriggeredAbilityType
# `StatType` etait importe UNIQUEMENT dans le corps de quelques methodes ; `630fb33e`
# (#270-r1-r1-r3) a converti des litteraux en `StatType.<MEMBRE>` dans des methodes qui n'ont PAS
# cet import local -> `NameError` a l'appel. Le lecteur est `get_stat_modification_stat`, appele au
# CHARGEMENT D'ETAT (`stat_modifications_by_source` <- `UnitContext.from_snapshot` <- `load_state`),
# donc toute bataille portant l'un de ces effets LEVAIT. Import module-level : foyer unique (#448-r3-r1).
from ...stats import StatType
from ...stats import StatType, StatPart

# `IdunBattle.Entities.UnitExtensions$$IsMechanical` -- LU au décompilé (#175-e), ce N'EST PAS
# `HasTrait(Mechanical)` seul : le corps enchaîne trois `BaseUnitComponent$$HasTrait` en OU
# court-circuité, sur `5`, `0x3e8` et `0x405`. Les trois ids sont QUALIFIÉS contre
# `IdunBattle.Entities.Enum.UnitTrait`. Même lecture que `engine/playbook/non_owner.py::_is_mechanical`
# (l'autre consommateur porté de cette fonction native) -- la valeur y est en IDS, ici en NOMS.
_IS_MECHANICAL_TRAITS = (UnitTrait.Mechanical,      # 5
                         UnitTrait.LivingMetal,     # 0x3e8 = 1000
                         UnitTrait.Vehicle)         # 0x405 = 1029


# ---------------------------------------------------------------------------------------------
# #368-r2 -- LA CONDITION D'ACTIVITE D'UN EFFET DE TUILE, et RIEN QUE POUR LES QUATRE QUI L'ONT
# ---------------------------------------------------------------------------------------------
# Corps natif (relu VERBATIM sur `t6dpr4k06g`), nomme par l'ICF
# `IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$CreateActiveCondition` :
#
#     op_BitwiseOr( DSLTriggers.IsWalkable(sel), DSLTriggers.IsSpawnTile(sel) )
#
# et chacun des deux termes est un `IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger`
# construit sur un SELECTEUR :
#     `DSLTriggers$$IsWalkable(sel)`  -> `AmountIsGreater( DSLSelectors$$Walkable(sel),  <minAmount> )`
#     `DSLTriggers$$IsSpawnTile(sel)` -> `AmountIsGreater( DSLSelectors$$SpawnTiles(sel), <minAmount> )`
# `sel` = `DSLSelectors+0x30`, LE MEME objet que rend leur `CreateTargetSelector` (corps
# `Loki.WhisperingWebEffect$$CreateTargetSelector` = `return DSLSelectors+0x30`), donc « Self ».
#
# ⚠ LE SECOND TERME NE PARLE PAS DE POINTS DE SPAWN, ET C'EST LE PIEGE DE SON NOM.
# `IdunBattle.Entities.Selectors.SpawnTilesSelector$$Select` (corps PROPRE : `frida/methods.tsv`
# l'attribue bien a cette classe) est litteralement :
#     foreach (tile in <selecteur interne>.Select(entities))
#         if (TileExtensions.IsTemporary(tile)) result.Add(tile)
# et `IdunBattle.Entities.TileExtensions$$IsTemporary` rend `TileComponent+0x2c`. Le predicat est
# donc « la tuile est TEMPORAIRE » (tuiles posees EN COMBAT : HulkDoor, plateformes de spawn), pas
# « la tuile appartient a un `SpawnPointGroup` du board ». Lire le nom au lieu du corps aurait fait
# porter une appartenance geometrique qui n'existe pas.
#
# ⚠ QUATRE CLASSES SEULEMENT partagent ce corps -- `FireEffect`, `IceEffect`,
# `DespoiledGroundEffect`, `Loki.ContaminatedEffect`. Les 114 autres classes du build partagent le
# corps par DEFAUT (`return DSLTriggers+0x40`, le trigger CONSTANT de la fabrique), qui n'est PAS
# une condition de tuile. En particulier `Idun.DarknessEffect` -- pourtant membre du set
# `StaticBattleRules.Effect$$IsTileStatusEffect` -- n'a AUCUNE condition : indexer cette table sur
# `TILE_STATUS_EFFECT_TYPES` serait FAUX (5 types au lieu de 4).
TILE_ACTIVE_CONDITION_EFFECT_TYPES = frozenset((
    EffectType.Fire,                # 5    = 0x05   -- `IdunBattle.Entities.Effects.FireEffect`
    EffectType.Ice,                 # 17   = 0x11   -- `IdunBattle.Entities.Effects.IceEffect`
    EffectType.Contaminated,        # 1244 = 0x4dc  -- proprietaire du corps partage
    EffectType.DespoiledGround,     # 1476 = 0x5c4
))


def tile_status_effect_is_active(walkable: "bool | None",
                                 is_temporary: "bool | None") -> "bool | None":
    """Mirror 1:1 de `Loki.ContaminatedEffect$$CreateActiveCondition` evaluee sur la tuile PORTEUSE.

        IsWalkable(Self) | IsSpawnTile(Self)   ==   walkable(tuile) OR IsTemporary(tuile)

    TRI-ETAT, et c'est LOAD-BEARING : `None` = **NON MESURE** (le substrat ne publie pas le canal),
    jamais un `True` de confort. Le consommateur qui recoit `None` doit LAISSER LE FLAG INCHANGE --
    exactement ce que fait le natif quand il ne re-evalue pas (`RefreshEffectsOperation$$
    ShouldBeActive` retourne `EffectComponent+0x5c` INCHANGE des que `ShouldRefreshForTrigger`
    est faux). Rendre `True` par defaut re-activerait un effet que le natif avait desactive.

    Un seul terme mesure suffit a conclure VRAI (disjonction court-circuitee) ; il faut les DEUX
    pour conclure FAUX."""
    if walkable is True or is_temporary is True:
        return True
    if walkable is False and is_temporary is False:
        return False
    return None


class HypersensoryMinimalHealthEffect(BaseEffect):
    """`HypersensoryAbilities_MinimalHealthEffect` (Effects.Idun, effet 0x564=1380 ; IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$.ctor).

    HP-FLOOR passif de Judh (genesJudh). i2 : « The first time each enemy turn that Judh is attacked, she
    cannot fall below 50% of her current Health. » Posé sur le porteur à l'init de l'ability passive
    `HypersensoryAbilities` (owner-effect `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility$$CreateBehaviour = `AddEffect(0x564, owner)`).

    - `IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$ApplyInternal : `floor = Min(Round(GetStat(Health,Current) x hpPct/100), current-1)` ->
      `HealthComponent.MinimalHealth @+0x1c` (Nullable). SNAPSHOT du HP COURANT au moment de l'Apply.
    - `IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$RevertInternal : `MinimalHealth = null` (efface le plancher).
    - `IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$CreateActiveCondition : `IsEnemyTurn(owner) & Not(HasBeenAttackedAmountThisTurn(owner)>=1)`
      = actif au tour ENNEMI, la 1re attaque SEULEMENT (retiré après -> le 2e coup peut tuer).

    hpPct[L1..65] = 30..50 (var 0x26, level-indexée, NON rarity-scalée : `variablesAffectedByRarityBonus` =
    [minDmg,maxDmg] seulement). Apply/Revert (IMPÉRATIF, mute `HealthComponent`) = `MinimalHealthEffectOperation`
    côté runner (évalué par le driver `evaluate_minimal_health` aux transitions turn-start / après-attaque) ;
    cette classe porte la FORMULE du plancher + le pct config (frontière déclaratif/impératif : la condition +
    la formule ici, la mutation ECS dans l'Operation)."""

    def minimal_health_pct(self) -> "int | None":
        """`hpPct[ability_level]` (%) — var 0x26, level-indexée, NON rarity-scalée. Niveau = celui de l'ability
        PASSIVE HypersensoryAbilities (fallback stack level)."""
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var("HypersensoryAbilities", "hpPct", lvl)

    def compute_floor(self, current_hp: "int | None") -> "int | None":
        """`IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$ApplyInternal : `Min(Round(current_hp x hpPct/100), current_hp - 1)`. None si pct absent
        ou hp<=0. `Fix64.Round` = RoundToNearest half-to-even == `round()` Python (le facteur pct/100 est exact
        en Fix64 ; l'arrondi ne joue que pour un hp impair a 50 %)."""
        pct = self.minimal_health_pct()
        if pct is None or current_hp is None or int(current_hp) <= 0:
            return None
        raw = int(round(int(current_hp) * pct / 100.0))
        return min(raw, int(current_hp) - 1)


class ContaminatedEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.ContaminatedEffect` (effet de TUILE 0x4dc=1244) — porté ICI pour
    son SEUL point d'extension déclaratif : l'IMMUNITÉ.

    `IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$EntityIsImmuneToEffect` (mirror 1:1) :

        HasTrait(entity, 0x7eb = 2027 = UnitTrait.ContagionsOfNurgle)
          || UnitExtensions.IsMechanical(entity)
          || base.EntityIsImmuneToEffect(entity)          # HasTrait(Immune) && CanBeImmuneTo

    `get_CanBeImmuneTo` = **true** (vtable runtime, cf. `BaseEffect.can_be_immune_to`) ⇒ la 3e branche
    mord réellement pour cet effet.

    ⚠ `IsMechanical` N'EST PAS `HasTrait(Mechanical)` (#175-e). Le corps de
    `IdunBattle.Entities.UnitExtensions$$IsMechanical` enchaîne TROIS `BaseUnitComponent$$HasTrait` en
    OU court-circuité — `5` `Mechanical`, `0x3e8` = 1000 `LivingMetal`, `0x405` = 1029 `Vehicle` — et
    l'approximation « trait `Mechanical` seul » (héritée de #154) était un FORK : la MÊME fonction
    native est déjà lue correctement par `engine/playbook/non_owner.py::_is_mechanical`. Sur le
    catalogue du build `rnca9r7q6c` les deux ensembles coïncident (130 unités des deux côtés : tout
    `LivingMetal`/`Vehicle` y est aussi `Mechanical`), donc l'écart était INOBSERVABLE au kit — mais
    `entity_trait_names` porte AUSSI les traits accordés EN BATAILLE (`AddTrait`), où rien ne garantit
    cette coïncidence. On lit les trois, comme le natif.

    C'est le canal unique consulté par les DEUX consommateurs : le gate générique de
    `IdunBattle.Operations.AddEffectOperation$$Execute` (via `EffectFactory.effect_def`) ET le vecteur
    tile-effect `ContaminatedTileEffect` (`operations/triggers/effect_triggers.py`), qui portait
    auparavant la même liste de traits EN DUR — fork 1 nœud natif → 2 portes offline, supprimé."""

    can_be_immune_to = True                          # `get_CanBeImmuneTo` -> stub partagé `return 1`

    def entity_is_immune_to_effect(self, trait_names: "list | None" = None) -> bool:
        # `HasTrait(entity, 0x7eb)` puis `IsMechanical(entity)` -- ce SECOND test est la chaîne de
        # TROIS traits en OU du natif, pas le seul `Mechanical` (cf. l'encart de la docstring).
        if has_any_trait(trait_names, (UnitTrait.ContagionsOfNurgle,)) \
                or has_any_trait(trait_names, _IS_MECHANICAL_TRAITS):
            return True
        return super().entity_is_immune_to_effect(trait_names)


class ContagionsOfNurgleArmorReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect` — le DEBUFF d'armure
    de l'aura `ContagionsOfNurgle` (trait 0x7eb = 2027), en DEUX instances de la MEME classe native.

    `IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$.ctor` =
    `AStatModifierEffect(AbilityOrEffect(0x431), 0, 0, 1, 1)` puis `this+0x488 = <cle de constante>`,
    `this+0x48c = <min>`, `this+0x490 = <max>`. Les DEUX seules constructions
    (`IdunBattle.Core.Services.EffectsDatabase` b__14_93 / b__14_94) :

        effet 0x42f = 1071  ContagionsOfNurgle_ArmorReduction1 : ctor(0x41, min=1, max=1)
        effet 0x430 = 1072  ContagionsOfNurgle_ArmorReduction2 : ctor(0x42, min=2, max=0x7fffffff)

    ⚠ Le parent est `AStatModifierEffect`, PAS `ADynamicStatModifierEffect` (lecture corrigee) :
    `IdunBattle.Entities.Effects.ADynamicStatModifierEffect$$CreateTargetTrigger` utilise `+0x488`
    comme CACHE DE POINTEUR de son trigger, or le ctor y ecrit un `int` (la cle de constante) — les
    deux usages sont incompatibles. Consequence : aucun `RefreshValueInternal` (revert+apply de
    magnitude) sur cette famille ; sa magnitude est une CONSTANTE de config.

    `$$GetStatModificationAmount` = `AbilityConfiguration.GetNumberConstant(config, this+0x488)` ->
    les variables de trait `contagionsOfNurgleArmorOneAura` (-20) / `contagionsOfNurgleArmorTwoOrMoreAuras`
    (-40) du gameconfig -- LUES, jamais ecrites en dur.
    `$$GetStatModificationStat` = **FixedArmor (16)**.

    ## Le CYCLE DE VIE — `CreateActiveCondition` (le sujet de ce cas)

    `$$CreateActiveCondition`, lu verbatim :

        AmountIsEqualOrGreater( ContagionsOfNurgleAmount(EffectSource(effect@0x150), Owner@0x30),
                                Get(this+0x48c = min) )
      & AmountIsEqualOrGreater( Get(this+0x490 = max),
                                ContagionsOfNurgleAmount(...) )

    soit `min <= amount <= max`. `amount` est le nœud `DSLFormulas$$ContagionsOfNurgleAmount`, dont
    `IdunBattle.Entities.Triggers.ContagionsOfNurgleAmountFormula$$Calculate` DELEGUE au slot 0x95
    d'`IBattleQuery` = `IdunBattle.Core.Services.BattleQuery$$GetInRangeAuraAmount(0x42f,
    GetCurrentTeamId(EffectSource), target, returnFirst: false)` — le MEME slot que celui porte par
    case-224 (`engine/battle_query.py`), et donc le comparateur INCLUSIF `dist <= GetCurrentRange`.

    C'est CETTE condition, et elle seule, qui tient les TROIS comportements que le port n'avait pas :
    l'aura qui GRANDIT (`GetCurrentRange` monte 1 -> 2 -> 3 avec `TurnsStarted` du porteur), l'unite
    qui en SORT, et la bascule 1071 <-> 1072. Les deux instances COEXISTENT sur la cible (le
    `CreateBehaviour` du vecteur pose `AddEffect(1071) & AddEffect(1072)`) et leurs fenetres
    `[1,1]` / `[2,+inf[` sont DISJOINTES : « basculer » n'est pas un switch, c'est l'une qui
    s'active pendant que l'autre se desactive.

    Chaine d'EVALUATION native (`IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect`) :

        active = ShouldBeActive(trigger, type, effect, effComp, owner, activePlayer, effectEntity)
        if (!active)  DeactivateEffect(...)       # IsActive@+0x5c = 0 PUIS UpdateEffectTargets([])
                                                  #   -> RevertEffectsForTargets -> RevertModification
        else          effComp.IsActive@+0x5c = 1 ; UpdateEffectTargets(GetTargets(entities))
                                                  #   -> ApplyEffectsForTargets -> ApplyModification

    donc **l'entite-effet n'est JAMAIS retiree** quand la condition tombe : elle est rendue INERTE
    et sa `ValueModification` est REVERSEE (meme forme que `PinnedEffect`, case-224/#208 §4). Cote
    port c'est le driver `runner/operations/refresh_effects.refresh_stat_modifier_effects` qui joue
    ce role — d'ou l'absence VOULUE d'`applied_stat_mods` ici (le driver ne prend en charge que les
    stat-mods DECLARATIFS ; un stat-mod EAGER serait pose par `AddEffectOperation` et jamais reevalue).

    Le stat-layer du port applique `get_stat_modification_amount()` en ADDITIF : le poseur
    (`operations/triggers/loki/contagions_of_nurgle.py`) materialise donc le -X% en DELTA PLAT
    pre-calcule `-round(FixedArmor x |pct| / 100)` et le range dans `value` -- MEME convention que
    `ContaminatedUnitEffect`.
    MESURE live (case-dpw) : `astraSmnKell` FixedArmor 1496, une seule aura -> 1496 - 299 = **1197**
    (`combatSnapshot` post-attaque), et `astraCreed` 6000 -> 4800.

    ## `get_CanBeImmuneTo` = **true** (#175-r2) -- l'OVERRIDE gagne sur le champ du `.ctor`

    La classe SURCHARGE le slot 59 avec le corps trivial `b0 01 c3` (`mov al,1 ; ret`), lu par DEUX
    voies concordantes (bloc `methodPointers`, 10 controles d'alignement ; vtable runtime). Les deux
    zeros que le `.ctor` passe a `AStatModifierEffect$$.ctor` n'y changent RIEN : le getter du
    parent (`MultiValueStatEntryEffect`) lit bien un CHAMP d'instance (`movzx eax, byte [rcx+X]`),
    mais `IdunBattle.Entities.Effects.BaseEffect$$EntityIsImmuneToEffect` appelle le slot
    VIRTUEL (`klass+0x4e8`), donc l'override de cette classe-ci. Une unite `UnitTrait.Immune`
    refuse donc 1071/1072 au gate de POSE."""

    can_be_immune_to = True                          # `get_CanBeImmuneTo` -> `b0 01 c3`

    stat_mod_source = None   # cle de source ChangeStat (revert par-source, symetrique de reverted_stats)

    # `IdunBattle.Core.Services.EffectsDatabase` b__14_93 / b__14_94 — les DEUX (et seuls) appels du
    # ctor : `effectType -> (cle de constante `+0x488`, min `+0x48c`, max `+0x490`)`. La cle de
    # constante n'est PAS relue ici (la magnitude est materialisee en delta plat par le poseur, qui
    # lit la variable de trait correspondante) ; la FENETRE, elle, est la `CreateActiveCondition`.
    # #270-r3 : les CLES sont des `EffectType` -- le nom de la constante de chaque entree
    # (`contagionsOfNurgleArmor...`) et le nom de la classe portent le meme designateur, et
    # `frida/enums.tsv` le confirme (1071/1072 = `ContagionsOfNurgle_ArmorReduction1`/`2`, la ou
    # `TriggeredAbilityType` nomme `CursedPlagueBell`/`CursedOfTheWalkingPox`).
    # Les VALEURS, elles, restent des scalaires : une constante gameconfig et une FENETRE
    # (min, max), dont `0x7FFFFFFF` est la borne « pas de maximum ».
    CTOR_ARGS = {
        EffectType.ContagionsOfNurgle_ArmorReduction1:    # 0x42F = 1071
            ("contagionsOfNurgleArmorOneAura", 1, 1),
        EffectType.ContagionsOfNurgle_ArmorReduction2:    # 0x430 = 1072
            ("contagionsOfNurgleArmorTwoOrMoreAuras", 2, 0x7FFFFFFF),
    }

    def aura_amount_window(self) -> "tuple | None":
        """`(min, max)` = `(this+0x48c, this+0x490)` de CETTE instance, resolus par son `effectType`
        (une seule classe native, deux constructions). `None` = type hors des deux constructions."""
        args = self.CTOR_ARGS.get(int(self.effect_type or 0))
        return None if args is None else (args[1], args[2])

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        """`ContagionsOfNurgle_ArmorReduction_Effect$$CreateActiveCondition` — mirror LITTERAL :
        `min <= ContagionsOfNurgleAmount(EffectSource(effect), Owner) <= max`.

        `unit_state["contagions_of_nurgle_amount"]` est le CALLABLE du foyer
        `runner/components.contagions_of_nurgle_amount` (lui-meme un mirror delegue de
        `BattleQuery$$GetInRangeAuraAmount`) ; on lui passe `self.source`, qui EST l'`EffectSource`
        (`EffectComponent.SourceUnit @+0x10`).

        DEGRADATION — cle absente, source inconnue, ou cardinal indeterminable : on rend le FLAG
        courant `self.active`. Ce n'est pas une convention inventee, c'est un chemin natif REEL :
        `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` rend litteralement
        `effectComponent.IsActive @+0x5c` (le flag COURANT, sans rien evaluer) des que
        `effect.ShouldRefreshForTrigger(trigger)` est faux. Un `True` inconditionnel rendrait ici
        les DEUX instances actives a la fois, donc -20 % ET -40 % cumules — precisement ce que les
        fenetres disjointes interdisent."""
        window = self.aura_amount_window()
        fn = (unit_state or {}).get("contagions_of_nurgle_amount") if unit_state else None
        if window is None or fn is None or self.source is None:
            return bool(self.active)
        n = fn(self.source)
        if n is None:
            return bool(self.active)
        return window[0] <= int(n) <= window[1]

    def get_stat_modification_stat(self) -> int | None:
        return StatType.FIXED_ARMOR                                    # StatType.FixedArmor (arg du ctor natif)

    def get_stat_modification_amount(self) -> int | None:
        # Forme de BASE (`GetStatModificationAmount`) : le DELTA PLAT pre-calcule a la pose
        # (= -round(FixedArmor x |pct| / 100)), range dans `value` par le vecteur poseur. `None` =
        # instance CAPTEE (le canal `decisionView.effects` ne publie pas de valeur) -> la magnitude
        # passe alors par la forme OVERRIDE `applied_stat_mods(ctx)` ci-dessous, qui sait la
        # re-deriver depuis le stat de BASE du porteur.
        return self.value

    def applied_stat_mods(self, stats_ctx) -> "list":
        """Forme OVERRIDE d'`AStatModifierEffect$$ApplyModification` — magnitude CONTEXTUELLE.

        Le natif rend `GetStatModificationAmount()` = `GetNumberConstant(<cle>)` = le POURCENTAGE
        (-20 / -40) et pose `Position(stat, part = isMultiply ? 9 : 5)` ; `isMultiply` vaut 1 pour
        cette famille (6e argument du ctor `AStatModifierEffect`). Le stat-layer du port n'a pas de
        part MULTIPLICATIVE : la contribution y est materialisee en DELTA PLAT equivalent,
        `-round(GetStat(FixedArmor, INITIAL) x |pct| / 100)` -- MESURE live, 2312 -> 1850 (-20 %)
        et 2312 -> 1387 (-40 %), bit-exact des deux cotes.

        POURQUOI cette forme en PLUS du `value` de la pose : une instance SEEDEE n'a pas de `value`
        (le canal de capture ne publie pas la magnitude). Sans elle, la passe 2 de
        `UnitContext.from_snapshot` (`stat_modifications_by_source(effects, stats_ctx=ctx)`) ne peut
        rien attribuer, la contribution reste dans le residu opaque `CAPTURED_SOURCE` et devient
        IRRETIRABLE -- mesure : sortie d'aura live 1387 -> 2312, port fige a 1387.

        GATE `self.active` = le FLAG `EffectComponent.IsActive @+0x5c`, et il est LOAD-BEARING : les
        DEUX instances (1071 et 1072) coexistent sur la cible, mais une seule est active a la fois,
        donc une seule a une `ValueModification` cote natif. Sans ce gate, la passe 2 attribuerait
        -20 % ET -40 % alors que le `statDelta` capte n'en porte qu'un -> double-compte. Le flag est
        seede par #219 et desormais ECRIT a chaque refresh par `refresh_stat_modifier_effects`
        (mirror `ActivateEffect`/`DeactivateEffect`), donc il suit la condition."""
        if not self.active:
            return []                                    # instance INERTE : le natif a deja reverte
        if self.value is not None:
            return [(int(StatType.FIXED_ARMOR), int(self.value))]
        args = self.CTOR_ARGS.get(int(self.effect_type or 0))
        if args is None or stats_ctx is None:
            return []
        pct = trait_var("ContagionsOfNurgle", args[0])
        st = getattr(stats_ctx, "stats", None)
        if pct is None or st is None:
            return []
        base = int(st.get_stat(int(StatType.FIXED_ARMOR), int(StatPart.INITIAL)) or 0)
        if base <= 0:
            return []
        return [(int(StatType.FIXED_ARMOR), -round(base * abs(int(pct)) / 100))]

    def reverted_stats(self) -> "list":
        """`RevertInternal` — annule le `ChangeStat` FixedArmor (lu par la feuille `RemoveEffect`)."""
        return [StatType.FIXED_ARMOR]


class ContaminatedUnitEffect(BaseEffect):
    """`Contaminated_Unit` (effet 0x4dd=1245, `ContaminatedStatModifierEffect`, IdunBattle.Entities.Effects.Loki.ContaminatedStatModifierEffect$$.ctor =
    ADynamicStatModifierEffect FixedArmor) — SOUS-effet pose sur une UNITE occupant/entrant une tuile
    `Contaminated` (0x4dc), 1 round. Debuff dynamique de la stat FixedArmor (=16).

    Le NATIF calcule le montant a l'apply (`IdunBattle.Entities.Effects.ADynamicStatModifierEffect$$GetStatModificationAmount`
    -> `IdunBattle.Entities.Effects.Loki.ContaminatedStatModifierEffect$$GetDynamicStatModificationAmount` = -X% du FixedArmor courant) et l'applique via ChangeStat.
    Cote port : le vecteur tile-effect (#128, `ContaminatedTileEffect`) calcule le delta a l'apply et le stocke
    dans `self.value` -> `get_stat_modification_amount` renvoie `self.value`.

    >>> MAGNITUDE (#132 RESOLUE 2026-07-14, RE re-expert decompile) : `IdunBattle.Entities.Effects.Loki.ContaminatedStatModifierEffect$$GetDynamicStatModificationAmount` = `-BattleQuery.GetEffectConfig(EffectType=6)` (interface IBattleQuery slot 0xbf, arg 6 =
    EffectType litteral). `IdunBattle.Core.Services.BattleQuery$$GetEffectConfig` = lookup `Dict<EffectType,int>@+0xd0`
    peuple par `IdunBattle.Core.Services.BattleQuery$$InitEffectConfig` depuis `BattleConfiguration.Effect` ; l'entree EffectType=6
    (offset +0x28) = **`ContaminatedArmorReductionPct` = 30**. => -30 % du FixedArmor cible. Source = section
    `Effect` de la BC (lue, PAS hardcodee) ; le vecteur `ContaminatedTileEffect` pre-calcule le DELTA PLAT
    `value = -round(FixedArmor * 30/100)` a la pose (le stat-layer l'applique en additif). ⚠ MODE % infere
    du nom `...Pct` + magnitude (le -30 flat serait negligeable) ; le modKind exact du chemin ChangeStat
    partage (flat vs percent) et le %-de-base-vs-courant restent a CONFIRMER live (drop d'armure via
    statModSources sur un occupant contamine)."""

    def get_stat_modification_stat(self) -> int | None:
        return StatType.FIXED_ARMOR                                    # StatType.FIXED_ARMOR

    def get_stat_modification_amount(self) -> int | None:
        # Delta calcule a l'apply par le vecteur (= -round(FixedArmor_courant * X/100)) et stocke dans value.
        # None tant que X non resolu (#132) -> aucune contribution stat (mais l'effet reste PRESENT).
        return self.value


class DespoiledGroundEffect(BaseEffect):
    """`Idun.Source.IdunBattle.Logic.Entities.Effects.DespoiledGroundEffect` (effet de TUILE 0x5c4=1476)
    — le pendant EXACT de `FireEffect` (5) : un MARQUEUR de tuile sans contribution propre, dont tout
    le comportement observable vit dans l'ability d'environnement qui le LIT
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.EnvDespoiledGroundTileAbility`, portee par
    `DespoiledGroundTileDoT`, `operations/triggers/loki/despoiled_ground.py`).

    Les TROIS SEULS virtuels que la classe native surcharge (recherche exhaustive des symboles
    `DespoiledGroundEffect$$*`) :

      * `$$CreateTargetSelector`  = `Self`  (l'effet se cible LUI-MEME : c'est un tile-effect, pas un
        effet projete sur une autre entite). Corps DEDUPLIQUE lui aussi, nomme
        `IdunBattle.Entities.Effects.Loki.WhisperingWebEffect$$CreateTargetSelector`, et son texte
        entier est `return DSLSelectors+0x30`. ⚠ L'offset `@0x148` qui etait ecrit ici ne designe
        RIEN sur `t6dpr4k06g` : sur ce build le champ est `DSLSelectors+0x30` -- et c'est
        EXACTEMENT le selecteur que reprend la `CreateActiveCondition` ci-dessous, ce qui est ce
        qui etablit que son `sel` vaut « Self » ;
      * `$$CreateActiveCondition` = `DSLTriggers.IsWalkable(sel) | DSLTriggers.IsSpawnTile(sel)`
        -- « la tuile est MARCHABLE, **ou bien c'est une tuile de SPAWN** ». Chacun des deux termes
        est un `IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger` sur
        `IdunBattleLogic.Entities.DSLSelectors$$Walkable` / `$$SpawnTiles`.
        ⚠ **LE SECOND TERME ETAIT FAUX ICI** (#368-r2, re-mesure du 2026-08-15) : il y etait ecrit
        `AllAliveMachines(Self@0x148)`, d'ou se deduisait un raisonnement d'innocuite (« les deux
        branches sont satisfaites des qu'une unite peut se tenir sur la tuile ») qui tombe avec lui
        -- une tuile de spawn n'a rien a voir avec un occupant. Le corps est DEDUPLIQUE par l'ICF et
        porte le nom d'un autre proprietaire,
        `IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$CreateActiveCondition`, qu'il PARTAGE
        avec `FireEffect` et `IceEffect` -- relu verbatim, et l'attribution re-derivee par le bloc
        `methodPointers` (`probe_175r2`, calage global 1193/1384) ;
      * `$$.ctor` -> `ABondEffect..ctor(..., 1, 0, <struct ZERO>, 0)`.

    RESIDU FLAGGE (`ActiveCondition` non modelisee) : le port n'ecrit pas
    `EffectComponent.IsActive @+0x5c` pour cet effet, donc l'instance est TOUJOURS active. Degradation
    PERMISSIVE. ⚠ **LA BORNE QUI ETAIT ECRITE ICI N'EN EST PAS UNE** : elle disait « les deux branches
    natives sont satisfaites des qu'une unite peut se tenir sur la tuile », ce qui supposait le second
    terme `AllAliveMachines` -- corrige ci-dessus en `IsSpawnTile`. Ce qui borne REELLEMENT l'ecart,
    c'est que les trois consommateurs lus de ce canal passent `onlyActive: false` (cf.
    `entities/triggers.py::HasEffectTrigger`), un littéral repete a trois sites et non une propriete
    structurelle. Le cycle de vie qui compte -- expiration a echeance -- passe, lui, par
    `remaining_turns`/`consumed` (`EffectComponent$$RemoveOneTurn` + `$$ShouldBeRemoved`, PR #138),
    pas par ce flag.

    DUREE : `StaticBattleRules.Effect$$DefaultAmountOfRounds(0x5c4)` = **2 rounds**
    (`_DEFAULT_ROUNDS[0x5c4]`, `runner/operations/effects.py`), converti en TOURS par
    `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (#98). Aucun poseur natif ne passe
    d'override : les deux `AddEffect(0x5c4, stateRef, Tiles(Target))` lus (FleshMetalGuns_TileEffect,
    LetTheGalaxyBurn) sont la surcharge SANS noeud de duree.

    IMMUNITE : aucune surcharge d'`EntityIsImmuneToEffect` (contraste `ContaminatedEffect`) -> c'est le
    corps GENERIQUE `BaseEffect$$EntityIsImmuneToEffect` qui s'applique.

    ⚠⚠ **MAIS LA CLASSE SURCHARGE `get_CanBeImmuneTo`, ET A `true` (#175-e).** La ligne qui disait
    « les TROIS SEULS virtuels que la classe surcharge (recherche EXHAUSTIVE des symboles
    `DespoiledGroundEffect$$*`) » etait fausse par sa METHODE, pas par inattention : cette classe n'a
    **AUCUN** symbole ghidra -- ses quatre corps sont fondus par l'ICF -- donc une recherche par
    symbole ne peut structurellement rien y voir (« L'ABSENCE dans les tables de symboles ne prouve
    RIEN », CLAUDE.md). Le `global-metadata.dat` lui attribue **4** methodes declarees
    (`get_CanBeImmuneTo` slot 59, `CreateActiveCondition` 62, `CreateTargetSelector` 64, `.ctor`), et
    le bloc `methodPointers` du PE donne `b0 01 c3` = `mov al,1 ; ret` pour le slot 59.
    Consequence : `EntityIsImmuneToEffect(u) = HasTrait(u, UnitTrait.Immune) && true`
    = **`HasTrait(u, Immune)`** -- le gate MORD, la ou le port rendait un `False` inconditionnel.

    ⚠ Le recensement de #224 (vtable RUNTIME, namespace `IdunBattle.Entities.Effects.*`) ne pouvait
    pas la voir non plus : elle vit sous `Idun.Source.IdunBattle.Logic.Entities.Effects`. Les deux
    mesures se RECONCILIENT une fois l'heritage propage (`FireEffect`/`IceEffect`/
    `BlockEnteringUnitsTileEffect` heritent le `true` de `BlockTileMovementEffect`) ; ce qui reste
    ouvert est l'ecart INVERSE -- trois classes qui DECLARENT `true` et que le port tient a `false`
    (residu, cf. `docs/rl/case-175e-immunite-des-feuilles-de-tuile.md`). #85, #175-e."""

    can_be_immune_to = True                          # `get_CanBeImmuneTo` -> `b0 01 c3` (mov al,1 ; ret)


class DespoiledGroundExtraDamagePctEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.DespoiledGround_ExtraDamagePctEffect` (effet 0x5c6=1478) —
    le buff pose sur l'unite **Chaos** qui demarre son tour sur une tuile DespoiledGround.
    i2 `UnitEffects/DespoiledGround_ExtraDamagePct_Description` : « Deals +{[DespoiledGroundExtraDmgPct]}%
    Damage to Xenos or Imperial enemies ».

    `$$CreateEffectDamageBonusForAttack` (MIRROR 1:1 du decompile) :

        trigger = HasTrait(target@0x178, 0x3ee = 1006 Xenos) | HasTrait(target@0x178, 0x1a = 26 Imperial)
        amount  = EffectConfig(8) = BC.Effect["DespoiledGroundExtraDmgPct"] = 15
        return    <EffectBonus inline : +0x00 = trigger, +0x08 = amount, +0x34 = Nullable(AbilityOrEffect)>

    KIND = **PercentIncrease**, et ce n'est PAS une deduction du nom : la fabrique est INLINEE par le
    compilateur, on la reconnait a l'OFFSET ecrit. `IdunBattle.Entities.Effects.EffectBonus$$ForPercentIncrease`
    ecrit `out[0]=trigger ; out[1]=amount` (montant a **+0x08**) tandis que
    `IdunBattle.Entities.Effects.EffectBonus$$ForAddition` ecrit `out[1]=0 ; out[2]=amount` (montant a
    **+0x10**) ; les deux copient le `Nullable<AbilityOrEffect>` a **+0x34**. Le corps de
    `DespoiledGround_ExtraDamagePctEffect` pose le montant a +0x08, laisse +0x10 a zero et le Nullable a
    +0x34 => `ForPercentIncrease`.

    `$$.ctor` = `BaseEffect..ctor(this, AbilityOrEffect(0x5cb), 1, 0)`. ⚠ QUALIFICATION D'ENUM : `0x5cb`
    = **1483 = `TriggeredAbilityType.EnvDespoiledGroundTileDamage`** (l'ability SOURCE de l'effet), PAS
    l'`EffectType` 1483 (`PrioritisedEfficiency_DmgReduction`).

    `$$CreateActiveCondition` = `IsWalkable(Self@0x148)` — non modelisee (meme residu FLAGGE que
    `DespoiledGroundEffect`, cf. sa docstring).

    Pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.EnvDespoiledGroundTileAbility$$
    CreateBehaviour` (2e volet), duree `Direct(1)` = **1 TOUR** (re-posee a chaque tick tant que
    l'unite reste sur la tuile). #85."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        # `HasTrait(target, Xenos) | HasTrait(target, Imperial)` — traits de GRANDE ALLIANCE de la CIBLE.
        # `target_traits is None` = cible inconnue -> aucune contribution (« present != applique »,
        # degradation fidele partagee avec les autres bonus target-conditionnels).
        if target_traits is None:
            return None
        if not has_any_trait(target_traits, (UnitTrait.Xenos, UnitTrait.Imperial)):
            return None
        pct = bc_effect_config("DespoiledGroundExtraDmgPct")     # EffectConfig(8) = 15 (BC, PAS hardcode)
        if not pct:
            return None
        return for_percent_increase(True, int(pct))


class StandVigilExtraArmorEffect(BaseEffect):
    """`StandVigil_ExtraArmorEffect` (Effects.Loki) — buff **StatModification** +armure, **SELF-buff**
    (l'unité se buffe elle-même en « stand vigil » = sans se déplacer). `IdunBattle.Entities.Effects.Loki.StandVigil_ExtraArmorEffect$$GetDynamicStatModificationAmount` = `ConfigVar(key 0x51c=1308, EffectSource, 0x1b)` = ability var
    `StandVigil.extraArmor[level]` (FLAT), ajouté à la **modification** du stat **FixedArmor** (=16) via
    `ChangeStat` (part 5/9 ; revert part 6).

    **Self-buff** ⇒ la source EST l'unité porteuse → `level` = niveau de l'ability StandVigil de l'unité
    elle-même (`self.ability_level` capté depuis unitConfig, sinon `self.level`) → magnitude EXACTE
    offline ⇒ **résidu 0 validable live** (contrairement à RitesOfBattle, buff cross-unité)."""

    def get_stat_modification_stat(self) -> int | None:
        return StatType.FIXED_ARMOR                                   # StatType.FIXED_ARMOR

    def get_stat_modification_amount(self) -> int | None:
        # StandVigil = ability ACTIVE → indexer sur activeAbilityLevel (fallback passif, puis stack level).
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        return ability_var("StandVigil", "extraArmor", lvl)


class MasterOfTheTutelariesEffect(BaseEffect):
    """`MasterOfTheTutelariesEffect` (Effects.Loki, effet 0x4ad=1197 ; IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$.ctor =
    `BaseEffect(AbilityOrEffect(0x448=1096), 1)`) — marqueur until-EoT posé sur ABRAXAS
    (thousInfernalMaster) par l'execute de l'active 1096 (`MasterOfTheTutelariesAbility.
    IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour` : `AddEffect(0x4ad, stateRef, caster@0x160, caster@0x160,
    durée@dsl+0xc0)`, séquencé AVANT le Spawn du Pink Horror — l'attaque immédiate du Horror
    peut donc DÉJÀ déclencher un Screamer).

    - `IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$ApplyInternal` : `AddTriggeredAbility(Entity(target), 0x495=1173,
      GetAbilityState(...))` — ARME la triggered `MasterOfTheTutelaries_SummonAbility`
      (Screamer sur attaque Psychic contre un ennemi) sur le porteur ; l'ability-state de
      1096 est propagé (le niveau des summons en dérive).
    - `IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$RevertInternal` : `RemoveTriggeredAbility(Entity(target), 0x495)` —
      désarme à l'expiration (i2 « until the end of this turn » ; durée = 1 round posée
      par l'AddEffect de l'arbre actif, aucun défaut `_DEFAULT_ROUNDS` pour 1197).

    Port runner : le trigger 1173 vit dans `EFFECT_TRIGGERS[1197]` (triggers/dispatch.py) —
    `collect_effect_triggers` n'instancie le trigger QUE tant que l'effet est ACTIF sur le
    porteur, ce qui EST le Add/RemoveTriggeredAbility natif (le natif gate d'ailleurs
    DOUBLEMENT : le `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateTrigger` re-teste `HasEffect(owner, 0x4ad)`).
    Marqueur pur : aucune stat-mod."""


#: `TriggeredAbilityType 0x5b4 = 1460` -- le litteral que teste `ActorHasTriggeredAbility` dans
#: `BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee`. Nomme (jamais l'ordinal
#: nu) : `EffectType` 1460 est `AmuletOfTheVoidwyrm_CritDamageReduction`, un AUTRE objet.
_TALISMAN_OF_RAGE = int(TriggeredAbilityType.TalismanOfRage)


def multiplier_based_on_defeated_in_melee(melee_defeats: "int | None", *,
                                          self_kills: "int | None" = None,
                                          owner_has_talisman: bool = False) -> int:
    """FOYER UNIQUE du mirror d'`IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$
    GetMultiplierBasedOnDefeatedInMelee`. Relu noeud par noeud (#998) :

        base   = Count( NormalUnits( UnitsDefeatedByMeleeAttack(AllUnits, 0, 1), 0 ) )
        mine   = Count( Filter( <les MEMES entites>,
                                AreEqual( Killer(<DSLSelectors+0x68>), Owner@DSLSelectors+0x30 ) ) )
        extra  = If( ActorHasTriggeredAbility(Owner@+0x30, 0x5b4 = TalismanOfRage),
                     mine, <DSLFormulas+0x18> = Direct(0) )
        return   Min( Sum(base, extra), ConfigConst(0x4c0 = BlessingsOfKhorne, 0x43 = MaxDefeatedUnits) )

    TROIS lecteurs portes, et c'est ce qui en fait un foyer : les deux value-modifications de
    `BlessingsOfKhorneModifiersEffect` (malus PSYCHIQUE en defense, bonus de degat en attaque) et le
    canal crit-DEGAT de la relique `TalismanOfRage` (`loki/talisman_of_rage.py`).

    ## LA BRANCHE `extra` ETAIT DECLAREE MORTE, ET ELLE NE L'EST PAS (#998)

    Le port portait : « INERTE-PAR-ROSTER : AUCUN unit du gameconfig courant ne porte TalismanOfRage
    (verifie unit_map) -- non codee ». **Re-mesure** : `unit_map.py find --ability TalismanOfRage`
    rend **6** unites -- `worldEightbound`, `worldExecutions`, `worldJakhal` (kind `lineup`, voie
    `item` = relique EQUIPABLE, les trois porteurs de `catalog_inject.py --list-relics`) et trois
    bosses npc LHE (voie `relic`, ability CABLEE AU KIT). Le verdict venait de l'angle mort **#323** :
    `unit_map` lisait alors 2 voies d'attribution sur 5 et etait **AVEUGLE AUX RELIQUES**. Les trois
    `lineup` sont exactement les World Eaters qui portent le trait `BlessingsOfKhorne` -- donc les
    deux termes se rencontrent sur la MEME unite, ce qui est le regime ou la branche mord.

    ## TRI-ETAT SUR LES DEUX COMPTEURS -- `None` = non mesure, JAMAIS 0

    * `melee_defeats is None` (aucune source de comptage) -> `0`, effet inerte : c'est le
      comportement anterieur, conserve a l'identique.
    * `self_kills is None` alors que la branche est ARMEE (`owner_has_talisman`) -> on rend le
      `base` SEUL et on ne devine rien. Ce n'est pas un repli neutre, c'est une SOUS-estimation
      nommee : le natif ajouterait un terme positif. Le substrat existe pourtant
      (`decisionView.units[].killerId`, publie par `frida/hooks/.../projection.ts`), donc ce chemin
      ne doit se produire que chez un appelant qui ne seede pas -- pas en production.

    ⚠ `Sum` PUIS `Min` : le cap s'applique a la SOMME, pas a chaque terme. Un porteur qui a tue 5
    unites en melee sur 6 defaites totales rend `Min(6 + 5, 8) = 8`, pas `Min(6,8) + Min(5,8)`.
    Les deux differaient des que la somme depasse le cap -- c'est le cas discriminant du test."""
    if melee_defeats is None:
        return 0
    base = int(melee_defeats)
    extra = int(self_kills) if (owner_has_talisman and self_kills is not None) else 0
    cap = trait_var("BlessingsOfKhorne", "blessingsOfKhorneMaxDefeatedUnits")  # ConfigConst 0x43 (=8)
    return min(base + extra, int(cap) if cap else 8)                          # Sum PUIS Min


class BlessingsOfKhorneModifiersEffect(BaseEffect):
    """`BlessingsOfKhorne_ModifiersEffect` (EffectType 0x4ee=1262, nom capté "BlessingsOfKhorne" ;
    config-owner TriggeredAbilityType 0x4c0=1216) — trait BlessingsOfKhorne (1046), TOUTE la faction
    World Eaters (11 carriers : Azkor worldEightbound, Kharn, Wrask, Macer, + bosses LHE). DEUX
    value-modifications sur le PORTEUR, toutes deux scalées par le MÊME multiplicateur N (#185) :

    - DÉFENSE `IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$CreateEffectDamageMalusForDefense` : `(OwnerIsTarget & DamageProfileIs(0xd=
      Psychic)) -> -ConfigConst(0x4c=DmgPctReduction) x N` ⇒ le dégât PSYCHIQUE reçu par le porteur
      est réduit de `8% x N` (max -64%).
    - ATTAQUE `IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$CreateEffectDamageBonusForAttack` : `get_OwnerIsCaster` SEUL (AUCUN filtre
      profil/normal/spéciale) `-> +ConfigConst(0xf=ExtraDmgPct) x N` ⇒ TOUT le dégât sortant du
      porteur est augmenté de `3% x N` (max +24%).

    N = `IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee` = `Min(Count(NormalUnits(UnitsDefeatedBy-
    MeleeAttack(AllUnits))) [+ TalismanOfRage self-kills], ConfigConst(0x43=MaxDefeatedUnits=8))`.
    Le compte de base est GLOBAL (unités normales des DEUX camps tuées par une attaque de MÊLÉE,
    flag `UnitComponent.DefeatedByMeleeAttack @0x178` écrit par `KillUnitOperation IdunBattle.Operations.KillUnitOperation$$Execute`,
    capté #185 dans decisionView.units). La branche self-kills (`ActorHasTriggeredAbility(owner,
    1460=TalismanOfRage)` → double-compte des kills mêlée du porteur, killer = `DeathReason.KillerId`
    capté) est désormais PORTÉE — cf. `multiplier_based_on_defeated_in_melee` ci-dessus.

    ⚠ ELLE ÉTAIT DÉCLARÉE « INERTE-PAR-ROSTER : AUCUN unit ne porte TalismanOfRage (vérifié
    unit_map) », ET C'ÉTAIT FAUX (#998) : `unit_map find --ability TalismanOfRage` rend **6** unités
    (3 `lineup` par voie `item`, 3 bosses npc par voie `relic`), et les trois `lineup` sont
    précisément des World Eaters — donc porteurs de CE trait. Le verdict venait de l'angle mort
    **#323**, où `unit_map` lisait 2 voies d'attribution sur 5 et était aveugle aux reliques.

    `melee_defeats` = compte BRUT (non cappé) seedé par `Scene._seed_battle_counters()` depuis
    `scene.melee_defeats()` (decisionView.units) ; None (runner offline sans tracking, #185
    runner-side non porté) → effet INERTE (dégradation fidèle « présent ≠ appliqué »).
    Constantes gameconfig (trait BlessingsOfKhorne) : DmgPctReduction=8, ExtraDmgPct=3,
    MaxDefeatedUnits=8 (hors rarityBonus — pas de scaling multiplier)."""

    # Compte BRUT de melee-defeats (seedé par Scene ; None = pas de source -> inerte).
    melee_defeats: "int | None" = None
    #: #998 — kills de MÊLÉE imputables AU PORTEUR (`Filter(..., AreEqual(Killer(u), Owner))`).
    #: Même tri-état : `None` = non mesuré, jamais 0. Seedé par le même foyer partagé.
    melee_defeats_by_owner: "int | None" = None
    #: #998 — `ActorHasTriggeredAbility(Owner@+0x30, 0x5b4)` : le porteur porte-t-il TalismanOfRage ?
    #: C'est ce booléen SEUL qui arme la branche `extra` ; faux -> le natif verse `Direct(0)`.
    owner_has_talisman_of_rage: bool = False

    def _n(self) -> int:
        """`IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee`,
        via le foyer PARTAGÉ (mirror complet, branche `ActorHasTriggeredAbility` comprise — #998)."""
        return multiplier_based_on_defeated_in_melee(
            self.melee_defeats,
            self_kills=self.melee_defeats_by_owner,
            owner_has_talisman=bool(self.owner_has_talisman_of_rage))

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if (damage_profile or "") != "Psychic":               # DamageProfileIs(0xd) IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$CreateEffectDamageMalusForDefense
            return None
        n = self._n()
        if n <= 0:
            return None
        pct = trait_var("BlessingsOfKhorne", "blessingsOfKhorneDmgPctReduction")    # ConfigConst 0x4c (=8)
        if not pct:
            return None
        return for_percent_decrease(False, abs(int(pct)) * n)   # owner=défenseur (effet sur la cible)

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        # trigger natif IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$CreateEffectDamageBonusForAttack = get_OwnerIsCaster SEUL — tous profils, normale ET spéciale.
        n = self._n()
        if n <= 0:
            return None
        pct = trait_var("BlessingsOfKhorne", "blessingsOfKhorneExtraDmgPct")        # ConfigConst 0xf (=3)
        if not pct:
            return None
        return for_percent_increase(True, abs(int(pct)) * n)


class StunnedEffect(BaseEffect):
    """`StunnedEffect` (effet COMPOSITE 0x48a=1162) — `IdunBattle.Entities.Effects.Loki.StunnedEffect$$ApplyInternal spawne 3 SOUS-effets
    quand Stunned est appliqué (confirmé live : parent rem=1 + enfants 1165 rem=1, 1166/1167 rem=0) :
      - `IdunBattle.Entities.Effects.Loki.StunnedEffect$$AddBlockAbilitiesSubEffect → 0x48d=1165 Stunned_CantUseAbility, via
        `AddSubEffectWithSameTurns` ⇒ MÊME durée que le parent.
      - `IdunBattle.Entities.Effects.Loki.StunnedEffect$$ApplyMovementModifier → 0x48e=1166 Stunned_MovementOverride, via
        `AddStatOverrideEffect` (durée 0 = permanent/lié au parent) ; gardé par `StatAmount(movement)>0`
        côté natif (simplification ici : toujours spawné — la quasi-totalité des units ont movement>0 ;
        reverté par `ResetMovementModifier`).
      - `IdunBattle.Entities.Effects.Loki.StunnedEffect$$ApplyDamageModifier → 0x48f=1167 Stunned_DamageModifier, via `AddEffect(turns=0)`
        (permanent/lié au parent ; reverté par `ResetDamageModifier`).
    Les enfants portent `parent_type=1162` (lien `ParentEffect@+0x70`) ; ils n'ont pas eux-mêmes de
    sous-effets. VALIDÉ live (templSwordBrother/ThunderousAssault → tyranTyrantGuard).

    `get_CanBeImmuneTo` = **true** (#175-r2) : la classe SURCHARGE le slot 59 avec le corps trivial
    `b0 01 c3` (`mov al,1 ; ret`). Une unité `UnitTrait.Immune` refuse donc le composite 1162 au
    gate de POSE d'`IdunBattle.Operations.AddEffectOperation$$Execute` — donc AUSSI ses trois
    sous-effets, qui ne sont spawnés que par l'`ApplyInternal` du parent."""

    can_be_immune_to = True                          # `get_CanBeImmuneTo` -> `b0 01 c3`

    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        return [
            # #270-r4 : l'id ET le nom viennent du MEME membre -- le 2e argument etait deja le
            # nom d'`EffectType`, l'ordinal ne faisait que le repeter en clair.
            SubEffectSpec(int(EffectType.Stunned_CantUseAbility),              # 0x48d
                          EffectType.Stunned_CantUseAbility.name, turns=SAME_TURNS),  # AddSubEffectWithSameTurns
            SubEffectSpec(int(EffectType.Stunned_MovementOverride),           # 0x48e
                          EffectType.Stunned_MovementOverride.name, turns=0),  # AddStatOverrideEffect (cond. mvt>0)
            SubEffectSpec(int(EffectType.Stunned_DamageModifier),             # 0x48f
                          EffectType.Stunned_DamageModifier.name, turns=0),   # AddEffect turns=0
        ]


class StunnedDamageModifierEffect(BaseEffect):
    """`Stunned_DamageModifierEffect` (enfant 0x48f=1167 du composite Stunned, posé par
    `IdunBattle.Entities.Effects.Loki.StunnedEffect$$ApplyDamageModifier` = DSL `AddEffect(0x48f)`) — le malus de DÉGÂT
    SORTANT du porteur stunné (#29 lead 2, la pièce ×0.5 du miss 777 s15).

    `IdunBattle.Entities.Effects.Loki.Stunned_DamageModifierEffect$$CreateEffectDamageMalusForDefense` : `EffectBonus.ForPercentDecrease(
    get_OwnerIsActor, EffectConfig(2))`. ⚠ Le hook natif est le SLOT DÉFENSE mais son trigger est
    **OwnerIsActor** (pas OwnerIsTarget) : le malus s'applique quand le PORTEUR est l'ACTEUR du coup
    (la boucle défense native est state-wide, le trigger route). Mapping port fidèle = la boucle
    ATTAQUANT (`create_effect_damage_bonus_for_attack`), qui n'itère que les effets de l'attaquant =
    OwnerIsActor par construction. Aucun autre gate (tous profils, normale ET spéciale, prédiction
    ET combat — le natif l'inclut dans l'oracle décision : mesuré aiPlaybookPredict s15).

    MAGNITUDE `EffectConfig(2)` = entrée BC `Effect.StunnedDmgReductionPct` (=50) — table
    `BattleConfiguration.Effect` (`EffectConfigAmount`, cf. `bc_effect_config`), PAS une var
    d'ability. VALIDÉ BIT-EXACT (777 s15, u83 admecDominus stunné -> u87 custoVexilusPraetor) :
    1607-3213 pré-mods × 0.8 (MartialKatah) × 0.5 (CE malus) × 0.34 (VexillaMagnifica) = 219-437
    == natif. Runner offline : l'enfant est matérialisé par `StunnedEffect.sub_effects_on_apply`
    -> le combat offline porte le malus dès la pose du stun (même canal)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        pct = bc_effect_config("StunnedDmgReductionPct", 50)   # EffectConfig(2) — BC Effect section
        if not pct:
            return None
        return for_percent_decrease(True, abs(int(pct)))

    # #437-r1-r1-r1 -- LA DIVERGENCE DANS L'AUTRE SENS, et c'est elle qui interdit toute regle
    # « effet du defenseur -> face defenseur ». Le natif implemente ici le slot DEFENSE
    # (`CreateEffectDamageMalusForDefense`, methods.tsv) : sa contribution part donc dans
    # `defenseModifiers`, MEME si l'effet est porte par l'ATTAQUANT (trigger `OwnerIsActor`, comme
    # la docstring ci-dessus le lisait deja). Le port l'evalue par la boucle ATTAQUANT parce que
    # c'est la seule qui balaie les effets de l'attaquant -- l'evaluation reste juste, seule
    # l'ATTRIBUTION D'ACCUMULATEUR change. CONSEQUENCE ARITHMETIQUE REELLE (canal POURCENT).
    ATTACK_BONUS_NATIVE_FACE = "defender"


class ActOfFaithBuffEffect(BaseEffect):
    """`ActOfFaithBuffEffect` (effet 0x3f9=1017, namespace `Effects.Loki`) — buff de crit empilable du
    trait ActOfFaith (Adepta Sororitas).

    C'est un effet **StatModification** (mute GetStat), PAS un modifier calc-time :
      - `IdunBattle.Entities.Effects.Loki.ActOfFaithBuffEffect$$ApplyModification : deux `ChangeStat` sur le porteur —
          crit-chance (`Position(9,5)`)  += `actOfFaithExtraCritChance` (=10) **FLAT** (la valeur
            observable get_CurrentValue plafonne à 100 via GetClampedValue) ;
          crit-damage (`Position(10,5)`) += `Ceiling(GetStat(10=critDmg, part=3) × actOfFaithExtraCritDmgPct%
            =25%)` où `part=3` = la stat de **BASE** (IdunBattle.Entities.Components.StatComponent$$GetStatPart → offset 0x48, SANS
            modifications) ⇒ boost **FLAT** sur la crit-dmg hors-ActOfFaith (PAS compound). Confirmé live :
            3 stacks base 250 → +63 plat à chaque fois (250->313->376->439).
      - `IdunBattle.Entities.Effects.Loki.ActOfFaithBuffEffect$$RevertInternal : annule les deux ChangeStat (delta natif stocké @+0xb8).

    Posé par `ActOfFaithAbility` (trigger mort/kill d'allié Imperial), retiré — TOUS les stacks — par
    `ActOfFaith_RemoveEffectAbility` au crit du porteur. La mutation de stat est faite par le TRIGGER
    (`operations.triggers`), PAS ici : ctx.crit_chance/crit_damage sont déjà effet-inclusifs (GetStat) →
    ne PAS contribuer aux hooks calc-time crit (sinon double-compte). Cette classe ne porte que les DELTAS
    appliqués par CE stack (`cc_delta`/`cd_delta`), pour un revert exact (l'addition compound est
    ordre-dépendante à l'aller, mais le revert = simple soustraction des deltas stockés, donc exact).

    ⚠ Un stack SEEDÉ depuis un snapshot live (déjà fondu dans ctx) ne connaît pas ses deltas (0 par
    défaut) : un reset de stacks seedés ne re-baisse pas la stat. Le chemin VALIDÉ accumule depuis 0
    (deltas exacts) ; le seeding mid-accumulation est un edge case documenté."""
    cc_delta: int = 0   # delta crit-chance OBSERVÉ par CE stack (info/report)
    cd_delta: int = 0   # delta crit-damage OBSERVÉ par CE stack (info/report)
    stat_mod_source = None   # clé de source ChangeStat (revert par-source via UnitStats.revert_stat)
    # Cet effet applique un stat-mod FRAIS à CHAQUE pose (accumulation) → la feuille `AddEffect` /
    # `AddEffectOperation` NE doit PAS le no-op sur « déjà présent » (contrairement à Fire/Pinned/Stunned
    # updatable qui refresh). RE slice-20 (Q3) : `IsUpdatable(1017)`=TRUE par fallback, mais chaque proc
    # a une source/évènement distinct → le natif STACKE (observable live-validé : 3 stacks +63 plat chacun).
    # On reproduit l'observable additif via N instances (chacune son `stat_mod_source`), pas via le compteur
    # `UpdateExistingEffect@0x6c` (source-matching natif non porté — divergence de représentation flaggée
    # validator, observable IDENTIQUE).
    stacks_stat_mod_on_add = True

    def applied_stat_mods(self, stats_ctx) -> "list":
        """`IdunBattle.Entities.Effects.Loki.ActOfFaithBuffEffect$$ApplyModification` (part DATA côté `entities/`, mirror des DEUX
        `ChangeStat` — symétrique de `reverted_stats()`). La couche runner (`AddEffectOperation._apply_stat_mods`)
        EXÉCUTE chaque `(StatType, montant)` via `apply_change_stat`, keyé par une source unique par instance
        (revert par-source exact via la feuille `RemoveEffect`). Deux stat-mods FLAT de CE stack :
          - crit-chance (`Position(9,5)`)  += `actOfFaithExtraCritChance` (GetNumberConstant 0x30=48, =10) ;
            la valeur observable get_CurrentValue plafonne à 100 (clamp fait par `apply_change_stat`) ;
          - crit-damage (`Position(10,5)`) += `Ceiling(GetStat(critDmg, part=3=Initial) × actOfFaithExtraCritDmgPct
            (0x31=49, =25)%)` FLAT (base hors-ActOfFaith → boost PLAT, PAS compound ; live : 3 stacks +63 plat).
        `stats_ctx` = le `StatsComponent.ctx` du porteur (duck-typé : `.stats.components`/`.stats.get_stat`,
        fallback `.crit_damage` si le composant crit-dmg n'est pas seedé)."""
        cc = int(global_value("actOfFaithExtraCritChance") or 0)   # GetNumberConstant 0x30 (=10)
        cd_pct = int(global_value("actOfFaithExtraCritDmgPct") or 0)   # GetNumberConstant 0x31 (=25)
        if int(StatType.CRIT_DAMAGE) in stats_ctx.stats.components:
            base_cd = stats_ctx.stats.get_stat(int(StatType.CRIT_DAMAGE), int(StatPart.INITIAL))
        else:
            base_cd = int(getattr(stats_ctx, "crit_damage", 0) or 0)
        cd_amount = -(-(base_cd * cd_pct) // 100)                 # Ceiling(base_cd × cd_pct%) entier (0.25 exact)
        return [(int(StatType.CRIT_CHANCE), cc), (int(StatType.CRIT_DAMAGE), cd_amount)]

    def reverted_stats(self) -> "list":
        """`IdunBattle.Entities.Effects.Loki.ActOfFaithBuffEffect$$RevertInternal` annule les DEUX `ChangeStat` de CE stack :
        crit-chance (Position(9,5)) + crit-damage (Position(10,5)). Ces StatTypes sont lus par la feuille
        `RemoveEffect` (runner) pour `revert_change_stat(…, stat_mod_source)` par-source."""
        return [StatType.CRIT_CHANCE, StatType.CRIT_DAMAGE]


class ThrillSeekersEffect(BaseEffect):
    """`ThrillSeekers` / « Thrilled » (effet 0x59a=1434) — buff CRIT_CHANCE a TIMER du trait
    `UnitTrait.ThrillSeekers` (1056, x5 Emperor's Children).

    ARTEFACT NATIF : il n'y a PAS de classe d'effet dediee — l'entite-effet est un
    `IdunBattle.Entities.Effects.StaticStatModifierEffect` generique, INSTANCIE par la feuille
    `IdunBattleLogic.Entities.DSLFactory$$AddStaticStatModifierEffect` de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ThrillSeekersAbility$$CreateBehaviour` :
    `AddStaticStatModifierEffect(Owner@0x148, 0x59a, statType 9 = CRIT_CHANCE,
     Get(AbilityConfiguration.GetNumberConstant(cfg, 0x30 = extraCritChance)),
     TurnsFromRounds(GetNumberConstant(cfg, 0x45 = nrOfRounds)), 0)`.
    Le couple (stat, montant) est donc BAKE dans le `StatModificationComponent` de l'entite-effet :
    `IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat` = champ `+0x10`,
    `IdunBattle.Entities.Effects.StaticStatModifierEffect$$GetStatModificationAmount` = champ `+0x14`.

    POURQUOI CETTE CLASSE EXISTE COTE PORT (#118) : `decisionView.effects` n'expose NI le stat NI le
    montant d'un effet capte (cf. `frida/hooks/game/effects.ts` : EffectType/remaining/level/source
    seulement). Un `Thrilled` DEJA ACTIF au chargement d'un `State` arrivait donc sans stat-modification
    declaree -> son +15 restait dans le RESIDU OPAQUE (`CAPTURED_SOURCE`) de `seed_unit_stats`, sans
    aucune `ValueModification` attribuee, donc **non retirable** : l'expiration offline gardait le bonus
    a vie alors que le live le retire (`AStatModifierEffect$$RevertModification`). En declarant ici le
    couple (stat, montant) — RE-DERIVE de la MEME source que le natif, la config d'ability exposee cote
    client sur le trait — l'attribution du seed (`stat_modifications_by_source`) pose la contribution
    par-source et l'expiration la reverte.

    MAGNITUDE : `GetNumberConstant(cfg, 0x30)` == gameconfig `traits.ThrillSeekers.variables.
    thrillSeekersExtraCritChance` (=15) — une CONSTANTE d'ability, donc NON scalee par
    l'`AbilityVariablesMultiplierPercentage` de l'unite (meme lecture que
    `runner/operations/triggers/loki/thrill_seekers.py::thrill_seekers_extra_crit_chance`, source unique).
    0/absent -> aucune contribution (no-op fidele plutot qu'une magnitude inventee)."""

    def get_stat_modification_stat(self) -> int | None:
        return StatType.CRIT_CHANCE                                     # StatType.CRIT_CHANCE (statType du CreateBehaviour)

    def get_stat_modification_amount(self) -> int | None:
        return trait_var("ThrillSeekers", "thrillSeekersExtraCritChance")


class TauntedEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal (effet COMPOSITE 27 = `Taunted_OnlySpecificTargets`,
    base `ABondEffect` — lien cible↔tauntant). À l'application, spawne 3 SOUS-effets via
    `AddSubEffectWithSameTurns` (⇒ MÊME durée que le parent) :
      - 0x19=25  `Taunted_BlockMovement`        (la cible ne peut plus se déplacer)
      - 0x1a=26  `Taunted_CantUseAbility`        (la cible ne peut plus utiliser d'ability active)
      - 0x4d5=1237 `Taunted_RefreshUnitTurnFinished`
    La QUEUE d'`ApplyInternal` écrit en plus la liste de cibles d'attaque FORCÉES de la cible
    (#436, relu VERBATIM sur `rnca9r7q6c`) :

        comp = target.GetComponent<ForcedAttackTargetsComponent>();
        list = new List<int>(); list.Add(ABondEffect.BondedEntityId(this, effect));
        comp.<+0x50> = list;                                  // REMPLACE

    et `IdunBattle.Entities.Effects.TauntedEffect$$RevertInternal` la VIDE
    (`comp.<+0x50> = new List<int>()`). C'est CE canal — et lui seul — qui rend le taunt opposable
    au ciblage : `IdunBattle.Entities.UnitExtensions$$GetOnlyTargets` le relit, et la règle
    `TargetIsAllowedForCaster` (bit 23) du filtre statique
    (`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`, surcharge 7 arguments)
    REFUSE toute cible qui n'y figure pas. La note antérieure « concern playbook, non porté ici »
    sous-estimait la portée : ce n'est pas un biais d'IA, c'est un GATE de légalité de cast, qui
    vaut aussi pour l'ATTAQUE NORMALE (masque `0x4002`, donc `TargetIsEnemy` -> règle ARMÉE).

    VALIDÉ live attendu : la cible porte 27 + 25/26/1237 (parent 1 round, enfants same-turns) après
    CrushingClaws.

    `get_CanBeImmuneTo` = **true** (#175-r2) : la classe SURCHARGE le slot 59 avec le corps trivial
    `b0 01 c3` (`mov al,1 ; ret`). Une unité `UnitTrait.Immune` refuse donc le composite 27 au gate
    de POSE — et avec lui les trois sous-effets ET l'écriture de `ForcedAttackTargetsComponent`,
    puisque tout cela vit dans l'`ApplyInternal` du parent."""

    can_be_immune_to = True                          # `get_CanBeImmuneTo` -> `b0 01 c3`
    # #982-r4 -- `IEffect` slot 3 `get_KeepOnChangeOwner` -> `32 c0 c3` (`xor al,al ; ret`) = FAUX.
    # `TauntedEffect` est l'une des DEUX SEULES classes du build (sur 465) a surcharger ce getter :
    # a la prise de controle, `ChangeUnitOwnerOperation$$RemoveEffects` PURGE le taunt.
    keep_on_change_owner = False
    # #1088 -- `IEffect` slot 4 `get_RemoveOnDeathStep` -> `b8 02 00 00 00 c3` = `AfterDeathTrigger`.
    # La classe SURCHARGE le defaut `AfterUnitRemove` de `BaseEffect` : le taunt SURVIT donc aux
    # deux premiers retraits de `KillUnitOperation$$Execute` et n'est purge qu'APRES les events
    # `On(UnitDeath)` / `On(UnitDefeated)`. C'est ce que le natif exige pour qu'un trigger sur la
    # mort puisse encore LIRE le taunt du mourant -- mesure live #911-r1 : `DaemonicPatrons` se
    # re-arme sur un kill de cible TAUNTEE, ce qui suppose `HasEffect(Target, 27)` vrai a
    # `On(UnitDefeated)`. Le port retirait ce composite au tout premier step, rendant cette face
    # structurellement inerte.
    remove_on_kill_step = KillUnitStep.AfterDeathTrigger

    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        return [
            # #270-r4 : idem -- id et nom derivent du meme membre d'`EffectType`.
            SubEffectSpec(int(EffectType.Taunted_BlockMovement),                # 0x19
                          EffectType.Taunted_BlockMovement.name, turns=SAME_TURNS),   # AddSubEffectWithSameTurns
            SubEffectSpec(int(EffectType.Taunted_CantUseAbility),               # 0x1a
                          EffectType.Taunted_CantUseAbility.name, turns=SAME_TURNS),  # AddSubEffectWithSameTurns
            SubEffectSpec(int(EffectType.Taunted_RefreshUnitTurnFinished),      # 0x4d5
                          EffectType.Taunted_RefreshUnitTurnFinished.name, turns=SAME_TURNS),
        ]

    def writes_forced_attack_targets(self) -> bool:
        """Queue d'`ApplyInternal` (cf. la docstring de classe) : la liste de cibles forcées de la
        cible devient `[BondedEntityId]`."""
        return True


class PinnedEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.PinnedEffect$$ApplyInternal (effet 1065 `Pinned` ; UI = « Suppressed »). Effet
    stat-mod SIMPLE (pas de sous-effet nommé) : un `ChangeStat(Position(1,5), statType=4 = Movement,
    valeur = Negative(EffectConfig(1)))` sur la cible ⇒ réduit le MOUVEMENT (la cible « pinned » ne peut
    pas avancer le tour suivant). `EffectConfig(1)` = BC `Effect.PinnedMovementReduction` (mapping
    ordinal→champ DTO prouvé par `IdunBattle.Core.Services.BattleQuery$$InitEffectConfig` : +0x10→0, +0x14→1, +0x1c→2, ... —
    recoupé par Stunned EffectConfig(2)=StunnedDmgReductionPct bit-exact).

    MALUS DE DÉGÂT ATTAQUANT (#57b, famille ×0.70 du batch #52) : `IdunBattle.Entities.Effects.Loki.PinnedEffect$$CreateEffectDamageBonusForAttack` = `EffectBonus.ForPercentIncrease(get_OwnerIsCaster, Negative(EffectConfig(0)))` —
    quand le PORTEUR attaque, son dégât est réduit de `EffectConfig(0)` = BC
    `Effect.PinnedDmgReductionPct` (=30) ⇒ ×0.70. Trigger OwnerIsCaster == boucle ATTAQUANT du port
    (même mapping que Stunned_DamageModifier ci-dessus). Aucun autre gate (mêlée ET ranged, tous
    profils). GROUND TRUTH : 54321 s16 u81 bloodIntercessor Pinned -> t89, natif 2192/3288 =
    off 3132/4698 × 0.700 EXACT (probe_57b_x070.py).

    « cannot be Suppressed » (#224 → #208) — CE N'EST PAS UNE IMMUNITÉ DE POSE. Le SEUL artefact natif
    qui nomme le couple `TerminatorArmour` ↔ `Pinned` est
    `IdunBattle.Entities.Effects.Loki.PinnedEffect$$CreateActiveCondition` =
    `Not(DSLFactory.HasTrait(Self, 0x40f = 1039 = UnitTrait.TerminatorArmour))` (i2 TerminatorArmour :
    « This unit cannot be Suppressed »), et il est porté par `is_active` ci-dessous — PAS par le gate
    d'immunité, qui n'a jamais rien refusé ici.

    MESURE DIRECTE 2026-07-28 (hook `frida/hooks/features/effect-immunity-observe.ts`, montage
    `sentinel` sur `blackAbaddon`) : `IdunBattle.Operations.AddEffectOperation$$Execute(1065)` **est
    appelé et n'abandonne PAS** (valeur de retour NON nulle ⇒ l'entité-effet EST allouée), et
    `IdunBattle.Entities.Effects.BaseEffect$$EntityIsImmuneToEffect` y rend **`false`** avec
    `HasTrait(cible, 0x19 = Immune)` **faux**. Le natif POSE l'effet et le laisse INERTE via
    l'`ActiveCondition`, évaluée par `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive`
    qui écrit `EffectComponent.IsActive @+0x5c`. Recoupement indépendant : `decisionView` DROPPE les
    effets dont `IsActive` est faux (`readEffectsByUnit`, `frida/hooks/game/effects.ts`) — d'où
    l'absence de 1065 sur la cible ; avec `includeInactive: true`, l'effet EST publié, `active: false`.
    La lecture « refus de pose » de #224 venait d'une inférence fautive : un effet inactif n'émet
    aucun groupe d'événement, donc l'absence d'événement ne distingue pas « pas posé » de
    « posé et inerte ».

    `get_CanBeImmuneTo` reste **true** (vtable runtime) : la branche générique
    `HasTrait(Immune) && CanBeImmuneTo` de la base mord bel et bien pour cet effet — c'est le trait
    `Immune` (0x19), PAS `TerminatorArmour`. Aucune surcharge d'`EntityIsImmuneToEffect` n'existe pour
    `PinnedEffect` dans le binaire (`search_symbols_by_name EntityIsImmuneToEffect` = 2 corps :
    `BaseEffect` et `ContaminatedEffect`) — donc aucune ici non plus (#208 : le collapse est DÉFAIT).

    ⚠ Contribution NON portée restante (présent ≠ appliqué, §17.4) : la réduction de Movement
    (le mouvement n'est pas dans le chemin de combat/dégât porté)."""

    can_be_immune_to = True                          # `get_CanBeImmuneTo` -> stub partagé `return 1`

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        """`IdunBattle.Entities.Effects.Loki.PinnedEffect$$CreateActiveCondition` = `Not(HasTrait(
        Self, 0x40f = TerminatorArmour))` — mirror LITTÉRAL, et le SEUL porteur du « cannot be
        Suppressed ». L'effet EXISTE sur un porteur `TerminatorArmour` (`has_effect` vrai, comme le
        natif) mais ne contribue à RIEN : `EffectsState.active_effects` l'exclut, donc ni le ×0.70
        ci-dessous ni aucune autre lecture d'effet actif ne le voit.

        `unit_state` sans clé `traits` ⇒ traits inconnus ⇒ actif — mirror du `HasTrait` faux sur une
        entité sans composant d'unité. ⚠ C'est une dégradation PERMISSIVE : tout appelant runner doit
        passer `components.unit_state_for_effects(state, uid)` (foyer unique, #208), et la face
        prédiction `Scene.unit_state(uid)`. Un `{"hp": ...}` ad hoc réintroduirait le ×0.70 fantôme."""
        return not has_trait((unit_state or {}).get("traits"), UnitTrait.TerminatorArmour)

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        pct = bc_effect_config("PinnedDmgReductionPct", 30)   # EffectConfig(0) — BC Effect section
        if not pct:
            return None
        # ForPercentIncrease(Negative(pct)) natif == percent-decrease de pct (1 - pct/100).
        return for_percent_decrease(True, abs(int(pct)))


class MV71InitialDmgEffect(BaseEffect):
    """`MV71SniperDroneSquad_InitialDmgEffect` (effet **1132=0x46c**, posé sur le DRONE par
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour` — `AddEffect(0x46c, stateRef,
    Get(drone))`, source = le CASTER Sho'syl = le PARENT du drone).

    `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ApplyInternal` : `parent = GetParentUnit(drone)` puis `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ApplyStat` sur
    **4 stats — 0 ATTACK, 9 CRIT_CHANCE, 10 CRIT_DAMAGE, 0x11 EXTRA_HITS** : chaque `ApplyStat` lit
    `GetStat(parent, stat, CURRENT)` (SNAPSHOT au moment de l'apply, nœud `Direct(valeur)`) et émet
    `ChangeStat(drone, Position(stat, part 7 = OVERRIDE), mode 4, Direct(valeur))` → `IdunBattle.Entities.Components.StatComponent$$ApplyModifier` case 7 → `IdunBattle.Entities.Components.ValueOverride$$SetOverride` (**modifiable** : les buffs PROPRES du drone
    continuent de s'appliquer par-dessus — i2 « uses Sho'syl's Damage stat, while other effects,
    like buffs, are taken from the Drone »). `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$RevertInternal` = `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ResetStat`
    ×4 (part 8 = REMOVE_OVERRIDE).

    Cycle de vie : `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$CreateTargetTrigger` = `On(AttackDamageAttack=10, 1) & OwnerIsCaster`
    → l'effet est retiré (RevertInternal) dès que le DRONE porte une attaque — l'attaque COMMANDÉE du
    cast (GT §2 case-61bis : après le cast, le drone ne porte plus que RangedSpecialist). Côté port,
    la consommation+revert est exécutée par l'ability juste après l'attaque commandée (seul On(10)
    du porteur atteignable dans ce cast — collapse documenté)."""

    def overridden_stats(self) -> "list":
        return [StatType.ATTACK, StatType.CRIT_CHANCE, StatType.CRIT_DAMAGE, StatType.EXTRA_HITS]


class MV71ResetInitialDmgEffect(BaseEffect):
    """`MV71SniperDroneSquad_ResetInitialDmg` (effet **1133=0x46d**, posé sur le DRONE juste APRÈS
    1132 par le même `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour` — `AddEffect(0x46d, stateRef, Get(drone))`).

    ⚠ Skew de nommage ARBITRÉ (#61bis §6) : le `.ctor` ghidra passant `0x46d` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.CyclicIonBlaster_AdditionalHitsEffect$$.ctor,
    « CyclicIonBlaster_AdditionalHitsEffect ») passe en réalité `AbilityOrEffect(TriggeredAbilityType.
    CyclicIonBlaster = 1133)` — l'ATTRIBUTION SOURCE de l'effet CyclicIonBlaster (EffectType 1148),
    PAS un EffectType. L'enum EffectType du dump (1133 = MV71SniperDroneSquad_ResetInitialDmg) est
    la bonne lecture du `AddEffect(0x46d)` de l'arbre MV71.

    Rôle : effet-compagnon du reset — retiré AVEC 1132 après l'attaque commandée du drone (GT : ni
    1132 ni 1133 présents post-cast). Aucun comportement observable propre lu dans le décompilé →
    matérialisation pure (présence + retrait), pas de contribution."""


class BlackRageExtraMoveEffect(BaseEffect):
    """`BlackRage_ExtraMove` (EffectType 0x53e=1342) — buff **StatModification** +MOUVEMENT, SELF-buff
    posé par `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$ExecuteBehaviour` via `AddStaticStatModifierEffect(caster@0x160,
    1342, stat=MOVEMENT(1), amount=ConfigConst(0xe=extraMovement))`. AUCUNE classe d'effet native bespoke
    (StaticStatModifierEffect générique — cf. `IdunBattleLogic.Entities.DSLFactory$$AddStaticStatModifierEffect`) : ici on porte le
    stat-mod EAGER (chemin runner `AddEffectOperation._apply_stat_mods` -> `apply_change_stat`, keyé par
    source) = +`extraMovement` (constante gameconfig = 1) à la stat MOVEMENT.

    VALIDÉ live (statModSources 31337) : movement total=1, bySource=[{source=effet 98, amount=1}]. Reverte
    MOVEMENT au retrait (`reverted_stats`, symétrique via la feuille `RemoveEffect`)."""

    def applied_stat_mods(self, stats_ctx) -> "list":
        amt = ability_var("BlackRage", "extraMovement", is_constant=True)   # ConfigConst(0xe) = 1
        return [(int(StatType.MOVEMENT), int(amt))] if amt else []

    def reverted_stats(self) -> "list":
        return [StatType.MOVEMENT]


class BlackRageExtraDamageEffect(BaseEffect):
    """`BlackRage_ExtraDamageEffect` (EffectType 0x53f=1343 ; `IdunBattle.Entities.Effects.Loki.BlackRage_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`)
    — posé sur le caster (self) par `ExecuteBehaviour` via `AddEffect(1343, caster@0x160)`. MIRROR 1:1 du
    décompilé (ordre de lecture natif : `get_OwnerIsCaster`, `op_BitwiseAnd(IsCharging(factory+0x160,
    factory+0x178))`, `op_BitwiseAnd(IsNormalAttack)`, puis `ForAddition(cond, ConfigVar(8, GetAbilityState,
    effet+0x60))`) :

        EffectBonus.ForAddition( get_OwnerIsCaster & IsCharging(caster, target) & IsNormalAttack,
                                 ConfigVar(8 = extraDmg, GetAbilityState(this), config@this+0x60) )

    = +`extraDmg[level]` x multiplier au dégât de l'attaque NORMALE de CHARGE du porteur (le coup qui suit
    le `MoveUnit` du MÊME cast). Canal additif `@+0x10` (`IdunBattle.Core.Services.DamageModifiers$$Add`),
    appliqué PAR COUP — identique aux deux jumeaux `AvalancheOfMuscle_ExtraDamage` (1025) et
    `FeederTendrils_ExtraDamage` (1197), avec lesquels il partage EXACTEMENT le nœud `IsCharging`
    (xrefs de `IdunBattleLogic.Entities.DSLFactory$$IsCharging` : ces trois `CreateEffectDamageBonusForAttack`
    et aucun autre — `SmashaEadEffect$$…` n'en a PAS, contrairement à ce qu'affirmaient les fiches).

    MARQUEUR porté (présent/diffable) — la CONTRIBUTION +extraDmg reste NON modélisée. Case-r32 a levé
    l'UNE des deux objections historiques et REMPLACÉ l'autre par un bloqueur MESURÉ :

    * ❌ « magnitude NÉGLIGEABLE, extraDmg[L] = [10, 12, 14, …] » — **FAUX**, c'était la tête du tableau.
      Gameconfig relu : `extraDmg[1] = 10`, **`[50] = 554`**, **`[65] = 728`** ; à multiplier 180 % cela
      fait **997 par coup**, soit ~4 000 sur l'attaque 4 coups de Lucien. L'argument tombe.
    * ✅ « le gate `IsCharging` n'est pas exprimable dans le canal modifier EAGER » — **levé** : il l'est
      désormais per-coup (`is_not_charging(att_ctx)`, foyer `effects/base.py`), et c'est précisément lui
      qui empêcherait la sur-application aux attaques hors-charge que cette note redoutait.
    * ⛔ BLOQUEUR RÉEL, mesuré le 2026-07-28 en tentant le port : l'effet 1343 **arrive au niveau ~1**.
      Le vecteur de pose (`AddEffect(1343, caster)` du `black_rage_tree`) ne propage NI
      `active_ability_level` NI `ability_level` depuis la source. Contribution offline obtenue : **18 par
      coup** (`extraDmg[1] = 10 x 180 %`) au lieu de 997 — A/B live, delta de PV de la cible
      `off(+charge) − off(−charge) = 52` sur 4 coups là où le port juste vaudrait ~3 900. Livrer le canal
      dans cet état produirait une valeur FAUSSE, pas une valeur manquante : on s'abstient.
      Débloqueur = le `scale_from_source` du vecteur de pose (cf. `runner/abilities/behaviours/effects.py
      ::_source_scaling`, déjà utilisé par `Waaagh_ExtraDamage` 1100), PAS ce fichier.

    Second écart croisé au passage sur le MÊME vecteur, non lié au canal dégât : le `SetHealth(30 % de
    MaxHealth)` du cast rend **56 871 live vs 60 000 offline** (⇒ `hp_max` 189 570 live vs 200 000
    offline sur un état rechargé par `load_state`). Il rend ce vecteur non bit-exact tant qu'il tient.

    Le natif, pour mémoire (MIRROR lu, ordre de lecture exact : `get_OwnerIsCaster`,
    `op_BitwiseAnd(IsCharging(factory+0x160, factory+0x178))`, `op_BitwiseAnd(IsNormalAttack)`, puis
    `ForAddition(cond, ConfigVar(8, GetAbilityState, effet+0x60))`) :

        EffectBonus.ForAddition( get_OwnerIsCaster & IsCharging(caster, target) & IsNormalAttack,
                                 ConfigVar(8 = extraDmg, GetAbilityState(this), config@this+0x60) )

    — canal additif `@+0x10` par coup, IDENTIQUE aux deux jumeaux `AvalancheOfMuscle_ExtraDamage` (1025)
    et `FeederTendrils_ExtraDamage` (1197), avec lesquels il partage EXACTEMENT le nœud `IsCharging` (les
    xrefs de `IdunBattleLogic.Entities.DSLFactory$$IsCharging` ne donnent que ces trois
    `CreateEffectDamageBonusForAttack` — `SmashaEadEffect$$…` n'en a PAS, contrairement aux fiches).
    Source de config : `AbilityOrEffect(0x48b = 1163 BlackRage)`, comme le ctor jumeau
    `IdunBattle.Entities.Effects.Loki.BlackRage_AutomaticUnitEffect$$.ctor`. AUCUN gate melee/ranged."""


class BlackRageAutomaticUnitEffect(BaseEffect):
    """`BlackRage_AutomaticUnitEffect` (EffectType 0x540=1344 ; IdunBattle.Entities.Effects.Loki.BlackRage_AutomaticUnitEffect$$.ctor = `BaseEffect(AbilityOrEffect(
    0x48b=1163), 1)`) — posé sur le caster (self) par `ExecuteBehaviour` via `AddEffect(1344, caster@0x160)`.
    MARQUEUR pur (aucune stat-mod) : arme la triggered `BlackRage_ActivationAbility` (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BlackRage_ActivationAbility$$CreateTrigger`
    = `On(0x16) & HasEffect(self, 0x540)` -> `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BlackRage_ActivationAbility$$CreateBehaviour` = `PerformAIAction(self)`) = Lucien
    REJOUE une action (berserk Death Company « acts again »).

    Le mécanisme ACT-AGAIN (triggered `PerformAIAction` sur event 0x16) n'est PAS modélisé (RÉSIDU documenté,
    tranche triggered dédiée : nécessite le vecteur On(0x16) + un re-tour d'action offline) ; l'effet est posé
    pour le diff structurel (présent/diffable, remaining=0)."""


class WaaaghExtraMovementEffect(BaseEffect):
    """`Waaagh_ExtraMovement` (EffectType 0x44b=1099) -- buff **StatModification** +MOUVEMENT pose par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour` via
    `AddStaticStatModifierEffect(<selecteur Waaagh>, 1099, stat=MOVEMENT(1),
                                 Direct(GetNumberConstant(0xe)=extraMovement), duree=Direct(1)@dsl+0xc0)`.
    AUCUNE classe d'effet native bespoke (StaticStatModifierEffect generique, `IdunBattleLogic.Entities.DSLFactory$$AddStaticStatModifierEffect`) : on porte le stat-mod EAGER (canal `applied_stat_mods` -> `AddEffectOperation.
    _apply_stat_mods` -> `apply_change_stat`, keye par source) = +`extraMovement` (constante gameconfig = 1)
    a la stat MOVEMENT. MEME template que `BlackRageExtraMoveEffect` (1342, valide live statModSources).

    CE PORT EST REQUIS PAR L'ETAGE MOVE de Waaagh : `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetPossibleMovementTiles`
    calcule sa portee via `IdunBattleLogic.Entities.DSLFactory$$UnitMovementRangeWithBonus(caster@0x160, 1099, Direct(extraMovement))` = `If( HasEffect(caster, 1099), StatAmount(caster, MOVEMENT), Sum(StatAmount(caster,
    MOVEMENT), bonus) )` -- le natif ANTI-DOUBLE-COMPTE : quand l'effet est DEJA pose (c'est le cas, le
    Group buff @0x25 s'execute AVANT le Group move @0x23 dans l'ordre d'`Execute` de IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour), la portee
    lit la stat MOVEMENT *deja bonifiee*. Sans `applied_stat_mods`, la charge perdrait son +1 hex."""

    def applied_stat_mods(self, stats_ctx) -> "list":
        amt = ability_var("Waaagh", "extraMovement", is_constant=True)   # ConfigConst(0xe) = 1
        return [(int(StatType.MOVEMENT), int(amt))] if amt else []

    def reverted_stats(self) -> "list":
        return [StatType.MOVEMENT]


class WaaaghExtraDamageEffect(BaseEffect):
    """`Waaagh_ExtraDamage` (EffectType 0x44c=1100 ; `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraDamageEffect$$.ctor`
    = `BaseEffect(AbilityOrEffect(0x422=1058 Waaagh), 1)` -> sa config = celle de l'ability WAAAGH) -- pose
    sur le SELECTEUR Waaagh (caster + allies adjacents + TOUS les allies de faction Orks) par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour` via
    `AddEffect(0x44c, AbilityStateReference, caster@0x160, <selecteur>, duree=Direct(1)@dsl+0xc0)`.

    CANAL PORTE (#95) -- `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`,
    MIRROR 1:1 du decompile :
        `EffectBonus.ForAddition( IsNormalAttack & IsMeleeAttack & get_OwnerIsCaster,
                                  ConfigVar(8=extraDmg, GetAbilityState(effet), effet+0x60) )`
    (ordre de lecture natif : `IsNormalAttack` puis `op_BitwiseAnd(IsMeleeAttack)` puis
    `op_BitwiseAnd(get_OwnerIsCaster)`, puis `ForAddition(cond, ConfigVar(...))`).
    => +`extraDmg[niveau Waaagh du POSEUR]` PLAT (multiplier resolu = 100, cf. plus bas), PAR COUP, sur
    les attaques **NORMALES MELEE** du porteur. `OwnerIsCaster` est vrai par construction sur ce canal (il n'est appele que pour
    les attaques du porteur, cf. `_attacker_effect_bonuses`). Canal `additive @+0x10` (`DamageModifiers.Add`)
    -- MEME canal que SmashaEad/DecoysAndMisdirection/LordOfTempests.

    NIVEAU = celui du POSEUR : `IdunBattle.Entities.Formulas.ConfigAmount$$GetAbilityState` resout le
    selecteur `AbilityStateFromEffect` (-> `EffectComponent.AbilityState` = {Owner=le Warboss,
    Ability=1058, Nullable<AbilityState> **VIDE** -- MESURE live `effectAbilityStates(1100)` :
    stateRaw=[81,1,1058,0,0,0,...]}) puis le passe au slot 0xd4 du `BattleQuery` -> l'AbilityState de
    l'ability 1058 de son OWNER. Cote port : le vecteur de pose passe `scale_from_source=True`
    (`runner/abilities/behaviours/effects.py::_source_scaling`) -> `active_ability_level` de la SOURCE.

    MULTIPLIER = **100** (aucun scaling de rarete), MESURE LIVE -- ne PAS passer celui du porteur ni
    celui du caster. `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`
    applique bien `Round(value x AbilityState.VariableMultiplierPercentage/100)` quand la cle est dans
    `variablesAffectedByRarityBonus` (c'est le cas d'`extraDmg`) : c'est donc le MULTIPLIER RESOLU qui
    vaut 100 ici. GROUND TRUTH (probe_95_waaagh_contrib, MC1_67 seed 31337, Warboss L50 mult 200,
    beneficiaire orksNob mult 180) : la contribution mesuree par la preview NATIVE (`aiPredict` ->
    `GetAllPredictions`) est **+443 par coup**, EXACTEMENT `extraDmg[L50]=443` BRUT --
    ni x200 % (=886, multiplier du caster) ni x180 % (=797, multiplier du porteur). Le facteur 200 est
    d'ailleurs arithmetiquement REFUTE : 443 est impair, aucun `extraDmg[L]` x2 ne le produit.
    (Meme famille que le gap #68/#75 « multiplier COMBAT d'un additif d'effet » -- ici MESURE, pas
    suppose.)

    PAS de gate `is_prediction` (contrairement a SmashaEad #71) : le calque est `CrushingStrikeEffect`
    (meme couple `IsNormalAttack & IsMeleeAttack`), et la contribution est MESUREE PRESENTE dans la
    preview native (face prediction) -- cf. GROUND TRUTH ci-dessus.

    #106 (fork `IsMeleeAttack`) : le gate melee lit `is_melee_attack(is_ranged)` = `is_ranged is False`
    (mirror `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack`) -- nature NON prouvee melee => AUCUNE
    contribution, EXACTEMENT comme le canal COUPS jumeau 1101 (`att_ctx["is_melee"] is not True`). Les deux
    canaux natifs portent la MEME condition (`IsNormalAttack & IsMeleeAttack & get_OwnerIsCaster`) : ils
    doivent donc se taire ENSEMBLE. L'ancien `if is_ranged:` (None FALSY) appliquait le +extraDmg aux coups
    de nature non threadee (vecteur `execute_normal_like` : splash Psyker RANGED, attaque on-appearance de
    summon) -- corrige a la SOURCE (la facade threade desormais la nature) + ici (defaut fidele)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: "bool | None" = None,
                                              has_moved: "bool | None" = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: "bool | None" = True,
                                              target_armor_reduced: "bool | None" = None,
                                              att_ctx=None) -> "EffectBonus | None":
        if not is_melee_attack(is_ranged):   # IsMeleeAttack (IdunBattleLogic.Entities.DSLFactory$$IsMeleeAttack)
            return None                      # #106 : nature NON prouvee melee -> gate FAUX (mirror BattleQuery)
        if is_normal_attack is False:        # IsNormalAttack (IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack)
            return None
        # ConfigVar(8=extraDmg, GetAbilityState(effet)) : NIVEAU du poseur, multiplier RESOLU = 100
        # (mesure live +443 = extraDmg[L50] brut ; cf. docstring). `multiplier_pct` laisse a 100.
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("Waaagh", "extraDmg", lvl)
        return for_addition(True, int(amt)) if amt else None


class WaaaghExtraHitsEffect(BaseEffect):
    """`Waaagh_ExtraHits` (EffectType 0x44d=1101) -- pose sur le MEME selecteur que 1100 par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour` (`AddEffect(0x44d, ..., duree=Direct(1)@dsl+0xc0)`).

    CANAL PORTE (#95) -- `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`,
    MIRROR 1:1 du decompile (JUMEAU EXACT du canal degat 1100, meme condition, autre magnitude) :
        `EffectBonus.ForAddition( IsNormalAttack & IsMeleeAttack & get_OwnerIsCaster,
                                  ConfigConst(0x2b=extraHit, effet+0x60) )`
    => **+extraHit coup** (CONSTANTE gameconfig Waaagh = 1, NON rarity-scalee -- `GetNumberConstant`, cf.
    `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` branche constante) sur les attaques **NORMALES
    MELEE** du porteur. Canal `CreateEffectHitsBonusForAttack` = axe COUPS attaquant
    (`entities.effects.hits_bonus_from_effects` -> `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate`),
    exactement comme `PowerTrip_FullHealthEffect` (dont le gate est `IsNormalAttack & OwnerIsCaster`, SANS
    le `IsMeleeAttack` d'ici).

    `is_melee` vient de l'`att_ctx` (= le `board` de la formule de coups, peuple par les DEUX facades :
    combat `damage_model.build_hits_board` et prediction `playbook/prediction/normal_attack.py`) ;
    contexte ABSENT / nature inconnue -> pas de contribution (degradation fidele « present != applique »)."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> "EffectBonus | None":
        if not is_normal_attack:             # IsNormalAttack (IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack)
            return None
        # IsMeleeAttack (IdunBattleLogic.Entities.DSLFactory$$IsMeleeAttack) : la nature du coup est portee par
        # l'att_ctx (board de la formule). None/absent = inconnu -> aucune contribution.
        if (att_ctx or {}).get("is_melee") is not True:
            return None
        n = ability_var("Waaagh", "extraHit", is_constant=True)   # ConfigConst(0x2b) = 1
        return for_addition(True, int(n)) if n else None


class HammerOfWrathConditionalDamageEffect(BaseEffect):
    """`HammerOfWrath_ConditionalDamage` (effet 0x534=1332, classe native
    `IdunBattle.Entities.Effects.Loki.HammerOfWrath_ConditionalDamageEffect` -- base `BaseEffect`,
    source `AbilityOrEffect 0x481` = HammerOfWrath, lu dans son `$$.ctor`).

    POSE : owner-effect PERMANENT ajoute au PORTEUR a l'INIT de l'ability, par la triggered 1258
    (`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour` =
    `If(<cond>, AddEffect(effectType, AbilityState(owner, abilityType), owner, owner, <duree ZEROE>))`,
    trigger `IdunBattleLogic.Entities.DSLFactory$$OnOwnerSpecificAbilityInit`). Cote port :
    `ABILITY_INIT_OWNER_EFFECTS["HammerOfWrath"]` (meme mecanisme que `AnvilShield`).

    ACTIVE-CONDITION -- `IdunBattle.Entities.Effects.Loki.HammerOfWrath_ConditionalDamageEffect$$CreateActiveCondition` :
        HealthPctIsBelowOrEqual( Self@0x148, ConfigConst(0x481 = 1153, Self, 0x4f = healthPct) )
    ou `IdunBattleLogic.Entities.DSLFactory$$HealthPctIsBelowOrEqual(unit, pct)` alloue un
    `IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger` sur la stat **5 = HEALTH**
    -> `(current / max) <= (healthPct / 100)` en Fix64. `GetNumberConstant(0x4f)` =
    `gameconfig.ability("HammerOfWrath").constants["healthPct"]` = 50. i2 : « If Mataneo is at or below
    50% Health, doubles the damage dealt by this ability. »

    AUCUNE contribution propre (ni stat-mod, ni EffectBonus) : sa SEULE fonction est d'etre LU par
    `HammerOfWrathAbility$$GetDoubleCondition` = `HasEffect(Self, 0x534, activeOnly=1)`, qui gate le
    `ConditionalAmount(cond, Multiply(MinMaxDamage, 2), MinMaxDamage)` du node de degat. C'est donc le
    MEME patron que `AnvilShield_BlockChanceBelowHealthCap` (present en permanence, `IsActive` bascule
    avec les PV) -- et, comme lui, il est ABSENT du seed live tant que la condition est fausse
    (`decisionView.effects` n'expose que les effets ACTIFS, GROUND TRUTH #100).

    Comparaison ENTIERE exacte (meme argument que `_regenerate_precondition` de SavageEchoes) :
    `100*current <= healthPct*max` -- pour des PV entiers la division Fix64 ne bascule jamais autrement,
    et l'egalite au bord (2*current == max) est rendue 0.5 exact -> `<=` vrai."""

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`CreateActiveCondition` : `HealthPct(Self) <= GetNumberConstant(0x4f = healthPct)`.
        `unit_state` = `{hp, max_hp}` (convention `PowerTripFullHealthEffect`/`AnvilShield...`).
        PV non captes -> True (degradation fidele : on ne masque pas l'effet a tort)."""
        s = unit_state or {}
        hp, mx = s.get("hp"), s.get("max_hp")
        pct = ability_var("HammerOfWrath", "healthPct", is_constant=True)   # GetNumberConstant(0x4f) = 50
        if hp is None or mx is None or not mx or pct is None:
            return True
        return 100 * int(hp) <= int(pct) * int(mx)


class TunnelingHorrorPendingSummonEffect(BaseEffect):
    """`TunnelingHorror_PendingSummon` (EffectType 0x459 = 1113, `necroSmnDestroyer` « Ophydian
    Destroyer ») -- MARQUEUR de bond POSE SUR LA TUILE de destination, dont la SEULE semantique est
    de NE JAMAIS s'auto-retirer. Aucune contribution (ni stat-mod, ni EffectBonus, ni condition).

    IDENTITE DE CLASSE (piege du `.ctor` mutualise, #366-r1)
    -------------------------------------------------------
    Ghidra nomme le corps appele par `IdunBattle.Entities.Effects.Loki.TunnelingHorror_PendingSummonEffect$$.ctor`
    « `IdunBattle.Entities.Effects.BaseEffect$$.ctor` » -- c'est un corps DEDUPLIQUE : la surcharge
    a 4 arguments d'`IdunBattle.Entities.Effects.ABondEffect` est instruction pour instruction celle
    de la base, donc IL2CPP n'en garde qu'un exemplaire, attribue a `BaseEffect`. Le parent REEL se
    lit dans `data/symbols/<build>/frida/classes.tsv` :
    `IdunBattle.Entities.Effects.Loki.TunnelingHorror_PendingSummonEffect` -> parent
    `IdunBattle.Entities.Effects.ABondEffect`. Ne jamais conclure la hierarchie du nom du `$$.ctor`.

        .ctor() = ABondEffect( hasAutomaticActivation: true,
                               unitEffectType: 0,
                               sourceAbility: AbilityOrEffect(ActiveAbilityType.TunnelingHorror = 1011) )

    (`mov edx, 0x3f3` puis la surcharge `IdunBattle.Core.AbilityOrEffect$$op_Implicit` qui appelle
    `IdunBattle.Core.AbilityOrEffect$$set_ActiveAbility` -- donc ActiveAbilityType, PAS EffectType ni
    TriggeredAbilityType, tous trois ayant une surcharge homonyme.)

    LES TROIS SURCHARGES DE LA CLASSE, ET CE QU'ELLES ETEIGNENT
    ----------------------------------------------------------
    La classe ne definit que quatre methodes ; les trois autres que le `.ctor` sont des getters a
    corps TRIVIAL (releves au runtime par le RPC `resolveMethodPtr` -- les tables de symboles
    dedupliquent ces corps et ne les nomment donc pas) :

        get_Adjacent                  -> false
        get_Range                     -> Nullable<int> sans valeur
        get_RemoveOnBondedEntityDeath -> false

    Ces trois getters sont les SEULS parametres lus par
    `IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal`, qui construit
    l'`ArraySet` des triggered-abilities PORTEES PAR L'EFFET -- une par condition, chacune
    `Triggered(<cond>, RemoveEffect(EffectSelf))` :

        RemoveOnBondedEntityDeath -> NOT AmountIsZero(BondedEntityFromEffect) & (On(0x2) | On(0x25))
                                     & IsEntityWithIdTarget(BondedEntityFromEffect)
        Range.HasValue            -> NOT IsInRange(Owner, BondedEntity, Direct(Range))
                                     & NOT AmountIsZero(BondedEntity) & On(0x1d)
        Adjacent                  -> NOT IsAdjacent(Owner, BondedEntity, 3)
                                     & NOT AmountIsZero(BondedEntity) & On(0x1d)

    Les trois etant faux/absents, l'`ArraySet` est **VIDE** : cet effet ne porte AUCUN trigger de
    retrait automatique. C'est pour cela qu'il n'a PAS d'entree dans `EFFECT_TRIGGERS` -- une
    absence MESUREE, pas un oubli.

    CE QUI REND CETTE CLASSE DISTINCTIVE. Balayage runtime des **16** classes derivant d'`ABondEffect`
    (`resolveMethodPtr`, 2026-08-01, build `rnca9r7q6c`) : `get_RemoveOnBondedEntityDeath` rend
    **true** chez 13 d'entre elles (corps trivial partage), un calcul chez
    `IdunBattle.Entities.Effects.APendingAttackEffect`, et **false** chez exactement DEUX :
    `TunnelingHorror_PendingSummonEffect` et son jumeau
    `IdunBattle.Entities.Effects.Loki.CallRipperSwarms_PendingSummonEffect`. Autrement dit : les deux
    marqueurs de « summon en attente » sont les seuls bonds que la mort de l'unite bondee ne casse
    pas. (`get_Adjacent` : false partout sauf `HolyDuel_TauntEffect` = true et
    `HazeOfCorruption_DamageTransferEffect` = bespoke.)

    LE VECTEUR DE POSE, ET SON ETAT COTE PORT
    -----------------------------------------
    `IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorrorAbility$$ExecuteBehaviour` (active
    1011) execute TROIS behaviours :
        `RemoveUnitFromItsTiles(Caster, removeTileFromUnit: true)`
        `RemoveAllForcedAttackTargets(Caster)`
        `AddBondEffect(0x459, AbilityStateReference, source: Caster, targets: TargetTiles,
                       bondedEntity: Caster, <options SANS TurnsFromRounds>)`
    L'ability 1011 n'est PAS portee (`ABILITY_CLASSES`) : il manque la primitive
    `IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute` (l'unite quitte le plateau).
    L'effet arrive donc offline par le SEUL chemin de CHARGEMENT
    (`runner/snapshot.py::_load_tile_effects`, canal `tileMeta.tiles[].effects`), jamais par une pose
    offline. Residu nomme : cf. `docs/rl/case-366-r1-tunneling-horror-pending-summon.md`.

    LE RETRAIT est explicite, et lui seul :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorror_AppearAbility$$ExecuteBehaviour`
    (active 1060) selectionne `First(EffectTarget(BondEffects(all, 0x459, bondedEntity: Owner)), 1)`
    = la tuile marquee, y deplace l'unite, puis `RemoveEffect(EffectSelf, 0x459)`.

    MESURE LIVE (2026-08-01, `probe_366_r1_tunneling_horror.py`, greffe de 1011 sur `necroDestroyer`,
    board MC1_67, seed 777) -- cast sur la tuile (3,6) :
        RemoveUnitFromTiles e=<caster>  Clear_Unit_Tiles=1
        ReceiveEffect e=<tuile>  BondEffect_BondedId=<caster> Effect_SourceId=<caster>
                                 Effect_SourceActiveAbility=1011 Effect_CurrentLevel=1
    puis `tileMeta` : `{name: TunnelingHorror_PendingSummon, effectType: 1113, source: <caster>,
    remaining: 0, level: 1}` sur (3,6) SEULEMENT, et le caster passe a `pos = null`.
    `remaining = 0` => l'effet est PERMANENT (aucun `TurnsFromRounds` dans les options d'`AddBondEffect`) ;
    la fiche `docs/rl/summon-abilities-port-spec.md` qui annoncait « default -> 1 round » est REFUTEE.
    Au tour suivant, cast de 1060 -> `ChangePosition e=<caster> Unit_Foot_Tile_Id_1=<tuile>` puis
    `LoseEffect`/`DeactivateEffect` de l'effet 1113 : la tuile est nettoyee.

    NON COUVERT cote port : `BaseEffect.bonded` reste `None` pour une instance SEEDEE -- le canal de
    capture `tileMeta` publie `{name, effectType, source, remaining, level}` et PAS le
    `BondEffect_BondedId` (limite connue du canal, cf. `runner/operations/effects.py`). Le flux
    d'events, lui, le porte."""

    # `ABondEffect..ctor(hasAutomaticActivation = 1, ...)` -- attribut INERTE cote port (aucun
    # lecteur), pose pour la meme raison que `CounterAttackEffect.HAS_AUTOMATIC_ACTIVATION`.
    HAS_AUTOMATIC_ACTIVATION = True
    # Les trois getters d'`ABondEffect` surcharges par la classe (cf. docstring). INERTES : le port
    # ne mirror PAS `CreateHandleTriggerAbilitiesInternal` de facon generique -- chaque effet declare
    # ses triggers dans `EFFECT_TRIGGERS`. Ils sont ecrits pour que la NON-inscription de 1113 dans
    # ce registre se lise comme une mesure et pas comme un trou.
    BOND_ADJACENT = False                    # `get_Adjacent` -> false
    BOND_RANGE = None                        # `get_Range` -> Nullable<int> sans valeur
    BOND_REMOVE_ON_BONDED_ENTITY_DEATH = False   # `get_RemoveOnBondedEntityDeath` -> false
