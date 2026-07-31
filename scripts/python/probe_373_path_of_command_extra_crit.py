#!/usr/bin/env python
"""probe_373_path_of_command_extra_crit -- l'axe CRIT de `PathOfCommand` (`eldarAutarch`).

LA QUESTION BINAIRE
-------------------
Le bonus de CHANCE DE CRITIQUE accorde par `PathOfCommand_ExtraCrit` (EffectType 0x453 = 1107)
est-il compte par le port comme par le natif, sur un montage ou il MORD ?

CE QUE LE DECOMPILE DIT (et que ce probe confronte, etage par etage)
--------------------------------------------------------------------
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PathOfCommandAbility$$CreateBehaviour` pose DEUX
`ADynamicStatModifierEffect` sur le porteur, par
`IdunBattleLogic.Entities.DSLBehaviors$$AddDynamicStatModifierEffectToOwner(effectType, statType,
turns, isHidden)` :

    AddDynamicStatModifierEffectToOwner( 0x453 = 1107, statType = 0x9 = CritChance, null, false )
  & AddDynamicStatModifierEffectToOwner( 0x458 = 1112, statType = 0x0 = Attack,     null, false )

-> l'axe porte par 1107 est une CHANCE de critique, PAS un multiplicateur de degat critique
   (aucun `statType 0xa = CritDamage` dans ce behaviour). Le jumeau 1112 (axe ATTACK) est deja porte.

`...PathOfCommandExtraCritEffect$$CreateTargetSelector` =
    UnitsWithStatBiggerThan(
        SurroundingFriends(Owner, GetNumberConstant(0x16 = range), unique, OnlyAliveAndTargetable),
        statType = 0x9, statPart = 0x0 = Current, amount = Constant(0), excludingEffect = true )
-> `IdunBattle.Entities.Selectors.UnitsWithStatBiggerThanSelector$$Select` garde l'unite si
   `GetStat(Current) - GetStat(part 5, source = CET effet) > 0` : **un allie a portee dont la chance
   de crit est NULLE n'est PAS cible**. C'est LE gate a faire mordre.

`...PathOfCommandExtraCritEffect$$GetDynamicStatModificationAmount` =
    ConfigVar( TriggeredAbilityType.PathOfCommand = 0x458, EffectSource(Get(effect)),
               AbilityVariableType.extraCritChance = 0x41 )
-> magnitude indexee sur l'`AbilityState` de la SOURCE ; `extraCritChance` n'est PAS dans
   `variablesAffectedByRarityBonus` de `PathOfCommand` -> aucun scaling de rarete.

POURQUOI LE HASARD N'ENTRE PAS DANS CETTE MESURE
------------------------------------------------
On ne mesure AUCUN jet de critique : on mesure la STAT `critChance` elle-meme, que `combatSnapshot`
rend par `IdunBattle.Entities.UnitExtensions$$GetStat` (valeur EXACTE, deterministe), et sa
DECOMPOSITION par source cote port. Aucune esperance, aucun echantillonnage.

COMMENT LE GATE EST FORCE (jamais subi)
---------------------------------------
La normalisation `buildNormalizedBC` remet `CritChance` a 0 sur TOUTES les unites du roster. On
remonte donc la chance de crit d'UN SEUL allie (`--unit-stat <ally>:CritChance=20`) et on laisse
l'autre a 0 : les deux sont a la MEME distance du porteur, seule la chance de crit les separe.

TROIS VOLETS
------------
  A. SEED      -- etat capte APRES atterrissage : la modification live (`statDelta.critChance`) est
                  ATTRIBUEE cote port a la cle de l'effet (et non plus au residu opaque), et le
                  GATE mord (l'allie a crit 0 ne recoit rien alors qu'il recoit bien le +Attack du
                  jumeau 1112 au meme instant).
  B. LANDING   -- deep-strike : la passive est DEFERREE jusqu'a l'atterrissage. On confronte le
                  delta de `critChance` LIVE across un `endturn` au delta OFFLINE across
                  `EndTurnOperation` (mirror `land_deep_strike` + `RefreshEffectsOperation`).
  C. MOBILITE  -- l'allie buffe SORT du rayon 2 puis y REVIENT, en LIVE et en OFFLINE : le natif
                  reverte puis re-applique (`UpdateEffectTargets`), le port doit faire pareil. Ce
                  volet n'est possible QUE parce que la contribution est attribuee (volet A) : une
                  part restee dans le residu opaque `captured` n'est retirable par personne.

  --avant : rejoue les TROIS volets sur le port d'AVANT, reconstitue par RETRAIT de l'inscription
            (`EFFECT_CLASSES["PathOfCommand_ExtraCrit"]` + l'entree d'`ABILITY_INIT_OWNER_EFFECTS`).
            Un lot ou AVANT et APRES rendent la meme chose ne conclut rien : le probe l'exige
            DIFFERENT.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_373_path_of_command_extra_crit.py
    python probe_373_path_of_command_extra_crit.py --seed 777 --board C3_01
    python probe_373_path_of_command_extra_crit.py --avant

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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.entities.stats import StatType, CAPTURED_SOURCE          # noqa: E402
from engine.runner.components import (OwnerComponent, PositionComponent,   # noqa: E402
                                      StatsComponent, UnitComponent)
from engine.runner.messages import MoveUnitMessage                   # noqa: E402
from engine.runner.runner import Runner                              # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402
from engine.runner.operations.turnflow import EndTurnOperation       # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
_seq = itertools.count()

CARRIER = "eldarAutarch"      # HERO du pool (`rl_duel.py build --list-pool`), porteur de PathOfCommand
ALLY_CRIT = "eldarRanger"     # allie a chance de crit > 0 -> CIBLE du selecteur
ALLY_NOCRIT = "eldarFarseer"  # allie a chance de crit == 0 -> NON cible (le gate mord)
FOE = "necroWarden"
A_UNITS = ",".join([FOE] * 3)
SEED = "31337"
BOARD = "MC1_67"
CRIT_SEED = 20                # `--unit-stat <ALLY_CRIT>:CritChance=20`
EFFECT_EXTRA_CRIT = "PathOfCommand_ExtraCrit"
EFFECT_EXTRA_DMG = "PathOfCommand_ExtraDmg"


# --------------------------------------------------------------------------- RPC / montage

def _r(sid, method, body, timeout=60):
    out = _rpc(sid, method, [body], timeout) or {}
    return out.get("result", out) if isinstance(out, dict) else out


def _build(sid, seed: str, board: str) -> int:
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe373-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", "%s,%s,%s" % (CARRIER, ALLY_CRIT, ALLY_NOCRIT),
            "--a-units", A_UNITS,
            "--unit-stat", "%s:CritChance=%d" % (ALLY_CRIT, CRIT_SEED),
            # ENNEMI a chance de crit > 0 : sans lui le noeud `Friends` ne serait exerce par RIEN
            # (les ennemis normalises sont a crit 0, donc exclus par le gate CRIT, pas par le gate
            # d'equipe). Volet D.
            "--unit-stat", "%s:CritChance=%d" % (FOE, CRIT_SEED)]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"])
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-400:])
        time.sleep(10)


def _capture(sid, rid, board=None):
    dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    sn = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    return dv, ob, sn, load_state(dv, ob, sn, board=board)


def _live_crit(sn) -> dict:
    """`GetStat(9, Current)` natif par unite + le delta (part MODIFICATION) que le natif expose."""
    return {int(u["entityId"]): (int((u.get("stats") or {}).get("critChance") or 0),
                                 int((u.get("statDelta") or {}).get("critChance") or 0))
            for u in (sn.get("units") or []) if u.get("entityId") is not None}


def _off_crit(state) -> dict:
    out = {}
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is None or sc.ctx is None:
            continue
        comp = sc.ctx.stats.components.get(int(StatType.CRIT_CHANCE))
        per = dict(comp.modification.per_source) if comp is not None else {}
        out[int(uid)] = (int(sc.ctx.stat(StatType.CRIT_CHANCE)),
                         int(comp.modification.total) if comp is not None else 0, per)
    return out


def _ids(dv) -> dict:
    return {u.get("visualId"): int(u["id"]) for u in (dv.get("units") or []) if u.get("alive")}


def _attr_1107(per: dict) -> int:
    """Part de la modification CritChance attribuee a l'effet 1107 (0 si aucune)."""
    return sum(v for k, v in per.items()
               if isinstance(k, tuple) and EFFECT_EXTRA_CRIT in [x for x in k if isinstance(x, str)])


