# #477-r15-r1 — la table de LITTERAUX IL2CPP, et ce que `Source=` n'est pas

**Build** `rnca9r7q6c`. Mesure live session Frida **8** (1 runner monte et dispose), plus des
mesures offline. Code : `scripts/python/dump_string_literals.py` (producteur),
`scripts/python/string_literals.py` (lecteur). Table :
`data/symbols/rnca9r7q6c/metadata/string_literals.tsv`. Probe :
`probe_477r15r1_litteraux_source.py`. Cliquet :
`tests/engine/test_477r15r1_string_literals_offline.py`.

## Verdict en une ligne

La table demandee est livree et tient ses promesses verifiables — mais **la premisse du residu
est REFUTEE** : `Source=` n'est pas un handle de litteral, c'est un `Enum.ToString()`. Sur les
**8** `Source=` non vides d'un flux de deroule reel, **1** est un litteral et **8** sont des noms
de membres d'enum. La table qui les resout, `frida/enums.tsv`, **existait deja**, et le port les
rend **9/9** aujourd'hui, sans une ligne de code neuve.

## 1. Ce que le residu affirmait, et ce que la mesure dit

Le residu posait : « le `sourceId` est un handle de litteral, non resoluble statiquement ; le
meme mur bloquera tout `Source=` non vide (`AvalancheOfMuscle_ExtraDamage`,
`BlockEnteringUnits`...), c'est-a-dire la quasi-totalite du deroule ».

Les deux exemples cites etaient **reels** (mesures sur un flux), et **aucun des deux n'est un
litteral** — c'est la premiere mesure qu'a rendue la table, en cherchant ses propres cas d'usage.

Flux de deroule `C1_02`, seed 777, 7 tours IA : 29 111 octets, **79** lignes `Group=`, dont **55**
a `Source=` vide et **8** sources non vides distinctes.

| `Source=` observe | litteral IL2CPP | porteur(s) enum |
|---|---|---|
| `OnOnMeltaDamageAbility` | — | `TriggeredAbilityType` = 1211 |
| `Melta_ExtraDmg` | — | `EffectType` = 1297 |
| `SwampBlockMovement` | — | `TriggeredAbilityType` = 5 |
| `BlockEnteringUnits` | — | `EffectType` = 0 |
| `AvalancheOfMuscle` | — | `TriggeredAbilityType` = 1028 |
| `AvalancheOfMuscle_ExtraDamage` | — | `EffectType` = 1025 |
| `BigTarget` | — | `TriggeredAbilityType` = 1030 **et** `UnitTrait` = 1017 |
| `Loki_NormalAttack` | **OUI** (index 11682) | `ActiveAbilityType` = 69 |

**1 / 8 litteral, 8 / 8 membre d'enum.** `Source=` emprunte donc exactement le mecanisme deja
porte pour `Group=`, `Action=` et `Tag=` : `format_enum_value`, qui mirrore le fait que
`Enum.ToString()` de .NET rend le NOM quand la valeur est un membre. Mesure de bout en bout :
les **9** couples (nom, enum) sont rendus **a l'identique** par les mirrors Python existants —
lesquels sont deja tenus en bijection par `probe_313`.

### Le mur n'est pas la resolution : il est dans les PRODUCTEURS

Ce qui reste a la tranche D n'est pas de savoir **nommer** une source, mais de savoir **laquelle**
chaque `StartGroup` passe. C'est de la RE de producteurs, pas une table de symboles.

