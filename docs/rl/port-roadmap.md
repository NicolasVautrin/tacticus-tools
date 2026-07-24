# Roadmap de port par KITS — audit + affectation agents (2026-07-23)

> Livrable de l'audit « kits restants à porter » : découpage en tâches de taille session,
> chaque tâche affectée à un type d'agent. Données : `kit-coverage.md` (généré par
> `audit_kit_coverage.py`, vue par-kit) + `combat-ability-coverage.md` (#95, vue par-ability),
> tous deux régénérés ce jour (build `gqfc5mff6c`).
>
> **Chiffres** : 123 kits lineup — **4 complets** (`admecMarshall`, `genesKelermorph`,
> `genesPrimus`, `thousInfernalMaster`), **119 avec du travail**, **249 items** manquants.
> Côté abilities : 171 actives castables, **16 portées combat**, ~30 playbooks NC décision,
> **27 actives [-D]** (décision portée, combat NO-OP silencieux).

## 1. Doctrine d'affectation des agents

| Agent | Quand l'utiliser | Livrable |
|---|---|---|
| **opus-solver** | artefact natif identifié, template existant : port 1:1, volume mécanique, câblage + validation | PR (worktree isolé) |
| **fable-solver** | cas qui a **résisté**, décompilé **ambigu**, datapoints discriminants à **concevoir**, modélisation inédite | PR + entrée `solving-playbook.md` |
| **re-expert** | énigme RE **seule** (structure/artefact inconnus AVANT de pouvoir découper), pas de port | verdict + VAs |
| **validator** | après chaque PR de solver, avant merge | verdict adversarial |
| **orchestrateur** (session principale) | garde 31337, merges, confrontations oracle, régénération des audits, tranches à jugement | commits master |

**Escalade** : un item `[opus]` qui résiste (divergence non localisée, verdicts contradictoires,
flip-flop) est **reporté candidat fable-solver**, jamais résolu à l'usure
(`feedback_tag_task_model`). Inversement, un « dur » présumé qui se révèle template redescend
en `[opus]`.

## 2. Modèle de découpage d'un kit (patron #202 Abraxas)

Un kit = actives + passifs/triggered + traits de kit. Tranches type (1 tranche = 1 session
d'agent ; parallélisables en worktrees indépendants) :

- **T-RE** — recon kit complet (artefacts natifs, VAs, classification DSL/impératif). Par
  **re-expert** SEULEMENT si la structure est ambiguë ; pour un kit template (1 active DAMAGE
  simple), T-RE est absorbée par le solver.
- **T-COMBAT** — port execute d'UNE ability + probe live PASS. **opus-solver** (PR) par défaut ;
  **fable-solver** si flaggée dure (§5.2).
- **T-PASSIF** — trigger natif (`CreateTrigger`) + effet du passif. **opus-solver** ; fusionnable
  avec T-COMBAT quand le kit tient en une session (≤ 2 items liés).
- **T-DECISION** — playbook NC natif pas encore porté. **opus-solver** ; la confrontation oracle
  (walk natif observé) reste à l'**orchestrateur**.
- **T-VALID** — **validator** sur chaque PR ; garde 31337 + merge par l'**orchestrateur**.

Taille validée empiriquement : 1 ability end-to-end par session (#204), ou 1 tranche de kit
(#202-C). Un kit à 2-3 items = 2-3 sessions d'agents, parallélisables.

## 3. P0 (#217) — résorber DÉCIDER ≠ EXÉCUTER : les 27 actives `[-D]`

La décision CHOISIT ces abilities en walk, l'exécution les NO-OP silencieusement → divergence
d'état invisible. **Chaque ability = 1 tâche solver** (la sémantique est déjà à moitié RE'd dans
le playbook NC porté). Par sous-groupe :

### P0-WALK — castées dans le walk de garde 31337 lui-même (à faire EN PREMIER)

| Ability | Porteur | Agent | Note |
|---|---|---|---|
| 1113 Stormcaller | spaceStormcaller | **fable-solver** | résidu case-35 : zone `GetAddIceTiles @18120cf70` + 3x AoE + stun Flying + gates terrain ICE (#131) — cumul de sous-systèmes |
| 1163 BlackRage | bloodDeathCompany | opus-solver | |
| 1151 TheQuickening | bloodMephiston | opus-solver | |
| 1153 HammerOfWrath | bloodIntercessor | ✅ opus-solver + prérequis (`case-220` §4) | formules `ConditionalAmount`/`MinDistance` + tile-pick de charge (Tile7) à collapser — escalade fable si le collapse ne tient pas ; `@1811e5a40` |
| 1191 MartialInspiration | custoBladeChampion | ✅ opus-solver + prérequis (`case-220` §4) | ⚠ le tag `[--]` était FAUX : décision DÉJÀ portée (`prediction.py:925`, validée #106) — reste combat : 1 effet ForPercentIncrease + `CurrentAbilityIs` + compteur +0x30 (≠ +0x20 !) ; `@1811f2b30` |

### P0-HEAL / P0-REPAIR — CLASSIFIÉ (campagne agents 2026-07-23, `case-220` §1)

| Ability | Porteur | Agent | Verdict (arbre + VAs dans `case-220` §1) |
|---|---|---|---|
| 1002 CombatRestoratives | ultraApothecary | ✅ opus-solver **direct** — **PORTÉ + VALIDÉ LIVE** | Heal ×2 split trait Imperial (Imperial=hpToHeal_2 / non-Imperial=hpToHeal, PAS de cumul, PAS d'exclusion) ; `ultramarines.py` ; live +7477==offline ; `@1811cc590` |
| 1037 RevitalizingMalignancy | deathRotbone | ✅ opus-solver **direct** | jumeau 1002 côté Chaos ; montant Chaos = SOMME var0x20+var0x22 (ne pas fitter) ; `@181200eb0` |
| 1117 DefendTheDivineWork | admecManipulus | ✅ opus-solver + prérequis | feuille Repair multi-cible (clone Heal) + PerformAIAttack multi-unités ; galvanic = pattern quickening DÉJÀ porté ; ⚠ attaque galvanique non-tooltipée à confirmer live ; `@1811d30b0` |
| 1039 RitesOfRestoration | adeptHospitaller | ✅ opus-solver + prérequis | feuille Resurrect (op existante) + sélecteur `AllDeadUnits` ; RNG double PickRandomly + flag no-act ; `@1812033c0` |
| 1082 InspiredToGreatness | tauAunShi | ⚠ **fable-solver** | `ResetActiveAbility` (réactivation d'active, ABSENTE) + override de niveau `Min(...)` — 5 primitives neuves, état d'activation/tour ; `@1811eac00` |

### P0-SUMMON — CLASSIFIÉ (`case-220` §2)

| Ability | Porteur | Agent | Verdict (arbre + VAs dans `case-220` §2) |
|---|---|---|---|
| 1166 AberrantHypermorph | genesBiophagus | ✅ opus-solver **direct** | 0 prérequis — template SpawnTutelaryHorror, spawn 1 adjacent + attaque IA ; `@1811b0550` |
| 1016 SendInTheNextWave | astraYarrick | ✅ opus-solver + prérequis | count dynamique (2+morts alliés, cap 5) + placement range-2 attack-priority ; `@181206490` |
| 1040 Poxwalkers | deathBlightbringer | ✅ opus-solver + prérequis | amount-nodes DSL `RandomAmount`/`Divide`/`Get` + PickRandomly-by-count + range d'effet Nurgle ; `@181208b80` |
| 1021 Incursion | blackPossession | ✅ opus-solver + prérequis | combinateur `ChainBehaviour` (boucle ≤6 ré-évaluée par itération) + `GetNextSpawnTile` ; `@1811e9fe0` |
| 1077 EarlyWarningOverride | tauCrisis | ✅ opus-solver (spawn) + **sous-système Overwatch** (§4) | drones portables tout de suite ; volet réactivation Overwatch (+1892) bloqué sur le sous-système — agreement partiel assumé d'ici là ; `@1811d7310` |
| 1121 ItItches | tyranParasite | ⚠ **fable-solver** | multi-étage atomique positionnel (suppress + push + kill + hexes libérés + spawn Rippers + `PerformAIAbility` + ResetMovement) ; dépend de P1 PerformAIAction ; `@1811ebd40` |

### P0-DAMAGE — CLASSIFIÉ (`case-220` §3)

| Ability | Porteur | Agent | Verdict (arbre + VAs dans `case-220` §3) |
|---|---|---|---|
| 1122 CordClaw | admecRuststalker | ✅ opus-solver **direct** | jumeau CrushingClaws, effet 0x4e2 DÉJÀ porté (`hits.py`) ; `@1811ccbf0` |
| 1202 VigilanceEternal | custoKyrus | ✅ opus-solver **direct** | template HeroicFusillade EXACT (move-si-pas-adjacent + attack) ; `@18122a580` |
| 1000 GauntletsOfUltramar | ultraCalgar | ✅ opus-solver **direct** | splash 2 bandes (adjacent + anneau r=2) ; sélecteur set-diff trivial ; `@1811e1c80` |
| 1038 FoulInfusion | deathPutrifier | ✅ opus-solver + prérequis | feuille `UseNormalAttack` (thin) ; effet aura 0x432 DÉJÀ porté ; `@1811dffb0` |
| 1092 DarkTalonStrike | darkaAzrael | opus-solver, borderline fable | géométrie ligne hex + heuristique best-line — RE `GetTilesInBestLine @1811d16f0` AVANT de figer ; `@1811d1440` |
| 1090 GrapnelLauncher | spaceHound | ⚠ **fable-solver** | ≥6 primitives pull/kill/remove-from-tile/placement + If imbriqués sur IsDead ; `@1811e29c0` |
| 1129 BloodyFury | worldTerminator | ⚠ **fable-solver** | primitive `ChainLeftOverHitsAttackDamage` (cleave coups-restants) + tri par prédiction de dégât + kill intra-attaque ; `@1811bbbc0` |

### P0-EFFECT — CLASSIFIÉ (`case-220` §4)

| Ability | Porteur | Agent | Verdict (arbre + VAs dans `case-220` §4) |
|---|---|---|---|
| 1183 VexillaMagnifica | custoVexilusPraetor | ✅ opus-solver + prérequis | 2 selectors seulement (`SortUnitsByDamageUtility`, `NormalUnits`) — Stun + DmgReduction DÉJÀ portés, template splash ; `@18122a020` |
| 1050 HolyDuel | templChampion | ✅ opus-solver + prérequis | 3 effet-classes du bond Duel (taunt mutuel no-expiry + ±dégât) — feuilles AddBondEffect/UseActiveAbility présentes ; `@1811e97a0` |
| 1081 FightingRetreat | tauDarkstrider | ⚠ **fable-solver** | ré-entrance de tour (`ResetTurn` — le caster peut rebouger) touche le scheduler + ~6 primitives neuves ; effets ±dégât DÉJÀ portés ; `@1811ddf90` |

Hors périmètre lineup : 1192/1194 NovaBoost/NovaShield (`tauBossRiptide`, NPC) — veille.

## 4. P1 (#218) — sous-systèmes transverses débloqueurs

À intercaler avec P0 (chacun débloque un GROUPE de faces décision/combat) :

| Sous-système | Débloque | Agent | Réf |
|---|---|---|---|
| Méthodes `BattleQuery` token 0x44/0x77/0x7c/0x7d/0x7f/0xb1 (+0x7b, légalité MindControl — non bloquant, mirror direct possible) | groupe d'overlays #27 | opus-solver (slots depuis le dump vtable, patron #202-C) | `case-27`, `case-219` §1 |
| **`PerformAIAction` — feuille unifiée + dispatch after-hit** (PROMU depuis le fix-forward fork #217) | Waaagh (§5.2), SupremeCommander (§5.2), act-again BlackRage, refactor CultDemagogue/`quickening.py`/`summon.py` | opus-solver | `case-219` §7, `case-217-thequickening` §5 |
| `GetAbilityStatModification` (petit mirror `UnitExtensions`) | SupremeCommander (canal Kell) + futures interactions « si X en jeu » | opus-solver (fusionnable avec la tâche SupremeCommander) | `case-219` §4 |
| Évaluateur DSL de forme/chain | groupe #27 + sélecteurs #216 | **fable-solver** (conception, fork full-tree vs prediction-only ouvert) | `dsl-vocabulary-catalog.md` |
| Réutilisation `GenerateMultiHitAttackPredictions` | groupe #27 | opus-solver | `case-27` |
| Utilité de déplacement (`UtilityMovementCase`, `GetTargetUtilityDiffOnDisplace`) | groupe #27 | opus-solver, escalade fable si structure ambiguë | `case-27` |
| Movement-stop #131/B4 (effets de tuile dans la reachability) + exemption Unstoppable | Stormcaller/ICE, Fire tiles, trait 1042 | opus-solver | `case-205`, `terrain-effects.md` |
| **Sous-système Overwatch en combat** (effets 1009/1144/1145/1149, `@180f40550`/`@180f40360`) | 1077 EarlyWarningOverride (volet réactivation) + blind spot IA overwatch connu | opus-solver (RE d'abord), escalade fable si état transient ambigu | `case-220` §2 |
| DslContext live-state (#5) | feuilles DSL à état | opus-solver (architecture à poser) | `dsl-live-context-substrate.md` |

### 4.1 Consolidation campagne `case-220` (2026-07-23) — top débloqueurs par nombre d'items

Ledger complet (~60 familles, avec VAs et items sourceurs) : `case-220-classification-campaign.md` §T.
Classement des NOUVEAUX sous-systèmes par retour sur investissement (items débloqués) :

| Sous-système (nouveau) | Items débloqués | Agent | Réf §T |
|---|---|---|---|
| **Harnais cast-par-MoW hors-plateau** | **17 items** BLOQUÉS (DutyEternal, Malleus, 2x tauBroadside, 2x necroReanimator, 2x adeptExorcist, 2x orksRukkatrukk, 2x thousDaemonPrince, EntropyCannons, MacroPlasmaIncinerator, HadesAutocannons, ForwardSpotter, DeathOnTheWind/Hailstrike) | **fable** (prouver le cast MoW en runner) | case-219 §5 |
| **Feuille AddStaticStatModifierEffect** (self / ToOwner / sur SÉLECTEUR) | 9 items (4 BlackTemplars + DoomSiren, ExcruciatingFrequencies, RefusalToBeOutdone, LeadingTheCharge, TrophyTaker) | opus | §T |
| **Persistent-data store** (Set/Get/Add/Clear, scalar+LIST+compteur) | 8 items (StandVigil, LegendaryCommander, PrioritisedEfficiency, FuryFromTheDelve, AncestralFortune, HazeOfCorruption, HaywireMine, AggressiveOnslaught) — Fury/Fortune retombent quasi-opus après | fable (1er port), retombées opus | §T |
| **Vecteur On(ArrivedAtFinalTile=28)** (émettre AUSSI en fin de tour sans move) | 7 items (FabricatorClawArray, LivingLightning, SanguinaryPriest, RedRampage, FuryOfTheAncients, ChampionOfTheFeast, SpiritualLeader) | opus (turnflow pose déjà le flag) | §T |
| ~~**Sous-système REVIVE**~~ **BASE PORTÉE** (`ReviveEffect` + `ReviveUnitOperation`, commit `864a371`, carrier `deathRotbone`/TaintedNarthecium validé live) | **TaintedNarthecium = PORTÉ**. Restent **6 consommateurs** (Narthecium, FuelledByFury/C, PhoenixGem, GhostRevive, RitesOfMorkai, TimeFlux) : ils héritent la structure, ne restent que filtre + vars + gate overkill | ~~fable~~ → **opus** (base en place) | §T, `case-66-revive-in-place.md` |
| **Vecteurs réactifs DÉFENSEUR** (on-being-hit On 58, PreUnitMove=31, UnitBlocked=0x3d, pré-attaque 0x2b + ANNULATION, riposte) | ~11 items (UnwaveringSentinel, MomentShackle, Deathwing, GrimRetribution, Hailstrike, HatefulAssault, GeminaeSuperia, MedicusMinistorum, AnvilShield, WireweaveNet, MartialSuperiority, SwornProtector) | fable (ordre d'exécution du pipeline) | §T |
| **Sous-système PENDING-ATTACK** (bond + snapshot + fire turn-start) | 4 classifiés (OverwhelmingWrath, SeekerMissile, HeavyRailRifle, DevastatingRefrain) + ~18 kits roster en enum | fable (brique commune) | §T |
| **PRIMITIVE AURA CONTAGION** (range = f(round)) + source armor-reduction | CursedPlagueBell x2, EntropyCannons, FoulInfusion, Poxwalkers + 6 héros DG | opus | §T |
| **Géométrie ligne hex** (best-line, TilesBehindInLine, array-par-position) | 6 items (DarkTalon, Excruciating, DeathOnTheWind, ThriceBlessed, RadBombardment, SwoopingHawk) | opus (helper cube existe côté décision) | §T |
| **Kill-events KILLER-side** On(0/53/54/55 & OwnerIsActor) + On(54) au CRUSH + IsDefeatedByMeleeAttack | Possession, HeadClaimer, BarbedOvipositor, CosmicHorror | opus | §T |
| **Feuille Repair DSL** + sélecteurs Repairable/UnitsAffectedByHealType | DefendTheDivineWork(+GalvanicField fold), FabricatorClawArray, RelentlessMarch, ReanimationBeam | opus | §T |
| **ChainLeftOverHitsAttackDamage** (report hits sur kill) | BloodyFury, MultiThreatEliminator, Fragstorm | opus (candidat fable si RNG délicat) | §T |
| Canal PIERCE attaquant/aura (`for_piercing` orphelin) ; canal CRIT-ATTAQUANT (hooks 0-user) ; NumLeftOverHits ; ResetMovement ; HasTakenDamageOfDamageProfileThisTurn (wrapper #202) ; AddEffectOrIncreaseLevel ; custom normal-attack (pattern MV71) ; spawn-sur-decoy ; MinMaxDamage2/3 | 2-4 items chacun — petits leviers à prendre AVEC le premier item consommateur | opus | §T |

**Règle par défaut** (sauf exceptions §5.2) : chaque kit de `kit-coverage.md` se découpe selon
le modèle §2, TOUT en **opus-solver** (1 tâche par active NO-OP, 1 par passif non câblé), PR +
validator + merge orchestrateur. La table par-kit de `kit-coverage.md` EST la liste des tâches —
ne pas la dupliquer ici ; piocher faction par faction dans l'ordre du volume :

AstraMilitarum (15) > EmperorsChildren (15) > Custodes (14) > WorldEaters (14) > DarkAngels (14)
> Tau (14) > Ultramarines (14) > DeathGuard (13) > Necrons (13) > Votann (12) > BlackLegion (12)
> BloodAngels (12) > Orks (11) > Sisterhood (11) > SpaceWolves (11) > Tyranids (10) > AdMec (9)
> Aeldari (9) > BlackTemplars (9) > ThousandSons (9) > Genestealers (6) > AdeptusAstartes (2).

(#20 « Roadmap AdMec » est absorbée ici : AdMec = 4 kits / 9 items, règle par défaut, aucune
exception dure détectée sauf `SentinelDirectives` à classifier en T-RE.)

### 5.1 Tâches « trait commun de faction » — CLASSIFIÉ (`case-220` §5)

**4 sur 7 sont FERMÉS sans travail** (déjà couverts ou invalidables) — il ne reste que 2 ports
[opus] + 1 [fable] :

| Trait | Porteurs | Verdict | Note (`case-220` §5) |
|---|---|---|---|
| MartialKatah (x4 Custodes) | custo* | ✅ **CLOS — rien à faire** | déjà porté + validé bit-exact (#105/#57d), registres complets |
| BlessingsOfKhorne (x11 WorldEaters) | world* | ✅ **CLOS — rien à faire** | validé bit-exact deux faces (case-185) ; ⚠ matérialisation par CAPTURE, PAS un enregistrement `TRAIT_OWNER_EFFECTS` (l'y ajouter serait FAUX) ; résiduel N-tracking runner = suite séparée case-185 |
| IndirectFire (x9) | astraOrdnance, ... | ✅ **CLOS — rien à faire** | volet Trench déjà câblé (`calculate_trench_reduction` gate) ; volet obscuring : moteur déjà over-permissif → rien à exempter (le gap = LoS des NON-porteurs, fondation séparée) |
| Vehicle (x8) | admecDestroyer, ... | ✅ **CLOS** (rattaché #131/B4) | target-trait déjà consommé (BeastSlayer) ; exemption mouvement = fondation déferrée INVALIDABLE (case-205 §3) — la porter = registered-but-dead |
| PutridExplosion (x6 DeathGuard) | deathPutrifier + npc | **opus-solver, 1 tranche** | fire-on-death miroir FinalJustice + AoE ability-damage 25% maxHP Toxic, exclusion faction DeathGuard ; VALIDABLE ; `@1812248f0` |
| ThrillSeekers (x5 EmperorsChildren) | emper* | **opus-solver, 1-2 tranches** | trigger 2 events (attaque pleine-vie / dégât subi) → effet Thrilled 1434 +15 CritChance 1 round ; events 6/0xf à confirmer ; `@1811a8570` |
| PrioritisedEfficiency (x7 Votann) | votan* | ⚠ **fable-solver** | machine de STANCE partagée-équipe (persistent-data + StanceDefiningUnit + parité d'actives + re-application turn-start + 1 Movement) — proche chantier DslContext #5 ; `@181114b80` |

### 5.2 Exceptions DURES ou à trancher (ne PAS envoyer en opus-solver direct)

| Item | Porteur | Agent | Pourquoi |
|---|---|---|---|
> **T-RE campagne 2026-07-23 (`case-219`)** : les 6 énigmes historiques sont TRANCHÉES par
> l'orchestrateur — 5 descendent en `[opus]` dispatchable, 1 reste bloquée substrat. Les lignes
> ✅ sont prêtes pour un solver SANS re-enquête (arbre + VAs dans le case doc).

| Item | Porteur | Agent | Verdict RE |
|---|---|---|---|
| 1164 MindControl | genesMagus | ✅ **opus-solver** (T-RE FAITE, `case-219` §1) | PAS d'owner-swap : 2 debuffs (1349 flat −dmgReduction sortant / 1350 +% subis) + taunt bondé 27/1367 vers l'allié adjacent max-Health, gate trait 25 Immune — substrat Taunted/AddBondEffect DÉJÀ porté ; `ExecuteBehaviour @1811f3ec0` |
| 1009 ResurrectionOrb | necroOverlord | ✅ **opus-solver** (T-RE FAITE, `case-219` §2) | summon template PUR (pas de résurrection) : `Min(morts LivingMetal alliés + turnsStarted, 6)` × necroSmnWarrior adjacents ; nouveau sélecteur `AllDeadOrResurrectedUnits` ; `@181200140` |
| 1058 Waaagh | orksWarboss | ✅ **opus-solver, 2 tranches** (T-RE FAITE, `case-219` §3) | 5 groupes séquentiels TOUS nommés/template (spawn, buff équipe, charge `SortTilesByUtility`, attaque normale, Boyz jouent) ; prérequis partagé `PerformAIAction` (§4) ; `@18122b010` |
| 1028 SupremeCommander | astraCreed | ✅ **opus-solver** (T-RE FAITE, `case-219` §4) | summon + `PerformAIAction` (Guardsmen jouent) + canal `GetAbilityStatModification` (interaction Kell : +1 summon, range 3) ; `@18120df30` |
| 1158 DutyEternal | ultraDreadnought | ⛔ `[opus]` **BLOQUÉ substrat** (T-RE FAITE, `case-219` §5) | transform MoW → unité 3-hex stationnaire (`RemoveMachine` + `Spawn(ThreeTileUnitSpawnShape)` + transfert questUnitId + trait Stationary) — pas un summon-à-la-mort ; prérequis = footprint multi-hex + cast par MoW hors-plateau ; `@1811d6b70` |
| 1226 Chronometron | necroChronomancer | **fable-solver** | `dp=False` (case-27) : non-modélisation, cadre à concevoir (NON re-examinée en case-219) |
| ~~SavageEchoes (id ?)~~ **1230** | bloodTerminator | ✅ **opus-solver** (id RÉSOLU, `case-219` §6) | tâche kit NORMALE (4× Eviscerate + healthPct 50 ; passif RedRampage 1551) — enum mirrors fixés (tsv stale) ; `@181204660` |
| ~~SternguardFocus (id ?)~~ **1228** | darkaSternguard | ✅ **opus-solver** (affiné `case-220` §6.5) | [opus]+prérequis : pattern OVERRIDE-ATTAQUE (1er user runner) + PercentageOfAttackCappedAtMax runner + ChangeCooldown (1548) ; ⚠ passif SpecialIssueCombiMelta 1545 = **[fable]**, RE à finir (effets 1563/1564 non lus) ; `@18120bca0` |
| 1100 SorcerousFacade | thousTzaangor | opus-solver **avec lecture case-171 obligatoire** | interaction attaque-normale déjà documentée |
| 1169 PlagueburstMortar, 1148 DaemonicOrdnance, 1142 MalleusRocketLauncher | deathCrawler, blackForgefiend, astraOrdnanceBattery | **BLOQUÉ harnais** | porteur MoW hors-plateau en arène (case-27/#172) — veille, pas de tâche ; **DutyEternal rejoint ce groupe** avec débloqueur explicite (multi-hex) |

### 5.3 Classification par faction — campagne `case-220` §6 (**COMPLÈTE 2026-07-23**, 24/24 tranches)

Les verdicts détaillés (VAs, arbres, prérequis) vivent dans `docs/rl/case-220/<tranche>.md`
(sommaire dans `case-220-classification-campaign.md`) ; le ledger des prérequis transverses =
`case-220` §T (~60 familles, la consolidation §4 P1 pointe dessus).

| Faction | Statut | Verdicts (détail `case-220` §6.x) |
|---|---|---|
| Custodes | ✅ classifiée (§6.1) | COUVERT : DaughterOfTheAbyss (déjà porté #184 — MISSING de `kit-coverage.md` à tort) ; [opus] direct : StandVigil ; [opus]+prérequis : TalonsOfTheEmperor, LegacyOfCombat (candidat fable) ; **[fable]** : UnwaveringSentinel, MomentShackle (sous-tranche décision-heal isolable [opus]), LegendaryCommander |
| AstraMilitarum | ✅ classifiée (§6.2) | quasi-couverts : SpotterReworked, Nightshroud (effets DÉJÀ portés — restes = pose runner-face) ; [opus] direct : AvalancheOfMuscle (clone FeederTendrils) ; [opus]+prérequis : ToughToKill, FragBomb, PsychicMaelstrom, BasiliskBarrage ; bloqué harnais MoW : ForwardSpotter ; mixte : SummaryExecution ; **[fable]** : SwornProtector, LeadingTheCharge |
| WorldEaters | ✅ classifiée (§6.3) | STALE kit-coverage : MurderousSwing 1137 DÉJÀ porté #108 ; [opus] direct : JakhalStimms ; [opus]+prérequis : WrathfulDevotion, Skullsmasher, TrophyTaker, OverwhelmingWrath (S2 candidat fable) ; **[fable]** : KillMaimBurn |
| EmperorsChildren | ✅ classifiée (§6.4) | [opus]+prérequis : TerrifyingCrescendo (effet déjà porté #204), LashOfTorment, EuphoricStrikes, ExcruciatingFrequencies, EcstaticSlaughter (dépend ThrillSeekers) + moitiés opus DoomSiren/ObsessiveAnnunciation ; **[fable]** : DaemonicPatrons, RefusalToBeOutdone, ArmourOfShriekingSouls (+ moitiés fable DoomSiren extra-hit, ObsessiveAnnunciation aura-crit) |
| DarkAngels | ✅ classifiée (§6.5) | [opus] direct : PlasmaCannon (0 prérequis) ; [opus]+prérequis : Supercharge, EnmityForTheUnworthy, FearedInterrogator, SternguardFocus (pattern override-attaque, 1er user runner) ; **[fable] x8** : CalibaniteGreatsword, LionHelm, GrimRetribution, Deathwing, ExemplarOfHate, SpecialIssueCombiMelta (RE à finir — effets 1563/1564 non lus), DeathOnTheWind + Hailstrike (MoW, groupe harnais) |
| Tau | ✅ classifiée (§6.6) | COUVERTS : MV71 passif 1119, CyclicIonBlaster (faux positifs) ; [opus] direct : DefenderOfTheGreaterGood/ExtraDmg ; [opus]+prérequis : StructuralAnalyser, ExemplarOfTheMontka, SereneUnifier, TwinSmartMissileSystem (MoW) ; **[fable]** : DotGG/ExtraHits (Maybe), SeekerMissileFrequencyLock + HeavyRailRifle (pending-attack, MoW), WayOfTheShortBlade, ExemplarOfTheKauyon |
| Necrons | ✅ classifiée (§6.7) | [opus] direct : MartialApotheosis, HarbingerOfDestruction ; [opus]+prérequis : FabricatorClawArray, RelentlessMarch, LivingLightning, MultiThreatEliminator (candidat fable), AdaptiveStrategy, TimesplinterMantle (pivot combat-flat) ; **[fable]** : InescapableDeath (overwatch) + ReanimationBeam/NanoscarabRepairProtocols (BLOQUÉS MoW). Débloqueurs faction : feuille Repair DSL + vecteur On(28) |
| DeathGuard | ✅ classifiée (§6.8) | COUVERT : ExplosiveMaladies (faux positif, validé #57c-C) ; [opus] direct : DestroyerHive, FlailSwing ; [opus]+prérequis : PlagueWind, CursedPlagueBell x2 ; BLOQUÉ MoW : EntropyCannons ; **PORTÉ : TaintedNarthecium** (`864a371`, base REVIVE) ; **[fable]** : HazeOfCorruption (leftover-overkill). Levier #1 : PRIMITIVE AURA CONTAGION |
| Ultramarines | ✅ classifiée (§6.9) | COUVERT : RitesOfBattle (faux positif) ; [opus] direct : PsychicFortress, MortisRound, DeathFromAbove, FuelledByFury/A ; [opus]+prérequis : ShockAssault, StormOfWrath (RE ChainAbilityDamage d'abord), CamoCloak (à différer) ; **[opus]** (base REVIVE portée `864a371`) : Narthecium + FuelledByFury/C ; **[fable]** : TacticalPrecision (IsCharging), MacroPlasmaIncinerator (MoW) |
| Votann | ✅ classifiée (§6.10) | RIEN de porté (ni combat ni décision) ; [opus] direct : IronkinSteeljack, AugmentedAssault, GravitonRifle (attaque) ; [opus]+prérequis : PredictiveGuidance, GrimEfficiency (GATE DUR PrioritisedEfficiency) ; **[fable]** : FuryFromTheDelve, EcogSupport (repair-combat), AncestralFortune. Levier : persistent-data (2 items retombent quasi-opus) |
| BlackLegion | ✅ classifiée (§6.11) | [opus] direct : BringerOfDespair ; [opus]+prérequis : FrenziedFiring, Possession, FleshmetalGuns (runner-face, effets portés), HeadClaimer, FirstAmongTraitors, Herald, Drachnyen (borderline) ; **[fable]** : HatefulAssault (before-move) ; BLOQUÉ MoW : HadesAutocannons. + trait LetTheGalaxyBurn 1482 non wiré |
| BloodAngels | ✅ classifiée (§6.12) | [opus] direct : SavageEchoes 1230 (template ArmoriumCherub) ; [opus]+prérequis : LordOfTheHost/1377, SanguinaryPriest, BloodChalice, RedRampage, VisionsOfHeresy ; **[fable]** : FuryOfTheAncients (ChainAttackDamage + no-heal), AggressiveOnslaught (bloqué HammerOfWrath). Débloqueur #1 : vecteur On(28) |
| Orks | ✅ classifiée (§6.13) | quasi-couverts : SquigHound, SmashaEad, PowerTrip (gaps mineurs) ; [opus]+prérequis : GrotTank, KustomForceFieldReworked, LightImUp, DakkaDakkaDakka ; **[fable]** : UnstoppableMomentum (charge impérative) ; BLOQUÉ MoW : SquigLaunchas, SquigMine. Levier #1 : NumLeftOverHits |
| Sisterhood | ✅ classifiée (§6.14) | COUVERTS : ArmoriumCherub, FireOfAbsolution (faux positif), ActOfFaith, RighteousRepugnance/A, SanctorumMissile (porté), SkyStrike (porté COMBAT), CondemnorStake (porté COMBAT + validé live, effet 1076) ; [opus] direct restant : aucun ; [opus]+prérequis : BrazierOfHolyFire, MedicusMinistorum, RighteousRepugnance/B, GeminaeSuperia ; BLOQUÉ MoW (adeptExorcist) : ThriceBlessed, DevastatingRefrain |
| SpaceWolves | ✅ classifiée (§6.15) | [opus] direct : GreatFrostAxe ; [opus]+prérequis : Foehammer, SagaOfTheWarriorBorn, WarHowl, HuntersBeyondDeath (borderline), HealingBalms (1re active heal) ; **[fable]** : AnvilShield (dispatch UnitBlocked), SavageKiller, RitesOfMorkai (revive-once) |
| Tyranids | ✅ classifiée (§6.16) | COUVERTS x5 (SpiritLeech, CrushingClaws, FeederTendrils, Neuroparasite, GuardianOrganism — sur-report) ; [opus] direct : SporeMineLauncher, AlphaWarrior ; [opus]+prérequis : BarbedOvipositor, SynapticLinchpin, FearOfTheUnseen ; **[fable]** : BioMinefield. ⚠ kits summons downstream (FloatingDeath…) = tâche séparée |
| AdeptusMechanicus | ✅ classifiée (§6.17) | CLOS/fold : Vehicle, GalvanicField (combat = fold 1117) ; [opus] direct : SentinelDirectives ; [opus]+prérequis : MasterAnnihilator (pose seule — effet validé), HeavyGravCannon (canal pierce), RadBombardment ; **[fable]** : OptimizedGait (react-to-ally-attack) |
| ThousandSons | ✅ classifiée (§6.18) | COUVERT : ArcaneShield (#149) ; [opus]+prérequis : RealityUnbound (0 primitive neuve), Doombolt, HellfyreMissileRack, PsychicStalk (aura à risque), TimeFlux/regen ; **[fable]** : AttemptedPossession (PerformAIAbility généralisé), TimeFlux/ghost-revive ; BLOQUÉ MoW : InfernalCannon, AetherStride (jumeau DutyEternal) |
| Aeldari | ✅ classifiée (§6.19) | COUVERT : Doom (#57c) ; [opus] direct : Executioner, HarvesterOfSouls (décisions déjà validées #122) ; [opus]+prérequis : TerrorsLament, FireAndReposition (ResetMovement), SilentDeath (snake-chain), InescapableAccuracy (canal crit-attaquant 1er user) ; **[fable]** : WireweaveNet (riposte pre-hit + annulation), SwoopingHawk |
| BlackTemplars | ✅ classifiée (§6.20) | COUVERTS : ThunderousAssault, AstartesBanner ; [opus]+prérequis : CrusadeOfWrath, ChampionOfTheFeast, Boltstorm (pattern MV71), DestroyTheWitch, UnbreakableDuty, Fragstorm (candidat fable) ; **[fable]** : MartialSuperiority (contre pré-attaque On 0x2b). Levier #1 : feuille AddStaticStatModifierEffect |
| Genestealers | ✅ classifiée (§6.21) | COUVERT : TwistedScience (décision live-validée) ; [opus]+prérequis : MightFromBelow, SpiritualLeader (spawn-sur-decoy) ; **[fable]** : CosmicHorror (RE ability 1025 OBLIGATOIRE avant port — ambiguïté gates 60%) |
| AdeptusAstartes | ✅ classifiée (§6.22) | [opus]+prérequis : StrikeFromTheShadows (magnitude effet 1549 à RE — sinon fable) ; **[fable]** : HaywireMine (persistent-data + OnPreDeath-depuis-crush). ⚠ i2 absent pour ce kit |

## 6. Entretien de la roadmap

- **Régénérer** `audit_kit_coverage.py` + `audit_combat_ability_coverage.py` après chaque merge
  de port (et à chaque changement de build) — les tables par-kit servent de source pour piocher
  les tâches suivantes.
- Les MISSING passifs/traits de `kit-coverage.md` sont des **candidats** (approximation
  registres) : le solver tranche au recon — certains ont déjà leurs effets portés (cf. §5.1) et
  la tâche se réduit à du câblage, voire à rien.
- Cadence validée : panel de 2-3 opus-solvers en vol + orchestrateur sur une tranche à jugement,
  merges séquencés avec garde 31337 combinée à chaque intégration (patron sessions #202/#204/#205).
