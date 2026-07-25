"""#84 volet 1 -- LetTheGalaxyBurn : le COUP ADDITIONNEL (trait 1058 -> triggered 1482 -> effet 1477).

Chaine PORTEE (decompile ghidra, build gqfc5mff6c) :
  - `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits` -> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create`
    { condition = `OwnerIsCaster & (IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$TargetHasTileEffect | IdunBattleLogic.Entities.DSLFactory$$IsPersistentData(0x5ca))`,
      degat = `FirstHitInCurrentAttackDamageRange`, profil = -1 (NULL), count = noeud NULL -> 1 } ;
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger` = `On(5=PreAttack) & OwnerIsCaster &
    Maybe(ConfigConst 0x2a = traitVariables.LetTheGalaxyBurnChancePct=33) & !HasTileStatusEffect(Targets)` ;
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateBehaviour` = `SetPersistentData(0x5ca, Self, key, 1)` ;
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour` = `... + ClearPersistentData(0x5ca, Self, key)`
    (le volet `AddEffect(0x5c4=1476 DespoiledGround)` du meme behaviour = VOLET 2, non porte).

Ce que ces tests PROUVENT, en confrontant le NATIF (aucune constante de coups en dur -- la base est
MESUREE sur le live, et les assertions portent sur des RELATIONS) :
  (1) LIVE, les DEUX branches du gate : cible sur tuile SANS status-effect -> le nb de coups oscille
      entre `base` et `base+1` (roll 33 %) ; cible sur tuile AVEC status-effect -> `base+1`
      SYSTEMATIQUE. Et JAMAIS `base+2` (count node NULL = 1 coup, pas N).
  (2) OFFLINE, que le maillon est POSE **et** LU (anti no-op silencieux) : rejouer N attaques via le
      Runner produit la meme oscillation `{base, base+1}` a la meme frequence, le flag persistant est
      TOUJOURS efface apres l'attaque (Reset), et deux COUNTERFACTUELS load-bearing :
        - effet 1477 retire de l'attaquant  -> plus AUCUN `base+1` ;
        - tuile de la cible forcee a un status-effect -> `base+1` a 100 % ET aucune pose (gate exclusif).
  (3) que le canal est bien branche cote PREDICTION : la formule PARTAGEE
      `attack_hits_with_modifiers` (facade `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`) rend `base+1`
      quand `tile_effects_by_pos` porte un effet sur la tuile de la cible, `base` sinon -- c'est
      EXACTEMENT le threading qui manquait (sans lui, l'IA sous-estimerait l'attaque d'un porteur).

Drive les positions (memoire « drive positions, don't blame geometry »). Lit l'etat LIVE ; aucune
tuile/RVA hardcodee. ASCII-only.
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.loki import LET_THE_GALAXY_BURN_PERSISTENT_KEY
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import (UnitComponent, PositionComponent, HealthComponent,
                                      StatsComponent, PersistentDataComponent)
from engine.services.attack_hits_formula import attack_hits_with_modifiers
from engine.runner.damage_model import build_hits_board

CARRIER = "blackTerminator"        # Angrax -- porteur du TRAIT LetTheGalaxyBurn (1058), arme Power melee
TARGET = "bloodSanguinary"
HP = "900000"                      # la cible survit a des dizaines d'attaques (on compte des COUPS)
BUILD = ["--p-units", CARRIER, "--a-units", TARGET, "--hp-target", HP, "--hp-player", HP]
LIVE_ROUNDS = 14                   # borne du round-cap d'un runner
OFFLINE_N = 300


# ------------------------------------------------------------------ helpers

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _find_by_vis(state, vis):
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == vis:
            return uid
    return None


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


@pytest.fixture(scope="module")
def ltgb_runner(rpc, build_runner):
    """Runner 1v1 Angrax (porteur) vs une cible tres tanky, board fixe."""
    rid = build_runner("84001", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    me = next((u for u in (dv.get("units") or [])
               if u.get("alive") and u.get("visualId") == CARRIER), None)
    if me is None:
        pytest.skip(f"{CARRIER} absent du build")
    names = [e.get("name") for e in (me.get("effects") or [])]
    if "LetTheGalaxyBurn" not in names:
        pytest.skip(f"effet LetTheGalaxyBurn absent du porteur live (effets: {names})")
    return {"rid": rid, "board": board}


# ------------------------------------------------------------------ (1) LIVE : les 2 branches du gate

def test_ltgb_live_gate_two_branches(rpc, ltgb_runner):
    """LIVE. Le porteur attaque en boucle la MEME cible ; on note, AVANT chaque attaque, les
    status-effects de la TUILE de la cible (`tileMeta`), et on compte les evenements de degat.

    Le tile-effect de la branche B apparait TOUT SEUL : c'est le volet 2 du meme kit
    (`LetTheGalaxyBurn_ResetAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour pose `DespoiledGround` quand le flag etait arme).

    Assertions (relations, pas de constante) :
      - l'ensemble des comptes observes est inclus dans {base, base+1} -> le count node NULL vaut
        bien 1 coup (et non `nrOfHits` comme chez MasterAnnihilator) ;
      - branche B (tuile a status-effect) : TOUS les echantillons valent base+1 (gate deterministe) ;
      - branche A : au moins un echantillon a `base` (le roll 33 % echoue parfois) ;
      - la branche B a bien ete atteinte (sinon le test ne prouve rien -> skip explicite)."""
    rid, board = ltgb_runner["rid"], ltgb_runner["board"]

    def dview():
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

    def tile_fx():
        tm = rpc("tileMeta", {"runnerId": rid}, 60)
        return {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
                for t in (tm.get("tiles") or [])}

    dv = dview()
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    me = next((u for u in units if u.get("visualId") == CARRIER), None)
    en = next((u for u in units if u.get("id") != (me or {}).get("id")), None)
    if me is None or en is None:
        pytest.skip("1v1 attendu")
    myp, aid, tid = me.get("owner"), me["id"], en["id"]
    norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("pas d'attaque normale")
    walk = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]

    rows = []
    for _ in range(LIVE_ROUNDS):
        for _ in range(6):
            dv = dview()
            if dv.get("currentPlayer") == myp:
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        else:
            break
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        me = next((u for u in units if u.get("id") == aid), None)
        en = next((u for u in units if u.get("id") == tid), None)
        if me is None or en is None:
            break
        T = _upos(en)
        nb = [c for c in walk if T is not None and hexgeo.distance(c, T) == 1]
        if not nb:
            break
        if _upos(me) not in nb:            # DRIVE : on colle l'attaquant a la cible (melee)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": aid, "to": {"col": nb[0][0], "row": nb[0][1]}}}, 40)
        fx_before = tile_fx().get(T) or []
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": aid, "targetId": tid, "abilityType": norm["id"]}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        n = 0
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == norm["id"]:
                n += 1
        if n:
            rows.append((tuple(fx_before), n))
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    if len(rows) < 6:
        pytest.skip(f"pas assez d'attaques live exploitables ({len(rows)})")
    hits = [n for _fx, n in rows]
    base = min(hits)
    a_rows = [n for fx, n in rows if not fx]
    b_rows = [n for fx, n in rows if fx]
    print(f"\n[LTGB live] base={base} n={len(rows)} | A(sans tile-fx) n={len(a_rows)} {a_rows} "
          f"| B(avec tile-fx) n={len(b_rows)} {b_rows}")

    assert set(hits) <= {base, base + 1}, \
        f"le canal ajoute autre chose que +1 coup: comptes observes {sorted(set(hits))} (base={base})"
    assert a_rows and min(a_rows) == base, \
        f"branche A: aucun echantillon a la base -> le gate 'sans tile-effect' ne serait pas conditionnel ({a_rows})"
    if not b_rows:
        pytest.skip("branche TargetHasTileEffect jamais atteinte sur ce run (roll 33% + expiration)")
    assert all(n == base + 1 for n in b_rows), \
        f"branche B (cible sur tuile a status-effect): attendu {base + 1} partout, obtenu {b_rows}"


# ------------------------------------------------------------------ (2) OFFLINE : POSE + LECTURE + clear

@pytest.fixture(scope="module")
def ltgb_state(rpc, ltgb_runner):
    """Etat LIVE du runner charge offline (rejouable a volonte)."""
    rid, board = ltgb_runner["rid"], ltgb_runner["board"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)

    def build_state():
        st = load_state(dv, ob, snap, board=board)
        st.rng = _seed_rng(rng0) if (isinstance(rng0, dict) and rng0.get("mt")) \
            else IntBasedMersenneTwister()
        if not (isinstance(rng0, dict) and rng0.get("mt")):
            st.rng.init_genrand(84001)
        return st
    if _find_by_vis(build_state(), CARRIER) is None:
        pytest.skip(f"{CARRIER} absent de l'etat charge")
    return {"build_state": build_state, "board": board}


def _melee_setup(st, board, aid, tid):
    """DRIVE : colle l'attaquant sur un voisin marchable de la cible, cible rendue immortelle."""
    tp = st.entities[tid].get_component(PositionComponent)
    ttile = board.id_at(tp.col, tp.row)
    nb = [board.coord(t) for t in board.neighbours(ttile) if board.walkable(t)]
    assert nb, "aucun voisin marchable de la cible"
    ap = st.entities[aid].get_component(PositionComponent)
    ap.col, ap.row = nb[0]
    return st.entities[tid].get_component(HealthComponent)


def _replay(st, board, aid, tid, n):
    """Rejoue n attaques normales via le Runner (= le chemin qui emet PreAttack(5) puis Attack(9))."""
    thc = _melee_setup(st, board, aid, tid)
    runner = Runner(st).install_default_handlers(20)
    hits, leaked = [], 0
    for _ in range(n):
        thc.hp = 10 ** 9
        runner.apply(AttackUnitMessage(attacker_id=aid, target_id=tid))
        last = runner.damage_handler.last
        if last is None:
            break
        hits.append(last["hits"])
        pdc = st.entities[aid].get_component(PersistentDataComponent)
        if pdc is not None and pdc.data:
            leaked += 1
    return hits, leaked


def test_ltgb_offline_arm_read_and_clear(ltgb_state):
    """OFFLINE (anti no-op silencieux). Le maillon `On(PreAttack=5)` -> `SetPersistentData` ->
    canal `CreateAdditionalHits` -> `On(Attack=9)` -> `ClearPersistentData` est-il reellement
    parcouru ? Trois faits mesures + deux counterfactuels."""
    board = ltgb_state["board"]
    st = ltgb_state["build_state"]()
    aid = _find_by_vis(st, CARRIER)
    tid = next(u for u in st.entities if u != aid)
    sc = st.entities[aid].get_component(StatsComponent)
    assert "LetTheGalaxyBurn" in (sc.ctx.traits or []), \
        f"le porteur n'a pas le trait offline (traits={sc.ctx.traits})"

    hits, leaked = _replay(st, board, aid, tid, OFFLINE_N)
    base = min(hits)
    k = sum(1 for h in hits if h > base)
    pct = 100.0 * k / max(1, len(hits))
    print(f"\n[LTGB offline] n={len(hits)} base={base} distinct={sorted(set(hits))} "
          f"base+1={k} ({pct:.1f}%) flags_non_effaces={leaked}")

    assert set(hits) <= {base, base + 1}, f"comptes offline hors {{base, base+1}}: {sorted(set(hits))}"
    assert leaked == 0, \
        f"{leaked} attaques laissent le flag persistant pose -> `ClearPersistentData` IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour non atteint"
    # La chance est un tirage : borne LARGE autour du 33 % de config (n=300 -> +-8 pts a 3 sigma).
    assert 15.0 <= pct <= 55.0, \
        f"frequence du +1 offline {pct:.1f}% incompatible avec Maybe(LetTheGalaxyBurnChancePct=33)"

    # COUNTERFACTUEL 1 : sans l'effet 1477 sur l'attaquant, plus AUCUN +1 (le canal est load-bearing).
    st2 = ltgb_state["build_state"]()
    st2.effects.by_unit[aid] = [e for e in st2.effects.by_unit.get(aid, [])
                                if e.name != "LetTheGalaxyBurn"]
    hits2, _ = _replay(st2, board, aid, tid, 120)
    print(f"[LTGB offline] sans l'effet 1477 : distinct={sorted(set(hits2))}")
    assert set(hits2) == {base}, \
        f"le +1 subsiste sans l'effet LetTheGalaxyBurn -> il vient d'ailleurs ({sorted(set(hits2))})"

    # COUNTERFACTUEL 2 : cible posee sur une tuile a status-effect -> +1 a 100 % ET aucune pose
    # (`!HasTileStatusEffect` du trigger IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger rend le gate EXCLUSIF).
    st3 = ltgb_state["build_state"]()
    tp = st3.entities[tid].get_component(PositionComponent)
    ttile = board.id_at(tp.col, tp.row)
    # `effect_type=5` (Fire) OBLIGATOIRE : `HasTileStatusEffect` filtre par EffectType via le set
    # `StaticBattleRules.Effect$$IsTileStatusEffect` (#102) -- un stub `effect_type=None` n'est PAS
    # un status de tuile pour le natif, et n'arme donc pas le gate.
    st3.effects.by_unit.setdefault(int(ttile), []).append(
        BaseEffect(name="Fire", effect_type=5))          # un status-effect de TUILE quelconque
    hits3, leaked3 = _replay(st3, board, aid, tid, 60)
    print(f"[LTGB offline] cible sur tuile a status-effect : distinct={sorted(set(hits3))} "
          f"flags_poses={leaked3}")
    assert set(hits3) == {base + 1}, \
        f"branche TargetHasTileEffect non deterministe offline: {sorted(set(hits3))}"
    assert leaked3 == 0, "le trigger a pose le flag alors que la cible est deja sur une tuile a effet"


# ------------------------------------------------------------------ (3) FACE PREDICTION (threading)

def test_ltgb_prediction_channel_is_wired(ltgb_state):
    """La formule PARTAGEE `attack_hits_with_modifiers` (= facade `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` cote decision) doit rendre `base+1` quand la tuile de la CIBLE porte un status-effect.
    Sans le threading `tile_effects_by_pos` (l'objet de #84), elle rendrait `base` -> l'IA
    sous-estimerait de 1/base l'attaque de tout porteur Black Legion."""
    board = ltgb_state["board"]
    st = ltgb_state["build_state"]()
    aid = _find_by_vis(st, CARRIER)
    tid = next(u for u in st.entities if u != aid)
    _melee_setup(st, board, aid, tid)
    ap = st.entities[aid].get_component(PositionComponent)
    tp = st.entities[tid].get_component(PositionComponent)
    a_pos, t_pos = (ap.col, ap.row), (tp.col, tp.row)
    sc = st.entities[aid].get_component(StatsComponent)
    from engine.runner.damage_model import select_weapon_pierce
    from engine.entities.stats import StatType
    _pierce, _ranged, whits = select_weapon_pierce(sc.ctx, 1)
    hb, auras, tgt_eff = build_hits_board(st, aid, tid, a_pos, t_pos, is_melee=True)
    att_eff = st.effects.active_effects(aid, {"hp": None})

    def calc(tfx):
        return attack_hits_with_modifiers(
            weapon_hits=whits, extra_hits=sc.ctx.stat(StatType.EXTRA_HITS),
            extra_hits_melee=sc.ctx.extra_hits_melee,
            attacker_effects=att_eff, trait_objects=sc.ctx.trait_objects(),
            target_effects=tgt_eff, aura_sources=auras, board=hb,
            is_melee=True, damage_profile="Power",
            include_bonus_hit_behaviours=True, tile_effects_by_pos=tfx)

    base = calc(None)                                    # pas de contexte tuile -> pas de bonus
    empty = calc({t_pos: []})                            # tuile connue SANS effet -> pas de bonus
    onfx = calc({t_pos: ["DespoiledGround"]})            # tuile a status-effect -> +1
    other = calc({(t_pos[0] + 1, t_pos[1] + 1): ["Fire"]})   # effet sur une AUTRE tuile -> pas de bonus
    # #102 : une tuile porte AUSSI des effets qui ne sont PAS des status (Swamp -> BlockEnteringUnits
    # + Thorns_DefenseReduction, mesures live C1_02). `HasTileStatusEffect` les EXCLUT via le set
    # `StaticBattleRules.Effect$$IsTileStatusEffect` -> ils ne doivent PAS armer le +1. Sans ce
    # filtre, le seed des effets de tuile (#102) sur-appliquerait le bonus sur tout board a Swamp.
    nonstatus = calc({t_pos: ["BlockEnteringUnits", "Thorns_DefenseReduction", "Melta_ExtraDmg"]})
    print(f"\n[LTGB pred] base={base} empty={empty} on_tile_fx={onfx} other_tile={other} "
          f"non_status={nonstatus}")

    assert empty == base, "un contexte tuile VIDE ne doit rien ajouter"
    assert other == base, "un status-effect sur une AUTRE tuile ne doit rien ajouter (gate = tuile de la CIBLE)"
    assert nonstatus == base, \
        (f"des effets de tuile NON-status (BlockEnteringUnits/Thorns_DefenseReduction/Melta_ExtraDmg) "
         f"arment le +1 ({nonstatus} vs {base}) -> `IsTileStatusEffect` n'est pas applique")
    assert onfx == base + 1, \
        (f"la prediction n'inclut PAS le coup additionnel LetTheGalaxyBurn quand la cible est sur une "
         f"tuile a status-effect ({onfx} vs {base + 1}) -> canal non threade")
