"""#1022 -- GARDE de la face COMBAT d'`AetherStride` (1208), le premier des deux `[-D]` du registre
npc (face DECISION portee, face COMBAT ABSENTE : `ABILITY_CLASSES.get(1208)` rendait `None`, donc
l'IA la CHOISISSAIT et le moteur ne l'EXECUTAIT pas, en silence et en consommant le tour).

Ce que chaque test verrouille est cite dans sa docstring par le SYMBOLE natif correspondant. La
MESURE, elle, vit dans `probe_1022_aether_stride.py` (dont ce module reutilise le montage).

MONTAGE (GREFFE, case-92 §5bis) : le seul porteur du build est `thousNpcMowDaemonPrince` (npc,
absent de `BC.Units` du seed). On greffe donc 1208 sur `ultraDreadnought`, MoW du POOL, par
`catalog_inject.graft_active_ability` -- DEUX ecritures dont la seconde (la CONFIG d'ability) fait
« system error » au cast si on l'oublie. La greffe est legitime : le natif charge le playbook PAR
ABILITY, l'arbre de 1208 ne lit du caster ni stat ni trait, et les `.ctor` de 1208 et 1158
produisent le MEME masque octet pour octet.

ASCII only.
"""
from __future__ import annotations

import json

import hexgeo
import pytest

import gameconfig as GC
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.services import movement_query as MQ
from engine.services import spawn_tile_shape as STS
from probe_1022_aether_stride import (AETHER_STRIDE, MOW, SUMMON, feet_from_events,
                                      graft_seed_bc)

DYNAMIC_RULE_SAMPLE = 24

#: Ce qui doit changer pour que ce fichier puisse changer de verdict (contrat `declencheur_cliquet`).
#: Pris LARGE volontairement : un declencheur trop etroit est un FAUX VERT (le fichier ne se rejoue
#: pas sous `--since` quand ce qu'il garde a bouge). Les DEUX registres sont dedans parce que le
#: premier test garde precisement l'entree de 1208 dans l'un ET dans l'autre.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/abilities/thousandsons.py",       # l'arbre porte
        "scripts/python/engine/runner/abilities/handler.py",            # ABILITY_CLASSES
        "scripts/python/engine/runner/abilities/attack_type.py",        # ABILITY_ATTACK_TYPE
        "scripts/python/engine/runner/abilities/targeting.py",          # le masque et ses gates
        "scripts/python/engine/services/spawn_tile_shape.py",           # ThreeTileUnitSpawnShape
        "scripts/python/engine/services/movement_query.py",             # le gate HasTrait(0x418)
        "scripts/python/engine/runner/abilities/behaviours/summon.py",  # Spawn / PerformAIAttack
        "scripts/python/engine/runner/abilities/behaviours/grants.py",  # AddTrait / AddTriggeredAbility
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",   # RemoveMachine
        "scripts/python/engine/entities/selectors/units.py",            # AdjacentFriends / UnitsWithTrait
        "scripts/python/engine/entities/triggers.py",                   # ActorHasTriggeredAbility
        "scripts/python/engine/entities/behaviours.py",                 # If / Seq (op_and, op_add)
        "scripts/python/probe_1022_aether_stride.py",                   # le MONTAGE (greffe) partage
        "scripts/python/catalog_inject.py",                             # graft_active_ability
    ),
    "build": True,       # confronte le NATIF : runner live + gameconfig du build installe
    "toujours": False,
    "raison": ("la face COMBAT de 1208 est un arbre DSL dont chaque feuille est nommee ci-dessus ; "
               "le montage (greffe MoW + config d'ability) vit dans le probe et dans "
               "`catalog_inject`. `build: True` parce que les etages A/B confrontent le natif "
               "tuile par tuile et que la config d'ability est relue au gameconfig installe."),
}


def _occupied(rpc, rid) -> set:
    return {(t["col"], t["row"]) for t in rpc("boardGraph", {"runnerId": rid})["tiles"]
            if t.get("occupantUnitId") is not None}


def _voisines(board, aire) -> set:
    """Tuiles a distance 1 de l'empreinte, empreinte exclue (`Board.neighbours` prend un ID)."""
    out = set()
    for f in aire:
        fid = board.id_at(f[0], f[1])
        for nid in (board.neighbours(fid) if fid is not None else ()):
            out.add(board.coord(nid))
    return out - set(aire)


