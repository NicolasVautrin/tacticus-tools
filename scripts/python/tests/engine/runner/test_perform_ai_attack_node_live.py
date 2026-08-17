"""GARDE DE-FORK — `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute` : UN corps.

Le corps natif n'a qu'UNE implementation offline (`abilities/loki/summon.py::
perform_ai_ability_unit_behaviour`), atteinte par les DEUX constructeurs `DSLFactory` homonymes
(`perform_ai_attack_from_current_position` = `+0x70=0` / `+0x78=Direct(0)` ;
`perform_ai_attack` = `+0x70`/`+0x78` fournis par l'appelant). La feuille DSL `PerformAIAttack`, la
feuille `SpawnReplica` (ScarabSummon) et la free-attack de
`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetTriggerAttackBehaviour` y
delèguent. Ce fichier verrouille les DEUX proprietes qui rendaient les mirrors divergents, chacune par
un scenario ou le comportement CHANGE l'observable :

A. **Domaine de cible = CONTEXTE, pas une variante de code.** `IdunBattle.Core.Services.TargetingQuery$$GetRange`
   fait `if (HasEffect(unit, 0x529 ForcedInMelee)) range = Math.Min(1, range)`. Mephiston porte une arme
   RANGED de portee 2 (Psychic, gameconfig) : sans ce clamp, sa free-attack tirerait sur un ennemi a
   distance 2 (c'est exactement le piege de l'« union permissive » entre les deux anciens mirrors, dont
   l'un ne regardait QUE l'adjacence et l'autre TOUTE la portee d'arme). Le test place l'ennemi le plus
   proche a distance 2 EXACTEMENT et exige ZERO attaque -- puis prouve, l'effet retire, que la cible
   etait bel et bien a portee d'arme (donc que seul le clamp l'a empechee).

B. **Dispatch after-hit INCONDITIONNEL.** Le noeud fait executer une VRAIE ability d'attaque par l'IA ->
   `IdunBattle.Operations.FinishAttackOperation$$Execute` emet `On(0x26)`/`On(8)`/`On(9)`. Aucun champ du
   `PerformAIAbilityUnitBehaviour` ne le gate. L'ancien mirror de TheQuickening (et celui de la feuille)
   sautait ce vecteur : une attaque libre ne reveillait AUCUN trigger post-attaque. Sonde = Judh
   (`genesKelermorph`, passif `HypersensoryAbilities`) dont
   `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateTrigger`
   = `On(9=Attack) & OwnerIsTarget` : etre CIBLE d'une attaque suffit, quel que soit l'attaquant. Sa
   reaction pose l'effet-drapeau once/turn 1407 -> observable binaire et deterministe.
   Teste sur les DEUX faces : la free-attack TheQuickening (B) ET la feuille DSL `PerformAIAttack`
   (on-appearance Poxwalkers, C).

D+E. **La feuille `SpawnReplica` (ScarabSummon 1047) passe par le MEME corps.** Elle etait le fork
   RESIDUEL laisse par la de-forkification : elle recablait `_nearest_enemy` +
   `AttackDamageOperation.execute` a la main, donc SANS gate de portee (D) et SANS dispatch after-hit
   (E). Les deux proprietes sont gardees SEPAREMENT, pour qu'un echec dise LAQUELLE a saute :
     D = le double, spawne loin de tout ennemi, ne frappe PAS (arme de melee portee 1, ennemi >= 2) ;
     E = le double, spawne AU CONTACT de Judh, declenche sa reaction `On(9)`.
   Le noeud natif de cette feuille est `IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttack` (et non
   `...FromCurrentPosition`) : `+0x70 allowMoveAction = 1`, `+0x78 moveAmount = null` (i2 « which then
   immediately takes a turn »). Depuis #348 le port APPROCHE bel et bien le double
   (`GenerateActionTiles(null)` + `MovementActionGenerator` + apply du `MoveUnitMessage`), d'ou deux
   ajustements ici : D parque les ennemis HORS DE PORTEE MEME APRES DEPLACEMENT (Movement 4 + arme de
   melee 1 = 5 hex de portee effective) et E lit la tuile d'ATTERRISSAGE (emission `SpawnUnit`) et
   non la position finale. La confrontation LIVE de l'approche vit dans `test_ai_approach_live.py`.

METHODE : etat REEL (`load_state` : board + stats live), positions PILOTEES, MT calee (`dumpRng`).
"""
from __future__ import annotations

