"""`IdunBattle.Entities.Effects.Loki.UntilOfEndTurnEffect` -- LA classe de MARQUEUR A DUREE du natif.

Ce n'est pas un effet « de HatefulAssault » : c'est une classe GENERIQUE du jeu, dont tout le contenu
tient en DEUX faits, tous deux lus au decompile du build `rnca9r7q6c` :

    IdunBattle.Entities.Effects.Loki.UntilOfEndTurnEffect$$.ctor(sourceAbility)
        -> IdunBattle.Entities.Effects.BaseEffect$$.ctor(hasAutomaticActivation: true,
                                                         unitEffectType: null,
                                                         sourceAbility: <copie>)
    IdunBattle.Entities.Effects.Loki.UntilOfEndTurnEffect$$CreateRemoveEffectTrigger()
        -> IdunBattleLogic.Entities.DSLTriggers$$On(EventTriggerType.TurnEnd = 0x17,
                                                    ownerNeedsToBeAlive: false)

AUCUN autre override : ni `CreateEffect*BonusForAttack`, ni `Create*MalusForDefense`, ni
`GetStatModification*`, ni `CreateActiveCondition`. La classe ne CONTRIBUE donc a RIEN -- sa seule
raison d'etre est sa DUREE. C'est pour cela que le port se contente d'heriter `BaseEffect` sans rien
surcharger : la contribution nulle est deja le comportement de la base, et la duree ne vit PAS dans la
classe cote port (elle vit dans le trigger de retrait, cf. `runner/operations/triggers/loki/
until_of_end_turn.py`, exactement comme le natif la met dans `CreateRemoveEffectTrigger`).

## Aucun TIMER -- la duree est un TRIGGER, et c'est mesure

`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds`
est un switch sur DIX valeurs (`0x5 0x11 0x12 0x3a 0x4f 0x429 0x48a 0x4dc 0x5c4`, plus le defaut) --
**1175 n'y est pas**, la fonction rend un `Nullable` VIDE. Et la fabrique appelle la surcharge
`AddEffect(effectType, abilityState, targets, turns: Nullable<int>)` avec `turns` vide. Les deux
branches de la cascade de duree d'`IdunBattle.Operations.AddEffectOperation$$Execute` sont donc
absentes -> `remaining = 0` = PERMANENT tant que rien ne le retire. Un port qui oublierait le trigger
de retrait n'aurait pas « une duree approximative » : il aurait un marqueur A VIE, donc un faux
positif silencieux a chaque tour suivant. Re-derive par `probe_1175_hateful_assault_marker.py`
etape 4 (le switch est re-execute depuis le desassemblage, pas recopie).

## Identite de classe -- ce que le probe TRANCHE, et ce qu'il ne tranche pas

`probe_1175 --step 1` rend le slot `Il2CppClass*` charge avant `il2cpp_object_new` (l'IDENTITE, cf.
CLAUDE.md « un nom de $$.ctor n'est PAS une classe ») : **1175 est SEUL sur son slot**. Le nom du ctor
appele, lui, est partage : `UntilOfEndTurnEffect$$.ctor` couvre DEUX slots, `1175
HatefulAssault_AlreadyAttacked` et `1407 HypersensoryAbilities_HasBeenAttacked` -- deux marqueurs
« a deja ete attaque/frappe », de meme forme. Le binaire porte d'ailleurs DEUX classes soeurs au corps
de ctor IDENTIQUE (donc dedupliquable) : `UntilOfEndTurnEffect` (retrait `On(0x17 TurnEnd)`) et
`IdunBattle.Entities.Effects.Loki.UntilOfEndPhaseEffect` (retrait `On(0x3a PhaseEnd)`). L'identite du
slot ne se resout pas statiquement en un NOM -- c'est une valeur runtime derriere la metadata IL2CPP.
La question « TurnEnd ou PhaseEnd ? » est donc tranchee par la MESURE LIVE (le tour ou 1175 quitte
`decisionView.effects`), cf. `tests/engine/runner/test_hateful_assault_live.py` -- jamais par le nom.

## Porteur

`1175` est pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.HatefulAssaultAbility$$
CreateBehaviour` (passif `HatefulAssault`, TriggeredAbilityType 0x40e = 1038, unite `blackTerminator`
« Angrax » -- HERO, dans le pool `rl_duel build --list-pool`). Il est LU par le `CreateTrigger` de
cette meme ability, et par personne d'autre : `probe_1175 --step 2` balaie TOUT le segment de code a
la recherche de l'immediat 1175 et le montre.
"""
from __future__ import annotations

from ..base import BaseEffect


class UntilOfEndTurnEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.UntilOfEndTurnEffect` -- marqueur NU a duree de tour.

    Zero override, et c'est FIDELE : la classe native n'implemente que son `.ctor` (qui delegue a
    `BaseEffect(hasAutomaticActivation: true, unitEffectType: null, sourceAbility)`) et son
    `CreateRemoveEffectTrigger`. Ce dernier n'est PAS un membre de la classe d'effet cote port : le
    natif le consomme par `IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities`, qui
    en fait une TriggeredAbility `Triggered(<trigger>, RemoveEffect(<cette instance>))` -- soit,
    cote port, une entree d'`EFFECT_TRIGGERS`. Cf. le module jumeau du runner.

    Consequence sur l'etat : l'instance nait avec `remaining_turns = None` (permanent, aucun
    `DefaultAmountOfRounds`) et disparait par le trigger. Elle ne porte AUCUNE magnitude -- l'appeler
    « effet » est un abus commode : c'est un booleen date, dont la seule lecture est un `HasEffect`."""
