"""CLIQUET `IsCharging` du canal CRIT (case-ischarging-crit-channel) -- residu `N14`.

`IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$CreateCritDamageBonus` est le
CALQUE EXACT de la face COUPS du meme effet (1223, Ragnar) -- meme arbre a deux noeuds, seule la cle
du `ConfigVar` change :

    EffectBonus.ForAddition( get_OwnerIsCaster & IsCharging(owner@0x148, target@0x178),
                             ConfigVar(0x42 = extraCritDmg, GetAbilityState(effect), config@+0x60) )

LE CANAL N'ETAIT PAS AVEUGLE COTE NATIF -- c'est le PORT qui perdait le contexte.
`IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage(this, attaquant, cible, ...)`
passe les DEUX entites a `GetCritDamageBonusFromEffects`, qui construit lui-meme son
`IdunBattle.Entities.Abilities.AbilityEntities` (caster = owner = l'attaquant, target = la cible)
avant d'evaluer le trigger de chaque `EffectBonus` par le slot `BaseEffect$$CritDamageBonus`.
Le contexte est desormais threade en UN point : `AttackDamageOperation._crit_params`.

OBSERVABLE : le CRIT est force (`--crit 100,700`) -> chaque coup crite, et le crit du COMBAT
s'ajoute a la BASE d'attaque AVANT spread (`eff_attack = attack + critDamage`). Un `+extraCritDmg`
non applique deplace donc TOUTES les valeurs per-coup, pas seulement leur nombre.

TROIS REGIMES + DEUX BORNES FORCEES. Les regimes viennent de `_charge_regime.py` ; les bornes
`off` / `always` sont le gate COURT-CIRCUITE dans les deux sens -- sans elles, un `shipped OK`
ne distinguerait pas « le gate est juste » de « le canal est eteint des deux cotes » :

  * `CHARGE`        -- `IsCharging` VRAI. `shipped` doit MATCHER le live, `off` doit MISMATCHER
                       (preuve que le bonus est REQUIS ici). VUE ROUGE AVANT LE FIX.
  * `STEP_ADJACENT` -- le caster BOUGE mais la cible etait DEJA adjacente : `UpdateCharging`
                       n'inscrit que les unites NOUVELLEMENT adjacentes -> `IsCharging` FAUX
                       alors que `UnitFlag.Moved` est VRAI. REGIME DISCRIMINANT du gate.
                       `shipped` doit MATCHER, `always` doit MISMATCHER (preuve que le port
                       n'a PAS rendu le bonus inconditionnel -- le risque exact que `N14` nommait).
  * `NO_STEP`       -- TEMOIN. Aucun pas : bit-exact AVANT comme APRES le fix.

ASCII only.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _charge_regime import (CHARGE, NO_STEP, STEP_ADJACENT,       # noqa: E402,F401  (fixture)
                            charge_regime)

from engine.entities.effects.factory import EFFECT_CLASSES        # noqa: E402
from engine.entities.effects.loki.hits import SagaOfTheWarriorBornOwnerEffect  # noqa: E402

_CASTER = "spaceBlackmane"          # <<Ragnar>>, HERO du pool, porteur du passif SagaOfTheWarriorBorn
_EFFECT_NAME = "SagaOfTheWarriorBorn_Owner"
_FORCE_CRIT = ["--crit", "100,700"]   # CritChance=100 (tout coup crite) / CritDamage=700 de base


# ---------------------------------------------------------------- instrumentation de la face CRIT

@contextmanager
def _crit_face(mode: str):
    """Court-circuite le GATE de la face CRIT de 1223, et RIEN d'autre (ni magnitude, ni canal).

      * `off`    -- la face ne contribue jamais (etat AVANT ce cas) ;
      * `always` -- la face contribue TOUJOURS (bonus inconditionnel = la regression que `N14`
                    redoutait si on posait la face sur un canal sans contexte)."""
    cls = SagaOfTheWarriorBornOwnerEffect
    orig = cls.create_effect_crit_damage_bonus_for_attack
    if mode == "off":
        def patched(self, att_ctx=None):
            return None
    else:
        # ⚠ #589-r1-r1 : le mutant force `is_charging` et PRESERVE le reste du contexte. Fabriquer
        # un dict MINIMAL (`{"is_charging": True}`) le rendrait inoperant depuis que
        # `get_OwnerIsCaster` a MIGRE du canal vers la classe (le balayage crit est desormais
        # BOARD-WIDE) : sans `owner_id`/`att_id`, le premier noeud ferme et la mutation ne mord
        # plus. Le test l'a correctement signale -- une contre-epreuve dont VERT est le resultat
        # suspect.
        def patched(self, att_ctx=None):
            return orig(self, {**(att_ctx or {}), "is_charging": True})
    cls.create_effect_crit_damage_bonus_for_attack = patched
    try:
        yield
    finally:
        cls.create_effect_crit_damage_bonus_for_attack = orig


# #589-r1-r1 : `get_OwnerIsCaster` a MIGRE du canal vers la classe (le balayage crit est desormais
# BOARD-WIDE, `board_effect_carriers`). L'identite du porteur fait donc partie du contexte du canal :
# un `att_ctx` sans elle ferme le PREMIER noeud. Ce n'est pas un assouplissement des tests, c'est le
# noeud lu a sa nouvelle place native -- et c'est le mutant `always` qui l'a signale le premier, en
# cessant de mordre.
_OK_CTX = {"is_charging": True, "owner_id": 1, "att_id": 1}


@contextmanager
def _count_crit_face():
    """COMPTE les appels reels de la face CRIT et enregistre le contexte recu.

    Parade au « lu jamais ecrit » : un canal branche mais jamais emprunte rendrait des tests verts
    pour une raison vide. La liste contient `(is_charging_recu, contribution)` par appel."""
    cls = SagaOfTheWarriorBornOwnerEffect
    orig = cls.create_effect_crit_damage_bonus_for_attack
    calls: list = []

    def counted(self, att_ctx=None):
        out = orig(self, att_ctx)
        calls.append(((att_ctx or {}).get("is_charging"), out))
        return out

    cls.create_effect_crit_damage_bonus_for_attack = counted
    try:
        yield calls
    finally:
        cls.create_effect_crit_damage_bonus_for_attack = orig


# ---------------------------------------------------------------- montage

@pytest.fixture(scope="module")
def ragnar_crit(charge_regime):
    """`spaceBlackmane` porte le passif `SagaOfTheWarriorBorn` -> effet 1223 sur lui-meme des le
    debut de bataille. `--crit 100,700` restaure le crit que la normalisation strippe (le crit d'un
    heros vient de ses items I_Crit) : sans lui la face CRIT existe mais n'est JAMAIS observable."""
    return charge_regime(p_units=_CASTER, a_units="necroOverlord,necroWarden", extra=_FORCE_CRIT)


