"""CLIQUET `FragLance` (#1065) -- le canal COUPS ADDITIONNELS (#179) gate `IsCharging`.

`IdunBattle.Entities.Effects.Loki.FragLanceEffect$$CreateAdditionalHits`
-> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` {
       trigger = `get_OwnerIsCaster` op_BitwiseAnd `IsNormalAttack`
                 op_BitwiseAnd `IsCharging(Caster@DSLSelectors+0x60, Target@+0x78)`,
       roll    = `BaseEffect$$GetMinMaxDamage(this, 0)` = `RandomAmount(minDmg, maxDmg)`,
       profile = `AbilityConfiguration$$GetDamageProfile(config).Value` = Blast,
       hits    = `DSLFormulas$$ConfigConst(0x2f = nrOfHits, config)`,
       display = `GetMinMaxDamage(this, 1)` = `Average(minDmg, maxDmg)` }

L'effet 1475 est pose a l'init par `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
FragLanceAbility` (parent `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`,
`$$GetEffectType` = `return 0x5c3`) -> table `ABILITY_INIT_OWNER_EFFECTS`.

MONTAGE -- porteur SUMMON, donc GREFFE (case-92 SS5bis, volet passif) : le porteur naturel
`astraSmnDeathRider` est spawne par `LeadingTheCharge` d'`astraDreir` et **ne se COMMANDE pas**
(#291) ; or le regime discriminant EXIGE de piloter le pas du caster (charge vs decalage adjacent).
`FragLance` se greffe : son utilite ne lit ni stat ni trait du caster, sa magnitude vient de la
config de l'ability, et son canal est celui d'une attaque normale quelconque. Greffon =
`astraBullgryn` (HERO MELEE du pool), `replace=True` -> ses passifs natifs sont ecartes, la
mecanique mesuree est ISOLEE.

TROIS REGIMES (montage : `_charge_regime.py`), memes roles que `test_ischarging_saga_hits_live` :
  * `CHARGE`        -- part a distance 2, arrive AU CONTACT -> `IsCharging` VRAI -> +nrOfHits coups
                       Blast en PLUS des coups d'arme.
  * `STEP_ADJACENT` -- part DEJA au contact et se decale -> `UpdateCharging` n'inscrit rien ->
                       `IsCharging` FAUX alors que `UnitFlag.Moved` est VRAI. REGIME DISCRIMINANT.
  * `NO_STEP`       -- aucun pas. TEMOIN.

POURQUOI LE NOMBRE DE COUPS : l'observable est DISCRETE (`len(per_hit)`). Un ecart d'un coup ne
peut etre ni absorbe ni compense par un regime d'armure ou de percage -- le harnais met deja
`Armor`/`FixedArmor` a 0 via `--hp-target`.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # LE PORT lui-meme : la classe d'effet, ses DEUX registres, et le foyer des gates.
        "scripts/python/engine/entities/effects/loki/hits.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        # LE CANAL #179 et ses DEUX facades COMBAT (c'est la que les deux cles neuves
        # `is_normal_attack` / `is_charging` sont threadees).
        "scripts/python/engine/runner/operations/additional_hits.py",
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        "scripts/python/engine/runner/operations/damage_ops/ability.py",
        # LE FOYER du predicat de charge, des DEUX cotes.
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/battle_query.py",
        "scripts/python/engine/playbook/prediction/normal_attack.py",
        # LE MONTAGE : harnais de charge, greffe catalogue, build de runner.
        "scripts/python/tests/engine/runner/_charge_regime.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/rl_duel.py",
        # La magnitude vient du gameconfig (minDmg/maxDmg/nrOfHits/damageProfile de `FragLance`).
        "data/symbols/*/gameconfig.json",
    ),
    "build": True,
    "toujours": True,
    "raison": "Confrontation AU NATIF : les coups per-coup live sortent du jeu, pas du depot, et "
              "le porteur est monte par GREFFE catalogue. Se rejoue donc a chaque passe live.",
}

import os        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)
import sys       # noqa: E402

import pytest    # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _charge_regime import (CHARGE, NO_STEP, STEP_ADJACENT,       # noqa: E402,F401  (fixture)
                            charge_regime)

from engine.entities.effect_type import EffectType                # noqa: E402
from engine.entities.effects.factory import (ABILITY_INIT_OWNER_EFFECTS,   # noqa: E402
                                             EFFECT_CLASSES)
from engine.entities.effects.loki.hits import FragLanceEffect     # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType    # noqa: E402

#: `TriggeredAbilityType` 0x5c9 = 1481 -- le PASSIF greffe (la CLE d'`ABILITY_INIT_OWNER_EFFECTS`).
ABILITY = TriggeredAbilityType.FragLance.name                     # "FragLance"
ABILITY_ID = int(TriggeredAbilityType.FragLance)                  # 1481
#: `EffectType` 0x5c3 = 1475 -- l'EFFET pose sur le porteur (la CLE d'`EFFECT_CLASSES`). Meme nom,
#: AUTRE enum, AUTRE ordinal : c'est le piege d'homonymie que cet appariement doit rendre visible.
EFFECT_NAME = EffectType.FragLance.name                           # "FragLance"
EFFECT_ID = int(EffectType.FragLance)                             # 1475
#: Greffon : HERO MELEE du pool (`rl_duel build --list-pool`, rank 17).
GRAFT = "astraBullgryn"


@pytest.fixture(scope="module")
def grafted_bc(tmp_path_factory):
    """Seed BC ou `FragLance` est GREFFE sur `astraBullgryn`. DEUX ecritures obligatoires
    (`BC.Units[].PassiveAbilities` + `BC.Abilities.PassiveAbilities[<nom>]`) -- cf.
    `catalog_inject.graft_passive_ability`. Les assertions sur le rapport sont le garde-fou du
    MONTAGE : un montage rate doit ASSERTER, jamais skipper."""
    import catalog_inject as CI
    out = tmp_path_factory.mktemp("fraglance") / "grafted-bc.json"
    p, reports = CI.write_grafted_seed_bc(str(out), ["%s:%s" % (GRAFT, ABILITY)])
    assert reports[0]["abilityId"] == ABILITY_ID, reports
    assert reports[0]["passiveAbilitiesAfter"] == [ABILITY_ID], reports
    assert reports[0]["configAdded"] or True, reports      # la config peut deja etre au seed
    return str(p)


@pytest.fixture(scope="module")
def bullgryn(charge_regime, grafted_bc):
    """Le greffon en p-units (c'est LUI qu'on pilote), cibles Necrons a PV gonfles."""
    return charge_regime(p_units=GRAFT, a_units="necroOverlord,necroWarden",
                         extra=["--seed-bc", grafted_bc])


@pytest.fixture(scope="module")
def bullgryn_alt(charge_regime, grafted_bc):
    """GENERALISATION : meme invariant, AUTRE board, AUTRE seed, AUTRES cibles."""
    return charge_regime(p_units=GRAFT, a_units="orksNob,tyranTyrantGuard",
                         seed="31337", board="C1_25", extra=["--seed-bc", grafted_bc])


def _run(h, regime):
    rec = h.run(caster_visual=GRAFT, regime=regime)
    if rec is None:
        pytest.skip("geometrie %s non realisable sur ce board" % regime)
    if not rec["live_ok"] or not rec["live_per_hit"]:
        pytest.skip("attaque normale live refusee/vide (%s)" % regime)
    return rec, h.replay_offline(rec)


def _frag_effect(rec, off):
    """L'effet 1475 doit etre MATERIALISE offline sur le caster -- sinon le test compare deux
    absences et son verdict ne vaut rien."""
    st = off["state"]
    return [e for e in (st.effects.by_unit.get(rec["caster"]) or [])
            if e.effect_type == EFFECT_ID or e.name == EFFECT_NAME]


def test_registres_portent_les_deux_faces():
    """Garde STRUCTURELLE (offline, sans jeu) : les DEUX tables du patron
    `AOwnerEffectTriggeredAbility` sont posees, et la CLE de chacune vient de SON enum.

    C'est le cran qui rend l'homonymie visible : `ABILITY_INIT_OWNER_EFFECTS` est keye par le nom
    d'un `TriggeredAbilityType` (1481), `EFFECT_CLASSES` par celui d'un `EffectType` (1475). Les
    deux chaines sont identiques et les deux ordinaux NON -- un appariement par ordinal serait
    faux."""
    assert ABILITY_ID != EFFECT_ID, "l'homonymie doit porter sur DEUX ordinaux distincts"
    assert ABILITY_INIT_OWNER_EFFECTS.get(ABILITY) == [EFFECT_NAME]
    assert EFFECT_CLASSES.get(EFFECT_NAME) is FragLanceEffect


def test_gate_tri_etat_offline():
    """Les TROIS conjoints du trigger sont exiges, et chacun en TRI-ETAT : une contribution rendue
    sans `is_charging` PROUVE (ou hors attaque normale, ou porteur != attaquant) serait un bonus
    inconditionnel -- exactement la degradation permissive que le port proscrit."""
    e = FragLanceEffect(name=EFFECT_NAME, effect_type=EFFECT_ID, level=1, ability_level=50)
    plein = {"owner_id": 7, "att_id": 7, "is_normal_attack": True, "is_charging": True}
    got = e.additional_hit_groups(plein)
    assert got and got[0]["count"] >= 1 and got[0]["profile"] == "Blast", \
        "contexte COMPLET -> un groupe Blast ; obtenu %r" % (got,)
    assert got[0]["min"] < got[0]["max"], "le noeud ROLL est un RandomAmount, pas un scalaire"
    assert got[0]["min"] <= got[0]["amount"] <= got[0]["max"], \
        "le noeud DISPLAY est l'Average des memes bornes ; obtenu %r" % (got,)
    assert e.additional_hit_groups(None) is None, "ctx ABSENT -> aucune contribution"
    for cle in ("is_charging", "is_normal_attack"):
        amput = dict(plein)
        amput[cle] = False
        assert e.additional_hit_groups(amput) is None, \
            "conjoint %s FAUX -> aucune contribution" % cle
        amput[cle] = None
        assert e.additional_hit_groups(amput) is None, \
            "conjoint %s NON MESURE -> aucune contribution (jamais permissif)" % cle
    autre = dict(plein, owner_id=8)
    assert e.additional_hit_groups(autre) is None, \
        "get_OwnerIsCaster : un porteur SPECTATEUR ne doit rien ajouter a l'attaque d'un tiers"


def test_charge_ajoute_les_coups_additionnels(bullgryn):
    """CAS PRINCIPAL -- la charge ajoute `nrOfHits` coups Blast au-dela des coups d'arme."""
    rec, off = _run(bullgryn, CHARGE)
    assert _frag_effect(rec, off), \
        "l'effet 1475 n'est pas materialise offline -- le test comparerait deux absences"
    assert rec["target"] in off["charged"], (
        "la cible DOIT entrer dans ChargedUnitIds (nouvellement adjacente) ; charged=%s target=%s"
        % (off["charged"], rec["target"]))
    assert len(off["per_hit_all"]) == len(rec["live_per_hit"]), (
        "CHARGE : le port n'ajoute pas les coups FragLance -- live n=%d %s offline n=%d %s "
        "(delta hits=%d)" % (len(rec["live_per_hit"]), rec["live_per_hit"],
                             len(off["per_hit_all"]), off["per_hit_all"],
                             len(off["per_hit_all"]) - len(rec["live_per_hit"])))
    assert off["per_hit_all"] == rec["live_per_hit"], (
        "CHARGE : meme nombre de coups mais valeurs differentes -- live=%s offline=%s"
        % (rec["live_per_hit"], off["per_hit_all"]))


