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


def ability_range_value(ability_id, visual_id) -> int | None:
    """La PORTEE effective d'une ability pour ce caster -- `TargetingQuery$$GetRange` restreint.

    L'ORDRE natif, respecte : `SetConfigValuesInTargetingOptions` pose `OverrideRange = config`
    **seulement si** `UseRangeFromConfig` ET `OverrideRange` encore vide ; puis `GetRange` fait
    `value = weaponRange` puis `value = OverrideRange.GetValueOrDefault(value)`. Un override du ctor
    GAGNE donc sur la config, et la config gagne sur l'arme.

    `only_adjacent` (resolu par `RangedBoolExtensions$$IsTrue`) ramene la portee EFFECTIVE a 1 : le
    consommateur (`TargetingQuery$$GetInvalidTargetReason`, volet portee) bascule alors sur
    `AreEntitiesAdjacent` au lieu de la comparaison de distance.

    Rend `None` -- « le port ne sait pas decider » -- dans QUATRE cas, tous natifs :
      * `TargetingRange` non RE-lu (ability absente des deux sources) ;
      * `UseWholeBoard` : le natif ne borne PAS la portee ici. Le port n'ELARGIT PAS pour autant
        (borne INFERIEURE assumee) -- MESURE (`probe_433_r4_r2_r1_ability_range.py --step seam`,
        `astraDreir`, dont `LeadingTheCharge` est whole-board) : le natif rend « hors portee » a
        TOUTE distance `d >= 2`, donc l'ability ne verse RIEN a la zone. Elargir aurait ete faux ;
      * `OverrideRangeFunc` : le delegue ECRASE la valeur et n'est pas resolu (meme arbitrage que
        `engine.runner.abilities.targeting.get_range`) ;
      * `UseRangeFromConfig` sans `constants.range` dans le kit."""
    rng = targeting_range_of(ability_id)
    if rng is None or rng.use_whole_board or rng.override_range_func:
        return None
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
    `AActiveAbility`, LoS et forme comprises) ; le port n'en garde que le RAYON. L'ecart est donc un
    sur-ensemble (le disque contient la zone reelle), a une exception mesuree pres : les gates par
    ability du natif (`GetInvalidCasterReason`, `CanCurrentlyBeUsed`) peuvent RETIRER une ability
    entiere -- residu `#433-r4-r2-r1` de la case-doc.

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


def is_tile_in_range_of_any_ability(unit_pos, tile, visual_id, feet_count: int = 1,
                                    ability_ids=None) -> bool:
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
    le movable set vide d'une unite hors tour rend `threatTiles = []` sur les 3 variantes."""
    if int(feet_count or 1) > 1:
        return True
    if unit_pos is None or tile is None:
        return False
    return hexgeo.distance(tuple(unit_pos), tuple(tile)) <= unit_threat_reach(visual_id, ability_ids)
