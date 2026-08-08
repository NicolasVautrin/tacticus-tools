"""GARDE #BL-1020r (OFFLINE PURE) -- l'effet `1027 HeraldOfTheApocalypse`, ses TROIS ecritures.

CE QU'ELLE PROTEGE. L'effet etait POSE et INERTE : `EffectFactory` rendait un `BaseEffect` nu, donc
`+extraDmg` valait 0 **sans erreur ni crash**. Le port tient sur TROIS ecritures independantes, et
chacune peut sauter seule, en silence :

  1. **LA MAGNITUDE** -- `HeraldOfTheApocalypse_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`
     = `ForAddition(get_OwnerIsTarget & IsUnit(caster@DSLSelectors+0x48), ConfigVar(8 = extraDmg))`.
     Elle sort par le canal DEFENSEUR (`create_effect_damage_malus_for_defense`) parce que le
     trigger est `OwnerIsTarget` : l'effet vit sur la VICTIME. Le natif, lui, verse dans
     `attackModifiers` -> `DEFENSE_MALUS_NATIVE_FACE = "attacker"`.
  2. **LE RETRAIT** -- `...$$CreateRemoveEffectTrigger` = `On(9 = Attack) & OwnerIsTarget &
     IsUnit(caster)`, inscrit dans `EFFECT_TRIGGERS[1027]`. Sans lui le bonus devient **PERMANENT**
     la ou le natif donne UNE charge -- et rien d'autre ne rougit : la magnitude reste juste.
  3. **`scale_from_source=True`** sur l'`AddEffect` de l'arbre de 1020. Le `ConfigVar` est resolu
     contre l'`AbilityState` de la SOURCE (Haarken) ; sans le flag, l'effet lit le niveau et le
     multiplicateur de l'unite qui le PORTE -- une magnitude fausse, jamais une erreur.

⚠ **LE PIEGE QUE CE FICHIER FIGE : le 4e conjoint qui N'EXISTE PAS.** Les deux jumeaux structuraux
de cet effet (`ExemplarOfHate_Target` 1293, `Chronometron_ExtraDamage` 1550) vivent dans le MEME
module et ont la MEME forme (`ForAddition` + `OwnerIsTarget` + face `attacker`). `Chronometron`
porte en plus `AreFriends(caster, EffectSource(Effect))` -- des DEUX cotes (bonus ET retrait). Une
recopie future qui l'ajouterait ici rendrait le port SILENCIEUSEMENT restrictif : le bonus ne
compterait plus que pour les allies de Haarken, et aucun test de magnitude ne le verrait (le
montage nominal a justement un attaquant allie du poseur). Les deux bras `..._SANS_gate_dequipe`
ci-dessous exercent donc un attaquant ENNEMI du poseur, cote bonus ET cote retrait.

Confront LIVE (magnitude bit-exacte + contre-epreuve chiffree + retrait) :
`python scripts/python/probe_bl_1020r_herald_extra_damage.py` et sa garde
`test_bl_1020r_herald_extra_damage_live.py`.
RE : `docs/rl/case-bl-1029-1020.md` Sec.7.2. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, perimetre pris LARGE : le registre de trigger tire la TOTALITE des
        # modules `loki/**` (`dispatch/registry.py` les importe tous), et la couche d'effets tire
        # la factory complete. Un declencheur feuille-a-feuille serait un FAUX VERT. Foyers
        # vraiment load-bearing, pour la relecture humaine :
        # `entities/effects/loki/damage_reduction.py` (la classe), `entities/effects/factory.py`
        # (le routage PAR NOM), `operations/triggers/loki/herald_of_the_apocalypse.py` (le
        # retrait), `operations/triggers/dispatch/registry.py` (le cablage),
        # `runner/abilities/blacklegion.py` (`scale_from_source`).
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment, donc
        # `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py` seul.
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        # La magnitude est `extraDmg[level]` de la config `HeraldOfTheApocalypse` du BUILD, et le
        # nom d'`EffectType` 1027 vient du mirror derive du dump.
        "data/symbols/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : le routage PAR NOM de l'effet 1027, la magnitude `ForAddition("
              "extraDmg[lvl] x mult)` avec sa face `attacker`, le gate `IsUnit(caster)` exerce "
              "seul, l'ABSENCE de tout gate de nature de coup et de tout gate d'EQUIPE (le 4e "
              "conjoint du jumeau Chronometron), l'inscription du retrait dans "
              "`EFFECT_TRIGGERS[1027]` avec `event_id == Attack`, et le `scale_from_source` de "
              "l'arbre de 1020. Aucun runner, aucune session Frida : le seul acces disque est le "
              "depot (gameconfig du build pour `extraDmg`).",
}

import pytest

from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import EffectFactory
from engine.entities.effects.magnitude import ability_var
from engine.dsl.event_trigger_type import EventTriggerType

HERALD_ABILITY = "HeraldOfTheApocalypse"
HERALD_EFFECT = int(EffectType.HeraldOfTheApocalypse)      # 0x403 = 1027
POSEUR, VICTIME, ALLIE_DU_POSEUR, ENNEMI_DU_POSEUR = 83, 77, 85, 79
NIVEAU, MULT = 50, 180


def _effet(level=NIVEAU, mult=MULT, source=POSEUR):
    """L'instance telle que `AddEffectOperation` la materialise apres l'`AddEffect` de 1020 :
    niveau/multiplicateur de la SOURCE (c'est ce que `scale_from_source=True` propage)."""
    e = EffectFactory.create({"name": EffectType.HeraldOfTheApocalypse.name,
                              "effect_type": HERALD_EFFECT, "source": source},
                             mult, level, level)
    return e


def _ctx(attaquant=ALLIE_DU_POSEUR, is_unit=True, **kw):
    c = {"id": attaquant, "is_unit": is_unit}
    c.update(kw)
    return c


# --------------------------------------------------------------------------------------------
# 1. LA MAGNITUDE
# --------------------------------------------------------------------------------------------

def test_1027_est_ROUTE_par_son_NOM_vers_la_classe_dediee():
    """Le routage de `EffectFactory` se fait par le NOM CAPTE, et le nom d'`EffectType` 1027 est
    `HeraldOfTheApocalypse` TOUT COURT -- pas `..._ExtraDamage`, contrairement a la classe native
    `HeraldOfTheApocalypse_ExtraDamageEffect`. Une entree de registre ecrite d'apres le nom NATIF
    laisserait un `BaseEffect` nu : effet present, bonus 0, aucune erreur."""
    from engine.entities.effects.loki.damage_reduction import HeraldOfTheApocalypseExtraDamageEffect
    assert EffectType(HERALD_EFFECT).name == HERALD_ABILITY
    assert isinstance(_effet(), HeraldOfTheApocalypseExtraDamageEffect)


def test_magnitude_vaut_extraDmg_du_niveau_ET_du_multiplicateur_de_la_SOURCE():
    """`ForAddition(ConfigVar(8 = extraDmg))`, indexe par l'`AbilityState` de la SOURCE."""
    attendu = ability_var(HERALD_ABILITY, "extraDmg", NIVEAU, multiplier_pct=MULT)
    assert attendu, "montage : la config du build ne rend pas `extraDmg` -- rien n'est mesure"
    b = _effet().create_effect_damage_malus_for_defense(attacker_ctx=_ctx())
    assert b is not None
    assert b.kind == "Addition", "ForAddition, PAS un pourcentage"
    assert int(b.value) == int(attendu)
    assert b.owner_is_caster is False, "l'effet vit sur la CIBLE"


def test_la_face_native_est_ATTAQUANT_malgre_le_trigger_OwnerIsTarget():
    """Le natif implemente `CreateEffectDamageBonusForAttack` (symbole PROPRE en table) -> il verse
    dans `attackModifiers`. Le port l'evalue dans la boucle DEFENSEUR (seule liste qui balaie les
    effets de la cible), donc il doit DIRE la face -- sinon un `Round` de la mauvaise face."""
    from engine.entities.effects.loki.damage_reduction import HeraldOfTheApocalypseExtraDamageEffect
    assert HeraldOfTheApocalypseExtraDamageEffect.DEFENSE_MALUS_NATIVE_FACE == "attacker"
    b = _effet().create_effect_damage_malus_for_defense(attacker_ctx=_ctx())
    from engine.entities.effects import build_defender_modifiers_from_effects
    acc = build_defender_modifiers_from_effects([_effet()], attacker_ctx=_ctx())
    assert acc.additive, "l'additif defenseur doit porter le bonus"
    assert b is not None


def test_le_gate_IsUnit_du_caster_est_exerce_SEUL():
    """`IsUnit(caster@DSLSelectors+0x48)` : un attaquant qui n'est pas une unite (tuile, objet) ne
    declenche rien. Contexte NON MESURE (`is_unit` absent) -> None aussi : on ne devine pas."""
    e = _effet()
    assert e.create_effect_damage_malus_for_defense(attacker_ctx=_ctx(is_unit=False)) is None
    assert e.create_effect_damage_malus_for_defense(attacker_ctx={"id": ALLIE_DU_POSEUR}) is None
    assert e.create_effect_damage_malus_for_defense(attacker_ctx=None) is None
    assert e.create_effect_damage_malus_for_defense(attacker_ctx={"is_unit": True}) is None


@pytest.mark.parametrize("kw", [
    {"is_melee": True}, {"is_melee": False}, {"is_melee": None},
    {"damage_profile": "Piercing"}, {"damage_profile": "Bolter"}, {"damage_profile": None},
])
def test_AUCUN_gate_de_nature_de_coup(kw):
    """La conjonction native a DEUX conjoints et rien d'autre : ni `IsMeleeAttack`, ni
    `IsRangedAttack`, ni `DamageProfileIs`. Ses deux jumeaux du meme module en ont
    (`ExemplarOfHate` = melee/overwatch ; `Neuroparasite` = Psychic) -- recopier l'un d'eux ici
    rendrait le port restrictif, donc trop FAIBLE, ce qui ne casse jamais un test de presence."""
    b = _effet().create_effect_damage_malus_for_defense(attacker_ctx=_ctx(), **kw)
    assert b is not None and b.kind == "Addition"


def test_AUCUN_gate_dequipe_le_4e_conjoint_du_jumeau_Chronometron_est_ABSENT():
    """⚠ LE PIEGE. `Chronometron_ExtraDamage` (1550), meme module et meme forme, porte en plus
    `AreFriends(caster, EffectSource(Effect))`. Il n'est PAS dans la conjonction de 1027 : un
    attaquant ENNEMI du poseur beneficie du bonus exactement comme un allie."""
    e = _effet(source=POSEUR)
    b_allie = e.create_effect_damage_malus_for_defense(
        attacker_ctx=_ctx(ALLIE_DU_POSEUR, team=1, team_by_id={POSEUR: 1}))
    b_ennemi = e.create_effect_damage_malus_for_defense(
        attacker_ctx=_ctx(ENNEMI_DU_POSEUR, team=2, team_by_id={POSEUR: 1}))
    assert b_allie is not None and b_ennemi is not None
    assert int(b_allie.value) == int(b_ennemi.value)


# --------------------------------------------------------------------------------------------
# 2. LE RETRAIT -- sans lui, le bonus est PERMANENT
# --------------------------------------------------------------------------------------------

def test_le_retrait_est_INSCRIT_dans_EFFECT_TRIGGERS_sur_le_vecteur_Attack():
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    from engine.runner.operations.triggers.loki.herald_of_the_apocalypse import (
        HeraldOfTheApocalypseExtraDamageRemove)
    classes = EFFECT_TRIGGERS.get(HERALD_EFFECT) or []
    assert HeraldOfTheApocalypseExtraDamageRemove in classes
    assert HeraldOfTheApocalypseExtraDamageRemove.event_id == EventTriggerType.Attack   # On(9)


def _state_avec_1027():
    """`State` minimal : la victime PORTE 1027, deux attaquants d'equipes opposees existent."""
    from engine.entities.effects_state import EffectsState
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    from engine.runner.state import State
    from engine.runner.operations.effects import AddEffectOperation
    st = State()
    st.effects = EffectsState()
    for uid, team, pos in ((POSEUR, 1, (3, 3)), (VICTIME, 2, (4, 3)),
                           (ALLIE_DU_POSEUR, 1, (3, 4)), (ENNEMI_DU_POSEUR, 2, (4, 4))):
        e = st.add_entity(uid)
        e.add_component(UnitComponent("u%d" % uid, True))
        e.add_component(OwnerComponent(team, team + 2))
        e.add_component(PositionComponent(pos[0], pos[1]))
    AddEffectOperation.execute(st, source=POSEUR, target=VICTIME, effect_type=HERALD_EFFECT,
                               name=EffectType.HeraldOfTheApocalypse.name)
    return st


def _porte_1027(st, uid):
    return any((not e.consumed) and e.effect_type == HERALD_EFFECT
               for e in st.effects.by_unit.get(uid, []))


def _ev(actor, target):
    from engine.runner.operations.triggers.base import TriggerEvent
    return TriggerEvent(EventTriggerType.Attack, actor, target, ranged=False, profile="Piercing")


@pytest.mark.parametrize("attaquant", [ALLIE_DU_POSEUR, ENNEMI_DU_POSEUR])
def test_le_retrait_consomme_la_charge_SANS_gate_dequipe(attaquant):
    """i2 : « the NEXT attack made by **a unit** against them ». Meme piege que ci-dessus, cote
    RETRAIT : le jumeau Chronometron n'est consomme que par un allie de SON poseur."""
    from engine.runner.operations.triggers.loki.herald_of_the_apocalypse import (
        HeraldOfTheApocalypseExtraDamageRemove)
    st = _state_avec_1027()
    assert _porte_1027(st, VICTIME), "montage : 1027 n'a pas ete pose"
    trig = HeraldOfTheApocalypseExtraDamageRemove(VICTIME)
    ev = _ev(attaquant, VICTIME)
    assert trig.matches(st, ev) is True
    assert trig.execute_behaviour(st, ev) is not None
    assert not _porte_1027(st, VICTIME), "la charge n'a pas ete consommee"


def test_le_retrait_refuse_une_attaque_qui_ne_vise_PAS_le_porteur():
    """`get_OwnerIsTarget` : c'est le seul gate qui borne le vecteur `On(9)`, generique a TOUTE
    attaque de la bataille."""
    from engine.runner.operations.triggers.loki.herald_of_the_apocalypse import (
        HeraldOfTheApocalypseExtraDamageRemove)
    st = _state_avec_1027()
    trig = HeraldOfTheApocalypseExtraDamageRemove(VICTIME)
    assert trig.matches(st, _ev(ALLIE_DU_POSEUR, ENNEMI_DU_POSEUR)) is False
    assert _porte_1027(st, VICTIME)


def test_le_retrait_refuse_un_acteur_qui_nest_PAS_une_unite():
    """`IsUnit(caster)` cote retrait aussi -- meme conjoint que cote bonus."""
    from engine.runner.operations.triggers.loki.herald_of_the_apocalypse import (
        HeraldOfTheApocalypseExtraDamageRemove)
    st = _state_avec_1027()
    st.add_entity(999)                      # entite SANS `UnitComponent` (tuile / objet)
    trig = HeraldOfTheApocalypseExtraDamageRemove(VICTIME)
    assert trig.matches(st, _ev(999, VICTIME)) is False
    assert trig.matches(st, _ev(None, VICTIME)) is False


# --------------------------------------------------------------------------------------------
# 3. `scale_from_source` -- sans lui, la magnitude lit le PORTEUR
# --------------------------------------------------------------------------------------------

def test_larbre_de_1020_pose_1027_avec_scale_from_source():
    """`AddEffect(0x403, AbilityStateReference, source = Owner@0x148, targets, options ZERO)` :
    l'`AbilityStateReference` est le 3e argument natif, et c'est lui que `scale_from_source`
    porte. Sans le flag, l'effet resout `ConfigVar(extraDmg)` contre le niveau/multiplicateur de
    la VICTIME -- une magnitude fausse, jamais une erreur."""
    from engine.runner.abilities.behaviours.effects import AddEffect
    from engine.runner.abilities.blacklegion import herald_of_the_apocalypse_tree

    trouves = []

    def _walk(n, vus):
        if id(n) in vus:
            return
        vus.add(id(n))
        if isinstance(n, AddEffect) and n.effect_type == HERALD_EFFECT:
            trouves.append(n)
        for v in list(getattr(n, "__dict__", {}).values()) + [
                getattr(n, s, None) for s in getattr(n, "__slots__", ())]:
            if hasattr(v, "__dict__") or hasattr(v, "__slots__"):
                _walk(v, vus)
            elif isinstance(v, (list, tuple)):
                for x in v:
                    if hasattr(x, "__dict__") or hasattr(x, "__slots__"):
                        _walk(x, vus)

    _walk(herald_of_the_apocalypse_tree(2), set())
    assert len(trouves) == 1, "l'arbre de 1020 doit poser 1027 EXACTEMENT une fois"
    assert trouves[0].scale_from_source is True
    assert trouves[0].duration_rounds is None, "options natives ZERO -> duree par DEFAUT"
