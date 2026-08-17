"""`InescapableDeath` (`TriggeredAbilityType` 0x3ed = 1005), passif de `necroDestroyer` (Imospekh).

Tache #924. Ce module porte la face DEGAT ; les deux `Triggered()` heritees vivent dans
`runner/operations/triggers/loki/reactivate_overwatch.py` (meme base native).

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================

## 0. La hierarchie -- LUE dans `data/symbols/<build>/frida/classes.tsv`, jamais deduite d'un nom

    IdunBattleLogic.Entities.Abilities.Active.Loki.InescapableDeathAbility
      : IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility

    IdunBattle.Entities.Effects.Loki.InescapableDeathEffect
      : IdunBattle.Entities.Effects.AReactivateOverwatchEffect

Le namespace `...Abilities.Active...` MENT : `InescapableDeath` est une `passiveAbilities` du
gameconfig, et sa base est celle des passifs qui posent un effet sur leur porteur.

## 1. L'ability -- TROIS methodes, toutes heritees sauf une

`IdunBattleLogic.Entities.Abilities.Active.Loki.InescapableDeathAbility$$GetEffectType`
= `return 0x3fa` = **1018 `EffectType.InescapableDeath_Effect`** (corps entier : `mov eax,0x3fa ; ret`).

`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateTrigger`
= `DSLTriggers.OnOwnerSpecificAbilityInit(this@0x10)`

`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour(abilityState, triggerType)`
= `If( CreateCondition(abilityState),
      AddEffect( GetEffectType(),                                  # vtable +0x378 -> 1018
                 DSLSelectors.AbilityState(owner@0x30, AbilityType.op_Implicit(abilityState)),
                 owner@0x30, owner@0x30, default(Nullable<...>) ) )`

=> patron **`ABILITY_INIT_OWNER_EFFECTS`** : l'effet 1018 est pose sur le PORTEUR a l'init de son
ability, sans condition d'etat. C'est la face **DECISION owner**.

## 2. L'effet 1018 -- QUATRE methodes declarees, et le comptage qui le PROUVE

`InescapableDeathEffect$$.ctor` = `AReactivateOverwatchEffect..ctor(this, 0x3ed)`. La surcharge
retenue est celle qui prend un `baseAbility: TriggeredAbilityType` (`InescapableDeath` est une
`passiveAbilities`) -> l'effet resout ses `ConfigVar` contre la config d'ability **`InescapableDeath`**
(`config@0x60`), pas contre celle du porteur.

⚠ **Le dump FRIDA ne liste que 4 methodes pour cette classe, et ce compte est JUSTE -- mais on ne
pouvait pas le savoir depuis lui.** `frida/methods.tsv` est indexe par ADRESSE et l'ICF fusionne les
corps identiques, donc une methode surchargee y DISPARAIT si son corps est partage. Le comptage qui
tranche est celui du bloc `methodPointers` du PE, ou **chaque proprietaire a SA propre entree** :

    slot 0  ->  InescapableDeathEffect$$.ctor
    slot 1  ->  InescapableDeathEffect$$GetHitReductionEffectType
    slot 2  ->  InescapableDeathEffect$$GetOverwatchExtraDamage           <- corps PARTAGE (cf. §5)
    slot 3  ->  InescapableDeathEffect$$GetAdditionalExtraDamageTrigger

Quatre entrees contigues, quatre methodes. **Aucune n'adresse `LegitDeathReasons`** => cette classe
n'override PAS `LegitDeathReasons` et prend celle de la base (§4). C'est l'inverse exact de sa
soeur `EarlyWarningOverride_ReactivateOverwatchEffect`, qui elle l'override.

⚠ **CE TABLEAU PORTAIT QUATRE VA ABSOLUES, ET LES QUATRE ETAIENT PERIMEES (#924-r1, 2026-08-15).**
Elles avaient ete lues sur `rnca9r7q6c` ; re-mesurees sur `t6dpr4k06g`, le bloc est ailleurs et le
corps aussi -- churn de **100 %**, exactement ce que le CLAUDE.md annonce pour les adresses (les
NOMS, eux, sont stables a 97,5 %). La STRUCTURE, elle, est confirmee a l'identique : quatre entrees
contigues, `GetOverwatchExtraDamage` en 3e position, aucune sur `LegitDeathReasons`.
D'ou l'ecriture par SLOT ci-dessus : elle survit au changement de build, et se re-verifie en un
`list_xrefs` sur `<Classe>$$.ctor` (l'unique xref DATA donne la tete du bloc) suivi d'un
`read_bytes` de 4 pointeurs.

Les corps :

  * `GetHitReductionEffectType()` = `return 0x3fb` = **1019 `InescapableDeath_HitsReduction`** ;
  * `GetAdditionalExtraDamageTrigger()` = `DSLTriggers.IsOverwatchAttack()` (§3) ;
  * `GetOverwatchExtraDamage()` = `DSLFormulas.ConfigVar(formulas, 8, abilityState, config@0x60)`
    -> **`AbilityVariableType.extraDmg`** (index 8, mirror verifie), variable per-niveau de
    `InescapableDeath`.

## 3. Le gate de la face DEGAT -- `AReactivateOverwatchEffect$$CreateDamageModifier`

    abilityOrEffect = GetOverwatchExtraDamage()            # vtable +0x778
    if (abilityOrEffect == null) return default(Nullable<EffectBonus>)   # <- la BASE s'eteint ici
    trigger =   get_OwnerIsCaster
              & TriggeringEffectIs(0x3f1)                                # 1009 Overwatch_AutoAttack
              & GetAdditionalExtraDamageTrigger()                        # vtable +0x768
    return EffectBonus.ForAddition(trigger, abilityOrEffect)

La base est donc INERTE par defaut (`GetOverwatchExtraDamage` renvoie `null`) : seule une sous-classe
qui l'override allume ce canal. `InescapableDeathEffect` l'override -> le canal est VIVANT.

⚠ **Les deux termes de declencheur sont le MEME predicat, relu terme a terme :**

    IsOverwatchAttack()  =  TriggeringAbilityIs( AbilityOrEffect.op_Implicit(0x3f1) )

L'immediat `0x3f1` est LU AUX OCTETS (`mov edx,0x3f1` avant le `call`), et la surcharge
`op_Implicit` appelee est celle @`18166a080`, dont le corps est `set_Effect` -- donc un
`AbilityOrEffect{Effect = EffectType.Overwatch_AutoAttack}`, exactement ce que construit
`TriggeringEffectIs(0x3f1)`. Et les deux fonctions lisent le MEME champ du contexte
(`DSLTriggers+0x10 -> +0x90 -> +0x90` dans les deux decompiles) puis appellent le MEME
`DSLSelectors.Direct`. La conjonction native est donc **strictement redondante** (`X & X = X`) :
le port n'evalue le predicat qu'une fois, et ce paragraphe est la mesure qui l'autorise.

`get_OwnerIsCaster` est STRUCTURELLEMENT satisfait sur ce canal : `create_effect_damage_bonus_for_attack`
n'est interroge que pour les effets portes par l'ATTAQUANT du coup courant.

## 4. Ce que la face DEGAT n'a PAS (et que le voisin de forme aurait fait recopier)

Aucun `IsRangedAttack` au decompile. L'i2 anglais dit pourtant « **ranged** attacks now deal
+{[extraDmg]} Damage per hit when triggered by Overwatch » -- la restriction au tir est portee par
le FAIT que l'overwatch est un tir (`Overwatch_AutoAttackEffect$$GetAttackBehaviour` =
`UseActiveAbility(NormalAttack)` a distance), pas par un noeud du trigger. Ecrire un
`if not is_ranged_attack(is_ranged): return None` serait une invention : ce gate n'existe pas.

De meme, aucun `LegitDeathReasons` propre (§2), aucun filtre d'`Immune`, aucun `IsNormalAttack`.

## 5. Le corps PARTAGE, et le residu qu'il ouvre (#924-r1)

Le corps de `GetOverwatchExtraDamage` est **PARTAGE par EXACTEMENT DEUX proprietaires** (ICF) : le
code est identique parce que toute la variabilite passe par `this` (`config@0x60`). Les deux, et
eux seuls :

    <bloc de EarlyWarningOverride_ReactivateOverwatchEffect>, slot 2  ->  ce corps
    <bloc de InescapableDeathEffect>,                          slot 2  ->  ce corps

**`EarlyWarningOverride` (1145) override donc AUSSI `GetOverwatchExtraDamage`**, et sa variable
`extraDmg` existe et est non nulle dans le gameconfig -- sa face DEGAT est VIVANTE et n'est PAS
portee : residu **#924-r1**.

⚠ **RE-MESURE COMPLETE DU 2026-08-15 SUR `t6dpr4k06g` (#924-r1) -- LA PREMISSE TIENT, LES TROIS VA
QUI L'ETAYAIENT ETAIENT FAUSSES.** La fiche du backlog citait un bloc `18326d838..d850` pour 1145 ;
decode sur le build courant, ce bloc porte des corps `18103d*` **sans aucun rapport**. Le vrai bloc
de 1145 a ete retrouve par `list_xrefs` sur ses trois methodes nommees, puis borne par lecture des
pointeurs voisins :

    slot 0  ->  EarlyWarningOverride_ReactivateOverwatchEffect$$.ctor
    slot 1  ->  EarlyWarningOverride_ReactivateOverwatchEffect$$GetHitReductionEffectType
    slot 2  ->  <le corps PARTAGE de GetOverwatchExtraDamage>
    slot 3  ->  EarlyWarningOverride_ReactivateOverwatchEffect$$LegitDeathReasons
    (slot suivant : EarlyWarningOverride_VisualEffect$$.ctor -- la classe a CHANGE, donc le bloc
     fait EXACTEMENT quatre entrees)

QUATRE entrees, dont le corps partage en 3e position : **la premisse de #924-r1 est CONFIRMEE**.
Et la BASE `AReactivateOverwatchEffect` ne porte PAS ce corps dans son propre bloc -- 1145
l'OVERRIDE, elle ne l'herite pas.

⚠ **LES DEUX SOEURS SONT DES MIROIRS CROISES, et c'est ce que le comptage etablit** :

    InescapableDeathEffect   : override GetAdditionalExtraDamageTrigger, PAS LegitDeathReasons
    EarlyWarningOverride_... : override LegitDeathReasons, PAS GetAdditionalExtraDamageTrigger

Consequence pour qui portera 1145 : son 3e conjoint de declencheur (`<vtable +0x768>`) est celui de
la BASE, pas l'`IsOverwatchAttack()` d'`InescapableDeath`. Recopier le §3 tel quel serait le piege
du voisin de forme -- et le voisin est litteralement la classe soeur.

⚠ La docstring de `reactivate_overwatch.py` affirmait « 1145 n'override PAS `GetOverwatchExtraDamage` ».
C'etait une lecture du seul dump FRIDA, ou l'entree de 1145 est absente pour cause d'ICF -- corrigee
dans le meme commit.

## 6. LA FACE DEGAT N'EST PAS PORTEE -- l'ETAGE est INVALIDE PAR LA MESURE (#924-r2)

Le gate et la magnitude sont ETABLIS (§3, §2) et le natif applique BIEN ce bonus -- mesure live, meme
run, meme attaquant, meme cible, armure 0 des deux cotes (`--hp-target 60000`, board MC1_67) :

    attaque NORMALE   coups = [569, 625, 647, 697, 728, 506]     moyenne  628,7
    tir  OVERWATCH    coups = [1328, 1114, 1329, 1206, 1279, 1220]  moyenne 1246,0

Le tir d'overwatch fait **1,98x** le degat de l'attaque normale de la MEME unite : la face existe,
elle n'est pas dead-code.

Et le port produirait un ECART DIFFERENT de celui du natif :

  * ecart NATIF   overwatch - normale =  617,3 par coup ;
  * ecart PORT    nominal - mutant    =  5388 pour 6 coups = **898,0 par coup, EXACTEMENT**
    (mutant = la meme salve rejouee avec `create_effect_damage_bonus_for_attack` neutralise).

⚠ **CE QUE CET ECART NE DIT PAS (#1084, 2026-08-14).** Il a d'abord ete lu comme un ecart
d'ETAGE (« le natif ajoute avant la resolution des bornes, le port apres »). Cette attribution est
REFUTEE, deux fois :

  * au DECOMPILE -- `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` calcule
    lui-meme les deux jeux de modificateurs (slots `0xd` ATTAQUANT et `0xe` DEFENSEUR de
    `IDamageCalculations`, c.-a-d. `IdunBattle.Core.Services.DamageCalculations$$
    CalculateAttackerModifiersForPrediction` et son jumeau DEFENSE), lit de CHACUN le champ
    `+0x10` (`DamageModifiers.Addition`) et le SOMME au `baseDamage` passe a
    `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` -- pour la
    borne MIN et pour la borne MAX. CBDWAM, lui, ne lit que `+0x20`/`+0x28`/`+0x18`/`+0x30`,
    JAMAIS `+0x10`. L'additif entre donc AVANT le percage et AVANT les %-mods : la position
    `attacker_additive_pre=True` du port ;
  * a la MESURE -- le montage est « armure 0 des deux cotes », or a armure nulle
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$
    GetDamageWithPiercing` est l'IDENTITE : les deux positions rendent le MEME nombre
    (`+898,0` des deux cotes). Le regime est DEGENERE pour la question posee. Dans le regime
    SEPARANT (celui de #75 : `pierce = 50`, armure `2208`) elles rendent `+449` contre `+898`.

Ce qui reste ouvert est donc une divergence de MAGNITUDE non localisee -- piste : le niveau et le
multiplicateur de l'`AbilityState` sous lequel `extraDmg` est lu (meme famille de verrou que
#1005 / #237). La methode reste RETIREE, pas ecrite « en attendant » : ce module porte la RE, le
registre porte l'effet, et le residu **#924-r2** porte le point ouvert. Deux cliquets :
`test_924_inescapable_death_offline.py` rougit si quelqu'un re-arme la face ;
`test_924r2_place_additif_attaquant_offline.py` rougit si quelqu'un DEPLACE l'additif.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition
from ..base import BaseEffect
from ..magnitude import ability_var
from ...ability_variable_type import AbilityVariableType
from ...effect_type import EffectType

#: `InescapableDeathEffect$$.ctor` = `AReactivateOverwatchEffect..ctor(this, 0x3ed)` -- l'ability
#: dont l'effet lit la config (`config@0x60`), donc la source de `extraDmg` ET de `hitsReduction`.
INESCAPABLE_DEATH = "InescapableDeath"

#: `EarlyWarningOverride_ReactivateOverwatchEffect$$.ctor` =
#: `AReactivateOverwatchEffect..ctor(this, 0x435)` -- LU au decompile (`t6dpr4k06g`). `0x435 = 1077`
#: est un **`ActiveAbilityType`** (`EarlyWarningOverride`, l'active de `tauCrisis` << Re'vas >>),
#: pas un `TriggeredAbilityType` : c'est le pendant exact du `0x3ed` de sa soeur, mais sur l'autre
#: hierarchie d'ability -- d'ou la cascade de niveau `active_ability_level` D'ABORD ci-dessous.
EARLY_WARNING_OVERRIDE = "EarlyWarningOverride"

#: `GetOverwatchExtraDamage` = `ConfigVar(..., 8, ...)`. Membre NOMME (regle ENUM) : l'ordinal 8 est
#: aussi un membre valide d'`AbilityConstantType`, ou il nomme autre chose.
EXTRA_DMG_VAR = AbilityVariableType.extraDmg.name

#: Le littéral `0x3f1` des DEUX termes de declencheur, qualifie **EffectType** (la surcharge
#: `op_Implicit` @`18166a080` appelle `set_Effect`) -- pas l'`ActiveAbilityType` 1009
#: (`ResurrectionOrb`) ni le `TriggeredAbilityType` 1009 (`WhipcoilBody`), qui portent le meme
#: ordinal et n'ont rien a voir.
TRIGGERING_EFFECT_TYPE = int(EffectType.Overwatch_AutoAttack)          # 0x3f1 = 1009


def is_overwatch_triggered(ctx: Mapping | None) -> bool:
    """`TriggeringEffectIs(0x3f1) & IsOverwatchAttack()` -- **UN SEUL** predicat, pas deux.

    Les deux termes du declencheur natif lisent le MEME champ (`AbilityEntities+0x98`, atteint par
    `DSLTriggers+0x10 -> +0x90 -> +0x90` dans les deux decompiles) et construisent le MEME
    `AbilityOrEffect{Effect = EffectType.Overwatch_AutoAttack}` : la conjonction est strictement
    redondante (`X & X = X`), et c'est la mesure de l'en-tete SS3 qui autorise a ne l'evaluer
    qu'une fois.

    DEUX cles du port servent ce meme fait, et l'ordre n'est pas arbitraire :
      * `trigger_ability_type` -- le mirror LITTERAL du champ `+0x98`, deja threade sur l'axe COUPS
        (`build_hits_board` -> `PurgeResponse`). S'il est present, il TRANCHE : une valeur autre
        que 1009 ferme le gate ;
      * `is_overwatch` -- le booleen que le SEUL producteur du vecteur pose conjointement
        (`triggers/effect_triggers.py::OverwatchAutoAttack` passe `is_overwatch=True` ET
        `triggering_ability=OVERWATCH_AUTO_ATTACK`). C'est lui que l'axe DEGAT recoit aujourd'hui.
    Aucune des deux -> gate FERME (<< non mesure >> n'est pas << faux >>, mais on n'invente pas un
    declencheur).

    ⚠ Ce predicat qualifie un **EffectType**. L'ordinal 1009 est aussi un `ActiveAbilityType`
    (`ResurrectionOrb`) et un `TriggeredAbilityType` (`WhipcoilBody`), qui n'ont rien a voir : la
    surcharge `AbilityOrEffect$$op_Implicit` appelee par `IsOverwatchAttack()` a pour corps
    `set_Effect`, lu aux octets."""
    c = ctx or {}
    tat = c.get("trigger_ability_type")
    if tat is not None:
        return int(tat) == TRIGGERING_EFFECT_TYPE
    return c.get("is_overwatch") is True


class InescapableDeathEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.InescapableDeathEffect` (EffectType 0x3fa = 1018).

    Les deux `Triggered()` de `CreateHandleTriggerAbilitiesInternal` -- re-entree en overwatch apres
    un kill, et sa reduction de coups 1019 -- sont portees, et enregistrees sur le MEME effet 1018
    dans `runner/operations/triggers/loki/reactivate_overwatch.py`.

    La face DEGAT est PORTEE depuis #924-r3 (cf. §6 de l'en-tete pour la mesure qui a leve
    #924-r2) : `create_effect_damage_bonus_for_attack` ci-dessous est le mirror de
    `AReactivateOverwatchEffect$$CreateDamageModifier` allume par l'override
    `InescapableDeathEffect$$GetOverwatchExtraDamage`."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """`IdunBattle.Entities.Effects.AReactivateOverwatchEffect$$CreateDamageModifier`, mirror
        1:1 (le corps entier, §3 de l'en-tete) :

            abilityOrEffect = GetOverwatchExtraDamage()             # <vtable +0x778>
            if (abilityOrEffect == null) return default             # la BASE s'eteint ici
            trigger = get_OwnerIsCaster
                      & TriggeringEffectIs(0x3f1)                   # 1009 Overwatch_AutoAttack
                      & GetAdditionalExtraDamageTrigger()           # <vtable +0x768>
            return EffectBonus.ForAddition(trigger, abilityOrEffect)

        Les TROIS conjoints, et rien d'autre :
          * `get_OwnerIsCaster` -- STRUCTUREL sur ce canal : `_attacker_effect_bonuses` n'itere que
            les effets de l'ATTAQUANT du coup courant ;
          * `TriggeringEffectIs(0x3f1)` et `GetAdditionalExtraDamageTrigger()` -- pour CETTE
            sous-classe, l'override rend `IsOverwatchAttack()`, qui EST le meme predicat (§3) :
            `is_overwatch_triggered` les evalue donc UNE fois.

        ⚠ **AUCUN `IsRangedAttack`** au decompile, alors que l'i2 anglais dit « **ranged** attacks
        now deal +extraDmg … » : la restriction au tir tient au FAIT que l'overwatch est un tir
        (`Overwatch_AutoAttackEffect$$GetAttackBehaviour` = `UseActiveAbility(NormalAttack)` a
        distance), pas a un noeud du trigger. L'ecrire serait une invention -- et elle serait
        INVISIBLE tant qu'on ne teste que l'overwatch. Meme chose pour `IsNormalAttack`,
        `has_moved`, et tout filtre `Immune` : aucun n'existe ici.

        ⚠ **`ForAddition` -> `DamageModifiers.Addition@+0x10`**, consomme par le canal deja porte
        `attacker_additive_pre=True` : l'additif entre AVANT le percage et AVANT les %-mods.
        `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` somme lui-meme ce `+0x10` au
        `baseDamage` (borne MIN et borne MAX), et
        `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` ne le lit
        JAMAIS -- il ne consomme que `+0x20`/`+0x28`/`+0x18`/`+0x30`. Rien a re-ordonnancer.

        MAGNITUDE -- `GetOverwatchExtraDamage()` = `ConfigVar(AbilityVariableType.extraDmg = 8,
        GetAbilityState(this), config@+0x60)`, ou `config@+0x60` est la config d'`InescapableDeath`
        (l'argument du `.ctor`), PAS celle du porteur. `extraDmg` EST dans
        `variablesAffectedByRarityBonus` -> `ability_var` applique le multiplicateur de rarete.
        Couple MESURE live par `probe_924r2_ability_state_overwatch.py` (`unitAbilityStates`) :
        `level = 50, mult = 180` -> 898."""
        if not is_overwatch_triggered(att_ctx):
            return None
        # `GetAbilityState(this)` -- `InescapableDeath` est une `passiveAbilities` : meme cascade
        # que les autres effets de passif (`active_ability_level -> ability_level -> level`).
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        if lvl is None:                      # ConfigVar sans AbilityState -> pas de magnitude
            return None
        v = ability_var(INESCAPABLE_DEATH, EXTRA_DMG_VAR, lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, int(v)) if v else None


class EarlyWarningOverrideReactivateOverwatchEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.EarlyWarningOverride_ReactivateOverwatchEffect`
    (`EffectType` 0x479 = **1145**) -- la SOEUR de forme de 1018, meme base native
    `AReactivateOverwatchEffect`. Residu **#924-r1**.

    Elle est posee par `IdunBattleLogic.Entities.Abilities.Active.Loki.EarlyWarningOverrideAbility$$
    ExecuteBehaviour` sur le CASTER lui-meme, en meme temps que `0x3f1 = 1009 Overwatch_AutoAttack`,
    `0x478 = 1144 SuppressCloseCombatWeakness` et `0x47d = 1149 EarlyWarningOverride_Visual`, pour
    `TurnsFromRounds(1)` -- QUATRE `AddEffect` qui partagent le MEME
    `DSLSelectors.CreateSnapshot(abilityState)` (lu au decompile ; d'ou le `scale_from_source=True`
    de `runner/abilities/tau.py`). Porteur `tauCrisis` << Re'vas >>, HERO, AU POOL : le montage est
    immediat, sans injection ni greffe.

    ## LE BLOC `methodPointers`, RE-LU AUX OCTETS SUR `t6dpr4k06g` -- QUATRE entrees

        slot 0  ->  EarlyWarningOverride_ReactivateOverwatchEffect$$.ctor
        slot 1  ->  EarlyWarningOverride_ReactivateOverwatchEffect$$GetHitReductionEffectType
        slot 2  ->  <le corps PARTAGE de GetOverwatchExtraDamage>   (ICF, 2 proprietaires)
        slot 3  ->  EarlyWarningOverride_ReactivateOverwatchEffect$$LegitDeathReasons
        (l'entree suivante appartient a la classe SUIVANTE -> le bloc fait EXACTEMENT quatre)

    ⇒ **1145 OVERRIDE `GetOverwatchExtraDamage`** : sa face DEGAT est VIVANTE, et
    `extraDmg` est non nul dans le gameconfig (`[26, 31, 36, ..., 1440]`, dans
    `variablesAffectedByRarityBonus`). C'est ce que `frida/methods.tsv` ne pouvait PAS montrer :
    indexe par ADRESSE, il ne garde qu'UN proprietaire par corps ICF.

    ## LES DEUX SOEURS SONT DES MIROIRS CROISES -- le piege du voisin de forme

        InescapableDeathEffect   : override GetAdditionalExtraDamageTrigger, PAS LegitDeathReasons
        EarlyWarningOverride_... : override LegitDeathReasons, PAS GetAdditionalExtraDamageTrigger

    Le `<vtable +0x768>` (`GetAdditionalExtraDamageTrigger`) de 1145 est donc celui de la BASE.
    Recopier le 3e conjoint d'`InescapableDeath` (`IsOverwatchAttack()`) serait le piege --
    et le voisin est litteralement la classe soeur.

    ⚠ **CE QUE REND LA BASE, ET COMMENT ON LE SAIT.** Son `GetAdditionalExtraDamageTrigger` n'a
    aucun symbole propre (corps trivial, deduplique par ICF). Il a ete retrouve dans le bloc
    `methodPointers` de `AReactivateOverwatchEffect`, entre `CreateDamageModifier` et le corps
    `xor eax,eax ; ret` de `GetOverwatchExtraDamage` (celui qui rend la BASE inerte) : son corps est
    `return <DSLTriggers+0x70>`, la constante que le port a deja identifiee ailleurs comme le
    **`YesTrigger`** (constante VRAIE ; memes octets que les `CreateActiveCondition` de
    `KardiocoreGalvanus_ExtraCritDmg` et de `WisdomOfTheAncients_DamageReduction`, tous deux
    documentes << TOUJOURS ACTIF >>).
    ⇒ le declencheur EFFECTIF de 1145 est `get_OwnerIsCaster & TriggeringEffectIs(0x3f1)` -- soit
    EXACTEMENT le meme predicat que 1018, dont le 3e conjoint est une redite. Les deux classes
    partagent donc le gate ET diffèrent par la CONFIG lue, et par rien d'autre sur cet axe.
    L'attribution est CONFRONTEE : `tests/engine/runner/test_924r1_early_warning_override_
    overwatch_live.py` rejoue le tir bit-exact ; un 3e conjoint qui ne serait pas `YesTrigger`
    ferait diverger la salve.

    ## MAGNITUDE

    `GetOverwatchExtraDamage()` = `ConfigVar(AbilityVariableType.extraDmg = 8, GetAbilityState(this),
    config@+0x60)` avec `config@+0x60` = la config d'**`EarlyWarningOverride`** (l'argument `0x435`
    du `.ctor`), pas celle du porteur ni celle d'`InescapableDeath`. `extraDmg` EST dans
    `variablesAffectedByRarityBonus` -> scale par le multiplicateur de rarete.

    ⚠ NIVEAU -- `EarlyWarningOverride` est une ability **ACTIVE** (1077), la ou `InescapableDeath`
    est une passive : la cascade commence donc par `active_ability_level`, que
    `scale_from_source=True` renseigne a la pose depuis l'`AbilityStateReference` du caster."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """MEME corps natif que sa soeur (`AReactivateOverwatchEffect$$CreateDamageModifier`), MEME
        gate effectif (le 3e conjoint de la BASE est le `YesTrigger`), AUTRE config."""
        if not is_overwatch_triggered(att_ctx):
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        if lvl is None:                      # ConfigVar sans AbilityState -> pas de magnitude
            return None
        v = ability_var(EARLY_WARNING_OVERRIDE, EXTRA_DMG_VAR, lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, int(v)) if v else None
