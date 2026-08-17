#!/usr/bin/env python
"""Probe #67b -- ORDRE `part bouclier` x `limites de degat` sur la voie ABILITY (residu case-67 SS5).

ARTEFACT NATIF confronte : `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`
(famille ABILITY = `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` ->
`IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`) :

    dmg        = Math.Max(param_2, 0)
    shieldPart = Math.Min(dmg, UnitExtensions.GetShield(cible))            # `iVar20`
    v          = CalculateBaseDamageWithAllModifiers(dmg - shieldPart)     # `iVar17 - iVar20`
    v          = Fix64.Max(v, 0)
    v          = ApplyTraitDamageLimitsToDamage(2, &v, &v, ...)            # cap sur le RESTE
    return       (int)(Fix64(shieldPart) + v)

=> la part absorbee par le BOUCLIER echappe aux caps (member-cap / Resilient / cap boss). Le port
capait AVANT le split (= ordre de la famille ATTACK, ou les limites capent les cellules en amont de
`IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`). Identique tant que shield == 0.

MONTAGE (confrontabilite, cf. case-67b) :
  - cible   : `astraYarrick` -- HERO du pool, trait `Resilient`, aucune mecanique de reduction de
              degat recu (kit offensif seul) ; `--hp-target` la met a `HP` PV, armure 0.
  - bouclier: `thousSorcerer` (Thaumachus, HERO du pool) -- passive `ArcaneShield` : APRES SON MOVE
              il pose un bouclier `shieldHp` sur l'ami le plus proche a <= 2 hex. Le move d'une unite
              ENNEMIE est accepte par `applyAction` hors de son tour (case-67 SS2.5) -> pose A LA DEMANDE,
              sans `endturn` intercalaire (donc sans decay `RemoveOneTurnOnShields`).
  - attaque : `tyranNeurothrope` / `SpiritLeech` (1104) -- famille ABILITY (`native_factory="ability"`,
              XREF `SpiritLeechAbility$$ExecuteBehaviour` -> `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`),
              RANGED range 3, `nrOfHits`=1, profil `Psychic` (PiercingRatio 100, `NoBlocking` -> aucun
              tirage de block, aucune armure residuelle : le coup isole l'etage conteste).

REGIMES (le cap Resilient exige `hp-1 < dmg` ET PAS d'overkill, i.e. `dmg < 2 x hp`) :
  - `--case none`  : aucun bouclier            -> NON-REGRESSION (doit rester bit-exact, comme #67) ;
  - `--case big`   : bouclier >= degat du coup -> le natif consomme `dmg` de bouclier, l'ancien port
                     n'en consommait que `cap` (= hp-1). Discriminant sur le BOUCLIER RESTANT ;
  - `--case small` : bouclier < degat du coup  -> le natif cape le RESTE (cible a 1 PV), l'ancien port
                     capait le TOTAL puis en donnait une part au bouclier (cible a `shield+1` PV).
                     Discriminant sur les PV. Le bouclier est erode au prealable par les attaques
                     NORMALES des co-equipiers (meme tour -> pas de decay).

Usage :
    python probe_67b_shield_ability_limits.py --case big   [--seed 6741] [--hp 1500]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rl_collect_batch as R                                        # noqa: E402
from engine.runner.snapshot import load_state                       # noqa: E402
from engine.runner.runner import Runner                             # noqa: E402
from engine.runner.messages import ActiveAbilityMessage             # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister              # noqa: E402
from engine.runner.components import HealthComponent, ShieldComponent, PositionComponent  # noqa: E402

CASTER_VIS = "tyranNeurothrope"     # SpiritLeech 1104, famille ABILITY, ranged r3, 1 coup, Psychic
# Cible : HERO du pool, trait `Resilient`, AUCUNE reduction du degat RECU (ContagionsOfNurgle est une
# aura qui rogne l'armure des ENNEMIS, pas la sienne ; le profil Psychic perce 100 % de toute facon).
# CHAOS obligatoire : mesure du 2026-07-26 -- avec `astraYarrick` (Imperial) a 1 hex, ArcaneShield
# pose le bouclier sur SOI, jamais sur l'allie non-Chaos (le tooltip « then other friendly units »
# n'est pas ce que fait le natif ; ecart port/natif documente en residu, hors perimetre #67b).
TARGET_VIS = "deathRotbone"
WARD_VIS = "thousSorcerer"          # ArcaneShield : pose un bouclier sur l'ami <= 2 hex apres son move
# EROSION du bouclier (case `small`) : `darkaAzrael` / `DarkTalonStrike` (1092) -- HERO du pool,
# ability RANGED (range 2) dont le coup PRINCIPAL vaut ~4000-4900, soit assez pour ramener le bouclier
# ArcaneShield (5483) sous le degat de `SpiritLeech` (~2000-3000) EN UN SEUL CAST, DANS LE MEME TOUR
# (une unite distincte -> le tour ne se clot pas -> ni decay ni re-pose du bouclier entre les deux).
ERODER_VIS = ["darkaAzrael"]
ERODER_ABILITY = 1092
ERODER_RANGE = 2
# Unite qui n'agit JAMAIS : tant qu'elle a son action, le cast ne CLOT pas mon tour -> aucun
# `EndTurnOperation$$RemoveOneTurnOnShields` derriere le coup, donc le bouclier restant reste LISIBLE
# (sans elle, le bouclier `remaining=1` expire dans la foulee et le live rend 0, cf. run 366).
FILLER_VIS = "eldarRanger"
ABILITY = 1104
ARCANE_RANGE = 2                    # `ArcaneShield.constants.range`

SID = R._resolve_session()


def rpc(method, body=None, timeout=90):
    r = R._rpc(SID, method, [body] if body is not None else [], timeout=timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def ok(r):
    return isinstance(r, dict) and r.get("ok")


def shields(rid):
    """{entityId: total bouclier} lu du `combatSnapshot` (source du ShieldComponent offline)."""
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    out = {}
    for u in (snap.get("units") or []):
        out[u.get("entityId")] = sum(int(s.get("amount") or 0) for s in (u.get("shields") or []))
    return out, snap


def bfs(board, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def unit_of(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def tile_of(board, u):
    p = (u or {}).get("pos") or {}
    return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None


def movement_of(rid, uid):
    """Stat `Movement` de l'unite — `decisionView` ne le porte pas, `combatSnapshot.stats.movement` si."""
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    for u in (snap.get("units") or []):
        if u.get("entityId") == uid:
            return max(1, int((u.get("stats") or {}).get("movement") or 2))
    return 2


