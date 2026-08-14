"""#1050-r1 -- les crans OFFLINE de l'ELARGISSEMENT MULTI-CIBLE de l'attaque normale d'`AncientFury`.

Ce fichier garde ce qui se PERIME EN SILENCE : la FORME de l'arbre de
`AncientFury_NormalAttackAbility$$GetTarget` (vslot `0x4a8`), la FRONTIERE avec la famille du cleave
#478 (les deux surchargent des slots DIFFERENTS et n'ecrivent pas les memes degats), le DOMAINE
MIXTE de `MinDistance` -- dont l'absence rendait l'anneau vide sans lever -- et les deux parametres
du vecteur normal qui expriment << cet appel est un tour de boucle, pas un cast >>.

Aucun runner : tout est structurel ou joue sur un `DslContext` synthetique.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.dsl.base import Const                                        # noqa: E402
from engine.dsl.nodes import DslContext                                  # noqa: E402
from engine.entities.formulas import MIN_DISTANCE_EMPTY, MinDistance     # noqa: E402
from engine.entities.selectors.accessors import CasterTile, TargetTile   # noqa: E402
from engine.entities.selectors.units import Union                        # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.entities.unit_selection_type import UnitSelectionType        # noqa: E402
from engine.runner.abilities.loki import ancient_fury as AF              # noqa: E402
from engine.services.custom_normal_attack import CUSTOM_NORMAL_ATTACK_BY_PASSIVE  # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # le port de la tranche
        "scripts/python/engine/runner/abilities/loki/ancient_fury.py",
        # le vecteur d'attaque normale et son cablage (les deux parametres de l'etage 6)
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        "scripts/python/engine/runner/operations/damage.py",
        # la FRONTIERE que l'etage 5 garde (l'autre famille de cleave d'attaque normale)
        "scripts/python/engine/runner/abilities/loki/additional_targets.py",
        "scripts/python/engine/services/custom_normal_attack.py",
        # les primitives MIRRORS que l'arbre traverse
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/triggers.py",
        # les MIRRORS d'enum dont les etages 1 et 2 gardent les ordinaux
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/unit_selection_type.py",
    ),
    "build": False,    # aucun etage ne lit le binaire ni `data/symbols/**`
    "toujours": True,
    "raison": ("l'etage 5 lit la table de dispatch `CUSTOM_NORMAL_ATTACK_BY_PASSIVE`, qui est "
               "alimentee par le gameconfig VIVANT : une MAJ du jeu qui retire l'entree "
               "`AncientFury -> AncientFury_NormalAttack` ferait changer ce fichier de verdict SANS "
               "qu'aucun chemin ci-dessus ne bouge. `build: False` parce que les litteraux natifs "
               "sont TRANSCRITS ici, pas relus."),
}

SEL = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3


# ---------------------------------------------------------------------------- substrat synthetique

def _u(uid: int, col: int, row: int, team: str):
    """Une unite au format que consomment les selecteurs DSL (`dsl.base._pos` lit `pos.col/row`)."""
    return {"id": uid, "pos": {"col": col, "row": row}, "team": team, "alive": True,
            "hp": 100, "max_hp": 100}


def _ctx(units, caster_id: int, target_id: int, kind: str) -> DslContext:
    by = {u["id"]: u for u in units}
    c = DslContext(units=units, caster=by[caster_id], target=by[target_id])
    # `IsMeleeAttack` du `ConditionalSelector` lit `ctx.attack_kind` : la nature de l'ARME CHOISIE.
    c.attack_kind = kind
    return c


def _pick(units, caster_id: int, target_id: int, kind: str) -> list:
    got = AF.ancient_fury_targets().evaluate(_ctx(units, caster_id, target_id, kind))
    return [u.get("id") for u in got if isinstance(u, dict)]


#: Le plan des etages RANGED : caster en (0,0), cible a distance 2, et TROIS voisins de la cible
#: dont un seul est a distance EXACTEMENT 2 du caster. C'est le discriminant de l'anneau.
_PLAN_RANGED = [_u(1, 0, 0, "A"),        # caster
                _u(2, 2, 0, "B"),        # cible primaire, d(caster) = 2
                _u(9, 2, 1, "B"),        # d(cible) = 1, d(caster) = 2  -> DANS l'anneau
                _u(5, 1, 0, "B"),        # d(cible) = 1, d(caster) = 1  -> HORS (soustrait)
                _u(3, 1, 1, "B"),        # d(cible) = 1, d(caster) = 1  -> HORS (soustrait)
                _u(7, 5, 5, "B")]        # trop loin des deux


# ------------------------------------------------------------------- 0. le plan est bien ce qu'on croit

def test_etage0_le_plan_synthetique_porte_bien_les_distances_annoncees():
    """Un plan dont les distances ne sont pas celles qu'on croit ferait passer les etages suivants
    pour les mauvaises raisons -- la geometrie hexagonale evenq n'est pas Chebyshev."""
    pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in _PLAN_RANGED}
    d_caster = {i: hexgeo.distance(pos[1], p) for i, p in pos.items()}
    d_cible = {i: hexgeo.distance(pos[2], p) for i, p in pos.items()}
    assert d_caster[2] == 2, "la cible primaire doit etre a distance 2 du caster"
    assert (d_cible[9], d_caster[9]) == (1, 2), "9 est le SEUL voisin de la cible a d(caster) = 2"
    assert (d_cible[5], d_caster[5]) == (1, 1), "5 est voisin de la cible mais a d(caster) = 1"
    assert (d_cible[3], d_caster[3]) == (1, 1), "3 idem -- c'est lui qui exerce la soustraction"
    assert min(d_cible[7], d_caster[7]) > 2, "7 doit etre hors de portee des deux ancres"


