> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.11 BlackLegion (10 items après exclusions 1021/1148 ; namespace natif « Loki »)

**Constat (PROUVÉ)** : aucune active BL dans ABILITY_CLASSES, aucun passif dans les registres
triggers ; faces DÉCISION présentes (Herald validé `prediction.py:1017`, BringerOfDespair
`prediction.py:1149`, Drachnyen custom-utility). Trait faction **LetTheGalaxyBurn** (trait 1058 →
triggered 1482 → effet 1477 ; DespoiledGround + extra-hit) : **VOLET 1 (le coup additionnel) PORTÉ +
VALIDÉ #84** — effet 1477 dans `EffectFactory`, `TRAIT_TRIGGERS["LetTheGalaxyBurn"]` (arm `On(5)` /
reset `On(9)`), nouveau vecteur `pre_attack_triggers`, threading du contexte CIBLE dans
`attack_hits_with_modifiers` ; cf. `docs/rl/case-84-let-the-galaxy-burn.md`. **VOLET 2 (pose de
`DespoiledGround` 1476 + `DespoiledGround_ExtraDamagePct` 1478) reste ouvert.**

```
[1022 BringerOfDespair | blackTerminator]  — [opus] direct — PORTE + VALIDE (2026-07-24, blacklegion.py)
VAs : ExecuteBehaviour @1811be740 ; GetValidBonusTargets @1811bebc0 / GetHitsToBonusTarget @180fb1690 /
      GetDamageProfile @1811beb50 ; playbook @181123c40
ExecuteAtomic( op_BitwiseAnd(
    AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage, Power, nrOfHits(0x2f)=4),          # MAIN
    AttackWithAttackDamage(caster@0x160,
        PickRandomly( Damageable(Enemies(AdjacentUnits(casterTile@0x168, r=1))) − Target()@0x178, 1 ),
        MinMaxDamage[PARTAGE], Power, nrOfHits_2(0x32)=4) ), 0x45 )                                     # BONUS
Bonus ANCRE SUR LE CASTER (CasterTile @0x168, PAS TargetTile) -> ennemi random adjacent a Angrax != cible.
native_factory="attack" (les 2 volets = DSLFactory.AttackWithAttackDamage @180de9fb0, VERIFIE callees).
Port = template splash `loki/splash.py` (Sub/Damageable/Enemies/AdjacentUnits/CasterTile) ; classe
`BringerOfDespairAbility` + arbre `bringer_of_despair_tree()`. Test `test_bringer_of_despair_live.py`
(3 tests : cast live ciblage main+bonus adjacent-caster + A/B bit-exact offline ; discriminant caster-anchor
B-adjacent-caster frappe / D-adjacent-cible NON frappe ; discriminant cap-1 PickRandomly(1) + exclude-target).
CONFOUND CONFIRME (decompile) : Angrax porte le TRAIT FACTION `LetTheGalaxyBurn` (1482, triggered
`LetTheGalaxyBurnEffect.CreateAdditionalHits @180f54e30` = EffectAdditionalHits +1 coup/attaque COMPOSE) ->
LIVE = 5+5 coups = 4 (BringerOfDespair) + 1 (trait). Le trait est HORS de @1811be740 et NON WIRE (transverse,
cf. synthese) -> per-coup-vs-live NON bit-exact (le coup extra decale le flux RNG) ; validation = ciblage LIVE
(non confondu) + A/B OFFLINE bit-exact + magnitude config. « x2 fatigue » (i2) = no-op degat (absent du tree).
```
```
[1036 FrenziedFiring | blackObliterator]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811e1600 ; GetHitsForOriginalTarget @1811e19f0 ; GetTargets @1811e1ba0
Attack(target, hits = 1 + count(hex libres adjacents cible), cap 10, HeavyRound) & Attack(adjacents
de la cible, 1 hit chacun). Prérequis : formule hits-par-free-hex en AMOUNT (comptage déjà fait côté
HeroicFusillade). Les extra-hits FleshmetalGuns COMPOSENT dessus. Risques : cap ; géométrie free-hex.
```
```
[Possession | blackPossession passif]  — [opus]+prérequis
VAs : CreateTrigger @181223f30 ; CreateBehaviour @181223d50
On(54 PostUnitKill KILLER-side) : kill melee → Spawn(blackSmnBloodletter) sur l'hex victime ;
kill ranged → Spawn(thousSmnBlueHorror). Prérequis : kill-event killer-side On(53/54) & OwnerIsActor
(dispatch = victime-side only) ; prédicat IsDefeatedByMeleeAttack. Validable direct.
```
```
[FleshmetalGuns | blackObliterator passif]  — **ROTATION PORTEE + VALIDEE LIVE (#222)**
VAs : CreateTrigger @180e17450 (corps DEDUPLIQUE, identifie par la table de pointeurs de methodes) ;
      CreateBehaviour @18121f6e0 ; TileEffect @18121fb40/@18121fbc0 ; base @180f48570/@180f48260
Les 3 effets extra-hits (1067/1212/1221) etaient PORTES+consommes ; la ROTATION turn-start est cablee :
`On(0x16=TurnStart_Actions) & IsTurnOf(Self@0x148 = df@0xa0)` -> Remove x3 + 3x
If(Modulo(UnitTurnsStarted(Self),3)==k, AddEffect(k)). PARITE TRANCHEE : %3==1 Melta(1067),
%3==2 Flame(1212), %3==0 HeavyRound(1221) -- confirmee LIVE (3 tours natifs consecutifs de Volk :
FocusedMalice -> RuinousSalvo -> WarpHail) et par le seed (turnsStarted=1 -> FocusedMalice).
Pas de double-pose (les 3 RemoveEffect sont INCONDITIONNELS avant les If).
Residu : volet WarpHail DespoiledGround (tile-pose) -- vecteur On(0x10=DamageDealt) absent + effet 1476
non porte. cf. case-222-maillons-de-pose.md §2.
```
```
[HeadClaimer | blackHaarken passif]  — [opus]+prérequis
VAs : CreateTrigger @181220f70 ; CreateBehaviour @181220e30 ; effets 1028 @180f4e0c0/@180f4ddc0,
      1029 @180f4e230/@180f4e110
Kill par Haarken → AddEffectOrIncreaseLevel(1028 +218 dmg) toujours + If(IsHero(victime), 1029 +1 hit).
Snowball capté live → prédiction gratuite. Prérequis : 2 classes d'effet per-level (template SmashaEad/
BeaconOfRage) ; feuille AddEffectOrIncreaseLevel [partagée] ; kill-trigger killer-side + IsHero.
```
```
[FirstAmongTraitors | blackAbaddon passif]  — [opus]+prérequis
VAs : effet @180f49f50/@180f499e0/@180f49ba0/@180f49b10/@180f49ee0 ; GetRange @18121f6b0
Aura Chaos rayon-2 : +dmg = Min(364 + 73 × TotalAttacksMade(Abaddon), cap 1313). Templates : aura
BeaconOfRage + magnitude dynamique LordOfTempests ; TotalAttacksMade présent (formulas.py). Prérequis :
la classe (compteur de la SOURCE d'aura, remote). Risques : self-exclusion ; compteur d'Abaddon pas
du bénéficiaire.
```
```
[1020 HeraldOfTheApocalypse | blackHaarken]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811e8860 ; effet 1027 @180f4f390/@180f4f570 ; playbook @181144390 (VALIDÉ)
Attack(target + 1 ennemi DERRIÈRE en ligne, 2x Piercing) + AddEffect(1027 : +1310 REÇU one-shot,
self-remove On(9)) + TriggerAbility(ennemis rayon-2, 1025 BattleFatigue). Templates : TilesBehindInLine
(excruciating_frequencies.py) ; BattleFatigue PORTÉ ; ForAddition(OwnerIsTarget) LordOfTheHost.
Prérequis : effet one-shot dmg-taken + feuille TriggerAbility-sur-sélecteur. Risques : parité hexgeo
« derrière » ; consommation par attaquant TIERS.
```
```
[1029 Drachnyen | blackAbaddon]  — [opus]+prérequis (borderline fable)
VAs : ExecuteBehaviour @1811d6570 ; effet 1471 @180e212f0/@180e210e0/@180e21450 ; playbook @18112dc60
SetHealth(self, Min(4729, maxHealth)) & AddEffect(1471 permanent) & UseActiveAbility(normal-attack).
1471 DÉRIVE une triggered : après CHAQUE attaque normale d'Abaddon → 2e attaque 3x Piercing sur un
adjacent, reste de la bataille. Prérequis : SetHealth variante Min(const, max) ; plumbing
effet-posé-par-active dérivant un triggered persistant (les effect-derived actuels = traits,
factory.py:354). Escalade [fable] si le wiring ne colle pas au patron EFFECT_TRIGGERS.
Risques : pas de boucle infinie ; ne compte pas les attaques d'ability.
```
```
[HatefulAssault | blackTerminator passif]  — [fable] (vecteur before-move partagé)
VAs : CreateTrigger @1812203e0 ; CreateBehaviour @1812201e0 ; marqueur 1175
Ennemi qui QUITTE un hex adjacent → Attack(2x Power) + marqueur AlreadyAttacked (once-per-mover).
Prérequis ABSENT : vecteur On(PreUnitMove=31) + hex-de-départ (enum présent event_trigger_type.py:60,
AUCUN émetteur) — PARTAGÉ MomentShackle §6.1. L'attaque est triviale → REDESCEND [opus] dès que le
vecteur existe. Risques : ordre attaque-vs-move ; kill à mi-déplacement.
```
```
[1147 HadesAutocannons | blackForgefiend MoW]  — BLOQUÉ harnais MoW
VAs : ExecuteBehaviour @1811e50e0 ; playbook @181140a60 (prediction.py:1031 note déjà « MoW »)
Rejoint le groupe DaemonicOrdnance/PlagueburstMortar/Malleus/DutyEternal.
```

