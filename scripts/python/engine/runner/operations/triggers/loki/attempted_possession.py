"""Le trigger de PROPAGATION de `1209 AttemptedPossession_Possessed` (#590-r3).

⚠ **CE MODULE N'EST PAS `triggers/loki/possession.py`, ET LA CONFUSION EST DEJA DOCUMENTEE.**
`possession.py` porte le PASSIF `Possession` de `blackPossession` << Archimatos >> (#955) ; sa
docstring dit elle-meme que « les classes `AttemptedPossession*` que le nom laisse croire siennes
appartiennent a l'ACTIVE `ActiveAbilityType.AttemptedPossession = 1101` de `thousSorcerer` ». Les
deux mecaniques n'ont rien de commun -- deux fichiers, comme cote natif.

`IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect$$CreateHandleTriggerAbilitiesInternal`
-- RELU au decompile (`rnca9r7q6c`), terme a terme :

    ArraySet = ABondEffect.CreateHandleTriggerAbilitiesInternal()          # les triggers HERITES
    trig = On(0x32 = UnitAdded)
         & AmountIsZero( Count( Parent(<DSLSelectors+0x30> Owner, root: false) ) )
         & AreEqual( Parent(<DSLSelectors+0x40> Actor, root: false), <DSLSelectors+0x30> Owner )
    beh  = AddBondEffect( effectType   = 0x4b9 = 1209 AttemptedPossession_Possessed,
                          abilityState = AbilityStateFromEffect(<+0x38> Effect),
                          source       = BondedEntityFromEffect(<+0x38> Effect),
                          targets      = <+0x40> Actor,
                          bondedEntity = BondedEntityFromEffect(<+0x38> Effect),
                          turns        = <DSLFormulas+0x20> = Direct(1) )
    ArraySet.Add( Triggered(trig, beh, null) )

## Ce que ca FAIT

Pendant la possession, tout SUMMON qui apparait sous la coupe de l'unite possedee est possede a son
tour, pour 1 tour, et bonde au MEME caster. L'arbre de `1101` possede
`Target + Alive(Children(Target))` au moment du cast ; ce trigger etend la possession aux enfants
qui apparaissent APRES.

## Les deux gates, et pourquoi ils ne sont pas cosmetiques

  * `AmountIsZero(Count(Parent(Owner)))` -- l'unite qui PORTE l'effet n'a PAS de parent, donc c'est
    la cible RACINE du cast et non un summon deja possede. Sans lui, un summon possede propagerait a
    ses propres summons : une CHAINE que le natif n'a pas.
  * `AreEqual(Parent(Actor), Owner)` -- l'unite qui vient d'apparaitre est un enfant DE CE porteur.
    `Parent(x, root: false)` = le SUMMONER IMMEDIAT (`IdunBattle.Entities.UnitExtensions$$GetParent`
    via `ParentComponent+0x10`), jamais l'equipe ni le proprietaire.

⚠ **`AmountIsZero` : le port suit la semantique MESUREE, pas le litteral.** Lu a la lettre,
`IdunBattleLogic.Entities.DSLTriggers$$AmountIsZero(x)` = `NOT AmountIsGreater(x, <DSLFormulas+0x20>)`
avec `<+0x20> = 1`, donc `x <= 1` -- ce qui rendrait CE gate toujours vrai (`Parent` rend au plus une
entite). La MESURE de `#462-r4b-r1-r1-r1-r1` (§2 de `triggers/bond_removal.py`) REFUTE cette lecture
sur l'autre call-site de la famille : `NOT AmountIsZero(BondedEntity)` y est VRAI quand le bonde
existe, ce qui est impossible sous le litteral. Le port lit donc `AmountIsZero(x)` comme `x == 0`,
ici comme la-bas. La reconciliation exacte avec `<+0x20> = 1` reste le residu NOMME
`#462-r4b-r1-r1-r1-r1-r1` ; ce qui change ici, c'est que les deux lectures NE donnent PAS le meme
port -- la propagation en CHAINE existerait sous le litteral, et pas sous la mesure.

⚠ **PAS de gate `EffectComponent.IsActive`.** Ce `Triggered()` vient de
`CreateHandleTriggerAbilitiesInternal`, donc du rail `ArraySet` que
`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities` sert -- et ce
rail-la n'accede JAMAIS a `+0x5c` (case-229). C'est l'AUTRE rail
(`...$$EvaluateEffectTriggerTargets`, celui de `CreateTargetTrigger`) qui porte le gate. L'y poser
eteindrait les `ActivateEffect` qui RALLUMENT un effet eteint.

## Les DEUX points que le residu declarait NON PROUVES -- l'un MESURE, l'autre NOMME

  1. **Les trois virtuels d'`ABondEffect` pour CETTE classe : MESURES** (2026-08-13,
     `probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared`, corps dedupliques resolus par
     ADRESSE) --

         get_Range                      OWN = none    -> PAS de trigger (b) `IsInRange`
         get_Adjacent                   OWN = false   -> PAS de trigger (c) `IsAdjacent`
         get_RemoveOnBondedEntityDeath  OWN = true    -> trigger (a) ARME

     Un seul des trois retraits herites s'arme donc : la possession tombe quand le CASTER (l'entite
     BONDEE) meurt ou quitte le plateau -- et elle ne tombe NI a la distance NI a la rupture
     d'adjacence, ce qui est coherent avec l'arbre du cast, qui envoie la proie ATTAQUER (donc
     s'eloigner de Thaumachus) dans le meme souffle. La ligne entre dans `BOND_REMOVAL_GATES`, et
     `bond_removal_registry_entries()` en DERIVE l'inscription -- jamais ecrite a la main.
  2. **`<DSLSelectors+0x40> = Actor` reste une lecture STRUCTURELLE, pas nominale.** Les champs
     partages de `DSLSelectors` sont alloues par `$$InitializeShared` depuis des `Il2CppClass*`
     (`DAT_*`) dont un SEUL est nomme par ghidra (`+0x18 = AllTilesSelector`) ; `list_xrefs` sur le
     `DAT_` de `+0x40` ne rend que ce site unique, donc AUCUN nom, et les ctors des selecteurs
     partages sont ICF-dedupliques entre eux. Ce qui l'etablit ici est la STRUCTURE : sur un
     `On(UnitAdded)` le port comme le natif construisent `AbilityEntities(added, added, added)`,
     donc l'unite qui apparait est l'ACTEUR, et c'est la seule entite qui VARIE par evenement --
     `+0x30` ne peut etre que le porteur (`AmountIsZero(Count(Parent(+0x30)))` n'a de sens que sur
     lui) et `+0x40` que l'acteur. Le NOMMER demanderait un capteur live (`classFields`/`typeName`
     sur l'instance) : residu `#590-r11`.

ASCII only (console cp1252).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import UnitComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddBondEffect
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from ..base import EffectTrigger, TriggerEvent

#: `0x4b9` -- l'effet POSE par le cast et l'effet PROPAGE sont le MEME `EffectType`.
POSSESSED = int(EffectType.AttemptedPossession_Possessed)          # 0x4b9 = 1209
#: `<DSLFormulas+0x20>` = `Direct(1)` -- l'argument `turns` de l'`AddBondEffect` du trigger. C'est
#: la MEME valeur que le cast (`abilities/loki/attempted_possession.py::POSSESSION_TURNS`), mais
#: elle est RELUE ici : les deux sites la portent independamment cote natif.
PROPAGATION_TURNS = 1


def _parent_of(state: State, unit_id: Optional[int]) -> Optional[int]:
    """`IdunBattleLogic.Entities.DSLSelectors$$Parent(sel, root: false)` ->
    `IdunBattle.Entities.UnitExtensions$$GetParent` : le SUMMONER IMMEDIAT, lu dans
    `ParentComponent+0x10`. `root: false` = on ne remonte PAS la chaine jusqu'a la racine.

    Substrat du port : `UnitComponent.parent_id` -- le MEME que le selecteur `ChildrenOf` de l'arbre
    de `1101`, donc les deux cotes de l'`AreEqual` lisent la meme donnee."""
    if unit_id is None:
        return None
    e = state.get_entity(int(unit_id))
    if e is None:
        return None
    uc = e.get_component(UnitComponent)
    if uc is None:
        return None
    p = getattr(uc, "parent_id", None)
    return None if p is None else int(p)


