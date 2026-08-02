"""#419-r1 tranche 9 -- le playbook `RapidFire` (triggered 1135) confronte au NATIF.

CE QUE CES GARDES PROTEGENT :

  1. **CONFORMITE** -- sur chaque ligne du montage, `terme_port == terme_natif`, ou
     `terme_natif = pairUtility(hote GREFFE) - pairUtility(hote PRIVE du seul 1135)`. C'est une
     DIFFERENCE DE DEUX MESURES NATIVES : les residus hors-perimetre de la paire (caster, cible)
     n'y entrent pas, et la tolerance de chaque ligne est DERIVEE du residu de prediction MESURE
     sur cette paire (`P.term_tolerance`), jamais posee au confort.
  2. **CABLAGE** -- le port PRIVE du playbook 1135 perd EXACTEMENT ce terme. Un playbook porte mais
     non dispatche rendrait `terme_port == 0` partout : c'est le patron que #419 recense.
  3. **LES QUATRE GATES ET LES DEUX AGREGATS** -- chaque lecture non devinable du corps natif a un
     regime ou son mutant MORD (`P.MUST_BITE`). Un mutant qui ne mord pas dans son regime est un
     ECHEC : la lecture n'y serait pas confrontee.
  4. **LE LITTERAL `0x45`** -- le regime `foreign` monte un caster dont l'attaque normale est
     CONCRETE (1128) : le natif y rend un terme NUL alors que les cibles sont a portee, parce que
     `AttackQuery$$GetValidTargets` ne trouve pas `0x45` a son `ActiveAbilityComponent`. C'est la
     garde qui rougirait si le port revenait a `case.AbilityType`.

Le montage exige tout cela ; s'il ne l'obtient pas il ECHOUE, il ne skippe pas (#268 -- un skip sur
un regime non atteint est un vert qui ment).

Porteurs reels : 3 npc `ultra*Intercessor*` + le SUMMON `ultraSmnHeavyIntercessor` -- aucun HERO,
d'ou la GREFFE (`catalog_inject.graft_passive_ability`), legitime parce que le corps natif ne lit
du caster que sa position, son flag `Moved` et ses cibles d'attaque normale. ASCII only.
Probe jumeau : `scripts/python/probe_419r1tr9_rapid_fire.py` (montage + mesure).
"""
from __future__ import annotations

import os

import pytest

import probe_419r1tr9_rapid_fire as P

EPS = P.EPS
REGIMES = ("home", "kill", "remove", "foreign")


@pytest.fixture(scope="module")
def rf_results(live_session, rpc, build_runner, host):
    """Joue les QUATRE regimes, un a la fois, et LIBERE chaque runner avant de passer au suivant :
    la discipline `runner.md` interdit d'en tenir huit jusqu'au teardown du module."""
    logs = os.path.abspath(os.path.join(os.path.dirname(P.__file__), "..", "..", "logs"))
    os.makedirs(logs, exist_ok=True)
    out = {}

    def _dispose(rid):
        host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)

    for regime in REGIMES:
        rid = build_runner(P.SEED, P.build_args(regime, logs))["rid"]
        try:
            out[regime] = P.run_regime(
                live_session, rpc, rid, regime,
                lambda r=regime: build_runner(P.SEED, P.build_args(r, logs, "base"))["rid"],
                _dispose)
        except P.MontageError as e:
            pytest.fail(f"[{regime}] {e}", pytrace=False)
        finally:
            _dispose(rid)
    return out


def test_montage_installs_every_regime(rf_results):
    """GARDE DE MONTAGE : les quatre regimes sont montes, le passif 1135 est bien dans
    l'`AbilitiesComponent` (sinon `build_case` aurait leve), et chacun porte des lignes."""
    assert set(rf_results) == set(REGIMES)
    for regime, res in rf_results.items():
        assert res["rows"], f"[{regime}] aucune ligne mesuree -- rien n'a ete confronte"


def test_term_matches_native_on_every_line(rf_results):
    """(1) CONFORMITE : `terme_port == terme_natif` sur chaque ligne, a la tolerance DERIVEE du
    residu de prediction de la paire."""
    for regime, res in rf_results.items():
        st = res["case"]
        for r in res["rows"]:
            tol = P.term_tolerance(st, r)
            assert abs(r["term_port"] - r["term_native"]) < tol, (
                f"[{regime}][{r['tag']}] tuile {r['tile']} cible u{r['target']} : "
                f"terme natif={r['term_native']!r} port={r['term_port']!r} "
                f"(nat={r['native']!r} base={r['native_base']!r} mute={r['port_muted']!r}, "
                f"residu de degat={st['dmg'].get(r['target'])!r}, tolerance={tol!r})")


