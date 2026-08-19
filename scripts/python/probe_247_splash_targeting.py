#!/usr/bin/env python
"""probe_247_splash_targeting -- ARMEMENT du gate de cible des SIX abilities du module `splash`.

CE QUE CE PROBE MESURE
----------------------
Les six abilities du module `engine/runner/abilities/loki/splash.py` entraient dans
`ABILITY_CLASSES` SANS `TARGETING_OPTIONS` -> `get_invalid_target_reason` commence par
`options = getattr(ability, "TARGETING_OPTIONS", None)` et rend 0 immediatement : AUCUN gate.
Degradation PERMISSIVE (ni erreur ni crash), donc invisible en self-play.

TROIS FORMES DE CTOR pour SIX abilities d'un MEME module -- lues une par une, jamais deduites :

  1000 GauntletsOfUltramar  FACTORY NOMMEE  `TargetingOptions$$SelfCastIfEnemyInCustomRangeOptions(2)`
                            -> isSelfCasting=1, range=CustomRange(2), forceMelee=RangedBool.False,
                               rules=0x4000 ; `AActiveAbility..ctor(...,2,0)` = Others
  1051 Stikkbomb            PRESET+FLAGS  preset `statics+0x140` | 0x2000000 -> 0x2004002
                            range=RANGE_FROM_CONFIG(2), forceMelee=RangedBool.True
  1065 ScythingTalons       PRESET COPIE  preset `statics+0x40` -> 0x4000
                            range=RANGE_ADJACENT, forceMelee=RangedBool.False
  1078 Fragstorm            PRESET+FLAGS  preset `statics+0x180` | 0x2000000 -> 0x2004002
                            range=RANGE_FROM_CONFIG(2), forceMelee=RangedBool.False  <- DIFFERE de 1051
  1098 PlasmaGrenade        PRESET+FLAGS  preset `statics+0x140` | 0x2000000 -> 0x2004002
                            range=RANGE_FROM_CONFIG(2), forceMelee=RangedBool.True
  1105 CrushingClaws        PRESET COPIE  preset `statics+0x40` -> 0x4000
                            range=RANGE_ADJACENT, forceMelee=RangedBool.False

Le contraste 1051/1098 (preset +0x140) vs 1078 (preset +0x180) est le coeur du cas : les deux blocs
de `IdunBattle.Core.Services.TargetingOptions$$.cctor` ne different QUE par `<preset>+0x20`
(`forceMeleeTarget`). Recopier la voisine aurait donne le bon `rules` et le MAUVAIS volet portee.

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` appelle le natif
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`. Le probe rejoue le gate OFFLINE
sur le MEME etat fige, en CINQ versions par ability :
  * APRES     = l'ability du registre (masque pose par cette tranche) ;
  * AVANT     = la MEME classe avec `TARGETING_OPTIONS = None` -- l'etat de `master` ;
  * sansRules = `rules = 0` (contrefactuel du champ RULES) ;
  * sansRange = `range = None` (contrefactuel du champ PORTEE) ;
  * fmtFlip   = `force_melee_target` bascule True<->False (contrefactuel du 3e champ).
Pour 1000 s'ajoute `sansSelf` (`self_cast = False`) : sans l'aiguillage self-cast, le port
appliquerait le filtre statique au cast sur SOI et refuserait `TargetIsEnemy` un cast que le natif
juge par `GetCasterNotAddedReason`.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_247_splash_targeting.py --group heroes
    python probe_247_splash_targeting.py --group heroes --seed 31337 --board C4_09
    python probe_247_splash_targeting.py --group summons

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

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import (RANGED_BOOL_FALSE,    # noqa: E402
                                               RANGED_BOOL_TRUE,
                                               get_invalid_caster_reason,
                                               get_invalid_target_reason)
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

FOE_VIS = "necroWarden"
_seq = itertools.count()

# --- LES DEUX MONTAGES ---------------------------------------------------------------------------
# `heroes`  : les trois porteurs LINEUP du module, tous dans `rl_duel build --list-pool`, mesures
#             dans le MEME etat fige (le socle -- runner, geometrie, oracle -- est mutualise).
# `summons` : les deux porteurs SUMMON joignables par leur SUMMONER, lui-meme au pool
#             (`orksWarboss` caste Waaagh 1058 -> `orksOrkBoys` ; `tyranWingedPrime` caste
#             AlphaWarrior 1112 -> `tyranSmnWarrior`). Un summon n'a pas a figurer au pool : on
#             spawne son summoner.
# ⚠ QUALIFIER LES ABILITIES, pas se fier au nom : `templAggressor` (le heros Aggressor, au pool)
#   NE porte PAS `Fragstorm` (1078) mais `FragstormGrenadeLauncher` (1048) -- deux
#   `ActiveAbilityType` distincts dont le nom se ressemble. Les porteurs REELS de 1078 sont
#   `templSmnAggressor` (summon) et `templNpc4Aggressor` (npc) ; le seul poseur du summon est le
#   PowerUp `PowerUp_SummonSpawn_templSmnAggressor`, qu'aucune unite du pool ne caste. Meme
#   situation pour 1098 (`eldarSmnGuardian`, AUCUN summoner au gameconfig). Ces deux-la exigent le
#   catalogue injecte (`catalog_inject.write_augmented_seed_bc`), cf. la fiche du cas.
GROUPS = {
    "heroes": {
        "p_units": ["ultraCalgar", "tyranTyrantGuard"],
        "casters": [("ultraCalgar", 1000), ("tyranTyrantGuard", 1105)],
        "summon_casts": [],
    },
    "summons": {
        "p_units": ["orksWarboss", "tyranWingedPrime"],
        "casters": [("orksOrkBoys", 1051), ("tyranSmnWarrior", 1065)],
        # (visualId du summoner, ActiveAbilityType du summon) -- castes AVANT la mesure
        "summon_casts": [("orksWarboss", 1058), ("tyranWingedPrime", 1112)],
    },
}
TOURS_DE_CHAUFFE = 6               # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(sid, seed, board, p_units):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe247-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    a_units = ",".join([FOE_VIS] * 4)
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
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-500:])
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


def _wait_movable(sid, rid, unit_id, maxit=4):
    """Tuiles de deplacement de `unit_id`, en enchainant les `endturn` jusqu'a ce que son camp ait la
    main. On ne COMPTE pas les `endturn` : quand toutes les unites d'un camp ont agi le moteur
    bascule DEJA seul, et un `endturn` de plus decalerait la parite."""
    for _ in range(maxit):
        t = _movable(sid, rid, unit_id)
        if t:
            return t
        _act(sid, rid, {"kind": "endturn"}, 60)
    return []


def _step_toward(sid, rid, unit_id, goal_pos, want):
    """Rapproche (ou eloigne) `unit_id` vers la distance `want` de `goal_pos`, dans la limite de son
    deplacement du tour."""
    tiles = _wait_movable(sid, rid, unit_id)
    if not tiles:
        return False
    best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, goal_pos) - want), t))
    _act(sid, rid, {"kind": "move", "unitId": unit_id,
                    "to": {"col": best[0], "row": best[1]}}, 90)
    return True


# --------------------------------------------------------------------------- montage geometrique

def _drive_spectrum(sid, rid, anchor_vis, wants=(1, 2, 3, 5), rounds=10):
    """Monte le SPECTRE DE DISTANCES autour du caster d'ancrage : un ennemi a chaque distance de
    `wants`. C'est ce spectre qui separe les trois regimes de portee du lot --
    `RANGE_ADJACENT` (1065/1105 : refus des d>=2), `RANGE_FROM_CONFIG` = 2 (1051/1078/1098 : refus
    des d>=3) et `CustomRange(2)` (1000) -- ET qui place les CAS LIMITES exactement aux seuils
    (d=1 vs d=2 pour l'adjacence, d=2 vs d=3 pour la portee 2).

    On DEPLACE les deux camps (`applyAction` ne verifie pas la propriete du `unitId`, runner.md §4)
    plutot que subir les spawns. Runner `--no-ai` : rien ne bouge tout seul."""
    for it in range(rounds):
        d = _dv(sid, rid)
        anchor = _by_vis(d, anchor_vis)
        if anchor is None:
            raise RuntimeError("ancre %s absente ou morte" % anchor_vis)
        ap = _pos(anchor)
        foes = sorted((u for u in (d.get("units") or [])
                       if u.get("alive") and u.get("owner") != anchor.get("owner")),
                      key=lambda u: int(u["id"]))
        if not foes:
            raise RuntimeError("aucun ennemi vivant")
        got = [hexgeo.distance(ap, _pos(f)) for f in foes]
        print("  [drive %d] ancre=%s@%s distances=%s (cibles=%s)" % (it, anchor_vis, ap, got,
                                                                     list(wants)))
        if all(abs(got[i] - wants[i]) == 0 for i in range(min(len(got), len(wants)))):
            return
        moved = False
        for i, f in enumerate(foes[:len(wants)]):
            if got[i] != wants[i]:
                moved = _step_toward(sid, rid, int(f["id"]), ap, wants[i]) or moved
        if not moved:
            _act(sid, rid, {"kind": "endturn"}, 60)
    print("  [drive] spectre partiel accepte (les distances REELLES sont mesurees, pas supposees)")


def _bring_to_contact(sid, rid, others, rounds=3):
    """Amene CHAQUE autre caster au contact d'un ennemi. Le spectre de `_drive_spectrum` est monte
    autour d'UNE ancre ; un second caster place ailleurs n'aurait alors AUCUNE ligne acceptee (0x0),
    et sans ligne acceptee la mesure ne distingue pas « le masque refuse » de « l'ability est
    indisponible ». MESURE de cette exacte lacune : sur `C4_09`/31337, `tyranTyrantGuard` n'avait
    aucun ennemi a d=1 -- 6 refus sur 6, accord parfait mais garde-fou non rempli."""
    for _ in range(rounds):
        d = _dv(sid, rid)
        todo = []
        for vis in others:
            u = _by_vis(d, vis)
            if u is None:
                continue
            foes = [f for f in (d.get("units") or [])
                    if f.get("alive") and f.get("owner") != u.get("owner")]
            if not foes:
                continue
            near = min(foes, key=lambda f: hexgeo.distance(_pos(u), _pos(f)))
            if hexgeo.distance(_pos(u), _pos(near)) > 1:
                todo.append((int(u["id"]), _pos(near)))
        if not todo:
            return
        for uid, goal in todo:
            _step_toward(sid, rid, uid, goal, 1)


def _give_turn_to(sid, rid, vis, maxit=8):
    """Rend la main au camp de `vis` (chaine d'`endturn`, runner `--no-ai`)."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        u = _by_vis(d, vis)
        if u is not None and u.get("ctrl"):
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


def _find_carrier(sid, rid, dv, vis, aid):
    """Le PORTEUR de l'ability sur le plateau. On tente d'abord le `visualId` attendu, puis -- et
    c'est le point qui compte pour un SUMMON -- on demande au NATIF quelle unite possede l'ability :
    `abilityReason(caster, abilityType)` sans `targetId` rend `abilityState.usable`, qui n'est vrai
    que si `ActiveAbilityComponent.GetOrNull(caster, abilityType)` a resolu. Le `visualId` d'une
    unite invoquee n'est PAS forcement l'id gameconfig du summon -- s'y fier ferait conclure a tort
    « porteur absent » alors que le spawn a bien eu lieu."""
    u = _by_vis(dv, vis)
    if u is not None:
        return u
    for cand in sorted((x for x in (dv.get("units") or []) if x.get("alive")),
                       key=lambda x: int(x["id"])):
        st = ((_nat(sid, rid, int(cand["id"]), aid) or {}).get("abilityState") or {})
        if st.get("usable"):
            print("  [porteur] %d resolu sur u%s(%s) (visualId attendu: %s)"
                  % (aid, cand["id"], cand.get("visualId"), vis))
            return cand
    return None


def _legal_targets(sid, rid, unit_id, aid):
    """Cibles LEGALES rendues par le natif (`abilityTargets`), au format
    `units[].abilities[].fromHere[] = {kind, tile:{col,row}}` ou `{kind, unitId}`. `fromHere` =
    legalite EXACTE du cast immediat (sans bouger) -- c'est ce qu'il nous faut."""
    tg = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": int(unit_id),
                                    "abilityType": int(aid)}, 90)
    out = []
    for un in ((tg or {}).get("units") or []):
        for ab in (un.get("abilities") or []):
            if int(ab.get("abilityId") or 0) != int(aid):
                continue
            for t in (ab.get("fromHere") or []):
                tile = t.get("tile") or {}
                if tile.get("col") is not None:
                    out.append({"col": tile["col"], "row": tile["row"]})
                elif t.get("unitId") is not None:
                    out.append({"id": int(t["unitId"])})
    return out


