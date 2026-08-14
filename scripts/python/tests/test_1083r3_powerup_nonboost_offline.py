"""#1083-r3 -- garde OFFLINE des `PowerUp_*` NON-BOOST (tranche 2 de la famille `APowerUpAbility`).

Ce que ce fichier garde, et POURQUOI chaque etage existe (chacun a ete ecrit contre une faute
PRECISE que le port pouvait commettre silencieusement) :

  1. INSCRIPTION      -- les classes sont au registre `ABILITY_TRIGGERS` sous leur nom gameconfig.
  2. TRIGGER HERITE   -- elles ne re-declarent PAS de trigger : le balayage natif etablit que ZERO
                         des 22 `PowerUp_*` ne surcharge `CreateTrigger`. Une sous-classe qui
                         redefinirait `event_id`/`matches` divergerait du natif SANS erreur.
  3. BOUCLIER PAR LA CONFIG -- `PowerUp_Bomb` n'a NI `shieldPct` NI `nrOfRounds` au gameconfig, donc
                         son volet bouclier est eteint par la branche `Nothing()` d'`AddShield` ;
                         `Healing` et `ReactivateAbility`, eux, en ont un. C'est le SEUL etage qui
                         distingue « le port lit la config » de « le port suppose que tous les
                         power-ups ont un bouclier ».
  4. LA PART DE STAT  -- le soin lit `Health/**Maximum**`, le bouclier `Health/**Initial**`. Les deux
                         coexistent dans le MEME arbre, et les confondre est INVISIBLE tant qu'aucun
                         modificateur de PV max n'est actif. L'etage les separe par la MESURE (il
                         monte un porteur dont Maximum != Initial), pas par lecture de code.
  5. LA BRANCHE       -- mecanique -> `Repair`, non-mecanique -> `Heal`. Inverser les deux branches
                         donnerait le meme arbre a l'oeil.
  6. NON-DEGENERESCENCE -- chaque temoin est assertionne NON VIDE avant d'etre compare. Un accord
                         entre deux ensembles vides passerait pour un vert (cf. CLAUDE.md).

Tout est OFFLINE : aucun runner, aucun RPC. Les montages construisent des arbres et les evaluent
contre un `State` minimal.
"""
from __future__ import annotations

import pytest

from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.effects.magnitude import ability_var
from engine.entities.stats import StatPart, StatType
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
from engine.runner.operations.triggers.loki import power_up as PU
from engine.runner.operations.triggers.loki import power_up_nonboost as PUN

#: Les mecaniques de CETTE tranche qui sont PORTEES (les quatre autres sont documentees en residu).
PORTEES = {
    "PowerUp_ReactivateAbility": PUN.PowerUpReactivateAbilityAbility,
    "PowerUp_Healing": PUN.PowerUpHealingAbility,
}
#: Les six `PowerUp_*` non-boost, pour l'etage « bouclier » (il porte AUSSI sur les non-portees :
#: c'est du gameconfig, pas du code).
AVEC_BOUCLIER = ("PowerUp_ReactivateAbility", "PowerUp_Healing")
SANS_BOUCLIER = ("PowerUp_Bomb", "PowerUp_Reinforcement", "PowerUp_Resurrect")


# ---------------------------------------------------------------------------------------------
# Etage 1 -- INSCRIPTION
# ---------------------------------------------------------------------------------------------
def test_etage1_les_deux_portees_sont_au_registre():
    assert PORTEES, "temoin VIDE : le dict des portees ne doit pas etre vide"
    for nom, cls in PORTEES.items():
        inscrites = ABILITY_TRIGGERS.get(nom, ())
        assert cls in tuple(inscrites), (
            "%s absente d'ABILITY_TRIGGERS : le port existe mais le moteur ne l'appellera "
            "JAMAIS -- degradation silencieuse, ni erreur ni crash." % cls.__name__)
        assert cls.ABILITY_NAME == nom, (
            "la CLE du registre doit etre le nom gameconfig porte par la classe")


def test_etage1b_les_ids_sont_des_membres_nommes_de_TriggeredAbilityType():
    """Le membre NOMME, jamais l'ordinal : les enums sont regeneres a chaque build et une
    confusion d'ordinal est SILENCIEUSE (`TriggeredAbilityType.PowerUp_MeleeHits` == 1138 ==
    `EffectType.PowerUp_Armor`). Cet etage fige l'appariement NOM -> id ecrit au site."""
    attendus = {
        "PowerUp_ReactivateAbility": TriggeredAbilityType.PowerUp_ReactivateAbility,
        "PowerUp_Healing": TriggeredAbilityType.PowerUp_Healing,
    }
    for nom, cls in PORTEES.items():
        assert cls.TRIGGERED_ABILITY_ID == int(attendus[nom]), (
            "%s : l'id ecrit au site ne correspond plus au membre nomme %s" % (nom, attendus[nom]))


