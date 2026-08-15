"""#590-r7 -- CLIQUETS des DEUX increments d'utilite d'`AttemptedPossessionPlaybook`.

Le natif compte `1 / 2 / 3` (`...AttemptedPossessionPlaybook$$EvaluateNonComparable`, RELU) :

    utility = Fix64.op_Implicit(1)                                       # PLANCHER
    if (GetChildrenUnits(target, state).Count > 0)  utility++            # increment 1
    if (GetEligibleTargetsForNormalAttack(target, entities.TargetPosition)
            .<+0x10>.Count > 0)                     utility++            # increment 2

Les deux `op_Increment` sont INDEPENDANTS (pas d'`else`) : les QUATRE combinaisons existent.

CE QUE CE FICHIER GARDE EN PLUS DES VALEURS : les DEUX PREMISSES de la fiche de residu, qui
etaient l'une PERIMEE et l'autre MAL ATTRIBUEE --
  * increment 1, `BLOCAGE: seeding` -> PERIME. Le lien parent est publie depuis #378
    (`combatSnapshot.units[].parentId`, `Scene.from_state` offline) et arrive au playbook par
    `ctx.scene.parent_by_id` ;
  * increment 2, << RPC oriente CASTER >> -> MAL ATTRIBUE. Le hook filtre
    `IsControlledByCurrentPlayer`, donc tout allie du joueur courant repond et aucun ENNEMI. Le
    blocage etait `etage`, et l'etage EXISTE : le foyer offline partage avec
    `ExemplarOfTheKauyonPlaybook`.

⚠ AUCUN TEST NE JOUAIT CE PLAYBOOK avant ce fichier (grep `AttemptedPossessionPlaybook` : le module
et son `__init__` seulement). La face DECISION partait donc sans filet.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

RACINE = pathlib.Path(__file__).resolve().parents[2]

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/playbook/noncomparable/attempted_possession.py",
        # Le foyer du 2e increment, PARTAGE : une derive y deplacerait AUSSI les verdicts de
        # `ExemplarOfTheKauyonPlaybook`, et c'est precisement ce que l'etage 3 garde.
        "scripts/python/engine/playbook/noncomparable/_base.py",
        "scripts/python/engine/playbook/noncomparable/exemplar_of_the_kauyon.py",
        # Le substrat du 1er increment (le lien parent) et celui de la portee d'attaque.
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/engine/ai/state_bridge.py",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "Perimetre BORNE : les cinq chemins sont ceux que les assertions LISENT. `scene.py` et "
        "`state_bridge.py` y sont parce que les deux increments dependent de leurs SUBSTRATS "
        "(`parent_by_id`, `_max_attack_range`) -- un tri-etat qui s'y perdrait rendrait ces tests "
        "verts sur une mesure fabriquee. `exemplar_of_the_kauyon.py` y est parce que l'etage 3 "
        "garde qu'il DELEGUE au foyer au lieu de re-transcrire le meme corps natif."),
}


def _nc(**kw):
    from engine.playbook.noncomparable._base import NCContext

    base = dict(uid=7, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={},
                hp_cur_by_id={}, units=[], obs_units=[], elev_by_pos={})
    base.update(kw)
    return NCContext(**base)


class _Scene:
    def __init__(self, parent_by_id=None):
        self.parent_by_id = parent_by_id or {}


# =================================================================================================
# ETAGE 1 -- increment 1 : `GetChildrenUnits(target).Count > 0`
# =================================================================================================

def test_etage1_le_lien_parent_est_INVERSE_pas_lu_a_l_endroit():
    """Le natif lit la liste vue du PARENT ; le canal porte le lien vu de l'ENFANT
    (`ChildComponent.ParentId`). Le port INVERSE -- une lecture << a l'endroit >> chercherait
    `parent_by_id[target]`, qui est le SUMMONER de la cible, pas ses enfants."""
    from engine.playbook.noncomparable.attempted_possession import AttemptedPossessionPlaybook

    pb = AttemptedPossessionPlaybook()
    ctx = _nc(scene=_Scene({11: 3, 12: 3, 13: 5}))
    assert pb._has_children_units(ctx, 3) is True     # 11 et 12 sont ses enfants
    assert pb._has_children_units(ctx, 5) is True     # 13 est son enfant
    assert pb._has_children_units(ctx, 11) is False   # 11 EST un enfant, il n'en a pas
    assert pb._has_children_units(ctx, 99) is False


def test_etage1_capteur_muet_rend_NON_MESURE_jamais_False():
    """`scene` absente ou table VIDE -> `None`. Un `False` fabrique se lirait << la cible n'a pas
    d'enfant >>, une MESURE que personne n'a faite."""
    from engine.playbook.noncomparable.attempted_possession import AttemptedPossessionPlaybook

    pb = AttemptedPossessionPlaybook()
    assert pb._has_children_units(_nc(), 3) is None                    # pas de `scene`
    assert pb._has_children_units(_nc(scene=_Scene({})), 3) is None    # table VIDE = capteur muet


def test_etage1_le_filtre_natif_est_NOMME():
    """`GetChildrenUnits` ne garde que les enfants dont `Type == EntityType.Unit`. Le canal lu est
    deja unit-only, donc le filtre est STRUCTUREL -- mais l'ordinal `1` ne doit pas etre ecrit en
    dur quelque part : le membre est nomme."""
    from engine.entities.entity_type import EntityType
    from engine.playbook.noncomparable.attempted_possession import _ENFANT_RETENU

    assert _ENFANT_RETENU is EntityType.Unit
    assert int(_ENFANT_RETENU) == 1


# =================================================================================================
# ETAGE 2 -- increment 2 : `GetEligibleTargetsForNormalAttack(target, targetPosition)`
# =================================================================================================

def test_etage2_le_caster_de_la_question_est_LA_CIBLE():
    """Le natif passe `target` et SA position : ses adversaires sont NOS unites. Interroger depuis
    notre camp (l'erreur naturelle) rendrait le predicat symetrique et FAUX -- ici la cible u3 est
    en team 2, ses seules cibles possibles sont les team 1."""
    from engine.playbook.noncomparable.attempted_possession import AttemptedPossessionPlaybook

    pb = AttemptedPossessionPlaybook()
    obs = [{"squadId": 3, "teamId": 2, "col": 4, "row": 4, "isDead": False,
            "visualId": "orksNob"},
           {"squadId": 7, "teamId": 1, "col": 4, "row": 5, "isDead": False,
            "visualId": "orksNob"}]
    assert pb._target_can_attack(_nc(obs_units=obs), 3) is True
    # La MEME configuration sans aucun adversaire de la cible -> False, sans exception.
    obs_seul = [dict(obs[0])]
    assert pb._target_can_attack(_nc(obs_units=obs_seul), 3) is False


def test_etage2_cible_hors_canal_ne_leve_pas_et_n_incremente_pas():
    """Une cible absente d'`obs_units`, morte, ou sans position -> `False` (borne INF). Le natif,
    lui, n'entrerait pas dans la boucle : ne pas incrementer est le comportement le plus proche."""
    from engine.playbook.noncomparable.attempted_possession import AttemptedPossessionPlaybook

    pb = AttemptedPossessionPlaybook()
    assert pb._target_can_attack(_nc(), 3) is False
    mort = [{"squadId": 3, "teamId": 2, "col": 4, "row": 4, "isDead": True}]
    assert pb._target_can_attack(_nc(obs_units=mort), 3) is False


# =================================================================================================
# ETAGE 3 -- le COMPTEUR, et l'unicite du foyer partage
# =================================================================================================

def test_etage3_les_quatre_combinaisons_donnent_1_2_2_3():
    """Les increments sont INDEPENDANTS : aucun `else` dans le decompile."""
    from engine.playbook.noncomparable.attempted_possession import AttemptedPossessionPlaybook

    pb = AttemptedPossessionPlaybook()
    ctx = _nc()
    for enfants, attaque, attendu in ((False, False, 1.0), (True, False, 2.0),
                                      (False, True, 2.0), (True, True, 3.0)):
        pb._has_children_units = staticmethod(                    # type: ignore[method-assign]
            lambda _c, _t, _v=enfants: _v)
        pb._target_can_attack = staticmethod(                     # type: ignore[method-assign]
            lambda _c, _t, _v=attaque: _v)
        assert pb.evaluate_non_comparable((0, 0), 3, ctx) == pytest.approx(attendu)


def test_etage3_le_plancher_reste_au_dessus_de_MIN_UTILITY():
    """`Bucket$$AddAction` admet sur `utilite >= min`. Le plancher DOIT donc rester >= 1, sinon le
    port cesserait de proposer un cast que le natif propose (degradation RESTRICTIVE interdite)."""
    from engine.playbook.noncomparable.attempted_possession import AttemptedPossessionPlaybook

    pb = AttemptedPossessionPlaybook()
    assert pb.BASE_UTILITY >= pb.MIN_UTILITY
    pb._has_children_units = staticmethod(lambda _c, _t: None)    # type: ignore[method-assign]
    pb._target_can_attack = staticmethod(lambda _c, _t: False)    # type: ignore[method-assign]
    assert pb.evaluate_non_comparable((0, 0), 3, _nc()) >= pb.MIN_UTILITY


def test_etage3_cible_absente_rend_None():
    from engine.playbook.noncomparable.attempted_possession import AttemptedPossessionPlaybook

    assert AttemptedPossessionPlaybook().evaluate_non_comparable((0, 0), None, _nc()) is None


def test_etage3_le_predicat_natif_n_est_transcrit_QU_UNE_FOIS():
    """`GetEligibleTargetsForNormalAttack` a DEUX appelants portes (`AttemptedPossession` et
    `ExemplarOfTheKauyon`). Deux transcriptions se desynchroniseraient -- une seule des deux serait
    corrigee le jour ou un etage manquant (brouillard, walkability, bits du masque) est porte.
    Le corps doit donc vivre dans `_base` et nulle part ailleurs."""
    from engine.playbook.noncomparable import _base, exemplar_of_the_kauyon

    assert hasattr(_base, "has_eligible_normal_attack_target")
    src = (RACINE / "engine" / "playbook" / "noncomparable"
           / "exemplar_of_the_kauyon.py").read_text(encoding="utf-8")
    arbre = ast.parse(src)
    corps = [n for n in ast.walk(arbre)
             if isinstance(n, ast.FunctionDef) and n.name == "has_enemy_in_range"]
    assert len(corps) == 1
    # Le NON-VIDE est asserte : un `walk` qui ne trouverait rien passerait pour vert.
    appels = [n for n in ast.walk(corps[0])
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "has_eligible_normal_attack_target"]
    assert len(appels) == 1, "`has_enemy_in_range` doit DELEGUER au foyer, pas re-transcrire"
    assert exemplar_of_the_kauyon.has_eligible_normal_attack_target is \
        _base.has_eligible_normal_attack_target