@pytest.fixture(scope="module")
def ragnar_crit_alt(charge_regime):
    """GENERALISATION : meme invariant, AUTRE board, AUTRE seed, AUTRES cibles."""
    return charge_regime(p_units=_CASTER, a_units="orksNob,tyranTyrantGuard",
                         seed="31337", board="C1_25", extra=_FORCE_CRIT)


def _run(h, regime):
    """Joue le regime en LIVE puis rend `(rec, shipped, off, always, calls)` :
    `shipped` = rejeu offline du port LIVRE ; `off`/`always` = les deux bornes forcees ;
    `calls` = trace des appels reels de la face CRIT pendant le rejeu LIVRE."""
    rec = h.run(caster_visual=_CASTER, regime=regime)
    if rec is None:
        pytest.skip("geometrie %s non realisable sur ce board" % regime)
    if not rec["live_ok"] or not rec["live_per_hit"]:
        pytest.skip("attaque normale live refusee/vide (%s)" % regime)
    with _count_crit_face() as calls:
        shipped = h.replay_offline(rec)
    with _crit_face("off"):
        off = h.replay_offline(rec)
    with _crit_face("always"):
        always = h.replay_offline(rec)
    return rec, shipped, off, always, calls


def _saga_effect(rec, off):
    """L'effet 1223 doit etre MATERIALISE offline sur le caster -- sinon le test compare deux
    absences et son verdict ne vaut rien."""
    st = off["state"]
    return [e for e in (st.effects.by_unit.get(rec["caster"]) or [])
            if e.effect_type == 1223 or e.name == _EFFECT_NAME]


# ---------------------------------------------------------------- gardes structurelles (offline)

def test_registry_carries_the_crit_face():
    """Garde STRUCTURELLE (offline, sans jeu) : la face CRIT existe ET son gate est TRI-ETAT.
    Une contribution rendue sans `is_charging` PROUVE serait un bonus INCONDITIONNEL -- exactement
    ce que `N14` refusait de livrer."""
    assert EFFECT_CLASSES.get(_EFFECT_NAME) is SagaOfTheWarriorBornOwnerEffect
    e = SagaOfTheWarriorBornOwnerEffect(name=_EFFECT_NAME, effect_type=1223, level=1,
                                        ability_level=50)
    assert e.create_effect_crit_damage_bonus_for_attack(None) is None, \
        "contexte ABSENT -> aucune contribution (le natif commence par AreEntitiesAdjacent)"
    assert e.create_effect_crit_damage_bonus_for_attack({**_OK_CTX, "is_charging": False}) is None
    got = e.create_effect_crit_damage_bonus_for_attack(_OK_CTX)
    assert isinstance(got, int) and got > 0, \
        "charge PROUVEE -> +extraCritDmg[level] ; obtenu %r" % (got,)


