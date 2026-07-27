# Case study #72 : `OnMeltaDamageAbility` (+50% vs Vehicle) est DEAD CODE dans le build gqfc5mff6c

## Contexte / mandat

Audit DamageTrait : `DamageTrait.OnMelta(5)` est porte par le profil de degat `Melta` (gameconfig,
verifie). Le `TriggeredAbilityType.OnOnMeltaDamageAbility = 1211` est DEFINI mais l'ability n'est portee
NULLE PART, alors que ses deux jumeaux le sont :
- OnFire (profil `Flame`) -> `OnFireDamageAbility` PORTE (pose feu on-hit, `triggers/loki/fire.py`).
- OnToxic (profil `Toxic`) -> `OnToxicDamageAbility` PORTE (pose Contaminated sous
  `IsFirstHitInSeries & Maybe(chance=25)`, `triggers/loki/on_toxic_damage.py` ;
  cf. `case-1203-on-toxic-damage.md`). NB : au moment de CET audit la mention « PORTE » etait une
  ERREUR de constat -- le canal n'a ete porte qu'ensuite ; le verdict DEAD-CODE de Melta, lui, est
  independant (il repose sur la lecture du `CreateTrigger` de 1211, cf. plus bas).

Tache taguee `[opus?]` (effet Melta non encore RE) avec escape-hatch explicite. **Verdict : DEAD-CODE**
(l'ability ne fire jamais dans le build actif) -> **NON porte** (le porter divergerait du live).

## Ce que fait Melta (RE decompile = verite, gqfc5mff6c)

### i2 (mecanique INTENTIONNELLE)

`Keywords/DMG_Melta` (data/i2_en.json) :
> `{[piercingDmgPct]}% pierce ratio. Deals +50% damage against <style="Vehicle">Vehicle</style> units`

= "Melta : 75% pierce ratio. +50% de degat contre les unites Vehicle". Le `Melta` gameconfig =
`{"PiercingRatio": 75, "Traits": ["OnMelta"]}`. Global value `meltaDamageExtraDmgPct = 50`.

### L'effet : `Melta_ExtraDmgEffect` (EffectType 1297 = Melta_ExtraDmg)

`IdunBattle.Entities.Effects.Loki.Melta_ExtraDmgEffect$$CreateEffectDamageBonusForAttack @180f59c80` :
```
uVar1 = DamageProfileHasTrait(factory, 5=OnMelta)
uVar2 = HasTrait(factory, target@0x178, 0x405=1029=Vehicle)
cond  = op_BitwiseAnd(uVar1, uVar2)                        # profil Melta ET cible Vehicle
amt   = ConfigConst(factory, 0xf, ...)                      # 0xf -> meltaDamageExtraDmgPct = 50
src   = AbilityOrEffect.op_Implicit(0x4bb=1211)             # source = OnMelta ability
return EffectBonus.ForPercentIncrease(cond, amt=50, src)   # +50% (multiplicatif)
```
= jumeau STRUCTUREL de `BeastSlayer_ExtraDmgEffect` (`ForPercentIncrease(HasTrait(target, BigTarget|
Vehicle), ConfigConst 0xf)`, deja porte `extra_damage.py`), a la difference que le gate n'est PAS un
noeud melee mais `DamageProfileHasTrait(OnMelta)`. `ctor @180f59e50` : `BaseEffect(AbilityOrEffect
0x4bb=1211, 1, 0)`. Effet enregistre dans `EffectsDatabase.InitializeEffects` (le TYPE existe).

### Le placement : `OnMeltaDamageAbility` (TriggeredAbilityType 1211)

`IdunBattleLogic.Entities.Abilities.Damage.Loki.OnMeltaDamageAbility$$CreateBehaviour @1811c3b70` :
```
AddEffect( effectType = 0x511 = 1297 (Melta_ExtraDmg),
           source     = AbilityStateReference (caster),
           target     = First(factory+0x78) )              # FromTriggerSelector, 1 entite
```
= place l'effet `Melta_ExtraDmg` sur `First(+0x78)` (l'attaquant, d'apres la semantique du gather :
`CreateEffectDamageBonusForAttack` n'est interroge que sur les effets de l'ATTAQUANT via
`CalculateAttackerModifiersForPrediction @181000590`). Mecanisme identique a OnFire/OnToxic (pose
d'effet on-hit apres un coup de profil correspondant).

### LA RACINE : OnMelta n'a PAS de CreateTrigger

| ability                | TriggeredAbilityType | CreateBehaviour | CreateTrigger              |
|------------------------|----------------------|-----------------|----------------------------|
| OnFireDamageAbility    | 1016                 | @1811c3a60      | @1811c3ae0 (On 0x10 & DamageProfileHasTrait(1) & !TriggeringEffectIs(5)) |
| OnToxicDamageAbility   | 1203                 | @1811c3c00      | @1811c3d20 (On 0x10 & DamageProfileHasTrait(4) & !TriggeringEffectIs(0x4dc)) |
| **OnMeltaDamageAbility** | **1211**           | **@1811c3b70**  | **ABSENT (aucun symbole, aucune place dans la plage 3b70..3c00)** |

OnFire/OnToxic OVERRIDENT `CreateTrigger` (le virtuel vtable slot +0x2b8) avec un
`DamageProfileHasTraitTrigger`. OnMelta ne l'override PAS. Le framework
(`BaseTriggeredAbility.ShouldTrigger @180fbcad0` / `GetTrigger @180fbc700`) appelle ce slot pour
materialiser le trigger ; un CreateTrigger renvoyant null y ferait THROW (`FUN_1801f2270`, no-return)
-> or le jeu ne crashe PAS sur un coup Melta -> OnMelta n'est jamais evalue (jamais materialise dans
le cache global de triggers `AbilityAndEffectCache`). **Sans trigger, l'ability ne fire jamais ->
`Melta_ExtraDmg` n'est jamais pose -> le +50% vs Vehicle n'existe pas dans ce build.**

