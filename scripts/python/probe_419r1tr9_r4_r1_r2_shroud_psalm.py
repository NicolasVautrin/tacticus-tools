#!/usr/bin/env python
"""#419-r1-tr9-r4-r1-r2 -- `ShroudPsalm` (1366) : le MALUS DEFENSEUR de coups gate ATTAQUE NORMALE.

CE QUE CE PROBE MESURE. `IdunBattle.Entities.Effects.Loki.ShroudPsalmEffect$$
CreateEffectHitsBonusForAttack` = `ForAdditionWithMinimum(get_OwnerIsTarget & IsNormalAttack,
Negative(Get(ConfigConst 0x2c = hitsReduction)), min=Get(1))`. C'est le SEUL porteur du noeud
`IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack` du cote DEFENSE du canal COUPS -- non porte,
le moteur SUR-COMPTE les coups portes contre une unite protegee.

LE BRAS QUI COMPTE : on mesure les coups **RECUS** par le porteur, pas ceux qu'il emet. Le porteur
de l'effet est donc la CIBLE de l'attaque mesuree.

MONTAGE (le porteur natif `admecBossBelisarius` est npc -> greffe, `case-92` SS5bis) :
  * `catalog_inject.graft_active_ability(CASTER, "ShroudPsalm")` -- l'active passe dans
    `BC.Units[CASTER].ActiveAbilities` ET sa config dans `BC.Abilities.ActiveAbilities` ;
  * equipe P = {CASTER, ALLY} -- l'ability vise `First(SortByFormula(Randomize(Friends(Caster,
    AllUnits - Caster, 3))), ., ConfigConst(0x11 = nrOfTargets = 2))`, donc **jusqu'a 2 allies, le
    caster EXCLU**. Avec UN SEUL allie le tirage est deterministe : ALLY est affecte, CASTER non ;
  * equipe A = {FOE}, un attaquant a beaucoup de coups d'arme (le malus est -2 et le plancher
    natif est 1 : il faut une base > 3 pour que la mesure ne bute pas sur le clamp) ;
  * mesure AVANT le cast, puis APRES le cast, sur les DEUX cibles. `CASTER` est le TEMOIN INTERNE
    (meme runner, memes positions, meme tour) : le natif ne doit rien lui retirer.

CE QUE LE VERDICT EXIGE (dans cet ordre) :
  1. MONTAGE INSTALLE -- mesure 100 % NATIVE : `hits(ALLY, apres) == hits(ALLY, avant) -
     hitsReduction` et `hits(CASTER, apres) == hits(CASTER, avant)`. Si (1) tombe, rien d'autre
     n'est lisible et le probe s'arrete : c'est un echec de MONTAGE, pas un verdict de port.
  2. ACCORD port/natif sur `appliedHits`, avant ET apres, sur les DEUX cibles.
  3. CONTRE-EPREUVE : le port prive de la classe `ShroudPsalm` (registre `EFFECT_CLASSES` vide de
     cette cle, effets re-hydrates) doit MORDRE de `+hitsReduction` sur ALLY APRES le cast, et
     de 0 partout ailleurs. Un mutant qui ne mord nulle part ne prouverait rien.

⚠ Seul `appliedHits` est confronte. Le meme `ShroudPsalmAbility$$ExecuteBehaviour` pose aussi
`0x55a = 1370 ShroudPsalm_Armor` (+extraArmor) et `0x555 = 1365 MachineVengeance` sur les memes
cibles : ils deplacent le DEGAT, pas le nombre de coups. Les bornes brutes sont IMPRIMEES pour
information, jamais assertees.

Usage (depuis scripts/python) :
    python probe_419r1tr9_r4_r1_r2_shroud_psalm.py --state-file <ABSOLU> [--keep]
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
SEED = "41366"
CASTER = "templAggressor"      # porteur greffe de l'active `ShroudPsalm`
ALLY = "astraBullgryn"         # le SEUL allie du caster -> cible deterministe de l'ability
FOE = "tauCrisis"              # attaquant : 6 coups melee / 6 coups ranged(2) -> base >> plancher 1
HP = "900000"                  # personne ne meurt pendant la mesure
GRAFT = "ShroudPsalm"


def write_bc(out_path: str) -> str:
    """Seed BC avec l'active `ShroudPsalm` greffee sur `CASTER`."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # `kind="active"` -> `graft_active_ability` : `ShroudPsalm` est une ACTIVE
    # (`ActiveAbilityType`), pas un passif -- le defaut `kind="passive"` chercherait un
    # `TriggeredAbilityType.ShroudPsalm` qui n'existe pas.
    p, _rep = CI.write_grafted_seed_bc(out_path, [f"{CASTER}:{GRAFT}"], kind="active")
    return str(p)