from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.components import PositionComponent, HealthComponent
from engine.runner.prng import IntBasedMersenneTwister

MEPH = "bloodMephiston"          # 1151 TheQuickening -- BloodAngels, arme ranged portee 2 (Psychic)
ALLY = "bloodIntercessor"
JUDH = "genesKelermorph"         # passif HypersensoryAbilities -> reaction On(9) & OwnerIsTarget
FILLER = "necroWarden"
BLIGHT = "deathBlightbringer"    # 1040 Poxwalkers -- on-appearance = la feuille DSL PerformAIAttack
SPYDER = "necroSpyder"           # 1007 ScarabHive -- fabrique le porteur de 1047 (necroSmnSwarm)
SWARM = "necroSmnSwarm"          # porteur de 1047 ScarabSummon ; arme MELEE portee 1 (5 hits Energy)
QUICKENING = 1151
HYPERSENSORY_FLAG = 1407         # `HypersensoryAbilities_HasBeenAttacked` (once/turn, pose par la reaction)
FORCED_IN_MELEE = 0x529          # 1321


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _board(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return None
    return Board(bg["tiles"], adjacency="native_sym")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _dists(board, src, maxd):
    """BFS sur `board.neighbours` (la MEME metrique que `_hex_dist`, le gate de portee) -> {tile: dist}."""
    seen = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        if seen[x] >= maxd:
            continue
        for n in board.neighbours(x):
            if n not in seen:
                seen[n] = seen[x] + 1
                q.append(n)
    return seen


def _place(state, uid, board, tile):
    pc = state.get_entity(uid).get_component(PositionComponent)
    pc.col, pc.row = board.coord(tile)


def _tile_of(state, board, uid):
    pc = state.get_entity(uid).get_component(PositionComponent)
    return board.id_at(pc.col, pc.row)


def _hp(state, uid):
    hc = state.get_entity(uid).get_component(HealthComponent)
    return hc.hp if hc is not None else None


def _far_tile(board, anchors, mind=6):
    """Une tuile walkable a >= `mind` de TOUS les `anchors` (parking des unites hors scenario)."""
    banned = {}
    for a in anchors:
        for t, d in _dists(board, a, mind - 1).items():
            banned[t] = min(banned.get(t, 99), d)
    for t in board.by_id:
        if board.walkable(t) and t not in banned:
            return t
    return None


def _pick(dv, vis, taken):
    u = next((x for x in (dv.get("units") or [])
              if x.get("visualId") == vis and x.get("alive") and x["id"] not in taken), None)
    if u is not None:
        taken.add(u["id"])
    return u


def _setup(rpc, build_runner, seed, p_units, a_units):
    """Runner + state offline charge + MT calee. Renvoie (state, board, dv) ou skip."""
    rid = build_runner(seed, extra=["--roster", "1", "--p-units", p_units, "--a-units", a_units,
                                    "--hp-target", "300000", "--hp-player", "300000"])["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s):
        pytest.skip("dumpRng indispo")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not _ok(dv):
        pytest.skip("decisionView KO")
    state = load_state(dv, ob, snap, board=board)
    state.rng = _seed_rng(s)
    return state, board, dv


# =================================================================================================== #
# A. Le clamp ForcedInMelee est PORTANT : la portee d'arme seule ferait tirer, le contexte l'interdit.
# =================================================================================================== #

def test_quickening_free_attack_range_clamped_by_forced_in_melee(live_session, rpc, build_runner):
    """`TargetingQuery.GetRange` : `HasEffect(unit, 0x529)` -> `range = Math.Min(1, range)`.

    Meph (arme ranged portee 2) se teleporte sur une tuile dont l'ennemi le plus proche est a distance
    2. Le natif POSE `ForcedInMelee` avant `PerformAIAttackFromCurrentPosition` -> aucune cible legale
    -> AUCUNE attaque. Un port qui aurait « fusionne » les deux anciens mirrors en gardant la portee
    d'arme (union permissive) tirerait ici. Controle final : l'effet retire, la cible EST a portee
    (`_in_attack_range` True) -> c'est bien le clamp, et rien d'autre, qui a bloque le tir."""
    from engine.runner.operations.triggers.base import _in_attack_range
    state, board, dv = _setup(rpc, build_runner, "31337", f"{MEPH},{ALLY}", f"{FILLER},{FILLER}")
    taken = set()
    meph, ally = _pick(dv, MEPH, taken), _pick(dv, ALLY, taken)
    e1, e2 = _pick(dv, FILLER, taken), _pick(dv, FILLER, taken)
    if not all((meph, ally, e1, e2)):
        pytest.skip("roster incomplet offline")
    mid, aid, eid, e2id = meph["id"], ally["id"], e1["id"], e2["id"]

    # geometrie : C -- T (adjacents) ; ennemi a distance EXACTEMENT 2 de T (et >= 2 de C).
    trio = None
    for c in board.by_id:
        if not board.walkable(c):
            continue
        for t in board.neighbours(c):
            if not board.walkable(t):
                continue
            dt, dc = _dists(board, t, 2), _dists(board, c, 2)
            cand = [x for x, d in dt.items() if d == 2 and board.walkable(x) and dc.get(x, 9) >= 2]
            if cand:
                trio = (c, t, cand[0])
                break
        if trio:
            break
    if trio is None:
        pytest.skip("aucune geometrie (C,T,ennemi a d=2) sur ce board")
    c_tile, t_tile, e_tile = trio
    park = _far_tile(board, [c_tile, t_tile, e_tile])
    if park is None:
        pytest.skip("pas de tuile de parking")
    _place(state, mid, board, c_tile)
    _place(state, eid, board, e_tile)
    _place(state, aid, board, park)          # ally hors scenario (T reste VIDE -> aucun swap)
    _place(state, e2id, board, park)         # 2e ennemi parque loin
    print(f"\n[CLAMP] meph@{c_tile} -> T@{t_tile} ; ennemi@{e_tile} (d(T,e)=2) ; park@{park}")

    hp0, hp0b = _hp(state, eid), _hp(state, e2id)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=mid, target_id=t_tile, ability_type=QUICKENING))
    last = runner.ability_handler.last or {}
    assert last.get("ported"), "TheQuickening non routee"
    assert _tile_of(state, board, mid) == t_tile, "le caster n'a pas teleporte sur la tuile ciblee"

    assert last.get("attacks") == [], (
        f"free-attack EXECUTEE alors qu'aucun ennemi n'est ADJACENT : le clamp ForcedInMelee "
        f"(GetRange -> Math.Min(1, range)) n'est pas applique (attacks={last.get('attacks')})")
    assert _hp(state, eid) == hp0 and _hp(state, e2id) == hp0b, "un ennemi a subi du degat"
    # net-zero (mesure live probe_217 : « aucun effet persistant ») -- sur les DEUX canaux : la liste
    # structuree `State.effects` ET la liste de NOMS `EffectsOwnedComponent` (lue par la couche decision).
    from engine.runner.components import EffectsOwnedComponent
    assert not state.effects.has_effect(mid, effect_type=FORCED_IN_MELEE), \
        "ForcedInMelee non retire apres le cast (net-zero rompu)"
    _eo = state.get_entity(mid).get_component(EffectsOwnedComponent)
    assert "ForcedInMelee" not in list(getattr(_eo, "effects", []) or []), (
        "le NOM ForcedInMelee reste colle sur le caster apres le cast -> fuite du canal "
        "EffectsOwnedComponent (RemoveEffect doit de-enregistrer le nom)")
    # DISCRIMINANT : sans l'effet, la cible EST a portee -> seul le clamp a bloque le tir.
    assert _in_attack_range(state, mid, eid), (
        "l'ennemi n'etait PAS a portee d'arme -> le scenario ne discrimine rien "
        "(il faut une cible dans la portee ranged de Meph mais NON adjacente)")