def _pos(state, uid):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def out_of_ring_candidates(board, carrier_pos, home, occupied, min_d: int = 3) -> list:
    """Tuiles LIBRES et jouables a distance >= `min_d` du PORTEUR, triees par proximite au point de
    depart de l'allie (donc par plausibilite de budget de mouvement). On PILOTE la geometrie : le
    probe ESSAIE les candidates jusqu'a ce que le natif en accepte une, il ne subit pas la
    premiere venue. Liste vide = le board n'en offre aucune -- a DIRE, jamais a taire."""
    out = []
    for pos, t in board.by_coord.items():
        if pos in occupied or not board.walkable(t["id"]):
            continue
        if hexgeo.distance(tuple(carrier_pos), tuple(pos)) < min_d:
            continue
        out.append((hexgeo.distance(tuple(home), tuple(pos)), pos))
    return [p for _, p in sorted(out)]


# --------------------------------------------------------------------------- volets

def run(seed=SEED, board_id=BOARD, sid=None, rid=None, keep=False) -> dict:
    sid = sid or _resolve_session()
    own = rid is None
    rid = rid or _build(sid, seed, board_id)
    rows = {"runner": rid, "seed": seed, "board": board_id}
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None

        # ---- volet B (1re moitie) : ETAT PRE-ATTERRISSAGE -------------------------------
        dv, ob, sn, s0 = _capture(sid, rid, board)
        ids = _ids(dv)
        rows["ids"] = ids
        missing = [v for v in (CARRIER, ALLY_CRIT, ALLY_NOCRIT) if v not in ids]
        if missing:
            raise RuntimeError("unites absentes du build : %s" % missing)
        carrier, a_crit, a_flat = ids[CARRIER], ids[ALLY_CRIT], ids[ALLY_NOCRIT]
        rows["pre"] = {"live": _live_crit(sn), "off": _off_crit(s0),
                       "teleporting_in": bool(s0.effects.has_effect(carrier, name="TeleportStrike_TeleportingIn")),
                       "d_crit": hexgeo.distance(_pos(s0, carrier), _pos(s0, a_crit)),
                       "d_flat": hexgeo.distance(_pos(s0, carrier), _pos(s0, a_flat))}

        # ---- volet B (2e moitie) : ATTERRISSAGE live ET offline -------------------------
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        sn_land = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
        oc = s0.get_entity(carrier).get_component(OwnerComponent)
        s0.current_player_id = oc.player
        EndTurnOperation.execute(s0, advance=False)
        rows["landing"] = {"live": _live_crit(sn_land), "off": _off_crit(s0),
                           "has_1107": bool(s0.effects.has_effect(carrier, name=EFFECT_EXTRA_CRIT)),
                           "has_1112": bool(s0.effects.has_effect(carrier, name=EFFECT_EXTRA_DMG))}

        # ---- volet A : SEED d'un etat DEJA atterri (attribution + gate) -----------------
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)   # rends-moi la main
        dv1, ob1, sn1, s1 = _capture(sid, rid, board)
        rows["seedstate"] = {"live": _live_crit(sn1), "off": _off_crit(s1)}

        # ---- volet C : MOBILITE (sortie du rayon 2, puis retour) ------------------------
        runner = Runner(s1).install_default_handlers(20)
        occupied = {_pos(s1, u) for u in s1.entities}
        home = _pos(s1, a_crit)
        steps = []
        out_tile = None
        cands = out_of_ring_candidates(board, _pos(s1, carrier), home, occupied - {home}) \
            if board is not None else []
        for tile in cands[:12]:
            res = _r(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": a_crit, "to": {"col": tile[0], "row": tile[1]}}}, 60)
            if isinstance(res, dict) and res.get("ok") is False:
                continue                                   # hors budget de mouvement -> candidate suivante
            out_tile = tile
            break
        if out_tile is not None:
            runner.apply(MoveUnitMessage(a_crit, tuple(out_tile)))
            steps.append(("out", _live_crit(_r(sid, "combatSnapshot", {"runnerId": rid}, 90)),
                          _off_crit(s1), out_tile))
            _r(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": a_crit, "to": {"col": home[0], "row": home[1]}}}, 60)
            runner.apply(MoveUnitMessage(a_crit, tuple(home)))
            steps.append(("back", _live_crit(_r(sid, "combatSnapshot", {"runnerId": rid}, 90)),
                          _off_crit(s1), home))
        rows["mobility"] = {"home": home, "out_tile": out_tile,
                            "candidates": len(cands), "steps": steps}

        # ---- volet D : le noeud `Friends` -- un ENNEMI a chance de crit > 0, A PORTEE -----
        # On DEPLACE le porteur vers l'ennemi le plus proche (au lieu d'attendre qu'un ennemi
        # vienne) : c'est la seule facon d'avoir un ennemi DANS le rayon 2 au tour 1.
        foes = [uid for uid, e in s1.entities.items()
                if (e.get_component(OwnerComponent) or None) is not None
                and e.get_component(OwnerComponent).team
                != s1.get_entity(carrier).get_component(OwnerComponent).team]
        foe_tile = None
        chosen_foe = None
        for foe in sorted(foes, key=lambda u: hexgeo.distance(_pos(s1, carrier), _pos(s1, u)) or 99):
            fpos = _pos(s1, foe)
            near = sorted((p for p, t in board.by_coord.items()
                           if p not in {_pos(s1, u) for u in s1.entities}
                           and board.walkable(t["id"])
                           and hexgeo.distance(tuple(fpos), tuple(p)) <= 2),
                          key=lambda p: hexgeo.distance(tuple(_pos(s1, carrier)), tuple(p)))
            for tile in near[:14]:
                res = _r(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": carrier, "to": {"col": tile[0], "row": tile[1]}}}, 60)
                if isinstance(res, dict) and res.get("ok") is False:
                    continue
                foe_tile, chosen_foe = tile, foe
                break
            if foe_tile is not None:
                break
        friends = None
        if foe_tile is not None:
            runner.apply(MoveUnitMessage(carrier, tuple(foe_tile)))
            friends = {"carrier_tile": foe_tile, "foe": chosen_foe,
                       "d_foe": hexgeo.distance(tuple(foe_tile), tuple(_pos(s1, chosen_foe))),
                       "live": _live_crit(_r(sid, "combatSnapshot", {"runnerId": rid}, 90)),
                       "off": _off_crit(s1)}
        rows["friends"] = friends
    finally:
        if own and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    return rows


# --------------------------------------------------------------------------- rapport

def _fmt(uid, live, off):
    lc, ld = live.get(uid, (None, None))
    oc, om, per = off.get(uid, (None, None, {}))
    return "u%-4d live cc=%-4s (mod %+d) | port cc=%-4s (mod %+d) | attr1107=%+d resid=%+d" % (
        uid, lc, ld or 0, oc, om or 0, _attr_1107(per), per.get(CAPTURED_SOURCE, 0))


def report(rows, avant=False) -> int:
    ids = rows["ids"]
    carrier, a_crit, a_flat = ids[CARRIER], ids[ALLY_CRIT], ids[ALLY_NOCRIT]
    tag = "AVANT (inscription RETIREE)" if avant else "APRES"
    print("=== probe 373 -- PathOfCommand_ExtraCrit (1107) -- port %s ===" % tag)
    print("runner=%s seed=%s board=%s" % (rows["runner"], rows["seed"], rows["board"]))
    print("porteur u%d %s | allie CRIT>0 u%d %s | allie CRIT=0 u%d %s"
          % (carrier, CARRIER, a_crit, ALLY_CRIT, a_flat, ALLY_NOCRIT))
    fails = []

    pre = rows["pre"]
    print("\n-- B1 PRE-ATTERRISSAGE (deep-strike, passives DEFERREES) --")
    print("   teleporting_in=%s  d(porteur,%s)=%s  d(porteur,%s)=%s"
          % (pre["teleporting_in"], ALLY_CRIT, pre["d_crit"], ALLY_NOCRIT, pre["d_flat"]))
    for uid in (carrier, a_crit, a_flat):
        print("   " + _fmt(uid, pre["live"], pre["off"]))
    if pre["d_crit"] is None or pre["d_crit"] > 2:
        fails.append("MONTAGE : l'allie CRIT>0 n'est pas dans le rayon 2 du porteur (d=%s)" % pre["d_crit"])
    if pre["d_flat"] is None or pre["d_flat"] > 2:
        fails.append("MONTAGE : l'allie CRIT=0 n'est pas dans le rayon 2 (d=%s) -> le gate ne serait "
                     "pas discrimine par la chance de crit mais par la DISTANCE" % pre["d_flat"])

    land = rows["landing"]
    print("\n-- B2 ATTERRISSAGE (live endturn vs EndTurnOperation offline) --")
    print("   owner-effects poses offline : 1107=%s 1112=%s" % (land["has_1107"], land["has_1112"]))
    for uid in (carrier, a_crit, a_flat):
        print("   " + _fmt(uid, land["live"], land["off"]))
    for uid in (carrier, a_crit, a_flat):
        lc = land["live"].get(uid, (None,))[0]
        oc = land["off"].get(uid, (None,))[0]
        if lc != oc:
            fails.append("B2 u%d : critChance offline %s != live %s apres atterrissage" % (uid, oc, lc))
    if land["live"].get(a_crit, (0, 0))[1] <= 0:
        fails.append("B2 MONTAGE : le natif n'a accorde AUCUN crit a l'allie CRIT>0 -- rien a mesurer")

    seed = rows["seedstate"]
    print("\n-- A SEED d'un etat atterri (attribution + gate) --")
    for uid in (carrier, a_crit, a_flat):
        print("   " + _fmt(uid, seed["live"], seed["off"]))
    for uid in (carrier, a_crit, a_flat):
        lc = seed["live"].get(uid, (None,))[0]
        oc = seed["off"].get(uid, (None,))[0]
        if lc != oc:
            fails.append("A u%d : critChance offline %s != live %s au seed" % (uid, oc, lc))
    if seed["live"].get(a_flat, (0, 0))[1] != 0:
        fails.append("A GATE : le natif accorde du crit a l'allie CRIT=0 -- le gate "
                     "UnitsWithStatBiggerThan ne mord pas, le montage ne prouve rien")
    attr = _attr_1107(seed["off"].get(a_crit, (0, 0, {}))[2])
    print("   attribution 1107 chez u%d = %+d (0 = contribution restee dans le residu OPAQUE, "
          "donc IRRETIRABLE)" % (a_crit, attr))

    mob = rows["mobility"]
    print("\n-- C MOBILITE (sortie du rayon 2 puis retour) --")
    if mob["out_tile"] is None:
        print("   NON CONFRONTE : %d tuiles a distance >= 3 du porteur, aucune ATTEIGNABLE par "
              "l'allie en un deplacement" % mob.get("candidates", 0))
        fails.append("C : montage impossible sur ce board -- rejouer sur un autre --board")
    for label, live, off, tile in mob["steps"]:
        print("   [%s] allie CRIT>0 en %s : %s" % (label, tile, _fmt(a_crit, live, off)))
        lc = live.get(a_crit, (None,))[0]
        oc = off.get(a_crit, (None,))[0]
        if lc != oc:
            fails.append("C [%s] u%d : critChance offline %s != live %s" % (label, a_crit, oc, lc))
    if mob["steps"]:
        out_live = mob["steps"][0][1].get(a_crit, (0, 0))
        if out_live[1] != 0:
            fails.append("C MONTAGE : le natif garde le bonus hors rayon (mod %+d) -- la tuile "
                         "choisie n'est pas assez loin" % out_live[1])

    fr = rows.get("friends")
    print("\n-- D noeud `Friends` (ENNEMI a chance de crit > 0, porteur AMENE a portee) --")
    if not fr:
        print("   NON CONFRONTE : le porteur n'a pu approcher aucun ennemi a <= 2 en un deplacement")
        fails.append("D : le gate `Friends` n'a PAS ete exerce (aucun ennemi amene dans le rayon)")
    else:
        print("   porteur amene en %s, ennemi u%d a d=%s" % (fr["carrier_tile"], fr["foe"], fr["d_foe"]))
        print("   " + _fmt(fr["foe"], fr["live"], fr["off"]))
        if fr["d_foe"] is None or fr["d_foe"] > 2:
            fails.append("D MONTAGE : l'ennemi est a d=%s, hors du rayon -> le gate d'EQUIPE n'est "
                         "pas ce qui le distingue" % fr["d_foe"])
        if fr["live"].get(fr["foe"], (0, 0))[0] <= 0:
            fails.append("D MONTAGE : l'ennemi n'a pas de chance de crit -> il serait exclu par le "
                         "gate CRIT, pas par `Friends` ; le volet ne prouve rien")
        if fr["live"].get(fr["foe"], (0, 0))[1] != 0 or _attr_1107(fr["off"].get(fr["foe"], (0, 0, {}))[2]):
            fails.append("D : un ENNEMI a portee recoit le bonus de crit -> le noeud `Friends` ne mord pas")
        for uid in (carrier, a_crit, a_flat, fr["foe"]):
            lc = fr["live"].get(uid, (None,))[0]
            oc = fr["off"].get(uid, (None,))[0]
            if lc != oc:
                fails.append("D u%d : critChance offline %s != live %s apres le pas du porteur"
                             % (uid, oc, lc))

    print("\n=== %s ===" % ("VERDICT : ACCORD natif/port sur les 4 volets" if not fails
                            else "VERDICT : %d ECART(S)" % len(fails)))
    for f in fails:
        print("   X " + f)
    return 0 if not fails else 1


def _strip_registration():
    """Reconstitue le port d'AVANT par RETRAIT de l'inscription (et de RIEN d'autre)."""
    from engine.entities.effects import factory as F
    F.EFFECT_CLASSES.pop(EFFECT_EXTRA_CRIT, None)
    F.ABILITY_INIT_OWNER_EFFECTS["PathOfCommand"] = [
        n for n in F.ABILITY_INIT_OWNER_EFFECTS.get("PathOfCommand", []) if n != EFFECT_EXTRA_CRIT]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--avant", action="store_true",
                    help="rejoue sur le port d'AVANT (inscription retiree) -- doit DIFFERER")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.avant:
        _strip_registration()
    rows = run(a.seed, a.board)
    if a.json:
        print(json.dumps(rows, default=str, indent=1))
        return 0
    rc = report(rows, avant=a.avant)
    if a.avant:
        # AVANT : on ATTEND des ecarts. Un `--avant` qui rend 0 ecart voudrait dire que
        # l'inscription ne change RIEN -> le lot ne conclurait rien.
        print("\n[--avant] %s" % ("ATTENDU : des ecarts sont apparus -> l'inscription est PORTEUSE"
                                  if rc else
                                  "ANOMALIE : AVANT et APRES rendent la MEME chose -> ce probe ne "
                                  "discrimine rien, le montage est a revoir"))
        return 0 if rc else 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
