"""`IdunBattleLogic.Entities.Abilities.Active.Loki.DoctrinaImperatives_SetStart` (triggered
`0x4b9` = **1201**) -- le helper PASSIF de l'active `0x466` = 1118 `DoctrinaImperatives`
(`admecMarshall` << Tan Gi'da >>, HERO Adeptus Mechanicus). #521-r4, case-521r1 Sec.5bis.

## Chemin de montage : `GetPassiveHelperAbility`, le SIXIEME chemin

`idun...StaticBattleRules.ActiveAbility$$GetPassiveHelperAbility` (dict `<statics>+0x78`,
scalaire `Nullable`) porte `1118 -> 1201`. Il est monte par
`IdunBattle.Entities.Factories.UnitFactory$$AddActiveAbility` avec le **`passiveAbilityState`** et la
hierarchie **0** -- pas par `GetDerivedTriggeredAbilities` (`+0x30`, dont la valeur est une List).
Cote port : `PASSIVE_HELPER_ABILITY_TRIGGERS`, cle = le NOM gameconfig de l'ACTIVE.

## `$$CreateTrigger` -- le trigger PARTAGE, et son dernier verrou est LEVE

Le corps est ABSENT de la table (dedupliqué) ; resolu par slot de vtable, `DoctrinaImperatives_SetStart`
et `BreathOfSilence_SetStart` pointent la MEME adresse, dont le proprietaire ghidra est
`IdunBattleLogic.Entities.Abilities.Active.Loki.SummaryExecutionAddBaseEffectAbility$$CreateTrigger`
(nom ARBITRAIRE). Son corps rend `<DSLTriggers+0x30>`, qu'`IdunBattleLogic.Entities.DSLTriggers$$
InitializeShared` construit :

    this+0x30 = On(0x21 = AbilityInit, ownerNeedsToBeAlive = 0) & <this+0x70> & get_OwnerIsActor

⚠ `<DSLTriggers+0x70>` etait le dernier verrou de lecture de ce port (case-521r1 Sec.5bis). Il est
IDENTIFIE : c'est `IdunBattle.Entities.Triggers.YesTrigger`, le trigger CONSTANT VRAI --
l'ELEMENT NEUTRE de la conjonction. Trois sources concordantes :
  1. `IdunBattleLogic.Entities.DSLTriggers$$Direct(bool)` -- corps entier :
     `return value ? this+0x40 : this+0x48`. `+0x40` et l'operande NEGE de `+0x48` sont deux
     instances de la MEME classe que `+0x70` (`DSLTriggers$$.ctor` les alloue toutes trois par le
     meme ctor 0-arg). Une classe qui sert de `Direct(true)` evalue VRAI inconditionnellement ;
  2. appariement FORCE sur les 13 classes de trigger de taille 16 (parent `IdunBattle.DSL.
     AbilityTrigger`) de `data/symbols/<build>/frida/classes.tsv` : seules `YesTrigger` et
     `NoTrigger` n'ont NI allocateur `DSLTriggers$$<X>` nomme NI `ShouldTrigger` dans la table
     (corps `mov al,1 ; ret` / `xor eax,eax ; ret`, dedupliqués) ; `Direct` choisit entre les
     deux, et le membre NU est le VRAI ;
  3. `IdunBattle.Entities.Effects.BaseEffect$$NeedsRefreshing` -- unique autre consommateur de la
     classe -- fait `if (cond is <cette classe> && sel is <le selecteur constant>) return <pas de
     refresh>` : << condition constante ⇒ rien ne peut changer >>, role exact d'un `YesTrigger`.

Le trigger effectif est donc `On(AbilityInit) & OwnerIsActor`, sans autre gate.

## `$$CreateBehaviour` (MIRROR du decompile, build `rnca9r7q6c`)

    AddDynamicStatModifierEffectToOwner( Behaviors@dsl+0x78,
                                         effectType = 0x4df = 1247 ProtectorImperative,
                                         statType   = 0x10  = 16 FixedArmor,
                                         turns      = null,
                                         isHidden   = <5e arg> )

`IdunBattleLogic.Entities.DSLBehaviors$$AddDynamicStatModifierEffectToOwner` alloue un
`IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour` avec **`source` ET `targets` tous
deux egaux a `Owner@DSLSelectors+0x30`** (self-buff), `amount = null` (magnitude DYNAMIQUE, lue par
l'effet lui-meme) et `turns = null` (duree par defaut). C'est UN SEUL noeud : la tranche est
minuscule parce que l'effet, lui, est deja porte (`entities/effects/loki/imperative.py::
ProtectorImperativeEffect`, `FixedArmor += extraArmor[level] x mult`).

## OBSERVABLE, et sa limite -- dite, pas masquee

Le vecteur `On(AbilityInit)` n'est emis cote port que par `abilities/behaviours/summon.py`
(`ability_init_triggers(state, gid)` au SPAWN). Les unites du ROSTER DE DEPART, elles, arrivent par
`load_state` depuis une capture live, ou l'effet 1247 est DEJA pose par le natif -- le port n'a donc
rien a y refaire, et une seconde pose serait un doublon (le gate << deja present >>
d'`AddEffectOperation` la rendrait no-op, mais on ne compte pas sur lui).

⇒ Cette inscription est FIDELE au registre natif et INERTE sur le regime courant : elle ne mordrait
que si une unite portant l'active 1118 etait SPAWNEE en cours de bataille. Aucune ne l'est
aujourd'hui. C'est un port de REGISTRE, et c'est ecrit comme tel plutot que presente comme un gain
de comportement.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddDynamicStatModifierEffect
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.tiles import Caster
from .....entities.stats import StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `PASSIVE_HELPER_ABILITY_TRIGGERS` = le NOM gameconfig de l'ACTIVE 0x466 = 1118.
DOCTRINA_IMPERATIVES_ACTIVE = "DoctrinaImperatives"
PROTECTOR_IMPERATIVE_EFFECT = int(EffectType.ProtectorImperative)          # 0x4df = 1247


def doctrina_imperatives_set_start_tree() -> AddDynamicStatModifierEffect:
    """Arbre de `DoctrinaImperatives_SetStart$$CreateBehaviour` (MIRROR, un SEUL noeud) :
    `AddDynamicStatModifierEffectToOwner(1247 ProtectorImperative, 16 FixedArmor, turns = null)`.

    `source` et `targets` valent tous deux `Owner@DSLSelectors+0x30` -- c'est la factory `...ToOwner`
    qui les fixe, et c'est ce couple (et non le nom de l'effet) qui tranche << self-buff >>.
    `duration_rounds=None` + `duration_turns=None` = le `turns` NUL du natif -> duree par DEFAUT de
    l'effet."""
    return AddDynamicStatModifierEffect(Caster(), Caster(), PROTECTOR_IMPERATIVE_EFFECT,
                                        int(StatType.FIXED_ARMOR),
                                        name=EffectType.ProtectorImperative.name)


