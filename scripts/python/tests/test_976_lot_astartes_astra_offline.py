"""#976 -- les cinq faces DECISION du lot Astartes / Astra Militarum, gardees OFFLINE.

Cinq abilities de kit `lineup`, ventilees par ce que leur playbook natif fait REELLEMENT :

    1154 TacticalPrecision   PORTEE   -- selecteur + entrees a DEUX branches (`WillBeCharging`)
    1231 TitanhammerSquad    PORTEE   -- `NonComparablePlaybook`, utilite de COMPTE
    1225 StrikeFromTheShadows CONSTANTE -- le playbook natif EST le chemin generique du port
    1204 LeadingTheCharge     CONSTANTE -- idem
    1026 BasiliskBarrage     RESIDU   -- 3 batchs d'obus ponderes, non porte (cf. `#976-r1`)

CE QUE CE FICHIER GARDE, ET POURQUOI IL EST NECESSAIRE
------------------------------------------------------
Les deux verdicts CONSTANTE sont les plus fragiles du lot : ils affirment une NON-ACTION. Rien
dans le code ne les porte -- ils ne survivent que tant que personne n'ajoute a 1225 / 1204 un
override « par analogie » avec un voisin de forme. Les etages 4 et 5 transforment cette absence en
CRAN : ils exigent que ces deux abilities restent hors des quatre registres d'override, ET qu'elles
restent dans le registre d'ARRONDI ou la lecture #350 les a rangees (1225 en forme (b), 1204 en
forme (a2)) -- deux formes DIFFERENTES, donc un test qui ne peut pas passer par accident.

Chaque etage porte sa CONTRE-EPREUVE : la mutation est jouee, le rouge est constate, l'etat est
restaure, et le vert est re-verifie. Un garde qu'on n'a pas vu mordre ne prouve rien.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gameconfig as GC                                          # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine.dsl import nodes as dsl                              # noqa: E402
from engine.entities.abilities.ability_configuration import AbilityConfiguration  # noqa: E402
from engine.entities.abilities import active_ability as AA       # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.playbook import REGISTRY as SE_REGISTRY              # noqa: E402
from engine.playbook.noncomparable import PLAYBOOKS              # noqa: E402
from engine.playbook.prediction import abilities as PA           # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`). Perimetre pris LARGE :
#: les etages 5 et 6 gardent des NON-ACTIONS (aucun override sur 1225 / 1204 / 1026), donc tout
#: fichier capable d'AJOUTER un override doit rejouer ce test -- pas seulement ceux qu'il lit.
DECLENCHEUR = {
    "chemins": (
        # Les DEUX foyers de registres que les etages 1, 2, 5 et 6 confrontent.
        "scripts/python/engine/playbook/prediction/abilities.py",
        "scripts/python/engine/entities/abilities/active_ability.py",
        # Le `__init__` du paquet est traverse a l'import d'`active_ability` (fermeture #486-r15).
        "scripts/python/engine/entities/abilities/__init__.py",
        # Le `ShouldExecute` de 1154 (etage 3) et le registre `REGISTRY` qui le porte.
        "scripts/python/engine/playbook/should_execute_gates.py",
        "scripts/python/engine/playbook/base.py",
        # La face DECISION de 1231 (etage 4) et le registre `PLAYBOOKS`.
        "scripts/python/engine/playbook/noncomparable/titanhammer_squad.py",
        "scripts/python/engine/playbook/noncomparable/__init__.py",
        # `will_be_charging` / `count_adjacent` / `is_adjacent` : le SUBSTRAT des etages 1, 3 et 4,
        # et la cible des trois contre-epreuves (elles substituent des noms de CE module).
        "scripts/python/engine/battle_query.py",
        # Le selecteur `AdjacentEnemies` et `_within`/`_is_alive` : l'etage 1 en depend
        # ENTIEREMENT, et c'est `_is_alive` qui l'a fait rougir a la premiere ecriture.
        "scripts/python/engine/dsl/base.py",
        "scripts/python/engine/entities/selectors/units.py",
        # Etage 6 : les deux etages de shells deja portes cote COMBAT, dont le residu #976-r1
        # se servira.
        "scripts/python/engine/runner/abilities/astramilitarum.py",
    ),
    # Les etages 2 et 5 LISENT le gameconfig (`nrOfHits_2`, `damageProfile_2`, `minDmg_2`) et le
    # dump de symboles : un changement de BUILD peut donc changer le verdict sans qu'aucun fichier
    # Python ne bouge. On le declare au lieu de le taire.
    "build": True,
    "toujours": True,
    "raison": ("les etages 2 et 5 lisent le GAMECONFIG du build courant (`nrOfHits_2`, "
               "`damageProfile_2`, `minDmg_2`/`maxDmg_2` de 1154) ; un changement de build peut "
               "inverser leur verdict sans qu'aucun chemin ci-dessus ne soit touche."),
}

TP = int(ActiveAbilityType.TacticalPrecision)        # 0x482 = 1154
THS = int(ActiveAbilityType.TitanhammerSquad)        # 0x4cf = 1231
SFS = int(ActiveAbilityType.StrikeFromTheShadows)    # 0x4c9 = 1225
LTC = int(ActiveAbilityType.LeadingTheCharge)        # 0x4b4 = 1204
BB = int(ActiveAbilityType.BasiliskBarrage)          # 0x402 = 1026


# =================================================================================================
#  Substrats minimaux
# =================================================================================================

class _Caster:
    """`UnitContext` minimal -- seuls les accesseurs que `AActiveAbility` traverse."""
    visual_id = "ultraTitus"
    damage_type = 0
    is_melee = True
    extra_hits_melee = 0

    def stat(self, *a, **k):
        return 0


def _unit(uid, col, row, team):
    """⚠ `hp`/`hpMax` sont OBLIGATOIRES : `engine.dsl.base._is_alive` mirrore
    `HealthComponent$$IsAlive`, dont la 1re branche est `RemainingValue >= 1`. Un dict portant
    `alive: True` mais sans PV en sort MORT, et TOUT selecteur d'occupation rend alors `[]` --
    silencieusement. C'est ce qui a fait rougir l'etage 1 a sa premiere ecriture, et c'est
    exactement la forme de faux negatif que ce fichier doit eviter de reproduire."""
    return {"id": uid, "pos": {"col": col, "row": row}, "team": team, "alive": True,
            "hp": 1000, "hpMax": 1000}


def _ability(name, aid):
    cfg = AbilityConfiguration.from_gameconfig(name, GC.ability(name))
    assert cfg is not None, "gameconfig absent pour %s" % name
    return AA.active_ability_for(name, aid, _Caster(), cfg,
                                 ability_state={"level": 50, "multiplier": 100}), cfg


def _dctx(units, caster, target, cfg, caster_pos):
    return dsl.DslContext(units=units, caster=caster, target=target, config=cfg,
                          ability_level=50, times_attacked=0, caster_pos=caster_pos,
                          elev_by_pos=None, board=None)


# =================================================================================================
#  ETAGE 1 -- 1154 : le SELECTEUR bascule sur `WillBeCharging`, et la bascule MORD
# =================================================================================================

def test_etage1_1154_selecteur_deux_branches():
    """`TacticalPrecisionPlaybook$$MakeDamagePredictions` : `sel = Target` si `WillBeCharging`,
    `AdjacentEnemies(Caster, unique, sel: 3)` sinon.

    Montage : caster en (2,2), cible en (3,2) DEJA adjacente, un second ennemi en (2,3) adjacent
    lui aussi. Depuis l'origine, la cible n'est PAS nouvellement adjacente -> NON-CHARGING ; depuis
    une tuile eloignee (5,5) elle ne l'est pas davantage. La bascule CHARGING s'obtient en partant
    d'une position d'ou la cible N'ETAIT PAS adjacente : on la fabrique en placant le caster loin
    et en evaluant un pas qui l'amene au contact."""
    ab, cfg = _ability("TacticalPrecision", TP)
    tgt = _unit(20, 3, 2, 2)
    other = _unit(21, 2, 3, 2)

    # --- NON-CHARGING : caster DEJA au contact, aucun nouveau contact ---------------------------
    caster_here = _unit(10, 2, 2, 1)
    units = [caster_here, tgt, other]
    ctx = _dctx(units, caster_here, tgt, cfg, (2, 2))
    got = ab.get_aoe_targets(ctx)
    assert ab.tp_will_be_charging is False, "pas de nouveau contact -> NON-CHARGING"
    ids = sorted(u.get("id") for u in got)
    assert ids == [20, 21], "AdjacentEnemies(Caster) = les DEUX ennemis adjacents, got %s" % ids

    # --- CHARGING : le pas candidat AMENE la cible au contact ------------------------------------
    caster_far = _unit(10, 6, 6, 1)
    units2 = [caster_far, tgt, other]
    ctx2 = _dctx(units2, caster_far, tgt, cfg, (3, 3))   # (3,3) est adjacent a (3,2)
    got2 = ab.get_aoe_targets(ctx2)
    assert ab.tp_will_be_charging is True, "nouveau contact -> CHARGING"
    assert [u.get("id") for u in got2] == [20], \
        "branche CHARGING : le selecteur EST `Target` (mono-cible), got %s" % got2

    # --- CONTRE-EPREUVE : neutraliser `will_be_charging` doit CHANGER la branche -----------------
    vrai = bq.will_be_charging
    try:
        bq.will_be_charging = lambda *a, **k: False
        got3 = ab.get_aoe_targets(ctx2)
        assert ab.tp_will_be_charging is False
        assert [u.get("id") for u in got3] != [20], \
            "MUTATION NON MORDANTE : la branche n'a pas change -> le garde ne prouve rien"
    finally:
        bq.will_be_charging = vrai
    got4 = ab.get_aoe_targets(ctx2)                       # VERT restaure
    assert ab.tp_will_be_charging is True and [u.get("id") for u in got4] == [20]


