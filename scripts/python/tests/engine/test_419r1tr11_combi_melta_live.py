"""#419-r1 tranche 11 -- le terme `SpecialIssueCombiMelta_LikesRange3` (+25) du `pairUtility`,
confronte au NATIF sur son porteur REEL.

`IdunBattle.AI.Playbook.Loki.SpecialIssueCombiMeltaPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
verse le poids quand `IBattleQuery.<slot 0x6c = GetDistance>(case.Target, case.CasterPosition.MainTile)`
vaut EXACTEMENT 3, et ne fait AUCUN yield sinon. Il entre dans la face ATTACK du dispatcher
`TriggeredAbilitiesUtility(2)`, donc DANS le terme de paire -- directement confrontable a l'oracle
natif `pairUtility`.

CE QUE CE FICHIER GARDE :

  1. **CONFORMITE, aux TROIS distances** (`neutered`) -- l'utilite de paire du port egale celle du
     natif, tuile par tuile et cible par cible, a 1e-4 pres.
  2. **DISCRIMINANCE** -- le meme moteur, playbook 1545 RETIRE du registre, DOIT diverger du natif
     d'EXACTEMENT le poids BC sur les tuiles a distance 3, et de RIEN aux distances 1 et 2. Sans
     cette seconde assertion, un port qui ignore le terme passerait.
  3. **LA CIBLE LUE EST `case.Target`** -- depuis une meme tuile, les DEUX cibles (placees
     adjacentes) sont a des distances differentes, et une seule recoit le poids.
  4. **LA CONFIGURATION REELLE DU JEU** (`raw`, sans aucun patch de BC) -- le terme est confronte
     tel quel a la distance 3, la seule ou la face COMBAT de la MEME ability (effets 1563/1564, non
     portes) ne perturbe pas la prediction.
  5. **LE PATCH DU BRAS `neutered` A MORDU** -- prouve par une mesure NATIVE des deux bras : les
     `pairUtility` coincident a la distance 3 et DIFFERENT aux distances 1 et 2. Un patch avale en
     silence (#375) rendrait deux bras identiques -> rouge.
  6. **CHAQUE LECTURE A UN REGIME OU SON MUTANT MORD** -- six contre-epreuves, chacune avec sa
     RECIPROQUE (au moins une ligne ou elle ne mord pas).

Le montage EXIGE l'injection catalogue du porteur, l'ability 1545 a son `AbilitiesComponent`, les
trois distances et un poids BC non nul ; s'il ne les obtient pas il ECHOUE, il ne skippe pas
(#268 -- un skip sur un regime non atteint est un vert qui ment).

Porteur : `darkaSternguard` << Ramus >>, HERO hors catalogue (`catalog_inject --missing`).
Cibles : `astraBullgryn` et `necroWarden`, placees ADJACENTES.
ASCII only. Probe jumeau : `scripts/python/probe_419r1tr11_combi_melta.py` (montage + mesure).
"""
from __future__ import annotations

import uuid

import pytest

import probe_419r1tr11_combi_melta as P


EPS = P.EPS


def _arm(build_runner, live_session, rpc, writer):
    """Monte UN bras : seed BC ecrit par `writer`, runner, puis le montage du probe."""
    P.LOGS.mkdir(parents=True, exist_ok=True)
    bc = P.LOGS / ("tr11-seedbc-%s.json" % uuid.uuid4().hex[:8])
    path = writer(bc)
    rid = build_runner(seed=P.SEED, extra=["--seed-bc", str(path), *P.BUILD_ARGS])["rid"]
    try:
        return P.build_case(live_session, rpc, rid)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def neutered(build_runner, live_session, rpc):
    """Bras discriminant : variables de degat de 1545 forcees a 0 -> la face COMBAT de la meme
    ability cesse de perturber la PREDICTION, et le port est confrontable aux TROIS distances."""
    return _arm(build_runner, live_session, rpc, P.write_neutered_seed_bc)


