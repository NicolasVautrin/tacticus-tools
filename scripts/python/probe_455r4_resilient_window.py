"""Probe #455-r4 -- MESURE du montage de
`test_env_fire_tile_migration_live.py::test_env_fire_tile_dot_applies_resilient_cap_live`,
rouge sur `master` avec `pytest.fail("cible morte avant la fenetre discriminante")`.

CRITERE tranche par ce probe : le rouge accuse-t-il le MONTAGE (le pilotage ne sait pas amener
la cible dans la fenetre ou le cap `Resilient` discrimine) ou le PORT (le cap est mal porte) ?

Ce que le natif fait, et qui definit la fenetre (RE) :
  `IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` cape le degat a
  `currentHealth - 1` quand la cible porte `Resilient`, SAUF si
  `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` rend vrai -- ce qui arrive des que
  `(healthDamage - initialHealth) / initialHealth * 100 >= overkillDmgPctOfHealth` (=100), donc
  des que `dot >= 2 x hp`. La fenetre discriminante est donc `hp` dans `(dot/2, dot]`.

VOLET `descente` -- deroule le pilotage du test en journalisant hp AVANT attaque, APRES attaque
(= le degat de l'attaque normale) et APRES tick (= le degat du DoT). Rend le pas de descente par
tour, a confronter a la LARGEUR de la fenetre (`dot - dot/2 = dot/2`).

VOLET `remaining` -- mesure si `--unit-stat "<id>:RemainingHealth=<v>"` MORD au deploiement
(hp courant != hp max), c.-a-d. si le montage peut DEMARRER dans la fenetre au lieu d'y descendre
a l'aveugle. Piege connu (`--unit-stat Shield`, #342) : un champ de `BC.Units` peut etre ecrit
dans le BC et JAMAIS lu par le natif -- d'ou cette mesure, et pas une supposition.

VOLET `tick` -- ISOLE le tick du DoT (aucune attaque ce tour-la) : c'est lui qui a montre que le
degat lu par le volet `descente` melait attaque ET tick, l'attaque terminant l'activation de la
SEULE p-unit et faisant basculer le tour toute seule.

VOLET `montage` -- joue le montage CANDIDAT (PV poses dans la fenetre + 2e p-unit inerte) et
journalise chaque etape, dont `currentPlayer` apres l'attaque : la preuve que le tour reste ouvert.

VOLET `frontiere` -- GENERALISATION : le meme montage a plusieurs niveaux de PV, de part et d'autre
des DEUX bornes (`> dot` cap inerte / `(dot/2, dot]` cap a 1 PV / `<= dot/2` bypass -> mort).
`--seed`/`--board` pour rejouer sur une autre geometrie.

Usage : python probe_455r4_resilient_window.py
        [--volet descente|remaining|tick|montage|frontiere|all] [--seed S] [--board B]  (ASCII only)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import hexgeo  # noqa: E402
import gameconfig as GC  # noqa: E402

ROOT = PYDIR.parents[1]
BOARD = "MC1_67"
W, H, MV = 7, 9, 3
P_UNIT = "adeptRetributor"          # arme hits=4 DamageProfile=Flame Range=2 -> POSE le feu
A_UNIT = "astraYarrick"             # traits ['Hero', 'Resilient']
HP_TARGET = 500000


def rpc(sid, m, args, t=90):
    r = _rpc(sid, m, [args], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def build(seed, state, extra=None):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", BOARD,
           "--p-units", P_UNIT, "--a-units", A_UNIT, "--hp-target", str(HP_TARGET),
           "--state-file", state, *(extra or [])]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        sys.stdout.write((p.stdout or "")[-1500:])
        sys.stdout.write((p.stderr or "")[-2000:])
        raise SystemExit("build KO")
    return json.loads(Path(state).read_text(encoding="utf-8"))["runnerId"]


def _alive(dv):
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _setup(sid, rid):
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    vin = next((u["id"] for u in _alive(dv) if u.get("visualId") == P_UNIT), None)
    tgt = next((u["id"] for u in _alive(dv) if u.get("visualId") != P_UNIT), None)
    norm = None
    for u in (dv.get("units") or []):
        if u.get("id") == vin:
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal":
                    norm = ab.get("id") if ab.get("id") is not None else ab.get("abilityId")
    return vin, tgt, norm, dv.get("currentPlayer")


def _hp(sid, rid, tgt):
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    u = next((x for x in (dv.get("units") or []) if x.get("id") == tgt), None)
    if u is None or not u.get("alive"):
        return None
    return int(u.get("hp") or 0)


def _endturn(sid, rid):
    try:
        rpc(sid, "applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)
    except Exception:
        pass


def _skip_enemy(sid, rid, me):
    for _ in range(6):
        if rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60).get("currentPlayer") == me:
            return
        _endturn(sid, rid)


def _fire_on(sid, rid, pos):
    tm = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    rows = tm.get("tiles") if isinstance(tm, dict) else tm
    for t in (rows or []):
        if (t.get("col"), t.get("row")) == pos:
            for e in (t.get("effects") or []):
                if str(e.get("name") or "").lower().startswith("fire"):
                    return True
    return False


def _attack(sid, rid, vin, tgt, norm):
    """Approche a distance 2 EXACTEMENT puis attaque. Rend True si l'attaque a ete lancee."""
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt), None)
    vu = next((u for u in _alive(dv) if u.get("id") == vin), None)
    if tu is None or not tu.get("alive") or vu is None:
        return False
    vp, tp = _pos(vu), _pos(tu)
    occ = {_pos(u) for u in _alive(dv)} - {vp}
    if hexgeo.distance(vp, tp) != 2:
        ring2 = sorted([t for t in hexgeo.ring(tp[0], tp[1], 2)
                        if 0 <= t[0] < W and 0 <= t[1] < H and t not in occ
                        and hexgeo.distance(vp, t) <= MV],
                       key=lambda t: hexgeo.distance(vp, t))
        cands = ring2 or sorted(
            [t for t in hexgeo.disk(vp[0], vp[1], MV)
             if 0 <= t[0] < W and 0 <= t[1] < H and t not in occ and t != vp],
            key=lambda t: hexgeo.distance(t, tp))[:6]
        for t in cands:
            r = rpc(sid, "applyAction", {"runnerId": rid, "actions": [
                {"kind": "move", "unitId": vin, "to": {"col": t[0], "row": t[1]}}]}, 60)
            if isinstance(r, dict) and r.get("ok", True) and not r.get("error"):
                vp = t
                break
    if hexgeo.distance(vp, tp) != 2:
        return False
    rpc(sid, "applyAction", {"runnerId": rid, "actions": [
        {"kind": "ability", "casterId": vin, "targetId": tgt, "abilityType": norm}]}, 90)
    return True


