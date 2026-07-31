"""#350-r3 (b) -- le porteur MACHINE OF WAR, confronte au LIVE.

#350 avait laisse `1147 HadesAutocannons` et `1148 DaemonicOrdnance` (porteur `blackForgefiend`,
MoW) NON CONFRONTEES : le gabarit #344 passe son caster par `--p-units`, qui REFUSE une MoW. La
levee est ecrite dans `probe_350r3_mow_caster.py` (en-tete) ; cette garde en verrouille le resultat.

Ce que la garde tient :

1. la garde `--p-units` est EXPLICITE et STRUCTURELLE -- `pool_regular = normalized - mow`, donc
   `blackForgefiend` est dans `pool_mow` et JAMAIS dans le pool regulier -- et le chemin MoW EST
   cable (`--a-mow` la deploie, board MoW-capable, entree `BC.Units` patchable) ;
2. le mur RESTANT n'etait PAS le deploiement -- et, depuis #360, ce n'etait pas non plus le jeu :
   l'oracle qui passe la position du CASTER (`ncPlaybookPredict`, = `UnitPosition$$NullPosition()`)
   REND les events d'une MoW, et `engine.ai.context.build_machine` lui construit un contexte. Ce que
   #350-r3 mesurait etait la SUBSTITUTION de la position de la cible faite par `rpc-predict.ts`
   (corrigee, cf. `test_360_mow_caster_oracle_live.py`) ;
3. `1147` CONFRONTEE : deux bras de parite, quatre variantes, `to_even` SEULE nulle sur les deux --
   ce que prevoit son inscription (a2) -- et le code LIVRE egal au natif sur les deux bras ;
4. `1148` CONFRONTEE dans ses DEUX regimes : zone froide (natif 0 == port 0) et zone EN FEU
   (natif == port). Le regime froid est celui ou le port INVENTAIT un event avant #350-r3 ;
5. (#359) le VOLET AoE de `1147` : le natif emet UN event PAR ENTITE de son selecteur
   `HadesAutocannonsAbility$$GetAllTargets`, le port n'en emettait qu'UN. Quatre regimes -- aucun
   summon, cible summon, porteur ennemi AU CONTACT, cible NON-summon -- avec le port d'AVANT
   reconstitue par retrait des entrees de registre, pour que la garde verrouille un ECART et pas un
   accord vide ;
6. (#359) la GENERALISATION du meme volet : autre board (`MC1_15`), caster ALLIE des summons, et un
   montage ou les summons ne prennent PAS tous le meme degat -- ce qui distingue une prediction
   PAR CIBLE d'une recopie ;
7. (#359-r1) le PENDANT du volet AoE pour `1148` : son playbook boucle lui aussi sur un selecteur
   (`GetAllDamageableTargets` = les ennemis debout sur une tuile EN FEU de la zone-triangle ancree
   sur la CIBLE), et le port n'avait AUCUN set AoE pour elle. Trois regimes, plus la meme mesure sur
   un board ou le predicat de plateau `IsPositionMachineForCurrentPlayer(2)` BASCULE -- ce qui borne
   les DEUX branches du `If` qui choisit la direction du triangle.

Sept runners au total, disposes par le probe. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_350r3_mow_caster as P                          # noqa: E402
from engine.entities.abilities.active_ability import (      # noqa: E402
    _PREDICTION_MINMAX_AVERAGE, _A_VIA_STAFF_OF_STARS_GET_DAMAGE)


@pytest.fixture(scope="module")
def scan():
    return P.scan(verbose=False)


@pytest.fixture(scope="module")
def mow_caster():
    return P.step1_mow_caster(seed=35130, verbose=False)


@pytest.fixture(scope="module")
def confronted_1147():
    return P.step2_confront_1147(seed=35140, verbose=False)


@pytest.fixture(scope="module")
def daemonic():
    return P.step3_daemonic_ordnance(seed=35160, verbose=False)


@pytest.fixture(scope="module")
def aoe_1147():
    return P.step4_aoe_1147(seed=35180, verbose=False)


@pytest.fixture(scope="module")
def aoe_1147_generalized():
    return P.step5_generalize_1147(seed=35200, verbose=False)


@pytest.fixture(scope="module")
def aoe_1148():
    """#359-r1 -- le MONTAGE, nomme et reutilisable : cible HORS zone de feu + second ennemi DEDANS.

    Positions DRIVEES de bout en bout (`dir` calcule par le mirror de
    `BattleQuery$$GetPositionMachineForPlayer` sur les `SpawnPointGroups` de la BC executee, puis
    RE-VERIFIE contre les tuiles reellement allumees), armures PILOTEES par ennemi pour que l'accord
    porte sur les VALEURS et pas seulement sur l'ensemble."""
    return P.step6_aoe_1148(seed=35220, verbose=False)


