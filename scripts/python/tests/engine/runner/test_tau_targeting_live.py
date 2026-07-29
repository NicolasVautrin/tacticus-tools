"""#250 -- GARDE des masques de ciblage des CINQ abilities du module `tau`.

  id    ability                   forme de ctor            rules effectives      TargetingRange
  ----  ------------------------  -----------------------  --------------------  -----------------
  1077  EarlyWarningOverride      3 PRESET STATIQUE COPIE  0x8004                statics+0x60 SELF
  1081  FightingRetreat           1 FLAGS DIRECTS          0x802                 statics+0x30 ADJ
  1082  InspiredToGreatness       1 FLAGS DIRECTS          0x402                 statics+0x30 ADJ
  1160  HeavyRailRifle            1 FLAGS DIRECTS          0x10400040004000      statics+0x48 BOARD
  1161  TwinSmartMissileSystem    1 FLAGS DIRECTS          0x40004000            statics+0x48 BOARD

1077 n'appelle AUCUN `IdunBattle.Core.Services.TargetingOptions$$.ctor` : son masque effectif est la
constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` =
`*(statics+0x2a8)`. 1160 et 1161 sortent de la MEME MoW (`tauBroadside`) et de la MEME forme de ctor
avec des masques DIFFERENTS. Detail complet : `docs/rl/case-250-tau-targeting.md`.

CE QUE CE TEST VERROUILLE, et pourquoi il ECHOUE sans les masques : sans `TARGETING_OPTIONS`,
`get_invalid_target_reason` rend 0 immediatement (`options is None` => aucun gate) et le moteur
ACCEPTE des casts que `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE. Le test
mesure sur le MEME etat fige le natif (oracle `abilityReason`), le port APRES et le port AVANT
(`TARGETING_OPTIONS = None`, l'etat de `master`), et exige par ability :
  1. accord natif/APRES sur toutes les lignes, SAUF les residus NOMMES (regle native que le port ne
     porte pas -- il rend alors 0, degradation permissive) ;
  2. au moins une ligne ou le natif REFUSE alors qu'AVANT rendait 0 ;
  3. les contrefactuels : le masque prive de ses REGLES, puis de son `TargetingRange`, faux-accepte
     bien des lignes -- un volet dont la neutralisation ne change RIEN n'est pas valide par la mesure.

Le montage (build MoW-capable + `MachineOfWarAmmo` patche hors `data/` + drive des positions) et les
trois lectures vivent dans `scripts/python/probe_250_tau_targeting.py` (le probe MESURE, ce test
GARDE) -- une seule implementation, aucune divergence possible entre les deux. UN SEUL runner pour
les cinq abilities (fixture de module). Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only.
"""
from __future__ import annotations

import pytest

import probe_250_tau_targeting as P

BOARD = "C4_09"      # MoW-capable (MachineOfWarPosition pose pour les DEUX camps)
SEED = 777


@pytest.fixture(scope="module")
def tau_measures(live_session):
    """UN SEUL runner pour les cinq abilities : le montage est identique, seul le caster change."""
    stats, dispose = P.measure_all(live_session, SEED, BOARD)
    try:
        yield stats
    finally:
        dispose()


def _one(stats, aid):
    s = stats.get(aid)
    assert s is not None, "ability %d non mesuree (porteur absent du plateau)" % aid
    assert s["usable"], (
        "%d non utilisable -> `AttackQuery.GetInvalidTargetReason` court-circuite sur "
        "`ActiveAbility.CanCurrentlyBeUsed` et rend 0x1 pour la MAUVAISE raison : rien de mesurable"
        % aid)

    # 1) ACCORD. Une ligne « residu » est un refus NATIF prononce par une regle que le port ne
    #    modelise pas (nommee dans `probe_250.CASES`), ou le port rend 0 : permissif, jamais un
    #    refus invente. Tout le reste doit s'accorder -- c'est CETTE assertion qui tombe si le
    #    masque disparait.
    mismatch = [(r["label"], hex(r["nat"] or 0), hex(r["apres"])) for r in s["rows"]
                if r["nat"] != r["apres"] and not (r["nat"] in s["residus_codes"]
                                                   and r["apres"] == 0)]
    assert not mismatch, "desaccord natif/port sur %d : %s" % (aid, mismatch)

    # 2) le masque SERT : au moins une ligne ou le natif REFUSE et ou `master` rendait 0.
    assert s["gain"] > 0, (
        "aucune ligne ou le masque de %d change le verdict -> ce test ne garderait rien "
        "(il passerait aussi sans `TARGETING_OPTIONS`)" % aid)
    return s


