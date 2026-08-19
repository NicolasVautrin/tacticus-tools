#!/usr/bin/env python
"""probe_245_target_is_healable -- ARMEMENT de la regle de ciblage `TargetIsHealable` (bit 8, 0x100)
sur SES DEUX PORTEURS : 1002 `CombatRestoratives` (ultraApothecary) et 1037
`RevitalizingMalignancy` (deathRotbone). Les deux masques valent 0x8500 -- MAIS deux abilities qui
partagent un masque ne partagent pas forcement un verdict, d'ou les DEUX montages.

CE QUE LA REGLE TESTE (decompile = verite)
------------------------------------------
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge SEPT arguments -- pas
celle a quatre, qui court-circuite pour un caster MoW), bloc TRAITS, apres `TargetIsSummon` et avant
`TargetHasFreeAdjacentTile` :

    if ((rules & 0x100) != 0) {
        aq = this.<+0x10>;                              // `TargetingQuery$$Init` : *(this+0x10) = attackQuery
        if (!aq.<slot 0x11>(caster, <cible resolue>, 0, 1)) -> broken(0x100)
    }

Le slot 0x11 de l'interface est `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed` -- lu sur un
DEUXIEME call-site independant : `IdunBattle.Entities.Selectors.HealableUnitsSelector$$Select`, le
selecteur qui PORTE le nom `Healable`, resout ce meme slot 0x11 sur la MEME classe d'interface.

Ce predicat a SIX termes ; la garde de mutation `healable_heal_type_0` n'en couvre que DEUX (HP<max
et `IsAffectedByHealType(target, 0)`). Le port cable donc le mirror COMPLET
`abilities/attack_query.py::entity_can_be_healed`, pas la garde de mutation.

LES TROIS LIGNES DISCRIMINANTES QUE CE MONTAGE FABRIQUE (jamais subies)
----------------------------------------------------------------------
  * allie ADJACENT et BLESSE, NON mecanique -> natif ACCEPTE (0). Sans elle, un port qui refuserait
    TOUT serait indistinguable d'un port correct.
  * allie ADJACENT a PV PLEINS               -> natif refuse 0x100 (`IsDamagedUnit` faux).
  * allie ADJACENT et BLESSE, MECANIQUE      -> natif refuse 0x100 (`IsAffectedByHealType(_, 0)`
    faux) : c'est CETTE ligne qui separe le terme `HP<max` du terme `heal type`, et qui interdit de
    faire passer la regle pour un simple test de PV.
Plus l'ennemi adjacent (0x400 `TargetIsFriendly`, teste AVANT) et l'allie eloigne (0x8000000
`TargetIsInRange`, teste AVANT aussi) : l'ORDRE de la cascade est mesure en meme temps que la regle.

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)`.
Le port rejoue le gate OFFLINE sur le MEME etat fige, en trois variantes : APRES (l'ability du
registre), AVANT (`TARGETING_OPTIONS = None`, l'etat d'avant #181) et `sansHealable` (le masque prive
du seul bit 8) -- le contrefactuel qui prouve que c'est bien CE bit qui rend le verdict.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_245_target_is_healable.py
    python probe_245_target_is_healable.py --only 1037 --board C4_09

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from dataclasses import replace as _replace
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import get_invalid_target_reason   # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR    # noqa: E402
from engine.runner.components import HealthComponent                 # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

# --- LES DEUX PORTEURS.
#     `soft` = allie NON mecanique qu'on BLESSE       -> le natif l'ACCEPTE (ligne 0)
#     `mech` = allie MECANIQUE qu'on BLESSE AUSSI     -> le natif le REFUSE quand meme (0x100)
#     `full` = allie non mecanique laisse a PV PLEINS -> refuse 0x100 par l'autre terme
#     `far`  = allie tenu HORS contact                -> exerce le volet PORTEE, teste AVANT le bit 8
#
#     `mech` = `admecMarshall` (traits `Hero, Mechanical`) et SURTOUT PAS un necron : `necroWarden`
#     porte `LivingMetal`, donc la REGENERATION -- mesure de ce cas, il rentrait a 300000/300000
#     avant l'interrogation et sa ligne retombait sur « PV pleins », c'est-a-dire sur le MEME terme
#     que `full`. Les deux termes du predicat n'etaient alors plus separes.
CASES = {
    1002: {"caster": "ultraApothecary", "soft": "adeptHospitaller", "mech": "admecMarshall",
           "full": "eldarRanger", "far": "ultraEliminatorSgt"},
    1037: {"caster": "deathRotbone", "soft": "deathBlightlord", "mech": "admecMarshall",
           "full": "deathBlightbringer", "far": "deathPutrifier"},
}
FOES = "ultraTitus,worldKharn"
BOARD, SEED = "MC1_67", "777"
# PV hauts DES DEUX COTES : les attaques de mise en place BLESSENT sans TUER (une unite morte
# disparait de `decisionView.units[alive]` et emporte la ligne qu'elle devait fabriquer -- vu en
# diagnostic de ce cas : `worldKharn` tue pendant l'approche, l'ennemi le plus proche repartant a 11
# hexes). Piege de mesure connu de ces deux options : elles mettent Armor/FixedArmor a 0 -- sans
# consequence ici, l'armure n'entre dans `EntityCanBeHealed` par aucun terme (elle n'apparait que
# dans le disjunct `GetStat(Armor, Missing)` du JUMEAU `EntityCanBeRepaired`, bit 16, hors sujet).
HP_PLAYER = HP_TARGET = 300000
TOURS_DE_CHAUFFE = 6                # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)

# Regles NON PORTEES admises en ecart PERMISSIF (port == 0). `TargetIsHealable` n'y est PLUS : c'est
# tout l'objet de cette fiche.
NON_PORTES = {
    int(TR.AddCasterIfAtLeastOneTarget):
        "`IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason` -- non portee (elle "
        "depend de `TargetingQuery$$GetValidTargets`, qui ENUMERE tout le plateau)",
}

_seq = itertools.count()


def _known_gap(nat, apres) -> int:
    return int(nat) if (nat in NON_PORTES and int(apres) == 0) else 0


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(seed: str, board: str, p_units: str, a_units: str):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe245-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--hp-player", str(HP_PLAYER), "--hp-target", str(HP_TARGET),
            "--p-units", p_units, "--a-units", a_units]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-400:])
        time.sleep(10)


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _act(sid, rid, action, timeout=90):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action}, timeout)


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _by_vis(dec, vis):
    for u in (dec.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return u
    return None


def _movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                    if t.get("col") is not None]
    return []


def _hand_to(sid, rid, owner, maxit=4):
    """Rend la main au camp `owner` (chaine d'`endturn` ; runner `--no-ai`, rien ne bouge seul).
    On NOMME le camp voulu plutot que de tester `ctrl` d'une unite : ce probe pilote les DEUX camps
    pour monter sa geometrie, la tautologie serait invisible."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        if d.get("currentPlayer") == owner:
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


def _step_toward(sid, rid, unit_id, goal_pos, want: int) -> bool:
    """UN pas de `unit_id` vers la distance `want` de `goal_pos`, dans la limite de SON deplacement
    du tour courant. Rend False si l'unite a deja bouge (ou n'est pas au camp courant) : l'appelant
    decide d'attendre son prochain tour, jamais ce helper."""
    tiles = _movable(sid, rid, unit_id)
    if not tiles:
        return False
    best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, goal_pos) - want),
                                     hexgeo.distance(t, goal_pos), t))
    _act(sid, rid, {"kind": "move", "unitId": unit_id,
                    "to": {"col": best[0], "row": best[1]}}, 90)
    return True


