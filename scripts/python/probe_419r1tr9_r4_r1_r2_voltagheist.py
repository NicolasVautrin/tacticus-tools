#!/usr/bin/env python
"""#419-r1-tr9-r4-r1-r2 -- `VoltagheistField_ExtraHit` (1381) : +1 coup gate ATTAQUE NORMALE.

CE QUE CE PROBE MESURE. `IdunBattle.Entities.Effects.Loki.VoltagheistField_ExtraHitEffect$$
CreateEffectHitsBonusForAttack` = `ForAddition(get_OwnerIsCaster & IsNormalAttack,
Get(ConfigConst 0x2b = extraHit))` -- jumeau structurel exact de `PowerTrip_FullHealthEffect`.

MONTAGE. Le passif natif `VoltagheistField` n'est porte que par des npc
(`admecNpc3Electropriest`, `admecNpc3ElectropriestSurv`) et par un summon d'ENVIRONNEMENT
(`admecSmnElectropriest`, invoque par la seule ability `EnvFactionSummons:AdeptusMechanicus`, que
porte aucune unite) -> **greffe du passif** sur une unite du pool (`case-92` SS5bis,
`catalog_inject.graft_passive_ability`, `TriggeredAbilityType.VoltagheistField = 1302`).

L'effet 1381 n'existe QUE dans la fenetre qui suit un soin recu :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.VoltagheistField_OnRepairAbility$$CreateTrigger`
= `On(0x30 = 48 UnitRepaired) & get_OwnerIsTarget`. Il faut donc un REPAIR (pas un heal : le
porteur doit etre `Mechanical`). Le porteur choisi est `necroWarden`, dont le trait `LivingMetal`
<< Regenerates {hpPct}% of its max Health at the start of the players' turn. This unit is also
Mechanical >> fournit le repair TOUT SEUL, au debut de son propre tour -- aucune seconde unite,
aucun cast a piloter. Il suffit qu'elle soit BLESSEE (`--unit-stat RemainingHealth < Health`).

PROTOCOLE : DEUX BRAS, meme board / meme seed / meme geometrie (le layout du 1er bras est rejoue
tel quel dans le 2nd), qui ne different QUE par la greffe.
  * `graft` : `BC.Units[necroWarden].PassiveAbilities` contient `VoltagheistField` ;
  * `none`  : le meme BC sans la greffe.
⚠ Le bras `t1 / t2` (mesurer avant puis apres un aller-retour de tours) a ete essaye d'abord et NE
MARCHE PAS : le repair de `LivingMetal` a deja eu lieu quand la premiere mesure est prise (le
placement `_drive_to` traverse des tours), donc l'effet 1381 est present AUX DEUX mesures et le
delta est nul. Mesure du 2026-08-02 -- c'est un montage non installe, pas un verdict.
TEMOIN INTERNE : une seconde unite de la meme equipe, non greffee et non reparee, mesuree dans les
deux bras -- tout ce qui bougerait pour une autre raison (aura, position, seed) se lirait sur elle.

VERDICT (meme forme que le probe jumeau `probe_419r1tr9_r4_r1_r2_shroud_psalm.py`) :
  1. MONTAGE INSTALLE, mesure 100 % NATIVE : `hits(porteur, graft) == hits(porteur, none) +
     extraHit` et `hits(temoin, graft) == hits(temoin, none)`. Si (1) tombe, rien d'autre n'est
     lisible.
  2. ACCORD port/natif sur `appliedHits`, dans les deux bras, sur les deux attaquants.
  3. CONTRE-EPREUVE : le port prive du comportement `VoltagheistField_ExtraHit` doit MORDRE de
     `-extraHit` sur le porteur du bras `graft`, et de 0 partout ailleurs.

Usage (depuis scripts/python) :
    python probe_419r1tr9_r4_r1_r2_voltagheist.py --state-file <ABSOLU> [--keep]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import catalog_inject as CI                                       # noqa: E402
import gameconfig as GC                                           # noqa: E402
import probe_124_line_elevation_decision as P124                  # noqa: E402
import probe_419r1tr9_r4_boltstorm_pred as P419                   # noqa: E402
from probe_419r1tr9_r4_boltstorm_pred import MontageError         # noqa: E402

BOARD = "MC1_67"
SEED = "41381"
CARRIER = "necroWarden"        # porteur greffe : Mechanical + LivingMetal (repair de debut de tour)
WITNESS = "templAggressor"     # temoin : ni greffe, ni repare
TARGET = "astraBullgryn"       # la cible commune des deux attaques mesurees
HP = "900000"
HURT = "300000"                # RemainingHealth du porteur : blesse -> la regen REPARE vraiment
GRAFT = "VoltagheistField"


ARMS = ("graft", "none")


def write_bc(out_path: str, arm: str) -> str:
    """Seed BC du bras. Les DEUX bras partagent le MEME catalogue (la config `VoltagheistField` est
    posee dans les deux par la greffe) ; seul `BC.Units[CARRIER].PassiveAbilities` differe -- meme
    protocole que `probe_419r1tr9_r4_r1_fold_context`, pour qu'aucune autre entree du BC ne bouge."""
    bc = CI._load_seed(None)
    CI.graft_passive_ability(bc, CARRIER, GRAFT, replace=False)   # pose la config + l'id dans l'unite
    node = (bc.get("Abilities") or {}).get("PassiveAbilities") or {}
    if GRAFT not in node:
        raise MontageError(f"config {GRAFT} absente de BC.Abilities.PassiveAbilities")
    hits = [u for u in (bc.get("Units") or []) if u.get("Id") == CARRIER]
    if not hits:
        raise MontageError(f"{CARRIER} absent de BC.Units")
    if arm == "none":                                             # on RETIRE l'id, la config RESTE
        aid = CI.triggered_ability_id(GRAFT)
        for u in hits:
            u["PassiveAbilities"] = [x for x in (u.get("PassiveAbilities") or [])
                                     if int(x) != int(aid)]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(bc, fh)
    return out_path


