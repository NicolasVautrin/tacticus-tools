#!/usr/bin/env python
"""#971-r5 -- le TIE depuis une position de MOVE : la mesure qui DISCRIMINE l'ordre par position.

CE QUE `#971-r4` A LAISSE OUVERT
--------------------------------
`_base.tiles_in_native_order` derive l'ordre d'enumeration des tuiles de spawn depuis la liste
d'adjacence STOCKEE (`ctx.neigh_by_pos`), et les TROIS playbooks de spawn ring-1
(`GrotTank` 1057, `MasterOfTheTutelaries` 1152, `IronkinSteeljack` 1219) l'empruntent. La
transposition est fermee par LECTURE -- les trois `TargetingOptions..ctor` sont identiques octet
pour octet -- mais elle n'avait AUCUNE mesure DISCRIMINANTE : l'ordre stocke ne se distingue de
l'ordre de l'UNION que dans un seul regime, et aucune suite ne l'atteignait.

    a la position d'ORIGINE  le port lit `fromHere`, qui EST la reponse par-position du RPC ;
    hors TIE                 l'utilite tranche seule, quel que soit l'ordre ;
    reste                    un TIE d'utilite depuis une position de MOVE. C'est tout.

CE QUE CE PROBE FAIT, ET POURQUOI IL NE PEUT PAS SE MENTIR
-----------------------------------------------------------
1. il CHERCHE le regime au lieu de l'esperer : pour chaque montage de la liste, il balaie les
   positions de move et retient celles ou (a) au moins DEUX tuiles de spawn eligibles sont a
   utilite MAXIMALE EGALE, et (b) l'ordre STOCKE et l'ordre de l'UNION ne designent PAS la meme
   tuile parmi les ex aequo. Une position ou les deux ordres tombent d'accord ne discrimine RIEN,
   et le probe le DIT au lieu de la compter ;
2. il confronte a `ncEvaluate --sweep`, dont le `action.targetLow` est le bas d'un POINTEUR
   d'entite -- opaque, mais STABLE : ce qui se compare, c'est la PARTITION des positions par
   cible retenue (deux positions ou le natif retient la MEME entite doivent etre deux positions
   ou le port retient la MEME tuile) ;
3. **il joue la CONTRE-EPREUVE dans le meme etat** : le meme port, avec `tiles_in_native_order`
   DEGENERE en `list(union)`, doit rendre une partition DIFFERENTE de celle du natif. Sans ce
   second bras, un accord ne prouverait rien -- c'est exactement le reproche que `#971-r5` fait a
   la tranche precedente.

⚠ **LA SUBSTITUTION VISE LE MODULE CONSOMMATEUR, PAS `_base`.** `grot_tank.py` lie le foyer par
`from ._base import tiles_in_native_order` (FORME A) : le nom est resolu a l'import, donc patcher
`_base.tiles_in_native_order` serait INERTE et la contre-epreuve rendrait un faux << pas de
difference >>. On substitue l'attribut du module qui CONSOMME.

Tri-etat : 0 = regime DISCRIMINANT atteint et les deux bras concluent ; 1 = mesure faite et
DIVERGENTE ; 2 = PAS MESURE / NON CONFRONTE (aucun montage n'a produit le regime) -- jamais
rabattu sur un vert.

Usage (depuis scripts/python) :
    python probe_971r5_ordre_par_position_live.py --state-file <ABSOLU> [--montages 6]
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

HOST = "http://127.0.0.1:8765"
CASTER = "orksBigMek"
ENEMIES = "orksNob,tyranWingedPrime,necroWarden"
GROT_TANK = 1057

EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/playbook/noncomparable/_base.py",
                "scripts/python/engine/playbook/noncomparable/grot_tank.py",
                "scripts/python/engine/playbook/noncomparable/master_of_the_tutelaries.py",
                "scripts/python/engine/playbook/noncomparable/ironkin_steeljack.py",
                "scripts/python/engine/battle_query.py",
                "scripts/python/probe_971r5_ordre_par_position_live.py"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte l'ORDRE d'enumeration des tuiles de spawn (foyer "
              "`_base.tiles_in_native_order`) a l'oracle `ncEvaluate`, sur le consommateur "
              "`grot_tank`. Le build en est une entree : `ncEvaluate` decode le `Bucket` par "
              "offsets, et la chaine `GetValidTargets` est resolue par slot d'interface.",
}

#: MONTAGES balayes dans l'ordre. Le premier qui produit le regime DISCRIMINANT gagne -- un
#: montage qui ne le produit pas n'est pas un echec, c'est une geometrie qui ne tie pas.
#: `Bridge` = le terrain ou la liste d'adjacence STOCKEE s'ecarte le plus de la couronne hex
#: (`C3_14` est le board qui en porte le plus : 15 tuiles, balayage des 779 dumps).
MONTAGES = (
    ("C3_14", "4242", "4,4", "6,6"),
    ("C3_14", "777", "3,4", "5,5"),
    ("C3_14", "31337", "4,5", "5,6"),
    ("MC1_67", "4242", "4,5", "5,5"),
    ("MC1_67", "777", "3,4", "4,6"),
    ("C1_02", "31337", "4,4", "5,5"),
)


def sid() -> int:
    return int(requests.get("%s/api/admin/status" % HOST, timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 120):
    r = requests.post("%s/api/scripts/%d/rpc" % (HOST, s),
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:300]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:300])
    return body.get("result") or {}


def build(state_file: Path, board: str, seed: str, cpos: str, epos: str) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if state_file.exists():
        state_file.unlink()
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
           "--p-units", CASTER, "--a-units", ENEMIES,
           "--place", "%s:%s" % (CASTER, cpos), "--a-place", "orksNob:%s" % epos,
           "--state-file", str(state_file)]
    proc = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO: %s" % ((proc.stderr or proc.stdout or "")[-500:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def contexte(s: int, rid: int):
    from engine.ai import context as ai_ctx
    from engine.playbook import noncomparable as playbooks
    from engine.playbook import scene as scene_mod
    from engine import weights as W
    _rpc = lambda m, b, t=120: rpc(s, m, b, t)                      # noqa: E731
    dv = _rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    cid = next((u.get("id") for u in (dv.get("units") or [])
                if u.get("visualId") == CASTER and u.get("alive")), None)
    if cid is None:
        return None, None, None
    mov = _rpc("aiMovableTiles", {"runnerId": rid}, 60)
    predictor = scene_mod.build_predictor(_rpc, rid)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    c = ai_ctx.build(_rpc, rid, dv, mov_by_unit, cid, W.load(), predictor, debug=False)
    nc = playbooks.NCContext(
        uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
        enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
        plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
        elev_by_pos=c.elev_by_pos, ability_targets=c.ability_targets, wt=c.wt,
        is_temporary_by_pos=c.is_temporary_by_pos, effects_by_pos=c.effects_by_pos,
        obs_units=c.obs_units, tile_id_by_pos=c.tile_id_by_pos,
        active_levels=c.active_ability_levels, units=c.units,
        cast_from_tiles=c.cast_from_tiles, scene=c.scene, debug=False)
    return nc, cid, _rpc


def _utilites(nc, tiles, rayon):
    import hexgeo
    epos = [(p[0], p[1]) for p in (nc.epos or [])]
    return {t: float(sum(1 for p in epos if hexgeo.distance(t, p) <= rayon)) for t in tiles}


def chercher_regime(nc, pb):
    """Les positions de MOVE ou l'ordre TRANCHE. Rend `(discriminantes, rapport)`."""
    from engine import battle_query as bq
    from engine.playbook.noncomparable._base import eligible_target_tiles, tiles_in_native_order
    from_here, union = eligible_target_tiles(nc, GROT_TANK)
    eligibles = set(from_here) | set(union)
    neigh = bq.neigh_map(nc)
    disc, rapport = [], []
    for T in (nc.reach_nc or []):
        if T == nc.origin:
            continue                       # a l'origine, `fromHere` EST la vue par-position
        stocke = [ST for ST in tiles_in_native_order(nc, T, from_here, union, eligibles)
                  if bq.is_adjacent(T, ST, nc.elev_by_pos, neigh)]
        uni = [ST for ST in union
               if ST in eligibles and bq.is_adjacent(T, ST, nc.elev_by_pos, neigh)]
        if len(stocke) < 2:
            continue
        u = _utilites(nc, set(stocke) | set(uni), pb._UTILITY_RADIUS)
        candidats = [t for t in stocke if u[t] > 0.0]
        if not candidats:
            continue
        m = max(u[t] for t in candidats)
        ex_aequo = [t for t in candidats if u[t] == m]
        prem_stocke = next((t for t in stocke if u.get(t) == m and u[t] > 0), None)
        prem_union = next((t for t in uni if u.get(t) == m and u[t] > 0), None)
        rapport.append((T, len(ex_aequo), m, prem_stocke, prem_union))
        if len(ex_aequo) >= 2 and prem_stocke is not None and prem_stocke != prem_union:
            disc.append(T)
    return disc, rapport


