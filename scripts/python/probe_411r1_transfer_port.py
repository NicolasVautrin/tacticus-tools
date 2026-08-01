"""#411-r1 -- CONFRONTATION DU PORT de `TransferHit` (DrawFire 1109) au natif.

Montage : celui de `probe_411_transfer_hit_guaranteed_block.py` (greffe du passif `DrawFire` sur
`astraCreed`, adjacent a `astraBullgryn` au spawn de `MC1_67`), rejoue ici en confrontant le PORT
au NATIF sur le MEME etat pre-attaque.

CE QUI EST COMPARE, et pourquoi ce n'est pas un scalaire --

  Le regime est `--crit 0,0 --crit-target 0,0`, donc le seul RNG restant est le tirage de degat
  dans les bornes reduites. Port et natif ne partagent PAS l'etat du PRNG : comparer les TOTAUX
  bit-a-bit n'a aucun sens. Ce qu'on compare est donc STRUCTUREL, et c'est ce que le transfert
  change :

    * la VENTILATION per-coup cote port : les coups d'index IMPAIR doivent valoir 0 sur la cible
      originale (`AmountIsOdd(CurrentHitIndex)`, 0-based), les PAIRS doivent etre non nuls ;
    * le PORTEUR doit encaisser, et le nombre de sous-attaques doit valoir le nombre de coups
      impairs (3 sur 6) ;
    * la BRANCHE de block : chaque coup transfere doit sortir avec `did_block` vrai et
      **zero tirage** consomme au block (route `ApplyBlockDamage` slot 4) ;
    * le RATIO natif victim/carrier doit encadrer celui du port (memes bornes, tirages differents).

  CONTRE-EPREUVE (le bras qui rend le verdict falsifiable) : le MEME probe SANS greffe. Si le port
  transferait quand meme, ou si le bras greffe ne transferait pas, on le voit -- un vert des deux
  cotes serait le resultat suspect (cf. `feedback_verify_the_mutation_applied`).

Usage (depuis scripts/python, session warmee) :
    python probe_411r1_transfer_port.py --state-file <ABSOLU> [--board MC1_67] [--seed 31337]

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
ATTACKER = "necroDestroyer"     # 6 coups de melee
VICTIM = "astraBullgryn"        # cible de l'attaque (a-units)
CARRIER = "astraCreed"          # greffon DrawFire, adjacent a VICTIM au spawn (a-units)
ABILITY = "DrawFire"
MOVE_STAT = 12


def sid() -> int:
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=10) as r:
        return int(json.loads(r.read().decode("utf-8"))["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    """⚠ `timeout` est ici en SECONDES ; le host, lui, attend des MILLISECONDES (il repond
    « RPC timeout after 90ms (base 90x1) » si on lui passe 90). Les probes anterieurs passent la
    valeur telle quelle et se font donc jeter -- cf. le rapport #411-r1."""
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


def _normal_ability_id(units: dict, uid: int) -> int:
    """Id de l'ATTAQUE NORMALE CONCRETE de `uid` (`decisionView.units[].abilities[]`,
    `kind == "normal"`) -- mirror de `rl_duel._normal_ability_map` (TF18).

    #411-r2 : c'est ICI qu'etait l'ecart d'echelle du bras TEMOIN (port 426 / natif 3433,
    « x8,06 »). `act ability` SANS `--ability` auto-resolvait depuis `attackPlans`, qui porte
    une entree PAR ABILITY castable sur la cible, et retenait la DERNIERE -- soit
    `1006 MultiThreatEliminator` (ACTIVE, config-based) et non les 6 coups de melee que ce
    probe confronte. Le port resolvait `AttackDamageOperation.execute` : les deux cotes ne
    calculaient pas la meme chose. `rl_duel` REFUSE desormais l'ambiguite (rc 2)."""
    u = units.get(int(uid)) or {}
    for ab in (u.get("abilities") or []):
        if ab.get("kind") == "normal" and ab.get("id") is not None:
            return int(ab["id"])
    raise RuntimeError("pas d'ability kind='normal' sur u%s -- ne pas deviner" % (uid,))


def _find(units: dict, visual_id: str):
    for uid, u in units.items():
        if u.get("visualId") == visual_id:
            return int(uid), u
    raise RuntimeError("unite %r absente du runner" % (visual_id,))


def _is_adjacent(pa: dict, pb: dict) -> bool:
    import hexgeo
    return hexgeo.distance((int(pa["col"]), int(pa["row"])),
                           (int(pb["col"]), int(pb["row"]))) == 1


def _adjacent_free(s: int, rid: int, units: dict, target_pos: dict, mover: int):
    """Une tuile LIBRE adjacente a la cible -- on DEPLACE l'attaquant pour forcer la melee,
    on ne subit pas la geometrie de spawn. Verbatim de `probe_411`."""
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


