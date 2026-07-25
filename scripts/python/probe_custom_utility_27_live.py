#!/usr/bin/env python
"""Validation LIVE des overrides `CalculateCustomUtility` de la tranche #27-1 (Herald, Drachnyen).

Deux A/B CAUSAUX : dans chaque paire d'etats, une SEULE entree bascule la condition du terme
natif ; on confronte le choix d'action du MOTEUR a celui de l'IA NATIVE (`aiDryRunAllUnits`,
read-only) sur le MEME etat. Les utilites de PAIRE sont verifiees au scoreur natif
(`pairUtility`) pour ecarter tout confond de prediction avant de conclure sur le terme d'ACTION.

(A) HeraldOfTheApocalypse (1020) IdunBattle.AI.Playbook.Loki.HeraldOfTheApocalypsePlaybook$$CalculateCustomUtility -- blackHaarken.
    Geometrie caster/ennemi FIGEE ; seul un APPAT allie bouge :
      - appat HORS de la portee d'arme de l'ennemi -> aucun ennemi atteignable n'est menacant
        -> custom = W(HeraldOfTheApocalypse_CannotKillEnemy)=50 -> natif = HERALD ;
      - appat DANS la portee -> custom = 0 -> natif = attaque NORMALE.
    L'ennemi est `astraOrdnance` (arme portee 3) : la bascule tombe EXACTEMENT a d=3/d=4,
    ce qui exclut une feuille d'adjacence.

(B) Drachnyen (1029) IdunBattle.AI.Playbook.Loki.DrachnyenPlaybook$$CalculateCustomUtility -- blackAbaddon.
    Confond de PAIRE neutralise : Drachnyen FIXE les PV du caster a 4729 -> `--hp-player 4729`
    rend le set-health neutre (paire native = 0). Caster LOIN (0 ennemi adjacent a sa tuile
    courante) ; on ajoute/retire un 2e ennemi adjacent a la TUILE D'ATTAQUE :
      - 1 ennemi adjacent -> custom 0 -> natif = attaque NORMALE ;
      - 2 ennemis adjacents -> custom = W(Drachnyen_MultipleAdjacentUnits)=10 -> natif = DRACHNYEN.

Un seul runner reutilise (state-file dedie), dispose en fin de passe. ASCII only.
Usage : python probe_custom_utility_27_live.py    (exit 0 = OK)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import hexgeo  # noqa: E402
from engine import weights as W  # noqa: E402
from engine.playbook import scene as _scene  # noqa: E402
from engine_validate import engine_decide  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "rl-state" / "custom-utility-27-live.json"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(p_units: str, a_units: str, extra: list) -> int | None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, "rl_duel.py", "build", "--seed", "4242",
            "--state-file", str(STATE), "--board", "MC1_67",
            "--p-units", p_units, "--a-units", a_units, "--roster", "2", *extra]
    proc = subprocess.run(args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-400:])
        return None
    return json.loads(STATE.read_text())["runnerId"]


def _find(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis), None)


def _move(sid, rid, uid, p):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 90)


def _reset_activation(sid, rid, cid):
    """Fait tourner les tours jusqu'a ce que le caster soit a nouveau CONTROLE avec son
    activation (il ne bouge pas) : les `applyAction move` de mise en place l'ont consommee."""
    for _ in range(8):
        d = _r(sid, "decisionView", {"runnerId": rid}, 120)
        cu = next((u for u in (d.get("units") or []) if u.get("id") == cid), {})
        if cu.get("ctrl") and cu.get("hasAction"):
            return True
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    return False


def _native_ability(sid, rid, cid):
    dry = _r(sid, "aiDryRunAllUnits", {"runnerId": rid}, 120)
    nat = next((u for u in (dry.get("units") or []) if u.get("unitId") == cid), None)
    for m in ((nat or {}).get("proposed") or []):
        if m.get("cls") == "ActiveAbilityMessage":
            return m.get("abilityType"), m.get("targetId")
    return None, None


def _confront(sid, rid, wt, predictor, cid, label, expect_ab, fails):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    if predictor is not None:
        _scene.refresh_shields(predictor, lambda m, b, t: _r(sid, m, b, t), rid)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    eng = engine_decide(sid, rid, dv, mbu, cid, wt, predictor)
    nat_ab, nat_tgt = _native_ability(sid, rid, cid)
    eng_ab = eng.get("ability") if eng.get("kind") == "ability" else None
    ok = (nat_ab == expect_ab) and (eng_ab == nat_ab)
    print(f"  [{label}] natif ab={nat_ab} tgt={nat_tgt} | moteur kind={eng.get('kind')} "
          f"ab={eng_ab} tgt={eng.get('target')} to={eng.get('to')} -> "
          f"{'OK' if ok else 'X'} (attendu {expect_ab})")
    if nat_ab != expect_ab:
        fails.append(f"{label}: natif ab={nat_ab}, attendu {expect_ab} (scenario non exerce)")
    elif eng_ab != nat_ab:
        fails.append(f"{label}: moteur ab={eng_ab} != natif ab={nat_ab}")


