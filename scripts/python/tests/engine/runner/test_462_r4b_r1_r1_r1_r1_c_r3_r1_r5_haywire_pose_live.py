"""#462-r4b-r1-r1-r1-r1-c-r3-r1-r5 -- LA POSE de la mine Haywire, confrontee natif vs port.

Ce que ces bras GARDENT (et pas seulement ce qu'ils mesurent) :

  * `pose_sur_tuile_precedente` -- un deplacement pose la mine sur la tuile QUITTEE, pas sur la
    tuile d'arrivee (branche `then` du selecteur : `CanAddUnit(PreviousTile(Owner))`) ;
  * `pas_de_seconde_pose_dans_le_meme_tour` -- la fin d'activation du MEME tour n'en pose pas une
    seconde : la tuile precedente est occupee, `Count(tiles) == 0`, le behaviour part sur
    `TriggerAbilityDelayed` (branche `else` du `If` de `CreateBehaviour`) ;
  * `pose_adjacente_quand_l_unite_n_a_pas_bouge` -- un tour SANS deplacement pose a la fin
    d'activation, sur la MEILLEURE tuile adjacente libre (branche `else` du selecteur : le
    `First(SortTilesByUtilityForSummon(Randomize(CanAddUnit(AdjacentTiles(Owner)))))`), et le port
    choisit la MEME tuile que le natif ;
  * `chaine_pose_ecrasement_explosion_repose` -- LE second cas discriminant : un ecraseur ENNEMI a
    PV bas meurt SUR la mine, ce qui LIBERE la tuile precedente, et la fin d'activation y REPOSE
    une mine. C'est le seul montage qui separe << la donnee persistante survit a `On(0x28)` >> de
    << le selecteur de tuiles est vide >>, et le seul qui exerce la chaine COMPLETE
    pose -> crush -> explosion -> repose.

Aucun `pytest.skip` : un montage qui ne s'installe pas ECHOUE (#268). Le porteur `astarCyrus` est
un HERO `lineup` HORS seed BC -> `catalog_inject` (cf. `docs/rl/case-92-catalog-injection.md`).
"""
from __future__ import annotations

import uuid

import pytest

import hexgeo

from engine.entities.pathfinding.board import Board
from engine.runner.components import PositionComponent, UnitComponent
from engine.runner.messages import FinishUnitTurnMessage, MoveUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

BOARD = "MC1_67"
SEED = "777"
SUMMONER = "astarCyrus"                 # HERO `lineup` hors seed BC -> catalog_inject
ALLY = "ultraTitus"
ENEMY = "orksNob"                       # l'ECRASEUR (PV bas -> meurt sur la mine)
ENEMY_FILLER = "necroWarden"            # survit -> la bataille continue apres la mort de l'ecraseur
MINE_FRAGMENT = "HaywireMine"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _vue(rpc, rid):
    """`decisionView` -- LE canal de vivacite d'une mine. PAS `observeBattle` : son `isDead` derive
    des PV, et une mine a 0 PV par construction (cf. la fiche de `-c-r3-r1-r3`)."""
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _units(dv):
    return [u for u in ((dv or {}).get("units") or []) if u.get("alive")]


def _uid(u):
    return u.get("id", u.get("squadId", u.get("entityId")))


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _by_vis(dv, vis):
    for u in _units(dv):
        if (u.get("visualId") or "") == vis:
            return u
    return None


def _mines(dv):
    return sorted(_pos(u) for u in _units(dv)
                  if MINE_FRAGMENT in (u.get("visualId") or ""))


def _mines_offline(st):
    out = []
    for e in st.entities.values():
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if uc is None or pc is None or not uc.alive:
            continue
        if MINE_FRAGMENT in (uc.visual_id or ""):
            out.append((pc.col, pc.row))
    return sorted(out)


