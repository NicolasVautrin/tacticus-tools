"""CLIQUET de l'axe DEGAT de `DefenderOfTheGreaterGood` (#420-r1) -- `1182 ..._ExtraDmg`
(`tauShadowsun`) et son jumeau drone `1306`.

POURQUOI CE FICHIER EXISTE : l'axe COUPS (`1183`) a son cliquet depuis #372
(`test_dotgg_extra_hits_live.py`) ; l'axe DEGAT n'en avait AUCUN. Or #420 vient d'y REVEILLER un
gate : `damage_profile` n'etait pas threade jusqu'aux modifiers ATTAQUANT, la cle etait ABSENTE, et
`!DamageProfileIs(Psychic)` ne fermait donc JAMAIS -- le port accordait le bonus meme sur une attaque
Psychic. Le threading corrige cette SUR-application ; rien ne la retenait.

L'ARTEFACT NATIF, relu au decompile (build `rnca9r7q6c`) :

    IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraDmgEffect$$CreateDamageModifier
      trigger = get_OwnerIsCaster & IsRangedAttack() & !DamageProfileIs(0xd = Psychic)
      amount  = ConfigVar(8 = extraDmg, GetAbilityState(effet), config = effet+0x60)

Le `ForAddition` est INLINE (aucun `call`) : on le lit a la DISPOSITION des champs. Le corps ecrit
`trigger` a `+0x00`, `0` a `+0x08`, `amount` a `+0x10` ;
`IdunBattle.Entities.Effects.EffectBonus$$ForAddition` ecrit son montant a `+0x10`,
`IdunBattle.Entities.Effects.EffectBonus$$ForPercentIncrease` a `+0x08`. C'est donc bien le canal
ADDITIF, celui de `SpotterReworked_ExtraDamage` / `LordOfTheHost_ExtraDamage`. La surcharge de
`DamageProfileIs` retenue est celle a UN scalaire, et `IsRangedAttack` celle SANS ability (les deux
tranchees par l'adresse du `call`, pas par le nom).

LE SELECTEUR (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector`) :

    sel = AdjacentFriends(dsl, Owner, ownerTiles, unique = 1) - Owner
    sel = Unique( sel + UnitsFromFaction(SurroundingFriends(dsl, Owner, ownerTiles, range = 2,
                                                            unique = 1, selectionType = 3), 9 = Tau, 3) )
    sel = UnitsWithRangedWeaponsExcludingDamageProfile(dsl, sel, 0xd = Psychic)
    if isDrone: sel = EntitiesIsNotTargetOfEffect(dsl, sel, int[]{ 0x49e = 1182 })

⚠ LES LITTERAUX NE SONT PAS TOUS DES RAYONS (piege #419) :
`IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(this, unit, unitTile, unique)` n'a AUCUN
parametre de rayon -- le `1` du call-site est `unique`, l'adjacence vient d'`AdjacentTiles`. En
revanche `IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends(this, unit, unitTile, range,
unique, unitSelectionType)` en a un, et le call-site y passe bien `range = 2` (puis `unique = 1`,
`selectionType = 3`). Les deux tiers du selecteur sont donc : d = 1 TOUTE faction, et d <= 2 T'au
SEULEMENT.

Le filtre CARRIER `UnitsWithRangedWeaponsExcludingDamageProfile` monte un
`IdunBattle.Entities.Selectors.UnitsWithWeaponsSelector` avec `minRange = 2` et
`excludedDamageProfile = Psychic` ; `...$$HasMatchingWeapon` exige qu'UNE MEME arme satisfasse les
deux. Il n'est PAS porte : il est SUBSUME par le gate d'attaque (`is_ranged & profil != Psychic`)
sur toute attaque d'ARME. Residu nomme : une attaque « ranged » d'une unite SANS arme de portee >= 2
serait accordee par le port et refusee par le natif.

CE QUE LES BRAS LIVE MESURENT -- chaque bras rend TROIS series sur le MEME etat :
`live` (evenements natifs), `offline` (rejeu du port), et `no_aura` (MEME rejeu, l'effet 1182 RETIRE
du porteur). `no_aura` est la CONTRE-EPREUVE DE SENSIBILITE : elle repond a « la mesure discrimine-
t-elle seulement ? ». Sans elle, deux absences se comparent et le vert ne prouve rien.

MESURES DE REFERENCE (`probe_420r1_dotgg_extra_dmg.py`, MC1_67/777, ablvl 50 x mult 180) :

  * `darkaHellblaster` ADJACENT : live = offline = [6930, 7105] ; no_aura = [6306, 6481]
    -> delta CONSTANT +624 par COUP. Sur ce montage l'armure de la cible est NULLE (`--hp-target`
       met `Armor`/`FixedArmor` a 0), donc l'etage percage n'y est pas exerce : ce que la mesure
       etablit est que l'apport est ADDITIF et PAR COUP, et qu'il vaut `extraDmg[50] x 1.8 = 499`
       porte par le x1,25 aval du beneficiaire (round(623,75) = 624). L'ordre exact
       additif/percage n'est PAS tranche ici -- il faudrait une armure non nulle.
  * `ultraTigurius` ADJACENT (arme ranged Psychic, `DamageProfileType = 13` lu au tag natif) :
    live = offline = no_aura = [3336] -> delta 0. MEME geometrie, SEUL le profil change.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

import hexgeo

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _dotgg_aura_regime import (ADJACENT, CARRIER, FAR, RING2_NON_TAU,       # noqa: E402,F401
                                RING2_TAU, dotgg_aura_regime)

from engine.entities.effects.factory import EFFECT_CLASSES                   # noqa: E402
from engine.entities.effects.magnitude import ability_var                    # noqa: E402
from engine.entities.effects.loki.extra_damage_aura import (
    DefenderOfTheGreaterGoodExtraDmgDroneEffect, DefenderOfTheGreaterGoodExtraDmgEffect
)  # noqa: E402

_EFFECT_NAME = "DefenderOfTheGreaterGood_ExtraDmg"
_BENEF_NON_TAU = "darkaHellblaster"     # Imperial, arme RANGED non-Psychic -> tier ADJACENT
_BENEF_TAU = "tauCrisis"                # T'au, arme RANGED -> tier `UnitsFromFaction(9)` du ring 2
_BENEF_PSYKER = "ultraTigurius"         # melee Physical + RANGED **Psychic** (r2) -> bascule profil
_PSYKER_TGT_DIST = (2, 2)               # son arme ranged porte a 2 : d = 3 ferait REFUSER l'attaque


# --------------------------------------------------------------------- gardes STRUCTURELLES (offline)

def _eff(cls=DefenderOfTheGreaterGoodExtraDmgEffect, effect_type=1182,
         ability_level=50, multiplier=100):
    e = cls(name=_EFFECT_NAME, effect_type=effect_type, level=1, ability_level=ability_level)
    e.ability_variables_multiplier = multiplier
    return e


def _ctx(**over):
    """Contexte AURA nominal : beneficiaire non-T'au ADJACENT au porteur, coup RANGED non-Psychic.
    C'est le seul regime ou le bonus existe -- chaque garde n'en bouge QU'UNE cle."""
    base = {"owner_id": 1, "owner_pos": (0, 4), "owner_team": 1,
            "att_id": 2, "att_team": 1, "att_pos": (0, 3), "att_faction": "AstraMilitarum",
            "is_melee": False, "damage_profile": "Bolter"}
    base.update(over)
    return base


