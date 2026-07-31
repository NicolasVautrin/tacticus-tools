"""probe #361 (contre-epreuve) -- `get_WillBeKill` GOUVERNE-T-IL vraiment un compte d'events ?

POURQUOI CE PROBE EXISTE
------------------------
`probe_361_ramming_speed_explosion_batches.py` a etabli, sur 1059 `RammingSpeed` : tuile d'arrivee
CONFIRMEE par cast reel, voisinage PEUPLE (1 ami + 2 ennemis), gate au predicat VRAI
(`willBeKill = true`, capteur #372) -- et pourtant les batchs 3/4 restent absents.

Deux choses restaient confondues, et il faut les separer avant d'accuser quoi que ce soit :

  (i)  `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` ne rend pas ce que le
       capteur #372 calcule (la RE ou le decodeur serait faux) ;
  (ii) `get_WillBeKill` est juste, et c'est le chemin propre a 1059 qui perd le predicat.

VOLET A -- `StormOfFlensingBlades` (1010) : LE TEST PUR DU FLAG
---------------------------------------------------------------
`IdunBattle.AI.Playbook.Loki.StormOfFlensingBladesPlaybook$$MakeDamagePredictions`, lu VERBATIM :

    ev = ProbableDamageEvent(target, <IBattleQuery slot 0x22 (caster, target, casterPosition)>, ...)
    if (!get_WillBeKill(&ev.Prediction))  return new[]{ ev, ev };   // DEUX fois le MEME event
    else                                  return new ProbableDamageEvent[0];

`&ev.Prediction` = `&ev + 0x08` -- exactement le `PDE_PREDICTION_OFF` que decode le capteur.
Le compte d'events depend donc DIRECTEMENT et UNIQUEMENT du flag : **2 si FAUX, 0 si VRAI**.
Aucun selecteur, aucun contexte d'evaluation, aucun `Enumerable.Any`, aucune config d'ability.

  * 2 puis 0 => `get_WillBeKill` et le capteur #372 disent VRAI ; (i) TOMBE.
  * 2 puis 2 => le flag ne bascule jamais cote natif ; (i) est la cause, et elle deborde 1059.

Confrontabilite : les 3 porteurs de 1010 sont NPC (`necroNpc2FlayedOne` & co). C'est le cas
« npc-only n'implique PAS non confrontable » de `case-92` sec.5bis : ce playbook ne lit NI stats,
NI traits, NI config d'ability du caster -- il n'appelle que le slot de prediction. On le GREFFE
donc sur un heros du pool, par le foyer unique `probe_353.build_grafted_seed_bc`.

VOLET B -- `FragstormGrenadeLauncher` (1048) : pourquoi il ne pouvait PAS trancher
----------------------------------------------------------------------------------
`FragstormGrenadeLauncherPlaybook$$MakeDamagePredictions` porte le meme motif (gate DIRECTE, puis
un batch supplementaire), mais son batch supplementaire est INOBSERVABLE, et c'est LU :

    if (!get_WillBeKill(&pred)) return list;
    sel = FragstormGrenadeLauncherAbility$$GetOtherTargets(ability);
    memset(&ctx, 0, 0x128);                      // <-- et AUCUN champ n'est renseigne ensuite
    if (sel != null) { ... TargetsSelector$$SelectUniqueUnits(sel, &ctx, 3) ... }

`GetOtherTargets` = `Damageable( SurroundingEnemies(Owner@0x30, range, 1, 3) - Target@0x60 )` :
evalue avec un contexte a ZERO, son `Owner` est nul, donc l'ensemble est VIDE **que la gate ouvre
ou non**. Le probe le MESURE quand meme (c'est une constatation native de valeur), mais il ne
compte PAS ce bras comme discriminant -- confondre les deux est exactement l'erreur que #353-r1
et #372 ont payee.

ASCII only (cp1252). Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_361_will_be_kill_gate_direct.py
    python probe_361_will_be_kill_gate_direct.py --skip-fragstorm --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import hexgeo

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402
from probe_353_ramming_speed_prediction import build_grafted_seed_bc     # noqa: E402
from probe_353r1_ramming_speed_charge_tile import _pos, _view, drive_to  # noqa: E402

# `data/symbols/rnca9r7q6c/frida/enums.tsv`, `IdunBattle.Entities.Enum.ActiveAbilityType`
STORM = 1010
STORM_NAME = "StormOfFlensingBlades"
FRAG = 1048
GRAFT = "orksKillaKan"          # heros MELEE du pool rank 17 (meme greffon que probe_353)
FRAG_CASTER = "templAggressor"  # Burchard -- porteur ACTIF de 1048, present au pool
ALLY = "astraBullgryn"
VICTIM = "necroWarden"
ENEMY2 = "ultraTitus"
BOARD = "MC1_67"
FRAG_RANGE = 2                  # `abilities.FragstormGrenadeLauncher.constants.range`
HP_KILL = 1
HP_ALIVE = 999999


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed: int, hp_target: int, caster: str, seed_bc=None) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", BOARD, "--rank", "17",
           "--p-units", "%s,%s" % (caster, ALLY),
           "--a-units", "%s,%s" % (VICTIM, ENEMY2),
           "--hp-target", str(int(hp_target)),
           "--crit", "0,0", "--block-target", "0,0", "--block-player", "0,0", "--no-ai"]
    if seed_bc is not None:
        cmd += ["--seed-bc", str(seed_bc)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1200:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _ids(dv, caster: str) -> dict:
    out = {}
    for v in (caster, ALLY, VICTIM, ENEMY2):
        u = next((x for x in (dv.get("units") or []) if x.get("visualId") == v and x.get("alive")),
                 None)
        if u is None:
            raise RuntimeError("unite absente du build : %s" % v)
        out[v] = int(u["id"])
    return out


def _rows(nat) -> list:
    return [{"targetId": e.get("targetId"), "hpBefore": e.get("hpBefore"),
             "healthDmgMin": e.get("healthDmgMin"), "healthDmgMax": e.get("healthDmgMax"),
             "appliedHits": e.get("appliedHits"), "willBeKill": e.get("willBeKill"),
             "willKillDmg": e.get("willKillDmg"),
             "blockScenarioCount": e.get("blockScenarioCount"),
             "cannotBeGuaranteedKilled": e.get("cannotBeGuaranteedKilled")}
            for e in (nat.get("events") or [])]


def _place_adjacent(sid, rid, ids, caster: str) -> dict:
    """Colle les DEUX ennemis au caster (voisins immediats) et exile l'allie. Foyer unique des deux
    volets : le volet A en a besoin pour que l'attaque predite ne soit pas nulle, le volet B pour
    que `SurroundingEnemies(range=2)` aurait de quoi rendre. Drive pas-a-pas puis RELECTURE."""
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dv = _view(sid, rid)
    here = _pos(dv, ids[caster])
    ring = [board.coord(n) for n in board.neighbours(board.id_at(*here)) if board.walkable(n)]
    if len(ring) < 2:
        raise RuntimeError("caster sans deux voisins marchables en %s" % (here,))
    far = max((board.coord(t) for t in board.by_id if board.walkable(t)),
              key=lambda p: hexgeo.distance(p, here))
    wanted = {ids[VICTIM]: ring[0], ids[ENEMY2]: ring[1], ids[ALLY]: far}
    if not drive_to(sid, rid, wanted):
        dv = _view(sid, rid)
        raise RuntimeError("drive KO : voulu %s obtenu %s"
                           % ({k: list(v) for k, v in wanted.items()},
                              {u: _pos(dv, u) for u in wanted}))
    dv = _view(sid, rid)
    cpos = _pos(dv, ids[caster])
    others = [u.get("visualId") for u in (dv.get("units") or [])
              if u.get("alive")
              and int(u["id"]) not in (ids[caster], ids[ALLY], ids[VICTIM])
              and hexgeo.distance(((u.get("pos") or {}).get("col"),
                                   (u.get("pos") or {}).get("row")), cpos) <= FRAG_RANGE]
    return {"caster_pos": list(cpos), "victim_pos": list(_pos(dv, ids[VICTIM])),
            "enemy2_pos": list(_pos(dv, ids[ENEMY2])), "ally_pos": list(far),
            "autres_ennemis_a_portee": others}


def _storm_arm(sid, seed: int, hp_target: int, sf: Path, bcf: Path) -> dict:
    """UN bras du volet A.

    ⚠ Le DRIVE est OBLIGATOIRE : le slot `0x22` predit l'ATTAQUE du caster sur la cible, donc il
    lit la portee. Sans drive, les deux unites restent a leur spawn et la prediction rend un degat
    NUL -- `willBeKill` est alors FAUX a juste titre meme a 1 PV, et le bras ne prouve RIEN
    (MESURE : `healthDmgMin/Max = 0`, `willKillDmg = 0`, 2 events dans les deux bras)."""
    rid = None
    out: dict = {"hp_target": hp_target}
    try:
        rid = _build(sf, seed, hp_target, GRAFT, seed_bc=bcf)
        out["runner"] = rid
        ids = _ids(_view(sid, rid), GRAFT)
        out["geometry"] = _place_adjacent(sid, rid, ids, GRAFT)
        nat = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": ids[GRAFT],
                                            "targetId": ids[VICTIM], "abilityType": STORM}, 120)
        out["playbook"] = nat.get("playbookClass")
        out["native_error"] = nat.get("error")
        out["events"] = _rows(nat)
        out["n_events"] = len(out["events"])
        # Le flag N'EST PAS LISIBLE quand la gate ouvre (le natif rend alors un tableau VIDE) :
        # c'est precisement pour ca que le COMPTE est la mesure, pas le champ.
        out["target_will_be_kill"] = (out["events"][0]["willBeKill"] if out["events"] else None)
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        sf.unlink(missing_ok=True)
    return out


def run_storm(sid, seed: int, verbose: bool) -> dict:
    logs = ROOT / "logs"
    bcf = logs / ("p361d-seed-bc-%s.json" % uuid.uuid4().hex[:8])
    out: dict = {"ability": STORM, "seed": seed}
    try:
        out["graft"] = build_grafted_seed_bc(bcf, graft=GRAFT, ability_id=STORM,
                                             ability_name=STORM_NAME)
        out["alive"] = _storm_arm(sid, seed, HP_ALIVE,
                                  logs / ("p361d-s-alive-%s.json" % uuid.uuid4().hex[:8]), bcf)
        out["kill"] = _storm_arm(sid, seed, HP_KILL,
                                 logs / ("p361d-s-kill-%s.json" % uuid.uuid4().hex[:8]), bcf)
    finally:
        bcf.unlink(missing_ok=True)
    a, k = out["alive"], out["kill"]
    # --- VERDICT DERIVE DES COMPTES (le decompile dit 2 quand FAUX, 0 quand VRAI)
    if a.get("native_error") or k.get("native_error"):
        out["ok"] = False
        out["verdict"] = ("MONTAGE KO : erreur native %s / %s"
                          % (a.get("native_error"), k.get("native_error")))
    elif a.get("target_will_be_kill") is not False:
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : au bras `alive` le capteur donne willBeKill=%s, "
                          "il faut FAUX (sinon le bras de reference ne vaut rien)."
                          % a.get("target_will_be_kill"))
    elif int((a["events"][0] or {}).get("willKillDmg") or 0) < int(k["hp_target"]):
        # Piege MESURE au 1er jet (sans drive) : degat predit NUL => `hp <= 0` est FAUX meme a
        # 1 PV, la gate ne PEUT pas basculer, et 2 events dans les deux bras ne prouvent RIEN.
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : la borne du kill vaut %s pour une cible a %s PV "
                          "-- le predicat ne peut PAS devenir vrai. Rapprocher le caster / baisser "
                          "les PV." % ((a["events"][0] or {}).get("willKillDmg"), k["hp_target"]))
    elif a["n_events"] == 2 and k["n_events"] == 0:
        out["ok"] = True
        out["verdict"] = ("FLAG CONFIRME : 2 events quand willBeKill est FAUX, 0 quand il devient "
                          "VRAI -- exactement ce que le decompile prescrit. `get_WillBeKill` et le "
                          "capteur #372 disent VRAI ; la cause de 1059 n'est donc PAS la lecture "
                          "du flag.")
    elif a["n_events"] == k["n_events"]:
        out["ok"] = False
        out["verdict"] = ("FLAG INERTE : %d events dans les DEUX bras alors que le decompile "
                          "prescrit 2 puis 0. Le flag ne bascule jamais cote natif => la RE de "
                          "`get_WillBeKill` ou le decodeur #372 est en cause, et le probleme "
                          "deborde 1059." % a["n_events"])
    else:
        out["ok"] = False
        out["verdict"] = ("COMPTES INATTENDUS : alive=%d kill=%d (le decompile prescrit 2 puis 0). "
                          "A decomposer avant tout verdict." % (a["n_events"], k["n_events"]))
    if verbose:
        print("[361d/storm] greffe %s <- %d (%s) | %s"
              % (GRAFT, STORM, STORM_NAME, json.dumps(out.get("graft"))))
        for tag in ("alive", "kill"):
            arm = out[tag]
            print("[361d/storm] bras %-5s hp_target=%-7s runner=%s playbook=%s events=%d erreur=%s"
                  % (tag, arm.get("hp_target"), arm.get("runner"), arm.get("playbook"),
                     arm.get("n_events", -1), arm.get("native_error")))
            for r in arm.get("events") or []:
                print("        %s" % json.dumps(r, sort_keys=True))
        print("[361d/storm] %s" % out["verdict"])
    return out


def _frag_arm(sid, seed: int, hp_target: int, sf: Path) -> dict:
    rid = None
    out: dict = {"hp_target": hp_target}
    try:
        rid = _build(sf, seed, hp_target, FRAG_CASTER)
        out["runner"] = rid
        ids = _ids(_view(sid, rid), FRAG_CASTER)
        out["geometry"] = _place_adjacent(sid, rid, ids, FRAG_CASTER)
        nat = _r(sid, "aiPlaybookPredict",
                 {"runnerId": rid, "unitId": ids[FRAG_CASTER], "targetId": ids[VICTIM],
                  "abilityType": FRAG}, 120)
        out["playbook"] = nat.get("playbookClass")
        out["native_error"] = nat.get("error")
        out["events"] = _rows(nat)
        out["n_events"] = len(out["events"])
        out["target_will_be_kill"] = (out["events"][0]["willBeKill"] if out["events"] else None)
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        sf.unlink(missing_ok=True)
    return out


def run_fragstorm(sid, seed: int, verbose: bool) -> dict:
    logs = ROOT / "logs"
    out: dict = {"ability": FRAG, "seed": seed}
    out["alive"] = _frag_arm(sid, seed, HP_ALIVE,
                             logs / ("p361d-f-alive-%s.json" % uuid.uuid4().hex[:8]))
    out["kill"] = _frag_arm(sid, seed, HP_KILL,
                            logs / ("p361d-f-kill-%s.json" % uuid.uuid4().hex[:8]))
    a, k = out["alive"], out["kill"]
    out["n_alive"], out["n_kill"] = a["n_events"], k["n_events"]
    # NON DISCRIMINANT PAR CONSTRUCTION (contexte a zero, cf. en-tete) : on ENREGISTRE, on ne
    # conclut pas. Le seul enonce que cette mesure autorise porte sur le CONTEXTE, pas sur la gate.
    out["ok"] = None
    out["verdict"] = ("MESURE, NON DISCRIMINANTE : %d event(s) au bras `alive` (willBeKill=%s) et "
                      "%d au bras `kill` (willBeKill=%s), avec %s autre(s) ennemi(s) a distance "
                      "<= %d. Le decompile explique l'absence du batch supplementaire SANS invoquer "
                      "la gate : `SelectUniqueUnits` y est evalue sur un contexte `memset(0, 0x128)` "
                      "jamais renseigne, donc `SurroundingEnemies(Owner@0x30, ...)` est vide quoi "
                      "qu'il arrive."
                      % (a["n_events"], a.get("target_will_be_kill"), k["n_events"],
                         k.get("target_will_be_kill"),
                         (k.get("geometry") or {}).get("autres_ennemis_a_portee"),
                         FRAG_RANGE))
    if verbose:
        for tag in ("alive", "kill"):
            arm = out[tag]
            print("[361d/frag ] bras %-5s hp_target=%-7s runner=%s playbook=%s events=%d"
                  % (tag, arm.get("hp_target"), arm.get("runner"), arm.get("playbook"),
                     arm.get("n_events", -1)))
            print("        geo=%s" % json.dumps(arm.get("geometry")))
            for r in arm.get("events") or []:
                print("        %s" % json.dumps(r, sort_keys=True))
        print("[361d/frag ] %s" % out["verdict"])
    return out


def run(seed: int = 36110, with_fragstorm: bool = True, verbose: bool = True) -> dict:
    sid = _resolve_session()
    out: dict = {"board": BOARD, "seed": seed}
    out["storm"] = run_storm(sid, seed, verbose)
    if with_fragstorm:
        out["fragstorm"] = run_fragstorm(sid, seed + 1, verbose)
    out["ok"] = bool(out["storm"].get("ok"))
    out["verdict"] = out["storm"]["verdict"]
    if verbose:
        print("[361d] -> %s" % ("OK" if out["ok"] else "ECHEC"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=36110)
    ap.add_argument("--skip-fragstorm", action="store_true",
                    help="ne joue que le volet A (le seul discriminant)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, with_fragstorm=not a.skip_fragstorm, verbose=not a.json)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
