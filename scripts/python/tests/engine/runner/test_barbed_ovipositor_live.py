"""Tyranids : `BarbedOvipositor` (passif de `tyranParasite` << Parasite of Mortrex >>) confronte au port.

BarbedOvipositor = **passiveAbility** -> ability-trigger (registre `ABILITY_TRIGGERS`, canal T), materialise
par UNE classe native (RE ghidra `gqfc5mff6c`, cf.
`engine/runner/operations/triggers/loki/barbed_ovipositor.py` pour l'arbre complet) :

  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateTrigger` =
      On(0=UnitDeath, 1) & OwnerIsActor & AreEnemies(owner@0x148, target@0x178)
      & NOT IsObjectOrSteppable(target@0x178)
      & NOT TriggeringAbilityIs(TriggeredAbilityType.ItsGonnaBlow = 1080)
      & NOT HasTrait(target@0x178, 5 = Mechanical)
  `...$$CreateBehaviour` =
      Spawn( owner@0x148,
             PickRandomly(CanAddUnit(Tiles(target@0x178)), 1)
               .Otherwise(PickRandomly(CanAddUnit(AdjacentTiles(target@0x178)), 1)),
             GetStringConstant(cfg,0) = "tyranSmnRipperSwarm",
             SpawnUnitOptions.WithStatsFromConfig(cfg, level) )

i2 : « When the Parasite of Mortrex defeats a unit it targeted that is not Mechanical it summons a Ripper
Swarm in the defeated unit's hex. »

CE FICHIER -- le CRITERE est « offline == live sur DEUX cas discriminants, dont un cas ou le passif NE
MORD PAS ». Les cas negatifs ne sont pas decoratifs : un summon-on-kill porte SANS ses gates rend le bon
chiffre quand la condition est vraie et ne se trahit QUE quand elle est fausse.

  1. LIVE (oracle, RE-independant) : le Parasite acheve un ennemi -> un Ripper Swarm apparait sur SA team,
     SUR la tuile du mort ; ses PV LIVE == `build_summon_context("BarbedOvipositor", level, mult)`.
  2. POSITIF offline    : meme scene hors-ligne -> 1 Ripper sur la tuile du mort.
  3. NEGATIF `Mechanical` (LE cas ou le passif NE MORD PAS) : victime `necroWarden` (trait Mechanical=5)
     -> AUCUN Ripper. C'est le gate que l'i2 enonce explicitement.
  4. NEGATIF `OwnerIsActor` : c'est l'ALLIE du Parasite qui tue -> AUCUN Ripper.
  5. NEGATIF `AreEnemies`   : la victime est un ALLIE du Parasite -> AUCUN Ripper.
  6. NEGATIF `IsObjectOrSteppable` : la victime est un decoy (trait Steppable=27) -> AUCUN Ripper.
  7. BRANCHE `Otherwise`    : la tuile du mort n'est pas `walkable` (cas d'une victime `Flying`) ->
     le Ripper tombe sur une tuile hex-adjacente LIBRE, jamais sur la tuile du mort.
  8. PAS de cap de summons : trois kills qualifiants -> trois Rippers (aucun `maxSummons` dans l'arbre
     natif, et `gameconfig.BarbedOvipositor.variables` n'en porte pas).
  9. REGIME CADAVRE (#462-r4b-r1-r1-r1-r1-b-r1-r1-r3) : une victime deja MORTE au chargement n'a
     AUCUN `StatsComponent` (`combatSnapshot.units` n'inclut pas les morts) -- les conjoints de
     trait, qui lisaient `ctx.traits` BRUT, y rendaient `set()` et etaient AVEUGLES. Les huit
     autres cas se jouent tous dans le regime NOMINAL et ne pouvaient donc pas le voir.

⚠ Les cas 3 et 6 gardent la RECOPIE tant qu'elle existe : depuis #462-...-r3 les conjoints passent
par les noeuds DSL du foyer `entities/triggers.py`, et c'est le cas 9 qui garde CE changement.

MONTAGE : fixture NOMMEE `barbed_scene` (fabrique de scenes, reutilisable et parametree) au-dessus du
runner module-scope `barbed_runner` -- UN seul slot du cap pour tous les cas offline. Positions DRIVE'es
(doctrine « drive positions, don't blame geometry »). ASCII only.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

PARASITE_VIS = "tyranParasite"        # Parasite of Mortrex (HERO Tyranids, pool rank 17)
ALLY_VIS = "tyranTyrantGuard"         # allie du Parasite (sert au cas negatif OwnerIsActor)
VICTIM_VIS = "astraBullgryn"          # victime NON-Mechanical, NON-Steppable (cas positif)
MECH_VIS = "necroWarden"              # victime MECHANICAL (trait 5) -> cas negatif du gate
RIPPER_KEY = "tyranSmnRipperSwarm"    # `GetStringConstant(cfg, 0)` = la CLE de config du summon
SUMMON_ABILITY = "BarbedOvipositor"
DECOY_VIS = "genesSmnDecoy"           # token Steppable (primitive `spawn_decoy`) -> cas negatif

BUILD = ["--roster", "1", "--p-units", f"{PARASITE_VIS},{ALLY_VIS}",
         "--a-units", f"{VICTIM_VIS},{MECH_VIS}"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


# --------------------------------------------------------------------------- fixtures NOMMEES

@dataclass
class BarbedScene:
    """Scene DRIVE'e d'un kill par le Parasite : etat offline + ids + tuiles utiles.

    `victim_tile` = la tuile ou la victime a ete POSEE = celle que le natif vise en priorite
    (`PickRandomly(CanAddUnit(Tiles(target)), 1)`)."""
    state: object
    board: object
    parasite: int
    ally: int
    victim: int
    parasite_tile: int
    victim_tile: int


@pytest.fixture(scope="module")
def barbed_runner(rpc, build_runner):
    """Runner ISOLE partage par TOUS les cas offline du fichier (un seul slot du cap partage).

    Les scenes sont re-chargees depuis les MEMES RPC a chaque test (`barbed_scene`) : chaque cas
    part donc d'un etat FRAIS sans consommer de runner supplementaire."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD, keep=True)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    return {"rid": rid, "board": Board(bg["tiles"], adjacency="evenq")}


