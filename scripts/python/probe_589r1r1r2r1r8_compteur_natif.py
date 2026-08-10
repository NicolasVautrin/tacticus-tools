"""`#589-r1-r1-r2-r1-r8` -- CE QUE LE NATIF COMPTE, mesure au lieu d'etre INFERE.

## Le desaccord a trancher

Deux mesures du depot etaient incompatibles PAR LE CHEMIN SUPPOSE :

  * `case-589-r1-r1-r2-r1` sec.6 : sur `C3_14`, porteur en `(5,4)` et compagnon en `(5,3)`
    (arete ABSENTE du substrat stocke DANS LES DEUX SENS), le natif ACTIVE
    `AmuletOfTheVoidwyrm_CritDamageReduction` -- donc << il compte ce voisin >> ;
  * `#589-r1-r1-r2-r1-r4` : `adjacentTilesNative` regime `selector` sur `(5,4)` ne rend PAS
    `(5,3)`, ni depuis la TUILE ni depuis l'ENTITE, `unmappedNeighbours = 0`.

Or le decompile ne laisse aucune porte entre les deux :

    ...AmuletOfTheVoidwyrm_CritDamageReductionEffect$$GetAdjacentFriendlySummonsAndDecoysCount
      -> IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(Owner, unique: 1, selectionType: 3)
         = Friends( Owner, Units(AdjacentTiles(Owner), 1, 3) op_Subtraction Owner, 3 )
      -> IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select
         = <tilesSelector>.<ITargetsSelector slot 4 = SelectUniqueUnits>(entities, selectionType)
      -> IdunBattle.DSL.TargetsSelector$$SelectUniqueUnits
         = foreach e in <vtable Select>(entities) : SelectUnit(e, selectionType)
      -> IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select
         = foreach t in origin.<slot 10 = SelectTiles>(entities) :
             foreach a in battleQuery.<IBattleQuery slot 80 = IterateAdjacentTiles>(t, 0, 1, 1) :
               if (!tiles.Contains(a)) set.Add(a)
      -> IdunBattle.Core.Services.BattleQuery.u003CIterateAdjacentTilesu003Ed__95$$MoveNext
         = foreach t in EntityExtensions$$IterateTiles(from) :
             foreach n in tileQuery.IterateAdjacentTiles(t, oes, owt, at)
      -> IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext
         = foreach id in tile.<+0x30>.<+0x10>  (une LISTE STOCKEE, aucune geometrie)

Aucune unite ne peut donc etre comptee si sa tuile n'est pas dans la LISTE STOCKEE de la tuile du
porteur. Les slots 4 (`SelectUniqueUnits`), 10 (`SelectTiles`) et 80 (`IterateAdjacentTiles`) sont
LUS dans `data/symbols/<build>/metadata/interface_slots.tsv`, pas deduits d'un nom.

## Ce que ce probe mesure -- et pourquoi l'activite seule ne suffisait pas

`CreateActiveCondition` = `AmountIsGreaterThanZero(<le compteur>)`, donc l'ACTIVITE de l'effet EST
un observable natif du compteur -- mais BINAIRE et ANONYME : elle dit << le compteur est > 0 >>,
jamais << c'est CE compagnon qui compte >>. `case-589` sec.6 a lu l'activite une fois, dans une
configuration ou plusieurs causes etaient possibles, et en a INFERE le comptage.

Trois etages, dans cet ordre :

  1. INVENTAIRE natif des porteurs de `Summon`/`Decoy` (`combatSnapshot.units[].traits`, #233 :
     les traits REELLEMENT portes en bataille, veto compris). C'est le point (2) que
     `#589-r1-r1-r2-r1-r7` demandait d'etablir PAR ENUMERATION, et il n'avait jamais ete fait.
  2. ACTIVITE DIFFERENTIELLE : tous les porteurs amis sont pousses a hex >= 4, puis UNE SEULE
     unite bouge entre deux lectures.

         S0 TEMOIN   tous les porteurs LOIN                     -> attendu INACTIF
         S1 GEO      le compagnon en hex 1 mais HORS liste stockee -> LA question
         S2 STOCKE   le meme compagnon sur un voisin STOCKE      -> attendu ACTIF (controle +)
         S3 RETOUR   le meme compagnon de nouveau LOIN           -> attendu INACTIF

     S0 et S3 sont les temoins NON DEGENERES : sans eux un << actif >> en S1 ne prouverait rien
     (l'effet pourrait etre actif quoi qu'il arrive), et un << inactif >> non plus (le montage
     pourrait etre mort). S2 prouve que le canal MORD sur ce board, ce runner, ce porteur.
  3. VALEUR du compteur, lue du DEGAT : le rejeu offline est force a `n = 0,1,2,3` et on garde le
     SEUL modele qui egale le live, RNG neutralise. Modeles ENTIERS discrets -- aucun scalaire
     fitte. La substitution est VERIFIEE (les quatre rejeux doivent differer entre eux, sinon
     elle n'a pas mordu et on REFUSE de conclure).

## UN RUNNER PAR FRAPPE

Une seconde `applyAction ability` sur le meme runner revient `ok: true, mutated: false,
changes: []` (mesure : bras `repro` joue en second). C'est le meme motif que le probe amulette,
qui construit un runner par valeur de `n`. Chaque bras qui FRAPPE a donc son runner, et les
positions de spawn etant deterministes (meme seed), l'intrus s'y retrouve tout seul a sa place.

Usage :
    python probe_589r1r1r2r1r8_compteur_natif.py
    python probe_589r1r1r2r1r8_compteur_natif.py --board C3_14 --anchor 5,4 --geo 5,3 --level 6

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_TESTS = os.path.join(_HERE, "tests", "engine", "runner")
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)

EFFECT_NAME = "AmuletOfTheVoidwyrm_CritDamageReduction"   # EffectType 0x5b4 = 1460


class MontageError(RuntimeError):
    """On REFUSE de rendre un verdict plutot que d'en fabriquer un depuis un montage muet."""


