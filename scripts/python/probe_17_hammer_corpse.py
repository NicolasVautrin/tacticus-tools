#!/usr/bin/env python
"""probe_17_hammer_corpse -- MONTAGE NOMME du filtre VIVANT des cibles secondaires de HammerOfWrath
(1153) sur la face DECISION.

CE QUE MESURE CE MONTAGE. `make_hammer_wrath_events` (engine/playbook/prediction/abilities.py) est le
chemin de scoring NonComparable de HammerOfWrath : il ajoute un event de degat par ennemi ADJACENT A LA
CIBLE. Le natif ne « filtre pas les morts » : il ne les VOIT pas, parce que ses cibles secondaires sont
resolues par OCCUPATION DE TUILE --

    IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$ExecuteBehaviour
      -> IdunBattleLogic.Entities.DSLSelectors$$Enemies( caster,
           IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(target, unique, kind) )
    IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(origin, ...) =
           Units( AdjacentTiles(origin), ... )  -  origin
    IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select = selecteur de TUILES (@+0x18) resolu
           dans le mode d'occupation (@+0x20) -> une unite morte n'est plus sur une tuile.

NOTRE substrat, lui, GARDE les cadavres : `scene.pos_by_id` vient de `decisionView.units`, qui conserve
les unites mortes a leur derniere position (cf. `decisionview-keeps-dead`). Le mirror fidele est donc le
filtre explicite `(scene.hp(u) or 0) > 0` de la boucle des adjacents. Sans lui, un CADAVRE hex-adjacent
a la cible entre dans le scan avec hp=0 -> `kill`/`killSure` vrais -> composite Damage ~ +120 d'utilite
FANTOME (mesure d'origine : 54321 s8, cadavre u95, #57k/#57m de docs/rl/case-52-generalisation.md).

CE MONTAGE NE SUBIT PAS LA GEOMETRIE, IL LA DRIVE (le `--center` n'est qu'un INDICE : si la tuile
demandee ne porte pas la configuration, le montage en choisit une qui la porte, et la rend dans son
resultat) : la cible est posee au centre, un ennemi SACRIFIABLE
et un ennemi TEMOIN sur son ring 1, Mataneo egalement adjacent (position de cast), puis le sacrifiable
est TUE pour de bon par un allie. DEUX REGIMES, qui ne cassent pas de la meme facon :

  * `witness`     -- cadavre ET temoin vivant adjacents : le port doit rendre {cible, temoin} ; un scan
                     sans filtre rendrait TROIS events. Le temoin interdit de confondre « filtre » et
                     « scan vide ».
  * `corpse-only` -- le temoin est envoye au loin : le SEUL adjacent de la cible est le CADAVRE. Le port
                     doit rendre le SEUL event principal ; un scan sans filtre en rendrait deux. C'est le
                     regime ou la difference est BINAIRE (secondaires : 0 contre 1).

On mesure ensuite, sur l'etat capture :

  * la CENSURE du montage      -- le cadavre est bien dans `scene.pos_by_id`, a distance hex 1 de la
                                  cible, camp adverse : le scan naif le VERRAIT (sans ca l'assertion
                                  serait vide de sens) ;
  * le SET d'events du port    -- doit etre {cible, temoin}, sans le cadavre ;
  * la MAGNITUDE retiree       -- l'utilite qu'aurait apportee l'event fantome du cadavre, calculee par
                                  un INSTRUMENT du probe (`_secondary_event`) AUTO-VERIFIE : applique au
                                  temoin VIVANT il doit reproduire au bit pres l'event que le port a
                                  produit pour lui.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_17_hammer_corpse.py [--case witness|corpse-only|all] [--seed 17153] [--board MC1_67]

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

HAMMER_OF_WRATH = 1153
NORMAL_ATTACK = 69                # `Loki_NormalAttack` (id CONCRET, cf. NormalAttackType@0x28)
BOARD = "MC1_67"
RANK = 17
CENTER = (3, 4)

CARRIER = "bloodIntercessor"      # Mataneo -- le seul porteur de HammerOfWrath (1153)
KILLER = "ultraInceptorSgt"       # allie : fabrique le CADAVRE (Mataneo garde son tour intact)
TARGET = "genesPrimus"            # cible du Hammer, au centre
CORPSE = "astraBullgryn"          # SACRIFIABLE : tue sur une tuile hex-adjacente a la cible
WITNESS = "necroWarden"           # TEMOIN VIVANT adjacent -- sans lui, un set vide passerait la garde
FILLER = "necroOverlord"          # tenu au loin : la bataille doit continuer apres le kill

HP_TARGET = 400                   # PV de TOUTES les a-units (`--hp-target`) : un coup normal tue

CASES = ("witness", "corpse-only")
# Distance minimale (hex) a laquelle on EXILE une unite : au-dela de 2 elle ne peut etre ni sur le ring
# de la cible, ni sur celui du sacrifiable -> elle ne pollue aucun des deux scans.
EXILE_MIN_DIST = 3


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(sid, state_file: Path, seed: int, board: str) -> int:
    """`rl_duel build` avec rosters CHOISIS, PV bas (kill deterministe) et alea neutralise."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    p_units = [CARRIER, KILLER]
    a_units = [TARGET, CORPSE, WITNESS, FILLER]
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", board, "--rank", str(RANK),
         "--p-units", ",".join(p_units), "--a-units", ",".join(a_units),
         "--hp-target", str(HP_TARGET), "--crit", "0,0", "--block-target", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-500:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)


