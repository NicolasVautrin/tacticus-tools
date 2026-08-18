"""#953-r5 -- CLIQUETS OFFLINE du recensement des consommateurs de `scene.hpmax` / `max_hp`.

Ce fichier garde TROIS choses, et aucune n'est de la prose :

  1. **le RECENSEMENT reste complet** -- `probe_953r5_consommateurs_hpmax --check` rend 0. Tout
     site neuf qui lirait `<scene>.hpmax` ou la cle `"max_hp"` sans porter sa classification de
     degradation fait rougir ; toute entree de la table qui ne s'apparie plus a un site reel
     aussi. C'est un INVARIANT dans les deux sens, pas un seuil -- et il porte son propre cran
     ANTI-VIDE (un recenseur qui ne visite rien rendrait `0 non classe` et se lirait comme un
     vert ; c'est exactement ce que son etape 1bis a fait a son premier jet).
  2. **la POLARITE de la degradation, EXECUTABLE.** Le fait que le residu demandait d'etablir
     n'est pas << `hpmax` valait `None` >> mais << ce que `None` PRODUISAIT >>, et la reponse
     n'a pas un seul signe : cote CONDITION D'ACTIVITE la cle ABSENTE ouvre le gate (l'effet vit
     alors qu'il ne devrait pas), cote MAGNITUDE elle le ferme. Les deux sont joues ici.
  3. **le FOYER central**, `engine/utilities/damage.py` : `target_max_hp = None` retombe sur les
     PV COURANTS, donc `combinedMax` SOUS-ESTIME et l'utilite de degat SUR-ESTIME. C'est le site
     par lequel les six playbooks NonComparable subissaient le trou, et il n'etait garde nulle
     part.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

#: #486-r15 -- CE QUI DOIT CHANGER POUR QUE CE FICHIER PUISSE CHANGER DE VERDICT. Il garde un
#: RECENSEMENT de `engine/**` : n'importe quel module du paquet peut y ajouter un site, donc le
#: perimetre est le paquet ENTIER plus le probe qui porte la table. Trop LARGE est sain ici -- un
#: declencheur limite aux quelques fichiers cites serait un faux vert des qu'un module neuf lirait
#: `scene.hpmax`.
DECLENCHEUR = {
    "chemins": (
        # Le SEUL chemin que la cascade d'imports ne couvre pas : la table de classification vit
        # dans le probe, qui n'est importe par aucun module de production.
        "scripts/python/probe_953r5_consommateurs_hpmax.py",
    ),
    "build": False,          # aucune lecture du binaire ni de `data/symbols/**`
    "toujours": True,
    "raison": ("`toujours` parce que le recensement est DERIVE de l'AST de **tout** `engine/**` : "
               "n'importe quel module du paquet peut y AJOUTER un consommateur de `scene.hpmax` "
               "ou de la cle `max_hp`, et c'est precisement le cas que le cliquet doit attraper. "
               "La fermeture d'imports (726 modules) couvre les lecteurs actuels, pas les FUTURS "
               "-- un declencheur limite a elle serait un faux vert des qu'un module neuf, encore "
               "importe par personne, lirait la table."),
}

import probe_953r5_consommateurs_hpmax as CENSUS   # noqa: E402
from engine.playbook.scene import Scene            # noqa: E402
from engine.utilities.damage import damage_composite  # noqa: E402
from engine import weights as W                    # noqa: E402


def test_le_recensement_est_complet_et_non_vide():
    """Etape 1/1bis/2 du probe : 0 site non classe, 0 entree orpheline, et NON VIDE."""
    assert CENSUS.main(["--check"]) == 0


def test_le_recensement_visite_bien_les_sites_temoins():
    """CRAN ANTI-VIDE PROPRE AU TEST : le probe pourrait rendre 0/0 en ne visitant rien. On exige
    donc que ses temoins soient LA -- le site d'ABANDON, le foyer PRODUCTEUR et un gate OUVERT."""
    sites, ecartes = CENSUS.recenser()
    vus = {"%s::%s" % (rel, jeton) for rel, _q, jeton, _l in sites}
    for temoin in ("playbook/prediction/normal_attack.py::hpmax",
                   "playbook/scene.py::max_hp",
                   "entities/effects/loki/hits.py::max_hp",
                   "utilities/tile.py::hpmax"):
        assert temoin in vus, "temoin %r absent du recensement (%d sites)" % (temoin, len(sites))
    # Le perimetre DIT ce qu'il ecarte, et il ecarte reellement quelque chose.
    assert sum(ecartes.values()) > 0 and any("hp_max" in m for m in ecartes)


def test_les_deux_voies_de_construction_sont_mesurees():
    """#953-r5 -- LE FAIT QUI CORRIGE LA FICHE. `engine/**` n'a qu'UN fichier qui appelle
    `Scene.from_predictor_sctx` en remplissant `sctx['hpmax_by_id']` en amont (`ai/context.py`,
    depuis `40da9467`, 2026-07-20). Ce sont les PROBES et OUTILS, qui passent un `step_context`
    BRUT, pour qui `predictor['hpmax_eff_by_id']` est la SEULE source de PV max -- et ils sont
    plusieurs dizaines. Le repli de #953-r1 est donc ce qui met TOUTES les voies d'accord."""
    voies = CENSUS.voies_de_construction()
    assert voies["engine"], "aucun appelant dans engine/** -- le recenseur ne visite rien"
    assert voies["hors_engine"], "aucun appelant hors engine/** -- idem"
    prets = [r for r, ok in voies["engine"] if ok]
    assert prets == ["engine/ai/context.py"], (
        "l'ensemble des voies `engine/**` qui pre-remplissent a change : %r" % (prets,))
    sans = [r for r, ok in voies["hors_engine"] if not ok]
    assert len(sans) >= 10, (
        "on attend une population NON TRIVIALE d'appelants hors engine/** qui dependent du seul "
        "repli ; mesure : %d" % len(sans))


