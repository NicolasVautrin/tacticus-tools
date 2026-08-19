#!/usr/bin/env python
"""probe #1049 -- MESURE des deux passifs de summon portes par cette tranche.

  * `RedThirst` (`TriggeredAbilityType` 0x4e1 = 1249) -> effet `RedThirst_ExtraDamageAndHit`
    (0x52a = 1322) : `+extraDmg` de degat des que `HealthPct(Owner) <= healthPct`, `+extraHit`
    coup EN PLUS quand le porteur CHARGE.
  * `CursedOfTheWalkingPox` (`TriggeredAbilityType` 0x430 = 1072) : chaque kill d'un ennemi
    non-mecanique, non-objet, invoque un CLONE du porteur sur l'hex du mort.

PORTEUR -- le JUMEAU NPC, pas le summon. Les deux summons (`bloodSmnIntercessor`,
`deathPoxwalker`) ont un npc jumeau (`bloodNpc1Intercessor`, `deathNpc1Poxwalker`) qui porte le
MEME `passiveAbilities`, la MEME arme (2 coups) et le MEME `visualId` ; `--explicit-stats` le rend
spawnable par le chemin de stats NATIF des npc (`UnitProgression$$GetNpcStats`, #419-r1-tr12-r2).
On PILOTE donc le porteur au lieu de l'OBSERVER -- ce qui evite tout le montage « un summon ne se
commande pas » (#291) sans rien changer au code exerce : le passif est le meme objet natif.

STEP `redthirst` -- TROIS regimes, chacun sur un runner FRAIS. L'observable est DOUBLE et DISCRET :
le NOMBRE de coups (arme = 2 coups Chain ; +1 en charge) et leur VALEUR (+extraDmg par coup).

  | regime            | PV du porteur | pas          | attendu                          |
  |-------------------|---------------|--------------|----------------------------------|
  | CHARGE_BLESSE     | <= healthPct  | 2 hex -> 1   | +extraDmg ET +1 coup             |
  | NOSTEP_BLESSE     | <= healthPct  | aucun        | +extraDmg SEUL                   |
  | CHARGE_PLEIN      | 100 %         | 2 hex -> 1   | RIEN (active-condition fausse)   |

`NOSTEP_BLESSE` est le regime DISCRIMINANT du gate `IsCharging` (un port qui rattacherait la charge
au canal DEGAT -- ce que dit la PROSE i2 -- y sur-tirerait), et `CHARGE_PLEIN` celui de
l'active-condition.

Chaque regime confronte le live au rejeu offline (bit-exact) ET a une CONTRE-EPREUVE offline ou
l'instance 1322 est retiree de l'etat : si les deux offline coincident, le scenario ne prouve rien.

STEP `pox` -- DEUX bras, chacun sur un runner FRAIS (patron `Lakrimae` de
`case-462-r4b-r1-r1-r1-r1-c-r3-r1-r4` SS4) :

  | bras       | victime      | trait         | attendu                       |
  |------------|--------------|---------------|-------------------------------|
  | POSITIF    | `orksNob`    | non-mecanique | +1 `deathPoxwalker` sur l'hex |
  | MECANIQUE  | `necroWarden`| **Mechanical**| AUCUN spawn (gate natif)      |

Usage (depuis scripts/python, session warmee) :
    python probe_1049_red_thirst_walking_pox.py [--step redthirst|pox|all] [--seed 777]
                                                [--board MC1_67]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

#: Porteur du STEP `pox` : le npc jumeau du summon `deathPoxwalker` (meme `visualId`, meme
#: `passiveAbilities`, meme arme), monte par le chemin de stats NATIF des npc.
POXWALKER_NPC = "deathNpc1Poxwalker:45"
POXWALKER_VIS = "deathPoxwalker"
#: 2e ennemi -- TEMOIN DE CONTINUATION, jamais attaque : il empeche le kill de terminer le match.
POX_FILLER = "worldJakhal"

#: Porteur du STEP `redthirst` : GREFFE de l'ability sur un HERO DU POOL (`case-92` SS5bis, recours
#: 3). Legitime ICI et mesure, pas contournement : les trois corps natifs de 1322 ne lisent NI stat
#: NI trait du caster -- seulement la config d'ability (`healthPct`/`extraDmg`/`extraHit`) et le
#: RATIO DE PV du porteur. Le natif charge par ability, pas par unite.
#: ⚠ POURQUOI PAS le jumeau npc `bloodNpc1Intercessor:45`, qui serait pourtant le porteur EXACT :
#: mesure du 2026-08-14 -- son `combatSnapshot.unitConfig` rend `{"passiveAbilityLevel": 1,
#: "abilityVariablesMultiplier": 100}` alors que le canal `unitAbilityStates` rend `(65, 200)` pour
#: la MEME entite. `snapshot.py::_ability_state_with_channel` ne comble QUE le trou (`passive_level`
#: falsy) et ce `1` est truthy -> l'offline lit `extraDmg[1] = 6` la ou le natif lit `extraDmg[65] x
#: 200 %`. C'est un artefact du montage `--explicit-stats` (une unite INVOQUEE, elle, n'a AUCUN
#: `unitConfig` -> le canal gagne), pas un ecart du port : residu `#1049-r1`.
GRAFT_HOST = "astraBullgryn"          # 4 coups Physical MELEE, passif d'origine remplace
#: `TriggeredAbilityType.RedThirst` -- `BC.Units[].PassiveAbilities` porte des IDS, pas des noms.
RED_THIRST_ID = 1249
GRAFT_PASSIVES = "PassiveAbilities=[%d]" % RED_THIRST_ID
#: PV du porteur greffe : `--hp-player` force `Health` ET `RemainingHealth`, `--unit-stat` (applique
#: APRES) rabaisse le seul `RemainingHealth` -> ratio choisi.
HOST_HP = 10000
HOST_HP_WOUNDED = 4000                # 40 % <= healthPct (50)
EFFECT_NAME = "RedThirst_ExtraDamageAndHit"
#: `--hp-target` met l'armure des a-units a 0 -> degat deterministe.
ENEMY_HP = "120000"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _build(seed, board, extra, prefix):
    fd, sf = tempfile.mkstemp(prefix=prefix, suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", sf, "--board", board, *extra]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        return None, ((p.stdout or "") + (p.stderr or ""))[-500:]
    rid = json.loads(Path(sf).read_text())["runnerId"]
    Path(sf).unlink(missing_ok=True)
    return rid, None


# ------------------------------------------------------------------ RedThirst

def _replay_without_effect(h, rec):
    """CONTRE-EPREUVE : meme rejeu que `replay_offline`, l'instance 1322 RETIREE de l'etat.

    Un scenario ou les deux offline rendent la MEME chose ne discrimine rien -- c'est le controle
    de non-degenerescence, pas un ornement."""
    from engine.runner.components import UnitComponent
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.runner import Runner
    st = h.offline_state(rec)
    if st.effects is not None:
        for uid, lst in list(st.effects.by_unit.items()):
            st.effects.by_unit[uid] = [e for e in lst if getattr(e, "name", None) != EFFECT_NAME]
    e = st.get_entity(rec["caster"])
    uc = e.get_component(UnitComponent) if e is not None else None
    charged = sorted(int(i) for i in (uc.charged_unit_ids or ())) if uc is not None else []
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(attacker_id=rec["caster"], target_id=rec["target"]))
    return {"per_hit": list((runner.damage_handler.last or {}).get("per_hit") or []),
            "charged": charged}


def step_redthirst(rpc, seed, board) -> int:
    from _charge_regime import ChargeRegimeHarness
    from engine.entities.pathfinding.board import Board

    regimes = (("CHARGE_BLESSE", "CHARGE", HOST_HP_WOUNDED),
               ("NOSTEP_BLESSE", "NO_STEP", HOST_HP_WOUNDED),
               ("CHARGE_PLEIN", "CHARGE", None))
    rc = 0
    for label, regime, remaining in regimes:
        fields = GRAFT_PASSIVES if remaining is None \
            else "%s,RemainingHealth=%d" % (GRAFT_PASSIVES, remaining)
        extra = ["--p-units", GRAFT_HOST, "--a-units", "necroWarden",
                 "--hp-target", ENEMY_HP, "--hp-player", str(HOST_HP), "--no-ai",
                 "--unit-stat", "%s:%s" % (GRAFT_HOST, fields)]
        rid, err = _build(seed, board, extra, "probe1049_rt_")
        if rid is None:
            print("[%s] BUILD KO : %s" % (label, err)); rc = 1; continue
        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
            dv = h.dview()
            me = h.by_visual(GRAFT_HOST, dv)
            if me is None:
                print("[%s] porteur ABSENT du decisionView" % label); rc = 1; continue
            dvi = rpc("decisionView", {"runnerId": rid, "includeInactive": True}, 60)
            mine = next((u for u in (dvi.get("units") or []) if u["id"] == me["id"]), {})
            live_eff = [(e.get("name"), e.get("active")) for e in (mine.get("effects") or [])]
            print("[%s] porteur u%s hp=%s | effets live (includeInactive) : %s"
                  % (label, me["id"], me.get("hp"), json.dumps(live_eff)), flush=True)
            rec = h.run(caster_visual=GRAFT_HOST, regime=regime)
            if rec is None:
                print("[%s] geometrie/regime non realisable" % label); rc = 1; continue
            off = h.replay_offline(rec)
            ctl = _replay_without_effect(h, rec)
            print("[%s] live n=%d %s" % (label, len(rec["live_per_hit"]), rec["live_per_hit"]),
                  flush=True)
            print("[%s] off  n=%d %s (charged=%s)"
                  % (label, len(off["per_hit"]), off["per_hit"], off["charged"]), flush=True)
            print("[%s] ctl  n=%d %s   <- 1322 RETIRE"
                  % (label, len(ctl["per_hit"]), ctl["per_hit"]), flush=True)
            match = off["per_hit"] == rec["live_per_hit"]
            discr = ctl["per_hit"] != off["per_hit"]
            print("[%s] VERDICT accord=%s | contre-epreuve discriminante=%s"
                  % (label, "MATCH" if match else "DIVERGE", discr), flush=True)
            if not match:
                rc = 1
        finally:
            rpc("disposeRunner", {"runnerId": rid}, 20)
    return rc


# ------------------------------------------------------------------ CursedOfTheWalkingPox

def step_pox(rpc, seed, board) -> int:
    from _charge_regime import ChargeRegimeHarness, _seed_rng
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import PositionComponent, UnitComponent
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state

    rc = 0
    for label, victim_vis in (("POSITIF", "orksNob"), ("MECANIQUE", "necroWarden")):
        # ⚠ DEUX ennemis, et le second n'est LA que pour que la bataille CONTINUE. Mesure du
        # 2026-08-14 : avec un seul ennemi le kill termine le match (`Match_Winner`), le
        # `decisionView` d'apres rend `units: []` et le spawn -- pourtant EMIS par le natif dans les
        # events du meme `applyAction` -- devient INOBSERVABLE. Un « 0 spawn » lu la aurait accuse
        # le port pour une fin de partie.
        extra = ["--p-units", POXWALKER_NPC, "--explicit-stats", POXWALKER_NPC,
                 "--a-units", "%s,%s" % (victim_vis, POX_FILLER), "--hp-target", "1", "--no-ai"]
        rid, err = _build(seed, board, extra, "probe1049_pox_")
        if rid is None:
            print("[%s] BUILD KO : %s" % (label, err)); rc = 1; continue
        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
            dv = h.dview()
            me = h.by_visual(POXWALKER_VIS, dv)
            tgt = h.by_visual(victim_vis, dv)
            if me is None or tgt is None:
                print("[%s] porteur/cible absents" % label); rc = 1; continue
            h.my_player = me.get("owner")
            if h.reach_my_turn(force_cycle=True) is None:
                print("[%s] tour non atteint" % label); rc = 1; continue
            # Poser le porteur AU CONTACT de la victime (la victime bouge en DERNIER n'a pas
            # d'importance ici : aucun gate de charge dans ce passif).
            tpos = (tgt["pos"]["col"], tgt["pos"]["row"])
            free = h.free_tiles(tpos, 1, exclude=(tpos,))
            if not free:
                print("[%s] aucune tuile libre adjacente a la victime" % label); rc = 1; continue
            if not h.place(me["id"], free[0]):
                print("[%s] pose du porteur refusee" % label); rc = 1; continue
            if h.reach_my_turn(force_cycle=True) is None:
                print("[%s] tour non atteint (2)" % label); rc = 1; continue
            snap = h.snapshot()
            before = {u["id"] for u in h.alive()}
            atype = h.normal_attack_type(me["id"])
            res = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": me["id"], "targetId": tgt["id"],
                "abilityType": int(atype)}}, 60)
            dv2 = h.dview()
            new_live = [u for u in (dv2.get("units") or []) if u["id"] not in before]
            print("[%s] victime u%s (%s) | live nouveaux = %s"
                  % (label, tgt["id"], victim_vis,
                     json.dumps([(u["id"], u.get("visualId"),
                                  (u.get("pos") or {}).get("col"),
                                  (u.get("pos") or {}).get("row"), u.get("hp"),
                                  u.get("parentId")) for u in new_live])),
                  flush=True)
            print("[%s] parent u%s hp=%s (CopyOwner -> le clone doit porter CE PV, pas un summonHp)"
                  % (label, me["id"], next((u.get("hp") for u in (dv2.get("units") or [])
                                            if u["id"] == me["id"]), None)), flush=True)
            victim_alive = any(u["id"] == tgt["id"] for u in h.alive(dv2))
            print("[%s] victime encore vivante : %s | tuile victime = %s"
                  % (label, victim_alive, tpos), flush=True)

            # --- rejeu OFFLINE du meme coup
            st = load_state(snap["dv"], snap["ob"], snap["snap"], board=h.board)
            dump = snap.get("rng")
            if isinstance(dump, dict) and dump.get("mt"):
                st.rng = _seed_rng(dump)          # MEME etat de PRNG que le coup live
            off_before = set(st.entities.keys())
            runner = Runner(st).install_default_handlers(20)
            runner.apply(AttackUnitMessage(attacker_id=me["id"], target_id=tgt["id"]))
            from engine.runner.components import HealthComponent, OwnerComponent
            off_new = []
            for eid in sorted(set(st.entities.keys()) - off_before):
                ent = st.get_entity(eid)
                uc = ent.get_component(UnitComponent)
                pc = ent.get_component(PositionComponent)
                hc = ent.get_component(HealthComponent)
                oc = ent.get_component(OwnerComponent)
                off_new.append((eid, getattr(uc, "visual_id", None),
                                (pc.col, pc.row) if pc is not None else None,
                                getattr(hc, "hp", None), getattr(uc, "parent_id", None),
                                getattr(oc, "team", None)))
            pe = st.get_entity(me["id"])
            phc = pe.get_component(HealthComponent) if pe is not None else None
            print("[%s] off  parent hp=%s" % (label, getattr(phc, "hp", None)), flush=True)
            print("[%s] off  nouveaux = %s" % (label, json.dumps(off_new)), flush=True)
            live_n = len([u for u in new_live if u.get("visualId") == POXWALKER_VIS])
            off_n = len([x for x in off_new if x[1] == POXWALKER_VIS])
            print("[%s] VERDICT live=%d spawn(s) | offline=%d spawn(s) -> %s"
                  % (label, live_n, off_n, "MATCH" if live_n == off_n else "DIVERGE"), flush=True)
            if live_n != off_n:
                rc = 1
        finally:
            rpc("disposeRunner", {"runnerId": rid}, 20)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all", choices=("all", "redthirst", "pox"))
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()
    w = _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        print("[probe] amorce KO : %s" % str(w)[:200])
        return 2

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    # ⚠ LIER LE TRANSPORT RPC AMBIANT -- c'est ce que fait la fixture `live_session` de pytest, et
    # sans lui `load_state` ne va PAS chercher `unitAbilityStates` (#357/#363). Mesure : sur un
    # porteur monte par `--explicit-stats`, dont le `unitConfig` capture ne porte NI
    # `passiveAbilityLevel` NI `abilityVariablesMultiplier`, l'offline retombe alors sur
    # `(level 1, mult 100)` et lit `extraDmg[1] = 6` au lieu d'`extraDmg[65] x 200 %`. Le port
    # paraissait faux ; c'etait le HARNAIS qui ne branchait pas le canal.
    from engine.runner.snapshot import bind_live_rpc, clear_ability_states_cache, unbind_live_rpc
    bind_live_rpc(rpc)

    rc = 0
    try:
        if a.step in ("all", "redthirst"):
            rc |= step_redthirst(rpc, a.seed, a.board)
        if a.step in ("all", "pox"):
            rc |= step_pox(rpc, a.seed, a.board)
    finally:
        unbind_live_rpc()
        clear_ability_states_cache()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