def test_1077_early_warning_override(tau_measures):
    """0x8004 = `CasterMatchesDynamicRule | CasterIsPossibleTarget` : AUCUN bit de refus du filtre
    CIBLE. C'est le `TargetingRange statics+0x60` = `RANGE_SELF` (`overrideRange = 0`) qui porte tout
    le refus -- l'ability est SELF, et toute cible autre que le caster rompt sur `TargetIsInRange`."""
    s = _one(tau_measures, 1077)
    assert s["cf_range"] > 0, (
        "neutraliser le `TargetingRange` de 1077 devrait faux-accepter des lignes : sans ca le volet "
        "PORTEE n'est pas valide par cette mesure")
    assert s["cf_rules"] == 0, (
        "les deux bits de 0x8004 ne sont PAS des regles de refus du filtre cible (bit 2 = volet "
        "CASTER non porte, bit 15 = flag declaratif) : neutraliser `rules` ne doit donc RIEN "
        "changer. Si ca change, la lecture du masque est fausse.")


def test_1081_fighting_retreat(tau_measures):
    """0x802 = `TargetMatchesDynamicRule | AddCasterIfAtLeastOneTarget` : aucun bit de camp
    (`refuses_all_enemy_targets` reste False), aucune regle statique. Le refus vient du
    `TargetingRange statics+0x30` = `RANGE_ADJACENT` -> `AreEntitiesAdjacent`."""
    s = _one(tau_measures, 1081)
    assert s["cf_range"] > 0, "le volet PORTEE de 1081 n'est pas exerce par cette mesure"
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import refuses_all_enemy_targets
    assert not refuses_all_enemy_targets(ABILITY_CLASSES[1081].TARGETING_OPTIONS), (
        "1081 ne porte NI TargetIsFriendly NI TargetIsCaster -> poser son masque ne doit deplacer "
        "aucun routage d'action cote IA")


def test_1082_inspired_to_greatness(tau_measures):
    """0x402 = `TargetMatchesDynamicRule | TargetIsFriendly` : le SEUL des cinq a porter une regle de
    CAMP. Les deux volets mordent -- `TargetIsFriendly` sur les ennemis, `RANGE_ADJACENT` sur les
    allies hors contact."""
    s = _one(tau_measures, 1082)
    assert s["cf_rules"] > 0, "le bit TargetIsFriendly de 1082 n'est pas exerce par cette mesure"
    assert s["cf_range"] > 0, "le volet PORTEE de 1082 n'est pas exerce par cette mesure"
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import refuses_all_enemy_targets
    assert refuses_all_enemy_targets(ABILITY_CLASSES[1082].TARGETING_OPTIONS), (
        "1082 porte TargetIsFriendly -> `refuses_all_enemy_targets` doit valoir True (l'ability "
        "soigne un ALLIE ; c'est le verdict natif que le masque manquant cachait)")


def test_1160_heavy_rail_rifle(tau_measures):
    """0x10400040004000 : `TargetIsEnemy` mord sur les allies et sur la MoW elle-meme. Le bit 46
    `TargetIsActor` ELARGIT le domaine -- la MoW ENNEMIE est une cible LEGALE."""
    s = _one(tau_measures, 1160)
    assert s["cf_rules"] > 0, "le bit TargetIsEnemy de 1160 n'est pas exerce par cette mesure"
    assert s["cf_range"] == 0, (
        "`RANGE_WHOLE_BOARD` -> le filtre statique NE TESTE AUCUNE portee : neutraliser le "
        "`TargetingRange` ne doit rien changer pour 1160")
    mow = [r for r in s["rows"] if "/MoW" in r["label"]]
    assert mow and all(r["nat"] == 0 for r in mow), (
        "le bit 46 `TargetIsActor` rend la MoW ENNEMIE legale pour 1160 : le natif doit l'ACCEPTER "
        "(c'est le seul discriminant vis-a-vis de 1161, meme porteur, meme forme de ctor) -- %s"
        % [(r["label"], hex(r["nat"] or 0)) for r in mow])


def test_1161_twin_smart_missile_system(tau_measures):
    """0x40004000 : MEME porteur et MEME `TargetingRange` que 1160, SANS le bit 46 -> une cible
    MACHINE rompt sur `TargetIsUnit` (bit 45, tete de domaine). Le contre-exemple qui interdit de
    generaliser un masque depuis sa voisine."""
    s = _one(tau_measures, 1161)
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    mow = [r for r in s["rows"] if "/MoW" in r["label"]]
    assert mow and all(r["nat"] == int(TR.TargetIsUnit) for r in mow), (
        "sans le bit 46, la MoW ENNEMIE doit rompre sur TargetIsUnit pour 1161 -- %s"
        % [(r["label"], hex(r["nat"] or 0)) for r in mow])
    assert s["cf_rules"] > 0, "le bit TargetIsEnemy de 1161 n'est pas exerce par cette mesure"
