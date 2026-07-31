# #237 — Forcer une RELIQUE en bataille : la condition exacte, au décompilé

**Question binaire.** Peut-on amener en bataille une unité du pool **AVEC une relique qu'elle
n'équipe pas au seed**, et à quelle condition ?

**Réponse.** Oui, et la condition tient en **trois écritures du BC**, chacune adossée à un verrou
natif nommé. Aucune n'est optionnelle, et **deux des trois échouent en silence**.

Build de mesure : `rnca9r7q6c`.

---

## 1. Le pipeline natif, du champ du BC à l'ability montée

`IdunBattle.Entities.Factories.UnitFactory$$Build` construit chaque unité depuis son
`IdunBattle.Configuration.UnitConfiguration`. Trois `AbilityState` y sont fabriqués, dans cet
ordre (offsets lus dans le corps de `Build`, confirmés par `UnitConfiguration$$.ctor`) :

| `AbilityState` | niveau lu | multiplicateur lu |
|---|---|---|
| `activeAbilityState`   | `config+0xb8` = `ActiveAbilityLevel`   | `config+0x74` |
| `passiveAbilityState`  | `config+0xbc` = `PassiveAbilityLevel`  | `config+0x74` |
| `tertiaryAbilityState` | `config+0xc0` = `TertiaryAbilityLevel` | `config+0x78` |

La surcharge de `IdunBattle.Configuration.AbilityState$$.ctor` retenue par `Build` est celle qui
**écrit le niveau DIRECTEMENT** (`*(int*)this = level`) — pas celle qui passe par
`Idun.Shared.Level$$.ctor`. Vérifié par les XREFS entrantes : `UnitFactory$$Build` appelle trois
fois `AbilityState$$.ctor+0x0` (variante à écriture directe), jamais la variante validante.
**Conséquence : aucune validation du niveau au moment du build.** Un `TertiaryAbilityLevel = 0`
traverse la construction sans un mot.

Puis `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities(entity, config,
activeAbilityState, passiveAbilityState, tertiaryAbilityState)` :

* itère `config+0xa8` (les passives) → `TriggeredAbilityComponent$$TryAdd(id, passiveState, 2)` ;
* **si `config+0xb0` (`Nullable<TriggeredAbilityType> TertiaryAbility`) a une valeur** →
  `IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd(id, tertiaryState, 3)` ;
* itère `config+0xa0` (les actives) → `UnitFactory$$AddActiveAbility`.

