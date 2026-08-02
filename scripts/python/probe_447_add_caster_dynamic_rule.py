#!/usr/bin/env python
"""probe_447_add_caster_dynamic_rule -- `AddCasterIfMatchesDynamicRule` (bit 3) et le DEEP STRIKE.

CE QUE CE PROBE MESURE
----------------------
`IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason` -- la TROISIEME cascade du
ciblage, celle que prend l'overload 5 arguments de
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` quand une ability SELF-CASTEE
(`options+0x00 != 0`) est castee SUR SON PROPRE CASTER. Sa chaine est un `if / else if / else`,
donc l'ORDRE des branches tranche :

    if ((char)rules < 0) return valide;          # bit 7  AddCaster -> court-circuit
    if (rules & 0x8) {                           # bit 3  AddCasterIfMatchesDynamicRule
        r = options[+0x30].Invoke(caster, casterTiles); if (r) return broken(r);
    } else if (rules & 0x400000) { ... }         # bit 22 (0 porteur au registre)
    else if (options+0x00 == 0 && !(rules & 0x800)) { ... }   # bit 15 CasterIsPossibleTarget
    else { if (GetValidTargets(...).AllTargets.Count == 0) return broken(0x800); }

Le porteur unique du bit 3 au registre est **1115 `FearOfTheUnseen`** (`tyranDeathleaper`), dont la
delegue `FearOfTheUnseenAbility$$GetDynamicInvalidCasterReason` rend `IsTeleporting(caster) ? 4 : 0`
-- soit `TargetingRule.CasterMatchesDynamicRule`. C'est litteralement le « and is not in Deep
Strike » du texte i2 de l'ability. Avant #447, `get_caster_not_added_reason` rendait `0` :
le port ACCEPTAIT un cast que le natif REFUSE.

⚠ LE CANAL DE MESURE MENT SI ON PREND `abilityReason` (mesure de ce probe, etape 0)
------------------------------------------------------------------------------------
`abilityReason` passe par `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`, qui
COURT-CIRCUITE sur `ActiveAbility$$get_CanCurrentlyBeUsed` AVANT toute cascade et rend alors le
litteral `1` (`ValidRequest`). Or 1115 porte `initialCooldownTurns = 1` : au tour de deploiement --
le SEUL tour ou le Deep Strike du trait `TeleportStrike` est actif -- ce canal publie `0x1` quel que
soit le verdict de ciblage. Un lecteur naif y verrait « ability indisponible » et conclurait que la
regle n'est pas confrontable.

LE CANAL JUSTE est `abilityTargets.fromHere`, dont le chemin natif
`IdunBattle.Core.Services.AttackQuery$$GetValidTargets` ne gate QUE sur `IsAlreadyUsedThisTurn`
(relu au decompile : pas de `get_CanCurrentlyBeUsed`). Il est BINAIRE (le caster est dans la liste,
ou il n'y est pas), et l'etape 0 du probe VERIFIE son pouvoir discriminant au lieu de le supposer.

ATTRIBUTION DU CANAL -- pourquoi `fromHere` mesure CETTE regle et pas une autre
------------------------------------------------------------------------------
`TargetingQuery$$GetValidTargets` n'appelle PAS `GetCasterNotAddedReason` : il RE-IMPLEMENTE l'ajout
du caster, dans le meme ordre (bit 7, puis `isSelfCasting || bit 11` SI la liste est deja non vide,
puis bit 22, puis bit 3). Pour 1115 le masque est `0x18` et la portee est `RANGE_SELF` :
`GetPossibleTargetsForOptions` rend **zero** cible, donc l'etage `isSelfCasting` ne peut rien
ajouter (`targets.Count > 0` est faux) et le SEUL chemin d'ajout restant est la branche bit 3. Le
probe imprime `targets`/`fromHere` cote a cote : `targets == 0` dans les deux regimes est ce qui
rend l'attribution valide, et une regression sur ce point se verrait.

LES TROIS REGIMES CONFRONTES AU NATIF
-------------------------------------
  R1  deploiement, caster NON bouge, `TeleportStrike_TeleportingIn` ACTIF
      -> natif `fromHere = 0` (REFUS)  ; port attendu `CasterMatchesDynamicRule` (0x4)
  R2  apres UN round complet, effet EXPIRE, caster non bouge
      -> natif `fromHere = 1` (le caster) ; port attendu `0`
  R3  meme etat que R2 mais le caster A BOUGE
      -> natif `fromHere = 0` ; port attendu `CasterHasNotMoved` (0x10) -- PREUVE D'ORDRE : la
         cascade CASTER (`GetInvalidCasterReason`) tourne AVANT `GetCasterNotAddedReason`, donc
         c'est la regle ANTERIEURE qui doit etre rendue, pas la notre.

R1 EST le regime discriminant, et il n'est PAS un accident de spawn : le Deathleaper porte le trait
`TeleportStrike`, donc il arrive en Deep Strike a chaque deploiement.

CONTRE-EPREUVES (port seul -- chacune verifie d'abord que sa mutation A MORDU)
-----------------------------------------------------------------------------
  CE1  masque prive du bit 3 (contrefactuel de CHAMP) -> le port doit ACCEPTER en R1.
       C'est l'etat de `master` : la mesure de la degradation permissive fermee.
  CE2  masque avec `AddCaster` (bit 7) OR-e -> le court-circuit ANTERIEUR doit gagner : le port
       ACCEPTE en R1 malgre le Deep Strike. Preuve d'ORDRE intra-etage.
  CE3  delegue neutralisee (la sous-classe rend 0) -> le port ACCEPTE en R1. Prouve que c'est la
       DELEGUE qui decide, pas le bit -- le bit n'est qu'un aiguillage.
  CE4  R1 + flag `Moved` pose OFFLINE -> le port doit rendre `0x10`, pas `0x4`. Meme preuve d'ordre
       que R3, dans un regime que le live ne peut pas produire (un move fait EXPIRER le Deep
       Strike : mesure -- l'effet disparait des que l'unite agit).

GENERALISATION (`--generalize`)
-------------------------------
Second couple (board, seed) ET attaquant d'une AUTRE faction : `darkaCompanion` (Dark Angels,
« Forcas ») porte **1189 `CalibaniteGreatsword`**, masque `0x80` = `AddCaster` seul, self-cast --
donc l'AUTRE branche portee de la meme fonction, celle du court-circuit. Le natif doit l'ACCEPTER
(`fromHere` contient le caster) et le port rendre `0`.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_447_add_caster_dynamic_rule.py
    python probe_447_add_caster_dynamic_rule.py --seed 31337 --board C3_01 --generalize

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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import (                      # noqa: E402
    get_invalid_target_reason, is_invalid_target)
from engine.runner.abilities.targeting_rule import TargetingRule as TR    # noqa: E402
from engine.runner.components import is_teleporting, set_moved_flag  # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
_seq = itertools.count()

FEAR = 1115                      # `FearOfTheUnseen` -- unique porteur du bit 3 au registre
GREATSWORD = 1189                # `CalibaniteGreatsword` -- masque 0x80 = `AddCaster` seul
CASTER_VIS = "tyranDeathleaper"
GEN_CASTER_VIS = "darkaCompanion"


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _act(sid, rid, action, timeout=90):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action}, timeout)


def _by_vis(dec, vis):
    for u in (dec.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return u
    return None


def _targets(sid, rid, uid, aid):
    """`abilityTargets` reduit a `(targets, fromHere)` pour UNE ability. `fromHere` = la legalite
    EXACTE du cast immediat (`AttackQuery$$GetValidTargets` depuis la tuile courante)."""
    out = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": int(uid),
                                     "abilityType": int(aid)}, 90)
    for u in (out.get("units") or []):
        if int(u.get("unitId", -1)) != int(uid):
            continue
        for a in (u.get("abilities") or []):
            if int(a.get("abilityId", -1)) == int(aid):
                return int(a.get("targetCount") or 0), int(a.get("fromHereCount") or 0), \
                    [int(t.get("targetId")) for t in (a.get("fromHere") or [])
                     if t.get("targetId") is not None]
    return None, None, []


def _reason(sid, rid, cid, aid, tid):
    """`abilityReason` -- gardé UNIQUEMENT pour l'etape 0 (montrer que ce canal NE PEUT PAS
    exprimer le refus tant que l'ability est en cooldown initial)."""
    return _r(sid, "abilityReason", {"runnerId": rid, "casterId": int(cid),
                                     "abilityType": int(aid), "targetId": int(tid)}, 60)


