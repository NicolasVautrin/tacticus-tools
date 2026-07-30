"""probe #27-4g -- A/B causal LIVE de PlasmaGrenade (1098).

CE QUI EST TESTE
----------------
`IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$CalculateCustomUtility` porte DEUX choses, et ce
probe les separe :

    n = |battleQuery.<slot itf 0x7d = GetAdjacentEnemies>(target, ownerId(caster), false)|
    u = n * U( prediction(CIBLE, base = Get(minDmg), hits = GetNumberConstant(0x32 = nrOfHits_2)) )
    if (u == Fix64(0)) u = BaseUtility.<statics+0x18>     # -> CalculateActionUtility rend null

* le terme est LINEAIRE et POSITIF en `n` (Stikkbomb, meme mold, nie sa somme parce qu'il compte des
  AMIS) -- donc il peut RENVERSER l'argmax par cible ;
* la somme nulle est un VETO, pas une utilite nulle : le natif ne genere AUCUNE action.

MONTAGE (board MC1_67), et pourquoi il est fabrique comme ca
------------------------------------------------------------
PORTEUR. Les deux seules unites qui portent 1098 sont `eldarSmnGuardian` (SUMMON) et
`eldarNpc1Guardian` (npc) ; le summon n'a pas d'invocateur et `buildNormalizedBC` refuse les deux.
=> porteur GREFFE : `ActiveAbilities` d'`eldarAutarch` (Aeldari, pool) remplace par `[1098]` dans une
COPIE du seed BC (`case-92` §5bis). Le natif charge le playbook PAR ABILITY
(`PlaybookDatabase.LoadPlaybook(abilityType)`), et il le PROUVE en emettant `ActiveAbilityMessage(1098)`.
La formule ne lit aucune stat ni trait du caster (uniquement le board et la config d'ability), donc la
greffe ne la deforme pas.

BRAS -- le CASTER et la CIBLE PRINCIPALE sont FIGES, seuls les deux autres ennemis bougent :

  C0 : n(A) = 0  (B et C relegues loin de A)   -> VETO : le natif ne propose JAMAIS 1098
  C1 : n(A) = 1  (B colle a A)                 -> 1098 redevient generable
  C2 : n(A) = 2  (B et C colles a A)           -> et le natif PREFERE A a B malgre pair(A) < pair(B)

BRUIT ASSUME, et pourquoi il n'empeche pas la mesure
-----------------------------------------------------
`IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$GetUseProbability` rend `Fix64(1)/Fix64(3)`, et
`IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate` en fait un TIRAGE. Le natif ne propose donc 1098
qu'environ un dry-run sur trois. Le probe REPETE `--tirages` dry-runs par bras et agrege :
  - en C0, `0/K` est concluant (a p = 1/3, `(2/3)^K` est negligeable des K = 12) ;
  - en C1/C2, seuls les tirages OU 1098 est proposee portent l'information de CIBLE.
Le moteur, lui, est deterministe et ne modelise pas cette porte -- ecart NOMME, hors #27.

Usage (depuis scripts/python, ASCII only) :
    python probe_27_4g_plasma_grenade_ab.py --build [--engine] [--tirages=18]
    python probe_27_4g_plasma_grenade_ab.py --engine      # re-joue sur le runner du state-file
    python rl_duel.py dispose --state-file <LOGS>/rs_pg_ab.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import probe_27_3_live as L
from engine.entities.active_ability_type import ActiveAbilityType

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_pg_graft.json"
STATE = LOGS / "rs_pg_ab.json"
BOARD = "MC1_67"
SEED = 909
RANK = "17"

PLASMA_GRENADE = int(ActiveAbilityType.PlasmaGrenade)     # 1098
NORMAL = 69

GRAFT_ON = "eldarAutarch"
P_UNITS = "eldarAutarch,eldarRanger"
A_UNITS = "orksWarboss,necroWarden,astraCreed"

CASTER_VID = "eldarAutarch"        # porte 1098 apres greffe
ALLY_VID = "eldarRanger"           # allie relegue -- il ne compte JAMAIS (le set est ENEMIES-only)
A_VID = "orksWarboss"              # CIBLE PRINCIPALE, FIGEE dans les 3 bras
B_VID = "necroWarden"              # voisin mobile #1
C_VID = "astraCreed"               # voisin mobile #2

CASTER_TILE = "2,4"                # FIGE : d = 2 de A (portee 1098 = 2)
A_TILE = "4,4"                     # FIGE
ALLY_TILE = "0,0"
# Les deux voisins mobiles : colles a A (bras C1/C2) ou relegues (bras C0).
NB = hexgeo.neighbors(4, 4)        # voisinage hex REEL de A, jamais suppose
B_NEAR = "%d,%d" % NB[0]
C_NEAR = "%d,%d" % NB[1]
# Bras C0 : B garde sa tuile de SPAWN (deja loin de A) et C est ecarte de B pour qu'aucune des trois
# cibles n'ait de voisin ennemi. `C_FAR` est choisie ATTEIGNABLE en un `act move` depuis le spawn --
# une tuile trop lointaine fait REFUSER le move, et les trois bras degenerent en un seul etat.
C_FAR = "3,8"

TIRAGES_DEFAULT = 18


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _move(rid: int, unit: int, to: str) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", to,
          "--state-file", str(STATE), "--runner", str(rid)])


def _dv(rid: int) -> dict:
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row))} -- les ids ne sont JAMAIS hardcodes."""
    out = {}
    for u in (_dv(rid).get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = (u.get("id"), (p.get("col"), p.get("row")))
    return out


def write_graft_seed_bc() -> None:
    """Copie du seed BC PARTAGE avec `ActiveAbilities` de `GRAFT_ON` remplace par `[1098]`.
    N'ECRIT JAMAIS le seed BC partage (meme discipline que `catalog_inject --out`)."""
    import rl_collect_batch as R
    bc = R._load_seed_bc(None)
    n = 0
    for u in bc.get("Units") or []:
        if u.get("Id") == GRAFT_ON:
            u["ActiveAbilities"] = [PLASMA_GRENADE]
            n += 1
    if n != 1:
        raise SystemExit("greffe impossible : %d entree(s) %r dans BC.Units" % (n, GRAFT_ON))
    LOGS.mkdir(parents=True, exist_ok=True)
    SEED_BC.write_text(json.dumps(bc), encoding="utf-8")
    print("[graft] %s.ActiveAbilities = [%d] -> %s" % (GRAFT_ON, PLASMA_GRENADE, SEED_BC))


def _assert_placed(rid: int, want) -> None:
    """Un `act move` REFUSE ne leve rien : les bras degenereraient en UN seul etat, ou l'accord
    moteur<->natif est trivialement vrai (piege mesure le 2026-07-30 sur #27-4)."""
    pos = {i: p for _v, (i, p) in _units(rid).items()}
    bad = [(u, to, pos.get(u)) for u, to in want
           if pos.get(u) != tuple(int(x) for x in to.split(","))]
    if bad:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s"
                         % ["u%s voulu=%s obtenu=%s" % (u, to, got) for u, to, got in bad])


