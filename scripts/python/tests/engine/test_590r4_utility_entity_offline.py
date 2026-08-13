"""#590-r4 -- le canal `utilityEntity` (`PerformAIAbilityUnitBehaviour+0x80`) est THREADE.

RE refaite sur `rnca9r7q6c` (`IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute`).
La fiche du residu decrivait le champ comme << resolu par `SelectFirst` et passe a la couche
d'utilite comme entite de reference du scoring >>, et donc INERTE. Les deux moities sont fausses :

  * il n'a AUCUN lecteur dans la couche d'utilite. Son SEUL consommateur est le `ValueTuple` que le
    behaviour construit pour invoquer le delegue `customUtility` (`+0x90`) :
    `ValueTuple..ctor(&tuple, <acteur courant>, <utilityEntity resolu>)`. Quand `+0x90` est NUL,
    il est effectivement mort -- mais c'est une propriete du CALL-SITE, pas du champ ;
  * chez `1101` il devient le parametre **`caster`** de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.AttemptedPossessionAbility$$GetPreferredAttackTarget(caster,
    possessedUnit)`, via `$$GetAttackCustomUtility` qui fait
    `GetPreferredAttackTarget(this, input+8, input+0)` -- donc `Item2` -> `caster`,
    `Item1` -> `possessedUnit`.

La resolution est le **slot 1 d'`ITargetsSelector` = `SelectFirst`** (LU dans le decompile ; le TSV
versionne `data/symbols/<build>/metadata/interface_slots.tsv` le nomme), et elle a lieu **UNE SEULE
FOIS, AVANT la boucle** sur les acteurs.

Ces gardes sont OFFLINE et n'ont besoin d'aucun runner : elles portent sur le CABLAGE de la feuille.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: La CASCADE D'IMPORTS (476 modules) est DERIVEE par le foyer depuis #531 : elle couvre le foyer
#: (`behaviours/ai_control.py`), le corps substitue (`loki/summon.py`), le call-site fige par
#: l'etage 4 (`loki/attempted_possession.py`), `dsl/base.py` et `selectors/accessors.py`. Les
#: recopier ici serait une liste a maintenir a la main a cote d'une derivation exacte.
DECLENCHEUR = {
    "chemins": (
        # Le SEUL chemin hors cascade, rendu par `probe_486r15 --proposer` : l'`__init__` du
        # paquet `behaviours`, que la fixture traverse pour substituer le corps.
        "scripts/python/engine/runner/abilities/behaviours/__init__.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "les gardes portent sur le CABLAGE de `PerformAIAbility` -- resolution UNIQUE du "
              "selecteur `+0x80`, arite du delegue `+0x90`, contenu de la trace. Tout cela est "
              "dans la cascade d'imports DERIVEE, sauf l'`__init__` du paquet. Aucun canal "
              "hors-import : le corps du tour d'IA est SUBSTITUE, donc ni runner ni RPC.",
}


class _Ctx:
    """`DslContext` minimal -- la feuille ne lit que ce que son selecteur d'acteurs consomme."""

    def __init__(self, units, owner=None):
        self.units = list(units)
        self.owner = owner
        self.caster = owner
        self.target = None


class _Ectx:
    def __init__(self, state):
        self.state = state
        self.rng = None
        self.emitted = []

    def emit(self, nom, **kw):
        self.emitted.append((nom, kw))


class _SelFixe:
    """Selecteur qui rend une liste FIXE et COMPTE ses evaluations.

    Le compteur est ce qui distingue << resolu une fois >> de << resolu par acteur >> : avec un
    selecteur constant, les deux regimes rendent la MEME valeur, donc seule la trace les separe.
    """

    def __init__(self, valeur):
        self.valeur = valeur
        self.appels = 0

    def evaluate(self, ctx):
        self.appels += 1
        return self.valeur

    select = evaluate


@pytest.fixture
def feuille(monkeypatch):
    """La feuille + un `perform_ai_ability_unit_behaviour` NEUTRALISE.

    On substitue le corps (qui exigerait un `State` complet) : ce fichier garde le CABLAGE de
    `PerformAIAbility`, pas le tour d'IA -- celui-la est deja garde par les tests de #590.
    """
    from engine.runner.abilities.behaviours import ai_control
    import engine.runner.abilities.loki.summon as summon
    monkeypatch.setattr(summon, "perform_ai_ability_unit_behaviour",
                        lambda *a, **k: {"ok": True})
    return ai_control


