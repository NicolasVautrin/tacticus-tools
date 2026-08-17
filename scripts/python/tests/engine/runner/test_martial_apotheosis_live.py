"""case-220 Necrons : MartialApotheosis (TriggeredAbilityType 1045) FACE COMBAT.

>>> LE PORTEUR N'A JAMAIS DISPARU -- c'est le KIT GAMECONFIG qui a cesse de le nommer (#392).
    Le build `rnca9r7q6c` a retire `MartialApotheosis` du kit de `necroOverlord` (remplacee par
    `MyWillBeDoneOverlord`), et #354 en avait conclu « plus aucun porteur », supprimant les trois
    vecteurs qui passent par `start_turn_triggers`. La conclusion etait FAUSSE, et la mesure est
    dans `probe_392_martial_apotheosis_bc_carrier.py` (5 etages, dont 3 LIVE) :

      * le natif ne lit PAS le kit -- `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`
        enumere `UnitConfiguration.PassiveAbilities` (`config+0xa8`) et appelle
        `IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd(id, passiveAbilityState, 2)` ;
      * `data/seed-bc.json` porte `necroOverlord.PassiveAbilities = [1045]` -- le seul porteur du BC ;
      * le `TriggeredAbilityComponent` REEL du porteur, en runner, rend en hierarchie 2 (Passive) :
        `['1045=MartialApotheosis']` (RPC `unitAbilityStates`) ;
      * LIVE, au turn-start du porteur, l'ennemi drive en anneau-1 encaisse 3702 -- et le MEME
        montage a d=2 encaisse **0**, ce qui ATTRIBUE le degat a une source de portee anneau-1
        (l'objection de `case-354` §3, « un delta > 0 n'attribue rien », est ainsi levee).

    Le decrochage de #354 etait donc un BUG DU PORT (`collect_triggered_abilities` derivait les
    passives du gameconfig par `visualId` au lieu de lire le montage), corrige par #366-r1
    (`21a38550`, canal MESURE `UnitContext.passive_abilities`). Les trois vecteurs supprimes sont
    RESTAURES ici, et la garde d'inertie est reorientee sur la SOURCE REELLE du montage (T0).

RE (decompile, cf. en-tete de `triggers/loki/martial_apotheosis.py`) : la classe native
`MartialApotheosisAbility` ETEND `DestroyerHiveAbility` -> CreateTrigger/GetValidTargets HERITES :
  IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateTrigger = On(TurnStart_Actions=0x16) & OwnerIsActor(@0xa0) & AmountIsGreaterThanZero(
                             GetValidTargets)
  IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$GetValidTargets = Damageable(Enemies(AdjacentUnits(casterTile@0x148, radius=1)))   # anneau-1
  IdunBattleLogic.Entities.Abilities.Active.Loki.MartialApotheosisAbility$$CreateBehaviour = AttackWithAttackDamage(caster, PickRandomly(GetValidTargets, count=1),
                               MinMaxDamage(minDmg/maxDmg[level]), GetDamageProfile(0)="Energy"(pierce 30),
                               GetNumberConstant(0x2f)=nrOfHits=2)   # famille "attack", melee, level passif
= au debut de son tour, si >=1 ennemi adjacent damageable, en attaque UN au hasard, 2 coups Energy.

CE QUI EST VALIDE, sur un etat LIVE (le runner du module fournit un porteur reel et son plateau) :
  (T0) GARDE D'INERTIE, sur la SOURCE REELLE du montage : le canal MESURE
      (`UnitContext.passive_abilities`, hierarchie 2 du `TriggeredAbilityComponent`) nomme
      l'ability, `collect_triggered_abilities` l'instancie pour le porteur, et le kit gameconfig
      NE la nomme PAS -- l'ecart kit/BC est constate, pas subi. Le jour ou le BC cesse de la
      monter, ce test rougit sur le BON canal : c'est alors, et seulement alors, que les vecteurs
      de dispatch (A/C/E) perdent leur sujet.
  (A) VECTEUR TURN-START + OwnerIsActor(@0xa0) : `start_turn_triggers(proprietaire)` dispatche
      l'ability et frappe l'ennemi adjacent ; `start_turn_triggers(adversaire)` est muet.
  (A') meme gate lu par CONSTRUCTION DIRECTE -- independant de l'attribution, il innocente (ou
      accuse) le PORT seul. C'est le couple (A)+(A') qui localise un decrochage a l'etage
      ATTRIBUTION plutot que dans l'arbre DSL ; son absence a coute le faux verdict #354.
  (B) AmountIsGreaterThanZero : 0 ennemi adjacent -> `matches` faux ET dispatch muet, aucun degat.
  (C) CIBLAGE ANNEAU-1 (via le dispatch) : un ennemi a dist 1 est frappe ; un ennemi a dist 2 NE
      l'est PAS (anneau-1, PAS le disque rayon-2 de HarbingerOfDestruction).
  (D) A/B bit-exact + params : pool==1 (deterministe) -> l'arbre == une sequence directe
      `execute_ability_attack` depuis le MEME MT ; params confrontes a l'ORACLE CONFIG (cf. ci-dessous), melee.
  (E) REPLAY-DIFF LIVE : `endturn` vers le turn-start du porteur -> la cible frappee live == la
      cible offline, AUCUN autre ennemi n'est touche (attribution geometrique : la portee du degat
      est l'anneau-1), et le DEGAT est BIT-EXACT (3702 des deux cotes) -- le montage est
      deterministe et `dumpRng` est pris juste avant l'`endturn`, donc le port rejoue depuis le
      MEME MT. #354 declarait ce degat « plus confrontable » ; il l'est.

ORACLE DES PARAMS (#96 -- aucun scalaire de gameplay fige ici). Le decompile TRANCHE : le nb de coups et le
profil sont lus TELS QUELS dans la config d'ability par
`IdunBattleLogic.Entities.Abilities.Active.Loki.MartialApotheosisAbility$$CreateBehaviour`
(`GetNumberConstant(cfg, 0x2f)` et `GetDamageProfile(cfg, 0)` passes directement en arguments de
`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` -- aucune formule),
et `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant` n'est qu'un
`GetStringConstant` + `System.Int32.Parse`. Ce sont donc des valeurs BRUTES -> l'oracle est la CONFIG :
`gameconfig.ability("MartialApotheosis").constants` (`nrOfHits`, `damageProfile`) et
`gameconfig.damage_profile(<profil>).PiercingRatio`. Cle non ambigue : enum `AbilityConstantType`
0x2f=nrOfHits(47) (cf. `engine/entities/formulas.py::ConfigConst`), distinct de 0x16=range(22).
La CONFIG D'ABILITY existe toujours au gameconfig courant malgre le zero-porteur (case-354 etage 2) :
l'oracle reste donc lisible, et (D) reste confrontable.

PIEGE D'ENUM, a ne pas confondre (noms voisins, enums DIFFERENTS) :
    `MartialApotheosis`  = Passive/TriggeredAbilityType **1045**   <- CE fichier
    `MartialInspiration` = ActiveAbilityType **1191**
    `GetEmRuntz`         = ActiveAbilityType **1045** (meme id, autre enum)

Drive les positions (memoire « drive positions, don't blame geometry »). Etat LIVE, aucune RVA/tuile
hardcodee. State-file UNIQUE (chemin absolu + agent id). ASCII-only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import gameconfig as GC

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.abilities.base import ability_attack_params
from engine.runner.operations.triggers.dispatch.turn import start_turn_triggers
from engine.runner.operations.triggers.base import TriggerEvent
from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
from engine.runner.operations.triggers.loki.martial_apotheosis import MartialApotheosisAttackAbility
from engine.dsl.event_trigger_type import EventTriggerType

AGENT_ID = "a2a29ebf31c1e4476"
PYDIR = Path(__file__).resolve().parents[3]                          # scripts/python
ROOT = Path(__file__).resolve().parents[5]                          # racine repo
STATE = ROOT / "logs" / "runners" / f"_pytest_martial_apotheosis_{AGENT_ID}.json"   # SORTIE -> logs/ (#349)

ABILITY = "MartialApotheosis"
CARRIER = "necroOverlord"                                           # porteur HISTORIQUE (retire au build rnca9r7q6c)
ENEMIES = "necroWarden,eldarRanger,eldarAutarch"                    # ennemis (team joueur), tanky + armure 0
HP = "500000"                                                       # --hp-player : survivent + armure 0 (per-coup net)
VOIES = ("passiveAbilities", "activeAbilities", "relicAbilities", "mythicAbilities")


# ------------------------------------------------------------------ oracle CONFIG (cf. en-tete)

def _const(key):
    """Constante de config d'ability = `AbilityConfiguration.GetNumberConstant/GetStringConstant`
    (lecture BRUTE, aucune formule) -> ORACLE des params. None si la cle a disparu de la config."""
    return ((GC.ability(ABILITY) or {}).get("constants") or {}).get(key)


# ------------------------------------------------------------------ helpers etat offline

def _find_by_vis(state, vis):
    from engine.runner.components import UnitComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == vis:
            return uid
    return None


def _owner(state, uid):
    from engine.runner.components import OwnerComponent
    e = state.get_entity(uid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.player if oc is not None else None


def _team(state, uid):
    from engine.runner.components import OwnerComponent
    e = state.get_entity(uid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _enemies_of(state, uid):
    from engine.runner.components import UnitComponent, OwnerComponent
    mine = _team(state, uid)
    out = []
    for oid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None or not uc.alive or oc.team == mine:
            continue
        out.append(oid)
    return sorted(out)


def _pos(state, uid):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _set_pos(state, uid, col, row):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is not None:
        pc.col, pc.row = int(col), int(row)


def _hp(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _park_others(state, board, keep_ids, center):
    """Deplace toute unite VIVANTE hors `keep_ids` loin (dist hex > 4) du centre."""
    from engine.runner.components import UnitComponent
    used = set()
    far = sorted(t for t in board.by_id
                 if board.walkable(t) and hexgeo.distance(board.coord(t), center) > 4)
    it = iter(far)
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uid in keep_ids or uc is None or not uc.alive:
            continue
        for t in it:
            if t not in used:
                used.add(t); _set_pos(state, uid, *board.coord(t)); break


def _ring(board, center, dx):
    """Tuiles marchables a dist hex EXACTEMENT `dx` de `center`."""
    return [board.coord(t) for t in board.by_id
            if board.walkable(t) and hexgeo.distance(center, board.coord(t)) == dx]


def _tile_with_ring1(board):
    """Une tuile marchable ayant au moins un voisin marchable."""
    return next((board.coord(t) for t in sorted(board.by_id)
                 if board.walkable(t) and len(_ring(board, board.coord(t), 1)) >= 1), None)


def _turn_start_ev(player):
    return TriggerEvent(EventTriggerType.TurnStart_Actions, -1, -1,
                        ranged=False, profile=None, player_id=player)


def _drive_carrier_and_one_enemy(state, board):
    """Montage commun : porteur au centre, UN ennemi en anneau-1, tout le reste parke loin.
    Rend `(cid, t_id, C, owner_player)` ou None si le plateau/roster ne s'y prete pas."""
    cid = _find_by_vis(state, CARRIER)
    ens = _enemies_of(state, cid) if cid is not None else []
    if cid is None or not ens:
        return None
    C = _tile_with_ring1(board)
    if C is None:
        return None
    t_id = ens[0]
    _park_others(state, board, {cid, t_id}, C)
    _set_pos(state, cid, *C)
    _set_pos(state, t_id, *_ring(board, C, 1)[0])
    return cid, t_id, C, _owner(state, cid)


