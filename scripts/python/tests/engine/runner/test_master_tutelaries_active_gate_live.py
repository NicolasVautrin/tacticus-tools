"""#231 -- un effet-marqueur 1197 INACTIF doit ETEINDRE la triggered 1173 (Screamer d'Abraxas).

> QUALIFICATION D'ENUM : `1197` ici = `EffectType.MasterOfTheTutelaries` (0x4ad). Ce n'est NI
> `ActiveAbilityType.ExcruciatingFrequencies` NI `TriggeredAbilityType.FeederTendrils`, qui
> portent la meme valeur dans d'autres enums.

CE QUE LE NATIF DIT (RE, cf. `docs/rl/case-231-master-tutelaries-active-gate.md`) -- 1197 est du
rail APPLY_REVERT, pas du rail TARGETS, et les deux ne se gatent PAS pareil :

  * l'arbre du trigger ne teste QUE la presence --
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$
    CreateTrigger` passe `HasEffect(owner@0x148, 0x4ad, onlyActive=**0**, relation=6=Both)`.
    Semantique du 4e argument LUE dans `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect`
    (il ne `continue` sur `IsActive@0x5c == 0` que si ce bool est vrai) ;
  * l'activite mord par un AUTRE chemin : la triggered 1173 est PORTEE PAR L'UNITE, ajoutee par
    `IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$ApplyInternal`
    (`AddTriggeredAbility(0x495)`) et retiree par `$$RevertInternal`
    (`RemoveTriggeredAbility(0x495)`). Or `IdunBattle.Operations.RefreshEffectsOperation$$
    DeactivateEffect` ecrit `EffectComponent.IsActive @+0x5c = 0` PUIS enchaine sur
    `UpdateEffectTargets` avec une liste de cibles **VIDE** -> `RemoveTargetsFromEffect` ->
    `Revert`. Effet inactif => triggered RETIREE => aucun Screamer.

CE QUE LE PORT FAISAIT : `matches` ne lisait pas `e.active`, en supposant le gate « implicite par
la collecte `EFFECT_TRIGGERS` ». FAUX -- `collect_effect_triggers` ne filtre que `consumed`, et
c'est VOULU (le rail ArraySet doit pouvoir RE-ACTIVER un effet eteint, #127/#229). Une instance
1197 inerte faisait donc spawner un Screamer que le natif ne peut pas produire.

PORTEE DE LA CONFRONTATION (mesure du 2026-07-29, ci-dessous `test_live_cast_arms_the_chain`) :
le chemin NOMINAL est confronte au live -- Abraxas caste 1096, le Pink Horror apparait et la
chaine 1173 produit des Screamers. Le chemin INACTIF, lui, n'est PAS atteignable live
aujourd'hui : le capteur `readEffectsByUnit` ne publie 1197 sur AUCUN canal (ni par defaut ni
`includeInactive`), donc aucune instance 1197 ne peut arriver offline par le seed, et la pose
offline cree l'effet ACTIF. Le gate est donc verrouille par CONSTRUCTION D'ETAT sur un etat LIVE
(on ecrit le flag comme le fait `DeactivateEffect`), ce qui est exactement la contre-epreuve : ces
assertions ECHOUENT sur le port d'avant #231 et PASSENT apres. Consequence a assumer : le gate est
non-regressif par construction (aucun etat produit aujourd'hui ne le fait mordre) -- c'est un
cliquet de fidelite, pas un changement de nombre.

ASCII only. Dispose SES runners.
"""
from __future__ import annotations

import pytest

import probe_112_darkangels as PR
import probe_224_effect_immunity as IM
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.components import OwnerComponent, UnitComponent
from engine.runner.operations.effects import AddEffectOperation
from engine.runner.operations.triggers.base import TriggerEvent
from engine.runner.operations.triggers.dispatch.core import collect_effect_triggers
from engine.runner.snapshot import decision_view_seed_body, load_state

MASTER_EFFECT = int(EffectType.MasterOfTheTutelaries)      # 1197 (0x4ad)
ABILITY = 1096                                             # MasterOfTheTutelariesAbility
CASTER_VISUAL = "thousInfernalMaster"                      # Abraxas -- HERO, present dans --list-pool
ENEMIES = ["blackAbaddon", "necroWarden"]
HORROR, SCREAMER = "thousNpc1PinkHorror", "thousNpc2Screamer"
PSYCHIC = "Psychic"                                        # profil 0xd du gate de l'arbre


# ------------------------------------------------------------------ helpers

def _dv(sid, rid, *, wide: bool):
    body = (decision_view_seed_body(rid, allAbilities=True) if wide
            else {"runnerId": rid, "allAbilities": True})
    return PR.rpc(sid, "decisionView", body, 90)


def _visual_counts(dv) -> dict:
    out: dict = {}
    for u in (dv.get("units") or []):
        out[u.get("visualId")] = out.get(u.get("visualId"), 0) + 1
    return out


