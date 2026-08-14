"""`AllIsDust` -- passif `TriggeredAbilityType` 0x486 = **1158**, owner-effect `EffectType` 0x4a5 =
**1189** (#1052).

PORTEURS (gate de confrontabilite, ventiles) :
  * `thousNpc3RubricMarine` -- **npc**, `units.npc[].stats[]` present -> confrontable par le CHEMIN
    DE STATS EXPLICITE (`rl_duel build --explicit-stats thousNpc3RubricMarine:3`, case-92 Sec.5bis
    recours 4). C'est le MIRROR du porteur, pas un montage : il arrive avec SES stats, SES traits,
    SES armes ;
  * `thousSmnRubricMarine` -- **summon**, `visualId == thousNpc3RubricMarine` (le jumeau npc
    ci-dessus). Son unique invocateur au gameconfig est `EnvFactionSummons:ThousandSons`
    (`constants.unitId = thousSmnRubricMarine`, `nrOfSummons = 2`), une ability d'ENVIRONNEMENT du
    live-event *Faction War* (`liveEvents.idunLiveEventConfigs[].factionWarData.factions[].abilityId`)
    -- elle n'est portee par AUCUNE unite, ce qui explique le `S?` de l'audit : son graphe de summon
    ne balaie que les abilities DES UNITES.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.AllIsDustAbility$$CreateTrigger` -- INVISIBLE des
tables (corps DEDUPLIQUE par ICF avec `...Active.Loki.SummaryExecutionAddBaseEffectAbility$$
CreateTrigger`, appartenance etablie slot a slot dans le bloc `methodPointers` du PE) :

    return <DSLTriggers+0x30>          # = `On(0x21 = AbilityInit) & get_OwnerIsActor`

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.AllIsDustAbility$$CreateBehaviour` :

    AddEffect( 0x4a5 = 1189 AllIsDust, AbilityStateReference,
               targets = Caster@<DSLSelectors+0x48>, turns = null )

-> owner-effect PERMANENT pose a l'init : canal `ABILITY_INIT_OWNER_EFFECTS` (factory.py).

`IdunBattle.Entities.Effects.Loki.AllIsDustEffect$$GetPierceStatModifier` :

    Sum( StatAmount(Caster@+0x48, 0x1a = ExtraPierce,       0x5 = Modification, null, 0),
         If( IsMeleeAttack,
             StatAmount(Caster@+0x48, 0x15 = ExtraPierceMelee,  0x5 = Modification, null, 0),
             StatAmount(Caster@+0x48, 0x16 = ExtraPierceRanged, 0x5 = Modification, null, 0) ) )

`IdunBattle.Entities.Effects.Loki.AllIsDustEffect$$CreatePiercingBonusForAttack` :

    seuil   = ConfigConst(0x49 = pierceRatio, config@+0x60)              # = 35
    total   = Sum( AttackPiercingRatio(),
                   GetPierceStatModifier(),
                   CasterEffectPierceAddition(excludedEffectType = 0x4a5) )
    trigger = get_OwnerIsTarget op_BitwiseAnd NOT( AmountIsGreater(total, seuil) )
    montant = Negative( Subtract(total, <DSLFormulas+0x20> = Direct(1)) )
    -> EffectBonus.ForPiercing(trigger, montant)          # axe PERCAGE @+0x20, PAS le scalaire degat

i2 : « Attacks against this unit with 35% pierce ratio or less are treated as having a 1% pierce
ratio. » -- le `-(total - 1)` ramene EXACTEMENT le percage effectif a 1, puisque le natif somme
ensuite `base + extra + extraDir + am + dm` dans
`IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio`.

⚠ `AmountIsGreater` est STRICT (classe native distincte d'`AmountIsEqualOrGreater`), et il est NIE :
le gate est donc `total <= 35`. « or less » de l'i2 concorde.

⚠ **DEUX BASES DE PERCAGE DIFFERENTES, ET C'EST LU, PAS DEDUIT.** Le terme `AttackPiercingRatio()`
(`IdunBattle.Entities.Formulas.AttackPiercingRatioFormula$$Calculate`) rend le `PiercingRatio` BRUT
du profil de degat (`profil+0x14`), alors que `GetAttackPiercingDamageRatio` utilise
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetPiercingRatio(profil,
traits)`, qui AJOUTE un bonus global quand le profil porte le `DamageTrait` 3 et que l'attaquant
porte le trait `0x3e9` ou `0x3f8`. Le gate d'`AllIsDust` s'evalue donc sur la base BRUTE. Non
modelise ici (le port ne porte pas ce bonus de trait sur la base non plus) -- inerte tant que les
deux coincident.

CE QUE LE PORT NE VOIT PAS (et le DIT au lieu de le deviner) : `CasterEffectPierceAddition` est une
boucle NATIVE sur TOUS les effets de l'etat (slot `IEffect.PiercingBonusForAttack` = 24, table
`data/symbols/<build>/metadata/interface_slots.tsv`), l'effet 1189 excepte. Cote port, la somme est
celle des effets de l'ATTAQUANT (`piercing_bonus_from_effects`, meme mirror de
`BaseEffect$$PiercingBonusForAttack`) posee par les DEUX call-sites dans `attacker_ctx
["effect_pierce_addition"]` ; les contributions d'effets portes par d'AUTRES unites que l'attaquant
ne sont pas dans cette somme. Cle ABSENTE -> le gate se FERME (aucun bonus rendu), jamais un 0
devine.
"""
from __future__ import annotations

