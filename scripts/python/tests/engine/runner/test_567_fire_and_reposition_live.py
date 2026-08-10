"""#567 -- `FireAndReposition` (ActiveAbilityType 1063, `eldarRanger` << Calandis >>), face COMBAT.

Ce que ces bras GARDENT (et pas seulement ce qu'ils mesurent) :

  * `test_registre_offline`   -- l'entree au registre porte SES DEUX donnees obligatoires
    (`TARGETING_OPTIONS` lu du preset statique `<TargetingOptions statics>+0x00`,
    `ABILITY_ATTACK_TYPE` = 3e argument d'`AActiveAbility$$.ctor` = **2 `Others`**, contre-intuitif
    puisque le cast FRAPPE), et le contrat de DISJONCTION est verifie PAR LE CODE (1063 dans AUCUNE
    des listes `*_UNPORTED`, dont elle a MIGRE) ;
  * `test_ordre_des_feuilles_offline` -- l'ORDRE `(attaque + ResetMovement) + AddEffect`, feuille par
    feuille et selecteur par selecteur. C'est la garde qui a le plus de valeur ici : les trois
    feuilles sont DETERMINISTES entre elles (aucune ne tire), donc permuter l'attaque et le reset ne
    changerait NI le degat NI le flux `state.rng` -- un test << ca fire >> resterait VERT. Le voisin
    `StrikeFromTheShadows` (1225), MEME patron a trois feuilles, emboite `(atk + eff) + reset` :
    l'ordre se LIT, il ne se recopie pas d'une soeur ;
  * `test_duree_de_l_effet_offline` -- `TurnsFromRounds(1)` NU, et le TEMOIN que la duree VOISINE
    (`TurnsUntilEndOfCurrentPlayersNextTurn`, celle de 1225) vaudrait UN TOUR DE PLUS ;
  * `test_degats_bit_exact_live` -- la sequence de degats coup par coup ET l'etat MT final, natif vs
    port. La config 1063 n'a NI `minDmg`/`maxDmg` NI `nrOfHits` NI `damageProfile` : ce que le port
    doit reproduire, c'est l'attaque NORMALE de Calandis, dispatchee par `UseActiveAbility` ;
  * `test_reset_movement_live` -- son deplacement EPUISE lui est RENDU, et le second pas est JOUE ;
  * `test_effet_pose_sur_le_caster_live` -- 1110 est pose sur **ELLE-MEME** (`targets` = Caster,
    pas Target), avec le `remaining` natif EGAL a `TurnsFromRounds(1)`, et le niveau d'ability
    **ACTIVE** bake sur l'instance du port (`scale_from_source`) ;
  * `test_gate_de_cible_live` -- le masque confronte cible par cible, natif (`abilityTargets`
    `fromHere`) contre port (`get_invalid_target_reason`), sur TOUTES les unites vivantes.

Aucun `pytest.skip` de complaisance : un montage qui ne s'installe pas ECHOUE (#268). Le porteur
`eldarRanger` est un HERO du pool spawnable -> aucune injection catalogue, aucun montage de relique.
L'EFFET 1110 lui-meme (ses trois gates, sa magnitude) est garde ailleurs
(`test_fire_and_reposition_reduce_dmg_live.py`, #366-r1) : ce fichier garde sa POSE.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture. Aucun
        # test ne les IMPORTE -- c'est de la semantique pytest -- et ils portent le
        # `green_skip_guard` de #455 plus les fixtures `autouse`, dont le verdict de CHAQUE test
        # depend.
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
        # registre, le vocabulaire DSL, les Operations, l'IA et le pathfinding -- une liste
        # choisie serait un faux vert, elle ne pourrait pas montrer le module qu'elle a oublie.
        # Foyers vraiment load-bearing, pour la relecture humaine :
        # `abilities/aeldari.py` (l'arbre), `abilities/behaviours/movement.py` (`ResetMovement`),
        # `abilities/behaviours/combat.py` (`UseActiveAbility`), `abilities/behaviours/effects.py`
        # (`AddEffect` + `_source_scaling`), `handler.py` + `attack_type.py` + `targeting.py` (les
        # registres confrontes), `entities/effects/loki/damage_reduction.py` (la classe de 1110),
        # `runner/components.py` (`UnitFlagsComponent`), `runner/prng.py` (l'ORDRE des tirages).
        "scripts/python/engine/**/*.py",
        # Les modules de la RACINE : la cascade des conftest de `tests/engine/runner` importe une
        # vingtaine de probes plus `hexgeo` / `engine_validate`. Ils entrent dans la fermeture de
        # CE fichier, qu'il les cite ou non.
        "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de `1063 FireAndReposition` : l'oracle est le jeu "
              "lui-meme (degat de l'attaque normale dispatchee, ORDRE des tirages, portee du "
              "deplacement rendu, pose et duree de l'effet 1110, legalite du ciblage). Un "
              "changement de build peut donc faire changer ce fichier d'avis sans qu'une ligne du "
              "port bouge.",
}

import os

import pytest

import hexgeo
import stream_events as SE

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.aeldari import (FIRE_AND_REPOSITION_ID, FireAndRepositionAbility,
                                             fire_and_reposition_tree)
from engine.runner.components import HealthComponent, UnitFlagsComponent
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

#: DEUX couples (board, seed) -- discipline de generalisation (`runner.md` S3) : un resultat obtenu
#: sur UN seul board peut etre un artefact de sa geometrie (distances de spawn, terrain, ordre de
#: tour). Les deux exercent des regimes de PORTEE differents : sur `MC1_67` la cible amenee est
#: ADJACENTE (donc `forceMeleeTarget = IfRangedCaster` rabat la portee a 1 et l'attaque part en
#: MELEE), sur `C4_09` elle ne l'est pas necessairement.
COUPLES = (("MC1_67", "31337"), ("C4_09", "4242"))
CASTER = "eldarRanger"                  # << Calandis >> -- HERO du pool spawnable (rank 17)
ALLY = "eldarFarseer"
ENEMIES = "necroWarden,necroDestroyer"
ABILITY = int(ActiveAbilityType.FireAndReposition)              # 1063 = 0x427
EFFECT = int(EffectType.FireAndReposition_ReduceDmg)            # 1110 = 0x456
#: Portee de l'arme RANGED de Calandis. Le masque n'a AUCUNE constante `range` a lire (la config
#: 1063 n'en porte pas) -- la portee effective est celle de l'ARME.
RANGE = 3


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


def _hp(ob, uid):
    """`observeBattle` indexe par `squadId`, PAS par `id` : lire `id` rend `None` partout et
    fabrique un accord en regime DEGENERE (deux dicts vides), donc zero preuve."""
    for u in ((ob or {}).get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _effects(dv, uid):
    for u in _units(dv):
        if u.get("id") == uid:
            return sorted(e.get("effectType") for e in (u.get("effects") or [])
                          if isinstance(e, dict) and e.get("effectType") is not None)
    return None


def _effect_row(dv, uid, etype):
    for u in _units(dv):
        if u.get("id") == uid:
            for e in (u.get("effects") or []):
                if isinstance(e, dict) and e.get("effectType") == etype:
                    return e
    return None


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
    """La SEQUENCE coup par coup du NATIF (tags `Amount` des events du pas `UnitDamaged`, resolu
    PAR NOM -- un ordinal fige designerait le pas VOISIN au prochain retrait de membre, sans erreur
    ni trace). Un TOTAL juste ne prouve rien : c'est la sequence qui mord."""
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


