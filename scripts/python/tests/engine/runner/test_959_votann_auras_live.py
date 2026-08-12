"""#959 LIVE -- `GrimEfficiency` (1490, `votanUthar`) et `PredictiveGuidance` (1525,
`votanMemnyr`) confrontes au NATIF sur un runner monte.

Les deux porteurs sont HORS POOL : le montage les injecte au catalogue (`catalog_inject`,
case-92 §6). UN SEUL runner sert les deux passifs -- leurs zones sont disjointes par construction
(cf. la geometrie CALCULEE en tete de `probe_959_grim_efficiency_predictive_guidance.py`).

L'oracle n'est JAMAIS le port : c'est `statModSources` (etage 3) et
`decisionView.attackPlans[].evals[].ranked[].dmg{Min,Max}` (etage 4), tous deux natifs.

RE + mesures : `docs/rl/case-959-grim-efficiency-predictive-guidance.md`.
"""
from __future__ import annotations

#: Perimetre : le probe qui porte les cinq etages, le module des classes, les DEUX registres, et
#: les TROIS canaux consommateurs -- l'aura stat-mod projetee (etage 3) et les deux faces du canal
#: aura-DEFENSE (etage 4, COMBAT + PREDICTION), dont le ctx a ete elargi par cette tranche.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/probe_959_grim_efficiency_predictive_guidance.py",
        "scripts/python/engine/entities/effects/loki/votann.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/aura_selectors.py",
        "scripts/python/engine/runner/operations/aura_stat_mods.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/rl_duel.py",
        # La fermeture d'imports de `rl_duel` : le montage passe par lui (build + dispose).
        "scripts/python/board.py",
        "scripts/python/oracle.py",
        "scripts/python/rl_probe_step.py",
        "scripts/python/runner_state.py",
        "data/boards/global/MC1_67.json",
        "data/symbols/*/gameconfig.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Live : les deux porteurs sont HORS POOL, le montage les injecte au catalogue puis "
              "fabrique la geometrie AU SEED (`--place`/`--a-place`, distances CALCULEES puis "
              "assertionnees). Oracles NON circulaires : `statModSources` et "
              "`decisionView.attackPlans`. Les sept mutants gardent la mesure elle-meme -- un "
              "mutant vert dirait que le temoin est aveugle, pas que le port est bon.",
}

import subprocess     # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)
import sys            # noqa: E402
from pathlib import Path                                                     # noqa: E402

import pytest                                                                # noqa: E402

HERE = Path(__file__).resolve()
PYDIR = HERE.parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_959_grim_efficiency_predictive_guidance as P   # noqa: E402


@pytest.fixture(scope="module")
def runner959():
    """UN runner pour tout le module (`scope="module"`) -- le montage coute une injection de
    catalogue et un build ; le rejouer par test saturerait le pump partage."""
    try:
        rid = P.build()
    except SystemExit as exc:
        pytest.fail("MONTAGE KO -- %s" % exc)
    dec = P.rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    g = P.etage1(dec)
    try:
        yield {"rid": rid, "dec": dec, "g": g}
    finally:
        subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "dispose",
                        "--runner", str(rid), "--state-file", str(P.STATE)],
                       capture_output=True, text=True)


def test_montage_les_sept_distances_sont_celles_voulues(runner959):
    """Un montage non conforme ne mesure RIEN -- il doit ROUGIR, jamais passer en silence."""
    g = runner959["g"]
    assert g["ok"], ("geometrie NON conforme : d(U,M)=%s d(U,C)=%s d(U,D)=%s d(M,E)=%s "
                     "d(M,F)=%s d(U,E)=%s d(U,F)=%s"
                     % (g["d_UM"], g["d_UC"], g["d_UD"], g["d_ME"], g["d_MF"],
                        g["d_UE"], g["d_UF"]))


def test_canal_une_seule_aura_GrimEfficiency_et_trois_PredictiveGuidance(runner959):
    """Le canal `decisionView.effects` est ACTIF-ONLY : il publie donc l'aura de la stance
    COURANTE et pas l'autre. Et les TROIS effets de `PredictiveGuidance` vivent sur AMMUK
    (`targets = Owner`), pas sur les ennemis -- leur `CreateTargetSelector` n'est pas
    materialise chez la cible."""
    r = P.etage2(runner959["dec"], runner959["g"])
    assert r["stance"] is not None, "aucune stance publiee -- le gate de GrimEfficiency ne mesure rien"
    assert r["partition_ok"], ("les DEUX auras de GrimEfficiency sont publiees ensemble "
                               "(stance=%s armor=%s pierce=%s)"
                               % (r["stance"], r["ge_armor"], r["ge_pierce"]))
    assert len(r["pg_on_carrier"]) == 3, r["pg_on_carrier"]
    assert not r["pg_on_foes"], ("un ennemi PORTE un effet PredictiveGuidance : %s -- le port le "
                                 "modelise cote SOURCE, ce serait un fork" % r["pg_on_foes"])


def test_aura_statmod_accord_avec_statModSources(runner959):
    """`GrimEfficiency` : le NATIF ecrit le stat-mod projete, le port doit ecrire le MEME, aux
    MEMES unites. Temoins qui DISCRIMINENT : la source (exclue), un allie a d>2, les ennemis."""
    r = P.etage3(runner959["rid"], runner959["g"])
    assert r["beneficiaires"], ("aucun beneficiaire NATIF -- l'accord serait DEGENERE "
                                "(le port pourrait ne rien ecrire et passer)")
    assert not r["bad"], "ECART(S) stat-mod natif/port :\n  " + "\n  ".join(r["bad"][:10])


def test_prediction_accord_avec_l_oracle_natif_par_tuile(runner959):
    """`PredictiveGuidance` : oracle NON circulaire (`decisionView.attackPlans`), par tuile
    candidate. Les TROIS assertions de non-degenerescence sont aussi importantes que l'accord --
    sans elles, un port qui n'appliquerait RIEN passerait."""
    d = runner959
    r = P.etage4(d["rid"], d["dec"], d["g"])
    assert r["rows"], "aucune tuile candidate rankee -- le montage ne mesure RIEN"
    assert r["lov_differe"], ("l'attaquant Leagues of Votann rend la MEME prediction dedans et "
                              "dehors de l'aura : le bonus n'est pas EXERCE, l'accord ne prouve rien")
    assert r["src_identique"] is True, ("la SOURCE (Ammuk) voit un ecart dedans/dehors -- "
                                        "`!AreEqual(EffectSource, Caster)` ne mord pas cote NATIF")
    assert r["wit_identique"] is True, ("un temoin NI LoV NI Mechanical voit un ecart -- "
                                        "le gate de faction ne mord pas cote NATIF")
    assert not r["bad"], "ECART(S) prediction natif/port :\n  " + "\n  ".join(r["bad"][:10])


def test_mutants_le_temoin_n_est_pas_aveugle(runner959):
    """DERNIER : sept mutations du port doivent TOUTES faire rougir l'etage qu'elles visent.
    Un mutant VERT ne dit pas que le port est bon -- il dit que la mesure ne voit rien."""
    d = runner959
    r = P.etage5(d["rid"], d["dec"], d["g"])
    assert r["ok"], "mutant(s) VERT(S) : %s" % [k for k, v in r["mutants"].items() if not v]
