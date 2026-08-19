"""#253 -- GARDE LIVE des masques de ciblage du module `astramilitarum` (les QUATRE abilities).

    1016 SendInTheNextWave      astraYarrick           HERO   TargetIsEnemy | TargetMatchesDynamicRule
    1028 SupremeCommander       astraCreed             HERO   CasterHasFreeAdjacentTile
                                                              | CasterIsPossibleTarget  (SELF-CAST)
    1142 MalleusRocketLauncher  astraOrdnanceBattery   MoW    CasterHas2TurnsLeft | AllowNullCasterTile
                                                              | TargetIsTile
    1143 ForwardSpotter         astraOrdnanceBattery   MoW    AllowNullCasterTile | TargetIsFriendly
                                                              | TargetHasFreeAdjacentTile
                                                              | TargetMatchesDynamicRule

CE QUE CE FICHIER GARDE, ET COMMENT
-----------------------------------
ORACLE = le NATIF, jamais une constante gelee : `abilityReason` rend le `TargetingRule` de
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` pour un triplet
(caster, ability, cible). Le test rejoue le gate OFFLINE sur le MEME etat fige et exige l'ACCORD
CODE PAR CODE -- pas seulement « refuse/accepte », le CODE de la regle rompue, qui est ce que
l'ordre de la cascade fixe.

La geometrie est CONDUITE (`--no-ai`, les deux camps deplaces) : ennemis a d=1 / d=2 / d=3 de
Yarrick, Creed a d<=2. Le SEUIL de portee de 1016 est ainsi encadre DES DEUX COTES (d=2 accepte,
d=3 refuse `TargetIsInRange`), ce qu'une seule borne ne prouverait pas.

⚠ MUNITIONS -- sans le seed BC patche, CE TEST NE MESURE RIEN pour 1142. Le seed BC partage capture
une bataille a `BC.Player.Players[*].MachineOfWarAmmo = 0` ; 1142 porte `munitionsCost = 1` -> le 4e
terme d'`IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed` est FAUX, et
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` (surcharge 4 arguments)
COURT-CIRCUITE en `broken(1 = ValidRequest)` AVANT d'entrer dans la cascade. MESURE (#253, meme
runner, meme caster, meme board, SEULE la BC change) : `casterReason` passe de 1 a 0 et les 9 lignes
de 1142 passent de `0x1` a des raisons sensees. 1143, portee par la MEME MoW mais SANS
`munitionsCost`, n'a JAMAIS ete court-circuitee -- ce n'est donc pas « caster MoW » qui court-circuite.

Le harnais (build, conduite de geometrie, patch de munitions, confrontation) est celui du probe
`probe_253_astramilitarum_targeting.py`, importe tel quel : deux copies divergeraient.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[4] / "scripts" / "python"
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_253_astramilitarum_targeting as P                      # noqa: E402
from engine.entities.pathfinding.board import Board                 # noqa: E402
from engine.runner.abilities.targeting import (get_invalid_caster_reason,   # noqa: E402
                                               get_invalid_target_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR      # noqa: E402
from engine.runner.snapshot import load_state                       # noqa: E402

BOARD = "C1_02"
SEED = "777"
AMMO = 5


@pytest.fixture(scope="module")
def scene():
    """UN runner pour les quatre abilities : le gate est une lecture PURE de l'etat fige, donc les
    quatre confrontations partagent la meme scene sans interferer."""
    try:
        sid = P._resolve_session()
    except Exception as e:                                           # noqa: BLE001
        pytest.skip("session Frida indisponible: %s" % e)
    seed_bc = P._seed_bc_with_ammo(AMMO)
    try:
        rid, state_file = P._build(sid, SEED, BOARD, seed_bc=seed_bc)
    except Exception as e:                                           # noqa: BLE001
        pytest.skip("build KO: %s" % e)
    try:
        for _ in range(P.TOURS_DE_CHAUFFE):
            P._act(sid, rid, {"kind": "endturn"}, 60)
        foes = P._drive(sid, rid)
        P._my_turn(sid, rid)
        dv = P._dv(sid, rid)
        ob = P._r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = P._r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = P._r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indisponible")
        board = Board(bg["tiles"], adjacency="native_sym")
        st = load_state(dv, ob, snap, board=board)
        yar, creed = P._by_vis(dv, P.YARRICK), P._by_vis(dv, P.CREED)
        mow = P._mow_by_vis(dv, P.BATTERY)
        if yar is None or creed is None or mow is None:
            pytest.skip("porteur absent de la scene")
        alive = [u for u in (dv.get("units") or []) if u.get("alive")]
        occupied = {board.id_at(*P._pos(u)) for u in alive if P._pos(u)[0] is not None}
        tiles = ([t for t in sorted(board.by_id) if board.walkable(t) and t not in occupied][:2]
                 + [t for t in sorted(occupied) if t is not None][:1]
                 + [t for t in sorted(board.by_id) if not board.walkable(t)][:1])
        yield {"sid": sid, "rid": rid, "st": st, "board": board, "foes": foes, "tiles": tiles,
               "units": sorted(int(u["id"]) for u in alive),
               "yarrick": int(yar["id"]), "creed": int(creed["id"]),
               "mow": int(mow["casterId"])}
    finally:
        try:
            P._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            state_file.unlink(missing_ok=True)
        except Exception:                                            # noqa: BLE001
            pass


def _confronte(scene, aid: int, caster_id: int, targets):
    """Accord CODE PAR CODE natif/port sur `targets`. Rend `(rows, n_gain)` et ECHOUE au premier
    desaccord -- avec la ligne complete, pour que le message dise QUOI diverge."""
    rows, n_gain = [], 0
    for tid in targets:
        nat = P._native(scene["sid"], scene["rid"], caster_id, aid, tid)
        port = int(get_invalid_target_reason(scene["st"], caster_id, tid, P._ability(aid, "apres")))
        avant = int(get_invalid_target_reason(scene["st"], caster_id, tid, P._ability(aid, "avant")))
        assert nat["val"] is not None, (
            "oracle natif indisponible pour %d/cible %s : %s" % (aid, tid, nat))
        assert nat["val"] != int(TR.ValidRequest) or port == nat["val"], (
            "`abilityReason` rend ValidRequest (0x1) pour %d/cible %s -> `AttackQuery` a "
            "COURT-CIRCUITE avant la cascade (ability indisponible : munitions/cooldown). "
            "L'oracle n'a pas tourne, la ligne ne prouve rien : %s" % (aid, tid, nat))
        assert port == nat["val"], (
            "ability %d, cible %s : natif=%s (%s) mais port=%s"
            % (aid, tid, hex(nat["val"]), ",".join(nat["reasons"]) or "-", hex(port)))
        n_gain += 1 if (nat["val"] != 0 and avant == 0) else 0
        rows.append((tid, nat["val"]))
    assert int(get_invalid_caster_reason(scene["st"], caster_id,
                                         P._ability(aid, "apres"))) == 0, (
        "aucun des quatre masques ne porte `CasterHasNotMoved` -> le volet CASTER du port doit "
        "rendre 0 pour %d" % aid)
    return rows, n_gain


def test_1016_send_in_the_next_wave_masque(scene):
    """`...SendInTheNextWaveAbility$$.ctor` -> `TargetingOptions..ctor(&opts, 0, <TargetingRange
    statics+0x00>, 1, 0x4002, 0,0,0)`. Le SEUIL de portee est encadre des DEUX cotes : Yarrick porte
    une arme `Range = 2` donc `onlyAdjacent = IfNotRangedCaster` retombe a faux -- d=2 ACCEPTE,
    d=3 REFUSE `TargetIsInRange`. Et l'ALLIE dans la portee isole `TargetIsEnemy` du volet portee."""
    rows, gain = _confronte(scene, 1016, scene["yarrick"], scene["units"])
    par_id = dict(rows)
    assert par_id[scene["foes"]["contact"]] == 0
    assert par_id[scene["foes"]["seuil"]] == 0, "d=2 doit etre ACCEPTE (portee d'arme = 2)"
    assert par_id[scene["foes"]["horsPortee"]] == int(TR.TargetIsInRange), \
        "d=3 doit etre REFUSE -- c'est le seuil+1 qui prouve la portee"
    assert par_id[scene["creed"]] == int(TR.TargetIsEnemy), \
        "un ALLIE dans la portee doit rompre TargetIsEnemy, pas la portee"
    assert gain > 0, "aucun cast illegal ferme -> la scene n'exerce pas le masque"