def test_registry_carries_both_damage_effect_types():
    """Les DEUX `EffectType` du canal DEGAT sont au registre, et le jumeau drone est bien la
    sous-classe `isDrone` -- pas une classe inventee.

    Le natif n'a qu'UNE classe pour `1182` et `1306` :
    `IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraDmgEffect$$.ctor(this, isDrone)`
    ecrit `isDrone` a `this+0x480` apres
    `IdunBattle.Entities.Effects.DamageModifierAbilityEffect$$.ctor(this, 0x483 = 1155, 0)`."""
    assert EFFECT_CLASSES.get(_EFFECT_NAME) is DefenderOfTheGreaterGoodExtraDmgEffect
    assert (EFFECT_CLASSES.get("DefenderOfTheGreaterGood_ExtraDmgDrone")
            is DefenderOfTheGreaterGoodExtraDmgDroneEffect)
    assert issubclass(DefenderOfTheGreaterGoodExtraDmgDroneEffect,
                      DefenderOfTheGreaterGoodExtraDmgEffect)
    assert DefenderOfTheGreaterGoodExtraDmgDroneEffect._IS_DRONE is True
    assert DefenderOfTheGreaterGoodExtraDmgEffect._IS_DRONE is False
    # `EntitiesIsNotTargetOfEffect` vise l'effet NON-drone `0x49e = 1182`, littéral du call-site de
    # `..._ExtraDmgEffect$$CreateTargetSelector` (le meme corps sert 1182 ET 1306).
    assert DefenderOfTheGreaterGoodExtraDmgEffect._SOURCE_EFFECT_TYPE == 1182