def build_args(bc_path: str) -> list:
    """Arguments `rl_duel build`, SANS `--seed` ni `--state-file`."""
    stats = ";".join([f"{CARRIER}:Health={HP},RemainingHealth={HURT}",
                      f"{WITNESS}:Health={HP},RemainingHealth={HP}",
                      f"{TARGET}:Health={HP},RemainingHealth={HP}"])
    return ["--board", BOARD, "--seed-bc", bc_path,
            "--p-units", f"{CARRIER},{WITNESS}", "--a-units", TARGET, "--unit-stat", stats]


def build(state_file: str, bc_path: str) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            *build_args(bc_path), "--state-file", state_file]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def dispose(state_file: str) -> None:
    subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", state_file],
                   cwd=_HERE, capture_output=True, text=True)


def extra_hit() -> int:
    """`GetNumberConstant(config, 0x2b)` de l'ability `VoltagheistField` -- MEME source que le port."""
    return int((GC.ability(GRAFT) or {}).get("constants", {}).get("extraHit"))


def port_hits_no_volt(scene, cid, tgt, tile) -> int:
    """Le PORT prive du comportement `VoltagheistField_ExtraHit`. On mute la METHODE (pas le
    registre `EFFECT_CLASSES`) : la scene est deja hydratee, retirer la cle ne defait rien --
    mesure du 2026-08-02 sur le probe jumeau `ShroudPsalm`, ou le mutant-registre rendait un
    deplacement NUL et donc un vert menteur."""
    from engine.entities.effects.loki.hits import VoltagheistFieldExtraHitEffect as V
    saved = V.create_effect_hits_bonus_for_attack
    V.create_effect_hits_bonus_for_attack = (
        lambda self, is_normal_attack=True, att_ctx=None: None)
    try:
        return P419.port_fields(scene, cid, tgt, tile)["hits"]
    finally:
        V.create_effect_hits_bonus_for_attack = saved


def measure(rpc, rid, attackers: dict, tgt_id: int) -> dict:
    """`{label: {native, port, ab, effects}}` -- l'attaque NORMALE de chaque attaquant sur `tgt_id`."""
    out = {}
    for label, (uid, tile) in attackers.items():
        _dv, ctx = P419._fresh_ctx(rpc, rid, uid)
        ab = P419._normal_ability_id(rpc, rid, uid)
        out[label] = {"uid": uid, "ab": ab,
                      "native": P419.native_fields(rpc, rid, uid, tgt_id, ab, tile),
                      "port": P419.port_fields(ctx.scene, uid, tgt_id, tile),
                      "effects": [e.name for e in (ctx.scene.effects(uid) or [])],
                      "scene": ctx.scene, "tile": tile}
    return out