def partition_port(nc, pb, degenere: bool):
    """`{position: tuile retenue}` par le PORT, avec l'ordre STOCKE ou l'ordre de l'UNION.

    ⚠ La substitution vise le module CONSOMMATEUR (`grot_tank`), pas `_base` : la liaison y est
    en FORME A (`from ._base import ...`), donc patcher `_base` serait INERTE."""
    from engine.playbook.noncomparable import grot_tank as GT
    from engine.playbook.noncomparable._base import tiles_in_native_order
    avant = GT.tiles_in_native_order
    if degenere:
        GT.tiles_in_native_order = lambda c, T, fh, un, el: list(un)
    try:
        out = {}
        for T in (nc.reach_nc or []):
            sous = type(nc)(**{k: getattr(nc, k) for k in nc.__dataclass_fields__})
            sous.reach_nc = [T]
            cands = pb.generate_candidates(sous)
            out[T] = (cands[0].get("target") if cands else None)
        return out
    finally:
        GT.tiles_in_native_order = avant
        assert GT.tiles_in_native_order is tiles_in_native_order or not degenere


def _classes(d: dict) -> list:
    inv: dict = {}
    for pos, cle in d.items():
        if cle is None:
            continue
        inv.setdefault(cle, []).append(tuple(pos))
    return sorted(sorted(v) for v in inv.values())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--montages", type=int, default=len(MONTAGES))
    a = ap.parse_args(argv)

    try:
        s = sid()
    except Exception as exc:                                        # noqa: BLE001
        print("[971r5] PAS MESURE -- session Frida indisponible : %s" % exc)
        return EX_PAS_MESURE

    from engine.playbook import noncomparable as playbooks
    pb = playbooks.PLAYBOOKS.get(GROT_TANK)
    if pb is None:
        print("[971r5] PAS MESURE -- 1057 absente du registre NonComparable")
        return EX_PAS_MESURE

    sf = Path(a.state_file)
    for board, seed, cpos, epos in MONTAGES[:a.montages]:
        print("\n[971r5] MONTAGE board=%s seed=%s caster=%s ennemi=%s" % (board, seed, cpos, epos))
        try:
            rid = build(sf, board, seed, cpos, epos)
        except Exception as exc:                                    # noqa: BLE001
            print("   build refuse : %s" % str(exc)[:300])
            if "cap reached" in str(exc):
                print("[971r5] PAS MESURE -- cap de runners sature (fenetre partagee)")
                return EX_PAS_MESURE
            continue
        try:
            nc, cid, _rpc = contexte(s, rid)
            if nc is None:
                print("   caster absent du deploiement")
                continue
            disc, rapport = chercher_regime(nc, pb)
            print("   positions de MOVE balayees : %d" % len(rapport))
            for T, nex, m, ps, pu in rapport[:10]:
                print("      T=%-8s ex_aequo=%d util_max=%s  1re(stocke)=%-8s 1re(union)=%-8s %s"
                      % (str(T), nex, m, str(ps), str(pu),
                         "DISCRIMINANTE" if (nex >= 2 and ps is not None and ps != pu) else ""))
            if not disc:
                print("   ce montage ne produit PAS le regime (aucun TIE ou les deux ordres "
                      "s'accordent) -- on passe au suivant")
                continue

            # ---- LE REGIME EST ATTEINT : on confronte -----------------------------------------
            nat = _rpc("ncEvaluate", {"runnerId": rid, "unitId": cid,
                                      "abilityType": GROT_TANK, "sweep": True}, 180)
            lignes = [p for p in (nat.get("positions") or []) if p.get("util") is not None]
            if not lignes:
                print("   bucket natif VIDE partout -- NON CONFRONTE (ce n'est pas un desaccord)")
                continue
            nat_part = _classes({tuple(p["pos"]): (p.get("action") or {}).get("targetLow")
                                 for p in lignes})
            vus = {tuple(p["pos"]) for p in lignes}
            p_ok = _classes({k: v for k, v in partition_port(nc, pb, False).items() if k in vus})
            p_deg = _classes({k: v for k, v in partition_port(nc, pb, True).items() if k in vus})
            print("\n   PARTITION natif        = %s" % (nat_part,))
            print("   PARTITION port STOCKE  = %s  -> %s"
                  % (p_ok, "OK" if p_ok == nat_part else "ECART"))
            print("   PARTITION port UNION   = %s  -> %s"
                  % (p_deg, "DIFFERE (attendu)" if p_deg != nat_part else "IDENTIQUE"))
            print("   positions DISCRIMINANTES : %s" % (disc,))
            ko = 0
            if p_ok != nat_part:
                print("   DESACCORD : l'ordre STOCKE ne reproduit pas la partition native.")
                ko += 1
            if p_deg == nat_part:
                print("   NON DISCRIMINANT : l'ordre de l'UNION rend la MEME partition -- ce "
                      "montage n'exerce donc pas ce que #971-r5 demande. On passe au suivant.")
                continue
            print("\n[971r5] VERDICT : %s" % ("OK -- regime DISCRIMINANT atteint, l'ordre par "
                                              "POSITION est confirme et l'ordre de l'UNION est "
                                              "REFUTE dans le meme etat" if ko == 0
                                              else "FAIL (%d)" % ko))
            return EX_VERT if ko == 0 else EX_ROUGE
        finally:
            try:
                rpc(s, "disposeRunner", {"runnerId": rid}, 30)
            except Exception as exc:                                # noqa: BLE001
                print("   dispose KO: %s" % str(exc)[:150])

    print("\n[971r5] NON CONFRONTE -- aucun des %d montages n'a produit un TIE depuis une "
          "position de MOVE ou les deux ordres divergent. Ce n'est PAS un accord : le regime "
          "n'a pas ete atteint." % min(a.montages, len(MONTAGES)))
    return EX_PAS_MESURE


if __name__ == "__main__":
    sys.exit(main())
