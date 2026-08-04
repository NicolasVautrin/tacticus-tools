"""GARDES #433-r4-r2-r1-r1 -- l'etage `GetDynamicInvalidTargetReason`.

CE QUE CE FICHIER VERROUILLE. `LightOfSanguinius` (1177) et `LeadingTheCharge` (1204) partagent le
MEME preset de ciblage (`IdunBattle.Core.Services.TargetingOptions$$.cctor`, statique `+0x240`) --
donc le meme `TargetingRange` (`UseWholeBoard`) ET le meme masque `Rules = 0x102004032` -- et
rendent pourtant des zones DIFFERENTES. Le discriminant est le slot de vtable `klass+0x478` :

    AActiveAbility$$.ctor :
        this.<TargetingOptions @+0x70>.<+0x30> = new TargetingOptions.DynamicTargetingRule(
                                                       this, <klass+0x470>)
        this.<TargetingOptions @+0x70>.<+0x38> = new TargetingOptions.DynamicTargetingTargetRule(
                                                       this, <klass+0x480>)

`klass+0x470` / `klass+0x480` sont les champs `MethodInfo*` (a `+8` du debut de slot) des slots
commencant a `klass+0x468` / `klass+0x478` -- la vtable IL2CPP demarrant a `klass+0x138`, pas 0x10,
ce sont les index 51 et 52. Resolus AU RUNTIME (`resolveVtableSlot`), ce sont
`GetDynamicInvalidCasterReason` et `GetDynamicInvalidTargetReason`.

Le champ `+0x38` est celui qu'invoque le TROISIEME predicat de
`IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` -- la lambda
`TargetingQuery.u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__2`,
appliquee en `RemoveAll` quand `Rules & 2` : la tuile est RETIREE quand le delegue rend une raison
non nulle. Le gate ne peut donc que RETRECIR la zone.

⚠ CE QUI NE PROUVE RIEN, ET POURQUOI CES GARDES SONT OFFLINE MAIS PAS AUTOSUFFISANTES. Le corps de
base (`AActiveAbility$$GetDynamicInvalidTargetReason`, retour 0) est TRIVIAL, donc DEDUPLIQUE par
IL2CPP : l'absence d'un `<X>$$GetDynamicInvalidTargetReason` dans les tables ne dit RIEN de la
classe X. Ce qui etablit le defaut `GATE_NONE`, c'est l'EGALITE DES POINTEURS DE SLOT lue sur la
vtable au runtime -- `probe_433_r4_r2_r1_r1_dynamic_target_gate.py --step gate`. Les gardes ci-dessous
verrouillent la CONSEQUENCE portee, pas la lecture.

Les valeurs citees sont MESUREES (sweep de 40 positions, `d = 2..10`, un seul ennemi vivant) --
cf. `docs/rl/case-433-r4-r2-r1-r2-portees.md`. ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.services import ability_range as ar

DANTE = "bloodDante"            # melee + LightOfSanguinius (whole board + gate de DISTANCE, range 5)
INTERCESSOR = "bloodIntercessor"  # melee + HammerOfWrath   (meme gate, meme range) -- 2e kit
ASMODAI = "darkaAsmodai"        # melee + ExemplarOfHate    (whole board SANS gate)
DREIR = "astraDreir"            # melee + LeadingTheCharge  (whole board + gate de MOUVEMENT)
MARKSMAN = "tauMarksman"        # SeekerMissileFrequencyLock (RANGE_FROM_CONFIG, PAS whole board)


# ------------------------------------------------------- 1. les trois regimes, et leur separation

def test_the_same_preset_yields_three_different_regimes():
    """LA garde de ce cas. Les trois abilities portent le MEME `TargetingRange` (`UseWholeBoard`),
    donc la MEME borne superieure -- et le port doit malgre tout les separer."""
    for aid in (1177, 1204, 1140):
        assert ar.targeting_range_of(aid).use_whole_board is True
        assert ar.tiles_in_range_reach(aid, DANTE) == ar.WHOLE_BOARD_REACH
    assert ar.ability_range_value(1177, DANTE) == 6                      # gate de DISTANCE
    assert ar.ability_range_value(1204, DREIR) is None                   # gate de MOUVEMENT
    assert ar.ability_range_value(1140, ASMODAI) == ar.WHOLE_BOARD_REACH  # AUCUN gate


def test_gate_regimes_are_the_ones_read_in_the_decompiled_bodies():
    assert ar.dynamic_target_gate_of(1177) == ar.GATE_FREE_ADJACENT_IN_CONFIG_RANGE
    assert ar.dynamic_target_gate_of(1153) == ar.GATE_FREE_ADJACENT_IN_CONFIG_RANGE
    assert ar.dynamic_target_gate_of(1204) == ar.GATE_NOT_DERIVABLE
    assert ar.dynamic_target_gate_of(1140) == ar.GATE_NONE, "ExemplarOfHate ne surcharge PAS"
    assert ar.dynamic_target_gate_of(1069) == ar.GATE_NONE, "Seeker ne surcharge PAS"


def test_absent_from_the_table_means_no_gate_and_never_shrinks():
    """Le DEFAUT est `GATE_NONE`, et il ne retire rien : une ability hors table garde exactement le
    rayon de `GetTilesInRange`. C'est ce qui laisse les kits deja EXACTS inchanges."""
    assert ar.dynamic_target_gate_of(999999) == ar.GATE_NONE
    assert ar.dynamic_target_gate_reach(999999) == ar.WHOLE_BOARD_REACH
    assert ar.ability_range_value(1069, MARKSMAN) == 5          # inchange par la tranche
    assert ar.ability_range_value(1191, "custoBladeChampion") == 1