def _build(sid, seed, board, p_units, a_units):
    state = ROOT / "logs" / ("_probe447-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", ",".join(p_units), "--a-units", a_units]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if ("runner cap reached" not in out and "runner creation paused" not in out) \
                or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-600:])
        time.sleep(10)


def _capture(sid, rid):
    dv = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    return dv, load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))


# --------------------------------------------------------------------------- variantes de CHAMP

def _variant(aid, rules_or=0, rules_and_not=0, kill_delegate=False):
    """La MEME classe d'ability avec un masque mute (et, au besoin, sa delegue neutralisee).
    Contrefactuel de CHAMP : on ne touche jamais au code teste."""
    klass = ABILITY_CLASSES[aid]
    base = klass.TARGETING_OPTIONS
    rules = (int(base.rules) | int(rules_or)) & ~int(rules_and_not)

    if kill_delegate:
        class _V(klass):                                              # type: ignore[misc, valid-type]
            __slots__ = ()
            TARGETING_OPTIONS = _replace(base, rules=rules)

            def get_dynamic_invalid_caster_reason(self, state, caster_id):
                return 0
    else:
        class _V(klass):                                              # type: ignore[misc, valid-type]
            __slots__ = ()
            TARGETING_OPTIONS = _replace(base, rules=rules)
    return _V()


