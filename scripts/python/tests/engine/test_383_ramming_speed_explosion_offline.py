"""#383 -- les batchs 3/4 (EXPLOSION) de `RammingSpeed` (1059), 100 % OFFLINE.

Ce que ce fichier verrouille, et POURQUOI chaque cliquet existe :

  * la GATE `!self.Any(p => p.Prediction.WillBeKill)` -- fermee, le natif s'arrete au 2e batch ;
  * l'ORDRE natif `[cible, caster, Friends(...), Enemies(...)]` et le drapeau `friendly` PAR BATCH
    (`DamageUtility.<EvaluateAttackInSteps>d__2$$MoveNext` : `if (IsFriend(caster, actor)) u *= -1`) ;
  * les entrees de `GenerateAttackPredictions` : **1 coup** (le slot `0x24` d'`IBattleQuery` est
    `BattleQuery$$GetAttackPrediction`, le 1er coup de `GetMultiHitAttackPrediction`) et le profil
    `Nullable(0xf = DirectDamage)`, litteral du call-site ;
  * `ExplodesAbility$$GetDamage` = `PercentageOf(StatAmount(Owner, Health, part = 2 -> MAX),
    Sum(ConfigConst(1021, 0xf), ConditionalAmount(HasEffect(Owner, 1098), ConfigConst(1059, 0xf),
    Get(0))))` -- **les DEUX branches** du `ConditionalAmount`, et la base **MAXIMUM** contre la
    base COURANTE (le seul axe qui a fait tomber le port en #383 : `UnitContext.get_stat(Health, 2)`
    rend le COURANT parce que le port seede `Health` en `StatComponent` generique) ;
  * le CASTER n'est **pas** retire de l'anneau : l'`origin` de `AdjacentUnits` est une TUILE, donc
    l'`op_Subtraction origin` de `DSLSelectors$$AdjacentUnits` ne mord sur aucune unite ;
  * `scene_tile_leaf_ctx` partitionne par EQUIPE du sujet (et non par le `ctrl` de la face
    decision) -- c'est ce que resout `GetAdjacentEnemies(tile, case.unit, false)`.

Board 7x7 PLAT et deterministe (meme construction que `runner/_ramming_speed_charge_montage.py`) :
`Tile(7)` y est constant, donc rien ne depend d'un terrain subi.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                              # noqa: E402
from engine.playbook.prediction import abilities as PA                     # noqa: E402
from engine.playbook.prediction import ramming_speed as RS                 # noqa: E402
from engine.playbook.scene import Scene                                    # noqa: E402

ABILITY, NAME = 1059, "RammingSpeed"
COLS, ROWS = 7, 7
CASTER_ID, TARGET_ID, ENEMY2_ID, ALLY_ID = 10, 20, 30, 40
HP_MAX, HP_CUR = 1000, 400          # DISSOCIES : c'est ce qui rend l'axe `StatPart` observable


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


def _scene(caster=(0, 3), target=(3, 3), enemy2=(3, 2), ally=(2, 1),
           hp_cur=HP_CUR, hp_max=HP_MAX):
    """`Scene` de PREDICTION batie depuis un `State` runner (`Scene.from_state`) -- meme substrat
    que le moteur en live.

    GEOMETRIE CHOISIE, pas subie (board 7x7 plat, `hexgeo` = even-q) : la tuile d'arrivee est
    `(2,2)`, et `ally = (2,1)` est un voisin de CETTE tuile qui n'est PAS voisin de la cible -- il
    peuple donc le batch `Friends` **sans** entrer dans `CanAddUnit(AdjacentTiles(Target))`, donc
    sans deplacer la tuile (POINT FIXE). `test_gate_open_...` exige un AMI **et** un ENNEMI et
    REFUSE de conclure sinon : si cette geometrie cessait d'etre peuplee, le cliquet rougirait au
    lieu de passer sur un ensemble vide."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": CASTER_ID, "visualId": "orksKillaKan", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": caster[0], "row": caster[1]}, "effects": []},
        {"id": ALLY_ID, "visualId": "astraBullgryn", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": ally[0], "row": ally[1]}, "effects": []},
        {"id": TARGET_ID, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": target[0], "row": target[1]}, "effects": []},
        {"id": ENEMY2_ID, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": enemy2[0], "row": enemy2[1]}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": hp_cur, "hpMax": hp_max}
                         for u in decision["units"]]}
    state = load_state(decision, observe, board=board)
    sc = Scene.from_state(state)
    # Deux tables que `Scene.from_state` ne peut pas porter sans `combatSnapshot`, et sans
    # lesquelles le handler se degrade AVANT d'avoir rien teste :
    #   * `ctx_by_id` -- `make_damage_predictions` sort en tete sur `ab is None` (l'ability se
    #     construit sur le `UnitContext` du caster), donc le 2e batch et les batchs 3/4 n'existent
    #     meme pas ;
    #   * `abstate_by_id` (`AbilityState` PER-ABILITY, #100) -- sans lui `ab.level` retombe a 0 et
    #     `GetVariableForLevel` rend une base NULLE.
    from engine.entities.effects_state import EffectsState
    from engine.entities.unit_context import UnitContext
    sc.ctx_by_id = {int(u["id"]): UnitContext(entity_id=int(u["id"]))
                    for u in decision["units"]}
    sc.abstate_by_id = {CASTER_ID: {ABILITY: {"level": 8, "multiplier": 100}}}
    if sc.eff_state is None:            # idem : pas de `combatSnapshot` -> table d'effets VIDE
        sc.eff_state = EffectsState()
    return sc, board


