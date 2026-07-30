"""Stikkbomb (1051) -- face DECISION, confrontee au LIVE (#27 verrou 3).

CE QUE CE TEST GARDE, et pourquoi il ne peut pas passer par accident :

A. **L'EXERCICE** : le natif doit REELLEMENT emettre `ActiveAbilityMessage(1051)`. Sans ce garde-fou
   le montage peut degenerer en « le natif joue son attaque normale dans les 7 bras » -- ce qui
   arrive des que le greffon a une arme ranged correcte (mesure du 2026-07-30 avec `orksKillaKan` :
   pair69 = 59.94 contre pair1051 = 28.88, ability 1051 JAMAIS proposee, et tous les bras
   « d'accord » sans rien mesurer).
B. **Le SOUS-SET est bien celui des AMIS adjacents a la CIBLE** : n=0 -> le natif vise T_high ;
   un seul ami colle a T_high le fait changer de cible ; les amis repartis loin -> retour a T_high.
C. **La forme est LINEAIRE, pas booleenne** : les bras DESEQUILIBRES tranchent sans recalibrer quoi
   que ce soit. `bal1` (1 ami sur chaque cible) doit rester sur T_high -- les deux modeles le
   predisent, c'est le controle ; `bal2` (2 amis sur T_high, 1 sur T_low) bascule sur T_low en
   LINEAIRE et resterait sur T_high en BOOLEEN.
D. **L'event splash porte sur la CIBLE PRINCIPALE, pas sur le voisin** : au bras `foe`, le
   supplement de `pairUtility(1051, T_high)` vaut la MOITIE de `pair(1051, T_high)` (1 coup au lieu
   de 2) et non la moitie de `pair(1051, voisin)`. C'est la face `MakeDamagePredictions` du meme
   quirk que le custom -- mesuree, pas deduite du decompile seul.
E. **Le terme est NECESSAIRE** (force a 0 -> le moteur diverge du natif) et **le port aussi**
   (playbook retire du registre -> divergence).

Le confond de PREDICTION est MESURE : les `pairUtility` natives sont bit-identiques sur tous les
bras ou seuls des AMIS bougent (un ami n'ajoute aucun event de prediction, seul un ENNEMI en ajoute).

PORTEUR : les deux seuls porteurs de 1051 sont un SUMMON (`orksOrkBoys`, via `Waaagh`) et un npc.
Le summon arrive bien en bataille par son summoner mais n'obtient jamais d'activation dans le
harnais arene -> GREFFE de l'ability sur `orksRuntherd` (`case-92` §5bis). Ce que la greffe ne
couvre pas est nomme dans `case-27` §Non couvert.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_27_4f_stikkbomb_ab as AB                       # noqa: E402

STIKKBOMB = AB.ABILITY


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


def _arms(rows):
    return {k: v for k, v in rows.items() if k != "_t"}


def test_native_actually_casts_stikkbomb(rows):
    """EXERCICE : sans un bras ou le natif joue REELLEMENT 1051, ce test ne mesure rien."""
    assert any(r["native"][0] == STIKKBOMB for r in _arms(rows).values()), (
        "le natif n'a jamais propose 1051 -- montage non exerce, l'accord des bras ne prouve rien")


def test_engine_matches_native_on_all_arms(rows):
    """Le moteur reproduit le choix NATIF (ability ET cible) dans les sept bras."""
    for k, row in _arms(rows).items():
        assert row["engine"] == row["native"], (
            "bras %s : moteur %s != natif %s" % (k, row["engine"], row["native"]))


def test_one_adjacent_friend_switches_the_target(rows):
    """Le SOUS-SET = les AMIS adjacents a la CIBLE : un seul suffit a changer de cible ici, et le
    natif revient sur T_high des qu'ils repartent (le terme est POSITIONNEL, pas une constante)."""
    t_high, t_low = rows["_t"]
    assert rows["n=0"]["native"][1] == t_high
    assert rows["n=1"]["native"][1] == t_low
    assert rows["ally-far"]["native"][1] == t_high


def test_term_is_linear_not_boolean(rows):
    """Bras DESEQUILIBRES : `bal1` reste sur T_high (les deux modeles), `bal2` bascule -- ce que
    seul un terme proportionnel au COMPTE d'amis peut produire."""
    t_high, t_low = rows["_t"]
    assert rows["bal1"]["native"][1] == t_high, (
        "bal1 a bascule -> le montage ne separe plus lineaire et booleen")
    assert rows["bal2"]["native"][1] == t_low, (
        "bal2 n'a pas bascule -> terme BOOLEEN (au moins un ami), pas -n x U1")


def test_pair_utilities_are_bit_identical_across_friend_arms(rows):
    """Confond de PREDICTION mesure et NUL : deplacer un AMI ne touche aucune `pairUtility` native
    (seul un ENNEMI adjacent ajoute un event, cf. `test_foe_adds_one_hit_on_the_target`)."""
    ref = rows["n=0"]["pairs"]
    for k in ("n=1", "n=2", "bal1", "bal2", "ally-far"):
        assert rows[k]["pairs"] == ref, (
            "bras %s : une pairUtility native a bouge -- l'A/B ne mesure plus le seul custom" % k)


def test_foe_adds_one_hit_on_the_target_not_on_the_neighbour(rows):
    """`StikkbombPlaybook$$MakeDamagePredictions` ajoute, par ENNEMI adjacent a la cible, un event
    de degat sur la CIBLE PRINCIPALE avec `nrOfHits_2`. Le supplement doit donc valoir ~la moitie de
    `pair(1051, T_high)` (1 coup contre 2), et NON la moitie de `pair(1051, voisin)`."""
    t_high, _ = rows["_t"]
    ref = rows["n=0"]["pairs"]
    add = rows["foe"]["pairs"][(STIKKBOMB, t_high)] - ref[(STIKKBOMB, t_high)]
    half_tgt = ref[(STIKKBOMB, t_high)] / 2.0
    half_foe = ref[(STIKKBOMB, AB.E3)] / 2.0
    assert add > 0, "un ennemi adjacent a la cible n'a rien ajoute a la prediction native"
    assert abs(add - half_tgt) < abs(add - half_foe), (
        "supplement %.4f plus proche de la moitie du VOISIN (%.4f) que de celle de la CIBLE (%.4f)"
        % (add, half_foe, half_tgt))


def test_custom_term_is_necessary(rows):
    """Force a 0, le custom fait DIVERGER le moteur du natif sur le bras qui bascule."""
    assert rows["n=1"]["engine_c0"] != rows["n=1"]["native"], (
        "custom force a 0 : le moteur suit encore le natif -> le terme est inerte dans ce montage")


def test_playbook_registration_is_necessary(rows):
    """Retire du registre, le playbook retombe sur la base `Fix64(0)` -> divergence."""
    assert rows["n=1"]["engine_noreg"] != rows["n=1"]["native"], (
        "playbook hors registre : le moteur suit encore le natif -> le port n'est pas ce qui decide")


def test_friend_count_is_what_the_engine_measures(rows):
    """Le compte moteur suit bien le montage (0, 1, 2 amis adjacents a T_high) : un `act move`
    refuse aurait laisse les trois bras identiques, et l'accord serait vide."""
    t_high, t_low = rows["_t"]
    assert rows["n=0"]["counts"][t_high] == 0
    assert rows["n=1"]["counts"][t_high] == 1
    assert rows["n=2"]["counts"][t_high] == 2
    assert rows["bal2"]["counts"][t_high] == 2 and rows["bal2"]["counts"][t_low] == 1
