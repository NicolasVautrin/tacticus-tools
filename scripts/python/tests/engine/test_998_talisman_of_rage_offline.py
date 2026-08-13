"""CLIQUET #998 -- la relique `TalismanOfRage` sur l'axe REDUCTION du canal crit-DEGAT
(`TalismanOfRage_CritDamageReduction`, EffectType 0x5ad = 1453), ET la branche du multiplicateur
`BlessingsOfKhorne` qui etait declaree MORTE a tort.

CRITERE : « le port retranche-t-il `critDmgReduction[niveau de RELIQUE] x N` du degat de crit recu
par le porteur, ou `N` est le multiplicateur natif COMPLET -- branche `ActorHasTriggeredAbility`
comprise ? »

CINQ etages, testes SEPAREMENT (aucun scalaire fitte) :
  1. IDENTITE   -- les trois enums et la collision 1460, relus des mirrors ;
  2. REGISTRE   -- la classe est inscrite sous le NOM publie par `decisionView.effects[].name` ;
  3. FOYER      -- `multiplier_based_on_defeated_in_melee` : `Sum` PUIS `Min`, et le tri-etat ;
  4. BRANCHE    -- `If(ActorHasTriggeredAbility(Owner, 0x5b4), mine, 0)` : armee vs non armee ;
  5. CANAL      -- `ForSubtraction(get_OwnerIsTarget, Multiply(ConfigVar(0x97), N))`.

⚠ CE QUI REND L'ETAGE 4 NECESSAIRE, et c'est la trouvaille de la tranche. Le port declarait :
« la branche self-kills est INERTE-PAR-ROSTER : AUCUN unit du gameconfig courant ne porte
TalismanOfRage (verifie unit_map) -- non codee ». **C'est FAUX** : `unit_map.py find --ability
TalismanOfRage` rend SIX unites (trois `lineup` par voie `item` -- les World Eaters, qui portent
justement le trait `BlessingsOfKhorne` -- et trois bosses npc par voie `relic`, ou l'ability est
CABLEE AU KIT). Le verdict venait de l'angle mort **#323** : `unit_map` lisait alors 2 voies
d'attribution sur 5 et etait AVEUGLE AUX RELIQUES. L'etape 4bis re-mesure ce fait contre le
gameconfig VIVANT -- si un jour la relique perd ses porteurs, c'est ICI que ca doit rougir, pas
dans une phrase de docstring.

⚠ LE CAS DISCRIMINANT DE L'ETAGE 3 (`test_le_cap_porte_sur_la_SOMME`) est le seul qui distingue le
mirror juste d'une erreur plausible : le natif fait `Min(Sum(base, extra), cap)`, et
`Sum(Min(base,cap), Min(extra,cap))` rendrait la MEME valeur partout SAUF quand la somme depasse le
cap. Sans ce bras, une implementation fausse passerait au vert.

OFFLINE : ce fichier ne monte AUCUN runner. La confrontation LIVE de la relique (montage
`--equip-relic` sur un World Eater, crit force, mesure de la salve) n'est PAS couverte ici -- elle
est nommee dans le rapport de la tranche comme NON CONFRONTEE.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des deux `conftest.py` et ses gardes.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE MODULE D'EFFET et son inscription au registre : l'objet meme du cliquet.
        "scripts/python/engine/entities/effects/loki/talisman_of_rage.py",
        "scripts/python/engine/entities/effects/loki/__init__.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        # LE FOYER PARTAGE du multiplicateur (il vit dans `status.py`) et le SEEDING de ses deux
        # compteurs par porteur -- les deux points ou la branche peut redevenir muette EN SILENCE.
        "scripts/python/engine/entities/effects/loki/status.py",
        "scripts/python/engine/entities/effects_state.py",
        # LES DEUX ENUMS dont ce fichier fige les ordinaux (et la collision 1460).
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        # LE RECENSEMENT DES PORTEURS : l'etape 4bis re-mesure contre le gameconfig vivant, par les
        # deux outils dont le desaccord a produit le verdict de dead-code falsifie (#323).
        "scripts/python/gameconfig.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/unit_map.py",
    ),
    # `build: True` -- les paliers `critDmgReduction`, le cap `blessingsOfKhorneMaxDefeatedUnits` et
    # la liste des PORTEURS sont RELUS du gameconfig VIVANT : un changement de build peut les
    # deplacer, et c'est precisement ce que ce fichier doit rougir.
    "build": True,
    "toujours": False,
    "raison": (
        "Ce fichier garde le port de la relique `TalismanOfRage` (TriggeredAbilityType 1460) et de "
        "son effet 1453 sur le canal crit-DEGAT, AINSI QUE le foyer partage du multiplicateur "
        "`GetMultiplierBasedOnDefeatedInMelee` -- dont la branche `ActorHasTriggeredAbility` etait "
        "declaree inerte-par-roster a tort. Les chemins listes sont ceux dont une modification peut "
        "faire changer un verdict : le mirror, son registre, le foyer et son seeding, les enums "
        "qu'il fige, et les outils qui recensent les porteurs."),
}

from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.effects.factory import EFFECT_CLASSES, EffectFactory  # noqa: E402
from engine.entities.effects.loki import status as STATUS                # noqa: E402
from engine.entities.effects.loki.talisman_of_rage import (              # noqa: E402
    TalismanOfRageCritDamageReductionEffect)
from engine.entities.effects.magnitude import ability_var                # noqa: E402
from engine.entities.effects_state import (                              # noqa: E402
    EffectsState, melee_defeats_by_killer, seed_battle_counters, units_with_triggered_ability)
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402

_EFFECT_NAME = "TalismanOfRage_CritDamageReduction"
_ABILITY_ID = "TalismanOfRage"
_OWNER = 7


def _effet(level=3, melee_defeats=None, self_kills=None, has_talisman=False):
    """Une instance passee par la MEME fabrique que la production (`EffectFactory.create`), pour que
    le test ne puisse pas passer a cote d'une inscription manquante au registre."""
    e = EffectFactory.create({"name": _EFFECT_NAME, "effectType": int(EffectType(1453)),
                              "level": 1, "remaining": None, "source": _OWNER},
                             100, level, None)
    e.melee_defeats = melee_defeats
    e.melee_defeats_by_owner = self_kills
    e.owner_has_talisman_of_rage = has_talisman
    return e


