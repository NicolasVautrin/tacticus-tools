# #380 — combien de fixtures ont mesuré du nominal en croyant mesurer leur régime ?

Build lu : `rnca9r7q6c`. Suite de #375 (`case-375-capteur-triggered-muet.md` §2), dont la parade
(sidecar `<seed-bc>.pins.json`) est **opt-in** — donc sans effet sur les autres fixtures.

## 0. La question binaire

> `refresh_ability_configs` écrasait en silence tout patch de seed BC. **Combien d'AUTRES fixtures
> sont dans ce cas, et laquelle a rendu un verdict sur du nominal ?**

**Réponse mesurée : zéro sur l'axe VALEUR, UNE sur l'axe ABSENCE** — un axe que #375 n'avait pas
nommé et qu'aucun balayage statique ne peut voir.

## 1. Ce que `_load_seed_bc` écrase, ce qu'il ne touche pas (lu au code)

| # | surface | mécanisme | épinglable |
|---|---|---|---|
| 1 | `BC.Abilities.{Active,Passive}Abilities[<nom>]` **en entier** | `target[name] = synthesize_ability(name)` pour tout nom connu du gameconfig | **oui** — `pinnedAbilityConfigs` (#375/#396) |
| 2 | `BC.Utilities` **en entier** | `refresh_ai_utilities` : `bc["Utilities"] = new` | **NON — aucun mécanisme** |
| 3 | l'**ABSENCE** d'une config réclamée par `BC.Units` | 2ᵉ boucle : `_ability_names(u["Id"])` (gameconfig) → pose la config manquante | **oui depuis ce lot** — `withheldAbilityConfigs` |

**Hors champ, donc SURVIT** : tout `BC.Units[*]` (`TertiaryAbility`, `TertiaryAbilityLevel`,
`ActiveAbilities`, `PassiveAbilities`, stats, `Traits`), `BC.Player`, `BC.Board`, et les entrées de
`BC.Abilities` sans pendant `units.abilities` (48 sur 325, configs internes moteur : `continue`).

**L'ORDRE décide de tout.** Le rattrapage a lieu **dans** `_load_seed_bc` :
patch **en mémoire** (`bc = _load_seed_bc(None)` puis patch puis `_normalize_and_extract_pool`) ⇒
postérieur ⇒ **survit**. Patch **sur disque** (patch, écriture, puis `--seed-bc <f>`) ⇒ antérieur ⇒
**écrasé** s'il tombe dans le tableau ci-dessus.

## 2. L'inventaire

Balayage : `python scripts/python/probe_380_seed_bc_patch_survival.py` — **75 modules** de
`scripts/python/**` (probes ET tests) touchent un seed BC ; **69** n'écrivent que hors champ.
La colonne « écrasée » n'est pas déduite du balayage : elle est **mesurée** (`--measure` produit
réellement chaque fixture offline et diffe sa sortie).

