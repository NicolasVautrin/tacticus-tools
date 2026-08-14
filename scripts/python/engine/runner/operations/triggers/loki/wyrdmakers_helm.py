"""`WyrdmakersHelm` (#1037) -- relique UNIQUE de `spaceWolfPriest` (« Baldr »), item
`R_Booster_Crit_WyrdmakersHelm` (`isRelic`, `isUniqueRelic`, `allowedUnits = ['spaceWolfPriest']`).

i2 authoritatif (`Abilities/WyrdmakersHelm_CurrentLevelDescription`) :

> « During his turn, each time Baldr or an adjacent friendly unit gets healed for the first time this
> turn, Baldr immediately performs a normal melee attack. These attacks deal +{extraDmg} Damage and
> add Ice to the target's hex. »

UN SEUL artefact natif porte l'id `1504` -- verifie a la source, pas suppose :
`data/symbols/<build>/frida/classes.tsv` ne contient QU'UNE classe `Wyrdmaker*`,
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WyrdmakersHelmAbility` (base
`IdunBattle.Entities.Abilities.BaseTriggeredAbility`), et `search_symbols_by_name` n'en trouve que
les deux methodes ci-dessous. Il n'y a NI classe d'effet `WyrdmakersHelmEffect` NI seconde ability
-- contraste `TheArdentBlade` / `PhasalSubjugator` / `Maugetar`, qui en enregistrent plusieurs.
L'`EffectType.WyrdmakersHelm` (1505) n'est donc PAS une classe d'effet : c'est l'etiquette du
stat-mod STATIQUE que le behaviour pose puis retire dans le meme arbre (cf. plus bas).

⚠ **1504 et 1505 sont DEUX enums differents**, et l'ordinal ne le dit pas :
`IdunBattle.Entities.Enum.TriggeredAbilityType.WyrdmakersHelm = 1504` (l'ABILITY) et
`IdunBattle.Entities.Enum.EffectType.WyrdmakersHelm = 1505` (le stat-mod). Meme nom, valeurs
voisines : les confondre serait silencieux.

## RE (build `rnca9r7q6c`, decompile = verite)

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WyrdmakersHelmAbility$$CreateTrigger` :

      On(0x2c = EventTriggerType.UnitHealedWithRemoveEffects, ownerNeedsToBeAlive: true)
    & (   get_OwnerIsTarget
        | (   IsAdjacent(Owner@DSLSelectors+0x30, Target@DSLSelectors+0x60,
                         selectionType: 3 = UnitSelectionType.OnlyAliveAndTargetable)
            & AreFriends(Owner@+0x30, Target@+0x60,
                         comparisonType: 0 = UnitTeamSelectionType.ByCurrentTeam,
                         anyEntity: false) ) )
    & AmountIsEqual( TimesHealedThisTurn(Target@+0x60), <DSLFormulas+0x20> = Constant(1) )
    & <DSLTriggers+0x28> = IsTurnOf(Owner)

Chaque littéral est LU, aucun deduit :
  * `0x2c` -> `IdunBattle.DSL.EventTriggerType` (c'est le type DECLARE du 1er parametre de
    `DSLTriggers$$On`, lu dans `frida/methods.tsv`), membre `UnitHealedWithRemoveEffects` ;
  * `selectionType:IdunBattle.Entities.Enum.UnitSelectionType` et
    `comparisonType:IdunBattle.Entities.Enum.UnitTeamSelectionType` -- DEUX enums distincts pour deux
    parametres voisins, tous deux LUS dans `frida/methods.tsv` (`DSLTriggers.IsAdjacent` /
    `DSLTriggers.AreFriends`), jamais devines ;
  * `<DSLFormulas+0x20>` = `Constant(1)`, etabli par `IdunBattleLogic.Entities.DSLFormulas$$.ctor`,
    qui remplit ses cinq constantes dans l'ordre `+0x18 = 0`, `+0x20 = 1`, `+0x28 = 2`,
    `+0x30 = 100`, `+0x38 = -1`. C'est ce `1` qui EST le « for the FIRST time this turn » ;
  * `<DSLTriggers+0x28>` = `IsTurnOf(Owner)` (identification etablie par case-366-r1 SS2, et
    re-confirmee ici : `DSLTriggers$$InitializeShared` construit `+0x28` avec `selectors+0x30`
    = Owner). C'est le « During HIS turn » ;
  * `AmountIsEqual` a TROIS surcharges dans ce build, dont une (`180ed5190`) construit un
    `AmountIsGreaterAbilityTrigger` sous un nom `AmountIsEqual` (fold ICF / mislabel). Celle
    appelee ici est tranchee par les XREFS ENTRANTES, pas par le nom : `WyrdmakersHelmAbility$$
    CreateTrigger` appelle `180ed5120`, qui construit bien un
    `IdunBattle.Entities.Conditions.AmountIsEqualAbilityTrigger`. C'est une EGALITE.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WyrdmakersHelmAbility$$CreateBehaviour` :

    cibles  = Randomize( ValidNormalAttackTargets(Owner, Tiles(Owner), range: null,
                                                  ignoreRule: null, additionalRule: null) )
    triees  = SortUnitsByDamageUtility(cibles, caster: Owner,
                                       ability: UnitNormalAttackType(Owner),
                                       utilityDefinition: UtilityDefinition(0x23 = UtilityType.Damage),
                                       damage: NormalAttackDamage(Owner),
                                       unitSelectionType: 0 = UnitSelectionType.Any, hits: null)
    choisie = First(triees, amount: 1, ignoreForcedTargets: false)
    cache   = Cache( Tiles(choisie), matchAbilityEntities: true )

      AddStaticStatModifierEffectToOwner(0x5e1 = EffectType.WyrdmakersHelm,
                                         statType: 0 = StatType.Attack,
                                         amount: ConfigVar(8 = AbilityVariableType.extraDmg,
                                                           abilityState, config@this+0x20),
                                         turns: null, isHidden: false)
    + SetCache(cache)
    + UseNormalAttack(caster: Owner, target: choisie,
                      parentAbility: null, triggerAbilityOrEffect: null, options: <struct>)
    + RemoveEffect(Owner, Nullable(0x5e1), replaceableEffectType: null)
    + If( NOT IsDead(Owner),
          AddEffect(0x11 = EffectType.Ice, AbilityStateReference, targets: cache, turns: null),
          null )

L'ORDRE des cinq termes est celui des `IdunBattle.DSL.AbilityBehaviour$$op_Addition` du decompile,
et il PORTE LA MECANIQUE :
  * le stat-mod `+extraDmg` d'ATTAQUE est pose AVANT l'attaque et retire APRES -> il ne vaut QUE
    pour ce coup-la (« THESE attacks deal +X Damage »), et n'apparait jamais dans les stats
    consultables entre deux declenchements ;
  * `SetCache` FIGE la tuile de la cible AVANT l'attaque -> la glace atterrit sur l'hex meme si la
    cible y meurt du coup. Sans lui, `Tiles(choisie)` serait re-evalue apres l'attaque, sur une
    cible potentiellement morte ;
  * le `If` final gate sur `NOT IsDead(OWNER)`, pas sur la cible : si Baldr meurt de sa propre
    attaque (riposte / overwatch declenche), la glace n'est pas posee.

`extraDmg` (`gameconfig.units.abilities.WyrdmakersHelm.variables`) a **10 paliers**, 490 -> 728 :
le niveau de la relique change donc le resultat, et c'est ce qui rend un montage a niveau 1
SEPARANT d'un montage a niveau 10 (meme lecon que #1006 sur `Maugetar`/`PhoenixGem`).

ASCII only (console cp1252).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If, SetCache
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import Const, StatAmount, TimesHealedThisTurn
from .....entities.selectors.accessors import Owner, Target
from .....entities.selectors.geometry import Cache, Randomize
from .....entities.selectors.units import (First, SortUnitsByDamageUtility, Tiles,
                                           ValidNormalAttackTargets)
from .....entities.stats import StatType
from .....entities.triggers import (AmountIsEqual, AreFriends, IsAdjacent, IsDead, IsTurnOf, Not,
                                    OwnerIsTarget, TriggerAnd, TriggerOr)
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_selection_type import UnitSelectionType
from .....entities.unit_team_selection_type import UnitTeamSelectionType
from ....abilities.behaviours.combat import UseNormalAttack
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, AddStaticStatModifierEffect, RemoveEffect
from ....components import StatsComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

ABILITY_ID = "WyrdmakersHelm"
EXTRA_DMG_KEY = "extraDmg"                                   # `AbilityVariableType` 8 = extraDmg

#: `AddStaticStatModifierEffectToOwner(0x5e1, ...)` -- l'ETIQUETTE du stat-mod temporaire, pas une
#: classe d'effet (aucune `WyrdmakersHelmEffect` n'existe dans le build).
WYRDMAKERS_HELM_STAT_MOD = EffectType.WyrdmakersHelm          # EffectType 1505 (0x5e1)
#: `AddEffect(0x11, ...)` -- l'effet de TUILE pose sur l'hex de la cible.
ICE_TILE = EffectType.Ice                                     # EffectType 17 (0x11)
#: `StatType` du stat-mod : le 2e argument litteral `0` d'`AddStaticStatModifierEffectToOwner`
#: (`statType:IdunBattle.Entities.Enum.StatType`, type DECLARE lu dans `frida/methods.tsv`).
WYRDMAKERS_HELM_STAT = StatType.ATTACK                        # StatType.Attack = 0

#: `IsAdjacent(..., selectionType: 3)` et `SortUnitsByDamageUtility(..., unitSelectionType: 0)` --
#: deux litteraux du MEME enum, deux valeurs differentes, tous deux lus au decompile.
ADJACENCY_SELECTION = UnitSelectionType.OnlyAliveAndTargetable          # 3
SORT_SELECTION = UnitSelectionType.Any                                 # 0
#: `AreFriends(..., comparisonType: 0, anyEntity: false)` -- un AUTRE enum (`UnitTeamSelectionType`).
FRIENDS_COMPARISON = UnitTeamSelectionType.ByCurrentTeam               # 0

#: `AmountIsEqual(TimesHealedThisTurn(Target), <DSLFormulas+0x20>)`. `+0x20` est la constante `1`
#: (cf. `DSLFormulas$$.ctor`, en-tete de module) : « for the FIRST time this turn ».
FIRST_HEAL_OF_TURN = 1


def wyrdmakers_helm_trigger_tree():
    """Mirror 1:1 de `WyrdmakersHelmAbility$$CreateTrigger`, PRIVE de son terme `On(0x2c)`.

    L'`On(...)` natif n'est pas un noeud du port : c'est le `event_id` de la classe, que le dispatch
    consulte AVANT d'evaluer quoi que ce soit (`evaluate_trigger_operation`). Le reste de l'arbre est
    ecrit tel quel -- l'ASSOCIATIVITE est celle du decompile, lue sur l'ordre des
    `op_BitwiseOr`/`op_BitwiseAnd` :

        ((On & (OwnerIsTarget | (IsAdjacent & AreFriends))) & AmountIsEqual) & IsTurnOf(Owner)

    Le `TriggerOr` est LITTERAL (`IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr`), pas une reecriture :
    le porteur soigne LUI-MEME satisfait la branche gauche sans avoir a etre son propre voisin
    adjacent -- ce que la branche droite lui refuserait (`IsAdjacent` n'est pas reflexif)."""
    voisin_ami = TriggerAnd(
        IsAdjacent(Owner(), Target(), selection_type=int(ADJACENCY_SELECTION)),
        AreFriends(Owner(), Target(), selection_type=FRIENDS_COMPARISON))
    return TriggerAnd(
        TriggerAnd(
            TriggerOr(OwnerIsTarget(), voisin_ami),
            # `AmountIsEqual(TimesHealedThisTurn(Target), <DSLFormulas+0x20> = Constant(1))`.
            # L'increment natif PRECEDE l'emission du vecteur, donc au PREMIER soin du tour ce
            # compteur vaut deja 1 (cf. `dispatch/heal.py`) ; un second soin le porte a 2 -> plus
            # d'egalite. C'est LA le « for the FIRST time this turn ».
            AmountIsEqual(TimesHealedThisTurn(Target()), Const(FIRST_HEAL_OF_TURN))),
        # `<DSLTriggers+0x28>` = `IsTurnOf(Owner)` -- « During HIS turn ».
        IsTurnOf(Owner()))


def wyrdmakers_helm_behaviour_tree(extra_dmg: int):
    """Mirror 1:1 de `WyrdmakersHelmAbility$$CreateBehaviour` (cf. en-tete de module).

    ⚠ **L'arbre est REBATI a chaque declenchement, et c'est OBLIGATOIRE** : le noeud `Cache` memoise
    dans son INSTANCE (`CacheSelector` slot `+0x28`). Un arbre garde entre deux soins reposerait la
    glace sur la tuile du declenchement PRECEDENT. Meme regime que `getemruntz_tree()`.

    `extra_dmg` est resolu par l'APPELANT : le natif l'attache par un noeud `DSLFormulas$$ConfigVar`
    qui referme l'`abilityState` et la `config@this+0x20` recus en argument de `CreateBehaviour` --
    donc une grandeur deja liee a l'ability quand l'arbre se batit, pas un noeud qui irait relire
    l'unite courante."""
    cible = First(SortUnitsByDamageUtility(
        Randomize(ValidNormalAttackTargets(Owner(), Tiles(Owner()))),
        Owner(),
        # `damage: NormalAttackDamage(Owner)` -- aucune classe `NormalAttackDamage` n'existe cote
        # port : le natif la construit comme `StatAmountFormula(unit, StatType.Attack)`, ce que la
        # docstring de `SortUnitsByDamageUtility` etablit deja. Meme noeud, meme valeur.
        StatAmount(Owner(), int(StatType.ATTACK)),
        # `ability: UnitNormalAttackType(Owner)` rend exactement le defaut natif
        # (`AbilityOrEffect(GetNormalAttackType(owner))`) -> `None` cote port : ce n'est pas une
        # omission, c'est la MEME valeur par les deux chemins (cf. docstring du noeud).
        ability=None,
        selection_type=int(SORT_SELECTION),
        # `hits: null` -> le noeud rend 1, comme le natif.
        hits=None))
    # `Cache(Tiles(choisie), matchAbilityEntities: true)`. Le 2e argument natif (`true`) selectionne
    # le mode de memoisation KEYE PAR CONTEXTE (`+0x30`) plutot que le slot unique ; le port n'a que
    # le slot unique, et c'est EXACT ici -- l'arbre est rebati par declenchement et les deux
    # consommateurs (`SetCache`, `AddEffect`) l'evaluent sous le MEME contexte top-level.
    cache = Cache(Tiles(cible))
    return _Seq([
        # 1. `AddStaticStatModifierEffectToOwner(1505, StatType.Attack, ConfigVar(extraDmg), null,
        #    isHidden: false)`. La surcharge `...ToOwner` passe `source = targets = Owner` ; le port
        #    n'a que `AddStaticStatModifierEffect`, dont la docstring etablit que source et cible
        #    coincident dans ce cas -> MEME entite, MEME resultat.
        AddStaticStatModifierEffect(Owner(), int(WYRDMAKERS_HELM_STAT_MOD),
                                    int(WYRDMAKERS_HELM_STAT), int(extra_dmg),
                                    name=str(WYRDMAKERS_HELM_STAT_MOD.name),
                                    # `turns: null` -> aucune duree posee : le stat-mod vit le temps
                                    # de l'arbre et c'est le `RemoveEffect` (terme 4) qui le retire.
                                    duration_rounds=None, duration_turns=None),
        # 2. `SetCache(cache)` -- FIGE la tuile AVANT l'attaque (cf. en-tete de module).
        SetCache(cache),
        # 3. `UseNormalAttack(Owner, choisie, null, null, options)`.
        UseNormalAttack(Owner(), cible),
        # 4. `RemoveEffect(Owner, Nullable(1505), null)` -- retire le bonus, donc il n'a valu QUE
        #    pour l'attaque du terme 3.
        RemoveEffect(int(WYRDMAKERS_HELM_STAT_MOD), Owner()),
        # 5. `If(NOT IsDead(Owner), AddEffect(Ice, AbilityStateReference, cache, null), null)`.
        #    Le gate porte sur le PORTEUR, pas sur la cible.
        If(Not(IsDead(Owner())),
           AddEffect(int(ICE_TILE), str(ICE_TILE.name), cache, duration_rounds=None)),
    ])


class _Seq:
    """`IdunBattle.DSL.AbilityBehaviour$$op_Addition` chaine : execute les termes DANS L'ORDRE et
    agrege les resultats. Le natif combine par `CombinedBehaviour`, dont `Execute` propage le flag
    d'arret ; aucun terme de CET arbre n'en pose (les cinq sont des feuilles pures ou un `If`), donc
    la sequence se deroule entiere -- c'est l'ORDRE qui porte la mecanique, pas un court-circuit."""
    __slots__ = ("terms",)

    def __init__(self, terms):
        self.terms = list(terms)

    def execute(self, entities, ectx):
        res = None
        for t in self.terms:
            r = t.execute(entities, ectx)
            res = r if res is None else res.combine(r)
        return res


def extra_dmg(state: State, owner_id: int) -> int:
    """`DSLFormulas$$ConfigVar(8 = AbilityVariableType.extraDmg, abilityState, config@this+0x20)`.

    MEME arbitrage d'`abilityState` que `DawnBlade` / `Maugetar` / `PhoenixGem`, et par le MEME foyer
    unique `triggered_ability_state` (#357) : couple TERTIAIRE (`TertiaryAbilityLevel`,
    `TertiaryAbilityVariablesMultiplierPercentage`) quand la relique est EQUIPEE, couple PASSIF quand
    `WyrdmakersHelm` est cablee au kit d'un npc -- ou quand le canal tertiaire n'a pas ete fourni au
    chargement.

    ⚠ **NE PAS lire le niveau sur une instance d'effet**, lecon MESUREE de #1006 : une instance
    captee publie `ability_level = 50` (l'etat PASSIF du porteur sur tout runner normalise) quel que
    soit le niveau reel de la relique, ce qui clamperait TOUJOURS au dernier palier. Ici la question
    ne se pose meme pas -- l'ability n'a pas d'effet-marqueur d'ou lire un niveau -- mais le foyer
    reste le meme, et c'est lui qui garantit qu'un montage a niveau 1 rend 490 et non 728.

    `extraDmg` n'est PAS dans `variablesAffectedByRarityBonus` du gameconfig de `WyrdmakersHelm` (la
    cle `upgrades` y est `null` et `variables` ne porte que `extraDmg`) -> le `multiplier_pct` ne
    s'applique pas (`ability_var` gate son application sur cette liste) ; on le passe quand meme,
    parce que c'est le natif qui decide -- pas nous. 0 si l'unite / son contexte / la variable
    manquent -> le stat-mod est alors pose a 0, exactement comme un `ConfigVar` natif sans palier."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None or getattr(sc, "ctx", None) is None:
        return 0
    lvl, mult = triggered_ability_state(state, owner_id, ABILITY_ID)
    return int(ability_var(ABILITY_ID, EXTRA_DMG_KEY, lvl, multiplier_pct=mult) or 0)


class WyrdmakersHelmAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WyrdmakersHelmAbility` -- pendant SON tour,
    la premiere fois qu'un soin touche le porteur ou un ALLIE ADJACENT, le porteur porte une attaque
    normale a `+extraDmg` et glace l'hex de sa cible.

    Le vecteur `On(0x2c = UnitHealedWithRemoveEffects)` est emis par
    `runner/operations/triggers/dispatch/heal.py` (pose par la meme tranche : sans lui cette classe
    serait inscrite au registre et JAMAIS declenchee)."""
    event_id = EventTriggerType.UnitHealedWithRemoveEffects        # `On(0x2c, ownerNeedsToBeAlive: true)`
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.WyrdmakersHelm)        # 0x5e0 = 1504

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        healed_id = ev.target_id            # `EvaluateAbilities(caster, caster, healed, 0x2c, ...)`
        if healed_id is None:
            return False
        # `ownerNeedsToBeAlive: true` -- le 2e argument litteral de `DSLTriggers$$On`. Il est
        # AILLEURS que dans l'arbre : le natif le passe a la fabrique du trigger d'evenement, pas
        # comme un noeud compose -> le port le garde ici, hors de `wyrdmakers_helm_trigger_tree`.
        owner = state.get_entity(self.owner_id)
        ouc = owner.get_component(UnitComponent) if owner is not None else None
        if ouc is None or not ouc.alive:
            return False
        # Tout le reste du `CreateTrigger` EMERGE de l'arbre (doctrine #149) : aucun gate n'est
        # recable a la main ici. `Owner` = le porteur du helm, `Target` = l'unite SOIGNEE (le natif
        # la passe en 3e argument d'`EvaluateAbilities`, cf. `dispatch/heal.py`).
        entities = entities_from_state(state, self.owner_id, int(healed_id))
        return bool(wyrdmakers_helm_trigger_tree().evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        amount = extra_dmg(state, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        # Le behaviour natif ne lit NI le soigneur NI l'unite soignee : `Owner` est le seul selecteur
        # d'entite de l'arbre, et la cible de l'attaque est choisie par `SortUnitsByDamageUtility`.
        # `entities_from_state(state, owner)` pose donc `caster = owner`, comme `DawnBlade`.
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        wyrdmakers_helm_behaviour_tree(amount).execute(entities, ectx)
        attacks = [p for (n, p) in ectx.emitted if n == "UseNormalAttack"]
        ices = [p for (n, p) in ectx.emitted if n == "AddEffect"
                and int(p.get("effect_type") or -1) == int(ICE_TILE)]
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "healed": None if ev.target_id is None else int(ev.target_id),
                "extra_dmg": int(amount), "attacks": attacks, "ice": ices}