# ------------------------------------------------------- 2. le `+1` de `GetFreeAdjacentTiles`

@pytest.mark.parametrize("aid,visual", [(1177, DANTE), (1153, INTERCESSOR)])
def test_the_distance_gate_is_config_range_plus_one(aid, visual):
    """`GetFreeAdjacentTiles(targetTiles).Any(t => GetDistance(t, casterTiles) <= config.range)` :
    le test porte sur les VOISINES de la cible, donc une cible a `config.range + 1` reste atteignable
    par une voisine a `config.range`.

    MESURE : natif « en portee » a 100 % pour `d <= 5` et encore **4/6 a d = 6**, puis 0 des `d >= 7`.
    Un modele en `config.range` aurait predit zero a `d = 6` -- seule la ventilation PAR DISTANCE
    separe les deux, une comparaison globale ne l'aurait pas vue. Deux kits, deux abilities."""
    assert ar._config_range(aid) == 5
    assert ar.dynamic_target_gate_reach(aid) == 6
    assert ar.ability_range_value(aid, visual) == 6
    assert ar.unit_threat_reach(visual) == 6, "l'arme de melee ne doit pas ecraser la zone d'ability"


def test_the_plus_one_follows_the_config_and_is_not_a_fitted_constant():
    """Le `+1` est STRUCTUREL (le voisinage), pas un ajustement : il suit `constants.range`. On le
    prouve sur une config synthetique -- aucune ability du lot ne porte une autre valeur."""
    saved = ar._config_range
    try:
        ar._config_range = lambda aid: 2 if int(aid) == 1177 else saved(aid)
        ar._REACH_CACHE.clear()
        assert ar.dynamic_target_gate_reach(1177) == 3
        assert ar.ability_range_value(1177, DANTE) == 3
    finally:
        ar._config_range = saved
        ar._REACH_CACHE.clear()


# ------------------------------------------------------- 2bis. la PORTE D'ELEVATION du gate

def _elev_isolating(tile, plateau=1, wall=4):
    """Une carte d'elevation ou `tile` est SEULE a son niveau : toutes ses voisines -- enumerees par
    `hexgeo.neighbors`, jamais a la main : la parite offset rend le voisinage NON symetrique en
    ecriture naive -- sont a un ecart >= 2, donc AUCUNE ne passe la porte d'`IterateAdjacentTiles`."""
    elev = {tuple(tile): plateau}
    for n in hexgeo.neighbors(tile[0], tile[1]):
        elev[tuple(n)] = wall
    return elev


def test_the_gate_is_evaluated_per_tile_when_the_elevation_channel_is_there():
    """`GetFreeAdjacentTiles` passe par `IterateAdjacentTiles`, dont
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` applique une
    PORTE D'ELEVATION `|srcElev - tile.Elevation| < 2`. Avec le canal, le port evalue le gate SUR LA
    TUILE au lieu de le rabattre sur son rayon.

    C'est la MESURE qui a designe cette porte, et le decompile qui l'a tranchee : a `d = 6` le natif
    accepte 4 tuiles sur 6 ; les DEUX refusees sont a elevation 2 et n'ont, a `d <= 5`, que des
    voisines a elevation 4."""
    T, caster = (5, 5), (5, 8)
    flat = {(c, r): 1 for c in range(0, 12) for r in range(0, 12)}
    assert ar._free_adjacent_gate_allows(caster, T, 2, flat) is True
    assert ar._free_adjacent_gate_allows(caster, T, 2, _elev_isolating(T)) is False


def test_without_the_channel_the_gate_degrades_to_its_radius_and_only_widens():
    """DEGRADATION NOMMEE : sans elevation le port garde `config.range + 1`, ce qui ne peut
    qu'ELARGIR -- MESURE : 2 faux positifs sur 40 pour `bloodDante` sans le canal, 0 avec."""
    T, caster = (5, 5), (5, 8)
    blocked = _elev_isolating(T)
    assert ar._ability_covers_tile(1177, DANTE, caster, T, None) is True
    assert ar._ability_covers_tile(1177, DANTE, caster, T, blocked) is False
    assert ar.is_tile_in_range_of_any_ability(caster, T, DANTE) is True
    assert ar.is_tile_in_range_of_any_ability(caster, T, DANTE, elev_by_pos=blocked) is False


