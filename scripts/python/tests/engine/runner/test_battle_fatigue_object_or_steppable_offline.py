"""#462-r4b-r1-r1-r1-r1-b-r1-r1 -- GARDE du 5e conjoint de `BattleFatigueAbility$$CreateTrigger`.

CE QUE CE FICHIER VERROUILLE. `IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateTrigger`
chaine SIX conjoints ; le port n'en portait que CINQ. Le manquant --
`NOT IsObjectOrSteppable(sel@+0x60 = le MOURANT)` -- etait **cite dans la docstring du module qui ne
l'implementait pas**, donc rien ne signalait son absence : ecart PERMISSIF et SILENCIEUX (le port
rendait l'unite eligible a la fuite sur la mort d'un objet / d'un decoy `Steppable` allie, que le
natif ignore).

POURQUOI UN TEST ET PAS SEULEMENT LE PROBE. La mesure vit dans
`probe_462_r4b_r1_r1_r1_r1_b_r1_r1_object_or_steppable.py --step guard`, mais **un probe MESURE, il
ne GARDE pas** : aucune passe de tests ne le joue, donc retirer `_IS_OBJECT_OR_STEPPABLE` de
`BattleFatigueAbility.matches` ne ferait rougir personne. Ce fichier rejoue le meme montage sous
pytest -- le probe reste la source du montage (aucun fork : ces tests l'IMPORTENT).

OFFLINE, ET C'EST UN CHOIX. `matches` est un predicat PUR : il se teste sans runner ni tirage. La
FUITE, elle, passe par `Maybe(GetFleeChance)` -- la confronter live demanderait N tirages
(`GetFleeChance` = `ConditionalAmount(TargetIsOverkilled ? 0x33 : 0x2a)`) et le `UnitFlag.Fled = 9`
interdit au meme porteur de re-fuir. Ce qu'on garde ici est la **presence du conjoint**, pas la
fuite ; le verdict natif reste NON CONFRONTE et la fiche le dit.

LE CONJOINT EST GARDE LIVE AILLEURS, et il ne faut pas le dupliquer :
`tests/engine/runner/test_barbed_ovipositor_live.py` confronte LIVE
`NOT IsObjectOrSteppable(target@0x178)` avec un `genesSmnDecoy` Steppable en bras negatif. Ce
fichier-ci garde le CONJOINT sur `BattleFatigueAbility`, que rien ne couvrait.

⚠ RECTIFIE DEUX FOIS. (2026-08-05 matin, #462-...-r1) cette docstring affirmait que
`barbed_ovipositor` << passe par le foyer >> : c'etait FAUX, le module avait garde sa recopie
manuelle. (2026-08-05, #462-...-r3) c'est REDEVENU VRAI -- les TROIS consommateurs du foyer y
passent maintenant. Le bras `genesSmnDecoy` cite ci-dessus garde le CONJOINT dans le regime NOMINAL ;
le regime CADAVRE (victime deja morte au chargement, donc SANS `StatsComponent` : substrat brut
VIDE) est garde par `test_barbed_ovipositor_live.py::test_barbed_ovipositor_corpse_substrate_live`.
Le foyer est aussi garde live par `test_master_tutelaries_object_target_live.py`.

ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_462_r4b_r1_r1_r1_r1_b_r1_r1_object_or_steppable as P


# Chaque bras : (libelle, traits du MOURANT, verdict attendu de `matches`).
# SEULS les traits du mourant changent d'un bras a l'autre -- meme geometrie (adjacence 1), meme
# team, meme evenement. C'est ce qui rend un verdict ATTRIBUABLE au conjoint et a rien d'autre.
BRAS = [
    pytest.param([], True, id="mourant-normal-CONTROLE"),
    pytest.param(["Steppable"], False, id="Steppable-27"),
    pytest.param(["Object"], False, id="Object-13"),
    pytest.param(["Steppable", "Object"], False, id="Steppable+Object"),
    # `Decoy` (1053) SEUL doit passer : `IsObjectOrSteppable` ne nomme que 27 et 13. Ce bras PORTE
    # UN VERDICT -- c'est lui qui refute la recopie `{Steppable, Decoy}` de
    # `triggers/loki/master_of_the_tutelaries.py` (residu `#462-r4b-r1-r1-r1-r1-b-r1-r1-r1`).
    # Le passer a False le jour ou l'on « harmonise » les deux sites serait la faute exacte.
    pytest.param(["Decoy"], True, id="Decoy-1053-seul"),
]


@pytest.mark.parametrize("traits,attendu", BRAS)
def test_conjoint_5_gate_sur_les_traits_du_mourant(traits, attendu):
    """`NOT IsObjectOrSteppable(dying)` = `NOT (HasTrait(27 Steppable) | HasTrait(13 Object))`.

    Le sujet est le MOURANT (`sel@+0x60`), pas `self` (`+0x30`) : porte sur `self`, le meme
    conjoint aurait empeche un objet de FUIR au lieu d'empecher un objet de FAIRE FUIR. Les deux
    lectures ont le meme nombre de conjoints et les memes symboles -- seul l'offset les separe,
    et c'est ce que ce test fige (le mourant porte les traits, jamais le porteur)."""
    got, _ = P._verdict(traits)
    assert got is attendu, (
        "traits du MOURANT %r -> matches=%s, attendu %s. Le 5e conjoint de "
        "`BattleFatigueAbility$$CreateTrigger` est `NOT IsObjectOrSteppable(sel@+0x60)` = "
        "`NOT (HasTrait(x,0x1b=27) | HasTrait(x,0xd=13))` -- passer par le foyer "
        "`engine/entities/triggers.py::is_object_or_steppable`." % (traits, got, attendu))