# =================================================================================================
#  ETAGE 2 -- 1154 : les ENTREES suivent la MEME branche (et lisent bien les variables `_2`)
# =================================================================================================

def test_etage2_1154_entrees_par_branche():
    """CHARGING -> `{}` (chemin generique) ; NON-CHARGING -> `minDmg_2`/`maxDmg_2`, `nrOfHits_2`,
    `damageProfile_2`. Les trois clefs sont LUES au gameconfig, pas recopiees d'un litteral."""
    ab, cfg = _ability("TacticalPrecision", TP)
    c = cfg.constants or {}
    assert c.get("nrOfHits") == "1" and c.get("nrOfHits_2") == "3", \
        "le gameconfig de 1154 a change -- la RE de ce test est perimee : %s" % c
    assert c.get("damageProfile") == "Bolter" and c.get("damageProfile_2") == "Chain"

    ab.tp_will_be_charging = True
    assert PA._tactical_precision_inputs(None, 10, 20, ab, cfg) == {}, \
        "branche CHARGING = chemin generique : AUCUN override ne doit figer le defaut"

    ab.tp_will_be_charging = False
    out = PA._tactical_precision_inputs(None, 10, 20, ab, cfg)
    assert out.get("hits_override") == 3, "hits = GetNumberConstant(0x32 = nrOfHits_2), NU"
    assert out.get("profile_override") == "Chain", "profil = damageProfile_2"
    mn = cfg.get_variable_for_level("minDmg_2", 50, 0, 100)
    mx = cfg.get_variable_for_level("maxDmg_2", 50, 0, 100)
    mn1 = cfg.get_variable_for_level("minDmg", 50, 0, 100)
    assert mn and mx, "minDmg_2 / maxDmg_2 absents du gameconfig -- RE perimee"
    assert mn != mn1, ("REGIME DEGENERE : minDmg_2 == minDmg, ce test ne discriminerait "
                       "plus les deux paires de variables")
    from engine.dsl.base import calculate_average
    assert out.get("base_override") == calculate_average(mn, mx), \
        "base = forme (b) : troncature de la moyenne, sur la paire `_2`"
    assert out["base_override"] != ab.get_damage(), \
        "REGIME DEGENERE : la branche NON-CHARGING rend la MEME base que le defaut"

    # --- CONTRE-EPREUVE : sans l'attribut, on retombe sur le comportement d'AVANT le port --------
    del ab.tp_will_be_charging
    assert PA._tactical_precision_inputs(None, 10, 20, ab, cfg) == {}


