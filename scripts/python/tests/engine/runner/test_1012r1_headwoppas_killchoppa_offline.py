"""#1012-r1 -- cliquet OFFLINE de `HeadwoppasKillchoppa` (relique 0x60d = 1549 d'`orksWarboss`).

Il garde les SIX etages que le port tranche au decompile, et chacun est ecrit pour ROUGIR sur une
mutation NOMMEE (la mutation est citee dans la docstring de l'etage) :

  0. les ordinaux figes au site (1549 / 1568) + les TROIS registres ;
  1. **la fourche des `options`** : l'effet naît au NIVEAU 0, donc INACTIF et sans magnitude ;
  2. le COMPTEUR : +1 par unite non-`Steppable` que le PORTEUR abat, et rien sinon ;
  3. le gate `IsMeleeAttack` de la patte SELF ;
  4. la MAGNITUDE `extraDmg[TERTIAIRE] x EffectLevel` -- et le niveau PASSIF donnerait autre chose ;
  5. la patte AURA : `UnitsWithVisualId(<constants.unitId>)`, tri-etat compris ;
  6. l'ABSENCE de cap (`max = null`).

Tout ce que ce fichier affirme est LU dans
`engine/entities/effects/loki/headwoppas_killchoppa.py` (en-tete) et
`engine/runner/operations/triggers/loki/headwoppas_killchoppa.py` (en-tete).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import hexgeo                                                              # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.effects.factory import (ABILITY_INIT_OWNER_EFFECTS,   # noqa: E402
                                             EFFECT_CLASSES, EffectFactory)
from engine.entities.effects.loki.headwoppas_killchoppa import (           # noqa: E402
    CTX_ABILITY_STATE_OF, CTX_ATT_VISUAL_ID, HEADWOPPAS_KILLCHOPPA_ABILITY,
    HeadwoppasKillchoppaExtraDmgEffect, _beneficiary_visual_id)
from engine.entities.effects.magnitude import ability_var                  # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType    # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                 # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent            # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS   # noqa: E402
from engine.runner.operations.triggers.loki.headwoppas_killchoppa import (  # noqa: E402
    HEADWOPPAS_KILLCHOPPA_EXTRA_DMG, HeadwoppasKillchoppaIncreaseLevelOnKill)

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/headwoppas_killchoppa.py",
        "scripts/python/engine/runner/operations/triggers/loki/headwoppas_killchoppa.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/engine/runner/damage_model.py",
        # Les primitives que les etages lisent.
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/services/effect_bonus.py",
        "scripts/python/engine/entities/triggers.py",
        # Les mirrors d'enum dont les ordinaux sont FIGES par l'etage 0.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/unit_selection_type.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "DEUX etages lisent le GAMECONFIG, qui se perime SEPAREMENT du build : la constante "
              "`HeadwoppasKillchoppa.constants.unitId` (le visualId des beneficiaires, etage 5) et "
              "les 10 paliers de `variables.extraDmg` (etage 4). L'etage 0 fige les ordinaux 1549 "
              "et 1568, qu'un renumerotage rendrait faux sans toucher aucun chemin ci-dessus.",
}

COLS, ROWS = 6, 6
OWNER_ID, VICTIM_ID, ALLY_ID, OTHER_KILLER_ID = 10, 20, 30, 40
HP = 50000
#: Le porteur : `orksWarboss` << Gulgortz >>, seul `allowedUnits` de la relique.
OWNER_VID = "orksWarboss"
#: Niveau de RELIQUE choisi pour SEPARER le palier tertiaire du palier clampe (meme raison que le
#: niveau 3 de #1012 : un port qui lirait le niveau PASSIF -- 50 sur tout runner normalise, donc le
#: dernier palier -- se trahirait sur la magnitude).
RELIC_LEVEL = 3


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _state():
    """Etat synthetique : le PORTEUR (team 1), une victime ennemie, un allie Ork Boy, et un SECOND
    tueur ami (pour la contre-epreuve `AreEqual(Attacker(), Owner)`)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    units = [
        {"id": OWNER_ID, "visualId": OWNER_VID, "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 1}, "effects": []},
        {"id": VICTIM_ID, "visualId": "astraBullgryn", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 1, "row": 2}, "effects": []},
        {"id": ALLY_ID, "visualId": _beneficiary_visual_id() or "orksNpc2OrkBoy", "alive": True,
         "team": 1, "owner": 1, "pos": {"col": 2, "row": 1}, "effects": []},
        {"id": OTHER_KILLER_ID, "visualId": "orksNob", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 2, "row": 2}, "effects": []},
    ]
    decision = {"currentPlayer": 1, "units": units}
    observe = {"units": [{"squadId": u["id"], "hp": HP, "hpMax": HP} for u in units],
               "counts": {"player": 3}}
    st = load_state(decision, observe, board=Board(tiles, adjacency="evenq"))
    if st.effects is None:
        from engine.entities.effects_state import EffectsState
        st.effects = EffectsState.seed({})
    return st