def build_args(bc_path: str) -> list:
    """Arguments `rl_duel build`, SANS `--seed` ni `--state-file` -- meme forme que les probes du
    foyer, pour que la garde jumelle puisse les passer telles quelles a `build_runner`."""
    stats = ";".join(f"{v}:Health={HP},RemainingHealth={HP}" for v in (CASTER, ALLY, FOE))
    # L'ATTAQUANT est dans MON equipe : `abilityTargets` (d'ou sort l'`ActiveAbilityType` concret de
    # l'attaque normale) ne renseigne que les unites du JOUEUR COURANT -- mesure du 2026-08-02, un
    # `unitId` adverse y rend zero ability. Le porteur de l'effet est donc dans l'equipe ADVERSE,
    # et le cast se fait pendant le tour adverse (cf. `run`).
    return ["--board", BOARD, "--seed-bc", bc_path,
            "--p-units", FOE, "--a-units", f"{CASTER},{ALLY}", "--unit-stat", stats]


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


def hits_reduction() -> int:
    """`GetNumberConstant(config, 0x2c)` de l'ability `ShroudPsalm` -- la MEME source que le port."""
    return int((GC.ability(GRAFT) or {}).get("constants", {}).get("hitsReduction"))


def port_hits_no_shroud(scene, cid, tgt, tile) -> int:
    """Le PORT prive du comportement `ShroudPsalm` : contre-epreuve.

    ⚠ On mute la METHODE de la classe, PAS le registre `EFFECT_CLASSES` : la scene est deja
    hydratee quand on arrive ici, donc retirer la cle du registre ne defait rien -- les instances
    construites restent des `ShroudPsalmEffect` et le mutant rend VERT sans avoir mordu (mesure du
    2026-08-02 : deplacement 0 au lieu de +hitsReduction, exactement le piege
    `feedback_verify_the_mutation_applied`). Le patch de methode, lui, agit sur les instances
    existantes."""
    from engine.entities.effects.loki.hits import ShroudPsalmEffect as SP
    saved = SP.create_effect_hits_malus_for_defense
    SP.create_effect_hits_malus_for_defense = (
        lambda self, is_melee=None, damage_profile=None, defender_on_cover=None,
        dist=None, is_normal_attack=True: None)
    try:
        return P419.port_fields(scene, cid, tgt, tile)["hits"]
    finally:
        SP.create_effect_hits_malus_for_defense = saved


def measure(rpc, rid, scene, atk_id, atk_tile, ab, targets: dict) -> dict:
    """`{label: {native, port}}` -- l'attaque NORMALE de `atk_id` depuis `atk_tile`, cible par cible."""
    out = {}
    for label, uid in targets.items():
        nat = P419.native_fields(rpc, rid, atk_id, uid, ab, atk_tile)
        prt = P419.port_fields(scene, atk_id, uid, atk_tile)
        out[label] = {"uid": uid, "native": nat, "port": prt}
    return out


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

    red = hits_reduction()
    bc = write_bc(os.path.abspath(os.path.join(
        _HERE, "..", "..", "logs", "probe_419r1tr9_r4_r1_r2", "seed_shroud.json")))
    rid = build(args.state_file, bc)
    try:
        res = run(sid, rpc, rid, red)
    finally:
        if not args.keep:
            dispose(args.state_file)

    print(f"runner {rid} | board {BOARD} seed {SEED} | hitsReduction = {red}")
    print(f"  caster u{res['caster']} @ {res['caster_pos']} ({CASTER}, {GRAFT} greffee)")
    print(f"  ally   u{res['ally']} @ {res['ally_pos']} ({ALLY})")
    print(f"  foe    u{res['foe']} @ {res['foe_pos']} ({FOE}), attaque normale = {res['ab']}")
    print(f"  effets d'ALLY apres le cast : {res['ally_effects']}")
    print(f"  effets du CASTER apres le cast : {res['caster_effects']}")
    print("\n  phase     cible    natif                       port")
    for phase in ("before", "after"):
        for label in ("ally", "caster"):
            n = res[phase][label]["native"]
            p = res[phase][label]["port"]
            print(f"  {phase:<9} {label:<8} ({n['rawMin']}, {n['rawMax']}, h{n['hits']})"
                  f"{'':<8} ({p['rawMin']}, {p['rawMax']}, h{p['hits']})")

    rc = 0
    print("\n=== VERDICT ===")
    d_ally = res["after"]["ally"]["native"]["hits"] - res["before"]["ally"]["native"]["hits"]
    d_cast = res["after"]["caster"]["native"]["hits"] - res["before"]["caster"]["native"]["hits"]
    print(f"  [1] montage (NATIF seul) : d(ally) = {d_ally} (attendu {-red}), "
          f"d(caster temoin) = {d_cast} (attendu 0)")
    if d_ally != -red or d_cast != 0:
        print("      MONTAGE NON INSTALLE -- rien d'autre n'est lisible")
        return 2

    for phase in ("before", "after"):
        for label in ("ally", "caster"):
            n = res[phase][label]["native"]["hits"]
            p = res[phase][label]["port"]["hits"]
            ok = (n == p)
            rc += 0 if ok else 1
            print(f"  [2] accord {phase:<6} {label:<7} natif h{n} vs port h{p} -> "
                  f"{'OK' if ok else 'DIVERGE'}")

    m_a, m_c = res["mutant"]["ally"], res["mutant"]["caster"]
    b_a = m_a - res["after"]["ally"]["port"]["hits"]
    b_c = m_c - res["after"]["caster"]["port"]["hits"]
    print(f"  [3] contre-epreuve (port sans la classe ShroudPsalm) : "
          f"deplacement ally = {b_a} (attendu {red}), caster = {b_c} (attendu 0)")
    if b_a != red or b_c != 0:
        rc += 1
    print(f"\nrc = {rc}")
    return 1 if rc else 0


