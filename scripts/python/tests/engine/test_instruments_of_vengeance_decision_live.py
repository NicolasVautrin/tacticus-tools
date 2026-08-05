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

G. **Le gate slot-4 est PORTE (#27-r8), et l'accord qu'il produit est ATTRIBUE.**
   `...InstrumentsOfVengeancePlaybook$$ShouldEvaluate(unit)` = `BasePlaybook.ShouldEvaluate(unit)
   && HasMinimumRemainingTurns(unit, 2)`, et `...$$GetUseProbability` rend `Fix64.Zero` a
   `GetTurnsFinished == 0`. `test_turns_finished_zero_gate_agrees_with_the_native` garde les trois
   crans : substrat MESURE (un canal muet rendrait le gate permissif et l'accord degenere), accord
   natif/moteur, et CONTRE-EPREUVE « gate neutralise » qui redonne 1215.

CE QUI N'EST PAS GARDE, ET POURQUOI (dit plutot que masque) :
* le volet `GetUseProbability(turnsFinished == 1) = Fix64.Half` du meme gate est un TIRAGE (meme
  statut que `...PlasmaGrenadePlaybook$$GetUseProbability`, 1/3) : il reste PERMISSIF cote port,
  et ce fichier ne le mesure pas -- il travaille a `turnsFinished == 0` (bras E) puis dans la
  fenetre DETERMINISTE `turnsFinished >= 2`, ou le gate rend `true` des deux cotes ;
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


def test_turns_finished_zero_gate_agrees_with_the_native(rows):
    """G -- le gate slot-4 `...InstrumentsOfVengeancePlaybook$$ShouldEvaluate` (#27-r8).

    Ce test GARDAIT l'ECART (`test_turns_finished_zero_gate_is_a_named_gap`) : le natif ne
    proposait pas 1215 a `turnsFinished == 0`, le moteur SI. Le gate est PORTE, donc il garde
    desormais l'ACCORD -- et il le fait en TROIS crans, parce qu'un accord seul ne prouverait rien
    ici (les deux cotes pourraient s'accorder pour une raison etrangere au gate) :

      1. le SUBSTRAT est MESURE : `Scene.turns_finished(caster) == 0` ET `should_evaluate_unit`
         rend `False`. Sans ce cran, un canal muet rendrait le gate permissif (convention
         `None -> True`) et l'accord serait celui d'un REGIME DEGENERE ;
      2. natif et moteur s'accordent a ne PAS proposer 1215 ;
      3. CONTRE-EPREUVE : le MEME etat, `should_evaluate_unit` neutralise a `True`, redonne 1215.
         C'est ce cran qui attribue l'accord (2) au gate plutot qu'a autre chose."""
    assert rows["turns_before"] == 0, (
        "turnsFinished(caster) = %r au build, attendu 0" % (rows["turns_before"],))
    assert rows["turns_after"] >= AB.MIN_TURNS_FINISHED, (
        "turnsFinished(caster) = %r apres %d endturn -- la fenetre deterministe n'est pas ouverte"
        % (rows["turns_after"], AB.TURNS_TO_ADVANCE))
    assert rows["E_turns0"]["native"][0] != INSTRUMENTS, (
        "le natif propose 1215 a turnsFinished == 0 (%r) -- `GetUseProbability` ne rend donc plus "
        "`Fix64.Zero`, toute la lecture du gate est a refaire" % (rows["E_turns0"]["native"],))
    e = rows["E_turns0"]["engine"]
    assert e["gate_turns_finished"] == 0 and e["gate"] is False, (
        "substrat NON MESURE : Scene.turns_finished(caster) = %r, gate = %r. Le canal "
        "`combatSnapshot.turnsFinished` -> `Scene.turns_finished_by_id` est muet, donc "
        "`should_evaluate_unit` est permissif par convention et les deux assertions suivantes ne "
        "mesurent RIEN" % (e["gate_turns_finished"], e["gate"]))
    assert e["on"][0] != INSTRUMENTS, (
        "le moteur propose 1215 a turnsFinished == 0 (%r) alors que le natif ne le fait pas : le "
        "gate slot-4 ne mord plus" % (e["on"],))
    assert e["nogate"][0] == INSTRUMENTS, (
        "gate NEUTRALISE, le moteur propose %r au lieu de 1215 : la contre-epreuve ne mord pas, "
        "donc l'accord ci-dessus n'est PAS imputable au gate -- ce test ne garde plus rien"
        % (e["nogate"],))


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


def test_slot4_gate_truth_table_offline():
    """G (offline) -- les CINQ regimes de `should_evaluate_unit`, dont trois que le live n'atteint pas.

    Le bras E ne mesure QU'UN point (`t == 0`). Cette table fige les autres, et surtout les deux
    conventions qui ne se voient dans aucune mesure : `t is None` (canal muet) et `scene is None`
    rendent `True` -- ne PAS gater a l'aveugle. Un repli sur `0` y signifierait `Fix64.Zero`, donc
    un refus que le natif n'a pas prononce.

    Les valeurs viennent de `...InstrumentsOfVengeancePlaybook$$GetUseProbability` :
    `Zero` a `GetTurnsFinished == 0`, `Half` a `== 1`, `One` sinon ; puis
    `BasePlaybook$$ShouldEvaluate` : `p >= 1 -> true`, `p <= 0 -> false`, sinon TIRAGE (rendu
    PERMISSIF ici, faute de PRNG offline -- c'est le regime `t == 1`)."""
    from engine.playbook.scene import Scene

    def scene(tf):
        return Scene(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                     vis_by_id={}, units=[], hp_by_id={}, pos_by_id={}, team_by_id={},
                     eff_state=None, turns_finished_by_id=tf)

    pb = _pb()
    cases = [({7: 0}, False, "t == 0 -> Fix64.Zero -> p <= 0 -> False"),
             ({7: 1}, True, "t == 1 -> Fix64.Half -> TIRAGE, laisse PERMISSIF (declare)"),
             ({7: 2}, True, "t == 2 -> Fix64.One -> p >= 1 -> True"),
             ({7: 9}, True, "t >= 2 -> Fix64.One -> True"),
             ({}, True, "uid hors table -> canal MUET -> permissif, jamais un 0 invente")]
    for tf, expected, why in cases:
        ctx = types.SimpleNamespace(scene=scene(tf), uid=7)
        assert pb.should_evaluate_unit(ctx, INSTRUMENTS) is expected, why
    ctx = types.SimpleNamespace(scene=None, uid=7)
    assert pb.should_evaluate_unit(ctx, INSTRUMENTS) is True, "scene absente -> permissif"


def test_slot4_gate_default_is_the_native_body():
    """G -- le DEFAUT de la route est `True`, et ce n'est pas une convention permissive de notre cote.

    Les deux surcharges de `IdunBattle.AI.Playbook.BasePlaybook$$GetUseProbability` rendent
    `Fix64.op_Implicit(1)`, donc `BasePlaybook$$ShouldEvaluate` prend la branche `p >= 1 -> true` :
    un playbook qui n'override pas le slot 4 est TOUJOURS evalue. Si ce defaut devenait `False`,
    tous les membres de la route non-attaque disparaitraient en silence."""
    from engine.playbook.nonattack import NonAttackComparablePlaybook, NONATTACK_PLAYBOOKS
    ctx = types.SimpleNamespace(scene=None, uid=1)
    assert NonAttackComparablePlaybook.should_evaluate_unit(
        NonAttackComparablePlaybook(), ctx, 0) is True
    others = [aid for aid, pb in NONATTACK_PLAYBOOKS.items()
              if aid != INSTRUMENTS
              and type(pb).should_evaluate_unit is not NonAttackComparablePlaybook.should_evaluate_unit]
    assert others == [], (
        "des membres de la route overrident le slot 4 sans etre gardes ici : %r" % (others,))


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