@pytest.fixture(scope="module")
def aoe_1148_other_dir():
    """LE MEME montage sur `C1_15`, ou `MachineOfWarPosition(team 1) = 0` : le predicat est FAUX et
    le natif prend `Direct(4)`. La fixture jumelle borne l'AUTRE branche du `If`."""
    return P.step7_generalize_1148(seed=35240, verbose=False)


def test_p_units_refuses_a_mow_by_construction_and_the_mow_path_is_wired(scan):
    """1 : la limite etait NOTRE outil, et elle est structurelle -- pas un oubli de cablage."""
    assert scan["in_pool_mow"] is True, "blackForgefiend n'est plus au pool MoW"
    assert scan["in_pool_regular"] is False, (
        "blackForgefiend serait desormais dans le pool REGULIER : `--p-units` l'accepterait, et le "
        "diagnostic de #350-r3 (garde explicite, pools disjoints) ne tiendrait plus")
    assert scan["in_bc_units_catalog"] is True, (
        "sans entree `BC.Units`, `--unit-stat <mow>:ActiveAbilityLevel` n'aurait aucune prise")
    assert scan["board_mow_ok"] is True, "MC1_67 n'est plus MoW-capable : la MoW serait DROP en silence"
    assert scan["ok"] is True


def test_the_mow_caster_is_measurable_by_the_caster_position_oracle(mow_caster):
    """2 : la MoW se deploie, son playbook se resout, son niveau est PILOTE -- et l'oracle qui passe
    la position du CASTER (`ncPlaybookPredict`, = la `NullPosition` du tactic natif) REND ses events.

    ⚠ Ce test disait l'inverse jusqu'a #360 : il verrouillait `hot.listNull is True` et
    `port_ctx_me is None` comme le « mur restant ». Les deux etaient des artefacts de MESURE --
    `aiPlaybookPredict` substituait la position de la CIBLE, et le probe appelait `build` (la
    fonction des UNITES) au lieu de `build_machine`. La garde porte donc desormais sur ce qui est
    vrai du JEU : l'oracle repond, et le port construit un contexte."""
    assert mow_caster["deployed"] is True
    assert dict(mow_caster["abilities"]).get(1147) == P.A1147_LVL_A, (
        "`--unit-stat` ne pilote plus le niveau d'ability de la MoW : la parite ne serait plus "
        "choisie mais subie")
    assert mow_caster["cold"]["count"] == 0 and mow_caster["cold"]["listNull"] is False
    assert mow_caster["summons"], "le montage summon n'a rien pose"
    assert mow_caster["oracles_agree"] is True, (
        "l'oracle par la position du CASTER ne rend plus d'event pour une MoW (ou les deux oracles "
        "divergent alors que le bundle porte le correctif #360) : %s / %s"
        % (mow_caster.get("hot"), mow_caster.get("hot_nc")))
    assert mow_caster["port_machine_ctx_me"] == P.MOW, (
        "`engine.ai.context.build_machine` ne construit plus le contexte de la MoW : %s"
        % mow_caster.get("port_machine_ctx_me"))
    assert mow_caster["port_ctx_me"] is None, (
        "`build` (fonction des UNITES) rend un contexte pour une Machine : `decisionView.units` "
        "contiendrait desormais les MoW, ce qui change le routage de tactic")


def test_1147_is_confronted_and_rounds_half_to_even(confronted_1147):
    """3 : le verdict d'arrondi de 1147, mesure sur les deux bras."""
    assert 1147 in _A_VIA_STAFF_OF_STARS_GET_DAMAGE and 1147 in _PREDICTION_MINMAX_AVERAGE
    r = confronted_1147
    for k in ("a", "b"):
        arm = r["arms"][k]
        assert not arm.get("error"), "bras %s KO : %s" % (k, arm["error"])
        assert arm["discriminates"], (
            "bras %s NON DISCRIMINANT (les quatre variantes coincident) : il ne prouve rien" % k)
        assert arm["shipped_ok"], (
            "bras %s : le code LIVRE %s != natif %s" % (k, arm["shipped"], arm["native"]))
    assert r["regimes_ok"], "la parite pilotee n'est pas celle annoncee (3 mod 4 puis 1 mod 4)"
    assert r["nul_on_both_arms"] == ["to_even"], (
        "variantes nulles sur les DEUX bras : %s -- attendu ['to_even'] (voie a2, "
        "`StaffOfStarsAbility$$GetDamage` avec isPrediction = 1)" % r["nul_on_both_arms"])


