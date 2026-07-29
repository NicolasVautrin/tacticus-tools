#!/usr/bin/env python
"""probe_250_summon_automatic -- POURQUOI le trait `Summon` eteint `ActiveAbility.CanStillBeUsed`.

LA QUESTION (posee par case-245 puis case-243, contournee trois fois, jamais expliquee)
---------------------------------------------------------------------------------------
Une unite portant le trait `Summon` rend `abilityState.usable == false` sur ses actives, donc
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` court-circuite a `0x1` et l'oracle
de ciblage ne dit plus rien. Les trois cas precedents ont RETIRE le trait de l'entree de catalogue
pour contourner ; aucun n'a explique la cause. La chaine candidate retenue (« le slot virtuel
`+0x3d8` lu par `IdunBattle.Entities.Abilities.AActiveAbility$$CanStillBeUsed` ») est un cul-de-sac :
ce slot est `GetCooldownAfterUse`, il ne lit AUCUN trait.

CE QUE DIT LE DECOMPILE (lu avant toute mesure)
-----------------------------------------------
1. Le champ mesure est `IdunBattle.Entities.Components.ActiveAbility` `CanStillBeUsed` @0x28.
   `IdunBattle.Entities.Components.ActiveAbility$$.ctor` le pose a `1`, et il n'a que TROIS
   ecrivains :
     * `IdunBattle.Operations.AddUnitOperation$$InitializeAbilitiesStatus` (au spawn) :
         comp.CanStillBeUsed = ability.CanStillBeUsed(unit, comp.AmountOfTimesUsed@0x10)
     * `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` (apres un cast) :
         comp.AmountOfTimesUsed@0x10 += 1 ; comp.<0x14> += 1 ;
         comp.CanStillBeUsed = ability.CanStillBeUsed(caster, comp.AmountOfTimesUsed)
     * `IdunBattle.Operations.ResetActiveAbilityOperation$$Execute` (re-arme) :
         comp.<0x18> = 0 ; comp.AmountOfTimesUsed@0x10 = 0 ; comp.CanStillBeUsed = 1
2. `IdunBattle.Entities.Abilities.AActiveAbility$$CanStillBeUsed(caster, amountOfTimesAlreadyUsed)` :
         if (UnitExtensions.IsBoss(caster)) return true;
         if (EntityExtensions.IsMachine(caster)) { ...primaire de machine... }
         cd = GetCooldownAfterUse();                  // slot virtuel +0x3d8, constante 0x27
         if (cd.HasValue && cd.Value > 0) return true;
         return amountOfTimesAlreadyUsed == 0;
   => AUCUNE lecture de trait. Une active SANS cooldown ne sert qu'UNE FOIS par bataille, et c'est
   la SEULE facon d'eteindre le champ.
3. Le trait `Summon` (`IdunBattle.Entities.Enum.UnitTrait` 2) est lu par
   `IdunBattle.Entities.UnitExtensions$$IsAutomatic` :
         HasTrait(2 Summon) || HasTrait(13 Object)
   et son SEUL consommateur cote moteur est
   `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute(player, skipAction)` :
         foreach (u in player.CurrentlyOwnedUnits
                    where u.IsAlive() && !u.HasFlag(3 TurnFinished) && u.IsAutomatic())
             if (!skipAction) for (i = 0; i < 5; i++) if (u.HasActionLeft()) <ComputerAction>(u);
             <EndUnitTurn>(u);
   appele par `Core.Services.OperationProcessor$$PlayAutomaticUnits` /
   `...$$FinishAutomaticUnitsTurn`.

L'HYPOTHESE A TRANCHER, ET CE QUE CE PROBE MESURE
-------------------------------------------------
Le trait `Summon` ne DESARME rien : il rend l'unite AUTOMATIQUE. Le moteur la joue lui-meme au tour
de son proprietaire ; elle consomme son active toute seule ; `CanStillBeUsed` retombe a false par le
chemin (2) -- exactement comme pour n'importe quelle unite ayant deja caste. Ce que les trois cas
precedents ont pris pour un gate est le RESIDU d'un cast reel.

MONTAGE. Le probe ne joue JAMAIS le summon : la seule action emise est `endturn`. Deux variantes du
MEME roster, meme board / meme seed, l'entree de catalogue amenagee sur les MEMES deux champs qu'en
case-243/245 (`Health` 0 -> 5000, l'entree d'un summon porte 0) :

  * `keep`  -- traits INCHANGES (le trait `Summon` est present)
  * `strip` -- le seul trait `Summon` retire, tout le reste identique

Signal attendu si l'hypothese tient : en `keep`, sans aucun ordre de notre part, le summon BOUGE
et/ou son `usable` passe true -> false des que son camp prend la main ; en `strip`, il ne bouge pas
et `usable` reste true. Si au contraire `usable` etait deja false AVANT que son camp ait joue, ce
serait un desarmement, et l'hypothese tomberait.

Le porteur `tyranSmnWarrior` est DEJA au catalogue `data/seed-bc.json` (`VisualId` =
`tyranNpc4Warrior`) : aucune injection de catalogue n'est necessaire -- ce qui evite au passage la
panne `initAndStart: system error` des rosters injectes depuis la MAJ.

USAGE
  python probe_250_summon_automatic.py [--board MC1_67] [--seed 777] [--rounds 4]
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dataclasses import replace as _replace                          # noqa: E402

import hexgeo                                                        # noqa: E402
import rl_duel as RD                                                 # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import (RANGED_BOOL_FALSE,    # noqa: E402
                                               RANGED_BOOL_TRUE,
                                               get_invalid_target_reason)
from engine.runner.snapshot import load_state                        # noqa: E402

CARRIER = "tyranSmnWarrior"          # Id de catalogue
CARRIER_VIS = "tyranNpc4Warrior"     # VisualId expose par decisionView
CARRIER_HEALTH = 5000
ENEMY = "necroWarden"
N_ENEMIES = 4
# Un allie CONTROLABLE est indispensable : quand TOUTES les unites du camp sont automatiques, le
# camp n'a jamais `ctrl` et `endturn` ne fait plus avancer les tours (mesure : le porteur se fige
# apres deux tours). L'allie est un simple relais de tour, il n'agit jamais.
ESCORT = "necroWarden"
BOARD = "MC1_67"
SEED = 777
RANK = 17
ABILITY = 1065          # ScythingTalons, l'active de tyranSmnWarrior (module `splash`)
TR_IN_RANGE = 0x8000000  # `IdunBattle.Core.Services.TargetingRule.TargetIsInRange` (bit 27)

_seq = itertools.count()


def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)


def _act(sid, rid, action, timeout=90):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action}, timeout)


def _by_vis(dv, vis):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis:
            return u
    return None


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _build(sid, seed, board, keep_summon_trait):
    """Runner isole : le porteur summon cote joueur, N ennemis en face. `owner` = state-file PROPRE
    sous `logs/` (jamais `data/`, qui est versionne)."""
    state_file = ROOT / "logs" / ("_probe250-%d-%d.json" % (os.getpid(), next(_seq)))
    state_file.parent.mkdir(parents=True, exist_ok=True)
    dump = RD._load_board_dump(board)
    template, _pool, _mow = RD._normalize_and_extract_pool(
        sid, RD._load_seed_bc(None), RANK, board_dump=dump)
    bc = copy.deepcopy(template)
    e = next((u for u in bc["Units"] if u.get("Id") == CARRIER), None)
    if e is None:
        raise RuntimeError("%s absent du catalogue BC.Units" % CARRIER)
    e["Health"] = CARRIER_HEALTH
    e["RemainingHealth"] = CARRIER_HEALTH
    traits = list(e.get("Traits") or [])
    if not keep_summon_trait:
        traits = [t for t in traits if t != "Summon"]
    e["Traits"] = traits
    RD._patch_predefined_units(bc, [ENEMY] * N_ENEMIES)
    spawns = RD._spawn_points_by_twpi(bc)
    pts = spawns.get(0) or []
    if not pts:
        raise RuntimeError("aucun spawn point joueur sur %s" % board)
    if len(pts) < 2:
        raise RuntimeError("%d spawn(s) joueur < 2 sur %s" % (len(pts), board))
    pu = [{"unitId": CARRIER, "playerId": RD.PLAYER_ID_HUMAN,
           "col": int(pts[0][0]), "row": int(pts[0][1])},
          {"unitId": ESCORT, "playerId": RD.PLAYER_ID_HUMAN,
           "col": int(pts[1][0]), "row": int(pts[1][1])}]
    resp = _rpc(sid, "initAndStart",
                [{"configJson": json.dumps(bc), "seed": seed, "playerUnits": pu,
                  "owner": str(state_file.resolve())}], timeout=120)
    rid = ((resp or {}).get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % json.dumps(resp)[:400])
    state_file.write_text(json.dumps({"runnerId": int(rid)}), encoding="utf-8")
    return int(rid), state_file, traits


def _snap(sid, rid):
    """Etat OBSERVABLE du porteur + des ennemis, sans rien muter."""
    dv = _dv(sid, rid)
    u = _by_vis(dv, CARRIER_VIS)
    if u is None:
        return None
    acts = []
    for a in (u.get("abilities") or []):
        acts.append({"id": a.get("id"), "usable": a.get("usable"),
                     "cooldown": a.get("cooldown"), "disabled": a.get("disabled")})
    foes = sorted((x for x in (dv.get("units") or [])
                   if x.get("owner") != u.get("owner")), key=lambda x: int(x["id"]))
    return {
        "turn": (dv.get("meta") or {}).get("turn"),
        "ctrl": bool(u.get("ctrl")),
        "alive": bool(u.get("alive")),
        "pos": _pos(u),
        "hp": u.get("hp"),
        "hasAction": u.get("hasAction"),
        "abilities": acts,
        "foeHp": [(int(x["id"]), x.get("hp")) for x in foes],
    }


def _fmt(s):
    ab = " ".join("%s:usable=%s,cd=%s,dis=%s" % (a["id"], a["usable"], a["cooldown"], a["disabled"])
                  for a in s["abilities"])
    return ("turn=%s ctrl=%s pos=%s hp=%s hasAction=%s | %s | foeHp=%s"
            % (s["turn"], s["ctrl"], s["pos"], s["hp"], s["hasAction"], ab,
               [h for _, h in s["foeHp"]]))


def _graph(sid, rid):
    """Adjacence hex NATIVE + walkable (`boardGraph`), capturee une fois."""
    g = _r(sid, "boardGraph", {"runnerId": rid}, 120)
    tiles = g.get("tiles") or []
    pos_by_id = {int(t["id"]): (t.get("col"), t.get("row")) for t in tiles}
    adj, walk = {}, {}
    for t in tiles:
        p = (t.get("col"), t.get("row"))
        walk[p] = bool(t.get("walkable"))
        adj[p] = [pos_by_id[int(n)] for n in (t.get("neighbours") or []) if int(n) in pos_by_id]
    return adj, walk


def _drive_foe_to_contact(sid, rid, adj, walk):
    """Amene un ennemi sur une tuile ADJACENTE au porteur. `applyAction` ne verifie pas la
    propriete du `unitId` (levier deja utilise par probe_243) : on CONDUIT la geometrie plutot que
    de la subir. Rend l'id de l'ennemi deplace, ou None."""
    dv = _dv(sid, rid)
    u = _by_vis(dv, CARRIER_VIS)
    if u is None:
        return None
    here = _pos(u)
    occupied = {_pos(x) for x in (dv.get("units") or []) if x.get("alive")}
    foes = [x for x in (dv.get("units") or [])
            if x.get("alive") and x.get("owner") != u.get("owner")]
    if not foes:
        return None
    free = [p for p in adj.get(here, []) if walk.get(p) and p not in occupied]
    if not free:
        return None
    fid = int(foes[0]["id"])
    _act(sid, rid, {"kind": "move", "unitId": fid,
                    "to": {"col": free[0][0], "row": free[0][1]}}, 90)
    return fid


def _hexval(node):
    h = (node or {}).get("hex")
    if isinstance(h, str):
        return int(h, 16)
    return 0 if (node or {}).get("ruleClass") == "NoBrokenTargetingRule" else None


def _variant(kind):
    """`apres` = le masque PORTE ; `avant` = l'etat pre-masque (`TARGETING_OPTIONS = None`, gate
    entierement absent) -- le contrefactuel qui chiffre la degradation PERMISSIVE fermee ;
    `fmtFlip` bascule `force_melee_target`, le champ que case-243 a montre discriminant sur les
    trois autres masques du module `splash`."""
    klass = ABILITY_CLASSES[ABILITY]
    if kind == "apres":
        return klass()
    base = klass.TARGETING_OPTIONS
    opts = {
        "avant": None,
        "sansRules": _replace(base, rules=0),
        "sansRange": _replace(base, range=None),
        "fmtFlip": _replace(base, force_melee_target=(RANGED_BOOL_FALSE
                                                      if int(base.force_melee_target) == RANGED_BOOL_TRUE
                                                      else RANGED_BOOL_TRUE)),
    }[kind]

    class _V(klass):
        __slots__ = ()
        TARGETING_OPTIONS = opts
    return _V()


VARIANTS = ["apres", "avant", "sansRules", "sansRange", "fmtFlip"]


def _confront_mask(sid, rid):
    """VOLET 2 : le masque de 1065 confronte sur son PORTEUR REEL, toutes cibles vivantes.
    Oracle = `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` via `abilityReason` ;
    le port est rejoue sur le MEME etat fige."""
    dv = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 120)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    caster = _by_vis(dv, CARRIER_VIS)
    cid = int(caster["id"])
    rows = []
    for u in (dv.get("units") or []):
        if not u.get("alive"):
            continue
        tid = int(u["id"])
        side = ("CASTER" if tid == cid else
                ("ALLIE" if u.get("owner") == caster.get("owner") else "ENNEMI"))
        nat = _r(sid, "abilityReason",
                 {"runnerId": rid, "casterId": cid, "abilityType": ABILITY, "targetId": tid}, 60)
        tr = (nat or {}).get("targetReason") or {}
        row = {"tid": tid, "side": side, "dist": hexgeo.distance(_pos(caster), _pos(u)),
               "nat": _hexval(tr), "reasons": tr.get("reasons") or []}
        for v in VARIANTS:
            row[v] = int(get_invalid_target_reason(st, cid, tid, _variant(v)))
        rows.append(row)
    return caster, rows


def _print_mask(caster, rows):
    opts = ABILITY_CLASSES[ABILITY].TARGETING_OPTIONS
    print("\n=== masque 1065 sur son PORTEUR REEL u%s(%s) -- rules=0x%x range=%s"
          % (caster["id"], caster.get("visualId"), int(opts.rules), opts.range))
    print("  %-8s %-4s %-12s %-12s %-12s %s" % ("side", "d", "natif", "port(apres)",
                                                "port(avant)", "flags natifs"))
    ok = bad = closed = 0
    div = {v: 0 for v in VARIANTS if v != "apres"}
    for r in sorted(rows, key=lambda x: (x["side"], x["dist"], x["tid"])):
        agree = (r["nat"] == r["apres"])
        ok += agree
        bad += (not agree)
        closed += (r["avant"] != r["nat"] and agree)
        for v in div:
            div[v] += (r[v] != r["apres"])
        print("  %-8s %-4d 0x%-10x 0x%-10x 0x%-10x %s%s"
              % (r["side"], r["dist"], r["nat"] or 0, r["apres"], r["avant"],
                 ",".join(r["reasons"]) or "-", "" if agree else "   <-- DESACCORD"))
    print("  accord natif/port = %d/%d ; casts illegaux fermes par le masque = %d" % (ok, ok + bad, closed))
    print("  contrefactuels (lignes divergentes / %d) : %s"
          % (len(rows), ", ".join("%s=%d" % (k, v) for k, v in div.items())))
    return ok, bad, closed, div


def _drive_foe_to_dist(sid, rid, adj, walk, want):
    """Amene un ennemi ENCORE NON CONDUIT a la distance hex `want` du porteur. Encadrer le seuil
    de portee DES DEUX COTES (d=1 accepte / d=2 refuse) est ce qui distingue une mesure d'une
    confirmation : sans la ligne d=2, un port sans volet portee passerait aussi."""
    dv = _dv(sid, rid)
    u = _by_vis(dv, CARRIER_VIS)
    if u is None:
        return None
    here = _pos(u)
    occupied = {_pos(x) for x in (dv.get("units") or []) if x.get("alive")}
    cand = [p for p, w in walk.items()
            if w and p not in occupied and hexgeo.distance(p, here) == want]
    foes = [x for x in (dv.get("units") or [])
            if x.get("alive") and x.get("owner") != u.get("owner")
            and hexgeo.distance(_pos(x), here) != want]
    if not cand or not foes:
        return None
    fid = int(foes[-1]["id"])
    _act(sid, rid, {"kind": "move", "unitId": fid,
                    "to": {"col": cand[0][0], "row": cand[0][1]}}, 90)
    return fid


def run_cast(sid, seed, board, rounds=6):
    """MAILLON 2, isole : `CanStillBeUsed` s'eteint-il par l'USAGE, sans aucun trait ?

    Variante `strip` (le porteur est CONTROLABLE) : on amene un ennemi adjacent, on interroge
    l'oracle natif (`abilityReason` -> `TargetingQuery$$GetInvalidTargetReason`), on CASTE 1065
    nous-memes, puis on relit `usable`. Le mirror natif est
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` :
        comp.AmountOfTimesUsed@0x10 += 1 ;
        comp.CanStillBeUsed@0x28 = ability.CanStillBeUsed(caster, comp.AmountOfTimesUsed)
    et `AActiveAbility$$CanStillBeUsed` rend alors `amountOfTimesAlreadyUsed == 0` = false (1065
    n'a pas de `GetCooldownAfterUse`)."""
    rid, sf, traits = _build(sid, seed, board, keep_summon_trait=False)
    print("[cast ] runner=%d traits=%s" % (rid, ",".join(traits)))
    out = {"before": None, "reason": None, "applied": None, "after": None, "dmg": None}
    try:
        adj, walk = _graph(sid, rid)
        for i in range(rounds):
            dv = _dv(sid, rid)
            u = _by_vis(dv, CARRIER_VIS)
            if u is None or not u.get("ctrl") or not u.get("hasAction"):
                _act(sid, rid, {"kind": "endturn"}, 90)
                continue
            fid = _drive_foe_to_contact(sid, rid, adj, walk)
            if fid is None:
                _act(sid, rid, {"kind": "endturn"}, 90)
                continue
            f2 = _drive_foe_to_dist(sid, rid, adj, walk, 2)
            if f2 is not None:
                print("  [cast ] ennemi u%d amene a d=2 (encadrement du seuil de portee)" % f2)
            dv = _dv(sid, rid)
            u = _by_vis(dv, CARRIER_VIS)
            foe = next((x for x in (dv.get("units") or []) if int(x["id"]) == fid), None)
            cid = int(u["id"])
            out["before"] = _snap(sid, rid)
            print("  [cast ] avant : %s" % _fmt(out["before"]))
            # VOLET 2 -- masque de 1065 confronte sur le porteur reel, AVANT de consommer la charge
            # (apres le cast, le court-circuit `CanCurrentlyBeUsed` rendrait 0x1 partout).
            c_u, rows = _confront_mask(sid, rid)
            out["rows"] = rows
            out["mask"] = _print_mask(c_u, rows)
            hp0 = foe.get("hp") if foe else None
            res = _act(sid, rid, {"kind": "ability", "casterId": cid,
                                  "targetId": fid, "abilityType": ABILITY}, 120)
            out["applied"] = res
            out["after"] = _snap(sid, rid)
            print("  [cast ] apres : %s" % _fmt(out["after"]))
            dvz = _dv(sid, rid)
            foe2 = next((x for x in (dvz.get("units") or []) if int(x["id"]) == fid), None)
            out["dmg"] = (hp0 or 0) - ((foe2 or {}).get("hp") or 0)
            print("  [cast ] degats sur u%d = %s" % (fid, out["dmg"]))
            break
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass
    return out


def run_variant(sid, seed, board, keep, rounds, contact=False):
    tag = "keep " if keep else "strip"
    rid, sf, traits = _build(sid, seed, board, keep)
    print("[%s] runner=%d traits=%s" % (tag, rid, ",".join(traits)))
    snaps = []
    try:
        adj, walk = _graph(sid, rid) if contact else ({}, {})
        for i in range(rounds):
            s = _snap(sid, rid)
            if s is None:
                print("  [%s] r%d : porteur ABSENT du decisionView" % (tag, i))
                break
            snaps.append(s)
            print("  [%s] r%d %s" % (tag, i, _fmt(s)))
            if not s["alive"]:
                break
            if contact:
                fid = _drive_foe_to_contact(sid, rid, adj, walk)
                if fid is not None:
                    print("       (ennemi u%d amene au contact)" % fid)
            _act(sid, rid, {"kind": "endturn"}, 90)     # SEULE action emise : jamais le porteur
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass
    return snaps


def _verdict(tag, snaps):
    """Rend (a_bouge, usable_initial, usable_final, ctrl_vu)."""
    if not snaps:
        return None
    poss = [s["pos"] for s in snaps]
    moved = len(set(poss)) > 1
    def _us(s):
        vals = [a["usable"] for a in s["abilities"]]
        return vals
    first, last = snaps[0], snaps[-1]
    foe0 = dict(first["foeHp"])
    foeN = dict(last["foeHp"])
    dmg = sum(max(0, (foe0.get(k) or 0) - (foeN.get(k) or 0)) for k in foe0)
    print("[%s] positions=%s bouge=%s usable(debut)=%s usable(fin)=%s degats_infliges=%s"
          % (tag, poss, moved, _us(first), _us(last), dmg))
    return {"moved": moved, "u0": _us(first), "uN": _us(last), "dmg": dmg,
            "ctrl_seen": [s["ctrl"] for s in snaps]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--only", choices=["keep", "strip", "cast"], default=None)
    ap.add_argument("--contact", action="store_true",
                    help="amene un ennemi ADJACENT au porteur a chaque tour (declenche son cast)")
    a = ap.parse_args(argv)
    sid = _resolve_session()
    print("session=%s board=%s seed=%d rounds=%d" % (sid, a.board, a.seed, a.rounds))
    if a.only == "cast":
        run_cast(sid, a.seed, a.board, a.rounds)
        return 0
    out = {}
    for keep in ([True] if a.only == "keep" else [False] if a.only == "strip" else [True, False]):
        tag = "keep " if keep else "strip"
        snaps = run_variant(sid, a.seed, a.board, keep, a.rounds, contact=a.contact)
        out[tag.strip()] = _verdict(tag, snaps)
    print()
    k, s = out.get("keep"), out.get("strip")
    if k and s:
        print("=== CONFRONTATION ===")
        print("  AVEC trait Summon  : bouge=%s usable %s -> %s degats=%s"
              % (k["moved"], k["u0"], k["uN"], k["dmg"]))
        print("  SANS trait Summon  : bouge=%s usable %s -> %s degats=%s"
              % (s["moved"], s["u0"], s["uN"], s["dmg"]))
        auto = k["moved"] or k["dmg"] > 0 or (k["u0"] != k["uN"])
        inert = (not s["moved"]) and s["dmg"] == 0
        if auto and inert:
            print("  VERDICT : le trait Summon rend l'unite AUTOMATIQUE (le moteur la joue).")
            print("            CanStillBeUsed=false est le RESIDU d'un cast reel, pas un gate.")
        else:
            print("  VERDICT : NON CONCLUANT sur ce montage (auto=%s inert=%s)" % (auto, inert))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
