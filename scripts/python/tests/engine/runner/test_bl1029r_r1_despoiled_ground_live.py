"""#BL-1029r-r1 -- le 10e coup du cast de `Drachnyen`, et pourquoi il manquait.

CE QUE CE FICHIER GARDE, ET CE QU'IL A FALLU REFUTER POUR L'ECRIRE
------------------------------------------------------------------
Apres le port de la triggered `1485 Drachnyen_ExtraAttack` (#BL-1029r), le cast d'Abaddon rendait
**9 coups offline contre 10 live**, les 9 premiers BIT-EXACTS. La fiche `case-bl-1029-1020` avait
ECARTE la piste `HasTileStatusEffect` en observant que le `Maybe(33 %)` du trigger de POSE est
evalue AVANT le gate de tuile, donc consomme son tirage dans les deux regimes. C'est vrai de la
CONSOMMATION, et sans rapport avec le VERDICT : le gate du COUP
(`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`) est

    get_OwnerIsCaster & ( TargetHasTileEffect | IsPersistentData(0x5ca, Owner, Get(<statique>)) )

-- une DISJONCTION. La branche gauche rend le coup CERTAIN, sans aucun tirage. Or elle etait
INATTEIGNABLE offline : ce qui l'arme est `DespoiledGround` (EffectType 1476), pose sur la TUILE de
la cible a la CLOTURE de l'attaque precedente par le **volet 2** de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour`,
volet qui n'etait pas porte.

L'ORDRE qui rend la chaine possible est LU, pas suppose :
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteBehaviour` appelle
`$$ExecuteNormalAttack` (qui contient le `FinishAttack` -> `On(9 = Attack)` -> le reset, donc la
pose) **puis** `$$ExecuteTriggerAbilities` (`EvaluateAbilities(0x26 = NormalAttack)` -> la triggered
1485). MESURE LIVE de la cascade (`probe_bl1029r_r1_despoiled_ground.py`) :
`[31] group LetTheGalaxyBurn` -> `[32] group DespoiledGround` -> `[38] group Drachnyen_ExtraAttack`
-> `[49] 1297` + `[51] group LetTheGalaxyBurn`.

LES QUATRE ETAGES
-----------------
  [1] ACCORD LIVE : les 10 coups du cast, offline == live, coup par coup.
  [2] DOMAINE : `DespoiledGround` atterrit sur la TUILE, pas sur l'UNITE (le selecteur du `Foreach`
      est `TargetTiles@DSLSelectors+0x78`, et `IdunBattle.Operations.AddEffectOperation$$Execute`
      ne route RIEN -- il pose sur son parametre `owner` tel quel).
  [3] CONTRE-EPREUVE : volet 2 neutralise -> le 10e coup DISPARAIT et les 9 premiers ne bougent pas.
      Sans cet etage, l'etage [1] ne separerait pas « le port compose le bon coup » de « les deux
      moteurs font la meme chose pour une autre raison ».
  [4] GATE `AttackUsedAttackDamage` (`AbilityEntities+0xf9`, corps ENTIER de
      `IdunBattle.Entities.Triggers.AttackUsedAttackDamageTrigger$$ShouldTrigger`) : un `On(9)` qui
      ne le porte pas ne pose RIEN, meme flag arme.

ASCII-only (cp1252).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test live : la cascade des `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/rl_duel.py", "scripts/python/hexgeo.py",
        "scripts/python/engine/runner/snapshot.py",
        # PERIMETRE PRIS LARGE, et il DOIT l'etre : ce fichier compare une CHAINE ENTIERE (ability
        # 1029 -> attaque normale -> `On(9)` -> reset/volet 2 -> `On(0x26)` -> triggered 1485 ->
        # canal #179), donc quasiment tout `engine/**` peut en changer le verdict. Les foyers
        # load-bearing pour la relecture : `runner/operations/triggers/loki/let_the_galaxy_burn.py`
        # (les deux volets), `runner/operations/triggers/base.py` (le canal
        # `attack_used_attack_damage`), `runner/operations/triggers/dispatch/attack.py` (les deux
        # emetteurs d'`On(9)`), `runner/operations/damage_ops/*.py` (qui le threadent),
        # `runner/operations/additional_hits.py` + `entities/effects/loki/hits.py` (le canal #179),
        # `runner/operations/effects.py` (`DefaultAmountOfRounds`),
        # `services/static_battle_rules.py` (`IsTileStatusEffect`),
        # `runner/abilities/blacklegion.py` + `runner/abilities/behaviours/combat.py`.
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment.
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        # Les valeurs (chance du trait, `nrOfHits`, profils) viennent du gameconfig et des enums du
        # build : un re-dump les change sans toucher a une ligne de `engine/**`.
        "data/symbols/**/frida/enums.tsv",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confront LIVE d'une chaine complete (cast 1029 -> attaque normale -> reset "
              "LetTheGalaxyBurn -> triggered 1485 -> coup additionnel du canal #179) : il monte un "
              "runner et compare coup par coup au natif, donc tout `engine/**` peut le faire "
              "changer de verdict.",
}

import json                                                              # noqa: E402

import pytest                                                            # noqa: E402

import hexgeo                                                            # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.components import PositionComponent                   # noqa: E402
from engine.runner.damage_model import tile_status_effects_by_pos        # noqa: E402
from engine.runner.messages import ActiveAbilityMessage                  # noqa: E402
from engine.runner.operations.triggers import base as trg_base           # noqa: E402
from engine.runner.operations.triggers.loki import let_the_galaxy_burn as LTGB   # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                   # noqa: E402
from engine.runner.runner import Runner                                  # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType               # noqa: E402

ABADDON = "blackAbaddon"
ENEMIES = "necroWarden,necroDestroyer,necroOverlord"
DRACHNYEN = 1029
SEED, BOARD_ID, HP_TARGET = 777, "MC1_67", "500000"


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _tags(ev):
    try:
        return json.loads(ev.get("tags") or "{}")
    except Exception:
        return {}


def _cascade(res):
    out = list(res.get("cascade") or [])
    for a in (res.get("actions") or []):
        out += list(a.get("events") or [])
    return out


def _flat_hits(obj, out=None):
    """Sequence PLATE des coups OFFLINE : toute liste sous une cle `per_hit`, dans l'ordre
    d'insertion des dicts (= l'ordre de composition des sous-attaques). Les coups du canal #179 y
    sont deja concatenes par `execute_additional_hits`."""
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "per_hit" and isinstance(v, list):
                out += [int(x) for x in v if isinstance(x, (int, float))]
            else:
                _flat_hits(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _flat_hits(v, out)
    return out


def _off_cast(build_state, caster_id, target_id):
    """Un cast OFFLINE sur un etat FRAIS et un RNG RECALE -> `(state, last, coups)`."""
    st = build_state()
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=caster_id, target_id=target_id,
                                      ability_type=DRACHNYEN))
    last = runner.ability_handler.last or {}
    return st, last, _flat_hits(last)


@pytest.fixture(scope="module")
def dg(live_session, rpc, build_runner):
    """Montage UNIQUE : Abaddon adjacent a une cible, etat capture AVANT le cast, puis UN cast LIVE.
    Les etages offline rejouent depuis `build_state()` (etat pre-cast + RNG recale)."""
    rid = build_runner(SEED, extra=["--p-units", ABADDON, "--a-units", ENEMIES,
                                    "--board", BOARD_ID, "--hp-target", HP_TARGET])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indispo -- rien n'a ete confronte"
    board = Board(bg["tiles"], adjacency="native_sym")

    def dv():
        return rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 150)

    dec = dv()
    ab = next((u for u in (dec.get("units") or [])
               if u.get("alive") and u.get("visualId") == ABADDON), None)
    assert ab is not None, f"{ABADDON} absent du build"
    for _ in range(12):
        if dec.get("currentPlayer") == ab.get("owner"):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dec = dv()
    alive = [u for u in (dec.get("units") or []) if u.get("alive")]
    ab = next(u for u in alive if u["id"] == ab["id"])
    ens = [u for u in alive if u.get("owner") != ab.get("owner")]
    assert ens, "aucun ennemi -- geometrie non montable"
    # ANCRE sur la tuile COURANTE du caster : le deplacer consommerait son activation et le cast
    # serait refuse. On ne bouge que l'ennemi.
    C = _upos(ab)
    occ = {_upos(u) for u in alive} - {C}
    nb = [board.coord(t) for t in sorted(board.by_id)
          if board.walkable(t) and hexgeo.distance(board.coord(t), C) == 1
          and board.coord(t) not in occ]
    assert nb, f"aucun voisin libre autour de {C} -- geometrie melee non montable"
    tgt_id = ens[0]["id"]
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": tgt_id, "to": {"col": nb[0][0], "row": nb[0][1]}}}, 90)

    dec = dv()
    ab = next(u for u in (dec.get("units") or []) if u["id"] == ab["id"])
    tu = next(u for u in (dec.get("units") or []) if u["id"] == tgt_id)
    T = _upos(tu)
    assert hexgeo.distance(_upos(ab), T) == 1, f"cible non adjacente : {_upos(ab)} vs {T}"

    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    fx_before = {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
                 for t in (tm.get("tiles") or [])}
    # La branche gauche du gate ne doit PAS etre deja armee au depart, sinon l'etage [3] ne
    # discriminerait rien (le coup partirait de toute facon).
    assert EffectType.DespoiledGround.name not in (fx_before.get(T) or []), \
        f"tuile cible deja despoilee au montage : {fx_before.get(T)}"

    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)

    def build_state():
        st = load_state(dec, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            st.rng = _seed_rng(rng0)
        return st

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": ab["id"], "targetId": tgt_id,
        "abilityType": DRACHNYEN}}, 240)
    a0 = ((res or {}).get("actions") or [{}])[0]
    assert a0.get("ok"), f"cast 1029 KO live : {json.dumps(a0)[:400]}"
    casc = _cascade(res)
    # On ECARTE les evenements qui portent un `Effect_Type` : le tick de fin de tour de la tuile
    # despoilee (`EnvDespoiledGroundTileDamage`, `Effect_Type: 1476`) n'est PAS un coup du cast.
    live_hits = [int(t["Amount"]) for t in (_tags(ev) for ev in casc)
                 if t.get("Amount") is not None and t.get("Target_Id") == tgt_id
                 and t.get("Effect_Type") is None]
    tm2 = rpc("tileMeta", {"runnerId": rid}, 60)
    fx_after = {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
                for t in (tm2.get("tiles") or [])}
    dec2 = dv()
    live_unit_fx = [e.get("name") for u in (dec2.get("units") or []) if u["id"] == tgt_id
                    for e in (u.get("effects") or [])]
    return {"rid": rid, "board": board, "build_state": build_state,
            "caster_id": ab["id"], "target_id": tgt_id, "tpos": T,
            "live_hits": live_hits, "tile_fx_after": fx_after.get(T) or [],
            "unit_fx_after": live_unit_fx,
            "group_sources": [ev.get("source") for ev in casc if ev.get("kind") == "group"]}


# =================================================================== [1] ACCORD LIVE

def test_ten_hits_offline_matches_live(dg):
    """Les coups du cast, offline == live, COUP PAR COUP. Le dernier est le coup additionnel
    `LetTheGalaxyBurn` de l'extra attack (celui qui manquait) : il n'existe que si la tuile de la
    cible porte deja `DespoiledGround` quand l'extra attack demarre."""
    _st, last, off = _off_cast(dg["build_state"], dg["caster_id"], dg["target_id"])
    assert last.get("ported") is True, f"1029 non routee par le registre de combat : {last}"
    # ANTI-VACUITE : un accord entre deux listes vides serait vert et ne prouverait rien.
    assert len(dg["live_hits"]) >= 10, \
        (f"montage degenere : {len(dg['live_hits'])} coup(s) live seulement -- "
         f"groupes={dg['group_sources'][:12]}")
    assert off == dg["live_hits"], (f"coups offline != live\n  offline={off}\n  live   ="
                                    f"{dg['live_hits']}")