def _by_visual(dv, vis):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis:
            return u
    return None


def _move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _attack(sid, rid, attacker, target, ability=NORMAL_ATTACK):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(attacker), "targetId": int(target),
        "abilityType": int(ability)}}, 120)


def _my_player(dv):
    """`owner` du camp CONTROLE (`ctrl == True`) -- l'id de deploiement n'est pas celui du tour."""
    for u in (dv.get("units") or []):
        if u.get("ctrl"):
            return u.get("owner")
    return dv.get("currentPlayer")


def _next_turn(sid, rid, me, max_steps=8):
    """Passe au tour suivant de MON camp sans faire jouer l'IA (geometrie figee). 1er `endturn`
    INCONDITIONNEL : Mataneo est en Deep Strike (TeleportStrike) et n'ATTERRIT qu'en fin de son 1er
    tour -- sans atterrissage ses passives (dont l'owner-effect 1332) ne sont jamais initialisees."""
    _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    for _ in range(max_steps):
        dv = _view(sid, rid)
        if dv.get("currentPlayer") == me:
            return dv
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    return _view(sid, rid)


def _positions(dv):
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        if p.get("col") is not None:
            out[u["id"]] = (p["col"], p["row"])
    return out


def _walkable_tiles(brd):
    """Tuiles PRATICABLES et connectees du board (`walkable` est une PROPRIETE de tuile : un mur n'est
    pas une arete manquante)."""
    out = []
    for tid, t in brd.by_id.items():
        c, r = t.get("col"), t.get("row")
        if c is None or r is None or not t.get("walkable") or t.get("isWall"):
            continue
        if not brd.neighbours(tid):
            continue
        out.append((c, r))
    return out


def _exile_tiles(brd, center, n, avoid):
    """`n` tuiles praticables a >= EXILE_MIN_DIST du centre, hors `avoid` -- l'exil est DERIVE du board,
    pas code en dur, pour que le montage se rejoue tel quel sur un autre couple board/centre."""
    out = [p for p in _walkable_tiles(brd)
           if hexgeo.distance(p, center) >= EXILE_MIN_DIST and p not in avoid]
    if len(out) < n:
        raise RuntimeError("board trop petit : %d tuiles d'exil libres a >= %d du centre %s "
                           "(il en faut %d)" % (len(out), EXILE_MIN_DIST, center, n))
    return out[:n]