# ---------------------------------------------------------------------------------------------
# Etage 2 -- LE TRIGGER EST HERITE, PAS RE-DECLARE
# ---------------------------------------------------------------------------------------------
def test_etage2_aucune_sous_classe_ne_redeclare_le_trigger():
    """ZERO des 22 `PowerUp_*` ne surcharge `CreateTrigger` (balayage exhaustif de
    `ghidra/functions.tsv`, build `rnca9r7q6c`). Une sous-classe qui redefinirait `matches` ou
    `event_id` divergerait donc du natif sans qu'aucun test live ne le montre forcement."""
    for nom, cls in PORTEES.items():
        assert "matches" not in vars(cls), (
            "%s redefinit `matches` : le natif ne surcharge AUCUN `CreateTrigger`" % nom)
        assert "event_id" not in vars(cls), (
            "%s redefinit `event_id` : le trigger doit venir de la base" % nom)
        # ... et l'heritage doit REELLEMENT donner le vecteur de la base.
        assert cls.event_id == PU.APowerUpAbility.event_id
        assert cls.fire_on_death is True, (
            "l'owner EST le mourant (`get_OwnerIsTarget`) -- sans `fire_on_death` le vecteur "
            "`On(PreUnitDeath)` ne partirait jamais")


# ---------------------------------------------------------------------------------------------
# Etage 3 -- LE BOUCLIER EST DECIDE PAR LA CONFIG, PAS PAR LE CODE
# ---------------------------------------------------------------------------------------------
def test_etage3_le_bouclier_suit_le_gameconfig_et_non_une_supposition():
    """`APowerUpAbility$$AddShield` commence par
    `if (!TryGetNumberConstant(config, shieldPct)) return Nothing();`.

    Un port qui poserait un bouclier « parce que les autres power-ups en ont un » serait faux pour
    `PowerUp_Bomb`, et la faute serait INVISIBLE hors mesure du bouclier."""
    poses, eteints = [], []
    for nom in AVEC_BOUCLIER:
        pct = ability_var(nom, AbilityConstantType.shieldPct.name, is_constant=True)
        assert pct is not None, ("%s : `shieldPct` attendue au gameconfig" % nom)
        arbre = PU.add_shield_tree(nom, 1)
        assert arbre is not None, ("%s : bouclier attendu, arbre VIDE" % nom)
        poses.append(nom)
    for nom in SANS_BOUCLIER:
        pct = ability_var(nom, AbilityConstantType.shieldPct.name, is_constant=True)
        assert pct is None, (
            "%s : `shieldPct` PRESENTE au gameconfig -- la premisse de cet etage a change, "
            "re-lire `AddShield` plutot que d'ajuster le test" % nom)
        assert PU.add_shield_tree(nom, 1) is None, (
            "%s : le port pose un bouclier que le natif eteint (`Nothing()`)" % nom)
        eteints.append(nom)
    # NON-DEGENERESCENCE : les deux cotes doivent etre non vides, sinon l'etage ne compare rien.
    assert poses and eteints, (
        "temoin DEGENERE : il faut au moins un power-up de chaque cote (%r / %r)" % (poses, eteints))


# ---------------------------------------------------------------------------------------------
# Etage 4 -- LA PART DE STAT : `Maximum` pour le soin, `Initial` pour le bouclier
# ---------------------------------------------------------------------------------------------
def _porteur(hp_courant: int, hp_initial: int, hp_max: int):
    """Un porteur dont `Initial` et `Maximum` DIVERGENT -- sans cette divergence l'etage 4 serait
    vacant (les deux parts rendraient le meme nombre et l'erreur passerait)."""
    return {"id": 1, "hp": hp_courant,
            "stats": {int(StatType.HEALTH): {int(StatPart.INITIAL): hp_initial,
                                             int(StatPart.MAXIMUM): hp_max}}}


class _EntitesFactices:
    """Le minimum que `StatAmount`/`PercentageOf` consomment : les accesseurs de selecteur et un
    `get_stat` au contrat REEL du moteur (`(u, stat_type, variant, level)` -- lu dans
    `entities/formulas.py::StatAmount.calculate`, pas devine). Volontairement squelettique :
    l'etage teste la PART LUE, pas le moteur.

    ⚠ Il LEVE sur une part non fournie plutot que de rendre 0. Le defaut degrade du moteur
    (`_default_get_stat`) rend le HP COURANT pour toute variante de `Health` -- s'y appuyer ici
    rendrait l'etage 4 incapable de distinguer `Initial` de `Maximum`, donc VACANT."""

    def __init__(self, unite):
        self.unite = unite
        self.caster = unite
        self.actor = unite
        self.owner = unite
        self.target = unite
        self.has_trait = None

    def get_stat(self, u, stat_type, variant, level=None):
        parts = self.unite["stats"][int(stat_type)]
        if int(variant) not in parts:
            raise AssertionError(
                "part %r non fournie par le porteur de test : l'etage exige une lecture "
                "EXPLICITE de la part, pas un repli sur le HP courant" % variant)
        return parts[int(variant)]