@pytest.fixture(scope="module")
def aether(rpc, build_runner):
    """LE MONTAGE, unique et partage : MoW greffee, adjacence Psyker CRAFTEE (on DEPLACE une unite
    plutot que de subir la geometrie de spawn), cast, et tout ce qu'il faut pour confronter."""
    bc = graft_seed_bc()
    rid = build_runner("777", extra=["--seed-bc", str(bc), "--p-mow", MOW, "--no-ai",
                                     "--p-units", "ultraTigurius,ultraCalgar",
                                     "--a-units", "necroWarden,necroSpyder"])["rid"]
    view = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    mows = [m for m in (view.get("mows") or []) if m.get("visualId") == MOW]
    if not mows:
        pytest.fail("%s absente de decisionView.mows -- la MoW n'est pas deployee" % MOW,
                    pytrace=False)
    caster, owner = mows[0]["casterId"], mows[0].get("owner")
    if AETHER_STRIDE not in [x.get("id") for x in (mows[0].get("abilities") or [])]:
        pytest.fail("la greffe n'a pas pris : le natif n'expose pas 1208 sur la MoW", pytrace=False)

    board = Board(rpc("boardGraph", {"runnerId": rid})["tiles"])
    ab = None
    for _ in range(16):
        v = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
        ab = next((x for x in (v["mows"][0].get("abilities") or [])
                   if x.get("id") == AETHER_STRIDE), None)
        if (ab and ab.get("usable") and ab.get("hasAmmo", True) and not (ab.get("cooldown") or 0)
                and (owner is None or v.get("currentPlayer") == owner)):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
    else:
        pytest.fail("1208 jamais castable en 16 fins de tour : %s" % json.dumps(ab), pytrace=False)

    occ = _occupied(rpc, rid)
    # --- la REGLE DYNAMIQUE, natif vs port, AVANT de toucher a quoi que ce soit ------------------
    # ⚠ les cles sont `casterId`/`abilityType` et le verdict est dans `targetReason`, PAS a la
    # racine : lu a cote, le canal « accepte » TOUTE tuile (meme piege que #287-r9).
    regle = []
    for tid in sorted(board.by_id)[:DYNAMIC_RULE_SAMPLE]:
        predit = len(STS.get_area(board, occ, board.coord(tid))) == 3
        tr = (rpc("abilityReason", {"runnerId": rid, "casterId": caster,
                                    "abilityType": AETHER_STRIDE, "targetId": tid})
              or {}).get("targetReason") or {}
        regle.append((tid, predit, int(str(tr.get("hex") or "0x0"), 16) == 0))

    # --- CRAFT de l'adjacence Psyker -------------------------------------------------------------
    mine = [u for u in (rpc("decisionView", {"runnerId": rid, "allAbilities": True}).get("units")
                        or [])
            if u.get("ctrl") and u.get("alive") and u.get("pos")
            and "Psyker" in set((GC.unit(u.get("visualId")) or {}).get("traits") or [])]
    mv = rpc("aiMovableTiles", {"runnerId": rid}) or {}
    atteignables = {e.get("unitId"): {(t["col"], t["row"]) for t in (e.get("tiles") or [])}
                    for e in (mv.get("units") or [])}
    cible = psyker = None
    for tid in sorted(board.by_id):
        ar = STS.get_area(board, occ, board.coord(tid))
        if len(ar) != 3:
            continue
        vs = _voisines(board, ar) - occ
        for u in mine:
            cand = sorted((atteignables.get(u["id"]) or set()) & vs)
            if cand and rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": u["id"],
                    "to": {"col": cand[0][0], "row": cand[0][1]}}}).get("ok"):
                cible, psyker, occ = tid, (u["id"], cand[0]), _occupied(rpc, rid)
                break
        if cible is not None:
            break
    if cible is None:
        pytest.fail("aucune (ancre, psyker deplacable) sur ce board -- le terme PerformAIAttack "
                    "resterait INERTE et l'accord ne prouverait rien de lui", pytrace=False)

    # --- AMENER UN ENNEMI AU CONTACT DE L'EMPREINTE (#1022-r3) -----------------------------------
    # Sans lui, `PerformAIAbilityUnitBehaviour$$Execute` s'execute mais ne frappe PERSONNE : natif
    # et port rendent 0 degat, et l'accord est en REGIME DEGENERE -- il ne dit rien du choix de
    # cible ni de la magnitude. La fiche du residu disait « l'equipe adverse n'est pas pilotable
    # sous --no-ai » et concluait qu'il fallait chercher un autre board : c'est FAUX, et le harnais
    # voisin l'ecrit noir sur blanc (`_charge_regime.py::place` : « `applyAction` ne verifie NI
    # propriete NI portee : les DEUX camps sont pilotables »). Aucun board n'aurait donne la
    # configuration de toute facon -- les spawns des deux equipes sont aux deux bouts et l'ancre
    # doit etre a portee du caster, donc dans son camp.
    aire_cast = STS.get_area(board, occ, board.coord(cible))
    vs_libres = sorted(_voisines(board, aire_cast) - _occupied(rpc, rid))
    dv_e = rpc("decisionView", {"runnerId": rid, "allAbilities": True}).get("units") or []
    adverses = [u for u in dv_e if u.get("alive") and u.get("pos") and not u.get("ctrl")]
    ennemi = None
    if any(hexgeo.distance((u["pos"]["col"], u["pos"]["row"]), f) <= 1
           for u in adverses for f in aire_cast):
        ennemi = ("DEJA", None)
    for u in (adverses if ennemi is None else ()):
        for dest in vs_libres:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": u["id"], "to": {"col": dest[0], "row": dest[1]}}})
            now = next((x for x in (rpc("decisionView", {"runnerId": rid, "allAbilities": True})
                                    .get("units") or []) if x.get("id") == u["id"]), None)
            p = (now or {}).get("pos") or {}
            if (p.get("col"), p.get("row")) == dest:
                ennemi = (u["id"], dest)
                break
        if ennemi is not None:
            break

    pre_dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    pre_ob = rpc("observeBattle", {"runnerId": rid})
    # Le MT est dumpe AVANT le cast : des que le summon frappe pour de bon, le rejeu offline doit
    # consommer le MEME flux que le natif, sinon `damage_ops/normal.py` REFUSE (`state.rng non
    # cale`) -- un refus explicite, jamais un degat invente.
    pre_rng = rpc("dumpRng", {"runnerId": rid})
    avant = {u.get("squadId") for u in (pre_ob.get("units") or [])}
    anc = board.coord(cible)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "abilityType": AETHER_STRIDE,
        "to": {"col": anc[0], "row": anc[1]}}})
    obs = rpc("observeBattle", {"runnerId": rid}).get("units") or []
    neufs = [u for u in obs if u.get("squadId") not in avant]
    pv_avant = {u.get("squadId"): u.get("hp") for u in (pre_ob.get("units") or [])}
    pv_apres = {u.get("squadId"): u.get("hp") for u in obs}
    touches = {s: int(pv_avant[s]) - int(pv_apres[s]) for s in pv_avant
               if s in pv_apres and pv_apres[s] is not None and pv_avant[s] is not None
               and pv_apres[s] < pv_avant[s]}
    return {"rid": rid, "caster": caster, "board": board, "anchor": anc, "tile": cible,
            "occ": occ, "regle": regle, "psyker": psyker, "pre": (pre_dv, pre_ob),
            "res": res, "feet": feet_from_events(res.get("actions") or [], board),
            "neufs": neufs, "ennemi": ennemi, "rng": pre_rng, "touches": touches}