@pytest.fixture
def barbed_scene(rpc, barbed_runner):
    """FABRIQUE de scenes (fixture NOMMEE, reutilisee par les 7 cas offline).

    `make(victim_vis=..., unwalkable=False)` :
      * charge un `State` FRAIS depuis les RPC du runner partage (kit + board LIVE) ;
      * cale `state.rng` sur le flux natif (`dumpRng`) -- le `PickRandomly(.,1)` du tile-selecteur
        consomme UN tirage meme a pool==1 (loi #130) ;
      * DRIVE les positions : Parasite sur une tuile A, victime sur une tuile B hex-adjacente, allie
        sur une tuile C adjacente a B -- geometrie stable, independante des spawns du board ;
      * `unwalkable=True` : pose la victime sur une tuile NON walkable (mirror d'une victime `Flying`
        morte sur un hex impassable) pour exercer la branche `Otherwise` du tile-selecteur.
    """
    def _make(victim_vis: str = VICTIM_VIS, unwalkable: bool = False) -> BarbedScene:
        state, board = _load(rpc, barbed_runner)
        par = _unit_by_vis(state, PARASITE_VIS)
        ally = _unit_by_vis(state, ALLY_VIS)
        vic = _unit_by_vis(state, victim_vis)
        if par is None or vic is None:
            pytest.skip(f"{PARASITE_VIS} ou {victim_vis} absent de l'etat offline")
        if unwalkable:
            spot = _unwalkable_with_free_neighbour(board, _occupied(state))
            if spot is None:
                pytest.skip("aucune tuile non-walkable avec voisin libre sur ce board")
            b, a = spot                                   # victime sur b (impassable), Parasite sur a
            _place(state, board, vic, b)
            _place(state, board, par, a)
            c = a
        else:
            trip = _open_triple(board, _occupied(state))
            if trip is None:
                pytest.skip("aucun triplet de tuiles libres adjacentes sur ce board")
            a, b, c = trip
            _place(state, board, par, a)
            _place(state, board, vic, b)
            if ally is not None:
                _place(state, board, ally, c)
        return BarbedScene(state=state, board=board, parasite=par, ally=ally, victim=vic,
                           parasite_tile=a, victim_tile=b)
    return _make


# --------------------------------------------------------------------------- helpers d'etat

def _load(rpc, runner):
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    rid, board = runner["rid"], runner["board"]
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


def _occupied(state):
    from engine.runner.operations.spawn import _occupied_tiles
    return _occupied_tiles(state)


def _place(state, board, uid, tile):
    from engine.runner.components import PositionComponent
    c, r = board.coord(tile)
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent)
    if pc is None:
        e.add_component(PositionComponent(col=c, row=r))
    else:
        pc.col, pc.row = c, r


def _open_triple(board, occupied):
    """(A, B, C) : trois tuiles walkable LIBRES, B voisine de A et C voisine de B. None si introuvable."""
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


def _unwalkable_with_free_neighbour(board, occupied):
    """(B, A) : B non walkable (ou la victime `Flying` peut mourir), A voisine walkable LIBRE.
    Sert a exercer la branche `Otherwise` du tile-selecteur. None si le board n'en porte pas."""
    for b in sorted(board.by_id):
        if board.walkable(b):
            continue
        free = [n for n in sorted(board.neighbours(b))
                if board.walkable(n) and n not in occupied]
        if free:
            return b, free[0]
    return None


