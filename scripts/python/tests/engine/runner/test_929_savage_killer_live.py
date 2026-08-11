"""#929 -- `SavageKiller` (passif `spaceWulfen` << Ulf >>, `TriggeredAbilityType` 0x487 = 1159) :
la reaction 5 coups Power, ses DEUX faces, et les DEUX gates qui les separent.

RE + residus : `engine/runner/operations/triggers/loki/savage_killer.py`.

MONTAGE UNIQUE, TROIS REGIMES -- duel `spaceWulfen` (moi) vs `orksRuntherd` (adverse), distance
PILOTEE, action jouee au tour ADVERSE puis rejouee offline sur un flux RNG seede. `orksRuntherd` a
ete choisi pour une raison structurelle, pas par commodite : son actif `GetEmRuntz` fait naitre ses
grots sur les tuiles LIBRES adjacentes AU CASTER **et** adjacentes a un ENNEMI
(`IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetSpawnTileSelector`, mirror
`abilities/behaviours/composites.py::get_spawn_tile_selector`) -- donc un grot NAIT ADJACENT A ULF,
ce qui exerce la face A sans aucun pilotage de summon.

    | regime    | dist | action de Runtherd | face B (Runtherd frappe ?) | face A (grot frappe ?) |
    |-----------|------|--------------------|----------------------------|------------------------|
    | `actif`   |  1   | caste GetEmRuntz   | OUI, 5 coups 1159          | OUI, 5 coups 1159      |
    | `normale` |  1   | attaque NORMALE    | **NON** (gate)             | oui (grot de SquigHound)|
    | `summon`  |  2   | caste GetEmRuntz   | **NON** (gate d'adjacence) | OUI, 5 coups 1159      |

Les deux NON sont les deux gates du decompile, et ils sont MESURES (probe_929, build `rnca9r7q6c`) :
  * `normale` : `IsActiveAbilityCountedAsUsed(true)` -> son volet `!IsNormalAttackOrHealOrRepair`
    eteint la face B sur une attaque normale. Live : Runtherd garde 999999 PV, zero event
    `Passive_Ability_Type: 1159` sur lui. C'est le << loophole >> deja observe en self-play
    (frapper Ulf en NORMALE depuis un corps deja-adjacent ne le reveille pas).
  * `summon` : `IsAdjacent(Owner@DSLSelectors+0x30, Caster@+0x48, 3)` -- le caster est a 2 hexes,
    la face B ne part pas, mais son GROT nait adjacent et prend les 5 coups.

ATTRIBUTION DES DIVERGENCES -- ce que ce fichier NE mesure PAS, et pourquoi :
  * regime `normale` : le grot live vient du PASSIF `SquigHound`, dont le spawn n'est PAS porte
    (`spawn.py::execute_squighound_summon` n'a AUCUN appelant cote port). Le test ne compare donc
    que les PV d'Ulf et de Runtherd -- tous deux calcules AVANT le spawn (SquigHound est un
    after-hit), donc insensibles a cette absence. Comparer le grot y accuserait `SquigHound`, pas
    `SavageKiller`.
  * les ids d'entite du grot DIFFERENT entre live et offline (compteur propre a chaque cote) : la
    confrontation se fait sur le visualId + le fait qu'il soit MORT, jamais sur l'id.

Lit l'etat LIVE (rien de hardcode). ASCII only.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.pathfinding.board import Board
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.runner.components import HealthComponent, StatsComponent, UnitComponent
from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage
from engine.runner.operations.triggers.loki.savage_killer import SavageKillerAbility
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

ULF = "spaceWulfen"
RUNTHERD = "orksRuntherd"
SAVAGE_KILLER = int(TriggeredAbilityType.SavageKiller)          # 0x487 = 1159
#: `AbilityConfiguration.GetNumberConstant(AbilityConstantType.nrOfHits = 0x2f)` du gameconfig.
NR_OF_HITS = 5


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


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


def _alive(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _tags(ev):
    td = ev.get("tags")
    if not td:
        return {}
    return json.loads(td) if isinstance(td, str) else td


def _savage_hits(events, victim_id):
    """Les `Amount` des events dont le tag `Passive_Ability_Type` vaut 1159 et qui portent sur
    `victim_id`. C'est le canal natif du passif : ses coups portent `Passive_Ability_Type` et
    AUCUN `Active_Ability_Type` (mesure probe_929)."""
    out = []
    for e in events:
        td = _tags(e)
        if td.get("Passive_Ability_Type") == SAVAGE_KILLER and td.get("Target_Id") == victim_id:
            out.append(td.get("Amount"))
    return out


def _summon_rows(dv):
    """Les unites du `decisionView` qui portent le tag natif de summon (visualId du grot)."""
    return [u for u in (dv.get("units") or []) if "Grot" in str(u.get("visualId") or "")]


def _offline_summons(state):
    """Les entites OFFLINE dont le `visual_id` est celui d'un grot -- le pendant port de
    `_summon_rows`. L'id d'entite n'est PAS comparable au live (compteurs distincts)."""
    out = []
    for eid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        vid = getattr(sc.ctx, "visual_id", None) if sc is not None else None
        if vid and "Grot" in str(vid):
            out.append(eid)
    return out


