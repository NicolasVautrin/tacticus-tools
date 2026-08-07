"""#508 -- CLIQUET du port de `1204 LeadingTheCharge` (`astraDreir` « Dreir »).

Ce que ce fichier garde, et que le probe live (`probe_508_leading_the_charge.py`) ne garde pas :
le probe MESURE (il a besoin d'une session Frida chaude) ; ce test GARDE, hors ligne, les cinq
proprietes dont la perte serait SILENCIEUSE -- et DEUX d'entre elles ont deja ete fausses dans ce
port meme, sans qu'aucun critere sur le total ne le montre.

  [1] CONTRAT DE DISJONCTION -- 1204 est dans `ABILITY_CLASSES` et porte son masque, donc elle doit
      avoir DISPARU des tables « non portee » (`TARGETING_OPTIONS_UNPORTED`,
      `DYNAMIC_TARGET_RULE_UNPORTED`, `POOL_ABILITIES_WITHOUT_COMBAT_CLASS`). La faute inverse ne
      casse rien a l'execution : elle donne DEUX sources au masque.

  [2] ORDINAUX MESURES AU SITE -- `probe_313` compare le MIRROR au build et redevient vert des
      qu'on regenere le mirror apres un renumerotage, alors que la valeur ECRITE au site, elle, a
      change. On fige donc ici les entiers LUS au decompile : `rules = 0x102004032` (preset
      `TargetingOptions statics+0x240`), `Infiltrate_UnitEffect = 0x416`,
      `TemporaryStatModifier = 0x56c`, `StatType.ExtraPierce = 0x1a`,
      `UtilityType.LeadingTheCharge_ChargeTile = 67`, `AbilityAttackType = 0`.

  [3] LE NIVEAU DE `nrOfSummons` -- MESURE #508 : lu SANS le niveau de l'`AbilityState`,
      `ability_var` retombe sur l'index 0 (`nrOfSummons` = **2** au niveau 1) alors que le runner
      normalise a 50 (**4**). Le natif posait QUATRE Death Riders, le port DEUX, et l'ecart ne se
      voyait NI sur la tuile d'atterrissage NI sur la sequence de la charge -- seulement sur les
      `AddUnit` natifs et sur DEUX tirages manquants. Le test fige la table par niveau.

  [4] LE SEUIL DE `HasAdjacentEnemies` -- LU `> 1` au decompile, REFUTE par la mesure : c'est
      `>= 1`. Le ctor que Ghidra nomme `AmountIsGreaterAbilityTrigger$$.ctor` est un corps TRIVIAL,
      donc DEDUPLIQUE entre `AmountIsGreater` et `AmountIsEqualOrGreater`. Un `> 1` rendrait le
      `SortByFormula` INERTE des qu'il n'y a qu'un ennemi -- et c'est exactement le regime le plus
      courant. Ce test exerce le predicat a UN et a ZERO ennemi adjacent.

  [5] STRUCTURE DES DEUX PHASES -- le natif appelle `AActiveAbility$$Execute` (AddEffect & MoveUnit)
      PUIS `AActiveAbility$$ExecuteAtomic` (SetCache & IfAlive(pierce & attaque) & If(spawn) &
      RemoveEffect). L'ORDRE EST la mecanique : le pierce pose AVANT l'attaque en fait beneficier
      l'attaque du cast, et le `RemoveEffect` final le retire du caster ET de ses summons.

ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre DECLARE LARGE, et c'est mesure : charger une ability tire le registre, le vocabulaire
#: DSL, les Operations, l'IA, le pathfinding et les utilites (~139 modules), plus la cascade des
#: `conftest.py`. Une liste feuille a feuille rougirait au premier import ajoute. `**/` exige un
#: SEGMENT, d'ou les deux globs ET les quatre conftest ecrits un par un.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/**/*.py", "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1204 et TOUT ce que sa fermeture d'imports traverse : registre "
              "d'abilities, tables de ciblage, vocabulaire DSL, Operations de spawn, base "
              "d'utilites de tuile. `build: True` parce que les ordinaux figes ici (masque, "
              "EffectType, StatType, UtilityType, AbilityAttackType) sont LUS dans le binaire du "
              "build -- un changement de build peut les renumeroter, et c'est precisement ce que "
              "ce fichier doit faire rougir.",
}

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import gameconfig as GC                                                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.behaviours import If, Seq                             # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.stats import StatType                                 # noqa: E402
from engine.entities.triggers import IsAlive                               # noqa: E402
from engine.runner.abilities.attack_type import (ABILITY_ATTACK_TYPE,      # noqa: E402
                                                 AbilityAttackType)
from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage   # noqa: E402
from engine.runner.abilities.behaviours.effects import (AddEffect,         # noqa: E402
                                                        AddStaticStatModifierEffect, RemoveEffect)
from engine.runner.abilities.behaviours.movement import MoveUnit           # noqa: E402
from engine.runner.abilities.behaviours.summon import PerformAIAttack, Spawn   # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.loki.leading_the_charge import (              # noqa: E402
    INFILTRATE, LEADING_THE_CHARGE_TILE_UTILITY, TEMPORARY_STAT_MODIFIER, EXTRA_PIERCE,
    LeadingTheChargeAbility, leading_the_charge_attack_tree, leading_the_charge_cleanup_tree,
    leading_the_charge_head_tree, leading_the_charge_spawn_tree)
from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,   # noqa: E402
                                               TARGETING_OPTIONS_UNPORTED)
from engine.utilities.leading_the_charge import LeadingTheCharge_ChargeTile    # noqa: E402
from engine.utilities.tile import utilities_database                       # noqa: E402
from engine.utilities.utility_type import UtilityType                      # noqa: E402

ABILITY = int(ActiveAbilityType.LeadingTheCharge)          # 1204


# ---------------------------------------------------------------- [1] disjonction

def test_1204_est_au_registre_et_a_UNE_seule_source_de_masque():
    """Le CONTRAT : une ability a UNE source de masque, jamais deux."""
    assert ABILITY in ABILITY_CLASSES, "1204 absente d'ABILITY_CLASSES -- le no-op n'est pas leve"
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED, "deux sources de masque pour 1204"
    assert ABILITY not in DYNAMIC_TARGET_RULE_UNPORTED, (
        "1204 encore dans DYNAMIC_TARGET_RULE_UNPORTED alors que la classe SURCHARGE "
        "get_dynamic_invalid_target_reason")
    assert not (set(ABILITY_CLASSES) & set(TARGETING_OPTIONS_UNPORTED)), (
        "la disjonction globale est rompue")


def test_la_classe_surcharge_bien_la_regle_dynamique():
    """`TargetMatchesDynamicRule` est POSE dans le masque : sans surcharge, la base rend 0 et le
    gate qui donne sa FORME a la zone de ciblage serait DESARME (degradation permissive)."""
    from engine.runner.abilities.base import ActiveAbility
    assert (LeadingTheChargeAbility.get_dynamic_invalid_target_reason
            is not ActiveAbility.get_dynamic_invalid_target_reason)


# ---------------------------------------------------------------- [2] ordinaux mesures au site

def test_ordinaux_lus_au_decompile():
    """Ce que `probe_313` ne peut PAS garder : la valeur ECRITE AU SITE au moment de la lecture."""
    opts = LeadingTheChargeAbility.TARGETING_OPTIONS
    assert int(opts.rules) == 0x102004032, (
        "masque de 1204 : le preset `TargetingOptions statics+0x240` porte rules=0x102004032")
    assert opts.self_cast is False
    assert INFILTRATE == 0x416 == int(EffectType.Infiltrate_UnitEffect)
    assert TEMPORARY_STAT_MODIFIER == 0x56c == int(EffectType.TemporaryStatModifier)
    assert EXTRA_PIERCE == 0x1a == int(StatType.EXTRA_PIERCE)
    assert int(UtilityType.LeadingTheCharge_ChargeTile) == 67
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.DirectTargetAttack, (
        "3e argument d'`AActiveAbility$$.ctor` = 0 = DirectTargetAttack")


def test_le_bucket_de_GetMoveTile_a_DEUX_termes_de_poids_1():
    """`GetMoveTile` batit sa `UtilityDefinition` A LA MAIN : deux `WeightedUtility` avec un
    `Nullable<Fix64>` VIDE -> poids 1 chacun, difference minimale 0 (somme NUE)."""
    b = LEADING_THE_CHARGE_TILE_UTILITY.bucket
    assert [w.utility_type for w in b.utilities] == [int(UtilityType.MovementSuggestion),
                                                     int(UtilityType.LeadingTheCharge_ChargeTile)]
    assert [w.weight for w in b.utilities] == [1.0, 1.0]
    assert b.min_utility_difference == 0.0
    # La feuille 67 DOIT etre au registre : `calculate_utility` LEVE sur un type absent, donc son
    # oubli ferait planter le 1er cast au lieu de degrader.
    assert isinstance(utilities_database(int(UtilityType.LeadingTheCharge_ChargeTile)),
                      LeadingTheCharge_ChargeTile)


# ---------------------------------------------------------------- [3] le niveau de nrOfSummons

def test_nrOfSummons_est_lu_PAR_NIVEAU():
    """MESURE #508 : au niveau 1 la variable vaut 2, au niveau 50 elle vaut 4. Un port qui ne
    passe pas le niveau pose DEUX Death Riders la ou le natif en pose QUATRE -- invisible du total
    de la charge, visible seulement sur `AddUnit` et sur deux tirages."""
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.ability_variable_type import AbilityVariableType
    cle = AbilityVariableType.nrOfSummons.name
    assert int(ability_var("LeadingTheCharge", cle, 1) or 0) == 2
    assert int(ability_var("LeadingTheCharge", cle, 50) or 0) == 4
    # Et la table gameconfig elle-meme, pour que le test rougisse si l'ability est re-equilibree.
    vals = ((GC.ability("LeadingTheCharge") or {}).get("variables") or {}).get("nrOfSummons") or []
    assert (len(vals) >= 50 and int(vals[0]) == 2 and int(vals[49]) == 4), (
        "table nrOfSummons re-equilibree : %r" % (vals[:3],))


def test_les_constantes_du_cast_sont_celles_du_gameconfig():
    """`GetNumberConstant(0x16 = range)` et `GetStringConstant(0 = unitId)` -- les DEUX index sont
    LUS au decompile, jamais devines (`unitToSpawn` = 8 existe aussi, et le confondre rend un
    spawn SILENCIEUSEMENT absent)."""
    consts = (GC.ability("LeadingTheCharge") or {}).get("constants") or {}
    assert int(consts.get("range")) == 4
    assert consts.get("unitId") == "astraSmnDeathRider"
    assert int(consts.get("nrOfHits")) == 3
    assert consts.get("damageProfile") == "Power"


# ---------------------------------------------------------------- [4] le seuil de HasAdjacentEnemies

class _Stub:
    """Etat MINIMAL pour exercer `_has_adjacent_enemies` : le predicat ne lit que l'owner, les
    positions et le trait `Steppable`."""

    class _Board:
        pass

    def __init__(self, unites):
        from engine.runner.components import (OwnerComponent, PositionComponent, UnitComponent)
        from engine.runner.state import Entity
        self.board = self._Board()
        self.entities = {}
        for eid, (team, pos, alive) in unites.items():
            e = Entity(eid)
            e.add_component(UnitComponent(visual_id=None, alive=alive))
            e.add_component(OwnerComponent(team=team))
            if pos is not None:
                e.add_component(PositionComponent(col=pos[0], row=pos[1]))
            self.entities[eid] = e

    def get_entity(self, eid):
        return self.entities.get(int(eid))


def test_HasAdjacentEnemies_mord_a_UN_ennemi_pas_a_deux():
    """LE point que le decompile seul faisait ecrire de travers (`AmountIsGreater` contre
    `AmountIsEqualOrGreater` -- meme corps de ctor, donc meme NOM chez Ghidra). La mesure live a
    tranche : avec UN SEUL ennemi sur le plateau, le natif met en TETE de ses tuiles de summon
    exactement les deux adjacentes a cet ennemi -> le predicat vaut VRAI a UN."""
    from engine.runner.abilities.loki.leading_the_charge import _has_adjacent_enemies
    st = _Stub({1: (1, (5, 5), True),          # l'owner (equipe 1)
                2: (2, (5, 8), True)})         # UN ennemi
    assert _has_adjacent_enemies(st, (5, 7), 1) is True, "un seul ennemi adjacent doit suffire"
    assert _has_adjacent_enemies(st, (5, 6), 1) is False, "aucun ennemi adjacent -> False"
    # Un MORT ne compte pas (`AdjacentUnits` ne rend que des unites POSEES et vivantes).
    st2 = _Stub({1: (1, (5, 5), True), 2: (2, (5, 8), False)})
    assert _has_adjacent_enemies(st2, (5, 7), 1) is False


# ---------------------------------------------------------------- [5] structure des deux phases

def _feuilles(node, out=None):
    """Aplati un arbre de behaviours en la LISTE de ses feuilles, dans l'ordre d'execution."""
    out = [] if out is None else out
    if isinstance(node, Seq):
        _feuilles(node.left, out)
        _feuilles(node.right, out)
    elif isinstance(node, If):
        out.append(("If", type(node.cond).__name__))
        _feuilles(node.then, out)
    else:
        out.append(type(node).__name__)
    return out


def test_phase_1_est_AddEffect_PUIS_MoveUnit():
    """`Execute( AddEffect(Infiltrate, Direct(1) tour) & MoveUnit(caster, GetMoveTile()) )`."""
    arbre = leading_the_charge_head_tree((5, 7))
    assert _feuilles(arbre) == ["AddEffect", "MoveUnit"]
    gauche = arbre.left
    assert isinstance(gauche, AddEffect) and gauche.effect_type == INFILTRATE
    assert gauche.duration_turns == 1, "`DSLFormulas+0x20` = Direct(1) = UN TOUR, pas un round"
    assert isinstance(arbre.right, MoveUnit)


def test_phase_2_pose_le_pierce_AVANT_l_attaque_sous_un_gate_IsAlive():
    """L'ORDRE EST la mecanique : l'attaque du cast BENEFICIE du +pierce. L'inverser changerait le
    degat sans changer le nombre de coups -- exactement le genre d'ecart qu'un compte ne voit pas."""
    arbre = leading_the_charge_attack_tree(30)
    assert isinstance(arbre, If) and isinstance(arbre.cond, IsAlive)
    assert _feuilles(arbre) == [("If", "IsAlive"), "AddStaticStatModifierEffect",
                                "AttackWithAttackDamage"]
    pierce = arbre.then.left
    assert isinstance(pierce, AddStaticStatModifierEffect)
    assert (pierce.effect_type, pierce.stat_type) == (TEMPORARY_STAT_MODIFIER, EXTRA_PIERCE)
    assert pierce.duration_turns == 1
    atk = arbre.then.right
    assert isinstance(atk, AttackWithAttackDamage)


def test_l_on_appearance_du_spawn_porte_le_pierce_ET_l_attaque_ia():
    """`opts.onAppearance(+0x18) = AddStaticStatModifierEffect(activeTarget) &
    PerformAIAttackFromCurrentPosition(activeTarget)` -- chaque Death Rider recoit le MEME bonus
    que Dreir, puis attaque SANS BOUGER (`allowMoveAction = 0`, `moveAmount = Direct(0)`)."""
    spawn = leading_the_charge_spawn_tree([(6, 7), (4, 7)], 30)
    assert isinstance(spawn, Spawn)
    assert spawn.unit_id_constant == "unitId", "`GetStringConstant(0)`, pas `unitToSpawn` (8)"
    assert _feuilles(spawn.on_appearance) == ["AddStaticStatModifierEffect", "PerformAIAttack"]
    ai = spawn.on_appearance.right
    assert isinstance(ai, PerformAIAttack)
    assert (ai.allow_move_action, ai.move_amount) == (False, 0), (
        "`...FromCurrentPosition` : le Death Rider n'APPROCHE pas")


def test_le_cleanup_retire_le_pierce_du_caster_ET_de_ses_enfants():
    """`RemoveEffect(caster@0x48 + Children(caster@0x48), Nullable(0x56c))` -- net-zero. Sans lui,
    le +pierce survivrait au cast sur les summons, qui rejouent au tour suivant."""
    from engine.entities.selectors.tiles import Caster, Children
    from engine.entities.selectors.units import Union
    node = leading_the_charge_cleanup_tree()
    assert isinstance(node, RemoveEffect) and node.effect_type == TEMPORARY_STAT_MODIFIER
    assert isinstance(node.target_sel, Union)
    assert isinstance(node.target_sel.a, Caster) and isinstance(node.target_sel.b, Children)


# ---------------------------------------------------------------- la feuille d'utilite 67

class _Wt:
    def sub(self, categorie, cle, default=0):
        assert (categorie, cle) == ("LeadingTheCharge_ChargeTile", "PreferAdjacentFreeTiles")
        return 5                      # `data/seed-bc.json` -> Utilities.Default.<cat>.<cle>


def test_utilite_67_compte_les_voisins_LIBRES_et_compte_self_comme_occupe():
    """`#GetFreeAdjacentTiles(tile) x PreferAdjacentFreeTiles`. `self_pos` est OCCUPE
    (`TileContentComponent$$IsEmpty` rend FAUX sur la tuile ou l'unite se tient encore), et ce
    corps natif ne le RE-CREDITE PAS -- contrairement a `GeminaeSuperiaPlaybook`."""
    u = LeadingTheCharge_ChargeTile()
    walkable = {(c, r): True for c in range(0, 8) for r in range(0, 10)}
    ctx_libre = {"walkable_by_pos": walkable, "friend_units": (), "enemy_units": (),
                 "self_pos": None}
    plein = u.evaluate((5, 5), None, ctx_libre, _Wt())
    assert plein == 6 * 5, "six voisins libres x 5 = 30 (repli hexgeo en l'absence de neigh_by_pos)"
    # Les DEUX positions sont des voisines REELLES de (5,5) (`hexgeo.neighbors(5,5)` =
    # [(4,4),(4,5),(5,4),(5,6),(6,4),(6,5)]) : une position non voisine ne retirerait rien et le
    # test mesurerait autre chose que ce qu'il annonce.
    ctx_occ = dict(ctx_libre, enemy_units=({"pos": (5, 6)}, {"pos": (6, 5)}))
    assert u.evaluate((5, 5), None, ctx_occ, _Wt()) == 4 * 5
    # `self_pos` compte comme OCCUPE, sans re-credit.
    assert u.evaluate((5, 5), None, dict(ctx_libre, self_pos=(5, 6)), _Wt()) == 5 * 5
    # Aucun voisin placable -> 0 (le `if (free.Count > 0)` natif, inerte mais transcrit).
    assert u.evaluate((5, 5), None, dict(ctx_libre, walkable_by_pos={(5, 5): True}), _Wt()) == 0.0
