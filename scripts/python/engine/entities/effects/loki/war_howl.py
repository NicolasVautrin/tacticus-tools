"""`WarHowl_ExtraDamage_Unstoppable` (0x4c6 = 1222) — le buff pose par l'ACTIVE `WarHowl`
(`ActiveAbilityType` 0x452 = 1106) de `spaceBlackmane` << Ragnar >>. case-366-r1.

## UNE classe native, UN `EffectType` — tranche par le SLOT, pas par le nom

`probe_366_inventaire_effets_forme_b.py --csv` rend pour 1222 le slot `Il2CppClass*` `0x1833908e8`,
qu'AUCUN autre des 96 ids de la forme B ne partage ; et `IdunBattle.Entities.Effects.Loki.
WarHowl_ExtraDamage_UnstoppableEffect$$.ctor` n'a **UN SEUL appelant** dans tout le binaire,
`IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_240`
(une fabrique = un enregistrement) -> aucun jumeau parmi les 607, formes A et B confondues.

## SOURCE DE CONFIG — l'ability ACTIVE 1106, pas une passive

`IdunBattle.Entities.Effects.Loki.WarHowl_ExtraDamage_UnstoppableEffect$$.ctor` :

    mov edx, 0x452                                          ; 1106
    call IdunBattle.Core.AbilityOrEffect$$op_Implicit        ; surcharge ACTIVE (celle qui prend
                                                            ;  un `ActiveAbilityType`)
    call IdunBattle.Entities.Effects.BaseEffect$$.ctor(this, abilityOrEffect,
                                                       hasAutomaticActivation: 1)

La surcharge d'`op_Implicit` est tranchee par son ADRESSE (`IdunBattle.Core.AbilityOrEffect.
op_Implicit(activeAbility:ActiveAbilityType)`), pas a l'oeil : les quatre surcharges portent le
meme nom. => la config lue est `abilities.WarHowl`, et le niveau qui indexe ses variables est le
niveau d'ability **ACTIVE** de la SOURCE.

## POSE — `WarHowlAbility$$ExecuteBehaviour` (PORTEE depuis #585)

MIRROR du decompile (`IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$
ExecuteBehaviour`) :

    targets = Caster
            + UnitsWithoutTrait( UnitsWithoutRangedWeapons(
                  Friends(Caster, <pool partage> - Caster,
                          UnitSelectionType.OnlyAliveAndTargetable) ),
                  trait = 0x2 = UnitTrait.Summon,
                  UnitSelectionType.OnlyAliveAndTargetable )

    AddEffect( 0x4c6 = 1222,
               abilityState = CreateSnapshot(<abilityState du cast>),
               source  = Caster,
               targets = <ci-dessus>,
               turns   = Get(1) )

`WarHowlAbility$$OtherBuffTargets` est le MEME selecteur sans le `+ Caster` (il sert la face
DECISION). Aucune restriction de faction ni de distance : **tout ami melee non-Summon** recoit le
buff, Space Wolf ou non. `turns = Get(1)` -> `Effect_RemainingTurns: 1`, et l'effet DISPARAIT apres
un seul `endturn` : il ne vaut que pour le tour du cast.

⚠ Le `UnitSelectionType.OnlyAliveAndTargetable` ecrit deux fois ci-dessus **MORD** : il ecarte une
unite en DEEP STRIKE (`UnitFlag.Untargetable`) que tous les autres filtres retiennent. C'est ce qui
explique la mesure historique « `spaceRockfist` n'est pas buffe » -- et NON ses armes, qui sont
melee. Le port est `engine/runner/abilities/spacewolves.py::war_howl_other_buff_targets` ;
mesure des deux regimes : `docs/rl/case-585-war-howl-pose.md` §3.

## TROIS ARTEFACTS, TROIS CANAUX DISTINCTS

### 1. DEGAT — `CreateEffectDamageBonusForAttack`

    EffectBonus.ForAddition( get_OwnerIsCaster & IsMeleeAttack & IsNormalAttack,
                             ConfigVar(0x08 = extraDmg, GetAbilityState(effect), config@+0x60) )

TROIS noeuds de trigger, tous portes : `get_OwnerIsCaster` est deja porte par le canal (ces effets
ne sont interroges que sur l'ATTAQUANT), `IsMeleeAttack` par `is_melee_attack(is_ranged)` (tri-etat
#106 : nature non prouvee => gate FERME) et `IsNormalAttack` par le parametre du meme nom.

### 2. CHANCE DE CRIT — `CreateCritChanceBonus`

    EffectBonus.ForAddition(
        get_OwnerIsCaster & IsMeleeAttack & IsNormalAttack
        & AmountIsGreaterThanZero( StatAmount(Caster, 0x9 = CriticalChance,
                                              StatPart.Current, null, UnitSelectionType.Any) ),
        ConfigVar(0x41 = extraCritChance, GetAbilityState(effect), config@+0x60) )

QUATRE noeuds : les trois du canal DEGAT **plus** un gate `AmountIsGreaterThanZero`. Il est
LOAD-BEARING et non decoratif : sans lui, un porteur a `GetStat(9) == 0` verrait
`could_crit(0 + extraCritChance, GetStat(10))` passer a VRAI et se mettrait a criter, ce que le
natif ne fait jamais (`IdunBattle.Core.Services.DamageCalculations$$CouldCrit` reclame
`GetStat(9) > 0`, et le bonus d'effet n'y entre pas). C'est le bras `--crit 0,700` du probe.

L'entite `Caster` est le champ `+0x48` de `IdunBattleLogic.Entities.DSLSelectors` (tranche par
recoupement : `HeraldOfTheApocalypse_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` =
`OwnerIsTarget & IsUnit(<0x48>)` -> l'ATTAQUANT ; `SagaOfTheWarriorBorn_KillAbility$$CreateTrigger`
lit `HasTrait(<0x60>, Hero)` = la CIBLE ; `...$$CreateBehaviour` pose `source = <0x30>` = l'Owner).
Sous `get_OwnerIsCaster`, `Caster` == l'attaquant, dont `_crit_params` a le `UnitContext`.

### 3. TRAIT — `ApplyInternal` / `RevertInternal`

    ApplyInternal (this, owner, target, effect)
        -> <IOperationProcessor @this+0x68>.<slot 0x26>(target, 0x412, isTemporary: 1)
    RevertInternal(this, owner, target, effect)
        -> <IOperationProcessor @this+0x68>.<slot 0x27>(target, 0x412, isTemporary: 1)

Les deux slots sont resolus par la meme interface (`FUN_1800103b0` = dispatch d'interface : offset
d'interface a `klass+0xb0`, slot ajoute, saut dans la vtable a `klass+0x138`) et leur signature
`(target, trait, isTemporary)` est celle de `Core.Services.OperationProcessor$$AddTrait` /
`$$RemoveTrait` -> `IdunBattle.Operations.AddTraitOperation$$Execute` /
`IdunBattle.Operations.RemoveTraitOperation$$Execute`. `0x412 = 1042 = UnitTrait.Unstoppable`
(qualifie : 1042 vaut `ActiveAbilityType.FlailSwing` et `EffectType.HailOfLivingAmmunition_ExtraHits`
dans d'AUTRES enums). `isTemporary: 1` -> la collection `BaseUnitComponent+0x48`, et aucun evenement
n'est diffuse (`AddTraitOperation$$Execute` retourne avant la publication quand `isTemporary`).

MESURE live (`combatSnapshot.units[].traits`, l'invoke de `UnitExtensions$$HasTrait` par valeur
d'enum) : avant cast `u81 = [16, 26, 1014, 1043, 1061]`, apres cast `[16, 26, 1014, **1042**, 1043,
1061]` ; idem `u85`. `u83` (`spaceWulfen`) porte deja 1042 au kit -> inchange. Le port LIT donc les
deux sens par le substrat d'entite (`entity_trait_names`, seede par `snapshot._load_unit_traits`) :
c'est ce meme substrat que consomme l'exemption de mouvement
`services/static_battle_rules.py::_MOVEMENT_EXEMPT_TRAIT_IDS` (Mounted/Vehicle/Unstoppable, mirror
`StaticBattleRules.Effect$$NotBlockingMovementOfTraits`), le SEUL consommateur natif du trait
(case-205 §1.5). La face POSE (accorder/retirer le trait OFFLINE) est PORTEE depuis #585 :
`applied_traits()` ci-dessous la DECLARE, `runner/operations/traits.py` l'EXECUTE (mirrors
`AddTraitOperation$$Execute` / `RemoveTraitOperation$$Execute`), et trois points la cablent --
`AddEffectOperation.execute` (apply), `remove_effect_instance` (retrait explicite),
`EndTurnOperation` (expiration). Cf. `docs/rl/case-585-war-howl-pose.md` §5.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition
from ...traits.unit_trait import UnitTrait          # `0x412 = 1042 = Unstoppable` de `ApplyInternal`
from ..base import BaseEffect, is_melee_attack, owner_is_caster
from ..magnitude import ability_var

_ABILITY_ID = "WarHowl"            # ActiveAbilityType 0x452 = 1106 (active, spaceBlackmane)


class WarHowlExtraDamageUnstoppableEffect(BaseEffect):
    """`WarHowl_ExtraDamage_Unstoppable` (0x4c6 = 1222) — +extraDmg et +extraCritChance sur les
    attaques normales de MELEE du porteur, pour UN tour.

    NIVEAU / MULTIPLICATEUR — les deux viennent de l'`AbilityState`, et le porteur n'est PAS
    toujours la source. `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`
    (foyer UNIQUE des quatre accesseurs de variable) lit **les deux** sur son argument
    `abilityState` : l'index par `Idun.Shared.Level$$ToZeroBasedIndex(abilityState)` (champ +0x0) et,
    pour toute variable listee dans `variablesAffectedByRarityBonus` (`config+0x28`), le facteur
    `Fix64(abilityState+0x4) / 100` avec `Round(AwayFromZero)`. Et l'`abilityState` d'un effet est
    `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` =
    `IdunBattleLogic.Entities.DSLSelectors$$AbilityStateFromEffect(<noeud EFFET>)`, c.-a-d. celui
    BAKE A LA POSE, donc celui de la **SOURCE**.

    Le port, lui, seede depuis le PORTEUR (`EffectsState.seed`, cle par porteur) — residu PARTAGE
    par les 135 entrees d'`EFFECT_CLASSES` (#382), pas un choix de cette classe. Il MORD ici, parce
    que `extraDmg` EST dans `variablesAffectedByRarityBonus` et que les multiplicateurs different :
    MESURE live (seed 777, MC1_67, rank 17) `spaceBlackmane` = **200**, `spaceWulfen` /
    `spaceHound` = **180** -> `extraDmg[50]` vaut 886x2.00 = **1772** cote natif contre
    round(886x1.80) = **1595** cote port sur un allie. Le probe le mesure explicitement (bras
    `SRCMULT`) et l'annule dans le bras de reference (`--unit-stat
    spaceBlackmane:AbilityVariablesMultiplierPercentage=180`). L'axe CRIT en est EXEMPT :
    `extraCritChance` n'est pas dans `variablesAffectedByRarityBonus`.

    Le NIVEAU, lui, est ecrit `active_ability_level` faute de mieux : `EffectsState.seed` ne propage
    a ce jour que `ability_level` (= `unitConfig.passiveAbilityLevel`), donc `active_ability_level`
    vaut None sur tout effet SEEDE et le repli s'applique. Sous `buildNormalizedBC` les deux valent
    50, l'ecart est nul ; l'idiome reste celui des 18 autres classes qui lisent une ability ACTIVE
    (`damage_reduction.py`, `extra_damage.py`, `imperative.py`, ...)."""

    def _level(self) -> "int | None":
        """`Level$$ToZeroBasedIndex(abilityState)` : la variable est celle d'une ability ACTIVE."""
        if self.active_ability_level is not None:
            return self.active_ability_level
        return self.ability_level if self.ability_level is not None else self.level

    def applied_traits(self) -> "list":
        """MIRROR de `IdunBattle.Entities.Effects.Loki.WarHowl_ExtraDamage_UnstoppableEffect$$
        ApplyInternal` / `$$RevertInternal` :

            ApplyInternal (this, owner, target, effect)
                -> <IOperationProcessor @this+0x68>.<slot 0x26>(target, 0x412, isTemporary: 1)
            RevertInternal(this, owner, target, effect)
                -> <IOperationProcessor @this+0x68>.<slot 0x27>(target, 0x412, isTemporary: 1)

        Les deux slots sont resolus par la MEME interface (`FUN_1800103b0` = dispatch d'interface :
        offset d'interface a `klass+0xb0`, slot ajoute, saut dans la vtable a `klass+0x138`) et leur
        signature `(target, trait, isTemporary)` est celle de `IdunBattle.Core.Services.
        OperationProcessor$$AddTrait` / `$$RemoveTrait`. `0x412 = 1042 = UnitTrait.Unstoppable` --
        QUALIFIE : 1042 vaut aussi `ActiveAbilityType.FlailSwing` et
        `EffectType.HailOfLivingAmmunition_ExtraHits` dans d'AUTRES enums.

        L'i2 l'apparie nom pour nom : « he and all friendly Characters that don't have a normal
        ranged attack gain <Unstoppable> until the end of this turn ».

        `is_temporary = True` : cote natif il choisit la collection `BaseUnitComponent+0x48` et
        SUPPRIME la diffusion d'evenement (`AddTraitOperation$$Execute` retourne avant la
        publication). Cote port les deux collections sont fondues (cf. `operations/traits.py`) --
        le drapeau est transporte, sans observable distinct.

        `AddDerivedAbilities` (l'etage qui suit le `coll.Add` natif) est un **NO-OP pour 1042** :
        `0x412` n'est cle d'aucun des deux dicts statiques de
        `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor`
        (41 cles pour `GetTriggeredAbility`, 2 pour `GetActiveAbility`). Mesure, pas supposition.

        CONSOMMATEUR NATIF du trait : `StaticBattleRules.Effect$$NotBlockingMovementOfTraits`
        (Mounted / Vehicle / Unstoppable exemptent des effets de tuile bloquants Fire / Ice /
        BlockEnteringUnits), lu par `IdunBattle.Entities.Pathfinding.WalkPathfinder$$
        GetTileBlockingReasons` -- porte par `services/static_battle_rules.py`."""
        return [(UnitTrait.Unstoppable, True)]           # AddTrait(0x412, isTemporary: 1)

    def create_effect_damage_bonus_for_attack(self, is_ranged: "bool | None" = None,
                                              has_moved: "bool | None" = None,
                                              target_traits=None,
                                              is_prediction: bool = False,
                                              is_normal_attack: "bool | None" = True,
                                              target_armor_reduced: "bool | None" = None,
                                              att_ctx=None) -> "EffectBonus | None":
        """MIRROR de `IdunBattle.Entities.Effects.Loki.WarHowl_ExtraDamage_UnstoppableEffect$$
        CreateEffectDamageBonusForAttack` :

            EffectBonus.ForAddition( get_OwnerIsCaster & IsMeleeAttack & IsNormalAttack,
                                     ConfigVar(0x08 = extraDmg, GetAbilityState(effect),
                                               config@+0x60) )

        `is_ranged` tri-etat (#106) : seule une nature PROUVEE melee ouvre le gate — le natif ne se
        rabat jamais sur melee quand `GetAbilityAttackRangeType` ne tranche pas."""
        if not is_melee_attack(is_ranged):                 # IsMeleeAttack
            return None
        if is_normal_attack is not True:                   # IsNormalAttack
            return None
        n = ability_var(_ABILITY_ID, "extraDmg", self._level(),      # ConfigVar 0x08
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, int(n)) if n else None

    def create_effect_crit_chance_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `IdunBattle.Entities.Effects.Loki.WarHowl_ExtraDamage_UnstoppableEffect$$
        CreateCritChanceBonus` :

            EffectBonus.ForAddition(
                get_OwnerIsCaster & IsMeleeAttack & IsNormalAttack
                & AmountIsGreaterThanZero( StatAmount(Caster, 0x9 = CriticalChance,
                                                      StatPart.Current, null,
                                                      UnitSelectionType.Any) ),
                ConfigVar(0x41 = extraCritChance, GetAbilityState(effect), config@+0x60) )

        Le retour est un ENTIER (pas un `EffectBonus`) : le canal natif somme des scalaires
        (`IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects` accumule
        `addition - subtraction` de chaque `EffectBonus` evalue), et son consommateur est
        `clamp(GetStat(9) + somme, 0, 100)` dans `RollCritical`.

        Les trois cles d'`att_ctx` sont chacune UN noeud DSL, jamais un besoin d'effet, et une cle
        ABSENTE fait TAIRE son gate (« present != applique ») :
          * `is_ranged`          -> `IsMeleeAttack` (tri-etat #106, cf. `is_melee_attack`) ;
          * `is_normal_attack`   -> `IsNormalAttack` ;
          * `caster_crit_chance` -> `StatAmount(Caster, CriticalChance, StatPart.Current)`, la stat
            COURANTE de l'attaquant telle que `_crit_params` la lit (stat-modifications comprises,
            et APRES l'event `On(PreAttackHit=6)` — donc apres un eventuel stat-mod de crit pose par
            `ThrillSeekers`, exactement comme le natif qui evalue le trigger dans `RollCritical`).

        ⚠ `get_OwnerIsCaster` (le QUATRIEME noeud) etait rendu par le CANAL jusqu'a #589-r1-r1 : le
        balayage ne voyait que les effets de l'ATTAQUANT. Il a MIGRE ICI, a sa place native, quand
        le balayage s'est aligne sur l'univers natif (`board_effect_carriers`) pour `EmpyricAmbush`
        (1578), qui est porte par la CIBLE. Sans lui, un porteur SPECTATEUR bufferait un tiers.

        `extraCritChance` n'est PAS dans `variablesAffectedByRarityBonus` de `WarHowl` (qui ne
        contient que `extraDmg` et `maxDmg`) -> le multiplicateur est passe mais inerte."""
        c = att_ctx or {}
        if not owner_is_caster(c):                          # get_OwnerIsCaster
            return None
        if not is_melee_attack(c.get("is_ranged")):         # IsMeleeAttack
            return None
        if c.get("is_normal_attack") is not True:           # IsNormalAttack
            return None
        cc = c.get("caster_crit_chance")                    # StatAmount(Caster, CriticalChance)
        if cc is None or int(cc) <= 0:                      # AmountIsGreaterThanZero
            return None
        n = ability_var(_ABILITY_ID, "extraCritChance", self._level(),   # ConfigVar 0x41
                        multiplier_pct=self.ability_variables_multiplier)
        return int(n) if n else None
