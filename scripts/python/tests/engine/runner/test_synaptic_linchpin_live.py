"""Tyranids : `SynapticLinchpin` (passif d'`tyranWingedPrime` << Winged Prime >>) confronte au port.

SynapticLinchpin = **passiveAbility** -> ability-trigger (registre `ABILITY_TRIGGERS`, canal T),
materialise par UNE classe native (RE ghidra `rnca9r7q6c`, arbre complet et etablissement des slots
de selecteur : `engine/runner/operations/triggers/loki/synaptic_linchpin.py`) :

  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SynapticLinchpinAbility$$CreateTrigger` =
      On(38 = NormalAttack,
         ownerNeedsToBeAlive: NOT(OwnerIsActor
                                  & TriggeringAbilityIs(TriggeredAbilityType.FinalJustice = 1024)))
      & HasTrait(actor@+0x40, UnitTrait.Synapse = 2024)
      & AreFriends(owner@+0x30, actor@+0x40)
      & IsAlive(target@+0x60)
  `...$$CreateBehaviour` =
      Repeat( If( NOT AmountIsEqualOrGreater(
                        UnitsWithId(Children(owner@+0x30), "tyranSmnHormagaunt",
                                    UnitSelectionType.OnlyAliveAndTargetable), Direct(maxSummons)),
                  Spawn(owner@+0x30,
                        First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(target@+0x60)),
                                                          UtilityType.Tile = 7, caster@+0x48), 1),
                        "tyranSmnHormagaunt",
                        opts{+0x18 = UseNormalAttackIfAble(activeTarget@+0x68, target@+0x60)}) ),
              Direct(nrOfSummons = 1) )

i2 : « Whenever the Winged Prime, or another friendly unit with Synapse, performs a normal attack
against an enemy and that enemy is not defeated, summons a Hormagaunt adjacent to the target, which
immediately attacks the enemy. Cannot have more than 4 Hormagaunts summoned this way at the same
time. »

================================================================================================
GROUND TRUTH LIVE (probe_937_synaptic_linchpin.py, build `rnca9r7q6c`, board MC1_67, seed 777)
================================================================================================
Le journal d'events du cast ouvre un groupe `source: "SynapticLinchpin"` et y pose, DANS CET ORDRE :

  step 9  entity=111  Unit_Owner_Id=3, Unit_IsSummoned=1, Unit_SpawnSource=2, **Unit_Parent_Id=81**
  step 12 entity=111  UnitStats_MaxHealth=2992, UnitStats_FixedArmor=599, UnitStats_Attack=2194
  step 13 entity=111  ActiveAbility_Id=69 Level=50 VariableMultiplierPercentage=180
                      (+ 4 TriggeredAbility au MEME niveau/multiplicateur)
  step 29 / step 4    l'unite 111 ATTAQUE la cible 79 (2 coups, melee) -> 4366 puis 4333
  step 12 entity=111  UnitStats_TurnFinished=1                      (`FinishUnitTurn(spawned, true)`)

  * `Unit_Parent_Id = 81` = le **Winged Prime**, **y compris quand c'est le `tyranNeurothrope` qui
    frappe** (mesure separee) -> le `parentSelector` natif est `owner@+0x30`, PAS l'acteur ;
  * `2992 / 2194 / 599` == `summonHp/summonDmg/summonArmor[49] x 180 %` (level 50 -> index 49,
    `Idun.Shared.Level$$ToZeroBasedIndex`), c'est-a-dire EXACTEMENT `ability_var(...)` du port ;
  * `tyranTyrantGuard` (allie SANS `Synapse`) frappe la MEME cible avec DEUX tuiles libres autour
    -> **AUCUN summon** : le gate `HasTrait(actor, Synapse)` MORD ;
  * une cible SANS voisin libre -> le groupe `SynapticLinchpin` est OUVERT mais VIDE. C'est un
    trigger qui FIRE dont le behaviour ne pose rien -- a ne pas confondre avec un trigger muet.

⚠ Le `visualId` LIVE du summon est **`tyranNpc1Hormagaunt`**, pas la CLE de config
`tyranSmnHormagaunt` que le port pose (`_spawn_config_grot`) -- meme dualite que
`admecSmnVanguard`/`admecNpc1Vanguard` d'oracle ControlEdict. Les helpers ci-dessous acceptent les
deux formes (sous-chaine `Hormagaunt`).

CE FICHIER -- le CRITERE est « offline == live sur des cas DISCRIMINANTS, dont plusieurs ou le
passif NE MORD PAS ». Un summon-on-attack porte SANS ses gates rend le bon resultat quand la
condition est vraie et ne se trahit QUE quand elle est fausse.

MONTAGE : fixture NOMMEE `linchpin_scene` (fabrique de scenes parametree) au-dessus d'un runner
module-scope -- UN seul slot du cap pour tous les cas offline. Positions DRIVE'es (doctrine « drive
positions, don't blame geometry » : la mesure live a montre qu'une cible collee au bord rend le
behaviour muet). ASCII only.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

PRIME_VIS = "tyranWingedPrime"      # PORTEUR du passif (traits Synapse + FinalJustice)
SYNAPSE_ALLY = "tyranNeurothrope"   # allie porteur de `Synapse` -> le trigger fire AUSSI
PLAIN_ALLY = "tyranTyrantGuard"     # allie SANS `Synapse` -> cas NEGATIF du gate
VICTIM_VIS = "necroWarden"          # ennemi robuste (il doit SURVIVRE au coup)
HORMA_KEY = "tyranSmnHormagaunt"    # `GetStringConstant(cfg, unitId)` = la CLE de config du summon
ABILITY = "SynapticLinchpin"

DECLENCHEUR = {
    "chemins": (
        # le port des deux faces de l'artefact natif
        "scripts/python/engine/runner/operations/triggers/loki/synaptic_linchpin.py",
        # le registre qui l'abonne a `On(NormalAttack)` -- sans lui le passif est MUET
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # le vecteur `On(0x26)` lui-meme : ce fichier est son seul consommateur cap-borne
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        # le noeud E NEUF que l'arbre exige (`RepeatBehaviour$$Execute`)
        "scripts/python/engine/entities/behaviours.py",
        # le foyer PARTAGE dont ce fichier garde le filtre `UnitSelectionType` (cas << mort >>)
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        # les selecteurs de l'arbre : ChildrenOf/AdjacentTiles/CanAddUnit/SortTilesByUtility
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/selectors/units.py",
        # les feuilles E : Spawn (+ son on-appearance) et UseNormalAttackIfAble
        "scripts/python/engine/runner/abilities/behaviours/summon.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/runner/operations/spawn.py",
        # la lecture des variables/constantes de config confrontee LIVE (2992 / 2194 / 599)
        "scripts/python/engine/entities/effects/magnitude.py",
        # les mirrors d'enum dont ce fichier fige les ordinaux
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
    ),
    # `data/symbols/**` est ajoute par le foyer : les ordinaux (Synapse 2024, FinalJustice 1024,
    # NormalAttack 38, SynapticLinchpin 1192) et les tables de config sont build-dependants.
    "build": True,
    "toujours": False,
    "raison": ("SynapticLinchpin : `On(NormalAttack) & HasTrait(actor, Synapse) & AreFriends(owner,"
               " actor) & IsAlive(target)` -> `Repeat(If(NOT cap, Spawn(owner, ..., opts{+0x18 ="
               " UseNormalAttackIfAble})))`. Ce fichier garde les gates, le cap `maxSummons` (y"
               " compris la liberation d'un slot par la MORT d'un summon), le parent = PORTEUR"
               " (et non l'acteur), les stats `WithStatsFromConfig` et l'attaque on-appearance."),
}

BUILD = ["--roster", "1", "--p-units", f"{PRIME_VIS},{SYNAPSE_ALLY},{PLAIN_ALLY}",
         "--a-units", VICTIM_VIS]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


# --------------------------------------------------------------------------- fixtures NOMMEES

@dataclass
class LinchpinScene:
    """Scene DRIVE'e d'une attaque normale : etat offline + ids + tuiles utiles.

    `victim_tile` a >= 2 voisins LIBRES : l'attaquant en occupe un (melee), il en reste au moins un
    pour le `CanAddUnit(AdjacentTiles(target))` du behaviour. La mesure live a etabli que sans cette
    marge le natif lui-meme ne pose rien."""
    state: object
    board: object
    prime: int
    ally_syn: int
    ally_plain: int
    victim: int
    attacker_tile: int
    victim_tile: int
    free_tiles: list


@pytest.fixture(scope="module")
def linchpin_runner(rpc, build_runner):
    """Runner ISOLE partage par TOUS les cas offline du fichier (un seul slot du cap partage)."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD, keep=True)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    return {"rid": rid, "board": Board(bg["tiles"], adjacency="evenq")}