# =================================================================================================
#  ETAGE 3 -- 1154 : `ShouldExecute`, DEUX clauses, chacune mordante SEULE
# =================================================================================================

class _Scene:
    def __init__(self, units, elev=None):
        self.units = units
        self.elev_by_pos = elev

    def _u(self, uid):
        return next((u for u in self.units if u.get("id") == uid), None)

    def pos(self, uid):
        u = self._u(uid)
        p = (u or {}).get("pos") or {}
        return (p["col"], p["row"]) if p.get("col") is not None else None

    def team(self, uid):
        return (self._u(uid) or {}).get("team")


class _Ctx:
    def __init__(self, scene, uid):
        self.scene, self.uid = scene, uid


def test_etage3_1154_should_execute_deux_clauses():
    """`WillBeCharging(caster, casterTile, target) || Count(AdjacentEnemies(Caster)) > 1`."""
    pb = SE_REGISTRY[TP]

    # (a) UN SEUL ennemi adjacent, aucun nouveau contact -> les DEUX clauses fausses -> REFUS
    caster = _unit(10, 2, 2, 1)
    sc = _Scene([caster, _unit(20, 3, 2, 2)])
    assert pb.should_execute(_Ctx(sc, 10), (2, 2), 20, TP, 5.0) is False, \
        "1 ennemi adjacent et pas de charge -> le natif REFUSE"

    # (b) clause 2 SEULE : deux ennemis adjacents, toujours aucun nouveau contact -> ACCEPTE
    sc2 = _Scene([caster, _unit(20, 3, 2, 2), _unit(21, 2, 3, 2)])
    assert pb.should_execute(_Ctx(sc2, 10), (2, 2), 20, TP, 5.0) is True, \
        "2 ennemis adjacents -> `Count > 1` accorde"

    # (c) clause 1 SEULE : un seul ennemi, mais le pas candidat l'amene au contact -> ACCEPTE
    caster_far = _unit(10, 6, 6, 1)
    sc3 = _Scene([caster_far, _unit(20, 3, 2, 2)])
    assert pb.should_execute(_Ctx(sc3, 10), (3, 3), 20, TP, 5.0) is True, \
        "`WillBeCharging` seul suffit -- le `||` est un COURT-CIRCUIT"

    # --- CONTRE-EPREUVES : neutraliser CHAQUE clause doit faire tomber le cas qu'elle porte ------
    vrai_wbc, vrai_cnt = bq.will_be_charging, bq.count_adjacent
    try:
        bq.will_be_charging = lambda *a, **k: False
        assert pb.should_execute(_Ctx(sc3, 10), (3, 3), 20, TP, 5.0) is False, \
            "MUTATION NON MORDANTE sur la clause WillBeCharging"
        assert pb.should_execute(_Ctx(sc2, 10), (2, 2), 20, TP, 5.0) is True, \
            "la clause 2 doit rester porteuse quand la clause 1 est neutralisee"
    finally:
        bq.will_be_charging = vrai_wbc
    try:
        bq.count_adjacent = lambda *a, **k: 0
        assert pb.should_execute(_Ctx(sc2, 10), (2, 2), 20, TP, 5.0) is False, \
            "MUTATION NON MORDANTE sur la clause de comptage"
    finally:
        bq.count_adjacent = vrai_cnt
    assert pb.should_execute(_Ctx(sc2, 10), (2, 2), 20, TP, 5.0) is True     # VERT restaure