def test_damage_profile_gate_polarity_offline():
    """`!DamageProfileIs(0xd = Psychic)` -- POLARITE : le bonus existe partout SAUF sur un coup
    Psychic. C'est le gate que #420 vient de reveiller, et que rien ne retenait.

    La cle ABSENTE laisse le gate OUVERT (le natif compare a `13` ; un contexte sans profil vaut
    `DamageProfileType.None_ = -1`, hors egalite) -- contrairement au gate `IsRangedAttack`,
    tri-etat, qui se TAIT (test suivant). Les deux ne se deduisent pas l'un de l'autre."""
    e = _eff()
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx()) is not None, \
        "profil non-Psychic : le bonus doit mordre"
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx(damage_profile="Psychic")) is None, \
        "!DamageProfileIs(0xd = Psychic) : aucun bonus sur un coup Psychic"
    for prof in ("Bolter", "Melta", "Blast", "Plasma", "Flame", "Pulse", "Physical"):
        assert e.create_aura_attack_damage_bonus_for_ally(
            _ctx(damage_profile=prof)) is not None, \
            "seul Psychic est exclu ; %s doit garder le bonus" % prof
    assert e.create_aura_attack_damage_bonus_for_ally(
        _ctx(damage_profile=None)) is not None, \
        "profil ABSENT -> le gate de PROFIL reste ouvert (le natif compare a 13, pas a `defini`)"


def test_ranged_gate_is_tristate_offline():
    """`IsRangedAttack()` -- gate TRI-ETAT, calque de `SpotterReworked_ExtraDamage._trigger_ok` :
    seul `is_melee is False` ouvre. `True` ferme (coup de melee), `None` ferme AUSSI (nature du coup
    non declaree -> le port ne devine pas).

    ⚠ Corollaire de mesure (#422) : RETIRER la cle d'un gate tri-etat le FERME. Pour eprouver ce
    gate il faut FORCER `is_melee`, jamais le supprimer."""
    e = _eff()
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx(is_melee=False)) is not None
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx(is_melee=True)) is None, \
        "IsRangedAttack : un coup de MELEE n'a jamais le bonus"
    c = _ctx()
    c.pop("is_melee")
    assert e.create_aura_attack_damage_bonus_for_ally(c) is None, \
        "TRI-ETAT : nature non declaree -> le gate se tait (il ne s'ouvre PAS)"
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx(is_melee=None)) is None


def test_selector_two_tiers_offline():
    """Le selecteur a DEUX tiers, et le port les separe : `AdjacentFriends` (d = 1, TOUTE faction)
    et `UnitsFromFaction(SurroundingFriends(range = 2), 9 = Tau)` (d <= 2, T'au SEULEMENT).

    Un port qui lirait le `1` d'`AdjacentFriends` comme un RAYON et le `2` de `SurroundingFriends`
    comme autre chose confondrait ces deux tiers (piege #419)."""
    e = _eff()
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx()) is not None, \
        "d = 1 non-T'au : DANS le selecteur (`AdjacentFriends`, toute faction)"
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx(att_pos=(0, 2))) is None, \
        "d = 2 NON-T'au : `UnitsFromFaction(9 = Tau)` filtre le ring 2"
    assert e.create_aura_attack_damage_bonus_for_ally(
        _ctx(att_pos=(0, 2), att_faction="Tau")) is not None, "d = 2 T'au : DANS le selecteur"
    assert e.create_aura_attack_damage_bonus_for_ally(
        _ctx(att_pos=(0, 3), att_faction="Tau")) is not None, "d = 1 T'au : DANS le selecteur aussi"
    assert e.create_aura_attack_damage_bonus_for_ally(
        _ctx(att_pos=(0, 1), att_faction="Tau")) is None, "d = 3 T'au : HORS (range = 2)"
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx(att_id=1)) is None, \
        "`sel - Owner` : le porteur ne se bonifie pas lui-meme"
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx(att_team=2)) is None, \
        "Adjacent/SurroundingFRIENDS : un ennemi n'est jamais dans le selecteur"


