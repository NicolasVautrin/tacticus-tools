"""#333 -- l'arrondi de `IdunBattle.Core.Services.MinMaxDamage$$Avg`, confronte au LIVE.

CE QUE CETTE GARDE VERROUILLE, et pourquoi elle ne peut pas passer par accident :

A. **Les DEUX cotes de la parite sont EXERCES, et ils sont PILOTES.** Un `.5` EXACT n'existe que
   si `Min + Max` est IMPAIR, et sur un `.5` a partie entiere IMPAIRE demi-vers-le-pair et
   demi-vers-le-haut rendent la MEME valeur. Une mesure qui ne verrait que ce cote-la ne dirait
   RIEN du mode -- c'est le trou de la mesure #329 (`3771 + 5652`, floor `4711`, IMPAIR).
   Le montage ne SUBIT donc pas la parite : `AccurateHealthDamage` est capee aux PV de la cible et
   `rl_duel build --hp-target H` les pose, donc `H` CHOISIT la somme `rawMin + H`. Deux bras a
   `H` distants de 2, tout le reste identique.
B. **Le port egale le natif sur les DEUX bras** (`pairUtility` =
   `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`,
   nourri des MEMES predictions natives `aiPlaybookPredict` que le port : formule ISOLEE, tout
   ecart est un gap de LOGIQUE).
C. **Le MODE est discrimine, pas suppose.** Quatre variantes d'arrondi tournent sur le MEME feed ;
   `demi-vers-le-haut` tombe sur le bras DOWN, `troncature` sur le bras UP, `le .5 conserve` (le
   port d'AVANT #333) sur les DEUX. Seul `demi-vers-le-pair` est nul partout.
D. **La MUTATION est jouee**, pas promise : la variante `kept_half` EST le port d'avant #333, et
   la garde exige qu'elle s'ecarte d'exactement un DEMI pas d'utilite, avec des signes OPPOSES sur
   les deux bras.
E. **Le regime n'est pas degenere** : somme IMPAIRE des deux cotes, `LimitedByMinHp` faux (sinon la
   branche court-circuite `Avg`), et le pas d'utilite MESURE vaut bien `100 / combinedMax` (sinon
   un clamp absorbe le demi et la mesure ne mord plus).

Toute la lecture du decompile qui justifie la colonne « attendu » vit dans l'en-tete de
`probe_333_minmax_avg_rounding.py`.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_333_minmax_avg_rounding as P                    # noqa: E402

TOL_STEPS = 0.02          # en multiples du pas d'utilite (100 / combinedMax)


@pytest.fixture(scope="module")
def measured():
    out = P.run(seed=33301, verbose=False)
    assert not out.get("error"), "montage KO : %s" % out.get("error")
    for key, arm in (out.get("arms") or {}).items():
        assert not arm.get("error"), "bras %s KO : %s" % (key, arm["error"])
    return out


def test_the_two_arms_exercise_both_sides_of_the_parity(measured):
    """A : sans un `.5` a floor PAIR **et** un a floor IMPAIR, la garde ne separe aucun mode."""
    arms = measured["arms"]
    for key, arm in arms.items():
        assert arm["sum_odd"], (
            "bras %s : somme %d PAIRE -- aucun `.5` exact, le montage n'exerce pas l'arrondi"
            % (key, arm["sum"]))
    assert arms["up"]["floor_odd"] is True, (
        "bras UP : floor %d n'est pas IMPAIR -- le natif n'y monte pas" % arms["up"]["floor"])
    assert arms["down"]["floor_odd"] is False, (
        "bras DOWN : floor %d n'est pas PAIR -- le natif n'y descend pas" % arms["down"]["floor"])
    assert abs(arms["up"]["hp"] - arms["down"]["hp"]) == 2, (
        "les deux bras ne different pas que de 2 PV (%s vs %s) : autre chose que la parite a bouge"
        % (arms["up"]["hp"], arms["down"]["hp"]))


def test_the_regime_is_not_degenerate(measured):
    """E : `LimitedByMinHp` court-circuiterait `Avg`, et un clamp absorberait le demi. On verifie
    que le pas d'utilite MESURE est bien la derivee analytique `100 / combinedMax`
    (`DamageDealt` 80 + `remaining` 20, `IdunBattle.AI.Utilities.DamageUtility$$.cctor`)."""
    for key, arm in measured["arms"].items():
        assert not arm["limitedByMinHp"], (
            "bras %s : `LimitedByMinHp` VRAI -- `GetHealthDamage` rend CurrentHealth sans passer "
            "par `Avg`, la mesure ne porte plus sur l'arrondi" % key)
        assert not arm["killSure"], (
            "bras %s : `WillBeKill` -- les PV sont sous la borne BASSE, la somme redevient paire"
            % key)
        # `trunc` (bras UP) et `half_up` (bras DOWN) valent exactement UNE unite de degat : leur
        # ecart mesure EST le pas, et il doit coincider avec la derivee analytique.
        one_unit = (arm["deltas"]["trunc"] if arm["floor_odd"] else -arm["deltas"]["half_up"])
        assert abs(one_unit - arm["step"]) < arm["step"] * TOL_STEPS, (
            "bras %s : une unite de degat deplace l'utilite de %.6f, or 100/combinedMax = %.6f -- "
            "un clamp est actif, le montage ne mesure plus l'arrondi" % (key, one_unit, arm["step"]))


def test_port_matches_the_native_on_both_arms(measured):
    """B : le terme degat du port == `pairUtility` natif, sur les DEUX parites."""
    for key, arm in measured["arms"].items():
        d = arm["measured_steps"]["to_even"]
        assert abs(d) < TOL_STEPS, (
            "bras %s : port %s != natif %s (ecart %s = %+.3f pas) -- l'arrondi demi-vers-le-pair "
            "n'est pas (ou plus) applique au foyer `MinMaxDamage$$Avg`"
            % (key, arm["ports"]["to_even"], arm["native"], arm["deltas"]["to_even"], d))


def test_round_to_even_is_the_only_mode_null_on_both_arms(measured):
    """C : LA discrimination. Chaque autre mode DOIT tomber sur au moins un bras."""
    arms = measured["arms"]
    for name in ("half_up", "kept_half", "trunc"):
        fails = [k for k, arm in arms.items() if abs(arm["measured_steps"][name]) >= TOL_STEPS]
        assert fails, (
            "le mode `%s` egale le natif sur les DEUX bras : le montage ne discrimine pas "
            "demi-vers-le-pair de `%s`" % (name, name))
    assert measured.get("nul_on_both_arms") == ["to_even"], (
        "modes nuls sur les deux bras : %s -- il devrait n'y avoir QUE `to_even`"
        % (measured.get("nul_on_both_arms"),))


def test_the_pre_333_port_turns_this_guard_red_in_both_directions(measured):
    """D : la MUTATION. `kept_half` reproduit EXACTEMENT le port d'avant #333 (`(min+max)/2.0`)
    sans revenir en arriere dans le code. Elle doit s'ecarter d'un DEMI pas -- vers le HAUT quand
    le natif monte, vers le BAS quand il descend. Un ecart de meme signe des deux cotes signalerait
    que la mesure ne voit pas la parite."""
    arms = measured["arms"]
    up, down = arms["up"]["measured_steps"]["kept_half"], arms["down"]["measured_steps"]["kept_half"]
    assert abs(up - 0.5) < TOL_STEPS, (
        "bras UP : le port d'avant #333 s'ecarte de %+.3f pas au lieu de +0.5 -- la mutation ne "
        "vire pas au rouge comme prevu" % up)
    assert abs(down + 0.5) < TOL_STEPS, (
        "bras DOWN : le port d'avant #333 s'ecarte de %+.3f pas au lieu de -0.5 -- le natif y "
        "DESCEND, or la mesure ne voit qu'une sur-estimation" % down)
    assert up * down < 0, (
        "l'ecart du port d'avant #333 a le MEME signe sur les deux bras (%+.3f / %+.3f) : la "
        "garde ne separe alors pas demi-vers-le-pair de demi-vers-le-haut" % (up, down))


def test_overall_verdict(measured):
    assert measured.get("ok"), "verdict global du probe #333 : ECHEC"
