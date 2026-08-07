"""#511 -- `StrikeFromTheShadows` (ActiveAbilityType 1225, `astarCyrus` << Cyrus >>), face COMBAT.

Ce que ces bras GARDENT (et pas seulement ce qu'ils mesurent) :

  * `test_registre_offline`      -- l'entree au registre porte SES DEUX donnees obligatoires
    (`TARGETING_OPTIONS` lu du preset statique `<TargetingOptions statics>+0x140`,
    `ABILITY_ATTACK_TYPE` = 3e argument d'`AActiveAbility$$.ctor`), et le contrat de DISJONCTION
    est verifie PAR LE CODE (1225 dans AUCUNE des listes `*_UNPORTED`) ;
  * `test_arbre_offline`         -- la FORME de l'arbre : trois volets, dans l'ORDRE du decompile
    (`(attaque + effet) + ResetMovement`), la cible de chaque selecteur, et surtout la DUREE, qui
    est `TurnsUntilEndOfCurrentPlayersNextTurn` et NON `TurnsFromRounds(1)` -- un tour d'ecart ;
  * `test_reset_movement_flags_offline` -- `ResetMovement` retire EXACTEMENT les quatre flags du
    natif, et LAISSE `ActiveAbilityUsed` : c'est ce qui separe la feuille de `remove_turn_flags`,
    et ce qui empeche un re-cast infini ;
  * `test_degats_bit_exact_live`  -- la sequence de degats COUP PAR COUP, natif vs port, MT offline
    cale sur `dumpRng` ;
  * `test_reset_movement_live`    -- Cyrus, dont le deplacement est EPUISE avant le cast, en
    retrouve un apres ; le second pas est JOUE (une capacite supposee ne vaut rien) ;
  * `test_effet_pose_et_inerte_live` -- l'effet 0x60d est pose sur la CIBLE, et une attaque recue
    par une cible MARQUEE coute exactement ce que le port calcule : c'est la confrontation de la
    lecture << `EffectBonus` a trigger seul, six slots de magnitude a ZERO >> (verifiee AUX OCTETS
    de `StrikeFromTheShadowsEffect$$CreateEffectDamageMalusForDefense`).

Aucun `pytest.skip` de complaisance : un montage qui ne s'installe pas ECHOUE (#268). Le porteur
`astarCyrus` est un HERO `lineup` HORS seed BC -> `catalog_inject`
(cf. `docs/rl/case-92-catalog-injection.md` §6), meme voie que son passif `HaywireMine`.
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
        # `abilities/astartes.py` (l'arbre), `abilities/behaviours/movement.py` (la feuille
        # `ResetMovement`), `handler.py` + `attack_type.py` + `targeting.py` (les registres
        # confrontes), `abilities/base.py` (`turns_until_end_of_current_players_next_turn`),
        # `runner/components.py` (`UnitFlagsComponent`), `abilities/behaviours/combat.py` et
        # `operations/damage_ops/ability.py` (la route de degat), `runner/prng.py` (l'ORDRE de
        # consommation).
        "scripts/python/engine/**/*.py",
        # Les modules de la RACINE : la cascade des conftest de `tests/engine/runner` importe une
        # vingtaine de probes plus `hexgeo` / `engine_validate`. Ils entrent dans la fermeture de
        # CE fichier, qu'il les cite ou non.
        "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de `1225 StrikeFromTheShadows` : l'oracle est le "
              "jeu lui-meme (degat, ORDRE des tirages, pose et retrait des effets, portee du "
              "deplacement). Un changement de build peut donc faire changer ce fichier d'avis "
              "sans qu'une ligne du port bouge.",
}

import uuid

import pytest

import hexgeo

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.astartes import (STRIKE_FROM_THE_SHADOWS_ID,
                                              StrikeFromTheShadowsAbility,
                                              strike_from_the_shadows_tree)
from engine.runner.components import HealthComponent, UnitFlagsComponent
from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

BOARD = "MC1_67"
SEED = "777"
CASTER = "astarCyrus"                   # HERO `lineup` hors seed BC -> catalog_inject
ALLY = "ultraTitus"
ENEMIES = "orksNob,necroWarden"
ABILITY = int(ActiveAbilityType.StrikeFromTheShadows)          # 1225
EFFECT = int(EffectType.StrikeFromTheShadows)                  # 1549 = 0x60d
RANGE = 3                                                      # gameconfig `range`


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
    """La SEQUENCE coup par coup du NATIF (tags `Amount` des events `action` step 4). Un TOTAL
    juste ne prouve rien : c'est la sequence qui mord."""
    import json as _j
    out = []
    for a in ((res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            if e.get("step") != 4:
                continue
            try:
                t = _j.loads(e.get("tags") or "{}")
            except Exception:
                continue
            if "Amount" in t and t.get("Active_Ability_Type") is not None:
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


def _drive(rpc, rid, tours=10):
    """DEPLACE Cyrus jusqu'a une cible a portee -- on ne se plaint jamais de la geometrie de spawn."""
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


# ------------------------------------------------------------------------------- OFFLINE

def test_registre_offline():
    """Les DEUX donnees obligatoires du registre, et le contrat de DISJONCTION -- RE-COMPTE PAR LE
    CODE, jamais soustrait."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   TARGETING_OPTIONS_UNPORTED)
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    assert ABILITY_CLASSES.get(ABILITY) is StrikeFromTheShadowsAbility

    opts = StrikeFromTheShadowsAbility.TARGETING_OPTIONS
    assert opts is not None, "sans masque, AUCUN gate n'est applique (degradation permissive)"
    # `<TargetingOptions statics>+0x168` = `<preset +0x140>+0x28` = 0x4002, LU dans le `.cctor`.
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy) == 0x4002
    assert opts.self_cast is False                       # `<preset>+0x00 isSelfCasting = 0`
    assert opts.range is not None and opts.range.use_range_from_config is True   # statics+0x18
    assert int(opts.force_melee_target) == 0             # `<preset>+0x20` = RangedBool.True

    # 3e argument d'`AActiveAbility$$.ctor(this, &opts, 0)` -- TRANSCRIT, pas deduit du profil.
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.DirectTargetAttack

    # DISJONCTION : 1225 n'a JAMAIS ete dans ces listes (son porteur est hors pool), donc rien
    # n'a ete retire -- ce bras garde qu'aucune seconde source n'apparaisse.
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED, "deux sources de masque = contrat viole"
    assert ABILITY not in DYNAMIC_TARGET_RULE_UNPORTED


def test_arbre_offline():
    """La FORME de l'arbre, et la DUREE de l'effet -- le point ou une lecture pressee perd un tour."""
    from engine.runner.abilities.base import (convert_rounds_to_turns,
                                              turns_until_end_of_current_players_next_turn)
    from engine.runner.abilities.behaviours.effects import AddEffect
    from engine.runner.abilities.behaviours.movement import ResetMovement
    from engine.runner.state import State

    st = State()
    st.turn_order_player_count = 2            # deux joueurs non-Environment (cas des runners)
    arbre = strike_from_the_shadows_tree(st)

    # `op_Addition(op_Addition(atk, eff), reset)` : l'attaque part D'ABORD, le mouvement est rendu
    # EN DERNIER. Le nom de l'ability evoque l'inverse -- le natif tranche.
    feuilles = _aplatir(arbre)
    noms = [type(f).__name__ for f in feuilles]
    assert noms == ["AttackWithAttackDamage", "AddEffect", "ResetMovement"], noms

    eff = next(f for f in feuilles if isinstance(f, AddEffect))
    assert eff.effect_type == EFFECT and eff.name == EffectType.StrikeFromTheShadows.name
    # `Sum(TurnsFromRounds(1), <DSLFormulas+0x20 = Direct(1)>)` : le champ `+0x20` est le noeud
    # constant `1` alloue par `DSLFormulas$$.ctor` -- donc la duree vaut
    # `TurnsUntilEndOfCurrentPlayersNextTurn`, soit UN TOUR DE PLUS que `TurnsFromRounds(1)`.
    assert eff.duration_turns == turns_until_end_of_current_players_next_turn(st) == 3
    assert eff.duration_turns == convert_rounds_to_turns(st, 1) + 1
    assert convert_rounds_to_turns(st, 1) == 2, "temoin : la lecture pressee rendrait 2, pas 3"

    reset = next(f for f in feuilles if isinstance(f, ResetMovement))
    assert type(reset.targets_sel).__name__ == "Owner"      # `DSLSelectors+0x30`, pas la cible


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


def test_reset_movement_flags_offline():
    """`ResetMovement` retire les QUATRE flags du natif -- et LAISSE `ActiveAbilityUsed`.

    C'est ce qui le separe d'`UnitFlagsComponent$$RemoveTurnFlags` : celui-la retirerait aussi
    `ActiveAbilityUsed(2)` et `Teleported(0xc)`, ce qui rendrait l'ability infiniment re-castable.
    """
    from engine.runner.abilities.behaviours.movement import _RESET_MOVEMENT_FLAGS

    attendus = {UnitFlagsComponent.ARRIVED_AT_FINAL_TILE, UnitFlagsComponent.MOVED,
                UnitFlagsComponent.TURN_FINISHED_FORCED}
    assert set(_RESET_MOVEMENT_FLAGS) == attendus
    assert UnitFlagsComponent.ACTIVE_ABILITY_USED not in _RESET_MOVEMENT_FLAGS
    assert UnitFlagsComponent.TELEPORTED not in _RESET_MOVEMENT_FLAGS
    # `TurnFinished(3)` est retire par la feuille elle-meme (son RETOUR est LU par le natif, qui
    # en fait la condition de sa publication de stream) -- il n'est donc pas dans la constante.
    assert int(UnitFlagsComponent.TURN_FINISHED) == 3
    assert int(UnitFlagsComponent.TURN_FINISHED_FORCED) == 0x1b


# ---------------------------------------------------------------------------------- LIVE

@pytest.fixture(scope="module")
def env(live_session, rpc, build_runner, tmp_path_factory):
    """Runner `--no-ai` ou `astarCyrus` est INJECTE au catalogue (il est hors seed BC)."""
    import catalog_inject
    bc = tmp_path_factory.mktemp("seedbc") / ("cyrus-%s.json" % uuid.uuid4().hex[:8])
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
    """UN cast, mesure sous toutes ses faces. UN SEUL : l'ability est a usage unique par bataille
    (`UnitStats_ActiveAbility_CanStillBeUsed` passe a 0), donc c'est le regime NATUREL."""
    rid, board = env["rid"], env["board"]
    me, tgt = _drive(rpc, rid)
    assert me is not None and tgt is not None, "aucune cible amenee a portee -- montage non conforme"
    cid, tid = me["id"], tgt["id"]

    mov_avant = _movable(rpc, rid, cid)
    dv0, ob0, st = _etat(rpc, rid, board)
    eff_avant = _effects(dv0, tid)
    hp_avant = {u["id"]: _hp(ob0, u["id"]) for u in _units(dv0)}
    runner = Runner(st).install_default_handlers(20)
    flags = st.get_entity(cid).get_component(UnitFlagsComponent)

    res = _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                          "abilityType": ABILITY})
    a0 = ((res or {}).get("actions") or [{}])[0]
    assert a0.get("ok") and a0.get("mutated"), "le natif REFUSE le cast : %r" % (a0,)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
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
    out = {"rid": rid, "board": board, "cid": cid, "tid": tid, "res": res, "diag": diag,
           "live": live, "off": off, "st": st, "runner": runner,
           # SNAPSHOT, pas la reference vivante : le second pas joue plus bas RE-POSE `Moved`, et
           # un test qui lirait l'objet mutable verrait l'etat d'APRES en croyant lire celui du
           # cast (faute commise puis corrigee ici).
           "flags_apres_cast": frozenset(flags.flags),
           "mov_avant": mov_avant, "eff_avant": eff_avant, "dv_apres": _vue(rpc, rid),
           "mov_apres": _movable(rpc, rid, cid)}

    # LA SUITE DU SCENARIO EST JOUEE ICI, DANS L'ORDRE, et les tests n'en sont que des LECTURES.
    # L'ordre est CONTRAINT et ce n'est pas un detail : le second pas repose `Moved` et
    # `ArrivedAtFinalTile`, donc il CLOT la fenetre d'action -- mesure de ce cas, l'attaque
    # normale d'inertie jouee APRES revenait `ok:true, mutated:false`, un refus SILENCIEUX qui
    # accusait a tort le `ResetMovement`. On mesure donc l'inertie D'ABORD, le pas ENSUITE.
    out["inertie"] = _mesurer_inertie(rpc, rid, board, tid)
    out["second_pas"] = _jouer_second_pas(rpc, rid, cid, out["mov_apres"], runner)
    return out


