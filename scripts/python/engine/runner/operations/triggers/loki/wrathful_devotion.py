"""`WrathfulDevotion` (passif de `worldTerminator` << Wrask >>, `TriggeredAbilityType` 0x4be = 1214)
-- UNE triggered-ability native, DEUX faces de declenchement, UN seul `CreateShield`.

i2 (gameconfig, verbatim) : << When Wrask arrives from Deep Strike or defeats an enemy in melee, he
and adjacent friendly Chaos units gain a Shield with 2910 Health for 1 round. >>

================================================================================================
RE (decompile ghidra + DESASSEMBLAGE, build `rnca9r7q6c`) -- decompile = verite
================================================================================================
`classes.tsv` : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WrathfulDevotionAbility :
IdunBattle.Entities.Abilities.BaseTriggeredAbility`. La table de methodes de la classe (bloc de
`MethodInfo*` contigu, lu a l'octet dans le PE) porte EXACTEMENT CINQ entrees, et pas une de plus :

    <.ctor>            corps TRIVIAL, fondu par l'ICF (`xor edx,edx ; jmp Object..ctor`) -- il
                       n'appelle AUCUN `IdunBattle.Core.Services.TargetingOptions$$.ctor`, ce qui
                       est la forme attendue d'une TRIGGERED (le masque de ciblage est une donnee
                       des ACTIVES, cf. `ABILITY_CLASSES`)
    $$CreateTrigger
    $$CreateBehaviour
    $$GetTargets
    $$GetOtherTargets

plus le `<>c__DisplayClass1_0` (son `.ctor` trivial + `b__0` + `b__1`). ⚠ Sa VOISINE IMMEDIATE dans
le meme bloc, `WraithcannonAbility`, surcharge `$$CannotBeGuaranteedKilled` et
`$$CreateSimulationBehaviour` -- `WrathfulDevotionAbility`, elle, NE LES SURCHARGE PAS. Lire le bloc
et pas seulement les symboles voisins est ce qui separe les deux.

## `...WrathfulDevotionAbility$$CreateTrigger` -- les DEUX faces

```
  ( On(EventTriggerType.UnitDefeated = 0x36, ownerNeedsToBeAlive: 1)
    & get_OwnerIsActor
    & IsDefeatedByMeleeAttack(Target@DSLSelectors+0x60, countRevived: 0, countResurrected: 1) )
| ( On(EventTriggerType.UnitBecameTargetable = 0x3b, ownerNeedsToBeAlive: 1)
    & get_OwnerIsTarget
    & CurrentAbilityIs(AbilityOrEffect((EffectType)0x40b = TeleportStrike_TeleportingIn)) )
```

⚠⚠ **L'IMMEDIAT `0x40b` EST UN `EffectType`, ET RIEN NE LE DIT DANS LE PSEUDO-C.** Ghidra efface
l'argument de `IdunBattle.Core.AbilityOrEffect$$op_Implicit` ; le desassemblage donne
`lea rcx,[rsp+0x50] ; mov edx, 0x40b ; call <op_Implicit>`, et la CIBLE de ce `call` tranche la
surcharge parmi les QUATRE homonymes (`frida/methods.tsv`, resolus a l'ADRESSE) :

    op_Implicit(triggeredAbility: TriggeredAbilityType)   <- ce que le voisin de forme ecrirait
    op_Implicit(activeAbility:    ActiveAbilityType)
    op_Implicit(effect:           EffectType)             <- **CELLE-CI**
    op_Implicit(abilityType:      AbilityType)

Et l'ordinal 1035 est VALIDE dans les trois espaces, ou il nomme trois choses SANS RAPPORT :
`EffectType` 1035 = `TeleportStrike_TeleportingIn`, `TriggeredAbilityType` 1035 =
`UnstoppableFerocity`, `ActiveAbilityType` 1035 = `PlagueWind`. Recopier le voisin (qui ecrit un
`TriggeredAbilityType` sur SA PROPRE ability, cf. `MartialSuperiority`/`CursedPlagueBell`) aurait
donc pose un gate parfaitement silencieux et parfaitement faux.

## `...WrathfulDevotionAbility$$CreateBehaviour(abilityState, triggerType)`

```
    amount  = AbilityConfiguration.GetVariableForLevel(AbilityVariableType.shieldHp = 0x27,
                                                       abilityState)
    targets = Owner@+0x30
              op_Addition UnitsWithTrait( AdjacentFriends(Owner@+0x30, unique: 1,
                                                          UnitSelectionType.OnlyAliveAndTargetable = 3),
                                          UnitTrait.Chaos = 0x7ea,
                                          UnitSelectionType.OnlyAliveAndTargetable = 3 )
    shield  = DSLBehaviors.CreateShield(unitSelector: targets,
                                        amount:       DSLFormulas.Direct(amount),
                                        source:       AbilityOrEffect((TriggeredAbilityType)this.Id),
                                        turns:        DSLFormulas.TurnsFromRounds(1),
                                        createdByEffect: Nullable VIDE,
                                        stackable:    true)

    switch (triggerType) {
      case EventTriggerType.UnitDeath = 0:                  // <-- DEAD, cf. ci-dessous
          return shield + Foreach(targets, b__0)
      case EventTriggerType.UnitBecameTargetable = 0x3b:
          return shield + Foreach(targets, b__1)
      default:                                              // == UnitDefeated 0x36, la face A
          return shield
    }

    b__0(target) = If( NOT HasEffect(target, EffectType.WrathfulDevotionKilled_Visual = 0x517,
                                     onlyActive: 0, EffectTargetType.Both = 6),
                       AddEffect(0x517, AbilityStateReference, targets, DSLFormulas.Direct(1)) )
    b__1(target) = <idem avec EffectType.WrathfulDevotionTeleported_Visual = 0x518>
```

Le `source` du `CreateShield` n'est PAS un immediat : le desassemblage montre `call <getter +0x10>`
(un corps trivial `mov eax,[rcx+0x10] ; ret`, que Ghidra attribue a
`CenterSpace.Free.MersenneTwister$$get_Count` -- ICF) puis `mov edx, eax` et le `call` vers la
surcharge `op_Implicit(triggeredAbility: **TriggeredAbilityType**)`. C'est donc bien `this.Id`, et
les DEUX `op_Implicit` de la MEME classe empruntent DEUX surcharges DIFFERENTES.

================================================================================================
LE VERDICT DEAD, ET IL EST STRUCTUREL -- pas un << je n'ai pas trouve de porteur >>
================================================================================================
**La branche `triggerType == EventTriggerType.UnitDeath (0)` de `$$CreateBehaviour` est
INATTEIGNABLE**, donc `b__0` et l'effet `0x517 WrathfulDevotionKilled_Visual` avec elle. Trois
lectures, toutes verifiees, et aucune n'est une absence :

 1. `$$CreateTrigger` n'appelle `IdunBattleLogic.Entities.DSLTriggers$$On` que DEUX fois, avec
    `mov edx, 0x36` et `mov edx, 0x3b` (immediats LUS au desassemblage). Jamais `0`.
 2. `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetEventTriggers` construit la liste des
    evenements abonnes en VISITANT CET ARBRE (slot `IEventTriggersProvider` +0x198), et journalise
    une ERREUR si la liste sort vide -- c'est bien elle, et rien d'autre, qui decide a quels
    evenements l'ability est inscrite.
 3. `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger` passe l'
    `EventTriggerType` **de l'evenement courant** a `...BaseTriggeredAbility$$ExecuteBy`, qui le
    relaie tel quel au slot virtuel `$$CreateBehaviour` (`+0x2e8`).

=> `triggerType` appartient a `{UnitDefeated, UnitBecameTargetable}`, jamais a `{UnitDeath}`. La
face << kill en melee >> retombe donc sur la branche `default` : **elle pose le bouclier SEUL, sans
aucun marqueur visuel**. C'est le residu d'un `On(UnitDeath)` remplace par `On(UnitDefeated)` dans
`$$CreateTrigger` sans que le `switch` de `$$CreateBehaviour` ait suivi. Grave par
`test_936_wrathful_devotion_offline.py` (dont l'etage binaire RE-DERIVE les deux immediats `On(x)`
depuis le PE : il rougira si un build futur rebranche `On(UnitDeath)`).

================================================================================================
LES DEUX FACES DECISION -- `$$GetTargets` / `$$GetOtherTargets`, SANS CONTENU PROPRE
================================================================================================
```
$$GetTargets      = Owner@+0x30 op_Addition UnitsWithTrait(AdjacentFriends(Owner@+0x30, 1, 3),
                                                           UnitTrait.Chaos, 3)
$$GetOtherTargets =                         UnitsWithTrait(AdjacentFriends(Owner@+0x30, 1, 3),
                                                           UnitTrait.Chaos, 3)
```
soit LITTERALEMENT le selecteur de `$$CreateBehaviour`, et sa moitie sans le porteur. Ces deux
faces n'ont donc AUCUNE decision propre a porter (meme situation que `$$GetInitialTarget` de
`SavageKiller`) : le port materialise le selecteur UNE fois, dans `wrathful_devotion_targets`, et
les deux symboles natifs sont cites sur elle. Elles ne portent NI degat NI cout, donc rien n'en
descend vers la couche `playbook`/`prediction`.

================================================================================================
CE QUE LE PORT MATERIALISE, ET CE QU'IL NE PEUT PAS
================================================================================================
UNE SEULE classe Python pour les deux faces, et c'est le natif qui l'impose : il n'y a qu'UNE
`WrathfulDevotionAbility`, donc UN compteur `GetTimesTriggeredThisPhase` (le cap de phase
d'`EvaluateAbilityTrigger`, porte par `dispatch/core.py` sous la cle `type(entry).__name__`). Deux
classes donneraient DEUX compteurs. La repartition des deux evenements entre `event_id` et
`event_ids` est de la PLOMBERIE du dispatch, pas une donnee native.

**LE CANAL `On(UnitBecameTargetable)` EST AJOUTE PAR CETTE TRANCHE** (#936) -- sans lui la face B,
celle que l'i2 nomme en PREMIER, serait restee inerte. Le point d'emission est LU au decompile, en
queue d'`IdunBattle.Operations.RemoveEffectOperation$$Execute` :

    if (EffectsDatabase.GetEffect(effectComponent.Type@+0x58) is
        IdunBattle.Entities.Effects.Common.UntargetableEffect)  { On(0x3b) ; Inform(5) }

Le `Il2CppClass*` teste n'est pas devine : le MEME slot global est lu par trois fonctions, dont
`IdunBattle.Core.Services.EffectsDatabase.<>c$$<InitializeEffects>b__14_576`, qui l'alloue et
appelle `IdunBattle.Entities.Effects.Common.UntargetableEffect$$.ctor` -- le nom sort du binaire,
pas d'une deduction. Cote port le domaine correspondant existe deja et est le foyer unique de ce
predicat : `entities/effects/aura_selectors.py::UNTARGETABLE_EFFECT_TYPES` (les feuilles
d'`ATeleportingEffect` reellement portees). Voir `operations/remove_effects.py` et
`triggers/dispatch/move_death.py::unit_became_targetable_triggers`.

RESIDUS EXPLICITES -- chacun est une MESURE, pas une supposition :

 * **marqueur << defaite par attaque de MELEE >>** : `IsDefeatedByMeleeAttack` lit un CHAMP
   persistant pose sur la victime (`UnitsDefeatedByMeleeAttackSelector$$IsValidUnit`) ; le port n'a
   aucun canal melee sur le vecteur `On(UnitDefeated)` (`unit_defeated_triggers` ne threade pas
   `ranged`). Il l'approxime POSITIONNELLEMENT par `_is_ranged_position` -- EXACTEMENT le meme
   collapse, et le meme foyer, que `DawnBladeHealAbility`, l'autre consommateur porte de ce nœud.
   La degradation est du bon cote : omettre le gate rendrait le trigger PERMISSIF.
 * **`countRevived = 0` / `countResurrected = 1`** : les deux drapeaux d'
   `UnitsDefeatedByMeleeAttackSelector` (`HasFlag(unit, 0x14)` / `HasFlag(unit, 0xe)`) ne sont pas
   modelises -- dans tout regime porte, une victime REVIVEE ne parvient pas jusqu'a la sequence de
   mort (la garde revive de `damage.py::_kill_unit_operation` court-circuite apres
   `On(PreUnitDeath)`), donc la seule branche atteignable est `HealthComponent.IsDead`. Meme
   lecture, meme mot, que `dawn_blade.py`.
 * **`stackable: true`** (7e argument de `CreateShield`) : le port ne modelise pas ce drapeau ; sa
   feuille appelle `ShieldComponent.add_or_update_shield`, qui CUMULE deja a source et duree
   egales et cree une instance neuve sinon. Ecart preexistant du foyer `CreateShield`, pas de
   cette tranche (`ArcaneShield` est dans le meme cas).
 * **`AddEffect(..., targets, ...)` et non `AddEffect(..., target, ...)`** : le lambda recoit un
   `target` mais ne s'en sert QUE pour le `HasEffect` du gate -- l'`AddEffect` qui suit repose sur
   le selecteur COMPLET capture par le `<>c__DisplayClass1_0` (`+0x18`). Le port transcrit cette
   forme telle quelle (cf. `_pose_visual`). Effet net identique a << poser sur tous >>, le gate
   << deja present >> d'`AddEffectOperation` absorbant les re-poses.
 * **`unique: 1`** d'`AdjacentFriends` n'a pas de pendant explicite cote port : `_within` ajoute au
   plus UNE fois chaque unite (`break` des qu'un pied tombe dans l'anneau), donc la
   deduplication est structurelle.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.selectors.accessors import Owner
from .....entities.selectors.units import AdjacentFriends, Union, UnitsWithTrait
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_selection_type import UnitSelectionType
from ....abilities.base import convert_rounds_to_turns
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, CreateShield
from ....components import StatsComponent, UnitComponent, has_effect_of_type
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, _is_ranged_position, triggered_ability_state

#: Cle gameconfig (`variables.shieldHp`, 65 paliers, `variablesAffectedByRarityBonus`).
ABILITY_ID = "WrathfulDevotion"
WRATHFUL_DEVOTION = int(TriggeredAbilityType.WrathfulDevotion)          # 0x4be = 1214
#: `AbilityConfiguration$$GetVariableForLevel(cfg, 0x27, abilityState, 0)`.
SHIELD_HP_KEY = "shieldHp"                                             # AbilityVariableType 0x27
#: `UnitsWithTrait(..., 0x7ea, 3)` -- pseudo-trait DERIVE de la GrandAlliance (`GrandAlliance$$
#: GetTrait` : "Chaos" -> 2026), qu'aucun kit ne porte dans sa liste `traits`. Le substrat du port
#: l'injecte par `entity_trait_names`, donc `ctx.has_trait` le voit.
CHAOS_TRAIT = UnitTrait.Chaos                                          # 0x7ea = 2026
#: Le DERNIER argument des DEUX selecteurs natifs.
SELECTION = UnitSelectionType.OnlyAliveAndTargetable                   # 3
#: `TurnsFromRounds(1)` -- le 4e argument de `CreateShield` (ROUNDS, donc converti).
SHIELD_ROUNDS = 1
#: `DSLFormulas.Direct(1)` -- le 4e argument de l'`AddEffect` du lambda. Une `IAmountFormula` brute,
#: PAS un `TurnsFromRounds` : la duree est deja en TOURS et n'est pas convertie.
VISUAL_TURNS = 1

_ON_UNIT_DEFEATED = int(EventTriggerType.UnitDefeated)                  # 0x36 = 54 -- face A
_ON_UNIT_BECAME_TARGETABLE = int(EventTriggerType.UnitBecameTargetable)  # 0x3b = 59 -- face B
#: `CurrentAbilityIs(AbilityOrEffect((EffectType)0x40b))` -- l'immediat efface par le pseudo-C, et
#: la surcharge d'`op_Implicit` tranchee a l'ADRESSE de son call-site (cf. l'en-tete).
_TELEPORT_STRIKE_TELEPORTING_IN = int(EffectType.TeleportStrike_TeleportingIn)   # 0x40b = 1035
#: Le marqueur de la face B (`b__1`), le SEUL des deux qui soit atteignable.
TELEPORTED_VISUAL = int(EffectType.WrathfulDevotionTeleported_Visual)   # 0x518 = 1304
#: Le marqueur de la branche MORTE (`b__0`, `triggerType == UnitDeath`). Nomme ici pour que le
#: verdict soit CITABLE et gardable ; AUCUN site du port ne le pose -- c'est le verdict, pas un
#: oubli (cf. l'en-tete, et `test_936_wrathful_devotion_offline.py`).
KILLED_VISUAL_DEAD = int(EffectType.WrathfulDevotionKilled_Visual)      # 0x517 = 1303


def wrathful_devotion_targets():
    """Le selecteur que le natif ECRIT TROIS FOIS -- dans `$$CreateBehaviour`, dans `$$GetTargets`,
    et (sans son premier terme) dans `$$GetOtherTargets` -- materialise UNE fois ici :

        Owner@+0x30 op_Addition UnitsWithTrait( AdjacentFriends(Owner@+0x30, unique: 1,
                                                                OnlyAliveAndTargetable = 3),
                                                UnitTrait.Chaos = 0x7ea,
                                                OnlyAliveAndTargetable = 3 )

    `AdjacentFriends` : la surcharge appelee est la variante A
    `IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(this, unit, unique, selectionType)`
    (tranchee a l'ADRESSE du `call`, pas au pseudo-C -- la variante B a la MEME arite et son 3e
    argument est une ANCRE GEOMETRIQUE, pas un booleen). Elle propage `selectionType` aux DEUX
    etages, d'ou le `selection_type=3` porte ici.

    `reference=Owner()` est EXPLICITE bien que le defaut (`ctx.caster`) coincide : pour une
    triggered-ability `Owner == Caster`, mais c'est le CENTRE qui est la reference d'equipe cote
    natif (`Friends(reference = X, ...)`) -- l'ecrire evite qu'un futur threadage de `caster`
    distinct change silencieusement le camp selectionne.

    Le porteur n'est PAS dans l'anneau (`AdjacentTilesSelector$$Select` retranche toute l'empreinte
    du centre), donc l'`op_Addition` ne peut pas produire de doublon."""
    voisins = AdjacentFriends(Owner(), reference=Owner(), selection_type=int(SELECTION))
    return Union(Owner(), UnitsWithTrait(voisins, int(CHAOS_TRAIT), int(SELECTION)))


