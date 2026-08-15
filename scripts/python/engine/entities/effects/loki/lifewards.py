"""Les DEUX effets de `Lifewards` (#963-r3) -- passif du summon `adeptSmnGeminaeSuperia`, second
maillon du kit de `adeptCelestine`.

`EffectType.Lifewards_BondEffect` = 0x424 = **1060** et `EffectType.Lifewards_Protecting` = 0x4d8 =
**1240**. Les deux sont poses par `LifewardsAbility$$CreateBehaviour` (cf.
`engine/runner/operations/triggers/loki/lifewards.py`, qui porte l'ability).

===================================================================================================
CE QUE CES DEUX EFFETS SONT, ET CE QU'ILS NE SONT PAS
===================================================================================================

**AUCUN DES DEUX N'A DE FACE DE DEGAT.** C'est une MESURE, pas une abstention : leurs blocs
`methodPointers` du PE ont ete lus slot a slot, et ils declarent exactement

    LifewardsBondEffect        -> [ .ctor , CreateActiveCondition ]
    LifewardsProtectingEffect  -> [ .ctor , <deux corps GENERIQUES dedupliques> ,
                                    CreateRemoveEffectTrigger ]

-- ni `CreateEffectDamageBonusForAttack`, ni `CreateEffectDamageMalusForDefense`, ni
`CreateDamageModifier`, ni `CreateCritDamageBonus`. Ce sont des MARQUEURS : toute la mecanique de
`Lifewards` vit dans le TRIGGER de l'ability (`TransferDamage`), pas dans la consommation d'un
effet. Les inscrire a `EFFECT_CLASSES` sert a porter leur CYCLE DE VIE (activation, retrait), qui
est ce que le trigger de l'ability LIT.

⚠ **LA LECTURE DU BLOC `methodPointers` NE SUFFIT PAS A CONCLURE SUR LES VIRTUELS DE BOND, et ce
lot en donne la contre-epreuve.** Le bloc de `LifewardsBondEffect` n'a que DEUX entrees, ce qui
donnerait a croire qu'elle n'override aucun des trois gates d'`ABondEffect`. La mesure
`probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared` (voie `class_get_methods`, qui lit la
METADATA et non les corps) rend l'inverse :

    LifewardsBondEffect | get_Range = OWN=none | get_Adjacent = OWN=false
                        | get_RemoveOnBondedEntityDeath = OWN=**true**
    TRIGGERS DE RETRAIT CONSTRUITS : LifewardsBondEffect -> **a**

Un virtuel a corps trivial est DEDUPLIQUE par ICF, donc absent du bloc des corps tout en etant
declare -- exactement le faux negatif que le CLAUDE.md decrit (<< l'absence dans les tables ne
prouve RIEN >>). D'ou l'entree `BOND_REMOVAL_GATES[1060]`, gate (a) seul.

===================================================================================================
1060 `Lifewards_BondEffect` -- base `ABondEffect` (LUE dans `frida/classes.tsv`)
===================================================================================================

    $$CreateActiveCondition = IsAdjacent( Owner@<DSLSelectors+0x30>,
                                          Parent(Owner@<DSLSelectors+0x30>),
                                          UnitSelectionType.OnlyAliveAndTargetable = 3 )

L'arbre vit dans `lifewards_condition.py` (module separe : cf. son en-tete pour le cycle d'import
MESURE que ce deplacement supprime). La classe ci-dessous ne lit qu'une CLE du `unit_state`.

OBSERVABLE : le lien Geminae <-> Celestine n'est ACTIF que tant que les deux sont adjacentes.

===================================================================================================
1240 `Lifewards_Protecting` -- base `BaseEffect` (LUE dans `frida/classes.tsv`)
===================================================================================================

    $$CreateRemoveEffectTrigger = DSLTriggers$$On( EventTriggerType.Attack = 0x9,
                                                   ownerNeedsToBeAlive: 0 )

Corps ENTIER : UN seul noeud, aucun conjoint. Le retrait est porte comme un `EffectTrigger` dans
`runner/operations/triggers/loki/lifewards.py` (registre `EFFECT_TRIGGERS[1240]`), la convention de
toutes les `CreateRemoveEffectTrigger` du port.

⚠ **`ownerNeedsToBeAlive` vaut 0, et c'est LOAD-BEARING ici** -- pas un detail recopie. C'est ce
qui donne son sens a 1240 : le 2e conjoint du trigger de l'ability est
`IsAlive(Owner) | HasEffect(Owner, 0x4d8)`, donc une Geminae MORTE qui porte encore ce marqueur
protege ENCORE Celestine, jusqu'a la prochaine attaque qui le retire.

⚠ **AUCUNE `CreateActiveCondition`** sur 1240 (elle n'est pas dans son bloc) : le marqueur est
toujours ACTIF tant qu'il est present. `active_condition_ported` reste donc FAUX ici, et c'est une
lecture, pas un oubli.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect

#: Cle PARESSEUSE publiee par `runner/components.py::UnitEffectStateView` -- le verdict de
#: `lifewards_condition.evaluate_lifewards_bond_adjacent` pour le PORTEUR de l'instance.
CTX_BOND_ADJACENT = "lifewards_bond_adjacent_to_parent"


class LifewardsBondEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.LifewardsBondEffect` (`EffectType` 0x424 = 1060, nom capte
    `Lifewards_BondEffect`), base `ABondEffect`.

    Marqueur du lien Geminae <-> Celestine. Sa SEULE mecanique propre est sa condition d'activite ;
    ses retraits viennent de la base (`BOND_REMOVAL_GATES[1060]`, gate (a) seul -- mesure en tete de
    module)."""

    #: `CreateActiveCondition` REELLEMENT portee (arbre 1:1 dans `lifewards_condition.py`) -> le
    #: port RE-EVALUE la condition au lieu de s'en remettre au flag capte.
    active_condition_ported = True

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        """`IsAdjacent(Owner, Parent(Owner), 3)`.

        TRI-ETAT STRICT sur le substrat : cle ABSENTE = canal NON MESURE (`unit_state` ad hoc,
        entite sans `PositionComponent`, face PREDICTION) -> on retombe sur le DEFAUT de
        `BaseEffect` (`True`), c.-a-d. le comportement STRICTEMENT anterieur a cette classe. Ecrire
        `False` sur une absence de mesure eteindrait le bond dans tout contexte qui ne publie pas la
        cle -- une degradation qui se lirait comme une mecanique."""
        v = (unit_state or {}).get(CTX_BOND_ADJACENT)
        if v is None:
            return True
        return bool(v)


class LifewardsProtectingEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.LifewardsProtectingEffect` (`EffectType` 0x4d8 = 1240, nom
    capte `Lifewards_Protecting`), base `BaseEffect`.

    Marqueur SANS condition d'activite et SANS face de degat (bloc `methodPointers` lu, cf. l'en-tete
    du module). Son unique mecanique est son RETRAIT, `On(0x9 = Attack)`, porte comme un
    `EffectTrigger` -- et sa seule LECTURE est le 2e conjoint du trigger de `LifewardsAbility`.

    La classe est inscrite a `EFFECT_CLASSES` pour que l'effet ait un porteur NOMME plutot qu'un
    `BaseEffect` anonyme qui se lirait comme << rien a porter ici >>."""