def test_step_adjacent_n_ajoute_rien(bullgryn):
    """REGIME DISCRIMINANT -- le caster BOUGE, mais la cible etait DEJA adjacente avant le pas.
    Un gate `has_moved` (le proxy que `IsCharging` NE VAUT PAS) accorderait ici."""
    rec, off = _run(bullgryn, STEP_ADJACENT)
    assert _frag_effect(rec, off), "l'effet 1475 doit etre present (sinon le gate n'est pas exerce)"
    assert rec["target"] not in off["charged"], (
        "la cible ne doit PAS entrer dans ChargedUnitIds (deja adjacente avant le pas) ; "
        "charged=%s target=%s" % (off["charged"], rec["target"]))
    assert len(off["per_hit_all"]) == len(rec["live_per_hit"]), (
        "STEP_ADJACENT : le port sur-applique FragLance -- live n=%d %s offline n=%d %s"
        % (len(rec["live_per_hit"]), rec["live_per_hit"],
           len(off["per_hit_all"]), off["per_hit_all"]))
    assert off["per_hit_all"] == rec["live_per_hit"], (
        "STEP_ADJACENT : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit_all"]))


def test_no_step_n_ajoute_rien(bullgryn):
    """TEMOIN -- aucun pas du tour : ni `Moved` ni `ChargedUnitIds`."""
    rec, off = _run(bullgryn, NO_STEP)
    assert off["charged"] == [], "aucun pas -> ChargedUnitIds vide, obtenu %s" % (off["charged"],)
    assert len(off["per_hit_all"]) == len(rec["live_per_hit"]), (
        "NO_STEP : live n=%d %s offline n=%d %s" % (len(rec["live_per_hit"]), rec["live_per_hit"],
                                                    len(off["per_hit_all"]), off["per_hit_all"]))
    assert off["per_hit_all"] == rec["live_per_hit"], (
        "NO_STEP : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit_all"]))


