# case-366-r1 -- `1174 StructuralAnalyser_Visual` : un « _Visual » qui porte un GATE, et rien d'autre

**Question** : l'effet `1174` du passif `StructuralAnalyser` (`tauDarkstrider`) porte-t-il une
charge, ou est-il inerte ? **Reponse mesuree** : il porte une `CreateActiveCondition` GEOMETRIQUE
bien reelle, et **aucune** contribution. Les deux moities ont ete etablies separement -- le nom ne
prouve rien (cf. `1255 MartialSuperiority_Visual`, dont la condition est `NOT IsTurnOf(Owner)`).

> Enums : `1174` = `EffectType.StructuralAnalyser_Visual` (0x496) ; `1156` =
> `EffectType.StructuralAnalyserDmgBoost` (0x484) ; `1143` = `TriggeredAbilityType.StructuralAnalyser`
> (0x477) ; `1122` = `EffectType.Markerlight` (0x462).

## 1. L'identite : SOEUR de 1156, pas sa fille

`data/symbols/<build>/frida/classes.tsv` (les vrais `Il2CppClass`, lus du runtime) :

    AStructuralAnalyserEffect         -> BaseEffect
    StructuralAnalyserAdjacentEffect  -> AStructuralAnalyserEffect     (= 1156)
    StructuralAnalyser_VisualEffect   -> AStructuralAnalyserEffect     (= 1174)

Le ctor de 1174, relu octet a octet, est `xor edx,edx ; jmp <corps>` -- un `: base()` nu qui saute
sur `BaseEffect..ctor(this, AbilityOrEffect.op_Implicit(0x477), true)`. Ce corps est **DEDUPLIQUE**
(deux entrees dans la table de pointeurs de methodes) et les tables ne nomment qu'un proprietaire :
`StructuralAnalyserAdjacentEffect$$.ctor`. Le lire comme un lien d'heritage aurait fait porter a
Darkstrider le `+extraDmg` de 1156 -- c'est exactement le piege CLAUDE.md « un nom de `$$.ctor`
n'est PAS une classe ». `AStructuralAnalyserEffect` n'apparait NI dans `ghidra/functions.tsv` NI
dans `frida/methods.tsv` : toutes ses methodes ont un corps partage.

