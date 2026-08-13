"""`Dw02AdvancedBurstCannon` -- relique `R_Crit_Dw02AdvancedBurstCannon`, `TriggeredAbilityType`
0x5c4 = **1476**, UN porteur autorise (`items[*].allowedUnits`) : `tauCrisis` << Re'vas >>, HERO du
pool rank 17. #1012.

i2 (`Abilities/Dw02AdvancedBurstCannon_CurrentLevelDescription`) : << Each time Re'vas attacks, she
gains +{[extraPierceRatio]}% pierce ratio. After attacking {[nrOfAttacks]} times, this bonus is
reset, and Re'vas can use her active ability again. >>

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- UNE classe native, UN arbre
================================================================================================
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Dw02AdvancedBurstCannonAbility` (parent
`IdunBattle.Entities.Abilities.BaseTriggeredAbility`, `frida/classes.tsv`) porte SES DEUX corps dans
les tables -- contrairement a `DaemonfleshPlateAbility`, rien n'est ici deduplique.

## `...Dw02AdvancedBurstCannonAbility$$CreateTrigger` -- MIRROR

    On( 9 = EventTriggerType.Attack, ownerNeedsToBeAlive = 1 )
  & get_OwnerIsCaster
  & NOT IsSpecialActiveAbility

## `...Dw02AdvancedBurstCannonAbility$$CreateBehaviour(abilityState, triggerType)` -- MIRROR

    counter = GetPersistentData( AbilityOrEffect(Dw02AdvancedBurstCannon), Owner@DSLSelectors+0x30,
                                 Get(<literal de chaine>) )
    cond    = AmountIsEqualOrGreater( counter,
                                      Subtract( ConfigVar(0x4e = nrOfAttacks, abilityState, config),
                                                <DSLFormulas+0x20> = Direct(1) ) )
    THEN    = (   RemoveEffect( Owner@+0x30, Nullable(0x5be = Dw02AdvancedBurstCannon_ExtraPierceRatio) )
                & ResetActiveAbility( Owner@+0x30, allowUseless = true ) )
              & ClearPersistentData( AbilityOrEffect(Dw02AdvancedBurstCannon), Owner@+0x30,
                                     Get(<literal>) )
    ELSE    = AddStaticStatModifierEffect( targets = Caster@DSLSelectors+0x48,
                                           0x5be = Dw02AdvancedBurstCannon_ExtraPierceRatio,
                                           stat   = 0x1a = StatType.ExtraPierce,
                                           amount = ConfigVar(0x3f = extraPierceRatio),
                                           turns  = null, isHidden = false )
              & AddPersistentData( AbilityOrEffect(Dw02AdvancedBurstCannon), Owner@+0x30,
                                   Get(<literal>), <DSLFormulas+0x20> = Direct(1) )
    return    If( cond, THEN, ELSE )

**L'ORDRE EST LU, ET C'EST CELUI DE `DaemonfleshPlate`, PAS CELUI DE `VolummsMasterArtifice`.** Le
dernier appel du corps est `DSLBehaviors$$If(cond, THEN, ELSE)` : le `If` est la RACINE, donc le
compteur est teste AVANT tout increment, et le seuil est `nrOfAttacks - 1`.
`VolummsMasterArtifice`, lui, place son `AddPersistentData` a GAUCHE d'un `op_BitwiseAnd` dont le
`If` est le terme DROIT -- seuil sur le compteur DEJA incremente. Recopier le mauvais voisin
decalerait le reset d'une attaque ET ajouterait une pile.

`<DSLFormulas+0x20>` = `Direct(1)`, LU dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor` (+0x18 = 0,
**+0x20 = 1**, +0x28 = 2, +0x30 = 100, +0x38 = -1) -- MEME noeud aux deux emplois, donc le seuil est
`nrOfAttacks - 1` et l'increment est `+1`.
`IdunBattleLogic.Entities.DSLFormulas$$Subtract(a, b)` = `Sum(a, Multiply(b, +0x38 = Direct(-1)))`,
porte par le noeud `Difference`.

DEUX ECARTS AVEC `DaemonfleshPlate`, tous deux LUS et tous deux observables :
  1. le re-armement de l'active est **IMMEDIAT** (`ResetActiveAbility` est DANS la branche THEN) --
     `DaemonfleshPlate` pose un marqueur (effet 1491) et attend son `On(0x3a = PhaseEnd)`. Il n'y a
     donc ici NI seconde classe native, NI second effet, et l'i2 (<< and Re'vas can use her active
     ability again >>) tombe dans la meme attaque ;
  2. le gate `NOT IsSpecialActiveAbility` (absent de `DaemonfleshPlate`), ci-dessous.

================================================================================================
`IsSpecialActiveAbility` -- CE QU'IL EST, ET CE QUE LE PORT EN EXPRIME
================================================================================================
`IdunBattleLogic.Entities.DSLTriggers$$IsSpecialActiveAbility` -- MIRROR :

    <A>( TriggeringAbility@DSLSelectors+0x90 )  &  NOT <B>( TriggeringAbility@DSLSelectors+0x90 )

Les deux operandes lisent le MEME slot `<DSLSelectors+0x90>` = le canal `TriggeringAbility`
(`AbilityEntities+0x98`, cf. la table de `runner/state.py`). `<B>` est la classe que
`DSLTriggers$$IsNormalAttackOrHealOrRepair` et `$$IsActiveAbilityCountedAsUsed` allouent aussi
(meme slot de metadata) ; `<A>` n'est alloue QUE par cette fonction, donc AUCUN `DSLTriggers$$X`
nomme ne le nomme -- son NOM PROPRE reste un residu (les tables ne portent que cinq
`Entities.Triggers.Ability*Trigger$$ShouldTrigger`, et leurs `.ctor` sont deduplique).

CE QUI TRANCHE LA SEMANTIQUE, ce n'est donc pas le nom de `<A>` mais **l'autre call-site**. Le
predicat n'a que DEUX xrefs dans tout le binaire : ce `CreateTrigger`, et
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicPowerFistAbility$$CreateBehaviour`, dont
l'i2 dit mot pour mot : << These chances are doubled **if the attack is an active ability**. >>
=> `IsSpecialActiveAbility` = << l'ability declenchante est une ability ACTIVE **autre que**
l'attaque normale >>, et le gate de `Dw02` exclut donc les attaques d'ability active du comptage.

⚠ **CE GATE EST INERTE SUR LE SEUL PORTEUR AUTORISE, ET C'EST MESURE, PAS SUPPOSE.** La relique est
`isUniqueRelic` avec `allowedUnits = ["tauCrisis"]` ; l'unique active de Re'vas est
`EarlyWarningOverride` (1077), qui SOMME des drones et pose de l'Overwatch -- elle ne porte AUCUNE
attaque, donc aucun `On(9 = Attack)` ne peut arriver avec elle en ability declenchante. Le gate est
porte quand meme, parce que le natif le porte ; il ne peut se manifester que sur une GREFFE.

COTE PORT le canal est `TriggerEvent.ability_type` (`None` sur la voie NORMALE, l'id de l'ability
sur la voie ABILITY). << Est-ce une ACTIVE ? >> se lit sur les actives REELLEMENT MONTEES du caster
(`UnitContext.active_ability_levels`, `{ActiveAbilityType: (level, mult)}`, seede par
`snapshot._load_active_ability_levels`) -- l'ORDINAL SEUL ne trancherait rien, `TriggeredAbilityType`
et `ActiveAbilityType` partageant 233 valeurs. Cf. `_is_special_active_ability` pour les trois
degradations NOMMEES.

================================================================================================
CE QUE LA MECANIQUE FAIT, ETAGE PAR ETAGE
================================================================================================
Compteur `c` dans le `PersistentDataComponent` du porteur, cle
`(GetPersistentDataId(AbilityOrEffect(1476)), <literal>)`. `AddPersistentData` **ACCUMULE**
(`IdunBattle.Entities.Triggers.AddPersistentDataBehavior$$Execute` relit puis `add dword`).
Avec `N = nrOfAttacks` (**8** aux niveaux 1-5, **7** aux niveaux 6-10) et
`p = extraPierceRatio` (3 au niveau 1, 4 aux 2-5, 5 aux 6-9, **6** au niveau 10) :

    attaques 1..N-1 : `c >= N-1` faux -> ELSE : +1 pile de `+p` ExtraPierce, `c += 1`
    attaque  N      : `c = N-1 >= N-1` VRAI -> THEN : les N-1 piles sont retirees d'un coup,
                      l'ability active est RE-ARMEE dans la foulee, le compteur est vide

Le maximum de percage accumule est donc `(N-1) x p`, atteint JUSTE AVANT la N-ieme attaque -- pas
`N x p`. Confondre `>= N-1` avec `>= N` decalerait le reset d'une attaque ET ajouterait une pile ;
c'est le premier mutant du garde.

================================================================================================
FORME DU PORT (doctrine #149)
================================================================================================
* `CreateTrigger` COLLAPSE imperativement dans `matches` (patron `DaemonfleshPlateAbility`) ;
* `CreateBehaviour` est un ARBRE DSL dont les feuilles APPELLENT les Operations deja portees
  (`AddEffectOperation` + `apply_change_stat`, `RemoveEffectOperation`, `ResetActiveAbilityOperation`,
  `PersistentDataComponent`) -- aucune n'est re-ecrite ;
* MAGNITUDE ET SEUIL sont resolus par l'APPELANT (`triggered_ability_state` + `ability_var`), comme
  `DawnBlade` / `DaemonfleshPlate` / `VolummsMasterArtifice` : le natif les tient en noeuds
  `ConfigVar` paresseux, mais leur valeur ne depend que du couple `(TertiaryAbilityLevel,
  TertiaryAbilityVariablesMultiplierPercentage)` de l'`AbilityState` sous lequel la relique est
  montee -- fixe pour la bataille. Lire `passive_ability_level` a la place rendrait TOUJOURS le
  dernier palier (6/7 au lieu de 4/8 au niveau 3), en silence.

RESIDUS NOMMES
  * **la `dataKey`** : `DSLFormulas$$Get(<literal de chaine>)`, contenu non resoluble statiquement
    (cache de metadata IL2CPP). Le literal est PARTAGE avec `DaemonfleshPlateAbility` (xrefs), donc
    generique. Sans consequence : le sac est indexe par `(GetPersistentDataId(abilityOrEffect), key)`
    et le port porte la meme cle composite -- deux abilities partageant la chaine ne se marchent pas
    dessus. Le port ecrit `_COUNTER_KEY`, constante locale.
  * **`isHidden = false`** (7e argument d'`AddStaticStatModifierEffect`) : la feuille portee ne
    modelise pas ce drapeau (cosmetique -- affichage de l'icone d'effet).
  * **`allowUseless = true`** de `ResetActiveAbility` : porte tel quel (`ignore_turn_flag`).
  * **le NOM de `<A>`** dans `IsSpecialActiveAbility` (cf. plus haut) : la SEMANTIQUE est tranchee
    par le second call-site, le nom de classe reste non resolu.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If, op_and
from .....entities.effect_type import EffectType
from .....entities.formulas import Difference, GetPersistentData
from .....entities.selectors.accessors import Owner
from .....entities.selectors.tiles import Caster
from .....entities.stats import StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsEqualOrGreater
from .....entities.effects.magnitude import ability_var
from ....abilities.attack_type import NORMAL_ATTACK_KIND
from ....abilities.behaviours.ability_state import ResetActiveAbility
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddStaticStatModifierEffect, RemoveEffect
from ....abilities.behaviours.persistent_data import AddPersistentData, ClearPersistentData
from ....components import StatsComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

#: Cle du registre `RELIC_ABILITY_TRIGGERS` = le NOM gameconfig de l'ability de relique.
ABILITY_ID = "Dw02AdvancedBurstCannon"
#: `AbilityOrEffect(0x5c4)` des trois noeuds de persistent-data.
DW02_ADVANCED_BURST_CANNON = int(TriggeredAbilityType.Dw02AdvancedBurstCannon)      # 0x5c4 = 1476
#: `EffectType` 0x5be -- ⚠ `TriggeredAbilityType` 0x5be, lui, est `Vitarus` : le membre NOMME est
#: obligatoire, l'ordinal ne designe rien tout seul.
EXTRA_PIERCE_EFFECT = int(EffectType.Dw02AdvancedBurstCannon_ExtraPierceRatio)      # 0x5be = 1470

EXTRA_PIERCE_RATIO_KEY = "extraPierceRatio"   # `AbilityVariableType` 0x3f = 63
NR_OF_ATTACKS_KEY = "nrOfAttacks"             # `AbilityVariableType` 0x4e = 78

#: `DSLFormulas$$Get(<literal>)` -- cf. le residu nomme de l'en-tete : la CHAINE n'est pas resoluble
#: statiquement ; seule compte sa CONSTANCE sur les trois emplois de l'ability.
_COUNTER_KEY = "Dw02AdvancedBurstCannon"

#: `ResetActiveAbility(Owner@+0x30, allowUseless = true)`.
RESET_ALLOW_USELESS = True


def _is_special_active_ability(state: State, caster_id, ability_type) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$IsSpecialActiveAbility` =
    `<A>(TriggeringAbility@+0x90) & NOT <B>(TriggeringAbility@+0x90)` -- << l'ability declenchante
    est une ACTIVE autre que l'attaque normale >> (semantique tranchee par le second call-site
    `RelicPowerFistAbility`, cf. l'en-tete du module).

    TROIS degradations, toutes NOMMEES, toutes du cote qui ne peut pas INVENTER un blocage :

      1. `ability_type is None` -- c'est la voie NORMALE du port (`dispatch/attack.py` :
         << `ability_type` reste None sur la voie NORMALE >>) : le natif y aurait `IsNormalAttack`
         VRAI, donc `IsSpecialActiveAbility` FAUX. Exact, pas une approximation.
      2. `ability_type == NORMAL_ATTACK_KIND` (0x3f5 = 1013) -- le MARQUEUR de kind que le port
         thread sur les volets d'attaque normale (`_normal_attack_kind`). Meme branche `<B>`.
         ⚠ Ce qui n'est PAS couvert : l'id CONCRET de l'attaque normale de l'unite
         (`NormalAttackType@0x28`, per-unit -- `69` sur `ultraCalgar`). Le port ne le thread nulle
         part aujourd'hui sur `On(9)` ; s'il le faisait un jour, il entrerait ici comme une active
         du caster et le gate le rejetterait a tort. Residu, sans porteur aujourd'hui.
      3. `active_ability_levels` absent (canal `unitAbilityStates` non lie : `State` nu, capture
         rejouee) -- on ne PROUVE pas que l'ability est une ACTIVE, donc `<A>` se tait et le gate
         laisse passer. Degradation PERMISSIVE pour le compteur (une attaque de plus comptee), et
         elle est bornee : sur le seul porteur autorise, le gate est de toute facon inerte."""
    if ability_type is None:                                        # 1
        return False
    aid = int(ability_type)
    if aid == NORMAL_ATTACK_KIND:                                   # 2
        return False
    if caster_id is None:
        return False
    ent = state.get_entity(int(caster_id))
    sc = ent.get_component(StatsComponent) if ent is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    levels = getattr(ctx, "active_ability_levels", None) if ctx is not None else None
    if not levels:                                                  # 3
        return False
    return aid in levels


