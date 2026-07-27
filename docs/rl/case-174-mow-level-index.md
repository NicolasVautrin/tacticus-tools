# Case #174 — les MoW lisaient TOUTES leurs variables au NIVEAU 0

**Question posee (binaire)** : une MoW chargee via `load_state` lit-elle ses variables d'ability a
son NIVEAU REEL, comme le natif ?

**Reponse** : non — elle les lisait a l'**index 0**. Corrige. Et l'index correct n'est pas « le
niveau » : c'est **`level - 1`**, prouve au decompile puis PINCE par un observable live sur une
table strictement croissante.

---

## 1. Le defaut

`_load_stats_and_effects` (`engine/runner/snapshot.py`) bouclait sur `combatSnapshot.units` **sans
filtrer `entityType`**. Or le capteur (`frida/hooks/features/ai-step/rpc-snapshot.ts`) teste
`ty !== EntityType.Unit && ty !== EntityType.Machine` : il remonte les DEUX types depuis `d9d0008`
(#128 « lot ATELIER VIDE »), et
etiquette chaque ligne d'un champ `entityType`.

Pour une ligne Machine, `unitConfig` vaut `{"error": "visualId introuvable"}`. **La cause exacte
n'est pas celle qui etait ecrite** : ce n'est pas que « `BattleQuery.GetUnitConfig` est keye par une
VisualId d'unite » — le capteur n'appelle jamais `GetUnitConfig` pour une MoW. `readUnitConfig`
cherche la VisualId sur un `UnitComponent` ; l'entite Machine porte un `MachineComponent`. Les deux
sont des **freres** derivant de `IdunBattle.Entities.Components.BaseUnitComponent$$.ctor`
(`classes.tsv` : `MachineComponent` 128 o et `UnitComponent` 432 o, meme parent), et la comparaison
du capteur est une egalite de classe -> elle echoue avant tout appel. Ce que le registre repondrait
n'est **pas mesure** ; ne pas l'invoquer comme cause.

Le `ctx` bati depuis cette ligne n'a donc **ni niveau, ni multiplicateur, ni VisualId, ni traits** —
et il **PRE-EMPTE** `_load_machine_stats`, qui ne pose rien si un `StatsComponent` existe deja et qui
tourne APRES la boucle. (Le dossier #162 disait « REMPLACE » ; le mecanisme exact est la pre-emption.)

Mesure sur `tyranBiovore` (build `gqfc5mff6c`, avant correctif) :

    ctx.active_ability_level = 0   ctx.ability_variables_multiplier = 100
    ctx.visual_id = None           ctx.traits = []
    (canal natif : level = 50, multiplier = 150, visualId = "tyranBiovore")

## 2. L'INDEX — prouve, pas ajuste

Le natif n'indexe pas « au niveau ». Chaine, decompilee sur `gqfc5mff6c` :

    IdunBattle.Entities.Formulas.ConfigAmount$$Calculate
      -> IdunBattle.Entities.Formulas.ConfigAmount$$GetAbilityState
           -> IdunBattle.Entities.UnitExtensions$$GetAbilityState (entite, abilityType)
                -> IdunBattle.Entities.Components.ActiveAbility$$get_AbilityState
      -> IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(cfg, varType, &state)
           -> IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel

et dans cette derniere, litteralement :

    Dictionary.TryGetValue(cfg.Variables, variableType, &arr)         # arr = string[] per-niveau
    idx = Idun.Shared.Level$$ToZeroBasedIndex(&abilityState)          # = Level - 1
    idx = System.Math.Max(0, idx)
    idx = (idx < arr.Length) ? idx : arr.Length - 1                   # clamp haut
    valeur = int.Parse(arr[idx].Split(',')[k])
    si variableType est dans cfg.VariablesAffectedByUnitRarityMultiplier :
        valeur = Fix64.Round(Fix64(abilityState.VariableMultiplierPercentage) / 100 * valeur)

`Idun.Shared.Level$$ToZeroBasedIndex` rend `*param_1 - 1` **et LEVE
`System.InvalidOperationException` si `*param_1 <= 0`** : un niveau 0 n'existe pas nativement. Le
`(0, 100)` de `_machine_ability_state` est donc une valeur de repli PORT, jamais un etat natif.

`AbilityState` fait 12 octets, `Level`@+0 / `VariableMultiplierPercentage`@+4 (`GetVariableForLevel`
recopie `*param_3` sur 8 o + `*(param_3+1)` sur 4 o, et `TryGetVariableArrayForLevel` lit le
multiplicateur a `state + 4`) — exactement ce que `readAbilityState` expose.

**Niveau natif = 50, par DEUX canaux RPC independants** qui lisent tous deux
`ActiveAbility.get_AbilityState` :

| canal | `deathCrawler` | `orksRukkatrukk` | `tyranBiovore` |
|---|---|---|---|
| `decisionView.mows[].abilities[].level` / `.multiplier` | 50 / 145 | 50 / 140 | 50 / 150 |
| `combatSnapshot.units[].abilityStates[].level` / `.multiplier` | 50 / 145 | 50 / 140 | 50 / 150 |

=> **index = 49**.

### Pourquoi « les 4 tests passent » ne prouvait PAS l'index

`SquigMine.nrOfTiles` vaut 4 sur **30 index differents** (table plate `[2×17, 3×18, 4×30]`) : la
faire passer ne discrimine rien. Il faut une table **strictement croissante** :

| ability | variable | table[0] | table[49] | mult | valeur portee = live |
|---|---|---|---|---|---|
| `SporeMineLauncher` | `summonHp` | 20 | 1109 | 150 | **1664** (index 0 rendrait 30) |
| `EntropyCannons` | `minDmg` | 28 | 1551 | 145 | **2249** (index 0 rendrait 28) |

Sur `summonHp`, l'observable live est les **PV de la mine invoquee**, non aleatoire : la valeur
live PINCE l'index. Mesure (probe de generalisation, 3 couples board/seed neufs) :

    [MC1_67/777]   level=50 mult=150 -> idx=49 table[49]=1109 resolu=1664 | LIVE hp=1664
    [C4_09/999]    idem
    [C3_01/31337]  idem

## 3. Le correctif

`engine/runner/snapshot.py` :

* `_load_stats_and_effects` : `continue` sur `su["entityType"] == 6` (`EntityType.Machine`,
  `frida/hooks/game/match-state.ts`). Les EFFETS de MoW continuent d'entrer dans le seed
  `EffectsState` : ils viennent de `decisionView.mows[].effects`, injectes dans `effects_by_id`
  AVANT la boucle — chemin independant de la ligne sautee.
* `_load_machine_stats` : consomme desormais la ligne Machine du snapshot pour les **stats
  resolues**, et **ecrase son `unitConfig`** par l'`AbilityState` per-ability. Mesure sur trois MoW :
  les 19 stats valent **0**, `statDelta={}`, `shields=[]`, `healthMax=0`, `normalAttack` en erreur —
  donc c'est un no-op AUJOURD'HUI (cohérent avec gameconfig `stats={Health:0,Damage:0,FixedArmor:0}`,
  `weapons=[]`). L'interet est de ne plus jeter le canal : une stat-modification posee sur une MoW
  en cours de combat arrivera par `statDelta` et sera attribuee comme pour une unite.
* `_load_feet` (#R30) **n'est pas touche** : il lit `observeBattle`, ou une MoW n'a **aucune ligne**
  (verifie : `observeBattle lignes pour la MoW = 0`, la projection marche `UnitFoot -> Tile` et une
  MoW est hors-plateau). Les suites multi-hex sont vertes avant ET apres.

Effet de bord VOULU du correctif : la MoW recupere aussi son `visual_id` et ses `traits`
(`['MachineOfWar']`), que la boucle unites lui retirait (`vis_by_id` ne contient que
`decisionView.units`).

## 4. Enonces PERIMES corriges (meme famille que #170)

| ou | ce qui etait ecrit | etat reel |
|---|---|---|
| `_load_machine_stats` (en-tete) | « `combatSnapshot` n'expose QUE `EntityType.Unit` » | FAUX depuis `d9d0008` |
| `_load_machine_stats` (residu) | « non captable tant que `combatSnapshot`/`statModSources` filtrent `EntityType.Unit` » | les DEUX incluent `Machine` depuis `d9d0008` |
| `_machine_ability_state` | « pas d'equivalent `GetUnitConfig` (la cle du registre est une VisualId d'unite) » | le capteur ne trouve pas de `UnitComponent` et n'appelle jamais `GetUnitConfig` |
| `blacklegion.hades_autocannons_tree` | « `combatSnapshot` filtre `EntityType.Unit` -> CritChance de MoW non captable » | captable, et MESUREE a 0 |
| `case-mow-offboard-cast.md` §8 | residu « stats resolues de MoW non captables » + spec du hook a faire | le hook a ete fait (`d9d0008`) ; residu LEVE — la « consequence non anticipee » N7 qui y etait notee OUVERTE est ce cas-ci, donc FERMEE |
| *ce dossier, 1re redaction* | « depuis **#93** » (recopie de `case-162` et du commentaire du hook) | **FAUX** : #93 = tache SpiritLeech. Le filtre vient de `d9d0008` (#128), tranche par `git log -S "EntityType.Machine" -- frida/hooks/features/ai-step/rpc-snapshot.ts`. Corrige au rebase, sur arbitrage du conflit avec la PR #154 |
| `case-mow-targeting-predicates.md` | idem, par renvoi | idem |
| `case-162-mow-red-suites.md` §4 | en-tete perime attribue a `_load_machines` ; « REMPLACE » | c'est `_load_machine_stats` ; et c'est une PRE-EMPTION |

## 5. Rayon d'action — MESURE, pas suppose

#162 ecrivait « toute suite chargeant un etat MoW via `load_state` herite du bug ». Inventaire reel :
**12** fichiers de test embarquent une MoW, dont **10** appellent `load_state`. Confrontation
avant/apres (meme session, correctif stashe puis restaure) :

| suite | avant | apres | verdict |
|---|---|---|---|
| `test_mow_caster_load_live` | 3F / 3P | **7P** | 2 rouges #174 + 1 rouge HARNAIS-1 (repare ici) ; +1 garde d'index |
| `test_mow_targeting_predicate_live` | 5F | **vert** | 5 rouges #174, dont `test_entropy_cannons_...` (`off_delta=20` vs `live_delta=1631`, la « mesure B » de #162) |
| `test_mow_groups_bcd_live` | 3F / 3P / 1s | **6P / 1s** | 3 rouges #174 (plagueburst ×2, thrice_blessed) |
| `test_hailstrike_phase2_live` | 2F | **vert** | 2 rouges #174 |
| `test_mow_effect_posers_live` | 1F / 7P | **8P** | 1 rouge #174 (squig_mine) |
| `test_spore_mine_launcher_live` | vert | vert | INCHANGE |
| `test_load_state_tile_effects_live` | vert | vert | INCHANGE |
| `test_targeting_masks_live` | vert | vert | INCHANGE |
| `test_multihex_dutyeternal_live` (7P) | vert | vert | INCHANGE — garde R30 |
| `test_storm_speeder_live` | 2F | 2F | **PRE-EXISTANT**, signature HARNAIS-1, hors #174 |
| `test_thrice_blessed_decision_live`, `test_catalog_inject_live` | vert | vert | pas de `load_state` |

**Total : 14 tests passent de rouge a vert** (11 par le correctif moteur, 1 par la garde ajoutee,
2 par la reparation de harnais). Le dossier #162 n'en annoncait que 4.

### Trois « ecarts de magnitude inexpliques » distincts, UNE cause

Le point le plus important du cas. Chacun avait ete inventorie separement, avec un sous-systeme
suspect DIFFERENT :

| symptome | ou il etait classe | sous-systeme suspecte | cause reelle |
|---|---|---|---|
| `EntropyCannons` : `off_delta=20` vs `live_delta=1631` | `case-162` « mesure B » | inexplique | `minDmg[0]` au lieu de `minDmg[49]` |
| `Hailstrike` : live **2700** hors des bornes portees **[1688, 2532]** | residu **N6**, `port-residuals-inventory` §4.a, **rang 1 du dispatch** | « etage percage », `engine/runner/abilities/darkangels.py` | idem — le porteur `darkaStormSpeeder` est une **MoW** |
| `nrOfTiles` 2/3 au lieu de 4/7, `nrOfRounds` 1 au lieu de 5 | residu **N7** | correctement identifie | idem |

**N6 est ferme par ce cas sans une seule ligne touchee dans `darkangels.py`.** Il etait decrit comme
« le dernier test de garde ROUGE, RE-REPRODUIT pour la 3e journee consecutive, chiffres inchanges
malgre les 50 insertions de `darkangels.py` » — l'invariance des chiffres a travers les modifications
de `darkangels.py` etait justement l'indice que la cause n'y etait pas.

**Regle a retenir : un ecart de magnitude sur un porteur MoW doit faire suspecter le NIVEAU LU avant
l'etage de calcul.** Le niveau est un facteur commun a toutes les variables du kit ; un etage de
calcul, lui, n'affecterait qu'une famille.

## 6. Harnais repare au passage

`test_mow_caster_load_live` prenait son `combatSnapshot` sur le runner de MESURE. Or ce RPC, sur un
runner contenant une entite Machine, rend toute pose d'effet ulterieure muette (HARNAIS-1, #162 §2 —
degats et spawns passent, c'est pourquoi seul `test_effect_posed_on_mow_is_loaded` en souffrait). La
parade jumelle (`_twin_snapshot`) etait en place dans les deux autres suites MoW ; elle manquait ici.
Le runner **sans** MoW garde le snapshot direct (contre-epreuve #162 : la corruption exige une Machine).

State-files migres de `data/` (VERSIONNE) vers `logs/` dans `test_mow_caster_load_live`,
`test_mow_targeting_predicate_live`, `test_spore_mine_launcher_live`.

## 7. Ce qui n'est PAS couvert

* `test_storm_speeder_live` (2 tests) reste ROUGE — pre-existant, HARNAIS-1 : la suite ne prend pas
  son snapshot sur un jumeau. La cause NATIVE de HARNAIS-1 (`AddEffectOperation$$Execute` sort sur un
  appel d'interface `+0x28` de la definition d'effet) reste non identifiee : elle demande un hook,
  donc un reinject.
* Une stat-modification REELLEMENT posee sur une MoW en cours de combat n'a pas ete produite : le
  nouveau chemin la capterait (`statDelta`), mais ce n'est pas confronte.
* La ligne Machine porte `shields` — vide sur les trois MoW mesurees, donc `_load_machine_stats` ne
  pose pas de `ShieldComponent`. Non porte faute d'observable.
* Trois autres suites ecrivent encore leurs state-files dans `data/` :
  `test_alpha_warrior_live`, `test_harbinger_of_destruction_live`, `test_martial_apotheosis_live`
  (hors perimetre de ce cas).

## 8. Reproduire

```
python probe_174_mow_level_index.py --mow deathCrawler --ability EntropyCannons --var minDmg
python probe_174_mow_level_generalize.py            # MC1_67/777, C4_09/999, C3_01/31337
python probe_162_mow_ability_level.py --mow orksRukkatrukk --ability SquigMine --var nrOfTiles
python -m pytest tests/engine/runner/test_mow_caster_load_live.py
```