@pytest.fixture(scope="module")
def raw(build_runner, live_session, rpc):
    """Bras SANS AUCUN PATCH : la configuration reelle du jeu."""
    return _arm(build_runner, live_session, rpc, P.write_raw_seed_bc)


@pytest.fixture(scope="module")
def neutered_rows(neutered, rpc):
    return P.measure(rpc, neutered)


@pytest.fixture(scope="module")
def raw_rows(raw, rpc):
    return P.measure(rpc, raw)


def test_pair_utility_matches_native_on_all_distances(neutered_rows):
    """(1) CONFORMITE : port == natif sur chaque (tuile, cible), aux trois distances."""
    assert neutered_rows, "aucune mesure produite -- le montage n'a rien confronte"
    seen = {r["dist"] for r in neutered_rows}
    assert {1, 2, 3} <= seen, ("les trois distances ne sont pas mesurees (vues : %s) -- le gate "
                               "`== 3` ne serait pas pris dans les deux sens" % sorted(seen))
    for r in neutered_rows:
        assert abs(r["native"] - r["port"]) < EPS, (
            "pairUtility != natif sur %s (d=%d) depuis %s : natif=%r port=%r ecart=%r"
            % (r["target"], r["dist"], r["tile"], r["native"], r["port"],
               r["port"] - r["native"]))


def test_term_is_exactly_the_weight_at_range_3(neutered, neutered_rows):
    """(2) DISCRIMINANCE : playbook 1545 RETIRE -> le port perd EXACTEMENT le poids BC aux tuiles a
    distance 3, et RIEN aux distances 1 et 2."""
    weight = neutered["weight"]
    assert weight != 0, ("le BC servi porte %s = 0 : le regime ne discrimine rien" % P.WEIGHT_KEY)
    for r in neutered_rows:
        expected = weight if r["dist"] == P.RANGE else 0.0
        got = r["native"] - r["port_muted"]
        assert abs(got - expected) < EPS, (
            "sans le playbook %d, l'ecart au natif sur %s (d=%d) depuis %s devrait valoir "
            "exactement %r : natif=%r port_mute=%r ecart=%r"
            % (P.ABILITY, r["target"], r["dist"], r["tile"], expected, r["native"],
               r["port_muted"], got))


def test_target_read_is_the_case_target(neutered, neutered_rows):
    """(3) La distance est prise sur `case.Target` (`UtilityAttackCase@+0x20`).

    Depuis une MEME tuile, les deux cibles sont a des distances differentes dont l'une vaut 3 :
    une seule des deux lignes porte le poids. Un port qui lirait l'ennemi le plus proche, le
    caster, ou une cible fixe rendrait la meme valeur sur les deux."""
    weight = neutered["weight"]
    by_tile: dict = {}
    for r in neutered_rows:
        by_tile.setdefault(r["tile"], {})[r["target"]] = r
    split = [(t, m) for t, m in by_tile.items()
             if len(m) == 2 and len({x["dist"] for x in m.values()}) == 2
             and P.RANGE in {x["dist"] for x in m.values()}]
    assert split, ("aucune tuile d'ou les deux cibles soient a des distances DIFFERENTES dont "
                   "l'une vaut 3 -- la lecture de `case.Target` n'est pas exercee")
    for tile, m in split:
        terms = {vis: x["native"] - x["port_muted"] for vis, x in m.items()}
        dists = {vis: x["dist"] for vis, x in m.items()}
        for vis, term in terms.items():
            expected = weight if dists[vis] == P.RANGE else 0.0
            assert abs(term - expected) < EPS, (
                "depuis %s, la cible %s est a distance %d : le terme natif devrait valoir %r, "
                "mesure %r (distances = %r, termes = %r)"
                % (tile, vis, dists[vis], expected, term, dists, terms))