def _scenario(rpc, build_runner, *, want_dist: int, use_active: bool):
    """Monte le duel, amene Ulf a `want_dist` hexes de Runtherd, passe au tour ADVERSE, puis joue
    l'action de Runtherd LIVE et OFFLINE sur le meme flux RNG. Renvoie la classification ou
    `{ok: False, reason}` (le test appelant decide skip/fail)."""
    b = build_runner("777", extra=["--roster", "1", "--p-units", ULF,
                                   "--a-units", RUNTHERD,
                                   "--hp-player", "999999", "--hp-target", "999999"])
    rid = b["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        return {"ok": False, "reason": "boardGraph indispo"}
    board = Board(bg["tiles"], adjacency="native_sym")

    def tile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row"))

    for _turn in range(30):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dv):
            return {"ok": False, "reason": "decisionView KO"}
        ulf, run = _alive(dv, ULF), _alive(dv, RUNTHERD)
        if ulf is None or run is None:
            return {"ok": False, "reason": "unite manquante"}
        dist = _bfs(board, tile(run))
        if dist.get(tile(ulf)) == want_dist:
            break
        if dv.get("currentPlayer") != ulf.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        row = next((x for x in (mt.get("units") or []) if x.get("unitId") == ulf["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((row or {}).get("tiles") or [])}
        exact = [t for t in reach if dist.get(t) == want_dist]
        pool = exact or [t for t in reach if t in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        best = exact[0] if exact else min(pool, key=lambda t: dist[t])
        col, r = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": ulf["id"], "to": {"col": col, "row": r}}}, 40)
        if not exact:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    # tour ADVERSE -- le natif REFUSE l'action d'une unite hors tour
    for _ in range(4):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ulf = _alive(dv, ULF)
        if ulf is not None and dv.get("currentPlayer") != ulf.get("owner"):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ulf, run = _alive(dv, ULF), _alive(dv, RUNTHERD)
    if ulf is None or run is None:
        return {"ok": False, "reason": "unite manquante post-setup"}
    got = _bfs(board, tile(run)).get(tile(ulf))
    if got != want_dist:
        return {"ok": False, "reason": f"distance {got} != {want_dist} apres pilotage"}
    kind = "active" if use_active else "normal"
    ab = next((a for a in (run.get("abilities") or []) if a.get("kind") == kind), None)
    if ab is None:
        return {"ok": False, "reason": f"pas d'ability {kind} sur Runtherd"}

    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap, board=board)      # board OBLIGATOIRE : le gate est POSITIONNEL
    hp_before = {}
    for u in (ulf, run):
        e = state.get_entity(u["id"])
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is None or hc.hp is None:
            return {"ok": False, "reason": "unite sans PV offline"}
        hp_before[u["id"]] = hc.hp
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        return {"ok": False, "reason": "dumpRng KO"}
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": run["id"], "targetId": ulf["id"],
        "abilityType": ab["id"]}}, 90)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        return {"ok": False, "reason": f"action live KO: {str(res)[:150]}"}
    events = a0.get("events") or []
    live_hp = {u.get("squadId"): u.get("hp") for u in (res.get("units") or [])}
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

    if use_active:
        runner.apply(ActiveAbilityMessage(caster_id=run["id"], target_id=ulf["id"],
                                          ability_type=int(ab["id"])))
    else:
        runner.apply(AttackUnitMessage(run["id"], ulf["id"]))

    off_hp = {}
    for u in (ulf, run):
        e = state.get_entity(u["id"])
        hc = e.get_component(HealthComponent) if e is not None else None
        off_hp[u["id"]] = hc.hp if hc is not None else None
    off_summons = []
    for eid in _offline_summons(state):
        e = state.get_entity(eid)
        uc = e.get_component(UnitComponent)
        hc = e.get_component(HealthComponent)
        off_summons.append({"id": eid, "alive": bool(uc.alive) if uc else None,
                            "hp": hc.hp if hc else None})
    live_summons = [{"id": u["id"], "alive": bool(u.get("alive")), "hp": u.get("hp")}
                    for u in _summon_rows(dv2)]
    return {"ok": True, "reason": None, "state": state, "board": board,
            "ulf": ulf["id"], "runtherd": run["id"], "dist": got,
            "hp_before": hp_before, "live_hp": live_hp, "off_hp": off_hp,
            "events": events,
            "hits_on_runtherd": _savage_hits(events, run["id"]),
            "live_summons": live_summons, "off_summons": off_summons}


# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="function")
def sk_active_adjacent(live_session, rpc, build_runner):
    return _scenario(rpc, build_runner, want_dist=1, use_active=True)


@pytest.fixture(scope="function")
def sk_normal_adjacent(live_session, rpc, build_runner):
    return _scenario(rpc, build_runner, want_dist=1, use_active=False)


@pytest.fixture(scope="function")
def sk_active_at_two(live_session, rpc, build_runner):
    return _scenario(rpc, build_runner, want_dist=2, use_active=True)


def test_face_b_frappe_le_caster_de_l_actif_adjacent(sk_active_adjacent):
    """FACE B (`On(PreUnitAbility) & IsAdjacent(Owner, Caster) & AreEnemies & ...`) : un ennemi
    ADJACENT qui caste un ACTIF prend les `nrOfHits` = 5 coups Power d'Ulf. Le REPLAY offline
    reproduit les PV du caster AU PV PRES -- valeur EXACTE, pas un signe."""
    c = sk_active_adjacent
    if not c["ok"]:
        pytest.skip(c["reason"])
    rid_run = c["runtherd"]
    assert len(c["hits_on_runtherd"]) == NR_OF_HITS, (
        f"le natif doit poser {NR_OF_HITS} coups `Passive_Ability_Type` = {SAVAGE_KILLER} sur le "
        f"caster, obtenu {c['hits_on_runtherd']} -- le scenario n'exerce pas la face B")
    assert c["live_hp"][rid_run] < c["hp_before"][rid_run], (
        "AUCUNE reaction live : le caster garde ses PV -- le scenario n'exerce rien")
    assert c["off_hp"][rid_run] == c["live_hp"][rid_run], (
        f"PV CASTER offline {c['off_hp'][rid_run]} != live {c['live_hp'][rid_run]} "
        f"(reaction non reproduite : coups live={c['hits_on_runtherd']})")


def test_face_a_frappe_le_summon_ne_adjacent(sk_active_adjacent):
    """FACE A (`On(UnitAdded) & HasTrait(Target, Summon) & IsAdjacent(Owner, Target) & AreEnemies`) :
    le grot que `GetEmRuntz` fait naitre ADJACENT a Ulf prend lui aussi les 5 coups et MEURT. Le
    port doit le tuer pareil -- c'est la face que ni le trait du caster ni la nature de l'ability
    ne gouvernent."""
    c = sk_active_adjacent
    if not c["ok"]:
        pytest.skip(c["reason"])
    live = c["live_summons"]
    if not live:
        pytest.skip("aucun grot n'est ne de ce cast (tuiles de spawn indisponibles)")
    hits = _savage_hits(c["events"], live[0]["id"])
    assert len(hits) == NR_OF_HITS, (
        f"le natif doit poser {NR_OF_HITS} coups 1159 sur le grot ne adjacent, obtenu {hits}")
    assert all(not s["alive"] for s in live), (
        f"le grot devait mourir des 5 coups Power live, etat={live}")
    assert len(c["off_summons"]) == len(live), (
        f"le port n'a pas fait naitre le meme nombre de grots : offline={c['off_summons']} "
        f"live={live} -- divergence de `GetEmRuntz`, pas de `SavageKiller`")
    assert all(not s["alive"] for s in c["off_summons"]), (
        f"GROT SURVIVANT offline : {c['off_summons']} alors que le natif l'a tue ({live}) -- "
        "la face A `On(UnitAdded)` ne part pas")


