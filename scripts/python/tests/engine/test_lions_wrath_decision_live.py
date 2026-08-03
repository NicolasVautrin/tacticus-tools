"""TheLionsWrath (1217, porteur `darkaBossLion` npc -> GREFFE) -- face DECISION, confrontee au LIVE.

CE QUE CE TEST GARDE, et pourquoi chaque assertion ferme une explication CONCURRENTE de l'accord :

A. **La GREFFE exerce bien `TheLionsWrathPlaybook`.** Le seul porteur de 1217 est un npc ; le natif
   charge le playbook PAR ABILITY (`PlaybookDatabase.LoadPlaybook(abilityType)`), donc greffer
   `[1217]` sur `darkaAsmodai` suffit -- et le natif le PROUVE en emettant
   `ActiveAbilityMessage(1217)`. Si cette assertion tombe, tout le reste du fichier est sans objet.
B. **`MakeDamagePredictions` rend une liste VIDE, des DEUX cotes.** Cote natif c'est
   `aiPlaybookPredict` (`count = 0` avec `listNull = false` : l'appel REUSSIT) ; cote port c'est
   l'override. C'est ce fait qui met 1217 sur la route NON-ATTAQUE (motif de 1009 ResurrectionOrb) --
   sans lui, le chemin generique fabriquerait une prediction depuis `attackPlans`, que
   `projection.ts` remplit avec la PREVIEW de l'attaque normale.
C. **Le terme custom DEPARTAGE la cible, et dans le SENS du natif.** Le montage oppose
   `blackAbaddon` (`FindMeleeWeapon().Hits = 5` -> custom 4300) a `thousAhriman` (`Hits = 1` ->
   4180), et donne a ce dernier des PV minuscules pour que sa PREVIEW d'attaque ecrase l'autre
   (238 contre 8 au dernier releve). Le natif choisit quand meme `blackAbaddon` : son choix ne
   s'explique donc PAS par l'utilite de degat.
D. **Ni par l'ORDRE d'enumeration** : le bras `swap` ECHANGE les deux tuiles. Le natif balaie les
   cibles par rang cube croissant et garde le premier maximum STRICT ; si son choix venait de
   l'ordre, il changerait de cible. Il ne change pas.
E. **Les contre-epreuves** : `custom = 0` et registre `NONATTACK_PLAYBOOKS` VIDE doivent tous deux
   DEPLACER la decision du moteur (sans quoi le port serait inerte), et NIER le seul terme qui
   departage ici (`30 x Hits`) doit changer la CIBLE (sans quoi il serait decoratif).

CE QUI N'EST PAS GARDE, ET POURQUOI (dit plutot que masque) :
* le terme `2000 x |adjacents Chaos+Hero|` ne departage PAS deux cibles (il ne depend que de
  `casterPosition`) : ce montage etablit sa VALEUR portee, pas son arbitrage ;
* le terme `150 x [cible Hero]` est CONSTANT ici -- les **97** unites du pool portent toutes le
  trait `Hero` (compte re-derive). Le discriminer exigerait une cible sans `Hero`, c.-a-d. un
  SUMMON adverse ou une MoW (mais une MoW n'est pas ciblable : le masque `0x4000` n'a pas le bit
  de domaine `TargetIsActor`, donc `TargetIsUnit` refuse) ;
* le gate `ShouldEvaluate` = `HasMinimumRemainingTurns(unit, 2) && Count() >= 0` : le second terme
  est TOUJOURS vrai (relu a l'assembleur) et le premier n'a pas de substrat cote port -- il ne peut
  mordre que dans un match A PLAFOND DE TOURS, qu'aucun runner d'arene ne monte ;
* la face COMBAT de 1217 n'est pas portee (residu nomme).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_27_r4_lions_wrath as AB                        # noqa: E402

LIONS_WRATH = AB.LIONS_WRATH
NORMAL = AB.NORMAL
ARMS = ("base", "swap")


@pytest.fixture(scope="module")
def rows():
    rid = AB.build(100)
    try:
        yield AB.run_arms(rid, 100)
    finally:
        try:
            AB.L._rpc("disposeRunner", [{"runnerId": rid}])
        except Exception:                                   # noqa: BLE001
            pass


def test_graft_makes_the_native_emit_the_ability(rows):
    """A -- le natif emet `ActiveAbilityMessage(1217)` sur les deux bras."""
    for k in ARMS:
        assert rows[k]["native_ability"] == LIONS_WRATH, (
            "bras %s : le natif a propose %r -- la greffe n'exerce pas le playbook, aucune des "
            "mesures suivantes ne vaut" % (k, rows[k]["native_ability"]))


def test_native_makes_no_damage_prediction(rows):
    """B -- `MakeDamagePredictions` NATIF rend 0 event sur chaque cible, et le port aussi."""
    for k in ARMS:
        for tgt, n in rows[k]["native_preds"].items():
            assert n == 0, (
                "bras %s : `aiPlaybookPredict(1217)` rend %r event(s) sur u%s -- si le natif predit "
                "un degat, la route non-attaque n'est plus le bon mirror" % (k, n, tgt))
        assert rows[k]["engine_preds"] == 0, (
            "bras %s : le port rend %d prediction(s) la ou le natif n'en rend aucune"
            % (k, rows[k]["engine_preds"]))


def test_native_utility_from_predictions_is_zero(rows):
    """B -- `pairUtility(1217)` = `CalculateUtilityFromPredictions` NATIF = 0 sur chaque cible.
    Deuxieme canal, independant d'`aiPlaybookPredict`."""
    for k in ARMS:
        for tgt, v in rows[k]["u_full"].items():
            assert v == 0.0, (
                "bras %s : pairUtility(1217, u%s) = %r, attendu 0 (liste de predictions vide)"
                % (k, tgt, v))


