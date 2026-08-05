"""#462-r4b-r1-r1-r1-r1-c-r3 -- la face EFFET n'a AUCUN gate d'owner : les DEUX surplus leves.

`-c-r1` avait deja LU que la face EFFET du natif ne gate rien
(`IdunBattle.Operations.EvaluateTriggerOperation$$CanGetEffectTrigger` et la branche EFFET
d'`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityOrEffectTrigger` commencent par un
corps DEDUPLIQUE `mov al,1 ; ret` -- `b0 01 c3`, 772 proprietaires ; le nom ghidra
`UnityEngine.U2D.IK.Solver2D$$DoValidate` est celui d'un proprietaire ARBITRAIRE), mais n'en avait
tire que le cas TUILE. Le port gardait donc DEUX gates que le natif n'a pas :

  1. porteur INTROUVABLE (`state.get_entity` rend None et l'id n'est pas une tuile) ;
  2. porteur MORT (`UnitComponent.alive` faux, sauf echappatoire `fire_on_death`).

Les deux sont leves. Ce fichier garde la levee, gate par gate, ET mesure ce qu'elle change.

CE QU'ELLE CHANGE, MESURE (aucun de ces chiffres n'est herite) :

  * FENETRE de la sequence de mort -- le mourant est `alive=False` avec ses effets NON CONSOMMES
    sur EXACTEMENT TROIS evenements : `On(3 = PendingDeathAdded)`, `On(1 = PreUnitDeath)`,
    `On(2 = PreUnitDeath_2)`. Des `On(0 = UnitDeath)`, le premier `RemoveEffects(PreUnitRemove)` a
    tourne et il n'y a plus rien a collecter. C'est la seule fenetre ou le gate `alive` mordait.
  * AUCUN PORTEUR NATUREL n'y perdait quoi que ce soit : sur les 54 classes NUES du registre, les
    seules qui ecoutent un evenement de cette fenetre ont pour owner le TUEUR
    (`EarlyWarningOverrideReactivateOverwatch`), le REVIVEUR (`ReanimationBeamReviveTrigger`) ou le
    porteur du bond (`BondRemoveOnBondedEntityDeath`) -- toutes VIVANTES. Les DEUX classes dont
    l'owner EST le mourant (`PhoenixGemReviveAbility`, `RitesOfMorkaiReviveTrigger`) declaraient
    `fire_on_death`, l'echappatoire ad hoc qui compensait exactement ce surplus. La levee la rend
    INERTE sur la face EFFET -- et c'est ce que le bras qui MORD exerce.
  * porteur INTROUVABLE : mesure live (bras dedie ci-dessous) -- toute cle de
    `EffectsState.by_unit` est soit une entite, soit une tuile. Le regime est VIDE aujourd'hui.

⚠ CE QUI RESTE OUVERT, et le dire fait partie du livrable : `_kill_steppable_units`
(`operations/movement.py`) pose `alive=False` + `hp=0` SANS retirer les effets, alors que le natif
passe par `IdunBattle.Operations.KillUnitOperation$$Execute` avec
`IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable` -- dont AUCUN des quatre tests sur
`options` ne se trouve sur le chemin des TROIS `RemoveEffects` (lu : `+0x00`, `+0x44`, `+0x45`,
`+0x46` gatent `IsSteppable`, `RecordDeathReason`, le flag overkill et une emission analytics, rien
d'autre). Un `Steppable` ecrase est donc, cote port et lui SEUL, un porteur MORT a effets intacts --
DE FACON PERSISTANTE. Residu `#462-r4b-r1-r1-r1-r1-c-r3-r1` ; le bras
`test_aucun_porteur_steppable_ne_porte_un_effect_type_du_registre` garde son caractere VIDE.

ASCII only.
"""
from __future__ import annotations

import pytest

from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.effects import EffectFactory
from engine.entities.effects.base import BaseEffect
from engine.entities.effects_state import EffectsState
from engine.entities.pathfinding.board import Board
from engine.runner.components import HealthComponent, UnitComponent
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.revive import kill_unit_revive_gate
from engine.runner.operations.triggers import after_death_triggers
from engine.runner.operations.triggers.base import (EffectTrigger, TileEffectTrigger,
                                                    TriggerEvent, TriggeredAbility)
