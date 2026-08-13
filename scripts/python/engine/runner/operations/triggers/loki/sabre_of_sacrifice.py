"""`SabreOfSacrifice` (0x5c6 = 1478) -- la relique d'`astraDreir` (Astra Militarum).

i2 : « When Dreir or Death Riders adjacent to Dreir are charging, their attacks Suppress their
targets for 1 round. After charging and until the start of their next turn, they additionally have
+1018 Armour for each friendly unit that has been defeated this battle. »

VOIE D'ATTRIBUTION : item RELIQUE (`UnitConfiguration.TertiaryAbility`), donc `RELIC_ABILITY_TRIGGERS`
et l'`AbilityState` TERTIAIRE. UN seul porteur, `astraDreir`, DANS le pool rank 17 -> `--equip-relic`
suffit (etat 2 de la gate relique). Ce n'est PAS une active : ni `ABILITY_CLASSES`, ni
`TARGETING_OPTIONS`, ni `ABILITY_ATTACK_TYPE`.

DECOMPILE, une seule classe native.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$CreateTrigger` :

    On(0x9 = Attack, ownerNeedsToBeAlive: 1)
      op_BitwiseAnd IsCharging(Caster@DSLSelectors+0x48, Target@DSLSelectors+0x60)
      op_BitwiseAnd ( get_OwnerIsCaster
                      op_BitwiseOr ( AreEqual(Parent(Caster@+0x48, root: 0), Owner@+0x30)
                                     op_BitwiseAnd IsUnitWithVisualId(Caster@+0x48,
                                                       Config.GetStringConstant(0x0 = unitId))
                                     op_BitwiseAnd IsAdjacent(Owner@+0x30, Caster@+0x48,
                                                       selectionType: 3 = OnlyAliveAndTargetable) ) )

⚠ UN SEUL vecteur `On()` -> UNE classe. La disjonction est INTERNE a la conjonction (elle porte sur
le PORTEUR du coup, pas sur l'evenement), donc elle ne se ventile PAS en deux classes -- contrairement
au patron `FuryFromTheDelve`/`ThrillSeekers`, ou l'`op_BitwiseOr` joint deux `On()`.

⚠ OWNER != CASTER, et c'est le premier call-site porte du depot ou ils divergent reellement. La
branche droite de la disjonction dit « le coup vient d'un SUMMON de l'owner, qui a le visuel du Death
Rider, et qui est adjacent a l'owner ». Le CASTER est alors le Death Rider ; l'OWNER reste Dreir. Le
port thread donc le slot `Owner` explicitement (`entities_from_state(..., owner_id=...)`, ajoute par
cette tranche) -- sans quoi le repli `ctx.owner or ctx.caster` d'`entities/selectors/accessors.Owner`
designerait le Death Rider, et `AreFriends(Owner, ...)` du compte d'armure changerait de referent,
SILENCIEUSEMENT.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$CreateBehaviour` :

      AddEffect( 0x429 = 1065 EffectType.Pinned, AbilityStateReference,
                 source = Owner@+0x30, targets = Target@+0x60,
                 options = default(Nullable<AddEffectBehaviourOptions>) )
    op_BitwiseAnd
      AddStaticStatModifierEffect( targets    = Caster@+0x48,
                                   effectType = 0x5c1 = 1473 SabreOfSacrifice_ExtraArmor,
                                   statType   = 0x10 = 16 StatType.FixedArmor,
                                   amount     = GetCurrentExtraArmor(abilityState),
                                   turns      = TurnsFromRounds(<DSLFormulas+0x20> = Direct(1)),
                                   isHidden   = 0 )

⚠ `options` est un `Nullable<AddEffectBehaviourOptions>` a ZERO (32 octets nuls au site d'appel) :
`AddEffectBehaviour$$.ctor` fait `options.GetValueOrDefault()`, donc le champ `+0x78` (turnsNode) est
NUL -> DUREE PAR DEFAUT DE L'EFFET, pas `1`. Cote port c'est `duration_rounds=None` (exactement le
regime « Pinned de CrushingClaws » que documente `AddEffect`). Le « for 1 round » de l'i2 est la
duree par defaut de `Pinned`, pas un litteral de cet arbre -- ne pas le coder en dur ici.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$GetCurrentExtraArmor` :

    Multiply( Count( Filter( AllUnits(),
                               AreFriends(Owner@+0x30, It@+0x68, comparisonType: 0, anyEntity: 0)
                               op_BitwiseAnd HasBeenDefeated(It@+0x68)
                               op_BitwiseAnd IsNormalUnit(It@+0x68) ) ),
              Get( Config.GetVariableForLevel(0x1b = 27 extraArmor, abilityState, null) ) )

C'est le MEME filtre que `...LeadingTheChargeAbility$$GetExtraPierceRatio` (l'active du meme heros) --
d'ou le deplacement de `HasBeenDefeated` / `IsNormalUnit` vers `entities/triggers.py` (#1002). Deux
differences LUES, transcrites telles quelles : l'ORDRE des trois conjonctions
(`AreFriends & HasBeenDefeated & IsNormalUnit` ici, `IsNormalUnit & AreFriends & HasBeenDefeated`
la-bas) et l'ORDRE des operandes du `Multiply` (`count` a GAUCHE ici).

⚠ `AllUnits()` = la primitive POOL-8 (`EntityPool.AllUnits`, MORTS INCLUS), pas `AllAliveUnits`.
Sous un `HasBeenDefeated`, une source qui filtre les mortes rendrait un compte structurellement NUL,
sans erreur. Site DECLARE dans `probe_514_allunits_rayon_de_souffle.py`.

FORME DU PORT (doctrine #149) : le `CreateTrigger` COLLAPSE imperativement dans `matches` (+
`event_id`) ; le `CreateBehaviour` est un ARBRE DSL dont les feuilles appellent les Operations deja
portees.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.ability_variable_type import AbilityVariableType
from .....entities.behaviours import op_and
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import Count, Get, Multiply
from .....entities.selectors.accessors import Owner, Subject, Target
from .....entities.selectors.tiles import AllUnits, Caster, Parent
from .....entities.selectors.units import Filter
from .....entities.stats import StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import (AreEqual, AreFriends, HasBeenDefeated, IsAdjacent, IsCharging,
                                    IsNormalUnit, IsUnitWithVisualId, TriggerAnd)
from .....entities.unit_selection_type import UnitSelectionType
from .....entities.unit_team_selection_type import UnitTeamSelectionType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, AddStaticStatModifierEffect
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

ABILITY_ID = "SabreOfSacrifice"
SABRE_OF_SACRIFICE = int(TriggeredAbilityType.SabreOfSacrifice)         # 0x5c6 = 1478
EXTRA_ARMOR_EFFECT = int(EffectType.SabreOfSacrifice_ExtraArmor)        # 0x5c1 = 1473
PINNED_EFFECT = int(EffectType.Pinned)                                  # 0x429 = 1065

# ⚠ LES DEUX CLES NE VIENNENT PAS DU MEME ENUM, et le natif les lit par deux accesseurs distincts :
# `GetVariableForLevel(0x1b)` (variable, indexee par NIVEAU) vs `GetStringConstant(0x0)` (constante).
# Les ordinaux se recouvrent entre les deux enums : seul le NOM rend la confusion visible -- elle
# l'a ete ici, `AbilityConstantType.extraArmor` n'existant pas.
EXTRA_ARMOR_KEY = AbilityVariableType.extraArmor.name    # `AbilityVariableType` 0x1b = 27
UNIT_ID_KEY = AbilityConstantType.unitId.name            # `AbilityConstantType` 0x0

#: 3e argument d'`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent`. Type DECLARE lu dans
#: `frida/methods.tsv` -- jamais deduit de l'ordinal.
_ADJACENT_SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)      # 3
#: `comparisonType` d'`IdunBattleLogic.Entities.DSLTriggers$$AreFriends` (le litteral `0` du site).
_FRIENDS_COMPARISON = int(UnitTeamSelectionType.ByCurrentTeam)           # 0


def sabre_of_sacrifice_defeated_friends_selector():
    """`Filter( AllUnits(), AreFriends(Owner@+0x30, It) & HasBeenDefeated(It) & IsNormalUnit(It) )`
    -- l'operande du `Count` de `GetCurrentExtraArmor`, ARBRE DSL 1:1, ordre des conjonctions LU.

    `Subject()` = `It@DSLSelectors+0x68` (l'element lie par le `Filter` ; `Filter.select` lie aussi
    `active_target` au meme item). `AreFriends(Owner(), ...)` est ce qui exige le slot OWNER threade :
    quand le coup vient d'un Death Rider, l'owner reste Dreir."""
    predicat = TriggerAnd(TriggerAnd(AreFriends(Owner(), Subject(),
                                                selection_type=_FRIENDS_COMPARISON),
                                     HasBeenDefeated(Subject())),
                          IsNormalUnit(Subject()))
    return Filter(AllUnits(), predicat)


def sabre_of_sacrifice_extra_armor_formula(extra_armor_per_unit: int):
    """`Multiply( Count(<le filtre>), Get(GetVariableForLevel(0x1b = extraArmor)) )` -- MIRROR, y
    compris l'ORDRE des operandes (`count` a GAUCHE, contrairement a `GetExtraPierceRatio`).

    `extra_armor_per_unit` est resolu par l'appelant (meme choix que `DawnBlade`/`DaemonfleshPlate` :
    la lecture du gameconfig n'est pas un noeud du DSL)."""
    return Multiply(Count(sabre_of_sacrifice_defeated_friends_selector()),
                    Get(int(extra_armor_per_unit)))


