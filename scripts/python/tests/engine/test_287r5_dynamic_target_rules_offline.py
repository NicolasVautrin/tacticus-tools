"""#287-r5 -- GARDE OFFLINE des trois regles dynamiques portees par cette tranche.

Pendant exact de `test_287r4r1_dynamic_target_rules_offline.py`, meme discipline, sur les regles
1185 `ForwardObservers`, 1177 `LightOfSanguinius` et 1175 `BloodChalice`. Cinq etages :

  1. RECENSEMENT -- les trois ids sont EVALUABLES, et le recenseur re-derive de la table de symboles
     tient son CLIQUET D'APPARIEMENT (aucun id a surcharge native sans etage recense, aucune entree
     d'etage sans symbole natif).
  2. ORDINAUX FIGES AU SITE. `probe_313` compare le MIRROR au BUILD : il redevient vert des qu'on
     regenere le mirror apres un renumerotage, alors que la valeur ECRITE AU SITE, elle, a change.
     Cet etage garde les ordinaux que les trois regles LISENT.
  3. BASCULE -- chaque regle DISCRIMINE : un substrat qui REFUSE, un substrat qui ACCEPTE, ne
     differant que par la grandeur que le corps natif lit.
  4. MUTANTS -- desarmer la regle EFFONDRE la bascule. Le critere est le DELTA
     (`avant == refus` ET `apres == 0`), jamais `apres == 0` seul : mesure du 2026-08-06, ce
     dernier rendait 5/5 sur un arbre ou AUCUNE regle n'etait portee.
  5. LE CHAINON COMPLET -- `is_invalid_target`, la cascade entiere, pas la regle isolee. Sans lui,
     une regle juste mais jamais ATTEINTE passerait pour portee.

Le fichier est jouable des DEUX cotes du correctif : `DYNAMIC_TARGET_RULE_UNPORTED` est lu par un
repli NOMME (dict vide), donc son rouge est un rouge de MECANIQUE, pas un `ImportError`.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import pytest                                                                  # noqa: E402

import probe_287r4r1_dynamic_target_rules as P                                 # noqa: E402
import probe_287r5_etages_bloquants as R                                       # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType              # noqa: E402
from engine.entities.effect_type import EffectType                             # noqa: E402
from engine.entities.effects_state import EffectsState                         # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                        # noqa: E402
import engine.runner.abilities.targeting as TG                                 # noqa: E402
from engine.runner.abilities.targeting import is_invalid_target                # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR         # noqa: E402

DYN = getattr(TG, "DYNAMIC_TARGET_RULE_UNPORTED", {})

# MEME RAISON QUE `DYN`, ET ELLE A ETE MESUREE. Un `from engine.entities.heal_type import HealType`
# en tete fait rougir CE FICHIER par un `ImportError` sur l'arbre d'AVANT (le mirror n'y existe pas)
# -- un rouge de STRUCTURE, qui interrompt la COLLECTE et masque les etages de mecanique qu'on veut
# justement voir rouges. Le repli est NOMME et rend `None` ; l'etage 2 le traduit alors en un rouge
# qui DIT ce qui manque (« le port ne sait pas nommer le heal type »), au lieu de ne rien dire.
try:                                                            # noqa: SIM105
    from engine.entities.heal_type import HealType
    HEAL_TYPE_NON_MECHANICAL = int(HealType.NonMechanical)
except ImportError:
    HEAL_TYPE_NON_MECHANICAL = None

CASTER, CIBLE = P.CASTER, P.CIBLE
FO = int(ActiveAbilityType.ForwardObservers)         # 1185
LOS = int(ActiveAbilityType.LightOfSanguinius)       # 1177
BCH = int(ActiveAbilityType.BloodChalice)            # 1175


class _EffetMarkerlight:
    """Porteur minimal d'un `EffectType.Markerlight` sur une entite, pour l'`EffectsState`."""
    __slots__ = ("unit_id", "effect_type", "consumed", "source", "remaining_turns")

    def __init__(self, unit_id: int):
        self.unit_id = int(unit_id)
        self.effect_type = int(EffectType.Markerlight)
        self.consumed = False
        self.source = None
        self.remaining_turns = 0


def _cas_forward_observers():
    """1185 -- `HasEffect(target, Markerlight)`. Les deux substrats ne different QUE par l'effet."""
    refuse = P.substrat([(CASTER, "tauNpc5StealthSuit", 1, 0, 0, []),
                         (CIBLE, "orksWarboss", 2, 1, 0, [])])
    if refuse.effects is None:
        refuse.effects = EffectsState()
    refuse.effects.add_effect(CIBLE, _EffetMarkerlight(CIBLE))
    passe = P.substrat([(CASTER, "tauNpc5StealthSuit", 1, 0, 0, []),
                        (CIBLE, "orksWarboss", 2, 1, 0, [])])
    if passe.effects is None:
        passe.effects = EffectsState()
    return refuse, passe