# --------------------------------------------------------------------- 1. IDENTITE

def test_les_trois_enums_et_la_collision_1460():
    """L'`EffectType` de l'effet et le `TriggeredAbilityType` de sa CONFIG sont DEUX ordinaux
    differents, et 1460 nomme un AUTRE objet dans chaque enum. Confondre les deux ferait lire les
    paliers de `AmuletOfTheVoidwyrm` -- silencieusement, puisque les deux abilities portent la MEME
    cle de variable (`critDmgReduction`) et le meme signe."""
    assert EffectType(1453).name == _EFFECT_NAME
    assert TriggeredAbilityType(1460).name == _ABILITY_ID
    # La collision : 1460 en EffectType est l'AUTRE relique du meme canal.
    assert EffectType(1460).name == "AmuletOfTheVoidwyrm_CritDamageReduction"
    assert EffectType(1460).name != _EFFECT_NAME
    # ... et 1453 en TriggeredAbilityType n'est PAS `TalismanOfRage`.
    assert TriggeredAbilityType(1453).name != _ABILITY_ID
    # CONTROLE DE NON-VIDE : les deux jeux de paliers doivent DIFFERER, sinon la confusion serait
    # inobservable et ce test ne garderait rien.
    a = [ability_var(_ABILITY_ID, "critDmgReduction", i) for i in range(1, 11)]
    b = [ability_var("AmuletOfTheVoidwyrm", "critDmgReduction", i) for i in range(1, 11)]
    assert all(x is not None for x in a), "paliers TalismanOfRage introuvables : %r" % (a,)
    assert a != b, "les deux reliques rendent les MEMES paliers -- la collision serait invisible"


# --------------------------------------------------------------------- 2. REGISTRE

def test_l_effet_est_au_registre_sous_le_nom_publie():
    """La cle d'`EFFECT_CLASSES` est le NOM que publie `decisionView.effects[].name`, pas
    l'ordinal. Une entree manquante degraderait sur `BaseEffect` -- canal `None`, aucune erreur."""
    assert EFFECT_CLASSES.get(_EFFECT_NAME) is TalismanOfRageCritDamageReductionEffect
    assert isinstance(_effet(), TalismanOfRageCritDamageReductionEffect), (
        "la FABRIQUE ne rend pas la classe portee -- l'inscription au registre ne mord pas")


# --------------------------------------------------------------------- 3. FOYER

