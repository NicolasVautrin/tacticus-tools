"""Genestealer Cults : `CosmicHorror` (passif de `genesPatriarch` << The Patermine >>) confronte au port.

CosmicHorror = **passiveAbility** -> ability-trigger (registre `ABILITY_TRIGGERS`), materialisee par
DEUX abilities natives distinctes (RE ghidra gqfc5mff6c, cf.
`engine/runner/operations/triggers/loki/cosmic_horror.py`) :
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnKillAbility$$CreateTrigger` =
    `On(0x37=UnitDefeated) & OwnerIsActor & AreEnemies & NOT HasTrait(target, Steppable)` ;
    `...$$CreateBehaviour` = `Spawn(decoy sur la tuile du mort)` op_BitwiseAnd
    `Foreach(Enemies(SurroundingTiles(mort,0,1)), Maybe(TriggerAbility(BattleFatigue)
     & If(IsAlive, AddEffect(Pinned 1065)), ConfigVar(chance)))`.
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnMoveAbility$$CreateTrigger` =
    `On(0x36=PostUnitKill) & OwnerIsActor & AreFriends & HasTrait(target, Decoy)` ;
    `...$$CreateBehaviour` = `Heal(caster, caster, ConfigVar(hp))`.

CE FICHIER (port-agreement offline, board natif evenq + kit gameconfig LIVE ; positions DRIVE'es) --
DEUX cas discriminants par volet, dont un cas NEGATIF ou le passif NE MORD PAS :

  volet OnKill
    1. POSITIF  : le Patermine acheve un ennemi normal -> decoy sur SA tuile + l'ennemi de l'anneau
                  recoit Pinned (1065) quand le `Maybe` passe ;
    2. NEGATIF (gate `NOT HasTrait(Steppable)`) : la victime est un DECOY (Steppable) -> le trigger ne
                  matche PAS : aucun decoy pose, aucun Pinned ;
    3. STRUCTURE du `Maybe` : quand le tirage ECHOUE, le decoy est QUAND MEME pose (il est HORS du
                  `Maybe`) mais AUCUN Pinned n'est applique -> prouve que le natif n'a qu'UN SEUL
                  `Maybe`, englobant les deux volets (et non les deux 60 % independants de l'i2).

  volet OnMove
    4. POSITIF  : le Patermine (blesse) marche sur un decoy ALLIE -> crush + `Heal(hp)` ;
    5. NEGATIF (gate `AreFriends`) : le decoy ecrase appartient a l'ENNEMI -> AUCUN heal.

Le RNG du `Maybe` est cale par un stub deterministe (`next_bool` force) : `next_bool(chance)` natif
rend `v in [1,99] <= chance` -> avec `chance` in [40,60] aucune des deux branches n'est atteignable de
facon deterministe par le seul niveau. Le stub n'entre PAS dans le moteur : il ne sert qu'a EXERCER
les deux branches du `Maybe` (le pont natif `MaybeBehaviour.Execute` -> `next_bool` est, lui, porte
tel quel et exerce dans le test 1 par le rng natif recupere du live).

ASCII only."""
from __future__ import annotations

import pytest

PATRIARCH_VIS = "genesPatriarch"       # The Patermine (HERO GS Cults, pool rank 17)
PINNED = 1065                          # EffectType.Pinned (0x429) — UI « Suppressed »
DECOY_VIS = "genesSmnDecoy"
BUILD = ["--roster", "1", "--p-units", f"{PATRIARCH_VIS},genesPrimus",
         "--a-units", "necroWarden,necroWarden"]


class _RngStub:
    """Stub deterministe du `Maybe` (`MaybeBehaviour.Execute` -> `IPseudoRNG.NextBool`). Compte les
    appels pour verifier qu'il y a bien UN tirage par victime (et pas deux)."""

    def __init__(self, value: bool):
        self.value = bool(value)
        self.calls = 0

    def next_bool(self, chance):
        self.calls += 1
        return self.value

    def next_internal(self, lo, hi):        # PickRandomly (non utilise ici, mais l'API doit tenir)
        return lo

    def next(self, bound):
        return 0


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _load(rpc, build_runner, seed="777"):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    rid = build_runner(seed, extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dec, ob, snap, board=board)
    if _ok(s0) and s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        state.rng = rng
    return state, board


def _unit_by_vis(state, vis):
    from engine.runner.components import UnitComponent
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == vis and uc.alive:
            return eid
    return None