# ------------------------------------------------------------------ etage 1 : le canal EXISTE
def test_le_custom_utility_a_TROIS_parametres_recoit_l_utility_entity(feuille):
    """Mirror de `ValueTuple(Item1 = acteur, Item2 = utilityEntity)`."""
    acteurs = [{"id": 11}, {"id": 12}]
    proprio = {"id": 7}
    recus = []

    def _cu(state, actor_id, utility_entity_id):
        recus.append((actor_id, utility_entity_id))
        return None

    noeud = feuille.PerformAIAbility(_SelFixe(acteurs), utility_entity=_SelFixe(proprio),
                                     custom_utility=_cu)
    noeud.execute(_Ctx(acteurs, owner=proprio), _Ectx(state=object()))
    assert recus == [(11, 7), (12, 7)], \
        "chaque acteur voit SON id en Item1 et le MEME utilityEntity en Item2"


def test_l_emit_porte_l_utility_entity(feuille):
    """Le residu l'annoncait << conserve, journalise >> -- l'`emit` ne le portait PAS."""
    acteurs = [{"id": 11}]
    noeud = feuille.PerformAIAbility(_SelFixe(acteurs), utility_entity=_SelFixe({"id": 7}))
    ectx = _Ectx(state=object())
    noeud.execute(_Ctx(acteurs), ectx)
    nom, kw = ectx.emitted[-1]
    assert nom == "PerformAIAbility"
    assert kw.get("utility_entity") == 7, \
        "sans ce champ dans la trace, le seul canal d'observation de `+0x80` est muet"


# ------------------------------------------- etage 2 : la migration est VALUE-PRESERVANTE
def test_un_custom_utility_a_DEUX_parametres_garde_exactement_son_contrat(feuille):
    """C'est la condition de non-rupture : les consommateurs ecrits avant #590-r4 -- dont celui de
    `1101`, qui capture `caster_id` par FERMETURE -- ne doivent voir aucun changement."""
    acteurs = [{"id": 11}]
    recus = []

    def _cu(state, actor_id):
        recus.append(actor_id)
        return {99}

    noeud = feuille.PerformAIAbility(_SelFixe(acteurs), utility_entity=_SelFixe({"id": 7}),
                                     custom_utility=_cu)
    ectx = _Ectx(state=object())
    noeud.execute(_Ctx(acteurs), ectx)
    assert recus == [11], "appel a DEUX arguments, comme avant"
    assert ectx.emitted[-1][1]["acted"][0]["allowed_targets"] == [99]


def test_un_custom_utility_VARIADIQUE_recoit_l_utility_entity(feuille):
    """`*args` accepte le 3e argument : le classer en refus le priverait d'une donnee qu'il peut
    lire, et ce sont exactement les wrappers/decorateurs qui s'ecrivent ainsi."""
    acteurs = [{"id": 11}]
    recus = []

    def _cu(*args):
        recus.append(args)
        return None

    noeud = feuille.PerformAIAbility(_SelFixe(acteurs), utility_entity=_SelFixe({"id": 7}),
                                     custom_utility=_cu)
    noeud.execute(_Ctx(acteurs), _Ectx(state=object()))
    assert len(recus[0]) == 3 and recus[0][1:] == (11, 7)


# -------------------------------------- etage 3 : resolu UNE FOIS, pas PAR ACTEUR
def test_l_utility_entity_est_resolu_UNE_SEULE_FOIS_pour_N_acteurs(feuille):
    """LU : dans `PerformAIAbilityUnitBehaviour$$Execute` le `SelectFirst` du champ `+0x80` precede
    le `foreach`, et son resultat est reutilise tel quel a chaque tour.

    Avec un selecteur CONSTANT les deux regimes rendent la meme valeur -- seul le COMPTE les
    separe. C'est pourquoi cette garde compte au lieu de comparer.
    """
    acteurs = [{"id": 11}, {"id": 12}, {"id": 13}]
    sel_ue = _SelFixe({"id": 7})
    noeud = feuille.PerformAIAbility(_SelFixe(acteurs), utility_entity=sel_ue,
                                     custom_utility=lambda s, a, u: None)
    noeud.execute(_Ctx(acteurs), _Ectx(state=object()))
    assert sel_ue.appels == 1, \
        "3 acteurs, UNE resolution : resoudre par acteur serait une infidelite invisible"


def test_sans_utility_entity_le_canal_rend_None_et_ne_fabrique_rien(feuille):
    """Degradation NOMMEE : aucun selecteur `+0x80` (les deux autres noeuds de la famille --
    `PerformAIAttack`, `PerformAIAttackFromCurrentPosition` -- n'en posent pas) -> `None`, jamais
    un repli sur le caster, qui inventerait une entite que le natif ne passe pas."""
    acteurs = [{"id": 11}]
    recus = []
    noeud = feuille.PerformAIAbility(_SelFixe(acteurs), utility_entity=None,
                                     custom_utility=lambda s, a, u: recus.append(u))
    ectx = _Ectx(state=object())
    noeud.execute(_Ctx(acteurs, owner={"id": 7}), ectx)
    assert recus == [None]
    assert ectx.emitted[-1][1]["utility_entity"] is None


