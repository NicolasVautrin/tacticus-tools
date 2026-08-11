"""#911 -- `DaemonicPatrons` (ActiveAbilityType 1203, `emperFlawlessBlade` << Hascule >>), face COMBAT.

CE QUE CE FICHIER GARDE (le probe MESURE, le test GARDE) :

  * le REGISTRE : 1203 dans `ABILITY_CLASSES`, son `TARGETING_OPTIONS` (masque PRESET+FLAGS
    `0x4000 | 0x200000000`, RANGE_ADJACENT, `RangedBool.False`) et son `ABILITY_ATTACK_TYPE` ;
  * la FORME DE L'ARBRE : `AddBondEffect(27) & (AddEffect(1464) & AddEffect(1465))`, avec la MEME
    duree EN TOURS sur les trois feuilles -- un `duration_rounds` y perdrait le `Const(1)` de
    `Sum(TurnsFromRounds(nrOfRounds), Const(1))` ;
  * la POSE LIVE : les trois effets sur les BONNES unites, a la duree POSEE que le natif publie
    dans ses events (`Effect_RemainingTurns=3`) ;
  * LE FILTRE, qui est le coeur du cas : `n` = les ennemis adjacents **TAUNTES**, pas les ennemis
    adjacents. Le montage pose DEUX adjacents dont UN SEUL taunte, donc un collapse du
    `Filter(..., HasEffect(It, 27))` rendrait 2 au lieu de 1 ;
  * LES DEUX MAGNITUDES en fonction de `n` : `+extraDmg x n` (lineaire, nulle a 0) et
    `-Min(100, dmgReductionPct x n)` (NEGATIVE, lineaire, CAPEE a -100). Le live ne peut pas
    depasser `n = 1` -- le cast ne taunte qu'une cible -- donc cet etage est OFFLINE, sur les
    INSTANCES REELLES posees par le cast.

CE QUI N'EST PAS COUVERT ICI, et le probe le dit aussi : la triggered `1473 DaemonicPatrons_Finale`
(residu **#911-r1**, RE lue et citee dans `engine/runner/abilities/emperorschildren.py`), et la face
DECISION (la cle `adjacent_taunted_enemies` est posee dans `Scene.unit_state` et les deux ctx de
prediction, mais aucun etage ne la confronte a `attackPlans`).

Detail, mesures et matrice de mutants : `docs/rl/case-911-daemonic-patrons.md`.
ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: PORTEE PRISE LARGE : le port touche l'arbre d'ability, DEUX classes d'effet, le foyer de
#: comptage de `runner/components.py`, les DEUX canaux de degat et les DEUX sites de prediction --
#: donc tout `engine/**` est dans le rayon, plus le harnais de montage (`catalog_inject`, sans
#: lequel le porteur n'arrive pas en bataille).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/rl_duel.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": ("Confrontation LIVE port-vs-natif de `1203 DaemonicPatrons` : arbre "
               "`AddBondEffect(27) & (AddEffect(1464) & AddEffect(1465))`, compteur "
               "`GetNumAdjacentTauntedEnemies` (foyer `runner/components.py`), et les deux canaux "
               "de degat (additif ATTAQUANT / pourcent NEGATIF DEFENSEUR). Le porteur "
               "`emperFlawlessBlade` est HORS pool ET HORS catalogue : le montage passe par "
               "`catalog_inject.write_augmented_seed_bc`."),
}

import uuid

import pytest

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.emperorschildren import (DAEMONIC_PATRONS_ID, DaemonicPatronsAbility,
                                                      daemonic_patrons_duration_turns,
                                                      daemonic_patrons_tree)
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

BOARD = "MC1_67"
SEED = "911"
CASTER = "emperFlawlessBlade"           # HERO `lineup` HORS pool ET HORS seed BC -> catalog_inject
FOES = "tauCrisis,tauCrisis"            # DEUX adjacents ; UN SEUL sera taunte
ABILITY = int(ActiveAbilityType.DaemonicPatrons)               # 1203 = 0x4b3
EF_TAUNT = int(EffectType.Taunted_OnlySpecificTargets)         # 27 = 0x1b
EF_EXTRA = int(EffectType.DaemonicPatrons_ExtraDamage)         # 1464 = 0x5b8
EF_REDUC = int(EffectType.DaemonicPatrons_DmgReduction)        # 1465 = 0x5b9
CASTER_TILE, TAUNT_TILE, PLAIN_TILE = (3, 4), (3, 5), (2, 4)
#: `Min(Const(100)@DSLFormulas+0x30, .)` -- LU dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor`.
CAP = 100


# ------------------------------------------------------------------ helpers de lecture live

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _vue(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _units(dv):
    return [u for u in ((dv or {}).get("units") or []) if u.get("alive")]


def _par_tuile(dv):
    out = {}
    for u in _units(dv):
        p = u.get("pos") or {}
        out[(p.get("col"), p.get("row"))] = int(u.get("id"))
    return out


def _effets(dv, uid):
    """{effectType -> remaining} de l'unite, LU de `decisionView`.

    ⚠ `remaining` y est DEJA decremente par l'`Effect_Refresh` du `[EndTurn]` que le cast
    declenche : ce canal atteste la PRESENCE, la DUREE POSEE se lit cote port (le test la confronte
    a la formule, pas a ce champ)."""
    for u in _units(dv):
        if int(u.get("id")) == int(uid):
            return {int(e.get("effectType")): e.get("remaining")
                    for e in (u.get("effects") or []) if isinstance(e, dict)}
    return {}


def _etat(rpc, rid, board):
    """Capture COMPLETE + MT cale sur `dumpRng` : sans lui le degat offline est un faux 0."""
    dv = _vue(rpc, rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 90)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 120)
    ab = rpc("unitAbilityStates", {"runnerId": rid}, 90)
    assert _ok(dv) and _ok(ob) and _ok(snap), "capture live KO -- montage non installe"
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    assert _ok(s), "dumpRng KO -- MT non calable"
    st = load_state(dv, ob, snap, board=board, ability_states=ab)
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(s["mt"]), s["mti"]
    st.rng = rng
    return dv, st


# ------------------------------------------------------------------------------- OFFLINE

def test_registre_offline():
    """Les DEUX donnees obligatoires du registre + le contrat de DISJONCTION -- RELUES PAR LE CODE."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   TARGETING_OPTIONS_UNPORTED)
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    assert ABILITY_CLASSES.get(ABILITY) is DaemonicPatronsAbility, "1203 absente du registre"
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.DirectTargetAttack, (
        "3e argument d'`AActiveAbility$$.ctor` = litteral 0 = DirectTargetAttack -- TRANSCRIT, "
        "et l'arbre de 1203 ne frappe pourtant PAS")
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED, "contrat de disjonction du masque"
    assert ABILITY not in DYNAMIC_TARGET_RULE_UNPORTED, "aucune regle dynamique (les deux virtuels "\
                                                        "retombent sur la base, qui rend 0)"

    opts = DaemonicPatronsAbility.TARGETING_OPTIONS
    assert opts is not None, ("sans TARGETING_OPTIONS, `get_invalid_target_reason` rend 0 "
                              "IMMEDIATEMENT -- degradation PERMISSIVE et silencieuse")
    attendu = int(TR.TargetIsEnemy) | int(TR.TargetIsNotAnObject)   # 0x4000 | 0x200000000
    assert int(opts.rules) == attendu == 0x200004000, (
        "masque EFFECTIF = `rules(preset statics+0x40) | additionalRules` de la surcharge "
        "PRESET+FLAGS -- pas le seul preset, pas les seuls flags")
    assert opts.self_cast is False
    assert opts.range is not None, "RANGE_ADJACENT (preset+0x08 = <TargetingRange statics>+0x30)"


