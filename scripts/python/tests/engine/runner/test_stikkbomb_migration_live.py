"""#149 slice-12 : Stikkbomb (1051, Ork Boy) MIGRATION vers l'arbre DSL + FIX friendly-fire (#213).

`IdunBattleLogic.Entities.Abilities.Active.Loki.StikkbombAbility$$ExecuteBehaviour` (DECOMPILE) = `Execute(AtomicGroup(op_Addition(main, splash)))` :
    main   = AttackWithAttackDamage(caster, target, RandomAmount, Blast, nrOfHits=2)
    splash = AttackWithAttackDamage(caster, AdjacentUnits(target,1,3), RandomAmount, Blast, nrOfHits_2=1)
Le splash passe `AdjacentUnits(target,1,3)` BRUT -- SANS wrapper `Enemies(...)` (contraste PlasmaGrenade
`Enemies(caster, AdjacentUnits(...))` et Fragstorm `AdjacentTiles - Tiles(Friends(...))`). DECOMPILE + i2
concordants (Stikkbomb = « units in hexes adjacent », les 3 autres = « enemy units »/« excluding friendly
hexes ») => FRIENDLY-FIRE : le splash touche TOUTES les unites adjacentes a la cible, ALLIES DU CASTER INCLUS.

La FRIENDLY-FIRE est une propriete du SELECTEUR de l'ability (config-driven `AdjacentUnits`), PAS du kit du
caster -> le vrai carrier (Ork Boy = orksNpc2OrkBoy NPC / orksOrkBoys summon) n'etant PAS buildable en lineup,
on exerce l'ability behaviour avec un caster PROXY buildable (le splash ne depend que de l'ability + geometrie).
On DRIVE un ALLIE du caster (meme team) ET un ennemi adjacents a la cible, on caste, et on verifie que le splash
touche LES DEUX = exactement l'ensemble des unites a distance hex 1 de la cible (AUCUN filtre team), l'allie du
caster INCLUS. Lit l'etat LIVE. ASCII-only. NON committe (tests confront live, hors depot).

ORACLE des COUPS (#96) -- aucune valeur figee. Le decompile passe `GetNumberConstant(config, 0x2f)` (main) et
`GetNumberConstant(config, 0x32)` (splash) TELS QUELS aux deux feuilles : scalaires BRUTS, donc oracle =
`constants.nrOfHits` / `constants.nrOfHits_2` de gameconfig (indices resolus sur
`IdunBattle.Configuration.AbilityConstantType`). Nuance qui vaut le controle supplementaire : la factory
native de Stikkbomb est `AttackWithAttackDamage` (famille ATTACK), donc `AttackDamageOperation.Execute`
FAIT passer cette base par `GetAttackHits` (ExtraHits, Parry/Camouflage/Diminutive, auras) -- le `hits` du
diag est la SORTIE de ce canal, pas la constante. Le test decale donc l'oracle (monkeypatch de la cle) et
exige que le port SUIVE le decalage a l'unite : cela prouve d'un coup (1) que la feuille lit bien CETTE cle
et non sa voisine, (2) que le canal est l'identite sur ce roster -- donc que l'egalite avec la config a un
sens ici.
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, PositionComponent, OwnerComponent, UnitComponent
from engine.runner.abilities.loki import StikkbombAbility

# caster PROXY + ennemis = unites lineup buildables (le carrier Stikkbomb reel = Ork Boy NPC/summon, non buildable ;
# le splash friendly-fire ne depend PAS du kit du caster, seulement de l'ability + geometrie).
BUILD = ["--roster", "1", "--p-units", "necroSpyder,necroDestroyer",
         "--a-units", "necroSpyder,necroDestroyer"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _pos(state, uid):
    pc = state.get_entity(uid).get_component(PositionComponent)
    return (pc.col, pc.row) if pc is not None else None


def _team(state, uid):
    oc = state.get_entity(uid).get_component(OwnerComponent)
    return oc.team if oc is not None else None


def _drive_adjacent(state, board, unit_id, target_id, occupied):
    """DRIVE `unit_id` sur une tuile LIBRE a distance hex 1 de `target_id` (hexgeo = adjacence PURE, pas
    board.neighbours qui exclut l'occupe). Renvoie True si place."""
    tp = _pos(state, target_id)
    for tid, info in board.by_id.items():
        cell = (info["col"], info["row"])
        if cell in occupied or not board.walkable(tid):
            continue
        if hexgeo.distance(cell, tp) == 1:
            pc = state.get_entity(unit_id).get_component(PositionComponent)
            pc.col, pc.row = info["col"], info["row"]
            occupied.add(cell)
            return True
    return False


def test_stikkbomb_migration_friendly_fire(live_session, rpc, build_runner, monkeypatch):
    """`StikkbombAbility.execute_behaviour` prend le chemin DSL (`stikkbomb_tree`) et le splash FRIENDLY-FIRE :
    allie-du-caster + ennemi adjacents a la cible sont TOUS DEUX touches (== toutes les unites a dist 1).
    Les nb de coups main/splash viennent de gameconfig et sont prouves DERIVES (cf. ORACLE en en-tete)."""
    import gameconfig as GC
    from engine.entities.pathfinding.board import Board
    cst = (GC.ability("Stikkbomb") or {}).get("constants") or {}
    cfg_main, cfg_splash = cst.get("nrOfHits"), cst.get("nrOfHits_2")
    assert cfg_main is not None and cfg_splash is not None, \
        f"oracle introuvable : constants nrOfHits/nrOfHits_2 de Stikkbomb (lu: {cst})"
    cfg_main, cfg_splash = int(cfg_main), int(cfg_splash)
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("rng absent")

    state = load_state(dec, ob, snap, board=board)
    state.rng = _seed_rng(s0)

    live_ids = [u["id"] for u in (dec.get("units") or []) if state.get_entity(u["id"]) is not None]
    if len(live_ids) < 3:
        pytest.skip("besoin d'au moins 3 unites")
    # caster PROXY = 1re unite ; allie = meme team (!= caster) ; cible = autre team ; enemy2 = autre team (!= cible)
    caster_id = live_ids[0]
    ctm = _team(state, caster_id)
    ally = next((i for i in live_ids if i != caster_id and _team(state, i) == ctm), None)
    target = next((i for i in live_ids if _team(state, i) != ctm), None)
    enemy2 = next((i for i in live_ids if i != target and _team(state, i) != ctm), None)
    if ally is None or target is None:
        pytest.skip("besoin d'un allie du caster + une cible ennemie")

    occupied = {_pos(state, i) for i in live_ids if _pos(state, i) is not None}
    occupied.discard(_pos(state, ally))
    assert _drive_adjacent(state, board, ally, target, occupied), "impossible de DRIVE l'allie adjacent a la cible"
    if enemy2 is not None:
        occupied.discard(_pos(state, enemy2))
        _drive_adjacent(state, board, enemy2, target, occupied)   # best-effort (2e ennemi adjacent)

    # ensemble ATTENDU = toutes les unites VIVANTES a distance hex 1 de la cible (AUCUN filtre team), hors cible
    tp = _pos(state, target)
    expected_splash = sorted(
        i for i in live_ids if i != target
        and _pos(state, i) is not None and hexgeo.distance(_pos(state, i), tp) == 1
        and (state.get_entity(i).get_component(UnitComponent) or UnitComponent(None, False)).alive)
    assert ally in expected_splash, "l'allie n'a pas ete drive adjacent (setup)"

    # positions DRIVEES : on les rejouera a l'identique pour le controle de derivation ci-dessous.
    pos_snap = {i: _pos(state, i) for i in live_ids if _pos(state, i) is not None}

    def _full_hp(st):
        """PV a plein sur cible + splash (evite l'overkill qui masque un coup)."""
        for i in [target] + expected_splash:
            hc = st.get_entity(i).get_component(HealthComponent)
            if hc is not None:
                hc.hp = hc.hp_max

    _full_hp(state)

    # === chemin DSL migre ===
    res = StikkbombAbility().execute_behaviour(state, caster_id, target)
    splash_ids = sorted((x.get("target") for x in (res.get("splash") or [])))
    main_hits = (res.get("main_attack") or {}).get("hits")
    print(f"\n[STIKKBOMB migration] dsl={res.get('dsl')} main_hits={main_hits} "
          f"splash={splash_ids} expected={expected_splash} ally={ally}(team{ctm})")

    assert res.get("dsl") is True, f"arbre DSL non pris: {res}"
    assert main_hits == cfg_main, \
        f"main hits {main_hits} != constants.nrOfHits={cfg_main} (oracle gameconfig, GetNumberConstant 0x2f)"
    # FRIENDLY-FIRE : le splash == TOUTES les unites adjacentes (allie du caster INCLUS), AUCUN filtre team
    assert splash_ids == expected_splash, f"splash {splash_ids} != adjacents-toutes-teams {expected_splash}"
    assert ally in splash_ids, "FRIENDLY-FIRE NON reproduit : l'allie du caster n'est PAS dans le splash"
    for x in (res.get("splash") or []):
        h = (x.get("attack") or {}).get("hits")
        assert h == cfg_splash, (f"splash cible {x.get('target')} hits {h} != "
                                 f"constants.nrOfHits_2={cfg_splash} (oracle gameconfig, 0x32)")
    # l'allie (meme team que le caster) a bien perdu des PV = friendly-fire effectif
    ally_hc = state.get_entity(ally).get_component(HealthComponent)
    assert ally_hc.hp < ally_hc.hp_max, "l'allie n'a pas subi de degat (friendly-fire non effectif)"

    # === DERIVATION : on DECALE l'oracle de la cle main et le port doit SUIVRE ===
    # Sans ce controle, `main_hits == cfg_main` ne separerait pas " la feuille lit constants.nrOfHits " de
    # " elle rend cfg_main par coincidence " (canal GetAttackHits, cle voisine nrOfHits_2, valeur en dur).
    # Le splash, lui, doit rester a `nrOfHits_2` : c'est ce qui prouve que les deux feuilles lisent des cles
    # DISTINCTES. Etat re-charge a neuf (memes positions/PV/rng) pour re-caster proprement.
    bumped = cfg_main + 2
    orig_ability = GC.ability
    patched = dict(orig_ability("Stikkbomb") or {})
    patched["constants"] = {**(patched.get("constants") or {}), "nrOfHits": str(bumped)}
    monkeypatch.setattr(GC, "ability", lambda aid: patched if aid == "Stikkbomb" else orig_ability(aid))

    st2 = load_state(dec, ob, snap, board=board)
    st2.rng = _seed_rng(s0)
    for i, p in pos_snap.items():
        pc = st2.get_entity(i).get_component(PositionComponent)
        if pc is not None:
            pc.col, pc.row = p
    _full_hp(st2)
    res2 = StikkbombAbility().execute_behaviour(st2, caster_id, target)
    main_hits2 = (res2.get("main_attack") or {}).get("hits")
    splash_hits2 = sorted({(x.get("attack") or {}).get("hits") for x in (res2.get("splash") or [])})
    print(f"[STIKKBOMB oracle] nrOfHits {cfg_main}->{bumped} : main_hits {main_hits}->{main_hits2} "
          f"splash_hits={splash_hits2} (attendu {cfg_splash}, inchange)")
    assert main_hits2 == bumped, (
        f"main hits {main_hits2} != oracle decale {bumped} : la feuille MAIN ne DERIVE pas de "
        f"constants.nrOfHits (cle voisine lue, valeur figee, ou canal GetAttackHits non identite)")
    assert splash_hits2 == [cfg_splash], (
        f"splash hits {splash_hits2} != [{cfg_splash}] apres decalage de nrOfHits : la feuille SPLASH ne lit "
        f"pas constants.nrOfHits_2 mais la cle du volet MAIN")
