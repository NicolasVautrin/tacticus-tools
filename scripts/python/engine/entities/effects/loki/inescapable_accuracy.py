"""`InescapableAccuracy_extraCritChance` (0x45b = **1115**), `InescapableAccuracy_extraCritDmg`
(0x45c = **1116**) et `InescapableAccuracy_overrideHits` (0x45d = **1117**) — les TROIS volets du
passif `InescapableAccuracy` (TriggeredAbilityType 0x45b = 1115) d'`eldarMauganRa`. case-366-r1.

## TROIS classes natives, pas une — tranche par le SLOT `Il2CppClass*`, jamais par le nom du ctor

La fiche d'inventaire annoncait « classe propre, ctor fondu avec 1116 ». Le ctor EST fondu (un seul
corps pour les trois ids) mais les CLASSES sont bien TROIS, et c'est le slot qui le dit :
`IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_141`,
`...b__14_142` et `...b__14_143` allouent chacune depuis un `Il2CppClass*` DIFFERENT, puis appellent
le MEME corps de `$$.ctor` (IL2CPP deduplique les corps bit-identiques -- et ce corps l'est, parce
que les trois classes derivent de `BaseEffect` avec la MEME constante d'ability).

Les trois tables de methodes le confirment -- RELUES BYTE A BYTE (case #366-r1/1116, pas heritees) :
trois blocs CONSECUTIFS de pointeurs de fonction, chacun ouvert par le MEME `.ctor` et la MEME
`CreateActiveCondition`, puis le MEME `CreateTargetSelector` (corps partage `= <DSLSelectors+0x30>`
= Owner) PLUS **une** methode qui lui est propre --

    table 1 : .ctor, CreateActiveCondition, ActiveCondition, CreateTargetSelector,
              CreateBlockHitReductionTrigger              -> `..._OverridHitsEffect`      = 1117
    table 2 : .ctor, CreateActiveCondition, CreateTargetSelector, CreateCritChanceBonus
                                                          -> `..._ExtraCritChanceEffect`  = 1115
    table 3 : .ctor, CreateActiveCondition, CreateTargetSelector, CreateCritDamageBonus
                                                          -> `..._ExtraCritDamageEffect`  = 1116

Ce module porte les TROIS -- trois canaux DIFFERENTS, donc trois classes distinctes ici aussi :
`RollCritical` (SI le coup crite), `CalculateCriticalDamage` (de COMBIEN), et `GetAttackHits`
(COMBIEN DE COUPS). Le troisieme (`BaseEffect$$BlockHitsReduction`, ouvert par la tranche 1117)
n'est pas un terme de somme mais un INTERRUPTEUR : cf. `InescapableAccuracyOverrideHitsEffect`.

## SOURCE DE CONFIG — la TRIGGERED 1115, pas l'EffectType 1115 (homonymie a deux faces)

Le corps de ctor partage :

    mov edx, 0x45b                                        ; 1115
    call IdunBattle.Core.AbilityOrEffect$$op_Implicit      ; surcharge TRIGGERED (tranchee par son
                                                          ;  ADRESSE : c'est celle dont le corps
                                                          ;  appelle `AbilityOrEffect$$set_
                                                          ;  TriggeredAbility`, les quatre
                                                          ;  surcharges portent le meme nom)
    call IdunBattle.Entities.Effects.BaseEffect$$.ctor(this, abilityOrEffect,
                                                      hasAutomaticActivation: 1)

`0x45b` vaut 1115 dans DEUX enums (`EffectType.InescapableAccuracy_extraCritChance` ET
`TriggeredAbilityType.InescapableAccuracy`, dump `enums.tsv`) : c'est le second qui est lu ici, et
c'est aussi la seule lecture COHERENTE -- sinon 1116 et 1117, qui partagent ce corps, liraient la
config de l'effet 1115. => la config est `abilities.InescapableAccuracy`, indexee par le niveau
d'ability **PASSIVE** du porteur.

## POSE — `InescapableAccuracyAbility$$CreateBehaviour` (les trois d'un bloc)

MIRROR du decompile :

    AddEffect(0x45b = 1115, <abilityStateReference>, targets = <DSLSelectors+0x30> = Owner, turns = NULL)
  + AddEffect(0x45c = 1116, <idem>)
  + AddEffect(0x45d = 1117, <idem>)
    (les trois fusionnes par `IdunBattle.DSL.AbilityBehaviour$$op_Addition`)

`turns = NULL` => PERMANENT : ce qui l'eteint est la CONDITION, pas une duree.

## CANAL — `CreateCritChanceBonus`, DEUX noeuds (et pas quatre)

    EffectBonus.ForAddition( get_OwnerIsCaster & IsRangedAttack,
                             ConfigVar(0x41 = extraCritChance, GetAbilityState(effect), config@+0x60) )

C'est le canal ouvert par `1222 WarHowl_ExtraDamage_Unstoppable` (case-366-r1) :
`IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects` accumule
`addition - subtraction` de chaque `EffectBonus`, et son consommateur unique est
`IdunBattle.Core.Services.DamagePrediction$$RollCritical` = `clamp(GetStat(9) + somme, 0, 100)`.
**N'HERITE RIEN DE SON VOISIN** : la ou WarHowl porte QUATRE noeuds
(`get_OwnerIsCaster & IsMeleeAttack & IsNormalAttack & AmountIsGreaterThanZero(StatAmount(Caster,
CriticalChance))`), celui-ci n'en porte que DEUX -- le gate d'attaque est l'INVERSE
(`IsRangedAttack`, surcharge SANS argument, tranchee par la cible du `call` :
`IdunBattleLogic.Entities.DSLTriggers$$IsRangedAttack` -> `IsRangedAttackAbilityTrigger`), il n'y a
**pas** de `IsNormalAttack` (le bonus vaut donc aussi pour les attaques d'ABILITY) et **pas** de
`AmountIsGreaterThanZero` (cf. le residu `CouldCrit` en fin de docstring).

## ACTIVE-CONDITION — `NOT HasFlag(Owner, UnitFlag.Moved)`

Le corps partage par les trois classes (`...InescapableAccuracy_ExtraCritDamageEffect$$
CreateActiveCondition` -- nom Ghidra du proprietaire arbitraire d'un corps DEDUPLIQUE, present dans
les TROIS tables de methodes) :

    op_LogicalNot( HasFlag( <DSLSelectors+0x30> = Owner, flag = 0 ) )

`IdunBattleLogic.Entities.DSLTriggers$$HasFlag` alloue un
`IdunBattle.Entities.Conditions.HasFlagAbilityTrigger(unit, flag, contains: 1)` dont le
`$$ShouldTrigger` est `IdunBattle.Entities.Components.UnitFlagsComponent$$Has(unit, flag)` ;
`flag = 0` = `UnitFlag.Moved` (cf. `runner/components.py::UnitFlagsComponent.MOVED`, meme foyer que
`unit_has_moved`). => **Maugan Ra qui a bouge ce tour ne beneficie plus du bonus.** Meme predicat
natif que `IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateActiveCondition` (#98), et
i2 le dit aussi (`Abilities/InescapableAccuracy_CurrentLevelDescription`).

Le port le rend DEUX fois, comme `ModifiedExoarmour_ExtraDmg` (case-322) rend son
`AmountIsGreaterThanZero(TilesMovedThisTurn)` : par `is_active` (la place NATIVE de la condition,
qui vaut pour tout consommateur d'`active_effects`) et par le gate du canal (`att_ctx["has_moved"]`,
pose au foyer unique `AttackDamageOperation._crit_params`). La redondance est assumee : les deux
lisent le MEME store, `UnitFlagsComponent`.

## CANAL 1116 — `CreateCritDamageBonus`, LES MEMES DEUX NOEUDS

    EffectBonus.ForAddition( get_OwnerIsCaster & IsRangedAttack,
                             ConfigVar(0x42 = extraCritDmg, GetAbilityState(effect), config@+0x60) )

RELU au decompile (`...InescapableAccuracy_ExtraCritDamageEffect$$CreateCritDamageBonus`), PAS
deduit de son voisin : meme paire `get_OwnerIsCaster` / `IsRangedAttack` fusionnee par
`IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd`, meme forme `ForAddition`, SEULE la variable change
(`0x42` au lieu de `0x41`). `0x41`/`0x42` = `AbilityVariableType` `65=extraCritChance` /
`66=extraCritDmg` (dump `enums.tsv`).

Le canal est l'AUTRE : `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects`
(qui batit le MEME `AbilityEntities` -- caster = owner = attaquant, target = defenseur -- puis
accumule `addition - subtraction`), consomme par
`IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage` :
`critDmgPct = max(0, GetStat(10) + somme)`. Il n'entre donc PAS dans `RollCritical` : 1115 decide SI
le coup crite, 1116 decide de COMBIEN. Les deux sont independants, et c'est ce qui les rend
mesurables separement.

## MAGNITUDE

`ConfigVar(0x41)` = `gameconfig.ability("InescapableAccuracy").variables["extraCritChance"][level]`
(10 -> 15 sur 65 niveaux ; **15** au niveau normalise 50).
`ConfigVar(0x42)` = `...variables["extraCritDmg"][level]` (10 -> 728 sur 65 niveaux ; **554** au
niveau normalise 50).

⚠ **LES DEUX VARIABLES NE SE COMPORTENT PAS PAREIL** face au bonus de rarete, et c'est la seule
asymetrie de ce module : `variablesAffectedByRarityBonus` de cette ability vaut exactement
`["extraCritDmg"]` -- donc `extraCritChance` n'est **PAS** scalee (aucun effet du multiplicateur) et
`extraCritDmg` l'EST (`round(base * AbilityVariablesMultiplierPercentage / 100)`). `ability_var`
applique cette regle config-driven toute seule : rien a coder de special, mais ne PAS transposer la
phrase « pas de scaling » de 1115 a 1116. Le residu #382 (« le multiplicateur vient de la SOURCE, le
port lit le PORTEUR ») reste inerte pour les deux : l'ability pose ses effets sur son propre porteur
(source == porteur), donc le multiplicateur lu est bien celui de la source.

## HYPOTHESE REFUTEE PAR LA MESURE — il n'y a PAS de residu `could_crit` ici

`IdunBattle.Core.Services.DamageCalculations$$CouldCrit(attacker)` lit bien `GetStat(9)` et
`GetStat(10)` BRUTES (le bonus d'effet n'y entre pas), et l'absence du gate
`AmountIsGreaterThanZero` -- que le voisin `1222` porte, lui -- faisait CRAINDRE que le port crite
la ou le natif ne crite pas, sur un porteur a `GetStat(9) == 0`.

**MESURE LIVE (`--crit 0,700`, `GetStat(9) = 0`) : le natif CRITE.** Le chemin d'execution ne passe
pas par `CouldCrit` (qui n'a que des xrefs DATA, donc n'est invoque que par slot d'interface) mais
par `IdunBattle.Core.Services.DamagePrediction$$RollCritical`, dont le gate est
`clamp(GetStat(9) + GetCritChanceBonusFromEffects, 0, 100) >= 1` -- **bonus INCLUS**. Le port, qui
passe `GetStat(9) + somme` a `could_crit`, rend donc exactement le meme gate. Les deux tirent, et le
coup mesure est bit-exact. Le carre du probe le montre dans les deux sens : sans le canal, le port
retombe a `could_crit(0, 700)` = faux, ne tire RIEN, et le coup cesse d'etre un crit.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect, is_ranged_attack
from ..magnitude import ability_var

_ABILITY_ID = "InescapableAccuracy"   # TriggeredAbilityType 0x45b = 1115 (passif, eldarMauganRa)


class _InescapableAccuracyEffect(BaseEffect):
    """Les DEUX methodes que les trois classes natives PARTAGENT, corps pour corps.

    Ce n'est pas une commodite Python : `.ctor` (un seul corps a l'adresse citee par les trois
    tables de methodes) et `CreateActiveCondition` (idem) sont UN SEUL corps natif reference par
    les trois entrees. La base rend cette structure telle quelle, et interdit que les deux volets
    derivent l'un de l'autre. Ce qui DIFFERE (le canal de lecture) reste dans chaque sous-classe."""

    def _level(self) -> "int | None":
        """`Level$$ToZeroBasedIndex(GetAbilityState(effect))` : `InescapableAccuracy` est une ability
        PASSIVE (`GC.unit("eldarMauganRa").passiveAbilities`) -> l'index est `ability_level`
        (= `unitConfig.passiveAbilityLevel`, propage par `EffectsState.seed`), repli stack level."""
        return self.ability_level if self.ability_level is not None else self.level

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`CreateActiveCondition` = `op_LogicalNot(HasFlag(Owner, 0 = UnitFlag.Moved))`.

        `has_moved` ABSENT du `unit_state` = **non mesure** -> on ne ferme pas (degradation fidele,
        meme regime que `ModifiedExoarmour_ExtraDmg` avec `tiles_moved_this_turn`). Cote COMBAT la
        cle EST posee : `UnitEffectStateView` la lit du `UnitFlagsComponent` via `unit_has_moved`,
        le store UNIQUE du fait « a bouge ce tour » (pose par `MoveUnitOperation`, purge par
        `RemoveTurnFlags` du `StartTurnOperation`)."""
        m = (unit_state or {}).get("has_moved")
        return True if m is None else not bool(m)


