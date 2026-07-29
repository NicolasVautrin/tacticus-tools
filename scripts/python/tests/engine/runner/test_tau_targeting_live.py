"""#250 -- GARDE des masques de ciblage des CINQ abilities du module `tau`.

  id    ability                   forme de ctor            rules effectives      TargetingRange
  ----  ------------------------  -----------------------  --------------------  -----------------
  1077  EarlyWarningOverride      3 PRESET STATIQUE COPIE  0x8004                statics+0x60 SELF
  1081  FightingRetreat           1 FLAGS DIRECTS          0x802                 statics+0x30 ADJ
  1082  InspiredToGreatness       1 FLAGS DIRECTS          0x402                 statics+0x30 ADJ
  1160  HeavyRailRifle            1 FLAGS DIRECTS          0x10400040004000      statics+0x48 BOARD
  1161  TwinSmartMissileSystem    1 FLAGS DIRECTS          0x40004000            statics+0x48 BOARD

1077 n'appelle AUCUN `IdunBattle.Core.Services.TargetingOptions$$.ctor` : son masque effectif est la
constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` =
`*(statics+0x2a8)`. 1160 et 1161 sortent de la MEME MoW (`tauBroadside`) et de la MEME forme de ctor
avec des masques DIFFERENTS. Detail complet : `docs/rl/case-250-tau-targeting.md`.

CE QUE CE TEST VERROUILLE, et pourquoi il ECHOUE sans les masques : sans `TARGETING_OPTIONS`,
`get_invalid_target_reason` rend 0 immediatement (`options is None` => aucun gate) et le moteur
ACCEPTE des casts que `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE. Le test
mesure sur le MEME etat fige le natif (oracle `abilityReason`), le port APRES et le port AVANT
(`TARGETING_OPTIONS = None`, l'etat de `master`), et exige par ability :
  1. accord natif/APRES sur toutes les lignes, SAUF les residus NOMMES (regle native que le port ne
     porte pas -- il rend alors 0, degradation permissive) ;
  2. au moins une ligne ou le natif REFUSE alors qu'AVANT rendait 0 ;
  3. les contrefactuels : le masque prive de ses REGLES, puis de son `TargetingRange`, faux-accepte
     bien des lignes -- un volet dont la neutralisation ne change RIEN n'est pas valide par la mesure.

Le montage (build MoW-capable + `MachineOfWarAmmo` patche hors `data/` + drive des positions) et les
trois lectures vivent dans `scripts/python/probe_250_tau_targeting.py` (le probe MESURE, ce test
GARDE) -- une seule implementation, aucune divergence possible entre les deux. UN SEUL runner pour
les cinq abilities (fixture de module). Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only.
"""
from __future__ import annotations

import pytest

import probe_250_tau_targeting as P

BOARD = "C4_09"      # MoW-capable (MachineOfWarPosition pose pour les DEUX camps)
SEED = 777


@pytest.fixture(scope="module")
def tau_measures(live_session):
    """UN SEUL runner pour les cinq abilities : le montage est identique, seul le caster change."""
    stats, dispose = P.measure_all(live_session, SEED, BOARD)
    try:
        yield stats
    finally:
        dispose()


def _one(stats, aid):
    s = stats.get(aid)
    assert s is not None, "ability %d non mesuree (porteur absent du plateau)" % aid
    assert s["usable"], (
        "%d non utilisable -> `AttackQuery.GetInvalidTargetReason` court-circuite sur "
        "`ActiveAbility.CanCurrentlyBeUsed` et rend 0x1 pour la MAUVAISE raison : rien de mesurable"
        % aid)

    # 1) ACCORD. Une ligne « residu » est un refus NATIF prononce par une regle que le port ne
    #    modelise pas (nommee dans `probe_250.CASES`), ou le port rend 0 : permissif, jamais un
    #    refus invente. Tout le reste doit s'accorder -- c'est CETTE assertion qui tombe si le
    #    masque disparait.
    mismatch = [(r["label"], hex(r["nat"] or 0), hex(r["apres"])) for r in s["rows"]
                if r["nat"] != r["apres"] and not (r["nat"] in s["residus_codes"]
                                                   and r["apres"] == 0)]
    assert not mismatch, "desaccord natif/port sur %d : %s" % (aid, mismatch)

    # 2) le masque SERT : au moins une ligne ou le natif REFUSE et ou `master` rendait 0.
    assert s["gain"] > 0, (
        "aucune ligne ou le masque de %d change le verdict -> ce test ne garderait rien "
        "(il passerait aussi sans `TARGETING_OPTIONS`)" % aid)
    return s