# ------------------------------------------------------------------- 1. l'ability et sa cascade

def test_etage1_l_ability_et_la_cascade_qui_la_monte():
    """`AncientFury` = 1256, et c'est la cascade `UnitFactory$$AddNormalAttackAbility` qui substitue
    son attaque normale par `AncientFury_NormalAttack` (1162) -- la MEME table que le cleave #478,
    donc le MEME substrat d'entite (`BC.Units[].PassiveAbilities`)."""
    assert int(TriggeredAbilityType.AncientFury) == 1256
    assert CUSTOM_NORMAL_ATTACK_BY_PASSIVE.get("AncientFury") == "AncientFury_NormalAttack", (
        "l'entree de la cascade a disparu du foyer -- l'elargissement ne partirait plus")
    assert set(AF.WIDENED_NORMAL_ATTACKS) == {"AncientFury"}, (
        "`AncientFury_NormalAttackAbility$$GetTarget` est la SEULE surcharge nommee du vslot 0x4a8 "
        "parmi les `<X>_NormalAttackAbility` du build : toute entree de plus doit etre LUE, pas "
        "ajoutee par analogie de nom")


def test_etage1b_le_selection_type_est_celui_lu_au_decompile():
    """Les QUATRE `DSLSelectors$$*` de `$$GetTarget` portent le litteral `3` EXPLICITEMENT. Le
    rabattre sur `1` (`OnlyAlive`) n'ecarterait PAS `Untargetable` -- l'inverse de ce que ce
    parametre repare."""
    assert AF.SELECTION == SEL == 3
    assert UnitSelectionType(AF.SELECTION).name == "OnlyAliveAndTargetable"


# ------------------------------------------------------------------- 2. la FORME de l'arbre

def test_etage2_la_racine_est_une_UNION_dont_la_gauche_est_la_cible():
    """`op_Addition(Target@0x60, ConditionalSelector(...))` : la cible du message est DANS le
    selecteur, en tete AVANT le tri. Un arbre qui ne la porterait pas ferait perdre la primaire au
    profit des seules additionnelles."""
    tree = AF.ancient_fury_targets()
    assert isinstance(tree, Union), (
        "la racine doit etre `op_Addition` -- pas une intersection, pas la branche seule")


