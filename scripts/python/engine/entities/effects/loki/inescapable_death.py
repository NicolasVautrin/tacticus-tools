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
