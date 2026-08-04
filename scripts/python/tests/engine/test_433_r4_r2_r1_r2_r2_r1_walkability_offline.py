"""OFFLINE #433-r4-r2-r1-r2-r2-r1 -- l'etage AMONT qui retire les tuiles NON MARCHABLES.

Ce que ces tests gardent, et qu'aucun test live ne garde : la FORME du mirror (quel bit, quels
volets, quel tri-etat) et son CABLAGE (que les deux cartes traversent bien
`is_tile_in_range_of_any_ability` jusqu'au foyer, pour l'attaque NORMALE comme pour chaque ability).
Le live, lui, garde le VERDICT.

Le natif, verbatim (`IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange`) :

    if ((options.Rules & AllowUnwalkableTargetTile) == 0)          # bit 43
        RemoveAll(zone, TargetingQuery.<>c.<GetTilesInRange>b__36_0);

    b__36_0(t) = !IdunBattle.Entities.TileExtensions$$IsWalkable(t, checkFog: true)
"""
from __future__ import annotations

import probe_433_r4_r2_r1_r2_r2_r1_walkability as W
from engine.services import ability_range as AR
from engine.services import targeting_query as TQ
from engine.runner.abilities.targeting import NORMAL_ATTACK_TARGETING_OPTIONS, targeting_options_for
from engine.runner.abilities.targeting_rule import TargetingRule as TR

#: `custoBladeChampion` porte une arme de MELEE (portee 1) : `is_tile_in_range_of_any_ability`
#: couvre donc ses voisines par le seul terme de l'attaque NORMALE, quel que soit son kit.
MELEE = "custoBladeChampion"


def _covers(tile, **kw):
    """`IsTileInRangeOfAnyAbility` depuis (0,0), kit VIDE : seul le terme attaque NORMALE joue."""
    return AR.is_tile_in_range_of_any_ability((0, 0), tile, MELEE, ability_ids=[], **kw)


# ------------------------------------------------------------------------------------------------
# 1. LE FOYER -- la lecture, confrontee a elle-meme
# ------------------------------------------------------------------------------------------------

def test_the_read_step_of_the_probe_is_self_consistent():
    """`--step read` : la table de verite complete du foyer, chaque ligne annotee de SON motif au
    decompile. Elle vit dans le probe (une seule ecriture), le test l'exerce."""
    assert W.step_read() == 0


def test_the_gating_bit_is_allow_unwalkable_target_tile():
    """Le bit 43 du masque, et pas un autre. Le litteral du foyer est confronte a l'enum du registre
    COMBAT (`TargetingRule`), deux sources ecrites independamment."""
    assert TQ.ALLOW_UNWALKABLE_TARGET_TILE == 1 << 43
    assert TQ.ALLOW_UNWALKABLE_TARGET_TILE == int(TR.AllowUnwalkableTargetTile)


def test_both_volets_of_is_walkable_remove_the_tile():
    """`IsWalkable(t, checkFog: true)` agrege DEUX volets ; chacun suffit a retirer la tuile."""
    assert TQ.tile_removed_by_walkability(0x4002, False, False) is True    # terrain infranchissable
    assert TQ.tile_removed_by_walkability(0x4002, True, True) is True      # IsInFogOfWar
    assert TQ.tile_removed_by_walkability(0x4002, True, False) is False


def test_the_allow_bit_disarms_the_whole_stage():
    """`(Rules & AllowUnwalkableTargetTile) != 0` -> le `RemoveAll` n'est PAS applique du tout."""
    rules = 0x4002 | TQ.ALLOW_UNWALKABLE_TARGET_TILE
    assert TQ.tile_removed_by_walkability(rules, False, True) is False


def test_a_muted_channel_is_not_a_false_channel():
    """TRI-ETAT. `None` = << pas mesure >>, jamais << marchable >> ni << non marchable >> : chaque
    volet muet est INERTE, et le masque non RE-lu desarme l'etage (convention permissive du module,
    ECART NOMME -- le natif RETIRE par defaut)."""
    assert TQ.tile_removed_by_walkability(0x4002, None, None) is False
    assert TQ.tile_removed_by_walkability(0x4002, True, None) is False
    assert TQ.tile_removed_by_walkability(0x4002, None, True) is True
    assert TQ.tile_removed_by_walkability(None, False, True) is False


