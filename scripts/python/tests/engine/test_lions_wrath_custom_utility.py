"""TheLionsWrath (1217) -- garde OFFLINE de la FORME du terme custom et de son substrat.

Le pendant LIVE (`test_lions_wrath_decision_live.py`) confronte le CHOIX au natif ; ce fichier-ci
garde ce que le live ne peut pas exercer :

  * les trois facteurs SEPAREMENT (`30 x Hits`, `2000 x n`, `150 x [Hero]`), chacun mis a zero par
    un montage ou lui seul disparait -- en live ils sont toujours melanges ;
  * le filtre `IsNormalUnit && HasTrait(Chaos) && HasTrait(Hero)` sur les ADJACENTS : en live il
    faudrait un ennemi `Object`/`Steppable` adjacent au caster AU SPAWN ;
  * le fait que `Chaos` (0x7ea) est un pseudo-trait de GRANDE-ALLIANCE, absent de tout `traits` de
    gameconfig -- lire `unit["traits"]` nu rendrait un compte SYSTEMATIQUEMENT NUL, sans erreur ;
  * `find_melee_weapon` / `weapon_hits` : le filtre `IsMelee` (INVERSE de `find_ranged_weapon`) et
    le defaut `0` (et non `1`) quand l'unite n'a pas d'arme de melee.

ASCII only.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import hexgeo                                               # noqa: E402
import engine.playbook as PB                                # noqa: E402
from engine.playbook.nonattack import NONATTACK_PLAYBOOKS   # noqa: E402
from engine.services.battle_query import (find_melee_weapon,  # noqa: E402
                                          find_ranged_weapon, weapon_hits)

LIONS_WRATH = 1217

# Deux tuiles ADJACENTES et une LOINTAINE, verifiees par `hexgeo` plutot que postulees.
ORIGIN = (5, 5)
NEAR_A = (5, 6)
NEAR_B = (6, 5)
FAR = (9, 9)

CHAOS_HERO = "blackAbaddon"        # GrandAlliance Chaos + trait Hero, arme de melee a 5 coups
CHAOS_HERO_2 = "thousAhriman"      # Chaos + Hero, arme de melee a 1 coup
IMPERIAL_HERO = "darkaAzrael"      # Hero mais Imperial -> ne compte PAS dans `n`
MACHINE = "adeptExorcist"          # MachineOfWar : ni Hero, ni arme de melee


def _u(uid, vis, pos):
    return {"id": uid, "visualId": vis, "alive": True,
            "pos": {"col": pos[0], "row": pos[1]}, "ctrl": False}


def _ctx(enemies):
    """`ctx` minimal : `scene = None` fait retomber `entity_trait_names` sur le substrat STATIQUE
    (kit gameconfig + pseudo-trait de grande-alliance), ce qui est exactement ce qu'on veut garder."""
    return types.SimpleNamespace(units=list(enemies), enemies=list(enemies),
                                 elev_by_pos={}, scene=None)


def _pb():
    return PB.REGISTRY.get(LIONS_WRATH)


def test_the_two_tiles_used_by_this_file_are_really_adjacent():
    """Un montage dont la geometrie serait fausse rendrait `n = 0` partout et TOUS les tests de ce
    fichier passeraient pour de mauvaises raisons."""
    assert hexgeo.distance(ORIGIN, NEAR_A) == 1
    assert hexgeo.distance(ORIGIN, NEAR_B) == 1
    assert hexgeo.distance(ORIGIN, FAR) > 1


def test_dispatch_and_route():
    """1217 doit etre sur `TheLionsWrathPlaybook` ET dans `NONATTACK_PLAYBOOKS` : hors de ce
    registre l'ability n'a AUCUNE route (elle est invisible de `_best_attack`, dont le gate porte
    sur la seule utilite de degat) et le terme serait INERTE."""
    assert type(_pb()).__name__ == "TheLionsWrathPlaybook"
    assert LIONS_WRATH in NONATTACK_PLAYBOOKS


def test_make_damage_predictions_is_empty():
    """`...TheLionsWrathPlaybook$$MakeDamagePredictions` rend une liste VIDE (trois canaux natifs
    concordants, cf. la docstring du port). C'est ce fait qui fixe la route."""
    assert _pb().make_damage_predictions(_ctx([]), ORIGIN, 1, LIONS_WRATH) == []


