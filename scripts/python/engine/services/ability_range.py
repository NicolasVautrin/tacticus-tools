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

LE SUBSTRAT A UN FOYER UNIQUE : `engine.runner.abilities.targeting.targeting_options_for`, qui
consulte `ABILITY_CLASSES[aid].TARGETING_OPTIONS` puis `TARGETING_OPTIONS_UNPORTED`. Ce module n'a
plus de table a lui (#433-r4-r2-r1-r2-r2-r1-r1) : il portait `TARGETING_RANGE_BY_ABILITY`, le volet
PORTEE SEUL des 32 abilities actives du pool hors registre, pendant que leur masque `rules` restait
non lu -- deux sources pour une meme struct native de 0x40 octets, donc un FORK. Les 32 sont
desormais dans `TARGETING_OPTIONS_UNPORTED` avec leurs QUATRE champs (`rules`, `isSelfCasting`,
`range`, `forceMeleeTarget`), qui sortent tous du MEME appel de ctor.
"""
from __future__ import annotations

import gameconfig as GC
import hexgeo

import engine.services.ability_caster_gates as acg   # modules FRERES, pas `from . import` (#270-r4-r2)
import engine.services.movement_query as MQ
import engine.services.targeting_query as TQ
from ..entities.active_ability_type import ActiveAbilityType
from ..entities.active_abilities import kit_active_ability_ids
from ..runner.abilities.targeting import (NORMAL_ATTACK_TARGETING_OPTIONS,
                                          NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE,
                                          RANGED_BOOL_FALSE, RANGED_BOOL_IF_RANGED_CASTER,
                                          RANGED_BOOL_TRUE, TargetingRange, unit_weapon_range)
from ..runner.abilities.targeting_rule import TargetingRule as TR
from .. import battle_query as bq
from ..entities.traits.unit_trait import UnitTrait, has_trait
import engine.runner.abilities.targeting as TGT   # FORME B (module, pas nom) -- cf. `_options_of`
from ..entities.pathfinding.board import adjacent_neigh_by_pos


def _options_of(ability_id):
    """Les `TargetingOptions` RE-LUES de l'ability, par le foyer UNIQUE
    `engine.runner.abilities.targeting.targeting_options_for` (registre COMBAT, puis
    `TARGETING_OPTIONS_UNPORTED`). `None` = masque NON LU.

    ⚠ **L'ACCES EST ATTRIBUTAIRE (`TGT.targeting_options_for`), et ce n'est pas du style.** La
    docstring annoncait ici un « import PARESSEUX » alors que le corps appelait un nom LIE AU
    NIVEAU MODULE (forme A, `from ..runner.abilities.targeting import targeting_options_for`) : la
    prose disait donc l'inverse du code. Effet MESURE le 2026-08-07 -- les contre-factuels du
    dossier #447 substituent `TGT.targeting_options_for` (forme B) pour demander « et si le natif
    n'armait pas le bit 15 ? », et cette liaison A les DESARMAIT en silence. `master` en etait
    rouge : `test_447_r1_r1_zone_inclusion_decision_live.py` (3 contre-epreuves) et
    `probe_447_r1_r1_zone_inclusion_decision.py --step portee_non_lue` rendaient un masque
    « mute » valant encore `0x8004` -- c'est-a-dire bit 15 TOUJOURS ARME. C'est le vice
    « HISSER EN FORME A desarme un patch deja pose » du CLAUDE.md, pris sur le fait.
    La forme B ne coute rien en cascade et casse le meme cycle : `targeting_options_for` tire
    `handler`, qui importe les modules d'abilities, qui importent ce paquet."""
    try:
        aid = int(ability_id)
    except (TypeError, ValueError):
        return None
    return TGT.targeting_options_for(aid)


def targeting_range_of(ability_id) -> TargetingRange | None:
    """Le `TargetingRange` d'une ability -- le champ `range` de ses `TargetingOptions`.

    `None` = **non RE-lu** (et non « pas de portee ») -- l'appelant ne pose alors AUCUN terme."""
    opts = _options_of(ability_id)
    return getattr(opts, "range", None) if opts is not None else None


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

#: Gate LU, et LU COMME NE RETIRANT RIEN dans le regime que pose la question -- une tuile SANS
#: unite (#-r1-r1-a). Ce n'est PAS `GATE_NONE` : le gate existe et mord, mais sur des tuiles
#: OCCUPEES, pas sur la geometrie.
#:
#: CE QUI LE REND DECIDABLE, et c'est la lecture qui l'a donne : le troisieme predicat ne passe pas
#: au delegue l'element de la liste, mais l'entite qu'il en RESOUT --
#: `TargetingQuery.u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__2` fait
#: `entity = (rules & TargetIsTile) ? EntityExtensions.GetMainTile(elem) : UnitExtensions.GetUnit(elem)`,
#: puis `delegate.Invoke(caster, casterTiles, entity, GetTiles(entity) ?? GetTiles(elem))`. Or
#: `GetPossibleTargetTiles` force `onlyTiles: 1`, donc les elements SONT des tuiles : sur une tuile
#: vide, une ability sans `TargetIsTile` recoit `entity == null`, et une ability avec le recoit la
#: TUILE. Les cinq gates de ce regime commencent tous par un test qui, dans ce cas, rend `0`.
#:
#: SUR UNE TUILE OCCUPEE, le gate RETIRE -- et le port le modelise desormais (#433-r4-r2-r1-r1-a-r1),
#: par le parametre `occupant_by_pos` d'`is_tile_in_range_of_any_ability`.
#: ⚠ La phrase qui vivait ici (« l'occupation n'est publiee par aucun canal cote DECISION ») etait
#: PERIMEE : `tileMeta.tiles[].occupantId` la publie depuis le capteur #175-r, et il INVOQUE
#: `IdunBattle.Entities.UnitExtensions$$GetUnit(TileEntity, state)`, c.-a-d. exactement le natif que
#: lit `1213 DeathOnTheWind`. C'est ce constat perime qui tenait le residu classe `BLOCAGE: capteur`,
#: donc ECARTE au dispatch. Canal absent -> aucun retrait, comme avant.
GATE_VALID_ON_EMPTY_TILE = "valid_on_empty_tile"

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
    # `LightOfSanguiniusAbility$$GetDynamicInvalidTargetReason` /
    # `HammerOfWrathAbility$$GetDynamicInvalidTargetReason`.
    ActiveAbilityType.LightOfSanguinius: GATE_FREE_ADJACENT_IN_CONFIG_RANGE,  # 1177
    ActiveAbilityType.HammerOfWrath: GATE_FREE_ADJACENT_IN_CONFIG_RANGE,  # 1153
    # --- LU, NON derivable hors etat de bataille ---------------------------------------------
    ActiveAbilityType.Waaagh: GATE_NOT_DERIVABLE,  # 1058 -- GetPossibleMovementTiles (selecteur DSL)
    ActiveAbilityType.ExemplarOfTheKauyon: GATE_NOT_DERIVABLE,  # 1087 -- TileExtensions$$IsFreeTile + slot 0x7a
    ActiveAbilityType.AlphaWarrior: GATE_NOT_DERIVABLE,  # 1112 -- IsInSynapseRange(caster, target)
    ActiveAbilityType.DutyEternal: GATE_NOT_DERIVABLE,  # 1158 -- DSLSelectors$$ThreeTileUnitSpawnShape
    ActiveAbilityType.BlackRage: GATE_NOT_DERIVABLE,  # 1163 -- GetPossibleMovementTiles (selecteur DSL)
    ActiveAbilityType.HeroicFusillade: GATE_NOT_DERIVABLE,  # 1180 -- GetSurroundingTiles + GetMinDistance
    ActiveAbilityType.VigilanceEternal: GATE_NOT_DERIVABLE,  # 1202 -- AreEntitiesAdjacent, sinon mouvement
    ActiveAbilityType.LeadingTheCharge: GATE_NOT_DERIVABLE,  # 1204 -- DSLSelectors$$TilesUnitCanMoveToChargeTarget
    # --- LU (#-r1-r1-a) : le gate ne mord QUE sur une tuile OCCUPEE --------------------------
    # Les sept gates `UseWholeBoard` restants ont ete lus ; AUCUN ne borne une distance. Chacun
    # commence par un test qui, sur l'`entity` que `b__2` resout depuis une tuile VIDE (`null` sans
    # `TargetIsTile`, la tuile elle-meme avec), rend `0` -- donc ne retire pas la tuile.
    ActiveAbilityType.TunnelingHorror: GATE_VALID_ON_EMPTY_TILE,  # 1011
    #     `TunnelingHorrorAbility$$GetDynamicInvalidTargetReason` :
    #     `DSLTriggers$$HasEffect(DSLSelectors$$Get(sel, target), 0x459)` -> `2` ; sinon parcourt
    #     `casterTiles` et rend `2` a la PREMIERE `TileExtensions$$IsTemporary`, `0` si aucune.
    ActiveAbilityType.SkyStrike: GATE_VALID_ON_EMPTY_TILE,  # 1025
    #     `SkyStrikeAbility$$GetDynamicInvalidTargetReason` :
    #     `moved = UnitExtensions$$DidMove(caster) || GetMainTile(caster) != casterTiles[0]` ;
    #     `moved && !<slot 0x62>(casterTiles, targetTiles)` -> `0x10` ; sinon valide si ce meme slot
    #     ou si `<slot 0x51>(targetTiles, 1, 1, 0).Count > 0` (les VOISINES libres et walkables).
    #     Le consommateur passe `casterTiles = {GetMainTile(unit)}` et interroge une unite qui n'a
    #     pas encore joue -> `moved` est faux. ECART NOMME : une tuile sans aucune voisine libre.
    ActiveAbilityType.SporeMineLauncher: GATE_VALID_ON_EMPTY_TILE,  # 1145 -- `TileExtensions$$HasSteppableUnit`
    #     (= `GetUnit(tile) != null && HasTrait(0x1b)`) puis `UnitExtensions$$IsEnemy` -> `2`.
    ActiveAbilityType.EntropyCannons: GATE_VALID_ON_EMPTY_TILE,  # 1168 -- `EntityExtensions$$IsUnit(entity)`
    #     d'abord (`null` -> `0`, LU : la fonction teste `entity == 0` avant tout) ; le reste teste
    #     `DSLTriggers$$IsInTeamContagionsOfNurgleAura` / `HasNegativeModifier` sur la CIBLE.
    ActiveAbilityType.SquigLaunchas: GATE_VALID_ON_EMPTY_TILE,  # 1200 -- meme premiere ligne `IsUnit(entity)`
    #     (`0` = valide) ; le reste compte les Orks/allies ADJACENTS AU CASTER.
    ActiveAbilityType.SquigMine: GATE_VALID_ON_EMPTY_TILE,  # 1201 -- `HasEffect(tile, 0x5a1) ||
    #     TileExtensions$$HasSteppableUnit(tile)` -> `2`, sinon `0`.
    ActiveAbilityType.DeathOnTheWind: GATE_VALID_ON_EMPTY_TILE,  # 1213 -- `UnitExtensions$$GetUnit(tile)`
    #     nul -> `0` ; sinon exige `GetNumAttacksReceivedThisTurn(unit) != 0`.
    # --- SURCHARGE etablie au runtime, corps NON LU par cette tranche -------------------------
    # Toutes NON-`UseWholeBoard` : leur borne superieure reste BORNEE, donc ne pas retrecir dessus
    # coute au plus le disque de leur portee (cf. `dynamic_target_gate_reach`).
    ActiveAbilityType.Repair: GATE_NOT_READ,  # 28
    ActiveAbilityType.AdaptiveStrategy: GATE_NOT_READ,  # 1005
    ActiveAbilityType.SendInTheNextWave: GATE_NOT_READ,  # 1016
    ActiveAbilityType.FoulInfusion: GATE_NOT_READ,  # 1038
    ActiveAbilityType.RammingSpeed: GATE_NOT_READ,  # 1059
    ActiveAbilityType.FightingRetreat: GATE_NOT_READ,  # 1081
    ActiveAbilityType.InspiredToGreatness: GATE_NOT_READ,  # 1082
    ActiveAbilityType.AttemptedPossession: GATE_NOT_READ,  # 1101
    ActiveAbilityType.RadBombardment: GATE_NOT_READ,  # 1116
    ActiveAbilityType.DefendTheDivineWork: GATE_NOT_READ,  # 1117
    ActiveAbilityType.Repair_GalvanicField: GATE_NOT_READ,  # 1119
    ActiveAbilityType.TheQuickening: GATE_NOT_READ,  # 1151
    ActiveAbilityType.MindControl: GATE_NOT_READ,  # 1164
    ActiveAbilityType.BloodChalice: GATE_NOT_READ,  # 1175
    ActiveAbilityType.CultDemagogue: GATE_NOT_READ,  # 1179
    ActiveAbilityType.ExcruciatingFrequencies: GATE_NOT_READ,  # 1197
    # `1100 SorcerousFacade` et `1143 ForwardSpotter` NE FIGURENT PLUS ICI : elles surchargent bien
    # le slot, mais leur gate n'est JAMAIS atteint -- `GetPossibleTargetTiles` court-circuite en
    # amont sur leur masque `rules` (cf. `target_tiles_zone_is_empty`).
}