def test_1148_agrees_with_the_native_in_both_fire_regimes(daemonic):
    """4 : le cliquet du gate de selecteur. Le regime FROID est celui ou le port inventait un
    event ; le regime EN FEU verifie que le gate ne l'a pas simplement eteint."""
    cold, hot = daemonic["cold"], daemonic["hot"]
    assert cold["n_native"] == 0, "le natif emet desormais sur une zone froide : relire le selecteur"
    assert cold["n_port"] == 0, (
        "le port emet %s sur une zone FROIDE la ou le natif n'emet rien -- c'est exactement la "
        "sur-prediction que `_MAKE_DMG_TARGET_GATE` ferme" % (cold["port"],))
    assert daemonic["cast_ok"], "le cast intermediaire a echoue : %s" % daemonic.get("cast_error")
    assert "Fire" in (hot["tile_effects_on_target"] or []), (
        "la tuile de la cible ne brule pas apres le cast : le second regime n'a pas ete atteint")
    assert hot["n_native"] > 0, "zone en feu et natif muet : le montage ne discrimine plus"
    assert hot["port"] == hot["native"], (
        "zone EN FEU : port %s != natif %s -- le gate ne doit pas eteindre les events LEGITIMES"
        % (hot["port"], hot["native"]))


def _bag(events):
    """Les events d'un regime, comparables SANS l'ordre. Le natif ORDONNE son ensemble
    (`SortByRow` / `SortReverse` sous `If(IsTopPlayer)`, un ordre de LECTURE du selecteur) ; le port
    ne porte PAS ces noeuds et emet la cible principale en tete. La garde porte donc sur l'ENSEMBLE
    et les valeurs -- ce que l'utilite consomme (`CalculateUtilityFromPredictions` SOMME) -- et non
    sur une sequence dont le port ne pretend pas mirrorer l'ordre."""
    return sorted((e["target"], tuple(e["dmg"])) for e in events)