| fixture | ce qu'elle patche | dans le champ ? | écrasée | verdict à rejouer |
|---|---|---|---|---|
| `probe_369.build_fixture` → `write_variable_patched_seed_bc` | `PassiveAbilities/LightImUp.Variables.{minDmg,maxDmg}[49]` | **oui** (surface 1) | **NON depuis #396** (épinglée) — OUI avant | **non** — rejoué et vert dans #375 §5 |
| **`probe_226_seed_bc_ability_configs` bras A `clone`** | **ABSENCE** de `ActiveAbilities/SavageEchoes` + `PassiveAbilities/RedRampage` | **oui** (surface 3) | **OUI** | **non pour le verdict, OUI pour le probe** — cf. §3 |
| `probe_226` bras B `clone-cfg` / C `inject` | configs = `synthesize_ability` | oui mais **idempotent** | non | non |
| `probe_353.build_grafted_seed_bc` | `ActiveAbilities/RammingSpeed` = `synthesize_ability` ; `Units[].ActiveAbilities` | idempotent / hors champ | non | non |
| `catalog_inject.write_augmented_seed_bc` + CLI `--units/--out` (≈ 30 appelants) | entrée `Units[]` + configs `synthesize_ability` | hors champ / idempotent | non | non |
| `write_relic_seed_bc` / `equip_relic` (#237) | `Units[].TertiaryAbility{,Level}` + config passive synthétisée | hors champ / idempotent | non | non — l'écraseur de `TertiaryAbilityLevel` est `buildNormalizedBC`, déjà documenté par #237 |
| `write_augmented_seed_bc(restrict_abilities=)` | `Units[].{Active,Passive}Abilities` | hors champ | non | non |
| greffes d'ability sur `Units[]` — `probe_343`, `probe_350r3`, `probe_368`, `probe_302_3`, `probe_27_4c/f/g`, `probe_317` | `Units[].{Active,Passive}Abilities` | hors champ | non | non |
| `probe_27_r1.ensure_seed_bcs` (`SEED_BC_NP`) | `Units[].PassiveAbilities = []` | hors champ | non | non |
| munitions MoW — `probe_254_mow_ammo`, `probe_r14._ammo_bc`, `probe_mow_ammo_gauge` | `BC.Player.Players[].MachineOfWarAmmo` | hors champ | non | non |
| *(toute fixture patchant `BC.Utilities`)* | poids d'utilité IA | **oui** (surface 2, **sans épingle**) | — | **0 fixture aujourd'hui : piège armé, sans victime** |

**Ligne de base des re-ajouts** (bruit vu par *toute* fixture, à soustraire pour lire le signal) :
`PassiveAbilities/MyWillBeDoneOverlord`, gagnée par `necroOverlord` à la migration de build.

## 3. Le seul cas trouvé : `probe_226`, bras A

Son bras A écrit un seed BC **sans aucune config d'ability** — c'est *le point* du montage (#226 :
la config manquante, pas le rang, cause le « system error »). La 2ᵉ boucle du rattrapage la
**repose**, en silence, parce qu'une entrée `Units` la réclame au gameconfig.

Mesuré live (MC1_67 / seed 777, `bloodTerminator` / `SavageEchoes` 1230) :

| bras | avant ce lot | après ce lot |
|---|---|---|
| A `clone` (sans config) | `ok=True errors=[]` — **indiscernable des témoins** | `ok=False errors=['system error']` |
| B `clone-cfg` | `ok=True hits=[3825, 3598, 3975, 3445]` | idem |
| C `inject` | idem | idem |

⇒ un re-jeu se serait lu comme une **réfutation** de #226. **Le verdict #226 reste juste** : il a été
mesuré le 2026-07-29 à **00h38**, le rattrapage #254 a été posé à **19h17 le même jour** — 18 h plus
tard. C'est la *reproductibilité* qui était perdue, pas la conclusion.

**Parade, symétrique de l'épingle** : clé `withheldAbilityConfigs` dans le **même** sidecar, opt-in
et nommée, et qui **lève** si elle ne retient rien (la config est en fait présente) — pendant exact
de l'épingle orpheline. `refresh_ability_configs(bc, skip=, withhold=)`. Le chemin par défaut est
**inchangé** : le filet #226 continue de couvrir tout le reste du BC.

## 4. Le recenseur — et pourquoi il mord

`scripts/python/probe_380_seed_bc_patch_survival.py`, trois étages :

1. **`--scan`** — AST, pas grep : `u["ActiveAbilities"]` (champ `Units`, survit) et
   `bc["Abilities"]["ActiveAbilities"]` (2ᵉ catalogue, écrasé) portent le **même mot**. C'est la
   chaîne de souscriptions qui tranche, avec suivi des alias (`node = bc.setdefault("Abilities", …)`).
2. **`--check <bc>`** — différentiel à **TROIS** termes (custom / `data/seed-bc.json` / gameconfig).
   Avec deux, on ne distingue pas la dérive de **capture** (#254, légitime) du patch de **fixture** :
   les deux se présentent comme `custom != synth`. Le 3ᵉ terme les sépare.
   `assert_survives(<path>)` est la garde réutilisable à appeler après toute écriture.
3. **`--self-test`** — la morsure, figée : rouge sur le cas connu de #369 (sidecar retiré), vert
   sitôt épinglé, rouge sur un patch de `Constants` et sur un patch de `BC.Utilities` fabriqués,
   **vert sur `data/seed-bc.json`** (aucun faux positif), et l'axe absence dans les deux sens.

## 5. Ce qui n'est PAS couvert

- **Hors `scripts/python/**`** : un appelant Node/shell/notebook qui poserait `--seed-bc <patché>`
  est invisible du balayage. Aucun n'existe à cette date, mais l'outil ne le prouve pas.
- **Indirection** : un patch bâti par clé calculée / `setattr` / dict déballé n'est pas classé.
- **Producteurs non reproductibles offline** : `--measure` couvre les 9 producteurs offline ; ceux
  dont la production exige une session (aucun trouvé) resteraient non mesurés.
- **`buildNormalizedBC`** est un **autre** écraseur (stats, `TertiaryAbilityLevel`, niveaux) —
  hors périmètre ici, documenté par #237.
- `BC.Utilities` n'a **toujours** pas d'épingle : la parade est le rouge de `--check`, pas un
  mécanisme. Créer `withheldUtilities`/`pinnedUtilities` n'a pas de client — le faire sans client
  serait du code spéculatif. **Re-mesuré et FERMÉ sur ce constat le 2026-08-15 → §6.**

## 6. `#380-r1` — « piège armé, sans victime » : RE-MESURÉ, et la réponse est la même

Build `t6dpr4k06g`. Le résidu demandait d'établir **s'il existe une victime** avant d'écrire un
`pinnedUtilities`. Réponse : **non**, et la mesure est aujourd'hui plus large qu'à l'époque.

| | mesure #380 | re-mesure 2026-08-15 |
|---|---|---|
| modules touchant un seed BC (`--scan`) | 75 | **248** |
| sites `bc["Utilities"]` en ÉCRITURE | 2 | **3** |
| dont fixtures VICTIMES | **0** | **0** |

Les trois sites sont `catalog_inject.refresh_ai_utilities` (le rattrapage lui-même) et les deux du
probe de garde `tests/test_380_seed_bc_patch_survival_offline.py` — c'est-à-dire le mécanisme et son
contrôle. **Aucune fixture ne patche un poids d'utilité.** Re-dériver :
`python scripts/python/probe_380_seed_bc_patch_survival.py --scan`.

Le piège reste **armé** : `refresh_ai_utilities` écrase `BC.Utilities` en entier dès que le
gameconfig porte `aiUtilities`, et l'écart capture↔gameconfig vaut aujourd'hui **16 clés ajoutées,
3 valeurs changées, 0 retirée** (identique à la mesure #27-4 sur `rnca9r7q6c`). Mais il n'a
toujours pas de victime, et un `pinnedUtilities` sans client serait un cliquet que le premier
refactor désarmerait. **La ligne est fermée sur ce constat, pas sur un mécanisme.**

### Trouvé en re-mesurant : l'axe symétrique, celui de la LECTURE (`#380-r2`)

Le recenseur regarde qui **ÉCRIT** dans `BC.Utilities`. Personne ne regardait qui la **LIT** — et
deux fichiers prennent la table **BRUTE** de `data/seed-bc.json` pour oracle, alors que tout runner
sert la table **RATTRAPÉE** :

| fichier | catégories lues | dans les catégories dérivées ? |
|---|---|---|
| `tests/engine/test_932_deathwing_offline.py` | `Default/TriggeredAbilitiesNonOwner` (25 au brut, **29** au rattrapé), `Default/TriggeredAbilities` (107 / **112**) | **OUI, les deux** |
| `tests/engine/test_448_r1_already_used_tile_offline.py` | `Default/TileEffects` (20 / 20) | non |

**0 verdict faux aujourd'hui** (les clés `DEATHWING*` sont présentes des deux côtés, et aucune en
non-owner des deux côtés) — mais l'assertion « aucune clé `DEATHWING*` en non-owner » est faite sur
une table qui a **4 clés de moins** que celle que le runner sert. Même forme que #380-r1 : armé,
sans victime. Ouvert en `#380-r2`, non corrigé ici (hors foyer de cette tranche).
