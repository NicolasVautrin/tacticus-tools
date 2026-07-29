> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.14 Sisterhood / Adepta Sororitas (11 items, préfixe `adept*` ; exclusions 1039/ActOfFaith)

**Constats (PROUVÉ)** : **adeptExorcist = MACHINE OF WAR** → ses 2 actives BLOQUÉES MoW.
**FireOfAbsolution = FAUX POSITIF kit-coverage** (COUVERT : fire.py + dispatch.py:329, splash 3x Flame
+ 30% ignite). ArmoriumCherub COUVERT (strike.py, handler 1014). ActOfFaith COUVERT (act_of_faith.py,
factory.py:212, validé #138/#149). **Correction registre : le tag `SkyStrike [--] NO-OP EFFECT/BUFF`
est FAUX** — c'est un charge+attaque melee.

```
[CondemnorStake | adeptCanoness <<Roswitha>> passif, effet 1076]  — [opus] direct — PORTÉ COMBAT + VALIDÉ LIVE
VAs : effet 1076 ctor @180f39600 (source AbilityOrEffect 0x42e=1070=CondemnorStake) ;
      CreateEffectDamageBonusForAttack @180f39450 ; get_OwnerIsActor @180e02530 (owner0x148 vs actor0x158,
      vs get_OwnerIsCaster @180e02610 caster0x160) ; jumeau AvalancheOfMuscle @180f32b20.
Effet PASSIF (pas une ExecuteBehaviour ability) : `EffectBonus.ForAddition(OwnerIsActor & HasTrait(target,
0x3ea=1002=Psyker), ConfigVar(8=extraDmg, GetAbilityState, EffectSource))`. JUMEAU EXACT de
AvalancheOfMuscleExtraDamageEffect avec le seul noeud `IsCharging` remplacé par `HasTrait(target, Psyker)`
(RE decompile @180f39450 : callees = {GetAbilityState, ConfigVar, get_OwnerIsActor, HasTrait(target 0x178,
0x3ea), op_BitwiseAnd, Nullable.ctor} — AUCUN gate melee/ranged/normal/charging). +extraDmg[ablvl passif]xmult
FLAT additif (canal attacker_additive_pre, DamageModifiers.Add @181005f10) à TOUTE attaque du porteur vs cible
Psyker. OwnerIsActor implicite TRUE (chemin appelé uniquement pour l'attaque du porteur ; précédent
SpotterReworked/DecoysAndMisdirection). Gate CIBLE porté via `target_traits` (précédent BeastSlayer/MartialKatah/
DaughterOfTheAbyss). MAGNITUDE = `ability_var("CondemnorStake", "extraDmg", level, mult)` (extraDmg [30(L1)..
2183(L65)] DANS variablesAffectedByRarityBonus) ; i2 "+2183 Damage" = extraDmg[L65] base — LU gameconfig,
JAMAIS hardcodé.
Placement : `entities/effects/loki/extra_damage.py` (CondemnorStakeExtraDmgEffect) + dispatch factory.py
"CondemnorStake_ExtraDmg" (PAS handler.py : c'est un effet, pas une active ability — déviation vs la roadmap
qui présumait le patron sisterhood.py/ExecuteBehaviour). Test `tests/engine/runner/test_condemnor_stake_live.py`.
VALIDATION LIVE (adeptCanoness SPAWNABLE — unité pool, effet 1076 capté dans decisionView.effects) : attaque
normale (id 69) vs cible PSYKER (eldarFarseer) et NON-PSYKER (admecManipulus), contrefactuel par toggle du
trait Psyker offline, RNG seedé (dumpRng) -> bit-exact per-coup les DEUX branches. L50 mult200 : PSYKER
live=[5903,6028,6012]==off_real != off_flip=[2579,2704,2688] (delta +3324/coup = extraDmg[50]=1662 x200/100
EXACT) ; NON-PSYKER live=[2579,2704,2688]==off_real != off_flip (ajout Psyker offline -> +3324 : gate
discrimine). PV résiduel matché. Zero-regression : jumeau AvalancheOfMuscle 3/3.
GAP infra PARTAGÉ (non spécifique) : `target_traits` n'est threadé que sur le chemin d'attaque NORMALE
(damage.py:400) -> le bonus n'entre pas sur les attaques d'ABILITY du porteur (ex. BrazierOfHolyFire) — MÊME
limite que BeastSlayer/MartialKatah ; adeptCanoness s'observe sur ses attaques normales (Chain melee + Bolter
ranged). Multiplier GLOBAL (self.ability_variables_multiplier) — comme AvalancheOfMuscle ; la validation live
L50 mult200 confirme la magnitude bit-exact (pas de bug per-ability #68/#75 côté passif ici).
```
```
[1062 SanctorumMissile | adeptMorvenn]  — [opus] direct — PORTÉ + VALIDÉ LIVE (face COMBAT)
VAs : ExecuteBehaviour @1812041d0 ; GetAdjacentDamageTargetsAll @1812044a0 (units-only frère
      GetAdjacentDamageTargetsUnits @181204580 = Units(All)) ; face DÉCISION prediction abilities.py OK.
Arbre = ExecuteAtomic(0x56, op_BitwiseAnd(MAIN, SPLASH)) : MAIN = AttackWithAttackDamage(target, Blast,
nrOfHits=0x2f=2) ; SPLASH = AttackWithAttackDamage(GetAdjacentDamageTargetsAll(), Blast, nrOfHits_2=0x32=1).
Sélecteur splash = Unobscured(self@0x168, (Units(AdjacentTiles(target))−caster@0x160) + EmptyOrHasSteppable(
adjTiles)) → porté `Unobscured(Sub(AdjacentUnits(TargetTile()), Caster()), Caster())`. FRIENDLY-FIRE (band UNIT
sans filtre équipe, == Stikkbomb) — CONFIRMÉ LIVE (allié adjacent touché). Hex de Morvenn EXCLU (Sub(caster))
— CONFIRMÉ LIVE (Morvenn drivée adjacente, absente des cibles). native_factory="attack" @180de9fb0 (XREFS
call-sites @18120432f/@1812043cf ; ABSENT de @180de9c90/@180de9dd0 ability) — discriminant OK 2 seeds.
GAP flaggé : band TILE EmptyOrHasSteppable @180ee83e0 (tuiles vides/steppables) NON porté — inerte pour le
degat-unite en duel (frère Units(All) l'élimine déjà). Observer Unobscured 0x168 = self/owner (≠ caster 0x160
soustrait, ≠ target 0x178 centre AdjTiles) = Morvenn en cast actif ; board plat → Unobscured passe-tout.
Placement : `runner/abilities/sisterhood.py` (NOUVEAU module Sisterhood isolé) + handler 1062 ;
test `tests/engine/runner/test_sanctorum_missile_live.py`.
```
```
[1025 SkyStrike | adeptCelestine]  — [opus] direct — PORTÉ COMBAT (sisterhood.py) + VALIDÉ
VAs : ExecuteBehaviour @181207d30 ; overload attaque @180dea6b0 (call-site @1812080b2, ABSENT @180de9fb0) ;
      node degat StatAmountFormula @180f22d40 ; MeleeWeaponHits WeaponHitsFormula @180f2f510 ;
      gate eligibilite @1812082a0 (DidMove) ; playbook @18115b110 ; ctx trigger +0x98 InitializeShared @180df2670.
Arbre = op_BitwiseAnd(If(Not(IsAdjacent(caster,target,3)), MoveUnit(caster, First(SortTilesByUtility(
CanAddUnit(AdjacentTiles(target)), caster, UtilityDef(7)), 1))), If(<+0x98 alive>, AttackWithAttackDamage(
caster, target, Sum(NormalAttackDamage=StatAmount(Attack), Direct(GetVariableForLevel(8=extraDmg))),
NormalMeleeAttackDamageProfile(caster), MeleeWeaponHits(caster)))). Template VigilanceEternal EXACT, sauf :
 - CHARGE SANS reach : dest = `CanAddUnit(AdjacentTiles(target))` SEUL (PAS d'`op_And MovableTilesInRange` ;
   Celestine vole) -> collapse = tuile libre ring-1 la plus proche du caster. VALIDÉ : dist 2 ET dist 5 -> charge.
 - ATTAQUE = attaque MELEE NORMALE + extraDmg (PAS config minDmg/maxDmg, absents = 0). Node `Sum(
   NormalAttackDamage(caster), Direct(extraDmg))` ou `DSLFactory$$NormalAttackDamage` @180df75e0 est LA MEME
   factory que celle de l'attaque NORMALE (`ALoki_NormalAttackAbility$$AttackAmount` @1811ae27f, xrefs).
   **#226-r : LE COUP PORTE LE SPREAD +-20 %** (le port le disait PLAT : FAUX). Le commutateur est le 8e
   argument d'`AttackWithAttackDamage` : `Nullable<AttackDamageBehaviourOptions>` avec l'OCTET **+6 = 1**
   (`uStack_1e2 = 1`, seul octet non nul ; +4 = alwaysOverkilled FlailSwing, +5 = alwaysCrit
   TacticalPrecision) — le meme octet que `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` @1811aef30
   renseigne DEPUIS UN GETTER de l'ability (`local_1d8._0_7_ = CONCAT16(<vtable+0x4b8>, ...)`), donc le
   drapeau « calcul de degat d'ARME ». Chemin : `AttackDamageBehaviour+0x9e` -> `AttackDamageOperation$$
   ExecuteHit` (options+0x2f) -> `AttackPredictionRequest+0x6a` -> slot 4 `DamagePrediction$$PredictAttack`,
   ou `GetBaseDamageFix64` etale les bornes de +-DamageSpreadPercentage autour de V = Attack + extraDmg,
   REDUIT, puis tire (reduce-then-roll, 1 tirage/coup). CONTRASTE mesure : le smite Psyker
   (`PsykerExtraAttackAbility$$CreateBehaviour` @1812241b0) passe ce meme Nullable VIDE et n'a AUCUNE variance.
   Profil/coups = arme MELEE (Celestine Power / 3 coups, MeleeWeaponHits SANS ExtraHits).
   Porte en mode `amount` (`Sum(StatAmount(Caster(), Attack), Const(extraDmg))`) + `amount_spread_pct=20`
   + `hits=MeleeWeaponHits` -> `execute_normal_like`.
 - GATE has-not-moved (@1812082a0, DidMove) : eligibilite ciblage (HORS ExecuteBehaviour) — CONFIRMÉ LIVE
   (Celestine non bougee -> castable ; bougee+non-adjacente -> reason 0x10, NON castable).
VALIDATION : **le port == le CAST LIVE, BIT-EXACT, 24 coups** (`probe_226r_skystrike_spread.py` : 4 seeds
adjacent + 2 seeds armure 4000 + 2 seeds charge dist 2 ; contre-modele degenere (V,V) 0/24, contre-modele
bornes brutes roll-then-reduce 4/24 et 0/6 en regime armure) + A/B `execute_normal_like(V, spread 20)` +
charge dist 2/5 + gate has-not-moved live + zero-regression (Psyker/Haze/HeroicFusillade/damage-roll).
CAST LIVE : le porteur HORS pool est injecte par `catalog_inject.write_augmented_seed_bc` (bloc `Units` +
configs `BC.Abilities`) et le cast de 1025 REUSSIT (#226 — l'ancien « GetVariableForLevel(8=extraDmg) throw
pour unite injectee » etait un diagnostic FAUX : c'est la config d'ability qui manquait au BC).
Placement : `runner/abilities/sisterhood.py` + handler 1025 ; test `tests/engine/runner/test_sky_strike_live.py`.
Fiche : `docs/rl/case-226r-skystrike-weapon-spread.md`.
```
```
[1041 BrazierOfHolyFire | adeptCanoness]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811bde60 ; @1811be2b0/@1811be210 ; effet 1075 @180f36b60/@180f36980
Attack(Flame, hits = ConditionalAmount(cible Daemon, 4, 2)) + pose FIRE sur l'hex + effet 1075 sur
voisins Daemon 2 rounds : vulnérabilité ForPercentIncrease REÇU (+60%, +20% si Immune — précédent
MindControl 1350). Prérequis : classe 1075 ; pose Fire via AddEffect. Risques : ne pas figer hits=2 ;
1075 = vulnérabilité (OwnerIsTarget), pas un buff caster.
```
```
[MedicusMinistorum | adeptHospitaller passif]  — [opus]+prérequis
VAs : CreateBehaviour @1812231c0 ; CreateTrigger @1812232d0
Ami adjacent (pas soi) prend du dégât → Heal(873, ForRegenerate) après le coup, sauf si vaincu.
Substrat Heal/ForRegenerate PRÉSENT. Prérequis : vecteur réactif on-adjacent-friend-damaged (On(9)
côté défenseur-voisin). Risques : skip si mort ; non-Mechanical only ; fire au tour ennemi.
```
```
[RighteousRepugnance | adeptMorvenn passif]  — volet A COUVERT / volet B [opus]+prérequis
VAs : 1107 @18119cdd0 ; normal-attack 1182 @181201570/@181201de0/@1812013e0/@1812027a0
A = double-count ActOfFaith 60% melee-kill : DÉJÀ PORTÉ (act_of_faith.py:80). B = attaque normale
CUSTOM 1182 : melee → +3x Power sur cible + ennemis adjacents-aux-DEUX (sélecteur _adjacent_to_both
PRÉSENT splash.py:232). Prérequis : handler normal-attack custom (pattern MV71, damage.py:1076).
Risques : modifie le dégât NORMAL de Morvenn (régression damage) ; ne pas re-porter le double-count.
```
```
[GeminaeSuperia | adeptCelestine passif]  — [opus]+prérequis
VAs : CreateBehaviour @18121fc60 ; CreateTrigger @18121fe40 (On 58 & IsFirstDamagingHitInSeries &
      OwnerIsTarget) ; @18121ffc0/@181220040
Celestine ATTAQUÉE → Spawn adeptSmnGeminaeSuperia adjacent + TriggerAbility(Lifewards 1049), cap 2/bataille
(Count(UnitsWithId(Children))). Prérequis : vecteur réactif on-being-hit ; TriggerAbility sur spawn ;
SummonLimit. Risques : tour ennemi ; Lifewards non modélisé = agreement partiel.
```
```
[1187 ThriceBlessedConflagration | adeptExorcist MoW]  — BLOQUÉ MoW (sinon [opus]+prérequis)
VAs : ExecuteBehaviour @181215060 ; ligne @181215510/@181215610/@1812154d0 ; effets 1401/1436
      @180f73900/@180f73680/@180f73950
Buff ami (+20% ranged vs ennemis sur Fire — ALL-attacks si Adepta Sororitas [HYP faction 1]) + Flame
sur la plus longue LIGNE depuis l'ami ciblé. Géométrie ligne = tâche partagée DarkTalonStrike/
ExcruciatingFrequencies.
```
```
[1188 DevastatingRefrain | adeptExorcist MoW]  — BLOQUÉ MoW (sinon [fable])
VAs : ExecuteBehaviour @1811d3730 ; GetShape @1811d3960 ; différé @18121d5c0 ; effets 1402/1403 @180e031f0
Marque hex + 3 hexes non-mutuellement-adjacents (bond 1402) → au turn-start suivant : Blast sur les
occupants + 75% × N accumulation ActOfFaith des alliés. Rejoint le sous-système PENDING-ATTACK.
```

**Synthèse Sisterhood** : couverts = ArmoriumCherub, FireOfAbsolution, ActOfFaith, RighteousRepugnance/A,
SanctorumMissile (porté), SkyStrike (porté COMBAT), CondemnorStake (porté COMBAT + validé live) ; [opus]
direct restant = aucun ; [opus]+prérequis = BrazierOfHolyFire,
MedicusMinistorum, RighteousRepugnance/B, GeminaeSuperia ; BLOQUÉ MoW = ThriceBlessed (+opus),
DevastatingRefrain (+fable). NOUVEAUX transverses : vecteurs réactifs défenseur ÉTENDUS (on-being-hit
On(58) IsFirstDamagingHitInSeries, on-adjacent-friend-damaged) ; effets vulnérabilité ForPercentIncrease
OwnerIsTarget (1075/1401/1436, précédent MindControl 1350) ; custom normal-attack per-unit (pattern
MV71 étendu par 1182). HYPOTHÈSES : faction 1 = AdeptaSororitas (i2) ; events On(9)/On(58) exacts ;
effets 1401/1436 non deep-read (MoW-bloqué).