def _drive(rpc, rid, tours=12):
    """DEPLACE Calandis jusqu'a une cible a portee -- on ne se plaint JAMAIS de la geometrie de
    spawn, on la FABRIQUE."""
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
        if 1 <= hexgeo.distance(_pos(me), _pos(tgt)) <= RANGE:
            return me, tgt
        tiles = _movable(rpc, rid, me["id"])
        if tiles:
            tp = _pos(tgt)
            best = min(tiles, key=lambda p: (0 if 1 <= hexgeo.distance(p, tp) <= RANGE else 1,
                                             hexgeo.distance(p, tp)))
            _act(rpc, rid, {"kind": "move", "unitId": me["id"],
                            "to": {"col": best[0], "row": best[1]}}, 60)
        else:
            _act(rpc, rid, {"kind": "endturn"}, 60)
    return None, None


def _aplatir(noeud) -> list:
    """Deplie les `Seq` imbriques en une liste de feuilles, dans l'ordre d'execution."""
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
    """Les DEUX donnees obligatoires du registre, et le contrat de DISJONCTION -- verifie PAR LE
    CODE, jamais soustrait d'un compteur."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   RANGED_BOOL_IF_RANGED_CASTER,
                                                   RANGED_BOOL_TRUE,
                                                   TARGETING_OPTIONS_UNPORTED)
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    assert ABILITY_CLASSES.get(ABILITY) is FireAndRepositionAbility
    assert FireAndRepositionAbility.ABILITY_ID == FIRE_AND_REPOSITION_ID == "FireAndReposition"

    opts = FireAndRepositionAbility.TARGETING_OPTIONS
    assert opts is not None, "sans masque, AUCUN gate n'est applique (degradation permissive)"
    # `<TargetingOptions statics>+0x28` = `<preset +0x00>+0x28` = 0x4002, LU dans le `.cctor`.
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy) == 0x4002
    assert opts.self_cast is False                       # `<preset>+0x00 isSelfCasting = 0`
    # `<preset>+0x08` = copie de `TargetingRange statics+0x00` = RANGE_ADJACENT_IF_MELEE_CASTER :
    # `onlyAdjacent = IfNotRangedCaster`, et SURTOUT PAS `useRangeFromConfig` -- la config 1063 ne
    # porte AUCUNE constante `range`, il n'y aurait rien a lire.
    assert opts.range is not None
    assert opts.range.use_range_from_config is False
    assert opts.range.use_whole_board is False
    assert opts.range.override_range is None
    assert int(opts.range.only_adjacent) == 3            # RangedBool.IfNotRangedCaster
    # `<preset>+0x20` = 2. 1063 etait la SEULE de son lot dans ce regime : recopier le `1`
    # (`RangedBool.False`) d'une voisine aurait produit un masque FAUX, qui ne rougit nulle part.
    assert int(opts.force_melee_target) == RANGED_BOOL_IF_RANGED_CASTER == 2
    assert int(opts.force_melee_target) != RANGED_BOOL_TRUE, "temoin : la valeur voisine vaut 0"

    # 3e argument d'`AActiveAbility$$.ctor(this, &opts, 2)` -- TRANSCRIT, surtout pas deduit : le
    # cast FRAPPE (attaque normale dispatchee), ce qui ferait ecrire `DirectTargetAttack` a l'oeil.
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.Others == 2
    assert ABILITY_ATTACK_TYPE.get(ABILITY) != AbilityAttackType.DirectTargetAttack

    # DISJONCTION : 1063 a MIGRE hors de `TARGETING_OPTIONS_UNPORTED` avec ce port (elle y etait,
    # son porteur etant dans le pool spawnable). Deux sources pour un meme masque = contrat viole.
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED, "deux sources de masque = contrat viole"
    assert ABILITY not in DYNAMIC_TARGET_RULE_UNPORTED


def test_ordre_des_feuilles_offline():
    """L'ORDRE `(attaque + ResetMovement) + AddEffect`, feuille par feuille et selecteur par
    selecteur.

    C'EST LA GARDE QUI PORTE LE PLUS ICI, et c'est mesurable : les trois feuilles sont
    DETERMINISTES entre elles (`ResetMovement` et `AddEffect` ne tirent AUCUN rng), donc permuter
    l'attaque et le reset ne changerait NI le degat NI le flux `state.rng` -- un test << le cast
    fire, les trois volets sont la >> resterait VERT sur un arbre faux. Seule une garde d'ORDRE le
    voit. Et l'ordre ne se DEDUIT pas : `StrikeFromTheShadows` (1225), MEME patron a trois
    feuilles, MEME famille de selecteurs, emboite `(atk + eff) + reset`.
    """
    from engine.runner.abilities.behaviours.combat import UseActiveAbility
    from engine.runner.abilities.behaviours.effects import AddEffect
    from engine.runner.abilities.behaviours.movement import ResetMovement

    feuilles = _aplatir(fire_and_reposition_tree())
    noms = [type(f).__name__ for f in feuilles]
    assert noms == ["UseActiveAbility", "ResetMovement", "AddEffect"], noms

    atk = next(f for f in feuilles if isinstance(f, UseActiveAbility))
    # `UseActiveAbility(subject = Caster@DSLSelectors+0x48, targets = Target@+0x60)`.
    assert type(atk.subject_sel).__name__ == "Caster"
    assert type(atk.targets_sel).__name__ == "Target"

    reset = next(f for f in feuilles if isinstance(f, ResetMovement))
    # `ResetMovement(targets = Owner@DSLSelectors+0x30)` -- l'OWNER, pas le caster ni la cible.
    assert type(reset.targets_sel).__name__ == "Owner"

    eff = next(f for f in feuilles if isinstance(f, AddEffect))
    assert eff.effect_type == EFFECT == 0x456
    assert eff.name == EffectType.FireAndReposition_ReduceDmg.name
    # `targets` ET `source` lisent tous deux `DSLSelectors+0x48` : l'effet est un buff DEFENSIF sur
    # SOI. Le poser sur `Target()` serait un debuff -- l'erreur exactement symetrique de 1225.
    assert type(eff.target_sel).__name__ == "Caster"
    assert type(eff.source_ref).__name__ == "Caster"
    # 3e argument natif `abilityState` : sans lui, la magnitude de 1110 retombe sur le niveau
    # PASSIF -- c'est le regime qui a refute le port initial de l'effet (#366-r1).
    assert eff.scale_from_source is True


def test_duree_de_l_effet_offline():
    """`TurnsFromRounds(1)` NU -- et le TEMOIN que la duree VOISINE vaudrait un tour de plus.

    Le decompile passe le resultat de `DSLFormulas$$TurnsFromRounds(1)` DIRECTEMENT en 6e argument
    d'`AddEffect`. `StrikeFromTheShadows` (1225), lui, passe
    `Sum(TurnsFromRounds(1), <DSLFormulas+0x20 = Direct(1)>)` = `TurnsUntilEndOfCurrentPlayersNextTurn`.
    Recopier la duree de la soeur depasserait d'UN TOUR, sans rien casser d'observable au cast."""
    from engine.runner.abilities.base import (convert_rounds_to_turns,
                                              turns_until_end_of_current_players_next_turn)
    from engine.runner.abilities.behaviours.effects import AddEffect
    from engine.runner.state import State

    eff = next(f for f in _aplatir(fire_and_reposition_tree()) if isinstance(f, AddEffect))
    assert eff.duration_rounds == 1
    assert eff.duration_turns is None, (
        "`duration_turns` est PRIORITAIRE sur `duration_rounds` : le renseigner ici court-circuiterait "
        "la conversion `TurnsFromRounds`")

    st = State()
    st.turn_order_player_count = 2            # deux joueurs non-Environment (cas des runners)
    assert convert_rounds_to_turns(st, 1) == 2
    assert turns_until_end_of_current_players_next_turn(st) == 3, (
        "temoin : la duree VOISINE (celle de 1225) vaut UN TOUR DE PLUS")


# ---------------------------------------------------------------------------------- LIVE

@pytest.fixture(scope="module", params=COUPLES, ids=["%s/%s" % c for c in COUPLES])
def env(request, live_session, rpc, build_runner):
    """Runner `--no-ai`. `eldarRanger` est dans le pool -> aucune injection catalogue.

    Crit et block sont mis a 0 des DEUX cotes : un coup CRITIQUE ou BLOQUE ne serait pas comparable
    a un rejeu deterministe, et le regime nominal en produirait au hasard."""
    BOARD, SEED = request.param
    built = build_runner(SEED, extra=[
        "--board", BOARD, "--rank", "17", "--no-ai",
        "--crit", "0,0", "--crit-target", "0,0",
        "--block-player", "0,0", "--block-target", "0,0",
        "--p-units", "%s,%s" % (CASTER, ALLY), "--a-units", ENEMIES], keep=True)
    rid = built["rid"]
    dv = _vue(rpc, rid)
    assert _by_vis(dv, CASTER) is not None, "%s absent du plateau -- montage KO" % CASTER
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph KO"
    return {"rid": rid, "board": Board(bg["tiles"], adjacency="evenq")}


@pytest.fixture(scope="module")
def cast(env, rpc):
    """UN cast, mesure sous toutes ses faces -- l'ORDRE des mesures est CONTRAINT et ce n'est pas un
    detail : le second pas rendu par `ResetMovement` RE-POSE `Moved`/`ArrivedAtFinalTile`, donc il
    est joue EN DERNIER."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import get_invalid_target_reason
    from engine.runner.messages import MoveUnitMessage

    rid, board = env["rid"], env["board"]
    me, tgt = _drive(rpc, rid)
    assert me is not None and tgt is not None, "aucune cible amenee a portee -- montage non conforme"
    cid, tid = me["id"], tgt["id"]

    # -- GATE : le natif est interroge SANS muter, AVANT le cast. `fromHere` (pas `targets`) : le
    #    port evalue depuis la TUILE COURANTE, alors que `targets` inclut le deplacement.
    nat_t = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
    legales, lignes_ability = set(), 0
    for urow in ((nat_t or {}).get("units") or []):
        if urow.get("unitId") != cid:
            continue
        for arow in (urow.get("abilities") or []):
            if arow.get("abilityId") != ABILITY:
                continue
            lignes_ability += 1
            for t in (arow.get("fromHere") or []):
                if isinstance(t, dict) and t.get("targetId") is not None:
                    legales.add(int(t["targetId"]))

    mov_avant = _movable(rpc, rid, cid)
    dv0, ob0, st = _etat(rpc, rid, board)
    mt_avant = (list(st.rng.mt), st.rng.mti)
    eff_caster_avant = _effects(dv0, cid)
    hp_avant = {u["id"]: _hp(ob0, u["id"]) for u in _units(dv0)}
    runner = Runner(st).install_default_handlers(20)
    flags = st.get_entity(cid).get_component(UnitFlagsComponent)

    # -- GATE cote PORT, sur la MEME capture, AVANT toute mutation.
    ability = ABILITY_CLASSES[ABILITY]()
    gate = []
    for u in _units(dv0):
        uid = u["id"]
        gate.append({"uid": uid, "visualId": u.get("visualId"),
                     "ami": u.get("owner") == me.get("owner"),
                     "d": hexgeo.distance(_pos(me), _pos(u)),
                     "natif": uid in legales,
                     "port": get_invalid_target_reason(st, cid, uid, ability) == 0,
                     "reason": get_invalid_target_reason(st, cid, uid, ability)})

    res = _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                          "abilityType": ABILITY})
    a0 = ((res or {}).get("actions") or [{}])[0]
    assert a0.get("ok") and a0.get("mutated"), "le natif REFUSE le cast : %r" % (a0,)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    live = {u: (hp_avant[u] - _hp(ob2, u)) for u in hp_avant
            if hp_avant.get(u) is not None and _hp(ob2, u) is not None
            and hp_avant[u] != _hp(ob2, u)}
    mt_natif = rpc("dumpRng", {"runnerId": rid}, 30)

    runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
    diag = runner.ability_handler.last or {}
    off = {}
    for uid in hp_avant:
        e = st.get_entity(uid)
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is not None and hp_avant[uid] is not None and hp_avant[uid] != hc.hp:
            off[uid] = hp_avant[uid] - hc.hp

    dv_apres = rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                    "includeInactive": True}, 150)
    inst = next((e for e in (st.effects.by_unit.get(cid) or []) if e.effect_type == EFFECT), None)
    out = {"rid": rid, "board": board, "cid": cid, "tid": tid, "res": res, "diag": diag,
           "live": live, "off": off, "st": st, "runner": runner,
           "gate": gate, "gate_lignes": lignes_ability, "gate_legales": legales,
           # SNAPSHOT, pas la reference vivante : le second pas joue plus bas RE-POSE `Moved`, et
           # un test qui lirait l'objet mutable verrait l'etat d'APRES en croyant lire celui du cast.
           "flags_apres_cast": frozenset(flags.flags),
           "mov_avant": mov_avant, "eff_caster_avant": eff_caster_avant,
           "dv_apres": dv_apres, "effet_row": _effect_row(dv_apres, cid, EFFECT),
           "effet_inst": inst,
           "mt_egaux": (mt_natif is not None and _ok(mt_natif)
                        and list(mt_natif.get("mt") or []) == list(st.rng.mt)
                        and mt_natif.get("mti") == st.rng.mti),
           "mt_bouge": (list(st.rng.mt), st.rng.mti) != mt_avant,
           "mov_apres": _movable(rpc, rid, cid)}

    # LE SECOND PAS EN DERNIER : il RE-POSE `Moved`, donc il clot la fenetre d'action.
    d2 = sorted(out["mov_apres"])[0] if out["mov_apres"] else None
    if d2 is None:
        out["second_pas"] = {"ok": False, "raison": "aucune tuile rendue"}
    else:
        r = _act(rpc, rid, {"kind": "move", "unitId": cid, "to": {"col": d2[0], "row": d2[1]}}, 60)
        b0 = ((r or {}).get("actions") or [{}])[0]
        if b0.get("ok") and b0.get("mutated"):
            runner.apply(MoveUnitMessage(int(cid), (int(d2[0]), int(d2[1]))))
            out["second_pas"] = {"ok": True, "to": d2}
        else:
            out["second_pas"] = {"ok": False, "raison": "%r" % (b0,)}
    return out


