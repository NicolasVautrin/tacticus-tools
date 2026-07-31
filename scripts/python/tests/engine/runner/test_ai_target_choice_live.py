"""#338 -- le CHOIX DE CIBLE de `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute`,
confronte au LIVE sur un regime INDEPENDANT de celui qui a revele l'ecart (#334 / 1117).

CE QUE CES TESTS VERROUILLENT. Le corps unique ne choisit AUCUNE cible : il delegue a
`IdunBattle.Core.Services.AiControl$$ExecuteAbilityActionFor(unit, GetNormalAttackType(unit), options)`
-> `IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext`
-> UN `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator` sur un set d'UNE ability ->
`IdunBattle.AI.BucketSystem.Bucket.ChooseAction`. Le port l'approximait par « ennemi vivant le plus
proche, tie-break id » (`_nearest_enemy`) -- huit consommateurs en heritaient.

MONTAGE (`ai_target_choice_case`, porte de `scripts/python/probe_338_ai_target_choice.py`) : DEUX
ennemis a distance EGALE (1) de la tuile de spawn d'un `genesSmnAberrant` (arme MELEE), avec des
`maxHP` d'un ordre de grandeur d'ecart. A distance egale, `_nearest_enemy` ne peut departager que
par son tie-break `id` -- il elit donc TOUJOURS le plus petit id. Le moteur d'utilite, lui, compare
`healthDmg / (maxHP + 1) * 100` : il suit le PETIT maxHP.

Les deux regimes ne se recouvrent pas : le premier etablit que le port ne suit PLUS la geometrie
(cible != celle du raccourci, et == celle du natif) ; le second echange les deux `maxHP` et etablit
que la victime BASCULE -- sans lui, « le port frappe le bon » pourrait n'etre qu'un coup de chance
de tie-break.

ASCII only (console cp1252).
"""
from __future__ import annotations

import probe_338_ai_target_choice as P


def test_the_target_comes_from_the_utility_engine_not_from_the_distance(ai_target_choice_case):
    """REGIME DISCRIMINANT -- l'ennemi a PETIT maxHP porte le PLUS GRAND id.

    Quatre assertions qui ne se recouvrent pas :
      1. le montage est bien DISCRIMINANT -- `_nearest_enemy` designe un AUTRE ennemi que celui
         que le NATIF frappe. La mesure se fait contre le live, jamais contre le port : sinon un
         port revenu au raccourci ferait dire au montage « je ne discrimine plus », ce qui
         masquerait la regression ;
      2. le cast LIVE a REELLEMENT eu lieu (`mutated`) -- sans quoi « zero degat » serait un
         echec de montage lu comme une mesure ;
      3. le NATIF frappe l'ennemi a petit maxHP ;
      4. le PORT frappe LE MEME.

    Le MONTANT, lui, n'est pas verrouille : le natif buffe le summon a l'apparition
    (`Hypermorph` -> `UnitStats_Attack_Modification`) et cette passive n'est pas portee -- residu
    PRE-EXISTANT de 1166, deja nomme par `test_aberrant_hypermorph_live`, sans rapport avec le
    choix de cible."""
    low = P.ENEMY_VIS[1]
    r = ai_target_choice_case(low)
    assert r["discriminant"] is True, (
        "montage NON discriminant : `_nearest_enemy` designe deja %s -- l'accord ne prouverait rien"
        % r["nearest_vis"])
    assert r["live_mutated"] is True, "le cast LIVE n'a pas mordu (hors tour ?) -- montage invalide"
    assert r["ported"] is True and len(r["spawned"] or []) == 1, (
        "le summon n'a pas ete spawne offline : %s" % (r,))
    assert r["live_victim"] == low, (
        "le NATIF devait frapper %s (petit maxHP), mesure : %s" % (low, r["live_victim"]))
    assert r["off_target_vis"] == low, (
        "le PORT frappe %s la ou le natif frappe %s -- le choix de cible n'est pas celui du moteur"
        " d'utilite" % (r["off_target_vis"], low))
    assert r["off_target_vis"] != r["nearest_vis"], (
        "le port a elu la cible du RACCOURCI (%s) : `_nearest_enemy` est revenu" % r["nearest_vis"])


def test_swapping_the_max_hp_swaps_the_victim(ai_target_choice_case):
    """CONTRE-EPREUVE -- meme geometrie, `maxHP` ECHANGES : la victime bascule sur l'AUTRE ennemi.

    C'est ce test qui interdit la lecture paresseuse « le port frappe le bon par hasard » : la
    geometrie est identique au regime precedent (memes tuiles, memes distances, memes ids), seul le
    `maxHP` change de camp -- et la cible SUIT, live comme offline.

    ⚠ Ce regime-ci n'est PAS discriminant, et il ne peut pas l'etre : le petit `maxHP` y porte le
    petit `id`, donc raccourci et moteur d'utilite tombent d'accord. C'est justement ce qui en fait
    une contre-epreuve et non une garde -- il etablit la BASCULE, le test precedent etablit le
    choix."""
    other = P.ENEMY_VIS[0]
    r = ai_target_choice_case(other)
    assert r["live_mutated"] is True, "le cast LIVE n'a pas mordu (hors tour ?) -- montage invalide"
    assert r["live_victim"] == other, (
        "le NATIF devait basculer sur %s, mesure : %s" % (other, r["live_victim"]))
    assert r["off_target_vis"] == other, (
        "le PORT n'a pas bascule avec le maxHP : %s" % r["off_target_vis"])