def _kill(state, uid):
    from engine.runner.components import UnitComponent, HealthComponent
    e = state.get_entity(uid)
    e.get_component(UnitComponent).alive = False
    hc = e.get_component(HealthComponent)
    if hc is not None:
        hc.hp = 0


def _rippers(state):
    """ids des Ripper Swarms VIVANTS -- le port spawn avec la CLE de config (`_spawn_config_grot`)."""
    from engine.runner.components import UnitComponent
    return sorted(eid for eid, e in state.entities.items()
                  if (uc := e.get_component(UnitComponent)) is not None
                  and uc.alive and uc.visual_id == RIPPER_KEY)


def _fire_death(state, victim, killer):
    """Emet le vecteur `On(UnitDeath=0)` a sa place exacte (3e event de `KillUnitOperation$$Execute`)."""
    from engine.runner.operations.triggers.dispatch import unit_death_triggers
    return unit_death_triggers(state, victim, killer_id=killer)


def _barbed(out):
    return [r for r in out if isinstance(r, dict) and r.get("ability") == SUMMON_ABILITY]


def _tile_of_unit(state, board, uid):
    from engine.runner.components import PositionComponent
    pc = state.get_entity(uid).get_component(PositionComponent)
    return board.id_at(pc.col, pc.row) if pc is not None else None


# --------------------------------------------------------------------------- 1. ORACLE LIVE

