"""#448-r1-r1-r2 -- le SECOND BRAS de `IdunBattle.Operations.MoveUnitOperation$$IsLikeFlying`.

    bool IsLikeFlying(IEntity unit, MoveUnitOptions options) {
        if (UnitExtensions.IsLikeFlying(unit)) return true;      // BRAS 1 -- HasTrait(Flying|Burrow)
        var ov = options.<+0x8>;                                 // Nullable<PathfinderType>
        if (!ov.HasValue) return false;
        return ov.Value == PathfinderType.Fly;                   // BRAS 2 -- l'OVERRIDE d'OPTIONS
    }

Le bras 2 est pose par `IdunBattleLogic.Entities.DSLBehaviors$$FlyUnit`, qui alloue un
`MoveUnitBehaviourOptions` (0x40 octets ZERO) et n'y ecrit QUE `+0x08 = Nullable(3 = Fly)`.

QUEL CANAL, ET POURQUOI PAS `tilesMovedThisTurn`. `MoveUnitOperation$$Execute` produit DEUX listes
par `CalculatePaths` : `path` (8e out-param), dont le pathfinder PORTE l'override ; et
`connectedPath` (9e), qui vient de `IdunBattle.Core.Services.BattleQuery$$GetConnectedPathTo(
entity, from, to)` -- TROIS arguments, ni options ni pathfinderType. Or `RecordTilesMoved` compte
`connectedPath`. **Le canal `actorStats.tilesMovedThisTurn` est donc STRUCTURELLEMENT AVEUGLE au
second bras** ; il ne peut pas servir de discriminant ici (il l'etait pour #448-r1-r1-r1-r1, qui
portait sur le bras 1, lu par `GetPathfinderTypeForUnit`).

Le SEUL effet d'etat du bras 2 est donc, dans `Execute` :

    movementSteps = IsLikeFlying(unit, options) ? GetDistance(path.First(), path.Last())
                                                : path.Count

et `movementSteps` n'a QU'UN lecteur dans tout le binaire (xrefs de
`IdunBattleLogic.Entities.DSLFormulas$$MovementSteps`) :

    ...FullThrottleAbility$$CreateTrigger = On(0x24) & OwnerIsActor
                                         & AmountIsEqualOrGreater(MovementSteps(), Direct(3))
    ...FullThrottleAbility$$CreateBehaviour = If(Maybe(chance = 30), Kill(Caster), null)

MONTAGE. `FullThrottle` greffe sur **`spaceHound` (Tjark)**, HERO du pool, traits
`Hero/Infiltrate/Terrifying` -- ni `Flying` ni `Burrow`, donc **le bras 1 est FAUX** et seul le
bras 2 peut allumer `IsLikeFlying`. Tjark caste `1090 GrapnelLauncher`, dont le `If` final est
`FlyUnit(Caster, <tuile d'ORIGINE de la cible>)` : c'est le seul call-site de `FlyUnit` porte, et
son porteur est le seul NON DEGENERE (`eldarLhykhis`/`EmpyricAmbush` et `bloodDante`/
`LightOfSanguinius` portent le trait `Flying` -- bras 1 deja vrai, donc aucun pouvoir separateur).

DISCRIMINANT, ENONCE AVANT LA MESURE. Chaque vol est classe par sa geometrie MESUREE (position de
Tjark avant/apres le cast), jamais supposee :

    d     = hex_distance(avant, apres)                 <- ce que rend le NATIF si le bras 2 mord
    count = _num_tiles_moved(avant, apres) + 1         <- `path.Count`, ce que rend le port SANS

  bras A (d >= 3 et count >= 3)  CONTROLE POSITIF : les deux modeles predisent VRAI -> ~30 % morts.
        Sans ce bras, un « 0 mort partout » ne prouverait rien (montage inerte).
  bras B (d <  3 et count >= 3)  DISCRIMINANT     : bras 2 -> gate FAUX -> **0 mort** ;
        port SANS le bras 2 -> gate VRAI -> ~30 %. P(0 mort sur n | gate vrai) = 0.7^n.
  bras C (d <  3 et count <  3)  CONTROLE NEGATIF : les deux predisent FAUX -> 0 mort.

Le bras B n'est PAS degenere : `count = d + 1` des que le chemin de marche est direct, donc les
deux modeles rendent des valeurs DIFFERENTES que le seuil 3 separe.

Usage :
    python probe_448_r1_r1_r2_fly_override.py --offline          # etape 0 SEULE (0 runner)
    python probe_448_r1_r1_r2_fly_override.py --rounds 12         # etape 0 + le volet live
    python probe_448_r1_r1_r2_fly_override.py --offline --mutate-no-second-arm   # CONTRE-EPREUVE
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
LOGSDIR = ROOT / "logs"
sys.path.insert(0, str(PYDIR))

ABILITY = "FullThrottle"
GRAFT = "spaceHound"                 # Tjark -- HERO du pool, NI Flying NI Burrow
GRAPNEL = 1090                       # ActiveAbilityType.GrapnelLauncher
THRESHOLD = 3                        # `FullThrottle.constants.movement`


# ------------------------------------------------------------------ ETAPE 0 (offline)
def etape0(mutate_no_second_arm: bool = False) -> int:
    """Cablage du port des DEUX bras, + la GARDE DE FIDELITE qui interdit de propager l'override
    a `_num_tiles_moved`."""
    from engine.runner.operations import movement as MV
    from engine.entities.pathfinding import pathfinders as _pf
    import engine.runner.abilities.behaviours.movement as BM

    bad = 0
    print("== ETAPE 0 (offline) -- les deux bras de MoveUnitOperation$$IsLikeFlying")

    saved = MV._is_like_flying
    if mutate_no_second_arm:
        # CONTRE-EPREUVE : le port d'AVANT #448-r1-r1-r2 -- bras 1 SEUL.
        from engine.entities.pathfinding.fly_pathfinder import is_like_flying as _b1
        MV._is_like_flying = lambda traits, ov: _b1(traits or [])
        print("   [MUTANT] second bras ETEINT (le port d'avant)")
    try:
        fly = int(_pf.PathfinderType.Fly)
        # Table EXHAUSTIVE sur les deux entrees. `7` = TeleportStrikeFly : le natif compare
        # `== 3` STRICTEMENT, donc un type decore ne compte PAS comme volant ici.
        table = [(["Hero"], None, False), (["Hero"], fly, True),
                 (["Hero"], int(_pf.PathfinderType.Walk), False), (["Hero"], 7, False),
                 (["Flying"], None, True), (["Burrow"], None, True), (["Flying"], fly, True)]
        for traits, ov, expect in table:
            got = bool(MV._is_like_flying(traits, ov))
            ok = got == expect
            bad += 0 if ok else 1
            print("     traits=%-10s override=%-4s -> %-5s (attendu %-5s) %s"
                  % (",".join(traits), ov, got, expect, "OK" if ok else "FAUX"))

        # Le champ existe et vaut `None` par defaut (le `Nullable` VIDE de tous les call-sites a
        # options nulles), et il SURVIT a la relance apres override de destination.
        op = MV.MoveUnitOperation(1, (2, 2))
        ok = op.pathfinder_type_override is None
        bad += 0 if ok else 1
        print("   MoveUnitOperation(...).pathfinder_type_override par defaut = %s -> %s"
              % (op.pathfinder_type_override, "OK" if ok else "FAUX"))
        op2 = MV.MoveUnitOperation(1, (2, 2), pathfinder_type_override=fly)
        ok = op2.pathfinder_type_override == fly
        bad += 0 if ok else 1
        print("   ... pose explicitement = %s -> %s"
              % (op2.pathfinder_type_override, "OK" if ok else "FAUX"))

        # La feuille DSL `FlyUnit` est le SEUL call-site qui pose l'override : on le lit dans la
        # SOURCE (le port n'a pas de canal d'introspection sur une Operation deja consommee).
        src = pathlib.Path(BM.__file__).read_text(encoding="utf-8")
        ok = "pathfinder_type_override=int(_pf.PathfinderType.Fly)" in src
        bad += 0 if ok else 1
        print("   feuille FlyUnit pose l'override -> %s" % ("OK" if ok else "MANQUANT"))
        ok = "pathfinder_type_override" not in src.split("class MoveUnit(")[-1]
        bad += 0 if ok else 1
        print("   feuille MoveUnit ne le pose PAS (options nulles au natif) -> %s"
              % ("OK" if ok else "FAUX"))

        # GARDE DE FIDELITE : `_num_tiles_moved` n'accepte PAS l'override. `connectedPath` vient
        # d'un appel a TROIS arguments (`BattleQuery$$GetConnectedPathTo(entity, from, to)`), donc
        # `tilesMovedThisTurn` NE DOIT PAS bouger. Un port qui « propagerait par symetrie » serait
        # INFIDELE -- c'est la faute que cette garde interdit.
        import inspect
        params = list(inspect.signature(MV._num_tiles_moved).parameters)
        ok = not any("override" in p for p in params)
        bad += 0 if ok else 1
        print("   _num_tiles_moved(%s) SANS override -> %s" % (", ".join(params),
                                                               "OK" if ok else "FAUX"))
        params_ms = list(inspect.signature(MV._movement_steps).parameters)
        ok = any("override" in p for p in params_ms)
        bad += 0 if ok else 1
        print("   _movement_steps(%s) AVEC override -> %s" % (", ".join(params_ms),
                                                              "OK" if ok else "FAUX"))
    finally:
        MV._is_like_flying = saved
    return bad


# ------------------------------------------------------------------ VOLET LIVE
def _rpc_factory():
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=120):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}
    return _resolve_session(), rpc


def _build(board: str, seed: int, foes: list, tag: str):
    import catalog_inject as CI
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    state_file = LOGSDIR / ("p448r1r1r2_state_%s.json" % tag)
    bc_path = LOGSDIR / ("p448r1r1r2_bc_%s.json" % tag)

    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    CI.graft_passive_ability(bc, GRAFT, ABILITY)
    bc_path.write_text(json.dumps(bc), encoding="utf-8")

    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--board", board, "--p-units", GRAFT, "--a-units", ",".join(foes), "--no-ai",
           "--seed-bc", str(bc_path), "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        sys.stdout.write((p.stdout or "")[-1800:])
        sys.stdout.write((p.stderr or "")[-1800:])
        raise SystemExit("build KO (%s)" % tag)
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def _units(dv) -> dict:
    out = {}
    for u in (dv.get("units") or []):
        if u.get("id") is None:
            continue
        out[int(u["id"])] = u
    return out


def _pos_by_squad(ob) -> dict:
    """Les positions, indexees par `squadId` -- c'est-a-dire par la MEME cle que
    `decisionView.units[].id` et que `toActivate`.

    ⚠ `decisionView` ne porte PAS `col`/`row` (mesure : ses deux unites rendent `col: None`), et
    `observeBattle` est indexe par `entityId` (78) et non par `squadId` (77). Melanger les deux
    lirait la position d'une AUTRE unite -- c'est le meme piege que `_alive_map` de
    `probe_448_r1_r1_full_throttle.py`, dans l'autre sens."""
    out = {}
    for u in (ob.get("units") or []):
        sq, c, r = u.get("squadId"), u.get("col"), u.get("row")
        if sq is None or c is None or r is None:
            continue
        out[int(sq)] = (int(c), int(r))
    return out