def test_term_is_load_bearing_and_wired(rf_results):
    """(2) CABLAGE : le terme est NON NUL la ou le corps natif doit le produire (`HOME` des regimes
    `home` et `kill`), et le port PRIVE de 1135 le perd EXACTEMENT."""
    for regime in ("home", "kill"):
        rows = [r for r in rf_results[regime]["rows"] if r["tag"] == "HOME"]
        assert rows, f"[{regime}] aucune ligne HOME"
        assert all(r["term_port"] > EPS for r in rows), (
            f"[{regime}] le terme RapidFire est nul sur au moins une ligne HOME "
            f"({[(r['target'], r['term_port']) for r in rows]}) -- la garde de cablage ne "
            f"prouverait rien")
        for r in rows:
            assert abs((r["port"] - r["port_muted"]) - r["term_port"]) < EPS


def test_gates_yield_zero_where_the_native_does(rf_results):
    """(3a) Les trois regimes a terme NUL le sont des DEUX cotes, et pour la raison NOMMEE :
    `MOVE` = tuile != tuile courante (gate 1) ; `MOVED` = `UnitFlag.Moved` (gate 3, la tuile
    courante EST la tuile evaluee) ; `remove`/`foreign` = ensemble de cibles VIDE."""
    zero = [("home", "MOVE"), ("home", "MOVED"), ("kill", "MOVE"), ("kill", "MOVED"),
            ("remove", "HOME"), ("foreign", "HOME")]
    for regime, tag in zero:
        rows = [r for r in rf_results[regime]["rows"] if r["tag"] == tag]
        assert rows, f"[{regime}][{tag}] ligne absente du montage"
        for r in rows:
            assert abs(r["term_native"]) < EPS, (
                f"[{regime}][{tag}] le NATIF porte un terme {r['term_native']!r} la ou il devrait "
                f"etre nul -- la lecture du corps est fausse")
            assert abs(r["term_port"]) < EPS, (
                f"[{regime}][{tag}] le port porte un terme {r['term_port']!r}")


def test_move_and_moved_pin_the_two_gates(rf_results):
    """(3b) Les gates 1 et 3 sont EPINGLEES sans circularite : sur la MEME tuile, le natif rend la
    MEME valeur avant et apres que le caster s'y soit REELLEMENT deplace. Si seule la gate 1
    existait, la seconde mesure porterait le terme (la tuile est devenue la tuile courante) ; si
    seule la gate 3 existait, la premiere le porterait."""
    for regime in ("home", "kill"):
        rows = {r["tag"]: r for r in rf_results[regime]["rows"]
                if r["tag"] in ("MOVE", "MOVED") and r["target"] == rf_results[regime]["case"]["ref_tgt"]}
        assert {"MOVE", "MOVED"} <= set(rows), f"[{regime}] MOVE/MOVED manquants"
        assert rows["MOVE"]["tile"] == rows["MOVED"]["tile"]
        assert abs(rows["MOVE"]["native"] - rows["MOVED"]["native"]) < EPS, (
            f"[{regime}] le natif change entre MOVE ({rows['MOVE']['native']!r}) et MOVED "
            f"({rows['MOVED']['native']!r}) : l'etat a bouge, les deux gates ne sont pas epinglees")


def test_foreign_regime_pins_the_literal_normal_attack(rf_results):
    """(4) Le regime `foreign` est REELLEMENT installe : l'attaque normale du caster n'est pas
    `0x45`, `GetValidTargets(caster, pos, 0x45)` est VIDE, et les memes cibles SONT a portee de son
    attaque normale concrete -- sans quoi le terme nul ne prouverait rien."""
    st = rf_results["foreign"]["case"]
    assert st["ab"] != P.NORMAL_69
    assert st["here69"] == []
    assert len(st["here_ab"]) >= 2, (
        f"seulement {len(st['here_ab'])} cible(s) a portee de l'attaque normale {st['ab']} : "
        f"le terme nul serait explique par la geometrie, pas par le litteral")


def test_every_reading_has_a_regime_where_its_mutant_bites(rf_results):
    """(3) CONTRE-EPREUVES : chaque mutant MORD dans le(s) regime(s) ou sa lecture est exercee.
    Critere = DEPLACEMENT par rapport au port NON MUTE, jamais l'ecart au natif."""
    covered = set()
    for regime, res in rf_results.items():
        for m in P.MUST_BITE[regime]:
            rowsm = res["mutants"].get(m)
            assert rowsm, f"[{regime}] mutant {m} non joue"
            worst = max(abs(x["port"] - x["port_ref"]) for x in rowsm)
            assert worst > EPS, (
                f"[{regime}] le mutant {m} NE MORD PAS (deplacement max {worst!r}) : la lecture "
                f"qu'il attaque n'est pas confrontee par ce regime")
            covered.add(m)
    assert covered == set(P.MUTANTS), (
        f"mutants sans regime mordant : {sorted(set(P.MUTANTS) - covered)}")