def test_barbed_ovipositor_summons_ripper_live(live_session, rpc, build_runner):
    """ORACLE LIVE (RE-independant) : on DRIVE le Parasite au contact d'un ennemi a 1 PV
    (`--hp-target 1`) et on lui fait porter son attaque NORMALE -> l'ennemi meurt et un Ripper Swarm
    apparait SUR SA TEAM, SUR la tuile du mort. Les PV LIVE du Ripper sont confrontes a
    `build_summon_context("BarbedOvipositor", level, mult)` (ce qui valide la lecture kit gameconfig
    ET le fait que le natif utilise bien `WithStatsFromConfig(cfg)` et non un `CopyOwner`).

    Skip propre si le Parasite ne peut atteindre un ennemi dans la fenetre de tours."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.operations.spawn import build_summon_context

    rid = build_runner("31337", extra=BUILD + ["--hp-target", "1"])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec, par = _advance_to_my_turn(rpc, rid, PARASITE_VIS)
    if par is None:
        pytest.skip("Parasite of Mortrex absent / n'a pas atteint son tour")
    my_owner = par.get("owner")
    before = {u["id"] for u in _live_summons(dec)}

    killed, dec2 = _drive_kill_with_parasite(rpc, rid, board)
    if killed is None:
        pytest.skip("le Parasite n'a pas pu achever un ennemi (geometrie/tours)")
    victim_pos, victim_vis = killed

    new = [u for u in _live_summons(dec2) if u["id"] not in before]
    print(f"[barbed LIVE] victim={victim_vis}@{victim_pos} new_summons="
          f"{[(u['id'], u.get('visualId'), u.get('pos')) for u in new]}")

    assert new, ("aucun summon n'est apparu apres le kill du Parasite : "
                 "le passif BarbedOvipositor n'a pas fire LIVE")
    rip = new[0]
    assert rip.get("owner") == my_owner, \
        f"le Ripper n'appartient pas au camp du Parasite (owner={rip.get('owner')} != {my_owner})"
    assert (rip.get("pos") or {}) == victim_pos, \
        f"le Ripper n'est PAS sur la tuile du mort (got {rip.get('pos')}, want {victim_pos})"

    # PV attendus = WithStatsFromConfig(BarbedOvipositor) au niveau/multiplicateur du Parasite.
    # Le niveau vit dans `combatSnapshot.units[].unitConfig` (PAS dans decisionView) et les PV du
    # summon dans `observeBattle.units[].hp` -- memes sources que l'oracle ControlEdict.
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    pcfg = next(((u.get("unitConfig") or {}) for u in (snap2.get("units") or [])
                 if (u.get("unitConfig") or {}).get("visualId") == PARASITE_VIS), {})
    lvl = pcfg.get("activeAbilityLevel")
    mult = int(pcfg.get("abilityVariablesMultiplier") or 100)
    # ⚠ APPARIEMENT : `observeBattle` cle sur `entityId`, `decisionView` sur `id`, et les deux
    # DIVERGENT pour une unite SPAWNEE en cours de bataille (mesure : Ripper `id=105` cote
    # decisionView, `entityId=106` cote observeBattle). On apparie donc par (visualId, position) --
    # meme choix que l'oracle ControlEdict, et suffisant ici (un seul Ripper en jeu).
    live_hp = next((u.get("hp") for u in (ob2.get("units") or [])
                    if "ipper" in (u.get("visualId") or "") and not u.get("isDead")
                    and u.get("col") == victim_pos.get("col")
                    and u.get("row") == victim_pos.get("row")), None)
    print(f"[barbed LIVE] lvl={lvl} mult={mult} live_hp={live_hp} rip_dec_id={rip['id']}")
    assert lvl is not None, f"activeAbilityLevel du Parasite absent du combatSnapshot : {pcfg}"
    assert live_hp is not None, \
        (f"aucun Ripper VIVANT sur la tuile du mort {victim_pos} dans observeBattle : "
         f"{[(u.get('visualId'), u.get('col'), u.get('row')) for u in (ob2.get('units') or [])]}")
    ctx = build_summon_context(-1, RIPPER_KEY, SUMMON_ABILITY, lvl, mult)
    print(f"[barbed LIVE] hp live={live_hp} attendu={ctx.health} (level={lvl} mult={mult})")
    assert int(live_hp) == int(ctx.health), \
        (f"PV du Ripper live {live_hp} != WithStatsFromConfig {ctx.health} "
         f"-- la lecture kit gameconfig ou la source de stats du summon diverge")


def _live_summons(dec):
    """Unites LIVE dont le `visualId` designe un Ripper Swarm. Le champ live peut differer de la CLE de
    config (cf. `admecSmnVanguard`/`admecNpc1Vanguard` de ControlEdict) -> on accepte les deux formes."""
    out = []
    for u in (dec.get("units") or []):
        vis = (u.get("visualId") or "")
        if u.get("alive") and "ipper" in vis:          # tyranSmnRipperSwarm / tyranNpc*RipperSwarm
            out.append(u)
    return out


def _find(dec, vis, alive=True):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and (u.get("alive") or not alive)), None)


def _advance_to_my_turn(rpc, rid, vis, max_iter=20):
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if not _ok(dec):
            return None, None
        u = _find(dec, vis)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}, "captureEvents": False}, 60)
    return None, None


def _drive_kill_with_parasite(rpc, rid, board, max_turns=16, prefer_vis=None):
    """DRIVE : approche le Parasite d'un ennemi puis lui fait porter son attaque NORMALE. Les a-units
    ont 1 PV (`--hp-target 1`) -> le coup TUE. Renvoie ((pos_du_mort, visual_du_mort), decisionView
    d'apres) ou (None, None).

    `prefer_vis` : n'attaque QUE l'ennemi de ce `visualId` (sert au cas NEGATIF live, ou la victime
    doit imperativement etre le porteur du trait Mechanical)."""
    from collections import deque

    def _bfs(start):
        seen, q = {start: 0}, deque([start])
        while q:
            x = q.popleft()
            for n in board.neighbours(x):
                if n not in seen:
                    seen[n] = seen[x] + 1
                    q.append(n)
        return seen

    def _tile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    for _ in range(max_turns):
        dec, par = _advance_to_my_turn(rpc, rid, PARASITE_VIS)
        if par is None:
            return None, None
        pid = par["id"]
        foes = [u for u in (dec.get("units") or [])
                if u.get("alive") and u.get("owner") != par.get("owner")
                and (u.get("pos") or {}).get("col") is not None
                and (prefer_vis is None or u.get("visualId") == prefer_vis)]
        if not foes:
            return None, None
        tgt = foes[0]
        norm = next((a.get("id") for a in (par.get("abilities") or []) if a.get("kind") == "normal"),
                    None)
        # a portee depuis la tuile ACTUELLE ? (le Parasite est melee : portee 1)
        pt, et = _tile(par), _tile(tgt)
        if pt is not None and et is not None and _bfs(et).get(pt, 99) <= 1:
            plan = _normal_eval(dec, pid, norm, tgt["id"])
            if plan is not None:
                res = rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "ability", "casterId": pid, "targetId": plan[0],
                    "abilityType": plan[1]}, "captureEvents": True}, 120)
                dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
                dead = next((u for u in (dec2.get("units") or [])
                             if u.get("id") == tgt["id"] and not u.get("alive")), None)
                if _ok(res) and dead is not None:
                    return (tgt.get("pos") or {}, tgt.get("visualId")), dec2
                if _ok(res):
                    continue                       # pas mort -> on retente au tour suivant
        # approcher
        dgoal = _bfs(et) if et is not None else {}
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == pid), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or []) if t.get("col") is not None}
        pool = [t for t in reach if t in dgoal]
        if pool:
            best = min(pool, key=lambda t: dgoal[t])
            col, row = reach[best]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": pid, "to": {"col": col, "row": row}}}, 40)
            dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            par2 = _find(dec2, PARASITE_VIS)
            if par2 is not None and et is not None and _bfs(et).get(_tile(par2), 99) <= 1:
                plan = _normal_eval(dec2, pid, norm, tgt["id"])
                if plan is not None:
                    res = rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "ability", "casterId": pid, "targetId": plan[0],
                        "abilityType": plan[1]}, "captureEvents": True}, 120)
                    dec3 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
                    dead = next((u for u in (dec3.get("units") or [])
                                 if u.get("id") == tgt["id"] and not u.get("alive")), None)
                    if _ok(res) and dead is not None:
                        return (tgt.get("pos") or {}, tgt.get("visualId")), dec3
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return None, None


def test_barbed_ovipositor_mechanical_victim_live(live_session, rpc, build_runner):
    """ORACLE LIVE **NEGATIF** -- gate `NOT HasTrait(target@0x178, 5 = Mechanical)`.

    MEME drive que l'oracle positif, mais la victime imposee est `necroWarden` (Hero/LivingMetal/
    **Mechanical**) : le Parasite l'acheve et AUCUN Ripper n'apparait. C'est le pendant live du cas
    offline `test_barbed_ovipositor_skipped_when_victim_is_mechanical` -- sans lui, on aurait mesure
    un summon-on-kill INCONDITIONNEL et on ne s'en serait apercu sur aucun chiffre du cas positif."""
    from engine.entities.pathfinding.board import Board

    rid = build_runner("31337", extra=BUILD + ["--hp-target", "1"])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec, par = _advance_to_my_turn(rpc, rid, PARASITE_VIS)
    if par is None:
        pytest.skip("Parasite of Mortrex absent / n'a pas atteint son tour")
    before = {u["id"] for u in _live_summons(dec)}

    killed, dec2 = _drive_kill_with_parasite(rpc, rid, board, prefer_vis=MECH_VIS)
    if killed is None:
        pytest.skip(f"le Parasite n'a pas pu achever le {MECH_VIS} (geometrie/tours)")
    victim_pos, victim_vis = killed
    new = [u for u in _live_summons(dec2) if u["id"] not in before]
    print(f"[barbed LIVE - mechanical] victim={victim_vis}@{victim_pos} new_summons="
          f"{[(u['id'], u.get('visualId'), u.get('pos')) for u in new]}")

    assert victim_vis == MECH_VIS, f"la victime achevee n'est pas le porteur Mechanical : {victim_vis}"
    assert not new, \
        (f"gate Mechanical KO LIVE : un Ripper est apparu apres le kill d'une unite Mechanical "
         f"-> {[(u.get('visualId'), u.get('pos')) for u in new]}")