@pytest.mark.parametrize("traits,attendu", BRAS)
def test_contre_epreuve_la_neutralisation_du_conjoint_mord(traits, attendu):
    """CONTRE-EPREUVE -- c'est elle qui rend le vert du test precedent ATTRIBUABLE.

    Le meme etat est rejoue avec le conjoint 5 rendu INERTE (noeud substitue, toujours faux, donc
    `NOT` toujours vrai) : cela reconstitue exactement le comportement d'AVANT le fix. On exige
    alors que le verdict **bascule** sur les bras que le conjoint est cense gater, et **coincide**
    sur les autres. Sans cette assertion, le test precedent resterait vert meme si son montage
    etait devenu incapable d'atteindre le conjoint -- il serait passe AVANT le fix aussi.

    ⚠ LA MUTATION EST VERIFIEE AVANT SON RESULTAT. `calls == 0` = le noeud substitue n'a jamais ete
    consulte : la contre-epreuve n'aurait alors rien prouve, et son « verdict identique » se
    lirait a tort comme « le conjoint ne change rien ». Le VERT est le resultat suspect ici, pas
    le rouge -- d'ou une assertion sur le fait que la substitution a mordu, posee en PREMIER."""
    contre, calls = P._verdict(traits, neutralise=True)
    assert calls is not None and calls > 0, (
        "MUTATION INERTE : le noeud substitue a `_IS_OBJECT_OR_STEPPABLE` n'a ete consulte %r "
        "fois pour traits=%r. La contre-epreuve ne mesure RIEN -- soit un conjoint anterieur "
        "court-circuite avant lui, soit la substitution ne prend pas (valeur capturee ailleurs "
        "qu'a l'attribut de module)." % (calls, traits))
    got, _ = P._verdict(traits)
    doit_basculer = not attendu               # les bras gates, et eux seuls, doivent basculer
    if doit_basculer:
        assert contre != got, (
            "traits=%r : neutraliser le conjoint 5 ne change RIEN (%s -> %s) alors que ce bras "
            "est precisement celui qu'il gate. Le verdict `False` du test precedent vient donc "
            "d'un AUTRE conjoint, et ce fichier ne garde pas ce qu'il pretend garder."
            % (traits, got, contre))
    else:
        assert contre == got, (
            "traits=%r : neutraliser le conjoint 5 change le verdict (%s -> %s) alors que ce bras "
            "ne doit PAS etre gate. Le conjoint mord trop large -- il ne nomme que 27 et 13."
            % (traits, got, contre))


def test_le_port_passe_par_le_foyer_partage():
    """Le conjoint doit venir du FOYER, pas d'une n-ieme recopie manuelle.

    C'est ce qui a produit le defaut d'origine : `IsObjectOrSteppable` a HUIT call-sites natifs, le
    port en portait DEUX, recopies a la main -- et ils DIVERGEAIENT (`barbed_ovipositor` fidele,
    `master_of_the_tutelaries` en `{Steppable, Decoy}`). Le meme predicat natif rendait deux
    verdicts selon le module. Cette assertion fige l'identite de l'objet : si quelqu'un remplace le
    noeud par une recopie locale, le test rougit meme si le comportement coincide -- parce que
    c'est la DIVERGENCE FUTURE qu'on previent, pas la valeur d'aujourd'hui."""
    from engine.runner.operations import behaviour as B
    from engine.entities.selectors.accessors import Target
    from engine.entities.triggers import is_object_or_steppable

    attendu = is_object_or_steppable(Target())
    assert type(B._IS_OBJECT_OR_STEPPABLE) is type(attendu), (
        "`behaviour._IS_OBJECT_OR_STEPPABLE` n'est plus un noeud produit par "
        "`entities/triggers.py::is_object_or_steppable` (type %r au lieu de %r)."
        % (type(B._IS_OBJECT_OR_STEPPABLE).__name__, type(attendu).__name__))
    # Le foyer mirroire `DSLTriggers$$IsObjectOrSteppable` = `HasTrait(x,0x1b) | HasTrait(x,0xd)`,
    # dans CET ordre (Steppable a gauche, Object a droite -- ordre du decompile).
    from engine.entities.traits.unit_trait import UnitTrait
    assert (B._IS_OBJECT_OR_STEPPABLE.a.trait, B._IS_OBJECT_OR_STEPPABLE.b.trait) == (
        int(UnitTrait.Steppable), int(UnitTrait.Object)), (
        "les operandes du OU ne sont plus `(27 Steppable, 13 Object)` : %r"
        % ((B._IS_OBJECT_OR_STEPPABLE.a.trait, B._IS_OBJECT_OR_STEPPABLE.b.trait),))
