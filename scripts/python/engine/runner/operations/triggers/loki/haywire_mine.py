"""`Abilities.Triggered.Loki.HaywireMineSteppableAbility` -- LA MINE QUI EXPLOSE QUAND ON MARCHE
DESSUS (#462-r4b-r1-r1-r1-r1-c-r3-r1-r3).

C'est l'ability du jeu qui n'existe QUE pour le regime « `Steppable` ECRASE » : son `CreateTrigger`
teste `HasDeathReason(Owner, DamageReason.Steppable)`, valeur que **seul** un crush grave. Elle est
donc la PREUVE, independante de toute deduction, que le natif publie bien `On(1 = PreUnitDeath)`
pour un crush et y enregistre la raison 2 -- les deux residus `-r1` et `-r2` dont ce module depend.

PORTEURS (voies d'attribution `unit_map`) : `astarSmnHaywireMine` (**SUMMON** -- confrontable en
amenant son summoner) et `astarNpc1HaywireMine` (npc). Le summoner est `astarCyrus` (HERO `lineup`,
hors seed BC -> `catalog_inject`), dont le passif `HaywireMine` (1531) pose la mine sur sa tuile
PRECEDENTE a chaque deplacement (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.
HaywireMineAbility$$CreateTrigger` = `(On(4 = UnitAfterMove) & OwnerIsActor & TriggeringAbilityIsNone)
| (On(0x29) & OwnerIsActor & AmountIsZero(GetPersistentData(...)))`). CE passif-la EST porte depuis
`#462-r4b-r1-r1-r1-r1-c-r3-r1-r5` (seconde moitie du module).

--------------------------------------------------------------------------------------------------
ARTEFACTS NATIFS (decompile ghidra, build `rnca9r7q6c` -- decompile = verite)
--------------------------------------------------------------------------------------------------

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HaywireMineSteppableAbility$$CreateTrigger`
(conjonction `op_BitwiseAnd`, lue noeud par noeud ; `sel+0x30 = Owner`, `sel+0x40 = Actor`) :

    OnPreDeath(<null>, ignoreOverkill = 1)             # `On(1)`, AUCUN gate overkill
    & get_OwnerIsTarget                                # la MINE est le mourant (@0x178)
    & HasDeathReason(Owner@sel+0x30, 2, <Nullable VIDE>)   # DamageReason.Steppable, aucun filtre d'ability
    & NOT HasTrait(Actor@sel+0x40, 0x1b = Steppable)   # celui qui marche dessus n'est pas lui-meme une mine
    & IsAlive(Actor@sel+0x40)
    & AreEnemies(Owner@sel+0x30, Actor@sel+0x40, 0 = ByCurrentTeam)

`...$$CreateBehaviour` (arbre lu de bas en haut ; `0x606` = `TriggeredAbilityType.HaywireMineSteppable`) :

    atk1 = AttackWithAbilityDamage( caster = Owner@sel+0x30, target = Actor@sel+0x40,
                                    amount  = RandomAmount(ConfigVar(0xc = minDmg),
                                                           ConfigVar(0xd = maxDmg)),
                                    profile = DamageProfileFromConfig(0x2e = damageProfile),
                                    hits    = ConfigConst(0x2f = nrOfHits),
                                    src     = AbilityOrEffect(0x606),
                                    selectionType = 1 )
    atk2 = <le meme, avec 0x36 = minDmg_2, 0x37 = maxDmg_2, 0x3f = damageProfile_2,
            0x32 = nrOfHits_2>
    If( HasTrait(Actor@sel+0x40, 5 = Mechanical), op_Addition(atk1, atk2), atk1 )

    => tout le monde prend `atk1` ; une cible **MECHANICAL** prend EN PLUS `atk2`. C'est le « haywire »
       du nom : le second volet est l'anti-vehicule.

CONFIG (gameconfig `HaywireMineSteppable`, ZERO hardcode -- lue par `ability_var`) :
    variables `minDmg`/`maxDmg`/`minDmg_2`/`maxDmg_2` (per-niveau, TOUTES dans
    `variablesAffectedByRarityBonus` -> scalees par le multiplicateur de l'AbilityState),
    constantes `nrOfHits = 1`, `damageProfile = Blast`, `nrOfHits_2 = 2`, `damageProfile_2 = Energy`,
    `attackRangeType = Melee`.

GROUND TRUTH LIVE (runner MC1_67, `astarCyrus` injecte au catalogue, seed 777) : Cyrus se deplace ->
`AddUnit e=103/106 Unit_IsSummoned=1 Unit_Parent_Id=<Cyrus>` + `ChangeAbility
UnitStats_TriggeredAbility_Id=1542 Level=50 VariableMultiplierPercentage=180` ; un `orksNob` ENNEMI
marche ensuite sur la tuile de la mine ->

    [Ability_Power e=106 «HaywireMineSteppable»]
      [Damage e=79]  Amount=1403 DamageProfileType=18 (Blast) Attacker_Id=106 Target_Id=79
                     Attack_DidBlock=1 Attack_DidCrit=0
    [/]
    DirectlyKillUnit e=106 / RemoveUnitFromTiles e=106 / RemoveUnit e=106

-> l'explosion PRECEDE le retrait de la mine du plateau, exactement comme `On(1 = PreUnitDeath)`
precede `processor.<slot 6>` dans `IdunBattle.Operations.KillUnitOperation$$Execute`. `orksNob`
n'etant pas `Mechanical`, seul `atk1` (Blast, 1 coup) est parti.

DOCTRINE #149 : le TRIGGER est collapse imperativement (lecture d'etat pure : OwnerIsTarget,
HasDeathReason, HasTrait, IsAlive, AreEnemies -- meme choix que `cosmic_horror.py`) ; le BEHAVIOUR
est un ARBRE DSL (`If` / `op_add` / `AttackWithAbilityDamage`), donc le degat passe par
`AbilityDamageOperation` avec ses etages (percage, armure, mods defenseur, block, bouclier, caps).

LA POSE, elle, est portee depuis `#462-r4b-r1-r1-r1-r1-c-r3-r1-r5` -- cf. la seconde moitie de ce
module (`HaywireMinePlaceOnMoveAbility` / `HaywireMinePlaceOnTurnEndAbility` /
`HaywireMineResetAbility` / `HaywireMineCustomAbility`) et
`docs/rl/case-462-r4b-r1-r1-r1-r1-c-r3-r1-r5-pose-mine-haywire.md`.

RESIDU NOMME :
  * l'argument `selectionType = 1` (`UnitSelectionType.OnlyAlive`) du 8e slot d'
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` n'a pas d'equivalent dans la
    feuille portee : il est REDONDANT ici avec le `IsAlive(Actor)` du trigger, qui vient d'etre
    evalue sur la meme entite.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If, op_add, op_and
from .....entities.damage_reason import DamageReason
from .....entities.formulas import RandomAmount
from .....entities.selectors.accessors import Actor, Owner
from .....entities.traits.unit_trait import UnitTrait, has_trait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import HasTrait
from ....abilities.behaviours.combat import AttackWithAbilityDamage
from ....abilities.behaviours.context import entities_from_state
from ....components import OwnerComponent, StatsComponent, UnitComponent
from ....state import State
from ..base import (TriggeredAbility, TriggerEvent, triggered_ability_state,
                    _unit_trait_names)
from .reactivate_overwatch import has_death_reason
from .....utilities.utility_type import UtilityType   # #270-r1-r1-r3
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import Count as CountF
from .....entities.selectors.geometry import Cache, Randomize, SelectIf
from .....entities.selectors.tiles import (
    AdjacentTiles, CanAddUnit, PreviousTile, SortTilesByUtility
)
from .....entities.selectors.units import First
from .....entities.triggers import AmountIsGreaterThanZero
from .....entities.triggers import AmountIsGreaterThanZero, HasUnitFlag, TriggerAnd
from ....abilities.behaviours.lifecycle import TriggerAbilityDelayed
from ....abilities.behaviours.persistent_data import AddPersistentData
from ....abilities.behaviours.summon import Spawn
from ....abilities.behaviours.persistent_data import ClearPersistentData
from ....components import UnitFlagsComponent
from ....components import persistent_data

ABILITY_ID = "HaywireMineSteppable"

# Cles de config (indices d'`IdunBattle.Configuration.AbilityVariableType` / `AbilityConstantType`
# lus au decompile, noms confirmes contre le gameconfig de l'ability).
MIN_DMG_KEY = "minDmg"              # ConfigVar 0xc      | volet 1
MAX_DMG_KEY = "maxDmg"              # ConfigVar 0xd      |
HITS_KEY = "nrOfHits"               # ConfigConst 0x2f   |
PROFILE_KEY = "damageProfile"       # ConfigConst 0x2e   |
MIN_DMG_2_KEY = "minDmg_2"          # ConfigVar 0x36     | volet 2 (cible MECHANICAL)
MAX_DMG_2_KEY = "maxDmg_2"          # ConfigVar 0x37     |
HITS_2_KEY = "nrOfHits_2"           # ConfigConst 0x32   |
PROFILE_2_KEY = "damageProfile_2"   # ConfigConst 0x3f   |

STEPPABLE_TRAIT = UnitTrait.Steppable        # 0x1b = 27
MECHANICAL_TRAIT = UnitTrait.Mechanical      # 5

# `attackRangeType = Melee` dans le gameconfig de l'ability : la mine explose AU CONTACT.
IS_MELEE = True


def _config(state: State, owner_id: int) -> Optional[dict]:
    """Les six valeurs de config du behaviour, resolues sous l'`AbilityState` de MONTAGE de l'ability
    (mirror `AbilityConfiguration$$GetVariableForLevel` / `$$GetNumberConstant` /
    `$$GetStringConstant`). `None` si l'unite / son contexte / la config manquent -- l'appelant
    n'execute alors AUCUN arbre (le natif, lui, LEVE ; le port refuse en silence, residu du foyer
    `ability_var`)."""
    e = state.get_entity(int(owner_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None or getattr(sc, "ctx", None) is None:
        return None
    lvl, mult = triggered_ability_state(state, int(owner_id), ABILITY_ID)
    def _var(key):
        return ability_var(ABILITY_ID, key, lvl, multiplier_pct=mult)
    def _const(key):
        return ability_var(ABILITY_ID, key, is_constant=True)
    import gameconfig as GC
    consts = (GC.ability(ABILITY_ID) or {}).get("constants") or {}
    lo, hi = _var(MIN_DMG_KEY), _var(MAX_DMG_KEY)
    lo2, hi2 = _var(MIN_DMG_2_KEY), _var(MAX_DMG_2_KEY)
    if lo is None or hi is None:
        return None
    return {"min": int(lo), "max": int(hi),
            "hits": int(_const(HITS_KEY) or 1), "profile": consts.get(PROFILE_KEY),
            "min2": None if lo2 is None else int(lo2),
            "max2": None if hi2 is None else int(hi2),
            "hits2": int(_const(HITS_2_KEY) or 1), "profile2": consts.get(PROFILE_2_KEY)}


def haywire_mine_steppable_tree(cfg: dict, rng):
    """Arbre de `HaywireMineSteppableAbility$$CreateBehaviour` (MIRROR 1:1 du DECOMPILE) :

        If( HasTrait(Actor@sel+0x40, 5 = Mechanical),
            op_Addition(atk1, atk2),
            atk1 )

    `rng` = le PRNG que la factory pose dans le champ `+0x20` du noeud `RandomAmount` (cf.
    `entities/formulas.py::RandomAmount`) -- il est pris AU CONSTRUCTEUR, pas dans le contexte.
    `multi=False` : le selecteur de cible est le slot ACTOR, qui resout UNE entite (le
    `AttackBehaviour$$Execute` natif lit bien une LISTE, mais elle a alors un seul element)."""
    def _atk(lo, hi, profile, hits):
        return AttackWithAbilityDamage(
            Actor(), profile, RandomAmount(Const(int(lo)), Const(int(hi)), rng=rng),
            is_melee=IS_MELEE, hits=int(hits), source_ref=Owner(), multi=False,
            native_operation="ability")
    atk1 = _atk(cfg["min"], cfg["max"], cfg["profile"], cfg["hits"])
    if cfg["min2"] is None or cfg["max2"] is None or not cfg["profile2"]:
        return atk1                      # config du volet 2 absente -> l'arbre natif ne se batit pas
    atk2 = _atk(cfg["min2"], cfg["max2"], cfg["profile2"], cfg["hits2"])
    return If(HasTrait(Actor(), int(MECHANICAL_TRAIT)), op_add(atk1, atk2), atk1)


class HaywireMineSteppableAbility(TriggeredAbility):
    """`HaywireMineSteppableAbility` -- la mine explose sur l'ENNEMI qui vient de l'ECRASER.

    `fire_on_death = True` : l'owner EST le mourant (`get_OwnerIsTarget`), donc `alive == False` au
    moment ou le vecteur `On(1)` part -- exactement le regime que le natif dispense du gate de
    vivacite d'`IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` (`IsAtomic`),
    et le meme choix que `FinalJusticeAbility` / la famille death-nova."""
    event_id = int(EventTriggerType.PreUnitDeath)                       # `On(1)`
    fire_on_death = True
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.HaywireMineSteppable)   # 0x606 = 1542

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsTarget` : la MINE est l'unite qui meurt (`AbilityEntities@0x178`).
        dying = ev.dying_id if ev.dying_id is not None else ev.target_id
        if dying is None or int(dying) != int(self.owner_id):
            return False
        # `HasDeathReason(Owner@sel+0x30, 2 = DamageReason.Steppable, <Nullable VIDE>)` -- le canal
        # est `UnitComponent.death_source`, ecrit par `KillUnitOperation$$RecordDeathReason` AVANT
        # `On(1)`. Un `Nullable` VIDE cote ability = aucun filtre d'`AbilityOrEffect`.
        if not has_death_reason(state, int(self.owner_id), int(DamageReason.Steppable), None):
            return False
        actor = ev.actor_id if ev.actor_id is not None else ev.killer_id
        if actor is None or int(actor) == int(self.owner_id):
            return False
        ae = state.get_entity(int(actor))
        if ae is None:
            return False
        # `NOT HasTrait(Actor@sel+0x40, Steppable)` : une mine ecrasee par une AUTRE mine n'explose pas.
        if has_trait(_unit_trait_names(state, int(actor)), STEPPABLE_TRAIT):
            return False
        # `IsAlive(Actor@sel+0x40)` -- `UnitExtensions$$IsAlive` = vivant ET PV > 0.
        auc = ae.get_component(UnitComponent)
        if auc is None or not auc.alive:
            return False
        # `AreEnemies(Owner@sel+0x30, Actor@sel+0x40, 0)` : une mine n'explose pas sous un ALLIE.
        moc = (state.get_entity(int(self.owner_id)) or ae).get_component(OwnerComponent)
        aoc = ae.get_component(OwnerComponent)
        if moc is None or aoc is None or moc.team is None or aoc.team is None:
            return False
        return moc.team != aoc.team

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        cfg = _config(state, int(self.owner_id))
        if cfg is None:
            return None
        actor = ev.actor_id if ev.actor_id is not None else ev.killer_id
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `AbilityEntities` du vecteur `On(1)` : owner == caster == la MINE (`Owner@sel+0x30`,
        # qui retombe sur `ctx.caster`), target == le mourant == la mine (`OwnerIsTarget`),
        # actor == celui qui a marche dessus (`Actor@sel+0x40`).
        entities = entities_from_state(state, int(self.owner_id), int(self.owner_id),
                                       actor_id=int(actor))
        haywire_mine_steppable_tree(cfg, state.rng).execute(entities, ectx)
        # Le PROFIL par attaque est attribue PAR POSITION, et c'est exact : l'arbre natif est
        # `If(cond, atk1 + atk2, atk1)`, donc la 1re emission est TOUJOURS `atk1` (profil
        # `damageProfile`) et la seconde, quand elle existe, `atk2` (`damageProfile_2`). C'est ce que
        # la mesure live montre cote natif : `[18 Blast]` sur un ennemi ordinaire,
        # `[18 Blast, 16 Energy, 16 Energy]` sur un MECANIQUE (`nrOfHits_2 = 2`).
        profils = [cfg["profile"], cfg["profile2"]]
        hits = [{"target": p["target"], "total": p.get("total"), "attack": p.get("attack"),
                 "profile": profils[i] if i < len(profils) else None}
                for i, (n, p) in enumerate(
                    [(n, p) for n, p in ectx.emitted if n == "AttackWithAbilityDamage"])]
        if not hits:
            return None
        return {"ability": ABILITY_ID, "owner": int(self.owner_id), "stepper": int(actor),
                "profile": cfg["profile"], "hits": hits,
                "mechanical": has_trait(_unit_trait_names(state, int(actor)), MECHANICAL_TRAIT),
                "total": sum(int(h.get("total") or 0) for h in hits)}


# =====================================================================================================
# LA POSE (#462-r4b-r1-r1-r1-r1-c-r3-r1-r5) -- `HaywireMineAbility` (1531) + `HaywireMine_ResetAbility`
# =====================================================================================================
#
# `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HaywireMineAbility$$CreateTrigger`, noeud par
# noeud (`DSLFactory+0x78` = DSLBehaviors, `+0x80` = DSLFormulas, `+0x88` = DSLTriggers,
# `+0x90` = DSLSelectors ; `DSLSelectors+0x30` = `Owner`) :
#
#     ( On(4 = UnitAfterMove, ownerNeedsToBeAlive = 1) & get_OwnerIsActor & TriggeringAbilityIsNone )
#   | ( On(0x29 = UnitFinishedTurnNormally, ownerNeedsToBeAlive = 1) & get_OwnerIsActor
#       & AmountIsZero( GetPersistentData(AbilityOrEffect(self), Owner, <cle statique>) ) )
#
# `...$$CreateBehaviour(abilityState, triggerType)` :
#
#     tiles = Cache( If( AmountIsGreaterThanZero(PreviousTile(Owner)) & HasFlag(Owner, 0 = Moved),
#                        CanAddUnit(PreviousTile(Owner)),
#                        First(SortTilesByUtilityForSummon(
#                                  Randomize(CanAddUnit(AdjacentTiles(Owner))), 7, Owner), 1) ),
#                    1 )
#     pose  = Spawn(Owner, tiles, GetStringConstant(8 = unitToSpawn),
#                   SpawnUnitOptions.WithStatsFromConfig(config, abilityState, 0, 0))
#             & AddPersistentData(AbilityOrEffect(self), Owner, <cle statique>, DSLFormulas+0x20)
#
#     if (triggerType == 0x20 = Custom) return pose;                       # le re-declenchement differe
#     return If( AmountIsGreaterThanZero(Count(tiles)),
#                pose,
#                TriggerAbilityDelayed(Owner, 0x5fb = 1531, 3) );
#
# `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HaywireMine_ResetAbility` :
#     CreateTrigger   : On(0x28 = UnitFinishedTurn, ownerNeedsToBeAlive = 1) & get_OwnerIsActor
#     CreateBehaviour : triggerType == 0x20 (Custom) -> Nothing()
#                       sinon                        -> ClearPersistentData(AbilityOrEffect(self),
#                                                                           Owner, <cle statique>)
#
# L'ORDRE COMPTE, ET IL EST MESURE. `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` publie
# `On(0x28)` PUIS, si `!isTerminated`, `On(0x29)` -- donc le `Clear` du Reset tombe AVANT la lecture
# `AmountIsZero` de la 2e disjonction, qui est par consequent TOUJOURS vraie a la fin d'une
# activation normale. Ce n'est pas une deduction : le bras discriminant de
# `probe_462_r4b_r1_r1_r1_r1_c_r3_r1_r5_haywire_pose.py --step discriminant` LIBERE la tuile
# precedente (un ecraseur ennemi a PV bas meurt dessus) et le natif y REPOSE une mine au `finish` --
# deux mines dans le meme tour. Sans liberation, la sequence observee est :
#   tour AVEC deplacement : 1 mine sur `PreviousTile` a l'`On(4)`, RIEN au `finish` (les tuiles sont
#                           vides -> la branche `else` part sur `TriggerAbilityDelayed`, dont le
#                           re-declenchement `Custom` ne trouve pas plus de tuile) ;
#   tour SANS deplacement : RIEN au move, 1 mine ADJACENTE au `finish` (`HasFlag(Moved)` a ete purge
#                           par le `RemoveTurnFlags(new_activation=1)` du turn-start -> branche
#                           `else` du selecteur de tuiles).
#
# La CLE de donnee persistante est un litteral de chaine (`DAT_1833596e8`), le MEME dans les trois
# corps (pose / lecture / clear) -- non lisible statiquement (slot de metadata IL2CPP resolu au
# runtime). Le port lui donne un nom PROPRE : seule compte son UNICITE au sein du sac, et les trois
# sites du port la partagent par cette constante.

HAYWIRE_MINE_ABILITY = "HaywireMine"
HAYWIRE_MINE_ID = int(TriggeredAbilityType.HaywireMine)          # 0x5fb = 1531
#: `GetStringConstant(config, 8)` -- `AbilityConstantType.unitToSpawn` (l'enum du build ; `0` serait
#: `unitId`, que cette ability ne porte PAS -- le confondre rend un spawn silencieusement absent).
UNIT_TO_SPAWN_KEY = "unitToSpawn"
#: `SortTilesByUtilityForSummon(tiles, 7, Owner)` -- le litteral `7` du call-site
#: (`UtilityDefinition(7)`, le composite `Tile` deja porte par `engine/utilities/tile.py`).
SUMMON_UTILITY_TYPE = UtilityType.Tile
#: `TriggerAbilityDelayed(Owner, 0x5fb, 3)` -- le 4e argument est un `UnitSelectionType`, PAS un
#: delai (`TriggerAbilityDelayedBehaviour$$.ctor(state, entity, triggeredAbilityType,
#: unitSelectionType)`). Le port ne modelise pas ce filtre : son selecteur est `Owner`, deja resolu.
DELAYED_UNIT_SELECTION_TYPE = 3
#: La `dataKey` de `AddPersistentData`/`GetPersistentData`/`ClearPersistentData` (cf. le bloc
#: ci-dessus : litteral natif non lisible offline ; c'est son UNICITE qui est load-bearing).
POSE_DATA_KEY = "HaywireMine.posedThisTurn"


def haywire_mine_tiles(owner_sel=None):
    """Le SELECTEUR DE TUILES de `HaywireMineAbility$$CreateBehaviour`, arbre DSL 1:1 :

        Cache( If( AmountIsGreaterThanZero(PreviousTile(Owner)) & HasFlag(Owner, Moved),
                   CanAddUnit(PreviousTile(Owner)),
                   First(SortTilesByUtilityForSummon(Randomize(CanAddUnit(AdjacentTiles(Owner))),
                                                     7, Owner), 1) ),
               1 )

    Trois traits LUS qui ne se devinent pas :
      * la garde est une CONJONCTION -- « il existe une tuile precedente » ET « l'unite a bouge ce
        tour ». Le second membre est ce qui bascule sur la branche ADJACENTE au tour ou l'unite ne
        s'est pas deplacee (le flag `UnitFlag.Moved` est purge au turn-start) ;
      * `PreviousTile` apparait DEUX FOIS -- dans la garde (via `AmountIsGreaterThanZero`, donc
        AVANT `CanAddUnit`) et dans la branche `then` (via `CanAddUnit`, donc APRES). La garde ne
        teste donc PAS la libre-occupation : une tuile precedente OCCUPEE passe la garde et rend un
        ensemble VIDE, ce qui fait tomber le behaviour sur `TriggerAbilityDelayed` ;
      * `Randomize` est un MELANGE COMPLET (`PickRandomAmountSelector` a `amount = 0x7fffffff`),
        pas un tri : il CONSOMME `len(pool)` tirages avant le tri d'utilite, qui est stable.

    Le `Cache` est load-bearing : le MEME noeud alimente le `Spawn` **et** le `Count(tiles)` du
    `If` du behaviour. Sans memoisation, le `Count` re-evaluerait `CanAddUnit` APRES la pose, la
    tuile serait occupee, et le `If` prendrait la branche `TriggerAbilityDelayed` alors que le
    spawn vient d'avoir lieu."""
    owner = owner_sel if owner_sel is not None else Owner()
    prev = PreviousTile(owner)
    garde = TriggerAnd(AmountIsGreaterThanZero(CountF(prev)),   # `AmountIsGreaterThanZero(PreviousTile)`
                       HasUnitFlag(owner, UnitFlagsComponent.MOVED))   # `HasFlag(Owner, 0 = Moved)`
    # `First(<tri>, amount = 1, ignoreForcedTargets = 0)` -- le 3e argument natif est un AMOUNT
    # (`DSLSelectors$$First(entities, amount, ignoreForcedTargets)`, la surcharge int enveloppant
    # `amount` dans une formule constante avant de deleguer). A `amount == 1` il rend l'element de
    # TETE, ce que le noeud porte (index 0) rend aussi -- les deux lectures coincident ICI, et
    # seulement ici.
    # `allow_steppable=False` EXPLICITE (#462-...-r5-r3) : les DEUX `CanAddUnit` de
    # `...HaywireMineAbility$$CreateBehaviour` prennent la surcharge a DEUX arguments et lui passent
    # `<DSLTriggers+0x40>` -- releve a l'octet aux deux call-sites (`mov r8,[r8+0x40]`), la ou 123
    # des 147 call-sites du binaire passent `<+0x48>` = `op_LogicalNot(<+0x40>)`. `ShouldTrigger` y
    # est donc VRAI, et `allowSteppable = !vrai = FALSE`. C'est ce que la mesure live de cette
    # ability montrait deja : au tour ou la mine occupe `PreviousTile`, le natif ne repose RIEN.
    adjacentes = First(SortTilesByUtility(Randomize(CanAddUnit(AdjacentTiles(owner),
                                                               allow_steppable=False)),
                                          utility_type=SUMMON_UTILITY_TYPE, parent_sel=owner))
    return Cache(SelectIf(garde, CanAddUnit(prev, allow_steppable=False), adjacentes))