def _dist(a, b) -> int:
    from engine.entities.effects.aura_selectors import hex_distance
    return int(hex_distance(a, b))


def _legal_moves(rpc, sid, rid, uid: int) -> set:
    mov = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    out = set()
    for mu in (mov.get("units") or []):
        if int(mu.get("unitId", -1)) != int(uid):
            continue
        for t in (mu.get("tiles") or []):
            c, r = t.get("col"), t.get("row")
            if c is not None and r is not None:
                out.add((int(c), int(r)))
    return out


def run_live(board: str, seed: int, foes: list, rounds: int, want: int) -> dict:
    """Un runner, `rounds` tours.

    LA GEOMETRIE EST PILOTEE PAR LA CIBLE, PAS PAR TJARK. C'est la seule facon de forcer la
    configuration sans polluer la mesure : tout pas de Tjark emet lui aussi un `On(0x24)` avec
    `movementSteps = path.Count`, donc un repositionnement de 2 pas suffirait a le tuer AVANT le
    cast (`count = 3 >= 3`) et se lirait comme une mort du vol. La cible, elle, ne porte pas le
    passif greffe -- on la deplace de son mouvement PLEIN, sans aucun effet de bord.
    Tjark n'ajuste que d'UN pas (`count = 2 < 3` -> gate FAUX, inoffensif) et seulement s'il le
    faut."""
    from engine.runner.snapshot import load_state
    from engine.runner.operations.movement import _num_tiles_moved
    from engine.entities.pathfinding.board import Board

    tag = "%s_%d_d%d" % (board, seed, want)
    rid = _build(board, seed, foes, tag)
    sid, rpc = _rpc_factory()
    print("== LIVE  board=%s seed=%d want_d=%d runner=%s" % (board, seed, want, rid))
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
    brd = Board(bg["tiles"], adjacency="native_sym")
    casts = []

    def endturn():
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)

    try:
        for turn in range(rounds):
            dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1,
                                           "allAbilities": True}, 150)
            ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
            uu, pos = _units(dv), _pos_by_squad(ob)
            me = next((u for u in uu.values() if u.get("visualId") == GRAFT), None)
            if me is None or not me.get("alive") or pos.get(int(me["id"])) is None:
                print("     t%d : Tjark absent/mort -> fin" % turn)
                break
            mid, mypos = int(me["id"]), pos[int(me["id"])]
            foes_alive = [u for u in uu.values()
                          if u.get("alive") and int(u["id"]) != mid
                          and u.get("team") != me.get("team")
                          and pos.get(int(u["id"])) is not None]
            if not foes_alive:
                print("     t%d : plus d'ennemi vivant -> fin" % turn)
                break
            tgt = min(foes_alive, key=lambda u: _dist(mypos, pos[int(u["id"])]))
            tid = int(tgt["id"])
            d = _dist(mypos, pos[tid])
            to_act = [int(x) for x in (dv.get("toActivate") or [])]

            snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
            ast = rpc(sid, "unitAbilityStates", {"runnerId": rid}, 90)
            st = load_state(dv, ob, snap, board=brd, ability_states=ast)

            # --- TOUR ADVERSE : la CIBLE se place a la distance voulue (mouvement PLEIN) -------
            if tid in to_act and mid not in to_act:
                legal = _legal_moves(rpc, sid, rid, tid)
                cands = sorted(legal, key=lambda p: (abs(_dist(p, mypos) - want),
                                                     _num_tiles_moved(st, tid, pos[tid], p)))
                if cands and _dist(cands[0], mypos) != d:
                    dst = cands[0]
                    rpc(sid, "applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": tid,
                        "to": {"col": dst[0], "row": dst[1]}}}, 120)
                    print("     t%d : cible u%s %s -> %s (d %d -> %d)"
                          % (turn, tid, pos[tid], dst, d, _dist(dst, mypos)))
                else:
                    print("     t%d : cible u%s deja placee (d=%d)" % (turn, tid, d))
                endturn()
                continue
            if mid not in to_act:
                endturn()
                continue

            # --- TOUR DE TJARK ----------------------------------------------------------------
            if d > want:
                # Un SEUL pas (count = 2 < 3 -> le gate ne peut pas mordre).
                legal = _legal_moves(rpc, sid, rid, mid)
                cands = [p for p in sorted(legal)
                         if _num_tiles_moved(st, mid, mypos, p) == 1]
                cands.sort(key=lambda p: abs(_dist(p, pos[tid]) - want))
                if cands:
                    dst = cands[0]
                    rpc(sid, "applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": mid,
                        "to": {"col": dst[0], "row": dst[1]}}}, 120)
                    print("     t%d : Tjark %s -> %s (d %d -> %d)"
                          % (turn, mypos, dst, d, _dist(dst, pos[tid])))
                else:
                    print("     t%d : aucun pas de 1 pour Tjark (d=%d)" % (turn, d))
                endturn()
                continue
            if d < want:
                print("     t%d : d=%d < want=%d, on laisse la cible s'ecarter" % (turn, d, want))
                endturn()
                continue

            # --- LE CAST -----------------------------------------------------------------------
            before = mypos
            res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": mid, "targetId": tid,
                "abilityType": GRAPNEL}}, 150)
            a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
            if not (res.get("ok") and a0.get("ok")):
                print("     t%d : cast REFUSE (%s) -> endturn" % (turn, str(res)[:200]))
                endturn()
                continue
            dv2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1,
                                            "allAbilities": True}, 150)
            ob2 = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
            me2 = _units(dv2).get(mid)
            dead = (me2 is None) or (not me2.get("alive"))
            after = _pos_by_squad(ob2).get(mid)
            if after is None or after == before:
                print("     t%d : PAS DE VOL (avant=%s apres=%s dead=%s) -- NON MESURE"
                      % (turn, before, after, dead))
                endturn()
                continue
            dd = _dist(before, after)
            count = _num_tiles_moved(st, mid, before, after) + 1
            arm = ("A" if (dd >= THRESHOLD and count >= THRESHOLD)
                   else "B" if count >= THRESHOLD else "C")
            casts.append({"turn": turn, "before": list(before), "after": list(after),
                          "d": dd, "count": count, "arm": arm, "dead": bool(dead)})
            print("     t%d : VOL %s -> %s  d=%d count=%d  bras=%s  %s"
                  % (turn, before, after, dd, count, arm, "MORT" if dead else "vivant"))
            if dead:
                break
            endturn()
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
    return {"board": board, "seed": seed, "want": want, "casts": casts}


