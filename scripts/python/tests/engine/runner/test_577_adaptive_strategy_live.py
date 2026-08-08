"""GARDE LIVE #577 -- le cast d'`AdaptiveStrategy` (1005, `necroWarden`) CONFRONTE au natif.

LE CRITERE, en une question binaire : **apres un cast de 1005, l'allie NON-Hero adjacent a-t-il
AGI ?** -- posee au NATIF et au PORT sur le MEME etat de depart. Avant ce port, 1005 etait absente
d'`ABILITY_CLASSES` : `AbilityHandler` l'ignorait, donc le port repondait « non » -- 0 degat,
0 effet, AUCUNE erreur.

Le montage vit dans `scripts/python/probe_577_adaptive_strategy.py` (`run()`) ; ce fichier n'est que
sa PORTE pytest, comme `test_366_r1_tunneling_horror_live.py` pour le sien.

⚠ Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268). Seule l'indisponibilite du
HARNAIS skippe, et c'est `live_session` qui la porte.

RE + les mesures : `docs/rl/case-577-adaptive-strategy.md`. ASCII only, aucune VA en dur.
"""
from __future__ import annotations

import pytest

import probe_577_adaptive_strategy as P

# Ce fichier est la PORTE pytest d'un probe qui monte un runner et confronte le port au natif : son
# verdict depend de l'arbre de 1005, de CHACUNE des cinq feuilles DSL qu'il compose, du gate de
# ciblage, du chargement d'etat -- et du mirror de `RelentlessMarch`, que le noeud (1) re-declenche.
# Le glob `engine/**` couvre la FERMETURE (un `ImportError` chez n'importe quel frere du paquet
# change le verdict d'ici) ; `toujours: True` repare la SELECTION, les deux crans sont
# INDEPENDANTS.
DECLENCHEUR = {
    "chemins": (
        # LE MONTAGE lui-meme -- le probe et la voie de build/RPC qu'il emprunte.
        "scripts/python/probe_577_adaptive_strategy.py",
        "scripts/python/rl_duel.py",
        "scripts/python/rl_collect_batch.py",
        "scripts/python/gameconfig.py",
        "scripts/python/hexgeo.py",
        # LES FOYERS SOUS TEST, nommes -- ils sont DEJA dans le glob ci-dessous, et c'est
        # deliberement redondant : un lecteur doit voir CE que ce fichier garde sans derouler un
        # glob de 400 chemins.
        "scripts/python/engine/runner/abilities/necrons.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/runner/abilities/behaviours/ai_control.py",
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        "scripts/python/engine/runner/abilities/behaviours/stats.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/operations/summon_ai.py",
        "scripts/python/engine/runner/operations/triggers/loki/relentless_march.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/dsl/base.py",
        # LA FERMETURE. Le probe importe `engine.*` par une dizaine de portes (snapshot, runner,
        # messages, selecteurs, formules, effets) : les nommer une a une serait TROP ETROIT, et
        # trop etroit est un FAUX VERT.
        "scripts/python/engine/**",
        # Les ENTREES versionnees que le build et le chargement d'etat lisent.
        "data/boards/**",
        "data/seed-bc.json",
    ),
    # Le port est un MIRROR d'un corps natif : toute migration de build peut deplacer l'arbre de
    # `...AdaptiveStrategyAbility$$ExecuteBehaviour`, le masque de son `.ctor`, ou les ordinaux des
    # trois enums cites (`EffectType` 1012/1011, `TriggeredAbilityType` 1004). Le verdict d'ici
    # change alors SANS qu'aucun fichier du depot n'ait bouge.
    "build": True,
    "toujours": True,
    "raison": (
        "Garde LIVE : son verdict depend AUSSI de l'etat du harnais (session Frida, runner, "
        "seed BC) et du BUILD du jeu, qu'aucun chemin du depot ne represente. Un declencheur "
        "purement statique serait donc trop ETROIT."
    ),
}

ADAPTIVE = 1005
OVERRIDE = 1012          # EffectType.AdaptiveStrategy_DmgOverride
MARCH_EFFECT = 1011      # EffectType.RelentlessMarch_Effect


@pytest.fixture(scope="module")
def adaptive_case(live_session):
    """Le montage, UNE fois pour tout le fichier (un build + un cast live). Le runner est DISPOSE
    par `run()` en sortie, donc rien a liberer au teardown."""
    return P.run()


