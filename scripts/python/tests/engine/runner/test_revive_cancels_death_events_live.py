"""case-89 volet C -- **la GARDE de `IdunBattle.Operations.KillUnitOperation$$Execute`** : un REVIVE pose pendant
`On(PreUnitDeath = 1)` COURT-CIRCUITE `On(2)`, `On(0)` et `On(54 = UnitDefeated)` -- mais **PAS**
`On(53 = PostUnitKill)`, qui est publie hors de la garde.

RE (decompile = verite) :
  * `IdunBattle.Operations.KillUnitOperation$$Execute` emet `On(1)` @IdunBattle.Operations.KillUnitOperation$$Execute+0x7cc PUIS teste
    `pcVar26 = thunk_FUN_1801f5f80(unitComponent + 0xa8, <hasValue de Nullable<...>>) ;
     if (*pcVar26 == '\\0') { ... }` @IdunBattle.Operations.KillUnitOperation$$Execute+0x81c. `On(2)` @+0x979,
    `On(0)` @+0xe49 et `On(0x36 = 54 UnitDefeated)` @+0xefc sont a l'interieur de ce bloc.

  * ⚠ CORRECTION #462-r4b-r1-r1-r1-r1-c-r3-r1-r4 -- cette docstring affirmait << les QUATRE autres
    dispatchs sont TOUS a l'interieur de ce bloc, sans `else` >>, et se fondait sur la PROFONDEUR
    d'accolades. Elle est FAUSSE sur deux points, re-mesures a la PILE d'accolades sur `rnca9r7q6c` :
    l'`else` EXISTE (`matchState.<slot 0x63>(killed)` @+0xfcc = l'application du revive), et
    `On(0x35 = 53 PostUnitKill)` @+0x10ac est APRES le `if/else` -- il part donc dans les DEUX
    branches. La profondeur ne discrimine pas (les quatre valent 9) ; la pile, si : `On(0x35)` porte
    `if (dispatcher != null)` la ou les trois autres portent `if (!PendingRevive.HasValue)`.
    Les libelles `0x37=55` / `0x36=54` etaient eux aussi decales d'un cran (les valeurs justes sont
    `0x36=54 UnitDefeated` et `0x35=53 PostUnitKill`) -- meme glissement que celui corrige en #301.
    Ce que ce fichier MESURE (la nova qui ne part pas) est INCHANGE : `On(2)` reste bien coupe.
  * Le champ teste est le MEME que celui qu'ECRIT `IdunBattle.Entities.Behaviours.ReviveBehaviour$$Execute`
    (`*(lVar20 + 0xa8..0xe8) = ReviveData`) et que LIT+PURGE `IdunBattle.Operations.ReviveUnitOperation$$Execute`
    (garde @IdunBattle.Operations.ReviveUnitOperation$$Execute+0x2ba, purge @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+) -> c'est le `Nullable<ReviveData>` « revive en attente ».

CONSEQUENCE OBSERVABLE choisie ici (scenario CRAFTE, distinct de ceux qui ont servi a batir le port) :
un porteur de **death-nova** (`deathPutrifier`, trait `PutridExplosion` -> `On(2)`) qui meurt A COTE d'un
**Narthecium** (`ultraApothecary`, chance=100, filtre `AreFriends & IsAdjacent(2)`, cible non-Mechanical)
est REVIVE -> **sa nova ne part PAS**, donc l'Apothecary adjacent ne prend AUCUN degat. On oppose la face
NEGATIVE sur le MEME etat (gate revive deja consomme ce tour) : la nova part et l'Apothecary encaisse
`putridExplosionDmgPct%` du maxPV du Putrifier. Le delta de PV d'une TROISIEME unite est le discriminant.

La mort passe par le VRAI chokepoint `AttackDamageOperation._apply_damage_pipeline` (damage.py), donc par
`_fire_death_if_killed` -> `On(1)` -> garde -> (`On(2)`/`On(54 = UnitDefeated)` ou court-circuit). ASCII only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.revive import reset_revive_gates
from engine.runner.components import (UnitComponent, HealthComponent,
                                      PositionComponent, StatsComponent)
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.pathfinding.board import Board
from engine.entities.effects.magnitude import ability_var, trait_var

CASTER = "ultraApothecary"        # passif Narthecium (chance=100), non-Mechanical, healType=0
NOVA = "deathPutrifier"           # trait PutridExplosion (nova `On(2)`), NON-Mechanical -> revivable
BUILD = ["--p-units", f"{CASTER},{NOVA}", "--a-units", "worldKharn",
         "--rank", "17", "--hp-player", "300000"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _by_vis(state, vis):
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _pc(st, uid):
    return st.get_entity(uid).get_component(PositionComponent)


def _hc(st, uid):
    return st.get_entity(uid).get_component(HealthComponent)


def _uc(st, uid):
    return st.get_entity(uid).get_component(UnitComponent)


@pytest.fixture(scope="module")
def env(live_session, rpc, build_runner):
    rid = build_runner("31337", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        pytest.skip("capture live KO")
    st0 = load_state(dv, ob, snap, board=board)
    ids = {"ap": _by_vis(st0, CASTER), "nova": _by_vis(st0, NOVA)}
    if any(v is None for v in ids.values()):
        pytest.skip("roster incomplet offline: %s" % ids)
    sc = st0.get_entity(ids["ap"]).get_component(StatsComponent)
    return {"dv": dv, "ob": ob, "snap": snap, "board": board, "ids": ids,
            "revive_hp": ability_var("Narthecium", "hp",
                                     getattr(sc.ctx, "passive_ability_level", None),
                                     multiplier_pct=getattr(sc.ctx, "ability_variables_multiplier", 100)),
            "nova_pct": trait_var("PutridExplosion", "putridExplosionDmgPct")}


def _fresh(env, seed=31337):
    """Etat REEL recharge + positions DRIVEES : Apothecary sur une tuile a >=3 voisins, Putrifier
    ADJACENT (le `IsAdjacent(2)` de Narthecium ET le `AdjacentUnits` de la nova sont alors satisfaits)."""
    st = load_state(env["dv"], env["ob"], env["snap"], board=env["board"])
    st.rng = IntBasedMersenneTwister(seed)
    board = env["board"]
    center = None
    for uid, e in st.entities.items():
        pc = e.get_component(PositionComponent)
        if pc is None:
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None and len([n for n in board.neighbours(t) if board.walkable(n)]) >= 3:
            center = t
            break
    if center is None:
        pytest.skip("aucune tuile centrale a >=3 voisins")
    _pc(st, env["ids"]["ap"]).col, _pc(st, env["ids"]["ap"]).row = board.coord(center)
    nb = next((n for n in board.neighbours(center) if board.walkable(n)), None)
    if nb is None:
        pytest.skip("pas de voisin walkable")
    _pc(st, env["ids"]["nova"]).col, _pc(st, env["ids"]["nova"]).row = board.coord(nb)
    # ecarter TOUTE autre unite (ennemi inclus) pour que le seul adjacent au Putrifier soit l'Apothecary
    near = set(board.neighbours(center)) | set(board.neighbours(nb)) | {center, nb}
    far = [t for t in board.by_id if board.walkable(t) and t not in near]
    for i, (uid, e) in enumerate(st.entities.items()):
        if uid in (env["ids"]["ap"], env["ids"]["nova"]):
            continue
        pc = e.get_component(PositionComponent)
        if pc is not None and i < len(far):
            pc.col, pc.row = board.coord(far[i])
    return st


def _lethal_kill(st, uid, killer):
    """Mort par le VRAI chokepoint de degat (`_apply_damage_pipeline`), avec un total letal exact."""
    hc = _hc(st, uid)
    total = int(hc.hp)                                   # letal NON overkill (dmg < 2*PV)
    return AttackDamageOperation._apply_damage_pipeline(
        st, uid, killer, st.get_entity(uid), hc, total, "Physical")


def test_revive_cancels_the_death_nova(env):
    """Narthecium adjacent -> le Putrifier est REVIVE pendant `On(1)` -> la garde @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e ECHOUE
    -> `On(2)` n'est PAS emis -> l'Apothecary adjacent ne prend AUCUN degat de nova."""
    st = _fresh(env)
    ap, nova = env["ids"]["ap"], env["ids"]["nova"]
    hp_ap0 = int(_hc(st, ap).hp)
    maxhp_nova = int(_hc(st, nova).hp_max)
    out = _lethal_kill(st, nova, ap) or []
    assert _uc(st, nova).alive, "le Putrifier n'a pas ete revive par Narthecium: %s" % out
    assert int(_hc(st, nova).hp) == min(int(env["revive_hp"]), maxhp_nova), "hp de revive inattendu"
    assert any("kill_cancelled_by_revive" in r for r in out), \
        "la garde n'a pas signale l'annulation de la mort: %s" % out
    assert not any(r.get("ability") == "PutridExplosion" for r in out), \
        "la death-nova a fire malgre le revive (On(2) non court-circuite): %s" % out
    assert int(_hc(st, ap).hp) == hp_ap0, "l'Apothecary a pris du degat de nova (On(2) emis)"


def test_without_revive_the_nova_fires(env):
    """Face NEGATIVE sur le MEME etat : gate revive deja consomme ce tour (`revive_used_this_turn`)
    -> aucun revive n'est pose -> la garde PASSE -> `On(2)` est emis -> la nova frappe l'Apothecary
    adjacent (`putridExplosionDmgPct%` du maxPV du Putrifier, faction excluee = DeathGuard, l'Apothecary
    est Ultramarines donc TOUCHE)."""
    st = _fresh(env)
    ap, nova = env["ids"]["ap"], env["ids"]["nova"]
    _uc(st, ap).revive_used_this_turn = True             # DeactivateEffect deja consomme ce tour
    hp_ap0 = int(_hc(st, ap).hp)
    out = _lethal_kill(st, nova, ap) or []
    assert not _uc(st, nova).alive, "revive alors que le gate once-per-turn est consomme"
    assert not any("kill_cancelled_by_revive" in r for r in out), "garde annulee a tort: %s" % out
    assert any(r.get("ability") == "PutridExplosion" for r in out), \
        "la death-nova n'a PAS fire alors qu'aucun revive n'etait en attente: %s" % out
    assert int(_hc(st, ap).hp) < hp_ap0, "l'Apothecary n'a pris aucun degat de nova"


def test_gate_reactivates_next_turn(env):
    """Garde de non-regression du once-per-turn : apres `reset_revive_gates` (turn-start), le revive
    redevient possible et re-annule la mort."""
    st = _fresh(env)
    ap, nova = env["ids"]["ap"], env["ids"]["nova"]
    _uc(st, ap).revive_used_this_turn = True
    _lethal_kill(st, nova, ap)
    assert not _uc(st, nova).alive
    st2 = _fresh(env)
    _uc(st2, ap).revive_used_this_turn = True
    reset_revive_gates(st2)
    out = _lethal_kill(st2, nova, ap) or []
    assert _uc(st2, nova).alive, "revive non re-arme au turn-start: %s" % out
