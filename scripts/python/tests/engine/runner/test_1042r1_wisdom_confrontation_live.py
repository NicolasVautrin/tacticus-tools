"""#1042-r1 -- CLIQUET LIVE de `WisdomOfTheAncients_DamageReduction` (1445).

Il ne duplique NI montage NI critere : il appelle
`probe_1042r1_wisdom_confrontation_live.confronter(rpc, rid)` sur un runner monte une SEULE fois
pour le module, et assertionne ce que le probe MESURE.

DEUX ETAGES, tous deux avec leur TEMOIN NON NUL :
  A. le SELECTEUR -- `wisdom_of_the_ancients_target_ids` contre `decisionView.targetIds`, ET le
     regime doit SEPARER (au moins une unite prise, au moins une ecartee). Sans ce second cran,
     l'accord ne prouverait rien : `rl_duel build` impose `targetRarity = 5` a toute unite
     normalisee, donc les TROIS etages `UnitsWithRarity(Mythic)` y sont uniformement VRAIS ;
  B. la MAGNITUDE -- prediction du port contre `attackPlans[].evals[].ranked[]` (foyer PARTAGE
     `prediction_confrontation`, tolerance 3), ET la liste confrontee doit etre NON VIDE.

TEMOIN d'ORIGINE (mesure du 2026-08-14, MEME runner, MEME oracle) : sur `origin/master` l'etage B
rendait **7 divergences / 25 lignes** (port `(2444, 3664)` contre oracle `(1956, 2932)`, soit le
`x0.80` natif absent) ; avec le port, **0**. Le bras separant `--rarity adeptRetributor=4` : natif
`{P2, P3}`, master 5 divergences, port 0.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]            # scripts/python
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_1042r1_wisdom_confrontation_live as C     # noqa: E402
import probe_1042_wisdom_of_the_ancients_live as G     # noqa: E402
import rl_collect_batch as B                           # noqa: E402
import rl_duel as R                                    # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_1042r1_wisdom_confrontation_live.py",
        "scripts/python/probe_1042_wisdom_of_the_ancients_live.py",
        "scripts/python/prediction_confrontation.py",
        "scripts/python/engine/entities/effects/loki/damage_reduction.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/engine/runner/snapshot.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "Il MONTE un runner : tout ce qui touche au harnais de build, au seed de la Scene ou "
              "au capteur `unitAbilityStates` le concerne, et le gameconfig "
              "(`WisdomOfTheAncients.dmgReductionPct`) se perime SEPAREMENT du build.",
}

LEVEL = 4
SEED = 777


@pytest.fixture(scope="module")
def mesure():
    """Monte le bras `mow` UNE fois, confronte, dispose. `pytest.fail` (jamais `skip`) si le
    montage ne s'installe pas : un skip se lirait comme un vert (#268/#455)."""
    import json

    sid = B._resolve_session()
    rpc = C._rpc_de(sid)
    rar = {G.H_VIS: str(G.RARITE_H)}
    sf = str(PYDIR.parent.parent / "logs" / ("test1042r1_l%d.json" % LEVEL))
    argv = ["build", "--seed", str(SEED), "--board", G.BOARD,
            "--p-units", ",".join(v for v, _ in G.MES_UNITS),
            "--a-units", ",".join(v for v, _ in G.AURA_UNITS),
            "--a-mow", G.PORTEUR_MOW,
            "--unit-stat", ";".join("%s:Rarity=%s" % (k, v) for k, v in sorted(rar.items())),
            "--equip-mythic", "%s:%s:%d" % (G.PORTEUR_MOW, G.ABILITY, LEVEL)]
    for vis, pos in G.MES_UNITS:
        argv += ["--place", "%s:%d,%d" % (vis, pos[0], pos[1])]
    for vis, pos in G.AURA_UNITS:
        argv += ["--a-place", "%s:%d,%d" % (vis, pos[0], pos[1])]
    argv += ["--state-file", sf]
    if R.main(argv) != 0:
        pytest.fail("montage #1042-r1 non installe (build KO) -- rien n'est mesure", pytrace=False)
    rid = json.loads(Path(sf).read_text(encoding="utf-8")).get("runnerId")
    if rid is None:
        pytest.fail("montage #1042-r1 : aucun runnerId", pytrace=False)
    try:
        yield C.confronter(rpc, int(rid))
    finally:
        try:
            rpc("disposeRunner", {"runnerId": int(rid)}, 40)
        except Exception:      # noqa: BLE001  -- le dispose n'est pas un critere
            pass


def test_le_montage_a_bien_pose_l_aura(mesure):
    """Anti-vacuite : sans porteur ni cible, les deux etages seraient vides ET verts."""
    assert mesure["porteur"] is not None, "aucun porteur de 1445 -- `--equip-mythic` n'a pas mordu"
    assert mesure["natif"], "l'aura ne vise personne : le montage ne mesure rien"


def test_le_regime_separe(mesure):
    """`rl_duel build` impose `targetRarity = 5` : sans separation, un port SANS gate de rarete
    serait d'accord partout. On exige donc un temoin PRIS **et** un temoin ECARTE."""
    pris = set(mesure["natif"])
    ecartes = set(mesure["univers"]) - pris
    assert pris, "aucune unite prise -- l'accord serait vide"
    assert ecartes, ("aucune unite ecartee : REGIME DEGENERE, un accord n'y separe RIEN "
                     "(monter `--rarity <vis>=N`)")


def test_etage_A_le_selecteur_concorde(mesure):
    """`wisdom_of_the_ancients_target_ids` (face PREDICTION) == `decisionView.targetIds`."""
    assert mesure["port"] is not None, "resolveur MUET (porteur sans equipe ?) -- rien n'est conclu"
    assert set(mesure["port"]) == set(mesure["natif"]), (
        "SELECTEUR : port\\natif=%s natif\\port=%s"
        % (sorted(set(mesure["port"]) - set(mesure["natif"])),
           sorted(set(mesure["natif"]) - set(mesure["port"]))))


def test_etage_B_la_magnitude_concorde(mesure):
    """Prediction du port contre `attackPlans[].evals[].ranked[]`, tolerance 3.

    C'est CET etage qui a trouve le bug de `GetAbilityState` : avant correctif le port lisait
    `dmgReductionPct[<niveau de STACK>] = 10` et rendait `x0.90` contre `x0.80` natif."""
    assert mesure["lignes"], "AUCUNE ligne confrontee -- un accord vide est zero preuve"
    assert not mesure["divergences"], (
        "MAGNITUDE : %d divergence(s) sur %d lignes -- %s"
        % (len(mesure["divergences"]), len(mesure["lignes"]), mesure["divergences"][:6]))