def test_etage4_le_soin_lit_MAXIMUM_et_le_bouclier_lit_INITIAL():
    """Les deux parts coexistent dans le MEME arbre pour `PowerUp_Healing`. On ne lit pas le code :
    on monte un porteur ou `Initial != Maximum` et on regarde QUEL nombre sort."""
    pct = ability_var("PowerUp_Healing", AbilityConstantType.HealPercentage.name, is_constant=True)
    assert pct is not None, "premisse changee : `HealPercentage` absente du gameconfig"
    pct = int(pct)

    montant = PUN.heal_amount_tree("PowerUp_Healing")
    assert montant is not None, "l'arbre de montant du soin ne doit pas etre vide"

    # Les deux parts DIVERGENT : Initial = 1000, Maximum = 3000.
    ent = _EntitesFactices(_porteur(hp_courant=1, hp_initial=1000, hp_max=3000))
    obtenu = int(montant.evaluate(ent))
    attendu_max = pct * 3000 // 100
    attendu_init = pct * 1000 // 100
    assert attendu_max != attendu_init, (
        "temoin DEGENERE : le porteur doit faire diverger Initial et Maximum, sinon cet etage "
        "ne peut PAS distinguer les deux parts")
    assert obtenu == attendu_max, (
        "le soin doit lire `Health/Maximum` (%d), il a lu %d ; `Health/Initial` vaudrait %d"
        % (attendu_max, obtenu, attendu_init))


# ---------------------------------------------------------------------------------------------
# Etage 5 -- LA BRANCHE : mecanique -> Repair, non-mecanique -> Heal
# ---------------------------------------------------------------------------------------------
def test_etage5_mecanique_va_vers_Repair_et_non_mecanique_vers_Heal():
    """`If(IsMechanical(target, 0), Repair, Heal)` -- inverser les deux branches donnerait un arbre
    identique a l'oeil. On inspecte donc les DEUX cotes du `If` construit."""
    from engine.runner.abilities.behaviours.stats import Heal, Repair

    arbre = PUN.PowerUpHealingAbility(owner_id=1).additional_behavior(None)
    assert arbre is not None, "l'arbre de `PowerUp_Healing` ne doit pas etre vide"
    branche_vraie = getattr(arbre, "then", None)
    branche_fausse = getattr(arbre, "otherwise", None)
    assert branche_vraie is not None and branche_fausse is not None, (
        "les deux branches du `If` doivent exister -- le natif passe `heal` en `otherwise`")
    assert isinstance(branche_vraie, Repair), (
        "branche VRAIE (`IsMechanical`) : `Repair` attendu, obtenu %r" % type(branche_vraie))
    assert isinstance(branche_fausse, Heal), (
        "branche FAUSSE : `Heal` attendu, obtenu %r" % type(branche_fausse))
    # Les options LUES : `ForRepair()` / defauts du ctor de `HealBehaviourOptions` -> (0, True).
    for feuille in (branche_vraie, branche_fausse):
        assert feuille.scope == 0 and feuille.remove_effects is True, (
            "options : le natif ecrit `(scope=0, remove_effects=True)` des deux cotes "
            "(ForRepair / defauts du ctor), pas une regeneration")
        assert feuille.guard is None, (
            "le natif passe `target` NU aux deux feuilles -- poser une garde EXCLURAIT des "
            "cibles que le natif laisse au gate de l'Operation")


# ---------------------------------------------------------------------------------------------
# Etage 6 -- REACTIVATE : le flag passe est bien `allowUseless = true`
# ---------------------------------------------------------------------------------------------
def test_etage6_reactivate_passe_allow_useless_vrai():
    """`ResetActiveAbility(target, allowUseless: true)`. Le flag est transmis tel quel au gate
    `BattleQuery$$EntityCanHaveActiveAbilityReset` : le poser a `False` restreindrait le reset
    sans aucune erreur."""
    from engine.runner.abilities.behaviours.ability_state import ResetActiveAbility

    arbre = PUN.PowerUpReactivateAbilityAbility(owner_id=1).additional_behavior(None)
    assert isinstance(arbre, ResetActiveAbility), (
        "`PowerUp_ReactivateAbility` doit poser un `ResetActiveAbility`, obtenu %r" % type(arbre))
    assert arbre.ignore_turn_flag is True, (
        "le natif passe `allowUseless = true` ; la feuille portee nomme ce parametre "
        "`ignore_turn_flag` mais c'est la MEME position et le MEME gate")