def test_arbre_offline():
    """La FORME de l'arbre : trois feuilles, la MEME duree EN TOURS, le taunt EN PREMIER."""
    arbre = daemonic_patrons_tree(3)
    noms = []

    def _visite(n):
        noms.append(type(n).__name__)
        for attr in ("a", "b", "left", "right", "children", "items", "nodes"):
            v = getattr(n, attr, None)
            if v is None:
                continue
            for c in (v if isinstance(v, (list, tuple)) else (v,)):
                if hasattr(c, "execute"):
                    _visite(c)

    _visite(arbre)
    assert noms.count("AddBondEffect") == 1, "le TAUNT est une feuille de l'arbre : %s" % noms
    assert noms.count("AddEffect") == 2, "les DEUX buffs sont des feuilles : %s" % noms


def test_duree_offline():
    """`Sum(TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds)), Const(1)@formulas+0x20)`.

    Le `+1` vient d'un CHAMP de l'instance `DSLFormulas`, LU dans son `.ctor` -- il n'est ni une
    regle de cycle de vie ni un arrondi. `nrOfRounds` est LU de la config, jamais code en dur."""
    import gameconfig as GC
    from engine.runner.abilities.base import convert_rounds_to_turns

    class _S:
        turn_order_player_count = 2

    rounds = int(((GC.ability(DAEMONIC_PATRONS_ID) or {}).get("constants") or {})["nrOfRounds"])
    st = _S()
    assert daemonic_patrons_duration_turns(st) == convert_rounds_to_turns(st, rounds) + 1