class _HaywireMinePlaceBase(TriggeredAbility):
    """Le CORPS COMMUN des trois entrees de pose -- il n'existe qu'UNE
    `HaywireMineAbility$$CreateBehaviour` cote natif, donc UN seul behaviour porte. Les sous-classes
    ne different que par leur `CreateTrigger` (les deux disjonctions) et par la branche du
    `triggerType` (`Custom` saute le `If` de repli)."""
    event_id = -1
    TRIGGERED_ABILITY_ID = HAYWIRE_MINE_ID
    #: `triggerType == 0x20` : la branche qui rend `pose` NU, sans le `If`/`TriggerAbilityDelayed`.
    is_custom_branch = False

    def _ability_state(self, state: State):
        """L'`AbilityState` sous lequel `HaywireMine` est montee sur l'owner -- c'est ce que le natif
        passe a `WithStatsFromConfig(config, abilityState, 0, 0)`, donc ce que la mine posee portera
        pour SA propre passive `HaywireMineSteppable`."""
        return triggered_ability_state(state, int(self.owner_id), HAYWIRE_MINE_ABILITY)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `AbilityEntities` du vecteur : l'owner est a la fois caster, target et actor
        # (`get_OwnerIsActor` du trigger, et le ctor natif de `On(4)`/`On(0x29)` pose `unit` aux
        # trois slots -- cf. `dispatch/turn.py` et `dispatch/move_death.py`).
        entities = entities_from_state(state, int(self.owner_id), int(self.owner_id),
                                       actor_id=int(self.owner_id))
        tiles = haywire_mine_tiles()                       # le `Cache` PARTAGE (cf. sa docstring)
        pose = op_and(
            Spawn(tiles, HAYWIRE_MINE_ABILITY, unit_id_constant=UNIT_TO_SPAWN_KEY,
                  ability_state=self._ability_state(state)),
            AddPersistentData(HAYWIRE_MINE_ID, Owner(), POSE_DATA_KEY, Const(1)))
        if self.is_custom_branch:
            arbre = pose                                   # `if (triggerType == 0x20) return pose;`
        else:
            arbre = If(AmountIsGreaterThanZero(CountF(tiles)), pose,
                       TriggerAbilityDelayed(Owner(), HAYWIRE_MINE_ID))
        arbre.execute(entities, ectx)
        poses = [p for n, p in ectx.emitted if n == "SpawnUnit"]
        return {"ability": HAYWIRE_MINE_ABILITY, "owner": int(self.owner_id),
                "mines": [p.get("unit") for p in poses],
                "tuiles": [p.get("tile") for p in poses],
                "differe": bool(not poses and not self.is_custom_branch)}