def _seed_relic(st):
    """Le montage RELIQUE : `ctx.tertiary_ability` + le seed d'owner-effect. C'est la voie que
    `_seed_ability_owner_effects` lit depuis #1005 -- une relique n'est PAS dans le kit."""
    from engine.entities.unit_context import UnitContext
    from engine.runner.components import StatsComponent
    from engine.runner.operations.spawn import _seed_ability_owner_effects
    ctx = UnitContext(entity_id=OWNER_ID, visual_id=OWNER_VID,
                      tertiary_ability=HEADWOPPAS_KILLCHOPPA_ABILITY,
                      tertiary_ability_level=RELIC_LEVEL,
                      tertiary_ability_variables_multiplier=100)
    st.get_entity(OWNER_ID).add_component(StatsComponent(ctx))
    return _seed_ability_owner_effects(st, OWNER_ID, OWNER_VID, 100, ability_level=50)


def _instance(st):
    for e in st.effects.by_unit.get(OWNER_ID, []):
        if e.effect_type == HEADWOPPAS_KILLCHOPPA_EXTRA_DMG and not e.consumed:
            return e
    return None


def _effect(level):
    """Une instance NUE de l'effet, au niveau demande -- pour les etages qui n'ont pas besoin
    d'un `State`."""
    e = EffectFactory.create({"name": EffectType.HeadwoppasKillchoppa_ExtraDmg.name,
                              "effectType": HEADWOPPAS_KILLCHOPPA_EXTRA_DMG,
                              "remaining": 0, "level": level},
                             ability_variables_multiplier=100, ability_level=50)
    e.level = level
    return e


def _state_fn(level=RELIC_LEVEL, mult=100):
    """Mirror du canal `tertiary_ability_state_of` (#357)."""
    def fn(owner_id, ability_name):
        assert ability_name == HEADWOPPAS_KILLCHOPPA_ABILITY, ability_name
        return (level, mult)
    return fn


# --------------------------------------------------------------------------------------------
# Etage 0 -- IDENTITE : les ordinaux figes au site, et les trois registres
# --------------------------------------------------------------------------------------------

def test_etage0_ordinaux_et_registres():
    """Les DEUX ordinaux sont ecrits au site du port ; `probe_313` compare le MIRROR au BUILD et
    redeviendrait vert apres un renumerotage -- ce cran-ci garde la valeur MESUREE a la conversion.

    MUTATION QUI ROUGIT : changer 1568 en 1567 dans le trigger, ou retirer une des trois entrees
    de registre."""
    assert int(TriggeredAbilityType.HeadwoppasKillchoppa) == 0x60d == 1549
    assert int(EffectType.HeadwoppasKillchoppa_ExtraDmg) == 0x620 == 1568
    assert HEADWOPPAS_KILLCHOPPA_EXTRA_DMG == 1568
    # Les TROIS registres, dans le meme commit que le port.
    assert EFFECT_CLASSES[EffectType.HeadwoppasKillchoppa_ExtraDmg.name] is \
        HeadwoppasKillchoppaExtraDmgEffect
    assert ABILITY_INIT_OWNER_EFFECTS[HEADWOPPAS_KILLCHOPPA_ABILITY] == \
        [EffectType.HeadwoppasKillchoppa_ExtraDmg.name]
    assert HeadwoppasKillchoppaIncreaseLevelOnKill in EFFECT_TRIGGERS[1568]
    assert HeadwoppasKillchoppaIncreaseLevelOnKill.event_id == int(EventTriggerType.UnitDefeated) == 54


def test_etage0_la_constante_de_beneficiaire_est_lue_au_gameconfig():
    """`ConfigConstString(TriggeredAbilityConfigId(0x60d), 0)` = `constants.unitId`.

    Le CODER EN DUR en ferait une fausse verite au prochain build ; ce cran verifie qu'elle est
    LUE, et qu'elle est non vide (une constante disparue rendrait la face AURA muette EN SILENCE).

    MUTATION QUI ROUGIT : remplacer `ability_const_str(...)` par un litteral."""
    vid = _beneficiary_visual_id()
    assert vid, "constants.unitId de HeadwoppasKillchoppa introuvable -- la face AURA serait muette"
    assert isinstance(vid, str) and vid.strip() == vid


