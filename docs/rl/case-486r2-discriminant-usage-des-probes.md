# #486-r2 — Le discriminant d'USAGE des probes, et l'élagage

**Verdict : 0 suppression.** Aucun des ~830 probes de premier niveau n'est *prouvablement mort*.
Ce qui manquait n'était pas une liste à couper, c'était l'**instrument qui permet de couper** —
il existe maintenant, il sait rougir, et il est sous cliquet.

Instrument : `scripts/python/probe_486r2_usage_des_probes.py`. Entrée de banque : `probe_486r2`.
Tous les chiffres ci-dessous se **re-dérivent** (`python probe_486r2_usage_des_probes.py`) ;
ils bougent à chaque probe livré. Ne pas les citer — les rejouer.

## 1. Deux axes, jamais confondus

| | |
|---|---|
| **USAGE** | le probe est-il encore **EXÉCUTABLE** ? Statique, sans le lancer (beaucoup tapent le live par RPC). |
| **CITATION** | qui le **nomme**, et **comment** ? Citation **EXÉCUTABLE** (lue à l'AST) vs simple **prose**. |

**« Rien ne le joue » n'est PAS « mort ».** Un probe est un instrument à main qu'on relance pour
re-dériver un chiffre (`reference_probes_are_not_tests` : 4 % d'assert). Le seul croisement qui
prouve la mort est **ORPHELIN** (nommé nulle part, union large) **ET NON EXÉCUTABLE**.

## 2. L'écueil : 22 faux positifs, et pourquoi

Une première tentative de discriminant « le probe résout-il encore ses imports ? » avait rendu
**22 morts, tous FAUX**. Cause : les probes posent
`sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))` puis
`from _charge_regime import ...` ; le détecteur cherchait le module **à côté du probe**.

Le discriminant **évalue symboliquement** les `sys.path` que le probe pose lui-même —
`Path(__file__).resolve().parent`, `.parents[k]`, `os.path.dirname/abspath/normpath/join`,
l'opérateur `/`, avec propagation des affectations de niveau module. Un argument qu'il ne sait
**pas** évaluer rend le probe **INDÉTERMINÉ**, jamais MORT.

Deux pièges mesurés en écrivant l'évaluateur, l'un et l'autre trouvés par l'auto-épreuve :

- `_dotted()` rend `None` sur `Path(__file__).resolve()` (la base est un `Call`, pas un `Name`) :
  un critère fondé sur le seul nom pointé rate **l'idiome le plus fréquent du dépôt** — exactement
  la forme des 22. Il faut lire `node.func.attr` **en plus** du nom pointé.
- accepter `path.insert` / `path.append` **nus** ramasse le BFS de `probe_124`, dont la variable
  locale s'appelle `path` : trois probes sortaient en INDÉTERMINÉ pour rien. Seule la forme pleine
  `sys.path.*` compte (le dépôt n'écrit nulle part `from sys import path` — vérifié).

## 3. Le critère d'exécutabilité

1. la source **compile** ;
2. chaque import de **niveau module** résout, contre `sys.path` modélisé + stdlib + site-packages,
   **transitivement** sur les modules du dépôt (un import cassé à la profondeur 2 empêche le probe
   de démarrer tout autant) ;
3. pour un `from X import Y` où `X` est du dépôt : `Y` est bien une liaison de `X`. C'est le
   critère de `probe_462r5`, dont les liaisons sont **réutilisées** (`liaisons_de`) et non
   ré-implémentées — un second détecteur dérivé ne vaut rien.

**Ce qui ne tue pas, et pourquoi** : un import **différé** (corps de `def`, `if TYPE_CHECKING`) —
il ne casse que la branche qui l'exécute ; un import gardé par `try/except ImportError` — l'auteur
a déclaré la dépendance optionnelle.

**LA BORNE ASSUMÉE.** Le dépôt ne porte **aucun manifeste de dépendances** (ni `requirements*.txt`,
ni `pyproject.toml`, ni `Pipfile` — vérifié). Un « module introuvable » a donc deux causes
indiscernables, et le seul discriminant disponible est l'existence de l'artefact dans l'arbre :

- artefact **présent** hors du `sys.path` du probe → le dépôt est accusé → **MORT** ;
- artefact **absent** → tierce partie non installée **ou** module supprimé → **INDÉTERMINÉ**.

Un module réellement supprimé sans homonyme atterrit donc en INDÉTERMINÉ, pas en MORT. La borne
penche du côté sûr : **on ne supprime jamais sur un doute**.

## 4. Ce qui garde le discriminant (joué à chaque passage)

- **étape 0** — 17 formes synthétiques : **6 attendues MORTES, 9 VIVANTES, 2 INDÉTERMINÉES**. Un
  détecteur qui déclarerait tout vivant (ou tout mort) passerait une épreuve unilatérale.
- **étape 0b** — la **règle du cliquet** elle-même, 4 scénarios. `probe_439` garde « ce cliquet
  *peut*-il rendre non nul ? » ; ceci garde « rougit-il sur **son** gisement ? ».
- **étape 2b** — les **29** porteurs de helper (9 helpers, dérivés) doivent rester VIVANTS.
- **étape 2c** — **MUTATION sur sources RÉELLES** : inserts `sys.path` retirés, les **14** imports
  concernés doivent être **SIGNALÉS**. C'est ce qui distingue « modélise `sys.path` » de
  « simplement laxiste ». Le lecteur de cette contre-épreuve a d'abord apparié des **chaînes de
  message** et rendu 9 faux rouges : il passe maintenant par un canal **machine** (`Usage.signales`).
- **étape 2d** — quatrième mode de mort **exploré et mesuré vide** : un `.py` cité dans une chaîne
  exécutable et absent de l'arbre. **14** probes concernés, **14 synthétiques** (fichiers de
  tmpdir des auto-épreuves). En faire un critère fabriquerait des rouges sur les cliquets les
  mieux gardés du dépôt.

**LE SOL** (`--confronter-import`, hors passage courant, ~6 min, purement offline) : chaque probe
est **réellement importé** en process frais. Mesure du 2026-08-06 (rejouée après rebase sur
`f1cdd32e`) : **827 réussis / 1 échec / 1 écarté**. L'unique échec est `probe_enum_dump_width`,
qui lève `HostInputUnavailable` — une entrée
gitignorée qu'un worktree ne voit pas (invariant 3, troisième catégorie) : **MONTAGE**, pas mort.
L'écarté (`probe_287r8_regles_battlequery_live`) lie du RPC live au niveau module et est
pré-filtré. **Le verdict statique ne ment donc pas** — c'est ce qui autorise à conclure que
0 suppression n'est pas un artefact d'indulgence.

## 5. La partition (exhaustive, re-dérivable)

Mesure du 2026-08-06 sur `f1cdd32e`, population **dérivée de `git ls-files`**
(`scripts/python/probe_*.py` sans sous-répertoire — **0** `probe_*.py` écarté ailleurs) :

| seau | n | usage |
|---|---:|---|
| CLIQUET (banque) | 36 | 36 vivants |
| JOUÉ PAR TEST | 329 | 329 vivants |
| JOUÉ PAR SCRIPT | 67 | 67 vivants |
| PROSE SEULE | 370 | 370 vivants |
| ORPHELIN | 27 | 27 vivants |
| **SOMME** | **829** | **0 mort, 0 indéterminé** |

**PROSE SEULE est le seau le plus peuplé** (44,6 %) : une case-doc cite son probe *pour toujours*,
la citation en prose enregistre l'**histoire**, pas l'**usage**. C'est pourquoi la règle « garder
ce qui est cité dans un document » ne coupe rien — et pourquoi elle n'est pas le critère.

**Mention ≠ exécution**, et le cran se paie : en comptant toute mention dans `tests/` plutôt que
la citation exécutable, la mesure d'ouverture de #486-r2 rendait **442** probes « joués par un
test » contre **319** réellement — **123 de trop**, nommés dans un commentaire ou une docstring.
La citation exécutable exclut donc tout `Expr(Constant(str))` (docstrings et chaînes flottantes) ;
les commentaires `#` ne sont pas dans l'AST.

## 6. La portée du critère de MENTION — quatre corpus, mesurés

Deux axes : la **forme** du nom (préfixe à la frontière de composant vs stem plein) et la
**source** (l'arbre seul vs l'arbre + ce qui n'y est pas : messages de commit `--all`, corps des PR).

| corpus | orphelins |
|---|---:|
| PRÉFIXE + hors-arbre (**RETENU**) | 27 |
| PRÉFIXE, arbre seul | 45 |
| stem PLEIN + hors-arbre | 38 |
| stem PLEIN, arbre seul | 53 |

Le retenu est **le plus large**, donc celui qui rend le **moins** d'orphelins, donc celui qui
supprimerait le moins. Le préfixe est nécessaire : la prose écrit `probe_181`, jamais
`probe_181_targeting_gaps`. La frontière de composant interdit `probe_46` de désigner
`probe_462r5_…`. Les **26** probes que seul le critère le plus étroit accuse sont **LISTÉS** par
l'outil, jamais supprimés — un critère plus étroit ne prouve pas une mort, il fabrique un suspect.

## 7. Le cliquet, et son tri-état

**ROUGE** : un probe à la fois ORPHELIN et NON EXÉCUTABLE. Contre-épreuve jouée sur le dépôt réel
(probe jetable injecté et indexé) : `rc=1`, le probe est nommé avec sa cause.

**NON MESURÉ (99)** : `git ls-files` muet ou liste vide, banque illisible — et surtout, **une
accusation portée sans le corps des PR**. L'asymétrie est le point : ne pas lire les PR ne peut
qu'**ajouter** des mentions, donc **rétrécir** l'ensemble des orphelins ; un `PASS` sans `gh`
reste valide, une **accusation** ne l'est pas — le squash-merge ne recopie pas le corps d'une PR
dans l'arbre (#468-r11). Vérifié : `--sans-pr` sur le dépôt injecté rend **99**, pas 1.

## 8. Ce que le discriminant NE voit PAS

- une mort **fonctionnelle** : un probe qui démarre mais dont le RPC, le hook ou le champ de
  réponse a disparu. Il faudrait le **lancer**, donc taper le live.
- une chaîne d'invocation **dynamique** : `importlib`, un nom de script assemblé à l'exécution, un
  probe lancé à la main par un humain. Aucun de ces chemins ne laisse de trace à l'AST.
- un probe nommé **sans son préfixe `probe_`** (« la sonde 49b », « probe 133 ») : hors du motif de
  mention. Direction sûre — cela ne peut que **sur**-compter les orphelins, jamais en cacher un.
- les **PR de plus de 200 rangs** (limite `gh`), et un numéro pris par un agent qui n'a encore rien
  écrit (même angle mort que `probe_468 --suggere`).

## 9. Résidus

- **`#486-r6`** — *distinguer « tierce partie non installée » de « module supprimé »* (§3). Le
  dépôt n'a pas de manifeste de dépendances ; tant qu'il n'en a pas, un module réellement supprimé
  sort en INDÉTERMINÉ et n'est jamais candidat à l'élagage. Poser un manifeste (même minimal)
  transformerait cette borne en verdict.
- **Renommage / déplacement** : hors périmètre, et volontairement — on ne renomme pas ce qu'on
  s'apprête à supprimer. L'ordre est maintenant inversé : rien n'est à supprimer, donc le
  renommage peut se faire sans attendre.

## 10. Hors sujet, mais mesuré en passant

`probe_471_tri_etat_cliquets.py` est **ROUGE sur `master`**, indépendamment de #486-r2 (vérifié en
le rejouant sans aucune modification non commitée). Sa contre-épreuve lance `probe_457` dans un
faux dépôt ; or `probe_457` **refuse de tourner** depuis `d82ec527` (2026-08-05, retrait de la
banque de la doctrine par l'utilisateur) et rend **99**. Le scénario VERT attend 0. S'y ajoute un
bug latent : `probe_471.py:293` imprime `l[:110]` alors que la variable de boucle s'appelle
`ligne` → `NameError` dans le chemin de diagnostic, donc la contre-épreuve **crashe au lieu de
rapporter**. Deux lignes à corriger, et une décision de doctrine à prendre (poser
`TACTICUS_ALLOW_RATCHETS=1` dans le montage, ou retirer l'entrée) — elle n'appartient pas à cette
tranche.

⚠ Corollaire pour le cliquet de §7 : la banque **n'est plus jouée automatiquement** (elle reste
« lançable à la demande », cf. `d82ec527`). L'entrée `probe_486r2` est donc un **instrument
enregistré**, pas une barrière de PR.