def test_le_multiplicateur_est_tri_etat_et_ne_fabrique_jamais_de_zero():
    """`melee_defeats is None` = **non mesure** -> `0` (effet inerte), jamais un compte invente.

    ⚠ LE SECOND BRAS EXISTE PARCE QU'UNE MUTATION EST PASSEE AU VERT SANS LUI. Rabattre le
    tri-etat (`melee_defeats = 0` au lieu de `return 0`) est INDISTINGUABLE tant que `self_kills`
    vaut `None` ou `0` -- les deux formes rendent alors `0`. Le SEUL regime discriminant est
    « base NON MESURE mais terme `mine` renseigne » : le rabattement y rendrait `mine`, c'est-a-dire
    une reduction de crit fabriquee a partir d'une mesure absente. C'est exactement le geste que le
    tri-etat interdit, et il ne se voit que la."""
    assert STATUS.multiplier_based_on_defeated_in_melee(None) == 0
    assert STATUS.multiplier_based_on_defeated_in_melee(0) == 0
    assert STATUS.multiplier_based_on_defeated_in_melee(3) == 3
    assert STATUS.multiplier_based_on_defeated_in_melee(
        None, self_kills=3, owner_has_talisman=True) == 0, (
        "base NON MESURE : le multiplicateur doit rester 0, jamais retomber sur le terme `mine`")


def test_le_cap_porte_sur_la_SOMME_pas_sur_chaque_terme():
    """CAS DISCRIMINANT -- `Min(Sum(base, extra), cap)`, et non `Sum(Min(base,cap), Min(extra,cap))`.

    Les deux formes coincident partout SAUF quand la somme depasse le cap : c'est le seul regime ou
    ce bras discrimine, donc il est joue explicitement."""
    cap = STATUS.multiplier_based_on_defeated_in_melee(10_000)
    assert cap > 0, "cap `blessingsOfKhorneMaxDefeatedUnits` introuvable"
    base, extra = cap - 1, cap - 1                       # somme = 2*cap - 2 > cap des que cap > 2
    assert base + extra > cap, "regime non discriminant (cap = %d)" % cap
    n = STATUS.multiplier_based_on_defeated_in_melee(base, self_kills=extra,
                                                     owner_has_talisman=True)
    assert n == cap, "le cap doit porter sur la SOMME : attendu %d, rendu %d" % (cap, n)
    assert n != base + extra, "aucun cap applique"


# --------------------------------------------------------------------- 4. BRANCHE

def test_la_branche_self_kills_est_ARMEE_par_le_seul_ActorHasTriggeredAbility():
    """`If(ActorHasTriggeredAbility(Owner@+0x30, 0x5b4), mine, Direct(0))` : c'est le BOOLEEN qui
    decide, pas la presence du compteur. Non arme -> le natif verse `Direct(0)`."""
    arme = STATUS.multiplier_based_on_defeated_in_melee(2, self_kills=1, owner_has_talisman=True)
    nu = STATUS.multiplier_based_on_defeated_in_melee(2, self_kills=1, owner_has_talisman=False)
    assert arme == 3 and nu == 2, "arme=%r nu=%r" % (arme, nu)
    assert arme != nu, "la branche ne mord pas -- elle serait indistinguable d'un no-op"
    # tri-etat du SECOND compteur : arme mais non mesure -> le base SEUL, jamais une invention.
    assert STATUS.multiplier_based_on_defeated_in_melee(
        2, self_kills=None, owner_has_talisman=True) == 2