**Synthèse BL** : [opus] direct = BringerOfDespair (**PORTE + VALIDE**, blacklegion.py) ; [opus]+prérequis = FrenziedFiring, Possession,
FleshmetalGuns (runner-face), HeadClaimer, FirstAmongTraitors, Herald, Drachnyen (borderline) ;
**[fable]** = HatefulAssault (vecteur before-move) ; BLOQUÉ MoW = HadesAutocannons. NOUVEAUX
transverses : kill-events KILLER-side On(53/54) + IsDefeatedByMeleeAttack (Possession, HeadClaimer) ;
Modulo + rotation d'effets turn-start (FleshmetalGuns) ; effet-dérivant-triggered persistant
(Drachnyen) ; ~~trait faction LetTheGalaxyBurn 1482 non wiré~~ **volet 1 PORTÉ #84** (RE'd via BringerOfDespair : triggered
`LetTheGalaxyBurnAbility.CreateTrigger @1811076f0` On(5)&OwnerIsCaster + `LetTheGalaxyBurnEffect.
CreateAdditionalHits @180f54e30` = `EffectAdditionalHits.Create` FirstHitInCurrentAttackDamageRange, gate
OwnerIsCaster & (TargetHasTileEffect DespoiledGround | IsPersistentData 0x5ca) ; +1 coup/attaque COMPOSE sur
CHAQUE attaque du porteur -- confirme live sur BringerOfDespair 5+5=4+1 ; extra-hit template hits.py comme
FleshmetalGuns 1067/1212/1221). HYPOTHÈSES : GetHitsForOriginalTarget
au bit ; event 53 vs 54 ; Not(AreEqual(Tiles,dest)) HatefulAssault ; index ConfigVar FirstAmongTraitors.