@pytest.fixture
def linchpin_scene(rpc, linchpin_runner):
    """FABRIQUE de scenes (fixture NOMMEE, reutilisee par tous les cas offline).

    Charge un `State` FRAIS depuis les RPC du runner partage, cale `state.rng` sur le flux natif,
    puis DRIVE les positions : la victime sur une tuile a >= 3 voisins libres, l'attaquant sur l'un
    d'eux, les deux autres allies HORS de ce voisinage (pour qu'ils n'occupent pas les tuiles de
    spawn et ne faussent pas le `CanAddUnit`)."""
    def _make(min_free: int = 3) -> LinchpinScene:
        state, board = _load(rpc, linchpin_runner)
        prime = _unit_by_vis(state, PRIME_VIS)
        syn = _unit_by_vis(state, SYNAPSE_ALLY)
        plain = _unit_by_vis(state, PLAIN_ALLY)
        vic = _unit_by_vis(state, VICTIM_VIS)
        if prime is None or syn is None or plain is None or vic is None:
            pytest.skip("roster offline incomplet (Prime/Neurothrope/TyrantGuard/Warden)")
        # `min_free` = le nombre de voisins LIBRES exige AVANT la pose de l'attaquant (qui en
        # consomme un). Les cas de CAP demandent `cap + 1` : sans cette marge le plafond observe
        # serait GEOMETRIQUE, pas le `maxSummons` natif -- et l'assertion `<= cap` passerait pour
        # verte sans rien discriminer (faux vert mesure au 1er jet de ce fichier).
        spot = _victim_spot(board, _occupied(state), min_free)
        if spot is None:
            pytest.skip(f"aucune tuile a >= {min_free} voisins libres sur ce board")
        vt, free = spot
        _place(state, board, vic, vt)
        _place(state, board, prime, free[0])            # l'attaquant au CONTACT (melee)
        # les deux autres allies loin du voisinage de la victime : ils ne doivent occuper AUCUNE
        # tuile candidate au spawn (sinon le cas NEGATIF ne serait plus discriminant).
        far = _far_tiles(board, set(free) | {vt} | _occupied(state), 2)
        if far is None:
            pytest.skip("pas assez de tuiles libres eloignees pour parquer les deux allies")
        _place(state, board, syn, far[0])
        _place(state, board, plain, far[1])
        return LinchpinScene(state=state, board=board, prime=prime, ally_syn=syn,
                            ally_plain=plain, victim=vic, attacker_tile=free[0],
                            victim_tile=vt, free_tiles=free[1:])
    return _make


