"""#969-r4 -- GARDE du `ListExtensions.Remove` que le port n'appliquait pas.

CE QUI EST GARDE, et pourquoi ca ne se voyait nulle part. `abilityTargets` rend la sortie BRUTE
du slot `0x42` d'`IAttackQuery` ;
`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities` y enchaine un
`ListExtensions.Remove(list, t => !ShouldEvaluateTarget(t))`. Le port lisait la sortie brute :
l'ensemble des cibles de TOUT playbook etait donc PERMISSIF, sans erreur ni crash.

⚠ LA FICHE PLACAIT LE `Remove` DANS `GetEligibleTargetsSelectable` -- IL N'Y EST PAS. Relu sur
`t6dpr4k06g` : cette fonction appelle `GetEligibleTargetsEntities` puis emet, sans filtrer. Le
nom du lambda le disait deja (`<GetEligibleTargetsEntities>b__58_0`). L'effet est le meme (toutes
les voies passent par `Entities`), la citation ne l'etait pas.

Les etages :

  A. LE PREDICAT, terme par terme, contre le decompile :
        ShouldEvaluateTarget(t) = !(IsUnit(t) && CurrentOwnerIsEnvironment(t))
                                  && !IsIrrelevantObject(t)
        IsIrrelevantObject(u)   = HasTrait(Steppable) || (GetStat(Attack) < 1 && HasTrait(Object))
     Le SEUIL `< 1` est teste pour lui-meme : c'est un litteral natif, et `== 0` passerait tous
     les cas usuels.

  B. LE TRI-ETAT, qui commande le SENS du doute : on ne RETIRE que sur une mesure POSITIVE. Un
     substrat non mesure laisse la cible EN PLACE -- le comportement d'AVANT. Sans cet etage, le
     port deviendrait RESTRICTIF sur les montages offline, ce qui serait une regression neuve.

  C. LES DEUX CONSOMMATEURS, cables sur le foyer : `_targets.eligible_units` / `eligible_any` et
     `nonattack.eligible_targets`. Le mutant (foyer neutralise) doit faire RATER l'etage --
     sinon la garde ne garderait rien.

  D. LE DOMAINE : une entite TUILE n'est JAMAIS ecartee (`IsIrrelevantObject` commence par
     `TryGetComponent<BaseUnitComponent>` et rend `false` sans composant). C'est ce que #302 a
     ouvert, et un filtre trop large le refermerait en silence.

ASCII only (cp1252).
"""
from __future__ import annotations

#: DECLENCHEUR -- purement offline, aucun runner.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/engine/**/*.py", "scripts/python/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Aucun runner, aucun RPC : le predicat est exerce sur des `UnitContext` construits "
              "a la main et les deux consommateurs sur des payloads `abilityTargets` synthetiques. "
              "Les ordinaux de trait viennent du mirror `UnitTrait` (deja sous cliquet "
              "`probe_313`), pas d'une table de build -> `build: False`.",
}

import os                                                                # noqa: E402
import sys                                                               # noqa: E402

import pytest                                                            # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from engine.entities.traits.unit_trait import UnitTrait                  # noqa: E402
from engine.playbook import nonattack as NA                              # noqa: E402
from engine.playbook import should_evaluate_target as SET                # noqa: E402
from engine.playbook.noncomparable import _targets as T                  # noqa: E402


class _Ctx:
    """Le minimum que le foyer LIT : `traits` (ids), `attack`, `current_owner_is_environment`."""

    def __init__(self, traits=(), attack=1000, env=False):
        self.traits = list(traits)
        self.attack = attack
        self.current_owner_is_environment = env


# =================================================================================================
# ETAGE A -- LE PREDICAT, TERME PAR TERME
# =================================================================================================

def test_a1_unite_ordinaire_est_evaluee():
    assert SET.should_evaluate_target(_Ctx(traits=[int(UnitTrait.Hero)], attack=2312)) is True


def test_a2_steppable_est_ecarte_meme_avec_une_attaque():
    """1re branche d'`IsIrrelevantObject` : le trait `Steppable` COURT-CIRCUITE avant toute
    lecture de stat. Un power-up n'a pas besoin d'attaque lisible pour etre ecarte."""
    ctx = _Ctx(traits=[int(UnitTrait.Steppable)], attack=9999)
    assert SET.is_irrelevant_object(ctx) is True
    assert SET.should_evaluate_target(ctx) is False


def test_a3_object_SANS_attaque_est_ecarte():
    """2e branche : `GetStat(Attack) < 1 && HasTrait(Object)`. C'est le cas MESURE en live --
    `LootObj_Strongbox_Imp`, traits `13,28`, `stats.attack = 0`, present dans `fromHere`."""
    ctx = _Ctx(traits=[int(UnitTrait.Object)], attack=0)
    assert SET.is_irrelevant_object(ctx) is True
    assert SET.should_evaluate_target(ctx) is False