# ------------------------------------------------------------------------------------------------
# 2. LE CABLAGE -- les deux cartes traversent-elles vraiment le consommateur ?
# ------------------------------------------------------------------------------------------------

def test_the_normal_attack_term_is_gated_by_walkability():
    """Le terme de l'attaque NORMALE porte le masque `NORMAL_ATTACK_TARGETING_OPTIONS` (0x4002), qui
    ne pose PAS le bit 43 : il est donc gate quel que soit le kit. C'est le terme le plus frequent,
    et celui qui rend l'etage effectif meme quand le masque d'une ability n'est pas RE-lu."""
    assert not (int(NORMAL_ATTACK_TARGETING_OPTIONS.rules) & TQ.ALLOW_UNWALKABLE_TARGET_TILE)
    assert _covers((1, 0), walkable_by_pos={(1, 0): True}) is True
    assert _covers((1, 0), walkable_by_pos={(1, 0): False}) is False


def test_the_fog_volet_travels_to_the_foyer_too():
    """Le SECOND volet n'est pas derivable du premier : `boardGraph.walkable` vient de
    `BattleQuery$$IsWalkableTile`, qui n'a pas de parametre `checkFog`. Une tuile MARCHABLE et en
    FOG doit etre retiree -- 31 tuiles sur 63 dans ce cas sur `C6_02`."""
    assert _covers((1, 0), walkable_by_pos={(1, 0): True},
                   is_in_fog_by_pos={(1, 0): True}) is False
    assert _covers((1, 0), walkable_by_pos={(1, 0): True},
                   is_in_fog_by_pos={(1, 0): False}) is True


def test_muted_maps_preserve_the_previous_behaviour():
    """NON-REGRESSION : sans les cartes, le consommateur rend EXACTEMENT ce qu'il rendait avant la
    tranche. Le defaut ne retire rien."""
    assert _covers((1, 0)) is True
    assert _covers((1, 0), walkable_by_pos=None, is_in_fog_by_pos=None) is True
    assert _covers((1, 0), walkable_by_pos={}) is True          # carte VIDE = tuile absente = muet


def test_an_ability_term_is_gated_too_and_1116_is_exempt():
    """Le gate porte AUSSI sur le terme PAR ABILITY, avec le masque de CETTE ability.
    `1116 RadBombardment` est le SEUL des 106 masques RE-lus a porter le bit 43 : sa zone garde
    donc les tuiles non marchables, et c'est ce qui separe les deux termes."""
    o1161 = targeting_options_for(1161)
    o1116 = targeting_options_for(1116)
    assert not (int(o1161.rules) & TQ.ALLOW_UNWALKABLE_TARGET_TILE)
    assert int(o1116.rules) & TQ.ALLOW_UNWALKABLE_TARGET_TILE
    walk = {(1, 0): False}
    assert AR._unwalkable(o1161.rules, (1, 0), walk, None) is True
    assert AR._unwalkable(o1116.rules, (1, 0), walk, None) is False


def test_the_ability_term_wiring_is_guarded_beyond_its_foyer():
    """Le test ci-dessus interroge le FOYER ; celui-ci garde son CABLAGE dans le terme PAR ABILITY
    -- deux choses independantes, et c'est une contre-epreuve de MUTATION qui l'a montre (couper
    l'appel dans `_ability_covers_tile` laissait le fichier VERT).

    La tuile est a `d = 3` : hors de la portee de l'arme de MELEE du porteur, donc le terme de
    l'attaque NORMALE ne peut pas la couvrir. Seule `1161 TwinSmartMissileSystem` (`UseWholeBoard`)
    l'atteint -- et son masque ne porte PAS le bit 43."""
    far = (3, 0)
    assert AR.is_tile_in_range_of_any_ability((0, 0), far, MELEE, ability_ids=[1161]) is True
    assert AR.is_tile_in_range_of_any_ability(
        (0, 0), far, MELEE, ability_ids=[1161], walkable_by_pos={far: False}) is False
    assert AR.is_tile_in_range_of_any_ability(
        (0, 0), far, MELEE, ability_ids=[1161],
        walkable_by_pos={far: True}, is_in_fog_by_pos={far: True}) is False
    # `1116 RadBombardment` porte le bit 43 : sa zone GARDE la tuile non marchable -- le
    # discriminant du foyer, exerce ici a travers tout le cablage. Sa portee est
    # `TargetingRange.CustomRange(1)`, donc la tuile temoin est a `d = 1` : le terme de l'attaque
    # NORMALE l'atteint aussi, mais il la REFUSE (masque 0x4002), et c'est bien le terme d'ability
    # qui fait basculer l'union.
    near = (1, 0)
    assert AR.is_tile_in_range_of_any_ability(
        (0, 0), near, MELEE, ability_ids=[], walkable_by_pos={near: False}) is False
    assert AR.is_tile_in_range_of_any_ability(
        (0, 0), near, MELEE, ability_ids=[1116], walkable_by_pos={near: False}) is True