def _load_offline(sid, rid):
    dv = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    board = Board(bg["tiles"], adjacency="native_sym")
    return load_state(dv, ob, snap, board=board), dv, board


def _nat(sid, rid, cid, aid, tid=None):
    body = {"runnerId": rid, "casterId": cid, "abilityType": aid}
    if tid is not None:
        body["targetId"] = tid
    nat = _r(sid, "abilityReason", body, 60) or {}
    tr = nat.get("targetReason") or {}
    h = tr.get("hex")
    val = int(h, 16) if isinstance(h, str) else (
        0 if tr.get("ruleClass") == "NoBrokenTargetingRule" else None)
    return val, (tr.get("reasons") or []), nat


# --------------------------------------------------------------------------- variantes du port

def _variant(aid: int, kind: str):
    klass = ABILITY_CLASSES[aid]
    base = klass.TARGETING_OPTIONS
    if kind == "apres":
        return klass()
    if kind == "avant":
        opts = None
    elif kind == "sansHealable":
        opts = _replace(base, rules=int(base.rules) & ~int(TR.TargetIsHealable))
    else:
        raise ValueError(kind)

    class _V(klass):                     # meme classe -> meme cascade, seul le masque change
        __slots__ = ()
        TARGETING_OPTIONS = opts
    return _V()


# --------------------------------------------------------------------------- montage

def _hp_of(dec, vis):
    u = _by_vis(dec, vis)
    return None if u is None else u.get("hp")


