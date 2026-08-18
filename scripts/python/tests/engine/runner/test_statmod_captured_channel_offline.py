"""case-366-r1-statmod -- GARDE du canal `StatModifierComponent` CAPTE, et de son PERIMETRE.

LE FAIT NATIF. `IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat` retourne
litteralement `StatModifierComponent+0x10` et
`IdunBattle.Entities.Effects.StaticStatModifierEffect$$GetStatModificationAmount` litteralement
`+0x14` : le stat ET la magnitude sont RELUS, pas recalcules. Le capteur publie ce composant champ
par champ sous ses noms natifs (`frida/hooks/game/effects.ts::readStatModifier`), donc le port peut
LIRE ce que le natif lit.

POURQUOI C'EST OBLIGATOIRE POUR CERTAINES CLASSES, et pour elles seules. Les TROIS surcharges
`IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect` construisent
`IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$.ctor` avec **source = NULL**, et
`...$$Execute` retombe alors sur l'ENTITE-CIBLE (`lVar9 = <target>; if (sourceSelectionne != 0)
lVar9 = <source>;`). Sur une pose qui vise autre chose que l'Owner, `EffectComponent.SourceUnit`
designe donc le PORTEUR -- et toute magnitude re-derivee d'un `AbilityState` lit la MAUVAISE unite.
Les DEUX `...$$AddStaticStatModifierEffectToOwner` passent `Owner@DSLSelectors+0x30` en source ET en
cibles : pour elles porteur == poseur, la re-derivation reste exacte.

Ce fichier garde les DEUX bouts :
  * le canal lui-meme (priorite, repli, gate `IsDynamic`, champ `StatType`) ;
  * le RECENSEMENT (`probe_366r1_statmod_rederivation_census.py --check`), qui est le cliquet du
    gisement : il n'est alimente que par NOTRE cadence de portage.

100 % offline. Le FAIT confronte au natif (`SourceUnit` = le porteur, `Amount` = celui du poseur)
l'est par `probe_366r1_statmod_captured_channel.py` / `test_statmod_captured_channel_live.py`.
"""
from __future__ import annotations

import pytest

import probe_366r1_statmod_rederivation_census as CENSUS
from engine.entities.effects.factory import EffectFactory
from engine.entities.effects.magnitude import ability_var

STORM_OF_FIRE = 1171                      # 0x493 SereneUnifierStormOfFire
SHOCK_ASSAULT_BUFF = 1000                 # 0x3e8 ShockAssault_Buff

# MESURE LIVE du 2026-08-01 (MC1_67 / 3711, `--unit-stat "tauCrisis:PassiveAbilityLevel=20"`) :
# le natif ecrit le MEME `Amount` sur les DEUX porteurs -- celui d'Aun'Shi (L50 x 180 %).
NATIVE_AMOUNT = 797
CARRIER_LEVEL, CARRIER_MULT = 20, 180     # l'ALLIE, dissocie -> re-derivation = 76


def _cap(name, effect_type, carrier_id, stat_mod=None):
    """Capture d'un effet tel que `decisionView.effects` la publie. `source` == le PORTEUR : c'est
    exactement ce que le natif ecrit quand la feuille de pose passe `source = null` (MESURE : sur
    `tauCrisis` u83, `EffectComponent.SourceUnit` vaut 83, pas l'id d'Aun'Shi)."""
    c = {"name": name, "effectType": effect_type, "level": 1, "remaining": 1, "source": carrier_id}
    if stat_mod is not None:
        c["statMod"] = stat_mod
    return c


def _sm(amount=NATIVE_AMOUNT, stat=0, dynamic=0):
    return {"StatType": stat, "Amount": amount, "ApplyCounter": 1,
            "IsDynamic": dynamic, "IsHidden": 0}


def _derived():
    """La re-derivation gameconfig depuis l'`AbilityState` DU PORTEUR -- le modele que le canal
    remplace en regime cross-unite."""
    v = ability_var("SereneUnifier", "extraDmg", CARRIER_LEVEL, multiplier_pct=CARRIER_MULT)
    assert v, "SereneUnifier.extraDmg non resoluble en gameconfig -> scenario vide"
    return int(v)


# --------------------------------------------------------------------------------------------------
# 1171 -- la bascule de ce cas
# --------------------------------------------------------------------------------------------------