def test_degats_bit_exact_live(cast):
    """La SEQUENCE de degats coup par coup, natif vs port, ET l'etat MT final.

    La config 1063 n'a NI `minDmg`/`maxDmg`, NI `nrOfHits`, NI `damageProfile` : ce que le port
    reproduit ici, c'est l'attaque NORMALE de Calandis, dispatchee par
    `UseActiveAbility(Caster, Target, UnitNormalAttackType(Caster))`."""
    diag = cast["diag"]
    # FACE EXECUTER : sans ce booleen, un cast non porte serait un no-op SILENCIEUX (0 degat,
    # 0 erreur), et la comparaison de deltas passerait pour un accord.
    assert diag.get("ported") is True, "1063 non portee : %r" % (diag,)
    assert diag.get("ability") == FIRE_AND_REPOSITION_ID
    assert cast["live"], ("aucun delta HP live -- temoin NUL : un accord en regime DEGENERE ne "
                          "prouve rien")
    assert cast["live"] == cast["off"], ("deltas HP live %r != offline %r"
                                         % (cast["live"], cast["off"]))
    atk = ((diag.get("attack") or {}).get("attack") or {})
    seq_natif = _montants_natifs(cast["res"])
    assert seq_natif, "aucun montant natif lu -- le canal d'events a change"
    assert list(atk.get("per_hit") or []) == seq_natif, (
        "SEQUENCE coup par coup : port %r != natif %r" % (atk.get("per_hit"), seq_natif))
    assert atk.get("hits") == len(seq_natif)
    # L'ETAGE RNG : si les deux MT ne sont pas au MEME point apres le cast, une egalite de montants
    # ne veut plus rien dire (c'est le flux qui aurait diverge, pas le degat).
    assert cast["mt_bouge"], "le port n'a tire AUCUN rng -- l'attaque n'a pas eu lieu"
    assert cast["mt_egaux"], "MT DESYNCHRONISE apres le cast : l'etage RNG a diverge"