def volet_descente(sid, rounds=12):
    state = str(ROOT / "logs" / "_probe455r4_descente.json")
    rid = build("90101", state)
    print("[descente] runner=%d" % rid)
    try:
        vin, tgt, norm, me = _setup(sid, rid)
        hp_max = int(_hp(sid, rid, tgt) or 0)     # PV pleins au deploiement == PV MAX
        pct = int(GC.global_value("fireDmgPct") or 0)
        dot = int(round(hp_max * pct / 100))     # armure forcee a 0 par --hp-target
        print("[descente] tgt=%d hpMax=%d fireDmgPct=%d -> dot=%d fenetre=(%d, %d] largeur=%d"
              % (tgt, hp_max, pct, dot, dot // 2, dot, dot - dot // 2))
        for k in range(rounds):
            hp0 = _hp(sid, rid, tgt)
            if hp0 is None:
                print("[descente] tour %d : CIBLE MORTE" % k)
                break
            burning = _fire_on(sid, rid, _pos(next(
                u for u in _alive(rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60))
                if u.get("id") == tgt)))
            inwin = dot // 2 < hp0 <= dot
            print("[descente] tour %d : hp=%d burning=%s in_window=%s" % (k, hp0, burning, inwin))
            if inwin and burning:
                print("[descente] FENETRE ATTEINTE au tour %d (hp=%d)" % (k, hp0))
                break
            ok = _attack(sid, rid, vin, tgt, norm)
            hp1 = _hp(sid, rid, tgt)
            _endturn(sid, rid)
            _skip_enemy(sid, rid, me)
            hp2 = _hp(sid, rid, tgt)
            print("           attaque=%s dmg_attaque=%s dmg_tick=%s pas=%s"
                  % (ok, None if hp1 is None else hp0 - hp1,
                     None if (hp1 is None or hp2 is None) else hp1 - hp2,
                     None if hp2 is None else hp0 - hp2))
            if hp2 is None:
                print("[descente] tour %d : CIBLE MORTE apres le tick" % k)
                break
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)