def test_etage2b_la_cible_primaire_est_toujours_selectionnee():
    for kind in ("melee", "ranged"):
        got = _pick(_PLAN_RANGED, 1, 2, kind)
        assert 2 in got, "la cible du message doit etre dans `$$GetTarget` (%s)" % kind
        assert got.count(2) == 1, (
            "aucun doublon possible : les deux branches sont intersectees avec "
            "`AdjacentUnits(Target)`, qui EXCLUT son propre centre")


# ------------------------------------------------------------------- 3. la branche MELEE

def test_etage3_melee_frappe_les_adjacents_des_DEUX_ancres():
    """Branche VRAIE : `AdjacentEnemies(Caster@0x48) & AdjacentUnits(Target@0x60)` -- l'i2 dit
    << adjacent to both the target and Galatian >>."""
    units = [_u(1, 0, 0, "A"),      # caster
             _u(2, 1, 0, "B"),      # cible, ADJACENTE
             _u(3, 1, 1, "B"),      # adjacent aux DEUX          -> DEDANS
             _u(6, 0, 1, "A"),      # adjacent aux deux mais ALLIE du caster -> dehors
             _u(4, 5, 5, "B")]      # trop loin
    got = _pick(units, 1, 2, "melee")
    assert sorted(got) == [2, 3], "melee = cible + les ennemis adjacents aux deux ; got=%r" % got
    assert 6 not in got, ("`AdjacentEnemies` est ancre sur le CASTER : un ALLIE ne peut pas entrer "
                          "par la branche melee")


def test_etage3b_melee_exclut_un_adjacent_du_caster_qui_ne_touche_pas_la_cible():
    """La conjonction est le point : un ennemi collé au caster mais LOIN de la cible ne compte pas
    -- c'est ce qui distingue cet arbre d'un simple `AdjacentEnemies(Caster)`."""
    units = [_u(1, 0, 0, "A"), _u(2, 2, 0, "B"), _u(8, 0, 1, "B")]
    assert hexgeo.distance((0, 0), (0, 1)) == 1, "8 est bien adjacent au caster"
    assert hexgeo.distance((2, 0), (0, 1)) > 1, "8 n'est PAS adjacent a la cible"
    got = _pick(units, 1, 2, "melee")
    assert got == [2], "seule la primaire ; got=%r" % got


# ------------------------------------------------------------------- 4. la branche RANGED (l'anneau)

def test_etage4_ranged_est_un_ANNEAU_EXACT_pas_un_disque():
    """Branche FAUSSE : `AdjacentUnits(Target) & (Surrounding(d) - Surrounding(d-1))`, `d =
    MinDistance(CasterTiles, TargetTiles)`. C'est ce qui rend l'i2 << exactly 2 hexes away >>.

    La CONTRE-EPREUVE est dans le meme plan : 5 et 3 sont eux aussi adjacents a la cible, mais a
    distance 1 du caster -- un DISQUE les prendrait, l'anneau les soustrait."""
    got = _pick(_PLAN_RANGED, 1, 2, "ranged")
    assert sorted(got) == [2, 9], (
        "ranged = cible + le SEUL voisin a distance EXACTEMENT 2 du caster ; got=%r" % got)
    assert 5 not in got and 3 not in got, (
        "la soustraction `Surrounding(d) - Surrounding(d-1)` doit ECARTER les voisins de la cible "
        "qui sont plus PRES du caster que la cible elle-meme")


def test_etage4b_les_deux_branches_ne_rendent_PAS_la_meme_chose_sur_ce_plan():
    """Sans cet ecart, l'etage 4 passerait meme si le `ConditionalSelector` etait cable a l'envers
    -- un test qui ne discrimine pas est un vert qui ment."""
    melee = sorted(_pick(_PLAN_RANGED, 1, 2, "melee"))
    ranged = sorted(_pick(_PLAN_RANGED, 1, 2, "ranged"))
    assert melee != ranged, (
        "le plan doit SEPARER les deux branches ; melee=%r ranged=%r" % (melee, ranged))
    # Sur ce plan les deux branches se REPONDENT : la melee prend 5 et 3 (adjacents au caster ET a
    # la cible) et laisse 9 (a 2 hexes du caster) ; la ranged fait EXACTEMENT l'inverse. Cabler le
    # `ConditionalSelector` a l'envers echangerait donc les deux ensembles -- c'est ce que ce plan
    # rend visible, et c'est plus fort qu'un simple << ils different >>.
    assert melee == [2, 3, 5], "melee = cible + les adjacents des DEUX ; got=%r" % melee
    assert ranged == [2, 9], "ranged = cible + l'anneau EXACT ; got=%r" % ranged
    assert set(melee) & set(ranged) == {2}, (
        "hors la primaire, les deux branches doivent etre DISJOINTES sur ce plan -- sinon "
        "l'etage 4 ne prouverait pas que la soustraction mord")


