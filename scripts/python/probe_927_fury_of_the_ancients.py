"""#927 -- `FuryOfTheAncients` (`TriggeredAbilityType` 0x4df = 1247), le passif de `bloodMephiston`
<< Mephiston >>, CONFRONTE AU LIVE.

CE QUE CE PROBE MESURE. Le passif n'etait dans AUCUN des registres de trigger : offline, Mephiston
terminait son activation SANS frapper personne et SANS poser son blocage de soin -- ni erreur, ni
crash. Trois observables INDEPENDANTS, quand il termine son activation a cote d'un ennemi :

  (a) QUI est frappe -- le natif frappe **DEUX** unites (la cible du tri + un ennemi adjacent A
      ELLE), pas une ; un port qui ne materialiserait pas la chaine n'en frapperait qu'une ;
  (b) COMBIEN chacune perd -- le tri par `DamagePredictionFormula` consomme 2 tirages PRNG par
      candidat AVANT l'attaque, donc l'accord bit-exact des PV exerce aussi cet alignement ;
  (c) QUI porte l'effet 1320 `FuryOfTheAncients` apres coup -- le blocage de soin
      (`HealBlockingEffect`), qui doit atterrir sur CHAQUE maillon de la chaine.

⚠ LE REGIME COMPTE, ET IL COMPTE DEUX FOIS. Il faut que la tuile d'arrivee soit adjacente a un
ennemi (sinon le trigger ne fire pas) ET que cet ennemi ait lui-meme un autre ennemi adjacent
(sinon la CHAINE est degeneree : `GetSecondTargetSelector` rend vide, le natif ne frappe qu'une
cible, et un port qui aurait lu `maxTargets = 0` passerait). `run()` publie `chain_len_live` pour
que l'appelant sache dans quel regime il a mesure, et `--prefer-chain` (defaut) trie les
destinations pour maximiser ce regime.

MONTAGE. Les positions sont CONDUITES (jamais << bloque par la geometrie de spawn >>) : on cherche
une tuile LIBRE adjacente a un ennemi qui a lui-meme un voisin ennemi, et on y DEPLACE Mephiston.
C'est ce deplacement qui publie `On(0x1c = ArrivedAtFinalTile)`
(`IdunBattle.Operations.MoveUnitOperation$$Execute`).

MEMES DEUX PIEGES DE HARNAIS que #419-r6-r2, et pour les memes raisons :
  * `Runner.apply(MoveUnitMessage(...))` NE ROUTE PAS le move hors boucle de tour -> la voie est
    `MovementHandler.visit_MoveUnitMessage` ;
  * `AttackDamageOperation.execute_ability_attack` SKIP le degat quand `state.rng` n'est pas cale
    -> `_capture` cale le MT live (`dumpRng`), ce dont le tri a de toute facon besoin.

ASCII only (console cp1252).

    python probe_927_fury_of_the_ancients.py [--board MC1_67] [--seed 777]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.entities.effect_type import EffectType                    # noqa: E402
from engine.entities.pathfinding.board import Board                   # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent  # noqa: E402
from engine.runner.messages import MoveUnitMessage                    # noqa: E402
from engine.runner.snapshot import load_state                         # noqa: E402

CASTER_VIS = "bloodMephiston"             # << Mephiston >>, le SEUL porteur du passif 1247
BOARD = "MC1_67"
SEED = 777
P_UNITS = "bloodMephiston,bloodIntercessor"
A_UNITS = "templChampion,templAncient,templAggressor"
FURY_EFFECT = int(EffectType.FuryOfTheAncients)      # 0x528 = 1320


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _unwrap(r):
    if isinstance(r, dict) and "result" in r:
        return r["result"]
    return r


def _live_units(rpc, rid):
    r = rpc("observeBattle", {"runnerId": rid}, 40)
    return {u["squadId"]: u for u in (r.get("units") or [])} if _ok(r) else {}


def _by_vis(state, vis):
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _payloads(rpc, rid):
    """Les QUATRE payloads RPC dont `load_state` a besoin, memorises TELS QUELS.

    Les garder permet de RE-FABRIQUER l'etat pre-move autant de fois qu'on veut (`_state_from`) --
    c'est ce qui rend les MUTANTS jouables : chacun rejoue le port sur un etat NEUF, contre la
    mesure NATIVE deja prise. Sans cela il faudrait un runner live par mutant."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    rngs = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        return None
    return (dv, ob, snap, rngs)