def build() -> int:
    write_graft_seed_bc()
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--rank", RANK,
          "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
          "--state-file", str(STATE)])
    rid = _runner_id()
    ids = {v: i for v, (i, _p) in _units(rid).items()}
    want = ((ids[A_VID], A_TILE), (ids[CASTER_VID], CASTER_TILE), (ids[ALLY_VID], ALLY_TILE))
    for unit, to in want:
        _move(rid, unit, to)
    _assert_placed(rid, want)
    return rid


def _adjacent_enemy_count(rid: int, target_vid: str) -> int:
    """Mirror LIVE, sans passer par le port : combien d'ENNEMIS du caster occupent une tuile
    hex-adjacente a la cible. Sert de controle independant du `n` que le moteur calcule."""
    u = _units(rid)
    tpos = u[target_vid][1]
    nb = set(hexgeo.neighbors(tpos[0], tpos[1]))
    ctrl = {}
    for x in (_dv(rid).get("units") or []):
        ctrl[x.get("visualId")] = bool(x.get("ctrl"))
    return sum(1 for v, (_i, p) in u.items()
               if v != target_vid and not ctrl.get(v) and p in nb)


def _legal_targets(rid: int, caster: int) -> set:
    """Cibles legales de 1098 selon le NATIF (`abilityTargets`, mirror de `TargetingQuery`). Rendues
    en `kind == "unit"` (masque preset+flags de `...PlasmaGrenadeAbility$$.ctor`)."""
    at = L._rpc("abilityTargets", [{"runnerId": rid, "casterId": caster,
                                    "abilityType": PLASMA_GRENADE}])
    out = set()
    for x in (at.get("units") or []):
        for a in (x.get("abilities") or []):
            if a.get("abilityId") != PLASMA_GRENADE:
                continue
            for t in (a.get("targets") or []):
                if t.get("kind") == "unit" and t.get("targetId") is not None:
                    out.add(int(t["targetId"]))
    return out