def _drive(sid, rid, brd, plan, max_rounds=8, verbose=False):
    """Applique un plan {unitId: (col,row)} et le VERIFIE, en MINIMISANT le nombre de `move` par unite.

    Deux pieges, tous deux MESURES :
      * un `move` vers une tuile encore OCCUPEE echoue SILENCIEUSEMENT (`ok:true, mutated:null`) --
        d'ou la verification finale : sans elle une geometrie ratee se lit plus loin comme un resultat ;
      * deux unites qui doivent ECHANGER leurs tuiles se bloquent indefiniment (le porteur et le filler
        sur MC1_63) -- on GARE alors UNE des deux sur une tuile tampon pour casser le cycle.
    Et un piege de la parade naive : garer TOUT LE MONDE d'office fait bouger chaque unite DEUX fois,
    ce qui epuise le tour du tueur (mesure : son attaque repond `mutated:null`, aucun cadavre). On ne
    gare donc que ce qui bloque."""
    targets = {tuple(p) for p in plan.values()}
    placed: dict = {}
    for rnd in range(max_rounds):
        placed = _positions(_view(sid, rid))
        todo = [(u, tuple(p)) for u, p in plan.items() if placed.get(u) != tuple(p)]
        if verbose:
            print("[17]   drive round %d : todo=%s" % (rnd, todo))
        if not todo:
            return placed
        occ = {q: u for u, q in placed.items()}
        moved = False
        for uid, p in todo:
            if p in occ:
                continue
            _move(sid, rid, uid, p[0], p[1])
            occ.pop(placed.get(uid), None)
            occ[p] = uid
            placed[uid] = p
            moved = True
        if moved:
            continue
        uid, p = todo[0]                       # cycle : degager l'occupant de la 1re destination
        other = occ.get(p)
        spot = next((t for t in _walkable_tiles(brd) if t not in occ and t not in targets), None)
        if verbose:
            print("[17]   drive cycle : garer u%s -> %s" % (other, spot))
        if other is None or spot is None:
            break
        _move(sid, rid, other, spot[0], spot[1])
    placed = _positions(_view(sid, rid))
    bad = {u: (placed.get(u), tuple(p)) for u, p in plan.items() if placed.get(u) != tuple(p)}
    if bad:
        raise RuntimeError("drive de positions NON APPLIQUE (obtenu, voulu) : %s" % bad)
    return placed


def _scene_of(sid, rid, dv):
    """Scene du seam de DECISION -- EXACTEMENT le substrat ou vivait le trou : `step_context` derive
    `pos_by_id` de `decisionView.units`, qui CONSERVE les cadavres."""
    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene
    def rpc_l(m, b, t=60):
        return _r(sid, m, b, t)
    predictor = SC.build_predictor(rpc_l, rid)
    if predictor is None:
        raise RuntimeError("build_predictor KO (combatSnapshot indisponible)")
    SC.refresh_shields(predictor, rpc_l, rid)
    return Scene.from_predictor_sctx(predictor, SC.step_context(predictor, dv))


def _secondary_event(scene, caster_id, tgt_id, attack_pos):
    """INSTRUMENT DU PROBE (pas du port) : recompose l'event SECONDAIRE de Hammer pour UNE unite, avec
    les MEMES entrees que `make_hammer_wrath_events` -- base `minDmg_2` (var 54,
    IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$GetMinDamage2), hits
    `nrOfHits_2` (const 50), profil `damageProfile_2`.

    Il sert a CHIFFRER ce que le filtre vivant retire (un cadavre n'a plus d'event, donc le port ne peut
    pas le rendre). Il est AUTO-VERIFIE par le probe : applique a un TEMOIN VIVANT il doit reproduire au
    bit pres l'event que le port a produit pour ce temoin -- sinon l'instrument est faux et la magnitude
    ne veut rien dire."""
    import gameconfig as GC
    from engine.entities.abilities.ability_configuration import AbilityConfiguration
    from engine.entities.abilities.active_ability import active_ability_for
    from engine.playbook.prediction.abilities import generate_multi_hit_attack_prediction
    from engine.playbook.probable_damage_event import ProbableDamageEvent
    name = "HammerOfWrath"
    ctx0 = scene.ctx(caster_id)
    cfg = AbilityConfiguration.from_gameconfig(name, GC.ability(name))
    if ctx0 is None or cfg is None:
        return None
    ab = active_ability_for(name, HAMMER_OF_WRATH, ctx0, cfg,
                            ability_state=scene.ability_state(caster_id, HAMMER_OF_WRATH))
    minv2 = cfg.get_variable_for_level("minDmg_2", ab.level, 0, ab.multiplier)
    consts = cfg.constants or {}
    dp = generate_multi_hit_attack_prediction(
        scene, caster_id, tgt_id, HAMMER_OF_WRATH, name, attack_pos=attack_pos,
        base_override=minv2, hits_override=max(1, int(consts.get("nrOfHits_2") or 1)),
        profile_override=consts.get("damageProfile_2"))
    return None if dp is None else ProbableDamageEvent(target=tgt_id, prediction=dp)


