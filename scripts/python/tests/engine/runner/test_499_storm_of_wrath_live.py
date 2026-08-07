"""GARDE #499 -- `1019 StormOfWrath` : la chaine `ChainAbilityDamage`, confrontee LIVE.

CE QUE CE FICHIER GARDE, ET POURQUOI CHAQUE TEST TOMBE POUR UNE RAISON DIFFERENTE
--------------------------------------------------------------------------------
Avant #499, `1019` etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, la decision pouvait
choisir le cast et l'execution l'ignorait -- 0 degat, 0 effet, AUCUNE erreur. La signature est
PERMISSIVE, donc invisible en self-play ; c'est exactement le trou qu'un entrainement irait
exploiter. Les tests ci-dessous ne se contentent pas de rejouer un scalaire :

  * `test_499_registre_offline` -- le cablage (registre + masque + `AbilityAttackType` + DISJONCTION
    avec `TARGETING_OPTIONS_UNPORTED`). Offline, instantane, et c'est lui qui rougirait si une
    future tranche re-cassait le contrat de source unique du masque.
  * `test_499_chaine_live` -- la chaine PROPAGE : 3 unites frappees la ou un port « ability =
    attaque mono-cible » n'en frapperait qu'une.
  * `test_499_coupe_live` -- MEME roster, MEME seed, maillons places HORS adjacence : **1 seule**
    unite. Le CARDINAL change avec la seule geometrie -> aucun forfait ne passe les deux.
  * `test_499_grappe_live` -- la cible a PLUSIEURS voisins : le `PickRandomly(cand, 1)` a un VRAI
    CHOIX a chaque saut. Sans ce test, l'accord de `chaine` serait DEGENERE (un seul candidat par
    pas) et ne prouverait RIEN du tirage ni de son ordre.
  * `test_499_psychic_bypasse_le_block_live` -- contre-epreuve NON VACUE : les cibles portent
    `BlockChance = 100` et PERSONNE ne bloque, ni le natif ni le port, parce que le profil `Psychic`
    porte le `DamageTrait.NoBlocking`. Le temoin `BlockChance > 0` est assertionne : sans lui,
    « aucun block observe » ne prouverait que le montage n'a rien arme.

Toute la mesure vit dans `probe_499_storm_of_wrath.py` (montage, cast live, rejeu offline depuis le
snapshot pre-cast avec le MEME etat de MT). Ce fichier ne fait que decider pass/fail. ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings

DECLENCHEUR = {
    "chemins": (
        # LARGE, ET C'EST UN RESULTAT (doctrine `declencheur_cliquet.py` : le doute se resout
        # TOUJOURS du cote large). Un cast confronte LIVE traverse le moteur Python ENTIER --
        # l'arbre DSL, les selecteurs, le PRNG, les operations de degat, le chargement d'etat --
        # plus son montage (`rl_duel`, `board.py`, `rl_collect_batch`). Un declencheur qui
        # enumererait la chaine attendue fabriquerait un FAUX VERT : le fichier ne serait pas rejoue
        # alors que son gisement vient de se rouvrir.
        # ⚠ LES DEUX GLOBS SONT NECESSAIRES : `scripts/python/**/*.py` exige un SEGMENT apres `**/`
        # et rate donc `scripts/python/board.py`, `rl_duel.py`, le probe lui-meme.
        "scripts/python/*.py",
        "scripts/python/**/*.py",
        # Entrees VERSIONNEES du montage : le seed BC et les boards.
        "data/seed-bc.json", "data/boards/**",
    ),
    # Le verdict compare le PORT au JEU : `minDmg`/`maxDmg`/`maxAdjacentTargets`/`damageProfile`
    # viennent du gameconfig du JEU, hors arbre -- un changement de build peut basculer le verdict
    # sans qu'un seul fichier du depot bouge.
    "build": True,
    "toujours": False,
    "raison": "Cast d'ability confronte LIVE : le perimetre reellement lu est le moteur Python "
              "entier (arbre DSL + selecteurs + PRNG + operations de degat + `snapshot.load_state`) "
              "plus le montage (`probe_499`, `rl_duel`, `board.py`, `rl_collect_batch`), d'ou les "
              "deux globs larges. `build: True` parce que les bornes de degat, le nombre de sauts "
              "et le profil sont lus dans le gameconfig du JEU.",
}

import probe_499_storm_of_wrath as SOW                    # noqa: E402

from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED   # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402

ABILITY = int(ActiveAbilityType.StormOfWrath)      # 1019

_CACHE: dict = {}


@pytest.fixture(scope="module")
def sow_case(live_session):
    """Un run de probe PAR REGIME, memoise : chaque regime monte son propre runner (le montage
    geometrique differe), et le meme regime n'est jamais paye deux fois."""
    def make(regime):
        if regime not in _CACHE:
            _CACHE[regime] = SOW.run(regime=regime)
        r = _CACHE[regime]
        if r.get("error"):
            pytest.skip("montage %s indisponible: %s" % (regime, r["error"]))
        return r
    return make


# ------------------------------------------------------------------ cablage (offline, instantane)