def _state_from(pl, board):
    """`load_state` + CALAGE DU PRNG sur l'etat MT live.

    Calage INDISPENSABLE ici : le `SortByFormula` du `GetTarget` natif evalue deux
    `RandomAmount$$Calculate` PAR CANDIDAT (slot 1, pas slot 4), donc le tri lui-meme consomme le
    MT ; et `execute_ability_attack` refuse d'infliger le degat sur un rng non cale."""
    dv, ob, snap, rngs = pl
    state = load_state(dv, ob, snap, board=board)
    if isinstance(rngs, dict) and rngs.get("mt"):
        from engine.runner.prng import IntBasedMersenneTwister
        rng = IntBasedMersenneTwister()
        rng.mt = list(rngs["mt"])
        rng.mti = rngs["mti"]
        state.rng = rng
    return state


def _capture(rpc, rid, board):
    pl = _payloads(rpc, rid)
    return None if pl is None else _state_from(pl, board)


def _hp(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return int(hc.hp) if hc is not None else None


def _has_fury(state, uid):
    """L'unite porte-t-elle l'effet 1320 `FuryOfTheAncients` ? Lu sur `EffectsState.by_unit`, la
    MEME liste que celle sur laquelle `attack_query.has_heal_blockers` conclut."""
    st = getattr(state, "effects", None)
    if st is None or uid is None:
        return False
    return any(getattr(e, "effect_type", None) == FURY_EFFECT and not e.consumed
               for e in st.by_unit.get(int(uid), []))


def _adj(board, a, b):
    from engine.runner.operations.triggers.base import _hex_dist
    return _hex_dist(board, a, b, 1) == 1


def _destination_candidates(board, occupied, enemy_tiles, exclude, prefer_chain=True):
    """Tuiles LIBRES marchables adjacentes a >= 1 ennemi, TRIEES pour maximiser le regime de CHAINE.

    Score = (le meilleur nombre de voisins ENNEMIS qu'a un ennemi adjacent a cette tuile) --
    c.-a-d. << depuis ici, la 1re cible aura-t-elle une 2e cible ? >>. `prefer_chain` a `False`
    rabat sur << adjacent a au moins un ennemi >> (regime DEGENERE de la chaine).

    On rend une LISTE : `walkable` + adjacence ne garantissent PAS que le natif ACCEPTE le move
    (pathfinding, elevation, reservation) -- l'appelant essaie dans l'ordre."""
    et = set(enemy_tiles)
    scored = []
    for t in board.by_id:
        if t in occupied or t in exclude or not board.walkable(t):
            continue
        adj_enemies = [e for e in et if _adj(board, t, e)]
        if not adj_enemies:
            continue
        # pour chaque ennemi adjacent : combien d'AUTRES ennemis lui sont adjacents
        chain = max((sum(1 for o in et if o != e and _adj(board, e, o)) for e in adj_enemies),
                    default=0)
        scored.append(((chain if prefer_chain else 0), len(adj_enemies), t))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [(t, c, n) for c, n, t in scored]


def _build(seed, board_id, p_units, a_units, state_file, move=25):
    """`--unit-stat <vis>:Movement=<n>` CONDUIT la position : les spawns sont a ~8 hex et le move
    natif serait CLAMPE avant l'adjacence -- le probe mesurerait << pas de fire >> pour une raison
    de GEOMETRIE, pas de port. Ne touche NI le passif NI le degat."""
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board_id,
           "--state-file", state_file, "--p-units", p_units, "--a-units", a_units,
           "--unit-stat", "%s:Movement=%d" % (CASTER_VIS, move)]
    r = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)),
                       capture_output=True, text=True, timeout=600)
    if not os.path.exists(state_file):
        return None, "BUILD KO rc=%s\n%s\n%s" % (r.returncode, (r.stdout or "")[-1200:],
                                                 (r.stderr or "")[-1200:])
    with open(state_file, encoding="utf-8") as fh:
        return json.load(fh).get("runnerId"), None


def _replay_port(pre, board, cid, tids, before, reached_coord):
    """Rejoue le PORT SEUL sur un etat pre-move NEUF, et rend `(deltas_hp, porteurs_de_1320)`.

    Meme voie que la mesure de reference (`MovementHandler.visit_MoveUnitMessage`), meme tuile
    d'arrivee, meme PRNG cale. C'est le SUBSTRAT des mutants : on ne rejoue jamais le LIVE."""
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MovementHandler
    st = _state_from(pre, board)
    h = MovementHandler(st, EventBus())
    h.visit_MoveUnitMessage(MoveUnitMessage(unit_id=cid, to=reached_coord))
    dhp = {sq: before[sq] - (_hp(st, tids[sq]) or 0) for sq in before}
    eff = sorted(str(sq) for sq in before if _has_fury(st, tids[sq]))
    fire = [f for f in (h.after_move or [])
            if isinstance(f, dict) and f.get("passive") == "FuryOfTheAncients"]
    return dhp, eff, fire


