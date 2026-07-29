"""#254 -- GARDE des masques de ciblage des QUATRE abilities a MODULE UNIQUE : 1076
MV71SniperDroneSquadAttack, 1113 Stormcaller, 1118 DoctrinaImperatives, 1151 TheQuickening.

Les quatre entraient dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` : `get_invalid_target_reason`
rend 0 des sa premiere ligne (`options is None` => aucun gate), donc le moteur ACCEPTE des casts que
`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE. Ni erreur ni crash --
invisible en self-play, et c'est exactement l'espace d'action qu'un entrainement irait exploiter.

CE QUE CHAQUE TEST VERROUILLE (et pourquoi il ECHOUE sans le masque de SON ability)
----------------------------------------------------------------------------------
  1076  `TargetIsEnemy` refuse le caster et l'allie ; la portee d'ARME (`RANGE_ADJACENT_IF_MELEE
        _CASTER` + caster RANGED) refuse l'ennemi a `range + 1`.
  1113  `TargetIsEnemy` refuse le caster et l'allie ; `RANGE_FROM_CONFIG` (= 3) refuse l'ennemi a 4.
  1118  masque `AddCaster` SEUL -- aucune regle de refus : tout le gate vient de `RANGE_SELF`
        (`overrideRange = 0`), qui refuse TOUTE cible autre que le caster. Encadrement le plus
        serre possible du seuil : d = 0 accepte, d = 1 refuse.
  1151  `TargetIsTile` refuse les tuiles NON MARCHABLES (le natif y rend le litteral `1`
        `ValidRequest`, faute d'`AllowUnwalkableTargetTile`) ; `RANGE_FROM_CONFIG` (= 2) refuse les
        tuiles a 3.

LE VOLET PORTEE DES ABILITIES TILE-TARGET (#254, correctif du module PARTAGE)
----------------------------------------------------------------------------
1151 a EXHIBE un bug de `targeting.get_range_broken_rule` : il resolvait la cible par
`components.get_unit_feet` (mirror de `GetUnitFeetIds`, qui ne couvre que l'EMPREINTE d'une UNITE
et rend `[]` sur une TUILE) au lieu d'`entity_tiles` (mirror d'`IdunBattle.Entities.
EntityExtensions$$GetTiles`, la variable `pcVar12` du decompile). Consequence : le volet portee etait
INERTE pour les CINQ abilities tile-target du registre qui ont un gate de portee reel -- 1017
FragBomb, 1092 DarkTalonStrike, 1116 RadBombardment, 1151 TheQuickening, 1219 IronkinSteeljack.
Le test `test_1151_...` en est la garde directe (4 tuiles hors portee par couple, 8 au total).

Le montage (geometrie DRIVEE, jamais subie) et les lectures vivent dans
`scripts/python/probe_254_loki_solo_targeting.py` : le probe MESURE, ce test GARDE, une seule
implementation. Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_254_loki_solo_targeting as P
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting_rule import TargetingRule as TR

BOARD, SEED = P.COUPLES[0]


@pytest.fixture(scope="module")
def units_res(live_session):
    """UN montage pour les deux porteurs a cible-UNITE : `spaceStormcaller` (1113) avec un ennemi a
    distance EXACTE 3 et un autre a EXACTEMENT 4 (seuil encadre serre), `admecMarshall` (1118) a son
    contact."""
    try:
        out = P._run_units(live_session, SEED, BOARD, "test %s/%s" % (BOARD, SEED))
    except RuntimeError as e:                                        # noqa: BLE001
        pytest.skip("montage UNITES impossible : %s" % e)
    res = {}
    for r in out:
        if r.get("skipped"):
            continue
        P._report(r)
        res[r["ability"]] = r
    return res


@pytest.fixture(scope="module")
def tiles_res(live_session):
    """Montage TUILE pour 1151 : `bloodMephiston`, tuiles a d = 1/2 (dans la portee de config 2),
    d = 3/4 (hors), plus les tuiles NON MARCHABLES du board."""
    try:
        out = P._run_tiles(live_session, SEED, BOARD, "test %s/%s" % (BOARD, SEED))
    except RuntimeError as e:                                        # noqa: BLE001
        pytest.skip("montage TUILES impossible : %s" % e)
    res = {}
    for r in out:
        if r.get("skipped"):
            continue
        P._report(r)
        res[r["ability"]] = r
    return res


@pytest.fixture(scope="module")
def mv71_res(live_session):
    """Montage 1076 : `tauMarksman`, seul porteur -- et il n'est PAS lisible dans le gameconfig
    (`GC.unit_abilities` n'attache l'ID 1076 a aucun kit). C'est `decisionView(allAbilities=true)`
    qui l'expose, et `abilityReason` traverse la cascade pour lui malgre un `abilityState` null."""
    try:
        out = P._run_mv71(live_session, SEED, BOARD, "test %s/%s" % (BOARD, SEED))
    except RuntimeError as e:                                        # noqa: BLE001
        pytest.skip("montage 1076 impossible : %s" % e)
    res = {}
    for r in out:
        if r.get("skipped"):
            pytest.skip("1076 exposee par aucune unite sur ce montage")
        P._report(r)
        res[r["ability"]] = r
    return res