def _movable(rpc, rid, unit_id):
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
    for mu in (mov.get("units") or []):
        if mu.get("unitId") == unit_id:
            return {(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                    if t.get("col") is not None}
    return set()


def _act(rpc, rid, action, timeout=120):
    return rpc("applyAction", {"runnerId": rid, "action": action}, timeout)


def _capture(rpc, rid):
    cap = {"bg": rpc("boardGraph", {"runnerId": rid}, 60),
           "dv": _vue(rpc, rid),
           "ob": rpc("observeBattle", {"runnerId": rid}, 60),
           "snap": rpc("combatSnapshot", {"runnerId": rid}, 60),
           "tm": rpc("tileMeta", {"runnerId": rid}, 60),
           "ab": rpc("unitAbilityStates", {"runnerId": rid}, 60)}
    assert _ok(cap["dv"]) and _ok(cap["ob"]) and _ok(cap["snap"]), \
        "capture live KO -- montage non installe"
    return cap


def _state(cap):
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"],
                    ability_states=cap.get("ab"))
    st.rng = IntBasedMersenneTwister(int(SEED))
    return st


def _seed_bc(tmp_path_factory):
    """Seed BC augmente, JETABLE de ce run (jamais un chemin sous `data/`, refuse par
    `catalog_inject --out`, ni sous `logs/` -- ce serait une entree gitignoree lue hors
    `host_inputs`)."""
    import catalog_inject
    bc = tmp_path_factory.mktemp("seedbc") / ("cyrus-%s.json" % uuid.uuid4().hex[:8])
    catalog_inject.write_augmented_seed_bc(str(bc), [SUMMONER])
    return bc


@pytest.fixture(scope="module")
def env_pose(live_session, rpc, build_runner, tmp_path_factory):
    """Un runner ou `astarCyrus` peut semer ses mines, `--no-ai` (on pilote tout)."""
    bc = _seed_bc(tmp_path_factory)
    built = build_runner(SEED, extra=[
        "--seed-bc", str(bc), "--board", BOARD, "--rank", "17", "--no-ai",
        "--p-units", "%s,%s" % (SUMMONER, ALLY),
        "--a-units", "%s,%s" % (ENEMY, ENEMY_FILLER)], keep=True)
    rid = built["rid"]
    dv = _vue(rpc, rid)
    cyrus = _by_vis(dv, SUMMONER)
    assert cyrus is not None, "%s absent du plateau -- injection catalogue KO" % SUMMONER
    assert _mines(dv) == [], "des mines existent DEJA au deploiement -- montage non conforme"
    return {"rid": rid, "cyrus": _uid(cyrus), "pos": _pos(cyrus)}


