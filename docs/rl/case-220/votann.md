> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.10 Votann (namespace natif « Loki ») — IronkinSteeljack / AugmentedAssault / GravitonRifle / AncestralFortune (volet actif) PORTES ; trait `PrioritisedEfficiency` volet DEGAT PORTE (#121)

```
[1219 IronkinSteeljack | votanMemnyr]  — [opus] direct — PORTE + valide offline (etat reel), live-cast BLOQUE headless
VAs : ctor @1811ebc30 ; ExecuteBehaviour = @1811b0550 (gshared DEDUPLIQUE, NON attache) ; playbook @181146a60/@181146860
RE RESOLU (le "forme = TestSummon" du resume etait imprecis) : l'ExecuteBehaviour d'IronkinSteeljack N'A PAS de
symbole dedie ; son slot methodPointers (@0x1830f8110, juste apres son ctor @1811ebc30 @0x1830f8108) pointe vers
@1811b0550 = EXACTEMENT le slot ExecuteBehaviour d'AberrantHypermorph (@0x1830f6fb0, apres son ctor @1811b0730
@0x1830f6fa8). IL2CPP a DEDUPLIQUE deux corps byte-identiques -> IronkinSteeljack = CLONE EXACT d'AberrantHypermorph
(1166), seule la config per-instance differe. ctor @1811ebc30 = TargetingOptions(0, statsFromClass, 1, 0x1040) +
AActiveAbility(...,2,0) IDENTIQUE a AberrantHypermorph @1811b0730 (le "2" != count spawn). gameconfig =
{unitId: votanSmnSteeljack} + summonHp/summonDmg/summonArmor (memes variables que 1166), PAS de count -> count=1
(confirme : @1811b0550 n'a PAS le Nullable(2)@options+0x40 de TestSummon @1811c7cd0). onAppearance = attaque
(PerformAIAttackFromCurrentPosition installe @options+0x18 dans @1811b0550 -- present, contrairement a TestSummon).
Arbre : Spawn(votanSmnSteeljack, TILE adjacent-self, WithStatsFromConfig(AbilityLevelAmount(Self,1219)), count=1,
onAppearance PerformAIAttack). no-move-this-turn : 1219 hors des frozensets base.py -> defauts (SetsEndTurnFlags=True)
-> FinishUnitTurn (caster no-move). Flag 0x23 sur le SUMMON = no-op runner (comme 1166).
PORT : engine/runner/abilities/votann.py (feuille SpawnSteeljack = clone SpawnAberrant config 1219) ; handler.py
ABILITY_CLASSES[1219]. VALIDE offline (test_ironkin_steeljack_live.py FACE 1, etat REEL charge, level 50 mult 180 :
spawn 1 votanSmnSteeljack, hp_max=8973=summonHp[50]x180, atk=2992=summonDmg[50]x180, on-appearance total=843,
turn_finished=True) + zero-regression (aberrant + damage).
LIVE-CAST : CONFRONTE ET VALIDE (case-92, 2026-07-25). L'ancien verdict "system error =
FindFirstObjectByType, blocage intrinseque a votanSmnSteeljack en headless" est REFUTE — le cast fonctionne en
runner headless. Deux causes cumulees, aucune liee a la scene Unity : (a) la config d'ability d'IronkinSteeljack
manquait dans BC.Abilities (aucune unite du seed BC ne la porte) -> AbilitiesConfiguration$$GetActive rend une
AbilityConfiguration VIDE, et AbilityConfiguration$$GetVariableForLevel LEVE -> "system error" ; (b) la tuile-cible
prise (targets[0] d'abilityTargets = tout l'ensemble castable) n'etait PAS adjacente au caster -> ok:true /
mutated:false / spawned:0 (controle : AberrantHypermorph 1166, live-validee, donne le MEME spawned:0 sur une tuile
non adjacente). Les deux corriges, le summon apparait avec hp_max=8973 / atk=2992 / fixedArmor=2194 + attaque a
l'apparition = les valeurs assertees offline. PIEGE : le summon porte le visualId `votanNpc2Steeljack`, pas
`votanSmnSteeljack`. Mecanisme + validation : docs/rl/case-92-catalog-injection.md
(scripts/python/catalog_inject.py, tests/engine/runner/test_catalog_inject_live.py).
```
```
[1221 AugmentedAssault | votanBeserk]  — PORTE + VALIDE LIVE (#113)
`IdunBattleLogic.Entities.Abilities.Active.Loki.AugmentedAssaultAbility$$ExecuteBehaviour` (MIRROR) :
    op_BitwiseAnd(
      AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(entities,0),
                             Nullable(GetDamageProfile(0)=Eviscerate), GetHits(0)=nrOfHits=4,
                             AbilityOrEffect(this+0x10=1221)),
      AddDynamicStatModifierEffect(targets=target@0x178, source=self@0x148, 0x605=1541,
                                   stat=0x10=16 FixedArmor, AbilityStateReference, duree=<aucune>) )
SENS/CIBLE TRANCHES AU DECOMPILE (les deux « risques » sont leves) :
 - QUI porte : `IdunBattleLogic.Entities.DSLFactory$$AddDynamicStatModifierEffect` (overload 8 args)
   -> `AddStatModifierEffectBehaviour$$.ctor(.., +0x58=source=param_3, +0x60=targets=param_2, ..)` ;
   son `$$Execute` ITERE **+0x60** (une instance par element) et attribue la ValueModification a
   **+0x58**. Le call-site passe target@0x178 en param_2 -> la CIBLE porte le malus. (Le helper jumeau
   `$$AddDynamicStatModifierEffectToOwner` met self@0x148 dans les DEUX slots = self-buff.)
 - SIGNE : les 3 stat-mods du lot n'ont AUCUNE classe native ; ce sont des
   `IdunBattle.Entities.Effects.DynamicStatModifierEffect` GENERIQUES instancies par des lambdas de
   `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects`. La magnitude sort du corps generique
   `DynamicStatModifierEffect$$GetDynamicStatModificationAmount` =
   `ConfigVar(<abilityId>, EffectSource(Get(entities)), <varKey>)` puis `isNegative ? -a : a`
   (champ +0x4a4, 4e arg du ctor). Lambda 1541 =
   `…EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_533` :
   `DynamicStatModifierEffect(AbilityType(0x4c5=1221), 0x30=48 armorReduction, isNegative=1, 1)`.
 - DUREE : aucun noeud de duree (+0x78=0) et 0x605 ABSENT du switch
   `idun…StaticBattleRules.Effect$$DefaultAmountOfRounds` (lu EN ENTIER : 0x4f=3 ; 0x429/0x48a=1 ;
   5/0x11/0x12/0x3a/0x4dc/0x5c4=2) -> duree 0 = PERMANENT (« rest of the battle »).
GROUND TRUTH LIVE (runner 696, necroWarden) : fixedArmor 2008 -> 1011 = **-997** =
armorReduction[L50]=554 x mult 180 ; effet sur la CIBLE, ABSENT du caster ; port == live per-coup.
PORT : `engine/runner/abilities/votann.py` (`augmented_assault_tree`) + feuille DSL
`AddDynamicStatModifierEffect` (behaviours/effects.py) + `AugmentedAssaultReduceArmorEffect`
(`engine/entities/effects/loki/votann.py`). Face DECISION (`…AugmentedAssaultPlaybook$$…`) NON portee.
```
```
[1206 GravitonRifle | votanIronmaster]  — PORTE + VALIDE LIVE (#113), canal percage CREE
`IdunBattleLogic.Entities.Abilities.Active.Loki.GravitonRifleAbility$$ExecuteBehaviour` (MIRROR) :
    op_Addition( AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(entities,0),
                                        Nullable(Physical), GetHits(0)=3, AbilityOrEffect(1206)),
                 AddEffect(0x48a=1162 Stunned, stateRef, target@0x178,
                           TurnsFromRounds(GetNumberConstant(config@0x60, 0x45=69 nrOfRounds))) )
OWNER-EFFECT 0x5cc=1484 : ajoute au porteur a la CREATION par le dict natif
`idun…StaticBattleRules.ActiveAbility$$GetEffectToBeAddedToOwnerForAbility` (ActiveAbility +0x50) —
porte (`ABILITY_OWNER_EFFECTS`, factory.py) + branche dans `_seed_ability_owner_effects` (spawn.py).
`IdunBattle.Entities.Effects.Loki.GravitonRifle_ExtraPierceEffect$$CreatePiercingBonusForAttack` :
    ForAddition( (get_OwnerIsCaster & CurrentAbilityIs(AbilityOrEffect(0x4b6=1206)))
                 & (HasTrait(target@0x178,0x40f=1039 TerminatorArmour)
                    | HasTrait(target@0x178,0x3f5=1013 MkXGravis)
                    | HasTrait(target@0x178,5 Mechanical)),
                 ConfigVar(0x3f=63 extraPierceRatio, GetAbilityState(this), this+0x60) )
CANAL PERCAGE CREE (c'etait le prerequis) : `BaseEffect.create_effect_piercing_bonus_for_attack` +
agregateur `piercing_bonus_from_effects` (mirror `BaseEffect$$PiercingBonusForAttack`), consomme par
`profile_pierce(..., effect_bonus=)` — le terme Fix64 que
`DamagePrediction$$GetAttackPiercingDamageRatio` additionne AVANT le `Min(100, …)`.
GROUND TRUTH LIVE (contraste a fixedArmor EGAL 2008) : necroWarden (Mechanical) **-6758** vs
bloodMephiston (non qualifiant) **-3548** ; le port reproduit les DEUX totaux, et l'A/B (effet 1484
consomme) ne bouge QUE sur la cible qualifiante. `GravitonRifle_ExtraPierce` est bien present sur Vynn
au deploiement. Face DECISION (`…GravitonRiflePlaybook$$…`) NON portee.
```
```
[PredictiveGuidance | votanMemnyr passif]  — [opus]+prérequis
VAs : CreateBehaviour @1811136f0 ; effets 1535/1536/1537 @180f65xxx ; BonusCondition @180f65860
3 effets HOSTÉS-SUR-ENNEMI (rayon 2 d'Ammuk) boostant les attaques amies Votann/Mechanical (≠ Ammuk) :
+655 melee si l'ennemi n'a PAS bougé au dernier tour, +655 ranged s'il a bougé, +1 hit. Templates :
Markerlight/Doom (topologie) + AstartesBanner (extra-hit). Prérequis : prédicat « CIBLE a bougé à son
dernier tour » (has_moved existe pour l'attaquant, pas la cible-porteuse). Risques : tour PRÉCÉDENT
vs courant ; auto-exclusion d'Ammuk.
```
```
[GrimEfficiency | votanUthar passif]  — [opus]+prérequis, GATE DUR PrioritisedEfficiency
VAs : CreateBehaviour @180f83870 ; ActiveConditions @180f4bed0/@180f4bfe0 ; playbook @181166db0
2 auras rayon-2 gatées par la STANCE d'Uthar : +437 Armour si HasEffect(1479), +20% pierce si
HasEffect(1480). Template imperative aura + ActiveCondition. PORTER APRÈS PrioritisedEfficiency
(sans les effets de stance : inerte + invalidable). Prérequis : aura rayon-2 (imperative = ring-1) ;
pierce-ratio en AURA.
```
```
[FuryFromTheDelve | votanBeserk passif]  — [fable]
VAs : CreateTrigger @180f81960 (On 0x2b=43 PreUnitAbility | On 0x26=38 NormalAttack) ;
      CreateBehaviour @180f81530 ; @180f81a70
2 events coordonnés par PERSISTENT DATA : pré-attaque → mémorise « cible >50% PV » ; post-attaque →
si flag, attaque bonus 2x Eviscerate + effet 1065. Prérequis ABSENTS : substrat persistent-data
(Set/Get keyé AbilityOrEffect) + coordination inter-event. Mutualisé AncestralFortune.
```
```
[EcogSupport | votanIronmaster passif]  — [fable]
VAs : CreateTrigger @180e220d0 (On 0x31=49 UnitRepaired) ; CreateBehaviour @180e21d70 ;
      @180e21cf0/@180e22160/@180e22210 ; init @180e22280
Sur repair de Vynn : si <3 E-COG → Spawn(votanSmnEcog) ; sinon un E-COG adjacent répare aussi
(PerformAIAbility-repair). Prérequis ABSENTS : ACTION repair combat + event UnitRepaired(49) (le trait
Mechanic n'est exécutable nulle part — repair.py = utilité IA seule) ; PerformAIAbility(repair) ;
tracking AlreadySummonedUnits. Non isolable sans le substrat repair d'abord.
```
```
[1207 AncestralFortune | votanUthar]  — VOLET ACTIF PORTE + VALIDE LIVE (#113) ; RESET hors perimetre
`IdunBattleLogic.Entities.Abilities.Active.Loki.AncestralFortuneAbility$$ExecuteBehaviour` (MIRROR) :
    turns = TurnsFromRounds(1)
    crit  = If( AmountIsGreaterThanZero(StatAmount(self@0x148, 9=CritChance,  3=INITIAL)),
                AddDynamicStatModifierEffectToOwner(0x5cd=1485, stat 9, turns) )
    block = If( AmountIsGreaterThanZero(StatAmount(self@0x148, 7=BlockChance, 3=INITIAL)),
                AddDynamicStatModifierEffectToOwner(0x5ce=1486, stat 7, turns) )
    tgt   = First(SortUnitsByDamageUtility(NormalUnits(AdjacentEnemies(caster@0x160,@0x168,1),3),
                                           MinMaxDamage(entities,1), 3), 1)
    atk   = If( AmountIsGreaterThanZero(tgt),
                AttackWithAttackDamage(caster@0x160, tgt, MinMaxDamage(entities,0),
                                       Nullable(Plasma), GetHits(0)=3, AbilityOrEffect(1207)) )
    clear = ClearPersistentData(AbilityOrEffect(1207), self@0x148, <type>)
    Execute( ((crit & block) & clear) & atk )
Les deux gates sont les corps EXACTS de `…AncestralFortuneAbility$$CanAddCritChance` /
`$$CanAddBlockChance`. `…$$GetAttackTarget` = le meme `First(SortUnitsByDamageUtility(NormalUnits(
AdjacentEnemies)))`, `…$$GetPossibleAttackTargets` = `NormalUnits(AdjacentEnemies)`, et
`…$$GetDynamicInvalidCasterReason` = `if CanAddCrit -> 0 ; if CanAddBlock -> 0 ; if Count(possible)>0
-> 0 ; else 2`. `MinMaxDamage(entities,1)` = branche `useAverage != 0` de
`IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` = `Half(Sum(Direct(minDmg),Direct(maxDmg)))`.
Effets : lambdas `…EffectsDatabase…b__14_520` (AbilityType 0x4b7=1207, var 0x41=65 extraCritChance,
isNegative=0) et `…b__14_519` (meme ability, var 0x3e=62 extraBlockChance) -> stats 9 / 7 sur le CASTER.
GROUND TRUTH LIVE — le GATE est le fait dominant : un heros FRAIS a critChance/blockChance de BASE = 0
(ces stats viennent des ITEMS, strippes par la normalisation) -> AUCUN des deux buffs n'est pose (c'est
ce que la campagne #92 avait lu comme « AncestralFortune sans effet »). Avec `rl_duel build --crit
10,300 --block-player 12,400` (option `--block-player` AJOUTEE, pendant de `--block-target`) : les deux
buffs apparaissent et critChance 10 -> 40 / blockChance 12 -> 42 = **+30/+30** = extraCritChance[L50] /
extraBlockChance[L50] (NON rarity-scale : `variablesAffectedByRarityBonus` de 1207 = [minDmg,maxDmg]).
`SortUnitsByDamageUtility` : PORTE — `engine/runner/operations/damage_utility.py`, mirror de
`IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select` (argmax du composite
Damage(0x22=34), `OrderBy(-utilite)`), etage EXTRAIT de `_finaljustice_target` et desormais PARTAGE.
`ClearPersistentData` : no-op documente (substrat persistent-data absent).
RESIDU MESURE (canal PARTAGE, hors #113) : en regime CRIT, sur C1_74/777 le natif crit 1/3 la ou le
port (meme rng cale, meme crit-chance 40) crit 2/3 — MEME roll de degat (1339), seul le verdict de
`DamageCalculations$$RollCritical` differe ; MC1_67/31337 concorde 3/3. Le regime SANS buff est
bit-exact sur les deux boards. Le test confronte COUP PAR COUP et borne ce residu a 1 verdict.
HORS PERIMETRE (inchange) : `…AncestralFortune_CountResetAbility$$CreateTrigger`/`$$CreateBehaviour`
+ `…AncestralFortune_TriggerResetAbility$$CreateTrigger`/`$$CanReset`/`$$CreateBehaviour`
(persistent-data compteur, ResetActiveAbility, predicat WasBlock/UnitBlocked) ; playbook
`…AncestralFortunePlaybook$$MakeDamagePredictions`/`$$ShouldExecute`.
```

```
[PrioritisedEfficiency | trait 0x423=1059, LES TROIS Votann]  — VOLET DEGAT PORTE + VALIDE LIVE (#121)
Systeme de STANCES a 5 effets (1479 marqueur HostileAcquisition, 1480 marqueur FortifyTakeover,
1481 ExtraDmg, 1482 ExtraMovement, 1483 DmgReduction). i2 : « au debut de chaque tour et jusqu'a la fin
de ce tour, l'unite gagne un effet selon sa stance ; quand un allie a PrioritisedEfficiency utilise une
active, la stance bascule pour TOUS les allies portant le trait. Hostile Acquisition : +{[extraDmgPct]}%
Damage with all attacks et +1 Movement. Fortify Takeover : -{[dmgReductionPct]}% Damage. »

PORTE (les DEUX faces de degat, mirror 1:1) :
  `IdunBattle.Entities.Effects.Loki.PrioritisedEfficiency_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`
      = EffectBonus.ForPercentIncrease( DSLFactory.get_OwnerIsCaster, DSLFactory.ConfigConst(0xf) )
  `IdunBattle.Entities.Effects.Loki.PrioritisedEfficiency_DmgReductionEffect$$CreateEffectDamageMalusForDefense`
      = EffectBonus.ForPercentDecrease( DSLFactory.get_OwnerIsTarget, DSLFactory.ConfigConst(0x72) )
-> `engine/entities/effects/loki/extra_damage.py::PrioritisedEfficiencyExtraDmgEffect` (jumeau EXACT de
`RapidAssault_ExtraDamage`) et `.../damage_reduction.py::PrioritisedEfficiencyDmgReductionEffect`
(jumeau de `MartialKatah_DmgReduction`, SANS son gate `IsNormalAttack`) ; factory.py 1481/1483.

REPONSES AUX 4 QUESTIONS D'ETAGE (toutes LUES au decompile) :
 * ATTAQUANT, pas reduction cible : le seul noeud de condition est `get_OwnerIsCaster`, et l'effet
   n'expose AUCUN `CreateEffectDamageMalusForDefense` -> un porteur ATTAQUE ne gagne rien. (Le volet
   defensif est l'effet SEPARE 1483, `get_OwnerIsTarget`, l'autre stance.)
 * TOUTES les attaques : pas de `IsNormalAttack`, pas de `IsMeleeAttack`/`IsRangedAttack`, pas de
   `HasTrait(cible,..)`, pas de `CreateActiveCondition`, pas de `CreateTargetSelector` -> attaque
   NORMALE **et** attaques d'ABILITY, melee comme distance, prediction comme combat.
 * ETAGE : `ForPercentIncrease` -> %-list du `DamageModifiers` ATTAQUANT
   (`IdunBattle.Core.Services.DamageModifiers$$Add`), consommee par
   `IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers` **APRES** percage/armure
   (`...DamagePrediction$$CalculateBaseDamageWithAllModifiers`) et AVANT l'additif @+0x10 ; les
   limites de trait (`ApplyTraitDamageLimitsTo*`) et le block restent en AVAL, inchanges.
 * 25 n'est PAS un litteral : `ConfigConst(0xf)` -> `ConfigAmount$$Calculate` ->
   `AbilityConfiguration$$GetNumberConstant(0xf)` de la config designee par la SOURCE de l'effet
   (`AbilityOrEffect(0x5ce)` = **TriggeredAbilityType**.PrioritisedEfficiency=1486, PAS EffectType
   1486 = AncestralFortune_ExtraBlockChance) = `globalValues.traitVariables
   .prioritisedEfficiencyExtraDmgPct`. COMMENT ON LE SAIT malgre la DEDUPLICATION IL2CPP des deux
   ctors (corps byte-identiques -> un seul code) : la table FRIDA (amont) attribue le RVA `f66060` a
   `PrioritisedEfficiency_ExtraDmgEffect..ctor` et n'a AUCUNE ligne pour
   `PrioritisedEfficiency_DmgReductionEffect..ctor`, tandis que ghidra (aval) a pose l'etiquette
   `...PrioritisedEfficiency_DmgReductionEffect$$.ctor` sur `180f66060`. Les deux noms designent donc
   le MEME corps, celui qui lit `BaseEffect(AbilityOrEffect(0x5ce), 1)` — piege classique : se fier a
   la seule etiquette ghidra aurait fait croire que 1481 n'a pas de ctor lisible.
   Clef 0xf = generique `extraDmgPct` (precedents `rapidAssaultExtraDmgPct`,
   et 0x72 = `<trait>DmgReductionPct` chez MartialKatah) ; placeholders i2 `{[extraDmgPct]}` idem.

DISCRIMINATION D'ETAGE — mesure qui invalide le cas nominal de #113 : `GetDamageWithPiercing` =
`max(0, dmg-armure, dmg x percage/100)`. En regime PLANCHER-PERCAGE, +25 % pre-percage et post-percage
donnent le MEME nombre. Sur `necroWarden` (armure 2008, percage 50, bornes [1595,2394]) les 4 coups
sont dans ce regime -> ecart POST/PRE = 0 : le cas #113 prouvait la MAGNITUDE, pas l'ETAGE. Etat
CRAFTE `genesMagus` (armure 1106) : 3 coups sur 4 basculent en regime ARMURE si le bonus est pose
pre-percage -> ecarts 180/149/203 ; le live valide POST sur les 4 (1286/1256/1309/1081 bit-exact) et
refute PRE sur les 3 discriminants. (`adeptRetributor`, armure 1205 : 2 coups discriminants, idem.)

NON PORTE (residus nommes) :
 * POSE/BASCULE des stances — `...APrioritisedEfficiencyAbility$$GetSetOffensiveStanceBehaviour`
   (= `RemoveAllStanceEffects & AddEffect(1479) & AddEffect(1481) &
   AddStaticStatModifierEffectToOwner(1482) & SetPersistentData`), `$$GetSetDefensiveStanceBehaviour`,
   `$$GetRemoveAllStanceEffectsBehaviour`, `$$GetStanceDefiningUnit`, `$$GetSwitchStanceCounter`,
   `$$GetShouldSwitchStance`, `$$IsTeamCurrentlyInOffensiveStance` + les 4 triggered
   `PrioritisedEfficiency_{Init,UpdateStance,Counter,ResetCounter}Ability`. Trigger d'init =
   `OnOwnerSpecificAbilityInit & AmountIsGreaterThanZero(CurrentPlayerTurnsStarted)` ; behaviour =
   `If( AreEqual(self, GetStanceDefiningUnit) OR Not(HasEffect(stanceDefiner, 1480)), offensive,
   defensive )` -> **stance OFFENSIVE par defaut** (ce que l'etat live capte montre). La bascule lit
   `GetPersistentData`/`AmountIsOdd(GetSwitchStanceCounter)` : PREREQUIS = substrat persistent-data
   (le MEME que FuryFromTheDelve / AncestralFortune-reset). En attendant, les effets sont SEEDES
   depuis `decisionView.effects` (le replay live-confronte est donc exact ; une bataille 100 %
   offline n'aurait pas la stance).
 * 1482 `PrioritisedEfficiency_ExtraMovement` (stat-mod MOVEMENT, template Waaagh/BlackRage) :
   ANOMALIE non tranchee — son ctor `...PrioritisedEfficiency_ExtraMovementEffect$$.ctor` construit
   `StaticStatModifierEffect(AbilityOrEffect(0x50f), ...)` avec 0x50f = 1295 =
   TriggeredAbilityType.**PriorityReclamation** (une AUTRE ability), alors que 1481/1483 pointent
   bien sur 0x5ce. Tant que cette source n'est pas expliquee, le porter serait deviner la magnitude
   -> laisse en residu (aucun effet sur le degat).
 * Les marqueurs 1479/1480 restent `BaseEffect` nu : ils n'ont AUCUNE methode native (ils ne servent
   qu'aux `HasEffect` des behaviours de stance et de `GrimEfficiency`) — les porter serait un
   double-compte.
GATE LEVE : `GrimEfficiency` (auras gatees `HasEffect(1479)`/`HasEffect(1480)`) n'est plus bloque par
l'absence des marqueurs — ceux-ci sont SEEDES et lisibles ; il reste bloque par ses propres prerequis
(aura rayon 2, pierce-ratio en aura).
```

**MAJ #121 (trait PrioritisedEfficiency, volet degat)** : le SHIM de mesure que #113 avait pose dans
`test_votann_lot1_live.py` (contribution %-degat recablee a la main sur l'instance d'effet) est
**SUPPRIME** ; la confrontation port/live des 3 actives Votann passe desormais par le pipeline complet.
Nouveau fichier `tests/engine/runner/test_prioritised_efficiency_live.py` (etage discriminant, vecteur
attaque NORMALE, orientation attaquant/defenseur, magnitude-config, inertie des marqueurs) et probe
`scripts/python/probe_121_prioritised_efficiency.py` (phases `regime` / `normal` / `defense`).

**MAJ #113 (lot 1 livré)** : `IronkinSteeljack` (1219), `AugmentedAssault` (1221), `GravitonRifle`
(1206) et le VOLET ACTIF d'`AncestralFortune` (1207) sont PORTÉS et VALIDÉS LIVE, avec leurs 4 effets
(1541 / 1484 / 1485 / 1486). Trois débloqueurs transverses ont été créés au passage :
  * **canal PERÇAGE conditionnel** — `BaseEffect.create_effect_piercing_bonus_for_attack` +
    `piercing_bonus_from_effects` (mirror `BaseEffect$$PiercingBonusForAttack`), consommé par
    `profile_pierce(..., effect_bonus=)`. Débloque aussi `GrimEfficiency_ExtraPierce` (1488),
    `RelicBoltPistol_ExtraPierce`, `Hailstrike_ExtraPierce`, `Supercharge_ExtraPiercing`,
    `AllIsDust`, `WallOfMirrors`, `HeavyGravCannon`, `BloodChalice_HealOnAttack` (mêmes symboles
    `…$$CreatePiercingBonusForAttack`).
  * **feuille DSL `AddDynamicStatModifierEffect`** (+ son jumeau `…ToOwner`) — la paire de slots
    source(+0x58)/targets(+0x60) qui tranche « self-buff vs debuff sur la cible ».
  * **`SortUnitsByDamageUtility`** extrait en port partagé (`operations/damage_utility.py`).
Restent Votann : `PredictiveGuidance`, `GrimEfficiency` (gate stance), `FuryFromTheDelve`,
`EcogSupport`, le RESET d'`AncestralFortune`, le trait `PrioritisedEfficiency` (5 effets, x7 porteurs).

**Synthèse Votann** : [opus] direct = IronkinSteeljack (PORTE), AugmentedAssault, GravitonRifle (attaque) ;
[opus]+prérequis = PredictiveGuidance, GrimEfficiency (gate stance) ; **[fable]** = FuryFromTheDelve,
EcogSupport, AncestralFortune. Débloqueurs faction : **persistent-data** (2 items ; une fois posé,
Fury/Fortune retombent quasi-[opus]), **canal pierce-ratio** (GravitonRifle + GrimEfficiency),
**repair-combat + UnitRepaired(49)** (EcogSupport, trait Mechanic faction-wide). HYPOTHÈSES : sens
du 1541 ; effet 1065 Fury ; behaviour base Steeljack (vtable).
