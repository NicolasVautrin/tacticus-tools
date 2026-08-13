"""`ParagonSpear` (0x5d6 = 1494) -- la relique de `custoKyrus` (Adeptus Custodes). #1013

i2 : au debut de son tour, Kyrus lance sa lance sur un ennemi -- de preference un ennemi ADJACENT,
a defaut le plus proche dans un rayon de `range`, en ligne de vue degagee.

VOIE D'ATTRIBUTION : item RELIQUE (`UnitConfiguration.TertiaryAbility`), donc `RELIC_ABILITY_TRIGGERS`
et l'`AbilityState` TERTIAIRE (`level_slot="tertiary"`). UN seul porteur, `custoKyrus`, DANS le pool
rank 17 -> `--equip-relic "custoKyrus:ParagonSpear:<niveau>"` suffit (etat 2 de la gate relique, aucune
injection catalogue). Ce n'est PAS une active : ni `ABILITY_CLASSES`, ni `TARGETING_OPTIONS`, ni
`ABILITY_ATTACK_TYPE`.

DECOMPILE (build `rnca9r7q6c`), UNE seule classe native, TROIS methodes.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ParagonSpearAbility$$GetPossibleTargets` :

    adjacents = Damageable( AdjacentEnemies(Owner@DSLSelectors+0x30,
                                            unique: 1,
                                            selectionType: 3 = OnlyAliveAndTargetable) )

    distants  = Damageable( Enemies( of       = Owner@+0x30,
                                     entities = Unobscured( caster  = Owner@+0x30,
                                                            targets = SurroundingUnits(
                                                                origin        = Owner@+0x30,
                                                                range         = Config.GetNumberConstant(0x16 = range),
                                                                unique        = 1,
                                                                includeCenter = 0,
                                                                selectionType = 3) ),
                                     selectionType: 3 ) )

    return If( AmountIsGreaterThanZero(adjacents), adjacents, distants )

⚠ Le sélecteur `If` est le TROISIEME homonyme du DSL (`DSLSelectors$$If`, kind S) -- porte sous le nom
`SelectIf`, et il n'evalue QU'UNE branche. Les deux branches sont ici PURES (aucun tirage), donc ce
point ne pese pas sur le RNG ici, contrairement a `DiveAttackAbilityBase`.

⚠ L'ancre geometrique des DEUX branches est `Owner@+0x30`, PAS `Caster@+0x48` -- les deux slots sont
LUS sans ambiguite (`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsActor` construit
`AreEqual(DSLSelectors+0x30, DSLSelectors+0x40)`, `$$get_OwnerIsCaster` `AreEqual(+0x30, +0x48)`).
Sur CE trigger ils coincident (`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` s'execute
sur son propre porteur, et `On(TurnStart_Actions)` n'apporte aucun acteur externe), mais le port thread
quand meme `owner_id=` (#1002) pour que le slot cite soit celui que le natif cite.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ParagonSpearAbility$$CreateTrigger` :

    On(0x16 = EventTriggerType.TurnStart_Actions, ownerNeedsToBeAlive: 1)
      op_BitwiseAnd <DSLTriggers+0x28 = IsTurnOf(Owner@DSLSelectors+0x30)>
      op_BitwiseAnd AmountIsGreaterThanZero(GetPossibleTargets())

⚠ Le champ `DSLTriggers+0x28` est ecrit par `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` et
n'a AUCUN getter : son identite se lit par le TYPE alloue (`DAT_1833ab568`), dont l'unique autre
constructeur du binaire est `IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf` -- donc
`IsTurnOf(Owner@+0x30)`. Meme champ, meme lecture que la relique `ArmourOfShriekingSouls`.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ParagonSpearAbility$$CreateBehaviour` :

    AttackWithAttackDamage(
        caster        = Caster@DSLSelectors+0x48,
        target        = First( SortByDistance( Randomize(GetPossibleTargets()), Owner@+0x30 ),
                               amount: 1, ignoreForcedTargets: 0 ),
        amount        = IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage(abilityState),
        damageProfile = Config.GetDamageProfile(),                 # constante `damageProfile` = Bolter
        hits          = Config.GetNumberConstant(0x2f = nrOfHits),  # = 2
        abilityOrEffect = AbilityOrEffect(<cette ability>),
        options       = default(Nullable<AttackDamageBehaviourOptions>),   # 32 octets NULS au site
        selectionType = 2 = OnlyTargetable )

  * la surcharge est `...$$AttackWithAttackDamage(caster, target, amount, damageProfile :
    IDamageProfileSelector, hits : System.Int32, abilityOrEffect, options, selectionType)` -- TYPES
    DECLARES lus dans `frida/methods.tsv`, pas devines : `GetDamageProfile` rend un
    `IDamageProfileSelector` et `GetNumberConstant` un `Int32`, ce qui designe UNE seule des cinq.
  * `Randomize` puis `SortByDistance` puis `First(1)` : le tri natif
    (`IdunBattle.Entities.Selectors.SortByDistanceSelector$$Select`) est STABLE, donc la permutation
    aleatoire ne survit QUE sur les EX AEQUO de distance. Traduction : « l'ennemi le plus proche, au
    hasard parmi les ex aequo ». C'est exactement le regime `Randomize -> tri stable -> First` que
    documente `entities/selectors/geometry.Randomize`.
  * `Randomize` = `PickRandomly(source, 0x7fffffff, allowRepeat: 0, maxRepeats: 0x7fffffff,
    skipForced: 0)` -> permutation COMPLETE : **`len(pool)` tirages** (bornes decroissantes, le
    dernier tirage sur un pool de 1 consomme quand meme un `genrand_int32`, loi #130/#215). Le
    contexte du runner porte ce canal (`DslContext.pick_randomly`, cable par
    `runner/abilities/behaviours/context.entities_from_state`), donc l'arbre reste DSL PUR -- pas de
    collapse imperatif a la `MartialApotheosis`, dont la docstring (« le DslContext ne porte pas
    state.rng ») est PERIMEE depuis que le canal existe.
  * `First(entities, amount : System.Int32, ignoreForcedTargets)` est un WRAPPER : il emballe
    l'`amount` dans un `Direct` et delegue a la surcharge `IAmountFormula`, laquelle construit un
    `IdunBattle.Entities.Selectors.PickFirstNSelector` -- donc `PickFirstN(source, 1)` cote port, PAS
    `PickAtIndexSelector` (classe DISTINCTE, autre factory).
  * `attackRangeType = "Ranged"` (gameconfig) -> `is_melee=False` : Kyrus LANCE sa lance.

FORME DU PORT (doctrine #149) : le `CreateTrigger` COLLAPSE imperativement dans `matches` (+
`event_id`), le `CreateBehaviour` et le `GetPossibleTargets` sont des ARBRES DSL dont la feuille
appelle l'Operation deja portee.

⚠ LIMITE CONNUE, NOMMEE : les noeuds portes `Enemies` / `AdjacentEnemies` prennent leur referent
d'equipe dans `ctx.caster` et non dans leur argument `of`. Sur CE call-site c'est EXACT (Owner ==
Caster, cf. plus haut) ; ca ne le serait pas sur un trigger ou les deux divergent. Le port ne
contourne pas -- il thread `owner_id=` et le dit.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.selectors.accessors import Owner
from .....entities.selectors.geometry import PickFirstN, Randomize, SelectIf
from .....entities.selectors.units import (AdjacentEnemies, Damageable, Enemies, SortByDistance,
                                           SurroundingUnits, Unobscured)
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsGreaterThanZero
from .....entities.unit_selection_type import UnitSelectionType
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....components import OwnerComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

ABILITY_ID = "ParagonSpear"
PARAGON_SPEAR = int(TriggeredAbilityType.ParagonSpear)               # 0x5d6 = 1494

# ⚠ LES TROIS CLES SONT DES **CONSTANTES** (`GetNumberConstant` / `GetDamageProfile`), pas des
# variables de niveau : leurs ordinaux existent AUSSI dans `AbilityVariableType` en nommant autre
# chose (`22` = `range` ici / `blockDmg_2` la-bas). Seul le NOM rend la confusion visible.
RANGE_KEY = AbilityConstantType.range.name                           # `AbilityConstantType` 0x16 = 22
NR_OF_HITS_KEY = AbilityConstantType.nrOfHits.name                   # `AbilityConstantType` 0x2f = 47
DAMAGE_PROFILE_KEY = AbilityConstantType.damageProfile.name          # `AbilityConstantType` 0x2e = 46

#: `selectionType` des trois selecteurs de `GetPossibleTargets` (le litteral `3` du site).
_TARGET_SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)    # 3
#: `selectionType` de la feuille `AttackWithAttackDamage` (le litteral `2` du site). Transcrit :
#: la feuille portee resout deja sa cible depuis un pool `Damageable`, ce filtre-ci est donc
#: redondant sur CE call-site -- il est nomme pour que le port cite ce que le natif ecrit.
_ATTACK_SELECTION = int(UnitSelectionType.OnlyTargetable)            # 2


def _config_constant(key: str) -> str:
    """Constante STRING du gameconfig (`AbilityConfiguration$$GetStringConstant` /
    `$$GetDamageProfile`). `ability_var(..., is_constant=True)` ne convient pas : il `int()` la
    cellule, ce qui leve sur `"Bolter"`. Meme entree que `ability_var` (module `gameconfig`),
    chargee une fois."""
    import gameconfig as GC                                   # DIFFERE et PORTEUR : cf. `magnitude`
    cfg = GC.ability(ABILITY_ID) or {}
    return str(((cfg.get("constants") or {}).get(key)) or "")


def paragon_spear_range() -> int:
    """`Config.GetNumberConstant(0x16 = range)` -- rayon de la branche DISTANTE. Constante (2 au
    build courant), donc INDEPENDANTE du niveau de relique."""
    try:
        return int(_config_constant(RANGE_KEY))
    except (TypeError, ValueError):
        return 0                                              # `GetNumberConstant` d'un index absent = 0


def paragon_spear_damage_profile() -> str:
    """`Config.GetDamageProfile()` = la constante `damageProfile` (Bolter au build courant)."""
    return _config_constant(DAMAGE_PROFILE_KEY)


def paragon_spear_adjacent_targets():
    """Branche ADJACENTE de `GetPossibleTargets` :
    `Damageable(AdjacentEnemies(Owner@+0x30, unique: 1, selectionType: 3))`.

    Surcharge A d'`IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies` (`this, unit, unique,
    selectionType`) -- tranchee par l'ARITE et la position du litteral `3`, pas par le pseudo-C : la
    surcharge B a pour 3e argument une ENTITE (l'ancre geometrique), et poser `3` en `unique` y
    donnerait un masque FAUX. Le port ne modelise pas `unique` (la deduplication est implicite) et
    porte le `selectionType`."""
    return Damageable(AdjacentEnemies(Owner(), selection_type=_TARGET_SELECTION))


def paragon_spear_ranged_targets(range_const: int):
    """Branche DISTANTE de `GetPossibleTargets` :
    `Damageable(Enemies(Owner, Unobscured(Owner, SurroundingUnits(Owner, range, 1, 0, 3)), 3))`.

    ⚠ `includeCenter = 0` -> le porteur lui-meme est EXCLU de l'anneau (defaut du noeud porte).
    ⚠ L'ordre des operandes d'`Unobscured` est INVERSE entre natif et port : le natif ecrit
    `Unobscured(caster, targets)`, le noeud porte `Unobscured(source, from_ref)`."""
    ring = SurroundingUnits(Owner(), Const(int(range_const)), include_center=False,
                            selection_type=_TARGET_SELECTION)
    return Damageable(Enemies(Unobscured(ring, Owner()), selection_type=_TARGET_SELECTION))


def paragon_spear_possible_targets(range_const: int):
    """Mirror 1:1 de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ParagonSpearAbility$$GetPossibleTargets` :
    `If(AmountIsGreaterThanZero(adjacents), adjacents, distants)`.

    Selecteur DSL **PUR** (aucun tirage) : c'est ce qui autorise le gate du trigger a l'evaluer
    sans desaligner le flux RNG, exactement comme le natif -- qui construit trois arbres distincts
    et ne pose `Randomize` que dans `CreateBehaviour`."""
    adjacents = paragon_spear_adjacent_targets()
    return SelectIf(AmountIsGreaterThanZero(adjacents), adjacents,
                    paragon_spear_ranged_targets(range_const))


def paragon_spear_target_selector(range_const: int):
    """`First(SortByDistance(Randomize(GetPossibleTargets()), Owner@+0x30), 1, 0)`.

    Le SEUL etage consommateur de RNG de cette ability (`len(pool)` tirages), et le tri stable qui
    suit le reduit a un depart au sort entre EX AEQUO de distance."""
    return PickFirstN(SortByDistance(Randomize(paragon_spear_possible_targets(range_const)),
                                     Owner()), 1)


def paragon_spear_behaviour_tree(range_const: int, profile: str):
    """Mirror 1:1 de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ParagonSpearAbility$$CreateBehaviour` : UNE
    feuille `AttackWithAttackDamage`.

    `level_slot="tertiary"` : les bornes `minDmg`/`maxDmg` sont indexees par le niveau de la
    RELIQUE (`TertiaryAbilityLevel` + `TertiaryAbilityVariablesMultiplierPercentage`, foyer unique
    `triggered_ability_state`, #357), PAS par le niveau des PASSIFS du porteur -- lequel vaut 50
    dans tout runner normalise et clamperait donc SILENCIEUSEMENT au dernier palier.
    `native_factory="attack"` (defaut) : `CreateBehaviour` appelle bien
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`, pas `...AttackWithAbilityDamage`
    -- classe par le call-site, jamais au juge."""
    return AttackWithAttackDamage(paragon_spear_target_selector(range_const), ABILITY_ID, profile,
                                  is_melee=False,          # `attackRangeType = "Ranged"`
                                  multi=True,              # selecteur -> N cibles (ici 1, par `First`)
                                  hits_key=NR_OF_HITS_KEY,
                                  ability_type=PARAGON_SPEAR,
                                  level_slot="tertiary")


class ParagonSpearAbility(TriggeredAbility):
    """`ParagonSpearAbility` (triggered 0x5d6 = 1494, relique de `custoKyrus`) -- cf. en-tete.

    `On(TurnStart_Actions=0x16, ownerNeedsToBeAlive: 1) & IsTurnOf(Owner) &
    AmountIsGreaterThanZero(GetPossibleTargets())` ->
    `AttackWithAttackDamage(First(SortByDistance(Randomize(GetPossibleTargets()), Owner), 1),
    nrOfHits coups profil Bolter, bornes minDmg/maxDmg au niveau TERTIAIRE)`."""
    event_id = int(EventTriggerType.TurnStart_Actions)                # On(0x16 = 22)
    TRIGGERED_ABILITY_ID = PARAGON_SPEAR

    def _entities(self, state: State):
        """`AbilityEntities` du behaviour : Owner ET Caster sur le porteur (le natif les fait
        coincider sur ce trigger -- cf. l'en-tete), `owner_id=` threade explicitement pour que
        `Owner()` ne passe pas par son repli."""
        return entities_from_state(state, int(self.owner_id), owner_id=int(self.owner_id))

    def _pool(self, state: State) -> list:
        """`GetPossibleTargets()` evalue -- le POOL du gate, sans `Randomize` (donc ZERO tirage,
        comme le `CreateTrigger` natif)."""
        ctx = self._entities(state)
        pool = paragon_spear_possible_targets(paragon_spear_range()).evaluate(ctx)
        return [u for u in (pool or []) if isinstance(u, dict) and u.get("id") is not None]

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        ent = state.get_entity(self.owner_id)
        if ent is None:
            return False
        # `On(0x16, ownerNeedsToBeAlive: 1)` -- le porteur doit etre VIVANT.
        uc = ent.get_component(UnitComponent)
        if uc is None or not uc.alive:
            return False
        # `IsTurnOf(Owner@+0x30)` : `start_turn_triggers` porte le joueur dont le tour DEBUTE ;
        # `IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger$$ShouldTrigger` compare
        # `OwnerComponent.CurrentPlayerEntityId` au joueur courant. Non threade -> FAUX (on ne
        # fabrique pas un tour), meme lecture que `ArmourOfShriekingSouls`.
        if ev.player_id is None:
            return False
        oc = ent.get_component(OwnerComponent)
        if oc is None or int(oc.player) != int(ev.player_id):
            return False
        # `AmountIsGreaterThanZero(GetPossibleTargets())` : sans cible eligible, le trigger ne fire
        # PAS (gate natif -- ne pas le rabattre sur un behaviour qui ne ferait rien).
        return len(self._pool(state)) > 0

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        entities = self._entities(state)
        ectx = ExecutionContext(state=state, rng=state.rng)
        rng_range = paragon_spear_range()
        profile = paragon_spear_damage_profile()
        paragon_spear_behaviour_tree(rng_range, profile).execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        atk = atks[0] if atks else None
        return {"ability": ABILITY_ID, "owner": int(self.owner_id), "caster": int(self.owner_id),
                "target": (atk.get("target") if atk else None),
                "attack": (atk.get("attack") if atk else None),
                "range": rng_range, "profile": profile, "dsl": True}