class InescapableAccuracyExtraCritChanceEffect(_InescapableAccuracyEffect):
    """`InescapableAccuracy_extraCritChance` (0x45b = 1115) — +extraCritChance% de chance de crit sur
    les attaques A DISTANCE du porteur, tant qu'il n'a pas bouge ce tour."""

    def create_effect_crit_chance_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
        InescapableAccuracy_ExtraCritChanceEffect$$CreateCritChanceBonus` :

            EffectBonus.ForAddition( get_OwnerIsCaster & IsRangedAttack,
                                     ConfigVar(0x41 = extraCritChance, GetAbilityState(effect),
                                               config@+0x60) )

        Le retour est un ENTIER (pas un `EffectBonus`) : le canal natif somme des scalaires
        (`GetCritChanceBonusFromEffects` accumule `addition - subtraction` de chaque `EffectBonus`),
        et son consommateur est `clamp(GetStat(9) + somme, 0, 100)` dans `RollCritical`.

        Les cles lues d'`att_ctx` sont chacune UN noeud natif, jamais un besoin d'effet, et une cle
        ABSENTE fait TAIRE son gate (« present != applique ») :
          * `is_ranged`  -> `IsRangedAttack` (tri-etat #106, cf. `is_ranged_attack` : nature non
            PROUVEE distance => aucune contribution) ;
          * `has_moved`  -> l'`ActiveCondition` `NOT HasFlag(Owner, UnitFlag.Moved)`. Ferme des que
            le mouvement est PROUVE ; la cle absente laisse passer, exactement comme
            `CrushingStrikeEffect` (#98), qui porte le MEME predicat natif par le MEME idiome.

        `get_OwnerIsCaster` est rendu par le CANAL (`crit_chance_bonus_from_effects` n'itere que les
        effets de l'ATTAQUANT). AUCUN gate `IsNormalAttack` cote natif -> le bonus vaut aussi pour
        les attaques d'ABILITY a distance ; ne pas en ajouter un par analogie avec 1222."""
        c = att_ctx or {}
        if not is_ranged_attack(c.get("is_ranged")):        # IsRangedAttack
            return None
        if c.get("has_moved"):                              # ActiveCondition NOT HasFlag(Moved)
            return None
        n = ability_var(_ABILITY_ID, "extraCritChance", self._level(),   # ConfigVar 0x41
                        multiplier_pct=self.ability_variables_multiplier)
        return int(n) if n else None


class InescapableAccuracyExtraCritDamageEffect(_InescapableAccuracyEffect):
    """`InescapableAccuracy_extraCritDmg` (0x45c = 1116) — +extraCritDmg points de DEGAT de crit sur
    les attaques A DISTANCE du porteur, tant qu'il n'a pas bouge ce tour.

    Frere de 1115 par la POSE (meme `AddEffect` d'un bloc, meme Owner, meme `turns = NULL`) et par
    le GATE (meme corps de `CreateActiveCondition`), mais PAS par le canal : celui-ci n'entre pas
    dans le tirage (`RollCritical`), il entre dans le MONTANT (`CalculateCriticalDamage`)."""

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
        InescapableAccuracy_ExtraCritDamageEffect$$CreateCritDamageBonus` :

            EffectBonus.ForAddition( get_OwnerIsCaster & IsRangedAttack,
                                     ConfigVar(0x42 = extraCritDmg, GetAbilityState(effect),
                                               config@+0x60) )

        Le retour est un ENTIER (pas un `EffectBonus`) : le canal natif somme des scalaires
        (`GetCritDamageBonusFromEffects` accumule `addition - subtraction` de chaque `EffectBonus`),
        et son consommateur est `max(0, GetStat(10) + somme)` dans `CalculateCriticalDamage`.

        Les DEUX cles lues d'`att_ctx` sont chacune UN noeud natif, et une cle ABSENTE fait TAIRE
        son gate (« present != applique ») -- exactement les memes que 1115, parce que le natif
        porte exactement les memes deux noeuds :
          * `is_ranged`  -> `IsRangedAttack` (tri-etat #106 : nature non PROUVEE distance =>
            aucune contribution) ;
          * `has_moved`  -> l'`ActiveCondition` `NOT HasFlag(Owner, UnitFlag.Moved)`, redondante
            avec `is_active` et VOULUE telle (l'agregateur `crit_damage_bonus_from_effects` ne
            filtre PAS sur `is_active` : le gate du canal est la garde effective).

        `get_OwnerIsCaster` est rendu par le CANAL (`crit_damage_bonus_from_effects` n'itere que les
        effets de l'ATTAQUANT). AUCUN gate `IsNormalAttack` cote natif -> le bonus vaut aussi pour
        les attaques d'ABILITY a distance ; ne pas en ajouter un par analogie avec 1222.

        ⚠ `extraCritDmg` EST dans `variablesAffectedByRarityBonus` (contrairement a
        `extraCritChance`) : `ability_var` applique le multiplicateur de rarete du porteur."""
        c = att_ctx or {}
        if not is_ranged_attack(c.get("is_ranged")):        # IsRangedAttack
            return None
        if c.get("has_moved"):                              # ActiveCondition NOT HasFlag(Moved)
            return None
        n = ability_var(_ABILITY_ID, "extraCritDmg", self._level(),      # ConfigVar 0x42
                        multiplier_pct=self.ability_variables_multiplier)
        return int(n) if n else None


class InescapableAccuracyOverrideHitsEffect(_InescapableAccuracyEffect):
    """`InescapableAccuracy_overrideHits` (0x45d = 1117) — les attaques A DISTANCE du porteur
    IGNORENT les REDUCTIONS de coups, tant qu'il n'a pas bouge ce tour.

    Le TROISIEME volet du passif, et le seul des trois a ne pas etre un terme de somme : son canal
    natif est un BOOLEEN. i2 le dit dans les memes mots
    (`Abilities/InescapableAccuracy_CurrentLevelDescription`) : << If Maugan Ra has not moved, then
    his ranged attacks **ignore hit reductions**, have +X% Crit Chance, and deal an additional Y
    Crit Damage >>.

    ## CANAL — `CreateBlockHitReductionTrigger`, LES MEMES DEUX NOEUDS que 1115/1116

        get_OwnerIsCaster & IsRangedAttack

    RELU au decompile (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    InescapableAccuracy_OverridHitsEffect$$CreateBlockHitReductionTrigger`), pas transpose : meme
    paire fusionnee par `IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd`, memes surcharges
    (`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster` /
    `IdunBattleLogic.Entities.DSLTriggers$$IsRangedAttack`, celle SANS argument).

    ⚠ **Ce n'est PAS un `EffectBonus`** : le corps rend le trigger NU, la ou 1115 et 1116 rendent un
    `EffectBonus.ForAddition(trigger, ConfigVar(...))`. Il n'y a donc **aucune variable de config**,
    donc **aucune magnitude**, donc rien a scaler -- `variablesAffectedByRarityBonus` de
    `InescapableAccuracy` ne contient que `extraCritDmg`, et cette ability n'a QUE deux variables
    (`extraCritChance`, `extraCritDmg`), toutes deux consommees par les deux autres volets. Le
    piege de #414 (« la rarete est PAR VARIABLE ») est donc INERTE ici, et pour une raison de
    STRUCTURE, pas de configuration.

    ## CONSOMMATEUR — l'interrupteur des reductions, pas un terme

    `IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction` evalue le trigger mis en cache a
    `<effect>+0x460` par `IdunBattle.Entities.Effects.BaseEffect$$InitializeBonusCacheIfNeeded`, et
    son unique lecteur est `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` : il trie les
    `HitsBonusForAttack` de tous les effets ACTIFS du board en DEUX listes selon le signe de leur
    `addition`, somme les additions, puis **saute la liste des reductions** si le flag est arme.
    C'est la MEME facade pour les deux faces -- `IdunBattle.Operations.AttackDamageOperation$$
    GetAttackHits` delegue au slot 0xb6 de `BattleQuery`, qui delegue a cette fonction -- donc le
    port n'a qu'un point de cablage (`services.attack_hits_formula`), COMBAT et PREDICTION.

    ## ACTIVE-CONDITION — meme corps que ses deux soeurs

    `NOT HasFlag(Owner, 0 = UnitFlag.Moved)`, heritee de `_InescapableAccuracyEffect`. Le corps que
    Ghidra nomme `..._OverridHitsEffect$$ActiveCondition` est INSTRUCTION POUR INSTRUCTION celui de
    `..._ExtraCritDamageEffect$$CreateActiveCondition` (meme `HasFlag(<DSLSelectors+0x30> = Owner,
    flag = 0)` suivi du meme `IdunBattle.DSL.AbilityTrigger$$op_LogicalNot`) : deux corps distincts
    dans la table, une seule semantique -- relu, pas suppose.

    ⚠ **La redondance est ici PLUS FAIBLE que chez 1115/1116, et c'est un fait natif** : l'agregateur
    de ce canal n'est PAS aveugle a l'etat actif. `IdunBattle.Core.Services.EffectsQuery$$
    GetActiveEffectsWithBonuses` filtre son enumeration sur `EffectComponent@+0x5c` (le flag
    `IsActive`) avant de rendre la liste, alors que `GetCritChanceBonusFromEffects` /
    `GetCritDamageBonusFromEffects` ne filtrent rien. Le gate `has_moved` reste rendu ici par
    coherence de famille (meme store `UnitFlagsComponent`, jamais faux), mais la garde EFFECTIVE de
    ce volet est `is_active`."""

    def block_hits_reduction(self, att_ctx: "Mapping | None" = None) -> bool:
        """MIRROR de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
        InescapableAccuracy_OverridHitsEffect$$CreateBlockHitReductionTrigger` :

            get_OwnerIsCaster & IsRangedAttack

        Le retour est un BOOLEEN (pas un `EffectBonus`) : le canal natif n'accumule rien, il arme un
        flag (`BaseEffect$$BlockHitsReduction` -> `DamagePrediction$$GetAttackHits`).

        `get_OwnerIsCaster` est rendu par le CANAL (`block_hits_reduction_from_effects` n'itere que
        les effets de l'ATTAQUANT). Les cles lues d'`att_ctx` sont celles du `board` de
        `AttackHitsWithModifiersFormula` :
          * `is_melee` -> `IsRangedAttack`. TRI-ETAT #106 : seule une nature PROUVEE distance ouvre
            le gate (`is not False` = mêlée ou nature inconnue -> muet), meme idiome que
            `BigTargetAdjacentEffect.create_aura_hits_malus_for_defense`. NB : sur l'axe COUPS la
            cle du board est `is_melee`, pas `is_ranged` -- ne pas transposer l'appel des canaux
            crit, qui lisent `att_ctx["is_ranged"]` pose par `AttackDamageOperation._crit_params` ;
          * `has_moved` -> l'`ActiveCondition`, rendue une seconde fois (cf. la docstring de
            classe). Cle ABSENTE = ne ferme pas.

        AUCUN gate `IsNormalAttack` cote natif -> le blocage vaut aussi pour une attaque d'ABILITY
        a distance de la famille ATTACK (le seul autre vecteur qui traverse cette formule)."""
        c = att_ctx or {}
        if c.get("is_melee") is not False:                   # IsRangedAttack (tri-etat #106)
            return False
        if c.get("has_moved"):                               # ActiveCondition NOT HasFlag(Moved)
            return False
        return True