def test_storm_of_fire_prefers_the_captured_native_amount():
    """LE CRITERE. Sur un ALLIE, `captured["source"]` designe l'allie lui-meme : la re-derivation
    lirait SON niveau et SON multiplier. MESURE LIVE : natif 797, re-derivation 76 -- un facteur 10,
    et 721 points d'ATTACK qui restaient collees a l'expiration."""
    derived = _derived()
    assert derived != NATIVE_AMOUNT, \
        "montage non discriminant : le repli donnerait deja %d" % NATIVE_AMOUNT
    eff = EffectFactory.create(_cap("SereneUnifierStormOfFire", STORM_OF_FIRE, 83, _sm()),
                               CARRIER_MULT, CARRIER_LEVEL, 50)
    assert eff.get_stat_modification_amount() == NATIVE_AMOUNT, (
        "magnitude RE-DERIVEE (%s) au lieu du `statMod.Amount` natif (%d) -- c'est l'ecart mesure "
        "live (76 au lieu de 797)" % (eff.get_stat_modification_amount(), NATIVE_AMOUNT))
    assert eff.captured_stat_mod_amount() == NATIVE_AMOUNT


def test_storm_of_fire_falls_back_to_the_derivation_without_the_channel():
    """LE REPLI, quand la capture ne publie pas `statMod` (pose OFFLINE, capture anterieure au
    capteur) : `ConfigVar(8 = extraDmg)` indexe par le slot PASSIF. EXACT sur Aun'Shi lui-meme
    (source == porteur), APPROCHE sur un allie -- sous-attribution absorbee par le residu opaque."""
    eff = EffectFactory.create(_cap("SereneUnifierStormOfFire", STORM_OF_FIRE, 83),
                               CARRIER_MULT, CARRIER_LEVEL, 50)
    assert eff.stat_mod is None, "ce montage doit exercer le REPLI (pas de statMod capte)"
    assert eff.get_stat_modification_amount() == _derived(), (
        "le repli ne suit plus `ConfigVar(8)` indexe par le slot PASSIF : %s"
        % (eff.get_stat_modification_amount(),))


def test_storm_of_fire_fallback_reads_the_PASSIVE_slot():
    """`SereneUnifier` est un PASSIF (`TriggeredAbilityType` 0x479 = 1145) : le repli doit indexer
    `PassiveAbilityLevel`, jamais l'actif. Invisible en runner normalise (les deux slots y valent
    50) -- on les DISSOCIE."""
    eff = EffectFactory.create(_cap("SereneUnifierStormOfFire", STORM_OF_FIRE, 83),
                               CARRIER_MULT, CARRIER_LEVEL, 50)
    assert eff.active_ability_level == 50 and eff.ability_level == CARRIER_LEVEL
    assert eff.get_stat_modification_amount() == _derived(), \
        "la magnitude suit l'ACTIF alors que SereneUnifier est un PASSIF"


# --------------------------------------------------------------------------------------------------
# Le canal lui-meme : `StatType` (+0x10) et le gate `IsDynamic`
# --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,effect_type", [
    ("SereneUnifierStormOfFire", STORM_OF_FIRE),
    ("ShockAssault_Buff", SHOCK_ASSAULT_BUFF),
])
def test_stat_type_is_read_from_the_component_with_a_literal_fallback(name, effect_type):
    """`AStatModifierEffect$$GetStatModificationStat` = `+0x10`. Les DEUX classes le LISENT, avec
    repli sur le litteral de leur feuille de pose (`0 = ATTACK` pour les deux -- MESURE :
    `StatType = 0`). Le repli DOIT rendre la meme valeur : un canal absent ne change rien."""
    with_ch = EffectFactory.create(_cap(name, effect_type, 83, _sm(stat=0)), 180, 50, 50)
    without = EffectFactory.create(_cap(name, effect_type, 83), 180, 50, 50)
    assert with_ch.get_stat_modification_stat() == 0
    assert without.get_stat_modification_stat() == 0
    assert with_ch.captured_stat_mod_stat() == 0 and without.captured_stat_mod_stat() is None