def test_registre_effets_offline():
    """Les DEUX effets entrent au registre AVEC l'ability -- sinon le cast poserait des instances
    GENERIQUES, sans magnitude ni condition d'activite, et rien ne le dirait."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.daemonic_patrons import (DaemonicPatronsDmgReductionEffect,
                                                               DaemonicPatronsExtraDamageEffect)
    assert EFFECT_CLASSES.get("DaemonicPatrons_ExtraDamage") is DaemonicPatronsExtraDamageEffect
    assert EFFECT_CLASSES.get("DaemonicPatrons_DmgReduction") is DaemonicPatronsDmgReductionEffect


# ------------------------------------------------------------------------------- LIVE

@pytest.fixture(scope="module")
def env(live_session, rpc, build_runner, tmp_path_factory):
    """Runner `--no-ai` ou `emperFlawlessBlade` est INJECTE au catalogue (hors seed BC ET hors pool).

    Les positions sont FORCEES : le caster au contact de DEUX ennemis, dont un seul sera taunte.
    C'est ce montage-la qui rend le `Filter` du compteur discriminant."""
    import catalog_inject
    bc = tmp_path_factory.mktemp("seedbc") / ("hascule-%s.json" % uuid.uuid4().hex[:8])
    catalog_inject.write_augmented_seed_bc(str(bc), [CASTER])
    built = build_runner(SEED, extra=[
        "--seed-bc", str(bc), "--board", BOARD, "--no-ai",
        "--crit", "0,100", "--crit-target", "0,100",
        "--hp-player", "900000", "--hp-target", "900000",
        "--p-units", CASTER, "--a-units", FOES,
        "--place", "%s:%d,%d" % (CASTER, CASTER_TILE[0], CASTER_TILE[1]),
        "--a-place", "tauCrisis:%d,%d" % (TAUNT_TILE[0], TAUNT_TILE[1]),
        "--a-place", "tauCrisis:%d,%d" % (PLAIN_TILE[0], PLAIN_TILE[1])], keep=True)
    rid = built["rid"]
    dv = _vue(rpc, rid)
    par_tuile = _par_tuile(dv)
    assert par_tuile.get(CASTER_TILE) is not None, (
        "%s absent du plateau -- injection catalogue KO" % CASTER)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph KO"
    return {"rid": rid, "board": Board(bg["tiles"], adjacency="evenq"),
            "caster": par_tuile[CASTER_TILE], "tgt": par_tuile[TAUNT_TILE],
            "plain": par_tuile[PLAIN_TILE]}


