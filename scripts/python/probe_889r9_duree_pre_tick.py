"""#889-r9 -- LA DUREE POSEE PAR `TurnsFromRounds` : PRE-TICK contre POST-TICK.

CE QUE CE PROBE DISCRIMINE. La fiche #889-r9 annonce que la duree posee « diverge REELLEMENT »
(`remaining` AU CAST = `1` natif contre `2` port) et oppose deux causes :

  (i)  le port derive son facteur d'un PROXY (`observeBattle.counts.player - 1`) au lieu du compte
       natif (`count(joueurs du BC.Player.TurnOrder dont PlayerType != 2)`) ;
  (ii) le canal de publication rendrait un `remaining` en ROUNDS, ou POST-tick.

Ce probe les mesure TOUTES DEUX, et il ajoute la TROISIEME que la fiche n'enonce pas -- le
MONTAGE. Le montage de `probe_889_lions_wrath.py` met le Lion **SEUL** dans son camp : son cast
appelle donc `FinishUnitTurn`, plus aucune unite n'est activable, et le natif enchaine
`IdunBattle.Operations.EndTurnOperation$$Execute` -> `IdunBattle.Operations.EndTurnOperation$$RefreshEffects`
-> `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` sur TOUT effet a duree AVANT que
`decisionView` ne soit relu. Le port, lui, ne joue que `_apply_active_ability` : aucun tick. Les
deux `remaining` compares ne sont alors pas pris au meme instant.

LES DEUX BRAS :

  * `--bras pre`  : le Lion a un CAMARADE encore activable derriere lui. Le cast termine le tour
    de l'UNITE, pas celui du JOUEUR -> aucun `EndTurnOperation` -> le `remaining` publie est
    PRE-tick. C'est le regime ou la valeur POSEE est observable telle quelle.
  * `--bras post` : le montage EXACT de la fiche (Lion seul). Le tour bascule au cast. Le port y
    joue ENSUITE `EndTurnOperation.execute(state, advance=False)` -- le meme tick que le natif
    vient de jouer -- et on regarde s'il converge.

CRITERE, enonce AVANT la mesure :
  * si `bras pre` rend `2` des DEUX cotes  -> (ii) est REFUTE (le canal publie bien des TOURS,
    pre-tick) et la valeur posee ACCORDE ;
  * si `facteur_port == facteur_bc`        -> (i) est REFUTE sur ce runner ;
  * si `bras post` converge apres le tick  -> la cause est le MONTAGE, pas la duree.
Un bras `pre` qui rendrait `1` des deux cotes serait DEGENERE (les deux modeles d'accord sur une
valeur fausse) : le probe imprime donc AUSSI le facteur, qui doit valoir 2 pour que le regime
discrimine.

ASCII only. SORTIES -> logs/, jamais data/ (#349).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
LOGS = ROOT / "logs" / "runners"

THE_LIONS_WRATH = 1217          # ActiveAbilityType.TheLionsWrath
BOARD = "CE6_boss"              # LA carte du boss (gameconfig battles[].BoardId)
BOSS = "darkaBossLion:4"        # palier HAUT (le seul a porter un CritChance non nul)
CAMARADE = "adeptRetributor"    # l'unite qui garde le tour du JOUEUR ouvert apres le cast

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/base.py",
                "scripts/python/engine/runner/snapshot.py",
                "scripts/python/engine/runner/operations/turnflow.py",
                "scripts/python/engine/runner/operations/effects.py",
                "data/seed-bc.json"),
    "build": True,
    "toujours": False,
    "raison": "Il tranche PRE-tick contre POST-tick sur la duree posee par "
              "`IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns`, et confronte le "
              "FACTEUR du port au compte lu dans la BC.",
}


def _session() -> int:
    st = requests.get(f"{HOST}/api/admin/status", timeout=20).json()
    return int(st["session"]["id"])


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 5).json()
    return r.get("result", r)


def facteur_bc(bc_path: Path | None = None) -> dict:
    """Le facteur NATIF, lu comme le decompile le lit : `count(joueurs du `BC.Player.TurnOrder`
    dont `PlayerComponent.<+0x20>` (PlayerType) != 2)`. Aucune deduction -- on itere la MEME
    liste, dans le MEME ordre, et on ecarte le MEME discriminant."""
    p = bc_path or (ROOT / "data" / "seed-bc.json")
    bc = json.loads(p.read_text(encoding="utf-8"))
    joueurs = ((bc.get("Player") or {}).get("Players") or {})
    ordre = ((bc.get("Player") or {}).get("TurnOrder") or [])
    detail = []
    n = 0
    for pid in ordre:
        cfg = joueurs.get(str(pid)) or joueurs.get(pid) or {}
        pt = cfg.get("PlayerType")
        compte = (pt is not None and int(pt) != 2)
        detail.append({"id": pid, "name": cfg.get("Name"), "PlayerType": pt, "compte": compte})
        if compte:
            n += 1
    return {"facteur": n, "turn_order": list(ordre), "detail": detail}


def build(state_path: Path, args: list) -> int:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    # Le boss arrive sous un id d'entite REMAPPE -> le garde de roster rend un FAUX NEGATIF.
    env["TACTICUS_ALLOW_ROSTER_DEFICIT"] = "1"
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    if not state_path.exists():
        print((proc.stderr or proc.stdout or "")[-2500:])
        raise SystemExit("build KO")
    return int(json.loads(state_path.read_text())["runnerId"])


def bind_transport(sid: int):
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(lambda method, body=None, timeout=60: rpc(sid, method, body or {}, timeout))


def load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    tiles = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    abst = rpc(sid, "unitAbilityStates", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=tiles, ability_states=abst), dec, ob


def footprint_live(dec) -> dict:
    out = {}
    for u in (dec.get("units") or []):
        effs = {int(e["effectType"]): e.get("remaining") for e in (u.get("effects") or [])
                if e.get("effectType") is not None}
        if effs:
            out[int(u["id"])] = effs
    return out


def footprint_off(state) -> dict:
    out = {}
    for key, effs in (state.effects.by_unit if state.effects is not None else {}).items():
        cur = {int(e.effect_type): (0 if e.remaining_turns is None else int(e.remaining_turns))
               for e in effs if not e.consumed}
        if cur:
            out[int(key)] = cur
    return out


def delta(before: dict, after: dict) -> dict:
    out = {}
    for k, effs in after.items():
        new = {et: rem for et, rem in effs.items() if et not in (before.get(k) or {})}
        if new:
            out[int(k)] = new
    return out


def seed_offline_rng(state, dump):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = int(dump["mti"])
    state.rng = rng
    return rng


# ---------------------------------------------------------------- LA FIXTURE, nommee et reutilisable

def monter_scenario(sid: int, *, avec_camarade: bool, seed: str = "777",
                    board: str = BOARD, state_name: str | None = None):
    """Monte le duel du Lion sur SA carte, avec ou sans CAMARADE activable derriere lui.

    `avec_camarade=True` est le SEUL levier qui change entre les deux bras : il garde le tour du
    JOUEUR ouvert apres le cast, donc empeche `EndTurnOperation` de tourner avant la relecture.
    Le Lion est `moveNone` -- c'est la CIBLE qu'on colle a lui, jamais l'inverse."""
    nom = state_name or ("probe_889r9_%s" % ("pre" if avec_camarade else "post"))
    state_path = LOGS / ("%s.json" % nom)
    p_units = BOSS + ((",%s" % CAMARADE) if avec_camarade else "")
    args = ["--seed", seed, "--board", board,
            "--explicit-stats", BOSS,
            "--p-units", p_units,
            "--a-units", "custoVexilusPraetor,orksBigMek",
            "--place", "%s:3,3" % BOSS,
            "--a-place", "custoVexilusPraetor:3,4", "--a-place", "orksBigMek:2,2"]
    if avec_camarade:
        # LOIN du Lion et de la melee : ce camarade ne doit rien changer d'autre que le fait
        # qu'une unite du camp reste activable.
        args += ["--place", "%s:6,8" % CAMARADE]
    rid = build(state_path, args)

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais ceux des autres

    return rid, dispose