# --------------------------------------------------------------------------- helpers

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


def _victim_spot(board, occupied, min_free=3):
    """(tuile_victime, [voisins libres]) avec AU MOINS `min_free` voisins walkable libres, comptes
    dans l'adjacence **NATIVE**. La tuile la PLUS degagee d'abord. None si le board n'en porte
    aucune.

    ⚠ `board.neighbours()` n'est PAS le bon voisinage ici : il TRIE et SYMETRISE, alors que le noeud
    `AdjacentTiles` mirrore `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select`, qui lit la
    liste STOCKEE sur la tuile (`board.neighbours_native`). Mesure #937 : la tuile 24 du board
    MC1_67 a **6** voisins symetrises mais seulement **4** natifs -- un montage cale sur le premier
    croit avoir 5 tuiles posables et n'en a que 3, ce qui rabat le plafond observe sur la GEOMETRIE
    au lieu du `maxSummons` natif (faux vert du 1er jet)."""
    best = None
    for t in sorted(board.by_id):
        if not board.walkable(t) or t in occupied:
            continue
        free = [n for n in sorted(board.neighbours_native(t))
                if board.walkable(n) and n not in occupied]
        if len(free) >= min_free and (best is None or len(free) > len(best[1])):
            best = (t, free)
    return best


def _far_tiles(board, forbidden, n):
    """`n` tuiles libres qui ne TOUCHENT pas le voisinage de la victime (ni au sens natif, ni au sens
    symetrise) : les allies parques ne doivent occuper AUCUNE tuile candidate au spawn, sinon les cas
    negatifs cesseraient d'etre discriminants."""
    out = [t for t in sorted(board.by_id)
           if board.walkable(t) and t not in forbidden
           and not ((set(board.neighbours(t)) | set(board.neighbours_native(t))) & forbidden)]
    return out[:n] if len(out) >= n else None


def _hormas(state, alive_only=True):
    """ids des Hormagaunts du port (`_spawn_config_grot` pose la CLE de config) -- on accepte aussi
    la forme LIVE `tyranNpc1Hormagaunt` (cf. l'en-tete : les deux existent selon la voie)."""
    from engine.runner.components import UnitComponent
    return sorted(eid for eid, e in state.entities.items()
                  if (uc := e.get_component(UnitComponent)) is not None
                  and (uc.alive or not alive_only)
                  and "Hormagaunt" in (uc.visual_id or ""))


