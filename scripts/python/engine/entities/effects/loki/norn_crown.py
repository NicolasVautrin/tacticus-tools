"""`NornCrown` -- la relique `R_Booster_Block_NornCrown` de `tyranNeurothrope` << Neurothrope >>
(Tyranids, HERO, AU POOL) et son owner-effect d'AURA. Tache #1011.

i2 (`Abilities/NornCrown_CurrentLevelDescription`) : « The maximum level of Neuroparasite is
increased by {[effectLevel]}. Other friendly Psykers within Synapse range and friendly Summons
within Synapse range deal +{[extraDmg]} Damage to enemies that are affected by Neuroparasite. »

================================================================================================
IDENTITE -- DEUX enums homonymes, et un TROISIEME qui porte le meme ordinal
================================================================================================

    TriggeredAbilityType  0x5d7 = 1495 = NornCrown                   <- l'ABILITY (la relique)
    EffectType            0x5d4 = 1492 = NornCrown                   <- l'EFFET pose sur le porteur
    EffectType            0x5d7 = 1495 = HunterOfSouls_ExtraDamage   <- rien a voir

Le couple ability -> effet est **LU**, jamais deduit du nom :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.NornCrownAbility$$GetEffectType` a pour corps
ENTIER `return 0x5d4`. Et `frida/classes.tsv` donne son parent :
`NornCrownAbility : IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` -- la classe
n'override QUE `GetEffectType`, tout le reste vient de la base.

================================================================================================
1. LA POSE -- owner-effect PERMANENT, a l'init de l'ability
================================================================================================

`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateTrigger` ::

    OnOwnerSpecificAbilityInit( <this+0x10> = this.AbilityType = 0x5d7 )

`...AOwnerEffectTriggeredAbility$$CreateBehaviour` ::

    If( CreateCondition(abilityState) = <DSLTriggers+0x70>,
        AddEffect( GetEffectType() = 0x5d4,
                   abilityState = AbilityState(Owner@DSLSelectors+0x30, AbilityType(abilityState)),
                   source  = Owner@DSLSelectors+0x30,
                   targets = Owner@DSLSelectors+0x30,
                   options = <Nullable ZERO-initialise> ) )

`options` VIDE (les 32 octets du local sont mis a zero juste avant l'appel) -> aucune duree ->
effet **PERMANENT**. Exactement le patron `Vitarus` (#1005), `ToughToKill` (#950),
`Skullsmasher` (#953) : d'ou l'entree `ABILITY_INIT_OWNER_EFFECTS["NornCrown"] = ["NornCrown"]`.
Comme pour `Vitarus`, la relique arrive par la voie TERTIAIRE, que `_seed_ability_owner_effects`
lit depuis #1005.

================================================================================================
2. QUI EN BENEFICIE -- `NornCrownEffect$$CreateTargetSelector`
================================================================================================

    Filter( AllUnits@DSLSelectors+0x20,
              AreFriends( Owner@DSLSelectors+0x30, It@DSLSelectors+0x68,
                          comparisonType = 0 = ByCurrentTeam, anyEntity = false )
            & IsInTeamSynapseRange( It@+0x68, Owner@+0x30 )
            & (   HasTrait( It@+0x68, 0x3ea = 1002 Psyker )
                | HasTrait( It@+0x68, 0x2   = 2    Summon ) ) )

Les signatures sont LUES dans `data/symbols/<build>/frida/methods.tsv`
(`DSLTriggers.AreFriends(unit1, unit2, comparisonType:UnitTeamSelectionType, anyEntity:Boolean)`,
`DSLTriggers.IsInTeamSynapseRange(target, team)`), et les slots `DSLSelectors` dans
`IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` (`+0x20 AllUnits · +0x30 Owner ·
+0x60 Target · +0x68 ActiveTarget`, cf. `docs/rl/case-489-fragstorm-grenade-launcher.md` §4).

⚠ **LE PORTEUR N'EST PAS EXCLU DU SELECTEUR** -- contrairement a ce que le mot « Other » de l'i2
suggere. `AreFriends` descend jusqu'a `IdunBattle.Core.Services.BattleQuery$$AreFriends`, dont le
corps ENTIER est `return UnitExtensions$$IsFriend(unit1, unit2, selectionType, state)`, et
`IsFriend` **n'ecarte PAS l'egalite** (le meme fait qui oblige `PsychicStalk_FriendlyChaos` et
`DestroyTheWitch_ExtraDamage` a porter une patte SELF). Le Neurothrope est lui-meme `Psyker` ET
`Synapse` : il est donc dans son propre set. D'ou les **DEUX pattes disjointes** ci-dessous, meme
arbitrage que `DestroyTheWitchExtraDamageEffect` et `IconOfObstinacy_ExtraDmg` -- les agregateurs
d'aura excluent deja `uid == att_id`, donc ni trou ni double-compte.

### `IsInTeamSynapseRange`, decompose jusqu'au scalaire

    DSLTriggers$$IsInTeamSynapseRange(target, team)
      -> new IsInAuraRangeTrigger(state, query, effectType = 0x41c = 1052 Synapse_Effect,
                                  target, team)
    IsInAuraRangeTrigger$$ShouldTrigger
      -> IBattleQuery slot 148 = IsInTeamAuraRange(effectType, GetCurrentTeamId(team), target)
    BattleQuery$$IsInTeamAuraRange  = GetInRangeAuraAmount(..., returnFirst: true) > 0
    BattleQuery$$GetInRangeAuraAmount(effectType, team, target, returnFirst) :
        auraDef = EffectsDatabase[effectType]                      # l'implementation d'EFFET
        trait   = auraDef.GetTrait()
        foreach unit in GetSurroundingUnits(target, <range>) :
            if !UnitExtensions$$HasTrait(unit, trait)            : continue
            if EntityExtensions$$GetCurrentTeamId(unit) != team  : continue
            if <range per-unit> < BattleQuery$$GetDistance(unit, target) : continue
            count++ ; if returnFirst : break

et l'implementation lue est `IdunBattle.Entities.Effects.Loki.SynapseEffect` :
`$$GetTrait` a pour corps ENTIER `return 0x7e8` (= 2024 `UnitTrait.Synapse`) et
`$$GetNextTurnRange` = `Direct(2)`.

=> **il existe une unite de l'equipe du PORTEUR, portant le trait `Synapse`, a distance hex <= 2
du beneficiaire**. Le trait, pas l'effet : le natif teste `HasTrait`, ce que le port lit sur le
substrat d'ENTITE (#264). Le rayon 2 est corrobore par deux sources independantes --
`services/movement_query.py::synapse_tiles_for` (`GetSurroundingTiles(e, 2, ...)` du
`FearOfTheUnseenPathfinder`) et l'i2 du trait (« Friendly units within 2 hexes »).

================================================================================================
3. CE QU'ILS GAGNENT -- `NornCrownEffect$$CreateEffectDamageBonusForAttack`
================================================================================================

    EffectBonus.ForAddition(
        get_OwnerIsCaster
          & HasEffect( Target@DSLSelectors+0x60, 0x4c2 = 1218 Neuroparasite,
                       onlyActive = false, targetType = 6 = Both ),
        ConfigVar( 0x8 = extraDmg, GetAbilityState(effect), <config@effet+0x60> ) )

`EffectTargetType 6 = Both` et `UnitTeamSelectionType 0 = ByCurrentTeam` sont lus dans
`data/symbols/<build>/frida/enums.tsv`. `onlyActive = false` -> la simple PRESENCE d'une instance
1218 sur la cible suffit, sans lire son `IsActive` (meme convention que le gate de pose de
`NeuroparasiteAbility`, cf. `runner/operations/triggers/loki/neuroparasite.py`).

Canal : additif ATTAQUANT (`DamageModifiers.Add`), le meme que `BeaconOfRage_FriendlyExtraDamage`
(#191) et `DestroyTheWitch_ExtraDamage` -- PAS le canal defenseur de `NeuroparasiteEffect$$
CreateEffectDamageMalusForDefense` (qui, lui, est gate `AreEqual(BondedEntity, damageSource)` et
ne profite qu'au Neurothrope infecteur). Les deux se cumulent sans se recouvrir.

⚠ **LE NIVEAU EST CELUI DE LA RELIQUE, PAS DU PASSIF** (#357). `GetAbilityState(effect)` rend
l'`AbilityState` BAKE a la pose, donc l'etat **TERTIAIRE** du porteur quand la relique est
EQUIPEE. Lire `self.ability_level` rendrait le niveau PASSIF (50 sur tout runner normalise), donc
le dernier palier `extraDmg[10] = 1308` au lieu de `extraDmg[1] = 880` -- un ecart de +49 %,
SILENCIEUX. Le foyer UNIQUE est `runner/operations/triggers/base.py::triggered_ability_state`,
expose au ctx sous `tertiary_ability_state_of` (meme cle et meme semantique que
`RelicBoltPistol*Effect`, `KardiocoreGalvanus`, `MawClawsOfThyrax`, ...).

================================================================================================
4. LA SECONDE FACE DE LA RELIQUE EST DEJA PORTEE
================================================================================================

« The maximum level of Neuroparasite is increased by 1 » ne vit PAS dans cette classe :
`IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$GetMaximumLevel` =
`Sum( ConfigVar(0x4c = buffMaxLevel, ...), If(ActorHasTriggeredAbility(BondedEntity, 0x5d7),
ConfigConst(0x5d7, BondedEntity, 0x73 = effectLevel), Direct(0)) )`, et ce terme est porte depuis
#462-r4b-r1-r1-r1 par `runner/operations/triggers/loki/neuroparasite.py::
neuroparasite_maximum_level`. Rien a faire ici -- mais c'est ce qui rend la relique
DOUBLEMENT observable en bataille.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition
from ...effect_type import EffectType
from ...traits.unit_trait import UnitTrait, has_any_trait
from ..base import BaseEffect
from ..magnitude import ability_var

#: `TriggeredAbilityType` 0x5d7 = 1495 -- la config lue par `ConfigVar` (celle de la RELIQUE).
NORN_CROWN_ABILITY = "NornCrown"
#: `AbilityVariableType` 0x8 = 8 -- la seule variable de `NornCrown` (`extraDmg`, 10 paliers).
_VAR_EXTRA_DMG = "extraDmg"
#: `HasTrait(It@+0x68, 0x3ea) | HasTrait(It@+0x68, 0x2)` -- le fork de trait du selecteur.
_QUALIFYING_TRAITS = (UnitTrait.Psyker, UnitTrait.Summon)
#: `SynapseEffect$$GetTrait` -> `return 0x7e8` -- l'EMETTEUR de la bulle, teste par `HasTrait`.
SYNAPSE_TRAIT = UnitTrait.Synapse.name
#: `SynapseEffect$$GetNextTurnRange` = `Direct(2)` -- rayon hex de la bulle (cf. en-tete §2).
SYNAPSE_RANGE = 2
#: `HasEffect(Target@+0x60, 0x4c2, onlyActive: false, 6 = Both)`.
NEUROPARASITE_EFFECT_NAME = EffectType.Neuroparasite.name
#: callable `(owner_id, ability_name) -> (level, multiplier)` -- mirror de `GetAbilityState(effect)`
#: (#357). Meme cle que `RelicBoltPistol*Effect` / `KardiocoreGalvanus` : le foyer UNIQUE
#: `runner/operations/triggers/base.py::triggered_ability_state`.
CTX_ABILITY_STATE_OF = "tertiary_ability_state_of"
#: `{team_id: ((col, row), ...)}` des unites VIVANTES portant le trait `Synapse`, par equipe --
#: substrat de `IsInTeamSynapseRange`. Tri-etat : cle ABSENTE = canal NON MESURE (le gate se tait).
CTX_TEAM_SYNAPSE_POSITIONS = "team_synapse_positions"
#: Noms des effets NON CONSOMMES portes par la CIBLE du coup -- substrat de `HasEffect(Target, ...)`.
#: Tri-etat : `None` = NON MESURE (le gate se tait), `frozenset()` = mesure et vide.
CTX_TGT_EFFECT_NAMES = "tgt_effect_names"


def _in_team_synapse_range(team, pos, ctx: "Mapping | None") -> "bool | None":
    """`IdunBattleLogic.Entities.DSLTriggers$$IsInTeamSynapseRange(target = <pos>, team = <team>)`,
    decompose jusqu'au scalaire dans l'en-tete du module.

    Rend `None` quand le canal n'est pas fourni (`team_synapse_positions` absent, equipe ou
    position inconnue) : le gate appelant se TAIT alors, il ne conclut jamais « hors bulle ».
    C'est la meme discipline tri-etat que `is_ranged` (#106) et `tgt_traits` (#267-r1)."""
    by_team = (ctx or {}).get(CTX_TEAM_SYNAPSE_POSITIONS)
    if by_team is None or team is None or not pos:
        return None
    import hexgeo
    for p in (by_team.get(team) or ()):
        if p and hexgeo.distance(p, pos) <= SYNAPSE_RANGE:      # GetDistance(unit, target) <= range
            return True
    return False


