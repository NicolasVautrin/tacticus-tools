"""GARDES #433-r4-r2-r1-r1-a -- les gates `UseWholeBoard` que la tranche precedente n'avait PAS lus.

CE QUE CE FICHIER VERROUILLE, et pourquoi ce n'est pas une redite de
`test_433_r4_r2_r1_r1_dynamic_target_gate_offline.py` : celui-la garde les gates DERIVABLES EN
RAYON (`config.range + 1`) et le regime indecidable. Celui-ci garde le fait que **aucun** des neuf
gates restants n'est un rayon, et les DEUX etages que leur lecture a fait apparaitre :

  1. `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetTiles` court-circuite AVANT
     `GetRange` -- `if ((rules >> 0xa & 1) && !(rules >> 0xe & 1)) return new OrderedSet<Tile>()`,
     soit `TargetIsFriendly` sans `TargetIsEnemy`. La zone est VIDE, ce qui est EXACT et non une
     borne. `1100 SorcerousFacade` et `1143 ForwardSpotter` y tombent : elles surchargent bien le
     slot `klass+0x478`, mais leur gate n'est JAMAIS atteint.

  2. les sept autres rendent `0` sur une tuile SANS unite -- `GATE_VALID_ON_EMPTY_TILE`. Le
     discriminant est la lambda
     `TargetingQuery.u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__2`,
     qui passe au delegue non pas l'element mais
     `entity = (rules & TargetIsTile) ? EntityExtensions.GetMainTile(elem)
                                      : UnitExtensions.GetUnit(elem)`.

MESURES (sweep de 40 positions `d = 2..10`, un seul ennemi vivant, `probe_433_r4_r2_r1_r1_a_whole_board_gates.py`) :

    1100 SorcerousFacade   porteur NATIF `thousTzaangor`   natif  2/40 (= sa seule arme, portee 2)
    1143 ForwardSpotter    greffe                          natif  0/40
    1145, 1201, 1025       greffe                          natif 40/40   -- port EXACT
    1011                   greffe (+1060 monte par le natif) natif 35/40 -- 5 FP d'obscurcissement
    1168, 1200, 1213       greffe                          natif 34/40   -- 5 + la tuile OCCUPEE

Les deux etages de l'ECART sont ATTRIBUES, pas supposes : le temoin `1161 TwinSmartMissileSystem`
n'a AUCUN gate (bit 1 absent, le troisieme predicat n'est meme pas applique) et subit les MEMES
5 refus ; le temoin `1147 HadesAutocannons` n'a pas de gate non plus mais porte les bits
`AllowObscuredTargetByElevation|Walls` et rend 40/40. ASCII only.
"""
from __future__ import annotations

import pytest

from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.services import ability_range as ar

#: Le lot : les `UseWholeBoard` classees `GATE_NOT_READ` avant cette tranche.
LOT = [1011, 1025, 1100, 1143, 1145, 1168, 1200, 1201, 1213]

#: Les deux qui tombent sur le court-circuit AMONT.
FRIENDLY_ONLY = [1100, 1143]

GRAFT_HOST = "custoBladeChampion"     # arme de MELEE seule -- le vehicule des mesures
TZAANGOR = "thousTzaangor"            # porteur NATIF de 1100, seule active de son kit, arme 2

_OBSCURED_BY_ELEVATION = 0x2000000
_OBSCURED_BY_WALLS = 0x4000000


def _rules(aid):
    cls = ABILITY_CLASSES.get(int(aid))
    opts = getattr(cls, "TARGETING_OPTIONS", None) if cls is not None else None
    return getattr(opts, "rules", None) if opts is not None else None


# ------------------------------------------------- 1. le lot est CLOS et plus aucun n'est NON LU

def test_no_whole_board_gate_is_left_unread():
    """LA garde du cas. Une ability `UseWholeBoard` qui surcharge le slot et reste `GATE_NOT_READ`
    est une borne SUPERIEURE non chiffree -- exactement ce que cette tranche ferme."""
    whole = {int(a) for a, c in ABILITY_CLASSES.items()
             if getattr(getattr(c, "TARGETING_OPTIONS", None), "range", None) is not None
             and getattr(getattr(c, "TARGETING_OPTIONS", None).range, "use_whole_board", False)}
    # 2e source du volet PORTEE depuis `#433-r4-r2-r1-r2-r2-r1-r1` (`TARGETING_RANGE_BY_ABILITY`
    # SUPPRIMEE : elle forkait le masque de sa propre portee).
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    whole |= {int(a) for a, o in TARGETING_OPTIONS_UNPORTED.items()
              if getattr(o.range, "use_whole_board", False)}
    unread = sorted(a for a in whole if ar.dynamic_target_gate_of(a) == ar.GATE_NOT_READ)
    assert unread == [], "gates whole-board encore NON LUS : %r" % (unread,)