def test_etage4c_l_anneau_suit_la_DISTANCE_REELLE_et_non_la_constante_2():
    """`d` est `MinDistance(caster, cible)`, pas le litteral 2 : cible a distance 3 -> anneau a 3.
    Coder `2` en dur serait juste sur le seul porteur (arme de portee 2) et faux partout ailleurs."""
    units = [_u(1, 0, 0, "A"),
             _u(2, 3, 0, "B"),      # cible a d(caster) = 3
             _u(9, 3, 1, "B"),      # voisin de la cible, d(caster) = 3  -> DANS l'anneau
             _u(5, 2, 0, "B")]      # voisin de la cible, d(caster) = 2  -> HORS
    assert hexgeo.distance((0, 0), (3, 0)) == 3
    assert hexgeo.distance((0, 0), (3, 1)) == 3 and hexgeo.distance((3, 0), (3, 1)) == 1
    assert hexgeo.distance((0, 0), (2, 0)) == 2 and hexgeo.distance((3, 0), (2, 0)) == 1
    got = sorted(_pick(units, 1, 2, "ranged"))
    assert got == [2, 9], "l'anneau doit suivre d=3, pas le litteral 2 ; got=%r" % got


# ------------------------------------------------------------------- 5. la FRONTIERE avec #478

def test_etage5_la_famille_du_cleave_et_celle_ci_sont_DISJOINTES():
    """Deux slots surcharges DIFFERENTS, deux ecritures de degat differentes. Melanger les deux
    donnerait les bornes de config au lieu des coups d'ARME -- silencieusement."""
    from engine.runner.abilities.loki.additional_targets import NORMAL_ATTACK_CLEAVES
    assert set(NORMAL_ATTACK_CLEAVES) & set(AF.WIDENED_NORMAL_ATTACKS) == set(), (
        "une ability ne peut pas etre dans les DEUX familles : la cascade "
        "`AddNormalAttackAbility` ne monte qu'UN passif substituant par unite")
    assert "AncientFury" not in NORMAL_ATTACK_CLEAVES, (
        "cf. `test_1050_optimized_gait_offline.py` etage 4 -- le cran d'origine")
    assert set(NORMAL_ATTACK_CLEAVES), "registre du cleave VIDE : le balayage ne prouverait rien"


# ------------------------------------------------------------------- 6. les deux etages non rejoues

def test_etage6_le_vecteur_normal_exprime_LOOP_et_ARME_FIGEE():
    """Les deux parametres sont le mirror d'etages que la boucle native NE rejoue PAS. Sans eux, le
    port re-emettrait `On(0x2a)` par cible et re-choisirait l'arme par cible."""
    import inspect
    from engine.runner.operations.damage import AttackDamageOperation
    sig = inspect.signature(AttackDamageOperation.execute)
    for name in ("in_attack_loop", "weapon_ref_target_id"):
        assert name in sig.parameters, (
            "`%s` a disparu du vecteur normal -- l'elargissement d'AncientFury re-jouerait un "
            "etage d'`ActiveAbilityOperation$$ExecuteInternal` par cible" % name)
    assert sig.parameters["in_attack_loop"].default is False, (
        "le defaut DOIT rester `False` : toutes les autres voies sont des CASTS")
    assert sig.parameters["weapon_ref_target_id"].default is None, (
        "le defaut DOIT rester `None` : l'arme se choisit alors contre la cible courante")