# ------------------------------------------------------------------------------------------------
# L'etage AMONT : le court-circuit de `GetPossibleTargetTiles` (#-r1-r1-a)
#
# `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetTiles` teste le masque `rules` AVANT
# d'appeler `GetRange` :
#
#     if ((options.Rules >> 0xa & 1) != 0            // TargetIsFriendly
#         && (options.Rules >> 0xe & 1) == 0)        // et PAS TargetIsEnemy
#         return new OrderedSet<Tile>();             // VIDE -- ni portee, ni gate
#
# Une ability qui ne cible QUE des allies ne contribue donc AUCUNE tuile a
# `AttackQuery$$GetAllTilesInAbilityRange`, quelle que soit sa portee. C'est ce qui separe
# `1100 SorcerousFacade` et `1143 ForwardSpotter` des autres `UseWholeBoard` : elles surchargent
# bien `GetDynamicInvalidTargetReason` (fait runtime), mais ce gate n'est JAMAIS atteint.
#
# Le test est PUREMENT STATIQUE (le masque est celui du ctor), donc EXACT -- pas une borne.
# ------------------------------------------------------------------------------------------------

#: `TargetingRule.TargetIsFriendly` / `TargetIsEnemy` -- les deux seuls bits que lit le
#: court-circuit. Nommes ici plutot qu'importes : `engine.runner.abilities.targeting` ne les expose
#: que dans sa table de commentaires, et ce module ne doit pas dependre de son enumeration interne.
_TARGET_IS_FRIENDLY = 1 << 0xA
_TARGET_IS_ENEMY = 1 << 0xE