def _target_has_neuroparasite(ctx: "Mapping | None") -> "bool | None":
    """`HasEffect(Target@DSLSelectors+0x60, 0x4c2 = 1218 Neuroparasite, onlyActive: false, 6)`.

    `onlyActive: false` -> la PRESENCE d'une instance suffit ; le port lit les noms d'effets NON
    CONSOMMES de la cible (`tgt_effect_names`). `None` = cible non mesuree -> `None` (le gate se
    tait), jamais « pas de parasite »."""
    names = (ctx or {}).get(CTX_TGT_EFFECT_NAMES)
    if names is None:
        return None
    return NEUROPARASITE_EFFECT_NAME in names


class NornCrownEffect(BaseEffect):
    """`NornCrown` (`EffectType` 0x5d4 = 1492) -- owner-effect PERMANENT de la relique
    `NornCrown` (`TriggeredAbilityType` 0x5d7 = 1495), pose sur son porteur a l'init et PROJETE sur
    les unites AMIES `Psyker` ou `Summon` a portee de la bulle SYNAPSE de son equipe : leurs
    attaques contre une cible portant `Neuroparasite` gagnent **+`extraDmg` PLAT** (canal additif
    ATTAQUANT `DamageModifiers.Add`).

    DEUX pattes DISJOINTES, parce que le selecteur natif n'exclut PAS le porteur (cf. en-tete §2) :
      * `create_effect_damage_bonus_for_attack`      -- le PORTEUR attaque ;
      * `create_aura_attack_damage_bonus_for_ally`   -- un ALLIE selectionne attaque.
    Les agregateurs d'aura (`damage_model._apply_ally_attack_damage_auras`, prediction
    `_shared._apply_ally_attack_dmg_bonus`) excluent deja `uid == att_id` : ni trou, ni
    double-compte."""

    def _amount(self, ctx: "Mapping | None", owner_id) -> "int | None":
        """`ConfigVar(0x8 = extraDmg, GetAbilityState(effect), <config@effet+0x60>)`.

        `GetAbilityState(effect)` = l'`AbilityState` BAKE a la pose. La relique etant EQUIPEE, c'est
        l'etat **TERTIAIRE** du porteur -> foyer UNIQUE `triggered_ability_state` (#357), expose
        sous `tertiary_ability_state_of`. Canal absent (contexte offline, probe) -> repli sur les
        niveaux que l'instance porte deja, EXACTEMENT le repli documente de
        `RelicBoltPistol*Effect._ability_state` : c'est une degradation NOMMEE (elle clampe au
        dernier palier), pas un choix."""
        c = ctx or {}
        fn = c.get(CTX_ABILITY_STATE_OF)
        lvl = mult = None
        if fn is not None and owner_id is not None:
            lvl, mult = fn(owner_id, NORN_CROWN_ABILITY)
        if lvl is None:
            lvl = self.ability_level if self.ability_level is not None else self.level
            mult = self.ability_variables_multiplier
        return ability_var(NORN_CROWN_ABILITY, _VAR_EXTRA_DMG, lvl,
                           multiplier_pct=int(mult if mult is not None else 100))

    def create_effect_damage_bonus_for_attack(self, is_ranged: "bool | None" = None,
                                              has_moved: "bool | None" = None,
                                              target_traits=None,
                                              is_prediction: bool = False,
                                              is_normal_attack: "bool | None" = True,
                                              target_armor_reduced: "bool | None" = None,
                                              att_ctx=None) -> "EffectBonus | None":
        """PATTE SELF -- le PORTEUR de la relique attaque, et il est dans son propre selecteur
        (`AreFriends(Owner, Owner)` est VRAI, cf. en-tete §2).

        Gates natifs re-joues sur le porteur lui-meme :
          1. `HasTrait(Owner, Psyker) | HasTrait(Owner, Summon)` -- `tyranNeurothrope` est `Psyker`,
             mais un montage qui greffe la relique ailleurs peut ne pas l'etre ;
          2. `IsInTeamSynapseRange(Owner, <equipe du porteur>)` ;
          3. `HasEffect(Target@+0x60, Neuroparasite, onlyActive: false, Both)`.
        `get_OwnerIsCaster` est VRAI par construction sur ce canal (il n'est appele que pour les
        attaques du porteur, cf. `entities/effects/__init__.py::_attacker_effect_bonuses`).

        TRI-ETAT sur les trois canaux : un canal NON MESURE rend `None` -> aucune contribution.
        Jamais permissif."""
        c = att_ctx or {}
        own = c.get("att_id")                                # sur ce canal, l'attaquant EST le porteur
        traits = c.get("att_traits")
        if traits is None or not has_any_trait(traits, _QUALIFYING_TRAITS):
            return None                                      # HasTrait(It, Psyker) | HasTrait(It, Summon)
        if _in_team_synapse_range(c.get("att_team"), c.get("att_pos"), c) is not True:
            return None                                      # IsInTeamSynapseRange(It, Owner)
        if _target_has_neuroparasite(c) is not True:
            return None                                      # HasEffect(Target, Neuroparasite)
        amt = self._amount(c, own)
        return for_addition(True, int(amt)) if amt else None

    def create_aura_attack_damage_bonus_for_ally(self, ctx: "Mapping | None" = None) -> "EffectBonus | None":
        """PATTE AURA -- un ALLIE selectionne attaque. Mirror du `Filter` de
        `NornCrownEffect$$CreateTargetSelector`, RE-EVALUE PAR CANDIDAT (l'agregateur passe la tuile
        d'attaque evaluee, pas la position courante), puis du trigger de
        `$$CreateEffectDamageBonusForAttack`."""
        c = ctx or {}
        if c.get("att_id") == c.get("owner_id"):             # patte SELF ci-dessus
            return None
        # `AreFriends(Owner@+0x30, It@+0x68, ByCurrentTeam, anyEntity: false)`
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None
        traits = c.get("att_traits")
        if traits is None or not has_any_trait(traits, _QUALIFYING_TRAITS):
            return None                                      # HasTrait(It, Psyker) | HasTrait(It, Summon)
        # `IsInTeamSynapseRange(It@+0x68, Owner@+0x30)` -- la bulle est celle de l'equipe du PORTEUR,
        # et le sujet teste est le BENEFICIAIRE (a sa position d'attaque evaluee).
        if _in_team_synapse_range(c.get("owner_team"), c.get("att_pos"), c) is not True:
            return None
        if _target_has_neuroparasite(c) is not True:         # HasEffect(Target, Neuroparasite)
            return None
        amt = self._amount(c, c.get("owner_id"))
        return for_addition(True, int(amt)) if amt else None