def test_the_non_hero_ally_acts_on_both_sides(adaptive_case):
    """LA question binaire. Le noeud (3) `PerformAIAction(..., resetTurnFlags: 1)` doit faire AGIR
    le summon -- MEME s'il avait deja fini son tour (`SpawnUnitBehaviour$$
    TriggerSpawnedUnitBehaviours` appelle `FinishUnitTurn(spawned, isTerminated: true)` a son
    apparition). Un port qui aurait oublie ce booleen rendrait un no-op silencieux."""
    c = adaptive_case
    s = c["summon"]
    origin = (c["before"].get(s) or {}).get("pos")
    assert origin is not None, "montage: le summon n'etait pas sur le plateau AVANT"
    assert (c["native"].get(s) or {}).get("pos") != origin, (
        "le NATIF n'a pas fait agir le summon (toujours en %r)" % (origin,))
    assert (c["port"].get(s) or {}).get("pos") != origin, (
        "le PORT n'a pas fait agir le summon -- le noeud (3) est reste un no-op : %r"
        % (c["port"].get(s),))


def test_the_hero_gate_discriminates(adaptive_case):
    """E1 -- `GetDynamicInvalidTargetReason` = `HasTrait(target, Hero) ? 2 : 0`. Le summon NON-Hero
    est une cible legale ; l'allie HERO adjacent ne l'est PAS. Sans ce SECOND bras, le gate pourrait
    tout accepter sans qu'aucun test ne rougisse."""
    c = adaptive_case
    assert c["summon"] in c["legal"], (
        "le summon %r n'est pas une cible legale de 1005 (legales=%r)" % (c["summon"], c["legal"]))
    assert not [f for f in c["fails"] if f.startswith("E1")], (
        "le gate `HasTrait(Hero)` ne discrimine pas : %r" % (c["fails"],))


def test_the_stat_override_is_net_zero_on_both_sides(adaptive_case):
    """E3 -- le noeud (4) `RemoveEffect(everyone, 1012)` retire ce que le noeud (2) a pose : APRES
    le cast, plus AUCUN porteur d'`AdaptiveStrategy_DmgOverride`, des deux cotes. Un override
    laisse colle serait une unite dont l'Attack reste ecrasee pour le reste de la bataille.

    ⚠ Ce `[]`-la est une MESURE, et il a fallu le prouver : la premiere version du probe
    interrogeait `decisionView.effects` (un champ INEXISTANT -- le canal est
    `decisionView.units[].effects`), donc elle rendait `[]` par IGNORANCE. C'est le temoin non nul
    (`native_effect_census`) qui l'a montre, et il tourne toujours."""
    c = adaptive_case
    assert c["nat_carriers"] == [], "le NATIF garde 1012 sur %r" % (c["nat_carriers"],)
    assert c["port_carriers"] == [], (
        "le PORT garde 1012 sur %r -- le noeud (4) n'a pas nettoye" % (c["port_carriers"],))


def test_port_and_native_agree_term_by_term(adaptive_case):
    """La confrontation complete -- `run()` accumule les ecarts dans `fails` (ce test les REND, il
    ne les re-derive pas : le montage est la source unique). Y sont compris le `hp` des trois
    unites (le canal qui porte le `Repair` du re-trigger `RelentlessMarch`, a l'unite pres) et
    l'IMPUTATION mesuree de l'ecart de tuile."""
    c = adaptive_case
    assert c["fails"] == [], "ECARTS port <-> natif : %r" % (c["fails"],)


def test_the_ability_actually_executed_offline(adaptive_case):
    """ANTI-TAUTOLOGIE. Les tests precedents comparent deux etats ; ils seraient VERTS aussi si le
    port n'avait RIEN execute et que le natif n'avait rien fait non plus. On exige donc que
    l'execution ait EU LIEU cote port : ability trouvee au registre (`ported: True`), gate de cible
    NON declenche, un override POSE, une action JOUEE sur le summon, et le re-trigger DISPATCHE."""
    c = adaptive_case
    last = c["last"]
    assert last.get("ported") is True, "1005 non executee offline : %r" % (last,)
    assert "invalid_target" not in last, "cast refuse par le gate de cible : %r" % (last,)
    assert last.get("overrides"), "aucun `AddStatOverrideEffect` emis : %r" % (last,)
    acts = [int(x) for x in ((last.get("actions") or {}).get("units") or [])]
    assert c["summon"] in acts, (
        "le summon %r n'est pas dans les cibles de `PerformAIAction` (%r)" % (c["summon"], acts))
    rt = last.get("retriggered") or {}
    assert rt.get("dispatched") is True, (
        "le noeud (1) n'a pas DISPATCHE `RelentlessMarch` : %r -- la branche `Custom` n'a donc "
        "toujours aucun appelant porte (residu #328 section 3)" % (rt,))
    assert not rt.get("notCarrying"), (
        "le caster a ete ECARTE par le gate `GetAbilityState` : %r" % (rt,))
