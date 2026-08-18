# tacticus-tools

Hooking Frida de **WH40K Tacticus** (Windows PC build, Unity 6 IL2CPP) — monorepo TypeScript.

## Structure

- Racine : `C:\Users\nicolasv\tacticus-tools`
- `frida/` — codebase active (hooks TS + host TS, bundlé par `frida-compile`)
  - `frida/hooks/` — script injecté dans Tacticus
  - `frida/host/` — serveur Node qui pilote les sessions Frida (Express + WS)
  - `frida/public/` — frontend browser (statique, servi sur `/view/`)
  - `frida/dist/` — outputs build (gitignored)
- `scripts/frida/` — scripts Frida one-shot **vivants**, hors bundle (notamment
  `dump-il2cpp-full.js`, qui produit toute la chaîne de symboles).
- `hooks-legacy/` — hooks et probes **historiques** (versionnés, consultables). Rien
  de vivant ne doit en dépendre. Voir `hooks-legacy/README.md`.
- `data/` — **VERSIONNÉ à la racine, aucune règle ne l'ignore** (depuis le 2026-07-26). Règle de
  partage : **`data/` = ce qu'on LIT, `logs/` = ce qu'on ÉCRIT**. Les `data/` NICHÉS
  (`frida/data/`, `scripts/python/data/`) sont des sorties runtime, eux ignorés.
  ⚠ Un fichier laissé non suivi sous `data/` n'est protégé par RIEN : `git clean` et un
  `worktree remove --force` l'effacent sans trace. L'indexer est ce qui le sauve.
- `sources_win/` — **PAS une décompilation Ghidra** : c'est un `dump.cs` d'**Il2CppDumper**
  éclaté en 26 382 fichiers, **daté du 2026-05-20** (donc un AUTRE build), et **tous les corps
  de méthode y sont VIDES** (`{ }`). Mesuré le 2026-08-13, après qu'un agent y a cherché du
  code. Utile pour les **signatures, champs et offsets** (stables à ~97,5 % par nom) ; **pour
  lire un CORPS, c'est `mcp__ghidra__decompile_function`, jamais ce répertoire.** gitignored
