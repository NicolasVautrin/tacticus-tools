# case-10028 — quatre cliquets d'ATTESTATION rouges, **trois** causes, et une qui n'est pas celle qu'on attendait

`#10028`. Quatre fichiers non-VERT sur `master` (`8b2a2e35`, build `t6dpr4k06g`), tous de la même
famille : l'attestation d'un symbole, d'un ordinal ou d'une annotation **contre le binaire**.
Verdict d'ensemble : **aucun n'accusait le port**. Deux des quatre partagent une cause, et ce
n'est **pas** celle que la consigne pointait.

| fichier | avant | après | verdict |
|---|---|---|---|
| `tests/engine/test_477r24_phase_attribution_offline.py` | 1 failed / 5 passed | **6 passed** | **le cliquet a RAISON** |
| `tests/test_337_dsl_triggers_attestation_offline.py` | 1 failed / 10 passed | **11 passed** | **le cliquet a RAISON** (rouge CUMULATIF de 3 PR) |
| `tests/engine/test_519_comptes_derives_offline.py` | 1 failed / 9 passed | **10 passed** | **INVENTAIRE FAUX** |
| `tests/test_1031_appariements_de_sondes_offline.py` | 3 failed / 22 passed | **25 passed** | **PRÉMISSE EXPIRÉE** |

---

## 0. La cause commune annoncée — **NON**, et c'est un résultat

La consigne pointait le vice de `#10026` : *« un même nom de symbole peut porter PLUSIEURS
adresses »* (`ghidra/functions.tsv`, **5 341 noms sur 145 703** à plusieurs VA, re-mesuré ici).
Il **ne s'applique à aucun des quatre** :

* `test_337` porte bien sur la famille `DSLTriggers`, mais son inventaire passe par
  `probe_326_dsl_primitive_inventory`, qui compte **déjà** les surcharges (`overloads_frida`,
  `overloads_ghidra`). Les trois primitives en cause ont **1 seule VA** chacune, vérifié :
  `$$IsInTeam` `refcount 12`, `$$IsSpawnTile` `6`, `$$IsPartialAttackAbility` `3`, **une adresse
  chacune** ;
* `477r24`, `519` et `1031` ne résolvent aucun symbole en adresse — ils travaillent sur des
  **ordinaux d'enum** et sur du **texte**.

**En revanche, deux des quatre partagent une AUTRE cause commune** (§3), et le résidu `#10026-r1`
est fermé ici parce que c'est la **même maladie sur un autre axe** : un helper recopié (§5).

---

## 1. `477r24` — le cliquet a RAISON : deux ordinaux de phase écrits nus

    scripts/python/engine/runner/operations/triggers/dispatch/damage_events.py:71
    scripts/python/tests/engine/runner/test_443r2b2_post_damage_taken_offline.py:76
      ordinal NU 0xe (attendu : PhaseType.ProcessDamageEvents /*0xe*/)

Confirmé au décompilé — `IdunBattle.Messages.InputMessageProcessor$$ProcessDamageEvents`, relu
verbatim sur `t6dpr4k06g` :

    q = matchState.<slot 7 = GetDamageEvents>()
    if (q.Count > 0)
        RunPhase(this, 0xe, <ProcessDamageEvents>b__0, isInternalPhase: 1, 0)