# =================================================================================================== #
# B. La free-attack de TheQuickening dispatche le vecteur after-hit (On(9) -> reaction du defenseur).
# =================================================================================================== #

def test_quickening_free_attack_dispatches_after_hit(live_session, rpc, build_runner):
    """Le noeud fait executer une attaque NORMALE complete -> `On(9=Attack)` est emis. Judh
    (`HypersensoryAbilities`) ecoute `On(9) & OwnerIsTarget` et pose l'effet-drapeau 1407 en reagissant.

    L'ancien mirror de TheQuickening appelait `AttackDamageOperation.execute` NU (aucun
    `after_hit_normal_attack`) : Judh restait de marbre. Ici on exige la reaction."""
    state, board, dv = _setup(rpc, build_runner, "31337", f"{MEPH},{ALLY}", f"{JUDH},{FILLER}")
    taken = set()
    meph, ally = _pick(dv, MEPH, taken), _pick(dv, ALLY, taken)
    judh, filler = _pick(dv, JUDH, taken), _pick(dv, FILLER, taken)
    if not all((meph, ally, judh, filler)):
        pytest.skip("roster incomplet offline")
    mid, aid, jid, fid = meph["id"], ally["id"], judh["id"], filler["id"]

    trio = None
    for c in board.by_id:
        if not board.walkable(c):
            continue
        for t in board.neighbours(c):
            if not board.walkable(t):
                continue
            js = [j for j in board.neighbours(t) if j != c and board.walkable(j)]
            if js:
                trio = (c, t, js[0])
                break
        if trio:
            break
    if trio is None:
        pytest.skip("aucune geometrie (C,T,J) sur ce board")
    c_tile, t_tile, j_tile = trio
    park = _far_tile(board, [c_tile, t_tile, j_tile])
    if park is None:
        pytest.skip("pas de tuile de parking")
    _place(state, mid, board, c_tile)
    _place(state, jid, board, j_tile)
    _place(state, aid, board, park)
    _place(state, fid, board, park)
    print(f"\n[AFTERHIT/quickening] meph@{c_tile} -> T@{t_tile} ; judh@{j_tile} ; park@{park}")

    assert not state.effects.has_effect(jid, effect_type=HYPERSENSORY_FLAG), "drapeau deja pose"
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=mid, target_id=t_tile, ability_type=QUICKENING))
    last = runner.ability_handler.last or {}
    assert last.get("ported"), "TheQuickening non routee"
    attacks = last.get("attacks") or []
    assert any(a.get("attacker") == mid and a.get("target") == jid for a in attacks), (
        f"la free-attack n'a pas cible Judh (attacks={attacks})")
    assert state.effects.has_effect(jid, effect_type=HYPERSENSORY_FLAG), (
        "Judh n'a PAS reagi : la free-attack n'emet pas le vecteur after-hit On(9) "
        "(l'ancien mirror appelait AttackDamageOperation.execute nu)")
    assert attacks[0].get("after_hit"), "le port ne remonte pas les triggers after-hit de la free-attack"


