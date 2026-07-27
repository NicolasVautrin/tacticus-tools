# Case — DEBLOQUEUR « cast d'ability par une MACHINE OF WAR hors-plateau »

**Statut** : DEBLOQUE (cote COMBAT / EXECUTION). Confronte live `gqfc5mff6c`, session Frida 71,
boards `C1_02` / `C2_02` (MoW-capables). Correctif **100 % Python** (`scripts/python/**`) — aucun
changement `frida/hooks`, aucun rebuild, aucun reinject.

---

## 1. Correction de premisse : le verrou n'etait PAS le cast live

Le backlog decrivait « le cas MoW-caste-depuis-hors-plateau ne se monte / ne s'exerce pas dans le
runner headless ». **MESURE : c'est faux cote LIVE.** Le harnais est deja entierement MoW-aware :

- `rl_duel build --p-mow/--a-mow` deploie la MoW (gate = slot `MachineOfWarPosition` du board, cf.
  `_board_supports_mow`) ;
- `decisionView.mows` / `observeBattle.mows` la projettent (`projectMowsFull`,
  `ai-step/projection.ts`) avec `casterId == machineId`, `slot`, `abilities[]` (+ `AbilityState`
  per-ability : `level` / `multiplier`) ;
- `abilityTargets` scanne les casters `EntityType.Machine` en plus de `EntityType.Unit`
  (`rpc-targeting.ts`) ;
- `applyAction {kind:"ability", casterId=<machineId>}` execute la cascade native complete.

**Sweep exhaustif des 8 MoW du pool spawnable** (`probe_mow_cast.py sweep`, board `C1_02`, 1 runner
a la fois) — 16 abilities, cast tente sur la 1re cible legale :

| MoW | ability (id) | cibles | cast | observable |
|---|---|---|---|---|
| adeptExorcist | ThriceBlessedConflagration (1187) | 2 | OK | effet pose sur l'allie cible |
| adeptExorcist | DevastatingRefrain (1188) | 33 | OK | effet pose sur la MoW |
| astraOrdnanceBattery | MalleusRocketLauncher (1142) | 33 | OK | marquage (2-phases) |
| astraOrdnanceBattery | ForwardSpotter (1143) | 2 | OK | spawn `astraNpc1Guardsman` (3435 HP) |
| blackForgefiend | HadesAutocannons (1147) | **0** | — | predicat de ciblage non rempli (cf. §5) |
| blackForgefiend | DaemonicOrdnance (1148) | 33 | OK | pose de feu (2-phases) |
| deathCrawler | EntropyCannons (1168) | **0** | — | predicat de ciblage non rempli (cf. §5) |
| deathCrawler | PlagueburstMortar (1169) | 33 | OK | cast tuile |
| orksRukkatrukk | SquigLaunchas (1200) | **0** | — | predicat de ciblage non rempli (cf. §5) |
| orksRukkatrukk | SquigMine (1201) | 29 | OK | marquage de tuiles |
| tauBroadside | HeavyRailRifle (1160) | 2 | OK | `HeavyRailRifle_PendingTarget` (cible) + `HeavyRailRifle_PendingAttack` (**sur la MoW**) |
| tauBroadside | TwinSmartMissileSystem (1161) | 2 | OK | `Markerlight` sur la cible |
| tyranBiovore | BioMinefield (1144) | 2 | OK | spawn `tyranSmnSporeMine` |
| tyranBiovore | SporeMineLauncher (1145) | 25 | OK | spawn `tyranSmnSporeMine` |
| ultraDreadnought | DutyEternal (1158) | 13 | OK | spawn `ultraSmnDreadnought` 19940 HP **sur 3 hexes** |
| ultraDreadnought | MacroPlasmaIncinerator (1159) | 33 | OK | marquage de zone (2-phases) |

=> **13/16 castent sans mise en scene ; les 3 restants sont des predicats de ciblage** (§5), pas des
defauts de harnais.

## 2. Le VRAI verrou : la MoW n'existait pas dans l'etat OFFLINE

`engine/runner/snapshot.py::load_state` n'iterait que `decisionView.units`. Les MoW vivant dans le
canal **separe** `decisionView.mows`, le caster n'existait PAS cote moteur :