def _coord(spec):
    if not spec:
        return None
    c = [int(x) for x in str(spec).split(",")]
    return (c[0], c[1])


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


def choisir_plan(board, occupe, anchor_force=None, geo_force=None):
    """Rend `(anchor, geo, nat_libres, loins)`.

    `geo` = une tuile a distance hex 1 de l'ancre et ABSENTE de sa liste d'adjacence stockee --
    exactement le regime que `case-589` sec.6 a monte. `nat_libres` = les voisins STOCKES libres
    (il en faut DEUX : un pour l'attaquant, un pour le controle positif S2). Aucun repli
    geometrique : si le board n'offre pas la paire, on REFUSE plutot que de mesurer autre chose."""
    import hexgeo
    marchables = [t for t in sorted(board.by_id) if board.walkable(t)]
    if anchor_force is not None:
        cands = [board.id_at(anchor_force[0], anchor_force[1])]
    else:
        cands = sorted(marchables, key=lambda t: (-len(board.neighbours_native(t)), t))
    for tid in cands:
        if tid is None:
            continue
        anchor = board.coord(tid)
        if anchor in occupe:
            continue
        nat = {board.coord(v) for v in board.neighbours_native(tid)}
        nat_libres = [c for c in sorted(nat) if c not in occupe
                      and board.id_at(c[0], c[1]) is not None
                      and board.walkable(board.id_at(c[0], c[1]))]
        geos = [board.coord(t) for t in marchables
                if hexgeo.distance(board.coord(t), anchor) == 1
                and board.coord(t) not in nat and board.coord(t) not in occupe]
        if geo_force is not None:
            geos = [g for g in geos if g == geo_force]
        loins = [board.coord(t) for t in marchables
                 if board.coord(t) not in occupe
                 and hexgeo.distance(board.coord(t), anchor) >= 4]
        if geos and len(nat_libres) >= 2 and len(loins) >= 3:
            return anchor, geos[0], nat_libres, loins
    return None


def activite(h, carrier_id):
    """TRI-ETAT de la `CreateActiveCondition` natif, LU sur le canal `decisionView` :
    `True`/`False` = mesure, `None` = l'effet est ABSENT du canal (donc NON MESURE -- jamais
    rabattu sur `False`, ce qui ferait passer un porteur sans relique pour un compteur nul)."""
    dvi = h.rpc("decisionView", {"runnerId": h.rid, "maxRank": 1, "allAbilities": True,
                                 "includeInactive": True}, 90)
    cu = next((u for u in (dvi.get("units") or []) if u.get("id") == carrier_id), None)
    for e in ((cu or {}).get("effects") or []):
        if e.get("name") == EFFECT_NAME:
            return bool(e.get("active"))
    return None


def ring_natif(h, carrier_id, regime="selector"):
    """`adjacentTilesNative` -- ce que `IterateAdjacentTiles` rend REELLEMENT pour l'ENTITE du
    porteur (la forme EXACTE que prend l'appel quand le DSL passe `Owner`)."""
    res = h.rpc("adjacentTilesNative", {"runnerId": h.rid, "entityIds": [carrier_id]}, 120)
    if not res.get("ok"):
        raise MontageError("adjacentTilesNative rend ok=false : %s" % res.get("error"))
    if int((res.get("diag") or {}).get("calls") or 0) == 0:
        raise MontageError("adjacentTilesNative n'a fait AUCUN appel natif")
    for r in (res.get("origins") or []):
        if r.get("originId") == carrier_id:
            rv = (r.get("byRegime") or {}).get(regime) or {}
            if "error" in rv:
                raise MontageError("regime %s en erreur : %s" % (regime, rv["error"]))
            return [(int(t["col"]), int(t["row"])) for t in (rv.get("tiles") or [])]
    return None