def _run_mutants(pre, board, cid, tids, before, live_hp, live_eff, reached_coord) -> list:
    """CONTRE-EPREUVE. Chaque mutation vise UN littéral ou UN etage LU au decompile ; elle MORD si
    le port mute ne reproduit plus la mesure NATIVE (PV **exacts** + porteurs de l'effet).

    ⚠ Le critere est l'EGALITE EXACTE, pas une inegalite large : un mutant qui ne changerait que
    l'ordre de deux cibles a degat egal passerait un `<=`. Un mutant qui NE MORD PAS est RENDU tel
    quel, avec sa cause -- jamais retire pour faire vert."""
    import engine.entities.selectors.units as U
    import engine.runner.operations.triggers.loki.fury_of_the_ancients as F
    from dataclasses import replace as _dc_replace

    ref_eff = sorted(str(sq) for sq in before if live_eff.get(sq))
    out = []

    def _measure(name, note):
        try:
            dhp, eff, fire = _replay_port(pre, board, cid, tids, before, reached_coord)
        except Exception as exc:                                  # noqa: BLE001
            # ⚠ UNE EXCEPTION N'EST PAS UNE MORSURE. Compter le `raise` du HARNAIS comme un mutant
            # qui mord rend la contre-epreuve VERTE pour la mauvaise raison -- mesure du 2026-08-11 :
            # un `NameError` dans l'instrumentation a fait passer 7/7 mutants, dont deux qui etaient
            # INERTES au tour precedent. `mord = None` = verdict INDISPONIBLE, jamais un vert.
            out.append({"mutant": name, "mord": None, "via": "exception",
                        "detail": "%s: %s" % (type(exc).__name__, exc), "note": note})
            return
        same = (all(dhp[sq] == live_hp[sq] for sq in before) and eff == ref_eff)
        out.append({"mutant": name, "mord": not same, "note": note,
                    "hp": {str(k): v for k, v in dhp.items()}, "effet": eff, "fire": fire})

    # (1) `maxTargets` : le piege `DSLFormulas+0x20`. `Direct(0)` = AUCUN saut -> 1 seule cible.
    old = F.MAX_TARGETS
    try:
        F.MAX_TARGETS = 0
        _measure("maxTargets=0 (le <<Zero @formulas+0x20>> du commentaire errone)",
                 "doit ne frapper qu'UNE cible")
    finally:
        F.MAX_TARGETS = old

    # (2) sens du tri : le flag natif est 0 = DESCENDANT.
    _orig_target = F.fury_target
    try:
        def _asc(state, owner_id, hits, rng=None):
            first = F.fury_damage_prediction_formula(
                F.ActiveTarget(), F.min_max_damage(state, owner_id, rng), hits)
            second = F.fury_damage_prediction_formula(
                F.fury_second_target_selector(F.ActiveTarget()),
                F.min_max_damage(state, owner_id, rng), hits)
            return F.Cache(F.PickFirstN(
                F.SortByFormula(F.fury_possible_targets(), F.Sum(first, second), ascending=True),
                F.Const(1)))
        F.fury_target = _asc
        _measure("SortByFormula ascending=True (le natif ecrit 0 = DESC)",
                 "doit choisir l'autre extremite du classement")
    finally:
        F.fury_target = _orig_target

    # (3) `SortByFormula` : le slot lie. Sans `active_target`, la formule ne resout plus sa cible.
    _orig_select = U.SortByFormula.select
    try:
        def _subject_only(self, ctx):
            lst = list(self.source.evaluate(ctx))
            return sorted(lst, key=lambda u: self.formula.evaluate(_dc_replace(ctx, subject=u)),
                          reverse=not self.ascending)
        U.SortByFormula.select = _subject_only
        _measure("SortByFormula lie `subject` SEUL (l'ancien binding, deduit par analogie)",
                 "la formule ne resout plus sa cible -> cles toutes nulles -> ordre SOURCE")
    finally:
        U.SortByFormula.select = _orig_select

    # (4) l'ORDRE du tirage dans `DamagePredictionFormula` : le natif tire AVANT ses null-guards.
    import engine.entities.formulas as FM
    _orig_calc = FM.DamagePredictionFormula.calculate
    try:
        def _guard_first(self, ctx):
            from engine.dsl.base import resolve_unit as _ru
            att, dfn = _ru(self.attacker, ctx), _ru(self.defender, ctx)
            if att is None or dfn is None:
                return 0                      # <-- SORTIE SANS TIRER : le desalignement PRNG
            return _orig_calc(self, ctx)
        FM.DamagePredictionFormula.calculate = _guard_first
        _measure("DamagePredictionFormula : null-guard AVANT le tirage",
                 "desaligne le MT des que le 2e maillon d'un candidat n'existe pas")
    finally:
        FM.DamagePredictionFormula.calculate = _orig_calc

    # (5) `GetSecondTargetSelector` : le REFERENT du `Friends` est la CIBLE, pas le caster.
    _orig_second = F.fury_second_target_selector
    try:
        def _friends_of_caster(last_target):
            return F.Damageable(F.Friends(
                F.AdjacentUnits(last_target, F.Const(F.ADJACENT_UNIQUE),
                                selection_type=F.UNIT_SELECTION_TYPE),
                reference=F.Caster(), selection_type=F.UNIT_SELECTION_TYPE))
        F.fury_second_target_selector = _friends_of_caster
        _measure("GetSecondTargetSelector : Friends(reference = Caster) au lieu de la CIBLE",
                 "vise les allies du CASTER -> la chaine ne saute plus sur un ennemi")
    finally:
        F.fury_second_target_selector = _orig_second

    # (6) `nrOfHits` : le litteral de config (2), pas 1.
    _orig_cc = F._config_const
    try:
        F._config_const = lambda key: (1 if key == F.HITS_KEY else _orig_cc(key))
        _measure("nrOfHits = 1 (au lieu du ConfigConst(0x2f) = 2)",
                 "doit HALVER le degat de chaque maillon")
    finally:
        F._config_const = _orig_cc

    # (7) `chainOptions+0x12` : le coup DIFFERE d'un cran.
    _orig_deferred = F.CHAIN_DEFERRED_HIT
    try:
        F.CHAIN_DEFERRED_HIT = False
        _measure("chainOptions+0x12 = 0 (coup immediat au lieu de differe)",
                 "la 2e cible serait choisie sur un plateau ou la 1re a DEJA pris le coup")
    finally:
        F.CHAIN_DEFERRED_HIT = _orig_deferred

    return out