# --------------------------------------------------------------------------- etapes

def _row(tag, nat_targets, nat_from, port, expect_nat_refus, expect_port):
    nat_refus = (nat_from == 0)
    ok = (nat_refus == expect_nat_refus) and (int(port) == int(expect_port))
    print("  %-46s natif[targets=%s fromHere=%s -> %s]  port=%s (attendu %s)  %s"
          % (tag, nat_targets, nat_from, "REFUS" if nat_refus else "VALIDE",
             hex(int(port)), hex(int(expect_port)), "OK" if ok else "MISMATCH"))
    return ok


def run_main(sid, seed, board, data=None):
    print("=== #447 -- AddCasterIfMatchesDynamicRule (bit 3) / DEEP STRIKE ==================")
    print("board=%s seed=%s caster=%s ability=%d" % (board, seed, CASTER_VIS, FEAR))
    data = {} if data is None else data
    data.update({"board": board, "seed": seed, "caster_vis": CASTER_VIS, "ability": FEAR})
    rid, state_file = _build(sid, seed, board,
                             [CASTER_VIS, "tyranNeurothrope"], "necroWarden,orksRuntherd")
    ok = True
    try:
        dv, st = _capture(sid, rid)
        cu = _by_vis(dv, CASTER_VIS)
        if cu is None:
            raise RuntimeError("%s absent du decisionView" % CASTER_VIS)
        cid = int(cu["id"])
        ab = ABILITY_CLASSES[FEAR]()

        # --- etape 0 : LE CANAL. `abilityReason` sait-il exprimer ce refus ? ------------------
        rr = _reason(sid, rid, cid, FEAR, cid) or {}
        tr = (rr.get("targetReason") or {})
        stt = (rr.get("abilityState") or {})
        print("")
        print("[etape 0] canal `abilityReason` en R1 : targetReason=%s cooldown=%s"
              % (tr.get("hex"), stt.get("cooldown")))
        muet = (str(tr.get("hex") or "").rstrip("0").endswith("x") is False
                and int(str(tr.get("hex") or "0x0"), 16) == 1)
        print("           -> %s" % ("MUET (0x1 ValidRequest = court-circuit cooldown de "
                                    "AttackQuery) : ce canal NE PEUT PAS trancher, on prend "
                                    "abilityTargets" if muet else
                                    "ce canal repond -- lire la valeur ci-dessus"))

        # --- R1 : Deep Strike actif ----------------------------------------------------------
        tele = is_teleporting(st, cid)
        print("")
        print("[R1] deploiement -- is_teleporting(port)=%s" % tele)
        if not tele:
            print("  ECHEC DE MONTAGE : le caster n'est pas en Deep Strike au deploiement.")
            return False
        data["canal_abilityreason"] = {"hex": tr.get("hex"), "cooldown": stt.get("cooldown"),
                                       "muet": bool(muet)}
        nt, nf, _ = _targets(sid, rid, cid, FEAR)
        p1 = int(is_invalid_target(st, cid, cid, ab) or 0)
        data["R1"] = {"teleporting": bool(tele), "nat_targets": nt, "nat_fromHere": nf, "port": p1}
        ok &= _row("R1 Deep Strike, non bouge", nt, nf, p1, True, int(TR.CasterMatchesDynamicRule))
        if nt not in (0, None):
            print("  [!] ATTRIBUTION : targets != 0 -- l'etage `isSelfCasting` de GetValidTargets "
                  "pourrait ajouter le caster ; la mesure ne serait plus attribuable au bit 3.")
            ok = False

        # --- contre-epreuves de CHAMP, dans le regime R1 --------------------------------------
        ce1 = int(get_invalid_target_reason(
            st, cid, cid, _variant(FEAR, rules_and_not=int(TR.AddCasterIfMatchesDynamicRule))) or 0)
        ce2 = int(get_invalid_target_reason(
            st, cid, cid, _variant(FEAR, rules_or=int(TR.AddCaster))) or 0)
        ce3 = int(get_invalid_target_reason(
            st, cid, cid, _variant(FEAR, kill_delegate=True)) or 0)
        data["CE"] = {"ce1_sans_bit3": ce1, "ce2_addcaster": ce2, "ce3_delegue_neutre": ce3}
        for tag, got in (("CE1 masque SANS bit 3 (= master)", ce1),
                         ("CE2 masque + AddCaster (court-circuit)", ce2),
                         ("CE3 delegue neutralisee", ce3)):
            good = (got == 0)
            ok &= good
            print("  %-46s port=%s (attendu 0x0)  %s"
                  % (tag, hex(got), "OK -- la mutation MORD" if good else "MISMATCH"))

        # --- CE4 : ordre OFFLINE (regime que le live ne produit pas) ---------------------------
        set_moved_flag(st, cid)
        ce4 = int(is_invalid_target(st, cid, cid, ab) or 0)
        data["CE"]["ce4_ordre_moved"] = ce4
        good = (ce4 == int(TR.CasterHasNotMoved))
        ok &= good
        print("  %-46s port=%s (attendu %s)  %s"
              % ("CE4 R1 + flag Moved (ordre)", hex(ce4), hex(int(TR.CasterHasNotMoved)),
                 "OK -- la regle ANTERIEURE gagne" if good else "MISMATCH"))

        # --- R2 : un round plus tard, effet expire --------------------------------------------
        _act(sid, rid, {"kind": "endturn"})
        _act(sid, rid, {"kind": "endturn"})
        dv, st = _capture(sid, rid)
        cu = _by_vis(dv, CASTER_VIS)
        cid = int(cu["id"])
        tele2 = is_teleporting(st, cid)
        print("")
        print("[R2] apres 1 round -- is_teleporting(port)=%s" % tele2)
        nt, nf, fh = _targets(sid, rid, cid, FEAR)
        p2 = int(is_invalid_target(st, cid, cid, ab) or 0)
        data["R2"] = {"teleporting": bool(tele2), "nat_targets": nt, "nat_fromHere": nf,
                      "port": p2, "fromHere_ids": fh, "caster": cid}
        ok &= _row("R2 hors Deep Strike, non bouge", nt, nf, p2, False, 0)
        if nf and fh != [cid]:
            print("  [!] ATTRIBUTION : fromHere=%s (attendu [%d] = le caster)" % (fh, cid))
            ok = False

        # --- R3 : le caster a bouge (preuve d'ORDRE confrontee au natif) ----------------------
        tiles = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        dest = None
        for m in (tiles.get("units") or []):
            if int(m.get("unitId", -1)) == cid:
                for t in (m.get("tiles") or []):
                    if t.get("col") is not None:
                        dest = (int(t["col"]), int(t["row"]))
                        break
        if dest is None:
            print("[R3] AUCUNE tuile de deplacement -- regime NON CONFRONTE")
            data["R3"] = None
        else:
            _act(sid, rid, {"kind": "move", "unitId": cid, "to": {"col": dest[0], "row": dest[1]}})
            dv, st = _capture(sid, rid)
            cid = int(_by_vis(dv, CASTER_VIS)["id"])
            nt, nf, _ = _targets(sid, rid, cid, FEAR)
            p3 = int(is_invalid_target(st, cid, cid, ab) or 0)
            print("")
            print("[R3] apres un move vers %s" % (dest,))
            data["R3"] = {"dest": list(dest), "nat_targets": nt, "nat_fromHere": nf, "port": p3}
            ok &= _row("R3 hors Deep Strike, A BOUGE", nt, nf, p3, True,
                       int(TR.CasterHasNotMoved))
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
        state_file.unlink(missing_ok=True)
    data["ok"] = bool(ok)
    return ok


