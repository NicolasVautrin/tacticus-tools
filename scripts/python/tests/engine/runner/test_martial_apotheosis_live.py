"""case-220 Necrons : MartialApotheosis (TriggeredAbilityType 1045) FACE COMBAT.

>>> L'ABILITY N'A PLUS DE PORTEUR DEPUIS LE BUILD `rnca9r7q6c` (case-354, #354-r2).
    Le jeu l'a retiree de son unique porteur `necroOverlord`, remplacee par `MyWillBeDoneOverlord`.
    `collect_triggered_abilities` ne l'instancie donc plus -- et c'est le comportement FIDELE :
    un port ne peut pas dispatcher une ability que le gameconfig n'accorde a personne.
    CE FICHIER A ETE CONVERTI EN CONSEQUENCE, PAS AFFAIBLI POUR PASSER AU VERT :
      - les trois vecteurs qui passaient par `start_turn_triggers` (dispatch turn-start, ciblage
        via dispatch, replay-diff LIVE) n'ont plus de sujet -- ils sont remplaces par la GARDE
        D'INERTIE (T0), qui rougit le jour ou un kit reprend l'ability ;
      - tout ce qui s'exerce SANS attribution est CONSERVE tel quel (gates `matches`, arbre DSL,
        A/B bit-exact, oracle config) : le port reste couvert.
    Pour restaurer les vecteurs de dispatch quand l'ability revient : leur derniere version vit au
    commit `6f07ab08` (`git show 6f07ab08:scripts/python/tests/engine/runner/test_martial_apotheosis_live.py`).
    Mesure du zero-porteur (4 etages, dont un LIVE) : `probe_354_martial_apotheosis_carrier.py`.

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
  (T0) GARDE D'INERTIE : dans le montage EXACT qui faisait fire l'ability (ennemi drive en anneau-1),
      `start_turn_triggers` est MUET -- et la construction DIRECTE de l'ability, elle, frappe. Le
      couple prouve que le decrochage est a l'etage ATTRIBUTION, pas dans le port. Rougit des qu'un
      kit reprend l'ability : c'est le signal qu'il faut restaurer les vecteurs de dispatch.
  (A) OwnerIsActor(@0xa0) : `matches` est vrai au turn-start du PROPRIETAIRE, faux a celui de
      l'adversaire -- gate lu directement sur l'ability (independant de l'attribution).
  (B) AmountIsGreaterThanZero : 0 ennemi adjacent -> `matches` faux, aucun degat.
  (C) CIBLAGE ANNEAU-1 : un ennemi a dist 1 est frappe ; un ennemi a dist 2 NE l'est PAS (anneau-1,
      PAS le disque rayon-2 de HarbingerOfDestruction).
  (D) A/B bit-exact + params : pool==1 (deterministe) -> l'arbre == une sequence directe
      `execute_ability_attack` depuis le MEME MT ; params confrontes a l'ORACLE CONFIG (cf. ci-dessous), melee.
Le DEGAT exact live n'est plus confrontable (plus aucun porteur ne la tire en bataille) ; la
bit-exactness du DEGAT reste prouvee PAR CONSTRUCTION en (D).

ORACLE DES PARAMS (#96 -- aucun scalaire de gameplay fige ici). Le decompile TRANCHE : le nb de coups et le
profil sont lus TELS QUELS dans la config d'ability par
`IdunBattleLogic.Entities.Abilities.Active.Loki.MartialApotheosisAbility$$CreateBehaviour`
(`GetNumberConstant(cfg, 0x2f)` et `GetDamageProfile(cfg, 0)` passes directement en arguments de
`IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` -- aucune formule),
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
from engine.runner.operations.triggers import start_turn_triggers
from engine.runner.operations.triggers.base import TriggerEvent
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


# ------------------------------------------------------------------ (T0) GARDE D'INERTIE

def test_ma_inertia_tripwire_no_carrier(ma_env):
    """GARDE D'INERTIE (case-354, #354-r2). Trois constats DANS LE MONTAGE QUI FAISAIT FIRE :

      1. le gameconfig n'accorde plus l'ability au porteur historique (aucune des 4 voies) ;
      2. le kit LIVE du porteur ne la contient pas non plus ;
      3. `start_turn_triggers` est donc MUET -- alors que l'ability construite DIRECTEMENT frappe
         bel et bien l'ennemi adjacent.

    Le point 3 est ce qui donne son sens au fichier : il localise le decrochage a l'etage
    ATTRIBUTION et innocente le port. Ce test ROUGIT le jour ou un kit reprend l'ability -- c'est
    alors le signal de RESTAURER les vecteurs de dispatch (cf. en-tete, commit `6f07ab08`)."""
    state = ma_env["build_state"]()
    board = ma_env["board"]
    drive = _drive_carrier_and_one_enemy(state, board)
    if drive is None:
        pytest.skip("porteur + 1 ennemi + tuile a >=1 voisin requis")
    cid, t_id, _C, op = drive

    # 1. gameconfig : aucune des 4 voies d'attribution ne nomme l'ability chez le porteur.
    kit = GC.unit(CARRIER) or {}
    porte_par_config = sorted(v for v in VOIES if ABILITY in (kit.get(v) or []))
    # 2. kit LIVE tel que le jeu le resout.
    live_u = next((u for u in (ma_env["dv"].get("units") or []) if u.get("visualId") == CARRIER), None)
    live_noms = sorted(a.get("name") for a in ((live_u or {}).get("abilities") or []) if a.get("name"))

    # 3. dispatch MUET vs construction DIRECTE qui frappe.
    hp0 = _hp(state, t_id)
    res = start_turn_triggers(state, op)
    disp = [r.get("ability") for r in res]
    ab = MartialApotheosisAttackAbility(cid)
    ev = _turn_start_ev(op)
    fired_direct = ab.matches(state, ev) and (ab.execute_behaviour(state, ev) or {}).get("target") == t_id

    print(f"\n[MA T0] config={porte_par_config or 'AUCUNE VOIE'} live_kit={live_noms} "
          f"dispatch={disp} direct_frappe={fired_direct}")

    assert porte_par_config == [], (
        f"{ABILITY} est REVENUE au kit gameconfig de {CARRIER} (voies {porte_par_config}) -- "
        f"restaurer les vecteurs de dispatch/live retires par #354-r2 (cf. en-tete du fichier)")
    assert ABILITY not in live_noms, (
        f"{ABILITY} est REVENUE au kit LIVE de {CARRIER} ({live_noms}) -- meme consigne")
    assert ABILITY not in disp, (
        f"start_turn_triggers dispatche {ABILITY} alors que le gameconfig ne l'accorde a personne : "
        f"l'etage ATTRIBUTION ne lit plus le kit ({disp})")
    assert fired_direct, (
        f"l'ability construite DIRECTEMENT ne frappe plus l'ennemi anneau-1 e{t_id} -- CE rouge-la "
        f"accuse LE PORT (arbre DSL / gates), pas l'absence de porteur")
    assert _hp(state, t_id) < hp0, "ennemi adjacent non endommage par la voie directe"
    print("[MA T0] OK : 0 porteur (config + live) -> dispatch muet ; le port, lui, tire toujours")


# ------------------------------------------------------------------ (A) OwnerIsActor(@0xa0)

def test_ma_owner_gate(ma_env):
    """OwnerIsActor(@0xa0) : `matches` vrai au turn-start du PROPRIETAIRE, faux a celui de
    l'adversaire. Gate lu sur l'ability construite directement -- il ne depend pas de
    l'attribution, et reste donc exercable malgre le zero-porteur (cf. T0)."""
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
    """AmountIsGreaterThanZero(GetValidTargets) : aucun ennemi adjacent -> le gate refuse."""
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
    for e in ens:
        assert _hp(state, e) == hp0[e], f"ennemi e{e} endommage sans adjacence"
    print("\n[MA B] OK : 0 ennemi adjacent -> pas de fire (AmountIsGreaterThanZero)")


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
    ab = MartialApotheosisAttackAbility(cid)
    ev = _turn_start_ev(op)
    assert ab.matches(state, ev) is True, "gate refuse alors qu'un ennemi est en anneau-1"
    res = ab.execute_behaviour(state, ev)
    print(f"\n[MA C] near(d1)=e{near} far(d2)=e{far} target={(res or {}).get('target')}")
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
