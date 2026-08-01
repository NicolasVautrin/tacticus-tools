"""#411-r2 -- DISCRIMINANT de l'ecart d'ECHELLE port/natif du BRAS TEMOIN de
`probe_411r1_transfer_port.py` (port 426 contre natif 3433, ~x8,06).

LA QUESTION BINAIRE, posee AVANT la methode
--------------------------------------------
Deux lectures tiennent, et le symptome seul ne les separe pas :

  (a) BUG DE PORT   -- un facteur perdu dans la chaine de degat du port ;
  (b) ARTEFACT DE MONTAGE -- le bras temoin n'atteint pas le regime qu'on croit, et
      les deux cotes ne calculent PAS la meme chose.

La question qui les separe :

    >> Sur le MEME etat pre-attaque, le nombre que le PORT calcule et le nombre que le
    >> NATIF applique sont-ils deux mesures de LA MEME attaque ?

Elle se tranche avec un TROISIEME nombre, natif, independant du tirage et de l'execution :
la PREDICTION native de l'attaque normale sur ce couple, prise sur le MEME etat --
`IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions` (RPC `aiPredict`),
qui rend `healthDamage [min,max]` pour la serie ENTIERE.

Trois nombres, donc :

    P = prediction NATIVE  (aiPredict, etat pre-attaque, aucun tirage)
    G = total du PORT      (`AttackDamageOperation.execute`, meme etat)
    N = delta PV NATIF     (`act ability`, l'execution reelle)

et la table de verite est SANS recouvrement :

    N dans [P.min, P.max] et G hors     -> (a) BUG DE PORT     : le natif fait bien ce
                                           qu'il predit, le port diverge -> localiser l'ETAGE.
    G dans [P.min, P.max] et N hors     -> (b) MONTAGE         : le port fait ce que le natif
                                           PREDIT, mais l'execution natif fait autre chose
                                           (plusieurs attaques, autre ability, autre cible...).
    G et N tous deux hors               -> ni l'un ni l'autre : la prediction elle-meme ne
                                           decrit pas ce montage -> le dire, ne rien conclure.

C'est la seule facon de ne PAS fitter un scalaire : on n'ajuste aucun facteur, on demande
a un troisieme temoin natif lequel des deux cotes il valide.

ETAGES (imprimes dans tous les cas, pour que la localisation ne demande pas un 2e run)
--------------------------------------------------------------------------------------
`combatSnapshot` = les stats RESOLUES par le natif (`GetStat`). Le port rend `base`
(= sa stat ATTACK lue), `armor`, `pierce`, `hits`, `clean_min/clean_max` (bornes du coup
APRES reduction) et `per_hit`. Les confronter etage par etage repond a « QUEL etage perd
le facteur » sans jamais avoir a le supposer.

Usage (depuis scripts/python, session warmee) :
    python probe_411r2_scale_discriminant.py --state-file <ABSOLU> [--board MC1_67]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import urllib.request

HOST = "http://127.0.0.1:8765"
ATTACKER = "necroDestroyer"     # 6 coups de melee (montage #411-r1)
VICTIM = "astraBullgryn"        # cible de l'attaque (a-units)
CARRIER = "astraCreed"          # 2e a-unit du montage temoin (aucune greffe ici)
MOVE_STAT = 12


def sid() -> int:
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=10) as r:
        return int(json.loads(r.read().decode("utf-8"))["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    """`timeout` en SECONDES cote appelant ; le host attend des MILLISECONDES."""
    body = json.dumps({"method": method, "args": args or {},
                       "timeout": int(timeout) * 1000}).encode("utf-8")
    req = urllib.request.Request(HOST + "/api/scripts/%d/rpc" % s, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 20) as r:
        out = json.loads(r.read().decode("utf-8"))
    if isinstance(out, dict) and "result" in out:
        return out["result"]
    return out


def _run(argv: list, cwd: Path) -> str:
    p = subprocess.run([sys.executable] + argv, cwd=str(cwd), capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("%s -> rc=%d\n%s\n%s" % (argv[:3], p.returncode, p.stdout[-1500:],
                                                    p.stderr[-1500:]))
    return p.stdout


def _units(s: int, rid: int) -> dict:
    dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
    return {int(u["id"]): u for u in (dv.get("units") or [])}


def normal_ability_id(units: dict, uid: int) -> int:
    """Id de l'ATTAQUE NORMALE CONCRETE de `uid`, lu dans `decisionView.units[].abilities[]`
    (`kind == "normal"`). Mirror de `rl_duel._normal_ability_map` (TF18).

    POURQUOI CE HELPER EXISTE (#411-r2) : `rl_duel act ability` SANS `--ability` auto-resolvait
    depuis `attackPlans`, qui porte une entree PAR ABILITY castable sur la cible -- et sa boucle
    retenait la DERNIERE, donc l'ACTIVE. Un probe qui croyait confronter l'attaque normale
    faisait jouer au natif l'active du caster ; l'ecart se lisait comme une divergence de PORT.
    On NOMME donc l'ability, toujours. Leve si le kind normal est absent : un defaut silencieux
    est precisement ce qui a produit le faux symptome."""
    u = units.get(int(uid)) or {}
    for ab in (u.get("abilities") or []):
        if ab.get("kind") == "normal" and ab.get("id") is not None:
            return int(ab["id"])
    raise RuntimeError("pas d'ability kind='normal' sur u%s (abilities=%r) -- ne pas deviner"
                       % (uid, [(a.get("id"), a.get("kind")) for a in (u.get("abilities") or [])]))


def _find(units: dict, visual_id: str):
    for uid, u in units.items():
        if u.get("visualId") == visual_id:
            return int(uid), u
    raise RuntimeError("unite %r absente du runner" % (visual_id,))


def _adjacent_free(s: int, rid: int, units: dict, target_pos: dict, mover: int):
    """Une tuile LIBRE adjacente a la cible -- on DEPLACE l'attaquant pour forcer la melee."""
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


def _port_replay(s: int, rid: int, att: int, vic: int) -> dict:
    """Rejoue le MEME etat pre-attaque dans le PORT. `bind_live_rpc` obligatoire (#363)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state, bind_live_rpc
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent, StatsComponent
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.entities.stats import StatType
    bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
    dec = rpc(s, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc(s, "observeBattle", {"runnerId": rid}, 60)
    snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 90)
    tm = rpc(s, "tileMeta", {"runnerId": rid}, 90)
    prev = bind_live_rpc(lambda method, args=None, timeout=60: rpc(s, method, args, timeout))
    try:
        st = load_state(dec, ob, snap, board=Board(bg["tiles"], adjacency="evenq"), tiles=tm)
    finally:
        bind_live_rpc(prev)
    st.rng = IntBasedMersenneTwister(777)

    def _hp(uid: int) -> int:
        e = st.get_entity(int(uid))
        hc = e.get_component(HealthComponent) if e is not None else None
        return int(getattr(hc, "hp", 0) or 0)

    def _stats(uid: int) -> dict:
        e = st.get_entity(int(uid))
        sc = e.get_component(StatsComponent) if e is not None else None
        if sc is None:
            return {}
        # `ARMOR`(4) est OBSOLETE cote natif -- l'armure EFFECTIVE est `DEFENSE`(3), et
        # `FIXED_ARMOR`(16) la part plate. Lire `ARMOR` rendait 0 et faisait croire a une
        # armure nulle alors que le port en applique 3513 (mesure du 1er run de ce probe).
        out = {}
        for nm in ("ATTACK", "DEFENSE", "FIXED_ARMOR", "HEALTH", "BLOCK_CHANCE",
                   "BLOCK_DAMAGE", "CRIT_CHANCE", "CRIT_DAMAGE", "EXTRA_HITS"):
            stt = getattr(StatType, nm, None)
            if stt is not None:
                try:
                    out[nm] = int(sc.ctx.stat(stt))
                except Exception as e:                                # noqa: BLE001
                    out[nm] = "ERR:%s" % (e,)
        return out

    hp_v0 = _hp(vic)
    n0 = int(st.rng.call_count)
    r = AttackDamageOperation.execute(st, int(att), int(vic), 20) or {}
    n1 = int(st.rng.call_count)
    return {"total": int(r.get("total") or 0), "hits": int(r.get("hits") or 0),
            "base": r.get("base"), "armor": r.get("armor"), "pierce": r.get("pierce"),
            "clean_min": r.get("clean_min"), "clean_max": r.get("clean_max"),
            "per_hit": [int(x) for x in (r.get("per_hit") or [])],
            "rolls": [int(x) for x in (r.get("rolls") or [])],
            "shield_dmg": r.get("shield_dmg"), "armor_dmg": r.get("armor_dmg"),
            "did_crit": r.get("did_crit"), "did_block": r.get("did_block"),
            "did_evade": r.get("did_evade"), "profile": r.get("profile"),
            "ranged": r.get("ranged"), "effects": r.get("effects"),
            "victim_lost": hp_v0 - _hp(vic), "hp_v0_port": hp_v0,
            "rng_draws": n1 - n0,
            "stats_att": _stats(att), "stats_vic": _stats(vic)}


def _snapshot_stats(s: int, rid: int, uids: list) -> dict:
    """Stats RESOLUES du natif (`GetStat`). La cle est `entityId` -- et c'est la MEME que
    la cle ECS du port (`combatSnapshot.entityId == decisionView.id`, cf. `snapshot.py`)."""
    snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 90)
    want = {int(x) for x in uids}
    out = {}
    for u in (snap.get("units") or []):
        eid = u.get("entityId")
        if eid is not None and int(eid) in want:
            out[int(eid)] = {"stats": u.get("stats"), "healthMax": u.get("healthMax"),
                             "shields": u.get("shields"), "weapons": u.get("weapons"),
                             "traits": u.get("traits")}
    return out


def _native_prediction(s: int, rid: int, att: int, vic: int, ability=None) -> dict:
    body = {"runnerId": rid, "unitId": int(att), "targetId": int(vic), "fresh": True}
    if ability is not None:
        body["abilityType"] = int(ability)
    return rpc(s, "aiPredict", body, 90) or {}


def _plan_for(dv: dict, att: int, vic: int) -> dict:
    for p in (dv.get("attackPlans") or []):
        if int(p.get("unitId") or -1) != int(att):
            continue
        for ev in (p.get("evals") or []):
            if int(ev.get("targetId") or -1) == int(vic):
                return ev
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--rank", default="17")
    ap.add_argument("--block-target", default="0,0",
                    help="chance,amount de block de la CIBLE (le probe #411-r1 le passe en "
                         "100,500 pour exercer la route de block).")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner (debug)")
    a = ap.parse_args()
    pydir = Path(__file__).resolve().parent
    sf = Path(a.state_file).resolve()
    sys.path.insert(0, str(pydir))
    import host_inputs                                        # noqa: F401 (garde data/)

    # --- MONTAGE : le BRAS TEMOIN de probe_411r1, a l'identique (aucune greffe) ---
    extra = ["--rank", str(a.rank), "--p-units", ATTACKER,
             "--a-units", "%s,%s" % (VICTIM, CARRIER),
             "--crit", "0,0", "--crit-target", "0,0", "--block-target", a.block_target,
             "--unit-stat", "%s:Movement=%d" % (ATTACKER, MOVE_STAT),
             "--board", a.board]
    _run(["rl_duel.py", "build", "--seed", a.seed, "--state-file", str(sf)] + extra, pydir)
    st = json.loads(sf.read_text(encoding="utf-8"))
    rid = int(st["runnerId"])
    s = sid()
    try:
        units = _units(s, rid)
        att, _ = _find(units, ATTACKER)
        vic, uv = _find(units, VICTIM)
        car, _ = _find(units, CARRIER)
        to = _adjacent_free(s, rid, units, uv["pos"], att)
        _run(["rl_duel.py", "act", "move", "--unit", str(att), "--to", "%d,%d" % to,
              "--state-file", str(sf)], pydir)
        units1 = _units(s, rid)
        hp_v0 = int((units1.get(vic) or {}).get("hp") or 0)
        hp_c0 = int((units1.get(car) or {}).get("hp") or 0)

        # --- ETAT PRE-ATTAQUE : les trois nombres, tous pris ICI ---
        dv = rpc(s, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 8}, 150)
        plan = _plan_for(dv, att, vic)
        ability = plan.get("abilityId")
        pred = _native_prediction(s, rid, att, vic, ability)
        port = _port_replay(s, rid, att, vic)
        nat = _snapshot_stats(s, rid, [att, vic])

        # --- EXECUTION NATIVE ---
        _run(["rl_duel.py", "act", "ability", "--caster", str(att), "--target", str(vic),
              "--ability", str(normal_ability_id(units1, att)), "--state-file", str(sf)], pydir)
        units2 = _units(s, rid)
        hp_v1 = int((units2.get(vic) or {}).get("hp") or 0)
        hp_c1 = int((units2.get(car) or {}).get("hp") or 0)
    finally:
        if not a.keep:
            try:
                rpc(s, "disposeRunner", {"runnerId": rid}, 20)
            except Exception as e:                                    # noqa: BLE001
                print("[warn] disposeRunner: %s" % (e,))

    N = hp_v0 - hp_v1
    G = int(port["total"])
    pf = pred.get("pred") or {}
    pmin = pf.get("healthDmgMin")
    pmax = pf.get("healthDmgMax")
    print("=== #411-r2 DISCRIMINANT (bras TEMOIN, runner %d) ===" % rid)
    print("[montage] att=u%d %s -> vic=u%d %s (carrier u%d, aucune greffe)"
          % (att, ATTACKER, vic, VICTIM, car))
    print("[plan]    abilityId=%s  eval=%s" % (ability, json.dumps(plan, ensure_ascii=True)[:600]))
    print("[pred]    NATIF aiPredict ok=%s ability=%s dictCount=%s layoutError=%s"
          % (pred.get("ok"), pred.get("ability"), pred.get("dictCount"),
             pred.get("layoutError")))
    print("[pred]    health=[%s..%s] shield=[%s..%s] hpBefore=%s shieldBefore=%s "
          "willKillDmg=%s mightKillDmg=%s"
          % (pmin, pmax, pf.get("shieldDmgMin"), pf.get("shieldDmgMax"),
             pf.get("hpBefore"), pf.get("shieldBefore"), pf.get("willKillDmg"),
             pf.get("mightKillDmg")))
    print("[hp]      victim %d -> %d  (N = %d)   carrier %d -> %d (%d)"
          % (hp_v0, hp_v1, N, hp_c0, hp_c1, hp_c0 - hp_c1))
    print("[port]    G = %d  hits=%s per_hit=%s" % (G, port["hits"], port["per_hit"]))
    print("[port]    base(ATTACK)=%s armor=%s pierce=%s clean=[%s..%s] shield_dmg=%s "
          "crit=%s block=%s evade=%s ranged=%s profile=%s"
          % (port["base"], port["armor"], port["pierce"], port["clean_min"],
             port["clean_max"], port["shield_dmg"], port["did_crit"], port["did_block"],
             port["did_evade"], port["ranged"], port["profile"]))
    print("[port]    stats lues att=%s" % json.dumps(port["stats_att"], ensure_ascii=True))
    print("[port]    stats lues vic=%s" % json.dumps(port["stats_vic"], ensure_ascii=True))
    print("[natif]   snapshot att=%s" % json.dumps(nat.get(att), ensure_ascii=True)[:1200])
    print("[natif]   snapshot vic=%s" % json.dumps(nat.get(vic), ensure_ascii=True)[:1200])
    if isinstance(pmin, int) and isinstance(pmax, int) and pmax > 0:
        n_in = pmin <= N <= pmax
        g_in = pmin <= G <= pmax
        print("[disc]    N dans la prediction ? %s   G dans la prediction ? %s" % (n_in, g_in))
        if n_in and not g_in:
            print("[VERDICT] (a) BUG DE PORT -- le natif applique ce qu'il predit ; "
                  "le port diverge. Localiser l'ETAGE avec les lignes [port]/[natif].")
        elif g_in and not n_in:
            print("[VERDICT] (b) MONTAGE -- le port calcule ce que le natif PREDIT ; "
                  "l'execution native fait autre chose que cette attaque.")
        else:
            print("[VERDICT] INDETERMINE -- ni N ni G (ou les deux) ne tombent dans la "
                  "prediction : la prediction ne decrit pas ce montage. Ne rien conclure.")
    else:
        print("[disc]    prediction NON LUE (aiPredict ok=%s error=%s) -- discriminant "
              "NON RENDU." % (pred.get("ok"), pred.get("error")))
    print("[ratio]   N/G = %.3f" % (N / G if G else float("nan")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