def run(sid, rpc, rid: int, red: int) -> dict:
    """Place les trois unites, mesure AVANT, caste `ShroudPsalm`, mesure APRES."""
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

    cid, aid, fid = by_vis(CASTER, False), by_vis(ALLY, False), by_vis(FOE, True)

    # Geometrie : FOE a distance 2 de CASTER et d'ALLY (portee de son arme ranged), CASTER et ALLY
    # non adjacents entre eux pour que rien d'autre (aura ring-1) ne bouge d'une phase a l'autre.
    import hexgeo
    layout = None
    for f in cells:
        ring2 = [c for c in cells if hexgeo.distance(f, c) == 2 and elev.get(c) == elev.get(f)]
        for i, c in enumerate(ring2):
            for a in ring2[i + 1:]:
                if hexgeo.distance(c, a) >= 2:
                    layout = {cid: c, aid: a, fid: f}
                    break
            if layout:
                break
        if layout:
            break
    if layout is None:
        raise MontageError(f"montage NON INSTALLE : aucune geometrie (foe ring-2 des deux) sur {BOARD}")
    if not P124._drive_to(sid, rid, walk, elev, layout):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {layout}, "
                           f"obtenu { {u: pos.get(u) for u in layout} }")
    P124._give_turn_back(sid, rid, myplayer)

    ftile = layout[fid]
    _dv, ctx = P419._fresh_ctx(rpc, rid, fid)
    ab = P419._normal_ability_id(rpc, rid, fid)
    tgts = {"ally": aid, "caster": cid}
    before = measure(rpc, rid, ctx.scene, fid, ftile, ab, tgts)

    # --- le cast. Le caster est ADVERSE : on lui rend la main (`endturn`) avant, on la reprend
    # apres. `ShroudPsalm` n'a pas de cible choisie (selecteur auto `Friends(Caster, AllUnits -
    # Caster, 3)`) : on passe le caster en `targetId`.
    psalm = CI.active_ability_id(GRAFT)
    for _ in range(3):
        dv_now = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150) or {}
        if dv_now.get("currentPlayer") != myplayer:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    else:
        raise MontageError("montage NON INSTALLE : impossible de passer la main a l'adversaire")
    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": cid, "abilityType": psalm}}, 120)
    a0 = ((r or {}).get("actions") or [{}])[0]
    groups = sorted({e.get("group") for e in (a0.get("events") or []) if e.get("kind") == "group"})
    print(f"  cast {GRAFT} : ok={a0.get('ok')} mutated={a0.get('mutated')} "
          f"actionConsumed={a0.get('actionConsumed')} events={a0.get('eventCount')} "
          f"groups={groups} err={a0.get('error')}")
    if not a0.get("ok"):
        raise MontageError(f"montage NON INSTALLE : le cast de {GRAFT} est REFUSE : {a0}")
    P124._give_turn_back(sid, rid, myplayer)

    _dv2, ctx2 = P419._fresh_ctx(rpc, rid, fid)
    after = measure(rpc, rid, ctx2.scene, fid, ftile, ab, tgts)
    mutant = {lab: port_hits_no_shroud(ctx2.scene, fid, uid, ftile) for lab, uid in tgts.items()}

    return {"rid": rid, "caster": cid, "ally": aid, "foe": fid, "ab": ab,
            "caster_pos": layout[cid], "ally_pos": layout[aid], "foe_pos": ftile,
            "before": before, "after": after, "mutant": mutant,
            "ally_effects": [e.name for e in (ctx2.scene.effects(aid) or [])],
            "caster_effects": [e.name for e in (ctx2.scene.effects(cid) or [])]}


if __name__ == "__main__":
    raise SystemExit(main())
