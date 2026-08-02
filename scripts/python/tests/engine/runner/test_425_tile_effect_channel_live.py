"""#425 -- la marque de tuile TRAVERSE le canal, du capteur natif jusqu'au consommateur.

#448-r1 avait mesure « entites Effect 17 -> 18, et AUCUNE tuile marquee dans `tileMeta` », et en
avait conclu un RESIDU DE CANAL (« le -100 est inatteignable cote port », capteur a poser, reinject
requis). Cette conclusion est REFUTEE, par mesure : le canal est sain de bout en bout. Ce qui
manquait etait le MONTAGE.

LA CAUSE, lue au decompile puis confrontee live -- le porteur greffe etait la SEULE unite de son
equipe, donc son `applyAction {kind:"finish"}` CLOTURAIT le tour d'equipe. Or
`IdunBattleLogic.Abilities.Triggered.Loki.StormboyzStrike_FallbackAbility$$CreateBehaviour` pose
`AddEffect(0x49b, AbilityStateReference, targets: <tuile>, turns: Nullable<int>(1))` : une duree
d'UN tour, consommee dans le meme `applyAction`. Au moment de la lecture l'effet n'etait plus dans
l'`EffectsOwnedComponent.ActiveEffectIds` de la tuile -- absence CORRECTE, pas un trou de capteur.
Avec un allie qui n'a pas fini, le tour d'equipe reste ouvert et la marque est publiee.

CE FICHIER verrouille les QUATRE etages que #448-r1 ne savait pas separer, sur UN seul runner :

  E1  CAPTEUR + DECODEUR -- `readEffectsByTile` (frida/hooks/game/effects.ts) publie l'effet sur
      l'entite-tuile OWNER. Le natif garantit que c'est bien une tuile :
      `IdunBattle.Entities.Blueprints$$Tile` attache un `EffectsOwnedComponent` a TOUTE tuile
      (slot `TileEntity+0x58`), et `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` fait
      `List.Add(effectId)` sur celui de l'`owner` sans regarder l'EntityType.
  E2  OWNER == SOURCE -- la surcharge `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect(effectType,
      abilityState, targets, turns)` passe `source = NULL` au ctor d'`AddEffectBehaviour` ;
      `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` retombe alors litteralement sur
      la CIBLE. `EffectComponent.SourceUnitId` publie par `effectAbilityStates` DOIT donc designer
      l'entite-tuile marquee -- c'est ce qui rend la mesure NOMINATIVE.
  E3  INGESTION -- `load_state(tiles=tileMeta, board=...)` materialise l'effet sur l'entite-tuile,
      et l'empreinte offline egale l'empreinte live. TEMOIN : sans le canal, empreinte VIDE.
  E4  CONSOMMATEUR -- la feuille `IdunBattle.AI.Utilities.TileEffectsUtility` du port rend le poids
      `-100` SUR LA POSITION REELLEMENT MARQUEE, alimentee par le meme `tileMeta`. C'est le pas que
      #448-r1 declarait « inatteignable ».

QUIRK NATIF verrouille au passage (E2b) -- la tuile marquee n'est PAS celle d'atterrissage.
`MoveUnitBehaviour` et `AddEffect` partagent le MEME noeud selecteur (`First(SortTilesByUtility(
CanAddUnit(<AllTilesSelector>), Caster, UtilityDefinition(6 = UnitMovement), null), Direct(1))`),
mais l'operateur `&` les execute EN SEQUENCE : quand `AddEffect` re-evalue le selecteur, le caster
occupe deja la meilleure tuile, `CanAddUnit` l'exclut, et `First` rend la SUIVANTE du classement.
#448-r1 §5 affirmait l'inverse (« la tuile marquee est EXACTEMENT celle ou il a atterri ») -- c'est
FAUX, et ce test le fige.

Drive des positions (doctrine) ; state-file/gestion runner par la conftest ; ASCII only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]      # .../scripts/python/tests/engine/runner/<ce fichier>

BOARD = "MC1_67"
SEED = "777"
ABILITY = "StormboyzStrike"
GRAFT = "orksNob"          # porteur du passif greffe (le seul porteur natif est npc)
ALLY = "ultraTitus"        # ALLIE -- garde le tour d'equipe OUVERT (cf. docstring)
FOE = "tauCrisis"
ALREADY_USED_TILE = 1179
EFFECT_NAME = "StormboyzStrike_AlreadyUsedTile"


# --------------------------------------------------------------------------- montage

@pytest.fixture(scope="module")
def grafted_seed_bc(tmp_path_factory) -> Path:
    """Seed BC ou `StormboyzStrike` est greffe sur `GRAFT` (case-92 §5bis, recours 3).

    La greffe monte les TROIS triggered d'un coup : `IdunBattle.Core.Services.AbilitiesDatabase
    .u003Cu003Ec$$u003CInitializeTriggeredAbilitiesu003Eb__28_134`, unique entree pour
    `TriggeredAbilityType.StormboyzStrike`, construit une `List` de trois instances."""
    import catalog_inject as CI
    import probe_380_seed_bc_patch_survival as P380

    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    rep = CI.graft_passive_ability(bc, GRAFT, ABILITY)
    assert rep.get("unitsPatched"), f"greffe {ABILITY} sur {GRAFT} sans effet: {rep}"
    out = tmp_path_factory.mktemp("p425") / "seed_bc_grafted.json"
    out.write_text(json.dumps(bc), encoding="utf-8")
    # #380 : un patch de seed BC sur DISQUE peut etre ECRASE en silence par le rattrapage
    # `catalog_inject.refresh_ability_configs` de `_load_seed_bc`. Sans cette garde, un run VERT
    # ne mesurerait rien.
    P380.assert_survives(out)
    return out


@pytest.fixture(scope="module")
def marked(rpc, build_runner, grafted_seed_bc):
    """Monte la bataille, termine le tour du porteur, et rend l'etat APRES la pose.

    Le roster ALLIE est le discriminant : `[GRAFT, ALLY]`. Avec le seul porteur, son `finish`
    cloture le tour d'equipe et la marque `turns: 1` est consommee dans le meme `applyAction`.
    """
    from engine.entities.pathfinding.board import Board

    rid = build_runner(SEED, extra=["--p-units", ",".join([GRAFT, ALLY]),
                                    "--a-units", FOE, "--no-ai",
                                    "--seed-bc", str(grafted_seed_bc)], board=BOARD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150) or {}
    # Le porteur part HORS PLATEAU sous `1140 StormboyzStrike_TeleportingIn` (acquis #366-r1) : il
    # sort de `decisionView` avec `visualId`, `team` ET `pos` a `null`, et il est ABSENT
    # d'`observeBattle.units[]`. On ne peut le reconnaitre qu'a `pos is None`.
    cand = [u for u in (dv.get("units") or []) if u.get("pos") is None]
    if len(cand) != 1:
        pytest.skip("porteur hors plateau non identifiable (candidats pos=None: %d)" % len(cand))
    uid = cand[0]["id"]

    before = rpc("tileMeta", {"runnerId": rid}, 90) or {}
    rpc("applyAction", {"runnerId": rid,
                        "action": {"kind": "finish", "unitId": uid}}, 120)
    after = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150) or {}
    me = next((u for u in (after.get("units") or []) if u.get("id") == uid), None)
    return {"rid": rid, "board": board, "uid": uid, "me": me, "tm_before": before}


def _marked_positions(tiles) -> list:
    return [(t.get("col"), t.get("row")) for t in (tiles or [])
            if any(e.get("effectType") == ALREADY_USED_TILE for e in (t.get("effects") or []))]


# --------------------------------------------------------------------------- E1/E2

def test_the_tile_channel_publishes_the_mark_live(rpc, marked):
    """E1 + E2 -- `tileMeta` publie `1179` sur une tuile, et l'OWNER publie par le canal SANS
    filtre (`effectAbilityStates`) est cette meme entite-tuile.

    Les deux canaux sont INDEPENDANTS : `effectAbilityStates` balaie toutes les entites
    `EntityType.Effect` sans aucun filtre d'appartenance, `tileMeta` part de la liste possedee par
    la tuile. Leur ACCORD est ce qui prouve que le capteur n'invente ni ne perd la marque -- un
    zero des deux cotes ne prouverait rien (cf. #444)."""
    rid, board = marked["rid"], marked["board"]
    tm = rpc("tileMeta", {"runnerId": rid, "includeInactive": True}, 90) or {}
    pos = _marked_positions(tm.get("tiles"))
    assert len(pos) == 1, (
        "attendu UNE tuile marquee %s apres le finish, mesure %s -- si la liste est vide, verifier "
        "d'abord que le tour d'equipe est bien reste OUVERT (roster allie >= 2)"
        % (ALREADY_USED_TILE, pos))

    eas = rpc("effectAbilityStates", {"runnerId": rid, "effectType": ALREADY_USED_TILE}, 120) or {}
    rows = eas.get("effects") or []
    assert len(rows) == 1, f"attendu UNE entite Effect de type {ALREADY_USED_TILE}, mesure {rows}"
    owner = rows[0].get("source")
    assert owner is not None, f"SourceUnitId non publie: {rows[0]}"
    assert board.coord(int(owner)) == pos[0], (
        "l'OWNER publie par effectAbilityStates (entite %s @ %s) n'est pas la tuile marquee par "
        "tileMeta (%s) -- les deux canaux divergent"
        % (owner, board.coord(int(owner)), pos[0]))

    name = {e.get("name") for t in (tm.get("tiles") or []) if (t.get("col"), t.get("row")) == pos[0]
            for e in (t.get("effects") or []) if e.get("effectType") == ALREADY_USED_TILE}
    assert name == {EFFECT_NAME}, (
        "le NOM publie est %s -- c'est LUI la cle de poids `BC.Utilities.<profil>.TileEffects` que "
        "lit `TileEffectsUtility` (Enum.ToString), pas l'id" % (name,))


def test_the_marked_tile_is_not_the_landing_tile_live(rpc, marked):
    """E2b -- QUIRK NATIF : la tuile MARQUEE n'est pas celle d'ATTERRISSAGE.

    `MoveUnitBehaviour` et `AddEffect` partagent le meme noeud `First(SortTilesByUtility(
    CanAddUnit(<AllTilesSelector>), ...))`, mais `&` les execute EN SEQUENCE : a la re-evaluation,
    le caster occupe deja la meilleure tuile et `CanAddUnit` l'exclut. #448-r1 §5 affirmait
    l'inverse ; ce test fige le comportement REEL, mesure."""
    rid = marked["rid"]
    landed = (marked["me"] or {}).get("pos") or {}
    assert landed.get("col") is not None, (
        "le porteur n'a pas atterri : le Fallback n'a pas fire, le scenario n'exerce rien")
    tm = rpc("tileMeta", {"runnerId": rid, "includeInactive": True}, 90) or {}
    pos = _marked_positions(tm.get("tiles"))
    assert pos, "aucune tuile marquee"
    assert pos[0] != (landed["col"], landed["row"]), (
        "la tuile marquee %s EST la tuile d'atterrissage -- si le natif a change, refaire la "
        "lecture de `StormboyzStrike_FallbackAbility$$CreateBehaviour`" % (pos[0],))


# --------------------------------------------------------------------------- E3

def test_load_state_ingests_the_mark_live(rpc, marked):
    """E3 -- l'INGESTION : `load_state(tiles=tileMeta, board=...)` materialise la marque sur
    l'entite-tuile, et l'empreinte offline egale l'empreinte live. TEMOIN sans le canal = vide."""
    from engine.runner.snapshot import (load_state, tile_effects_footprint,
                                        tile_effects_footprint_live)

    rid, board = marked["rid"], marked["board"]
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    tm = rpc("tileMeta", {"runnerId": rid}, 90)

    st = load_state(dec, ob, snap, board=board, tiles=tm)
    fp_off = tile_effects_footprint(st) or {}
    fp_live = tile_effects_footprint_live(tm, board) or {}
    marked_ids = sorted(k for k, e in fp_live.items() if ALREADY_USED_TILE in e)
    assert marked_ids, "l'empreinte LIVE ne porte pas la marque : rien a ingerer"
    assert fp_off == fp_live, f"empreinte offline {fp_off} != live {fp_live}"
    assert all(ALREADY_USED_TILE in fp_off.get(k, {}) for k in marked_ids)

    st_ctrl = load_state(dec, ob, snap, board=board, tiles=None)
    assert not (tile_effects_footprint(st_ctrl) or {}), (
        "le TEMOIN (load_state SANS `tiles`) porte deja des effets de tuile -- le test ne "
        "discrimine plus le vecteur d'ingestion")


# --------------------------------------------------------------------------- E4

def test_the_utility_leaf_reaches_minus_100_on_the_marked_tile_live(rpc, marked):
    """E4 -- le CONSOMMATEUR. La feuille `TileEffects` du port, alimentee par le MEME `tileMeta`
    que le decideur (`engine/ai/context.py` construit `effects_by_pos` exactement ainsi), rend
    `-100` sur la position marquee et `0` sur les autres.

    C'est le pas que le residu #448-r1 declarait inatteignable. Le contre-bras (une tuile NON
    marquee) est indispensable : un port qui rendrait -100 partout passerait le premier."""
    from engine.utilities.tile import TileEffectsUtility
    from engine.weights import Weights

    rid = marked["rid"]
    tm = rpc("tileMeta", {"runnerId": rid}, 90) or {}
    tiles = tm.get("tiles") or []
    # MEME construction que `engine.ai.context.build` : la cle de poids est le NOM.
    effects_by_pos = {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
                      for t in tiles}
    pos = _marked_positions(tiles)
    assert len(pos) == 1, f"attendu UNE tuile marquee, mesure {pos}"

    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    wt = Weights(bc["Utilities"])
    leaf = TileEffectsUtility()

    u_marked = leaf.evaluate(None, {"effects": effects_by_pos[pos[0]]}, None, wt)
    assert u_marked == -100.0, (
        "la feuille rend %s sur la tuile marquee %s (effets publies : %s) -- le poids "
        "`BC.Utilities.Default.TileEffects[%s]` n'atteint pas le decideur"
        % (u_marked, pos[0], effects_by_pos[pos[0]], EFFECT_NAME))

    clean = [p for p, names in effects_by_pos.items() if not [n for n in names if n]]
    assert clean, "aucune tuile SANS effet sur ce board : pas de contre-bras"
    assert leaf.evaluate(None, {"effects": effects_by_pos[clean[0]]}, None, wt) == 0.0, (
        "une tuile SANS effet ne rend pas 0 -- la feuille ne discrimine pas")