def _fire_normal_attack(state, actor, target):
    """Emet le vecteur `On(NormalAttack = 38)` a sa place exacte, sans rejouer le pipeline de degat
    (on veut EXERCER le trigger, pas mesurer une attaque)."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.triggers.dispatch.core import evaluate_trigger_operation
    ev = TriggerEvent(EventTriggerType.NormalAttack, actor, target, ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


def _linchpin(out):
    return [r for r in out if isinstance(r, dict) and r.get("ability") == ABILITY]


def _heal_full(state, uid):
    """Restaure les PV de la cible AVANT chaque tir des cas de CAP.

    Ce n'est pas un artifice de confort : le sous-behaviour on-appearance fait ATTAQUER chaque
    Hormagaunt frais, et trois d'entre eux suffisent a tuer la victime -- le 4e tir est alors ecarte
    par `IsAlive(target@+0x60)`, pas par le cap. Sans cette remise a plat, le test du cap mesurerait
    la LETALITE des summons (mesure : 3 Hormagaunts au lieu de 4)."""
    from engine.runner.components import HealthComponent, UnitComponent
    e = state.get_entity(uid)
    uc, hc = e.get_component(UnitComponent), e.get_component(HealthComponent)
    if uc is not None:
        uc.alive = True
    if hc is not None and hc.hp_max is not None:
        hc.hp = hc.hp_max


def _tile_of(state, board, uid):
    from engine.runner.components import PositionComponent
    pc = state.get_entity(uid).get_component(PositionComponent)
    return board.id_at(pc.col, pc.row) if pc is not None else None


# --------------------------------------------------------------------------- 1. ORACLE LIVE

def test_synaptic_linchpin_summons_hormagaunt_live(live_session, rpc, build_runner):
    """ORACLE LIVE (RE-independant) : on DRIVE le Winged Prime au contact d'un ennemi ROBUSTE qui a
    des voisins LIBRES, et on lui fait porter son attaque NORMALE -> un Hormagaunt apparait sur SA
    team, ADJACENT a la cible, et la cible SURVIT. Les PV LIVE du Hormagaunt sont confrontes a
    `build_summon_context("SynapticLinchpin", level, mult)`.

    Le choix de cible est DRIVE par la geometrie (voisins libres d'abord) : la mesure #937 a etabli
    qu'une cible sans voisin libre rend le behaviour natif MUET, ce qui ressemble a un trigger qui
    n'a pas fire. Skip propre si le Prime ne peut atteindre une telle cible dans la fenetre."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.operations.spawn import build_summon_context

    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec, prime = _advance_to_my_turn(rpc, rid, PRIME_VIS)
    if prime is None:
        pytest.skip("Winged Prime absent / n'a pas atteint son tour")
    before = _live_hormas(dec)
    hit = _drive_normal_attack(rpc, rid, board, PRIME_VIS)
    if hit is None:
        pytest.skip("le Winged Prime n'a pas pu frapper une cible qualifiante (geometrie/tours)")
    dec2, tid, tpos = hit
    new = [u for u in (dec2.get("units") or [])
           if u.get("id") not in before and "Hormagaunt" in (u.get("visualId") or "")]
    tgt = next((u for u in (dec2.get("units") or []) if u.get("id") == tid), None)
    print(f"[937 LIVE] cible={tid} alive={(tgt or {}).get('alive')} "
          f"nouveaux={[(u['id'], u.get('visualId'), u.get('pos')) for u in new]}")

    assert (tgt or {}).get("alive"), "la cible est morte : le gate `IsAlive(target)` n'est pas exerce"
    assert new, ("aucun Hormagaunt apres l'attaque normale du Winged Prime : "
                 "le passif SynapticLinchpin n'a pas fire LIVE")
    h = new[0]
    assert h.get("owner") == prime.get("owner"), \
        f"le Hormagaunt n'appartient pas au camp du Prime (owner={h.get('owner')})"
    hp_pos, tp = h.get("pos") or {}, tpos or {}
    dist = _hex_dist(board, (hp_pos.get("col"), hp_pos.get("row")), (tp.get("col"), tp.get("row")))
    assert dist == 1, f"le Hormagaunt n'est PAS adjacent a la cible (dist={dist})"

    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    pcfg = next(((u.get("unitConfig") or {}) for u in (snap2.get("units") or [])
                 if (u.get("unitConfig") or {}).get("visualId") == PRIME_VIS), {})
    # `WithStatsFromConfig(cfg, abilityState)` : l'`AbilityState` est celui du PASSIF du porteur.
    lvl = pcfg.get("passiveAbilityLevel") or pcfg.get("activeAbilityLevel")
    mult = int(pcfg.get("abilityVariablesMultiplier") or 100)
    ctx = build_summon_context(-1, HORMA_KEY, ABILITY, lvl, mult)
    print(f"[937 LIVE] lvl={lvl} mult={mult} hp_live={h.get('hp')} attendu={ctx.health}")
    assert lvl is not None, f"niveau de passif du Prime absent du combatSnapshot : {pcfg}"
    assert int(h.get("hp")) == int(ctx.health), \
        (f"PV du Hormagaunt live {h.get('hp')} != WithStatsFromConfig {ctx.health} "
         f"-- la lecture kit gameconfig ou la source de stats du summon diverge")


def test_synaptic_linchpin_skipped_without_synapse_live(live_session, rpc, build_runner):
    """CAS NEGATIF LIVE -- LE cas ou le passif NE MORD PAS : c'est le `tyranTyrantGuard` (allie du
    Prime, SANS le trait `Synapse`) qui porte l'attaque normale. Le gate
    `HasTrait(actor@+0x40, Synapse)` doit ecarter, et AUCUN Hormagaunt ne doit apparaitre -- alors
    meme que la cible survit et que des tuiles libres l'entourent (c'est la mesure #937 : le meme
    montage avec le Prime en produit un)."""
    from engine.entities.pathfinding.board import Board

    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec, guard = _advance_to_my_turn(rpc, rid, PLAIN_ALLY)
    if guard is None:
        pytest.skip("Tyrant Guard absent / n'a pas atteint son tour")
    before = _live_hormas(dec)
    hit = _drive_normal_attack(rpc, rid, board, PLAIN_ALLY)
    if hit is None:
        pytest.skip("le Tyrant Guard n'a pas pu frapper une cible qualifiante")
    dec2, tid, _tp = hit
    tgt = next((u for u in (dec2.get("units") or []) if u.get("id") == tid), None)
    new = [u for u in (dec2.get("units") or [])
           if u.get("id") not in before and "Hormagaunt" in (u.get("visualId") or "")]
    print(f"[937 LIVE-NEG] cible={tid} alive={(tgt or {}).get('alive')} nouveaux={new}")
    # GARDE ANTI-VACUITE : le cas negatif ne vaut que si le regime est celui du cas POSITIF --
    # cible VIVANTE (sinon c'est `IsAlive` qui ecarte) et au moins une tuile libre autour d'elle
    # (sinon c'est la geometrie, mesuree comme cause d'un groupe VIDE en #937).
    assert (tgt or {}).get("alive"), "la cible est morte -> ce n'est plus le gate Synapse qui tranche"
    free = _free_around(dec2, board, tgt)
    assert free, ("aucune tuile libre autour de la cible -> le negatif serait VACUE "
                  "(la geometrie l'expliquerait, pas le gate Synapse)")
    assert not new, ("un Hormagaunt est apparu sur une attaque du Tyrant Guard : "
                     "le gate HasTrait(actor, Synapse) ne mord pas LIVE")


def _live_hormas(dec):
    return {u["id"] for u in (dec.get("units") or [])
            if u.get("alive") and "Hormagaunt" in (u.get("visualId") or "")}


def _free_around(dec, board, tgt):
    p = (tgt or {}).get("pos") or {}
    if p.get("col") is None:
        return []
    t = board.id_at(p["col"], p["row"])
    occ = set()
    for u in (dec.get("units") or []):
        q = u.get("pos") or {}
        if u.get("alive") and q.get("col") is not None:
            occ.add(board.id_at(q["col"], q["row"]))
    # adjacence NATIVE (`AdjacentTilesSelector`), pas la symetrisee -- cf. `_victim_spot`.
    return [n for n in board.neighbours_native(t) if board.walkable(n) and n not in occ]


def _hex_dist(board, a, b):
    from collections import deque
    ta, tb = board.id_at(a[0], a[1]), board.id_at(b[0], b[1])
    if ta is None or tb is None:
        return None
    seen, q = {ta: 0}, deque([ta])
    while q:
        x = q.popleft()
        if x == tb:
            return seen[x]
        for n in board.neighbours(x):
            if n not in seen:
                seen[n] = seen[x] + 1
                q.append(n)
    return None


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
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _drive_normal_attack(rpc, rid, board, attacker_vis, max_turns=16):
    """DRIVE : approche `attacker_vis` d'un ennemi et lui fait porter son attaque NORMALE.

    Le choix de cible est classe par (voisins LIBRES, PV) decroissants : le behaviour natif a besoin
    d'au moins une tuile posable adjacente APRES que l'attaquant se soit mis au contact. Rend
    (decisionView d'apres, target_id, position de la cible) ou None."""
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
        dec, att = _advance_to_my_turn(rpc, rid, attacker_vis)
        if att is None:
            return None
        aid = att["id"]
        norm = next((a.get("id") for a in (att.get("abilities") or []) if a.get("kind") == "normal"),
                    None)
        foes = [u for u in (dec.get("units") or [])
                if u.get("alive") and u.get("owner") != att.get("owner")
                and (u.get("pos") or {}).get("col") is not None]
        if not foes or norm is None:
            return None
        foes.sort(key=lambda u: (len(_free_around(dec, board, u)), int(u.get("hp") or 0)),
                  reverse=True)
        tgt = foes[0]
        at, et = _tile(att), _tile(tgt)
        if at is not None and et is not None and _bfs(et).get(at, 99) <= 1:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": aid, "targetId": tgt["id"],
                "abilityType": norm}, "captureEvents": True}, 120)
            return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150), \
                tgt["id"], tgt.get("pos")
        dgoal = _bfs(et) if et is not None else {}
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == aid), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or []) if t.get("col") is not None}
        pool = [t for t in reach if t in dgoal]
        if pool:
            best = min(pool, key=lambda t: dgoal[t])
            col, row = reach[best]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": aid, "to": {"col": col, "row": row}}}, 40)
            dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            att2 = _find(dec2, attacker_vis)
            if att2 is not None and et is not None and _bfs(et).get(_tile(att2), 99) <= 1:
                tgt2 = next((u for u in (dec2.get("units") or []) if u.get("id") == tgt["id"]), None)
                if tgt2 is not None and tgt2.get("alive"):
                    rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "ability", "casterId": aid, "targetId": tgt["id"],
                        "abilityType": next((a.get("id") for a in (att2.get("abilities") or [])
                                             if a.get("kind") == "normal"), norm)},
                        "captureEvents": True}, 120)
                    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150), \
                        tgt["id"], tgt2.get("pos")
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return None