def _cas_light_of_sanguinius():
    """1177 -- les deux substrats ne different QUE par la DISTANCE caster <-> cible.

    Le board de `P.substrat` fait 6x6, toutes tuiles marchables : la cible a donc toujours des
    tuiles adjacentes LIBRES (l'etage 1 passe), et c'est bien l'etage 2 (`GetDistance <= range`,
    range = 5 au gameconfig) qui tranche."""
    refuse = P.substrat([(CASTER, "bloodDante", 1, 0, 0, []),
                         (CIBLE, "orksWarboss", 2, 5, 5, [])])
    passe = P.substrat([(CASTER, "bloodDante", 1, 0, 0, []),
                        (CIBLE, "orksWarboss", 2, 2, 0, [])])
    return refuse, passe


def _cas_blood_chalice():
    """1175 -- les deux substrats sont ADJACENTS des deux cotes et ne different QUE par le trait
    `LivingMetal`, qui rend `IsMechanical` vrai et donc `IsAffectedByHealType(_, NonMechanical)`
    faux. C'est ce qui isole le terme HEAL TYPE de celui d'ADJACENCE."""
    refuse = P.substrat([(CASTER, "bloodSanguinary", 1, 0, 0, []),
                         (CIBLE, "necroWarden", 1, 1, 0, [UnitTrait.LivingMetal])])
    passe = P.substrat([(CASTER, "bloodSanguinary", 1, 0, 0, []),
                        (CIBLE, "thousTzaangor", 1, 1, 0, [])])
    return refuse, passe


CAS = [
    (FO, "effet Markerlight deja pose", _cas_forward_observers,
     int(TR.TargetMatchesDynamicRule)),
    (LOS, "aucune tuile libre a range du caster", _cas_light_of_sanguinius,
     int(TR.TargetHasFreeAdjacentTile)),
    (BCH, "allie adjacent MECANIQUE (LivingMetal)", _cas_blood_chalice,
     int(TR.TargetMatchesDynamicRule)),
]


# ================================================================================================
# 1. RECENSEMENT
# ================================================================================================

def test_les_trois_regles_sont_evaluables():
    manquantes = [aid for aid, _l, _f, _r in CAS if P.evaluabilite(aid) == "aucune"]
    assert not manquantes, (
        "regle(s) non evaluable(s) : %s -- une ability qui pose TargetMatchesDynamicRule sans regle "
        "portee degrade en `0` PERMISSIF, silencieusement" % manquantes)


def test_le_recenseur_tient_son_cliquet_d_appariement():
    """Le recensement est DERIVE de `ghidra/functions.tsv`, pas ecrit : il doit rester en phase."""
    res = R.recenser()
    par_classe = R.symboles_natifs()
    orphelins = [n for _a, n, _s in res["dette"] if _a not in R.ETAGE_BLOQUANT]
    fantomes = [ActiveAbilityType(a).name for a in R.ETAGE_BLOQUANT
                if ActiveAbilityType(a).name + "Ability" not in par_classe]
    assert not orphelins, ("id(s) a surcharge NATIVE lisible sans etage recense : %s -- le "
                           "recensement se tait sur un corps qu'il VOIT" % orphelins)
    assert not fantomes, ("entree(s) d'ETAGE_BLOQUANT sans symbole natif : %s -- renommage "
                          "inter-build : re-lire la table, pas rafraichir la table ecrite" % fantomes)
    assert res["dette"], "recensement de la DETTE vide -- un probe qui ne visite rien ne mesure rien"


def test_le_compte_sans_regle_a_baisse():
    """Le chiffre que cette tranche fait bouger. Il est RE-DERIVE, jamais cite."""
    res = R.recenser()
    aucune = len(res["dette"]) + len(res["base"])
    assert aucune <= 43, (
        "« aucune regle » = %d ; #287-r5 l'a mesure a 43 (46 avant la tranche). Une remontee "
        "signifie qu'une ability est entree en posant TargetMatchesDynamicRule sans sa regle."
        % aucune)


# ================================================================================================
# 2. ORDINAUX FIGES AU SITE
# ================================================================================================