def _mesurer_inertie(rpc, rid, board, tid):
    """Cyrus attaque NORMALEMENT la cible qu'il vient de marquer. Deux raisons de le prendre LUI :
    aucune geometrie a re-monter (la cible est deja a portee), et c'est le MEME geste qui exerce
    le `ResetMovement` -- sans lui son tour serait clos et l'attaque refusee. `applyAction` n'a pas
    de `kind: "attack"` : l'attaque normale est une ABILITY d'id CONCRET par unite."""
    dv = _vue(rpc, rid)
    att = _by_vis(dv, CASTER)
    if att is None:
        return {"ok": False, "raison": "Cyrus absent"}
    na = next((a["id"] for a in (att.get("abilities") or [])
               if a.get("kind") == "normal" and a.get("id") is not None), None)
    if na is None:
        return {"ok": False, "raison": "attaque normale introuvable"}
    dv0, ob0, st2 = _etat(rpc, rid, board)
    hp0 = _hp(ob0, tid)
    res = _act(rpc, rid, {"kind": "ability", "casterId": int(att["id"]),
                          "targetId": int(tid), "abilityType": int(na)})
    a0 = ((res or {}).get("actions") or [{}])[0]
    if not (a0.get("ok") and a0.get("mutated")):
        return {"ok": False, "raison": "attaque refusee : %r" % (a0,)}
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    natif = (hp0 or 0) - (_hp(ob2, tid) or 0)
    Runner(st2).install_default_handlers(20).apply(AttackUnitMessage(int(att["id"]), int(tid)))
    e = st2.get_entity(tid)
    hc = e.get_component(HealthComponent) if e is not None else None
    port = (hp0 or 0) - (hc.hp if hc is not None else 0)
    return {"ok": True, "natif": natif, "port": port}