def test_a4_object_AVEC_attaque_est_GARDE():
    """LE TEMOIN NON DEGENERE de l'etage : MEME trait, verdict INVERSE. Sans lui, un filtre qui
    ecarterait tout `Object` passerait A3 et serait FAUX."""
    ctx = _Ctx(traits=[int(UnitTrait.Object)], attack=1)
    assert SET.is_irrelevant_object(ctx) is False
    assert SET.should_evaluate_target(ctx) is True


@pytest.mark.parametrize("attaque,ecarte", [(-5, True), (0, True), (1, False), (2, False)])
def test_a5_le_seuil_est_bien_INFERIEUR_A_UN(attaque, ecarte):
    """`< 1`, le litteral natif -- PAS `== 0`. Une attaque NEGATIVE (possible sous debuff) rend
    l'objet irrelevant, et `Attack == 1` ne le rend PAS. Les deux bornes sont testees : un port
    ecrit `== 0` passerait les deux cas usuels et raterait exactement ceux-la."""
    assert SET.is_irrelevant_object(_Ctx(traits=[int(UnitTrait.Object)], attack=attaque)) is ecarte


def test_a6_environnement_ecarte_une_UNITE_seulement():
    """1er terme : `IsUnit(t) && CurrentOwnerIsEnvironment(t)`. Le `IsUnit` n'est PAS decoratif --
    le natif ne l'applique qu'aux unites, et une entite-tuile appartenant a l'environnement doit
    rester."""
    env = _Ctx(traits=[int(UnitTrait.Hero)], attack=2000, env=True)
    assert SET.should_evaluate_target(env, is_unit=True) is False
    assert SET.should_evaluate_target(env, is_unit=False) is True


def test_a7_les_DEUX_drapeaux_ne_se_confondent_PAS():
    """PIEGE TROUVE EN ECRIVANT CE FICHIER, et il aurait rendu le filtre INERTE sur les MoW.

    `IsUnit` garde le PREMIER terme ; `IsIrrelevantObject`, lui, ne depend que de la presence
    d'un `BaseUnitComponent`. Une MACHINE OF WAR n'est pas forcement `IsUnit` mais en PORTE un
    (son `MachineComponent` en DERIVE -- c'est ce qui fait marcher la voie `GetBaseUnitComponent`
    de #1039). Un port qui aurait ecrit `if not is_unit: return True` l'aurait donc laissee
    passer quoi qu'elle porte.

    Ici : meme `ctx` irrelevant, TROIS combinaisons, TROIS verdicts qui doivent differer."""
    irr = _Ctx(traits=[int(UnitTrait.Steppable)], attack=0)
    # unite ordinaire irrelevante -> ecartee
    assert SET.should_evaluate_target(irr, is_unit=True) is False
    # MoW (pas `IsUnit`, mais PORTE un BaseUnitComponent) -> ecartee QUAND MEME
    assert SET.should_evaluate_target(irr, is_unit=False,
                                      has_base_unit_component=True) is False
    # entite TUILE (aucun BaseUnitComponent) -> GARDEE
    assert SET.should_evaluate_target(irr, is_unit=False,
                                      has_base_unit_component=False) is True


# =================================================================================================
# ETAGE B -- LE TRI-ETAT : ON NE RETIRE QUE SUR UNE MESURE POSITIVE
# =================================================================================================

def test_b1_traits_non_mesures_ne_retirent_rien():
    """`traits` vide = PAS MESURE (le port n'a pas hydrate l'entite). Retirer ici transformerait
    un trou de substrat en RESTRICTION -- l'inverse exact de la degradation qu'on corrige."""
    ctx = _Ctx(traits=[], attack=0)
    assert SET.is_irrelevant_object(ctx) is None
    assert SET.should_evaluate_target(ctx) is True


def test_b2_attaque_non_lue_sur_un_Object_ne_retire_rien():
    """Trait `Object` MESURE mais attaque inconnue : indetermine -> on garde."""
    ctx = _Ctx(traits=[int(UnitTrait.Object)], attack=None)
    assert SET.is_irrelevant_object(ctx) is None
    assert SET.should_evaluate_target(ctx) is True


def test_b3_canal_environnement_non_mesure_ne_retire_rien():
    """`current_owner_is_environment is None` = capteur absent. ⚠ C'est ICI que le tri-etat est le
    plus glissant : ce predicat est FAUX pour la quasi-totalite des unites, donc un repli sur
    `False` serait d'accord avec le natif partout SAUF dans le seul regime qui existe pour le
    mesurer. `None` doit se comporter comme `False` cote DECISION (on garde) tout en restant
    DISTINGUABLE cote canal."""
    ctx = _Ctx(traits=[int(UnitTrait.Hero)], attack=2000, env=None)
    assert SET.should_evaluate_target(ctx) is True