# =================================================================================================== #
# C. La feuille DSL `PerformAIAttack` (on-appearance) dispatche le MEME vecteur (corps partage).
# =================================================================================================== #

def test_perform_ai_attack_leaf_dispatches_after_hit(live_session, rpc, build_runner):
    """`SpawnUnitOptions+0x18 = PerformAIAttackFromCurrentPosition(activeTarget@0x180)` (Poxwalkers 1040)
    passe par le MEME corps que la free-attack -> l'attaque du summon a l'apparition emet elle aussi
    `On(9)`. Sonde identique (Judh). Avant le de-fork, la feuille dupliquait cible+gate+attaque SANS le
    vecteur after-hit : aucun trigger post-attaque ne partait des grots/Poxwalkers/Cadians."""
    from engine.runner.abilities.deathguard import spawn_poxwalkers_tree
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.dsl.effects import ExecutionContext
    state, board, dv = _setup(rpc, build_runner, "2468", BLIGHT, f"{JUDH},{FILLER}")
    taken = set()
    blight = _pick(dv, BLIGHT, taken)
    judh, filler = _pick(dv, JUDH, taken), _pick(dv, FILLER, taken)
    if not all((blight, judh, filler)):
        pytest.skip("roster incomplet offline")
    bid, jid, fid = blight["id"], judh["id"], filler["id"]

    pair = None
    for j in board.by_id:
        if not board.walkable(j):
            continue
        ps = [p for p in board.neighbours(j) if board.walkable(p)]
        if len(ps) >= 2:
            pair = (j, ps[0], ps[1])
            break
    if pair is None:
        pytest.skip("aucune geometrie (J, P, C) sur ce board")
    j_tile, p_tile, c_tile = pair
    park = _far_tile(board, [j_tile, p_tile, c_tile])
    if park is None:
        pytest.skip("pas de tuile de parking")
    _place(state, jid, board, j_tile)
    _place(state, bid, board, c_tile)
    _place(state, fid, board, park)
    print(f"\n[AFTERHIT/leaf] blight@{c_tile} ; spawn@{p_tile} ; judh@{j_tile} ; park@{park}")

    assert not state.effects.has_effect(jid, effect_type=HYPERSENSORY_FLAG), "drapeau deja pose"
    ectx = ExecutionContext(state=state, rng=state.rng)
    spawn_poxwalkers_tree([p_tile]).execute(entities_from_state(state, bid), ectx)
    spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
    attacks = next((p["attacks"] for n, p in ectx.emitted if n == "PerformAIAttack"), [])
    assert spawned, "aucun Poxwalker pose sur la tuile choisie"
    assert any(a.get("target") == jid for a in attacks), (
        f"l'on-appearance n'a pas attaque Judh (attacks={attacks})")
    assert state.effects.has_effect(jid, effect_type=HYPERSENSORY_FLAG), (
        "Judh n'a PAS reagi a l'attaque du summon : la feuille DSL n'emet pas le vecteur after-hit")


