#!/usr/bin/env python
"""probe_212 -- le CAP de `SpiritualLeaderPlaybook` (1275) mord-il ? MESURE en regime n>=2 decoys.

QUESTION BINAIRE (posee AVANT la methode, en deux volets qui se mesurent separement) :

  A. CAP -- sur des tuiles candidates SANS occupant steppable (donc ou les feuilles 19/64 sont
     muettes et `X_nat` se reduit au terme de 1275), `X_nat` est-il le MEME pour n = 1, 2, 3 decoys
     allies adjacents ? PLAT => le cap `vtbl+0x228` du corps commun
     `IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook.
     u003CCalculateMovementUtilityInStepsInternalu003Ed__1u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext`
     (`n1 = Min(count(filtre vtbl+0x248), cap vtbl+0x228)`) vaut 1, et un port qui somme `30 x n`
     est faux. CROISSANT => le `<ret 1>` lu au bloc `methodPointers` n'appartient pas a ce slot.
  B. ACCORD -- tuile par tuile, `X_nat == X_port` ?

Le probe REND UN VERDICT sur les deux (rc != 0 sinon). Il ne l'a pas toujours fait : jusqu'au
2026-08-03 sa phase finale rendait `0` INCONDITIONNELLEMENT -- il IMPRIMAIT un `DELTA` de -9 sur
l'origine de `genesMagus` et passait quand meme. Ce -9 etait d'ailleurs un artefact de MESURE
(retranchement perime, cf. `x_port` de #193c), pas un ecart du port.

Decomposition par etage (jamais un scalaire fitte), sur les hooks EXISTANTS de
`scorer-damage-trace` armes pour UN SEUL `aiStepDryRun` puis desarmes -- AUCUNE reinjection :

    X_nat (tuile) = Tile(7) - Elevation - TileEffects       (scorerTileTermTrace / Elev / Leaf)
    X_port(tuile) = `x_port(feuilles du port)`, MEME retranchement (foyer unique #193c)

MONTAGE -- ON PILOTE LES POSITIONS, on ne subit pas la geometrie. `_drive_carrier_toward` deplace
`genesMagus` vers une tuile RICHE (>= 2 decoys allies a distance 1) et termine le tour des allies ;
le `move` du carrier declenche lui-meme `On(0x1c=ArrivedAtFinalTile)` -> sa face COMBAT pose un
decoy de plus, donc le drive ENRICHIT le plateau en meme temps qu'il en rapproche le carrier.
Sans ce forcage le regime n'est atteint que par la DUREE (mesure du 2026-08-03 : pas 47 sur
`MC1_67`/777, 2 activations du carrier en 47 pas) -- un echantillon SUBI, qui a deja rendu
« trajectoire epuisee, aucune activation qualifiee » chez un autre lecteur.

Usage (ASCII only, depuis scripts/python) :
  python probe_212_spiritual_leader_tile_term.py --board MC1_67 --seed 777 --extra \
      --hp-target 100000 --hp-player 100000 \
      --p-units "genesMagus,genesPrimus,genesKelermorph,orksNob,spaceWulfen" \
      --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"
  python probe_212_spiritual_leader_tile_term.py --no-drive ...   # regime SUBI (contre-epreuve)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hexgeo                                                     # noqa: E402
from build_pin import BuildPinRefused                             # noqa: E402
from rl_collect_batch import _resolve_session                      # noqa: E402
from probe_193c_move_playbook_terms import (_r, _build, _by_tile, _one, _port_leaves,  # noqa: E402
                                            _exiger_build_des_rva, x_port, x_excluded)

ABILITY = 1275                      # TriggeredAbilityType.SpiritualLeader
CARRIER = "genesMagus"              # HERO du pool ; seul passif = SpiritualLeader (gameconfig)
DECOY_TRAIT = "Decoy"               # UnitTrait.Decoy = 0x41d = 1053
STEPPABLE_TRAIT = "Steppable"       # UnitTrait.Steppable = 0x1b = 27
MIN_RICH = 2                        # n de decoys adjacents a partir duquel le cap peut etre pris en defaut


def _leaf_names():
    """`UTILITY_TYPE` -> nom de classe, pour nommer les feuilles du composite Tile(7) du port."""
    from engine.utilities.tile import TILE_UTILITY
    return {int(c.UTILITY_TYPE): type(c).__name__ for c in TILE_UTILITY.children}


def decoys_adjacent(leaf_ctx, tile):
    """Les decoys ALLIES sur une tuile ADJACENTE a `tile`, au sens de l'ADJACENCE NATIVE.

    FOYER UNIQUE de ce comptage, partage avec la garde `test_spiritual_leader_tile_term_live.py`
    -- et c'est ce partage qui est l'objet du correctif. Les deux lisaient
    `hexgeo.distance(tile, u["pos"]) == 1`, c'est-a-dire la COURONNE HEX, la ou le port (comme le
    natif) passe par `engine.battle_query.is_adjacent`, mirror de
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` -- la liste
    STOCKEE du `ConnectivityComponent` PUIS la porte INCONDITIONNELLE `|elev(t) - elev(v)| < 2`.

    ⚠ L'ECART EST STRICTEMENT PERMISSIF, DONC IL SUR-COMPTE : la couronne hex est un SUR-ENSEMBLE
    du voisinage natif (mesure #271 : 0 faux sur 4 963 paires pour `is_adjacent`, contre 9 / 22 / 2
    faux pour `hexgeo.distance == 1`, TOUJOURS dans le sens permissif). Un oracle bati sur la
    couronne annonce donc des decoys que ni le natif ni le port ne comptent, et le desaccord se lit
    comme un trou du PORT alors qu'il est dans l'ORACLE. Mesure du 2026-08-15 sur `MC1_67`/777 :
    la tuile `(1,3)` est a l'elevation 4 et DEUX de ses six voisins hex, `(1,2)` et `(2,2)`, sont a
    l'elevation 2 -- `|dElev| = 2`, donc exclus par la porte. Elle rendait `(terme 0.0, n 2)` et
    faisait tomber `test_term_is_capped_at_one_adjacent_decoy`.

    L'ANCRAGE COMPTE : `is_adjacent(tile, pos)` enumere les voisins DE `tile` (la tuile candidate),
    comme le natif -- la liste stockee n'est pas garantie symetrique, contrairement a la porte
    d'elevation. C'est l'ordre qu'emploie
    `AdjacentUnitPreferenceTriggeredAbilityPlaybook.calculate_movement_utility_in_steps`."""
    from engine import battle_query as bq
    elev = leaf_ctx.get("elev_by_pos")
    neigh = bq.neigh_map(leaf_ctx)
    return [u for u in (leaf_ctx.get("friend_units") or ())
            if u.get("pos") and bq.is_adjacent(tile, tuple(u["pos"]), elev, neigh)
            and DECOY_TRAIT in (u.get("traits") or ())]


def decoys_adjacent_hex(leaf_ctx, tile):
    """Le MEME comptage sur la COURONNE HEX -- gardé pour le DIRE, jamais pour en conclure.

    C'est l'ancien oracle. Il n'est plus consomme par aucun verdict : la table de `_measure`
    l'imprime a cote du comptage natif pour que l'ecart (`nHex != nNat`) soit VISIBLE au lieu
    d'etre un rouge inexplique."""
    return [u for u in (leaf_ctx.get("friend_units") or ())
            if u.get("pos") and hexgeo.distance(tile, tuple(u["pos"])) == 1
            and DECOY_TRAIT in (u.get("traits") or ())]


def _has_steppable_occupant(leaf_ctx, tile) -> bool:
    """La tuile porte-t-elle un occupant STEPPABLE ? Ces tuiles-la arment AUSSI les feuilles 19/64
    (#241) : `X_nat` n'y vaut plus le seul terme de 1275, donc elles sont exclues du volet A."""
    for units in ((leaf_ctx.get("friend_units") or ()), (leaf_ctx.get("enemy_units") or ())):
        for u in units:
            if tuple(u.get("pos") or ()) == tuple(tile) and STEPPABLE_TRAIT in (u.get("traits") or ()):
                return True
    return False


def _profile(ctx, tiles):
    """{tuile: (n decoys adjacents NATIF, occupant steppable ?, n decoys couronne HEX)}.

    Le 3e membre n'entre dans AUCUN verdict : il n'est la que pour rendre l'ecart entre les deux
    adjacences LISIBLE dans la table (cf. `decoys_adjacent`)."""
    out = {}
    for t in tiles:
        lc = _port_leaves(ctx, t)[1]
        out[t] = (len(decoys_adjacent(lc, t)), _has_steppable_occupant(lc, t),
                  len(decoys_adjacent_hex(lc, t)))
    return out


def _regime_ok(prof) -> bool:
    """Le regime que le volet A EXIGE : parmi les tuiles SANS occupant steppable, au moins une a
    `n = 0` et au moins une a `n >= MIN_RICH`. Sans les deux, un port qui somme `30 x n` rend la
    MEME chose qu'un port qui borne -- la mesure ne peut rien contredire.

    `n` est le comptage NATIF (`decoys_adjacent`) : c'est celui que le terme borne. Un regime
    etabli sur la couronne hex serait un regime ANNONCE et non REALISE -- la tuile compterait
    2 decoys pour l'oracle et 0 pour le natif comme pour le port."""
    ns = {n for (n, occ, _h) in prof.values() if not occ}
    return bool(ns) and 0 in ns and max(ns) >= MIN_RICH


# ------------------------------------------------------------------ DRIVE des positions

def _ally_decoys(leaf_ctx):
    """Positions des decoys ALLIES vivants, lues dans le `leaf_ctx` du port.

    ⚠ PAS dans `decisionView` : ses `units[]` ne publient PAS de champ `traits` (les traits runtime
    passent par `combatSnapshot`, cf. `frida/hooks/features/ai-step/rpc-snapshot.ts` #233). Un
    filtre `DECOY_TRAIT in u["traits"]` sur `decisionView` rend donc TOUJOURS la liste vide --
    mesure du 2026-08-03 : `0 decoy(s) allie(s)` a chaque activation alors que trois candidates
    portaient un `genesSmnDecoy`, ce qui laissait le drive en mode SEMIS en permanence."""
    return [tuple(u["pos"]) for u in (leaf_ctx.get("friend_units") or ())
            if DECOY_TRAIT in (u.get("traits") or ()) and u.get("pos")]


def _rich_tiles(decoys, leaf_ctx, min_n=MIN_RICH):
    """Tuiles ayant `>= min_n` decoys allies ADJACENTS AU SENS NATIF -- l'ensemble que le CAP borne.

    Deux etages, et le premier n'est qu'une ENUMERATION : la couronne hex de chaque decoy sert de
    SUR-ENSEMBLE de candidates (au plus 6 x |decoys|, plutot que le plateau entier), ce qui est
    licite parce que le voisinage natif y est INCLUS (l'ecart mesure est strictement permissif,
    cf. `decoys_adjacent`). Le comptage, lui, passe par `bq.is_adjacent`.

    ⚠ VISER UNE TUILE RICHE POUR L'ORACLE ET PAUVRE POUR LE NATIF fait croire au drive qu'il a
    atteint le regime alors qu'il ne l'a pas atteint : le pas est retenu, la mesure est prise, et
    le cap n'est jamais mis en defaut. C'est la MEME faute que celle du comptage, un etage plus
    haut -- d'ou le partage de `bq.is_adjacent` entre le but et la mesure."""
    from engine import battle_query as bq
    elev = leaf_ctx.get("elev_by_pos")
    neigh = bq.neigh_map(leaf_ctx)
    cand = {t for d in decoys for t in hexgeo.neighbors(d[0], d[1])}
    out = []
    for t in sorted(cand):
        if sum(1 for d in decoys if bq.is_adjacent(t, d, elev, neigh)) >= min_n:
            out.append(t)
    return out


def walk_driven(call, rid, carrier_id, wants, goals_of, max_steps=120, drive=True):
    """Marche la trajectoire NATIVE en PILOTANT les positions du carrier, et YIELD les etats de
    decision ou le REGIME est realise.

    C'est le montage partage de #212 et #241 (et le patron de `_drive_cluster`, #242) : plutot que
    d'esperer que la geometrie de spawn produise la condition mesuree, on la FABRIQUE.

      `wants(ctx, leaf_ctx)`            -> le regime est-il realise sur les candidates de ce pas ?
      `goals_of(ctx, leaf_ctx, decoys)` -> les tuiles de DESTINATION que le drive vise sinon.

    Yield `{step, uid, dv, ctx, lc, decoys}` a chaque activation du carrier ou `wants` est vrai --
    l'appelant mesure, et REPREND l'iteration si la mesure ne suffit pas (les tuiles reellement
    HOOKEES sont un sous-ensemble des candidates). S'arrete (fin d'iteration) quand la trajectoire
    native est epuisee ou `max_steps` atteint ; `call` est injecte pour servir aussi aux tests."""
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene

    step = seen = driven = 0
    while step < max_steps:
        dry = call("aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            print("        walk: trajectoire native epuisee au pas %d (%s) apres %d activation(s) "
                  "du carrier et %d drive(s)" % (step, dry.get("error"), seen, driven))
            return
        uid = dry.get("activatedUnitId")
        if uid == carrier_id:
            seen += 1
            dv = call("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
            mov = call("aiMovableTiles", {"runnerId": rid}, 90)
            mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
            wt = W.load()
            pred = _scene.build_predictor(lambda m, b, t: call(m, b, t), rid)
            ctx = _ai_ctx.build(lambda m, b, t: call(m, b, t), rid, dv, mov_by_unit, uid, wt, pred)
            lc = _port_leaves(ctx, (ctx.action_tiles or [(0, 0)])[0])[1]
            decoys = _ally_decoys(lc)
            if wants(ctx, lc):
                yield {"step": step, "uid": uid, "dv": dv, "ctx": ctx, "lc": lc, "decoys": decoys,
                       "seen": seen, "driven": driven}
            if drive:
                allies = [u.get("id") for u in (dv.get("units") or [])
                          if u.get("ctrl") and u.get("alive") and u.get("hasAction")
                          and u.get("id") != carrier_id]
                if _drive_carrier_toward(call, rid, carrier_id, goals_of(ctx, lc, decoys),
                                         allies, avoid=decoys) is not None:
                    driven += 1
                step += 1
                continue
        _apply_native_via(call, rid, dry)
        step += 1
    print("        walk: %d pas sans regime realise (%d activations du carrier, %d drives)"
          % (max_steps, seen, driven))


def _apply_native_via(call, rid, dry):
    """`_apply_native` de #193c, mais sur le `call` INJECTE (le test parle au host par sa fixture)."""
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
        call("applyAction", {"runnerId": rid, "action": a}, 90)


def carrier_id_of(call, rid, visual_id):
    """id d'entite du porteur, par son `visualId` -- lu UNE fois (ids stables sur la vie du runner)."""
    dv = call("decisionView", {"runnerId": rid, "maxRank": 1}, 180)
    return next((u.get("id") for u in (dv.get("units") or []) if u.get("visualId") == visual_id),
                None)


def _drive_carrier_toward(call, rid, carrier_id, goals, allies, avoid=()):
    """Rapproche le carrier de `goals`, puis TERMINE le tour des allies. Rend la tuile jouee ou None.

    On ne SUBIT pas la geometrie de spawn (patron `_drive_cluster` de
    `probe_242_fabricator_claw_cap.py`) : tant que le regime n'est pas realise sur les candidates du
    carrier, on le DEPLACE vers l'endroit ou il le sera au tour suivant.

      * si une tuile de `goals` est atteignable, on s'y pose -- elle devient l'ORIGINE du carrier,
        donc une candidate garantie du tour suivant ;
      * sinon on prend la tuile atteignable qui MINIMISE la distance hex a `goals` ;
      * `goals` vide -> on s'ELOIGNE des decoys deja adjacents. C'est le regime de SEMIS : le `move`
        declenche `On(0x1c)` donc un decoy de plus, et s'eloigner evite que le second volet du
        behaviour (`AmountIsEqualOrGreater(GetAdjacentDecoys(), Direct(2))`) invoque un Neophyte
        qui ECRASE le decoy qu'on vient de poser.
      * `avoid` = tuiles a ne pas fouler (un move DESSUS crushe l'occupant steppable).

    `call(method, body, timeout)` est injecte pour que le montage serve AUSSI a un test de garde."""
    mov = call("aiMovableTiles", {"runnerId": rid}, 90)
    tiles = {u.get("unitId"): [(t["col"], t["row"]) for t in (u.get("tiles") or [])]
             for u in (mov.get("units") or [])}
    cand = [t for t in (tiles.get(carrier_id) or []) if t not in set(avoid)]
    if not cand:
        print("        DRIVE: le carrier n'a aucune tuile atteignable (hors `avoid`)")
        return None
    if goals:
        gs = list(goals)
        atteignables = [g for g in gs if g in set(cand)]      # `goals` est TRIE par preference
        dest = atteignables[0] if atteignables else min(
            cand, key=lambda t: (min(hexgeo.distance(t, g) for g in gs), t))
        why = "sur la tuile visee" if atteignables else "au plus pres de la tuile visee"
    else:
        seeds = list(avoid)                      # les decoys connus : on s'en ELOIGNE pour semer
        dest = (max(cand, key=lambda t: (min((hexgeo.distance(t, s) for s in seeds), default=0), t))
                if seeds else max(cand))
        why = "SEMIS (aucune tuile riche)"
    res = call("applyAction", {"runnerId": rid,
                               "action": {"kind": "move", "unitId": carrier_id,
                                          "to": {"col": dest[0], "row": dest[1]}}}, 90)
    ok = bool(res.get("ok"))
    print("        DRIVE: %s -> u%s move %s (%s)" % (why, carrier_id, dest, "ok" if ok else res))
    call("applyAction", {"runnerId": rid, "action": {"kind": "finish", "unitId": carrier_id}}, 60)
    for a in allies:                             # les allies ont joue : on enchaine sur le tour suivant
        call("applyAction", {"runnerId": rid, "action": {"kind": "finish", "unitId": a}}, 60)
    return dest if ok else None


# ------------------------------------------------------------------ mesure

def _measure(sid, rid, ctx, dv, uid, names, wt, pb):
    """Arme les hooks pour UN dry-run, puis rend la table par tuile + le verdict des deux volets."""
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
    prof = _profile(ctx, tiles)
    print("\n===== u%s (%s) origin=%s natif joue %s ; %d tuiles hookees ====="
          % (uid, (me or {}).get("visualId"), origin, nat_tile, len(tiles)))
    print("\n  tuile      X_nat  X_port  DELTA  terme_pb  nNat nHex step occupant           "
          "feuilles NON NULLES du port")
    by_n, bad, rows = {}, [], 0
    for t in tiles:
        vt, ve, vf = _one(tt, t), _one(el, t), _one(te, t, 0.0)
        leaves, leaf_ctx = _port_leaves(ctx, t)
        p_x = x_port(leaves)                     # foyer UNIQUE du retranchement (#254, cf. `x_port`)
        term = pb.calculate_movement_utility_in_steps(t, leaf_ctx, wt)
        n, occ_step, n_hex = prof[t]
        x = (vt - ve - vf) if None not in (vt, ve, vf) else None
        d = (x - p_x) if x is not None else None
        nz = ", ".join("%s=%g" % (names.get(k, k), v) for k, v in sorted(leaves.items())
                       if abs(v) > 1e-9 and k not in x_excluded())
        # `nNat` != `nHex` = la tuile porte un decoy que la COURONNE HEX voit et que la liste
        # stockee (ou la porte d'elevation) ECARTE. Ce n'est pas un ecart du port : c'est ce que
        # `IterateAdjacentTiles` fait, et l'imprimer evite qu'un lecteur relise le port.
        print("  %-10s %-6s %-7.4g %-6s %-9.4g %-4d %-4s %-4s %-18s %s"
              % (t, x, p_x, ("%.4g" % d) if d is not None else "?", term, n,
                 ("%d *" % n_hex) if n_hex != n else str(n_hex),
                 "OUI" if occ_step else "-", occupant.get(t, "-"), nz or "-"))
        if x is None:
            continue
        rows += 1
        if abs(d) > 1e-6:
            bad.append((t, round(d, 4), n, occ_step))
        if not occ_step:                          # volet A : seules les tuiles SANS feuille 19/64
            by_n.setdefault(n, set()).add(round(x, 4))

    print("\n  VOLET A  #decoys adjacents -> {X_nat}, sur les tuiles SANS occupant steppable")
    for n in sorted(by_n):
        print("    n=%d -> %s" % (n, sorted(by_n[n])))
    return {"tiles": len(tiles), "rows": rows, "bad": bad, "by_n": by_n, "prof": prof}


def _verdict(got) -> int:
    """rc 0 seulement si les DEUX volets concluent, et sur un echantillon qui les exerce."""
    by_n, bad = got["by_n"], got["bad"]
    rc = 0
    ns = sorted(by_n)
    if not ns or 0 not in ns or max(ns) < MIN_RICH:
        print("\n  ECHANTILLON NON CONFRONTABLE -- n(decoys) vus sur les tuiles SANS occupant "
              "steppable = %r ; il en faut une a 0 et une a >= %d, sinon un port qui SOMME rend la "
              "meme chose qu'un port qui BORNE (le DRIVE a-t-il echoue ?)" % (ns, MIN_RICH))
        return 2
    plateau = sorted({v for n in ns if n >= 1 for v in by_n[n]})
    if len(plateau) != 1:
        print("\n  VOLET A : ECHEC -- `X_nat` n'est PAS plat sur n >= 1 : %r. Le cap `vtbl+0x228` "
              "ne mord pas (ou une autre feuille varie sur ces tuiles)." % plateau)
        rc |= 1
    elif plateau[0] in by_n.get(0, set()):
        print("\n  VOLET A : ECHEC -- `X_nat` vaut %g AUSSI a n=0 : le terme ne distingue rien."
              % plateau[0])
        rc |= 1
    else:
        print("\n  VOLET A : OK -- `X_nat` = %g pour tout n >= 1 (n vus : %r) et %r a n=0. Le cap "
              "MORD : le terme est borne a UN decoy." % (plateau[0], [n for n in ns if n >= 1],
                                                         sorted(by_n.get(0, ()))))
    if not got["rows"]:
        # `X_nat` n'est calculable que si les TROIS canaux repondent (`Tile7`, `Elevation`,
        # `TileEffects`). Quand les hooks de feuille sont muets -- typiquement une adresse epinglee
        # que `pinnedAddress` REFUSE apres un changement de build -- chaque ligne sort a `None` et
        # la boucle les saute TOUTES. Sans ce cran, `bad` reste vide et le volet B s'annonce « OK
        # sur les 0 tuiles » : un VERT QUI MENT, sur zero assertion evaluee.
        print("\n  VOLET B : NON MESURE -- aucune tuile ne porte un `X_nat` calculable (les %d "
              "tuiles hookees sortent toutes a None). Les trois canaux sont-ils vivants ? "
              "`scorerElevTraceDump` et `scorerLeafTraceDump` rendent 0 entree des que leurs "
              "adresses epinglees sont refusees par `build_pin` (build du jeu != build declare "
              "par le pin)." % got["tiles"])
        return rc | 1
    if bad:
        print("  VOLET B : ECHEC -- %d/%d tuiles en desaccord `X_nat != X_port` "
              "(tuile, DELTA, n, occupant steppable) : %r" % (len(bad), got["rows"], bad))
        rc |= 1
    else:
        print("  VOLET B : OK -- `X_nat == X_port` sur les %d tuiles hookees." % got["rows"])
    return rc


def wants_212(ctx, lc) -> bool:
    """Le regime que #212 exige, evalue sur les candidates d'un pas (predicat de `walk_driven`)."""
    return _regime_ok(_profile(ctx, ctx.action_tiles or []))


def goals_212(ctx, lc, decoys):
    """Les tuiles que le drive de #212 vise : celles a `>= MIN_RICH` decoys allies adjacents.

    S'y poser fait de la tuile RICHE l'ORIGINE du carrier au tour suivant -- donc une candidate
    GARANTIE a `n >= MIN_RICH`, pendant que les tuiles du bord de son rayon restent a `n = 0`.
    « Adjacents » y est l'adjacence NATIVE, comme dans le comptage : `lc` porte les deux cartes
    (`elev_by_pos`, `neigh_by_pos`) que `bq.is_adjacent` consomme."""
    return _rich_tiles(decoys, lc)


def run(sid, rid, max_steps, drive=True, max_arm=6):
    from engine import weights as W
    from engine.playbook.adjacent_unit_preference import load_playbook

    pb = load_playbook(ABILITY)
    if pb is None:
        print("!! ability %d absente de TRIGGERED_MOVE_PLAYBOOKS -- rien a confronter" % ABILITY)
        return 2
    names = _leaf_names()
    call = lambda m, b, t=90: _r(sid, m, b, t)                          # noqa: E731
    carrier_id = carrier_id_of(call, rid, CARRIER)
    if carrier_id is None:
        print("!! %s absent du runner -- roster/pool a re-etalonner" % CARRIER)
        return 2
    armed, last = 0, None
    for st in walk_driven(call, rid, carrier_id, wants_212, goals_212, max_steps, drive):
        print("pas %-3d activation #%d de %s (u%s) : REGIME realise sur les candidates ; "
              "%d decoy(s) allie(s)" % (st["step"], st["seen"], CARRIER, st["uid"],
                                        len(st["decoys"])))
        if armed >= max_arm:
            break
        armed += 1
        got = _measure(sid, rid, st["ctx"], st["dv"], st["uid"], names, W.load(), pb)
        if got is not None and _regime_ok(got["prof"]):
            return _verdict(got)
        last = got
        print("        (regime non realise sur les tuiles HOOKEES -- on continue)")
    print("\n  ECHANTILLON NON CONFRONTABLE -- aucun pas ou les tuiles HOOKEES realisent le regime "
          "en %d pas (%d armement(s)). Derniere mesure : %r"
          % (max_steps, armed, None if last is None else sorted(last["by_n"])))
    return 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--max-steps", type=int, default=120)
    ap.add_argument("--max-arm", type=int, default=6)
    ap.add_argument("--no-drive", action="store_true",
                    help="ne PILOTE pas les positions : regime SUBI (contre-epreuve du montage)")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en fin de passe")
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    a = ap.parse_args()
    try:
        _exiger_build_des_rva()            # #431 : le pin des RVA du hook passe par `build_pin`
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    sid = _resolve_session()
    if a.runner is not None:
        return run(sid, a.runner, a.max_steps, drive=not a.no_drive, max_arm=a.max_arm)
    rid, state = _build(a.seed, a.board, a.extra)
    if rid is None:
        return 2
    print("runner %d seed=%s board=%s carrier=%s drive=%s"
          % (rid, a.seed, a.board, CARRIER, not a.no_drive))
    try:
        return run(sid, rid, a.max_steps, drive=not a.no_drive, max_arm=a.max_arm)
    finally:
        if not a.keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            try:
                state.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