class _Rec:
    """Sentinelle de prediction : seul `will_be_kill()` est lu (le predicat de la gate)."""
    def __init__(self, kill: bool = False):
        self.kill = bool(kill)

    def will_be_kill(self) -> bool:
        return self.kill


def _capture(monkeypatch, kill_self: bool):
    """Remplace le foyer de degat par une sentinelle et rend la liste des appels. `kill_self` =
    la valeur que `will_be_kill()` rend sur l'event du CASTER (la gate des batchs 3/4)."""
    calls = []

    def _fake(scene, uid, tgt, ability_id, ability_name, attack_pos=None, base_bonus=0,
              base_override=None, hits_override=None, profile_override=None):
        calls.append({"caster": uid, "target": tgt, "base": base_override,
                      "hits": hits_override, "profile": profile_override})
        return _Rec(kill=(kill_self and tgt == uid))

    monkeypatch.setattr(PA, "generate_multi_hit_attack_prediction", _fake)
    return calls


# --------------------------------------------------------------- A : la GATE `WillBeKill`

def test_gate_closed_stops_at_the_self_batch(monkeypatch):
    """`if (!self.Any(p => p.Prediction.WillBeKill)) return list;` -- le recul ne tue pas le caster,
    donc AUCUN batch d'explosion, quel que soit le voisinage."""
    sc, _ = _scene()
    _capture(monkeypatch, kill_self=False)
    evs = PA.make_damage_predictions(sc, CASTER_ID, TARGET_ID, ABILITY, NAME, attack_pos=(0, 3))
    assert [e.target for e in evs] == [TARGET_ID, CASTER_ID], (
        "gate FERMEE : le natif emet la cible puis le caster, et s'arrete")


def test_gate_open_emits_friends_then_enemies_in_native_order(monkeypatch):
    """Gate OUVERTE : `AddRange(Friends(...))` PUIS `AddRange(Enemies(...))`, et le drapeau
    `friendly` suit le BATCH (pas une heuristique par cible)."""
    sc, _ = _scene()
    _capture(monkeypatch, kill_self=True)
    evs = PA.make_damage_predictions(sc, CASTER_ID, TARGET_ID, ABILITY, NAME, attack_pos=(0, 3))
    assert len(evs) > 2, "montage non discriminant : l'anneau de la tuile d'arrivee est vide"
    assert [e.target for e in evs[:2]] == [TARGET_ID, CASTER_ID]
    expl = evs[2:]
    fr = [e.target for e in expl if e.friendly]
    en = [e.target for e in expl if not e.friendly]
    assert fr and en, "montage non discriminant : il faut un AMI et un ENNEMI dans l'anneau"
    assert [e.target for e in expl] == fr + en, (
        "l'ordre natif est `Friends(...)` puis `Enemies(...)` -- deux `AddRange` successifs")
    assert set(fr) <= {ALLY_ID, CASTER_ID} and set(en) <= {TARGET_ID, ENEMY2_ID}


def test_explosion_events_are_one_hit_direct_damage(monkeypatch):
    """Les entrees LITTERALES du call-site : `1` coup (slot `0x24` = `GetAttackPrediction`, PAS la
    surcharge multi-coups) et `Nullable(0xf = DirectDamage)` en `param_8`."""
    sc, _ = _scene()
    calls = _capture(monkeypatch, kill_self=True)
    PA.make_damage_predictions(sc, CASTER_ID, TARGET_ID, ABILITY, NAME, attack_pos=(0, 3))
    expl = calls[2:]
    assert expl, "aucun batch d'explosion -- le montage ne teste rien"
    assert all(c["hits"] == 1 for c in expl), "chaque event d'explosion vaut UN coup"
    assert all(c["profile"] == "DirectDamage" for c in expl)
    bases = {c["base"] for c in expl}
    assert len(bases) == 1, (
        "`amount` est evalue UNE FOIS hors des boucles puis re-emballe en `Get(amount)` : toutes "
        "les cibles recoivent la MEME base")