def test_1028_supreme_commander_masque(scene):
    """`...SupremeCommanderAbility$$.ctor` -> `TargetingOptions..ctor(&opts, 1, <TargetingRange
    statics+0x60>, 1, 0x208000, 0,0,0)`. SEUL des quatre a poser `isSelfCasting = 1` : caste sur
    lui-meme, Creed part sur `TargetingQuery$$GetCasterNotAddedReason` (accepte) ; toute autre cible
    tombe sur la portee NULLE (`overrideRange = 0`) -- seuil encadre a d=0 / d=1."""
    rows, gain = _confronte(scene, 1028, scene["creed"], scene["units"])
    par_id = dict(rows)
    assert par_id[scene["creed"]] == 0, "le SELF-CAST doit etre accepte (aiguillage `options+0x00`)"
    assert par_id[scene["yarrick"]] == int(TR.TargetIsInRange), \
        "un allie a d=1 doit etre REFUSE : la portee est NULLE (RANGE_SELF)"
    assert gain > 0


def test_1142_malleus_rocket_launcher_masque(scene):
    """`...MalleusRocketLauncherAbility$$.ctor` -> `TargetingOptions..ctor(&opts, 0, <TargetingRange
    statics+0x48>, 1, 0x10000040000040, 0,0,0)`. Cast TILE-target : la seule regle CIBLE portee est
    `TargetIsTile`, qui refuse une tuile NON MARCHABLE en rendant le litteral `1`
    (`TargetingRule.ValidRequest`, que le natif REUTILISE comme code de refus). `useWholeBoard` ->
    AUCUN test de portee, y compris depuis une MoW SANS position."""
    cibles = scene["tiles"] + scene["units"]
    rows, gain = _confronte(scene, 1142, scene["mow"], cibles)
    par_id = dict(rows)
    unwalk = [t for t in scene["tiles"] if not scene["board"].walkable(t)]
    if unwalk:
        assert par_id[unwalk[0]] == int(TR.ValidRequest), \
            "une tuile NON MARCHABLE doit rompre `TargetIsTile` (code litteral 1)"
        assert gain > 0
    assert any(v == 0 for v in par_id.values()), \
        "aucune cible acceptee -> l'oracle est court-circuite, la mesure ne vaut rien"


