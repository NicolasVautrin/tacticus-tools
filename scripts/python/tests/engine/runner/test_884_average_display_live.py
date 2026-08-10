"""#884 -- le canal DISPLAY `Average` des QUATRE descripteurs `EffectAdditionalHits` qui
publiaient `min`/`max` SANS `amount`, CONFRONTE LIVE sur ses quatre porteurs.

## L'artefact natif, LU (build rnca9r7q6c)

`IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, isPrediction, minVar, maxVar)` :

    isPrediction == 0 -> `IdunBattleLogic.Entities.DSLFormulas$$RandomAmount(minNode, maxNode)`  # ROLL
    isPrediction != 0 -> `IdunBattleLogic.Entities.DSLFormulas$$Average(minNode, maxNode)`       # DISPLAY

`IdunBattle.Entities.Effects.EffectAdditionalHits$$Create(out, trigger, roll, type, profile, hits,
forceOverkill, display)` pose `out+0x08 = roll` puis `out+0x10 = display if display else roll` ;
`IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(this, entities, useDisplay)` lit
`min = max = <+0x10>.Calculate()` quand `useDisplay`, sinon `<+0x08>.CalculateMin()/.CalculateMax()`.
`DSLFormulas$$Average(a, b)` = `DivideAmount(SumAmount(a, b), Direct(2), rule = null)` ->
`IdunBattle.Entities.Formulas.DivideAmount$$Calculate` ->
`IdunBattle.DSL.AAmountFormula$$RoundFix64Result(., 0)` = `FixMath.NET Fix64.Round` demi-vers-le-PAIR.

Les QUATRE `...$$CreateAdditionalHits` concernes passent bien `GetMinMaxDamage(this, 1)` en 8e
argument (`GetMinMaxDamage2` pour `CordClaw` : meme corps, variables `0x36`/`0x37`) :
`SquigHound_AdditionalHitsEffect`, `CordClaw_AdditionalHitsEffect`,
`SorcerousFacade_AdditionalHitsEffect`, `FearOfTheUnseen_ExtraDamageEffect`.

## CE QUE CE FICHIER GARDE

  1. **LE BI-CANAL EST MODELISE** (offline) : les quatre descripteurs publient `amount` ET
     `min`/`max`, et `amount` vaut `Fix64.Round((min + max) / 2)` demi-vers-le-PAIR.
  2. **L'ORDINAL EST FIGE** : les valeurs mesurees a la conversion sont ecrites ici. `probe_313`
     et consorts comparent un mirror a un build ; ils redeviennent VERTS des qu'on regenere le
     mirror. Ce qui manque toujours, c'est un garde sur la valeur ECRITE AU SITE -- c'est celui-ci.
  3. **LE MONTAGE SEPARE LES QUATRE MODELES** (live) : `port` (Fix64.Round), `predefined`
     (l'ANCIEN modele, sans `amount`), `float` ((min+max)/2 sans arrondi) et `floor`
     (`Fix64.Floor`) rendent des predictions DIFFERENTES sur chaque porteur, et seul `port`
     egale le natif. C'est ce que le montage de `#419-r1-tr11-r5` ne pouvait PAS faire : au
     regime qu'il servait, la somme des bornes etait PAIRE et le mutant `.5` rendait 26/26.
  4. **LE TEMOIN** : AVANT le cast, sans l'effet, port == natif. L'ecart mesure vient donc de
     l'effet, et de rien d'autre.

## LE LEVIER QUI REND L'ARRONDI SEPARABLE, et pourquoi il ne se devine pas

`round != floor` exige que la moyenne soit `k + 0.5` avec `k` IMPAIR, c'est-a-dire
`minDmg + maxDmg == 3 (mod 4)`. Le multiplicateur qui le realise est DERIVE de
`units.heroProgressionSteps` du gameconfig (`probe_884_average_display.separating_multiplier`), et
il est FORCE dans une copie du seed BC -- car `AbilityVariablesMultiplierPercentage` **n'est pas
recalcule par `buildNormalizedBC`** : le `--rank 17` de `rl_duel build` ne le touche pas, et le
seed sert **200** a `orksRuntherd`/`admecRuststalker`, **180** aux deux autres. Un probe qui
suppose 180 partout imprime un regime FAUX.

Ce n'est PAS un patch INVISIBLE DU PORT (motif `#366-r1-bcpatch-invisible`) : le multiplicateur est
LU par le port depuis l'etat du runner, donc les deux cotes voient le meme regime.

Montage et mesure : `scripts/python/probe_884_average_display.py`. ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/board.py", "scripts/python/hexgeo.py",
        "scripts/python/rl_duel.py",
        # PROPRE A CE FICHIER, perimetre pris LARGE. Le montage MONTE un runner et confronte la
        # chaine de PREDICTION complete : `entities/effects/loki/hits.py` (les quatre
        # descripteurs), `entities/effects/magnitude.py` (`ability_var` et le multiplicateur de
        # rarete), `dsl/base.py` (`_round_fix64`), `playbook/prediction/normal_attack.py` (le
        # choix `amount` vs `predefined`), `services/damage_prediction.py` et
        # `services/damage_calculations.py` (le spread +/-20 %), `playbook/scene.py`.
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment.
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/probe_884_average_display.py",
        # Le regime SERVI est une DONNEE du seed BC (`AbilityVariablesMultiplierPercentage`), la
        # courbe vient du gameconfig, et les ordinaux d'`EffectType` du dump du build.
        "data/seed-bc.json",
        "data/boards/**",
        "data/symbols/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : les QUATRE descripteurs publient le bi-canal ROLL/DISPLAY, "
              "`amount` vaut `Fix64.Round((min + max) / 2)` demi-vers-le-PAIR, l'ORDINAL mesure a "
              "la conversion (mult separant DERIVE de `heroProgressionSteps`, bornes, moyenne), "
              "la condition `min + max == 3 (mod 4)` qui rend l'arrondi separable, et -- LIVE -- "
              "l'egalite port/natif ligne a ligne plus la MORSURE des trois mutants "
              "(`predefined`, `float`, `floor`) sur chacun des quatre porteurs.",
}

import sys                                                    # noqa: E402
from fractions import Fraction                                # noqa: E402
from pathlib import Path                                      # noqa: E402

import pytest                                                 # noqa: E402

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_884_average_display as P                        # noqa: E402
from engine.dsl.base import _round_fix64                     # noqa: E402
from engine.entities.effects.factory import EFFECT_CLASSES   # noqa: E402
from engine.entities.effects.magnitude import ability_var    # noqa: E402
from engine.entities.effect_type import EffectType           # noqa: E402


#: `EffectType` de chaque descripteur ferme par #884 -- membres NOMMES, jamais l'ordinal.
_EFFECTS = (EffectType.SquigHound_AdditionalHits,
            EffectType.CordClaw_AdditionHits,
            EffectType.SorcerousFacade_AdditionalHits,
            EffectType.FearOfTheUnseen_ExtraDamage)

#: L'ordinal FIGE au moment de la conversion : (mult separant, min, max, amount attendu).
#: Regenerer le mirror ne peut pas rendre ce test vert -- il faut que la VALEUR ECRITE AU SITE
#: soit celle-la. Un changement de courbe gameconfig doit donc etre CONSTATE, pas subi.
_MESURE = {
    "SquigHound":            (180, 2394, 3589, 2992),
    "CordClaw":              (140,  620,  931,  776),
    "SorcerousFacade":       (100,  554, 1109,  832),
    "FearOfTheUnseen":       (120,  798,  997,  898),
}


def test_les_quatre_descripteurs_sont_au_registre():
    """(0) OFFLINE -- garde DERIVE : sans eux au registre, tout le reste de ce fichier confronte
    un port qui n'inscrit rien."""
    missing = [e.name for e in _EFFECTS if e.name not in EFFECT_CLASSES]
    assert not missing, (
        "descripteur(s) sorti(s) d'`EFFECT_CLASSES` : %s -- le canal #179 ne les pose plus, et "
        "les assertions live ci-dessous mesureraient un port qui ignore l'effet" % ", ".join(missing))