def _has_effect_anywhere(dv, effect_type: int) -> bool:
    return any(int(e.get("effectType") or -1) == int(effect_type)
               for u in (dv.get("units") or []) for e in (u.get("effects") or []))


def _tile_targets(sid, rid, caster) -> list:
    """Tuiles LEGALES pour 1096 DEPUIS la position courante. 1096 vise une TUILE (le spawn du
    Horror) : `abilityTargets` rend `{kind:'tile', tile:{col,row}}`, jamais un `targetId`."""
    at = PR.rpc(sid, "abilityTargets",
                {"runnerId": rid, "unitId": caster, "abilityType": ABILITY}, 90)
    for u in (at.get("units") or []):
        for a in (u.get("abilities") or []):
            if int(a.get("abilityId") or -1) == ABILITY:
                return [t["tile"] for t in (a.get("fromHere") or [])
                        if t.get("kind") == "tile" and t.get("tile")]
    return []


def _instances(state, uid) -> list:
    effs = (state.effects.by_unit.get(int(uid)) if state.effects is not None else None) or []
    return [e for e in effs if not e.consumed and e.effect_type == MASTER_EFFECT]


def _triggers_for(state, uid) -> list:
    return [t for t in collect_effect_triggers(state)
            if t.effect_type == MASTER_EFFECT and int(t.owner_id) == int(uid)]


def _an_enemy_of(state, uid):
    e0 = state.get_entity(int(uid))
    oc0 = e0.get_component(OwnerComponent) if e0 is not None else None
    for eid, e in state.entities.items():
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        if (oc is not None and oc0 is not None and oc.team != oc0.team
                and uc is not None and uc.alive):
            return int(eid)
    return None


def _attack_event(actor, target):
    """`On(9 = Attack, 1)` porteur d'un profil PSYCHIC -- le seul conjoint de l'arbre qui depende
    du coup (`CurrentAttackDamageProfilesContain(0xd)`)."""
    return TriggerEvent(int(EventTriggerType.Attack), int(actor), int(target),
                        ranged=False, profile=None, profiles={PSYCHIC})


# ------------------------------------------------------------------ fixture

@pytest.fixture(scope="module")
def tutelaries_case(live_session):
    """UN runner pour tout le fichier. Abraxas caste 1096 EN LIVE (le marqueur et la chaine
    doivent venir du JEU, pas d'une pose offline), puis on capture les deux canaux et on charge
    l'etat par le canal large."""
    sid = live_session
    rid = IM._build_custom(sid, [CASTER_VISUAL], ENEMIES)
    try:
        dv0 = _dv(sid, rid, wide=False)
        bv = PR.units_by_visual(dv0)
        if CASTER_VISUAL not in bv:
            pytest.skip("roster incomplet: %s" % sorted(k for k in bv if k))
        caster = bv[CASTER_VISUAL]["id"]
        tiles = _tile_targets(sid, rid, caster)
        if not tiles:
            pytest.skip("aucune tuile legale pour 1096 depuis la position courante")
        res = PR.act(sid, rid, {"kind": "ability", "casterId": caster, "abilityType": ABILITY,
                                "to": {"col": tiles[0]["col"], "row": tiles[0]["row"]}})
        assert res.get("ok"), "cast live 1096 KO: %s" % str(res)[:200]

        bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        cs = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
        dv_def, dv_all = _dv(sid, rid, wide=False), _dv(sid, rid, wide=True)
        yield {"sid": sid, "rid": rid, "caster": caster, "dv0": dv0,
               "dv_def": dv_def, "dv_all": dv_all,
               "st": load_state(dv_all, ob, cs, board=board)}
    finally:
        PR.dispose(sid, rid)


# ------------------------------------------------------------------ ce que le LIVE dit

def test_live_cast_arms_the_chain(tutelaries_case):
    """PREMISSE LIVE : le cast de 1096 fait apparaitre le Pink Horror, et la chaine 1173
    (`MasterOfTheTutelaries_SummonAbility`) produit des Screamers -- donc la triggered EST portee
    par Abraxas cote natif. Sans ce fait, gater son pendant offline ne mesurerait rien."""
    c = tutelaries_case
    before, after = _visual_counts(c["dv0"]), _visual_counts(c["dv_def"])
    horrors = after.get(HORROR, 0) - before.get(HORROR, 0)
    screamers = after.get(SCREAMER, 0) - before.get(SCREAMER, 0)
    assert horrors >= 1, "le cast live n'a spawn AUCUN Pink Horror (%s -> %s)" % (before, after)
    if screamers < 1:
        pytest.skip("la chaine 1173 n'a pas fire dans cette geometrie (0 Screamer) -- "
                    "le Horror doit attaquer en Psychic pour re-declencher")
    assert screamers >= 1