def _jouer_second_pas(rpc, rid, cid, tuiles, runner):
    """UNE CAPACITE SUPPOSEE NE VAUT RIEN : on joue le pas rendu par `ResetMovement`."""
    from engine.runner.messages import MoveUnitMessage
    if not tuiles:
        return {"ok": False, "raison": "aucune tuile rendue"}
    d2 = sorted(tuiles)[0]
    r = _act(rpc, rid, {"kind": "move", "unitId": cid, "to": {"col": d2[0], "row": d2[1]}}, 60)
    a0 = ((r or {}).get("actions") or [{}])[0]
    if a0.get("ok") and a0.get("mutated"):
        runner.apply(MoveUnitMessage(int(cid), (int(d2[0]), int(d2[1]))))
        return {"ok": True, "to": d2}
    return {"ok": False, "raison": "%r" % (a0,)}


def test_degats_bit_exact_live(cast):
    """La SEQUENCE de degats coup par coup, natif vs port -- pas seulement le total."""
    diag = cast["diag"]
    # FACE EXECUTER : sans ce booleen, un cast non porte serait un no-op SILENCIEUX (0 degat,
    # 0 erreur), et la comparaison de deltas passerait pour un accord.
    assert diag.get("ported") is True, "1225 non portee : %r" % (diag,)
    assert cast["live"], ("aucun delta HP live -- temoin NUL : un accord en regime DEGENERE ne "
                          "prouve rien")
    assert cast["live"] == cast["off"], ("deltas HP live %r != offline %r"
                                         % (cast["live"], cast["off"]))
    atk = diag.get("attack") or {}
    seq_natif = _montants_natifs(cast["res"])
    assert seq_natif, "aucun montant natif lu -- le canal d'events a change"
    assert list(atk.get("per_hit") or []) == seq_natif, (
        "SEQUENCE coup par coup : port %r != natif %r" % (atk.get("per_hit"), seq_natif))
    assert atk.get("hits") == len(seq_natif)


