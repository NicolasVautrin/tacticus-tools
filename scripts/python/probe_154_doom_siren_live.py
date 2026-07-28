"""probe #154 -- MESURE des evenements d'un cast LIVE de DoomSiren (1199, `emperKakophonist`).

But : etablir la FORME REELLE des tags d'evenement de degat pour cette ability (le test
`test_doom_siren_live.py` en depend : il extrait `Amount`/`Target_Id` filtres sur
`Active_Ability_Type`). Le probe MESURE, il n'asserte rien.

Ce qu'il fait : build isole, drive les positions (Adamatar au contact d'une cible qui a 2 voisins
ennemis), cast LIVE, puis DUMP de tous les tags d'evenement rencontres + le detail PV avant/apres.

Usage (depuis scripts/python, session Frida warmee) :
    python probe_154_doom_siren_live.py
ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
STATE = PYDIR.parent.parent / "logs" / "runners" / "probe154_doomsiren.json"
ADAMATAR = "emperKakophonist"
ENEMIES = "orksNob,tyranTyrantGuard,templAggressor"
ABILITY = 1199


def main() -> int:
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        r = R._rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--board", "MC1_67",
         "--state-file", str(STATE), "--p-units", ADAMATAR, "--a-units", ENEMIES,
         "--hp-target", "500000", "--crit", "0,0", "--block-target", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[probe154] build KO: %s" % (p.stderr or p.stdout or "")[-400:])
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    print("[probe154] runnerId=%d" % rid)

    try:
        bg = rpc("boardGraph", {"runnerId": rid})
        tiles = {t["id"]: (t["col"], t["row"]) for t in bg["tiles"]}
        walk = {t["id"]: t.get("walkable", True) for t in bg["tiles"]}

        def dv():
            return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

        def alive(d):
            return [u for u in (d.get("units") or []) if u.get("alive")]

        def upos(u):
            q = u.get("pos") or {}
            return (q.get("col"), q.get("row")) if q.get("col") is not None else None

        def move(uid, c):
            return rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 40)

        d = dv()
        adam = next(u for u in alive(d) if u.get("visualId") == ADAMATAR)
        me = adam["owner"]
        print("[probe154] currentPlayer(initial)=%s me=%s" % (d.get("currentPlayer"), me))

        ens = [u for u in alive(d) if u.get("owner") != me]
        print("[probe154] ennemis=%s" % [(u["id"], u["visualId"]) for u in ens])

        # geometrie : C (Adamatar), T voisin de C, deux voisins de T pour les additionnels
        geom = None
        for tid, C in sorted(tiles.items()):
            if not walk.get(tid):
                continue
            nb_c = [c for t2, c in sorted(tiles.items())
                    if walk.get(t2) and hexgeo.distance(C, c) == 1]
            for T in nb_c:
                slots = [c for t3, c in sorted(tiles.items())
                         if walk.get(t3) and hexgeo.distance(T, c) == 1 and c != C]
                if len(slots) >= 2:
                    geom = (C, T, slots[0], slots[1])
                    break
            if geom:
                break
        if geom is None:
            print("[probe154] pas de geometrie")
            return 1
        C, T, S1, S2 = geom
        move(adam["id"], C)
        move(ens[0]["id"], T)
        move(ens[1]["id"], S1)
        move(ens[2]["id"], S2)
        # LES PLACEMENTS D'ABORD, MON TOUR ENSUITE : bouger des unites (des DEUX camps) consomme des
        # activations et fait basculer le tour ; en repassant par des `endturn` APRES le placement, le
        # caster entame un tour NEUF (flags de tour purges par `StartTurnOperation$$ResetUnit`), donc
        # il n'a PAS bouge ce tour-la -- indispensable des qu'un masque porte `CasterHasNotMoved`.
        d = dv()
        for _ in range(12):
            if d.get("currentPlayer") == me:
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            d = dv()
        print("[probe154] currentPlayer(avant cast)=%s" % d.get("currentPlayer"))
        pos = {u["id"]: upos(u) for u in alive(d)}
        print("[probe154] C=%s T=%s S1=%s S2=%s | pos=%s" % (C, T, S1, S2, pos))
        hp0 = {u["id"]: u.get("hp") for u in alive(d)}

        # VERDICT NATIF de ciblage AVANT le cast : `abilityTargets` rend, par ability, les cibles
        # legales (`now` = castable sans bouger) et la raison de refus quand il y en a une.
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": adam["id"]}, 60)
        print("[probe154] abilityTargets = %s" % json.dumps(at, sort_keys=True)[:1500])
        adam_live = next(u for u in alive(d) if u["id"] == adam["id"])
        print("[probe154] adamatar flags/abilities = %s"
              % json.dumps({k: v for k, v in adam_live.items()
                            if k in ("id", "hasMoved", "canAct", "abilities", "activeAbilities",
                                     "turnFinished", "activeAbilityUsed")}, sort_keys=True)[:800])

        # SNAPSHOT PRE-CAST (le meme quadruplet que le harnais de test) -> rejeu OFFLINE ensuite.
        pre = {"dv": d,
               "ob": rpc("observeBattle", {"runnerId": rid}, 40),
               "snap": rpc("combatSnapshot", {"runnerId": rid}, 60),
               "rng": rpc("dumpRng", {"runnerId": rid}, 30)}

        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": adam["id"], "targetId": ens[0]["id"],
            "abilityType": ABILITY}}, 60)
        a0 = (res.get("actions") or [{}])[0]
        print("[probe154] cast ok=%s actionOk=%s mutated=%s"
              % (res.get("ok"), a0.get("ok"), res.get("mutated")))
        if a0.get("error"):
            print("[probe154] error=%s" % a0.get("error"))
        evs = a0.get("events") or []
        print("[probe154] %d events" % len(evs))
        keys = set()
        for i, e in enumerate(evs):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else td
            if isinstance(td, dict):
                keys |= set(td)
            # n'imprimer QUE ce qui ressemble a du degat (sinon 80 lignes de bruit de cascade)
            if isinstance(td, dict) and any(k for k in td
                                            if "Amount" in k or "Damage" in k or "Hit" in k):
                print("  [%02d] tags=%s" % (i, json.dumps(td, sort_keys=True)[:500]))
        print("[probe154] TOUTES les cles de tags rencontrees = %s" % sorted(keys))

        d2 = dv()
        hp1 = {u["id"]: u.get("hp") for u in alive(d2)}
        print("[probe154] PV avant=%s" % hp0)
        print("[probe154] PV apres=%s" % hp1)
        print("[probe154] delta=%s"
              % {k: (hp0.get(k) or 0) - (hp1.get(k) or 0) for k in hp0 if hp1.get(k) is not None})
        for u in alive(d2):
            names = [x.get("name") for x in (u.get("effects") or [])]
            print("[probe154] effets u%s(%s) = %s" % (u["id"], u["visualId"], names))

        # ---------------- volet OFFLINE : meme cast, meme etat, meme MT ----------------
        from engine.runner.snapshot import load_state
        from engine.runner.runner import Runner
        from engine.runner.messages import ActiveAbilityMessage
        from engine.runner.prng import IntBasedMersenneTwister
        from engine.entities.pathfinding.board import Board

        st = load_state(pre["dv"], pre["ob"], pre["snap"],
                        board=Board(bg["tiles"], adjacency="native_sym"))
        if isinstance(pre["rng"], dict) and pre["rng"].get("mt"):
            r = IntBasedMersenneTwister()
            r.mt = list(pre["rng"]["mt"]); r.mti = pre["rng"]["mti"]
            st.rng = r
        eff_before = [e.name for e in (st.effects.by_unit.get(adam["id"], []) if st.effects else [])
                      if not e.consumed]
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=adam["id"], target_id=ens[0]["id"],
                                          ability_type=ABILITY))
        last = runner.ability_handler.last or {}
        off = {ens[0]["id"]: (last.get("main_attack") or {}).get("per_hit")}
        for s in (last.get("splash") or []):
            off[s["target"]] = (s.get("attack") or {}).get("per_hit")
        eff_after = [e.name for e in (st.effects.by_unit.get(adam["id"], []) if st.effects else [])
                     if not e.consumed]
        print("[probe154] OFFLINE per_hit = %s" % {k: off[k] for k in sorted(off)})
        print("[probe154] OFFLINE effets Adamatar avant=%s apres=%s" % (eff_before, eff_after))

        # ETAGE CRIT : la CritChance d'Adamatar APRES le cast (le stat-mod pose par Thrilled). Si elle
        # est > 0 des deux cotes, le crit-roll existe des deux cotes et l'ecart n'est qu'un RANG.
        from engine.entities.stats import StatType
        from engine.runner.components import StatsComponent
        sc = st.get_entity(adam["id"]).get_component(StatsComponent)
        us = getattr(sc.ctx, "stats", None) if sc is not None else None
        print("[probe154] OFFLINE CritChance(Adamatar) apres cast = %s"
              % (us.get_stat(int(StatType.CRIT_CHANCE), 0) if us is not None else None))

        # VERDICT DU PROBE (mesure du 2026-07-28, seed 777 / MC1_67, 3 ennemis) :
        #   live u77 [931, 1036, 893] == offline u77 -> la CIBLE PRINCIPALE est BIT-EXACTE ;
        #   live u79 [1367, 1284, 1245] vs offline [1367, 1379, 1553] -> le 1er coup de la cible
        #   ADDITIONNELLE est exact, les suivants divergent ; live u81 coup 0 porte
        #   `Attack_DidCrit: 1`.
        # CritChance(Adamatar) apres cast = 15 DES DEUX COTES -> le stat-mod du trait `ThrillSeekers`
        # (effet `Thrilled` 1434, `+thrillSeekersExtraCritChance`) est POSE et APPLIQUE offline comme
        # live. L'ecart n'est donc PAS une absence de port : c'est le RANG auquel la modification
        # devient effective PENDANT une attaque multi-cibles (live, elle mord des le 2e coup de la 2e
        # cible ; offline, plus tard). Etage PARTAGE (pose + refresh de stat-mod intra-attaque),
        # EXTERIEUR a DoomSiren -- cf. le residu nomme dans `test_doom_siren_live.py`.
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        STATE.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