def inventaire_traits(h, traits_comptes, dv=None):
    """Les porteurs REELS de `Summon`/`Decoy`, cote NATIF (`combatSnapshot.units[].traits`, #233).

    La cle d'unite de `combatSnapshot` est `entityId`, pas `id` : la lire de travers rend un
    inventaire d'anonymes, exactement le genre de zero qui se lit << rien a signaler >>.

    Tri-etat respecte : `traits == None` = capteur MUET -> on le DIT, on ne rend pas une liste
    vide qui se lirait << personne ne porte le trait >>."""
    snap = h.rpc("combatSnapshot", {"runnerId": h.rid}, 60)
    units = (snap.get("units") if isinstance(snap, dict) else None) or []
    dv = dv if dv is not None else h.dview()
    par_id = {u.get("id"): u for u in (dv.get("units") or [])}
    out, muets = [], []
    for u in units:
        eid, tr = u.get("entityId"), u.get("traits")
        if tr is None:
            muets.append(eid)
            continue
        porte = sorted(set(int(t) for t in tr) & set(traits_comptes))
        if porte:
            d = par_id.get(eid) or {}
            out.append({"id": eid, "visualId": d.get("visualId") or u.get("visualId"),
                        "owner": d.get("owner"), "pos": _pos(d), "alive": d.get("alive"),
                        "traits_comptes": porte})
    if muets:
        raise MontageError("combatSnapshot rend traits=null pour %s -- capteur MUET, "
                           "l'inventaire ne peut pas etre rendu" % (muets,))
    return out


def rejeu_force(h, rec, n):
    """Rejeu OFFLINE avec le compteur du port FORCE a `n`.

    DEUX bindings a substituer, et ils ne se valent pas :
      * `engine.runner.components.adjacent_friendly_summons_and_decoys_count` -- resolu en GLOBAL
        du module par `UnitEffectStateView`, donc il gouverne `is_active` (sans lui l'effet
        n'entre meme pas dans `active_effects`) ;
      * `engine.runner.operations.damage.adjacent_friendly_summons_and_decoys_count` -- une
        liaison `from ... import` FIGEE au chargement (forme A), donc patcher le module d'origine
        NE MORD PAS dessus. C'est elle que `_crit_board` referme dans le callable du canal.
    Substituer un seul des deux rendrait un rejeu qui ne mesure pas ce qu'il annonce."""
    from engine.runner import components as C
    from engine.runner.operations import damage as D
    oc, od = (C.adjacent_friendly_summons_and_decoys_count,
              D.adjacent_friendly_summons_and_decoys_count)
    try:
        C.adjacent_friendly_summons_and_decoys_count = lambda st, uid: int(n)
        D.adjacent_friendly_summons_and_decoys_count = lambda st, uid: int(n)
        return h.replay_offline(rec)["per_hit"]
    finally:
        C.adjacent_friendly_summons_and_decoys_count = oc
        D.adjacent_friendly_summons_and_decoys_count = od