## 2. La POSE : les deux effets d'un bloc, sur le porteur

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.StructuralAnalyser_AddDamageBuffAbility$$CreateBehaviour` :

    AddEffect(0x484 = 1156) + AddEffect(0x496 = 1174)     (op_Addition ; meme abilityState, turns VIDE)

`turns` vide => PERMANENTS. Ce qui eteint 1174 est sa CONDITION.

## 3. Ce que 1174 CIBLE : `Owner` -- et c'est ce qui le separe de 1156

Sa table de methodes est `[CreateActiveCondition, CreateTargetSelector, .ctor]`, et le
`CreateTargetSelector` y porte le corps archi-partage `return <DSLSelectors+0x30>` (= `Owner`,
~250 entrees dans la table). MESURE qui tranche sans dependre du decoupage de table -- un seul
releve d'evenements, apres avoir rendu un allie adjacent :

    [Effect_Refresh e=94 «StructuralAnalyserDmgBoost»]  ReceiveEffect e=81   <- l'ALLIE
    [Effect_Refresh e=95 «StructuralAnalyser_Visual»]   ReceiveEffect e=79   <- LE PORTEUR

## 4. La CONDITION : `AmountIsGreaterThanZero(<le selecteur d'aura de 1156>)`

`IdunBattle.Entities.Effects.Loki.StructuralAnalyser_VisualEffect$$CreateActiveCondition` appelle
`...StructuralAnalyserAdjacentEffect$$CreateTargetSelector`, qui est

    Unique( AdjacentFriends(Owner) + UnitsFromFaction(SurroundingFriends(Owner, Direct(2)), 9 = Tau) )

= « un allie ADJACENT (toute faction) OU un allie T'AU a <= 2 hexes ». Selecteur d'aura PARTAGE x4
(StructuralAnalyser / SereneUnifier / DotGG / WayOfTheShortBlade, `case-220/tau.md`), deja porte
cote DotGG. Le porteur ne s'y compte pas (sinon la condition serait tautologique).

**Table de verite, MESUREE sur DEUX couples (board, seed)** -- `C3_01`/31337 et `MC1_67`/777, ami
non-T'au `astraDreir`, ami T'au `tauCrisis`, natif lu par `decisionView{includeInactive:true}` :

| d(non-T'au) | d(T'au) | natif | port |
|---|---|---|---|
| 1 | >=3 | True | True |
| 2 | >=3 | **False** | False |
| >=3 | 2 | **True** | True |
| >=3 | >=3 | False | False |

La 2e ligne est le DISCRIMINANT du tier 2 : un ami non-T'au a 2 hexes ne suffit pas. La 3e montre
que le tier T'au ring-2 suffit SEUL. Cote natif la bascule est explicite dans les evenements de
`MoveUnitOperation` : `ActivateEffect` / `DeactivateEffect e=<porteur> Effect_Id=95`.

⚠ Le canal `decisionView` par DEFAUT **filtre les inactifs** : il aurait rendu « 1174 absent »
exactement quand la condition est fausse. Toute la mesure passe par `includeInactive: true`.

## 5. Ce que 1174 ne fait PAS : aucune contribution (MESURE, pas deduction)

Le canal `...StructuralAnalyserAdjacentEffect$$CreateEffectDamageBonusForAttack`
(`ForAddition(get_OwnerIsCaster & HasEffect(target, 0x462 = Markerlight) & IsRangedAttack,
ConfigVar(8 = extraDmg))`) n'a **qu'une** entree dans la table de pointeurs de methodes. Verdict pris
sur l'etat, pas sur la table : cible MARKERLIGHTEE, Darkstrider IMMOBILE, seule la position de
l'ami change --

| board / seed | 1174 inactif | 1174 actif |
|---|---|---|
| `C3_01` / 31337 | `[18428-27640]` | `[18428-27640]` |
| `MC1_67` / 777 | `[12284-18428]` | `[12284-18428]` |

(temoin du canal : `[16024-24036]` AVANT la pose du Markerlight, soit le `x1.15` de
`MarkerlightEffect` deja porte.) => ni degat, ni coups, ni percage, ni crit.

## 6. Ce que le port inscrit, et pourquoi

`EFFECT_CLASSES["StructuralAnalyser_Visual"] = StructuralAnalyserVisualEffect`
(`engine/entities/effects/loki/structural_analyser.py`), `active_condition_ported = True`,
`seed_witness_effect = "StructuralAnalyserDmgBoost"`, et
`ABILITY_INIT_OWNER_EFFECTS["StructuralAnalyser"] = ["StructuralAnalyser_Visual"]`.
`is_active` lit la cle PARESSEUSE `structural_analyser_friends`, exposee par
`UnitEffectStateView` (`runner/components.py`) -- cle absente = non mesure = on ne ferme pas.

**Cette entree ne change AUCUN comportement** (`BaseEffect` no-op etait deja identique). Elle
existe pour deux raisons : fixer l'identite de classe -- interdire qu'on donne un jour a Darkstrider
le `+extraDmg` de 1156 en croyant 1174 derive de lui -- et rendre la condition a sa place NATIVE.

`1156` reste **NON PORTE** : c'est le cas `[opus]` `StructuralAnalyser` de `case-220/tau.md` (le
canal de degat cote ALLIES), hors perimetre de #366.

## 7. Gardes

`scripts/python/probe_1174_structural_analyser_visual.py` (`--step 1` identite offline, `--step 2`
condition, `--step 3` absence de contribution) et
`tests/engine/runner/test_structural_analyser_visual_live.py` (6 tests). Le test passe par le
CHEMIN REEL du moteur (`load_state` -> `unit_state_for_effects` -> `is_active`), donc il garde
AUSSI le mirror de selecteur de `components.py`. **Quatre mutations adversariales verifiees**,
chacune rougissant une ligne PRECISE : filtre faction retire -> regime « non-T'au a 2 » ; tier T'au
supprime -> « T'au a 2 seul » ; porteur compte -> « aucun ami » ; `is_active` non portee -> les deux
regimes negatifs.

## 8. NON COUVERT

* **Canal DEFENSIF** (degat RECU par Darkstrider) : non mesure directement -- la prediction adverse
  n'est pas lisible depuis le POV joueur. Argument de cloture : la table de methodes de la famille
  est CLOSE (9 entrees resolues, aucune methode `CreateDamage*ForDefense`), et tout canal herite
  serait partage avec 1156.
* **Le decoupage exact** des trois blocs de la table de pointeurs de methodes entre
  `AStructuralAnalyserEffect` et ses deux filles n'est pas tranche a l'octet (deux decoupages
  restent compatibles). Sans consequence : le verdict « aucune contribution » vient de la MESURE.
* **1156** : ni porte, ni confronte ici.
