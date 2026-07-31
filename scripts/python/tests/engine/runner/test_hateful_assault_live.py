"""case-366-r1 -- `HatefulAssault` (1038) et son MARQUEUR `HatefulAssault_AlreadyAttacked` (1175).

> QUALIFICATION D'ENUM : `1175` ici = `EffectType.HatefulAssault_AlreadyAttacked` (0x497) ; `1038` =
> `TriggeredAbilityType.HatefulAssault` (0x40e). Deux enums DISTINCTS -- ne pas les confondre avec un
> `ActiveAbilityType` de meme valeur.

L'axe de cet effet est la DUREE, pas une magnitude. Trois fautes possibles, toutes SILENCIEUSES (ni
erreur, ni test de degat rouge), et ce fichier en pose une garde chacune :

  1. le trigger ne fire PAS       -> l'ennemi qui s'ecarte ne prend rien ;
  2. le marqueur n'est PAS pose   -> il reprend l'attaque a CHAQUE deplacement du meme tour ;
  3. le marqueur n'est PAS retire -> il n'est plus JAMAIS frappe, pour le reste de la bataille.

CE QUE LE LIVE PROUVE, ET CE QU'IL NE PEUT PAS PROUVER (limite du CAPTEUR, mesuree) :
`IdunBattle.Operations.AddEffectOperation$$AddNewEffect` ecrit `EffectComponent` +0x10/+0x14/+0x6c
(et +0x5d/+0x60/+0x64 si `turns` a une valeur) mais **n'ecrit JAMAIS `IsActive @+0x5c`** : un effet
frais nait INACTIF, et `readEffectsByUnit` (la projection de `decisionView.units[].effects`) FILTRE
les inactifs. Le marqueur est donc INVISIBLE de cette vue au moment ou il est pose -- comme 1197
avant lui (case-231). Le capteur qui le voit est le COMPTE D'ENTITES-EFFET du plateau
(`observeBattle.counts.effects`), qui ne filtre rien. C'est lui l'arbitre de la pose ici ; le
`decisionView` seul rendrait un zero qu'on lirait a tort comme une absence.

MONTAGE : `blackTerminator` <<Angrax>> cote ADVERSE (on ne commande que sa propre equipe, or c'est
l'unite qui BOUGE qu'il faut piloter). PV joueur montes pour survivre aux 2 coups Power et rejouer
le scenario. Angrax porte `TeleportStrike` : il est NON CIBLABLE tant qu'il n'a pas agi, ce qui
ETEINT le gate `IsAdjacent(..., OnlyAliveAndTargetable)` -- le montage attend qu'il soit pose.

ASCII only. Dispose SES runners.
"""
from __future__ import annotations

import pytest

import probe_1175_live_marker as P
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.components import PositionComponent
from engine.runner.operations.effects import AddEffectOperation
from engine.runner.operations.triggers.base import TriggerEvent
from engine.runner.operations.triggers.dispatch.core import collect_effect_triggers
from engine.runner.operations.triggers.loki.hateful_assault import HatefulAssaultAttackAbility
from engine.runner.snapshot import load_state

MARKER = int(EffectType.HatefulAssault_AlreadyAttacked)      # 0x497 = 1175
CARRIER = "blackTerminator"
P_UNITS = "templSwordBrother,ultraTitus"
A_UNITS = "blackTerminator,necroWarden"
MAX_STAGING_TURNS = 12


def _pre_move_event(mover: int, dest=None) -> TriggerEvent:
    """`On(PreUnitMove = 0x1f)` tel que `MoveUnitOperation$$EvaluatePreMoveTriggers` le publie :
    `caster = actor = target = le mover`, et la DESTINATION en `casterTiles`/`targetTiles`."""
    return TriggerEvent(int(EventTriggerType.PreUnitMove), int(mover), int(mover),
                        ranged=False, profile=None, dest_tile=dest)


