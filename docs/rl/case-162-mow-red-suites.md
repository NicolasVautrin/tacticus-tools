# Case #162 — les suites MoW rouges : DEUX defauts de HARNAIS, puis UN defaut de PORT

**Question posee** : ces rouges sont-ils un defaut de HARNAIS (les MoW ne sont pas la, rien n'est
mesure) ou un defaut de MOTEUR (elles sont la, et leur cast ne produit pas ce que le natif produit) ?

**Reponse mesuree** : **les 13 rouges etaient TOUS des defauts de HARNAIS.** Les MoW sont bel et bien
deployees et castent. Une fois le montage repare, la suite mesure enfin — et **4 vrais defauts de PORT
apparaissent, tous de la MEME cause unique**, qui explique aussi la « mesure B » contradictoire.

Les deux mesures qui se contredisaient disaient donc la verite toutes les deux : la corruption de
harnais bloque les **effets** et laisse passer le **degat** (mesure : 6180 PV identiques avec et sans).
« live=[] » (mesure A) etait une empreinte d'EFFETS vide ; « live_delta=1631 » (mesure B) un delta de PV.

---

## 1. Ventilation des 13 rouges (etat de depart)

| suite | test | cause |
|---|---|---|
| posers | `test_heavy_rail_rifle_confront_live` | HARNAIS-1 `combatSnapshot` |
| posers | `test_macro_plasma_incinerator_confront_live` | HARNAIS-1 |
| posers | `test_devastating_refrain_confront_live` | HARNAIS-1 |
| posers | `test_squig_mine_confront_live` | HARNAIS-1 **puis** PORT-1 |
| posers | `test_malleus_rocket_launcher_confront_live` | HARNAIS-1 |
| posers | `test_macro_plasma_tile_filters_live[elevation]` | HARNAIS-2 `ImportError` |
| posers | `test_macro_plasma_tile_filters_live[walkable]` | HARNAIS-2 |
| posers | `test_machine_side_branch_flips_live` | HARNAIS-1 |
| bcd | `test_twin_smart_missile_system_confront_live` | HARNAIS-1 |
| bcd | `test_plagueburst_mortar_confront_live` | HARNAIS-1 **puis** PORT-1 |
| bcd | `test_plagueburst_mortar_center_zone_live` | HARNAIS-1 **puis** PORT-1 |
| bcd | `test_daemonic_ordnance_confront_live` | HARNAIS-1 |
| bcd | `test_thrice_blessed_conflagration_confront_live` | HARNAIS-1 **puis** PORT-1 |

`test_forward_spotter_confront_live` etait deja VERT : il compte des **summons**, pas des effets — la
corruption HARNAIS-1 ne touche que la pose d'effets. C'est le premier indice qu'elle etait selective.

---

## 2. HARNAIS-1 — le RPC `combatSnapshot` CORROMPT le runner des qu'une MACHINE est presente

### Le fait

Appeler `combatSnapshot` sur un runner qui contient une entite `EntityType.Machine` (une MoW deployee)
laisse **CE runner** dans un etat ou **toute pose d'effet ulterieure est un NO-OP silencieux**.

* Aucune erreur : `applyAction` rend `ok=true`, l'action est consommee (`UnitStats_ActionsAvailable=0`).
* Les events d'ouverture sont la, ceux de pose d'effet ont disparu :
  `['HeavyRailRifle', 'HeavyRailRifle', 'HeavyRailRifle_PendingTarget', 'HeavyRailRifle_PendingAttack']`
  (15 events) devient `['HeavyRailRifle', 'HeavyRailRifle']` (7 events).
* **Le degat, lui, passe normalement** : `ThunderousAssault` inflige 6180 PV avec ET sans corruption.
* Ce n'est pas une affaire de MoW : le cast d'une **UNITE** est frappe pareil (`ThunderousAssault` ne
  pose plus `Stunned`) — il suffit qu'une MoW soit sur le plateau.

### Les contre-epreuves (ce qui NE corrompt pas)

| geste | pose d'effet apres |
|---|---|
| rien | OK |
| `decisionView` + `abilityTargets` | OK |
| `observeBattle`, `boardGraph`, `tileMeta`, `dumpRng` | OK |
| `statModSources` (meme `GetStat`, sur les Machines aussi) | OK |
| `aiPlaybookPredict` avec le **caster = la MoW** | OK |
| **`combatSnapshot`** | **CASSE** |
| meme runner **sans MoW** + `combatSnapshot` | OK |

