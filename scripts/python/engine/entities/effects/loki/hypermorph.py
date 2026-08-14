"""`Hypermorph` (`EffectType` 0x54d = 1357) -- le passif du summon `genesSmnAberrant`
(<< Aberrant Hypermorph >>, Genestealers) et du npc `genesNpc1Aberrant`.

i2 (`Abilities/Hypermorph_CurrentLevelDescription`) : << Gains extra Damage equal to
{healthPct}% of current Health. >> -- `gameconfig.abilities.Hypermorph.constants = {healthPct: 15}`.

⚠ NE PAS CONFONDRE avec `AberrantHypermorph` (`ActiveAbilityType` 1166), l'ACTIVE de
`genesBiophagus` qui INVOQUE ce summon (`runner/abilities/loki/summon.py`). Les deux noms se
ressemblent, les deux ids n'ont rien a voir : ici c'est le PASSIF porte par la creature invoquee
(`TriggeredAbilityType` 0x4ff = 1279).

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================

## Le TRIGGER -- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypermorphAbility$$CreateTrigger`

    <DSLTriggers+0x30>  |  ( On(0x1e = HealthChanged, ownerNeedsToBeAlive: true)
                             & DSLTriggers$$get_OwnerIsTarget )

`<DSLTriggers+0x30>` est le trigger d'INIT partage, construit une fois par
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` (LU sur CE build, pas herite d'une
citation) :

    this+0x30 = On(0x21 = AbilityInit) & <this+0x70 = YesTrigger> & get_OwnerIsActor
    this+0x38 = On(0x41)               & <this+0x70>              & get_OwnerIsActor

C'est donc un passif d'**INIT** (canal `ABILITY_INIT_OWNER_EFFECTS`), PLUS un re-declenchement a
chaque changement de PV **du porteur** (`get_OwnerIsTarget` = `AreEqual(Owner@DSLSelectors+0x30,
Target@DSLSelectors+0x60)`).

## Le BEHAVIOUR -- `...HypermorphAbility$$CreateBehaviour`

    RemoveEffect( Owner@DSLSelectors+0x30, Nullable<EffectType>(0x54d), replaceable: null )
  + AddDynamicStatModifierEffectToOwner( effectType = 0x54d, statType = 0 = Attack,
                                         turns = null -> PERMANENT, isHidden = false )

(joints par `IdunBattle.DSL.AbilityBehaviour$$op_Addition`). Le couple RETIRE-puis-REPOSE est le
mecanisme de RECALCUL : la magnitude etant une fonction des PV COURANTS, le natif la reevalue a
chaque `HealthChanged` en detruisant l'entite-effet et en la reconstruisant.

Cote port, la magnitude est lue A LA LECTURE (`applied_stat_mods(stats_ctx)`, forme OVERRIDE
d'`ApplyModification`) et re-posee par le driver `runner/operations/refresh_effects.py`
(`ValueModification.Modify` = replace par-source) : meme observable, sans modeliser la
destruction/reconstruction de l'entite-effet.

## La MAGNITUDE -- `IdunBattle.Entities.Effects.Loki.HypermorphEffect$$GetDynamicStatModificationAmount(owner, target, effect)`

    hp   = UnitExtensions$$GetStat(target, 5 = Health, 0 = Current)
    pct  = Fix64.Round( Fix64(GetNumberConstant(0x4f = healthPct)) / 100 * 100, mode 0 ) / 100
    return Nullable<int>( (int) ( Fix64(hp) * pct ) )       // op_Explicit = FLOOR

`target` == le porteur : `AddDynamicStatModifierEffectToOwner` met `Owner@0x30` en source ET en
cible (cf. `IdunBattleLogic.Entities.DSLBehaviors$$AddDynamicStatModifierEffectToOwner`, qui lit
DEUX FOIS `<DSLSelectors+0x30>`). Signature LUE dans `frida/methods.tsv` :
`owner:IEntity, target:IEntity, effect:IEntity -> System.Nullable<System.Int32>`.

⚠ **LE `-1` DE FIX64 N'EST PAS UNE APPROXIMATION, C'EST LE RESULTAT NATIF.** `Fix64` est un
Q31.32 : `15/100` s'y ecrit `644245094 / 2^32` = `0.14999999997671694`, STRICTEMENT sous 0,15
(`op_Division` = round-half-up sur un quotient accumule a 2^-33, cf. `services/fix64.py`). Le
produit final passe par `op_Explicit` = **floor**, donc des que `hp * healthPct / 100` tombe sur
un ENTIER, le natif rend **une unite de moins** :

    hp = 2000, healthPct = 15  ->  exact 300      natif 299
    hp = 1000, healthPct = 15  ->  exact 150      natif 149
    hp = 1234, healthPct = 15  ->  exact 185,1    natif 185

Le round intermediaire (`/100 * 100` puis `Round`) RATTRAPE la premiere division (14,99999999 ->
15,0 exact) mais la SECONDE division n'a pas de rattrapage. Modeliser ce calcul en float ou en
`Fraction` exacte donnerait 300 au lieu de 299 -- c'est exactement pourquoi le mirror passe par
`engine.services.fix64` (raw int, precision arbitraire) et non par une regle de trois.

## La CLASSE d'effet -- `IdunBattle.Entities.Effects.Loki.HypermorphEffect$$.ctor`

`AStatModifierEffect(AbilityOrEffect(...), 0, 0, isHidden: true, ...)` -- famille
`ADynamicStatModifierEffect` (elle surcharge `GetDynamicStatModificationAmount`), donc le stat
modifie n'est PAS un champ de la classe : il vient du `StatModifierComponent` de l'entite-effet,
rempli par l'argument `statType` du behaviour (ici `0 = Attack`), cf.
`IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat`. Le port le declare
donc en dur dans `get_stat_modification_stat`, comme les autres membres du mold.
"""
from __future__ import annotations

