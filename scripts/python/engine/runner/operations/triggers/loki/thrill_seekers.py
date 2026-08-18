"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ThrillSeekersAbility` (TriggeredAbilityType
`ThrillSeekers` = 1444) — ability accordee par le TRAIT `UnitTrait.ThrillSeekers` = 1056 (0x420),
porte par les CINQ kits Emperor's Children (`emperExultant`, `emperFlawlessBlade`,
`emperKakophonist`, `emperLucius`, `emperNoiseMarine` — tous `lineup`/HERO, aucun npc ni summon).

⚠ TROIS IDS DISTINCTS DANS TROIS ENUMS DISTINCTS, ne pas les confondre :
`UnitTrait.ThrillSeekers = 1056` (le trait) ; `TriggeredAbilityType.ThrillSeekers = 1444`
(l'ability accordee) ; `EffectType.ThrillSeekers = 1434` (0x59a — l'effet « Thrilled » pose).

RE (decompile ghidra, build gqfc5mff6c) — MIRROR 1:1 :

  `...ThrillSeekersAbility$$CreateTrigger` (arbre T) :
      ( On(PreAttackHit=6, subject=1)
        & IsFirstHitInSeries
        & get_OwnerIsCaster
        & op_LogicalNot( IsWounded(target@0x178) ) )
      op_BitwiseOr
      ( On(DamageTaken=0xf, subject=0) & get_OwnerIsTarget )

  `...ThrillSeekersAbility$$CreateBehaviour` (arbre E) :
      turns  = TurnsFromRounds( Get( AbilityConfiguration.GetNumberConstant(cfg, 0x45) ) )
      amount = Get( AbilityConfiguration.GetNumberConstant(cfg, 0x30) )
      If( op_LogicalNot( HasFlag(Owner@0x148, 6) ),
          If( HasEffect(Owner@0x148, 0x59a, activeOnly=0, sourceFlags=6),
              ChangeEffectTurns(Owner@0x148, 0x59a, turns, ChangeType.Set=1),
              AddStaticStatModifierEffect(Owner@0x148, 0x59a, stat=9, amount, turns, 0) ),
          null )

  Qualification des constantes (dump d'enums du build) :
  - `IdunBattle.Configuration.AbilityConstantType` : **0x45 = 69 = `nrOfRounds`**,
    **0x30 = 48 = `extraCritChance`**.
  - `IdunBattle.Entities.Enum.StatPart` : `Missing` = 4 (lu par `IsWounded`).
  - `IdunBattle.Entities.Enum.UnitFlag` : **6 = `Dead`** (le gate `Not(HasFlag(Owner,6))` = « le
    porteur n'est pas mort », PAS une immunite — cf. la rectification dans `operations/effects.py`).
  - `IdunBattle.Entities.Enum.ChangeType` : 0 = Add, **1 = Set**.
  - `engine/entities/stats.py` : StatType **9 = CRIT_CHANCE**.

  Sous-fonctions natives lues (pas devinees) :
  - `IdunBattle.Entities.Triggers.IsFirstHitInSeriesTrigger$$ShouldTrigger` =
    `AbilityEntities.get_IsFirstHit` = `Nullable<bool>(hitIndex.HasValue && hitIndex == 0)`
    (`get_IsFirstHit` lit le Nullable<int> `AbilityEntities@+0x110`) ; Nullable vide -> FALSE.
  - `IdunBattle.Entities.Triggers.IsWoundedTrigger$$ShouldTrigger` =
    `selector.Select(entities).All(u => UnitExtensions.GetStat(u, Health=5, StatPart.Missing=4) != 0)`
    (boucle `MoveNext` : sortie FALSE des qu'une unite a `Missing == 0`, TRUE si la collection est
    epuisee) => `Not(IsWounded(target))` = « la cible n'a AUCUN PV manquant » = **PLEINE VIE**.
  - `IdunBattle.Entities.Triggers.HasEffectTrigger$$ShouldTrigger` ->
    `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects(unit, query, [type], activeOnly, flags)` ;
    ThrillSeekers passe **activeOnly = 0** (byte) et flags = 6 (owned|incoming).
  - `IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect` ->
    `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$.ctor` : `param_9 -> +0x78` =
    le noeud de DUREE (evalue en `Nullable<int>` par `...$$Execute` et passe a l'`EffectBuilder`).

  gameconfig (trait `ThrillSeekers`) : `thrillSeekersNrOfRounds = 1`,
  `thrillSeekersExtraCritChance = 15` — MEMES donnees que les number-constants de l'ability, exposees
  cote client sur le TRAIT (helper `trait_var`). i2 : « Each turn, when this unit takes Damage or
  targets an enemy with full Health, it becomes *Thrilled* for {nrOfRounds} round. While *Thrilled*,
  its Crit Chance is increased by +{extraCritChance}% and if it defeats an enemy with a Crit, that
  enemy is always overkilled. »

DISPATCH (2 classes = 2 branches de l'`op_BitwiseOr`, patron `TerrifyingCrescendo`/`ActOfFaith`) :
  - `ThrillSeekersFullHealthTargetAbility` : `On(PreAttackHit=6)`, vecteur `pre_attack_hit_triggers`.
    ⚠ **CETTE LIGNE A AFFIRME L'INVERSE DE CE QUE FAIT LE NATIF** — elle disait « `ExecuteHit` emet
    `On(6)` en TETE, avant le calcul du crit de CE coup -> le buff s'applique bien a l'attaque
    declenchante ». RELU dans `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (#522-r1),
    l'ordre est : slot 0xad (profil) -> `AttackHit..ctor` -> **slot 0xa `RollCritical`** ->
    `AbilityEntities..ctor` -> `EnqueueOperation(6)` -> `EnqueueOperation(7)` -> sub-op 0x42 ->
    `EvaluateAfterHitTriggers`. `On(6)` est donc en **QUEUE**, apres le crit.
    Conjugue au fait que `IdunBattle.Core.Services.DamagePrediction$$RollCritical` relit
    `GetStat(attacker, 0x9)` **a chaque appel** et qu'`ExecuteHits` boucle sur `ExecuteHit`, la loi
    est : **le +15 ne mord jamais sur le coup qui l'a declenche, et mord sur tous les suivants**,
    ceux de la MEME salve compris. Porte par `crit_chance_after` (`damage_hits.py::_run_hits`), que
    les trois vecteurs alimentent en relisant `_crit_params` APRES l'emission.
    D'ou venait le faux : l'affirmation decrivait la place du vecteur **cote PORT** (ou l'event
    etait effectivement emis avant `_crit_params`) et la presentait comme « la place NATIVE » --
    une justification de l'existant, jamais confrontee au decompile ;
  - `ThrillSeekersDamageTakenAbility` : `On(DamageTaken=15)`, vecteur `damage_taken_triggers` (emis
    par `_apply_damage_pipeline` juste apres la mutation de PV, gate `degat SANTE applique > 0` =
    mirror `if (0 < local_7dc)` d'`IdunBattle.Operations.ApplyDamageOperation$$Execute`, ou
    `local_7dc = FillUpStatComponent.Reduce(...)` = la reduction REELLEMENT appliquee).

DOCTRINE #149 : le `CreateTrigger` est COLLAPSE imperativement dans `matches()` (choix de repo
documente `docs/rl/dsl-effect-nodes.md` §« Axes SEPARES » — les triggers portes font tous ainsi) ;
le `CreateBehaviour` est un VRAI ARBRE DSL (`thrill_seekers_tree()`), aucune logique recablee a la
main : les feuilles `ChangeEffectTurns` / `AddStaticStatModifierEffect` appellent leurs Operations.

RESIDUS (honnetes) :
- `Not(HasFlag(Owner, Dead))` n'est PAS un noeud de l'arbre porte : le nœud `HasFlag` du port est
  1-arg (`flag in ctx.flags`) et `ctx.flags` n'est jamais peuple. On le porte par le noeud
  SEMANTIQUEMENT EQUIVALENT `IsAlive(Caster())` (`UnitFlag.Dead` <=> `!IsAlive`), lui-meme REDONDANT
  avec le gate « owner vivant » de `evaluate_trigger_operation` (`CanGetAbilityTrigger`) — garde
  double, aucun effet observable divergent.
- Le gate implicite ANDe a tout `On(e, subject)` natif (`IdunBattleLogic.Entities.DSLTriggers$$On` : `OnEvent(e) &
  factory@0x98` si subject!=0, `& factory@0x128` sinon) n'est identifie pour AUCUN `On()` du port
  (vocabulaire entier) : residu UNIFORME, pas propre a ce trait.
- GRANULARITE (meme classe d'approximation que `unit_blocked_triggers`) : le natif emet `On(6)` PAR
  COUP et `On(0xf)` PAR COUP ; le port les emet UNE fois par attaque. Strictement equivalent pour
  ThrillSeekers (branche 1 gatee `IsFirstHitInSeries` -> seul le coup 0 compte ; branche 2 =
  re-pose/refresh idempotent). A raffiner si un consommateur per-coup non gate apparait.
- RIDER OVERKILL (« defeats an enemy with a Crit -> always overkilled ») : c'est une face
  PREDICTION separee — `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` force son
  **`isForceOverkill`** a 1 quand l'attaquant `HasTrait(0x420)` ET `HasEffect(0x59a)` ET le coup est
  CRITIQUE ; non porte ici (cf. `docs/rl/case-30-raw-bounds.md` et le case-doc).
  ⚠ #R33 : le rider est CONDITIONNE au crit, et `isCritical` est deja le 3e argument d'
  `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` (desormais threade jusqu'au chokepoint de
  mort) -- pour un porteur ThrillSeekers les deux chemins donnent le MEME verdict. C'est pour cela
  que la mesure #R33 attribue via un tueur SANS le trait (`ultraInceptorSgt`, montage revive)."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import HealthComponent, UnitComponent
from ....abilities.behaviours.context import entities_from_state
from .....entities.behaviours import If as IfBehaviour
from .....entities.selectors.tiles import Caster
from .....entities.triggers import IsAlive, HasEffect
from .....entities.effect_type import EffectType
from .....entities.stats import StatType
from .....entities.effects.magnitude import trait_var
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ....abilities.behaviours.effects import (AddStaticStatModifierEffect, ChangeEffectTurns)
from ..base import TriggeredAbility, TriggerEvent

THRILLED = int(EffectType.ThrillSeekers)              # 1434 (0x59a) — l'effet « Thrilled »
_ON_PRE_ATTACK_HIT = int(EventTriggerType.PreAttackHit)   # 6
_ON_DAMAGE_TAKEN = int(EventTriggerType.DamageTaken)      # 15 (0xf)
_CHANGE_SET = 1                                       # `IdunBattle.Entities.Enum.ChangeType.Set`


def thrill_seekers_rounds() -> int:
    """`AbilityConfiguration.GetNumberConstant(cfg, 0x45=nrOfRounds)` = gameconfig
    `traits.ThrillSeekers.variables.thrillSeekersNrOfRounds` (=1). Defaut 1 si la cle manque."""
    v = trait_var("ThrillSeekers", "thrillSeekersNrOfRounds")
    return 1 if v is None else int(v)


def thrill_seekers_extra_crit_chance() -> int:
    """`AbilityConfiguration.GetNumberConstant(cfg, 0x30=extraCritChance)` = gameconfig
    `traits.ThrillSeekers.variables.thrillSeekersExtraCritChance` (=15). Defaut 0 si la cle manque
    (no-op fidele plutot qu'une magnitude inventee)."""
    v = trait_var("ThrillSeekers", "thrillSeekersExtraCritChance")
    return 0 if v is None else int(v)


def thrill_seekers_tree():
    """Arbre E de `...ThrillSeekersAbility$$CreateBehaviour` — MIRROR 1:1 du decompile :

        If( Not(HasFlag(Owner, Dead=6)),                     -> Not(IsAlive(Caster())) inverse, cf. header
            If( HasEffect(Owner, 0x59a, activeOnly=0),
                ChangeEffectTurns(Owner, 0x59a, TurnsFromRounds(nrOfRounds), Set),
                AddStaticStatModifierEffect(Owner, 0x59a, CRIT_CHANCE, extraCritChance,
                                            TurnsFromRounds(nrOfRounds)) ) )

    `Owner@0x148` == `Caster()` (triggered : Owner == Caster, convention du port). `turns` est passe
    en ROUNDS aux DEUX feuilles (`duration_rounds` / `turns_rounds`) : c'est le noeud
    `TurnsFromRounds(n)` natif, converti a l'execution par `ConvertRoundsToTurns` (le facteur = le
    nombre de joueurs non-Environment)."""
    rounds = thrill_seekers_rounds()
    amount = thrill_seekers_extra_crit_chance()
    refresh = ChangeEffectTurns(Caster(), THRILLED, change_type=_CHANGE_SET,
                                turns_rounds=Const(rounds))
    place = AddStaticStatModifierEffect(Caster(), THRILLED, int(StatType.CRIT_CHANCE),
                                        Const(amount), name=EffectType.ThrillSeekers.name,
                                        duration_rounds=rounds)
    inner = IfBehaviour(HasEffect(Caster(), THRILLED, 0, False), refresh, place)
    return IfBehaviour(IsAlive(Caster()), inner)          # == Not(HasFlag(Owner, Dead))


class _ThrillSeekersBase(TriggeredAbility):
    """Corps PARTAGE des deux branches de l'`op_BitwiseOr` du `CreateTrigger` : le natif n'a qu'UN
    `CreateBehaviour`, les deux branches l'executent a l'identique (patron `TerrifyingCrescendo`).

    ⚠ **`fire_on_death = True` (#10015)**, mirror de `ITriggeredAbility` slot 8 =
    `get_AllowForDeadOwner`, LU sur `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    ThrillSeekersAbility` (`OVERRIDE`, corps `b0 01 c3` = `return true` ; entree versionnee
    `data/symbols/<build>/metadata/allow_for_dead_owner.tsv`). La propriete appartient a la classe
    NATIVE, qui est UNIQUE : elle se pose donc sur la BASE, pas sur chacune des deux branches
    portees. Ce couple etait invisible du cliquet `probe_10015` parce que ces deux classes portees
    pour une seule native sont, par construction, hors de son appariement par le NOM.

    ⚠ **ET IL NE VIENT JAMAIS SEUL** : `get_AllowForDeadOwner` ouvre le gate d'AMONT
    (`triggers/dispatch/core.py`, qui saute tout porteur non vivant), alors que le gate d'AVAL est
    porte PAR BRANCHE, par le 3e argument d'`IdunBattleLogic.Entities.DSLTriggers$$On(this,
    triggerType, ownerNeedsToBeAlive)` -- LU : `On` construit `EventAbilityTrigger(type) &
    (ownerNeedsToBeAlive ? <DSLTriggers+0x20> : <DSLTriggers+0x70 = YesTrigger>)`. Les deux branches
    n'ont PAS la meme valeur (`On(6, **1**)` contre `On(0xf, **0**)`), donc poser `fire_on_death`
    sans reporter le gate de la branche 1 la rendrait PLUS permissive que le natif -- exactement la
    degradation silencieuse que `LightImUp` a payee dans l'autre sens (« deux gates distincts »)."""

    #: `ITriggeredAbility` slot 8 = `get_AllowForDeadOwner` -- LU (cf. la docstring ci-dessus).
    fire_on_death = True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None                                  # pas d'EffectsState -> pose impossible
        ectx = ExecutionContext(state=state, rng=state.rng)
        thrill_seekers_tree().execute(entities_from_state(state, self.owner_id, ev.target_id), ectx)
        placed = [p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
        refreshed = [p for n, p in ectx.emitted if n == "ChangeEffectTurns"]
        return {"trait": "ThrillSeekers", "unit": self.owner_id, "on_event": ev.event_id,
                "placed": bool(placed), "refreshed": bool(refreshed),
                "crit_chance_bonus": (placed[0]["amount"] if placed else None)}


def _owner_unit_component(state: State, unit_id: Optional[int]):
    """Le `UnitComponent` du PORTEUR -- le canal ou vit `alive`, que le gate `ownerNeedsToBeAlive`
    de la branche 1 interroge. `None` = pas d'entite/pas de composant : on ne refuse RIEN sur une
    absence de mesure (le gate ne mord que sur un `alive` LU a `False`)."""
    ent = state.get_entity(unit_id) if unit_id is not None else None
    return ent.get_component(UnitComponent) if ent is not None else None


def _is_wounded(state: State, unit_id: Optional[int]) -> bool:
    """`IdunBattle.Entities.Triggers.IsWoundedTrigger$$ShouldTrigger` sur un selecteur MONO-cible
    (`target@0x178`) : `GetStat(unit, Health=5, StatPart.Missing=4) != 0` = l'unite a-t-elle des PV
    MANQUANTS ? Le natif retourne TRUE quand la collection est EPUISEE (`All` sur vide) -> cible
    absente/sans PV = « wounded » = la branche 1 ne fire pas (c'est le sens du `Not` en aval)."""
    ent = state.get_entity(unit_id) if unit_id is not None else None
    hc = ent.get_component(HealthComponent) if ent is not None else None
    if hc is None or hc.hp is None or hc.hp_max is None:
        return True                                      # collection vide/sans stat -> All == True
    return int(hc.hp_max) - int(hc.hp) != 0              # StatPart.Missing != 0


class ThrillSeekersFullHealthTargetAbility(_ThrillSeekersBase):
    """Branche 1 de `...ThrillSeekersAbility$$CreateTrigger` :
    `On(PreAttackHit=6, ownerNeedsToBeAlive=1) & IsFirstHitInSeries & get_OwnerIsCaster
     & Not(IsWounded(target))`
    = « le porteur commence une attaque (1er coup) sur un ennemi a PLEINE VIE » -> devient *Thrilled*."""
    event_id = _ON_PRE_ATTACK_HIT

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `ownerNeedsToBeAlive = 1` -- le 3e argument d'`IdunBattleLogic.Entities.DSLTriggers$$On`,
        # LU : il conjugue `<DSLTriggers+0x20>` (le trigger « le porteur est vivant ») a l'event.
        # ⚠ CETTE BRANCHE-CI SEULEMENT : la branche 2 passe `0`, donc `<DSLTriggers+0x70 =
        # YesTrigger>` et AUCUN gate. Tant que `fire_on_death` etait FAUX, le gate d'amont du
        # dispatch masquait la difference en refusant les DEUX ; depuis #10015 il ne refuse plus
        # RIEN, et ce test est ce qui garde la branche 1 fidele.
        ouc = _owner_unit_component(state, self.owner_id)
        if ouc is not None and not ouc.alive:
            return False
        if ev.actor_id != self.owner_id:                 # get_OwnerIsCaster (le porteur EST l'attaquant)
            return False
        if not ev.is_first_hit:                          # IsFirstHitInSeries (Nullable vide -> False)
            return False
        return not _is_wounded(state, ev.target_id)      # op_LogicalNot(IsWounded(target@0x178))


class ThrillSeekersDamageTakenAbility(_ThrillSeekersBase):
    """Branche 2 de `...ThrillSeekersAbility$$CreateTrigger` :
    `On(DamageTaken=0xf) & get_OwnerIsTarget` = « le porteur SUBIT du degat » -> devient *Thrilled*."""
    event_id = _ON_DAMAGE_TAKEN

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return ev.target_id == self.owner_id             # get_OwnerIsTarget (le porteur EST la victime)
