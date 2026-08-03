"""InstrumentsOfVengeance (1215, porteur `darkaBossLion` npc -> GREFFE) -- DECISION, confrontee au LIVE.

CE QUE CE TEST GARDE (et pourquoi il ne peut pas passer par accident) :

A. **La GREFFE exerce bien `InstrumentsOfVengeancePlaybook`.** Le seul porteur de 1215 est un npc ;
   le natif charge le playbook PAR ABILITY (`PlaybookDatabase.LoadPlaybook(abilityType)`), donc
   greffer `[1215]` sur `darkaAsmodai` suffit -- et le natif le PROUVE deux fois : il emet
   `ActiveAbilityMessage(1215)`, et le RPC `pairUtility` rend
   `playbookClass = InstrumentsOfVengeancePlaybook` sur l'unite greffee.
B. **La ROUTE est la bonne.** `pairUtility(1215, SELF) = 0` (la cible est le caster : aucun degat
   predit) et les `attackPlans.evals` de 1215 sur les ENNEMIS ont tous `rankCount = 0` :
   `_best_attack` ne peut RIEN produire, d'ou la route non-attaque bien que
   `constants.damageProfile = HeavyRound`. Le bras `noroute` rejoue la decision dans l'etat d'AVANT
   le port -- s'il rendait la meme chose, le port serait inerte.
C. **Le terme custom est NECESSAIRE** : force a 0, le moteur DIVERGE du natif sur les trois bras ou
   la geometrie n'est pas degeneree (B, C, F).
D. **Le TERME EST POSITION-DEPENDANT, et c'est ce qui rend ses constantes discriminables** :
   1215 n'a PAS `CasterHasNotMoved` (contraste 1216), donc il existe autant d'actions 1215 que de
   tuiles atteignables et le natif CHOISIT SA TUILE. Le `+100` (bras B) et le `+20` (bras C) sont
   mesures par ce choix, pas postules.
E. **Le QUIRK de geometrie est mesure** : `GetAdjacentEnemies` porte la porte d'elevation
   `|dElev| < 2` d'`IterateAdjacentTiles`, `GetSurroundingEnemies` non (disque hex pur). Au bras F,
   le modele `20 x |dist == 2|` -- celui qu'on ecrirait en resumant `surrounding \\ adj` par une
   distance -- choisit une AUTRE tuile que le natif.
F. **`abilityTargets(1215)` SURVIT au deplacement du caster** : c'est la contre-epreuve du masque
   `0x8004` (static-copy du preset `<TargetingOptions statics>+0x280`, SANS le `| 0x10` que 1216
   ajoute). Si ce bit etait pose a tort, la cible tomberait a 0 apres le move, comme pour 1216.

CE QUI N'EST PAS GARDE, ET POURQUOI (dit plutot que masque) :
* le gate `...InstrumentsOfVengeancePlaybook$$ShouldEvaluate` n'est PAS porte. Son volet
  `GetUseProbability(turnsFinished == 1) = Fix64.Half` est un TIRAGE (meme statut que
  `...PlasmaGrenadePlaybook$$GetUseProbability`) ; son volet `== 0` est DETERMINISTE et le port ne
  peut pas le mirrorer -- `turnsFinished` (`UnitComponent + 0x5c`) est absent de `decisionView`.
  L'ECART est MESURE ici (`test_turns_finished_zero_gate_is_a_named_gap`), pas suppose : au tour du
  build le natif ne propose PAS 1215 et le moteur SI. Le reste du fichier mesure dans la fenetre
  DETERMINISTE `turnsFinished >= 2`, ou le gate rend `true` des deux cotes ;
* `HasMinimumRemainingTurns(unit, 2)` rend `true` des que la limite de tours du match est ABSENTE --
  le regime du runner. Le defaut permissif de la route y est EXACT ; aucun canal offline n'expose
  cette limite (residu nomme) ;
* la face COMBAT de 1215 (`...InstrumentsOfVengeanceAbility$$ExecuteBehaviour`) n'est pas portee.

ASCII only.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_27_r6_instruments_of_vengeance as AB           # noqa: E402
import engine.playbook as PB                                # noqa: E402

INSTRUMENTS = AB.INSTRUMENTS
GEOMETRIC_ARMS = ("B_adjacent", "C_ring2", "F_elevation")
ALL_ARMS = ("A_far",) + GEOMETRIC_ARMS


@pytest.fixture(scope="module")
def rows():
    rid = AB.build()
    try:
        yield AB.run_ab(rid, engine=True)
    finally:
        try:
            AB.L._rpc("disposeRunner", [{"runnerId": rid}])
        except Exception:                                   # noqa: BLE001
            pass


def test_graft_makes_the_native_emit_the_ability(rows):
    """A -- le natif propose 1215 sur LUI-MEME dans les quatre bras : la greffe exerce le playbook."""
    for key in ALL_ARMS:
        assert rows[key]["native"] == (INSTRUMENTS, rows["caster_id"]), (
            "bras %s : le natif a propose %r -- la greffe n'exerce pas le playbook, aucune des "
            "mesures suivantes ne vaut" % (key, rows[key]["native"]))


def test_native_loads_this_playbook_for_the_grafted_unit(rows):
    """A -- second canal, independant du choix : `pairUtility` NOMME le playbook charge."""
    assert (rows["pair_utility"] or {}).get("playbookClass") == "InstrumentsOfVengeancePlaybook", (
        "playbookClass = %r" % ((rows["pair_utility"] or {}).get("playbookClass"),))


def test_route_is_non_attack(rows):
    """B -- aucune prediction (cible = le caster) et aucun eval rankable sur les ennemis."""
    assert (rows["pair_utility"] or {}).get("utility") == 0, (
        "pairUtility(1215, SELF) = %r, attendu 0 -- `make_damage_predictions` ne peut plus rendre []"
        % ((rows["pair_utility"] or {}).get("utility"),))
    ranks = rows["attack_plan_ranks"]
    assert ranks, "1215 n'apparait pas dans attackPlans -- le montage ne teste plus la route"
    assert all(rc == 0 for _t, rc in ranks), (
        "attackPlans.evals(1215) = %r : un rankCount non nul rendrait `_best_attack` productive, "
        "et la route non-attaque serait un DOUBLON" % (ranks,))


def test_native_targets_only_the_caster(rows):
    """`CasterIsPossibleTarget` : la SEULE cible que le natif retient est le caster."""
    for key in ALL_ARMS:
        tg = rows[key]["targets_rpc"]
        assert len(tg) == 1 and tg[0] == ("unit", rows["caster_id"]), (
            "bras %s : abilityTargets(1215) = %r, attendu la seule cible UNITE <caster>" % (key, tg))
        assert rows[key]["engine"]["targets"] == [rows["caster_id"]], (
            "bras %s : le port enumere %r" % (key, rows[key]["engine"]["targets"]))


def test_engine_picks_the_same_tile_as_the_native(rows):
    """D -- l'accord porte sur (ability, cible, TUILE DE CAST), pas seulement sur l'ability."""
    for key in ALL_ARMS:
        e = rows[key]["engine"]
        assert e["on"] == (INSTRUMENTS, rows["caster_id"]), (
            "bras %s : moteur %r != natif %r" % (key, e["on"], rows[key]["native"]))
        assert e["to"] == rows[key]["native_to"], (
            "bras %s : le moteur caste depuis %r, le natif depuis %r -- le terme est POSITION-"
            "DEPENDANT, un desaccord de tuile est un desaccord de port"
            % (key, e["to"], rows[key]["native_to"]))


def test_the_native_moves_when_the_geometry_pays(rows):
    """D -- le montage EXERCE bien le sweep : degenere (A) le natif reste, sinon il se DEPLACE.

    Sans cette assertion, les trois bras geometriques pourraient tous rendre `to=None` et l'accord
    du test precedent serait trivial."""
    assert rows["A_far"]["native_to"] is None, (
        "bras A : le natif s'est deplace en %r alors que le custom est CONSTANT (20100 partout) -- "
        "le montage n'est plus degenere, il ne sert plus de temoin" % (rows["A_far"]["native_to"],))
    for key in GEOMETRIC_ARMS:
        assert rows[key]["native_to"] is not None, (
            "bras %s : le natif n'a pas bouge -- la geometrie ne paie pas, le bras ne discrimine "
            "aucune des trois constantes" % key)


def test_custom_term_and_route_are_both_necessary(rows):
    """C -- contre-epreuves : custom force a 0, et registre `NONATTACK_PLAYBOOKS` vide."""
    for key in GEOMETRIC_ARMS:
        e = rows[key]["engine"]
        assert e["zero"][:2] != (INSTRUMENTS, rows["caster_id"]) or e["zero"][2] != e["to"], (
            "bras %s : custom force a 0 rend la MEME decision (%r) -- le terme est inerte, l'accord "
            "vient d'ailleurs" % (key, e["zero"]))
        assert e["noroute"][0] != INSTRUMENTS, (
            "bras %s : route non-attaque DESACTIVEE rend toujours 1215 (%r) -- le port est inerte"
            % (key, e["noroute"]))


def test_adjacency_gate_costs_the_hundred(rows):
    """`adj.Any() ? 0 : 100` -- l'origine vaut 20100 sans ennemi adjacent, 20000 avec."""
    assert rows["A_far"]["engine"]["custom_origin"] == 20100.0
    assert rows["C_ring2"]["engine"]["custom_origin"] == 20100.0
    assert rows["B_adjacent"]["engine"]["custom_origin"] == 20000.0, (
        "bras B : custom(origine) = %r -- l'ennemi pose en (2,0) devrait etre ADJACENT a (1,0) et "
        "faire tomber le `+100`" % (rows["B_adjacent"]["engine"]["custom_origin"],))