# ---------------------------------------------- B : `ExplodesAbility$$GetDamage`, terme par terme

def _pcts():
    import gameconfig as GC
    base = ((GC.trait("Explodes") or {}).get("variables") or {}).get("explodesDmg")
    extra = ((GC.ability(NAME) or {}).get("constants") or {}).get("extraDmgPct")
    return int(base), int(extra)


def test_amount_is_a_percentage_of_MAX_health_not_current():
    """La base est `StatAmount(Owner, Health, part = 2 -> MAXIMUM)`.

    Bras DISCRIMINANT par construction : `hp_cur != hp_max`. C'est l'axe qui a fait tomber le port
    -- `UnitContext.get_stat(Health, 2)` rend le COURANT (le port seede `Health` en
    `StatComponent` generique, cf. `entities/stats.seed_unit_stats`), donc lire cette voie donnait
    25 % de 400 au lieu de 25 % de 1000."""
    base_pct, _ = _pcts()
    sc, _ = _scene()
    assert sc.hpmax(CASTER_ID) != sc.hp(CASTER_ID), "bras non discriminant : hp == hpMax"
    got = RS.explosion_amount(sc, CASTER_ID, TARGET_ID, (0, 3))
    assert got == round(HP_MAX * base_pct / 100)
    assert got != round(HP_CUR * base_pct / 100), "le bras ne separe pas MAX et COURANT"


def test_conditional_amount_true_branch_adds_the_ramming_speed_constant():
    """`ConditionalAmount(HasEffect(Owner, 0x44a = 1098), ConfigConst(1059, 0xf), Get(0))`.

    La branche VRAIE n'est atteignable qu'avec l'effet `RammingSpeed_ExtraExplode` POSE -- son seul
    poseur en jeu est `RammingSpeedAbility$$ExecuteBehaviour`. On le pose ICI directement dans
    l'`EffectsState` de la scene : c'est le MEME substrat que `ctx.has_effect` interroge."""
    base_pct, extra_pct = _pcts()
    sc, _ = _scene()
    before = RS.explosion_amount(sc, CASTER_ID, TARGET_ID, (0, 3))
    assert before == round(HP_MAX * base_pct / 100)

    class _Eff:
        name, effect_type, consumed, expired, active = ("RammingSpeed_ExtraExplode",
                                                        RS.RAMMING_SPEED_EXTRA_EXPLODE,
                                                        False, False, True)

        def is_active(self, unit_state=None):
            return True

    sc.eff_state.by_unit.setdefault(CASTER_ID, []).append(_Eff())
    after = RS.explosion_amount(sc, CASTER_ID, TARGET_ID, (0, 3))
    assert after == round(HP_MAX * (base_pct + extra_pct) / 100)
    assert after != before, "bras non discriminant : `extraDmgPct` vaut 0 en config"


def test_amount_degrades_to_none_without_the_trait_variable(monkeypatch):
    """Config de trait absente -> `None` (aucun event invente), meme convention que les autres
    handlers du registre."""
    import gameconfig as GC
    monkeypatch.setattr(GC, "trait", lambda name: {})
    sc, _ = _scene()
    assert RS.explosion_amount(sc, CASTER_ID, TARGET_ID, (0, 3)) is None


# ------------------------------------------------- C : la TUILE et l'anneau (`AdjacentUnits`)

