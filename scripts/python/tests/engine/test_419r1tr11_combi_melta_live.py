"""#419-r1 tranche 11 -- le terme `SpecialIssueCombiMelta_LikesRange3` (+25) du `pairUtility`,
confronte au NATIF sur son porteur REEL, **et desormais dans la CONFIGURATION REELLE DU JEU**.

`IdunBattle.AI.Playbook.Loki.SpecialIssueCombiMeltaPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
verse le poids quand `IBattleQuery.<slot 0x6c = GetDistance>(case.Target, case.CasterPosition.MainTile)`
vaut EXACTEMENT 3, et ne fait AUCUN yield sinon. Il entre dans la face ATTACK du dispatcher
`TriggeredAbilitiesUtility(2)`, donc DANS le terme de paire -- directement confrontable a l'oracle
natif `pairUtility`.

## LE BRAS `neutered` A DISPARU (#419-r1-tr11-r3), ET C'EST LE PORT QUI L'A TUE
Ce fichier montait DEUX bras. Le second (`neutered`) forcait a 0, dans le seed BC, les variables de
degat de l'ability, pour que la face COMBAT non portee cesse de perturber la prediction -- un patch
INVISIBLE DU PORT (motif `#366-r1-bcpatch-invisible`), licite tant que le port ne modelisait pas ces
variables. Il declarait lui-meme sa condition de validite, et un garde OFFLINE derive du registre la
tenait : *« des que la face COMBAT entre au registre, le meme geste devient une DESYNCHRONISATION »*.

La face COMBAT est portee (effets **1563** `SpecialIssueCombiMelta_AdditionalHits` a `d == 2` et
**1564** `_ExtraDmg` a `d == 1`, cf. `entities/effects/loki/hits.py` et `.../extra_damage.py`). Le
garde a donc fait ce pour quoi il etait ecrit, et la reponse est celle qu'il prescrivait : **retomber
sur le seul bras `raw`** -- qui n'a plus besoin d'etre borne a la distance 3, puisque le port colle
maintenant au natif aux TROIS distances. Les trois entrees `SpecialIssueCombiMelta` de
`probe_366_r1_bcpatch_port_blindspot._EXCEPTIONS` sont retirees dans le meme commit.

CE QUE CE FICHIER GARDE :

  1. **CONFORMITE, aux TROIS distances, SANS AUCUN PATCH** -- l'utilite de paire du port egale celle
     du natif, tuile par tuile et cible par cible, a 1e-4 pres, sur toutes les lignes SAUF le regime
     residuel du (5).
  2. **DISCRIMINANCE** -- le meme moteur, playbook 1545 RETIRE du registre, DOIT diverger du natif
     d'EXACTEMENT le poids BC sur les tuiles a distance 3, et de RIEN aux distances 1 et 2. Sans
     cette seconde assertion, un port qui ignore le terme passerait.
  3. **LA CIBLE LUE EST `case.Target`** -- depuis une meme tuile, les DEUX cibles (placees
     adjacentes) sont a des distances differentes, et une seule recoit le poids.
  4. **LA FACE COMBAT EST AU REGISTRE** -- garde derive, pendant EXACT de l'ancien garde de
     condition de validite : si elle en sortait, ce fichier redeviendrait un montage a deux bras.
  5. **LE REGIME RESIDUEL EST EXACTEMENT CELUI QU'ON DIT** (`#419-r1-tr11-r5`) -- les seules lignes
     qui divergent encore sont a **distance 2**, l'ecart y est **inferieur a 1 point**, et il en
     existe AU MOINS UNE. Les trois conditions sont gardees : la derniere fait rougir le jour ou
     l'etage DISPLAY du canal #179 sera porte, pour qu'on RESSERRE ce garde au lieu de le laisser
     tolerer un ecart devenu impossible.
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
from engine.entities.effect_type import EffectType


EPS = P.EPS

# Les DEUX effets de la face COMBAT de 1545 (`SpecialIssueCombiMelta_InitAbility$$CreateBehaviour`
# = `AddEffect(0x61b) & AddEffect(0x61c)`). ⚠ Ces ids vivent dans un espace de numerotation
# DIFFERENT de l'ability 1545 : ils sont RE-DERIVES de l'enum du port (mirror 1:1 du natif), jamais
# recopies d'une fiche.
_COMBAT_EFFECTS = (int(EffectType.SpecialIssueCombiMelta_AdditionalHits),      # 1563
                   int(EffectType.SpecialIssueCombiMelta_ExtraDmg))            # 1564

# Borne du regime residuel `#419-r1-tr11-r5` (cf. (5) de l'en-tete). MESUREE, pas choisie : sur ce
# montage l'ecart residuel vaut 0.960412 sur 4 lignes `necroWarden` a d = 2, contre un ecart de
# **8.35 a 78.01 sur 15 lignes** avant le port de la face COMBAT (contre-epreuve
# `probe_419r1tr11_combi_melta.py --sans-face-combat`, meme runner, meme geometrie).
_RESIDUAL_MAX = 1.0
_RESIDUAL_DIST = 2


def _arm(build_runner, live_session, rpc, writer):
    """Monte le bras : seed BC ecrit par `writer`, runner, puis le montage du probe."""
    P.LOGS.mkdir(parents=True, exist_ok=True)
    bc = P.LOGS / ("tr11-seedbc-%s.json" % uuid.uuid4().hex[:8])
    path = writer(bc)
    rid = build_runner(seed=P.SEED, extra=["--seed-bc", str(path), *P.BUILD_ARGS])["rid"]
    try:
        return P.build_case(live_session, rpc, rid)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def raw(build_runner, live_session, rpc):
    """Le SEUL bras : aucun patch de BC, la configuration reelle du jeu."""
    return _arm(build_runner, live_session, rpc, P.write_raw_seed_bc)


@pytest.fixture(scope="module")
def raw_rows(raw, rpc):
    return P.measure(rpc, raw)


def _is_residual(r) -> bool:
    """La ligne appartient-elle au regime residuel `#419-r1-tr11-r5` ? (cf. (5) de l'en-tete)"""
    return (r["dist"] == _RESIDUAL_DIST
            and EPS <= abs(r["native"] - r["port"]) < _RESIDUAL_MAX)


def test_combat_face_is_registered():
    """(4) OFFLINE -- la face COMBAT de 1545 EST au registre.

    Pendant EXACT de l'ancien `test_neutered_arm_condition_of_validity`, dans l'autre sens : ce
    fichier ne monte plus qu'un bras PARCE QUE le port modelise 1563/1564. Si une des deux entrees
    disparaissait, les mesures ci-dessous redeviendraient fausses aux distances 1 et 2 (elles y
    divergeaient de 8.35 a 78.01 points) et il faudrait remonter le bras `neutered`.

    Le critere est DERIVE du registre, jamais saisi."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    missing = [EffectType(e).name for e in _COMBAT_EFFECTS
               if EffectType(e).name not in EFFECT_CLASSES]
    assert not missing, (
        "la face COMBAT de SpecialIssueCombiMelta n'est plus au registre `EFFECT_CLASSES` (%s "
        "manquant) : les assertions de ce fichier confrontent un port qui ignore les effets "
        "1563/1564 a un natif qui les applique. A refaire : re-inscrire les deux effets, ou "
        "remonter le bras `neutered` de ce montage (variables de degat de 1545 forcees a 0 dans le "
        "seed BC) AVEC ses trois entrees dans "
        "`probe_366_r1_bcpatch_port_blindspot._EXCEPTIONS`." % ", ".join(missing))


def test_pair_utility_matches_native_on_all_distances(raw_rows):
    """(1) CONFORMITE : port == natif sur chaque (tuile, cible), aux trois distances, SANS PATCH.

    Seules les lignes du regime residuel (5) sont exemptees, et elles le sont par un predicat
    ETROIT (distance 2 ET ecart < 1 point), pas par une tolerance globale."""
    assert raw_rows, "aucune mesure produite -- le montage n'a rien confronte"
    seen = {r["dist"] for r in raw_rows}
    assert {1, 2, 3} <= seen, ("les trois distances ne sont pas mesurees (vues : %s) -- le gate "
                               "`== 3` ne serait pas pris dans les deux sens" % sorted(seen))
    for r in raw_rows:
        if _is_residual(r):
            continue
        assert abs(r["native"] - r["port"]) < EPS, (
            "pairUtility != natif sur %s (d=%d) depuis %s : natif=%r port=%r ecart=%r"
            % (r["target"], r["dist"], r["tile"], r["native"], r["port"],
               r["port"] - r["native"]))


def test_residual_regime_is_exactly_what_we_claim(raw_rows):
    """(5) `#419-r1-tr11-r5` -- le regime residuel, garde dans les TROIS sens.

    Ce qui reste : sur ce montage, 4 lignes `necroWarden` a d = 2 ou le port SOUS-estime de
    ~0.96 point. CAUSE LOCALISEE (et hors de cette tranche) : le bi-canal ROLL/DISPLAY du canal
    #179. `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(this, entities, useDisplay)` pose
    `min = max = <noeud DISPLAY>.Calculate()` quand `useDisplay` -- une cellule DEGENEREE que le
    pipeline de prediction etale ensuite -- alors que le port publie `predefined = [min, max]` pour
    tout descripteur a forme PREDEFINED. Le TOTAL ne bouge pas (la moyenne est la meme), seule la
    LARGEUR de la plage change, donc l'ecart n'apparait que sur une cible ou un terme NON LINEAIRE
    de l'utilite (KillUnit / OverkillUnit) est sensible aux bornes -- ce que `necroWarden` est et
    `astraBullgryn` n'est pas. L'etage est PARTAGE par tous les descripteurs #179 a forme
    PREDEFINED (SquigHound, CordClaw, SorcerousFacade, FearOfTheUnseen, FleshmetalGuns, 1563) : le
    corriger ici changerait le comportement de six autres effets.

    Les trois assertions, et la 3e est la plus importante : elle fait ROUGIR ce fichier le jour ou
    l'etage sera porte, pour qu'on RESSERRE le garde au lieu de tolerer un ecart devenu impossible."""
    off = [r for r in raw_rows if abs(r["native"] - r["port"]) >= EPS]
    assert all(r["dist"] == _RESIDUAL_DIST for r in off), (
        "des lignes divergent HORS du regime residuel (distance %d) : %r -- le port a une seconde "
        "cause d'ecart, non documentee"
        % (_RESIDUAL_DIST,
           [(r["target"], r["dist"], r["tile"], r["port"] - r["native"])
            for r in off if r["dist"] != _RESIDUAL_DIST]))
    assert all(abs(r["native"] - r["port"]) < _RESIDUAL_MAX for r in off), (
        "l'ecart residuel depasse %r point(s) : %r -- ce n'est plus le bi-canal ROLL/DISPLAY, "
        "c'est autre chose"
        % (_RESIDUAL_MAX, [(r["target"], r["tile"], r["port"] - r["native"]) for r in off]))
    assert off, (
        "AUCUNE ligne ne diverge : le regime residuel `#419-r1-tr11-r5` (bi-canal ROLL/DISPLAY du "
        "canal #179) est FERME. A refaire : retirer `_is_residual` de (1), supprimer ce test, et "
        "fermer le residu au backlog.")


def test_term_is_exactly_the_weight_at_range_3(raw, raw_rows):
    """(2) DISCRIMINANCE : playbook 1545 RETIRE -> le port perd EXACTEMENT le poids BC aux tuiles a
    distance 3, et RIEN aux distances 1 et 2 (hors regime residuel)."""
    weight = raw["weight"]
    assert weight != 0, ("le BC servi porte %s = 0 : le regime ne discrimine rien" % P.WEIGHT_KEY)
    for r in raw_rows:
        if _is_residual(r):
            continue
        expected = weight if r["dist"] == P.RANGE else 0.0
        got = r["native"] - r["port_muted"]
        assert abs(got - expected) < EPS, (
            "sans le playbook %d, l'ecart au natif sur %s (d=%d) depuis %s devrait valoir "
            "exactement %r : natif=%r port_mute=%r ecart=%r"
            % (P.ABILITY, r["target"], r["dist"], r["tile"], expected, r["native"],
               r["port_muted"], got))


def test_target_read_is_the_case_target(raw, raw_rows):
    """(3) La distance est prise sur `case.Target` (`UtilityAttackCase@+0x20`).

    Depuis une MEME tuile, les deux cibles sont a des distances differentes dont l'une vaut 3 :
    une seule des deux lignes porte le poids. Un port qui lirait l'ennemi le plus proche, le
    caster, ou une cible fixe rendrait la meme valeur sur les deux."""
    weight = raw["weight"]
    by_tile: dict = {}
    for r in raw_rows:
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
            if _is_residual(m[vis]):
                continue
            expected = weight if dists[vis] == P.RANGE else 0.0
            assert abs(term - expected) < EPS, (
                "depuis %s, la cible %s est a distance %d : le terme natif devrait valoir %r, "
                "mesure %r (distances = %r, termes = %r)"
                % (tile, vis, dists[vis], expected, term, dists, terms))


def test_every_reading_has_a_regime_where_its_mutant_bites(raw, rpc):
    """(6) Six contre-epreuves, chacune avec sa RECIPROQUE.

    Le critere est le DEPLACEMENT du port par rapport au NATIF : sur ce bras le port NON MUTE colle
    au natif au bit pres partout hors du regime residuel (tests 1 et 5), donc tout ecart >= 1 point
    EST le mutant. Chaque mutant doit (a) s'ecarter d'au moins 1 point dans au moins une distance et
    (b) rester INERTE sur au moins une ligne -- une contre-epreuve qui mord partout ne discrimine
    rien."""
    for name in sorted(P.MUTANTS):
        rows = P.run_mutant(rpc, raw, name)
        per = P.mutant_bite(rows)
        inert = P.mutant_inert_lines(rows)
        assert per and max(per.values()) >= 1.0, (
            "le mutant %r ne DEPLACE rien (%r) : la lecture qu'il casse n'est exercee par aucun "
            "regime du montage -- la garde ne la protege pas" % (name, per))
        assert inert > 0, (
            "le mutant %r s'ecarte du natif sur TOUTES les lignes : la contre-epreuve ne "
            "discrimine aucun regime" % name)
