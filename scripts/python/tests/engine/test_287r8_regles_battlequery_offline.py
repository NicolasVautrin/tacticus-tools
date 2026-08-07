"""#287-r8 -- la garde OFFLINE des trois regles dynamiques portees par la tranche.

Le probe live (`probe_287r8_regles_battlequery_live.py`) confronte au natif ; ce fichier GARDE ce
que la confrontation a etabli, et tient les bras que le live n'exerce pas.

SIX ETAGES, et chacun existe parce qu'un etage plus haut ne pouvait PAS voir sa faute :

 1. RECENSEMENT BI-CANAL -- les trois ids sont EVALUABLES, chacun par SON canal (surcharge de classe
    pour 1025/1112, entree de `DYNAMIC_TARGET_RULE_UNPORTED` pour 1087, qui n'a pas de classe).
    Une regle rangee dans le mauvais canal serait ignoree par la cascade, sans erreur.
 2. BASCULE -- chaque regle DISCRIMINE, sur chacun de ses termes. `1025` en a TROIS (`0x10` /
    `0x20` / le court-circuit d'adjacence) : une bascule a deux bras ne verrait pas qu'un port a
    confondu ses deux codes de refus.
 3. MUTANTS, en DELTA (`avant == refus` ET `apres == 0`). Le seul `apres == 0` serait vert sur un
    port qui n'evalue rien -- mesure dans cette lignee, il rendait 5/5 sur un arbre sans regle.
 4. LE TERME `Remove(caster)` DE 1087 -- trouve par le SOUS-REFUS live, pas par la lecture.
    `IsEnemy(caster, caster)` etant faux, le `RemoveAll` ne retire pas le caster : sans ce retrait,
    une tuile dont le SEUL voisin est le caster passait. Aucune bascule ami/ennemi ne l'exhibe.
 5. LE CRAN SOUS L'ETAGE -- `SynapseEffect` comme `IAuraEffect`. Sans lui, `GetInRangeAuraAmount`
    rend `0` par cast echoue et `1112` refuse TOUTE cible : un SUR-refus systematique. On garde
    AUSSI que l'ajout n'a pas APLATI la portee tabulee de `ContagionsOfNurgle`.
 6. LE CHAINON COMPLET -- `is_invalid_target`, seul etage qui prouve que la regle arrive jusqu'a
    l'observable : une regle juste mais jamais consultee par la cascade serait verte partout ailleurs.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PY = HERE.parents[2]
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

import probe_287r8_regles_battlequery as R                                 # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.effects.aura import (aura_current_range, aura_max_range,  # noqa: E402
                                          aura_trait, is_aura_effect)
from engine.entities.traits.unit_trait import UnitTrait                    # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,  # noqa: E402
                                               is_invalid_target)
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402

SKY = int(ActiveAbilityType.SkyStrike)                    # 1025
KAUYON = int(ActiveAbilityType.ExemplarOfTheKauyon)       # 1087
ALPHA = int(ActiveAbilityType.AlphaWarrior)               # 1112
TRIO = (SKY, KAUYON, ALPHA)


# ================================================================================================
# 1. RECENSEMENT BI-CANAL
# ================================================================================================

def test_les_trois_ids_sont_evaluables_par_leur_canal():
    """Le canal N'EST PAS interchangeable : la cascade lit la SURCHARGE quand la classe existe, et
    l'entree de table sinon. Une regle du mauvais cote serait silencieusement ignoree."""
    assert R.evaluabilite(SKY) == "surcharge", "1025 a une classe : sa regle doit y etre surchargee"
    assert R.evaluabilite(ALPHA) == "surcharge", "1112 a une classe portee"
    # 1087 a CHANGE DE CANAL au port de sa face COMBAT (#488) : sa classe
    # `ExemplarOfTheKauyonAbility` surcharge desormais `get_dynamic_invalid_target_reason` (qui
    # appelle le MEME corps, `targeting.py::_dynamic_rule_exemplar_of_the_kauyon`), et son entree
    # de `DYNAMIC_TARGET_RULE_UNPORTED` a ete retiree dans le meme commit. Ce que le test garde
    # est INCHANGE -- « le canal doit suivre l'existence d'une classe » -- seule la reponse a bouge.
    assert R.evaluabilite(KAUYON) == "surcharge", (
        "1087 a une classe portee (#488) -> canal surcharge")
    # Les DEUX tables `*_UNPORTED` sont DISJOINTES d'`ABILITY_CLASSES` : une entree qui resterait en
    # table pendant que la classe existe donnerait DEUX sources pour une meme regle, et la cascade
    # n'en lirait qu'une (la surcharge) -- l'autre deviendrait un mort silencieux.
    assert KAUYON not in DYNAMIC_TARGET_RULE_UNPORTED
    assert SKY in ABILITY_CLASSES and ALPHA in ABILITY_CLASSES and KAUYON in ABILITY_CLASSES


def test_les_trois_ids_posent_le_bit_au_masque():
    """Le RECENSEMENT se fait sur le BIT POSE AU MASQUE, jamais sur le code rendu : `1025` rend
    `CasterHasNotMoved`/`TargetHasFreeAdjacentTile`, deux bits que son masque ne porte MEME PAS."""
    from engine.runner.abilities.targeting import targeting_options_for
    for aid in TRIO:
        opts = targeting_options_for(aid)
        assert opts is not None and opts.has(TR.TargetMatchesDynamicRule), (
            "%d ne pose plus TargetMatchesDynamicRule : la cascade n'appellerait plus sa regle" % aid)


# ================================================================================================
# 2. BASCULE
# ================================================================================================

