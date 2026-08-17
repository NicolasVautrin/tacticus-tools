"""#924-r1 -- la face DEGAT de `EarlyWarningOverride_ReactivateOverwatch` (1145), gardes OFFLINE.

CE FICHIER GARDE CE QUE LA CONFRONTATION LIVE NE PEUT PAS VOIR. Le test live
(`tests/engine/runner/test_924r1_early_warning_override_overwatch_live.py`) CAPTURE l'etat APRES le
cast : `load_state` seede alors les niveaux d'ability depuis l'`unitConfig` du PORTEUR de l'effet --
et ici porteur == source (Re'vas se pose l'effet a elle-meme). Le live reste donc VERT meme si la
pose oublie l'`AbilityStateReference` natif. Mesure : retirer `scale_from_source=True` de
`early_warning_override_tree` laisse le test live PASSER.

Sur le chemin PUREMENT OFFLINE (le runner joue lui-meme le cast), c'est `AddEffectOperation` qui
cree l'instance, avec `ability_level = active_ability_level = None` sauf si la feuille porte
`scale_from_source`. La face serait alors MATERIALISEE ET INERTE -- exactement le vice que
#462-r4b-r1-r1 a ferme ailleurs. C'est l'etage 3 ci-dessous.

Tout est offline : aucun runner, aucun RPC.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import EFFECT_CLASSES
from engine.entities.effects.loki.inescapable_death import (
    EARLY_WARNING_OVERRIDE, EarlyWarningOverrideReactivateOverwatchEffect,
    INESCAPABLE_DEATH, InescapableDeathEffect, is_overwatch_triggered,
)
from engine.entities.effects.magnitude import ability_var

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/inescapable_death.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/abilities/tau.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/gameconfig.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Fige les ordinaux MESURES au portage de 1145, la SEPARATION de magnitude d'avec sa "
              "soeur 1018 (un copier-coller y ecrirait la config de l'autre ability), et le "
              "`scale_from_source=True` de la pose -- que la confrontation live ne peut PAS voir.",
}

#: le mult de rarete d'un HERO mythique rank 17 : le meme que celui mesure sur `tauCrisis`
#: (`unitConfig.abilityVariablesMultiplier = 180`, capte au montage live).
MULT = 180
LEVEL = 50


def _ewo(level: int = LEVEL, mult: int = MULT) -> EarlyWarningOverrideReactivateOverwatchEffect:
    """⚠ `BaseEffect.__init__` prend `name` en PREMIER : construire par MOTS-CLES, sinon le
    multiplicateur reste a son defaut et le volet SCALING devient inerte (meme piege que #924)."""
    return EarlyWarningOverrideReactivateOverwatchEffect(
        name=EffectType.EarlyWarningOverride_ReactivateOverwatch.name,
        effect_type=int(EffectType.EarlyWarningOverride_ReactivateOverwatch),
        active_ability_level=level, ability_variables_multiplier=mult)


# ------------------------------------------------------- 1. ORDINAUX et REGISTRE, figes au portage

def test_924r1_ordinaux_mesures_au_portage():
    """Valeurs LUES au decompile, figees au site : `EarlyWarningOverride_ReactivateOverwatchEffect$$
    .ctor` = `AReactivateOverwatchEffect..ctor(this, **0x435**)` -- et `0x435 = 1077` est un
    `ActiveAbilityType`, pas un `TriggeredAbilityType` (c'est ce qui commande la cascade de niveau).
    Les quatre `AddEffect` d'`ExecuteBehaviour` portent `0x3f1 / 0x478 / 0x479 / 0x47d`."""
    assert int(ActiveAbilityType.EarlyWarningOverride) == 0x435 == 1077
    assert int(EffectType.EarlyWarningOverride_ReactivateOverwatch) == 0x479 == 1145
    assert int(EffectType.EarlyWarningOverride_HitReduction) == 0x47a == 1146
    assert int(EffectType.EarlyWarningOverride_Visual) == 0x47d == 1149
    assert int(EffectType.SuppressCloseCombatWeakness) == 0x478 == 1144
    assert int(EffectType.Overwatch_AutoAttack) == 0x3f1 == 1009


def test_924r1_la_classe_est_au_registre():
    assert EFFECT_CLASSES.get(EffectType.EarlyWarningOverride_ReactivateOverwatch.name) \
        is EarlyWarningOverrideReactivateOverwatchEffect


# ------------------------------------------- 2. la MAGNITUDE : deux soeurs, DEUX configs distinctes

def test_924r1_la_magnitude_vient_de_SA_config_pas_de_celle_de_sa_soeur():
    """LE point ou un copier-coller de 1018 donnerait un port FAUX en silence. Les deux classes ont
    le MEME corps `GetOverwatchExtraDamage` (ICF : un seul corps, deux proprietaires), mais toute la
    variabilite passe par `this` -- `config@+0x60` est la config de l'ability passee au `.ctor`.

    Ce test assertionne son propre NON-VIDE **et** l'ECART : si les deux valeurs devenaient egales,
    la confusion redeviendrait invisible et il faudrait un autre discriminant."""
    ewo = ability_var(EARLY_WARNING_OVERRIDE, "extraDmg", LEVEL, multiplier_pct=MULT)
    idd = ability_var(INESCAPABLE_DEATH, "extraDmg", LEVEL, multiplier_pct=MULT)
    assert ewo and idd, (ewo, idd)
    assert ewo != idd, ("les deux configs rendent la MEME valeur : ce test ne discrimine plus un "
                        "copier-coller entre les deux soeurs -- re-deriver le discriminant")
    assert _ewo().create_effect_damage_bonus_for_attack(att_ctx={"is_overwatch": True}).value == ewo
    e_id = InescapableDeathEffect(name=EffectType.InescapableDeath_Effect.name,
                                  effect_type=int(EffectType.InescapableDeath_Effect),
                                  ability_level=LEVEL, ability_variables_multiplier=MULT)
    assert e_id.create_effect_damage_bonus_for_attack(att_ctx={"is_overwatch": True}).value == idd


def test_924r1_le_niveau_se_lit_sur_le_slot_ACTIF_dabord():
    """`EarlyWarningOverride` est une ability **ACTIVE** (1077) : la cascade commence par
    `active_ability_level`, la ou celle de sa soeur (passive 1005) commence par `ability_level`.
    Sans etat d'ability du tout, `ConfigVar` n'a rien a indexer -> la face se TAIT."""
    assert _ewo().create_effect_damage_bonus_for_attack(att_ctx={"is_overwatch": True}) is not None
    nu = EarlyWarningOverrideReactivateOverwatchEffect(
        name=EffectType.EarlyWarningOverride_ReactivateOverwatch.name,
        effect_type=int(EffectType.EarlyWarningOverride_ReactivateOverwatch))
    assert nu.create_effect_damage_bonus_for_attack(att_ctx={"is_overwatch": True}) is None


# ------------------------------------------------- 3. la POSE porte l'`AbilityStateReference` natif

def test_924r1_les_quatre_AddEffect_portent_le_snapshot_dability_state():
    """`...EarlyWarningOverrideAbility$$ExecuteBehaviour` construit UN SEUL
    `DSLSelectors.CreateSnapshot(abilityState)` et le passe TEL QUEL aux QUATRE `AddEffect`.

    Cote port c'est `scale_from_source=True`. **La confrontation live ne peut PAS garder ce cran** :
    quand l'etat est capture APRES le cast, `load_state` seede les niveaux depuis l'`unitConfig` du
    porteur -- et ici porteur == source. Mesure : sans `scale_from_source`, le test live PASSE
    quand meme. Sur le chemin purement offline, l'instance naitrait sans `AbilityState` et la face
    serait materialisee et INERTE."""
    from engine.runner.abilities.tau import EWO_EFFECTS, early_warning_override_tree

    poses = {int(t) for t, _ in EWO_EFFECTS}
    assert poses == {int(EffectType.Overwatch_AutoAttack),
                     int(EffectType.SuppressCloseCombatWeakness),
                     int(EffectType.EarlyWarningOverride_ReactivateOverwatch),
                     int(EffectType.EarlyWarningOverride_Visual)}, sorted(poses)

    class _Etat:                       # `convert_rounds_to_turns` ne lit QUE ce champ ici
        turn_order_player_count = 2
    feuilles = _feuilles_add_effect(early_warning_override_tree(_Etat(), []))
    assert {int(f.effect_type) for f in feuilles} == poses, [f.effect_type for f in feuilles]
    manquants = [int(f.effect_type) for f in feuilles if not f.scale_from_source]
    assert not manquants, (
        "ces `AddEffect` ne portent pas l'`AbilityStateReference` natif (`scale_from_source`) : "
        "leur `ConfigVar` rendra `None` sur le chemin offline -> face INERTE. %s" % (manquants,))


def _feuilles_add_effect(node) -> list:
    """Parcours de l'arbre DSL construit -- les `AddEffect` sont assembles par `op_add`, dont la
    forme interne n'est pas un contrat : on descend par les attributs de composition connus."""
    from engine.runner.abilities.behaviours.effects import AddEffect
    vus, pile, out = set(), [node], []
    while pile:
        n = pile.pop()
        if n is None or id(n) in vus:
            continue
        vus.add(id(n))
        if isinstance(n, AddEffect):
            out.append(n)
            continue
        for nom in ("left", "right", "children", "behaviours", "nodes", "a", "b", "inner", "child"):
            v = getattr(n, nom, None)
            if isinstance(v, (list, tuple)):
                pile.extend(v)
            elif v is not None:
                pile.append(v)
        for nom in getattr(n, "__slots__", ()) or ():
            v = getattr(n, nom, None)
            if isinstance(v, (list, tuple)):
                pile.extend(x for x in v if hasattr(x, "__slots__") or hasattr(x, "__dict__"))
            elif hasattr(v, "__slots__") or hasattr(v, "__dict__"):
                pile.append(v)
    return out


# --------------------------------------------------- 4. le GATE : UN foyer, partage par les DEUX

def test_924r1_le_gate_est_le_MEME_foyer_que_celui_de_sa_soeur():
    """Les deux classes appellent `is_overwatch_triggered` -- et c'est une MESURE, pas une commodite :
    le 3e conjoint de 1145 est le `<vtable +0x768>` de la BASE (`<DSLTriggers+0x70>` = `YesTrigger`,
    constante VRAIE), et celui de 1018 est son override `IsOverwatchAttack()`, qui est le MEME
    predicat que le `TriggeringEffectIs(0x3f1)` qui le precede. Les deux gates coincident donc,
    et un seul foyer les porte."""
    ouvre = ({"trigger_ability_type": int(EffectType.Overwatch_AutoAttack)}, {"is_overwatch": True})
    ferme = (None, {}, {"is_overwatch": False},
             {"trigger_ability_type": int(EffectType.SuppressCloseCombatWeakness)})
    for c in ouvre:
        assert is_overwatch_triggered(c) is True, c
    for c in ferme:
        assert is_overwatch_triggered(c) is False, c
    e = _ewo()
    for c in ferme:
        assert e.create_effect_damage_bonus_for_attack(att_ctx=c) is None, c


def test_924r1_aucun_gate_de_nature_dattaque_na_ete_INVENTE():
    """`AReactivateOverwatchEffect$$CreateDamageModifier` n'a NI `IsRangedAttack`, NI
    `IsNormalAttack`, NI `has_moved` -- alors que l'i2 anglais parle de << **ranged** attacks >>.
    La restriction au tir tient au FAIT que l'overwatch EST un tir. Un gate invente ici serait
    invisible tant qu'on ne teste que l'overwatch : ce test le rend visible."""
    e = _ewo()
    ctx = {"is_overwatch": True}
    ref = e.create_effect_damage_bonus_for_attack(att_ctx=ctx)
    assert ref is not None
    for kw in ({"is_ranged": False}, {"is_ranged": True}, {"is_normal_attack": False},
               {"has_moved": True}, {"has_moved": False},
               {"target_traits": frozenset({"Hero"})}, {"is_prediction": True}):
        got = e.create_effect_damage_bonus_for_attack(att_ctx=ctx, **kw)
        assert got is not None and got.value == ref.value, (kw, got)