def herald(sid, wt, fails):
    print("(A) HeraldOfTheApocalypse (1020) IdunBattle.AI.Playbook.Loki.HeraldOfTheApocalypsePlaybook$$CalculateCustomUtility -- blackHaarken")
    rid = _build("blackHaarken,astraDreir", "astraOrdnance", [])
    if rid is None:
        fails.append("A: build KO")
        return None
    print("    runner", rid)
    predictor = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    walk = {(t["col"], t["row"]) for t in (bg.get("tiles") or []) if t.get("walkable")}
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    c, e, b = _find(dv, "blackHaarken"), _find(dv, "astraOrdnance"), _find(dv, "astraDreir")
    if not (c and e and b):
        fails.append("A: unites absentes")
        return rid
    cid, eid, bid = c["id"], e["id"], b["id"]
    cpos = (c["pos"]["col"], c["pos"]["row"])
    epos = sorted(p for p in walk if hexgeo.distance(cpos, p) == 4)[0]
    _move(sid, rid, eid, epos)
    for tag, d, expect in (("appat DANS la portee de l'ennemi (d=3) -> custom 0", 3, 69),
                           ("appat HORS portee (d=4) -> custom W=50", 4, 1020)):
        cands = sorted(p for p in walk if hexgeo.distance(p, epos) == d
                       and hexgeo.distance(p, cpos) >= 5)
        if not cands:
            fails.append(f"A: pas de tuile appat a d={d}")
            continue
        _move(sid, rid, bid, cands[0])
        _reset_activation(sid, rid, cid)
        _confront(sid, rid, wt, predictor, cid, tag, expect, fails)
    return rid


def drachnyen(sid, wt, fails):
    print("(B) Drachnyen (1029) IdunBattle.AI.Playbook.Loki.DrachnyenPlaybook$$CalculateCustomUtility -- blackAbaddon")
    rid = _build("blackAbaddon,astraDreir", "worldTerminator,blackTerminator",
                 ["--hp-target", "90000", "--hp-player", "4729"])
    if rid is None:
        fails.append("B: build KO")
        return None
    print("    runner", rid)
    predictor = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    tiles = bg.get("tiles") or []
    walk = {(t["col"], t["row"]) for t in tiles if t.get("walkable")}
    id2pos = {t.get("id"): (t.get("col"), t.get("row")) for t in tiles}
    neigh = {(t.get("col"), t.get("row")): [id2pos[n] for n in (t.get("neighbours") or [])
                                            if n in id2pos] for t in tiles}
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    c = _find(dv, "blackAbaddon")
    t = _find(dv, "worldTerminator")
    x = _find(dv, "blackTerminator")
    a = _find(dv, "astraDreir")
    if not (c and t and x and a):
        fails.append("B: unites absentes")
        return rid
    cid, tid, xid, aid = c["id"], t["id"], x["id"], a["id"]
    tpos, TA, cpos = (2, 4), (2, 3), (0, 2)
    if tpos not in walk or TA not in walk or cpos not in walk:
        fails.append("B: geometrie MC1_67 inattendue")
        return rid
    xpos = next((n for n in neigh[TA] if n in walk and n != tpos
                 and n not in neigh.get(tpos, []) and n != cpos), None)
    far = sorted(p for p in walk if hexgeo.distance(p, tpos) >= 5)
    if xpos is None or len(far) < 2:
        fails.append("B: geometrie appat introuvable")
        return rid
    for tag, xp, expect in (
            ("1 ennemi adjacent a la tuile d'attaque -> custom 0", far[0], 69),
            ("2 ennemis adjacents a la tuile d'attaque -> custom W=10", xpos, 1029)):
        _move(sid, rid, tid, tpos)
        _move(sid, rid, xid, xp)
        _move(sid, rid, aid, far[1])
        _move(sid, rid, cid, cpos)
        _reset_activation(sid, rid, cid)
        _confront(sid, rid, wt, predictor, cid, tag, expect, fails)
    return rid


def main() -> int:
    sid = _resolve_session()
    wt = W.load()
    fails: list = []
    rid = None
    try:
        rid = herald(sid, wt, fails)
        if rid is not None:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
            rid = None
        rid = drachnyen(sid, wt, fails)
    finally:
        if rid is not None:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
    print("\n==== RESULT ====")
    if fails:
        for f in fails:
            print("FAIL", f)
        return 2
    print("PASS : Herald (1020) et Drachnyen (1029) -- les DEUX bras de chaque A/B causal "
          "sont exerces cote natif ET reproduits par le moteur.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
