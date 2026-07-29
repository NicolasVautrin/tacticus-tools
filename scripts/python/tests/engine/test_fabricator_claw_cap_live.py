"""GARDE #242 -- `FabricatorClawArrayPlaybook` (1006, `necroSpyder`/Aleph-Null) : le CAP amis.

CE QUE CETTE GARDE PROTEGE. Le corps commun
`IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext`
fait `n = Min(count(<amis filtres>), vtbl+0x228)` puis ne somme que les `n` premiers.
`FabricatorClawArrayPlaybook` override ce slot a **1** : son groupe `methodPointers` est
`[.ctor, GetAdjacentFriendUtility, <ret 0>, <ret 1>, FilterAdjacentFriends]`, exactement le meme que
`SpiritualLeaderPlaybook` (memes deux corps fondus par l'ICF -- `33 c0 c3` = `xor eax,eax ; ret` et
`b8 01 00 00 00 c3` = `mov eax,1 ; ret` -- aux memes positions relatives, +0x10 et +0x18 du `.ctor`).
Le terme vaut donc le poids BC des qu'il y a UN ami retenu, et **pas** 30 x n. Cette garde tombe si
le cap disparait (2 amis mecaniques adjacents -> 60, 4 -> 120 : c'est ce que le port rendait avant
ce commit).

POURQUOI ELLE N'EXISTAIT PAS. #57i et #193c n'ont exerce que `n <= 1` sur ce playbook, regime ou le
cap est TRANSPARENT -- aucun de leurs verdicts ne le contredisait ni ne le confirmait. Il fallait un
montage a >= 2 amis Mechanical autour d'une MEME tuile candidate, que la geometrie de spawn ne donne
jamais : `_drive_cluster` (`probe_242_fabricator_claw_cap.py`) DEPLACE les allies sur des voisins
distincts d'une tuile atteignable par le carrier, puis termine leur tour.

MESURE FONDATRICE (`probe_242_fabricator_claw_cap.py`, decomposition
`X = Tile(7) - Elevation - TileEffects` aux hooks EXISTANTS de `scorer-damage-trace`, deux couples
board/seed, seed BC SANS reliques) -- `X_nat` par (nMech, nRep) ou `nRep` = amis Mechanical **et**
`CanBeRepaired` :

    (0,0) -> 0    (1,0) -> 0    (1,1) -> 30    (2,1) -> 30    (2,2) -> 30    (4,3) -> 30

`X_nat` est PLAT de 1 a 3 amis retenus : le cap mord et vaut 1.

CE QUE CETTE GARDE NE COUVRE PAS -- le second gate du filtre natif
(`IBattleQuery.<slot 0x2e = CanBeRepaired>`, cf. la docstring de `FabricatorClawArrayPlaybook`) :
`(1,0) -> X_nat = 0` alors que le port rend 30. Le porter demande `hp`/`hp_max` dans les
`friend_units` du `tile_leaf_ctx`, hors perimetre de #242. Les assertions ci-dessous portent donc sur
la loi du PORT (`terme == w x [au moins un ami Mechanical adjacent]`), pas sur l'accord avec le natif
dans le regime ou ce gate mord.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

ABILITY = 1006                                     # TriggeredAbilityType.FabricatorClawArray
CARRIER = "necroSpyder"
BC_KEY = "FABRICATORCLAWARRAY_AdjacentFriend"      # `Utilities.Default.TriggeredAbilities[..]` = 30
MECH_TRAIT = "Mechanical"                          # UnitTrait.Mechanical = 5 (`HasTrait(u, 5)`)

# Roster : le carrier + QUATRE allies Mechanical. `admecMarshall` en est EXCLU a dessein -- son
# active `DoctrinaImperatives` (1118) allume `AttractMechanicalsUtility` (feuille 57, +10 par tuile
# voisine de lui), qui se superposerait au terme mesure.
_ROSTER = ["--hp-target", "100000", "--hp-player", "100000",
           "--p-units", "necroSpyder,admecDestroyer,admecManipulus,admecRuststalker,necroDestroyer",
           "--a-units", "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"]

CASES = [("MC1_67", "777"), ("C4_09", "31337")]


@pytest.fixture(scope="module", params=CASES, ids=lambda c: "%s-%s" % (c[0], c[1]))
def claw_case(request, rpc, build_runner, tmp_path_factory):
    """Etat de decision d'une activation du carrier ou >= 2 amis Mechanical bordent une candidate.

    On ne SUBIT pas la geometrie : tant que le carrier a son action, on regroupe les allies autour
    d'une tuile qu'il peut atteindre (`_drive_cluster`) et on termine leur tour, si bien que l'IA
    n'a plus que lui a activer. Le regroupement est tente des DEUX cotes (allie active OU carrier
    active) -- `aiStepDryRun` ne mute pas, donc on peut deplacer les allies puis redemander la
    decision du carrier."""
    from probe_242_fabricator_claw_cap import _drive_cluster, _seed_bc_montage
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene

    board, seed = request.param
    seed_bc = _seed_bc_montage(tmp_path_factory.mktemp("a242") / "seed-bc.json")
    rid = build_runner(seed, extra=list(_ROSTER) + ["--seed-bc", str(seed_bc)], board=board)["rid"]

    def r(m, b, t=90):
        return rpc(m, b, t)

    vis = {u.get("id"): u.get("visualId")
           for u in (r("decisionView", {"runnerId": rid, "maxRank": 1}, 180).get("units") or [])}
    carrier_id = next((k for k, v in vis.items() if v == CARRIER), None)
    assert carrier_id is not None, "%s absent du runner (roster/pool a re-etalonner)" % CARRIER

    def drive(dv, done):
        cu = next((u for u in (dv.get("units") or []) if u.get("id") == carrier_id), None)
        if cu is None or not cu.get("alive") or not cu.get("hasAction"):
            return 0
        allies = [u.get("id") for u in (dv.get("units") or [])
                  if u.get("ctrl") and u.get("alive") and u.get("hasAction")
                  and u.get("id") != carrier_id]
        if not allies or done:
            return 0
        return _drive_cluster(lambda m, b, t=90: r(m, b, t), rid, carrier_id, allies)

    driven = set()
    for step in range(60):
        dry = r("aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            pytest.skip("trajectoire native epuisee au pas %d (%s)" % (step, dry.get("error")))
        uid = dry.get("activatedUnitId")
        dv = r("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
        if (me is not None and me.get("ctrl")) and drive(dv, step in driven):
            driven.add(step)
            continue
        if uid == carrier_id:
            mov = r("aiMovableTiles", {"runnerId": rid}, 90)
            mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
            wt = W.load()
            pred = _scene.build_predictor(lambda m, b, t: r(m, b, t), rid)
            ctx = _ai_ctx.build(lambda m, b, t: r(m, b, t), rid, dv, mov_by_unit, uid, wt, pred)
            case = {"rid": rid, "step": step, "uid": uid, "ctx": ctx,
                    "visual_id": (me or {}).get("visualId")}
            if max(n for (_, n) in _terms_by_tile(case).values()) >= 2:
                return case
        for m in ((dry.get("action") or {}).get("messages") or []):
            cls = m.get("cls")
            if cls == "MoveUnitMessage":
                act = {"kind": "move", "unitId": m["unitId"],
                       "to": {"col": m["to"]["col"], "row": m["to"]["row"]}}
            elif cls == "ActiveAbilityMessage":
                act = {"kind": "ability", "casterId": m["casterId"],
                       "targetId": m.get("targetId"), "abilityType": m["abilityType"]}
            elif cls == "FinishUnitTurnMessage":
                act = {"kind": "finish", "unitId": m["unitId"]}
            else:
                continue
            r("applyAction", {"runnerId": rid, "action": act}, 90)
    pytest.skip("aucune activation du carrier a >=2 amis Mechanical adjacents en 60 pas "
                "(board=%s seed=%s)" % (board, seed))


def _terms_by_tile(case):
    """{tuile: (terme du playbook 1006, #amis Mechanical a distance 1)} sur les candidates."""
    import hexgeo
    from engine.utilities.tile import tile_leaf_ctx
    from engine.playbook.adjacent_unit_preference import load_playbook
    pb = load_playbook(ABILITY)
    assert pb is not None, "ability %d absente de TRIGGERED_MOVE_PLAYBOOKS" % ABILITY
    ctx = case["ctx"]
    lc = tile_leaf_ctx(ctx)
    out = {}
    for t in (ctx.action_tiles or []):
        n = sum(1 for u in (lc.get("friend_units") or ())
                if hexgeo.distance(t, u["pos"]) == 1 and MECH_TRAIT in (u.get("traits") or ()))
        out[t] = (pb.calculate_movement_utility_in_steps(t, lc, ctx.wt), n)
    return out


def test_case_still_activates_the_carrier(claw_case):
    """Le montage n'a de sens que si le pas active bien Aleph-Null."""
    assert claw_case["visual_id"] == CARRIER, (
        "pas %d : porteur attendu %s, active %s -- trajectoire derivee, montage a re-etalonner"
        % (claw_case["step"], CARRIER, claw_case["visual_id"]))


def test_kit_source_carries_the_triggered_ability(claw_case):
    """GARDE DE SOURCE : sans elle le playbook peut etre au registre et n'etre JAMAIS appele."""
    from engine.utilities.tile import tile_leaf_ctx
    kit = tile_leaf_ctx(claw_case["ctx"]).get("unit_triggered_abilities") or []
    assert ABILITY in kit, (
        "pas %d (%s) : ability %d absente du kit declenche %r -- le playbook ne sera JAMAIS appele"
        % (claw_case["step"], claw_case["visual_id"], ABILITY, kit))


def test_bc_key_is_non_zero(claw_case):
    """Le poids lu par `IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$
    GetAdjacentFriendUtility` doit exister : a 0 le terme meurt sans le moindre signal."""
    w = claw_case["ctx"].wt.sub("TriggeredAbilities", BC_KEY)
    assert w > 0, (
        "la cle BC %r rend %r -- disparue de `Utilities.Default.TriggeredAbilities` "
        "(BC re-dumpee ? build change ?)" % (BC_KEY, w))


def test_montage_exercises_more_than_one_adjacent_mechanical(claw_case):
    """Sans une candidate a >= 2 amis Mechanical adjacents, le cap ne peut pas etre mis en defaut :
    la garde suivante passerait A VIDE. C'est exactement ce qui manquait a #57i/#193c."""
    counts = sorted({n for (_, n) in _terms_by_tile(claw_case).values()})
    assert 0 in counts and max(counts) >= 2, (
        "pas %d (%s) : #amis Mechanical adjacents par candidate = %r -- il faut au moins une tuile "
        "a 0 et une a >=2 pour exercer le cap (le DRIVE de positions a-t-il echoue ?)"
        % (claw_case["step"], claw_case["visual_id"], counts))


def test_term_is_capped_at_one_adjacent_mechanical(claw_case):
    """LE COEUR DE #242 : le terme vaut le poids BC des qu'il y a UN ami retenu, et PAS PLUS.

    `vtbl+0x228 = 1` (`Min(count, 1)`) : deux candidates a 1 et a 4 amis Mechanical portent le MEME
    terme. Un port qui somme (comportement d'avant ce commit) rendrait 30 / 60 / 120 -- cette
    assertion tombe. Un port sans l'entree au registre rendrait 0 partout : elle tombe aussi."""
    w = claw_case["ctx"].wt.sub("TriggeredAbilities", BC_KEY)
    tv = _terms_by_tile(claw_case)
    bad = {t: (round(v, 4), n) for t, (v, n) in tv.items()
           if abs(v - (w if n >= 1 else 0.0)) > 1e-6}
    assert not bad, (
        "pas %d (%s) : terme != %g x [au moins 1 ami Mechanical adjacent] sur %r. Le cap "
        "`vtbl+0x228` de `FabricatorClawArrayPlaybook` vaut 1 (corps trivial `mov eax,1 ; ret`, lu "
        "au bloc methodPointers du PE) : le terme NE SOMME PAS les amis. (terme, n) par tuile = %r"
        % (claw_case["step"], claw_case["visual_id"], w, sorted(bad),
           {t: (round(v, 4), n) for t, (v, n) in tv.items()}))
