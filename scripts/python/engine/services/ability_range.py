"""Portee de CIBLAGE d'une ability, cote DECISION -- le volet PORTEE de
`IdunBattle.Core.Services.TargetingQuery$$GetRange` sur le substrat OFFLINE (kit gameconfig).

POURQUOI CE MODULE EXISTE (#433-r4-r2-r1). `IdunBattle.Core.Services.BattleQuery$$IsTileInRangeOfAnyAbility`
demande « la tuile T est-elle frappable par `unit` DEPUIS SA TUILE COURANTE, par n'importe laquelle
de ses abilities » -- une question qui se decompose en une portee PAR ABILITY. Le mirror complet de
cette portee vit deja dans `engine.runner.abilities.targeting` (`get_range`), mais il consomme un
`State` de RUNNER (composants ECS, effets, stats) que la face DECISION n'a pas. Ce module en est la
restriction : meme cascade, meme ordre, substrat gameconfig, et **`None` chaque fois que le port ne
sait pas decider** -- jamais une portee devinee.

LE CANAL DE LA DONNEE, ET POURQUOI IL A DEUX ETAGES. Le `TargetingRange` d'une ability est ecrit par
son `<X>Ability$$.ctor`, de trois facons -- toutes rencontrees dans le lot lu ici :

  1. **ctor « flags directs »** : `IdunBattle.Core.Services.TargetingOptions$$.ctor(&opts,
     isSelfCasting, &range, forceMeleeTarget, rules, ...)` ou `&range` pointe l'un des CINQ
     `TargetingRange` STATIQUES (`IdunBattle.Core.Services.TargetingRange$$.cctor`) ;
  2. **preset** : le ctor recopie les 0x40 octets d'un champ statique de `TargetingOptions`
     (`IdunBattle.Core.Services.TargetingOptions$$.cctor`), dont le `TargetingRange` occupe
     `<preset>+0x08..0x1f` -- lui-meme copie d'un des cinq statiques ;
  3. **`TargetingRange$$CustomRange(GetRange)`** : un DELEGUE, dont `GetRange` ECRASE la valeur ->
     portee non derivable (`override_range_func`).

Les cinq statiques, RE-LUS a l'octet sur `IdunBattle.Core.Services.TargetingRange$$.cctor` (layout
`onlyAdjacent@+0x00`, `useRangeFromConfig@+0x04`, `useWholeBoard@+0x05`, `Nullable<int>
overrideRange@+0x08`, `overrideRangeFunc@+0x10`) :

    statics+0x00  onlyAdjacent = 3 (IfNotRangedCaster)             -> RANGE_ADJACENT_IF_MELEE_CASTER
    statics+0x18  onlyAdjacent = 1 (False), useRangeFromConfig = 1 -> RANGE_FROM_CONFIG
    statics+0x30  onlyAdjacent = 0 (True),  overrideRange = 1      -> RANGE_ADJACENT
    statics+0x48  onlyAdjacent = 1 (False), useWholeBoard = 1      -> RANGE_WHOLE_BOARD
    statics+0x60  onlyAdjacent = 1 (False), overrideRange = 0      -> RANGE_SELF

-- exactement les cinq que `engine.runner.abilities.targeting` nomme deja. Ce module les REUTILISE,
il n'en redefinit aucun.

LE SUBSTRAT SE LIT EN DEUX SOURCES, dans cet ordre :
  * `ABILITY_CLASSES` (registre du runner) quand l'ability y est -- son `TARGETING_OPTIONS.range`
    a ete lu au decompile par la tranche qui l'a portee. **102 entrees, 102 avec un
    `TargetingRange`** (re-derive du code, pas herite) ;
  * `TARGETING_RANGE_BY_ABILITY` ci-dessous, pour les abilities HORS registre : le volet PORTEE
    SEUL, lu au decompile. C'est une lecture PARTIELLE assumee -- poser ces abilities dans
    `ABILITY_CLASSES` exigerait de porter leur COMPORTEMENT, ce que cette tranche ne fait pas.
"""
from __future__ import annotations

import gameconfig as GC
import hexgeo

from ..runner.abilities.targeting import (RANGE_ADJACENT, RANGE_ADJACENT_IF_MELEE_CASTER,
                                          RANGE_FROM_CONFIG, RANGE_SELF, RANGE_WHOLE_BOARD,
                                          RANGED_BOOL_FALSE, RANGED_BOOL_IF_NOT_RANGED_CASTER,
                                          RANGED_BOOL_IF_RANGED_CASTER, RANGED_BOOL_TRUE,
                                          TargetingRange, custom_range_func, unit_weapon_range)

