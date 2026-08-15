"""Passifs DARK ANGELS a effets — `LionHelm` (darkaAzrael) et `FearedInterrogator` (darkaAsmodai).

Les deux abilities sont des `TriggeredAbilityType` dont le SEUL artefact natif est un `CreateBehaviour`
DSL qui pose des effets sur le PORTEUR a l'init de l'ability (`CreateTrigger` herite =
`On(AbilityInit) & OwnerIsActor`, meme corps deduplique qu'AnvilShield). TOUTE la mecanique vit dans les
classes d'EFFET -> canal de port = `ABILITY_INIT_OWNER_EFFECTS` (pose) + `EFFECT_CLASSES` (comportement),
JAMAIS `ABILITY_TRIGGERS` (aucun trigger propre) ni `ABILITY_CLASSES` (ce ne sont pas des actives).

## Piege de RE a retenir (mesure 2026-07-27)

`data/symbols/<build>/frida/methods.tsv` est **DEDUPE PAR ADRESSE** (121 501 lignes, 121 501 adresses
distinctes) alors que le binaire fait de l'*identical code folding* : plusieurs `CreateTargetSelector`
au corps identique partagent une adresse et **une seule survit** dans la table.
`LionHelm_ExtraDmgEffect.CreateTargetSelector` en est ABSENT — et il EXISTE pourtant. Le depart se lit
sur la **VTABLE RUNTIME** (`resolveVtableSlot`, slot `+0x538` = `CreateTargetSelector`, lu depuis
`IdunBattle.Entities.Effects.BaseEffect$$CreateTargetSelectorAndCache`) :

    LionHelm_ExtraDmgEffect          slot 0x538 -> corps `SurroundingFriends(owner, ConfigConst(range))`
    LionHelm_ExtraBlockDamageEffect  slot 0x538 -> LE MEME corps
    LionHelm_ExtraBlockChanceEffect  slot 0x538 -> corps propre (+ UnitsFromFaction(DarkAngels))
    FearedInterrogator_OwnerEffect   slot 0x538 -> corps DEFAUT (= le porteur seul, comme SmashaEadEffect)
    FearedInterrogator_TargetEffect  slot 0x538 -> corps propre (cf. `FearedInterrogatorTargetEffect`)

## Qualification des enums (le meme id nomme autre chose ailleurs)

    EffectType 1193 LionHelm_ExtraDmg        != TriggeredAbilityType 1193 SynapticInsight
    EffectType 1214 LionHelm_ExtraBlockDamage!= ActiveAbilityType     1214 Hailstrike
    EffectType 1232 LionHelm_ExtraBlockChance!= TriggeredAbilityType 1232 EnvDefenderHealthBuff
    EffectType 1294/1295 FearedInterrogator_Owner/_Target
                                             != TriggeredAbilityType 1294/1295 RadZoneCorps/PriorityReclamation
    TriggeredAbilityType 1163 LionHelm · 1235 FearedInterrogator (les AbilityOrEffect des `.ctor`)
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition
# FORME B (#930) : `faction_of` reste patchable au foyer. Import ABSOLU du MODULE et non
# `from .. import aura_selectors` (#943) : la forme `from . import x` declare le PAQUET (elle lit
# son attribut), donc elle refermait le SCC `effects` -> `effects.factory` -> `loki.dark_angels_
# passives` -> `effects`. `import <module> as N` ne declare que le module, et reste forme B.
import engine.entities.effects.aura_selectors as ASel
from ..aura_selectors import is_targetable as _is_targetable, surrounding_friends
from ..base import BaseEffect
from ..magnitude import ability_var
# #943-r7 -- les deux canaux du substrat d'adjacence NATIF, en FORME B (#485-r1-r1).
# `pathfinding.board` n'importe RIEN de `engine` (il ne porte qu'un `from __future__`), et
# `engine.battle_query` n'importe que `hexgeo` + `.hex_corner` : aucune de ces deux aretes ne peut
# refermer le SCC `effects`.
from ...pathfinding import board as _board
from .... import battle_query as _bq
from ....entities.effect_type import EffectType   # #270-r1-r1-r3
from ....entities.stats import StatType   # #270-r1-r1-r3

_LION_HELM = "LionHelm"                    # TriggeredAbilityType 0x48b = 1163 (darkaAzrael)
_FEARED_INTERROGATOR = "FearedInterrogator"  # TriggeredAbilityType 0x4d3 = 1235 (darkaAsmodai)

# EffectTypes cites par les gates natifs de ce module.
EFFECT_LION_HELM_EXTRA_DMG = EffectType.LionHelm_ExtraDmg           # 0x4a9
EFFECT_LION_HELM_EXTRA_BLOCK_DAMAGE = EffectType.LionHelm_ExtraBlockDamage  # 0x4be
EFFECT_LION_HELM_EXTRA_BLOCK_CHANCE = EffectType.LionHelm_ExtraBlockChance  # 0x4d0
EFFECT_FEARED_INTERROGATOR_OWNER = EffectType.FearedInterrogator_Owner     # 0x50e
EFFECT_FEARED_INTERROGATOR_TARGET = EffectType.FearedInterrogator_Target    # 0x50f
EFFECT_STUNNED = EffectType.Stunned                       # 0x48a
EFFECT_PINNED = EffectType.Pinned                        # 0x429 -- « Suppressed » de l'i2

# `IdunBattle.Entities.Enum.UnitFaction` 10 = DarkAngels (argument litteral du `UnitsFromFaction` des
# deux selecteurs) ; cote gameconfig la meme faction est le champ `FactionId` = "DarkAngels".
_FACTION_DARK_ANGELS = "DarkAngels"
# `IdunBattle.Entities.Enum.UnitTrait` 0x7ea = 2026 = grande-alliance Chaos (derive de `GrandAllianceId`,
# `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` : Imperial->26, Xenos->0x3ee, Chaos->0x7ea) —
# meme derivation que RitesOfBattle / BeaconOfRage.
_GRAND_ALLIANCE_CHAOS = "Chaos"


def _hex_distance(a, b) -> "int | None":
    if not a or not b:
        return None
    import hexgeo
    return hexgeo.distance(tuple(a), tuple(b))


def _adjacency_channels(state):
    """Les DEUX canaux de l'adjacence NATIVE derives du board de l'ECS, en TRI-ETAT (#943-r7).

    `IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(origin)` =
    `Units(AdjacentTiles(origin)) - origin`, et
    `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` ENUMERE
    `BattleQuery$$GetAdjacentTiles(t)` pour chaque tuile de l'origine -- donc la liste STOCKEE du
    `ConnectivityComponent`, puis la porte `|dElev| < 2` de
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`. Une couronne
    hex nue SUR-ATTEINT cette liste (mesure #943-r4 : 22 aretes sur `MC2_60`, 8 sur `C4_69`).

    Board absent -> `(None, None)`, et `battle_query.is_adjacent` retombe alors sur son repli
    geometrique NOMME : le comportement d'avant, jamais un voisinage vide.

    La DERIVATION elle-meme vit au foyer `pathfinding.board.adjacency_channels` depuis #943-r7 : ce
    wrapper ne garde que la lecture du board sur l'ECS et la RE ci-dessus."""
    return _board.adjacency_channels(getattr(state, "board", None))


# ─────────────────────────────────────────────────────────────────────────────────────────────────
#  LionHelm — 3 effets AURA poses sur AZRAEL par
#  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LionHelmAbility$$CreateBehaviour` :
#
#     AddEffect( LionHelm_ExtraDmg 1193, AbilityStateReference, targets = Owner@0x148, turns = null )
#   + AddDynamicStatModifierEffect( Owner@0x148, LionHelm_ExtraBlockChance 1232,
#                                   StatType.BlockChance = 7, turns = null, isHidden = false )
#   + AddDynamicStatModifierEffect( Owner@0x148, LionHelm_ExtraBlockDamage 1214,
#                                   StatType.BlockDamage = 8, turns = null, isHidden = false )
#
#  Les trois effets-entites vivent sur le PORTEUR (verifie live : `decisionView` d'un runner frais
#  liste les 3 chez Azrael et RIEN chez ses allies) ; c'est leur `CreateTargetSelector` qui projette.
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def _lion_helm_range() -> int:
    """`AbilityConfiguration.GetNumberConstant(0x16 = range)` = `LionHelm.constants.range` (=2)."""
    r = ability_var(_LION_HELM, "range", is_constant=True)
    return int(r) if r else 2


def _surrounding_friends(ctx: Mapping, other_key: str, other_pos_key: str,
                         other_team_key: str) -> bool:
    """`IdunBattleLogic.Entities.DSLFactory$$SurroundingFriends(unit = Owner@0x148, range, unique = true,
    unitSelectionType = OnlyAliveAndTargetable)` — allies du porteur a <= range hexes, **self EXCLU**
    (`SurroundingTiles(range) - Tiles(self)`). Le volet « OnlyAliveAndTargetable » est assure par
    l'appelant (les agregateurs ne presentent que des unites vivantes)."""
    if ctx.get(other_key) == ctx.get("owner_id"):
        return False                                   # self exclu
    if ctx.get("owner_team") is None or ctx.get("owner_team") != ctx.get(other_team_key):
        return False                                   # Friends = meme equipe que le porteur
    d = _hex_distance(ctx.get("owner_pos"), ctx.get(other_pos_key))
    return d is not None and d <= _lion_helm_range()


class LionHelmExtraDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.LionHelm_ExtraDmgEffect` (EffectType 1193) — AURA cote SOURCE :
    +extraDmg FLAT par coup aux attaques DECLENCHEES des allies d'Azrael a <= 2 hexes.

    `.ctor` = `BaseEffect(AbilityOrEffect(TriggeredAbilityType.LionHelm = 1163), hasAutomaticActivation = true)`.

    Selecteur (vtable slot `+0x538`, corps partage avec `LionHelm_ExtraBlockDamageEffect` et
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PathOfCommandExtraDmgEffect$$CreateTargetSelector`) :
    `SurroundingFriends(Owner@0x148, GetNumberConstant(0x16 = range), true, OnlyAliveAndTargetable)`.

    `IdunBattle.Entities.Effects.Loki.LionHelm_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`
    (MIRROR du decompile) :

        amount = ConfigVar( AbilityVariableType.extraDmg = 8, GetAbilityState(this), config@0x60 )
        A      = HasEffect( Caster@0x160, EffectType.Overwatch_AutoAttack = 1009,
                            onlyActive = false, targetType = EffectTargetType.Both )
                 & IsOverwatchAttack()
        B      = HasEffect( Caster@0x160, EffectType.GrimRetribution_CounterAttack = 1213,
                            onlyActive = false, targetType = Both )
                 & CurrentAbilityIs( AbilityOrEffect(TriggeredAbilityType.GrimRetribution = 1177) )
        return   EffectBonus.ForAddition( get_OwnerIsCaster & (A | B), amount,
                                          source = AbilityOrEffect(LionHelm 1163) )

    i2 : « Friendly units within 2 hexes ... deal +437 Damage with attacks triggered by Overwatch. »

    CANAL PORT = `create_aura_attack_damage_bonus_for_ally` (additif PRE-percage PAR COUP, meme canal que
    `LordOfTheHost_ExtraDamage` / `SpotterReworked_ExtraDamage`) : l'effet-entite vit sur Azrael, le bonus
    est evalue POUR L'ALLIE qui attaque.

    BRANCHE A (portee) : `IsOverwatchAttack` <- `ctx["is_overwatch"]`, threade depuis
    `AttackDamageOperation.execute(is_overwatch=...)` (le meme flag qui alimente deja
    `Hailstrike_ExtraPierce`). Le conjoint `HasEffect(Caster, Overwatch_AutoAttack)` est
    STRUCTURELLEMENT satisfait cote port : `is_overwatch=True` n'est pose QUE par le vecteur
    `Overwatch_AutoAttackEffect` (`triggers/effect_triggers.py`), c'est-a-dire exactement quand
    l'attaquant PORTE l'effet 1009.

    BRANCHE B — **RESIDU FLAGGE, inerte aujourd'hui** : elle exige que l'attaquant porte
    `GrimRetribution_CounterAttack` (1213) ET que l'ability courante soit `GrimRetribution` (1177).
    Le passif `GrimRetribution` de `darkaHellblaster` n'est PAS porte (GAP-ABSENT, item #13 de
    `docs/rl/passive-ability-coverage.md`) -> ni l'effet 1213 ni l'ability 1177 n'existent offline, la
    branche ne peut ni fire ni etre confrontee. Elle est documentee ici pour etre cablee AVEC
    GrimRetribution, jamais devinee. Consequence : MANQUE possible (jamais un sur-compte)."""

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        # gate A : IsOverwatchAttack (+ HasEffect(Caster, Overwatch_AutoAttack), structurel — cf. docstring).
        # Branche B (GrimRetribution) : residu flagge, cf. docstring.
        if not c.get("is_overwatch"):
            return None
        if not _surrounding_friends(c, "att_id", "att_pos", "att_team"):
            return None
        if self.ability_level is None:                 # ConfigVar sans AbilityState -> pas de magnitude
            return None
        amt = ability_var(_LION_HELM, "extraDmg", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt else None


class _LionHelmAuraStatModEffect(BaseEffect):
    """Socle des DEUX `ADynamicStatModifierEffect` de LionHelm — `.ctor` identique :
    `ADynamicStatModifierEffect( sourceAbility = AbilityOrEffect(LionHelm 1163), unitEffectType = null,
    canBeImmuneTo = false, keepOnRevive = true, isMultiply = false )`.

    Leur `GetDynamicStatModificationAmount(owner, target, effect)` lit
    `ConfigVar( abilityType = TriggeredAbilityType.LionHelm, unit = EffectSource(Get(effect)),
    variableType = <var> )` : la magnitude s'indexe sur l'`AbilityState` de la **SOURCE** (Azrael),
    jamais sur celle du buffe -> `self.ability_level` / `self.ability_variables_multiplier` de
    l'instance, qui VIT sur Azrael. C'est aussi pourquoi ces effets sont modelises cote SOURCE.

    INTERFACE PORT (duck-typed, consommee par `runner/operations/aura_stat_mods.py`) :
      * `aura_stat_modification_stat()`   -> le `StatType` ecrit chez la cible ;
      * `aura_stat_modification_amount()` -> la magnitude (indexee SOURCE) ;
      * `aura_stat_modification_targets(state, owner_id)` -> les entity-ids selectionnes.
    Elle est VOLONTAIREMENT hors de `BaseEffect` : seuls ces deux effets la portent aujourd'hui, et le
    driver interroge par `getattr` (meme regime que `TARGETING_OPTIONS`).

    GROUND TRUTH LIVE (runner 4242, board MC1_67, Azrael ablvl 50 / mult 180) — `statModSources` :
      * `darkaHellblaster` (Dark Angels, dist 1)  : blockChance +20 (source 97), blockDamage +797 (source 98)
      * `ultraApothecary`  (Ultramarines, dist 1) : blockDamage +797 SEUL  -> le gate `UnitsFromFaction`
        du volet blockChance est REEL et discriminant ;
      * `darkaTerminator`  (Deep Strike, TeleportingIn) : RIEN -> `OnlyAliveAndTargetable` est REEL ;
      * `darkaAzrael` lui-meme : RIEN -> `SurroundingFriends` exclut bien la source.
    Et l'aura est RE-EVALUEE A CHAQUE MOUVEMENT (mesure : l'allie eloigne a (4,4) perd les +797, il les
    retrouve en revenant) -> le port materialise/reverte au `MoveUnitOperation`, il ne fige pas le seed.
    """

    _VAR = ""                    # cle gameconfig de la magnitude
    _STAT = 0                    # StatType ecrit chez la cible
    _DARK_ANGELS_ONLY = False    # UnitsFromFaction(DarkAngels) en plus de SurroundingFriends

    def aura_stat_modification_stat(self) -> int:
        return int(self._STAT)

    def aura_stat_modification_amount(self) -> "int | None":
        if self.ability_level is None:
            return None
        return ability_var(_LION_HELM, self._VAR, self.ability_level,
                           multiplier_pct=self.ability_variables_multiplier)

    def aura_stat_modification_targets(self, state, owner_id: int) -> list:
        """`SurroundingFriends(Owner, range, unique, OnlyAliveAndTargetable)` [ + `UnitsFromFaction(
        DarkAngels)` ] evalue contre l'ECS. Le volet « Targetable » retire les unites en Deep Strike
        (`TeleportStrike_TeleportingIn`), mesure live ci-dessus.

        Le noeud de tete est le FOYER PARTAGE `effects/aura_selectors.surrounding_friends` (le
        binaire lui-meme partage ce corps entre plusieurs effets, cf. l'en-tete de ce module et
        `loki/crit_aura.py`) ; ne reste ici que le filtre PROPRE a cette classe."""
        out: list = []
        for uid in surrounding_friends(state, owner_id, _lion_helm_range()):
            if self._DARK_ANGELS_ONLY and _faction_of(state, uid) != _FACTION_DARK_ANGELS:
                continue                               # UnitsFromFaction(UnitFaction.DarkAngels = 10)
            out.append(uid)
        return out


class LionHelmExtraBlockDamageEffect(_LionHelmAuraStatModEffect):
    """`IdunBattle.Entities.Effects.Loki.LionHelm_ExtraBlockDamageEffect` (EffectType 1214).

    Selecteur (vtable `+0x538`, corps partage avec `LionHelm_ExtraDmgEffect`) :
    `SurroundingFriends(Owner@0x148, GetNumberConstant(0x16 = range), true, OnlyAliveAndTargetable)`.

    `IdunBattle.Entities.Effects.Loki.LionHelm_ExtraBlockDamageEffect$$GetDynamicStatModificationAmount` :
    `ConfigVar( TriggeredAbilityType.LionHelm, EffectSource(Get(effect)),
    AbilityVariableType.blockDmg = 20 )` ; stat ecrit = `StatType.BlockDamage = 8`.
    `blockDmg` EST dans `variablesAffectedByRarityBonus` -> scale par le multiplier d'AZRAEL
    (mesure live : blockDmg[50] = 443 x 1.8 = 797, exactement la modification observee).

    i2 : « Friendly units within 2 hexes block an additional 582 Damage when they Block ... »"""

    _VAR = "blockDmg"
    _STAT = StatType.BLOCK_DAMAGE                     # StatType.BlockDamage
    _DARK_ANGELS_ONLY = False


class LionHelmExtraBlockChanceEffect(_LionHelmAuraStatModEffect):
    """`IdunBattle.Entities.Effects.Loki.LionHelm_ExtraBlockChanceEffect` (EffectType 1232).

    `IdunBattle.Entities.Effects.Loki.LionHelm_ExtraBlockChanceEffect$$CreateTargetSelector` :
    `UnitsFromFaction( SurroundingFriends(Owner@0x148, GetNumberConstant(0x16 = range), true,
    OnlyAliveAndTargetable), UnitFaction.DarkAngels = 10, OnlyAliveAndTargetable )`.

    `IdunBattle.Entities.Effects.Loki.LionHelm_ExtraBlockChanceEffect$$GetDynamicStatModificationAmount` :
    `ConfigVar( TriggeredAbilityType.LionHelm, EffectSource(Get(effect)),
    AbilityVariableType.blockChance = 21 )` ; stat ecrit = `StatType.BlockChance = 7`.
    `blockChance` n'est **PAS** dans `variablesAffectedByRarityBonus` -> AUCUN scaling de rarete
    (mesure live : +20 exactement, la ou blockDmg est scale x1.8 sur le meme porteur).

    i2 : « Other friendly Dark Angels within 2 hexes also have their Block chance increased by +20% »"""

    _VAR = "blockChance"
    _STAT = StatType.BLOCK_CHANCE                     # StatType.BlockChance
    _DARK_ANGELS_ONLY = True


# ─────────────────────────────────────────────────────────────────────────────────────────────────
#  FearedInterrogator — 2 effets poses sur ASMODAI par
#  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FearedInterrogatorAbility$$CreateBehaviour` :
#
#     AddEffect( FearedInterrogator_Owner  1294, AbilityStateReference,
#                source = Owner@0x148, targets = Owner@0x148, options = default )
#   & AddEffect( FearedInterrogator_Target 1295, AbilityStateReference,
#                source = Owner@0x148, targets = Owner@0x148, options = default )
#
#  Verifie live : les DEUX sont listes chez `darkaAsmodai`, AUCUN chez les ennemis -> le marqueur
#  `_Target` n'est PAS un effet capte cote cible, c'est un SELECTEUR a re-evaluer offline.
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def _unit_component_ctx(state, unit_id: int):
    from ....runner.components import StatsComponent
    ent = state.get_entity(unit_id)
    sc = ent.get_component(StatsComponent) if ent is not None else None
    return getattr(sc, "ctx", None)


def _faction_of(state, unit_id: int) -> "str | None":
    """`FactionId` gameconfig de l'unite (resolu par `visual_id`) — le pendant offline de
    `IdunBattleLogic.Entities.DSLSelectors$$UnitsFromFaction(UnitFaction)`.

    HISSE dans le FOYER `effects/aura_selectors.faction_of` (#930), qui porte deja les autres
    primitives de selecteur d'aura : un second porteur du meme accesseur serait un fork.
    Appel en FORME B (`ASel.faction_of`, module lie puis attribut lu a l'appel) — une liaison
    `from ... import faction_of` figerait le binding et DESARMERAIT tout patch pose au foyer."""
    return ASel.faction_of(state, unit_id)


def grand_alliance_of(state, unit_id: int) -> "str | None":
    """`GrandAllianceId` gameconfig — source du trait de grande-alliance
    (`idun.Idun.Source.Shared.GrandAlliance$$GetTrait` : Chaos -> UnitTrait 0x7ea = 2026)."""
    ctx = _unit_component_ctx(state, unit_id)
    vid = getattr(ctx, "visual_id", None) if ctx is not None else None
    if vid is None:
        return None
    import gameconfig as GC
    return (GC.unit(vid) or {}).get("GrandAllianceId")


# `TeleportStrike_TeleportingIn` — l'unite est en Deep Strike : NON ciblable tant qu'elle n'a pas agi
# (i2 du trait TeleportStrike). C'est le volet « Targetable » d'`OnlyAliveAndTargetable` que la mesure
# live a rendu visible (darkaTerminator en Deep Strike ne recoit AUCUNE modification de LionHelm).
# Le predicat vit dans le FOYER `effects/aura_selectors.is_targetable` (importe en tete sous
# `_is_targetable`) — il est partage avec les autres selecteurs d'aura.


def _effect_names(state, unit_id: int) -> frozenset:
    if state.effects is None:
        return frozenset()
    return frozenset(e.name for e in (state.effects.by_unit.get(int(unit_id), []) or [])
                     if not e.consumed and e.name)


class FearedInterrogatorTargetEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.FearedInterrogator_TargetEffect` (EffectType 1295) — le
    MARQUEUR. Effet sans aucun bonus propre : il n'existe que pour que son `CreateTargetSelector`
    designe les ennemis que `FearedInterrogator_OwnerEffect` bonifie
    (`HasEffect(Target@0x178, 1295, targetType = Both)`).

    `.ctor` (corps partage avec `_OwnerEffect`) =
    `BaseEffect(AbilityOrEffect(TriggeredAbilityType.FearedInterrogator = 1235), hasAutomaticActivation = true)`.

    `IdunBattle.Entities.Effects.Loki.FearedInterrogator_TargetEffect$$CreateTargetSelector`
    (MIRROR du decompile) :

        A       = ValidNormalAttackTargets( unit = Owner@0x148, unitTile = Tiles(Owner@0x148),
                                            range = null, ignoreRule = null, additionalRule = null )
        friends = UnitsFromFaction( Friends(of = Owner@0x148, entities = <all>@0x80,
                                            OnlyAliveAndTargetable),
                                    UnitFaction.DarkAngels = 10, OnlyAliveAndTargetable )
                  - Owner@0x148                                  // « ANOTHER friendly Dark Angel »
        E       = EntitiesWithAnyEffect( A, [ EffectType.Stunned = 1162, EffectType.Pinned = 1065 ] )
        B       = AdjacentUnits( friends, unique = true, OnlyAliveAndTargetable )
        return    Unique( E + (A & B) )

    i2 : « ... enemies that are Suppressed, Stunned, or that are adjacent to another friendly Dark
    Angel. » — « Suppressed » = `EffectType.Pinned` (1065), le meme effet que pose SuppressiveFire.

    NB le texte i2 TAIT le gate `ValidNormalAttackTargets` : le marqueur ne se pose QUE sur des cibles
    d'attaque normale legales d'Asmodai (portee de SON arme depuis SA tuile). C'est un vrai gate du
    decompile, pas une lecture.

    INTERFACE PORT (duck-typed, consommee par `runner/damage_model.marked_effect_types_for_target`) :
    `marks_target(state, owner_id, target_id) -> bool`. Le marqueur n'etant JAMAIS materialise sur la
    cible cote natif (verifie live), il est re-evalue a la demande — comme tout selecteur d'aura."""

    def marks_target(self, state, owner_id: int, target_id: int) -> bool:
        from ....runner.components import PositionComponent, OwnerComponent, UnitComponent
        owner = state.get_entity(owner_id)
        tgt = state.get_entity(target_id)
        if owner is None or tgt is None:
            return False
        opc, ooc = owner.get_component(PositionComponent), owner.get_component(OwnerComponent)
        tpc, toc = tgt.get_component(PositionComponent), tgt.get_component(OwnerComponent)
        if opc is None or ooc is None or tpc is None or toc is None:
            return False
        # --- A = ValidNormalAttackTargets(Owner, Tiles(Owner), range = null) : ENNEMIS vivants,
        #         ciblables, a portee de l'attaque NORMALE du porteur depuis SA tuile.
        if toc.team == ooc.team:
            return False
        tuc = tgt.get_component(UnitComponent)
        if tuc is not None and not tuc.alive:
            return False
        if not _is_targetable(state, target_id):
            return False
        d = _hex_distance((opc.col, opc.row), (tpc.col, tpc.row))
        if d is None or d > _normal_attack_range(state, owner_id):
            return False
        # --- E = EntitiesWithAnyEffect(A, [Stunned, Pinned])
        names = _effect_names(state, target_id)
        if "Stunned" in names or "Pinned" in names:
            return True
        # --- B = AdjacentUnits( UnitsFromFaction(Friends(Owner), DarkAngels) - Owner )
        # #943-r7 : `AdjacentUnits(origin)` = `Units(AdjacentTiles(origin)) - origin`, et
        # `AdjacentTilesSelector$$Select` enumere le voisinage des tuiles de l'ORIGINE -- donc
        # la SOURCE de l'enumeration est l'ami Dark Angel, pas la cible. Une couronne hex nue est
        # symetrique et ne pouvait pas porter cet axe ; la liste stockee, si.
        # (`- origin` inerte ici : la cible est un ENNEMI, jamais dans `friends`.)
        elev_by_pos, neigh_by_pos = _adjacency_channels(state)
        for uid, ent in state.entities.items():
            if uid == owner_id or uid == target_id:
                continue                                   # « ANOTHER » Dark Angel (op_Subtraction Owner)
            uc = ent.get_component(UnitComponent)
            if uc is not None and not uc.alive:
                continue
            oc = ent.get_component(OwnerComponent)
            pc = ent.get_component(PositionComponent)
            if oc is None or pc is None or oc.team != ooc.team:
                continue                                   # Friends(Owner)
            if not _is_targetable(state, uid):
                continue                                   # OnlyAliveAndTargetable
            if _faction_of(state, uid) != _FACTION_DARK_ANGELS:
                continue                                   # UnitsFromFaction(DarkAngels)
            if _bq.is_adjacent((pc.col, pc.row), (tpc.col, tpc.row), elev_by_pos, neigh_by_pos):
                return True                                # AdjacentUnits(friends)
        return False


def _normal_attack_range(state, unit_id: int) -> int:
    """Portee de l'attaque NORMALE du porteur (`range = null` de `ValidNormalAttackTargets` = la portee
    propre de l'unite) : `UnitContext.range` (0/absent = melee -> 1)."""
    ctx = _unit_component_ctx(state, unit_id)
    r = int(getattr(ctx, "range", 0) or 0) if ctx is not None else 0
    return r if r > 0 else 1


class FearedInterrogatorOwnerEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.FearedInterrogator_OwnerEffect` (EffectType 1294) — les DEUX
    bonus d'ASMODAI. Selecteur = le corps DEFAUT (vtable `+0x538` -> le meme que `SmashaEadEffect`) :
    l'effet reste sur son porteur, c'est un SELF-effect.

    `IdunBattle.Entities.Effects.Loki.FearedInterrogator_OwnerEffect$$CreateEffectDamageBonusForAttack` :

        amount = ConfigVar( AbilityVariableType.extraDmg = 8, GetAbilityState(this), config@0x60 )
        gate   = get_OwnerIsCaster
               & HasEffect( Target@0x178, EffectType.FearedInterrogator_Target = 1295,
                            onlyActive = false, targetType = EffectTargetType.Both )
        return   EffectBonus.ForAddition( gate, amount )

    `IdunBattle.Entities.Effects.Loki.FearedInterrogator_OwnerEffect$$CreateEffectHitsBonusForAttack` :

        amount = ConfigVar( AbilityVariableType.extraHits = 19, GetAbilityState(this), config@0x60 )
        gate   = get_OwnerIsCaster
               & HasEffect( Target@0x178, 1295, false, Both )
               & HasTrait( Target@0x178, UnitTrait 0x7ea = 2026 = grande-alliance Chaos )
        return   EffectBonus.ForAddition( gate, amount )

    i2 : « Deals +728 Damage against enemies that are Suppressed, Stunned, or that are adjacent to
    another friendly Dark Angel. Scores 2 additional hits if the enemy is also Chaos. »

    MAGNITUDES : `extraDmg` EST dans `variablesAffectedByRarityBonus` (scale par le multiplier
    d'Asmodai) ; `extraHits` ne l'est PAS (2 coups, jamais scale).

    `get_OwnerIsCaster` est satisfait STRUCTURELLEMENT : ces deux hooks ne sont appeles que sur les
    effets de l'ATTAQUANT (`_attacker_effect_bonuses` / `hits_bonus_from_effects`).

    `HasEffect(Target, 1295, Both)` est re-evalue par `marked_effect_types_for_target`
    (`runner/damage_model.py`) et threade dans le ctx sous `marked_effect_types` — le natif ne
    materialise RIEN sur la cible (verifie live), donc rien a lire dans `decisionView.effects`."""

    def _marked(self, ctx: Mapping | None) -> bool:
        c = ctx or {}
        marked = c.get("marked_effect_types")
        return marked is not None and EFFECT_FEARED_INTERROGATOR_TARGET in marked

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits=None, is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if not self._marked(att_ctx):
            return None                                   # HasEffect(Target, FearedInterrogator_Target)
        if self.ability_level is None:
            return None
        amt = ability_var(_FEARED_INTERROGATOR, "extraDmg", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt else None

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: Mapping | None = None) -> EffectBonus | None:
        c = att_ctx or {}
        if not self._marked(c):
            return None                                   # HasEffect(Target, FearedInterrogator_Target)
        if c.get("tgt_grand_alliance") != _GRAND_ALLIANCE_CHAOS:
            return None                                   # HasTrait(Target, 0x7ea = Chaos)
        if self.ability_level is None:
            return None
        amt = ability_var(_FEARED_INTERROGATOR, "extraHits", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt else None
