"""Chronometron (1226, Thothmek `necroChronomancer`) -- face DECISION, confrontee au LIVE.

CE QUE CE TEST GARDE (et pourquoi il ne peut pas passer par accident) :

A. **La ROUTE non-attaque existe et sert.** 1226 n'a pas de `damageProfile` : `_is_attack_ability` la
   rejette, elle n'entre jamais dans `plans`, et `_best_attack` ne la voit pas. Le bras `noroute`
   (registre `NONATTACK_PLAYBOOKS` vide) rejoue la decision dans l'etat d'AVANT le port -- s'il rend
   la MEME chose que le port, c'est que le port est inerte et que l'accord vient d'ailleurs.
B. **Le terme custom est NECESSAIRE** : force a 0, le moteur DIVERGE du natif sur le bras n=2.
C. **La forme est LINEAIRE, pas booleenne** : le montage est calibre pour que l'attaque normale
   concurrente vaille entre `W` et `2W` -- n=1 ne bascule pas, n=2 bascule. Un port booleen (copie du
   2e terme de DoomSiren) aurait bascule des n=1.
D. **Le selecteur scope aux ENNEMIS** (`DSLSelectors.Enemies(...)`) : un ALLIE a la meme distance ne
   compte pas, le natif revient sur l'attaque normale.
L'ancrage du compte (position REELLE du caster et non tuile candidate du balayage) n'est PAS garde
ici : il exige un runner ou le caster n'a pas encore bouge (un `act move` consomme son mouvement, et
`aiMovableTiles` rend alors 0 tuile -- les deux hypotheses coincident et le test serait vide). Il est
MESURE par `probe_27_4b_chronometron_ab.py --anchor --build --engine` (qui oppose les deux hypotheses
et laisse le natif trancher) et garde OFFLINE par `probe_custom_utility_27.py` (invariance a
`caster_tile`).

Le confond de prediction est MESURE : les `pairUtility(69)` natives sont bit-identiques d'un bras a
l'autre (deplacer un appat ne change ni les stats ni le profil de degat).

Aucun scalaire de gameplay n'est fige : le poids vient de la BC re-synthetisee, l'encadrement des
`pairUtility` natives du montage.

PORTEUR HORS POOL : `necroChronomancer` est absent du seed BC capture -> injecte avec SES configs
d'ability par `catalog_inject.py` dans une COPIE sous `logs/` (jamais le seed partage).

ASCII only.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_27_4b_chronometron_ab as AB                    # noqa: E402

CHRONOMETRON = AB.CHRONOMETRON


def _seed_bc() -> Path | None:
    if AB.SEED_BC.exists():
        return AB.SEED_BC
    AB.SEED_BC.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([sys.executable, "catalog_inject.py", "--units", AB.CASTER_VID,
                        "--out", str(AB.SEED_BC)],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return AB.SEED_BC if (p.returncode == 0 and AB.SEED_BC.exists()) else None


@pytest.fixture(scope="module")
def rows():
    if _seed_bc() is None:
        pytest.skip("catalog_inject KO : porteur necroChronomancer non injectable")
    rid = AB.build(AB.HP_TARGET_DEFAULT)
    try:
        yield AB.run_ab(rid, engine=True)
    finally:
        try:
            AB.L._rpc("disposeRunner", [{"runnerId": rid}])
        except Exception:                                   # noqa: BLE001
            pass


def test_engine_matches_native_on_all_arms(rows):
    """Le moteur reproduit le choix NATIF dans les quatre bras (n=0 / n=1 / n=2 / allie)."""
    for k, row in rows.items():
        assert row["engine"]["on"] == row["native"], (
            "bras %s : moteur %s != natif %s" % (k, row["engine"]["on"], row["native"]))


def test_native_switches_only_at_two_enemies(rows):
    """LINEARITE : le natif garde l'attaque normale a n=1 et bascule sur 1226 a n=2."""
    assert rows["n=1"]["native"][0] != CHRONOMETRON, "n=1 a bascule -> terme booleen, pas lineaire"
    assert rows["n=2"]["native"][0] == CHRONOMETRON, "n=2 n'a pas bascule -> terme absent ou trop bas"


def test_pair_utilities_are_bit_identical_across_arms(rows):
    """Confond de PREDICTION mesure et NUL : la paire native de l'appat a paire forte ne bouge pas."""
    ref = max(rows["n=1"]["pairs"].values())
    for k in ("n=2", "ally"):
        assert max(rows[k]["pairs"].values()) == ref, (
            "bras %s : le maximum des pairUtility natives a bouge (%r != %r) -- le levier a change "
            "l'etage PAIRE, l'A/B ne mesure plus le seul terme custom"
            % (k, max(rows[k]["pairs"].values()), ref))


def test_custom_term_is_necessary(rows):
    """Force a 0, le custom fait DIVERGER le moteur du natif sur le bras n=2."""
    e = rows["n=2"]["engine"]
    assert e["zero"] != e["on"], "custom force a 0 ne change rien -> le terme est inerte"


def test_nonattack_route_is_necessary(rows):
    """Sans la route non-attaque, le moteur ne PEUT PAS proposer 1226 (elle n'est dans aucun `plan`)."""
    e = rows["n=2"]["engine"]
    assert e["on"][0] == CHRONOMETRON
    assert e["noroute"][0] != CHRONOMETRON, (
        "le moteur propose 1226 SANS la route non-attaque -- une autre voie la fait passer, "
        "la mesure ne prouve rien sur le deblocage")


def test_allies_do_not_count(rows):
    """`SurroundingEnemies` scope aux ENNEMIS : un allie a la meme distance ne compte pas."""
    assert rows["ally"]["engine"]["n"] == rows["n=1"]["engine"]["n"]
    assert rows["ally"]["native"] == rows["n=1"]["native"]


def test_no_action_without_enemy_in_range(rows):
    """Gate self-cast (`GetCasterNotAddedReason` -> 0x800) : sans ennemi a portee, aucune action."""
    assert rows["n=0"]["native"][0] != CHRONOMETRON
    assert rows["n=0"]["engine"]["caster_added"] is False
    assert rows["n=0"]["engine"]["targets"] == []