def _cast_summons(sid, rid, summon_casts):
    """Fait CASTER a chaque summoner son ability d'invocation, pour amener les porteurs SUMMON en
    bataille (`Waaagh` 1058 -> `orksOrkBoys` ; `AlphaWarrior` 1057 -> `tyranSmnWarrior`). Le summon
    apparait dans l'equipe du summoner -- c'est le chemin de confrontabilite d'un carrier summon,
    qui n'a pas a figurer dans `build --list-pool`."""
    for vis, aid in summon_casts:
        _give_turn_to(sid, rid, vis)
        d = _dv(sid, rid)
        u = _by_vis(d, vis)
        if u is None:
            print("  [summon] %s absent -> cast %d impossible" % (vis, aid))
            continue
        # La cible NE PEUT PAS etre devinee : Waaagh (1058) et AlphaWarrior (1112) posent
        # `TargetIsTile`, donc un `targetId = casterId` est REFUSE par le gate -- observable
        # `mutated=false, actionConsumed=false, 2 evenements, groupe 12 User_UseAbility` (la
        # signature de refus documentee en tete de `abilities/targeting.py`), MESUREE ici avant
        # correction. On demande donc au natif ses cibles legales.
        cands = _legal_targets(sid, rid, int(u["id"]), aid)
        if not cands:
            # 0 cible legale DEPUIS ICI : ce n'est pas un echec du chemin summon, c'est la geometrie.
            # On DEPLACE le summoner vers le centre du plateau et on redemande au natif.
            _step_toward(sid, rid, int(u["id"]), (4, 4), 0)
            d = _dv(sid, rid)
            u = _by_vis(d, vis) or u
            cands = _legal_targets(sid, rid, int(u["id"]), aid)
        done = False
        for c in cands[:12]:
            act = {"kind": "ability", "casterId": int(u["id"]), "abilityType": int(aid)}
            if "id" in c:
                act["targetId"] = c["id"]
            else:
                act["to"] = {"col": c["col"], "row": c["row"]}
            res = _act(sid, rid, act, 120)
            acts = ((res or {}).get("actions") or [{}])[0]
            if acts.get("mutated") or int(acts.get("spawned") or 0) > 0:
                print("  [summon] %s caste %d sur %s -> spawned=%s"
                      % (vis, aid, c, acts.get("spawned")))
                done = True
                break
        if not done:
            print("  [summon] %s : aucun cast de %d n'a mute l'etat (candidats=%d)"
                  % (vis, aid, len(cands)))