import engine.services.fix64 as _fx      # module FEUILLE (aucun import du paquet) -> pas de cycle
from ..base import BaseEffect
from ..magnitude import ability_var
from ...stats import StatPart, StatType

#: `GetNumberConstant(0x4f)` -> `gameconfig.abilities.Hypermorph.constants["healthPct"]`.
HYPERMORPH = "Hypermorph"
HEALTH_PCT_KEY = "healthPct"


def hypermorph_extra_damage(hp: int, health_pct: int) -> int:
    """Mirror 1:1 du corps Fix64 de `HypermorphEffect$$GetDynamicStatModificationAmount`.

        pct = Round(Fix64(health_pct) / 100 * 100, mode 0) / 100
        return (int)(Fix64(hp) * pct)                       # op_Explicit = floor

    Isole du reste pour etre confrontable seul (le quirk `-1` decrit en tete de module est
    entierement contenu ici)."""
    hundred = _fx.from_int(100)
    pct = _fx.div(_fx.from_int(int(health_pct)), hundred)        # Fix64.op_Division
    pct = _fx.mul(pct, hundred)                                  # Fix64.op_Multiply
    pct = _fx.round_raw(pct, 0)                                  # Fix64.Round(value, 0 = ToEven)
    pct = _fx.div(pct, hundred)                                  # Fix64.op_Division
    return _fx.to_int(_fx.mul(_fx.from_int(int(hp)), pct))       # op_Multiply puis op_Explicit


class HypermorphEffect(BaseEffect):
    """`Hypermorph` (0x54d = 1357) -- stat-mod **Attack(0) POSITIF et PERMANENT** pose sur le
    porteur a l'init de son passif, dont la magnitude vaut `healthPct %` de ses PV COURANTS
    (recalculee a chaque `HealthChanged`). Cf. la RE complete en tete de module."""

    #: cle de source `ChangeStat` -- `None` = instance SEEDEE, donc pilotee par le driver
    #: `refresh_stat_modifier_effects` (qui re-derive la magnitude quand les PV bougent).
    stat_mod_source = None

    def get_stat_modification_stat(self) -> "int | None":
        """`statType` du `StatModifierComponent` de l'entite-effet = l'argument `0 = Attack` de
        l'`AddDynamicStatModifierEffectToOwner` du behaviour. C'est lui que
        `refresh_stat_modifier_effects` lit pour savoir QUEL stat reverter."""
        return int(StatType.ATTACK)

    def applied_stat_mods(self, stats_ctx) -> "list":
        """Forme OVERRIDE d'`ApplyModification` -- la magnitude se lit SUR LE PORTEUR :

            (int)( Fix64(GetStat(target, 5 Health, 0 Current)) * Round(pct/100*100, 0)/100 )

        `stats_ctx` absent, PV nuls ou constante illisible -> `[]` : la magnitude contextuelle
        n'est PAS devinee (meme degradation fidele que `ReinforcedHiveNodeExtraArmorEffect`)."""
        if stats_ctx is None:
            return []
        pct = ability_var(HYPERMORPH, HEALTH_PCT_KEY, is_constant=True)
        if not pct:
            return []
        hp = int(stats_ctx.get_stat(int(StatType.HEALTH), int(StatPart.CURRENT)) or 0)
        if hp <= 0:
            return []
        amt = hypermorph_extra_damage(hp, int(pct))
        return [(int(StatType.ATTACK), int(amt))] if amt else []

    def reverted_stats(self) -> "list":
        """`AStatModifierEffect$$RevertModification` -- meme stat que l'apply (part 6). C'est aussi
        ce que retire la feuille `RemoveEffect(Owner, 0x54d)` de `$$CreateBehaviour` avant chaque
        re-pose."""
        return [StatType.ATTACK]