def _enemy_ids(state, of_id):
    from engine.runner.components import OwnerComponent, UnitComponent
    team = state.get_entity(of_id).get_component(OwnerComponent).team
    out = []
    for eid, e in state.entities.items():
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        if oc is None or uc is None or not uc.alive or oc.team == team:
            continue
        out.append(eid)
    return sorted(out)


def _occupied(state):
    from engine.runner.operations.spawn import _occupied_tiles
    return _occupied_tiles(state)


def _place(state, board, uid, tile):
    from engine.runner.components import PositionComponent
    c, r = board.coord(tile)
    pc = state.get_entity(uid).get_component(PositionComponent)
    if pc is None:
        state.get_entity(uid).add_component(PositionComponent(col=c, row=r))
    else:
        pc.col, pc.row = c, r


def _open_triple(board, occupied):
    """(A, B, C) : trois tuiles walkable LIBRES, B voisine de A et C voisine de B -- de quoi poser le
    Patermine (A), sa victime (B) et un ennemi de l'anneau de la victime (C). None si introuvable."""
    for a in sorted(board.by_id):
        if not board.walkable(a) or a in occupied:
            continue
        for b in sorted(board.neighbours(a)):
            if b == a or not board.walkable(b) or b in occupied:
                continue
            for c in sorted(board.neighbours(b)):
                if c in (a, b) or not board.walkable(c) or c in occupied:
                    continue
                return a, b, c
    return None


def _prep_kill(rpc, build_runner, roll: bool):
    """Scene OnKill DRIVE'e : Patermine en A, victime (ennemi) en B adjacente, 2e ennemi en C (anneau
    de B). Renvoie (state, board, pat, victim, bystander, tile_b)."""
    state, board = _load(rpc, build_runner)
    pat = _unit_by_vis(state, PATRIARCH_VIS)
    if pat is None:
        pytest.skip("genesPatriarch absent de l'etat offline")
    if state.effects is None:
        pytest.skip("EffectsState absent (snapshot sans combatSnapshot) -> AddEffect impossible")
    foes = _enemy_ids(state, pat)
    if len(foes) < 2:
        pytest.skip("moins de 2 ennemis vivants -> pas de victime + bystander")
    victim, bystander = foes[0], foes[1]
    trip = _open_triple(board, _occupied(state) - {board.id_at(*_pos(state, u)) for u in (pat, victim, bystander)})
    if trip is None:
        pytest.skip("aucun triplet de tuiles libres adjacentes sur ce board")
    a, b, c = trip
    _place(state, board, pat, a)
    _place(state, board, victim, b)
    _place(state, board, bystander, c)
    state.rng = _RngStub(roll)
    return state, board, pat, victim, bystander, b


def _pos(state, uid):
    from engine.runner.components import PositionComponent
    pc = state.get_entity(uid).get_component(PositionComponent)
    return (pc.col, pc.row) if pc is not None else (0, 0)


def _kill(state, uid):
    from engine.runner.components import UnitComponent, HealthComponent
    e = state.get_entity(uid)
    e.get_component(UnitComponent).alive = False
    hc = e.get_component(HealthComponent)
    if hc is not None:
        hc.hp = 0


def _decoys(state):
    from engine.runner.components import UnitComponent
    return [eid for eid, e in state.entities.items()
            if (uc := e.get_component(UnitComponent)) is not None
            and uc.alive and uc.visual_id == DECOY_VIS]


# ------------------------------------------------------------------ volet OnKill (On(0x37))

