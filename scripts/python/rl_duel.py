#!/usr/bin/env python
"""rl_duel — duel MIROIR : Claude (oracle) vs IA native, sur un runner PERSISTANT.

Le runner vit dans l'agent Frida (registry, par runnerId) entre les invocations
Python — donc on pilote le duel par sous-commandes successives :

  build              monte le runner (seed/rank/roster), NE dispose PAS, sauve
                     l'état (runnerId + bc) et affiche la carte décision.
  view               re-affiche la carte décision (mon tour).
  act move    --unit U --to C,R
  act ability --caster U --target T --ability A
  act finish  --unit U
  act endturn        fin de MON tour → passe la main à l'IA.
  aiturn             joue UN tour d'équipe de l'IA (aiPlayByUnit, capture
                     overwatch → on voit si l'IA mange l'overwatch).
  status             stage + survivants par équipe + winner.
  dispose            libère le runner.

Claude = la POLICY : à chaque tour, il lit `view`, décide, enchaîne des `act`,
puis `act endturn`, puis `aiturn`. Lancer avec `python` (psycopg3),
cf. feedback_rl_batch_python_psycopg3.
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import (  # noqa: E402
    _resolve_session, _ensure_ai_trace, _load_seed_bc, _load_unspawnable,
    _normalize_and_extract_pool, _spawn_points_by_twpi,
    _patch_predefined_units, _patch_predefined_machines, _rpc,
    PLAYER_ID_HUMAN,
)
from rl_probe_step import _print_apply  # noqa: E402
import oracle  # noqa: E402
import stream_events  # noqa: E402
from board import Board  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "duel_state.json"


def _save_state(d: dict) -> None:
    STATE.write_text(json.dumps(d), encoding="utf-8")


def _load_state() -> dict:
    if not STATE.exists():
        print("[error] pas d'état de duel — lance `build` d'abord", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text(encoding="utf-8"))


def _decision(sid: int, rid: int, maxrank: int = 8) -> dict:
    return (_rpc(sid, "decisionView", [{"runnerId": rid, "maxRank": maxrank}],
                 timeout=300).get("result") or {})


def _show_card(sid: int, rid: int, bc: dict) -> dict:
    res = _decision(sid, rid)
    if not res.get("ok"):
        print(f"[view] decisionView ERROR: {res.get('error')}")
        return res
    print(oracle.build_card(res, Board(bc)))
    return res


def _advance(sid: int, rid: int, n: int, maxpump: int) -> None:
    played = 0
    while played < n:
        chunk = min(2, n - played)
        r = (_rpc(sid, "aiPlayByUnit",
                  [{"runnerId": rid, "maxTurns": chunk, "maxActivations": 9999,
                    "maxPump": maxpump}], timeout=180).get("result") or {})
        if not r.get("ok"):
            print(f"  [advance] ERROR: {r.get('error')}"); break
        played += r.get("turnsPlayed") or 0
        if r.get("finalStage") != 1:
            break


def _plans_summary(res: dict) -> None:
    """Ré-évaluation compacte APRÈS une action : HP ennemis vivants + plans
    d'attaque restants de mes units (base de décision pour l'action suivante)."""
    units = res.get("units") or []
    enemies = [u for u in units if not u.get("ctrl") and u.get("alive")]
    print("  -- ennemis vivants : "
          + ", ".join(f"u{e['id']}[{e.get('visualId')}] hp={e.get('hp')}"
                      for e in enemies))
    toact = res.get("toActivate") or []
    print(f"  -- mes units à activer : {toact}")
    for p in (res.get("attackPlans") or []):
        if p.get("unitId") not in toact:
            continue
        best = []
        for ev in (p.get("evals") or []):
            r0 = (ev.get("ranked") or [None])[0]
            if not r0 or r0.get("dmgMax") is None:
                continue
            km = ("K!" if r0.get("killSure") else "K?" if r0.get("kill") else "")
            best.append(f"u{ev['targetId']}@({r0['col']},{r0['row']})"
                        f"[{r0['dmgMin']}-{r0['dmgMax']}{km}]")
        if best:
            print(f"     u{p['unitId']}: " + "  ".join(best))


def _alive_by_team(units: list) -> dict:
    out: dict = {}
    for u in units:
        if u.get("alive"):
            out[u.get("team")] = out.get(u.get("team"), 0) + 1
    return out


def _parse_ids(s: str | None) -> list[str] | None:
    return [x.strip() for x in s.split(",") if x.strip()] if s else None


def _board_mow_ok(bc: dict) -> bool:
    """True si la board de la BC a un slot MoW (MachineOfWarPosition) pour les
    deux camps sur le SpawnPointSet actif — sinon le MoW drop silencieusement
    au déploiement (cf. _board_supports_mow / project_mow_deploy_gate)."""
    spsets = (bc.get("Board") or {}).get("SpawnPointSets") or []
    idx = bc.get("SpawnPointSetIndex") or 0
    if not (0 <= idx < len(spsets)):
        return False
    mp = {g.get("TeamWithPlayerIndex"): g.get("MachineOfWarPosition")
          for g in (spsets[idx].get("SpawnPointGroups") or [])}
    return mp.get(0) not in (0, None) and mp.get(1) not in (0, None)


def cmd_build(sid: int, a) -> int:
    seed_bc = _load_seed_bc()
    template_bc, pool, pool_mow = _normalize_and_extract_pool(sid, seed_bc, a.rank)
    bad_u, bad_mow = _load_unspawnable(a.rank)
    pool = [u for u in pool if u not in bad_u]
    pool_mow = [u for u in pool_mow if u not in bad_mow]

    if a.list_pool:
        print(f"[pool] rank {a.rank} — {len(pool)} units régulières spawnables :")
        for uid in pool:
            print("  ", uid)
        print(f"[pool] {len(pool_mow)} MoW spawnables : {pool_mow}")
        return 0

    rng = random.Random(a.seed)
    explicit_p = _parse_ids(a.p_units)
    explicit_a = _parse_ids(a.a_units)

    def pick(label: str, explicit: list[str] | None, n: int) -> list[str]:
        if explicit:
            miss = [u for u in explicit if u not in pool]
            if miss:
                print(f"[error] {label}: hors pool / non spawnables au rank "
                      f"{a.rank}: {miss}", file=sys.stderr)
                print(f"        pool = {len(pool)} units (voir `build --list-pool`)",
                      file=sys.stderr)
                sys.exit(2)
            return list(explicit)
        return rng.sample(pool, n)

    p_units = pick("--p-units", explicit_p, a.roster)
    a_units = pick("--a-units", explicit_a, a.roster)

    # MoW : explicite, ou auto (--mow), ou aucun.
    p_mow, a_mow = a.p_mow, a.a_mow
    if a.mow and not p_mow and not a_mow and pool_mow:
        p_mow, a_mow = rng.choice(pool_mow), rng.choice(pool_mow)
    for label, m in (("--p-mow", p_mow), ("--a-mow", a_mow)):
        if m and m not in pool_mow:
            print(f"[error] {label}={m} hors pool MoW spawnable: {pool_mow}",
                  file=sys.stderr)
            return 2

    bc = copy.deepcopy(template_bc)
    _patch_predefined_units(bc, a_units)
    _patch_predefined_machines(bc, p_mow, a_mow)

    if (p_mow or a_mow) and not _board_mow_ok(bc):
        print("[warn] board de la seed BC SANS slot MoW (MachineOfWarPosition) "
              "→ le MoW sera DROP silencieusement au déploiement. Il faut une "
              "board MoW-capable (cf. _board_supports_mow).", file=sys.stderr)

    spawns = _spawn_points_by_twpi(bc)
    player_pts = spawns.get(0) or []
    roster_p = len(p_units)
    if len(player_pts) < roster_p:
        print(f"[error] {len(player_pts)} spawns joueur < {roster_p} units",
              file=sys.stderr)
        return 2
    player_units = [
        {"unitId": p_units[i], "playerId": PLAYER_ID_HUMAN,
         "col": int(player_pts[i][0]), "row": int(player_pts[i][1])}
        for i in range(roster_p)
    ]
    init = (_rpc(sid, "initAndStart",
                 [{"configJson": json.dumps(bc), "seed": a.seed,
                   "playerUnits": player_units}], timeout=40).get("result") or {})
    rid = init.get("runnerId")
    if rid is None:
        print(f"[error] initAndStart: {init}", file=sys.stderr); return 2
    mow_str = (f"  MoW: moi={p_mow or '-'} IA={a_mow or '-'}"
               if (p_mow or a_mow) else "")
    print(f"[build] runnerId={rid}  MON roster (team 1)={p_units}")
    print(f"[build] roster ADVERSE (team 2)={a_units}{mow_str}")
    if a.advance > 0:
        _advance(sid, rid, a.advance, a.maxpump)
        print(f"[build] advanced {a.advance} tours (IA vs IA)")
    res = _show_card(sid, rid, bc)
    my_team = next((u.get("team") for u in (res.get("units") or [])
                    if u.get("ctrl")), None)
    _save_state({"runnerId": rid, "bc": bc, "seed": a.seed, "myTeam": my_team})
    return 0


def cmd_view(sid: int, a) -> int:
    st = _load_state()
    _show_card(sid, st["runnerId"], st["bc"])
    return 0


def cmd_act(sid: int, a) -> int:
    st = _load_state()
    rid = st["runnerId"]
    res = _decision(sid, rid)
    my_ids = [u["id"] for u in (res.get("units") or []) if u.get("ctrl")]
    if a.kind == "move":
        col, row = (int(x) for x in a.to.split(","))
        action = {"kind": "move", "unitId": a.unit, "to": {"col": col, "row": row}}
        label = f"MOVE u{a.unit}->({col},{row})"
    elif a.kind == "ability":
        ability = a.ability
        if ability is None:  # auto-résout depuis le plan (caster→target)
            for p in (res.get("attackPlans") or []):
                if p.get("unitId") == a.caster:
                    for ev in (p.get("evals") or []):
                        if ev.get("targetId") == a.target:
                            ability = ev.get("abilityId")
        if ability is None:
            print(f"[act] pas de plan {a.caster}->{a.target} (hors portée ?), "
                  f"passe --ability"); return 2
        action = {"kind": "ability", "casterId": a.caster,
                  "targetId": a.target, "abilityType": ability}
        label = f"ABILITY {ability} u{a.caster}->u{a.target}"
    elif a.kind == "finish":
        action = {"kind": "finish", "unitId": a.unit}
        label = f"FINISH u{a.unit}"
    elif a.kind == "endturn":
        action = {"kind": "endturn"}
        label = "ENDTURN"
    else:
        print(f"[act] kind inconnu: {a.kind}"); return 2
    r = (_rpc(sid, "applyAction", [{"runnerId": rid, "action": action}],
              timeout=60).get("result") or {})
    _print_apply(label, r, my_ids)
    print(f"  -> stage={r.get('stage')} currentPlayer={r.get('currentPlayer')}")
    # Ré-évaluation APRÈS l'action (le board a changé) — base de la décision
    # suivante, surtout pour le focus-fire (arrêter dès qu'une cible meurt).
    if a.kind != "endturn":
        _plans_summary(_decision(sid, rid))
    return 0


def _my_team(sid: int, rid: int, st: dict):
    t = st.get("myTeam")
    if t is not None:
        return t
    res = _decision(sid, rid)
    return next((u.get("team") for u in (res.get("units") or [])
                 if u.get("ctrl")), None)


def _fmt_dmg(d: dict) -> str:
    eff = f" [{d['effect']}]" if d.get("effect") else ""
    crit = "*" if d.get("crit") else ""
    kill = " KILL" if d.get("killed") else ""
    return f"u{d.get('attacker')}->u{d.get('target')} {d.get('amount')}{crit}{eff}{kill}"


def _summarize_cascade(an: dict, cap: int = 16) -> None:
    """Bilan UNIFORME de la cascade (overwatch/counter/aura/DoT = events comme
    les autres, juste labellisés via `effect`). received = ce que J'ENCAISSE ;
    dealt (pendant le tour adverse) = MA réaction (overwatch/contre/aura)."""
    rec, dealt = an.get("received") or [], an.get("dealt") or []
    if rec:
        tot = sum(d.get("amount") or 0 for d in rec)
        nk = sum(1 for d in rec if d.get("killed"))
        print(f"  SUBI : {len(rec)} coups, {tot} dmg"
              + (f", {nk} de MES units tuées" if nk else ""))
        for d in rec[:cap]:
            print("    - " + _fmt_dmg(d))
        if len(rec) > cap:
            print(f"    … (+{len(rec) - cap})")
    if dealt:
        tot = sum(d.get("amount") or 0 for d in dealt)
        nk = sum(1 for d in dealt if d.get("killed"))
        print(f"  MA RÉACTION (overwatch/contre/aura) : {len(dealt)} coups, "
              f"{tot} dmg" + (f", {nk} ennemis tués en réaction" if nk else ""))
        for d in dealt[:cap]:
            print("    - " + _fmt_dmg(d))
        if len(dealt) > cap:
            print(f"    … (+{len(dealt) - cap})")
    if not rec and not dealt:
        print("  (aucun dégât dans la cascade)")


def _ai_turn(sid: int, rid: int, maxpump: int, my_team) -> dict:
    r = (_rpc(sid, "aiPlayByUnit",
              [{"runnerId": rid, "maxTurns": 1, "maxActivations": 9999,
                "maxPump": maxpump, "captureEvents": True}],
              timeout=300).get("result") or {})
    print(f"[aiturn] ok={r.get('ok')} turnsPlayed={r.get('turnsPlayed')} "
          f"stop={r.get('stopReason')} finalStage={r.get('finalStageName')} "
          f"finalPlayer={r.get('finalPlayer')} events={r.get('cascadeCount')}")
    res = _decision(sid, rid)
    units = res.get("units") or []
    # my_ids inclut mes MoW (casterId) — sinon l'AoE du MoW (attacker=casterId)
    # tombe dans le catch-all `damage` au lieu de `dealt`.
    my_ids = [u["id"] for u in units if u.get("team") == my_team]
    my_ids += [m["casterId"] for m in (res.get("mows") or [])
               if m.get("team") == my_team]
    cascade = r.get("cascade") or []
    an = stream_events.analyze(cascade, my_ids)
    _summarize_cascade(an)
    # Diagnostic frontière : TOUT UnitDamaged ciblant un ennemi (capte l'AoE/DoT
    # de fin de tour quelle que soit la source) → vérifie la capture EndTurn.
    enemy_dmg = [d for d in an["damage"] if d.get("target") not in set(my_ids)]
    if enemy_dmg:
        tot = sum(d.get("amount") or 0 for d in enemy_dmg)
        print(f"  DÉGÂTS AUX ENNEMIS (cascade, toutes sources) : "
              f"{len(enemy_dmg)} coups, {tot} dmg")
        for d in enemy_dmg[:14]:
            print("    - " + _fmt_dmg(d))
    return r


def cmd_aiturn(sid: int, a) -> int:
    st = _load_state()
    rid = st["runnerId"]
    _ai_turn(sid, rid, a.maxpump, _my_team(sid, rid, st))
    return 0


def cmd_play(sid: int, a) -> int:
    """1 ROUND : applique MES actions (--spec JSON), endturn, tour IA, status,
    puis ré-affiche la carte. spec = liste d'actions :
      {"kind":"move","unit":95,"to":[3,2]}
      {"kind":"ability","caster":97,"target":89[,"ability":N]}  (ability auto-résolu)
      {"kind":"finish","unit":95}"""
    st = _load_state()
    rid, bc = st["runnerId"], st["bc"]
    spec = json.loads(a.spec) if a.spec else []
    res = _decision(sid, rid)
    my_ids = [u["id"] for u in (res.get("units") or []) if u.get("ctrl")]
    # abilityId par (caster, target) depuis les plans (attaque normale concrète).
    plan_ab: dict = {}
    for p in (res.get("attackPlans") or []):
        for ev in (p.get("evals") or []):
            plan_ab[(p["unitId"], ev["targetId"])] = ev.get("abilityId")
    for ac in spec:
        k = ac["kind"]
        if k == "move":
            action = {"kind": "move", "unitId": ac["unit"],
                      "to": {"col": ac["to"][0], "row": ac["to"][1]}}
            label = f"MOVE u{ac['unit']}->{tuple(ac['to'])}"
        elif k == "ability":
            ab = ac.get("ability") or plan_ab.get((ac["caster"], ac["target"]))
            if ab is None:
                print(f"  [play] pas d'ability {ac['caster']}->{ac['target']} "
                      f"(hors portée ?) — SKIP"); continue
            action = {"kind": "ability", "casterId": ac["caster"],
                      "targetId": ac["target"], "abilityType": ab}
            label = f"ABILITY {ab} u{ac['caster']}->u{ac['target']}"
        elif k == "finish":
            action = {"kind": "finish", "unitId": ac["unit"]}
            label = f"FINISH u{ac['unit']}"
        else:
            print(f"  [play] kind inconnu: {k}"); continue
        r = (_rpc(sid, "applyAction", [{"runnerId": rid, "action": action}],
                  timeout=60).get("result") or {})
        _print_apply(label, r, my_ids)
    # Fin de mon tour → main à l'IA.
    et = (_rpc(sid, "applyAction",
               [{"runnerId": rid, "action": {"kind": "endturn"}}],
               timeout=30).get("result") or {})
    print(f"  [endturn] -> player {et.get('currentPlayer')} stage={et.get('stage')}")
    if et.get("stage") != 1:
        print("  *** battle finie après mon tour ***")
        return cmd_status(sid, a)
    # Tour de l'IA.
    _ai_turn(sid, rid, a.maxpump, _my_team(sid, rid, st))
    # Bilan + carte pour ma prochaine décision.
    print("\n========== ÉTAT APRÈS LE ROUND ==========")
    cmd_status(sid, a)
    res2 = _decision(sid, rid)
    if res2.get("ok"):
        print()
        print(oracle.build_card(res2, Board(bc)))
    return 0


def cmd_status(sid: int, a) -> int:
    st = _load_state()
    rid = st["runnerId"]
    res = _decision(sid, rid)
    units = res.get("units") or []
    alive = _alive_by_team(units)
    stage = res.get("stageName")
    print(f"[status] stage={stage} turn={res.get('turn')} "
          f"currentPlayer={res.get('currentPlayer')} alive_by_team={alive}")
    for u in units:
        if u.get("alive"):
            pos = u.get("pos") or {}
            print(f"    t{u.get('team')} u{u.get('id')} [{u.get('visualId')}] "
                  f"@({pos.get('col')},{pos.get('row')}) hp={u.get('hp')} "
                  f"{'CTRL' if u.get('ctrl') else 'AI'}")
    if len(alive) <= 1:
        win = next(iter(alive), None)
        print(f"  *** BATTLE FINIE — team gagnante : {win} ***")
    return 0


def cmd_dispose(sid: int, a) -> int:
    st = _load_state()
    _rpc(sid, "disposeRunner", [{"runnerId": st["runnerId"]}], timeout=15)
    print(f"[dispose] runner {st['runnerId']} libéré")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "view", "act", "aiturn",
                                    "status", "dispose", "play"])
    ap.add_argument("kind", nargs="?", default=None,
                    help="pour act: move|ability|finish|endturn")
    ap.add_argument("--spec", default=None,
                    help="play: JSON liste d'actions du tour")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--rank", type=int, default=17)
    ap.add_argument("--roster", type=int, default=5,
                    help="taille de roster pour le tirage ALÉATOIRE "
                         "(ignoré si --p-units/--a-units fournis)")
    ap.add_argument("--p-units", default=None,
                    help="build: MON roster (team 1), ids séparés par virgule "
                         "(ex. 'custoVexilusPraetor,orksKillaKan,...'). "
                         "Sinon tirage aléatoire seedé.")
    ap.add_argument("--a-units", default=None,
                    help="build: roster ADVERSE (team 2), ids séparés par virgule")
    ap.add_argument("--p-mow", default=None,
                    help="build: MoW de MON équipe (1 id, ex. 'ultraDreadnought')")
    ap.add_argument("--a-mow", default=None,
                    help="build: MoW de l'équipe adverse (1 id)")
    ap.add_argument("--mow", action="store_true",
                    help="build: auto-pick 1 MoW aléatoire par équipe "
                         "(si ni --p-mow ni --a-mow)")
    ap.add_argument("--list-pool", action="store_true",
                    help="build: imprime le pool spawnable (units + MoW) et sort")
    ap.add_argument("--advance", type=int, default=0)
    ap.add_argument("--maxpump", type=int, default=2000)
    ap.add_argument("--unit", type=int, default=None)
    ap.add_argument("--caster", type=int, default=None)
    ap.add_argument("--target", type=int, default=None)
    ap.add_argument("--ability", type=int, default=None)
    ap.add_argument("--to", default=None, help="col,row pour move")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    _ensure_ai_trace(sid)
    dispatch = {"build": cmd_build, "view": cmd_view, "act": cmd_act,
                "aiturn": cmd_aiturn, "status": cmd_status,
                "dispose": cmd_dispose, "play": cmd_play}
    return dispatch[a.cmd](sid, a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
