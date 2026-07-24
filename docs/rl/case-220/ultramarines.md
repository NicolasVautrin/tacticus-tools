> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.9 Ultramarines (10 items après exclusions 1000/1002/1158 ; 1 faux positif kit-coverage)

**Constat (PROUVÉ)** : **RitesOfBattle passif = FAUX POSITIF kit-coverage** — DÉJÀ PORTÉ deux faces
(`extra_damage.py:270` + factory.py:145-146 ; playbook `adjacent_unit_preference.py:111`). Rien à faire.

```
[PsychicFortress | ultraTigurius passif]  — [opus] direct (le + facile)
VAs : CreateBehaviour @181224070 ; DmgReduction @180f66a30/@180f66c30/@180f66cb0 ; ExtraBlock @180f66cc0
AddExtraBlockEffectToOwner(1007, +45 block-chance/+dmg) + aura 1010 : −873 Psychic reçu, amis ring-1.
Templates : AnvilShield/BeastSlayer (ExtraBlock) + Nightshroud/DaughterOfTheAbyss (aura). 2 classes à écrire.
Risques : canal ExtraBlock hors GetStat ; gate Psychic-only ; magnitude ×amount@0xd8.
```
```
[1004 MortisRound | ultraEliminatorSgt]  — [opus] direct
VAs : ExecuteBehaviour @1811f54a0 ; lambda @1811fd290
AtomicGroup(Attack(HeavyRound) puis PushUnit(target)) — les 2 nœuds PORTÉS (strike.py, behaviours.py:809).
NUANCE i2 : « Heavy Weapon applies double » (+50% au lieu de +25%) = quirk per-ability NON lu dans
l'ExecuteBehaviour — flag/config à trouver au port. Risques : magnitude x2 ; ordre attaque-avant-push.
```
```
[1003 DeathFromAbove | ultraInceptorSgt]  — [opus] direct  ✅ PORTÉ + VALIDÉ LIVE BIT-EXACT
VAs : ExecuteBehaviour @1811d1b20 ; GetNumSummons @1811d2110 ; tiles @1811d2160
Spawn(ultraSmnInceptor × StatAmount(caster,0xc=TURNS_STARTED), tuiles adjacentes-cible triées par
distance-caster, onAppearance=UseNormalAttackIfAble(target)) — feuille dédiée `SpawnInceptors`
(ultramarines.py) : count DYNAMIQUE (raw TURNS_STARTED, pas de plancher) CAPPÉ par `First(count)` au
nb de tuiles libres (i2 « fewer Inceptors ») ; placement `SortByDistance(caster)` DÉTERMINISTE (0 rng) ;
unitId = GetStringConstant(config,8) = constants["unitToSpawn"] ; spawn délégué à `_spawn_config_grot`
(== per-summon de SpawnUnitOperation.execute) ; on-appearance = attaque normale Bolter 6 coups (PAS de
`unitDamageProfile` override, contraste ScarabHive) via `_summon_on_appearance_attack(prof=None ->
normal_profile)`. PAS d'AddEffect persistant (contraste ScarabHive 0x4a3).
Adjacence = porte d'ÉLÉVATION native (|dElev|<2 depuis la cible), portée par `board.neighbours`
native_sym (boardGraph, mode prod) — l'évenq géométrique sur-inclurait (bug probe uniquement, corrigé).
VALIDÉ : count off==live 1/2/3 + cap (4→3, 6→3) ; degat total on-appearance BIT-EXACT (élévation #45).
Résidus INERTES (non portés) : AbilityOrEffect(1003) threadé dans l'attaque = 0 consommateur ;
tie-break placement (id tuile vs ordre AdjacentTiles) = positionnel (count/degat inchangés).
ShockAssault (passif carrier On(10)) = item SÉPARÉ ([opus]+prérequis), pas dans ce cast.
```
```
[FuelledByFury | ultraTitus passif — 3 volets]  — A [opus] direct / B résiduel / C [fable]
VAs : A @180f80f90/@180f80e70/@180f4ae70/@180f4ad60 ; B @180f4a7c0/@180f4a850/@180f4aa30 ;
      C @180f810c0/@180f81250
A = clone STRICT BeaconOfRage : +153 × level(1323), accumulation On(0xe ActiveAbilityUsed) par ami
Character ; level capté decisionView.effects[].level. B = pose du flag 0x13 suppress-overkill (le
consommateur EXISTE trait_damage_limits.py:209, forcé False) + cycle par tour. C = Revive(self, 5456)
si kill via FinalJustice — dépend du sous-système REVIVE (transverse).
HYPOTHÈSES : traits 0x10/0x419 ; ability 0x400=FinalJustice.
```
```
[ShockAssault | ultraInceptorSgt passif]  — [opus]+prérequis (APRÈS DeathFromAbove)
VAs : CreateBehaviour @1812253e0 ; CreateTrigger @181225630 ; GetAffectedUnits @1812256d0 ; effet @180f6b770
On(0xa=10 attaque-terminée) : les Inceptors-Children adjacents non-marqués(1209) attaquent la cible
avec +364. Primitives portées (Children, PerformAIAbility, AddStaticStatModifier). Prérequis :
DeathFromAbove d'abord ; vecteur On(10) à vérifier/ajouter au dispatch. Risques : fire APRÈS l'attaque ;
marqueur once-per-Inceptor.
```
```
[1019 StormOfWrath | ultraTigurius]  — [opus]+prérequis (RE d'abord)
VAs : ExecuteBehaviour @18120c820 ; nœud ChainAbilityDamage @180deb6b0
ChainAbilityDamage(cible, ≤5 adjacents chaînés, MinMax Psychic) — nœud ABSENT du port ; xrefs = StormOfWrath
+ ChainLightning seulement. Tranche 1 = RE la sémantique (chaîne séquentielle vs splash ring-1 cap-5) ;
tranche 2 = port. Risques : cap 5, full-damage par cible, ordre RNG.
```
```
[CamoCloak | ultraEliminatorSgt passif]  — [opus]+prérequis, CANDIDAT À DIFFÉRER
VAs : CreateBehaviour @18121b370 ; effet @180f37fa0/@180f37f70/@180f381f0/@180f38270
−364 × coups-réduits sur attaque ranged ENTRANTE dont les hits ont été réduits (marqueurs 0x3f5/0x402 =
HYPOTHÈSE hit-reduction). Faible valeur + validation difficile (Certus n'a aucune hit-reduction naturelle).
```
```
[1154 TacticalPrecision | ultraTitus]  — [fable]
VAs : ExecuteBehaviour @18120e540 ; @18120eae0/@18120eb30/@18120eb20 ; reset @1811a30f0
If(IsCharging(caster, CETTE cible)) : 1x Bolter crit GARANTI +728 (ChangeStat crit temporaire) ; sinon
3x Chain sur TOUS les adjacents (MinMax2). Reset au revive (On 46/47). Prérequis ABSENTS : prédicat
IsCharging DSL (approximé has_moved, annoté status.py:439 — transverse FeederTendrils/CrushingStrike) ;
crit-override scope-attaque ; branche splash conditionnelle. Risques : discriminer charge/non-charge.
```
```
[1159 MacroPlasmaIncinerator | ultraDreadnought MoW]  — [fable] + BLOQUÉ MoW
VAs : ExecuteBehaviour @1811f1910 ; tiles @1811f1b90 ; AttackAbility @18110b3d0 ; effet tuile
      @180f57ca0/@180f57be0/@180f57e10/@180f57e70
Marque une zone TRIANGLE (target + arrière, TilesInTriangleShape — runner ABSENT, décision only
loki_custom.py:13) 1 round ; 1re unité qui TERMINE son move dedans → 3x Plasma sur TOUS les ennemis de
la zone (tile-effect à TargetTrigger on-enter, ≠ DoT-tick). + bloqueur cast-MoW (groupe DutyEternal).
```
```
[Narthecium | ultraApothecary passif]  — [fable] (sous-système REVIVE)
VAs : effet @180f5ae20/@180f5add0/@180f5ada0/@180f5acf0 ; base ReviveEffect ; test natif @1808202e0
Allié non-Mechanical adjacent(2) vaincu (non-overkill) → Revive 100% à 4365 HP, once-per-turn.
`DSLFactory.Revive`/ReviveEffect ABSENTS du moteur (grep). Consommateurs du même sous-système :
FuelledByFury C, TaintedNarthecium (§6.8), PhoenixGem @1811117b0, GhostRevive @180f83800.
Risques : timing à-la-mort ; exclusion Mechanical ; gate overkill ; 1x/tour.
```

**Synthèse UM** : couvert = RitesOfBattle, **MortisRound (1004)**, **DeathFromAbove (1003, ✅ PORTÉ+VALIDÉ
BIT-EXACT)** ; [opus] direct restant = PsychicFortress, FuelledByFury/A ; [opus]+prérequis = ShockAssault
(débloqué : DeathFromAbove porté), StormOfWrath (RE chaîne d'abord),
CamoCloak (à différer) ; **[fable]** = TacticalPrecision, MacroPlasmaIncinerator (MoW), Narthecium +
FuelledByFury/C. Débloqueur le + rentable = **sous-système REVIVE** (2 items UM + DG + hors-faction).
