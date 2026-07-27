"""GARDE live des deux passifs ThousandSons portes : `RealityUnbound` (thousTzaangor) et le volet
REGEN de `TimeFlux` (thousTerminator).

Live-agreement ONLY (aucune fixture gelee) : chaque test monte son runner, joue la sequence et
confronte le port au NATIF. Les deux scenarios sont ceux des probes de mesure
(`probe_ru_reality_unbound.py`, `probe_tf_time_flux.py`) reduits a leur assertion DISCRIMINANTE,
dont le cas NEGATIF de chaque passif.

Ce qui est garde ici :
  * RealityUnbound / gate `>= 3` : Move(1205)+Range(1206) poses SSI au moins 3 ennemis DISTINCTS ont
    encaisse du Psychic dans le tour -- le temoin INDEPENDANT du seuil est l'effet 1185
    (`WeaverOfFate`, meme trigger natif `WeaverOfFateAbility$$GetTrigger`, mecanisme deja valide
    #202). C'est le CAS NEGATIF : a 2 ennemis, le stack ExtraMaxDamage monte mais 1205/1206 restent
    ABSENTS.
  * RealityUnbound / stack : la contribution EXTRA_MAX_DAMAGE vaut `ApplyCounter x Amount`
    (le natif empile par un COMPTEUR sur UNE entite-effet, pas par N entites) et `Amount` doit
    egaler la magnitude offline `ability_var('RealityUnbound','extraMaxDmg', level, mult)`.
  * TimeFlux / cas NEGATIF isole : un tour adverse SANS aucune action -> le regen du turn-start vaut
    `hpToHeal` EXACTEMENT (le terme `LastHitDamageTakenLastTurn` est bien remis a zero par le
    roulement `ActorStatistics@+0x6c -> @+0x70` de `StartTurnOperation$$ResetUnit`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.entities.effects.magnitude import ability_var          # noqa: E402
import probe_ru_reality_unbound as RU                              # noqa: E402
import probe_tf_time_flux as TF                                    # noqa: E402
from rl_collect_batch import _resolve_session                      # noqa: E402

SEED = 31337
LEVEL, MULT = 50, 180        # rank 17 : level 50, AbilityVariablesMultiplierPercentage 180


@pytest.fixture(scope="module")
def sid():
    return _resolve_session()


def test_reality_unbound_gate_three_and_stack(sid):
    """CAS NEGATIF + CAS POSITIF du gate `>= 3`, et coherence du stack ExtraMaxDamage."""
    pos = RU.run_case(sid, SEED, "garde 3 distincts", 3, 3, same_target=False)
    neg = RU.run_case(sid, SEED, "garde 2 distincts", 2, 3, same_target=False)
    assert pos is not None and neg is not None, "scenarios non montes"

    amount_off = int(ability_var("RealityUnbound", "extraMaxDmg", LEVEL, multiplier_pct=MULT) or 0)
    for r in (pos, neg):
        if r["apply_counter"]:
            # magnitude : le montant NATIF de la stat-modification == la magnitude offline.
            assert r["amount"] == amount_off, (
                f"{r['label']}: Amount natif {r['amount']} != offline {amount_off}")
            # stack : contribution totale == ApplyCounter x Amount (empilement par COMPTEUR).
            assert r["total_xmax"] == r["apply_counter"] * r["amount"], (
                f"{r['label']}: total {r['total_xmax']} != "
                f"{r['apply_counter']}x{r['amount']}")
        # gate `>= 3` : 1205/1206 poses SSI le seuil est atteint (temoin = WeaverOfFate 1185).
        expected = 1 if r["weaver"] else 0
        assert r["n_movement"] == expected, (
            f"{r['label']}: Movement(1205)={r['n_movement']} attendu {expected} "
            f"(seuil>=3 temoin WeaverOfFate={r['weaver']})")
        assert r["n_range"] == expected, (
            f"{r['label']}: Range(1206)={r['n_range']} attendu {expected}")

    # CAS NEGATIF explicite : le lot doit contenir un cas SOUS le seuil ou le stack MONTE quand meme.
    assert not neg["weaver"], "le cas 2-ennemis a atteint le seuil : cas negatif non exerce"
    assert neg["apply_counter"] >= 1, "le cas 2-ennemis n'a pose AUCUN stack ExtraMaxDamage"
    assert neg["n_movement"] == 0 and neg["n_range"] == 0, (
        "CAS NEGATIF ROMPU : Move/Range poses alors que le seuil >= 3 n'est pas atteint")


def test_time_flux_regen_negative_case_is_exactly_hp_to_heal(sid):
    """CAS NEGATIF isole de la regen TimeFlux : un tour adverse SANS action -> regen == hpToHeal.

    Prouve (a) que le regen fire au turn-start du PROPRIETAIRE, (b) que le terme
    `LastHitDamageTakenLastTurn` vaut 0 quand aucun coup n'a ete encaisse -- donc que le port ne
    porte pas un bonus INCONDITIONNEL, et (c) que la magnitude offline est exacte."""
    rid = TF.build(SEED)
    try:
        hp_to_heal = int(ability_var("TimeFlux", "hpToHeal", LEVEL, multiplier_pct=MULT) or 0)
        assert hp_to_heal > 0, "magnitude hpToHeal introuvable en gameconfig"
        p_team = TF.cp(sid, rid)
        # PREREQUIS : Toth doit avoir de la PLACE (a PV pleins le heal est cape a 0 et le cas n'est
        # pas discriminant). Les orks sont melee : quelques cycles suffisent a l'entamer.
        # Il ne suffit PAS qu'il soit entame : il faut qu'il MANQUE strictement plus que `hpToHeal`,
        # sinon `HealUnitOperation` cape a `hp_max` et le regen mesure vaut le manque, pas la formule
        # (mesure : a 393 PV manquants le flip rend 393, pas 1197 -- cape, donc non discriminant).
        damaged = False
        for _ in range(14):
            TF.endturn(sid, rid)
            TF.aiturn()
            hp, hpmax, _uid = TF.hp_of(sid, rid)
            if (hpmax - hp) > hp_to_heal * 2:
                damaged = True
                break
        if not damaged:
            pytest.skip("Toth pas assez entame (manque <= 2x hpToHeal) : heal cape, non discriminant")
        # un cycle P -> A -> P SANS `aiturn` : le tour adverse ne contient AUCUNE action.
        if TF.cp(sid, rid) != p_team:
            TF.endturn(sid, rid)
        TF.endturn(sid, rid)                       # P -> A
        hp_b = TF.hp_of(sid, rid)[0]
        TF.endturn(sid, rid)                       # A -> P : flip -> turn-start -> regen SEUL
        hp_c = TF.hp_of(sid, rid)[0]
        assert hp_c - hp_b == hp_to_heal, (
            f"regen isole {hp_c - hp_b} != hpToHeal {hp_to_heal} "
            f"(terme lastHit non remis a zero, ou magnitude fausse)")
    finally:
        TF.rpc(sid, "disposeRunner", {"runnerId": rid}, 15)