def reachable_tiles(rid, board, dec, mover):
    """Tuiles atteignables par `mover`. `aiMovableTiles` ne rend RIEN pour une unite dont ce n'est pas
    le tour (mesure : `side=enemy` -> 0 tuiles) alors que `applyAction move` l'accepte quand meme
    (case-67 SS2.5) -> pour un ENNEMI on calcule le disque de mouvement soi-meme (BFS borne par son
    `movement`, tuiles walkable, destinations libres). Renvoie {tileId: (col,row)}."""
    if mover.get("mine"):
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == mover["id"]), None)
        return {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                for t in ((cmt or {}).get("tiles") or [])}
    src = tile_of(board, mover)
    mv = movement_of(rid, mover["id"])
    occupied = {tile_of(board, u) for u in (dec.get("units") or []) if u.get("alive")}
    dist, q, out = {src: 0}, deque([src]), {}
    while q:
        x = q.popleft()
        if dist[x] >= mv:
            continue
        for n in board.neighbours(x):
            if n in dist or not board.walkable(n):
                continue
            dist[n] = dist[x] + 1
            q.append(n)
            if n not in occupied:
                out[n] = board.coord(n)
    return out


def move_toward(rid, board, mover, dest_tile, max_dist=0, dec=None):
    """Deplace `mover` (ami OU ennemi) le plus pres possible de `dest_tile`. Renvoie True si un move
    a ete applique. `max_dist` = distance visee (on s'arrete des qu'elle est atteinte)."""
    src = tile_of(board, mover)
    if src is None or dest_tile is None:
        return False
    d = bfs(board, dest_tile)
    if d.get(src, 99) <= max_dist:
        return False
    reach = reachable_tiles(rid, board, dec or {}, mover)
    pool = [t for t in reach if t in d]
    if not pool:
        return False
    best = min(pool, key=lambda t: d[t])
    if d[best] >= d.get(src, 99):
        return False
    col, row = reach[best]
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": mover["id"], "to": {"col": col, "row": row}}}, 60)
    return ok(res)