def volet_remaining(sid, remaining=80000):
    """`--unit-stat RemainingHealth` MORD-il ? (hp courant != hp max au deploiement)"""
    state = str(ROOT / "logs" / "_probe455r4_remaining.json")
    rid = build("90101", state,
                extra=["--unit-stat", "%s:RemainingHealth=%d" % (A_UNIT, remaining)])
    print("[remaining] runner=%d demande RemainingHealth=%d" % (rid, remaining))
    try:
        ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        for u in (ob.get("units") or []):
            if u.get("visualId") == A_UNIT:
                print("[remaining] %s hp=%s hpMax=%s -> MORD=%s"
                      % (A_UNIT, u.get("hp"), u.get("hpMax"),
                         int(u.get("hp") or 0) != int(u.get("hpMax") or 0)))
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)


def _tile_fire(sid, rid, pos):
    """Effets de la tuile `pos` (nom + tours restants) -- pour voir SI et COMBIEN de temps ca brule."""
    tm = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    rows = tm.get("tiles") if isinstance(tm, dict) else tm
    for t in (rows or []):
        if (t.get("col"), t.get("row")) == pos:
            return [(e.get("name"), e.get("remainingTurns"), e.get("turnsLeft"))
                    for e in (t.get("effects") or [])]
    return None


def volet_tick(sid, rounds=8, endturns=6):
    """Ou tombe le tick du DoT ? On amene la tuile a bruler (comme `_drive_until_burning`), puis on
    passe les tours UN PAR UN en journalisant currentPlayer / hp / effets de la tuile."""
    state = str(ROOT / "logs" / "_probe455r4_tick.json")
    rid = build("90101", state)
    print("[tick] runner=%d" % rid)
    try:
        vin, tgt, norm, me = _setup(sid, rid)
        print("[tick] vin=%s tgt=%s me=%s" % (vin, tgt, me))
        burning = False
        for k in range(rounds):
            dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt), None)
            if tu is None or not tu.get("alive"):
                print("[tick] cible morte avant que la tuile brule")
                return
            tp = _pos(tu)
            if _fire_on(sid, rid, tp):
                burning = True
                print("[tick] tuile %s EN FEU au tour %d (hp=%s) effets=%s"
                      % (str(tp), k, tu.get("hp"), _tile_fire(sid, rid, tp)))
                break
            _attack(sid, rid, vin, tgt, norm)
            _endturn(sid, rid)
            _skip_enemy(sid, rid, me)
        if not burning:
            print("[tick] la tuile n'a jamais brule")
            return
        for n in range(endturns):
            dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt), None)
            tp = _pos(tu) if tu else None
            print("[tick] etape %d : currentPlayer=%s hp=%s pos=%s tuile=%s"
                  % (n, dv.get("currentPlayer"), (tu or {}).get("hp"), str(tp),
                     _tile_fire(sid, rid, tp) if tp else None))
            _endturn(sid, rid)
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)


IDLE = "astraDreir"          # 2e p-unit JAMAIS activee -> empeche la bascule AUTOMATIQUE de tour
                             # (passif `ToughToKill` = regen + reduction SELF, aucune aura sur la cible)


def _board_tiles(sid, rid):
    """Tuiles REELLES du board -- les bornes `W`/`H` en dur ne valent que pour `MC1_67`, et sur un
    board plus grand elles ecartaient toutes les candidates (`distance 2 non atteinte`)."""
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    return {(t.get("col"), t.get("row")) for t in ((bg or {}).get("tiles") or [])}