def test_1077_early_warning_override(tau_measures):
    """0x8004 = `CasterMatchesDynamicRule | CasterIsPossibleTarget` : AUCUN bit de refus du filtre
    CIBLE. C'est le `TargetingRange statics+0x60` = `RANGE_SELF` (`overrideRange = 0`) qui porte tout
    le refus -- l'ability est SELF, et toute cible autre que le caster rompt sur `TargetIsInRange`."""
    s = _one(tau_measures, 1077)
    assert s["cf_range"] > 0, (
        "neutraliser le `TargetingRange` de 1077 devrait faux-accepter des lignes : sans ca le volet "
        "PORTEE n'est pas valide par cette mesure")
    assert s["cf_rules"] == 0, (
        "les deux bits de 0x8004 ne sont PAS des regles de refus du filtre cible (bit 2 = volet "
        "CASTER non porte, bit 15 = flag declaratif) : neutraliser `rules` ne doit donc RIEN "
        "changer. Si ca change, la lecture du masque est fausse.")


def test_1081_fighting_retreat(tau_measures):
    """0x802 = `TargetMatchesDynamicRule | AddCasterIfAtLeastOneTarget` : aucun bit de camp
    (`refuses_all_enemy_targets` reste False), aucune regle statique. Le refus vient du
    `TargetingRange statics+0x30` = `RANGE_ADJACENT` -> `AreEntitiesAdjacent`.

    Sa regle DYNAMIQUE est portee (#247) mais reste INERTE dans CE montage (Darkstrider y a un
    ennemi au contact, donc `Any(GetAdjacentEnemies)` court-circuite). Le montage ou elle MORD est
    un test SEPARE (`test_dynamic_rules_bite_and_flip`) -- confondre les deux ferait passer ce
    test-ci pour une preuve qu'il n'apporte pas."""
    s = _one(tau_measures, 1081)
    assert s["cf_range"] > 0, "le volet PORTEE de 1081 n'est pas exerce par cette mesure"
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import refuses_all_enemy_targets
    assert not refuses_all_enemy_targets(ABILITY_CLASSES[1081].TARGETING_OPTIONS), (
        "1081 ne porte NI TargetIsFriendly NI TargetIsCaster -> poser son masque ne doit deplacer "
        "aucun routage d'action cote IA")


def test_1082_inspired_to_greatness(tau_measures):
    """0x402 = `TargetMatchesDynamicRule | TargetIsFriendly` : le SEUL des cinq a porter une regle de
    CAMP. Les TROIS volets mordent -- `TargetIsFriendly` sur les ennemis, `RANGE_ADJACENT` sur les
    allies hors contact, et la regle DYNAMIQUE (#247) sur le caster lui-meme et sur l'allie au
    contact a pleins PV dont l'actif n'est pas consomme."""
    s = _one(tau_measures, 1082)
    assert s["cf_rules"] > 0, "le bit TargetIsFriendly de 1082 n'est pas exerce par cette mesure"

    # LE REGIME QUE LE VOLET PORTEE EXIGE, asserte AVANT son contrefactuel -- sinon un montage
    # degrade rendrait `cf_range == 0` sans dire POURQUOI. Depuis #247, un allie hors contact a
    # PLEINS PV est refuse DEUX FOIS : `RANGE_ADJACENT` (qui precede, d'ou le `TargetIsInRange`
    # natif) ET la regle dynamique (`0x1`). Neutraliser la portee ne fait alors rien apparaitre.
    # Il FAUT donc que l'allie hors contact soit BLESSE (`IsDamagedUnit` d'`EntityCanBeHealed` ->
    # la regle dynamique accepte), et c'est `probe_250.measure_all` qui l'y amene.
    far_allies = [r for r in s["rows"]
                  if r["label"].startswith("ALLIE ") and r["dist"] not in (None, 0, 1)]
    assert far_allies, (
        "aucune cible ALLIEE hors contact dans la mesure -- le volet PORTEE de 1082 n'a alors "
        "aucune ligne ou mordre : %s" % [(r["label"], r["dist"]) for r in s["rows"]])
    assert any(r["hp"] is not None and r["hp_max"] is not None and r["hp"] < r["hp_max"]
               for r in far_allies), (
        "l'allie hors contact doit etre BLESSE : a pleins PV la regle dynamique de #247 refuse "
        "DEJA la ligne (0x1) et le contrefactuel `sansRange` ne peut plus exposer de faux-accept "
        "-- %s" % [(r["label"], r["dist"], r["hp"], r["hp_max"]) for r in far_allies])
    assert s["cf_range"] > 0, "le volet PORTEE de 1082 n'est pas exerce par cette mesure"
    assert s["cf_dyn"] >= 2, (
        "#247 : desarmer `InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason` doit "
        "faire redivergir les 2 lignes qu'elle tranche (le caster lui-meme, et l'allie au contact "
        "non eligible). Un contrefactuel a 0 signifie que la regle ne garde RIEN -- %d ligne(s)"
        % s["cf_dyn"])
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import refuses_all_enemy_targets
    assert refuses_all_enemy_targets(ABILITY_CLASSES[1082].TARGETING_OPTIONS), (
        "1082 porte TargetIsFriendly -> `refuses_all_enemy_targets` doit valoir True (l'ability "
        "soigne un ALLIE ; c'est le verdict natif que le masque manquant cachait)")