Seul autre placeur de l'effet 1297 : aucun. `SpecialIssueCombiMelta` (l'active de darkaSternguard
"Ramus") pose des effets DIFFERENTS (0x61b/0x61c = 1563/1564 via `_InitAbility` sur self@0x148), pas
1297. Aucun `Melta_InitAbility` generique. -> l'unique chemin de pose (OnMeltaDamageAbility) est mort.

## Confirmation LIVE (ground truth, build gqfc5mff6c, session Frida 71)

Carriers Melta SPAWNABLES (probe `probe_melta_carrier.py`) : `darkaSternguard` (Ramus, melee Melta,
hors pool rank 17), `tauShadowsun` (Shadowsun, RANGED Melta 2 coups pierce 75, IN pool). Cible Vehicle
spawnable : `admecDestroyer` (Sy-gex, trait Vehicle=1029, lineup). Controle non-Vehicle : `adeptCanoness`.

Runner `build#1075` (board MC1_67), Shadowsun @(2,4) a portee 2 des deux cibles :

1. **Prediction LIVE (`aiPredict`, GetAllPredictions natif) identique Vehicle == non-Vehicle** :
   - vs u77 admecDestroyer (Vehicle) : `totalDmg [6008-9014]`, appliedHits=2.
   - vs u79 adeptCanoness (non-Vehicle) : `totalDmg [6008-9014]`, appliedHits=2.
   -> AUCUN +50% vehicule dans la prediction (coherent : l'effet on-hit n'est pas encore pose).

