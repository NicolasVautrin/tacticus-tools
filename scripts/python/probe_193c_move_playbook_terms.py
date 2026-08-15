#!/usr/bin/env python
"""#193c - CONFRONTATION par TUILE d'un playbook de MOUVEMENT porte, contre le NATIF.

QUESTION BINAIRE : sur un montage ou le terme du playbook N'EST PAS CONSTANT, le port rend-il, TUILE
PAR TUILE, exactement ce que le natif met dans son `Tile(7)` ?

Decomposition PAR ETAGE (jamais un scalaire fitte), sur les hooks EXISTANTS de `scorer-damage-trace`
(aucune reinjection ; armes pour UN SEUL `aiStepDryRun`, desarmes en `finally`) :

    X_natif(tuile) = Tile(7)  -  Elevation  -  TileEffects        (scorerTileTermTrace / Elev / Leaf)
    X_port (tuile) = Tile(7) du PORT - ses feuilles Elevation et TileEffects

`X` = la somme des feuilles NON instrumentees ; sur un montage propre (mover MELEE, aucun effet porte,
pas de point de capture) elle se reduit a la feuille dispatcher `TriggeredAbilities(2)`, donc au
playbook teste. Le probe affiche AUSSI le terme du playbook seul et le VOISINAGE qualifie (ennemi a
arme de portee / ami de faction), pour que l'ecart se lise etage par etage au lieu de se deviner.

Usage (ASCII only) :
  python probe_193c_move_playbook_terms.py --carrier blackTerminator --ability 1038 \
      --board MC1_67 --seed 777 --p-units "blackTerminator,..." --a-units "..."
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pin import BuildPinRefused, require_pinned  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


def _exiger_build_des_rva() -> None:
    """Refuse si les RVA en dur du hook ne valent pas pour le build INSTALLE.

    Le hash est TRANSCRIT depuis `frida/hooks/features/scorer-damage-trace.ts`
    (`installRvaHooks`) : il ne se derive d'aucun artefact du depot, il est donc declare ICI
    et confronte par le foyer (#431). Il valait `gqfc5mff6c` alors que #257 avait deja migre
    les RVA du hook vers `rnca9r7q6c` -- le probe REFUSAIT de tourner sur un build ou tout
    etait bon, et un refus FAUX se lit exactement comme un refus legitime.

    C'est la DECLARATION UNIQUE de ce pin pour toute la famille des probes qui arme les hooks
    de `scorer-damage-trace` : #211, #212, #241 et #242 l'appellent au lieu d'en porter une
    copie (#462-r4c). Ils importaient auparavant un `BUILD_HASH` que #431 a retire -- et le
    seul a avoir un test qui le consomme, #242, a rendu 0 passed / 10 errors pendant deux jours.
    Quatre copies du meme littéral, c'est quatre endroits a migrer au prochain build.
    """
    require_pinned("rnca9r7q6c",
                   "les RVA en dur de scorer-damage-trace (installRvaHooks)",
                   "rafraichir les RVA_* et LEAF_HOOKS_VA du hook depuis le dump du nouveau "
                   "build, PUIS mettre ce hash a jour")


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(seed, board, extra):
    state = ROOT / "logs" / "runners" / f"probe193c-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--board", board, "--state-file", str(state)] + list(extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-600:])
        return None, None
    return json.loads(state.read_text())["runnerId"], state


def _apply_native(sid, rid, dry):
    for m in (dry["action"]["messages"]):
        cls = m.get("cls")
        if cls == "MoveUnitMessage":
            a = {"kind": "move", "unitId": m["unitId"],
                 "to": {"col": m["to"]["col"], "row": m["to"]["row"]}}
        elif cls == "ActiveAbilityMessage":
            a = {"kind": "ability", "casterId": m["casterId"],
                 "targetId": m.get("targetId"), "abilityType": m["abilityType"]}
        elif cls == "FinishUnitTurnMessage":
            a = {"kind": "finish", "unitId": m["unitId"]}
        else:
            continue
        _r(sid, "applyAction", {"runnerId": rid, "action": a}, 90)


def _visual_map(sid, rid):
    """id d'unite -> visualId, lu UNE fois (les ids sont stables sur la vie du runner)."""
    dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 180)
    return {u.get("id"): u.get("visualId") for u in (dv.get("units") or [])}


def _by_tile(entries, ck, rk, vk):
    out = {}
    for e in entries:
        t = (e.get(ck), e.get(rk))
        if t[0] is None or t[0] < 0:
            continue
        out.setdefault(t, set()).add(round(float(e.get(vk) or 0.0), 4))
    return out


def _one(d, t, default=None):
    v = d.get(t)
    if not v:
        return default
    return sorted(v)[0] if len(v) == 1 else None      # ambigu -> None (jamais une moyenne)


def x_port(leaves) -> float:
    """`X_port` = somme des feuilles du PORT, retranchee des DEUX feuilles que `X_nat` retranche.

    `X_nat = Tile(7) - Elevation - TileEffects` (les deux seules feuilles que les hooks de
    `scorer-damage-trace` tracent separement) : les deux membres de la comparaison doivent porter la
    MEME somme, sinon la difference mesure le retranchement au lieu du port.

    DECLARATION UNIQUE de ce retranchement pour toute la famille des probes de terme de tuile
    (#193c, #211, #212, #241, #242, #242b). Les cles sont des MEMBRES `UtilityType`, jamais des
    litteraux (#254) : la MAJ de build a insere `AttackTile` en 8, decalant `Elevation` 8->9 et
    `TileEffects` 9->10. CINQ sites portaient encore `leaves.get(8) - leaves.get(9)` -- ils
    retranchaient donc
    `AttackTile` (ABSENTE de `TILE_UTILITY.children`, soit 0.0) et `Elevation`, et **jamais**
    `TileEffects`. Mesure du 2026-08-03 sur `MC1_67`/777 : `probe_241` rendait 3 tuiles en desaccord
    sur 16, de valeur exactement `-TileEffects` (-9, +25, +25), et `probe_212` mesurait -9 sur
    l'origine de `genesMagus` -- un rouge qui accusait le PORT alors que la MESURE etait fausse."""
    return sum(leaves.values()) - sum(leaves.get(k, 0.0) for k in x_excluded())


def x_excluded() -> tuple:
    """Les `UtilityType` que `x_port` retranche -- pour que l'AFFICHAGE des feuilles non nulles
    exclue EXACTEMENT ce que le calcul exclut. Les probes filtraient sur `(8, 9)` en dur : ils
    montraient donc `Elevation` comme une feuille du terme (elle est retranchee) et cachaient une
    colonne vide (`AttackTile`, qui n'est pas une feuille du composite Tile)."""
    from engine.utilities.utility_type import UtilityType
    return (int(UtilityType.Elevation), int(UtilityType.TileEffects))


def cause_x_nat_non_mesurable(call, rid, tt, el, te, armement=None) -> str:
    """La panne NOMMEE quand `X_nat` n'est calculable sur AUCUNE tuile -- jamais un silence.

    `X_nat = Tile(7) - Elevation - TileEffects` exige les TROIS canaux de `scorer-damage-trace`.
    Il suffit que l'un soit muet pour que CHAQUE ligne sorte a `None` -- et tout consommateur qui
    saute les `None` (c'est la forme naturelle : `if x_nat is None: continue`) conclut alors
    « 0 desaccord » sur ZERO assertion evaluee.

    ⚠ CE N'EST PAS UNE PRECAUTION, C'EST UNE MESURE (2026-08-15). Le jeu est passe a `t6dpr4k06g`
    et le foyer live `frida/hooks/il2cpp/build-pin.ts` a refuse les ONZE adresses epinglees de la
    session. `scorerTileTermTraceDump` rendait 14 entrees (il se resout au RUNTIME, par
    `resolveSharedPlaybookBody`), mais `scorerElevTraceDump` et `scorerLeafTraceDump` rendaient
    **0**. Consequence sur `test_477r33_non_owner_playbooks_live.py` : `test_le_natif_suit_le_PORT`
    -- LE verdict du fichier -- passait A VIDE, et seules les deux contre-epreuves rougissaient
    (12 F / 29 P). Douze rouges qui accusaient les montages pour UNE panne de capteur.

    FOYER PARTAGE de ce diagnostic : `x_port` / `x_excluded` declarent le RETRANCHEMENT pour toute
    la famille (#193c, #211, #212, #241, #242, #477r29, #477r31, #477r33) ; ceci en declare
    l'INDISPONIBILITE, au meme endroit et pour les memes appelants.

    `armement` = la reponse de `scorerDamageTraceOn`. Depuis #1112 elle porte `rvaHooks`, l'etat
    REEL de chaque sous-hook (`rvaInstalled`, lui, ne dit que « on a essaye »).
    """
    vides = [nom for nom, d in (("Tile7", tt), ("Elevation", el), ("TileEffects", te))
             if not d]
    bouts = ["X_nat NON MESURABLE : aucune tuile hookee ne porte les TROIS canaux "
             "(Tile7=%d, Elevation=%d, TileEffects=%d entree(s) par tuile)"
             % (len(tt or {}), len(el or {}), len(te or {}))]
    if vides:
        bouts.append("canal(aux) MUET(S) : %s" % ", ".join(vides))
    morts = [k for k, v in ((armement or {}).get("rvaHooks") or {}).items() if not v]
    if morts:
        bouts.append("sous-hooks NON POSES (scorerDamageTraceOn.rvaHooks) : %s" % ", ".join(morts))
    try:
        st = call("nameResolutionStatus", {}, 60) or {}
    except Exception as exc:                                        # noqa: BLE001
        st = {"_err": str(exc)}
    if st.get("_err"):
        bouts.append("nameResolutionStatus INTERROGEABLE ? %s" % st["_err"])
    else:
        # Tri-etat : `build: None` = le foyer n'a pas pu LIRE le build (ce n'est pas
        # « un autre build »), et `buildWhy` dit laquelle des trois pannes c'est.
        bouts.append("build charge = %s%s"
                     % (st.get("build"),
                        "" if not st.get("buildWhy") else " (%s)" % st["buildWhy"]))
        refus = st.get("pinnedAddressRefusals")
        if refus is None:
            bouts.append("refus d'adresses epinglees : NON MESURE")
        elif refus:
            bouts.append("%d refus d'adresses epinglees, le premier : %s"
                         % (len(refus), refus[0][:300]))
    bouts.append("REMEDE : re-deriver les VA de `frida/hooks/features/scorer-damage-trace.ts` "
                 "depuis `data/symbols/<build>/ghidra/functions.tsv`, rebuild du bundle, puis "
                 "une FENETRE DE REINJECT (un agent ne reinjecte pas). Tant qu'elle n'a pas eu "
                 "lieu, ce fichier ne PEUT PAS etre vert -- et c'est ce qu'il doit dire.")
    return " | ".join(bouts)


def _port_leaves(ctx, pos):
    """Les feuilles du `Tile(7)` du PORT, evaluees UNE PAR UNE sur la meme (tuile, meta, leaf_ctx).

    Mirror du meta construit par `engine.playbook.base.tile_utility` (meme fonction que celle
    qu'appelle `_action_utility`) : on ne recalcule pas une variante, on rejoue la sienne puis on
    ouvre le composite au lieu de n'en lire que la somme."""
    from engine.utilities.tile import (terrain_tile_effects, tile_leaf_ctx, apply_tile_attributes,
                                       TILE_UTILITY)
    meta: dict = {}
    e = ctx.elev_by_pos.get(pos)
    if e is not None:
        elevs = [x for x in ctx.elev_by_pos.values() if x is not None]
        meta = {"elevation": e, "elevation_max": max(elevs), "elevation_min": min(elevs)}
    if pos in ctx.is_temporary_by_pos:
        meta["is_temporary"] = ctx.is_temporary_by_pos[pos]
    effs = list(ctx.effects_by_pos.get(pos) or [])
    effs += terrain_tile_effects((getattr(ctx, "terrain_by_pos", None) or {}).get(pos), effs)
    if effs:
        meta["effects"] = effs
    leaf_ctx = tile_leaf_ctx(ctx)
    apply_tile_attributes(meta, pos, leaf_ctx)
    out = {}
    for child in TILE_UTILITY.children:
        out[int(child.UTILITY_TYPE)] = float(child.evaluate(pos, meta, leaf_ctx, ctx.wt))
    return out, leaf_ctx


def run(sid, rid, carrier, ability, max_steps, max_arm=6):
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    from engine.playbook.adjacent_unit_preference import load_playbook
    import hexgeo

    # --- avance jusqu'au 1er pas ou le PORTEUR est active ET son terme VARIE --
    # Le regime discriminant se CHERCHE : un pas ou le terme vaut la meme chose sur toutes les
    # tuiles candidates ne peut pas contredire le port. On evalue donc le terme du PORT (gratuit,
    # `aiStepDryRun` ne MUTE PAS) a chaque activation du porteur, et on n'arme les hooks que sur le
    # premier pas ou il prend au moins 2 valeurs distinctes.
    vmap = _visual_map(sid, rid)
    step, seen_carrier, armed = 0, 0, 0
    dv = ctx = tterm = elev = leaf = None
    while True:
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            print("trajectoire native epuisee au pas %d (%s)" % (step, dry.get("error")))
            return 1
        uid = dry.get("activatedUnitId")
        if vmap.get(uid) == carrier:
            seen_carrier += 1
            dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
            mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
            mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
            wt0 = W.load()
            pred0 = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
            ctx = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit, uid,
                                wt0, pred0)
            pb0 = load_playbook(ability)
            vals = sorted({round(pb0.calculate_movement_utility_in_steps(
                t, _port_leaves(ctx, t)[1], wt0), 4) for t in (ctx.action_tiles or [])})
            print("pas %-3d activation #%d de %s (u%s) : terme du port = %s"
                  % (step, seen_carrier, carrier, uid, vals))
            # Les hooks ne voient QUE les tuiles evaluees par le tier Comparable (sous-ensemble des
            # `action_tiles`) : un terme qui varie sur les candidates peut etre PLAT sur ce
            # sous-ensemble. On arme, on regarde, et on CONTINUE de marcher si c'est plat.
            if len(vals) > 1 and armed < max_arm:
                armed += 1
                _r(sid, "scorerDamageTraceOn", {"runnerId": rid}, 90)
                _r(sid, "scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
                try:
                    dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 90)
                    tterm = _r(sid, "scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
                    elev = _r(sid, "scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
                    leaf = _r(sid, "scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
                finally:
                    _r(sid, "scorerDamageTraceOff", {"runnerId": rid}, 60)
                hooked = {(e.get("casterCol"), e.get("casterRow"))
                          for e in (tterm.get("entries") or []) if (e.get("casterCol") or -1) >= 0}
                hvals = sorted({round(pb0.calculate_movement_utility_in_steps(
                    t, _port_leaves(ctx, t)[1], wt0), 4)
                    for t in (ctx.action_tiles or []) if t in hooked})
                print("        tuiles HOOKEES=%d, terme sur ces tuiles = %s" % (len(hooked), hvals))
                if len(hvals) > 1:
                    break
        if step >= max_steps:
            print("aucun pas DISCRIMINANT (cote HOOKS) en %d pas (%d activations, %d armements)"
                  % (max_steps, seen_carrier, armed))
            return 1
        _apply_native(sid, rid, dry)
        step += 1

    uid = dry.get("activatedUnitId")
    msgs = (dry.get("action") or {}).get("messages") or []
    nat_move = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
    me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    mpos = ((me or {}).get("pos") or {})
    origin = (mpos.get("col"), mpos.get("row")) if mpos.get("col") is not None else None
    nat_tile = ((nat_move["to"]["col"], nat_move["to"]["row"]) if nat_move else origin)

    wt = ctx.wt
    tt = _by_tile(tterm.get("entries") or [], "casterCol", "casterRow", "tileTerm")
    el = _by_tile(elev.get("entries") or [], "col", "row", "leaf")
    te = _by_tile([e for e in (leaf.get("entries") or []) if e.get("leaf") == "TileEffects"],
                  "col", "row", "value")
    if not tt:
        print("!! AUCUN event tileTerm -- hooks non armes ou pas de tier Comparable a ce pas")
        return 1

    pb = load_playbook(ability)
    if pb is None:
        print("!! ability %d absente de TRIGGERED_MOVE_PLAYBOOKS" % ability)
        return 1

    print("\n===== u%s (%s) origin=%s ability=%d =====" % (uid, (me or {}).get("visualId"),
                                                           origin, ability))
    print("  natif : move=%s" % ((nat_tile if nat_move else None),))

    tiles = [t for t in (ctx.action_tiles or []) if t in tt]
    print("\n  tuile      Tile7nat  Elev  TileEff  X_nat | Tile7port  X_port  terme_pb  DELTA(X)")
    bad = 0
    for t in tiles:
        vt, ve, vf = _one(tt, t), _one(el, t), _one(te, t, 0.0)
        leaves, leaf_ctx = _port_leaves(ctx, t)
        p_tot = sum(leaves.values())
        p_x = x_port(leaves)                   # foyer UNIQUE du retranchement (cf. `x_port`)
        term = pb.calculate_movement_utility_in_steps(t, leaf_ctx, wt)
        x = (vt - ve - vf) if None not in (vt, ve, vf) else None
        d = (x - p_x) if x is not None else None
        if d is not None and abs(d) > 1e-6:
            bad += 1
        print("  %-10s %-9s %-5s %-8s %-6s| %-10.4g %-7.4g %-9.4g %s"
              % (t, vt, ve, vf, x, p_tot, p_x, term, ("%.4g" % d) if d is not None else "?"))

    # --- VOISINAGE QUALIFIE : ce qui fait VARIER le terme, tuile par tuile ----
    import gameconfig as GC
    alive = [u for u in (dv.get("units") or [])
             if u.get("alive") and (u.get("pos") or {}).get("col") is not None
             and u.get("id") != uid]
    mine = bool((me or {}).get("ctrl"))

    def q(u):
        g = GC.unit(u.get("visualId")) or {}
        rng = any(int(w.get("Range") or 0) >= 2 for w in (g.get("weapons") or ()))
        return "%s%s/%s" % ("R" if rng else "M", "", g.get("FactionId"))

    print("\n  VOISINS R1 par tuile (M=melee R=arme de portee ; faction) :")
    for t in tiles:
        fr = [u for u in alive if bool(u.get("ctrl")) == mine
              and hexgeo.distance(t, (u["pos"]["col"], u["pos"]["row"])) == 1]
        fo = [u for u in alive if bool(u.get("ctrl")) != mine
              and hexgeo.distance(t, (u["pos"]["col"], u["pos"]["row"])) == 1]
        print("  %-10s amis=%-46s ennemis=%s"
              % (t, [q(u) for u in fr] or "-", [q(u) for u in fo] or "-"))

    vals = sorted({round(pb.calculate_movement_utility_in_steps(t, _port_leaves(ctx, t)[1], wt), 4)
                   for t in tiles})
    print("\n  terme du playbook sur les %d tuiles : valeurs distinctes = %s" % (len(tiles), vals))
    if len(vals) <= 1:
        print("  !! TERME CONSTANT sur ce montage -- la mesure ne peut pas contredire le port.")
    print("  ==> tuiles en DESACCORD X_nat vs X_port : %d / %d" % (bad, len(tiles)))
    return 0 if bad == 0 and len(vals) > 1 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--carrier", required=True)
    ap.add_argument("--ability", type=int, required=True)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--max-steps", type=int, default=40)
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    a = ap.parse_args()
    try:
        _exiger_build_des_rva()
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    sid = _resolve_session()
    if a.runner is not None:
        return run(sid, a.runner, a.carrier, a.ability, a.max_steps)
    rid, state = _build(a.seed, a.board, a.extra)
    if rid is None:
        return 1
    print("runner %d seed=%s board=%s carrier=%s" % (rid, a.seed, a.board, a.carrier))
    try:
        return run(sid, rid, a.carrier, a.ability, a.max_steps)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        try:
            state.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