def _utility(ev, wt, scene):
    from engine.playbook.probable_damage_event import calculate_utility_from_damage_event
    return calculate_utility_from_damage_event(ev, wt, scene.hpmax(ev.target))


def _layout_at(brd, brd_nat, walk, occupied, center, case):
    """Plan de tuiles pour UN centre candidat, ou None si le centre ne peut pas porter le montage.

    Contraintes : 3 hex-voisins praticables (cadavre / temoin / porteur), une tuile praticable libre
    VOISINE AU SENS NATIF du cadavre (portee de melee du tueur), et 2 tuiles d'exil libres."""
    if center not in walk:
        return None
    ring = [brd.coord(t) for t in brd.neighbours(brd.id_at(*center)) if brd.coord(t) in walk]
    if len(ring) < 3:
        return None
    corpse_tile, witness_ring, carrier_tile = ring[0], ring[1], ring[2]
    try:
        far_filler, far_witness = _exile_tiles(
            brd, center, 2, avoid={center} | set(ring) | set(occupied))
    except RuntimeError:
        return None
    witness_tile = witness_ring if case == "witness" else far_witness
    taken = {center, corpse_tile, carrier_tile, witness_tile, far_filler, far_witness}
    kill_tile = next((brd_nat.coord(t) for t in brd_nat.neighbours(brd_nat.id_at(*corpse_tile))
                      if brd_nat.coord(t) in walk and brd_nat.coord(t) not in taken), None)
    if kill_tile is None:
        return None
    return {"center": center, "corpse": corpse_tile, "witness": witness_tile,
            "carrier": carrier_tile, "kill": kill_tile, "filler": far_filler}


def _layout(brd, brd_nat, walk, occupied, center, case):
    """`_layout_at` sur le centre DEMANDE ; a defaut, premier centre praticable du board qui porte le
    montage. Le centre n'est pas une entree du verdict -- seule compte la CONFIGURATION obtenue --,
    donc le rabattre vaut mieux qu'echouer, et le centre retenu est rendu dans le resultat."""
    lay = _layout_at(brd, brd_nat, walk, occupied, tuple(center), case)
    if lay is not None:
        return lay
    for c in sorted(walk):
        lay = _layout_at(brd, brd_nat, walk, occupied, c, case)
        if lay is not None:
            return lay
    raise RuntimeError("aucun centre de ce board ne porte le montage (ring praticable >= 3 + voisin "
                       "natif libre du cadavre + 2 tuiles d'exil)")


