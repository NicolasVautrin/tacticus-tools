"""#342 -- le terme BOUCLIER du composite `Damage(34)`, confronte au LIVE.

#333 a discrimine l'arrondi de `IdunBattle.Core.Services.MinMaxDamage$$Avg` sur le seul terme
SANTE ; `IdunBattle.AI.Utilities.DamageUtility$$GetShieldDamage` recevait le meme correctif PAR
SYMETRIE, sans mesure -- `AccurateShieldDamage` valait `[0, 0]` partout. Cette garde ferme ce
residu.

CE QU'ELLE VERROUILLE, et pourquoi elle ne peut pas passer par accident :

A. **Le levier de montage est le BON.** `BC.Units[].Shield` est ACCEPTE par `--unit-stat`, ECRIT
   dans le BC envoye a `initAndStart`, et SILENCIEUSEMENT ignore par le natif : la garde le
   MESURE aux deux bouts (BC archive vs `combatSnapshot.shields`). Le bouclier reel vient d'une
   pose EN BATAILLE (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility`).
B. **Le terme mesure est NON NUL et le regime n'est pas degenere** : bouclier reellement pose,
   borne haute CAPEE a `shieldBefore` (c'est ce cap qui rend la somme IMPAIRE), `LimitedByMinHp`
   faux, et le pas d'utilite MESURE vaut bien `100 / combinedMax`.
C. **Les DEUX cotes de la parite sont EXERCES, et ils sont PILOTES** par un pas de 1 sur
   `--unit-stat "<attaquant>:Damage=D"`.
D. **Le port egale le natif sur les DEUX bras** (`pairUtility` natif nourri des MEMES predictions
   `aiPlaybookPredict` que le port : formule ISOLEE, tout ecart est un gap de LOGIQUE).
E. **Le MODE est discrimine, pas suppose** -- et il l'est SUR LE TERME BOUCLIER SEUL : les quatre
   variantes remplacent la seule methode `DamageUtility.get_shield_damage`, le terme SANTE gardant
   son arrondi natif. Sans cette isolation, le terme sante suffirait a expliquer l'ecart.
F. **La MUTATION est jouee**, pas promise : `kept_half` EST le port d'avant #333, et il doit
   s'ecarter d'un DEMI pas avec des signes OPPOSES sur les deux bras.

Toute la lecture du decompile qui justifie la colonne « attendu » vit dans l'en-tete de
`probe_342_shield_term_rounding.py`.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_342_shield_term_rounding as P                   # noqa: E402

TOL_STEPS = 0.02          # en multiples du pas d'utilite (100 / combinedMax)


@pytest.fixture(scope="module")
def measured():
    out = P.run(seed=34201, verbose=False)
    assert not out.get("error"), "montage KO : %s" % out.get("error")
    for key, arm in (out.get("arms") or {}).items():
        assert not arm.get("error"), "bras %s KO : %s" % (key, arm["error"])
    return out


@pytest.fixture(scope="module")
def bc_field():
    return P.check_bc_shield_field(verbose=False)


def test_bc_units_shield_is_written_but_never_materialised(bc_field):
    """A : le levier `BC.Units[].Shield` est INERTE -- et le montage n'en dit RIEN de lui-meme.

    Les deux assertions separent les trois hypotheses : si le champ n'arrivait pas dans le BC,
    le bug serait cote outil Python / `buildNormalizedBC` ; il y arrive, et c'est le NATIF qui ne
    le lit pas. Un jour ou le natif l'honorerait, la seconde assertion tomberait -- et ce serait
    une VRAIE nouvelle, pas une regression."""
    assert not bc_field.get("error"), "montage KO : %s" % bc_field.get("error")
    assert bc_field["written_to_bc"], (
        "`--unit-stat <u>:Shield=%s` n'arrive PAS dans le BC envoye a initAndStart (Shield=%s) : "
        "le trou est cote outil Python / buildNormalizedBC, pas cote natif"
        % (bc_field["asked"], bc_field["bc_shield"]))
    assert not bc_field["materialised"], (
        "le natif a MATERIALISE un bouclier depuis `BC.Units[].Shield` (shields=%s) -- le champ "
        "n'etait pas lu au deploiement quand cette garde a ete ecrite "
        "(`BattleConfigBuilder$$GetUnitConfiguration` saute `UnitConfiguration.Shield@+0x4c`, "
        "`AddUnitOperation$$Execute` n'y touche pas). Verifier le levier et la doc case-342."
        % (bc_field["shields"],))


def test_the_shield_term_is_actually_exercised(measured):
    """B : sans bouclier POSE et sans CAP de la borne haute, `AccurateShieldDamage` vaut `[0,0]`
    (le cas de #333) ou une somme PAIRE -- et la garde ne mesurerait aucun arrondi."""
    for key, arm in measured["arms"].items():
        assert arm["shieldBefore"] > 0, (
            "bras %s : aucun bouclier en bataille -- le vecteur ArcaneShield n'a pas fire "
            "(deplacement du porteur refuse, ou aucun allie dans son rayon)" % key)
        assert arm["shieldCapped"], (
            "bras %s : la borne haute (%d) n'est pas capee au bouclier (%d) -- hors du regime de "
            "cap la somme est un multiple du nombre de coups, donc PAIRE, et aucun `.5` n'existe"
            % (key, arm["shieldDmgMax"], arm["shieldBefore"]))
        assert arm["sum_odd"], (
            "bras %s : somme bouclier %d PAIRE -- aucun `.5` exact, l'arrondi n'est pas exerce"
            % (key, arm["sum"]))


def test_the_two_arms_exercise_both_sides_of_the_parity(measured):
    """C : sans un `.5` a floor PAIR **et** un a floor IMPAIR, la garde ne separe aucun mode."""
    arms = measured["arms"]
    assert arms["up"]["floor_odd"] is True, (
        "bras UP : floor %d n'est pas IMPAIR -- le natif n'y monte pas" % arms["up"]["floor"])
    assert arms["down"]["floor_odd"] is False, (
        "bras DOWN : floor %d n'est pas PAIR -- le natif n'y descend pas" % arms["down"]["floor"])
    assert arms["up"]["shieldBefore"] == arms["down"]["shieldBefore"], (
        "les deux bras n'ont pas le meme bouclier (%s vs %s) : autre chose que la parite a bouge"
        % (arms["up"]["shieldBefore"], arms["down"]["shieldBefore"]))


def test_the_regime_is_not_degenerate(measured):
    """B (suite) : `LimitedByMinHp` court-circuiterait le terme SANTE, et un clamp absorberait le
    demi. On verifie que le pas d'utilite MESURE est bien la derivee analytique
    `100 / combinedMax` (`DamageDealt` 80 + `remaining` 20,
    `IdunBattle.AI.Utilities.DamageUtility$$.cctor`)."""
    for key, arm in measured["arms"].items():
        assert not arm["limitedByMinHp"], (
            "bras %s : `LimitedByMinHp` VRAI -- le composite ne lit plus les deux termes de la "
            "meme facon, la mesure ne porte plus sur l'arrondi du bouclier" % key)
        assert not arm["killSure"], (
            "bras %s : `WillBeKill` -- le regime de cap n'est plus celui qui est decrit" % key)
        # `trunc` (bras UP) et `half_up` (bras DOWN) valent exactement UNE unite de degat : leur
        # ecart mesure EST le pas, et il doit coincider avec la derivee analytique.
        one_unit = (arm["deltas"]["trunc"] if arm["floor_odd"] else -arm["deltas"]["half_up"])
        assert abs(one_unit - arm["step"]) < arm["step"] * TOL_STEPS, (
            "bras %s : une unite de degat deplace l'utilite de %.6f, or 100/combinedMax = %.6f -- "
            "un clamp est actif, le montage ne mesure plus l'arrondi" % (key, one_unit, arm["step"]))


def test_port_matches_the_native_on_both_arms(measured):
    """D : le terme degat du port == `pairUtility` natif, sur les DEUX parites.

    Deux mesures, et il FAUT les deux : `to_even` prouve que le MODE lu au decompile est le bon,
    `current` prouve que c'est bien CE mode que le moteur applique aujourd'hui. Les quatre
    variantes REMPLACENT `DamageUtility.get_shield_damage` : sans `current`, une regression du
    code reel ne rougirait nulle part."""
    for key, arm in measured["arms"].items():
        d = arm["measured_steps"]["to_even"]
        assert abs(d) < TOL_STEPS, (
            "bras %s : port %s != natif %s (ecart %s = %+.3f pas) -- l'arrondi demi-vers-le-pair "
            "n'est pas le mode du natif sur le terme BOUCLIER"
            % (key, arm["ports"]["to_even"], arm["native"], arm["deltas"]["to_even"], d))
        c = arm["measured_steps"]["current"]
        assert abs(c) < TOL_STEPS, (
            "bras %s : le moteur EN VIGUEUR rend %s la ou le natif rend %s (ecart %+.3f pas) -- "
            "`DamageUtility.get_shield_damage` n'applique plus `min_max_avg`"
            % (key, arm["ports"]["current"], arm["native"], c))


def test_round_to_even_is_the_only_mode_null_on_both_arms(measured):
    """E : LA discrimination, portee par le SEUL terme bouclier. Chaque autre mode DOIT tomber
    sur au moins un bras."""
    arms = measured["arms"]
    for name in ("half_up", "kept_half", "trunc"):
        fails = [k for k, arm in arms.items() if abs(arm["measured_steps"][name]) >= TOL_STEPS]
        assert fails, (
            "le mode `%s` egale le natif sur les DEUX bras : le montage ne discrimine pas "
            "demi-vers-le-pair de `%s` sur le terme BOUCLIER" % (name, name))
    assert measured.get("nul_on_both_arms") == ["to_even"], (
        "modes nuls sur les deux bras : %s -- il devrait n'y avoir QUE `to_even`"
        % (measured.get("nul_on_both_arms"),))


def test_the_pre_333_port_turns_this_guard_red_in_both_directions(measured):
    """F : la MUTATION. `kept_half` reproduit EXACTEMENT le port d'avant #333 (`(min+max)/2.0`)
    sur le terme BOUCLIER, sans revenir en arriere dans le code. Elle doit s'ecarter d'un DEMI
    pas -- vers le HAUT quand le natif monte, vers le BAS quand il descend."""
    arms = measured["arms"]
    up = arms["up"]["measured_steps"]["kept_half"]
    down = arms["down"]["measured_steps"]["kept_half"]
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
    assert measured.get("ok"), "verdict global du probe #342 : ECHEC"