# =================================================================================================
#  ETAGE 4 -- 1231 : dispatch NonComparable + formule de comptage
# =================================================================================================

def test_etage4_1231_noncomparable_et_comptage():
    """1231 quitte le chemin COMPARABLE (aucun `Make*Predictions` natif) et son utilite est le
    COMPTE d'ennemis DISTINCTS autour de la TUILE visee."""
    assert AA.makes_damage_predictions("TitanhammerSquad") is False, \
        "1231 doit etre dispatchee NonComparable"
    pb = PLAYBOOKS.get(THS)
    assert pb is not None and pb.MIN_UTILITY == 1.0, "`.cctor` = Fix64(1)"

    class _NC:
        uid = 10
        origin = (0, 0)
        elev_by_pos = None
        neigh_by_pos = {}
        obs_units = []
        debug = False
        enemies = [{"id": 20, "pos": {"col": 3, "row": 2}},
                   {"id": 21, "pos": {"col": 4, "row": 2}},
                   {"id": 22, "pos": {"col": 9, "row": 9}}]

    # tuile visee (3,3) : 20 et 21 sont a <= 2 pas, 22 est loin.
    util = pb.evaluate_non_comparable((0, 0), (3, 3), _NC())
    assert util == 2.0, "deux ennemis DISTINCTS dans la double couronne, got %s" % util

    # DEDOUBLONNAGE (`PooledHashSet`) : un ennemi voisin de PLUSIEURS tuiles ne compte qu'UNE fois.
    class _NC1(_NC):
        enemies = [{"id": 20, "pos": {"col": 3, "row": 3}}]
    assert pb.evaluate_non_comparable((0, 0), (3, 3), _NC1()) == 1.0, \
        "l'occupant de la tuile visee est adjacent a TOUTE sa couronne -- il ne compte qu'une fois"

    # CONTRE-EPREUVE : aucun ennemi -> 0 < MIN_UTILITY, donc AUCUN candidat n'est genere.
    class _NC0(_NC):
        enemies = []
    assert pb.evaluate_non_comparable((0, 0), (3, 3), _NC0()) == 0.0
    assert _NC0.enemies == [] and pb.MIN_UTILITY > 0.0, \
        "MUTATION NON MORDANTE : sans ennemi, le gate `minUtility` doit refuser"


