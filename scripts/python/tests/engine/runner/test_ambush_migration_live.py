"""Gen-stealer G3 : trait Ambush (1052, Isaak/Judh) PORT -> triggers + Operation resurrect, valide LIVE.

Trait Ambush = 2 abilities-triggers (namespace `Triggered.Loki`) + 1 Operation impLerative :
  - `Ambush_SummonAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.Ambush_SummonAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.Ambush_SummonAbility$$GetSummonBehaviour) : `On(UnitDefeated=54) & OwnerIsTarget & Not(HasFlag 0xe)`
    -> pose 1 genesSmnDecoy sur la tuile du mort (ForSteppable) + enregistre `turn_defeated`.
  - `EnvAmbushResurrectAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$CreateBehaviour) : `On(TurnStart=22) & ValidDecoys>0 & Eligible>0`
    -> ressuscite chaque porteur eligible (mort au tour PRECEDENT, delta==1, non-flag-0xe) sur un decoy allie
    aleatoire, PV pleins, tour immediat, ordre Character-first.
  - feuille `Resurrect` -> `IdunBattle.Operations.ResurrectUnitOperation$$Execute` : alive=True + flag 0xe (one-shot) +
    crushe le decoy + SetHealth(full) + RemoveTurnFlags + emet `On(UnitResurrected=46)` (-> G2 BuffFriends).

VALIDATION : deterministe-sur-etat-live (comme G2/G4/G5). BUILD un runner (Isaak genesPrimus + Judh
genesKelermorph + ennemi banal), capture l'etat LIVE, DRIVE les positions, SIMULE la mort (alive=False +
`unit_defeated_triggers`, exactement ce que le pipeline `_fire_death_if_killed` fait) puis l'avance de tour
(`turn_counts += 1` + `start_turn_triggers`), et asserte le WIRING :
  (A) mort -> decoy sur la tuile du mort + turn_defeated pose ;
  (B) resurrection au tour SUIVANT (delta==1) : alive, PV pleins, flag 0xe, sur la tuile du decoy, decoy crushe ;
  (C) GATE de delai : delta==0 (meme tour) et delta==2 NE ressuscitent PAS (condition `==1`, pas `>=`) ;
  (D) ONE-SHOT : re-tuer un ressuscite (flag 0xe) -> pas de 2e decoy ni 2e resurrection ;
  (E) CHAINAGE : `On(UnitResurrected)` atteint G2 -> Isaak (carrier DecoysAndMisdirection) pose l'effet 1379
      (+582) sur le ressuscite (prouve l'emission de l'event).
ASCII-only. Skip si pas de session / unites non buildables / geometrie board infaisable.
"""
from __future__ import annotations

import pytest

ISAAK_VIS = "genesPrimus"        # Hero + Ambush + DecoysAndMisdirection (carrier BuffFriends)
JUDH_VIS = "genesKelermorph"     # Hero + Ambush + BeastSlayer ; actif HeroicFusillade
BUILD = ["--p-units", "genesPrimus,genesKelermorph", "--a-units", "necroWarden"]
DECOY_VIS = "genesSmnDecoy"
DECOYS_EXTRA_DMG = 1379          # EffectType.DecoysAndMisdirection_ExtraDamage (chainage G2)


# ------------------------------------------------------------------ helpers etat

def _find_by_vis(state, vis, alive_only=True):
    from engine.runner.components import UnitComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == vis and (uc.alive or not alive_only):
            return uid
    return None


def _all_by_vis(state, vis, alive_only=True):
    from engine.runner.components import UnitComponent
    out = []
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == vis and (uc.alive or not alive_only):
            out.append(uid)
    return out