def test_reset_movement_live(cast):
    """`ResetMovement(Owner)` : le deplacement EPUISE de Calandis lui est RENDU, et il est JOUE."""
    assert not cast["mov_avant"], (
        "Calandis a encore du mouvement AVANT le cast (%d tuiles) -- le reset ne serait pas "
        "observable, montage non conforme" % len(cast["mov_avant"]))
    assert cast["mov_apres"], "le natif ne rend AUCUNE tuile apres le cast -- ResetMovement muet"

    flags = cast["flags_apres_cast"]
    assert UnitFlagsComponent.MOVED not in flags, "le port garde `Moved` : ResetMovement inerte"
    # `ActiveAbilityUsed` est RE-POSE par la cloture du cast et `ResetMovement` ne le retire pas :
    # Calandis re-bouge, elle ne re-caste pas. C'est ce qui separe la feuille de `remove_turn_flags`.
    assert UnitFlagsComponent.ACTIVE_ABILITY_USED in flags
    assert cast["diag"].get("reset") == cast["cid"], (
        "le port a reset une AUTRE unite que l'owner : %r" % (cast["diag"].get("reset"),))

    # UNE CAPACITE SUPPOSEE NE VAUT RIEN : le pas a ete JOUE dans la fixture.
    assert cast["second_pas"].get("ok"), (
        "le second pas est REFUSE : %s" % cast["second_pas"].get("raison"))


