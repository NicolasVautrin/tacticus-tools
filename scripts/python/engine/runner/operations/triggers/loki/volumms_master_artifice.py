"""`VolummsMasterArtifice` -- relique `R_Crit_VolummsMasterArtifice`, `TriggeredAbilityType`
0x5d0 = 1488, porteur `votanIronmaster` << Vynn >> (HERO Leagues of Votann, HORS du pool rank 17).
#1001.

i2 : << After Vynn or friendly E-COGs have performed +nrOfRepairs repairs, Vynn heals for hpToHeal
Health and can use his active ability again. >>

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- UNE classe native, UN arbre
================================================================================================

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.VolummsMasterArtificeAbility$$CreateTrigger`

    On( 0x30 = 48 UnitRepaired, ownerNeedsToBeAlive = 1 )
  & (   AreEqual( DSLSelectors$$Parent( Caster@DSLSelectors+0x48, root = false ),
                  Owner@DSLSelectors+0x30 )
      | get_OwnerIsCaster )

Le compteur monte donc sur DEUX voies : Vynn repare lui-meme, ou un de SES enfants repare (les
E-COGs que son passif `EcogSupport` 1487 invoque). `Parent` est le lien `ChildComponent.ParentId`
(`IdunBattle.Entities.UnitExtensions$$GetParent`), `root = false` = le parent DIRECT.

## `...VolummsMasterArtificeAbility$$GetPersistentData` (helper, corps propre)

    GetPersistentData( AbilityOrEffect(0x5d0 = 1488), Owner@+0x30, Get(<literal de chaine>) )

(`mov edx,0x5d0` relu a l'assembleur juste avant `IdunBattle.Core.AbilityOrEffect$$op_Implicit` --
le pseudo-C perd le litteral, il part par `edx`.)

## `...VolummsMasterArtificeAbility$$CreateBehaviour(abilityState, triggerType)` -- MIRROR

    cond = AmountIsEqualOrGreater( GetPersistentData(...),
                                   ConfigVar(0x9b = 155 nrOfRepairs, abilityState, config) )
    THEN =   Heal( healer = Owner@+0x30, targets = Owner@+0x30,
                   ConfigVar(0x20 = 32 hpToHeal, abilityState, config),
                   HealBehaviourOptions$$ForHeal(AbilityOrEffect) )
           & ResetActiveAbility( Owner@+0x30, allowUseless = true )
           & SetPersistentData( AbilityOrEffect(0x5d0), Owner@+0x30, Get(<literal>),
                                <DSLFormulas+0x18> = Direct(0) )
    return   AddPersistentData( AbilityOrEffect(0x5d0), Owner@+0x30, Get(<literal>),
                                <DSLFormulas+0x20> = Direct(1) )
           & If( cond, THEN, null )

**L'ORDRE EST LU, ET IL EST L'INVERSE DE `DaemonfleshPlate`.** Le dernier `op_BitwiseAnd` du corps
est `op_BitwiseAnd(AddPersistentData, If(...))` : l'INCREMENT est a GAUCHE, donc il s'execute AVANT
que le `If` n'evalue son `GetPersistentData`. Le seuil est donc `compteur >= nrOfRepairs` sur le
compteur DEJA incremente -- c.-a-d. le soin tombe a la N-ieme reparation, `N = nrOfRepairs`.
`DaemonfleshPlate`, lui, teste AVANT d'incrementer et compare a `nrOfAttacks - 1`. Recopier le
voisin de forme decalerait le declenchement d'une reparation.

Le reset est un `SetPersistentData(..., Direct(0))`, PAS un `ClearPersistentData` : la cle reste
posee a 0, le cycle repart de zero. (`DaemonfleshPlate` vide le sac -- deux fabriques differentes,
deux `Execute` differents, cf. `abilities/behaviours/persistent_data.py`.)

`DSLFormulas+0x18 = Direct(0)` et `+0x20 = Direct(1)` sont les constantes mises en cache par
`IdunBattleLogic.Entities.DSLFormulas$$.ctor` (+0x18 = 0, +0x20 = 1, +0x28 = 2, +0x30 = 100,
+0x38 = -1).

================================================================================================
CRITERE DE L'EMETTEUR
================================================================================================
`On(0x30 = 48 UnitRepaired)` EXISTE cote port depuis #964-r1
(`dispatch/repair.py::unit_repaired_triggers`), a sa place native : APRES la mutation `FillUp` et
APRES le gate de sortie anticipee de `IdunBattle.Operations.RepairUnitOperation$$Execute`. Le natif
y passe le REPARATEUR dans les DEUX premiers slots (owner ET actor), donc `Caster@+0x48` se lit sur
`ev.actor_id` -- meme mapping que `ECogSupportAbility`, qui partage le vecteur ET le porteur.

================================================================================================
FORME DU PORT (doctrine #149)
================================================================================================
* `CreateTrigger` COLLAPSE imperativement dans `matches` (patron `ECogSupportAbility`) ;
* `CreateBehaviour` est un ARBRE DSL dont les feuilles APPELLENT les Operations deja portees
  (`HealUnitOperation`, `ResetActiveAbilityOperation`, `PersistentDataComponent`) -- aucune n'est
  re-ecrite ;
* MAGNITUDE ET SEUIL sont resolus par l'APPELANT (`triggered_ability_state` + `ability_var`), comme
  `DawnBlade` et `DaemonfleshPlate` : le natif les tient en noeuds `ConfigVar` paresseux, mais leur
  valeur ne depend que du couple `(TertiaryAbilityLevel,
  TertiaryAbilityVariablesMultiplierPercentage)` de l'`AbilityState` sous lequel la relique est
  montee -- fixe pour la bataille. Lire `passive_ability_level` a la place rendrait TOUJOURS le
  dernier palier, en silence.

RESIDUS NOMMES
  * **la `dataKey`** : `DSLFormulas$$Get(<literal de chaine>)`, contenu non resoluble statiquement
    (cache de metadata IL2CPP). Seule son UNICITE est load-bearing -- le sac est indexe par
    `(GetPersistentDataId(AbilityOrEffect(1488)), key)`, donc aucune autre ability ne peut le
    percuter. Le port ecrit `_COUNTER_KEY`, constante locale.
  * `HealBehaviourOptions$$ForHeal` -> `(scope = 0, removeEffects = True)`, les DEFAUTS de la
    feuille `Heal` (#520). Ecrits explicitement au site pour que la fabrique soit citee.
  * `root = false` du `Parent` : le port ne remonte QUE d'un cran (c'est ce que fait le selecteur
    porte). Aucun regime porte n'a de petit-enfant.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If, op_and
from .....entities.formulas import GetPersistentData
from .....entities.selectors.accessors import Owner
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsEqualOrGreater
from .....entities.effects.magnitude import ability_var
from ....abilities.behaviours.ability_state import ResetActiveAbility
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.persistent_data import AddPersistentData, SetPersistentData
from ....abilities.behaviours.stats import Heal
from ....components import UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

#: Cle du registre `RELIC_ABILITY_TRIGGERS` = le NOM gameconfig de l'ability de relique.
ABILITY_ID = "VolummsMasterArtifice"
#: `AbilityOrEffect(0x5d0)` des trois noeuds de persistent-data (litteral relu a l'assembleur).
VOLUMMS_MASTER_ARTIFICE = int(TriggeredAbilityType.VolummsMasterArtifice)   # 0x5d0 = 1488

NR_OF_REPAIRS_KEY = "nrOfRepairs"    # `AbilityVariableType` 0x9b = 155
HP_TO_HEAL_KEY = "hpToHeal"          # `AbilityVariableType` 0x20 = 32

#: `DSLFormulas$$Get(<literal>)` -- cf. le residu nomme de l'en-tete : la CHAINE n'est pas resoluble
#: statiquement ; seule compte sa CONSTANCE sur les TROIS emplois de l'ability.
_COUNTER_KEY = "VolummsMasterArtifice"

#: `HealBehaviourOptions$$ForHeal` : `+0x10 = 0` (scope), `+0x14 = 1` (removeEffects).
HEAL_SCOPE = 0
HEAL_REMOVE_EFFECTS = True

#: `ResetActiveAbility(Owner, allowUseless = true)`.
RESET_ALLOW_USELESS = True


def volumms_master_artifice_tree(nr_of_repairs: int, hp_to_heal: int):
    """`...VolummsMasterArtificeAbility$$CreateBehaviour` -- MIRROR 1:1 (cf. l'en-tete du module).

    `nr_of_repairs` / `hp_to_heal` = les deux `ConfigVar`, resolus par l'appelant (meme choix et
    meme justification que `DawnBlade` / `DaemonfleshPlate`).

    L'INCREMENT est le terme de GAUCHE du dernier `op_BitwiseAnd` : il s'execute AVANT que le `If`
    ne relise le compteur. C'est ce qui fait du seuil un `>= nrOfRepairs` (et non `>= n - 1`)."""
    counter = GetPersistentData(VOLUMMS_MASTER_ARTIFICE, Owner(), _COUNTER_KEY)
    cond = AmountIsEqualOrGreater(counter, Const(int(nr_of_repairs)))
    then_ = op_and(
        op_and(Heal(Owner(), int(hp_to_heal), scope=HEAL_SCOPE,
                    remove_effects=HEAL_REMOVE_EFFECTS),
               ResetActiveAbility(Owner(), ignore_turn_flag=RESET_ALLOW_USELESS)),
        SetPersistentData(VOLUMMS_MASTER_ARTIFICE, Owner(), _COUNTER_KEY, 0))
    return op_and(AddPersistentData(VOLUMMS_MASTER_ARTIFICE, Owner(), _COUNTER_KEY, 1),
                  If(cond, then_))