def _normal_attack_type(unit) -> Optional[int]:
    """L'`ActiveAbilityType` de l'attaque NORMALE de l'unite, lu dans `decisionView.units[].abilities`
    (l'entree `kind == "normal"`, ex. 69 `Loki_NormalAttack`).

    ⚠ `applyAction` n'a PAS de `kind: "attack"` -- ses seules formes sont `move` / `ability` /
    `finish` / `endturn` (`ai-step/rpc-view.ts`). Une action `attack` est acceptee par le transport
    puis rendue `ok: false` SANS message d'erreur : mesure de ce cas, 13 attaques de mise en place
    silencieusement perdues, montage « sans blessure » et ligne « natif ACCEPTE » manquante. On passe
    donc par `ability` + ce type -- et l'attaque normale n'est PAS l'id generique 17 mais un id
    CONCRET par unite."""
    for a in (unit or {}).get("abilities") or []:
        if a.get("kind") == "normal" and a.get("id") is not None:
            return int(a["id"])
    return None


def _approach(sid, rid, c: dict, mine: int, theirs: int, rounds=8) -> bool:
    """PHASE 1 -- amener MON groupe au contact du camp adverse. Le roster spawne SERRE DANS UN COIN
    (mesure de ce cas sur MC1_67 : les 5 unites en (0,0)..(1,1), l'adversaire a 10 hexes) : la
    victime y est ENCERCLEE PAR SES PROPRES ALLIES, aucune tuile libre au contact, et un ennemi qui
    « s'approche » ne peut jamais atteindre l'adjacence. On DEPLACE donc, on ne subit pas."""
    for it in range(rounds):
        d = _dv(sid, rid)
        soft, mech = _by_vis(d, c["soft"]), _by_vis(d, c["mech"])
        foes = [u for u in (d.get("units") or [])
                if u.get("alive") and u.get("owner") == theirs and None not in _pos(u)]
        if soft is None or mech is None or not foes:
            return False
        fp = _pos(min(foes, key=lambda u: hexgeo.distance(_pos(soft), _pos(u))))
        d_soft = min(hexgeo.distance(_pos(soft), _pos(f)) for f in foes)
        d_mech = min(hexgeo.distance(_pos(mech), _pos(f)) for f in foes)
        print("  [approche %d] d(soft,ennemi)=%d d(mech,ennemi)=%d" % (it, d_soft, d_mech))
        if d_soft <= 1 and d_mech <= 1:
            return True
        _hand_to(sid, rid, mine)
        for vis, want in ((c["soft"], 1), (c["mech"], 1), (c["full"], 2), (c["caster"], 2)):
            u = _by_vis(_dv(sid, rid), vis)
            if u is not None:
                _step_toward(sid, rid, int(u["id"]), fp, want)
        _hand_to(sid, rid, theirs)
        for f in foes:
            _step_toward(sid, rid, int(f["id"]), _pos(soft), 1)
        _act(sid, rid, {"kind": "endturn"}, 60)
    return False


def _wound(sid, rid, victim_vis: str, theirs: int, rounds=4) -> bool:
    """PHASE 2 -- BLESSER `victim_vis` : un ennemi ADJACENT l'attaque. Rend True seulement si les PV
    ont EFFECTIVEMENT baisse : une blessure SUPPOSEE ne vaut rien, la ligne « natif ACCEPTE » repose
    entierement dessus (et sa jumelle « mecanique BLESSE, natif refuse quand meme » aussi)."""
    hp0 = _hp_of(_dv(sid, rid), victim_vis)
    if hp0 is None:
        return False
    for _ in range(rounds):
        _hand_to(sid, rid, theirs)
        d = _dv(sid, rid)
        vic = _by_vis(d, victim_vis)
        if vic is None:
            return False
        foes = sorted((u for u in (d.get("units") or [])
                       if u.get("alive") and u.get("owner") == theirs and None not in _pos(u)),
                      key=lambda u: (hexgeo.distance(_pos(vic), _pos(u)), int(u["id"])))
        for foe in foes:
            na = _normal_attack_type(foe)
            if na is None or hexgeo.distance(_pos(vic), _pos(foe)) > 1:
                continue
            out = _act(sid, rid, {"kind": "ability", "casterId": int(foe["id"]),
                                  "targetId": int(vic["id"]), "abilityType": na}, 120)
            hp1 = _hp_of(_dv(sid, rid), victim_vis)
            print("    [attaque normale %d] %s -> %s  hp %s -> %s  ok=%s"
                  % (na, foe.get("visualId"), victim_vis, hp0, hp1, (out or {}).get("ok")))
            if hp1 is not None and int(hp1) < int(hp0):
                return True
        for foe in foes:
            _step_toward(sid, rid, int(foe["id"]), _pos(vic), 1)
        _act(sid, rid, {"kind": "endturn"}, 60)
    return False