@pytest.fixture(scope="module")
def cast(env, rpc):
    """Le cast NATIF, et son pendant HORS LIGNE sur la MEME capture (MT cale)."""
    dv0, st0 = _etat(rpc, env["rid"], env["board"])
    res = rpc("applyAction", {"runnerId": env["rid"], "action": {
        "kind": "ability", "casterId": env["caster"], "targetId": env["tgt"],
        "abilityType": ABILITY}}, 240)
    assert _ok(res), "le cast natif a echoue : %r" % (res,)
    Runner(st0).install_default_handlers(20).apply(
        ActiveAbilityMessage(caster_id=env["caster"], target_id=env["tgt"], ability_type=ABILITY))
    return {"apres": _vue(rpc, env["rid"]), "port": st0}


def test_pose_les_trois_effets_live(env, cast):
    """LA POSE : le bond sur la CIBLE, les DEUX buffs sur le CASTER, et RIEN sur le second ennemi."""
    nat_c = _effets(cast["apres"], env["caster"])
    nat_t = _effets(cast["apres"], env["tgt"])
    nat_p = _effets(cast["apres"], env["plain"])
    assert EF_TAUNT in nat_t, "le natif n'a pas taunte la cible -- montage KO"
    assert EF_EXTRA in nat_c and EF_REDUC in nat_c, "les deux buffs vivent sur le CASTER"
    assert EF_TAUNT not in nat_p, ("le second ennemi ne doit PAS etre taunte -- c'est LUI qui rend "
                                   "le compteur discriminant")
    st = cast["port"]
    port = {uid: sorted(e.effect_type for e in (st.effects.by_unit.get(int(uid)) or [])
                        if not e.consumed)
            for uid in (env["caster"], env["tgt"], env["plain"])}
    assert EF_TAUNT in port[env["tgt"]], "port : bond ABSENT de la cible"
    assert EF_EXTRA in port[env["caster"]] and EF_REDUC in port[env["caster"]], (
        "port : un des deux buffs manque au caster")
    assert EF_TAUNT not in port[env["plain"]], "port : le second ennemi est taunte a tort"


def test_duree_posee_live(env, cast):
    """La duree POSEE cote port == `convert_rounds_to_turns(nrOfRounds) + 1`.

    Le natif la publie a **3** dans ses events (`ReceiveEffect ... Effect_RemainingTurns=3`, cf.
    `probe_911_daemonic_patrons.py` etage E1) ; `decisionView`, lui, est capture APRES le `[EndTurn]`
    du cast et rend **2**. On garde donc ici la valeur POSEE, et on verifie que le canal
    `decisionView` reste a exactement UN decrement -- ce qui interdit un `duration_rounds`, qui
    rendrait 6 (2 joueurs)."""
    st = cast["port"]
    attendu = daemonic_patrons_duration_turns(st)
    assert attendu == 3, "2 joueurs, nrOfRounds=1 -> 1*2 + 1 = 3 (mesure du montage)"
    for uid, et in ((env["tgt"], EF_TAUNT), (env["caster"], EF_EXTRA), (env["caster"], EF_REDUC)):
        rt = next((e.remaining_turns for e in (st.effects.by_unit.get(int(uid)) or [])
                   if int(e.effect_type) == et), None)
        assert rt == attendu, "duree posee %s pour l'effet %s (attendu %s)" % (rt, et, attendu)
    nat = _effets(cast["apres"], env["caster"]).get(EF_EXTRA)
    assert nat == attendu - 1, ("`decisionView` doit etre a EXACTEMENT un decrement de la duree "
                               "posee (natif %s, pose %s)" % (nat, attendu))