def _port_cast(aether, pre=None):
    """Rejoue 1208 COTE PORT sur l'etat PRE-cast (meme caster, meme tuile).

    ⚠ LE MT EST CALE quand le montage a un ennemi au contact : le summon frappe alors pour de
    bon, et `damage_ops/normal.py` REFUSE un rejeu sans twister (`state.rng non cale`) plutot que
    d'inventer un degat. Sans ennemi, le rail n'atteint jamais l'operation de degat et l'absence
    de MT ne se voyait pas."""
    from engine.runner.abilities.thousandsons import AetherStrideAbility
    from engine.runner.prng import IntBasedMersenneTwister
    pre_dv, pre_ob = pre or aether["pre"]
    state = load_state(pre_dv, pre_ob, board=aether["board"])
    dump = aether.get("rng") or {}
    if isinstance(dump, dict) and dump.get("mt"):
        mt = IntBasedMersenneTwister()
        mt.mt, mt.mti = list(dump["mt"]), dump["mti"]
        state.rng = mt
    return state, AetherStrideAbility().execute_behaviour(state, aether["caster"], aether["tile"])


def test_port_ability_is_registered_with_its_literals():
    """Non-regression de REGISTRE. 1208 entre avec SES DEUX donnees obligatoires, lues au ctor natif
    `IdunBattleLogic.Entities.Abilities.Active.Loki.AetherStrideAbility$$.ctor` :
    `TARGETING_OPTIONS` (forme FLAGS DIRECTS, masque `0x20000040000042`) et `ABILITY_ATTACK_TYPE`
    (3e argument d'`AActiveAbility..ctor` = 2 = `Others`).

    C'est le cliquet qui rendait 1208 `[-D]` : sans entree au registre, `ABILITY_CLASSES.get(1208)`
    rend `None` et le moteur n'execute RIEN, sans erreur."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    klass = ABILITY_CLASSES.get(AETHER_STRIDE)
    assert klass is not None, "1208 absente d'ABILITY_CLASSES -- la face COMBAT est un NO-OP"
    assert int(klass.TARGETING_OPTIONS.rules) == 0x20000040000042, \
        "masque %s != litteral du ctor 0x20000040000042" % hex(int(klass.TARGETING_OPTIONS.rules))
    assert ABILITY_ATTACK_TYPE.get(AETHER_STRIDE) == AbilityAttackType.Others


def test_tree_is_not_its_form_neighbour():
    """L'arbre de 1208 n'est PAS celui de 1158 `DutyEternal`, et ce test le VERROUILLE nom par nom.

    Les deux derniers noeuds sont mot pour mot les memes (`RemoveMachine & Spawn(
    ThreeTileUnitSpawnShape)`), mais le sous-behaviour on-appearance differe sur TROIS points lus au
    decompile de `...AetherStrideAbility$$ExecuteBehaviour` :
      1. le transfert de triggered ability est un `If(ActorHasTriggeredAbility(Owner, 0x5d8), ...)`
         DSL a id FIXE, la ou 1158 lit le `TriggeredAbilityComponent` du caster A LA CONSTRUCTION ;
      2. 1208 porte un SECOND terme (`PerformAIAttack` sous condition Psyker) absent de 1158 ;
      3. les operateurs de jointure sont `op_BitwiseAnd` PUIS `op_Addition`, pas deux `&`.
    Recopier le voisin de forme aurait produit un arbre qui passe tous les tests d'empreinte.

    ⚠ Le point 3 n'est PAS assertionnable en l'etat : le port collapse les deux operateurs en un
    seul `Seq` (ecart ANTERIEUR a cette tranche, documente sur `entities/behaviours.py::Seq`), alors
    que le natif alloue DEUX pointeurs de classe distincts. L'ecart est inerte ici -- les trois
    termes de l'arbre sont PURS, donc aucun ne pose le flag de court-circuit -- et ce test verrouille
    ce qui EST distinguable : la FORME de l'arbre et ses feuilles."""
    from engine.entities.behaviours import Seq
    from engine.entities.triggers import ActorHasTriggeredAbility, AmountIsGreaterThanZero
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.runner.abilities.behaviours.grants import AddTrait, AddTriggeredAbility
    from engine.runner.abilities.behaviours.summon import PerformAIAttack
    from engine.runner.abilities.thousandsons import aether_stride_on_appearance
    from engine.entities.behaviours import If as IfBehaviour

    top = aether_stride_on_appearance()
    assert isinstance(top, Seq), "la racine du sous-behaviour est une jointure Seq"
    gauche, droite = top.left, top.right
    # terme 2 : `If(AmountIsGreaterThanZero(Count(...)), PerformAIAttack(ActiveTarget))`
    assert isinstance(droite, IfBehaviour), "le 2e terme de l'op_Addition est un If"
    assert isinstance(droite.cond, AmountIsGreaterThanZero), \
        ("`DSLBehaviors$$If(formula, ...)` est litteralement "
         "`If(DSLTriggers$$AmountIsGreaterThanZero(formula), ...)` -- le seuil est `> 0`")
    assert isinstance(droite.then, PerformAIAttack)
    assert droite.then.allow_move_action is False and droite.then.move_amount == 0, \
        ("`PerformAIAttack(unit, allowOnlyMove=0, overrideMovement=<DSLFormulas+0x18 = Direct(0)>)` "
         "-- MEMES `+0x70`/`+0x78` que `PerformAIAttackFromCurrentPosition`, pas le regime "
         "`allowOnlyMove=1` de `ForwardSpotterAbility`")
    # terme 1 : `AddTrait(...) & If(ActorHasTriggeredAbility(Owner, 0x5d8), AddTriggeredAbility)`
    assert isinstance(gauche, Seq) and isinstance(gauche.left, AddTrait)
    assert isinstance(gauche.right, IfBehaviour)
    assert isinstance(gauche.right.cond, ActorHasTriggeredAbility)
    assert gauche.right.cond.triggered_ability_type == TriggeredAbilityType.CabalOfSorcerers, \
        "0x5d8 = 1496 = CabalOfSorcerers, LU aux deux sites (predicat ET grant)"
    assert isinstance(gauche.right.then, AddTriggeredAbility)
    assert gauche.right.then.ability_id == TriggeredAbilityType.CabalOfSorcerers
    # Le collapse `op_and`/`op_add` -> `Seq` est INERTE ICI parce que les trois termes sont PURS.
    # Ce test le VERIFIE au lieu de le supposer : si une feuille devenait bloquante, la jointure de
    # gauche court-circuiterait et l'arbre ne serait plus le mirror du natif.
    from engine.dsl.effects import OperationResult
    assert OperationResult.ok().stop is False, \
        "le collapse Seq n'est inerte que tant que les feuilles rendent un resultat NON bloquant"