# =================================================================================================== #
# D + E. La feuille `SpawnReplica` (ScarabSummon 1047) -- le fork RESIDUEL -- passe par le MEME corps.
#        D = gate de portee ; E = dispatch after-hit. GARDES SEPAREES (un echec dit LAQUELLE saute).
# =================================================================================================== #

def _make_scarab(state, spyder_id):
    """Materialise UN vrai `necroSmnSwarm` (le porteur de 1047) via l'Operation de spawn VALIDEE
    LIVE-BIT-EXACT `SpawnUnitOperation.execute` (ScarabHive), sur une tuile libre adjacente au spyder
    -- AUCUNE unite fabriquee a la main : owner/stats/traits sont ceux d'un scarab de partie."""
    import gameconfig as GC
    from engine.runner.operations.spawn import SpawnUnitOperation
    vid = ((GC.ability("ScarabHive") or {}).get("constants") or {}).get("unitId")
    ids = SpawnUnitOperation.execute(state, spyder_id, spyder_id, "ScarabHive", vid, 1)
    if not ids:
        return None
    return ids[0] if state.get_entity(ids[0]).get_component(PositionComponent) is not None else None


def _replica_run(state, scarab_id):
    """Joue l'arbre natif de ScarabSummon depuis le scarab. Renvoie (replicas, on_appearance,
    spawn_pos) -- `spawn_pos` = {unit: (col,row)} capture A L'ATTERRISSAGE. Depuis #348 le double
    PEUT se deplacer avant d'attaquer (`+0x78 moveAmount = null`), donc sa position finale n'est
    plus sa tuile de spawn : lire la position APRES coup mesurerait l'approche, pas le placement."""
    from engine.runner.abilities.loki import scarab_summon_tree
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.dsl.effects import ExecutionContext
    ectx = ExecutionContext(state=state, rng=state.rng)
    scarab_summon_tree().execute(entities_from_state(state, scarab_id), ectx)
    return ([p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"],
            [p for n, p in ectx.emitted if n == "ReplicaOnAppearance"],
            {p["unit"]: p.get("pos") for n, p in ectx.emitted if n == "SpawnUnit"})


def test_spawn_replica_gates_on_attack_range(live_session, rpc, build_runner):
    """D -- GATE DE PORTEE. Le double d'un scarab (`necroSmnSwarm`, Movement 4, arme de MELEE
    portee 1) apparait a >= 7 hex du premier ennemi : sa portee EFFECTIVE etant 4 + 1 = 5 hex
    (`+0x78 moveAmount = null` lui ouvre son deplacement depuis #348),
    `IdunBattle.Core.Services.TargetingQuery$$GetRange` ne rend AUCUNE cible legale depuis AUCUNE
    tuile d'action -- donc AUCUNE attaque. Il s'APPROCHE (deplacement pur), et c'est le natif.

    ROUGE avant le fix : la feuille `SpawnReplica` recablait `_nearest_enemy` +
    `AttackDamageOperation.execute` SANS gate -- le double frappait l'ennemi le plus proche a n'importe
    quelle distance. DISCRIMINANT explicite : on prouve qu'une cible VIVANTE existe (donc que l'ancien
    corps aurait tire) et qu'elle reste HORS portee APRES l'approche (donc que c'est bien le gate qui
    l'a arretee, et non un manque de mouvement)."""
    from engine.runner.abilities.loki import _nearest_enemy
    from engine.runner.operations.triggers.base import _in_attack_range
    state, board, dv = _setup(rpc, build_runner, "31337", f"{SPYDER},{ALLY}", f"{FILLER},{FILLER}")
    taken = set()
    spyder, ally = _pick(dv, SPYDER, taken), _pick(dv, ALLY, taken)
    e1, e2 = _pick(dv, FILLER, taken), _pick(dv, FILLER, taken)
    if not all((spyder, ally, e1, e2)):
        pytest.skip("roster incomplet offline")
    sid, aid, eid, e2id = spyder["id"], ally["id"], e1["id"], e2["id"]

    # C = tuile du scarab, avec au moins une voisine libre ; ennemis parques a >= 7 de C. Le double
    # atterrit sur une voisine de C -> il reste a >= 6 de l'ennemi, au-dela de sa portee EFFECTIVE
    # (Movement 4 + arme de melee 1 = 5). Le plancher etait 4 avant #348, quand le port n'approchait
    # pas : a 3 hex, le double ATTEINDRAIT desormais sa cible et le test ne mesurerait plus le gate.
    c_tile = ez = None
    for cand in sorted(board.by_id):
        if not (board.walkable(cand) and sum(1 for n in board.neighbours(cand)
                                             if board.walkable(n)) >= 2):
            continue
        ez = next((z for z in (_far_tile(board, [cand], mind=m) for m in (10, 9, 8, 7))
                   if z is not None), None)
        if ez is not None:
            c_tile = cand
            break
    if c_tile is None or ez is None:
        pytest.skip("aucune geometrie (C isolable a >= 7 des ennemis) sur ce board")
    _place(state, eid, board, ez)
    _place(state, e2id, board, ez)
    # spyder + ally parques loin de C ET de la zone ennemie (le spyder doit garder une voisine libre)
    park = _far_tile(board, [c_tile, ez], mind=3)
    if park is None:
        pytest.skip("pas de tuile de parking")
    _place(state, sid, board, park)
    _place(state, aid, board, ez)
    scarab = _make_scarab(state, sid)
    if scarab is None:
        pytest.skip("scarab non materialise (pas de tuile libre adjacente au spyder)")
    _place(state, scarab, board, c_tile)
    print(f"\n[GATE/replica] scarab@{c_tile} ; ennemis@{ez} ; spyder@{park}")

    hp0, hp0b = _hp(state, eid), _hp(state, e2id)
    replicas, attacks, _spawn_pos = _replica_run(state, scarab)
    assert replicas, "aucun double spawne : le scenario ne teste rien"
    rid_ = replicas[0]
    tgt = _nearest_enemy(state, rid_)
    assert tgt is not None, ("aucun ennemi vivant visible du double -> scenario non discriminant "
                             "(l'ancien corps sans gate n'aurait rien frappe non plus)")
    assert not _in_attack_range(state, rid_, tgt), (
        "l'ennemi le plus proche EST a portee -> le scenario ne discrimine pas le gate")
    assert attacks == [], (
        f"le double a ATTAQUE une cible hors de portee : le gate `_in_attack_range` "
        f"(mirror TargetingQuery$$GetRange) n'est pas applique par la feuille SpawnReplica "
        f"(attacks={attacks})")
    assert _hp(state, eid) == hp0 and _hp(state, e2id) == hp0b, "un ennemi a subi du degat"


def test_spawn_replica_dispatches_after_hit(live_session, rpc, build_runner):
    """E -- DISPATCH AFTER-HIT. Le double apparait AU CONTACT de Judh (`genesKelermorph`,
    `HypersensoryAbilities` = `On(9=Attack) & OwnerIsTarget`) : l'attaque du double etant une attaque
    NORMALE complete cote natif (`IdunBattle.Operations.FinishAttackOperation$$Execute`), Judh reagit
    et pose son drapeau once/turn 1407.

    ROUGE avant le fix : la feuille appelait `AttackDamageOperation.execute` NU -- degat pose, mais
    AUCUN trigger post-attaque. La tuile d'atterrissage est RENDUE DETERMINISTE en bloquant toutes les
    voisines du scarab sauf une avec des allies (le tirage `PickRandomly(., 1)` reste consomme : pool
    de taille 1 => 1 tirage, cf. loi #130)."""
    state, board, dv = _setup(rpc, build_runner, "31337",
                              f"{SPYDER},{ALLY},{ALLY},{ALLY},{ALLY}", f"{JUDH},{FILLER}")
    taken = set()
    spyder = _pick(dv, SPYDER, taken)
    allies = [_pick(dv, ALLY, taken) for _ in range(4)]
    judh, filler = _pick(dv, JUDH, taken), _pick(dv, FILLER, taken)
    if not (spyder and judh and filler and all(allies)):
        pytest.skip("roster incomplet offline")
    sid, jid, fid = spyder["id"], judh["id"], filler["id"]
    blockers = [spyder["id"]] + [a["id"] for a in allies]     # tous team JOUEUR = team du scarab

    # (C, P, J) : P seule voisine LIBRE de C (les autres bloquees par des allies), J adjacent a P
    # et NON voisin de C -> le double atterrit sur P, au contact de Judh, qui reste hors de portee
    # du scarab lui-meme (d(C,J)=2).
    trio = None
    for c in sorted(board.by_id):
        if not board.walkable(c):
            continue
        nb = [n for n in board.neighbours(c) if board.walkable(n)]
        if not (2 <= len(nb) <= len(blockers) + 1):
            continue
        for p in nb:
            js = [j for j in board.neighbours(p)
                  if board.walkable(j) and j != c and j not in nb]
            if js:
                trio = (c, p, js[0], [n for n in nb if n != p])
                break
        if trio:
            break
    if trio is None:
        pytest.skip("aucune geometrie (C, P, J) bloquable avec les allies disponibles")
    c_tile, p_tile, j_tile, block_tiles = trio
    park = _far_tile(board, [c_tile, p_tile, j_tile], mind=4)
    if park is None:
        pytest.skip("pas de tuile de parking")

    _place(state, sid, board, park)                          # spyder au large -> voisine libre pour le spawn
    for a in allies:
        _place(state, a["id"], board, park)
    _place(state, jid, board, j_tile)
    _place(state, fid, board, park)                          # 2e ennemi loin -> Judh EST le plus proche
    scarab = _make_scarab(state, sid)
    if scarab is None:
        pytest.skip("scarab non materialise (pas de tuile libre adjacente au spyder)")
    _place(state, scarab, board, c_tile)
    for tile, uid in zip(block_tiles, blockers):             # bloque toutes les voisines sauf P
        _place(state, uid, board, tile)
    print(f"\n[AFTERHIT/replica] scarab@{c_tile} ; libre P@{p_tile} ; judh@{j_tile} ; "
          f"bloquees={block_tiles}")

    assert not state.effects.has_effect(jid, effect_type=HYPERSENSORY_FLAG), "drapeau deja pose"
    replicas, attacks, spawn_pos = _replica_run(state, scarab)
    assert len(replicas) == 1, f"attendu 1 double, obtenu {replicas}"
    # Tuile d'ATTERRISSAGE (capturee a l'emission `SpawnUnit`), et non position finale : depuis #348
    # le double peut se DEPLACER avant de frapper (`+0x78 moveAmount = null`), et il le fait ici --
    # il attaque Judh depuis une autre tuile adjacente. Lire la position finale mesurerait
    # l'approche, pas le determinisme du placement que ce setup veut etablir.
    assert spawn_pos.get(replicas[0]) == board.coord(p_tile), (
        "le double n'a pas atterri sur la seule tuile libre -> setup non deterministe")
    assert any(a.get("target") == jid for a in attacks), (
        f"le double n'a pas attaque Judh alors qu'il est ADJACENT (attacks={attacks})")
    assert state.effects.has_effect(jid, effect_type=HYPERSENSORY_FLAG), (
        "Judh n'a PAS reagi : la feuille SpawnReplica n'emet pas le vecteur after-hit On(9) "
        "(l'ancien mirror appelait AttackDamageOperation.execute nu)")
    assert attacks[0].get("after_hit") is not None, (
        "le port ne remonte pas les triggers after-hit de l'attaque du double")