@pytest.fixture(scope="module")
def hateful_case(live_session, tmp_path_factory):
    """UN runner pour tout le fichier. On amene une unite A NOUS au contact d'Angrax, on capture
    l'etat AVANT l'ecart, puis on joue l'ecart EN LIVE et on capture l'APRES."""
    s = live_session
    state_file = tmp_path_factory.mktemp("hateful") / "runner.json"
    rid = P.build(str(state_file), "MC1_67", "777", P_UNITS, A_UNITS)
    try:
        sn = P.snap(s, rid)
        angrax = next((uid for uid, u in sn["units"].items() if u["visualId"] == CARRIER), None)
        if angrax is None:
            pytest.fail("montage KO : %s absent du runner (roster : %s)"
                        % (CARRIER, sorted(u["visualId"] for u in sn["units"].values())))
        my_player = next((u["owner"] for u in sn["units"].values() if u.get("ctrl")), None)

        mover, before, tile_out = None, None, None
        witness = []            # cout des pas d'APPROCHE (aucun ne part d'un hex adjacent)
        for _ in range(MAX_STAGING_TURNS):
            sn = P.snap(s, rid)
            au = sn["units"].get(angrax) or {}
            mine = [uid for uid, u in sn["units"].items()
                    if u.get("ctrl") and u["alive"] and u["hasAction"]]
            if sn["currentPlayer"] != my_player or not mine:
                P.endturn(s, rid)
                continue
            deep = P.has_eff(au, P.TELEPORTING_IN)
            adj = [uid for uid in mine
                   if P.hexdist((sn["units"][uid] or {}).get("pos"), au.get("pos")) == 1]
            if adj and not deep:
                cand = adj[0]
                out = [t for t in P.movable(s, rid, cand)
                       if P.hexdist({"col": t[0], "row": t[1]}, au.get("pos")) >= 2]
                if out:
                    mover, before, tile_out = cand, dict(sn["units"][cand]), out[0]
                    break
            # approche (ce move NE part PAS d'un hex adjacent -> bras temoin par construction)
            best, bestd = None, 99
            for uid in mine:
                for (c, r) in P.movable(s, rid, uid):
                    d = P.hexdist({"col": c, "row": r}, au.get("pos"))
                    if d < bestd:
                        best, bestd = (uid, c, r), d
            if best is not None and bestd < 99:
                hp0 = int((sn["units"][best[0]] or {}).get("hp") or 0)
                P.move(s, rid, best[0], best[1], best[2])
                hp1 = int((P.snap(s, rid)["units"].get(best[0]) or {}).get("hp") or 0)
                witness.append((int(best[0]), bestd, hp0 - hp1))
            P.endturn(s, rid)

        if mover is None:
            pytest.fail("montage KO : aucune unite n'a pu se placer au contact d'Angrax en %d tours"
                        % MAX_STAGING_TURNS)

        # ETAT AVANT L'ECART -- c'est LUI que le port doit juger (le mover est encore adjacent).
        bg = P.rpc(s, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        dv_before = P.rpc(s, "decisionView", {"runnerId": rid, "allAbilities": True}, 90)
        ob_before = P.rpc(s, "observeBattle", {"runnerId": rid}, 60)
        cs_before = P.rpc(s, "combatSnapshot", {"runnerId": rid}, 90)
        n_before = int(((ob_before.get("counts") or {}).get("effects")) or 0)

        res = P.move(s, rid, mover, tile_out[0], tile_out[1], events=True)
        sn_after = P.snap(s, rid)
        n_after = P.eff_count(s, rid)

        # 2e ECART, un tour PLUS TARD, par la MEME unite depuis le meme hex adjacent. C'est le seul
        # observable qui separe « marqueur retire » de « marqueur A VIE » : le compte GLOBAL
        # d'entites-effet ne peut pas servir d'horloge (Angrax porte `LetTheGalaxyBurn`, qui pose une
        # tuile `DespoiledGround` a chaque attaque, et des effets de tuile naissent au fil des tours).
        dmg2 = None
        for _ in range(2 * MAX_STAGING_TURNS):
            sk = P.snap(s, rid)
            ak, uk = sk["units"].get(angrax) or {}, sk["units"].get(mover) or {}
            if sk["currentPlayer"] != my_player or not uk.get("hasAction") or not uk.get("alive"):
                P.endturn(s, rid)
                continue
            if P.hexdist(uk.get("pos"), ak.get("pos")) == 1:
                out2 = [t for t in P.movable(s, rid, mover)
                        if P.hexdist({"col": t[0], "row": t[1]}, ak.get("pos")) >= 2]
                if out2:
                    hp0 = int(uk.get("hp") or 0)
                    P.move(s, rid, mover, out2[0][0], out2[0][1])
                    dmg2 = hp0 - int((P.snap(s, rid)["units"].get(mover) or {}).get("hp") or 0)
                    break
            else:
                back = [t for t in P.movable(s, rid, mover)
                        if P.hexdist({"col": t[0], "row": t[1]}, ak.get("pos")) == 1]
                if back:
                    P.move(s, rid, mover, back[0][0], back[0][1])
            P.endturn(s, rid)

        yield {
            "dmg2": dmg2, "witness": witness,
            "sid": s, "rid": rid, "angrax": angrax, "mover": mover, "board": board,
            "dv_before": dv_before, "ob_before": ob_before, "cs_before": cs_before,
            "hp_before": int(before.get("hp") or 0),
            "hp_after": int((sn_after["units"].get(mover) or {}).get("hp") or 0),
            "eff_before": n_before, "eff_after": n_after,
            "tile_out": tile_out, "move_res": res, "sn_after": sn_after,
        }
    finally:
        try:
            P.rpc(s, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass


def _state(case):
    st = load_state(case["dv_before"], case["ob_before"], case["cs_before"])
    st.board = case["board"]
    return st


# ------------------------------------------------------------------ (1) le trigger FIRE (LIVE)

def test_live_opportunity_attack_hits_the_unit_that_steps_away(hateful_case):
    """L'ennemi adjacent a Angrax qui S'ECARTE encaisse -- c'est le fait observable de 1038.

    Le HP est l'oracle : aucun autre canal ne frappe ce mover a cet instant (le tour adverse n'est
    pas joue, et le pas d'approche des tours precedents n'a rien coute -- cf. le bras temoin)."""
    dmg = hateful_case["hp_before"] - hateful_case["hp_after"]
    assert dmg > 0, ("le mover n'a RIEN encaisse en s'ecartant d'un hex adjacent a Angrax : "
                     "HatefulAssault n'a pas fire (hp %d -> %d)"
                     % (hateful_case["hp_before"], hateful_case["hp_after"]))


def test_live_approach_costs_nothing(hateful_case):
    """ATTRIBUTION -- BRAS TEMOIN LIVE. Les pas d'APPROCHE (aucun ne PART d'un hex adjacent, y
    compris celui qui ARRIVE au contact) doivent coûter ZERO. C'est ce qui transforme le « degat > 0 »
    du test precedent en « SEUL le move qui part d'un hex adjacent coute » -- sans lui, n'importe quel
    canal de degat rendrait ce fichier vert.

    ⚠ LIMITE DU MONTAGE, mesuree : ce bras n'est propre que si le camp adverse n'a AUCUNE unite a
    tir d'opportunite. Sur `C1_14`/31337 avec `eldarRanger` en face, une approche a d=1 coute 4197
    (l'overwatch, effet 1009) -- et ce n'est PAS 1038. D'ou `A_UNITS` melee ici."""
    if not hateful_case["witness"]:
        pytest.fail("montage KO : aucun pas d'approche enregistre")
    bad = [w for w in hateful_case["witness"] if w[2] != 0]
    assert not bad, ("des pas d'approche ont coute des PV %s -- un autre canal frappe le mover, "
                     "l'attribution du bras pose n'est plus etablie" % bad)


def test_live_marker_entity_is_created(hateful_case):
    """La POSE de 1175, mesuree par le compte d'ENTITES-EFFET -- pas par `decisionView`.

    `AddNewEffect` n'ecrit pas `IsActive @+0x5c` (l'effet nait inactif) et la projection filtre les
    inactifs : un marqueur absent de `decisionView.units[].effects` n'est PAS une preuve d'absence.
    Le compte d'entites, lui, ne filtre rien."""
    assert hateful_case["eff_after"] > hateful_case["eff_before"], (
        "aucune entite-effet creee par l'attaque d'opportunite (%d -> %d) : le `AddEffect(0x497)` "
        "du behaviour natif n'a pas eu lieu"
        % (hateful_case["eff_before"], hateful_case["eff_after"]))


def test_live_attack_repeats_on_a_later_turn(hateful_case):
    """LE RETRAIT, mesure par le COMPORTEMENT : la MEME unite, ecartee A NOUVEAU du meme hex un tour
    plus tard, encaisse ENCORE. Zero ici = le marqueur est reste colle et 1038 est ETEINT pour cette
    unite jusqu'a la fin de la bataille -- la faute n°3, invisible de toute autre facon.

    ⚠ CE QUE CE BRAS NE SEPARE PAS : `On(TurnEnd)` de `On(PhaseEnd)`. Entre la pose (mon tour) et le
    prochain deplacement de cette unite (mon tour suivant), le jeu franchit LES DEUX dates. Le regime
    qui les separerait exige un deplacement supplementaire APRES la fin du tour d'equipe -- hors de
    ce montage. C'est mesure, pas suppose (cf. `case-366-r1-hateful-assault-marker.md` §5)."""
    if hateful_case["dmg2"] is None:
        pytest.fail("montage KO : la meme unite n'a pas pu se re-ecarter d'un hex adjacent")
    assert hateful_case["dmg2"] > 0, (
        "2e ecart au tour ulterieur : degat=%d -> le marqueur 1175 n'a PAS ete retire"
        % hateful_case["dmg2"])


# ------------------------------------------------------------------ (2) les GATES du port

def test_port_trigger_matches_on_the_same_live_state(hateful_case):
    """Sur l'etat LIVE d'AVANT l'ecart, le port dit OUI -- meme verdict que le natif (test 1)."""
    st = _state(hateful_case)
    trg = HatefulAssaultAttackAbility(int(hateful_case["angrax"]))
    dest = (hateful_case["tile_out"][0], hateful_case["tile_out"][1])
    assert trg.matches(st, _pre_move_event(hateful_case["mover"], dest)) is True


def test_port_marker_gates_the_second_trigger(hateful_case):
    """`NOT HasEffect(Actor, 0x497)` -- une unite DEJA marquee ne redeclenche pas.

    C'est la faute n°2 : sans ce gate, une unite qui bouge deux fois dans le meme tour prendrait
    l'attaque d'opportunite deux fois. On pose le marqueur par l'Operation REELLE (pas un flag
    bricole) pour que le gate soit exerce tel qu'il tourne en production."""
    st = _state(hateful_case)
    trg = HatefulAssaultAttackAbility(int(hateful_case["angrax"]))
    dest = (hateful_case["tile_out"][0], hateful_case["tile_out"][1])
    assert trg.matches(st, _pre_move_event(hateful_case["mover"], dest)) is True
    AddEffectOperation.execute(st, source=int(hateful_case["mover"]),
                               target=int(hateful_case["mover"]), effect_type=MARKER,
                               name=EffectType(MARKER).name, duration_override=None)
    assert trg.matches(st, _pre_move_event(hateful_case["mover"], dest)) is False, (
        "le marqueur 1175 ne bloque PAS le second declenchement")


def test_port_no_trigger_when_destination_is_the_current_tile(hateful_case):
    """`NOT AreEqual(Tiles(Actor), <tuiles @DSLSelectors+0x78>)` -- un « deplacement » vers la tuile
    COURANTE n'est pas un deplacement. Le canal `dest_tile` du `TriggerEvent` est ce qui rend ce
    terme evaluable ; sans lui il n'y aurait rien a comparer."""
    st = _state(hateful_case)
    trg = HatefulAssaultAttackAbility(int(hateful_case["angrax"]))
    e = st.get_entity(int(hateful_case["mover"]))
    pc = e.get_component(PositionComponent)
    assert trg.matches(st, _pre_move_event(hateful_case["mover"], (pc.col, pc.row))) is False


def test_port_no_trigger_for_a_non_adjacent_mover(hateful_case):
    """`IsAdjacent(Owner, Actor)` -- BRAS TEMOIN. Une unite qui bouge SANS partir d'un hex adjacent
    a Angrax ne doit ni etre frappee ni etre marquee. Sans ce bras, une pose observee ne prouve pas
    que c'est CE mecanisme qui l'a produite."""
    st = _state(hateful_case)
    trg = HatefulAssaultAttackAbility(int(hateful_case["angrax"]))
    far = [uid for uid in st.entities
           if int(uid) not in (int(hateful_case["angrax"]), int(hateful_case["mover"]))]
    ang = st.get_entity(int(hateful_case["angrax"])).get_component(PositionComponent)
    tested = 0
    for uid in far:
        e = st.get_entity(int(uid))
        pc = e.get_component(PositionComponent)
        if pc is None:
            continue
        at = st.board.id_at(pc.col, pc.row)
        an = st.board.id_at(ang.col, ang.row)
        if at is None or an is None or at in set(st.board.neighbours(an)):
            continue                                   # adjacent -> ce n'est pas le bras temoin
        tested += 1
        assert trg.matches(st, _pre_move_event(uid, (pc.col, pc.row + 1))) is False, (
            "unite %s NON adjacente a Angrax et pourtant declenchante" % uid)
    if not tested:
        pytest.fail("montage KO : aucune unite non-adjacente pour le bras temoin")


# ------------------------------------------------------------------ (3) l'EXPIRATION

def test_port_marker_is_removed_at_turn_end(hateful_case):
    """`UntilOfEndTurnEffect$$CreateRemoveEffectTrigger` = `On(TurnEnd)` SANS predicat ->
    `BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(<l'instance>)`.

    C'est la faute n°3 : le marqueur n'a AUCUN timer (`DefaultAmountOfRounds(1175)` rend un Nullable
    VIDE, et le poseur passe un `turns` vide) -- il est PERMANENT tant que ce trigger ne tourne pas.
    Un port qui l'oublierait eteindrait HatefulAssault pour le reste de la bataille."""
    st = _state(hateful_case)
    mover = int(hateful_case["mover"])
    AddEffectOperation.execute(st, source=mover, target=mover, effect_type=MARKER,
                               name=EffectType(MARKER).name, duration_override=None)
    inst = [e for e in st.effects.by_unit.get(mover, []) if e.effect_type == MARKER]
    assert inst, "le marqueur n'a pas ete pose par l'Operation"
    assert inst[0].remaining_turns is None, (
        "1175 ne doit porter AUCUN timer (remaining=%s) : sa duree est un TRIGGER"
        % inst[0].remaining_turns)

    trg = [t for t in collect_effect_triggers(st)
           if t.effect_type == MARKER and int(t.owner_id) == mover]
    assert trg, "aucun EFFECT_TRIGGERS[1175] collecte sur le porteur"
    assert trg[0].event_id == int(EventTriggerType.TurnEnd)
    ev = TriggerEvent(int(EventTriggerType.TurnEnd), -1, -1, ranged=False, profile=None)
    assert trg[0].matches(st, ev) is True, "le trigger natif n'a AUCUN predicat -- il doit matcher"
    trg[0].execute_behaviour(st, ev)
    assert not st.effects.has_effect(mover, effect_type=MARKER), (
        "1175 survit au TurnEnd -> marqueur A VIE, HatefulAssault ne refrapperait jamais %s" % mover)


def test_port_marker_gate_reopens_after_removal(hateful_case):
    """Boucle complete : marque -> gate ferme -> TurnEnd -> gate ROUVERT. C'est l'invariant de
    comportement (« une attaque d'opportunite par ennemi et par tour »), pas un detail d'etat."""
    st = _state(hateful_case)
    mover = int(hateful_case["mover"])
    trg = HatefulAssaultAttackAbility(int(hateful_case["angrax"]))
    dest = (hateful_case["tile_out"][0], hateful_case["tile_out"][1])
    assert trg.matches(st, _pre_move_event(mover, dest)) is True
    AddEffectOperation.execute(st, source=mover, target=mover, effect_type=MARKER,
                               name=EffectType(MARKER).name, duration_override=None)
    assert trg.matches(st, _pre_move_event(mover, dest)) is False
    for t in collect_effect_triggers(st):
        if t.effect_type == MARKER and int(t.owner_id) == mover:
            t.execute_behaviour(st, TriggerEvent(int(EventTriggerType.TurnEnd), -1, -1,
                                                 ranged=False, profile=None))
    assert trg.matches(st, _pre_move_event(mover, dest)) is True, (
        "le gate ne se rouvre pas apres le retrait du marqueur")
