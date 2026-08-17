"""#84 volet 1 -- LetTheGalaxyBurn : le COUP ADDITIONNEL (trait 1058 -> triggered 1482 -> effet 1477).

Chaine PORTEE (decompile ghidra, build gqfc5mff6c) :
  - `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits` -> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create`
    { condition = `OwnerIsCaster & (IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$TargetHasTileEffect | IdunBattleLogic.Entities.DSLTriggers$$IsPersistentData(0x5ca))`,
      degat = `FirstHitInCurrentAttackDamageRange`, profil = -1 (NULL), count = noeud NULL -> 1 } ;
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger` = `On(5=PreAttack) & OwnerIsCaster &
    Maybe(ConfigConst 0x2a = traitVariables.LetTheGalaxyBurnChancePct=33) & !HasTileStatusEffect(Targets)` ;
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateBehaviour` = `SetPersistentData(0x5ca, Self, key, 1)` ;
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour` = `... + ClearPersistentData(0x5ca, Self, key)`
    (le volet `AddEffect(0x5c4=1476 DespoiledGround)` du meme behaviour = VOLET 2, non porte).

⚠ #227 -- LE COUP SURNUMERAIRE EST UN GROUPE DU CANAL #179, PAS UN COUP D'ARME. Le degat du
descripteur est `FirstHitInCurrentAttackDamageRange` = le `IdunBattle.Core.HitDamage` de l'AttackData
de l'attaque courante (liste `currentAttack@+0x50`, alimentee par `IdunBattle.Operations.
AttackDamageOperation$$ExecuteHits`). Pour une attaque NORMALE ce `HitDamage` est DEGENERE, donc
`IdunBattle.Core.HitDamage$$GetDamage` court-circuite (gate `min == max`) et le coup vaut une
CONSTANTE ; pour une ability bounds-mode il est NON degenere, donc le coup est TIRE (c'est pourquoi
l'ancien modele « +1 coup d'ARME » etait fortuitement juste sur ce vecteur-la, cf. case-bl-1029-1020).

Ce que ces tests PROUVENT, en confrontant le NATIF (aucune constante de coups en dur -- la base est
MESUREE sur le live, et les assertions portent sur des RELATIONS) :
  (1) LIVE, les DEUX branches du gate : cible sur tuile SANS status-effect -> le nb d'evenements de
      degat oscille entre `base` et `base+1` (roll 33 %) ; cible sur tuile AVEC status-effect ->
      `base+1` SYSTEMATIQUE. Et JAMAIS `base+2` (count node NULL = 1 coup, pas N). PLUS : sur les
      attaques armees, le DERNIER evenement est CONSTANT alors que les coups d'arme VARIENT.
  (2) OFFLINE, que le maillon est POSE **et** LU (anti no-op silencieux) : rejouer N attaques via le
      Runner produit la meme oscillation `{base, base+1}` a la meme frequence, le flag persistant est
      TOUJOURS efface apres l'attaque (Reset), et deux COUNTERFACTUELS load-bearing :
        - effet 1477 retire de l'attaquant  -> plus AUCUN `base+1` ;
        - tuile de la cible forcee a un status-effect -> `base+1` a 100 % ET aucune pose (gate
          exclusif), le coup de groupe valant alors une CONSTANTE.
  (3) le CONTRAT DU CANAL, les deux faces : la formule de coups partagee
      `attack_hits_with_modifiers` (facade `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`)
      ne bouge PLUS, et `additional_hit_groups` rend un groupe d'UN coup a profil NULL -- rien du
      tout quand aucune attaque n'est en cours, ce qui EST la face PREDICTION.

Drive les positions (memoire « drive positions, don't blame geometry »). Lit l'etat LIVE ; aucune
tuile/RVA hardcodee. ASCII-only.
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.entities.effect_type import EffectType
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.loki.hits import LET_THE_GALAXY_BURN_PERSISTENT_KEY
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
        amounts = []
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == norm["id"]:
                amounts.append(int(td["Amount"]))
        if amounts:
            rows.append((tuple(fx_before), amounts))
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    if len(rows) < 6:
        pytest.skip(f"pas assez d'attaques live exploitables ({len(rows)})")
    hits = [len(a) for _fx, a in rows]
    base = min(hits)
    a_rows = [len(a) for fx, a in rows if not fx]
    b_rows = [len(a) for fx, a in rows if fx]
    print(f"\n[LTGB live] base={base} n={len(rows)} | A(sans tile-fx) n={len(a_rows)} {a_rows} "
          f"| B(avec tile-fx) n={len(b_rows)} {b_rows}")

    assert set(hits) <= {base, base + 1}, \
        f"le canal ajoute autre chose que +1 coup: comptes observes {sorted(set(hits))} (base={base})"
    assert a_rows and min(a_rows) == base, \
        f"branche A: aucun echantillon a la base -> le gate 'sans tile-effect' ne serait pas conditionnel ({a_rows})"

    # #227 -- LE COUP SURNUMERAIRE EST UNE CONSTANTE (vecteur ATTAQUE NORMALE). Il sort d'un GROUPE
    # du canal #179, execute APRES la boucle d'arme, dont le `HitDamage` est celui de l'AttackData
    # -- DEGENERE pour une attaque normale, donc `IdunBattle.Core.HitDamage$$GetDamage` court-circuite
    # (gate `min == max`) : il ne reste que la reduction. Les coups d'ARME de la MEME attaque, eux,
    # sont tires. C'est le contrefactuel qui refute le modele « +1 coup d'ARME ».
    armed = [a for _fx, a in rows if len(a) == base + 1]
    if len(armed) >= 2:
        lasts = [a[-1] for a in armed]
        weapon = sorted({v for _fx, a in rows for v in a[:base]})
        print(f"[LTGB live] dernier evenement des attaques ARMEES : {lasts} "
              f"(coups d'ARME observes : [{weapon[0]}..{weapon[-1]}], {len(weapon)} valeurs distinctes)")
        assert len(set(lasts)) == 1, \
            (f"le coup surnumeraire live VARIE {sorted(set(lasts))} -> il serait TIRE ; le natif rend "
             f"une constante (HitDamage degenere de l'attaque normale)")
        assert len(weapon) > 1, "coups d'arme tous identiques -> le contrefactuel n'est pas discriminant"

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


def _replay(st, board, aid, tid, n, despoil_decay=True):
    """Rejoue n attaques normales via le Runner (= le chemin qui emet PreAttack(5) puis Attack(9)).

    Rend `(evenements_de_degat, valeurs_du_groupe_#179, flags_non_effaces)`. #227 : le coup
    `LetTheGalaxyBurn` n'est PAS un coup d'arme -- c'est un GROUPE du canal #179 (descripteur
    `IdunBattle.Entities.Effects.EffectAdditionalHits`, execute par `IdunBattle.Operations.
    AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` APRES la boucle d'arme).
    L'observable comparable au LIVE est donc la SOMME des deux canaux : coups d'arme + coups de
    groupe, dans cet ordre.

    `despoil_decay` (#BL-1029r-r1) -- CE MONTAGE REJOUE N ATTAQUES DANS LE MEME TOUR, et c'est ce
    qui rend le parametre necessaire. Depuis que le **volet 2** du reset est porte
    (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour`
    -> `AddEffect(0x5c4 = 1476 DespoiledGround)` sur la tuile de la cible), une attaque a succes
    DESPOILE la tuile ; l'attaque suivante y trouve alors un status-effect et prend la branche
    GAUCHE du gate (`TargetHasTileEffect`), qui rend le coup CERTAIN. La chaine s'auto-alimente
    donc, et un rejeu SANS decroissance mesure 98,7 % de `base+1` au lieu du 33 % du `Maybe` --
    ce qui est le comportement NATIF, pas un bug (i2 : « If the attacked unit is already on a hex
    with a hex effect, the attack automatically scores an additional hit »).
    Le natif fait expirer l'effet (`StaticBattleRules.Effect$$DefaultAmountOfRounds(0x5c4)` = 2
    rounds) ; ce montage ne fait passer AUCUN tour. `despoil_decay=True` retire donc le
    `DespoiledGround` de la tuile de la cible entre deux attaques -- c'est le mirror de cette
    expiration, et c'est ce qui laisse le regime BRANCHE A (le `Maybe`) observable.
    `despoil_decay=False` mesure l'autre regime, celui de l'auto-alimentation."""
    thc = _melee_setup(st, board, aid, tid)
    tp = st.entities[tid].get_component(PositionComponent)
    ttile = board.id_at(tp.col, tp.row)
    runner = Runner(st).install_default_handlers(20)
    hits, grp, leaked = [], [], 0
    for _ in range(n):
        thc.hp = 10 ** 9
        runner.apply(AttackUnitMessage(attacker_id=aid, target_id=tid))
        last = runner.damage_handler.last
        if last is None:
            break
        ah = (last.get("additional_hits") or {}).get("per_hit") or []
        hits.append(last["hits"] + len(ah))
        grp += list(ah)
        pdc = st.entities[aid].get_component(PersistentDataComponent)
        if pdc is not None and pdc.data:
            leaked += 1
        if despoil_decay and ttile is not None:
            st.effects.by_unit[int(ttile)] = [
                e for e in st.effects.by_unit.get(int(ttile), [])
                if e.name != EffectType.DespoiledGround.name]
    return hits, grp, leaked


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

    hits, grp, leaked = _replay(st, board, aid, tid, OFFLINE_N)
    base = min(hits)
    k = sum(1 for h in hits if h > base)
    pct = 100.0 * k / max(1, len(hits))
    print(f"\n[LTGB offline] n={len(hits)} base={base} distinct={sorted(set(hits))} "
          f"base+1={k} ({pct:.1f}%) flags_non_effaces={leaked} groupe#179 distinct={sorted(set(grp))}")

    assert set(hits) <= {base, base + 1}, f"comptes offline hors {{base, base+1}}: {sorted(set(hits))}"
    # #227 : le coup surnumeraire sort du canal #179 (et d'un SEUL groupe d'UN coup), pas de la
    # formule de coups -> autant de coups de groupe que d'attaques a base+1.
    assert len(grp) == k, f"{k} attaques a base+1 mais {len(grp)} coups de groupe #179"
    assert leaked == 0, \
        f"{leaked} attaques laissent le flag persistant pose -> `ClearPersistentData` IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour non atteint"
    # La chance est un tirage : borne LARGE autour du 33 % de config (n=300 -> +-8 pts a 3 sigma).
    assert 15.0 <= pct <= 55.0, \
        f"frequence du +1 offline {pct:.1f}% incompatible avec Maybe(LetTheGalaxyBurnChancePct=33)"

    # COUNTERFACTUEL 1 : sans l'effet 1477 sur l'attaquant, plus AUCUN +1 (le canal est load-bearing).
    st2 = ltgb_state["build_state"]()
    st2.effects.by_unit[aid] = [e for e in st2.effects.by_unit.get(aid, [])
                                if e.name != "LetTheGalaxyBurn"]
    hits2, _g2, _ = _replay(st2, board, aid, tid, 120)
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
    hits3, grp3, leaked3 = _replay(st3, board, aid, tid, 60)
    print(f"[LTGB offline] cible sur tuile a status-effect : distinct={sorted(set(hits3))} "
          f"flags_poses={leaked3} groupe#179 distinct={sorted(set(grp3))}")
    assert set(hits3) == {base + 1}, \
        f"branche TargetHasTileEffect non deterministe offline: {sorted(set(hits3))}"
    assert leaked3 == 0, "le trigger a pose le flag alors que la cible est deja sur une tuile a effet"
    # #227 -- LE point du cas : sur le vecteur ATTAQUE NORMALE, la VALEUR du coup de groupe est une
    # CONSTANTE. Le noeud `FirstHitInCurrentAttackDamageRange` rend le `IdunBattle.Core.HitDamage`
    # de l'AttackData, DEGENERE pour une attaque normale -> `IdunBattle.Core.HitDamage$$GetDamage`
    # court-circuite (gate `min == max`) et il ne reste que la reduction, deterministe. L'ancien
    # modele (« +1 coup d'ARME ») TIRAIT dans la cellule d'arme : c'est exactement ce que cette
    # assertion interdit de reintroduire.
    assert len(set(grp3)) == 1, \
        (f"le coup de groupe LetTheGalaxyBurn VARIE offline ({sorted(set(grp3))}) -> le port tire "
         f"la ou le natif rend une constante (HitDamage degenere)")

    # COUNTERFACTUEL 3 (#BL-1029r-r1) : SANS decroissance, la chaine S'AUTO-ALIMENTE. Le volet 2 du
    # reset despoile la tuile de la cible des la premiere attaque a succes ; toutes les suivantes
    # prennent alors la branche GAUCHE du gate (`TargetHasTileEffect`), donc `base+1` CERTAIN et
    # AUCUNE nouvelle pose de flag (`!HasTileStatusEffect` du trigger est faux). C'est le meme fait
    # que le counterfactuel 2, mais atteint par le port LUI-MEME au lieu d'un effet stub -- c'est ce
    # qui manquait, et c'est precisement ce qui privait le cast de Drachnyen de son 10e coup.
    st4 = ltgb_state["build_state"]()
    hits4, _g4, leaked4 = _replay(st4, board, aid, tid, 40, despoil_decay=False)
    pct4 = 100.0 * sum(1 for h in hits4 if h > base) / max(1, len(hits4))
    tp4 = st4.entities[tid].get_component(PositionComponent)
    fx4 = [e.name for e in st4.effects.by_unit.get(int(board.id_at(tp4.col, tp4.row)) or -1, [])
           if not e.consumed]
    print(f"[LTGB offline] sans decroissance : n={len(hits4)} base+1={pct4:.1f}% "
          f"tuile={fx4} flags_non_effaces={leaked4}")
    assert EffectType.DespoiledGround.name in fx4, \
        f"le volet 2 n'a pas despoile la tuile de la cible : {fx4}"
    # La 1re attaque peut echouer son `Maybe` (donc rester a `base`) ; a partir de la 1re reussite
    # tout est `base+1`. Sur 40 attaques a 33 %, la probabilite d'ouvrir sur >= 8 echecs est ~4e-4.
    assert pct4 >= 80.0, \
        (f"la branche TargetHasTileEffect ne s'auto-alimente pas ({pct4:.1f}%) -> le volet 2 pose "
         f"un effet que le gate du coup ne voit pas (tuile={fx4})")
    assert leaked4 == 0, "le flag reste pose alors que la cible est sur une tuile despoilee"


# ------------------------------------------------------------------ (3) FACE PREDICTION (threading)

def test_ltgb_is_an_additional_hits_group_not_a_hits_bonus(ltgb_state):
    """#227 -- CONTRAT DU CANAL, les deux faces.

    L'artefact natif est un descripteur `IdunBattle.Entities.Effects.EffectAdditionalHits` (canal
    #179), PAS un `EffectHitsBonusForAttack`. Deux consequences GARDEES ici :

    (a) `attack_hits_with_modifiers` (= facade `IdunBattle.Core.Services.DamagePrediction$$
        GetAttackHits`, PARTAGEE combat/prediction) ne doit RIEN ajouter -- meme quand la tuile de
        la cible porte un status-effect. Le +1 ne passe plus par la formule de coups.
    (b) `additional_hit_groups` rend UN groupe d'UN coup, `profile` NULL (= profil de l'arme), de
        degat `[HitDamage.min, HitDamage.max]` de l'attaque courante -- et RIEN quand ce
        `attack_hit_damage` est absent, ce qui est TOUJOURS le cas cote PREDICTION
        (`IdunBattle.Entities.Abilities.AActiveAbility$$GetAdditionalHitsFromEffectsForPrediction`
        tourne hors `OngoingAttack` -> `FirstHitInCurrentAttackDamageRange` rend 0 -> coup a 0
        degat = no-op numerique).

    Le gate lui-meme (les DEUX branches + le filtre `IsTileStatusEffect`) est re-garde ici, sur son
    nouveau porteur."""
    from engine.entities.effects import additional_hit_groups
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
    atk = int(sc.ctx.stat(StatType.ATTACK))
    armed_keys = frozenset({LET_THE_GALAXY_BURN_PERSISTENT_KEY})

    # --- (a) la FORMULE DE COUPS ne doit plus bouger, quel que soit l'etat de la tuile ---
    hits = attack_hits_with_modifiers(
        weapon_hits=whits, extra_hits=sc.ctx.stat(StatType.EXTRA_HITS),
        extra_hits_melee=sc.ctx.extra_hits_melee,
        attacker_effects=att_eff, trait_objects=sc.ctx.trait_objects(),
        target_effects=tgt_eff, aura_sources=auras, board=hb,
        is_melee=True, damage_profile="Power", include_bonus_hit_behaviours=True)
    assert hits == whits + sc.ctx.stat(StatType.EXTRA_HITS) + sc.ctx.extra_hits_melee, \
        (f"la formule de coups rend {hits} != base d'arme -> un terme LetTheGalaxyBurn y subsiste "
         f"(il doit vivre dans le canal #179)")

    # --- (b) le CANAL #179 : gate x contexte ---
    def grp(**over):
        ctx = {"is_melee": True, "t_pos": t_pos, "tile_effects_by_pos": None,
               "persistent_data": (), "attack_hit_damage": (atk, atk)}
        ctx.update(over)
        return list(additional_hit_groups(att_eff, ctx))

    g_armed = grp(persistent_data=armed_keys)                    # branche IsPersistentData
    g_tile = grp(tile_effects_by_pos={t_pos: ["DespoiledGround"]})   # branche TargetHasTileEffect
    g_none = grp()                                               # aucune branche -> rien
    g_pred = grp(persistent_data=armed_keys, attack_hit_damage=None)  # face PREDICTION
    g_other = grp(tile_effects_by_pos={(t_pos[0] + 1, t_pos[1] + 1): ["Fire"]})
    # #102 : une tuile porte AUSSI des effets qui ne sont PAS des status (Swamp -> BlockEnteringUnits
    # + Thorns_DefenseReduction, mesures live C1_02). `HasTileStatusEffect` les EXCLUT via le set
    # `StaticBattleRules.Effect$$IsTileStatusEffect` -> ils ne doivent PAS armer le coup.
    g_nonstatus = grp(tile_effects_by_pos={
        t_pos: ["BlockEnteringUnits", "Thorns_DefenseReduction", "Melta_ExtraDmg"]})
    print(f"\n[LTGB canal] hits_formule={hits} ATTACK={atk} armed={g_armed} tile={g_tile} "
          f"none={g_none} pred={g_pred} other={g_other} nonstatus={g_nonstatus}")

    for name, g in (("IsPersistentData", g_armed), ("TargetHasTileEffect", g_tile)):
        assert g == [{"count": 1, "min": atk, "max": atk, "profile": None}], \
            (f"branche {name}: groupe #179 attendu (1 coup, [{atk},{atk}], profil NULL), obtenu {g}")
    assert g_none == [], f"aucune branche armee -> aucun groupe, obtenu {g_none}"
    assert g_other == [], "un status-effect sur une AUTRE tuile ne doit rien armer (gate = tuile de la CIBLE)"
    assert g_nonstatus == [], \
        ("des effets de tuile NON-status (BlockEnteringUnits/Thorns_DefenseReduction/Melta_ExtraDmg) "
         "arment le coup -> `IsTileStatusEffect` n'est pas applique")
    assert g_pred == [], \
        ("face PREDICTION (aucune attaque en cours -> `FirstHitInCurrentAttackDamageRange` = 0) : "
         f"le port emet un groupe {g_pred} -> il sur-predirait un coup PLEIN")