def _verdict(tot: dict) -> int:
    """Le verdict, sur l'AGREGAT. Un run isole ne porte que quelques vols : c'est l'union des runs
    qui donne au bras B sa force (`0.7 ** n`)."""
    b, aa = tot.get("B"), tot.get("A")
    print("\n== VERDICT")
    if not b:
        print("   bras B (DISCRIMINANT) NON MESURE -> rien de tranche")
        return 1
    if not aa or aa["morts"] == 0:
        print("   bras A (controle positif) sans mort -> le montage n'a PAS ete prouve mordant ;")
        print("   un 0 mort en B ne prouverait alors rien (montage possiblement inerte).")
        return 1
    if b["morts"] == 0:
        print("   bras A tue (%d/%d) ET bras B ne tue JAMAIS (0/%d, P = %.5f) ->"
              % (aa["morts"], aa["n"], b["n"], 0.7 ** b["n"]))
        print("   SECOND BRAS CONFIRME : le natif lit la DISTANCE, pas path.Count.")
        return 0
    print("   bras B tue (%d/%d) -> le natif lit path.Count : SECOND BRAS REFUTE"
          % (b["morts"], b["n"]))
    return 1


def _tally(casts: list) -> dict:
    tot = {}
    for c in casts:
        t = tot.setdefault(c["arm"], {"n": 0, "morts": 0})
        t["n"] += 1
        t["morts"] += 1 if c["dead"] else 0
    return tot