# --------------------------------------------------------------------------------------------
# Etage 1 -- LA FOURCHE : l'effet naît au NIVEAU 0, donc INACTIF
# --------------------------------------------------------------------------------------------

def test_etage1_l_effet_naît_au_niveau_zero_donc_inactif_et_sans_magnitude():
    """La fourche que #1012-r1 laissait ouverte, tranchee au decompile : `options{+0x10}` est le
    NIVEAU INITIAL (`<DSLFormulas+0x18>` = `Direct(0)`), pas la duree.

    Consequence OBSERVABLE, et c'est elle qu'on garde : au deploiement, l'effet est INACTIF
    (`CreateActiveCondition` = `AmountIsGreaterThanZero(EffectLevel)`) et ne verse RIEN.

    MUTATION QUI ROUGIT : lire `options{+0x10}` comme une duree (l'effet naîtrait au niveau 1
    par le defaut d'`AddEffectBehaviour$$Execute`) -- `is_active()` rendrait alors True et la patte
    SELF verserait `extraDmg` des le tour 0, sans le moindre kill."""
    st = _state()
    poses = _seed_relic(st)
    assert EffectType.HeadwoppasKillchoppa_ExtraDmg.name in poses, poses
    inst = _instance(st)
    assert inst is not None, "l'owner-effect de la relique n'a pas ete seede"
    assert not inst.is_active(), "l'effet naît ACTIF -- la fourche a ete lue comme une duree"
    ctx = {"att_id": OWNER_ID, CTX_ABILITY_STATE_OF: _state_fn()}
    assert inst.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx=ctx) is None


# --------------------------------------------------------------------------------------------
# Etage 2 -- LE COMPTEUR : +1 par kill non-`Steppable` fait par le PORTEUR
# --------------------------------------------------------------------------------------------

def _kill_event(actor_id, victim_id):
    return TriggerEvent(int(EventTriggerType.UnitDefeated), actor_id, victim_id,
                        ranged=False, profile=None, killer_id=actor_id, dying_id=victim_id)


def test_etage2_un_kill_du_porteur_monte_le_niveau_de_un():
    """`On(0x36) & NOT IsSteppableUnit(Target) & AreEqual(Attacker(), Owner)` ->
    `IncreaseEffectLevel(Owner, 1568, Direct(1), null)`.

    MUTATION QUI ROUGIT : incrementer de 2, ou ne pas incrementer du tout."""
    st = _state()
    _seed_relic(st)
    trig = HeadwoppasKillchoppaIncreaseLevelOnKill(OWNER_ID)
    ev = _kill_event(OWNER_ID, VICTIM_ID)
    assert trig.matches(st, ev) is True
    trig.execute_behaviour(st, ev)
    assert int(_instance(st).level) == 1
    trig.execute_behaviour(st, ev)
    assert int(_instance(st).level) == 2, "l'increment n'est pas de +1 par kill"


def test_etage2_le_niveau_un_active_l_effet():
    """Le pendant de l'etage 1 : c'est le COMPTEUR qui allume l'effet. Un gate `IsActive` sur ce
    trigger le gelerait donc a zero POUR TOUJOURS (rail ARRAYSET, aucun gate natif -- cf.
    `probe_229.RAIL`).

    MUTATION QUI ROUGIT : ajouter `if not inst.active: return False` dans `matches`."""
    st = _state()
    _seed_relic(st)
    inst = _instance(st)
    assert not inst.is_active()
    trig = HeadwoppasKillchoppaIncreaseLevelOnKill(OWNER_ID)
    trig.execute_behaviour(st, _kill_event(OWNER_ID, VICTIM_ID))
    assert _instance(st).is_active(), "le premier kill n'active pas l'effet"


def test_etage2_un_kill_fait_par_un_ALLIE_ne_monte_rien():
    """`AreEqual(Attacker(), Owner@+0x30)`. Il n'existe QU'UNE instance (posee sur le porteur) :
    contrairement a ce qu'ecrivait `case-1012` SS 2.2, un Ork Boy qui tue ne monte RIEN.

    MUTATION QUI ROUGIT : retirer le test `ev.actor_id == self.owner_id`."""
    st = _state()
    _seed_relic(st)
    trig = HeadwoppasKillchoppaIncreaseLevelOnKill(OWNER_ID)
    assert trig.matches(st, _kill_event(OTHER_KILLER_ID, VICTIM_ID)) is False
    assert int(_instance(st).level or 0) == 0