def test_raw_arm_agrees_at_range_3(raw, raw_rows):
    """(4) CONFIGURATION REELLE DU JEU -- aucun patch de BC dans ce bras.

    A la distance 3, la face COMBAT de la MEME ability (`SpecialIssueCombiMelta_AdditionalHits`
    1563 et `_ExtraDmg` 1564, non portes) ne modifie PAS la prediction : c'est la seule distance ou
    le port est confrontable sans neutralisation, et il doit y coller au natif."""
    weight = raw["weight"]
    at3 = [r for r in raw_rows if r["dist"] == P.RANGE]
    assert at3, "le bras `raw` ne mesure aucune tuile a distance 3"
    for r in at3:
        assert abs(r["native"] - r["port"]) < EPS, (
            "bras RAW : pairUtility != natif sur %s (d=3) depuis %s : natif=%r port=%r"
            % (r["target"], r["tile"], r["native"], r["port"]))
        assert abs((r["native"] - r["port_muted"]) - weight) < EPS, (
            "bras RAW : sans le playbook %d l'ecart au natif sur %s depuis %s devrait valoir %r, "
            "mesure %r" % (P.ABILITY, r["target"], r["tile"], weight,
                           r["native"] - r["port_muted"]))


def test_combat_face_perturbs_only_below_range_3(raw_rows, neutered_rows):
    """(5) MESURE NATIVE des deux bras -- et c'est CE test qui atteste que le patch a MORDU.

    Le patch du bras `neutered` vit dans `BC.Abilities` ; s'il etait ecrase au chargement (#375,
    `refresh_ability_configs`) les deux bras rendraient le MEME `pairUtility` partout et cette
    garde rougirait. Le fait natif qu'elle publie au passage : les effets 1563/1564 modifient la
    prediction aux distances 1 et 2, et PAS a la distance 3."""
    raw_by = {(r["tile"], r["target"]): r for r in raw_rows}
    neu_by = {(r["tile"], r["target"]): r for r in neutered_rows}
    common = sorted(set(raw_by) & set(neu_by))
    assert common, ("les deux bras ne partagent aucune paire (tuile, cible) -- la geometrie du "
                    "montage n'est pas reproductible d'un bras a l'autre")
    diff_below = 0
    for key in common:
        a, b = raw_by[key], neu_by[key]
        assert a["dist"] == b["dist"], "distance incoherente entre les bras sur %r" % (key,)
        if a["dist"] == P.RANGE:
            assert abs(a["native"] - b["native"]) < EPS, (
                "a distance 3 les deux bras devraient rendre le MEME natif sur %r : raw=%r "
                "neutered=%r -- la face COMBAT n'y mord pas, donc le patch ne doit rien y changer"
                % (key, a["native"], b["native"]))
        elif a["native"] - b["native"] > EPS:
            diff_below += 1
    assert diff_below, (
        "AUCUNE paire a distance 1 ou 2 ne differe entre les bras : le patch de neutralisation "
        "(BC.Abilities/SpecialIssueCombiMelta) n'a PAS mordu -- sidecar d'epinglage absent ou "
        "ecrase (#375). Les mesures du bras `neutered` ne prouveraient alors rien de plus que "
        "celles du bras `raw`.")


def test_every_reading_has_a_regime_where_its_mutant_bites(neutered, rpc):
    """(6) Six contre-epreuves, chacune avec sa RECIPROQUE.

    Le critere est le DEPLACEMENT du port par rapport au NATIF : sur ce bras le port NON MUTE colle
    au natif au bit pres (test 1), donc tout ecart EST le mutant. Chaque mutant doit (a) s'ecarter
    d'au moins 1 point dans au moins une distance et (b) rester INERTE sur au moins une ligne --
    une contre-epreuve qui mord partout ne discrimine rien."""
    for name in sorted(P.MUTANTS):
        rows = P.run_mutant(rpc, neutered, name)
        per = P.mutant_bite(rows)
        inert = P.mutant_inert_lines(rows)
        assert per and max(per.values()) >= 1.0, (
            "le mutant %r ne DEPLACE rien (%r) : la lecture qu'il casse n'est exercee par aucun "
            "regime du montage -- la garde ne la protege pas" % (name, per))
        assert inert > 0, (
            "le mutant %r s'ecarte du natif sur TOUTES les lignes : la contre-epreuve ne "
            "discrimine aucun regime" % name)
