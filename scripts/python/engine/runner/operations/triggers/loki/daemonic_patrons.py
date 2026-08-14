"""`DaemonicPatrons_Finale` (`TriggeredAbilityType` 0x5c1 = **1473**) -- les DEUX dernieres phrases
de l'i2 de l'active `1203 DaemonicPatrons` (`emperFlawlessBlade` << Hascule >>, HERO Emperor's
Children). `#911-r1`, `docs/rl/case-911-daemonic-patrons.md` Sec.6.

    << If he defeats an adjacent Taunted enemy while being watched, he can use this ability again.
       If he does not, he loses 30% of his current Health. >>

DEUX classes natives pour UN seul `TriggeredAbilityType` -- meme forme que `Lakrimae` (1541) et
`LetTheGalaxyBurn` : `...Triggered.Loki.DaemonicPatrons_FinaleSuccessAbility` et
`...Triggered.Loki.DaemonicPatrons_FinaleFailAbility`.

================================================================================================
1. LE CHEMIN DE MONTAGE -- `GetDerivedTriggeredAbilities`, et c'est ce que le residu BLOQUAIT
================================================================================================
La fiche `#911-r1` portait `BLOCAGE: seeding`, sur cet enonce : << `1473` n'est NI dans
`activeAbilities` NI dans `passiveAbilities` du kit d'`emperFlawlessBlade` (gameconfig relu), donc
le canal par lequel le natif l'inscrit n'est pas etabli >>. Le kit est bien relu et il est bien
muet -- mais le canal, lui, EXISTE et ne passe pas par le kit :

    idun...StaticBattleRules.ActiveAbility$$.cctor, dict range en `<statics>+0x30`
    (= celui que lit `...$$GetDerivedTriggeredAbilities`) :
        GetDerivedTriggeredAbilities[0x4b3 /* 1203 DaemonicPatrons */] = [ 0x5c1 /* 1473 */ ]

LU au decompile : la `List` est construite (`List$$.ctor`), `Add(0x5c1)`, puis `Dictionary$$Add(dict,
0x4b3, list)` -- et l'entree IMMEDIATEMENT SUIVANTE du meme dict est `[0x405 /* 1029 Drachnyen */] =
[0x5cd /* 1485 */]`, c'est-a-dire le cas DEJA porte par `#BL-1029r` (`loki/drachnyen.py`), qui avait
etabli l'identite de ce slot. Le dict est referme par `*(statics + 0x30) = lVar1`, ce qui NOMME le
slot sans deduction.

⇒ Cote port c'est `ACTIVE_ABILITY_TRIGGERS` (cle = le NOM gameconfig de l'ACTIVE), monte par
`IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities` : **toute unite qui POSSEDE l'active
1203 porte 1473 des l'init**, sans aucun cast prealable et sans aucune entree de kit. Le rail est le
MEME que `Hailstrike` (1214 -> 1507), `EmpyricAmbush` (1232 -> 1555) et `Drachnyen` (1029 -> 1485).
Le `BLOCAGE: seeding` est donc REFUTE, pas contourne.

================================================================================================
2. FACE SUCCESS -- `DaemonicPatrons_FinaleSuccessAbility`
================================================================================================
`$$CreateTrigger` (MIRROR du decompile, build `rnca9r7q6c`, dans l'ordre des `op_BitwiseAnd`) :

    On( 0x36 = EventTriggerType.UnitDefeated, ownerNeedsToBeAlive = 1 )
  & get_OwnerIsActor
  & HasEffect( Target@<DSLSelectors+0x60>, 0x1b  = 27   Taunted_OnlySpecificTargets, onlyActive 0, 6 )
  & HasEffect( Actor@<DSLSelectors+0x40>,  0x5b8 = 1464 DaemonicPatrons_ExtraDamage,  onlyActive 0, 6 )

`$$CreateBehaviour` -- **ABSENT DES DEUX TABLES**, retrouve par le bloc de `methodPointers` :

    ResetActiveAbility( Owner@<DSLSelectors+0x30>, allowUseless: 1 )

⚠ COMMENT IL A ETE RETROUVE (l'absence d'un symbole ne prouve rien, cf. `CLAUDE.md`). Les xrefs
DATA des trois corps LISIBLES de la paire tombent dans un meme bloc de pointeurs, et ce bloc est
structure en TRIPLETS `(CreateTrigger, CreateBehaviour, .ctor)` -- le `.ctor` etant le corps vide
partage, identique aux trois slots voisins :

    +0x00  Success.CreateTrigger    (xref connue)
    +0x08  Success.CreateBehaviour  <- LE SLOT CHERCHE
    +0x10  .ctor  (corps vide partage)
    +0x18  Fail.CreateTrigger       (xref connue)
    +0x20  Fail.CreateBehaviour     (xref connue)
    +0x28  .ctor  (meme corps vide)

Le pointeur du slot manquant est publie par ghidra sous
`...Triggered.Loki.TacticalPrecision_ResetAbility$$CreateBehaviour` -- corps DEDUPLIQUE par l'ICF
(aucun litteral distinctif : un seul appel a `ResetActiveAbility`), partage par **8** sites. Le nom
du proprietaire ne dit donc rien de l'appelant ; c'est l'appartenance du SLOT qui tranche. MEME
forme, MEME corps partage et MEME propietaire arbitraire que `EmpyricAmbush_ResetAbility` (cf.
`loki/empyric_ambush.py`), ce qui vaut controle croise.

Le litteral du 2e argument est **1** (`CONCAT71(..., 1)`), la ou
`InspiredToGreatnessAbility$$ExecuteBehaviour` passe **0** : il fait sauter le gate de tour de
`IdunBattle.Core.Services.BattleQuery$$EntityCanHaveActiveAbilityReset`. Necessaire ici pour la meme
raison que chez Lhykhis -- Hascule vient d'agir quand la mort est drainee, donc son
`UnitFlag.TurnFinished` peut deja etre pose.

================================================================================================
3. FACE FAIL -- `DaemonicPatrons_FinaleFailAbility`, et LA FICHE SE TROMPAIT DE LITTERAL
================================================================================================
`$$CreateTrigger` (MIRROR du decompile) :

    On( 0x40 = EventTriggerType.EffectRemoved, ownerNeedsToBeAlive = 1 )
  & get_OwnerIsTarget
  & CurrentAbilityIs( AbilityOrEffect( 0x5b9 = 1465 EffectType.DaemonicPatrons_DmgReduction ) )
  & NOT CanUseAbility( Owner@<DSLSelectors+0x30>, 0x4b3 = 1203 ActiveAbilityType.DaemonicPatrons )

⚠ **LE 3e CONJOINT N'EST PAS `AbilityOrEffect(this)`.** La fiche `#911-r1` (et le bloc recopie en
tete de `runner/abilities/emperorschildren.py`) ecrivait `CurrentAbilityIs(<AbilityOrEffect(this)>)`.
Le pseudo-C ne montre effectivement qu'un `op_Implicit(local_28)` sur un tampon de pile dont ghidra
n'affiche pas l'initialisation -- mais l'immediat est LU AUX OCTETS, juste avant le `call` :

    ...FinaleFailAbility$$CreateTrigger+0xa8 :  BA B9 05 00 00   mov edx, 0x5b9
                                                E8 ...           call AbilityOrEffect$$op_Implicit

`0x5b9` = **1465**, l'effet `DaemonicPatrons_DmgReduction`. Porter la fiche telle qu'ecrite aurait
compare `1473` (l'id de la triggered) a la valeur que le vecteur `On(EffectRemoved)` met dans
`CurrentAbility` -- qui est le TYPE DE L'EFFET RETIRE. Les deux ne peuvent jamais etre egaux : la
classe serait entree au registre et serait restee **INERTE**, sans erreur ni crash. C'est exactement
le mode de degradation silencieuse que la doctrine du registre decrit.

⚠ **`CanUseAbility` N'EST PAS `AttackQuery$$CanUseAbility`** (le gate stun/taunt, mirror
`engine/battle_query.py::can_use_ability`), qui est ce qu'un lecteur du depot aurait pris au nom. Le
noeud DSL est `IdunBattleLogic.Entities.DSLTriggers$$CanUseAbility` ->
`Idun.Source.IdunBattle.Logic.Entities.Triggers.CanUseAbilityTrigger$$ShouldTrigger`, dont le corps
LU est :

    unit = <trigger+0x10 = le selecteur>.Select(entities)     ; null -> false
    comp = unit.GetComponent<ActiveAbilityComponent>()        ; null -> false
    ab   = ActiveAbilityComponent$$GetActive(comp, <trigger+0x18 = l'ActiveAbilityType>)
    if (ab == null) return false
    return ActiveAbility$$get_CanCurrentlyBeUsed(ab)

-> la propriete COMPOSITE (charge consommee + cooldown + munitions), portee par
`ActiveAbilitiesComponent`.`can_currently_be_used` (`runner/components.py`). Le gate stun/taunt n'y
figure PAS.

`$$CreateBehaviour` (MIRROR du decompile) :

    DirectDamage( <DSLBehaviors+0x78>,
                  caster  = Owner@<DSLSelectors+0x30>,
                  targets = Owner@<DSLSelectors+0x30>,
                  amount  = PercentageOf( StatAmount(Owner@+0x30, 5 = StatType.HEALTH, 0, 0),
                                          GetVariableForLevel(0x26 = hpPct, abilityState) ),
                  abilityOrEffect = AbilityOrEffect(this.Id = 1473),
                  selectionType = 3,
                  options = <struct ZEROEE> )

⚠ QUALIFICATION D'ENUM : `0x26` est un **`AbilityVariableType`** (= `hpPct`) parce que l'accesseur
appele est `GetVariableForLevel`, dont le type DECLARE du 2e parametre tranche. Contre-epreuve :
`AbilityConstantType(0x26)` nomme `lootMultiplierIncreasePct`, une cle sans aucun rapport -- et la
config 1203 n'a pas cette cle (ses trois variables sont `extraDmg`, `dmgReductionPct`, `hpPct`), donc
la confusion aurait lu une cle INEXISTANTE **sans lever la moindre erreur**.

Le `damageProfile` est ABSENT de la signature native (six arguments, `options` integralement zeroee)
-> `profile=None` cote port, exactement comme l'autre call-site porte de cette feuille
(`ArmourOfShriekingSoulsEffect$$CreateTargetTriggerBehaviour`).

================================================================================================
4. LE CANAL D'ACTEUR SUR `On(UnitDefeated)` -- lecture STRICTE
================================================================================================
`get_OwnerIsActor` = `AreEqual(Owner@+0x30, Actor@+0x40)`. Sur le vecteur MORT, l'ACTEUR natif est
le TUEUR (`AbilityEntities+0x00/+0x08`, ecrit par `KillUnitOperation$$Execute` depuis le slot 0x158)
-- tueur inconnu ⇒ le slot est NUL ⇒ `AreEqual` est FAUX.

Cote port, `unit_defeated_triggers` remplit `ev.actor_id = killer_id if killer_id is not None else
dying_id` : le repli rabat l'acteur sur le MOURANT. On lit donc `ev.killer_id`, le canal STRICT --
meme lecture, et pour la meme raison ecrite, que `loki/empyric_ambush.py`, l'autre consommateur de
`get_OwnerIsActor` sur ce meme event.

⚠ RESIDU PREEXISTANT, NOMME, HORS PERIMETRE : `loki/trophy_taker.py` lit `ev.actor_id` pour le MEME
predicat sur le MEME event, donc son gate passe aussi quand le porteur est la VICTIME d'une mort sans
tueur identifie. Les deux modules ne peuvent pas avoir raison ensemble. Ce port ne tranche pas pour
autrui : il suit la lecture qui porte sa justification.

================================================================================================
5. CE QUE CE PORT NE FAIT PAS
================================================================================================
* **Aucun gate d'ADJACENCE.** L'i2 dit << an adjacent Taunted enemy >>, le `CreateTrigger` n'en
  porte AUCUN : les quatre conjoints sont ceux ecrits ci-dessus. L'adjacence est de fait portee par
  l'effet `Taunted_OnlySpecificTargets`, que 1203 ne pose que sur la cible du cast. On mirror
  l'arbre, pas la phrase marketing.
* **La face DECISION** (`DaemonicPatronsPlaybook`) n'est pas touchee.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_variable_type import AbilityVariableType
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import PercentageOf, StatAmount
from .....entities.selectors.accessors import Owner
from .....entities.stats import StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.behaviours.ability_state import ResetActiveAbility
from ....abilities.behaviours.combat import DirectDamage
from ....abilities.behaviours.context import entities_from_state
from ....components import ActiveAbilitiesComponent, StatsComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `ACTIVE_ABILITY_TRIGGERS` = le NOM gameconfig de l'ability ACTIVE porteuse
#: (`units.activeAbilities`), ici `ActiveAbilityType 0x4b3 = 1203`. C'est AUSSI la config que lit la
#: face FAIL : `StaticBattleRules.TriggeredAbility$$.cctor` range `GetActiveAbilityUsedForConfig
#: [0x5c1] = 0x4b3` (le voisin immediat du `0x5cd -> 0x405` de `Drachnyen`), et le gameconfig n'a
#: AUCUNE entree `DaemonicPatrons_Finale`.
DAEMONIC_PATRONS_ABILITY = "DaemonicPatrons"
DAEMONIC_PATRONS_ACTIVE = int(ActiveAbilityType.DaemonicPatrons)             # 0x4b3 = 1203
DAEMONIC_PATRONS_FINALE = int(TriggeredAbilityType.DaemonicPatrons_Finale)   # 0x5c1 = 1473

#: `HasEffect(Target@+0x60, 0x1b, ...)` -- le bond TAUNT que 1203 pose sur la cible de son cast.
DP_TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)                     # 0x1b = 27
#: `HasEffect(Actor@+0x40, 0x5b8, ...)` -- le buff OFFENSIF que 1203 pose sur le caster.
DP_EXTRA_DAMAGE = int(EffectType.DaemonicPatrons_ExtraDamage)                # 0x5b8 = 1464
#: `CurrentAbilityIs(AbilityOrEffect(0x5b9))` -- le buff DEFENSIF, dont le RETRAIT arme la face FAIL.
#: Litteral LU AUX OCTETS (`mov edx, 0x5b9`), cf. Sec.3 : ce n'est PAS `AbilityOrEffect(this)`.
DP_DMG_REDUCTION = int(EffectType.DaemonicPatrons_DmgReduction)              # 0x5b9 = 1465

#: `GetVariableForLevel(0x26)` -- `AbilityVariableType.hpPct`. L'ACCESSEUR tranche l'enum (cf. Sec.3).
DP_VAR_HP_PCT = AbilityVariableType.hpPct                                    # 0x26 = 38


def _has_effect(state: State, unit_id: Optional[int], effect_type: int) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$HasEffect(sel, effectType, onlyActive: 0, targetType: 6)`
    -- `onlyActive = 0` ⇒ un effet present mais INACTIF compte. `None` (pas d'`EffectsState`) ⇒ FAUX,
    jamais << inconnu = vrai >>."""
    if unit_id is None or state.effects is None:
        return False
    return bool(state.effects.has_effect(int(unit_id), effect_type=int(effect_type)))


