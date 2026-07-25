> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.15 SpaceWolves (9 items, préfixe `space*` ; exclusions 1090/1113/LordOfTempests — spaceStormcaller COMPLET)

**Substrat (grep PROUVÉ)** : aucun port combat SW ; MAIS les canaux crit-chance ET crit-dmg additifs
(base.py:213/220, damage.py:292-293), hits/dmg additifs, tuile Ice (case-35) et la résolution de block
(did_block, damage.py:448) sont PORTÉS — dé-risquent la moitié des items. L'event `UnitBlocked=0x3d`
n'est PAS émis.

```
[1089 GreatFrostAxe | spaceWulfen]  — [opus] direct -> PORTÉ + BIT-EXACT live (résidu x1.5 RÉSOLU #45f)
VAs : ExecuteBehaviour @1811e3500 ; playbook @18113fbd0 (prédiction VALIDÉE 54321 s18)
Natif EXACT (mirror 1:1) : op_BitwiseAnd( AddEffect(0x11 Ice, source=stateRef, owner@0x148,
  op_Addition(AdjacentTiles(TargetTiles@0x190), TargetTiles@0x190), Nullable ZÉROÉ -> defaut 2 rounds),
  If(IsAlive(target@0x178), AttackWithAttackDamage(caster@0x160, target@0x178, RandomAmount(minDmg,maxDmg),
  GetDamageProfile=Piercing-80, GetNumberConstant(0x2f)=nrOfHits=4, AbilityOrEffect(1089))) )
  -> GLACE d'abord (tuile cible + ring-1), PUIS attaque la CIBLE DIRECTE (mono-cible, ATTACK-family
  @180de9fb0 XREF from 1811e367f -- PAS ability-family, contraste Stormcaller). Porté `spacewolves.py`,
  enregistré handler.py, test live `test_great_frost_axe_live.py`. VALIDÉ live : zone glace = 7 tuiles
  (cible+ring1 exact), 4 coups, DEGAT PER-COUP BIT-EXACT (post #45f).
RÉSIDU x1.5 RÉSOLU (#45f fable, 2026-07-24) : l'ex-« +50% crit-sur-Ice sur coups non-crit » était un
  ARTEFACT D'ATTRIBUTION — la vraie cause = bonus d'ÉLÉVATION (`Damage.ElevationBonus`=50, feuille du
  builder attaquant PARTAGÉ @181000590, gate strict elev(att)>elev(cible) + !HasEffect(0x423) deux côtés,
  cf. CalculateElevationBonusModifier @181003ea0) que le vecteur offline `execute_ability_attack`
  n'appliquait pas (le scénario historique movait sur du surplomb -> 1.5x systématique ; l'attaque
  normale du même caster passait par le chemin qui applique l'élévation -> « pas de divergence » =
  confond parfait). PROUVÉ par sonde discriminante (`probe_45f_gfa_elevation`, une variable = la
  relation d'élévation) : pre-fix high = 1.5000x/coup À ROLLS PRNG IDENTIQUES, flat/low = bit-exact ;
  post-fix bit-exact partout. La contradiction CRIT_DAMAGE=0 est levée : la formule Ice
  (`IceEffect.CreateEffectDamageBonusForAttack @180f44940` = EffectBonus.addition
  `PercentageOf(StatAmount(attacker, CRIT_DAMAGE=10), EffectConfig(5)=25)` gate `AttackDamageIsCritical
  & AreEqual(occupant-tuiles-Ice, target) & !HasTrait(target, 0x19)`) n'a JAMAIS été la source du 1.5x :
  elle est crit-only (flag crit RÉEL per-coup injecté au ctx AbilityEntities, ExecuteHit @180e5eff0) et
  vaut 0 pour cd=0. PORTÉE (`damage_model.ice_crit_damage_addition`) + VALIDÉE live par crit forcé
  (+175 = floor(700x25/100) par coup crit, 4/4 bit-exact). Le sous-système effect-damage-bonus PARTAGÉ
  (~40 effets `CreateEffectDamageBonusForAttack`, collecteur `BaseEffect.DamageBonusForAttack @180f0f5e0`)
  a désormais ses DEUX canaux modélisés : ADDITIF ungated (AvalancheOfMuscle/TerrifyingCrescendo/
  CondemnorStake, inchangés) + ADDITION crit-gated (Ice). i2 « already applied » = note d'AFFICHAGE.
  Asymétrie de FAMILLE (décompilé) : ATTACK ExecuteHit @180e5eff0 = RollCritical + builder mods complet
  (élévation/trench) ; ABILITY ExecuteHit @180e29d50 = AUCUN crit (AttackHit isCrit=0) + mods attaquant
  ZÉROÉS (pas d'élévation) — mesuré live storm_high (Stormcaller surélevé = aucun bonus, 3/3 bit-exact).
```
```
[1097 Foehammer | spaceRockfist]  — [opus]+1 sélecteur
VAs : ExecuteBehaviour @1811df2d0 ; GetDeadHeroes @1811df610
Stun(cible, 1 round) + Attack(MinMax + var8 × Count(héros MORTS — AllDeadOrResurrectedUnits), Power-40,
1 hit). Prérequis : sélecteur AllDeadOrResurrectedUnits [PARTAGÉ RitesOfRestoration §1, SendInTheNextWave §2].
```
```
[SagaOfTheWarriorBorn | spaceBlackmane passif]  — [opus]+prérequis (borderline)
VAs : effet 1223 @180f6a710/@180f6a580 ; kill-ability @18119d640/@18119d740
Owner-effect Ragnar : EN CHARGE → +3 hits + +582 crit-dmg (canaux PORTÉS) ; au kill d'un Hero →
propage 1224 aux Space Wolves amis. Prérequis : gate IsCharging en canal COMBAT eager (status.py:437) ;
kill-propagation faction. Risques : attaque hors-charge doit annuler le bonus.
```
```
[1106 WarHowl | spaceBlackmane]  — [opus]+prérequis
VAs : ExecuteBehaviour @18122cfc0 ; @18122d1b0 ; effet 1222 @180f77990/@180f77ba0
Buff self + alliés melee-only (sans arme ranged, hors Summon) : +36% crit-chance +1164 flat, melee
normal only + grant Unstoppable (résidu inerte). Prérequis : sélecteur UnitsWithoutRangedWeapons ;
classe 1222. Canaux crit PORTÉS.
```
```
[HuntersBeyondDeath | spaceHound passif]  — [opus]+prérequis (borderline fable)
VAs : CreateBehaviour @180f87100 ; effets @180f50e80/@180f51170/@180f512d0 (1172/1190/1191)
3 owner-effects : +582 vs Psykers (offense) ; −ConfigVar défense des Psykers ennemis à dist<=2 (aura) ;
SUPPRESSION du splash psyker (1191) — le consommateur psyker.py:21 lit déjà has_effect(psyker, 1191)
TARGET-side mais RIEN ne le pose → inerte. Prérequis : 3 classes + matérialisation aura target-side.
```
```
[HealingBalms | spaceWolfPriest passif+active 1212]  — [opus]+prérequis (borderline fable)
VAs : triggered @180f85a50 ; active @1811e7830 ; effet 1508 @180f4eb80/@180f4ea60
Remplace l'active Heal(18) par 1212 : Heal(HealAmount trait Healer) + buffs crit 2 rounds (canaux OK)
+ effet différé 1508 (re-heal 3638 au turn-start suivant, patron LivingMetal). Prérequis : 1re active
HEAL dans ABILITY_CLASSES + formule HealAmount (Damage × max hits) + effet différé. Note : dp=False
en case-27 pour la décision — la face combat reste portable.
```
```
[AnvilShield | spaceRockfist passif]  — **volet ApplyIce PORTE (#222) ; reste [fable]**
VAs : @180e16340 (+ son CreateTrigger DEDUPLIQUE @180e15880 = df@0xa8) ; ApplyIce @180e16480/@180e16500 ;
      ApplyStun @180e16590/@180e16680 ; FrozenAttackerAdvantage @180e16840/@180e168e0 (effets 1200/1201/1202)
CORRECTION RE : « tout gate On(UnitBlocked) » est FAUX. `ApplyAdditionalBlockAndBlockChance @180e16340`
a pour trigger `df@0xa8` = `On(0x21=AbilityInit) & OwnerIsActor` (InitializeShared @180df2670) : 1202 et
1200 sont des OWNER-EFFECTS poses A L'INIT (ground truth : Arjac porte AnvilShield_AdditionalBlock des le
1er decisionView) -> RIEN a caber pour 1202 (premisse « la pose manque » REFUTEE pour cet effet).
Le DISPATCH `On(UnitBlocked=0x3d)` (emetteur `EvaluateAfterHitTriggers @180e25fc0`, branche `param_6`,
emis AVANT On(8)) est desormais PORTE (`unit_blocked_triggers`, did_block threade) et consomme par
`ApplyIce` : glace la tuile de l'ATTAQUANT (`AddEffect(0x11=Ice, cible=CasterTile@0x168)`) -- confirme
LIVE (cascade `AnvilShield -> Ice` sur un runner --block-target 100).
Restent [fable] : ApplyStun (gate HasEffect(1200|1201), effets NON portes -> port = no-op garanti) et
FrozenAttackerAdvantage (vecteur On(0x2b=PreUnitAbility) + effet 1201 + canal stat 7 absents).
cf. case-222-maillons-de-pose.md §4.
```
```
[SavageKiller | spaceHound passif]  — [fable]
Interrupt pré-ability On(0x2b) à la réaction du mouvement d'un Summon (HasTrait(target, 2) — tooltip
« When a Summon moves »). ⚠ Bloc détail absent du rapport agent (seul le classement + l'hypothèse
trait-2 rendus) — VAs à compléter au moment du port.
```
```
[1211 RitesOfMorkai | spaceWolfPriest]  — [fable]
VAs : ExecuteBehaviour @181202ca0 ; @1812031f0/@181203220 (effets 1502 Inspired / 1529)
Inspired = REVIVE-ONCE 5456 HP sur self+amis non-méca rayon-2 (rejoint le sous-système REVIVE) +
+582 aux porteurs FinalVengeance + UseNormalAttack post-cast (SortUnitsByDamageUtility). Prérequis :
revive-once partagé ; feuilles UseNormalAttack/ValidNormalAttackTargets/SortUnitsByDamageUtility.
```

**Synthèse SW** : [opus] direct = GreatFrostAxe (PORTÉ + BIT-EXACT live, résidu x1.5 RÉSOLU #45f =
élévation manquante du vecteur ability + bonus crit-Ice porté) ; [opus]+prérequis = Foehammer, SagaOfTheWarriorBorn,
WarHowl, HuntersBeyondDeath (borderline), HealingBalms (borderline) ; **[fable]** = AnvilShield
(on-block), SavageKiller, RitesOfMorkai (revive-once). Transverses : AllDeadOrResurrectedUnits ;
IsCharging combat ; dispatch UnitBlocked=0x3d ; active-heal + HealAmount (tous les Healers du roster) ;
revive-once → REVIVE. HYPOTHÈSES : trait 2=Summon, 0x3ea=Psyker (triangulés) ; faces DÉCISION des
actives non-RE'd (à faire au port).