def _print_tally(tot: dict, n: int) -> None:
    print("\n== BILAN (vols mesures : %d)" % n)
    for k in ("A", "B", "C"):
        t = tot.get(k)
        if t:
            print("   bras %s : %d essai(s), %d mort(s)   P(0 mort | gate vrai) = %.5f"
                  % (k, t["n"], t["morts"], 0.7 ** t["n"]))
        else:
            print("   bras %s : 0 essai -- NON MESURE" % k)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=None,
                    help="glob de fichiers --out a AGREGER (aucun runner monte)")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--mutate-no-second-arm", action="store_true")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seeds", default="777")
    ap.add_argument("--foes", default="tauCrisis")
    ap.add_argument("--rounds", type=int, default=14)
    ap.add_argument("--want", type=int, default=2, help="distance hex Tjark<->cible au cast")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    if a.report:
        import glob
        casts = []
        for f in sorted(glob.glob(a.report)):
            d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
            casts.extend(d.get("casts") or [])
            print("   + %s (%d vol(s))" % (pathlib.Path(f).name, len(d.get("casts") or [])))
        tot = _tally(casts)
        _print_tally(tot, len(casts))
        return _verdict(tot)

    bad = etape0(a.mutate_no_second_arm)
    print("   -> etape 0 : %d anomalie(s)" % bad)
    if a.offline:
        if a.mutate_no_second_arm:
            print("VERDICT CONTRE-EPREUVE : %s (le mutant DOIT rougir)"
                  % ("ROUGE (attendu)" if bad else "VERT -- LE MUTANT NE MORD PAS"))
            return 0 if bad else 1
        print("VERDICT OFFLINE : %s" % ("PASS" if bad == 0 else "FAIL"))
        return 1 if bad else 0

    allc = []
    for s in [int(x) for x in a.seeds.split(",") if x.strip()]:
        r = run_live(a.board, s, [x for x in a.foes.split(",") if x], a.rounds, a.want)
        allc.extend(r["casts"])
    tot = _tally(allc)
    _print_tally(tot, len(allc))
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps({"casts": allc, "tot": tot}, indent=1),
                                       encoding="utf-8")
    return _verdict(tot)


if __name__ == "__main__":
    raise SystemExit(main())
