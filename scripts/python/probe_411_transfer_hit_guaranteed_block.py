#!/usr/bin/env python
"""probe #411 -- CONFRONTATION LIVE de `DealDamageInfo[+0x1D]` (block GARANTI, 0 tirage).

QUESTION BINAIRE, posee avant la methode : **le coup TRANSFERE laisse-t-il sa cible d'origine a
degat ZERO, et le transfert deplace-t-il ce degat sur le porteur du passif ?** C'est le seul
observable du champ `+0x1D` : son unique ecrivain est le passage a `null` du `PendingHit` du
defenseur, et son unique effet est de router
`IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation` vers la surcharge
`ApplyBlockDamage(blockChances, damage)` (slot 4 d'`IDamageCalculations`) au lieu du couple
`ApplyRandomEvasion` + `ApplyRandomBlockDamage` (slots 3 et 2) -- donc un block SANS AUCUN tirage.

RE (case-407 §7 -> case-411) :
  IdunBattle.Operations.AttackDamageOperation$$ExecuteHit
      defenderUnitComponent.PendingHit = Nullable(new AttackHit(damage, profile, discard:false))
      -> dispatch des triggers de coup (EventTriggerType 7)
      -> si !PendingHit.HasValue : damage = 0 ; hitGroup[+0x29] = 1 (collant) ;
         DealDamageInfo[+0x1D] = 1
  IdunBattle.Operations.TransferHitOperation$$Execute  -- L'ECRIVAIN
      originalTargetComponent.PendingHit = default   (les 0x10 octets remis a zero)
      puis rejoue une AttackDamage sur chaque transferTarget avec HitDamage(hit.damage)
  Porteurs DSL de `IdunBattleLogic.Entities.DSLBehaviors$$TransferHit` : exactement deux --
      IdunBattleLogic.Entities.Abilities.Triggered.Loki.DrawFireAbility (1109)
      IdunBattleLogic.Entities.Abilities.Triggered.Loki.PrimarchOfTheFirstLegionAbility (1511)

MONTAGE. `DrawFire` n'a que deux porteurs -- `blackSmnTerminator` (SUMMON, dont l'unique invocateur
`EnvFactionSummons:BlackLegion` est une ability d'ENVIRONNEMENT portee par aucune unite du
catalogue) et `blackNpc2Terminator` (npc, refuse par `buildNormalizedBC`). On GREFFE donc le passif
sur une unite du pool (`catalog_inject.write_grafted_seed_bc`, `case-92` §5bis volet passif). La
greffe est legitime : `DrawFireAbility$$CreateTrigger` ne lit du porteur que sa POSITION
(`IsAdjacent`) et son camp (`AreFriends`) ; `CreateBehaviour` ne lit ni stat, ni trait, ni arme, et
l'entree gameconfig de `DrawFire` n'a ni variable ni constante.

DEUX runners STRICTEMENT identiques (meme seed, meme board, memes rosters, memes patchs de stats),
un seul bit de difference : la greffe. Les chiffres lus sont les PV perdus par la CIBLE et par le
VOISIN au cours d'UNE attaque.

Usage (depuis scripts/python, session warmee) :
    python probe_411_transfer_hit_guaranteed_block.py --state-file <ABSOLU> [--board MC1_67]
                                                      [--seed 31337]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
ATTACKER = "necroDestroyer"     # 6 coups de melee -> indices impairs 1,3,5 = 3 coups transferes
VICTIM = "astraBullgryn"        # cible de l'attaque (a-units)
CARRIER = "astraCreed"          # greffon DrawFire, adjacent a VICTIM au spawn (a-units)
ABILITY = "DrawFire"
MOVE_STAT = 12                  # Movement du greffon d'attaque : rejoint la cible en UN move


def sid() -> int:
    return int(requests.get(HOST + "/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    r = requests.post("%s/api/scripts/%d/rpc" % (HOST, s),
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def _run(argv: list, cwd: Path) -> str:
    p = subprocess.run([sys.executable] + argv, cwd=str(cwd), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return (p.stdout or "") + (p.stderr or "")


def _units(s: int, rid: int) -> dict:
    dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
    return {int(u["id"]): u for u in (dv.get("units") or [])}


def _find(units: dict, visual_id: str):
    for uid, u in units.items():
        if u.get("visualId") == visual_id:
            return int(uid), u
    raise RuntimeError("unite %r absente du runner" % (visual_id,))


def _normal_ability_id(units: dict, uid: int) -> int:
    """Id de l'ATTAQUE NORMALE CONCRETE de `uid` (`decisionView.units[].abilities[]`,
    `kind == "normal"`) -- mirror de `rl_duel._normal_ability_map` (TF18).

    #411-r2 : `act ability` SANS `--ability` auto-resolvait depuis `attackPlans`, qui porte une
    entree PAR ABILITY castable sur la cible, et retenait la DERNIERE -- donc l'ACTIVE. Le natif
    jouait alors une autre ability que celle qu'on croyait mesurer. On la NOMME toujours, et on
    LEVE si le kind normal manque plutot que de retomber sur un defaut silencieux."""
    u = units.get(int(uid)) or {}
    for ab in (u.get("abilities") or []):
        if ab.get("kind") == "normal" and ab.get("id") is not None:
            return int(ab["id"])
    raise RuntimeError("pas d'ability kind='normal' sur u%s -- ne pas deviner" % (uid,))


def _adjacent_free(s: int, rid: int, units: dict, target_pos: dict, mover: int):
    bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
    tiles = {int(t["id"]): t for t in (bg.get("tiles") or [])}
    by_pos = {(int(t["col"]), int(t["row"])): int(t["id"]) for t in tiles.values()}
    occupied = {(int(u["pos"]["col"]), int(u["pos"]["row"]))
                for uid, u in units.items() if u.get("pos") and int(uid) != mover}
    tid = by_pos.get((int(target_pos["col"]), int(target_pos["row"])))
    if tid is None:
        raise RuntimeError("tuile de la cible introuvable")
    for n in (tiles.get(tid, {}).get("neighbours") or []):
        t = tiles.get(int(n))
        if t is None or t.get("walkable") is False:
            continue
        p = (int(t["col"]), int(t["row"]))
        if p in occupied:
            continue
        return p
    raise RuntimeError("aucune tuile libre adjacente a la cible")


def one_run(pydir: Path, state_file: Path, seed_bc, seed: str, board: str, label: str) -> dict:
    extra = ["--rank", "17", "--p-units", ATTACKER,
             "--a-units", "%s,%s" % (VICTIM, CARRIER),
             "--crit", "0,0", "--crit-target", "0,0", "--block-target", "0,0",
             "--unit-stat", "%s:Movement=%d" % (ATTACKER, MOVE_STAT),
             "--board", board]
    if seed_bc:
        extra = ["--seed-bc", str(seed_bc)] + extra
    out = _run(["rl_duel.py", "build", "--seed", seed, "--state-file", str(state_file)] + extra,
               pydir)
    st = json.loads(state_file.read_text(encoding="utf-8"))
    rid = int(st["runnerId"])
    s = sid()
    units = _units(s, rid)
    att, _ = _find(units, ATTACKER)
    vic, uv = _find(units, VICTIM)
    car, uc = _find(units, CARRIER)
    hp_v0, hp_c0 = int(uv.get("hp") or 0), int(uc.get("hp") or 0)
    to = _adjacent_free(s, rid, units, uv["pos"], att)
    mv = _run(["rl_duel.py", "act", "move", "--unit", str(att), "--to", "%d,%d" % to,
               "--state-file", str(state_file)], pydir)
    # #411-r2 -- `--ability` EXPLICITE, OBLIGATOIRE. Sans lui, l'auto-resolution de `rl_duel`
    # retenait la DERNIERE entree d'`attackPlans` pour ce couple, c'est-a-dire l'ACTIVE du
    # caster (`necroDestroyer` -> 1006 MultiThreatEliminator) et non l'attaque normale que ce
    # probe croit confronter. `rl_duel` REFUSE desormais l'ambiguite (rc 2) au lieu de choisir.
    at = _run(["rl_duel.py", "act", "ability", "--caster", str(att), "--target", str(vic),
               "--ability", str(_normal_ability_id(units, att)),
               "--state-file", str(state_file)], pydir)
    units2 = _units(s, rid)
    hp_v1 = int((units2.get(vic) or {}).get("hp") or 0)
    hp_c1 = int((units2.get(car) or {}).get("hp") or 0)
    rpc(s, "disposeRunner", {"runnerId": rid}, 20)
    return {"label": label, "runner": rid,
            "victim_lost": hp_v0 - hp_v1, "carrier_lost": hp_c0 - hp_c1,
            "victim_hp": [hp_v0, hp_v1], "carrier_hp": [hp_c0, hp_c1],
            "move_tail": mv[-160:].replace("\n", " "), "atk_tail": at[-160:].replace("\n", " "),
            "build_tail": out[-160:].replace("\n", " ")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="31337")
    a = ap.parse_args()
    pydir = Path(__file__).resolve().parent
    sf = Path(a.state_file).resolve()
    sys.path.insert(0, str(pydir))
    import catalog_inject as CI
    import host_inputs                                        # noqa: F401 (garde data/)

    grafted = sf.parent / "drawfire-grafted-bc.json"
    path, reports = CI.write_grafted_seed_bc(grafted, ["%s:%s" % (CARRIER, ABILITY)])
    print("[graft] %s" % json.dumps(reports, ensure_ascii=True))

    base = one_run(pydir, sf, None, a.seed, a.board, "SANS greffe (temoin)")
    graf = one_run(pydir, sf, path, a.seed, a.board, "AVEC DrawFire greffe")
    for r in (base, graf):
        print("[%-22s] victim_lost=%-6d carrier_lost=%-6d victim=%s carrier=%s"
              % (r["label"], r["victim_lost"], r["carrier_lost"],
                 r["victim_hp"], r["carrier_hp"]))
    print("[verdict] transfert observe = %s"
          % ("OUI" if (graf["carrier_lost"] > 0 and base["carrier_lost"] == 0
                       and graf["victim_lost"] < base["victim_lost"]) else "NON"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