def test_1160_heavy_rail_rifle(tau_measures):
    """0x10400040004000 : `TargetIsEnemy` mord sur les allies et sur la MoW elle-meme. Le bit 46
    `TargetIsActor` ELARGIT le domaine -- la MoW ENNEMIE est une cible LEGALE."""
    s = _one(tau_measures, 1160)
    assert s["cf_rules"] > 0, "le bit TargetIsEnemy de 1160 n'est pas exerce par cette mesure"
    assert s["cf_range"] == 0, (
        "`RANGE_WHOLE_BOARD` -> le filtre statique NE TESTE AUCUNE portee : neutraliser le "
        "`TargetingRange` ne doit rien changer pour 1160")
    mow = [r for r in s["rows"] if "/MoW" in r["label"]]
    assert mow and all(r["nat"] == 0 for r in mow), (
        "le bit 46 `TargetIsActor` rend la MoW ENNEMIE legale pour 1160 : le natif doit l'ACCEPTER "
        "(c'est le seul discriminant vis-a-vis de 1161, meme porteur, meme forme de ctor) -- %s"
        % [(r["label"], hex(r["nat"] or 0)) for r in mow])


def test_1161_twin_smart_missile_system(tau_measures):
    """0x40004000 : MEME porteur et MEME `TargetingRange` que 1160, SANS le bit 46 -> une cible
    MACHINE rompt sur `TargetIsUnit` (bit 45, tete de domaine). Le contre-exemple qui interdit de
    generaliser un masque depuis sa voisine."""
    s = _one(tau_measures, 1161)
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    mow = [r for r in s["rows"] if "/MoW" in r["label"]]
    assert mow and all(r["nat"] == int(TR.TargetIsUnit) for r in mow), (
        "sans le bit 46, la MoW ENNEMIE doit rompre sur TargetIsUnit pour 1161 -- %s"
        % [(r["label"], hex(r["nat"] or 0)) for r in mow])
    assert s["cf_rules"] > 0, "le bit TargetIsEnemy de 1161 n'est pas exerce par cette mesure"


# ------------------------------------------------------------------------------------------------
# #247 -- LES DEUX REGLES DYNAMIQUES, dans le montage ou elles MORDENT, et son BASCULEMENT
# ------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tau_bites(live_session):
    """RUNNER SEPARE : la geometrie qui fait mordre 1081 est INCOMPATIBLE avec celle du montage
    principal (elle exige Darkstrider SANS ennemi au contact, l'autre lui en met un). Deux montages
    distincts, pas un compromis qui n'exercerait ni l'un ni l'autre."""
    res, dispose = P.measure_dynamic_bites(live_session, SEED, BOARD)
    try:
        yield res
    finally:
        dispose()