def run(board_id=BOARD, seed=SEED, p_units=P_UNITS, a_units=A_UNITS,
        state_file=None, prefer_chain=True, keep=False, mutants=False) -> dict:
    """Monte UN runner, CONDUIT Mephiston au contact, mesure les deux cotes, DISPOSE le runner.

    Rend un dict de mesure (jamais d'assertion ici -- un probe MESURE, un test GARDE)."""
    sf = state_file or os.path.join(tempfile.gettempdir(), "st_927_probe.json")
    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    out: dict = {"ok": False, "err": None, "board": board_id, "seed": seed}
    rid, err = _build(seed, board_id, p_units, a_units, sf)
    if rid is None:
        out["err"] = err
        return out
    out["runner"] = rid
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym") if bg and bg.get("tiles") else None
        if board is None:
            out["err"] = "boardGraph indispo"
            return out

        U = _live_units(rpc, rid)
        sq_c = next((sq for sq, u in U.items() if u.get("visualId") == CASTER_VIS), None)
        if sq_c is None:
            out["err"] = "caster %s absent live" % CASTER_VIS
            return out
        c_team = U[sq_c].get("teamId")
        enemies = [sq for sq, u in U.items() if u.get("teamId") != c_team and not u.get("isDead")]
        if not enemies:
            out["err"] = "aucun ennemi live"
            return out

        occupied = {board.id_at(u["col"], u["row"]) for u in U.values()}
        c_tile = board.id_at(U[sq_c]["col"], U[sq_c]["row"])
        enemy_tiles = {sq: board.id_at(U[sq]["col"], U[sq]["row"]) for sq in enemies}
        cands = _destination_candidates(board, occupied, set(enemy_tiles.values()),
                                        exclude={c_tile}, prefer_chain=prefer_chain)
        if not cands:
            out["err"] = "aucune tuile libre adjacente a un ennemi"
            return out
        out["candidates"] = len(cands)
        out["chain_potentiel"] = cands[0][1]

        # --- capture PRE-move : l'etat COMMUN aux deux cotes ---------------------------------
        pre = _payloads(rpc, rid)
        if pre is None:
            out["err"] = "capture pre-move KO"
            return out
        state = _state_from(pre, board)
        cid = _by_vis(state, CASTER_VIS)
        if cid is None:
            out["err"] = "caster absent offline"
            return out
        vis_by_sq = {sq: U[sq].get("visualId") for sq in enemies}
        tids = {sq: _by_vis(state, vis_by_sq[sq]) for sq in enemies}
        before = {sq: _hp(state, tids[sq]) for sq in enemies if tids[sq] is not None}
        out["before"] = {str(sq): before[sq] for sq in before}

        # --- LIVE : le move publie On(0x1c), le natif fire -----------------------------------
        dest = reached = None
        for cand, chain, n_adj in cands:
            ccol, crow = board.coord(cand)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": sq_c, "to": {"col": ccol, "row": crow}}}, 60)
            U2 = _live_units(rpc, rid)
            if sq_c not in U2:
                out["err"] = "le caster a disparu apres le move"
                return out
            got = board.id_at(U2[sq_c]["col"], U2[sq_c]["row"])
            if got != c_tile:                       # l'unite A bouge -> `On(0x1c)` a ete publie
                dest, reached = cand, got
                out["dest"] = board.coord(cand)
                out["reached"] = board.coord(got)
                out["adj_atteint"] = sum(1 for t in enemy_tiles.values() if _adj(board, got, t))
                break
        if reached is None:
            out["err"] = ("aucune des %d tuiles candidates n'a ete atteinte par le natif "
                          "(l'unite est restee sur son spawn) -- panne de GEOMETRIE, pas de port"
                          % len(cands))
            return out
        if (out.get("adj_atteint") or 0) < 1:
            out["err"] = ("le natif a clampe le move sur une tuile SANS ennemi adjacent (%s) -- "
                          "montage non discriminant" % (out.get("reached"),))
            return out
        after_live = _capture(rpc, rid, board)
        if after_live is None:
            out["err"] = "capture post-move KO"
            return out
        live_hp, live_eff = {}, {}
        for sq in before:
            t = _by_vis(after_live, vis_by_sq[sq])
            live_hp[sq] = before[sq] - (_hp(after_live, t) or 0)
            live_eff[sq] = _has_fury(after_live, t)
        out["delta_live"] = {str(sq): live_hp[sq] for sq in live_hp}
        out["fury_live"] = sorted(str(sq) for sq in live_eff if live_eff[sq])
        out["cible_live"] = sorted(str(sq) for sq in live_hp if live_hp[sq])
        out["chain_len_live"] = len(out["cible_live"])

        # --- PORT : rejouer le MEME move sur l'etat PRE-move ---------------------------------
        # Voie = `MovementHandler.visit_MoveUnitMessage` (le chemin JOUEUR porte), vers la tuile
        # REELLEMENT ATTEINTE par le natif -- jamais la destination DEMANDEE.
        from engine.runner.events import EventBus
        from engine.runner.operations.movement import MovementHandler
        handler = MovementHandler(state, EventBus())
        handler.visit_MoveUnitMessage(MoveUnitMessage(unit_id=cid, to=board.coord(reached)))
        out["fire"] = [f for f in (handler.after_move or [])
                       if isinstance(f, dict) and f.get("passive") == "FuryOfTheAncients"]
        port_hp, port_eff = {}, {}
        for sq in before:
            port_hp[sq] = before[sq] - (_hp(state, tids[sq]) or 0)
            port_eff[sq] = _has_fury(state, tids[sq])
        out["delta_port"] = {str(sq): port_hp[sq] for sq in port_hp}
        out["fury_port"] = sorted(str(sq) for sq in port_eff if port_eff[sq])
        out["cible_port"] = sorted(str(sq) for sq in port_hp if port_hp[sq])

        # --- verdicts ------------------------------------------------------------------------
        out["temoin_natif_non_nul"] = any(live_hp.values())
        out["accord_hp"] = all(live_hp[sq] == port_hp[sq] for sq in before)
        out["accord_cible"] = out["cible_live"] == out["cible_port"]
        out["accord_effet"] = out["fury_live"] == out["fury_port"]
        out["ok"] = bool(out["temoin_natif_non_nul"] and out["accord_hp"]
                         and out["accord_cible"] and out["accord_effet"])

        # --- MUTANTS : chacun doit MORDRE (= faire diverger le port du natif MESURE) ---------
        if mutants:
            out["mutants"] = _run_mutants(pre, board, cid, tids, before, live_hp, live_eff,
                                          board.coord(reached))
        return out
    finally:
        if not keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 30)
            except Exception as exc:                       # noqa: BLE001
                out.setdefault("dispose_err", type(exc).__name__)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--p-units", dest="p_units", default=P_UNITS)
    ap.add_argument("--a-units", dest="a_units", default=A_UNITS)
    ap.add_argument("--state-file", dest="state_file", default=None)
    ap.add_argument("--no-prefer-chain", dest="prefer_chain", action="store_false",
                    help="ne PAS chercher le regime de CHAINE (2 cibles) -- regime DEGENERE")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--mutants", action="store_true",
                    help="rejouer le port MUTE contre la mesure native (contre-epreuve)")
    args = ap.parse_args()

    m = run(board_id=args.board, seed=args.seed, p_units=args.p_units, a_units=args.a_units,
            state_file=args.state_file, prefer_chain=args.prefer_chain, keep=args.keep,
            mutants=args.mutants)
    if m.get("err"):
        print("KO : %s" % m["err"])
        return 1
    print("runner=%s board=%s seed=%s ; dest=%s atteinte=%s ; adjacents=%s ; %s candidates "
          "(chain potentiel %s)"
          % (m.get("runner"), m["board"], m["seed"], m.get("dest"), m.get("reached"),
             m.get("adj_atteint"), m.get("candidates"), m.get("chain_potentiel")))
    for sq in sorted(m.get("before") or {}):
        print("  squad %s : hp avant=%s | natif d=%s | port d=%s"
              % (sq, (m["before"] or {}).get(sq), (m["delta_live"] or {}).get(sq),
                 (m["delta_port"] or {}).get(sq)))
    print("  effet 1320 : natif sur %s | port sur %s" % (m.get("fury_live"), m.get("fury_port")))
    for f in (m.get("fire") or []):
        print("  REF fire: hits demandes=%s cibles=%s" % (f.get("hits"), f.get("targets")))
        for a in (f.get("attacks") or []):
            if isinstance(a, dict):
                print("      coups JOUES=%s rolls=%s total=%s pierce=%s armor=%s"
                      % (a.get("hits"), a.get("rolls"), a.get("total"), a.get("pierce"),
                         a.get("armor")))
    print("-" * 90)
    if not m.get("temoin_natif_non_nul"):
        print("INCONCLUANT : temoin natif NUL -- un accord a zero ne prouve rien.")
        return 1
    print("temoin natif NON NUL : OK  (chaine natif = %s cible(s))" % m.get("chain_len_live"))
    print("accord PV     : %s" % ("OK" if m["accord_hp"] else "DIVERGE"))
    print("accord CIBLES : %s  (live=%s port=%s)"
          % ("OK" if m["accord_cible"] else "DIVERGE", m["cible_live"], m["cible_port"]))
    print("accord EFFET  : %s  (live=%s port=%s)"
          % ("OK" if m["accord_effet"] else "DIVERGE", m["fury_live"], m["fury_port"]))
    if (m.get("chain_len_live") or 0) < 2:
        print("NOTE : chaine natif = %s -> regime DEGENERE, le 2e maillon n'est PAS discrimine."
              % m.get("chain_len_live"))
    muts = m.get("mutants")
    if muts:
        print("-" * 90)
        mord = sum(1 for x in muts if x["mord"] is True)
        casse = sum(1 for x in muts if x["mord"] is None)
        for x in muts:
            tag = "CASSE " if x["mord"] is None else ("MORD  " if x["mord"] else "INERTE")
            print("  [%s] %s" % (tag, x["mutant"]))
            print("        %s ; hp=%s effet=%s%s"
                  % (x.get("note"), x.get("hp"), x.get("effet"),
                     ("" if x.get("detail") is None else " ; %s" % x["detail"])))
            for f in (x.get("fire") or []):
                print("        fire: hits=%s cibles=%s attaques=%s"
                      % (f.get("hits"), f.get("targets"), f.get("attacks")))
        print("  -> %d/%d mutants MORDENT ; %d INERTE(S) ; %d CASSE(S) (verdict indisponible)"
              % (mord, len(muts), len(muts) - mord - casse, casse))
    return 0 if m["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
