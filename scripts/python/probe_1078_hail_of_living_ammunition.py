"""#1078 -- CONFRONTATION LIVE de `HailOfLivingAmmunition_ExtraHits` (1042).

Mesure ce que le NATIF fait sur un montage ou UN SEUL facteur bouge par phase. L'oracle de coups
est le nombre d'EVENEMENTS de degat portes par une attaque normale (meme extraction que
`probe_1018_hungering_swarm.py`, dont ce probe est le pendant de famille).

Attendu du port (arbre natif, cf. `engine/entities/effects/loki/hail_of_living_ammunition.py`) :

    coups = base_arme + extraHit * |{ allies ADJACENTS a l'ATTAQUANT dont l'unitId est dans la
                                      constante unitIds }|,  et SEULEMENT si l'attaque est RANGED

PORTEUR (ventile) : le passif est porte par le summon `tyranSmnTermagant` ET par CINQ npc
(`tyranNpc3Termagant`, `...Kronos`, `...Gorgon`, `..._SyncPvp_Kronos`, `..._SyncPvp_Gorgon`).

  * VOIE 1 (summoner unite)      -- EXCLUE, par balayage EXHAUSTIF du gameconfig : `tyranSmnTermagant`
    n'apparait QUE dans les `constants.unitIds` de ses propres passifs (`HailOfLivingAmmunition`,
    `BroodProgenitor`, `SynapticBacklash`) ; aucune `constants.unitId*` ne le nomme. Les trois
    `SpawnTermagants{,2,3}` invoquent des `GuildBoss1Npc*`, pas lui. Confirme a l'execution :
    `catalog_inject.explicit_stats("tyranSmnTermagant")` refuse -- << aucune ability du gameconfig
    ne declare 'tyranSmnTermagant' >>.
  * VOIE 2 (ability d'ENVIRONNEMENT) -- EXCLUE : `EnvFactionSummons:Tyranids` invoque
    `tyranSmnBarbgaunt`.
  * VOIE 3 (jumeau npc)          -- RETENUE, et ce n'est meme pas un mirror par `visualId` : les
    cinq npc PORTENT le passif eux-memes (`units.npc.<id>.passiveAbilities[0]`).
    `--explicit-stats tyranNpc3Termagant:45` (le nom NU est refuse par `--p-units`, qui doit
    reprendre la chaine VERBATIM, suffixe de palier compris).

LES QUATRE PHASES -- chacune deplace UN SEUL facteur :

  * `armed`  -- 2 Termagants allies ADJACENTS a l'ATTAQUANT, cible a d = 2 -> attaque RANGED,
                compte = 2 ;
  * `far`    -- LES MEMES unites, posees hors du ring-1 de l'attaquant : seule la GEOMETRIE change
                -> compte 0. Refute << ces Termagants ajoutent des coups par leur seule PRESENCE >> ;
  * `melee`  -- geometrie `armed` INCHANGEE cote pairs, mais la cible est ADJACENTE : l'attaque
                normale passe sur l'arme de MELEE -> le gate `IsRangedAttack` doit FERMER. Refute
                << le bonus vaut pour toute attaque >> ;
  * `kronos` -- 2 `tyranNpc3TermagantKronos` adjacents (geometrie IDENTIQUE a `armed`), dont le
                `visualId` gameconfig est `GuildBoss1Npc2TyranTermagantKronos` -- present dans
                `unitIds`, alors que leur id de CONFIG ne l'est pas. Cette phase MESURE lequel des
                deux ids le natif compare (cf. la docstring d'`entities/selectors/units.py::
                UnitsWithIds`, qui laissait la question ouverte cote offline).

Usage (state-file ABSOLU, `--runner` explicite pour re-jouer sur un runner deja monte) :

    python probe_1078_hail_of_living_ammunition.py --phase armed  --state-file <abs>.json
    python probe_1078_hail_of_living_ammunition.py --phase far    --state-file <abs>.json
    python probe_1078_hail_of_living_ammunition.py --phase melee  --state-file <abs>.json
    python probe_1078_hail_of_living_ammunition.py --phase kronos --state-file <abs>.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request

HOTE = "http://127.0.0.1:8765"
ATTACKER = "tyranNpc3Termagant:45"
PEER_ARMED = "tyranNpc3Termagant:45"
PEER_KRONOS = "tyranNpc3TermagantKronos:45"    # meme Termagant au sens du JEU, autre id de CONFIG
TARGET = "ultraTitus"
BOARD = "MC1_67"

#: Placement -- l'ATTAQUANT au centre (c'est LUI le centre du voisinage, contraste #1018 ou c'est la
#: cible). `hexgeo.distance((3,4), .) == 1` pour (2,3) (2,4) (3,3) (3,5) (4,3) (4,4) ; les deux
#: tuiles retenues sont a elevation 3, LA MEME que (3,4) -> la porte `|dElev| < 2` de
#: `TileQuery$$IterateAdjacentTiles` ne peut pas trancher entre les deux lectures d'adjacence.
ATT_POS = (3, 4)
NEAR = [(2, 4), (3, 3)]                        # adjacents a l'ATTAQUANT, elev 3 comme lui
FAR = [(1, 4), (1, 5)]                         # d(attaquant) = 2, memes unites
T_RANGED = (5, 4)                              # d(attaquant) = 2 -> arme a distance (Bio, r2)
T_MELEE = (4, 3)                               # d(attaquant) = 1 -> arme de melee (Physical)

_SID: "int | None" = None


def session_id() -> int:
    """Id de la session Frida VIVANTE, LU du host -- jamais un litteral."""
    global _SID
    if _SID is None:
        with urllib.request.urlopen(f"{HOTE}/api/admin/status", timeout=10) as r:
            st = json.loads(r.read().decode())
        s = (st or {}).get("session") or {}
        if s.get("status") != "running":
            raise SystemExit(f"[1078] pas de session Frida vivante : {s.get('status')!r}")
        _SID = int(s["id"])
    return _SID


def rpc(method: str, params: dict, timeout: int = 60):
    """Corps attendu par le host : `{method, args: [<params>], timeout: <ms>}` -- `args` POSITIONNEL."""
    body = json.dumps({"method": method, "args": [params],
                       "timeout": int(timeout * 1000)}).encode()
    req = urllib.request.Request(f"{HOTE}/api/scripts/{session_id()}/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 10) as r:
        out = json.loads(r.read().decode())
    if isinstance(out, dict) and out.get("error"):
        raise RuntimeError(f"{method}: {out['error']}")
    res = out.get("result", out) if isinstance(out, dict) else out
    if isinstance(res, dict) and res.get("ok") is False:
        raise RuntimeError(f"{method}: {res.get('error')}")
    return res


def amounts(res, tid: int, ability_id) -> list:
    """Les montants de degat de l'attaque = UN PAR COUP."""
    out = []
    for a in (res.get("actions") or []) if isinstance(res, dict) else []:
        for e in (a.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == ability_id:
                out.append(int(td["Amount"]))
    return out


def build_args(phase: str) -> list:
    """Les arguments `rl_duel build` d'une phase. UN SEUL montage, quatre configurations."""
    peer = PEER_KRONOS if phase == "kronos" else PEER_ARMED
    spots = FAR if phase == "far" else NEAR
    tpos = T_MELEE if phase == "melee" else T_RANGED
    argv = ["--board", BOARD,
            "--p-units", f"{ATTACKER},{peer},{peer}",
            "--explicit-stats", ATTACKER,
            "--a-units", TARGET,
            "--hp-target", "900000", "--armor-target", "0",
            "--crit", "0,0", "--block-target", "0,0",
            "--place", f"{ATTACKER}:{ATT_POS[0]},{ATT_POS[1]}"]
    if phase == "kronos":
        argv += ["--explicit-stats", PEER_KRONOS]
    argv += ["--place", f"{peer}:{spots[0][0]},{spots[0][1]}",
             "--place", f"{peer}:{spots[1][0]},{spots[1][1]}",
             "--a-place", f"{TARGET}:{tpos[0]},{tpos[1]}"]
    return argv


def build(phase: str, state_file: str, seed: str) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", state_file] + build_args(phase)
    p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for ln in (p.stdout or "").splitlines():
        if "runnerId=" in ln:
            return int(ln.split("runnerId=")[1].split()[0])
    print(p.stdout[-4000:] if p.stdout else "", p.stderr[-2000:] if p.stderr else "")
    raise SystemExit("[1078] build a echoue -- pas de runnerId")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=("armed", "far", "melee", "kronos"), required=True)
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed", default="10781")
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    rid = a.runner if a.runner is not None else build(a.phase, a.state_file, a.seed)
    print(f"[1078] phase={a.phase} runner={rid}")
    try:
        import hexgeo
        from engine.entities.effects.loki.hail_of_living_ammunition import (
            HailOfLivingAmmunitionExtraHitsEffect, _unit_ids)

        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]

        def pos(u):
            p = u.get("pos") or {}
            return (p.get("col"), p.get("row"))

        tgt = next((u for u in units if u.get("visualId") == TARGET), None)
        if tgt is None:
            raise SystemExit(f"[1078] cible absente : {[u.get('visualId') for u in units]}")
        tp = pos(tgt)
        att = next((u for u in units if u.get("id") != tgt["id"] and pos(u) == ATT_POS), None)
        if att is None:
            raise SystemExit(f"[1078] aucun attaquant sur {ATT_POS} -- montage rate")
        aid, tid = att["id"], tgt["id"]

        ids = set(_unit_ids())
        peers = [u for u in units
                 if u["id"] not in (aid, tid)
                 and hexgeo.distance(pos(u), ATT_POS) == 1
                 and u.get("team") == att.get("team")
                 and u.get("visualId") in ids]
        print(f"[1078] attaquant u{aid}@{ATT_POS} ({att.get('visualId')})  "
              f"cible u{tid}@{tp}  d(att,cible) = {hexgeo.distance(ATT_POS, tp)}")
        for u in units:
            print(f"        u{u['id']:<4} {str(u.get('visualId')):<36} team={u.get('team')} "
                  f"pos={pos(u)} d(att)={hexgeo.distance(pos(u), ATT_POS)} "
                  f"{'[dans unitIds]' if u.get('visualId') in ids else ''}")
        print(f"[1078] pairs retenus par le filtre unitIds = {len(peers)}")

        norm = next((ab for ab in (att.get("abilities") or [])
                     if "NormalAttack" in str(ab.get("name") or "")), None)
        if norm is None:
            raise SystemExit(f"[1078] pas d'attaque normale sur u{aid}")

        # Le PORT, sur un board monte depuis le MEME `decisionView`. `is_melee` est DERIVE de la
        # distance mesuree (d == 1 -> melee), jamais suppose.
        is_melee = hexgeo.distance(ATT_POS, tp) == 1
        board = {"att_id": aid, "tgt_id": tid, "attack_pos": ATT_POS, "t_pos": tp,
                 "is_melee": is_melee,
                 "pos_by_id": {u["id"]: pos(u) for u in units},
                 "team_by_id": {u["id"]: u.get("team") for u in units},
                 "vid_by_id": {u["id"]: u.get("visualId") for u in units},
                 "hp_by_id": {u["id"]: u.get("hp") for u in units},
                 "hpmax_by_id": {u["id"]: u.get("hpMax") for u in units}}
        eff = HailOfLivingAmmunitionExtraHitsEffect("HailOfLivingAmmunition_ExtraHits")
        bonus = eff.create_effect_hits_bonus_for_attack(True, board)
        port = 0 if bonus is None else int(bonus.value)
        print(f"[1078] PORT : is_melee={is_melee} -> bonus = +{port}")

        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": aid, "targetId": tid,
            "abilityType": norm["id"]}}, 90)
        am = amounts(res, tid, norm["id"])
        print(f"[1078] RESULTAT phase={a.phase} : {len(am)} coup(s) natif(s) -> {am}")
        return 0
    finally:
        if a.runner is None and not a.keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 30)
                print(f"[1078] runner {rid} dispose")
            except Exception as e:                                # noqa: BLE001
                print(f"[1078] dispose KO: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