def _can_use_ability(state: State, unit_id: Optional[int], active_type: int) -> bool:
    """`CanUseAbilityTrigger$$ShouldTrigger` -- MIRROR du decompile (corps cite en Sec.3) :
    `GetActive(comp, activeType)` puis `ActiveAbility$$get_CanCurrentlyBeUsed`.

    Chaque etage rend FAUX quand il ne trouve rien -- unite absente, `ActiveAbilityComponent` absent
    (canal `allAbilities` non demande a `decisionView`), ou ability non possedee. Ce n'est PAS une
    degradation : c'est le `return 0` de chacun des trois gates natifs."""
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    if e is None:
        return False
    comp = e.get_component(ActiveAbilitiesComponent)
    if comp is None:
        return False
    # `ActiveAbilitiesComponent.get` EST le mirror d'`ActiveAbilityComponent$$GetActive` (lookup par
    # `ActiveAbilityType` dans la `KeyedCollection` @+0x20).
    ab = comp.get(int(active_type))
    if ab is None:
        return False
    return bool(ab.can_currently_be_used())


def daemonic_patrons_finale_reset_tree() -> ResetActiveAbility:
    """Arbre de `...FinaleSuccessAbility$$CreateBehaviour` (MIRROR, cf. Sec.2) :
    `ResetActiveAbility(Owner@<DSLSelectors+0x30>, allowUseless: 1)`.

    `allowUseless = 1` est le litteral LU (`CONCAT71(..., 1)`) ; il fait sauter le gate de tour de
    `BattleQuery$$EntityCanHaveActiveAbilityReset`. La feuille porte ce champ sous le nom
    `ignore_turn_flag` (`abilities/behaviours/ability_state.py`) -- meme `this+0x58`."""
    return ResetActiveAbility(Owner(), True)