def test_chaque_bascule_discrimine():
    basc = R.mesurer_bascule()
    assert len(basc) >= 5, "moins de bras qu'a la mesure : un terme n'est plus couvert"
    for aid, libelle, refus, obtenu_refus, obtenu_accepte in basc:
        assert obtenu_refus == refus, "%d %s : refus attendu %s, obtenu %s" % (
            aid, libelle, hex(refus), hex(obtenu_refus))
        assert obtenu_accepte == 0, "%d %s : le bras qui PASSE rend %s" % (
            aid, libelle, hex(obtenu_accepte))


def test_1025_rend_DEUX_codes_de_refus_distincts():
    """`CasterHasNotMoved` (a bouge + non adjacent) et `TargetHasFreeAdjacentTile` (n'a pas bouge,
    mais la cible n'offre aucune tuile d'atterrissage). Les confondre passerait la bascule."""
    obtenu, attendu, nb_voisins = R.mesurer_tuile_sans_voisin()
    assert nb_voisins > 0, "substrat degenere : la cible n'a aucun voisin marchable a ceinturer"
    assert obtenu == attendu == int(TR.TargetHasFreeAdjacentTile)
    st_moved, _libre, _adj = R._cas_sky_strike()
    assert R._regle(SKY, st_moved) == int(TR.CasterHasNotMoved)


# ================================================================================================
# 3. MUTANTS, en DELTA
# ================================================================================================

def test_mutants_en_delta():
    mut = R.mesurer_mutants()
    assert len(mut) == 3
    for aid, lib, morde, avant, apres in mut:
        assert morde, ("%s : mutation INERTE (avant=%s apres=%s) -- le port ne consulte pas la "
                       "regle, ou le substrat ne l'exerce pas" % (lib, hex(avant), hex(apres)))


# ================================================================================================
# 4. LE TERME `Remove(caster)` DE 1087
# ================================================================================================

def test_1087_retire_le_caster_de_ses_voisins():
    """`units.Remove(caster)` (slot 6 d'`ICollection<T>`) AVANT `RemoveAll(IsEnemy)`. Le second ne
    retire PAS le caster (`IsEnemy(caster, caster)` est faux) : c'est un terme a part entiere, et
    c'est la MESURE LIVE (un sous-refus) qui l'a impose, la premiere lecture du decompile ayant
    laisse l'appel sous son nom Ghidra anonyme."""
    st_enn, st_all, tuile, st_seul = R._cas_exemplar()
    assert R._regle(KAUYON, st_seul, R.CASTER, tuile) == int(TR.TargetMatchesDynamicRule), (
        "une tuile dont le SEUL voisin est le caster doit etre REFUSEE")
    assert R._regle(KAUYON, st_all, R.CASTER, tuile) == 0, (
        "un allie TIERS adjacent doit la faire passer")
    assert R._regle(KAUYON, st_enn, R.CASTER, tuile) == int(TR.TargetMatchesDynamicRule)


# ================================================================================================
# 5. LE CRAN SOUS L'ETAGE
# ================================================================================================

def test_synapse_est_un_aura_effect():
    syn = int(EffectType.Synapse_Effect)
    assert is_aura_effect(syn), (
        "sans cette entree le cast `as IAuraEffect` echoue, GetInRangeAuraAmount rend 0, et 1112 "
        "refuse TOUTE cible -- un SUR-refus systematique")
    assert aura_trait(syn) == int(UnitTrait.Synapse), "`SynapseEffect$$GetTrait` -> 0x7e8"
    assert aura_max_range(syn) == 2, "`$$GetMaxRange` -> Direct(2)"
    # Les TROIS slots de portee partagent UN corps (vtable) : la portee ne depend pas du tour.
    assert {aura_current_range(syn, n) for n in (0, 1, 2, 3, 5, 9)} == {2}


def test_l_ajout_n_a_pas_aplati_la_portee_tabulee_de_contagions():
    """Contre-epreuve du precedent : `ContagionsOfNurgle` a, lui, une portee QUI DEPEND du tour
    (`GetRangeOnOwnerTurn` : <=2 -> 1, <=4 -> 2, sinon 3). Un registre qui aurait rendu la portee
    constante pour tout le monde passerait le test ci-dessus et casserait celui-ci."""
    con = int(EffectType.ContagionsOfNurgle_ArmorReduction1)
    assert [aura_current_range(con, n) for n in (0, 2, 3, 4, 5)] == [1, 1, 2, 2, 3]
    assert aura_current_range(int(EffectType.Markerlight), 3) is None, (
        "un EffectType qui n'est PAS une aura doit rendre None (cast echoue), jamais une portee")


# ================================================================================================
# 6. LE CHAINON COMPLET -- la regle arrive-t-elle jusqu'a l'observable ?
# ================================================================================================

def test_chainon_complet_is_invalid_target():
    """`is_invalid_target` = la cascade ENTIERE (masque + volet caster + regle dynamique). Une regle
    juste mais jamais consultee serait verte a tous les etages ci-dessus."""
    st_enn, st_all, tuile, _seul = R._cas_exemplar()
    ab = R._porteur(KAUYON)
    refus = int(is_invalid_target(st_enn, R.CASTER, tuile, ab) or 0)
    passe = int(is_invalid_target(st_all, R.CASTER, tuile, ab) or 0)
    assert refus & int(TR.TargetMatchesDynamicRule), (
        "la cascade ne remonte pas le refus dynamique de 1087 (obtenu %s)" % hex(refus))
    assert not (passe & int(TR.TargetMatchesDynamicRule)), (
        "la cascade refuse dynamiquement une tuile que la regle accepte (obtenu %s)" % hex(passe))

