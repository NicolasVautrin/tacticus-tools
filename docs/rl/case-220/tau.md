> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.6 Tau (11 items après exclusions 1082/1077/1081/1192/1194 ; 2 faux positifs kit-coverage)

**Constat transverse (PROUVÉ)** : 2 « MISSING » sont DÉJÀ COUVERTS — **MV71SniperDroneSquad passif
1119** (recâble le NormalAttackType vers l'actif 1076 PORTÉ, `loki/mv71.py`, case-61bis tranches 1-3)
et **CyclicIonBlaster** (effet 1148 porté+validé `hits.py`, #57e — vérifier au smoke le seeding
owner-effect au build runner). Ne pas re-porter.

```
[StructuralAnalyser | tauDarkstrider passif]  — [opus]+prérequis
VAs : AddMarkerlight @1811a2a00/@1811a2ac0 ; AddDamageBuff @1811a2910 ; effet adjacent @180f6e610 ;
      GetStructuralAnalyserBuffedFriends @180f5f250
(1) On(10=AttackDamageAttack) & IsRangedAttack → AddEffect(1122 Markerlight PORTÉ, cible, 1 round).
(2) aura 1156 : +728 aux attaques ranged amies SI cible A Markerlight ; hôtes = adjacents +
    T'au range-2 (sélecteur partagé, cf. synthèse). Prérequis : vecteur On(10) ranged-hit
    (dispatch n'émet que 0x26/8/9) ; gate d'aura HasEffect(target, X) — 2 petites primitives.
Risques : ordre pose-Markerlight vs calcul +728 du même coup ; anneau T'au range-2 vs adjacent.
```
```
[SereneUnifier | tauAunShi passif]  — [opus]+prérequis
VAs : CreateTrigger @18119fba0 ; CreateBehaviour @18119f3f0 ; mods @18119f1e0/@18119f340/@18119f2a0 ;
      SenseOfStone @180f6b230
Turn-start d'Aun'Shi, sélecteur self+adjacents+T'au range-2, round-cycling Modulo(PlayerTurnsStarted,3) :
tour1 → 1169 SenseOfStone (−% dégât reçu) ; tour2 → 1170 ZephyrsGrace (+1 MOVEMENT) ; tour3 → 1171
StormOfFire (+582 ATTACK). Durée TurnsFromRounds(1) (persiste si Aun'Shi tombe). Templates : les 3
effets (damage_reduction/status/stat-mod) ; trigger turn-start (LivingMetal). Prérequis : behaviour
turn-start→buff-sur-SÉLECTEUR (les portés ciblent le porteur seul) ; Modulo(PlayerTurnsStarted,3).
Risques : offset 1-indexé (bon buff au bon round) ; persistance post-mort.
```
```
[DefenderOfTheGreaterGood | tauShadowsun passif]  — ExtraDmg [opus] PORTE+VALIDE / ExtraHits [fable]
VAs : CreateBehaviour @180e203d0 (branche HasTrait Summon : Drone→1306/1307, Shadowsun→1182/1183) ;
      selector @180e20590 ; ExtraDmg @180f3e4f0 ; ExtraHits @180f3e7c0/@180f3eb50
1182 = +364 ranged non-Psychic (aura source-side, template SpotterReworked). PORTE :
DefenderOfTheGreaterGoodExtraDmgEffect (loki/extra_damage.py) — RE 1:1 @180f3e4f0 (ForAddition(
OwnerIsCaster & IsRangedAttack & !DamageProfileIs(0xd=Psychic), ConfigVar(8=extraDmg))) + selecteur
@180e20590 ((AdjacentFriends(1)-owner) + UnitsFromFaction(SurroundingFriends(2), Tau=9)). Threading
damage_profile/att_faction (prediction _shared/normal_attack/abilities/psyker/fury ; combat damage_model/
damage). VALIDE LIVE (probe_220_dotgg.py, MC1_67) : 24/24 agreement offline==oracle (TOL 3) ; aura
load-bearing discriminante — tier ADJACENT (d=1 Tau ET non-Tau), tier T'au range-2 (d=2 Tau), non-Tau
EXCLU au ring-2 (0 divergence admec d>=2). 1183 = coup additionnel PROBABILISTE : Maybe(chance = Min(cap,
25 × UnitTurnsStarted(Shadowsun))) → +1 coup ; NON porte (RNG/valeur-attendue à trancher = [fable]) — le
natif ne compte PAS ce coup probabiliste dans la DamagePrediction (admec bit-exact le prouve). Jumeaux
drone 1306/1307 (branche Summon) NON portes (couplés à ExemplarOfTheKauyon [fable]).
Risques (résiduels ExtraHits/[fable]) : hôte Drone couplé à ExemplarOfTheKauyon ; scale UnitTurnsStarted.
```
```
[WayOfTheShortBlade | tauFarsight passif]  — [fable]
VAs : Init @1811ac970 ; Attack @1811ac750/@1811ac890 ; effet @180f78170/@180f784a0 ; GetAffectedUnits @180f5f3a0
(1) aura 1499 : +30% normal-ranged non-Psychic SI cible adjacente à un ami Character [+ ignore armour
= HYPOTHÈSE, 2e modificateur non décompilé] ; hôtes = T'au Character range-2. (2) marker 1500.
(3) re-attaque : On(9) & IsMeleeAttack & IsEffectTarget(actor,1500) → AddFlag(0x15) &
UseNormalAttackIfAble(actor, target) & RemoveFlag — un Character marqué qui frappe en melee exécute
aussitôt son attaque normale ranged (template TheQuickening, UseNormalAttackIfAble PORTÉ).
Prérequis : gate cible-adjacente-Character ; canal armour-ignore d'aura ; réaction melee→ranged
marker-driven (anti-boucle = gate IsMeleeAttack). Face DECISION : WayOfTheShortBladeNonOwnerPlaybook
@180e442f0 existe — vérifier reachability avant de porter.
```
```
[1210 ExemplarOfTheMontka | tauFarsight]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811dbbd0 ; effet @180f436c0/@180f43730
AddEffect(1498, équipe entière Character+RangedWeapons, this-turn, ne finit PAS le tour) : ApplyInternal
= AddTrait(1042 Unstoppable) ; dégât = ForAddition(IsNormalAttack, If(BigTarget, +946, +437))
(template BeastSlayer). Prérequis : grant de trait par effet (Apply/Revert — présent-inerte, exemption
mouvement INVALIDABLE case-205) ; flag does-not-end-turn (vérifier existant FightingRetreat/BlackRage).
Risques : valider SEULEMENT le +437/+946 (pas le mouvement) ; buff des alliés, pas que Farsight.
```
```
[1069 SeekerMissileFrequencyLock | tauMarksman]  — [fable] (pending-attack)
VAs : ExecuteBehaviour @181206130 ; AttackAbility @18119ebe0 ; TargetEffect @180f6af50 (APendingAttackEffect)
Cast : Markerlight(cible) + bonds 1123 (cible, snapshot) + 1136 (aiming). Au turn-start suivant du
caster : RandomAmount(var 0xc/0xd) → AttackWithAbilityDamage(HeavyRound, hits 0x2f) + RemoveEffect.
Prérequis : SOUS-SYSTÈME PENDING-ATTACK (~20 effets *_PendingAttack en enum, AUCUN porté) —
snapshot ability-state + fire turn-start + annulation. Transverse (partagé HeavyRailRifle,
OverwhelmingWrath §6.3, ~18 kits). Risques : timing fire, snapshot du dégât au cast, caster mort.
```
```
[1160 HeavyRailRifle | tauBroadside MoW]  — [fable] (pending + MoW)
VAs : ExecuteBehaviour @1811e7d70 ; AttackAbility @180f85b40 ; GetFinalUnitDamageAmount @180f86360 ;
      PendingAttackEffect @180f4ef80
Pending 1333/1334 → au tour+1 : dégât = ReducedAmount(base, 30 × TilesMovedLastTurn(cible)) puis
+75% si Vehicle, +75% si BigTarget → AttackWithAbilityDamage(Piercing, hits 0x2f) ; branche Machine =
ChangeCooldown. Prérequis : pending-attack (transverse) ; TilesMovedLastTurn (tracking hexes tour
précédent — 1er consommateur) ; harnais MoW (caster off-board, case-172). Risques : cible immobile
vs mobile ; validation en 2 tours ; déploiement MoW.
```
```
[1161 TwinSmartMissileSystem | tauBroadside MoW]  — [opus]+prérequis (risque MoW)
VAs : ExecuteBehaviour @1812175c0 ; GetAttackTargets @181217950
Attaque Blast 3 hits sur TOUS les ennemis porteurs de Markerlight (Foreach — template FireTile DoT
behaviours.py:559) ; puis refresh Markerlight cible 2 rounds (ChangeEffectTurns) ou pose si absent.
Prérequis : attaque d'ability multi-cible (extension Foreach) ; ChangeEffectTurns ; harnais MoW.
Risques : 1er cast (0 marqués → pose seule) vs 2e ; ordre AoE-vs-pose.
```
```
[1087 ExemplarOfTheKauyon | tauShadowsun]  — [fable]
VAs : ExecuteBehaviour @1811db0f0 ; AdditionalHits @180f43670/@180f43460 ; gate @1811db560
Teleport(caster → tuile adjacente-à-un-allié) → PerformAIAttackFromCurrentPosition → spawn
tauSmnDroneCommandLink sur la tuile PRÉCÉDENTE du caster (Stationary) → additional-hits 1181
(+2×2183 Blast) posé/retiré autour de l'attaque. Prérequis : teleport-ciblé (TheQuickening = échange,
pas ce ciblage) ; spawn-sur-ex-tuile ; couplage drone → DefenderOfTheGreaterGood (1306/1307).
Face DECISION : ExemplarOfTheKauyonPlaybook @181130eb0. Risques : tuiles de réapparition/spawn ;
le +2×2183 ; activation des effets du drone.
```

**Synthèse Tau** : couverts = MV71 passif, CyclicIonBlaster ; PORTE+VALIDE = DotGG/ExtraDmg (probe_220_dotgg
LIVE 24/24, sélecteur d'aura partagé confirmé : adjacent all-faction + T'au range-2, non-Tau exclu au ring-2) ;
[opus]+prérequis = StructuralAnalyser, ExemplarOfTheMontka, SereneUnifier, TwinSmartMissileSystem
(MoW) ; **[fable]** = DotGG/ExtraHits, SeekerMissileFrequencyLock, HeavyRailRifle (MoW),
WayOfTheShortBlade, ExemplarOfTheKauyon. **Sélecteur d'aura partagé x4** (StructuralAnalyser/
SereneUnifier/DotGG/WayOfTheShortBlade) : `AdjacentFriends + UnitsFromFaction(SurroundingFriends
range-2, 9=T'au)` — valider avec un allié adjacent ET un à distance 2. HYPOTHÈSES : armour-ignore
WotSB ; magnitudes ConfigVar ; `<cond+0xa0>` SereneUnifier ; trait 0x10=Character ; seeding
CyclicIonBlaster au build.