def run(sid, rpc, rid: int, arm: str, layout_vis: dict | None) -> dict:
    elev, walk, _tid = P124._board(sid, rid)
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    dv, _pos = P124._positions(sid, rid)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mine = [u for u in units if u.get("ctrl")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    myplayer = mine[0]["owner"]

    def by_vis(vis, own):
        u = next((x for x in units if x.get("visualId") == vis
                  and ((x.get("owner") == myplayer) == own)), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster "
                               f"({'joueur' if own else 'adverse'})")
        return u["id"]

    cid, wid, tid_ = by_vis(CARRIER, True), by_vis(WITNESS, True), by_vis(TARGET, False)

    # Geometrie : les DEUX attaquants a distance 2 de la cible, meme elevation, et non adjacents
    # entre eux (aucune aura ring-1 ne doit relier le porteur au temoin). Le layout du PREMIER bras
    # est REJOUE tel quel dans le second, par visualId -- les deux bras sont alors strictement
    # comparables.
    import hexgeo
    if layout_vis is not None:
        layout = {cid: layout_vis[CARRIER], wid: layout_vis[WITNESS], tid_: layout_vis[TARGET]}
    else:
        layout = None
        for t in cells:
            ring2 = [c for c in cells if hexgeo.distance(t, c) == 2 and elev.get(c) == elev.get(t)]
            for i, c in enumerate(ring2):
                for wv in ring2[i + 1:]:
                    if hexgeo.distance(c, wv) >= 2:
                        layout = {cid: c, wid: wv, tid_: t}
                        break
                if layout:
                    break
            if layout:
                break
        if layout is None:
            raise MontageError(f"montage NON INSTALLE : aucune geometrie (cible ring-2 des deux) "
                               f"sur {BOARD}")
    if not P124._drive_to(sid, rid, walk, elev, layout):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"[{arm}] montage NON INSTALLE : placement incomplet -- voulu {layout}, "
                           f"obtenu { {u: pos.get(u) for u in layout} }")
    P124._give_turn_back(sid, rid, myplayer)

    attackers = {"carrier": (cid, layout[cid]), "witness": (wid, layout[wid])}
    rows = measure(rpc, rid, attackers, tid_)
    mutant = {lab: port_hits_no_volt(rows[lab]["scene"], rows[lab]["uid"], tid_, rows[lab]["tile"])
              for lab in attackers}
    return {"arm": arm, "rid": rid, "carrier": cid, "witness": wid, "target": tid_,
            "layout_vis": {CARRIER: layout[cid], WITNESS: layout[wid], TARGET: layout[tid_]},
            "rows": rows, "mutant": mutant}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--keep", action="store_true", help="ne dispose pas le runner")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    bump = extra_hit()
    stem = os.path.splitext(args.state_file)[0]
    bc_dir = os.path.join(_HERE, "..", "..", "logs", "probe_419r1tr9_r4_r1_r2")
    res, layout_vis = {}, None
    for arm in ARMS:
        st = f"{stem}_{arm}.json"
        bc = write_bc(os.path.abspath(os.path.join(bc_dir, f"seed_volt_{arm}.json")), arm)
        rid = build(st, bc)
        try:
            res[arm] = run(sid, rpc, rid, arm, layout_vis)
            layout_vis = res[arm]["layout_vis"]
        finally:
            if not args.keep:
                dispose(st)

    print(f"board {BOARD} seed {SEED} | extraHit = {bump} | layout {layout_vis}")
    for arm in ARMS:
        r = res[arm]
        print(f"[{arm:<5}] runner {r['rid']} | porteur u{r['carrier']} ({CARRIER}, blesse "
              f"{HURT}/{HP}) | temoin u{r['witness']} ({WITNESS}) | cible u{r['target']} ({TARGET})")
        for lab in ("carrier", "witness"):
            row = r["rows"][lab]
            n, p = row["native"], row["port"]
            print(f"         {lab:<8} ab={row['ab']:<5} nat=({n['rawMin']}, {n['rawMax']}, "
                  f"h{n['hits']})  port=({p['rawMin']}, {p['rawMax']}, h{p['hits']})")
        print(f"         effets porteur : {r['rows']['carrier']['effects']}")

    rc = 0
    print("\n=== VERDICT ===")
    d_c = (res["graft"]["rows"]["carrier"]["native"]["hits"]
           - res["none"]["rows"]["carrier"]["native"]["hits"])
    d_w = (res["graft"]["rows"]["witness"]["native"]["hits"]
           - res["none"]["rows"]["witness"]["native"]["hits"])
    print(f"  [1] montage (NATIF seul) : d(porteur) = {d_c} (attendu {bump}), "
          f"d(temoin) = {d_w} (attendu 0)")
    if d_c != bump or d_w != 0:
        print("      MONTAGE NON INSTALLE -- rien d'autre n'est lisible")
        return 2

    for arm in ARMS:
        for lab in ("carrier", "witness"):
            n = res[arm]["rows"][lab]["native"]["hits"]
            p = res[arm]["rows"][lab]["port"]["hits"]
            ok = (n == p)
            rc += 0 if ok else 1
            print(f"  [2] accord {arm:<5} {lab:<8} natif h{n} vs port h{p} -> "
                  f"{'OK' if ok else 'DIVERGE'}")

    b_c = res["graft"]["mutant"]["carrier"] - res["graft"]["rows"]["carrier"]["port"]["hits"]
    b_w = res["graft"]["mutant"]["witness"] - res["graft"]["rows"]["witness"]["port"]["hits"]
    n_c = res["none"]["mutant"]["carrier"] - res["none"]["rows"]["carrier"]["port"]["hits"]
    print(f"  [3] contre-epreuve (port sans VoltagheistField_ExtraHit) : deplacement "
          f"graft/porteur = {b_c} (attendu {-bump}), graft/temoin = {b_w} (attendu 0), "
          f"none/porteur = {n_c} (attendu 0)")
    if b_c != -bump or b_w != 0 or n_c != 0:
        rc += 1
    print(f"\nrc = {rc}")
    return 1 if rc else 0


if __name__ == "__main__":
    raise SystemExit(main())
