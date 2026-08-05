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
| (On(0x29) & OwnerIsActor & AmountIsZero(GetPersistentData(...)))`). CE passif-la n'est PAS porte
(residu nomme en fin de module) : la mine arrive dans l'etat offline par la CAPTURE live.

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

RESIDUS NOMMES :
  * `HaywireMineAbility` (1531, la POSE de la mine par Cyrus) n'est pas portee -- elle exige
    `Spawn` + `GetPersistentData`/`AddPersistentData` + `TriggerAbilityDelayed`, hors perimetre de
    cette tranche. Consequence : le port ne CREE jamais de mine ; il ne sait que la faire exploser
    quand la capture live en pose une.
  * `HaywireMine_ResetAbility` (le re-armement) idem.
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
from .....entities.behaviours import If, op_add
from .....entities.damage_reason import DamageReason
from .....entities.formulas import RandomAmount
from .....entities.selectors import Actor, Owner
from .....entities.traits.unit_trait import UnitTrait, has_trait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import HasTrait
from ....abilities.behaviours import AttackWithAbilityDamage, entities_from_state
from ....components import OwnerComponent, StatsComponent, UnitComponent
from ....state import State
from ..base import (TriggeredAbility, TriggerEvent, triggered_ability_state,
                    _unit_trait_names)
from .reactivate_overwatch import has_death_reason

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
    from .....entities.effects.magnitude import ability_var
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