def target_tiles_zone_is_empty(ability_id) -> bool:
    """Le court-circuit `TargetIsFriendly && !TargetIsEnemy` de `GetPossibleTargetTiles`.

    `False` aussi quand le masque n'est PAS LU : le port ne retire alors rien -- meme arbitrage que
    `GATE_NOT_READ`, l'ecart ne peut qu'ELARGIR.

    ⚠ Cette fonction lisait le SEUL `ABILITY_CLASSES`, donc rendait `False` pour les 32 abilities du
    pool hors registre alors meme que leur volet PORTEE etait lu (#433-r4-r2-r1-r2-r2-r1-r1). Elle
    passe par `_options_of`, le foyer unique : **6** d'entre elles portent le court-circuit
    (1005, 1038, 1039, 1049, 1061, 1175) et ne contribuent donc AUCUNE tuile a
    `AttackQuery$$GetAllTilesInAbilityRange`."""
    opts = _options_of(ability_id)
    rules = getattr(opts, "rules", None) if opts is not None else None
    if rules is None:
        return False
    return bool(int(rules) & _TARGET_IS_FRIENDLY) and not bool(int(rules) & _TARGET_IS_ENEMY)


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
    comportement de la tranche precedente pour les 16 abilities non-whole-board concernees, plutot
    que de leur substituer un `None` qui les retirerait toutes de la zone d'un coup.

    `GATE_VALID_ON_EMPTY_TILE` ne retire rien non plus, mais pour une raison LUE et non par defaut :
    le gate rend `0` sur une tuile sans unite."""
    gate = dynamic_target_gate_of(ability_id)
    if gate == GATE_FREE_ADJACENT_IN_CONFIG_RANGE:
        cfg = _config_range(ability_id)
        return None if cfg is None else int(cfg) + 1
    if gate == GATE_NOT_DERIVABLE:
        return None
    return WHOLE_BOARD_REACH   # GATE_NONE, GATE_NOT_READ, GATE_VALID_ON_EMPTY_TILE : aucun retrait


def _config_range(ability_id) -> int | None:
    """`AbilityConfiguration.GetNumberConstant(0x16 range)` = `constants.range` de gameconfig --
    ce que `IdunBattle.Entities.Abilities.AActiveAbility$$SetConfigValuesInTargetingOptions` recopie
    dans `options.Range.OverrideRange` quand `UseRangeFromConfig` est pose.

    Le foyer de la lecture est `ability_caster_gates.try_get_number_constant` (mirror
    d'`IdunBattle.Configuration.AbilityConfiguration$$TryGetNumberConstant`), partage avec les
    quatre autres constantes que les gates CASTER interrogent -- une seule fonction pour la meme
    table `AbilityConstantType`."""
    return acg.try_get_number_constant(ability_id, "range")


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

    ⚠ **L'ORDRE des deux derniers tests est celui du NATIF, et il n'est PAS celui de `get_range`**
    (#419-r1-tr14-r5-r2-r1-r2-r1-r1-r3). La cascade de `GetTilesInRange`, relue a l'octet :

        if      ((int)range < 0)      -> OrderedSet VIDE
        else if (range.UseWholeBoard) -> <IBattleQuery slot 0x69>()  = GetAllTiles()
        else if ((int)range == 0)     -> casterTiles  (ou VIDE si le bit 15 de `rules` est absent)
        else if (range.OnlyAdjacent)  -> tuiles ADJACENTES
        else                          -> GetTilesInRadius(casterTiles, (int)range, ...)

    Une portee NULLE l'emporte donc sur `OnlyAdjacent` : la zone est alors `casterTiles` (rayon 0),
    pas les adjacentes (rayon 1). C'est l'inverse de `GetInvalidTargetReason`, qui teste
    `OnlyAdjacent` EN PREMIER et ne lit `(int)range` que dans l'autre branche -- deux consommateurs
    du MEME `Range`, deux ordres. Les aligner « par symetrie » serait un faux dans un sens ou dans
    l'autre.

    Rend `None` -- « le port ne sait pas decider » -- dans TROIS cas, tous natifs :
      * `TargetingRange` non RE-lu (ability absente des deux sources) ;
      * `OverrideRangeFunc` : le delegue ECRASE la valeur et n'est pas resolu (meme arbitrage que
        `engine.runner.abilities.targeting.get_range`) ;
      * `UseRangeFromConfig` sans `constants.range` dans le kit.

    ⚠ Ce `None` sur portee NON OBSERVABLE est CORRECT ici et ne doit PAS etre aligne sur le tri-etat
    de `get_range` : la valeur est lue AVANT `OnlyAdjacent`, donc sans elle on ne sait pas quelle
    branche prendre. Un cran de test l'interdit (#419-r1-tr14-r5-r2-r1-r2-r1-r1 §3)."""
    terms = _range_terms(targeting_range_of(ability_id), ability_id, visual_id)
    if terms is None:
        return None
    value, only_adjacent, use_whole_board = terms
    if use_whole_board:
        return WHOLE_BOARD_REACH
    if value is None:
        return None
    if int(value) == 0:
        return 0                                      # `(int)range == 0` -> `casterTiles`, AVANT `OnlyAdjacent`
    return 1 if only_adjacent else int(value)


def _range_terms(rng, ability_id, visual_id):
    """Les TROIS termes que `TargetingQuery$$GetRange` rend, dans l'ordre natif de leur resolution :
    `((int)range, Range.OnlyAdjacent, Range.UseWholeBoard)`.

    FOYER UNIQUE de la resolution de la portee : `tiles_in_range_reach` (le RAYON) et
    `tiles_in_range_zone_contains` (l'ENSEMBLE) le partagent, sinon ils seraient deux sources pour
    la meme lecture -- exactement le fork que `#433-r4-r2-r1-r2-r2-r1-r1` a supprime entre la table
    de portee et les masques.

    `None` (le triplet entier) = `TargetingRange` non RE-lu ou `OverrideRangeFunc` pose. Un `value`
    a `None` DANS le triplet = portee non observable, mais les deux autres termes valent.

    `UseWholeBoard` court-circuite : `GetRange` rend `{ Range = 1, OnlyAdjacent = false,
    UseWholeBoard = true }` sans evaluer ni `only_adjacent` ni la portee d'arme."""
    if rng is None or rng.override_range_func:
        return None
    if rng.use_whole_board:
        return (1, False, True)
    ov = rng.override_range
    if ov is None and rng.use_range_from_config:
        ov = _config_range(ability_id)
    if ov is None and not rng.use_range_from_config:
        ov = unit_weapon_range(visual_id, None)       # `stats` absent -> ExtraRange = 0 (cf. mirror)
    only_adjacent = _ranged_bool_is_true(rng.only_adjacent, visual_id)
    return (None if ov is None else int(ov), only_adjacent, False)


# ------------------------------------------------------------------------------------------------
# L'ENSEMBLE de `GetTilesInRange`, la ou `tiles_in_range_reach` n'en rend que le RAYON
# (#433-r4-r2-r1-r2-r2-r1-r1-r1)
#
# Un rayon ne peut pas dire si la tuile du CASTER est dans la zone : `d <= reach` inclut toujours
# `d = 0`. Le natif, lui, la traite branche par branche -- et c'est le PARAMETRE de la branche, pas
# une regle globale, qui decide. Cascade relue a l'octet sur
# `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange`, avec le SLOT `IBattleQuery` de chaque
# branche generatrice et sa signature :
#
#   (int)range < 0            -> `OrderedSet` VIDE
#   range.UseWholeBoard       -> <slot 0x69> `GetAllTiles()`                      -- INCLUT tout
#   (int)range == 0           -> `rules >> 0xf & 1` ? `new OrderedSet(casterTiles)` : VIDE
#   range.OnlyAdjacent        -> <slot 0x51> `BattleQuery$$GetAdjacentTiles(casterTiles,
#                                  onlyEmptyOrSteppable: false, onlyWalkableTiles: !bit43,
#                                  allowTemporary: true)`                         -- EXCLUT toujours
#   rules & TargetIsAtRange   -> <slot 0x64> `BattleQuery$$GetTilesAtDistance(casterTiles,
#                                  (int)range, onlyEmptyOrSteppable: false)`      -- ANNEAU `d == v`
#   sinon                     -> <slot 0x67> `BattleQuery$$GetSurroundingTiles(casterTiles,
#                                  (int)range, onlyEmptyOrSteppable: false, onlyWalkable: !bit43,
#                                  onlyMovable: false, includeCenter: `rules >> 0xf & 1`)`
#
# Les slots sont attribues par la SIGNATURE de leur surcharge (6 parametres nommes
# `center/distance/onlyEmptyOrSteppable/onlyWalkable/onlyMovable/includeCenter` pour `0x67`, 3 pour
# `0x64`, 4 pour `0x51`), pas par un comptage a l'oeil. `includeCenter` est le SEUL parametre qui
# rende la tuile source : `BattleQuery.u003CIterateSurroundingTilesu003Ed__117$$MoveNext` delegue a
# `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`, dont le
# triple balayage en coordonnees CUBE (`x+y+z == 0`, chaque axe dans `[c-d, c+d]` = le disque hex)
# ne garde une tuile que si `includeCenter || tile != center` ; et la surcharge LISTE
# (`BattleQuery$$GetSurroundingTiles`, celle que prend `casterTiles`) RE-filtre en plus le resultat
# par `ListExtensions$$FilterInPlace` sur la liste des centres quand `includeCenter` est faux.
#
# ⚠ ET LA CASCADE N'EST PAS LE DERNIER MOT. `TargetingQuery$$GetPossibleTargetsForOptions` --
# l'appelant que `GetPossibleTargetTiles` emprunte -- RE-AJOUTE `casterTiles` juste apres, par DEUX
# fois et avant les trois `RemoveAll` :
#
#     tiles = GetTilesInRange(...)
#     if (rules >> 0xf & 1)        tiles.<IOrderedSet slot 0>(casterTiles)   // CasterIsPossibleTarget
#     if (rules & 0x200000000000000) tiles.<IOrderedSet slot 0>(casterTiles) // TargetIsCasterOrEnemy
#
# Le slot 0 est un AJOUT, et c'est une LECTURE, pas une deduction de nom :
# `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFor` l'invoque sur le meme couple
# (interface, receveur) avec `EntityExtensions$$IterateTiles(unit)` -- le movable set d'une unite
# CONTIENT sa tuile courante, donc le slot ne peut pas etre un retrait. Le slot 1 de la meme
# interface est `RemoveAll(Predicate<T>)`, celui du filtre de walkability.
#
# CONSEQUENCE, et c'est la reponse a « la regle n'est pas uniforme » : elle l'est au niveau du
# CONSOMMATEUR. La tuile du caster est dans la zone ssi `UseWholeBoard`, ou `CasterIsPossibleTarget`,
# ou `TargetIsCasterOrEnemy` -- les branches `(int)range == 0` et `GetSurroundingTiles` lisent le
# MEME bit 15 que le premier ajout, elles n'en sont pas des exceptions. `OnlyAdjacent` et
# `TargetIsAtRange`, eux, ne rendent JAMAIS la source d'eux-memes : seul l'ajout aval l'y remet.
#
# PORTEE DE CE MIRROR, mesuree sur les 140 masques lus : `CasterIsPossibleTarget` = 17 porteurs,
# `TargetIsCasterOrEnemy` = 2 (19 en tout), et **AUCUN** des 18 profils d'attaque normale. Le bit
# `TargetIsAtRange` a **0** porteur : sa branche est un mirror STRUCTUREL, NON CONFRONTE -- si elle
# se met a mordre, c'est qu'une ability neuve a ouvert le regime, et il faut alors la confronter.
#
# ⚠ REGIME COUVERT : `casterTiles` est le SINGLETON `{GetMainTile(unit)}` (cf.
# `is_tile_in_range_of_any_ability`). Pour un caster MULTI-TUILES, `GetAdjacentTiles` versrait les
# tuiles du caster adjacentes entre elles -- hors regime, et deja couvert par le `feet_count > 1`
# qui rend `True` inconditionnellement en amont.
# ------------------------------------------------------------------------------------------------


def _bit(rules, bit) -> bool:
    """`(rules >> n & 1) != 0` -- `False` quand le masque n'est PAS LU, meme convention permissive
    que le reste du module."""
    return rules is not None and bool(int(rules) & int(bit))


def verse_par_ajout_aval(rules, distance) -> bool:
    """La tuile est-elle versee dans la zone par l'un des DEUX `AddRange(casterTiles)` de
    `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` ?

    FOYER UNIQUE de cette clause (#447-r1-r1-r1) : `_zone_contains_distance` s'en sert pour DIRE que
    la tuile est dans la zone, et `_ability_covers_tile` pour savoir qu'elle n'a PAS traverse le
    `RemoveAll` de walkability -- deux lectures d'un meme fait natif, donc une seule ecriture.

    Les deux ajouts vivent chez l'APPELANT de `GetTilesInRange` et versent `casterTiles`, donc la
    clause porte sur `d == 0` dans le regime SINGLETON de `is_tile_in_range_of_any_ability`."""
    return int(distance) == 0 and (_bit(rules, TR.CasterIsPossibleTarget)
                                   or _bit(rules, TR.TargetIsCasterOrEnemy))


def _zone_contains_distance(rules, value, only_adjacent: bool, use_whole_board: bool,
                            distance) -> bool | None:
    """La zone de `GetTilesInRange` PUIS les deux `AddRange(casterTiles)` de
    `GetPossibleTargetsForOptions`, evaluees a la DISTANCE `distance` d'un caster SINGLETON.

    `value` = `(int)range`, la valeur rendue par `TargetingQuery$$GetRange` (jamais le rayon
    EFFECTIF : `OnlyAdjacent` est un champ separe, cf. `Range`). `None` = portee non decidable ->
    la fonction rend `None`, sauf si l'ajout aval mord (le caster est ajoute quelle que soit la
    portee)."""
    d = int(distance)
    if use_whole_board:
        in_range = True                                   # <slot 0x69> `GetAllTiles()`
    elif value is None:
        in_range = None                                   # portee non decidable
    elif int(value) < 0:
        in_range = False                                  # `OrderedSet` VIDE
    elif int(value) == 0:
        in_range = d == 0 and _bit(rules, TR.CasterIsPossibleTarget)
    elif only_adjacent:
        in_range = d == 1                                 # <slot 0x51>, EXCLUT `casterTiles`
    elif _bit(rules, TR.TargetIsAtRange):
        in_range = d == int(value)                        # <slot 0x64>, ANNEAU
    else:                                                 # <slot 0x67>, `includeCenter` = bit 15
        in_range = d <= int(value) and (d != 0
                                        or _bit(rules, TR.CasterIsPossibleTarget))
    if verse_par_ajout_aval(rules, d):
        return True                                       # les deux ajouts, APRES `GetTilesInRange`
    return in_range


def tiles_in_range_zone_contains(ability_id, visual_id, distance) -> bool | None:
    """`GetTilesInRange(ability).Contains(tile)` pour une tuile a `distance` du caster -- le pendant
    ENSEMBLISTE de `tiles_in_range_reach`, qui n'en rend que le rayon.

    Meme cascade, meme ordre, meme resolution de la portee (c'est `tiles_in_range_reach` qui la
    porte) : la valeur `(int)range` est re-derivee ici par le MEME chemin, et les deux fonctions
    restent d'accord par construction -- `tiles_in_range_reach` est la borne SUPERIEURE de cet
    ensemble, jamais une seconde source.

    `None` = « le port ne sait pas decider », exactement les trois cas de `tiles_in_range_reach`."""
    return zone_contains_for_options(_options_of(ability_id), ability_id, visual_id, distance)


def zone_contains_for_options(options, ability_id, visual_id, distance) -> bool | None:
    """La MEME zone, mais pour un masque **EFFECTIF** fourni par l'appelant plutot que relu du
    registre par son `ability_id`.

    POURQUOI CETTE PORTE (#447-r1, et c'est un DEFAUT MESURE, pas un confort) : un appelant qui
    porte un masque MUTE -- une contre-epreuve qui desarme un bit, un override runtime -- et qui
    passait par `tiles_in_range_zone_contains` voyait sa mutation **silencieusement ignoree**, la
    fonction rechargeant le masque du registre depuis l'`ability_id`. Une contre-epreuve devenue
    inoperante rend alors un VERT qui ne prouve rien.

    L'`ability_id` reste requis : il ne sert QU'A resoudre le `TargetingRange` (`UseRangeFromConfig`
    lit la config de l'ability), jamais les `rules`.

    ⚠ UN `TargetingRange` NON RE-LU NE COURT-CIRCUITE PAS (#447-r1-r1). Les deux `AddRange(
    casterTiles)` vivent dans `GetPossibleTargetsForOptions`, l'APPELANT de `GetTilesInRange`, et ne
    consultent NI la portee NI la branche prise : une ability dont le `TargetingRange` sort d'un
    preset non resolu met quand meme la tuile du caster dans ses cibles possibles des que le bit 15
    est arme. Le triplet manquant est donc rabattu sur `(None, False, False)` -- portee NON
    DECIDABLE, ce que `_zone_contains_distance` rend deja par `None` a toute autre distance -- au
    lieu d'un `return None` qui retirait AUSSI l'ajout aval. MESURE (`probe_447_r1_r1 --step
    portee_non_lue`, `1215 InstrumentsOfVengeance` greffee sur `darkaAsmodai`, cul-de-sac) : le
    natif VERSE la tuile source, le port n'en versait AUCUNE -- ecart RESTRICTIF."""
    terms = _range_terms(getattr(options, "range", None) if options is not None else None,
                         ability_id, visual_id)
    value, only_adjacent, use_whole_board = terms if terms is not None else (None, False, False)
    return _zone_contains_distance(getattr(options, "rules", None) if options is not None else None,
                                   value, only_adjacent, use_whole_board, distance)


def normal_attack_zone_contains(normal_attack_id, visual_id, distance) -> bool | None:
    """La meme zone, pour le terme `includeNormalAttack: true` de
    `AttackQuery$$GetAllTilesInAbilityRange`.

    Les options sont celles de SON type (`NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE`, defaut = le
    generique `69`) -- masque ET portee : le profil `69` porte `RANGE_ADJACENT_IF_MELEE_CASTER`
    (`onlyAdjacent = IfNotRangedCaster`, valeur = `unit_weapon_range`), mais tous ne le partagent
    pas (`1146` porte `RANGE_ADJACENT`, dont l'`overrideRange = 1` GAGNE sur l'arme). C'est
    `_range_terms` qui tranche, comme pour une ability.

    AUCUN des 18 masques lus ne porte `CasterIsPossibleTarget` ni `TargetIsCasterOrEnemy` : la
    tuile du caster est donc exclue quel que soit le profil -- `d == 1` pour un caster de melee,
    `1 <= d <= portee d'arme` pour un caster a distance. Le triplet manquant est rabattu comme dans
    `zone_contains_for_options` (meme regle, un seul foyer) ; son gisement est VIDE ici, les 18
    profils portant tous un `TargetingRange` RE-lu."""
    opts = (NORMAL_ATTACK_TARGETING_OPTIONS if normal_attack_id is None
            else NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE.get(int(normal_attack_id),
                                                             NORMAL_ATTACK_TARGETING_OPTIONS))
    terms = _range_terms(opts.range, None, visual_id)
    value, only_adjacent, use_whole_board = terms if terms is not None else (None, False, False)
    return _zone_contains_distance(opts.rules, value, only_adjacent, use_whole_board, distance)


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
        donc verser le plateau ferait 40 faux POSITIFS la ou `None` en fait 0.

    Le court-circuit AMONT (`target_tiles_zone_is_empty`) precede les deux etages : il rend `None`
    -- ici « l'ability ne contribue AUCUNE tuile », un fait EXACT, et non « le port ne sait pas ».
    Les deux se confondent pour l'appelant (il ne pose aucun terme), et c'est voulu : verser un
    rayon nul demanderait au consommateur de distinguer « rayon 0 » de « pas de zone »."""
    if target_tiles_zone_is_empty(ability_id):
        return None
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
    """Les ids d'ability ACTIVE du kit gameconfig de l'unite (`activeAbilities`, noms -> enum).

    DELEGUE au foyer `entities.active_abilities.kit_active_ability_ids` (#477-r29) : la meme
    conversion existait ici et allait etre reecrite pour le predicat de `RadSaturationPlaybook` --
    deux copies d'un seul substrat sont le fork que la doctrine `check-own-port` interdit."""
    return kit_active_ability_ids(visual_id)


_REACH_CACHE: dict = {}    # {visual_id: reach} -- kit gameconfig = STATIQUE (aucune dependance d'etat)


def _gated_out(ability_id, ability_state, caster=None) -> bool:
    """L'ability est-elle ANNULEE par l'un des QUATRE gates CASTER (#433-r4-r2-r1-r1-c, puis
    #433-r4-r2-r1-r2-r2-r1-r1-r1-r4) ?

    Foyer : `engine.services.ability_caster_gates.gates_allow` -- les quatre gates que
    `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange` (surcharge 4 arguments)
    evalue AVANT les slots 9/10, et qui font rendre un ensemble VIDE. `ability_state` = la table
    `{abilityId: ligne}` de `decisionView.units[].abilities[]` ; absente, seul `IsDisabled`
    (derivable du kit) peut mordre. `caster` = le `CasterSubstrate` du 4e gate ; absent, aucune de
    ses onze regles ne peut refuser."""
    st = (ability_state or {}).get(int(ability_id)) if ability_state else None
    return not acg.gates_allow(ability_id, st, caster)


def unit_threat_reach(visual_id, ability_ids=None, ability_state=None,
                      normal_attack_id=None, caster=None) -> int:
    """Le RAYON de `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange(unit,
    {GetMainTile(unit)}, includeNormalAttack: true)` -- l'UNION des zones de portee de l'unite
    depuis sa tuile COURANTE, modelisee par le max de ses portees.

    Les deux termes de l'union, dans l'ordre du natif :
      * `includeNormalAttack: true` -> l'attaque NORMALE. Son `TargetingRange` est
        `RANGE_ADJACENT_IF_MELEE_CASTER` (`onlyAdjacent = IfNotRangedCaster`), ce qui se reduit
        EXACTEMENT a `unit_weapon_range` : portee d'arme pour un caster a arme a distance,
        adjacence (1) sinon. ⚠ Elle N'EST PAS un cas a part cote natif : la lambda
        `AttackQuery.u003Cu003Ec__DisplayClass39_1$$u003CGetAllTilesInAbilityRangeu003Eb__0`
        enumere l'`ActiveAbilityComponent` ENTIER et `includeNormalAttack` ne fait que LEVER le
        filtre `!IsRegularAttack` -- son entree passe donc par les MEMES quatre gates CASTER, d'ou
        `normal_attack_id` ;
      * chaque ability ACTIVE du kit dont la portee est derivable (`ability_range_value`).

    APPROXIMATION NOMMEE : le natif rend un ENSEMBLE de tuiles (les slots 9/10 de chaque
    `AActiveAbility`, LoS et forme comprises) ; le port n'en garde que le RAYON. Le predicat de
    ciblage dynamique (`GetDynamicInvalidTargetReason`) est desormais MODELISE -- c'est ce qui borne
    la zone d'une ability `UseWholeBoard` (cf. `ability_range_value`) -- et les QUATRE gates CASTER
    en AMONT le sont aussi depuis `#433-r4-r2-r1-r1-c` puis `#433-r4-r2-r1-r2-r2-r1-r1-r1-r4`
    (`ability_state` + `caster`, cf.
    `engine.services.ability_caster_gates`). Reste NON modelise le 2e predicat de
    `GetPossibleTargetsForOptions` : `b__1` retire les tuiles obscurcies par le terrain (residu
    `#433-r4-r2-r1-r2`).

    `WHOLE_BOARD_REACH` se propage par le `max` : une seule ability `UseWholeBoard` SANS gate suffit
    a rendre toute tuile du plateau menacee, ce qui est exactement `GetAllTiles()`.

    `ability_state` -- l'etat LIVE par ability (`decisionView.units[].abilities[]`). Fourni, il
    RETIRE de l'union les abilities que les quatre gates CASTER annulent (cf. `_gated_out`) : c'est
    le seul terme de cette fonction qui depende de l'ETAT, donc le cache est COURT-CIRCUITE des
    qu'il est present.

    `caster` -- le `CasterSubstrate` du 4e gate (#433-r4-r2-r1-r2-r2-r1-r1-r1-r4). Comme
    `ability_state`, c'est un terme d'ETAT : il COURT-CIRCUITE le cache.

    Cache par `visual_id` quand ni le kit ni l'etat ne sont forces par l'appelant : les deux
    sources sont alors STATIQUES (gameconfig + tables lues au decompile), donc le resultat ne
    depend d'AUCUN etat de bataille -- et l'appelant est un SWEEP de positions, qui le
    redemanderait a chaque tuile."""
    cacheable = ability_ids is None and not ability_state and caster is None
    if cacheable:
        got = _REACH_CACHE.get(visual_id)
        if got is not None:
            return got
    reach = 0
    if normal_attack_id is None or not _gated_out(normal_attack_id, ability_state, caster):
        w = unit_weapon_range(visual_id, None)
        reach = 0 if w is None else int(w)
    for aid in (_active_ability_ids(visual_id) if ability_ids is None else ability_ids):
        if _gated_out(aid, ability_state, caster):
            continue                                  # `GetAllTilesInAbilityRange` -> ensemble VIDE
        v = ability_range_value(aid, visual_id)
        if v is not None and v > reach:
            reach = int(v)
    if cacheable:
        _REACH_CACHE[visual_id] = reach
    return reach


def _free_adjacent_gate_allows(unit_pos, tile, cfg_range: int, elev_by_pos,
                               neigh_by_pos=None) -> bool:
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
    t = (int(tile[0]), int(tile[1]))
    # Le pool reste la couronne hex, mais `is_adjacent` le REDUIT a la liste STOCKEE des que le
    # canal est la (#433-r4-r1-r4-r2) : `pool ^ N[t] == N[t]` puisque `N subset G`. Le natif, lui,
    # itere directement `GetAdjacentTiles(from, 1, 1)` -- meme ensemble, ordre non observable ici
    # (le predicat est un `Any`).
    for n in hexgeo.neighbors(t[0], t[1]):
        if not bq.is_adjacent(t, tuple(n), elev_by_pos, neigh_by_pos):
            continue                                   # porte d'elevation |dElev| < 2
        if hexgeo.distance(tuple(n), tuple(unit_pos)) <= cfg_range:
            return True
    return False


def _has_indirect_fire(visual_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasTrait(caster, 0x3ed)`, substrat gameconfig -- le
    litteral que `IdunBattle.Core.Services.TargetingQuery$$GetTilesObscuringTerrain` teste avant de
    poser le volet ELEVATION du `ObscuringType`."""
    return has_trait((GC.unit(visual_id or "") or {}).get("traits"), UnitTrait.IndirectFire)


def _obscured(board, unit_pos, tile, rules, visual_id,
              caster_team=None, team_by_pos=None) -> bool:
    """Le SECOND predicat de `GetPossibleTargetsForOptions`, pose sur la paire (caster, tuile).

    `casterTiles` est le SINGLETON `{GetMainTile(unit)}` -- c'est ce que
    `BattleQuery$$IsTileInRangeOfAnyAbility` construit et transmet jusqu'ici, donc la surcharge
    LISTE de `MovementQuery$$GetTilesObscuringTerrain` court-circuite sur sa branche `Count == 1`
    et aucune intersection multi-pieds n'est exercee (cf. son mirror).

    `caster_team` / `team_by_pos` alimentent les DEUX gardes « ami » (#433-r4-r2-r1-r2-r2) --
    foyer unique `targeting_query.friend_gates_for_tile_target`, qui porte la lecture. Les deux
    absents, on retombe sur `(False, False)`, le statu quo d'avant la tranche."""
    t = (int(tile[0]), int(tile[1]))
    occupant = (team_by_pos or {}).get(t)
    is_friend, has_friendly = TQ.friend_gates_for_tile_target(caster_team, occupant)
    return TQ.target_is_obscured(board, [(int(unit_pos[0]), int(unit_pos[1]))], t, rules,
                                 caster_has_indirect_fire=_has_indirect_fire(visual_id),
                                 target_is_friend=is_friend,
                                 target_is_friend_or_has_friendly_unit=has_friendly)


def _unwalkable(rules, tile, walkable_by_pos, is_in_fog_by_pos) -> bool:
    """L'etage AMONT de `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` : la tuile est-elle
    RETIREE de la zone parce qu'elle n'est pas MARCHABLE (#433-r4-r2-r1-r2-r2-r1) ?

    Foyer UNIQUE : `targeting_query.tile_removed_by_walkability`, qui porte la lecture (le bit 43
    `AllowUnwalkableTargetTile`, la lambda `TargetingQuery.<>c$$<GetTilesInRange>b__36_0` et les
    DEUX volets de `TileExtensions$$IsWalkable`). Les deux cartes absentes -> aucun retrait, statu
    quo d'avant la tranche."""
    t = (int(tile[0]), int(tile[1]))
    return TQ.tile_removed_by_walkability(
        rules,
        None if walkable_by_pos is None else walkable_by_pos.get(t),
        None if is_in_fog_by_pos is None else is_in_fog_by_pos.get(t))


def _ability_covers_tile(ability_id, visual_id, unit_pos, tile, elev_by_pos, board=None,
                         caster_team=None, team_by_pos=None,
                         walkable_by_pos=None, is_in_fog_by_pos=None,
                         occupant_by_pos=None) -> bool:
    """UNE ability couvre-t-elle `tile` depuis `unit_pos` ? -- la composition des CINQ etages,
    evaluee sur la TUILE : le court-circuit `rules` de `GetPossibleTargetTiles`, puis
    `GetTilesInRange` (son RAYON, puis son retrait des NON MARCHABLES, #-r1-r2-r2-r1), puis le
    predicat de LIGNE DE VUE (`b__1`, #-r1-r2), puis le predicat
    `GetDynamicInvalidTargetReason` (`b__2`, #-r1-r1).

    L'ORDRE natif est `GetTilesInRange` (rayon PUIS walkability), les DEUX `AddRange(casterTiles)`,
    puis `b__0`, `b__1`, `b__2` : les trois derniers sont des `RemoveAll`, donc COMMUTATIFS -- leur
    ordre relatif n'est pas observable, seule leur conjonction l'est.

    ⚠ **LE RETRAIT DES NON MARCHABLES, LUI, N'EST PAS COMMUTATIF, ET LE PORT LE PLACAIT DU MAUVAIS
    COTE DE L'AJOUT AVAL** (#447-r1-r1-r1). Le `RemoveAll` de walkability est la DERNIERE
    instruction de `TargetingQuery$$GetTilesInRange` (relue a l'octet : `if ((options.Rules &
    AllowUnwalkableTargetTile) == 0) RemoveAll(zone, <>c.<GetTilesInRange>b__36_0)`), tandis que les
    deux `AddRange(casterTiles)` vivent chez l'APPELANT, `GetPossibleTargetsForOptions`, et
    s'executent APRES. Une tuile qui n'entre dans la zone QUE par l'ajout aval n'est donc JAMAIS
    filtree par la walkability cote natif -- alors que le port l'y soumettait, d'ou un ecart
    RESTRICTIF. `verse_par_ajout_aval` porte la condition, en partage avec
    `_zone_contains_distance` pour qu'il n'y ait qu'une seule ecriture du fait.

    GISEMENT, MESURE et vide -- mais mesure, pas suppose. La tuile en question est `casterTiles`,
    c'est-a-dire celle ou se tient le caster ; l'ecart exige donc qu'elle soit NON MARCHABLE ou EN
    BROUILLARD. Sur les deux boards sondes (`MC1_67` pvp : 63 tuiles, 0 en fog ; `C6_02` campagne :
    63 tuiles dont **32 en fog** et 22 non marchables), l'intersection « occupee ET (fog ou non
    marchable) » vaut **0**. Cause structurelle, LUE :
    `IdunBattle.Operations.AddUnitOperation$$AreTilesDisallowedAndLog` refuse toute tuile qui ne
    passe pas son gate `<IBattleQuery slot 0xa1>` ou dont le `TileContentComponent$$IsFilled` est
    vrai, `GetMovableTilesFor` ne rend pas de tuile en brouillard, et le brouillard RECULE (il se
    leve a l'exploration) au lieu d'avancer. Sur `C6_02` les 32 tuiles en fog sont les salles
    fermees, ou les unites ne sont pas ENCORE instanciees (`observeBattle.counts.units = 3` pour six
    unites demandees au build). Le mirror est donc pose ET exerce par un cran SYNTHETIQUE, pas
    confronte live : aucun montage n'amene un caster sur une telle tuile.

    L'attaque normale n'est pas concernee : aucun de ses 18 profils ne porte `CasterIsPossibleTarget`
    ni `TargetIsCasterOrEnemy`, donc `verse_par_ajout_aval` y est toujours faux (cf.
    `normal_attack_zone_contains`).

    ⚠ L'etage `GetTilesInRange` est teste par `tiles_in_range_zone_contains`, pas par une
    comparaison `d <= rayon` : un rayon ne sait pas dire si la tuile du CASTER en fait partie, et
    la reponse depend de la branche prise (#433-r4-r2-r1-r2-r2-r1-r1-r1).

    ⚠ ET LE RAYON NE COURT-CIRCUITE PLUS L'ENSEMBLE (#447-r1-r1). Cette fonction refusait des que
    `tiles_in_range_reach` rendait `None`. C'etait un fork : l'ajout aval de
    `GetPossibleTargetsForOptions` ne consulte pas la portee, donc une ability a `TargetingRange`
    non RE-lu et bit 15 arme verse quand meme la tuile du caster. C'est l'ENSEMBLE qui tranche
    desormais, et il rend `None` (donc refus) a toute autre distance -- le rayon ne sert plus qu'au
    gate `GATE_NOT_DERIVABLE`, qui a besoin de savoir si la borne est FINIE."""
    if target_tiles_zone_is_empty(ability_id):
        return False                               # zone VIDE avant meme `GetRange`
    base = tiles_in_range_reach(ability_id, visual_id)
    d = hexgeo.distance(tuple(unit_pos), tuple(tile))
    if not tiles_in_range_zone_contains(ability_id, visual_id, d):
        return False
    opts = _options_of(ability_id)
    if (not verse_par_ajout_aval(getattr(opts, "rules", None), d)
            and _unwalkable(getattr(opts, "rules", None), tile,
                            walkable_by_pos, is_in_fog_by_pos)):
        return False                               # `GetTilesInRange` -- NON MARCHABLE
    if _obscured(board, unit_pos, tile, getattr(opts, "rules", None), visual_id,
                 caster_team=caster_team, team_by_pos=team_by_pos):
        return False                               # b__1 -- LIGNE DE VUE
    gate = dynamic_target_gate_of(ability_id)
    if gate == GATE_FREE_ADJACENT_IN_CONFIG_RANGE:
        cfg = _config_range(ability_id)
        if cfg is None:
            return False
        if elev_by_pos:
            return _free_adjacent_gate_allows(unit_pos, tile, int(cfg), elev_by_pos,
                                              adjacent_neigh_by_pos(board))
        # DEGRADATION NOMMEE : sans canal d'elevation, on ne garde du gate que sa consequence de
        # DISTANCE (`config.range + 1`) -- borne SUPERIEURE exacte, mesuree a 2 faux positifs sur 40.
        return hexgeo.distance(tuple(unit_pos), tuple(tile)) <= int(cfg) + 1
    if gate == GATE_NOT_DERIVABLE:
        # cf. `ability_range_value` : la borne superieure n'est exploitable que si elle est bornee.
        # `base is None` (portee non RE-lue) n'atteint ce point que par l'ajout aval, dont l'apport
        # est le SINGLETON `casterTiles` -- donc borne, et `None != WHOLE_BOARD_REACH` le dit.
        return base != WHOLE_BOARD_REACH
    if gate == GATE_VALID_ON_EMPTY_TILE:
        # #433-r4-r2-r1-r1-a-r1 -- le gate NE MORD QUE sur une tuile OCCUPEE, et l'occupation EST
        # publiee : `tileMeta.tiles[].occupantId` (capteur #175-r), qui INVOQUE
        # `IdunBattle.Entities.UnitExtensions$$GetUnit(TileEntity, state)` -- LE natif que lit
        # `DeathOnTheWindAbility$$GetDynamicInvalidTargetReason`, et la meme entite que
        # `EntityExtensions$$IsUnit(entity)` teste chez `1168`/`1200`. La fiche du residu disait
        # « exige un capteur » : c'etait vrai a son ecriture, ce ne l'est plus.
        # TRI-ETAT : `None` = canal absent -> aucun retrait (statu quo PERMISSIF, comportement
        # d'avant). Une table FOURNIE mais vide est une mesure (« aucune tuile occupee »), et son
        # regime degenere est ecarte en amont par l'appelant, pas ici.
        if occupant_by_pos is not None and occupant_by_pos.get((tile[0], tile[1])) is not None:
            return False
        return True
    # GATE_NONE / GATE_NOT_READ : aucun retrait sur une tuile LIBRE.
    return True


def is_tile_in_range_of_any_ability(unit_pos, tile, visual_id, feet_count: int = 1,
                                    ability_ids=None, elev_by_pos=None,
                                    ability_state=None, normal_attack_id=None,
                                    is_wall_by_pos=None, caster_team=None,
                                    team_by_pos=None, walkable_by_pos=None,
                                    is_in_fog_by_pos=None, caster_pos=None,
                                    is_turn_of_unit=None, occupant_by_pos=None,
                                    has_moved=None) -> bool:
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
    qu'ELARGIR (mesure : 2 faux positifs sur 40 pour `bloodDante`, 0 avec le canal).

    `elev_by_pos` porte AUSSI le SECOND predicat (`b__1`, la LIGNE DE VUE, #-r1-r2) : c'est de lui
    que sort le `PositionBoard` sur lequel `MovementQuery$$GetTilesObscuringTerrain` trace ses deux
    lignes. `is_wall_by_pos` (`boardGraph.isWall` = `TileComponent+0x41`) en est le second volet ;
    ABSENT, le port ne voit AUCUN mur, ce qui ne peut qu'ELARGIR.

    `walkable_by_pos` / `is_in_fog_by_pos` -- l'etage AMONT `GetTilesInRange`
    (#433-r4-r2-r1-r2-r2-r1), `{(col,row): bool}` du `boardGraph` (`walkable` =
    `BattleQuery$$IsWalkableTile` ; `isInFog` = `TileComponent+0x40`). Sans eux, le port ATTRIBUE
    des tuiles que le natif RETIRE -- ecart PERMISSIF, le seul type qu'un entrainement puisse
    exploiter. Les DEUX sont necessaires : `IsWalkable(t, checkFog: true)` agrege les deux volets
    et `IsWalkableTile` n'en rend que le premier (mesure : 31 tuiles `walkable && isInFog` sur
    `C6_02`). Canal muet -> volet inerte, statu quo.

    `caster_team` / `team_by_pos` -- les DEUX gardes « ami » du meme predicat
    (#433-r4-r2-r1-r2-r2), `{(col,row): TeamId}` de l'OCCUPANT VIVANT de chaque tuile. Elles sont
    les seules de la cascade dont l'ecart soit RESTRICTIF : sans elles, le port RETIRE des tuiles
    que le natif GARDE (une tuile portant un allie du caster n'est JAMAIS obscurcie). Canal muet
    -> statu quo, et l'ecart subsiste. Le foyer de leur lecture est
    `targeting_query.friend_gates_for_tile_target` ; il n'est PAS symetrique (`IsFriend` ne
    resout pas l'occupant d'une tuile, `IsFriendOrHasFriendlyUnitOnIt` si).

    `ability_state` / `normal_attack_id` -- le canal d'ETAT par ability
    (`decisionView.units[].abilities[]`, `allAbilities: true`), consomme par TROIS des QUATRE gates
    CASTER que `GetAllTilesInAbilityRange` evalue AVANT les slots 9/10 (#433-r4-r2-r1-r1-c ; le
    4e, lui, se nourrit de `caster_pos` et des cartes de plateau). Une
    ability annulee ne verse RIEN, exactement comme l'ensemble vide du natif. Canal absent -> seul
    `IsDisabled` (derivable du kit) peut mordre, et le reste est le statu quo, borne SUPERIEURE.
    MESURE qui l'a impose (`darkaTerminator`, arme de MELEE + `PlasmaCannon` de zone 3, dont
    `initialCooldownTurns = 1` arme le gate au premier tour) : le natif rend « en portee »
    jusqu'a `d = 3` cooldown eteint, et `d <= 1` SEULEMENT tant qu'il brule -- meme unite, meme
    tuile, meme sweep.

    `caster_pos` -- la tuile COURANTE du caster (`GetMainTile(unit)`), quand elle DIFFERE de
    `unit_pos` (#433-r4-r2-r1-r2-r2-r1-r1-r1-r4). Les deux coincident dans le regime du foyer natif
    `BattleQuery$$IsTileInRangeOfAnyAbility`, qui construit `{GetMainTile(unit)}` -- d'ou le defaut.
    Elles se SEPARENT chez l'autre appelant natif, `AttackQuery$$GetAllTilesInAbilityRange(unit,
    possiblePositions, true)` (l'oracle `aiMovableTiles`), qui balaie des positions CANDIDATES :
    la regle-delegue CASTER de `1045 GetEmRuntz` y lit `GetMainTile(caster)` -- la COURANTE -- via
    `CasterSelector`, pas la position balayee. Confondre les deux ferait varier un verdict que le
    natif tient CONSTANT sur tout le balayage.

    `occupant_by_pos` -- `{(col,row): occupantId | None}`, l'OCCUPANT de chaque tuile
    (#433-r4-r2-r1-r1-a-r1). Substrat : `tileMeta.tiles[].occupantId`, qui INVOQUE
    `IdunBattle.Entities.UnitExtensions$$GetUnit(TileEntity, state)` -- pas une reconstitution.
    Consomme par le SEUL regime `GATE_VALID_ON_EMPTY_TILE` (sept abilities), dont le gate natif ne
    retire QUE sur une tuile portant une unite. `None` = **non mesure** -> aucun retrait, c.-a-d.
    le statu quo PERMISSIF d'avant.

    `is_turn_of_unit` -- `IdunBattle.Core.Services.BattleQuery$$IsTurnOfUnit(caster)`, le PREFIXE de
    la regle `CasterHasNotMoved` (#447-r1-r1). Il n'a d'effet QUE dans le regime BALAYE : la 2e
    clause de cette regle compare `casterTiles` (la position candidate, donc `unit_pos`) aux tuiles
    REELLES du caster, et le natif refuse des qu'elles different. `None` = **non mesure**, la
    clause ne refuse alors jamais -- c'est le statu quo, et c'est ce que rendent les appelants de
    production, qui ne publient pas ce fait. Derivable sans capteur neuf :
    `observeBattle.units[].playerId == observeBattle.currentPlayer` (cf. `CasterSubstrate`).

    `has_moved` -- `IdunBattle.Entities.UnitExtensions$$DidMove(caster)` =
    `UnitFlagsComponent.Has(UnitFlag.Moved)`, l'AUTRE terme de `CasterHasNotMoved` (#447-r1-r1-r3-r1).
    Il est en TRI-ETAT et il est GARDE PAR LE PREFIXE : la clause n'est evaluee que si
    `is_turn_of_unit` est vrai, ce que le natif exige aussi. `None` = **non mesure** -> la clause ne
    refuse jamais.
    ⚠ SON GISEMENT EST ETROIT, ET C'EST UNE MESURE, PAS UNE EXCUSE : chez l'unique appelant de
    production (`playbook/noncomparable/early_warning_override.py`) le << caster >> interroge est un
    ENNEMI du joueur courant, donc `is_turn_of_unit` y vaut `False` et ce terme est INERTE -- sauf
    sous CONTROLE MENTAL, ou une unite qui nous appartient (`playerId` = nous, donc prefixe VRAI)
    est jouee par l'adversaire et apparait cote ennemi. Le canal est neanmoins cable parce qu'il ne
    coute RIEN (`combatSnapshot.units[].unitFlags` est deja capte a chaque pas par
    `Scene.refresh_shields`) et parce qu'il ferme la chaine pour l'AUTRE consommateur natif,
    `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange(unit, possiblePositions, true)`,
    ou la 2e clause MORD."""
    if int(feet_count or 1) > 1:
        return True
    if unit_pos is None or tile is None:
        return False
    # Le substrat du 4e gate CASTER. `pos` est la tuile COURANTE (cf. `caster_pos`).
    # `has_moved` est desormais RELAYE par l'appelant (#447-r1-r1-r3-r1) : son point d'ancrage --
    # le `UnitFlagsComponent` (`UnitFlag.Moved`) sur la ligne d'unite -- etait deja publie par
    # `combatSnapshot.units[].unitFlags` et consolide dans `Scene.moved_by_id`. Restent `None` :
    # `feet_count` et `is_machine`, qu'AUCUN canal cote DECISION ne publie -- les poser au juge
    # inventerait une mesure.
    # `neigh_by_pos = None` : cette fonction ne recoit PAS la liste d'adjacence STOCKEE, et
    # `adjacent_neigh_by_pos(MQ.PositionBoard(...))` rend `None` (mesure) -- le gate CIBLE
    # `GATE_FREE_ADJACENT_IN_CONFIG_RANGE` est deja dans ce meme regime. `battle_query.is_adjacent`
    # retombe donc sur la couronne hex PLUS la porte d'elevation : degradation PERMISSIVE connue
    # (4 aretes sur `C1_74`, 38 sur `C3_14`), jamais un voisinage vide.
    cpos = tuple(caster_pos) if caster_pos is not None else tuple(unit_pos)
    caster = acg.CasterSubstrate(
        pos=(int(cpos[0]), int(cpos[1])), has_tile=True, team=caster_team,
        is_turn_of_unit=is_turn_of_unit, has_moved=has_moved,
        # `casterTiles` INTERROGE = la position balayee. Dans le regime du foyer natif elle EGALE
        # `pos`, donc la 2e clause de `CasterHasNotMoved` reste inerte -- comme chez le natif.
        interrogated_pos=(int(unit_pos[0]), int(unit_pos[1])),
        team_by_pos=team_by_pos, walkable_by_pos=walkable_by_pos, elev_by_pos=elev_by_pos,
        neigh_by_pos=None)
    d = hexgeo.distance(tuple(unit_pos), tuple(tile))
    if d > unit_threat_reach(visual_id, ability_ids, ability_state, normal_attack_id, caster):
        return False                          # hors de la borne SUPERIEURE : aucune ability ne porte
    board = (MQ.PositionBoard(elev_by_pos, is_wall_by_pos)
             if elev_by_pos else None)        # canal absent -> aucun retrait (degradation NOMMEE)
    # `includeNormalAttack: true` -- l'attaque normale, dont le `TargetingRange` se reduit a
    # `unit_weapon_range` et qui n'a PAS de gate dynamique porte. Elle passe en revanche par les
    # MEMES quatre gates CASTER (son entree est dans l'`ActiveAbilityComponent`, #-r1-r1-c) ET par
    # le MEME `GetPossibleTargetsForOptions` : le predicat de LIGNE DE VUE s'y applique, avec le
    # masque `NORMAL_ATTACK_TARGETING_OPTIONS` (0x4002), qui ne porte AUCUN `AllowObscuredTarget*`.
    if normal_attack_id is None or not _gated_out(normal_attack_id, ability_state, caster):
        # La zone de l'attaque normale, branche par branche (#433-r4-r2-r1-r2-r2-r1-r1-r1) : son
        # masque ne porte NI `CasterIsPossibleTarget` NI `TargetIsCasterOrEnemy`, donc `d = 0` en
        # est EXCLU -- ce que `d <= portee d'arme` attribuait a tort.
        if normal_attack_zone_contains(normal_attack_id, visual_id, d):
            # `NORMAL_ATTACK_TARGETING_OPTIONS.rules` (0x4002) ne porte PAS `AllowUnwalkableTargetTile` :
            # le terme de l'attaque normale est donc TOUJOURS gate par la walkability, quel que soit
            # le kit -- contrairement aux abilities dont le masque n'est pas RE-lu.
            if (not _unwalkable(NORMAL_ATTACK_TARGETING_OPTIONS.rules, tile,
                                walkable_by_pos, is_in_fog_by_pos)
                    and not _obscured(board, unit_pos, tile,
                                      NORMAL_ATTACK_TARGETING_OPTIONS.rules, visual_id,
                                      caster_team=caster_team, team_by_pos=team_by_pos)):
                return True
    aids = _active_ability_ids(visual_id) if ability_ids is None else ability_ids
    return any(_ability_covers_tile(aid, visual_id, unit_pos, tile, elev_by_pos, board,
                                    caster_team=caster_team, team_by_pos=team_by_pos,
                                    walkable_by_pos=walkable_by_pos,
                                    is_in_fog_by_pos=is_in_fog_by_pos,
                                    occupant_by_pos=occupant_by_pos)
               for aid in aids if not _gated_out(aid, ability_state, caster))