class DoctrinaImperativesSetStartAbility(TriggeredAbility):
    """`DoctrinaImperatives_SetStart` (triggered 1201) -- cf. l'en-tete du module.
    `owner_id` = l'unite qui POSSEDE l'active 1118, instanciee par le registre
    `PASSIVE_HELPER_ABILITY_TRIGGERS` (mirror de `GetPassiveHelperAbility`)."""
    event_id = EventTriggerType.AbilityInit        # On(0x21, ownerNeedsToBeAlive = 0)
    TRIGGERED_ABILITY_ID = TriggeredAbilityType.DoctrinaImperatives_SetStart

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` -- sur ce vecteur le port pose `actor == target == l'unite qui
        # s'initialise` (cf. `dispatch/ability.py::ability_init_triggers`).
        # PAS de gate de vie : `On(0x21)` porte `ownerNeedsToBeAlive = 0` (LU), et le 2e conjoint
        # `<DSLTriggers+0x70>` est le `YesTrigger` constant -- element neutre, rien a porter.
        return ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        doctrina_imperatives_set_start_tree().execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        placed = [p for n, p in ectx.emitted
                  if n == "AddDynamicStatModifierEffect" and p.get("placed")]
        if not placed:
            return None
        return {"ability": "DoctrinaImperatives_SetStart", "owner": int(self.owner_id),
                "effect": PROTECTOR_IMPERATIVE_EFFECT, "stat": int(StatType.FIXED_ARMOR)}