def test_1147_emits_one_event_per_entity_of_its_selector(aoe_1147):
    """5 (#359) : le volet AoE de `1147`, verrouille par un ECART mesure.

    `HadesAutocannonsPlaybook$$MakeDamagePredictions` ne prend PAS `<Target>` : il boucle sur
    `GetEntitiesFromSelector(HadesAutocannonsAbility$$GetAllTargets, ...)` -- les summons du camp de
    la CIBLE dans son disque `range`, cible INCLUSE -- et `AddRange` un
    `GenerateMultiHitAttackPredictions` par entite.

    Les quatre regimes ne sont pas redondants :
      * R0 (aucun summon en jeu) tient la borne BASSE : selecteur vide -> 0 event. C'est le regime
        mesure 16 fois par #350-r3, et celui ou le port d'AVANT inventait un event ;
      * R1 donne le COMPTE (le natif en emet autant que de summons retenus) ;
      * R2 amene le porteur -- du camp du CASTER -- au contact : le compte ne doit PAS bouger, ce qui
        discrimine le referent d'equipe `Friends(of: Target)` (R1 seul le laisse ambigu, summoner et
        summons y etant du meme camp) ;
      * R3 cible une unite NON-summon : le natif emet quand meme sur les summons voisins. C'est CE
        regime qui interdit de court-circuiter la boucle AoE quand la cible principale est refusee
        par le gate -- une lecture qui ne se devine pas depuis R1/R2."""
    r = aoe_1147
    assert not r.get("error"), "montage KO : %s" % r["error"]
    assert len(r["summons"]) >= 2, (
        "le montage n'a pose que %s summon(s) : le volet AoE ne serait pas exerce" % len(r["summons"]))
    assert r["r0"]["native"] == [], (
        "R0 : le natif emet %s SANS aucun summon en jeu -- le selecteur ne serait plus restreint aux "
        "summons, et les 16 mesures de #350-r3 seraient a relire" % (r["r0"]["native"],))
    for k in ("r0", "r1", "r2", "r3"):
        reg = r[k]
        assert _bag(reg["port_after"]) == _bag(reg["native"]), (
            "%s : port %s != natif %s" % (reg["tag"], reg["port_after"], reg["native"]))
    # R1 : le natif emet bien PLUSIEURS events -- sans quoi la garde passerait sur un montage
    # mono-cible, ou le volet AoE n'est tout simplement pas exerce.
    assert len(r["r1"]["native"]) == len(r["summons"]) >= 2, (
        "R1 : %d event(s) natif(s) pour %d summons -- le selecteur ne les retient plus tous"
        % (len(r["r1"]["native"]), len(r["summons"])))
    assert len(r["r2"]["native"]) == len(r["r1"]["native"]), (
        "R2 : le porteur ENNEMI au contact change le compte natif (%d -> %d) -- `Friends` "
        "referencerait le CASTER et non la CIBLE"
        % (len(r["r1"]["native"]), len(r["r2"]["native"])))
    import hexgeo
    cpos, tpos = r.get("r2_caster_pos"), r.get("r2_target_pos")
    assert cpos is not None and tpos is not None and hexgeo.distance(cpos, tpos) <= 1, (
        "R2 : le porteur n'a pas ete amene au CONTACT de la cible (caster=%s cible=%s) -- le regime "
        "ne discrimine alors plus le referent d'equipe" % (cpos, tpos))
    # R3 : la cible demandee n'est PAS dans les events natifs, et pourtant il y en a.
    tgt3 = r["r3"]["target"]
    assert r["r3"]["native"], "R3 : le natif ne rend plus rien quand la cible est hors selecteur"
    assert all(e["target"] != tgt3 for e in r["r3"]["native"]), (
        "R3 : le natif emet sur la cible NON-summon %s -- `UnitsWithTrait(2 = Summon)` ne la "
        "filtrerait plus" % tgt3)
    # LE CLIQUET : le port d'AVANT #359 differait sur les trois regimes. Sans cet ecart, la garde
    # ci-dessus serait un accord vide.
    for k in ("r0", "r1", "r2", "r3"):
        reg = r[k]
        assert _bag(reg["port_before"]) != _bag(reg["native"]), (
            "%s : le port d'AVANT #359 est deja d'accord avec le natif -- la garde ne verrouille "
            "plus rien, relire le montage" % reg["tag"])


def test_1147_aoe_generalizes_to_another_board_and_a_friendly_caster(aoe_1147_generalized):
    """6 (#359) : la generalisation -- board DIFFERENT (`MC1_15`) et caster ALLIE des summons.

    Le selecteur ne lit RIEN du caster : `Friends(of: Target)` et `SurroundingUnits(Target, range)`
    referencent la CIBLE. L'etape 4 borne un cote (caster ENNEMI : un port qui referencerait le
    caster rendrait 0) ; celle-ci borne l'autre (caster ALLIE : un port qui filtrerait les cibles
    ennemies -- le reflexe pour une ability offensive, et ce que disent ses `TargetingOptions` --
    rendrait 0 alors que le natif emet).

    Elle tient AUSSI la fidelite PAR CIBLE : un event par entite RETENUE, chacun porte par SA cible
    -- pas un event recopie N fois. Mesure (seed 35130, `MC1_15`) : les trois summons n'y prennent
    pas le meme degat (`(486, 738, 6)` deux fois, `(324, 492, 6)` une fois, un facteur geometrique
    de 1.5) et le port reproduit la ventilation. Cette ventilation-la n'est PAS asserte : elle
    depend des tuiles ou le tirage natif pose les summons, donc de la seed -- l'exiger ferait rougir
    le MONTAGE et non le port. Ce qui est asserte, c'est ce qui ne depend pas du tirage : l'ensemble
    des cibles, et l'egalite des valeurs avec le natif."""
    g = aoe_1147_generalized
    assert not g.get("error"), "montage KO : %s" % g["error"]
    assert g["caster_team_is_target_team"] is True, (
        "le caster n'est PAS allie de la cible : le montage ne borne plus le referent d'equipe")
    assert g["native"], "le natif n'emet rien avec un caster allie : relire le selecteur"
    assert _bag(g["port_after"]) == _bag(g["native"]), (
        "board %s / caster allie : port %s != natif %s"
        % (g["board"], g["port_after"], g["native"]))
    assert _bag(g["port_before"]) != _bag(g["native"]), (
        "le port d'AVANT #359 est deja d'accord ici : la garde ne verrouille rien")
    # Fidelite PAR CIBLE, sur l'axe qui ne depend PAS du tirage : un event par summon retenu, aucun
    # doublon, et exactement les summons -- ce qu'une recopie de la cible principale ne donnerait pas.
    tgts = [e["target"] for e in g["port_after"]]
    assert len(set(tgts)) == len(tgts), "le port emet deux events sur la meme cible : %s" % tgts
    assert set(tgts) <= set(g["summons"]), (
        "le port emet sur %s, hors des summons poses %s" % (sorted(set(tgts)), g["summons"]))
    # RESIDU NOMME, MESURE ici et pas ailleurs : sur ce montage le natif ordonne `%s` et le port
    # `%s` -- les noeuds `SortByRow` / `SortReverse` du selecteur ne sont pas portes. On ne l'ASSERTE
    # pas (l'ordre du port suit `scene.units` et peut coincider par hasard, comme a l'etape 4) : la
    # garde porte sur l'ENSEMBLE, qui est ce que l'utilite SOMME. Le fait est expose par le probe.
    assert isinstance(g["same_order"], bool), "le probe ne rapporte plus la comparaison d'ordre"