def test_native_dynamic_rule_matches_the_port(aether):
    """`...AetherStrideAbility$$GetDynamicInvalidTargetReason` = « la tuile est legale SSI une aire
    triangulaire de 3 tuiles existe autour d'elle » (`ThreeTileUnitSpawnShape(Target@+0x60)` puis
    `Count(tiles) <= 0 ? 2 : 0`). Confronte tuile par tuile au mirror
    `engine.services.spawn_tile_shape.get_area`.

    Le test EXIGE SON PROPRE NON-DEGENERESCENCE : un echantillon ou toutes les tuiles ont le meme
    verdict rendrait un accord qui ne prouve rien."""
    accepte = [r for r in aether["regle"] if r[1] and r[2]]
    refuse = [r for r in aether["regle"] if (not r[1]) and (not r[2])]
    ecarts = [r for r in aether["regle"] if r[1] != r[2]]
    assert accepte and refuse, \
        ("regime DEGENERE : %d acceptee(s) / %d refusee(s) -- il faut les DEUX verdicts"
         % (len(accepte), len(refuse)))
    assert not ecarts, "desaccord natif/port sur %s" % (ecarts,)


def test_native_cast_spawns_one_unit_on_the_whole_footprint(aether):
    """`SpawnUnitOptions+0x60 = 1` -> `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute`
    prend sa branche `GetTileIds(tiles)` : **UNE** unite sur les 3 tuiles, pas 3 unites d'un pied.
    Et l'unite posee est bien `GetStringConstant(config, 0 = unitId)`."""
    assert aether["res"].get("ok") is True, \
        ("cast refuse : %s -- si l'erreur est « system error », la CONFIG d'ability manque dans "
         "`BC.Abilities.ActiveAbilities` (verrou #226)" % json.dumps(aether["res"])[:400])
    squads = sorted({u.get("squadId") for u in aether["neufs"]})
    assert len(squads) == 1, "1 seule unite attendue sur l'empreinte, vu %s" % (squads,)
    vid = next((u.get("visualId") for u in aether["neufs"]), None)
    assert vid == SUMMON, "summon %r != constants.unitId %r" % (vid, SUMMON)
    assert len(aether["feet"]) == 3, "empreinte native %s" % (aether["feet"],)