# --------------------------------------------------------------------------- variantes du port

def _variant(aid, kind):
    """Les CINQ (six pour 1000) versions confrontees. Chaque contrefactuel neutralise UN champ des
    `TargetingOptions` et un seul : une ligne que le natif refuse et qu'un contrefactuel accepte
    prouve que CE champ porte le refus. Un champ dont la neutralisation ne change rien n'est PAS
    valide par la mesure -- le bilan le dit explicitement."""
    klass = ABILITY_CLASSES[aid]
    base = klass.TARGETING_OPTIONS
    if kind == "apres":
        return klass()
    opts = {
        "avant": None,
        "sansRules": _replace(base, rules=0),
        "sansRange": _replace(base, range=None),
        "fmtFlip": _replace(base, force_melee_target=(RANGED_BOOL_FALSE
                                                      if int(base.force_melee_target) == RANGED_BOOL_TRUE
                                                      else RANGED_BOOL_TRUE)),
        "sansSelf": _replace(base, self_cast=False),
    }[kind]

    class _V(klass):
        __slots__ = ()
        TARGETING_OPTIONS = opts
    return _V()


def _nat(sid, rid, cid, aid, tid=None):
    body = {"runnerId": rid, "casterId": cid, "abilityType": int(aid)}
    if tid is not None:
        body["targetId"] = int(tid)
    return _r(sid, "abilityReason", body, 60)