def test_the_normal_attack_has_no_dynamic_gate():
    """`includeNormalAttack: true` ajoute l'attaque normale a l'union, et elle n'a PAS de gate :
    une tuile a portee d'ARME reste en zone meme si le gate de l'ability la refuse.

    `tauMarksman` porte une arme de portee 3 ; la tuile est a 2, donc l'attaque normale suffit."""
    T, caster = (5, 5), (5, 7)
    assert ar.is_tile_in_range_of_any_ability(caster, T, MARKSMAN,
                                              elev_by_pos=_elev_isolating(T)) is True


# ------------------------------------------------------- 3. whole board SANS gate = tout le plateau

def test_no_gate_whole_board_covers_every_tile():
    """`TargetingQuery$$GetTilesInRange` branche sur `UseWholeBoard` AVANT tout le reste et rend
    `<IBattleQuery slot 0x69>()` = `GetAllTiles()`. Sans gate pour en retirer, la zone est le
    plateau ENTIER -- MESURE sur `darkaAsmodai` : 40/40, a TOUTE distance de 2 a 10."""
    assert ar.unit_threat_reach(ASMODAI) == ar.WHOLE_BOARD_REACH
    for d in (1, 6, 10, 25):
        assert ar.is_tile_in_range_of_any_ability((0, 0), (d, 0), ASMODAI) is True


def test_undeciderable_gate_on_whole_board_still_yields_none():
    """Le SEUL regime ou la borne superieure est inutilisable : la verser declarerait tout le
    plateau menace. MESURE sur `astraDreir` : le natif rend « hors portee » des `d >= 2`, donc
    verser le plateau ferait 40 faux POSITIFS la ou `None` en fait 0."""
    assert ar.dynamic_target_gate_reach(1204) is None
    assert ar.ability_range_value(1204, DREIR) is None
    assert ar.unit_threat_reach(DREIR) == 1, "seule l'arme de melee subsiste"
    assert ar.is_tile_in_range_of_any_ability((0, 0), (2, 0), DREIR) is False


def test_a_bounded_base_survives_an_underivable_gate():
    """Un gate non derivable ne fait PAS retomber a `None` une ability dont la zone de base est
    bornee : le rayon reste une borne SUPERIEURE exacte (le gate ne peut que retirer). Sans cette
    regle, les 15 abilities non-whole-board qui surchargent disparaitraient d'un coup de la zone."""
    saved = dict(ar.DYNAMIC_TARGET_GATE_BY_ABILITY)
    try:
        ar.DYNAMIC_TARGET_GATE_BY_ABILITY[1069] = ar.GATE_NOT_DERIVABLE
        ar._REACH_CACHE.clear()
        assert ar.tiles_in_range_reach(1069, MARKSMAN) == 5
        assert ar.ability_range_value(1069, MARKSMAN) == 5
    finally:
        ar.DYNAMIC_TARGET_GATE_BY_ABILITY.clear()
        ar.DYNAMIC_TARGET_GATE_BY_ABILITY.update(saved)
        ar._REACH_CACHE.clear()


# ------------------------------------------------------- 4. hygiene de la table

def test_every_gate_regime_in_the_table_is_a_known_constant():
    known = {ar.GATE_NONE, ar.GATE_FREE_ADJACENT_IN_CONFIG_RANGE,
             ar.GATE_NOT_DERIVABLE, ar.GATE_VALID_ON_EMPTY_TILE, ar.GATE_NOT_READ}
    bad = {aid: g for aid, g in ar.DYNAMIC_TARGET_GATE_BY_ABILITY.items() if g not in known}
    assert bad == {}, "regimes inconnus : %r" % (bad,)
    assert ar.GATE_NONE not in ar.DYNAMIC_TARGET_GATE_BY_ABILITY.values(), \
        "GATE_NONE est le DEFAUT : l'inscrire explicitement brouillerait la lecture de la table"


def test_a_derivable_gate_must_have_a_config_range():
    """`GATE_FREE_ADJACENT_IN_CONFIG_RANGE` LIT `config.GetNumberConstant(0x16)`. Une ability
    classee ainsi sans `constants.range` retomberait silencieusement sur `None`."""
    for aid, gate in ar.DYNAMIC_TARGET_GATE_BY_ABILITY.items():
        if gate == ar.GATE_FREE_ADJACENT_IN_CONFIG_RANGE:
            assert ar._config_range(aid) is not None, "ability %d sans constants.range" % aid