def test_effet_pose_sur_le_caster_live(cast):
    """1110 est pose sur **ELLE-MEME** (`targets` = Caster@+0x48), pour `TurnsFromRounds(1)`, avec
    le niveau d'ability **ACTIVE** bake sur l'instance du port."""
    from engine.runner.abilities.base import (convert_rounds_to_turns,
                                              turns_until_end_of_current_players_next_turn)
    from engine.runner.components import has_effect_of_type
    cid, tid, st = cast["cid"], cast["tid"], cast["st"]

    assert EFFECT not in (cast["eff_caster_avant"] or []), "Calandis portait DEJA 1110 avant le cast"
    assert EFFECT in (_effects(cast["dv_apres"], cid) or []), "le natif n'a pas pose 1110"
    assert has_effect_of_type(st, cid, EFFECT), "le port n'a pas pose 1110 sur le CASTER"
    assert cast["diag"].get("effect_placed") is True

    # LA CIBLE ne le porte PAS -- des deux cotes. C'est l'erreur symetrique de 1225 (dont l'effet va
    # bien sur la cible) : un `AddEffect(..., Target())` ici ne casserait AUCUN degat.
    assert EFFECT not in (_effects(cast["dv_apres"], tid) or []), (
        "le natif a pose 1110 sur la CIBLE -- la lecture `targets = Caster@+0x48` serait fausse")
    assert not has_effect_of_type(st, tid, EFFECT), "le port a pose 1110 sur la CIBLE"

    # DUREE : le `remaining` natif doit valoir `TurnsFromRounds(1)`, PAS la duree voisine.
    # ⚠ ET LA VALEUR DU PORT DOIT Y ETRE COUPLEE. Mesure de cette tranche : une premiere version de
    # ce bras ne comparait que `remaining` natif a `convert_rounds_to_turns(st, 1)` -- deux
    # lectures de l'ORACLE, aucune du PORT. Une mutation `duration_turns=3` sur l'arbre le laissait
    # VERT (seule la garde offline rougissait). C'est `inst.remaining_turns` qui ferme le circuit.
    row = cast["effet_row"]
    inst = cast["effet_inst"]
    assert row is not None, "l'effet n'est pas publie par `decisionView` (inactifs inclus)"
    attendu = convert_rounds_to_turns(st, 1)
    voisine = turns_until_end_of_current_players_next_turn(st)
    assert row.get("remaining") == attendu, (
        "duree natif=%s, `TurnsFromRounds(1)`=%s (la duree VOISINE, celle de 1225, vaudrait %s)"
        % (row.get("remaining"), attendu, voisine))
    assert attendu != voisine, (
        "regime NON DISCRIMINANT : les deux durees coincident ici, la mesure ne tranche rien")
    assert inst is not None, "le port n'a materialise AUCUNE instance de 1110 sur le caster"
    assert inst.remaining_turns == row.get("remaining"), (
        "duree PORT=%s != duree NATIF=%s -- l'arbre ne passe pas `TurnsFromRounds(1)`"
        % (inst.remaining_turns, row.get("remaining")))

    # SCALE : `scale_from_source=True` bake le niveau de l'ability ACTIVE sur l'instance. Sans lui,
    # la magnitude de 1110 retomberait sur le niveau PASSIF (#366-r1 : natif 716, port 2992).
    assert inst is not None and type(inst).__name__ == "FireAndRepositionReduceDmgEffect", (
        "1110 est route sur %s" % (None if inst is None else type(inst).__name__))
    assert inst.active_ability_level is not None, (
        "`scale_from_source` n'a pas seede `active_ability_level` -- la magnitude retombera sur le "
        "niveau PASSIF")
    # Le bonus dans le SEUL regime ou le natif soustrait (ranged, tour ennemi) : NON NUL, sinon la
    # pose serait inerte et personne ne le verrait.
    eb = inst.create_effect_damage_malus_for_defense(False, None, {"is_turn_of_owner": False})
    assert eb is not None and eb.value > 0, (
        "l'instance posee ne soustrait RIEN (%r) -- la pose serait decorative" % (eb,))