# =================================================================== [2] DOMAINE : TUILE, pas UNITE

def test_despoiled_ground_lands_on_the_tile_not_on_the_unit(dg):
    """`Foreach(TargetTiles@DSLSelectors+0x78, ... AddEffect(1476, cibles = Current@+0x68))` : l'effet
    va sur la TUILE. Confronte des deux cotes -- `IdunBattle.Operations.AddEffectOperation$$Execute`
    ne route rien, il pose sur son parametre `owner` tel quel, donc un `Foreach` sur des UNITES
    aurait mis l'effet sur l'unite."""
    st, last, _off = _off_cast(dg["build_state"], dg["caster_id"], dg["target_id"])
    off_tile_fx = (tile_status_effects_by_pos(st, [dg["tpos"]]) or {}).get(tuple(dg["tpos"])) or []
    assert EffectType.DespoiledGround.name in off_tile_fx, \
        f"volet 2 non pose offline sur la tuile {dg['tpos']} : {off_tile_fx}"
    assert EffectType.DespoiledGround.name in dg["tile_fx_after"], \
        f"volet 2 absent de la tuile LIVE {dg['tpos']} : {dg['tile_fx_after']}"
    assert EffectType.DespoiledGround.name not in dg["unit_fx_after"], \
        f"LIVE : l'effet est sur l'UNITE, pas sur la tuile : {dg['unit_fx_after']}"
    # cote port aussi : l'unite ne doit PAS le porter
    off_unit_fx = [e.name for e in (st.effects.by_unit.get(int(dg["target_id"])) or [])
                   if not e.consumed and e.name]
    assert EffectType.DespoiledGround.name not in off_unit_fx, \
        f"OFFLINE : l'effet est sur l'UNITE, pas sur la tuile : {off_unit_fx}"
    # le RESET a bien rendu l'id de tuile qu'il a despoilee (canal de tracabilite du port)
    resets = [p for p in _walk_resets(last) if p.get("cleared")]
    assert resets and resets[0].get("despoiled_tile") is not None, \
        f"aucun reset LetTheGalaxyBurn n'a rendu de tuile despoilee : {resets}"


