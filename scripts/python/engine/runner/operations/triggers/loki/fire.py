"""Cluster FEU — abilities natives partageant l'effet `Fire` (type 5) et le gate d'immunite feu :
- `Abilities.Active.Loki.EnvFireTileAbility` (IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour) : DoT de tuile en feu.
- `Abilities.Damage.Loki.OnFireDamageAbility` (IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateBehaviour) : pose du FEU on-hit.
- `Abilities.Active.Loki.FireOfAbsolutionAbility` (IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateBehaviour) : splash Flame + ignite adjacents (adeptRetributor).

Regroupees ICI (et pas separees par sous-namespace Active/Damage) car elles partagent les constantes `FIRE_*`
et le helper `_is_immune_to_fire` (evite un module « fire-commun » invente). Cf. `loki/__init__.py`."""
from __future__ import annotations

from typing import Optional

import gameconfig as GC

from ....state import State
from ....components import UnitComponent
from ....abilities.behaviours.combat import AttackWithAbilityDamage, AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, SetOnFire
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.effects.magnitude import ability_var
from .....entities.stats import StatType, StatPart
from .....entities.unit_selection_type import UnitSelectionType
from .....entities.traits.unit_trait import UnitTrait, has_any_trait
from .....entities.damage_trait import DamageTrait
from .....entities.effect_type import EffectType
from .....entities.formulas import PercentageOf, StatAmount
from .....entities.selectors.accessors import Target, TargetTile
from .....entities.selectors.tiles import AdjacentTiles, Caster
from .....entities.selectors.units import AdjacentUnits, Alive, Sub, Tiles
from .....entities.behaviours import Foreach, Maybe, Inform, op_and
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TileEffectTrigger, TriggeredAbility, TriggerEvent, _unit_trait_names
# #270-r4 : 	ag de DSLBehaviors.Inform, type DECLARE lu dans rida/methods.tsv.
from .....streams.tag_key import TagKey

# --- Fire (tile-effect DoT, EnvFireTileAbility, Active.Loki) ---------------------------------------
FIRE_TILE = int(EffectType.Fire)  # 5 — effet de TUILE (posé par attaque Flame, `OnFireDamageAbility`IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateBehaviour).
FIRE_DMG_PCT_KEY = "fireDmgPct"  # globalValues=20 (`ConfigConst 0x12`) : % de la PV INITIALE (max) infligé/tour.
# Immunité feu = `UnitsWithoutTraits([0x1b=27=Steppable, 0x19=25=Immune])` (IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour) : le DoT EXCLUT ces
#   deux traits (enum TRAIT, ≠ enum EFFECT où 25/27=Taunted_*). Mapping id<->nom centralisé dans
#   `entities.traits.UnitTrait` (#146) ; `ctx.traits` = NOMS gameconfig (unit_context.py:191) → gate par nom.
FIRE_IMMUNE_TRAITS = (UnitTrait.Steppable, UnitTrait.Immune)
FIRE_PROFILE = "Flame"  # profil de degat du DoT feu (perçage = Flame.PiercingRatio=25 ; RE + live-valide net 477)

# --- FireOfAbsolution (adeptRetributor «Vindicta», passive, Active.Loki) ---------------------------
FIRE_OF_ABSOLUTION_ID = "FireOfAbsolution"
#: `AbilityConstantType.chance` (0x2a = 42) -- la cle que `GetNumberConstant` lit dans la CONFIG,
#: et non la valeur. Le port l'avait figee a `30` (#951) : juste au moment ou elle a ete ecrite,
#: mais c'etait un HARDCODE silencieux -- il aurait survecu a un rebalancage du gameconfig sans
#: qu'aucun test ne rougisse, exactement le mode de panne que la doctrine nomme (« inventer/coder
#: en dur au lieu de mirrorer la source reelle »). Les DEUX autres grandeurs du meme
#: `CreateBehaviour` etaient deja lues de la config (`dmg` par `min_key`/`max_key`, `nrOfHits` par
#: le `hits_key` par defaut d'`AttackWithAttackDamage`) : c'etait la seule des trois a ne pas l'etre.
FIRE_OF_ABSOLUTION_CHANCE_KEY = AbilityConstantType.chance.name        # 0x2a = 42


