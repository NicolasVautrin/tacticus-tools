"""Tranche DAMAGE — REPLAY-DIFF d'attaque : runner OFFLINE vs runner LIVE.

On rejoue LA MÊME attaque (move au contact puis attaque normale) sur le runner LIVE
(`applyAction`) ET sur le runner Python, et on diffe les PV de la cible. Le runner
offline tire le dégât DEPUIS SON ECS :
  • `StatsComponent` (stat Attack résolue = base de combat confirmée — pas le weapon-base
    d'`aiPredict`) + spread BC → plage brute du coup ;
  • effets STRUCTURÉS (`State.effects`) → modifiers (×bonus, perçage, ignore-armure) ;
  • réduction perçage/armure (`get_damage_with_piercing`) APRÈS le tirage ;
  • `state.rng` CALÉ sur l'état MT live (`dumpRng`) → mêmes tirages que le natif.

C'est la VALIDATION de l'init stats+effets : si le runner reproduit le dégât réel,
c'est qu'il a chargé correctement stats ET effets. (Pas d'`aiPredict` comme oracle :
l'oracle = le runner live qui exécute le VRAI combat.)

PALIER ACTUEL = coup MONO propre (no-crit/no-block). Le tirage de dégât est le 1er
conso RNG d'`ExecuteHit` (crit/block APRÈS) → pour un coup mono propre, l'offline
matche bit-exact. Crit/block/multi-coups (désync RNG inter-coups) = paliers suivants ;
les cas où le live sort de la plage propre (crit/block) sont signalés et exclus.

Property-based, indépendant version/seed. Skip si pas de session / aucun cas mono propre.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, StatsComponent

_SEEDS = ["777", "31337", "123"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


@pytest.fixture(scope="session")
def attack_replay(live_session, rpc, build_runner):
    """Rejoue chaque attaque normale mono-coup propre (live + offline) et collecte les PV.

    Renvoie `{"cases": [...]}` où chaque cas = {att, tgt, live_after, off_after, off_total,
    live_dmg, in_clean, hits, effects}. `cases` non vide (sinon skip)."""
    import predict_validate as PV          # lazy : tire rl_collect_batch
    sid = live_session

    for seed in _SEEDS:
        b = build_runner(seed)
        rid, my_team = b["rid"], b["my_team"]
        if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
            pytest.skip("dumpRng indispo (rebuild+reinject hooks ?)")
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        if not _ok(snap):
            continue
        rows = PV.build_samples(sid, rid, my_team, 6)
        if not rows:
            continue
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 3, "allAbilities": True}, 90)
        cur = dec.get("currentPlayer")
        u_by_id = {u["id"]: u for u in (dec.get("units") or [])}
        tile_by = {}
        for ap in (dec.get("attackPlans") or []):
            for ev in (ap.get("evals") or []):
                rk = (ev.get("ranked") or [{}])[0]
                tile_by[(ap.get("unitId"), ev.get("targetId"))] = (rk.get("col"), rk.get("row"))

        cases = []
        for r in rows:
            if r["hits"] != 1 or not PV.sample_is_clean(r):      # mono-coup, predOptimistic exclus
                continue
            att, tgt = r["att"], r["tgt"]
            a = u_by_id.get(att)
            if not a or a.get("owner") != cur:
                continue
            norm = next((ab for ab in (a.get("abilities") or [])
                         if ab.get("kind") == "normal"), None)
            if not norm:
                continue
            col, row = tile_by.get((att, tgt), (None, None))
            if col is not None:                                  # move au contact (overwatch éventuel
                rpc("applyAction", {"runnerId": rid, "action": {                 # consommé AVANT dumpRng)
                    "kind": "move", "unitId": att, "to": {"col": col, "row": row}}}, 40)
            dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
            state = load_state(dv2, ob2, snap)                   # ECS offline (stats+effets) post-move
            te = state.get_entity(tgt)
            hc = te.get_component(HealthComponent) if te is not None else None
            if hc is None or hc.hp is None:
                continue
            hp_before = hc.hp
            s1 = rpc("dumpRng", {"runnerId": rid}, 30)
            if not _ok(s1):
                continue
            state.rng = _seed_rng(s1)                            # MT offline = MT live
            runner = Runner(state).install_default_handlers(20)
            res = rpc("applyAction", {"runnerId": rid, "action": {                # LIVE attaque
                "kind": "ability", "casterId": att, "targetId": tgt,
                "abilityType": norm["id"]}}, 40)
            if not (_ok(res) and (res.get("actions") or [{}])[0].get("ok")):
                continue
            live_after = next((u.get("hp") for u in (res.get("units") or [])
                               if u.get("squadId") == tgt), None)
            if live_after is None:
                continue
            runner.apply(AttackUnitMessage(att, tgt))            # OFFLINE attaque (même MT)
            rr = runner.damage_handler.last
            off_after = state.get_entity(tgt).get_component(HealthComponent).hp
            live_dmg = hp_before - int(live_after)
            if live_dmg <= 0 or rr is None:
                continue
            cases.append({
                "seed": seed, "att": att, "tgt": tgt,
                "live_after": int(live_after), "off_after": off_after,
                "off_total": rr["total"], "live_dmg": live_dmg,
                "in_clean": rr["clean_min"] <= live_dmg <= rr["clean_max"],
                "hits": rr["hits"], "effects": rr["effects"],
            })
        if cases:
            return {"cases": cases}

    pytest.skip("aucune attaque normale mono-coup propre applicable sur les seeds testés")


def test_offline_attack_reproduces_live_damage(attack_replay):
    """CŒUR : pour chaque coup MONO PROPRE (live dans la plage no-crit/no-block), le runner
    OFFLINE inflige EXACTEMENT les mêmes PV que le live → init stats+effets correcte."""
    clean = [c for c in attack_replay["cases"] if c["in_clean"]]
    skipped = [c for c in attack_replay["cases"] if not c["in_clean"]]
    for c in clean:
        print(f"\n[ATK replay] seed {c['seed']} u{c['att']}→u{c['tgt']} : live_dmg={c['live_dmg']} "
              f"off={c['off_total']} → live_after={c['live_after']} off_after={c['off_after']} "
              f"eff={c['effects']}")
    if skipped:
        print(f"\n[ATK replay] {len(skipped)} cas hors plage propre (crit/block — palier suivant) : "
              + ", ".join(f"u{c['att']}→u{c['tgt']}(dmg {c['live_dmg']})" for c in skipped))
    assert clean, ("aucun coup mono PROPRE (no-crit/no-block) capturé — impossible de valider "
                   "le replay-diff d'attaque sur ces seeds")
    bad = [c for c in clean if c["off_after"] != c["live_after"]]
    assert not bad, ("PV offline != live (init stats/effets ou réduction fautive):\n  " +
                     "\n  ".join(f"u{c['att']}→u{c['tgt']} seed {c['seed']}: off_after={c['off_after']} "
                                 f"!= live_after={c['live_after']} (off_total={c['off_total']} "
                                 f"vs live_dmg={c['live_dmg']}, eff={c['effects']})" for c in bad))


def test_stats_and_effects_are_loaded(attack_replay):
    """SANITY : l'init a bien posé `StatsComponent` (stats) + `State.effects` (effets
    structurés) — sans quoi le runner ne pourrait pas calculer le dégât."""
    cases = attack_replay["cases"]
    assert cases and any(c["off_total"] > 0 for c in cases), \
        "le runner offline n'a produit aucun dégât → stats/effets non chargés"