def test_gate_de_cible_live(cast):
    """Le MASQUE, confronte cible par cible : natif (`abilityTargets.fromHere`) contre port
    (`get_invalid_target_reason`), sur TOUTES les unites vivantes -- AMIES comprises, puisque c'est
    `TargetIsEnemy` (0x4000) qui doit les refuser."""
    assert cast["gate_lignes"] > 0, (
        "`abilityTargets` ne publie AUCUNE ligne pour (unit, 1063) -- canal absent, rien mesure")
    assert cast["gate_legales"], (
        "le natif n'accepte AUCUNE cible -- temoin NUL : le port pourrait tout refuser pour la "
        "mauvaise raison sans que personne le voie")
    ecarts = [g for g in cast["gate"] if g["natif"] != g["port"]]
    assert not ecarts, "desaccord de ciblage sur %d cible(s) : %r" % (len(ecarts), ecarts)
    # DISCRIMINANCE : le balayage doit contenir au moins un ACCEPTE et un REFUSE, sinon << tout
    # accepte >> ou << tout refuse >> passerait pour un accord.
    assert any(g["port"] for g in cast["gate"]) and any(not g["port"] for g in cast["gate"]), (
        "balayage NON DISCRIMINANT (que des acceptes ou que des refuses) : %r" % (cast["gate"],))
    # Les AMIS sont refuses, et par `TargetIsEnemy` -- pas par la portee, qui les laisserait passer.
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    amis = [g for g in cast["gate"] if g["ami"]]
    assert amis, "aucun ami sur le plateau -- le bit `TargetIsEnemy` n'est pas exerce"
    for g in amis:
        assert g["reason"] == int(TR.TargetIsEnemy), (
            "ami %r refuse par %s au lieu de `TargetIsEnemy`" % (g["visualId"], hex(g["reason"])))