def test_magnitude_is_extra_dmg_at_the_carrier_passive_level_offline():
    """`ConfigVar(8 = extraDmg, GetAbilityState(effet), config = effet+0x60)` -- la magnitude est
    indexee sur le niveau du PASSIF DU PORTEUR (`ability_level`), pas sur `level` (qui est
    l'`EffectLevel`), et scalee par le multiplier de rarete du porteur.

    `extraDmg` est la SEULE variable de l'ability, et elle EST dans son
    `variablesAffectedByRarityBonus` -- le multiplier s'y applique donc (contrairement a
    `PsychicStalk.extraDmgPct`, qui n'y est pas)."""
    for lvl in (1, 30, 50, 65):
        for mult in (100, 180):
            want = ability_var("DefenderOfTheGreaterGood", "extraDmg", lvl, multiplier_pct=mult)
            got = _eff(ability_level=lvl, multiplier=mult).create_aura_attack_damage_bonus_for_ally(
                _ctx())
            assert got is not None and got.kind == "Addition" and got.value == want, (
                "extraDmg[%d] x %d%% : attendu Addition/%s, obtenu %s" % (lvl, mult, want, got))
    # le multiplier MORD (sinon les deux regimes ci-dessus ne discrimineraient rien)
    assert (ability_var("DefenderOfTheGreaterGood", "extraDmg", 50, multiplier_pct=180)
            != ability_var("DefenderOfTheGreaterGood", "extraDmg", 50, multiplier_pct=100))
    # `level` (EffectLevel) ne doit RIEN changer : ce n'est pas lui que `ConfigVar` lit.
    a, b = _eff(), _eff()
    b.level = 7
    assert (a.create_aura_attack_damage_bonus_for_ally(_ctx()).value
            == b.create_aura_attack_damage_bonus_for_ally(_ctx()).value), \
        "la magnitude ne doit pas dependre de l'EffectLevel"
    # `GetAbilityState` sans etat -> AUCUNE contribution (on n'invente pas de niveau)
    assert _eff(ability_level=None).create_aura_attack_damage_bonus_for_ally(_ctx()) is None


def test_drone_does_not_double_count_offline():
    """`EntitiesIsNotTargetOfEffect(sel, int[]{0x49e = 1182})` -- branche `isDrone` du selecteur, sur
    le canal DEGAT (le cliquet #372 ne la gardait que sur le canal COUPS).

    Sans elle, une unite couverte par l'aura de Shadowsun ET par celle du drone prendrait DEUX fois
    `extraDmg`."""
    src = _eff()                                                        # 1182 sur Shadowsun (id 1)
    drone = _eff(DefenderOfTheGreaterGoodExtraDmgDroneEffect, 1306)     # 1306 sur le drone (id 3)
    peers = [(1, (0, 4), 1, [src]), (3, (0, 2), 1, [drone])]
    c = _ctx(owner_id=3, owner_pos=(0, 2), aura_peers=peers)
    assert src.create_aura_attack_damage_bonus_for_ally(
        {**c, "owner_id": 1, "owner_pos": (0, 4)}) is not None, \
        "controle : la classe SOURCE accorde bien sur cette geometrie"
    assert drone.create_aura_attack_damage_bonus_for_ally(c) is None, \
        "l'attaquant est deja cible de l'effet 1182 de Shadowsun -> le drone n'ajoute RIEN"
    c2 = _ctx(owner_id=3, owner_pos=(0, 2), att_pos=(0, 1), aura_peers=peers)
    assert drone.create_aura_attack_damage_bonus_for_ally(c2) is not None, \
        "hors de l'aura de Shadowsun, le drone accorde bien son degat"
    # le gate de PROFIL vaut pour le drone aussi (meme corps natif)
    assert drone.create_aura_attack_damage_bonus_for_ally(
        {**c2, "damage_profile": "Psychic"}) is None


# --------------------------------------------------------------------- confrontation LIVE

@pytest.fixture(scope="module")
def shadowsun_geometry(dotgg_aura_regime):
    """UN runner pour les TROIS regimes de geometrie : il embarque le beneficiaire non-T'au ET le
    T'au (`arrange` ecarte a d >= 5 celui qui ne joue pas)."""
    return dotgg_aura_regime(benef=_BENEF_NON_TAU, p_extra=(_BENEF_TAU,))


