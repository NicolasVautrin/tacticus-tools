"""`#419-r1-tr14-r5-r2-r1-r1-r1-r3-r1` -- les confrontations LIVE de la tranche.

CINQ bancs, chacun avec son propre montage, tous joues par le probe jumeau
`scripts/python/probe_419r1tr14r5r2r1r1r1r3r1_gates.py` (qui monte et DISPOSE ses runners) :

  * **etape 2b** -- REACHABILITY par `resolveMethodPtr` : une classe qui override `EvaluateInternal`
    rend son propre `ShouldExecute` inatteignable. C'est ce qui etablit que
    `BloodChalicePlaybook$$ShouldExecute` est du CODE MORT. TEMOIN : `MomentShacklePlaybook`
    (`ShouldExecute` sans `EvaluateInternal`, donc gate VIVANT).
  * **etape 3** -- `1147 HadesAutocannons`, TROIS bras. Le port lisait les ALLIES la ou le natif
    interroge `GetAllEnemiesOf` ; la contre-epreuve rejoue l'ANCIENNE lecture et doit DIVERGER du
    natif sur le bras `enemy` (aucun allie porteur) et coincider sur `both`.
  * **etape 4** -- `1014 ArmoriumCherub`, DEUX bras sur la branche `n < 2` : cible a 1 PV
    (`MightBeKill` -> le gate REFUSE, et le natif ne propose pas malgre une utilite de ~174) et
    cible a PV enormes (le gate ACCEPTE, le natif propose).
  * **etape 5** -- `1010 StormOfFlensingBlades` : le gate est INERTE dans le port faute de
    prediction portee. Le cran est un DECLENCHEUR (il rougit le jour ou la prediction arrive).
  * **etape 6** -- `1095 ReapingScythe` : la bascule `TurnsStarted > 2`, mesuree sur UN runner.
  * **etape 7** -- la clause BOSS du soin : le trait `Boss` REFUTE comme substrat d'`IsBoss`.

⚠ Ce fichier ne re-transcrit AUCUN critere : il joue les etapes et exige `bad == 0`. Les criteres,
leurs temoins et leurs contre-epreuves vivent dans le probe, qui est le seul endroit ou ils peuvent
etre lus a cote de la mesure qu'ils jugent.

ASCII only. Detail : `docs/rl/case-419-r1-tr14-r5-r2-r1-r1-r1-r3-r1-trois-corps-et-quatre-confrontations.md`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r5r2r1r1r1r3r1_gates as P

#: Ce qui doit changer pour que cette garde puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        # LE PROBE : il porte les montages ET les criteres de ce fichier.
        "scripts/python/probe_419r1tr14r5r2r1r1r1r3r1_gates.py",
        # LES GATES confrontes.
        "scripts/python/engine/playbook/should_execute_gates.py",
        "scripts/python/engine/playbook/loki_custom.py",
        "scripts/python/engine/playbook/common.py",
        "scripts/python/engine/playbook/noncomparable/_base.py",
        "scripts/python/engine/playbook/base.py",
        # LE HARNAIS de montage (build, placement, contexte de decision).
        "scripts/python/rl_duel.py",
        "scripts/python/engine/ai/context.py",
        "scripts/python/engine/playbook/scene.py",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "`build: True` est un FAIT ici : les etapes 1 et 2 lisent `data/symbols/<build>/metadata/"
        "interface_slots.tsv` et `frida/methods.tsv`, et l'etape 2b interroge le PROCESSUS "
        "(`resolveMethodPtr`). Un changement de build renumerote les slots d'interface -- c'est "
        "exactement le glissement que l'etape 1 est la pour voir. `toujours: False` : ce fichier "
        "garde SIX foyers nommes, pas le harnais."
    ),
}


@pytest.fixture(scope="module")
def logs(tmp_path_factory):
    return str(tmp_path_factory.mktemp("g419r3r1"))


# --------------------------------------------------------------------------- crans OFFLINE (rapides)

def test_les_cinq_slots_d_interface_de_la_famille():
    """Le SEUL canal qui separe `GetAllEnemiesOf` (0x8e) de son voisin `GetAllFriendsOf` (0x8d) --
    les deux corps natifs ne different que par le sens de la comparaison d'owner."""
    assert P.etape1_slots(verbose=False)["bad"] == 0


def test_reachability_offline_juge_EvaluateInternal():
    """Elle ne juge QUE les presences : l'ABSENCE d'une methode dans `methods.tsv` ne prouve rien
    (dedup IL2CPP des corps triviaux) -- et ce build en porte un exemple, imprime par l'etape."""
    r = P.etape2_reachability(verbose=False)
    assert r["bad"] == 0


# --------------------------------------------------------------------------- crans LIVE

def test_live_reachability_par_resolveMethodPtr():
    """`class_get_methods` REFAIT dans le processus -- la source qui tranche l'absence."""
    r = P.etape2b_reachability_live(verbose=True)
    assert r.get("measured"), "RPC muet : la mesure n'a pas eu lieu"
    assert r["bad"] == 0


def test_live_1147_lit_les_ennemis_et_l_ancienne_lecture_divergeait(logs):
    r = P.etape3_live_1147(logs, verbose=True)
    assert r["rows"], "aucune ligne mesuree -- montage non installe"
    assert r["bad"] == 0


def test_live_1014_le_gate_de_surtuage(logs):
    r = P.etape4_live_1014(logs, verbose=True)
    assert r["rows"], "aucune ligne mesuree -- montage non installe"
    assert r["bad"] == 0


def test_live_1010_le_gate_est_inerte_faute_de_prediction(logs):
    r = P.etape5_live_1010(logs, verbose=True)
    assert r["rows"], "aucune ligne mesuree -- montage non installe"
    assert r["bad"] == 0


def test_live_1095_la_bascule_turns_started(logs):
    r = P.etape6_live_1095(logs, verbose=True)
    assert r["rows"], "aucune ligne mesuree -- montage non installe"
    assert r["bad"] == 0


def test_live_la_clause_boss_et_son_substrat_refute(logs):
    r = P.etape7_live_boss(logs, verbose=True)
    assert r["rows"], "aucune ligne mesuree -- montage non installe"
    assert r["bad"] == 0