def test_the_remaining_unread_gates_are_all_bounded():
    """`GATE_NOT_READ` subsiste, et c'est voulu -- mais seulement la ou la borne superieure est
    BORNEE. Ne pas retrecir y coute au plus le disque de la portee, jamais le plateau entier."""
    for aid, gate in ar.DYNAMIC_TARGET_GATE_BY_ABILITY.items():
        if gate != ar.GATE_NOT_READ:
            continue
        rng = ar.targeting_range_of(aid)
        assert rng is not None and not rng.use_whole_board, \
            "ability %d : GATE_NOT_READ sur une zone WHOLE BOARD" % aid


def test_none_of_the_nine_is_a_radius():
    """Le critere binaire du cas, en negatif : AUCUN des neuf n'est reductible a une distance.
    Les deux seuls regimes de rayon (`GATE_FREE_ADJACENT_IN_CONFIG_RANGE`) restent les deux de la
    tranche precedente."""
    for aid in LOT:
        assert ar.dynamic_target_gate_of(aid) != ar.GATE_FREE_ADJACENT_IN_CONFIG_RANGE
    radius = sorted(a for a, g in ar.DYNAMIC_TARGET_GATE_BY_ABILITY.items()
                    if g == ar.GATE_FREE_ADJACENT_IN_CONFIG_RANGE)
    assert radius == [1153, 1177]


# ------------------------------------------------- 2. l'etage AMONT : la zone VIDE

@pytest.mark.parametrize("aid", FRIENDLY_ONLY)
def test_friendly_only_abilities_contribute_no_tile(aid):
    """`TargetIsFriendly` sans `TargetIsEnemy` -> `GetPossibleTargetTiles` rend un ensemble VIDE.

    MESURE : sur son porteur NATIF `thousTzaangor` (dont c'est la SEULE active), `1100` laisse le
    natif « en portee » a `d = 2` seulement -- soit exactement la portee de son arme. Le port
    d'avant cette tranche rendait le plateau entier, soit 38 faux positifs sur 40."""
    assert ar.target_tiles_zone_is_empty(aid) is True
    assert ar.targeting_range_of(aid).use_whole_board is True, "la zone de BASE est le plateau"
    assert ar.ability_range_value(aid, GRAFT_HOST) is None, "elle ne doit poser AUCUN terme"
    assert ar._ability_covers_tile(aid, GRAFT_HOST, (0, 0), (7, 7), None) is False


def test_the_short_circuit_reads_both_bits_and_not_one():
    """Le court-circuit teste DEUX bits : `TargetIsEnemy` DESARME `TargetIsFriendly`. Une ability
    qui cible les deux camps (`1153 HammerOfWrath`, `rules & 0x4400`) garde donc sa zone."""
    assert ar.target_tiles_zone_is_empty(1153) is False
    assert _rules(1153) & (1 << 0xA) == 0, "HammerOfWrath n'est pas friendly, la garde reste utile"
    assert ar.target_tiles_zone_is_empty(1002) is True, "CombatRestoratives : friendly SEUL"
    assert ar.targeting_range_of(1002).use_whole_board is False, \
        "l'etage AMONT ne depend PAS de UseWholeBoard -- il precede GetRange"


def test_an_unread_mask_never_shrinks():
    """Sans masque lu, le port ne retire rien : l'ecart ne peut qu'ELARGIR -- meme arbitrage que
    `GATE_NOT_READ`.

    ⚠ Le TEMOIN a change DEUX fois, et la seconde dit pourquoi il en fallait un meilleur :
    `1177 LightOfSanguinius` a ete lu par `#433-r4-r2-r1-r2-r2-r1-r1`, puis `1053 DevoutPush` par
    `#433-r4-r2-r1-r2-r2-r1-r1-r1`. Un temoin « pas ENCORE lu » se perime a chaque tranche de
    portage -- c'est le seul gisement que notre propre cadence alimente.

    Le temoin est maintenant `1091 SlashingDive`, dont la non-lecture est STRUCTURELLE et non
    circonstancielle : aucune classe `SlashingDiveAbility` n'existe dans les tables (seuls son
    Playbook et ses Visuals portent ce nom), donc il n'y a aucun ctor a lire -- trancher exigerait
    le slot de vtable de l'INSTANCE, au runtime (residu `#433-r4-r2-r1-r2-r2-r1-r1-r1-r2`, garde
    par `test_433_r4_r2_r1_r2_r2_r1_r1_r1_source_tile_zone_offline.py`)."""
    from engine.runner.abilities.targeting import targeting_options_for
    assert targeting_options_for(1091) is None, "temoin PERIME : le masque de 1091 a ete lu"
    assert ar.target_tiles_zone_is_empty(1091) is False
    assert targeting_options_for(1177) is not None, "1177 doit desormais porter son masque"
    assert ar.target_tiles_zone_is_empty(1177) is False       # LU, et il porte `TargetIsEnemy`
    assert ar.target_tiles_zone_is_empty(999999) is False
    assert ar.target_tiles_zone_is_empty(None) is False


# ------------------------------------------------- 3. le regime `GATE_VALID_ON_EMPTY_TILE`

