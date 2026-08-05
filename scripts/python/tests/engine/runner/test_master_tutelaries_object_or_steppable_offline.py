"""#462-r4b-r1-r1-r1-r1-b-r1-r1-r1 -- GARDE du 4e conjoint de
`MasterOfTheTutelaries_SummonAbility$$CreateTrigger`.

CE QUE CE FICHIER VERROUILLE. Le conjoint `NOT IsObjectOrSteppable(sel@+0x60 = la CIBLE)` etait
RECOPIE A LA MAIN dans le module, et FAUX : `{"Steppable", "Decoy"}` la ou le natif dit
`Steppable | Object`. `Decoy` vaut **1053**, `Object` vaut **13** -- deux membres DISTINCTS de
`UnitTrait`, et la factory native
(`IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable` = `HasTrait(x, 0x1b) |
HasTrait(x, 0xd)`) ne nomme QUE 27 et 13.

CE QUE LA MIGRATION CHANGE (mesure gameconfig, `--step census`) :
  * `Decoy` SANS `Steppable` = **0** porteur -> le volet retire etait INERTE, son retrait est
    value-preserving sur le catalogue ;
  * `Object` SANS `Steppable` = **28** porteurs (tous npc `LootObj_*`) -> le volet ajoute est le
    TROU : 28 cibles que le natif ecarte et que le port laissait passer.

PORTEE ASSUMEE. Aucun de ces 28 porteurs n'est dans `data/seed-bc.json` et tous sont `npc` : le
volet ajoute est NON CONFRONTABLE par la voie `rl_duel build`. Ce fichier garde donc un MIRROR DE
FIDELITE, pas un nombre mesure live -- et le dit plutot que de le maquiller.

POURQUOI UN TEST ET PAS SEULEMENT LE PROBE. La mesure vit dans
`probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r1_mot_object_or_steppable.py --step guard`, mais **un probe
MESURE, il ne GARDE pas** : aucune passe de tests ne le joue. Ce fichier rejoue le meme montage
sous pytest -- le probe reste la source du montage (aucun fork : ces tests l'IMPORTENT).

OFFLINE, ET C'EST UN CHOIX. `matches` est un predicat PUR : il se teste sans runner ni tirage. Le
chemin nominal (le cast live de 1096 qui ARME la chaine, et le gate d'activite #231) est deja
confronte par `tests/engine/runner/test_master_tutelaries_active_gate_live.py`.

ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r1_mot_object_or_steppable as P


# Chaque bras : (traits de la CIBLE, verdict attendu, verdict du port D'AVANT le fix).
# SEULS les traits de la cible changent d'un bras a l'autre -- meme geometrie, memes equipes
# (opposees), meme marqueur 1197 actif, meme evenement `On(9)` porteur du profil Psychic. C'est ce
# qui rend un verdict ATTRIBUABLE au conjoint et a rien d'autre.
BRAS = [
    pytest.param([], True, True, id="cible-normale-CONTROLE"),
    pytest.param(["Steppable"], False, False, id="Steppable-27"),
    # LE TROU : 28 porteurs `LootObj_*` que le port laissait passer (il spawnait un Screamer que
    # le natif ne produit pas).
    pytest.param(["Object"], False, True, id="Object-13-LE-TROU"),
    pytest.param(["Steppable", "Object"], False, False, id="Steppable+Object"),
    # TEMOIN, PAS une garde de regression : `Decoy` (1053) SEUL n'a AUCUN porteur reel (tout
    # porteur `Decoy` du catalogue porte aussi `Steppable`). Ce bras n'existe que dans l'etat
    # SYNTHETIQUE ; ce qu'il fige est le LITTERAL du natif -- 27 et 13, jamais 1053. Le repasser a
    # False en << harmonisant >> avec l'ancienne recopie serait la faute exacte.
    pytest.param(["Decoy"], True, False, id="Decoy-1053-seul-TEMOIN"),
]


@pytest.mark.parametrize("traits,attendu,avant", BRAS)
def test_conjoint_gate_sur_les_traits_de_la_cible(traits, attendu, avant):
    """`NOT IsObjectOrSteppable(target)` = `NOT (HasTrait(27 Steppable) | HasTrait(13 Object))`.

    Le sujet est la CIBLE de l'attaque (`sel@+0x60`), le meme selecteur que le 2e argument
    d'`AreEnemies` -- pas le porteur (`sel@+0x30`)."""
    got, _ = P._verdict(traits)
    assert got is attendu, (
        "traits de la CIBLE %r -> matches=%s, attendu %s. Le 4e conjoint de "
        "`MasterOfTheTutelaries_SummonAbility$$CreateTrigger` est "
        "`NOT IsObjectOrSteppable(sel@+0x60)` = `NOT (HasTrait(x,0x1b=27) | HasTrait(x,0xd=13))` "
        "-- passer par le foyer `engine/entities/triggers.py::is_object_or_steppable`."
        % (traits, got, attendu))


