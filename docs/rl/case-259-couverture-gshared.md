# #259 — la chaîne de symboles ne nomme plus aucun générique pleinement partagé

> **CLOS (2026-07-29), par DEUX voies complémentaires** : (a) `#259-a` restaure la **table**
> (Il2CppDumper, 0 → 4 874) ; (c) `#259-b` prouve la **résolution runtime** et supprime deux
> adresses en dur de `scorer-damage-trace.ts`. La voie (b) est réfutée. Détail : §4.
>
> Re-dériver les chiffres plutôt que les citer : `python scripts/python/probe_259_gshared_coverage.py`
> (couverture de table) et `python scripts/python/probe_262_gshared_runtime.py` (résolution runtime).
> Garde permanente : axe 5 de `scripts/python/symbols_sync.py` + `tests/test_symbols_coverage_guard_offline.py`.
>
> **Suite** : le retrait de l'entrée `PERTES_CONNUES` par `#259-a` a laissé quatre tests rouges
> derrière lui — ils prélevaient leur fixture sur ce registre, dont l'état nominal est **vide**.
> Diagnostic, correction et validation adversariale : [`case-282`](case-282-pertes-connues-vide.md).

## 1. Le fait

| table | `__Il2CppFullySharedGeneric*` |
|---|---|
| `data/symbols/gqfc5mff6c/ghidra/functions.tsv` | **4 882** (dont 4 015 `...GenericType`, 867 `...GenericStructType`) |
| `data/symbols/rnca9r7q6c/ghidra/functions.tsv` | **0** |
| `frida/methods.tsv`, **les deux builds** | **0** |

La troisième ligne tranche la cause : ces noms n'ont **jamais** transité par la chaîne Frida. Ils
venaient du seul applier legacy `GhidraApplyIl2CppNamesWin.java`, qui lisait le `script.json`
d'**Il2CppDumper v39** — supprimé le 2026-07-25 (`8e591496`). La table de `gqfc5mff6c` gardait ses
noms parce que le **projet Ghidra** avait été symbolisé par lui ; la première re-symbolisation
complète (2026-07-29) les a fait tomber à 0, silencieusement.

Même cause racine que l'incident de forme du même jour — un maillon remplacé sans rejouer son aval —
mais sur l'axe **couverture** au lieu de l'axe **forme**.

## 2. Ce que chaque chaîne sait nommer, mesuré

`probe_259` étape 3 recalcule `GhidraApplyIl2CppSymbols.canonicalName` à l'identique et attribue
chaque symbole de la table Ghidra.

| | `gqfc5mff6c` (chaîne legacy) | `rnca9r7q6c` (chaîne Frida) |
|---|---|---|
| symboles Ghidra | 143 030 | 154 176 |
| méthodes Frida | 121 501 | 124 719 |
| nom Ghidra == `canonicalName(frida)` | 110 691 (91,1 %) | 124 719 (**100 %**) |
| nom Ghidra différent (resté `FUN_`) | 3 165 | 0 |
| méthode Frida sans fonction Ghidra | 7 645 | 0 |
| **symboles nommés HORS chaîne Frida** | **6 622** | **741** |
| — dont pleinement partagés | 4 862 | 0 |
| — dont autres (gshared classique `<object>`, thunks, runtime C++) | 1 760 | 741 |

**La chaîne legacy nommait 5 881 symboles de plus**, dont **4 862 corps pleinement partagés**.
Les 3 165 « restés `FUN_` » côté gqfc sont l'inverse : des adresses que la chaîne Frida nomme et
qu'Il2CppDumper ne nommait pas. Les deux chaînes sont **complémentaires**, pas redondantes.

**Impact concret sur le dépôt** : 31 citations `$$` distinctes portent le marqueur
`__Il2CppFullySharedGeneric` (`scripts/python/engine`, `docs`, `frida/hooks`). Elles sont **toutes**
dans `IdunBattle.AI.Playbook` / `IdunBattle.AI.BucketSystem` — exactement la couche de décision que
la campagne de portage instrumente. Deux d'entre elles bloquent #257, qui bloque #258 :

```
IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility
IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromTilePrediction
```