def test_etage2_une_victime_steppable_ne_monte_rien():
    """`NOT IsSteppableUnit(Targets@DSLSelectors+0x60)`.

    MUTATION QUI ROUGIT : retirer le conjoint `_TARGET_IS_STEPPABLE`."""
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.unit_context import UnitContext
    from engine.runner.components import StatsComponent
    st = _state()
    _seed_relic(st)
    vctx = UnitContext(entity_id=VICTIM_ID, visual_id="astraBullgryn",
                       traits=(UnitTrait.Steppable.name,))
    st.get_entity(VICTIM_ID).add_component(StatsComponent(vctx))
    trig = HeadwoppasKillchoppaIncreaseLevelOnKill(OWNER_ID)
    assert trig.matches(st, _kill_event(OWNER_ID, VICTIM_ID)) is False


def test_etage6_aucun_cap():
    """`max = null` -> le clamp d'`IncreaseEffectLevelOperation$$Execute` est desactive.
    Contraste EXPLICITE avec `Neuroparasite`, qui, lui, ecrit `$$GetMaximumLevel`.

    MUTATION QUI ROUGIT : introduire un plafond (le niveau plafonnerait avant 12)."""
    st = _state()
    _seed_relic(st)
    trig = HeadwoppasKillchoppaIncreaseLevelOnKill(OWNER_ID)
    ev = _kill_event(OWNER_ID, VICTIM_ID)
    for _ in range(12):
        trig.execute_behaviour(st, ev)
    assert int(_instance(st).level) == 12, "un cap est apparu -- le natif passe `max = null`"


# --------------------------------------------------------------------------------------------
# Etages 3 et 4 -- la patte SELF : gate MELEE, et magnitude `extraDmg[TERTIAIRE] x EffectLevel`
# --------------------------------------------------------------------------------------------

def test_etage3_la_patte_self_est_gatee_melee():
    """`ForAddition(IsMeleeAttack & get_OwnerIsCaster, ...)`. Tri-etat : nature NON PROUVEE melee
    => aucune contribution (`is_melee_attack`).

    MUTATION QUI ROUGIT : retirer le gate -- le bonus tomberait aussi a distance."""
    e = _effect(2)
    ctx = {"att_id": OWNER_ID, CTX_ABILITY_STATE_OF: _state_fn()}
    assert e.create_effect_damage_bonus_for_attack(is_ranged=True, att_ctx=ctx) is None
    assert e.create_effect_damage_bonus_for_attack(is_ranged=None, att_ctx=ctx) is None
    assert e.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx=ctx) is not None


def test_etage4_magnitude_extraDmg_du_TERTIAIRE_fois_le_niveau():
    """`Multiply(ConfigVar(0x8 = extraDmg, GetAbilityState(this)), EffectLevel)`, produit d'ENTIERS.

    MUTATION QUI ROUGIT : oublier le facteur `EffectLevel` (le bonus serait constant), ou
    multiplier deux fois."""
    per = ability_var(HEADWOPPAS_KILLCHOPPA_ABILITY, "extraDmg", RELIC_LEVEL, multiplier_pct=100)
    assert per, "extraDmg[%d] introuvable au gameconfig" % RELIC_LEVEL
    ctx = {"att_id": OWNER_ID, CTX_ABILITY_STATE_OF: _state_fn()}
    for lvl in (1, 2, 5):
        eb = _effect(lvl).create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx=ctx)
        assert eb is not None and int(eb.value) == int(per) * lvl, (lvl, per, eb)