def test_dynamic_rules_bite_and_flip(tau_bites):
    """LE test des deux `GetDynamicInvalidTargetReason` -- et il asserte les DEUX SENS.

    T1 (Darkstrider ISOLE, Aun'Shi a son contact) :
      * 1081 -> `0x2 TargetMatchesDynamicRule` : ni ennemi adjacent, ni allie a `RangedSpecialist`
        DESACTIVE. C'est le montage que #250 n'avait PAS, et sans lequel le port de 1081 serait
        pose en aveugle (un contrefactuel a 0 ne valide rien) ;
      * 1082 -> `0x1 ValidRequest` : cible a pleins PV, non-mecanique, actif non consomme.
    T2 (un ennemi amene AU CONTACT de Darkstrider et l'ATTAQUE) : les deux passent a 0, par DEUX
    disjuncts differents (`GetAdjacentEnemies` non vide / `EntityCanBeHealed` sur un blesse).

    Un port qui refuserait TOUJOURS passerait T1 et tomberait en T2 ; un port permissif (l'etat
    d'avant #247) tomberait en T1. Les deux moities sont necessaires.

    ⚠ LA MOITIE 1082 DE T2 EXIGE DES DEGATS REELS, pas seulement le contact. Le montage d'origine
    envoyait `applyAction{"kind": "attack"}` -- une action QUI N'EXISTE PAS : `applyOneAction`
    (`frida/hooks/features/ai-step/internals.ts`) ne connait que `move | ability | finish |
    endturn` et rend `ok:false, error:"unknown kind: attack", mutated:false`. Le retour n'etant pas
    lu, le montage mesurait `7530 -> 7530` en croyant avoir frappe : 1081 basculait (l'ennemi est
    bien la) mais 1082 restait a `0x1`, port et natif D'ACCORD -- un rouge de MONTAGE. L'attaque
    normale est une ABILITY (`probe_250._wound`), d'ou l'assertion de PV ci-dessous : elle garde le
    regime, pas seulement le verdict."""
    r = tau_bites
    assert r["geometry_ok"], (
        "geometrie non atteinte (d_ally=%s d_foe=%s) : la regle de 1081 n'est pas exercee"
        % (r["d_ally"], r["d_foe"]))

    n1, p1, d1 = r["t1_1081"]
    assert n1 == 0x2, ("T1 : le natif doit refuser 1081 sur `TargetMatchesDynamicRule` (0x2) "
                       "quand Darkstrider n'a aucun ennemi au contact -- natif=%s" % hex(n1 or 0))
    assert p1 == n1, "T1 1081 : port=%s natif=%s" % (hex(p1), hex(n1))
    assert d1 == 0, ("T1 1081 : desarmer la regle dynamique doit RE-ACCEPTER la ligne "
                     "(contrefactuel) -- sansDyn=%s" % hex(d1))

    n2, p2, d2 = r["t1_1082"]
    assert n2 == 0x1, ("T1 : le natif doit refuser 1082 sur le litteral `ValidRequest` (0x1) pour "
                       "un allie au contact non eligible -- natif=%s" % hex(n2 or 0))
    assert p2 == n2, "T1 1082 : port=%s natif=%s" % (hex(p2), hex(n2))
    assert d2 == 0, ("T1 1082 : desarmer la regle dynamique doit RE-ACCEPTER la ligne "
                     "(contrefactuel) -- sansDyn=%s" % hex(d2))

    assert r["d_foe_t2"] == 1, ("T2 : l'ennemi doit etre AU CONTACT de Darkstrider (d=%s) -- sans "
                                "ca le basculement n'est pas provoque" % r["d_foe_t2"])
    # BLESSER et METTRE AU CONTACT sont deux regimes DISTINCTS, et 1082 exige AUSSI que la portee
    # `RANGE_ADJACENT` reste franchie : le `necroWarden` etant RANGED, il peut parfaitement blesser
    # a d=3 sans jamais venir au contact (mesure `C3_26`/31337). Les trois conditions sont donc
    # asserees separement, pour que l'echec DISE laquelle manque.
    assert r["d_ally_t2"] == 1, ("T2 : Aun'Shi doit rester AU CONTACT de Darkstrider (d=%s), sinon "
                                 "1082 rompt sur la portee et non sur sa regle dynamique"
                                 % r["d_ally_t2"])
    hp_before, hp_after = r["hp_before"], r["hp_after"]
    assert (hp_after[0] is not None and hp_before[0] is not None
            and hp_after[0] < hp_before[0]), (
        "T2 : Darkstrider doit avoir ete BLESSE (%s -> %s) -- c'est le disjunct `IsDamagedUnit` "
        "d'`EntityCanBeHealed` que ce volet exerce" % (hp_before, hp_after))

    n3, p3, _ = r["t2_1081"]
    assert n3 == 0 and p3 == 0, ("T2 1081 : un ennemi au contact leve le refus (natif=%s port=%s)"
                                 % (hex(n3 or 0), hex(p3)))
    n4, p4, _ = r["t2_1082"]
    assert n4 == 0 and p4 == 0, ("T2 1082 : une cible BLESSEE est soignable, donc legale "
                                 "(natif=%s port=%s)" % (hex(n4 or 0), hex(p4)))
