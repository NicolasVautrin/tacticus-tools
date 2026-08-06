#!/usr/bin/env python
"""#211 - CursedPlagueBell (1071) : le terme de MOUVEMENT du port egale-t-il le NATIF ?

QUESTION BINAIRE : sur des pas ou le terme du playbook N'EST PAS CONSTANT, le port rend-il TUILE PAR
TUILE ce que le natif met dans son `Tile(7)` ?

`IdunBattle.AI.Playbook.Loki.CursedPlagueBellPlaybook` surcharge les DEUX faces, et chacune LIT le
voisin :
  * `GetAdjacentFriendUtility` : `HasTrait(unit, 0x7ea)` (UnitTrait.Chaos) sinon 0 -> 20 BC ;
  * `GetAdjacentEnemyUtility`  : `Any(weapons, w => w.DamageProfile == ability.GetDamageProfile()
    && w.IsMelee)` sinon 0 -> 10 BC.
Les deux gates ont un PIEGE symetrique, et c'est ce que ce probe cherche a exhiber :
  * cote AMI, le trait `Chaos` n'est PAS dans le `traits` du gameconfig : il vient du
    `GrandAllianceId` (`idun.Idun.Source.Shared.GrandAlliance$$GetTrait`) et n'existe que dans le
    `UnitConfiguration.Traits` du BattleConfiguration ;
  * cote ENNEMI, un psyker a arme Psychic de PORTEE (`Range >= 2`) vaut 0, pas 10 : le predicat
    exige AUSSI `IdunShared.Battle.WeaponProfile$$get_IsMelee`.

ETAPE 0 (offline, aucun live) : GARDE DE SUBSTRAT. Le port lit le gameconfig la ou le natif lit le
`BaseUnitComponent`/`WeaponsComponent`. On mesure l'ecart des deux sources sur `data/seed-bc.json` :
traits (alliance ajoutee) et armes (DamageProfileType x IsMelee).

ETAPE 1 (live) : CONFRONTATION PAR TUILE, par etage, sur les hooks EXISTANTS de `scorer-damage-trace`
(aucune reinjection ; armes pour un `aiStepDryRun`, desarmes en `finally`). Reutilise la machinerie de
`probe_193c_move_playbook_terms.py` mais AGREGE plusieurs pas discriminants au lieu de s'arreter au
premier, et qualifie chaque voisin par le CAS qu'il exerce.

ETAPE 2 : MUTATION ADVERSARIALE du port lui-meme. On ampute `TRIGGERED_MOVE_PLAYBOOKS` de l'entree
1071 et on recompte les desaccords sur EXACTEMENT les memes tuiles : s'ils restent a 0, la mesure ne
prouvait rien.

Usage (ASCII only) :
  python probe_211_cursed_plague_bell.py --offline-only
  python probe_211_cursed_plague_bell.py --seed 777 --board MC1_67 \
      --p-units "deathBlightbringer,..." --a-units "..."
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pin import BuildPinRefused                          # noqa: E402
from rl_collect_batch import _resolve_session, _rpc            # noqa: E402
from probe_193c_move_playbook_terms import (                   # noqa: E402
    _apply_native, _build, _by_tile, _exiger_build_des_rva, _one, _port_leaves, _visual_map,
    x_port)

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
ABILITY = 1071
CARRIER = "deathBlightbringer"
KEY_FRIEND = "CursedPlagueBell_AdjacentChaosFriend"
KEY_ENEMY = "CursedPlagueBell_AdjacentPsychicEnemy"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


# --------------------------------------------------------------------------------------------
# ETAPE 0 - garde de substrat : gameconfig (ce que le port lit) vs BattleConfiguration (ce que la
# bataille consomme, et donc ce que le natif voit dans BaseUnitComponent / WeaponsComponent).
# --------------------------------------------------------------------------------------------
def step0_substrate() -> int:
    import gameconfig as GC
    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    units = bc.get("Units") or []
    n_units = n_weapons = 0
    bad_trait = bad_weapon = 0
    alliance_seen = {}
    for u in units:
        vis = u.get("VisualId")
        g = GC.unit(vis) or {}
        n_units += 1
        # (a) Traits : le BC ajoute EXACTEMENT le trait de grande alliance (+ Hero/NPC/Summon, qui
        #     viennent de `AddUnitOperation$$AddUnitTypeTraits`, hors substrat gameconfig).
        extra = set(u.get("Traits") or ()) - set(g.get("traits") or ())
        alli = g.get("GrandAllianceId")
        if alli not in extra:
            bad_trait += 1
            if bad_trait <= 5:
                print("  TRAIT KO %-22s alliance=%-9s extra=%s" % (vis, alli, sorted(extra)))
        alliance_seen[alli] = alliance_seen.get(alli, 0) + 1
        # (b) Weapons : profil de degat ET IsMelee, arme par arme, dans l'ordre.
        gw = list(g.get("weapons") or ())
        bw = list(u.get("Weapons") or ())
        if len(gw) != len(bw):
            bad_weapon += 1
            print("  WEAPON LEN KO %-22s %d vs %d" % (vis, len(gw), len(bw)))
            continue
        for a, b in zip(gw, bw):
            n_weapons += 1
            rng = a.get("Range")
            melee = rng is None or int(rng) < 2      # WeaponProfile$$get_IsMelee
            if melee != bool(b.get("IsMelee")) or a.get("DamageProfile") != b.get("DamageProfileType"):
                bad_weapon += 1
                if bad_weapon <= 5:
                    print("  WEAPON KO %-22s gc=%s bc=(%s, melee=%s)"
                          % (vis, a, b.get("DamageProfileType"), b.get("IsMelee")))
    print("[etape0] %d unites, %d armes du seed BC" % (n_units, n_weapons))
    print("[etape0] trait d'alliance present dans BC.Traits et absent de gameconfig.traits : %s"
          % ", ".join("%s=%d" % kv for kv in sorted(alliance_seen.items(), key=lambda kv: str(kv[0]))))
    print("[etape0] traits KO=%d  armes KO=%d" % (bad_trait, bad_weapon))
    return 0 if (bad_trait == 0 and bad_weapon == 0) else 1


# --------------------------------------------------------------------------------------------
# ETAPE 1 - confrontation live, agregee sur PLUSIEURS pas discriminants.
# --------------------------------------------------------------------------------------------
def _qualify(vis: str) -> str:
    """Le CAS que ce voisin exerce, du point de vue des deux gates de CursedPlagueBell."""
    from engine.playbook.adjacent_unit_preference import _unit_weapons, _weapon_is_melee
    import gameconfig as GC
    g = GC.unit(vis) or {}
    rec = {"vis": vis, "traits": frozenset(g.get("traits") or ())}
    chaos = g.get("GrandAllianceId") == "Chaos"
    ws = _unit_weapons(rec)
    mp = any(w.get("DamageProfile") == "Psychic" and _weapon_is_melee(w) for w in ws)
    rp = any(w.get("DamageProfile") == "Psychic" and not _weapon_is_melee(w) for w in ws)
    return "%s|%s" % ("chaos" if chaos else "nonchaos",
                      "meleePsy" if mp else ("rangedPsy" if rp else "noPsy"))


def _confront(sid, rid, dv, ctx, uid, tterm, elev, leaf, cases, rows):
    """Une passe de mesure : remplit `rows` (tuile, X_nat, X_port, X_port_ampute) et `cases`."""
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    import hexgeo
    tt = _by_tile(tterm.get("entries") or [], "casterCol", "casterRow", "tileTerm")
    el = _by_tile(elev.get("entries") or [], "col", "row", "leaf")
    te = _by_tile([e for e in (leaf.get("entries") or []) if e.get("leaf") == "TileEffects"],
                  "col", "row", "value")
    tiles = [t for t in (ctx.action_tiles or []) if t in tt]
    if not tiles:
        return 0
    me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    mine = bool((me or {}).get("ctrl"))
    alive = [u for u in (dv.get("units") or [])
             if u.get("alive") and (u.get("pos") or {}).get("col") is not None
             and u.get("id") != uid]
    saved = TRIGGERED_MOVE_PLAYBOOKS.pop(ABILITY, None)          # ETAPE 2, meme tuiles
    try:
        amputated = {}
        for t in tiles:
            lv = _port_leaves(ctx, t)[0]
            amputated[t] = x_port(lv)          # foyer UNIQUE du retranchement (#254, cf. `x_port`)
    finally:
        if saved is not None:
            TRIGGERED_MOVE_PLAYBOOKS[ABILITY] = saved
    used = 0
    for t in tiles:
        vt, ve, vf = _one(tt, t), _one(el, t), _one(te, t, 0.0)
        if None in (vt, ve, vf):
            continue
        leaves, leaf_ctx = _port_leaves(ctx, t)
        p_x = x_port(leaves)                   # foyer UNIQUE du retranchement (#254, cf. `x_port`)
        term = TRIGGERED_MOVE_PLAYBOOKS[ABILITY].calculate_movement_utility_in_steps(t, leaf_ctx,
                                                                                    ctx.wt)
        nb = []
        for u in alive:
            if hexgeo.distance(t, (u["pos"]["col"], u["pos"]["row"])) != 1:
                continue
            side = "ami" if bool(u.get("ctrl")) == mine else "enn"
            q = _qualify(u.get("visualId"))
            nb.append("%s:%s" % (side, q))
            cases["%s/%s" % (side, q)] = cases.get("%s/%s" % (side, q), 0) + 1
        rows.append({"tile": t, "x_nat": vt - ve - vf, "x_port": p_x,
                     "x_amp": amputated[t], "term": term, "nb": nb})
        used += 1
    return used


def _herd(sid, rid, uid, carrier_uid):
    """DEPLACE une unite VERS le porteur au lieu de laisser l'IA la jouer.

    Doctrine « drive positions, don't blame geometry » : les deux CAS NEGATIFS de cet item (voisin
    AMI hors alliance Chaos, voisin ENNEMI a arme Psychic de PORTEE) ne s'exercent que si un tel
    voisin est adjacent a une tuile que le tier Comparable EVALUE. L'IA native, elle, disperse ses
    unites — attendre qu'elle produise la configuration, c'est mesurer sa politique, pas notre gate.
    On substitue donc, POUR CETTE UNITE SEULEMENT, un `move` vers la tuile atteignable la plus proche
    du porteur, puis un `finish`. Le tour du PORTEUR, lui, reste integralement natif : la mesure
    n'est pas touchee, seule la geometrie l'est."""
    import hexgeo
    dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 180)
    units = dv.get("units") or []
    cp = next(((u.get("pos") or {}) for u in units if u.get("id") == carrier_uid), {})
    if cp.get("col") is None:
        return False
    cpos = (cp["col"], cp["row"])
    # On vise le CONTACT que le porteur va prendre, pas sa case actuelle : les tuiles que le tier
    # Comparable evalue (les seules que les hooks exposent) sont ses tuiles d'ATTAQUE, donc celles
    # collees a l'ennemi. Viser le porteur laisse les amis un pas derriere, et aucun voisin ami
    # n'apparait jamais sur une tuile mesuree.
    foes = [(u["pos"]["col"], u["pos"]["row"]) for u in units
            if u.get("alive") and not u.get("ctrl") and (u.get("pos") or {}).get("col") is not None]
    if foes:
        cpos = min(foes, key=lambda t: hexgeo.distance(t, cpos))
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    ent = next((u for u in (mov.get("units") or []) if u.get("unitId") == uid), None)
    tiles = [(t.get("col"), t.get("row")) for t in ((ent or {}).get("tiles") or [])
             if t.get("col") is not None]
    if not tiles:
        return False
    best = min(tiles, key=lambda t: hexgeo.distance(t, cpos))
    _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": best[0], "row": best[1]}}}, 90)
    _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "finish", "unitId": uid}}, 90)
    return True


def run_live(sid, rid, seed, board, max_steps, max_arm, herd=()):
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    from engine.playbook.adjacent_unit_preference import load_playbook

    vmap = _visual_map(sid, rid)
    pb = load_playbook(ABILITY)
    if pb is None:
        print("!! ability %d absente de TRIGGERED_MOVE_PLAYBOOKS" % ABILITY)
        return 1
    rows, cases = [], {}
    carrier_uid = next((u for u, v in vmap.items() if v == CARRIER), None)
    step = armed = seen = 0
    while step < max_steps and armed < max_arm:
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            print("trajectoire native epuisee au pas %d (%s)" % (step, dry.get("error")))
            break
        uid = dry.get("activatedUnitId")
        if vmap.get(uid) in herd and uid != carrier_uid:
            ok = _herd(sid, rid, uid, carrier_uid)
            print("pas %-3d HERD %s (u%s) -> %s" % (step, vmap.get(uid), uid,
                                                    "deplace" if ok else "IMPOSSIBLE"))
            if ok:
                step += 1
                continue
        if vmap.get(uid) == CARRIER:
            seen += 1
            dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
            mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
            ctx = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv,
                                {u.get("unitId"): u for u in (mov.get("units") or [])}, uid,
                                W.load(), _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t),
                                                                 rid))
            vals = sorted({round(pb.calculate_movement_utility_in_steps(
                t, _port_leaves(ctx, t)[1], ctx.wt), 4) for t in (ctx.action_tiles or [])})
            print("pas %-3d activation #%d de %s (u%s) : terme du port sur les candidates = %s"
                  % (step, seen, CARRIER, uid, vals))
            if len(vals) > 1:
                _r(sid, "scorerDamageTraceOn", {"runnerId": rid}, 90)
                _r(sid, "scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
                try:
                    dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 90)
                    tterm = _r(sid, "scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
                    ev = _r(sid, "scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
                    lf = _r(sid, "scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
                finally:
                    _r(sid, "scorerDamageTraceOff", {"runnerId": rid}, 60)
                n = _confront(sid, rid, dv, ctx, uid, tterm, ev, lf, cases, rows)
                print("        tuiles confrontees a ce pas : %d" % n)
                if n:
                    armed += 1
        _apply_native(sid, rid, dry)
        step += 1

    if not rows:
        print("\n!! AUCUNE tuile confrontee (%d activations du porteur en %d pas)" % (seen, step))
        return 1
    print("\n  tuile      X_nat   X_port  terme  DELTA | voisins R1 qualifies")
    bad = amp_flag = 0
    for r in rows:
        d = r["x_nat"] - r["x_port"]
        if abs(d) > 1e-6:
            bad += 1
        if abs(r["x_nat"] - r["x_amp"]) > 1e-6:
            amp_flag += 1
        print("  %-10s %-7.4g %-7.4g %-6.4g %-6s| %s"
              % (r["tile"], r["x_nat"], r["x_port"], r["term"], "%.4g" % d, ", ".join(r["nb"]) or "-"))
    terms = sorted({round(r["term"], 4) for r in rows})
    print("\n[etape1] seed=%s board=%s : %d tuiles, termes distincts = %s" % (seed, board,
                                                                             len(rows), terms))
    print("[etape1] CAS de voisinage exerces : %s"
          % ", ".join("%s=%d" % kv for kv in sorted(cases.items())))
    print("[etape1] tuiles en DESACCORD X_nat vs X_port : %d / %d" % (bad, len(rows)))
    print("[etape2] MUTATION (registre ampute de 1071) : tuiles qui ROUGISSENT : %d / %d"
          % (amp_flag, len(rows)))
    ok = (bad == 0) and (len(terms) > 1) and (amp_flag > 0)
    print("[verdict] %s" % ("ACCORD, sur un regime DISCRIMINANT et une mesure QUI MORD" if ok
                            else "NON CONCLUANT (voir les 3 lignes ci-dessus)"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--max-steps", type=int, default=40)
    ap.add_argument("--max-arm", type=int, default=4)
    ap.add_argument("--p-units", default="deathBlightbringer,deathBlightlord,thousSorcerer,"
                                         "astraBullgryn,necroWarden")
    ap.add_argument("--a-units", default="bloodMephiston,astraPrimarisPsy,thousAhriman,"
                                         "tauMarksman,orksNob")
    # Le regime discriminant se CHERCHE : gonfler les PV (`--hp-target/--hp-player`) allonge la
    # bataille, donc le nombre d'activations du porteur ET le nombre de tuiles que le tier
    # Comparable evalue (les hooks ne voient QUE celles-la).
    ap.add_argument("--herd", default="", help="visualIds (virgule) a DEPLACER vers le porteur "
                                              "au lieu de laisser l'IA les jouer")
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    a = ap.parse_args()
    herd = frozenset(x for x in (a.herd or "").split(",") if x)
    rc0 = step0_substrate()
    if a.offline_only:
        return rc0
    try:
        _exiger_build_des_rva()            # #431 : le pin des RVA du hook passe par `build_pin`
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    sid = _resolve_session()
    if a.runner is not None:
        return run_live(sid, a.runner, a.seed, a.board, a.max_steps, a.max_arm, herd) or rc0
    rid, state = _build(a.seed, a.board,
                        ["--p-units", a.p_units, "--a-units", a.a_units] + list(a.extra or []))
    if rid is None:
        return 1
    print("runner %d seed=%s board=%s carrier=%s" % (rid, a.seed, a.board, CARRIER))
    try:
        return run_live(sid, rid, a.seed, a.board, a.max_steps, a.max_arm, herd) or rc0
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        try:
            state.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