def _normal_eval(dec, caster_id, norm_id, want_target):
    """(targetId, abilityId) du plan d'attaque NORMALE du caster vers `want_target`, ou None."""
    for p in (dec.get("attackPlans") or []):
        if p.get("unitId") != caster_id:
            continue
        for ev in (p.get("evals") or []):
            if ev.get("targetId") != want_target:
                continue
            if norm_id is not None and ev.get("abilityId") != norm_id:
                continue
            return ev.get("targetId"), ev.get("abilityId")
    return None


# --------------------------------------------------------------------------- 2. POSITIF offline

def test_barbed_ovipositor_spawns_ripper_on_victim_hex_offline(barbed_scene):
    """POSITIF : le Parasite acheve un ennemi NON-Mechanical et NON-Steppable ->
      (a) le trigger fire sur `On(0=UnitDeath)` avec `OwnerIsActor` ;
      (b) UN Ripper Swarm est pose SUR la tuile du mort (branche primaire du tile-selecteur :
          la victime est `alive=False`, donc `CanAddUnit(Tiles(target))` la voit libre) ;
      (c) il appartient au camp du Parasite et le porte comme PARENT (`Unit_Parent_Id`)."""
    from engine.runner.components import OwnerComponent, UnitComponent, PositionComponent
    sc = barbed_scene()
    before = set(_rippers(sc.state))

    _kill(sc.state, sc.victim)
    out = _fire_death(sc.state, sc.victim, sc.parasite)
    res = _barbed(out)
    new = sorted(set(_rippers(sc.state)) - before)
    print(f"[barbed +] res={res} new={new} victim_tile={sc.victim_tile}")

    assert res, f"BarbedOvipositor n'a pas fire sur On(0=UnitDeath) : {out}"
    assert len(new) == 1, f"attendu 1 Ripper, obtenu {new}"
    rid_ = new[0]
    assert res[0].get("spawned") == [rid_], f"diag incoherent avec l'etat : {res[0]}"
    assert _tile_of_unit(sc.state, sc.board, rid_) == sc.victim_tile, \
        (f"le Ripper n'est pas sur la tuile du mort "
         f"(got {_tile_of_unit(sc.state, sc.board, rid_)}, want {sc.victim_tile})")
    p_team = sc.state.get_entity(sc.parasite).get_component(OwnerComponent).team
    r_own = sc.state.get_entity(rid_).get_component(OwnerComponent)
    assert r_own.team == p_team, f"Ripper hors du camp du Parasite (team {r_own.team} != {p_team})"
    r_uc = sc.state.get_entity(rid_).get_component(UnitComponent)
    assert r_uc.parent_id == sc.parasite, \
        f"lien parent absent : parent_id={r_uc.parent_id} (attendu {sc.parasite})"
    assert sc.state.get_entity(rid_).get_component(PositionComponent) is not None