def _assert_accord(res, aid, min_gain=1):
    """Accord natif/port sur TOUTES les lignes (les ecarts admis sont EXACTEMENT les regles non
    portees de `P.NON_PORTES`, et seulement quand le port rend 0), et au moins `min_gain` cast
    illegal que `master` acceptait."""
    r = res.get(aid)
    assert r is not None, "ability %d non mesuree" % aid
    bad = [(x["label"], hex(x["nat"] or 0), hex(x["apres"])) for x in r["rows"]
           if x["nat"] != x["apres"] and not P._known_gap(x["nat"], x["apres"])]
    assert not bad, (
        "ability %d : le gate porte DIVERGE du natif (hors regles non portees nommees) -> %s"
        % (aid, bad))
    assert r["n_gain"] >= min_gain, (
        "ability %d : aucun cast illegal rattrape -- le masque ne mord pas sur ce montage, le test "
        "ne prouve rien" % aid)
    assert any(x["nat"] == 0 for x in r["rows"]), (
        "ability %d : AUCUNE cible acceptee -> rien ne distingue le masque d'un refus global (ou "
        "l'ability court-circuite avant la cascade)" % aid)
    return r


def _assert_seuil_encadre(r, aid):
    """Le seuil de portee doit etre encadre DES DEUX COTES : au moins une cible ACCEPTEE et au moins
    un refus `TargetIsInRange`, et neutraliser le `TargetingRange` doit DEPLACER ce refus. Sans ca
    on n'aurait mesure que « loin = refuse », ce qui ne distingue aucune valeur de portee."""
    assert any(x["nat"] == int(TR.TargetIsInRange) for x in r["rows"]), (
        "ability %d : aucun refus natif `TargetIsInRange` -> le volet portee n'est pas exerce par "
        "ce montage" % aid)
    assert r["cf"]["sansRange"] >= 1, (
        "ability %d : neutraliser le `TargetingRange` ne deplace AUCUN verdict -> le volet portee "
        "n'est pas valide par cette mesure" % aid)


def test_1113_stormcaller_targeting(units_res):
    """0x200004002 = TargetMatchesDynamicRule | TargetIsEnemy | TargetIsNotAnObject, portee de
    config 3. `TargetIsEnemy` refuse le caster et l'allie ; la portee refuse l'ennemi a 4."""
    r = _assert_accord(units_res, 1113, min_gain=3)
    _assert_seuil_encadre(r, 1113)
    assert r["cf"]["sans_TargetIsEnemy"] >= 1, (
        "1113 : neutraliser `TargetIsEnemy` ne deplace aucun verdict -> le montage n'a ni allie ni "
        "caster interrogeable, le bit n'est pas valide")


def test_1118_doctrina_imperatives_targeting(units_res):
    """0x80 = `AddCaster` SEUL. Aucune regle de refus dans le masque : c'est `RANGE_SELF`
    (`overrideRange = 0`) qui refuse tout ce qui n'est pas le caster, et le cast SUR SOI passe par
    le court-circuit `if ((char)rules < 0) return valide;` de `GetCasterNotAddedReason`.

    Le test EXIGE les deux faces, parce que l'une sans l'autre ne prouverait rien : un masque qui
    refuserait AUSSI le caster passerait le premier assert mais pas le second."""
    r = _assert_accord(units_res, 1118, min_gain=3)
    _assert_seuil_encadre(r, 1118)
    caster = [x for x in r["rows"] if x["targetId"] == r["caster"]]
    assert caster and caster[0]["nat"] == 0 and caster[0]["apres"] == 0, (
        "1118 : le cast SUR LE CASTER doit etre VALIDE des deux cotes (court-circuit `AddCaster`) "
        "-> %s" % caster)
    assert all(x["nat"] == int(TR.TargetIsInRange) for x in r["rows"]
               if x["targetId"] != r["caster"]), (
        "1118 : une cible autre que le caster n'est pas refusee sur la PORTEE -> le gate ne vient "
        "pas de RANGE_SELF comme le decompile le dit")


