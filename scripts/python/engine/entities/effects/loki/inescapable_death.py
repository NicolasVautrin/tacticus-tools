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

    18326e540  ->  InescapableDeathEffect$$.ctor
    18326e548  ->  InescapableDeathEffect$$GetHitReductionEffectType
    18326e550  ->  InescapableDeathEffect$$GetOverwatchExtraDamage        <- corps PARTAGE (cf. §5)
    18326e558  ->  InescapableDeathEffect$$GetAdditionalExtraDamageTrigger

Quatre entrees contigues, quatre methodes. **Aucune n'adresse `LegitDeathReasons`** => cette classe
n'override PAS `LegitDeathReasons` et prend celle de la base (§4). C'est l'inverse exact de sa
soeur `EarlyWarningOverride_ReactivateOverwatchEffect`, qui elle l'override.

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

`GetOverwatchExtraDamage` @`18104dd20` porte **DEUX** entrees `methodPointers` :

    18326d848  ->  EarlyWarningOverride_ReactivateOverwatchEffect$$GetOverwatchExtraDamage
    18326e550  ->  InescapableDeathEffect$$GetOverwatchExtraDamage

Un seul corps, deux proprietaires (ICF) : le code est identique parce que toute la variabilite passe
par `this` (`config@0x60`). **`EarlyWarningOverride` (1145) override donc AUSSI `GetOverwatchExtraDamage`**,
et sa variable `extraDmg` existe et est non nulle dans le gameconfig -- sa face DEGAT est VIVANTE et
n'est PAS portee. Ce n'est pas dans le perimetre de #924 (son montage est distinct : `tauCrisis`) :
residu **#924-r1**.

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

Mais le port la placait au MAUVAIS ETAGE, et c'est mesurable a la decimale :

  * ecart NATIF   overwatch - normale =  617,3 par coup ;
  * ecart PORT    nominal - mutant    =  5388 pour 6 coups = **898,0 par coup, EXACTEMENT**
    (mutant = la meme salve rejouee avec `create_effect_damage_bonus_for_attack` neutralise).

`617,3 / 898 = 0,687`. Or le rapport `degat normal / stat Attack` vaut, MESURE INDEPENDAMMENT,
`628,7 / 906 = 0,694`. **Les deux rapports coincident** : le bonus subit exactement la meme
transformation que la base. Donc le natif l'ajoute AVANT l'etage qui resout les bornes
(`DamagePrediction$$RandomlyResolveMinMaxDamage` sur des bornes calculees a partir de
`base + additif`), la ou le port l'ajoute APRES (`_reduced_bounds`, `attacker_additive_pre` =
« bornes (base +- spread) + additif », position validee bit-exact par #75 pour une AUTRE famille).

Livrer la face a cet etage-la donnerait **+45 % de degat** sur chaque tir d'overwatch d'Imospekh --
pire que l'absence, qui est le comportement actuel de `master`. La methode est donc RETIREE, pas
ecrite « en attendant » : ce module porte la RE, le registre porte l'effet, et le residu **#924-r2**
porte le seul point ouvert (l'etage). Cliquet : `test_924_inescapable_death_offline.py` rougit si
quelqu'un re-arme la face sans traiter l'etage.
"""
from __future__ import annotations

from ..base import BaseEffect
from ...ability_variable_type import AbilityVariableType
from ...effect_type import EffectType

#: `InescapableDeathEffect$$.ctor` = `AReactivateOverwatchEffect..ctor(this, 0x3ed)` -- l'ability
#: dont l'effet lit la config (`config@0x60`), donc la source de `extraDmg` ET de `hitsReduction`.
INESCAPABLE_DEATH = "InescapableDeath"

#: `GetOverwatchExtraDamage` = `ConfigVar(..., 8, ...)`. Membre NOMME (regle ENUM) : l'ordinal 8 est
#: aussi un membre valide d'`AbilityConstantType`, ou il nomme autre chose.
EXTRA_DMG_VAR = AbilityVariableType.extraDmg.name

#: Le littéral `0x3f1` des DEUX termes de declencheur, qualifie **EffectType** (la surcharge
#: `op_Implicit` @`18166a080` appelle `set_Effect`) -- pas l'`ActiveAbilityType` 1009
#: (`ResurrectionOrb`) ni le `TriggeredAbilityType` 1009 (`WhipcoilBody`), qui portent le meme
#: ordinal et n'ont rien a voir.
TRIGGERING_EFFECT_TYPE = int(EffectType.Overwatch_AutoAttack)          # 0x3f1 = 1009


class InescapableDeathEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.InescapableDeathEffect` (EffectType 0x3fa = 1018).

    Les deux `Triggered()` de `CreateHandleTriggerAbilitiesInternal` -- re-entree en overwatch apres
    un kill, et sa reduction de coups 1019 -- sont portees, et enregistrees sur le MEME effet 1018
    dans `runner/operations/triggers/loki/reactivate_overwatch.py`.

    ⚠ **La face DEGAT n'est volontairement PAS surchargee ici** : `create_effect_damage_bonus_for_attack`
    reste celle de `BaseEffect` (aucun bonus). Ce n'est ni un oubli ni du dead-code -- le natif
    APPLIQUE bien ce bonus (mesure : le tir d'overwatch fait 1,98x l'attaque normale du meme
    porteur), mais l'ETAGE ou le port sait l'injager donne +45 % de trop. Toute la mesure, et le
    seul point qui reste ouvert, sont en §6 de l'en-tete du module -> residu **#924-r2**.

    La classe reste inscrite a `EFFECT_CLASSES` pour que l'effet ait un porteur NOMME : c'est ce qui
    rend le residu visible depuis le registre, au lieu d'un `BaseEffect` anonyme qui se lirait comme
    « rien a porter ici »."""
