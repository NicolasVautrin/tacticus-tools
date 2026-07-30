# case-275 — `enum_maps.py` périmée, et sans réparateur

**Question binaire, par enum** : la table de `scripts/python/enum_maps.py` coïncide-t-elle
EXACTEMENT — mêmes valeurs, mêmes noms — avec `data/symbols/<CURRENT>/frida/enums.tsv` ?
Toute divergence est un **nom FAUX rendu en silence**.

Build de référence : `rnca9r7q6c`. Toutes les mesures ci-dessous sont re-dérivables par
`python scripts/python/probe_275_enum_maps_drift.py [--citations] [--live]`.

## 1. Verdict par bloc — 3 des 6 dérivaient

| bloc | enum natif | avant | après | renumérotés | absents du jeu | manquants |
|---|---|---:|---:|---:|---:|---:|
| `EFFECT_TYPE` | `IdunBattle.Entities.Enum.EffectType` | 682 | **629** | **2** | 73 | 20 |
| `ACTIVE_ABILITY_TYPE` | `…Enum.ActiveAbilityType` | 260 | 260 | 0 | 0 | 0 |
| `PASSIVE_ABILITY_TYPE` | `…Enum.TriggeredAbilityType` | 574 | **476** | 0 | 107 | 9 |
| `DAMAGE_PROFILE_TYPE` | `…Enum.DamageProfileType` | 24 | 24 | 0 | 0 | 0 |
| `UNIT_SPAWN_SOURCE` | `…Enum.SpawnSource` | 9 | 9 | 0 | 0 | 0 |
| `GROUP_TYPE` | `IdunBattle.Streams.GroupType` | 102 | **104** | **66** | 0 | 2 |

`ACTIVE_ABILITY_TYPE` était déjà sain — il a son propre régénérateur depuis #276. Les trois
autres blocs sains le sont **par chance** : ce sont les plus petits, et le jeu n'y a rien
touché. Rien dans le dépôt ne le garantissait avant ce cas.

**Le nom du bloc ne suit pas celui de l'enum** : `PASSIVE_ABILITY_TYPE` vient de
`TriggeredAbilityType`, `UNIT_SPAWN_SOURCE` de `SpawnSource`, et `GROUP_TYPE` d'un **autre
namespace** (`IdunBattle.Streams`). Les six appariements sont lus dans `enums.tsv`, jamais
déduits du nom ; l'appariement fait foi dans `regen_enum_maps.BLOCS`.

### Les deux réattributions — le cas qui ne proteste pas

Un id **réattribué** est pire qu'un id absent : il résout, pointe ailleurs, et rien ne signale
l'erreur.