def _regroup(sid, rid, c: dict, mine: int, rounds=8) -> bool:
    """PHASE 3 -- geometrie DISCRIMINANTE : `soft`/`mech`/`full` au CONTACT du caster, `far` HORS
    contact (c'est lui qui exerce le volet PORTEE, teste AVANT le bit 8 dans la cascade). Le CASTER
    ne bouge PAS ici : on ne veut pas consommer son action avant l'interrogation."""
    near = (c["soft"], c["mech"], c["full"])
    for it in range(rounds):
        d = _hand_to(sid, rid, mine)
        me = _by_vis(d, c["caster"])
        if me is None:
            return False
        cp = _pos(me)
        dist = {v: (None if _by_vis(d, v) is None
                    else hexgeo.distance(cp, _pos(_by_vis(d, v))))
                for v in near + (c["far"],)}
        print("  [regroup %d] caster=%s distances=%s" % (it, cp, dist))
        if (all(dist.get(v) == 1 for v in near)
                and (dist.get(c["far"]) is None or dist[c["far"]] > 1)):
            return True
        for vis in near:
            u = _by_vis(_dv(sid, rid), vis)
            if u is not None and hexgeo.distance(cp, _pos(u)) != 1:
                _step_toward(sid, rid, int(u["id"]), cp, 1)
        u = _by_vis(_dv(sid, rid), c["far"])
        if u is not None and hexgeo.distance(cp, _pos(u)) <= 1:
            _step_toward(sid, rid, int(u["id"]), cp, 4)
        _act(sid, rid, {"kind": "endturn"}, 60)
    return False


def _run(sid, aid: int, seed: str, board_id: str) -> dict:
    c = CASES[aid]
    roster = ",".join((c["caster"], c["soft"], c["mech"], c["full"], c["far"]))
    rid, sf = _build(seed, board_id, roster, FOES)
    print("\n########## ability %d  runner=%d board=%s seed=%s  roster=%s"
          % (aid, rid, board_id, seed, roster))
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)

        d0 = _dv(sid, rid)
        me0 = _by_vis(d0, c["caster"])
        if me0 is None:
            raise RuntimeError("caster %s absent au demarrage" % c["caster"])
        mine = me0.get("owner")
        theirs = next((u.get("owner") for u in (d0.get("units") or [])
                       if u.get("alive") and u.get("owner") != mine), None)
        if theirs is None:
            raise RuntimeError("aucun camp adverse")

        # 1) APPROCHE puis BLESSURES de `soft` (non mecanique) et `mech` (mecanique) -- les deux
        #    moities du predicat : HP<max d'un cote, `IsAffectedByHealType(_, 0)` de l'autre.
        appr = _approach(sid, rid, c, mine, theirs)
        w_soft = _wound(sid, rid, c["soft"], theirs)
        w_mech = _wound(sid, rid, c["mech"], theirs)
        print("  [approche=%s] [blessures] %s=%s  %s=%s"
              % (appr, c["soft"], w_soft, c["mech"], w_mech))

        # 2) GEOMETRIE : soft/mech/full au contact du caster, far a l'ecart.
        geom = _regroup(sid, rid, c, mine)
        _hand_to(sid, rid, mine)

        st, dv, _board = _load_offline(sid, rid)
        me = _by_vis(dv, c["caster"])
        if me is None:
            raise RuntimeError("caster absent du plateau")
        cid = int(me["id"])
        usable = bool(((_nat(sid, rid, cid, aid)[2] or {}).get("abilityState") or {}).get("usable"))
        if not usable:
            raise RuntimeError("ability %d non utilisable -> l'oracle court-circuite (ValidRequest)"
                               % aid)
        units = {int(u["id"]): u for u in (dv.get("units") or []) if u.get("alive")}
        own = me.get("owner")

        def _hp(tid):
            e = st.get_entity(int(tid))
            hc = e.get_component(HealthComponent) if e is not None else None
            if hc is None or hc.hp is None or hc.hp_max is None:
                return None
            return (int(hc.hp), int(hc.hp_max))

        rows = []
        for tid in sorted(units):
            u = units[tid]
            side = ("CASTER" if tid == cid else ("ALLIE" if u.get("owner") == own else "ENNEMI"))
            hp = _hp(tid)
            nat_val, nat_reasons, _raw = _nat(sid, rid, cid, aid, tid)
            rows.append({
                "label": "%s %s d=%d %s" % (
                    side, u.get("visualId"), hexgeo.distance(_pos(me), _pos(u)),
                    ("hp=%d/%d" % hp) if hp else "hp=?"),
                "targetId": tid, "visualId": u.get("visualId"), "side": side,
                "wounded": bool(hp and hp[0] < hp[1]),
                "nat": nat_val, "nat_reasons": nat_reasons,
                "apres": int(get_invalid_target_reason(st, cid, tid, _variant(aid, "apres"))),
                "avant": int(get_invalid_target_reason(st, cid, tid, _variant(aid, "avant"))),
                "sansHealable": int(get_invalid_target_reason(
                    st, cid, tid, _variant(aid, "sansHealable"))),
            })
        return {"ability": aid, "caster": cid, "rows": rows, "geom": geom,
                "wounded_soft": w_soft, "wounded_mech": w_mech,
                "soft": c["soft"], "mech": c["mech"], "full": c["full"], "far": c["far"]}
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            sf.unlink(missing_ok=True)
            print("[cleanup] runner %d dispose" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)