Le littéral `3` est la **hiérarchie Tertiary** — c'est le discriminant observable qui distingue une
relique d'un passif de kit dans le composant. `TryAdd` stocke `{abilityId@+0x10, Level@+0x20,
VariableMultiplierPercentage@+0x24, Counter@+0x28, Hierarchy@+0x38}` et ne valide rien.

## 2. Le verrou du NIVEAU — `Idun.Shared.Level$$ToZeroBasedIndex`

Les **quatre** accesseurs de variable d'une `AbilityConfiguration` —
`GetVariableForLevel`, `TryGetVariableForLevel`, `GetVariableArrayForLevel`,
`GetAllVariablesForLevel` — passent **tous** par le même foyer :
`IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`. Son corps :

```
idx = Idun.Shared.Level$$ToZeroBasedIndex(abilityState)   // level - 1
idx = System.Math$$Max(0, idx)
if (idx < arr.Length)  lVar5 = idx
else                   lVar5 = arr.Length - 1             // CLAMP HAUT
... arr[lVar5] ...
```

et `Idun.Shared.Level$$ToZeroBasedIndex` :

```
if (0 < *param_1) return *param_1 - 1;
throw new InvalidOperationException(...)
```

D'où **la condition exacte, nommée** :

> **`BC.Units[].TertiaryAbilityLevel >= 1`.**
> Champ : `UnitConfiguration+0xc0`. Lu par `UnitFactory$$Build` (→ `AbilityState`), consommé par
> `AbilityConfiguration$$TryGetVariableArrayForLevel`, comparé à **`0`** dans
> `Idun.Shared.Level$$ToZeroBasedIndex`, qui **lève `InvalidOperationException`** sur `<= 0`.

Et son pendant, qui compte autant parce qu'il **désamorce** une fausse crainte :

> **Il n'y a PAS de borne haute.** Le même foyer clampe (`idx >= len` → `len - 1`). Un niveau 50
> sur une ability de relique à **10** paliers rend le palier 10 — pas une erreur, mais pas le
> niveau demandé non plus.

Le `0` n'est pas une valeur accidentelle : `Idun.Shared.Level$$CreateValidOrLockedLevel` le laisse
passer explicitement (`if (param_1 == 0) return 0;`) et `Idun.Shared.LevelJsonConverter$$ReadJson`
aussi — **`0` signifie « verrouillé / non débloqué »**, pas « niveau zéro ». C'est exactement ce que
portent les **171** entrées `Units` sans relique du seed BC, et ce que `catalog_inject.synthesize`
produit. Poser la relique sans toucher au niveau laisse donc une unité qui **se déploie
normalement** puis **faute à la première lecture de variable**.

⚠ La désérialisation n'est PAS le verrou : `LevelJsonConverter$$ReadJson` accepte `0` et tout entier
positif, ne refusant que les négatifs (`ArgumentOutOfRangeException`). Chercher la validation à la
lecture du JSON est une fausse piste.

## 3. Le verrou de la CONFIG — 29 des 32 abilities de relique sont absentes du seed BC

Mesuré (`python catalog_inject.py --list-relics`) : le gameconfig porte **32 items relique**
(`items[*].abilityId`), donc **32 abilities distinctes**. Le seed BC n'en porte la config que pour
**3** — exactement celles qu'une unité équipe au seed :
`KardiocoreGalvanus` (1457), `NetherRealmCasket` (1462), `SupaCyborkBody` (1475).

C'est le verrou déjà connu de #226, appliqué à la relique. **Mesuré, la forme exacte est plus
retorse qu'une config nulle** : `AbilitiesDatabase.GetConfig(1467)` rend une config **non nulle mais
VIDE** (`cfgClassName = AbilityConfiguration`, `rarityFlagged: []`), et
`GetVariableForLevel(extraCritDmg, level=6)` y rend **`0`** au lieu de `749`. La sonde
`abilityConfigProbe` passe `fallbackToDefault = true`, d'où le `0` ; **le jeu, lui, faute** — le
nœud DSL qui lit la variable dans le behaviour de la relique
(`IdunBattle.Entities.Formulas.ConfigAmount$$Calculate`, atteint depuis
`RelicBoltPistol_ExtraCritDamageEffect$$CreateCritDamageBonus` via
`IdunBattleLogic.Entities.DSLFormulas$$ConfigVar`) appelle
`GetVariableForLevel(cfg, varType, state, 0)`, donc **`fallbackToDefault = false`**, et cette
branche lève `System.Exception`. `catalog_inject.synthesize_ability` produit l'entrée depuis le
gameconfig.

⚠ **`BC.Abilities` traverse `buildNormalizedBC` INTACT** — le RPC ne touche que `bc.Units`,
`bc.Board` et `bc.SpawnPointSetIndex`. La config peut donc se poser avant OU après la
normalisation, contrairement au couple `TertiaryAbility`/`TertiaryAbilityLevel`. Mesuré : supprimer
l'injection pré-normalisation de `rl_duel` ne rend **aucun** test rouge, parce qu'`equip_relic` la
repose après. C'est pourquoi il n'y a qu'**un seul foyer** — `equip_relic`.

## 4. Ce que fait `buildNormalizedBC`, et pourquoi l'ORDRE compte

`frida/hooks/features/normalize-bc/json-build.ts` ne touche à la relique que d'une façon :

```ts
if (typeof args.targetAbilityLevel === "number") {
    const lvl = args.targetAbilityLevel;
    u.ActiveAbilityLevel = lvl;
    u.PassiveAbilityLevel = lvl;
    if (u.TertiaryAbility != null) u.TertiaryAbilityLevel = lvl;
}
```

Il **PRÉSERVE `TertiaryAbility`** et **ÉCRASE `TertiaryAbilityLevel`** — avec
`targetAbilityLevel = 50` (`rl_collect_batch._normalize_and_extract_pool`). Deux conséquences
mesurées, l'une bénigne et l'autre décisive :

* **bénigne** — les 4 unités du seed passent de `TertiaryAbilityLevel = 1` à `50`, donc le natif
  les clampe au palier **10**. Le harnais ne joue donc jamais une relique au niveau du seed ;
* **décisive** — le champ n'est réécrit que **si `TertiaryAbility` est déjà non nul au moment de la
  normalisation**. Poser la relique **après** `buildNormalizedBC` (par `--unit-stat`, par un patch
  du template) laisse `TertiaryAbilityLevel` à **0** : verrou 3 armé, en silence.

D'où les deux voies, et ce qu'elles donnent :

| voie | où on pose | niveau effectif |
|---|---|---|
| seed BC augmenté (`write_relic_seed_bc` + `build --seed-bc`) | avant normalisation | **écrasé à 50** → clampé au dernier palier |
| `rl_duel build --equip-relic` | **après** normalisation | **exactement celui demandé** |

Mesuré live, vue ROUGE : en retirant l'écriture du niveau d'`equip_relic`, le test
`test_relique_non_equipee_arrive_en_bataille` rend
`AssertionError: TertiaryAbilityLevel attendu 3, lu 0` — le natif porte bien **0** quand personne
ne l'écrit après la normalisation.

## 5. Le montage — fixture nommée et réutilisable

```bash
# recenser : abilities, ids TriggeredAbilityType, paliers, porteurs, config présente ou non
python catalog_inject.py --list-relics
python catalog_inject.py --relic-state          # les TROIS états, sur le seed BC

