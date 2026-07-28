"""#159 (a) -- BORNES COMBAT du canal #179 pour un descripteur a DEUX noeuds de degat.

QUESTION (binaire) : quand un descripteur de coups additionnels porte un noeud ROLL et un noeud
DISPLAY DISTINCTS, la face COMBAT tire-t-elle dans le noeud ROLL (`RandomAmount(min, max)`) ou
dans le noeud DISPLAY etale a +-20 % (`Average(min, max) +- 20 %`) ?

RE (decompile = verite, gqfc5mff6c) -- `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits
(this, entities, useDisplay)`, lu verbatim :

    if (!d.condition.ShouldTrigger(entities))  return default          # slot 5
    count  = d.countNode != null ? d.countNode.Calculate(entities) : 1 # +0x18, slot 1
    amount = d.minNode.<slot 4>(entities)                              # +0x10  noeud DISPLAY
    min = max = amount
    if (!useDisplay) {                                                 # <- FACE COMBAT
        min = d.amountNode.<slot 2>(entities)                          # +0x08  noeud ROLL
        max = d.amountNode.<slot 3>(entities)
    }

et `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`
appelle `IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsFromEffectsInternal`
avec l'octet **EXPLICITEMENT MIS A ZERO** (`in_stack & 0xffffff00`) => `useDisplay = false`.
`IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsData` bat ensuite l'AttackData
par `IdunBattle.Core.HitDamage$$.ctor(min, Nullable(max))` depuis ce MinMaxDamage.

Pour `FleshmetalGuns` les deux noeuds sont DISTINCTS et sortent du meme helper
`IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, useAverage, keyMin, keyMax)` :

    a = ConfigVar(keyMin, AbilityStateFromEffect(...)) ; b = ConfigVar(keyMax, ...)
    return useAverage ? DSLFactory.Average(a, b) : DSLFactory.RandomAmount(a, b)

`IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$CreateAdditionalHits` l'appelle DEUX
fois (`0` -> param_3 = noeud ROLL ; `1` -> param_8 = noeud DISPLAY).

MONTAGE : `blackObliterator` (Volk) attaque a DISTANCE (le trigger du canal est `IsRangedAttack`)
une cible TEMOIN `necroWarden` (aucun trait mordant le canal de coups). La variante active du
cycle est pilotee par `UnitTurnsStarted(Self) mod 3`
(`IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour`) :
1 -> Melta, 2 -> Flame, 0 -> **WarpHail**, dont la paire [minDmg_3, maxDmg_3] est ASYMETRIQUE
autour de sa moyenne -> c'est la variante qui DISCRIMINE le plus franchement les deux modeles
(a mult 180 : natif [698, 1096] largeur 399 vs display-spread [718, 1076] largeur 359).

MESURE D'ORIGINE (`probe_159_ah_bounds.py`, flux RNG cale par `dumpRng`) : groupe live reproduit
**6/6** par les bornes ROLL et **0/6** par `amount +-20 %` sur WarpHail, **2/2** vs **0/2** sur
Melta -- 8/8 montages discriminants. Cf. `docs/rl/case-159-rng-canal179-et-maybe-ltgb.md`.

⚠ Le canal LetTheGalaxyBurn (`LetTheGalaxyBurnEffect$$CreateAdditionalHits`) reste porte dans la
FORMULE DE COUPS et non dans ce canal-ci (residu #159 (b), chiffre dans la case-doc) : quand son
`Maybe(33)` arme, le port emet un coup d'ARME de plus la ou le natif emet un groupe #179 a cellule
DEGENEREE. La garde ancre donc sur le GROUPE, pas sur le nombre de coups d'arme, et n'exige
l'egalite des coups d'arme que lorsque le `Maybe` n'a PAS arme (meme nombre de coups des 2 cotes).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
from probe_159_ah_bounds import (_bounds_variant, _board, _drive_ranged,   # noqa: E402
                                 _replay, CARRIER, DEFAULT_TARGET)
from probe_r6_round_materialize import _build, _live_amounts        # noqa: E402

# Seeds MESURES discriminants sur les deux variantes (cf. en-tete).
WARPHAIL_SEEDS = ["777", "12345", "31337"]
MELTA_SEEDS = ["12345"]


def _one(rpc, seed, variant):
    """Monte le montage, attaque LIVE, et rend `(groupe_live, groupe_shipped, groupe_display)`."""
    rid, sf = _build(seed, CARRIER, DEFAULT_TARGET,
                     extra=["--crit", "0,0", "--block-target", "0,0", "--hp-target", "90000"])
    if rid is None:
        pytest.skip("build KO")
    try:
        cid, tid, moved, nrm = _drive_ranged(rpc, rid, variant, DEFAULT_TARGET, max_turns=40)
        if cid is None:
            pytest.skip(f"cycle {variant} / portee non atteints ({nrm})")
        board = _board(rpc, rid)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not (isinstance(rng0, dict) and rng0.get("mt")):
            pytest.skip("dumpRng indispo")
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid,
            "abilityType": nrm}, "captureEvents": True}, 120)
        live, dirty = _live_amounts(res, tid)
        if dirty:
            pytest.skip("coup non propre (crit/block/evade)")
        off = _replay(dv, ob, snap, board, rng0, cid, tid, moved)
        arme_s, grp_s, bnd_s, _n, _c = off["shipped"]
        _ad, grp_d, _bd, _nd, _cd = off["display"]
        k = len(arme_s)
        return {"live": live, "arme": arme_s, "k": k, "grp_live": live[k:k + len(grp_s)],
                "grp_shipped": grp_s, "grp_display": grp_d, "bounds": bnd_s}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


@pytest.mark.parametrize("seed", WARPHAIL_SEEDS)
def test_additional_hits_roll_node_bounds_live(live_session, rpc, seed):
    """RATCHET + DISCRIMINATION sur la variante ASYMETRIQUE (WarpHail)."""
    r = _one(rpc, seed, "WarpHail")
    print(f"\n[#159a WarpHail] seed={seed} live={r['live']} arme={r['arme']}")
    print(f"[#159a WarpHail] bornes={r['bounds']} shipped={r['grp_shipped']} "
          f"display={r['grp_display']} grp_live={r['grp_live']}")
    assert r["grp_shipped"], "aucun coup du canal #179 rejoue offline (l'effet du cycle est-il pose ?)"
    assert len(r["live"]) > r["k"], f"aucun event live apres les {r['k']} coups d'arme"
    b = (r["bounds"] or [{}])[0]
    # (0) le descripteur DOIT porter les DEUX noeuds -- sinon la face COMBAT retombe sur le spread.
    assert b.get("min") is not None and b.get("max") is not None, (
        f"le descripteur FleshmetalGuns ne porte pas ses bornes du noeud ROLL ({b}) : "
        "`_BaseFleshmetalGunsEffect.additional_hit_groups` rend-il encore `amount` SEUL ?")
    # (1) le montage DOIT discriminer, sinon la garde ne prouve rien.
    assert r["grp_shipped"] != r["grp_display"], (
        f"seed {seed} : groupe NON discriminant (les deux modeles donnent {r['grp_shipped']}) -- "
        "re-selectionner la seed avec `probe_159_ah_bounds.py`.")
    # (2) le natif tire dans le noeud ROLL.
    assert r["grp_shipped"] == r["grp_live"], (
        f"le port LIVRE ne reproduit pas le groupe : shipped={r['grp_shipped']} "
        f"live={r['grp_live']} (display={r['grp_display']}) -- la face COMBAT lit-elle encore "
        "`amount` au lieu de `min`/`max` dans `execute_additional_hits` ?")
    # (3) DISCRIMINATION : le modele DISPLAY (le port d'avant #159) doit ECHOUER.
    assert r["grp_display"] != r["grp_live"], (
        f"le modele `amount +-20 %` reproduit AUSSI le live ({r['grp_display']}) : garde AVEUGLE.")


@pytest.mark.parametrize("seed", MELTA_SEEDS)
def test_additional_hits_roll_node_bounds_symmetric_variant_live(live_session, rpc, seed):
    """2e VARIANTE (Melta) -- paire quasi symetrique autour de sa moyenne : le montage teste que le
    fix tient AUSSI la ou l'ecart entre les deux modeles est FAIBLE (largeur 500 vs 499), regime ou
    un fix « ajuste au scalaire » sur WarpHail se serait trahi."""
    r = _one(rpc, seed, "Melta")
    print(f"\n[#159a Melta] seed={seed} bornes={r['bounds']} shipped={r['grp_shipped']} "
          f"display={r['grp_display']} grp_live={r['grp_live']}")
    assert r["grp_shipped"], "aucun coup du canal #179 rejoue offline"
    assert r["grp_shipped"] == r["grp_live"], (
        f"variante Melta : shipped={r['grp_shipped']} live={r['grp_live']} "
        f"(display={r['grp_display']})")


@pytest.mark.parametrize("seed", ["12345"])
def test_weapon_hits_bit_exact_when_maybe_not_armed_live(live_session, rpc, seed):
    """GARDE DE FLUX : quand le `Maybe(33)` de `LetTheGalaxyBurn` n'arme PAS, les coups d'ARME sont
    bit-exacts -- c'est ce qui PROUVE que le flux RNG est aligne a l'entree du groupe, donc que la
    mesure du groupe porte bien sur les BORNES et pas sur un decalage de tirages.

    (Quand le `Maybe` arme, le port emet un coup d'ARME la ou le natif emet un groupe #179 a
    cellule degeneree : residu #159 (b), hors perimetre de cette garde.)"""
    r = _one(rpc, seed, "WarpHail")
    k = r["k"]
    print(f"\n[#159a flux] seed={seed} live_arme={r['live'][:k]} off_arme={r['arme']}")
    assert r["live"][:k] == r["arme"], (
        f"coups d'ARME desalignes (live={r['live'][:k]} off={r['arme']}) : le `Maybe` a-t-il arme "
        "d'un seul cote, ou un etage AMONT du degat a-t-il regresse ?")