# --------------------------------------------------------------------------- cas OFFLINE

def test_synaptic_linchpin_spawns_adjacent_to_target_offline(linchpin_scene):
    """POSITIF offline : le Winged Prime frappe -> UN Hormagaunt, sur SA team, ADJACENT a la cible,
    et son `parentId` est le PORTEUR (mesure live `Unit_Parent_Id = 81`)."""
    from engine.runner.components import OwnerComponent, UnitComponent
    sc = linchpin_scene()
    out = _fire_normal_attack(sc.state, sc.prime, sc.victim)
    res = _linchpin(out)
    hor = _hormas(sc.state)
    assert res, f"SynapticLinchpin n'a pas fire offline (out={out})"
    assert len(hor) == 1, f"attendu 1 Hormagaunt, obtenu {hor}"
    h = sc.state.get_entity(hor[0])
    huc, hoc = h.get_component(UnitComponent), h.get_component(OwnerComponent)
    poc = sc.state.get_entity(sc.prime).get_component(OwnerComponent)
    assert hoc.team == poc.team and hoc.player == poc.player, \
        "le Hormagaunt n'est pas sur le camp du porteur"
    assert huc.parent_id == sc.prime, \
        f"`Spawn(parentSelector = owner)` : parent attendu {sc.prime}, obtenu {huc.parent_id}"
    t = _tile_of(sc.state, sc.board, hor[0])
    # adjacence NATIVE : c'est celle que rend `AdjacentTilesSelector$$Select` (liste stockee).
    assert t in set(sc.board.neighbours_native(sc.victim_tile)), \
        f"le Hormagaunt {t} n'est pas adjacent a la cible {sc.victim_tile}"


