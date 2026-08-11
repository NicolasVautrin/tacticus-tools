"""`DaemonfleshPlate` -- relique `R_Block_DaemonfleshPlate`, `TriggeredAbilityType` 1493.

i2 (`Abilities/DaemonfleshPlate_CurrentLevelDescription`) : << Each time the relic bearer attacks,
it gains +extraArmor Armour. After attacking nrOfAttacks times, this bonus is reset and the relic
bearer can use its active ability again. >>

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- DEUX classes natives pour UNE cle de registre
================================================================================================
Meme patron que `LetTheGalaxyBurn` / `HaywireMine` : l'ability principale et son << reset >>.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DaemonfleshPlateAbility$$CreateTrigger`

    On(9 = EventTriggerType.Attack, ownerNeedsToBeAlive = true) & get_OwnerIsCaster

⚠ **CE CORPS EST INVISIBLE DES TABLES, ET LE PROUVER FAISAIT PARTIE DE LA TRANCHE.**
`DaemonfleshPlateAbility$$CreateTrigger` n'apparait NI dans `frida/methods.tsv` NI dans
`ghidra/functions.tsv` : IL2CPP a DEDUPLIQUE son corps avec celui de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateTrigger`
(les deux sont `On(9, true) & OwnerIsCaster`, 112 octets a l'octet pres), et la table ne garde qu'UN
proprietaire par adresse. L'appartenance est etablie **slot a slot dans le bloc `methodPointers` du
PE** (la meme methode que #910) : le groupe de la classe s'y lit entre deux occurrences du corps
partage `UnityEngine.Scripting.RequiredByNativeCodeAttribute$$.ctor` (le `.ctor` trivial deduplique
qui sert de separateur de fait), et vaut, dans l'ordre :

    <sep>  CreateTrigger(=le corps partage)  CreateBehaviour  GetLocalizationData  GetCurrentExtraArmor  <sep>

soit exactement l'ordre de declaration que porte aussi `DaemonfleshPlate_ResetActiveAbility`
(CreateTrigger puis CreateBehaviour). Le corps partage a par ailleurs **trois** xrefs DATA : une
`.pdata` et **deux** entrees de `methodPointers` -- une par classe proprietaire. Conclure
<< la classe ne definit pas CreateTrigger >> de son absence des tables aurait ete faux.

`...DaemonfleshPlateAbility$$CreateBehaviour(abilityState, triggerType)` -- MIRROR :

    counter = GetPersistentData( AbilityOrEffect(DaemonfleshPlate), Owner@DSLSelectors+0x30,
                                 Get(<literal>) )
    cond    = AmountIsEqualOrGreater( counter,
                                      Subtract( ConfigVar(0x4e = nrOfAttacks), DSLFormulas+0x20 ) )
    THEN    = ( RemoveEffect( Owner@+0x30, Nullable(0x5d2 = DaemonfleshPlate_ExtraArmor) )
              & AddEffect( 0x5d3 = DaemonfleshPlate_ResetActive, AbilityStateReference,
                           source = Owner@+0x30, targets = Owner@+0x30, options ZERO ) )
              & ClearPersistentData( AbilityOrEffect(DaemonfleshPlate), Owner@+0x30, Get(<literal>) )
    ELSE    = AddStaticStatModifierEffect( targets = Caster@DSLSelectors+0x48,
                                           0x5d2 = DaemonfleshPlate_ExtraArmor,
                                           stat = 0x10 = FixedArmor,
                                           amount = ConfigVar(0x1b = extraArmor),
                                           turns = null, isHidden = false )
              & AddPersistentData( AbilityOrEffect(DaemonfleshPlate), Owner@+0x30, Get(<literal>),
                                   DSLFormulas+0x20 )
    return    If( cond, THEN, ELSE )

`DSLFormulas+0x20` = `Direct(1)` (LU dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor` : +0x18 = 0,
**+0x20 = 1**, +0x28 = 2, +0x30 = 100, +0x38 = -1) -- c'est le MEME noeud aux deux emplois, donc le
seuil est `nrOfAttacks - 1` et l'increment est `+1`.
`IdunBattleLogic.Entities.DSLFormulas$$Subtract(a, b)` = `Sum(a, Multiply(b, +0x38 = Direct(-1)))`,
porte par le noeud `Difference` deja existant.

**LES SIX SURCHARGES SONT TRANCHEES PAR LA CIBLE DU `call`**, pas par l'arite ni par le pseudo-C
(les `.ctor` que ghidra affiche sur ces factories -- `PerformAIMovementBehaviour` pour
`DSLBehaviors$$If`, `AmountIsGreaterAbilityTrigger` pour `$$AmountIsEqualOrGreater` -- sont des folds
gshared MISLABELES). Les adresses lues au desassemblage de `...DaemonfleshPlateAbility$$CreateBehaviour`
designent : `DSLFormulas$$ConfigVar` (surcharge a 4 args), `DSLFormulas$$GetPersistentData`,
`DSLFormulas$$Subtract`, `DSLTriggers$$AmountIsEqualOrGreater`,
`DSLBehaviors$$AddStaticStatModifierEffect` (surcharge `Nullable<int> turns`),
`DSLBehaviors$$AddPersistentData` (surcharge a `dataKey` deja formee),
`DSLBehaviors$$RemoveEffect`, `DSLBehaviors$$ClearPersistentData`, `DSLBehaviors$$AddEffect`,
`DSLBehaviors$$If`.

`...DaemonfleshPlate_ResetActiveAbility$$CreateTrigger` :

    On(0x3a = EventTriggerType.PhaseEnd, ownerNeedsToBeAlive = true)
  & HasEffect( Owner@+0x30, 0x5d3 = DaemonfleshPlate_ResetActive, onlyActive = false, sourceFlags = 6 )

`...DaemonfleshPlate_ResetActiveAbility$$CreateBehaviour` :

    ResetActiveAbility( Owner@+0x30, allowUseless = true )
  + RemoveEffect( Owner@+0x30, Nullable(0x5d3 = DaemonfleshPlate_ResetActive) )

(`op_Addition` ici, `op_BitwiseAnd` dans l'ability principale : les DEUX allouent la meme
`IdunBattle.DSL.CombinedBehaviour`, cf. `entities/behaviours.py::Seq`.)

================================================================================================
CE QUE LA MECANIQUE FAIT, ETAGE PAR ETAGE
================================================================================================
Compteur `c` dans le `PersistentDataComponent` du porteur, cle `(AbilityOrEffect(1493), <literal>)`.
`AddPersistentData` **ACCUMULE** (`IdunBattle.Entities.Triggers.AddPersistentDataBehavior$$Execute`
relit puis `add dword`, cf. `abilities/behaviours/persistent_data.py`), donc `c` monte de 1 par
attaque. Avec `N = nrOfAttacks` (8 aux niveaux 1-5, **7** aux niveaux 6-10) :

    attaques 1..N-1 : `c-1 >= N-1` faux -> ELSE : +1 pile d'armure (`extraArmor`), `c += 1`
    attaque  N      : `c = N-1 >= N-1` VRAI -> THEN : les N-1 piles sont retirees d'un coup,
                      l'effet 1491 est pose, le compteur est vide (`c` disparait)
    puis, a la fin de la phase courante : l'ability active du porteur est RE-ARMEE et 1491 retire

Le maximum d'armure accumulee est donc `(N-1) x extraArmor`, atteint JUSTE AVANT la N-ieme attaque
-- pas `N x extraArmor`. Confondre `>= N-1` avec `>= N` decalerait le reset d'une attaque ET
ajouterait une pile ; c'est le premier mutant du garde.

`GetCurrentExtraArmor` (= `Multiply(Direct(GetVariableForLevel(0x1b)), GetPersistentData(...))`,
lu, non porte -- c'est l'alimentation de `extraArmorCurrent` du descriptif d'effet) confirme que le
natif tient l'armure courante pour `extraArmor x c` : l'effet 1490 **EMPILE**, il n'est pas
rafraichi. Cf. `entities/effects/loki/daemonflesh_plate.py` pour la forme native de l'empilement et
pour le fait que ce verdict est une MESURE.

================================================================================================
FORME DU PORT (doctrine #149)
================================================================================================
* les DEUX `CreateTrigger` COLLAPSENT imperativement dans `matches` (patron `ActOfFaithResetAbility`
  pour `On(9) & OwnerIsCaster`, patron `RammingSpeed` pour le vecteur `PhaseEnd`) ;
* les DEUX `CreateBehaviour` sont des ARBRES DSL dont les feuilles APPELLENT les Operations deja
  portees (`AddEffectOperation`, `apply_change_stat`, `RemoveEffectOperation`,
  `ResetActiveAbilityOperation`, `PersistentDataComponent`) -- aucune n'est re-ecrite.

MAGNITUDE ET SEUIL sont resolus par l'APPELANT (`triggered_ability_state` + `ability_var`), comme
`DawnBlade` : le natif les tient en noeuds `ConfigVar` paresseux, mais leur valeur ne depend que du
couple `(TertiaryAbilityLevel, TertiaryAbilityVariablesMultiplierPercentage)` de l'`AbilityState`
sous lequel l'ability est montee -- fixe pour la bataille. Passer par `triggered_ability_state` est
ce qui distingue le niveau de RELIQUE (1..10) du niveau des PASSIFS (50 sur tout runner normalise) ;
le lire au mauvais slot rendrait toujours le dernier palier, en silence.

RESIDUS NOMMES
  * **la `dataKey`** : le natif la fabrique par `DSLFormulas$$Get(<literal de chaine>)`, dont le
    contenu n'est pas resoluble statiquement (cache de metadata IL2CPP initialise par
    `il2cpp_codegen_initialize_runtime_metadata`). Le literal est PARTAGE avec
    `Dw02AdvancedBurstCannonAbility` (xrefs), donc generique et non specifique a la relique. Sans
    consequence : le sac est indexe par `(GetPersistentDataId(abilityOrEffect), key)` et le port
    porte la meme cle composite -- deux abilities partageant la chaine ne se marchent pas dessus.
    Le port ecrit `_COUNTER_KEY`, constante locale, jamais comparee a une autre ability.
  * **`isHidden = false`** (7e argument d'`AddStaticStatModifierEffect`) : la feuille portee ne
    modelise pas ce drapeau (cosmetique -- affichage de l'icone d'effet), aucun observable d'etat.
  * **`allowUseless = true`** de `ResetActiveAbility` : porte tel quel (`ignore_turn_flag`), cf.
    `abilities/behaviours/ability_state.py`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If, op_add, op_and
from .....entities.effect_type import EffectType
from .....entities.formulas import Difference, GetPersistentData
from .....entities.selectors.accessors import Owner
from .....entities.selectors.tiles import Caster
from .....entities.stats import StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsEqualOrGreater
from .....entities.effects.magnitude import ability_var
from ....abilities.behaviours.ability_state import ResetActiveAbility
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import (AddEffect, AddStaticStatModifierEffect, RemoveEffect)
from ....abilities.behaviours.persistent_data import AddPersistentData, ClearPersistentData
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

ABILITY_ID = "DaemonfleshPlate"
DAEMONFLESH_PLATE = int(TriggeredAbilityType.DaemonfleshPlate)          # 0x5d5 = 1493
EXTRA_ARMOR_EFFECT = int(EffectType.DaemonfleshPlate_ExtraArmor)       # 0x5d2 = 1490
RESET_ACTIVE_EFFECT = int(EffectType.DaemonfleshPlate_ResetActive)     # 0x5d3 = 1491

EXTRA_ARMOR_KEY = "extraArmor"       # `AbilityVariableType` 0x1b = 27
NR_OF_ATTACKS_KEY = "nrOfAttacks"    # `AbilityVariableType` 0x4e = 78

#: `DSLFormulas$$Get(<literal>)` -- cf. le residu nomme de l'en-tete : la CHAINE n'est pas resoluble
#: statiquement ; seule compte sa CONSTANCE sur les quatre emplois de l'ability.
_COUNTER_KEY = "DaemonfleshPlate"

def daemonflesh_plate_behaviour_tree(extra_armor: int, nr_of_attacks: int):
    """`...DaemonfleshPlateAbility$$CreateBehaviour` -- MIRROR 1:1 (cf. l'en-tete du module).

    `extra_armor` / `nr_of_attacks` = les deux `ConfigVar`, resolus par l'appelant (meme choix que
    `DawnBlade`, meme justification). Le `- 1` reste un noeud `Difference` = le `Subtract(a,
    DSLFormulas+0x20 = Direct(1))` natif, pour que le seuil ne soit pas re-ecrit en scalaire."""
    counter = GetPersistentData(DAEMONFLESH_PLATE, Owner(), _COUNTER_KEY)
    cond = AmountIsEqualOrGreater(counter, Difference(Const(int(nr_of_attacks)), Const(1)))
    # THEN -- `(RemoveEffect & AddEffect) & ClearPersistentData` (ordre des `op_BitwiseAnd` du natif)
    then_ = op_and(
        op_and(RemoveEffect(EXTRA_ARMOR_EFFECT, Owner()),
               AddEffect(RESET_ACTIVE_EFFECT, EffectType.DaemonfleshPlate_ResetActive.name,
                         Owner(), duration_rounds=None, source_ref=Owner())),
        ClearPersistentData(DAEMONFLESH_PLATE, Owner(), _COUNTER_KEY))
    # ELSE -- `AddStaticStatModifierEffect & AddPersistentData`
    else_ = op_and(
        AddStaticStatModifierEffect(Caster(), EXTRA_ARMOR_EFFECT, int(StatType.FIXED_ARMOR),
                                    int(extra_armor),
                                    name=EffectType.DaemonfleshPlate_ExtraArmor.name),
        AddPersistentData(DAEMONFLESH_PLATE, Owner(), _COUNTER_KEY, 1))
    return If(cond, then_, else_)


def daemonflesh_plate_reset_tree():
    """`...DaemonfleshPlate_ResetActiveAbility$$CreateBehaviour` = `ResetActiveAbility(Owner, true)
    + RemoveEffect(Owner, Nullable(1491))`."""
    return op_add(ResetActiveAbility(Owner(), ignore_turn_flag=True),
                  RemoveEffect(RESET_ACTIVE_EFFECT, Owner()))


def relic_vars(state: State, owner_id: int) -> tuple[int, int]:
    """`(extraArmor, nrOfAttacks)` au niveau de l'`AbilityState` sous lequel la relique est montee.

    `triggered_ability_state` rend le couple TERTIAIRE (`TertiaryAbilityLevel` /
    `TertiaryAbilityVariablesMultiplierPercentage`) quand `DaemonfleshPlate` arrive par l'item
    equipe, le couple PASSIF sinon -- exactement la distribution d'`UnitFactory$$Build`. Ni
    `extraArmor` ni `nrOfAttacks` ne figurent dans `variablesAffectedByRarityBonus` du gameconfig de
    la relique, donc le multiplicateur ne s'applique pas ; on le passe quand meme, parce que c'est
    `ability_var` (mirror de `GetVariableForLevel`) qui en decide, pas nous."""
    lvl, mult = triggered_ability_state(state, owner_id, ABILITY_ID)
    return (int(ability_var(ABILITY_ID, EXTRA_ARMOR_KEY, lvl, multiplier_pct=mult) or 0),
            int(ability_var(ABILITY_ID, NR_OF_ATTACKS_KEY, lvl, multiplier_pct=mult) or 0))


class DaemonfleshPlateAbility(TriggeredAbility):
    """`DaemonfleshPlateAbility` -- a CHAQUE attaque du porteur : une pile de `+extraArmor`
    `FixedArmor` de plus, jusqu'a la `nrOfAttacks`-ieme, qui les retire toutes et arme le re-armement
    de l'active (effet 1491).

    `On(9 = Attack)` est l'evenement GENERIQUE de fin d'attaque (`FinishAttackOperation`, emis pour
    l'attaque NORMALE comme pour une ability) ; `get_OwnerIsCaster` = le porteur est l'attaquant."""
    event_id = int(EventTriggerType.Attack)                            # 9
    TRIGGERED_ABILITY_ID = DAEMONFLESH_PLATE                           # 1493

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return ev.actor_id == self.owner_id                            # get_OwnerIsCaster

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        extra_armor, nr_of_attacks = relic_vars(state, self.owner_id)
        if nr_of_attacks <= 0:
            # `GetVariableForLevel` n'a rien rendu (relique non seedee) -> l'arbre natif comparerait
            # a `-1` et prendrait TOUJOURS la branche THEN. Le port refuse d'inventer ce regime.
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        daemonflesh_plate_behaviour_tree(extra_armor, nr_of_attacks).execute(entities, ectx)
        emitted = dict()
        for name, payload in ectx.emitted:
            emitted.setdefault(name, []).append(payload)
        stacked = sum(1 for p in emitted.get("AddStaticStatModifierEffect", ()))
        removed = sum(int(p.get("removed") or 0) for p in emitted.get("RemoveEffect", ()))
        posees = [q for p in emitted.get("AddPersistentData", ()) for q in (p.get("posees") or ())]
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "extra_armor": int(extra_armor), "nr_of_attacks": int(nr_of_attacks),
                "stacked": stacked, "removed": removed,
                "counter": (posees[0]["value"] if posees else None),
                "reset_armed": bool(emitted.get("AddEffect"))}


class DaemonfleshPlateResetActiveAbility(TriggeredAbility):
    """`DaemonfleshPlate_ResetActiveAbility` -- a la FIN DE PHASE, si le porteur porte le marqueur
    1491, son ability active est RE-ARMEE (`ResetActiveAbilityOperation`) et le marqueur retire.

    Le decalage d'une PHASE est du natif, pas du port : la branche THEN pose 1491 pendant l'attaque,
    et c'est le `On(PhaseEnd)` de CETTE ability qui consomme le marqueur -- donc le re-armement n'est
    jamais visible dans l'attaque elle-meme."""
    event_id = int(EventTriggerType.PhaseEnd)                          # 0x3a = 58

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `HasEffect(Owner, 1491, onlyActive = false, sourceFlags = 6)`
        if state.effects is None:
            return False
        return state.effects.has_effect(int(self.owner_id), effect_type=RESET_ACTIVE_EFFECT)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, None)
        daemonflesh_plate_reset_tree().execute(entities, ectx)
        resets = [p for (n, p) in ectx.emitted if n == "ResetActiveAbility"]
        removed = sum(int(p.get("removed") or 0) for (n, p) in ectx.emitted if n == "RemoveEffect")
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "reset": bool(resets and resets[0].get("reset")),
                "gate": (resets[0].get("gate") if resets else None),
                "marker_removed": removed}