# ------------------------------------------------------------ face DECISION (#567-r1)
# `FireAndRepositionPlaybook` -- portee par #567-r1, alors que #567 l'avait laissee NON confrontee.
# FOYER UNIQUE du montage et des criteres : `probe_567r1_fire_and_reposition_decision.campagne`.

@pytest.fixture(scope="module")
def decision567():
    import probe_567r1_fire_and_reposition_decision as D567
    try:
        sid = D567._resolve_session()
    except Exception as e:
        pytest.skip("host indisponible (%s)" % (e,))
    sf = os.path.join(os.environ.get("TEMP", "."), "t567d_%s.json" % os.getpid())
    recs = D567.campagne(sid, sf, 56701, D567.BOARD)
    if not recs:
        pytest.skip("build KO -- session/host indisponible")
    return {rec["tag"]: rec for rec in recs}


def test_567r1_le_natif_RECULE_et_le_port_avec_lui(decision567):
    """`u(position) = 3/2 + 20 * distanceMoyenneAuxEnnemis + Tile(7)` : l'ability REND son
    deplacement a Calandis, donc le natif tire depuis la position la plus RECULEE encore legale.
    Le port doit proposer la MEME ability, la MEME cible et la MEME tuile."""
    rec = decision567["recul"]
    assert rec["natif"]["ability"] == 1063, (
        "le natif ne caste pas 1063 -- montage sterile : %r" % (rec["natif"],))
    assert rec["port"].get("ability") == 1063
    assert rec["port"].get("target") == rec["natif"]["target"]
    assert rec["port"].get("to") == rec["natif"].get("move")
    assert rec["d_natif"] > rec["d_origine"], (
        "la tuile choisie n'est pas un RECUL (d=%s vs origine d=%s) : le terme de distance ne "
        "serait pas exerce" % (rec["d_natif"], rec["d_origine"]))


