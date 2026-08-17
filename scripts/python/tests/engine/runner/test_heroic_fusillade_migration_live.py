"""Gen-stealer G5 : HeroicFusillade (actif 1180, Judh genesKelermorph) PORT -> arbre DSL, valide LIVE.

`HeroicFusilladeAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1) =
    op_Addition(
      If( Not(IsSurrounding(caster, target, radius=1)), MoveUnit(caster, destTile) ),          # MOVE
      If( IsAlive(target),
          op_Addition( op_Addition(
              ChangeStat(caster, CRIT_DAMAGE=10, mode=2=Add, mag),                              # buff crit (pose)
              AttackWithAttackDamage(caster, splash, MinMaxDamage, Projectile, nrOfHits=6) ),   # 6x splash
              ChangeStat(caster, CRIT_DAMAGE=10, mode=3=Sub, mag) ) ) )                         # buff crit (retire)
FINDINGS DECOMPILE (au-dela du verdict RE) :
  - SPLASH `Unobscured(Enemies(SurroundingUnits(target, radius, includeCenter=1)))` : le `includeCenter=1`
    (IdunBattleLogic.Entities.DSLSelectors$$SurroundingUnits -> IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles disk INCLUANT la tuile cible) -> la CIBLE est
    dans l'ensemble (i2 « 6x ... to the target AND all other enemies surrounding it »). Le MOVE-ring passe
    `includeCenter=0` (exclut la cible). Porte = `Union(Target(), Alive(SurroundingEnemies(TargetTile(), 1)))`.
  - "surrounding radius" = DslContext @+0xc0 = 1 (adjacence, i2 « surrounding hex »), DISTINCT du `range`
    config = 2 (`GetNumberConstant(0x16)`, portee de MOUVEMENT `MovableTilesInRange`).
  - ⚠ MoveUnit options NULL n'eteint PAS l'after-move (#933-r2, REFUTANT la phrase qui vivait ici) : la
    coupure native est `publish On(0x24) ; if (isInterimStep) return ; publish On(4) ; publish On(0x1d)`, et
    `isInterimStep` = `MoveUnitOptions+0x14` = `MoveUnitBehaviour+0x80`, DEFAUT 0 -> l'OVERWATCH part. Seul
    `+0x10` est inverse (`^0x101`) -> ni flag `ArrivedAtFinalTile` ni `On(0x1c)`. Sur ce montage, le tir
    d'overwatch declenche le passif `HypersensoryAbilities_MoveAndSpawnDecoy` de Judh, qui le RELOCALISE.
  - crit `mag = extraCritDmg[level] x nbFree`, nbFree compte POST-move (Cache 1re eval = ChangeStat(Add)).

VALIDATION : deterministe-sur-etat-live (comme G2/G4). On BUILD un runner (Judh + 2 ennemis), on capture
l'etat LIVE (units/teams/board/stats), on DRIVE les positions (cluster controle) sur l'etat charge, on execute
le PORT et on asserte le WIRING : (1) move sur un hex libre adjacent a la cible -- la DESTINATION CHOISIE par
l'ability, la position FINALE pouvant differer par la cascade after-move, qui doit alors l'EXPLIQUER ; (2) splash = cible +
ennemi voisin (les deux subissent des degats) ; (3) `crit_bonus == extraCritDmg x nbFree` ; (4) CRIT_DAMAGE
du caster RESTAURE (revert net-nul) ; (5) gate : deja-adjacent -> pas de move ; (6) OBSERVABILITE du buff crit
au roll (CC force 100 : l'ability inflige PLUS que la meme attaque SANS le buff, meme seed). ASCII-only.
Skip si pas de session / Judh non buildable / geometrie board infaisable.
"""
from __future__ import annotations

import pytest

import hexgeo

BUILD = ["--p-units", "genesKelermorph", "--a-units", "necroWarden,necroDestroyer"]
JUDH_VIS = "genesKelermorph"
MOVE_RANGE = 2
SURROUND_RADIUS = 1


