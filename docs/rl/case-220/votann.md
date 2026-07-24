> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.10 Votann (8 items après exclusion PrioritisedEfficiency x4 ; namespace natif « Loki » ; IronkinSteeljack COMBAT porté — reste 7 items)

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
BLOCKER LIVE-CAST (environnement, PAS le port) : votanMemnyr absent du seed BC standard (injecte au catalogue Units
en memoire, buildNormalizedBC recalcule ses stats reelles -> spawn OK comme p-unit, 1219 usable level 50). MAIS le
cast NATIF de 1219 leve un "system error" = FindFirstObjectByType (query scene Unity absente en runner HEADLESS),
SPECIFIQUE au spawn de votanSmnSteeljack (config gameconfig, inchangeable par edit catalogue). Controles : (a)
AberrantHypermorph spawn OK live meme session ; (b) mon votanMemnyr synthetique + ability 1166 spawn genesSmnAberrant
OK (caster synthetique SAIN) -> le blocage est intrinseque a votanSmnSteeljack en headless, orthogonal au port (dont
le corps natif est byte-identique a 1166 live-valide). Live-cast confront = residu d'ENVIRONNEMENT documente.
```
```
[1221 AugmentedAssault | votanBeserk]  — [opus] direct
VAs : ExecuteBehaviour @1811b80d0 ; playbook @18111da40/@18111d690
Attack(4x Eviscerate pierce-50) & AddDynamicStatModifierEffect(1541, stat 16 FixedArmor) — patron
ProtectorImperative. Risques : cible/sens/magnitude du 1541 (self+armor vs target−armor) NON tranchés
au décompilé → i2/statModSources live.
```
```
[1206 GravitonRifle | votanIronmaster]  — [opus] direct + prérequis pierce
VAs : ExecuteBehaviour @1811e31a0 ; effet ExtraPierce @180f4be80/@180f4bc20
Attack(3x Physical range-2) + Stunned 1 round (PORTÉ) ; le +60% pierce vs Gravis/Terminator/Mechanical
= owner-effect init NON porté (factory.py:346) → prérequis canal pierce-ratio attaquant conditionnel
trait-cible. Risques : delta mesurable seulement vs cible à trait qualifiant.
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
[1207 AncestralFortune | votanUthar]  — [fable] (le + lourd)
VAs : ExecuteBehaviour @1811b1b00 ; CountReset @180e15bf0/@180e15d00 ; TriggerReset @180e15fa0/
      @180e16170/@180e15e20 ; playbook @18111b430/@18111b070
Active = +crit-chance 1485 & +block-chance 1486 (1 tour) & attaque conditionnelle 3x Plasma
(First(SortUnitsByDamageUtility(adjacents))) & ClearPersistentData. CountReset On(9) : WasCrit(caster)
OU WasBlock(target) → compteur +1 ; TriggerReset On(59 PhaseEnd) : compteur ≥6 → ResetActiveAbility.
Prérequis ABSENTS : persistent-data compteur ; ResetActiveAbility [partagé InspiredToGreatness §1] ;
prédicat WasBlock (event UnitBlocked=61) ; SortUnitsByDamageUtility. Risques : boucle 6-exact ;
Clear au re-cast.
```

**Synthèse Votann** : [opus] direct = IronkinSteeljack (PORTE), AugmentedAssault, GravitonRifle (attaque) ;
[opus]+prérequis = PredictiveGuidance, GrimEfficiency (gate stance) ; **[fable]** = FuryFromTheDelve,
EcogSupport, AncestralFortune. Débloqueurs faction : **persistent-data** (2 items ; une fois posé,
Fury/Fortune retombent quasi-[opus]), **canal pierce-ratio** (GravitonRifle + GrimEfficiency),
**repair-combat + UnitRepaired(49)** (EcogSupport, trait Mechanic faction-wide). HYPOTHÈSES : sens
du 1541 ; effet 1065 Fury ; behaviour base Steeljack (vtable).