def test_le_seeding_pose_les_deux_compteurs_PAR_PORTEUR():
    """`seed_battle_counters` est le foyer PARTAGE par les deux faces. Le compte de base est GLOBAL,
    les deux autres sont PAR PORTEUR -- c'est ce que l'iteration sur `bu.items()` doit refleter."""
    units = [
        {"id": _OWNER, "alive": True, "triggered": [int(TriggeredAbilityType.TalismanOfRage)]},
        {"id": 8, "alive": True, "triggered": []},
        {"id": 20, "alive": False, "defeatedByMelee": True, "killerId": _OWNER},
        {"id": 21, "alive": False, "defeatedByMelee": True, "killerId": _OWNER},
        {"id": 22, "alive": False, "defeatedByMelee": True, "killerId": 8},
        {"id": 23, "alive": False, "defeatedByMelee": False, "killerId": _OWNER},   # pas melee
        {"id": 24, "alive": True, "defeatedByMelee": True, "killerId": _OWNER},     # RESSUSCITEE
    ]
    assert melee_defeats_by_killer(units) == {_OWNER: 2, 8: 1}, (
        "le terme `mine` doit heriter des DEUX gates du compte de base (melee ET mort)")
    assert units_with_triggered_ability(
        units, int(TriggeredAbilityType.TalismanOfRage)) == {_OWNER}

    # Le seeding est teste sur `BlessingsOfKhorne`, PAS sur l'effet de la relique : les deux
    # consommateurs du foyer arment la branche par des voies DIFFERENTES, et c'est structurel.
    #   * `BlessingsOfKhorne_ModifiersEffect` est pose par un TRAIT -- son Owner peut porter ou non
    #     la relique, donc le booleen doit etre MESURE (`ActorHasTriggeredAbility`) ;
    #   * `TalismanOfRage_CritDamageReductionEffect` est un OWNER-EFFECT de la relique elle-meme :
    #     son Owner EST le porteur de 1460 par construction (`AOwnerEffectTriggeredAbility$$
    #     CreateBehaviour` pose `source = targets = Owner`), donc le test natif est VRAI sans etre
    #     mesure. Le port l'ecrit en dur et le dit -- cf. `talisman_of_rage.py::_n`.
    st = EffectsState.seed({_OWNER: [{"name": "BlessingsOfKhorne", "effectType": 1262, "level": 1}],
                            8: [{"name": "BlessingsOfKhorne", "effectType": 1262, "level": 1}]})
    n = seed_battle_counters(st, units)
    assert n == 3, "compte de base GLOBAL attendu 3, rendu %r" % (n,)
    porteur, autre = st.by_unit[_OWNER][0], st.by_unit[8][0]
    assert type(porteur).__name__ == "BlessingsOfKhorneModifiersEffect", (
        "la fabrique n'a pas rendu la classe attendue (%s) -- le bras ne testerait rien"
        % type(porteur).__name__)
    assert porteur.melee_defeats == 3 and autre.melee_defeats == 3, "le base doit rester GLOBAL"
    assert porteur.melee_defeats_by_owner == 2, "self-kills du porteur : %r" % (
        porteur.melee_defeats_by_owner,)
    assert autre.melee_defeats_by_owner == 1, "self-kills de l'autre : %r" % (
        autre.melee_defeats_by_owner,)
    assert porteur.owner_has_talisman_of_rage is True
    assert autre.owner_has_talisman_of_rage is False
    # ... et l'effet du non-porteur ne verse donc PAS le terme `mine`.
    assert porteur._n() == 5 and autre._n() == 3, "%r / %r" % (porteur._n(), autre._n())


def test_l_owner_effect_de_la_relique_arme_la_branche_PAR_CONSTRUCTION():
    """Le pendant du bras precedent : l'effet de la relique n'a PAS a mesurer
    `ActorHasTriggeredAbility` -- son Owner EST le porteur de 1460.

    C'est ce qui rend le port INSENSIBLE a une question de seeding ouverte : que
    `decisionView.units[].triggered` publie ou non les abilities TERTIAIRES (hierarchie 3, cf.
    `case-237`) ne change RIEN pour cet effet-ci. Ce bras fige ce choix -- s'il devait un jour etre
    mesure, c'est ici que le changement doit se voir."""
    e = _effet(level=3, melee_defeats=2, self_kills=1)      # `has_talisman` PAS passe
    assert e._n() == 3, "l'owner-effect doit compter le terme `mine` sans qu'on l'arme : %r" % e._n()
    # Contre-epreuve : sans le terme `mine`, le meme etat rendrait 2.
    assert STATUS.multiplier_based_on_defeated_in_melee(2, self_kills=1,
                                                        owner_has_talisman=False) == 2