def test_step_context_ne_produit_pas_le_pv_max():
    """La premisse de la fiche, RE-MESUREE et confirmee : `step_context` rend SEPT cles et aucune
    ne porte le PV max. Ce n'est pas un oubli reparable -- `decisionView.units[]` ne le publie pas.
    C'est ce qui rend le repli NECESSAIRE plutot que defensif."""
    import ast
    import inspect
    from engine.playbook import scene as SC
    src = inspect.getsource(SC.step_context)
    arbre = ast.parse(src.lstrip())
    cles = {n.value for n in ast.walk(arbre)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert not {c for c in cles if "hpmax" in c or "max_hp" in c}, (
        "`step_context` porte desormais une cle de PV max : le repli de #953-r1 doit etre relu")


def test_la_cle_max_hp_est_ABSENTE_quand_le_pv_max_ne_l_est_pas():
    """LE `if` QUI FABRIQUE LE GATE OUVERT. `Scene.unit_state` n'ecrit `max_hp` que si la table le
    porte : un trou de substrat devient donc une cle ABSENTE, pas une cle a `None`. C'est cette
    distinction-la que les six `CreateActiveCondition` lisent -- et `.get('max_hp')` rend `None`
    dans les DEUX cas, ce qui est precisement pourquoi la degradation etait invisible."""
    def _scene(hpmax):
        # `Scene` a neuf champs positionnels obligatoires ; on ne les DEVINE pas, on les prend a
        # vide -- seuls `hp_by_id` et `hpmax_by_id` sont lus par `unit_state`.
        return Scene(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                     vis_by_id={}, pos_by_id={}, team_by_id={}, eff_state=None,
                     units=[{"id": 1}], hp_by_id={1: 50}, hpmax_by_id=hpmax)

    vide, plein = _scene({}), _scene({1: 100})
    assert "max_hp" not in vide.unit_state(1)
    assert vide.hpmax(1) is None
    assert plein.unit_state(1)["max_hp"] == 100


@pytest.mark.parametrize("module,classe", [
    ("engine.entities.effects.loki.hits", "AnvilShieldBlockChanceBelowHealthCapEffect"),
    ("engine.entities.effects.loki.status", "HammerOfWrathConditionalDamageEffect"),
])
def test_le_gate_d_activite_est_OUVERT_quand_la_cle_manque(module, classe):
    """POLARITE, jouee. Cle absente -> `is_active` rend VRAI : l'effet contribue a la prediction
    alors que le natif le desactiverait. La degradation du trou #953 etait donc PERMISSIVE ici,
    et RESTRICTIVE cote magnitude -- deux signes opposes pour une seule cause."""
    import importlib
    cls = getattr(importlib.import_module(module), classe)
    eff = cls.__new__(cls)                    # pas de `.ctor` : on n'exerce que le predicat
    for champ, valeur in (("level", 1), ("ability_level", 50), ("source_id", None),
                          ("ability_variables_multiplier", 100)):
        try:
            setattr(eff, champ, valeur)
        except Exception:                     # pragma: no cover - slots / property
            pass
    assert eff.is_active({"hp": 100}) is True, (
        "%s : cle `max_hp` absente -> le gate devrait etre OUVERT (c'est la degradation MESUREE, "
        "pas une preference)" % classe)


def test_le_foyer_damage_SURESTIME_quand_le_pv_max_manque():
    """`engine/utilities/damage.py::DamageUtility.evaluate` -- LE site silencieux du gisement.

    `max_hp = target_max_hp if (target_max_hp and > 0) else hp` : `None` retombe sur les PV
    COURANTS, donc `combinedMax` SOUS-ESTIME et `u_damage = Clamp(D/combinedMax,0,1)*80`
    SUR-ESTIME. On le joue sur une cible BLESSEE (le seul regime ou courant != max), et on exige
    un ECART STRICT -- un test qui passerait sur une cible pleine serait vide."""
    wt = W.load()
    # Les cles LUES par `get_health_damage` / `get_shield_damage` (`min_max_avg` des deux bornes).
    pred = {"hpBefore": 2000, "shieldBefore": 0,
            "healthDmgMin": 1000, "healthDmgMax": 1000,
            "shieldDmgMin": 0, "shieldDmgMax": 0}
    sans = damage_composite(pred, None, wt)          # PV max NON MESURE
    avec = damage_composite(pred, 10000, wt)         # PV max REEL (cible a 2000/10000)
    assert sans > avec, (
        "sans PV max %.6f devrait SUR-ESTIMER par rapport a %.6f -- si l'ecart a disparu, c'est "
        "que le repli du foyer a change et le recensement doit etre relu" % (sans, avec))