def daemonic_patrons_finale_fail_tree(hp_pct: int) -> DirectDamage:
    """Arbre de `...FinaleFailAbility$$CreateBehaviour` (MIRROR, cf. Sec.3) :

        DirectDamage( caster = Owner, targets = Owner,
                      PercentageOf( StatAmount(Owner, 5 = HEALTH), hpPct ),
                      AbilityOrEffect(1473), 3, <options ZEROEE> )

    `StatAmount(unit, 5, 0, 0)` = les PV **COURANTS** (`variant = 0`), pas le maximum -- l'i2 dit
    bien << 30% of his current Health >>. `profile=None` : le `damageProfile` est ABSENT de la
    signature native (cf. Sec.3), donc le degat passe integralement par l'armure du defenseur."""
    amount = PercentageOf(Const(int(hp_pct)),
                          StatAmount(Owner(), int(StatType.HEALTH)), 0)
    return DirectDamage(Owner(), amount, source_sel=Owner(), profile=None,
                        ability_type=DAEMONIC_PATRONS_FINALE)


class DaemonicPatronsFinaleSuccessAbility(TriggeredAbility):
    """`DaemonicPatrons_FinaleSuccessAbility` (triggered 1473) -- cf. Sec.2 pour les deux arbres.

    `owner_id` = l'unite qui POSSEDE l'active 1203 (Hascule), instanciee par le registre
    `ACTIVE_ABILITY_TRIGGERS` (mirror de `GetDerivedTriggeredAbilities`).

    OBSERVABLE : apres un cast de 1203, l'actif de Hascule est consomme
    (`decisionView.units[].abilities[].usable == false`). S'il ACHEVE un ennemi porteur du taunt 27
    alors qu'il porte encore 1464, l'actif redevient utilisable (`usable: true`, `cooldown: null`)."""
    event_id = int(EventTriggerType.UnitDefeated)          # On(0x36 = 54, ownerNeedsToBeAlive = 1)
    TRIGGERED_ABILITY_ID = DAEMONIC_PATRONS_FINALE

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # --- get_OwnerIsActor : AreEqual(Owner@+0x30, Actor@+0x40) ----------------------------
        # Canal STRICT `ev.killer_id`, cf. Sec.4 (`ev.actor_id` est rabattu sur le MOURANT par le
        # repli du vecteur, ce que le slot natif ne fait pas -- il reste NUL).
        killer = ev.killer_id
        if killer is None or int(killer) != int(self.owner_id):
            return False
        victim = ev.dying_id if ev.dying_id is not None else ev.target_id
        if victim is None:
            return False
        # --- HasEffect(Target@+0x60, 0x1b = 27, onlyActive 0, 6) : la VICTIME est tauntee ------
        if not _has_effect(state, victim, DP_TAUNTED):
            return False
        # --- HasEffect(Actor@+0x40, 0x5b8 = 1464, onlyActive 0, 6) : le TUEUR porte le buff ----
        # L'`Actor` natif etant le TUEUR (Sec.4), et `get_OwnerIsActor` venant de le contraindre a
        # etre l'Owner, les deux slots designent ici la meme entite.
        return _has_effect(state, killer, DP_EXTRA_DAMAGE)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        daemonic_patrons_finale_reset_tree().execute(
            entities_from_state(state, self.owner_id, ev.target_id, ev.actor_id), ectx)
        reset = [p for n, p in ectx.emitted if n == "ResetActiveAbility"]
        if not reset:
            return None
        return {"ability": "DaemonicPatrons_FinaleSuccess", "owner": int(self.owner_id),
                "killed": None if ev.dying_id is None else int(ev.dying_id),
                "reset": reset}