def test_etage4_le_niveau_lu_est_le_TERTIAIRE_pas_le_PASSIF():
    """#357, a l'identique de `NornCrown` : `GetAbilityState(this)` rend l'etat TERTIAIRE. Lire le
    PASSIF (50 sur tout runner normalise) clamperait au dernier palier.

    CE TEST N'A DE VALEUR QUE SI LES DEUX PALIERS DIFFERENT -- il l'assertionne (un test dont le
    discriminant est vide passerait pour vert, cf. la lecon d'`AbilityConstantType`).

    MUTATION QUI ROUGIT : remplacer le canal `tertiary_ability_state_of` par `self.ability_level`."""
    a = ability_var(HEADWOPPAS_KILLCHOPPA_ABILITY, "extraDmg", RELIC_LEVEL, multiplier_pct=100)
    b = ability_var(HEADWOPPAS_KILLCHOPPA_ABILITY, "extraDmg", 50, multiplier_pct=100)
    assert a and b and int(a) != int(b), (
        "palier tertiaire et palier clampe EGAUX (%r vs %r) : ce cran ne discriminerait rien"
        % (a, b))
    e = _effect(1)                       # `ability_level = 50` pose par `_effect`
    eb = e.create_effect_damage_bonus_for_attack(
        is_ranged=False, att_ctx={"att_id": OWNER_ID, CTX_ABILITY_STATE_OF: _state_fn()})
    assert eb is not None and int(eb.value) == int(a), "le port a lu le niveau PASSIF"
    # Canal ABSENT -> repli NOMME sur les niveaux de l'instance (degradation declaree, pas un choix).
    eb2 = e.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx={"att_id": OWNER_ID})
    assert eb2 is not None and int(eb2.value) == int(b)


# --------------------------------------------------------------------------------------------
# Etage 5 -- la patte AURA : `UnitsWithVisualId(<constants.unitId>)`
# --------------------------------------------------------------------------------------------

def _aura_ctx(att_visual_id, **over):
    ctx = {"att_id": ALLY_ID, "owner_id": OWNER_ID, "owner_team": 1, "att_team": 1,
           "is_melee": True, CTX_ABILITY_STATE_OF: _state_fn()}
    if att_visual_id is not None:
        ctx[CTX_ATT_VISUAL_ID] = att_visual_id
    ctx.update(over)
    return ctx


def test_etage5_l_aura_ne_va_qu_aux_unites_du_bon_visualId():
    """`Friends(Owner, UnitsWithVisualId(<constants.unitId>, OnlyAlive), OnlyAliveAndTargetable)`.

    MUTATION QUI ROUGIT : retirer la comparaison de `visualId` -- TOUT allie recevrait le bonus."""
    e = _effect(3)
    good = _beneficiary_visual_id()
    assert e.create_aura_attack_damage_bonus_for_ally(_aura_ctx(good)) is not None
    assert e.create_aura_attack_damage_bonus_for_ally(_aura_ctx("orksNob")) is None


def test_etage5_tri_etat_equipe_melee_et_canal_absent():
    """Les trois refus RESTRICTIFS de la patte AURA, chacun pour un motif NATIF distinct :
    equipe differente (`Friends`), nature non-melee (`IsMeleeAttack`), canal `att_visual_id` non
    mesure (le gate se TAIT plutot que de supposer).

    MUTATION QUI ROUGIT : rendre l'un des trois permissif."""
    e = _effect(3)
    good = _beneficiary_visual_id()
    assert e.create_aura_attack_damage_bonus_for_ally(_aura_ctx(good, att_team=2)) is None
    assert e.create_aura_attack_damage_bonus_for_ally(_aura_ctx(good, is_melee=False)) is None
    assert e.create_aura_attack_damage_bonus_for_ally(_aura_ctx(good, is_melee=None)) is None
    assert e.create_aura_attack_damage_bonus_for_ally(_aura_ctx(None)) is None


def test_etage5_le_porteur_n_est_pas_servi_deux_fois():
    """Le porteur est dans son PROPRE selecteur (`Owner` est le 1er terme), d'ou les DEUX pattes
    disjointes ; l'agregateur exclut deja `uid == att_id`, et la patte AURA le re-refuse.

    MUTATION QUI ROUGIT : retirer le garde `att_id == owner_id` -- double-compte sur Gulgortz."""
    e = _effect(3)
    assert e.create_aura_attack_damage_bonus_for_ally(
        _aura_ctx(_beneficiary_visual_id(), att_id=OWNER_ID)) is None


def test_etage5_le_niveau_zero_ne_verse_rien_sur_aucune_des_deux_pattes():
    """`AmountIsGreaterThanZero(EffectLevel)` ET la magnitude `V x 0` : les deux etages
    convergent. C'est ce qui rend l'effet inerte AVANT le premier kill, des deux cotes.

    MUTATION QUI ROUGIT : traiter `level = None` comme << non mesure >> et se taire (l'effet
    naîtrait actif et le port verserait la magnitude du niveau 1)."""
    e0 = _effect(0)
    assert e0.create_effect_damage_bonus_for_attack(
        is_ranged=False, att_ctx={"att_id": OWNER_ID, CTX_ABILITY_STATE_OF: _state_fn()}) is None
    assert e0.create_aura_attack_damage_bonus_for_ally(
        _aura_ctx(_beneficiary_visual_id())) is None