def test_elevation_quirk_is_measured_not_assumed(rows):
    """E -- le modele `20 x |dist == 2|` DIVERGE du natif sur le bras F.

    C'est la seule assertion qui separe `surrounding \\ adj` (deux geometries natives distinctes) de
    son resume par une distance. Si elle tombe, le bras F ne discrimine plus rien et le quirk n'est
    garde que par la lecture du decompile."""
    f = rows["F_elevation"]
    assert f["engine"]["wrong"][2] != f["native_to"], (
        "bras F : le modele FAUX caste depuis %r, comme le natif -- la geometrie du montage ne "
        "distingue plus les deux modeles (elevations attendues : (1,2)=2 voisine de (1,3)=4)"
        % (f["engine"]["wrong"][2],))


def test_caster_has_not_moved_is_absent_from_the_mask(rows):
    """F -- 1215 SURVIT au deplacement du caster (contraste 1216, dont la cible tombait a 0)."""
    d = rows["caster_has_not_moved"]
    assert d["from"] != d["to"], (
        "le caster n'a pas bouge (%r -> %r) : le bit n'est pas exerce" % (d["from"], d["to"]))
    assert d["before"], "abilityTargets(1215) etait deja vide AVANT le move"
    assert d["after"] == d["before"], (
        "abilityTargets(1215) = %r apres le move (avant : %r) -- si la cible tombe, le masque porte "
        "`CasterHasNotMoved` et `TARGETING_OPTIONS_UNPORTED[1215]` est FAUX" % (d["after"], d["before"]))
    assert any(m.get("cls") == "ActiveAbilityMessage" for m in
               [{"cls": c} for c, _a, _t, _to in d["native_after"]]), (
        "le natif ne propose plus 1215 apres le deplacement du caster : %r" % (d["native_after"],))


