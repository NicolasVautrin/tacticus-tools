"""CLIQUET #366-r1 -- `InescapableAccuracy_overrideHits` (1117) sur `eldarMauganRa`.

TROISIEME et dernier volet du passif `InescapableAccuracy` (TriggeredAbilityType 0x45b = 1115),
pose sur son PORTEUR avec ses deux jumeaux par
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.InescapableAccuracyAbility$$CreateBehaviour` :
`AddEffect(0x45b) + AddEffect(0x45c) + AddEffect(0x45d)`, targets = Owner, `turns = NULL`.

Le seul des trois a n'etre PAS un terme de somme : son canal natif
(`...InescapableAccuracy_OverridHitsEffect$$CreateBlockHitReductionTrigger` ->
`IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction`) rend un BOOLEEN, et
`IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` s'en sert pour SAUTER la liste des bonus
de coups a `addition < 0`. Son seul effet observable est donc la CARDINALITE de la salve -- ce que
mesurent tous les bras ici.

TROIS ARTEFACTS GARDES, chacun avec sa vue ROUGE mesuree (fiche
`docs/rl/case-366-r1-inescapable-accuracy-override-hits.md`) :

  * CANAL          -- `get_OwnerIsCaster & IsRangedAttack`, cable dans
                      `services.attack_hits_formula` (foyer PARTAGE combat/prediction :
                      `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` delegue au slot
                      0xb6 de `BattleQuery`, qui delegue a `DamagePrediction$$GetAttackHits`).
                      Vue rouge : le port comptait 4 coups la ou le natif en joue 6.
  * GATE MOUVEMENT -- `CreateActiveCondition` (corps PARTAGE par les trois classes du passif) =
                      `op_LogicalNot(HasFlag(Owner, 0 = UnitFlag.Moved))`.
  * GATE ATTAQUE   -- le noeud `IsRangedAttack` : au CONTACT, l'`ActiveCondition` est pourtant VRAIE
                      et les reductions doivent RESTER appliquees.

AUCUN seed BC custom, et c'est une CONTRAINTE : le nombre de coups vient du BC cote natif et du
gameconfig cote port (residu de SOURCE #366-r1 §7.2), les deux coincidant tant qu'on ne patche rien.
Patcher `Weapons[].Hits` -- ce que font les cliquets de 1115 et 1116 pour contourner le residu
`#366-r1-crit-multihit` -- DESYNCHRONISERAIT les deux modeles sur l'etage meme qu'on mesure ici.
Ce cas n'en a pas besoin : le residu CRIT decale les VALEURS, jamais le COMPTE.

Probe de mesure : `probe_366_r1_inescapable_accuracy_override_hits.py` (foyer unique du montage --
`stage`, `strike`, `replay`, `carried` sont IMPORTES ici plutot que re-transcrits).

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _charge_regime import charge_regime                          # noqa: E402,F401  (fixture)

from engine.entities.effects import block_hits_reduction_from_effects   # noqa: E402
from engine.entities.effects.factory import EFFECT_CLASSES        # noqa: E402
from engine.entities.effects.loki import (                        # noqa: E402
    InescapableAccuracyExtraCritChanceEffect, InescapableAccuracyExtraCritDamageEffect,
    InescapableAccuracyOverrideHitsEffect)
from engine.services.attack_hits_formula import attack_hits_with_modifiers   # noqa: E402
from probe_366_r1_inescapable_accuracy_override_hits import (     # noqa: E402
    EFFECT_NAME, EFFECT_TYPE, EXPECTED_HITS, MAUGAN, TARGET_MELEE, TARGET_RANGED,
    carried, replay, stage, strike)

_A_UNITS = "%s,%s" % (TARGET_RANGED, TARGET_MELEE)
#: `CritChance` de BASE du porteur = **0**. Dans MOVED et MELEE le volet `1115` est ferme (mouvement
#: / melee), donc `clamp(0 + 0) = 0` : la salve ne crite pas du tout et les VALEURS y sont
#: confrontables en plus du compte. Dans NOMOVE `1115` ouvre `clamp(0 + 15) = 15` -- le compte reste
#: exact, les valeurs peuvent legitimement diverger (residu `#366-r1-crit-multihit`).
_CRIT = "0,700"


def _measure(charge_regime, arm, seed="777", board="MC1_67"):
    """Monte le bras (`NOMOVE` / `MOVED` / `MELEE`), tire, rend `(h, rec, live)`. ECHEC FORT si le
    regime n'est pas atteint -- un `skip` VERT mentirait sur une garde qui n'a rien garde."""
    h = charge_regime(p_units=MAUGAN, a_units=_A_UNITS, seed=seed, board=board,
                      extra=["--crit", _CRIT])
    rec, why = stage(h, arm)
    assert rec is not None, "regime NON ATTEINT (%s) : %s" % (arm, why)
    live, why = strike(h, rec)
    assert live is not None, "salve non mesurable : %s" % why
    assert len(live) == EXPECTED_HITS[arm], (
        "le natif a joue %d coup(s), %d attendus pour le bras %s -- le regime n'est PAS celui que "
        "le bras promet (reduction absente ? cible morte ? mauvaise arme ?)"
        % (len(live), EXPECTED_HITS[arm], arm))
    return h, rec, live


@pytest.fixture(scope="module")
def oh_nomove(charge_regime):
    """BRAS NOMOVE -- tir a d=3 sur le porteur de `Camouflage` (`-2` coups au-dela de 2 hexes), sans
    avoir bouge : le block MORD, le natif joue ses **6** coups d'arme pleins."""
    return _measure(charge_regime, "NOMOVE")