def dw02_advanced_burst_cannon_tree(extra_pierce_ratio: int, nr_of_attacks: int):
    """`...Dw02AdvancedBurstCannonAbility$$CreateBehaviour` -- MIRROR 1:1 (cf. l'en-tete du module).

    `extra_pierce_ratio` / `nr_of_attacks` = les deux `ConfigVar`, resolus par l'appelant (meme choix
    et meme justification que `DaemonfleshPlate`). Le `- 1` reste un noeud `Difference` = le
    `Subtract(a, <DSLFormulas+0x20> = Direct(1))` natif, pour que le seuil ne soit pas re-ecrit en
    scalaire."""
    counter = GetPersistentData(DW02_ADVANCED_BURST_CANNON, Owner(), _COUNTER_KEY)
    cond = AmountIsEqualOrGreater(counter, Difference(Const(int(nr_of_attacks)), Const(1)))
    # THEN -- `(RemoveEffect & ResetActiveAbility) & ClearPersistentData` (ordre des `op_BitwiseAnd`)
    then_ = op_and(
        op_and(RemoveEffect(EXTRA_PIERCE_EFFECT, Owner()),
               ResetActiveAbility(Owner(), ignore_turn_flag=RESET_ALLOW_USELESS)),
        ClearPersistentData(DW02_ADVANCED_BURST_CANNON, Owner(), _COUNTER_KEY))
    # ELSE -- `AddStaticStatModifierEffect & AddPersistentData`
    else_ = op_and(
        AddStaticStatModifierEffect(Caster(), EXTRA_PIERCE_EFFECT, int(StatType.EXTRA_PIERCE),
                                    int(extra_pierce_ratio),
                                    name=EffectType.Dw02AdvancedBurstCannon_ExtraPierceRatio.name),
        AddPersistentData(DW02_ADVANCED_BURST_CANNON, Owner(), _COUNTER_KEY, 1))
    return If(cond, then_, else_)


