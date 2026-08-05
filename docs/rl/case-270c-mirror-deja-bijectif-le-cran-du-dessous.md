# #270-c — `TriggeredAbilityType` : le mirror était DÉJÀ régénéré, le trou était un cran plus bas

**Build** `rnca9r7q6c` (`data/symbols/CURRENT` == `ghidra_symbols.py build` == build installé, vérifié).
Tranche **offline pure** — aucun runner, aucune session Frida.

## 1. Le constat de la tâche était PÉRIMÉ, et l'écart s'explique exactement

La ligne de backlog annonçait « le mirror porte **574** membres, **107 ids morts**, **9 manquants** ».
Re-dérivé du disque, le mirror est en **bijection parfaite** :

| table | membres | manquants | morts | renumérotés |
|---|---|---|---|---|
| `engine.entities.TriggeredAbilityType` **avant** `05518726` (#313) | 575 | 8 | 107 | 0 |
| `engine.entities.TriggeredAbilityType` **courant** | **476** | **0** | **0** | **0** |
| `enum_maps.PASSIVE_ABILITY_TYPE` **avant** `218ddfc6` (#275) | 574 | 9 | 107 | 0 |
| `enum_maps.PASSIVE_ABILITY_TYPE` **courant** | **476** | **0** | **0** | **0** |
| `IdunBattle.Entities.Enum.TriggeredAbilityType` (build) | 476 valeurs / 477 noms | — | — | — |

**Les deux chiffres du backlog sont justes — ils décrivent l'AUTRE table.** `574 / 9 / 107` est
`enum_maps.PASSIVE_ABILITY_TYPE` avant #275 ; le mirror Python, lui, en portait `575 / 8 / 107`.
**L'écart d'exactement 1 est `ModifiedExoarmour` (1529)**, que #304 avait ajouté à la main au mirror
pour porter un passif — d'où un membre de plus et un manquant de moins. Les deux tables ont été
réparées séparément (#275 puis #313), et **aucune n'a été rouverte depuis**.

Le mirror est **SOUS GARDE** dans `probe_313` depuis #313, et `9999` porte l'alias
`{STRIPPED, testAssetBundles}` — d'où 476 valeurs pour 477 noms, ce qui n'est pas une dérive
(l'inclusion `noms_port <= noms_jeu` le couvre déjà).

## 2. Les cinq contrôles de dé-risquage, rejoués sur CET enum

Transposés du patron #275-a / #318, sur l'état courant. Les 107 noms retirés sont re-dérivés du git
(`05518726~1`), jamais recopiés.

| # | contrôle | mesure |
|---|---|---|
| C1 | AST — `TriggeredAbilityType.<membre>` dans du Python suivi | **161** références (2 416 tous mirrors) ; **0** introuvable, **0** morte |
| C2 | textuel global — un nom RETIRÉ subsiste-t-il ? | **22 / 107** présents ailleurs, **0** comme `TriggeredAbilityType` : tous sont des **homonymes** d'un autre enum (`EffectType`, `UnitTrait`, `UtilityType`), des chaînes du seed BC / i2, ou des tables de hooks. `Regeneration` dans le mirror lui-même = `EnhancementRegeneration` (1433, vivant) — faux positif de la recherche par sous-chaîne |
| C3 | `TriggeredAbilityType(<littéral>)` | **2** sites, **0** id inconnu du build |
| C4 | clés des dicts consommateurs | `ABILITY_TRIGGERS` 35, `RELIC_ABILITY_TRIGGERS` 1, `CUSTOM_TRIGGERED_ABILITIES` 1, `TRAIT_TRIGGERED_ABILITY_IDS` 5 → **0** hors build |
| C5 | gameconfig — nomme-t-il un membre retiré ? | **0** sur 247 noms (`passiveAbilities` + `relicAbilities` + `mythicAbilities`) ; **1 seul non nommable**, `ShroudPsalm` (cf. §4) |

## 3. Le vrai trou : le cran EN DESSOUS du mirror

Un mirror bijectif ne dit rien de ce que le moteur **lit**. `dispatch/core.py` fait
`ABILITY_TRIGGERS.get(pa, ())` : **une clé dont le nom a disparu du build ne lève pas** — elle rend
`()`, et le passif n'est **jamais inscrit**. C'est mot pour mot la dégradation du sens MANQUANT
(« il ne casse rien, il RETIRE en silence »), **un cran plus bas**, et elle survit à un mirror
parfait.

#318 avait fermé ce cran pour **`EFFECT_CLASSES` seul**
(`test_le_registre_EFFECT_CLASSES_resout_entierement_dans_le_mirror`). Les **six registres** de
`triggers.dispatch` — c'est-à-dire les **cinq chemins de registration** que parcourt
`collect_triggered_abilities` (trait, `passiveAbilities`, `activeAbilities` dérivées,
`relicAbilities` + `UnitConfiguration.TertiaryAbility`, effet) — n'étaient gardés par personne.

**Étape 5 de `probe_313`** : **245 clés** sur 7 dicts (35 + 2 + 1 + 11 + 163 + 1 + 32). Trois
verdicts, dont un **nomme sa cause** :

- `INTROUVABLE` — la clé n'est dans aucun enum du build : l'entrée est morte, en silence ;
- `MORTE` — dans le mirror mais plus dans le build : le mirror ment en plus ;
- `EGAREE` — **le nom vit dans un AUTRE enum** : c'est l'**appariement du registre** qui est faux,
  pas la clé. Dire « absente » enverrait chercher une faute de frappe.

**Les appariements sont LUS**, jamais déduits du fait qu'une clé « résout » — et c'est nécessaire :
`TriggeredAbilityType` et `EffectType` partagent **458 ordinaux sur 476**, dont **454 nomment autre
chose**. Une clé entière qui résout ne prouve donc à peu près rien.

**La forme `EGAREE` est arrivée pendant cette tranche.** Apparier `RELIC_ABILITY_TRIGGERS` à
`ActiveAbilityType` — une relique, donc « active » de réflexe — fait sortir `DawnBlade`, qui est un
`TriggeredAbilityType` **1501** : le natif la monte par
`TriggeredAbilityComponent$$TryAdd(id, tertiaryAbilityState, 3)`, branche tertiaire d'
`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`. Mesure corroborante : les **25**
noms de `relicAbilities` du gameconfig sont **25/25** dans `TriggeredAbilityType`, **0/25** dans
`ActiveAbilityType`.

## 4. Les homonymes inter-enums — un INVENTAIRE, jamais une garde

Un homonyme est un fait du **build**, pas une dérive du port : le garder ferait crier le cliquet en
permanence. `probe_313 --homonymes` l'imprime, sans jamais rougir. **Deux axes, coût inégal.**

**Axe NOM** (`TriggeredAbilityType`, 476 valeurs) — **158 paires** de noms partagés avec un autre
enum à ordinal **DIFFÉRENT** : `AdaptiveToxins` (Trig 1097 / `EffectType` 1095), `Ambush`
(Trig 1271 / `UnitTrait` 1052), `BattleFocus` (Trig 1172 / `EffectType` 1199), `BigTarget`
(Trig 1030 / `UnitTrait` 1017)… Lire un de ces noms depuis le mauvais mirror rend un **ordinal
FAUX**. **C'est ce que l'étape 5 garde** (`EGAREE`).

**Axe ORDINAL** — un même ordinal sous des noms **différents** rend une clé **entière** non
vérifiable :

| autre enum | ordinaux partagés avec `TriggeredAbilityType` | dont nom DIFFÉRENT |
|---|---|---|
| `EffectType` | 458 | **454** |
| `ActiveAbilityType` | 233 | **231** |
| `GuiId` | 122 | 122 |
| `UnitTrait` | 65 | 64 |

C'est la **justification chiffrée** de « un entier qui DÉSIGNE passe par un enum » (CLAUDE.md) :
le nom discrimine, l'ordinal non.

## 5. Ce que ça DÉBLOQUE pour #270-r1

Le volet 2 de #270-r1 attend les **56 clés qui hésitent `Active` / `Triggered`**. Deux faits mesurés :

1. **Le mirror n'est plus le blocage** : `TriggeredAbilityType` est bijectif et sous cliquet
   (le CLAUDE.md disait le contraire — corrigé par cette tranche).
2. **Le NOM tranche sans ambiguïté.** Sur le gameconfig du build, **aucun nom n'est ambigu** :

   | voie | noms | `TriggeredAbilityType` seul | `ActiveAbilityType` seul | **les deux** | aucun |
   |---|---|---|---|---|---|
   | `passiveAbilities` | 211 | 210 | 1 | **0** | 0 |
   | `activeAbilities` | 175 | 1 | 174 | **0** | 0 |
   | `relicAbilities` | 25 | 25 | 0 | **0** | 0 |
   | `mythicAbilities` | 11 | 11 | 0 | **0** | 0 |

   L'intersection nom-à-nom actives/passifs est **VIDE** — `audit_passive_ability_coverage.py` le
   mesure de son côté, indépendamment (206/207 `TriggeredAbilityType`). **Deux sources concordantes.**

**Les deux exceptions ne sont pas des homonymes, mais des INVERSIONS DE VOIE** — le champ gameconfig
ment sur la nature de l'ability, et une conversion mécanique « voie ⇒ enum » y produirait un id faux
ou un membre jeté :

- `admecBossBelisarius` (npc) porte **`ShroudPsalm`** en `passiveAbilities`, alors que le nom n'existe
  que dans `ActiveAbilityType` (**1181**). `triggered_ability_ids()` le **jette en silence**
  (`__members__.get` → `None`). Déjà connu de `audit_passive_ability_coverage.py`.
- `eldarBossMauganRaUltra` (npc) porte **`Maugetar`** en `activeAbilities`, alors que le nom n'existe
  que dans `TriggeredAbilityType` (**1498**). Déjà connu de `audit_kit_coverage.py`.

⇒ **la conversion se fait PAR NOM, jamais par la voie**, et les deux exceptions se lisent
explicitement.

## 6. Le détecteur MORD — vérifié par mutation réelle, restaurée

Un cliquet vert sur un dépôt sain ne prouve rien.

| mutation | posée où | verdict rendu |
|---|---|---|
| clé `"Narthecium"` → `"NartheciumZZ"` | `dispatch/registry.py` (fichier réel) | `INTROUVABLES=['NartheciumZZ']` — **rouge** |
| appariement `RELIC_ABILITY_TRIGGERS` → `ActiveAbilityType` | `probe_313` (fichier réel) | `EGAREES=[('DawnBlade', ['TriggeredAbilityType'])]` — **rouge, et il nomme le bon enum** |
| clé juste (`Narthecium`, `FabricatorClawArray`) | table truquée | `([], [], [])` — anti-faux-positif |

Les trois sens sont aussi exercés sur tables truquées dans le cliquet, dont `MORTE` — aucun membre du
mirror n'étant dans ce cas (c'est ce que garde l'étape 2), cette branche ne serait **jamais exercée**
sans truquage de l'enum du build.

## 7. Ce qui n'est PAS couvert

- **`scripts/sql/006` et `013`** (`ref_triggered_ability`, `ref_effect`) : **hors périmètre**
  (résidu #270-b, générateurs arrimés à un `dump.cs` supprimé). **Non re-mesurés.**
- **`frida/hooks/data/triggered-ability-names.ts`** : à jour (476 entrées, généré depuis
  `rnca9r7q6c`), gardé par `probe_252_hook_name_tables.py`. **Constaté, pas modifié.**
- Les **128 clés ambiguës** de #270-r1 : cette tranche les **débloque** (§5), elle ne les convertit
  pas.
- **L'étape 5 ne garde que les 7 dicts inscrits.** Contrairement à l'étape 1 (qui **découvre** toute
  `IntEnum` sous `engine/`), le registre `CONSOMMATEURS` est une **liste écrite** : un huitième dict
  ajouté demain y échapperait sans que rien ne le signale. Découvrir automatiquement « un dict dont
  les clés désignent un enum » n'est pas décidable par AST — une table de constantes et un registre
  d'abilities ont la même forme. **Résidu `#270-r2`** (numéro attribué par
  `probe_468_collision_numeros.py --suggere 270`, jamais choisi).
- Les registres **par valeur** (`CUSTOM_TRIGGERED_ABILITIES`, `EFFECT_TRIGGERS`) sont gardés
  **beaucoup plus faiblement** : avec 454/458 ordinaux partagés `Trig`/`Effect` nommant autre chose,
  un id qui « résout » ne prouve pas l'enum. C'est dit dans le code plutôt que maquillé.
- **Aucun contrôle live.** Budget saturé (`liveRunners` 5 pour un plafond de 4) et la tranche est
  offline-dominante ; `dumpEnum` n'a pas été sollicité — `enums.tsv` + `classes.tsv` + gameconfig +
  les deux audits suffisent, et `dumpEnum` mesurerait la même chose par un canal plus cher.