def test_crit_magnitude_is_rarity_scaled():
    """`extraCritDmg` est la SEULE variable de `SagaOfTheWarriorBorn` listee dans
    `variablesAffectedByRarityBonus` -> contrairement a `extraHits`, le multiplier la SCALE.
    Confondre les deux regimes de magnitude est la faute classique de ce canal."""
    base = SagaOfTheWarriorBornOwnerEffect(name=_EFFECT_NAME, effect_type=1223, level=1,
                                           ability_level=50)
    scaled = SagaOfTheWarriorBornOwnerEffect(name=_EFFECT_NAME, effect_type=1223, level=1,
                                             ability_level=50, ability_variables_multiplier=180)
    b = base.create_effect_crit_damage_bonus_for_attack(_OK_CTX)
    s = scaled.create_effect_crit_damage_bonus_for_attack(_OK_CTX)
    assert s > b, "extraCritDmg doit etre scalee par le multiplier (mult 180 -> %r vs %r)" % (s, b)
    # La face COUPS, elle, NE l'est PAS (extraHits hors `variablesAffectedByRarityBonus`).
    hb = base.create_effect_hits_bonus_for_attack(True, {"is_charging": True})
    hs = scaled.create_effect_hits_bonus_for_attack(True, {"is_charging": True})
    assert hb.value == hs.value, "extraHits ne doit PAS etre scalee (%r vs %r)" % (hb, hs)


# ---------------------------------------------------------------- confrontations live

def test_charge_grants_extra_crit_damage(ragnar_crit):
    """CAS ROUGE AVANT LE FIX -- en charge, chaque coup crite avec `GetStat(10) + extraCritDmg`.

    Trois exigences, pas une : (1) le canal est VIVANT (la face a ete APPELEE, avec un contexte
    portant `is_charging=True`) ; (2) le port LIVRE reproduit le live per-coup ; (3) la borne `off`
    NE le reproduit PAS -- sans quoi le match ne prouverait rien."""
    rec, shipped, off, _always, calls = _run(ragnar_crit, CHARGE)
    assert _saga_effect(rec, shipped), \
        "l'effet 1223 n'est pas materialise offline -- le test comparerait deux absences"
    assert rec["target"] in shipped["charged"], (
        "la cible DOIT entrer dans ChargedUnitIds (nouvellement adjacente) ; charged=%s target=%s"
        % (shipped["charged"], rec["target"]))
    assert calls, ("canal MORT : la face CRIT de 1223 n'a jamais ete appelee pendant le rejeu "
                   "-- un canal branche mais jamais emprunte rend des verts vides")
    assert any(c[0] is True for c in calls), (
        "le contexte n'atteint pas la face CRIT avec la charge PROUVEE ; trace=%r" % (calls,))
    assert shipped["per_hit"] == rec["live_per_hit"], (
        "CHARGE : le port n'applique pas le +extraCritDmg de charge -- live n=%d %s "
        "offline n=%d %s" % (len(rec["live_per_hit"]), rec["live_per_hit"],
                             len(shipped["per_hit"]), shipped["per_hit"]))
    assert off["per_hit"] != rec["live_per_hit"], (
        "REGIME NON DISCRIMINANT : la face CRIT desactivee reproduit AUSSI le live "
        "(%s) -- ce montage ne prouve pas que le bonus s'applique" % (off["per_hit"],))


def test_step_adjacent_grants_no_crit_bonus(ragnar_crit):
    """REGIME DISCRIMINANT + TEMOIN DU GATE -- le caster BOUGE, mais la cible etait DEJA adjacente.

    `UpdateCharging` ne l'ajoute donc PAS aux `ChargedUnitIds` : `IsCharging` FAUX alors que
    `UnitFlag.Moved` est VRAI. Le port LIVRE doit rendre le live EXACT, et la borne `always`
    (gate court-circuite) doit MISMATCHER : c'est la preuve que la face n'est pas INCONDITIONNELLE."""
    rec, shipped, _off, always, calls = _run(ragnar_crit, STEP_ADJACENT)
    assert _saga_effect(rec, shipped), "l'effet 1223 doit etre present (sinon le gate n'est pas exerce)"
    assert rec["target"] not in shipped["charged"], (
        "la cible ne doit PAS entrer dans ChargedUnitIds (deja adjacente avant le pas) ; "
        "charged=%s target=%s" % (shipped["charged"], rec["target"]))
    assert calls and any(c[0] is False for c in calls), (
        "la face CRIT doit etre APPELEE avec `is_charging=False` (canal vivant, gate ferme) ; "
        "trace=%r" % (calls,))
    assert all(c[1] is None for c in calls), \
        "gate ferme -> aucune contribution ; trace=%r" % (calls,)
    assert shipped["per_hit"] == rec["live_per_hit"], (
        "STEP_ADJACENT : live=%s offline=%s" % (rec["live_per_hit"], shipped["per_hit"]))
    assert always["per_hit"] != rec["live_per_hit"], (
        "GATE INOPERANT : le +extraCritDmg force reproduit AUSSI le live (%s) -- le montage ne "
        "discrimine pas, ou le bonus est devenu inconditionnel" % (always["per_hit"],))