def test_1151_the_quickening_targeting(tiles_res):
    """0x806000042 = TargetMatchesDynamicRule | TargetIsTile | AllowObscuredTargetByElevation |
    AllowObscuredTargetByWalls | CasterHas1Tiles. Cast TILE-TARGET, portee de config 2.

    C'est le test qui garde AUSSI le correctif du module partage (`get_range_broken_rule` resolvant
    la cible par `entity_tiles` et non `get_unit_feet`) : sans lui, les quatre tuiles hors portee
    sont ACCEPTEES par le port alors que le natif rend `TargetIsInRange`."""
    r = _assert_accord(tiles_res, 1151, min_gain=4)
    _assert_seuil_encadre(r, 1151)
    assert r.get("n_nowalk"), (
        "aucune tuile non marchable sur ce board -> `TargetIsTile` n'est pas exerce, le test ne "
        "prouve rien")
    assert any(x["nat"] == int(TR.ValidRequest) for x in r["rows"]), (
        "1151 : aucun refus natif sur tuile NON MARCHABLE (le natif y rend le litteral 1) -> la "
        "regle `TargetIsTile` n'est pas exercee")
    assert r["cf"]["sans_TargetIsTile"] >= 1, (
        "1151 : neutraliser `TargetIsTile` ne deplace aucun verdict -> le bit n'est pas valide")


def test_1076_mv71_sniper_drone_targeting(mv71_res):
    """0x4002 = TargetMatchesDynamicRule | TargetIsEnemy, portee d'ARME (le caster est RANGED, donc
    `onlyAdjacent = IfNotRangedCaster` est FAUX pour lui).

    Le porteur ne se lit PAS dans le gameconfig -- il a fallu l'oracle live pour l'etablir (cf. la
    docstring de la fixture). Le test le RE-VERIFIE a chaque run : si `tauMarksman` cessait
    d'exposer 1076, la fixture skip au lieu de passer en silence."""
    r = _assert_accord(mv71_res, 1076, min_gain=2)
    _assert_seuil_encadre(r, 1076)
    assert r["cf"]["sans_TargetIsEnemy"] >= 1, (
        "1076 : neutraliser `TargetIsEnemy` ne deplace aucun verdict -> le bit n'est pas valide")


def test_les_quatre_masques_sont_poses_et_portent_leur_range():
    """Garde OFFLINE (aucune session) : les quatre masques et leurs `TargetingRange` sont poses, et
    la somme des bits nommes redonne EXACTEMENT le masque EFFECTIF calcule au decompile -- aucun bit
    residuel, aucun bit en trop. C'est la transcription qui est verrouillee ici, pas son effet.

    Les valeurs attendues sont les masques EFFECTIFS, pas les litteraux visibles des ctors : 1113 et
    1151 passent par la surcharge « PRESET + FLAGS » qui COMBINE (`dst+0x28 = flags | preset+0x28`),
    1076 par la factory `CustomLokiNormalAttackOptions` qui combine de meme."""
    attendu = {
        # 0x4002 = `0x4002 (preset TargetingOptions statics+0x28) | 2 (argument de la factory)`
        1076: (int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy), 0x4002),
        # 0x200004002 = `0x200000000 (flags) | 0x4002 (statics+0x1a8)`
        1113: (int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy | TR.TargetIsNotAnObject),
               0x200004002),
        1118: (int(TR.AddCaster), 0x80),
        # 0x806000042 = `0x806000000 (flags) | 0x42 (statics+0x228)`
        1151: (int(TR.TargetMatchesDynamicRule | TR.TargetIsTile
                   | TR.AllowObscuredTargetByElevation | TR.AllowObscuredTargetByWalls
                   | TR.CasterHas1Tiles), 0x806000042),
    }
    for aid, (somme, effectif) in attendu.items():
        opts = getattr(ABILITY_CLASSES[aid], "TARGETING_OPTIONS", None)
        assert opts is not None, "masque de %d absent" % aid
        assert somme == effectif, (
            "decomposition de %d INCOMPLETE : les bits nommes valent 0x%x, le masque effectif du "
            "ctor vaut 0x%x" % (aid, somme, effectif))
        assert int(opts.rules) == effectif, (
            "masque de %d = 0x%x, le ctor natif produit 0x%x" % (aid, int(opts.rules), effectif))
        assert opts.range is not None, (
            "%d : `TargetingRange` absent -> aucun gate de portee ; il se lit dans la MEME ligne de "
            "decompile que le masque" % aid)
    assert ABILITY_CLASSES[1118].TARGETING_OPTIONS.self_cast, (
        "1118 : `isSelfCasting` = 1 au ctor -- sans lui le port applique le filtre statique au "
        "cast-sur-soi au lieu de brancher sur `GetCasterNotAddedReason`")