def sabre_of_sacrifice_behaviour_tree(extra_armor_per_unit: int):
    """`...SabreOfSacrificeAbility$$CreateBehaviour` -- MIRROR 1:1 (cf. l'en-tete du module).

    `duration_rounds=None` sur le `Pinned` : le `Nullable<AddEffectBehaviourOptions>` du site est a
    ZERO, donc `turnsNode` est NUL cote natif -> duree PAR DEFAUT de l'effet.
    `duration_rounds=1` sur l'armure : `TurnsFromRounds(<DSLFormulas+0x20> = Direct(1))`."""
    return op_and(
        AddEffect(PINNED_EFFECT, EffectType.Pinned.name, Target(),
                  duration_rounds=None, source_ref=Owner()),
        AddStaticStatModifierEffect(Caster(), EXTRA_ARMOR_EFFECT, int(StatType.FIXED_ARMOR),
                                    sabre_of_sacrifice_extra_armor_formula(extra_armor_per_unit),
                                    name=EffectType.SabreOfSacrifice_ExtraArmor.name,
                                    duration_rounds=1))


def relic_extra_armor_per_unit(state: State, owner_id: int) -> int:
    """`extraArmor` au niveau de l'`AbilityState` sous lequel la relique est MONTEE.

    `triggered_ability_state` rend le couple TERTIAIRE quand `SabreOfSacrifice` arrive par l'item
    equipe (le seul chemin reel : le gameconfig ne cable la relique en dur sur AUCUNE unite), le
    couple PASSIF sinon. Lire `passive_ability_level` a la place donnerait 50 sur tout runner
    normalise, donc TOUJOURS le dernier palier -- un ecart de magnitude SILENCIEUX."""
    lvl, mult = triggered_ability_state(state, owner_id, ABILITY_ID)
    return int(ability_var(ABILITY_ID, EXTRA_ARMOR_KEY, lvl, multiplier_pct=mult) or 0)