def test_barbed_ovipositor_ripper_stats_from_config_offline(barbed_scene):
    """Le natif pose `SpawnUnitOptions.WithStatsFromConfig(cfg, level)` (et NON un `CopyOwner`) : les PV
    du Ripper viennent de `ability_var("BarbedOvipositor", "summonHp", level, mult)`, pas du Parasite.
    Confronte l'entite spawnee au `build_summon_context` de reference."""
    from engine.runner.components import HealthComponent, StatsComponent
    from engine.runner.operations.spawn import build_summon_context
    sc = barbed_scene()
    p_ctx = sc.state.get_entity(sc.parasite).get_component(StatsComponent).ctx
    lvl = getattr(p_ctx, "active_ability_level", None)
    mult = int(getattr(p_ctx, "ability_variables_multiplier", 100) or 100)

    _kill(sc.state, sc.victim)
    res = _barbed(_fire_death(sc.state, sc.victim, sc.parasite))
    assert res and res[0].get("spawned"), "aucun Ripper spawne (pre-cond)"
    rid_ = res[0]["spawned"][0]

    want = build_summon_context(-1, RIPPER_KEY, SUMMON_ABILITY, lvl, mult)
    hc = sc.state.get_entity(rid_).get_component(HealthComponent)
    print(f"[barbed stats] hp={hc.hp}/{hc.hp_max} attendu={want.health} (level={lvl} mult={mult})")
    assert int(hc.hp_max) == int(want.health), \
        f"PV du Ripper {hc.hp_max} != WithStatsFromConfig {want.health}"
    assert int(hc.hp) == int(hc.hp_max), "le Ripper ne spawn pas a PV pleins"


# --------------------------------------------------------------------------- 3-6. NEGATIFS

def test_barbed_ovipositor_skipped_when_victim_is_mechanical(barbed_scene):
    """NEGATIF -- gate `NOT HasTrait(target@0x178, 5 = Mechanical)`. **LE cas ou le passif NE MORD PAS**,
    et le seul que l'i2 enonce noir sur blanc (« a unit ... that is not Mechanical »).

    Sans ce gate, le port rendrait le BON chiffre sur le cas positif et resterait faux ici : c'est
    exactement le trou qu'un summon-on-kill porte sans ses gates laisse ouvert. La victime est un
    VRAI porteur du trait (`necroWarden` : Hero/LivingMetal/Mechanical), pas un etat mute."""
    sc = barbed_scene(victim_vis=MECH_VIS)
    before = set(_rippers(sc.state))

    _kill(sc.state, sc.victim)
    out = _fire_death(sc.state, sc.victim, sc.parasite)
    res = _barbed(out)
    new = sorted(set(_rippers(sc.state)) - before)
    print(f"[barbed - mechanical] res={res} new={new}")

    assert not res, f"gate Mechanical KO : le passif a fire sur une victime Mechanical : {res}"
    assert not new, f"gate Mechanical KO : un Ripper a ete pose : {new}"


def test_barbed_ovipositor_skipped_when_killer_is_an_ally(barbed_scene):
    """NEGATIF -- gate `get_OwnerIsActor`. C'est l'ALLIE du Parasite (`tyranTyrantGuard`) qui porte le
    coup fatal : le meme `On(0=UnitDeath)` est emis, mais le porteur n'est pas l'ACTEUR -> aucun Ripper.
    Sans ce gate, le Parasite recolterait un Ripper sur CHAQUE mort ennemie de la bataille."""
    sc = barbed_scene()
    if sc.ally is None:
        pytest.skip(f"{ALLY_VIS} absent de l'etat offline")
    before = set(_rippers(sc.state))

    _kill(sc.state, sc.victim)
    out = _fire_death(sc.state, sc.victim, sc.ally)          # actor = l'ALLIE, pas le Parasite
    res = _barbed(out)
    new = sorted(set(_rippers(sc.state)) - before)
    print(f"[barbed - other killer] res={res} new={new}")

    assert not res, f"gate OwnerIsActor KO : fire sur un kill d'allie : {res}"
    assert not new, f"gate OwnerIsActor KO : un Ripper a ete pose : {new}"


def test_barbed_ovipositor_skipped_when_victim_is_friendly(barbed_scene):
    """NEGATIF -- gate `AreEnemies(owner@0x148, target@0x178)`. La victime est un ALLIE du Parasite
    (friendly fire / crush) : aucun Ripper. Sans ce gate, une mort dans son propre camp le nourrirait."""
    sc = barbed_scene()
    if sc.ally is None:
        pytest.skip(f"{ALLY_VIS} absent de l'etat offline")
    before = set(_rippers(sc.state))

    _kill(sc.state, sc.ally)
    out = _fire_death(sc.state, sc.ally, sc.parasite)        # victime = un ALLIE
    res = _barbed(out)
    new = sorted(set(_rippers(sc.state)) - before)
    print(f"[barbed - friendly victim] res={res} new={new}")

    assert not res, f"gate AreEnemies KO : fire sur la mort d'un allie : {res}"
    assert not new, f"gate AreEnemies KO : un Ripper a ete pose : {new}"


