"""#964 OFFLINE -- `FuryFromTheDelve` (TriggeredAbilityType 1528, `votanBeserk`).

Ce fichier GARDE ce que le decompile a dit, sans session : les ordinaux ECRITS AUX SITES, le
cablage du registre, les constantes du gameconfig que le port LIT, et surtout la POLARITE du flag
persistant -- le seul endroit ou une inversion serait silencieuse. La confrontation au natif vit
dans `scripts/python/probe_964_fury_from_the_delve.py` (bit-exact sur les deux regimes).

Pourquoi FIGER les ordinaux ici alors que `probe_313` garde deja les mirrors : `probe_313` compare
le MIRROR au BUILD, donc il redevient vert des qu'on regenere le mirror apres un renumerotage --
alors que la valeur ECRITE au site, elle, a change. Meme cran que
`test_270r1r1r3_role_enum_offline.py` etage 1.
"""
from __future__ import annotations

import pytest

#: Perimetre du declencheur (#486-r15) : le module porteur, le registre qui le fait exister, les
#: mirrors d'enum dont un ordinal est fige ci-dessous, et le gameconfig d'ou sortent les quatre
#: constantes.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/triggers/loki/fury_from_the_delve.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/damage_profile_type.py",
        "scripts/python/engine/entities/stats.py",
        "data/gameconfig.json",
    ),
}

FURY = "FuryFromTheDelve"