def _hexval(node):
    h = (node or {}).get("hex")
    if isinstance(h, str):
        return int(h, 16)
    return 0 if (node or {}).get("ruleClass") == "NoBrokenTargetingRule" else None


def _measure(sid, rid, st, dv, caster_u, aid, variants):
    cid = int(caster_u["id"])
    rows = []
    for u in (dv.get("units") or []):
        if not u.get("alive"):
            continue
        tid = int(u["id"])
        # le camp se lit sur `owner`, JAMAIS sur `ctrl` (qui designe le joueur COURANT et s'inverse
        # des qu'on a pilote une unite adverse pour monter la geometrie)
        side = ("CASTER" if tid == cid else
                ("ALLIE" if u.get("owner") == caster_u.get("owner") else "ENNEMI"))
        nat = _nat(sid, rid, cid, aid, tid)
        tr = (nat or {}).get("targetReason") or {}
        row = {"label": "%s %s" % (side, u.get("visualId")), "targetId": tid,
               "dist": hexgeo.distance(_pos(caster_u), _pos(u)),
               "nat": _hexval(tr), "nat_reasons": tr.get("reasons") or [],
               "nat_caster": _hexval((nat or {}).get("casterReason") or {})}
        for v in variants:
            row[v] = int(get_invalid_target_reason(st, cid, tid, _variant(aid, v)))
        rows.append(row)
    return rows