@pytest.mark.parametrize("aid", [1011, 1025, 1145, 1168, 1200, 1201, 1213])
def test_valid_on_empty_tile_keeps_the_whole_board(aid):
    """Le gate a ete LU et il rend `0` sur une tuile sans unite : il ne retire donc rien du plateau.

    MESURE : 40/40 pour `1145`, `1201`, `1025` -- accord EXACT dans les deux sens. Pour `1011`,
    `1168`, `1200`, `1213` l'ecart residuel est ATTRIBUE ailleurs (cf. la classe de tests
    suivante), jamais au gate."""
    assert ar.dynamic_target_gate_of(aid) == ar.GATE_VALID_ON_EMPTY_TILE
    assert ar.dynamic_target_gate_reach(aid) == ar.WHOLE_BOARD_REACH
    assert ar.ability_range_value(aid, GRAFT_HOST) == ar.WHOLE_BOARD_REACH
    for d in (1, 6, 10, 25):
        assert ar._ability_covers_tile(aid, GRAFT_HOST, (0, 0), (d, 0), None) is True


def test_valid_on_empty_tile_is_not_the_same_claim_as_no_gate():
    """`GATE_NONE` = « la classe ne surcharge pas » (egalite de pointeurs de slot, fait runtime).
    `GATE_VALID_ON_EMPTY_TILE` = « elle surcharge, et le corps LU rend 0 sur une tuile libre ».
    Les deux donnent la meme zone ICI et divergeraient sur une tuile OCCUPEE -- les confondre
    perdrait le seul endroit ou la mesure les separe."""
    assert ar.GATE_VALID_ON_EMPTY_TILE != ar.GATE_NONE
    assert ar.dynamic_target_gate_of(1140) == ar.GATE_NONE       # ExemplarOfHate ne surcharge pas
    assert ar.dynamic_target_gate_of(1145) == ar.GATE_VALID_ON_EMPTY_TILE


# ------------------------------------------------- 4. l'ECART residuel, et son ATTRIBUTION

@pytest.mark.parametrize("aid,expected", [
    (1011, False), (1168, False), (1200, False), (1213, False),   # subissent l'obscurcissement
    (1025, True), (1145, True), (1201, True),                     # en sont dispensees
    (1147, True), (1161, False),                                  # les deux TEMOINS, sans gate
])
def test_the_residual_gap_is_predicted_by_the_obscuring_bits(aid, expected):
    """CE QUI ATTRIBUE L'ECART. Les positions que le port garde a tort ne viennent PAS du gate :
    le temoin `1161 TwinSmartMissileSystem` n'a AUCUN gate (`rules & 2 == 0`, le troisieme predicat
    n'est meme pas construit) et subit les MEMES 5 refus que `1011`/`1168`/`1200`/`1213` ; le
    temoin `1147 HadesAutocannons`, sans gate lui aussi mais porteur des deux bits, rend 40/40.

    Le discriminant est donc le masque -- `AllowObscuredTargetByElevation` (0x2000000) et
    `AllowObscuredTargetByWalls` (0x4000000) -- et l'etage responsable est le DEUXIEME predicat de
    `GetPossibleTargetsForOptions`, soit le residu `#433-r4-r2-r1-r2`, hors de cette tranche."""
    r = _rules(aid)
    assert r is not None
    exempt = bool(r & _OBSCURED_BY_ELEVATION) and bool(r & _OBSCURED_BY_WALLS)
    assert exempt is expected


def test_the_witness_without_any_gate_proves_the_gap_is_not_the_gate():
    """`1161` n'a PAS le bit `TargetMatchesDynamicRule` : `GetPossibleTargetsForOptions` ne pose le
    troisieme predicat que `if ((rules & 2) != 0)`. Un ecart qu'elle reproduit ne peut donc pas
    etre impute au gate. C'est ce qui rend la mesure ATTRIBUABLE au lieu d'etre une coincidence."""
    assert _rules(1161) & 0x2 == 0, "le temoin doit etre SANS gate"
    assert ar.dynamic_target_gate_of(1161) == ar.GATE_NONE
    assert _rules(1147) & 0x2 == 0
    assert ar.dynamic_target_gate_of(1147) == ar.GATE_NONE


def test_the_occupied_tile_gap_is_named_and_bounded():
    """L'ecart PROPRE au regime : sur une tuile OCCUPEE, trois des sept gates retirent la tuile
    (`1168` et `1200` par `EntityExtensions$$IsUnit(entity)`, `1213` par
    `UnitExtensions$$GetUnit(tile)`), et le port ne le modelise pas -- l'occupation n'est publiee
    par aucun canal ici (meme trou que `#433-r4-r2-r1-r1-b`).

    MESURE : sur le sweep, la SEULE tuile occupee est celle du caster, et c'est EXACTEMENT la
    position supplementaire que ces trois refusent face au temoin `1161`. Donc 1 tuile sur 40,
    toujours la meme -- l'ecart est chiffre, pas suppose."""
    for aid in (1168, 1200, 1213):
        assert ar.dynamic_target_gate_of(aid) == ar.GATE_VALID_ON_EMPTY_TILE
        assert ar._ability_covers_tile(aid, GRAFT_HOST, (0, 0), (3, 3), None) is True
