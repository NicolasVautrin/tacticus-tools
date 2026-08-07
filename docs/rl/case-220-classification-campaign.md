# case-220 — Campagne de classification par agents (P0 #217, traits §5.1, factions P2)

> **Protocole** (2026-07-23) : panel roulant de 5 agents `re-expert` (modèle opus, worktree isolé
> + junction `data/`), **classification SEULE** — décompiler l'artefact natif de chaque item,
> identifier arbre + template moteur existant, vérifier les prérequis par grep dans `engine/`,
> rendre un verdict `[opus] direct` / `[opus]+prérequis nommés` / `[fable]` + découpe en tranches.
> **Aucun port, aucune édition de doc par les agents** — l'orchestrateur intègre chaque rapport
> ici et dans `port-roadmap.md` (droit d'édition exclusif), puis relance un agent de la file.
> File : P0 (5 tranches) puis factions P2 par volume (AstraMilitarum → EmperorsChildren → …).
>
> Build `gqfc5mff6c`, VAs base `0x180000000`. Le décompilé = vérité ; le live = confirmation.

## Sommaire des tranches

| Tranche | Statut | Section |
|---|---|---|
| P0-HEAL/REPAIR (5) | ✅ classifiée | [§1](case-220/p0-heal.md) |
| P0-SUMMON (6) | ✅ classifiée | [§2](case-220/p0-summon.md) |
| P0-DAMAGE (7) | ✅ classifiée | [§3](case-220/p0-damage.md) |
| P0-EFFECT + P0-WALK restants (5) | ✅ classifiée | [§4](case-220/p0-effect-walk.md) |
| Traits communs §5.1 (7) | ✅ classifiée | [§5](case-220/traits.md) |
| P2 Custodes | ✅ classifiée | [§6.1](case-220/custodes.md) |
| P2 AstraMilitarum | ✅ classifiée | [§6.2](case-220/astra-militarum.md) |
| P2 WorldEaters | ✅ classifiée | [§6.3](case-220/world-eaters.md) |
| P2 EmperorsChildren | ✅ classifiée | [§6.4](case-220/emperors-children.md) |
| P2 DarkAngels | ✅ classifiée | [§6.5](case-220/dark-angels.md) |
| P2 Tau | ✅ classifiée | [§6.6](case-220/tau.md) |
| P2 Necrons | ✅ classifiée | [§6.7](case-220/necrons.md) |
| P2 DeathGuard | ✅ classifiée | [§6.8](case-220/death-guard.md) |
| P2 Ultramarines | ✅ classifiée | [§6.9](case-220/ultramarines.md) |
| P2 Votann | ✅ classifiée | [§6.10](case-220/votann.md) |
| P2 BlackLegion | ✅ classifiée | [§6.11](case-220/black-legion.md) |
| P2 BloodAngels | ✅ classifiée | [§6.12](case-220/blood-angels.md) |
| P2 Orks | ✅ classifiée | [§6.13](case-220/orks.md) |
| P2 Sisterhood | ✅ classifiée | [§6.14](case-220/sisterhood.md) |
| P2 SpaceWolves | ✅ classifiée | [§6.15](case-220/space-wolves.md) |
| P2 Tyranids | ✅ classifiée | [§6.16](case-220/tyranids.md) |
| P2 AdeptusMechanicus | ✅ classifiée | [§6.17](case-220/admec.md) |
| P2 ThousandSons | ✅ classifiée | [§6.18](case-220/thousand-sons.md) |
| P2 Aeldari | ✅ classifiée | [§6.19](case-220/aeldari.md) |
| P2 BlackTemplars | ✅ classifiée | [§6.20](case-220/black-templars.md) |
| P2 Genestealers | ✅ classifiée | [§6.21](case-220/genestealers.md) |
| P2 AdeptusAstartes | ✅ classifiée | [§6.22](case-220/adeptus-astartes.md) |

**CAMPAGNE COMPLÈTE (2026-07-23)** — 24/24 tranches rendues et intégrées. Synthèse finale : voir
`port-roadmap.md` §5.3 (verdicts par faction) et §4 (prérequis transverses consolidés depuis §T).

> **Structure** : le detail de chaque tranche (VAs, arbres, prerequis, risques) vit dans
> `docs/rl/case-220/<tranche>.md` (liens dans le sommaire). Ce fichier maitre garde le
> protocole, le sommaire et le ledger §T. Integration d'un nouveau rapport = 1 fichier
> de tranche + 1 ligne de sommaire + extensions §T.

---
## §T Prérequis transverses cumulés (ledger — consolidation en §4 P1 roadmap à la FIN de la campagne)

| Prérequis | Surfacé par | Tranches |
|---|---|---|
| PerformAIAction (feuille unifiée + after-hit ; variantes PerformAIAbility / -repair / PerformAIMovement ; généralisation aux unités ENNEMIES + move-before-attack) | Waaagh, SupremeCommander, ItItches, act-again BlackRage, AdaptiveStrategy, ReanimationBeam, ShockAssault, EcogSupport, BioMinefield (movement), AttemptedPossession (ennemis+summons) | case-219 §7, §2, §6.7, §6.9, §6.10, §6.16, §6.18 |
| Sous-système Overwatch (effets 1009/1144/1145/1149 ; re-arm-on-kill + hits décroissants ; extra-dmg gate IsOverwatchAttack) | EarlyWarningOverride, InescapableDeath, LionHelm/GrimRetribution (attribution), CalibaniteGreatsword ; blind spot IA connu | §2, §6.5, §6.7 |
| Vecteurs réactifs DÉFENSEUR : on-being-attacked, on-being-hit (On 58 IsFirstDamagingHitInSeries), on-adjacent-friend-damaged, On(PreUnitMove=31) + hex-de-départ, ON-BLOCK mid-attaque, riposte self+allié-adjacent, attaque-liée machine | UnwaveringSentinel, MomentShackle, Deathwing, GrimRetribution, Hailstrike, HatefulAssault, GeminaeSuperia, MedicusMinistorum, ~~AnvilShield (dispatch UnitBlocked=0x3d)~~ **LEVÉ #222** (`unit_blocked_triggers` — émetteur `EvaluateAfterHitTriggers @180e25fc0` branche `param_6`, `did_block` threadé ; 1er user = AnvilShield ApplyIce), SavageKiller (réaction move Summon), WireweaveNet (riposte PRE-HIT + annulation on-kill) | §6.1, §6.5, §6.11, §6.14, §6.15, §6.19 |
| TriggerAbilityDelayed (file d'ability différée — écarté 2x par collapse, act_of_faith.py:96) | UnwaveringSentinel, Hailstrike, HaywireMine | §6.1, §6.5, §6.22 |
| Pattern OVERRIDE-ATTAQUE (AddStatOverrideEffect dégât + UseNormalAttack + Remove) + PercentageOfAttackCappedAtMax runner | SternguardFocus, ExemplarOfHate | §6.5 |
| Sélecteur d'attaquant prediction-heavy (SortAttackersByDamagePredictionSelector + UnitsWhoCanAttack + UnitsFromFaction) | ExemplarOfHate | §6.5 |
| Petits nœuds : IncreaseEffectLevel, ChangeCooldown, AddDynamicStatModifierEffect, IsAtRange | Deathwing, SternguardFocus, LionHelm/StandVigil, SpecialIssueCombiMelta | §6.1, §6.5 |
| Harnais cast-par-MoW hors-plateau (déploiement OK côté BC, cast non prouvé) | DutyEternal, PlagueburstMortar/DaemonicOrdnance/Malleus, ForwardSpotter, DeathOnTheWind, Hailstrike, HeavyRailRifle/TwinSmartMissileSystem (tauBroadside), ReanimationBeam/NanoscarabRepairProtocols (necroReanimator), EntropyCannons (deathCrawler), MacroPlasmaIncinerator (ultraDreadnought), HadesAutocannons (blackForgefiend), SquigLaunchas/SquigMine (orksRukkatrukk), ThriceBlessed/DevastatingRefrain (adeptExorcist), InfernalCannon/AetherStride (thousDaemonPrince — AetherStride = jumeau DutyEternal multi-hex) | case-219 §5, §6.2, §6.5-§6.18 |
| Persistent data — scalar (Set/Get) et LIST (Add/IsIn/clear) + compteur (Add/Clear) | StandVigil (range), LegendaryCommander (marquage), PrioritisedEfficiency (stance), FuryFromTheDelve (flag 2-events), AncestralFortune (compteur 6), HazeOfCorruption (0x434), HaywireMine (gate un-seul-mine), AggressiveOnslaught (tracking summons) | §5, §6.1, §6.8, §6.10, §6.12, §6.22 |
| Compteurs/prédicats d'attaque : TimesAttackMadeThisTurn, CurrentAbilityIs, IsFirstHitGroupInAttack, IsPartialAttackAbility, TriggeringAbilityIsNormalAttack, TotalTurnsWithAttacksMade (+0x30) | LegacyOfCombat, LegendaryCommander, MartialInspiration | §4, §6.1 |
| HasUsedActiveAbilityThisTurn comme filtre de sélecteur | LegendaryCommander | §6.1 |
| ~~AddEffectOrIncreaseLevel côté ÉCRITURE (accumulate, level-cap)~~ **LEVÉ #222** (factory `add_effect_or_increase_level` + feuille `IncreaseEffectLevel`, clamp mirror @180e73cb0 ; 1er user = TerrifyingCrescendo) | TalonsOfTheEmperor (1420), TerrifyingCrescendo (1424) **PORTÉ**, HeadClaimer (1028/1029) | §6.1, §6.4, §6.11 |
| Amount-nodes DSL : RandomAmount / Divide / Get(const) + PickRandomly-by-count | Poxwalkers, OptimizedGait (RandomAmount) | §2, §6.17 |
| ChainBehaviour (boucle ré-évaluée par itération) + snake-chain impératif (expand-from-last + exclusion + PickRandomly par pas) | Incursion, SilentDeath | §2, §6.19 |
| Feuilles turn-flow : ResetTurn (ré-entrance), FinishTurn | FightingRetreat | §4 |
| Formules ConditionalAmount, MinDistance | HammerOfWrath | §4 |
| UseNormalAttack (feuille thin) | FoulInfusion, SternguardFocus, ExemplarOfHate, RitesOfMorkai | §3, §6.5, §6.15 |
| Feuille Resurrect + sélecteur AllDeadUnits / AllDeadOrResurrectedUnits + variante HP-cible paramétré | RitesOfRestoration, ResurrectionOrb, SendInTheNextWave, ArmourOfShriekingSouls, Foehammer (count morts) | §1, case-219 §2, §2, §6.4, §6.15 |
| ResetActiveAbility (réactivation d'active) | InspiredToGreatness, AncestralFortune | §1, §6.10 |
| Dérivation faction/grande-alliance (HasFaction 18=AdeptusCustodes) | TalonsOfTheEmperor | §6.1 |
| Géométrie ligne hex (GetTilesInLine / best-line / TilesBehindInLine+FilterContinuous / 6-directions ; + array de dégât PAR POSITION + landing) | DarkTalonStrike, ExcruciatingFrequencies, DeathOnTheWind, ThriceBlessedConflagration, RadBombardment, SwoopingHawk | §3, §6.4, §6.5, §6.14, §6.17, §6.19 |
| PullUnitOneTile (symétrique toward-pusher du push porté) | GrapnelLauncher, LashOfTorment | §3, §6.4 |
| SortUnitsByDamageUtility (+First) — collapse impératif | VexillaMagnifica, EcstaticSlaughter, KillMaimBurn (0x22), AncestralFortune | §4, §6.4, §6.3, §6.10 |
| Feuilles stat-mod : AddStaticStatModifierEffect (self / ToOwner / sur SÉLECTEUR) / AddOrUpdate — **levier #1 BlackTemplars** | DoomSiren, ExcruciatingFrequencies, RefusalToBeOutdone, LeadingTheCharge, TrophyTaker, CrusadeOfWrath, UnbreakableDuty, DestroyTheWitch, ChampionOfTheFeast | §6.2-§6.4, §6.20 |
| Canal DÉFENSEUR « REÇU » (crit-chance/dmg reçu OwnerIsTarget ; dmg-taken flat one-shot self-remove On(9) ; vulnérabilité ForPercentIncrease — précédent MindControl 1350) | ToughToKill, ObsessiveAnnunciation, EuphoricStrikes, Herald 1027, BrazierOfHolyFire 1075, ThriceBlessed 1401/1436 | §6.2, §6.4, §6.11, §6.14 |
| Contexte PV-CIBLE (target_health_pct) dans les hooks bonus attaque/crit | TrophyTaker (et tout bonus low-HP-target) | §6.3 |
| Contexte PV-CASTER pour magnitude additive | Skullsmasher | §6.3 |
| Event deep-strike-landing On(UnitBecameTargetable=60) | WrathfulDevotion | §6.3 |
| **Sous-système PENDING-ATTACK** (APendingAttackEffect + snapshot ability-state + fire turn-start + annulation) — ~20 effets `*_PendingAttack` en enum, AUCUN porté ; candidat [fable] brique commune | OverwhelmingWrath, SeekerMissileFrequencyLock, HeavyRailRifle, DevastatingRefrain (+~18 kits roster : TargetingProtocols/AnnihilatorBeam/NeedsMoreDakka/TheLantern/GazeOfMagnus/SolarAtomizer…) | §6.3, §6.6, §6.14 |
| Multi-profil : MinMaxDamage2/3 + GetDamageProfile2/3 + GetNextTarget kill-priority + prédiction N-events | KillMaimBurn, PlagueWind (courbes tiers), TacticalPrecision (branche MinMax2), Supercharge (plages séparées) | §6.3, §6.8, §6.9, §6.5 |
| Sélecteur TilesAtDistance (natif @181069760) | BasiliskBarrage | §6.2 |
| RNG probabiliste : Maybe en AMOUNT (cascade hit-count), coup additionnel Maybe (valeur attendue), Maybe en EXÉCUTION (75% revive) | PsychicMaelstrom, DefenderOfTheGreaterGood_ExtraHits, TaintedNarthecium | §6.2, §6.6, §6.8 |
| Feuille SortedAttackSeries (main+splash en série triée) + nœud AbilityDamage (≠ AttackWithAbilityDamage) | FragBomb, HellfyreMissileRack | §6.2, §6.18 |
| Résolution 2 overloads AttackWith*Damage (direct @180de9c90 vs crit @180de9fb0) | BasiliskBarrage, PsychicMaelstrom | §6.2 |
| Prédicats Filter : IsNormalUnit / HasBeenDefeated / HasAdjacentEnemies | LeadingTheCharge, BioMinefield (détonation) | §6.2, §6.16 |
| Feuille Kill/ForDirectKill + vecteur flee On(0x34) | SummaryExecution | §6.2 |
| Vecteur On(PreUnitAbility=0x2b) PRÉ-ATTAQUE (contre AVANT résolution, peut ANNULER l'attaque) + échange-de-position + redirect-de-dégât + CanSwitchPosition | SwornProtector, MartialSuperiority, SavageKiller | §6.2, §6.20, §6.15 |
| Canal stat PierceRatio (26) honoré par le pipeline de dégât + pierce-ratio ATTAQUANT conditionnel trait-cible + pierce en AURA | LeadingTheCharge, Supercharge (1208), GravitonRifle (+60% vs Gravis/Terminator/Mechanical, factory.py:346 non porté), GrimEfficiency, HeavyGravCannon (for_piercing défini effect_bonus.py:72 mais JAMAIS consommé) | §6.2, §6.5, §6.10, §6.17 |
| Sélecteur UnitsDamagedThisPhase + canal modificateur nrOfHits d'attaque NORMALE | DoomSiren | §6.4 |
| Effet Infiltrate 0x416=1046 (marqueur) | HammerOfWrath, Nightshroud, LeadingTheCharge | §4, §6.2 |
| **Feuille Repair DSL** (amount + HealUnitOperation, variante ForRepair réveil) + sélecteurs Repairable/UnitsAffectedByHealType/UnitsWithNegativeEffects/MechanicalUnits | DefendTheDivineWork, FabricatorClawArray, RelentlessMarch, ReanimationBeam | §1, §6.7 |
| Vecteur dispatch On(ArrivedAtFinalTile=28) — flag posé turnflow.py:48/67, jamais dispatché ; single-trigger « ait bougé ou non » (émettre AUSSI en fin de tour sans mouvement) | FabricatorClawArray, LivingLightning, SanguinaryPriest, RedRampage, FuryOfTheAncients, ChampionOfTheFeast, SpiritualLeader | §6.7, §6.12, §6.20, §6.21 |
| Nœud TriggerAbility (re-déclenche une autre ability, incl. sur SÉLECTEUR / on-demand) | AdaptiveStrategy, SwornProtector, Herald (BattleFatigue AoE), GeminaeSuperia (Lifewards du spawn), FearOfTheUnseen (BattleFatigue on-demand) | §6.7, §6.2, §6.11, §6.14, §6.16 |
| ChainLeftOverHitsAttackDamage (report des hits restants sur kill, +1 hit/kill, re-ciblage dynamique) | BloodyFury, MultiThreatEliminator, FragstormGrenadeLauncher | §3, §6.7, §6.20 |
| **PRIMITIVE AURA CONTAGION** (`ContagionsOfNurgleRange @180dece10`, `CalculateRange @180f39940` : rounds ≤2→1/3-4→2/5+→3, `IsInUnitContagionsOfNurgleAura`) + gap séparé : l'aura armor-reduction elle-même (source de `target_armor_reduced` jamais alimentée) | Poxwalkers (range), FoulInfusion (range), CursedPlagueBell x2, EntropyCannons (ciblage), 6 héros DG (armor-reduction) | §2, §3, §6.8 |
| **Sous-système REVIVE** (Revive-en-place ≠ Resurrect/ambush ; gate once-per-turn ; gate overkill ; variantes revive-ONCE aura et revive-AT-POSITION time-ghost) | Narthecium, FuelledByFury/C, TaintedNarthecium, PhoenixGem @1811117b0, GhostRevive @180f83800, RitesOfMorkai (Inspired), TimeFlux (ghost) | §6.8, §6.9, §6.15, §6.18 |
| GetLeftOverDamages (reliquat overkill CHIFFRÉ de la cible tuée) | HazeOfCorruption | §6.8 |
| Flag « always overkilled » passthrough sur nœud d'attaque | FlailSwing, ExplosiveMaladies (résidu hits.py:254) | §6.8 |
| ~~Nœud ChainAbilityDamage (xrefs : StormOfWrath + ChainLightning, aucun porté — RE chaîne vs splash cap-5 d'abord)~~ **PORTÉ (#499)** : `behaviours/chain.py::ChainAbilityDamage`. Ce n'est **ni** une chaîne « au dernier maillon » **ni** un splash cap-5 — l'origine du saut est l'**ensemble** des cibles déjà piquées, et le coup est **différé d'un cran** (`chainOptions+0x12`). `ChainLightning` reste non portée mais consomme la même factory, avec les mêmes options. | StormOfWrath | §6.9, `case-499` |
| Prédicat IsCharging (relation « a chargé CETTE cible ce tour » — approximé has_moved, annoté status.py:439) + vecteur On(UnitAbility=11)&IsCharging | TacticalPrecision, FeederTendrils/CrushingStrike, SagaOfTheWarriorBorn (gate combat eager), AggressiveOnslaught | §6.9, §6.12, §6.15 |
| Tile-effect à TargetTrigger ON-ENTER (≠ DoT-tick) + TilesInTriangleShape côté RUNNER (décision only loki_custom.py:13) + système mines multi-hex (détonation on-enemy-enter, clear-on-friend) | MacroPlasmaIncinerator, SquigMine (1441) | §6.9, §6.13 |
| Vecteur On(10=AttackDamageAttack / attaque-terminée) au dispatch | StructuralAnalyser (ranged-hit), ShockAssault, LegendaryCommander (marquage) | §6.6, §6.9, §6.1 |
| Gate d'aura « cible-a-effet » HasEffect(target, X) | StructuralAnalyser (Markerlight) | §6.6 |
| Grant de trait par effet (ApplyInternal AddTrait / RevertInternal) | ExemplarOfTheMontka (Unstoppable présent-inerte) | §6.6 |
| ChangeEffectTurns (re-timing de durée d'effet) | ThrillSeekers (refresh), TwinSmartMissileSystem, RedRampage (+1 au kill) | §5, §6.6, §6.12 |
| Attaque d'ability MULTI-CIBLE (Foreach sur sélecteur d'unités — extension du Foreach FireTile) | PutridExplosion, TwinSmartMissileSystem, MacroPlasmaIncinerator (zone) | §5, §6.6, §6.9 |
| Teleport-ciblé (tuile adjacente-à-un-allié) + spawn-sur-ex-tuile-du-caster | ExemplarOfTheKauyon | §6.6 |
| Trigger turn-start → buff sur SÉLECTEUR (les portés ciblent le porteur seul) + Modulo round-cycling (PlayerTurnsStarted / UnitTurnsStarted) — **volet Modulo/UnitTurnsStarted LEVÉ #222** (`UnitTurnsStarted` lit le vrai `GetStat(unit,0xc)` ; `IsTurnOf(Self)` = `df@0xa0`) | SereneUnifier, TimesplinterMantle, RelentlessMarch, FleshmetalGuns (rotation x3) **PORTÉE** | §6.6, §6.7, §6.11 |
| Tracking mouvement de la CIBLE au tour précédent : TilesMovedLastTurn (chiffré) / prédicat moved-last-turn | HeavyRailRifle, PredictiveGuidance | §6.6, §6.10 |
| Prédicat WasBlock (event UnitBlocked=61) comme trigger | AncestralFortune | §6.10 |
| Action REPAIR combat exécutable + event UnitRepaired(49) (trait Mechanic faction-wide — repair.py = utilité IA seule) | EcogSupport | §6.10 |
| Kill-events KILLER-side : On(UnitDeath=0) / On(53/54/55) & OwnerIsActor + IsDefeatedByMeleeAttack ; + On(54) émis au CRUSH de Steppable (silencieux aujourd'hui) | Possession, HeadClaimer, BarbedOvipositor, CosmicHorror (crush decoy + kill) | §6.11, §6.16, §6.21 |
| Effet posé-par-active DÉRIVANT un triggered persistant (≠ effect-derived de trait, factory.py:354) | Drachnyen 1471 | §6.11 |
| Trait faction LetTheGalaxyBurn 1482 (DespoiledGround + extra-hit) — enum présent, NON wiré TRAIT_TRIGGERS | tous kits black* | §6.11 |
| Canal AURA sur stat EXTRA_HITS (stat-mod nrOfHits, ≠ attaque additionnelle) | LordOfTheHost 1377 | §6.12 |
| ChainAttackDamage (attaque primaire + 2e cible par fonction-sélecteur) | FuryOfTheAncients | §6.12 |
| Effet SUPPRESSION-de-soin cross-cutting (hooks heal/regenerate/repair/resurrect — fuite silencieuse si un canal est oublié) | FuryOfTheAncients 1320 | §6.12 |
| NumLeftOverHits (réallocation des hits restants après kill) + sous-arbre de distribution | DakkaDakkaDakka, LightImUp | §6.13 |
| Nœud RoundsStarted côté RUNNER (décision only aujourd'hui, active_ability.py:395) | GrotTank, RadBombardment (longueur de ligne) | §6.13, §6.17 |
| Charge-driver en ligne IMPÉRATIF (Move/Push hex-par-hex, dégât scalé per-hex, displacement ami sans dégât) | UnstoppableMomentum | §6.13 |
| Custom normal-attack per-unit (dispatch sur NormalAttackType concret — pattern MV71, damage.py:1076) | RighteousRepugnance 1182 | §6.14 |
| Active HEAL en ABILITY_CLASSES + formule HealAmount (trait Healer) — 1re du registre | HealingBalms | §6.15 |
| Boucle repeat-until-cap spawn GÉNÉRIQUE (bespoke spawn.py:583 aujourd'hui) + trigger réactif cross-unit (owner≠actor, gates trait/amitié sur l'ACTEUR) | SynapticLinchpin, BioMinefield | §6.16 |
| Kits de summons Tyranides DOWNSTREAM (tyranSmnSporeMine.FloatingDeath, RipperSwarm.Burrowers, Hormagaunt.AdrenalGlands) — sans eux les spawns exécutent mais l'aval = 0 | SporeMineLauncher, BioMinefield, BarbedOvipositor, SynapticLinchpin | §6.16 |
| ~~remove-effect-by-source (retirer l'effet posé PAR CE caster, marqueur unique)~~ **LEVÉ #222** (sélecteurs `EffectsFromUnitSource @180deec70` + `OwnerOfEffect @180df8350` + `RemoveEffect` multi-cible) | MasterAnnihilator **PORTÉ** | §6.17 |
| Compteur TotalRepairActionsAmount (repairs battle-scoped des amis Mechanic) | RadBombardment | §6.17 |
| **Canal CRIT-ATTAQUANT** (crit-chance/crit-dmg DONNÉ — hooks base.py:213/220 présents, 0 USER) | InescapableAccuracy (1er user), PathOfCommand_ExtraCrit (TODO factory.py:377), SagaOfTheWarriorBorn (crit-dmg) | §6.19, §6.15 |
| Feuille ResetMovement (2e move du caster, ≠ ResetTurn) | ItItches, FireAndReposition, StrikeFromTheShadows | §2, §6.19, §6.22 |
| Helper distribution-ÉGALE de N hits entre M cibles (hits%N / hits/N) | Doombolt | §6.18 |
| Sélecteur HasTakenDamageOfDamageProfileThisTurn + comptage ennemis-DISTINCTS (wrapper MINCE sur le dict psychic-this-turn #202 — coût faible) | HellfyreMissileRack, InfernalCannon, RealityUnbound | §6.18 |
| SPAWN-SUR-TUILE-DE-DECOY (le summon consomme/remplace le decoy co-localisé) | MightFromBelow (Purestrains), SpiritualLeader (Neophyte) | §6.21 |
| Fondation « trap/mine explose à sa mort » : OnPreDeath-depuis-CRUSH + HasDeathReason (le crush movement.py:50 est un kill PROPRE sans death-trigger) | HaywireMine, SquigMine (apparenté) | §6.22, §6.13 |
