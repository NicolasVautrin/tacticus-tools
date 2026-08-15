"""#952-r2, volet `AddActiveAbility` -- la moitie AJOUT de la substitution passif -> active.

CE QUE LA FICHE DISAIT, ET CE QUE LA RE-MESURE REND :

  * << `RemoveActiveAbility(Owner, 0x1c Repair)` n'a aucun canal d'init >> -- **REFUTE** :
    `PASSIVE_REMOVES_ACTIVE_ABILITY` existe depuis #1015-r1, avec les TROIS entrees et le meme
    recensement par xrefs entrantes que celui refait ici sur `t6dpr4k06g`.
  * << `AddActiveAbility(Owner, 0x45f Repair_GalvanicField, abilityState)` n'a aucun canal >> --
    **a moitie refute, et le fait neuf est precis** : le canal existe cote DECISION
    (`ai/state_bridge.py::_granted_abilities`) mais il DERIVE l'ability accordee du NOM du passif
    (`Heal_<Passif>`), et cette convention ne marche que pour UN des trois artefacts natifs.

MESURE, sur le build `t6dpr4k06g` :

    passif           litteral natif                convention `Heal_<P>`      resultat
    TwistedScience   0x48f = `Heal_TwistedScience`  `Heal_TwistedScience`      1167   TROUVE
    HealingBalms     0x4bc = `HealingBalms_Heal`    `Heal_HealingBalms`        None   RATE
    GalvanicField    0x45f = `Repair_GalvanicField` `Heal_GalvanicField`       None   RATE

Effet chiffre du trou : `entity_active_ability_ids` rendait `[1117]` pour `admecManipulus` la ou le
natif rend `[1117, 1119]` (mesure live #952, runner 367, board MC1_67).

C'est le CLAUDE.md mot pour mot -- << la VOIE ne dit pas l'enum >>, seul le NOM ecrit au site
tranche. D'ou le registre LITTERAL `PASSIVE_ADDS_ACTIVE_ABILITY`, jumeau exact de son voisin de
retrait, et son consommateur dans le REPLI d'`entity_active_ability_ids`.

REGIME SEPARANT. Les etages construisent un contexte SANS `active_abilities` mesure : c'est le seul
regime ou le registre mord (le capteur, lui, publie deja `[1117, 1119]`).
"""
from __future__ import annotations

import inspect

import pytest

from engine.entities.active_abilities import (PASSIVE_ADDS_ACTIVE_ABILITY,
                                              PASSIVE_REMOVES_ACTIVE_ABILITY,
                                              entity_active_ability_ids,
                                              passive_granted_active_ability_ids)
from engine.entities.active_ability_type import ActiveAbilityType

#: Ce que ce fichier LIT, donc ce qui doit changer pour qu'il puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/active_abilities.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "data/gameconfig.json",
    ),
    "build": False,          # ne lit ni le binaire ni `data/symbols/**`
    "toujours": False,
    "raison": "les deux registres de substitution passif -> active, leur consommateur "
              "(`entity_active_ability_ids`), le registre d'execution qui rend les trois ids "
              "non inertes, et le kit gameconfig des porteurs.",
}

#: Les TROIS littéraux LUS dans les `CreateBehaviour` natifs -- couple (retire, ajoute) par passif.
#: Recensement EXHAUSTIF : `DSLBehaviors$$RemoveActiveAbility` et `$$AddActiveAbility` n'ont chacun
#: que TROIS appelants de code dans le build, et ce sont les memes trois.
SUBSTITUTIONS = {
    "TwistedScience": (int(ActiveAbilityType.Heal), int(ActiveAbilityType.Heal_TwistedScience)),
    "HealingBalms": (int(ActiveAbilityType.Heal), int(ActiveAbilityType.HealingBalms_Heal)),
    "GalvanicField": (int(ActiveAbilityType.Repair),
                      int(ActiveAbilityType.Repair_GalvanicField)),
}

CARRIER = "admecManipulus"     # `activeAbilities = [DefendTheDivineWork]`, `passiveAbilities = [GalvanicField]`
WITNESS = "tauCrisis"          # ne porte aucun des trois passifs -> TEMOIN


class _Ctx:
    """Contexte MINIMAL sans `active_abilities` mesure -- le regime separant."""
    def __init__(self, vis, passives=None):
        self.visual_id = vis
        self.active_abilities = None
        self.passive_abilities = passives


# ------------------------------------------------- [1] les deux moities, et leurs memes trois cles
def test_1_les_deux_registres_couvrent_les_MEMES_trois_passifs():
    assert set(PASSIVE_ADDS_ACTIVE_ABILITY) == set(PASSIVE_REMOVES_ACTIVE_ABILITY) == set(SUBSTITUTIONS)
    for p, (retire, ajoute) in SUBSTITUTIONS.items():
        assert PASSIVE_REMOVES_ACTIVE_ABILITY[p] == retire
        assert PASSIVE_ADDS_ACTIVE_ABILITY[p] == ajoute, (
            f"{p} : le port ajoute {PASSIVE_ADDS_ACTIVE_ABILITY[p]}, le natif ajoute {ajoute}")


