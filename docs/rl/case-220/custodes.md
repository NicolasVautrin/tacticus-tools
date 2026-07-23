> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.1 Custodes (7 items sur 5 kits, après exclusions 1202/1191/1183/MartialKatah)

**Constat transverse (PROUVÉ)** : deux passifs marqués MISSING par `kit-coverage.md` sont DÉJÀ
portés et câblés — l'approximation-registre du script les surestime : **DaughterOfTheAbyss**
(3 effets 1417/1418/1419, `factory.py:259-261`, validé #184) et MartialKatah (§5). **Ne PAS
re-porter (double-registre).**

```
[DaughterOfTheAbyss | custoAtlacoya passif]  — COUVERT
VAs : CreateBehaviour @180e1f540 ; effets @180f3cb60/@180f3d070/@180f3cde0 (TargetSelector @180f3cd00)
3 AddEffect owner-hosted permanents — classes DÉJÀ portées (damage_reduction.py:333/374,
extra_damage.py:497), face défense validée bit-exact #184. Optionnel : init-pose runner via
ABILITY_INIT_OWNER_EFFECTS (patron PathOfCommand, factory.py:370) = [opus] 1-liner.
```
```
[StandVigil | custoVexilusPraetor passif]  — [opus] direct
VAs : CreateBehaviour @1811a1cf0 (SetPersistentData range + 2 effets aura) ; ExtraArmor 1384
      @180f6d910 (PORTÉ status.py:82) ; ExtraDmg 1385 @180f6db90 (ForPercentIncrease 25%,
      gate OwnerIsCaster & !IsNormalAttack & IsAttackAbility) ; TargetSelector @180f6d7e0/@180f6dd30
      = SurroundingFriends(caster, GetPersistentData(range 1|2)) ; UpdateEffectRange @1811a1ed0/@1811a2020
Prérequis : classe StandVigilExtraDmgEffect (mirror trivial) + 1 ligne factory. Range dynamique/
   RefreshEffects/persistent-data = face runtime-pose NON requise pour la prédiction (capté live).
⚠ VALIDATOR : le docstring de StandVigilExtraArmorEffect (porté) dit « SELF-buff » alors que le
   TargetSelector est SurroundingFriends (AURA sur les ALLIÉS) → self.ability_level = niveau du
   BÉNÉFICIAIRE : magnitude fausse SAUF si extraArmor/extraDmgPct level-flat — à confirmer gameconfig.
```
```
[1195 TalonsOfTheEmperor | custoAtlacoya active]  — [opus]+prérequis
VAs : ExecuteBehaviour @18120f910 ; GetExtraDamage @18120fdb0 ; MeetSecondDamageProfileRequirement
      @1812100d0 ; tracking @1811a3440 ; playbook @181169900 (Comparable)
Arbre : damage = MinMax + ConfigVar(8)=728 x EffectLevel(effet capté 1420 sur caster) ;
   profil Power→Direct si cible Psyker OU un ami adjacent AdeptusCustodes (HasFaction 18) ;
   tracking = AddEffectOrIncreaseLevel(1420) par active d'un Character ami (this battle).
Prérequis : injection extra-dmg dans la prédiction de CETTE active (lecture self.level = patron
   BeaconOfRage) ; commutation de PROFIL per-target (ABSENTE) ; écriture accumulate 1420 + execute runner.
Découpe : 2 tranches (prédiction ; runner tracking+execute). Risques : scope du compteur (Character-only,
   this-battle — CreateTrigger du tracking à lire) ; faction 18 à dériver (précédent RitesOfBattle #49).
```
```
[LegacyOfCombat | custoBladeChampion passif]  — [opus]+prérequis (candidat fable)
VAs : CreateBehaviour @180f8a660 ; CreateTrigger @180f8aac0 ; profils @180f8ac70/@180f8abe0 ;
      playbook @181167830/@181167880
Arbre : trigger = On(0xb UnitAbility) & OwnerIsActor & !CurrentAbilityIs(self)
   & TimesAttackMadeThisTurn == 1 (« après la 1re attaque du tour ») ;
   behaviour = If(BigTarget adjacent, attaque mono 1x Piercing sur First(SortTargetsByDamagePrediction
   (Randomize(bigT))), attaque TOUS les adjacents 3x Power).
Prérequis : TimesAttackMadeThisTurn ; CurrentAbilityIs ; vecteur On(11)-après-Nième-attaque ;
   attaque triggered MULTI-CIBLE (les portées sont mono). Template : PsykerExtraAttackAbility.
Risques : ne PAS dupliquer le +33%/tour (vient de MartialInspiration 1191 via effet 0x580) ;
   3e sous-tranche = playbook positionnement.
```
```
[UnwaveringSentinel | custoKyrus passif]  — [fable]
VAs : CreateBehaviour @1811aade0 ; GetAddEffectBehaviour @1811aafe0 (AddEffect 1439) ;
      GetCounterAttackBehaviour @1811ab060 ; effet 1439 : @180f76220 (TriggerAbilityDelayed 1449, 3) /
      condition @180f76260 (OwnerOrOwnerTileIsTarget & Contains(ValidNormalAttackTargets(range 2→1)))
Mécanique : quand Tyrith est CIBLE d'une attaque (tour ennemi) et l'attaquant est à portée →
   contre-attaque différée 1449 (2x Bolter) sur l'attaquant vivant.
Prérequis ABSENTS : vecteur réactif on-being-attacked (défenseur) ; TriggerAbilityDelayed (file
   différée post-résolution) ; ValidNormalAttackTargets ; classes 1439/1449.
Risques : réaction pendant le TOUR ENNEMI (validation replay-diff sur tour adverse) ; ordre file
   différée vs résolution.
```
```
[1184 MomentShackle | custoTrajann active]  — [fable] (sous-tranche décision-heal isolable [opus])
VAs : ExecuteBehaviour @1811f4620 ; GetHealAmount @1811f48e0 ; triggered @18110c740/@18110c8f0 ;
      playbook @18114c7f0/@18114c8d0/@18114c6e0
Arbre : Heal(self, var 0x20) & stat-mods 1391 (+20% BLOCK_CHANCE stat 7) / 1392 (+873 BLOCK_DAMAGE
   stat 8) & marqueur 1393 (TurnsFromRounds 0x45) ; triggered = On(0x1f=31 PreUnitMove) &
   HasEffect(1393) & AreEnemies & IsAdjacent(3) → attaque Bolter 2 hits sur l'ennemi adjacent QUI PART.
Prérequis ABSENTS : vecteur On(PreUnitMove=31) + géométrie hex-de-DÉPART (dispatch n'a que
   after-move) ; stat-mod BLOCK_CHANCE (stat 7 — seul stat 8 a un précédent AnvilShield hits.py:372) ;
   classes 1393/1394 ; face combat active non portée.
Découpe : (1) DÉCISION heal (template heals.py) = [opus] isolable — rend l'active non-NO-OP côté IA ;
   (2) combat active ; (3) vecteur réactif + attaque triggered.
```
```
[LegendaryCommander | custoTrajann passif]  — [fable], le plus lourd du lot
VAs : CreateBehaviour @1811074d0 (AddEffect 1394 & 1395) ; base TargetSelector @180f48160 /
      ActiveCondition @180f48140 ; ExtraDamage 1394 @180f54050 ; ExtraHits 1395 @180f54200 /
      IsValidAttack @180f54b70 / marquage @180f54710/@180f545b0/@180f548b0/@180f54a10/@180f54780 /
      RevertInternal @180f54cc0
Arbre : TargetSelector = AdjacentEnemies(Filter(Friends(caster), HasUsedActiveAbilityThisTurn)) —
   aura sur ENNEMIS re-ciblée CHAQUE tour. 1394 = +800 FLAT reçu des attaques amies (canal défense).
   1395 = +2 hits pour la 1re attaque NON-normale par (attaquant, cible), marquage via
   AddToPersistentDataList sur On(10).
Prérequis ABSENTS : aura-sur-ennemis re-évaluée/tour ; PERSISTENT DATA LIST (Add/IsIn/clear) ;
   IsFirstHitGroupInAttack ; IsPartialAttackAbility ; TriggeringAbilityIsNormalAttack ;
   canal +hits cross-unité (les hits d'un ami dépendent d'un effet sur l'ennemi + état de marquage).
Risques : état PARTAGÉ + deux effets sur cible ennemie déclenchés par des attaquants ALLIÉS.
```

**Synthèse Custodes** : couvert = DaughterOfTheAbyss ; [opus] direct = StandVigil ; [opus]+prérequis =
TalonsOfTheEmperor, LegacyOfCombat (candidat fable) ; **[fable]** = UnwaveringSentinel, MomentShackle,
LegendaryCommander. HYPOTHÈSES restantes : magnitudes i2 (728/800/291/873/25%/20%) — index ConfigVar
prouvés, noms gameconfig à mapper ; mécanisme exact range 2→1 (UnwaveringSentinel).
