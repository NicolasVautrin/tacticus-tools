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

def test_recensement_est_non_vide_et_la_partition_est_SAINE():
    """Le probe visite quelque chose, et les canaux de portage sont DISJOINTS.

    Assertionner son propre NON-VIDE est ce qui separe « aucune faute » de « rien n'a ete visite » --
    un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas.

    ⚠ CE TEST EXIGEAIT `assert tables` -- « la voie non portee a perdu ses regles » (#1015). C'etait
    un SEUIL deguise en invariant : le canal `table` se vide par le travail accompli (chaque
    behaviour portee fait migrer sa regle en surcharge), et #996 en a sorti le dernier occupant
    (`1185 ForwardObservers`). `master` en est reste rouge, ici comme dans
    `test_287r5r1_charge_tiles_offline`. Ce qui se garde n'est pas le PEUPLEMENT d'un canal mais la
    SANTE de la partition ; que le cablage de la table reste arme est garde separement, a table vide
    (`test_le_cablage_de_la_table_est_ARME` plus bas)."""
    ids = P.ids_portant_le_bit()
    assert len(ids) > 0, "recensement VIDE : le probe ne visite rien, son vert ne prouve rien"
    etats = {a: P.evaluabilite(a) for a in ids}
    inconnus = sorted(set(etats.values()) - set(P.ETATS))
    assert inconnus == [], "etats hors partition : %r" % inconnus
    assert [a for a, e in etats.items() if e == "surcharge"], (
        "aucune regle portee en SURCHARGE de classe -- ce canal a disparu")
    # Les DEUX etats de DEFAUT de la partition : un id ne peut pas etre declare dans les deux canaux.
    for defaut, explication in (
            ("ambigu", "l'entree de table y est INATTEIGNABLE (le porteur est la classe) : second "
                       "mirror du meme corps natif, que rien ne consulte"),
            ("perdue", "la classe portee capture le porteur SANS surcharger, alors qu'une entree de "
                       "table existe : le mirror n'est jamais appele, l'id est PERMISSIF")):
        coupables = sorted(a for a, e in etats.items() if e == defaut)
        assert coupables == [], "ids en etat %s : %r -- %s" % (defaut, coupables, explication)
    # Les bras de mesure portent sur des ids REELLEMENT evaluables : sans cela, la bascule
    # mesurerait le defaut permissif et serait verte pour la mauvaise raison.
    for aid, libelle, _f in P.CAS:
        assert etats.get(aid) in P.ETATS_EVALUABLES, (
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
    doit pas heriter de la regle du voisin -- faute classique d'une table consultee par defaut.

    ⚠ L'ID TESTE EST **DERIVE DE LA TABLE**, JAMAIS ECRIT EN DUR, ET C'EST LA LECON DU ROUGE.
    Ce test citait `1005 AdaptiveStrategy` (ecrit le 2026-08-06) ; #577 (`4c5e4c88`, 2026-08-08) a
    RETIRE son entree parce que `necrons.AdaptiveStrategyAbility` SURCHARGE desormais la methode --
    donc `UnportedAbilityTargeting(1005)` rend `0`, ce qui est la BONNE reponse du port. Le test
    accusait un regime qui n'existait plus. Un id ecrit en dur peut migrer d'un canal a l'autre ;
    la QUESTION (« le porteur non porte consulte-t-il la table ? »), elle, ne migre pas."""
    from engine.runner.abilities.targeting import targeting_options_for
    en_table = sorted(set(DYNAMIC_TARGET_RULE_UNPORTED))
    if not en_table:
        pytest.skip(
            "`DYNAMIC_TARGET_RULE_UNPORTED` est VIDE -- toutes les regles ont migre en surcharge "
            "(#1015). Ce test-ci mesure la table PEUPLEE ; le cablage lui-meme reste garde a table "
            "vide par `test_le_cablage_de_la_table_est_ARME`, qui n'a PAS de condition de montage.")
    bras = {aid: fab for aid, _l, fab in P.CAS}
    testables = [a for a in en_table if a in bras]
    assert testables, (
        "aucun bras de `P.CAS` ne porte un id de la table (%r) : les etages BASCULE et MUTANTS ne "
        "mesurent plus que le canal SURCHARGE, et la table pourrait se vider sans rougir." % en_table)
    autre = int(ActiveAbilityType.PsychicMaelstrom)          # pose le bit, AUCUNE regle portee
    assert P.evaluabilite(autre) == "aucune", (
        "%d n'est plus un id SANS regle portee : le bras negatif de ce test ne discrimine plus rien "
        "(il faut lui choisir un autre voisin)." % autre)
    for aid in testables:
        st_refuse, st_passe = bras[aid]()
        bon = UnportedAbilityTargeting(aid, targeting_options_for(aid))
        faux = UnportedAbilityTargeting(autre, targeting_options_for(autre))
        assert int(bon.get_dynamic_invalid_target_reason(st_refuse, P.CASTER, P.CIBLE) or 0) == int(
            TR.TargetMatchesDynamicRule), (
            "%d est dans la table et le porteur non porte ne la consulte pas" % aid)
        assert int(bon.get_dynamic_invalid_target_reason(st_passe, P.CASTER, P.CIBLE) or 0) == 0, (
            "%d : le porteur refuse le substrat ACCEPTANT -- la regle lue ne discrimine pas" % aid)
        assert int(faux.get_dynamic_invalid_target_reason(st_refuse, P.CASTER, P.CIBLE) or 0) == 0, (
            "un porteur construit pour %d herite de la regle de %d" % (autre, aid))


def test_le_cablage_de_la_table_est_ARME():
    """L'INVARIANT QUI SURVIT AU VIDAGE DE LA TABLE (#1015), et la raison d'etre de ce test.

    Les gardes de ce fichier et de `test_287r5r1` exigeaient que `DYNAMIC_TARGET_RULE_UNPORTED` soit
    PEUPLEE. C'est un critere qui expire par le travail accompli : chaque behaviour portee fait
    migrer sa regle vers la surcharge de sa classe, et #996 (`b061a916`) en a sorti le dernier
    occupant, `1185 ForwardObservers` -- laissant `master` rouge sur deux fichiers.

    Or ce qui compte n'a jamais ete le PEUPLEMENT : c'est que la plomberie MORDE le jour ou un corps
    du residu #287-r5 sera mirrore sans que sa classe le soit. On l'exerce donc a table vide, avec
    une entree TEMOIN, sur un id que la voie non portee sert REELLEMENT. Trois faits mesures :

      1. la regle temoin est APPELEE (elle enregistre ce qu'elle recoit) et son refus est RENDU ;
      2. un porteur construit pour un AUTRE id n'en herite pas (pas de consultation par defaut) ;
      3. l'entree DISPARAIT a la sortie du contexte, et le porteur redevient permissif -- sans quoi
         ce test laisserait derriere lui une regle fantome que les suivants prendraient pour vraie.

    L'id est DERIVE (`P.ids_sans_regle_portee()`), jamais ecrit en dur : la lecon du rouge de
    #883-r1, ou un id cite en dur avait migre de canal et le test accusait un regime disparu. Il ne
    sert qu'a INDEXER -- le porteur est construit explicitement, et c'est lui le sujet.

    ⚠ ET LE TEST PUBLIE L'ETAT DE LA POPULATION AU LIEU DE LE SUPPOSER. Mesure du 2026-08-13 : AUCUN
    des 80 ids posant le bit n'est servi par `UnportedAbilityTargeting` en production (tous ont une
    classe portee avec masque). Le canal est donc doublement vide -- sans entree ET sans lecteur.
    C'est un fait, pas un defaut ; il est assertionne ici pour qu'un futur repeuplement soit VU (la
    garde change de bras et exige alors que le lecteur reel soit exerce), plutot que de rester une
    hypothese tacite dans une docstring."""
    from engine.runner.abilities.targeting import targeting_options_for
    servis = P.ids_servis_par_la_voie_non_portee()
    if servis:
        # Regime REPEUPLE : le cablage a de vrais lecteurs -> on les exerce EUX, le temoin devient
        # superflu comme sujet et l'invariant se mesure sur la production.
        for aid in servis:
            assert P.evaluabilite(aid) in ("table", "aucune"), (
                "%d est servi par la voie non portee ET declare par une classe : etat %s"
                % (aid, P.evaluabilite(aid)))
    candidats = P.ids_sans_regle_portee()
    assert candidats, (
        "aucun id ne pose le bit sans regle portee : ce test n'a plus de sujet. Ce n'est pas un vert "
        "-- soit le residu #287-r5 est entierement resorbe (et alors la voie non portee est "
        "reellement morte, ce qui se DECIDE, pas se constate), soit le recensement est casse.")
    aid = candidats[0]
    autre = candidats[-1]
    assert autre != aid, (
        "un SEUL id sans regle portee : le bras negatif (« un porteur d'un autre id n'herite pas ») "
        "n'a pas de second sujet et ne discriminerait rien.")

    st_refuse, _st_passe = P._cas_adaptive_strategy()      # substrat quelconque : la regle temoin
    #                                                       ne le lit pas, elle enregistre.
    porteur = UnportedAbilityTargeting(aid, targeting_options_for(aid))
    voisin = UnportedAbilityTargeting(autre, targeting_options_for(autre))

    # AVANT : rien dans la table -> permissif. Sans cette mesure, le `2` d'apres pourrait venir
    # d'ailleurs et le test serait vert pour la mauvaise raison.
    assert int(porteur.get_dynamic_invalid_target_reason(st_refuse, P.CASTER, P.CIBLE) or 0) == 0

    with P.entree_temoin(aid) as temoin:
        rendu = int(porteur.get_dynamic_invalid_target_reason(st_refuse, P.CASTER, P.CIBLE) or 0)
        herite = int(voisin.get_dynamic_invalid_target_reason(st_refuse, P.CASTER, P.CIBLE) or 0)
    assert temoin.vue, (
        "la regle TEMOIN n'a jamais ete APPELEE : `UnportedAbilityTargeting` ne consulte plus "
        "`DYNAMIC_TARGET_RULE_UNPORTED`. La voie non portee est un gate DESARME -- tout futur port "
        "de regle sur cette voie serait un no-op silencieux.")
    assert temoin.vue[0][1:] == (P.CASTER, P.CIBLE), (
        "la regle recoit %r au lieu de (caster, cible) : le cablage passe les mauvais arguments"
        % (temoin.vue[0][1:],))
    assert rendu == int(TR.TargetMatchesDynamicRule), (
        "le refus de la regle temoin n'est pas REMONTE : rendu %r" % rendu)
    assert herite == 0, (
        "un porteur construit pour %d herite de la regle de %d -- la table est consultee par "
        "defaut au lieu de l'etre par `ABILITY_TYPE`" % (autre, aid))

    # APRES : le contexte a bien retire l'entree, et l'etat de la partition est restaure.
    assert aid not in DYNAMIC_TARGET_RULE_UNPORTED
    assert P.evaluabilite(aid) == "aucune"
    assert int(porteur.get_dynamic_invalid_target_reason(st_refuse, P.CASTER, P.CIBLE) or 0) == 0


def test_un_id_MIGRE_en_surcharge_sort_de_la_table_sans_perdre_sa_regle():
    """LE CRAN QUE LE ROUGE A REVELE : quand une regle passe du canal TABLE au canal SURCHARGE, les
    DEUX faces doivent bouger ENSEMBLE. Le porteur non porte cesse de la rendre (l'entree a disparu)
    ET la classe portee la rend. Si l'une des deux manque, l'id devient PERMISSIF en silence.

    `1005 AdaptiveStrategy` est le temoin (#577) : `necrons.AdaptiveStrategyAbility` SURCHARGE
    `get_dynamic_invalid_target_reason` et appelle `_dynamic_rule_adaptive_strategy`, l'UNIQUE mirror
    de `AdaptiveStrategyAbility$$GetDynamicInvalidTargetReason`. Ce test rougirait si l'on retirait
    la surcharge sans remettre l'entree -- exactement la degradation permissive de #287-r4-r1."""
    from engine.runner.abilities.targeting import targeting_options_for
    aid = int(ActiveAbilityType.AdaptiveStrategy)
    st_refuse, _ = P._cas_adaptive_strategy()
    assert aid not in DYNAMIC_TARGET_RULE_UNPORTED, (
        "1005 est REVENU dans la table alors que sa classe surcharge : deux mirrors du meme corps "
        "natif, dont un seul serait consulte.")
    assert P.evaluabilite(aid) == "surcharge"
    orphelin = UnportedAbilityTargeting(aid, targeting_options_for(aid))
    assert int(orphelin.get_dynamic_invalid_target_reason(
        st_refuse, P.CASTER, P.CIBLE) or 0) == 0, (
        "le porteur NON PORTE rend encore une regle pour 1005 : l'entree de table n'a pas ete "
        "retiree a la migration.")
    assert int(P._porteur(aid).get_dynamic_invalid_target_reason(
        st_refuse, P.CASTER, P.CIBLE) or 0) == int(TR.TargetMatchesDynamicRule), (
        "la CLASSE portee ne rend plus la regle de 1005, et la table ne l'a plus : l'id est devenu "
        "PERMISSIF -- le natif, lui, refuse (`HasTrait(target, Hero)`).")