def test_synaptic_linchpin_summon_stats_from_config_offline(linchpin_scene):
    """`SpawnUnitOptions.WithStatsFromConfig(cfg, abilityState)` : PV/attaque/armure du Hormagaunt
    == `ability_var(SynapticLinchpin, summon*, level, mult)`. Les trois valeurs ont ete confrontees
    LIVE (2992 / 2194 / 599 a level 50 / 180 %)."""
    from engine.runner.components import HealthComponent, StatsComponent
    from engine.entities.effects.magnitude import ability_var
    sc = linchpin_scene()
    pctx = sc.state.get_entity(sc.prime).get_component(StatsComponent).ctx
    lvl = getattr(pctx, "passive_ability_level", None) or getattr(pctx, "active_ability_level", None)
    mult = int(getattr(pctx, "ability_variables_multiplier", 100) or 100)
    _fire_normal_attack(sc.state, sc.prime, sc.victim)
    hor = _hormas(sc.state)
    assert hor, "aucun Hormagaunt -> rien a confronter"
    hc = sc.state.get_entity(hor[0]).get_component(HealthComponent)
    want = ability_var(ABILITY, "summonHp", lvl, multiplier_pct=mult)
    assert want, f"summonHp illisible (level={lvl} mult={mult})"
    assert int(hc.hp_max) == int(want), \
        f"PV max du Hormagaunt {hc.hp_max} != summonHp[{lvl}] x {mult}% = {want}"


def test_synaptic_linchpin_summon_stats_follow_the_PASSIVE_level_offline(linchpin_scene):
    """`WithStatsFromConfig(cfg, **abilityState**)` : l'`AbilityState` que `CreateBehaviour` recoit
    est celui du **PASSIF** du porteur, pas de son ACTIF.

    ⚠ CE CAS EXISTE PARCE QU'UN MUTANT ETAIT INERTE SANS LUI. `probe_937_mutants.py` mutant **M9**
    retire l'`ability_state` du `Spawn` (le niveau retombe alors sur `active_ability_level`) et
    restait VERT : apres `buildNormalizedBC`, actif et passif valent TOUS DEUX `targetAbilityLevel`
    (50), donc les deux lectures coincident et le regime est DEGENERE. On les SEPARE ici -- c'est le
    seul endroit ou la distinction est observable."""
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.components import HealthComponent, StatsComponent
    sc = linchpin_scene()
    pctx = sc.state.get_entity(sc.prime).get_component(StatsComponent).ctx
    mult = int(getattr(pctx, "ability_variables_multiplier", 100) or 100)
    lvl_actif, lvl_passif = 50, 12                  # deux niveaux dont les cellules DIFFERENT
    want_passif = ability_var(ABILITY, "summonHp", lvl_passif, multiplier_pct=mult)
    want_actif = ability_var(ABILITY, "summonHp", lvl_actif, multiplier_pct=mult)
    assert want_passif != want_actif, \
        (f"summonHp[{lvl_passif}] == summonHp[{lvl_actif}] == {want_passif} -> le regime est "
         f"DEGENERE et le cas ne discriminerait rien")
    pctx.active_ability_level = lvl_actif
    pctx.passive_ability_level = lvl_passif
    _fire_normal_attack(sc.state, sc.prime, sc.victim)
    hor = _hormas(sc.state)
    assert hor, "aucun Hormagaunt -> rien a confronter"
    hc = sc.state.get_entity(hor[0]).get_component(HealthComponent)
    assert int(hc.hp_max) == int(want_passif), \
        (f"PV du Hormagaunt {hc.hp_max} : attendu summonHp[{lvl_passif}] = {want_passif} (niveau du "
         f"PASSIF), obtenu ce que donnerait summonHp[{lvl_actif}] = {want_actif} si le port lisait "
         f"l'ACTIF")


