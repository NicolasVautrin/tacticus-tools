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
combatSnapshot ids  = [49, 51, 54, 56]          <- EntityType.Unit only
load_state entities = [49, 51, 54, 56]          <- caster 53 ABSENT
```

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
- **les MoW sont EXCLUES** de la face DECISION : le natif ne met que `EntityType.Unit` dans
  `decisionView.units` / `observeBattle.units` (canal `.mows` separe), et la decision MoW native a son
  propre chemin de resolution de caster Machine (case-172, `aiPlaybookPredict`). Zero contamination de
  l'agreement.

## 5. Les 3 abilities « 0 cible » = predicats de ciblage, pas un verrou

Lecture i2 (kit) + confront live :

| ability | predicat (i2) | verdict |
|---|---|---|
| `SquigLaunchas` (1200) | cible ennemie ayant **>=1 Ork allie** ou **>=2 unites alliees** adjacentes (« allie » = **du CASTER**) | **PROUVE montable** : 0 cible au spawn ; en deplacant 2 de MES unites adjacentes a l'ennemi -> **1 cible**, cast OK, degat observe (astraBullgryn 9539 -> 9450). Pure mise en scene. |
| `HadesAutocannons` (1147) | cible = **un SUMMON ennemi** (+ tous les summons ennemis a 2 hexes) | montable : adversaire summoner + laisser invoquer. |
| `EntropyCannons` (1168) | cible = ennemi a **Armure reduite** OU dans une **aura Contagion alliee** | montable : reducteur d'armure, ou allie Death Guard porteur de Contagion. |

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
| `EntropyCannons` (1168) | deathCrawler | **OUI** + monter le predicat (armure reduite / Contagion) |
| `DaemonicOrdnance` (1148) | blackForgefiend | **OUI** (2-phases : 1er cast pose le feu) |
| `HadesAutocannons` (1147) | blackForgefiend | **OUI** + monter le predicat (summon ennemi) |
| `MalleusRocketLauncher` (1142) | astraOrdnanceBattery | **OUI** (2-phases : marquage puis barrage) |
| `ForwardSpotter` (1143) | astraOrdnanceBattery | **OUI** (spawn + tour immediat du summon) |
| `ThriceBlessedConflagration` (1187) | adeptExorcist | **OUI** |
| `DevastatingRefrain` (1188) | adeptExorcist | **OUI** (2-phases) |
| `HeavyRailRifle` (1160) | tauBroadside | **OUI** (2-phases, etat d'attente **sur la MoW** — desormais visible offline) |
| `TwinSmartMissileSystem` (1161) | tauBroadside | **OUI** |
| `SquigLaunchas` (1200) | orksRukkatrukk | **OUI** + geometrie (prouvee §5) |
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

- **Stats resolues de MoW non captables** : `combatSnapshot` (`allUnits`) et `statModSources`
  (`targetUnits`) filtrent tous deux `ty === EntityType.Unit`. La MoW a pourtant
  `Attack/CritChance/CritDamage/ExtraHits/ExtraPierce*/ExtraMaxDamage`. Base = 0 (gameconfig), donc le
  seed a 0 est EXACT a l'init ; une **stat-modification posee en cours de combat sur la MoW** ne serait
  pas captee. **Spec du changement `frida/hooks` requis** (non fait ici : rebuild+reinject interdits) :
  elargir le filtre de `rpc-snapshot.ts` a `EntityType.Machine` pour `combatSnapshot.allUnits` (emission
  d'une section `machines[]` ou inclusion dans `units[]` avec un marqueur), et idem pour les
  `targetUnits` de `statModSources`. `GetStat` lui-meme est generique (aucun autre obstacle).
- **Face DECISION MoW toujours bloquee** : `state_bridge._plans_for_unit` ne feede pas l'attaque d'une
  MoW a `_best_attack` (`origin=None`). C'est le blocage nomme par `case-27` pour les 3 overlays
  `CalculateCustomUtility` de porteur MoW (PlagueburstMortar / DaemonicOrdnance / Malleus). **Non leve**
  par ce debloqueur (qui est cote COMBAT) et volontairement : mirrorer la decision MoW demande le
  chemin natif dedie (case-172), pas de faire passer une entite sans position pour une unite.
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