def test_port_cast_matches_the_native_footprint(aether):
    """L'ORDRE compris : `GetTilesInTriangleShape` construit `{ancre, t1, t2}` puis `new List<>` ->
    `feet[0]` == l'ancre == la main tile. Le port doit rendre la MEME liste, dans le MEME ordre."""
    state, diag = _port_cast(aether)
    assert diag["spawned"], "le port n'a rien pose : %s" % (diag,)
    assert diag["feet"] == aether["feet"], \
        "empreinte portee %s != native %s" % (diag["feet"], aether["feet"])
    assert diag["summon"] == SUMMON


def test_port_cast_grants_stationary_and_detaches_the_machine(aether):
    """Les deux volets que le natif pose et que rien d'autre ne poserait :
      * `AddTrait(ActiveTarget@+0x68, 0x418)` = `UnitTrait.Stationary` -- PAS une propriete de la
        config du summon (verifie ci-dessous, sinon le test ne prouverait rien), et son consommateur
        natif est le gate `HasTrait(0x418)` en tete de `MovementQuery$$GetMovablePositionsFor` ;
      * `RemoveMachine(Caster@+0x48)` -> `IdunBattle.Operations.RemoveMachineOperation$$Execute`,
        qui DETACHE sans tuer : `alive` reste vrai, l'`ActiveAbilityComponent` n'est pas touche."""
    from engine.entities.traits.unit_trait import UnitTrait, has_trait
    from engine.runner.components import MachineComponent, StatsComponent, UnitComponent
    assert UnitTrait.Stationary.name not in ((GC.unit(SUMMON) or {}).get("traits") or []), \
        "si la config portait deja Stationary, ce test ne prouverait rien"
    state, diag = _port_cast(aether)
    uid = diag["spawned"][0]
    sc = state.get_entity(uid).get_component(StatsComponent)
    assert has_trait(sc.ctx.traits, UnitTrait.Stationary), \
        "trait Stationary absent du summon : %s" % (sc.ctx.traits,)
    assert MQ.get_movable_positions_for(aether["board"], state, uid, [aether["anchor"]]) == [], \
        "une unite Stationary n'a AUCUNE position mobile (gate HasTrait(0x418))"
    assert diag["removed_machine"] == [aether["caster"]], "RemoveMachine n'a pas vise le caster"
    mow = state.get_entity(aether["caster"])
    assert mow.get_component(MachineComponent).removed is True
    uc = mow.get_component(UnitComponent)
    assert uc is None or uc.alive is True, "le natif DETACHE la machine, il ne la TUE pas"