def test_etage6b_l_ordre_rendu_est_le_tri_par_id_de_AttackBehaviour_Execute():
    """`if (targets.Count > 1) targets.OrderBy(<>c.b__5_0)` -- MEME `OrderBy`, MEME cle que le mode
    `multi=True` d'`AttackWithAttackDamage`. Le plan met volontairement l'ordre de SELECTION en
    desaccord avec l'ordre d'ID."""
    units = [_u(1, 0, 0, "A"), _u(50, 1, 0, "B"), _u(4, 1, 1, "B"), _u(30, 0, 1, "B")]
    got = _pick(units, 1, 50, "melee")
    assert set(got) >= {50, 4}, "le plan doit produire au moins deux cibles ; got=%r" % got
    tries = AF.widened_targets(_FakeState(units), 1, 50, AF.WIDENED_NORMAL_ATTACKS["AncientFury"],
                               is_melee=True)
    ids = [u["id"] for u in tries]
    assert ids == sorted(ids), "les cibles doivent sortir TRIEES par id ; got=%r" % ids
    assert len(ids) > 1, "un tri sur une seule cible ne prouverait rien"


def test_etage6c_les_additionnelles_excluent_la_primaire_PAR_ID():
    """La primaire est retiree par son ID, jamais << le premier element >> : l'`OrderBy` peut
    l'envoyer ailleurs, et retirer la tete supprimerait alors la mauvaise unite."""
    units = [_u(1, 0, 0, "A"), _u(50, 1, 0, "B"), _u(4, 1, 1, "B")]
    entry = AF.WIDENED_NORMAL_ATTACKS["AncientFury"]
    st = _FakeState(units)
    tous = [u["id"] for u in AF.widened_targets(st, 1, 50, entry, is_melee=True)]
    adds = AF.additional_target_ids(st, 1, 50, entry, is_melee=True)
    assert tous and tous[0] != 50, (
        "ce plan doit placer la primaire AILLEURS qu'en tete apres tri -- sinon il ne discrimine "
        "rien ; tous=%r" % tous)
    assert 50 not in adds and set(adds) == set(tous) - {50}, "adds=%r tous=%r" % (adds, tous)


# ------------------------------------------------------------------- 7. le DOMAINE MIXTE de MinDistance

def test_etage7_min_distance_accepte_le_domaine_TUILE():
    """CONTRE-EPREUVE du bug trouve par cette tranche : `MinDistance` ne visitait que les dicts
    d'unite, donc deux operandes en domaine TUILE rendaient DEUX listes vides et la formule rendait
    `int.MaxValue` -- un rayon absurde, sans lever. Le natif, lui, appelle le slot 10
    `TargetsSelector$$SelectTiles`, DOMAINE MIXTE par construction."""
    units = [_u(1, 0, 0, "A"), _u(2, 2, 0, "B")]
    ctx = _ctx(units, 1, 2, "ranged")
    assert CasterTile().evaluate(ctx) == [(0, 0)], "l'ancre doit bien rendre une TUILE"
    assert TargetTile().evaluate(ctx) == [(2, 0)]
    d = MinDistance(CasterTile(), TargetTile()).evaluate(ctx)
    assert d == 2, "domaine TUILE : la distance doit etre reelle, got=%r" % d
    assert d != MIN_DISTANCE_EMPTY, (
        "le sentinel `int.MaxValue` est ce que rendait le foyer AVANT la correction")


def test_etage7b_min_distance_reste_exacte_en_domaine_UNITE():
    """NON-REGRESSION : le seul autre call-site executable (`IsInUnitAura`) passe deux selecteurs
    d'UNITES. La delegation au helper doit y etre value-preserving."""
    from engine.entities.selectors.tiles import Caster as CasterUnit
    from engine.entities.selectors.accessors import Target as TargetUnit
    units = [_u(1, 0, 0, "A"), _u(2, 2, 0, "B")]
    ctx = _ctx(units, 1, 2, "ranged")
    assert MinDistance(CasterUnit(), TargetUnit()).evaluate(ctx) == 2