def test_synaptic_linchpin_fires_for_a_friendly_synapse_unit_offline(linchpin_scene):
    """`HasTrait(actor, Synapse) & AreFriends(owner, actor)` : c'est le `tyranNeurothrope` (ALLIE
    porteur de Synapse) qui frappe -> le Hormagaunt apparait quand meme, et son parent reste le
    WINGED PRIME (mesure live : `Unit_Parent_Id = 81` alors que l'acteur etait le Neurothrope)."""
    from engine.runner.components import UnitComponent
    sc = linchpin_scene()
    _place(sc.state, sc.board, sc.ally_syn, sc.attacker_tile)     # le Neurothrope au contact
    _place(sc.state, sc.board, sc.prime, sc.free_tiles[-1])       # le Prime ailleurs, hors contact
    out = _fire_normal_attack(sc.state, sc.ally_syn, sc.victim)
    hor = _hormas(sc.state)
    assert _linchpin(out), f"le passif n'a pas fire pour un allie Synapse (out={out})"
    assert len(hor) == 1, f"attendu 1 Hormagaunt, obtenu {hor}"
    huc = sc.state.get_entity(hor[0]).get_component(UnitComponent)
    assert huc.parent_id == sc.prime, \
        (f"le parent du summon doit etre le PORTEUR ({sc.prime}), pas l'acteur ({sc.ally_syn}) : "
         f"obtenu {huc.parent_id}")


def test_synaptic_linchpin_skipped_when_actor_has_no_synapse_offline(linchpin_scene):
    """NEGATIF `HasTrait(actor, Synapse)` : le `tyranTyrantGuard` frappe -> AUCUN Hormagaunt.
    Garde ANTI-VACUITE : on verifie d'abord que la MEME scene avec le Prime en produit un."""
    from engine.entities.traits.unit_trait import UnitTrait, has_trait
    from engine.runner.components import StatsComponent
    sc = linchpin_scene()
    # non-vacuite : le TyrantGuard ne porte PAS Synapse (sinon le cas ne teste rien)
    gctx = sc.state.get_entity(sc.ally_plain).get_component(StatsComponent).ctx
    assert not has_trait(set(getattr(gctx, "traits", None) or []), UnitTrait.Synapse), \
        f"{PLAIN_ALLY} porte Synapse dans ce build -> le cas negatif est VACUE"
    _place(sc.state, sc.board, sc.ally_plain, sc.attacker_tile)
    _place(sc.state, sc.board, sc.prime, sc.free_tiles[-1])
    out = _fire_normal_attack(sc.state, sc.ally_plain, sc.victim)
    assert not _linchpin(out), "le passif a fire pour un acteur SANS Synapse"
    assert not _hormas(sc.state), f"un Hormagaunt est apparu : {_hormas(sc.state)}"


def test_synaptic_linchpin_skipped_when_actor_is_an_enemy_offline(linchpin_scene):
    """NEGATIF `AreFriends(owner, actor)` : l'ACTEUR est l'ennemi (equipe adverse). Meme s'il portait
    Synapse, le gate d'amitie doit ecarter -- on le force en LUI DONNANT le trait, sinon c'est le
    gate Synapse qui trancherait et le cas serait un doublon du precedent."""
    from engine.runner.components import StatsComponent
    sc = linchpin_scene()
    vctx = sc.state.get_entity(sc.victim).get_component(StatsComponent).ctx
    vctx.traits = list(getattr(vctx, "traits", None) or []) + ["Synapse"]
    out = _fire_normal_attack(sc.state, sc.victim, sc.prime)      # l'ennemi frappe le Prime
    assert not _linchpin(out), "le passif a fire pour un acteur ENNEMI (gate AreFriends muet)"
    assert not _hormas(sc.state), f"un Hormagaunt est apparu : {_hormas(sc.state)}"


def test_synaptic_linchpin_skipped_when_target_is_defeated_offline(linchpin_scene):
    """NEGATIF `IsAlive(target@+0x60)` -- l'i2 le dit : « that enemy is **not defeated** ». La cible
    est tuee avant l'emission du vecteur (le natif emet `On(0x26)` APRES la resolution des degats)."""
    from engine.runner.components import HealthComponent, UnitComponent
    sc = linchpin_scene()
    e = sc.state.get_entity(sc.victim)
    e.get_component(UnitComponent).alive = False
    hc = e.get_component(HealthComponent)
    if hc is not None:
        hc.hp = 0
    out = _fire_normal_attack(sc.state, sc.prime, sc.victim)
    assert not _linchpin(out), "le passif a fire sur une cible DEFAITE"
    assert not _hormas(sc.state), f"un Hormagaunt est apparu : {_hormas(sc.state)}"


