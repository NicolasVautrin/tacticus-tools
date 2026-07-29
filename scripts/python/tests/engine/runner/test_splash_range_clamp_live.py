"""GARDE live des TROIS masques `splash` a `0x2004002` (#243) -- ceux que #248 avait poses sur RE
seule, sans confrontation.

    1051 Stikkbomb     (orksOrkBoys)       preset `TargetingOptions statics+0x140` | 0x2000000
    1078 Fragstorm     (templSmnAggressor) preset `statics+0x180`                  | 0x2000000
    1098 PlasmaGrenade (eldarSmnGuardian)  preset `statics+0x140`                  | 0x2000000

Les trois ont le MEME `rules` effectif et le MEME `TargetingRange` (`RANGE_FROM_CONFIG` ->
`constants.range` = 2). Le SEUL champ qui les separe est `<preset>+0x20` `forceMeleeTarget` :
`RangedBool.True` pour 1051/1098 (le clamp de `IdunBattle.Core.Services.TargetingQuery$$GetRange`
est ARME) contre `RangedBool.False` pour 1078 (clamp DESARME). Un test qui ne mettrait pas d'ennemi
au contact du caster ne verrait AUCUNE difference entre les trois -- et ne garderait donc pas le
champ qui a motive la lecture preset-par-preset.

Le probe MESURE (`probe_243_splash_range_clamp.py`, qui porte le montage et sa justification), ce
test GARDE. Ce qu'il exige, et pourquoi :
  * accord natif/port sur TOUTES les lignes des DEUX montages -- le fond ;
  * au moins une ligne ACCEPTEE (0x0) -- sans elle, « le natif refuse tout » ne distingue pas le
    masque d'une ability indisponible (`AttackQuery$$GetInvalidTargetReason` court-circuite a `0x1`,
    ce que fait justement le trait `Summon`, cf. case-245) ;
  * au moins une ligne ou le natif REFUSE alors que `TARGETING_OPTIONS = None` rendait 0 -- la
    regression PERMISSIVE que le masque ferme ;
  * l'encadrement du seuil des DEUX cotes : d = 2 accepte, d >= 3 rompt sur `TargetIsInRange` ;
  * LE DISCRIMINANT : avec un ennemi non-Steppable au contact, la cible a d = 2 est REFUSEE par
    1051/1098 et ACCEPTEE par 1078 -- mesure faite dans le MEME runner, meme geometrie, meme tour ;
  * le contrefactuel `fmtFlip` (basculer `force_melee_target`) doit DIVERGER sur cette ligne : sans
    ca le champ serait « pose » sans etre demontre porteur.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import pytest

from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import RANGED_BOOL_TRUE
from engine.runner.abilities.targeting_rule import TargetingRule as TR

import probe_243_splash_range_clamp as P

STIKKBOMB = 1051
FRAGSTORM = 1078
PLASMA_GRENADE = 1098
ALL = [STIKKBOMB, FRAGSTORM, PLASMA_GRENADE]
CLAMP_ARME = {STIKKBOMB, PLASMA_GRENADE}        # `forceMeleeTarget = RangedBool.True`


@pytest.fixture(scope="module")
def montage(live_session):
    """Monte UNE fois le runner (catalogue injecte, trait `Summon` retire) + les DEUX geometries,
    et rend les lignes natif/port des trois abilities. Dispose SON runner (jamais ceux des autres).
    """
    from rl_collect_batch import _rpc
    sid = live_session
    carriers = P.resolve_carriers()
    rid, _added, _ab, state_file = P._build(sid, P.SEED, P.BOARD)
    try:
        got = P.collect(sid, rid, carriers)
        for aid, rec in got.items():
            assert not rec.get("error"), "ability %d : %s" % (aid, rec["error"])
        yield got
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            state_file.unlink(missing_ok=True)
        except Exception:                                            # noqa: BLE001
            pass


@pytest.mark.parametrize("aid", ALL)
def test_accord_natif_port(montage, aid):
    rows = montage[aid]["rows"]
    assert rows, "aucune ligne mesuree pour %d" % aid
    bad = [(r["montage"], r["label"], r["dist"], hex(r["nat"] or 0), hex(r["apres"])) for r in rows
           if r["nat"] != r["apres"]]
    assert not bad, "desaccord natif/port sur %d : %s" % (aid, bad)
    assert any(r["nat"] == 0 for r in rows), (
        "aucune cible ACCEPTEE pour %d -> impossible de distinguer « le masque refuse » de "
        "« l'ability est indisponible »" % aid)


@pytest.mark.parametrize("aid", ALL)
def test_le_masque_ferme_des_casts_que_master_acceptait(montage, aid):
    """`TARGETING_OPTIONS = None` (l'etat d'avant #248) rendait 0 sur des lignes que le natif
    REFUSE : c'est la degradation PERMISSIVE que le masque ferme."""
    gains = [r for r in montage[aid]["rows"] if r["nat"] not in (None, 0) and r["avant"] == 0]
    assert gains, ("aucun cast illegal ferme par le masque de %d -- l'etat monte ne discrimine "
                   "rien" % aid)


@pytest.mark.parametrize("aid", ALL)
def test_seuil_de_portee_range_from_config_2(montage, aid):
    """`RANGE_FROM_CONFIG` -> `AActiveAbility$$SetConfigValuesInTargetingOptions` pose
    `overrideRange = constants.range` = 2, `onlyAdjacent = RangedBool.False` : le filtre statique
    compare `hexDistance <= 2`. Montage LIBRE (aucun ennemi au contact -> aucun clamp) : d = 2
    passe, d >= 3 rompt sur `TargetIsInRange`."""
    rows = [r for r in montage[aid]["rows"]
            if r["side"] == "ENNEMI" and r["montage"] == "libre"]
    d2 = [r for r in rows if r["dist"] == 2]
    d3 = [r for r in rows if r["dist"] >= 3]
    assert d2 and d3, "spectre insuffisant (d=2 et d>=3 requis) : %s" % [r["dist"] for r in rows]
    assert all(r["nat"] == 0 and r["apres"] == 0 for r in d2), d2
    assert all(r["nat"] == int(TR.TargetIsInRange) and r["apres"] == int(TR.TargetIsInRange)
               for r in d3), d3


@pytest.mark.parametrize("aid", ALL)
def test_clamp_de_melee_le_champ_qui_separe_les_trois(montage, aid):
    """LE test de ce fichier. Montage MELEE : un ennemi non-Steppable AU CONTACT du caster ->
    `AttackQuery$$ShouldApplyRangedInMelee` est vrai. Alors `GetRange` applique
    `v = Math.Min(1, v) ; onlyAdjacent = true` SI ET SEULEMENT SI
    `RangedBoolExtensions.IsTrue(options.ForceMeleeTarget, caster)`.

    1051/1098 (`RangedBool.True`)  -> la cible a d = 2 devient ILLEGALE (`TargetIsInRange`) ;
    1078      (`RangedBool.False`) -> elle reste LEGALE.
    Meme runner, meme geometrie, meme tour : c'est le seul champ qui varie."""
    rows = [r for r in montage[aid]["rows"]
            if r["side"] == "ENNEMI" and r["montage"] == "melee"]
    assert any(r["dist"] == 1 for r in rows), (
        "aucun ennemi au contact -> le clamp n'est pas EXERCE : %s" % [r["dist"] for r in rows])
    at2 = [r for r in rows if r["dist"] == 2]
    assert at2, "aucune cible a d=2 dans le montage MELEE : %s" % [r["dist"] for r in rows]
    armed = int(ABILITY_CLASSES[aid].TARGETING_OPTIONS.force_melee_target) == RANGED_BOOL_TRUE
    assert armed == (aid in CLAMP_ARME), (
        "le port de %d n'a plus le `forceMeleeTarget` lu au ctor" % aid)
    if armed:
        assert all(r["nat"] == int(TR.TargetIsInRange) for r in at2), (
            "%d a le clamp ARME : le natif doit REFUSER la cible a d=2 avec un ennemi au "
            "contact -- %s" % (aid, at2))
        assert all(r["apres"] == int(TR.TargetIsInRange) for r in at2), at2
    else:
        assert all(r["nat"] == 0 for r in at2), (
            "%d a le clamp DESARME : le natif doit ACCEPTER la cible a d=2 malgre l'ennemi au "
            "contact -- %s" % (aid, at2))
        assert all(r["apres"] == 0 for r in at2), at2


@pytest.mark.parametrize("aid", ALL)
def test_force_melee_target_est_demontre_porteur(montage, aid):
    """Contrefactuel : basculer `force_melee_target` doit faire DIVERGER le port du natif, et
    precisement sur la ligne « cible a d=2, ennemi au contact ». Sans cette divergence le champ
    serait renseigne sans etre mesure -- le statut exact que ce cas devait lever."""
    at2 = [r for r in montage[aid]["rows"]
           if r["side"] == "ENNEMI" and r["montage"] == "melee" and r["dist"] == 2]
    assert at2, "montage MELEE sans cible a d=2"
    assert all(r["fmtFlip"] != r["apres"] for r in at2), (
        "neutraliser `force_melee_target` ne change RIEN sur %d : le champ n'est pas valide par "
        "la mesure -- %s" % (aid, at2))


@pytest.mark.parametrize("aid", ALL)
def test_masque_present_et_decompose_sans_residu(aid):
    """Garde OFFLINE (aucun runner) : le masque est pose, ses bits se nomment tous dans
    `targeting_rule.py`, et `range` accompagne toujours `rules`."""
    opts = getattr(ABILITY_CLASSES[aid], "TARGETING_OPTIONS", None)
    assert opts is not None, "masque absent pour %d" % aid
    assert opts.range is not None, "volet PORTEE non arme pour %d" % aid
    assert int(opts.rules) == (int(TR.TargetMatchesDynamicRule) | int(TR.TargetIsEnemy)
                               | int(TR.AllowObscuredTargetByElevation)), hex(int(opts.rules))
    reste = int(opts.rules)
    for bit in TR:
        reste &= ~int(bit)
    assert reste == 0, "bits non nommes dans le masque de %d : 0x%x" % (aid, reste)