def test_cosmic_horror_on_kill_spawns_decoy_and_pins(live_session, rpc, build_runner):
    """POSITIF OnKill : le Patermine acheve un ennemi NON-steppable ->
      (a) un decoy `genesSmnDecoy` est pose sur la tuile du mort (`FreeTilesOrAdjacentFreeTiles(
          Tiles(target))` : la victime est `alive=False` donc sa tuile est libre) ;
      (b) l'ennemi de l'anneau (dist 1 de la victime) recoit `Pinned` (1065) -- le `Maybe` passe."""
    from engine.runner.operations.triggers.dispatch import unit_defeated_triggers
    state, board, pat, victim, bystander, tile_b = _prep_kill(rpc, build_runner, roll=True)
    before = set(_decoys(state))
    assert not state.effects.has_effect(bystander, effect_type=PINNED), "bystander deja Pinned (pre-cond KO)"

    _kill(state, victim)
    out = unit_defeated_triggers(state, victim, killer_id=pat)
    ch = [r for r in out if isinstance(r, dict) and r.get("ability") == "CosmicHorror_OnKill"]
    new = set(_decoys(state)) - before
    print(f"[cosmic kill+] res={ch} new_decoys={sorted(new)} tile_b={tile_b} "
          f"pinned={state.effects.has_effect(bystander, effect_type=PINNED)} rng_calls={state.rng.calls}")

    assert ch, f"CosmicHorror_OnKill n'a pas fire sur On(0x37) : {out}"
    assert ch[0].get("decoy") is not None, f"aucun decoy spawne : {ch}"
    assert ch[0].get("decoy_tile") == tile_b, \
        f"decoy pose ailleurs que sur la tuile du mort (got {ch[0].get('decoy_tile')}, want {tile_b})"
    assert new, "aucune nouvelle entite decoy dans l'etat"
    assert bystander in (ch[0].get("surrounding") or []), \
        f"l'ennemi de l'anneau n'est pas dans Enemies(SurroundingTiles(mort,0,1)) : {ch[0]}"
    assert state.rng.calls == len(ch[0]["surrounding"]), \
        f"le Maybe doit tirer UNE fois par victime (calls={state.rng.calls}, victimes={ch[0]['surrounding']})"
    assert state.effects.has_effect(bystander, effect_type=PINNED), \
        "tirage reussi mais l'ennemi de l'anneau n'est PAS Pinned (1065)"


def test_cosmic_horror_on_kill_skipped_when_victim_is_steppable(live_session, rpc, build_runner):
    """NEGATIF OnKill (LE cas ou le passif NE MORD PAS) -- gate `NOT HasTrait(target, Steppable=0x1b)`.
    Le natif emet la MEME sequence de morts pour un steppable ecrase (`KillUnitOperation$$Execute`) :
    sans ce gate, achever/ecraser un decoy re-declencherait le passif. Ici la victime est un DECOY
    (trait Steppable) -> `matches` doit refuser : aucun nouveau decoy, aucun Pinned."""
    from engine.runner.operations.triggers.dispatch import unit_defeated_triggers
    from engine.runner.operations.spawn import spawn_decoy
    state, board, pat, victim, bystander, tile_b = _prep_kill(rpc, build_runner, roll=True)
    # DRIVE : la victime devient un DECOY (steppable) pose sur la meme tuile B, l'ancien ennemi degage.
    _place(state, board, victim, sorted(board.by_id)[-1])
    did = spawn_decoy(state, tile_b, pat)
    assert did is not None, "spawn du decoy-victime KO (pre-cond)"
    before = set(_decoys(state))

    _kill(state, did)
    out = unit_defeated_triggers(state, did, killer_id=pat)
    ch = [r for r in out if isinstance(r, dict) and r.get("ability") == "CosmicHorror_OnKill"]
    new = set(_decoys(state)) - before
    print(f"[cosmic kill- steppable] res={ch} new_decoys={sorted(new)} "
          f"pinned={state.effects.has_effect(bystander, effect_type=PINNED)}")

    assert not ch, f"gate NOT Steppable KO : le passif a fire sur la mort d'un decoy : {ch}"
    assert not new, f"gate KO : un decoy a ete pose alors que la victime etait Steppable : {sorted(new)}"
    assert not state.effects.has_effect(bystander, effect_type=PINNED), \
        "gate KO : Pinned applique alors que la victime etait Steppable"


def test_cosmic_horror_on_kill_single_maybe_covers_both_volets(live_session, rpc, build_runner):
    """STRUCTURE : le `Maybe` du decompile englobe `TriggerAbility(BattleFatigue) & If(IsAlive,
    AddEffect(Pinned))` -- et RIEN d'autre. Tirage FORCE A FAUX :
      * le decoy EST quand meme pose (le `Spawn` est HORS du `Maybe`, en op_BitwiseAnd du `Foreach`) ;
      * AUCUN Pinned n'est applique (les deux volets tombent ENSEMBLE).
    C'est ce qui distingue le decompile de la prose i2 (« 60 % ... et 60 % ... », deux tirages)."""
    from engine.runner.operations.triggers.dispatch import unit_defeated_triggers
    state, board, pat, victim, bystander, tile_b = _prep_kill(rpc, build_runner, roll=False)
    before = set(_decoys(state))

    _kill(state, victim)
    out = unit_defeated_triggers(state, victim, killer_id=pat)
    ch = [r for r in out if isinstance(r, dict) and r.get("ability") == "CosmicHorror_OnKill"]
    new = set(_decoys(state)) - before
    hits = (ch[0].get("hits") if ch else []) or []
    print(f"[cosmic kill maybe-false] new_decoys={sorted(new)} hits={hits} "
          f"pinned={state.effects.has_effect(bystander, effect_type=PINNED)}")

    assert ch, f"CosmicHorror_OnKill n'a pas fire : {out}"
    assert ch[0].get("decoy") is not None and new, \
        "le decoy doit etre pose MEME quand le tirage echoue (Spawn hors du Maybe)"
    assert hits and all(h.get("rolled") is False for h in hits), f"tirages non refutes : {hits}"
    assert all(h.get("pinned") is False and h.get("fatigue") is None for h in hits), \
        f"tirage rate mais un volet a quand meme mordu : {hits}"
    assert not state.effects.has_effect(bystander, effect_type=PINNED), \
        "tirage rate mais Pinned applique -> le Maybe n'englobe pas le AddEffect"