# ------------------------------------------------------------------ helpers etat

def _find_by_vis(state, vis):
    from engine.runner.components import UnitComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == vis:
            return uid
    return None


def _team(state, uid):
    from engine.runner.components import OwnerComponent
    e = state.get_entity(uid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _enemies_of(state, uid):
    from engine.runner.components import UnitComponent, OwnerComponent
    mine = _team(state, uid)
    out = []
    for oid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None or not uc.alive or oc.team == mine:
            continue
        out.append(oid)
    return out


def _pos(state, uid):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _set_pos(state, uid, col, row):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is not None:
        pc.col, pc.row = int(col), int(row)


def _hp(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _ctx(state, uid):
    from engine.runner.components import StatsComponent
    e = state.get_entity(uid)
    sc = e.get_component(StatsComponent) if e is not None else None
    return sc.ctx if sc is not None else None


def _stat(state, uid, st):
    ctx = _ctx(state, uid)
    return int(ctx.stat(int(st))) if ctx is not None else None


def _force_stat(state, uid, st, val):
    """Force la stat a `val` via un modifier de source dediee (apply_change_stat = ModifyStatMessage)."""
    from engine.runner.operations.stat_ops import apply_change_stat
    cur = _stat(state, uid, st) or 0
    apply_change_stat(state, uid, int(st), ("test_force", int(st)), int(val) - int(cur))


def _level_mult(state, uid):
    ctx = _ctx(state, uid)
    level = getattr(ctx, "active_ability_level", None) if ctx is not None else None
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    return level, mult


def _walk_nbrs(board, tid):
    return [n for n in board.neighbours(tid) if board.walkable(n)]


def _park_others(state, board, keep_ids, center_coord):
    """Deplace toute unite VIVANTE hors `keep_ids` sur une tuile marchable LOIN (dist hex > 4) du centre,
    pour qu'aucune n'entoure la cible ni ne pollue le splash/nbFree. Tuiles distinctes."""
    from engine.runner.components import UnitComponent
    used = set()
    far = [t for t in board.by_id
           if board.walkable(t) and hexgeo.distance(board.coord(t), center_coord) > 4]
    far.sort()
    it = iter(far)
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uid in keep_ids or uc is None or not uc.alive:
            continue
        for t in it:
            if t not in used:
                used.add(t)
                _set_pos(state, uid, *board.coord(t))
                break


def _find_cluster(board):
    """Trouve (T, judh_start, e2) : T = tuile-cible avec >=3 voisins marchables ; judh_start a dist HEX 2 de
    T et ADJACENT a un voisin LIBRE de T (Judh peut s'y poser en 1 pas) ; e2 = un AUTRE voisin marchable de T
    (ennemi splash). Renvoie (T_coord, judh_coord, e2_coord, n_walk_nbrs) ou None."""
    for T in sorted(board.by_id):
        if not board.walkable(T):
            continue
        nbrs = _walk_nbrs(board, T)
        if len(nbrs) < 3:
            continue
        for landing in nbrs:                                  # voisin libre ou Judh se posera
            for js in _walk_nbrs(board, landing):             # depart Judh, adjacent au landing
                if js == T or js in nbrs:                      # pas la cible, pas deja adjacent a T
                    continue
                if hexgeo.distance(board.coord(js), board.coord(T)) != 2:
                    continue
                others = [n for n in nbrs if n != landing and n != js]
                if not others:
                    continue
                return board.coord(T), board.coord(js), board.coord(others[0]), len(nbrs)
    return None


def _find_adjacent_pair(board):
    """Trouve (T, judh_adj) : T marchable avec >=2 voisins marchables ; judh_adj = un voisin marchable de T
    (Judh DEJA adjacent -> gate no-move). Renvoie (T_coord, judh_coord, n_walk_nbrs) ou None."""
    for T in sorted(board.by_id):
        if not board.walkable(T):
            continue
        nbrs = _walk_nbrs(board, T)
        if len(nbrs) < 2:
            continue
        return board.coord(T), board.coord(nbrs[0]), len(nbrs)
    return None


# ------------------------------------------------------------------ fixture

@pytest.fixture(scope="session")
def g5_state(rpc, build_runner):
    """Etat LIVE reel (Judh genesKelermorph + necrons) charge offline, rejouable a volonte."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister

    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)

    def build_state():
        st = load_state(dv, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            r = IntBasedMersenneTwister()
            r.mt = list(rng0["mt"]); r.mti = rng0["mti"]
            st.rng = r
        return st

    if _find_by_vis(build_state(), JUDH_VIS) is None:
        pytest.skip("Judh (genesKelermorph) absent du build (non spawnable rank 17 ?)")
    return {"build_state": build_state, "board": board}


# ------------------------------------------------------------------ cascade after-move (#933-r2)

def _after_move_relocations(payload):
    """Toutes les RELOCALISATIONS trouvees dans un payload `after_move`, sous la forme
    `[(nom_de_l_ability, (col, row)), ...]`.

    Le vecteur after-move est une CASCADE : `MoveUnitOperation` publie `On(4 = UnitAfterMove)`,
    l'overwatch adverse tire, et le `finish_attack` de CE tir peut a son tour deplacer la cible
    (`HypersensoryAbilities_MoveAndSpawnDecoy` sur Judh). La profondeur n'est donc pas connue
    d'avance -- on descend recursivement plutot que d'ecrire un chemin, qu'un maillon de plus
    invaliderait en silence."""
    out = []

    def _walk(x):
        if isinstance(x, dict):
            mt = x.get("moved_to")
            if isinstance(mt, (tuple, list)) and len(mt) == 2:
                out.append((x.get("ability") or x.get("effect"), (int(mt[0]), int(mt[1]))))
            for v in x.values():
                _walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                _walk(v)

    _walk(payload)
    return out


def _replay_move_only(g5_state, clus):
    """Rejoue le MEME montage sur un etat TEMOIN et n'execute QUE le membre GAUCHE du `op_Addition`
    racine de `heroic_fusillade_tree` -- c'est-a-dire le volet MOVE, cascade after-move comprise.

    Rend `(nb_tuiles_libres_autour_de_T, destination_choisie, position_finale_de_Judh)`.

    POURQUOI un temoin plutot qu'une formule : `_hf_crit_mag` compte les tuiles libres a l'instant
    du `ChangeStat(Add)`, qui suit le MOVE **et** sa cascade (relocalisation du caster + pose d'un
    leurre). Une expression comme `n_nbrs - 2` code en dur une occupation que la cascade dement, et
    c'est exactement ce genre de constante gravee qui fait accuser le port a la place du montage.
    L'etat temoin est reconstruit par `build_state()` (meme RNG initial) : la passe est
    deterministe, et la position finale des deux passes est comparee dans le test."""
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.abilities.genestealer import heroic_fusillade_tree, _surrounding_free_tiles
    from engine.dsl.effects import ExecutionContext

    st = g5_state["build_state"]()
    board = g5_state["board"]
    judh = _find_by_vis(st, JUDH_VIS)
    enemies = _enemies_of(st, judh)
    t_coord, judh_coord, e2_coord, _n = clus
    target, e2 = enemies[0], enemies[1]
    _park_others(st, board, {judh, target, e2}, t_coord)
    _set_pos(st, target, *t_coord)
    _set_pos(st, e2, *e2_coord)
    _set_pos(st, judh, *judh_coord)
    tree = heroic_fusillade_tree(st, judh, target, SURROUND_RADIUS, MOVE_RANGE)
    ectx = ExecutionContext(state=st, rng=st.rng)
    tree.left.execute(entities_from_state(st, judh, target), ectx)     # UNIQUEMENT le volet MOVE
    mv = next((p for n, p in ectx.emitted if n == "MoveUnit"), None)
    return (len(_surrounding_free_tiles(st, t_coord, SURROUND_RADIUS)),
            (mv or {}).get("to"), _pos(st, judh))


# ------------------------------------------------------------------ tests

def test_g5_move_splash_crit_wiring(g5_state):
    """Cast complet dans un cluster controle : (1) Judh MOVE sur un hex libre adjacent a la cible ; (2) le
    splash frappe la CIBLE + l'ennemi voisin (degats aux deux) ; (3) crit_bonus == extraCritDmg x nbFree
    (nbFree = voisins libres post-move) ; (4) CRIT_DAMAGE du caster RESTAURE (revert net-nul)."""
    from engine.runner.abilities.genestealer import HeroicFusilladeAbility, _surrounding_free_tiles
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.stats import StatType
    state = g5_state["build_state"]()
    board = g5_state["board"]
    judh = _find_by_vis(state, JUDH_VIS)
    enemies = _enemies_of(state, judh)
    if judh is None or len(enemies) < 2:
        pytest.skip("Judh + 2 ennemis requis")
    clus = _find_cluster(board)
    if clus is None:
        pytest.skip("aucun cluster geometrique (T + depart dist2 + voisin splash)")
    t_coord, judh_coord, e2_coord, n_nbrs = clus
    target, e2 = enemies[0], enemies[1]
    _park_others(state, board, {judh, target, e2}, t_coord)
    _set_pos(state, target, *t_coord)
    _set_pos(state, e2, *e2_coord)
    _set_pos(state, judh, *judh_coord)

    # crit_bonus attendu = extraCritDmg[level] x nbFree. `_hf_crit_mag` collapse
    # `Count(CanAddUnit(SurroundingTiles(target, 1)))` au `ChangeStat(Add)`, donc APRES le MOVE **et
    # apres sa cascade after-move**. On le MESURE sur un etat TEMOIN (meme montage, meme RNG, seul
    # le volet MOVE de l'arbre est execute) au lieu de le DEDUIRE d'une formule de geometrie :
    # `n_nbrs - 2` supposait que seuls e2 et Judh occupent des voisins de T, ce que la cascade
    # dement (cf. le bloc (1) ci-dessous).
    level, mult = _level_mult(state, judh)
    extra = int(ability_var("HeroicFusillade", "extraCritDmg", level, multiplier_pct=mult) or 0)
    expected_nbfree, temoin_dest, temoin_final = _replay_move_only(g5_state, clus)
    assert 0 < expected_nbfree <= n_nbrs, \
        f"temoin ABSURDE : nbFree={expected_nbfree} hors ]0, {n_nbrs}] -- le montage temoin n'a pas joue"

    cd0 = _stat(state, judh, StatType.CRIT_DAMAGE)
    hp_t0, hp_e0 = _hp(state, target), _hp(state, e2)
    res = HeroicFusilladeAbility().execute_behaviour(state, judh, target)
    assert res is not None and res.get("dsl") is True, f"port non execute: {res}"

    # (1) MOVE : l'ability POSE Judh sur un hex libre ADJACENT a la cible.
    #
    # ⚠ ON ASSERTE LA DESTINATION CHOISIE (`res["move"]["to"]`), PAS LA POSITION FINALE, et c'est ce
    # que le rouge #933-r2 confondait (« Judh pas adjacent a la cible post-move: (1, 2) vs (0, 0) »,
    # `2 == 1`). Entre les deux, `MoveUnitOperation` joue son vecteur after-move : la feuille DSL a
    # options nulles ne SUPPRIME PAS `On(4 = UnitAfterMove)` (`MoveUnitOptions+0x14 = isInterimStep
    # = 0`, cf. `runner/operations/triggers/dispatch/move_death.after_move_triggers`) -- l'OVERWATCH
    # de l'ennemi part donc, et le passif de Judh `HypersensoryAbilities_MoveAndSpawnDecoy` le
    # RELOCALISE en laissant un leurre sur la tuile qu'il quitte. La cascade est FIDELE ; c'est
    # l'assertion qui mesurait au mauvais instant.
    assert res["move"] is not None and res["move"].get("moved") is True, f"Judh n'a pas bouge: {res['move']}"
    dest = res["move"].get("to")
    assert dest is not None and hexgeo.distance(dest, t_coord) == 1, \
        f"destination CHOISIE pas adjacente a la cible: {dest} vs {t_coord}"
    # ... et la position FINALE ne peut differer de `dest` QUE par une relocalisation after-move
    # NOMMEE. Sans ce second volet, le test cesserait de voir un port qui deplacerait Judh ailleurs.
    final = _pos(state, judh)
    reloc = _after_move_relocations(res["move"].get("after_move"))
    assert final == dest or final in [p for _a, p in reloc], (
        f"Judh a fini en {final} alors que l'ability l'a pose en {dest}, et AUCUNE relocalisation "
        f"after-move ne l'explique (relocalisations vues : {reloc})")
    assert final == temoin_final, \
        f"le temoin et la passe reelle divergent sur la position finale: {temoin_final} vs {final}"
    # TEMOIN NON NUL de la cascade : sur CE montage l'overwatch adverse part et relocalise Judh. Si
    # ce jour-la il ne partait plus, l'assertion `final == dest` ci-dessus deviendrait triviale et
    # le test cesserait d'observer le vecteur after-move sans le dire.
    assert reloc, (
        "la cascade after-move n'a RELOCALISE personne : le montage n'exerce plus `On(4 = "
        f"UnitAfterMove)` (after_move = {res['move'].get('after_move')})")

    # (2) SPLASH = cible + voisin, les deux subissent des degats
    assert res["main_attack"] is not None, "pas d'attaque principale sur la cible"
    splash_ids = {s["target"] for s in (res["splash"] or [])}
    assert e2 in splash_ids, f"l'ennemi voisin {e2} absent du splash {sorted(splash_ids)}"
    assert _hp(state, target) < hp_t0, f"cible pas endommagee (hp {hp_t0} -> {_hp(state, target)})"
    assert _hp(state, e2) < hp_e0, f"voisin splash pas endommage (hp {hp_e0} -> {_hp(state, e2)})"

    # (3) CRIT-PER-FREE-HEX : crit_bonus == extraCritDmg x nbFree
    assert res["crit_bonus"] == extra * expected_nbfree, \
        f"crit_bonus {res['crit_bonus']} != extraCritDmg {extra} x nbFree {expected_nbfree}"

    # (4) REVERT NET-NUL : CRIT_DAMAGE du caster restaure a sa base
    assert _stat(state, judh, StatType.CRIT_DAMAGE) == cd0, \
        f"CRIT_DAMAGE non restaure post-cast ({cd0} -> {_stat(state, judh, StatType.CRIT_DAMAGE)})"


def test_g5_gate_already_adjacent_no_move(g5_state):
    """GATE `Not(IsSurrounding(caster, target, 1))` : quand Judh est DEJA adjacent a la cible, AUCUN move
    (i2 « or is already on a hex surrounding Judh »). L'attaque a toujours lieu."""
    from engine.runner.abilities.genestealer import HeroicFusilladeAbility
    state = g5_state["build_state"]()
    board = g5_state["board"]
    judh = _find_by_vis(state, JUDH_VIS)
    enemies = _enemies_of(state, judh)
    if judh is None or not enemies:
        pytest.skip("Judh + 1 ennemi requis")
    pair = _find_adjacent_pair(board)
    if pair is None:
        pytest.skip("aucune paire adjacente geometrique")
    t_coord, judh_coord, _n = pair
    target = enemies[0]
    _park_others(state, board, {judh, target}, t_coord)
    _set_pos(state, target, *t_coord)
    _set_pos(state, judh, *judh_coord)
    assert hexgeo.distance(judh_coord, t_coord) == 1, "setup: Judh doit etre adjacent"

    hp_t0 = _hp(state, target)
    res = HeroicFusilladeAbility().execute_behaviour(state, judh, target)
    assert res is not None
    # gate FALSE -> le node MoveUnit n'est jamais execute -> aucun 'MoveUnit' emis
    assert res["move"] is None, f"un move a fire alors que Judh etait deja adjacent: {res['move']}"
    assert _pos(state, judh) == judh_coord, "Judh a bouge malgre le gate deja-adjacent"
    # l'attaque a bien eu lieu (branche If(IsAlive) independante du move)
    assert res["main_attack"] is not None and _hp(state, target) < hp_t0, \
        "l'attaque devrait avoir lieu meme sans move"


def test_g5_crit_buff_observable_at_roll(g5_state):
    """OBSERVABILITE (validator priority #1) : le buff CRIT_DAMAGE pose par l'ability est LU au roll. Avec
    CC force a 100 (tous les coups critent) et meme seed, l'ability (crit_damage = base + mag) inflige a la
    cible STRICTEMENT PLUS que la MEME attaque splash SANS le buff (crit_damage = base). Isole le seul effet
    du buff (memes positions Judh-adjacent -> pas de move, memes tirages rng)."""
    from engine.runner.abilities.genestealer import HeroicFusilladeAbility, heroic_fusillade_tree
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.entities.selectors.accessors import Target, TargetTile
    from engine.entities.selectors.units import Alive, SurroundingEnemies, Union
    from engine.dsl.base import Const
    from engine.dsl.effects import ExecutionContext
    from engine.entities.stats import StatType
    board = g5_state["board"]
    pair = _find_adjacent_pair(board)
    if pair is None:
        pytest.skip("aucune paire adjacente geometrique")
    t_coord, judh_coord, n_nbrs = pair

    def _prep():
        st = g5_state["build_state"]()
        j = _find_by_vis(st, JUDH_VIS)
        en = _enemies_of(st, j)
        if j is None or not en:
            return None
        tgt = en[0]
        _park_others(st, board, {j, tgt}, t_coord)
        _set_pos(st, tgt, *t_coord)
        _set_pos(st, j, *judh_coord)
        _force_stat(st, j, StatType.CRIT_CHANCE, 100)         # tous les coups critent
        _force_stat(st, j, StatType.CRIT_DAMAGE, 100)         # base crit_damage connue > 0 (could_crit)
        return st, j, tgt

    # --- REAL : l'ability complete (buff crit + attaque) ; Judh adjacent -> pas de move
    prep_r = _prep()
    if prep_r is None:
        pytest.skip("Judh/ennemi absent")
    st_r, j_r, t_r = prep_r
    hp0 = _hp(st_r, t_r)
    res = HeroicFusilladeAbility().execute_behaviour(st_r, j_r, t_r)
    assert res["move"] is None, "Judh adjacent : pas de move attendu (isole le buff)"
    if not res.get("crit_bonus"):
        pytest.skip("nbFree=0 (cible boxee) -> mag nul, pas de buff a observer")
    dmg_real = hp0 - _hp(st_r, t_r)

    # --- CONTROL : la MEME attaque splash, SANS le buff crit (crit_damage = base seul), meme seed/positions
    st_c, j_c, t_c = _prep()
    hp0c = _hp(st_c, t_c)
    splash = Union(Target(), Alive(SurroundingEnemies(TargetTile(), Const(SURROUND_RADIUS))))
    attack = AttackWithAttackDamage(splash, "HeroicFusillade", "Projectile", is_melee=False, multi=True)
    ectx = ExecutionContext(state=st_c, rng=st_c.rng)
    attack.execute(entities_from_state(st_c, j_c, t_c), ectx)
    dmg_ctrl = hp0c - _hp(st_c, t_c)

    print(f"\n[HF crit-obs] mag={res['crit_bonus']} dmg_real={dmg_real} dmg_ctrl={dmg_ctrl}")
    assert dmg_real > dmg_ctrl, (
        f"buff CRIT_DAMAGE NON observable au roll : ability {dmg_real} <= attaque-sans-buff {dmg_ctrl} "
        f"(mag={res['crit_bonus']})")