def test_the_marker_is_not_published_by_any_capture_channel(tutelaries_case):
    """BORNE DE CONFRONTABILITE, mesuree et non supposee : bien que la chaine soit ARMEE (test
    precedent), `readEffectsByUnit` ne publie 1197 sur AUCUN canal -- ni par defaut, ni
    `includeInactive`. C'est ce qui rend le regime « instance 1197 inerte » INATTEIGNABLE par le
    seed aujourd'hui, et donc le gate non-regressif par construction. Si cette assertion tombe un
    jour (capteur elargi), le gate deviendra confrontable live directement : c'est une BONNE
    nouvelle, pas une regression -- relire la fiche avant de la relacher."""
    c = tutelaries_case
    assert not _has_effect_anywhere(c["dv_def"], MASTER_EFFECT)
    assert not _has_effect_anywhere(c["dv_all"], MASTER_EFFECT)
    assert not _instances(c["st"], c["caster"]), \
        "1197 seede alors qu'aucun canal ne le publie -- la borne a change"


# ------------------------------------------------------------------ LE CRITERE #231

def test_an_active_marker_lets_the_summon_trigger_match(tutelaries_case):
    """CHEMIN NOMINAL (non-regression du gate) : marqueur POSE et ACTIF -> le trigger est collecte
    ET `matches` accepte une attaque Psychic sur un ennemi. Le gate ne doit rien casser ici."""
    c = tutelaries_case
    st, abx = c["st"], c["caster"]
    enemy = _an_enemy_of(st, abx)
    if enemy is None:
        pytest.skip("aucun ennemi vivant dans l'etat charge")
    eff = AddEffectOperation.execute(st, source=abx, target=abx, effect_type=MASTER_EFFECT,
                                     name=EffectType.MasterOfTheTutelaries.name)
    assert eff is not None and eff.active is True, \
        "la pose offline doit creer l'entite-effet ACTIVE (mirror AddEffectOperation)"
    trigs = _triggers_for(st, abx)
    assert trigs, "1197 pose mais EFFECT_TRIGGERS n'instancie aucun trigger 1173"
    assert any(t.matches(st, _attack_event(abx, enemy)) for t in trigs), \
        "marqueur ACTIF : le trigger 1173 refuse une attaque Psychic sur un ennemi"


def test_deactivating_the_marker_disarms_the_summon(tutelaries_case):
    """LE CRITERE. On ecrit `EffectComponent.IsActive @+0x5c = 0` sur l'instance -- exactement ce
    que fait `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect`, dont l'enchainement
    `UpdateEffectTargets(cibles vides)` -> `RemoveTargetsFromEffect` -> `Revert` ->
    `MasterOfTheTutelariesEffect$$RevertInternal` RETIRE la triggered 1173 de l'unite.
    => plus AUCUN fire possible. CETTE assertion ECHOUE sur le port d'avant #231."""
    c = tutelaries_case
    st, abx = c["st"], c["caster"]
    enemy = _an_enemy_of(st, abx)
    if enemy is None:
        pytest.skip("aucun ennemi vivant dans l'etat charge")
    insts = _instances(st, abx)
    if not insts:                                   # ordre des tests non garanti -> pose idempotente
        AddEffectOperation.execute(st, source=abx, target=abx, effect_type=MASTER_EFFECT,
                                   name=EffectType.MasterOfTheTutelaries.name)
        insts = _instances(st, abx)
    assert insts, "aucune instance 1197 a desactiver"
    ev = _attack_event(abx, enemy)
    trigs = _triggers_for(st, abx)
    assert any(t.matches(st, ev) for t in trigs), "premisse: le trigger doit matcher AVANT"

    for e in insts:                                  # DeactivateEffect : +0x5c = 0
        e.active = False

    assert not any(t.matches(st, ev) for t in _triggers_for(st, abx)), \
        "marqueur INACTIF : le trigger 1173 matche encore -- le port spawnerait un Screamer que " \
        "le natif ne peut pas produire (la triggered a ete RemoveTriggeredAbility'ee par Revert)"


def test_the_collect_rail_still_ignores_the_flag(tutelaries_case):
    """NON-REGRESSION #229 -- le gate est dans `matches`, PAS dans la collecte. Meme INACTIVE,
    l'instance reste dans `EFFECT_TRIGGERS` : c'est ce qui permet au rail ArraySet
    (`EvaluateEffectTriggerEffectAbilities`, qui n'a AUCUN gate `IsActive`) de RE-ACTIVER un effet
    eteint. Gater la collecte eteindrait ce rail pour tous les effets."""
    c = tutelaries_case
    st, abx = c["st"], c["caster"]
    insts = _instances(st, abx)
    if not insts:
        AddEffectOperation.execute(st, source=abx, target=abx, effect_type=MASTER_EFFECT,
                                   name=EffectType.MasterOfTheTutelaries.name)
        insts = _instances(st, abx)
    for e in insts:
        e.active = False
    assert _triggers_for(st, abx), \
        "la collecte a filtre sur e.active -- le rail ArraySet ne pourrait plus re-activer"
