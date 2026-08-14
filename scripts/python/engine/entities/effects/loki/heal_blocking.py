"""`IdunBattle.Entities.Effects.HealBlockingEffect` et ses sous-classes -- les effets qui INSCRIVENT
leur porteur au registre des BLOQUEURS DE SOIN (#927).

LA HIERARCHIE EST LUE DANS `data/symbols/<build>/frida/classes.tsv`, PAS DEDUITE DU PSEUDO-C.
`FuryOfTheAncientsEffect$$.ctor` appelle un corps que ghidra NOMME
`IdunBattle.Entities.Effects.Loki.DeathwingEffect$$.ctor` -- et `DeathwingEffect` porte, elle, quatre
overrides de DEGAT (`GetEffectAmount`, `GetDoubleEffectCondition`,
`CreateEffectDamageBonusForAttack`, `CreateEffectDamageMalusForDefense`) qui n'ont RIEN a voir avec
un blocage de soin. Le corps est simplement DEDUPLIQUE par l'ICF : trois `.ctor` distincts
(`DeathwingEffect`, `FuryOfTheAncientsEffect`, `MischiefMakersEffect`) partagent la meme forme
`<base>..ctor(this, AbilityOrEffect(<abilityType>), true)`, donc le meme code, donc UN SEUL
proprietaire dans la table de symboles. La table des CLASSES tranche sans ambiguite :

    IdunBattle.Entities.Effects.HealBlockingEffect              -> IdunBattle.Entities.Effects.BaseEffect
    IdunBattle.Entities.Effects.Loki.FuryOfTheAncientsEffect    -> IdunBattle.Entities.Effects.HealBlockingEffect
    IdunBattle.Entities.Effects.Loki.MischiefMakersEffect       -> IdunBattle.Entities.Effects.HealBlockingEffect
    IdunBattle.Entities.Effects.Loki.DeathwingEffect            -> IdunBattle.Entities.Effects.BaseEffect

Lire la hierarchie dans le pseudo-C aurait donne un effet de DEGAT la ou l'i2 annonce
« Can neither get their Health restored nor be revived » (`UnitEffects/FuryOfTheAncients_Description`).

CE QUE LA CLASSE DE BASE FAIT, ET C'EST TOUT (elle n'a QUE ces deux methodes dans le dump) :

    `IdunBattle.Entities.Effects.HealBlockingEffect$$ApplyInternal(owner, target, effect)` =
        target.HealthComponent.<+0x78>.Add(effect.Id, effect.Id)
    `IdunBattle.Entities.Effects.HealBlockingEffect$$RevertInternal(owner, target, effect)` =
        target.HealthComponent.<+0x78>.Remove(effect.Id)

et le LECTEUR de ce dictionnaire est `IdunBattle.Entities.UnitExtensions$$HasHealBlockers` :

    if (GetEntityType(unit) != 1 /* Unit */) return false;
    hc = unit.HealthComponent;
    return hc.<+0x78> != null && hc.<+0x78>.Count > 0;

Aucun filtre `IsActive @+0x5c` nulle part : l'inscription vit exactement de la POSE au RETRAIT de
l'instance. Cote port, le dict `+0x78` n'est donc pas materialise -- `has_heal_blockers` derive
l'appartenance de la PRESENCE d'une instance de cette famille sur la cible
(`attack_query.has_heal_blockers`, foyer unique). Les deux sont equivalents PAR CONSTRUCTION,
puisque le natif ajoute et retire aux memes instants.

QUI LIT `HasHealBlockers` (les trois gates natifs, tous deja portes en STRUCTURE) :
  * `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed`   -> le SOIN ;
  * `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` -> la REPARATION ;
  * le gate de RESURRECTION (`operations/triggers/revive_effect.py`).
C'est la triade exacte de l'i2 (« cannot be revived, healed, repaired »).

RESIDU #927 FERME PAR #1077 : `MischiefMakersEffect` (`EffectType` 0x5bd = 1469), SECOND porteur de
cette base, est desormais inscrit au registre `EffectFactory` (`EFFECT_CLASSES["MischiefMakers"]`).
La degradation PERMISSIVE qui restait -- un porteur de 1469 soignable cote port alors que le natif
le refuse -- est levee.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..base import BaseEffect


@dataclass
class HealBlockingEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.HealBlockingEffect` -- la BASE. Aucune contribution de degat,
    aucune `CreateActiveCondition` : son seul comportement est l'inscription de son porteur au
    registre des bloqueurs de soin (`HealthComponent+0x78`), faite par `ApplyInternal` et defaite
    par `RevertInternal`.

    Cote port il n'y a rien a exposer de plus qu'un TYPE : `attack_query.has_heal_blockers` teste
    `isinstance(e, HealBlockingEffect)` sur les instances non consommees / non expirees du porteur.
    C'est le mirror EXACT de « le dict `+0x78` est non vide », puisque le natif y met et en retire
    aux memes instants que la vie de l'instance."""