def test_les_porteurs_de_la_relique_existent_VRAIMENT(request):
    """ETAPE 4bis -- LE FAIT QUI FALSIFIE LE VERDICT DE DEAD-CODE, re-mesure contre le gameconfig
    VIVANT (jamais contre une phrase de docstring).

    Le port declarait « AUCUN unit du gameconfig courant ne porte TalismanOfRage (verifie
    unit_map) ». Deux recensements independants sont croises ici, exactement parce que le desaccord
    entre eux EST le gisement #323 : la voie RELIQUE (`items[*].abilityId` -> `allowedUnits`) et le
    trait `BlessingsOfKhorne` du kit. Les porteurs de la relique doivent etre des World Eaters,
    sinon les deux termes du multiplicateur ne se rencontrent jamais sur la meme unite."""
    import catalog_inject
    import gameconfig as GC
    porteurs = catalog_inject.relic_carriers(_ABILITY_ID)
    assert porteurs, (
        "0 porteur pour %s -- c'est EXACTEMENT le zero qui avait fait classer la branche en "
        "dead-code ; s'il redevient vrai, le port doit etre re-examine, pas la doctrine" % _ABILITY_ID)
    khorne = [u for u in porteurs
              if "BlessingsOfKhorne" in ((GC.unit(u) or {}).get("traits") or [])]
    assert khorne == list(porteurs), (
        "les porteurs de la relique doivent TOUS porter le trait BlessingsOfKhorne (sinon la "
        "branche `extra` ne peut jamais mordre) : relique=%r trait=%r" % (list(porteurs), khorne))


# --------------------------------------------------------------------- 5. CANAL

def test_le_canal_est_ForSubtraction_et_rend_un_terme_NEGATIF():
    """`GetCritDamageBonusFromEffects` accumule `addition - subtraction` : le port rend un ENTIER
    NEGATIF, mirror du terme soustractif -- pas une convention locale."""
    e = _effet(level=3, melee_defeats=2, self_kills=1, has_talisman=True)
    v = e.create_effect_crit_damage_bonus_for_attack({"owner_id": _OWNER, "tgt_id": _OWNER})
    attendu = -(ability_var(_ABILITY_ID, "critDmgReduction", 3) * 3)     # N = 2 + 1
    assert v == attendu, "canal = %r, attendu %r" % (v, attendu)
    assert v < 0, "`ForSubtraction` doit verser un terme NEGATIF"


def test_le_trigger_get_OwnerIsTarget_est_NU_et_ferme_sur_identite_non_prouvee():
    """`AreEqual(Owner@+0x30, Target@+0x60)`, aucun `op_BitwiseAnd`. Une cle ABSENTE => noeud FAUX,
    jamais permissif : un contexte incomplet ne doit pas faire verser une reduction."""
    e = _effet(level=3, melee_defeats=2, self_kills=1, has_talisman=True)
    assert e.create_effect_crit_damage_bonus_for_attack(
        {"owner_id": _OWNER, "tgt_id": 99}) is None, "le porteur n'est pas le defenseur"
    assert e.create_effect_crit_damage_bonus_for_attack({"owner_id": _OWNER}) is None
    assert e.create_effect_crit_damage_bonus_for_attack({"tgt_id": _OWNER}) is None
    assert e.create_effect_crit_damage_bonus_for_attack(None) is None


@pytest.mark.parametrize("level", [1, 3, 10])
def test_le_produit_discrimine_le_NIVEAU_et_le_COMPTEUR_separement(level):
    """Les deux facteurs bougent INDEPENDAMMENT -- c'est ce qui interdit de fitter un scalaire :
    a compteur fixe le niveau doit bouger le resultat, et a niveau fixe le compteur aussi."""
    ctx = {"owner_id": _OWNER, "tgt_id": _OWNER}
    v1 = _effet(level=level, melee_defeats=1, has_talisman=False
                ).create_effect_crit_damage_bonus_for_attack(ctx)
    v2 = _effet(level=level, melee_defeats=2, has_talisman=False
                ).create_effect_crit_damage_bonus_for_attack(ctx)
    assert v2 == 2 * v1, "le compteur doit DOUBLER la reduction : %r puis %r" % (v1, v2)
    assert v1 == -ability_var(_ABILITY_ID, "critDmgReduction", level)
    # a compteur EGAL, deux niveaux distincts doivent rendre deux valeurs distinctes.
    autre = 10 if level != 10 else 1
    v3 = _effet(level=autre, melee_defeats=1, has_talisman=False
                ).create_effect_crit_damage_bonus_for_attack(ctx)
    assert v3 != v1, "les niveaux %d et %d rendent la MEME valeur" % (level, autre)


def test_sans_compteur_mesure_le_canal_est_MUET():
    """`melee_defeats is None` (aucun seeding) -> `N = 0` -> aucune contribution. Degradation
    fidele « present != applique », et surtout : jamais un 0 qui se lirait comme une mesure."""
    e = _effet(level=3, melee_defeats=None)
    assert e.create_effect_crit_damage_bonus_for_attack(
        {"owner_id": _OWNER, "tgt_id": _OWNER}) is None