et `IdunBattle.Core.PhaseType` porte `14 = ProcessDamageEvents`. Les deux citations sont **nommées**,
et l'ordinal **ÉCRIT** entre dans `ORDINAUX_ECRITS` — le cran que `probe_313` ne peut pas rendre
(il redevient vert dès qu'on régénère le mirror après un renumérotage).

### Un TROISIÈME site, que le recenseur ne voyait pas — résidu `#10028-r1`

Le même fichier écrivait, six lignes plus haut, `RunPhase(PhaseType 0xe, ...)` — **sans point**.
`RE_ORDINAL` ne matche pas (ce n'est pas un nombre seul), `RE_MEMBRE` cherche `PhaseType\.` et ne
matche pas non plus : le site est **ignoré**, ni nommé ni signalé. Il est mis à la forme canonique
ici, mais **le trou du recenseur reste** : toute écriture `PhaseType <n>` est invisible de l'étape 2.
Un critère qui exige un `PhaseType.` sur la ligne est aveugle à la forme sans point, qui *nomme*
pourtant l'enum.

---

## 2. `337` — le cliquet a RAISON, et le rouge est **CUMULATIF**

Trois primitives revenues en `CITE_A_QUALIFIER` : `IsInTeam`, `IsPartialAttackAbility`,
`IsSpawnTile`. `CITE_A_QUALIFIER` n'est pas une mesure — c'est l'aveu que l'heuristique ne sait pas
attribuer.

**Mécanisme, mesuré** : une tranche CITE le symbole `DSLTriggers$$<nom>` dans `engine/**`, ce qui
fait basculer l'heuristique de `NON_PORTE` (aucune citation) vers `CITE_A_QUALIFIER` dès lors
qu'aucun **porteur plausible** ne se présente — le porteur devant contenir le nom de la primitive
dans sa `class`/`def` englobante ou dans le nom de fichier. Mesure des six sites : `owned = False`
partout.

| primitive | site de citation | porteur | commit | PR |
|---|---|---|---|---|
| `IsInTeam` | `power_up_spawn.py:227` | `_ActeurDansLaTeam` | `8ff8c672` (#10004) | #1104 |
| `IsPartialAttackAbility` | `static_battle_rules.py:130` | `ability_is_partial_attack` | `78a604de` | #1112 |
| `IsSpawnTile` | `status.py:45,50,402` + `triggers.py:993` | `<module>`, `DespoiledGroundEffect`, `HasEffect` | `94f84dab` | #1123 |

**TROIS PR INDÉPENDANTES.** Aucune n'a vu le rouge qu'elle creusait : le fichier ne rougit qu'à
leur **somme**, et c'est la troisième arrivée qui a fait tomber le test. C'est la forme la plus
coûteuse de ce gisement — le responsable n'est identifiable qu'après coup.

### Les trois corps, LUS (décompilé = vérité)

    DSLTriggers$$IsInTeam(unit, team)
        -> new IdunBattle.Entities.Triggers.IsInTeamTrigger(state, unit, team)

    DSLTriggers$$IsSpawnTile(selector)
        -> AmountIsGreaterAbilityTrigger( DSLSelectors$$SpawnTiles(selector), <minAmount> )

    DSLTriggers$$IsPartialAttackAbility(ability)
        -> new <AbilityIsPartialAttackAbilityTrigger>(ability, 0)

⚠ Le ctor du troisième est rendu par ghidra sous le nom
`UnityEngine_Scripting_RequiredByNativeCodeAttribute___ctor` — **mislabel gshared**. C'est la
STRUCTURE de l'appel qui tranche, jamais le nom (CLAUDE.md).

⚠ **`IsSpawnTile` : LE NOM MENT.** `IdunBattle.Entities.Selectors.SpawnTilesSelector$$Select`
filtre par `IdunBattle.Entities.TileExtensions$$IsTemporary` (= `TileComponent+0x2c`) : le prédicat
est « la tuile est TEMPORAIRE » (posée EN COMBAT), pas « la tuile appartient à un `SpawnPointGroup`
du board ». Lire le nom au lieu du corps aurait fait porter une appartenance géométrique qui
n'existe pas.

Les trois entrent au TSV en `PORTE_HORS_FACADE`, ancrées sur leur mirror.

### Le cran ajouté — et il a fallu TROIS mutations pour établir qu'il n'est pas redondant

| mutation sur `IsSpawnTile` | cran qui mord |
|---|---|
| (a) ligne du TSV **retirée** | `a_qualifier` (retour à `CITE_A_QUALIFIER`) |
| (b) verdict **dégradé en `NON_PORTE`** | `lus` (son égalité est STRICTE) |
| (c) ligne retirée **ET** citation retirée du moteur | **le cran neuf, SEUL** |

(c) est le régime dangereux : sans attestation **et** sans citation, le verdict est `NON_PORTE`
**sans** le préfixe `attestation:`, donc il sort de `lus` **et** d'`a_qualifier` — le fichier
redeviendrait **VERT** en ayant perdu l'attestation d'un port qui, lui, existe toujours.

⚠ **Deux mesures fausses avant la bonne, et la même cause les deux fois.** Le premier essai
concluait « le cran n'est pas discriminant » et le deuxième « il est inerte » — parce que le
détecteur cherchait un littéral d'assertion dans la sortie **entière** de pytest, qui **recopie le
source du test** dans le traceback. Toute chaîne écrite dans le test s'y trouve donc toujours. La
mesure ne vaut qu'en ne lisant que les lignes `E ` du traceback.

---

## 3. `519` et `1031` — LA cause commune : la référence élisait le build où il n'y a RIEN à voir

Les deux rouges tiennent au même fait : **`previous_build()` (= `rnca9r7q6c`) est IDENTIQUE au
build courant sur les quatre enums**. Le seul renumérotage jamais mesuré est
`gqfc5mff6c -> rnca9r7q6c` (171 membres déplacés). `#10023` avait déjà réparé ce vice pour
`probe_283` et `test_enum_ordinal_ratchet_offline.py` en passant à la **mémoire archivée** (union
sur toutes les archives). Ces deux-là étaient **restés en arrière**.

### `519` — INVENTAIRE FAUX : l'heuristique était structurellement biaisée

`probe_519_ordinaux_decales.builds()` élisait son build de référence par
« celui qui partage le plus de **NOMS** avec le courant ». Ce critère **récompense la
ressemblance** : plus deux tables se ressemblent, plus le score est haut. Il converge donc, par
construction, vers le build sur lequel il n'y a **rien** à voir.

    UtilityType, contre t6dpr4k06g :   rnca9r7q6c -> 0 membre décalé
                                       gqfc5mff6c -> 73 membres décalés
    et l'heuristique élisait rnca9r7q6c.

Le détecteur était **VACANT**, donc son voisin (`test_aucun_ordinal_cite_ne_vient_du_build_precedent`)
était un **VERT VIDE** — et c'est exactement ce que le test de non-vide a dit en rouge.

Après réparation : **73 membres décalés**, **0 citation périmée** dans `engine/**`.

⚠ **Le passage à l'union change le TYPE de `vieux`** (`{nom: frozenset}` au lieu de
`{nom: int}`), et c'est un piège : écrite à la main côté test, la comparaison `vieux[n] != neuf[n]`
serait **toujours vraie** (un ensemble n'est jamais égal à un entier), donc le test serait **VERT
ET VACANT** — l'état même qu'il existe pour interdire. Deux parades, les deux posées :
`membres_decales()` est un **foyer partagé** entre le probe et son test, et une **borne haute**
(`len(decales) < len(neuf)`) rougit sur exactement cette panne.

### `1031` — PRÉMISSE EXPIRÉE : le test dupliquait le câblage qu'il garde

`_ann` reconstruisait `old` depuis `previous_build()`, alors que le foyer de production
(`step_on`) lit `memoire_archivee` depuis `#10023`. `annotation_de_ligne` ne pouvait donc plus
rendre `perimee`, et les trois étages 2 tombaient sur `nue`. C'est mot pour mot la leçon d'`_olds()`
(`#10023`) : **un cliquet qui reconstruit ce qu'il garde ne garde pas ce qui tourne.**

S'y ajoutait le figeage des couples (`PreUnitAbility`/`0x2b`, `0x34`), qui suivent le **calendrier**
et non la table. Ils sont dérivés du foyer `temoins_de_decalage` (§5).

### Contre-épreuves — les quatre rouges se REPRODUISENT à volonté

| mutation | attendu | mesuré |
|---|---|---|
| `memoire_archivee` rabattue sur la table du seul `previous_build()` | les 4 rouges reviennent | **4 rouges** (1 en `519`, 3 en `1031`) |
| `membres_decales` rabattue sur le critère vacant (`frozenset != int`) | la borne HAUTE mord | **rouge : « rend TOUS les 83 membres »** |
| aucune mutation (témoin, avant **et** après) | tout vert | **tout vert** |

Sous la première mutation, `1031` rougit désormais **dans `temoins_de_decalage`** (« moins de 1
témoin de décalage pour `PreUnitAbility` ») et non sur un verdict faux : le foyer **dit que la
mesure est impossible** au lieu de laisser passer un résultat.

---

## 4. Le foyer des témoins — `probe_283.temoins_de_decalage`

`_temoins` vivait dans `tests/test_enum_ordinal_ratchet_offline.py`, un fichier de test que
personne n'importe ; `test_1031` en portait une version **figée**. La réparation de `#10023` ne
pouvait donc pas l'atteindre. Le corps a migré dans le probe ; `_temoins` n'est plus qu'un alias, et
`test_enum_ordinal_ratchet_offline.py` reste **25 passed** avant comme après.

Le paramètre `membre=` sert les fixtures qui doivent rester **fidèles au site réel** qu'elles
reproduisent : le NOM est celui que l'auteur a écrit au site, seuls ses ORDINAUX sont dérivés.

---

## 5. `#10026-r1` FERMÉ — trois copies de `_va_of`, un foyer

Même maladie, autre axe. `#10026` avait réparé le helper d'un fichier et nommé le résidu :
`_va_of` était recopié dans `test_929_savage_killer_offline.py` et
`test_936r1_expiry_removal_offline.py`, verts **par chance** (leurs symboles n'ont qu'une VA sur ce
build). Foyer : `scripts/python/pe_symboles.py` — `build_avec_dll`, `chemin_dll`, `vas_du_symbole`,
`va_du_symbole` (qui **REFUSE** un nom partagé), `lire_a_la_va`, `noms_a_plusieurs_va`,
`IMAGE_BASE`. **42 passed** sur les trois fichiers.

⚠ **Les délégations sont des WRAPPERS, pas des liaisons.** Le premier jet écrivait
`_va_of = PE.va_du_symbole` — la forme **A**, qui gèle la fonction à l'import et **ne mord pas**
sous `monkeypatch.setattr("pe_symboles.va_du_symbole", …)`. Le commentaire posé annonçait pourtant
« forme B » : une affirmation fausse dans un commentaire de cliquet vaut moins que rien.

---

## 6. Ce que cette tranche NE couvre PAS

* **Aucun fichier `engine/**` n'a changé de comportement.** Les seules éditions y sont deux lignes
  de **docstring** (`damage_events.py`) : `RunPhase(0xe)` → `RunPhase(PhaseType.ProcessDamageEvents
  /*0xe*/)`. Les trois verdicts de port attestés en §2 sont **confirmés**, pas révisés.
* **Rien n'est confronté LIVE** — les quatre fichiers sont offline par construction.
* **Le trou du recenseur `477r24`** (la forme `PhaseType <n>` sans point) reste ouvert : résidu
  `#10028-r1`.
* **`scripts/cliquets-cache/probe_326_inventaire_natif.tsv` est PÉRIMÉ sur `master`** et n'est pas
  régénéré ici : son `contexte` vaut `4f819e65…` alors que le sha courant de
  `probe_326_dsl_primitive_inventory.py` — que cette tranche n'a **pas** touché — est `b354edc8…`.
  Le cache ne sert donc jamais. Le régénérer serait un débordement et un conflit garanti. Résidu
  `#10028-r2`.
* **Les deux caches de `probe_283`** (`step_exec`, `step_mirror`) SONT régénérés : leur contexte est
  le sha du probe, que la tranche modifie. C'est une conséquence directe, pas un débordement.
* **La couverture d'attestation `DSLFormulas` reste PARTIELLE** et sans cliquet de complétude,
  comme `PERIMETRE_ATTESTATIONS` le déclare — inchangé.
* **Le gisement de `337` n'est pas fermé, il est ratcheté** : chaque tranche qui cite une primitive
  `DSLTriggers` sans l'attester le rouvre. C'est notre propre cadence qui l'alimente, et le fichier
  ne rougit qu'à la **somme** des tranches — donc jamais dans la PR qui le creuse.