# --------------------------------------------------------------------- 1. ORDINAUX ECRITS AU SITE
def test_ordinaux_ecrits_au_site():
    """Les ordinaux MESURES a la conversion, figes. Un renumerotage du build les fait rougir ICI,
    la ou `probe_313` redeviendrait vert apres regeneration du mirror."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.entities.ability_constant_type import AbilityConstantType
    from engine.entities.ability_variable_type import AbilityVariableType
    from engine.entities.effect_type import EffectType
    from engine.entities.stats import StatPart, StatType
    from engine.entities.triggered_ability_type import TriggeredAbilityType

    assert int(TriggeredAbilityType.FuryFromTheDelve) == 1528       # 0x5f8
    assert int(EffectType.Pinned) == 1065                           # 0x429
    assert int(EventTriggerType.PreUnitAbility) == 42               # 0x2a -- bras 1
    assert int(EventTriggerType.NormalAttack) == 38                 # 0x26 -- bras 2
    assert int(AbilityConstantType.hpPct) == 18                     # 0x12 -- GetNumberConstant
    assert int(AbilityConstantType.nrOfRounds) == 69                # 0x45 -- GetNumberConstant
    assert int(AbilityConstantType.nrOfHits) == 47                  # 0x2f -- GetHits()
    assert int(AbilityVariableType.minDmg) == 12 and int(AbilityVariableType.maxDmg) == 13
    assert int(StatType.HEALTH) == 5                                # StatAmount(., 0x5, .)
    assert int(StatPart.CURRENT) == 0 and int(StatPart.MAXIMUM) == 2


def test_les_deux_ordinaux_du_kit_nomment_autre_chose_ailleurs():
    """Le NOM est le seul canal ou une confusion d'enum est visible (CLAUDE.md). On le VERIFIE au
    lieu de l'affirmer -- et on assertionne le NON-VIDE, sans quoi le test passerait pour vert en
    ne mesurant rien."""
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType

    autres = {}
    for enum in (ActiveAbilityType, EffectType):
        m = next((x for x in enum if int(x) == int(TriggeredAbilityType.FuryFromTheDelve)), None)
        if m is not None:
            autres[enum.__name__] = m.name
    assert autres, ("aucun autre enum ne porte l'ordinal 1528 : ce controle ne mesure rien -- "
                    "verifier qu'il n'est pas devenu vide par renumerotage")
    assert FURY not in autres.values(), (
        "l'ordinal 1528 nomme AUSSI `FuryFromTheDelve` dans %r : la confusion d'enum y serait "
        "SILENCIEUSE, et le port doit alors qualifier son enum a chaque site" % autres)


# --------------------------------------------------------------------- 2. CABLAGE DU REGISTRE
def test_les_deux_bras_sont_au_registre():
    """UN nom de kit, DEUX classes -- et les deux sont necessaires. `ABILITY_TRIGGERS` est keye par
    le NOM gameconfig de la passiveAbility (canal `collect_triggered_abilities`)."""
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.runner.operations.triggers.loki.fury_from_the_delve import (
        FuryFromTheDelveAttackOrPinAbility, FuryFromTheDelveCheckTargetHealthAbility)

    entree = ABILITY_TRIGGERS.get(FURY)
    assert entree, "`ABILITY_TRIGGERS['%s']` absent -- le passif n'est branche par AUCUN canal" % FURY
    assert set(entree) == {FuryFromTheDelveCheckTargetHealthAbility,
                           FuryFromTheDelveAttackOrPinAbility}, (
        "les DEUX bras de l'`op_BitwiseOr` doivent etre inscrits : sans le bras PreUnitAbility la "
        "cle persistante n'est jamais ecrite, `GetPersistentDataFormula$$Calculate` rend "
        "`default(T)` = 0, et le bras NormalAttack part TOUJOURS en attaque supplementaire ; "
        "lu : %r" % [c.__name__ for c in entree])


def test_les_deux_bras_ecoutent_les_bons_vecteurs():
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.loki.fury_from_the_delve import (
        FuryFromTheDelveAttackOrPinAbility, FuryFromTheDelveCheckTargetHealthAbility)

    assert (FuryFromTheDelveCheckTargetHealthAbility.event_id
            == int(EventTriggerType.PreUnitAbility))
    assert FuryFromTheDelveAttackOrPinAbility.event_id == int(EventTriggerType.NormalAttack)


def test_le_passif_n_entre_pas_dans_les_registres_des_ACTIVES():
    """Piege de namespace (#961/#958, les deux sens) : `TARGETING_OPTIONS` et `ABILITY_ATTACK_TYPE`
    sont indexes par `ActiveAbilityType`. Y inscrire une `TriggeredAbilityType` ecrirait un masque
    sur une AUTRE ability -- l'ordinal 1528 existe dans les deux espaces."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.entities.triggered_ability_type import TriggeredAbilityType

    assert int(TriggeredAbilityType.FuryFromTheDelve) not in ABILITY_CLASSES, (
        "1528 est entre dans `ABILITY_CLASSES`, qui est keye par `ActiveAbilityType` : ce n'est "
        "pas le meme objet")


# --------------------------------------------------------------------- 3. CONSTANTES GAMECONFIG
def test_constantes_du_gameconfig():
    """Les quatre constantes que le port LIT, figees a la valeur mesuree. `GetNumberConstant` (et
    non `GetVariableForLevel`) : elles vivent dans `constants`, donc hors indexation par niveau."""
    import gameconfig as GC
    from engine.entities.damage_profile_type import DamageProfileType

    a = GC.ability(FURY) or {}
    cst = a.get("constants") or {}
    assert int(cst.get("hpPct")) == 50, "hpPct lu = %r" % cst.get("hpPct")
    assert int(cst.get("nrOfRounds")) == 1, "nrOfRounds lu = %r" % cst.get("nrOfRounds")
    assert int(cst.get("nrOfHits")) == 2, "nrOfHits lu = %r" % cst.get("nrOfHits")
    assert cst.get("damageProfile") == DamageProfileType.Eviscerate.name, (
        "damageProfile lu = %r -- le port le CITE, il ne le deduit pas du nom de l'ability"
        % cst.get("damageProfile"))
    assert a.get("attackRangeType") == "Melee"
    v = a.get("variables") or {}
    assert "minDmg" in v and "maxDmg" in v, "MinMaxDamage(abilityState) n'aurait pas de bornes"


def test_le_porteur_est_bien_celui_du_kit():
    """`votanBeserk` porte `FuryFromTheDelve` en `passiveAbilities` -- le couple (unite, passif) est
    le seul point de depart certain, et il se RE-DERIVE du gameconfig."""
    import gameconfig as GC
    u = GC.unit("votanBeserk") or {}
    assert FURY in (u.get("passiveAbilities") or []), (
        "votanBeserk ne porte plus %s : la cle du registre est le NOM gameconfig, donc l'entree "
        "deviendrait morte en silence" % FURY)


# --------------------------------------------------------------------- 4. POLARITE DU FLAG
_CAS = [
    # (pv_courants, pv_max, hpPct, attendu) -- `AmountIsGreater` est STRICT.
    (100, 100, 50, True),        # cible intacte
    (51, 100, 50, True),         # juste au-dessus du seuil
    (50, 100, 50, False),        # PILE au seuil -> FAUX (comparaison stricte)
    (49, 100, 50, False),        # sous le seuil
    (1, 100, 50, False),
]


@pytest.mark.parametrize("hp,mx,pct,attendu", _CAS)
def test_polarite_du_seuil(hp, mx, pct, attendu):
    """`AmountIsGreater( StatAmount(Target, Health, Current),
                         PercentageOf( StatAmount(Target, Health, Maximum), hpPct ) )`.

    Le cas `hp == pct % de mx` est le SEUL qui distingue `>` de `>=`, et c'est celui qu'une
    relecture distraite inverse. Il vaut FAUX -- donc une cible pile a la moitie recoit l'ATTAQUE
    supplementaire, pas le `Pinned`."""
    from engine.dsl.base import DslContext
    from engine.runner.operations.triggers.loki.fury_from_the_delve import (
        target_health_above_threshold_trigger)
    from engine.entities.stats import StatPart

    cible = {"id": 7}

    def get_stat(unit, stat_type, variant=0, level=None):
        assert (unit or {}).get("id") == 7, "la formule doit lire la CIBLE, pas une autre unite"
        return hp if int(variant) == int(StatPart.CURRENT) else mx

    ctx = DslContext(units=[cible], target=cible, caster={"id": 1}, get_stat=get_stat)
    assert bool(target_health_above_threshold_trigger(pct).should_trigger(ctx)) is attendu


def test_la_formule_lit_bien_les_DEUX_parts():
    """Contre-epreuve de `statpart_confondus` (le mutant du probe) : si les deux `StatAmount`
    lisaient la MEME part, le predicat deviendrait `PV > PV x pct%`, donc TOUJOURS vrai pour
    `pct < 100` -- et l'attaque supplementaire ne partirait JAMAIS. On verifie que les deux parts
    sont REELLEMENT demandees."""
    from engine.dsl.base import DslContext
    from engine.runner.operations.triggers.loki.fury_from_the_delve import (
        target_health_above_threshold_trigger)
    from engine.entities.stats import StatPart

    vues = []

    def get_stat(unit, stat_type, variant=0, level=None):
        vues.append(int(variant))
        return 40 if int(variant) == int(StatPart.CURRENT) else 100

    cible = {"id": 7}
    ctx = DslContext(units=[cible], target=cible, caster={"id": 1}, get_stat=get_stat)
    target_health_above_threshold_trigger(50).should_trigger(ctx)
    assert int(StatPart.CURRENT) in vues and int(StatPart.MAXIMUM) in vues, (
        "les deux `StatPart` ne sont pas lues (vues : %r) -- le seuil serait calcule sur la "
        "mauvaise reference" % vues)


# --------------------------------------------------------------------- 5. LES DEUX FEUILLES
def test_la_feuille_pinned_pose_la_source_OWNER():
    """La surcharge native appelee est celle a SIX parametres, donc le selecteur SOURCE est
    EXPLICITE et vaut `Owner@+0x30`. `SpecialIssueCombiMelta_AddEffectAbility` pose le MEME effet
    1065 par la surcharge a CINQ (source NULLE -> la source EST la cible) : recopier ce voisin de
    forme aurait ecrit la mauvaise source."""
    from engine.entities.effect_type import EffectType
    from engine.runner.operations.triggers.loki.fury_from_the_delve import (
        fury_from_the_delve_pinned_tree)

    n = fury_from_the_delve_pinned_tree(1)
    assert n.effect_type == int(EffectType.Pinned)
    assert n.source_from_target is False, (
        "`source_from_target` est VRAI : ce serait la surcharge a CINQ parametres, celle de "
        "`SpecialIssueCombiMelta`, pas celle de ce kit")
    assert n.duration_rounds == 1, (
        "la duree vient de `TurnsFromRounds(GetNumberConstant(nrOfRounds))`, pas du defaut de "
        "l'effet -- `duration_rounds=None` signifierait `DefaultAmountOfRounds(0x429)`")


def test_la_feuille_attaque_cite_le_bon_volet_de_degat():
    """`MinMaxDamage(abilityState)` / `GetDamageProfile()` / `GetHits()` = le volet PRINCIPAL
    (`minDmg`/`maxDmg`/`damageProfile`/`nrOfHits`), jamais le volet `_2`."""
    from engine.entities.ability_constant_type import AbilityConstantType
    from engine.entities.ability_variable_type import AbilityVariableType
    from engine.entities.damage_profile_type import DamageProfileType
    from engine.runner.operations.triggers.loki.fury_from_the_delve import (
        fury_from_the_delve_attack_tree)

    n = fury_from_the_delve_attack_tree()
    assert n.min_key == AbilityVariableType.minDmg.name
    assert n.max_key == AbilityVariableType.maxDmg.name
    assert n.hits_key == AbilityConstantType.nrOfHits.name
    assert n.profile == DamageProfileType.Eviscerate.name
    assert n.level_slot == "passive", (
        "`FuryFromTheDelve` est un PASSIF : sa config se resout au niveau des passives du porteur")


def test_la_cle_persistante_est_composite():
    """La cle offline mirror la cle composite native `(GetPersistentDataId(abilityOrEffect),
    dataKey)`. Le `dataKey` est le literal `TARGET_HEALTH_ABOVE_HALF` LU dans
    `metadata/string_literals.tsv` -- il n'est ni invente ni deduit du sens."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.runner.operations.triggers.loki.fury_from_the_delve import FURY_PERSISTENT_KEY

    assert FURY_PERSISTENT_KEY == (int(TriggeredAbilityType.FuryFromTheDelve),
                                   "TARGET_HEALTH_ABOVE_HALF")