@dataclass
class FuryOfTheAncientsEffect(HealBlockingEffect):
    """`IdunBattle.Entities.Effects.Loki.FuryOfTheAncientsEffect` (`EffectType` 0x528 = 1320), pose
    par le passif `FuryOfTheAncients` (`TriggeredAbilityType` 0x4df = 1247) de `bloodMephiston` sur
    CHAQUE cible de sa chaine, pour `TurnsFromRounds(effectTurns = 2)`.

    Le `.ctor` natif passe `0x4df` -- le `TriggeredAbilityType` SOURCE, pas son propre
    `EffectType` -- a la base, qui le convertit en `AbilityOrEffect` pour l'attribution. Les DEUX
    ids sont donc en jeu, et les confondre nommerait `ProtectorImperative` (`EffectType` 1247).

    i2 : « Can neither get their Health restored nor be revived »
    (`UnitEffects/FuryOfTheAncients_Description`)."""


@dataclass
class MischiefMakersEffect(HealBlockingEffect):
    """`IdunBattle.Entities.Effects.Loki.MischiefMakersEffect` (`EffectType` 0x5bd = 1469), pose par
    le passif `MischiefMakers` (`TriggeredAbilityType` 0x5bf = 1471) des Nurglings sur la cible de
    CHAQUE attaque normale, pour `TurnsFromRounds(nrOfRounds = 1)`. #1077.

    ⚠ **LA HIERARCHIE VIENT DE `classes.tsv`, ET LE PSEUDO-C DIT LE CONTRAIRE.** Le `.ctor` decompile
    est `IdunBattle.Entities.Effects.Loki.DeathwingEffect$$.ctor(this, 0x5bf)` -- or `DeathwingEffect`
    derive de `BaseEffect` et porte QUATRE overrides de DEGAT. Le corps est simplement DEDUPLIQUE par
    l'ICF (meme forme `<base>..ctor(this, AbilityOrEffect(<abilityType>), true)` pour trois `.ctor`
    distincts). La table des CLASSES tranche : `MischiefMakersEffect -> HealBlockingEffect`.

    ⚠ **DEUX ENUMS, DEUX ORDINAUX, ET LES DEUX SONT VALIDES DES DEUX COTES.** Le `.ctor` passe
    `0x5bf` = le `TriggeredAbilityType` SOURCE (1471 `MischiefMakers`), pas son propre `EffectType` ;
    lire `0x5bf` en `EffectType` nommerait `Drachnyen_ExtraAttack`, et lire `0x5bd` (l'EffectType de
    l'effet) en `TriggeredAbilityType` nommerait `MawClawsOfThyrax`. Aucune des deux confusions ne
    leverait d'erreur.

    i2 (`Abilities/MischiefMakers_CurrentLevelDescription`) : « Targets of the Nurglings' normal
    attacks cannot be revived, healed, repaired, or otherwise restore Health for 1 round. »"""