@pytest.fixture(scope="module")
def oh_moved(charge_regime):
    """BRAS MOVED -- MEME tir, MEME distance d=3, apres UN pas : `UnitFlag.Moved` pose, l'effet est
    INACTIF, la reduction s'applique -> **4** coups."""
    return _measure(charge_regime, "MOVED")


@pytest.fixture(scope="module")
def oh_melee(charge_regime):
    """BRAS MELEE -- frappe au CONTACT sur le porteur de `Parry` (`-1` coup), sans avoir bouge :
    l'`ActiveCondition` est VRAIE et c'est `IsRangedAttack` qui ferme -> **4** coups (5 - 1)."""
    return _measure(charge_regime, "MELEE")


@pytest.fixture(scope="module")
def oh_alt(charge_regime):
    """GENERALISATION -- meme invariant, AUTRE board (`C1_25`, a elevation), AUTRE seed (31337)."""
    return _measure(charge_regime, "NOMOVE", seed="31337", board="C1_25")


def test_registry_binds_dedicated_class():
    """Garde STRUCTURELLE (offline, sans jeu) : 1117 a sa PROPRE classe, distincte des deux autres.

    Les fabriques `IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffects
    u003Eb__14_141/142/143` allouent depuis TROIS slots `Il2CppClass*` DIFFERENTS puis appellent le
    MEME corps de `$$.ctor` (dedup IL2CPP) : le ctor « fondu » ne fait PAS une classe commune. Les
    trois tables de methodes portent chacune UNE methode propre -- `CreateBlockHitReductionTrigger`
    pour celle-ci, `CreateCritChanceBonus` / `CreateCritDamageBonus` pour les deux autres."""
    assert EFFECT_CLASSES.get(EFFECT_NAME) is InescapableAccuracyOverrideHitsEffect
    assert InescapableAccuracyOverrideHitsEffect is not InescapableAccuracyExtraCritChanceEffect
    assert InescapableAccuracyOverrideHitsEffect is not InescapableAccuracyExtraCritDamageEffect


def test_gates_are_tristate_offline():
    """Les deux gates se taisent tant que leur contexte ne PROUVE pas le regime.

    ⚠ Le gate d'ATTAQUE lit `att_ctx["is_melee"]` (la cle du `board` de la formule de COUPS), PAS
    `is_ranged` comme les canaux CRIT de 1115/1116 -- transposer l'une pour l'autre rendrait le gate
    muet partout, en silence. Tri-etat #106 : seule une nature PROUVEE distance (`is_melee is False`)
    ouvre le canal ; `True` et `None` le ferment."""
    e = InescapableAccuracyOverrideHitsEffect(name=EFFECT_NAME, effect_type=EFFECT_TYPE,
                                              level=1, ability_level=50)
    assert e.block_hits_reduction(None) is False                       # ctx absent
    assert e.block_hits_reduction({}) is False                         # nature non mesuree
    assert e.block_hits_reduction({"is_melee": None}) is False
    assert e.block_hits_reduction({"is_melee": True}) is False         # melee
    assert e.block_hits_reduction({"is_melee": False}) is True
    assert e.block_hits_reduction({"is_melee": False, "has_moved": False}) is True
    assert e.block_hits_reduction({"is_melee": False, "has_moved": True}) is False, \
        "ActiveCondition NOT HasFlag(Owner, Moved) : une unite qui a bouge ne bloque RIEN"
    # `is_active` = le MEME predicat, sur l'autre voie (tout consommateur d'`active_effects`), et
    # c'est ici la garde EFFECTIVE : le natif filtre son enumeration sur `EffectComponent@+0x5c`
    # (`EffectsQuery$$GetActiveEffectsWithBonuses`), contrairement aux agregateurs CRIT.
    assert e.is_active({"has_moved": False}) is True
    assert e.is_active({"has_moved": True}) is False
    assert e.is_active({}) is True, "cle absente = non mesuree -> on ne ferme pas"
    # L'agregateur est un OU LOGIQUE, sans magnitude ni cumul.
    assert block_hits_reduction_from_effects([], {"is_melee": False}) is False
    assert block_hits_reduction_from_effects([e], {"is_melee": False}) is True
    assert block_hits_reduction_from_effects([e], {"is_melee": True}) is False