@pytest.mark.parametrize("membre,attendu,ou", [
    (int(EffectType.Markerlight), 0x462, "ForwardObserversAbility$$GetDynamicInvalidTargetReason"),
    (HEAL_TYPE_NON_MECHANICAL, 0,
     "BloodChaliceAbility -> UnitExtensions$$IsAffectedByHealType ; `None` = le mirror "
     "`engine/entities/heal_type.py` n'existe pas, donc le port ne sait pas NOMMER ce heal type"),
    (int(UnitTrait.AffectedByHealAndRepair), 0x421, "UnitExtensions$$IsAffectedByHealType"),
    (int(UnitTrait.Mechanical), 0x5, "UnitExtensions$$IsMechanical"),
    (int(UnitTrait.LivingMetal), 0x3e8, "UnitExtensions$$IsMechanical"),
    (int(UnitTrait.Vehicle), 0x405, "UnitExtensions$$IsMechanical"),
    (int(TR.TargetHasFreeAdjacentTile), 0x20, "LightOfSanguiniusAbility -- le code RENDU"),
    (int(TR.TargetMatchesDynamicRule), 0x2, "le bit qui fait invoquer le delegue"),
])
def test_ordinal_fige_au_site(membre, attendu, ou):
    """`probe_313` compare le MIRROR au BUILD ; il redevient vert apres regeneration d'un mirror
    renumerote, alors que la valeur LUE AU DECOMPILE, elle, n'a pas bouge. Cet etage fige donc
    l'ordinal que le natif ECRIT, tel qu'il a ete lu a la conversion."""
    assert membre == attendu, "ordinal glisse (%s) -- relire le decompile, pas le mirror" % ou


# ================================================================================================
# 3. BASCULE
# ================================================================================================

@pytest.mark.parametrize("aid,libelle,fabrique,refus", CAS)
def test_bascule_chaque_regle_discrimine(aid, libelle, fabrique, refus):
    st_refuse, st_passe = fabrique()
    ab = P._porteur(aid)
    r1 = int(ab.get_dynamic_invalid_target_reason(st_refuse, CASTER, CIBLE) or 0)
    r2 = int(ab.get_dynamic_invalid_target_reason(st_passe, CASTER, CIBLE) or 0)
    assert (r1, r2) == (refus, 0), (
        "%d (%s) ne DISCRIMINE pas : refus=%s passe=%s (attendu %s / 0x0) -- une regle qui rend "
        "toujours la meme chose est indistinguable d'une regle ABSENTE"
        % (aid, libelle, hex(r1), hex(r2), hex(refus)))


# ================================================================================================
# 4. MUTANTS
# ================================================================================================

@pytest.mark.parametrize("aid,libelle,fabrique,refus", CAS)
def test_mutant_desarmer_change_le_verdict(aid, libelle, fabrique, refus):
    st_refuse, _ = fabrique()
    avant = int(P._porteur(aid).get_dynamic_invalid_target_reason(st_refuse, CASTER, CIBLE) or 0)
    with P.desarme(aid):
        apres = int(P._porteur(aid).get_dynamic_invalid_target_reason(
            st_refuse, CASTER, CIBLE) or 0)
    assert avant == refus and apres == 0, (
        "%d (%s) : la mutation ne retire RIEN (avant=%s apres=%s) -- ce bras ne garde rien. Le "
        "critere est le DELTA, pas `apres == 0` : sur un arbre sans regle portee, ce dernier rend "
        "un VERT sur l'inertie." % (aid, libelle, hex(avant), hex(apres)))


# ================================================================================================
# 5. LE CHAINON COMPLET -- la cascade, pas la regle isolee
# ================================================================================================

def test_chainon_complet_forward_observers():
    """`is_invalid_target` ENTIER : masque statique + cascade + regle dynamique. Seul etage qui
    prouve que la regle est ATTEINTE par le code que le moteur execute reellement."""
    refuse, passe = _cas_forward_observers()
    ab = P._porteur(FO)
    r1 = int(is_invalid_target(refuse, CASTER, CIBLE, ab) or 0)
    r2 = int(is_invalid_target(passe, CASTER, CIBLE, ab) or 0)
    assert r1 & int(TR.TargetMatchesDynamicRule), (
        "cible PORTANT Markerlight acceptee par la cascade (%s) -- la regle n'est pas ATTEINTE"
        % hex(r1))
    assert not (r2 & int(TR.TargetMatchesDynamicRule)), (
        "cible SANS Markerlight refusee par le bit dynamique (%s) -- sur-refus" % hex(r2))


def test_chainon_complet_blood_chalice():
    refuse, passe = _cas_blood_chalice()
    ab = P._porteur(BCH)
    r1 = int(is_invalid_target(refuse, CASTER, CIBLE, ab) or 0)
    r2 = int(is_invalid_target(passe, CASTER, CIBLE, ab) or 0)
    assert r1 & int(TR.TargetMatchesDynamicRule), (
        "allie MECANIQUE adjacent accepte par la cascade (%s)" % hex(r1))
    assert r2 == 0, (
        "allie non-mecanique adjacent refuse par la cascade (%s) -- sur-refus" % hex(r2))


def test_le_repli_nomme_existe_des_deux_cotes():
    """Le fichier doit rougir sur la MECANIQUE, jamais sur un `ImportError` : `DYN` est lu par
    `getattr` avec un repli NOMME (dict vide = l'etat d'avant la tranche)."""
    assert isinstance(DYN, dict)