from engine.runner.operations.triggers.dispatch import core as CORE
from engine.runner.operations.triggers.dispatch import registry as REG
from engine.runner.operations.triggers.loki.rites_of_morkai import (RITES_OF_MORKAI_EFFECT,
                                                                    RitesOfMorkaiReviveTrigger)
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state
from engine.runner.state import State

# Board et roster DIFFERENTS de ceux de `-c-r1` (`MC1_67`, roster par defaut) : la levee ne doit
# dependre d'aucune particularite de l'etat qui a servi a la tranche precedente.
# `--hp-target 1` : le bras de GISEMENT a besoin d'unites REELLEMENT MORTES dans un etat CHARGE.
# C'est l'IA adverse qui joue (`aiPlayByUnit`) et ses unites meurent en s'approchant (overwatch /
# reactions) -- mesure du 2026-08-05 : 2 morts en 2 tours, bataille encore `Running`. `--hp-player`,
# lui, ne produit RIEN ici : l'IA marche sans atteindre mon camp (mesure : 0 mort en 12 tours).
# TROIS de chaque cote pour qu'il en reste apres les premieres morts -- sinon la bataille passe
# `Finished` et `decisionView` ne rend plus AUCUNE unite a mesurer.
BUILD = ["--p-units", "ultraTitus,bloodIntercessor,eldarFarseer",
         "--a-units", "worldKharn,orksNob,orksWarboss",
         "--rank", "17", "--board", "C3_01", "--hp-target", "1"]

POSER_LEVEL = 50          # niveau de l'ACTIVE RitesOfMorkai du poseur, transporte par l'effet
POSER_MULT = 180

_EVENTS_MORT = (int(EventTriggerType.PendingDeathAdded), int(EventTriggerType.PreUnitDeath),
                int(EventTriggerType.PreUnitDeath_2), int(EventTriggerType.UnitDeath),
                int(EventTriggerType.UnitDefeated))


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


