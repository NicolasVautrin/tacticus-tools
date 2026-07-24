> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.5 DarkAngels (13 items ; faction native id 10, codename « Loki » ; DarkTalonStrike exclu)

```
[1150 PlasmaCannon | darkaTerminator]  — [opus] direct — PORTÉ + VALIDÉ (abilities/darkangels.py)
VAs : ExecuteBehaviour @1811f95c0 ; playbook @181150b10/@181150fe0
Main 3x Plasma + PickRandomly(UnitsDirectlyBehind, 2) même plage/hits — template plasma_grenade_tree ;
UnitsDirectlyBehind DÉJÀ porté (selectors.py:157, cite PlasmaCannon).
PORT : ExecuteAtomic(op_BitwiseAnd(main, splash), 0x2a) = AtomicGroup(op_and(...)) ; splash =
AttackWithAttackDamage(UnitsDirectlyBehind(), multi=True, pick_n=2). hits main==splash==nrOfHits(0x2f)
(GetHits(0)=ArmoriumCherub$$GetHits @180fb16c0 pour les DEUX volets — PAS de nrOfHits_2).
⚠ native_factory="attack" (@180de9fb0, PROUVÉ par XREFS call-sites @1811f97ab/@1811f9866 ; PlasmaCannon
ABSENT des xrefs de @180de9c90) — CONTRE le template PlasmaGrenade "ability". Piège tip #2 évité : NE PAS
copier native_factory du template. Validé live : ratio live/offline main CONSTANT en "attack" (rng-synced,
2 tirages/coup), désync en "ability".
BACKLOG (confounds SHARED-pipeline découverts en validant — HORS ce port, candidats suivi) :
  (i)  `execute_ability_attack` (operations/damage.py:806) ne passe PAS `is_ranged` à `attacker_modifiers`
       -> les buffs ranged du caster (HeavyWeapon_ExtraDmg gated IsRangedAttack + clause ability ×2 @180f4f030,
       +/- bonus high-ground) NON appliqués aux attaques d'ABILITY. Mesuré : live PlasmaCannon = offline ×
       facteur SCALAIRE constant (×1.25 HeavyWeapon seul ; ×1.875 = HeavyWeapon × high-ground caster>cible).
       Affecte TOUTES les abilities ranged des casters HeavyWeapon. [candidat fable — cross-cutting, risque]
  (ii) SPLASH desync per-coup (ratio non constant) : le `PickRandomly` natif consomme du rng même en piquant
       tout (<=2 candidats), là où `_pick_randomly_n` court-circuite (GAP #215 partagé Fragstorm). [candidat]
  (iii) armure : sans --hp-target, `defender_fixed_armor(necroWarden)`=2008 offline vs `RemainingArmor`=0 live
       (à confirmer : FixedArmor stale/profil Plasma). Contourné par --hp-target dans le test. [à vérifier]
```
```
[1103 Supercharge | darkaHellblaster]  — [opus]+1 effet
VAs : ExecuteBehaviour @18120da20 ; @18120de80/@18120de50 ; effet 1208 @180f703b0 ; playbook @1811623b0
= PlasmaCannon avec plages main/behind SÉPARÉES (MinMax vs MinMax2) + effet Supercharge_ExtraPiercing
1208 (+35% pierce Plasma, cible+secondaires, 1 tour). Prérequis : effet pierce-ratio (buff lu par les
attaques FUTURES). Risques : persistance du buff sur un 2e coup Plasma.
```
```
[EnmityForTheUnworthy | darkaCompanion passif]  — [opus]+2 effets (passif le + facile)
VAs : @180f78ff0 ; effets 1400 @180f41fe0 (@180f41b60/@180f41d90/@180f41c20), 1399 (@180f42280/@180f42120)
1400 = +291 FLAT x amis DarkAngels adjacents ; 1399 = +20% x TOUTES unités adjacentes. Patron BeaconOfRage.
Risques : self-exclusion du comptage ; ordre flat+pct dans le pipeline.
```
```
[FearedInterrogator | darkaAsmodai passif]  — [opus]+2 effets
VAs : @180f7fcf0 ; effet 1294 @180f48c60
1294 = +728 vs ennemis Suppressed|Stunned|adjacents-à-un-DA-ami (prédicat évalué sur la CIBLE) ;
1295 = +2 coups si cible AUSSI Chaos (hits.py). Templates existants (BeastSlayer / extra-hits).
```
```
[1228 SternguardFocus | darkaSternguard]  — [opus]+prérequis (le + risqué des opus)
VAs : ExecuteBehaviour @18120bca0 ; GetOverrideAttackDamageAmount @18120c020 ; cooldown 1548
      @1811a2240/@1811a2290 ; playbook @18115ee70/@18115f300/@18115f4e0
PATTERN OVERRIDE-ATTAQUE (1er user runner) : AddStatOverrideEffect(1296, PercentageOfAttackCappedAtMax
(part 3, var 0xd, cap 0x4a)) + UseNormalAttack + RemoveEffect ; triggered 1548 = ChangeCooldown(1228, 3).
Prérequis : nœud override-du-dégât-d'attaque ; UseNormalAttack ; PercentageOfAttackCappedAtMax runner
(impl décision : action_generators.py:493) ; ChangeCooldown. Risques : revert sans fuite ; StatPart 3 vs 0.
```
```
[1189 CalibaniteGreatsword | darkaCompanion]  — [fable]
VAs : ExecuteBehaviour @1811cb000 ; @1811caf30/@1811cb490/@1811cb410/@1811cb320 ; sweep-triggered
      @180e1c070 ; StrikeOverwatching @180f37840 ; playbooks @1811251b0/@1811252b0
TOGGLE de stance (marqueurs 1404 Strike / 1405 Sweep, patron DoctrinaImperatives) — mais Sweep =
splash adjacent-both sur ATTAQUE NORMALE (trigger passif) et Strike = overwatch persistant
post-attaque + decay de coups au kill (1425+1009). HYPOTHÈSE : corps 1425/1009 non lus.
```
```
[LionHelm | darkaAzrael passif]  — [fable]
VAs : @1811084b0 ; effets @180f55f30/@180f561b0/@180f56540
Aura range 2 : +582 block-damage amis, +20% block-chance AUTRES DA seulement, +437 dégât des attaques
déclenchées par Overwatch. Prérequis : projection aura range-2 (template SpotterReworked) + block
défenseur (existant BeastSlayer) + bonus conditionnel-overwatch (neuf) + AddDynamicStatModifierEffect.
```
```
[GrimRetribution | darkaHellblaster passif]  — [fable]
VAs : effet @180f4c090/@180f4c280/@180f4c2b0
Riposte tour-ennemi : si AUCUN ennemi adjacent, tire 1x Plasma (compte Overwatch) sur le 1er ennemi
ayant attaqué Sarquael ou un allié DA adjacent. Prérequis : vecteur on-attacked (self+allié-adjacent),
suivi 1er-attaquant, gate no-adjacent, attribution overwatch.
```
```
[Deathwing | darkaTerminator passif]  — [fable]
VAs : @180e1fb20/@180e1fcc0 ; effet @180f3e160 ; playbooks @181165110/@181165040
À chaque BLOCK : stack DeathwingEffect (−146 dégât entrant suivant / +146 sortant melee+PlasmaCannon,
1 tour, doublé vs Chaos ou adjacent-DA). Prérequis : trigger ON-BLOCK (défenseur mid-attaque) +
IncreaseEffectLevel + effet bi-directionnel. Risques : « further incoming » = coups RESTANTS de la
même attaque (gating inter-coups #72).
```
```
[1213 DeathOnTheWind | darkaStormSpeeder MoW]  — [fable] + BLOQUÉ harnais MoW
VAs : ExecuteBehaviour @1811d22b0 ; @1811d2760/@1811d2930/@1811d26f0 ; effet 1257 @180f3dca0
      (@180f3d9c0/@180f3db60/@180f3dbc0) ; playbook @18112b430
6x HeavyRound sur LIGNE de 3 hexes + effet 1257 (+33% dégât de la prochaine attaque DA amie, avec
retrait). Sans harnais cast-par-MoW : INVALIDABLE (groupe Malleus/DutyEternal).
```
```
[1214 Hailstrike | darkaStormSpeeder MoW]  — [fable] + BLOQUÉ harnais MoW
VAs : ExecuteBehaviour @1811e57c0 ; triggered @180f84360 ; effet 1509 @180f4cdc0 ; playbook
      @181141390/@181141640
Buff ami (+15% pierce ranged/overwatch 1 tour) ; quand l'ami attaque, la MACHINE attaque la même
cible (3x Projectile, gate IsDefeated, sinon TriggerAbilityDelayed). Vecteur « attaque-liée »
genuinement nouveau (une unité attaque hors de son tour, déclenchée par l'attaque d'un ami).
```
```
[1140 ExemplarOfHate | darkaAsmodai]  — [fable]
VAs : ExecuteBehaviour @1811da7e0 ; GetAttacker @1811dad70 ; GetAttackDamage @1811dac90 ;
      effet 1293 @180f433a0 (@180f431c0) ; playbook @181130e70
Pose 1293 (+728 dégât ENTRANT des attaques amies melee/overwatch, 2 tours) ; SI cible Chaos :
Suppress 1065 + le MEILLEUR attaquant DA (First(SortAttackersByDamagePredictionSelector(
UnitsWhoCanAttack(UnitsFromFaction(10))))) frappe via pattern override-attaque plafonné.
Prérequis : sélecteur d'attaquant prediction-heavy ; UnitsWhoCanAttack/UnitsFromFaction ;
pattern override-attaque (partagé SternguardFocus).
```
```
[SpecialIssueCombiMelta | darkaSternguard passif 1545]  — [fable] : RE À FINIR
VAs : init @1811a11a0 (AddEffect 1563+1564 self) ; trigger @1811a10c0 (On 0x26 après-attaque-normale
      & IsAtRange(3)) ; effet ExtraDmg @180e11920 ; playbook @181188c00
⚠ Sémantique des effets 1563/1564/ExtraDmg = HYPOTHÈSE (corps non décompilés, PAS d'i2) — RE
complémentaire OBLIGATOIRE avant tout port (sinon spéculatif/invalidable).
```

**Synthèse DA** : [opus] = PlasmaCannon (direct), Supercharge, EnmityForTheUnworthy,
FearedInterrogator, SternguardFocus (override-attaque, le + risqué) ; **[fable] x8** =
CalibaniteGreatsword, LionHelm, GrimRetribution, Deathwing, DeathOnTheWind (MoW), Hailstrike (MoW),
ExemplarOfHate, SpecialIssueCombiMelta (RE à finir).