2. **Post-coup : AUCUN effet `Melta_ExtraDmg` pose.** Shadowsun attaque u77 (Melta, DamageProfileType=8) :
   2 coups 3129 + 4248 = 7377 (dans [6008-9014] => pas de +50%). Cascade : PAS de groupe
   `OnMeltaDamageAbility`. `view` post-coup : effets de Shadowsun = {DefenderOfTheGreaterGood_ExtraDmg/
   ExtraHits, RangedSpecialist, Camouflage_HitReduction, Infiltrate} -- PAS de Melta_ExtraDmg ; effets
   du vehicule = {HeavyWeapon_ExtraDmg, HeavyGravCannon, Overwatch_AutoAttack} -- PAS de Melta_ExtraDmg.
   Re-prediction vs Vehicle apres le coup : toujours [6008-9014] (inchangee).

3. **A/B avec un jumeau qui MARCHE (OnFire)** : `adeptRetributor` (arme ranged Flame 4 coups,
   DamageProfileType=3) attaque u77 dans le MEME runner -> la cascade contient bien
   `[Group «OnFireDamageAbility»] -> [Group «Fire»] Effect_Id=104 Effect_SourceTriggeredAbility=24`.
   => Le MECANISME "pose d'effet on-hit apres un coup de profil" fonctionne live ; c'est OnMelta
   SPECIFIQUEMENT qui ne fire pas (faute de trigger).

## Verdict et decision de port

**DEAD-CODE (registered-but-dead).** `OnMeltaDamageAbility` (1211) : behaviour present, trigger absent,
jamais materialise -> le +50% vs Vehicle annonce par l'i2 est NON-FONCTIONNEL dans gqfc5mff6c.

- **NON porte.** Le port actuel (aucun Melta bonus) MATCHE le live bit pour bit
  (prediction [6008-9014] offline == live). Ajouter le +50% (effet + placement) DIVERGERAIT du live
  et casserait l'agreement -- exactement le contre-sens a eviter (cf.
  `feedback_no_unvalidatable_ability_ports` : mecanique NON confrontable -> pas de port speculatif ;
  ici le carrier est spawnable mais la mecanique ne fire PAS -> invalidable).
- **Reste documente.** Si un futur build ajoute le CreateTrigger manquant (rendant l'ability vivante),
  le port se fait alors 1:1 sur le modele BeastSlayer : classe `Melta_ExtraDmgEffect(BaseEffect)` dans
  `entities/effects/loki/extra_damage.py` avec `create_effect_damage_bonus_for_attack` gate
  `target_traits >= {"Vehicle"}` ET profil `DamageProfileHasTrait(OnMelta)`, magnitude
  `global_value("meltaDamageExtraDmgPct")=50`, `for_percent_increase(True, 50)` ; + un
  `_on_melta_damage_ability` (calque `_on_fire_damage_ability`) qui pose l'effet on-hit gate
  `DamageProfileHasTrait(OnMelta)`, cable dans `after_hit_normal_attack`. A REVALIDER live (le +50%
  devrait alors apparaitre en prediction/combat vs Vehicle) avant tout merge.

## VAs citees

- `OnMeltaDamageAbility$$CreateBehaviour` @1811c3b70 (AddEffect 1297, First(+0x78)) ; PAS de CreateTrigger.
- `Melta_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` @180f59c80 ; `$$.ctor` @180f59e50.
- Jumeaux : OnFire beh @1811c3a60 / trig @1811c3ae0 ; OnToxic beh @1811c3c00 / trig @1811c3d20.
- `BaseTriggeredAbility$$ShouldTrigger` @180fbcad0 / `GetTrigger` @180fbc700 (slot virtuel +0x2b8).
- `CalculateAttackerModifiersForPrediction` @181000590 (gather effets ATTAQUANT).
- Enums : TriggeredAbilityType 1016/1203/1211 (`triggered_ability_type.py`) ; EffectType
  Melta_ExtraDmg=1297 (`effect_type.py`) ; UnitTrait Vehicle=1029 (`traits/unit_trait.py`) ;
  DamageTrait OnMelta=5 (`damage_trait.py`).