@pytest.fixture(scope="module")
def shadowsun_psyker(dotgg_aura_regime):
    """La BASCULE PSYCHIC -- `ultraTigurius` : melee Physical, RANGED **Psychic** (r2). AUTRE seed
    (31337) : le verdict ne doit pas tenir a une bataille."""
    return dotgg_aura_regime(benef=_BENEF_PSYKER, seed="31337")


def _run(h, regime, benef, tgt_dist=(2, 3)):
    """Joue le regime et rend `(rec, offline, offline_sans_l_aura)`.

    Un montage qui n'aboutit pas ASSERTE (jamais un skip vert) : sans geometrie il n'y a pas de
    mesure, donc pas de verdict."""
    rec = h.run(benef, regime, tgt_dist=tgt_dist)
    if rec is None:
        pytest.fail("montage dotgg NON INSTALLE (regime %s, benef %s)" % (regime, benef),
                    pytrace=False)
    if not rec["live_ok"] or not rec["live_per_hit"]:
        pytest.fail("attaque normale live refusee/vide (%s, %s) -- ce rouge accuse le MONTAGE"
                    % (regime, benef), pytrace=False)
    off = h.replay_offline(rec)
    no_aura = h.replay_offline(rec, drop_carrier_effects=(_EFFECT_NAME,))
    assert _EFFECT_NAME in (off["carrier_effects"] or []), (
        "l'effet %s n'est pas materialise offline sur le porteur -- le test comparerait deux "
        "absences ; effets vus = %s" % (_EFFECT_NAME, off["carrier_effects"]))
    assert len(no_aura["per_hit"]) == len(off["per_hit"]), (
        "le retrait de l'aura DEGAT ne doit pas changer le NOMBRE de coups (c'est 1183 qui le "
        "fait) -- %s vs %s" % (off["per_hit"], no_aura["per_hit"]))
    return rec, off, no_aura


def _agree(rec, off, label):
    assert off["per_hit"] == rec["live_per_hit"], (
        "%s : port != natif -- live=%s offline=%s" % (label, rec["live_per_hit"], off["per_hit"]))


def _deltas(off, no_aura):
    return [a - b for a, b in zip(off["per_hit"], no_aura["per_hit"])]


def test_adjacent_non_tau_gets_the_extra_damage(shadowsun_geometry):
    """TIER `AdjacentFriends` (d = 1, TOUTE faction) sur le canal DEGAT.

    Trois choses en une : le port ACCORDE, il accorde LA MEME CHOSE que le natif (live == offline),
    et la mesure DISCRIMINE (le retrait chirurgical de l'aura change bien les valeurs).

    Le delta est exige sur CHAQUE coup, pas seulement sur la somme : c'est ce qui separe un apport
    ADDITIF PAR COUP d'un forfait applique une fois a l'attaque. On n'exige PAS qu'il soit egal
    d'un coup a l'autre -- les etages aval (crit, block) le modulent, et c'est le cas mesure sur
    un beneficiaire multi-coups."""
    rec, off, no_aura = _run(shadowsun_geometry, ADJACENT, _BENEF_NON_TAU)
    assert hexgeo.distance(rec["benef_pos"], rec["carrier_pos"]) == 1
    _agree(rec, off, "ADJACENT")
    d = _deltas(off, no_aura)
    assert d and all(x > 0 for x in d), (
        "ADJACENT : le retrait de l'aura ne change RIEN sur au moins un coup -- soit le bonus "
        "manque, soit la mesure ne discrimine pas ; offline=%s no_aura=%s delta=%s"
        % (off["per_hit"], no_aura["per_hit"], d))


def test_ring2_non_tau_gets_nothing(shadowsun_geometry):
    """REGIME DISCRIMINANT du tier de DISTANCE -- LE MEME beneficiaire, un hex plus loin.

    `SurroundingFriends(range = 2)` est filtre par `UnitsFromFaction(9 = Tau)` : un NON-T'au a d = 2
    n'est pas dans le selecteur. Un port qui traiterait `d <= 2` sans le gate de faction en
    accorderait ici, et le desaccord live/offline le dirait."""
    rec, off, no_aura = _run(shadowsun_geometry, RING2_NON_TAU, _BENEF_NON_TAU)
    assert hexgeo.distance(rec["benef_pos"], rec["carrier_pos"]) == 2
    _agree(rec, off, "RING2_NON_TAU")
    assert _deltas(off, no_aura) == [0] * len(off["per_hit"]), (
        "RING2_NON_TAU : le port SUR-applique le +extraDmg (gate de faction manquant ?) -- "
        "offline=%s no_aura=%s" % (off["per_hit"], no_aura["per_hit"]))