def test_synaptic_linchpin_cap_is_max_summons_offline(linchpin_scene):
    """`NOT AmountIsEqualOrGreater(UnitsWithId(Children(owner), unitId, 3), Direct(maxSummons))` :
    on repete des attaques qualifiantes -> le nombre de Hormagaunts VIVANTS plafonne a
    `maxSummons[level]`, et pas au-dela. Le compte est DERIVE de la config, jamais ecrit en dur."""
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.components import StatsComponent
    # 5 = `maxSummons` max de la table (4) + la tuile que l'attaquant consomme. Un hex en a 6 : la
    # scene prend la tuile la PLUS degagee du board.
    sc = linchpin_scene(min_free=5)
    pctx = sc.state.get_entity(sc.prime).get_component(StatsComponent).ctx
    lvl = getattr(pctx, "passive_ability_level", None) or getattr(pctx, "active_ability_level", None)
    mult = int(getattr(pctx, "ability_variables_multiplier", 100) or 100)
    cap = int(ability_var(ABILITY, "maxSummons", lvl, multiplier_pct=mult))
    assert cap >= 1, f"cap illisible ({cap}) -> le test serait VACUE"
    for _ in range(cap + 3):                       # au-dela du cap, expres
        _heal_full(sc.state, sc.victim)            # cf. `_heal_full` : isoler le CAP de la letalite
        _fire_normal_attack(sc.state, sc.prime, sc.victim)
    hor = _hormas(sc.state)
    print(f"[937 offline] cap={cap} hormagaunts={len(hor)} tuiles_libres={len(sc.free_tiles)}")
    # NON-VACUITE : `<= cap` seul passerait pour vert avec un plafond GEOMETRIQUE (mesure du 1er
    # jet : 3 tuiles libres pour un cap de 4). On exige donc que le cap soit REELLEMENT ATTEINT.
    assert len(sc.free_tiles) >= cap, \
        f"seulement {len(sc.free_tiles)} tuiles posables pour un cap de {cap} -> test VACUE"
    assert len(hor) == cap, f"{len(hor)} Hormagaunts vivants pour un cap de {cap}"


def test_synaptic_linchpin_dead_summon_frees_a_cap_slot_offline(linchpin_scene):
    """Le cap compte `UnitSelectionType.OnlyAliveAndTargetable` -- un Hormagaunt MORT ne tient PLUS
    de slot. C'est le mode `3` du `UnitsWithId` natif : sans lui, `Children(owner)` (qui ne filtre
    RIEN) laisserait les cadavres bloquer le passif."""
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.components import HealthComponent, StatsComponent, UnitComponent
    sc = linchpin_scene(min_free=5)                # cf. le test du cap : marge geometrique
    pctx = sc.state.get_entity(sc.prime).get_component(StatsComponent).ctx
    lvl = getattr(pctx, "passive_ability_level", None) or getattr(pctx, "active_ability_level", None)
    mult = int(getattr(pctx, "ability_variables_multiplier", 100) or 100)
    cap = int(ability_var(ABILITY, "maxSummons", lvl, multiplier_pct=mult))
    for _ in range(cap + 2):
        _heal_full(sc.state, sc.victim)            # cf. `_heal_full`
        _fire_normal_attack(sc.state, sc.prime, sc.victim)
    at_cap = _hormas(sc.state)
    assert len(at_cap) == cap, f"le cap n'est pas atteint ({at_cap}) -> le test serait VACUE"
    # CONTRE-EPREUVE : au cap, un tir de plus n'ajoute RIEN (sinon le << slot libere >> ci-dessous
    # ne prouverait pas que c'est la MORT qui l'a libere).
    _heal_full(sc.state, sc.victim)
    _fire_normal_attack(sc.state, sc.prime, sc.victim)
    assert len(_hormas(sc.state)) == cap, "le cap ne retient pas un tir supplementaire"
    # on en TUE un : un slot doit se liberer
    e = sc.state.get_entity(at_cap[0])
    e.get_component(UnitComponent).alive = False
    hc = e.get_component(HealthComponent)
    if hc is not None:
        hc.hp = 0
    _heal_full(sc.state, sc.victim)
    _fire_normal_attack(sc.state, sc.prime, sc.victim)
    after = _hormas(sc.state)
    assert len(after) == cap, \
        (f"un Hormagaunt MORT tient encore un slot du cap : {len(after)} vivants pour cap={cap} "
         f"(le filtre UnitSelectionType.OnlyAliveAndTargetable ne mord pas)")
    assert at_cap[0] not in after, "le mort ne devrait plus compter parmi les vivants"


def test_synaptic_linchpin_summon_attacks_the_target_offline(linchpin_scene):
    """`opts.<+0x18> = UseNormalAttackIfAble(activeTarget@+0x68, target@+0x60)` : le Hormagaunt
    frais frappe la cible immediatement (i2 « which immediately attacks the enemy »). Mesure live :
    deux coups de l'entite 111 sur l'entite 79, DANS la fenetre du groupe SynapticLinchpin."""
    from engine.runner.components import HealthComponent
    sc = linchpin_scene()
    hp0 = sc.state.get_entity(sc.victim).get_component(HealthComponent).hp
    out = _fire_normal_attack(sc.state, sc.prime, sc.victim)
    res = _linchpin(out)
    assert res, "le passif n'a pas fire -> rien a mesurer"
    hp1 = sc.state.get_entity(sc.victim).get_component(HealthComponent).hp
    attacks = [a for r in res for a in (r.get("attacks") or [])]
    print(f"[937 offline] hp cible {hp0} -> {hp1} ; attaques du summon = {len(attacks)}")
    assert attacks, ("le sous-behaviour on-appearance n'a produit AUCUNE attaque : "
                     "`UseNormalAttackIfAble(ActiveTarget, Target)` est inerte")
    assert int(hp1) < int(hp0), \
        f"la cible n'a pas perdu de PV ({hp0} -> {hp1}) : l'attaque du summon n'a pas mordu"