def test_reset_movement_live(cast):
    """`ResetMovement(Owner)` : le deplacement EPUISE de Cyrus lui est RENDU, et il est JOUE."""
    assert not cast["mov_avant"], (
        "Cyrus a encore du mouvement AVANT le cast (%d tuiles) -- le reset ne serait pas "
        "observable, montage non conforme" % len(cast["mov_avant"]))
    assert cast["mov_apres"], "le natif ne rend AUCUNE tuile apres le cast -- ResetMovement muet"

    flags = cast["flags_apres_cast"]
    assert UnitFlagsComponent.MOVED not in flags, "le port garde `Moved` : ResetMovement inerte"
    # `ActiveAbilityUsed` est RE-POSE par la cloture du cast (`AddFlagsAfterAbilityExecution` --
    # la classe n'override NI `SetsEndTurnFlags` NI `SetsActiveAbilityUsedFlag`, verifie sur ses
    # QUATRE seules methodes), et `ResetMovement` ne le retire pas : Cyrus re-bouge, il ne
    # re-caste pas.
    assert UnitFlagsComponent.ACTIVE_ABILITY_USED in flags

    # UNE CAPACITE SUPPOSEE NE VAUT RIEN : le pas a ete JOUE dans la fixture.
    assert cast["second_pas"].get("ok"), (
        "le second pas est REFUSE : %s" % cast["second_pas"].get("raison"))