class DaemonicPatronsFinaleFailAbility(TriggeredAbility):
    """`DaemonicPatrons_FinaleFailAbility` (triggered 1473) -- cf. Sec.3 pour les deux arbres.

    OBSERVABLE : quand l'effet 1465 `DaemonicPatrons_DmgReduction` quitte Hascule (expiration du
    timer, ou retrait) alors qu'il ne peut TOUJOURS pas re-caster 1203 -- c'est-a-dire que la face
    SUCCESS n'a pas re-arme l'actif --, il perd `hpPct` % de ses PV COURANTS.

    ⚠ INERTE PAR CONSTRUCTION quand la face SUCCESS a joue : celle-ci re-arme 1203, donc
    `CanUseAbility(Owner, 1203)` devient VRAI et le 4e conjoint (`NOT ...`) ferme le gate. Les deux
    faces sont les DEUX BRANCHES d'un meme << if he does / if he does not >>, et c'est le natif qui
    les rend mutuellement exclusives par cet unique predicat -- pas un `else` cote port."""
    event_id = int(EventTriggerType.EffectRemoved)         # On(0x40 = 64, ownerNeedsToBeAlive = 1)
    TRIGGERED_ABILITY_ID = DAEMONIC_PATRONS_FINALE

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # --- get_OwnerIsTarget : l'effet retire etait SUR le porteur ---------------------------
        # `RemoveEffectOperation$$Execute` n'ecrit que `+0x10`/`+0x18` (target = owner = le porteur
        # de l'effet) -- cf. `dispatch/move_death.py::_effect_vector_triggers`.
        if ev.target_id is None or int(ev.target_id) != int(self.owner_id):
            return False
        # --- CurrentAbilityIs(AbilityOrEffect(0x5b9 = 1465)) -----------------------------------
        # Sur le vecteur de RETRAIT, `CurrentAbility` (+0x60) porte le TYPE DE L'EFFET retire et
        # `TriggeringAbility` (+0x98) reste VIDE (#306) : on lit donc `ev.triggering_ability`, le
        # mirror de `+0x60`, comme `loki/ecstatic_slaughter.py` sur le vecteur symetrique de POSE.
        if ev.triggering_ability is None or int(ev.triggering_ability) != DP_DMG_REDUCTION:
            return False
        # --- NOT CanUseAbility(Owner@+0x30, 0x4b3 = 1203) --------------------------------------
        return not _can_use_ability(state, self.owner_id, DAEMONIC_PATRONS_ACTIVE)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        e = state.get_entity(int(self.owner_id))
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = getattr(sc, "ctx", None) if sc is not None else None
        if ctx is None:
            return None
        # `GetVariableForLevel(0x26 = hpPct, abilityState)` -- l'`AbilityState` passe par le natif est
        # celui de la config 1203 (`GetActiveAbilityUsedForConfig[1473] = 1203`), donc le niveau
        # d'ability ACTIVE du porteur et son multiplicateur de rarete.
        lvl = getattr(ctx, "active_ability_level", None)
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
        pct = ability_var(DAEMONIC_PATRONS_ABILITY, DP_VAR_HP_PCT.name, lvl, multiplier_pct=mult)
        if not pct:
            return None            # config incomplete -> aucun degat INVENTE
        ectx = ExecutionContext(state=state, rng=state.rng)
        daemonic_patrons_finale_fail_tree(int(pct)).execute(
            entities_from_state(state, self.owner_id, ev.target_id), ectx)
        hit = next((p for n, p in ectx.emitted if n == "DirectDamage"), None)
        atk = (hit or {}).get("attack") or {}
        # ⚠ DIAGNOSTIC SERIALISABLE : on n'expose PAS l'`atk` brut (il porte un `set` dans
        # `attack_state`, que `json.dumps` refuse) -- meme precaution que `loki/drachnyen.py`.
        return {"ability": "DaemonicPatrons_FinaleFail", "owner": int(self.owner_id),
                "hp_pct": int(pct), "total": atk.get("total"), "base": atk.get("base"),
                "removed_effect": DP_DMG_REDUCTION}
