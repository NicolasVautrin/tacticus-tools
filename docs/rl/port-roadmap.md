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
| 1153 HammerOfWrath | bloodIntercessor | opus-solver | |
| 1191 MartialInspiration | custoBladeChampion | opus-solver | `[--]` (ni décision ni combat) mais castée au walk — inclure sa face décision |

### P0-HEAL / P0-REPAIR — substrat prêt (`HealUnitOperation`, repair dans `heal.py`)

1002 CombatRestoratives (ultraApothecary), 1037 RevitalizingMalignancy (deathRotbone),
1039 RitesOfRestoration (adeptHospitaller), 1082 InspiredToGreatness (tauAunShi),
1117 DefendTheDivineWork (admecManipulus, repair) — **opus-solver**, 1 tâche chacune.

### P0-SUMMON — templates ScarabHive / GetEmRuntz / MasterOfTheTutelaries

1016 SendInTheNextWave (astraYarrick), 1021 Incursion (blackPossession), 1040 Poxwalkers
(deathBlightbringer), 1077 EarlyWarningOverride (tauCrisis), 1121 ItItches (tyranParasite),
1166 AberrantHypermorph (genesBiophagus) — **opus-solver**, 1 tâche chacune.

### P0-DAMAGE — template SpiritLeech / CrushingClaws

1000 GauntletsOfUltramar (ultraCalgar), 1038 FoulInfusion (deathPutrifier), 1090 GrapnelLauncher
(spaceHound), 1092 DarkTalonStrike (darkaAzrael), 1122 CordClaw (admecRuststalker), 1129
BloodyFury (worldTerminator), 1202 VigilanceEternal (custoKyrus) — **opus-solver**, 1 tâche chacune.

### P0-EFFECT

1050 HolyDuel (templChampion), 1081 FightingRetreat (tauDarkstrider), 1183 VexillaMagnifica
(custoVexilusPraetor) — **opus-solver**, 1 tâche chacune.

Hors périmètre lineup : 1192/1194 NovaBoost/NovaShield (`tauBossRiptide`, NPC) — veille.

## 4. P1 (#218) — sous-systèmes transverses débloqueurs

À intercaler avec P0 (chacun débloque un GROUPE de faces décision/combat) :

| Sous-système | Débloque | Agent | Réf |
|---|---|---|---|
| Méthodes `BattleQuery` token 0x44/0x77/0x7c/0x7d/0x7f/0xb1 | groupe d'overlays #27 | opus-solver (slots depuis le dump vtable, patron #202-C) | `case-27` |
| Évaluateur DSL de forme/chain | groupe #27 + sélecteurs #216 | **fable-solver** (conception, fork full-tree vs prediction-only ouvert) | `dsl-vocabulary-catalog.md` |
| Réutilisation `GenerateMultiHitAttackPredictions` | groupe #27 | opus-solver | `case-27` |
| Utilité de déplacement (`UtilityMovementCase`, `GetTargetUtilityDiffOnDisplace`) | groupe #27 | opus-solver, escalade fable si structure ambiguë | `case-27` |
| Movement-stop #131/B4 (effets de tuile dans la reachability) + exemption Unstoppable | Stormcaller/ICE, Fire tiles, trait 1042 | opus-solver | `case-205`, `terrain-effects.md` |
| DslContext live-state (#5) | feuilles DSL à état | opus-solver (architecture à poser) | `dsl-live-context-substrate.md` |

## 5. P2 — le reste des kits, par faction

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

### 5.1 Tâches « trait commun de faction » (1 tâche chacune, AVANT les kits porteurs)

| Trait | Porteurs | Agent | Note |
|---|---|---|---|
| ThrillSeekers (x5 EmperorsChildren) | tous les emper* | opus-solver | |
| PrioritisedEfficiency (x7 Votann) | tous les votan* | opus-solver | |
| PutridExplosion (x6 DeathGuard) | deathPutrifier + npc | opus-solver | |
| IndirectFire (x9) | astraOrdnance, ... | opus-solver | vérifier d'abord si legality/LoS le couvre déjà |
| BlessingsOfKhorne (x11 WorldEaters) | world* | opus-solver (câblage) | effets DÉJÀ portés (case-185) — probable simple enregistrement registre, trancher en T-RE courte |
| MartialKatah (x4 Custodes) | custo* | opus-solver (câblage) | effets DÉJÀ portés (case-108 DmgBonus/DmgReduction) — idem |
| Vehicle (x8) | admecDestroyer, ... | opus-solver | probablement couvert par couches globales (pathfinder NotBlockingMovement) — audit court |

### 5.2 Exceptions DURES ou à trancher (ne PAS envoyer en opus-solver direct)

| Item | Porteur | Agent | Pourquoi |
|---|---|---|---|
| 1164 MindControl | genesMagus | **re-expert** (T-RE) puis probable **fable-solver** | prise de contrôle d'une unité ennemie = sémantique ECS inédite (owner-swap) |
| 1009 ResurrectionOrb | necroOverlord | **re-expert** puis opus/fable selon verdict | résurrection (event `UnitResurrected` existe, mécanique complète inconnue) |
| 1058 Waaagh | orksWarboss | **re-expert** d'abord | summon/buff de masse, sémantique inconnue |
| 1028 SupremeCommander | astraCreed | **re-expert** d'abord | summon à sémantique inconnue |
| 1158 DutyEternal | ultraDreadnought | **re-expert** d'abord | summon (dreadnought à la mort ?) à confirmer |
| 1226 Chronometron | necroChronomancer | **fable-solver** | `dp=False` (case-27) : non-modélisation, cadre à concevoir |
| SavageEchoes (id ?) | bloodTerminator | **re-expert** | sans id `ActiveAbilityType` résolu — identifier l'artefact |
| SternguardFocus (id ?) | darkaSternguard | **re-expert** | idem |
| 1100 SorcerousFacade | thousTzaangor | opus-solver **avec lecture case-171 obligatoire** | interaction attaque-normale déjà documentée |
| 1169 PlagueburstMortar, 1148 DaemonicOrdnance, 1142 MalleusRocketLauncher | deathCrawler, blackForgefiend, astraOrdnanceBattery | **BLOQUÉ harnais** | porteur MoW hors-plateau en arène (case-27/#172) — veille, pas de tâche |

## 6. Entretien de la roadmap

- **Régénérer** `audit_kit_coverage.py` + `audit_combat_ability_coverage.py` après chaque merge
  de port (et à chaque changement de build) — les tables par-kit servent de source pour piocher
  les tâches suivantes.
- Les MISSING passifs/traits de `kit-coverage.md` sont des **candidats** (approximation
  registres) : le solver tranche au recon — certains ont déjà leurs effets portés (cf. §5.1) et
  la tâche se réduit à du câblage, voire à rien.
- Cadence validée : panel de 2-3 opus-solvers en vol + orchestrateur sur une tranche à jugement,
  merges séquencés avec garde 31337 combinée à chaque intégration (patron sessions #202/#204/#205).