# =================================================================================================
#  ETAGE 5 -- 1225 et 1204 : le verdict CONSTANTE, transforme en CRAN
# =================================================================================================

_REGISTRES_D_OVERRIDE = (
    ("_MAKE_DMG_INPUT_OVERRIDES", lambda: {int(k) for k in PA._MAKE_DMG_INPUT_OVERRIDES}),
    ("_MAKE_DMG_SELECTOR_ONLY", lambda: {int(k) for k in PA._MAKE_DMG_SELECTOR_ONLY}),
    ("_MAKE_DMG_EXTRA_EVENTS", lambda: {int(k) for k in PA._MAKE_DMG_EXTRA_EVENTS}),
    ("_PLAYBOOK_PROFILE_OVERRIDE", lambda: {int(k) for k in PA._PLAYBOOK_PROFILE_OVERRIDE}),
    ("_MAKE_DMG_TARGET_GATE", lambda: {int(k) for k in PA._MAKE_DMG_TARGET_GATE}),
)


@pytest.mark.parametrize("aid,nom,registre_arrondi", [
    (SFS, "StrikeFromTheShadows", "b"),
    (LTC, "LeadingTheCharge", "a2"),
])
def test_etage5_verdict_constante(aid, nom, registre_arrondi):
    """`<X>Playbook$$MakeDamagePredictions` de 1225 et 1204 fait UN appel a
    `GenerateMultiHitAttackPredictions` avec `sel = DSLSelectors+0x60 = Target`, `hits =
    AActiveAbility$$GetHits`, `prof = AActiveAbility$$GetDamageProfile` -- c'est-a-dire le chemin
    GENERIQUE du port, terme pour terme. La seule chose qui les distingue est la FORME de la
    moyenne, deja lue et registree par #350 :

        1225 -> `VigilanceEternalAbility$$GetDamage` = `MinMaxDamage(state, isPrediction: FALSE)`
                = forme (b), TRONCATURE
        1204 -> `StaffOfStarsAbility$$GetDamage(state, isPrediction: TRUE)`
                = forme (a2), arrondi demi-vers-le-PAIR

    Ce test EXIGE donc DEUX choses : qu'aucun override ne soit ajoute (ce serait un port
    speculatif), et que l'appartenance au registre d'arrondi reste celle qui a ete LUE."""
    for reg, lire in _REGISTRES_D_OVERRIDE:
        assert aid not in lire(), (
            "%s (%d) est entree dans `%s` : le playbook natif ne fait pourtant qu'un appel "
            "GENERIQUE. Si le decompile a change, refaire la RE -- ne pas retirer cette ligne."
            % (nom, aid, reg))
    assert nom not in AA._SPECIAL_ABILITY_CLASSES, \
        "%s n'a AUCUN selecteur AoE propre : son playbook boucle sur `Target`" % nom
    assert AA.makes_damage_predictions(nom) is True, \
        "%s a bien un playbook COMPARABLE (`MakeDamagePredictions` existe)" % nom
    assert aid not in PLAYBOOKS, "%s n'est pas NonComparable" % nom
    assert aid not in SE_REGISTRY, "%s n'a pas de `ShouldExecute` propre" % nom

    # `_PREDICTION_MINMAX_AVERAGE` est le registre de la forme **(a)** (arrondi Fix64 demi-vers-le-
    # PAIR) -- c'est le predicat que `AActiveAbility.get_damage` teste. Ne PAS y figurer signifie
    # forme **(b)** (`RandomAmount` puis slot 4 `CalculateAverage` = TRONCATURE), qui est le DEFAUT.
    # `_A_VIA_STAFF_OF_STARS_GET_DAMAGE` en est le sous-registre (a2), celui du call-site
    # `isPrediction: TRUE`.
    a2 = {int(x) for x in AA._A_VIA_STAFF_OF_STARS_GET_DAMAGE}
    forme_a = {int(x) for x in AA._PREDICTION_MINMAX_AVERAGE}
    if registre_arrondi == "a2":
        assert aid in a2, "%s : `StaffOfStarsAbility$$GetDamage(state, isPrediction: TRUE)`" % nom
        assert aid in forme_a, "(a2) est un sous-ensemble de la forme (a)"
    else:
        assert aid not in a2
        assert aid not in forme_a, \
            "%s doit rester en forme (b) -- `MinMaxDamage(state, isPrediction: FALSE)`" % nom
    assert a2 and forme_a and not a2 - forme_a, \
        "REGIME DEGENERE : (a2) doit etre non vide ET inclus dans (a), sinon rien n'est discrimine"