def report(res: dict) -> bool:
    aid, rows = res["ability"], res["rows"]
    opts = ABILITY_CLASSES[aid].TARGETING_OPTIONS
    print("\n=== ability %d  masque 0x%x  range=%s" % (aid, int(opts.rules), opts.range))
    print("  %-46s %-6s %-12s %-24s %-12s %-12s %-12s"
          % ("cible", "id", "natif", "regle", "APRES", "AVANT", "sansHealable"))
    n_ok = n_gap = n_gain = 0
    for r in rows:
        gap = _known_gap(r["nat"], r["apres"])
        agree = (r["nat"] == r["apres"])
        n_gap += 1 if gap else 0
        n_ok += 1 if (agree or gap) else 0
        gain = (r["nat"] not in (None, 0)) and r["avant"] == 0 and not gap
        n_gain += 1 if gain else 0
        print("  %-46s %-6d %-12s %-24s %-12s %-12s %-12s %s%s"
              % (r["label"], r["targetId"], "-" if r["nat"] is None else hex(r["nat"]),
                 ",".join(r["nat_reasons"]) or "-", hex(r["apres"]), hex(r["avant"]),
                 hex(r["sansHealable"]),
                 "GAP-permissif" if gap else ("OK" if agree else "MISMATCH"),
                 "  <-GAIN" if gain else ""))
    moved = sum(1 for r in rows if r["sansHealable"] != r["apres"])
    heal_refus = [r for r in rows if r["nat"] == int(TR.TargetIsHealable)]
    accept = [r for r in rows if r["nat"] == 0 and r["side"] == "ALLIE"]
    # LA LIGNE QUI SEPARE LES DEUX TERMES : allie MECANIQUE et BLESSE, refuse quand meme. Sans elle,
    # `TargetIsHealable` serait indistinguable d'un simple « HP < max ».
    mech_wounded = [r for r in rows if r["visualId"] == res["mech"] and r["wounded"]
                    and r["nat"] == int(TR.TargetIsHealable)]
    print("  [contrefactuel] sansHealable deplace %d verdict(s) -> %s"
          % (moved, "PORTEUR" if moved else "INERTE (le bit n'est pas valide par cette mesure)"))
    print("  [lignes] natif==0x100 : %d ; ALLIE natif==0 (cible ACCEPTEE) : %d ; MECANIQUE BLESSE "
          "refuse : %d ; blessures posees soft=%s mech=%s ; geometrie=%s"
          % (len(heal_refus), len(accept), len(mech_wounded),
             res["wounded_soft"], res["wounded_mech"], res["geom"]))
    print("  [bilan] accord natif/APRES : %d/%d (dont %d GAP permissifs) ; casts illegaux que "
          "master acceptait : %d" % (n_ok, len(rows), n_gap, n_gain))
    res.update({"n_ok": n_ok, "n_rows": len(rows), "n_gap": n_gap, "n_gain": n_gain,
                "cf_moved": moved, "n_heal_refus": len(heal_refus), "n_accept": len(accept),
                "n_mech_wounded_refus": len(mech_wounded)})
    return (n_ok == len(rows) and moved >= 1 and len(heal_refus) >= 1 and len(accept) >= 1
            and len(mech_wounded) >= 1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--only", type=int, default=0, help="1002 | 1037 (defaut : les deux)")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    aids = [a.only] if a.only else sorted(CASES)
    results = []
    for aid in aids:
        results.append(_run(sid, aid, a.seed, a.board))

    ok = True
    print("\n================================ BILAN ================================")
    for res in results:
        ok = report(res) and ok
    print("\n[VERDICT] %s" % ("PASS" if ok else "FAIL"))
    print("[RAW] " + json.dumps(results))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
