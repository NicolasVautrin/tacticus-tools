"""#287-r4-r1 -- GARDE des REGLES DYNAMIQUES DE CIBLE portees. OFFLINE (aucun runner, aucun RPC).

POURQUOI OFFLINE. Le defaut garde ici est STRUCTUREL : une regle dynamique portee peut disparaitre
(refactor d'une classe, entree retiree de `DYNAMIC_TARGET_RULE_UNPORTED`) sans qu'aucun test live ne
rougisse -- la degradation est PERMISSIVE (`0` = « pas de refus »), donc ni erreur ni crash, juste
des casts que le natif REFUSE et que le port accepte. C'est exactement la signature du rouge qui a
ouvert cette tranche.

CINQ ETAGES, et chacun voit une faute que le precedent declare verte :

  1. RECENSEMENT non vide, et NON DEGENERE : les deux canaux de portage (surcharge dans la classe /
     entree de table) doivent tous deux etre peuples. Un etage qui ne visiterait qu'un canal
     laisserait l'autre disparaitre en silence.
  2. ORDINAUX FIGES au site. Les trois grandeurs LUES au decompile (`UnitTrait.Hero` = 0x10,
     `UnitTrait.Chaos` = 0x7ea, `EffectType.SquigMine_Tile` = 0x5a1) sont gardees a la valeur
     MESUREE. `probe_313` compare le mirror au build et redeviendrait VERT apres un renumerotage
     ayant deja fausse le site ; c'est le cran manquant, cf. CLAUDE.md.
  3. BASCULE : chaque regle DISCRIMINE (un substrat refuse, un substrat passe). Une regle rendant
     toujours `0` serait indistinguable d'une regle absente ; une regle rendant toujours `2`
     refuserait tout.
  4. MUTANTS : desarmer la regle fait TOMBER la bascule. Sans cet etage, l'etage 3 serait vert sur
     un port qui ne consulte plus rien. ⚠ `a_morde` est ASSERTIONNE ET publie separement : une
     mutation que les donnees n'exercent pas se DECLARE.
  5. LE CHAINON COMPLET : `turnflow._has_valid_targets` -- le predicat
     d'`IdunBattle.Core.Services.AttackQuery$$HasValidTargets`, donc du flag
     `UnitFlag.NoActionAvailable`. C'est le seul etage qui prouve que la regle ARRIVE jusqu'a
     l'observable ; les etages 3-4 testent la regle isolee et resteraient verts si la cascade
     cessait de l'appeler (le defaut que #287-r4 a corrige).

La MESURE (recensement chiffre, residu, symboles natifs) vit dans
`probe_287r4r1_dynamic_target_rules.py`, que ce fichier importe : le probe MESURE, le test GARDE.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[2]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import probe_287r4r1_dynamic_target_rules as P                      # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType    # noqa: E402
from engine.entities.effect_type import EffectType                   # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait              # noqa: E402
from engine.runner.abilities.targeting import UnportedAbilityTargeting   # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402

# Meme repli NOMME que dans le probe (cf. sa docstring d'import) : ce fichier doit etre JOUABLE des
# DEUX cotes du correctif, sinon son rouge serait un `ImportError` -- un rouge de structure, qui ne
# dit rien de la mecanique gardee.
DYNAMIC_TARGET_RULE_UNPORTED = P.DYNAMIC_TARGET_RULE_UNPORTED


# ------------------------------------------------------------------ 1. RECENSEMENT

def test_recensement_est_non_vide_et_les_deux_canaux_sont_peuples():
    """Le probe visite quelque chose, et les DEUX canaux de portage sont vivants.

    Assertionner son propre NON-VIDE est ce qui separe « aucune faute » de « rien n'a ete visite » --
    un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas."""
    ids = P.ids_portant_le_bit()
    assert len(ids) > 0, "recensement VIDE : le probe ne visite rien, son vert ne prouve rien"
    etats = {a: P.evaluabilite(a) for a in ids}
    surcharges = [a for a, e in etats.items() if e == "surcharge"]
    tables = [a for a, e in etats.items() if e == "table"]
    assert surcharges, "aucune regle portee en SURCHARGE de classe -- ce canal a disparu"
    assert tables, "aucune regle portee en TABLE -- la voie non portee a perdu ses regles"
    # Les cinq bras de mesure portent sur des ids REELLEMENT evaluables : sans cela, la bascule
    # mesurerait le defaut permissif et serait verte pour la mauvaise raison.
    for aid, libelle, _f in P.CAS:
        assert etats.get(aid) in ("surcharge", "table"), (
            "le bras '%s' porte sur l'id %d, dont la regle n'est PAS evaluable (%s)"
            % (libelle, aid, etats.get(aid)))


def test_la_table_des_non_portees_ne_contient_que_des_ids_qui_posent_le_bit():
    """Une entree de `DYNAMIC_TARGET_RULE_UNPORTED` pour un id qui NE POSE PAS
    `TargetMatchesDynamicRule` ne serait jamais consultee (la cascade teste le masque avant
    d'appeler) : du code mort deguise en port. On l'interdit."""
    poseurs = set(P.ids_portant_le_bit())
    orphelines = sorted(set(DYNAMIC_TARGET_RULE_UNPORTED) - poseurs)
    assert orphelines == [], (
        "regles dynamiques inatteignables (masque sans TargetMatchesDynamicRule) : %s" % orphelines)


# ------------------------------------------------------------------ 2. ORDINAUX FIGES

def test_les_grandeurs_lues_au_decompile_gardent_leur_ordinal_mesure():
    """Les littéraux que les corps natifs comparent, figes a la valeur LUE dans le decompile du
    build `rnca9r7q6c` :

        AdaptiveStrategyAbility$$GetDynamicInvalidTargetReason  -> HasTrait(target, 0x10)
        FoulInfusionAbility$$GetDynamicInvalidTargetReason      -> HasTrait(target, 0x7ea)
        SquigMineAbility$$GetDynamicInvalidTargetReason         -> HasEffect(target, .., 0x5a1, 0)
        SporeMineLauncherAbility$$..., SquigMineAbility$$...    -> HasSteppableUnit -> trait 0x1b

    Un renumerotage du build ferait glisser ces valeurs ; `probe_313` (mirror vs build) redeviendrait
    VERT des la regeneration du mirror, alors que la regle porterait desormais un AUTRE trait. Ce
    test-ci est le cran qui l'attrape."""
    assert int(UnitTrait.Hero) == 0x10
    assert int(UnitTrait.Chaos) == 0x7ea
    assert int(UnitTrait.Steppable) == 0x1b
    assert int(EffectType.SquigMine_Tile) == 0x5a1
    assert int(TR.TargetMatchesDynamicRule) == 2


def test_les_deux_traits_ne_se_confondent_pas():
    """CONTRE-CONTROLE, et il a sa raison d'etre : `Hero` et `Chaos` sont lus par DEUX regles de
    sens INVERSE (l'une refuse sur presence, l'autre sur absence). Les confondre inverserait les
    deux verdicts a la fois -- et l'etage 3, qui ne regarde que la bascule, resterait vert si les
    deux substrats etaient construits avec le meme trait."""
    assert int(UnitTrait.Hero) != int(UnitTrait.Chaos)
    assert UnitTrait.Hero.name != UnitTrait.Chaos.name


# ------------------------------------------------------------------ 3. BASCULE

@pytest.mark.parametrize("aid,libelle,fabrique", P.CAS,
                         ids=[("%d-%s" % (a, l.replace(" ", "_"))) for a, l, _ in P.CAS])
def test_chaque_regle_portee_discrimine(aid, libelle, fabrique):
    """Deux substrats qui ne different QUE par la grandeur lue par le corps natif : l'un doit rendre
    `TargetMatchesDynamicRule`, l'autre `0`. La valeur de refus est verifiee EXACTEMENT (et pas
    « non nulle ») : le natif rend `2`, pas un code de refus quelconque."""
    st_refuse, st_passe = fabrique()
    ab = P._porteur(aid)
    r_refuse = int(ab.get_dynamic_invalid_target_reason(st_refuse, P.CASTER, P.CIBLE) or 0)
    r_passe = int(ab.get_dynamic_invalid_target_reason(st_passe, P.CASTER, P.CIBLE) or 0)
    assert r_refuse == int(TR.TargetMatchesDynamicRule), (
        "%d (%s) : le substrat REFUSANT rend %d" % (aid, libelle, r_refuse))
    assert r_passe == 0, "%d (%s) : le substrat ACCEPTANT rend %d" % (aid, libelle, r_passe)


def test_une_cible_non_resolue_ne_fabrique_aucun_refus():
    """`target_id = None` / entite inconnue : le natif appelle `HasTrait(null)` (-> `false`) ou sort
    en tete (`if (target == null) return 0`). Le port ne doit inventer aucun refus -- c'est la
    convention permissive du module, et c'est ce qui evite qu'une regle portee rende un id
    INCASTABLE des que la cascade lui passe une cible qu'elle n'a pas resolue."""
    st = P.substrat([(P.CASTER, "necroWarden", 1, 0, 0, [UnitTrait.Hero])])
    for aid in sorted({a for a, _l, _f in P.CAS}):
        ab = P._porteur(aid)
        assert int(ab.get_dynamic_invalid_target_reason(st, P.CASTER, None) or 0) == 0
        assert int(ab.get_dynamic_invalid_target_reason(st, P.CASTER, 99999) or 0) == 0


def test_un_id_sans_regle_portee_reste_permissif_et_ne_leve_pas():
    """La DETTE, gardee explicitement : pour un id qui pose le bit mais dont le corps n'est pas
    porte, le porteur rend `0` -- sans lever. Le natif, lui, LEVE sur un delegue nul ; le port ne
    peut pas evaluer un corps qu'il n'a pas, et cette asymetrie est NOMMEE (residu #287-r5), pas
    silencieuse. Ce test interdit qu'on la « corrige » en refusant tout, ce qui rendrait
    incastables 46 abilities d'un coup."""
    ids = P.ids_portant_le_bit()
    sans = [a for a in ids if P.evaluabilite(a) == "aucune"]
    assert sans, "plus aucun id sans regle portee : ce test a perdu son objet (mettre a jour #287-r5)"
    st = P.substrat([(P.CASTER, "necroWarden", 1, 0, 0, [UnitTrait.Hero]),
                     (P.CIBLE, "necroImmortal", 1, 1, 0, [UnitTrait.Hero])])
    for aid in sans[:12]:
        assert int(P._porteur(aid).get_dynamic_invalid_target_reason(
            st, P.CASTER, P.CIBLE) or 0) == 0


# ------------------------------------------------------------------ 4. MUTANTS

def test_desarmer_chaque_regle_fait_tomber_sa_bascule():
    """LE MUTANT, un par bras. On retire la regle (la classe retrouve le defaut herite, la table
    perd son entree) et l'on exige que le substrat REFUSANT cesse de refuser.

    ⚠ `a_morde` est assertionne bras par bras ET publie en bloc, et son critere est le DELTA
    (`avant == 2` ET `apres == 0`), pas « apres vaut 0 ». Mesure du 2026-08-06 sur l'arbre d'avant la
    tranche : le critere `apres == 0` rendait **5/5** alors qu'aucune regle n'y etait portee -- la
    mutation n'y retirait rien et son inertie se comptait comme un vert. Un bras dont la mutation ne
    change rien ne garde RIEN, et doit le DIRE."""
    mutants = P.mesurer_mutants()
    assert len(mutants) == len(P.CAS)
    inertes = [(a, l, av, ap) for a, l, morde, av, ap in mutants if not morde]
    assert inertes == [], (
        "a_morde %d/%d -- bras dont la mutation ne retire RIEN (ils ne gardent rien) : %s"
        % (len(mutants) - len(inertes), len(mutants), inertes))


def test_le_desarmement_est_bien_REVERSIBLE():
    """Contre-epreuve du mutant lui-meme : apres restauration, la bascule REVIENT. Sans elle, un
    `desarme` qui laisserait l'arbre mute ferait passer les tests suivants dans un etat degrade --
    et l'ordre d'execution de pytest deciderait du verdict."""
    aid, _libelle, fabrique = P.CAS[0]
    st_refuse, _ = fabrique()
    avant = int(P._porteur(aid).get_dynamic_invalid_target_reason(st_refuse, P.CASTER, P.CIBLE) or 0)
    with P.desarme(aid):
        pendant = int(P._porteur(aid).get_dynamic_invalid_target_reason(
            st_refuse, P.CASTER, P.CIBLE) or 0)
    apres = int(P._porteur(aid).get_dynamic_invalid_target_reason(st_refuse, P.CASTER, P.CIBLE) or 0)
    assert (avant, pendant, apres) == (int(TR.TargetMatchesDynamicRule), 0,
                                       int(TR.TargetMatchesDynamicRule))


# ------------------------------------------------------------------ 5. LE CHAINON COMPLET

def test_has_valid_targets_bascule_avec_la_regle_dynamique():
    """LE ROUGE de #287-r4-r1, reproduit : `C1_02`/seed 28704, `necroWarden`, `AdaptiveStrategy`
    (1005). Natif : `targetReason = TargetMatchesDynamicRule`, `UnitFlag.NoActionAvailable` POSE.
    Port avant cette tranche : `0`, flag absent (`live=[0,1,4]` vs `port=[0,1]`).

    Les deux bras sont a UN TRAIT d'ecart, et traversent la cascade ENTIERE (volet caster compris --
    le substrat porte un board et des positions adjacentes, donc rien ne court-circuite en amont)."""
    tem = P.temoin_has_valid_targets()
    assert tem["tous_heros"] is False, (
        "tous les allies sont HEROS et le port trouve encore une cible : la regle dynamique "
        "n'arrive pas jusqu'a `_has_valid_targets` (c'est le rouge de #287-r4-r1)")
    assert tem["un_non_heros"] is True, (
        "un allie NON-HEROS existe et le port ne trouve AUCUNE cible : la regle refuse trop")


def test_has_valid_targets_redevient_permissif_quand_on_desarme_la_regle():
    """Le mutant du chainon, et il vise l'etage que les autres ne voient pas : desarmee, la regle
    laisse `_has_valid_targets` rendre `True` sur le substrat « tous heros » -- c'est-a-dire
    exactement le comportement d'avant la tranche. Cette assertion est ce qui prouve que le `False`
    du test precedent vient de LA REGLE, et non d'un autre etage du masque (portee, camp, adjacence)
    qui refuserait de toute facon."""
    import engine.runner.operations.turnflow as TF
    aid = int(ActiveAbilityType.AdaptiveStrategy)
    refuse, _passe = P._cas_adaptive_strategy()
    with P.desarme(aid):
        assert TF._has_valid_targets(refuse, P.CASTER, aid) is True, (
            "regle desarmee et le port ne trouve TOUJOURS pas de cible : le `False` mesure par le "
            "test precedent ne vient pas de la regle dynamique -- le bras ne garde pas ce qu'il croit")


def test_le_porteur_non_porte_consulte_bien_la_table():
    """Le cablage, teste pour lui-meme : `UnportedAbilityTargeting` doit LIRE
    `DYNAMIC_TARGET_RULE_UNPORTED` par son `ABILITY_TYPE`. Un porteur construit pour un AUTRE id ne
    doit pas heriter de la regle du voisin -- faute classique d'une table consultee par defaut."""
    from engine.runner.abilities.targeting import targeting_options_for
    st_refuse, _ = P._cas_adaptive_strategy()
    aid = int(ActiveAbilityType.AdaptiveStrategy)
    autre = int(ActiveAbilityType.PsychicMaelstrom)          # pose le bit, AUCUNE regle portee
    bon = UnportedAbilityTargeting(aid, targeting_options_for(aid))
    faux = UnportedAbilityTargeting(autre, targeting_options_for(autre))
    assert int(bon.get_dynamic_invalid_target_reason(st_refuse, P.CASTER, P.CIBLE) or 0) == int(
        TR.TargetMatchesDynamicRule)
    assert int(faux.get_dynamic_invalid_target_reason(st_refuse, P.CASTER, P.CIBLE) or 0) == 0
