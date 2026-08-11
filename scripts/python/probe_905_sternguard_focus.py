#!/usr/bin/env python
"""probe_905_sternguard_focus -- CONFRONT LIVE de `1228 SternguardFocus` (#905).

Porteur retenu : **`darkaSternguard`** (<< Ramus >>, HERO `kind` lineup, DarkAngels) -- HORS du pool
capture, donc amene en bataille par **INJECTION CATALOGUE** (`catalog_inject --units
darkaSternguard --out <seedbc>.json` puis `initAndStart` sur ce seed BC augmente,
`docs/rl/case-92-catalog-injection.md` SS6). Le second porteur, `darkaBossSternguardLHE`, est un
**npc** : il serait montable par `--explicit-stats` (formule `UnitProgression$$GetNpcStats`), mais
il porte EXACTEMENT le meme kit (memes deux armes `Melta` / `Bolter` Range 3, meme active 1228,
meme passif 1545) et sa voie de STATS est differente -- le prendre confondrait << port de
l'ability >> et << port des stats npc >>. On confronte donc le porteur LINEUP, dont le pipeline de
stats (`buildNormalizedBC`, rank/level/rarite) est celui que le port modelise.

Ce que le probe MESURE (aucune assertion ici -- les assertions vivent dans
`tests/engine/runner/test_905_sternguard_focus_live.py`) :

  * `abilityTargets.fromHere` du natif pour 1228 vs le gate statique porte
    (`TARGETING_OPTIONS` = masque 0x4002 `TargetMatchesDynamicRule|TargetIsEnemy`, range
    `RANGE_ADJACENT_IF_MELEE_CASTER`, `forceMeleeTarget = IfRangedCaster`) ;
  * le montant d'override `UnitStats_Attack_Override` de la cascade live vs le noeud
    `PercentageOfAttackCappedAtMax(Subject, statPart=3 Initial, maxDmg, dmgPct)` ;
  * le DEGAT (tags `Amount`) live vs le port rejoue sur l'etat PRE-cast + `dumpRng` ;
  * l'etat NET des effets apres le cast (`TemporaryStatOverride` 1296 ne doit PAS rester) ;
  * les FLAGS DE TOUR apres le cast (`SetsEndTurnFlags` est SURCHARGE par cette ability avec un
    trigger qui n'est ni TRUE ni FALSE -- residu #905-r1 : le port garde le defaut << termine le
    tour >>, cette mesure-ci est ce qui le confirme ou l'infirme).

La DISTANCE caster<->cible est un parametre (`--dist`) : elle change l'ARME de l'attaque normale
(`Melta` melee a 1, `Bolter` a 2-3) ET la portee du passif `SpecialIssueCombiMelta` (1545), qui
mord differemment a 1 / 2 / 3 (extra-dmg / hits / `Pinned`). C'est le seul axe de generalisation qui
change le resultat observable de 1228 sans changer l'arbre.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_905_sternguard_focus.py --seedbc <absolu>.json --dist 1
    python probe_905_sternguard_focus.py --seedbc <absolu>.json --dist 3 --case all

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import copy
import json

import hexgeo
import rl_collect_batch as R

BOARD = "MC1_67"
SEED = 905905
RANK = 17
STERNGUARD_FOCUS = 1228
TEMPORARY_STAT_OVERRIDE = 1296
PINNED = 1065

CASTER_ID = "darkaSternguard"
# UN SEUL ennemi : c'est ce qui rend la DISTANCE controlable. Avec 5 adversaires groupes autour du
# spawn, un second ennemi tombe adjacent au caster et le `forceMeleeTarget = IfRangedCaster` clampe
# la portee a 1 -- la mesure << ranged >> serait alors inatteignable sans qu'on le voie.
# ⚠ PAS de porteur `TeleportStrike` : mesure du 2026-08-11 -- avec `blackTerminator`, le natif
# refusait 1228 **ET l'attaque normale 69** avec `targetReason = 0x20000000 TargetIsTargetable`
# (deep-strike : la cible n'est pas encore posee sur le plateau). Le refus n'avait RIEN a voir avec
# l'ability ; c'est le TEMOIN qui ne discriminait pas. `blackObliterator` n'a pas ce trait.
A_UNITS = ["blackObliterator"]

_rids: list[int] = []


def rpc(sid, method, body, timeout=90):
    r = R._rpc(sid, method, [body], timeout=timeout)
    if isinstance(r, dict) and r.get("error"):
        raise RuntimeError("%s: %s" % (method, r["error"]))
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def dispose(sid, rid):
    try:
        R._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
    except Exception:
        pass
    if rid in _rids:
        _rids.remove(rid)


def _placement_at_distance(bc, dist: int, n_units: int):
    """Tuiles de deploiement joueur a `dist` hexes EXACTEMENT du spawn adverse retenu.

    On DEPLACE les unites au lieu de subir la geometrie de spawn (les deux coins de MC1_67 sont a
    9-11 hexes). Le premier point rendu est celui du CASTER."""
    spawns = R._spawn_points_by_twpi(bc)
    epts = [tuple(p) for p in (spawns.get(1) or [])]
    if not epts:
        raise RuntimeError("aucun spawn adverse")
    board = bc.get("Board") or {}
    w, h = int(board.get("Width") or 0), int(board.get("Height") or 0)
    # On n'exclut que les spawns REELLEMENT occupes (`len(A_UNITS)` premiers) : exclure les 5 points
    # du groupe adverse vide l'anneau R1 et rend la mesure << au contact >> inatteignable -- ce
    # serait un << bloque par la geometrie de spawn >> fabrique par le probe lui-meme.
    taken = set(epts[:len(A_UNITS)])
    e0 = epts[0]
    ring = [(c, r) for c, r in hexgeo.disk(e0[0], e0[1], dist + 2)
            if (c, r) not in taken and 0 <= c < w and 0 <= r < h
            and hexgeo.distance((c, r), e0) == dist]
    if not ring:
        raise RuntimeError("aucune tuile a distance %d du spawn adverse" % dist)
    ring.sort()
    out = [ring[0]]
    if n_units > 1:
        # Les remplisseurs restent DANS la zone utile (dist..dist+2) : les envoyer << loin >>
        # rendait le TEMOIN de fin de tour inutilisable (`PlasmaCannon`, portee 3, n'avait aucune
        # cible legale) -- un temoin qu'on ne peut pas jouer ne discrimine rien.
        near = [(c, r) for c, r in hexgeo.disk(e0[0], e0[1], dist + 2)
                if (c, r) not in taken and (c, r) != ring[0] and 0 <= c < w and 0 <= r < h
                and dist <= hexgeo.distance((c, r), e0) <= dist + 2]
        near.sort(key=lambda p: (hexgeo.distance(p, e0), p))
        out += near[:n_units - 1]
    if len(out) < n_units:
        raise RuntimeError("pas assez de tuiles libres (dist=%d)" % dist)
    return out


def _apply_unit_stats(bc: dict, specs) -> None:
    """Meme semantique que `rl_duel build --unit-stat` : patch PER-UNIT des champs de `BC.Units`
    sur le BC **deja normalise**. Forme `"VisualId:Champ=<json>[,Champ=<json>]"`, repetable.
    Sert a descendre l'`Attack` du caster SOUS le `maxDmg` pour faire gagner la branche
    POURCENTAGE du `Min` (le regime naturel la fait toujours perdre)."""
    for spec in (specs or []):
        vis, _, fields = spec.partition(":")
        vis = vis.strip()
        touched = [u for u in bc.get("Units", []) if u.get("VisualId") == vis]
        if not touched:
            raise RuntimeError("--unit-stat: VisualId '%s' absent de BC.Units" % vis)
        for kv in fields.split(","):
            k, _, v = kv.partition("=")
            for u in touched:
                u[k.strip()] = json.loads(v)
            print("[905] unit-stat %s.%s = %s" % (vis, k.strip(), v))


def build(sid, seedbc_path: str, dist: int = 1, p_units=None, cap_wait_s=600, unit_stats=None):
    """Runner isole depuis le seed BC AUGMENTE. Rend le runnerId.

    CAP SATURE (MAX_RUNNERS, partage entre agents) : on ATTEND qu'un slot se libere au lieu
    d'echouer -- on ne dispose JAMAIS le runner d'un autre."""
    import time
    deadline = time.time() + max(0, int(cap_wait_s))
    while True:
        try:
            return _build_once(sid, seedbc_path, dist, p_units, unit_stats)
        except RuntimeError as exc:
            if "cap reached" not in str(exc) or time.time() >= deadline:
                raise
            time.sleep(10)


def _build_once(sid, seedbc_path: str, dist: int, p_units=None, unit_stats=None):
    p_units = list(p_units or [CASTER_ID])
    seed = R._load_seed_bc(seedbc_path)
    board_dump = R._load_board_dump(BOARD)
    template, pool, _mow = R._normalize_and_extract_pool(sid, seed, RANK, board_dump=board_dump)
    miss = [u for u in p_units + A_UNITS if u not in pool]
    if miss:
        raise RuntimeError("hors pool rank %d : %s (seed BC = %s)" % (RANK, miss, seedbc_path))
    bc = copy.deepcopy(template)
    _apply_unit_stats(bc, unit_stats)
    R._patch_predefined_units(bc, list(A_UNITS))
    pos = _placement_at_distance(bc, dist, len(p_units))
    player_units = [{"unitId": u, "playerId": R.PLAYER_ID_HUMAN,
                     "col": pos[i][0], "row": pos[i][1]} for i, u in enumerate(p_units)]
    resp = R._rpc(sid, "initAndStart",
                  [{"configJson": json.dumps(bc), "seed": SEED, "playerUnits": player_units,
                    "owner": "probe_905_sternguard_focus"}], timeout=60)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % (resp.get("error") or resp))
    _rids.append(rid)
    return rid


# --------------------------------------------------------------------------- observation

def units_by_visual(dv):
    return {u.get("visualId"): u for u in (dv.get("units") or [])}


def positions(dv):
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u["id"]] = (p.get("col"), p.get("row"))
    return out


def eff_names(dv, uid):
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return sorted((e.get("effectType"), e.get("name"), e.get("remaining"))
                  for e in ((u or {}).get("effects") or []))


def act(sid, rid, action):
    r = rpc(sid, "applyAction", {"runnerId": rid, "action": action}, 90)
    acts = r.get("actions") or []
    out = dict(acts[0]) if acts else {}
    out["stage"] = r.get("stage")
    return out


def cast(sid, rid, caster, target, ability=STERNGUARD_FOCUS):
    return act(sid, rid, {"kind": "ability", "casterId": caster,
                          "targetId": target, "abilityType": ability})


def legal_from_here(sid, rid, unit, ability=STERNGUARD_FOCUS):
    """Cibles LEGALES DEPUIS LA POSITION COURANTE -- JAMAIS `targets`, qui est un SUPERSET incluant
    les cibles atteignables APRES deplacement (#111)."""
    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": unit, "abilityType": ability}, 90)
    out = []
    for u in (at.get("units") or []):
        for a in (u.get("abilities") or []):
            if int(a.get("abilityId") or -1) == int(ability):
                out += [x.get("targetId") for x in (a.get("fromHere") or [])]
    return out


def dmg_by_target(action: dict) -> dict:
    out = {}
    for e in (action.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" in td:
            out.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return out


def tag_values(action: dict, key: str) -> list:
    out = []
    for e in (action.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if key in td:
            out.append((td[key], e.get("entity")))
    return out


def snapshot(sid, rid):
    """(board, decisionView, observeBattle, combatSnapshot, dumpRng) -- l'etat PRE-cast complet."""
    from engine.entities.pathfinding.board import Board
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym") if bg and bg.get("tiles") else None
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    cs = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    rng = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    return board, dv, ob, cs, rng


# --------------------------------------------------------------------------- cas

def case_confront(sid, seedbc, dist, unit_stats=None):
    """Cast LIVE + rejeu du port sur l'etat PRE-cast. Imprime les deux cotes, etage par etage."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.abilities.darkangels import (SternguardFocusAbility,
                                                    _sternguard_capped_attack_vars)
    rid = build(sid, seedbc, dist, unit_stats=unit_stats)
    try:
        board, dv, ob, cs, rng = snapshot(sid, rid)
        bv = units_by_visual(dv)
        if CASTER_ID not in bv:
            raise RuntimeError("caster absent de la vue : %s" % sorted(bv))
        caster = bv[CASTER_ID]["id"]
        pos = positions(dv)
        foes = [u["id"] for u in (dv.get("units") or []) if not u.get("ctrl")]
        print("[905] dist=%d caster u%s @%s ; ennemis %s" % (dist, caster, pos[caster],
                                                             [(f, pos[f]) for f in foes]))
        legal = legal_from_here(sid, rid, caster)
        print("[905] legal fromHere (natif) : %s" % legal)
        print("[905] effets PRE caster : %s" % eff_names(dv, caster))
        ucast = next((x for x in (dv.get("units") or []) if x.get("id") == caster), None)
        print("[905] abilities (decisionView) : %s"
              % json.dumps((ucast or {}).get("abilities"))[:900])
        print("[905] flags caster : %s"
              % json.dumps({k: (ucast or {}).get(k) for k in
                            ("canAct", "canMove", "hasActed", "isDead", "ap", "traits")})[:500])
        print("[905] toActivate : %s ; stage=%s" % (dv.get("toActivate"), dv.get("stage")))
        at = rpc(sid, "abilityTargets",
                 {"runnerId": caster and rid, "unitId": caster,
                  "abilityType": STERNGUARD_FOCUS}, 90)
        print("[905] abilityTargets brut : %s" % json.dumps(at)[:900])
        if not legal:
            print("[905] AUCUNE cible legale a cette distance -- rien a confronter")
            return
        tgt = legal[0]
        print("[905] distance caster<->cible = %d" % hexgeo.distance(pos[caster], pos[tgt]))

        cap, pct = None, None
        off = None
        if board is not None and isinstance(rng, dict) and rng.get("mt"):
            st = load_state(dv, ob, cs, board=board)
            r = IntBasedMersenneTwister()
            r.mt = list(rng["mt"]); r.mti = rng["mti"]
            st.rng = r
            cap, pct = _sternguard_capped_attack_vars(st, caster)
            off = SternguardFocusAbility().execute_behaviour(st, caster, tgt)
            print("[905] PORT   cap=%s pct=%s override=%s total=%s skipped=%s"
                  % (cap, pct, (off or {}).get("override"), (off or {}).get("total"),
                     (off or {}).get("skipped")))
            print("[905] PORT   etages=%s" % json.dumps((off or {}).get("etages")))
        else:
            print("[905] etat offline INDISPONIBLE (boardGraph/dumpRng) -- pas de rejeu du port")

        hp_pre = {u["squadId"]: u.get("hp") for u in (ob.get("units") or [])}
        res = cast(sid, rid, caster, tgt)
        print("[905] cast ok=%s stage=%s" % (res.get("ok"), res.get("stage")))
        print("[905] LIVE   Amount par cible : %s" % dmg_by_target(res))
        print("[905] LIVE   Attack_Override  : %s" % tag_values(res, "UnitStats_Attack_Override"))
        ob2 = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        hp_post = {u["squadId"]: u.get("hp") for u in (ob2.get("units") or [])}
        print("[905] LIVE   hp cible %s -> %s (delta %s)"
              % (hp_pre.get(tgt), hp_post.get(tgt),
                 (hp_pre.get(tgt) or 0) - (hp_post.get(tgt) or 0)))
        dv2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        print("[905] POST   effets caster : %s" % eff_names(dv2, caster))
        print("[905] POST   effets cible  : %s" % eff_names(dv2, tgt))
        u1 = next((x for x in (dv.get("units") or []) if x.get("id") == caster), None)
        u2 = next((x for x in (dv2.get("units") or []) if x.get("id") == caster), None)
        # `SetsEndTurnFlags` -- l'observable est `hasAction` (le flag `NoActionAvailable` du natif),
        # pas `toActivate` (qui reste peuple tant que le tour du joueur n'est pas clos).
        print("[905] FLAGS  hasAction caster : PRE=%s POST=%s ; toActivate POST=%s"
              % ((u1 or {}).get("hasAction"), (u2 or {}).get("hasAction"), dv2.get("toActivate")))
        # CONTRE-EPREUVE : si le tour N'EST PAS termine, une attaque normale doit encore passer.
        follow = cast(sid, rid, caster, tgt, 69)
        print("[905] FLAGS  attaque normale APRES le cast : ok=%s mutated=%s"
              % (follow.get("ok"), follow.get("mutated")))
    finally:
        dispose(sid, rid)


def case_control(sid, seedbc, dist):
    """TEMOIN de DISCRIMINATION du verdict << ne termine pas le tour >>.

    On monte le MEME runner avec, en plus, `darkaTerminator` (active `PlasmaCannon` 1150, ABSENTE
    des deux frozensets de `base.py` -> elle TERMINE le tour), et on rejoue exactement la meme
    sequence : cast, puis attaque normale. Si le harnais laissait passer l'attaque normale MEME
    apres une ability qui termine le tour, la mesure faite sur 1228 ne dirait RIEN -- c'est ce
    temoin, et lui seul, qui etablit qu'elle discrimine."""
    rid = build(sid, seedbc, dist, p_units=[CASTER_ID, "darkaTerminator"])
    try:
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        bv = units_by_visual(dv)
        term = bv["darkaTerminator"]["id"]
        pos = positions(dv)
        foes = [u["id"] for u in (dv.get("units") or []) if not u.get("ctrl")]
        tgt = foes[0]
        u0 = next((x for x in (dv.get("units") or []) if x.get("id") == term), None)
        print("[905ctrl] terminator u%s @%s ; cible u%s @%s ; hasAction PRE=%s"
              % (term, pos[term], tgt, pos[tgt], (u0 or {}).get("hasAction")))
        legal = legal_from_here(sid, rid, term, 1150)
        print("[905ctrl] legal 1150 fromHere : %s" % legal)
        if not legal:
            print("[905ctrl] TEMOIN INUTILISABLE : aucune cible legale pour 1150")
            return
        res = cast(sid, rid, term, legal[0], 1150)
        print("[905ctrl] cast 1150 ok=%s mutated=%s" % (res.get("ok"), res.get("mutated")))
        dv2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        u2 = next((x for x in (dv2.get("units") or []) if x.get("id") == term), None)
        print("[905ctrl] hasAction POST=%s" % (u2 or {}).get("hasAction"))
        follow = cast(sid, rid, term, legal[0], 69)
        print("[905ctrl] attaque normale APRES 1150 : ok=%s mutated=%s"
              % (follow.get("ok"), follow.get("mutated")))
    finally:
        dispose(sid, rid)


def case_flags(sid, seedbc, dist):
    """`SetsEndTurnFlags` de 1228 : le natif rend `<DSLTriggers>+0x60`, qui n'est NI la constante
    TRUE (`+0x40`) NI la constante FALSE (`+0x48`). On BALAYE donc les regimes qui pourraient
    porter la condition, et on lit `hasAction` + la recevabilite d'une attaque normale APRES.

    Regimes : (a) caster SEUL ; (b) allie DarkAngels ADJACENT (le predicat du playbook
    `SternguardFocusPlaybook$$HasAdjacentDarkAngels`) ; (c) caster ayant DEJA bouge ;
    (d) cible TUEE par le cast."""
    regimes = [("seul", [CASTER_ID], False, None),
               ("allie-DA-adjacent", [CASTER_ID, "darkaAzrael"], False, None),
               ("apres-mouvement", [CASTER_ID], True, None),
               ("cible-tuee", [CASTER_ID], False, ["blackObliterator:Health=1"])]
    for label, punits, do_move, ustats in regimes:
        rid = build(sid, seedbc, dist, p_units=punits, unit_stats=ustats)
        try:
            dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            bv = units_by_visual(dv)
            caster = bv[CASTER_ID]["id"]
            pos = positions(dv)
            foes = [u["id"] for u in (dv.get("units") or []) if not u.get("ctrl")]
            tgt = foes[0]
            allies = [u["id"] for u in (dv.get("units") or [])
                      if u.get("ctrl") and u["id"] != caster]
            adj = [a for a in allies if hexgeo.distance(pos[a], pos[caster]) == 1]
            if do_move:
                cands = [p for p in hexgeo.disk(pos[tgt][0], pos[tgt][1], dist)
                         if hexgeo.distance(p, pos[tgt]) == dist and p != pos[caster]]
                cands.sort(key=lambda p: hexgeo.distance(p, pos[caster]))
                if cands:
                    mv = act(sid, rid, {"kind": "move", "unitId": caster,
                                        "to": {"col": cands[0][0], "row": cands[0][1]}})
                    print("[905flags/%s] move ok=%s" % (label, mv.get("ok")))
            legal = legal_from_here(sid, rid, caster)
            if not legal:
                print("[905flags/%s] AUCUNE cible legale -- regime non joue" % label)
                continue
            res = cast(sid, rid, caster, tgt)
            dv2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            u2 = next((x for x in (dv2.get("units") or []) if x.get("id") == caster), None)
            t2 = next((x for x in (dv2.get("units") or []) if x.get("id") == tgt), None)
            ab2 = {a.get("id"): (a.get("usable"), a.get("cooldown"))
                   for a in ((u2 or {}).get("abilities") or [])}
            follow = cast(sid, rid, caster, tgt, 69)
            print("[905flags/%s] allies adjacents=%s cible_vivante=%s | cast mutated=%s | "
                  "hasAction POST=%s | attaque normale APRES mutated=%s | 1228 apres=%s"
                  % (label, adj, (t2 or {}).get("alive"), res.get("mutated"),
                     (u2 or {}).get("hasAction"), follow.get("mutated"),
                     ab2.get(STERNGUARD_FOCUS)))
        finally:
            dispose(sid, rid)


def case_scan(sid, seedbc, dist):
    """DIAGNOSTIC : construit a `dist`, puis RAPPROCHE le caster hexe par hexe en interrogeant
    `abilityTargets` a chaque pas, et tente le cast a chaque distance. Sert a etablir A QUELLE
    DISTANCE le natif accepte 1228 -- et, s'il n'accepte JAMAIS, a lire son refus."""
    rid = build(sid, seedbc, dist)
    try:
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        bv = units_by_visual(dv)
        caster = bv[CASTER_ID]["id"]
        pos = positions(dv)
        foes = [u["id"] for u in (dv.get("units") or []) if not u.get("ctrl")]
        tgt = foes[0]
        tpos = pos[tgt]
        print("[905scan] caster u%s @%s ; cible u%s @%s" % (caster, pos[caster], tgt, tpos))
        for d in range(dist, 0, -1):
            cur = positions(rpc(sid, "decisionView",
                                {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90))[caster]
            if hexgeo.distance(cur, tpos) != d:
                cands = [p for p in hexgeo.disk(tpos[0], tpos[1], d)
                         if hexgeo.distance(p, tpos) == d]
                cands.sort(key=lambda p: hexgeo.distance(p, cur))
                mv = act(sid, rid, {"kind": "move", "unitId": caster,
                                    "to": {"col": cands[0][0], "row": cands[0][1]}})
                print("[905scan] move -> %s ok=%s" % (cands[0], mv.get("ok")))
            legal = legal_from_here(sid, rid, caster)
            print("[905scan] d=%d legal=%s" % (d, legal))
            for ab in (STERNGUARD_FOCUS, 69):
                rs = rpc(sid, "abilityReason", {"runnerId": rid, "casterId": caster,
                                                "abilityType": ab, "targetId": tgt}, 60)
                print("[905scan] d=%d ab=%s target=%s caster=%s"
                      % (d, ab, json.dumps(rs.get("targetReason")),
                         json.dumps(rs.get("casterReason"))))
            tu = next((x for x in (rpc(sid, "decisionView",
                                       {"runnerId": rid, "maxRank": 1,
                                        "allAbilities": True}, 90).get("units") or [])
                       if x.get("id") == tgt), None)
            print("[905scan] cible brute : %s" % json.dumps(tu)[:700])
            res = cast(sid, rid, caster, tgt)
            print("[905scan] d=%d cast ok=%s mutated=%s err=%s"
                  % (d, res.get("ok"), res.get("mutated"), str(res.get("error"))[:200]))
            if res.get("ok") and res.get("mutated"):
                print("[905scan] Amount=%s ; Override=%s"
                      % (dmg_by_target(res), tag_values(res, "UnitStats_Attack_Override")))
                break
    finally:
        dispose(sid, rid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--seedbc", required=True, help="seed BC AUGMENTE (catalog_inject --out)")
    ap.add_argument("--dist", type=int, default=1)
    ap.add_argument("--case", default="confront")
    ap.add_argument("--unit-stat", action="append", default=None,
                    help="'VisualId:Champ=<json>' -- patch du BC NORMALISE, repetable")
    a = ap.parse_args()
    sid = a.session if a.session is not None else R._resolve_session()
    print("[905] session %s" % sid)
    try:
        if a.case in ("confront", "all"):
            case_confront(sid, a.seedbc, a.dist, a.unit_stat)
        if a.case in ("scan", "all"):
            case_scan(sid, a.seedbc, a.dist)
        if a.case in ("control", "all"):
            case_control(sid, a.seedbc, a.dist)
        if a.case in ("flags", "all"):
            case_flags(sid, a.seedbc, a.dist)
    finally:
        for rid in list(_rids):
            dispose(sid, rid)


if __name__ == "__main__":
    main()
