"""#249 -- GARDE des masques de ciblage du module `deathguard` : 1037 RevitalizingMalignancy,
1040 SpawnPoxwalkers, 1042 FlailSwing, 1168 EntropyCannons, 1169 PlagueburstMortar.

Les cinq entraient dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` : `get_invalid_target_reason`
rend 0 des sa premiere ligne (`options is None` => aucun gate), donc le moteur ACCEPTE des casts
que `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE. Ni erreur ni crash --
invisible en self-play.

CE QUE CHAQUE TEST VERROUILLE (et pourquoi il ECHOUE sans le masque de SON ability)
----------------------------------------------------------------------------------
  1037  `TargetIsFriendly` refuse les 3 necrons ; le volet PORTEE arme par `RANGE_ADJACENT` refuse
        l'allie a 4 hex.
  1040  `TargetIsCaster` refuse TOUTE cible autre que le caster (5 lignes).
  1042  `TargetIsEnemy` refuse les allies ET le caster ; `RANGE_ADJACENT` refuse l'ennemi a 6 hex.
  1168  `TargetIsEnemy` refuse les deux allies de la MoW.
  1169  `TargetIsTile` refuse les tuiles NON MARCHABLES (le natif y rend le litteral `1`
        `ValidRequest`, faute d'`AllowUnwalkableTargetTile`).

LES DEUX ORACLES, ET POURQUOI ILS DIFFERENT
-------------------------------------------
  * `abilityReason` (-> `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`) pour les
    trois HEROS et pour 1169 (domaine TUILE) ;
  * `abilityTargets` (-> `TargetingQuery$$GetPossibleTargetsForOptions` + la cascade) pour 1168.
    MESURE de ce cas : avec un caster MACHINE OF WAR en domaine UNITE, `abilityReason` rend `0x1`
    sur une cible que `abilityTargets` declare pourtant LEGALE -- la surcharge 4 arguments d'
    `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` court-circuite sur
    `ActiveAbilityComponent.GetOrNull(<composant du caster>, abilityType) == null` (les abilities
    d'une MoW ne vivent pas dans un `ActiveAbilityComponent` d'unite) et rend
    `GenericBrokenTargetingRule(1)` AVANT la cascade. Un « oracle » lu la ne mesurerait rien.

DEUX REGLES NON PORTEES restent attendues en ecart PERMISSIF, et le probe les NOMME au lieu de les
absoudre : `TargetingQuery$$GetCasterNotAddedReason` (0x800) et la regle-delegue
`TargetMatchesDynamicRule` (0x2). Le port rend 0 sur ces lignes -- jamais un refus invente, et jamais
un FAUX REFUS (c'est ce que le test 1168 verifie explicitement).
Il y en avait TROIS : `TargetIsHealable` (bit 8) est PORTEE depuis #245, et la ligne « allie adjacent
a PV pleins » de 1037 est passee de GAP a ACCORD (cf. `test_target_is_healable_live.py`).

Le montage (geometrie DRIVEE, jamais subie) et les lectures vivent dans
`scripts/python/probe_249_deathguard_targeting.py` : le probe MESURE, ce test GARDE, une seule
implementation. Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_249_deathguard_targeting as P
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting_rule import TargetingRule as TR


@pytest.fixture(scope="module")
def units_res(live_session):
    """UN montage pour les trois heros : `deathRotbone` au contact de `deathBlightlord` et d'un
    necron, `deathBlightbringer` a l'ecart, au moins un necron hors contact."""
    try:
        out = P._run_units(live_session, P.U_SEED, P.U_BOARD)
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
def mow_res(live_session):
    """UN montage pour la MoW `deathCrawler` : phase sans aura Contagion puis phase avec
    (`deathTyphus` amene au contact d'un ennemi)."""
    try:
        out = P._run_mow(live_session, P.M_SEED, P.M_BOARD)
    except RuntimeError as e:                                        # noqa: BLE001
        pytest.skip("montage MoW impossible : %s" % e)
    if not out:
        pytest.skip("MoW deathCrawler non deployee sur ce board")
    res = {}
    for r in out:
        if r.get("oracle") == "abilityTargets":
            P._report_set(r)
            res[(r["ability"], r["phase"])] = r
        else:
            P._report(r)
            res[r["ability"]] = r
    return res