⚠ **Et le NOM ne designe pas l'enum** : `BigTarget` est porte par `TriggeredAbilityType` (1030)
**et** par `UnitTrait` (1017). Un comparateur qui resoudrait « par le nom » choisirait au hasard.
C'est la regle de qualification du `CLAUDE.md` (`ActiveAbilityType != TriggeredAbilityType !=
EffectType a id egal`), rencontree ici sur un cas reel, dans un echantillon de **huit**.

## 2. Ce que la table resout, elle

Elle n'est pas la voie de `Source=`, mais elle tient ce qui etait verifiable — et le residu
enoncait justement une **condition de retournement executable**.

- **Le handle du groupe `AddUnit` est la chaine VIDE, pas `null`.** `String.Format` rend le meme
  texte dans les deux cas : seule la lecture tranche. `AddUnitOperation$$Execute` charge
  **12** litteraux, dont exactement un vide.
- **Les CINQ litteraux du writer sont desormais LUS.** `case-477r15` §1 les declarait « MESURES,
  PAS LUS », faute de pouvoir lire une chaine .NET dans le PE ; la RE offline anterieure
  (`case-477` §10.7) en avait meme deduit « tabulations », ce qui etait faux. Ils se lisent, et
  chacun est attribue a **sa** methode par le scan :

  | methode native | litteral lu | constante du mirror |
  |---|---|---|
  | `StreamCache$$Log` / `$$AddToBatchedLog` / `$$Action` | `"    "` | `INDENT` |
  | `StreamCache$$StartGroup` | `"Group={0} Entity={1} Source={2} InitialTarget={3}\n"` | `FMT_GROUP` |
  | `StreamCache$$Action` | `"Action={0} Entity={1}\n"`, `"Tag={0}:{1}\n"` | `FMT_ACTION`, `FMT_TAG` |
  | `StreamCache$$FinishGroup` | `"Finish_Group\n"` | `FINISH_GROUP` |

  **5 / 5 concordants** avec les valeurs qui avaient ete mesurees sur le flux. Les deux canaux
  sont independants, donc leur accord confirme ; le cliquet le tient a chaque build.

## 3. La voie : trois candidates, mesurees

| voie | verdict |
|---|---|
| runtime `il2cpp_string_literal_*` (Frida) | exige un capteur neuf et une fenetre de reinjection. **Ne rend rien de plus.** |
| Il2CppDumper `stringliteral.json` | correct, mais sa sortie vit sous `logs/` (**gitignore**), et l'outil aussi. En dependre rendait la table non re-derivable la ou elle sert. |
| **offline et autonome** | les deux colonnes se lisent des fichiers **livres avec le jeu**. ~4 s. **Retenue.** |

### Le slot n'est PAS vide sur disque — c'est ce qui rend la voie autonome

« Les chaines ne sont pas dans le binaire » est vrai des **valeurs**, faux du **pont**. Le slot
porte STATIQUEMENT le token de metadata usage `(kind << 29) | (2 * index + 1)`, avec `kind == 5`
(`kIl2CppMetadataUsageStringLiteral`) ;
`il2cpp_codegen_initialize_runtime_metadata(&slot)` ne le remplace par le `String_t*` qu'au
demarrage. Un balayage des sections initialisees (u64 **alignes sur 8**, token dans une fenetre de
moins de 2^17 valeurs sur 2^64) le retrouve.

La relation vient de `probe_212_bc_key_literals.py`, qui l'avait calibree sur **9 ancres**. Elle
est **re-calibree ici sur les 30 367 references** d'Il2CppDumper : **0 slot manquant, 0 en trop,
0 valeur discordante**, en 2,6 s.

**Preuve que le changement de voie est value-preserving** : la table produite par balayage du PE
est **identique ligne pour ligne** a celle produite par jointure sur `stringliteral.json` — seules
les deux lignes d'en-tete different (horodatage, nom d'un champ). Et sans `stringliteral.json`, le
producteur rend la meme table, en **annoncant** que le controle croise n'a pas eu lieu.

## 4. La table

`data/symbols/<build>/metadata/string_literals.tsv` — troisieme famille, a cote de `frida/`
(dump du jeu qui tourne) et `ghidra/` (extrait de Ghidra). La famille porte le nom de sa
**source** : `global-metadata.dat`.

- **30 372** litteraux, **0 non decodable**. **30 367** portent un slot PE ; les **5** restants ne
  sont utilises par aucun site de code.
- 1,47 Mo, LF force par `.gitattributes` (le diff inter-build est le livrable).
- Format : provenance en ligne 1, en-tete en ligne 2, puis `index` / `rva` / valeur echappee
  `json.dumps` (reversible, ASCII pur — les litteraux portent des LF, des TAB et des caracteres
  de controle).

### La cle stable est la VALEUR — ni l'index, ni la RVA

La RVA est une adresse (elles changent a **100 %** entre builds) ; l'index est un rang d'emission
du compilateur, et la table **n'est pas triee** (verifie). Aucun des deux ne survit a une mise a
jour. La table est donc estampillee du sha256 **du PE ET du fichier de metadonnees** — ce sont
deux artefacts, et seule cette table depend du second — et le lecteur **leve** en cas d'ecart.

L'echappatoire `verifier=False` existe pour consulter un build archive ; elle ne ment pas :
l'objet porte `verifiee = False`.

## 5. Ce qui rend la mesure honnete

- **Le pont est confronte au binaire, pas cru.** Le scan des references RIP-relatives est ecrit
  ici et **independant de Ghidra** : sur `AddUnitOperation$$Execute` il retrouve exactement les
  **12** memes litteraux que `mcp__ghidra__decompile_function`. Ce n'est pas un desassembleur —
  il peut lire un motif a l'interieur d'une autre instruction ; c'est assume, car un faux positif
  rend une adresse qui n'est pas dans la table, donc la table le filtre, et rater une reference ne
  ferait que **sous-estimer**.
- **La contre-epreuve de la table.** « Toutes les valeurs observees sont dans la table » ne vaut
  rien si la table matche n'importe quoi : 30 372 chaines, ca finit par tout contenir. **200**
  valeurs mutees d'UN caractere, **0** retrouvee.
- **La contre-epreuve du cliquet.** Un test qui n'assertionne rien passe comme un test qui garde.
  **4 mutations** du writer (gabarit de tag, indentation par tabulation, fin de groupe, gabarit de
  groupe), **4 / 4 detectees**, avec un bras temoin vert et verification que chaque mutation a
  **mordu** avant de conclure.
- **Le refus inter-build est teste**, sur une table fabriquee : une garde qui ne refuse jamais rien
  est un inventaire deguise. Et ce test-la ne depend ni du binaire installe ni de la table
  versionnee — le fichier a donc toujours au moins une assertion evaluee (#455).

## 6. L'outillage qui existait deja, et pourquoi il ne suffisait pas

Le residu disait « aucune table dans `data/symbols/` ». C'etait exact, mais **la resolution**,
elle, existait — sous deux formes, aucune versionnee :

- **`probe_212_bc_key_literals.py`** (#212) resout les litteraux qu'une fonction lit, **a la
  demande**, a partir de son symbole. Il **fonctionne** (verifie : `--anchors` rend `VERDICT: OK`).
  C'est de lui que vient la relation token -> index. Il ne persiste rien : chaque question
  re-scanne, et rien ne se diffe entre builds.
- **`playbook_keys.py`** lisait `data/dumps/<hash>/stringliteral.json`. Ce chemin **n'existe plus**
  (ni dans un worktree, ni dans l'arbre principal) : l'outil est **casse**. Il refuse proprement
  (`rc=2`, « aucun dump stringliteral.json trouve »), donc il ne rend pas de faux resultat — mais
  il retombait sinon sur « le dump le plus recent », sans confronter aucun sha256.

L'apport tient donc en quatre points : la table **versionnee** (donc diffable), la **provenance**
avec refus inter-build, un **lecteur** reutilisable, et la relation token -> index re-calibree sur
**30 367** points au lieu de 9.

## 7. Ce que je n'ai PAS fait

- **Aucune emission de `Source=`** — c'est la tranche D, et la mesure ci-dessus la **reoriente** :
  ce qu'il lui faut n'est pas une table de chaines, c'est de savoir quel enum et quel ordinal
  chaque `StartGroup` passe.
- **Aucune table des IDENTIFIANTS.** La 3e section de `global-metadata.dat` porte **181 313**
  entrees (**181 182** uniques) — noms de types, methodes, champs — et c'est la que se lisent les
  8 noms observes. Mais `frida/enums.tsv` les couvre deja pour ce qui nous interesse, et une table
  de 181 k entrees sans consommateur identifie serait du poids sans emploi.
- **Aucune consolidation de `probe_212` / `playbook_keys.py`** sur la table (residu `#477-r15-r1-r1`).
- **Aucun capteur Frida, aucune reinjection** : la voie retenue n'en a pas eu besoin.

## Residus

- **#477-r15-r1-r1** — **`playbook_keys.py` est casse et `probe_212` re-scanne a chaque question.**
  Les deux resolvent des litteraux par une chaine qui leur est propre, sans provenance :
  `playbook_keys.py` lit `data/dumps/<hash>/stringliteral.json`, **chemin disparu** (il refuse,
  `rc=2`) et retombait sinon sur « le dump le plus recent » sans confronter de sha256 ;
  `probe_212` fonctionne mais ne persiste rien. La table versionnee les couvre tous deux.
  **Condition de retournement executable** : faire consommer `string_literals.charger()` aux deux,
  verifier que `playbook_keys.py --grep SAVIORPROTOCOLS` rend a nouveau ses cles, et que
  `probe_212 --anchors` rend toujours `VERDICT: OK` sur ses 9 ancres.
- **La version de metadonnees est FIGEE a 39** (`VERSIONS_LUES`). C'est voulu, pas une dette : la
  disposition des sections change entre versions, et la deviner produirait des chaines plausibles
  et fausses. Au prochain build, si la version bouge, le producteur **refuse** et le dit — la
  confronter alors a Il2CppDumper (`--stringliteral-json`) avant d'elargir la constante.