def test_2_la_CONVENTION_de_nommage_rate_DEUX_des_trois():
    """Le fait qui justifie ce registre. Si un jour les trois enums etaient renommes en
    `Heal_<Passif>`, cet etage tomberait -- et ce serait le signal qu'un registre litteral n'est
    plus necessaire, pas un faux positif. On mesure les DEUX cotes : un registre juste ET une
    convention qui rate, sinon l'accord serait trivial."""
    rates = [p for p, (_, ajoute) in SUBSTITUTIONS.items()
             if ActiveAbilityType.__members__.get(f"Heal_{p}") is None]
    assert set(rates) == {"HealingBalms", "GalvanicField"}, (
        f"la convention `Heal_<P>` ne rate plus les memes : {rates}")
    # ... et le tiers, lui, passe : c'est ce qui rend le trou INVISIBLE quand on ne regarde que lui.
    assert int(ActiveAbilityType.Heal_TwistedScience) == SUBSTITUTIONS["TwistedScience"][1]


def test_3_aucune_entree_n_est_un_MENSONGE_DE_COUVERTURE():
    """Un id qu'on fait apparaitre sans que le runner sache l'executer ferait passer l'audit de GAP
    a PORTE sans qu'aucun comportement ne change."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    for p, aid in PASSIVE_ADDS_ACTIVE_ABILITY.items():
        assert ABILITY_CLASSES.get(aid) is not None, (
            f"{p} accorde {aid}, qui n'a AUCUNE classe d'execution portee")


# ------------------------------------------------------------------ [4] la fonction et son tri-etat
def test_4_le_tri_etat_de_la_fonction():
    assert passive_granted_active_ability_ids(("GalvanicField",)) == [
        int(ActiveAbilityType.Repair_GalvanicField)]
    assert passive_granted_active_ability_ids(("HealingBalms",)) == [
        int(ActiveAbilityType.HealingBalms_Heal)]
    assert passive_granted_active_ability_ids(()) == []
    # `None` = canal MUET -> AUCUN ajout. C'est une BORNE nommee, pas une mesure : le confondre avec
    # `()` ferait lire << ce porteur n'accorde rien >> la ou on n'a rien mesure.
    assert passive_granted_active_ability_ids(None) == []
    # ORDRE STABLE (celui du registre) -- deux appels doivent rendre la meme liste.
    deux = ("HealingBalms", "TwistedScience")
    assert passive_granted_active_ability_ids(deux) == passive_granted_active_ability_ids(deux[::-1])


# ------------------------------------------------- [5] le REPLI porte enfin ce que le natif rend
def test_5_le_repli_kit_rend_ce_que_le_natif_rend():
    """MESURE LIVE de reference (#952, runner 367 board MC1_67) : `admecManipulus` publie
    `[1117 DefendTheDivineWork, 1119 Repair_GalvanicField]`."""
    got = entity_active_ability_ids(_Ctx(CARRIER), CARRIER)
    assert int(ActiveAbilityType.DefendTheDivineWork) in got     # du kit
    assert int(ActiveAbilityType.Repair_GalvanicField) in got    # accordee par le passif
    assert int(ActiveAbilityType.Repair) not in got              # RETIREE par le meme passif


def test_5b_le_TEMOIN_ne_recoit_rien():
    got = entity_active_ability_ids(_Ctx(WITNESS), WITNESS)
    for aid in PASSIVE_ADDS_ACTIVE_ABILITY.values():
        assert aid not in got, f"{WITNESS} a recu {aid} sans porter le passif"


# ------------------------------------------------- [6] la MESURE prime, et le substrat est l'ENTITE
def test_6_une_mesure_d_active_abilities_fait_AUTORITE():
    """Le tri-etat du champ ne change pas : une liste mesuree (fut-elle vide) prime sur tout, y
    compris sur ce nouveau registre. Sans quoi le seed reecrirait par-dessus une capture."""
    ctx = _Ctx(CARRIER)
    ctx.active_abilities = ["DefendTheDivineWork"]
    assert entity_active_ability_ids(ctx, CARRIER) == [int(ActiveAbilityType.DefendTheDivineWork)]
    ctx.active_abilities = []
    assert entity_active_ability_ids(ctx, CARRIER) == []


def test_7_le_substrat_des_passifs_est_l_ENTITE_pas_le_kit():
    """Meme piege de substrat que #264 / #931-r2 : une greffe `replace=True` REMPLACE
    `BC.Units[].PassiveAbilities`, donc lire le kit sur une unite greffee donnerait la mauvaise
    substitution. On monte les DEUX sens -- un porteur du kit dont l'entite ne porte PLUS le passif,
    et une unite tierce a qui on le greffe."""
    prive = entity_active_ability_ids(_Ctx(CARRIER, passives=[]), CARRIER)
    assert int(ActiveAbilityType.Repair_GalvanicField) not in prive, (
        "le kit a primé sur la mesure d'entite -- substrat FAUX")
    greffe = entity_active_ability_ids(_Ctx(WITNESS, passives=["GalvanicField"]), WITNESS)
    assert int(ActiveAbilityType.Repair_GalvanicField) in greffe


# -------------------------------------------------------- [8] le consommateur LIT bien le registre
@pytest.mark.parametrize("symbole", ["passive_granted_active_ability_ids", "passive_abilities"])
def test_8_le_repli_consomme_le_REGISTRE(symbole):
    """Un registre que personne n'interroge serait un inventaire, pas un canal."""
    src = inspect.getsource(entity_active_ability_ids)
    assert symbole in src, f"`{symbole}` n'est plus lu par `entity_active_ability_ids`"