def _assert_accord(res, aid, bit, min_gain=1):
    """Accord natif/port sur TOUTES les lignes (les ecarts admis sont EXACTEMENT les trois regles
    non portees de `P.NON_PORTES`, et seulement quand le port rend 0), au moins `min_gain` cast
    illegal que `master` acceptait, et le bit cite DEPLACE au moins un verdict."""
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
    key = "sans_" + bit.name
    assert r["cf"].get(key), (
        "ability %d : neutraliser %s ne deplace AUCUN verdict -> le bit n'est pas valide par cette "
        "mesure" % (aid, bit.name))


def test_1037_revitalizing_malignancy_targeting(units_res):
    """0x8500 = TargetIsHealable | TargetIsFriendly | CasterIsPossibleTarget, range RANGE_ADJACENT.
    `TargetIsFriendly` refuse les necrons, la portee adjacente refuse l'allie eloigne."""
    _assert_accord(units_res, 1037, TR.TargetIsFriendly, min_gain=3)
    r = units_res[1037]
    assert r["cf"]["sansRange"] >= 1, (
        "le `TargetingRange` de 1037 (RANGE_ADJACENT) ne deplace aucun verdict : le montage n'a pas "
        "d'allie HORS contact, la ligne TargetIsInRange n'existe pas")
    assert any(x["nat"] == int(TR.TargetIsInRange) for x in r["rows"]), \
        "aucun refus natif TargetIsInRange observe -> le volet portee n'est pas exerce"


def test_1040_spawn_poxwalkers_targeting(units_res):
    """0x8000000004 = CasterMatchesDynamicRule | TargetIsCaster. Self-cast : le caster est la SEULE
    cible legale, tout le reste rompt `TargetIsCaster`.

    Le `TargetingRange` vient de `TargetingRange$$CustomRange(GetRange)` -- une portee ECRASEE par
    un delegue non resolu, donc AUCUN gate de portee. Le test VERIFIE que ce non-port est sans
    consequence ici (le neutraliser ne deplace aucun verdict) plutot que de le supposer : la cascade
    refuse sur `TargetIsCaster` bien AVANT d'atteindre le volet portee."""
    _assert_accord(units_res, 1040, TR.TargetIsCaster, min_gain=4)
    r = units_res[1040]
    assert r["cf"]["sansRange"] == 0, (
        "neutraliser le TargetingRange de 1040 DEPLACE un verdict : le volet portee est donc "
        "atteignable, et le delegue `overrideRangeFunc` non resolu devient un vrai residu a fermer")
    assert any(x["nat"] == 0 for x in r["rows"]), \
        "aucune cible acceptee -> le court-circuit d'ability mord, rien n'est mesure"


def test_1042_flail_swing_targeting(units_res):
    """0x4000 = TargetIsEnemy (preset statique `TargetingOptions+0x40` copie TEL QUEL, sans ctor),
    range RANGE_ADJACENT. Refuse allies et caster ; l'ennemi hors contact rompt la portee."""
    _assert_accord(units_res, 1042, TR.TargetIsEnemy, min_gain=4)
    r = units_res[1042]
    assert r["cf"]["sansRange"] >= 1, "le volet portee de 1042 n'est pas exerce par ce montage"
    assert any(x["nat"] == 0 for x in r["rows"]), \
        "aucune cible acceptee -> rien ne distingue le masque d'un refus global"


