"""#550 -- `1121 ItItches` (`tyranParasite`, Parasite of Mortrex) : la face COMBAT, etage par etage.

Artefact natif : `IdunBattleLogic.Entities.Abilities.Active.Loki.ItItchesAbility$$ExecuteBehaviour`
(DECOMPILE, mirror 1:1 -- l'arbre vit dans `engine/runner/abilities/tyranids.py::it_itches_tree`).
L'ability etait un NO-OP SILENCIEUX avant cette tranche (absente d'`ABILITY_CLASSES`, donc ignoree
par `AbilityHandler.visit_ActiveAbilityMessage` -- 0 degat, 0 effet, aucune erreur), alors que sa
face DECISION (`playbook/noncomparable/it_itches.py`) etait deja portee et pouvait la choisir.

⚠ LA FICHE D'AUDIT DISAIT « SUMMON », ET LE BEHAVIOUR EST UN COMPOSITE DE CINQ MECANIQUES. La
colonne de `docs/rl/combat-ability-coverage.md` derive du `damageProfile` de l'ARME du porteur, pas
du behaviour ; pour une ability NON PORTEE, l'`ExecuteBehaviour` n'est connu de personne. Ce fichier
garde donc les CINQ, separement -- un critere unique (« le cast passe ») serait vert sur un port qui
n'en porterait qu'une.

CE QUE CHAQUE TEST TIENT, ET LA MUTATION QUI LE REND ROUGE :

  * `test_it_itches_push_is_vector_not_radial` -- LE test discriminant. Les trois cibles reculent
    d'un hex dans la MEME direction (`VectorFromAdjacentTo(CasterTile, Tiles(Target), 1)`), pas
    chacune a l'oppose du caster. Sur la configuration craftee, un `FindTileToPush` (direction 0)
    enverrait les deux cibles LATERALES ailleurs -- c'est ce que ce test refuse. Mutation vue rouge :
    `vector_dir=None` passe a `DisplaceUnitOperation` (les laterales ne bougent plus).
  * `test_it_itches_pins_every_target`      -- `AddEffect(0x429 = Pinned)` sur les TROIS.
  * `test_it_itches_spawns_on_vacated_tiles`-- un `tyranSmnRipperSwarm` par hex LIBERE, aux MEMES
    positions que le natif. ⚠ Les summons se comptent par squadId NEUF, jamais par `visualId` : la
    resolution DOWNSTREAM (`SpawnUnitBehaviour`, HORS `ExecuteBehaviour`) substitue la variante NPC
    concrete `tyranNpc2RipperSwarm` au constant config -- meme ecart, deja documente, que
    `AlphaWarrior`/`tyranNpc4Warrior`.
  * `test_it_itches_resets_casters_movement` -- `ResetMovement(Owner)` : « The Parasite of Mortrex
    may move again after activating this ability. »
  * `test_it_itches_onappearance_damage_bit_exact` -- le cran QUANTITATIF, et celui qui TRANCHE
    l'unique hypothese du port : la lambda `getAbilityType` du `PerformAIAbility` est DEDUPLIQUEE
    dans le binaire (absente des DEUX tables de symboles du build `rnca9r7q6c`), donc illisible
    statiquement. Le port suppose `IdunBattle.Entities.UnitExtensions$$GetNormalAttackType`. Si elle
    rendait `1023 Burrowers` (la seule ACTIVE du Ripper Swarm), les summons QUITTERAIENT le plateau a
    l'apparition et n'infligeraient rien. Le test exige les deux : summons SUR le plateau, et TOTAL
    de degat par cible egal au natif.

MESURE (2026-08-08, board MC1_67, seed 777) : natif et port coincident sur les cinq etages ; degat
on-appearance `{u81: 50, u83: 218}` des deux cotes. Detail et sortie brute : `probe_550_it_itches.py`.

ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.components import PositionComponent, UnitComponent
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state

AGENT_ID = "ad03765eb404ead1a"
PYDIR = Path(__file__).resolve().parents[3]                        # scripts/python
ROOT = Path(__file__).resolve().parents[5]                         # racine repo
# `data/` = ce qu'on LIT (VERSIONNE), `logs/` = ce qu'on ECRIT (gitignore) -- cf. CLAUDE.md.
STATE = ROOT / "logs" / f"_pytest_ititches_{AGENT_ID}.json"        # state-file UNIQUE

IT_ITCHES = int(ActiveAbilityType.ItItches)                        # 1121
PINNED = int(EffectType.Pinned)                                    # 0x429 = 1065
CARRIER = "tyranParasite"
ENEMIES = "orksNob,orksRuntherd,orksBigMek"
SEED = "777"
BOARD = "MC1_67"

# Configuration CRAFTEE : P adjacent a T, et les DEUX autres ennemis sur les deux seules tuiles
# adjacentes A LA FOIS a P et a T -- le maximum que `...ItItchesAbility$$GetTargetUnits` peut rendre.
# Les positions ne sont PAS laissees au spawn : sans `--place`, le Parasite demarre a 8 hex de la
# melee et `ItItches` est un no-op certain (mesure : `-> no-op certain` dans la vue decision).
P_POS = (3, 5)
T_POS = (3, 6)
E1_POS = (2, 5)
E2_POS = (4, 5)
# Destinations ATTENDUES = un pas dans la direction `P -> T` pour LES TROIS (calculees par
# `_dir_index`/`_step`, le foyer porte de `IBattleQuery` slot 113 `GetVector`).
EXPECTED_PUSH = {T_POS: (3, 7), E1_POS: (2, 6), E2_POS: (4, 6)}


@pytest.fixture(scope="module")
def itches(host, live_session):
    """Runner ISOLE frais avec les QUATRE unites placees a la main, dispose au teardown."""
    created: list[int] = []

    def _rpc(m, b, t=90):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    def _build():
        STATE.parent.mkdir(parents=True, exist_ok=True)
        if STATE.exists():
            STATE.unlink()
        proc = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
             "--p-units", CARRIER, "--a-units", ENEMIES,
             "--place", "%s:%d,%d" % (CARRIER, P_POS[0], P_POS[1]),
             "--a-place", "orksNob:%d,%d" % T_POS,
             "--a-place", "orksRuntherd:%d,%d" % E1_POS,
             "--a-place", "orksBigMek:%d,%d" % E2_POS,
             "--state-file", str(STATE)],
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not STATE.exists():
            pytest.skip(f"build {CARRIER} KO: {(proc.stderr or proc.stdout or '')[-300:]}")
        rid = json.loads(STATE.read_text())["runnerId"]
        created.append(rid)
        return rid

    yield _build, _rpc
    for rid in created:
        try:
            host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:
            pass


def _units(rpc, rid) -> list:
    ob = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    return list(ob.get("units") or [])


def _load(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dec, ob, snap, board=board)
    if isinstance(s0, dict) and s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        state.rng = rng
    return state, board


def _caster(units):
    return next((u for u in units if u.get("visualId") == CARRIER and not u.get("isDead")), None)


def _cast(rpc, rid, board, cid):
    """Applique le cast NATIF sur la tuile `T_POS`. Rend (units_avant, units_apres, tile_id)."""
    before = _units(rpc, rid)
    tid = board.id_at(*T_POS)
    info = board.by_id[tid]
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "abilityType": IT_ITCHES,
        "to": {"col": info["col"], "row": info["row"]}}}, 90) or {}
    act = (res.get("actions") or [{}])[0]
    if act.get("error"):
        pytest.skip(f"cast natif bloque: {act.get('error')}")
    return before, _units(rpc, rid), tid


def _port_run(rpc, rid, cid, board):
    """Execute l'arbre PORTE sur l'etat AVANT (charge du meme runner) -> (dict de retour, positions)."""
    state, _b = _load(rpc, rid)
    cls = ABILITY_CLASSES.get(ActiveAbilityType.ItItches)
    assert cls is not None, "1121 ItItches absente d'ABILITY_CLASSES"
    out = cls().execute_behaviour(state, cid, board.id_at(*T_POS)) or {}
    pos = {}
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if uc is None:
            continue
        pos[eid] = (uc.visual_id, None if pc is None else (pc.col, pc.row), bool(uc.alive))
    return out, pos


# ------------------------------------------------------------------ E1/E3 : ciblage + poussee

def test_it_itches_push_is_vector_not_radial(itches):
    """LE test discriminant : les TROIS cibles reculent d'un hex dans la MEME direction.

    `DisplaceUnitInAdjacentDirection` = `DisplaceUnitOperation` **direction 3** (`AdjacentVector`),
    dont la destination vient d'un VECTEUR fourni en options -- pas de la geometrie pousseur/poussee.
    Sur cette configuration, `FindTileToPush` (direction 0) enverrait `orksRuntherd` (2,5) et
    `orksBigMek` (4,5) sur d'AUTRES tuiles, puisque leur direction propre depuis le caster (3,5)
    n'est pas celle de la cible principale. Les deux geometries ne coincident QUE sur la cible
    principale -- d'ou l'insistance sur les LATERALES."""
    build, rpc = itches
    rid = build()
    units = _units(rpc, rid)
    caster = _caster(units)
    if caster is None:
        pytest.skip("caster absent")
    cid = caster["squadId"]
    _state, board = _load(rpc, rid)
    port_out, port_pos = _port_run(rpc, rid, cid, board)
    before, after, _tid = _cast(rpc, rid, board, cid)

    src = {(u.get("col"), u.get("row")): u.get("squadId") for u in before}
    dst = {u.get("squadId"): (u.get("col"), u.get("row")) for u in after}
    print(f"\n[550/push] direction port={port_out.get('direction')} "
          f"natif={[(k, dst.get(v)) for k, v in sorted(src.items())]}")
    for start, expected in EXPECTED_PUSH.items():
        uid = src.get(start)
        assert uid is not None, f"aucune unite en {start} avant le cast"
        assert dst.get(uid) == expected, \
            (f"u{uid} depuis {start} : natif -> {dst.get(uid)}, attendu {expected} "
             f"(un pas dans la direction UNIQUE caster->cible, pas a l'oppose du caster)")
        # ... et le PORT doit rendre la meme chose (c'est le confront, pas un second oracle).
        assert port_pos.get(uid, (None, None, None))[1] == expected, \
            f"u{uid} : le PORT rend {port_pos.get(uid)}, natif {expected}"
    # Le caster, lui, N'A PAS bouge (aucun noeud ne le deplace).
    assert dst.get(cid) == P_POS, f"le caster a bouge : {dst.get(cid)} != {P_POS}"


# ------------------------------------------------------------------ E2 : Pinned

def test_it_itches_pins_every_target(itches):
    """`AddEffect(0x429 = Pinned)` sur les TROIS cibles -- « Suppresses » du tooltip.

    L'effet se lit par `decisionView.units[].effects` : `observeBattle` ne publie PAS les effets, et
    y chercher a rendu un ensemble VIDE au premier passage du probe (faux negatif de CANAL, pas de
    comportement)."""
    build, rpc = itches
    rid = build()
    units = _units(rpc, rid)
    caster = _caster(units)
    if caster is None:
        pytest.skip("caster absent")
    cid = caster["squadId"]
    _state, board = _load(rpc, rid)
    port_out, _pp = _port_run(rpc, rid, cid, board)
    before, _after, _tid = _cast(rpc, rid, board, cid)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}
    pinned_native = sorted(u.get("id") for u in (dv.get("units") or [])
                           if any(int((e or {}).get("effectType") or 0) == PINNED
                                  for e in (u.get("effects") or [])))
    enemies = sorted(u.get("squadId") for u in before
                     if u.get("visualId") != CARRIER and not u.get("isDead"))
    print(f"\n[550/pin] natif={pinned_native} port={sorted(port_out.get('pinned') or [])} "
          f"ennemis={enemies}")
    assert pinned_native == enemies, \
        f"Pinned natif {pinned_native} != les 3 cibles {enemies}"
    assert sorted(port_out.get("pinned") or []) == pinned_native, \
        f"Pinned port {sorted(port_out.get('pinned') or [])} != natif {pinned_native}"


# ------------------------------------------------------------------ E4 : summons

def test_it_itches_spawns_on_vacated_tiles(itches):
    """Un summon par hex LIBERE, aux MEMES tuiles que le natif.

    ⚠ Comptes par squadId NEUF : le natif substitue `tyranNpc2RipperSwarm` au constant config
    `tyranSmnRipperSwarm` que le port mirrore (resolution DOWNSTREAM, hors `ExecuteBehaviour` --
    meme ecart que `AlphaWarrior`/`tyranNpc4Warrior`). Filtrer par `visualId` rendrait 0, ce qui est
    exactement ce que le probe a mesure a son premier passage."""
    build, rpc = itches
    rid = build()
    units = _units(rpc, rid)
    caster = _caster(units)
    if caster is None:
        pytest.skip("caster absent")
    cid = caster["squadId"]
    _state, board = _load(rpc, rid)
    port_out, _pp = _port_run(rpc, rid, cid, board)
    before, after, _tid = _cast(rpc, rid, board, cid)

    known = {u.get("squadId") for u in before}
    fresh = [u for u in after if u.get("squadId") not in known and not u.get("isDead")]
    nat_tiles = sorted((u.get("col"), u.get("row")) for u in fresh)
    port_tiles = sorted((board.by_id[p["tile"]]["col"], board.by_id[p["tile"]]["row"])
                        for p in (port_out.get("spawned") or []) if p.get("tile") in board.by_id)
    print(f"\n[550/spawn] natif={nat_tiles} ({[u.get('visualId') for u in fresh]}) port={port_tiles}")
    assert nat_tiles == sorted([T_POS, E1_POS, E2_POS]), \
        f"le natif spawne sur {nat_tiles}, attendu les 3 hex liberes {sorted([T_POS, E1_POS, E2_POS])}"
    assert port_tiles == nat_tiles, f"le port spawne sur {port_tiles}, natif {nat_tiles}"


# ------------------------------------------------------------------ E5 : ResetMovement

def test_it_itches_resets_casters_movement(itches):
    """« The Parasite of Mortrex may move again after activating this ability. » =
    `ResetMovement(Owner@0x30)` -- le caster reste ACTIVABLE apres le cast."""
    build, rpc = itches
    rid = build()
    units = _units(rpc, rid)
    caster = _caster(units)
    if caster is None:
        pytest.skip("caster absent")
    cid = caster["squadId"]
    _state, board = _load(rpc, rid)
    port_out, _pp = _port_run(rpc, rid, cid, board)
    _before, _after, _tid = _cast(rpc, rid, board, cid)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}
    to_activate = list(dv.get("toActivate") or [])
    print(f"\n[550/reset] toActivate={to_activate} caster={cid} port={port_out.get('movement_reset')}")
    assert cid in to_activate, \
        f"le caster u{cid} n'est plus activable apres le cast : ResetMovement(Owner) non joue"
    assert cid in (port_out.get("movement_reset") or []), \
        f"le PORT ne rouvre pas le tour du caster : {port_out.get('movement_reset')}"


# ------------------------------------------------------------------ E6 : on-appearance (l'hypothese)

def test_it_itches_onappearance_damage_bit_exact(itches):
    """TRANCHE l'unique hypothese du port : `getAbilityType` = `GetNormalAttackType`.

    La lambda native (`...ItItchesAbility.<>c.<ExecuteBehaviour>b__2_0`) est DEDUPLIQUEE -- absente
    des deux tables de symboles du build `rnca9r7q6c` -- donc son corps n'est pas lisible
    statiquement. Deux observables la tranchent :
      1. si elle rendait `1023 Burrowers` (la seule ACTIVE du Ripper Swarm), les summons QUITTERAIENT
         le plateau a l'apparition (`RemoveUnitFromItsTiles(Caster, true)` -> col/row nuls) ;
      2. le TOTAL de degat par CIBLE doit coincider bit-a-bit avec ce que le port calcule -- un
         critere « des degats ont eu lieu » serait satisfait par n'importe quel pipeline."""
    build, rpc = itches
    rid = build()
    units = _units(rpc, rid)
    caster = _caster(units)
    if caster is None:
        pytest.skip("caster absent")
    cid = caster["squadId"]
    _state, board = _load(rpc, rid)
    port_out, _pp = _port_run(rpc, rid, cid, board)
    before, after, _tid = _cast(rpc, rid, board, cid)

    known = {u.get("squadId") for u in before}
    fresh = [u for u in after if u.get("squadId") not in known and not u.get("isDead")]
    off_board = [u for u in fresh if u.get("col") is None]
    hp0 = {u.get("squadId"): u.get("hp") for u in before}
    nat_dmg = {u.get("squadId"): hp0[u["squadId"]] - u.get("hp")
               for u in after
               if u.get("squadId") in hp0 and u.get("hp") != hp0[u.get("squadId")]}
    port_dmg: dict = {}
    for at in (port_out.get("attacks") or []):
        port_dmg[at["target"]] = port_dmg.get(at["target"], 0) + int(at.get("total") or 0)
    print(f"\n[550/onappear] summons sur le plateau={len(fresh) - len(off_board)} hors={len(off_board)} "
          f"degat natif={nat_dmg} port={port_dmg}")
    assert not off_board, \
        (f"{len(off_board)} summon(s) ont QUITTE le plateau a l'apparition -> `getAbilityType` "
         f"rend 1023 Burrowers, pas GetNormalAttackType : l'hypothese du port est FAUSSE")
    assert nat_dmg, "aucun degat on-appearance cote natif : le PerformAIAbility n'a pas fire"
    assert port_dmg == nat_dmg, \
        (f"degat on-appearance port {port_dmg} != natif {nat_dmg} -- les summons n'attaquent pas "
         f"la meme chose ou pas par le meme pipeline")