def test_no_config_variable_read_offline():
    """1117 ne lit AUCUNE variable de config -- le piege « la rarete est PAR VARIABLE » (#414) est
    inerte ici, et pour une raison de STRUCTURE, pas de configuration.

    Le corps natif rend le trigger NU (pas d'`EffectBonus`, donc pas de `ConfigVar`), et l'ability
    n'a que DEUX variables, toutes deux consommees par les deux autres volets. Le verdict est donc
    INDEPENDANT du multiplicateur de rarete du porteur."""
    import gameconfig as GC
    cfg = GC.ability("InescapableAccuracy") or {}
    assert sorted((cfg.get("variables") or {}).keys()) == ["extraCritChance", "extraCritDmg"]
    ranged = {"is_melee": False, "has_moved": False}
    for mult in (100, 180, 300):
        e = InescapableAccuracyOverrideHitsEffect(name=EFFECT_NAME, effect_type=EFFECT_TYPE,
                                                  level=1, ability_level=50,
                                                  ability_variables_multiplier=mult)
        assert e.block_hits_reduction(ranged) is True


def test_sign_not_provenance_offline():
    """Le tri natif porte sur le SIGNE de chaque bonus, PAS sur sa provenance -- verrouille sur la
    FORMULE, la ou le natif le fait (`DamagePrediction$$GetAttackHits`).

    Un `Camouflage` de la CIBLE et un bonus POSITIF de l'attaquant tombent dans deux listes
    differentes : le block eteint la premiere et laisse la seconde intacte. Restreindre le block aux
    seuls effets du defenseur (lecture « intuitive » mais fausse) laisserait passer
    `FightingRetreat_HitReduction`, qui est porte par l'ATTAQUANT."""
    def mk(name, et=0):
        return EFFECT_CLASSES[name]({"name": name, "effectType": et}, 100, 50, None)

    blk = mk(EFFECT_NAME, EFFECT_TYPE)
    cam = mk("Camouflage_HitReduction", 1134)
    board = {"att_id": 1, "tgt_id": 2, "attack_pos": (0, 0), "t_pos": (3, 0), "tgt_team": 1,
             "is_melee": False, "pos_by_id": {1: (0, 0), 2: (3, 0)}, "team_by_id": {1: 0, 2: 1},
             "has_moved": False}

    def hits(att_eff, bd):
        return attack_hits_with_modifiers(
            weapon_hits=6, extra_hits=0, extra_hits_melee=0, attacker_effects=att_eff,
            trait_objects=[], target_effects=[cam], aura_sources=[], board=bd,
            is_melee=False, damage_profile="Physical")

    assert hits([], board) == 4, "Camouflage a d=3 retire 2 coups (branche `dist > 2`)"
    assert hits([blk], board) == 6, "le block eteint la reduction PORTEE PAR LA CIBLE"
    assert hits([blk], {**board, "has_moved": True}) == 4, "apres un pas, la reduction revient"
    assert hits([blk], {**board, "is_melee": True}) == 4, \
        "au contact `IsRangedAttack` ferme le block (la valeur de Camouflage change, pas le verdict)"


def test_block_matches_native(oh_nomove):
    """CAS ROUGE AVANT LE FIX -- un Maugan Ra IMMOBILE tire ses 6 coups pleins malgre le
    `Camouflage` de la cible ; un port sans le canal n'en compte que 4."""
    h, rec, live = oh_nomove
    res = h.replay_offline(rec)
    assert carried(rec, res["state"]), \
        "1117 n'est pas materialise offline sur l'attaquant -- le test comparerait deux absences"
    assert len(res["per_hit"]) == len(live), (
        "CANAL : le port ne bloque pas la reduction de coups -- live n=%d %s / offline n=%d %s"
        % (len(live), live, len(res["per_hit"]), res["per_hit"]))