@pytest.fixture(scope="module")
def sequence(env_pose, rpc):
    """Joue UNE FOIS la sequence natif (move / finish / tour suivant sans move / finish) et rejoue
    la MEME sur le port, sur un etat CHAINE. Renvoie les couples natif/port de chaque etape.

    ⚠ CHAINE, jamais recharge a mi-tour : `PositionComponent+0x88` (la position precedente) n'est
    publiee par AUCUN RPC, donc un `load_state` pris APRES le deplacement repart avec `previous`
    VIDE et le port prendrait la branche ADJACENTE. C'est un ECART DE HARNAIS nomme (residu), pas
    un ecart de port -- une simulation offline reelle part d'un etat et JOUE."""
    rid, cid = env_pose["rid"], env_pose["cyrus"]
    depart = env_pose["pos"]
    pas = {t for t in _movable(rpc, rid, cid) if hexgeo.distance(t, depart) == 1}
    assert pas, "aucun pas legal pour %s -- montage non conforme" % SUMMONER
    dest = sorted(pas)[0]

    cap = _capture(rpc, rid)
    st = _state(cap)
    r = Runner(st).install_default_handlers()

    _act(rpc, rid, {"kind": "move", "unitId": cid, "to": {"col": dest[0], "row": dest[1]}})
    r.apply(MoveUnitMessage(int(cid), (int(dest[0]), int(dest[1]))))
    apres_move = (_mines(_vue(rpc, rid)), _mines_offline(st))

    _act(rpc, rid, {"kind": "finish", "unitId": cid})
    r.apply(FinishUnitTurnMessage(unit_id=int(cid)))
    apres_finish = (_mines(_vue(rpc, rid)), _mines_offline(st))

    # Tour SUIVANT, SANS deplacement. Cote port on repart d'une capture FRAICHE : le tour a
    # tourne (turn-start, purge des flags de tour), et `HasFlag(Moved)` faux est justement la
    # premisse de la branche ADJACENTE -- aucune dependance a `previous` ici.
    _act(rpc, rid, {"kind": "endturn"}, 90)
    _act(rpc, rid, {"kind": "endturn"}, 90)
    cap2 = _capture(rpc, rid)
    st2 = _state(cap2)
    avant2 = _mines_offline(st2)
    nat_avant2 = _mines(_vue(rpc, rid))
    _act(rpc, rid, {"kind": "finish", "unitId": cid})
    Runner(st2).install_default_handlers().apply(FinishUnitTurnMessage(unit_id=int(cid)))
    neuves = (sorted(set(_mines(_vue(rpc, rid))) - set(nat_avant2)),
              sorted(set(_mines_offline(st2)) - set(avant2)))
    return {"depart": depart, "dest": dest,
            "apres_move": apres_move, "apres_finish": apres_finish, "neuves_sans_move": neuves}


def test_pose_sur_tuile_precedente(sequence):
    """`On(4 = UnitAfterMove) & OwnerIsActor & TriggeringAbilityIsNone` -> la mine atterrit sur la
    tuile QUITTEE (`CanAddUnit(PreviousTile(Owner))`), et le port la met AU MEME ENDROIT."""
    nat, port = sequence["apres_move"]
    depart, dest = sequence["depart"], sequence["dest"]
    assert nat == [depart], "le NATIF n'a pas pose sur la tuile precedente : %s" % (nat,)
    assert dest not in nat, "le natif a pose sur la tuile d'ARRIVEE -- lecture du selecteur fausse"
    assert port == nat, "port != natif apres le deplacement : %s vs %s" % (port, nat)


def test_pas_de_seconde_pose_dans_le_meme_tour(sequence):
    """La fin d'activation du MEME tour ne pose RIEN : `PreviousTile` porte deja la mine, donc
    `CanAddUnit` la rejette, `Count(tiles) == 0`, et le behaviour part sur `TriggerAbilityDelayed`
    -- dont le re-declenchement `Custom` ne trouve pas plus de tuile."""
    nat_move, _ = sequence["apres_move"]
    nat, port = sequence["apres_finish"]
    assert nat == nat_move, "le NATIF a pose une 2e mine dans le meme tour : %s" % (nat,)
    assert port == nat, "port != natif apres le finish : %s vs %s" % (port, nat)


def test_pose_adjacente_quand_l_unite_n_a_pas_bouge(sequence):
    """Un tour SANS deplacement pose a la fin d'activation, sur une tuile ADJACENTE -- et le port
    elit la MEME (meme `SortTilesByUtilityForSummon`, meme `First`)."""
    nat, port = sequence["neuves_sans_move"]
    assert len(nat) == 1, "le NATIF n'a pas pose exactement une mine : %s" % (nat,)
    assert port == nat, "port != natif sur la pose adjacente : %s vs %s" % (port, nat)


