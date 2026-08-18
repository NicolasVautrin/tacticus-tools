"""`ShockAssault_Buff` (1000 = 0x3e8) -- le buff « +Damage for this attack » que le PASSIF
`ShockAssault` (`TriggeredAbilityType` 0x3ea = 1002) de `ultraInceptorSgt` (« Bellator ») pose sur
ses Inceptors (`ultraSmnInceptor`) avant de les faire attaquer.

i2 : « Whenever Bellator attacks, any Inceptor adjacent to him also attacks eligible targets,
dealing +{[extraDmg]} Damage for this attack. »

ARTEFACT NATIF -- classe d'effet DEDIEE, `IdunBattle.Entities.Effects.Loki.ShockAssaultBuffEffect`,
qui derive de `IdunBattle.Entities.Effects.StaticStatModifierEffect` (`classes.tsv`) et n'AJOUTE
qu'un membre : `$$CreateRemoveEffectTrigger`. Le ctor est le corps FONDU (IL2CPP deduplique les
`.ctor` triviaux -- Ghidra le nomme `...Loki.SwarmHitReductionEffect$$.ctor`), donc SANS aucun
argument fige : ni `AbilityOrEffect` source, ni stat, ni magnitude. **Le nom du ctor ne fait PAS
l'identite de classe** : celle-ci est tranchee au slot `Il2CppClass*` charge par la fabrique
`IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_26`, dont
c'est l'UNIQUE xref sur tout le binaire -> classe PROPRE a l'id 1000, partagee avec aucun autre.

LA POSE (`IdunBattleLogic.Entities.Abilities.Active.Loki.ShockAssaultAbility$$CreateBehaviour`) --
lue au decompile, NON PORTEE ici (l'ability 1002 est un item distinct, cf. la docstring de
`DeathFromAboveAbility`) :

    v   = GetVariableForLevel(config, 8 = extraDmg, <AbilityState du PASSIF>, fallback = 0)
    sel = GetAffectedUnits(Owner@DSLSelectors+0x30)
    AddStaticStatModifierEffect( targets    = sel,
                                 effectType = 0x3e8 = 1000,
                                 statType   = 0    = ATTACK,
                                 amount     = Formulas.Get(v),
                                 turns      = NULL,
                                 isHidden   = true )
    & PerformAIAbility( sel, unit => UnitExtensions.GetNormalAttackType(unit), null,
                        <overrideMovement>, <utilityEntity>, customUtility = b__1_1 )

`GetAffectedUnits(origin)` = `EntitiesWithoutEffects( Filter( AdjacentUnits(origin, unique: 1,
sel: 3), IsUnitWithVisualId(ActiveTarget@DSLSelectors+0x68, GetStringConstant(config, 0 = unitId))
& AreFriends(Caster@DSLSelectors+0x48, ActiveTarget@+0x68) ), [0x4b9 = 1209 AttemptedPossession_Possessed] )`
-- les Inceptors AMIS adjacents au Bellator qui ne sont pas possedes.

STAT ET MAGNITUDE VIENNENT DU COMPOSANT, PAS DE LA CLASSE.
`IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$StatModifierBuilder` ecrit
`EffectComponent+0x10 = statType`, `+0x14 = amount`, `+0x1d = isHidden`, et BAKE l'`AbilityState`
du poseur en `+0x18..+0x38` ; `IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat`
relit `+0x10` et `IdunBattle.Entities.Effects.StaticStatModifierEffect$$GetStatModificationAmount`
relit `+0x14`. Or `decisionView.effects` n'expose NI l'un NI l'autre -> un 1000 deja pose au
chargement d'un `State` arriverait sans stat-modification declaree, et sa contribution resterait
dans le RESIDU OPAQUE (`CAPTURED_SOURCE`) de `seed_unit_stats` : attribuee a AUCUNE source, donc
**non retirable** (#118). C'est exactement ce que cette classe ferme -- meme motif que
`SereneUnifierStormOfFireEffect` / `UnbreakableDuty*Effect` (case-371), a ceci pres qu'ici le
retrait n'est pas un TIMER (`turns = NULL` => permanent) mais un TRIGGER :

    `ShockAssaultBuffEffect$$CreateRemoveEffectTrigger` = `On(0xa, ownerNeedsToBeAlive: 1)
                                                          & get_OwnerIsCaster`

soit `EventTriggerType.AttackDamageAttack` : le buff dure jusqu'a la CLOTURE de l'attaque de son
porteur -- « for this attack » de l'i2. Porte cote runner par
`engine/runner/operations/triggers/loki/shock_assault.py`.

MAGNITUDE : `extraDmg` (`AbilityVariableType` 8) est la SEULE variable de `ShockAssault` au
gameconfig, et elle figure dans son `variablesAffectedByRarityBonus` -> scalee par
l'`AbilityVariablesMultiplierPercentage` du POSEUR (mirror
`IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel` : index
`Idun.Shared.Level$$ToZeroBasedIndex` clampe, puis `Round(mult/100 x base)` SSI la variable est
dans la liste). `ShockAssault` est un PASSIF -> le niveau est `ability_level` (slot passif),
JAMAIS `active_ability_level` -- le natif passe l'`abilityState` que `UnitFactory$$Build` a fabrique
pour les passives.

CROSS-UNITE, ET RESOLU : porteur (le summon) != source (le Bellator). Le port ne lit PAS le niveau
du porteur -- `engine/entities/effects_state.py::baked_ability_state` resout l'etat d'ability par
`captured["source"]` (= `EffectComponent.SourceUnit @+0x10`), mirror du bake natif. La magnitude est
donc celle du Bellator des lors que celui-ci est dans le snapshot ; le repli porteur ne joue que si
la source est absente/non chargee.
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var

_ABILITY_ID = "ShockAssault"


class ShockAssaultBuffEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.ShockAssaultBuffEffect` (0x3e8 = 1000) -- +`extraDmg` sur
    ATTACK, PERMANENT au sens du timer (`turns = NULL`), retire par le trigger
    `On(AttackDamageAttack) & OwnerIsCaster` de son porteur.

    Jumeau structurel de `SereneUnifierStormOfFireEffect` (meme feuille de pose, meme statType, meme
    variable, meme canal de revert `AStatModifierEffect$$RevertModification`) ; il en differe par
    l'identite de classe (native DEDIEE ici, generique la-bas) et par le cycle de vie (trigger vs
    timer)."""

    def get_stat_modification_stat(self) -> int | None:
        """`AStatModifierEffect$$GetStatModificationStat` = `StatModifierComponent+0x10` -- lu au
        canal capte, repli sur le litteral `0 = ATTACK` du `CreateBehaviour` (meme valeur : le natif
        n'a qu'UNE feuille de pose pour 1000). Jumeau de `captured_stat_mod_amount` sur l'autre champ
        de la paire native."""
        native = self.captured_stat_mod_stat()
        return native if native is not None else 0

    def get_stat_modification_amount(self) -> int | None:
        """`StaticStatModifierEffect$$GetStatModificationAmount` = `StatModifierComponent+0x14`.

        On lit d'ABORD ce champ tel que la capture le publie (`captured_stat_mod_amount`) : c'est
        litteralement ce que le natif relit, et c'est la SEULE lecture exacte ici -- la feuille de
        pose passe `source = null`, donc `EffectComponent.SourceUnit` (le canal `captured["source"]`
        de `baked_ability_state`) designe le PORTEUR, jamais le Bellator. MESURE 2026-08-01 : natif
        `Amount = 499` (= `extraDmg[L50] x 180 %`), re-derivation par le porteur `extraDmg[1] = 5`.

        REPLI, quand le canal `statMod` est absent (pose OFFLINE, capture antérieure au capteur) :
        `ConfigVar(8 = extraDmg)` indexe par `ability_level` -- `ShockAssault` est un PASSIF, donc
        le slot passif, JAMAIS `active_ability_level`. Ce repli est EXACT si l'`AbilityState` porte
        celui du poseur, APPROCHE sinon (sous-attribution : le residu opaque absorbe l'ecart,
        jamais une sur-attribution)."""
        native = self.captured_stat_mod_amount()
        if native is not None:
            return native
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var(_ABILITY_ID, "extraDmg", lvl,
                           multiplier_pct=self.ability_variables_multiplier)