# ------------------------------------------------------------------ fixture : etat LIVE rejouable

@pytest.fixture(scope="module")
def ma_env(host, live_session, request):
    """Runner LIVE (porteur historique + 3 ennemis) : `build_state()` rejouable pour les drives.
    State-file UNIQUE (discipline runner) ; runner dispose au teardown."""
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "4321", "--state-file", str(STATE),
         "--board", "MC1_67", "--p-units", ENEMIES, "--a-units", CARRIER, "--hp-player", HP],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        pytest.skip(f"build runner KO (rl_duel): {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(STATE.read_text())["runnerId"]

    def _rpc(m, b, t=60):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    request.addfinalizer(lambda: host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20))

    bg = _rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = _rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 90)
    ob = _rpc("observeBattle", {"runnerId": rid}, 40)
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = _rpc("dumpRng", {"runnerId": rid}, 30)

    def build_state():
        st = load_state(dv, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            st.rng = _seed_rng(rng0)
        return st

    if _find_by_vis(build_state(), CARRIER) is None:
        pytest.skip(f"porteur {CARRIER} absent du build")
    return {"build_state": build_state, "board": board, "rid": rid, "rpc": _rpc, "dv": dv}


# --------------------------------------------- (T0) GARDE D'INERTIE, sur la SOURCE DU MONTAGE

def test_ma_attribution_source_is_the_measured_channel(ma_env):
    """GARDE D'INERTIE (#392) -- elle surveille la voie par laquelle l'ability arrive REELLEMENT
    en bataille, pas le kit gameconfig.

    Le natif monte `UnitConfiguration.PassiveAbilities` (`UnitFactory$$AddConfiguredAbilities` ->
    `TriggeredAbilityComponent$$TryAdd(id, passiveAbilityState, 2)`), JAMAIS le kit. Les quatre
    constats, dans cet ordre :

      1. le canal MESURE a parle (`State.ability_states_seed.source` in {auto, given}) -- sans lui
         `collect_triggered_abilities` retomberait sur la derivation gameconfig et ce test
         mesurerait un FALLBACK, pas le montage ;
      2. ce canal nomme l'ability sur le porteur (hierarchie 2 du `TriggeredAbilityComponent`) ;
      3. le dispatch l'instancie donc pour lui ;
      4. et le kit gameconfig, lui, ne la nomme PAS -- l'ecart kit/BC est CONSTATE, pas subi.

    C'est le point 4 qui a fait conclure a tort « 0 porteur » en #354 : le kit n'est pas la source.
    Ce test rougit le jour ou le BC cesse de monter l'ability -- alors, et alors seulement, les
    vecteurs (A)/(C)/(E) perdent leur sujet. C'est ATTENDU au jour du re-dump du seed
    (backlog #254-bc : le bloc `Units` est reste celui de `gqfc5mff6c`) ; ce qui est valide ici est
    « le moteur reproduit le natif POUR CETTE CONFIGURATION », les deux lisant le meme BC."""
    from engine.runner.components import StatsComponent
    state = ma_env["build_state"]()
    cid = _find_by_vis(state, CARRIER)
    if cid is None:
        pytest.skip("porteur absent")
    seed = getattr(state, "ability_states_seed", None) or {}
    sc = state.get_entity(cid).get_component(StatsComponent)
    measured = list(getattr(sc.ctx, "passive_abilities", None) or []) if sc is not None else []
    ported = sorted(type(x).__name__ for x in collect_triggered_abilities(state)
                    if getattr(x, "owner_id", None) == cid)
    kit = GC.unit(CARRIER) or {}
    porte_par_config = sorted(v for v in VOIES if ABILITY in (kit.get(v) or []))
    print(f"\n[MA T0] seed={seed} measured_passives={measured} ported={ported} "
          f"kit_gameconfig={porte_par_config or 'AUCUNE VOIE'}")

    assert seed.get("source") in ("auto", "given"), (
        f"le canal MESURE n'a pas parle (source={seed.get('source')!r}) -- sans lui le dispatch "
        f"retombe sur la derivation gameconfig et ce test ne mesure plus le montage natif")
    assert ABILITY in measured, (
        f"{ABILITY} n'est plus montee sur {CARRIER} par le BC : `UnitContext.passive_abilities` "
        f"= {measured}. Si c'est durable, ce sont les vecteurs (A)/(C)/(E) qui perdent leur sujet "
        f"-- cf. en-tete, et `probe_392_martial_apotheosis_bc_carrier.py` pour re-mesurer.")
    assert "MartialApotheosisAttackAbility" in ported, (
        f"le dispatch n'instancie plus l'ability alors que le canal mesure la nomme : {ported}")
    assert porte_par_config == [], (
        f"{ABILITY} est REVENUE au kit gameconfig de {CARRIER} (voies {porte_par_config}) -- "
        f"l'ecart kit/BC que ce fichier documente n'existe plus, mettre l'en-tete a jour")
    print("[MA T0] OK : le BC monte l'ability, le dispatch la porte, le kit ne la nomme pas")


# ------------------------------------------------- (A) vecteur TURN-START + OwnerIsActor(@0xa0)

def test_ma_turnstart_dispatch_and_owner_gate(ma_env):
    """`start_turn_triggers(proprietaire)` dispatche MartialApotheosis (1 ennemi adjacent -> le
    frappe) ; `start_turn_triggers(adversaire)` ne le fire PAS (OwnerIsActor @0xa0).

    VECTEUR RESTAURE (#392) : il exerce la chaine COMPLETE attribution -> rail turn-start -> arbre.
    Son pendant par construction directe est (A') ci-dessous ; c'est le COUPLE qui localise un
    decrochage, et son absence a coute le faux verdict #354."""
    state = ma_env["build_state"]()
    board = ma_env["board"]
    drive = _drive_carrier_and_one_enemy(state, board)
    if drive is None:
        pytest.skip("porteur + 1 ennemi + tuile a >=1 voisin requis")
    _cid, t_id, _C, op = drive
    ep = _owner(state, t_id)
    if ep == op:
        pytest.skip("porteur et cible du meme joueur (le gate n'est pas discriminant)")
    hp0 = _hp(state, t_id)

    # OwnerIsActor : au tour de l'ENNEMI (ep), MartialApotheosis ne fire pas.
    res_e = start_turn_triggers(state, ep)
    assert not any(r.get("ability") == ABILITY for r in res_e), \
        f"{ABILITY} a fire au tour ADVERSE (OwnerIsActor viole): {res_e}"
    assert _hp(state, t_id) == hp0, "cible endommagee au tour adverse (OwnerIsActor viole)"

    # au tour du PROPRIETAIRE (op) : dispatche + frappe la cible adjacente.
    res_o = start_turn_triggers(state, op)
    ma = next((r for r in res_o if r.get("ability") == ABILITY), None)
    print(f"\n[MA A] owner_player={op} enemy_player={ep} target={ma.get('target') if ma else None} "
          f"total={(ma.get('attack') or {}).get('total') if ma else None} "
          f"dispatch={[r.get('ability') for r in res_o]}")
    assert ma is not None, f"{ABILITY} non dispatche au turn-start du proprietaire: {res_o}"
    assert ma.get("target") == t_id, f"cible {ma.get('target')} != ennemi adjacent {t_id}"
    assert (ma.get("attack") or {}).get("total", 0) > 0, "aucune attaque"
    assert _hp(state, t_id) < hp0, "ennemi adjacent non endommage"
    print("[MA A] OK : On(TurnStart_Actions) & OwnerIsActor -> frappe l'ennemi adjacent ; muet au tour adverse")


# ------------------------------------------------------------- (A') OwnerIsActor, voie DIRECTE

def test_ma_owner_gate(ma_env):
    """OwnerIsActor(@0xa0) : `matches` vrai au turn-start du PROPRIETAIRE, faux a celui de
    l'adversaire. Gate lu sur l'ability construite DIRECTEMENT -- il ne depend pas de
    l'attribution. Pendant de (A) : si (A) rougit et (A') passe, le decrochage est a l'etage
    ATTRIBUTION ; si les deux rougissent, c'est le PORT."""
    state = ma_env["build_state"]()
    board = ma_env["board"]
    drive = _drive_carrier_and_one_enemy(state, board)
    if drive is None:
        pytest.skip("porteur + 1 ennemi + tuile a >=1 voisin requis")
    cid, t_id, _C, op = drive
    ep = _owner(state, t_id)
    if ep == op:
        pytest.skip("porteur et cible du meme joueur (le gate n'est pas discriminant)")
    hp0 = _hp(state, t_id)
    ab = MartialApotheosisAttackAbility(cid)

    # tour de l'ADVERSAIRE : le gate refuse, et rien n'est execute.
    assert ab.matches(state, _turn_start_ev(ep)) is False, \
        "matches True au turn-start ADVERSE (OwnerIsActor viole)"
    assert _hp(state, t_id) == hp0, "cible endommagee au tour adverse"

    # tour du PROPRIETAIRE : le gate passe, l'ennemi adjacent est frappe.
    assert ab.matches(state, _turn_start_ev(op)) is True, \
        "matches False au turn-start du PROPRIETAIRE avec 1 ennemi adjacent"
    res = ab.execute_behaviour(state, _turn_start_ev(op))
    print(f"\n[MA A] owner_player={op} enemy_player={ep} target={(res or {}).get('target')} "
          f"total={((res or {}).get('attack') or {}).get('total')}")
    assert res is not None and res.get("target") == t_id, \
        f"cible {(res or {}).get('target')} != ennemi adjacent {t_id}"
    assert ((res.get("attack") or {}).get("total", 0)) > 0, "aucune attaque"
    assert _hp(state, t_id) < hp0, "ennemi adjacent non endommage"
    print("[MA A] OK : OwnerIsActor -> muet au tour adverse, frappe au tour du proprietaire")


# ------------------------------------------------------------------ (B) AmountIsGreaterThanZero (0 cible)

def test_ma_no_adjacent_no_fire(ma_env):
    """AmountIsGreaterThanZero(GetValidTargets) : aucun ennemi adjacent -> le gate refuse, sur les
    DEUX voies (construction directe ET dispatch turn-start)."""
    state = ma_env["build_state"]()
    board = ma_env["board"]
    cid = _find_by_vis(state, CARRIER)
    ens = _enemies_of(state, cid) if cid is not None else []
    if cid is None or not ens:
        pytest.skip("porteur + ennemis requis")
    # tuile isolee : porteur au centre, TOUS les ennemis parkes loin (dist > 4).
    C = next((board.coord(t) for t in sorted(board.by_id) if board.walkable(t)), None)
    _park_others(state, board, {cid}, C)
    _set_pos(state, cid, *C)
    op = _owner(state, cid)
    hp0 = {e: _hp(state, e) for e in ens}
    ab = MartialApotheosisAttackAbility(cid)
    assert ab.matches(state, _turn_start_ev(op)) is False, \
        "matches True sans ennemi adjacent (AmountIsGreaterThanZero viole)"
    res = start_turn_triggers(state, op)
    assert not any(r.get("ability") == ABILITY for r in res), \
        f"{ABILITY} a fire sans cible adjacente: {res}"
    for e in ens:
        assert _hp(state, e) == hp0[e], f"ennemi e{e} endommage sans adjacence"
    print("\n[MA B] OK : 0 ennemi adjacent -> pas de fire (AmountIsGreaterThanZero), voie directe ET dispatch")


# ------------------------------------------------------------------ (C) ciblage ANNEAU-1 (pas rayon-2)

def test_ma_ring1_not_radius2(ma_env):
    """CIBLAGE ANNEAU-1 : un ennemi a dist 1 est ciblable ; un ennemi a dist 2 ne l'est PAS (contraste
    HarbingerOfDestruction disque rayon-2). Pool == {dist1} -> pick deterministe -> dist2 jamais frappe."""
    state = ma_env["build_state"]()
    board = ma_env["board"]
    cid = _find_by_vis(state, CARRIER)
    ens = _enemies_of(state, cid) if cid is not None else []
    if cid is None or len(ens) < 2:
        pytest.skip("porteur + 2 ennemis requis")
    # C avec >=1 voisin dist1 ET >=1 tuile dist2.
    C = None
    for t in sorted(board.by_id):
        if not board.walkable(t):
            continue
        c = board.coord(t)
        if len(_ring(board, c, 1)) >= 1 and len(_ring(board, c, 2)) >= 1:
            C = c; break
    if C is None:
        pytest.skip("aucune tuile avec dist1 & dist2")
    near, far = ens[0], ens[1]
    _park_others(state, board, {cid, near, far}, C)
    _set_pos(state, cid, *C)
    occ = {C}
    d1 = [p for p in _ring(board, C, 1) if p not in occ]
    _set_pos(state, near, *d1[0]); occ.add(d1[0])
    d2 = [p for p in _ring(board, C, 2) if p not in occ]
    _set_pos(state, far, *d2[0]); occ.add(d2[0])
    assert hexgeo.distance(C, _pos(state, near)) == 1 and hexgeo.distance(C, _pos(state, far)) == 2
    op = _owner(state, cid)
    hp0 = {near: _hp(state, near), far: _hp(state, far)}
    # VECTEUR RESTAURE (#392) : le ciblage est lu A TRAVERS LE DISPATCH, pas par construction
    # directe -- c'est la chaine que le jeu emprunte au turn-start.
    res_all = start_turn_triggers(state, op)
    res = next((r for r in res_all if r.get("ability") == ABILITY), None)
    print(f"\n[MA C] near(d1)=e{near} far(d2)=e{far} target={(res or {}).get('target')} "
          f"dispatch={[r.get('ability') for r in res_all]}")
    assert res is not None and res.get("target") == near, \
        f"cible {(res or {}).get('target')} != ennemi ANNEAU-1 {near} (dist2 cible a tort ?)"
    assert _hp(state, near) < hp0[near], "ennemi anneau-1 non endommage"
    assert _hp(state, far) == hp0[far], f"ennemi a dist 2 (e{far}) endommage a tort -> rayon > 1 (pas anneau-1)"
    print("[MA C] OK : ciblage anneau-1 (dist1 frappe, dist2 exclu)")


# ------------------------------------------------------------------ (D) A/B bit-exact + params

def test_ma_ab_and_params(ma_env):
    """A/B : pool==1 (cible deterministe) -> l'arbre == `PickRandomly(pool,1)` + une sequence directe
    `execute_ability_attack` depuis le MEME MT (bit-exact). ATTENTION : le pick consomme 1 tirage MEME a
    pool==1 (#130) -- la baseline le reproduit explicitement. Params confrontes a l'ORACLE CONFIG
    (cf. en-tete, aucun scalaire fige) : nb de coups == `constants.nrOfHits`, percage == `PiercingRatio`
    du profil `constants.damageProfile`, melee, chaque coup dans [bmin,bmax]."""
    from engine.runner.components import StatsComponent
    state = ma_env["build_state"]()
    board = ma_env["board"]
    drive = _drive_carrier_and_one_enemy(state, board)
    if drive is None:
        pytest.skip("porteur + 1 ennemi + tuile a >=1 voisin requis")
    cid, t_id, C, op = drive

    # ORACLE CONFIG : nb de coups + profil lus TELS QUELS dans la config (cf. en-tete).
    want_hits = _const("nrOfHits")
    prof = _const("damageProfile")
    assert want_hits is not None and prof is not None, (
        f"oracle introuvable : gameconfig.ability('{ABILITY}').constants sans nrOfHits/damageProfile "
        "-- le natif les lit par GetNumberConstant(0x2f)/GetDamageProfile(0), elles DOIVENT exister. "
        "Si la CONFIG d'ability a disparu (et pas seulement son attribution), le port n'a plus "
        "d'oracle : voir case-354 (le zero-porteur laissait la config INTACTE)")
    want_hits = int(want_hits)
    dp = GC.damage_profile(prof) or {}
    assert dp.get("PiercingRatio") is not None, f"oracle introuvable : damageProfiles.{prof}.PiercingRatio"
    want_pierce = int(dp["PiercingRatio"])

    # params via le port (level_slot="passive"), profil pris de la config (== GetDamageProfile(0)).
    bmin, bmax, pierce, hits = ability_attack_params(state, cid, ABILITY, prof,
                                                     ranged=False, level_slot="passive")
    assert hits == want_hits, (
        f"nrOfHits lu {hits} != oracle config {want_hits} (constants.nrOfHits) -- le port ne lit pas la "
        f"CONSTANTE d'ability (0x2f) mais autre chose (variable per-niveau scalee ? mauvaise cle ?)")
    # le percage de l'attaque = PiercingRatio du PROFIL + ExtraPierce du caster ; ici le porteur n'en a
    # aucun -> l'identite isole l'oracle de profil. Si un patch lui en donnait, ce garde-fou le DIRAIT
    # au lieu de laisser l'assertion suivante rougir sans explication.
    _sc = state.get_entity(cid).get_component(StatsComponent)
    _xp = int(_sc.ctx.extra_pierce or 0) + int(_sc.ctx.extra_pierce_melee or 0)
    assert _xp == 0, (f"setup n'isole plus le PiercingRatio du profil : le porteur a ExtraPierce={_xp} "
                      f"-> l'oracle attendu devient PiercingRatio + {_xp}")
    assert pierce == want_pierce, (
        f"pierce {pierce} != oracle config {want_pierce} (damageProfiles.{prof}.PiercingRatio)")

    # snapshot MT AVANT le fire.
    rng_snap = {"mt": list(state.rng.mt), "mti": state.rng.mti} if state.rng is not None else None
    hp0 = _hp(state, t_id)
    ab = MartialApotheosisAttackAbility(cid)
    res = ab.execute_behaviour(state, _turn_start_ev(op))
    assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
    assert res.get("target") == t_id, f"cible {res.get('target')} != ennemi adjacent {t_id}"
    port_ph = (res.get("attack") or {}).get("per_hit")
    print(f"\n[MA D] [bmin,bmax]=[{bmin},{bmax}] pierce={pierce} hits={hits} port_per_hit={port_ph}")
    assert _hp(state, t_id) < hp0, "ennemi non endommage"

    # baseline : rejoue depuis le MEME MT la sequence native = `PickRandomly(pool, 1)` PUIS l'attaque.
    # Le pick consomme `min(len(pool), 1)` tirages MEME quand le pool tient dans `amount` (#130 :
    # `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` n'a aucun court-circuit ; la borne
    # 1 passe par la branche puissance-de-2 de `IntBasedMersenneTwister$$NextInternal`, qui consomme un
    # `genrand_int32`). Une baseline sans ce tirage decrit un flux RNG qui n'existe pas.
    st2 = ma_env["build_state"]()   # #64 : build_state pose deja state.board (via load_state board=)
    if rng_snap is not None:
        r = IntBasedMersenneTwister(); r.mt = list(rng_snap["mt"]); r.mti = rng_snap["mti"]; st2.rng = r
    _park_others(st2, board, {cid, t_id}, C)
    _set_pos(st2, cid, *C)
    _set_pos(st2, t_id, *_pos(state, t_id))
    if st2.rng is not None:
        st2.rng.next_internal(0, 1)          # PickRandomly(pool={t_id}, 1) : 1 tirage, borne 1
    rr = AttackDamageOperation.execute_ability_attack(st2, cid, t_id, bmin, bmax, pierce, hits,
                                                      damage_profile=prof, is_melee=True)
    ref_ph = (rr or {}).get("per_hit")
    print(f"[MA D] ref_per_hit={ref_ph}")
    assert port_ph == ref_ph, f"A/B : arbre {port_ph} != baseline execute_ability_attack {ref_ph}"
    assert port_ph is not None and len(port_ph) == want_hits, \
        f"{len(port_ph or [])} coups emis par l'arbre != oracle config nrOfHits={want_hits}, per_hit={port_ph}"
    for v in port_ph:
        assert bmin <= v <= bmax, f"coup {v} hors plage config [{bmin},{bmax}]"
    print(f"[MA D] OK : A/B tree==baseline ({want_hits} coups {prof} pierce {want_pierce}, bit-exact), "
          f"params == oracle config")


# ------------------------------------------------------------- (E) LIVE replay-diff turn-start

def test_ma_live_replay(ma_env):
    """LIVE : drive un ennemi adjacent au porteur, `endturn` (flip -> son turn-start), et confronte
    la cible frappee LIVE a la cible OFFLINE (pool==1 -> deterministe).

    VECTEUR RESTAURE (#392) + DURCI. `case-354` §3 objectait -- a juste titre -- qu'un
    `live_dmg > 0` n'attribue le degat a RIEN : n'importe quelle source le satisfait. On ajoute
    donc l'ATTRIBUTION GEOMETRIQUE : apres le move, l'ennemi drive est le SEUL a distance <= 1 du
    porteur, et apres l'`endturn` il doit etre le SEUL a avoir perdu des PV. Une source de portee
    autre que l'anneau-1 (ou un AoE) ne peut pas produire ce profil.

    Le DEGAT est confronte BIT-EXACT (#392) : montage DETERMINISTE (seed figee + `dumpRng` pris
    juste avant l'`endturn`), donc le port rejoue le turn-start depuis le MEME MT que le natif --
    mesure 3702 des deux cotes. L'ancien en-tete le declarait « plus confrontable » ; il l'est.
    Ce test CONSOMME le runner partage (endturn irreversible) : il doit rester le DERNIER du module."""
    rpc = ma_env["rpc"]
    board = ma_env["board"]
    rid = ma_env["rid"]

    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ov = next((u for u in (dec.get("units") or []) if u.get("visualId") == CARRIER), None)
    if ov is None:
        pytest.skip(f"{CARRIER} absent")
    ov_player = ov.get("owner")
    if dec.get("currentPlayer") == ov_player:
        pytest.skip("build demarre au tour du porteur (impossible d'endturn INTO son turn-start)")
    oid = ov["id"]
    ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
    om = {u.get("squadId"): u for u in (ob0.get("units") or [])}
    ovp = om.get(oid)
    if ovp is None:
        pytest.skip("porteur absent live")
    opos = (ovp.get("col"), ovp.get("row"))
    foes = [u for u in (ob0.get("units") or [])
            if u.get("teamId") != ovp.get("teamId") and not u.get("isDead") and u.get("col") is not None]
    if not foes:
        pytest.skip("aucun ennemi vivant")
    otile = board.id_at(*opos)
    occupied = {board.id_at(u.get("col"), u.get("row")) for u in om.values()
                if u.get("col") is not None and not u.get("isDead")}
    free = [n for n in board.neighbours(otile) if n not in occupied]
    if not free:
        pytest.skip("aucun voisin libre du porteur")
    fid = foes[0].get("squadId")
    dcol, drow = board.coord(free[0])
    rpc("applyAction", {"runnerId": rid,
                        "action": {"kind": "move", "unitId": fid, "to": {"col": dcol, "row": drow}}}, 90)

    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    alive = [u for u in (ob.get("units") or [])
             if u.get("teamId") != ovp.get("teamId") and not u.get("isDead") and u.get("col") is not None]
    dists = {u.get("squadId"): hexgeo.distance(opos, (u.get("col"), u.get("row"))) for u in alive}
    if dists.get(fid) != 1:
        pytest.skip(f"ennemi pas adjacent apres move (dest occupee ?) dists={dists}")
    if [k for k, d in dists.items() if d <= 1] != [fid]:
        pytest.skip(f"plusieurs ennemis en anneau-1 -> attribution non isolable : {dists}")

    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    hp_before = {u.get("squadId"): u.get("hp") for u in alive}

    # LIVE : endturn -> turn-start du porteur.
    # NB (mesure) : `applyAction endturn` + `captureEvents` rend 1 action / 0 event -- la cascade
    # turn-start n'expose AUCUN evenement per-coup. Le nb de coups de ce vecteur n'est donc PAS
    # confrontable live (residu) ; seuls le HP delta et sa GEOMETRIE le sont.
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}, "captureEvents": True}, 90)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    hp_after = {u.get("squadId"): u.get("hp") for u in (ob2.get("units") or [])}
    deltas = {k: (hp_before[k] - hp_after.get(k)) for k in hp_before
              if hp_before[k] is not None and hp_after.get(k) is not None}

    # OFFLINE : load_state(S) + seed rng + start_turn_triggers(porteur).
    state = load_state(dec, ob, snap, board=board)
    if isinstance(rng0, dict) and rng0.get("mt"):
        state.rng = _seed_rng(rng0)
    if state.get_entity(oid) is None or state.get_entity(fid) is None:
        pytest.skip("porteur/ennemi absent offline (snapshot incomplet)")
    res = start_turn_triggers(state, ov_player)
    ma = next((r for r in res if r.get("ability") == ABILITY), None)
    off_target = ma.get("target") if ma else None
    off_total = (ma.get("attack") or {}).get("total") if ma else None
    print(f"\n[MA E] dists={dists} live_deltas={deltas} | off target={off_target} total={off_total} "
          f"{'BIT-EXACT' if off_total == deltas.get(fid) else '(degat diverge = calage RNG turn-start, hors scope)'}")

    assert ma is not None and off_target is not None, f"{ABILITY} non tire offline: {res}"
    assert off_target == fid, f"cible offline {off_target} != ennemi drive adjacent {fid}"
    assert off_total is not None and off_total > 0, f"pas d'attaque offline (total={off_total})"
    assert deltas.get(fid, 0) > 0, f"live : ennemi anneau-1 pas touche au turn-start ({deltas})"
    # ATTRIBUTION GEOMETRIQUE : personne d'autre n'encaisse -> la portee du degat EST l'anneau-1.
    touches = sorted(k for k, d in deltas.items() if d > 0)
    assert touches == [fid], (
        f"des ennemis HORS anneau-1 ont encaisse au turn-start ({deltas}, dists={dists}) : le degat "
        f"n'est pas attribuable a {ABILITY} -- une autre source turn-start est en jeu")
    # DEGAT BIT-EXACT (#392). Le montage est DETERMINISTE (seed 4321 + `dumpRng` pris juste avant
    # l'`endturn`) : le port rejoue le turn-start depuis le MEME MT que le natif. Un rouge ici
    # signale soit une divergence de calcul, soit un DECALAGE DU FLUX RNG au turn-start (un trigger
    # de plus/de moins consommant un tirage avant le fire) -- lire `[MA E]` pour trancher.
    assert off_total == deltas.get(fid), (
        f"degat offline {off_total} != degat live {deltas.get(fid)} : calcul divergent, ou flux RNG "
        f"turn-start decale (dispatch offline = {[r.get('ability') for r in res]})")
    print("[MA E] OK : live turn-start -> l'ennemi ANNEAU-1 (et lui seul) est frappe ; "
          "cible ET degat offline == live (bit-exact)")