def test_port_perform_ai_attack_fires_only_with_an_adjacent_psyker_friend(aether):
    """LE terme qui separe 1208 de son voisin de forme :
    `If(Count(UnitsWithTrait(AdjacentFriends(ActiveTarget@+0x68, unique: 1, 3), 0x3ea, 3)) > 0,
    PerformAIAttack(ActiveTarget@+0x68))`.

    Le montage a CRAFTE l'adjacence (une unite Psyker DEPLACEE au contact de l'empreinte) ; la
    CONTRE-EPREUVE retire ce seul rail en ecartant le psyker de l'etat PRE-cast, sans rien changer
    d'autre -- le noeud doit alors ne PAS s'executer.

    L'ATTAQUE elle-meme (`PerformAIAbilityUnitBehaviour$$Execute`) est confrontee par les deux
    tests qui suivent, depuis que le montage AMENE un ennemi au contact (#1022-r3)."""
    import copy
    _state, diag = _port_cast(aether)
    assert diag["ai_attacks"], \
        ("avec un allie Psyker au contact de l'empreinte, le noeud PerformAIAttack DOIT "
         "s'executer -- psyker pose en %s, empreinte %s" % (aether["psyker"], aether["feet"]))
    # CONTRE-EPREUVE : meme etat, psyker ECARTE (on ne retire PAS le noeud, on retire sa CAUSE).
    pre_dv, pre_ob = aether["pre"]
    dv2, ob2 = copy.deepcopy(pre_dv), copy.deepcopy(pre_ob)
    loin = max(aether["board"].by_coord)
    for src in (dv2.get("units") or []):
        if src.get("id") == aether["psyker"][0] and src.get("pos"):
            src["pos"] = {"col": loin[0], "row": loin[1]}
    for src in (ob2.get("units") or []):
        if src.get("squadId") == aether["psyker"][0]:
            src["col"], src["row"] = loin
    _s2, diag2 = _port_cast(aether, pre=(dv2, ob2))
    assert any(hexgeo.distance(loin, f) > 1 for f in diag2["feet"]), \
        "la contre-epreuve doit VRAIMENT eloigner le psyker de l'empreinte"
    assert not diag2["ai_attacks"], \
        ("SANS psyker adjacent le noeud ne doit PAS s'executer -- il s'est execute : %s"
         % (diag2["ai_attacks"],))


def _attaques_du_port(diag):
    return [x for a in (diag.get("ai_attacks") or []) for x in (a.get("attacks") or [])]


