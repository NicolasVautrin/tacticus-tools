#!/usr/bin/env python
"""#236 -- les GATES D'ENTREE de la feuille de mouvement `MinDistanceToClosestEnemy(17)`.

`<EvaluateMovementInSteps>IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
court-circuite la feuille sur QUATRE gates, AVANT tout calcul de distance -- chacun rend
`Fix64.FromInt(0)` (soit 0.0, PAS `NO_PATH_UTILITY`) :

  1. `case.Unit == null`                                            (`case+0x10`)
  2. `IdunBattle.Entities.UnitExtensions$$IsNonAttacking(case.Unit)`  (trait 0x409 = 1033)
  3. `case.ClosestEnemy == null`                                    (`case+0x20`)
  4. `!IdunBattle.AI.Utilities.UnitCanBeDamagedUtility$$UnitCanBeDamaged(case.Unit, case.ClosestEnemy)`
     = ClosestEnemy `Impervious` (trait 0x1c = 28) ET `GetStat(unit, 9 = CriticalChance) == 0`

Aucun n'etait porte (ni face LIVE ni face OFFLINE) : le port attribuait un terme de distance la
ou le natif rend zero -> il PREFERE des tuiles que le natif n'evalue pas. La degradation est
PERMISSIVE et STRUCTURELLEMENT INVISIBLE en agrement (`MovementActionGenerator.generate` est un
argmax pur : un ecart UNIFORME ne deplace aucun choix). D'ou ce probe, qui confronte TUILE PAR
TUILE et jamais par un taux d'accord.

MONTAGE DU GATE 3 (le seul des quatre qui soit CONFRONTABLE LIVE avec des unites du pool) :
un roster adverse compose a 100 % de porteurs du trait `TeleportStrike`. Au premier tour, les
cinq portent l'effet `TeleportStrike_TeleportingIn` -> `IdunBattle.Entities.UnitExtensions$$IsTargetable`
est FAUX -> `FindClosestEnemy` ne retient AUCUN candidat -> `ClosestEnemy == null`, et le RPC
`pathDistToEnemies` le dit par son champ STRUCTURE `noTargetableEnemies`.
Les ennemis restent VIVANTS et POSITIONNES (`ctx.epos` non vide), donc l'ancien port basculait
sur son repli HEX et rendait `wMin * hexdist` != 0 la ou le natif rend 0.

Gates 2 et 4 : leurs porteurs de kit sont EXCLUSIVEMENT npc (`orksNpc4AmmoGrot` /
`orksNpc5LootGrotTeam` pour NonAttacking ; les trois `LootObj_Strongbox_*` pour Impervious) et
AUCUN ne passe `buildNormalizedBC` ("v2 patch: system error") -> non spawnables en runner. Le
gameconfig n'accorde ces traits par AUCUNE ability (`AddTrait`). Ils sont donc exerces ici sur la
face OFFLINE, en posant le trait dans le substrat que `HasTrait` lit reellement
(`UnitContext.traits` = `BaseUnitComponent+0x48`, ce qu'ecrit le leaf DSL `AddTrait`).

REGLE DE LECTURE DU VERDICT : chaque etape porte un STATUT explicite -- `OK` (exercee ET
conforme), `DIVERGE` (exercee, non conforme) ou `NON EXERCE` (le montage n'a pas forme ce qui
devait etre mesure). Un `NON EXERCE` ECHOUE le probe au meme titre qu'un `DIVERGE` : un accord
sur une etape non exercee est un accord VIDE. Seul un `PENDING` (dependance nommee a une fenetre
de reinject) ne fait pas echouer, et il est affiche en clair au verdict.

DEUX REGIMES, et ils ne couvrent PAS les memes gates -- c'est pour cela que le defaut les monte
tous les deux :
  * `gate`    (roster adverse 100 % TeleportStrike) : gate 3 sur les deux faces. Le gate 2 n'y est
    PAS confrontable -- le gate 3 mord AVANT lui, donc le terme est deja nul et poser le trait ne
    prouve rien. La version anterieure de ce probe le comptait pourtant comme conforme : un vert
    sur une etape non exercee, exactement ce que le statut `NON EXERCE` existe pour attraper.
  * `nominal` (roster ordinaire) : non-regression des termes, gate 2 (AddTrait NonAttacking) et
    identite du ClosestEnemy (`closestEnemyId`).

Usage (depuis scripts/python, session Frida deja warmee) :
  python probe_236_mindist_gates.py --state-file <ABSOLU>.json    # monte les DEUX regimes
  python probe_236_mindist_gates.py --runner <rid>                # regime `gate` sur un runner monte
  python probe_236_mindist_gates.py --runner <rid> --nominal      # regime `nominal`
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine import weights  # noqa: E402
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.ai import state_bridge as _sb  # noqa: E402
from engine.entities.pathfinding.board import Board as _Board  # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait  # noqa: E402
from engine.playbook import scene as _scene  # noqa: E402
from engine.runner.components import StatsComponent  # noqa: E402
from engine.runner.snapshot import load_state  # noqa: E402
from engine.utilities.move import (MIN_DIST_UTILITY, UtilityMovementCase,  # noqa: E402
                                   is_non_attacking)

PYDIR = Path(__file__).resolve().parent

# Roster adverse 100 % `TeleportStrike` -> les cinq sont `TeleportStrike_TeleportingIn` au tour 1,
# donc NON CIBLABLES -> `FindClosestEnemy` rend null. Tous dans `rl_duel --list-pool` (rank 17).
DEEP_STRIKE_ROSTER = "bloodDante,blackTerminator,darkaTerminator,spaceRockfist,worldTerminator"
MOVER_ROSTER = "ultraTitus,spaceStormcaller"

OK, DIVERGE, UNEXERCISED, PENDING = "OK", "DIVERGE", "NON EXERCE", "PENDING"


class Report:
    """Journal des etapes. Un `NON EXERCE` compte comme un echec -- pas comme un silence."""

    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []
        self.live_crit = None      # `GetStat(mover, 9)` LUE en live -- portee reelle du gate 4

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.rows.append((name, status, detail))
        print("   [%-10s] %-46s %s" % (status, name, detail))

    def count(self, status: str) -> int:
        return sum(1 for _n, s, _d in self.rows if s == status)

    def verdict(self) -> int:
        print("\n== VERDICT #236 ==")
        for name, status, detail in self.rows:
            print("   %-10s %-46s %s" % (status, name, detail))
        bad, une, pend = (self.count(DIVERGE), self.count(UNEXERCISED), self.count(PENDING))
        print("   -> %d non conforme(s), %d non exercee(s), %d en attente de reinject"
              % (bad, une, pend))
        if bad or une:
            print("   RESULTAT : ECHEC")
            return 1
        if pend:
            print("   RESULTAT : OK SOUS RESERVE (voir les PENDING ci-dessus)")
            return 0
        print("   RESULTAT : OK")
        return 0


def _mk_rpc(sid: int):
    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return (r.get("result") or {}) if isinstance(r, dict) else {}
    return rpc


def _build(state_file: str, seed: int, board: str, a_units: str) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--p-units", MOVER_ROSTER, "--a-units", a_units, "--state-file", state_file]
    out = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True)
    for line in (out.stdout or "").splitlines():
        if line.startswith("[build] runnerId="):
            return int(line.split("runnerId=")[1].split()[0])
    print(out.stdout)
    print(out.stderr, file=sys.stderr)
    raise RuntimeError("build KO")


def _rows(ctx, wt, case):
    """Terme MinDist par tuile du movable set, avec et sans le `case` (donc avec/sans gates)."""
    order = [(t["col"], t["row"]) for t in ctx.move_tiles]
    out = []
    for t in order:
        u_no = MIN_DIST_UTILITY.evaluate_movement(
            t, ctx.tgt_epos or ctx.epos, wt, ctx.pathdist_by_pos, case=None)
        u_yes = MIN_DIST_UTILITY.evaluate_movement(
            t, ctx.tgt_epos or ctx.epos, wt, ctx.pathdist_by_pos, case=case)
        out.append((t, u_no, u_yes))
    return out


def _check_face(rep: Report, label: str, rows, expect_zero: bool) -> None:
    """Confronte TUILE PAR TUILE. Trois refus de vert vide, dans cet ordre :
      - aucune tuile               -> rien confronte ;
      - (regime gate) terme deja nul SANS le gate -> le gate ne prouverait rien ;
      - (regime nominal) tous les termes nuls     -> la garde ne verrouille rien."""
    if not rows:
        rep.add(label, UNEXERCISED, "movable set vide -- aucune tuile confrontee")
        return
    if not any(u_no != 0.0 for _t, u_no, _u in rows):
        rep.add(label, UNEXERCISED,
                "terme deja nul SANS gate sur les %d tuiles -- montage non discriminant"
                % len(rows))
        return
    bad = [(t, u_no, u_yes) for t, u_no, u_yes in rows
           if not ((u_yes == 0.0) if expect_zero else (u_yes == u_no))]
    print("     %-10s %-16s %-16s" % ("tile", "port SANS gate", "port AVEC gate"))
    for t, u_no, u_yes in rows[:6]:
        print("     %-10s %-16s %-16s" % (t, u_no, u_yes))
    if len(rows) > 6:
        print("     ... (%d tuiles au total)" % len(rows))
    rep.add(label, DIVERGE if bad else OK,
            "%d tuiles, %d non conformes (attendu natif = %s)"
            % (len(rows), len(bad), "0 partout (gate)" if expect_zero else "inchange"))


def run_regime(rep: Report, rpc, wt, rid: int, unit: int | None, nominal: bool) -> None:
    """Confronte UN regime. `nominal` False = montage gate 3 (roster 100 % TeleportStrike)."""
    tag = "nominal" if nominal else "gate3"
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    mov = rpc("aiMovableTiles", {"runnerId": rid})
    mov_by_unit = {m.get("unitId"): m for m in (mov.get("units") or [])}
    mine = [u for u in (dv.get("units") or []) if u.get("ctrl") and u.get("alive")]
    uid = unit if unit is not None else (mine[0].get("id") if mine else None)
    if uid is None:
        rep.add("[%s] montage" % tag, UNEXERCISED, "aucune unite controlee vivante")
        return

    pdr = rpc("pathDistToEnemies", {"runnerId": rid, "unitId": uid})
    print("\n== regime %s -- runner %d, mover u%d ==" % (tag, rid, uid))
    print("   RPC pathDistToEnemies: cles=%s" % (sorted(pdr.keys()),))
    print("   ok=%s err=%r enemyCount=%s closestResolved=%s noTargetableEnemies=%r"
          % (pdr.get("ok"), pdr.get("error"), pdr.get("enemyCount"),
             pdr.get("closestResolved"), pdr.get("noTargetableEnemies")))

    # --- Le CANAL du gate 3. Ce n'est pas le resultat qu'on mesure ici, c'est la voie : le champ
    #     STRUCTURE doit etre SERVI par le bundle injecte. Le litteral d'erreur du meme `return`
    #     n'est plus une donnee -- `engine.ai.context._mindist_case` LEVE s'il le voit seul.
    if nominal:
        if pdr.get("noTargetableEnemies") is None and pdr.get("ok"):
            rep.add("[%s] canal gate 3 (noTargetableEnemies)" % tag, OK,
                    "champ ABSENT et ok=True, coherent avec un ClosestEnemy resolu")
        else:
            rep.add("[%s] canal gate 3 (noTargetableEnemies)" % tag, DIVERGE,
                    "champ=%r ok=%r" % (pdr.get("noTargetableEnemies"), pdr.get("ok")))
    elif pdr.get("noTargetableEnemies") is True:
        rep.add("[%s] canal gate 3 (noTargetableEnemies)" % tag, OK,
                "champ STRUCTURE servi par le bundle (=True), litteral non consomme")
    elif pdr.get("error") == "aucun ennemi vivant":
        rep.add("[%s] canal gate 3 (noTargetableEnemies)" % tag, DIVERGE,
                "litteral SANS le champ -> bundle Frida anterieur, rebuild+reinject requis")
    else:
        rep.add("[%s] canal gate 3 (noTargetableEnemies)" % tag, UNEXERCISED,
                "le montage n'a pas forme ClosestEnemy==null (err=%r)" % (pdr.get("error"),))

    # --- Face LIVE. Le predictor (donc la `Scene`) est OBLIGATOIRE : sans lui `GetStat(unit, 9)`
    #     n'est pas lisible et le gate 4 reste SUSPENDU -- on mesurerait un montage degrade.
    predictor = _scene.build_predictor(rpc, rid)
    ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, uid, wt, predictor)
    print("   ctx.epos=%s" % (sorted(ctx.epos),))
    print("   ctx.mindist_case=%s" % (ctx.mindist_case,))

    gate_bites = not nominal
    face_live = "[%s] face LIVE -- %s" % (tag, "gate 3" if gate_bites else "non-regression")
    if ctx.mindist_case is None:
        rep.add(face_live, UNEXERCISED, "aucun UtilityMovementCase construit")
    elif gate_bites and ctx.mindist_case.closest_enemy is not None:
        rep.add(face_live, DIVERGE,
                "le port croit avoir un ClosestEnemy (%r)" % (ctx.mindist_case.closest_enemy,))
    elif not nominal and not ctx.epos:
        rep.add(face_live, UNEXERCISED,
                "aucun ennemi positionne : le repli hex n'aurait rien a mesurer")
    elif nominal and ctx.mindist_case.closest_enemy is None:
        rep.add(face_live, UNEXERCISED,
                "regime nominal mais ClosestEnemy null : le gate 3 mord, montage non forme")
    else:
        _check_face(rep, face_live, _rows(ctx, wt, ctx.mindist_case), gate_bites)

    # --- La STAT du gate 4. `GetStat(unit, 9, Current, null)` est ce que lit
    #     `UnitCanBeDamagedUtility$$UnitCanBeDamaged` ; le RPC `combatSnapshot` invoque LA MEME
    #     fonction native (`UnitExtensions$$GetStat` 4-args, part=Current). On confronte donc la
    #     valeur du case a la lecture native, et on refuse le `None` (gate suspendu) comme un
    #     NON EXERCE : un gate suspendu n'a rien verifie.
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    nat_crit = next((((u.get("stats") or {}).get("critChance"))
                     for u in (snap.get("units") or []) if u.get("entityId") == uid), None)
    port_crit = getattr(ctx.mindist_case, "unit_crit_chance", None) if ctx.mindist_case else None
    _crit = "[%s] gate 4 -- GetStat(unit,9) face LIVE" % tag
    if port_crit is None:
        rep.add(_crit, UNEXERCISED,
                "unit_crit_chance=None (Scene absente) -> gate 4 SUSPENDU, rien verifie")
    elif nat_crit is None:
        rep.add(_crit, UNEXERCISED,
                "combatSnapshot ne rend pas critChance pour u%d -- pas d'oracle" % uid)
    elif int(port_crit) != int(nat_crit):
        rep.add(_crit, DIVERGE, "port=%r natif=%r" % (port_crit, nat_crit))
    else:
        rep.add(_crit, OK, "port=%r == natif combatSnapshot=%r" % (port_crit, nat_crit))
    if port_crit is not None:
        rep.live_crit = port_crit

    # --- L'IDENTITE du ClosestEnemy (#236 residu 1). `closestEnemyId` ferme l'ambiguite du gate 4
    #     quand les candidats sont PANACHES sur `Impervious`. Decidable dans le SEUL regime nominal
    #     (en regime gate 3 le RPC sort en `ok=false`). Champ ajoute au hook : tant que le bundle
    #     injecte est anterieur, l'etape est PENDING -- jamais un OK muet.
    if nominal:
        ce_rpc = pdr.get("closestEnemyId")
        ce_case = ctx.mindist_case.closest_enemy if ctx.mindist_case else None
        if ce_rpc is None:
            rep.add("[%s] identite ClosestEnemy (closestEnemyId)" % tag, PENDING,
                    "champ absent du bundle injecte -> exige la prochaine fenetre de reinject ; "
                    "le port retombe sur son verdict d'unanimite (case.closest_enemy=%r)" % ce_case)
        elif ce_case != ce_rpc:
            rep.add("[%s] identite ClosestEnemy (closestEnemyId)" % tag, DIVERGE,
                    "RPC=%r case.closest_enemy=%r" % (ce_rpc, ce_case))
        else:
            rep.add("[%s] identite ClosestEnemy (closestEnemyId)" % tag, OK,
                    "RPC=%r consomme par le case" % (ce_rpc,))

    # --- Face OFFLINE.
    obs = rpc("observeBattle", {"runnerId": rid}, 60)
    bg = rpc("boardGraph", {"runnerId": rid})
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    bd = _Board(bg["tiles"], adjacency="native_sym")
    state = load_state(dv, obs, snap, board=bd, tiles=tm)   # `board=` OBLIGATOIRE (sinon repli hex)
    octx = _sb.build_from_state(state, uid)
    print("   octx.mindist_case=%s" % (octx.mindist_case,))
    face_off = "[%s] face OFFLINE -- %s" % (tag, "gate 3" if gate_bites else "non-regression")
    if octx.mindist_case is None:
        rep.add(face_off, UNEXERCISED, "aucun UtilityMovementCase construit")
    else:
        _check_face(rep, face_off, _rows(octx, wt, octx.mindist_case), gate_bites)
    off_crit = getattr(octx.mindist_case, "unit_crit_chance", None) if octx.mindist_case else None
    _ocrit = "[%s] gate 4 -- GetStat(unit,9) face OFFLINE" % tag
    if off_crit is None:
        rep.add(_ocrit, UNEXERCISED, "unit_crit_chance=None -> gate 4 SUSPENDU cote offline")
    elif nat_crit is None:
        rep.add(_ocrit, UNEXERCISED, "pas d'oracle combatSnapshot pour u%d" % uid)
    elif int(off_crit) != int(nat_crit):
        rep.add(_ocrit, DIVERGE, "offline=%r natif=%r" % (off_crit, nat_crit))
    else:
        rep.add(_ocrit, OK, "offline=%r == natif combatSnapshot=%r" % (off_crit, nat_crit))

    # --- GATE 2 (IsNonAttacking) : hors portee live (porteurs npc non normalisables), exerce sur
    #     le substrat que `HasTrait` lit reellement -- exactement ce qu'ecrit le leaf DSL `AddTrait`.
    #     REGIME NOMINAL SEULEMENT : en regime gate 3 le terme est deja nul (le gate 3 mord avant),
    #     donc poser le trait ne prouverait rien.
    if not nominal:
        return
    sc = state.get_entity(uid).get_component(StatsComponent)
    _g2 = "[%s] gate 2 -- AddTrait(NonAttacking) OFFLINE" % tag
    if sc is None or sc.ctx is None:
        rep.add(_g2, UNEXERCISED, "pas de UnitContext : substrat HasTrait absent")
        return
    before = _rows(octx, wt, octx.mindist_case)
    if not any(u != 0.0 for _t, _u_no, u in before):
        rep.add(_g2, UNEXERCISED, "terme deja nul AVANT le trait -- un gate anterieur mord")
        return
    sc.ctx.traits = list(sc.ctx.traits or []) + [UnitTrait.NonAttacking.name]
    octx2 = _sb.build_from_state(state, uid)
    if not is_non_attacking(octx2.mindist_case.unit_traits):
        rep.add(_g2, UNEXERCISED, "le trait pose n'est pas vu par le substrat du case")
    else:
        _check_face(rep, _g2, _rows(octx2, wt, octx2.mindist_case), True)
    sc.ctx.traits = [t for t in sc.ctx.traits if t != UnitTrait.NonAttacking.name]


def check_gate4_case(rep: Report, wt, live_crit) -> None:
    """GATE 4 (`UnitCanBeDamaged`) sur un case CONSTRUIT : l'etat live ne peut pas produire le
    couple (aucun porteur `Impervious` n'est spawnable, et ceux du gameconfig sont `Object` +
    Attack 0 donc `IsIrrelevantObject` -> `FindClosestEnemy` ne les retient JAMAIS)."""
    print("\n== GATE 4 (case construit) : ClosestEnemy Impervious x CriticalChance du mover ==")
    good = []
    for crit, exp_zero in ((0, True), (15, False), (None, False)):
        c = UtilityMovementCase(unit=1, unit_traits=(), unit_crit_chance=crit,
                                closest_enemy=999,
                                closest_enemy_traits=(UnitTrait.Impervious.name,))
        u = MIN_DIST_UTILITY.evaluate_movement((0, 0), [(3, 3)], wt, {(0, 0): 4}, case=c)
        ok = (u == 0.0) if exp_zero else (u != 0.0)
        good.append(ok)
        print("   crit=%-5r -> U=%-14s attendu %s  %s"
              % (crit, u, "0 (gate)" if exp_zero else "non nul", "OK" if ok else "DIVERGE"))
    rep.add("gate 4 -- UnitCanBeDamaged (case construit)", OK if all(good) else DIVERGE,
            "3 branches : crit=0 (mord), crit=15 (ne mord pas), crit=None (SUSPENDU)")
    if live_crit == 0:
        rep.add("gate 4 -- pertinence de la stat live", OK,
                "la CriticalChance LIVE du mover vaut 0 : `None` (suspendu) et `0` (mord) "
                "DIVERGENT sur ce mover -- la suspension n'etait pas cosmetique")
    elif live_crit is None:
        rep.add("gate 4 -- pertinence de la stat live", UNEXERCISED,
                "aucune CriticalChance live lue -- la portee du gate 4 n'est pas etablie")
    else:
        rep.add("gate 4 -- pertinence de la stat live", OK,
                "CriticalChance LIVE = %r (non nulle) : le gate 4 ne mordrait pas sur ce mover"
                % (live_crit,))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None,
                    help="runner DEJA monte -> un seul regime (cf. --nominal)")
    ap.add_argument("--unit", type=int, default=None)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--nominal", action="store_true",
                    help="avec --runner : traite ce runner comme le regime NOMINAL")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer les runners montes ici")
    a = ap.parse_args()

    sid = _resolve_session()
    rpc = _mk_rpc(sid)
    wt = weights.load()
    rep = Report()
    mine: list[int] = []
    try:
        if a.runner is not None:
            # Couverture PARTIELLE assumee : un seul regime, l'autre n'est pas monte. Les etapes de
            # l'autre regime ne sont pas listees -- elles sont hors perimetre du run, pas « vertes ».
            print("[couverture] regime %s SEUL (--runner %d) -- l'autre regime n'est pas monte"
                  % ("nominal" if a.nominal else "gate3", a.runner))
            run_regime(rep, rpc, wt, a.runner, a.unit, a.nominal)
        else:
            base = a.state_file or str(PYDIR / "probe236_state.json")
            for nominal, suffix, roster in ((False, "_gate", DEEP_STRIKE_ROSTER),
                                            (True, "_nominal", MOVER_ROSTER)):
                sf = base[:-5] + suffix + ".json" if base.endswith(".json") else base + suffix
                rid = _build(sf, a.seed, a.board, roster)
                mine.append(rid)
                run_regime(rep, rpc, wt, rid, a.unit, nominal)
        check_gate4_case(rep, wt, rep.live_crit)
        return rep.verdict()
    finally:
        if not a.keep:
            for rid in mine:      # dispose MES runners, jamais ceux des autres agents
                try:
                    rpc("disposeRunner", {"runnerId": rid}, 30)
                except Exception as e:                       # noqa: BLE001
                    print("[warn] disposeRunner(%d) : %s" % (rid, e))


if __name__ == "__main__":
    raise SystemExit(main())