def test_etage7c_min_distance_rend_le_sentinel_quand_rien_n_est_mesurable():
    """L'autre moitie du mirror : la boucle native ne tourne pas -> `int.MaxValue`. Le corriger en
    `0` ferait passer tout gate `<= n`."""
    from engine.entities.selectors.units import UnitSet
    units = [_u(1, 0, 0, "A"), _u(2, 2, 0, "B")]
    ctx = _ctx(units, 1, 2, "ranged")
    assert MinDistance(CasterTile(), UnitSet([])).evaluate(ctx) == MIN_DISTANCE_EMPTY


# ------------------------------------------------------------------- 8. degradations nommees

def test_etage8_aucune_cible_sans_cible_primaire():
    """`target_id is None` -> aucune cible : le selecteur entier est ancre sur `Target@0x60`."""
    units = [_u(1, 0, 0, "A"), _u(2, 1, 0, "B")]
    entry = AF.WIDENED_NORMAL_ATTACKS["AncientFury"]
    assert AF.widened_targets(_FakeState(units), 1, None, entry, is_melee=True) == []
    assert AF.additional_target_ids(_FakeState(units), 1, None, entry, is_melee=True) == []


def test_etage8b_widened_for_passe_par_la_cascade_et_non_par_un_in():
    """Le dispatch doit etre le MEME foyer que `cleave_for` -- une unite qui porte `AncientFury`
    DERRIERE un autre passif substituant recoit l'attaque normale de l'AUTRE."""
    assert AF.widened_for(["AncientFury"]) is not None
    assert AF.widened_for([]) is None
    assert AF.widened_for(["Boltstorm"]) is None, (
        "un autre passif substituant ne doit PAS declencher l'elargissement")


class _FakeState:
    """Porteur des unites du plan pour les etages qui appellent `widened_targets` /
    `additional_target_ids`. Il ne remplace PAS un `State` runner : hors runner, la construction
    d'`AbilityEntities` est court-circuitee par la fixture ci-dessous.

    `units` est expose tel quel -- c'est tout ce que le substitut de `entities_from_state` lit."""

    def __init__(self, units):
        self.board = None
        self.rng = None
        self.units = list(units)


@pytest.fixture(autouse=True)
def _entities_from_fake_state(monkeypatch):
    """`entities_from_state` construit un `AbilityEntities` depuis un `State` RUNNER complet
    (composants ECS, effets, position de machine du joueur courant...). Le reconstituer ici
    n'apporterait rien a ce que ces etages mesurent -- la FORME de l'arbre et l'ORDRE de sortie --
    et ferait dependre le test de champs sans rapport.

    ⚠ Le substitut est pose sur `ancient_fury.entities_from_state`, donc au SITE que le port
    resout : si le module cessait d'appeler ce foyer, `test_etage_zz_le_stub_mord_bien` rougirait au
    lieu de laisser passer un test devenu inerte."""
    def _fake(state, caster_id, target_id=None, actor_id=None, owner_id=None):
        units = list(state.units)
        by = {u["id"]: u for u in units}
        ctx = DslContext(units=units, caster=by.get(int(caster_id)),
                         target=None if target_id is None else by.get(int(target_id)))
        return ctx
    monkeypatch.setattr(AF, "entities_from_state", _fake)


def test_etage_zz_le_stub_mord_bien(monkeypatch):
    """Un stub qui ne mord plus laisse le fichier VERT en ne mesurant plus rien. On le verifie
    explicitement : le module DOIT passer par `entities_from_state`."""
    appels = []
    vrai = AF.entities_from_state

    def _compte(state, caster_id, target_id=None, actor_id=None, owner_id=None):
        appels.append((caster_id, target_id))
        return vrai(state, caster_id, target_id)
    monkeypatch.setattr(AF, "entities_from_state", _compte)
    units = [_u(1, 0, 0, "A"), _u(2, 1, 0, "B"), _u(3, 1, 1, "B")]
    AF.widened_targets(_FakeState(units), 1, 2, AF.WIDENED_NORMAL_ATTACKS["AncientFury"],
                       is_melee=True)
    assert appels == [(1, 2)], (
        "`widened_targets` doit construire son `AbilityEntities` par `entities_from_state` ; "
        "got=%r" % appels)
