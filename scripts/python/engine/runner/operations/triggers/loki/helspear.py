"""`Helspear` -- relique `R_Crit_Helspear`, `TriggeredAbilityType` 0x616 = 1558. UN SEUL porteur
autorise (`items/R_Crit_Helspear/allowedUnits`, LU) : `blackHaarken` << Haarken Worldclaimer >>,
HERO Black Legion, `kind = lineup`, DANS le pool rank 17. #1008.

⚠ **AUCUNE description i2** : ni `Abilities/Helspear_CurrentLevelDescription`, ni
`Abilities/Helspear_Name` n'existent dans `data/i2_en.json` (balayage cle ET valeur). Le seul
libelle est `items/R_Crit_Helspear/name = "Helspear"`. Le decompile est donc la SEULE source de
comportement ici -- il n'y a pas d'i2 a confronter, et donc pas non plus d'i2 sur laquelle se
tromper (piege #1006).

Variables gameconfig : `armorIgnored` = [685, 722, 759, 796, 833, 870, 907, 944, 981, 1018],
`nrOfUnits` = [8, 8, 7, 7, 6, 6, 5, 5, 4, 4].

===================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- DEUX classes natives pour UNE cle
===================================================================================================

Patron `LetTheGalaxyBurn` / `DaemonfleshPlate` / `ChaliceOfBaal` : deux `BaseTriggeredAbility`
DISTINCTES, a `CreateTrigger` differents, rangees sous la MEME cle de kit.

Slots lus : `DSLSelectors+0x30 Owner`, `+0x48 Caster`, `+0x60 Target(s)`.
`<ctx>+0x78 DSLBehaviors`, `+0x80 DSLFormulas`, `+0x88 DSLTriggers`, `+0x90 DSLSelectors`.

## 1. `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Helspear_BuffActiveAbility`

    CreateTrigger =
        On( 9 = EventTriggerType.Attack, ownerNeedsToBeAlive = 1 )
      & get_OwnerIsCaster
      & CurrentAbilityIs( AbilityOrEffect(ActiveAbilityType.HeraldOfTheApocalypse = 0x3fc) )

    CreateBehaviour(abilityState, triggerType) =
        AddEffect( EffectType.Helspear_IgnoreArmor = 0x62f, AbilityStateReference,
                   source = Owner@+0x30, targets = Target@+0x60, options = NULL )
      + AddEffect( EffectType.DespoiledGround = 0x5c4, AbilityStateReference,
                   source = Owner@+0x30, targets = Tiles(Target@+0x60), options = NULL )

⚠ **`0x3fc` A ETE QUALIFIE PAR L'ADRESSE DE SON `op_Implicit`, PAS PAR SON ORDINAL.** Le pseudo-C
perd le litteral (il part par `edx`) ; relu a l'assembleur, `mov edx, 0x3fc` precede un
`call` dont la cible est `IdunBattle.Core.AbilityOrEffect$$op_Implicit` **RVA `166a000`** =
la surcharge `activeAbility: ActiveAbilityType`. Les surcharges `triggeredAbility` (`1669f80`),
`effect` (`166a080`) et `abilityType` (`1669f30`) sont a des RVA DIFFERENTES. Sans ce controle,
`1020` nomme aussi `LivingLightning_MoveEffect` dans DEUX autres enums -- confusion silencieuse.
`HeraldOfTheApocalypse` est bien l'unique `activeAbilities` de `blackHaarken` (gameconfig).

⚠ L'assemblage est un `op_Addition`, PAS un `op_BitwiseAnd`. Les deux `AddEffect` sont donc joints
en SEQUENCE simple (aucun des deux ne gate l'autre).

## 2. `...Helspear_ResetActiveAbility`

    CreateTrigger =
        On( 0x36 = EventTriggerType.UnitDefeated, ownerNeedsToBeAlive = 1 )
      & get_OwnerIsActor
      & NOT IsSteppableUnit( Target@+0x60 )
      & NOT AreFriends( Owner@+0x30, Target@+0x60,
                        UnitTeamSelectionType.ByCurrentTeam = 0, anyEntity = false )
      & NOT TriggeringAbilityIs( AbilityOrEffect(ActiveAbilityType.HeraldOfTheApocalypse = 0x3fc) )
      & <DSLTriggers+0x58 = HasOwnersActiveAbilityBeenUsed>   <-- PORTE (#1008-r3), cf. plus bas

    GetNumDefeatedEnemiesCurrent() =
        GetPersistentData( AbilityOrEffect(TriggeredAbilityType.Helspear = 0x616),
                           Owner@+0x30, <literal statique> )

    CreateBehaviour(abilityState, triggerType) =
        AddPersistentData( AbilityOrEffect(0x616), Owner@+0x30, <literal>,
                           <DSLFormulas+0x20> = Direct(1) )
      + If( AmountIsEqualOrGreater( GetNumDefeatedEnemiesCurrent(),
                                    Get(ConfigVar(AbilityVariableType.nrOfUnits = 0x9a)) ),
            ResetActiveAbility( Owner@+0x30, allowUseless = true )
          + ClearPersistentData( AbilityOrEffect(0x616), Owner@+0x30, <literal> ),
            NULL )

**L'ORDRE EST LU** : l'INCREMENT est le terme de GAUCHE de l'`op_Addition` final, donc il
s'execute AVANT que le `If` ne relise le compteur. Le seuil porte sur le compteur **DEJA
incremente** -- meme forme que `VolummsMasterArtifice`, l'INVERSE de `DaemonfleshPlate` (qui teste
avant d'incrementer et compare a `n - 1`). Recopier le voisin decalerait le declenchement d'un kill.

Le reset est un `ClearPersistentData` (retire LA cle), pas un `SetPersistentData(..., 0)` :
`VolummsMasterArtifice` fait l'inverse. Les deux fabriques sont distinctes cote natif
(`abilities/behaviours/persistent_data.py`).

La cle de persistance est le literal `"helspear_defeat_count"` (`metadata/string_literals.tsv`
index 25558) -- le SEUL literal du binaire portant `helspear`, et le champ statique lu aux DEUX
sites (`<statics>+0xb8`) est le meme. Le port le nomme `_COUNTER_KEY`.

===================================================================================================
CRITERE DE L'EMETTEUR
===================================================================================================
* `On(9 = Attack)` : vecteur porte et peuple (`DaemonfleshPlate`, `Vitarus`, `ActOfFaith`...).
* `On(0x36 = UnitDefeated)` : vecteur porte et peuple -- et notamment par
  `IdunBattle.Operations.FleeOperation$$Execute`, chaine relue par #981 (cf.
  `loki/head_claimer.py`, le passif du MEME porteur). Aucune des deux inscriptions n'est
  registered-but-dead.

===================================================================================================
RESIDUS NOMMES
===================================================================================================
* ~~**`<DSLTriggers+0x58>` : SIXIEME conjoint du `CreateTrigger` du RESET, NON IDENTIFIE.**~~
  **FERME (#1008-r3, 2026-08-18) -- IDENTIFIE PAR SON NOM DE CHAMP, ET PORTE.** Le residu cherchait
  l'appariement par la TAILLE de classe (« il reste `<+0x50>` et `<+0x58>` pour `NoTrigger` et
  `HasActiveAbilityBeenUsedByOwner...`, sans que rien ne dise LEQUEL est LEQUEL ») et declarait
  `BLOCAGE: capteur`. Aucun capteur n'etait requis : le RPC `classFields` **deja en vol** nomme les
  champs, en lecture pure et sans runner. RE-MESURE du 2026-08-18, session 11, build `t6dpr4k06g` --
  `classFields("IdunBattleLogic.Entities", "DSLTriggers")` rend

      +0x40 True   +0x48 False   +0x50 IsOwnerEmpty   +0x58 HasOwnersActiveAbilityBeenUsed
      +0x60 No     +0x68 Never   +0x70 Yes

  Le NOM DE CHAMP est plus fort que le nom de classe cherche : c'est le nom que le jeu donne au
  slot, et il survit a un renumerotage. ⚠ Il refute AUSSI la premisse intermediaire du residu :
  `<+0x50>` n'est pas `NoTrigger` (c'est `IsOwnerEmpty`), donc l'enumeration « trois classes de
  taille 16 » ne pouvait pas trancher.

  SEMANTIQUE, LUE au corps de `IdunBattle.DSL.HasActiveAbilityBeenUsedByOwnerAbilityTrigger$$
  ShouldTrigger` (aucune deduction depuis le nom) :

      owner = <AbilityEntities.Owner>                      ; null -> throw
      comp  = owner.<ActiveAbilitiesComponent>             ; comp.<+0x20> null -> throw
      foreach (a in comp.<+0x20>)                          # la Collection<ActiveAbility>
          if (StaticBattleRules.ActiveAbility.IsActiveAbility(a.<+0x44>) && a.<+0x28> == 0)
              return true
      return false

  Les deux offsets sont DEJA nommes par le port (`runner/components.py::ActiveAbility`) :
  `+0x44 AbilityName` -> `ability_type`, `+0x28 CanStillBeUsed` -> `can_still_be_used`. Donc le
  predicat est « le porteur a AU MOINS UNE active (au sens d'`IsActiveAbility`) qui n'est PLUS
  utilisable » -- c'est-a-dire qui a DEJA SERVI. `IsActiveAbility` est lui aussi deja porte
  (`runner/abilities/attack_type.py::is_active_ability`, mirror du decompile :
  `!IsRegularAttack(t) && t not in {Heal, Repair, Repair_GalvanicField, Heal_TwistedScience,
  HealingBalms_Heal}`) -- ce port-ci n'en re-derive AUCUN etage.

  EFFET, exactement celui que le residu annoncait : les kills faits AVANT le premier usage d'une
  active du porteur n'incrementent PLUS le compteur.
  ⚠ TRI-ETAT, et la degradation est PERMISSIVE **par mesure, pas par gout** : le composant
  `ActiveAbilitiesComponent` n'est seede que si la vue de decision porte `allAbilities: true`
  (`runner/snapshot.py::_active_abilities` le DIT : « sans `allAbilities: true` [...] composant
  ABSENT »). Composant ABSENT = canal NON MESURE -> on ne bloque pas, ce qui est STRICTEMENT le
  comportement d'avant ce port. Le rabattre sur FAUX eteindrait le compteur entier sur un trou de
  substrat -- une regression la ou il n'y avait qu'une absence de gate.
* **l'EFFET `1583 Helspear_IgnoreArmor` est porte, sa MAGNITUDE n'atteint pas le calcul** :
  cf. `entities/effects/loki/helspear.py`, residu `#1008-r2`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.behaviours import If, op_and
from .....entities.effect_type import EffectType
from .....entities.formulas import GetPersistentData
from .....entities.selectors.accessors import Owner, Target
from .....entities.selectors.units import Tiles
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsEqualOrGreater, HasTrait
from .....entities.effects.magnitude import ability_var
from ....abilities.behaviours.ability_state import ResetActiveAbility
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....abilities.behaviours.persistent_data import AddPersistentData, ClearPersistentData
from ....abilities.attack_type import is_active_ability
from ....components import ActiveAbilitiesComponent, OwnerComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

#: Cle du registre `RELIC_ABILITY_TRIGGERS` = le NOM gameconfig de l'ability de relique.
ABILITY_ID = "Helspear"
#: `TriggeredAbilityType` 0x616 = 1558 -- l'`AbilityOrEffect` des TROIS noeuds de persistent-data.
HELSPEAR = int(TriggeredAbilityType.Helspear)
#: `EffectType` 0x62f = 1583, pose sur la CIBLE de l'active.
IGNORE_ARMOR_EFFECT = int(EffectType.Helspear_IgnoreArmor)
IGNORE_ARMOR_EFFECT_NAME = "Helspear_IgnoreArmor"
#: `EffectType` 0x5c4 = 1476, pose sur la TUILE de la cible -- l'effet de tuile Black Legion, DEJA
#: porte par `entities/effects/loki/despoiled_ground.py` (aucun 2e port ici).
DESPOILED_GROUND_EFFECT = int(EffectType.DespoiledGround)
DESPOILED_GROUND_EFFECT_NAME = "DespoiledGround"
#: `CurrentAbilityIs(AbilityOrEffect(0x3fc))` / `NOT TriggeringAbilityIs(...)` -- l'active du
#: porteur. Litteral QUALIFIE par l'adresse de son `op_Implicit` (cf. l'en-tete du module).
HERALD_OF_THE_APOCALYPSE = int(ActiveAbilityType.HeraldOfTheApocalypse)

NR_OF_UNITS_KEY = "nrOfUnits"        # `AbilityVariableType` 0x9a = 154
ARMOR_IGNORED_KEY = "armorIgnored"   # `AbilityVariableType` 0x40 = 64 (lu par l'EFFET, pas ici)

#: `<literal statique>` des trois noeuds de persistent-data = `"helspear_defeat_count"`, LU dans
#: `data/symbols/<build>/metadata/string_literals.tsv` (index 25558). Seule son UNICITE est
#: load-bearing : le sac est indexe par `(GetPersistentDataId(AbilityOrEffect(1558)), key)`.
_COUNTER_KEY = "helspear_defeat_count"
#: `ResetActiveAbility(Owner@+0x30, allowUseless = true)`.
RESET_ALLOW_USELESS = True
#: `<DSLFormulas+0x20>` = `Direct(1)` (cf. `loki/volumms_master_artifice.py`, meme champ relu).
_INCREMENT = 1

#: `NOT IsSteppableUnit(Target@+0x60)` -- `IdunBattleLogic.Entities.DSLTriggers$$IsSteppableUnit` a
#: pour corps `HasTrait(selector, UnitTrait.Steppable = 0x1b)`. Noeud DSL du foyer, jamais une
#: recopie du nom de trait au site.
_TARGET_IS_STEPPABLE = HasTrait(Target(), int(UnitTrait.Steppable))


def _owners_active_ability_been_used(state: State, owner_id: int) -> bool:
    """`<DSLTriggers+0x58> = HasOwnersActiveAbilityBeenUsed` (#1008-r3) -- mirror de
    `IdunBattle.DSL.HasActiveAbilityBeenUsedByOwnerAbilityTrigger$$ShouldTrigger`, LU verbatim :

        foreach (a in owner.<ActiveAbilitiesComponent>.<+0x20>)
            if (StaticBattleRules.ActiveAbility.IsActiveAbility(a.<+0x44>) && a.<+0x28> == 0)
                return true
        return false

    `+0x44 AbilityName` et `+0x28 CanStillBeUsed` sont les offsets que `runner/components.py::
    ActiveAbility` NOMME deja ; `IsActiveAbility` est le mirror deja porte de
    `runner/abilities/attack_type.py`. Cette fonction ne re-derive AUCUN etage.

    TRI-ETAT : composant ABSENT = canal NON MESURE -> **VRAI** (on ne bloque pas). Ce n'est pas un
    choix de gout : `runner/snapshot.py::_active_abilities` n'ajoute le composant que si la vue de
    decision porte `allAbilities: true`, et rendre FAUX sur ce trou eteindrait le compteur entier --
    une REGRESSION la ou il n'y avait, avant ce port, qu'une absence de gate. Un composant PRESENT
    mais vide, lui, est une mesure : aucune active montee -> aucune active utilisee -> **FAUX**."""
    ent = state.get_entity(int(owner_id))
    comp = ent.get_component(ActiveAbilitiesComponent) if ent is not None else None
    if comp is None:
        return True                                    # canal NON MESURE (cf. la docstring)
    return any(is_active_ability(a.ability_type) and not a.can_still_be_used
               for a in (comp.abilities or ()))


def helspear_buff_tree():
    """`AddEffect(1583, ..., targets = Target@+0x60) + AddEffect(1476, ..., targets = Tiles(Target))`.

    `op_Addition` : sequence simple, aucun gate entre les deux. `duration_rounds = None` mirroire le
    `options = NULL` natif (aucune duree passee -> l'effet vit selon sa propre regle de retrait)."""
    return op_and(
        AddEffect(IGNORE_ARMOR_EFFECT, IGNORE_ARMOR_EFFECT_NAME, Target(), duration_rounds=None),
        AddEffect(DESPOILED_GROUND_EFFECT, DESPOILED_GROUND_EFFECT_NAME, Tiles(Target()),
                  duration_rounds=None))


def helspear_reset_tree(nr_of_units: int):
    """`AddPersistentData(+1) + If(compteur >= nrOfUnits, ResetActiveAbility + ClearPersistentData)`.

    L'INCREMENT est le terme de GAUCHE : il s'execute AVANT que le `If` ne relise le compteur (cf.
    l'en-tete). Le seuil est donc `>= nrOfUnits` sur le compteur DEJA incremente -- l'active se
    recharge au `nrOfUnits`-ieme ennemi vaincu."""
    counter = GetPersistentData(HELSPEAR, Owner(), _COUNTER_KEY)
    cond = AmountIsEqualOrGreater(counter, Const(int(nr_of_units)))
    then_ = op_and(ResetActiveAbility(Owner(), ignore_turn_flag=RESET_ALLOW_USELESS),
                   ClearPersistentData(HELSPEAR, Owner(), _COUNTER_KEY))
    return op_and(AddPersistentData(HELSPEAR, Owner(), _COUNTER_KEY, _INCREMENT), If(cond, then_))


def relic_vars(state: State, owner_id: int) -> "tuple[int, int]":
    """`(nrOfUnits, armorIgnored)` au niveau de l'`AbilityState` sous lequel la relique est montee.

    `triggered_ability_state` rend le couple TERTIAIRE (`TertiaryAbilityLevel` /
    `TertiaryAbilityVariablesMultiplierPercentage`) quand `Helspear` arrive par l'item equipe, le
    couple PASSIF sinon -- distribution d'`UnitFactory$$Build`. Lire le couple PASSIF ferait lire le
    DERNIER palier (clamp de `TryGetVariableArrayForLevel`), en silence : c'est la faute mesuree par
    #1007, et elle est SEPARANTE ici (`nrOfUnits[0] = 8` contre `nrOfUnits[9] = 4`)."""
    lvl, mult = triggered_ability_state(state, owner_id, ABILITY_ID)
    return (int(ability_var(ABILITY_ID, NR_OF_UNITS_KEY, lvl, multiplier_pct=mult) or 0),
            int(ability_var(ABILITY_ID, ARMOR_IGNORED_KEY, lvl, multiplier_pct=mult) or 0))


class HelspearBuffActiveAbility(TriggeredAbility):
    """`Helspear_BuffActiveAbility` -- quand Haarken frappe avec son active
    `HeraldOfTheApocalypse`, sa cible recoit l'effet 1583 (`Helspear_IgnoreArmor`) et SA TUILE
    recoit l'effet 1476 (`DespoiledGround`)."""

    event_id = int(EventTriggerType.Attack)                # 9
    TRIGGERED_ABILITY_ID = HELSPEAR                        # 1558

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`On(9, alive) & get_OwnerIsCaster & CurrentAbilityIs(HeraldOfTheApocalypse)`.

        `ev.triggering_ability` porte le champ natif **`CurrentAbility`** (`AbilityEntities+0x60`),
        qui est exactement ce que `CurrentAbilityIs` lit (`CurrentAbilitySelector`) -- cf. le long
        avertissement de nommage de `triggers/base.TriggerEvent`."""
        if ev.actor_id != self.owner_id:                   # get_OwnerIsCaster
            return False
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        ouc = owner.get_component(UnitComponent)
        if ouc is not None and not ouc.alive:              # On(..., ownerNeedsToBeAlive = 1)
            return False
        # `CurrentAbilityIs(AbilityOrEffect(0x3fc))` -- canal TRI-ETAT : `None` = l'attaque n'a pas
        # d'ability courante threadee, donc le gate natif est FAUX (le `Nullable` vide ne peut
        # egaler aucun id). On REFUSE, on ne suppose pas.
        if ev.triggering_ability is None:
            return False
        return int(ev.triggering_ability) == HERALD_OF_THE_APOCALYPSE

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, int(self.owner_id), ev.target_id,
                                       actor_id=ev.actor_id)
        helspear_buff_tree().execute(entities, ectx)
        posed = [p.get("effect_type", p.get("name")) for n, p in ectx.emitted if n == "AddEffect"]
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "target": None if ev.target_id is None else int(ev.target_id),
                "effects": posed, "dsl": True}


class HelspearResetActiveAbility(TriggeredAbility):
    """`Helspear_ResetActiveAbility` -- chaque ennemi non-`Steppable` vaincu par Haarken (autrement
    que par `HeraldOfTheApocalypse` elle-meme) incremente un compteur ; au `nrOfUnits`-ieme, son
    active est RE-ARMEE et le compteur est vide."""

    event_id = int(EventTriggerType.UnitDefeated)          # 0x36 = 54
    TRIGGERED_ABILITY_ID = HELSPEAR                        # 1558

    def _victim(self, ev: TriggerEvent):
        return ev.dying_id if ev.dying_id is not None else ev.target_id

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """Les SIX conjoints du `CreateTrigger` (le sixieme, `<DSLTriggers+0x58> =
        HasOwnersActiveAbilityBeenUsed`, est porte depuis `#1008-r3` -- cf. l'en-tete)."""
        if ev.actor_id != self.owner_id:                   # get_OwnerIsActor
            return False
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        # `<DSLTriggers+0x58> = HasOwnersActiveAbilityBeenUsed` -- le SIXIEME conjoint (#1008-r3).
        # Mirror de `IdunBattle.DSL.HasActiveAbilityBeenUsedByOwnerAbilityTrigger$$ShouldTrigger`
        # (corps cite dans l'en-tete) : VRAI des qu'UNE active du porteur, au sens d'`IsActiveAbility`,
        # n'est plus utilisable (`CanStillBeUsed@0x28 == 0`), c'est-a-dire a DEJA servi.
        if not _owners_active_ability_been_used(state, int(self.owner_id)):
            return False
        ouc = owner.get_component(UnitComponent)
        if ouc is not None and not ouc.alive:              # On(..., ownerNeedsToBeAlive = 1)
            return False
        victim = self._victim(ev)
        if victim is None or int(victim) == int(self.owner_id):
            return False
        # `NOT TriggeringAbilityIs(AbilityOrEffect(0x3fc))` -- le kill fait PAR l'active elle-meme
        # ne compte pas. Canal `triggering_ability` (= `CurrentAbility`, cf. `TriggerEvent`) ;
        # `None` = pas d'ability courante -> le `TriggeringAbilityIs` natif est FAUX, donc son
        # NOT est VRAI : on laisse passer.
        if ev.triggering_ability is not None and \
                int(ev.triggering_ability) == HERALD_OF_THE_APOCALYPSE:
            return False
        # `NOT AreFriends(Owner@+0x30, Target@+0x60, ByCurrentTeam = 0, anyEntity = false)` --
        # et NON `AreEnemies`, qui est un AUTRE noeud natif. Equipe inconnue d'un cote -> on REFUSE
        # (degradation RESTRICTIVE, meme choix que `head_claimer.py` sur le meme porteur).
        victim_e = state.get_entity(int(victim))
        if victim_e is None:
            return False
        ooc = owner.get_component(OwnerComponent)
        voc = victim_e.get_component(OwnerComponent)
        if ooc is None or voc is None or ooc.team is None or voc.team is None:
            return False
        if ooc.team == voc.team:
            return False
        # `NOT IsSteppableUnit(Target@+0x60)` -- noeud DSL du foyer (un cadavre charge sans
        # `StatsComponent` y reste VOYANT, ce qu'une lecture brute de `ctx.traits` ne serait pas).
        entities = entities_from_state(state, int(self.owner_id), int(victim),
                                       actor_id=ev.actor_id)
        return not _TARGET_IS_STEPPABLE.should_trigger(entities)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        nr_of_units, _armor = relic_vars(state, self.owner_id)
        if nr_of_units <= 0:
            # `GetVariableForLevel` n'a rien rendu (relique non seedee) -> l'arbre natif comparerait
            # le compteur a 0 et re-armerait l'active a CHAQUE kill. Le port refuse ce regime.
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, int(self.owner_id), self._victim(ev),
                                       actor_id=ev.actor_id)
        helspear_reset_tree(nr_of_units).execute(entities, ectx)
        emitted: dict = {}
        for name, payload in ectx.emitted:
            emitted.setdefault(name, []).append(payload)
        posees = [q for p in emitted.get("AddPersistentData", ()) for q in (p.get("posees") or ())]
        resets = emitted.get("ResetActiveAbility", ())
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "victim": self._victim(ev), "nr_of_units": int(nr_of_units),
                "counter": (posees[0]["value"] if posees else None),
                "reset": bool(resets and resets[0].get("reset")),
                "cleared": len(emitted.get("ClearPersistentData", ())),
                "dsl": True}