def test_turns_finished_zero_gate_is_a_named_gap(rows):
    """Le gate `GetUseProbability` -- MESURE de l'ECART, pas de son absence.

    Au tour du build (`turnsFinished == 0`) le natif ne propose PAS 1215 ; le moteur SI. Ce test
    FIGE l'ecart : s'il tombe, c'est que le gate a ete porte (bonne nouvelle) ou que la fenetre a
    bouge -- dans les deux cas la case-doc doit etre relue."""
    assert rows["turns_before"] == 0, (
        "turnsFinished(caster) = %r au build, attendu 0" % (rows["turns_before"],))
    assert rows["turns_after"] >= AB.MIN_TURNS_FINISHED, (
        "turnsFinished(caster) = %r apres %d endturn -- la fenetre deterministe n'est pas ouverte"
        % (rows["turns_after"], AB.TURNS_TO_ADVANCE))
    assert rows["E_turns0"]["native"][0] != INSTRUMENTS, (
        "le natif propose 1215 a turnsFinished == 0 (%r) -- `GetUseProbability` ne rend donc plus "
        "`Fix64.Zero`, toute la lecture du gate est a refaire" % (rows["E_turns0"]["native"],))
    assert rows["E_turns0"]["engine"]["on"][0] == INSTRUMENTS, (
        "le moteur ne propose PAS 1215 a turnsFinished == 0 (%r) : l'ecart nomme dans la case-doc "
        "n'existe plus, il faut la corriger" % (rows["E_turns0"]["engine"]["on"],))