def nudge_ward(rid, board, dec, ward, tgt_tile, radius=ARCANE_RANGE):
    """Fait BOUGER le ward (unite ENNEMIE) vers une tuile DIFFERENTE encore a <= `radius` de la cible.
    C'est le move lui-meme qui declenche `ArcaneShieldAbility$$CreateTrigger` (« After moving,
    Thaumachus applies a Shield to the closest friendly unit within 2 hexes ») : rester sur place ne
    pose rien. Priorise la tuile la plus PROCHE de la cible parmi celles qui restent dans le rayon."""
    src = tile_of(board, ward)
    d = bfs(board, tgt_tile)
    reach = reachable_tiles(rid, board, dec, ward)
    pool = [t for t in reach if t != src and d.get(t, 99) <= radius]
    if not pool:                                   # sinon : au moins se rapprocher
        pool = [t for t in reach if t != src and d.get(t, 99) < d.get(src, 99)]
    if not pool:
        return False
    best = min(pool, key=lambda t: d.get(t, 99))
    col, row = reach[best]
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": ward["id"], "to": {"col": col, "row": row}}}, 60)
    return ok(res)


def seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def live_hits(res, tid, ability):
    """Montants per-coup emis LIVE pour la cible (events step-4 `Amount`)."""
    a0 = (res.get("actions") or [{}])[0]
    out, dc, db, de = [], False, False, False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == ability:
            out.append(td.get("Amount"))
            dc = dc or bool(td.get("Attack_DidCrit"))
            db = db or bool(td.get("Attack_DidBlock"))
            de = de or bool(td.get("Attack_DidEvade"))
    return out, (dc, db, de), a0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=["none", "big", "small"], default="big")
    ap.add_argument("--seed", default="6741")
    ap.add_argument("--hp", type=int, default=1500)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    from engine.entities.pathfinding.board import Board
    import subprocess
    state_file = a.state_file or str(Path(__file__).resolve().parents[2] /
                                     "logs" / f"st67b_{a.case}.json")
    p_units = [CASTER_VIS, FILLER_VIS] + (ERODER_VIS if a.case == "small" else [])
    # `none` = AUCUN ward dans la bataille : ArcaneShield se declenche aussi « at the end of his turn »
    # si Thaumachus ne bouge pas -> le garder en jeu rendrait le regime shield==0 inatteignable.
    a_units = [TARGET_VIS] if a.case == "none" else [WARD_VIS, TARGET_VIS]
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
            "--board", a.board, "--roster", "1",
            "--p-units", ",".join(p_units),
            "--a-units", ",".join(a_units),
            "--hp-target", str(a.hp), "--state-file", state_file]
    pr = subprocess.run(argv, cwd=str(Path(__file__).resolve().parent),
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        print("[error] build KO:", (pr.stderr or pr.stdout)[-500:])
        return 2
    rid = json.loads(Path(state_file).read_text())["runnerId"]
    print(f"[build] runner={rid} case={a.case} hp-target={a.hp}")

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")

    # --- 1) POSITIONNEMENT : amener la cible a portee 3 du caster (moves des DEUX camps) --------
    caster = tgt = ward = None
    my_player = None
    reached = False
    for _turn in range(40):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        if not ok(dec):
            print("[error] decisionView KO")
            return 2
        caster, tgt, ward = (unit_of(dec, CASTER_VIS), unit_of(dec, TARGET_VIS),
                             unit_of(dec, WARD_VIS))
        if caster is None or tgt is None or (ward is None and a.case != "none"):
            print(f"[error] unite manquante caster={bool(caster)} tgt={bool(tgt)} ward={bool(ward)}")
            return 2
        if my_player is None:
            my_player = caster.get("owner")
        for u in (caster, tgt, ward):
            if u is not None:
                u["mine"] = (u.get("owner") == my_player)
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        ct, tt = tile_of(board, caster), tile_of(board, tgt)
        if bfs(board, tt).get(ct, 99) <= 3:
            reached = True
            break
        # Seul MON caster avance : deplacer la cible la SEPARERAIT du ward (spawn adjacent), et
        # ArcaneShield exige <= 2 hex. Chaque `endturn` fait de toute facon poser le bouclier par le
        # ward (« If Thaumachus does not move, this ability triggers at the end of his turn »).
        moved = move_toward(rid, board, caster, tt, max_dist=3, dec=dec)
        for _v in (ERODER_VIS if a.case == "small" else []):   # erodeurs amenes a portee AUSSI
            _e = unit_of(dec, _v)
            if _e is not None:
                _e["mine"] = True
                moved |= move_toward(rid, board, _e, tt, max_dist=ERODER_RANGE, dec=dec)
        if not moved:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    if not reached:
        print("[error] caster/cible jamais a portee 3")
        return 2
    print(f"[pos] caster u{caster['id']} @ {tile_of(board, caster)} | "
          f"cible u{tgt['id']} @ {tile_of(board, tgt)} | "
          f"ward {('u%d @ %s' % (ward['id'], tile_of(board, ward))) if ward else '-'}")

    # --- 2) BOUCLIER : amener le ward a <= 2 hex de la cible, son MOVE declenche ArcaneShield ----
    if a.case != "none":
        for _try in range(40):
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
            caster, tgt, ward = (unit_of(dec, CASTER_VIS), unit_of(dec, TARGET_VIS),
                                 unit_of(dec, WARD_VIS))
            for u in (caster, tgt, ward):
                if u is not None:
                    u["mine"] = (u.get("owner") == my_player)
            if dec.get("currentPlayer") != my_player:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
                continue
            sh, _ = shields(rid)
            if int(sh.get(tgt["id"]) or 0) > 0:
                break
            if not nudge_ward(rid, board, dec, ward, tile_of(board, tgt)):
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        sh, _ = shields(rid)
        print(f"[shield] cible u{tgt['id']} bouclier={sh.get(tgt['id'])}")
        if not int(sh.get(tgt["id"]) or 0):
            print("[error] ArcaneShield n'a pas pose de bouclier sur la cible")
            return 2

    # --- 3) EROSION (case `small`) : attaques NORMALES des co-equipiers, MEME tour (pas de decay)
    if a.case == "small":
        # Fenetre visee : 0 < bouclier <= SMALL_MAX, avec SMALL_MAX < minDmg du coup -> le bouclier NE
        # PEUT PAS absorber tout le coup, donc le RESTE post-bouclier existe ET depasse `hp-1` (le cap
        # mord). Erosion UNE attaque a la fois (une salve complete vide le bouclier d'un coup) ; si on
        # tombe a 0, deux `endturn` laissent ArcaneShield le reposer (fin de tour du ward) et on
        # recommence avec des actions fraiches.
        SMALL_MAX = 1900        # < minDmg live de SpiritLeech (~1950) -> le bouclier ne peut tout absorber
        for _e in range(24):
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
            if dec.get("currentPlayer") != my_player:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
                continue
            tgt = unit_of(dec, TARGET_VIS)
            if tgt is None:
                print("[error] cible disparue pendant l'erosion")
                rpc("disposeRunner", {"runnerId": rid}, 20)
                return 2
            sh, _ = shields(rid)
            cur = int(sh.get(tgt["id"]) or 0)
            print(f"   [erode] bouclier={cur}")
            if 0 < cur <= SMALL_MAX:
                break
            if cur == 0:                            # attendre la re-pose (EndTurn du ward)
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
                continue
            fired = False
            for vis in ERODER_VIS:
                eu = unit_of(dec, vis)
                if eu is None:
                    print(f"      [erode] {vis} ABSENT du build")
                    continue
                if not eu.get("hasAction"):
                    continue
                eu["mine"] = True
                move_toward(rid, board, eu, tile_of(board, tgt), max_dist=ERODER_RANGE, dec=dec)
                r2 = rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "ability", "casterId": eu["id"], "targetId": tgt["id"],
                    "abilityType": ERODER_ABILITY}}, 60)
                a2 = (r2.get("actions") or [{}])[0]
                if ok(r2) and a2.get("mutated"):
                    fired = True
                    break                            # UN cast, puis on relit le bouclier
                print(f"      [erode] {vis} cast KO ok={a2.get('ok')} "
                      f"mutated={a2.get('mutated')} err={str(a2.get('error'))[:80]}")
            if not fired:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        sh, _ = shields(rid)
        print(f"[shield] apres erosion = {sh.get(tgt['id'])}")
        if not (0 < int(sh.get(tgt["id"]) or 0) <= SMALL_MAX):
            print("[error] fenetre `small` non atteinte (bouclier hors ]0, %d])" % SMALL_MAX)
            rpc("disposeRunner", {"runnerId": rid}, 20)
            return 2

    # --- 4) CAPTURE + CAST ----------------------------------------------------------------------
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    if dec.get("currentPlayer") != my_player:
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    caster, tgt = unit_of(dec, CASTER_VIS), unit_of(dec, TARGET_VIS)
    att, tid = caster["id"], tgt["id"]
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    sh_before, snap = shields(rid)
    state = load_state(dec, ob, snap)
    te = state.get_entity(tid)
    thc = te.get_component(HealthComponent) if te is not None else None
    shc = te.get_component(ShieldComponent) if te is not None else None
    off_shield_before = shc.get_total_shield() if shc is not None else 0
    if thc is None or thc.hp is None:
        print("[error] cible introuvable offline")
        return 2
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not ok(s0):
        print("[error] dumpRng KO")
        return 2
    state.rng = seed_rng(s0)
    hp_before = int(thc.hp)
    print(f"[pre ] hp cible={hp_before} bouclier live={sh_before.get(tid)} offline={off_shield_before}")

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": ABILITY}}, 60)
    lph, (dc, db, de), a0 = live_hits(res, tid, ABILITY)
    if not (ok(res) and a0.get("ok")):
        print(f"[error] cast KO: {str(res)[:300]}")
        return 2
    if not lph:
        print(f"[error] aucun event de degat live: {str(a0)[:300]}")
        return 2
    live_hp = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid), None)
    sh_after, _ = shields(rid)

    # --- 5) REPLAY OFFLINE ----------------------------------------------------------------------
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=att, target_id=tid, ability_type=ABILITY))
    _last = runner.ability_handler.last or {}
    atk = _last.get("main_attack") or _last.get("attack")
    if atk is None:
        print(f"[error] pas d'attaque offline: {runner.ability_handler.last}")
        return 2
    off_hp = state.get_entity(tid).get_component(HealthComponent).hp
    shc2 = state.get_entity(tid).get_component(ShieldComponent)
    off_shield_after = shc2.get_total_shield() if shc2 is not None else 0

    # --- 5bis) CONTROLE « ANCIEN ORDRE » : rejoue le MEME etat en forcant la famille ATTACK, dont
    # l'ordre est cap-sur-le-TOTAL-puis-split (= ce que faisait le port avant #67b). Sert a PROUVER
    # que le montage est discriminant : si legacy == live, le scenario ne teste rien.
    # (Le forcage rallume aussi le resolve slot-8 -> 1 tirage de plus APRES le coup : sans effet sur
    #  le per-coup mesure ici, l'ability n'ayant qu'UN coup.)
    from engine.runner.operations.damage import AttackDamageOperation as _ADO
    state_l = load_state(dec, ob, snap)
    state_l.rng = seed_rng(s0)
    _orig = _ADO._run_hits
    try:
        _ADO._run_hits = staticmethod(
            lambda *ar, **kw: _orig(*ar, **{**kw, "is_attack_damage_op": True}))
        Runner(state_l).install_default_handlers(20).apply(
            ActiveAbilityMessage(caster_id=att, target_id=tid, ability_type=ABILITY))
    finally:
        _ADO._run_hits = _orig
    te_l = state_l.get_entity(tid)
    shc_l = te_l.get_component(ShieldComponent)
    legacy = {"hp": te_l.get_component(HealthComponent).hp,
              "shield": shc_l.get_total_shield() if shc_l is not None else 0}

    print()
    print(f"[case {a.case}] crit/block/evade live = {dc}/{db}/{de}")
    print(f"  per-coup   live={lph}   offline={atk['per_hit']}")
    print(f"  PV cible   live={live_hp}   offline={off_hp}   (avant={hp_before})")
    print(f"  bouclier   live={sh_before.get(tid)} -> {sh_after.get(tid)}   "
          f"offline={off_shield_before} -> {off_shield_after}")
    print(f"  CONTROLE ancien ordre (cap AVANT le split) : PV={legacy['hp']} bouclier={legacy['shield']}")
    verdict = []
    if atk["per_hit"] != lph:
        verdict.append(f"PER-COUP MISMATCH off={atk['per_hit']} live={lph}")
    if live_hp is not None and off_hp != live_hp:
        verdict.append(f"PV MISMATCH off={off_hp} live={live_hp}")
    if off_shield_after != int(sh_after.get(tid) or 0):
        verdict.append(f"BOUCLIER MISMATCH off={off_shield_after} live={sh_after.get(tid)}")
    if a.case != "none" and (legacy["hp"], legacy["shield"]) == (off_hp, off_shield_after):
        verdict.append("SCENARIO NON DISCRIMINANT (ancien ordre == nouveau)")
    print("VERDICT:", "OK" if not verdict else " | ".join(verdict))
    if not a.keep:
        rpc("disposeRunner", {"runnerId": rid}, 20)
    return 0 if not verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