@pytest.fixture(scope="module")
def env_live(live_session, rpc, build_runner):
    """Un BOARD et des UNITES reels. Portee MODULE : un seul runner pour tout le fichier."""
    built = build_runner("31337", extra=BUILD)
    rid = built["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indisponible -- montage non installe"
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    assert _ok(dv) and _ok(ob) and _ok(snap), "capture live KO -- montage non installe"
    st0 = load_state(dv, ob, snap, board=board, tiles=tm)
    assert getattr(st0, "effects", None) is not None, "pas d'EffectsState (combatSnapshot partiel)"
    return {"rid": rid, "my_team": built.get("my_team", 1), "dv": dv, "ob": ob, "snap": snap,
            "board": board, "tiles": tm}


def _fresh(env, seed: int = 777) -> State:
    st = load_state(env["dv"], env["ob"], env["snap"], board=env["board"], tiles=env["tiles"])
    st.rng = IntBasedMersenneTwister(seed)
    return st


def _deux_allies(state: State):
    from engine.runner.components import OwnerComponent
    teams: dict = {}
    for uid, e in state.entities.items():
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        if oc is not None and uc is not None and uc.alive:
            teams.setdefault(oc.team, []).append(int(uid))
    t = sorted(teams)[0]
    assert len(teams[t]) >= 2, "moins de deux allies vivants -- montage non installe"
    return teams[t][0], teams[t][1]


def _inspire(st: State, uid: int):
    """Pose l'effet 1502 << Inspired >> sur `uid` -- meme append que le natif
    (`IdunBattle.Operations.AddEffectOperation$$AddNewEffect`), et meme voie que
    `test_rites_of_morkai_revive_live.py`, dont c'est le montage EPROUVE : le porteur reel
    (`spaceWolfPriest`) est hors du roster ici, et ce qui est sous test est le GATE, pas la pose."""
    e = BaseEffect(name="RitesOfMorkai", effect_type=RITES_OF_MORKAI_EFFECT,
                   active_ability_level=POSER_LEVEL, ability_level=POSER_LEVEL,
                   ability_variables_multiplier=POSER_MULT, source=uid, target=uid)
    st.effects.by_unit.setdefault(int(uid), []).append(e)
    return e


def _tue(st: State, uid: int, killer: int):
    """`On(1 = PreUnitDeath)` PUIS la garde revive @`KillUnitOperation$$Execute+0x82e`."""
    st.get_entity(uid).get_component(HealthComponent).hp = 0
    st.get_entity(uid).get_component(UnitComponent).alive = False
    out = after_death_triggers(st, dying_id=uid, killer_id=killer, overkill=False)
    kill_unit_revive_gate(st, uid)
    return out


# ───────────────────────── GATE 2 (porteur MORT) : le bras qui MORD, porteur REEL

def test_le_self_revive_survit_a_la_perte_de_fire_on_death_live(env_live, monkeypatch):
    """LE BRAS QUI MORD pour le gate `alive`, sur un porteur REEL et un observable REEL.

    `RitesOfMorkaiReviveTrigger` (effet 1502) est le cas d'ecole : c'est un `EffectTrigger` dont
    l'owner EST le mourant (`get_OwnerIsTarget`), donc la seule famille que le gate `alive` pouvait
    jeter. Il declare `fire_on_death = True` -- l'echappatoire ad hoc qui compensait le surplus.

    Trois mesures sur le MEME etat live (board `C3_01`, roster reel) :

      A. `fire_on_death` intact                    -> revive        (controle positif)
      B. attribut RETIRE de la classe              -> revive        (la face EFFET ne gate plus)
      C. B + `_owner_gate_applies` force a `True`  -> AUCUN revive  (attribution)

    B est l'invariant : AVANT `-c-r3` il rendait << pas de revive >>, parce que le porteur est
    `alive=False` au moment ou `On(1)` part. C attribue le passage de B a la discrimination de FACE
    et a elle seule -- forcer la face ABILITY remet le `UnitExtensions$$IsAlive` de
    `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` et le revive retombe.

    ⚠ Retirer `fire_on_death` est un MONTAGE, pas un porteur naturel, et le dire fait partie de la
    mesure : les DEUX classes de la face EFFET dont l'owner est le mourant le declarent (l'autre est
    `PhoenixGemReviveAbility`), justement parce que quelqu'un avait bute sur ce gate. La levee ne
    change donc aucun observable AUJOURD'HUI -- elle retire une bequille et rend le mirror exact."""
    def revive(sans_fod: bool, forcer_le_gate: bool) -> bool:
        st = _fresh(env_live)
        uid, autre = _deux_allies(st)
        _inspire(st, uid)
        sauf_fod = RitesOfMorkaiReviveTrigger.fire_on_death
        sauf_gate = CORE._owner_gate_applies
        try:
            if sans_fod:
                RitesOfMorkaiReviveTrigger.fire_on_death = False
            if forcer_le_gate:
                CORE._owner_gate_applies = lambda entry: True
            _tue(st, uid, autre)
        finally:
            RitesOfMorkaiReviveTrigger.fire_on_death = sauf_fod
            CORE._owner_gate_applies = sauf_gate
        return bool(st.get_entity(uid).get_component(UnitComponent).alive)

    assert revive(False, False), \
        "A : le montage ne revive MEME PAS avec fire_on_death -- la suite ne prouverait rien"
    assert revive(True, False), (
        "B : prive de son `fire_on_death`, le self-revive d'un porteur MORT est jete -- le gate "
        "`alive` mord encore sur la face EFFET (#462-r4b-r1-r1-r1-r1-c-r3)")
    assert not revive(True, True), (
        "C : le revive passe encore alors que la face ABILITY est forcee -- le passage de B n'est "
        "PAS attribuable a la discrimination de face")


def test_la_fenetre_de_mort_rend_ses_trois_evenements_a_la_face_effet(env_live):
    """LA FENETRE, mesuree sur le VRAI pipeline de mort du port (`_fire_death_if_killed` ->
    `IdunBattle.Operations.KillUnitOperation$$Execute`), avec une unite REELLE de l'etat live.

    Une sonde NUE (aucun `fire_on_death`, aucun `owner_is_tile`) est inscrite sur les CINQ
    evenements de mort et note chaque passage de `matches`. Ce qu'elle voit :

      * `On(3)`, `On(1)`, `On(2)` : le mourant est `alive=False` et son effet est encore la (les
        `RemoveEffects` natifs sont APRES `On(2)`) -> la face EFFET les evalue DESORMAIS ;
      * `On(0)`, `On(54)` : `RemoveEffects(PreUnitRemove)` a tourne, `collect_effect_triggers`
        skippe l'effet consomme -> rien, et ce n'est PAS le gate qui l'ecarte.

    La contre-epreuve force la face ABILITY : les trois passages disparaissent."""
    def passages(forcer_le_gate: bool) -> list:
        st = _fresh(env_live)
        uid, autre = _deux_allies(st)
        et = _effect_type_hors_registre()
        st.effects.by_unit.setdefault(int(uid), []).append(EffectFactory.create(
            {"name": "SondeEffect", "effectType": int(et), "remaining": 0}, 100, None, None))
        _Sonde.vus = []
        _Sonde.event_ids = _EVENTS_MORT
        _Sonde.event_id = _EVENTS_MORT[0]
        sauf_gate = CORE._owner_gate_applies
        REG.EFFECT_TRIGGERS[et] = [_Sonde]
        try:
            if forcer_le_gate:
                CORE._owner_gate_applies = lambda entry: True
            ent = st.get_entity(uid)
            hc = ent.get_component(HealthComponent)
            avant = int(hc.hp or 0)
            hc.hp = 0
            AttackDamageOperation._fire_death_if_killed(st, uid, autre, avant, 0, ent,
                                                        damage=avant)
        finally:
            CORE._owner_gate_applies = sauf_gate
            REG.EFFECT_TRIGGERS.pop(et, None)
        return [(e, a) for e, _o, a in _Sonde.vus]

    vus = passages(False)
    events = [e for e, _a in vus]
    assert events == [int(EventTriggerType.PendingDeathAdded),
                      int(EventTriggerType.PreUnitDeath),
                      int(EventTriggerType.PreUnitDeath_2)], (
        "la fenetre mesuree n'est pas On(3)/On(1)/On(2) : %s -- soit le gate mord encore, soit "
        "l'ordre de la sequence de mort a change" % events)
    assert all(a is False for _e, a in vus), \
        "le porteur n'etait pas `alive=False` sur toute la fenetre : %s" % vus
    assert not passages(True), (
        "la fenetre reste ouverte alors que la face ABILITY est forcee -- les trois passages ne "
        "sont pas attribuables a la levee du gate `alive` sur la face EFFET")


# ───────────────────────── GATE 1 (porteur INTROUVABLE)

class _Sonde(EffectTrigger):
    """Effet-trigger NU (surtout PAS `TileEffectTrigger`, surtout PAS `fire_on_death`) qui note
    `(event, owner, alive)` a chaque passage de `matches` et ne mute rien.

    C'est le capteur du gate : ecarte avant `matches`, il ne note rien."""
    event_id = -1
    event_ids: tuple = ()
    vus: list = []

    def matches(self, state, ev) -> bool:
        e = state.get_entity(int(self.owner_id))
        uc = e.get_component(UnitComponent) if e is not None else None
        _Sonde.vus.append((int(ev.event_id), int(self.owner_id),
                           None if uc is None else bool(uc.alive)))
        return False

    def execute_behaviour(self, state, ev):
        return None


def _effect_type_hors_registre() -> int:
    """Un `effect_type` ABSENT du registre : la sonde s'y inscrit sans ecraser d'entree reelle."""
    et = 990001
    while et in REG.EFFECT_TRIGGERS:
        et += 1
    return et


def test_un_porteur_introuvable_atteint_matches_sur_la_face_effet():
    """LE MECANISME du gate 1. Un id qui n'est NI une entite NI une tuile doit atteindre `matches`.

    Mirror direct : `CanGetEffectTrigger(this, owner, effect, onlyNonAtomic)` a pour PREMIERE
    instruction un appel dont le corps est `mov al,1 ; ret` -- l'argument `owner` n'est meme pas
    lu. Et la branche EFFET d'`EvaluateAbilityOrEffectTrigger` pose ensuite ce `owner` TEL QUEL dans
    l'`AbilityEntities` via `$$EvaluateEffectTriggerEffectAbilities`, `null` compris.

    Contre-epreuve dans le meme test : force la face ABILITY -> l'entree est jetee. C'est ce qui
    borne la levee a une face au lieu d'un gate supprime partout."""
    def passages(forcer_le_gate: bool) -> list:
        st = State()
        st.effects = EffectsState()
        et = _effect_type_hors_registre()
        orphelin = 987654                    # ni dans `state.entities`, ni dans un board (il n'y en a pas)
        st.effects.add_effect(orphelin, EffectFactory.create(
            {"name": "SondeEffect", "effectType": int(et), "remaining": 0}, 100, None, None))
        _Sonde.vus = []
        _Sonde.event_ids = ()
        _Sonde.event_id = 2
        sauf_gate = CORE._owner_gate_applies
        REG.EFFECT_TRIGGERS[et] = [_Sonde]
        try:
            if forcer_le_gate:
                CORE._owner_gate_applies = lambda entry: True
            CORE.evaluate_trigger_operation(
                st, TriggerEvent(2, orphelin, orphelin, ranged=False, profile=None))
        finally:
            CORE._owner_gate_applies = sauf_gate
            REG.EFFECT_TRIGGERS.pop(et, None)
        return list(_Sonde.vus)

    assert passages(False), (
        "un porteur introuvable est encore JETE sur la face EFFET -- `CanGetEffectTrigger` ne gate "
        "RIEN (#462-r4b-r1-r1-r1-r1-c-r3)")
    assert not passages(True), (
        "il passe AUSSI quand la face ABILITY est forcee -- le gate a ete supprime partout, pas "
        "borne a la face EFFET")


# ───────────────────────── PORTEE : la face ABILITY, elle, gate TOUJOURS

class _SondeAbility(TriggeredAbility):
    """Ability-trigger NU inscrit par la voie REELLE du registre (`TRAIT_TRIGGERS` -> un trait porte
    par une unite). Il note son passage et ne mute rien."""
    event_id = 2
    fire_on_death = False
    vus: list = []

    def matches(self, state, ev) -> bool:
        _SondeAbility.vus.append(int(self.owner_id))
        return False

    def execute_behaviour(self, state, ev):
        return None


_TRAIT_SONDE = "_SondeTrait462cr3"


def test_le_gate_alive_de_la_face_ABILITY_mord_toujours(env_live):
    """CONTRE-EPREUVE STRUCTURELLE, et elle existe parce qu'une premiere passe de mutants l'a
    trouvee MANQUANTE : neutraliser le gate PARTOUT (`_owner_gate_applies` -> `False`) laissait
    **14 verts sur 14**. Les bras d'attribution des autres tests SUBSTITUENT ce predicat, donc ils
    sont par construction aveugles a sa disparition -- c'est le piege << vacuously vrai >> par une
    autre porte.

    Ce bras-ci n'y touche pas. Il inscrit un ability-trigger par la voie REELLE (`TRAIT_TRIGGERS`,
    un trait pose sur une unite du live) et lit les trois regimes de
    `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` :

        if (!IsAtomic(ability)) { if (IsUnit(owner) && !IsAlive(owner)) return 0; }

      * porteur VIVANT                      -> evalue   (controle positif)
      * porteur MORT                        -> JETE     (`UnitExtensions$$IsAlive`)
      * porteur MORT + `fire_on_death`      -> evalue   (mirror d'`IsAtomic(ability)`)"""
    from engine.runner.components import StatsComponent

    def passages(vivant: bool, atomique: bool) -> list:
        st = _fresh(env_live)
        uid, _autre = _deux_allies(st)
        ent = st.get_entity(uid)
        sc = ent.get_component(StatsComponent)
        assert sc is not None, "l'unite du live n'a pas de StatsComponent -- montage non installe"
        sc.ctx.traits = list(sc.ctx.traits or []) + [_TRAIT_SONDE]
        ent.get_component(UnitComponent).alive = bool(vivant)
        _SondeAbility.vus = []
        _SondeAbility.fire_on_death = bool(atomique)
        REG.TRAIT_TRIGGERS[_TRAIT_SONDE] = [_SondeAbility]      # dict MUTE in-place, jamais rebinde
        try:
            CORE.evaluate_trigger_operation(
                st, TriggerEvent(2, uid, uid, ranged=False, profile=None))
        finally:
            REG.TRAIT_TRIGGERS.pop(_TRAIT_SONDE, None)
            _SondeAbility.fire_on_death = False
        return list(_SondeAbility.vus)

    assert passages(True, False), \
        "l'ability-trigger d'un porteur VIVANT n'est pas evalue -- le montage ne prouve rien"
    assert not passages(False, False), (
        "l'ability-trigger d'un porteur MORT passe : le gate `IsAlive` de `CanGetAbilityTrigger` a "
        "disparu -- la levee #462-r4b-r1-r1-r1-r1-c-r3 a deborde sur la face ABILITY")
    assert passages(False, True), (
        "`fire_on_death` ne dispense plus du gate `alive` : le mirror d'`IsAtomic(ability)` est "
        "casse sur la face ABILITY")


# ───────────────────────── ce que la levee change AUJOURD'HUI : trois mesures de GISEMENT

def test_aucune_cle_de_by_unit_n_est_introuvable_en_live(env_live):
    """GISEMENT du gate 1, mesure live : toute cle de `EffectsState.by_unit` est soit une ENTITE
    soit une TUILE. Le regime << porteur introuvable >> est donc VIDE aujourd'hui, et la levee n'a
    aucun porteur naturel -- c'est le seul enonce honnete a rendre.

    Ce bras ne garde pas le correctif : il garde cet ENONCE. Il rougira le jour ou une cle
    orpheline apparaitra, et c'est alors la levee qui deviendra observable."""
    st = _fresh(env_live)
    cles = [int(k) for k, lst in st.effects.by_unit.items() if any(not e.consumed for e in lst)]
    assert cles, "aucun effet non consomme dans l'etat live -- la mesure serait vide"
    tuiles = set(st.board.by_id) if st.board is not None else set()
    orphelines = [k for k in cles if st.get_entity(k) is None and k not in tuiles]
    print("\n[gisement] %d cle(s) de by_unit portant un effet ; orphelines=%s"
          % (len(cles), orphelines))
    assert not orphelines, (
        "des cles de by_unit ne designent ni une entite ni une tuile : %s -- le regime du gate 1 "
        "n'est plus vide, ces porteurs doivent etre confrontes" % orphelines[:10])


def test_aucune_unite_morte_ne_porte_d_effet_non_consomme_en_live(env_live, rpc):
    """GISEMENT du gate 2 dans un etat CHARGE : une unite morte n'y porte aucun effet non consomme.

    C'est ce qui ecarte le risque symetrique de la levee -- si le canal live ramenait des effets sur
    des morts la ou le natif les a retires (`KillUnitOperation$$RemoveEffects`), lever le gate
    ferait firer des triggers FANTOMES. Mesure : le canal est fidele.

    NON VACUITE : le bras exige des unites MORTES ET des effets dans l'etat ; sans elles il rougit
    au lieu de passer pour rien."""
    rid, my_team = env_live["rid"], env_live["my_team"]
    ennemi = 4 if my_team == 1 else 3
    # Faire MOURIR du monde : rendre la main a l'adversaire puis jouer UN tour d'IA, repete. C'est la
    # voie de `rl_duel aiturn` (`aiPlayByUnit` == `CheatRunAIMessage`), GARDE-FOU COMPRIS : un seul
    # `endturn` ne flippe pas toujours `currentPlayer` (quirk H19), et jouer l'IA sans le flip la
    # ferait jouer MA team. On s'ARRETE des la premiere mort : aller plus loin termine la bataille,
    # et `decisionView` d'une bataille `Finished` ne rend plus AUCUNE unite (mesure du 2026-08-05) --
    # le bras deviendrait vide au lieu de mesurer.
    def _cp():
        return (rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 120) or {}).get("currentPlayer")

    st = morts = None
    for _ in range(12):
        for _flip in range(3):
            if _cp() == ennemi:
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        if _cp() != ennemi:
            break                       # la main ne passe plus -> on mesure ce qu'on a
        rpc("aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999}, 300)
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        if not (_ok(dv) and _ok(ob) and _ok(snap)) or not (dv.get("units") or []):
            break                       # bataille terminee : on garde la derniere capture utile
        st = load_state(dv, ob, snap, board=env_live["board"], tiles=env_live["tiles"])
        morts = {int(u) for u, e in st.entities.items()
                 if e.get_component(UnitComponent) is not None
                 and not e.get_component(UnitComponent).alive}
        if morts:
            break
    assert st is not None, "capture live KO apres les tours joues"
    vivants = sum(1 for lst in st.effects.by_unit.values() for e in lst if not e.consumed)
    print("\n[gisement] %d entite(s), %d morte(s), %d effet(s) non consomme(s)"
          % (len(st.entities), len(morts), vivants))
    assert morts, "aucune unite morte apres les tours joues -- la mesure serait vide"
    assert vivants, "aucun effet non consomme dans l'etat -- la mesure serait vide"
    portes = {uid: sorted({int(e.effect_type)
                           for e in st.effects.by_unit.get(uid, []) if not e.consumed})
              for uid in sorted(morts)}
    portes = {u: t for u, t in portes.items() if t}
    assert not portes, (
        "des unites MORTES portent des effets non consommes : %s -- le canal live ne reflete plus "
        "`KillUnitOperation$$RemoveEffects`, et lever le gate `alive` ferait firer des triggers "
        "FANTOMES" % portes)


def test_aucun_porteur_steppable_ne_porte_un_effect_type_du_registre():
    """GARDE DU RESIDU `#462-r4b-r1-r1-r1-r1-c-r3-r1` -- le SEUL regime ou la levee pourrait mordre
    a tort, et il est vide.

    `_kill_steppable_units` (`operations/movement.py`) pose `alive=False` + `hp=0` sans retirer les
    effets, alors que le natif passe par `KillUnitOperation$$Execute` avec
    `KillUnitOperationOptions$$ForSteppable` -- dont AUCUN des quatre tests sur `options` n'est sur
    le chemin des trois `RemoveEffects`. Un Steppable ecrase est donc un porteur MORT a effets
    intacts, DE FACON PERSISTANTE, cote port seulement.

    Ce qui rend la levee sans consequence ici : aucun kit `Steppable` ne porte d'ability qui pose un
    `effect_type` du registre `EFFECT_TRIGGERS`, et 18 des 20 sont `Immune`. Le jour ou l'un d'eux
    en portera un, ce bras rougira -- et c'est le residu qu'il faudra alors fermer, pas ce test."""
    import unit_map as UM
    kits = [k for k in UM.all_kits() if "Steppable" in (k.get("traits") or [])]
    assert kits, "aucun kit Steppable trouve -- la mesure serait vide"
    noms_registre = _noms_d_ability_du_registre()
    fautifs = [(k["id"], sorted(set(k.get("abilities_all") or []) & noms_registre))
               for k in kits if set(k.get("abilities_all") or []) & noms_registre]
    print("\n[steppable] %d kit(s) Steppable ; %d nom(s) d'ability adosse(s) au registre"
          % (len(kits), len(noms_registre)))
    assert not fautifs, (
        "un kit Steppable porte une ability adossee au registre EFFECT_TRIGGERS : %s -- le residu "
        "#462-r4b-r1-r1-r1-r1-c-r3-r1 n'est plus vide" % fautifs)


def _noms_d_ability_du_registre() -> set:
    """Les NOMS d'ability associes aux `effect_type` du registre, derives de `EffectType`.

    On ne recopie aucune liste : le nom de l'enum EST la cle de rapprochement avec le
    `abilities_all` d'`unit_map` (meme vocabulaire gameconfig). Un nom compose (`X_Y`) rend aussi sa
    tete `X`, parce que c'est l'ABILITY qui pose l'effet et qu'elle porte le prefixe."""
    from engine.entities.effect_type import EffectType
    noms = set()
    for et in REG.EFFECT_TRIGGERS:
        try:
            n = EffectType(int(et)).name
        except ValueError:
            continue
        noms.add(n)
        noms.add(n.split("_", 1)[0])
    return noms


def test_fire_on_death_est_devenu_inerte_sur_la_face_effet():
    """MESURE DERIVEE : quelles classes d'`EffectTrigger` declarent encore `fire_on_death` ?

    L'attribut mirrore, sur la face ABILITY, le `IsAtomic(ability)` de `CanGetAbilityTrigger` qui
    dispense du gate de vivacite. Sur la face EFFET il n'a plus d'objet -- il n'y a plus de gate a
    dispenser. Ce bras l'ENONCE et le chiffre plutot que de le supposer ; il ne demande PAS son
    retrait (il documente une intention, et le retirer ne changerait aucun comportement)."""
    porteurs = sorted({(int(et), c.__name__)
                       for et, classes in REG.EFFECT_TRIGGERS.items() for c in classes
                       if getattr(c, "fire_on_death", False)})
    print("\n[fod] EffectTrigger declarant fire_on_death : %s" % porteurs)
    for _et, nom in porteurs:
        assert not nom.startswith("Tile"), \
            "un TileEffectTrigger declare fire_on_death : %s (double bequille)" % nom
    assert all(issubclass(c, EffectTrigger) and not issubclass(c, TileEffectTrigger)
               for classes in REG.EFFECT_TRIGGERS.values() for c in classes
               if getattr(c, "fire_on_death", False)), \
        "une classe non-EffectTrigger a ete comptee ici -- l'inventaire ne porte plus sur la face EFFET"