# monter, niveau EXACT (voie recommandée)
python rl_duel.py build --board MC1_67 --state-file <absolu>.json \
    --p-units ultraTitus --equip-relic "ultraTitus:RelicBoltPistol:6"

# ou écrire un seed BC réutilisable (niveau ensuite écrasé à 50 par la normalisation)
python catalog_inject.py --equip-relic "tauCrisis:Dw02AdvancedBurstCannon:10" \
    --out <absolu>/logs/relic.json
```

Depuis un test/probe Python : `catalog_inject.equip_relic(bc, unit_id, ability, level)` sur un BC
déjà chargé, ou `catalog_inject.write_relic_seed_bc(out, ["uid:Ability:lvl", ...])`. La fonction
fait les **trois** écritures d'un bloc — les séparer est précisément ce qui produit un montage
muet. Elle **refuse** `level < 1` en nommant `Idun.Shared.Level$$ToZeroBasedIndex`, et refuse un
porteur hors `allowedUnits` sauf `allow_unlisted=True` (greffe assumée : le natif côté combat ne
relit jamais `allowedUnits` — c'est un garde-fou de montage, pas une gate du moteur).

## 6. Les TROIS états, re-dérivés

`python catalog_inject.py --relic-state`, sur `data/seed-bc.json` :

| état | compte | ce qu'il faut |
|---|---|---|
| 1 — relique **équipée au seed** | **4** unités, 3 abilities (`admecMarshall`/`admecRuststalker` partagent 1457) | rien |
| 2 — au catalogue, relique **absente** | **52** | les trois écritures (ce cas) |
| 3 — porteur **hors catalogue** | **9** (`adeptCelestine`, `astarCyrus`, `darkaSternguard`, `emperExultant`, `emperFlawlessBlade`, `spaceWolfPriest`, `tauFarsight`, `votanIronmaster`, `votanUthar`) | injection catalogue (#92 §6) **puis** les trois écritures |

4 + 52 = **56**, le chiffre de `case-323`. L'état 3 était compté « 0 » par toute lecture qui
s'arrêtait au pool.

## 6bis. Ce qui a été MESURÉ live (build `rnca9r7q6c`, board `MC1_67`, seed 777)

Observable : `unitAbilityStates` dumpe `TriggeredAbilityComponent+0x18` instance par instance ;
`raw` = 12 × int32 depuis `+0x10`, donc `raw[0]` = id, `raw[4]` = Level, `raw[10]` = **hiérarchie**.
Une relique montée = une entrée de hiérarchie **3**. `probe_237_relic_equip.py` :

| régime | mesure |
|---|---|
| TÉMOIN (aucun montage) | **0** entrée de hiérarchie 3 |
| `ultraTitus` ← `RelicBoltPistol` niv. 6 | `{abilityId: 1467, level: 6, mult: 100}` — montée |
| `admecDestroyer` ← `KardiocoreGalvanus` niv. 3 | `{abilityId: 1457, level: 3, mult: 100}` — montée |
| `RelicBoltPistol.extraCritDmg` par niveau | 1 → **590**, 6 → **749**, 10 → **877**, **50 → 877** |
| `KardiocoreGalvanus.extraCritDmg` par niveau | 1 → **295**, 3 → **327**, 10 → **438**, **50 → 438** |
| niveaux `0` et `-1` | **`err: "system error"`** (l'`InvalidOperationException` de `ToZeroBasedIndex`) |
| `RelicBoltPistol` sans sa config au BC | variable → **`0`** au lieu de 749 |

Les valeurs correspondent au gameconfig terme à terme
(`extraCritDmg: [590, 622, 654, 686, 717, 749, 781, 813, 845, 877]` → `arr[level-1]`), et le
**clamp haut** est direct : 50 rend le palier 10.

**Généralisation — l'ÉTAT 3 joué de bout en bout, et les deux voies confrontées côte à côte.**
`tauFarsight` est **hors catalogue** ; injecté (`catalog_inject --units tauFarsight`) puis équipé de
`DawnBlade` (1501, `allowedUnits = [tauFarsight]`), niveau **8** demandé :

| voie | `TriggeredAbility.Level` lu en bataille | `extraDmg` résolu |
|---|---|---|
| A — relique dans le seed BC, puis `build --seed-bc` | **50** (écrasé par `buildNormalizedBC`) | 579 = palier **10** |
| B — `build --equip-relic "tauFarsight:DawnBlade:8"` | **8** (exact) | **537** = palier 8 |

⚠ La variable sondée est **`extraDmg`** (`[390, 411, …, 579]`), pas `hpToHeal` : le probe prend
`sorted(variables)[0]`. `DawnBlade.hpToHeal` vaut `[4895, …, 7273]` — c'est elle que lit le
behaviour porté, et #357 la mesure (6745 au niveau 8).

Sur les deux runners : niveau 10 → 579, **niveau 50 → 579** (clamp), niveau 0 → `system error`.
C'est la mesure qui tranche « où poser le couple » : la voie A **ne peut pas** jouer un niveau
choisi.

**Balayage offline** : les **32** abilities de relique se synthétisent (`synthesize_ability`, 0
échec) et les **56** couples (porteur au catalogue × relique autorisée) se montent — soit toutes
les unités des états 1 et 2.

## 7. Ce qui n'est PAS couvert

* ~~**Le rail COMBAT du port Python ne lit toujours pas la relique équipée** (résidu `N317-a`).~~
  **FERMÉ par #357** (`case-357-rail-relique-equipee.md`) : `snapshot._load_tertiary_abilities`
  (canal OPT-IN `load_state(ability_states=…)`, RPC `unitAbilityStates`, entrées de hiérarchie 3)
  seede `UnitContext.tertiary_ability`, et `collect_triggered_abilities` l'inscrit comme CINQUIÈME
  chemin de registration. Confronté live sur `DawnBlade` : natif == port == `hpToHeal[niveau]` sur
  deux niveaux (6745 et 5423), 0 côté port sans le canal. **Une seule relique sur 32**, et le canal
  n'a qu'un producteur (le probe) — hors de ce montage une relique équipée reste inerte.
* **Aucune mesure du contenu de l'effet** : le probe vérifie que l'ability est **montée** (hiérarchie
  3, id, niveau) et que le natif **résout ses variables** — pas que son effet de jeu est correct.
* **La levée du verrou 2 en usage réel est LUE, pas jouée.** Le décompilé de
  `ConfigAmount$$Calculate` montre `fallbackToDefault = false`, donc l'exception ; la mesure, elle,
  passe par `abilityConfigProbe` (qui force `dontThrow`) et observe la valeur **`0`**. Faire fauter
  un vrai cast demanderait de déclencher le trigger de la relique en bataille — hors périmètre.
* **`allowedUnits` n'a pas été confronté côté natif** : rien dans `AddConfiguredAbilities` ne le
  relit, mais aucun montage `allow_unlisted=True` n'a été joué live pour le vérifier.
* ~~`TertiaryAbilityVariablesMultiplierPercentage` (`UnitConfiguration+0x78`) vaut **200** sur les
  entrées du seed et n'est **jamais** recalculé par `buildNormalizedBC`. Un porteur synthétisé par
  `catalog_inject.synthesize` porte **100**. L'écart n'a pas été confronté ici.~~ **TRANCHÉ par
  #357** : ce n'est pas un écart de synthèse. Sur les 175 entrées du seed, `+0x78` vaut **200** sur
  **4** et **100** sur **171** — et les 4 sont EXACTEMENT celles qui portent une `TertiaryAbility`
  (elles portent aussi `AbilityVariablesMultiplierPercentage = 200`). Les 171 autres n'ont pas de
  relique : leur `+0x78` est un champ neutre que rien ne lit, donc le `100` de `synthesize` est
  correct. Mesuré en bataille à deux sources indépendantes (`AbilityState` monté et
  `unitConfig.tertiaryAbilityVariablesMultiplier`) : **100** des deux côtés, contre **180** pour
  `+0x74` — deux champs distincts, et le port lit le bon.

## 8. Ce que ce cas a démenti en route

* **« Le verrou est le niveau du HÉROS porteur »** — non. Ni `Level`, ni `Rank`, ni
  `StarLevel`, ni `ActiveAbilityLevel` n'entrent dans le chemin de la relique.
  `UnitProgression$$ProgressionLevelNeededToUnlockTertiaryAbility` existe bien, mais c'est du côté
  **META** (`IdunMetaLogic.UserProgress`), sur le chemin qui CONSTRUIT un BC depuis la progression
  du joueur. Nous fabriquons le BC directement : ce chemin n'est jamais emprunté. Le verrou est le
  niveau de **l'ABILITY tertiaire**, pas celui de l'unité.
* **« Un niveau trop haut casse »** — non, le natif clampe. La crainte d'un dépassement d'index sur
  10 paliers est infondée ; l'écriture `TertiaryAbilityLevel = 50` de `buildNormalizedBC` est
  inoffensive (mais non fidèle).
* **« La désérialisation valide le niveau »** — non, `LevelJsonConverter$$ReadJson` accepte `0`.