def _native(rid: int, caster: int, enemies: list, tirages: int) -> tuple[dict, dict]:
    """pairUtility natives (etage PAIRE, SANS le custom) + distribution des dry-runs.

    Le tirage `GetUseProbability` = 1/3 impose la repetition : on rend un histogramme
    {(abilityType, targetId): compte} sur `tirages` dry-runs READ-ONLY."""
    pairs = {}
    for tgt in enemies:
        for ab in (NORMAL, PLASMA_GRENADE):
            r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": caster,
                                        "targetId": tgt, "abilityType": ab}])
            pairs[(ab, tgt)] = r.get("utility")
    hist = {}
    for _ in range(tirages):
        dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
        for x in (dr.get("units") or []):
            if x.get("unitId") != caster:
                continue
            key = tuple(sorted((m.get("cls"), m.get("abilityType"), m.get("targetId"))
                               for m in (x.get("proposed") or [])))
            hist[key] = hist.get(key, 0) + 1
    return pairs, hist


def _engine(rid: int, caster: int) -> dict:
    """Trois decisions MOTEUR sur le MEME etat : telle quelle / VETO desarme / custom force a 0."""
    import engine_validate as EV
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)

    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, caster, wt, predictor)
    pb = PB.REGISTRY.get(PLASMA_GRENADE)
    per_target = {}
    for e in (ctx.enemies or []):
        t = e.get("id")
        per_target[t] = (pb._adjacent_enemy_count(ctx, t),
                         repr(pb.calculate_custom_utility(ctx, ctx.origin, t, PLASMA_GRENADE)))

    on = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    orig = type(pb).calculate_custom_utility

    # MUTATION ADVERSARIALE 1 -- VETO DESARME : le custom rend 0.0 au lieu de la sentinelle. C'est
    # exactement l'etat du port AVANT ce commit (aucun override -> base = Fix64(0)), et c'est ce que
    # la garde doit voir ROUGE en C0.
    type(pb).calculate_custom_utility = lambda self, c, t, target, aid: 0.0
    try:
        noveto = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig

    # MUTATION ADVERSARIALE 2 -- terme CONSTANT au lieu de LINEAIRE (n remplace par min(n,1)) : si le
    # montage ne distingue pas les deux, la mesure ne prouve pas la linearite et il faut le DIRE.
    def _boolean(self, c, t, target, aid):
        n = self._adjacent_enemy_count(c, target)
        return orig(self, c, t, target, aid) if n <= 1 else orig(self, c, t, target, aid) / float(n)
    type(pb).calculate_custom_utility = _boolean
    try:
        boolean = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    return {"on": (on.get("ability"), on.get("target")), "to": on.get("to"),
            "noveto": (noveto.get("ability"), noveto.get("target")),
            "boolean": (boolean.get("ability"), boolean.get("target")),
            "per_target": per_target}


def measure(rid: int, label: str, engine: bool, tirages: int) -> dict:
    u = _units(rid)
    caster = u[CASTER_VID][0]
    enemies = [u[v][0] for v in (A_VID, B_VID, C_VID)]
    pairs, hist = _native(rid, caster, enemies, tirages)
    n_live = {v: _adjacent_enemy_count(rid, v) for v in (A_VID, B_VID, C_VID)}
    legal = _legal_targets(rid, caster)
    print("  --- %s ---" % label)
    print("      positions : caster=%s A=%s B=%s C=%s"
          % (u[CASTER_VID][1], u[A_VID][1], u[B_VID][1], u[C_VID][1]))
    print("      n (ennemis adjacents, mesure LIVE independante du port) = %s" % n_live)
    # SANS ca, un bras « le natif ne propose pas 1098 » serait ambigu : VETO du custom, ou simple
    # absence de cible legale ? Le ciblage est mesure, pas suppose.
    print("      cibles LEGALES de 1098 (abilityTargets natif) = %s" % sorted(legal))
    print("      pairUtility natives : %s"
          % {("ab%d" % ab, "u%d" % t): pairs[(ab, t)] for (ab, t) in sorted(pairs)})
    for k, c in sorted(hist.items(), key=lambda kv: -kv[1]):
        print("      natif x%-3d : %s" % (c, list(k)))
    row = {"pairs": pairs, "hist": hist, "caster": caster, "n_live": n_live, "legal": legal,
           "ids": {v: u[v][0] for v in (A_VID, B_VID, C_VID)}}
    if engine:
        e = _engine(rid, caster)
        print("      moteur : on=%s to=%s | (n, custom) par cible = %s"
              % (e["on"], e["to"], e["per_target"]))
        print("      moteur MUTE : veto desarme -> %s | terme rendu BOOLEEN -> %s"
              % (e["noveto"], e["boolean"]))
        row["engine"] = e
    return row


