"""Face TRIGGERED de `1195 TalonsOfTheEmperor` (`custoAtlacoya` << Atlacoya >>, Adeptus Custodes) --
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TalonsOfTheEmperor_UsedAbilitiesAbility`,
`TriggeredAbilityType.TalonsOfTheEmperor_UsedAbilities` = 0x532 = 1330. Residu **#521-r1**.

Elle ACCUMULE le niveau de l'effet `EffectType.TalonsOfTheEmperor_UsedAbilities` (0x58c = 1420), le
COMPTEUR que l'ability ACTIVE lit dans `...TalonsOfTheEmperorAbility$$GetExtraDamage`
(`runner/abilities/custodes.py::talons_used_abilities_level`). Sans ce fichier, le port LIT le
compteur depuis la capture mais ne le fait pas AVANCER : en simulation pure il reste fige a sa valeur
de depart, et l'extra damage est faux des le 2e cast d'ability allie.

i2 (1195) : << This attack deals +{extraDmg} Damage **for each time a friendly Character has used an
active ability this battle**. >> -- le << for each time >> est CE fichier ; le << +{extraDmg} >> est
`GetExtraDamage`, deja porte (#521).

## 1. Le CHEMIN DE MONTAGE : `GetPassiveHelperAbility`, un CINQUIEME registre

`custoAtlacoya` ne porte PAS 1330 dans son kit : ses `passiveAbilities` valent `['DaughterOfTheAbyss']`
et ses `activeAbilities` `['TalonsOfTheEmperor']`. Le natif la monte par un dictionnaire statique
DISTINCT des quatre chemins deja portes (trait / passiveAbility / activeAbility DERIVEE / relique) :

```
IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities(entity, config, activeState,
                                                                  passiveState, tertiaryState)
    config@+0xa8 (PassiveAbilities) -> TriggeredAbilityComponent.TryAdd(id, passiveState, 2)
    config@+0xb0 (TertiaryAbility)  -> TriggeredAbilityComponent.TryAdd(id, tertiaryState, 3)
    config@+0xa0 (ActiveAbilities)  -> UnitFactory$$AddActiveAbility(aa, activeState, passiveState,
                                                                     actives, triggered, i == 0)

IdunBattle.Entities.Factories.UnitFactory$$AddActiveAbility(...)
    ActiveAbilityComponent.Add(actives, aa, activeState, hierarchy)
    helper = StaticBattleRules.ActiveAbility.GetPassiveHelperAbility(aa)      # Nullable
    if (helper.HasValue)
        TriggeredAbilityComponent.TryAdd(triggered, helper.Value, **passiveState**, 0)
```

`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$GetPassiveHelperAbility`
lit le champ statique `<StaticBattleRules.ActiveAbility statics>+0x78` -- un
`Dictionary<ActiveAbilityType, TriggeredAbilityType>` peuple par le `.cctor` de la meme classe, et il
compte **SIX** entrees, transcrites VERBATIM dans `PASSIVE_HELPER_ABILITY_TRIGGERS`
(`dispatch/registry.py`). C'est un dict AUTRE que celui des triggered-abilities DERIVEES
(`...$$GetDerivedTriggeredAbilities`, statics+0x30) -- confondre les deux ferait ecrire 1195 dans un
registre ou le natif ne l'a pas mis. La CLE de la table native est bien `0x4ab = 1195`.

⚠ L'etat d'ability passe au `TryAdd` est le **`passiveAbilityState`**, pas l'actif : une variable de
config lue par le behaviour du helper s'indexerait sur le niveau des PASSIVES du porteur. Sans
observable ici (le behaviour n'a aucun `ConfigVar`, cf. SS 3), mais c'est le litteral natif.

## 2. `...TalonsOfTheEmperor_UsedAbilitiesAbility$$CreateTrigger`

Slots `DSLFactory` (`this@+0x28`) : `+0x78 Behaviors`, `+0x80 Formulas`, `+0x88 Triggers`,
`+0x90 Selectors` ; slots `DSLSelectors` : `+0x30 Owner`, `+0x48 Caster` (l'ACTEUR de l'event).

```
On( 0xe = EventTriggerType.UnitPostAbility, ownerNeedsToBeAlive = 1 )
& AreFriends( Owner@+0x30, actor@+0x48, comparisonType = 0, anyEntity = 0 )
& ( HasTrait(actor@+0x48, 0x10 = UnitTrait.Hero)
    & !HasTrait(actor@+0x48, 0x419 = UnitTrait.MachineOfWar) )
& IsActiveAbilityCountedAsUsed( isPreAbilityTrigger = 0 )
```

C'est TERME POUR TERME le trigger de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ExtraDamageAbility$$CreateTrigger`
-- et pour cause : IL2CPP a **DEDUPLIQUE les deux corps**, dont le proprietaire unique dans la table
de symboles du build `rnca9r7q6c` est celui de TalonsOfTheEmperor. Le symbole
`FuelledByFury_ExtraDamageAbility$$CreateTrigger` est ABSENT de `ghidra/functions.tsv` : c'est le faux
negatif structurel du `CLAUDE.md` (`L'ABSENCE d'une methode dans les tables ne prouve RIEN`), pas une
methode manquante.

- `On(0xe)` est le DERNIER evenement d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
  (`0x2b` -> execution -> `0xb` -> `0xc` -> `0xe`), emis par les DEUX voies du port
  (`triggers/dispatch/ability.py::unit_post_ability_triggers`, #120) -- y compris pour l'attaque
  NORMALE, qui EST une active ability cote natif. C'est exactement ce que le gate
  `IsActiveAbilityCountedAsUsed` filtre.
- `ownerNeedsToBeAlive = 1` (3e argument litteral d'`IdunBattleLogic.Entities.DSLTriggers$$On`) ->
  `fire_on_death` reste a son defaut FAUX.
- `HasTrait(actor, Hero) & !HasTrait(actor, MachineOfWar)` = le << friendly **Character** >> de l'i2 :
  une machine de guerre alliee qui caste ne compte PAS. Les deux noeuds sont mirrores separement,
  comme le natif les pose.
- `AreFriends(Owner, actor)` compare les EQUIPES, sans aucun `!AreEqual` : Atlacoya castant sa PROPRE
  active compte (elle est `Hero` et sa propre alliee).
- `IsActiveAbilityCountedAsUsed(isPreAbilityTrigger = 0)` -- mirror UNIQUE dans
  `loki/fuelled_by_fury.py::is_active_ability_counted_as_used` (branche `false`, seuil `Direct(1)`).
  On DELEGUE : un 2e port de la meme fonction native divergerait en silence.

## 3. `...TalonsOfTheEmperor_UsedAbilitiesAbility$$CreateBehaviour`

```
AddEffectOrIncreaseLevel( Behaviors@+0x78, 0x58c = 1420,
                          abilityState = BaseTriggeredAbility.get_AbilityStateReference(this),
                          source  = Owner@+0x30,
                          targets = Owner@+0x30,
                          level   = Formulas@+0x20,
                          maxLevel = NULL )
```

- Le natif appelle ICI la factory COMPOSITE `IdunBattleLogic.Entities.DSLBehaviors$$AddEffectOrIncrease
  Level` (elle alloue un `ForeachBehaviour(targets, Func)` dont le lambda construit, PAR ELEMENT,
  `If(HasEffect, IncreaseEffectLevel, AddEffect)`) -- la ou FuelledByFury ecrit les trois noeuds A LA
  MAIN. Meme arbre, deux ecritures ; le port passe par le helper `add_effect_or_increase_level`, qui
  EST le mirror de cette factory.
- `Formulas@+0x20` : `IdunBattleLogic.Entities.DSLFormulas$$.ctor` met en cache CINQ noeuds constants
  -- `+0x18 = Direct(0)`, `+0x20 = Direct(1)`, `+0x28 = Direct(2)`, `+0x30 = Direct(100)`,
  `+0x38 = Direct(-1)`. Le slot lu est le `1` -> increment **+1** par declenchement.
- `maxLevel = NULL` -> **AUCUN CAP** (le clamp d'`IdunBattle.Operations.IncreaseEffectLevelOperation$$
  Execute` est desactive), contrairement a TerrifyingCrescendo (`buffMaxLevel = 6`). L'i2 dit
  << for each time ... this battle >>, sans << up to >>.
- L'options-struct de la branche `AddEffect` du lambda ne porte pas de `TurnsFromRounds` -> duree 0 =
  PERMANENT cote port, et le niveau de la 1re pose vaut l'increment (1).
- source == targets == `Owner@+0x30` : le compteur vit sur le PORTEUR (Atlacoya), pas sur l'acteur.

## 4. Frontiere DSL/imperatif (#149)

Artefact natif = `CreateTrigger` + `CreateBehaviour` -> le behaviour est un ARBRE DSL
(`Foreach(If(HasEffect, IncreaseEffectLevel, AddEffect))`), monte par le helper de factory ; les
feuilles restent imperatives (`IncreaseEffectLevelOperation`, `AddEffectOperation`). Les predicats du
`CreateTrigger` sont collapses dans `matches` (doctrine des triggers, cf. `fuelled_by_fury.py`).

## 5. Ce qui n'entre PAS ici

1330 est une TRIGGERED-ability : elle n'entre ni dans `ABILITY_CLASSES`, ni dans `TARGETING_OPTIONS`,
ni dans `ABILITY_ATTACK_TYPE` -- ces trois registres ne concernent que les abilities ACTIVES (le
gate `ActiveAbilityOperation$$IsInvalidTarget` ne s'applique qu'a un cast joueur). Le masque de 1195,
lui, est pose par `runner/abilities/custodes.py` depuis #521.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import add_effect_or_increase_level
from .....entities.selectors.tiles import Caster
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.effect_type import EffectType
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, _unit_trait_names
# FORME B (`import <module>` + acces attributaire) et non `from ... import <nom>` : c'est la seule
# des trois formes qui reste PATCHABLE (`monkeypatch.setattr("...fuelled_by_fury.is_active_ability
# _counted_as_used", ...)`), cf. la regle << HISSER, OUI -- MAIS EN FORME B >> du CLAUDE.md.
from . import fuelled_by_fury as _fbf

#: `EffectType.TalonsOfTheEmperor_UsedAbilities` = 0x58c = 1420 -- le COMPTEUR d'abilities actives
#: alliees. C'est le MEME type que lit `runner/abilities/custodes.py::talons_used_abilities_level`.
TOTE_USED_ABILITIES = int(EffectType.TalonsOfTheEmperor_UsedAbilities)        # 0x58c = 1420
#: Nom d'`EffectType` tel qu'il arrive dans la capture live (`decisionView.units[].effects[].name`) --
#: c'est par ce NOM que `EffectsOwnedComponent` indexe, jamais par l'ordinal.
TOTE_USED_ABILITIES_NAME = "TalonsOfTheEmperor_UsedAbilities"
#: `TriggeredAbilityType.TalonsOfTheEmperor_UsedAbilities` = 0x532 = 1330 -- la VALEUR du dict
#: `GetPassiveHelperAbility`. L'ordinal 1330 nomme AUTRE CHOSE dans l'enum voisin
#: (`EffectType.TzeentchsFirestormSecondCircle`) : le NOM tranche, jamais l'entier.
TALONS_USED_ABILITIES_ABILITY = TriggeredAbilityType.TalonsOfTheEmperor_UsedAbilities       # 1330
#: `ActiveAbilityType.TalonsOfTheEmperor` = 0x4ab = 1195 -- la CLE du dict `GetPassiveHelperAbility`,
#: et la cle gameconfig sous laquelle le registre l'inscrit.
TALONS_OF_THE_EMPEROR = ActiveAbilityType.TalonsOfTheEmperor                                # 1195
#: Cle du registre `PASSIVE_HELPER_ABILITY_TRIGGERS` = le NOM gameconfig de l'ability ACTIVE porteuse
#: (`units.activeAbilities` / `UnitConfiguration.ActiveAbilities`).
TALONS_OF_THE_EMPEROR_ID = "TalonsOfTheEmperor"

_ON_UNIT_POST_ABILITY = int(EventTriggerType.UnitPostAbility)                # 0xe = 14
_HERO = UnitTrait(int(UnitTrait.Hero)).name                                  # 0x10 = 16   -> "Hero"
_MACHINE_OF_WAR = UnitTrait(int(UnitTrait.MachineOfWar)).name                # 0x419 = 1049


def talons_used_abilities_tree():
    """Mirror 1:1 de `...TalonsOfTheEmperor_UsedAbilitiesAbility$$CreateBehaviour` :
    `AddEffectOrIncreaseLevel(0x58c, AbilityStateReference, source = Owner@+0x30,
    targets = Owner@+0x30, level = Formulas@+0x20 = Direct(1), maxLevel = NULL)`.

    `Caster()` = `Owner@+0x30` : dans un `TriggeredAbility`, `entities_from_state(state, owner, ...)`
    fait du porteur le caster -- c'est la meme convention que `fuelled_by_fury_tree()`.
    `max_level=None` = le `maxLevel` NULL natif (AUCUN clamp)."""
    return add_effect_or_increase_level(
        TOTE_USED_ABILITIES, TOTE_USED_ABILITIES_NAME, Caster(),
        amount=Const(1), max_level=None)


def _team_of(state: State, unit_id) -> Optional[int]:
    """L'equipe d'une entite -- le substrat d'`AreFriends`. Meme lecture que
    `fuelled_by_fury.py::_team_of` (deux modules-feuilles, aucune dependance croisee sur ce point)."""
    e = state.get_entity(unit_id) if unit_id is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


class TalonsOfTheEmperorUsedAbilitiesAbility(TriggeredAbility):
    """`...TalonsOfTheEmperor_UsedAbilitiesAbility` -- `On(UnitPostAbility = 0xe, alive = 1)
    & AreFriends(Owner, actor) & HasTrait(actor, Hero) & !HasTrait(actor, MachineOfWar)
    & IsActiveAbilityCountedAsUsed(false)` -> `AddEffectOrIncreaseLevel(1420, +1, SANS cap)` sur le
    PORTEUR. Cf. l'en-tete de module pour les deux arbres et le chemin de montage.

    Rail = `PASSIVE_HELPER_ABILITY_TRIGGERS['TalonsOfTheEmperor']` (mirror de
    `StaticBattleRules.ActiveAbility$$GetPassiveHelperAbility`), et NON `ABILITY_TRIGGERS` (le porteur
    n'a pas 1330 en `passiveAbilities`) ni `ACTIVE_ABILITY_TRIGGERS` (autre dict natif)."""
    event_id = _ON_UNIT_POST_ABILITY                                  # On(0xe)
    TRIGGERED_ABILITY_ID = TALONS_USED_ABILITIES_ABILITY              # 1330

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        caster = ev.actor_id                     # `actor@+0x48` = l'acteur de l'ability qui se ferme
        if caster is None:
            return False
        my_team = _team_of(state, self.owner_id)               # `AreFriends(Owner@+0x30, actor@+0x48)`
        if my_team is None or _team_of(state, caster) != my_team:
            return False
        traits = _unit_trait_names(state, caster)
        if _HERO not in traits:                                # `HasTrait(actor, 0x10 = Hero)`
            return False
        if _MACHINE_OF_WAR in traits:                          # `!HasTrait(actor, 0x419 = MachineOfWar)`
            return False
        # `IsActiveAbilityCountedAsUsed(isPreAbilityTrigger = 0)` -- foyer UNIQUE (mirror de
        # `IdunBattleLogic.Entities.DSLTriggers$$IsActiveAbilityCountedAsUsed`, branche `false`).
        return _fbf.is_active_ability_counted_as_used(state, caster, ev.ability_type)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        talons_used_abilities_tree().execute(entities_from_state(state, self.owner_id, None), ectx)
        lvl = None
        for n, p in ectx.emitted:
            if n in ("IncreaseEffectLevel", "AddEffect"):
                lvl = p.get("level")
        return {"ability": TALONS_OF_THE_EMPEROR_ID, "unit": int(self.owner_id),
                "caster": int(ev.actor_id), "ability_type": ev.ability_type,
                "effect": TOTE_USED_ABILITIES, "level": lvl, "on_event": int(ev.event_id)}
