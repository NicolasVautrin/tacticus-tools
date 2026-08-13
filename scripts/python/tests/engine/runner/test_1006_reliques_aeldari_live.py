"""#1006 -- reliques AELDARI `Maugetar` (1498, `eldarMauganRa`) et `PhoenixGem` (1458,
`eldarAutarch`), montees LIVE par `rl_duel build --equip-relic` (#237, etat 2 des trois).

CE QUE CE FICHIER GARDE, ET POURQUOI CHAQUE GARDE EXISTE
--------------------------------------------------------
* l'effet 1497 se materialise en `MaugetarHasNotMovedEffect` -- sans l'entree `EFFECT_CLASSES`,
  `EffectFactory` retombe SILENCIEUSEMENT sur `BaseEffect` et le descripteur #179 disparait ;
* son groupe n'existe QUE si l'attaque a crite (`AttackDamageIsCritical` = `hitGroup+0x3d`), et le
  tri-etat << non mesure >> ne fabrique PAS de groupe ;
* les bornes viennent de l'etat TERTIAIRE, pas de l'instance : au niveau 1 le natif sert
  `[1765, 2350]`, l'ancienne lecture servait `[2622, 3492]` (+49 %). C'est le REGIME SEPARANT --
  au niveau 10 les deux coincident, donc un montage a niveau 10 aurait rendu VERT le port FAUX ;
* le retrait au `On(PreUnitMove)` et le `ResetMovement` au `On(UnitPostAbility)` mordent sur le
  PORTEUR et sur lui seul ;
* `PhoenixGem` rend `hp[niveau de RELIQUE]`, pas `hp[dernier palier]`.

Le niveau **1** est choisi DELIBEREMENT : c'est le seul regime ou les deux modeles divergent.

Runner UNIQUE pour les deux reliques : les porteurs partagent leur roster (Aeldari), donc un seul
harnais -- c'est la raison d'etre du groupement de ce cas.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.components import (UnitComponent, HealthComponent, OwnerComponent,
                                      PositionComponent, UnitFlagsComponent)
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.pathfinding.board import Board
from engine.entities.effect_type import EffectType
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.loki.hits import MaugetarHasNotMovedEffect
from engine.entities.effects.magnitude import ability_var
from engine.runner.operations.triggers.base import triggered_ability_state
from engine.runner.operations.triggers.dispatch.move_death import (after_death_triggers,
                                                                   pre_move_triggers)
from engine.runner.operations.triggers.dispatch.ability import unit_post_ability_triggers
from engine.runner.operations.triggers.dispatch.turn import tile_tick_triggers
from engine.runner.operations.revive import kill_unit_revive_gate
from engine.runner.operations.triggers.loki.maugetar import MAUGETAR_HAS_NOT_MOVED
from engine.runner.operations.triggers.loki.phoenix_gem import PHOENIX_GEM_CAN_REVIVE

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # PERIMETRE LARGE, et c'est une MESURE : ce fichier importe `load_state`, la factory d'effets et
    # trois vecteurs de dispatch -- leur fermeture d'import atteint la quasi-totalite de
    # `scripts/python`. Declarer etroit produirait un FAUX VERT.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    # Le NATIF est l'oracle : la POSE des deux effets de relique, le niveau tertiaire publie par
    # `unitAbilityStates`, et les paliers `minDmg`/`maxDmg`/`hp` du gameconfig viennent tous du
    # build installe. Un changement de build peut faire basculer ces verdicts sans qu'une ligne du
    # port bouge.
    "build": True,
    "toujours": False,
    "raison": ("Lit l'etat live d'un runner monte avec --equip-relic (effets 1497/1451, niveau "
               "TERTIAIRE) et les registres du port (EFFECT_CLASSES, RELIC_ABILITY_TRIGGERS, "
               "EFFECT_TRIGGERS) ; tous vivent sous scripts/python, le reste sous data/."),
}

#: Niveau de relique du montage. **1 = REGIME SEPARANT** : `minDmg`/`maxDmg` et `hp` ont 10 paliers,
#: et l'ancienne lecture (l'instance, `ability_level = 50`) clampait au 10e. Au niveau 10 les deux
#: modeles coincident -- un montage a 10 aurait rendu VERT le port faux.
RELIC_LEVEL = 1
MAUGAN_RA, AETHANA = "eldarMauganRa", "eldarAutarch"
BUILD = ["--p-units", "%s,%s" % (AETHANA, MAUGAN_RA), "--a-units", "orksNob,orksRuntherd",
         "--rank", "17", "--board", "MC1_67",
         "--equip-relic", "%s:Maugetar:%d" % (MAUGAN_RA, RELIC_LEVEL),
         "--equip-relic", "%s:PhoenixGem:%d" % (AETHANA, RELIC_LEVEL)]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


@pytest.fixture(scope="module")
def env(live_session, rpc, build_runner):
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        pytest.skip("capture live KO")
    st = load_state(dv, ob, snap, board=board)
    if getattr(st, "effects", None) is None:
        pytest.skip("pas d'EffectsState")
    return {"dv": dv, "ob": ob, "snap": snap, "board": board}


def _fresh(env, seed=777):
    st = load_state(env["dv"], env["ob"], env["snap"], board=env["board"])
    st.rng = IntBasedMersenneTwister(seed)
    return st


def _unit(st, visual_id):
    for uid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == visual_id:
            return int(uid)
    pytest.skip("unite %s absente du runner" % visual_id)


def _insts(st, uid, etype):
    return [e for e in (st.effects.by_unit.get(int(uid)) or [])
            if int(getattr(e, "effect_type", -1) or -1) == int(etype) and not e.consumed]


def _ctx(st, uid, **extra):
    """Le ctx que `collect_additional_hit_groups` monte pour la branche PORTEUR (les quatre cles
    que #1006 y a ajoutees, plus le minimum que les autres descripteurs lisent)."""
    base = {"owner_id": int(uid), "att_id": int(uid), "is_melee": False,
            "tertiary_ability_state_of":
                lambda oid, ab: triggered_ability_state(st, int(oid), ab)}
    base.update(extra)
    return base


# --------------------------------------------------------------------------- Maugetar : la POSE
def test_relique_montee_les_deux_effets_sont_poses(env):
    """MESURE FONDATRICE. La prose du port disait `PhoenixGem` << non posable via rl_duel build >> :
    c'est PERIME depuis #237. Les DEUX effets de relique sont poses par le natif et publies."""
    st = _fresh(env)
    mr, ae = _unit(st, MAUGAN_RA), _unit(st, AETHANA)
    assert _insts(st, mr, MAUGETAR_HAS_NOT_MOVED), \
        "effet 1497 Maugetar_HasNotMoved absent -- la relique n'est pas montee"
    assert _insts(st, ae, PHOENIX_GEM_CAN_REVIVE), \
        "effet 1451 PhoenixGem_CanRevive absent -- la relique n'est pas montee"


def test_effet_1497_se_materialise_en_classe_portee(env):
    """`EFFECT_CLASSES["Maugetar_HasNotMoved"]`. Sans cette entree, `EffectFactory` retombe
    SILENCIEUSEMENT sur `BaseEffect` (`registry.get(name, BaseEffect)`) : l'effet existe, il
    n'agit pas. C'est le mode de panne exact que le canal #179 ne signale jamais."""
    st = _fresh(env)
    inst = _insts(st, _unit(st, MAUGAN_RA), MAUGETAR_HAS_NOT_MOVED)[0]
    assert isinstance(inst, MaugetarHasNotMovedEffect), \
        "1497 materialise en %s -- entree EFFECT_CLASSES manquante" % type(inst).__name__


# ----------------------------------------------------------- Maugetar : le gate AttackDamageIsCritical
def test_groupe_additionnel_seulement_si_l_attaque_a_crite(env):
    """`get_OwnerIsCaster & AttackDamageIsCritical`. Les TROIS regimes du gate, dont le tri-etat :
    une cle ABSENTE est << non mesuree >> et ne fabrique AUCUN groupe."""
    st = _fresh(env)
    inst = _insts(st, (mr := _unit(st, MAUGAN_RA)), MAUGETAR_HAS_NOT_MOVED)[0]
    assert inst.additional_hit_groups(_ctx(st, mr, attack_had_critical=False)) is None, \
        "groupe rendu sur une attaque SANS crit"
    assert inst.additional_hit_groups(_ctx(st, mr)) is None, \
        "groupe rendu alors que le crit n'est pas MESURE (cle absente)"
    grp = inst.additional_hit_groups(_ctx(st, mr, attack_had_critical=True))
    assert grp and len(grp) == 1, "aucun groupe sur une attaque AVEC crit : %r" % (grp,)


def test_le_porteur_doit_etre_l_attaquant(env):
    """`get_OwnerIsCaster` : le descripteur ne rend rien quand le ctx PROUVE que le porteur n'est
    pas l'attaquant du coup (identite non prouvee != identite fausse)."""
    st = _fresh(env)
    mr, ae = _unit(st, MAUGAN_RA), _unit(st, AETHANA)
    inst = _insts(st, mr, MAUGETAR_HAS_NOT_MOVED)[0]
    ctx = _ctx(st, mr, attack_had_critical=True)
    ctx["att_id"] = ae                      # l'attaquant est un AUTRE que le porteur
    assert inst.additional_hit_groups(ctx) is None, "groupe rendu pour l'attaque d'un TIERS"


def test_bornes_et_compte_du_groupe(env):
    """Les quatre champs du descripteur : `count` = `ConfigConst(nrOfHits)`, `min`/`max` = noeud
    ROLL, `amount` = noeud DISPLAY (`Average` ARRONDI, pas un `.5`), `profile` = la config."""
    st = _fresh(env)
    inst = _insts(st, (mr := _unit(st, MAUGAN_RA)), MAUGETAR_HAS_NOT_MOVED)[0]
    g = inst.additional_hit_groups(_ctx(st, mr, attack_had_critical=True))[0]
    mn = int(ability_var("Maugetar", "minDmg", RELIC_LEVEL))
    mx = int(ability_var("Maugetar", "maxDmg", RELIC_LEVEL))
    assert (g["min"], g["max"]) == (mn, mx), "bornes ROLL != gameconfig au niveau de RELIQUE"
    assert g["count"] == int(ability_var("Maugetar", "nrOfHits", is_constant=True))
    assert g["profile"] == "DirectDamage"
    assert g["amount"] == (mn + mx) // 2 if (mn + mx) % 2 == 0 else g["amount"] in (
        (mn + mx) // 2, (mn + mx) // 2 + 1), "canal DISPLAY : Average non ARRONDI"


def test_le_niveau_de_relique_mord_regime_separant(env):
    """LE BUG QUE CE PORT EVITE. L'instance d'effet publie `ability_level = 50` (l'etat PASSIF) quel
    que soit le niveau de la relique -- MESURE sur deux runners (`:1` et `:10`). Lire l'instance
    clampe donc au DERNIER palier. Le descripteur doit servir le palier de la RELIQUE.

    Le montage est a `RELIC_LEVEL = 1` precisement pour que les deux modeles DIVERGENT."""
    st = _fresh(env)
    inst = _insts(st, (mr := _unit(st, MAUGAN_RA)), MAUGETAR_HAS_NOT_MOVED)[0]
    lvl_t, _ = triggered_ability_state(st, mr, "Maugetar")
    assert lvl_t == RELIC_LEVEL, "etat TERTIAIRE non seede (canal unitAbilityStates) : %r" % lvl_t
    assert int(getattr(inst, "ability_level", 0) or 0) != RELIC_LEVEL, \
        "l'instance porte deja le niveau de relique -- le regime n'est plus SEPARANT"
    g = inst.additional_hit_groups(_ctx(st, mr, attack_had_critical=True))[0]
    assert g["min"] == int(ability_var("Maugetar", "minDmg", RELIC_LEVEL))
    # CONTRE-EPREUVE : sans le callable, le descripteur retombe sur l'instance -> dernier palier.
    ctx = _ctx(st, mr, attack_had_critical=True)
    ctx.pop("tertiary_ability_state_of")
    faux = inst.additional_hit_groups(ctx)[0]
    assert faux["min"] > g["min"], \
        "le repli sur l'instance ne diverge pas -- la garde ne mesure rien"


# ------------------------------------------------------- Maugetar : retrait au PreUnitMove
def test_retrait_de_l_effet_quand_le_porteur_amorce_un_deplacement(env):
    """`CreateRemoveEffectTrigger` = `On(0x1f = PreUnitMove) & get_OwnerIsActor`."""
    st = _fresh(env)
    mr = _unit(st, MAUGAN_RA)
    assert _insts(st, mr, MAUGETAR_HAS_NOT_MOVED), "pre-condition : effet absent"
    pre_move_triggers(st, mr)
    assert not _insts(st, mr, MAUGETAR_HAS_NOT_MOVED), \
        "l'effet 1497 survit au deplacement du porteur"


def test_le_deplacement_d_un_tiers_ne_retire_rien(env):
    """`get_OwnerIsActor` : c'est le MOVER qui perd son marqueur, pas un spectateur."""
    st = _fresh(env)
    mr, ae = _unit(st, MAUGAN_RA), _unit(st, AETHANA)
    pre_move_triggers(st, ae)
    assert _insts(st, mr, MAUGETAR_HAS_NOT_MOVED), \
        "l'effet 1497 retire par le deplacement d'une AUTRE unite"


# --------------------------------------------------- Maugetar : ResetMovement au UnitPostAbility
def test_reset_movement_rouvre_le_deplacement_du_porteur(env):
    """`On(0xe = UnitPostAbility) & get_OwnerIsCaster` -> `If(HasEffect(Owner, 1497),
    ResetMovement(Owner))`. `ResetMovementBehavior$$Execute` retire `Moved`,
    `ArrivedAtFinalTile`, `TurnTerminated` et `TurnFinished` -- mais PAS `ActiveAbilityUsed`."""
    st = _fresh(env)
    mr = _unit(st, MAUGAN_RA)
    fl = st.get_entity(mr).get_component(UnitFlagsComponent)
    if fl is None:
        fl = UnitFlagsComponent()
        st.get_entity(mr).add_component(fl)
    for f in (UnitFlagsComponent.MOVED, UnitFlagsComponent.ARRIVED_AT_FINAL_TILE,
              UnitFlagsComponent.TURN_FINISHED, UnitFlagsComponent.ACTIVE_ABILITY_USED):
        fl.add(f)
    unit_post_ability_triggers(st, mr, mr, ranged=True)
    assert not fl.has(UnitFlagsComponent.MOVED), "`Moved` non retire"
    assert not fl.has(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE), "`ArrivedAtFinalTile` non retire"
    assert not fl.has(UnitFlagsComponent.TURN_FINISHED), "`TurnFinished` non retire"
    assert fl.has(UnitFlagsComponent.ACTIVE_ABILITY_USED), \
        "`ActiveAbilityUsed` retire -- ce serait `RemoveTurnFlags`, pas `ResetMovementBehavior`"


def test_pas_de_reset_movement_sans_l_effet(env):
    """La branche `else` NULLE du `If` natif : le porteur qui a DEJA bouge (donc plus de 1497) ne
    recupere rien. C'est ce qui empeche la boucle attaquer/bouger/attaquer indefiniment."""
    st = _fresh(env)
    mr = _unit(st, MAUGAN_RA)
    pre_move_triggers(st, mr)                     # consomme l'effet
    fl = st.get_entity(mr).get_component(UnitFlagsComponent)
    if fl is None:
        fl = UnitFlagsComponent()
        st.get_entity(mr).add_component(fl)
    fl.add(UnitFlagsComponent.MOVED)
    unit_post_ability_triggers(st, mr, mr, ranged=True)
    assert fl.has(UnitFlagsComponent.MOVED), \
        "`ResetMovement` joue sans l'effet 1497 -- le gate `HasEffect` de l'arbre ne mord pas"


def test_l_ability_d_un_tiers_ne_rouvre_pas_le_porteur(env):
    """`get_OwnerIsCaster` : le vecteur `UnitPostAbility` est emis pour CHAQUE ability de la
    bataille ; seul le caster-porteur declenche le reset."""
    st = _fresh(env)
    mr, ae = _unit(st, MAUGAN_RA), _unit(st, AETHANA)
    fl = st.get_entity(mr).get_component(UnitFlagsComponent)
    if fl is None:
        fl = UnitFlagsComponent()
        st.get_entity(mr).add_component(fl)
    fl.add(UnitFlagsComponent.MOVED)
    unit_post_ability_triggers(st, ae, ae, ranged=True)
    assert fl.has(UnitFlagsComponent.MOVED), "le reset a joue pour l'ability d'un TIERS"


# ------------------------------------------------- Maugetar : re-pose au debut du tour du porteur
def test_repose_au_turn_start_du_proprietaire(env):
    """`On(0x12 = TurnStart_EffectActivation) & IsTurnOf(Owner)` -> `AddEffect(1497, ..., turns =
    null)`. Sans ce vecteur, un porteur ayant bouge au tour N n'aurait plus JAMAIS son bonus."""
    st = _fresh(env)
    mr = _unit(st, MAUGAN_RA)
    oc = st.get_entity(mr).get_component(OwnerComponent)
    st.current_player_id = oc.player
    pre_move_triggers(st, mr)                     # l'effet tombe
    assert not _insts(st, mr, MAUGETAR_HAS_NOT_MOVED), "pre-condition : effet encore la"
    tile_tick_triggers(st)
    assert _insts(st, mr, MAUGETAR_HAS_NOT_MOVED), \
        "l'effet 1497 n'est pas re-pose au debut du tour de son proprietaire"


def test_pas_de_repose_au_tour_de_l_adversaire(env):
    """`IsTurnOf(Owner)` : le marqueur ne revient PAS pendant le tour d'en face (c'est ce qui rend
    l'i2 << if he has not moved in his LAST TURN >> exact pour l'overwatch)."""
    st = _fresh(env)
    mr = _unit(st, MAUGAN_RA)
    oc = st.get_entity(mr).get_component(OwnerComponent)
    autres = {e.get_component(OwnerComponent).player for e in st.entities.values()
              if e.get_component(OwnerComponent) is not None} - {oc.player}
    if not autres:
        pytest.skip("un seul joueur sur ce runner")
    st.current_player_id = sorted(autres)[0]
    pre_move_triggers(st, mr)
    tile_tick_triggers(st)
    assert not _insts(st, mr, MAUGETAR_HAS_NOT_MOVED), \
        "l'effet 1497 revient au tour de l'ADVERSAIRE"


# ----------------------------------------------------------------------- PhoenixGem : la MAGNITUDE
def test_phoenix_gem_revive_au_niveau_de_la_relique(env):
    """`GetVariableForLevel(0x1d = hp, abilityState)` : l'`AbilityState` est celui du RELIC.
    L'ancienne lecture (l'instance, `ability_level = 50`) rendait TOUJOURS `hp[10]` = 5817 ;
    au niveau 1 le natif sert 3915. Regime SEPARANT, comme pour Maugetar."""
    st = _fresh(env)
    ae, mr = _unit(st, AETHANA), _unit(st, MAUGAN_RA)
    lvl_t, mult = triggered_ability_state(st, ae, "PhoenixGem")
    assert lvl_t == RELIC_LEVEL, "etat TERTIAIRE non seede : %r" % lvl_t
    attendu = int(ability_var("PhoenixGem", "hp", lvl_t, multiplier_pct=mult or 100))
    dernier = int(ability_var("PhoenixGem", "hp", 50))
    assert attendu != dernier, "regime NON separant -- la garde ne mesurerait rien"
    hc = st.get_entity(ae).get_component(HealthComponent)
    maxhp = int(hc.hp_max)
    hc.hp = 0
    st.get_entity(ae).get_component(UnitComponent).alive = False
    after_death_triggers(st, dying_id=ae, killer_id=mr, overkill=True)
    kill_unit_revive_gate(st, ae)
    assert st.get_entity(ae).get_component(UnitComponent).alive, \
        "PhoenixGem n'a pas revive en overkill (`OnPreDeath(ignoreOverkill)`)"
    assert int(hc.hp) == min(attendu, maxhp), \
        "PV rendus = %d, attendu min(hp[%d], maxPV) = %d" % (int(hc.hp), lvl_t,
                                                             min(attendu, maxhp))


def test_phoenix_gem_une_seule_fois_par_bataille(env):
    """Les DEUX triggers de retrait du marqueur (`On(UnitRevived) & CurrentAbilityIs(PhoenixGem)`,
    `On(UnitResurrected)`) realisent le << the FIRST TIME each battle >>."""
    st = _fresh(env)
    ae, mr = _unit(st, AETHANA), _unit(st, MAUGAN_RA)
    hc = st.get_entity(ae).get_component(HealthComponent)
    for tour in (1, 2):
        hc.hp = 0
        st.get_entity(ae).get_component(UnitComponent).alive = False
        after_death_triggers(st, dying_id=ae, killer_id=mr)
        kill_unit_revive_gate(st, ae)
        vivant = st.get_entity(ae).get_component(UnitComponent).alive
        if tour == 1:
            assert vivant, "revive #1 attendu"
        else:
            assert not vivant, "revive #2 joue -- le marqueur 1451 n'a pas ete consomme"


# ------------------------------------------------------------------------------ anti-regression
def test_aucune_autre_unite_ne_porte_les_marqueurs(env):
    """Garde de NON-CONTAMINATION : les deux effets de relique vivent sur LEUR porteur et nulle
    part ailleurs. Un `AddEffect` mal cible (selecteur `Owner` confondu avec `Caster`) se verrait
    ici, et nulle part dans les gardes de magnitude."""
    st = _fresh(env)
    mr, ae = _unit(st, MAUGAN_RA), _unit(st, AETHANA)
    for uid in st.entities:
        if _insts(st, uid, MAUGETAR_HAS_NOT_MOVED):
            assert int(uid) == mr, "1497 porte par u%s, qui n'est pas Maugan Ra" % uid
        if _insts(st, uid, PHOENIX_GEM_CAN_REVIVE):
            assert int(uid) == ae, "1451 porte par u%s, qui n'est pas Aethana" % uid


def test_un_effet_nu_du_meme_type_ne_rend_aucun_groupe(env):
    """CONTRE-EPREUVE de la garde `EFFECT_CLASSES` : un `BaseEffect` NU portant le meme
    `effect_type` ne rend rien. C'est ce que faisait le port AVANT #1006 -- la garde
    `test_effet_1497_se_materialise_en_classe_portee` mesure donc bien un ecart REEL."""
    st = _fresh(env)
    mr = _unit(st, MAUGAN_RA)
    nu = BaseEffect(name=EffectType.Maugetar_HasNotMoved.name,
                    effect_type=MAUGETAR_HAS_NOT_MOVED, ability_level=RELIC_LEVEL,
                    ability_variables_multiplier=100, source=mr, target=mr)
    assert nu.additional_hit_groups(_ctx(st, mr, attack_had_critical=True)) is None