# --- OFFLINE : le mirror de la formule, sur les regimes que le live n'atteint pas ----------------

def _ctx(enemies, elev=None):
    """Substrat minimal : `calculate_custom_utility` ne lit que `ctx.enemies` et `ctx.elev_by_pos`."""
    return types.SimpleNamespace(
        enemies=[{"id": i, "pos": {"col": c, "row": r}} for i, (c, r) in enumerate(enemies)],
        elev_by_pos=dict(elev or {}))


def _pb():
    return PB.REGISTRY[INSTRUMENTS]


def test_formula_mirrors_the_three_hard_coded_constants():
    """`20000 + (adj.Any() ? 0 : 100) + 20 x |surrounding \\ adj|`, sans aucun poids `BC.Utilities`."""
    pb = _pb()
    assert pb.calculate_custom_utility(_ctx([]), (0, 0), 1, INSTRUMENTS) == 20100.0
    # un ennemi ADJACENT : plus de `+100`, et il n'est pas compte dans le `+20` (il est dans `adj`)
    assert pb.calculate_custom_utility(_ctx([(1, 0)]), (0, 0), 1, INSTRUMENTS) == 20000.0
    # un ennemi a distance 2 : `+100` conserve, `+20` ajoute
    assert pb.calculate_custom_utility(_ctx([(0, 2)]), (0, 0), 1, INSTRUMENTS) == 20120.0
    # lineaire dans le compte des non-adjacents
    assert pb.calculate_custom_utility(_ctx([(0, 2), (2, 1)]), (0, 0), 1, INSTRUMENTS) == 20140.0
    # au-dela du rayon 2 : rien
    assert pb.calculate_custom_utility(_ctx([(0, 4)]), (0, 0), 1, INSTRUMENTS) == 20100.0
    # un adjacent ET un a distance 2 : `+100` perdu, `+20` conserve
    assert pb.calculate_custom_utility(_ctx([(1, 0), (0, 2)]), (0, 0), 1, INSTRUMENTS) == 20020.0


def test_elevation_gate_applies_to_adjacency_only():
    """Le QUIRK, en isolation : un ennemi a distance 1 avec `|dElev| >= 2` est HORS `adj`
    (`IterateAdjacentTiles`) mais DANS `surrounding` (`IterateSurroundingTiles`, disque pur).

    Il vaut donc `+100 + 20`, la ou le meme ennemi a elevation EGALE vaut `0 + 0`."""
    pb = _pb()
    flat = {(0, 0): 3, (1, 0): 3}
    assert pb.calculate_custom_utility(_ctx([(1, 0)], flat), (0, 0), 1, INSTRUMENTS) == 20000.0
    steep = {(0, 0): 2, (1, 0): 4}
    assert pb.calculate_custom_utility(_ctx([(1, 0)], steep), (0, 0), 1, INSTRUMENTS) == 20120.0, (
        "un ennemi a distance 1 et |dElev| = 2 doit rester HORS `GetAdjacentEnemies` et DANS "
        "`GetSurroundingEnemies` -- s'il compte comme adjacent, la porte d'elevation a fuite dans "
        "le second slot")
    edge = {(0, 0): 2, (1, 0): 3}                      # |dElev| = 1 < 2 -> adjacent
    assert pb.calculate_custom_utility(_ctx([(1, 0)], edge), (0, 0), 1, INSTRUMENTS) == 20000.0


def test_registry_wiring():
    """L'ability est dans les DEUX registres attendus, et son masque EFFECTIF est lu."""
    from engine.playbook import nonattack as NA
    from engine.runner.abilities.targeting import targeting_options_for
    assert INSTRUMENTS in NA.NONATTACK_PLAYBOOKS
    opts = targeting_options_for(INSTRUMENTS)
    assert opts is not None and opts.rules == 0x8004, (
        "masque = %r, attendu 0x8004 (static-copy du preset <TargetingOptions statics>+0x280)"
        % (opts.rules if opts else None,))
    assert opts.can_target_caster and opts.self_cast and not opts.is_tile_targeting