def test_567r1_l_argmax_STRICT_est_reproduit_et_ATTRIBUABLE(decision567):
    """Le bras `recul` ne suffit PAS : la decomposition y montre CINQ positions eligibles a la MEME
    utilite 91.5 (`20*d` et `Tile(7)` se compensent), donc le keep-first tranche et l'accord
    n'attribue rien. Le bras `attribution` place l'ennemi d'apres la table `Tile(7)` MESUREE pour
    que l'argmax soit STRICT (marge 30) sur une tuile que `Tile(7)` seul ne designerait pas."""
    rec = decision567["attribution"]
    assert rec["natif"]["ability"] == 1063
    assert rec["natif"].get("move") == rec["port"].get("to")
    elig = [x for x in rec["decomposition"] if x[1] and x[5] is not None]
    assert elig, "aucune position eligible dans la decomposition -- rien a departager"
    us = sorted((x[5] for x in elig), reverse=True)
    assert len(us) > 1 and us[0] > us[1], (
        "l'argmax n'est PAS strict (%r) : ce bras ne mesure pas ce qu'il annonce" % (us[:3],))


def test_567r1_les_DEUX_contre_epreuves_MORDENT_sur_le_bras_attribuant(decision567):
    """`poids -20` (signe inverse) ET `poids 0` (terme neutralise) doivent tous deux DEPLACER le
    choix du port. Sans la seconde, `Tile(7)` seul pourrait produire le meme accord -- c'est
    exactement ce qui se passe sur `recul`, ou elle est NON discriminante et n'est donc pas exigee."""
    rec = decision567["attribution"]
    assert rec["signe"].get("to") != rec["port"].get("to"), (
        "poids -20 rend la MEME tuile : le terme de distance n'est pas ce qui choisit")
    assert rec["sans_terme"].get("to") != rec["port"].get("to"), (
        "poids 0 rend la MEME tuile : `Tile(7)` seul suffirait, ce banc n'ATTRIBUE rien")