def run_generalize(sid, seed, board, data=None):
    """Second couple (board, seed) ET attaquant d'une AUTRE faction : la branche `AddCaster`.

    ⚠ CE QUE CE BLOC PROUVE, ET CE QU'IL NE PROUVE PAS. Il n'est PAS discriminant sur la valeur
    (le port rendait deja `0` avant #447 -- son `get_caster_not_added_reason` etait un `return 0`
    inconditionnel) : c'est une NON-REGRESSION, la face RESTRICTIVE. Elle a sa valeur propre --
    un port trop strict casserait ce self-cast legitime -- et elle couvre l'AUTRE branche portee
    sur un autre couple (board, seed) et une autre faction."""
    data = {} if data is None else data
    print("")
    print("=== GENERALISATION -- branche AddCaster (bit 7), autre faction ==================")
    print("board=%s seed=%s caster=%s ability=%d" % (board, seed, GEN_CASTER_VIS, GREATSWORD))
    rid, state_file = _build(sid, seed, board,
                             [GEN_CASTER_VIS, "darkaAsmodai"], "necroWarden,orksRuntherd")
    ok = True
    try:
        dv, st = _capture(sid, rid)
        cu = _by_vis(dv, GEN_CASTER_VIS)
        if cu is None:
            raise RuntimeError("%s absent du decisionView" % GEN_CASTER_VIS)
        cid = int(cu["id"])
        ab = ABILITY_CLASSES[GREATSWORD]()
        nt, nf, fh = _targets(sid, rid, cid, GREATSWORD)
        port = int(is_invalid_target(st, cid, cid, ab) or 0)
        data["G1"] = {"board": board, "seed": seed, "caster_vis": GEN_CASTER_VIS,
                      "ability": GREATSWORD, "nat_targets": nt, "nat_fromHere": nf,
                      "port": port, "caster": cid, "fromHere_ids": fh}
        ok &= _row("G1 AddCaster -> court-circuit", nt, nf, port, False, 0)
        if nf and cid not in fh:
            print("  [!] ATTRIBUTION : le caster (%d) n'est pas dans fromHere=%s" % (cid, fh))
            ok = False
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
        state_file.unlink(missing_ok=True)
    return ok