def test_the_stage_is_upstream_of_line_of_sight():
    """L'ORDRE, rendu OBSERVABLE : une tuile non marchable est retiree meme quand AUCUN canal de
    ligne de vue n'est fourni (`elev_by_pos` absent -> `board is None` -> `target_is_obscured` rend
    `False` par construction). Si le retrait avait ete cable en AVAL, il n'aurait pas lieu ici."""
    assert _covers((1, 0), walkable_by_pos={(1, 0): False}, elev_by_pos=None) is False


# ------------------------------------------------------------------------------------------------
# 3. LE CANAL -- `isInFog` arrive-t-il jusqu'au playbook ?
# ------------------------------------------------------------------------------------------------

def test_the_nc_context_carries_the_fog_map():
    """`NCContext.is_in_fog_by_pos` existe et defaute a `{}` (canal muet), comme `is_wall_by_pos`."""
    from engine.playbook.noncomparable._base import NCContext
    ctx = NCContext(uid=1, origin=(0, 0), reach_nc=[], epos=[], fpos=[], plan={}, hp_cur_by_id={})
    assert ctx.is_in_fog_by_pos == {}


def test_the_generator_forwards_both_maps_to_the_playbook():
    """Le generateur NonComparable RECOPIE les deux cartes du `AiDecisionContext` dans le
    `NCContext` : sans cette ligne, le port serait juste a son foyer et muet chez son consommateur
    (le vice mesure sur `is_wall_by_pos` avant #433-r4-r2-r1-r2)."""
    import inspect
    from engine.ai import action_generators as AG
    src = inspect.getsource(AG.NonComparableGenerator.generate)
    assert "is_in_fog_by_pos=" in src
    assert "walkable_by_pos=" in src


def test_the_offline_bridge_exposes_the_fog_map():
    """Le bridge OFFLINE publie la meme carte que le contexte LIVE, en TRI-ETAT STRICT : un board
    dont aucune tuile ne PORTE la cle rend `{}` (canal muet), jamais un dict de `False` qui se
    lirait << mesure : aucune tuile en fog >>. L'erreur serait du bon cote, mais elle mentirait."""
    from engine.ai.state_bridge import _board_fog_map

    class _B:
        def __init__(self, tiles):
            self.by_id = {i: t for i, t in enumerate(tiles)}

    assert _board_fog_map(None) == {}
    assert _board_fog_map(_B([{"col": 0, "row": 0}, {"col": 1, "row": 0}])) == {}
    got = _board_fog_map(_B([{"col": 0, "row": 0, "isInFog": True},
                             {"col": 1, "row": 0, "isInFog": False}]))
    assert got == {(0, 0): True, (1, 0): False}


def test_the_consumer_passes_the_maps_down():
    """`EarlyWarningOverridePlaybook` -- le seul appelant de `is_tile_in_range_of_any_ability` --
    transmet les deux cartes jusqu'a lui."""
    import inspect
    from engine.playbook.noncomparable import early_warning_override as EW
    src = inspect.getsource(EW)
    assert "walkable_by_pos=walkable_by_pos" in src
    assert "is_in_fog_by_pos=is_in_fog_by_pos" in src