def run(case: str = "witness", seed: int = 17153, board: str = BOARD, center=CENTER,
        state_file=None, keep: bool = False, verbose: bool = True) -> dict:
    """Monte le cas, mesure, dispose. Rend un dict (ou `{"error": ...}` si le montage ne s'installe
    pas -- un montage NON INSTALLE doit ROUGIR chez l'appelant, jamais passer pour un vert)."""
    from engine import weights
    from engine.playbook.prediction.abilities import make_hammer_wrath_events
    from engine.entities.pathfinding.board import Board

    if case not in CASES:
        raise AssertionError("cas inconnu : %s (connus : %s)" % (case, sorted(CASES)))
    a_center = tuple(center)                      # centre DEMANDE (indice) -- cf. `_layout`
    center = a_center
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (ROOT / "logs" / ("probe_17_%s.json" % case))
    rid = None
    try:
        rid = _build(sid, sf, seed, board)
        if verbose:
            print("[17] %s : runner=%d seed=%d board=%s centre=%s"
                  % (case, rid, seed, board, center))
        dv = _view(sid, rid)
        _next_turn(sid, rid, _my_player(dv))          # atterrissage deep-strike de Mataneo
        dv = _view(sid, rid)

        ids = {}
        for vis in (CARRIER, KILLER, TARGET, CORPSE, WITNESS, FILLER):
            u = _by_visual(dv, vis)
            if u is None:
                raise RuntimeError("unite absente du build : %s" % vis)
            ids[vis] = u["id"]

        bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
        # DEUX lectures du meme board, et la distinction est LOAD-BEARING :
        #  * `evenq`      = adjacence HEX -- c'est `hexgeo.distance(...) == 1`, la lecture que fait
        #                   `make_hammer_wrath_events` pour ses cibles secondaires ; le montage doit
        #                   poser le cadavre adjacent AU SENS DU PORT ;
        #  * `native_sym` = le graphe de connectivite CAPTURE (`ConnectivityComponent.IsNeighbour`),
        #                   celui que le JEU consulte pour la portee de melee. Deux tuiles hex-voisines
        #                   n'y sont pas forcement voisines (mesure MC1_63 : le tueur pose sur une
        #                   hex-voisine ne pouvait pas frapper -> aucun cadavre).
        brd = Board(bg["tiles"], adjacency="evenq")
        brd_nat = Board(bg["tiles"], adjacency="native_sym")
        walk = set(_walkable_tiles(brd))

        # GEOMETRIE DRIVEE : cible au centre ; sacrifiable / Mataneo sur son ring 1 ; le tueur sur une
        # tuile VOISINE (graphe natif) du sacrifiable ; le filler exile. Le TEMOIN est adjacent
        # (`witness`) ou exile (`corpse-only`, ou le cadavre devient le SEUL adjacent de la cible).
        lay = _layout(brd, brd_nat, walk, set(_positions(dv).values()), center, case)
        center = lay["center"]
        if verbose and center != tuple(a_center):
            print("[17]   centre rabattu sur %s (le centre demande ne porte pas le montage)" % (center,))
        # ORDRE DU PLAN : les unites ADVERSES d'abord, les MIENNES ensuite. Mesure (MC1_63) : des
        # qu'une unite de MON camp a bouge, les `move` suivants sur des unites ADVERSES sont refuses
        # (silencieusement, `ok:true mutated:null`) -- l'ordre naif laissait le filler sur place.
        placed = _drive(sid, rid, brd, {
            ids[TARGET]: center, ids[CORPSE]: lay["corpse"], ids[WITNESS]: lay["witness"],
            ids[FILLER]: lay["filler"], ids[CARRIER]: lay["carrier"], ids[KILLER]: lay["kill"]},
            verbose=verbose)

        # LE CADAVRE : tue pour de bon (pas un PV force), par un ALLIE -- Mataneo garde son tour.
        last = None
        for _ in range(3):
            ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
            dead = {u["squadId"]: bool(u.get("isDead")) for u in (ob.get("units") or [])}
            if dead.get(ids[CORPSE]):
                break
            last = _attack(sid, rid, ids[KILLER], ids[CORPSE])
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        dead_by_id = {u["squadId"]: bool(u.get("isDead")) for u in (ob.get("units") or [])}
        if not dead_by_id.get(ids[CORPSE]):
            hp_by_id = {u["squadId"]: u.get("hp") for u in (ob.get("units") or [])}
            raise RuntimeError(
                "le sacrifiable u%s @%s n'est pas mort (hp=%s) -- pas de cadavre, le montage ne "
                "mesure rien. Tueur u%s @%s (d=%s), derniere reponse applyAction=%s"
                % (ids[CORPSE], placed.get(ids[CORPSE]), hp_by_id.get(ids[CORPSE]), ids[KILLER],
                   placed.get(ids[KILLER]),
                   hexgeo.distance(placed[ids[KILLER]], placed[ids[CORPSE]]),
                   {k: last.get(k) for k in ("ok", "mutated", "error")} if last else None))

        dv = _view(sid, rid)
        scene = _scene_of(sid, rid, dv)
        wt = weights.load()
        caster, target = ids[CARRIER], ids[TARGET]
        cpos, tpos = scene.pos(caster), scene.pos(target)
        if cpos is None or tpos is None:
            raise RuntimeError("caster/cible sans position dans la scene (%s / %s)" % (cpos, tpos))

        # CENSURE DU MONTAGE : ce que le scan NAIF (sans filtre vivant) verrait autour de la cible.
        naive_adj = sorted(
            u for u in scene.pos_by_id
            if u != target and scene.team(u) != scene.team(caster)
            and scene.pos(u) is not None and hexgeo.distance(scene.pos(u), tpos) == 1)
        corpse_seen = ids[CORPSE] in naive_adj
        witness_seen = ids[WITNESS] in naive_adj

        events = make_hammer_wrath_events(scene, caster, target, cpos) or []
        ev_targets = [e.target for e in events]
        ev_util = {e.target: _utility(e, wt, scene) for e in events}

        # MAGNITUDE : l'event FANTOME qu'un scan sans filtre aurait ajoute pour le cadavre, mesure par
        # l'instrument du probe. Auto-verification sur le temoin VIVANT d'abord.
        probe_witness = _secondary_event(scene, caster, ids[WITNESS], cpos)
        probe_witness_u = None if probe_witness is None else _utility(probe_witness, wt, scene)
        probe_corpse = _secondary_event(scene, caster, ids[CORPSE], cpos)
        probe_corpse_u = None if probe_corpse is None else _utility(probe_corpse, wt, scene)

        out = {
            "case": case, "rid": rid, "seed": seed, "board": board, "center": center, "ids": ids,
            "caster": caster, "target": target, "corpse": ids[CORPSE], "witness": ids[WITNESS],
            # Ce que le port DOIT rendre : l'event principal + les adjacents VIVANTS. La vivacite est
            # lue de la VERITE LIVE (`observeBattle.isDead`), JAMAIS du predicat que la garde eprouve --
            # sinon l'attendu bougerait avec le code teste et n'attesterait plus rien.
            "expected_event_targets": sorted(
                {target} | {u for u in naive_adj if not dead_by_id.get(u, False)}),
            "caster_pos": cpos, "target_pos": tpos,
            "corpse_pos": scene.pos(ids[CORPSE]), "witness_pos": scene.pos(ids[WITNESS]),
            "corpse_hp": scene.hp(ids[CORPSE]), "witness_hp": scene.hp(ids[WITNESS]),
            "corpse_is_dead": bool(dead_by_id.get(ids[CORPSE])),
            "naive_adj": naive_adj, "corpse_seen_by_naive_scan": corpse_seen,
            "witness_seen_by_naive_scan": witness_seen,
            "event_targets": ev_targets, "event_utility": ev_util,
            "sum_utility": sum(ev_util.values()),
            "probe_witness_utility": probe_witness_u,
            "port_witness_utility": ev_util.get(ids[WITNESS]),
            "ghost_corpse_utility": probe_corpse_u,
        }
        if verbose:
            print("[17] %s : caster u%d @%s | cible u%d @%s" % (case, caster, cpos, target, tpos))
            print("[17]   cadavre u%d @%s hp=%s isDead=%s | temoin u%d @%s hp=%s"
                  % (ids[CORPSE], out["corpse_pos"], out["corpse_hp"], out["corpse_is_dead"],
                     ids[WITNESS], out["witness_pos"], out["witness_hp"]))
            print("[17]   scan NAIF (sans filtre vivant) autour de la cible : %s "
                  "(cadavre vu=%s, temoin vu=%s)" % (naive_adj, corpse_seen, witness_seen))
            print("[17]   events du PORT : %s  attendu=%s  (Sigma u=%.4f)"
                  % (ev_targets, out["expected_event_targets"], out["sum_utility"]))
            for t, u in sorted(ev_util.items()):
                print("[17]      ev u%-4d u=%+.4f" % (t, u))
            print("[17]   instrument : temoin port=%s probe=%s | FANTOME cadavre=%s"
                  % (out["port_witness_utility"], probe_witness_u, probe_corpse_u))
        return out
    except RuntimeError as exc:
        return {"error": str(exc)}
    finally:
        if rid is not None and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            if verbose:
                print("[17] runner %d dispose" % rid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="all", choices=list(CASES) + ["all"])
    ap.add_argument("--seed", type=int, default=17153)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--center", default="%d,%d" % CENTER,
                    help="tuile 'col,row' ou est posee la cible (GENERALISATION : rejouer sur >= 2 "
                         "couples board/centre)")
    a = ap.parse_args()
    center = tuple(int(x) for x in a.center.split(","))
    rc = 0
    for c in (CASES if a.case == "all" else (a.case,)):
        r = run(case=c, seed=a.seed, board=a.board, center=center)
        if "error" in r:
            print("[17] MONTAGE NON INSTALLE (%s) : %s" % (c, r["error"]), file=sys.stderr)
            rc = 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