def relic_vars(state: State, owner_id: int) -> "tuple[int, int]":
    """`(extraPierceRatio, nrOfAttacks)` au niveau de l'`AbilityState` sous lequel la relique est
    montee.

    `triggered_ability_state` rend le couple TERTIAIRE (`TertiaryAbilityLevel` /
    `TertiaryAbilityVariablesMultiplierPercentage`) quand `Dw02AdvancedBurstCannon` arrive par l'item
    equipe, le couple PASSIF sinon -- exactement la distribution d'`UnitFactory$$Build`. Aucune des
    deux variables n'est dans `variablesAffectedByRarityBonus` du gameconfig de la relique, donc le
    multiplicateur ne mord pas ; on le passe quand meme, parce que c'est `ability_var` (mirror de
    `GetVariableForLevel`) qui en decide, pas nous."""
    lvl, mult = triggered_ability_state(state, owner_id, ABILITY_ID)
    return (int(ability_var(ABILITY_ID, EXTRA_PIERCE_RATIO_KEY, lvl, multiplier_pct=mult) or 0),
            int(ability_var(ABILITY_ID, NR_OF_ATTACKS_KEY, lvl, multiplier_pct=mult) or 0))


class Dw02AdvancedBurstCannonAbility(TriggeredAbility):
    """`Dw02AdvancedBurstCannonAbility` -- a CHAQUE attaque du porteur qui n'est pas une ability
    ACTIVE : une pile de `+extraPierceRatio` `ExtraPierce` de plus, jusqu'a la `nrOfAttacks`-ieme,
    qui les retire toutes et RE-ARME l'ability active dans la foulee.

    `On(9 = Attack)` est l'evenement GENERIQUE de fin d'attaque (`FinishAttackOperation`, emis pour
    l'attaque NORMALE comme pour une ability) ; `get_OwnerIsCaster` = le porteur est l'attaquant."""
    event_id = int(EventTriggerType.Attack)                            # 9
    TRIGGERED_ABILITY_ID = DW02_ADVANCED_BURST_CANNON                  # 1476

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsCaster` -- le vecteur `On(9)` publie l'attaquant en `actor`/`caster`.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        # `On(9, ownerNeedsToBeAlive = 1)` -- `<DSLTriggers+0x20>`.
        owner = state.get_entity(int(self.owner_id))
        ouc = owner.get_component(UnitComponent) if owner is not None else None
        if owner is None or (ouc is not None and not ouc.alive):
            return False
        # `NOT IsSpecialActiveAbility`
        return not _is_special_active_ability(state, ev.actor_id,
                                              getattr(ev, "ability_type", None))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        extra_pierce_ratio, nr_of_attacks = relic_vars(state, self.owner_id)
        if nr_of_attacks <= 0:
            # `GetVariableForLevel` n'a rien rendu (relique non seedee) -> l'arbre natif comparerait
            # a `-1` et prendrait TOUJOURS la branche THEN. Le port refuse d'inventer ce regime.
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, int(self.owner_id), None, actor_id=ev.actor_id)
        dw02_advanced_burst_cannon_tree(extra_pierce_ratio, nr_of_attacks).execute(entities, ectx)
        emitted: dict = {}
        for name, payload in ectx.emitted:
            emitted.setdefault(name, []).append(payload)
        stacked = sum(1 for _ in emitted.get("AddStaticStatModifierEffect", ()))
        removed = sum(int(p.get("removed") or 0) for p in emitted.get("RemoveEffect", ()))
        posees = [q for p in emitted.get("AddPersistentData", ()) for q in (p.get("posees") or ())]
        resets = emitted.get("ResetActiveAbility", ())
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "extra_pierce_ratio": int(extra_pierce_ratio),
                "nr_of_attacks": int(nr_of_attacks),
                "stacked": stacked, "removed": removed,
                "counter": (posees[0]["value"] if posees else None),
                "reset": bool(resets and resets[0].get("reset")),
                "reset_gate": (resets[0].get("gate") if resets else None),
                "dsl": True}
