"""#441 -- la sortie de `Neuroparasite` (1183) dans le `pairUtility`, confrontee au NATIF.

`IdunBattle.AI.Playbook.Loki.NeuroparasitePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`
n'a que DEUX sorties -- `Fix64.op_Implicit(1)` quand la CIBLE porte l'effet `Neuroparasite`
(EffectType 1218 = 0x4c2), `Fix64.op_Implicit(0)` sinon. Il entre dans la face ATTACK du dispatcher
`TriggeredAbilitiesUtility(2)`, donc DANS le terme de paire -- directement confrontable a l'oracle.

CE QUE CE TEST GARDE -- quatre choses :

  1. **NON-DEGENERESCENCE + ANTI-CONFOND TEMPOREL** -- le regime « infecte » n'existe PAS au
     deploiement : il se CONSTRUIT (le Neurothrope tire, l'arme psychique pose le parasite). Le
     montage mesure donc la MEME cible AVANT et APRES, et exige qu'elle change de regime. Sans ca,
     port et natif rendraient tous deux 0 partout -- d'accord pour rien.
  2. **CONFORMITE** -- pour chaque phase et chaque cible, l'utilite de paire du port
     (`ComparablePlaybook.calculate_action_utility(...)["u"]`) egale celle du NATIF (RPC
     `pairUtility`), depuis la MEME tuile.
  3. **DISCRIMINANCE** -- playbook 1183 RETIRE du registre, le port DOIT perdre EXACTEMENT 1.0 sur
     la cible infectee et RIEN sur les saines. Un port qui verserait le terme inconditionnellement
     passerait (2) sur l'infectee et tomberait ici.
  4. **QUALIFICATION DE L'ENUM** (`test_neuroparasite_reads_the_effect_not_the_ability`) -- `1183`
     est le `TriggeredAbilityType` (l'ability) et `1218` l'`EffectType` (le parasite pose sur la
     victime). Le corps natif lit l'EFFET. La garde verifie que la feuille discrimine bien sur
     1218, et qu'AUCUNE cible ne porte un effet `1183` -- un port qui aurait confondu les deux
     rendrait 0 partout. Elle verifie AUSSI que la feuille verse son terme SANS `prediction` :
     contrairement a `BarbedOvipositor` (#438), ce corps ne lit pas `UtilityAttackCase@+0x28`.

Le montage EXIGE les deux regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268).
Les deux cibles sont ECARTEES d'au moins 4 tuiles : MESURE -- adjacentes, le tir en infecte DEUX et
le temoin sain disparait.

Porteur : `tyranNeurothrope` (HERO au pool ; 6 npc portent 1183 aussi).
ASCII only. Probe jumeau : `scripts/python/probe_441_neuroparasite_pair_term.py`.
"""
from __future__ import annotations

import pytest

import probe_441_neuroparasite_pair_term as P441

EPS = P441.EPS


@pytest.fixture(scope="module")
def np_case(live_session, rpc, build_runner):
    """Un runner : placement ECARTE, tir d'amorcage, re-armement de l'action, attestation des deux
    regimes des DEUX cotes (canal `decisionView` natif ET `battle_query.scene_has_effect` du port).

    Tout le montage vit dans `probe_441_neuroparasite_pair_term` -- cette fixture n'en est que la
    porte pytest. Un `MontageError` devient un ECHEC, jamais un skip."""
    try:
        rid = build_runner(P441.SEED, P441.BUILD_ARGS)["rid"]
        return P441.build_case(live_session, rpc, rid)
    except P441.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def np_rows(np_case, rpc):
    return P441.measure(rpc, np_case)


def test_neuroparasite_covers_both_regimes(np_rows):
    """(1) NON-DEGENERESCENCE + ANTI-CONFOND TEMPOREL : les deux sorties natives sont installees,
    et c'est bien la MEME cible qui change de regime entre les deux phases."""
    seen = {(r["phase"], r["target"], r["infected"]) for r in np_rows}
    assert {r["infected"] for r in np_rows} == {True, False}, (
        f"un seul regime couvert -- port et natif seraient d'accord pour rien : {seen}")
    before = {r["target"]: r["infected"] for r in np_rows if r["phase"] == "before"}
    after = {r["target"]: r["infected"] for r in np_rows if r["phase"] == "after"}
    assert before == {P441.TGT_INFECT: False, P441.TGT_CLEAN: False}, (
        f"une cible portait deja l'effet {P441.EFFECT} avant l'amorcage : {before}")
    assert after == {P441.TGT_INFECT: True, P441.TGT_CLEAN: False}, (
        f"apres l'amorcage, {P441.TGT_INFECT} doit etre infectee et {P441.TGT_CLEAN} saine : "
        f"{after}")


def test_neuroparasite_pair_term_matches_native(np_rows):
    """(2) CONFORMITE : port == natif sur les deux phases et les deux cibles."""
    assert np_rows, "aucune mesure produite -- le montage n'a rien confronte"
    for r in np_rows:
        assert abs(r["native"] - r["port"]) < EPS, (
            f"pairUtility != natif en phase {r['phase']} sur {r['target']} "
            f"(infecte={r['infected']}) : natif={r['native']} port={r['port']} "
            f"ecart={r['port'] - r['native']}")


