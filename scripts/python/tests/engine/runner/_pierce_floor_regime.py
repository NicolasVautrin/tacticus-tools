"""FIXTURE NOMMEE ET REUTILISABLE — le regime PERCAGE-DOMINANT, seul regime ou la
MATERIALISATION finale du degat est OBSERVABLE.

POURQUOI cette fixture existe (et pourquoi elle doit resservir) : le dernier etage de
`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` est le
MULTIPLICATEUR (slot 0x10 ->
`IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`), LU verbatim :

    v = Fix64.Mul(dmg, multiplier) ; v <= 0 -> 0 ; 0 < v < 1 -> 1 ;
    sinon `FixMath.NET.Fix64$$Round(v, AwayFromZero)`        <-- ARRONDI, pas troncature

Cet arrondi n'est OBSERVABLE que si la valeur reduite est FRACTIONNAIRE, ce qui exige TROIS
conditions simultanees, difficiles a reunir par hasard :

  (a) les DEUX %-list VIDES (attaquant ET defenseur) -- sinon
      `IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers` arrondit deja en fin
      d'appel et la valeur est entiere avant d'arriver ici ;
  (b) la branche PERCAGE du plancher natif
      `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`
      (`max(0, d - armure, d x pierce%)`) l'emporte, i.e. `armure > d x (1 - pierce/100)` --
      sinon `d - armure` est ENTIER ;
  (c) la partie fractionnaire de `d x fix(pierce/100)` est >= 0.5. `fix(p/100)` est LEGEREMENT
      INFERIEUR a la fraction exacte des que `p/100` n'est pas dyadique (`Div(20,100)` =
      0.1999999999534...) -> tout `d` dont le produit exact est ENTIER donne une fraction
      ~0.99999, le cas le plus discriminant.

LE LEVIER : `rl_duel build --armor-target N` force `Armor`+`FixedArmor` des a-units. C'est le
pendant MANQUANT de `--hp-target` (qui les met a 0 et supprime donc silencieusement l'etage
armure). Une valeur HAUTE arme (b) pour n'importe quel profil ; une valeur BASSE fabrique le
regime TEMOIN (branche armure -> degat entier -> les deux materialisations COINCIDENT), qui sert
a refuter « l'arrondi collait par chance ».

⚠ NE PAS utiliser `--hp-target`/`--hp-player` ici : ils remettent l'armure a 0 et detruisent
exactement le regime cherche.
"""
from __future__ import annotations

import json
from collections import deque

import pytest


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


@pytest.fixture(scope="session")
def pierce_dominant_regime(build_runner, rpc):
    """Fabrique de batailles dans le regime PERCAGE-DOMINANT (cf. en-tete du module).

    `regime(seed, p_units, a_units, armor=6000, board="MC1_67", extra=None)` ->
    `{"rid": int, "board": Board}`.

    Ce qui est neutralise D'OFFICE, pour qu'UNE SEULE variable bouge (la materialisation) :
      * `--crit 0,0`        : aucun crit-roll cote attaquant ;
      * `--block-target 0,0`: aucune source de block de BASE cote cible ;
      * `--armor-target N`  : armure CHOISIE (haute = regime discriminant, basse = temoin).
    """
    from engine.entities.pathfinding.board import Board

    def _regime(seed, p_units, a_units, armor=6000, board="MC1_67", extra=None):
        b = build_runner(seed, extra=["--roster", "1", "--p-units", p_units,
                                      "--a-units", a_units, "--crit", "0,0",
                                      "--block-target", "0,0",
                                      "--armor-target", str(armor),
                                      "--board", board, *(extra or [])])
        rid = b["rid"]
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        return {"rid": rid, "board": Board(bg["tiles"], adjacency="native_sym")}
    return _regime


def _bfs(board, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def drive(rpc, rid, board, caster_vis, target_vis, ability_id=None, max_turns=25):
    """DEPLACE l'attaquant jusqu'a pouvoir agir sur la cible (jamais « bloque par la geometrie
    de spawn ») : au CONTACT hex si `ability_id is None` (attaque normale melee), sinon jusqu'a
    ce que `abilityTargets` declare la cible LEGALE depuis la position courante.
    Rend `(caster_id, target_id, moved)` ou `(None, None, 0)`."""
    my, moves = None, 0
    for _ in range(max_turns):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        cst = next((u for u in units if u.get("visualId") == caster_vis and u.get("alive")), None)
        tg = next((u for u in units if u.get("visualId") == target_vis and u.get("alive")), None)
        if cst is None or tg is None:
            return None, None, 0
        if my is None:
            my = cst.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        tpos = (tg["pos"]["col"], tg["pos"]["row"])
        cpos = (cst["pos"]["col"], cst["pos"]["row"])
        ttile, ctile = board.id_at(*tpos), board.id_at(*cpos)
        if ability_id is None:
            if ctile in board.neighbours(ttile):
                return cst["id"], tg["id"], moves
        else:
            at = rpc("abilityTargets", {"runnerId": rid, "unitId": cst["id"],
                                        "abilityType": ability_id}, 90)
            ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                       if a.get("abilityId") == ability_id), {})
            if tg["id"] in [x.get("targetId") for x in (ab.get("fromHere") or [])]:
                return cst["id"], tg["id"], moves
        dist = _bfs(board, ttile)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cst["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        if ability_id is None:
            adj = sorted((t, cr) for t, cr in reach.items() if t in board.neighbours(ttile))
            if adj:
                _t, (col, row) = adj[0]
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": cst["id"], "to": {"col": col, "row": row}}}, 60)
                return cst["id"], tg["id"], moves + 1
        pool = [t for t in reach if t in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        best = min(pool, key=lambda t: dist[t])
        col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cst["id"], "to": {"col": col, "row": row}}}, 60)
        moves += 1
        if ability_id is None and dist[best] > 1:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None, 0


