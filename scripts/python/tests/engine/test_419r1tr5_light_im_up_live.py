"""#419-r1 tranche 5 -- le playbook `LightImUp` (triggered 1103) confronte au NATIF, etage par etage.

CE QUE CES GARDES PROTEGENT, et pourquoi elles sont a DEUX etages :

  1. **CONFORMITE ISOLEE** -- les TROIS entrees natives du playbook
     (`$$CalculateAttackUtilityForMainTarget`, `$$CalculateAttackUtilityForSecondaryTarget`, et la
     machine a etats `<CalculateAttackUtilityInStepsInternal>d__2$$MoveNext`) sont invoquees UNE PAR
     UNE par `ncPlaybookPredict` (#369/#375) et comparees aux trois methodes homonymes du port. Une
     divergence est ainsi LOCALISEE, pas diluee dans une utilite de paire.
  2. **COUVERTURE DES ETATS** -- la SM a cinq sorties ; le montage doit les atteindre. L'etat joue
     est attribue par les SEULES mesures natives (`inSteps` compare a `Main`, `Sec` et leur
     moyenne), donc sans rien devoir au port. Une ligne dont l'etat n'est pas identifiable de facon
     UNIQUE est un ECHEC, pas un accord.
  3. **CABLAGE** -- le `pairUtility` natif (qui CONTIENT la feuille `TriggeredAbilities(2)`) egale
     le port, et le port PRIVE du playbook 1103 perd EXACTEMENT le terme mesure a l'etage isole. Un
     playbook porte mais non cable rendrait `manque = 0` : c'est le patron que #419 recense.
  4. **ANCRAGE DU DISQUE SECONDAIRE** -- `LightImUpAbility$$GetPossibleSecondaryTargets` ancre son
     `SurroundingEnemies(unit, unitTile, ...)` sur `AbilityEntities.CasterTile`, que le playbook
     alimente avec `case.CasterPosition.MainTile`. La garde le PROUVE en interrogeant le natif
     depuis une tuile candidate dont le disque ne contient pas les memes ennemis, et en exigeant que
     la variante ancree sur la tuile REELLE en DIVERGE (sinon le montage ne discrimine rien, et
     c'est un ECHEC de montage, pas un vert).

Le montage exige tout cela ; s'il ne l'obtient pas, il ECHOUE, il ne skippe pas (#268 -- un skip sur
un regime non atteint est un vert qui ment).

Porteur : `orksWarboss` << Gulgortz >>, HERO au pool (rank 17), qui porte `LightImUp` par son KIT
gameconfig (`passiveAbilities`). ASCII only.
Probe jumeau : `scripts/python/probe_419r1tr5_light_im_up.py` (montage + mesure).
"""
from __future__ import annotations

import pytest

import probe_419r1tr5_light_im_up as P

EPS = P.EPS


@pytest.fixture(scope="module")
def liu_case(live_session, rpc, build_runner):
    """Monte UN runner, place le caster au centre d'une etoile (trois cibles adjacentes a des PV
    calibres + une cible lointaine) et rend tout ce qu'il faut pour mesurer."""
    rid = build_runner(P.SEED, P.BUILD_ARGS)["rid"]
    try:
        return P.build_case(live_session, rpc, rid)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def liu_rows(liu_case, rpc):
    try:
        return P.measure_faces(rpc, liu_case)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_carrier_kit_carries_the_triggered_ability(liu_case):
    """GARDE DE SOURCE : 1103 est bien dans l'`AbilitiesComponent` que le dispatcher itere.

    Sans elle, un playbook peut etre au registre et n'etre JAMAIS appele -- port speculatif.
    (`build_case` leve deja si l'ability manque ; cette assertion NOMME l'invariant.)"""
    assert liu_case["hits"] > 0, "nrOfHits absent du gameconfig : le montage ne calcule rien"


def test_three_native_faces_match_the_port(liu_rows):
    """(1) CONFORMITE ISOLEE : les trois voies natives == les trois methodes du port, cible par
    cible. Les valeurs natives ne sont PAS gelees ici -- elles sont re-mesurees a chaque run."""
    assert liu_rows, "aucune mesure produite -- le montage n'a rien confronte"
    for r in liu_rows:
        for k in ("main", "sec", "steps"):
            n, p = r["n_" + k], r["p_" + k]
            assert abs(n - p) < EPS, (
                f"face {k} sur {r['target']} (hp={r['hp']}, gates={r['gates']}) : "
                f"natif={n!r} port={p!r} ecart={p - n!r}")