def test_no_step_is_bit_exact(ragnar_crit):
    """TEMOIN -- aucun pas du tour : ni `Moved` ni `ChargedUnitIds`. Bit-exact des deux cotes du
    fix ; ce test verrouille qu'on n'a rien deplace sur le regime deja juste avant lui."""
    rec, shipped, off, always, _calls = _run(ragnar_crit, NO_STEP)
    assert shipped["charged"] == [], \
        "aucun pas -> ChargedUnitIds vide, obtenu %s" % (shipped["charged"],)
    assert shipped["per_hit"] == rec["live_per_hit"], (
        "NO_STEP : live=%s offline=%s" % (rec["live_per_hit"], shipped["per_hit"]))
    assert off["per_hit"] == rec["live_per_hit"], (
        "NO_STEP : la face CRIT desactivee doit donner LE MEME resultat (gate deja ferme) ; "
        "off=%s live=%s" % (off["per_hit"], rec["live_per_hit"]))
    assert always["per_hit"] != rec["live_per_hit"], (
        "NO_STEP : le bonus force doit MISMATCHER (%s) -- sinon le montage ne mesure rien"
        % (always["per_hit"],))


def test_charge_beats_step_adjacent_live(ragnar_crit):
    """Le natif SEPARE bien les deux regimes SUR L'AXE CRIT -- on compare deux mesures LIVE.

    La comparaison porte sur la valeur MOYENNE par coup (pas sur leur nombre : la face COUPS,
    livree par `case-ischarging-hits`, deplace deja le compte)."""
    rec_c, _s, _o, _a, _c = _run(ragnar_crit, CHARGE)
    rec_s, _s2, _o2, _a2, _c2 = _run(ragnar_crit, STEP_ADJACENT)
    mc = sum(rec_c["live_per_hit"]) / float(len(rec_c["live_per_hit"]))
    ms = sum(rec_s["live_per_hit"]) / float(len(rec_s["live_per_hit"]))
    assert mc > ms, (
        "le natif doit frapper PLUS FORT par coup en charge (crit + extraCritDmg) -- "
        "CHARGE moy=%.1f %s, STEP_ADJACENT moy=%.1f %s"
        % (mc, rec_c["live_per_hit"], ms, rec_s["live_per_hit"]))


def test_charge_other_board(ragnar_crit_alt):
    """GENERALISATION du cas rouge : autre board (`C1_25`), autre seed (31337), autres cibles."""
    rec, shipped, off, _always, calls = _run(ragnar_crit_alt, CHARGE)
    assert rec["target"] in shipped["charged"]
    assert calls and any(c[0] is True for c in calls), \
        "canal MORT sur C1_25/31337 ; trace=%r" % (calls,)
    assert shipped["per_hit"] == rec["live_per_hit"], (
        "CHARGE (C1_25/31337) : live=%s offline=%s" % (rec["live_per_hit"], shipped["per_hit"]))
    assert off["per_hit"] != rec["live_per_hit"], (
        "CHARGE (C1_25/31337) : regime non discriminant (off=%s)" % (off["per_hit"],))


def test_step_adjacent_other_board(ragnar_crit_alt):
    """GENERALISATION du regime discriminant ET du temoin d'inconditionnalite."""
    rec, shipped, _off, always, _calls = _run(ragnar_crit_alt, STEP_ADJACENT)
    assert rec["target"] not in shipped["charged"]
    assert shipped["per_hit"] == rec["live_per_hit"], (
        "STEP_ADJACENT (C1_25/31337) : live=%s offline=%s"
        % (rec["live_per_hit"], shipped["per_hit"]))
    assert always["per_hit"] != rec["live_per_hit"], (
        "STEP_ADJACENT (C1_25/31337) : le bonus force reproduit le live (%s) -- gate inoperant"
        % (always["per_hit"],))
