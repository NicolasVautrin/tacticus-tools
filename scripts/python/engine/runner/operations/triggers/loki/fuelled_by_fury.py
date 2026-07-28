"""Passif `FuelledByFury` d'`ultraTitus` << Titus >> (Ultramarines) -- `TriggeredAbilityType.
FuelledByFury = 0x4e3 = 1251`. Le passif porte DEUX triggered-abilities natives DISTINCTES, toutes
deux ici :

  * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ExtraDamageAbility` --
    l'ACCUMULATION du stack de l'effet `FuelledByFury_ExtraDamage` (0x52b=1323) ;
  * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ReviveAbility` (#88, residu A1) --
    le SELF-REVIVE sur kill FinalJustice, arme par l'effet-marqueur `FuelledByFury_CanRevive`
    (0x52c=1324) dont les 3 triggers propres sont portes plus bas.

i2 : << Deals +153 Damage with all attacks **for each time a friendly Character has used an active
ability this battle**. >> Le << +153 >> est la face MAGNITUDE (portee dans
`entities/effects/loki/extra_damage.py::FuelledByFuryExtraDamageEffect`) ; le << for each time >> est
CE fichier. Porter l'une sans l'autre laisse soit un effet INERTE (level fige au seed), soit un
compteur MORT -- les deux se degradent en silence.

## RE native (decompile ghidra, build gqfc5mff6c)

| Symbole |
|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ExtraDamageAbility$$CreateTrigger` |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ExtraDamageAbility$$CreateBehaviour` |
| `IdunBattleLogic.Entities.DSLFactory$$IsActiveAbilityCountedAsUsed` |
| `IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack` (= `IsNormalAttackOrHealOrRepair`) |
| `IdunBattle.Entities.Triggers.AbilityIsCountedOnceTrigger$$ShouldTrigger` |
| `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$ShouldAbilityOnlyBeCountedOncePerBattleAbility` |
| `IdunBattleLogic.Entities.DSLFactory$$IncreaseEffectLevel` (surcharge 5-args) |

### `...FuelledByFury_ExtraDamageAbility$$CreateTrigger`
```
On(0xe = UnitPostAbility)
& AreFriends(Owner@0x148, caster@0x160)
& ( HasTrait(caster@0x160, 0x10 = 16 Hero) & !HasTrait(caster@0x160, 0x419 = 1049 MachineOfWar) )
& IsActiveAbilityCountedAsUsed(alreadyCounted = false)
```
- `On(0xe)` est le DERNIER evenement d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
  (sequence `0x2b` -> execution -> `0xb` -> `0xc` -> `0xe`) ; le port l'emet deja par les DEUX voies
  (`triggers/dispatch/ability.py::unit_post_ability_triggers`, cf. #120) -- y compris pour l'attaque
  NORMALE, qui EST une active ability cote natif. C'est exactement ce que le gate
  `IsActiveAbilityCountedAsUsed` filtre.
- `HasTrait(caster, Hero) & !HasTrait(caster, MachineOfWar)` = le << friendly **Character** >> de l'i2 :
  une MACHINE DE GUERRE alliee qui caste ne compte PAS. Les deux noeuds sont mirrores separement
  (le trait `Hero` suffirait en pratique sur le roster actuel, mais le natif en pose DEUX).
- `AreFriends(Owner, caster)` compare les EQUIPES : Titus castant sa PROPRE active compte (il est
  Hero et son propre allie) -- aucun noeud `!AreEqual(Owner, caster)` dans la conjonction.

### `IdunBattleLogic.Entities.DSLFactory$$IsActiveAbilityCountedAsUsed(df, alreadyCounted)`
```
N     = df@(0xb8 + ((alreadyCounted & 0xff) ^ 1) * 8)     # 0xb8 = Const(0) | 0xc0 = Const(1)
left  = AmountIsEqualOrGreater( TimesAbilityUsed(caster@0x160, ability@0x130), N )
        & IsAbilityCountedOnlyOnce(ability@0x130)
right = IsNormalAttackOrHealOrRepair(df)                  # = IsNormalAttack(df, ability@0x130)
return !right & !left
```
(`df@0xb8`/`0xc0` = les noeuds constants 0 et 1 poses par `IdunBattleLogic.Entities.DSLFactory$$.ctor` ;
`IsAbilityCountedOnlyOnce` = `IdunBattleLogic.Entities.DSLFactory$$IsAbilityCountedOnlyOnce` ->
`AbilityIsCountedOnceTrigger$$ShouldTrigger` -> `ShouldAbilityOnlyBeCountedOncePerBattleAbility`.)

- **`!right`** = le SEUL volet qui compte en pratique, et il est deja porte, foyer unique :
  `abilities/attack_type.py::is_normal_attack` (branche 1 = `IsRegularAttack` sur l'`OrderedSet`
  statique `StaticBattleRules.ActiveAbility@+0x18` ; branche 2 = le marqueur kind `0x3f5` que la voie
  normale du port thread deja). On DELEGUE -- surtout pas un 2e port de la meme fonction native.
- **`!left`** ne peut mordre que sur les DEUX `ActiveAbilityType` du HashSet statique
  `StaticBattleRules.ActiveAbility@+0x58` (`ABILITY_COUNTED_ONCE_PER_BATTLE` ci-dessous) : hors de ces
  deux ids, `IsAbilityCountedOnlyOnce` est FAUX donc `left` est FAUX. Le facteur
  `TimesAbilityUsed(caster, ability) >= 1` n'est PAS observable offline (meme regime que
  `entities/formulas.py::TotalActiveAbilityUsed`, dont le compteur natif n'est pas capte) -- RESIDU
  NOMME. Degradation choisie : compteur inconnu -> `left` FAUX -> l'ability COMPTE. C'est le sens sur
  (il preserve le comportement de la 1re utilisation, la seule que les deux lectures possibles du
  seuil rendent identique), et il ne concerne que 2 ids sur les ~90 du registre.

### `...FuelledByFury_ExtraDamageAbility$$CreateBehaviour`
```
If( HasEffect(Owner@0x148, 0x52b, 0, 6),
    IncreaseEffectLevel(Owner@0x148, 0x52b, amount = NULL, max = NULL),
    AddEffect(0x52b, AbilityStateReference, source = Owner@0x148, cible = Owner@0x148, options = {0}) )
```
- `amount = NULL` -> `IdunBattleLogic.Entities.DSLFactory$$IncreaseEffectLevel` substitue
  `df@0xc0 = Const(1)` : increment **+1** par declenchement.
- `max = NULL` -> **AUCUN CAP** (le clamp d'`IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute`
  est desactive), contrairement a TerrifyingCrescendo (`buffMaxLevel = 6`) : le stack de Titus monte
  sans plafond sur la bataille, ce que dit l'i2 (<< for each time ... this battle >>, sans << up to >>).
- l'options-struct de l'`AddEffect` est ZEROEE : ni `TurnsFromRounds` (duree 0 = PERMANENT cote port)
  ni niveau initial -- le niveau de la 1re pose retombe sur le defaut natif **1**
  (`IdunBattle.Operations.AddEffectOperation$$Execute`, `local_588[0] = 1`), donc identique a la
  branche AddEffect d'`AddEffectOrIncreaseLevel` qui, elle, passe explicitement `level = amount = 1`.

## Frontiere DSL/imperatif (#149)
Le behaviour est un ARBRE (`If(HasEffect, IncreaseEffectLevel, AddEffect)`) -- exactement la forme que
`IdunBattleLogic.Entities.DSLFactory$$AddEffectOrIncreaseLevel` alloue, d'ou la reutilisation du
helper d'arbre `add_effect_or_increase_level` (Foreach + If/else + les 2 feuilles) plutot qu'un
helper imperatif fusionne. Les feuilles restent imperatives (`IncreaseEffectLevelOperation`,
`AddEffectOperation`). Les predicats du `CreateTrigger` sont collapses dans `matches` (doctrine des
triggers, cf. `terrifying_crescendo.py`).

===================================================================================================
VOLET REVIVE (#88 residu A1) -- `FuelledByFury_ReviveAbility` + effet-marqueur 1324
===================================================================================================

i2 (autoritatif) : << The first time each turn that Titus is defeated he cannot be **Overkilled**.
The first time each turn **he defeats an enemy with an attack triggered by Final Vengeance** he is
immediately revived with a maximum of {hp} Health. >>
(<< Final Vengeance >> = le nom joueur du trait `FinalJustice`, `TriggeredAbilityType` 0x400=1024.)

### `...FuelledByFury_ReviveAbility$$CreateTrigger`
```
On(3 = PendingDeathAdded)
& HasEffect(self@0x148, 0x52c = 1324 EffectType.FuelledByFury_CanRevive, 1, 6)
& AreEqual(caster@0x160, self@0x148)                        # = OwnerIsCaster, ecrit explicitement
& TriggeringAbilityIs(AbilityOrEffect(0x400 = 1024 TriggeredAbilityType.FinalJustice))
```
- `On(3)` : l'EMETTEUR (residu A1 du case-66 §8.1, << non localise >>) EST
  `IdunBattle.Operations.RecordKillOperation$$Execute` -- il enregistre le kill, pose le flag 0xf sur
  la victime, appelle `MatchState.AddDeath` puis publie `On(3)` avec le triplet d'entites
  `(killer, killer, dying)`. Cf. `dispatch/move_death.py::pending_death_added_triggers`.
- `AreEqual(caster@0x160, self@0x148)` : le caster de l'event `On(3)` etant le TUEUR, ce noeud dit
  << c'est le porteur du passif qui vient de tuer >>. Ce n'est donc PAS un trigger de mort de Titus.
- `TriggeringAbilityIs(1024)` : le coup fatal a ete porte DANS le behaviour de `FinalJusticeAbility`
  (`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` inscrit l'id dans l'`AbilityEntities`
  avant d'executer le behaviour -> tout ce qu'il engendre le transporte).
- `HasEffect(..., 1324, **1**, 6)` : le 4e argument vaut 1 ici (contre 0 pour PhoenixGem) -> l'effet
  doit etre **ACTIF** (`EffectComponent.IsActive @+0x5c`), et c'est cet etat qui porte le
  << first time each TURN >>.

### `...FuelledByFury_ReviveAbility$$CreateBehaviour`
```
Revive( self@0x148, self@0x148, ConfigVar(0x1d = 'hp', abilityState@0x20),
        healType = 0, Nullable(AbilityOrEffect(this.Id = 0x4e3 = 1251)), 0, priority = 0, 0 )
```
Self-revive INCONDITIONNEL (aucun `Maybe`). `healType = 0` (Heal) est le litteral lu
(`uVar6 & 0xffffffff00000000` = 0). `priority = 0` = la priorite par defaut (contraste PhoenixGem
= -1000). Comme toute feuille `Revive`, elle ne fait que POSER la `ReviveData` sur
`UnitComponent+0xa8` ; c'est `ReviveUnitOperation` qui l'applique (cf. `operations/revive.py`).

### `IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal`
`ArraySet` de TROIS `Triggered()` -- ils pilotent l'etat ACTIF du marqueur 1324, rien d'autre :
```
On(0x21 = 33 AbilityInit)                & OwnerIsActor                       -> ActivateEffect(self@0x150)
On(0x12 = 18 TurnStart_EffectActivation)                                      -> ActivateEffect(self@0x150)
On(0x2e = 46 UnitRevived) & OwnerIsTarget & CurrentAbilityIs(0x4e3 = 1251)    -> DeactivateEffect(self@0x150)
```
Le 2e est le << first time each TURN >> (re-armement a CHAQUE tick de tour) ; le 3e est la
CONSOMMATION (le revive de FuelledByFury -- et lui seul, d'ou le `CurrentAbilityIs` -- desactive le
marqueur). Meme forme que `PhoenixGem_CanReviveEffect`, a ceci pres que PhoenixGem RETIRE l'effet
(one-shot par BATAILLE) la ou FuelledByFury le DESACTIVE (one-shot par TOUR).

### Ce qui reste HORS PERIMETRE (inventorie, non porte)
`IdunBattle.Entities.Effects.Loki.FuelledByFury_BlockOverkillEffect` (`EffectType.
FuelledByFury_BlockOverkill` = 1354, present LIVE sur Titus au meme titre que 1324) = le volet
<< cannot be Overkilled >> de l'i2. Artefacts : `...$$ApplyInternal`, `...$$RevertInternal`,
`...$$CreateHandleTriggerAbilitiesInternal`. C'est une MECANIQUE DISTINCTE (pose du flag
`UnitFlag.PreventOverkill` lu par `IsOverkill`), pas un morceau du revive.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent, StatsComponent
from ....abilities.attack_type import is_normal_attack
from ....abilities.behaviours import add_effect_or_increase_level, entities_from_state
from .....entities.selectors import Caster
from .....entities.effect_type import EffectType
from .....entities.traits.unit_trait import UnitTrait
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, EffectTrigger, TriggerEvent, _unit_trait_names
from ..revive_effect import Revive, can_be_revived

FURY_EFFECT = int(EffectType.FuelledByFury_ExtraDamage)      # 0x52b = 1323
FURY_EFFECT_NAME = "FuelledByFury_ExtraDamage"               # nom d'EffectType capte live
_ON_UNIT_POST_ABILITY = int(EventTriggerType.UnitPostAbility)   # 0xe = 14
_HERO = UnitTrait(int(UnitTrait.Hero)).name                  # 0x10 = 16  -> "Hero"
_MACHINE_OF_WAR = UnitTrait(int(UnitTrait.MachineOfWar)).name   # 0x419 = 1049 -> "MachineOfWar"

ABILITY_ID = "FuelledByFury"                                 # cle gameconfig (vars 'hp' / 'extraDmg')
# `TriggeredAbilityType.FuelledByFury` = 0x4e3 = 1251 -- l'id que `...FuelledByFury_ReviveAbility$$
# CreateBehaviour` passe en `sourceId` du `Revive` (`AbilityOrEffect(this.Id)`) ET que teste le
# `CurrentAbilityIs` du trigger de desactivation du marqueur.
FUELLED_BY_FURY_ABILITY = 0x4e3                              # 1251
# `EffectType.FuelledByFury_CanRevive` = 0x52c = 1324 -- le marqueur << il reste un revive ce tour >>.
FUELLED_BY_FURY_CAN_REVIVE = int(EffectType.FuelledByFury_CanRevive)      # 1324
# `TriggeredAbilityType.FinalJustice` = 0x400 = 1024 -- l'argument du `TriggeringAbilityIs`.
FINAL_JUSTICE_ABILITY = 0x400                                # 1024
# 5e argument litteral du `Revive` (`uVar6 & 0xffffffff00000000` = 0) : healType = 0 = Heal
# -> `IsAffectedByHealType(0)` refuse les cibles Mechanical (Titus ne l'est pas).
FUELLED_BY_FURY_HEAL_TYPE = 0
# 8e argument litteral : priorite 0 (defaut) -- contraste PhoenixGem = -1000.
FUELLED_BY_FURY_PRIORITY = 0

# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$.cctor` --
# le `HashSet<ActiveAbilityType>` range dans le champ statique @+0x58, le SEUL lu par
# `...ActiveAbility$$ShouldAbilityOnlyBeCountedOncePerBattleAbility` (`Contains`). Transcription
# VERBATIM (DEUX entrees, dans l'ordre du cctor).
ABILITY_COUNTED_ONCE_PER_BATTLE = frozenset({
    0x45e,   # 1118 DoctrinaImperatives
    0x4a5,   # 1189 CalibaniteGreatsword
})


def fuelled_by_fury_tree():
    """Mirror 1:1 de `...FuelledByFury_ExtraDamageAbility$$CreateBehaviour` :
    `If(HasEffect(Owner@0x148, 0x52b), IncreaseEffectLevel(Owner, 0x52b, +1, SANS cap),
    AddEffect(0x52b, AbilityStateReference, Owner, Owner))`. `Caster()` = `Owner@0x148` (le porteur du
    trigger est aussi la cible de l'effet). `max_level=None` = le `max` NULL natif (aucun clamp)."""
    return add_effect_or_increase_level(
        FURY_EFFECT, FURY_EFFECT_NAME, Caster(),
        amount=Const(1), max_level=None)


def _team_of(state: State, unit_id) -> Optional[int]:
    e = state.get_entity(unit_id) if unit_id is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def is_active_ability_counted_as_used(state: State, caster_id, ability_type) -> bool:
    """`IdunBattleLogic.Entities.DSLFactory$$IsActiveAbilityCountedAsUsed(df, alreadyCounted=false)`
    = `!IsNormalAttackOrHealOrRepair(ability@0x130)
       & !( TimesAbilityUsed(caster@0x160, ability@0x130) >= 1 & IsAbilityCountedOnlyOnce(ability) )`.

    Le 2e facteur du `left` est fige a FAUX hors `ABILITY_COUNTED_ONCE_PER_BATTLE` (mirror du
    HashSet statique) ; DANS ce set, le compteur `TimesAbilityUsed` n'est pas observable offline ->
    residu nomme, degradation << l'ability compte >> (cf. l'en-tete de module)."""
    if ability_type is None:
        return False                       # aucune ability declenchante -> aucun noeud ne resout
    if is_normal_attack(ability_type):     # `!right` : attaque normale (ou kind 0x3f5) -> ne compte pas
        return False
    if int(ability_type) in ABILITY_COUNTED_ONCE_PER_BATTLE:
        used = _times_ability_used(state, caster_id, ability_type)
        if used is not None and int(used) >= 1:      # `!left` : deja comptee -> ne recompte pas
            return False
    return True


def _times_ability_used(state: State, caster_id, ability_type) -> Optional[int]:
    """`TimesAbilityUsed(caster@0x160, ability@0x130)` -- le noeud AMOUNT du `left`. MEME substrat que
    `entities/formulas.py::TotalActiveAbilityUsed` (`ctx.total_active_ability_used`) : NON capte par
    les RPC offline -> None. Rendu explicite ici pour que le residu soit LOCALISABLE le jour ou le
    compteur devient observable (un seul point a cabler)."""
    fn = getattr(state, "total_active_ability_used", None)
    if fn is None:
        return None
    try:
        return int(fn(caster_id, int(ability_type)))
    except Exception:
        return None


def _can_revive_instances(state: State, owner_id: int) -> list:
    """Les instances NON consommees du marqueur `FuelledByFury_CanRevive` (1324) portees par `owner_id`.
    L'effet est POSE PAR LE JEU a l'init de l'unite (`On(0x21=AbilityInit) -> ActivateEffect`) et il est
    donc CAPTE tel quel par le snapshot live -- le port n'a rien a poser. [] si pas d'`EffectsState`."""
    if state.effects is None:
        return []
    return [e for e in state.effects.by_unit.get(int(owner_id), [])
            if not e.consumed and e.effect_type == FUELLED_BY_FURY_CAN_REVIVE]


def _can_revive_is_armed(state: State, owner_id: int) -> bool:
    """`HasEffect(self@0x148, 0x52c, **1**, 6)` -- le 4e argument a 1 exige un effet **ACTIF**
    (`EffectComponent.IsActive @+0x5c`, `BaseEffect.active`), pas seulement present. Aucune instance ->
    False : le marqueur EST la condition d'armement, son absence ne peut pas armer."""
    return any(bool(e.active) for e in _can_revive_instances(state, owner_id))


def _set_can_revive_active(state: State, owner_id: int, value: bool) -> bool:
    """Ecrit `EffectComponent.IsActive @+0x5c` sur les instances 1324 du porteur -- mirror de
    `IdunBattle.Operations.RefreshEffectsOperation$$ActivateEffect` / `$$DeactivateEffect` (memes
    ecritures que le port de l'overwatch, cf. `effect_triggers.py::_set_ranged_auto_attack_active`).
    Renvoie True si un flag a CHANGE (le natif no-ope sur une ecriture identique)."""
    changed = False
    for e in _can_revive_instances(state, owner_id):
        if bool(e.active) != bool(value):
            e.active = bool(value)
            changed = True
    return changed


class FuelledByFuryReviveAbility(TriggeredAbility):
    """`...FuelledByFury_ReviveAbility` -- `On(3 = PendingDeathAdded) & HasEffect(self, 1324, actif)
    & AreEqual(caster, self) & TriggeringAbilityIs(1024 FinalJustice)` -> `Revive(self, self,
    ConfigVar('hp'), healType=0, sourceId=1251, priority=0)`. Cf. l'en-tete de module pour les arbres.

    Rail = `ABILITY_TRIGGERS['FuelledByFury']` (le passif porte les DEUX triggered-abilities), et NON
    `EFFECT_TRIGGERS[1324]` : l'`ArraySet` de `FuelledByFury_CanReviveEffect` n'enregistre QUE les trois
    triggers d'activation/desactivation du marqueur, jamais l'ability de revive elle-meme."""
    event_id = int(EventTriggerType.PendingDeathAdded)         # On(3)
    TRIGGERED_ABILITY_ID = FUELLED_BY_FURY_ABILITY             # 1251 (l'ability EST le passif)
    # `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` :
    #     if (!<slot 8 de l'interface d'ability>) { if (IsUnit(owner) && !IsAlive(owner)) return 0; }
    # et `IdunBattle.Entities.UnitExtensions$$IsAlive` rend FAUX des que `HealthComponent.IsAlive()`
    # l'est (Titus est a `hp = 0` quand sa riposte FinalJustice tue -- son `KillUnitOperation` est en
    # cours et n'a pas encore pose le flag 6). Le slot 8 vaut donc VRAI pour cette ability, faute de
    # quoi la mecanique de l'i2 serait inatteignable -- et c'est ce que MESURE le live
    # (`probe_88_fuelled_by_fury_revive`, regime KILL : Titus revient a 7477 PV). RESIDU NOMME : le
    # NOM de ce slot d'interface n'est pas resolu (meme famille que les `fire_on_death` deja poses sur
    # FinalJustice / Ambush / PhoenixGem / RitesOfMorkai).
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `AreEqual(caster@0x160, self@0x148)` : sur `On(3)`, le caster est le TUEUR (triplet
        # `(killer, killer, dying)` de `RecordKillOperation$$Execute`) -> le porteur doit etre l'auteur
        # du kill.
        if ev.killer_id is None or int(ev.killer_id) != int(self.owner_id):
            return False
        # `TriggeringAbilityIs(AbilityOrEffect(0x400 = FinalJustice))`
        if ev.triggering_ability is None or int(ev.triggering_ability) != FINAL_JUSTICE_ABILITY:
            return False
        # `HasEffect(self, 0x52c, 1, 6)` -> marqueur present ET actif (once-per-turn)
        if not _can_revive_is_armed(state, self.owner_id):
            return False
        # `DSLFactory.Revive` -> `ReviveBehaviour` : la cible doit etre revivable. Titus vient de mourir
        # (son `On(1)` a lance la riposte FinalJustice), donc `GetStat(Health,0) < 1` est vrai ; si le
        # porteur est VIVANT (kill FinalJustice d'une autre origine), `can_be_revived` rend False et le
        # revive est un no-op -- exactement comme le natif, dont le `CanBeRevived` vit dans le behaviour.
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        tgt = entities.target
        if tgt is None:
            return False
        return can_be_revived(entities, tgt, self.owner_id, state,
                              heal_type=FUELLED_BY_FURY_HEAL_TYPE)

    def _revive_level(self, state: State):
        """`ConfigVar(0x1d='hp', abilityState@0x20)` : `FuelledByFury` est un **passiveAbility** -> le
        niveau est `passive_ability_level` du porteur (jamais l'actif), scale par son
        `ability_variables_multiplier` ('hp' est dans `variablesAffectedByRarityBonus`)."""
        e = state.get_entity(self.owner_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        if sc is None:
            return None, 100
        return (getattr(sc.ctx, "passive_ability_level", None),
                getattr(sc.ctx, "ability_variables_multiplier", 100))

    def execute_behaviour(self, state: State, ev: TriggerEvent):
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        level, mult = self._revive_level(state)
        Revive(Caster(), ABILITY_ID, "hp", level, mult,
               heal_type=FUELLED_BY_FURY_HEAL_TYPE, source_id=FUELLED_BY_FURY_ABILITY,
               priority=FUELLED_BY_FURY_PRIORITY).execute(entities, ectx)
        revives = [p for n, p in ectx.emitted if n == "Revive" and p.get("revived")]
        return {"ability": ABILITY_ID, "owner": int(self.owner_id), "killed": ev.dying_id,
                "triggering_ability": ev.triggering_ability, "revives": revives}


class _FuelledByFuryCanReviveActivate(EffectTrigger):
    """Base des DEUX `Triggered()` d'ACTIVATION du marqueur 1324 (`...FuelledByFury_CanReviveEffect$$
    CreateHandleTriggerAbilitiesInternal`) : behaviour commun `ActivateEffect(self@0x150)`."""
    effect_type = FUELLED_BY_FURY_CAN_REVIVE

    def execute_behaviour(self, state: State, ev: TriggerEvent):
        changed = _set_can_revive_active(state, self.owner_id, True)
        return {"ability": ABILITY_ID, "owner": int(self.owner_id),
                "activated": FUELLED_BY_FURY_CAN_REVIVE, "changed": changed,
                "on_event": int(ev.event_id)}


class FuelledByFuryCanReviveActivateOnAbilityInit(_FuelledByFuryCanReviveActivate):
    """1re entree de l'`ArraySet` : `On(0x21 = 33 AbilityInit) & OwnerIsActor -> ActivateEffect`.
    C'est l'armement INITIAL. Le port n'emet ce vecteur qu'a l'init d'ability ; sur un etat charge
    depuis une capture live, le marqueur arrive DEJA actif (`BaseEffect.active` = True par defaut),
    ce qui est l'etat que le natif a lui-meme atteint par ce trigger."""
    event_id = int(EventTriggerType.AbilityInit)               # 0x21 = 33

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id)   # OwnerIsActor


class FuelledByFuryCanReviveActivateOnTurnStart(_FuelledByFuryCanReviveActivate):
    """2e entree de l'`ArraySet` : `On(0x12 = 18 TurnStart_EffectActivation) -> ActivateEffect`.
    AUCUN predicat d'owner ni de joueur au decompile (contraste l'overwatch, qui porte `NOT
    IsTurnOf(owner)`) -> le marqueur est re-arme a CHAQUE tick de tour. C'est le << the first time each
    TURN >> de l'i2."""
    event_id = int(EventTriggerType.TurnStart_EffectActivation)   # 0x12 = 18

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return True


class FuelledByFuryCanReviveDeactivateOnRevive(EffectTrigger):
    """3e entree de l'`ArraySet` : `On(0x2e = 46 UnitRevived) & OwnerIsTarget &
    CurrentAbilityIs(AbilityOrEffect(0x4e3 = 1251)) -> DeactivateEffect(self@0x150)`.

    Le `CurrentAbilityIs` est essentiel : SEUL un revive venu de FuelledByFury consomme le marqueur ;
    un revive d'ailleurs (Narthecium d'un allie, PhoenixGem, ...) emet bien `On(0x2e)` mais laisse
    l'armement en place. Meme discriminant que `PhoenixGemRemoveMarkerOnRevive`."""
    effect_type = FUELLED_BY_FURY_CAN_REVIVE
    event_id = int(EventTriggerType.UnitRevived)               # 0x2e = 46

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.target_id is None or int(ev.target_id) != int(self.owner_id):   # OwnerIsTarget
            return False
        return ev.ability_type is not None and int(ev.ability_type) == FUELLED_BY_FURY_ABILITY

    def execute_behaviour(self, state: State, ev: TriggerEvent):
        changed = _set_can_revive_active(state, self.owner_id, False)
        return {"ability": ABILITY_ID, "owner": int(self.owner_id),
                "deactivated": FUELLED_BY_FURY_CAN_REVIVE, "changed": changed,
                "on_event": int(ev.event_id)}


class FuelledByFuryExtraDamageAbility(TriggeredAbility):
    """`...FuelledByFury_ExtraDamageAbility` -- `On(UnitPostAbility=0xe) & AreFriends(Owner, caster)
    & HasTrait(caster, Hero) & !HasTrait(caster, MachineOfWar) & IsActiveAbilityCountedAsUsed(false)`
    -> `If(HasEffect(Owner, 1323), IncreaseEffectLevel(+1), AddEffect(1323))`."""
    event_id = _ON_UNIT_POST_ABILITY
    TRIGGERED_ABILITY_ID = FUELLED_BY_FURY_ABILITY   # 1251 (meme passif que le volet revive)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        caster = ev.actor_id                         # `caster@0x160` = l'acteur de l'ability close
        if caster is None:
            return False
        my_team = _team_of(state, self.owner_id)     # `AreFriends(Owner@0x148, caster@0x160)`
        if my_team is None or _team_of(state, caster) != my_team:
            return False
        traits = _unit_trait_names(state, caster)
        if _HERO not in traits:                      # `HasTrait(caster, 0x10 = Hero)`
            return False
        if _MACHINE_OF_WAR in traits:                # `!HasTrait(caster, 0x419 = MachineOfWar)`
            return False
        return is_active_ability_counted_as_used(state, caster, ev.ability_type)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        fuelled_by_fury_tree().execute(entities_from_state(state, self.owner_id, None), ectx)
        lvl = None
        for n, p in ectx.emitted:
            if n in ("IncreaseEffectLevel", "AddEffect"):
                lvl = p.get("level")
        return {"ability": "FuelledByFury", "unit": int(self.owner_id),
                "caster": int(ev.actor_id), "ability_type": ev.ability_type,
                "level": lvl, "on_event": int(ev.event_id)}