def test_499_registre_offline():
    """Le CABLAGE complet -- c'est ce qui ferme le no-op silencieux, et la DISJONCTION des deux
    sources de masque (un masque declare aux DEUX endroits a deja rendu `master` rouge)."""
    assert ABILITY in ABILITY_CLASSES, (
        "1019 absente d'ABILITY_CLASSES = NO-OP SILENCIEUX : la decision caste, l'execution ignore")
    cls = ABILITY_CLASSES[ABILITY]
    assert cls.TARGETING_OPTIONS is not None, (
        "TARGETING_OPTIONS absent -> `get_invalid_target_reason` rend 0 sans aucun gate")
    assert int(cls.TARGETING_OPTIONS.rules) == int(TR.TargetIsEnemy), (
        "rules != TargetIsEnemy : le ctor natif passe le litteral 0x4000 et RIEN d'autre")
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED, (
        "1019 declare son masque aux DEUX endroits -- le contrat de disjonction est CASSE")
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == int(AbilityAttackType.DirectTargetAttack), (
        "AbilityAttackType != le 3e argument LU d'`AActiveAbility$$.ctor` (litteral 0)")


# ------------------------------------------------------------------ les regimes LIVE

def test_499_chaine_live(sow_case):
    """La chaine PROPAGE : cible + maillons adjacents, per-coup bit-exact live vs port."""
    r = sow_case("chaine")
    assert r["diag"].get("ported") is True, "1019 non routee par le handler: %s" % r["diag"]
    lc, oc = SOW.counts(r["live"]), SOW.counts(r["off"])
    print("\n[499 chaine] cible=u%s maillons=%s live=%s" % (r["target"], r["links"], lc))
    assert len(lc) >= 3, (
        "la chaine n'a frappe que %d unite(s) : un port mono-cible rendrait exactement 1" % len(lc))
    assert set(lc) == {r["target"], *r["links"]}, (
        "ensemble frappe %s != cible+maillons %s" % (sorted(lc), sorted([r["target"], *r["links"]])))
    assert oc == lc, "coups OFFLINE %s != LIVE %s" % (oc, lc)
    assert r["off"] == r["live"], (
        "per-coup OFFLINE != LIVE\noff =%s\nlive=%s" % (r["off"], r["live"]))


def test_499_coupe_live(sow_case):
    """CONTRE-CAS : maillons hors adjacence -> UNE seule unite frappee. C'est le cardinal qui
    change avec la geometrie ; un forfait « N unites » ne peut pas passer ce test ET le precedent."""
    r = sow_case("coupe")
    assert r["diag"].get("ported") is True, "1019 non routee par le handler: %s" % r["diag"]
    lc, oc = SOW.counts(r["live"]), SOW.counts(r["off"])
    print("\n[499 coupe] cible=u%s exiles=%s live=%s" % (r["target"], r["exiled"], lc))
    assert lc == {r["target"]: 1}, (
        "sans voisin adjacent la chaine ne peut PAS partir : LIVE %s != {cible: 1}" % lc)
    assert oc == lc, "coups OFFLINE %s != LIVE %s" % (oc, lc)
    assert r["off"] == r["live"], (
        "per-coup OFFLINE != LIVE\noff =%s\nlive=%s" % (r["off"], r["live"]))


def test_499_grappe_live(sow_case):
    """REGIME NON DEGENERE du tirage : la cible a >= 2 voisins, donc `PickRandomly(cand, 1)` a un
    VRAI choix a chaque saut. L'ORDRE des maillons est celui du tirage -- s'il divergeait, le flux
    RNG aval divergerait aussi et les valeurs ne colleraient plus."""
    r = sow_case("grappe")
    assert r["diag"].get("ported") is True, "1019 non routee par le handler: %s" % r["diag"]
    assert len(r["links"]) >= 2, (
        "pool de candidats de taille %d : le tirage serait DEGENERE, ce test ne prouverait rien"
        % len(r["links"]))
    lc, oc = SOW.counts(r["live"]), SOW.counts(r["off"])
    order_live = [t for t, _a in r["live"]]
    order_off = [t for t, _a in r["off"]]
    print("\n[499 grappe] cible=u%s voisins=%s ordre live=%s" % (r["target"], r["links"], order_live))
    assert set(lc) == {r["target"], *r["links"]}, "ensemble frappe %s inattendu" % sorted(lc)
    assert order_off == order_live, (
        "ORDRE des maillons OFFLINE %s != LIVE %s -- le tirage `PickRandomly` diverge"
        % (order_off, order_live))
    assert r["off"] == r["live"], (
        "per-coup OFFLINE != LIVE\noff =%s\nlive=%s" % (r["off"], r["live"]))


def test_499_psychic_bypasse_le_block_live(sow_case):
    """CONTRE-EPREUVE NON VACUE : `--block-target 100,500` arme un block a 100 % sur les cibles, et
    PERSONNE ne bloque -- ni le natif ni le port -- parce que le profil de 1019 est `Psychic`, qui
    porte `DamageTrait.NoBlocking` (`AttackDamageOperation._block_sources`, gate #65, mirror
    d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`).

    Le temoin `BlockChance > 0` est ASSERTIONNE : sans lui, « aucun block observe » serait un vert
    qui ment (le montage aurait pu ne rien armer du tout)."""
    r = sow_case("block")
    assert r["diag"].get("ported") is True, "1019 non routee par le handler: %s" % r["diag"]
    bc = r["block_chance"]
    print("\n[499 block] BlockChance=%s live=%s" % (bc, SOW.counts(r["live"])))
    assert bc and all((v or 0) > 0 for v in bc.values()), (
        "BlockChance des cibles = %s : le montage n'a RIEN arme, la contre-epreuve serait vide" % bc)
    blocked = [a for a in ([r["diag"].get("main_attack")]
                           + [c.get("attack") for c in (r["diag"].get("chain") or [])])
               if isinstance(a, dict) and a.get("did_block")]
    assert not blocked, (
        "le port a BLOQUE alors que `Psychic` porte NoBlocking : %s" % blocked)
    assert r["off"] == r["live"], (
        "per-coup OFFLINE != LIVE sous block arme\noff =%s\nlive=%s" % (r["off"], r["live"]))