La corruption **n'est pas reversible** : elle survit aux fins de tour (2 casts plus tard, toujours cassee).

### Ce qui reste a instruire (defaut d'OUTILLAGE, hors de ce cas)

`combatSnapshot` est le SEUL RPC fautif ; la condition est la presence d'une entite `Machine`. Les seuls
invokes qu'il est seul a faire sur une entite Machine sont, dans `frida/hooks/features/ai-step/
rpc-snapshot.ts` :

* `UnitExtensions.GetUnitPosition(machine, state)` puis
  `CachedDamagePredictionQuery.GetNormalAttackPrediction(machine, target, position)` pour chaque cible
  (`readNormalAttack`) — une MoW est **hors plateau**, sa `UnitPosition` est VIDE (`Tiles=[]`, cf.
  `rpc-predict.ts`), et la ligne Machine du snapshot rend deja
  `{"error": "aucune cible atteignable au deploiement"}` : **cet appel ne rapporte donc AUCUNE
  information** ;
* `UnitExtensions.GetStat` aux `StatPart` 0/2/3 (`statModSources` n'exerce que la part 5).

La sortie silencieuse cote natif est visible dans `IdunBattle.Operations.AddEffectOperation$$Execute` :
apres avoir resolu la definition d'effet dans l'`EffectsDatabase`, un appel d'interface sur cette
definition (slot `+0x28`) rend un booleen qui, non nul, fait `return 0` **sans rien poser ni logger**.
Identifier ce qui, dans l'etat, bascule ce predicat demande un hook — donc un reinject, hors du perimetre
de cet agent. **Piste a verifier en premier au prochain reinject** : ne pas appeler `readNormalAttack`
pour les entites `Machine` (ni les prendre comme cible de prediction) et re-jouer les deux suites sans
le contournement ci-dessous.

### La parade livree (harnais, validee live)

Deux `rl_duel build` de MEMES arguments donnent un etat **strictement identique** — mesure : payload
`combatSnapshot` egal, `decisionView` egal, memes ids d'entites, meme etat du PRNG (`dumpRng`). Le
snapshot est donc pris sur un **runner JUMEAU**, dispose aussitot, et le runner de mesure n'est jamais
snapshotte (`_twin_snapshot` dans les deux suites). Le jumeau rejoue la sequence deja jouee sur le
runner de mesure (fins de tour, 1er cast) via `replay`, sans quoi l'etat snapshotte ne serait pas celui
qu'on confronte. Son `--state-file` est DEDIE : un `build` dispose le runner enregistre dans son propre
state-file, le partager tuerait le runner de mesure.

Durcissement au passage : `_cast_live` **AVALAIT** une erreur de niveau RPC. `(r.get("actions") or
[{}])[0]` rend `{}` quand le host repond `{ok:false, error}` sans clef `actions` — donc `act.get("error")`
valait `None`, le test continuait et echouait plus loin sur une empreinte live vide, **en accusant le
port**. Il remonte desormais l'erreur.

---

## 3. HARNAIS-2 — un import prive casse par le passage de `selectors.py` au package `selectors/`

`test_macro_plasma_tile_filters_live` construit son oracle « triangle brut » avec
`_TRIANGLE_SHAPE_DIRECTIONS`, importe a plat depuis `engine.entities.selectors`. Le module est devenu un
package : le symbole PRIVE n'est pas re-exporte par `__init__.py` (seul `neighbour_at` l'est) ->
`ImportError`. L'import pointe desormais le module qui le definit,
`engine.entities.selectors.geometry`.

---

## 4. PORT-1 — le `StatsComponent` d'une MoW est ECRASE : toutes ses variables per-niveau sont lues au niveau 1

C'est le seul defaut de MOTEUR du cas, et il en explique **quatre** echecs plus la « mesure B ».

### La chaine (mesuree par `probe_162_mow_ability_level.py`, pas deduite)

1. `decisionView.mows[].abilities[]` porte bien `level`/`multiplier`, et
   `snapshot._machine_ability_state` les lit : `orksRukkatrukk` -> **(50, 140)**.
2. `_load_machines` pose donc un `StatsComponent` CORRECT sur l'entite Machine.
3. `load_state` appelle `_load_machines` **puis** `_load_stats_and_effects`. Ce dernier boucle sur
   `snapshot["units"]` **sans filtrer `entityType`** — or le RPC `combatSnapshot` **inclut** les entites
   `Machine` depuis `d9d0008` (#128 ; le « #93 » ecrit ici puis recopie dans `snapshot.py` etait FAUX
   — #93 est la tache SpiritLeech). L'en-tete de **`_load_machine_stats`** (et non de `_load_machines` : cette
   attribution-ci etait imprecise, corrigee en #174) affirme le contraire (« `combatSnapshot` n'expose
   QUE `EntityType.Unit` (son `allUnits` filtre `ty === EntityType.Unit`) ») : **l'affirmation est
   PERIMEE**, le hook teste `ty !== EntityType.Unit && ty !== EntityType.Machine`.
4. Pour la ligne Machine, `unitConfig` vaut `{"error": "visualId introuvable"}` (le registre
   `BattleQuery.GetUnitConfig` est keye par une VisualId d'UNITE) -> le bloc
   `if uc.get("abilityVariablesMultiplier") is not None:` ne s'execute pas -> le `ctx` reconstruit n'a
   **ni niveau ni multiplicateur**, et `ent.add_component(StatsComponent(ctx=ctx))` **REMPLACE** celui de
   `_load_machines`.

Mesure : `load_state` -> `ctx.active_ability_level = 0`, `ctx.ability_variables_multiplier = 100`.

### Les ecarts que ca produit — chaque chiffre confronte au live

| ability (MoW) | variable | niveau LU (0) | niveau REEL (50) | observable live |
|---|---|---|---|---|
| `SquigMine` (1201) | `nrOfTiles` | 2 | 4 | 5 tuiles minees = 1 ciblee + 4 |
| `PlagueburstMortar` (1169) | `nrOfTiles` | 3 | 7 | zone au CENTRE = 7 tuiles ; en COIN = 4 = `1 + min(6, 3 voisines)` |
| `ThriceBlessedConflagration` (1187) | `nrOfRounds` | 1 | 5 | `remaining = 10` = `TurnsFromRounds(5)` |

La « mesure B » du dossier (`test_entropy_cannons...` : `off_delta=20` contre `live_delta=1631`) est **le
meme bug** : `minDmg`/`maxDmg` sont des tables per-niveau, lues a l'index 0 au lieu de 49.

### Le correctif — LIVRE EN #174

Voir **`case-174-mow-level-index.md`** : correctif applique, INDEX prouve au decompile (le natif
indexe a `Level.ToZeroBasedIndex() = level - 1`, pas « au niveau »), et rayon d'action MESURE — il
etait plus large que ce dossier ne le disait (**5 tests de plus** dans `test_mow_targeting_predicate_live`
et `test_hailstrike_phase2_live`, **2 de plus** dans `test_mow_caster_load_live`).

Deux imprecisions de ce dossier-ci, corrigees la-bas : l'en-tete perime est celui de
**`_load_machine_stats`** (pas `_load_machines`), et le `StatsComponent` de la MoW n'etait pas
« REMPLACE » mais **PRE-EMPTE** (`_load_machine_stats` ne pose rien si un `StatsComponent` existe deja,
et il tourne APRES la boucle).

---

## 5. Etat des suites apres ce cas

| suite | avant | apres #162 | apres #174 |
|---|---|---|---|
| `test_mow_effect_posers_live` | 0/8 | **7/8** (reste `squig_mine`, PORT-1) | **8/8** |
| `test_mow_groups_bcd_live` | 1/7 (+1 skip) | **3/7** (+1 skip) — les 3 restants sont PORT-1 | **6/7** (+1 skip) |

Le skip de `test_twin_smart_missile_system_marked_target_is_attacked_live` est celui deja documente en
#90 §6.4 residu 4 (le marquage n'a pas survecu jusqu'au 2e cast) — inchange, et **pas** un skip de
harnais.

Migration au passage : les state-files des deux suites vivaient sous `data/` (VERSIONNE) et laissaient
4 entrees `??` dans `git status`. Ils passent sous `logs/`, comme la `conftest` l'avait deja fait.

## 6. Reproduire

```
python probe_162_mow_cast_live.py --mow tauBroadside --ability 1160        # la corruption combatSnapshot
python probe_162_mow_ability_level.py --mow orksRukkatrukk --ability SquigMine --var nrOfTiles
```