def live_amounts(res, target_id):
    """Per-coup LIVE attribues a `target_id`, dans l'ordre des events + flags de salete."""
    out, dirty = [], False
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if td.get("Target_Id") == target_id and "Amount" in td:
                out.append(int(td.get("Amount")))
                dirty = dirty or bool(td.get("Attack_DidCrit")) or bool(td.get("Attack_DidBlock")) \
                    or bool(td.get("Attack_DidEvade"))
    return out, dirty


def replay_materializations(dv, ob, snap, board, rng0, caster_id, target_id, ability_id, moved,
                            module_path, recorder="normal_like", ah_impl_factory=None):
    """Rejoue DEUX FOIS le MEME coup offline, sur le MEME etat et le MEME flux RNG, en ne faisant
    varier QUE la materialisation finale (`round_materialize` FORCE dans les globals du module
    PORTEUR -- #169 : patcher le `__init__` du package `damage_ops` serait un NO-OP SILENCIEUX,
    les deux modeles rendraient les MEMES cellules).

    Rend `{"floor": [...], "round": [...], "shipped": [...], "arme": [...]}` -- les per-coup du
    VECTEUR VISE
    seulement (les coups d'arme du meme message ne sont pas melanges) :
      * `floor`/`round` = les deux LOIS possibles, FORCEES -> disent laquelle est celle du natif ;
      * `shipped`       = le port TEL QU'IL EST LIVRE (aucun forcage) -> rend la garde ROUGE si
                          l'etage regresse (c'est la difference avec la garde #131, qui ne
                          verrouillait que la loi).
    `recorder` = "normal_like" | "additional_hits". `ah_impl_factory(force_round)` (optionnel) =
    implementation de substitution du canal `additional_hits` (sert a ISOLER l'etage
    materialisation d'un etage AMONT non encore porte) ; elle recoit `None` pour le run `shipped`."""
    import importlib
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import set_moved_flag
    from engine.services.damage_modifiers import apply_all_modifiers as _aam
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations import additional_hits as _ah_mod
    from engine.runner.operations.damage_ops import normal as _dnormal
    from engine.runner.operations.damage_ops import ability as _dability

    mod = importlib.import_module(module_path)

    def _one(force_round):
        st = load_state(dv, ob, snap, board=board)
        if moved:
            set_moved_flag(st, caster_id)
        rng = IntBasedMersenneTwister()
        rng.mt = list(rng0["mt"])
        rng.mti = rng0["mti"]
        st.rng = rng
        per_hit: list = []
        arme: list = []
        o_aam = mod.apply_all_modifiers
        o_nl = AttackDamageOperation.execute_normal_like
        o_ah = _ah_mod.execute_additional_hits
        o_n, o_a = _dnormal.execute_additional_hits, _dability.execute_additional_hits
        impl = ah_impl_factory(force_round) if ah_impl_factory is not None else None  # None = livre

        def _rec_nl(*a, **kw):
            out = o_nl(*a, **kw)
            if out and recorder == "normal_like":
                per_hit.extend(out.get("per_hit") or [])
            return out

        def _rec_ah(*a, **kw):
            out = (impl or o_ah)(*a, **kw)
            if out and recorder == "additional_hits":
                per_hit.extend(out.get("per_hit") or [])
            return out

        if force_round is not None:                  # None = port LIVRE, aucun forcage
            mod.apply_all_modifiers = (
                lambda v, m, round_materialize=False: _aam(v, m, round_materialize=force_round))
        AttackDamageOperation.execute_normal_like = staticmethod(_rec_nl)
        _ah_mod.execute_additional_hits = _rec_ah
        _dnormal.execute_additional_hits = _rec_ah
        _dability.execute_additional_hits = _rec_ah
        try:
            runner = Runner(st).install_default_handlers(20)
            if ability_id is None:
                runner.apply(AttackUnitMessage(caster_id, target_id))
            else:
                runner.apply(ActiveAbilityMessage(caster_id=caster_id, target_id=target_id,
                                                  ability_type=ability_id))
            # coups d'ARME du MEME message (attaque normale) : servent a LOCALISER le groupe dans
            # le flux d'events live, qui porte aussi ce qui suit (on-appearance d'un summon...).
            last = getattr(getattr(runner, "damage_handler", None), "last", None)
            if isinstance(last, dict):
                arme.extend(last.get("per_hit") or [])
            return per_hit, arme
        finally:
            mod.apply_all_modifiers = o_aam
            AttackDamageOperation.execute_normal_like = o_nl
            _ah_mod.execute_additional_hits = o_ah
            _dnormal.execute_additional_hits = o_n
            _dability.execute_additional_hits = o_a

    f, r, s = _one(False), _one(True), _one(None)
    return {"floor": f[0], "round": r[0], "shipped": s[0], "arme": r[1]}