def test_tile_to_move_to_matches_the_combat_face():
    """UN seul mirror de `GetTileToMoveTo` dans le depot : la face PREDICTION (substrat `Scene`) et
    la face COMBAT (substrat `State`) doivent rendre LA MEME tuile sur le MEME etat."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities.orks import ramming_speed_tile_to_move_to
    from engine.runner.snapshot import load_state
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": CASTER_ID, "visualId": "orksKillaKan", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 0, "row": 3}, "effects": []},
        {"id": ALLY_ID, "visualId": "astraBullgryn", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 2, "row": 2}, "effects": []},
        {"id": TARGET_ID, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 3, "row": 3}, "effects": []},
        {"id": ENEMY2_ID, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 3, "row": 2}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": HP_CUR, "hpMax": HP_MAX}
                         for u in decision["units"]]}
    state = load_state(decision, observe, board=board)
    combat = ramming_speed_tile_to_move_to(state, CASTER_ID, TARGET_ID)
    pred = RS.tile_to_move_to(Scene.from_state(state), CASTER_ID, TARGET_ID, (0, 3))
    assert combat is not None and pred is not None
    assert tuple(pred) == tuple(combat)


def test_no_tile_means_no_explosion_batch(monkeypatch):
    """`First(...)` ne designe rien -> les DEUX batchs sont VIDES (le natif n'emet ni erreur ni
    event). La gate reste ouverte : on verifie bien l'absence d'events, pas un court-circuit."""
    sc, _ = _scene()
    _capture(monkeypatch, kill_self=True)
    monkeypatch.setattr(RS, "tile_to_move_to", lambda *a, **k: None)
    evs = PA.make_damage_predictions(sc, CASTER_ID, TARGET_ID, ABILITY, NAME, attack_pos=(0, 3))
    assert [e.target for e in evs] == [TARGET_ID, CASTER_ID]


def test_caster_adjacent_to_the_charge_tile_is_counted_as_a_friend(monkeypatch):
    """L'`origin` de `AdjacentUnits` est une TUILE : l'`op_Subtraction origin` de
    `DSLSelectors$$AdjacentUnits` ne retire AUCUNE unite, donc un caster adjacent a la tuile
    d'arrivee compte dans `Friends` (il est son propre ami). QUIRK NATIF, mirrore tel quel."""
    sc, board = _scene()
    tile = RS.tile_to_move_to(sc, CASTER_ID, TARGET_ID, (0, 3))
    assert tile is not None
    # On DEPLACE le caster sur un voisin LIBRE de la tuile d'arrivee (jamais « bloque par la
    # geometrie de spawn » : la position est choisie, et le test echoue s'il n'y en a aucune).
    occupied = {(u["pos"]["col"], u["pos"]["row"]) for u in sc.units if u["id"] != CASTER_ID}
    near = next(p for p in hexgeo.neighbors(tile[0], tile[1])
                if 0 <= p[0] < COLS and 0 <= p[1] < ROWS
                and p not in occupied and p != tuple(tile))
    for u in sc.units:
        if u["id"] == CASTER_ID:
            u["pos"] = {"col": near[0], "row": near[1]}
    sc.pos_by_id[CASTER_ID] = near
    _capture(monkeypatch, kill_self=True)
    monkeypatch.setattr(RS, "tile_to_move_to", lambda *a, **k: tile)
    evs = PA.make_damage_predictions(sc, CASTER_ID, TARGET_ID, ABILITY, NAME, attack_pos=near)
    expl = evs[2:]
    assert CASTER_ID in [e.target for e in expl], (
        "le caster adjacent a la tuile d'arrivee DOIT figurer dans le batch `Friends`")
    assert all(e.friendly for e in expl if e.target == CASTER_ID)


# ------------------------------------------------------ D : `scene_tile_leaf_ctx` (le 3e jumeau)

def test_scene_leaf_ctx_partitions_by_team_of_the_subject():
    """`RammingSpeed_MostAdjacentEnemies` compte `GetAdjacentEnemies(tile, case.unit, false)`, dont
    le camp est resolu par `OwnerComponent.get_CurrentPlayerEntityId(case.unit)`. Le ctx doit donc
    partitionner par EQUIPE DU SUJET -- pris du point de vue d'une unite de l'AUTRE camp, les deux
    listes s'ECHANGENT. (La face decision lit `ctrl` : ce serait FAUX pour un caster adverse.)"""
    from engine.utilities.tile import scene_tile_leaf_ctx
    sc, _ = _scene()
    mine = scene_tile_leaf_ctx(sc, CASTER_ID)
    theirs = scene_tile_leaf_ctx(sc, TARGET_ID)
    assert {u["id"] for u in mine["friend_units"]} == {ALLY_ID}
    assert {u["id"] for u in mine["enemy_units"]} == {TARGET_ID, ENEMY2_ID}
    assert {u["id"] for u in theirs["friend_units"]} == {ENEMY2_ID}
    assert {u["id"] for u in theirs["enemy_units"]} == {CASTER_ID, ALLY_ID}
    assert mine["uid"] == CASTER_ID and mine["is_spawning"] is False


def test_scene_leaf_ctx_without_subject_is_empty():
    """`case.unit == null` cote prediction : aucun call-site SUMMON n'y mene, donc `{}` (et surtout
    pas le regime `is_spawning` de case-205, qui ferait mentir les feuilles gatees)."""
    from engine.utilities.tile import scene_tile_leaf_ctx
    sc, _ = _scene()
    assert scene_tile_leaf_ctx(sc, None) == {}


@pytest.mark.parametrize("key", ["explosion_amount", "tile_to_move_to", "explosion_events"])
def test_module_degrades_when_the_caster_is_absent(key):
    """Caster hors scene -> `None`/`[]` selon la fonction, jamais une exception ni un event invente."""
    sc, _ = _scene()
    fn = getattr(RS, key)
    got = (fn(sc, 999, TARGET_ID, (0, 3)) if key != "explosion_events"
           else fn(sc, 999, TARGET_ID, ABILITY, NAME, (0, 3)))
    assert got in (None, []) or got == []