def fire_of_absolution_ignite_chance() -> int:
    """`GetNumberConstant(AbilityConstantType.chance)` du gameconfig. `0` si la constante manque --
    le `Maybe` natif tirerait alors contre une probabilite nulle, donc jamais de feu ; c'est le
    comportement du natif avec une config absente, pas une valeur de repli inventee."""
    v = ability_var(FIRE_OF_ABSOLUTION_ID, FIRE_OF_ABSOLUTION_CHANCE_KEY, is_constant=True)
    return int(v or 0)


def _is_immune_to_fire(state: State, unit_id: int) -> bool:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour : `Foreach(UnitsWithoutTraits([0x1b=27=Steppable,
    0x19=25=Immune]) & Units(EntitiesWithAnyEffect(5)), ...)`. Le DoT feu EXCLUT donc les unités portant
    `Steppable` (tokens marchables : decoys/mines) OU `Immune`. Résolution enum UnitTrait dump.cs (gqfc5mff6c)."""
    names = _unit_trait_names(state, unit_id)
    return has_any_trait(names, FIRE_IMMUNE_TRAITS)


def env_fire_tile_tree(pct: int, profile: str):
    """Feuille de `IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour` (MIRROR 1:1 du DECOMPILE) :
        Foreach( UnitsWithoutTraits([Steppable=0x1b, Immune=0x19]) & Units(EntitiesWithAnyEffect(Fire=5)),
                 AttackWithAbilityDamage(
                     targets = Tiles(@0x180),
                     amount  = PercentageOf( StatAmount(@0x180, Health=5, Max=2), ConfigConst(0x12=fireDmgPct) ),
                     Direct(Nullable(3)),
                     source  = AbilityOrEffect(Fire=5) ) )
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` construit `IdunBattle.Entities.Behaviours.
    AbilityDamageBehaviour$$.ctor` + `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor` (LU) : c'est la
    famille ABILITY (`IdunBattle.Operations.AbilityDamageOperation` -> `IdunBattle.Core.Services.
    DamagePrediction$$CalculateAbilityDamage`), DISTINCTE de `IdunBattleLogic.Entities.DSLFactory$$
    AttackWithAttackDamage` (famille ATTACK, Psyker/ThunderousAssault) — et distincte AUSSI de la voie
    `IdunBattle.Operations.DirectDamageOperation` / `IdunBattle.Core.Services.DamagePrediction$$
    CalculateDirectDamage`, que ce DoT n'emprunte PAS.
    Port : la FEUILLE `AttackWithAbilityDamage(Target(), "Flame", PercentageOf(Const(pct), StatAmount(Target(),
    Health, Maximum)), native_operation="ability")`. Le `Foreach(<selecteur>)` natif (occupants NON-immunes sur
    tuile en feu) est resolu EN AMONT par le dispatch runner (`TileEffectTrigger` par tuile en feu =
    `EntitiesWithAnyEffect(5)`, `_unit_on_tile` = l'occupant, `_is_immune_to_fire` = le gate
    `UnitsWithoutTraits([Steppable, Immune])`) — DSL-ification du selecteur deferree (comme le selecteur
    Psyker, #216). La cible RESOLUE (l'occupant) passe via `Target()` ; sa PV MAX via `StatAmount(Target(),
    Health, Maximum)`. La feuille calcule `base = round_fix64(pct% * PVmax)` (Fix64 = mirror natif
    `PercentageOf.Calculate`) puis route via `execute_ability_attack(base, base, ..., is_attack_damage_op=False)`.

    CORRESPONDANCE DES SELECTEURS (`AttackBehaviour$$Execute` : +0x50 = CASTER resolu en UNE entite,
    +0x58 = la LISTE des cibles) : la factory recoit `(Tiles(@0x180), @0x180)` -> CASTER = la TUILE de
    l'occupant, CIBLE = l'occupant. `source` non passe cote port -> `entities.caster` = `owner_id` = la
    tuile : MEME entite que le natif (attribution de mort incluse).

    `is_melee=None` (et non True) : l'`AbilityOrEffect` du coup est l'EFFET `Fire(5)`, pas une ability a
    `attackRangeType` -> `IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType` rend 0 (absent),
    donc `IsMeleeAttack` ET `IsRangedAttack` sont FAUX (cf. la table de verite de `hits_channel_is_melee`).
    Les malus DEFENSEUR gates `IsMeleeAttack` (Terrifying_ExtraDefense) restent donc inertes, comme le natif.
    Le percage est inchange (`profile_pierce(ctx=None, ...)` ignore `ranged` : la tuile n'a pas d'ExtraPierce).

    `pct`/`profile` passes par l'appelant (`GC.global_value(fireDmgPct)` / `FIRE_PROFILE`) pour eviter
    tout couplage d'import."""
    amount = PercentageOf(Const(pct), StatAmount(Target(), int(StatType.HEALTH), int(StatPart.MAXIMUM)))
    return AttackWithAbilityDamage(Target(), profile, amount, is_melee=None, hits=1,
                                   native_operation="ability")


class FireTileDoT(TileEffectTrigger):
    """`EnvFireTileAbility` (IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateTrigger = `On(0x14) & Count(EntitiesWithAnyEffect(5))>0` ;
    IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour) — DoT de la tuile en feu (`FireEffect` type 5, IdunBattle.Entities.Effects.FireEffect$$.ctor). Au tick de
    tour (`On(0x14)`), l'unite qui DEMARRE son tour sur une tuile en feu subit `PercentageOf(StatAmount(
    Health, variant=2=Maximum), fireDmgPct=20)` = 20% de sa PV MAX, porte en degat DIRECT.

    behaviour = arbre DSL `env_fire_tile_tree()` (mirror 1:1 de la feuille de IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour ;
    factory `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` = DIRECT, DISTINCTE de `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` =
    Psyker/ThunderousAssault). i2 `Keywords/EffectFire` : « Units starting their turn on a Fire hex take 20%
    of their initial Health » = la BASE (20% PV max), PAS le net. Le natif route la base par le PERCAGE/ARMURE
    (CONFIRME LIVE 2026-07-12 : blackHaarken net 477 = base 1908 x PiercingRatio(Flame) 25%, l'armure absorbant
    le non-perce). `Direct(3)` = pas de crit/block/spread. fireDmgPct tire de globalValues (ConfigConst 0x12,
    NON hardcode). Decay via on_turn_end. Mort routee par `_fire_death_if_killed` (source = la tuile).

    DUREE (#98, corrige) : `DefaultAmountOfRounds(5)` = 2 ROUNDS ; le natif stocke
    `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns(2) = `count(joueurs du turnOrder, PlayerType != 2) x 2` TURNS.
    Ce count vaut **2** dans un duel standard (BC : Players 11/12/13 = PlayerType 0/1/2,
    `Player.TurnOrder=[11,12,13]`) -> le feu dure **4 tours**, et l'ancre `Effect_RemainingTurns=4` est
    la valeur NORMALE, pas un cas d'arene. L'ancienne lecture « count = 1, prouve par test_effect_stun_
    live » etait un ARTEFACT DE MESURE (lecture POST-tick en 1v1 strict, cf. `convert_rounds_to_turns`).

    GATE IMMUNITE feu (`UnitsWithoutTraits([0x1b=27=Steppable, 0x19=25=Immune])` IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour) PORTE : le DoT
    EXCLUT les occupants portant `Steppable` (tokens marchables) ou `Immune` (cf. `_is_immune_to_fire`) —
    resolu EN AMONT (le `Foreach(<selecteur>)` reste imperatif, DSL-ification deferree comme Psyker, #216)."""
    effect_type = FIRE_TILE
    event_ids = (EventTriggerType.TurnStart_EnvironmentEffects,)

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        return self._unit_on_tile(state) is not None

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        uid = self._unit_on_tile(state)
        if uid is None:
            return None
        if _is_immune_to_fire(state, uid):               # gate UnitsWithoutTraits([Steppable=27, Immune=25]) IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour
            return None
        pct = GC.global_value(FIRE_DMG_PCT_KEY)           # fireDmgPct=20 (globalValues == ConfigConst 0x12, non hardcode)
        if not pct:
            return None
        # behaviour = arbre DSL `env_fire_tile_tree()` (mirror 1:1 de la feuille IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour) :
        # AttackWithAbilityDamage(Tiles, PercentageOf(StatAmount(Health,Max), fireDmgPct), Direct(3), source=Fire).
        # La feuille route la famille ABILITY (`AbilityDamageOperation`) : percage/armure + mods DEFENSEUR +
        # block + bouclier + etage LIMITES mode 2 (member-cap / Resilient), AUCUN crit. La source
        # (entities.caster = la tuile owner_id) sert a l'attribution de mort.
        ectx = ExecutionContext(state=state, rng=state.rng)
        env_fire_tile_tree(int(pct), FIRE_PROFILE).execute(
            entities_from_state(state, self.owner_id, uid), ectx)
        hit = next((p for n, p in ectx.emitted if n == "AttackWithAbilityDamage"), None)
        atk = (hit or {}).get("attack")
        if not atk or not atk.get("total"):              # dmg <= 0 -> no-op comme l'ancien corps
            return None
        return {"tile_effect": "Fire", "tile": self.owner_id, "unit": uid, "dot": atk.get("total"),
                "hp_before": atk.get("hp_before"), "hp_after": atk.get("hp_after"), "on_event": ev.event_id}


# --- OnFireDamage (Damage.Loki) : pose du FEU on-hit ----------------------------------------------
def on_fire_damage_tree(fire_effect_type: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateBehaviour` (Damage.Loki — MIRROR 1:1 du DECOMPILE) :
        AddEffect( effectType = 5 (FireEffect),
                   source     = AbilityStateReference (caster),
                   target     = Tiles(target@0x178) )                                     # TILE-domain
    = un noeud DSL UNIQUE `AddEffect` avec selecteur TILE-DOMAIN `Tiles(Target())` (mirror `IdunBattleLogic.Entities.DSLSelectors$$Tiles -> `UnitsMainTilesSelector` = la MainTile occupee de la cible). La feuille `AddEffect`
    (generalisee tile-domain) convertit la position en id de tuile et route vers `AddEffectOperation.execute(
    target=tile_id, FIRE_TILE, "Fire")` -- MEME Operation/args que l'ancien imperatif -> bit-exact BY
    CONSTRUCTION (meme mutation, meme gate `already-present` d'AddEffect). Le gate de DECLENCHEMENT
    (`DamageProfileHasTrait(OnFire)` + `NOT TriggeringEffectIs(5)`, IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateTrigger) reste UPSTREAM
    (hors CreateBehaviour) dans `_on_fire_damage_ability`. RNG-free (AddEffect inconditionnel).
    `fire_effect_type` = passe par l'appelant (constante `FIRE_TILE`) pour eviter tout couplage d'import."""
    # #98 : le decompile IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateBehaviour appelle la surcharge a 4 args `AddEffect(factory, 5, stateRef,
    # Tiles(target))` -- AUCUN noeud duree -> duree PAR DEFAUT (`DefaultAmountOfRounds(5) = 2 rounds`,
    # converti par `AddEffectOperation`). Le port passait le defaut positionnel `duration_rounds=1`,
    # qui ECRASAIT la duree par defaut (feu a 1 tour) et divergeait de l'AUTRE chemin de pose du MEME
    # effet (`SetOnFire` de FireOfAbsolution, qui n'override rien). Corrige : `duration_rounds=None`.
    # `source_from_target=True` : le selecteur SOURCE de cette surcharge est NUL ->
    # `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` retombe sur la CIBLE, donc la source
    # du FEU est la TUILE et non le caster. GROUND TRUTH live du JUMEAU (meme surcharge, memes arguments)
    # : `FleshMetalGuns_TileEffectAbility` pose DespoiledGround avec `source` = l'id de la tuile
    # (#85, `probe_85_despoiled_ground.py`). Le port passait encore le caster -- residu ferme ici.
    return AddEffect(fire_effect_type, "Fire", Tiles(Target()), duration_rounds=None,
                     source_from_target=True)


class OnFireDamageAbility(TriggeredAbility):
    """`OnFireDamageAbility` (TriggeredAbilityType 1016, `Abilities.Damage.Loki`) — pose du FEU on-hit,
    branchee sur le BUS `On(DamageDealt = 0x10)`.

        IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateTrigger
            On(0x10, 1) & DamageProfileHasTrait(1 = OnFire) & !TriggeringEffectIs(5)
        IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateBehaviour
            AddEffect(5 = FireEffect, AbilityStateReference, Tiles(target@0x178))   # INCONDITIONNEL

    ABILITY GLOBALE (`owner_is_global`) : le `CreateTrigger` ne porte AUCUN predicat d'owner -- il ne
    teste que le PROFIL du coup, donc le canal vaut pour n'importe quel attaquant. Inscription UNIQUE
    (`dispatch/registry.py::GLOBAL_TRIGGERS`), cf. `collect_global_triggers`.

    VECTEUR (de-fork) : ce canal etait appele IMPERATIVEMENT depuis `after_hit_normal_attack` et
    `execute_ability_attack`, c.-a-d. APRES la resolution complete de l'attaque. Il est desormais
    consommateur du bus `On(0x10)`, emis par le chokepoint `AttackDamageOperation._apply_damage_pipeline`
    en mirror d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` -- donc AVANT le traitement de la
    mort (`VerifyDeaths` -> `IdunBattle.Operations.KillUnitOperation$$Execute`). Cette place n'est pas
    cosmetique : elle est ARBITREE LIVE sur le jumeau Toxic (`probe_o10_rng_order.py`, 6 confrontations,
    3 seeds -- ordre BUS 6/6 d'accord avec le natif, ordre imperatif 3/6).

    JUMEAU : `OnToxicDamageAbility` (1203, `on_toxic_damage.py`) partage le vecteur, la forme du gate de
    profil et la feuille de pose, mais son behaviour est CONDITIONNEL (`If(IsFirstHitInSeries() &
    Maybe(chance), AddEffect(1244))`) -- cf. `case-1203-on-toxic-damage.md` §1 pour le diff complet.

    SOURCE de l'effet pose = la TUILE, pas le caster : la surcharge `AddEffect` a 5 arguments passe un
    selecteur SOURCE **NUL**, et `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` retombe
    alors sur la CIBLE. GROUND TRUTH live du jumeau DespoiledGround (#85, `probe_85_despoiled_ground.py`
    runners 365/8514 : `source` = l'id de la TUILE, jamais celui du caster) -- meme surcharge, memes
    arguments. Porte ici par `source_from_target=True` (le port passait le caster).

    ANTI-BOUCLE : le `!TriggeringEffectIs(5)` du trigger est desormais PORTE (`ev.triggering_effect`),
    et `AddEffectOperation` no-ope de toute facon si la tuile brule deja."""
    event_id = int(EventTriggerType.DamageDealt)         # 0x10 = 16
    owner_is_global = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if not ev.profile or state.effects is None or getattr(state, "board", None) is None:
            return False
        traits = (GC.damage_profile(ev.profile) or {}).get("Traits") or []
        if DamageTrait.OnFire.name not in traits:        # DamageProfileHasTrait(DamageTrait.OnFire = 1)
            return False
        return ev.triggering_effect != FIRE_TILE          # !TriggeringEffectIs(5)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # behaviour = arbre DSL `on_fire_damage_tree()` (mirror 1:1 de `$$CreateBehaviour`) :
        # AddEffect(5 = Fire, Tiles(Target())). `ev.actor_id` = la SOURCE du degat (caster == actor dans
        # l'`AbilityEntities` que construit `ApplyDamageOperation`), `ev.target_id` = la VICTIME.
        ectx = ExecutionContext(state=state, rng=state.rng)
        on_fire_damage_tree(FIRE_TILE).execute(
            entities_from_state(state, ev.actor_id, ev.target_id), ectx)
        placed = [p["target"] for n, p in ectx.emitted if n == "AddEffect" and p.get("placed")]
        if not placed:                                   # tuile deja en feu -> no-op (gate already-present)
            return None
        return {"tile_effect": "Fire", "placed_on_tile": placed[0], "by": ev.actor_id,
                "on": ev.target_id, "placement": "OnFireDamage"}


def fire_of_absolution_tree(ignite_chance: int, fire_effect_type: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateBehaviour` (adeptRetributor «Vindicta», passif
    `Active.Loki` — MIRROR 1:1 du DECOMPILE) :
        op_BitwiseAnd( op_BitwiseAnd(
            Inform(0xb3, EntityId(target)),                                                    # [1] message
            AttackWithAttackDamage(caster@0x160, AdjacentUnits(target@0x178,0,3) − caster − target,
                                   Direct(dmg = GetVariableForLevel 0xb), Flame,
                                   nrOfHits = GetNumberConstant(0x2f)=3) ),                     # [2] splash
            Maybe( SetOnFire, AdjacentTiles(target), chance = GetNumberConstant(0x2a)=30 ) )    # [3] ignite
    Port (`op_and`/`Foreach`/`Maybe`) :
      [1] `Inform(int(TagKey.Target_Id))` = message natif (notif listeners) -> NO-OP dans le runner (pas de bus de messages ;
          l'ancien port ne le modelisait pas et etait live-valide). Present pour le MIRROR STRUCTUREL.
      [2] splash = `AttackWithAttackDamage(Alive(Sub(Sub(AdjacentUnits(TargetTile()),Caster()),Target())),
          "FireOfAbsolution","Flame", ranged, min_key=max_key="dmg", multi=True)`. `Direct(dmg)` = min==max
          (la meme cle config `dmg` en borne min ET max -> valeur FIXE, mirror `Direct(GetVariableForLevel
          0xb)`). Selecteur = FRIENDLY-FIRE : `AdjacentUnits(target) − caster − target` BRUT, AUCUN wrapper
          `Enemies` -> allies du caster adjacents INCLUS (#213 ; `Alive` mirror `Units`=unites DEBOUT).
      [3] ignite = `Foreach(AdjacentTiles(Target()), Maybe(chance, SetOnFire(Fire)))` = le `Maybe(child,
          selecteur, chance)` natif dans sa variante FOREACH-Maybe (1 `next_bool(30)` par tuile adjacente,
          cf. convention documentee du noeud `Maybe`) : pour chaque voisine de la cible, tirage puis pose du
          FEU (`SetOnFire` -> `AddEffectOperation` sur la TUILE). `AdjacentTiles(Target())` = `board.neighbours(
          tuile-cible)` (MEME ordre que l'ancien imperatif -> MEME conso `state.rng`).
    Ordre `op_and` gauche->droite = Inform -> splash -> ignite (== l'ancien imperatif) ; effets PURS ->
    pas de court-circuit (les trois volets s'executent). PAS d'`AtomicGroup` (natif = `CreateBehaviour` plain,
    PAS `ExecuteAtomic`). Bit-exact BY CONSTRUCTION vs l'ancien corps imperatif (memes Operations/args, meme
    ordre, meme `state.rng`). `ignite_chance`/`fire_effect_type` = passes par l'appelant (constantes
    `fire_of_absolution_ignite_chance()`/`FIRE_TILE`) pour eviter tout couplage d'import.
    ⚠ GAP RNG (flagge, cf. `_fire_of_absolution_after_attack`) : timing du passif vs coups primaires +
    reproductibilite du feu sur hex VIDE (stochastique)."""
    tgt = Target()
    # splash : AdjacentUnits(target) − caster − target (FRIENDLY-FIRE, mirror des 2 op_Subtraction natifs) ;
    # Direct(dmg) = borne min==max via min_key=max_key="dmg" ; multi=True = selecteur -> N cibles (OrderBy id).
    # #951 : `selection_type` = le 4e argument NATIF d'`AdjacentUnits(origin, unique: false,
    # selectionType: 3 = OnlyAliveAndTargetable)`, LU aux octets (`xor r8d,r8d` = unique false,
    # `mov r9d,3`). Le port l'AVALAIT et compensait par un wrapper `Alive(...)` : le volet ALIVE
    # etait donc porte, le volet TARGETABLE non -- une unite adjacente en DEEP STRIKE
    # (`UnitFlag.Untargetable`) etait touchee par le port et pas par le natif. Le wrapper est
    # retire parce qu'il ferait DOUBLE emploi : `_selection_ok(u, 3, ctx)` delegue au foyer
    # `matches_unit_selection_type`, dont la branche `OnlyAliveAndTargetable` est
    # `IsAlive && !HasFlag(Untargetable)` -- le meme predicat, plus un.
    splash = AttackWithAttackDamage(
        Sub(Sub(AdjacentUnits(TargetTile(),
                              selection_type=int(UnitSelectionType.OnlyAliveAndTargetable)),
                Caster()), Target()),
        "FireOfAbsolution", "Flame", is_melee=False, min_key="dmg", max_key="dmg", multi=True)
    # ignite : Maybe(SetOnFire, AdjacentTiles(target), 30) -> Foreach-Maybe (1 next_bool/tuile, ordre board).
    ignite = Foreach(AdjacentTiles(tgt), Maybe(ignite_chance, SetOnFire(fire_effect_type, "Fire")))
    return op_and(op_and(Inform(int(TagKey.Target_Id)), splash), ignite)


def _fire_of_absolution_after_attack(state: State, attacker_id: int, target_id: int,
                                     ranged: bool) -> list[dict]:
    """Passif `FireOfAbsolution` (adeptRetributor «Vindicta») — `IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateBehaviour. i2 : « When performing a ranged attack, also deals 3x Flame Damage to all units adjacent to
    the target. Has a 30% chance of setting each adjacent hex on Fire as well. »

    Behaviour natif (`&` = op_BitwiseAnd, gauche->droite) :
        Inform(0xb3, target)
      & AttackWithAttackDamage(caster, targets = AdjacentUnits(target, kind=3) − caster − target,
                               Direct(dmg = GetVariableForLevel 0xb), Flame, nrOfHits = GetNumberConstant 0x2f = 3)
      & Maybe(SetOnFire, AdjacentTiles(target), chance = GetNumberConstant 0x2a = 30)

    `AdjacentUnits(target, unique: false, 3) − caster − target` = TOUTES les unités adjacentes à la CIBLE,
    hors caster/cible, AUCUN filtre d'équipe (FRIENDLY-FIRE ; porté par le SÉLECTEUR DSL
    `Sub(Sub(AdjacentUnits(TargetTile(), selection_type=3), Caster()), Target())`, PAS un helper
    impératif). ⚠ le `3` est le `UnitSelectionType` (`OnlyAliveAndTargetable`), PAS un masque d'équipe
    (prémisse « kind=3 → ennemis » RÉFUTÉE, cf. Stikkbomb #213 :
    `AdjacentUnits` BRUT sans wrapper `Enemies(...)`) → alliés du caster adjacents à la cible TOUCHÉS, concordant
    avec l'i2 ci-dessus (« all units adjacent to the target »). `Direct(dmg)` = valeur FIXE (pas
    de spread ; min==max) routée par perçage/armure/mods + crit/block du pipeline d'attaque (≠ le DoT de tuile,
    tick sans contexte-attaquant). Chaque coup splash (Flame=OnFire) POSE du feu sur la tuile de la cible splash
    (via `execute_ability_attack`, #136). Le `Maybe` pose du feu même sur un hex VIDE (30%/hex).

    Se déclenche sur TOUTE attaque RANGED de l'unité (arme normale 4x Flame OU actif ArmoriumCherub) → appelé
    depuis `after_hit_normal_attack` (ranged) ET `ArmoriumCherubAbility.execute_behaviour`.

    ⚠ GAP RNG (flaggé, à valider live — cf. #136) : le TIMING exact du passif vs les coups de l'attaque
    primaire (porté post-attaque). Le feu sur hex VIDE (stochastique) n'est donc PAS reproductible
    bit-exact ; splash + feu sur adjacents OCCUPÉS = déterministe.

    ⚠ CORRECTION #951 -- « pas de `CreateTrigger` distinct dumpé pour ce passif » ÉTAIT FAUX, et
    cette phrase a survécu telle quelle jusqu'ici. Le trigger EXISTE et il est nommé :

        IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateTrigger
            On(EventTriggerType.AttackInAtomicGroup = 0x4a, ownerNeedsToBeAlive: true)
            & get_OwnerIsActor
            & IsRangedAttack()                            # surcharge SANS argument (0 arité)

    Les TROIS conjoints sont portés, mais par le VECTEUR et non par une entrée d'`ABILITY_TRIGGERS` :
    `dispatch/ability.py::evaluate_abilities_for_event` route ce passif sur
    `int(event) == EventTriggerType.AttackInAtomicGroup`, `dispatch/attack.py` l'appelle sur
    l'attaque normale, et le gate `ranged` + l'appartenance du passif au kit de l'attaquant tiennent
    lieu d'`IsRangedAttack()` et de `get_OwnerIsActor`. Ce qui reste NON porté est le seul
    `ownerNeedsToBeAlive: true` — inobservable sur ce vecteur, l'attaquant étant vivant par
    construction d'une attaque qu'il vient de porter.

    Conséquence de méthode : l'audit `kit-coverage.md` compte `FireOfAbsolution` comme MANQUANT
    pour `adeptRetributor` parce qu'il lit les REGISTRES, et que ce passif n'y a pas d'entrée.
    C'est un FAUX MANQUANT — résidu #951-r2."""
    if not ranged or state.board is None or state.effects is None or state.rng is None:
        return []
    e = state.get_entity(attacker_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or "FireOfAbsolution" not in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
        return []
    # behaviour = arbre DSL `fire_of_absolution_tree()` (mirror 1:1 de IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateBehaviour) :
    # Inform(int(TagKey.Target_Id)) & splash(AttackWithAttackDamage multi, Direct(dmg)) & Foreach(AdjacentTiles, Maybe(30,
    # SetOnFire)). Les feuilles emettent les MEMES Operations que l'ancien corps imperatif hybride
    # (`execute_ability_attack` par cible splash + `AddEffectOperation` sur les tuiles ignitees) -> meme
    # mutation, meme ordre (splash PUIS ignite), meme `state.rng` = bit-exact BY CONSTRUCTION. Le gate ci-dessus
    # (ranged/board/effects/rng + ownership du passif) reste la CONDITION DE DECLENCHEMENT (hors CreateBehaviour,
    # upstream de l'arbre). Direct(dmg) : `dmg` = GetVariableForLevel(0xb) scale rarete, min==max (min_key=
    # max_key="dmg" dans la feuille) ; hits=3, pierce/armure + crit/block du pipeline d'attaque ; feu pose #136.
    ectx = ExecutionContext(state=state, rng=state.rng)
    fire_of_absolution_tree(fire_of_absolution_ignite_chance(), FIRE_TILE).execute(
        entities_from_state(state, attacker_id, target_id), ectx)
    splash = [{"target": p["target"], "attack": p["attack"]}
              for n, p in ectx.emitted if n == "AttackWithAttackDamage"]   # id-tries (multi=True OrderBy id)
    ignited = [p["tile"] for n, p in ectx.emitted if n == "SetOnFire"]      # ordre board.neighbours (Foreach)
    if not splash and not ignited:
        return []
    return [{"passive": "FireOfAbsolution", "by": attacker_id, "on": target_id,
             "splash": splash, "ignited_tiles": ignited}]