def _cast(sid: int, rid: int, avec_camarade: bool) -> dict:
    from engine.runner.operations.summon_ai import _apply_active_ability

    bind_transport(sid)
    dec0 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    caster = next((u for u in (dec0.get("units") or [])
                   if "DarkaLion" in str(u.get("visualId") or "")), None)
    if caster is None:
        raise AssertionError("SCENARIO NON MONTE : le Lion est absent du decisionView")
    caster_id = int(caster["id"])
    allies = [int(u["id"]) for u in (dec0.get("units") or [])
              if int(u.get("owner", -1)) == int(caster.get("owner", -2)) and int(u["id"]) != caster_id]
    if avec_camarade and not allies:
        raise AssertionError("SCENARIO NON MONTE : le camarade %s est absent" % CAMARADE)

    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": caster_id, "abilityType": THE_LIONS_WRATH}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == THE_LIONS_WRATH), {})
    from_here = [t.get("targetId") for t in (ab.get("fromHere") or [])]
    if not from_here:
        raise AssertionError("SCENARIO NON MONTE : aucune cible legale SUR PLACE pour 1217")
    target_id = int(from_here[0])

    # ---- OFFLINE -------------------------------------------------------------------------
    state, _, ob0 = load(sid, rid)
    seed_offline_rng(state, rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {})
    off_before = footprint_off(state)
    _apply_active_ability(state, caster_id, target_id, THE_LIONS_WRATH)
    off_cast = delta(off_before, footprint_off(state))

    # ---- LIVE ----------------------------------------------------------------------------
    live_before = footprint_live(dec0)
    rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": THE_LIONS_WRATH,
        "targetId": target_id}}, 90)
    dec1 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    live_cast = delta(live_before, footprint_live(dec1))

    out = {
        "caster": caster_id, "cible": target_id, "camarades": allies,
        "counts_player": (ob0.get("counts") or {}).get("player"),
        "facteur_port": getattr(state, "turn_order_player_count", None),
        "currentPlayer_avant": dec0.get("currentPlayer"),
        "currentPlayer_apres": dec1.get("currentPlayer"),
        "bascule": dec0.get("currentPlayer") != dec1.get("currentPlayer"),
        "live_cast": live_cast, "off_cast": off_cast,
    }

    # ---- BRAS POST : on joue cote port LE MEME TICK que le natif vient de jouer ------------
    if out["bascule"]:
        from engine.runner.operations.turnflow import EndTurnOperation
        EndTurnOperation.execute(state, advance=False)
        out["off_apres_tick"] = delta(off_before, footprint_off(state))
    return out