def test_1143_forward_spotter_masque(scene):
    """`...ForwardSpotterAbility$$.ctor` -> `TargetingOptions..ctor(&opts, 0, <TargetingRange
    statics+0x48>, 1, 0x40000422, 0,0,0)`. Cible = une unite ALLIEE (i2 : « in a hex adjacent to the
    targeted friendly unit »). Les TUILES VIDES rompent `TargetIsUnit` -- le PREAMBULE de domaine de
    la cascade, porte avec ce lot ; la tuile OCCUPEE, elle, est ACCEPTEE parce que le natif la resout
    en son occupant (`UnitExtensions$$GetUnit`)."""
    cibles = scene["units"] + scene["tiles"]
    rows, gain = _confronte(scene, 1143, scene["mow"], cibles)
    par_id = dict(rows)
    for lab in ("contact", "seuil", "horsPortee"):
        assert par_id[scene["foes"][lab]] == int(TR.TargetIsFriendly), \
            "un ENNEMI doit rompre TargetIsFriendly (%s)" % lab
    assert par_id[scene["yarrick"]] == 0 and par_id[scene["creed"]] == 0, \
        "les ALLIES doivent etre acceptes"
    vides = [t for t in scene["tiles"]
             if scene["board"].walkable(t) and scene["st"].unit_at(scene["board"].coord(t)) is None]
    if vides:
        assert par_id[vides[0]] == int(TR.TargetIsUnit), \
            "une tuile VIDE doit rompre la tete de domaine TargetIsUnit"
    assert gain > 0
