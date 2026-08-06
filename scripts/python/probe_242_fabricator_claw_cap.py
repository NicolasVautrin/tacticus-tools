#!/usr/bin/env python
"""probe_242 -- le CAP amis de `FabricatorClawArrayPlaybook` (1006) mord-il ? MESURE en regime n>=2.

QUESTION BINAIRE (fiche #242) : sur un etat ou AU MOINS DEUX allies retenus par
`IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$FilterAdjacentFriends` sont adjacents a la
MEME tuile candidate de `necroSpyder`, l'utilite native `X_nat` est-elle PLATE entre n=1, n=2, n=3 ?

  * PLATE      -> le cap `vtbl+0x228` mord (`mov eax,1 ; ret`), il vaut 1, et le port qui somme
                  `30 x n` est faux.
  * CROISSANTE -> le corps `<ret 1>` lu au bloc `methodPointers` n'appartient pas a ce slot.

CE QUE #57i / #193c N'ONT PAS PU DIRE : leurs montages n'ont exerce que `n <= 1`, regime ou le cap est
TRANSPARENT. Aucun de leurs accords n'est donc contredit par cette mesure, dans un sens ou dans l'autre.

MONTAGE -- il n'existait pas, et c'est l'essentiel du travail. Deux verrous :

  1. Le filtre natif ne garde PAS « tout ami Mechanical ». Il fait
     `HasTrait(u, 5) && IBattleQuery.<slot 0x2f = CanBeRepaired>(u, false)`, et
     `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` exige notamment que l'unite soit
     BLESSEE (`IdunBattle.Core.Services.AttackQuery$$IsDamagedUnit` -> `HealthComponent.IsWounded`).
     Un ami mecanique a PV PLEINS ne compte pas. On mesure donc DEUX comptages par tuile :
     `nMech` (ce que le port retient aujourd'hui) et `nRep` (mirror du natif : mecanique ET blesse).
  2. La geometrie de spawn ne donne jamais 2 allies retenus autour d'une meme tuile. On la FORCE :
     `_drive_cluster` deplace les allies mecaniques sur des VOISINS DISTINCTS d'une tuile atteignable
     par le carrier, puis termine leur tour pour que l'IA n'ait plus que le carrier a activer.

Decomposition par etage (hooks EXISTANTS de `scorer-damage-trace`, armes pour UN `aiStepDryRun`,
desarmes en `finally` -- AUCUNE reinjection) :

    X_nat (tuile) = Tile(7) - Elevation - TileEffects      (scorerTileTermTrace / Elev / Leaf)
    X_port(tuile) = somme des feuilles du port, MEME retranchement
    DELTA         = X_nat - X_port     groupe par (nMech, nRep)

Lecture : si le port ne borne pas, DELTA vaut 0 pour nRep<=1 puis -30 par ami retenu supplementaire.

Usage (ASCII only, depuis scripts/python) :
  python probe_242_fabricator_claw_cap.py --board MC1_67 --seed 777 --extra \
      --p-units "necroSpyder,admecDestroyer,admecManipulus,admecRuststalker,necroDestroyer" \
      --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"
  python probe_242_fabricator_claw_cap.py --board MC1_67 --seed 777 --no-wound --min-rep 0 --extra ...
      # regime TEMOIN : allies a PV pleins -> le gate `CanBeRepaired` rend le terme natif NUL

`admecMarshall` est volontairement HORS roster : son active `DoctrinaImperatives` (1118) allume
`AttractMechanicalsUtility` (feuille 57, +10 par tuile voisine de lui), qui se superpose au terme
mesure. Ne PAS passer `--hp-player`/`--hp-target` : ils reecrasent le `RemainingHealth` du montage.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hexgeo                                                        # noqa: E402
from build_pin import BuildPinRefused                                # noqa: E402
from rl_collect_batch import _resolve_session                        # noqa: E402
from probe_193c_move_playbook_terms import (_r, _build, _apply_native, _visual_map, _by_tile,  # noqa: E402
                                            _one, _port_leaves, _exiger_build_des_rva, x_port,
                                            x_excluded)

ABILITY = 1006                      # TriggeredAbilityType.FabricatorClawArray
CARRIER = "necroSpyder"             # HERO du pool (rank 17) ; passif = FabricatorClawArray
MECH_TRAIT = "Mechanical"           # UnitTrait.Mechanical = 5 (`HasTrait(u, 5)` du filtre natif)
KEY = "FABRICATORCLAWARRAY_AdjacentFriend"      # `Utilities.Default.TriggeredAbilities[..]` = 30

# VOIE ECARTEE, notee ici pour qu'on ne la re-tente pas : compter les LECTURES de `KEY` par
# `aiUtilityTrace*` aurait donne le cap directement (le corps commun lit la cle une fois par ami
# retenu). Elle ne marche PAS sur un runner isole : `prePopulateKnownConfigs` ne peuple
# `knownConfigs` que depuis l'`UtilitiesDatabase` du MIRROR (capturee sous
# `state.buildingMirror`), et le filtre des hooks `TryGetValue`/`get_Item` rejette tout ce qui n'y
# est pas -> `knownConfigs=0`, buffer vide (mesure : 0 entree). L'armer autrement supposerait
# `aiUtilityTraceEnable`, qui installe des hooks GLOBAUX sur un chemin chaud -- proscrit tant qu'un
# autre agent tourne.


def _seed_bc_montage(out_path):
    """Seed BC du montage : toutes les `TertiaryAbility` (= l'ability de la RELIQUE equipee) retirees.

    Sans ca la mesure est ININTERPRETABLE : `necroSpyder` porte la relique `NetherRealmCasket`
    (`TertiaryAbility: 1462`), dont
    `IdunBattle.AI.Playbook.Loki.NetherRealmCasketPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`
    est un SECOND playbook de mouvement sur EXACTEMENT le meme voisinage :

        list = IBattleQuery.<slot 0x83>(tile, ...)                  # amis adjacents
        list.RemoveAll(b__0)                                        # retire self, puis !HasTrait(u, 5)
        yield Fix64.FromInt(ctx["NetherRealmCasket_LikesAdjacentFriendlyMechanicals"] * list.Count)

    soit `+5 x #amis Mechanical adjacents`, SANS cap et SANS gate -- il se superpose terme a terme a
    celui de 1006. Le neutraliser sur TOUT le roster retire aussi les reliques des allies
    (`KardiocoreGalvanus_LikesAdjacentMechanicalFriends`, meme forme).

    VOIE ECARTEE, notee pour qu'on ne la re-tente pas : poser `RemainingHealth = Health // 2` ICI
    pour franchir d'emblee le gate `CanBeRepaired` NE MARCHE PAS -- `frida/hooks/features/
    normalize-bc/json-build.ts` fait `if ("RemainingHealth" in u) u.RemainingHealth = u.Health`
    APRES le chargement du seed BC (mesure : 102 unites patchees, `nRep = 0` sur toutes les
    candidates). Le seul point d'insertion utile est le template DEJA normalise (ce que fait
    `rl_duel --hp-player`, et ce que refait a la main `probe_226_hammer_foehammer._build_custom_once`).
    D'ou le choix inverse : bataille LONGUE (`--hp-*` eleve) + forcage des positions, les allies se
    blessant au fil des tours.

    Ecrit dans `logs/` (gitignore), jamais dans `data/`."""
    import json
    src = Path(__file__).resolve().parents[2] / "data" / "seed-bc.json"
    bc = json.loads(src.read_text(encoding="utf-8"))
    n = 0
    for u in (bc.get("Units") or []):
        if u.get("TertiaryAbility"):
            u["TertiaryAbility"] = None
            u["TertiaryAbilityLevel"] = 0
            n += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bc), encoding="utf-8")
    print("seed BC montage : %d reliques retirees -> %s" % (n, out_path))
    return out_path


def _leaf_names():
    """`UTILITY_TYPE` -> nom de classe, pour nommer les feuilles du composite Tile(7) du port."""
    from engine.utilities.tile import TILE_UTILITY
    return {int(c.UTILITY_TYPE): type(c).__name__ for c in TILE_UTILITY.children}


def _hp_by_pos(sid, rid):
    """(col,row) -> (hp, hpMax) via `observeBattle` (le seul RPC qui rende `hpMax`).

    Substrat de `IdunBattle.Core.Services.AttackQuery$$IsDamagedUnit` ->
    `IdunBattle.Entities.Components.HealthComponent$$IsWounded` (hp < hpMax) pour le cas NON-boss."""
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 90)
    out = {}
    for u in (ob.get("units") or []):
        if u.get("isDead") or u.get("col") is None:
            continue
        out[(u["col"], u["row"])] = (u.get("hp"), u.get("hpMax"))
    return out


def _counts(leaf_ctx, tile, hp):
    """(nMech, nRep) a distance 1 de `tile`.

    `nMech` = ce que `FabricatorClawArrayPlaybook.filter_adjacent_friend` retient aujourd'hui
    (trait Mechanical seul) ; `nRep` ajoute le second gate du natif (`CanBeRepaired` -> blesse)."""
    n_mech = n_rep = 0
    for u in (leaf_ctx.get("friend_units") or ()):
        if hexgeo.distance(tile, u["pos"]) != 1 or MECH_TRAIT not in (u.get("traits") or ()):
            continue
        n_mech += 1
        h, hmax = hp.get(tuple(u["pos"]), (None, None))
        if h is not None and hmax is not None and h < hmax:
            n_rep += 1
    return n_mech, n_rep


# ------------------------------------------------------------------ DRIVE des positions

def _assign(cands, allies):
    """Affectation allie -> tuile DISTINCTE (backtracking ; <=4 allies x <=6 voisins)."""
    best = {}

    def rec(i, used, acc):
        nonlocal best
        if len(acc) > len(best):
            best = dict(acc)
        if i >= len(allies):
            return
        a = allies[i]
        for t in cands.get(a, ()):
            if t in used:
                continue
            acc[a] = t
            rec(i + 1, used | {t}, acc)
            del acc[a]
        rec(i + 1, used, acc)

    rec(0, frozenset(), {})
    return best


def _drive_cluster(call, rid, carrier, allies):
    """Force le regime n>=2 : les allies mecaniques vont sur des VOISINS DISTINCTS d'une tuile T
    atteignable par le carrier, puis TERMINENT leur tour.

    On ne subit pas la geometrie de spawn -- sans ce forcage, toutes les candidates du carrier
    voient `n <= 1` et la mesure ne peut rien contredire (c'est ce qui a manque a #212 §7.2).
    T est laissee LIBRE : elle devient la candidate a `n = |allies places|`, ses propres voisines
    donnant naturellement les regimes intermediaires.

    `call(method, body, timeout)` -- injecte pour que le montage serve AUSSI au test de garde
    (`tests/engine/test_fabricator_claw_cap_live.py`), qui parle au host par la fixture `rpc`."""
    mov = call("aiMovableTiles", {"runnerId": rid}, 90)
    tiles = {u.get("unitId"): {(t["col"], t["row"]) for t in (u.get("tiles") or [])}
             for u in (mov.get("units") or [])}
    ctiles = tiles.get(carrier) or set()
    live = [a for a in allies if a in tiles]
    best_t, best_asg = None, {}
    for t in sorted(ctiles):
        ring = hexgeo.neighbors(t[0], t[1])
        cands = {a: [n for n in ring if n in tiles[a]] for a in live}
        asg = _assign(cands, live)
        if len(asg) > len(best_asg):
            best_t, best_asg = t, asg
    if best_t is None or len(best_asg) < 2:
        print("        DRIVE: aucune tuile du carrier n'admet 2 allies sur des voisins distincts")
        return 0
    print("        DRIVE: T=%s <- %s" % (best_t, sorted((a, best_asg[a]) for a in best_asg)))
    moved = 0
    for a, t in best_asg.items():
        res = call("applyAction", {"runnerId": rid,
                                   "action": {"kind": "move", "unitId": a,
                                              "to": {"col": t[0], "row": t[1]}}}, 90)
        moved += 1 if res.get("ok") else 0
    for a in live:                      # les allies ont joue : l'IA n'a plus que le carrier
        call("applyAction", {"runnerId": rid, "action": {"kind": "finish", "unitId": a}}, 60)
    return moved


# ------------------------------------------------------------------ mesure

def _measure(sid, rid, ctx, dv, uid, hp, names, wt, pb):
    """Arme les hooks pour UN dry-run, puis rend la table par tuile. Desarmement garanti."""
    _r(sid, "scorerDamageTraceOn", {"runnerId": rid}, 90)
    _r(sid, "scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
    try:
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 90)
        tterm = _r(sid, "scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
        elev = _r(sid, "scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
        leaf = _r(sid, "scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
    finally:
        _r(sid, "scorerDamageTraceOff", {"runnerId": rid}, 60)

    tt = _by_tile(tterm.get("entries") or [], "casterCol", "casterRow", "tileTerm")
    el = _by_tile(elev.get("entries") or [], "col", "row", "leaf")
    te = _by_tile([e for e in (leaf.get("entries") or []) if e.get("leaf") == "TileEffects"],
                  "col", "row", "value")
    # Decomposition par etage : TOUTES les feuilles natives tracees, tuile par tuile. Sans ca, un
    # residu se lit comme un scalaire a fitter -- avec, il s'attribue a une feuille NOMMEE.
    nat_leaves = {}
    for e in (leaf.get("entries") or []):
        t = (e.get("col"), e.get("row"))
        if t[0] is None or t[0] < 0:
            continue
        nat_leaves.setdefault(t, {})[e.get("leaf")] = round(float(e.get("value") or 0.0), 4)
    if not tt:
        print("        !! AUCUN event tileTerm -- pas de tier Comparable a ce pas")
        return None

    me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    mpos = ((me or {}).get("pos") or {})
    origin = (mpos.get("col"), mpos.get("row")) if mpos.get("col") is not None else None
    msgs = (dry.get("action") or {}).get("messages") or []
    nat_move = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
    nat_tile = (nat_move["to"]["col"], nat_move["to"]["row"]) if nat_move else origin

    occupant = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        if u.get("alive") and p.get("col") is not None:
            occupant[(p["col"], p["row"])] = "%s%s" % (u.get("visualId"), "" if u.get("ctrl") else "(E)")

    tiles = [t for t in (ctx.action_tiles or []) if t in tt]
    print("\n===== u%s (%s) origin=%s natif joue %s ; %d tuiles hookees ====="
          % (uid, (me or {}).get("visualId"), origin, nat_tile, len(tiles)))
    print("\n  tuile      X_nat  X_port  DELTA  terme_pb  nMech nRep  occupant        feuilles NON NULLES du port")
    by_pair, rows = {}, 0
    for t in tiles:
        vt, ve, vf = _one(tt, t), _one(el, t), _one(te, t, 0.0)
        leaves, leaf_ctx = _port_leaves(ctx, t)
        p_x = x_port(leaves)                    # foyer UNIQUE du retranchement (#254, cf. `x_port`)
        term = pb.calculate_movement_utility_in_steps(t, leaf_ctx, wt)
        nm, nr = _counts(leaf_ctx, t, hp)
        x = (vt - ve - vf) if None not in (vt, ve, vf) else None
        d = (x - p_x) if x is not None else None
        nz = ", ".join("%s=%g" % (names.get(k, k), v) for k, v in sorted(leaves.items())
                       if abs(v) > 1e-9 and k not in x_excluded())
        natnz = ", ".join("%s=%g" % (k, v) for k, v in sorted((nat_leaves.get(t) or {}).items())
                          if abs(v) > 1e-9)
        print("  %-10s %-6s %-7.4g %-6s %-9.4g %-5d %-5d %-15s %s"
              % (t, x, p_x, ("%.4g" % d) if d is not None else "?", term, nm, nr,
                 occupant.get(t, "-"), nz or "-"))
        print("             NATIF: %s" % (natnz or "-"))
        if x is not None:
            by_pair.setdefault((nm, nr), {"x": set(), "d": set()})
            by_pair[(nm, nr)]["x"].add(round(x, 4))
            by_pair[(nm, nr)]["d"].add(round(d, 4))
            rows += 1
    print("\n  RECAP  (nMech, nRep) -> {X_nat} | {DELTA = X_nat - X_port}")
    for k in sorted(by_pair):
        print("    nMech=%d nRep=%d -> X_nat=%-18s DELTA=%s"
              % (k[0], k[1], sorted(by_pair[k]["x"]), sorted(by_pair[k]["d"])))

    return {"pairs": by_pair, "rows": rows, "tiles": len(tiles)}


def run(sid, rid, max_steps, min_rep, max_arm):
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    from engine.playbook.adjacent_unit_preference import load_playbook

    pb = load_playbook(ABILITY)
    if pb is None:
        print("!! ability %d absente de TRIGGERED_MOVE_PLAYBOOKS -- rien a confronter" % ABILITY)
        return None
    names = _leaf_names()
    vmap = _visual_map(sid, rid)
    step, seen, armed = 0, 0, 0
    out, driven = None, set()

    def _try_drive(dv, step):
        """DRIVE si le carrier a encore son action et qu'on ne l'a pas deja fait a ce pas.

        Appele des DEUX cotes de la boucle : quand l'IA active un allie (avant qu'il ne se
        disperse) ET quand elle active le CARRIER en premier -- `aiStepDryRun` ne MUTE PAS, donc
        rien n'empeche de deplacer les allies puis de re-demander la decision du carrier. Sans ce
        second point d'entree, le cluster ne se refaisait plus des le tour 2 (mesure : 2 seules
        activations utiles en 140 pas sur `C4_09`/31337)."""
        carrier_id = next((k for k, v in vmap.items() if v == CARRIER), None)
        cu = next((u for u in (dv.get("units") or []) if u.get("id") == carrier_id), None)
        if step in driven or cu is None or not cu.get("alive") or not cu.get("hasAction"):
            return 0
        allies = [u.get("id") for u in (dv.get("units") or [])
                  if u.get("ctrl") and u.get("alive") and u.get("hasAction")
                  and u.get("id") != carrier_id]
        if not allies:
            return 0
        driven.add(step)
        print("pas %-3d DRIVE (carrier u%s en attente, %d allies)" % (step, carrier_id, len(allies)))
        return _drive_cluster(lambda m, b, t=90: _r(sid, m, b, t), rid, carrier_id, allies)

    while True:
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            print("trajectoire native epuisee au pas %d (%s)" % (step, dry.get("error")))
            return out
        uid = dry.get("activatedUnitId")
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
        if vmap.get(uid) == CARRIER:
            if _try_drive(dv, step):        # regroupe AVANT de lire la decision du carrier
                step += 1
                continue
            seen += 1
            hp = _hp_by_pos(sid, rid)
            mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
            mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
            wt = W.load()
            pred = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
            ctx = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit, uid, wt, pred)
            pairs = sorted({_counts(_port_leaves(ctx, t)[1], t, hp)
                            for t in (ctx.action_tiles or [])})
            print("pas %-3d activation #%d de %s (u%s) : (nMech,nRep) sur les candidates = %s"
                  % (step, seen, CARRIER, uid, pairs))
            # On ARME des que la geometrie varie (le regime `nRep = 0` avec `nMech > 0` est deja
            # une mesure : il isole le gate `CanBeRepaired`), mais on ne S'ARRETE que quand le
            # regime vise -- `nRep >= min_rep` sur au moins une tuile HOOKEE -- est atteint.
            if len(set(pairs)) > 1 and armed < max_arm:
                armed += 1
                got = _measure(sid, rid, ctx, dv, uid, hp, names, wt, pb)
                if got:
                    out = got
                    if max(k[1] for k in got["pairs"]) >= min_rep:
                        return got
        elif me is not None and me.get("ctrl"):
            # MON tour, une unite a moi est activee et le carrier n'a pas encore joue -> on FORCE
            # la geometrie avant de laisser l'IA disperser les allies (cf. `_drive_cluster`).
            if _try_drive(dv, step):
                step += 1
                continue
        if step >= max_steps:
            print("aucun pas discriminant en %d pas (%d activations du carrier, %d armements)"
                  % (max_steps, seen, armed))
            return out
        _apply_native(sid, rid, dry)
        step += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--max-steps", type=int, default=80)
    ap.add_argument("--min-rep", type=int, default=2, help="nRep minimal exige pour armer")
    ap.add_argument("--max-arm", type=int, default=8)
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en fin de passe")
    ap.add_argument("--relics", action="store_true",
                    help="garder les reliques (par defaut on les retire : cf. _seed_bc_montage)")
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    a = ap.parse_args()
    try:
        _exiger_build_des_rva()            # #431 : le pin des RVA du hook passe par `build_pin`
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    sid = _resolve_session()
    if a.runner is not None:
        return 0 if run(sid, a.runner, a.max_steps, a.min_rep, a.max_arm) else 1
    extra = list(a.extra or [])
    if not a.relics:
        seed_bc = _seed_bc_montage(Path(__file__).resolve().parents[2]
                                   / "logs" / "runners" / "a242-seed-bc.json")
        extra += ["--seed-bc", str(seed_bc)]
    rid, state = _build(a.seed, a.board, extra)
    if rid is None:
        return 1
    print("runner %d seed=%s board=%s carrier=%s" % (rid, a.seed, a.board, CARRIER))
    try:
        return 0 if run(sid, rid, a.max_steps, a.min_rep, a.max_arm) else 1
    finally:
        if not a.keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            try:
                state.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