# ------------------------------------------------------------------------------------------------
# Le volet PORTEE des abilities HORS `ABILITY_CLASSES`, lu ability par ability au decompile.
#
# PERIMETRE DE CE LOT : les 32 abilities ACTIVES du pool spawnable (`rl_duel build --list-pool`,
# rank courant) qui n'etaient pas au registre -- c'est exactement l'ensemble des portees que
# `IsTileInRangeOfAnyAbility` peut avoir a lire sur un ennemi confrontable. Chaque entree cite le
# ctor LU et la voie (preset `TargetingOptions+0x<n>` ou `TargetingRange` statique direct).
# ------------------------------------------------------------------------------------------------
TARGETING_RANGE_BY_ABILITY: dict[int, TargetingRange] = {
    # --- ctor « flags directs », `&range` = un `TargetingRange` statique ---
    1005: RANGE_ADJACENT,        # AdaptiveStrategyAbility$$.ctor          -- TR statics+0x30
    1019: RANGE_ADJACENT_IF_MELEE_CASTER,  # StormOfWrathAbility$$.ctor    -- TR statics+0x00
    1038: custom_range_func(),   # FoulInfusionAbility$$.ctor              -- CustomRange(GetRange)
    1039: RANGE_ADJACENT,        # RitesOfRestorationAbility$$.ctor        -- TR statics+0x30
    1049: RANGE_FROM_CONFIG,     # CrusadeOfWrathAbility$$.ctor            -- TR statics+0x18
    1057: RANGE_ADJACENT,        # GrotTankAbility$$.ctor                  -- TR statics+0x30
    1061: RANGE_FROM_CONFIG,     # UnbreakableDutyAbility$$.ctor           -- TR statics+0x18
    1087: RANGE_WHOLE_BOARD,     # ExemplarOfTheKauyonAbility$$.ctor       -- TR statics+0x48
    1121: RANGE_ADJACENT,        # ItItchesAbility$$.ctor                  -- TR statics+0x30
    1141: RANGE_ADJACENT,        # OverwhelmingWrathAbility$$.ctor         -- TR statics+0x30
    1152: RANGE_ADJACENT,        # UnstoppableMomentumReworkedAbility$$.ctor -- TR statics+0x30
    1164: RANGE_FROM_CONFIG,     # MindControlAbility$$.ctor               -- TR statics+0x18
    1175: RANGE_ADJACENT,        # BloodChaliceAbility$$.ctor              -- TR statics+0x30
    1197: RANGE_ADJACENT,        # ExcruciatingFrequenciesAbility$$.ctor   -- TR statics+0x30
    # --- preset : recopie des 0x40 octets d'un statique de `TargetingOptions` ---
    1027: RANGE_FROM_CONFIG,     # PsychicMaelstromAbility$$.ctor          -- preset +0x180
    1048: RANGE_FROM_CONFIG,     # FragstormGrenadeLauncherAbility$$.ctor  -- preset +0x180
    1050: RANGE_ADJACENT,        # HolyDuelAbility$$.ctor                  -- preset +0x40
    1063: RANGE_ADJACENT_IF_MELEE_CASTER,  # FireAndRepositionAbility$$.ctor -- preset +0x00
    1064: RANGE_ADJACENT,        # SwoopingHawkAbility$$.ctor -> DiveAttackAbilityBase$$.ctor, preset +0x40
    1068: RANGE_ADJACENT,        # SilentDeathAbility$$.ctor               -- preset +0x40
    1069: RANGE_FROM_CONFIG,     # SeekerMissileFrequencyLockAbility$$.ctor -- preset +0x180
    1088: RANGE_FROM_CONFIG,     # HellfyreMissileRackAbility$$.ctor       -- preset +0x140
    1101: RANGE_FROM_CONFIG,     # AttemptedPossessionAbility$$.ctor       -- preset +0x180
    1106: RANGE_SELF,            # WarHowlAbility$$.ctor                   -- preset +0x280
    1129: RANGE_ADJACENT,        # BloodyFuryAbility$$.ctor                -- preset +0x40
    1132: RANGE_ADJACENT,        # KillMaimBurnAbility$$.ctor              -- preset +0x40
    1165: RANGE_ADJACENT,        # MightFromBelowAbility$$.ctor            -- preset +0x40
    1177: RANGE_WHOLE_BOARD,     # LightOfSanguiniusAbility$$.ctor         -- preset +0x240
    1183: RANGE_ADJACENT,        # VexillaMagnificaAbility$$.ctor          -- preset +0x40
    1191: RANGE_ADJACENT,        # MartialInspirationAbility$$.ctor        -- preset +0x40
    1195: RANGE_ADJACENT,        # TalonsOfTheEmperorAbility$$.ctor        -- preset +0x40
    1204: RANGE_WHOLE_BOARD,     # LeadingTheChargeAbility$$.ctor          -- preset +0x240
}


