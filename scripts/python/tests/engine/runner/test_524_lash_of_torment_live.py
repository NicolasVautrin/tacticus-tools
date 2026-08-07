"""#524 -- `LashOfTorment` (ActiveAbilityType 1196, `emperLucius` << Lucius >>), face COMBAT.

Ce que ces bras GARDENT (et pas seulement ce qu'ils mesurent) :

  * `test_registre_offline`  -- l'entree au registre porte SES DEUX donnees obligatoires
    (`TARGETING_OPTIONS` lu du preset statique `<TargetingOptions statics>+0x140`,
    `ABILITY_ATTACK_TYPE` = 3e argument d'`AActiveAbility$$.ctor`), et le contrat de DISJONCTION
    est verifie PAR LE CODE (1196 dans AUCUNE des listes `*_UNPORTED`) ;
  * `test_arbre_offline`     -- la FORME de l'arbre : l'ATTAQUE PRECEDE le pull (inverse de
    `GrapnelLauncher` 1090), le taunt est SOUS le pull dans le meme `IfAlive(Caster)`, et le nombre
    de coups vient de la CONFIG (`GetHits()` = `GetNumberConstant(0x2f = nrOfHits)`), pas d'un
    litteral `6` -- ce bras ECHOUE si quelqu'un code le 6 en dur ;
  * `test_selection_type_alive_offline` -- le `selectionType: 3` de l'`IsAdjacent` MORD : sur un
    CADAVRE encore pose sur sa tuile, le trigger rend FAUX. C'est le cran qui empeche de taunter un
    mort, et il a ete pose APRES une mesure live qui l'a montre manquant ;
  * `test_degats_bit_exact_live`  -- la sequence de degats COUP PAR COUP (6 coups), natif vs port,
    MT offline cale sur `dumpRng`. Un TOTAL juste peut masquer deux erreurs qui se compensent ;
  * `test_pull_et_taunt_live`     -- le pull DEPLACE la cible d'un hex vers Lucius, et le bond 27
    (+ ses trois enfants 25/26/1237) est pose, bonde au CASTER, pour `TurnsFromRounds(nrOfRounds)`.

Aucun `pytest.skip` de complaisance : un montage qui ne s'installe pas ECHOUE (#268). Le porteur
`emperLucius` est un HERO `lineup` HORS seed BC ET hors catalogue -> `catalog_inject`
(cf. `docs/rl/case-92-catalog-injection.md` §6), meme voie qu'`astarCyrus` (#511).

MESURE, elle, dans `probe_524_lash_of_torment.py` (dont le regime CHAINE, residu `#524-r2`).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, pris LARGE et non feuille a feuille : charger UNE ability tire le
        # registre, le vocabulaire DSL, les Operations, l'IA et le pathfinding -- une liste choisie
        # serait un faux vert, elle ne pourrait pas montrer le module qu'elle a oublie. Foyers
        # vraiment load-bearing, pour la relecture humaine : `abilities/emperorschildren.py`
        # (l'arbre), `abilities/behaviours/movement.py` + `operations/displace.py` (le pull et son
        # knockback), `abilities/behaviours/effects.py` (`AddBondEffect`),
        # `entities/triggers.py` (`IsAdjacent` et son `UnitSelectionType`),
        # `entities/unit_selection_type.py`, `handler.py` + `attack_type.py` + `targeting.py`
        # (les registres confrontes), `operations/damage_ops/ability.py` (la route de degat),
        # `runner/prng.py` (l'ORDRE de consommation).
        "scripts/python/engine/**/*.py",
        # Les modules de la RACINE : la cascade des conftest importe une vingtaine de probes plus
        # `hexgeo` / `engine_validate`. Ils entrent dans la fermeture de CE fichier.
        "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de `1196 LashOfTorment` : l'oracle est le jeu "
              "lui-meme (degat coup par coup, ORDRE des tirages, deplacement du pull, pose et "
              "duree du bond de taunt). Un changement de build peut donc faire changer ce fichier "
              "d'avis sans qu'une ligne du port bouge.",
}

import uuid

import pytest

import hexgeo
import stream_events as SE

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.entities.unit_selection_type import UnitSelectionType
from engine.runner.abilities.emperorschildren import (LASH_OF_TORMENT_ID, LashOfTormentAbility,
                                                      lash_of_torment_tree)
from engine.runner.components import HealthComponent, PositionComponent
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

BOARD = "MC1_67"
SEED = "777"
CASTER = "emperLucius"                  # HERO `lineup` hors seed BC ET hors catalogue
ALLY = "ultraTitus"
ENEMIES = "orksNob,necroWarden"
ABILITY = int(ActiveAbilityType.LashOfTorment)                  # 1196
TAUNT = int(EffectType.Taunted_OnlySpecificTargets)             # 0x1b = 27
TAUNT_CHILDREN = (int(EffectType.Taunted_BlockMovement),        # 25
                  int(EffectType.Taunted_CantUseAbility),       # 26
                  int(EffectType.Taunted_RefreshUnitTurnFinished))   # 1237
RANGE = 2                                                       # gameconfig `constants.range`


# ------------------------------------------------------------------ helpers de lecture live

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _vue(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _units(dv):
    return [u for u in ((dv or {}).get("units") or []) if u.get("alive")]


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _by_vis(dv, vis):
    return next((u for u in _units(dv) if (u.get("visualId") or "") == vis), None)


def _by_id(dv, uid):
    return next((u for u in _units(dv) if u.get("id") == uid), None)


def _hp(ob, uid):
    """`observeBattle` indexe par `squadId`, PAS par `id` : lire `id` rend `None` partout et
    fabrique un accord en regime DEGENERE (deux dicts vides), donc zero preuve."""
    for u in ((ob or {}).get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _effets_bruts(dv, uid):
    for u in _units(dv):
        if u.get("id") == uid:
            return list(u.get("effects") or [])
    return []


def _effects(dv, uid):
    return sorted(e.get("effectType") for e in _effets_bruts(dv, uid)
                  if isinstance(e, dict) and e.get("effectType") is not None)


def _movable(rpc, rid, unit_id):
    mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
    for mu in (mov.get("units") or []):
        if mu.get("unitId") == unit_id:
            return {(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                    if t.get("col") is not None}
    return set()


def _act(rpc, rid, action, timeout=240):
    return rpc("applyAction", {"runnerId": rid, "action": action}, timeout)


def _montants_natifs(res):
    """La SEQUENCE coup par coup du NATIF (tags `Amount` des events `action` du pas
    `UnitDamaged`, resolu PAR NOM -- un ordinal fige designerait le pas VOISIN au prochain
    retrait de membre, sans erreur ni trace)."""
    import json as _j
    out = []
    for a in ((res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            if e.get("step") != SE.step_id("UnitDamaged"):
                continue
            try:
                t = _j.loads(e.get("tags") or "{}")
            except Exception:
                continue
            if "Amount" in t:
                out.append(int(t["Amount"]))
    return out


def _etat(rpc, rid, board):
    dv = _vue(rpc, rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    ab = rpc("unitAbilityStates", {"runnerId": rid}, 60)
    assert _ok(dv) and _ok(ob) and _ok(snap), "capture live KO -- montage non installe"
    st = load_state(dv, ob, snap, board=board, ability_states=ab)
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    assert _ok(s), "dumpRng KO -- MT non calable ; sans lui le degat offline est un faux 0"
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    st.rng = rng
    return dv, ob, st


def _drive(rpc, rid, dmin=2, dmax=2, tours=12):
    """DEPLACE Lucius jusqu'a une cible a distance dans `[dmin, dmax]` -- on ne se plaint JAMAIS de
    la geometrie de spawn. `dmin=dmax=2` est le regime ou le pull DEPLACE (a distance 1 il ne
    deplace pas : l'arc AVANT se reduit a la tuile du caster, cf. `probe_524 --step pull`)."""
    for _ in range(tours):
        dv = _vue(rpc, rid)
        me = _by_vis(dv, CASTER)
        if me is None:
            return None, None
        if dv.get("currentPlayer") != me.get("owner"):
            _act(rpc, rid, {"kind": "endturn"}, 60)
            continue
        foes = [u for u in _units(dv) if u.get("owner") != me.get("owner")]
        if not foes:
            return None, None
        tgt = min(foes, key=lambda e: hexgeo.distance(_pos(me), _pos(e)))
        if dmin <= hexgeo.distance(_pos(me), _pos(tgt)) <= dmax:
            return me, tgt
        tiles = _movable(rpc, rid, me["id"])
        if tiles:
            tp = _pos(tgt)
            best = min(tiles, key=lambda p: (0 if dmin <= hexgeo.distance(p, tp) <= dmax else 1,
                                             abs(hexgeo.distance(p, tp) - dmax)))
            _act(rpc, rid, {"kind": "move", "unitId": me["id"],
                            "to": {"col": best[0], "row": best[1]}}, 60)
        else:
            _act(rpc, rid, {"kind": "endturn"}, 60)
    return None, None


def _aplatir(noeud) -> list:
    """Deplie les `op_and` imbriques en une liste de feuilles, dans l'ordre d'execution."""
    enfants = getattr(noeud, "behaviours", None) or getattr(noeud, "items", None)
    if enfants is None:
        gauche, droite = getattr(noeud, "left", None), getattr(noeud, "right", None)
        if gauche is not None and droite is not None:
            return _aplatir(gauche) + _aplatir(droite)
        return [noeud]
    out: list = []
    for e in enfants:
        out.extend(_aplatir(e))
    return out


# ------------------------------------------------------------------------------- OFFLINE

def test_registre_offline():
    """Les DEUX donnees obligatoires du registre, et le contrat de DISJONCTION."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   TARGETING_OPTIONS_UNPORTED)
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    assert ABILITY_CLASSES.get(ABILITY) is LashOfTormentAbility

    opts = LashOfTormentAbility.TARGETING_OPTIONS
    assert opts is not None, "sans masque, AUCUN gate n'est applique (degradation permissive)"
    # `<TargetingOptions statics>+0x168` = `<preset +0x140>+0x28` = 0x4002, LU dans le `.cctor`.
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy) == 0x4002
    assert opts.self_cast is False                       # `<preset>+0x00 isSelfCasting = 0`
    assert opts.range is not None and opts.range.use_range_from_config is True   # statics+0x18
    assert int(opts.force_melee_target) == 0             # `<preset>+0x20` = RangedBool.True

    # 3e argument d'`AActiveAbility$$.ctor(this, &opts, 0)` -- TRANSCRIT, pas deduit du profil.
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.DirectTargetAttack

    # DISJONCTION : une ability n'a qu'UNE source de masque / de regle dynamique.
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED, "deux sources de masque = contrat viole"
    assert ABILITY not in DYNAMIC_TARGET_RULE_UNPORTED

    # La classe n'a AUCUN corps `GetDynamicInvalidTargetReason` dans les DEUX tables de symboles ->
    # le virtuel retombe sur la base, qui rend 0. Ce bras garde qu'on n'invente pas de refus.
    assert LashOfTormentAbility.get_dynamic_invalid_target_reason.__qualname__.startswith(
        "ActiveAbility."), "une surcharge apparue sans lecture du decompile"


def test_arbre_offline():
    """La FORME de l'arbre -- et le point ou une lecture pressee code `6` en dur."""
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.abilities.behaviours.effects import AddBondEffect
    from engine.runner.abilities.behaviours.movement import PullUnitOneTile

    arbre = lash_of_torment_tree(3)
    feuilles = _aplatir(arbre)
    noms = [type(f).__name__ for f in feuilles]
    # `op_BitwiseAnd(attaque, If(IsAlive(Caster), op_BitwiseAnd(pull, If(IsAdjacent, bond))))` :
    # l'attaque est le terme GAUCHE, donc elle part D'ABORD -- l'INVERSE de `GrapnelLauncher`
    # (1090), dont l'ExecuteBehaviour ouvre par le pull. Les deux se LISENT, aucun ne se deduit.
    assert noms == ["AttackWithAttackDamage", "If"], noms

    atk = feuilles[0]
    assert isinstance(atk, AttackWithAttackDamage)
    assert atk.ability_id == LASH_OF_TORMENT_ID and atk.profile == "Eviscerate"
    assert atk.is_melee is False, "gameconfig 1196 : `attackRangeType = Ranged`"
    assert atk.ability_type == ABILITY, "`AbilityOrEffect(abilityState)`, 6e argument natif"
    # ⚠ LE NOMBRE DE COUPS N'EST PAS UN LITTERAL DE L'ARBRE : `AActiveAbility$$GetHits` =
    # `GetNumberConstant(0x2f = nrOfHits)`. Le port doit lire la CONFIG, pas ecrire `6`.
    assert atk.hits is None and atk.hits_override is None, "un `6` code en dur au lieu de la config"
    assert atk.hits_key == "nrOfHits"

    # Le CORPS de l'`IfAlive` : `pull & If(IsAdjacent, bond)`.
    queue = feuilles[1]
    assert type(queue.cond).__name__ == "IsAlive"
    assert type(queue.cond.unit).__name__ == "Caster", "IfAlive porte sur le CASTER (`sel+0x48`)"
    sous = _aplatir(queue.then)
    assert [type(f).__name__ for f in sous] == ["PullUnitOneTile", "If"], sous

    pull = sous[0]
    assert isinstance(pull, PullUnitOneTile)
    assert type(pull.puller_sel).__name__ == "Caster"
    assert type(pull.pulled_sel).__name__ == "Target"
    # 4e argument natif = `Nullable` NUL -> aucun knockback de DENIVELE (contraste 1090, qui y met
    # `GetNumberConstant(0x5b = knockbackRange)`). Le knockback de la branche `IsFilled` reste arme.
    assert pull.elevation_knockback is None

    taunt = sous[1]
    assert type(taunt.cond).__name__ == "IsAdjacent"
    assert int(taunt.cond.selection_type) == int(UnitSelectionType.OnlyAliveAndTargetable) == 3
    bond = taunt.then
    assert isinstance(bond, AddBondEffect)
    assert bond.effect_type == TAUNT and bond.name == EffectType.Taunted_OnlySpecificTargets.name
    assert type(bond.source_ref).__name__ == "Caster"
    assert type(bond.target_ref).__name__ == "Target"
    assert type(bond.bonded_ref).__name__ == "Caster", "`bondedEntity` = 5e argument natif"
    assert bond.duration_rounds == 3 and bond.duration_turns is None    # `TurnsFromRounds(...)`
    assert bond.scale_from_source is False, "27 est un COMPOSITE, il ne lit aucun `ConfigVar`"


def test_selection_type_alive_offline():
    """Le `selectionType: 3` de l'`IsAdjacent` MORD -- et sans lui, le port taunte un CADAVRE.

    Le cran est LU (`IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType` : `IsAlive` pour
    `1` et `3`) et il a ete pose APRES une mesure live qui l'a montre manquant
    (`probe_524 --step taunt-dead --dmin 1 --dmax 1` : natif `[]`, port `[25, 26, 27, 1237]`).
    Le TEMOIN est ce qui rend ce bras non trivial : le CADAVRE garde ses tuiles, donc l'adjacence
    geometrique reste VRAIE -- seul le filtre de selection le rejette."""
    from engine.dsl.base import DslContext
    from engine.entities.triggers import IsAdjacent
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import Caster

    vivant = {"id": 1, "pos": {"col": 3, "row": 3}, "feet": [(3, 3)], "alive": True, "hp": 10}
    cadavre = {"id": 2, "pos": {"col": 4, "row": 3}, "feet": [(4, 3)], "alive": False, "hp": 0}
    ctx = DslContext(units=[vivant, cadavre], caster=vivant, target=cadavre)

    # TEMOIN NON NUL : la geometrie, elle, dit ADJACENT -- sans le filtre le trigger rendrait VRAI.
    assert IsAdjacent(Caster(), Target()).should_trigger(ctx) is True
    assert IsAdjacent(Caster(), Target(),
                      UnitSelectionType.OnlyAliveAndTargetable).should_trigger(ctx) is False
    assert IsAdjacent(Caster(), Target(),
                      UnitSelectionType.OnlyAlive).should_trigger(ctx) is False
    # `OnlyTargetable` (2) N'APPELLE PAS `IsAlive` au decompile -> les trois call-sites portes qui
    # passent `2` (BattleFatigue / Narthecium / TaintedNarthecium) restent INCHANGES.
    assert IsAdjacent(Caster(), Target(),
                      UnitSelectionType.OnlyTargetable).should_trigger(ctx) is True
    assert IsAdjacent(Caster(), Target(), UnitSelectionType.Any).should_trigger(ctx) is True

    # ... et sur DEUX VIVANTS, le filtre ne change rien (il n'a pas rendu le trigger inerte).
    vivant2 = dict(cadavre, alive=True, hp=7)
    ctx2 = DslContext(units=[vivant, vivant2], caster=vivant, target=vivant2)
    assert IsAdjacent(Caster(), Target(),
                      UnitSelectionType.OnlyAliveAndTargetable).should_trigger(ctx2) is True


# ---------------------------------------------------------------------------------- LIVE

@pytest.fixture(scope="module")
def env(live_session, rpc, build_runner, tmp_path_factory):
    """Runner `--no-ai` ou `emperLucius` est INJECTE au catalogue (hors seed BC ET hors pool)."""
    import catalog_inject
    bc = tmp_path_factory.mktemp("seedbc") / ("lucius-%s.json" % uuid.uuid4().hex[:8])
    catalog_inject.write_augmented_seed_bc(str(bc), [CASTER])
    built = build_runner(SEED, extra=[
        "--seed-bc", str(bc), "--board", BOARD, "--rank", "17", "--no-ai",
        "--p-units", "%s,%s" % (CASTER, ALLY), "--a-units", ENEMIES], keep=True)
    rid = built["rid"]
    dv = _vue(rpc, rid)
    assert _by_vis(dv, CASTER) is not None, "%s absent du plateau -- injection catalogue KO" % CASTER
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph KO"
    return {"rid": rid, "board": Board(bg["tiles"], adjacency="evenq")}


@pytest.fixture(scope="module")
def cast(env, rpc):
    """UN cast, mesure sous toutes ses faces, dans un runner FRAIS.

    UN SEUL, et c'est un CHOIX mesure : enchainer deux casts de 1196 dans le meme runner fait
    diverger le second (residu `#524-r2`, reproduit par
    `probe_524 --step chaine --amorce ability --vecteur ability`). Ce bras garde le regime
    DIRECT ; le regime chaine est nomme, pas maquille."""
    rid, board = env["rid"], env["board"]
    me, tgt = _drive(rpc, rid, dmin=2, dmax=2)
    assert me is not None and tgt is not None, \
        "aucune cible amenee a distance 2 -- montage non conforme"
    cid, tid = me["id"], tgt["id"]

    dv0, ob0, st = _etat(rpc, rid, board)
    pos_caster = _pos(_by_id(dv0, cid))
    pos_avant = _pos(_by_id(dv0, tid))
    eff_avant = _effects(dv0, tid)
    hp_avant = {u["id"]: _hp(ob0, u["id"]) for u in _units(dv0)}
    runner = Runner(st).install_default_handlers(20)

    res = _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                          "abilityType": ABILITY})
    a0 = ((res or {}).get("actions") or [{}])[0]
    assert a0.get("ok") and a0.get("mutated"), "le natif REFUSE le cast : %r" % (a0,)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    dv2 = _vue(rpc, rid)
    live = {u: (hp_avant[u] - _hp(ob2, u)) for u in hp_avant
            if hp_avant.get(u) is not None and _hp(ob2, u) is not None
            and hp_avant[u] != _hp(ob2, u)}

    runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
    diag = runner.ability_handler.last or {}
    off = {}
    for uid in hp_avant:
        e = st.get_entity(uid)
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is not None and hp_avant[uid] is not None and hp_avant[uid] != hc.hp:
            off[uid] = hp_avant[uid] - hc.hp
    e = st.get_entity(tid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return {"cid": cid, "tid": tid, "diag": diag, "live": live, "off": off, "res": res,
            "st": st, "dv2": dv2, "eff_avant": eff_avant, "pos_avant": pos_avant,
            "pos_caster": pos_caster, "pos_apres_nat": _pos(_by_id(dv2, tid)),
            "pos_apres_port": (pc.col, pc.row) if pc is not None else None}


def test_degats_bit_exact_live(cast):
    """DECIDER != EXECUTER : `ported is True`, PUIS l'accord COUP PAR COUP."""
    diag = cast["diag"]
    assert diag.get("ported") is True, \
        "1196 absente du registre -> le cast est accepte et IGNORE (no-op SILENCIEUX)"
    assert diag.get("ability") == LASH_OF_TORMENT_ID

    atk = diag.get("main_attack") or {}
    assert atk.get("hits") == 6, "`GetHits()` = `nrOfHits` du gameconfig"

    # TEMOIN NON NUL : deux dicts vides seraient un accord en regime DEGENERE, donc zero preuve.
    assert cast["live"], "aucun delta HP live -- le montage ne prouve rien"
    assert cast["live"] == cast["off"], \
        "deltas HP natif=%r port=%r" % (cast["live"], cast["off"])

    # ... et le TOTAL ne suffit pas : avec six coups, deux erreurs peuvent se compenser.
    nat = _montants_natifs(cast["res"])
    port = list(atk.get("per_hit") or [])
    assert len(port) == 6, port
    assert nat[:6] == port, "sequence natif=%r port=%r" % (nat, port)


def test_pull_et_taunt_live(cast):
    """Le pull DEPLACE, et le bond 27 (+ enfants) est pose, bonde au CASTER, pour `nrOfRounds`."""
    diag, dv2, tid = cast["diag"], cast["dv2"], cast["tid"]

    # --- PULL : la cible AVANCE d'un hex vers Lucius, des deux cotes -----------------------
    assert cast["pos_apres_nat"] == cast["pos_apres_port"], \
        "position cible natif=%r port=%r" % (cast["pos_apres_nat"], cast["pos_apres_port"])
    # TEMOIN NON NUL : sans deplacement, l'egalite ci-dessus ne prouverait rien.
    assert cast["pos_apres_nat"] != cast["pos_avant"], "la cible n'a pas bouge -- temoin nul"
    assert hexgeo.distance(cast["pos_caster"], cast["pos_apres_nat"]) == 1
    assert (diag.get("pull") or {}).get("moved") is True
    # `elevationDifferenceForKnockback` NUL -> le pull REUSSI ne paie AUCUN knockback.
    assert (diag.get("pull") or {}).get("knockback") is None

    # --- TAUNT : pose, famille COMPLETE, bond, duree ---------------------------------------
    poses = sorted(set(_effects(dv2, tid)) - set(cast["eff_avant"]))
    attendus = sorted({TAUNT, *TAUNT_CHILDREN})
    assert sorted(set(poses) & set(attendus)) == attendus, \
        "le natif pose %r, on attendait la famille %r" % (poses, attendus)

    st = cast["st"]
    port_poses = sorted(int(getattr(x, "effect_type", -1))
                        for x in (st.effects.by_unit.get(int(tid)) or []))
    assert sorted(set(port_poses) & set(attendus)) == attendus, \
        "le port ne pose pas la famille TAUNT : %r" % (port_poses,)

    # DUREE : `TurnsFromRounds(nrOfRounds)` -- le natif rend un `remaining` en TOURS.
    rem_nat = {e.get("effectType"): e.get("remaining") for e in _effets_bruts(dv2, tid)
               if e.get("effectType") in attendus}
    rem_port = {int(getattr(x, "effect_type", -1)): getattr(x, "remaining_turns", None)
                for x in (st.effects.by_unit.get(int(tid)) or [])
                if int(getattr(x, "effect_type", -1)) in attendus}
    assert rem_nat and rem_nat == rem_port, "duree natif=%r port=%r" % (rem_nat, rem_port)

    # BOND DU PARENT : `bondedEntity` = 5e argument natif = le CASTER.
    parent_nat = next(e for e in _effets_bruts(dv2, tid) if e.get("effectType") == TAUNT)
    assert parent_nat.get("bondMeasured") is True, "capteur de bond MUET -- rien a comparer"
    assert parent_nat.get("bondedEntityId") == cast["cid"]
    parent_port = next(x for x in st.effects.by_unit[int(tid)]
                       if int(getattr(x, "effect_type", -1)) == TAUNT)
    assert getattr(parent_port, "bonded", None) == cast["cid"]
    assert (diag.get("taunt") or {}).get("bonded") == cast["cid"]

    # #524-r1 (FERME) : les ENFANTS portent le bond du parent, des DEUX cotes. Le natif l'ecrit par
    # un CONTEXTE PARTAGE (`IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` :
    # `ctx.<+0x18> = ABondEffect$$BondedEntityId(parent)`, passe aux trois `EffectBuilder`) ; le port
    # le fait descendre au foyer de creation des sous-effets. TEMOIN NON NUL : le bond vaut l'id du
    # caster, jamais `None` -- sans quoi cette egalite serait `None == None`.
    enf_nat = {e.get("effectType"): e.get("bondedEntityId") for e in _effets_bruts(dv2, tid)
               if e.get("effectType") in TAUNT_CHILDREN}
    enf_port = {int(getattr(x, "effect_type", -1)): getattr(x, "bonded", None)
                for x in (st.effects.by_unit.get(int(tid)) or [])
                if int(getattr(x, "effect_type", -1)) in TAUNT_CHILDREN}
    assert set(enf_nat.values()) == {cast["cid"]}, \
        "temoin nul : le natif ne bonde pas les enfants (%r)" % (enf_nat,)
    assert enf_nat == enf_port, \
        "#524-r1 -- bond des sous-effets natif=%r port=%r" % (enf_nat, enf_port)