def _assert_1148_aoe(r, expect_dir: int):
    """Le corps commun des deux gardes de `1148` (#359-r1) : meme montage, `dir` attendu different.

    Ce que chaque regime tient :
      * RA (cible sur tuile en feu) : le regime DEJA couvert par #350-r3 -- ici il sert de temoin,
        le port d'AVANT y est d'accord ;
      * RB (cible sur tuile FROIDE, un AUTRE ennemi brulant dans SON triangle) : LE regime du pendant
        AoE. Le natif emet -- sur l'autre ennemi, jamais sur la cible demandee -- et le port rendait
        `[]`. C'est aussi le SEUL regime qui exerce la levee du court-circuit `if main is None`
        (#359) : la cible principale y est refusee par `_MAKE_DMG_TARGET_GATE` ;
      * RC (DEUX ennemis sur des tuiles en feu) : le COMPTE, et surtout les VALEURS par cible -- les
        deux ennemis ont des armures pilotees DIFFERENTES, donc une recopie de la prediction
        principale sur chaque membre du set serait visible."""
    assert not r.get("error"), "montage KO : %s" % r.get("error")
    assert r["dir_expected"] == expect_dir, (
        "board %s : `MachineOfWarPosition` du joueur courant a change -- `dir` attendu %s, calcule "
        "%s. Le montage ne borne plus la branche visee du `If`."
        % (r["board"], expect_dir, r["dir_expected"]))
    assert r["dir_confirmed"] is True, (
        "board %s : les tuiles ALLUMEES %s ne sont pas incluses dans le triangle `dir = %s` %s -- "
        "le mirror de `BattleQuery$$GetPositionMachineForPlayer` designerait la mauvaise direction"
        % (r["board"], r.get("fire_measured"), r["dir_expected"], r.get("fire_expected")))
    assert r["cast_ok"], "le cast qui ALLUME la zone a echoue : %s" % r.get("cast_error")
    for k in ("ra", "rb", "rc"):
        assert k in r, "regime %s absent du montage (%s)" % (k, r.get("error"))
        reg = r[k]
        assert _bag(reg["port_after"]) == _bag(reg["native"]), (
            "%s (board %s) : port %s != natif %s"
            % (reg["tag"], r["board"], reg["port_after"], reg["native"]))
    # RB : la cible demandee n'a AUCUN event natif, et pourtant le natif emet. C'est l'ecart que
    # #359-r1 ferme, et la preuve que la boucle du playbook n'est pas `<Target>`.
    rb = r["rb"]
    assert rb["native"], (
        "RB : le natif n'emet plus rien quand la cible est hors zone de feu -- le montage ne "
        "discrimine plus (verifier que l'autre ennemi brule bien DANS le triangle de la cible)")
    assert all(e["target"] != rb["target"] for e in rb["native"]), (
        "RB : le natif emet sur la cible %s alors que sa tuile ne brule pas -- le `Filter(...,"
        " HasEffect(Fire))` du selecteur ne mordrait plus" % rb["target"])
    assert rb["port_before"] == [], (
        "RB : le port d'AVANT #359-r1 emet deja %s -- il avait donc un set AoE pour 1148, et la "
        "garde ne verrouille rien" % (rb["port_before"],))
    # RC : le COMPTE et les VALEURS. Deux armures pilotees -> deux couples de bornes distincts.
    rc = r["rc"]
    assert len(rc["native"]) == 2, (
        "RC : %d event(s) natif(s) pour DEUX ennemis sur tuiles en feu -- le montage n'a pas atteint "
        "son regime" % len(rc["native"]))
    assert len({tuple(e["dmg"]) for e in rc["native"]}) == 2, (
        "RC : les deux events natifs portent les MEMES bornes %s -- les armures pilotees ne "
        "separent plus les cibles, et l'accord serait muet sur les VALEURS"
        % [e["dmg"] for e in rc["native"]])
    assert r["values_discriminate"] is True
    # LE CLIQUET : le port d'AVANT differait. Sans cet ecart, tout ce qui precede est un accord vide.
    assert r["before_differed"] is True, (
        "board %s : le port d'AVANT #359-r1 (registre de classes ampute de `DaemonicOrdnance`) est "
        "deja d'accord avec le natif sur les trois regimes -- la garde ne verrouille rien"
        % r["board"])


