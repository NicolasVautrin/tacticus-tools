"""`ReanimationProtocols` (`TriggeredAbilityType` 0x3f0 = **1008**) -- LE passif de faction Necron,
et l'item le PLUS PORTE de la dette de kit : **9 porteurs**. #1016.

i2 (authoritatif) : << If there is **at least one other** friendly unit of the same type on the
battlefield when this unit is defeated, it has a **35 %** chance to be immediately revived with
**25 % of its initial Health** in the same hex or a random adjacent one. **Does not apply if
Overkilled.** >>

Le gameconfig ne porte AUCUNE variable, seulement DEUX constantes : `chance = 35`, `hpPct = 25`.

## L'ARTEFACT NATIF

    IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationProtocolsAbility
        : IdunBattle.Entities.Abilities.BaseTriggeredAbility        (`frida/classes.tsv`)

⚠ Le NAMESPACE ment (`Abilities.Active.Loki`) : c'est une TRIGGERED -- `TriggeredAbilityType 1008`,
et `unit_map` la classe `voie: passive`. Meme piege exact que `CamoCloakAbility`.
`frida/methods.tsv` ne lui donne que DEUX corps : `$$CreateTrigger` et `$$CreateBehaviour` (plus la
closure `<>c__DisplayClass4_0` du `Maybe`).

### `$$CreateTrigger` -- COLLAPSE dans `matches()` (idiome de tous les trigger-ports, #149)

    OnPreDeath(triggerOnOverkill: 0, triggerOnSteppable: 0)
    & get_OwnerIsTarget
    & AmountIsEqualOrGreater(
          Friends( of: Target@DSLSelectors+0x60,
                   entities: UnitsWithSameVisualId(Target@+0x60, 1 = OnlyAlive),
                   3 = OnlyAliveAndTargetable ),
          Direct(1) )

`IdunBattleLogic.Entities.DSLTriggers$$OnPreDeath(triggerOnOverkill, triggerOnSteppable)` delegue a
`$$OnDeathEvent(triggerType: 1, ...)`, dont le corps LU donne les deux gates :

  * `triggerOnOverkill == 0` -> AJOUTE `NOT(TargetIsOverkilled)`  => << Does not apply if Overkilled >>
  * `triggerOnSteppable == 0` -> AJOUTE `NOT(HasTrait(Target@DSLSelectors+0x60, 0x1b))`.
    ⚠ `0x1b = 27 = UnitTrait.Steppable` (`frida/enums.tsv`), et le PARAMETRE NATIF S'APPELLE
    `triggerOnSteppable` : ce n'est PAS un gate de bouclier. Aucun des 9 porteurs ne porte
    `Steppable` (`necroSmnSwarm` = Summon/LivingMetal/Mechanical/Swarm/Flying, etc.), donc ce gate
    est INERTE sur eux -- porte quand meme, il ne coute rien et il est LU.

`get_OwnerIsTarget` = `AreEqual(Owner@DSLSelectors+0x30, Target@DSLSelectors+0x60)` (corps LU de
`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget`, qui fixe au passage les deux slots) :
seul le PORTEUR qui meurt se ressuscite lui-meme.

### ⚠ `AmountIsEqualOrGreater` EST MAL NOMME -- c'est un `>` STRICT

`IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger` finit par
`return evaluate(minAmount@+0x20) < amount`, et **AUCUN des deux `.ctor`** (surcharge `amount` ->
`+0x18`, surcharge `selector` -> `+0x10`) ne decremente `minAmount` : les deux se contentent de
`this+0x20 = minAmount`. Le predicat est donc `count > 1`, pas `count >= 1`.

Deux lectures INDEPENDANTES concordent, et c'est ce qui le rend sur :
  * le decompile ci-dessus (`<` strict, `Direct(1)`) ;
  * l'i2, mot pour mot : << at least one **OTHER** friendly unit of the same type >>.
`count > 1` avec le mourant DANS le set <=> << au moins UNE AUTRE >>. Lire `>=` aurait fait
ressusciter un Necron ISOLE, en silence -- l'ecart le plus visible qu'on puisse produire ici.

`Friends` alloue en realite un selecteur PAR EQUIPE, pas par faction : le nom
`UnitsFromFactionSelector` que ghidra donne au `.ctor` est un faux positif de deduplication (les
deux `.ctor` ont le MEME corps de 5 ecritures de champ, donc UN seul proprietaire dans la table) --
`DSLSelectors$$Friends` alloue `DAT_18336e320`, deja tranche par `playbook/prediction/ramming_speed`
et `runner/abilities/spacewolves`. Et l'ORDRE de ses arguments est LU :
`Friends(this, of, entities, selectionType)` -> `..ctor(state, entities = of, factionId = entities,
shouldBelong: 1, selectionType)`, donc `of` est le REFERENT et `entities` la SOURCE.

`UnitsWithSameVisualId` -> `IdunBattle.Entities.Selectors.UnitsWithVisualIdSelector$$Select` :
resout l'id de la source, puis garde les entites dont
`IdunBattle.Entities.UnitExtensions$$HasVisualUnitId(unit, id)` est vrai -- une comparaison de
CHAINES sur `GetVisualUnitId`. Cote port : `UnitComponent.visual_id`.

### `$$CreateBehaviour` -- un VRAI arbre DSL (#149)

    hpPct  = GetNumberConstant(config@+0x20, 0x12 = hpPct)     = 25
    chance = GetNumberConstant(config@+0x20, 0x2a = chance)    = 35
    if (GetTutorialAbilityValue(0) > 0) { chance = 100 ; DecreaseTutorialAbilityValue(0) }
    amount = PercentageOf( StatAmount(Owner@+0x30, 5 = Health, 3 = Initial, null, sel),
                           Direct(hpPct), roundingRule: 0 )
    revive = Revive( caster: Owner@+0x30, targets: Target@+0x60, hp: amount,
                     healType: 1 = Mechanical,
                     ability: Nullable(AbilityOrEffect(this.AbilityType@+0x10)),
                     targetsTile: null, priority: 0 )
    return Maybe( behaviourFactory: <>c__DisplayClass4_0.<method> = () => revive,
                  entities: Owner@+0x30, probability: chance )

  * ⚠ **`AbilityConstantType`, PAS `AbilityVariableType`** : c'est `GetNumberConstant` qui est
    appele, deux fois, donc `0x12 = 18 = hpPct` et `0x2a = 42 = chance` -- et NON `dmgReduction` /
    `summonDmg`, qui sont ce que les MEMES ordinaux nomment dans `AbilityVariableType`. Le
    gameconfig tranche dans le meme sens (`constants: {chance: "35", hpPct: "25"}`,
    `variables: {}`), ce qui fait une seconde source.
  * **`healType = 1 = HealType.Mechanical`** (`CONCAT44(0, 1)`, low dword = 1) : le gate
    `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(1)` exige une cible **MECHANICAL**
    (ou le trait `AffectedByHealAndRepair`). Les 9 porteurs sont TOUS `Mechanical` -- ce n'est donc
    pas un gate mort, c'est un DISCRIMINANT : greffer ce passif sur un porteur non-mecanique donne
    un revive qui ne fire jamais, et c'est la contre-epreuve du montage.
  * **`targetsTile = null`** -> revive EN PLACE. Le << or a random adjacent one >> de l'i2 n'est
    PAS dans cet arbre : il vient de `IdunBattle.Operations.ReviveUnitOperation` quand la tuile est
    occupee (`operations/revive.py`), pas d'un selecteur de tuile ici.
  * **`priority = 0`** (contraste `PhoenixGem`, qui passe `-1000`).
  * **`AbilityOrEffect(this.AbilityType@+0x10)`** : le getter appele sur `this` est mislabele
    `CenterSpace.Free.MersenneTwister$$get_Count` par l'ICF, mais son corps ENTIER est
    `return *(uint*)(this + 0x10)` -- EXACTEMENT le champ que
    `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateTrigger` lit pour
    `OnOwnerSpecificAbilityInit`. C'est donc le `TriggeredAbilityType` de l'ability = **1008**.
  * **AUCUN second volet** : ni `DeactivateEffect` ni `RemoveEffect` ni `HasBeenRevivedByAbility`.
    Ce passif n'est PAS un `ReviveEffect` -- il n'a donc NI gate once-per-turn NI gate
    once-per-battle, et l'i2 ne dit pas << the first time >>. La resurrection est REPETABLE tant
    qu'il reste un congenere vivant : c'est la mecanique de faction, pas un oubli de RE.
  * **Le `Maybe` prend une CLOSURE** (`<>c__DisplayClass4_0`), donc l'arbre `Revive` n'est
    CONSTRUIT que si le tirage passe -- meme forme que `ReviveEffect$$CreateTargetTriggerBehaviour`,
    et meme consequence : un roll rate ne consomme rien.

### Le gate TUTORIEL, porte comme INERTE et dit comme tel

`GetTutorialAbilityValue(0) > 0` force `chance = 100` puis DECREMENTE le compteur. C'est le
`idun.Tutorials.Tutorial.SpecialBehaviour` **12 = ForceReanimationProtocols** (`frida/enums.tsv`).
Aucun runner monte depuis une seed BC ne porte de compteur de tutoriel -> la branche est INERTE
hors tutoriel. Elle n'est PAS portee : le port n'a aucun substrat pour ce compteur, et fabriquer
un `0` serait une mesure inventee. Nomme ici plutot que tu.

## PORTEURS -- 9, dont TROIS summons (`unit_map find --ability ReanimationProtocols`)

    npc     : necroNpc1Warrior, necroNpc1WarriorSurv, necroNpc2FlayedOne,
              necroNpc3Deathmark, necroNpc5Swarm, necroNpcLHESwarm
    SUMMON  : necroSmnSwarm (via `necroSpyder` / `ScarabHive`, qui en spawne DEUX),
              necroSmnWarrior (via `necroOverlord` / `ResurrectionOrb`),
              necroSmnDeathmark

La gate de confrontabilite passe par le SUMMON : `necroSpyder` et `necroOverlord` sont `kind =
lineup` et au pool. `ScarabHive` est le montage de choix parce qu'il spawne **deux** swarms d'un
coup -- donc deux unites de MEME `visual_id` et de MEME equipe, ce qui est exactement le predicat
`count > 1`. Tuer le premier swarm exerce la branche VRAIE ; tuer le second (le dernier congenere)
exerce la branche FAUSSE, sans rien changer d'autre au montage.

ASCII only.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import UnitComponent, OwnerComponent
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import Maybe
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import PercentageOf, StatAmount
from .....entities.selectors.accessors import Target
from .....entities.stats import StatType, StatPart
from .....entities.traits.unit_trait import UnitTrait, has_trait
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.behaviours.context import entities_from_state
from ..base import TriggeredAbility, TriggerEvent, _unit_trait_names
from ..revive_effect import Revive, can_be_revived

#: Cle gameconfig des DEUX constantes. C'est le NOM, jamais l'ordinal : `ActiveAbilityType 1008` =
#: `HarbingerOfDestruction` (deja portee dans `runner/abilities/necrons.py`), une ability REELLE ->
#: une confusion d'enum ne leverait PAS, elle lirait la mauvaise config.
ABILITY_ID = "ReanimationProtocols"
#: `AbilityConstantType 0x2a = 42 = chance` (`frida/enums.tsv`) -- `constants.chance = "35"`.
_CHANCE_CONST_KEY = "chance"
#: `AbilityConstantType 0x12 = 18 = hpPct` (`frida/enums.tsv`) -- `constants.hpPct = "25"`.
#: ⚠ Le MEME ordinal 0x12 est `dmgReduction` dans `AbilityVariableType` : c'est `GetNumberConstant`
#: (et non `GetVariableForLevel`) qui tranche, et le gameconfig le confirme (`variables: {}`).
_HP_PCT_CONST_KEY = "hpPct"
#: 5e argument de `IdunBattleLogic.Entities.DSLBehaviors$$Revive` -- `HealType.Mechanical`
#: (`frida/enums.tsv` : `0 = NonMechanical, 1 = Mechanical`). Litteral LU (`CONCAT44(0, 1)`).
REANIMATION_HEAL_TYPE = 1
#: 8e argument (`IsPreferredRevive`). Litteral 0 -- contraste `PhoenixGem`, qui passe -1000.
REANIMATION_REVIVE_PRIORITY = 0
#: 6e argument : `Nullable(AbilityOrEffect(this.AbilityType@+0x10))`. Relu par `CurrentAbilityIs`
#: sur `On(0x2d = UnitRevived)` et inscrit dans `revived_by_abilities` par `ReviveUnitOperation`.
REANIMATION_ABILITY = int(TriggeredAbilityType.ReanimationProtocols)     # 0x3f0 = 1008
#: `NOT(HasTrait(Target@+0x60, 0x1b))` ajoute par `OnDeathEvent` quand `triggerOnSteppable == 0`.
REANIMATION_EXCLUDED_TRAIT = UnitTrait.Steppable                        # 0x1b = 27
#: 4e argument du `Friends` et 3e de `UnitsWithSameVisualId` -- `UnitSelectionType`
#: (`0 = Any, 1 = OnlyAlive, 2 = OnlyTargetable, 3 = OnlyAliveAndTargetable`).
_VISUAL_ID_SELECTION = 1                                                # OnlyAlive
_FRIENDS_SELECTION = 3                                                  # OnlyAliveAndTargetable


def _identity(state: State, unit_id) -> tuple:
    """`(visual_id, team)` d'une unite -- les deux grandeurs que le sous-arbre de comptage lit.

    `visual_id` = `IdunBattle.Entities.UnitExtensions$$GetVisualUnitId`, compare par
    `System.String$$op_Equality` dans `UnitsWithVisualIdSelector$$Select` ; `team` =
    `IdunBattle.Entities.EntityExtensions$$GetCurrentTeamId`, le discriminant reel de
    `DSLSelectors$$Friends` (equipe COURANTE, pas la faction ni l'equipe d'origine).
    `(None, None)` quand l'entite n'est pas resolvable."""
    e = state.get_entity(unit_id) if unit_id is not None else None
    if e is None:
        return None, None
    uc = e.get_component(UnitComponent)
    oc = e.get_component(OwnerComponent)
    return (getattr(uc, "visual_id", None) if uc is not None else None,
            getattr(oc, "team", None) if oc is not None else None)


def same_type_allies_alive(state: State, dying_id: int) -> int:
    """Cardinal du sous-arbre `Friends(Target, UnitsWithSameVisualId(Target, OnlyAlive),
    OnlyAliveAndTargetable)` **SANS le mourant**, c'est-a-dire le nombre d'AUTRES congeneres vivants
    de son equipe. Le trigger natif compare ce set a `Direct(1)` par un `>` STRICT, le mourant
    ETANT dedans -> `count > 1` <=> `same_type_allies_alive(...) >= 1`.

    ⚠ POURQUOI LE MOURANT EST EXCLU ICI, ET POURQUOI CE N'EST PAS UNE LIBERTE. A l'instant du
    `On(PreUnitDeath)` natif, le porteur n'a pas encore recu son flag `Dead` et compte donc dans son
    propre `OnlyAlive`. Le port, lui, pose `alive = False` AVANT de dispatcher ce vecteur (c'est ce
    que declare `fire_on_death`, cf. `revive_effect.py` et `ghost_revive.py`) : compter les `alive`
    telles quelles rendrait `count` = nombre d'AUTRES, et un `> 1` y exigerait DEUX congeneres au
    lieu d'un. On retablit donc l'ecart de harnais a l'endroit ou il naît -- l'expression finale
    (`>= 1 autre`) est litteralement celle de l'i2 (<< at least one other >>).

    ⚠ CE QUI N'EST PAS PORTE, et c'est PERMISSIF : le volet `Targetable` du
    `UnitSelectionType.OnlyAliveAndTargetable` (= 3) du `Friends`. Le port n'a pas de notion
    generale de << ciblable >> ; il ne filtre donc que sur `alive`. Un congenere vivant mais rendu
    NON ciblable ferait, au natif, tomber le compte -- donc refuser la resurrection -- la ou le port
    l'accorde. Aucun effet porte a ce jour ne rend une unite vivante non ciblable, ce qui rend
    l'ecart inerte aujourd'hui ; il est nomme parce qu'il va dans le sens PERMISSIF."""
    vis, team = _identity(state, dying_id)
    if vis is None or team is None:
        return 0                                     # entree non mesuree -> gate FERME (restrictif)
    n = 0
    for other in state.entities.values():
        if int(other.id) == int(dying_id):
            continue                                 # le mourant : re-ajoute par le `> 1` du natif
        uc = other.get_component(UnitComponent)
        if uc is None or not getattr(uc, "alive", False):
            continue                                 # `UnitSelectionType.OnlyAlive`
        if getattr(uc, "visual_id", None) != vis:
            continue                                 # `HasVisualUnitId(unit, GetVisualUnitId(Target))`
        oc = other.get_component(OwnerComponent)
        if oc is None or oc.team != team:
            continue                                 # `Friends(of = Target)` -> meme equipe COURANTE
        n += 1
    return n


class ReanimationProtocolsAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationProtocolsAbility` -- cf. l'en-tete
    du module pour l'arbre natif complet.

    Rail : `ABILITY_TRIGGERS["ReanimationProtocols"]`. Ce n'est PAS un `ReviveEffect` (aucun effet
    n'est pose, aucun `EffectType ReanimationProtocols*` n'existe dans le build) : c'est une
    `BaseTriggeredAbility` autonome qui appelle le MEME
    `IdunBattleLogic.Entities.DSLBehaviors$$Revive` -> `IdunBattle.Entities.Behaviours.
    ReviveBehaviour$$Execute`, donc le meme sous-systeme revive-en-place -- exactement le
    rattachement de `PhoenixGem_ReviveAbility` et `FuelledByFury_ReviveAbility`."""

    event_id = int(EventTriggerType.PreUnitDeath)     # OnPreDeath -> OnDeathEvent(triggerType: 1)
    # `get_OwnerIsTarget` : le porteur EST le mourant, donc deja `alive = False` quand le port emet
    # `PreUnitDeath` -> il faut bypasser le gate << owner vivant >> de `evaluate_trigger_operation`.
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # --- `get_OwnerIsTarget` = AreEqual(Owner@+0x30, Target@+0x60) -------------------------
        if ev.dying_id is None or int(ev.dying_id) != int(self.owner_id):
            return False
        if state.get_entity(ev.dying_id) is None:
            return False
        # --- `OnPreDeath(triggerOnOverkill: 0)` -> NOT(TargetIsOverkilled) ----------------------
        # << Does not apply if Overkilled >> -- contraste EXACT avec `PhoenixGem` (litteral 1) et
        # `GhostEffect`, qui eux ne posent AUCUN gate d'overkill.
        if ev.overkill:
            return False
        # --- `OnPreDeath(triggerOnSteppable: 0)` -> NOT(HasTrait(Target@+0x60, Steppable)) ------
        if has_trait(_unit_trait_names(state, int(ev.dying_id)), REANIMATION_EXCLUDED_TRAIT):
            return False
        # --- `AmountIsEqualOrGreater(Friends(...SameVisualId...), Direct(1))`, un `>` STRICT ----
        if same_type_allies_alive(state, int(ev.dying_id)) < 1:
            return False
        # --- gate du behaviour : `ReviveBehaviour$$Execute` verifie `CanBeRevived(target, healType)`
        # AVANT d'ecrire la `ReviveData`. `healType = 1 = Mechanical` -> `IsAffectedByHealType`
        # exige une cible MECANIQUE : c'est le discriminant, pas une formalite.
        entities = entities_from_state(state, self.owner_id, ev.dying_id)
        tgt = entities.target
        if tgt is None:
            return False
        return can_be_revived(entities, tgt, int(ev.dying_id), state,
                              heal_type=REANIMATION_HEAL_TYPE)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # `GetNumberConstant(config, 0x2a = chance)` / `(config, 0x12 = hpPct)` -- des CONSTANTES :
        # ni indexees par niveau, ni scalees par la rarete (`is_constant=True`, aucun
        # `multiplier_pct`), ce que le gameconfig confirme (`variables: {}`).
        chance = ability_var(ABILITY_ID, _CHANCE_CONST_KEY, is_constant=True)
        hp_pct = ability_var(ABILITY_ID, _HP_PCT_CONST_KEY, is_constant=True)
        if chance is None or hp_pct is None:
            return None
        entities = entities_from_state(state, self.owner_id, ev.dying_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        # ARBRE DSL (#149) : le `Maybe` porte la closure `<>c__DisplayClass4_0`, donc le `Revive`
        # n'est evalue QUE si le tirage passe -- un roll rate ne consomme rien.
        #   amount = PercentageOf(StatAmount(Owner@+0x30, Health, Initial), Direct(hpPct), 0)
        # `Owner@+0x30` et `Target@+0x60` designent la MEME entite sous `get_OwnerIsTarget` : le
        # port ecrit `Target()` des deux cotes (meme collapse que `GhostEffectRevive`).
        amount = PercentageOf(Const(int(hp_pct)),
                              StatAmount(Target(), int(StatType.HEALTH), int(StatPart.INITIAL)))
        Maybe(int(chance),
              # `targetsTile` NUL -> revive EN PLACE (le port ne passe donc pas de `tiles_sel`).
              Revive(Target(), ABILITY_ID, _HP_PCT_CONST_KEY,
                     heal_type=REANIMATION_HEAL_TYPE, source_id=REANIMATION_ABILITY,
                     priority=REANIMATION_REVIVE_PRIORITY,
                     amount_node=amount)).execute(entities, ectx)
        revives = [p for n, p in ectx.emitted if n == "Revive" and p.get("revived")]
        return {"ability": ABILITY_ID, "owner": int(self.owner_id), "dying": ev.dying_id,
                "chance": int(chance), "hp_pct": int(hp_pct),
                "same_type_allies_alive": same_type_allies_alive(state, int(ev.dying_id)),
                "revives": revives, "rolled": state.rng is not None}