- `STATUS.md` — **instantané HISTORIQUE du 2026-05-03** (ère « Tacticus Builder » : pipeline
  d'injection et de build de nœud). **Ce n'est pas l'état du projet** — ne pas s'y fier.

### Où lire l'avancement (ces fichiers-là, pas `STATUS.md`)

- `docs/rl/backlog.md` — **les tâches OUVERTES**, versionné (le tracker `TaskCreate`/`TaskList` vit
  côté compte et a déjà disparu d'une session). Les tâches finies n'y sont plus : elles ont leur
  `docs/rl/case-<n>-*.md`. ⚠ Il décrit des INTENTIONS HORODATÉES, pas l'état du code — confronter
  au commit courant avant de dispatcher.
- `docs/rl/kit-coverage.md` et `docs/rl/combat-ability-coverage.md` — **audits GÉNÉRÉS** de la
  couverture (`audit_kit_coverage.py`, `audit_combat_ability_coverage.py`, depuis `scripts/python/`).
  **Ne jamais résoudre un conflit dessus — les REGÉNÉRER.** ⚠ Mais **ne les régénère pas de ta
  propre initiative** : la régénération appartient à l'orchestrateur, au MERGE, parce qu'il n'y a
  là qu'un seul acteur. Depuis une PR, N branches parallèles réécriraient les mêmes fichiers —
  le conflit est garanti. Si ta tranche fait bouger une couverture, **dis-le au rapport**.
- Les chiffres se **re-dérivent**, ils ne se citent pas : ils bougent à chaque tranche livrée.

## Cible Windows

- **Exe** : `C:\Users\nicolasv\AppData\Local\tacticus\games\<HASH>\Tacticus.exe`
- **GameAssembly.dll** : ~60 MB, IL2CPP AOT (Unity **6000.3.13f1** au 2026-08-04 — comme le
  `<HASH>`, ça bouge à chaque mise à jour : le LIRE dans `meta.unityVersion` de la réponse
  d'inject, jamais recopier cette ligne. Elle est restée à `6000.3.8f1` plusieurs builds durant.)
- **Pas d'`adb`, pas de device, pas de `frida-server`** : injection locale via `frida.getLocalDevice()`

### Hash du build = identité du dump

Tacticus stocke chaque build dans `C:\Users\nicolasv\AppData\Local\tacticus\games\<HASH>\`
où `<HASH>` (ex. `nb3o9lmt6c`, `uu2fr8mv6c`, …) **change à chaque mise à jour**
du jeu. Toutes les RVAs IL2CPP, le dump `data/il2cpp_full.json` et ses TSV,
la table `data/symbols/<HASH>/` et le projet Ghidra du build (cf. `sources_win/` ci-dessus,
qui n'en est PAS un) sont
**spécifiques à ce hash**. Une RVA résolue contre le mauvais dump donne un
nom de méthode incohérent — symptôme classique : la stack pointe vers une
méthode qui n'existe pas dans le binaire actif (typique : `findMethod` retourne
RVA différente de celle dumpée), et tous les hooks installés via RVA hardcodée
(ex. `RVA_BUCKET_ADD_ACTION = 0x1478820`) tombent sur du code aléatoire.

**Avant de consulter `sources_win/` ou `data/dumps/<HASH>/` ou de croiser
une stack frame contre `all_game_targets_win.tsv` :**

1. Lire le hash du build courant :
   ```bash
   ls -d /c/Users/nicolasv/AppData/Local/tacticus/games/*/
   ```
2. Lire le hash du dump :
   ```bash
   cat data/dumps/<HASH>/HASH    # ancien data/win_dump/HASH
   ```
3. **Si les deux ne matchent pas, refuser l'analyse offline** : signaler à
   l'utilisateur, demander un re-dump avant tout. Forcer la désynchronisation
   silencieuse a déjà coûté plusieurs heures de debug.

### Règle de code : résolution runtime, pas de RVA hardcodées

**Tout hook doit résoudre son entry point en runtime** via la table IL2CPP :

```ts
const klass = findClassAnywhere(ns, cls);              // helpers.ts
const mptr = findMethod(klass, methodName);            // helpers.ts
Interceptor.attach(mptr.ptr, { ... });
```

**Aucune RVA hardcodée**, ni en constante, ni en fallback `?? il2cppBase.add(0x...)`.
Une RVA copiée d'un dump devient invalide au prochain changement de hash, et
`Interceptor.attach` réussit silencieusement sur du code aléatoire — symptôme
que le hook ne fire jamais (ou fire et crashe). Si `findClassAnywhere` ou
`findMethod` ne trouve pas la méthode (rare — typiquement des gshared bodies
ou des classes non indexées par `image_get_class`), c'est une vraie limitation
à investiguer, **pas** un cas pour ressortir un RVA offline.

Cette règle s'applique aux dumps offline pareil : tout `data/dumps/<hash>/*.tsv`
ou `*.json` n'a de valeur que pour la **lecture humaine** (consulter du code
décompilé, comprendre l'archi). Aucun hook live ne doit en dépendre.

**Quand il n'y a RIEN à résoudre** (placeholder `FUN_*` sans `MethodInfo`, point interne, `DAT_*`,
corps d'itérateur), l'exigence n'est pas « pas d'adresse » — c'est **détecter la péremption et
REFUSER de s'attacher**. Foyer unique : `pinnedAddress` de `frida/hooks/il2cpp/build-pin.ts`
(pendant live de `build_pin.require_pinned`, #431). Le porteur DÉCLARE son build, le foyer le
confronte à celui qui est chargé, et rend `null` en le disant. **C'est le SEUL module où
`il2cppBase.add(<constante>)` a le droit d'exister**.
⚠ La phrase « reste en VA, et c'est voulu » (§ suivant) est écrite pour la **CITATION**, jamais
pour l'**ATTACHEMENT** : mesuré le 2026-08-04, les six adresses en dur des hooks étaient **6/6
périmées**, et la seule encore armée attachait `Interceptor` **au milieu d'une autre fonction**.
⚠ Et « résolu au runtime » ne suffit pas non plus : sur une **définition générique**, `findMethod`
rend le **thunk d'invocation**, pas le corps gshared — `bucket-audit` se déclarait `enabled` avec
**0 fire**. Passer par l'**instance inflatée** (#259-b). Détail : `docs/rl/case-475-adresses-epinglees.md`.

### Règle d'écriture : on cite un SYMBOLE, jamais une adresse

**Toute référence à du code natif — commentaire, docstring, message de test, doc —
s'écrit avec le symbole Ghidra VERBATIM, jamais avec une VA.**

```
IdunBattle.Core.Services.DamagePrediction$$CalculateDirectDamage      ✅
`CalculateDirectDamage @18102f130`                                    ❌
```

- **Point interne** à une fonction : `<symbole>+0x<offset>`.
- **Échappement conservé tel quel** (`u003C` = `<`, `u003E` = `>`) : c'est ce qui rend le
  grep code ↔ table immédiat.
- **Les offsets RELATIFS restent** : champs de struct (`+0xa8`), slots de vtable, RVA
  calculées en code depuis l'image base. Seules les **VA absolues** sont proscrites.

**Pourquoi** : churn inter-build **mesuré** (build de mai → `gqfc5mff6c`) — les noms sont
stables à **97,5 %**, les adresses changent à **100 %**. Une citation par adresse est donc
fausse dès la mise à jour suivante, **silencieusement** : on ne l'apprend qu'en lisant du
décompilé qui ne correspond à rien. Le symbole, lui, survit et se re-résout d'un grep.

**Comment résoudre** une adresse trouvée dans Ghidra :

```bash
python scripts/python/ghidra_symbols.py whereis <VA>     # -> <symbole>+0x<offset>
```

ou, 100 % offline (ghidra-mcp éteint), un grep dans `data/symbols/<build>/functions.tsv`
(format `<adresse>\t<symbole>`). Migration d'un lot existant :
`scripts/python/migrate_va_to_symbol.py` (token-aware — il ne réécrit QUE dans les
commentaires et chaînes, jamais un littéral exécutable) ; `probe_va_in_code_vs_prose.py`
est le garde-fou à passer avant.

**Reste en VA, et c'est voulu** : les adresses qui ne résolvent que sur un placeholder
`FUN_<addr>` (le « symbole » n'y est que l'adresse déguisée) et les thunks de la table
d'imports. Les lister plutôt que les maquiller.

### Règle de code : un ENTIER qui DÉSIGNE quelque chose passe par un ENUM

**Pas de champ de bits sans enum. Pas de clé entière sans enum.** Tout littéral qui *désigne*
une entité du jeu s'écrit par son membre nommé, **même quand l'ordinal est juste**.

- **champ de bits** → `TR.CasterIsPossibleTarget`, jamais `rules & 0x8000` ;
- **clé de dict** — `effect_type`, `event_id`, `ability_id`, trait, `GroupType` → le membre ;
- **argument** → `int(EventTriggerType.PreUnitDeath_2)`, jamais `2`.

**Pourquoi** : un ordinal juste aujourd'hui devient faux au changement de build, **en silence** —
mesuré, pas redouté : `GROUP_TYPE` porte **66 noms FAUX sur 102** (#270-a). Un membre d'enum se
re-dérive du dump, et le diff de `data/symbols/<build>/frida/enums.tsv` rend le glissement
visible. C'est « on cite un SYMBOLE, jamais une adresse » ci-dessus, transposé de l'axe des
ADRESSES à celui des VALEURS.

**Les enums existent — les compléter, pas les contourner** :
`engine/runner/abilities/targeting_rule.py` (60), `engine/dsl/event_trigger_type.py` (76),
`engine/entities/effect_type.py` (629), `engine/entities/traits/unit_trait.py` (117),
`engine/entities/active_ability_type.py` (260, importé par **145** fichiers). Si le tien n'y est
pas, **l'ajouter fait partie de la tranche**.

⚠ **Les axes BITS, CLÉS DE DICT et ÉLÉMENT DE CONTENEUR sont tenus** — **0** test de bit exécutable
à littéral brut ; **305** clés de dict converties (169 + 128 + 8) ; **160** éléments de conteneur
(#270-r1-r1, 2026-08-05), soit `element de conteneur` **201 → 41** et `cle de dict` **8 → 0**.
Puis **140** littéraux des **rôles DÉRIVÉS** (#270-r1-r1-r3) : `affectation` **166 → 44**,
`valeur de retour` **18 → 6**, candidats **746 → 610**. Value-preserving **vérifié** à chaque fois
par empreinte des deux versions.

⚠ **Là où il n'y a PAS de groupe, il n'y a PAS de couverture — le discriminant redevient le SITE.**
Les volets « clé de dict » et « élément de conteneur » s'appuyaient sur la **couverture du groupe**
(tous les entiers d'un dict/tuple dans le même enum ⇒ le groupe est clé par cet enum). Les rôles
dérivés sont des positions **isolées** (`_STAT = 8`, `return 7`, un argument, un indice) : aucun
voisin ne les contraint. Le tri se fait **site par site**, par le **NOM déjà écrit** ou le **TYPE
DÉCLARÉ** lu dans `frida/methods.tsv` — et « hors règle, c'est un scalaire » reste un résultat.

⚠ **UN MIRROR D'ENUM EST UNE FEUILLE — son EMPLACEMENT se MESURE, il ne se décrète pas ; et la
contrainte qui vivait ici A DISPARU.** Ranger `AbilityConstantType`/`AbilityVariableType` sous
`engine/entities/abilities/` les rendait **inimportables** (l'`__init__.py` du paquet tirait
`active_ability` → `services.damage_prediction` → `ImportError` sur module partiellement
initialisé), tout comme la place des deux imports d'enum de `services/static_battle_rules.py`
était contrainte par la même forme de boucle. La **vidange des barils** (#485-r1-r1) a supprimé
les deux : `import engine.entities` charge **94** modules `engine.*` avant, **2** après, et
`entities/effects/loki/hits.py` n'est plus tiré du tout. Les deux étages qui gardaient ces
prescriptions **se sont retournés**, comme ils étaient écrits pour le faire, et mesurent
désormais l'inverse — le déplacement est **effectué dans une copie** de l'arbre et doit
**passer** (`test_270r1r1r3_role_enum_offline` étage 6), les deux imports sont **en tête** et la
cascade du paquet doit rester **courte** (`test_270r1r1_container_enum_offline` étage 4). Les
mirrors restent sous `engine/entities/` : c'est désormais un **choix**, pas une obligation. Ce
qui reste prescriptif : un emplacement de mirror s'établit en **déplaçant pour de vrai** dans un
arbre témoin, jamais en recopiant une ligne comme celle-ci.

⚠ **Une confusion d'enums peut être SILENCIEUSE EN ORDINAL, et c'est ce qui rend le NOM obligatoire.**
Mesuré (#270-r1-r1-r3) : les **19/19** ordinaux `AbilityConstantType` utilisés par le port sont
**aussi** des membres valides d'`AbilityVariableType` (**10/10** dans l'autre sens) — confondre
`GetNumberConstant` et `GetVariableForLevel` n'aurait levé **aucune erreur**, juste lu la mauvaise
clé du gameconfig. Mais **28/29 nomment autre chose** (`22` = `range` / `blockDmg_2`). Le nom est le
seul canal où la faute est visible. Corollaire de contrôle : un test « les ordinaux communs nomment
autre chose » a d'abord rendu un ensemble **VIDE** (les deux jeux d'ordinaux sont disjoints) — un
test vide serait passé pour vert ; **assertionner son propre non-vide** est ce qui l'a sauvé.

⚠ **UN RECENSEUR NE PEUT PAS RENDRE ZÉRO SUR CE QU'IL NE VISITE PAS — et une LISTE BLANCHE de rôles
ne peut pas montrer le rôle qu'elle a oublié.** Ce gisement a été sous-compté **trois fois de
suite**, toujours par la même cause : « 284 clés » ne voyait que les dicts ; le `0` d'après le volet
2 ne voyait que les dicts d'au moins 3 clés (**seuil**) ; et l'ajout du rôle conteneur a fait
apparaître **deux positions de plus** que personne n'avait comptées (`return 7`, `X = 1119`). Le
probe **n'énumère plus des rôles** : il visite **tous** les `ast.Constant` entiers et **dérive** le
rôle du nœud parent, une position inconnue sortant sous `autre (<Noeud>)` ; la somme des rôles est
imprimée comme partition exhaustive. Effet mesuré : **285 → 912** candidats, soit **3,2×**. Tout
compte filtré **dit ce qu'il filtre** (`ECARTES PAR CE SEUIL : …`). Effet mesuré : **285 → 912**
candidats, soit **3,2×**. Restent ouverts les rôles que le tri site-par-site n'a pas tranchés
(`argument d'appel`, `comparaison`, `expression` — majoritairement des timeouts RPC et des
pourcentages). Re-dériver (`probe_270r1_enum_candidates.py --croiser`), **jamais citer ce
paragraphe**.

⚠ **Une conversion de masse se vérifie par EMPREINTE — et l'empreinte doit hacher la VALEUR, pas la
REPRÉSENTATION.** Mesuré (#270-r1-r1) : une empreinte sur `repr(v)` a rendu **3 divergences, toutes
fausses** — `repr(6)` ≠ `repr(<PathfinderType.TeleportStrikeWalk: 6>)` alors qu'un `IntEnum` **est**
un `int`. Canonicaliser par `int(x)`, **récursivement** dans les conteneurs. Le contrôle qui rougit
sur son propre artefact fait renoncer à des conversions justes.
⚠ **Et l'arbre TÉMOIN doit voir les mêmes ENTRÉES que l'arbre mesuré** : re-mesuré
(#270-r1-r1-r3), un `git archive HEAD scripts/python` sans `data/` a rendu **3 divergences, encore
toutes fausses** — les caches *lazy* alimentés par le gameconfig restaient vides d'un seul côté.
Extraire l'arbre **complet** les dissout. **La portée de l'empreinte se prend LARGE** (tout
attribut de module ET de classe du paquet) : une liste de structures choisies ne peut pas montrer
la valeur qu'elle a oubliée — le vice même que le recenseur a dû corriger.

⚠ **Un mirror NEUF entre au registre de `probe_313` DANS LE MÊME COMMIT**, apparié par son nom
**PLEIN** : le build porte `UnityEngine.RectTransform.Edge` en plus d'`IdunBattle.Utils.Hex.Edge`,
et cinq `Corner` Unity/SimpleUI. Ce gisement s'est rouvert **quatre** fois par notre propre cadence
(`PathfinderType` #381-r5, `KillUnitStep` #389-r2, `DamageReason` #651 — qui rendait `master` rouge —
`Edge` #270-r1-r1, inscrit à temps ; puis les **quatre** de #270-r1-r1-r3, inscrits de même).
⚠ **Le registre ne suffit pas — il faut aussi FIGER l'ordinal ÉCRIT AU SITE.** `probe_313` compare
le *mirror* au *build* : il redevient **VERT** dès qu'on régénère le mirror après un renumérotage,
alors que la valeur écrite au site, elle, a changé. Le cran manquant est un test qui garde
l'ordinal **mesuré à la conversion** (`test_270r1r1r3_role_enum_offline.py`, étage 1).

⚠ **La VOIE ne dit pas l'enum, et l'ORDINAL non plus — seul le NOM ou le TYPE DÉCLARÉ tranchent.**
Mesuré sur les 128 clés du volet 2 : les 110 ids d'ability sont attribués par le **symbole natif
déjà cité au site** (110/110 concordants), jamais par leur ordinal, que `TriggeredAbilityType`
partage à 458 exemplaires avec `EffectType` et 233 avec `ActiveAbilityType`. Et les 18 clés
« petits entiers » qu'on croyait scalaires sont un `IdunBattleLogic.Utils.Hex.Corner` — **type LU
dans `frida/methods.tsv`**, pas déduit. Quand ni le nom ni une signature ne tranchent, écrire « hors
règle, c'est un scalaire » est un résultat valable ; forcer un nom sur un entier qui n'en désigne
aucun est pire que l'ordinal, qui au moins ne ment pas. Détail :
`docs/rl/case-270r1-volet2-cles-ambigues.md`.

⚠ **Et la conversion n'est PAS mécanique** : elle vaut ce que vaut le miroir Python. `ActiveAbilityType`
(#270) **et** `TriggeredAbilityType` (#313, puis #270-c) sont réparés et **sous cliquet**
(`probe_313`, 14 mirrors en bijection, 0 dette) ; les générateurs des tables **SQL** restent **cassés**
(#270-b, arrimés à un `dump.cs` supprimé). Convertir depuis un miroir périmé écrirait des noms
FAUX — pire que l'ordinal, qui au moins ne ment pas. **Vérifier la fraîcheur de la table avant
de nommer quoi que ce soit** — la ligne que tu lis a elle-même annoncé « 107 ids morts » **quatre
jours après leur retrait**, et c'est exactement ce genre de citation périmée qui fait renoncer à une
conversion pourtant sûre.

⚠ **La conversion se fait PAR NOM, jamais par la VOIE.** Mesuré (#270-c) : le nom **discrimine** —
sur le gameconfig, l'intersection nom-à-nom `passiveAbilities`/`activeAbilities` est **VIDE**, donc
**0 nom ambigu** ; l'**ordinal**, lui, ne discrimine pas — `TriggeredAbilityType` partage **458**
ordinaux avec `EffectType` (**454** nomment autre chose) et **233** avec `ActiveAbilityType`
(**231**). Deux **inversions de voie** existent et se lisent explicitement (`ShroudPsalm` en
`passiveAbilities` est un `ActiveAbilityType` 1181 ; `Maugetar` en `activeAbilities` est un
`TriggeredAbilityType` 1498) — une conversion « voie ⇒ enum » y écrirait un id faux.
⚠ **Un mirror bijectif ne garde PAS ce que le moteur LIT** : `.get(clé, ())` sur un nom disparu rend
`()` — le passif n'est jamais inscrit, sans erreur et **sans que le mirror ait bougé**. L'étape 5 de
`probe_313` garde ce cran (245 clés, 7 dicts) ; elle distingue `INTROUVABLE` d'`EGAREE` (le nom vit
dans un **autre** enum ⇒ c'est l'**appariement** qui est faux). Détail :
`docs/rl/case-270c-mirror-deja-bijectif-le-cran-du-dessous.md`.

**Reste en littéral, et c'est voulu** : le décompilé **CITÉ** (docstring, commentaire) — on cite
le natif verbatim, avec le nom en commentaire de fin de ligne. Et les offsets **relatifs**
(`+0xa8`, slots de vtable), qui ne désignent aucun enum.

### Règle de code : un import DIFFÉRÉ est un outil à CYCLE, pas un idiome

**Face à un cycle d'import, dans cet ordre : (1) DÉPLACER le code partagé vers un module que la
cascade ne ré-entre pas — ça supprime l'arête ; (2) ALLÉGER l'`__init__` du paquet, qui est la
cause racine (`engine/entities/__init__.py` tire tout `effects` → `loki` → `selectors`, donc
toucher une feuille énum traîne un millier de modules) ; (3) DIFFÉRER — en DERNIER, et le
commentaire porte alors la MESURE qui établit que (1) et (2) échouent, pas le constat qu'un cycle
existe.**

**Classer, mécaniquement** : pour un différé `M -> X`, charger `X` seul dans un process FRAIS et
regarder si `M` atterrit dans `sys.modules`. Oui ⇒ hisser fermerait un cycle, le différé est
**PORTEUR**. Non ⇒ **GRATUIT**, à hisser.

**Ce n'est pas une préférence de style.** Mesuré le 2026-08-06 : **430 modules sur 430** de
`engine/**` s'importent SEULS en process frais. Nos ~500 probes entrent dans le paquet chacune par
le module dont elle a besoin — l'import isolé n'est pas une commodité de test, c'est
l'architecture. La PR #738 a ajouté une arête `battle_query -> entities.traits.unit_trait` : le
compte est tombé à 429 et `probe_433_r1_identity_shortcircuit.py`, **versionné**, est passé de
`rc 0` à `rc 1`. Trouvé à la relecture, par flair — aucun cliquet ne le voyait.

⚠ **Le 430/430 est TENU PAR les différés — ce n'est pas un certificat de graphe sain.** « Pas de
différés » est inatteignable, et le prescrire serait de la prose contre un fait. Ce qui est
exigible : **chaque différé DÉCLARE sa classe**, et le compte des gratuits ratchette au plus bas
atteint. Le cliquet d'import isolé garde « **aucun NOUVEAU cycle** », jamais « aucun cycle ».
**Re-dériver les comptes, jamais les citer** :

```powershell
python scripts/python/probe_485_imports_differes.py              # recensés / porteurs / gratuits
python scripts/python/probe_485_imports_differes.py --porteurs   # la raison de CHAQUE porteur
```

⚠ **Un plancher de gratuits se REMONTE tout seul, et c'est mesuré.** Ce fichier a porté « 169
différés, 166 porteurs, **3 gratuits** » ; **dix jours plus tard le même probe rendait 51 gratuits
neufs**, alimentés par notre propre cadence — exactement l'imitation décrite plus bas. Un chiffre
écrit ici n'est donc pas un état, c'est une photo qui se périme en silence et **fait renoncer à
une réparation juste**. Le gisement est **RATCHETÉ** (`scripts/ratchets-485-differes-attestes.json`,
qui ne doit que DÉCROÎTRE), pas résolu.

⚠ **Les gratuits ATTESTÉS ne sont pas un reliquat à finir** : ce sont des imports OPTIONNELS sous
`try/except`. Les hisser déplacerait l'échec du site d'appel — où il est rattrapé — vers le
chargement du module. La base attestée les nomme ; le probe les distingue des NEUFS.

⚠ **`from PKG import NOM` ne charge PAS que `PKG` — et le confondre a fait réclamer un hissage qui
CASSE.** Quand `NOM` désigne un sous-module, Python charge `PKG` **puis** `PKG.NOM` : la fermeture
d'un hissage est celle du MODULE. Le recenseur ne rendait que le paquet, donc il classait GRATUITS
des différés réellement PORTEURS — et ça visait précisément les sites écrits en **forme B**, celle
que cette section prescrit. Corrigé le 2026-08-18 (`_resoudre` résout le sous-module, et `classer`
décide **par INSTRUCTION** : une ligne qui charge N modules est porteuse dès qu'**un** tire
l'appelant). Ce qu'il faut en retenir : **la mesure d'un cliquet se contre-éprouve, elle aussi** —
un `import <cible>` dans un process frais, à la main, sur le couple qu'il accuse.

⚠ **Une RAISON ÉCRITE au site est au moins aussi trompeuse qu'une raison absente** : elle survit à
la disparition de son objet, et elle décourage la vérification. Mesuré le 2026-08-18 — **8 raisons
sur 8** annonçaient un cycle nommément décrit ; les **8** ont rendu `APPELANT_ABSENT` en process
frais, la vidange des barils (#485-r1-r1) ayant supprimé les arêtes de retour sans que personne ne
relise les commentaires qui les invoquaient. Écrire la raison reste utile (c'est ce qui arrête
l'imitation), mais **la raison qui fait foi est celle que `--porteurs` DÉRIVE**.

⚠ **HISSER, OUI — MAIS EN FORME B, ET C'EST LA SEULE DES TROIS QUI TIENNE.** Mesuré sous
`monkeypatch.setattr("src_x.foo", stub)` : **A** `from X import foo` au niveau module **NE MORD
PAS** ; **B** `import X` puis `X.foo()` **mord** ; **C** `from X import foo` dans la fonction
**mord, par accident** (l'instruction est re-exécutée à chaque appel). Hisser en forme A fait donc
passer de MORD à NE MORD PAS — c'est la cause exacte des 28 fichiers rouges de #484 et des 12 de
la famille #429-r1, et elle a **récidivé** dans #485-r1-r1 même (deux couples, dont un désarmé
SILENCIEUSEMENT parce que son patcheur est un probe que la banque ne joue pas). B ne coûte rien en
cascade (`from pkg.sub import mod` charge les mêmes modules que `from pkg.sub.mod import nom` —
écart 0) et éteint aussi l'ordre-dépendance : un binding de module n'est jamais gelé.
⚠ **Avant tout hissage, jouer `migrate_485r1_barils_reexport.py morsure`** : il dit lesquels
désarmeraient un patch déjà posé. Il ne le disait pas — deux angles morts, tous deux réparés :
`DEJA_INERTE` était testé AVANT `HISSAGE_DESARMERAIT` et faisait `continue` (une liaison A dans un
module tiers masquait le site C qu'on allait hisser), et sa base de gratuits était **ATTESTÉE**,
donc en retard d'une vidange — or un différé est gratuit **par rapport à un arbre**.

⚠ **Le gisement se propage par IMITATION, et c'est mesuré deux fois** : avant le sweep #485-r1-r1,
**32 des 52 gratuits (62 %)** vivaient dans un module portant DÉJÀ un différé légitime ; et le
sweep suivant a retrouvé un gisement du même ordre au même endroit. S'y ajoute qu'une large
majorité des porteurs n'écrit **aucune raison** : un lecteur ne peut pas distinguer « structurel,
n'y touche pas » de « scorie », donc il recopie. Écrire la raison n'est pas de la politesse — c'est
ce qui arrête la propagation. ⚠ Mais **ne la recopie pas en masse** : réécrire des centaines de
raisons dans des fichiers partagés est le sweep que la doctrine interdit (conflit garanti), et il
faudrait le refaire à chaque vidange. Annote **ce que tu touches**, et pour le reste sers-toi de
`--porteurs`.

⚠ **VIDER UN BARIL : l'ACCÈS ATTRIBUTAIRE est une voie de consommation, et il ne laisse AUCUNE
trace dans un recensement d'`ImportFrom`.** `from engine.playbook import noncomparable as NC` lie
un **module** ; tout `NC.X` qui suit est attributaire. Mesuré (#485-r1-r1) : le recenseur
couvrait `import X as E` et pas cette écriture-là — 4 couples vidés sous les pieds de leurs
lecteurs, dont **deux dans `engine/**` lui-même**, qu'aucun des tests tombés ne montrait. Cliquet
exécutable : `probe_485r1r1_acces_attributaires.py` (il résout chaque accès contre le module
RÉELLEMENT importé, donc il voit l'`AttributeError` avant qu'il soit joué).

⚠ **L'incitation joue CONTRE la réparation**, et elle vient du brief : « reste borné, ne touche
pas aux foyers des autres » rend le différé rationnel, puisque déplacer un foyer touche un fichier
partagé. Si ta tranche mesure qu'un déplacement est la bonne réponse, **fais-le et dis-le** — c'est
une réparation, pas un débordement de périmètre.

Re-dériver ces comptes, ne jamais citer ce paragraphe.

### L'ABSENCE d'une méthode dans les tables ne prouve RIEN

**`frida/methods.tsv` et `ghidra/functions.tsv` sont indexées par ADRESSE**, et IL2CPP
**déduplique les corps triviaux** (`mov eax,imm32 ; ret`, `xor eax,eax ; ret`, un `ret` nu…).
Un corps partagé par N classes n'a donc qu'**UN SEUL propriétaire** dans la table. S'y ajoute
que les **bases génériques** (`Playbook<T>`, `NonComparablePlaybook<T>`…) sont **absentes du
dump**, donc un getter hérité n'y est pas lisible non plus.

⇒ **« `<Classe>$$<Méthode>` n'apparaît pas dans la table » ne permet JAMAIS de conclure
« la classe ne surcharge pas ».** Ghidra ne nommera aucun de ces corps non plus.

**Mesuré (2026-07-27)** : `methods.tsv` = 121 502 lignes, **0 RVA répétée** ; `get_Priority`
y occupe **3 lignes pour 22 surcharges réelles**. C'est exactement ce faux négatif qui avait
fait écrire « aucun override n'existe » — puis **supprimer** deux valeurs justes en les
croyant périmées.

**Les génériques pleinement partagés sont absents du dump FRIDA, présents dans le dump
GHIDRA.** Mesuré le 2026-07-31 sur `rnca9r7q6c` : `__Il2CppFullySharedGeneric` = **4 874**
dans `ghidra/functions.tsv`, **0** dans `frida/methods.tsv` (dont **2 184**
`IdunBattle.AI.Playbook`). Le zéro Frida est structurel — le `methodPointer` d'une définition
générique est un thunk, pas le corps. Donc : chercher un générique dans **Ghidra**, et ne pas
conclure à l'illisibilité de la couche `Playbook`. Détail :
**`docs/rl/case-259-couverture-gshared.md`**.

**Comment conclure pour de vrai** : invoquer le **slot de vtable** sur l'instance (runtime,
cf. `reference_il2cpp_methodptr_uninit_class`), balayer **toutes** les valeurs d'enum
concernées plutôt que les classes trouvées, et recouper par une seconde source indépendante.
Détail de la méthode : `docs/rl/case-170-get-priority.md`.

## Workflow RL — runner isolé

> **Le LANCEMENT DE RUNNER est centralisé dans `.claude/skills/tacticus/references/runner.md`**
> (inclus ci-dessus, pointé par les agents `validator`/`re-expert`) : warmup obligatoire, voie
> `rl_duel build`, choix de board (`--board`/`--board-pool` + `board.py`), discipline runner.
> C'est LA source unique — ne pas dupliquer ces règles ici.

Pour entraîner un agent RL / valider le moteur sans toucher au battle in-game, on monte un
**runner isolé** depuis une **seed BC sur disque** (`rl_duel build`), déployé et pilotable à
volonté sans casser le jeu actif. Rappel des deux points les plus violés (détail : `runner.md`) :

1. **Warmup une fois par session Frida**, AVANT tout RPC/build. Sans lui : caches `MethodInfo*`
   vides + init IL2CPP non amorcée → crash `0x2c`. Il est **autonome** (pilote la nav lui-même,
   rend la main sur l'écran CAMPAGNE, sait sortir seul d'un écran de bataille hérité, ~12 s) :
   **ne JAMAIS demander à un humain de cliquer une battle ni de ramener la campagne.**
   Session froide → `warmupGameSingletons({ force: true })`.
   La PROCÉDURE (inject, endpoints host, fenêtres) est orchestrateur-only : skill
   `tacticus-orchestration`. Un agent ne (ré)injecte pas — cf. invariant 4 plus bas.

   > **RÈGLE INCONDITIONNELLE — warmup après CHAQUE (re)inject, AVANT tout RPC/probe, SANS EXCEPTION**,
   > y compris les probes « self-contained » montés depuis une seed BC sur disque (ex.
   > `rl_probe_step.py`, `rl_collect_batch`). Un (re)inject repart avec des caches `MethodInfo*`
   > Frida-side vides + la couche d'init IL2CPP non ré-amorcée dont dépend `initAndStart`. Un probe
   > qui « marche » sans warmup ne prouve rien (jeu déjà warm par chance) → au prochain build froid
   > c'est le crash `0x2c` (metadata non initialisée). Ne jamais raisonner « ce mode-là n'a pas
   > besoin de warmup ».

2. **Build + pilotage** : `rl_duel build --seed <s> --state-file <propre> [--p-units/--a-units,
   --board/--board-pool, ...]` puis `view/act/play/aiturn` ou `engine_validate.py --runner <id>`.
   Discipline runner (state-file propre, `--runner` explicite, coexistence/MAX_RUNNERS, dispose
   tes runners jamais ceux des autres) : `runner.md` §3.

## Sorties console Python — ASCII only (Windows cp1252)

La console Windows (et les tools Bash/PowerShell) tourne en **cp1252**, pas UTF-8.
Tout caractère non-ASCII envoyé à `stdout` (un `print`, un message d'assertion pytest
affiché via `-s`, une f-string de diagnostic) lève **`UnicodeEncodeError`** et fait
**crasher le script / échouer le test** — un faux négatif qui masque le vrai résultat
(les assertions, elles, passaient).

- **Dans tout `print`/log/sortie de script ou de test Python : ASCII uniquement.**
  Remplacer les symboles courants : `->` (pas `→`), `OK`/`X` (pas `✓`/`✗`), `<=`/`>=`
  (pas `≤`/`≥`), `Delta`/`d=` (pas `Δ`), `x` (pas `×`), `v`/`down` (pas `↓`), `...`
  (pas `…`). Le français accentué (é, è, à) est **aussi** non-ASCII → l'éviter dans les
  chaînes *imprimées* (OK dans les commentaires/docstrings non imprimés).
- **Pytest** : ne pas compter sur `-s` pour voir des prints contenant du non-ASCII (ça
  crashe). Invoquer pytest **sans `-s`** (sortie capturée) ; si une diagnostic est
  vraiment nécessaire à l'écran, la garder ASCII ou poser `PYTHONIOENCODING=utf-8`.
- **Pourquoi** : faute déjà commise plusieurs fois (`→`/`✓`/`Δ`/`↓` dans des prints) ;
  le contenu *écrit dans un fichier* via `open(..., encoding="utf-8")` n'est PAS concerné,
  seulement ce qui part vers la console.

## Tests du moteur Python — NE PAS relancer la suite complète

Après une modif, **ne lancer QUE les tests CIBLÉS de la tranche touchée**, jamais toute la
suite `tests/engine/` — **beaucoup trop lourd**.

- **Pourquoi** : chaque test live monte une (ou plusieurs) bataille(s) isolée(s) via le runner
  (build + nav + RPC). Un seul fichier = quelques dizaines de secondes à plusieurs minutes ; la
  suite entière = ~10 min+ et sature la session Frida. C'est un coût disproportionné pour valider
  un changement localisé.
- **Comment** : invoquer pytest sur les **fichiers pertinents uniquement** (ex. slice DAMAGE →
  `test_damage_roll_live.py` + `test_runner_attack_live.py` + les tests crit/block ; slice EFFETS →
  `test_effect_*_live.py`). Inclure un test de garde par dépendance impactée (ex. une modif d'un
  composant partagé `effects`/`base` → relancer aussi un test damage qui consomme ce chemin), mais
  **pas plus**.
- **Suite complète** : seulement sur **demande explicite** de l'utilisateur, ou avant un jalon
  (commit d'une tranche), pas après chaque édition.
- **PLUSIEURS modules à lancer → les lancer EN PARALLÈLE, 4 à la fois.** Mesuré le 2026-07-29 sur
  7 fichiers : 278 s en série → 80 s. Le harnais le supporte déjà (state-files isolés par PID,
  runner en `scope="module"`), donc N processus pytest, ou `pytest-xdist -n 4 --dist loadfile`
  (`--dist loadfile` OBLIGATOIRE : sans lui xdist répartit les *tests* et chaque worker
  reconstruit le runner du module). **Pas plus de 4** : le rendement tombe à 23 % dès 6 workers,
  et le pump est partagé avec les autres agents.
- **Le plafond de 4 borne ce qui MONTE UN RUNNER, pas la parallélisation.** C'est le critère :
  runner/RPC → 4 max (pump partagé) ; **purement offline → autant que le CPU**.
  ⚠ Deux probes lancés ENSEMBLE qui portent le même littéral de state-file se marchent dessus —
  **4 groupes, 16 probes sur 526** (`_49gnt`, `_32ct`, `state.json`, `_57h`). Non bloquant : les
  108 porteurs de littéral acceptent tous `--state-file`, donc un chemin explicite dissout la
  collision. Les 264 probes qui prennent leur chemin *uniquement* par argument ne sont isolés que
  si l'appelant leur en donne un distinct.
- **Un FICHIER dont le bilan est `passed == 0 and skipped > 0` fait désormais ROUGIR la passe
  (#455).** Le skip n'est pas le défaut — l'INVISIBILITÉ l'est : `test_summon_trait_effects_live.py`
  rendait 8 skipped / 0 passed / rc 0 sur `master`, zéro assertion évaluée, trouvé en ÉCARTANT une
  PR. Le garde #77 ne le voyait pas : il lit la RAISON d'un skip, et un skip de MONTAGE ne porte
  aucun marqueur de harnais. Si ton fichier rougit ainsi : **répare le montage** (c'était le cas —
  8 skipped → 8 passed) ou **nomme** l'impossibilité, jamais retirer le skip pour faire taire.
  Le garde se tait sur sélection partielle (`-k`, nodeid, `-x`) ; échappatoire consciente
  `TACTICUS_ALLOW_GREEN_SKIP=1`. Détail : `docs/rl/case-455-fichier-integralement-skippe.md`.
- **Un fichier dont TOUS les tests ont DISPARU rougit aussi (#455-r3)** — autre porte, même vice.
  Il n'émet aucun report, donc aucun bilan : le critère ci-dessus lui est structurellement aveugle,
  et pytest ne le signale (`rc=5`) que s'il est joué SEUL. Le discriminant est la **COLLECTE**, pas
  la sélection : `-k`/`-m`/`--deselect` filtrent APRÈS elle, un nodeid explicite n'émet aucun report
  de collecte — donc **aucune allowlist**. Un helper reste hors de portée par son NOM (`_x.py`,
  hors `python_files`). Deux volets : hook `pytest_collectreport` à chaque passe, et un balayage
  statique à périmètre dérivé dans le cliquet (le runtime ne voit que ce qu'une passe joue).

## Tu OUVRES un résidu ⇒ tu DEMANDES son numéro, tu ne le choisis pas (#468)

```powershell
python scripts/python/probe_468_collision_numeros.py --suggere [parent]
```

Rien n'allouait les numéros : ils étaient pris au vol, et une collision ne se voyait **qu'à l'œil au
merge**. Deux le 2026-08-04 à quelques heures d'écart, plus une **quadruple** (`#420-r1`, quatre
dossiers) que le cliquet a trouvée à son premier passage.

- **Les deux modes ont des critères INVERSES, et c'est voulu.** Détecter porte sur la **position**
  (1ʳᵉ cellule, tête de puce, préfixe de case-doc) — sur `docs/rl`, 6 580 occurrences `#<n>` pour
  836 définitions, donc un critère par présence rougirait sur presque tous les renvois. Attribuer
  porte sur l'**UNION** (mentions et messages de commit compris) : **un numéro seulement cité est
  déjà pris**. Mesuré : 13 racines `< 500` n'existent QUE dans `git log`.
- **Une mesure incomplète ne rend JAMAIS de numéro** (git muet → 99, rien suggéré), et on ne
  recycle pas un trou — une PR peut être en vol.
- ⚠ **`--suggere` n'OBSERVE plus, elle ALLOUE — le numéro qu'elle rend est RÉSERVÉ (#468-r14).**
  Elle le prend par `os.open(<git-common-dir>/tacticus-468-reservations/<clé>.json,
  O_CREAT|O_EXCL)` : l'allocation **EST** l'appel système, donc il n'existe aucune fenêtre entre
  « c'est libre » et « je le prends », et deux appels simultanés ne peuvent **pas** rendre le même
  numéro. Ce n'est pas improbable, c'est impossible. Mesuré à 8 processus au même instant : le
  régime d'avant rend **8 fois `#911`**, l'allocation rend **8 numéros distincts**. Le `.git`
  commun est le seul emplacement qui tienne les trois contraintes — **même chemin absolu depuis
  les 32 worktrees**, **survit** à `git worktree remove`, et **hors de tout arbre de travail**
  (donc `git status` inchangé, et pas un conflit de merge par allocation).
  ⚠ **Une réservation impossible sort en `99` sans rendre de numéro** : l'allocation ne se dégrade
  JAMAIS en observation. Et il n'y a **pas de `--liberer`** — il rouvrirait une course pour
  économiser un entier.
  ⚠ **Ce que ça ne couvre PAS, et la portée le DIT à chaque appel** : un numéro choisi **sans
  passer par l'outil**, et un numéro pris depuis un **autre clone / une autre machine** (l'espace
  de noms est per-dépôt, comme le `.git` qui le porte). **ANNONCE quand même le numéro que tu
  prends** si d'autres agents travaillent.
- **Le corpus, lui, répond à « où est-ce déjà ÉCRIT ? » — six sources.** Il rendait un `PASS`
  rassurant dans le SEUL régime où nos collisions se produisent : ce qui est écrit **et fusionné**,
  quand une allocation se fait au DÉBUT d'une tranche. Deux agents ont ainsi pris `#479` (collision
  **double**, racine ET `r1`). Depuis #468-r10 il lit les **refs hors `HEAD`** et les **noms écrits
  dans les autres worktrees** — ce qui a évité **deux** collisions imminentes (`#425-r3`,
  `#448-r3`) — depuis #468-r11 le **corps des PULL REQUESTS**, qui n'entre JAMAIS dans l'arbre (le
  squash-merge ne le recopie pas : `git grep` et `git log --all` rendaient **0** sur `#479-r2`, que
  la PR #663 ouvre explicitement) — et depuis #468-r14 les **réservations**. Détail et parades
  chiffrées (dont **deux refusées** : balayer les 94 branches non fusionnées apporte **0**
  changement de numéro ; et **une retenue** : le corps des PR en change **2**) :
  `docs/rl/case-468-r10-angle-mort-des-agents-en-vol.md`,
  `docs/rl/case-468-r11-monotonie-des-deux-modes-et-corps-des-pr.md` et
  `docs/rl/case-468-r14-de-l-observation-a-l-allocation.md`.
- ⚠ **La suggestion est MONOTONE dans les DEUX modes — elle ne l'était que dans un.** Le mode
  RÉSIDU s'arrêtait au **premier trou** et le proposait (`--suggere 477` → `#477-r14` alors que
  `-r15/-r16/-r17` existent), en n'affichant comme « pris » que le **préfixe contigu** : les
  résidus au-delà étaient **VUS par le corpus** et **tus par la sortie**. **11 parents sur 218**
  étaient dans ce cas. Un trou n'est jamais proposé, dans aucun mode — il peut être réservé par
  une PR en vol ou par un agent qui n'a rien écrit ; il est seulement **listé**.
- ⚠ La **puce** de résidu d'une case-doc est une 4ᵉ position de définition **de fait** — portée et
  MESURÉE (`#468-r7`, 2026-08-15), puis rendue en **INVENTAIRE** (`--report`), **jamais bloquante**.
  Le remède qui semblait évident — « un critère de SECTION » — est **réfuté** : seul, il rend **33**
  identifiants en puce ouverte dans ≥ 2 case-docs, parce qu'une section « Résidus » RÉCAPITULE sa
  famille. Le discriminant qui marche est le **propriétaire au plus long préfixe** (et, **sans
  propriétaire, toutes les puces définissent** — sinon le cas motivant `case-467`/`#472-r1` est
  perdu) : doubles **33 → 6 + 3**, lus un par un, **9/9 légitimes**. Faux positifs 9/9 ⇒ un critère
  bloquant se ferait désarmer. La seule forme qui le deviendrait (deux dossiers, **aucun**
  propriétaire) est **comptée à chaque run** ; elle vaut 0.
- ⚠ **EN POSITION DE DÉFINITION, L'IDENTIFIANT SE LIT PAR SA POSITION, PAS PAR UNE GRAMMAIRE**
  (`#468-r1`). Une grammaire qui s'arrête trop tôt ne *replie* pas le résidu sur sa racine — elle le
  fait **DISPARAÎTRE**, parce que le motif exige un `|` juste après. Mesuré le 2026-08-15 :
  **72 lignes de tableau** de `backlog.md` (7 % du registre) n'étaient **aucune définition**, et
  l'étape 1 leur était structurellement aveugle. Reste ouvert, et c'est une **convention
  d'écriture** : `normaliser` retire les tirets, donc `#222-1` et un futur `#2221` sont
  indistinguables — `--suggere` subit déjà cette confusion à l'identique.
- ⚠ **`--gate <ref>`** (`#468-r2`) n'accuse que ce que TA branche introduit : merge-base, arbre de
  travail inclus, appariement par le TEXTE de la ligne. Gain de **précision**, pas de détection —
  le balayage complet reste le mode qui garde l'arbre.
- ⚠ **`#<n>` désignait à la fois une tâche et une PR, et les deux compteurs se sont REJOINTS —
  corrigé par une BANDE (`#468-r8`).** Tant que les racines vivaient à ~500 et les PR à ~1500, une
  collision était accidentelle ; mesuré le 2026-08-14, racine en usage max **1084** contre PR max
  **1088**, donc **toute** racine neuve heurtait une PR — trois fois dans la même journée
  (`#1084`, `#1088`, `#1089`, chacun désignant aussi une PR mergée). Depuis, `--suggere` alloue les
  racines **à partir de `PLANCHER_RACINE = 10000`**, au-dessus de l'espace des numéros de PR : une
  racine neuve a 5 chiffres, une PR en a 4.
  ⚠ **Ajouter les numéros de PR au corpus ne suffisait PAS, et c'est le piège de ce correctif** :
  marquer `#1088` pris fait allouer `#1089`… que GitHub donne à la PR suivante, ouverte quelques
  minutes plus tard pour cette tranche même. La collision serait **déplacée**, pas supprimée. Les
  numéros de PR sont néanmoins entrés au corpus (`SRC_PR_NUMERO`) — c'est ce qui rend « pris »
  honnête, pas ce qui règle la collision.
  ⚠ **La bande a une DATE DE PÉREMPTION** (~240 jours au rythme mesuré de ~37 PR/jour), donc
  `--suggere` **alerte** quand les PR entrent dans les 1000 derniers numéros, et **dit** quand il
  n'a pas pu les mesurer (`gh` muet ⇒ « MARGE NON VÉRIFIÉE », jamais un vert).
  ⚠ **Effet de bord à connaître** : sous le plancher, `borne_des_taches()` n'influence plus le
  numéro alloué. Tout cliquet qui garde une source en assertant « le numéro X n'est pas proposé »
  devient donc **vacant** sur un dépôt jetable — sept l'étaient. Le remède n'est pas d'affaiblir
  l'assertion mais de placer le corpus **au-dessus** de la bande, où `borne + 1` commande à nouveau
  (`BASE_SUGGERE`), ou de viser la fonction pure directement. Les racines **historiques** (≤ 1084)
  ne bougent pas : `#1084` reste ambigu dans `git log`, c'est un artefact assumé.

### Et tu termines son corps par `FOYER:` et `BLOCAGE:` — deux champs, une ligne chacun

**Toute ligne de résidu que tu ajoutes à `docs/rl/backlog.md` finit par ces deux champs**, juste
avant le `|` de la colonne « Modèle » :

```
FOYER: engine/runner/abilities/targeting.py, engine/services/battle_query.py
BLOCAGE: aucun
```

- **`FOYER`** = les fichiers que la tranche va **ÉDITER**. Pas ceux qu'elle lit — ceux-là sont déjà
  dans « Point d'entrée ». `aucun` est une réponse valable (résidu documentaire ou d'outillage).
  Tu le connais au moment où tu ouvres le résidu : tu viens de lire le décompilé et tu sais quel
  mirror est en cause. Personne d'autre ne le saura sans relire toute ta fiche.
- **`BLOCAGE`** = un mot parmi `capteur` (exige une fenêtre de reinject) · `seeding` (le substrat
  ne publie pas la donnée) · `etage` (une fonction native intermédiaire n'est pas portée) ·
  `porteur` (aucune unité confrontable) · `aucun`. Un seul, le plus haut qui s'applique.

**Pourquoi — mesuré le 2026-08-07 sur les 297 résidus ouverts.** Grouper deux résidus dans un même
agent exige des **foyers DISJOINTS**, sinon on déplace une collision au lieu de l'éviter. Or c'est
la seule chose que le backlog ne porte pas : la **famille** se dérive gratuitement (46 familles
multi-résidus, 50 isolés) mais c'est **le mauvais axe** — `#287` compte **10** résidus répartis sur
**5 foyers disjoints**, et inversement `probe_457_offline_tests_green.py` est le foyer de **3**
résidus de **familles différentes** (`#457`, `#463`, `#486`). Le foyer TRAVERSE les familles.
Quant au « Point d'entrée », il cite majoritairement une **case-doc** — où LIRE, pas où ÉCRIRE.

⚠ **Le blocage, lui, est déjà écrit — mais en prose libre, donc incomptable** : un balayage rend
`etage manquant : 0` alors que `#287-r11` en nomme **trois**. Un mot discret le rend dénombrable,
et surtout **écartable au dispatch** : un résidu `BLOCAGE: capteur` ne part pas tant qu'aucune
fenêtre n'est prévue.

**Rétro-remplissage : au fil de l'eau, jamais en masse.** Si tu touches une ligne existante qui
n'a pas ces champs, ajoute-les.

⚠ **Et « jamais en masse » n'est PAS une question de coût — c'est le MERGE qui l'interdit.**
Mesuré le 2026-08-07 : **36 des 40 dernières PR mergées touchent `docs/rl/backlog.md`** (90 %),
et c'est de très loin le fichier le plus partagé du dépôt — le suivant est à 15. La cause est la
doctrine elle-même : tout agent qui ouvre un résidu y ajoute sa ligne. Une tranche qui réécrirait
les 297 lignes toucherait **toutes** les zones du fichier, donc chaque PR en vol tomberait dans un
hunk adjacent, sur des lignes de tableau modifiées **des deux côtés** — le conflit que git ne
résout pas seul, avec le risque d'écraser une ligne qu'on n'a pas lue. Le premier argument (« un
champ rempli de mémoire plutôt que par lecture est pire que son absence ») reste vrai mais il est
**négociable** ; celui-ci ne l'est pas. Ne dispatche pas d'agent de classification de masse sur ce
fichier, quelle que soit la valeur attendue.

## L'état de la BOUCLE — `loop_status.py`, déclenché tout seul (#467)

```powershell
python scripts/python/loop_status.py          # flotte / livraison / harnais
```

Il garde la **BOUCLE** : agents en vol vs plafond, commits non poussés, worktrees d'agents
nettoyables, PR ouvertes, session Frida, drain, et **`liveRunners`** (le budget partagé des
4-en-parallèle, que personne ne peut deviner).

- **Il se déclenche seul** : hook `Stop` du projet (`.claude/settings.json` →
  `scripts/hooks/loop-status.ps1`). Une checklist qu'il faut PENSER à lancer est oubliable —
  mesuré le 2026-08-04, un tour terminé à **1 agent sur 5** avec 30 commits non poussés et
  4 worktrees livrés, sans que rien ne le signale.
- **Il se TAIT** quand il n'y a rien à faire, et le critère de silence est **dérivé** : hors
  campagne (0 agent, 0 worktree, 0 PR, 0 commit d'avance), silence total.
- **Tri-état obligatoire** sur tout ce qui vient du host ou de `gh` : `null` = **PAS mesuré**,
  jamais rendu comme un zéro (même règle que `host_inputs.py`). Un `liveRunners` rabattu sur 0
  fait lancer 4 tests sur un budget inconnu — faute déjà commise.
- **Un verdict doit dire À QUOI il s'applique — jamais rendre pour l'état COURANT ce qui juge un
  ANCÊTRE (#472).** Mesuré : le hook a répété trois tours de suite un verdict pour une cause déjà
  corrigée, `HEAD` ayant changé deux fois entre-temps ; re-mesuré à froid, **48 commits** d'écart.
  Un verdict **PÉRIMÉ** reste **AFFICHÉ** avec les deux commits — il change d'**accusé** (contexte,
  pas signal), pas d'existence, et n'est rabattu **ni sur un vert ni sur un rouge**.
- ⚠ **Le chiffre du plafond (5 depuis le 2026-08-07 ; 6 du 2026-08-06 au 2026-08-07) est le SEUL
  qui ne soit pas une mesure** :
  c'est un paramètre d'orchestration (`--max-agents`, `TACTICUS_DISPATCH_CAP`). Résidu `#467-r1`.
  ⚠ **Ce n'est PAS le budget des RUNNERS** — mais l'inverse non plus : **rien n'oblige à donner
  une tranche offline au-delà de 4 agents**, et la prescription qui le disait ici (2026-08-06) est
  **RETIRÉE le même jour, sur correction de l'utilisateur**. Elle promouvait en plafond de
  CAPACITÉ ce qui n'est qu'un **rendement décroissant** : le « pas plus de 4 » borne les *workers
  d'une même passe pytest* (simultanés par construction), pas le nombre d'agents *capables* de
  live (passes sporadiques et entrelacées). Les mesures vont dans l'autre sens — `MAX_RUNNERS`
  = **50**, latence **plate à 10 runners** (#132), et sur la banque le throttle 4/6/8/16 rend
  280 / 240 / **227** / 235 s : au-delà de 4, c'est encore plus RAPIDE, seulement moins efficient.
  Ce qui reste vrai : le pump est **partagé**, donc une passe donnée ne prend pas plus de 4
  workers. Le nombre d'agents en vol, lui, ne se dérive pas de là.
- ⚠ **Une panne de capteur doit porter son NOM (#467-r6).** `gh` rendait `rc=127` pour ses trois
  pannes — binaire absent, délai dépassé, `OSError` — parce que toutes retombaient sur la même
  sentinelle. Résultat **mesuré** : l'incident a été diagnostiqué « `gh` absent du PATH » alors que
  `gh` était sur le PATH (identique sous `pwsh` et sous le `powershell.exe -NoProfile` du hook) et
  que la vraie cause était le **budget** — 2,90 s pour 3,00 s en solo, **5 tours sur 8** aveugles
  dans le tour complet, **0/8** après correctif. Un capteur qui ne sait pas nommer sa panne fait
  corriger la mauvaise cause. La piste « remplacer `gh` par du git pur » est **réfutée** :
  `--no-merged origin/master` sur les remotes rend **79** branches pour **1** PR ouverte (elles
  survivent au squash-merge), et le filtre de fraîcheur qui la sauverait rate les PR *anciennes*,
  les plus oubliables.
  ⚠ **Et un `rc` ne NOMME rien** — mesuré sur `gh 2.88.1` : `rc=1` couvre à lui seul le token
  invalide (HTTP 401), le dépôt inconnu (GraphQL) et l'erreur d'usage ; `4` = non authentifié. Seul
  le **stderr** les sépare, et le lecteur le **jetait**. Une table `rc -> libellé` aurait rendu un
  *mot* à la place d'une *cause*. Même vice côté **git**, où `RC_MUET` couvrait délai dépassé et
  erreur système sur le capteur qui court sous les 3 s du hook. Et nommer ne suffit pas s'il n'y a
  personne pour lire : un `git status` en échec rendait `push`/`sale`/`nettoyage` muets d'un bloc.
- ⚠ **Un repli sur cache peut SIGNALER, jamais RASSURER.** Servi quand `gh` est muet, il n'est
  retenu que s'il porte une PR **ouverte** : un cache disant « 0 PR » ne prouve rien, et le rabattre
  en mesure ferait taire l'outil sur une PR ouverte depuis. Aucun chemin ne fabrique un zéro.
- **Deux probes** gardent SA fidélité, et le second existe parce que le premier ne pouvait pas
  voir son gisement : les deux probes #467 **substituent** `http_json`, donc un champ disparu côté
  host les laissait verts tous les deux. `probe_467r4` confronte le contrat au **code source** du
  host, liste des champs **dérivée** de `mesurer_harnais`. Détail :
  `docs/rl/case-467-etat-de-boucle.md`.

## Ne jamais

- **Utiliser `--reload`/hot-reload côté host** : casse les sessions Frida
  actives, peut crash Tacticus si `Interceptor.replace` est en cours.
- **Stop manuel d'une session avec `Interceptor.replace` actif** sans le
  protocole cleanup graceful (crash le jeu).
- **Heap scans automatiques** (`Process.enumerateRanges`, `Memory.scan`) :
  Frida suspend les threads de la cible pendant le scan IL2CPP heap (~10 s sur
  Tacticus PC). UnityFreezeDetector (qui est lui-même hooké pour le pump)
  conclut que le main thread est figé → tue le process. Heap scans uniquement
  sur action utilisateur explicite, gated par `allowHeapScan: true`.
- **Broad-hooks sur méthodes UI hot** (`UnitProgression.Get*/Has*/...`) : la
  surcharge des trampolines × hot path = destabilisation IL2CPP cctor cascade.
- **Hook permanent sur des property getters** appelés par les sérialisations
  Newtonsoft du jeu (ex. `GameConfigData.get_gameConfigDto`) : 27 000 appels/s
  → frame >960 ms → crash.
- **Commit** : `frida/dist/`, `server/`, `logs/`, `frida/assets/raw/`, `sources_win/`.
  (`hooks-legacy/` EST versionné — l'ancienne mention ici était fausse. **`data/` à la racine
  aussi** : la ligne qui l'interdisait ici datait d'avant le 2026-07-26 et faisait laisser
  non suivies des entrées que `git clean` détruit — cf. section Structure.)

## Protocole RE + portage (DÉCISION + COMBAT)

Le protocole complet — recon du kit, RE fidèle (décompilé = vérité, jamais l'expérience live),
mirror 1:1 des fonctions natives nommées, décomposition par étage (jamais fitter un scalaire),
validation des DEUX faces (décider ≠ exécuter) — vit dans le skill `tacticus-re-port`
(invocable via `/tacticus-re-port`), inclus ci-dessous. C'est LA source unique de cette doctrine.

### Gate de confrontabilité : HERO / MoW / SUMMON — jamais NPC

Avant de porter une mécanique (ou d'exiger un datapoint live), établir **qui la porte** et si ce
porteur est atteignable en bataille. Trois catégories de porteur comptent, et les chemins de
vérification sont **distincts** :

- **HERO / MACHINE OF WAR** → présence dans `python scripts/python/rl_duel.py build --list-pool`
  (rank courant) — surtout pas `kind == lineup` de gameconfig, qui ment.
  **ABSENT DU POOL ≠ NON CONFRONTABLE** — le pool dérive du seed BC, capture d'**UNE** bataille.
  Un héros hors pool s'**injecte** (`catalog_inject.write_augmented_seed_bc` + `build --seed-bc`) :
  recette et pièges dans **`docs/rl/case-92-catalog-injection.md` §6**. Seul refus légitime :
  `data/unspawnable_rank<N>.json`. Mesuré le 2026-07-29 — `spaceWolfPriest`, classé « non
  confrontable » par un solveur, entre au pool (97 → 98) par cette voie.
- **SUMMON** → compte **aussi**, **même absent de `--list-pool`**. On l'amène en bataille en spawnant
  son **summoner** (qui, lui, doit être dans le pool) : le summon apparaît dans l'équipe du summoner.
  **Ne jamais conclure « non confrontable » d'un carrier summon.**
  ⚠ **Mais on l'OBSERVE, on ne le COMMANDE pas** — et le confondre a coûté un faux verrou (#291,
  `docs/rl/case-291-summon-activation.md`). Le natif TERMINE le tour de toute unité qui apparaît
  pendant le tour de son propriétaire (`SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` →
  `FinishUnitTurn(spawned, isTerminated: true)` → `MarkUnitAsNoActionAvailable`, sauf traits
  `Steppable`/`Hero`), donc un summon **n'entre JAMAIS** dans `decisionView.toActivate`, et
  `aiDryRunAllUnits` rend pour lui `FinishUnitTurnMessage` — c'est la réponse CORRECTE du natif, pas
  un trou de harnais. Il agit par deux chemins, qui sont les points d'observation :
  **(a)** le nœud DSL `PerformAIAction` de l'ability du summoner (→ `ComputerAction` forcé) — ses
  déplacements/abilities sont dans les **events du cast**, portés par l'entité du summon ;
  **(b)** `PlayAutomaticUnits` au **turn-start suivant** de sa team (trait `Summon`/`Object`) — se lit
  au delta d'état pris au tout début de son tour, avant toute action. Recette et probe :
  `probe_291_summon_activation.py`.
- **NPC** → le porteur est hors-jeu. Mais **« npc-only » n'implique PAS « non confrontable »** :
  quand le natif charge le playbook **PAR ABILITY** et que son utilité ne lit ni stats ni traits du
  caster, l'ability se **GREFFE** sur une unité du pool. Mesuré le 2026-07-31 — `1194 NovaShield`,
  seul porteur `tauBossRiptide` (npc), confrontée sur `tauCrisis` : **bug de port trouvé**. Recette :
  `docs/rl/case-92-catalog-injection.md` §5bis. Vérifier la condition avant de greffer ; à défaut,
  écrire NON CONFRONTÉ, jamais « non pertinent ».

#### Une ability de RELIQUE se ventile en TROIS états, jamais deux

« Confrontable / non confrontable » est un axe **faux** pour une relique — et le rabattre à deux a
produit au moins **six verdicts « 0 porteur, DEAD » démontrés FAUX** (recensés dans
`docs/rl/case-323-unit-map-attribution-voies.md`). Les trois états :

1. **Équipée au seed** → confrontable *tout de suite*, sans rien monter. Lire
   `BC.Units[].TertiaryAbility`. Mesuré : **4 unités** du seed en portent une (3 abilities
   distinctes — `admecMarshall` et `admecRuststalker` partagent la même). `buildNormalizedBC` la
   **préserve** (`normalize-bc/json-build.ts` ne touche qu'à `TertiaryAbilityLevel`).
2. **Porteur au pool, relique NON équipée** → **montage ÉCRIT (#237)** :
   `rl_duel build --equip-relic "<unitId>:<Ability>[:level]"`, ou `catalog_inject.equip_relic` /
   `write_relic_seed_bc` depuis un test. C'est le cas de loin le plus fréquent : sur les **56**
   unités du seed éligibles à une relique — **toutes dans le pool** — **52 y arrivent sans**.
3. **Porteur hors pool** → injection catalogue, comme un héros hors pool (**9** unités), **puis**
   le montage de l'état 2.

**Le montage tient en TROIS écritures, et DEUX échouent EN SILENCE** (RE :
`docs/rl/case-237-relique-forcee.md`) : `BC.Units[].TertiaryAbility` (sans lui,
`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` ne monte rien, sans erreur) ;
la config d'ability dans `BC.Abilities.PassiveAbilities` (**29 des 32** abilities de relique sont
absentes du seed → « system error » au cast, même verrou que #226) ; et
**`TertiaryAbilityLevel >= 1`** — `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`
(foyer UNIQUE des quatre accesseurs de variable) convertit par `Idun.Shared.Level$$ToZeroBasedIndex`,
qui **lève `InvalidOperationException` sur `<= 0`**, et `0` est exactement ce que porte toute
entrée sans relique (`0` = « verrouillé », cf. `Idun.Shared.Level$$CreateValidOrLockedLevel`).
**Pas de borne haute** : le même foyer clampe (`idx >= len` → `len - 1`).
⚠ **L'ORDRE** : `buildNormalizedBC` réécrit le niveau à `targetAbilityLevel` (50) **seulement si
`TertiaryAbility` est déjà non nul** — poser la relique APRÈS la normalisation (`--unit-stat`,
patch du template) laisse le niveau à `0`, verrou armé en silence.

**Le piège central** : `rl_duel build --list-pool` répond à « quels `unitId` normalisent au rank
cible », **pas** à « arrive en bataille AVEC sa relique ». Une gate passée sur le seul pool ne conclut
donc **rien** sur une ability de relique.

⚠ **Corollaire outillage** : `unit_map.py find --ability` lisait 2 voies d'attribution sur 5 et était
**aveugle aux reliques** — c'est ainsi qu'un « 0 unité » a fait classer un effet vivant en DEAD.
Depuis #323 il lit les 5 et **imprime les 4 non couvertes** quand il rend zéro. Un zéro de cet outil
n'est donc plus une preuve de mort — et ne l'a jamais été. Ne jamais conclure « pas de porteur » d'un
seul outil de recensement.

Même forme pour les **MACHINES OF WAR** : leurs `mythicAbilities` (**11**) sont invisibles de toute
autre voie. Les neuf voies d'attribution, mesurées, vivent dans `case-323` §2.

**Pourquoi** : les deux erreurs symétriques ont déjà coûté. Compter les npc comme spawnables envoie un
solver valider une branche impossible ; inversement, ranger un carrier **summon** en « non confrontable »
rabat à tort un port validable-live sur du mirror-offline (vécu le 2026-07-25 sur TwoManTeam/Diminutive,
corrigé en cours de route). Toujours **ventiler les porteurs hero / mow / summon / npc** et dire par
quel chemin chacun arrive en bataille — et pour une relique, **lequel des trois états**.

### DSL-effet vs impératif : c'est l'ARTEFACT NATIF qui tranche (#149)

Avant de porter/migrer un behaviour, demander **« quel est l'artefact natif ? »** :

- Natif = `CreateBehaviour`/`ExecuteBehaviour`/`CreateTrigger`, sélecteur ou formule (un **arbre de nœuds
  `DSLFactory`**, kinds E/T/S/V) → **DOIT être un arbre DSL** ; jamais de logique (ciblage, re-trigger,
  exclusion de trait) recâblée à la main dans un `execute_*` — elle doit **émerger** des nœuds.
- Natif = `Operation.Execute` (mutateur ECS), `Effect.ApplyModification`/`ReverseModification`, pathfinding,
  scheduler, PRNG, pipeline Apply → **RESTE impératif** (mirror fidèle). Une **feuille DSL l'APPELLE**.

**La frontière = le `.Execute` d'une feuille DSL** : au-dessus (structure de l'arbre + sélecteurs/formules) =
déclaratif → DSL ; en-dessous (l'Operation) = impératif → Operation. **Piège** : un helper qui FUSIONNE le
behaviour (`AddEffect`) et le `ApplyModification` de l'effet (ex. `_apply_act_of_faith_stack`) — les SÉPARER
(feuille DSL au-dessus, Operation/effet impératif en-dessous), ne pas wrapper le mélange. Classification par
ability + roadmap des tranches restantes : **`docs/rl/dsl-effect-nodes.md`** (section « Classification »).

### Entrer au registre SANS son masque de ciblage = régression silencieuse (règle de non-régression)

**Une ability qui entre dans `ABILITY_CLASSES` pose son `TARGETING_OPTIONS` DANS LE MÊME COMMIT.**

- **Pourquoi** : `get_invalid_target_reason` / `get_invalid_caster_reason`
  (`engine/runner/abilities/targeting.py`) commencent par
  `options = getattr(ability, "TARGETING_OPTIONS", None)` ; `None` ⇒ **retour 0 immédiat, aucun
  gate**. Le moteur accepte alors des casts que `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget`
  REFUSE (ami/ennemi, cible == caster, caster ayant bougé). La dégradation est **permissive** :
  ni erreur, ni crash — donc invisible en self-play, et c'est exactement le trou qu'un
  entraînement irait exploiter.
- **Dette RÉSORBÉE — re-mesurée le 2026-08-01** (compte re-dérivé du code, pas hérité —
  `python scripts/python/probe_181_targeting_gaps.py`) : `ABILITY_CLASSES` = **98 entrées**,
  **98** portent leur masque, **0 manquante**. Trajectoire des MANQUANTES : 75 → 53 → 40 → **0**,
  et le zéro tient depuis, à travers **quatre** entrées neuves (94 → 98 entre le 2026-07-30 et le
  2026-08-01). Le pendant `ABILITY_ATTACK_TYPE` est lui aussi à **0 manquant**.
  ⚠ **Zéro n'est pas un acquis, c'est un CLIQUET** : ce gisement est le seul que notre propre
  cadence de portage alimente — chaque ability entrée sans son masque le rouvre. La règle
  ci-dessus (masque posé DANS LE MÊME COMMIT) est donc désormais ce qui MAINTIENT le zéro,
  pas ce qui le vise.
  ⚠ Il ne le tenait PAS avant #430 : `probe_181` rendait `0` inconditionnellement — un inventaire
  déguisé en garde-fou, que cette ligne prescrivait pourtant de « faire passer ».
  ⚠ Ces chiffres se périment vite : les re-dériver plutôt que citer cette ligne.
- **Source du masque** : le littéral passé par `<X>Ability$$.ctor` à
  `IdunBattle.Core.Services.TargetingOptions$$.ctor`. **Piège** : l'overload **PRESET + flags**
  (`TargetingOptions..ctor(&opts, &preset, <flags>, 0)`, ex.
  `IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$.ctor`) — le littéral
  visible n'est PAS le masque effectif. Ne renseigner que les masques EFFECTIVEMENT lus ; recopier
  le littéral sans vérifier l'overload produit un masque FAUX, pire que l'absence.
- **Deuxième forme du piège, MESURÉE le 2026-07-27 (PR #126)** : certaines abilities
  **n'appellent AUCUN ctor** — elles recopient les 0x40 octets d'un champ **statique** de
  `TargetingOptions`, et le masque effectif est la constante écrite par
  `IdunBattle.Core.Services.TargetingOptions$$.cctor` à `<preset>+0x28`. Les presets ne sont pas
  interchangeables (`statics+0x168` = `0x4002`, `statics+0x68` = `0x4000`) : sur 10 abilities d'un
  même lot, 9 valaient `0x4002` et JakhalStimms `0x4000`. **Lire ability par ability, ne jamais
  généraliser « toutes les offensives valent X ».**

### Même règle pour `ABILITY_ATTACK_TYPE` — l'autre donnée obligatoire du registre

**Une ability qui entre dans `ABILITY_CLASSES` pose AUSSI son littéral `AbilityAttackType`,
DANS LE MÊME COMMIT.** C'est le pendant exact de la règle ci-dessus, sur l'axe DÉGÂT.

- **Pourquoi** : le garde-fou `probe_120` étape 0 le vérifie — et il **échouait sur `origin/master`**
  le 2026-07-27, sur trois abilities entrées sans leur littéral : `1036 FrenziedFiring` (`d2be96e`),
  puis `1041 BrazierOfHolyFire` et `1116 RadBombardment` (`825f69f`). Les deux dernières n'ont été
  découvertes **qu'au re-jeu après rebase** d'un autre agent : le trou ne s'était vu dans aucune des
  deux PR qui l'avaient creusé.
- **Même signature de dégradation** que `TARGETING_OPTIONS` : ni erreur ni crash, et **le seul
  gisement que notre propre cadence de portage aggrave** — chaque nouveau port l'alimente.
- **Comment** : relire le littéral au décompilé (jamais le déduire du nom de l'ability ni du profil
  de dégât).

!include .claude/skills/tacticus-re-port/SKILL.md

## Agents — invariants (valent AUSSI si tu es toi-même un agent qui en lance un)

Les solveurs disposent de tous les outils : **un agent lance couramment un `re-expert`**. Ces
règles ne sont donc pas réservées à l'orchestrateur — elles s'appliquent à quiconque dispatche.

1. **Toujours `isolation: "worktree"`**, sans exception. Sans elle, l'agent partage le working
   directory et peut corrompre l'arbre de son appelant (déjà vécu : un `return /float(...)`
   laissé dans `engine/utilities/tile.py` cassait tout l'import `engine`).
2. **Ne JAMAIS passer `model:`** à l'invocation. Le paramètre écrase le frontmatter et retombe
   sur la fenêtre 200 K — l'enum d'invocation ne sait pas exprimer le suffixe `[1m]`.
3. **Aucune étape 0 : un worktree frais est RUNNABLE par son seul checkout** (depuis le
   2026-07-26). `data/` est VERSIONNÉ et ne contient que des ENTRÉES — `symbols/`,
   `boards/`, `seed-bc.json`, `i2_en.json`. La junction vers l'arbre principal est
   SUPPRIMÉE : chaque agent lit les entrées de SON commit, et écrit ses sorties dans
   SON `logs/` (gitignoré), qui **meurt avec son worktree**. Corollaire : plus de
   discipline « nom unique par agent » sur les state-files, et un `worktree remove`
   ne peut plus rien détruire de partagé. **Rien de produit par un run ne va dans
   `data/`** — s'il y atterrit, il apparaît dans `git status`, et c'est le garde-fou.
   Deux gardes le tiennent (#349, après **25** sites trouvés sur **19** fichiers) :
   `probe_273 --only-scan` **étape 0c** rougit si un chemin `data/<x>` construit dans
   `scripts/python/**` ne désigne pas une entrée VERSIONNÉE, et `rl_duel --state-file` /
   `catalog_inject --out` **refusent** (rc 2) un chemin sous `data/` — ce second garde
   couvre les appelants hors Python, que le balayage ne voit pas.

   ⚠ **TROISIÈME catégorie, qu'un worktree ne verra JAMAIS** (mesurée par #273) : les
   artefacts écrits par un processus **hors du checkout** — le host Node (`frida/data/ai-traces`,
   `rl-batches`, `meta`) — ou par l'utilisateur (`.env`). Ce ne sont ni des entrées versionnées
   ni des sorties du run ; ils vivent dans l'arbre principal, et c'est correct. L'invariant ne
   promet pas qu'un worktree les voie. Ce qu'il exige, c'est qu'un lecteur **DISE qu'il ne les
   voit pas au lieu de rendre un zéro** : toute lecture d'une entrée gitignorée passe par
   `scripts/python/host_inputs.py` (tri-état `null` = pas mesuré / `[]` = mesuré et vide).
   Symptôme si on l'oublie : un
   balayage rend `0 fichier` et se lit comme « rien à signaler » — mesuré, `rl_ingest --all`
   ingérait **zéro** batch depuis un worktree, sans erreur.

   ⛔ **JAMAIS DE JUNCTION (ni lien symbolique) depuis ton worktree vers l'arbre principal.**
   Pas pour `node_modules`, pas pour `frida/hooks/probes`, pas pour `data/` — pour rien.
   **Pourquoi** : sous Windows, une suppression récursive forcée (`git worktree remove --force`,
   `Remove-Item -Recurse`) **SUIT le point de reparse et vide la CIBLE**. Mesuré le 2026-07-31 :
   `frida/hooks/scratch` a été détruit dans l'arbre principal par cette voie, et `frida/node_modules`
   amputé. Le bundle est devenu inconstructible. Un agent qui a « nettoyé sa junction avant de rendre
   la main » ne prouve rien : la destruction a lieu au `worktree remove`, après son départ.

   ⚠ **Ce qui rend une destruction IRRÉVERSIBLE, c'est le NON-VERSIONNEMENT — pas la junction.**
   Ces sondes étaient alors gitignorées : re-mesuré le 2026-08-05, l'arbre git juste avant
   `774df416` portait **0** entrée sous ce chemin (témoin : 2 733 entrées au total), donc **rien
   n'était récupérable depuis git** — un seul module a pu revenir, reconstruit depuis le bundle
   compilé. Elles vivent aujourd'hui sous **`frida/hooks/probes/`** (renommé par #480-r6 — le nom
   `scratch` déclarait jetable du code livré), **VERSIONNÉES** depuis #365 : **67 fichiers**, dont
   **66 dans le bundle**. Le danger d'aujourd'hui porte donc ailleurs — sur `frida/node_modules` (qui se
   réinstalle) et sur tout fichier laissé **non suivi**, que rien ne protège. La règle qui protège
   est en amont de l'interdiction : **une entrée de build se versionne**, et le cliquet
   `probe_480r1_entrees_de_build.py` interdit qu'on la redécrive comme jetable.
   **Si un build te manque une dépendance** : `npm ci` dans TON worktree (`package-lock.json` est
   versionné, ~10 s) — jamais un lien vers l'arbre du voisin. Si une **source** te manque, c'est
   qu'elle est gitignorée à tort : dis-le, ne la contourne pas. Le cliquet
   `probe_365_versioned_imports_gitignored.py` rougit sur cette faute (un fichier versionné qui
   importe statiquement une cible gitignorée ou absente).
4. **⛔ Ne (ré)injecter NI redémarrer le host TOI-MÊME, jamais.** Ce geste stoppe la session
   Frida et casse le harnais des autres agents. Il appartient à l'orchestrateur, qui dispose
   d'une procédure sûre (mode DRAIN). Si ton travail exige un reinject — un correctif
   `frida/hooks/*` à activer, un capteur neuf à poser — **livre le code et DIS-LE dans ton
   rapport** : la fenêtre sera planifiée. Tout le reste (mêmes fichiers, mêmes sujets, RPC
   concurrents, runners) est libre — un worktree est figé au commit de lancement, donc les
   éditions de l'appelant ne peuvent pas le perturber.

   Corollaire — **si un build de runner te revient en `503 runner creation paused`** : c'est une
   fenêtre de maintenance volontaire, **de quelques minutes**, pas une panne. Tu **ATTENDS, tu ne
   t'arrêtes PAS**. Dans cet ordre :

   1. **Commite immédiatement** ce que tu as, même partiel, même non validé. Un agent qui rend la
      main avec un worktree **PROPRE** le perd — il est auto-supprimé, et sa reprise repart
      silencieusement dans l'**arbre principal**, où il éditerait `master`.
   2. **Dispose TES runners** (jamais ceux des autres). C'est ce qui fait converger la fenêtre :
      tant qu'un runner traîne, la maintenance attend après toi.
   3. **Attends la réouverture** : `GET /api/admin/drain` jusqu'à `enabled == false`, en espaçant
      les sondages (pas de boucle serrée de retries sur le build lui-même — chaque refus est
      compté et n'avance à rien). Puis **reprends ton travail là où tu en étais**.
   4. Si la fenêtre dépasse largement l'échelle de la minute, **alors** seulement rends ton état :
      ce que tu as établi, ce qui reste à confronter, et **le montage exact** que tu comptais
      jouer — c'est ce qui te fera repartir vite quand je te reprendrai.

   Et dans tous les cas : **ne conclus RIEN de ce refus.** Ce n'est ni un « porteur non
   confrontable », ni un « régime inatteignable », ni un « montage impossible ». Écris
   « NON CONFRONTÉ — fenêtre DRAIN ».
5. **Une modif Python `engine/**` n'exige NI rebuild NI reinject** : ce code tourne dans le
   process pytest/probe et parle au runner par RPC. Seul `frida/hooks/*` vit dans Frida.
6. **Le worktree part de `origin/master`** — ni de la branche courante, ni des changements non
   commités. Pour qu'un agent voie du travail en cours : le commiter et le POUSSER d'abord.
7. **Un agent mis en pause avec un worktree PROPRE le PERD** — il est auto-supprimé (règle
   « auto-cleaned if unchanged »), et la reprise par `SendMessage` le fait repartir dans
   l'**arbre principal**, silencieusement : l'invariant 1 saute et l'agent édite `master`.
   Cause racine : une pause est rapportée `completed` — le harnais ne distingue pas « fini,
   rien à garder » de « en pause, n'a PAS ENCORE écrit ». Vise donc le profil « RE d'abord,
   édition ensuite » (un `re-expert`/`opus-solver` qui lit du décompilé 20 min avant sa
   première édition). **Parade, mesurée le 2026-07-26 : faire écrire l'agent TÔT** — une
   édition réelle, ou à défaut un fichier jetable `git add`-é. Un worktree SALE survit
   intégralement à la pause (cwd, index, branche, `master` non contaminé). À défaut, avant
   toute reprise d'un agent qui va écrire : lui faire vérifier `pwd` +
   `git rev-parse --show-toplevel`, et relancer un agent frais s'il n'y est plus.
   NB : dans `git worktree list`, `locked` = agent EN COURS d'exécution, **pas** « worktree
   conservé » — un agent arrêté mais sale apparaît `unlocked` et bien présent.

Le reste de la conduite de campagne (pipeline de dispatch — `opus-solver` et lui seul, workflow de
livraison par PR, reprise d'un agent par `SendMessage`, exploitation de la plateforme,
migration au changement de build) vit dans le skill **`tacticus-orchestration`**, chargé à la
demande — il ne sert qu'à l'orchestrateur et n'a pas à peser sur le contexte de chaque agent.

## Documentation détaillée

!include .claude/skills/tacticus/references/rpc-api.md
!include .claude/skills/tacticus/references/runner.md

<!-- TODO références à (ré)écrire contre le code actuel (les drafts d'avril
     dans .claude/worktrees/agent-a0e45617/ sont périmés) : frida-host.md,
     game-architecture.md, decompilation.md, ai-engine-audit.md, knowledge.md.
     Ne pas !include tant qu'ils n'existent pas dans ce tree (résolution à vide). -->

