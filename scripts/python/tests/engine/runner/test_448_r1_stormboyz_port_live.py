"""#448-r1 -- CONFRONTATION LIVE du port de `StormboyzStrike_FallbackAbility` / `_MissAbility`.

Le montage est celui, deja etabli, de #425 : greffe du passif sur `orksNob` (le seul porteur natif,
`orksNpc6Stormboy`, est npc et n'a aucun summoner -> `case-92` §5bis, recours 3), board `MC1_67`,
seed 777, **et un ALLIE, obligatoire** -- avec le seul porteur, son `finish` cloture le tour d'equipe
et la marque `turns: 1` est consommee dans le meme `applyAction`.

CE QUE CE FICHIER CONFRONTE, et pourquoi c'est adversarial
-----------------------------------------------------------
Le pas mesure est UN `applyAction {kind:"finish"}` sur le porteur, encore hors plateau sous
`1140 StormboyzStrike_TeleportingIn`. Ce seul pas fait travailler, dans cet ordre, TOUT le kit :

    On(0x28 = UnitFinishedTurn)  ->  Fallback.CreateTrigger
      MoveUnit(Caster, <sel>)    ->  MoveUnitOperation  ->  On(0x1f = PreUnitMove)
                                       ->  Miss.CreateTrigger
                                             Maybe(chance = 20)  ->  OverrideUnitMovementTarget
                                             RemoveEffect(1140)
                                             TriggerAbility(FullThrottle) -> Maybe(30) -> Kill
      AddEffect(1179, <le MEME noeud sel, RE-EVALUE>, turns: 1)
      If(Count(Tiles(Caster)) == 0, RemoveEffect(1140) & Kill(Caster))

Trois observables INDEPENDANTS en sortent -- la position d'ATTERRISSAGE, la tuile MARQUEE, et la
consommation du PRNG -- et le port doit les rendre tous les trois.

L'ALIGNEMENT DU PRNG est ce qui rend la confrontation exacte au lieu d'approximative : le kit tire
`Maybe(20)` (le miss), puis `Maybe(30)` (FullThrottle), plus un `PickRandomly` en cas de miss. Sans
alignement, un desaccord de tuile serait indiscernable d'un tirage different. On seede donc l'etat
offline avec le `dumpRng` PRIS JUSTE AVANT le pas, et on compare l'etat MT APRES : **meme `mti`**
= meme NOMBRE de tirages, **meme `mt`** = meme flux.

Discipline : `--board` explicite, state-file/gestion runner par la conftest, ASCII only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]      # .../scripts/python/tests/engine/runner/<ce fichier>

BOARD = "MC1_67"
SEED = "777"
ABILITY = "StormboyzStrike"
GRAFT = "orksNob"          # porteur du passif greffe
ALLY = "ultraTitus"        # ALLIE -- garde le tour d'equipe OUVERT (#425)
FOE = "tauCrisis"
ALREADY_USED_TILE = 1179
TELEPORTING_IN = 1140


@pytest.fixture(scope="module")
def grafted_seed_bc(tmp_path_factory) -> Path:
    """Seed BC ou `StormboyzStrike` est greffe sur `GRAFT`. La greffe monte les TROIS triggered
    d'un coup (le builder `AbilitiesDatabase.u003Cu003Ec$$u003CInitializeTriggeredAbilities
    u003Eb__28_134` en construit une `List` de trois)."""
    import catalog_inject as CI
    import probe_380_seed_bc_patch_survival as P380

    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    rep = CI.graft_passive_ability(bc, GRAFT, ABILITY)
    assert rep.get("unitsPatched"), f"greffe {ABILITY} sur {GRAFT} sans effet: {rep}"
    out = tmp_path_factory.mktemp("p448r1port") / "seed_bc_grafted.json"
    out.write_text(json.dumps(bc), encoding="utf-8")
    P380.assert_survives(out)          # #380 : un patch de seed BC peut etre ECRASE en silence
    return out


@pytest.fixture(scope="module")
def grafted_seed_bc_with_full_throttle(tmp_path_factory) -> Path:
    """MEME greffe, mais le porteur recoit AUSSI `FullThrottle` (`replace=False` : la liste est
    CUMULEE au lieu d'etre remplacee).

    Ce n'est pas une variante decorative : c'est le SECOND BRAS du gate `GetAbilityState` de
    `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility`. Avec le seul
    `StormboyzStrike`, le `TriggerAbility(Caster, 0x46e)` du Miss tombe sur une unite qui ne PORTE
    pas FullThrottle -> le natif n'execute rien et ne tire rien. Ici l'unite la porte : le
    `Maybe(chance = 30)` PART, et l'accord PRNG doit toujours tenir -- avec UN tirage de plus."""
    import catalog_inject as CI
    import probe_380_seed_bc_patch_survival as P380

    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    r1 = CI.graft_passive_ability(bc, GRAFT, ABILITY)
    r2 = CI.graft_passive_ability(bc, GRAFT, "FullThrottle", replace=False)
    assert r1.get("unitsPatched") and r2.get("unitsPatched"), (r1, r2)
    assert len(r2.get("passiveAbilitiesAfter") or []) == 2, (
        "les DEUX passifs doivent etre montes : %r" % (r2,))
    out = tmp_path_factory.mktemp("p448r1ft") / "seed_bc_grafted_ft.json"
    out.write_text(json.dumps(bc), encoding="utf-8")
    P380.assert_survives(out)
    return out


def _confront(rpc, build_runner, seed_bc: Path) -> dict:
    """Monte la bataille, capture l'etat AVANT (etat MT inclus), joue le `finish` NATIF, capture
    l'etat APRES, puis REJOUE le meme pas cote PORT depuis l'etat AVANT.

    Renvoie les deux cotes, terme a terme."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.operations.triggers import unit_finished_turn_triggers

    rid = build_runner(SEED, extra=["--p-units", ",".join([GRAFT, ALLY]),
                                    "--a-units", FOE, "--no-ai",
                                    "--seed-bc", str(seed_bc)], board=BOARD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.fail("boardGraph indispo -- le montage n'a rien mesure")
    board = Board(bg["tiles"], adjacency="evenq")

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150) or {}
    # Le porteur est HORS PLATEAU sous 1140 : `visualId`, `team` et `pos` sortent a `null` et il est
    # ABSENT d'`observeBattle.units[]`. Seul `pos is None` le designe (mesure #425).
    cand = [u for u in (dv.get("units") or []) if u.get("pos") is None]
    if len(cand) != 1:
        pytest.fail("porteur hors plateau non identifiable (candidats pos=None: %d) -- montage KO"
                    % len(cand))
    uid = cand[0]["id"]

    ob = rpc("observeBattle", {"runnerId": rid}, 60) or {}
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90) or {}
    tm_before = rpc("tileMeta", {"runnerId": rid, "includeInactive": True}, 90) or {}
    mt_before = rpc("dumpRng", {"runnerId": rid}, 30) or {}
    if not (isinstance(mt_before, dict) and mt_before.get("mt")):
        pytest.fail("dumpRng indispo -- sans alignement PRNG la confrontation ne vaut rien")

    # --- cote PORT : meme etat de depart, meme flux RNG
    state = load_state(dv, ob, snap, board=board, tiles=tm_before)
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(mt_before["mt"]), mt_before["mti"]
    state.rng = rng
    port_out = unit_finished_turn_triggers(state, int(uid))

    # --- cote NATIF : le meme pas
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "finish", "unitId": uid}}, 120)
    dv_after = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150) or {}
    tm_after = rpc("tileMeta", {"runnerId": rid, "includeInactive": True}, 90) or {}
    mt_after = rpc("dumpRng", {"runnerId": rid}, 30) or {}
    me = next((u for u in (dv_after.get("units") or []) if u.get("id") == uid), None)

    return {"rid": rid, "board": board, "uid": uid, "state": state, "port_out": port_out,
            "native": me, "tm_after": tm_after, "tm_before": tm_before,
            "mt_before": mt_before, "mt_after": mt_after, "rng": rng}


@pytest.fixture(scope="module")
def confrontation(rpc, build_runner, grafted_seed_bc):
    """BRAS 1 -- le porteur ne porte QUE `StormboyzStrike` (la greffe REMPLACE la liste)."""
    return _confront(rpc, build_runner, grafted_seed_bc)


@pytest.fixture(scope="module")
def confrontation_ft(rpc, build_runner, grafted_seed_bc_with_full_throttle):
    """BRAS 2 -- le porteur porte AUSSI `FullThrottle` (cf. la fixture du seed)."""
    return _confront(rpc, build_runner, grafted_seed_bc_with_full_throttle)


def _consumed(c) -> tuple:
    """(tirages PORT, tirages NATIF) sur le pas mesure.

    ⚠ Le compteur `mti` du Mersenne Twister WRAPPE a 624 (`genrand_int32` regenere le buffer et
    remet l'index a 0) : une simple soustraction rend un nombre NEGATIF des que le pas franchit la
    borne, ce qui masquerait un ecart. On compte donc MODULO 624."""
    n = len(c["mt_before"]["mt"]) or 624
    before = int(c["mt_before"]["mti"])
    return ((int(c["rng"].mti) - before) % n,
            (int((c["mt_after"] or {}).get("mti", before)) - before) % n)


def _marked_positions(tiles) -> list:
    return sorted((t.get("col"), t.get("row")) for t in (tiles or [])
                  if any(e.get("effectType") == ALREADY_USED_TILE for e in (t.get("effects") or [])))


def _port_marked_positions(state) -> list:
    """Positions des tuiles portant `1179` cote PORT (l'effet est pose sur l'ENTITE-TUILE, cf.
    #425 -- meme cle que la pose native)."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return []
    out = []
    for owner, lst in (eff.by_unit or {}).items():
        if not any((not e.consumed) and e.effect_type == ALREADY_USED_TILE for e in lst):
            continue
        try:
            xy = state.board.coord(int(owner))
        except Exception:
            xy = None
        if xy is not None:
            out.append((int(xy[0]), int(xy[1])))
    return sorted(out)


def _port_pos(state, uid):
    from engine.runner.components import PositionComponent
    e = state.get_entity(int(uid))
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


# --------------------------------------------------------------------------- L1

def test_L1_le_fallback_fait_atterrir_le_porteur_AU_MEME_ENDROIT(confrontation):
    """L1 -- l'observable central : la tuile d'ATTERRISSAGE.

    Elle est le resultat de `First(SortTilesByUtility(CanAddUnit(AllTiles), Caster,
    UtilityDefinition(6 = UnitMovement)), 1)`, un tri DETERMINISTE (zero tirage) sur le composite
    `UnitMovement(6) = Tile(7) + MinDistanceToClosestEnemy(17)` -- donc l'accord porte sur TOUT
    l'etage d'utilite de mouvement, pas seulement sur le cablage du trigger.

    ⚠ Si le `Maybe(20)` du Miss est passe, le natif a ete DEVIE d'un hex : le port, aligne sur le
    MEME flux RNG, doit alors avoir ete devie de la MEME facon. Le test ne relache donc RIEN ici."""
    c = confrontation
    native = (c["native"] or {}).get("pos") or {}
    assert native.get("col") is not None, (
        "le porteur n'a PAS atterri cote natif -- le Fallback n'a pas fire, le scenario n'exerce "
        "rien (verifier la greffe et l'effet 1140 au depart)")
    port = _port_pos(c["state"], c["uid"])
    assert port is not None, (
        "le PORT n'a pas repose le porteur sur le plateau : le vecteur On(0x28) n'a pas fire, ou "
        "`MoveUnit` n'a trouve aucune tuile. Sortie du port : %r" % (c["port_out"],))
    assert port == (native["col"], native["row"]), (
        "atterrissage PORT %s != NATIF %s (PRNG aligne : mti avant=%s)"
        % (port, (native["col"], native["row"]), c["mt_before"].get("mti")))


def test_L2_la_MEME_tuile_est_marquee_1179(confrontation):
    """L2 -- la marque `1179`, terme a terme. C'est la SECONDE evaluation du meme objet-noeud
    selecteur ; elle ne peut coincider que si le port partage bien le noeud ET re-evalue
    `CanAddUnit` sur l'etat POST-move."""
    c = confrontation
    native = _marked_positions((c["tm_after"] or {}).get("tiles"))
    port = _port_marked_positions(c["state"])
    assert native, (
        "AUCUNE tuile marquee cote natif -- si la liste est vide, verifier d'abord que le tour "
        "d'equipe est reste OUVERT (roster allie >= 2, cf. #425)")
    assert port == native, "tuiles marquees PORT %s != NATIF %s" % (port, native)


def test_L3_la_tuile_marquee_n_est_PAS_celle_d_atterrissage_des_DEUX_cotes(confrontation):
    """L3 -- le QUIRK #425, verifie SUR LES DEUX COTES. Un port qui construirait deux noeuds
    jumeaux marquerait la tuile d'atterrissage : L2 le verrait, mais seulement si le natif ne fait
    pas la meme chose. Ce test fige l'invariant lui-meme."""
    c = confrontation
    native_pos = (c["native"] or {}).get("pos") or {}
    landed = (native_pos.get("col"), native_pos.get("row"))
    native_marked = _marked_positions((c["tm_after"] or {}).get("tiles"))
    port_marked = _port_marked_positions(c["state"])
    assert landed not in native_marked, (
        "NATIF : la tuile marquee %s EST la tuile d'atterrissage %s -- si le jeu a change, refaire "
        "la lecture de `StormboyzStrike_FallbackAbility$$CreateBehaviour`" % (native_marked, landed))
    assert _port_pos(c["state"], c["uid"]) not in port_marked, (
        "PORT : la tuile marquee EST la tuile d'atterrissage -- le noeud selecteur n'est pas "
        "PARTAGE (ou pas re-evalue)")


def test_L4_l_effet_1140_est_retire_des_DEUX_cotes(confrontation):
    """L4 -- `RemoveEffect(Caster, 0x474)` du Miss (hors du `If` : il tombe que le hex ait ete rate
    ou non). Le porteur ne doit plus etre « en vol » apres le pas.

    ⚠ Le retrait a DEUX sources natives concurrentes, et c'est voulu : ce `RemoveEffect`-ci, et le
    3e trigger propre d'`ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal`
    (`On(0x28) & OwnerIsActor & HasTile(Owner)`, porte depuis #448-r2b), qui devient vrai des que le
    move a redonne une tuile au porteur. Les deux menent au meme etat observable."""
    c = confrontation
    native_eff = [e for e in ((c["native"] or {}).get("effects") or [])
                  if int((e or {}).get("effectType") or -1) == TELEPORTING_IN]
    assert not native_eff, "NATIF : 1140 encore present apres le pas : %r" % (native_eff,)
    eff = getattr(c["state"], "effects", None)
    port_eff = [e for e in ((eff.by_unit or {}).get(int(c["uid"])) or [])
                if (not e.consumed) and e.effect_type == TELEPORTING_IN] if eff else []
    assert not port_eff, "PORT : 1140 encore present apres le pas"


def test_L5_le_PORT_consomme_le_MEME_flux_PRNG(confrontation):
    """L5 -- l'accord BIT-EXACT du PRNG. Le kit tire `Maybe(20)` (le miss) puis `Maybe(30)`
    (FullThrottle), plus `min(len(pool), 1)` tirages de `PickRandomly` en cas de miss.

    `mti` egal = MEME NOMBRE de tirages -> aucun `Maybe` oublie ni invente ; `mt` egal = MEME flux.
    C'est la garde qui rendrait un port « qui marche par hasard » ROUGE : oublier le
    `TriggerAbility(FullThrottle)` laisserait l'atterrissage et la marque intacts (L1..L4 verts) et
    ne se verrait QUE par un tirage manquant.

    ⚠ Le pas natif englobe aussi ce que le port ne rejoue pas ici (fin de tour d'equipe cote natif) ;
    si `mti` diverge, la sortie affiche les deux compteurs pour trancher tout de suite."""
    c = confrontation
    after = c["mt_after"] or {}
    if not after.get("mt"):
        pytest.fail("dumpRng APRES indisponible -- rien n'est mesure")
    port_consumed, live_consumed = _consumed(c)
    assert port_consumed == live_consumed, (
        "tirages consommes : PORT %d != NATIF %d (mti %s -> port %s / natif %s). Un ecart de 1 "
        "designe un `Maybe` : celui du Miss (chance=20) ou celui de FullThrottle (chance=30)."
        % (port_consumed, live_consumed, c["mt_before"]["mti"], c["rng"].mti, after["mti"]))
    assert list(c["rng"].mt) == list(after["mt"]), (
        "meme NOMBRE de tirages mais flux MT DIFFERENT -- le port tire les memes quantites dans un "
        "ordre different (ou avec des chances differentes)")


def test_L6_le_gate_GetAbilityState_a_ses_DEUX_bras(confrontation, confrontation_ft):
    """L6 -- GENERALISATION, et le seul test qui exerce le gate `GetAbilityState` des DEUX cotes.

    `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` n'execute l'ability
    declenchee que si la cible la PORTE (`ignoreUnitHavingAbility = false` a ce call-site) :

      * BRAS 1 (`confrontation`) -- le porteur n'a que `StormboyzStrike` : le
        `TriggerAbility(Caster, 0x46e)` du Miss ne trouve RIEN, donc **aucun tirage** ;
      * BRAS 2 (`confrontation_ft`) -- il porte AUSSI `FullThrottle` : le `Maybe(chance = 30)` PART,
        donc **un tirage de PLUS** que le bras 1.

    C'est ce delta de +1 qui prouve que le gate est LU et non simule : un port qui declencherait
    toujours (l'etat d'avant #448-r1) rendrait les deux bras EGAUX -- et faux sur le bras 1, ou il
    consommait 3 tirages contre 2 au natif (mesure du 2026-08-03). Un port qui ne declencherait
    JAMAIS les rendrait egaux aussi, et faux sur le bras 2."""
    p1, n1 = _consumed(confrontation)
    p2, n2 = _consumed(confrontation_ft)
    assert (p1, p2) == (n1, n2), (
        "accord PRNG rompu : bras SANS FullThrottle port=%d natif=%d | bras AVEC port=%d natif=%d"
        % (p1, n1, p2, n2))
    assert n2 == n1 + 1, (
        "le NATIF devrait consommer UN tirage de plus quand le porteur a FullThrottle "
        "(le `Maybe(chance = 30)`) : %d -> %d. Si les deux sont egaux, le bras 2 n'exerce rien "
        "(la greffe cumulee n'a pas pris) et le test ne mesure PAS le gate." % (n1, n2))
    assert list(confrontation_ft["rng"].mt) == list(confrontation_ft["mt_after"]["mt"])