def test_neuroparasite_term_is_load_bearing(np_rows):
    """(3) DISCRIMINANCE : playbook 1183 RETIRE -> le port perd EXACTEMENT 1.0 sur la cible
    infectee, et RIEN sur les saines."""
    assert {r["expected"] for r in np_rows} == {0.0, P441.EXPECTED_INFECTED}, (
        f"les deux niveaux de terme (0 / {P441.EXPECTED_INFECTED}) ne sont pas tous attendus par "
        f"la mesure : {[(r['phase'], r['target'], r['expected']) for r in np_rows]}")
    for r in np_rows:
        got = r["native"] - r["port_muted"]
        assert abs(got - r["expected"]) < EPS, (
            f"sans le playbook 1183, l'ecart au natif en phase {r['phase']} sur {r['target']} "
            f"(infecte={r['infected']}) devrait valoir exactement {r['expected']} : "
            f"natif={r['native']} port_mute={r['port_muted']} ecart={got}")


def test_neuroparasite_ignores_effect_level(np_case, np_rows, live_session, rpc):
    """(5) GENERALISATION -- le corps natif fait un `HasEffect` BINAIRE : il ne lit PAS
    `EffectLevel`. Le terme doit donc valoir EXACTEMENT 1.0 aux niveaux 1, 2, 3 du parasite.

    La mesure est discriminante parce que l'utilite TOTALE, elle, bouge fortement d'un niveau a
    l'autre (`NeuroparasiteEffect$$CreateEffectDamageMalusForDefense` MULTIPLIE son additif par
    `EffectLevel`) : un port qui aurait lu le niveau au lieu de la presence divergerait de 1, 2,
    3... et cette garde le verrait. `escalate` ECHOUE si le niveau ne monte pas -- une contre-
    epreuve qui ne mord pas ne prouve rien.

    Depend de `np_rows` pour que les mesures `before`/`after` soient prises AVANT que ce test ne
    fasse avancer la bataille (l'ordre des fixtures fige la phase, pas l'ordre des tests)."""
    assert np_rows, "les phases before/after doivent avoir ete mesurees avant l'escalade"
    rows = P441.measure_levels(live_session, rpc, np_case, levels=3)
    lvls = sorted({r["phase"] for r in rows})
    assert len(lvls) == 3, f"trois niveaux distincts attendus, mesures : {lvls}"
    for r in rows:
        assert abs(r["native"] - r["port"]) < EPS, (
            f"pairUtility != natif au niveau {r['phase']} sur {r['target']} : "
            f"natif={r['native']} port={r['port']}")
        got = r["native"] - r["port_muted"]
        assert abs(got - r["expected"]) < EPS, (
            f"au niveau {r['phase']}, le terme de 1183 sur {r['target']} (infecte="
            f"{r['infected']}) vaut {got} au lieu de {r['expected']} : le corps natif ne lit PAS "
            f"`EffectLevel`, il teste la seule PRESENCE de l'effet")


def test_neuroparasite_reads_the_effect_not_the_ability(np_case):
    """(4) QUALIFICATION DE L'ENUM + INDEPENDANCE DE LA PREDICTION.

    `1183` est le `TriggeredAbilityType` (l'ability du Neurothrope) et `1218` l'`EffectType` (le
    parasite pose sur la victime) : le corps natif lit l'EFFET. La garde vise le FOYER
    (`engine.utilities.tile.triggered_abilities_attack_utility`) et verifie, en phase `after` :
      - qu'AUCUNE cible ne porte un effet `1183` -- donc un port qui aurait confondu les deux
        enums rendrait 0 sur les deux cibles et tomberait ici ;
      - que la feuille rend 1.0 sur l'infectee et 0.0 sur la saine ;
      - qu'elle le fait SANS `prediction` : ce corps ne lit que `case@+0x20` (la cible), jamais
        `case.DamagePrediction` (`UtilityAttackCase@+0x28`) -- l'inverse exact de #438."""
    from engine import battle_query as bq
    from engine.utilities.tile import triggered_abilities_attack_utility

    ctx, cid, tile, ab = np_case["ctx"], np_case["cid"], np_case["tile"], np_case["ab"]
    for vis, uid in np_case["tgt"].items():
        assert not bq.scene_has_effect(ctx.scene, uid, P441.ABILITY), (
            f"{vis} porte un effet {P441.ABILITY} : l'enum n'est plus discriminant, ce test ne "
            f"prouverait plus que le port lit bien l'EffectType {P441.EFFECT}")
        expected = P441.EXPECTED_INFECTED if vis == P441.TGT_INFECT else 0.0
        got = triggered_abilities_attack_utility(ctx, cid, ab, uid, tile)
        assert abs(got - expected) < EPS, (
            f"la feuille TriggeredAbilities(2) FACE ATTACK rend {got} sur {vis} (infectee="
            f"{vis == P441.TGT_INFECT}) alors qu'elle doit rendre {expected}, SANS prediction")