def test_aucune_reaction_sur_une_attaque_normale(sk_normal_adjacent):
    """NEGATIF `IsActiveAbilityCountedAsUsed(true)` : MEME porteur, MEME adjacence, MEME evenement
    `On(PreUnitAbility)` -- mais l'ennemi frappe en NORMALE. Le natif ne reagit PAS (son volet
    `!IsNormalAttackOrHealOrRepair` mord). Sans ce gate, le port infligerait 5 coups Power fantomes
    a chaque attaque normale d'un ennemi adjacent, ce qui est de tres loin le cas le plus frequent
    en bataille.

    ⚠ Le grot que le PASSIF `SquigHound` de Runtherd fait naitre apres son attaque n'est PAS
    compare : son spawn n'est pas porte (cf. l'en-tete). Les deux PV compares sont calcules AVANT
    lui."""
    c = sk_normal_adjacent
    if not c["ok"]:
        pytest.skip(c["reason"])
    rid_run, rid_ulf = c["runtherd"], c["ulf"]
    assert c["dist"] == 1, f"scenario non discriminant : distance {c['dist']}"
    assert c["hits_on_runtherd"] == [], (
        f"le natif a reagi a une attaque NORMALE ({c['hits_on_runtherd']}) -- le gate "
        "`IsActiveAbilityCountedAsUsed` ne serait pas ce que dit le decompile")
    assert c["live_hp"][rid_run] == c["hp_before"][rid_run], (
        f"PV du caster live {c['live_hp'][rid_run]} != {c['hp_before'][rid_run]} : quelque chose "
        "l'a frappe alors qu'aucun coup 1159 n'a ete emis")
    assert c["off_hp"][rid_run] == c["live_hp"][rid_run], (
        f"REACTION FANTOME offline : PV caster {c['off_hp'][rid_run]} != live "
        f"{c['live_hp'][rid_run]}")
    assert c["off_hp"][rid_ulf] == c["live_hp"][rid_ulf], (
        f"PV ULF offline {c['off_hp'][rid_ulf]} != live {c['live_hp'][rid_ulf]} "
        "(flux RNG desynchronise avant meme l'attaque)")


def test_face_b_ne_part_pas_a_deux_hexes_mais_face_a_oui(sk_active_at_two):
    """NEGATIF `IsAdjacent(Owner@+0x30, Caster@+0x48, 3)` ET positif de la face A, dans le MEME
    coup : Runtherd caste depuis 2 hexes -> il n'est PAS touche, mais son grot NAIT adjacent a Ulf
    (`GetSpawnTileSelector` = tuiles libres adjacentes au caster ET a un ennemi) et prend les 5
    coups. C'est le seul montage qui separe les deux faces sur la MEME action."""
    c = sk_active_at_two
    if not c["ok"]:
        pytest.skip(c["reason"])
    rid_run = c["runtherd"]
    assert c["dist"] == 2, f"scenario non discriminant : distance {c['dist']}"
    assert c["hits_on_runtherd"] == [], (
        f"le natif a frappe un caster NON adjacent ({c['hits_on_runtherd']}) -- le gate "
        "d'adjacence de la face B ne serait pas ce que dit le decompile")
    live = c["live_summons"]
    if not live:
        pytest.skip("aucun grot n'est ne de ce cast (tuiles de spawn indisponibles)")
    hits = _savage_hits(c["events"], live[0]["id"])
    assert len(hits) == NR_OF_HITS, (
        f"la face A devait poser {NR_OF_HITS} coups sur le grot ne adjacent, obtenu {hits} -- "
        "sans elle ce scenario ne prouverait que le negatif")
    assert c["off_hp"][rid_run] == c["live_hp"][rid_run], (
        f"REACTION FANTOME offline sur un caster a 2 hexes : {c['off_hp'][rid_run]} != "
        f"{c['live_hp'][rid_run]}")
    assert len(c["off_summons"]) == len(live) and all(not s["alive"] for s in c["off_summons"]), (
        f"le port n'a pas tue le grot ne adjacent : offline={c['off_summons']} live={live}")


def test_les_quatre_evenements_natifs_sont_abonnes():
    """GARDE STRUCTURELLE, offline pur : le `CreateTrigger` natif est une union de QUATRE
    disjonctions ; TROIS sont abonnees (`UnitAfterMove`, `UnitDisplaced`, `UnitAdded`) plus
    `PreUnitAbility`. La 4e (`UnitBecameTargetable`) ne l'est PAS -- residu #929-r1, faute
    d'emetteur cote port. Ce test FIGE cette repartition : la modifier sans toucher a la RE ferait
    rougir, et retirer un evenement par accident (le plus probable) aussi."""
    abonnes = {int(SavageKillerAbility.event_id)} | {int(e) for e in SavageKillerAbility.event_ids}
    assert abonnes == {int(EventTriggerType.PreUnitAbility),
                       int(EventTriggerType.UnitAfterMove),
                       int(EventTriggerType.UnitDisplaced),
                       int(EventTriggerType.UnitAdded)}, (
        f"abonnements = {sorted(abonnes)} ; le decompile en veut exactement ces quatre "
        "(la 5e branche `UnitBecameTargetable` est un residu documente, PAS un oubli)")
    assert int(EventTriggerType.UnitBecameTargetable) not in abonnes, (
        "`UnitBecameTargetable` a ete abonne : aucun site du port n'emet cet evenement, donc le "
        "predicat `NOT (PreviousTile | TurnStartTile)` de cette branche serait NON confrontable "
        "(port speculatif). Si un emetteur a ete ajoute, porter la branche ET retirer #929-r1.")
