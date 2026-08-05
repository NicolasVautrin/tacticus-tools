# case-92 / case-54 — Injection de porteurs au catalogue de bataille

Debloqueur de harnais : rendre confrontable N'IMPORTE QUEL porteur du gameconfig, y compris ceux
que le seed BC capture ne contient pas. Couvre les deux familles bloquees — `thousDaemonPrince`
et `necroReanimator` (#92, Machines of War) et les carriers Votann hors seed BC (#54) — par UN
seul mecanisme.

Outil : `scripts/python/catalog_inject.py`. Confront live : `scripts/python/probe_92_catalog.py`.
Test : `scripts/python/tests/engine/runner/test_catalog_inject_live.py`.

## 1. Le verrou, et ou il vit reellement

`data/seed-bc.json` est la capture d'UNE bataille reelle : son `Units[]` ne contient que les 175
unites que le compte possedait ce jour-la. 17 unites `units.lineup` du gameconfig n'y sont pas —
dont les 4 heros Votann, `thousDaemonPrince`, `necroReanimator` et `darkaStormSpeeder` :

```
    adeptCelestine      astarCyrus        bloodTerminator     darkaSternguard
MoW darkaStormSpeeder   emperExultant     emperFlawlessBlade  emperLucius
    necroChronomancer   MoW necroReanimator                   spaceWolfPriest
    tauFarsight         MoW thousDaemonPrince                 votanBeserk
    votanIronmaster     votanMemnyr       votanUthar
```

`rl_duel build --p-units <id>` les refuse (« hors pool »), donc leurs abilities etaient
inconfrontables — pas difficiles : impossibles.

**Le catalogue d'unites d'une bataille EST `BattleConfiguration.Units`.**
`IdunBattle.Core.Services.BattleQuery$$GetUnitConfig(this, string unitId)` resout un unitId en
parcourant la liste `Units` de la BC (BC+0x80) et en comparant `UnitConfiguration.Id` (champ
+0x10) ; sur echec il journalise une erreur et rend null. Toute la chaine de spawn
(`IdunBattle.Messages.AddUnitMessage` -> `IdunBattle.Operations.AddUnitOperation$$Execute`, et
`IdunBattle.Messages.AddMachineMessage` pour les MoW) part de ce lookup.

Cette liste est **construite, pas figee** :
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$AddMainPlayerUnitConfigs` /
`$$AddPredefinedUnitConfigs` / `$$AddSummonUnitConfigs` appellent tous
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration(unit, universe, ...)` puis
`List.Add(BC.Units, cfg)`, avec dedupe par Id (OrderedSet). Ajouter une entree au catalogue n'est
donc pas un hack : c'est litteralement ce que le jeu fait quand une unite entre en bataille.

## 2. Le second catalogue — la piece qui manquait

Un porteur injecte avec sa seule entree `Units` **se deploie, s'affiche au `decisionView` avec ses
abilities au bon niveau… et FAUTE au cast** (« system error » cote Frida). La cause n'est ni le
headless, ni l'entree : c'est le SECOND catalogue.

`BattleConfiguration.Abilities` (`IdunBattle.Configuration.AbilitiesConfiguration`, keye par NOM)
porte les `Variables` / `Constants` / `AttackRangeType` de chaque ability. Le seed BC capture ne
contient QUE celles des unites de cette bataille-la : 131 actives + 194 passives.

Chaine causale, lue dans le decompile :

- `IdunBattle.Configuration.AbilitiesConfiguration$$GetActive` fait un `TryGetValue` ; **sur echec
  il construit et rend une `AbilityConfiguration` VIDE** (pas d'exception, pas de null).
- `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` appelle
  `TryGetVariableArrayForLevel` ; si la variable est absente et que le flag « quiet » est nul, il
  **construit une `System.Exception` et la LEVE**.
- `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant` delegue a
  `$$GetStringConstant` puis `System.Int32.Parse(null)` — meme classe de faute.

Une exception managee levee sous `invokeMethod` remonte cote Frida en **« system error »**. D'ou
le symptome exact : l'ability EXISTE (elle est dans `decisionView`, `abilityTargets` rend des
cibles), et le cast faute des la premiere lecture de variable.

**Mesure discriminante (les deux sens) :**

| Experience | Resultat |
|---|---|
| `thousDaemonPrince` INJECTEE + ability 1145 (config presente, portee par tyranBiovore) | cast OK, spawn `tyranSmnSporeMine` |
| `blackForgefiend` CAPTUREE (zero injection) + abilities 1208/1209 (configs absentes) | « system error » |
| `ultraTitus` CAPTUREE + passif 1525 ou 1490 (configs absentes) | echec du deploiement PRE-START |

La faute suit l'ABILITY, jamais l'entree de catalogue. Corollaire : un passif dont la config
manque fait echouer le **deploiement** (le triggered lit ses variables a la creation) — ce qui se
lisait a tort comme « ce porteur ne peut pas spawner ».

**La cause SYMETRIQUE, decouverte a la migration de build (#254)** : une config *presente mais
PERIMEE*. Le seed BC est capture sur UN build, `gameconfig.py` lit le fichier VIVANT ; une MAJ qui
AJOUTE une variable/constante a une ability laisse la capture en arriere, et le meme
`GetStringConstant` leve sur la cle absente. Mesure : `ShockAssault` (passif d'`ultraInceptorSgt`)
gagne `unitId = ultraSmnInceptor`, et **tout** `rl_duel build` dont un roster contenait cette unite
du POOL rendait « system error » — sans la moindre injection. `_load_seed_bc` re-synthetise
desormais `BC.Abilities` depuis le gameconfig courant a chaque chargement
(`catalog_inject.refresh_ability_configs`). Detail :
`docs/rl/case-254-build-migration-blockers.md`.

## 3. Le mecanisme

`catalog_inject.augment(seed_bc, ids)` rend une COPIE du seed BC ou :

1. `Units[]` recoit l'entree `UnitConfiguration` de chaque id manquant, mirror de
   `BattleConfigBuilder$$GetUnitConfiguration` ;
2. `Abilities.ActiveAbilities` / `.PassiveAbilities` recoivent les configs manquantes des abilities
   ET des traits de ces unites, mirror des entrees `AbilityConfiguration`.

Le seed BC partage n'est **jamais** modifie : `rl_duel build --seed-bc <fichier>` et
`rl_collect_batch._load_seed_bc(path)` acceptent deja un seed custom.

### Derivations (toutes mesurees sur le catalogue capture, 0 divergence)

Entree `UnitConfiguration` <- `units.{lineup,npc,summons}[id]` + `units.damageProfiles` :

| Champ BC | Source |
|---|---|
| `Id` / `VisualId` / `QuestUnitId` | id ; `visualId` / `questUnitId` si presents |
| `Faction` / `Subfaction` | `FactionId` / `Subfaction` |
| `Traits` | `[GrandAllianceId] + [Subfaction si presente] + traits` (+ `"NPC"` si kind npc) |
| `Movement` / `NumberOfMembers` | `Movement` / `nrOfMembers` (defauts 0 / 1) |
| `Weapons[]` | `weapons[]` x `damageProfiles` ; `IsMelee = Range is None` |
| `ActiveAbilities[]` | noms -> `IdunBattle.Entities.Enum.ActiveAbilityType` |
| `PassiveAbilities[]` | noms -> `IdunBattle.Entities.Enum.TriggeredAbilityType` |
| `ConfigId` | `{PureId, Rarity: null, Level: <suffixe ":N"> ou null, IsBorrowed: false, IsPvpOpponent: false}` |
| `Health`/`Damage`/`Armor`/`FixedArmor`/`Crit*`/`Block*` | **laisses a 0** : `buildNormalizedBC` les recalcule par `IStatsFormula.StatsUsingProgressionIndexFor` |
| `Affinity` / `Class` / `DamageType` / `ArmorType` / `Range` / `Shield` | constantes du catalogue capture (5 = `UnitAffinity.None`, 4 = `UnitClass.NONE`, 0, 0, 0, 0) |
| `AbilityVariablesMultiplierPercentage` | mirror de `IdunMetaLogic.UserProgress.UnitConfigUtil$$GetAbilityVariablesMultiplierPercentageForProgressionIndex` : la fonction indexe la liste heros (unitsConfig+0x80) ou MoW (+0x88, branche IsMachineOfWar) et rend le champ +0x24 ; cote gameconfig ce sont `units.heroProgressionSteps[MoW].abilityStatMultiplierPct`. On prend le premier palier couvrant la cible (rank 17 -> 180, exactement la valeur des heros rank-17 du seed BC) |
| `TertiaryAbility*` | `null` / 0 / 100 — la tertiaire est l'ability du RELIQUE equipe (etat joueur), null sur 171 des 175 entrees capturees |
| `Power` | 0 — sans effet observable (cf. controle §4) |

Entree `AbilityConfiguration` <- `units.abilities[nom]` :

| Champ BC | Source |
|---|---|
| `Variables` | `variables`, valeurs en CHAINES (cles trimmees : 2 cles a espace parasite sur 325) |
| `Constants` | `constants`, valeurs en CHAINES |
| `AttackRangeType` | `attackRangeType` -> `IdunBattle.Entities.Enum.AttackRangeType` (absent = 0) |
| `VariablesAffectedByUnitRarityMultiplier` | `variablesAffectedByRarityBonus` : NOMS -> ids `IdunBattle.Configuration.AbilityVariableType` |
| `TutorialAbilityBehaviours` | `{}` (vide sur les 325 entrees) |

Regle de peuplement, mesuree : `ActiveAbilities` == exactement l'union des `activeAbilities` des
unites du catalogue (131/131, 0 manquant 0 en trop) ; `PassiveAbilities` == union des
`passiveAbilities` + les traits qui ont une entree `units.abilities`. Les traits **marqueurs**
(Hero, MachineOfWar, Mechanical, Resilient, Flying, …) n'ont de config nulle part — 30 des 54
traits portes par les 175 unites capturees sont dans ce cas : leur absence est la norme.

### Ids d'ability : `data/symbols/<build>/frida/enums.tsv`, jamais `ability-names.ts`

`frida/hooks/data/ability-names.ts` est **stale** sur `gqfc5mff6c` : il ignore
`ReanimationBeam=1223` et `NanoscarabRepairProtocols=1224` — les deux abilities de
`necroReanimator`. S'en servir produit un porteur SANS ability, silencieusement. La table
`enums.tsv` est estampillee per-build (`#!il2cpp-provenance … build=<hash>`) et versionnee : c'est
la seule source acceptable. `catalog_inject` la lit et **leve** si un nom n'y est pas.

## 4. Validation

**Offline — la synthese reproduit le catalogue du jeu.** `python catalog_inject.py --validate`
re-synthetise les 175 entrees `Units` et les 277 configs d'ability du seed BC capture et diffe
champ a champ : **0 divergence**. Une entree injectee n'est donc pas une approximation ecrite a la
main : c'est la meme fonction qui, appliquee a une unite dont le JEU a construit l'entree, redonne
l'entree du jeu.

**Controle live — indiscernabilite.** Pour `genesBiophagus` (deja au catalogue), remplacer
l'entree capturee par l'entree synthetisee donne un profil live IDENTIQUE : `attack=3614`,
`health=5522`, `fixedArmor=1205`, `movement=3`, AbilityStates (1166 AberrantHypermorph et 1167
Heal_TwistedScience, level 50 / mult 180), et l'effet de trait `Ambush_CanResurrect` (1358) pose
au deploiement. Ce controle couvre aussi `Power=0` et les constantes Affinity/Class.

**Les trois etats, live (session 78, build `gqfc5mff6c`) :**

| Etat | Resultat |
|---|---|
| (1) PRESENT | **17/17** au pool spawnable, MoW comprises (`darkaStormSpeeder`, `necroReanimator`, `thousDaemonPrince` en pool MoW) |
| (2) SPAWNE | 4 Votann + 2 MoW #92 + 4 temoins hors-famille, vivants avec kit complet |
| (3) AGIT | 10 porteurs castent avec effet observable (detail ci-dessous) |

```
thousDaemonPrince  1208 AetherStride    -> spawn thousSmnDaemonPrince (effets 1034 Daemon_ExtraBlock,
                                          1026 BigTarget_AdjacentEffect)
                   1209 InfernalCannon  -> effet de TUILE 5 (Fire) remaining=4 sur la tuile ennemie
necroReanimator    1224 NanoscarabRepairProtocols -> cible necroDestroyer hp 8032 -> 10691,
                                          effets 1545/1546 (NanoscarabRepairProtocols[_ExtraHp])
                   1223 ReanimationBeam -> (allie mort present) +1563 hp sur necroWarden + effet
                                          1547 ReanimationBeam_Revive remaining=2 sur la MoW
votanMemnyr        1219 IronkinSteeljack -> spawn du Steeljack (hp 8973, atk 2992, fixedArmor 2194),
                                          attaque a l'apparition (-3952), effets 1538 PurgeResponse /
                                          1026 BigTarget / 1009 Overwatch
votanBeserk        1221 AugmentedAssault -> -4903 hp + effet 1541 AugmentedAssault_ReduceArmor ;
                                          l'attaque normale suivante TUE la cible
votanIronmaster    1206 GravitonRifle    -> -2674 hp + Stunned (1162/1165/1166/1167) sur la cible
votanUthar         1207 AncestralFortune -> effets 1488 GrimEfficiency_ExtraPierce + stance
                                          PrioritisedEfficiency (1480/1483)
adeptCelestine     1025 SkyStrike        -> -3740 hp
bloodTerminator    1230 SavageEchoes     -> cible TUEE (9537 -> 0)
tauFarsight        1210 ExemplarOfTheMontka -> effet 1498 ; attaque normale -6125 hp
necroChronomancer  1226 Chronometron     -> effets 1065 Pinned + 1550 Chronometron_ExtraDamage
```

Les passifs materialisent leurs effets au deploiement — `PredictiveGuidance_Melee/Ranged/ExtraHits`
(1535-1537), `GrimEfficiency_ExtraArmor` (1487), `GravitonRifle_ExtraPierce` (1484),
`TimesplinterMantle_DamageReduction` (1551), `TerminatorArmour_ReduceDmg` (1147) — preuve que la
config de passif injectee est consommee.

## 5. `votanSmnSteeljack` — resolu, et pourquoi il paraissait bloque

Verdict anterieur (case-220 §6.10) : « le cast natif de 1219 leve un system error =
`FindFirstObjectByType` (query scene Unity absente en runner headless) ». **Refute.** Le cast
fonctionne en headless. Deux causes cumulees, aucune liee a la scene Unity :

1. **Config d'ability manquante** — `IronkinSteeljack` n'est pas dans le `BC.Abilities` capture
   (aucune unite du seed BC ne la porte) : premiere lecture de variable -> exception -> « system
   error ». Injecter la config supprime la faute.
2. **Tuile-cible non adjacente** — `abilityTargets` rend TOUT l'ensemble castable (25 tuiles),
   alors que le behaviour de summon exige une tuile **adjacente au caster**. Prendre `targets[0]`
   donne `ok:true` / `mutated:false` / `spawned:0` : un faux negatif parfait, qui se lit
   « le summon ne marche pas en headless ». Le controle est net : `AberrantHypermorph` (1166),
   ability live-validee, produit exactement le meme `spawned:0` sur une tuile non adjacente.

Avec les deux corriges, le summon apparait : `hp_max=8973`, `atk=2992`, `fixedArmor=2194`,
attaque a l'apparition — exactement les valeurs que le port offline assertait.

**Piege de nommage a retenir** : le summon apparait sous le `visualId` **`votanNpc2Steeljack`**
(champ `visualId` de l'entree summon du gameconfig), pas `votanSmnSteeljack`. Un test qui cherche
l'id de l'entree ne le trouve jamais.

## 5bis. La LIMITE de l'injection, et la recette qui prend le relais (mesuree #27-4c, 2026-07-30)

**`catalog_inject` complete le CATALOGUE ; il ne rend pas tout SPAWNABLE.** Ce sont deux etages, et
c'est le SECOND qui refuse les summons et les npc :

```
seed BC + catalog_inject   ->  BC.Units / BC.Abilities completes      (etage 1 : le catalogue)
buildNormalizedBC          ->  `normalized` = le POOL de --p-units     (etage 2 : la formule de stats)
```

L'etage 2 appelle `IStatsFormula.StatsUsingProgressionIndexFor` par unite ; **une unite sans table de
progression de heros y leve**, et le RPC la range dans `skipped` avec `reason = "v2 patch: system
error"`. Mesure du 2026-07-30 sur `rnca9r7q6c` : `tauSmnStealthSuit` (summon) et `tauNpc5StealthSuit`
(npc) entrent bien dans `BC.Units` (175 -> 176 entrees) et sont malgre tout **absents du pool**, aux
cotes des 70 entrees `*Npc*:<n>` deja presentes dans la capture. Leurs `Health`/`Damage`/`Armor`
restent a 0 — l'entree synthetisee est structurellement complete, mais sans stats.

Le diagnostic se lit en UNE commande, et il vaut mieux que de deviner :

```python
out = R._rpc(sid, "buildNormalizedBC", [args], timeout=60)["result"]
[s for s in out["skipped"] if "<mon id>" in s["unitId"]]     # -> reason
```

**Ce que ca ne veut PAS dire, c'est « dossier ferme ».** L'ordre des recours, du plus fidele au moins :

1. **SUMMON avec invocateur** -> spawner l'invocateur (la voie de la gate de confrontabilite).
2. **SUMMON SANS invocateur** — verifie par balayage du gameconfig, pas suppose : chercher l'ability
   qui le declare (`units.abilities.<X>.constants.unitId`) PUIS chercher qui porte `<X>` dans
   `activeAbilities`/`passiveAbilities`. Si personne, il n'y a pas d'invocateur (cas
   `tauSmnStealthSuit` / `ATemptingTrap`).
3. **GREFFE DE L'ABILITY sur une unite DU POOL** — remplacer `ActiveAbilities` de l'entree `BC.Units`
   d'un heros spawnable par `[<abilityId>]` dans une COPIE du seed BC. **C'est une mesure, pas un
   contournement** : le natif charge le playbook PAR ABILITY
   (`PlaybookDatabase.LoadPlaybook(abilityType)`), jamais par unite — le code exerce est donc bien
   celui de l'ability visee, et le natif le PROUVE en emettant `ActiveAbilityMessage(<id>)` dans
   `aiDryRunAllUnits`. La config d'ability est deja la (`_load_seed_bc` re-synthetise `BC.Abilities`
   depuis le gameconfig courant, donc meme une ability que personne ne porte y figure).

   ```python
   bc = R._load_seed_bc(None)
   for u in bc["Units"]:
       if u["Id"] == "<hero du pool>":
           u["ActiveAbilities"] = [<abilityId>]
   Path(out).write_text(json.dumps(bc), encoding="utf-8")   # JAMAIS le seed BC partage
   ```

   Choisir le greffon avec la MEME faction et un profil d'arme compatible quand la mecanique en
   depend (#27-4c : `tauCrisis`, T'au, arme Pulse portee 2, pour 1185 `ForwardObservers`).

**Ce que la greffe NE couvre PAS**, et qu'il faut ecrire dans le rapport : les stats, traits et armes
du VRAI porteur — donc toute interaction de la mecanique avec eux. Elle est donc legitime pour un
terme qui ne lit ni stats ni traits du caster (un terme de playbook qui lit `BC.Utilities` + l'etat du
board), et NON pour une prediction de degat.

**4. CHEMIN DE STATS EXPLICITE — le recours qui rend la greffe INUTILE (#419-r1-tr12-r2).**
Le verrou n'est pas le catalogue, c'est l'etage 2 : `buildNormalizedBC` n'avait QU'UNE formule,
celle des HEROS. Le natif en a deux autres, NOMMEES, desormais mirrorees et cablees :

```bash
python rl_duel.py build --board MC1_67 --state-file <absolu>.json \
       --explicit-stats admecNpc3Electropriest:33 --p-units admecNpc3Electropriest:33
python catalog_inject.py --explicit-stats admecNpc3Electropriest:33   # le patch, hors ligne
python catalog_inject.py --explicit-stats-witness                     # le temoin, 0 divergence
```

* **NPC** -> `IdunMetaLogic.UserProgress.UnitProgression$$GetNpcStats` ->
  `idun.meta.extensions.UnitConfigExtensions$$GetStatsForLevel` = `units.npc[id].stats[]`, palier =
  suffixe `:<n>` de l'unitId (`idun.shared.UnitNamingConventions$$GetLevelFromUnitId`, **defaut 1**),
  clamp HAUT seulement. 491/491 npc portent la table. L'unite arrive avec SES stats, SES traits,
  SES armes — la greffe n'est plus necessaire.
* **SUMMON** -> `$$GetSummonStats` = les variables `summon*` de l'ability qui invoque. ⚠ Les 65
  entrees summon du seed BC portent `Health = 0`, **ecrit par le jeu** : leurs stats sont posees au
  SPAWN (`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$GetStatsToOverride`), pas au catalogue.
  Ecrire des stats sur une entree summon est donc un MONTAGE (etat post-spawn), et `explicit_stats`
  le DIT (`source = "summon-spawn"` vs `"npc"`).

Quand le porteur summon a un jumeau NPC (memes `passiveAbilities`, meme arme, meme `Movement` —
c'est le cas de `admecSmnElectropriest` / `admecNpc3Electropriest`), **prendre le NPC** : c'est le
mirror, pas le montage. Detail, temoins, contre-epreuves et limites :
`docs/rl/case-419-r1-tr12-r2-stats-npc-summon.md`.

## 5ter. La RELIQUE — un TROISIEME catalogue, et un verrou de NIVEAU (#237)

Le meme module equipe desormais une **relique** (`--equip-relic`, `equip_relic`,
`write_relic_seed_bc`). Ce n'est pas une variante de l'injection de porteur : c'est un montage a
**trois** ecritures, dont deux echouent EN SILENCE si on les oublie.

1. `BC.Units[].TertiaryAbility` = id `TriggeredAbilityType` —
   `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` ne monte l'ability que si le
   `Nullable` a une valeur (`TriggeredAbilityComponent$$TryAdd(id, state, 3)`, le `3` = hierarchie
   Tertiary). Champ nul = rien, sans erreur.
2. `BC.Abilities.PassiveAbilities[<nom>]` — **29 des 32** abilities de relique sont ABSENTES du seed
   capture (seules les 3 equipees y sont). Meme verrou et meme parade que §2 : sans la config,
   « system error » au cast.
3. `BC.Units[].TertiaryAbilityLevel >= 1` — **le verrou propre a la relique**.
   `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel` (foyer UNIQUE des
   quatre accesseurs de variable) convertit par `Idun.Shared.Level$$ToZeroBasedIndex`, qui LEVE
   `InvalidOperationException` des que `level <= 0`. Or **`synthesize` pose `TertiaryAbilityLevel =
   0`**, comme les 171 entrees sans relique du seed (0 = « verrouille », cf.
   `Idun.Shared.Level$$CreateValidOrLockedLevel`). **Pas de borne haute** : le meme foyer clampe
   (`idx >= len` -> `len - 1`).

⚠ **L'ORDRE compte.** `buildNormalizedBC` ECRASE `TertiaryAbilityLevel` a `targetAbilityLevel` (50)
**si et seulement si** `TertiaryAbility` est deja non nul — donc poser la relique APRES la
normalisation (patch du template, `--unit-stat`) laisse le niveau a 0. `rl_duel build
--equip-relic` fait les deux moities au bon moment (config avant, couple apres) et rend le niveau
EXACT ; la voie `--seed-bc` est plus simple mais donne toujours 50, clampe au dernier palier.

Detail, decompile et ventilation des trois etats : **`docs/rl/case-237-relique-forcee.md`**.

## 6. Usage

```bash
# ce qui manque au catalogue
python catalog_inject.py --missing

# les RELIQUES : abilities, ids, paliers, porteurs, config presente ou non (#237)
python catalog_inject.py --list-relics
python catalog_inject.py --relic-state      # les TROIS etats : 4 equipees / 52 sans / 9 hors catalogue
python rl_duel.py build --board MC1_67 --state-file <absolu>.json \
       --p-units ultraTitus --equip-relic "ultraTitus:RelicBoltPistol:6"

# la synthese reproduit-elle le catalogue capture ? (offline, 0 divergence attendue)
python catalog_inject.py --validate

# seed BC augmente, puis runner par la voie normale
python catalog_inject.py --units thousDaemonPrince,votanMemnyr --out <chemin absolu>.json
python rl_duel.py build --seed <s> --board MC1_67 --state-file <absolu unique>.json \
       --seed-bc <chemin absolu>.json --p-units votanMemnyr --a-units ultraTitus
python rl_duel.py build ... --seed-bc <...>.json --board C1_02 --p-mow thousDaemonPrince

# confront live des trois etats
python probe_92_catalog.py --phase present
python probe_92_catalog.py --phase control
python probe_92_catalog.py --phase act    --units votanMemnyr,votanBeserk
python probe_92_catalog.py --phase actmow --mow thousDaemonPrince
```

`--board` est obligatoire ; une MoW exige un board avec slot `MachineOfWarPosition` des deux cotes
(`C1_02` par exemple).

### Piege de mesure : `decisionView` est AVEUGLE aux effets de TUILE

`InfernalCannon` a d'abord paru caster « sans effet observable » : elle pose un effet de TUILE
(`Fire` 5, remaining 4), et seul `tileMeta` (`readEffectsByTile`) les expose — `decisionView` ne
rend que les effets d'unite et de MoW. L'empreinte du probe et du test lit donc les DEUX canaux ;
sans ca, toute ability de zone se lit comme un no-op.

## 7. Ce qui n'est PAS couvert

- **Les 7 autres unites hors catalogue** (`astarCyrus`, `darkaSternguard`, `darkaStormSpeeder`,
  `emperExultant`, `emperFlawlessBlade`, `emperLucius`, `spaceWolfPriest`) : etat (1) verifie,
  (2)/(3) non joues faute de pertinence immediate. Rien ne les distingue des 10 confrontes.
- **Le `Power` de l'entree injectee est 0** : sans effet observable sur les canaux mesures
  (stats, abilities, effets, degats). Si un jour un canal meta le consomme, il faudra le deriver
  (`powerMultiplier`, `abilityPowerCurve`, `traitPowerModifiers` sont dans le gameconfig).
- **Traits marqueurs sans config** (Hero, MachineOfWar, Mechanical, Resilient, …) : non
  synthetisables — mais leur absence est la norme, 30 des 54 traits des unites capturees sont
  dans ce cas.