def test_barbed_ovipositor_skipped_when_victim_is_steppable(barbed_scene):
    """NEGATIF -- gate `NOT IsObjectOrSteppable(target@0x178)` (= `HasTrait(27=Steppable) |
    HasTrait(13=Object)`). Un token Steppable ECRASE emet la MEME sequence de morts
    (`KillUnitOperation$$Execute`) : sans ce gate, pietiner un decoy ferait apparaitre un Ripper."""
    from engine.runner.operations.spawn import spawn_decoy
    sc = barbed_scene()
    # DRIVE : la victime degage, un decoy (Steppable) prend sa tuile.
    _place(sc.state, sc.board, sc.victim, sorted(sc.board.by_id)[-1])
    did = spawn_decoy(sc.state, sc.victim_tile, sc.parasite)
    assert did is not None, "spawn du decoy-victime KO (pre-cond)"
    before = set(_rippers(sc.state))

    _kill(sc.state, did)
    out = _fire_death(sc.state, did, sc.parasite)
    res = _barbed(out)
    new = sorted(set(_rippers(sc.state)) - before)
    print(f"[barbed - steppable] res={res} new={new}")

    assert not res, f"gate IsObjectOrSteppable KO : fire sur l'ecrasement d'un decoy : {res}"
    assert not new, f"gate IsObjectOrSteppable KO : un Ripper a ete pose : {new}"


# --------------------------------------------------------------------------- 7-8. structure de l'arbre

def test_barbed_ovipositor_falls_back_to_adjacent_tile(barbed_scene):
    """BRANCHE `Otherwise` du tile-selecteur. La victime meurt sur une tuile NON walkable (situation
    reelle : le Parasite lui-meme est `Flying`, « can traverse impassable hexes ») -> `CanAddUnit`
    REFUSE la tuile du mort et la branche de repli `PickRandomly(CanAddUnit(AdjacentTiles(target)),1)`
    prend le relais. Le Ripper apparait donc sur une tuile hex-adjacente LIBRE, jamais sur celle du mort.

    C'est le seul cas ou les deux branches du `Otherwise` divergent -- s'il tombait quand meme sur la
    tuile du mort, `CanAddUnit` serait un no-op silencieux."""
    sc = barbed_scene(unwalkable=True)
    before = set(_rippers(sc.state))

    _kill(sc.state, sc.victim)
    res = _barbed(_fire_death(sc.state, sc.victim, sc.parasite))
    new = sorted(set(_rippers(sc.state)) - before)
    tile = _tile_of_unit(sc.state, sc.board, new[0]) if new else None
    print(f"[barbed otherwise] new={new} tile={tile} victim_tile={sc.victim_tile} "
          f"walkable={sc.board.walkable(sc.victim_tile)}")

    assert not sc.board.walkable(sc.victim_tile), "pre-cond KO : la tuile de la victime est walkable"
    assert res and len(new) == 1, f"la branche de repli n'a pose aucun Ripper : {res}"
    assert tile != sc.victim_tile, "le Ripper est sur une tuile NON walkable (CanAddUnit inerte)"
    assert tile in set(sc.board.neighbours(sc.victim_tile)), \
        f"le Ripper n'est pas sur une tuile ADJACENTE au mort (tile={tile})"