def test_custom_term_has_the_read_values(rows):
    """Les valeurs PORTEES, contre une derive de code : `30 x Hits + 2000 x n + 150 x [Hero]`
    avec n = 2 (les deux adjacents sont Chaos+Hero), Hits = 5 et 1, les deux cibles Hero."""
    for k in ARMS:
        r = rows[k]
        assert r["custom"][r["hi"]] == 4300.0, (
            "bras %s : custom(blackAbaddon) = %r, attendu 30*5 + 2000*2 + 150"
            % (k, r["custom"][r["hi"]]))
        assert r["custom"][r["lo"]] == 4180.0, (
            "bras %s : custom(thousAhriman) = %r, attendu 30*1 + 2000*2 + 150"
            % (k, r["custom"][r["lo"]]))


def test_arms_are_discriminant(rows):
    """C -- au moins un bras oppose argmax(custom) et argmax(preview). Sans ce contraste, l'accord
    natif<->moteur serait le meme avec un custom NUL et ne prouverait rien."""
    assert any(rows[k]["arg_custom"] != rows[k]["arg_preview"] for k in ARMS), (
        "aucun bras discriminant : argmax(custom) == argmax(preview) partout -- regler les PV de "
        "thousAhriman (`AB.build(<pv>)`)")


def test_native_picks_the_argmax_of_custom(rows):
    """C -- le natif choisit la cible d'argmax(CUSTOM), pas celle d'argmax(preview)."""
    for k in ARMS:
        r = rows[k]
        assert r["native_target"] == r["arg_custom"], (
            "bras %s : natif cible=u%s, argmax(custom)=u%s (preview favorisait u%s)"
            % (k, r["native_target"], r["arg_custom"], r["arg_preview"]))


def test_choice_survives_swapping_the_two_tiles(rows):
    """D -- le vainqueur natif ne change pas quand on ECHANGE les tuiles des deux cibles : le choix
    ne vient donc pas de l'ordre d'enumeration."""
    assert rows["base"]["native_target"] == rows["swap"]["native_target"], (
        "le vainqueur natif CHANGE avec l'arrangement des positions (%s -> %s) : le choix suit "
        "l'ordre d'enumeration, pas le custom"
        % (rows["base"]["native_target"], rows["swap"]["native_target"]))


def test_engine_matches_native_on_both_arms(rows):
    """Le moteur reproduit ability ET cible du natif sur les deux bras."""
    for k in ARMS:
        r = rows[k]
        assert r["engine"] == (LIONS_WRATH, r["native_target"]), (
            "bras %s : moteur %r != natif (%s, %s)"
            % (k, r["engine"], LIONS_WRATH, r["native_target"]))


def test_counter_proof_custom_zero_moves_the_decision(rows):
    """E -- custom force a 0 : le moteur ne doit plus rendre la meme decision."""
    for k in ARMS:
        assert rows[k]["zero"] != rows[k]["engine"], (
            "bras %s : custom force a 0 rend toujours %r -- le terme est INERTE"
            % (k, rows[k]["zero"]))


def test_counter_proof_route_off_moves_the_decision(rows):
    """E -- registre `NONATTACK_PLAYBOOKS` vide : 1217 n'a plus AUCUNE route (elle est invisible de
    `_best_attack`), le moteur doit retomber ailleurs."""
    for k in ARMS:
        assert rows[k]["noroute"] != rows[k]["engine"], (
            "bras %s : route OFF rend toujours %r -- le routage non-attaque est INERTE"
            % (k, rows[k]["noroute"]))


def test_counter_proof_negating_the_hits_term_flips_the_target(rows):
    """E -- nier `30 x Hits` (le SEUL des trois facteurs qui departage ici) doit changer la CIBLE.
    S'il ne la changeait pas, l'accord de `test_native_picks_the_argmax_of_custom` viendrait
    d'autre chose."""
    for k in ARMS:
        r = rows[k]
        assert r["neg"] == (LIONS_WRATH, r["lo"]), (
            "bras %s : terme `30 x Hits` nie -> %r, attendu (%s, u%s) : le terme ne departage pas "
            "les cibles" % (k, r["neg"], LIONS_WRATH, r["lo"]))