def run_blast_radius(data=None):
    """RAYON DE SOUFFLE, entierement OFFLINE et DERIVE du registre -- la justification chiffree du
    choix de cette regle, et la garantie qu'un port TROP STRICT ne casse pas des casts legitimes.

    Deux comptes, aucun saisi :
      * masques du registre qui ARMENT la regle = ceux qui posent le bit 3 (la regle est armee par
        SON PROPRE bit ici -- verifie au decompile de `GetCasterNotAddedReason`, pas par un
        predicat tiers comme le TAUNT ou `TargetIsNotSteppable`) ;
      * masques ou le port peut desormais RENDRE un refus = ceux qui posent le bit 3 ET dont la
        classe SURCHARGE `get_dynamic_invalid_caster_reason` (le defaut de `ActiveAbility` rend 0,
        donc une ability qui pose le bit sans surcharger reste permissive, comme le natif l'est
        quand sa delegue rend 0).

    Le second compte EST le rayon de souffle du fix. Tout masque hors de cet ensemble voit
    `get_caster_not_added_reason` rendre `0` exactement comme avant."""
    from engine.runner.abilities.base import ActiveAbility
    print("")
    print("=== RAYON DE SOUFFLE (offline, derive du registre) ==============================")
    armes, mordants = [], []
    for aid, klass in sorted(ABILITY_CLASSES.items()):
        opts = getattr(klass, "TARGETING_OPTIONS", None)
        if opts is None or not opts.has(TR.AddCasterIfMatchesDynamicRule):
            continue
        armes.append(aid)
        if klass.get_dynamic_invalid_caster_reason is not ActiveAbility.get_dynamic_invalid_caster_reason:
            mordants.append(aid)
    total = sum(1 for k in ABILITY_CLASSES.values()
                if getattr(k, "TARGETING_OPTIONS", None) is not None)
    print("  masques lisibles au registre                      : %d" % total)
    print("  ... qui ARMENT AddCasterIfMatchesDynamicRule      : %d %s" % (len(armes), armes))
    print("  ... dont la delegue CASTER est portee (= le rayon): %d %s" % (len(mordants), mordants))
    ok = (armes == mordants) and len(mordants) >= 1
    print("  -> %s" % ("OK : le fix ne peut refuser que chez ces masques-la"
                       if ok else "A REGARDER : un masque arme sans delegue portee reste permissif"))
    if data is not None:
        data["blast"] = {"total_masques": total, "armes": armes, "rayon": mordants}
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--generalize", action="store_true",
                    help="joue AUSSI la branche AddCaster sur un autre caster/board/seed")
    ap.add_argument("--gen-seed", type=int, default=31337)
    ap.add_argument("--gen-board", default="C3_01")
    ap.add_argument("--offline", action="store_true",
                    help="n'execute QUE le rayon de souffle (aucun runner, aucune session)")
    args = ap.parse_args(argv)

    data = {"blast": None}
    if args.offline:
        ok = run_blast_radius(data)
        print("")
        print("[RAW] " + json.dumps(data, sort_keys=True))
        print("VERDICT: %s" % ("PASS" if ok else "FAIL"))
        return 0 if ok else 1

    sid = _resolve_session()
    ok = run_blast_radius(data)
    ok = run_main(sid, args.seed, args.board, data) and ok
    if args.generalize:
        ok = run_generalize(sid, args.gen_seed, args.gen_board, data) and ok
    print("")
    print("[RAW] " + json.dumps(data, sort_keys=True))
    print("VERDICT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