class HaywireMinePlaceOnMoveAbility(_HaywireMinePlaceBase):
    """1re disjonction : `On(4 = UnitAfterMove) & get_OwnerIsActor & TriggeringAbilityIsNone`.

    `TriggeringAbilityIsNone` (`IdunBattleLogic.Entities.DSLTriggers$$TriggeringAbilityIsNone`) porte
    sur le champ `AbilityEntities+0x98`, ecrit par l'operation qui a DECLENCHE le mouvement : un move
    joue par une feuille DSL (`MoveUnit` d'une autre ability, un `Displace`, un teleport) le
    renseigne, un deplacement JOUE PAR LE JOUEUR ne le renseigne pas. La mine n'est donc semee que
    sur un deplacement PROPRE de l'unite."""
    event_id = int(EventTriggerType.UnitAfterMove)             # `On(4)`

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        actor = ev.actor_id if ev.actor_id is not None else ev.target_id
        if actor is None or int(actor) != int(self.owner_id):   # `get_OwnerIsActor`
            return False
        return ev.triggering_ability is None                    # `TriggeringAbilityIsNone`


class HaywireMinePlaceOnTurnEndAbility(_HaywireMinePlaceBase):
    """2e disjonction : `On(0x29 = UnitFinishedTurnNormally) & get_OwnerIsActor
    & AmountIsZero(GetPersistentData(AbilityOrEffect(self), Owner, <cle>))`.

    Le gate persistant est ce qui empeche une SECONDE mine le tour ou l'unite a deja seme au
    deplacement -- sauf que `HaywireMine_ResetAbility` vide le sac sur `On(0x28)`, publie JUSTE
    AVANT par le meme `FinishUnitTurnOperation$$Execute`. Le gate est donc, en pratique, TOUJOURS
    ouvert ici : ce qui borne la pose a une par tour n'est pas lui, c'est le fait que la tuile
    precedente soit deja occupee par la mine du deplacement (mesure live, cf. le bloc en tete)."""
    event_id = int(EventTriggerType.UnitFinishedTurnNormally)   # `On(0x29)`

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        actor = ev.actor_id if ev.actor_id is not None else ev.target_id
        if actor is None or int(actor) != int(self.owner_id):   # `get_OwnerIsActor`
            return False
        e = state.get_entity(int(self.owner_id))
        v = persistent_data(e, (HAYWIRE_MINE_ID, POSE_DATA_KEY))
        return (0 if v is None else int(v)) == 0                # `AmountIsZero(GetPersistentData)`