def test_barbed_ovipositor_corpse_substrate_live(live_session, rpc, build_runner):
    """#462-r4b-r1-r1-r1-r1-b-r1-r1-r3 -- LE REGIME QUE LES SEPT AUTRES BRAS NE TOUCHENT PAS :
    une victime deja MORTE au chargement.

    Les deux conjoints de trait (`NOT IsObjectOrSteppable(sel@+0x60)`,
    `NOT HasTrait(sel@+0x60, 5)`) lisaient `StatsComponent.ctx.traits` BRUT, avec le repli `set()`.
    Or `combatSnapshot.units` **n'inclut pas les morts**, et `snapshot._load_stats_and_effects` ne
    pose de `StatsComponent` que pour ses lignes : un cadavre charge n'en a AUCUN, donc les deux
    gates rendaient `set()` -- AVEUGLES. Le natif, lui, lit
    `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`, dont la mort ne vide aucune
    collection.

    LE MONTAGE (partage avec `probe_..._r3`, aucun fork -- ce test l'IMPORTE) : le Parasite est
    place AU CONTACT d'un `necroWarden` a 1 PV (`--place`/`--a-place`), il l'acheve par son attaque
    NORMALE, **puis l'etat est RECHARGE**. Le cadavre y est alors sans `StatsComponent` : le regime
    discriminant, obtenu sur un etat LIVE et non fabrique. Un SECOND ennemi est laisse loin --
    sans lui le kill termine la bataille et `decisionView` rend une liste VIDE.

    Le trigger est ensuite emis sur ce cadavre (voie native `ResurrectUnitOperation$$Execute`, qui
    cible une unite DEFEATED et ne pose aucun `StatsComponent`). Contre-epreuve : la lecture BRUTE
    rejouee doit FIRE -- sinon le bras ne mesure pas le changement."""
    import probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_barbed_object_or_steppable as P

    rid = build_runner("777", extra=list(P.BUILD_EXTRA), board=P.BOARD)["rid"]
    m = P.mesurer_cadavre_live(rpc, rid)
    print(f"[barbed corpse] {m}")

    # --- non-vacuite du montage, AVANT tout verdict.
    assert m.get("tue"), (
        f"le Parasite n'a pas TUE le {P.MECH} depuis sa position -- montage KO, rien n'est mesure "
        f"(decisionView ids={m.get('dv_ids')})")
    assert m.get("stats") is False, (
        f"le cadavre PORTE un `StatsComponent` (stats={m.get('stats')}) : le regime discriminant "
        f"n'est PAS atteint sur cet etat live. Si `load_state` en pose desormais un a tout le "
        f"monde, c'est une BONNE nouvelle a instruire -- ce test doit alors etre re-ecrit, pas "
        f"assoupli. combatSnapshot ids={m.get('snap_ids')}")
    assert m.get("consultations"), (
        "MUTATION INERTE : les noeuds substitues de la contre-epreuve n'ont pas ete consultes "
        "-- un conjoint anterieur court-circuite, et la comparaison qui suit ne prouve rien.")

    # --- la divergence de substrat, LUE sur l'etat live.
    assert m.get("brut") == [], (
        f"la lecture BRUTE rend {m.get('brut')} sur ce cadavre -- la mesure de ce residu est "
        f"perimee.")
    assert "Mechanical" in (m.get("foyer") or ()), (
        f"le substrat FOYER ne porte pas `Mechanical` sur un {P.MECH} : {m.get('foyer')}")

    # --- le verdict, et la preuve que le changement CHANGE quelque chose.
    assert m.get("port") is False and m.get("rippers") == 0, (
        f"le port FIRE sur un mort `Mechanical` (fire={m.get('port')}, "
        f"rippers={m.get('rippers')}) : le gate est toujours aveugle sur un cadavre.")
    assert m.get("avant") is True, (
        "la lecture BRUTE rejouee NE fire PAS sur ce cadavre : elle ne reconstitue donc pas le "
        "port d'avant le fix, et ce test ne mesure aucun changement.")


def test_barbed_ovipositor_has_no_summon_cap(barbed_scene):
    """L'arbre natif ne porte AUCUN `AmountIsEqualOrGreater(UnitsWithId(Children(owner), ...), max)`
    -- contrairement a SquigHound/ControlEdict/SynapticLinchpin -- et `gameconfig.BarbedOvipositor
    .variables` n'expose pas de `maxSummons`. Trois kills qualifiants successifs doivent donc rendre
    TROIS Rippers. Ce test est le garde-fou contre l'ajout << par analogie >> d'un cap inexistant."""
    import gameconfig as GC
    assert "maxSummons" not in ((GC.ability(SUMMON_ABILITY) or {}).get("variables") or {}), \
        "le gameconfig porte un maxSummons : le port doit alors le gater (arbre a re-lire)"
    sc = barbed_scene()
    before = set(_rippers(sc.state))
    victims = [sc.victim] + [v for v in (sc.ally,) if v is not None]

    # 1er kill : la victime ennemie posee par la fixture.
    _kill(sc.state, sc.victim)
    _fire_death(sc.state, sc.victim, sc.parasite)
    # 2e et 3e : on re-tue la MEME entite apres l'avoir << ressuscitee >> ailleurs -- ce qui compte est
    # que le trigger fire 3 fois sur 3 morts qualifiantes, pas l'identite des victimes.
    from engine.runner.components import UnitComponent
    n_fired = 1
    for _ in range(2):
        free = [t for t in sorted(sc.board.by_id)
                if sc.board.walkable(t) and t not in _occupied(sc.state)]
        if not free:
            break
        sc.state.get_entity(sc.victim).get_component(UnitComponent).alive = True
        _place(sc.state, sc.board, sc.victim, free[0])
        _kill(sc.state, sc.victim)
        if _barbed(_fire_death(sc.state, sc.victim, sc.parasite)):
            n_fired += 1
    new = sorted(set(_rippers(sc.state)) - before)
    print(f"[barbed no-cap] fired={n_fired} rippers={new} (victims={victims})")

    assert n_fired == 3, f"le trigger n'a fire que {n_fired} fois sur 3 morts qualifiantes"
    assert len(new) == 3, f"attendu 3 Rippers (aucun cap), obtenu {len(new)} : {new}"