def _native_1098_targets(row) -> set:
    """Cibles pour lesquelles le natif a propose 1098 sur AU MOINS un tirage."""
    out = set()
    for key in row["hist"]:
        for (cls, ab, tgt) in key:
            if cls == "ActiveAbilityMessage" and ab == PLASMA_GRENADE:
                out.add(tgt)
    return out


def run_ab(rid: int, engine: bool, tirages: int) -> dict:
    ids = {v: i for v, (i, _p) in _units(rid).items()}
    rows = {}
    _move(rid, ids[C_VID], C_FAR)
    _assert_placed(rid, ((ids[C_VID], C_FAR),))
    rows["C0"] = measure(rid, "C0 : n(A)=0 -- VETO attendu (aucune action 1098)", engine, tirages)
    _move(rid, ids[B_VID], B_NEAR)
    _assert_placed(rid, ((ids[B_VID], B_NEAR),))
    rows["C1"] = measure(rid, "C1 : n(A)=1 -- 1098 redevient generable", engine, tirages)
    _move(rid, ids[C_VID], C_NEAR)
    _assert_placed(rid, ((ids[C_VID], C_NEAR),))
    rows["C2"] = measure(rid, "C2 : n(A)=2 -- le custom doit RENVERSER l'argmax par cible", engine,
                         tirages)
    return rows


def main() -> int:
    argv = sys.argv[1:]
    engine = "--engine" in argv
    tirages = int(next((a.split("=", 1)[1] for a in argv if a.startswith("--tirages=")),
                       str(TIRAGES_DEFAULT)))
    rid = build() if "--build" in argv else _runner_id()
    print("runner=%d board=%s seed=%d tirages=%d" % (rid, BOARD, SEED, tirages))
    rows = run_ab(rid, engine, tirages)

    print("\n=== SYNTHESE ===")
    ok = True
    a_id = rows["C0"]["ids"][A_VID]
    b_id = rows["C0"]["ids"][B_VID]
    for k in ("C0", "C1", "C2"):
        r = rows[k]
        tg = _native_1098_targets(r)
        line = "  %-3s : n(A)=%d  natif propose 1098 sur %s (sur %d tirages)" % (
            k, r["n_live"][A_VID], sorted(tg) or "AUCUNE cible", tirages)
        if engine:
            e = r["engine"]
            eng_1098 = (e["on"][0] == PLASMA_GRENADE)
            # Critere d'accord, honnete face au tirage 1/3 : le moteur propose 1098 SSI le natif l'a
            # proposee au moins une fois, et sur la MEME cible.
            agree = (eng_1098 == bool(tg)) and (not eng_1098 or e["on"][1] in tg)
            ok = ok and agree
            line += " | moteur -> %s %s" % (e["on"], "MATCH" if agree else "DIVERGE")
        print(line)

    print("  VETO (C0) : le natif n'a JAMAIS propose 1098 sur %d tirages : %s"
          % (tirages, "OUI" if not _native_1098_targets(rows["C0"]) else "NON"))
    t2 = _native_1098_targets(rows["C2"])
    pa = rows["C2"]["pairs"].get((PLASMA_GRENADE, a_id))
    pb_ = rows["C2"]["pairs"].get((PLASMA_GRENADE, b_id))
    if pa is not None and pb_ is not None:
        print("  C2 RENVERSEMENT : pair(1098, A=u%d)=%.6f < pair(1098, B=u%d)=%.6f ; natif cible %s"
              % (a_id, pa, b_id, pb_, sorted(t2) or "-"))
        print("    => le natif prend %s : %s"
              % ("A (la cible la plus ENTOUREE)" if a_id in t2 else "B",
                 "TERME LINEAIRE POSITIF EN n" if (a_id in t2 and pa < pb_)
                 else "non discriminant sur ce montage"))
    if engine:
        rouge0 = rows["C0"]["engine"]["noveto"][0] == PLASMA_GRENADE
        print("  GARDE ROUGE (veto desarme, C0) : le moteur propose 1098 la ou le natif ne le fait "
              "JAMAIS -> %s" % ("ROUGE (attendu)" if rouge0 else "vert -- la garde ne mord pas"))
        diff_bool = any(rows[k]["engine"]["boolean"] != rows[k]["engine"]["on"] for k in rows)
        print("  MUTATION 'terme BOOLEEN' : change la decision du moteur -> %s"
              % ("OUI (la linearite est exercee)" if diff_bool
                 else "NON -- ce montage ne distingue pas lineaire de booleen, le DIRE"))
    print("(pense a disposer le runner : rl_duel.py dispose --state-file %s)" % STATE)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