def test_chaine_pose_ecrasement_explosion_repose(live_session, rpc, build_runner,
                                                 tmp_path_factory):
    """LE SECOND CAS DISCRIMINANT, et le seul qui exerce la chaine complete.

    Un ecraseur ENNEMI a PV bas marche sur la mine : elle l'ecrase (crush `Steppable`) ET lui
    explose dessus (`AreEnemies`), il MEURT, et `RemoveUnitFromTiles` retire les deux -> la tuile
    precedente de Cyrus est LIBRE. La fin d'activation y REPOSE alors une mine, ce qui prouve
    d'un coup (a) que `HaywireMine_ResetAbility` a bien vide le sac sur `On(0x28)` AVANT la lecture
    d'`On(0x29)`, et (b) que la branche `then` du selecteur de tuiles est atteinte.

    ⚠ Un SECOND ennemi est indispensable : sans lui la bataille se termine a la mort de l'ecraseur
    et `applyAction` refuse la suite (stage != 1) -- le `finish` rendait alors une cascade VIDE et
    le verdict etait sans objet."""
    bc = _seed_bc(tmp_path_factory)
    built = build_runner(SEED, extra=[
        "--seed-bc", str(bc), "--board", BOARD, "--rank", "17", "--no-ai",
        "--p-units", "%s,%s" % (SUMMONER, ALLY),
        "--a-units", "%s,%s" % (ENEMY, ENEMY_FILLER),
        "--unit-stat", "%s:Movement=25" % ENEMY,      # PORTEE : atteindre la mine depuis son spawn
        "--hp-target", "300"])                        # PV BAS : l'ecraseur MEURT sur la mine
    rid = built["rid"]
    dv = _vue(rpc, rid)
    cyrus, ecraseur = _by_vis(dv, SUMMONER), _by_vis(dv, ENEMY)
    assert cyrus is not None and ecraseur is not None, "montage incomplet"
    cid, aid = _uid(cyrus), _uid(ecraseur)
    depart = _pos(cyrus)
    pas = {t for t in _movable(rpc, rid, cid) if hexgeo.distance(t, depart) == 1}
    assert pas, "aucun pas legal pour %s" % SUMMONER
    dest = sorted(pas)[0]

    cap = _capture(rpc, rid)
    st = _state(cap)
    r = Runner(st).install_default_handlers()

    _act(rpc, rid, {"kind": "move", "unitId": cid, "to": {"col": dest[0], "row": dest[1]}})
    r.apply(MoveUnitMessage(int(cid), (int(dest[0]), int(dest[1]))))
    n1, p1 = _mines(_vue(rpc, rid)), _mines_offline(st)
    assert n1 == [depart], "la mine n'est pas sur la tuile precedente : %s" % (n1,)

    # `aiMovableTiles` ne rend QUE les unites du joueur COURANT : l'interroger pour l'ecraseur
    # (equipe ADVERSE) rendrait un set vide et se lirait a tort comme << hors de portee >>.
    # `applyAction` ne verifie pas la propriete du `unitId` (runner.md §4) -- on joue le pas et on
    # verifie la POST-condition (la mine ecrasee, l'ecraseur mort).
    _act(rpc, rid, {"kind": "move", "unitId": aid, "to": {"col": depart[0], "row": depart[1]}})
    r.apply(MoveUnitMessage(int(aid), (int(depart[0]), int(depart[1]))))
    n2, p2 = _mines(_vue(rpc, rid)), _mines_offline(st)
    assert n2 == [], "la mine n'a pas ete ecrasee -- montage non conforme"
    assert _by_vis(_vue(rpc, rid), ENEMY) is None, \
        "l'ecraseur a SURVECU -- la tuile reste occupee, le bras ne discrimine plus"

    _act(rpc, rid, {"kind": "finish", "unitId": cid})
    r.apply(FinishUnitTurnMessage(unit_id=int(cid)))
    n3, p3 = _mines(_vue(rpc, rid)), _mines_offline(st)
    assert n3 == [depart], \
        "le NATIF n'a pas repose sur la tuile precedente LIBEREE : %s" % (n3,)
    assert [p1, p2, p3] == [n1, n2, n3], \
        "port != natif sur la chaine : port=%s natif=%s" % ([p1, p2, p3], [n1, n2, n3])