def test_le_summon_frappe_LA_MEME_cible_que_le_natif(aether):
    """L'ATTAQUE de `PerformAIAttack`, enfin CONFRONTEE (#1022-r3).

    Le residu disait : « accord natif/port a 0 degat, en regime DEGENERE », et concluait qu'il
    fallait « soit un board ou les trois contraintes coexistent, soit amener un ennemi (l'equipe
    adverse n'est pas pilotable sous `--no-ai`) ». **Les deux moities de cette conclusion sont
    fausses.** L'equipe adverse EST pilotable -- `applyAction` ne verifie ni propriete ni portee,
    ce que `_charge_regime.py::place` ecrit deja -- et aucun board n'aurait donne la configuration,
    puisque les spawns des deux equipes sont aux deux bouts et que l'ancre doit rester a portee du
    caster. Le montage POSE donc un ennemi au contact de l'empreinte.

    ⚠ CE TEST ASSERTIONNE SON PROPRE NON-VIDE AVANT DE COMPARER. Un `[] == []` (ou `0 == 0`) est
    exactement le regime degenere qu'on vient de supprimer : sans ces deux gardes, le test
    redeviendrait vert le jour ou le montage cesserait d'amener l'ennemi."""
    _state, diag = _port_cast(aether)
    att = _attaques_du_port(diag)
    assert aether["ennemi"] is not None, (
        "TEMOIN DEGENERE : aucun ennemi n'a pu etre pose au contact de l'empreinte -- "
        "`PerformAIAttack` frappe dans le vide et l'accord ne prouverait rien")
    assert att, ("TEMOIN DEGENERE cote PORT : `attacks` est vide, il n'y a aucune attaque a "
                 "confronter (ai_attacks=%s)" % (diag.get("ai_attacks"),))
    assert aether["touches"], (
        "TEMOIN DEGENERE cote NATIF : aucune unite n'a perdu de PV pendant le cast, le summon "
        "natif n'a donc frappe personne")
    cibles_port = sorted({int(x["target"]) for x in att if x.get("target") is not None})
    cibles_natif = sorted(int(s) for s in aether["touches"])
    assert cibles_port == cibles_natif, (
        "le summon ne frappe pas la MEME unite : port=%s natif=%s (degats natifs %s)"
        % (cibles_port, cibles_natif, aether["touches"]))


def test_la_magnitude_du_summon_DIVERGE_et_l_etage_est_NOMME(aether):
    """CLIQUET INVERSE, et il est ecrit pour etre LEVE, pas pour durer.

    La cible concorde (test precedent), la MAGNITUDE non : mesure du 2026-08-18 sur ce montage
    meme, port **29** contre natif **2761**. La cause n'est ni la formule de degat ni le choix de
    cible -- c'est le SUBSTRAT DE STATS du summon, decompose par etage :

        grandeur   | port | natif
        attack     |    7 |   698
        health     |   60 |  5983
        level      |    0 |     1

    Le port fait naitre le summon sur les valeurs BRUTES du gameconfig, la ou
    `IdunBattle.Entities.Factories.UnitFactory` lui donne les stats calculees du match
    (`unitConfig.level = 1`, `abilityVariablesMultiplier = 100`). Le rapport des degats (95x) suit
    celui des attaques (99,7x) : c'est un etage d'ENTREE, pas un ecart de pipeline.

    ⚠ Ce n'est PAS un defaut general de `build_summon_context` : sur un AUTRE porteur (#577,
    `necroNpc1Warrior`), le `hp` du summon concorde a l'unite pres des deux cotes. C'est le
    call-site de 1208 qui n'apporte pas le niveau.

    Ce test rougit des que l'ecart se ferme -- et c'est voulu : il faut alors le remplacer par
    l'assertion d'ACCORD, pas le rendre plus permissif. Residu **#1022-r4**."""
    _state, diag = _port_cast(aether)
    att = _attaques_du_port(diag)
    assert att and aether["touches"], "regime degenere -- cf. le test precedent"
    degat_port = sum(int(x.get("total") or 0) for x in att)
    degat_natif = sum(int(v) for v in aether["touches"].values())
    assert degat_port > 0 and degat_natif > 0, (
        "TEMOIN DEGENERE : un des deux degats est nul (port=%s natif=%s), l'inegalite ci-dessous "
        "serait vraie pour une mauvaise raison" % (degat_port, degat_natif))
    assert degat_port != degat_natif, (
        "L'ECART DE MAGNITUDE S'EST FERME (port=%s natif=%s) -- #1022-r4 est resolu : REMPLACER ce "
        "cliquet inverse par l'assertion d'ACCORD, ne pas l'assouplir" % (degat_port, degat_natif))