def _player(state, uid):
    from engine.runner.components import OwnerComponent
    e = state.get_entity(uid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.player if oc is not None else None


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


def _hp_max(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp_max if hc is not None else None


def _alive(state, uid):
    from engine.runner.components import UnitComponent
    e = state.get_entity(uid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return bool(uc.alive) if uc is not None else None


def _has_flag(state, uid, flag):
    from engine.runner.components import UnitFlagsComponent
    e = state.get_entity(uid)
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    return bool(fl is not None and fl.has(flag))


def _turn_defeated(state, uid):
    from engine.runner.components import UnitComponent
    e = state.get_entity(uid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc.turn_defeated if uc is not None else None


def _walk_nbrs(board, tid):
    return [n for n in board.neighbours(tid) if board.walkable(n)]


def _park_others(state, board, keep_ids, center_coord):
    """Deplace toute unite VIVANTE hors `keep_ids` LOIN (dist hex > 5) du centre, sur des tuiles distinctes."""
    import hexgeo
    from engine.runner.components import UnitComponent
    used = set()
    far = [t for t in board.by_id
           if board.walkable(t) and hexgeo.distance(board.coord(t), center_coord) > 5]
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


def _kill(state, uid, killer_id):
    """Tue `uid` par l'APPLICATION reelle de la mort -- `AttackDamageOperation._kill_unit_operation`,
    mirror d'`IdunBattle.Operations.KillUnitOperation$$Execute`. `hp = 0` et `alive = False` sont
    poses en amont, comme `_fire_death_if_killed` le fait avant d'enfiler.

    ⚠ **CE MONTAGE APPELAIT `unit_defeated_triggers` DIRECTEMENT, ET C'ETAIT UN COURT-CIRCUIT
    (#10015-r3).** Sa docstring affirmait simuler `_fire_death_if_killed` << EXACTEMENT >> ; en
    realite elle sautait toute l'Operation de mort pour n'en publier qu'UN des cinq evenements.
    Le test passait quand meme parce que `Ambush_SummonAbility` ecrivait `turn_defeated` de sa
    propre main -- une COMPENSATION du port. En la retirant (le natif l'ecrit dans
    `IdunBattle.Operations.RemoveUnitOperation$$Execute`, atteint depuis
    `KillUnitOperation$$Execute+0xd34`), ces cinq tests sont passes au ROUGE : ils accusaient le
    MONTAGE, pas le portage. Passer par le vrai chemin est ce qui les rend a nouveau capables de
    juger -- et desormais ils couvrent AUSSI l'ordre natif retrait -> `On(UnitDefeated)`."""
    from engine.runner.components import UnitComponent, HealthComponent
    from engine.runner.operations.damage import AttackDamageOperation
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent)
    uc = e.get_component(UnitComponent)
    if hc is not None:
        hc.hp = 0
    uc.alive = False
    return AttackDamageOperation._kill_unit_operation(state, uid, killer_id, False) or []


def _start_turn(state, player, force_delta=None):
    """Avance au debut de tour de `player` : incremente `turn_counts[player]` (mirror de l'ecrivain
    natif `TurnComponent$$SetCurrentPlayer`, cote port `turnflow.set_current_player` -- surtout PAS
    `StartTurnOperation`, qui ne fait que LIRE ce dict, cf. #287-r11-r1-r1-r1-r1) puis tire
    `start_turn_triggers` (On 22) -> EnvAmbushResurrect. `force_delta` (optionnel) force
    `turn_counts[player]` a `turn_defeated + force_delta` pour tester le gate de delai."""
    from engine.runner.operations.triggers.dispatch.turn import start_turn_triggers
    state.turn_counts[player] = state.turn_counts.get(player, 0) + 1
    return start_turn_triggers(state, player)


# ------------------------------------------------------------------ fixture

@pytest.fixture(scope="session")
def g3_state(rpc, build_runner):
    """Etat LIVE reel (Isaak + Judh + necron) charge offline, rejouable a volonte."""
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

    probe = build_state()
    if _find_by_vis(probe, ISAAK_VIS) is None or _find_by_vis(probe, JUDH_VIS) is None:
        pytest.skip("Isaak (genesPrimus) et/ou Judh (genesKelermorph) absents du build")
    return {"build_state": build_state, "board": board}


def _setup_open(state, board, victim_vis):
    """Place le porteur `victim_vis` sur une tuile T avec >=1 voisin marchable (place pour le decoy), Isaak
    (carrier) sur un autre voisin (chainage G2), le reste parque loin. Renvoie (victim, isaak, T_id, T_coord)."""
    victim = _find_by_vis(state, victim_vis)
    isaak = _find_by_vis(state, ISAAK_VIS)
    if victim is None or isaak is None:
        return None
    for T in sorted(board.by_id):
        if not board.walkable(T):
            continue
        nbrs = _walk_nbrs(board, T)
        if len(nbrs) < 2:
            continue
        t_coord = board.coord(T)
        keep = {victim, isaak}
        _park_others(state, board, keep, t_coord)
        _set_pos(state, victim, *t_coord)
        if isaak != victim:
            _set_pos(state, isaak, *board.coord(nbrs[0]))
        return victim, isaak, T, t_coord
    return None


# ------------------------------------------------------------------ tests

def test_g3_death_spawns_decoy_and_records_turn(g3_state):
    """(A) A la mort d'un porteur Ambush : 1 decoy genesSmnDecoy apparait sur la tuile du mort, et
    `turn_defeated` = compteur de tours du joueur du porteur a la mort."""
    from engine.runner.components import UnitComponent
    state = g3_state["build_state"]()
    board = g3_state["board"]
    setup = _setup_open(state, board, JUDH_VIS)
    if setup is None:
        pytest.skip("setup geometrique infaisable")
    judh, isaak, T, t_coord = setup
    player = _player(state, judh)
    state.turn_counts[player] = 2                      # le porteur meurt alors que son joueur a demarre 2 tours

    decoys_before = set(_all_by_vis(state, DECOY_VIS))
    res = _kill(state, judh, killer_id=isaak)          # simulate death -> On(UnitDefeated)
    assert any(r.get("ability") == "Ambush_Summon" for r in res), f"Ambush_Summon n'a pas fire: {res}"

    # turn_defeated pose au compteur du joueur a la mort
    assert _turn_defeated(state, judh) == 2, f"turn_defeated attendu 2, obtenu {_turn_defeated(state, judh)}"
    # un NOUVEAU decoy, co-localise avec le mort (tuile du mort libre car alive=False)
    new = [d for d in _all_by_vis(state, DECOY_VIS) if d not in decoys_before]
    assert len(new) == 1, f"1 decoy attendu, obtenu {len(new)}"
    assert _pos(state, new[0]) == t_coord, f"decoy pas sur la tuile du mort {t_coord}: {_pos(state, new[0])}"


def test_g3_resurrect_next_turn_full_mutations(g3_state):
    """(B) Au tour SUIVANT du joueur (delta==1) : le porteur ressuscite sur la tuile du decoy, alive, PV
    PLEINS, flag 0xe pose, et le decoy est CRUSHE (alive=False)."""
    from engine.runner.components import UnitFlagsComponent
    state = g3_state["build_state"]()
    board = g3_state["board"]
    setup = _setup_open(state, board, JUDH_VIS)
    if setup is None:
        pytest.skip("setup geometrique infaisable")
    judh, isaak, T, t_coord = setup
    player = _player(state, judh)
    hpmax = _hp_max(state, judh)
    state.turn_counts[player] = 3

    decoys_before = set(_all_by_vis(state, DECOY_VIS))
    _kill(state, judh, killer_id=isaak)
    new_decoys = [d for d in _all_by_vis(state, DECOY_VIS) if d not in decoys_before]
    assert new_decoys, "pas de decoy pose a la mort"
    decoy = new_decoys[0]
    decoy_coord = _pos(state, decoy)
    assert _alive(state, judh) is False, "setup: le porteur doit etre mort"

    # tour suivant du joueur : turn_counts 3 -> 4, delta = 4 - turn_defeated(3) = 1 -> eligible
    res = _start_turn(state, player)
    assert any(r.get("ability") == "EnvAmbushResurrect" for r in res), f"resurrection n'a pas fire: {res}"

    assert _alive(state, judh) is True, "le porteur devrait etre ressuscite (alive)"
    assert _hp(state, judh) == hpmax, f"PV non pleins post-resurrection: {_hp(state, judh)} != {hpmax}"
    assert _has_flag(state, judh, UnitFlagsComponent.AMBUSH_CONSUMED), "flag 0xe (one-shot) non pose"
    assert _pos(state, judh) == decoy_coord, \
        f"le porteur devrait reapparaitre sur la tuile du decoy {decoy_coord}: {_pos(state, judh)}"
    assert _alive(state, decoy) is False, "le decoy devrait etre crushe a la reapparition"


def test_g3_delay_gate_only_next_turn(g3_state):
    """(C) GATE de delai `Difference==1` (PAS `>=`) : au tour MEME de la mort (delta 0) et DEUX tours apres
    (delta 2) le porteur NE ressuscite PAS ; seul delta==1 ressuscite."""
    state = g3_state["build_state"]()
    board = g3_state["board"]
    setup = _setup_open(state, board, JUDH_VIS)
    if setup is None:
        pytest.skip("setup geometrique infaisable")
    judh, isaak, T, t_coord = setup
    player = _player(state, judh)
    state.turn_counts[player] = 5
    _kill(state, judh, killer_id=isaak)               # turn_defeated = 5
    assert _turn_defeated(state, judh) == 5

    # delta 0 : meme tour (turn_counts reste 5 sans start_turn) -> pas de resurrection
    from engine.runner.operations.triggers.dispatch.turn import start_turn_triggers
    # on force un start_turn SANS incrementer (simule un dispatch a delta 0)
    r0 = start_turn_triggers(state, player)
    assert _alive(state, judh) is False, "delta 0 : ne doit PAS ressusciter"
    assert not any(rr.get("ability") == "EnvAmbushResurrect" for rr in r0), f"resurrection a delta 0: {r0}"

    # delta 2 : deux tours apres la mort (turn_counts 5 -> 7) -> ne doit PAS ressusciter (== 1 seulement)
    state.turn_counts[player] = 7
    r2 = start_turn_triggers(state, player)
    assert _alive(state, judh) is False, "delta 2 : ne doit PAS ressusciter (condition ==1, pas >=1)"
    assert not any(rr.get("ability") == "EnvAmbushResurrect" for rr in r2), f"resurrection a delta 2: {r2}"

    # delta 1 (sanity) : depuis turn_defeated 5, turn_counts=6 -> ressuscite
    state.turn_counts[player] = 6
    r1 = start_turn_triggers(state, player)
    assert _alive(state, judh) is True, "delta 1 : doit ressusciter"
    assert any(rr.get("ability") == "EnvAmbushResurrect" for rr in r1)


def test_g3_resurrect_is_one_shot(g3_state):
    """(D) ONE-SHOT (flag 0xe) : un porteur deja ressuscite qui re-meurt NE pose PAS de nouveau decoy
    (Ambush_Summon gate Not(HasFlag 0xe)) et NE re-ressuscite PAS."""
    state = g3_state["build_state"]()
    board = g3_state["board"]
    setup = _setup_open(state, board, JUDH_VIS)
    if setup is None:
        pytest.skip("setup geometrique infaisable")
    judh, isaak, T, t_coord = setup
    player = _player(state, judh)
    state.turn_counts[player] = 2
    _kill(state, judh, killer_id=isaak)
    _start_turn(state, player)                        # ressuscite (turn_counts 2->3, delta 1)
    assert _alive(state, judh) is True, "setup: 1re resurrection attendue"

    # re-tuer : Ambush_Summon gate Not(HasFlag 0xe) -> AUCUN decoy pose
    decoys_before = set(_all_by_vis(state, DECOY_VIS))
    res = _kill(state, judh, killer_id=isaak)
    assert not any(r.get("ability") == "Ambush_Summon" for r in res), f"Ambush_Summon a re-fire (0xe ignore): {res}"
    new = [d for d in _all_by_vis(state, DECOY_VIS) if d not in decoys_before]
    assert not new, f"un 2e decoy a ete pose malgre le flag one-shot: {new}"

    # re-avancer d'un tour : pas de 2e resurrection
    _start_turn(state, player)
    assert _alive(state, judh) is False, "2e resurrection interdite (flag 0xe)"


def test_g3_resurrect_emits_event_to_g2_bufffriends(g3_state):
    """(E) CHAINAGE `On(UnitResurrected=46)` : la resurrection d'un ALLIE (Judh) emet l'event qui atteint
    G2 `DecoysAndMisdirection_BuffFriends` (carrier Isaak vivant) -> pose l'effet 1379 (+582) sur Judh. Prouve
    que la resurrection publie bien `On(UnitResurrected)` (source live de G2/G5)."""
    state = g3_state["build_state"]()
    board = g3_state["board"]
    if state.effects is None:
        pytest.skip("state.effects indisponible (pas de couche effets pour verifier le chainage)")
    setup = _setup_open(state, board, JUDH_VIS)
    if setup is None:
        pytest.skip("setup geometrique infaisable")
    judh, isaak, T, t_coord = setup
    assert isaak != judh and _alive(state, isaak), "setup: Isaak (carrier) doit etre vivant et distinct"
    player = _player(state, judh)
    state.turn_counts[player] = 2
    _kill(state, judh, killer_id=isaak)
    res = _start_turn(state, player)
    assert _alive(state, judh) is True, "Judh doit etre ressuscite"

    # BuffFriends (owner Isaak, actor Judh) a pose l'effet 1379 sur Judh -> prouve l'emission de UnitResurrected
    effs = [e for e in state.effects.by_unit.get(judh, []) if int(getattr(e, "effect_type", -1)) == DECOYS_EXTRA_DMG]
    assert effs, ("effet 1379 absent sur le ressuscite : On(UnitResurrected) n'a pas atteint G2 BuffFriends "
                  f"(res={[r.get('ability') for r in res]})")