def test_state_machine_states_are_covered_and_identified(liu_rows):
    """(2) COUVERTURE : les quatre regimes que ce montage doit atteindre sont atteints, et chacun
    est identifie de facon UNIQUE par les seules mesures natives.

    `etats1-2-gate` (une gate refuse -> 0), `etat3-secondaire` (l'attaque normale tue a coup sur),
    `etat4-principal` (meme normale + passif ne peut pas tuer), `etat5-moyenne` (indetermine)."""
    for r in liu_rows:
        st = r["state"]
        assert st["discriminating"], (
            f"{r['target']} : l'etat natif n'est pas identifiable (candidats egaux "
            f"{st['candidates']!r}, matches {st['matched']!r}) -- la ligne ne prouve rien")
    seen = {r["state"]["state"] for r in liu_rows}
    for want in ("etats1-2-gate", "etat3-secondaire", "etat4-principal", "etat5-moyenne"):
        assert want in seen, (
            f"regime {want} NON ATTEINT par le montage (vus : {sorted(seen)}) -- les PV des cibles "
            f"sont a re-calibrer, cf. l'en-tete de probe_419r1tr5_light_im_up.HP")


def test_non_regular_attack_is_refused_by_both(liu_case, rpc):
    """ETAT 2 : un case qui NOMME une ability non reguliere (`Waaagh`) rend 0 des DEUX cotes, et le
    natif l'atteste par sa gate `isRegularAttack: false`."""
    nr = P.measure_not_regular(rpc, liu_case)
    assert nr["regular_refused"], (
        f"la gate native `isRegularAttack` n'a PAS refuse {nr['ability']} (gates={nr['gates']!r}) : "
        f"le regime de l'etat 2 n'est pas exerce")
    assert abs(nr["native"] - nr["port"]) < EPS, (
        f"etat 2 : natif={nr['native']!r} port={nr['port']!r}")


def test_empty_secondary_set_yields_zero(liu_case):
    """`Count == 0` : le natif rend `Fix64(0)` AVANT tout calcul de montant. Le port doit rendre 0
    par le MEME chemin (ensemble vide), pas par un repli defensif."""
    ns = P.measure_no_secondary(liu_case)
    assert ns["confronted"], ns.get("reason")
    assert ns["targets"] == [], f"le disque n'est pas vide sur {ns['tile']} : {ns['targets']!r}"
    assert ns["utility"] == 0.0, f"ensemble secondaire vide mais utilite {ns['utility']!r}"


def test_secondary_disk_is_anchored_on_the_attack_tile(liu_case, rpc):
    """(4) ANCRAGE : le disque de `GetPossibleSecondaryTargets` suit la TUILE D'ATTAQUE.

    La garde exige d'abord que le montage DISCRIMINE (les deux variantes du port divergent) ; sinon
    la mesure ne conclurait rien et un accord serait fortuit."""
    a = P.measure_anchor(rpc, liu_case)
    assert a["confronted"], a.get("reason")
    assert a["discriminating"], (
        f"les deux ancrages rendent la MEME valeur sur {a['tile']} "
        f"({a['port_anchor_attack_tile']!r}) -- le montage ne discrimine pas, il ne prouve rien")
    assert abs(a["native"] - a["port_anchor_attack_tile"]) < EPS, (
        f"depuis la tuile candidate {a['tile']} (disque {a['targets_there']!r} contre "
        f"{a['targets_here']!r} a la tuile courante) : natif={a['native']!r} "
        f"port(ancre tuile d'attaque)={a['port_anchor_attack_tile']!r}")
    assert abs(a["native"] - a["port_anchor_real_tile"]) >= EPS, (
        f"la variante ancree sur la tuile REELLE coincide aussi avec le natif "
        f"({a['port_anchor_real_tile']!r}) -- l'ancrage n'est pas tranche par ce montage")


def test_pair_term_matches_native_and_is_load_bearing(liu_case, liu_rows, rpc):
    """(3) CABLAGE : `pairUtility` natif == port, et le port PRIVE de 1103 perd EXACTEMENT le terme
    mesure a l'etage isole. C'est la garde qui rougit si le playbook sort du registre OU si la
    feuille `TriggeredAbilities(2)` face ATTACK cesse de le dispatcher."""
    isole = {r["target"]: r["n_steps"] for r in liu_rows}
    rows = P.measure_pair(rpc, liu_case)
    assert rows, "aucune paire mesuree"
    assert any(abs(isole.get(r["target"], 0.0)) > EPS for r in rows), (
        "le terme LightImUp est nul sur TOUTES les cibles -- la garde de cablage ne prouverait rien")
    for r in rows:
        assert abs(r["native"] - r["port"]) < EPS, (
            f"pairUtility sur {r['target']} : natif={r['native']!r} port={r['port']!r}")
        want = isole.get(r["target"])
        assert want is not None and abs(r["missing"] - want) < EPS, (
            f"sans le playbook 1103, l'ecart du port sur {r['target']} devrait valoir EXACTEMENT le "
            f"terme isole {want!r} : manque mesure {r['missing']!r} "
            f"(port={r['port']!r} mute={r['port_muted']!r})")