class HaywireMineCustomAbility(_HaywireMinePlaceBase):
    """La branche `triggerType == 0x20 = Custom` -- atteinte UNIQUEMENT par le drain de
    `state.pending_triggered_abilities` (`dispatch/pending.py`), c'est-a-dire par le
    `TriggerAbilityDelayed(Owner, 1531, 3)` que le behaviour enfile quand `Count(tiles) == 0`.

    Elle n'a AUCUN `CreateTrigger` (le natif la selectionne par le `triggerType` passe a
    `TriggerTriggeredAbilityOperation$$TriggerAbility`), donc `matches` ne doit jamais etre
    consulte : cette classe n'entre pas dans `ABILITY_TRIGGERS`, seulement dans
    `CUSTOM_TRIGGERED_ABILITIES`."""
    is_custom_branch = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return False        # jamais atteinte par le bus d'evenements (cf. docstring)


class HaywireMineResetAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HaywireMine_ResetAbility` -- MEME
    `TriggeredAbilityType` (1531) que la pose, DEUXIEME classe native du meme id (le patron
    `DawnBlade_Heal` / `DawnBlade_Init`, deja rencontre en #317).

        CreateTrigger   : On(0x28 = UnitFinishedTurn) & get_OwnerIsActor
        CreateBehaviour : triggerType == 0x20 -> Nothing()
                          sinon               -> ClearPersistentData(AbilityOrEffect(self), Owner,
                                                                     <cle>)

    Elle RE-ARME la pose de fin de tour d'un tour a l'autre. La preuve qu'elle est bien MONTEE est
    live : au tour 2, l'unite qui n'a pas bouge pose une mine a son `finish`, ce qui exige que la
    donnee posee au tour 1 ait ete effacee entre-temps -- et c'est le seul effaceur du binaire pour
    cette cle. (`HaywireMine_Reset` n'a PAS d'entree propre dans `TriggeredAbilityType`, d'ou
    l'inscription sous le meme nom de kit que la pose.)

    La branche `Nothing()` du `Custom` n'a pas de porteur : le `TriggerAbilityDelayed` du binaire ne
    vise que `0x5fb`, et le drain n'appelle QUE les classes de `CUSTOM_TRIGGERED_ABILITIES` -- y
    inscrire un no-op serait du bruit. RESIDU NOMME."""
    event_id = int(EventTriggerType.UnitFinishedTurn)           # `On(0x28)`
    TRIGGERED_ABILITY_ID = HAYWIRE_MINE_ID

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        actor = ev.actor_id if ev.actor_id is not None else ev.target_id
        return actor is not None and int(actor) == int(self.owner_id)    # `get_OwnerIsActor`

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, int(self.owner_id), int(self.owner_id),
                                       actor_id=int(self.owner_id))
        ClearPersistentData(HAYWIRE_MINE_ID, Owner(), POSE_DATA_KEY).execute(entities, ectx)
        return {"ability": "HaywireMine_Reset", "owner": int(self.owner_id)}