def test_channel_actually_bites(oh_nomove):
    """Le bras NOMOVE EXERCE bien le canal -- sinon le test precedent passerait pour une raison
    TRIVIALE (aucune reduction nulle part, deux comptes qui s'accordent).

    Mutation ADVERSARIALE : l'inscription est retiree d'`EFFECT_CLASSES`, l'effet capte retombe sur
    `BaseEffect` (dont `block_hits_reduction` rend False). Le rejeu DOIT alors compter MOINS de
    coups que le rejeu de REFERENCE."""
    h, rec, live = oh_nomove
    ref = h.replay_offline(rec)["per_hit"]
    mut = replay(h, rec, mutate="NOCHANNEL")
    assert len(mut) < len(ref), (
        "l'inscription retiree ne reduit PAS le compte (ref n=%d, mut n=%d) -- ce tir n'exerce pas "
        "le canal" % (len(ref), len(mut)))


def test_move_closes_the_gate(oh_moved):
    """BRAS MOVED -- apres UN pas, le natif SUBIT de nouveau la reduction (`HasFlag(Owner, Moved)`),
    et le port aussi. La distance est INCHANGEE (d=3) : le seul facteur qui bouge est le flag."""
    h, rec, live = oh_moved
    res = h.replay_offline(rec)
    assert carried(rec, res["state"]), \
        "1117 doit rester MATERIALISE (il est PERMANENT) -- c'est la CONDITION qui l'eteint"
    assert res["per_hit"] == live, (
        "GATE MOUVEMENT : live n=%d %s / offline n=%d %s"
        % (len(live), live, len(res["per_hit"]), res["per_hit"]))


def test_move_gate_is_load_bearing(oh_moved):
    """Le gate de mouvement est CHARGE UTILE, pas decoratif.

    Mutation ADVERSARIALE : les DEUX mirrors de l'`ActiveCondition` sont desarmes. Le port se
    remettrait a bloquer la reduction la ou le natif, qui a vu `HasFlag(Moved)`, la subit."""
    h, rec, live = oh_moved
    ref = h.replay_offline(rec)["per_hit"]
    mut = replay(h, rec, mutate="NOGATE")
    assert len(mut) > len(ref), (
        "gate desarme : le compte ne remonte pas (ref n=%d, mut n=%d) -- ce bras ne prouve pas que "
        "la condition mord" % (len(ref), len(mut)))


def test_melee_closes_the_gate(oh_melee):
    """BRAS MELEE -- au CONTACT, `IsRangedAttack` ferme le canal alors que l'`ActiveCondition` est
    VRAIE : le `Parry` de la cible retire bien son coup. Seul bras qui isole le noeud d'ATTAQUE."""
    h, rec, live = oh_melee
    res = h.replay_offline(rec)
    assert carried(rec, res["state"]), "1117 doit etre MATERIALISE meme quand son gate ferme"
    assert res["per_hit"] == live, (
        "GATE ATTAQUE : live n=%d %s / offline n=%d %s"
        % (len(live), live, len(res["per_hit"]), res["per_hit"]))


def test_melee_gate_is_load_bearing(oh_melee):
    """Mutation ADVERSARIALE : `IsRangedAttack` desarme (cle `is_melee` FORCEE a `False` -- la
    RETIRER fermerait le gate au lieu de l'ouvrir, mutation inerte mesuree le 2026-08-01). Le port
    bloquerait alors le `Parry` d'une frappe de contact -> le compte DOIT remonter."""
    h, rec, live = oh_melee
    ref = h.replay_offline(rec)["per_hit"]
    mut = replay(h, rec, mutate="NORANGEGATE")
    assert len(mut) > len(ref), (
        "`IsRangedAttack` desarme : le compte ne remonte pas (ref n=%d, mut n=%d) -- ce bras ne "
        "prouve pas que le gate d'attaque mord" % (len(ref), len(mut)))


def test_other_board(oh_alt):
    """GENERALISATION du cas rouge : autre board (`C1_25`, a ELEVATION), autre seed (31337)."""
    h, rec, live = oh_alt
    ref = h.replay_offline(rec)["per_hit"]
    assert carried(rec, h.replay_offline(rec)["state"])
    assert len(ref) == len(live), (
        "C1_25/31337 : live n=%d %s / offline n=%d %s" % (len(live), live, len(ref), ref))
    mut = replay(h, rec, mutate="NOCHANNEL")
    assert len(mut) < len(ref), \
        "C1_25/31337 : la mutation ne change rien -- ce bras n'exerce pas le canal"