```
decisionView.mows   = [{"casterId": 53, "visualId": "tauBroadside", ...}]
combatSnapshot ids  = [49, 51, 54, 56]          <- EntityType.Unit only (mesure d'ALORS)
load_state entities = [49, 51, 54, 56]          <- caster 53 ABSENT
```

> ⚠ **La ligne `EntityType.Unit only` est PERIMEE depuis `d9d0008` (2026-07-26)** :
> `rpc-snapshot.ts:131` teste desormais `ty !== EntityType.Unit && ty !== EntityType.Machine`, donc
> `combatSnapshot.allUnits` **inclut** la MoW (avec un champ `entityType`). Cela ne change rien au
> verrou decrit ici (le caster manquait bien a l'epoque), mais cela cree un defaut NOUVEAU cote port :
> la ligne Machine entre dans la boucle non filtree de `_load_stats_and_effects` et y ecrase le
> `StatsComponent` de la MoW -- cf. `case-162` §4 et le residu **N7** de `port-residuals-inventory.md`.

Consequence : tout port d'ability MoW etait **inconfrontable** (le cast live marchait, l'execution
offline n'avait aucun caster). Le seul port MoW existant (`SporeMineLauncher`, case-220 §6.16)
devait **FABRIQUER** un faux caster a la main dans son test (`_fabricate_caster`) — un contournement
non generalisable : le faux caster ne portait ni effets, ni registre de triggers, ni identite Machine,
donc rien de 2-phases (etat d'attente pose SUR la MoW) n'etait modelisable.

## 3. RE — ce qu'est une MoW dans l'ECS natif

`IdunBattle.Operations.AddMachineOperation$$Execute` **@180e4b5e0** cree la MoW comme entite de
premier plan (`EntityType.Machine` = 6, litteral `6` passe au factory d'entites), puis :

- lie sa/ses plateformes (`EntityType.MachinePlatform` = 7) via
  `MachinePlatformComponent.MachineId` (`Nullable<BEntityId>` : hasValue @+0x14, value @+0x18) —
  ecriture visible en fin de fonction ;
- initialise ses abilities (`AddMachineOperation.InitializeAbilitiesStatus`) ;
- pose le slot de deploiement (`MachineComponent.Position` @0x78 = `MachineOfWarPosition`,
  None/Top/Bottom ; gate board = `BoardConfiguration.HasMachineOfWarPosition` **@1810b39f0**) ;
- `AddMachineOfWarPlatformOperation$$Execute` **@180e4b340** cree les plateformes.

**Jeu de composants MESURE** (`dumpEntityComponents`, entite Machine vivante d'un runner
`--p-mow tauBroadside`) :

```
ParentComponent · EffectsOwnedComponent · TriggeredAbilityComponent · OwnerComponent ·
AttackComponent · CritChanceComponent · CritDamageComponent · ActiveAbilityComponent ·
UnitFlagsComponent · ExtraHitsComponent · ExtraPierceRangedComponent · ExtraPierceComponent ·
ExtraMaxDamageComponent · MachineComponent · ActorStatisticsComponent
```

et la plateforme liee (Type=7) : `MachinePlatformComponent` **seul**.

=> **ni `HealthComponent` ni `PositionComponent`** sur la Machine : une MoW est **hors-plateau**
(pas de PV, pas de tuile). C'est exactement ce que « hors-plateau » veut dire dans l'ECS, et c'est
corrobore par gameconfig : les 8 MoW ont `stats={Health:0, Damage:0, FixedArmor:0}` et
`weapons=[]` (aucune attaque normale) — la ou une unite reguliere a de vraies bases + des armes.
Leur degat vient donc des VARIABLES d'ability (`AActiveAbility.MinMaxDamage` **@180fb2dc0**,
cf. case-172), pas d'une stat d'unite.

## 4. Le correctif (Python uniquement)

`scripts/python/engine/runner/components.py`
- **`MachineComponent`** (mirror `IdunBattle.Entities.Components.MachineComponent`, `Position`@0x78) :
  porte le `slot` et sert de **discriminant** « cette entite est une MoW » (le port n'a pas de champ
  `type` sur l'entite ; le natif ne pose ce composant que sur les Machines).
- **`is_machine_of_war(entity)`**.

`scripts/python/engine/runner/snapshot.py`
- **`_load_machines`** : materialise chaque ligne de `decisionView.mows` en entite ECS clee par
  `casterId` (== `machineId`, l'id qu'attendent `applyAction` / `abilityTargets`), avec
  `UnitComponent` (role `BaseUnitComponent` @180f96380 : identite/alive — `MachineComponent` et
  `UnitComponent` en derivent tous deux, d'ou `VisualId`@0x20 valide sur les deux), `OwnerComponent`,
  `TriggeredAbilityComponent`, `MachineComponent(slot)`, `EffectsOwnedComponent` si effets — et
  **NI `PositionComponent` NI `HealthComponent`** (mirror exact du mesure).
- **`_load_machine_stats`** : `StatsComponent` bati par la MEME chaine que les unites
  (`UnitContext.from_snapshot`) avec un `snap_unit` synthetique **sans bloc `stats`** -> les 8 stats
  de base sont seedees a 0, ce qui EST la valeur gameconfig reelle d'une MoW (aucune valeur inventee).
  Le canal utile = `active_ability_level` / `ability_variables_multiplier`, lus de l'`AbilityState`
  per-ability (`ActiveAbility._abilityState` : `Level`@+0, `VariableMultiplierPercentage`@+4 — mirror
  `get_AbilityState` **@180f8fc40**), le seul canal de niveau qu'ait une MoW (`BattleQuery.GetUnitConfig`
  est indexe par VisualId d'unite).
- Les effets de MoW entrent dans le seed `EffectsState` (mesure : `HeavyRailRifle_PendingAttack` se
  pose sur l'entite Machine).
- **`snapshot_live`** emet aussi les lignes MoW -> `diff(snapshot_live, snapshot(state))` reste
  **equilibre** (sans quoi tout replay-diff MoW signalerait « absente a gauche »).

`engine/playbook/scene.py` + `engine/ai/state_bridge.py` (`_dv_units`, `_obs_units`)
- **les MoW sont EXCLUES** de ces deux canaux, et ca reste vrai apres R14 : le natif ne met que
  `EntityType.Unit` dans `decisionView.units` / `observeBattle.units` (canal `.mows` separe). La face
  DECISION MoW a son PROPRE tactic (`IdunBattle.AI.Tactics.DefaultMachineTactic`, cf.
  `case-r14-mow-decision`), branche par `engine.ai.context.build_machine` +
  `engine_validate.engine_decide` -- jamais en glissant une entite sans position dans `dv.units`.
  Zero contamination de l'agreement.

## 5. Les 3 abilities « 0 cible » = predicats de ciblage, pas un verrou

**RESOLU** — les 3 sont desormais RE, MONTEES et PORTEES (face COMBAT), confrontees live :
**`docs/rl/case-mow-targeting-predicates.md`** (tache #90 lot A, 7 tests
`test_mow_targeting_predicate_live.py`).

| ability | predicat (decompile) | verdict |
|---|---|---|
| `SquigLaunchas` (1200) | `GetDynamicInvalidTargetReason` **@18120ab80** : `HasMinimumAdjacentOrks(nrOfUnits=1)` OU `HasMinimumAdjacentFriendlyUnits(nrOfUnits_2=2)` (« allie » = **du CASTER**, referent `Owner@0x148`) | **PORTE + VALIDE** : 0 cible au spawn ; 1 Ork ami adjacent -> cible legale ; 2 Orks -> le Squig est en plus invoque (`FulfillsSummonCriteria @18120aac0`, seuils **nrOfUnits_3=2 / nrOfUnits_4=4**, evalue AVANT l'attaque via `SetCache`). |
| `HadesAutocannons` (1147) | pas de `GetDynamicInvalidTargetReason` : `TargetingOptions` du ctor **@1811e56b0** + `GetAllTargets` **@1811e5480** (`UnitsWithTrait(2=Summon)`) -> cible = **SUMMON ennemi** ; splash = summons du camp **de la CIBLE** a `<= range`=2, **cible incluse** | **PORTE + VALIDE** (SET frappe identique offline/live ; borne `range` et exclusion des summons ALLIES confrontees). |
| `EntropyCannons` (1168) | `GetDynamicInvalidTargetReason` **@1811bfc20** : `IsInTeamContagionsOfNurgleAura(effet 1071)` OU `HasNegativeModifier(FixedArmor)` | **PORTE + VALIDE** (branche AURA montee avec `deathTyphus` ; branche armure-reduite non montee live, mirror offline `UnitStats.has_negative_modifier` deja present). |

## 6. SECOND VERROU CONFIRME — substrat MULTI-HEX

`DutyEternal` (1158) caste et spawn bien, mais **le summon occupe 3 hexes** (mesure live :
`ultraSmnDreadnought` squadId 72 -> positions **(0,2) (1,3) (1,2)**, un seul squad `EntityType.Unit`
avec 3 `UnitFoot`). Le moteur offline modelise `PositionComponent(col,row)` = **UNE** tuile par unite.

=> Porter `DutyEternal` exige un **substrat multi-hex** (N `UnitFoot` par squad : occupation,
adjacence, ciblage, blocage de pathfinding). **Verrou distinct**, hors perimetre de ce debloqueur.
`AetherStride` est annonce dans la meme famille mais son porteur n'est meme pas spawnable (§7).

## 7. Verdict par item (les 18 abilities annoncees)

Porteurs **dans** le pool MoW spawnable (`rl_duel build --list-pool` -> 8 MoW ; le pool vient des
`Units[]` du seed BC, 175 entrees dont 8 `MachineOfWar`) :

| ability | porteur | debloque ? |
|---|---|---|
| `PlagueburstMortar` (1169) | deathCrawler | **OUI** — cast + caster offline |
| `EntropyCannons` (1168) | deathCrawler | **PORTE + VALIDE LIVE** (#90 lot A, `case-mow-targeting-predicates`) |
| `DaemonicOrdnance` (1148) | blackForgefiend | **OUI** (2-phases : 1er cast pose le feu) |
| `HadesAutocannons` (1147) | blackForgefiend | **PORTE + VALIDE LIVE** (#90 lot A) |
| `MalleusRocketLauncher` (1142) | astraOrdnanceBattery | **OUI** (2-phases : marquage puis barrage) |
| `ForwardSpotter` (1143) | astraOrdnanceBattery | **OUI** (spawn + tour immediat du summon) |
| `ThriceBlessedConflagration` (1187) | adeptExorcist | **OUI** |
| `DevastatingRefrain` (1188) | adeptExorcist | **OUI** (2-phases) |
| `HeavyRailRifle` (1160) | tauBroadside | **OUI** (2-phases, etat d'attente **sur la MoW** — desormais visible offline) |
| `TwinSmartMissileSystem` (1161) | tauBroadside | **OUI** |
| `SquigLaunchas` (1200) | orksRukkatrukk | **PORTE + VALIDE LIVE** (#90 lot A ; degat + summon conditionnel) |
| `SquigMine` (1201) | orksRukkatrukk | **OUI** |
| `MacroPlasmaIncinerator` (1159) | ultraDreadnought | **OUI** (2-phases : zone marquee) |
| `DutyEternal` (1158) | ultraDreadnought | **NON** — bloque par le substrat **multi-hex** (§6) |

Porteurs **absents du seed BC** (donc hors pool : `buildNormalizedBC` n'enumere que `bc.Units[]`) —
**autre verrou**, meme famille que les carriers Votann absents :

| ability | porteur | etat |
|---|---|---|
| `InfernalCannon` (1209) | `thousDaemonPrince` (Z'Kar, MoW) | porteur absent du seed BC -> non spawnable |
| `AetherStride` (1208) | `thousDaemonPrince` | idem (+ suspicion multi-hex) |
| `ReanimationBeam` | `necroReanimator` | porteur absent du seed BC -> non spawnable |
| `NanoscarabRepairProtocols` | `necroReanimator` | idem |

## 8. Residus documentes

- ~~**Stats resolues de MoW non captables**~~ -- **LEVE, la spec ci-dessous EST implementee**
  (`d9d0008`, *#128 lot ATELIER VIDE*, 2026-07-26). `rpc-snapshot.ts:131` (`combatSnapshot.allUnits`) et
  `:367` (`statModSources.targetUnits`) acceptent tous deux `EntityType.Machine`, et les deux charges
  utiles portent un champ `entityType`. Mesure de l'auteur : « 10 units + 2 machines des deux cotes ».
  Texte d'origine conserve pour trace : *« les deux filtrent `ty === EntityType.Unit` ; la MoW a pourtant
  `Attack/CritChance/CritDamage/ExtraHits/ExtraPierce*/ExtraMaxDamage` ; base = 0 (gameconfig), donc le
  seed a 0 est EXACT a l'init ; une stat-modification posee en cours de combat sur la MoW ne serait pas
  captee. Spec : elargir le filtre de `rpc-snapshot.ts` a `EntityType.Machine` ... et idem pour les
  `targetUnits` de `statModSources`. `GetStat` lui-meme est generique. »*
  Cote PORT, la ligne Machine est desormais consommee par `_load_machine_stats` (**#174**).
  Mesure sur `deathCrawler`/`orksRukkatrukk`/`tyranBiovore` : les **19 stats resolues valent 0**,
  `statDelta={}`, `shields=[]`, `healthMax=0` -- le seed a 0 etait donc bien EXACT, et une
  stat-modification posee en cours de combat serait desormais captee par `statDelta`.
  ⚠ Ce que la ligne Machine NE porte PAS : `unitConfig` (elle rend `{"error": "visualId introuvable"}`,
  l'entite portant un `MachineComponent` la ou le capteur cherche un `UnitComponent` -- deux FRERES
  derivant de `IdunBattle.Entities.Components.BaseUnitComponent$$.ctor`, la comparaison du capteur
  etant une egalite de classe). Le niveau d'ability d'une MoW ne vient donc QUE de son `AbilityState`
  per-ability.
  **Consequence non anticipee** : la ligne Machine ainsi emise ecrasait le `StatsComponent` de la
  MoW cote port (`case-162` §4 ; residu **N7**) -- **FERME par #174**
  (`case-174-mow-level-index.md`). La corruption de runner par ces memes RPC (`case-162` §2, residu
  **O7**) reste OUVERTE : c'est la tache **#175**, elle exige un rebuild+reinject.
- ~~**Face DECISION MoW toujours bloquee**~~ -- **LEVE par R14** (`case-r14-mow-decision.md`). Le
  chemin natif dedie n'est pas `aiPlaybookPredict` mais `IdunBattle.AI.Tactics.DefaultMachineTactic`
  (routage `IdunBattle.Core.Services.AiQuery$$GetUnitTacticForUnit` sur `IsMachine`) : generateurs
  d'ability SANS `MovementActionGenerator`, caster a `UnitPosition.NullPosition`, tuiles candidates
  VIDES. Porte (`engine.ai.tactic.DefaultMachineTactic` + `engine.ai.context.build_machine` + routage
  dans `engine_validate.engine_decide`) ; sweep 8/8 MoW sans violation d'invariant, coincidence
  mesuree sur 1187. `_plans_for_unit` reste inchange et n'etait PAS le chemin : une MoW n'a aucune
  tuile candidate, donc aucun plan d'attaque positionnel. Ce qui reste pour les 3 overlays
  `CalculateCustomUtility` de porteur MoW (PlagueburstMortar / DaemonicOrdnance / Malleus) est le
  PORT de leur feuille de decision -- 1187 est la seule des 16 abilities MoW a en avoir une.
- **Multi-hex** (§6) : verrou distinct.

## 9. Validation

- Nouveau test `scripts/python/tests/engine/runner/test_mow_caster_load_live.py` (6 tests, tous
  passants) : loader (composants exacts, ni Position ni Health, level/mult == `AbilityState` live) ;
  forme canonique equilibree ; **zero impact sur un runner sans MoW** ; **exercice** d'une ability MoW
  portee (`SporeMineLauncher` 1145) **depuis le caster CHARGE** (zero fabrication) + confront LIVE
  (equipe / tuile / hp identiques) ; generalisation **2 MoW (une par camp), autre board `C2_02`, autres
  porteurs** ; generalisation **effet 2-phases pose SUR la MoW** (`HeavyRailRifle`) visible offline en
  noms (`EffectsOwnedComponent`) ET en structure (`State.effects`).
- Non-regression (tests CIBLES rejoues, tous verts) : `test_spore_mine_launcher_live`,
  `test_playbook_live`, `test_predict_live`, `test_runner_attack_live`, `test_runner_state_live`,
  `test_turnflow_live`, `test_summon_spawn_live`, `test_summon_ability_ports_live`.
- Probe reutilisable : `scripts/python/probe_mow_cast.py` (`sweep` = tableau §1 ; `offline` = etat du
  caster charge + diff canonique).