def test_dynamic_component_is_never_read_as_a_static_amount():
    """GATE `IsDynamic` -- c'est le DISPATCH NATIF. Seul `StaticStatModifierEffect$$
    GetStatModificationAmount` relit `+0x14` ; `ADynamicStatModifierEffect$$GetStatModificationAmount`
    appelle son slot `+0x798` et RECALCULE. Les surcharges `AddDynamicStatModifierEffect*` ne passent
    aucun `amount` -> `AddStatModifierEffectBehaviour$$Execute` ecrit **0** dans le composant. Lire ce
    0 serait pire qu'une derivation approchee : l'accesseur doit rendre `None` et laisser le repli."""
    eff = EffectFactory.create(
        _cap("SereneUnifierStormOfFire", STORM_OF_FIRE, 83, _sm(amount=0, dynamic=1)),
        CARRIER_MULT, CARRIER_LEVEL, 50)
    assert eff.captured_stat_mod_amount() is None, \
        "le canal DYNAMIQUE est lu comme une magnitude statique -> 0 au lieu du repli"
    assert eff.get_stat_modification_amount() == _derived()


# --------------------------------------------------------------------------------------------------
# LE CLIQUET du gisement
# --------------------------------------------------------------------------------------------------

def test_no_unclassified_ability_state_rederivation_in_the_registry():
    """RECENSEMENT, re-derive du code a chaque run (jamais un compte recopie).

    Toute classe du registre dont la magnitude BOUGE avec l'`AbilityState` du porteur et qui ne lit
    pas le canal capte doit avoir sa feuille de pose CLASSEE (`OWNER` / `SRC` / `CROSS`) dans
    `probe_366r1_statmod_rederivation_census.POSE_TARGETS`. Sans cette classification, une classe
    posee cross-unite rouvre en silence le trou de `1000` et `1171` : ni erreur, ni crash, juste une
    magnitude fausse et un residu opaque non retirable.

    ⚠ ANTI-VACUITE (#10029). `assert not bad` passe VERT sur un recensement VIDE -- registre ampute,
    import casse, filtre du recenseur devenu trop etroit : le cliquet se tairait exactement quand il
    devrait crier. Le cran est un INVARIANT, pas un seuil : **toute** entree de `POSE_TARGETS` doit
    s'apparier a une ligne du recensement. Une classe retiree d'`EFFECT_CLASSES` (ou renommee) laisse
    alors une entree ORPHELINE, et un recenseur devenu muet les rend TOUTES orphelines -- les deux
    regimes rougissent ici, sans qu'aucun chiffre arbitraire soit ecrit."""
    rows = CENSUS.census()
    vus = {r["name"] for r in rows}
    orphelines = sorted(set(CENSUS.POSE_TARGETS) - vus)
    assert not orphelines, (
        "%d entree(s) de POSE_TARGETS ne s'apparient a AUCUNE ligne du recensement (%s) : la classe "
        "a disparu du registre, ou le recenseur ne visite plus le gisement -- dans les deux cas "
        "`not bad` ci-dessous serait un vert VACANT (recensement = %d lignes)"
        % (len(orphelines), orphelines, len(rows)))
    bad = CENSUS.offenders(rows)
    assert not bad, (
        "%d classe(s) re-derivent une magnitude ability-state SANS canal capte NI classification de "
        "leur feuille de pose : %s -- lire le `CreateBehaviour` du poseur et l'inscrire dans "
        "POSE_TARGETS (OWNER si `AddStat*StatModifierEffectToOwner`/`(Owner@+0x30)`, CROSS sinon, et "
        "dans ce cas BASCULER la classe sur `captured_stat_mod_amount()`)"
        % (len(bad), [r["name"] for r in bad]))


def test_every_cross_unit_class_reads_the_captured_channel():
    """La NON-REGRESSION de ce cas : une classe classee `CROSS` qui perdrait sa lecture du canal
    redeviendrait fausse hors de son poseur, sans qu'aucun test de magnitude ne rougisse (le regime
    NOMINAL est DEGENERE -- `buildNormalizedBC` met tous les niveaux a `targetAbilityLevel`)."""
    rows = CENSUS.census()
    cross = [r for r in rows if r["kind"] == "CROSS"]
    assert cross, "aucune classe CROSS recensee -- le cliquet ne garde plus rien"
    assert not CENSUS.cross_without_channel(rows), (
        "classe(s) CROSS sans lecture du canal capte : %s"
        % ([r["name"] for r in CENSUS.cross_without_channel(rows)],))