# ------------------------------------------- etage 4 : le CALL-SITE 1101 passe bien `Owner`
def test_le_call_site_1101_passe_Owner_et_son_consommateur_le_recoit_en_caster():
    """L'arbre de `1101` cable `utilityEntity = Owner@sel+0x30`, et le consommateur natif en fait
    le `caster` de `GetPreferredAttackTarget`. Cette garde est le point d'ancrage du canal : si un
    jour l'arbre y passait autre chose, elle rougirait au lieu de laisser passer en silence.
    """
    from engine.entities.selectors.accessors import Owner
    from engine.runner.abilities.loki.attempted_possession import (attempted_possession_targets,
                                                                   attempted_possession_tree)

    def _feuilles(noeud, out=None):
        out = [] if out is None else out
        for attr in ("left", "right"):
            enfant = getattr(noeud, attr, None)
            if enfant is not None:
                _feuilles(enfant, out)
        if not hasattr(noeud, "left"):
            out.append(noeud)
        return out

    ais = [f for f in _feuilles(attempted_possession_tree(attempted_possession_targets()))
           if type(f).__name__ == "PerformAIAbility"]
    assert len(ais) == 1, "un seul `PerformAIAbility` dans l'arbre de 1101"
    assert isinstance(ais[0].utility_entity, Owner), "utilityEntity = Owner@sel+0x30"


# ------------------- etage 5 : le consommateur de 1101 LIT le canal (#590-r9)
def test_le_consommateur_1101_declare_le_TROISIEME_parametre():
    """Sans ce parametre, la feuille appelle a DEUX arguments (`_accepte_utility_entity` rend
    `False`) et le canal `+0x80` reste POSE et NON LU -- le court-circuit que #590-r9 nomme."""
    from engine.runner.abilities.behaviours.ai_control import PerformAIAbility
    from engine.runner.abilities.loki.attempted_possession import (
        attempted_possession_custom_utility)

    cu = attempted_possession_custom_utility(state=None, caster_id=7)
    assert PerformAIAbility._accepte_utility_entity(cu), \
        "le delegue `+0x90` de 1101 doit accepter `Item2` du ValueTuple"


def test_le_consommateur_1101_prend_son_caster_DANS_le_canal_pas_dans_sa_fermeture(monkeypatch):
    """`GetPreferredAttackTarget(this, input+8, input+0)` : `input+8` est l'`utilityEntity` RESOLU,
    pas une valeur capturee. La fermeture ne doit plus etre la SOURCE."""
    import engine.runner.abilities.loki.attempted_possession as ap

    vus = []
    monkeypatch.setattr(ap, "attempted_possession_preferred_target",
                        lambda st, caster_id, possessed_id: vus.append((caster_id, possessed_id)))

    cu = ap.attempted_possession_custom_utility(state=None, caster_id=7)
    cu(object(), 11, 42)
    assert vus == [(42, 11)], \
        "le `caster` vient du canal (42), pas du `caster_id` capture au call-site (7)"


def test_le_repli_sur_la_fermeture_est_NOMME_et_ne_s_arme_que_sur_None(monkeypatch):
    """Degradation NOMMEE : aucun `utilityEntity` resolu -> on retombe sur le caster du call-site.
    Rendre `None` ferait sauter TOUTE contrainte de cible (degradation PERMISSIVE)."""
    import engine.runner.abilities.loki.attempted_possession as ap

    vus = []
    monkeypatch.setattr(ap, "attempted_possession_preferred_target",
                        lambda st, caster_id, possessed_id: vus.append((caster_id, possessed_id)))

    cu = ap.attempted_possession_custom_utility(state=None, caster_id=7)
    cu(object(), 11, None)
    assert vus == [(7, 11)], "canal muet -> repli sur le caster capture, jamais un abandon"


def test_le_canal_traverse_la_feuille_jusqu_au_consommateur_de_1101(feuille, monkeypatch):
    """Garde de BOUT EN BOUT : c'est la composition feuille + consommateur qui etait cassee, pas
    l'une des deux moities. La feuille resout `+0x80` et le consommateur en fait son `caster`."""
    import engine.runner.abilities.loki.attempted_possession as ap

    vus = []
    monkeypatch.setattr(ap, "attempted_possession_preferred_target",
                        lambda st, caster_id, possessed_id: vus.append((caster_id, possessed_id)))

    acteurs = [{"id": 11}, {"id": 12}]
    noeud = feuille.PerformAIAbility(
        _SelFixe(acteurs), utility_entity=_SelFixe({"id": 42}),
        custom_utility=ap.attempted_possession_custom_utility(state=None, caster_id=7))
    noeud.execute(_Ctx(acteurs), _Ectx(state=object()))
    assert vus == [(42, 11), (42, 12)], \
        "chaque acteur interroge le MEME utilityEntity resolu, pas le caster capture"