from typing import Mapping

from ....services.effect_bonus import EffectBonus, for_piercing
from ..base import BaseEffect
from ..magnitude import ability_var

#: Nom gameconfig du passif (cle d'`ABILITY_INIT_OWNER_EFFECTS` et de `units.abilities`).
ABILITY_ID = "AllIsDust"
#: `ConfigConst(0x49 = pierceRatio, config@+0x60)` -- constante, pas une variable de niveau.
PIERCE_RATIO_KEY = "pierceRatio"
#: `<DSLFormulas+0x20>` = `Direct(1)`, LU dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor` (meme
#: singleton que celui deja cite par `entities/triggers.py`).
DIRECT_ONE = 1


def pierce_ratio_threshold() -> int:
    """`ConfigConst(0x49 = pierceRatio)` = `units.abilities.AllIsDust.constants.pierceRatio` (35)."""
    return int(ability_var(ABILITY_ID, PIERCE_RATIO_KEY, is_constant=True) or 0)


class AllIsDustEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.AllIsDustEffect` (effet **1189 = 0x4a5**) -- cf. l'en-tete.

    OBSERVABLE : toute attaque contre le PORTEUR dont le percage total vaut `pierceRatio` (35) ou
    moins est resolue avec un percage de **1**. Au-dessus du seuil, l'effet est un no-op strict.

    `attacker_ctx` porte les DEUX termes que la formule native lit sur le CASTER et que ce slot
    d'interface ne recoit pas autrement (memes cles / meme semantique sur les DEUX faces, cf.
    `runner/damage_model.defender_modifiers` et `playbook/prediction/_shared`) :
      * `extra_pierce`            -> `StatAmount(Caster, 0x1a = ExtraPierce, Modification)` ;
      * `extra_pierce_dir`        -> `StatAmount(Caster, 0x15|0x16, Modification)` selon `is_melee` ;
      * `effect_pierce_addition`  -> `CasterEffectPierceAddition(excluded = 0x4a5)`.
    Une seule manquante -> la conjonction se FERME (retour None), jamais un terme devine."""

    def create_piercing_bonus_for_attack(self, damage_profile: str | None = None,
                                         is_melee: bool | None = None,
                                         attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        import gameconfig as _GC
        ac = attacker_ctx or {}
        # `AttackPiercingRatio()` = `profil+0x14` BRUT (cf. l'en-tete). Profil non threade -> le
        # noeud natif rendrait 0 sur un `Nullable<DamageProfileType>` vide, mais offline « pas de
        # profil » veut dire « non mesure » : on se TAIT plutot que de decreter un percage nul, qui
        # ouvrirait le gate `total <= 35` a coup sur.
        if not damage_profile:
            return None
        base = int((_GC.damage_profile(damage_profile) or {}).get("PiercingRatio") or 0)
        # `GetPierceStatModifier()` -- les DEUX `StatAmount` sur le CASTER. Le `If(IsMeleeAttack, ..)`
        # exige la nature du coup : tri-etat, `None` => on se tait (la branche n'est pas choisie).
        if is_melee is None:
            return None
        for key in ("extra_pierce", "extra_pierce_dir", "effect_pierce_addition"):
            if ac.get(key) is None:
                return None                       # terme NON MESURE -> gate ferme
        stat_mod = int(ac["extra_pierce"]) + int(ac["extra_pierce_dir"])
        total = base + stat_mod + int(ac["effect_pierce_addition"])
        # `NOT AmountIsGreater(total, seuil)` -- STRICT et NIE, donc `total <= seuil`.
        if total > pierce_ratio_threshold():
            return None
        # `Negative(Subtract(total, Direct(1)))`. Le natif rend l'`EffectBonus` MEME quand le montant
        # est nul (`total == 1`) : on le rend aussi, un 0 sur l'axe percage etant un no-op exact.
        # `owner_is_caster=False` : le trigger est `get_OwnerIsTarget` (l'effet vit sur la VICTIME et
        # corrige le percage de QUI l'attaque) -- meme face que `Supercharge_ExtraPiercingEffect`.
        return for_piercing(False, -(total - DIRECT_ONE))