def _approach(sid, rid, vin, tgt, want=2, tiles=None):
    """Rapproche l'attaquant SANS attaquer, en ne visant que des tuiles REELLEMENT atteignables
    (`aiMovableTiles` = le BFS natif, creuse par blockers/terrain). Deviner une tuile par la seule
    geometrie hexagonale echouait des que le board n'etait pas `MC1_67` -- pas une limite du montage,
    une limite du choix de tuile. Rend la distance atteinte."""
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt), None)
    vu = next((u for u in _alive(dv) if u.get("id") == vin), None)
    if tu is None or vu is None:
        return None
    vp, tp = _pos(vu), _pos(tu)
    if hexgeo.distance(vp, tp) == want:
        return want
    mov = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60) or {}
    reach = []
    for mu in (mov.get("units") or []):
        if mu.get("unitId") == vin:
            reach = [(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                     if t.get("col") is not None]
    occ = {_pos(u) for u in _alive(dv)} - {vp}
    reach = [t for t in reach if t not in occ]
    if not reach:
        return hexgeo.distance(vp, tp)
    # d'abord la distance VOULUE ; sinon la tuile qui s'en rapproche le plus
    reach.sort(key=lambda t: (abs(hexgeo.distance(t, tp) - want), hexgeo.distance(t, tp)))
    for t in reach[:8]:
        r = rpc(sid, "applyAction", {"runnerId": rid, "actions": [
            {"kind": "move", "unitId": vin, "to": {"col": t[0], "row": t[1]}}]}, 60)
        if isinstance(r, dict) and r.get("ok", True) and not r.get("error"):
            vp = t
            break
    return hexgeo.distance(vp, tp)


def volet_montage(sid, start_pct=90, rounds=8):
    """Montage CANDIDAT : PV courants poses DANS la fenetre au build, 2e p-unit inerte pour garder
    la main sur le moment du tick. Journalise chaque etape pour prouver que le tick est ISOLE."""
    state = str(ROOT / "logs" / "_probe455r4_montage.json")
    pct = int(GC.global_value("fireDmgPct") or 0)
    dot_attendu = int(round(HP_TARGET * pct / 100))          # armure 0 (--hp-target) -> percage no-op
    start = int(round(dot_attendu * start_pct / 100))
    rid = build("90101", state,
                extra=["--p-units", "%s,%s" % (P_UNIT, IDLE),
                       "--unit-stat", "%s:RemainingHealth=%d" % (A_UNIT, start)])
    print("[montage] runner=%d dot_attendu=%d start=%d fenetre=(%d, %d]"
          % (rid, dot_attendu, start, dot_attendu // 2, dot_attendu))
    try:
        vin, tgt, norm, me = _setup(sid, rid)
        print("[montage] vin=%s tgt=%s me=%s hp0=%s" % (vin, tgt, me, _hp(sid, rid, tgt)))
        d = None
        for k in range(rounds):
            d = _approach(sid, rid, vin, tgt)
            print("[montage] approche tour %d : distance=%s hp=%s" % (k, d, _hp(sid, rid, tgt)))
            if d == 2:
                break
            _endturn(sid, rid)
            _skip_enemy(sid, rid, me)
        if d != 2:
            print("[montage] ECHEC : distance 2 non atteinte")
            return
        rpc(sid, "applyAction", {"runnerId": rid, "actions": [
            {"kind": "ability", "casterId": vin, "targetId": tgt, "abilityType": norm}]}, 90)
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt), None)
        hp1 = int((tu or {}).get("hp") or 0)
        tp = _pos(tu)
        print("[montage] APRES attaque : currentPlayer=%s (me=%s) hp=%d in_window=%s tuile=%s"
              % (dv.get("currentPlayer"), me, hp1, dot_attendu // 2 < hp1 <= dot_attendu,
                 _tile_fire(sid, rid, tp)))
        _endturn(sid, rid)
        _skip_enemy(sid, rid, me)
        dv2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        tu2 = next((u for u in (dv2.get("units") or []) if u.get("id") == tgt), None)
        alive = bool(tu2 and tu2.get("alive"))
        hp2 = int((tu2 or {}).get("hp") or 0) if alive else 0
        print("[montage] APRES tick : alive=%s hp=%d tick=%d (cap attendu a 1 PV)"
              % (alive, hp2, hp1 - hp2))
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)