def targeting_range_of(ability_id) -> TargetingRange | None:
    """Le `TargetingRange` d'une ability : registre du runner d'abord, table locale ensuite.

    `None` = **non RE-lu** (et non « pas de portee ») -- l'appelant ne pose alors AUCUN terme."""
    try:
        aid = int(ability_id)
    except (TypeError, ValueError):
        return None
    from ..runner.abilities.handler import ABILITY_CLASSES     # lazy : cycle services <-> runner
    cls = ABILITY_CLASSES.get(aid)
    opts = getattr(cls, "TARGETING_OPTIONS", None) if cls is not None else None
    rng = getattr(opts, "range", None) if opts is not None else None
    return rng if rng is not None else TARGETING_RANGE_BY_ABILITY.get(aid)


def _has_ranged_weapon(visual_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsRanged` sur le substrat gameconfig :
    `HasTrait(unit, 0xb Ranged) || WeaponsComponent.HasRangedWeapon(unit)`. Le trait `0xb` n'est
    porte par AUCUNE unite du gameconfig (constat #161, deja acte par
    `engine.runner.abilities.targeting.unit_is_ranged`), donc seul le 2e terme mord ici.

    ⚠ `HasRangedWeapon` teste la PRESENCE d'un `Range`, pas `!IsMelee` : une arme `Range == 1` est
    MELEE pour `WeaponProfile$$get_IsMelee` mais compte ici. Les deux tris coexistent dans le natif
    -- cf. `engine.services.battle_query.weapon_is_melee`."""
    weapons = (GC.unit(visual_id or "") or {}).get("weapons") or []
    return any(w.get("Range") for w in weapons)


def _ranged_bool_is_true(value: int, visual_id) -> bool:
    """`IdunBattle.Core.Services.RangedBoolExtensions$$IsTrue(RangedBool, unit)`, face DECISION."""
    v = int(value)
    if v == RANGED_BOOL_TRUE:
        return True
    if v == RANGED_BOOL_FALSE:
        return False
    if v == RANGED_BOOL_IF_RANGED_CASTER:
        return _has_ranged_weapon(visual_id)
    return not _has_ranged_weapon(visual_id)          # IfNotRangedCaster


# ------------------------------------------------------------------------------------------------
# L'ETAGE `GetDynamicInvalidTargetReason` -- ce qui SEPARE deux abilities au MEME preset (#-r1-r1)
#
# `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` ne se contente pas de recopier les 0x40
# octets du preset dans `this.<TargetingOptions @+0x70>` : il ECRASE ensuite le champ `+0x38` par
# `new TargetingOptions.DynamicTargetingTargetRule(this, <klass+0x480>)`. `klass+0x480` est le champ
# `MethodInfo*` du slot de vtable commencant a `klass+0x478` (vtable a `klass+0x138`, pas 0x10 :
# index 52) -- RESOLU AU RUNTIME (`resolveVtableSlot`), c'est `GetDynamicInvalidTargetReason`.
#
# Ce champ `+0x38` est EXACTEMENT celui qu'invoque le TROISIEME predicat de
# `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` -- la lambda
# `TargetingQuery.u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__2`,
# appliquee en `RemoveAll` quand `Rules & 2` : la tuile est RETIREE de la zone quand le delegue rend
# une raison NON NULLE. C'est donc `GetDynamicInvalidTargetReason` -- et lui seul -- qui donne sa
# FORME a la zone AU-DELA du `TargetingRange`, et c'est ce qui separait `LightOfSanguinius` (1177) de
# `LeadingTheCharge` (1204), pourtant au MEME preset `TargetingOptions statics+0x240`.
#
# Le gate ne peut que RETIRER (`RemoveAll`) : le rayon de `GetTilesInRange` en est donc une borne
# SUPERIEURE, que le gate abaisse.
# ------------------------------------------------------------------------------------------------

#: La base `AActiveAbility$$GetDynamicInvalidTargetReason` rend 0 -- elle ne retire RIEN. C'est le
#: DEFAUT (ability absente de la table) et c'est un FAIT runtime, pas une hypothese : le corps de
#: base est DEDUPLIQUE par IL2CPP, donc l'absence d'un `<X>$$GetDynamicInvalidTargetReason` dans les
#: tables ne prouverait rien -- ce qui le prouve, c'est l'egalite des pointeurs de slot lue sur la
#: vtable (`probe_433_r4_r2_r1_r1_dynamic_target_gate.py --step gate`).
GATE_NONE = "none"

#: `GetFreeAdjacentTiles(targetTiles).Any(t => GetDistance(t, casterTiles) <= config.range)`
#: -- slots `IBattleQuery` 0x53 et 0x6d, re-derives au RUNTIME (ifaceOffset = 4, prouve sur
#: `IsTileInRangeOfAnyAbility` 0xc5 -> index 201 et `FindRangedWeapon` 0xb3 -> index 183).
#: La zone est donc bornee par `config.range + 1` : le `+1` vient de ce que le test porte sur les
#: VOISINES de la cible, pas sur la cible.
GATE_FREE_ADJACENT_IN_CONFIG_RANGE = "free_adjacent_in_config_range"

#: Gate LU, mais dont la condition n'est pas derivable du seul kit gameconfig -- elle interroge
#: l'ETAT de bataille (tuiles mouvables et pathfinding, portee de synapse, occupation des tuiles,
#: forme de spawn). Le port ne le modelise pas.
GATE_NOT_DERIVABLE = "not_derivable"

#: L'ability SURCHARGE (fait runtime), mais son corps n'a pas ete lu par cette tranche.
GATE_NOT_READ = "not_read"

#: `TargetingQuery$$GetTilesInRange` branche AVANT tout le reste sur `range.UseWholeBoard` et rend
#: `<IBattleQuery slot 0x69>()` = `GetAllTiles()` : le natif ne borne AUCUNE distance. Le port
#: modelisant la zone par un RAYON, on lui donne ici un infini pratique -- aucune donnee n'y est
#: ajustee, la seule propriete requise est de majorer tout plateau.
WHOLE_BOARD_REACH = 1_000_000

#: Le regime du gate, ability par ability. **Une entree ABSENTE signifie `GATE_NONE`** -- ce qui se
#: verifie au runtime, slot par slot. Ne figurent donc ici QUE les abilities dont la vtable montre
#: une surcharge.
DYNAMIC_TARGET_GATE_BY_ABILITY: dict[int, str] = {
    # --- LU et derivable : la borne est une DISTANCE au caster -------------------------------
    1177: GATE_FREE_ADJACENT_IN_CONFIG_RANGE,  # LightOfSanguiniusAbility$$GetDynamicInvalidTargetReason
    1153: GATE_FREE_ADJACENT_IN_CONFIG_RANGE,  # HammerOfWrathAbility$$GetDynamicInvalidTargetReason
    # --- LU, NON derivable hors etat de bataille ---------------------------------------------
    1058: GATE_NOT_DERIVABLE,   # WaaaghAbility -- GetPossibleMovementTiles (selecteur DSL)
    1087: GATE_NOT_DERIVABLE,   # ExemplarOfTheKauyonAbility -- TileExtensions$$IsFreeTile + slot 0x7a
    1112: GATE_NOT_DERIVABLE,   # AlphaWarriorAbility -- IsInSynapseRange(caster, target)
    1158: GATE_NOT_DERIVABLE,   # DutyEternalAbility -- DSLSelectors$$ThreeTileUnitSpawnShape
    1163: GATE_NOT_DERIVABLE,   # BlackRageAbility -- GetPossibleMovementTiles (selecteur DSL)
    1180: GATE_NOT_DERIVABLE,   # HeroicFusilladeAbility -- GetSurroundingTiles + GetMinDistance
    1202: GATE_NOT_DERIVABLE,   # VigilanceEternalAbility -- AreEntitiesAdjacent, sinon mouvement
    1204: GATE_NOT_DERIVABLE,   # LeadingTheChargeAbility -- DSLSelectors$$TilesUnitCanMoveToChargeTarget
    # --- SURCHARGE etablie au runtime, corps NON LU par cette tranche -------------------------
    28:   GATE_NOT_READ,        # RepairAbility
    1005: GATE_NOT_READ,        # AdaptiveStrategyAbility
    1011: GATE_NOT_READ,        # TunnelingHorrorAbility
    1016: GATE_NOT_READ,        # SendInTheNextWaveAbility
    1025: GATE_NOT_READ,        # SkyStrikeAbility
    1038: GATE_NOT_READ,        # FoulInfusionAbility
    1059: GATE_NOT_READ,        # RammingSpeedAbility
    1081: GATE_NOT_READ,        # FightingRetreatAbility
    1082: GATE_NOT_READ,        # InspiredToGreatnessAbility
    1100: GATE_NOT_READ,        # SorcerousFacadeAbility
    1101: GATE_NOT_READ,        # AttemptedPossessionAbility
    1116: GATE_NOT_READ,        # RadBombardmentAbility
    1117: GATE_NOT_READ,        # DefendTheDivineWorkAbility
    1119: GATE_NOT_READ,        # Repair_GalvanicFieldAbility
    1143: GATE_NOT_READ,        # ForwardSpotterAbility
    1145: GATE_NOT_READ,        # SporeMineLauncherAbility
    1151: GATE_NOT_READ,        # TheQuickeningAbility
    1164: GATE_NOT_READ,        # MindControlAbility
    1168: GATE_NOT_READ,        # EntropyCannonsAbility
    1175: GATE_NOT_READ,        # BloodChaliceAbility
    1179: GATE_NOT_READ,        # CultDemagogueAbility
    1197: GATE_NOT_READ,        # ExcruciatingFrequenciesAbility
    1200: GATE_NOT_READ,        # SquigLaunchasAbility
    1201: GATE_NOT_READ,        # SquigMineAbility
    1213: GATE_NOT_READ,        # DeathOnTheWindAbility
}


def dynamic_target_gate_of(ability_id) -> str:
    """Le regime du gate `GetDynamicInvalidTargetReason` de cette ability.

    L'ABSENCE de la table vaut `GATE_NONE` : la base `AActiveAbility` rend 0, donc ne retire rien.
    Ce defaut est un FAIT runtime (egalite des pointeurs de slot), pas une deduction d'absence."""
    try:
        aid = int(ability_id)
    except (TypeError, ValueError):
        return GATE_NONE
    return DYNAMIC_TARGET_GATE_BY_ABILITY.get(aid, GATE_NONE)


def dynamic_target_gate_reach(ability_id) -> int | None:
    """Le rayon que le gate LAISSE SUBSISTER -- `WHOLE_BOARD_REACH` quand il ne retire rien,
    `None` quand le port ne sait pas decider.

    `GATE_NOT_READ` ne retire rien NON PLUS : ne pas retrecir sur un corps non lu preserve le
    comportement de la tranche precedente pour les 15 abilities non-whole-board concernees, plutot
    que de leur substituer un `None` qui les retirerait toutes de la zone d'un coup."""
    gate = dynamic_target_gate_of(ability_id)
    if gate == GATE_FREE_ADJACENT_IN_CONFIG_RANGE:
        cfg = _config_range(ability_id)
        return None if cfg is None else int(cfg) + 1
    if gate == GATE_NOT_DERIVABLE:
        return None
    return WHOLE_BOARD_REACH                       # GATE_NONE et GATE_NOT_READ : aucun retrait


def _config_range(ability_id) -> int | None:
    """`AbilityConfiguration.GetNumberConstant(0x16 range)` = `constants.range` de gameconfig --
    ce que `IdunBattle.Entities.Abilities.AActiveAbility$$SetConfigValuesInTargetingOptions` recopie
    dans `options.Range.OverrideRange` quand `UseRangeFromConfig` est pose."""
    from ..entities.active_ability_type import ActiveAbilityType
    try:
        name = ActiveAbilityType(int(ability_id)).name
    except (TypeError, ValueError):
        return None
    raw = ((GC.ability(name) or {}).get("constants") or {}).get("range")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def tiles_in_range_reach(ability_id, visual_id) -> int | None:
    """Le rayon de `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` -- la zone AVANT les
    trois predicats de `GetPossibleTargetsForOptions`. C'est une borne SUPERIEURE exacte.

    L'ORDRE natif, respecte : `SetConfigValuesInTargetingOptions` pose `OverrideRange = config`
    **seulement si** `UseRangeFromConfig` ET `OverrideRange` encore vide ; puis `GetRange` fait
    `value = weaponRange` puis `value = OverrideRange.GetValueOrDefault(value)`. Un override du ctor
    GAGNE donc sur la config, et la config gagne sur l'arme.

    `UseWholeBoard` COURT-CIRCUITE tout le reste, et dans les DEUX etages : `GetRange` rend
    `{ Range = 1, OnlyAdjacent = false, UseWholeBoard = true }` sans meme evaluer `only_adjacent` ni
    la portee d'arme, puis `GetTilesInRange` branche dessus EN PREMIER et rend
    `<IBattleQuery slot 0x69>()` = `GetAllTiles()`. D'ou `WHOLE_BOARD_REACH`.

    `only_adjacent` (resolu par `RangedBoolExtensions$$IsTrue`) ramene la portee EFFECTIVE a 1 : le
    consommateur (`TargetingQuery$$GetInvalidTargetReason`, volet portee) bascule alors sur
    `AreEntitiesAdjacent` au lieu de la comparaison de distance.

    Rend `None` -- « le port ne sait pas decider » -- dans TROIS cas, tous natifs :
      * `TargetingRange` non RE-lu (ability absente des deux sources) ;
      * `OverrideRangeFunc` : le delegue ECRASE la valeur et n'est pas resolu (meme arbitrage que
        `engine.runner.abilities.targeting.get_range`) ;
      * `UseRangeFromConfig` sans `constants.range` dans le kit."""
    rng = targeting_range_of(ability_id)
    if rng is None or rng.override_range_func:
        return None
    if rng.use_whole_board:
        return WHOLE_BOARD_REACH
    ov = rng.override_range
    if ov is None and rng.use_range_from_config:
        ov = _config_range(ability_id)
        if ov is None:
            return None
    if ov is None:
        ov = unit_weapon_range(visual_id, None)       # `stats` absent -> ExtraRange = 0 (cf. mirror)
        if ov is None:
            return None                               # `!HasAnyWeapon` -> `GetStat(Range)`, non observable
    return 1 if _ranged_bool_is_true(rng.only_adjacent, visual_id) else int(ov)


def ability_range_value(ability_id, visual_id) -> int | None:
    """La PORTEE effective d'une ability pour ce caster -- la COMPOSITION des deux etages natifs :
    le rayon de `GetTilesInRange` (borne SUPERIEURE) puis le retrait opere par le predicat
    `GetDynamicInvalidTargetReason` (`RemoveAll`, donc il ne peut que RETRECIR).

    Le regime `UseWholeBoard` se scinde alors en DEUX, et c'est ce qui ferme `#433-r4-r2-r1-r1` :

      * gate `GATE_NONE` -- la zone est le plateau ENTIER. MESURE (`darkaAsmodai`,
        `ExemplarOfHate`, sweep de 40 positions `d = 2..10`) : le natif rend « en portee » sur
        **40/40**, a TOUTE distance. L'ancienne tranche rendait `None` ici, soit 40 faux negatifs ;
      * gate LU et derivable -- la zone est bornee par le gate. MESURE (`bloodDante`,
        `LightOfSanguinius`, `constants.range = 5`) : le natif est « en portee » a **100 %** pour
        `d <= 5` et encore **4/6** a `d = 6`, puis **0** des `d >= 7`. C'est `config.range + 1`,
        le `+1` venant de ce que `GetFreeAdjacentTiles` teste les VOISINES de la cible. Un modele
        en `config.range` aurait predit zero a `d = 6` : seule la ventilation PAR DISTANCE separe
        les deux, une comparaison globale ne l'aurait pas vu ;
      * gate LU mais NON derivable -- `None`, comme avant. C'est le SEUL regime ou la borne
        superieure est inutilisable : la verser reviendrait a declarer tout le plateau menace.
        MESURE (`astraDreir`, `LeadingTheCharge`) : le natif rend « hors portee » des `d >= 2`,
        donc verser le plateau ferait 40 faux POSITIFS la ou `None` en fait 0."""
    base = tiles_in_range_reach(ability_id, visual_id)
    if base is None:
        return None
    gate = dynamic_target_gate_reach(ability_id)
    if gate is None:
        # Gate non derivable. Si la zone de base est bornee, elle reste une borne SUPERIEURE
        # exacte et le port la garde (statu quo de la tranche precedente) ; si elle est le plateau
        # entier, il n'y a plus rien d'exploitable -> `None`.
        return None if base == WHOLE_BOARD_REACH else base
    return min(base, gate)


def _active_ability_ids(visual_id) -> list:
    """Les ids d'ability ACTIVE du kit gameconfig de l'unite (`activeAbilities`, noms -> enum)."""
    from ..entities.active_ability_type import ActiveAbilityType
    out = []
    for name in ((GC.unit(visual_id or "") or {}).get("activeAbilities") or []):
        try:
            out.append(int(ActiveAbilityType[name]))
        except KeyError:
            continue
    return out


_REACH_CACHE: dict = {}    # {visual_id: reach} -- kit gameconfig = STATIQUE (aucune dependance d'etat)


def unit_threat_reach(visual_id, ability_ids=None) -> int:
    """Le RAYON de `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange(unit,
    {GetMainTile(unit)}, includeNormalAttack: true)` -- l'UNION des zones de portee de l'unite
    depuis sa tuile COURANTE, modelisee par le max de ses portees.

    Les deux termes de l'union, dans l'ordre du natif :
      * `includeNormalAttack: true` -> l'attaque NORMALE. Son `TargetingRange` est
        `RANGE_ADJACENT_IF_MELEE_CASTER` (`onlyAdjacent = IfNotRangedCaster`), ce qui se reduit
        EXACTEMENT a `unit_weapon_range` : portee d'arme pour un caster a arme a distance,
        adjacence (1) sinon ;
      * chaque ability ACTIVE du kit dont la portee est derivable (`ability_range_value`).

    APPROXIMATION NOMMEE : le natif rend un ENSEMBLE de tuiles (les slots 9/10 de chaque
    `AActiveAbility`, LoS et forme comprises) ; le port n'en garde que le RAYON. Le predicat de
    ciblage dynamique (`GetDynamicInvalidTargetReason`) est desormais MODELISE -- c'est ce qui borne
    la zone d'une ability `UseWholeBoard` (cf. `ability_range_value`) -- mais les deux autres
    predicats de `GetPossibleTargetsForOptions` ne le sont pas : `b__1` retire les tuiles obscurcies
    par le terrain (residu `#433-r4-r2-r1-r2`), et les gates par ability en AMONT
    (`GetInvalidCasterReason`, `CanCurrentlyBeUsed`, `IsAbilityBlocked`) peuvent retirer une ability
    ENTIERE sans que le kit gameconfig le dise.

    `WHOLE_BOARD_REACH` se propage par le `max` : une seule ability `UseWholeBoard` SANS gate suffit
    a rendre toute tuile du plateau menacee, ce qui est exactement `GetAllTiles()`.

    Cache par `visual_id` quand le kit n'est pas force par l'appelant : les deux sources sont
    STATIQUES (gameconfig + tables lues au decompile), donc le resultat ne depend d'AUCUN etat de
    bataille -- et l'appelant est un SWEEP de positions, qui le redemanderait a chaque tuile."""
    if ability_ids is None:
        got = _REACH_CACHE.get(visual_id)
        if got is not None:
            return got
    reach = unit_weapon_range(visual_id, None)
    reach = 0 if reach is None else int(reach)
    for aid in (_active_ability_ids(visual_id) if ability_ids is None else ability_ids):
        v = ability_range_value(aid, visual_id)
        if v is not None and v > reach:
            reach = int(v)
    if ability_ids is None:
        _REACH_CACHE[visual_id] = reach
    return reach


def _free_adjacent_gate_allows(unit_pos, tile, cfg_range: int, elev_by_pos) -> bool:
    """Le gate `GATE_FREE_ADJACENT_IN_CONFIG_RANGE`, evalue TUILE PAR TUILE au lieu d'etre rabattu
    sur son rayon :

        free = <IBattleQuery slot 0x53>(targetTiles)            # GetFreeAdjacentTiles
        return free.Count > 0 && free.Any(t => <slot 0x6d>(t, casterTiles) <= config.range)

    `IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles` = `GetAdjacentTiles(from,
    onlyEmptyOrSteppable: 1, onlyWalkableTiles: 1)` filtre en place, et son iterateur
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` applique --
    APRES les gardes de walkability -- une PORTE D'ELEVATION `|srcElev - tile.Elevation| < 2`.

    Le foyer porte est donc `engine.battle_query.is_adjacent`, et surtout PAS
    `are_entities_adjacent` : les deux natifs sont DISTINCTS (cf. `#433-r1`) et seul le premier
    mirrore `IterateAdjacentTiles` -- le second porte un court-circuit d'IDENTITE qui compterait ici
    la cible elle-meme comme sa propre voisine.

    MESURE qui l'a attribuee (`bloodDante`, `bloodIntercessor`, sweep de 40 positions) : a `d = 6`
    le natif accepte 4 tuiles sur 6. Les DEUX refusees sont a elevation 2 et n'ont, a `d <= 5`, que
    des voisines a elevation 4 (ecart 2) ; les quatre acceptees ont toutes une voisine proche a
    ecart `<= 1`. Separation parfaite -- puis CONFIRMEE au decompile, pas seulement ajustee dessus.

    NON MODELISE, et c'est nomme : `onlyEmptyOrSteppable` / `onlyWalkableTiles` -- l'occupation et
    la walkability des voisines ne sont publiees par aucun canal cote DECISION. Le port ne retire
    donc pas les voisines occupees, ce qui ne peut qu'ELARGIR."""
    from .. import battle_query as bq                  # foyer d'`IterateAdjacentTiles` (#124)
    t = (int(tile[0]), int(tile[1]))
    for n in hexgeo.neighbors(t[0], t[1]):
        if not bq.is_adjacent(t, tuple(n), elev_by_pos):
            continue                                   # porte d'elevation |dElev| < 2
        if hexgeo.distance(tuple(n), tuple(unit_pos)) <= cfg_range:
            return True
    return False


def _ability_covers_tile(ability_id, visual_id, unit_pos, tile, elev_by_pos) -> bool:
    """UNE ability couvre-t-elle `tile` depuis `unit_pos` ? -- la composition des deux etages, mais
    evaluee sur la TUILE : `GetTilesInRange` puis le predicat `GetDynamicInvalidTargetReason`."""
    base = tiles_in_range_reach(ability_id, visual_id)
    if base is None:
        return False
    if hexgeo.distance(tuple(unit_pos), tuple(tile)) > base:
        return False
    gate = dynamic_target_gate_of(ability_id)
    if gate == GATE_FREE_ADJACENT_IN_CONFIG_RANGE:
        cfg = _config_range(ability_id)
        if cfg is None:
            return False
        if elev_by_pos:
            return _free_adjacent_gate_allows(unit_pos, tile, int(cfg), elev_by_pos)
        # DEGRADATION NOMMEE : sans canal d'elevation, on ne garde du gate que sa consequence de
        # DISTANCE (`config.range + 1`) -- borne SUPERIEURE exacte, mesuree a 2 faux positifs sur 40.
        return hexgeo.distance(tuple(unit_pos), tuple(tile)) <= int(cfg) + 1
    if gate == GATE_NOT_DERIVABLE:
        # cf. `ability_range_value` : la borne superieure n'est exploitable que si elle est bornee.
        return base != WHOLE_BOARD_REACH
    return True                                        # GATE_NONE / GATE_NOT_READ : aucun retrait


def is_tile_in_range_of_any_ability(unit_pos, tile, visual_id, feet_count: int = 1,
                                    ability_ids=None, elev_by_pos=None) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsTileInRangeOfAnyAbility(unit, tile)` -- mirror :

        if (UnitExtensions.GetFeetCount(unit, state) > 1) return true;      // MULTI-TUILES
        main  = EntityExtensions.GetMainTile(unit, state);
        set   = new OrderedSet<Tile>(main == null ? new List<Tile>() : main.ToList());
        tiles = <BattleQuery.attack @+0x20>.<slot 0xe>(unit, set, true);
        return tiles != null && tiles.Contains(tile);

    Le slot `0xe` du service `attack` (4e parametre de
    `IdunBattle.Core.Services.BattleQuery$$Initialize(processor, movement, tileQuery, ATTACK, ...)`)
    est `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange(unit, possiblePositions,
    includeNormalAttack)` -- surcharge a TROIS arguments, `includeNormalAttack` = le litteral `1` du
    call-site.

    ⚠ **L'ensemble de positions est le SINGLETON `{GetMainTile(unit)}`** : il n'y a AUCUN
    deplacement dans cette question, contrairement a ce qu'annoncait la fiche heritee de
    `#433-r4-r2` §7. Le `d = 5` qu'elle mesurait sur `tauMarksman` (arme de portee 3) vient de son
    ability `SeekerMissileFrequencyLock`, dont le `TargetingRange` est `RANGE_FROM_CONFIG` et le
    `constants.range` vaut 5 -- pas d'un rayon de mouvement.

    `feet_count > 1` -> `True` INCONDITIONNEL (1re ligne du natif). Cote DECISION le compte de pieds
    n'est publie par aucun canal (aucun champ gameconfig ne porte la taille d'une unite, cf.
    `engine.runner.components.get_feet_count`) : l'appelant passe 1 par defaut, et le residu est
    NOMME -- pour une unite MULTI-HEX le port rend `False` la ou le natif rend `True`, donc il
    attribue le bonus que le natif refuse.

    `unit_pos is None` (`GetMainTile` nul) -> l'`OrderedSet` est VIDE, `GetAllTilesInAbilityRange`
    rend un ensemble vide et `Contains` est faux. MESURE de ce regime : `--step seam` du probe, ou
    le movable set vide d'une unite hors tour rend `threatTiles = []` sur les 3 variantes.

    `elev_by_pos` -- le canal d'elevation de l'appelant. Fourni, il permet d'evaluer le gate
    `GetDynamicInvalidTargetReason` SUR LA TUILE (porte d'elevation de `GetFreeAdjacentTiles`) au
    lieu de le rabattre sur son rayon ; absent, le port se degrade sur le rayon, ce qui ne peut
    qu'ELARGIR (mesure : 2 faux positifs sur 40 pour `bloodDante`, 0 avec le canal)."""
    if int(feet_count or 1) > 1:
        return True
    if unit_pos is None or tile is None:
        return False
    if hexgeo.distance(tuple(unit_pos), tuple(tile)) > unit_threat_reach(visual_id, ability_ids):
        return False                          # hors de la borne SUPERIEURE : aucune ability ne porte
    # `includeNormalAttack: true` -- l'attaque normale, dont le `TargetingRange` se reduit a
    # `unit_weapon_range`, n'a PAS de gate dynamique : elle couvre son disque tel quel.
    weapon = unit_weapon_range(visual_id, None)
    if weapon is not None and hexgeo.distance(tuple(unit_pos), tuple(tile)) <= int(weapon):
        return True
    aids = _active_ability_ids(visual_id) if ability_ids is None else ability_ids
    return any(_ability_covers_tile(aid, visual_id, unit_pos, tile, elev_by_pos) for aid in aids)