def _port_replay(s: int, rid: int, att: int, vic: int, car: int, expect_graft: bool) -> dict:
    """Rejoue le MEME etat pre-attaque dans le PORT et rend la ventilation per-coup.

    `bind_live_rpc` est OBLIGATOIRE (#363) : sans le transport ambiant, `_auto_ability_states`
    rend `no-transport`, `UnitContext.passive_abilities` reste None, et le port RETOMBE sur la
    derivation gameconfig par `visualId` -- ou la GREFFE n'existe pas. Le passif serait INERTE,
    sans erreur : le probe rendrait « le port ne transfere pas » pour une raison de HARNAIS."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state, bind_live_rpc
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent, StatsComponent
    from engine.runner.operations.damage import AttackDamageOperation
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
    _sc = st.get_entity(int(car)).get_component(StatsComponent)
    carried = list(getattr(_sc.ctx, "passive_abilities", None) or [])
    if expect_graft and ABILITY not in carried:
        raise RuntimeError("le port ne voit PAS la greffe (passives=%r) -- montage casse, "
                           "pas un verdict" % carried)
    if (not expect_graft) and ABILITY in carried:
        raise RuntimeError("le bras TEMOIN porte la greffe (passives=%r) -- montage casse" % carried)

    def _hp(uid: int) -> int:
        e = st.get_entity(int(uid))
        hc = e.get_component(HealthComponent) if e is not None else None
        return int(getattr(hc, "hp", 0) or 0)

    hp_v0, hp_c0 = _hp(vic), _hp(car)
    n0 = int(st.rng.call_count)
    r = AttackDamageOperation.execute(st, int(att), int(vic), 20) or {}
    n1 = int(st.rng.call_count)
    per_hit = [int(x) for x in (r.get("per_hit") or [])]
    return {"per_hit": per_hit,
            "zero_at_odd": all(per_hit[i] == 0 for i in range(1, len(per_hit), 2)),
            "nonzero_at_even": all(per_hit[i] > 0 for i in range(0, len(per_hit), 2)),
            "did_block": bool(r.get("did_block")),
            "victim_lost": hp_v0 - _hp(vic), "carrier_lost": hp_c0 - _hp(car),
            "rng_draws": n1 - n0}


def one_run(pydir: Path, state_file: Path, seed_bc, seed: str, board: str, label: str,
            expect_graft: bool, block_target: str = "0,0") -> dict:
    extra = ["--rank", "17", "--p-units", ATTACKER,
             "--a-units", "%s,%s" % (VICTIM, CARRIER),
             "--crit", "0,0", "--crit-target", "0,0", "--block-target", block_target,
             "--unit-stat", "%s:Movement=%d" % (ATTACKER, MOVE_STAT),
             "--board", board]
    if seed_bc:
        extra = ["--seed-bc", str(seed_bc)] + extra
    _run(["rl_duel.py", "build", "--seed", seed, "--state-file", str(state_file)] + extra, pydir)
    st = json.loads(state_file.read_text(encoding="utf-8"))
    rid = int(st["runnerId"])
    s = sid()
    units = _units(s, rid)
    att, _ = _find(units, ATTACKER)
    vic, uv = _find(units, VICTIM)
    car, uc = _find(units, CARRIER)
    # GENERALISATION : on ne SUBIT pas la geometrie de spawn -- sur un board ou le porteur n'est
    # pas deja voisin de la cible, on l'y AMENE (`applyAction` ne verifie pas la propriete du
    # `unitId` : les deux camps se pilotent). Sans ca, un 2e board rendrait « pas de transfert »
    # pour une raison de PLACEMENT, pas de port.
    if not _is_adjacent(uv["pos"], uc["pos"]):
        cto = _adjacent_free(s, rid, units, uv["pos"], car)
        _run(["rl_duel.py", "act", "move", "--unit", str(car), "--to", "%d,%d" % cto,
              "--state-file", str(state_file)], pydir)
        units = _units(s, rid)
        uv = units[vic]
    to = _adjacent_free(s, rid, units, uv["pos"], att)
    _run(["rl_duel.py", "act", "move", "--unit", str(att), "--to", "%d,%d" % to,
          "--state-file", str(state_file)], pydir)
    units1 = _units(s, rid)
    hp_v0 = int((units1.get(vic) or {}).get("hp") or 0)
    hp_c0 = int((units1.get(car) or {}).get("hp") or 0)
    port = _port_replay(s, rid, att, vic, car, expect_graft)
    _run(["rl_duel.py", "act", "ability", "--caster", str(att), "--target", str(vic),
          "--ability", str(_normal_ability_id(units1, att)),          # #411-r2 : jamais implicite
          "--state-file", str(state_file)], pydir)
    units2 = _units(s, rid)
    hp_v1 = int((units2.get(vic) or {}).get("hp") or 0)
    hp_c1 = int((units2.get(car) or {}).get("hp") or 0)
    rpc(s, "disposeRunner", {"runnerId": rid}, 20)
    return {"label": label, "runner": rid,
            "nat_victim_lost": hp_v0 - hp_v1, "nat_carrier_lost": hp_c0 - hp_c1,
            "port": port}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--block-target", default="0,0",
                    help="chance,amount de block de la CIBLE. Non nul = le REGIME DISCRIMINANT du "
                         "port : les coups PAIRS tirent leur block (slots 2/3), les coups "
                         "TRANSFERES n'en tirent AUCUN (slot 4). Sans lui, la propriete portee "
                         "n'est pas exercee.")
    a = ap.parse_args()
    pydir = Path(__file__).resolve().parent
    sf = Path(a.state_file).resolve()
    sys.path.insert(0, str(pydir))
    import catalog_inject as CI
    import host_inputs                                        # noqa: F401 (garde data/)

    grafted = sf.parent / "drawfire-grafted-bc-r1.json"
    path, reports = CI.write_grafted_seed_bc(grafted, ["%s:%s" % (CARRIER, ABILITY)])
    print("[graft] %s" % json.dumps(reports, ensure_ascii=True))

    base = one_run(pydir, sf, None, a.seed, a.board, "TEMOIN (sans greffe)", False,
                   a.block_target)
    graf = one_run(pydir, sf, path, a.seed, a.board, "AVEC DrawFire greffe", True,
                   a.block_target)
    for r in (base, graf):
        p = r["port"]
        print("[%-22s] NATIF victim=%-6d carrier=%-6d | PORT victim=%-6d carrier=%-6d "
              "per_hit=%s draws=%s" % (r["label"], r["nat_victim_lost"], r["nat_carrier_lost"],
                                       p["victim_lost"], p["carrier_lost"], p["per_hit"],
                                       p["rng_draws"]))
    bp, gp = base["port"], graf["port"]
    # LE check de fond : la CONSOMMATION de tirages de block. Etalonnage mesure sur ce montage --
    # `next_internal` comme `next_bool` coutent 2 `genrand_int32` chacun, et l'attaque normale
    # consomme 1 resolve par coup (cf. `damage_hits.py`, « NORMALE cc=0 : 1 tirage/coup »).
    #     rng_draws = 2 * (resolve + block_rolls)
    #     resolve   = <coups de la serie> + <sous-attaques de transfert, 1 coup chacune>
    # Un coup TRANSFERE prend la route `ApplyBlockDamage` (slot 4) : il consomme son resolve sur
    # la cellule [0,0] mais AUCUN tirage de block. Donc, dans le bras greffe :
    #     block_rolls attendus = <coups NON transferes> + <sous-attaques>
    # Si le port roulait le block d'un coup transfere, on lirait `+1` par coup transfere -- et
    # c'est exactement la desynchronisation SILENCIEUSE que la garde #411 existe pour empecher.
    def _block_ledger(p: dict) -> dict:
        ph = p["per_hit"]
        n_xfer = sum(1 for i in range(1, len(ph), 2) if ph[i] == 0)
        resolve = len(ph) + n_xfer
        rolls = (p["rng_draws"] - 2 * resolve) // 2
        return {"n_xfer": n_xfer, "resolve": resolve, "block_rolls": rolls,
                "expected": (len(ph) - n_xfer) + n_xfer,
                "if_xfer_rolled": len(ph) + n_xfer}
    bl_b, bl_g = _block_ledger(bp), _block_ledger(gp)
    for nm, bl in (("TEMOIN", bl_b), ("GREFFE", bl_g)):
        print("[ledger] %-7s resolve=%d block_rolls=%d attendu=%d (si les transferes roulaient: %d)"
              % (nm, bl["resolve"], bl["block_rolls"], bl["expected"], bl["if_xfer_rolled"]))
    block_on = a.block_target != "0,0"
    checks = {
        "natif_transfere": (graf["nat_carrier_lost"] > 0 and base["nat_carrier_lost"] == 0
                            and graf["nat_victim_lost"] < base["nat_victim_lost"]),
        "port_transfere": gp["carrier_lost"] > 0 and gp["zero_at_odd"] and gp["nonzero_at_even"],
        "port_temoin_inerte": bp["carrier_lost"] == 0 and all(x > 0 for x in bp["per_hit"]),
        "port_did_block": gp["did_block"],
        "meme_nombre_de_coups": len(bp["per_hit"]) == len(gp["per_hit"]),
        # inerte quand `--block-target 0,0` (aucune source -> 0 tirage des deux cotes, donc
        # NON DISCRIMINANT : le dire plutot que rendre un vert qui ne prouve rien).
        "zero_block_roll_sur_transfere": (bl_g["block_rolls"] == bl_g["expected"]
                                          and bl_g["block_rolls"] != bl_g["if_xfer_rolled"]
                                          ) if block_on else None,
    }
    if not block_on:
        print("[warn] --block-target 0,0 : aucune source de block -> la propriete PORTEE "
              "(0 tirage sur un coup transfere) n'est PAS exercee. Relancer avec 100,500.")
    checks = {k: v for k, v in checks.items() if v is not None}
    for k, v in checks.items():
        print("[check] %-22s %s" % (k, "OK" if v else "ECHEC"))
    print("[verdict] %s" % ("PORT CONFORME" if all(checks.values()) else "DIVERGENCE"))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