def test_cosmic_horror_on_kill_retriggers_battle_fatigue_only_on_carriers(live_session, rpc, build_runner):
    """`TriggerAbility(subject@0x180, 0x401=TriggeredAbilityType.BattleFatigue)` -- « trigger Battle
    Fatigue a second time, **if they have it** ». DEUX bystanders dans l'anneau du mort, tirage force
    a VRAI :
      * un summon ENNEMI porteur du trait `BattleFatigue` (`genesSmnNeophyte`) -> le behaviour de son
        BattleFatigue s'execute (`FleeOperation` : flag `UnitFlag.Fled=9`) ;
      * un ennemi SANS le trait -> `fatigue is None` (no-op fidele, pas d'ability a re-declencher).
    Les DEUX recoivent Pinned (le meme tirage couvre les deux volets)."""
    from engine.runner.operations.triggers.dispatch import unit_defeated_triggers
    from engine.runner.operations.spawn import _spawn_config_grot
    from engine.runner.components import OwnerComponent, UnitFlagsComponent
    state, board, pat, victim, bystander, tile_b = _prep_kill(rpc, build_runner, roll=True)
    # DRIVE : un 3e ennemi PORTEUR de BattleFatigue, place dans l'anneau de la victime.
    foe_team = state.get_entity(bystander).get_component(OwnerComponent)
    occ = _occupied(state)
    ring = [n for n in sorted(board.neighbours(tile_b))
            if n not in occ and board.walkable(n)]
    if not ring:
        pytest.skip("aucune tuile libre dans l'anneau de la victime pour poser le porteur")
    carrier = _spawn_config_grot(state, "genesSmnNeophyte", ring[0], "SpiritualLeader", 50, 100,
                                 foe_team.team, foe_team.player, ai_controlled=False)
    if carrier is None:
        pytest.skip("spawn du porteur BattleFatigue KO")

    _kill(state, victim)
    out = unit_defeated_triggers(state, victim, killer_id=pat)
    ch = [r for r in out if isinstance(r, dict) and r.get("ability") == "CosmicHorror_OnKill"]
    hits = {h["enemy"]: h for h in ((ch[0].get("hits") if ch else []) or [])}
    fl = state.get_entity(carrier).get_component(UnitFlagsComponent)
    print(f"[cosmic fatigue] hits={hits} carrier={carrier} fled={fl and fl.has(UnitFlagsComponent.FLED)}")

    assert ch, f"CosmicHorror_OnKill n'a pas fire : {out}"
    assert carrier in hits, f"le porteur BattleFatigue n'est pas dans l'anneau : {hits}"
    assert hits[carrier].get("fatigue") is not None, \
        f"TriggerAbility(BattleFatigue) n'a pas re-declenche le passif du porteur : {hits[carrier]}"
    assert fl is not None and fl.has(UnitFlagsComponent.FLED), \
        "le porteur n'a pas fui : le behaviour BattleFatigue n'a pas ete execute"
    assert bystander in hits and hits[bystander].get("fatigue") is None, \
        f"un non-porteur a re-declenche BattleFatigue : {hits.get(bystander)}"
    assert state.effects.has_effect(carrier, effect_type=PINNED), "porteur non Pinned (meme tirage)"
    assert state.effects.has_effect(bystander, effect_type=PINNED), "non-porteur non Pinned (meme tirage)"


# ------------------------------------------------------------------ volet OnMove (On(0x36))