def test_compteur_ne_compte_que_les_tauntes_live(env, cast):
    """LE FILTRE. Deux ennemis ADJACENTS, un seul TAUNTE -> `n == 1`, pas 2.

    C'est l'etage que ce montage existe pour exercer : le compte SANS filtre (`adjacent_enemies_count`,
    le foyer de `SupaCyborkBody`) rend 2 sur le MEME etat, donc l'ecart n'est pas theorique."""
    from engine.runner.components import adjacent_enemies_count, adjacent_taunted_enemies_count
    st = cast["port"]
    n = adjacent_taunted_enemies_count(st, env["caster"])
    tous = adjacent_enemies_count(st, env["caster"])
    assert tous == 2, "montage KO : le caster doit avoir DEUX ennemis adjacents (%s)" % tous
    assert n == 1, ("`GetNumAdjacentTauntedEnemies` doit rendre 1 (le seul TAUNTE), pas %s -- "
                    "un collapse du `Filter(..., HasEffect(It, 27))` rendrait %s" % (n, tous))


def test_magnitudes_par_n_live(env, cast):
    """LES DEUX MAGNITUDES, sur les INSTANCES REELLES posees par le cast.

    Le live ne peut pas depasser `n = 1` (le cast ne taunte qu'UNE cible), donc un facteur `x n`
    faux -- `x 1` en dur, ou un `n` capte a la pose -- passerait tous les etages live. On force
    donc `n` dans le contexte du canal, ce qui exerce le PRODUIT et le CAP."""
    st = cast["port"]
    inst = {int(e.effect_type): e for e in (st.effects.by_unit.get(int(env["caster"])) or [])}
    ex, rd = inst.get(EF_EXTRA), inst.get(EF_REDUC)
    assert ex is not None and rd is not None, "les deux instances doivent exister pour cet etage"

    def _x(n):
        b = ex.create_effect_damage_bonus_for_attack(att_ctx={"adjacent_taunted_enemies": n})
        return None if b is None else int(b.value)

    def _r(n):
        b = rd.create_effect_damage_malus_for_defense(attacker_ctx={"adjacent_taunted_enemies": n})
        return None if b is None else int(b.value)

    v1 = _x(1)
    assert v1 is not None and v1 > 0, "extraDmg nul a n=1 -- l'effet serait INERTE"
    assert _x(0) is None, "`Multiply(ConfigVar, 0)` = 0 -> aucune contribution"
    assert _x(2) == 2 * v1 and _x(4) == 4 * v1, "`Multiply(ConfigVar(extraDmg), n)` est LINEAIRE"

    p1 = _r(1)
    assert p1 is not None and p1 < 0, ("la reduction sort au slot ForPercentIncrease avec un "
                                       "montant NEGATIF (`Multiply(Const(-1), .)`)")
    assert _r(0) is None, "aucune reduction sans ennemi taunte adjacent"
    assert _r(2) == 2 * p1 and 2 * p1 > -CAP, "lineaire tant que le cap n'est pas atteint"
    assert _r(4) == -CAP, "`Min(Const(100), pct x n)` -- le CAP porte sur le PRODUIT"


def test_condition_dactivite_live(env, cast):
    """`ADaemonicPatronsEffect$$CreateActiveCondition` = `AmountIsGreaterThanZero(n)`.

    Cle ABSENTE = non mesure -> on NE FERME PAS (degradation fidele, comme
    `StructuralAnalyser_Visual` / `SupaCyborkBody_CritDmgReduction`)."""
    st = cast["port"]
    inst = [e for e in (st.effects.by_unit.get(int(env["caster"])) or [])
            if int(e.effect_type) in (EF_EXTRA, EF_REDUC)]
    assert len(inst) == 2
    for e in inst:
        assert e.is_active({"adjacent_taunted_enemies": 1}) is True
        assert e.is_active({"adjacent_taunted_enemies": 0}) is False
        assert e.is_active({}) is True, "non mesure -> on ne ferme pas"
        assert e.is_active(None) is True