@pytest.mark.parametrize("traits,attendu,avant", BRAS)
def test_contre_epreuve_neutralisee_le_conjoint_mord(traits, attendu, avant):
    """CONTRE-EPREUVE 1 -- le conjoint EXISTE et il est CONSULTE.

    Le meme etat est rejoue avec le noeud rendu INERTE (toujours faux, donc `NOT` toujours vrai) :
    cela reconstitue << le conjoint n'existe pas >>. On exige que le verdict BASCULE sur les bras
    que le conjoint gate, et COINCIDE sur les autres.

    ⚠ LA MUTATION EST VERIFIEE AVANT SON RESULTAT. `calls == 0` = le noeud substitue n'a jamais ete
    consulte : la contre-epreuve n'aurait alors rien prouve, et son << verdict identique >> se
    lirait a tort comme << le conjoint ne change rien >>. Le VERT est le resultat suspect ici."""
    neu, calls = P._verdict(traits, "neutralise")
    assert calls is not None and calls > 0, (
        "MUTATION INERTE : le noeud substitue a `_IS_OBJECT_OR_STEPPABLE` a ete consulte %r fois "
        "pour traits=%r. La contre-epreuve ne mesure RIEN -- soit un conjoint anterieur "
        "court-circuite avant lui (marqueur 1197, `AreEnemies`, `UnitComponent`), soit la "
        "substitution ne prend pas." % (calls, traits))
    got, _ = P._verdict(traits)
    if not attendu:
        assert neu != got, (
            "traits=%r : neutraliser le conjoint ne change RIEN (%s -> %s) alors que ce bras est "
            "precisement celui qu'il gate -- le `False` vient donc d'un AUTRE conjoint, et ce "
            "fichier ne garde pas ce qu'il pretend garder." % (traits, got, neu))
    else:
        assert neu == got, (
            "traits=%r : neutraliser le conjoint change le verdict (%s -> %s) alors que ce bras "
            "ne doit PAS etre gate -- le conjoint mord trop large." % (traits, got, neu))


@pytest.mark.parametrize("traits,attendu,avant", BRAS)
def test_contre_epreuve_la_recopie_infidele_rejouee_donne_bien_l_etat_d_avant(traits, attendu, avant):
    """CONTRE-EPREUVE 2 -- c'est ELLE qui prouve que le fix n'est pas un no-op deguise.

    Le noeud est remplace par le predicat `{Steppable, Decoy}` : cela reconstitue EXACTEMENT le
    port d'avant ce fix. On exige (a) que la substitution ait mordu, (b) qu'elle rende le verdict
    d'AVANT, et (c) que ce verdict DIFFERE du verdict courant sur les deux bras que la migration
    change (`Object` = le trou, `Decoy` seul = le volet inerte).

    Sans ce test, un fix qui aurait << oublie >> Object -- ou qui aurait garde Decoy -- resterait
    invisible : les trois autres bras coincident dans les deux mondes."""
    rec, calls = P._verdict(traits, "recopie")
    assert calls is not None and calls > 0, (
        "MUTATION INERTE : la recopie substituee n'a ete consultee %r fois pour traits=%r."
        % (calls, traits))
    assert rec is avant, (
        "traits=%r : rejouer `{Steppable, Decoy}` rend %s, or le port d'AVANT le fix rendait %s. "
        "La contre-epreuve ne reconstitue pas l'etat d'avant -- elle ne mesure donc pas le "
        "CHANGEMENT." % (traits, rec, avant))
    got, _ = P._verdict(traits)
    if attendu != avant:
        assert rec != got, (
            "traits=%r : le fix devait CHANGER ce bras (%s -> %s) et il ne change rien."
            % (traits, avant, attendu))
    else:
        assert rec == got, (
            "traits=%r : le fix a change un bras qu'il ne devait PAS changer (%s -> %s)."
            % (traits, avant, attendu))


