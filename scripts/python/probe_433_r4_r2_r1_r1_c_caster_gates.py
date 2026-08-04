"""probe #433-r4-r2-r1-r1-c -- les TROIS gates CASTER, en AMONT du calcul de zone.

LA CHAINE, LUE (`IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange`, surcharge a
QUATRE arguments) : avant meme d'appeler les slots 9/10 de l'`IActiveAbility`, le natif annule
l'ability -- l'ensemble rendu est VIDE -- si l'un de ces trois gates mord, DANS CET ORDRE :

    1. !impl.<IActiveAbility slot 0x14>(unit, ability.<AmountOfTimesAlreadyUsed @+0x10>)
       = `IdunBattle.Entities.Abilities.AActiveAbility$$CanStillBeUsed`
    2.  impl.<IActiveAbility slot 0x13>(unit)
       = `IdunBattle.Entities.Abilities.AActiveAbility$$IsDisabled`
    3.  `IdunBattle.Core.Services.AttackQuery$$GetInvalidCasterReason(unit, position, type)`
        .IsInvalid()  -- dont la marche (d) lit
        `IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed`

Le port mirror vit dans `engine.services.ability_caster_gates` ; le consommateur est
`engine.services.ability_range.is_tile_in_range_of_any_ability`.

LE DISCRIMINANT, ENONCE AVANT LA MESURE. Il faut un bras ou l'ability est REELLEMENT bloquee et un
TEMOIN ou elle ne l'est pas -- sans le second, un port qui refuse TOUT passerait aussi. Le kit
`darkaTerminator` les porte tous les deux, sur la MEME unite, la MEME tuile et le MEME sweep :

    arme = MELEE (Range 1)   |   `PlasmaCannon` (1150) = zone 3, `initialCooldownTurns = 1`

  * bras BLOQUE  (les 2 premiers tours : `cooldown = 1`) -> le natif doit rendre « en portee »
    pour `d <= 1` SEULEMENT (il ne reste que l'attaque normale) ;
  * bras TEMOIN  (`cooldown = null`)                      -> jusqu'a `d = 3` (la zone de 1150).

Les trois ports possibles se separent donc TOUS les trois :
    port CORRECT        -> 1 puis 3
    port QUI NE GATE PAS-> 3 puis 3   (echoue sur le bras bloque : 12 faux positifs mesures)
    port QUI GATE TOUT  -> 1 puis 1   (echoue sur le TEMOIN)
et le regime n'est pas DEGENERE : `zone == portee d'arme` est FAUX sur ce kit (3 != 1), donc
l'accord du bras temoin ne peut pas venir d'une coincidence de modeles.

CE QUE LE PROBE MESURE :

  * `--step inventaire` : OFFLINE. Le gisement de chaque gate sur le catalogue gameconfig -- pour
    dire ce que chacun COUTE et ce qu'il ne coute pas, au lieu de l'affirmer.
  * `--step arms` : LIVE. Les deux bras ci-dessus, natif contre port, ventiles PAR DISTANCE (une
    comparaison globale ne separerait pas un rayon 1 d'un rayon 3 sur un sweep dont la plupart des
    positions sont hors des deux).

Usage (ASCII only, depuis scripts/python) :
  python probe_433_r4_r2_r1_r1_c_caster_gates.py --step inventaire
  python probe_433_r4_r2_r1_r1_c_caster_gates.py --step arms
  python probe_433_r4_r2_r1_r1_c_caster_gates.py --step all
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                     # noqa: E402
from rl_collect_batch import _resolve_session, _rpc               # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

CASTER = "tauCrisis"          # HERO du pool ; seul porteur `lineup` de 1077 EarlyWarningOverride
ENEMY = "darkaTerminator"     # arme de MELEE + PlasmaCannon zone 3, initialCooldownTurns = 1
GATED_ABILITY = 1150          # ActiveAbilityType.PlasmaCannon
ABILITY = 1077                # ActiveAbilityType.EarlyWarningOverride
BOARD = "MC1_67"
SEED = "777"
SEP = 5                       # hexdist caster <-> ennemi : NON adjacent (branche A) et < 9 (gate)


def _r(sid, m, b, t=180):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


# ------------------------------------------------------------------------------------------------
# --step inventaire : le GISEMENT de chaque gate, sur le catalogue gameconfig
# ------------------------------------------------------------------------------------------------
def step_inventaire() -> int:
    import gameconfig as GC
    from engine.services import ability_caster_gates as acg
    from engine.services import ability_range as ar
    from engine.runner.abilities.targeting import unit_weapon_range

    ids = GC.all_unit_ids()
    units = [u for k in ("lineup", "npc", "summons") for u in (ids.get(k) or [])]
    actives: dict = {}
    for uid in units:
        for name in ((GC.unit(uid) or {}).get("activeAbilities") or []):
            actives.setdefault(name, []).append(uid)
    n_dis = n_ct = n_icd = 0
    disabled = []
    for name in actives:
        aid = GC.ability_id(name)
        if aid is None:
            continue
        if acg.is_disabled(aid):
            n_dis += 1
            disabled.append(name)
        if acg.try_get_number_constant(aid, acg.CONST_COOLDOWN_TURNS) is not None:
            n_ct += 1
        if acg.try_get_number_constant(aid, acg.CONST_INITIAL_COOLDOWN) is not None:
            n_icd += 1
    print("abilities ACTIVES distinctes du gameconfig : %d" % len(actives))
    print("  gate 2 `AActiveAbility$$IsDisabled` (nrOfTargets < 1, sinon nrOfHits < 1) : %d"
          % n_dis)
    if disabled:
        print("     -> %s" % ", ".join(sorted(disabled)))
    print("  avec `cooldownTurns`        (gate 1, borne le `amountUsed == 0`) : %d" % n_ct)
    print("  avec `initialCooldownTurns` (gate 3d, arme des le tour 1)        : %d" % n_icd)
    print("")
    print("KITS ou un gate CHANGE la zone (portee d'ability > portee d'arme) :")
    n = 0
    for uid in (ids.get("lineup") or []):
        w = unit_weapon_range(uid, None)
        w = 0 if w is None else int(w)
        for name in ((GC.unit(uid) or {}).get("activeAbilities") or []):
            aid = GC.ability_id(name)
            if aid is None:
                continue
            rng = ar.ability_range_value(aid, uid)
            if rng is None or rng <= w or rng >= ar.WHOLE_BOARD_REACH:
                continue
            icd = acg.try_get_number_constant(aid, acg.CONST_INITIAL_COOLDOWN)
            n += 1
            print("  %-22s %-30s id=%-5d arme=%d zone=%d  initialCooldownTurns=%s"
                  % (uid, name, aid, w, rng, icd))
    print("  total : %d" % n)
    return 0


# ------------------------------------------------------------------------------------------------
# --step arms : les DEUX bras, natif contre port
# ------------------------------------------------------------------------------------------------
def _build():
    state = ROOT / "logs" / "runners" / ("p433r1r1c-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
            "--state-file", str(state), "--p-units", CASTER, "--a-units", ENEMY,
            "--hp-target", "90000", "--hp-player", "90000",
            "--unit-stat", "%s:Movement=6" % CASTER]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-1200:]
    return json.loads(state.read_text())["runnerId"], None


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 180)


def _row(dv, visual):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == visual), None)


def _partition(sid, rid, caster_id, Y):
    """`{P : en portee}` / `{P : hors portee}` -- le bonus de branche A vaut `util + 10*d(P,E)`,
    donc `0` = `IsTileInRangeOfAnyAbility` VRAI et `50` = FAUX.

    VERROU DE MONTAGE (herite de `probe_433_r4_r2_r1_ability_range._nc_partition`) : la partition
    n'est ATTRIBUABLE qu'a UN SEUL ennemi vivant -- chacun verse son propre `+50/0` ET son propre
    `-10*d`, donc a deux ennemis un bonus de 50 ne dit plus LEQUEL est hors portee."""
    nat = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": caster_id, "abilityType": ABILITY,
                                 "sweep": True}, 180)
    inr, outr = set(), set()
    for p in (nat.get("positions") or []):
        if p.get("util") is None:
            continue
        P = tuple(p["pos"])
        b = round(p["util"] + 10 * hexgeo.distance(P, Y), 6)
        (inr if b == 0 else outr).add(P)
    return inr, outr


def _confront(tag, Y, inr, outr, vid, state_map, na_id, elev, expect_max):
    """Le port contre la partition, VENTILE PAR DISTANCE. Rend `(fp, fn, reach)`."""
    from engine.services import ability_range as ar
    reach = ar.unit_threat_reach(vid, None, state_map, na_id)
    sweep = sorted(inr | outr)
    modeled = {P for P in sweep
               if ar.is_tile_in_range_of_any_ability(Y, P, vid, elev_by_pos=elev,
                                                     ability_state=state_map,
                                                     normal_attack_id=na_id)}
    byd: dict = {}
    for P in sweep:
        byd.setdefault(hexgeo.distance(P, Y), []).append((P in inr, P in modeled))
    print("[%s] port reach=%d (attendu %s)  sweep n=%d" % (tag, reach, expect_max, len(sweep)))
    for d in sorted(byd):
        v = byd[d]
        print("   d=%-2d natif in=%d/%-2d   port in=%d/%-2d"
              % (d, sum(1 for a, _ in v if a), len(v), sum(1 for _, b in v if b), len(v)))
    fp = sorted(modeled - inr)
    fn = sorted(inr - modeled)
    print("   FP=%d FN=%d -> %s" % (len(fp), len(fn), "EXACT" if not fp and not fn else "DIVERGE"))
    if fp:
        print("   faux positifs : %r" % (fp[:12],))
        # ATTRIBUER plutot que supposer : on imprime l'elevation des tuiles REFUSEES et celle des
        # ACCEPTEES a la MEME distance. C'est le discriminant du residu `#433-r4-r2-r1-r2` (le
        # 2e predicat de `GetPossibleTargetsForOptions`, `b__1`, retire les tuiles obscurcies).
        print("   Y=%r elev=%s" % (Y, elev.get(Y)))
        for P in fp[:8]:
            d = hexgeo.distance(P, Y)
            same = sorted(q for q in inr if hexgeo.distance(q, Y) == d)
            print("      FP %r d=%d elev=%s | acceptees a d=%d : %r"
                  % (P, d, elev.get(P), d, [(q, elev.get(q)) for q in same[:6]]))
    if fn:
        print("   faux negatifs : %r" % (fn[:12],))
    return fp, fn, reach


def step_arms(verbose=True) -> dict:
    from engine.services import ability_caster_gates as acg

    sid = _resolve_session()
    if not sid:
        return {"error": "aucune session Frida"}
    rid, err = _build()
    if rid is None:
        return {"error": "build KO : %s" % err}
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
        tiles = bg.get("tiles") or []
        pos_of = {t["id"]: (t["col"], t["row"]) for t in tiles}
        elev = {pos_of[t["id"]]: t.get("elevation") for t in tiles}
        walk = {pos_of[t["id"]]: bool(t.get("walkable")) for t in tiles}
        dv = _dv(sid, rid)
        c, e = _row(dv, CASTER), _row(dv, ENEMY)
        if c is None or e is None:
            return {"error": "caster/ennemi absent de decisionView"}
        alive = [u for u in (dv.get("units") or [])
                 if u.get("pos") and u.get("alive") and not u.get("ctrl")]
        if len(alive) != 1:
            return {"error": "montage IMPUR : %d ennemis vivants (partition non attribuable)"
                             % len(alive)}
        O = (c["pos"]["col"], c["pos"]["row"])
        Y = next((q for q in sorted(walk)
                  if walk[q] and elev.get(q) is not None and hexgeo.distance(O, q) == SEP), None)
        if Y is None:
            return {"error": "aucune tuile walkable a hexdist %d de %r" % (SEP, O)}
        # On deplace SEULEMENT l'ennemi : le caster garde son set de move FRAIS (un `move` pose
        # le drapeau `Moved`, ce qui viderait le sweep et couterait 2 endturn -- exactement le
        # budget qui epuise l'`initialCooldownTurns` qu'on veut mesurer).
        _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": e["id"], "to": {"col": Y[0], "row": Y[1]}}}, 90)

        out = {"O": O, "Y": Y, "enemy_visual": ENEMY, "arms": {}}
        elev_ok = {p: v for p, v in elev.items() if v is not None}

        # --- bras BLOQUE : `initialCooldownTurns` encore en cours -------------------------------
        dv = _dv(sid, rid)
        e = _row(dv, ENEMY)
        st = acg.ability_state_map(e)
        na = acg.normal_attack_id(e)
        blocked = st.get(GATED_ABILITY) or {}
        if acg.can_currently_be_used(blocked) is not False:
            return {"error": "bras BLOQUE non arme : etat 1150 = %r (le gate ne mord pas)"
                             % (blocked,)}
        inr, outr = _partition(sid, rid, c["id"], Y)
        if not inr and not outr:
            return {"error": "sweep VIDE sur le bras bloque (caster sans set de move ?)"}
        if verbose:
            print("[arms] O=%r Y=%r hexdist=%d -> branche A pure" % (O, Y, hexgeo.distance(O, Y)))
            print("[arms] etat 1150 BLOQUE = %r"
                  % ({k: blocked.get(k) for k in ("usable", "cooldown", "disabled")},))
        fp, fn, reach = _confront("BLOQUE", Y, inr, outr, ENEMY, st, na, elev_ok, 1)
        out["arms"]["bloque"] = {"fp": fp, "fn": fn, "reach": reach, "state": st, "na": na,
                                 "in_range": sorted(inr), "sweep": sorted(inr | outr),
                                 "natif_dmax": max((hexgeo.distance(P, Y) for P in inr),
                                                   default=None)}

        # --- bras TEMOIN : cooldown eteint, meme unite, meme tuile ------------------------------
        for _ in range(6):
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            dv = _dv(sid, rid)
            e2, c2 = _row(dv, ENEMY), _row(dv, CASTER)
            st2 = acg.ability_state_map(e2)
            if acg.can_currently_be_used(st2.get(GATED_ABILITY) or {}) and c2.get("ctrl"):
                break
        else:
            return {"error": "bras TEMOIN jamais atteint (cooldown toujours arme)"}
        Y2 = (e2["pos"]["col"], e2["pos"]["row"])
        na2 = acg.normal_attack_id(e2)
        if Y2 != Y:
            return {"error": "l'ennemi a bouge entre les deux bras : %r -> %r" % (Y, Y2)}
        inr2, outr2 = _partition(sid, rid, c2["id"], Y)
        if verbose:
            print("[arms] etat 1150 TEMOIN = %r"
                  % ({k: (st2.get(GATED_ABILITY) or {}).get(k)
                      for k in ("usable", "cooldown", "disabled")},))
        fp2, fn2, reach2 = _confront("TEMOIN", Y, inr2, outr2, ENEMY, st2, na2, elev_ok, 3)
        out["arms"]["temoin"] = {"fp": fp2, "fn": fn2, "reach": reach2, "state": st2, "na": na2,
                                 "in_range": sorted(inr2), "sweep": sorted(inr2 | outr2),
                                 "natif_dmax": max((hexgeo.distance(P, Y) for P in inr2),
                                                   default=None)}
        out["elev"] = elev_ok
        return out
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all", choices=["inventaire", "arms", "all"])
    a = ap.parse_args()
    rc = 0
    if a.step in ("inventaire", "all"):
        rc |= step_inventaire()
    if a.step in ("arms", "all"):
        print("")
        res = step_arms()
        if "error" in res:
            print("[arms] REFUS : %s" % res["error"])
            return rc | 1
        b, t = res["arms"]["bloque"], res["arms"]["temoin"]
        print("")
        print("VERDICT : bloque reach=%d natif_dmax=%s FP=%d FN=%d | temoin reach=%d "
              "natif_dmax=%s FP=%d FN=%d"
              % (b["reach"], b["natif_dmax"], len(b["fp"]), len(b["fn"]),
                 t["reach"], t["natif_dmax"], len(t["fp"]), len(t["fn"])))
        if b["reach"] == t["reach"]:
            print("REGIME DEGENERE : les deux bras donnent le meme reach -- rien n'est separe")
            rc |= 1
        if b["fp"] or b["fn"]:
            rc |= 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