def mesurer_n(h, AM, etiquette, anchor, contact):
    """Le compteur natif LU DU DEGAT : on joue l'attaque, RNG neutralise, avec le compteur du port
    force a 0/1/2/3, et on garde le SEUL modele entier qui egale le live.

    `None` = aucun (ou plusieurs) ne colle, et c'est un RESULTAT, pas un repli."""
    d = h.dview()
    a_, c_ = h.by_visual(AM.ATTACKER, d), h.by_visual(AM.CARRIER, d)
    if a_ is None or c_ is None:
        raise MontageError("%s : attaquant ou porteur absent" % etiquette)
    r = {"caster": a_["id"], "target": c_["id"],
         "ability_type": int(h.normal_attack_type(a_["id"], d)),
         "n": None, "anchor": anchor, "contact": contact, "step_to": None}
    r["snapshot"] = h.snapshot()
    r["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    lv, w = AM.strike(h, r)
    if lv is None:
        raise MontageError("%s : la frappe live a echoue : %s" % (etiquette, w))
    kk = len(lv)
    of = {n: rejeu_force(h, r, n)[:kk] for n in (0, 1, 2, 3)}
    # La substitution a-t-elle MORDU ? Des rejeux identiques = elle n'a rien change, et
    # << live == off(n) >> ne dirait alors RIEN sur n (un VERT qui ne mesure pas).
    if len({tuple(x) for x in of.values()}) != len(of):
        raise MontageError("%s : la substitution du compteur NE MORD PAS : %s"
                           % (etiquette, {n: of[n][:3] for n in of}))
    acc = [n for n in sorted(of) if of[n] == lv]
    n_lu = acc[0] if len(acc) == 1 else None
    print("   %-34s LIVE %s -> n NATIF = %s"
          % (etiquette, lv[:4], n_lu if n_lu is not None else "AUCUN(%s)" % acc))
    print("      off = %s" % {n: of[n][:4] for n in sorted(of)})
    # DECOMPOSITION PAR ETAGE du PORT, sur le MEME etat offline -- c'est elle qui dit QUEL etage
    # diverge quand `n natif != n port`, au lieu de laisser un ecart de degat sans accuse.
    et = AM.etages(h, r)
    print("      PORT : compteur=%s effet_actif=%s ability_state=%s bonus_signe=%s"
          % (et.get("compteur"), et.get("effet_actif_port"), et.get("ability_state"),
             et.get("bonus_signe")))
    return n_lu, et.get("compteur"), r


def diag_port_unite(h, AM, rec, uid, carrier_id):
    """Ce que le PORT voit de l'unite `uid` sur l'etat OFFLINE reconstruit -- presence, equipe,
    position, traits. C'est le seul moyen de dire QUEL etage du port perd une unite que le natif
    compte : l'entite absente, l'equipe fausse, la position absente ou le trait non porte."""
    from engine.runner.components import OwnerComponent, PositionComponent, StatsComponent
    from engine.entities.traits.unit_trait import entity_trait_names, has_trait, UnitTrait
    st = h.offline_state(rec)
    ent = st.get_entity(int(uid))
    if ent is None:
        return {"present": False}
    oc, pc = ent.get_component(OwnerComponent), ent.get_component(PositionComponent)
    sc = ent.get_component(StatsComponent)
    ce = st.get_entity(int(carrier_id))
    coc = ce.get_component(OwnerComponent) if ce is not None else None
    # Le substrat de traits du port est `entity_trait_names` (kit gameconfig + traits ACCORDES en
    # bataille + pseudo-trait d'alliance), pas une liste brute -- c'est ce que lit `UnitsWithTrait`.
    tn = entity_trait_names(getattr(sc, "ctx", None) if sc is not None else None)
    out = {"present": True,
           "team": getattr(oc, "team", None), "team_porteur": getattr(coc, "team", None),
           "col_row": ((getattr(pc, "col", None), getattr(pc, "row", None))
                       if pc is not None else None),
           "a_Decoy": has_trait(tn, UnitTrait.Decoy), "a_Summon": has_trait(tn, UnitTrait.Summon),
           "traits": sorted(tn)[:12]}

    # ---- DECOMPOSITION PAR ETAGE de l'ARBRE DSL du port, sur le MEME etat -------------------
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.entities.selectors.units import AdjacentFriends
    from engine.entities.selectors.accessors import Owner
    from engine.dsl.base import Const, _within, _is_alive, _feet
    ctx = entities_from_state(st, int(carrier_id))
    cu = next((u for u in ctx.units if u.get("id") == int(carrier_id)), None)
    iu = next((u for u in ctx.units if u.get("id") == int(uid)), None)
    out["dans_ctx_units"] = iu is not None
    # `_is_alive(u)` = `alive AND hp > 0` : les DEUX doivent etre publies pour que le filtre de
    # `_within` soit imputable. Un `hp` absent rend `(None or 0) > 0` = False, donc une unite
    # VIVANTE disparait de tout selecteur d'occupation -- sans erreur.
    out["ctx_intrus"] = (None if iu is None else
                         {"pos": iu.get("pos"), "team": iu.get("team"),
                          "alive": iu.get("alive"), "hp": iu.get("hp"),
                          "visualId": iu.get("visualId"), "_is_alive": _is_alive(iu),
                          "feet": iu.get("feet")})
    out["ctx_porteur"] = (None if cu is None else
                          {"pos": cu.get("pos"), "team": cu.get("team")})
    cpos = _pos(cu) if cu is not None else (None, None)
    tid = (ctx.board.id_at(cpos[0], cpos[1])
           if ctx.board is not None and cpos[0] is not None else None)
    out["tuile_porteur_port"] = tid
    # LE substrat du port pour `order='adjacent'` : la liste STOCKEE, telle que `boardGraph` l'a
    # captee. C'est elle qu'il faut confronter au ring `selector` mesure cote natif.
    out["neighbours_native_port"] = (None if tid is None else
                                     sorted(ctx.board.coord(v)
                                            for v in ctx.board.neighbours_native(tid)))
    out["_feet_intrus"] = None if iu is None else _feet(iu)
    ring = _within(ctx.units, cu, 1, board=ctx.board, order="adjacent")
    out["_within_ids"] = sorted(u.get("id") for u in ring)
    # QUI le filtre `_is_alive` retire du ring : la liste des unites dont un pied EST dans le ring
    # mais que `_within` refuse. C'est l'accusation NOMMEE, au lieu d'un ensemble vide sans cause.
    tset = {tuple(t) for t in (out.get("neighbours_native_port") or [])}
    out["retires_par_is_alive"] = [
        (u.get("id"), u.get("visualId"), u.get("hp"), u.get("alive"))
        for u in ctx.units
        if not _is_alive(u) and any(f in tset for f in _feet(u))]
    out["adjacent_friends_ids"] = sorted(
        u.get("id") for u in AdjacentFriends(Owner(), Const(1), Owner()).select(ctx))
    return out


def monter(a, AM, Board, Harness, rpc, tag):
    """Construit un runner, amene mon tour, choisit le plan et pose porteur / attaquant.

    Rend `(h, rid, sf, anchor, geo, contact, stocke, loins, carrier, att, comps, porteurs)`.
    Les compagnons ne sont PAS places ici : chaque bras decide ou il les veut."""
    import argparse as _ap
    from engine.entities.traits.unit_trait import UnitTrait
    ns = _ap.Namespace(seed=a.seed, board=a.board, crit_damage=a.crit_damage,
                       trait=a.trait, geo_only=True, verbose=False)
    rid, sf = AM.build(ns, tag, a.level)
    if rid is None:
        raise MontageError("le build a echoue (voir la ligne `build KO` ci-dessus)")
    bg = rpc("boardGraph", {"runnerId": rid}, 120)
    h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
    dv = h.dview()
    att = h.by_visual(AM.ATTACKER, dv)
    if att is None:
        raise MontageError("attaquant absent du deploiement")
    h.my_player = att.get("owner")
    if h.reach_my_turn(force_cycle=True) is None:
        raise MontageError("mon tour non atteint")
    dv = h.dview()
    att, carrier = h.by_visual(AM.ATTACKER, dv), h.by_visual(AM.CARRIER, dv)
    comps = [h.by_visual(c, dv) for c in AM.COMPANIONS]
    if att is None or carrier is None or any(c is None for c in comps):
        raise MontageError("une unite du montage est absente du deploiement")
    pilotees = {carrier["id"], att["id"]} | {c["id"] for c in comps}
    occupe = {_pos(u) for u in h.alive(dv)
              if u.get("id") not in pilotees and _pos(u)[0] is not None}
    plan = choisir_plan(h.board, occupe, _coord(a.anchor), _coord(a.geo))
    if plan is None:
        raise MontageError("aucun plan (ancre, voisin hex-1 hors liste stockee, 2 voisins "
                           "stockes libres, 3 tuiles a hex >= 4) sur ce board")
    anchor, geo, nat_libres, loins = plan
    if not h.place(carrier["id"], anchor):
        raise MontageError("placement du porteur refuse")
    occ = {_pos(u) for u in h.alive()}
    contact = next((c for c in nat_libres if c not in occ and h.place(att["id"], c)), None)
    if contact is None:
        raise MontageError("placement de l'attaquant refuse (candidats %s)" % (nat_libres,))
    occ = {_pos(u) for u in h.alive()}
    stocke = next((c for c in nat_libres if c != contact and c not in occ), None)
    if stocke is None:
        raise MontageError("aucun voisin STOCKE libre pour le controle positif")
    porteurs = inventaire_traits(h, (int(UnitTrait.Summon), int(UnitTrait.Decoy)), h.dview())
    return (h, rid, sf, anchor, geo, contact, stocke, loins, carrier, att, comps, porteurs)


def pousser_loin(h, ids, loins, quoi):
    """DEPLACE les unites vers des tuiles a hex >= 4 du porteur -- on force la configuration, on
    ne subit pas la geometrie de spawn."""
    for uid in ids:
        occ = {_pos(u) for u in h.alive()}
        dest = next((c for c in loins if c not in occ and h.place(uid, c)), None)
        if dest is None:
            raise MontageError("impossible d'eloigner u%s (%s)" % (uid, quoi))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="C3_14")
    ap.add_argument("--level", type=int, default=6, help="niveau de la RELIQUE (1..10)")
    ap.add_argument("--crit-damage", type=int, default=2000)
    ap.add_argument("--anchor", default="5,4", help="col,row du PORTEUR (vide = derive du board)")
    ap.add_argument("--geo", default="5,3",
                    help="col,row du compagnon hex-1 HORS liste stockee (vide = derive)")
    ap.add_argument("--trait", default="Decoy")
    ap.add_argument("--bras", default="tous", choices=("tous", "sequence", "repro"),
                    help="`sequence` = inventaire + activite differentielle + valeur sur un "
                         "voisin STOCKE (1 runner) ; `repro` = les deux bras de reproduction de "
                         "`case-589` sec.6 (2 runners). Le verdict COMPLET exige `tous`.")
    a = ap.parse_args()

    import rl_collect_batch as R
    import probe_589r1r1r2r1_amulet_crit_reduction_live as AM
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    from engine.runner import snapshot as SNAP
    from engine.runner.snapshot import clear_ability_states_cache

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        r = R._rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    # CANAL RELIQUE : sans transport ambiant, `triggered_ability_state` retombe sur le couple
    # PASSIF et le port lirait `critDmgReduction` au dernier palier (cf. `case-589` sec.5).
    SNAP.bind_live_rpc(rpc)

    paliers = AM.paliers_du_gameconfig()
    if not (1 <= a.level <= len(paliers)):
        raise SystemExit("niveau %d hors des %d paliers" % (a.level, len(paliers)))
    print("== #589-r1-r1-r2-r1-r8 -- ce que le natif COMPTE (board %s, niveau %d -> %d)"
          % (a.board, a.level, paliers[a.level - 1]))

    resultats = {}
    rc = 0

    def bras(tag, corps):
        """Un runner par bras -- une seconde `applyAction ability` sur le meme runner revient
        `mutated: false` (mesure)."""
        m = monter(a, AM, Board, ChargeRegimeHarness, rpc, tag)
        h, rid, sf = m[0], m[1], m[2]
        print("   [%s] runner %s" % (tag, rid))
        try:
            return corps(*m)
        finally:
            clear_ability_states_cache("build#%s" % rid)
            rpc("disposeRunner", {"runnerId": rid}, 30)
            Path(sf).unlink(missing_ok=True)

    # ---- BRAS 1 : inventaire + activite DIFFERENTIELLE + valeur sur un voisin STOCKE -----------
    def bras_sequence(h, rid, sf, anchor, geo, contact, stocke, loins, carrier, att, comps,
                      porteurs):
        print("")
        print("=== 1. inventaire NATIF des porteurs de Summon/Decoy (combatSnapshot.traits) ===")
        print("   porteur de la relique : u%s (%s) owner=%s pos=%s"
              % (carrier["id"], AM.CARRIER, carrier.get("owner"), _pos(carrier)))
        print("   ancre=%s | GEO=%s (hex 1, HORS liste stockee) | STOCKE=%s | contact=%s"
              % (anchor, geo, stocke, contact))
        pilotes = {c["id"] for c in comps}
        intrus = []
        for p in porteurs:
            ami = p.get("owner") == carrier.get("owner")
            role = ("compagnon du montage" if p["id"] in pilotes
                    else ("INTRUS ami" if ami else "porteur ENNEMI (hors `Friends`)"))
            if ami and p["id"] not in pilotes and p["id"] != carrier["id"]:
                intrus.append(p)
            print("   u%-4s %-18s traits=%s owner=%s pos=%-8s alive=%s  <- %s"
                  % (p["id"], p["visualId"], p["traits_comptes"], p.get("owner"),
                     p.get("pos"), p.get("alive"), role))
        resultats["intrus"] = [(p["id"], p["visualId"], p["pos"]) for p in intrus]
        ring0 = ring_natif(h, carrier["id"])
        resultats["ring"] = ring0
        print("   ring `selector` du porteur (AdjacentTiles(Owner)) : %s" % (ring0,))
        for p in intrus:
            print("   [!] u%s (%s) est AMI, porte %s, et sa tuile %s est %s le ring."
                  % (p["id"], p["visualId"], p["traits_comptes"], p["pos"],
                     "DANS" if p["pos"] in (ring0 or []) else "hors de"))

        mobile, fixe = comps[0], comps[1]
        pousser_loin(h, [mobile["id"], fixe["id"]] + [p["id"] for p in intrus if p.get("alive")],
                     loins, "porteur de trait")
        loin = _pos(h.by_visual(AM.COMPANIONS[0]))

        print("")
        print("=== 2. activite DIFFERENTIELLE (seul u%s bouge) ===" % mobile["id"])
        mes = {}
        for nom, dest, attendu in (("S0 TEMOIN", loin, False), ("S1 GEO   ", geo, None),
                                   ("S2 STOCKE", stocke, True), ("S3 RETOUR", loin, False)):
            if not h.place(mobile["id"], dest):
                raise MontageError("%s : placement en %s refuse" % (nom.strip(), dest))
            reel = _pos(h.by_visual(AM.COMPANIONS[0]))
            if reel != dest:
                raise MontageError("%s : u%s est en %s, pas en %s"
                                   % (nom.strip(), mobile["id"], reel, dest))
            act = activite(h, carrier["id"])
            ring = ring_natif(h, carrier["id"])
            mes[nom.strip()] = {"pos": reel, "actif": act,
                                "dans_ring": None if ring is None else (reel in ring)}
            marque = "" if attendu is None or act == attendu else "   <== INATTENDU"
            print("   %s pos=%-8s actif_natif=%-5s dans AdjacentTiles(Owner)=%-5s%s"
                  % (nom, reel, act, mes[nom.strip()]["dans_ring"], marque))
        resultats["sequence"] = mes
        s0, s1, s2, s3 = (mes["S0 TEMOIN"], mes["S1 GEO"], mes["S2 STOCKE"], mes["S3 RETOUR"])
        if any(x["actif"] is None for x in (s0, s1, s2, s3)):
            raise MontageError("l'effet est ABSENT du canal decisionView -- la relique n'est pas "
                               "montee, rien n'est mesure ici")
        if s0["actif"] or s3["actif"]:
            raise MontageError("TEMOIN NON NUL en defaut : l'effet est actif avec TOUS les "
                               "porteurs a hex >= 4 (S0=%s S3=%s) -- une AUTRE cause l'allume"
                               % (s0["actif"], s3["actif"]))
        if not s2["actif"]:
            raise MontageError("CONTROLE POSITIF en defaut : un compagnon sur un voisin STOCKE "
                               "n'active pas l'effet -- le canal ne mord pas sur ce montage")
        print("")
        print("=== 3. VALEUR du compteur, lue du DEGAT (modeles entiers 0/1/2/3) ===")
        if not h.place(mobile["id"], stocke):
            raise MontageError("re-pose du compagnon en %s refusee" % (stocke,))
        n, np_, _ = mesurer_n(h, AM, "1 compagnon sur un voisin STOCKE", anchor, contact)
        resultats["n_stocke"], resultats["n_stocke_port"] = n, np_

    # ---- BRAS 2 et 3 : reproduction du montage de `case-589` sec.6, INTRUS LAISSE EN PLACE -----
    def bras_repro(place_compagnon_en_geo):
        def corps(h, rid, sf, anchor, geo, contact, stocke, loins, carrier, att, comps, porteurs):
            # L'intrus n'est PAS touche : il respawne a sa place (seed deterministe).
            pilotes = {c["id"] for c in comps}
            intrus = [p for p in porteurs
                      if p.get("owner") == carrier.get("owner") and p["id"] not in pilotes
                      and p["id"] != carrier["id"]]
            if not intrus:
                raise MontageError("aucun intrus a ce montage -- le bras REPRO ne reproduit rien")
            pousser_loin(h, [comps[0]["id"], comps[1]["id"]], loins, "compagnon")
            if place_compagnon_en_geo and not h.place(comps[0]["id"], geo):
                raise MontageError("placement du compagnon en %s refuse" % (geo,))
            reel = _pos(h.by_visual(AM.COMPANIONS[0]))
            etiq = ("intrus + compagnon en %s" % (geo,) if place_compagnon_en_geo
                    else "intrus SEUL, compagnons LOIN")
            print("   intrus u%s en %s | compagnon en %s | actif_natif=%s"
                  % (intrus[0]["id"], intrus[0]["pos"], reel, activite(h, carrier["id"])))
            # LA SANTE, cote NATIF : si le natif donne AUSSI 0 PV a cette unite, alors une unite
            # VIVANTE A 0 PV existe et c'est le filtre du port qui est faux ; si le natif lui en
            # donne, c'est la CAPTURE du port qui perd la stat. Deux foyers differents.
            snp = h.rpc("combatSnapshot", {"runnerId": h.rid}, 60)
            su = next((u for u in (snp.get("units") or [])
                       if u.get("entityId") == intrus[0]["id"]), None)
            obs = h.rpc("observeBattle", {"runnerId": h.rid}, 40)
            ou = next((u for u in (obs.get("units") or [])
                       if u.get("id") == intrus[0]["id"]), None)
            dvu = next((u for u in h.alive() if u.get("id") == intrus[0]["id"]), None)
            print("      SANTE NATIVE de u%s : combatSnapshot.stats.health=%s healthMax=%s | "
                  "observeBattle hp=%s hpMax=%s isDead=%s | decisionView hp=%s alive=%s"
                  % (intrus[0]["id"], ((su or {}).get("stats") or {}).get("health"),
                     (su or {}).get("healthMax"), (ou or {}).get("hp"), (ou or {}).get("hpMax"),
                     (ou or {}).get("isDead"), (dvu or {}).get("hp"), (dvu or {}).get("alive")))
            n, n_port, rec = mesurer_n(h, AM, etiq, anchor, contact)
            d = diag_port_unite(h, AM, rec, intrus[0]["id"], carrier["id"])
            print("      PORT voit l'INTRUS u%s : %s" % (intrus[0]["id"], d))
            rn = ring_natif(h, carrier["id"])
            rp = d.get("neighbours_native_port")
            print("      ring NATIF (selector) = %s" % (rn,))
            print("      ring PORT (neighbours_native) = %s" % (rp,))
            if rn is not None and rp is not None:
                print("      NATIF \\ PORT = %s | PORT \\ NATIF = %s"
                      % (sorted(set(rn) - set(rp)), sorted(set(rp) - set(rn))))
            return n, n_port
        return corps

    if a.bras in ("tous", "sequence"):
        bras("r8seq", bras_sequence)
    if a.bras in ("tous", "repro"):
        print("")
        print("=== 4. REPRODUCTION de `case-589` sec.6 -- l'intrus RESTE a sa place ===")
        resultats["n_repro"], resultats["n_repro_port"] = bras("r8rep0", bras_repro(False))
        resultats["n_repro_geo"], resultats["n_repro_geo_port"] = bras("r8repg", bras_repro(True))
    if a.bras != "tous":
        print("")
        print("=== BRAS PARTIEL `%s` -- aucun verdict complet (relancer sans --bras) ===" % a.bras)
        return 2

    # ---- verdict ---------------------------------------------------------------------------
    s = resultats["sequence"]
    s1 = s["S1 GEO"]
    print("")
    print("=== VERDICT ===")
    if s1["actif"] and s1["dans_ring"] is False:
        print("Le natif COMPTE un compagnon que `AdjacentTiles(Owner)` ne rend PAS.")
        print("  -> `case-589` sec.6 tient, et le capteur `adjacentTilesNative` mesure autre")
        print("     chose que ce que le selecteur consomme. A instruire cote CAPTEUR.")
        rc = 1
    elif not s1["actif"]:
        print("Le natif NE COMPTE PAS le compagnon hex-1 hors liste stockee.")
        print("  S0/S3 inactifs, S2 actif : le canal mord, et seule l'appartenance a la LISTE")
        print("  STOCKEE fait basculer la condition.")
    else:
        print("S1 actif ET dans le ring : le montage n'est pas dans le regime voulu.")
        rc = 2
    nr, ng = resultats.get("n_repro"), resultats.get("n_repro_geo")
    if nr is not None and ng is not None:
        if ng == nr:
            print("  REPRODUCTION : n = %d avec l'intrus SEUL, n = %d en AJOUTANT le compagnon" % (nr, ng))
            print("  en hex 1 hors liste stockee -- il n'ajoute RIEN. Le `1` de la fiche etait")
            print("  celui de l'INTRUS %s, et l'accord de son bras `--geo-only` etait un accord"
                  % (resultats["intrus"][0][1] if resultats["intrus"] else "?",))
            print("  par COMPENSATION : deux causes differentes, le meme 1.")
        else:
            print("  REPRODUCTION : n passe de %d a %d en ajoutant le compagnon -- il COMPTE."
                  % (nr, ng))
            rc = 1
    else:
        print("  REPRODUCTION : compteur non determine (n_repro=%s n_repro_geo=%s)" % (nr, ng))
        rc = 2
    print("   S0=%s S1=%s S2=%s S3=%s | n(STOCKE)=%s n(intrus seul)=%s n(intrus+geo)=%s"
          % (s["S0 TEMOIN"]["actif"], s1["actif"], s["S2 STOCKE"]["actif"],
             s["S3 RETOUR"]["actif"], resultats.get("n_stocke"), nr, ng))
    # L'ECART QUI RESTE : le port compte-t-il ce que le natif compte ? La question de
    # `#589-r1-r1-r2-r1-r7` reste ouverte tant que les deux colonnes different, meme si son
    # ATTRIBUTION (le compagnon en hex 1) est refutee ci-dessus.
    ecarts = [(k, resultats.get(k), resultats.get(k + "_port"))
              for k in ("n_stocke", "n_repro", "n_repro_geo")
              if resultats.get(k) != resultats.get(k + "_port")]
    print("   compteur NATIF vs PORT : %s"
          % ({k: (resultats.get(k), resultats.get(k + "_port"))
              for k in ("n_stocke", "n_repro", "n_repro_geo")}))
    if ecarts:
        print("  [!] ECART NATIF/PORT sur %s -- le port ne compte pas ce que le natif compte."
              % ([e[0] for e in ecarts],))
        rc = 1
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MontageError as e:
        print("MONTAGE : %s" % e)
        sys.exit(2)