def test_find_melee_weapon_mirrors_the_native_selection():
    """`FindMeleeWeapon(unit)` = `SelectMaxRangeWeapon({w : w.IsMelee})` -- filtre INVERSE de
    `find_ranged_weapon`, et `None` quand l'unite n'a aucune arme de melee."""
    assert weapon_hits(find_melee_weapon(CHAOS_HERO)) == 5
    assert weapon_hits(find_melee_weapon(CHAOS_HERO_2)) == 1
    w = find_melee_weapon(CHAOS_HERO)
    assert w is not None and (w.get("Range") is None or int(w["Range"]) < 2), (
        "l'arme rendue n'est pas MELEE au sens de `WeaponProfile$$get_IsMelee`")
    assert find_melee_weapon(MACHINE) is None, (
        "%s n'a pas d'arme de melee : le natif rend `null` (set vide -> SelectMaxRangeWeapon)"
        % MACHINE)
    # Le filtre est bien INVERSE : ce que rend `find_ranged_weapon` n'est jamais melee.
    r = find_ranged_weapon(CHAOS_HERO)
    assert r is None or (r.get("Range") is not None and int(r["Range"]) >= 2)


def test_weapon_hits_defaults_to_zero_not_one():
    """`iVar8` reste a 0 quand `FindMeleeWeapon` rend `null`. Un defaut a `1` offrirait 30 points."""
    assert weapon_hits(None) == 0
    assert weapon_hits({}) == 0


def test_no_adjacent_enemy_leaves_only_the_target_terms():
    """`n = 0` -> `30 x Hits + 150 x [Hero]`, et RIEN d'autre."""
    tgt = _u(1, CHAOS_HERO, FAR)
    ctx = _ctx([tgt])
    assert _pb().calculate_custom_utility(ctx, ORIGIN, 1, LIONS_WRATH) == 30 * 5 + 150


def test_adjacent_chaos_hero_counts_and_is_linear():
    """`2000 x n`, LINEAIRE : un puis deux adjacents Chaos+Hero."""
    a = _u(1, CHAOS_HERO, NEAR_A)
    b = _u(2, CHAOS_HERO_2, NEAR_B)
    pb = _pb()
    one = pb.calculate_custom_utility(_ctx([a, _u(3, CHAOS_HERO_2, FAR)]), ORIGIN, 1, LIONS_WRATH)
    two = pb.calculate_custom_utility(_ctx([a, b]), ORIGIN, 1, LIONS_WRATH)
    assert one == 2000 + 30 * 5 + 150
    assert two == 2 * 2000 + 30 * 5 + 150


def test_adjacent_non_chaos_hero_does_not_count():
    """Le filtre est une CONJONCTION : `darkaAzrael` est `Hero` mais Imperial -> exclu de `n`.
    C'est aussi le test qui prouve que le pseudo-trait de GRANDE-ALLIANCE est bien lu : sans lui,
    `blackAbaddon` non plus ne compterait pas, et `test_adjacent_chaos_hero_counts...` tomberait."""
    a = _u(1, IMPERIAL_HERO, NEAR_A)
    tgt = _u(2, CHAOS_HERO, FAR)
    assert _pb().calculate_custom_utility(_ctx([a, tgt]), ORIGIN, 2, LIONS_WRATH) == 30 * 5 + 150


def test_target_terms_read_the_target_not_the_caster():
    """`Hits` et `Hero` sont ceux de la CIBLE : deux cibles differentes, meme voisinage, deux
    valeurs. C'est CE fait qui rend le terme discriminant par cible (et l'ability greffable)."""
    a = _u(1, CHAOS_HERO, NEAR_A)          # adjacent ET cible possible
    b = _u(2, CHAOS_HERO_2, NEAR_B)
    ctx = _ctx([a, b])
    pb = _pb()
    assert pb.calculate_custom_utility(ctx, ORIGIN, 1, LIONS_WRATH) == 2 * 2000 + 30 * 5 + 150
    assert pb.calculate_custom_utility(ctx, ORIGIN, 2, LIONS_WRATH) == 2 * 2000 + 30 * 1 + 150


def test_unknown_target_drops_both_target_terms():
    """Cible non resolue : le natif ferait `IsUnit(null)` (faux) puis `HasTrait(null, Hero)` (faux)
    -> les deux termes de CIBLE tombent a 0, le terme d'adjacence subsiste."""
    a = _u(1, CHAOS_HERO, NEAR_A)
    assert _pb().calculate_custom_utility(_ctx([a]), ORIGIN, 999, LIONS_WRATH) == 2000.0


def test_targeting_options_mask_is_target_is_enemy_only():
    """Masque EFFECTIF `0x4000` = `TargetIsEnemy` SEUL, avec `range = RANGE_ADJACENT`. Il est dans
    `TARGETING_OPTIONS_UNPORTED` (face COMBAT non portee) -- jamais dans `ABILITY_CLASSES`, dont il
    ferait passer la behaviour pour portee."""
    from engine.runner.abilities.targeting import (TARGETING_OPTIONS_UNPORTED, targeting_options_for)
    from engine.runner.abilities.handler import ABILITY_CLASSES
    o = TARGETING_OPTIONS_UNPORTED[LIONS_WRATH]
    assert int(o.rules) == 0x4000
    assert o.self_cast is False
    assert o.range is not None and o.range.override_range == 1
    assert targeting_options_for(LIONS_WRATH) is o
    assert LIONS_WRATH not in ABILITY_CLASSES