def volet_frontiere(sid, pcts=(120, 90, 65, 55, 40), seed="90101", board=None, rounds=8):
    """GENERALISATION : le meme montage joue a plusieurs niveaux de PV, de part et d'autre des DEUX
    bornes de la fenetre. Attendu (RE) : au-dessus de `dot` le cap ne mord pas (degat plein, survie
    a `hp - dot`) ; dans `(dot/2, dot]` il cape a `hp-1` ; a `hp <= dot/2` `IsOverkill` rend vrai et
    le cap est BYPASSE -> la cible MEURT. C'est la frontiere que le montage repare doit respecter."""
    global BOARD
    old_board = BOARD
    if board:
        BOARD = board
    pct = int(GC.global_value("fireDmgPct") or 0)
    dot_attendu = int(round(HP_TARGET * pct / 100))
    print("[frontiere] seed=%s board=%s dot_attendu=%d fenetre=(%d, %d]"
          % (seed, BOARD, dot_attendu, dot_attendu // 2, dot_attendu))
    try:
        for sp in pcts:
            state = str(ROOT / "logs" / ("_probe455r4_front_%d.json" % sp))
            start = int(round(dot_attendu * sp / 100))
            rid = build(seed, state,
                        extra=["--p-units", "%s,%s" % (P_UNIT, IDLE),
                               "--unit-stat", "%s:RemainingHealth=%d" % (A_UNIT, start)])
            try:
                vin, tgt, norm, me = _setup(sid, rid)
                tiles = _board_tiles(sid, rid)
                d = None
                for _ in range(rounds):
                    d = _approach(sid, rid, vin, tgt, tiles=tiles)
                    if d == 2:
                        break
                    _endturn(sid, rid)
                    _skip_enemy(sid, rid, me)
                if d != 2:
                    print("[frontiere] start=%d : distance 2 non atteinte" % start)
                    continue
                rpc(sid, "applyAction", {"runnerId": rid, "actions": [
                    {"kind": "ability", "casterId": vin, "targetId": tgt,
                     "abilityType": norm}]}, 90)
                dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
                tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt), None)
                if tu is None or not tu.get("alive"):
                    print("[frontiere] start=%d : morte a l'attaque" % start)
                    continue
                hp1 = int(tu.get("hp") or 0)
                _endturn(sid, rid)
                _skip_enemy(sid, rid, me)
                dv2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
                tu2 = next((u for u in (dv2.get("units") or []) if u.get("id") == tgt), None)
                alive = bool(tu2 and tu2.get("alive"))
                hp2 = int((tu2 or {}).get("hp") or 0) if alive else 0
                if hp1 > dot_attendu:
                    regime = "au-dessus (cap inerte)"
                    attendu = "hp %d" % (hp1 - dot_attendu)
                elif hp1 > dot_attendu // 2:
                    regime = "fenetre (cap actif)"
                    attendu = "hp 1"
                else:
                    regime = "sous dot/2 (IsOverkill -> bypass)"
                    attendu = "MORTE"
                print("[frontiere] start=%-7d hp_avant_tick=%-7d %-32s attendu=%-8s "
                      "lu: alive=%-5s hp=%d" % (start, hp1, regime, attendu, alive, hp2))
            finally:
                rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
    finally:
        BOARD = old_board


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--volet", default="all",
                    choices=["descente", "remaining", "tick", "montage", "frontiere", "all"])
    ap.add_argument("--seed", default="90101")
    ap.add_argument("--board", default=None)
    ap.add_argument("--remaining", type=int, default=80000)
    a = ap.parse_args()
    (ROOT / "logs").mkdir(exist_ok=True)
    sid = _resolve_session()
    if a.volet in ("descente", "all"):
        volet_descente(sid)
    if a.volet in ("tick", "all"):
        volet_tick(sid)
    if a.volet in ("remaining", "all"):
        volet_remaining(sid, a.remaining)
    if a.volet in ("montage", "all"):
        volet_montage(sid)
    if a.volet in ("frontiere", "all"):
        volet_frontiere(sid, seed=a.seed, board=a.board)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