def test_ring2_tau_gets_the_extra_damage(shadowsun_geometry):
    """TIER `UnitsFromFaction(9 = Tau)` du ring 2, sur le canal DEGAT : un T'AU a d = 2 EST dans le
    selecteur, la ou le non-T'au du MEME rayon (test precedent) ne l'est pas. Meme runner, meme
    porteur, meme cible -- seule la FACTION du beneficiaire change."""
    rec, off, no_aura = _run(shadowsun_geometry, RING2_TAU, _BENEF_TAU)
    assert hexgeo.distance(rec["benef_pos"], rec["carrier_pos"]) == 2
    _agree(rec, off, "RING2_TAU")
    d = _deltas(off, no_aura)
    assert d and all(x > 0 for x in d), (
        "RING2_TAU : le tier T'au du ring 2 n'accorde rien (ou pas sur tous les coups) -- "
        "offline=%s no_aura=%s delta=%s" % (off["per_hit"], no_aura["per_hit"], d))


def test_psychic_ranged_attack_gets_nothing(shadowsun_psyker):
    """LA BASCULE -- le gate que #420 a reveille et que rien ne retenait.

    `ultraTigurius` est ADJACENT au porteur (donc DANS le selecteur de geometrie : le zero ne peut
    pas venir de la distance) et tire avec son arme RANGED **Psychic** -- le tag natif du coup le
    dit (`DamageProfileType = 13`). Le natif n'accorde rien, le port non plus.

    L'assertion de geometrie et celle de profil sont LOAD-BEARING : sans elles, un bras qui
    tirerait du Bolter, ou depuis d = 4, passerait vert sans jamais exercer
    `!DamageProfileIs(0xd)`."""
    rec, off, no_aura = _run(shadowsun_psyker, ADJACENT, _BENEF_PSYKER, tgt_dist=_PSYKER_TGT_DIST)
    assert hexgeo.distance(rec["benef_pos"], rec["carrier_pos"]) == 1, (
        "le beneficiaire doit etre ADJACENT au porteur, sinon le zero vient de la GEOMETRIE et le "
        "gate de profil n'est pas exerce")
    profs = {p for p in (rec.get("live_profiles") or []) if p is not None}
    assert profs == {13}, (
        "le coup mesure doit etre Psychic (`DamageProfileType = 13`) -- profils vus %s ; sinon la "
        "bascule n'est pas exercee" % (sorted(profs),))
    _agree(rec, off, "PSYCHIC")
    assert _deltas(off, no_aura) == [0] * len(off["per_hit"]), (
        "PSYCHIC : le port applique le +extraDmg sur un coup Psychic -- le gate "
        "`!DamageProfileIs(0xd)` ne mord pas ; offline=%s no_aura=%s"
        % (off["per_hit"], no_aura["per_hit"]))
    # CONTRE-CONTROLE : le MEME effet, le MEME porteur, le MEME beneficiaire -- seul le profil du
    # coup change -> le bonus reapparait. C'est ce qui separe « gate qui MORD » de « effet inerte ».
    src = next(e for e in (off["state"].effects.by_unit.get(rec["carrier"]) or [])
               if getattr(e, "name", None) == _EFFECT_NAME)
    ctx = {"owner_id": rec["carrier"], "owner_pos": rec["carrier_pos"], "owner_team": 1,
           "att_id": rec["benef"], "att_pos": rec["benef_pos"], "att_team": 1,
           "att_faction": "Ultramarines", "is_melee": False}
    assert src.create_aura_attack_damage_bonus_for_ally(
        {**ctx, "damage_profile": "Psychic"}) is None
    assert src.create_aura_attack_damage_bonus_for_ally(
        {**ctx, "damage_profile": "Bolter"}) is not None, (
        "l'effet capte doit accorder sur un profil non-Psychic -- sinon le zero mesure ci-dessus "
        "vient d'un effet INERTE (magnitude absente), pas du gate")