@pytest.mark.parametrize("cfg,kmin,kmax", [
    ("SquigHound", "minDmg", "maxDmg"),
    ("CordClaw", "minDmg_2", "maxDmg_2"),
    ("SorcerousFacade", "minDmg", "maxDmg"),
    ("FearOfTheUnseen", "minDmg", "maxDmg"),
])
def test_regime_separant_derive_et_fige(cfg, kmin, kmax):
    """(2) OFFLINE -- le multiplicateur separant est DERIVE du gameconfig, et l'ordinal ECRIT ici
    est celui mesure a la conversion. Les deux doivent coincider."""
    mult_attendu, mn_attendu, mx_attendu, amt_attendu = _MESURE[cfg]
    mult = P.separating_multiplier(cfg, kmin, kmax)
    assert mult == mult_attendu, (
        "le multiplicateur SEPARANT derive de `units.heroProgressionSteps` vaut %r, la mesure de "
        "la conversion dit %r -- la table de progression ou la courbe du gameconfig a bouge, "
        "CONSTATER avant de reecrire" % (mult, mult_attendu))
    mn = ability_var(cfg, kmin, 50, multiplier_pct=mult)
    mx = ability_var(cfg, kmax, 50, multiplier_pct=mult)
    assert (int(mn), int(mx)) == (mn_attendu, mx_attendu), (
        "bornes %s a (lvl 50, mult %d) : lues [%r, %r], mesurees [%d, %d]"
        % (cfg, mult, mn, mx, mn_attendu, mx_attendu))
    amt = _round_fix64(Fraction(int(mn) + int(mx), 2), 0)
    assert amt == amt_attendu, (
        "`Fix64.Round((%d + %d) / 2)` = %r, mesure %d" % (mn, mx, amt, amt_attendu))
    # `round != floor` : c'est CE qui rend l'arrondi separable -- l'assertion qui manquait a
    # `#419-r1-tr11-r5`, dont le montage servait une somme PAIRE.
    assert (int(mn) + int(mx)) % 4 == 3, (
        "somme %d (mod 4 = %d) : a ce regime `Fix64.Round` et `Fix64.Floor` COINCIDENT, et le "
        "montage cesserait de separer l'arrondi" % (int(mn) + int(mx), (int(mn) + int(mx)) % 4))
    assert amt != _round_fix64(Fraction(int(mn) + int(mx), 2), 2), (
        "`Round` et `Floor` rendent la MEME valeur -- le mutant `floor` ne mordrait pas")