class AttemptedPossessionPropagate(EffectTrigger):
    """`Triggered(On(UnitAdded) & AmountIsZero(Count(Parent(Owner))) & AreEqual(Parent(Actor), Owner),
    AddBondEffect(1209, ..., targets = Actor, bondedEntity = BondedEntityFromEffect(Effect),
    turns = 1))` -- cf. l'en-tete du module.

    Le `CreateTrigger` COLLAPSE imperativement dans `matches` (doctrine #149, meme patron que
    `BondRemoveOnBondedEntityDeath`) ; le behaviour, lui, RESTE un arbre DSL -- la feuille
    `AddBondEffect` est celle du cast, pas une re-implementation."""
    effect_type = POSSESSED
    event_id = int(EventTriggerType.UnitAdded)          # 0x32 = 50

    def _instance(self, state: State):
        """L'instance de `1209` portee par l'owner -- elle transporte le `bondedEntity` que les DEUX
        selecteurs `BondedEntityFromEffect(Effect)` du behaviour lisent (source ET bondedEntity)."""
        eff = getattr(state, "effects", None)
        if eff is None:
            return None
        for e in (eff.by_unit.get(int(self.owner_id)) or []):
            if (not e.consumed) and int(e.effect_type) == POSSESSED:
                return e
        return None

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        added = ev.actor_id
        if added is None or state.get_entity(int(added)) is None:
            return False
        # `AmountIsZero(Count(Parent(Owner, root: false)))` -- semantique MESUREE (`== 0`), cf.
        # l'en-tete : le PORTEUR doit etre la cible RACINE, pas un summon deja possede.
        if _parent_of(state, int(self.owner_id)) is not None:
            return False
        # `AreEqual(Parent(Actor, root: false), Owner)` -- l'unite qui apparait est un enfant DE CE
        # porteur.
        if _parent_of(state, int(added)) != int(self.owner_id):
            return False
        # Le behaviour LIT `BondedEntityFromEffect(Effect)` DEUX fois : sans instance resoluble il n'y
        # a rien a lire, et poser un bond sans bonde inventerait un effet que le natif ne construit
        # pas (son `AddBondEffect` recevrait un selecteur VIDE).
        inst = self._instance(state)
        return inst is not None and getattr(inst, "bonded", None) is not None

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        inst = self._instance(state)
        added = ev.actor_id
        if inst is None or added is None:
            return None
        bonded = getattr(inst, "bonded", None)
        if bonded is None:
            return None
        # `Caster` <- `BondedEntityFromEffect(Effect)` (source ET bondedEntity), `Target` <- `Actor`.
        entities = entities_from_state(state, int(bonded), int(added))
        ectx = ExecutionContext(state=state, rng=state.rng)
        AddBondEffect(POSSESSED, EffectType.AttemptedPossession_Possessed.name,
                      Caster(), Target(),
                      duration_rounds=None, duration_turns=PROPAGATION_TURNS,
                      bonded_ref=Caster()).execute(entities, ectx)
        posed = [{"effect_type": p.get("effect_type"), "target": p.get("target"),
                  "bonded": p.get("bonded"), "placed": p.get("placed")}
                 for n, p in ectx.emitted if n == "AddBondEffect"]
        return {"trigger": "AttemptedPossession_Propagate", "owner": int(self.owner_id),
                "added": int(added), "bonded": int(bonded), "bonds": posed}