def _report(aid, caster_u, rows, variants):
    opts = ABILITY_CLASSES[aid].TARGETING_OPTIONS
    print("\n=== ability %d  caster=u%s(%s)  masque=0x%x  self_cast=%s  fmt=%d"
          % (aid, caster_u["id"], caster_u.get("visualId"), int(opts.rules), opts.self_cast,
             int(opts.force_melee_target)))
    hdr = "  %-26s %-5s %-3s %-12s %-26s" % ("cible", "id", "d", "natif", "regle")
    for v in variants:
        hdr += " %-11s" % v
    print(hdr + " accord")
    n_agree = n_gain = 0
    cf = {v: 0 for v in variants if v != "apres"}
    for r in rows:
        agree = (r["nat"] == r["apres"])
        n_agree += 1 if agree else 0
        gain = (r["nat"] not in (None, 0)) and r["avant"] == 0
        n_gain += 1 if gain else 0
        line = "  %-26s %-5d %-3s %-12s %-26s" % (
            r["label"], r["targetId"], r["dist"],
            "-" if r["nat"] is None else hex(r["nat"]),
            ",".join(r["nat_reasons"])[:26] or "-")
        for v in variants:
            line += " %-11s" % hex(r[v])
        print(line + (" OK" if agree else " MISMATCH") + ("  <-GAIN" if gain else ""))
        # Un contrefactuel compte des lignes DIVERGENTES, dans LES DEUX SENS : neutraliser un champ
        # peut faux-ACCEPTER (le refus disparait) comme faux-REFUSER (basculer `force_melee_target`
        # ARME un clamp de melee que le natif ne pose pas). Ne compter que les faux-accepts
        # declarerait « non valide par la mesure » un champ pourtant demontre porteur -- c'est
        # exactement le cas de `force_melee_target` et de `self_cast` sur ce lot.
        for v in cf:
            if r[v] != r["apres"]:
                cf[v] += 1
    accepte = any(r["nat"] == 0 for r in rows)
    print("  [bilan %d] accord natif/APRES %d/%d ; casts illegaux que master acceptait : %d ; "
          "au moins une cible ACCEPTEE : %s" % (aid, n_agree, len(rows), n_gain,
                                                "OUI" if accepte else "NON"))
    print("  [contrefactuels %d] lignes que la neutralisation d'UN champ fait diverger : %s"
          % (aid, "  ".join("%s -> %d/%d" % (v, cf[v], len(rows)) for v in cf if v != "avant")))
    inertes = [v for v in cf if v != "avant" and cf[v] == 0]
    if inertes:
        print("  [NON VALIDE PAR LA MESURE %d] champs dont la neutralisation ne change RIEN sur "
              "cet etat : %s" % (aid, ",".join(inertes)))
    ok = (n_agree == len(rows) and accepte and n_gain > 0)
    return ok, {"ability": aid, "agree": n_agree, "rows": len(rows), "gain": n_gain,
                "accepte": accepte, "cf": cf, "inertes": inertes, "detail": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="heroes", choices=sorted(GROUPS))
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args(argv)
    grp = GROUPS[a.group]

    sid = _resolve_session()
    rid, state_file = _build(sid, a.seed, a.board, grp["p_units"])
    print("[build] runner=%d group=%s board=%s seed=%s p_units=%s"
          % (rid, a.group, a.board, a.seed, ",".join(grp["p_units"])))
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        # ORDRE : la GEOMETRIE d'abord, les invocations ENSUITE. `Waaagh` (1058) borne ses cibles
        # legales a `constants.range` = 3 ET les restreint par sa regle dynamique -- tant que les
        # ennemis sont a 10 hex, `abilityTargets` rend 0 cible et l'invocation est impossible.
        # Une fois le spectre monte, elle passe.
        anchor = grp["p_units"][0]
        _drive_spectrum(sid, rid, anchor)
        _bring_to_contact(sid, rid, [v for v in grp["p_units"] if v != anchor])
        if grp["summon_casts"]:
            _cast_summons(sid, rid, grp["summon_casts"])
            # les invoques naissent avec leur `initialCooldownTurns` -> l'oracle court-circuiterait
            # (`ValidRequest`) ; on purge, personne ne bouge (`--no-ai`).
            for _ in range(TOURS_DE_CHAUFFE):
                _act(sid, rid, {"kind": "endturn"}, 60)
        _give_turn_to(sid, rid, anchor)

        dv = _dv(sid, rid)
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("[FAIL] boardGraph indisponible")
            return 2
        st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))

        allok = True
        out = []
        print("[plateau] %s" % sorted(set((u.get("visualId"), u.get("owner"))
                                          for u in dv["units"] if u.get("alive"))))
        for vis, aid in grp["casters"]:
            cu = _find_carrier(sid, rid, dv, vis, aid)
            if cu is None:
                print("\n=== ability %d : porteur %s ABSENT du plateau -> non mesure" % (aid, vis))
                allok = False
                continue
            nat0 = _nat(sid, rid, int(cu["id"]), aid)
            if not bool(((nat0 or {}).get("abilityState") or {}).get("usable")):
                print("\n=== ability %d : NON UTILISABLE par %s -> l'oracle court-circuite "
                      "(`ValidRequest`), mesure impossible" % (aid, vis))
                allok = False
                continue
            variants = ["apres", "avant", "sansRules", "sansRange", "fmtFlip"]
            if ABILITY_CLASSES[aid].TARGETING_OPTIONS.self_cast:
                variants.append("sansSelf")
            rows = _measure(sid, rid, st, dv, cu, aid, variants)
            ok, rec = _report(aid, cu, rows, variants)
            pc = int(get_invalid_caster_reason(st, int(cu["id"]), _variant(aid, "apres")))
            nc = sorted(set(r["nat_caster"] for r in rows if r["nat_caster"] is not None))
            print("  [volet CASTER %d] casterReason natif=%s port=%s" % (aid, nc, hex(pc)))
            ok = ok and (pc in nc if nc else True)
            allok = allok and ok
            rec["caster_nat"] = nc
            rec["caster_port"] = pc
            out.append(rec)

        print("\n[VERDICT %s] %s" % (a.group, "PASS" if allok else "FAIL"))
        print("[RAW] " + json.dumps(out))
        return 0 if allok else 1
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            state_file.unlink(missing_ok=True)
            print("[cleanup] runner %d dispose" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)


if __name__ == "__main__":
    sys.exit(main())