## 3. Pourquoi la chaîne Frida ne peut PAS les produire (RE)

Le dump (`scripts/frida/dump-il2cpp-full.js`) énumère les classes par `il2cpp_image_get_class`, donc
les **définitions** génériques — elles sont bien présentes dans `classes.tsv`
(`IdunBattle.AI.Playbook.ComparablePlaybook`1`, `Playbook`1`, `Bucket`1`) — puis leurs méthodes par
`il2cpp_class_get_methods`, en gardant le `methodPointer` (premier champ du `MethodInfo`).

Sur 805 définitions génériques du build courant, **20 seulement** ont au moins une méthode avec un
`methodPointer` non nul. Pour la famille qui nous intéresse, il y en a exactement deux :
`IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1$$Init` et
`IdunBattle.AI.Playbook.TriggeredAbilityNonOwnerPlaybook`1$$Init`. **Ce ne sont pas les corps** :

```c
// IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1$$Init  (décompilé, build courant)
local_48 = abilitiesDatabase; local_40 = query; local_38 = dsl; /* ... */
uVar1 = (*(code *)in_stack_00000050[2])(*in_stack_00000050, in_stack_00000050, this, &local_48, 0);
return uVar1;
```

Les arguments sont recopiés dans un tampon de pile, puis l'appel part vers `methodInfo[2]` —
`MethodInfo.invoker_method` (+0x10) — avec `methodInfo[0]` (`methodPointer`) en premier argument.
C'est le **thunk d'invocation** d'une définition générique, pas l'implémentation. Structure
identique sur `TriggeredAbilityNonOwnerPlaybook`1$$Init`. Confirmation par les adresses : sur
`gqfc5mff6c`, le thunk `Init` est à `FUN_18011fd60` (Frida) tandis que le corps partagé est nommé
`TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$Init` — **deux adresses
distinctes**.

⇒ Étendre l'applier ou le dump pour lire les `methodPointer` des **définitions** génériques rend
des **thunks**, jamais les corps. Ce n'est pas la voie.

## 4. Les trois voies, ce que chacune rend

| voie | rend | sur les 2 cibles #257 | coût / risque |
|---|---|---|---|
| **(a) passe Il2CppDumper v39 en amont de l'applier** — **LIVRÉE (#259-a)** | **5 899 renommages** appliqués, famille GSHARED 0 → 4 874 | **OUI** — les deux cibles sont redevenues citables | une fenêtre de re-symbolisation Ghidra par build |
| **(b) dériver les corps depuis les `methodPointer` des classes génériques** | **rien** — le `methodPointer` d'une **définition** est un thunk d'invocation (§3) | non | **RÉFUTÉE** |
| **(c) résolution runtime côté Frida** — **PROUVÉE ET APPLIQUÉE (#259-b)** | une **adresse par cible** au moment du hook ; aucun symbole à la table | **OUI**, mesuré (§5.2) | supprime la RVA en dur au lieu de la transcrire |

**Les voies (a) et (c) ne se remplacent pas** : (a) rend la table **lisible** (RE offline, `whereis`,
citations par symbole) ; (c) rend un hook **indépendant du build**. Un hook qui résout au runtime
n'a plus besoin de la table — mais la table reste ce qui permet de LIRE le décompilé.

**Voie (a) — précision qui change son évaluation.** L'applier legacy ne renommait **que** les
fonctions encore appelées `FUN_*` :

```java
if (!fn.getName().startsWith("FUN_")) { alreadyNamed++; continue; }
```

C'est donc un **complément pur** : appliqué APRÈS `GhidraApplyIl2CppSymbols`, il ne peut pas écraser
un nom de la chaîne Frida. Ce n'est pas sa présence qui a causé l'incident de forme du 2026-07-29,
c'est son **retrait sans rejeu de l'aval** — et la forme `$$` qu'il portait est désormais produite
par `canonicalName` (accord 100 % mesuré sur le build courant, §2). L'ordre correct est :
`GhidraApplyIl2CppSymbols` (nomme, type, signe) **puis** l'applier legacy (bouche les `FUN_`).

**Le `MethodInfo` d'une instance INFLATÉE porte bien le corps pleinement partagé** — mesuré, §5.2.
C'est ce qui sépare (b) de (c) : une **définition** générique n'expose qu'un thunk, une **instance**
expose le corps. Les deux voies partaient du même mécanisme, seule la seconde l'attaque du bon côté.

## 5. Protocole de preuve (à jouer dans une fenêtre dédiée)

### 5.1 Voie (a) — coût mesurable en une passe

1. Ré-acquérir Il2CppDumper v39 et le passer sur le `GameAssembly.dll` du build **installé**
   (`data/symbols/CURRENT`) → `script.json`.
2. Vérifier **avant tout** que `script.json` contient des entrées `__Il2CppFullySharedGeneric*`
   (`grep -c`). Si l'outil ne supporte pas la version de métadonnées de ce build, la voie s'arrête
   là, sans avoir touché au projet Ghidra.
3. Restaurer `GhidraApplyIl2CppNamesWin.java` (`git show 8e591496^:scripts/ghidra/GhidraApplyIl2CppNamesWin.java`),
   en lui ajoutant la **garde de provenance** de `GhidraApplyIl2CppSymbols` (sélection du build par
   sha256 du binaire chargé) : le legacy ne l'avait pas, et son chemin d'entrée était en dur.
4. Rejouer la chaîne complète sur un projet Ghidra : `GhidraApplyIl2CppSymbols` **puis** le legacy.
5. `python scripts/python/ghidra_symbols.py dump` → la table neuve.
6. Critère d'acceptation, sans interprétation : `probe_259_gshared_coverage.py` **sort 0**
   (les deux cibles de #257 résolvent) et `probe_257_scorer_rva_migration.py` passe de `perdu=5`
   à `perdu=3` (les trois `FUN_`/`DAT_` restants sont légitimes, cf. sa propre sortie).

⛔ Ne pas jouer 3–5 sur le projet Ghidra en place tant qu'un agent RE travaille : une
re-symbolisation casse sa surface d'analyse sans qu'il le voie.

### 5.2 Voie (c) — MESURÉE le 2026-07-29, elle est vivante

RPC `resolveMethodPtr` (`frida/hooks/features/introspect.ts`) : remonte `class_get_parent` depuis
une classe de playbook **concrète** et rend, par niveau, le pointeur d'entrée de la méthode nommée.
Re-dérivation : `python scripts/python/probe_262_gshared_runtime.py`.

```
IdunBattle.AI.Playbook.MurderousSwingPlaybook::CalculateActionUtility
  [0] MurderousSwingPlaybook            (pas de methode de ce nom)
  [1] ComparablePlaybook`1  params=6
       entry   -> ...ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility
       invoker -> FUN_180079f90
```

Trois faits, aucun déduit :

1. **`entry` tombe à l'offset 0 du corps partagé** — la sonde ne compare à aucune constante, elle
   demande à `ghidra/functions.tsv` qui habite l'adresse rendue.
2. **La même adresse pour les 4 classes concrètes** essayées (`MurderousSwing`, `BlightGrenades`,
   `EntropyCannons`, `LightOfSanguinius`) : c'est bien UN corps partagé, pas du code par
   instanciation.
3. **`findMethod` sur la classe CONCRÈTE échoue** (profondeur 0 : « pas de méthode de ce nom ») —
   elle ne remonte pas les parents. Il faut viser le **parent**, l'instance inflatée. C'est le seul
   piège de la recette.

**Appliqué** : `CalculateActionUtility` et `CalculateUtilityFromTilePrediction` n'ont plus d'adresse
en dur dans `scorer-damage-trace.ts` — `resolveSharedPlaybookBody` les résout au runtime. Validé
bout-en-bout (trace armée, 4 tours d'IA : `scorerUtilTraceDump` = 48, `scorerTileTermTraceDump` = 48).

⚠ **Ne pas généraliser aux 13 autres cibles de #257.** Ce sont des **itérateurs** (`<...>d__N.MoveNext`)
et des corps sans classe porteuse atteignable par la chaîne de parents : la recette ne s'y applique
pas telle quelle. Chaque cible se re-mesure.

## 6. La garde livrée : axe 5 de `symbols_sync.py`

Les quatre axes existants vérifient la **provenance** (sha256, cohérence des estampilles, build
servi par ghidra-mcp) ou la **forme**. Aucun ne compte le **contenu** — c'est exactement pour ça
qu'une perte de 4 882 symboles est passée sans un mot, tous les axes au vert.

**Maille.** La famille `GSHARED` est définie sur le **mécanisme** (`__Il2CppFullySharedGeneric`),
pas sur un namespace, et testée **avant** lui. À la maille namespace la perte est invisible :
`IdunBattle.AI.Playbook` ne bouge que de 2 122 → 2 083 (−1,8 %) alors que des centaines de corps y
ont disparu. Les placeholders (`FUN_`/`DAT_`/`PTR_`) forment leur propre famille et ne sont **jamais**
alertés : une baisse y est une bonne nouvelle.

**Seuil = 0,60, plancher = 100 symboles.** Il est dimensionné sur le bruit inter-build **mesuré sur
les tables Frida** — même outil des deux côtés, donc churn de mise à jour pur, sans contamination
par le changement d'outillage (le diff des deux tables Ghidra, lui, mélange les deux et ne peut pas
servir de calibrage) :

```
gqfc5mff6c -> rnca9r7q6c, frida/methods.tsv
  26 familles >= 100 methodes : ratio min 1,000 ; max 1,292 ; AUCUNE famille disparue
  aucune famille >= 100 n'a PERDU un seul membre
  526 familles < 100 : ratio 0,750 a 2,000  -> exclues (bruit relatif eleve)
```

Côté Ghidra (contaminé), la pire famille légitime tombe à 0,863 (`BaseTest`, 124 → 107 — artefact
d'outillage : la table Frida donne 107 → 107). Le seuil laisse donc 0,26 de marge sous la pire
valeur légitime observée et 0,60 au-dessus de la panne (0,000).

**Registre des pertes connues.** Une perte documentée est **imprimée avec son motif** mais ne fait
pas échouer la garde — une garde qui hurle à chaque démarrage s'ignore aussi sûrement qu'une garde
absente. La clé est la **transition** `(famille, build de référence, build courant)`, ce qui lui
donne trois propriétés : elle ne tait que cette perte-là, elle re-déclenche si la même famille
retombe sur une **autre** transition, et elle s'auto-périme à la mise à jour suivante (la famille
sera à 0 des deux côtés, donc sous le plancher).

**Référence** = l'archive la plus **récemment dumpée**, ordonnée par le champ `generated=` de son
estampille de provenance — ni l'ordre alphabétique du hash (aucun sens chronologique) ni le mtime
(un checkout git le réécrit). Pas d'archive ⇒ axe **NON VÉRIFIÉ**, jamais un vert.

**Effet de bord utile** : une table en notation pointée (l'incident de forme) vide **toutes** les
familles `il2cpp:*` d'un coup — l'axe 5 l'attrape aussi, indépendamment de l'axe 4.

## 7. Ce qui n'est PAS prouvé

- **Que la recette de la voie (c) s'étend aux 13 autres cibles de #257.** Elle est démontrée sur
  deux méthodes atteignables par la chaîne de parents d'une classe concrète. Les itérateurs
  (`<...>d__N.MoveNext`) et les corps sans classe porteuse accessible n'ont pas ce chemin — chacun
  se re-mesure avec `probe_262_gshared_runtime.py`, aucun ne se déduit.
- **Que les 4 graines de `resolveSharedPlaybookBody` survivent au prochain build.** Elles sont
  choisies pour la redondance, pas garanties. Si les quatre disparaissent, le hook ne s'installe
  pas et le dit — c'est le comportement voulu, pas un cas pour ressortir une adresse en dur.
- **Que la voie (a) n'introduit aucune régression de forme.** Le raisonnement (complément pur,
  `FUN_*` seulement) est lu dans le source supprimé, pas rejoué. La garde qui le vérifierait existe
  désormais : l'axe 4 (forme) et l'axe 5 (couverture) encadrent la passe des deux côtés.