def test_1148_emits_one_event_per_enemy_on_a_burning_tile(aoe_1148):
    """7 (#359-r1) : le pendant AoE de `1148`, verrouille par un ECART mesure.

    `DaemonicOrdnancePlaybook$$MakeDamagePredictions` boucle sur
    `GetEntitiesFromSelector(DaemonicOrdnanceAbility$$GetAllDamageableTargets, ...)` =
    `Enemies(Caster, Units(Filter(GetTargetAreaTiles(), HasEffect(Tiles(Subject), 5 = Fire))))`.
    #350-r3 n'avait porte que le GATE de la cible principale (reduction exacte : la zone est ancree
    SUR elle, donc la contient toujours) ; le SET, lui, restait vide -- si bien qu'une cible hors
    zone de feu avec un autre ennemi dedans rendait `[]` cote port et un event cote natif.

    MESURE (`MC1_67`, niveau 50, armures 0 / 500) : RB natif `1` event, port d'AVANT `0` ; RC natif
    `2` events aux bornes distinctes, port d'AVANT `1`."""
    _assert_1148_aoe(aoe_1148, expect_dir=1)


def test_1148_aoe_generalizes_to_a_board_where_the_triangle_flips(aoe_1148_other_dir):
    """8 (#359-r1) : la GENERALISATION -- un board ou le predicat de plateau BASCULE.

    `GetTargetAreaTiles` = `TilesOnSameElevation(Target, TilesInTriangleShape(Target,
    If(IsPositionMachineForCurrentPlayer(2), Direct(1), Direct(4))), 1)`. `MC1_67` declare
    `MachineOfWarPosition(team 1) = 2` -> `dir = 1` (triangle `{S, SE}`) ; `C1_15` declare `0` ->
    `dir = 4` (`{NW, N}`). Un port qui coderait la direction en dur -- ou qui laisserait le canal
    `Scene.machine_of_war_position` non branche, ce qui rend le predicat FAUX d'office -- passe le
    test precedent et ECHOUE ici. Les deux ensemble bornent les DEUX branches du `If`.

    ⚠ RESIDU NOMME, mesure ici : sur `C1_15` le natif allume `{(3,3), (3,4)}` alors que le triangle
    en compte TROIS -- `(2,3)` reste froide. Ni l'elevation (`(3,3)` a la MEME et brule) ni un trou
    d'observation (`tileMeta` projette bien `(2,3)`) ne l'expliquent ; la seule covariable mesuree
    est `walkable = False`. Ni `BattleQuery$$GetTilesInTriangleShape` ni
    `TilesOnSameElevationSelector$$Select` ne filtrent la marchabilite (decompile relu) : l'ecart est
    donc dans la POSE de l'effet, hors du perimetre de cette tranche. Il est INERTE pour ce
    selecteur -- une unite ne se tient pas sur une tuile non marchable, donc `Units(<tuile non
    marchable>)` rend vide de toute facon -- d'ou une garde par INCLUSION (les tuiles allumees sont
    dans le triangle attendu, centre compris) et non par egalite."""
    _assert_1148_aoe(aoe_1148_other_dir, expect_dir=4)
    r = aoe_1148_other_dir
    assert set(map(tuple, r["fire_measured"])) < set(map(tuple, r["fire_expected"])), (
        "sur %s le natif allume desormais TOUT le triangle %s : le residu « tuile non marchable non "
        "allumee » a disparu, et le commentaire ci-dessus est a relire"
        % (r["board"], r["fire_expected"]))