def test_b4_cible_sans_UnitContext_est_gardee():
    """Le port n'hydrate pas toutes les entites. `filtrer_cibles` garde ce qu'il ne connait pas."""
    assert SET.filtrer_cibles({}, [(81, (1, 0)), (106, (0, 1))], cle=lambda e: e[0]) \
        == [(81, (1, 0)), (106, (0, 1))]


# =================================================================================================
# ETAGE C -- LES DEUX CONSOMMATEURS
# =================================================================================================

#: Le montage MESURE en live (runner 112, board MC1_67) : l'ennemi ordinaire et le Strongbox
#: cote a cote dans `fromHere`.
ENNEMI, STRONGBOX, POD = 81, 106, 108


class _NCtx:
    """Le minimum que les deux consommateurs LISENT."""

    def __init__(self, cibles, tab):
        self.uid = 77
        self.units = [{"id": i, "pos": {"col": 1, "row": 1}} for i, _k in cibles]
        self.tile_id_by_pos = {}
        self.scene = type("_S", (), {"ctx_by_id": tab})()
        self._cibles = cibles

    def ability_targets(self, uid, ability_id):
        cibles = [{"kind": k, "targetId": i} for i, k in self._cibles]
        return {"units": [{"unitId": self.uid, "abilities": [
            {"abilityId": ability_id, "targets": cibles, "fromHere": cibles}]}]}


def _tab():
    return {
        ENNEMI: _Ctx(traits=[int(UnitTrait.Hero)], attack=2312),
        STRONGBOX: _Ctx(traits=[int(UnitTrait.Object)], attack=0),      # ECARTE par le natif
        POD: _Ctx(traits=[int(UnitTrait.Object)], attack=1125),         # GARDE (temoin)
    }


def test_c1_eligible_units_retire_l_objet_irrelevant():
    ctx = _NCtx([(ENNEMI, "unit"), (STRONGBOX, "unit"), (POD, "unit")], _tab())
    assert [t for t, _p in T.eligible_units(ctx, 69)] == [ENNEMI, POD]


def test_c2_eligible_any_retire_l_objet_mais_garde_la_TUILE():
    """ETAGE D en meme temps : une entite `kind == "tile"` n'est jamais ecartee, meme si un
    `UnitContext` homonyme la declarerait irrelevante."""
    tab = _tab()
    tab[999] = _Ctx(traits=[int(UnitTrait.Steppable)], attack=0)
    ctx = _NCtx([(ENNEMI, "unit"), (STRONGBOX, "unit"), (999, "tile")], tab)
    assert [t for t, _p, _k in T.eligible_any(ctx, 69)] == [ENNEMI, 999]


def test_c3_nonattack_eligible_targets_retire_l_objet():
    pb = type("_PB", (NA.NonAttackComparablePlaybook,), {
        "ability_id": 69, "targets_tiles": lambda self, a: False})()
    ctx = _NCtx([(ENNEMI, "unit"), (STRONGBOX, "unit"), (POD, "unit")], _tab())
    assert pb.eligible_targets(ctx, 69) == [ENNEMI, POD]


def test_c4_mutant_foyer_neutralise_fait_rater_les_deux_etages(monkeypatch):
    """MUTATION ADVERSARIALE = l'arbre d'AVANT, a la ligne pres : le foyer rend l'identite.
    Les deux consommateurs doivent alors RE-ADMETTRE le Strongbox.

    Substitution en FORME B (`_SET.<nom>` via `setattr` sur le MODULE) : les deux sites lisent
    l'attribut de module a chaque appel, donc le patch MORD. Une liaison `from X import f` au
    niveau module l'aurait GELE -- c'est la cause mesuree des 28 rouges de #484."""
    monkeypatch.setattr(SET, "filtrer_cibles",
                        lambda tab, cibles, cle=None, kind=None: cibles)
    ctx = _NCtx([(ENNEMI, "unit"), (STRONGBOX, "unit"), (POD, "unit")], _tab())
    assert [t for t, _p in T.eligible_units(ctx, 69)] == [ENNEMI, STRONGBOX, POD]
    pb = type("_PB", (NA.NonAttackComparablePlaybook,), {
        "ability_id": 69, "targets_tiles": lambda self, a: False})()
    assert pb.eligible_targets(ctx, 69) == [ENNEMI, STRONGBOX, POD]


def test_c5_sans_scene_le_comportement_est_INCHANGE():
    """Un `ctx` sans predicteur (`scene is None`) ne filtre RIEN : le statu quo, exactement.
    C'est ce qui rend ce port non regressif sur tous les montages offline existants."""
    ctx = _NCtx([(ENNEMI, "unit"), (STRONGBOX, "unit")], _tab())
    ctx.scene = None
    assert [t for t, _p in T.eligible_units(ctx, 69)] == [ENNEMI, STRONGBOX]