def test_1168_entropy_cannons_targeting(mow_res):
    """0x40004002 = TargetMatchesDynamicRule | TargetIsEnemy | AllowNullCasterTile.

    Oracle ENSEMBLISTE (cf. l'en-tete). DEUX exigences, et la premiere est la plus importante : le
    port ne doit JAMAIS refuser une cible que le natif accepte (un faux refus serait une regression
    STRICTE, le seul sens interdit). La seconde : une fois l'aura Contagion montee, l'accord doit
    etre EXACT -- ce qui prouve que le sur-ensemble de la phase 1 vient bien de la regle dynamique
    non portee, et de rien d'autre."""
    pre = mow_res.get((1168, "avant-aura"))
    post = mow_res.get((1168, "apres-aura"))
    assert pre is not None and post is not None, "phases 1168 non mesurees"
    for tag, r in (("avant-aura", pre), ("apres-aura", post)):
        assert r["n_strict"] == 0, (
            "1168 [%s] : le port REFUSE une cible que le natif juge LEGALE -- regression STRICTE" % tag)
    assert post["n_over"] == 0, (
        "1168 : apres montage de l'aura Contagion, le port accepte encore des cibles que le natif "
        "refuse -> l'ecart ne vient PAS que de la regle dynamique %s" % post["nat_set"])
    assert pre["n_over"] > 0, (
        "1168 : la phase sans aura n'exhibe aucun sur-ensemble -> le montage d'aura n'a rien change, "
        "les deux phases ne sont pas discriminantes")
    assert post["n_gain"] >= 2, "1168 : aucun cast illegal rattrape (les allies doivent etre refuses)"


def test_1169_plagueburst_mortar_targeting(mow_res):
    """0x40000042 = TargetMatchesDynamicRule | TargetIsTile | AllowNullCasterTile. Cast TILE-TARGET
    (le bit 6 le CONFIRME au decompile, la ou le port l'avait deduit d'une mesure `abilityTargets`).
    Une tuile NON MARCHABLE rompt et le natif rend le litteral `1` (`ValidRequest`)."""
    _assert_accord(mow_res, 1169, TR.TargetIsTile, min_gain=1)
    r = mow_res[1169]
    assert r.get("n_nowalk"), (
        "aucune tuile non marchable sur ce board -> `TargetIsTile` n'est pas exerce, le test ne "
        "prouve rien")
    assert any(x["nat"] == 0 for x in r["rows"]), \
        "aucune tuile acceptee -> le court-circuit d'ability mord, rien n'est mesure"


def test_les_cinq_masques_sont_poses_et_portent_leur_range():
    """Garde OFFLINE (aucune session) : les cinq masques et leurs `TargetingRange` sont poses, et la
    somme des bits nommes redonne EXACTEMENT le litteral du ctor -- aucun bit residuel, aucun bit en
    trop. C'est la transcription du decompile qui est verrouillee ici, pas son effet."""
    attendu = {
        1037: (int(TR.TargetIsHealable | TR.TargetIsFriendly | TR.CasterIsPossibleTarget), 0x8500),
        1040: (int(TR.CasterMatchesDynamicRule | TR.TargetIsCaster), 0x8000000004),
        1042: (int(TR.TargetIsEnemy), 0x4000),
        1168: (int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy | TR.AllowNullCasterTile),
               0x40004002),
        1169: (int(TR.TargetMatchesDynamicRule | TR.TargetIsTile | TR.AllowNullCasterTile),
               0x40000042),
    }
    for aid, (somme, litteral) in attendu.items():
        opts = getattr(ABILITY_CLASSES[aid], "TARGETING_OPTIONS", None)
        assert opts is not None, "masque de %d absent" % aid
        assert somme == litteral, (
            "decomposition de %d INCOMPLETE : les bits nommes valent 0x%x, le ctor passe 0x%x"
            % (aid, somme, litteral))
        assert int(opts.rules) == litteral, (
            "masque de %d = 0x%x, le ctor natif passe 0x%x" % (aid, int(opts.rules), litteral))
        assert opts.range is not None, (
            "%d : `TargetingRange` absent -> aucun gate de portee ; il se lit dans la MEME ligne de "
            "decompile que le masque" % aid)