@pytest.mark.parametrize("cfg,kmin,kmax", [
    ("SquigHound", "minDmg", "maxDmg"),
    ("CordClaw", "minDmg_2", "maxDmg_2"),
    ("SorcerousFacade", "minDmg", "maxDmg"),
    ("FearOfTheUnseen", "minDmg", "maxDmg"),
])
def test_le_descripteur_publie_les_deux_canaux(cfg, kmin, kmax):
    """(1) OFFLINE -- `amount` (noeud DISPLAY) ET `min`/`max` (noeud ROLL). Sans `amount`, la
    PREDICTION du port lit `predefined = [min, max]` la ou le natif lit une cellule DEGENEREE a la
    moyenne, etalee +/-20 % -- l'ecart MESURE va de 2 a 366 points selon le porteur."""
    name = {"SquigHound": EffectType.SquigHound_AdditionalHits,
            "CordClaw": EffectType.CordClaw_AdditionHits,
            "SorcerousFacade": EffectType.SorcerousFacade_AdditionalHits,
            "FearOfTheUnseen": EffectType.FearOfTheUnseen_ExtraDamage}[cfg].name
    mult, mn, mx, amt = _MESURE[cfg]
    eff = EFFECT_CLASSES[name](name=name, level=1, ability_level=50,
                               ability_variables_multiplier=mult)
    grp = (eff.additional_hit_groups({"is_melee": True}) or [None])[0]
    assert grp, "%s ne rend aucun groupe a (lvl 50, mult %d)" % (name, mult)
    assert (grp.get("min"), grp.get("max")) == (mn, mx), (
        "canal COMBAT (noeud ROLL) altere : attendu [%d, %d], lu %r"
        % (mn, mx, (grp.get("min"), grp.get("max"))))
    assert grp.get("amount") == amt, (
        "canal PREDICTION (noeud DISPLAY) : attendu `Fix64.Round((%d + %d) / 2)` = %d, lu %r"
        % (mn, mx, amt, grp.get("amount")))


@pytest.fixture(scope="module")
def mesures():
    """Le montage LIVE, joue UNE fois : quatre porteurs, multiplicateur separant force par porteur,
    armure des cibles a 0 (la reduction COMPRIME l'ecart d'arrondi et le rendrait invisible)."""
    state = PYDIR.parents[1] / "logs" / "runners" / "_884test_state.json"
    out = P.main(["--seed", "88410", "--max-rounds", "8", "--armor-target", "0",
                  "--separating-mult", "--state-file", str(state)], return_verdicts=True)
    if not isinstance(out, dict):
        pytest.fail("le montage #884 n'a produit aucune mesure (rc=%r)" % out, pytrace=False)
    return out


@pytest.mark.parametrize("vis", [c[0] for c in P.CARRIERS])
def test_port_egale_le_natif_et_les_trois_mutants_mordent(mesures, vis):
    """(3)+(4) LIVE -- sur chaque porteur : `port` egale le natif ligne a ligne, et les TROIS
    mutants (`predefined`, `float`, `floor`) en different. Le `predefined` est l'ANCIEN port : son
    ecart est la mesure du bug ferme."""
    assert vis in mesures, (
        "%s NON CONFRONTE : l'effet n'a jamais ete pose, ou aucune tuile classee. Ce n'est pas un "
        "skip acceptable -- le porteur est au pool et son ability poseuse est au registre." % vis)
    res, non_separees = mesures[vis]
    ok, n, worst, _ = res["port"]
    assert ok == n and worst == 0, (
        "%s : le port diverge du natif sur %d/%d lignes (|ecart| max %s)" % (vis, n - ok, n, worst))
    for mutant in ("predefined", "float", "floor"):
        assert mutant in res, "%s : la variante %s n'a pas ete jouee" % (vis, mutant)
        m_ok, m_n, m_worst, _ = res[mutant]
        assert m_ok == 0 and m_worst > 0, (
            "%s : le mutant `%s` NE MORD PAS (%d/%d en accord, |ecart| max %s) -- ce montage ne "
            "separe donc pas ce modele-la, et le vert du port ne prouve rien sur cet axe"
            % (vis, mutant, m_ok, m_n, m_worst))
    assert not non_separees, (
        "%s : variantes indistinguables du port sur ce montage : %s" % (vis, non_separees))