def test_le_fix_change_exactement_deux_bras():
    """La migration n'est ni un no-op ni un elargissement sauvage : elle deplace EXACTEMENT deux
    verdicts -- `Object` seul (False au lieu de True : le trou de 28 porteurs) et `Decoy` seul
    (True au lieu de False : le volet inerte, 0 porteur reel). Si un jour ce compte bouge, c'est
    que le foyer a change de litteraux."""
    changeants = [tuple(p.values[0]) for p in BRAS if p.values[1] != p.values[2]]
    assert changeants == [("Object",), ("Decoy",)], (
        "les bras que le fix fait changer ne sont plus (Object,), (Decoy,) mais %r" % (changeants,))


def test_le_port_passe_par_le_foyer_partage():
    """Le conjoint doit venir du FOYER, pas d'une n-ieme recopie manuelle.

    C'est ce qui a produit le defaut : `IsObjectOrSteppable` a HUIT call-sites natifs, le port en
    portait DEUX, recopies a la main -- et ils DIVERGEAIENT. Cette assertion fige l'identite de
    l'objet : si quelqu'un remplace le noeud par une recopie locale, le test rougit meme si le
    comportement coincide, parce que c'est la DIVERGENCE FUTURE qu'on previent."""
    from engine.runner.operations.triggers.loki import master_of_the_tutelaries as M
    from engine.entities.selectors import Target
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.triggers import is_object_or_steppable

    attendu = is_object_or_steppable(Target())
    assert type(M._IS_OBJECT_OR_STEPPABLE) is type(attendu), (
        "`master_of_the_tutelaries._IS_OBJECT_OR_STEPPABLE` n'est plus un noeud produit par "
        "`entities/triggers.py::is_object_or_steppable` (type %r au lieu de %r)."
        % (type(M._IS_OBJECT_OR_STEPPABLE).__name__, type(attendu).__name__))
    # Ordre du decompile : Steppable a gauche, Object a droite.
    assert (M._IS_OBJECT_OR_STEPPABLE.a.trait, M._IS_OBJECT_OR_STEPPABLE.b.trait) == (
        int(UnitTrait.Steppable), int(UnitTrait.Object)), (
        "les operandes du OU ne sont plus `(27 Steppable, 13 Object)` : %r"
        % ((M._IS_OBJECT_OR_STEPPABLE.a.trait, M._IS_OBJECT_OR_STEPPABLE.b.trait),))
    assert int(UnitTrait.Decoy) not in (M._IS_OBJECT_OR_STEPPABLE.a.trait,
                                        M._IS_OBJECT_OR_STEPPABLE.b.trait), \
        "`Decoy` (1053) est reapparu dans le foyer -- le natif ne nomme que 27 et 13."


def test_le_module_ne_porte_plus_de_recopie_de_traits():
    """Le symptome exact du defaut etait un SET de NOMS de traits fige dans le module. Sa
    disparition est ce qui garantit qu'aucune 3e recopie ne repousse ici."""
    from engine.runner.operations.triggers.loki import master_of_the_tutelaries as M
    assert not hasattr(M, "_STEPPABLE_TRAITS"), (
        "`_STEPPABLE_TRAITS` est revenu dans le module : c'est la recopie manuelle que ce residu "
        "ferme. Le conjoint doit passer par `entities/triggers.py::is_object_or_steppable`.")