def _walk_resets(obj, out=None):
    """Tous les retours de `LetTheGalaxyBurnResetAbility.execute_behaviour` du cast."""
    if out is None:
        out = []
    if isinstance(obj, dict):
        if obj.get("trait") == "LetTheGalaxyBurn" and "cleared" in obj:
            out.append(obj)
        for v in obj.values():
            _walk_resets(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_resets(v, out)
    return out


# =================================================================== [3] CONTRE-EPREUVE

def test_without_the_despoil_volet_the_tenth_hit_disappears(dg, monkeypatch):
    """VOLET 2 NEUTRALISE -> le 10e coup DISPARAIT, et les 9 premiers ne bougent PAS d'un bit.

    C'est l'etat EXACT d'avant #BL-1029r-r1 (mesure de `case-bl-1029-1020` §7.1 : 9 coups offline
    contre 10 live). Sans cet etage, l'accord de [1] ne separerait pas « le port compose le bon
    coup » de « les deux moteurs coincident pour une autre raison ».

    Le patch mord parce que `execute_behaviour` resout `_despoil_target_tile` comme un GLOBAL de son
    module a chaque appel (forme B) -- une liaison `from ... import` gelee ne mordrait pas."""
    ref, _l, off_ref = _off_cast(dg["build_state"], dg["caster_id"], dg["target_id"])
    assert len(off_ref) >= 10, f"reference degeneree : {off_ref}"
    monkeypatch.setattr(LTGB, "_despoil_target_tile", lambda *a, **k: None)
    st, last, off_mut = _off_cast(dg["build_state"], dg["caster_id"], dg["target_id"])
    # le mutant MORD : un coup en moins, et c'est le DERNIER
    assert len(off_mut) == len(off_ref) - 1, \
        (f"le mutant n'a pas mordu : {len(off_mut)} coup(s) contre {len(off_ref)}\n"
         f"  ref={off_ref}\n  mut={off_mut}")
    assert off_mut == off_ref[:-1], \
        f"le mutant a deplace autre chose que le dernier coup\n  ref={off_ref}\n  mut={off_mut}"
    # et il RESTE INERTE la ou il doit l'etre : la tuile n'est plus despoilee, rien d'autre ne change
    mut_tile_fx = (tile_status_effects_by_pos(st, [dg["tpos"]]) or {}).get(tuple(dg["tpos"])) or []
    assert EffectType.DespoiledGround.name not in mut_tile_fx, \
        f"le mutant n'a pas neutralise la pose : {mut_tile_fx}"
    assert [p.get("cleared") for p in _walk_resets(last)] == [True] * len(_walk_resets(last)), \
        "le mutant a aussi casse le CLEAR (il ne doit toucher que le volet 2)"


# =================================================================== [4] GATE AttackUsedAttackDamage

def test_gate_attack_used_attack_damage_blocks_the_pose(dg):
    """`AttackUsedAttackDamage` (`AbilityEntities+0xf9`) est un CONJOINT du `If` du volet 2 : un
    `On(9 = Attack)` qui ne le porte pas ne pose RIEN, meme flag arme -- et il efface quand meme le
    flag (le `ClearPersistentData` est HORS du `If`, donc inconditionnel).

    Le natif lit un `byte` BRUT d'un `AbilityEntities` `memset` a 0 : `None` cote port se lit donc
    FAUX, ce n'est pas une degradation."""
    st = dg["build_state"]()
    caster, target = int(dg["caster_id"]), int(dg["target_id"])
    e = st.get_entity(target)
    pc = e.get_component(PositionComponent)
    tile_id = st.board.id_at(pc.col, pc.row)
    assert tile_id is not None, "tuile de la cible introuvable -- rien n'a ete confronte"

    def _armed_reset(flag):
        LTGB._persistent(st, caster).persist_data(LTGB.LET_THE_GALAXY_BURN_PERSISTENT_KEY, 1)
        ev = trg_base.TriggerEvent(int(EventTriggerType.Attack), caster, target,
                                   ranged=False, profile="Power",
                                   attack_used_attack_damage=flag)
        ab = LTGB.LetTheGalaxyBurnResetAbility(caster)
        assert ab.matches(st, ev), "le reset ne matche pas son propre vecteur"
        return ab.execute_behaviour(st, ev)

    out_no = _armed_reset(None)
    assert out_no is not None and out_no.get("cleared") is True, \
        f"le CLEAR doit rester INCONDITIONNEL : {out_no}"
    assert out_no.get("despoiled_tile") is None, \
        f"pose alors que `AttackUsedAttackDamage` est absent : {out_no}"
    fx = (tile_status_effects_by_pos(st, [dg["tpos"]]) or {}).get(tuple(dg["tpos"])) or []
    assert EffectType.DespoiledGround.name not in fx, f"tuile despoilee a tort : {fx}"

    # ANTI-VACUITE : le MEME appel avec le flag POSE, lui, pose bien -- sinon ce test serait vert
    # pour une raison quelconque (montage casse, gate en amont, tuile deja sous status).
    out_yes = _armed_reset(True)
    assert out_yes.get("despoiled_tile") == int(tile_id), \
        f"le flag pose ne suffit pas a declencher le volet 2 : {out_yes}"