def test_effet_pose_et_inerte_live(cast):
    """L'effet 0x60d est pose sur la CIBLE, et il ne modifie PAS les degats qu'elle recoit.

    C'est la confrontation de la lecture << `EffectBonus` a TRIGGER SEUL >> : les six slots de
    magnitude (`+0x08` pct, `+0x10` addition, `+0x18` soustraction, `+0x20` minimum, `+0x28`
    override, `+0x30` reset) sont a ZERO -- verifie au decompile ET aux octets. L'attaquant est
    Cyrus lui-meme, dans la foulee : aucune geometrie a re-monter, et c'est le meme geste qui
    exerce le `ResetMovement` (sans lui, son tour serait clos et l'attaque refusee).
    """
    from engine.runner.components import has_effect_of_type
    tid, st = cast["tid"], cast["st"]

    assert EFFECT not in (cast["eff_avant"] or []), "la cible portait DEJA 1549 avant le cast"
    assert EFFECT in (_effects(cast["dv_apres"], tid) or []), "le natif n'a pas pose 1549"
    assert has_effect_of_type(st, tid, EFFECT), "le port n'a pas pose 1549"

    r = cast["inertie"]
    assert r.get("ok"), (
        "l'attaque normale post-cast n'a pas eu lieu (%s) -- soit le tour de Cyrus est clos (donc "
        "`ResetMovement` n'a pas mordu cote natif), soit le montage a change de main"
        % r.get("raison"))
    assert r["natif"] > 0, "temoin NUL : aucune blessure, la comparaison ne prouverait rien"
    assert r["natif"] == r["port"], (
        "attaque sur cible MARQUEE : natif=%s port=%s -- 1549 modifierait donc les degats recus, "
        "contre la lecture du decompile" % (r["natif"], r["port"]))