def _death_rider_visual_id() -> str:
    """`Config.GetStringConstant(0x0 = AbilityConstantType.unitId)` = la constante `unitId` du
    gameconfig de la relique (`astraNpc5DeathRider`).

    C'est bien une CONSTANTE d'ability, pas une donnee d'unite : le natif la relit a chaque
    construction du trigger. `IsUnitWithVisualId` la compare ensuite au `visualId` de l'entite."""
    import gameconfig as GC                      # meme entree que `ability_var`, chargee une fois
    cfg = GC.ability(ABILITY_ID) or {}
    return str(((cfg.get("constants") or {}).get(UNIT_ID_KEY)) or "")


class SabreOfSacrificeAbility(TriggeredAbility):
    """`SabreOfSacrificeAbility` -- sur CHAQUE attaque en CHARGE de Dreir (ou d'un Death Rider
    summon adjacent) : `Pinned` sur la cible + `+extraArmor x <allies normaux vaincus>` d'armure
    FIXE sur le chargeur, pour 1 round.

    `matches` = collapse du `CreateTrigger`, terme par terme et dans l'ordre LU."""
    event_id = int(EventTriggerType.Attack)                             # `On(0x9, alive: 1)`
    TRIGGERED_ABILITY_ID = SABRE_OF_SACRIFICE

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        caster_id, target_id = ev.actor_id, ev.target_id                # Caster@+0x48 / Target@+0x60
        if caster_id is None or target_id is None:
            return False
        ctx = entities_from_state(state, int(caster_id), int(target_id), owner_id=self.owner_id)
        # `IsCharging(Caster@+0x48, Target@+0x60)` -- le terme le PLUS discriminant, en tete comme
        # au natif (`op_BitwiseAnd` du dernier niveau).
        if not IsCharging(Caster(), Target()).evaluate(ctx):
            return False
        # `get_OwnerIsCaster  op_BitwiseOr  (<les trois termes du Death Rider>)`
        if int(caster_id) == int(self.owner_id):
            return True
        return bool(TriggerAnd(TriggerAnd(AreEqual(Parent(Caster()), Owner()),
                                          IsUnitWithVisualId(Caster(), _death_rider_visual_id())),
                               IsAdjacent(Owner(), Caster(),
                                          selection_type=_ADJACENT_SELECTION)).evaluate(ctx))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        caster_id, target_id = ev.actor_id, ev.target_id
        if caster_id is None or target_id is None:
            return None
        entities = entities_from_state(state, int(caster_id), int(target_id),
                                       owner_id=self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        per_unit = relic_extra_armor_per_unit(state, self.owner_id)
        sabre_of_sacrifice_behaviour_tree(per_unit).execute(entities, ectx)
        armor = next((p for (n, p) in ectx.emitted if n == "AddStaticStatModifierEffect"), {})
        return {"ability": ABILITY_ID, "owner": self.owner_id, "caster": int(caster_id),
                "target": int(target_id), "extra_armor_per_unit": per_unit,
                "extra_armor": armor.get("amount"), "emitted": list(ectx.emitted)}