# =================================================================================================
#  ETAGE 6 -- 1026 : le RESIDU est NOMME, pas oublie
# =================================================================================================

def test_etage6_1026_residu_atteste():
    """`BasiliskBarragePlaybook$$MakeDamagePredictions` emet TROIS batchs d'obus, chacun sur un
    POOL DE TUILES et pondere `numShells / |pool|` -- une forme que AUCUN registre du port ne sait
    exprimer aujourd'hui (les poids `probability1` y sont derives de `GetMaxSecondaryTargets`, et
    le domaine y est l'UNITE, pas la tuile).

    Ce test ATTESTE l'etat : 1026 reste sur le chemin generique, et les trois formules de shells
    dont la face DECISION a besoin sont DEJA portees cote COMBAT
    (`runner/abilities/astramilitarum.basilisk_num_shells`). Il rougira le jour ou quelqu'un
    branchera 1026 sans fermer le residu `#976-r1` -- ce qui est exactement le signal voulu."""
    for reg, lire in _REGISTRES_D_OVERRIDE:
        assert BB not in lire(), (
            "1026 est entree dans `%s` : fermer `#976-r1` (les 3 batchs ponderes) plutot que "
            "de brancher un override partiel." % reg)
    from engine.runner.abilities import astramilitarum as AM
    assert hasattr(AM, "basilisk_num_shells") and hasattr(AM, "basilisk_tiles_at_distance"), \
        "les etages deja portes cote COMBAT ont disparu -- le residu #976-r1 s'en sert"
    assert BB in {int(x) for x in AA._A_VIA_GET_DAMAGE_AMOUNT_MAIN}, \
        ("la base des obus est `StranglethornCannonAbility$$GetDamageAmountMain` = "
         "`MinMaxDamageAverage` (forme (a1)) -- lecture #350, requise par le residu")