def _rendu(nom: str, m: dict) -> None:
    print("  [%s] counts.player=%s facteur_port=%s | currentPlayer %s -> %s (bascule=%s)"
          % (nom, m["counts_player"], m["facteur_port"], m["currentPlayer_avant"],
             m["currentPlayer_apres"], m["bascule"]))
    print("      camarades du caster : %s" % (m["camarades"] or "AUCUN"))
    print("      NATIF (publie) : %s" % json.dumps(m["live_cast"], sort_keys=True))
    print("      PORT  (au cast): %s" % json.dumps(m["off_cast"], sort_keys=True))
    if "off_apres_tick" in m:
        print("      PORT  (+ EndTurnOperation, le tick que le natif a joue) : %s"
              % json.dumps(m["off_apres_tick"], sort_keys=True))


def _valeurs(foot: dict) -> set:
    return {v for effs in foot.values() for v in effs.values()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bras", choices=["pre", "post", "les-deux"], default="les-deux")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default=BOARD)
    a = ap.parse_args()

    sid = _session()
    fbc = facteur_bc()
    print("FACTEUR NATIF lu dans la BC (`BattleQuery$$ConvertRoundsToTurns`) : %d" % fbc["facteur"])
    print("  TurnOrder=%s" % fbc["turn_order"])
    for d in fbc["detail"]:
        print("    joueur %s (%s) PlayerType=%s -> compte=%s"
              % (d["id"], d["name"], d["PlayerType"], d["compte"]))

    res = {}
    for bras in (("pre", "post") if a.bras == "les-deux" else (a.bras,)):
        rid, dispose = monter_scenario(sid, avec_camarade=(bras == "pre"),
                                       seed=a.seed, board=a.board)
        try:
            res[bras] = _cast(sid, rid, avec_camarade=(bras == "pre"))
        finally:
            dispose()
        _rendu(bras, res[bras])

    print("")
    print("VERDICT")
    if "pre" in res:
        m = res["pre"]
        if m["bascule"]:
            print("  [pre] REGIME NON OBTENU : le tour a bascule malgre le camarade -- ce bras ne")
            print("        discrimine PAS (le natif a tique avant la relecture).")
        else:
            vn, vp = _valeurs(m["live_cast"]), _valeurs(m["off_cast"])
            print("  [pre] PRE-TICK -- valeurs natives=%s port=%s" % (sorted(vn), sorted(vp)))
            print("        (ii) canal en ROUNDS/POST-tick : %s"
                  % ("REFUTE" if vn == vp and vn == {fbc["facteur"]} else "NON REFUTE"))
    if "post" in res:
        m = res["post"]
        ok = m.get("off_apres_tick") == m["live_cast"]
        print("  [post] montage de la fiche -- bascule=%s ; le port converge apres le MEME tick : %s"
              % (m["bascule"], "OUI" if ok else "NON"))
    f_port = (res.get("pre") or res.get("post") or {}).get("facteur_port")
    print("  (i) PROXY `counts.player - 1` : port=%s vs BC=%s -> %s"
          % (f_port, fbc["facteur"],
             "REFUTE (identiques)" if f_port == fbc["facteur"] else "DIVERGENT"))

    out = LOGS / "probe_889r9_duree_pre_tick.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"facteur_bc": fbc, "bras": res}, indent=2), encoding="utf-8")
    print("  -> %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