def _prep_move(rpc, build_runner):
    """Scene OnMove DRIVE'e : Patermine BLESSE en A, une tuile B adjacente libre ou poser un decoy."""
    state, board = _load(rpc, build_runner)
    pat = _unit_by_vis(state, PATRIARCH_VIS)
    if pat is None:
        pytest.skip("genesPatriarch absent de l'etat offline")
    from engine.runner.components import HealthComponent, PositionComponent
    hc = state.get_entity(pat).get_component(HealthComponent)
    if hc is None or not hc.hp_max:
        pytest.skip("Patermine sans HealthComponent -> heal non observable")
    hc.hp = max(1, int(hc.hp_max) // 4)                 # blesse : le heal doit etre observable
    pc = state.get_entity(pat).get_component(PositionComponent)
    tile_a = board.id_at(pc.col, pc.row)
    occ = _occupied(state)
    tile_b = next((n for n in sorted(board.neighbours(tile_a))
                   if n not in occ and board.walkable(n)), None)
    if tile_b is None:
        pytest.skip("aucune tuile libre adjacente au Patermine")
    return state, board, pat, tile_a, tile_b, hc


def test_cosmic_horror_on_move_heals_when_stepping_on_friendly_decoy(live_session, rpc, build_runner):
    """POSITIF OnMove : le Patermine marche sur un decoy ALLIE -> `_kill_steppable_units` le crushe,
    `after_move_triggers` emet `On(0x36=PostUnitKill)` {actor=Patermine, target=decoy}, et
    `Heal(caster, caster, ConfigVar(hp))` le soigne."""
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.spawn import spawn_decoy
    from engine.runner.operations.triggers.dispatch import after_move_triggers
    state, board, pat, tile_a, tile_b, hc = _prep_move(rpc, build_runner)
    did = spawn_decoy(state, tile_b, pat)               # decoy ALLIE (CopyOwner du caster)
    assert did is not None, "spawn decoy KO (pre-cond)"
    hp0 = int(hc.hp)

    MoveUnitOperation(pat, board.coord(tile_b)).execute(state, EventBus())
    out = after_move_triggers(state, pat)
    ch = [r for r in out if isinstance(r, dict) and r.get("ability") == "CosmicHorror_OnMove"]
    print(f"[cosmic move+] res={ch} hp {hp0} -> {hc.hp} (max {hc.hp_max})")

    assert ch, f"CosmicHorror_OnMove n'a pas fire sur On(0x36) : {out}"
    assert ch[0].get("decoy") == did, f"le crushe rapporte n'est pas le decoy pose : {ch[0]}"
    assert int(ch[0].get("amount") or 0) > 0, f"montant de heal nul : {ch[0]}"
    assert int(hc.hp) > hp0, f"aucun heal applique (hp {hp0} -> {hc.hp})"


def test_cosmic_horror_on_move_no_heal_on_enemy_decoy(live_session, rpc, build_runner):
    """NEGATIF OnMove (LE cas ou le passif NE MORD PAS) -- gate `AreFriends(caster, target)`. Le decoy
    ecrase appartient a l'ENNEMI : `On(0x36)` est bien emis (le crush a lieu), mais le trigger refuse
    -> AUCUN heal. Sans ce gate, le Patermine se soignerait en pietinant les leurres adverses."""
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.spawn import spawn_decoy
    from engine.runner.operations.triggers.dispatch import after_move_triggers
    from engine.runner.components import OwnerComponent
    state, board, pat, tile_a, tile_b, hc = _prep_move(rpc, build_runner)
    foes = _enemy_ids(state, pat)
    if not foes:
        pytest.skip("aucun ennemi vivant -> pas de decoy ENNEMI possible")
    did = spawn_decoy(state, tile_b, foes[0])           # decoy de l'equipe ADVERSE
    assert did is not None, "spawn decoy ennemi KO (pre-cond)"
    d_team = state.get_entity(did).get_component(OwnerComponent).team
    p_team = state.get_entity(pat).get_component(OwnerComponent).team
    assert d_team != p_team, "pre-cond KO : le decoy n'est pas dans l'equipe adverse"
    hp0 = int(hc.hp)

    MoveUnitOperation(pat, board.coord(tile_b)).execute(state, EventBus())
    out = after_move_triggers(state, pat)
    ch = [r for r in out if isinstance(r, dict) and r.get("ability") == "CosmicHorror_OnMove"]
    print(f"[cosmic move- enemy decoy] res={ch} hp {hp0} -> {hc.hp}")

    assert not ch, f"gate AreFriends KO : heal sur un decoy ENNEMI : {ch}"
    assert int(hc.hp) == hp0, f"gate KO : hp modifie ({hp0} -> {hc.hp}) sur un decoy ennemi"