* `GROUP_TYPE` : un membre `Ability_Displace` inséré en **36** et `EndTurn` en **48** décalaient
  **66 ids**. La table donnait `59 = NormalAttack_AtomicDamage` là où le jeu dit `ZingerAbility`
  (le vrai `NormalAttack_AtomicDamage` est **61**). C'est ce mensonge qui avait fixé le `59` de
  `_ATTACK` dans l'ingest RL — le fallback « 015 » ne s'est donc **jamais** armé sur une attaque
  normale (corrigé en #254b-b côté code ; la table, elle, restait fausse jusqu'ici).
* `EFFECT_TYPE` : `1563`/`1564` portaient `DA_Hero6_Passive_1`/`_2`, deux membres qui n'existent
  sur **aucun** des deux builds versionnés. Le jeu y place
  `SpecialIssueCombiMelta_AdditionalHits`/`_ExtraDmg`.

`GROUP_TYPE` n'a **rien à voir avec la migration de build** : `probe_274` mesure `GroupType` à
**0 ordinal divergent** entre `gqfc5mff6c` et `rnca9r7q6c`. C'est une table qui n'avait jamais
été régénérée depuis un `dump.cs` bien antérieur. `StepType`, lui, a **55** ordinaux divergents
entre ces deux builds — ne pas confondre les deux causes.

## 2. La cause racine : le réparateur était en panne

`enum_maps.py` était généré par `rl_gen_enum_columns.py`, qui lit `data/dumps/<hash>/dump.cs` —
artefact Il2CppDumper **gitignoré et supprimé le 2026-07-25**. Même cause racine que #270 : la
dérive n'avait plus rien pour la corriger, et rien pour la signaler.

Livré : **`scripts/python/regen_enum_maps.py`**, sur le patron de
`regen_active_ability_tables.py` (#276) — il lit `data/symbols/<CURRENT>/frida/enums.tsv`, qui
est **versionnée** donc présente dans tout checkout, y compris un worktree d'agent frais.

Règles reprises de #256/#270 : on garde le nom déjà présent s'il appartient toujours à
l'ensemble des noms de cette valeur (diff minimal), sinon le premier par ordre lexicographique ;
seuls les blocs visés et l'en-tête du fichier sont réécrits, `BY_COLUMN` et le reste sont
recopiés verbatim.

Un commentaire de fin de ligne a disparu au passage, et c'est voulu :
`1551: 'RedRampage',  # fix live dumpEnum 2026-07-23 (absent du tsv)`. Il était **faux** —
`RedRampage` est bien dans `enums.tsv` à 1551, sur les **deux** builds versionnés.

## 3. Les 180 suppressions, tranchées citation par citation

Le piège de #270 : une régénération naïve **supprime** des membres encore cités par le port.
Les 73 + 107 noms retirés ont été passés au crible (`probe_275 … --citations`, étape 3) :

| classe | occurrences | verdict |
|---|---:|---|
| `GENERE` | 731 | lignes de table (`enum_maps`, les mirrors `engine/entities/*_type.py`, SQL 006/013) — pas des citations |
| `HOMONYME` | 100 | le nom vit dans un **autre** enum ou dans le gameconfig |
| `DOC` | 86 | prose (journaux, wiki) — dominée par des mots courants (`Guard`, `Attack`) qui ne parlent pas de l'enum |
| `CODE` | **47** | voir ci-dessous |

**Aucune des 47 citations `CODE` ne devient fausse**, et il a fallu les lire une par une :

* **41** sont des faux positifs textuels : `Guard` dans « Death Guard », « Tyrant Guard »,
  « Guardsman » — le membre `TriggeredAbilityType.Guard` disparaît, le mot anglais reste ;
* **3** citent `SpiderWeb` dans des commentaires sur la **catégorie BC**
  `Utilities.Default.AddedTileEffects`, dont les clés viennent de la `BattleConfiguration`, pas
  de l'enum ;
* **2** sont dans `frida/public/src/battle-log.js` (`GROUP_LABEL`) et
  `frida/hooks/features/ai-utility-trace.ts` (`UTILITY_TYPE_NAMES`) : **tables indépendantes, et
  justes**. `GROUP_LABEL` porte bien `Ability_Displace` et `EndTurn` — le front était correct et
  `enum_maps` faux. `probe_274.sweep_js` garde déjà cette table.

**Collisions de valeur** (étape 2 du probe) : les 66 renumérotations de `GROUP_TYPE` sont
**toutes** des collisions — l'ancien nom vit toujours dans l'enum, à la valeur voisine. C'est
précisément pour ça qu'elles étaient invisibles : chaque nom cité restait valide, seul
l'appariement id↔nom mentait.

## 4. La base RL : la prémisse était fausse, et rétro-corriger aurait DÉTRUIT des données justes

La tâche annonçait « `stream_event.step_name` est décalée de +1 pour tout pas ≥ 7 sur
l'historique ». **Mesure sur la base réelle : c'est faux, et l'inverse est vrai.**

État mesuré (un seul batch, `batch_id=1`, `started_at = 2026-06-14`, 50 batailles) :

| colonne | lignes | fausses |
|---|---:|---:|
| `stream_event.step_name` | 61 785 | **0** (voir ci-dessous) |
| `stream_event.effect_type_name` / `passive_…` / `active_…` / `damage_profile_…` / `unit_spawn_…` | 11 083 | **0** |
| `stream_group.group_name` | 38 440 | 2 099 « faux » **au sens du build courant seulement** |

### Quel build a émis ces ordinaux ? La question qu'il fallait poser d'abord

`step_code` et `group_code` sont des **ordinaux implicites** : leur nom dépend du build qui les
a émis. On ne peut donc pas juger un nom stocké sans savoir de quel build il vient — et
`batch.game_hash` valait **`.temp`**, une valeur qui ne désigne aucun build (voir §5).

Premier indice, trompeur : les `step_name` stockés coïncident à **100 %** (61 785/61 785,
33/33 couples) avec la table `gqfc5mff6c`. Cela prouve seulement que la **table de nommage**
utilisée à l'ingest était `gqfc5mff6c`-compatible — pas que le **jeu** émettait ces ordinaux.

Le discriminant qui tranche est **sémantique**, et il ne dépend d'aucune table du dépôt : le
**contenu** des groupes.

| observation | build à 102 membres | build à 104 membres |
|---|---|---|
| `group_code = 46` contient 561 fois le pas `StartTurn` | 46 = `StartTurn` ✔ | 46 = `RarityCapTransform` ✘ |
| `group_code = 59` : **1 212** groupes, tous sous `Ability_Power` | 59 = `NormalAttack_AtomicDamage` ✔ | 59 = `ZingerAbility` ✘ |
| `group_code = 61` : **0** groupe | 61 n'existe pas encore ✔ | 61 = `NormalAttack_AtomicDamage`, ~1 200 attendus ✘ |
| `group_code = 48` : **0** groupe | 48 = `HornOfDespair_LightUnits`, rare ✔ | 48 = `EndTurn`, ~1/fin de tour ✘ |

Le jeu qui a produit ce batch émettait donc un `GroupType` à **102 membres** : un build
**antérieur aux deux builds versionnés**. Ses `group_name` stockés sont **cohérents avec leur
émetteur** — et la table de ce build n'est pas dans `data/symbols/`.

### Décision : ne rien rétro-corriger, et rendre la question décidable

1. **`step_name` : rien à corriger.** Le décoder avec `rnca9r7q6c` renommerait 52 842 lignes vers
   le pas **voisin** — exactement la faute que #254b-b a corrigée côté code. La vue
   `v_damage_tree` filtre `step_name = 'UnitDamaged'` (5 213 lignes) : `UnitDamaged` vaut 4 sur
   les deux builds versionnés, donc la vue tient — mais tout le reste de la colonne serait
   détruit.
2. **`group_name` : rien à corriger non plus.** Les 2 099 lignes « fausses » le sont uniquement
   si on les lit avec la table du build courant. Pour leur émetteur, elles sont justes.
3. **Les 5 colonnes `*_name` d'`enum_maps` : 0 ligne fausse**, sur les deux builds — les valeurs
   réellement émises tombent dans la partie stable de chaque enum.
4. **Le vrai défaut n'est dans aucune colonne `*_name`** : c'est que rien en base ne dit **quel
   build a émis les ordinaux**. C'est ce qui rend toute rétro-correction indécidable, et c'est ça
   qui est réparé (§5).

> **La leçon, et elle vaut au-delà de ce cas** : « la colonne est fausse » se vérifie contre le
> build **qui a écrit la ligne**, jamais contre le build courant. Ici, appliquer la correction
> demandée aurait cassé 61 785 + 38 440 lignes cohérentes. Le seul signal qui a résisté était
> sémantique — *un groupe qui contient 561 `StartTurn` n'est pas un `RarityCapTransform`* — et il
> a fallu le chercher **après** qu'une première inférence (la coïncidence à 100 % avec
> `gqfc5mff6c`) eut donné une réponse plausible et incomplète.

## 5. `batch.game_hash` — la donnée qui manquait

`rl_collect_batch` renseignait `game_hash = ents[0].name`, le **premier répertoire** de
`%LOCALAPPDATA%\tacticus\games` par ordre de listage. Sur cette machine c'est `.temp`, un
répertoire de travail : l'unique ligne de `tacticus.batch` porte donc `game_hash = '.temp'`.

Corrigé : on retient le répertoire qui contient réellement `Tacticus.exe`, en ignorant les noms
commençant par un point ; **s'il y en a plusieurs, on laisse `NULL` et on le dit** — une valeur
fausse est pire que « inconnu », c'est tout le sujet de cette fiche.

La ligne existante n'est **pas** réécrite : son build est une **inférence** (§4), pas une
donnée, et transformer une inférence en donnée est précisément ce qui a créé le problème.

## 6. Validation

* `probe_275_enum_maps_drift.py` : 6/6 blocs `OK`, 0 collision, 0 nom à trancher.
* `scripts/python/tests/test_enum_maps_ratchet_offline.py` — **8 tests**, dont trois qui
  vérifient que le détecteur **mord** (membre retiré / ajouté / **réattribué**) et un qui exige
  qu'un alias de valeur ne soit **pas** compté comme dérive. Contre-épreuve jouée : réintroduire
  `59: 'NormalAttack_AtomicDamage'` dans le fichier fait tomber 2 tests avec le diagnostic exact ;
  restauration → vert.
* **Confrontation LIVE** (`probe_275 --live`, session 27, lecture seule — aucun inject) : le RPC
  `dumpEnum` lit les enums **dans le processus du jeu**, source indépendante d'`enums.tsv`. Les
  **six** coïncident exactement — 629 / 260 / 476 / 24 / 9 / 104, `0` valeur manquante, `0` en
  trop, `0` nom divergent. C'est aussi ce qui périme le commentaire
  `1551: 'RedRampage'  # absent du tsv` : le tsv et le live sont d'accord à 100 %.
* Recoupement croisé : `enum_maps.GROUP_TYPE` et `stream_events.group_name` — **deux lectures
  indépendantes** de la même table versionnée, par deux chemins de code — rendent maintenant le
  même nom sur les **104** membres. C'est ce recoupement qui manquait : `rl_collect_batch`
  résolvait par les deux voies à la fois, l'une juste et l'autre fausse, sans que rien ne les
  confronte.
* Consommateurs, avant/après :
  * `audit_passive_ability_coverage.enum_qualification` : `none` **5 → 0**. Cinq passifs du parc
    que le dépôt ne savait pas qualifier entrent en `triggered` — `IconOfObstinacy` (1552),
    `ModifiedExoarmour` (1529), `MyWillBeDoneOverlord` (1556), `PropheticSentinel` (1543),
    `WhisperingWeb` (1554). **0 passif perdu.**
  * `channels()` : les **123** clés de `EFFECT_CLASSES` résolvent avant **et** après, avec
    **0 id changé** — aucun canal `G` ne bouge.
  * `state_bridge` : reverse `ACTIVE_ABILITY_TYPE` inchangé (260 noms).
* `pytest tests/test_enum_maps_ratchet_offline.py tests/test_stream_events_offline.py
  tests/test_step_ordinal_ratchet_offline.py` → **32 passed**.

## 7. Ce qui n'est PAS couvert

* **Les mirrors `IntEnum` portent la MÊME dérive**, mesurée par l'étape 4 du probe :
  `engine/entities/effect_type.py` (682→629 : 2 renumérotés, 73 absents, 20 manquants) et
  `engine/entities/triggered_ability_type.py` (574→476 : 107 absents, 9 manquants).
  `damage_profile_type.py` et `active_ability_type.py` sont sains. **Hors périmètre de ce cas**
  (qui vise `enum_maps.py`) → backlog. Le travail y est déjà chiffré et le risque **mesuré à
  zéro** : `0` usage `EffectType.<membre mort>` / `TriggeredAbilityType.<membre mort>` hors
  artefacts générés. Tant que ce n'est pas fait, le dépôt porte deux tables du même enum qui se
  contredisent — la contradiction est désormais **visible** (étape 4 du probe) au lieu d'être
  muette.
* **`GROUP_TYPE` n'a plus aucun consommateur** depuis #254b-b (`rl_collect_batch._group_name`
  passe par `stream_events`). Il est régénéré quand même — une table qu'on garde est une table
  qu'on régénère — et son en-tête le dit désormais dans le fichier. Le **supprimer** serait
  défendable ; ce n'est pas tranché ici.
* **Les tables SQL de référence** (`ref_triggered_ability`, `ref_effect` dans `006`, et les
  backfills correspondants de `013`) recopient elles aussi `TriggeredAbilityType` / `EffectType`.
  Non mesurées ici. `regen_active_ability_tables.py` couvre déjà le volet `ActiveAbilityType` des
  deux fichiers ; le pendant pour les deux autres enums reste à faire.
* **Aucune bataille n'a été montée.** Ce cas ne porte aucune mécanique : il n'y a rien à
  confronter en runner, et la seule confrontation qui a du sens (les enums tels que le jeu les
  porte) a été faite par `dumpEnum` en lecture seule (§6). Un scénario de généralisation en
  `rl_duel build` n'aurait mesuré que l'ingest RL, dont la chaîne `*_name` est déjà vérifiée
  ligne à ligne sur les 61 785 events en base (§4).
* **La ligne `batch_id=1` garde `game_hash = '.temp'`** : le correctif ne vaut que pour les
  batches à venir. La réécrire demanderait d'inscrire une inférence comme donnée (§5).