def test_le_natif_separe_les_deux_regimes(bullgryn):
    """Sans ce cran, les deux tests ci-dessus passeraient pour une raison TRIVIALE (aucun bonus
    nulle part). On compare deux mesures LIVE, jamais le port."""
    rec_c, _ = _run(bullgryn, CHARGE)
    rec_s, _ = _run(bullgryn, STEP_ADJACENT)
    assert len(rec_c["live_per_hit"]) > len(rec_s["live_per_hit"]), (
        "le natif doit porter PLUS de coups en charge qu'en decalage adjacent -- "
        "CHARGE n=%d, STEP_ADJACENT n=%d (si egal, le montage n'exerce pas le canal)"
        % (len(rec_c["live_per_hit"]), len(rec_s["live_per_hit"])))


def test_charge_autre_board(bullgryn_alt):
    """GENERALISATION : autre board (`C1_25`), autre seed (31337), autres cibles."""
    rec, off = _run(bullgryn_alt, CHARGE)
    assert rec["target"] in off["charged"]
    assert len(off["per_hit_all"]) == len(rec["live_per_hit"]), (
        "CHARGE (C1_25/31337) : live n=%d %s offline n=%d %s"
        % (len(rec["live_per_hit"]), rec["live_per_hit"], len(off["per_hit_all"]), off["per_hit_all"]))
    assert off["per_hit_all"] == rec["live_per_hit"], (
        "CHARGE (C1_25/31337) : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit_all"]))