def shield_hp(state: State, owner_id: int) -> int:
    """`AbilityConfiguration$$GetVariableForLevel(cfg, AbilityVariableType.shieldHp = 0x27,
    abilityState, 0)`.

    `shieldHp` EST dans `variablesAffectedByRarityBonus` du gameconfig de `WrathfulDevotion` -> le
    multiplicateur de rarete s'applique (`ability_var` gate l'application sur cette liste).
    `triggered_ability_state` rend le couple (niveau, multiplicateur) sous lequel l'ability est
    MONTEE -- ici la voie PASSIVE (`worldTerminator.passiveAbilities = ['WrathfulDevotion']`).
    `0` si l'unite / son contexte / la variable manquent -> la feuille `CreateShield` est alors un
    no-op (`amount > 0` est sa garde, et celle d'`add_or_update_shield`)."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None or getattr(sc, "ctx", None) is None:
        return 0
    lvl, mult = triggered_ability_state(state, owner_id, ABILITY_ID)
    return int(ability_var(ABILITY_ID, SHIELD_HP_KEY, lvl, multiplier_pct=mult) or 0)


class WrathfulDevotionAbility(TriggeredAbility):
    """`WrathfulDevotionAbility` (triggered 0x4be = 1214, passif `worldTerminator`) -- cf. l'en-tete.

    UNE classe, DEUX evenements, DEUX faces :
      * FACE A `On(UnitDefeated)` -- Wrask ACHEVE un ennemi **en melee** -> bouclier ;
      * FACE B `On(UnitBecameTargetable)` -- Wrask sort du Deep Strike (l'effet
        `TeleportStrike_TeleportingIn` vient d'etre retire de LUI) -> bouclier **+ marqueur
        `WrathfulDevotionTeleported_Visual`**.

    ⚠ LES DEUX FACES N'ONT PAS LA MEME GATE, ET C'EST NATIF : la face A exige que le porteur soit
    l'ACTEUR (`get_OwnerIsActor`, donc le TUEUR) et que la victime ait ete defaite EN MELEE ; la
    face B exige que le porteur soit la CIBLE (`get_OwnerIsTarget`, donc celui dont l'effet part) et
    que l'effet retire soit exactement `TeleportStrike_TeleportingIn`. Recopier la gate d'une face
    sur l'autre eteindrait exactement une face sur deux.

    ⚠ ET ELLES N'ONT PAS LE MEME BEHAVIOUR : seule la face B pose un marqueur visuel. Ce n'est pas
    une dissymetrie inventee -- c'est le `switch (triggerType)` du natif, dont la troisieme branche
    (`UnitDeath`, celle qui poserait `WrathfulDevotionKilled_Visual`) est DEAD."""
    #: Le natif n'a qu'UN `CreateTrigger` ; la repartition entre les deux attributs est de la
    #: plomberie du dispatch (`dispatch/core.py` teste `event_id` PUIS `event_ids`). `event_id`
    #: porte la face A pour que les recenseurs qui ne lisent que cet attribut voient la face que
    #: l'on peut declencher sans effet prealable.
    event_id = _ON_UNIT_DEFEATED
    event_ids = (_ON_UNIT_BECAME_TARGETABLE,)
    #: `AbilityOrEffect((TriggeredAbilityType)1214)` -- ce que `BaseTriggeredAbility$$Execute` ecrit
    #: dans `CurrentAbility` (`AbilityEntities+0x60`) avant le behaviour, et ce que le
    #: `CreateShield` natif passe en `source`.
    TRIGGERED_ABILITY_ID = WRATHFUL_DEVOTION

    # -------------------------------------------------------------------------------- le trigger
    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """COLLAPSE du `CreateTrigger` (doctrine des triggers) : une disjonction de DEUX conjonctions
        que le dispatch a deja separees par `event_id`."""
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        # `ownerNeedsToBeAlive: 1` -- deja applique par le dispatch (`CanGetAbilityTrigger`), re-teste
        # ici parce que la face A s'evalue DANS la sequence de mort, ou l'owner peut lui-meme etre
        # en train de mourir (echange mortel).
        ouc = owner.get_component(UnitComponent)
        if ouc is not None and not ouc.alive:
            return False
        if int(ev.event_id) == _ON_UNIT_BECAME_TARGETABLE:
            return self._teleport_in_face(ev)
        return self._melee_kill_face(state, ev)

    # ------------------------------------------------------------------------------- face A / B
    def _melee_kill_face(self, state: State, ev: TriggerEvent) -> bool:
        """`get_OwnerIsActor & IsDefeatedByMeleeAttack(Target@+0x60, 0, 1)`.

        `unit_defeated_triggers` construit l'evenement avec `actor = killer` et
        `target = dying` -- le porteur doit donc etre l'ACTEUR (le tueur), et le nœud
        `IsDefeatedByMeleeAttack` porte sur le slot `Target`, c'est-a-dire la VICTIME."""
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False                                   # get_OwnerIsActor
        dying = ev.dying_id if ev.dying_id is not None else ev.target_id
        if dying is None or int(dying) == int(self.owner_id):
            return False
        victim = state.get_entity(int(dying))
        if victim is None:
            return False
        # `UnitsDefeatedByMeleeAttackSelector$$IsValidUnit` -- branche `HealthComponent$$IsDead`
        # (les deux drapeaux revive/resurrect ne sont pas modelises, cf. residus de l'en-tete).
        vuc = victim.get_component(UnitComponent)
        if vuc is not None and vuc.alive:
            return False
        # ... et le marqueur << defaite par une attaque de MELEE >>, approxime POSITIONNELLEMENT
        # (le champ natif n'a aucun canal sur ce vecteur) -- MEME foyer que `DawnBladeHealAbility`.
        return not _is_ranged_position(state, int(self.owner_id), int(dying))

    def _teleport_in_face(self, ev: TriggerEvent) -> bool:
        """`get_OwnerIsTarget & CurrentAbilityIs(AbilityOrEffect((EffectType)1035))`.

        Le vecteur est publie par `RemoveEffectOperation$$Execute`, dont l'`AbilityEntities` pose le
        PORTEUR de l'effet en `+0x10` (`Target@+0x60`) ET `+0x18` (`Owner@+0x30`) -- `OwnerIsTarget`
        y est donc vrai pour le porteur, et faux pour tout autre. Cote port c'est
        `_effect_vector_triggers(..., removing=True)` qui reconstruit cette struct : `target_id` =
        le porteur, `actor` VIDE.

        `CurrentAbilityIs` lit `AbilityEntities+0x60`, que la meme Operation remplit avec
        `AbilityOrEffect(effectComponent.Type)` -> canal `ev.triggering_ability` (et NON
        `ev.triggering_effect`, structurellement vide sur un RETRAIT, cf. #306).

        ⚠ Le port collapse les quatre champs de l'`AbilityOrEffect` natif en UN entier : un
        `TriggeredAbilityType 1035` (`UnstoppableFerocity`) arrivant par ce canal serait confondu
        avec l'`EffectType 1035` compare ici. Inerte : sur CE vecteur le canal ne porte jamais
        qu'un `EffectType` (c'est `RemoveEffectOperation` qui l'ecrit)."""
        if ev.target_id is None or int(ev.target_id) != int(self.owner_id):
            return False                                   # get_OwnerIsTarget
        ta = getattr(ev, "triggering_ability", None)
        return ta is not None and int(ta) == _TELEPORT_STRIKE_TELEPORTING_IN

    # -------------------------------------------------------------------------------- le behaviour
    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        amount = shield_hp(state, self.owner_id)
        if amount <= 0:
            return None                                    # garde `amount > 0` de la feuille
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `AbilityEntities` du behaviour : pour une triggered, `Owner == Caster == le porteur`
        # (`BaseTriggeredAbility$$Execute` s'execute sur son propre porteur). Le selecteur ne lit
        # QUE `Owner`, donc aucun autre slot n'a besoin d'etre threade.
        entities = entities_from_state(state, self.owner_id)
        targets = wrathful_devotion_targets()
        # `TurnsFromRounds(1)` -> `BattleQuery$$ConvertRoundsToTurns` (le decay du bouclier est
        # `EndTurnOperation$$RemoveOneTurnOnShields`, 1 par EndTurn = la cadence des TOURS).
        dur = convert_rounds_to_turns(state, SHIELD_ROUNDS)
        CreateShield(targets, amount, duration=dur, source=ABILITY_ID).execute(entities, ectx)
        shielded = [p for (n, p) in ectx.emitted if n == "CreateShield"]
        visual = None
        if int(ev.event_id) == _ON_UNIT_BECAME_TARGETABLE:
            visual = self._pose_visual(state, entities, ectx, targets)
        return {"ability": ABILITY_ID, "owner": int(self.owner_id), "amount": int(amount),
                "event": int(ev.event_id), "remaining": dur,
                "targets": [int(p.get("target")) for p in shielded],
                "shields": shielded, "visual": visual, "dsl": True}

    def _pose_visual(self, state: State, entities, ectx, targets) -> Optional[dict]:
        """`Foreach(targets, t => If(NOT HasEffect(t, 0x518, onlyActive: 0, Both = 6),
        AddEffect(0x518, AbilityStateReference, **targets**, Direct(1))))` -- mirror de `b__1`.

        Deux points transcrits TELS QUELS, parce que c'est ce que le natif ecrit :
          * le gate porte sur le `t` du `Foreach`, mais l'`AddEffect` porte sur le selecteur
            COMPLET capture par le `<>c__DisplayClass1_0` (`+0x18`) -- une seule cible depourvue du
            marqueur suffit donc a relancer la pose sur TOUTES ;
          * `HasEffect(..., onlyActive: 0, EffectTargetType.Both = 6)` = le foyer
            `components.has_effect_of_type` (qui ne filtre QUE `consumed`, et dont l'index est deja
            la cible de l'`AddEffect` -- les deux branches de `Both` y coincident).

        Un `AddEffect` sur une cible qui porte deja le marqueur est absorbe par le gate
        << deja present >> d'`AddEffectOperation` (`placed = False`), donc la re-pose est un no-op :
        l'etat final ne depend pas de l'ordre du `Foreach`.

        `source_from_target=True` : la surcharge 4-args
        `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect(effectType, abilityState, targets, turns)`
        -- celle du call-site, tranchee a l'ADRESSE (`0x180e9eb30`), face aux QUATRE homonymes --
        n'a PAS de parametre `source` : son corps passe litteralement `0` a
        `AddEffectBehaviour$$.ctor`, d'ou le fallback natif << la source EST la cible >>. Le port a
        deja ce drapeau pour cette surcharge exacte (cf. `RitesOfMorkai`, `stormboyz_strike`)."""
        ids = [int(u["id"]) for u in targets.evaluate(entities)
               if isinstance(u, dict) and u.get("id") is not None]
        if not any(not has_effect_of_type(state, uid, TELEPORTED_VISUAL) for uid in ids):
            return None                                    # tous marques -> le `If` refuse partout
        AddEffect(TELEPORTED_VISUAL, EffectType.WrathfulDevotionTeleported_Visual.name, targets,
                  duration_rounds=None, duration_turns=VISUAL_TURNS,
                  source_from_target=True).execute(entities, ectx)
        placed = [int(p.get("target")) for (n, p) in ectx.emitted
                  if n == "AddEffect" and p.get("placed")]
        return {"effect": TELEPORTED_VISUAL, "placed": placed, "turns": VISUAL_TURNS}