def relic_vars(state: State, owner_id: int) -> "tuple[int, int]":
    """`(nrOfRepairs, hpToHeal)` au niveau de l'`AbilityState` sous lequel la relique est montee.

    `triggered_ability_state` rend le couple TERTIAIRE (`TertiaryAbilityLevel` /
    `TertiaryAbilityVariablesMultiplierPercentage`) quand `VolummsMasterArtifice` arrive par l'item
    equipe, le couple PASSIF sinon -- exactement la distribution d'`UnitFactory$$Build`. Aucune des
    deux variables n'est dans `variablesAffectedByRarityBonus` du gameconfig de la relique, donc le
    multiplicateur ne mord pas ; on le passe quand meme, parce que c'est `ability_var` (mirror de
    `GetVariableForLevel`) qui en decide, pas nous."""
    lvl, mult = triggered_ability_state(state, owner_id, ABILITY_ID)
    return (int(ability_var(ABILITY_ID, NR_OF_REPAIRS_KEY, lvl, multiplier_pct=mult) or 0),
            int(ability_var(ABILITY_ID, HP_TO_HEAL_KEY, lvl, multiplier_pct=mult) or 0))


class VolummsMasterArtificeAbility(TriggeredAbility):
    """`VolummsMasterArtificeAbility` -- a chaque REPARATION faite par Vynn OU par un de ses enfants
    (les E-COGs de son passif `EcogSupport`), le compteur monte de 1 ; a la `nrOfRepairs`-ieme, Vynn
    se soigne de `hpToHeal`, son ability active est RE-ARMEE, et le compteur repart a 0."""

    event_id = int(EventTriggerType.UnitRepaired)                           # 0x30 = 48
    TRIGGERED_ABILITY_ID = VOLUMMS_MASTER_ARTIFICE                          # 1488

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        ouc = owner.get_component(UnitComponent)
        if ouc is not None and not ouc.alive:              # `On(..., ownerNeedsToBeAlive = 1)`
            return False
        caster = ev.actor_id                               # `Caster@+0x48` sur ce vecteur
        if caster is None:
            return False
        if int(caster) == int(self.owner_id):              # `get_OwnerIsCaster`
            return True
        # `AreEqual( Parent(Caster@+0x48, root = false), Owner@+0x30 )` -- le lien
        # `ChildComponent.ParentId`, porte par `UnitComponent.parent_id` (pose au spawn par
        # `SpawnUnitOperation`, seede par `snapshot._load_unit_parent` sur un etat hydrate).
        ce = state.get_entity(int(caster))
        cuc = ce.get_component(UnitComponent) if ce is not None else None
        parent = getattr(cuc, "parent_id", None) if cuc is not None else None
        return parent is not None and int(parent) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        nr_of_repairs, hp_to_heal = relic_vars(state, self.owner_id)
        if nr_of_repairs <= 0:
            # `GetVariableForLevel` n'a rien rendu (relique non seedee) -> l'arbre natif comparerait
            # le compteur a 0 et soignerait a CHAQUE reparation. Le port refuse d'inventer ce regime.
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, int(self.owner_id), ev.target_id,
                                       actor_id=ev.actor_id)
        volumms_master_artifice_tree(nr_of_repairs, hp_to_heal).execute(entities, ectx)
        emitted: dict = {}
        for name, payload in ectx.emitted:
            emitted.setdefault(name, []).append(payload)
        posees = [q for p in emitted.get("AddPersistentData", ()) for q in (p.get("posees") or ())]
        heals = [q for p in emitted.get("Heal", ()) for q in (p.get("heals") or ())]
        resets = emitted.get("ResetActiveAbility", ())
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "repairer": None if ev.actor_id is None else int(ev.actor_id),
                "nr_of_repairs": int(nr_of_repairs), "hp_to_heal": int(hp_to_heal),
                "counter": (posees[0]["value"] if posees else None),
                "healed": sum(int(h.get("healed") or 0) for h in heals),
                "reset": bool(resets and resets[0].get("reset")),
                "reset_gate": (resets[0].get("gate") if resets else None),
                "dsl": True}
