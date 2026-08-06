# #485-r1-r1 — exécuter le sweep, et la cause qu'il a fait apparaître

`#485-r1` avait livré l'outil et sa preuve, **sans toucher une ligne d'`engine/`**. Cette tranche
l'applique. Elle a aussi trouvé, en l'appliquant, que le vice qu'on croyait résiduel (« 25 tests
mal écrits ») est une **propriété du langage**, et que le dépôt en porte une bombe **déjà armée**.

## Ce qui a été appliqué

| | avant | après |
|---|---:|---:|
| différés recensés dans `engine/**` | 308 | **169** |
| **PORTEURS** | 261 | **166** |
| **GRATUITS** | 47 | **3** |
| instructions différées (`probe_270r4r2r2`) | 349 | **211** |

Réécriture **2 022 symboles / 426 fichiers**, vidange **339 ré-exports / 17 barils**, hissage
**138** sites. Les chiffres se re-dérivent (`probe_485_imports_differes.py`,
`migrate_485r1_barils_reexport.py`) ; ne pas les citer.

⚠ **Les 3 gratuits restants ne sont pas un reliquat à finir** : ce sont des imports **optionnels**
sous `try/except` (`entities/effects/magnitude.py`, `playbook/nonattack.py`,
`services/custom_normal_attack.py`). Les hisser déplacerait l'échec du site d'appel — où il est
rattrapé — vers le chargement du module. Le refus `sous-try` est un **résultat**, et il est
déclaré dans la base attestée.

⚠ **La vidange a rendu 339 et non 284** parce que le passage en forme B (ci-dessous) a libéré
`triggers.dispatch` (−55) : les deux gestes ne sont pas indépendants, et le second **augmente** le
gain du premier.

## La coupe en trois commits de `#485-r1` était rouge par construction — MESURÉ

Elle prescrivait un commit 1 « re-cibler les 25 `PERD_LA_MORSURE`, aucun autre changement ». Ce
commit **ne peut pas être vert** : re-cibler un patch du baril vers l'enfant le rend inerte tant
que le consommateur lit le baril. Mesure, sur l'arbre du commit précédent, re-ciblage **seul** :
**7 failed / 35 passed** — exactement les 7 tests que la contre-épreuve fait rougir. Les deux
changements (réécriture d'`engine/` et re-ciblage des patchs) sont **mécaniquement couplés** ; ils
vivent donc dans le même commit. La séparation « empreinte nulle / non nulle » est préservée
autrement : l'empreinte de la **réécriture seule** est mesurée outil-à-outil (0 divergence sur
243 633 attributs), et les fichiers volontairement hors de ce périmètre sont **listés**.

## La vraie cause : la FORME de l'import, pas l'écriture du test

`probe_485r1r1_formes_dimport.py` — banc exécutable, trente lignes, même symbole, même patch :

| forme | avant patch | après patch | |
|---|---|---|---|
| **A** `from X import foo` au niveau module | VRAI | VRAI | **NE MORD PAS** |
| **B** `import X` / `from pkg import X`, puis `X.foo()` | VRAI | PATCHE | mord |
| **C** `from X import foo` **dans** la fonction | VRAI | PATCHE | mord, **par accident** |

**Hisser, c'est passer de C à A** — donc de « mord » à « ne mord pas ». C'est la cause exacte des
**28 fichiers rouges** de #484 et des **12 rouges** de la famille #429-r1. Le diagnostic écrit les
deux fois (« le test était mal écrit ») est **faux** : le test profitait d'une propriété que la
forme C lui donnait gratuitement, et que le hissage lui reprend.

⚠ **B est le seul point fixe**, et il ne coûte rien : mesure sur ce dépôt, `from pkg.sub.mod import
nom`, `from pkg.sub import mod` et `import pkg.sub.mod` chargent les **mêmes** modules —
**écart 0**. B ne rouvre donc aucun cycle. ⚠ **Il n'en résout aucun non plus** : un différé
PORTEUR le reste quelle que soit sa forme. Ce sont **deux problèmes distincts**, et les confondre
ferait croire qu'un changement de forme supprime un cycle.

⚠ **Corollaire, plus large que cette tranche** : un différé protège **son** site, mais la cascade
qu'il déclenche crée des liaisons de forme **A** dans tous les modules **traversés**, gelées dès le
premier chargement. Dans **une** passe pytest (un seul process), le verdict dépend alors de
l'**ORDRE des fichiers** — mesuré par l'étage [3] du banc : `interA` rend `VRAI` en
« charge-puis-patche » et `PATCHE` en « patche-en-premier » ; `interB` rend `PATCHE` dans les deux.
`-k`, `--deselect`, un fichier ajouté avant dans la passe, xdist qui redistribue : le verdict peut
changer sans qu'une ligne ait bougé. **Ce que le `430/430 modules s'importent seuls` du `CLAUDE.md`
protège vraiment**, c'est ça : chaque probe a son propre process, donc sa propre cascade. Une passe
pytest multi-fichiers n'a **pas** cette protection.

## Le recenseur qui manquait — l'axe HISSAGE

`substitutions` mesure ce que la **RÉÉCRITURE** fait à un patch. Il ne dit **rien** de ce que le
**HISSAGE** lui fait : autre axe, autre gisement. D'où `migrate_485r1_barils_reexport.py morsure`,
qui croise les substitutions du dépôt (**tout** `.py` — offline, `_live.py`, probes) avec les
différés que le cliquet #485 **prescrit de hisser**.

Sur `master` avant la tranche, sur **222** couples (module `engine`, attribut) substitués :

| | n |
|---|---:|
| `DEJA_INERTE` — ≥ 1 liaison forme A dans `engine/**` | **32** |
| `DIFFERE_MORDANT` — porteur, mord encore (fragile) | 13 |
| `HISSAGE_DESARMERAIT` — gratuit **et** substitué | **5** |
| sans liaison `from` dans `engine/**` (accès attributaire seul) | 172 |

⚠ **Les 5 sont une bombe déjà armée** : le cliquet #485 prescrivait, sur `master`, de hisser
47 différés — dont **5 auraient désarmé un patch**, deux d'entre eux dans des tests `_live.py`
(`test_381r3_neighbour_source_live.py`, `test_403_fly_no_expansion_gate_live.py`). Le prescripteur
et le gisement vivaient dans le même dépôt sans se voir.

À l'arrivée de la tranche : `HISSAGE_DESARMERAIT` = **0** — les cinq couples ont été traités
**avant** le hissage, en passant leurs quatre consommateurs en forme B. `DEJA_INERTE` = 33
(contre 32 sur `master`) : le sweep **ne résorbe pas** ce gisement-là, il ne l'aggrave pas non
plus, et il est chiffré en résidu.

## Ce qui a été passé en forme B, et pourquoi pas plus

**Huit modules**, en deux lots. Le premier (les 25 `PERD_LA_MORSURE`) :
`runner/operations/movement.py`, `runner/operations/damage.py`,
`runner/operations/damage_ops/normal.py`, `runner/abilities/handler.py`. Le second, dicté par
`morsure` **avant** le hissage : `entities/pathfinding/pathfinders.py`,
`playbook/prediction/normal_attack.py`, plus deux sites de plus dans `damage.py` et
`damage_ops/normal.py`.

`handler.py` est le cas qui tranche : son différé vers `triggers.dispatch.ability` est mesuré
**GRATUIT**, donc promis au hissage — en forme A il aurait rendu inertes trois patchs, dont deux
tests `_live.py`. En forme B, il est hissable **et** mordant.

**Le périmètre B complet est chiffré, pas exécuté** : rendre la banque ordre-indifférente
demanderait **49 modules / 75 liaisons** — borné, mais hors de cette tranche. Résidu `#485-r1-r3`.

## Ce que le sweep a CASSÉ, et les trois angles morts qui l'ont laissé passer

Le sweep a fait rougir **4 tests**. Aucun ne vient d'un choix de la tranche : les quatre viennent
d'un **recenseur qui ne visitait pas la voie concernée** — ou d'un étage qui faisait exactement ce
pour quoi il était écrit.

### Angle mort 1 — la vidange ne comptait pas l'ACCÈS ATTRIBUTAIRE

`vider_barils` réclamait tout un baril pour `import X as E` (l'accès y est attributaire, on ne sait
pas le suivre), **mais pas pour `from pkg import sous_module`** — qui lie pourtant un module lui
aussi. `NC.NATIVE_PRIORITY` était donc invisible : le recenseur n'y voyait qu'une réclamation du
nom `noncomparable` au baril PARENT.

Dégât mesuré : **4 couples**, dont **deux lus par `engine/**` lui-même** —
`ai/action_generators.py` → `noncomparable._has_valid_targets`, et
`playbook/{tile_targets,loki_custom,resurrection_orb}.py` → `dsl.DslContext`. **Aucun des tests
tombés ne les montrait.**

Cliquet : **`probe_485r1r1_acces_attributaires.py`**, qui résout chaque accès contre le module
RÉELLEMENT importé (il voit l'`AttributeError` avant qu'il soit joué). VERT sur `origin/master`,
ROUGE sur la branche avant réparation. Contre-épreuve du correctif : sans lui, la vidange
re-propose ces 4 mêmes ré-exports ; avec, **0**.

### Angle mort 2 — `DEJA_INERTE` absorbait `HISSAGE_DESARMERAIT`

Dans `recenser_morsure`, `DEJA_INERTE` était testé **en premier** et faisait `continue`. Dès
qu'UNE liaison de forme A existait quelque part — fût-ce dans un baril que personne n'appelle — le
couple sortait « rien à faire », et le site de forme C **qu'on s'apprêtait à hisser** n'était plus
examiné. `phase_end_triggers` avait A dans `runner/operations/triggers/__init__.py` **et** C dans
`runner/runner.py`, son consommateur RÉEL.

### Angle mort 3 — la base des GRATUITS était en retard d'une vidange

`morsure` lisait `ratchets-485-differes-attestes.json`, une base **attestée**. Or un différé est
gratuit **par rapport à un arbre** : sur `master`, charger `dispatch.phase` tirait `runner.runner`
(donc PORTEUR, donc absent de la base) ; **après** la vidange le même différé devient GRATUIT. La
mesure est désormais prise à FRAIS, et la commande **dit** sur quoi elle s'appuie.

### Ce que les trois corrections changent, mesuré

Sur l'arbre **post-vidange / pré-hissage**, `morsure` passe de **5** à **10**
`HISSAGE_DESARMERAIT`. Les 5 visibles à l'époque avaient été traités (forme B). Des 5 autres,
**deux** étaient restés en forme A pure :

| couple | patcheur | visible ? |
|---|---|---|
| `dispatch.phase.phase_end_triggers` | `test_389_ramming_speed_combat_offline` | test ROUGE |
| `active_ability.is_dead_unit_and_not_allowed_by_ability` | `probe_429r1r1r1` | **silencieux** |

Le second est le cas qui compte : son patcheur est un **probe**, que la banque ne joue jamais.
Deux sites (`operations/damage.py`, `operations/damage_ops/normal.py`) portaient le commentaire
`# lazy : cycle` sur `master` ; le hissage les a passés en forme A et la mesure du probe ne mord
plus — exactement la famille #429-r1 que cette tranche visait à ne pas rouvrir. Les trois sites
sont réparés **en forme B**.

**Bonus** : `existe_module` était **insensible à la CASSE** sous Windows. `from ... import
EFFECT_TRIGGERS` (une constante) répondait « module » à cause d'`effect_triggers.py` voisin, ce
qui classait le couple en forme B — « point fixe, rien à faire » — et liait le nom à un
pseudo-module qu'un lecteur ne peut pas importer.

## Les deux étages qui se sont RETOURNÉS — et c'est la preuve que le sweep marche

`test_270r1r1_container_enum_offline::etage4` et `test_270r1r1r3_role_enum_offline::etage6`
déplaçaient un mirror dans un arbre temporaire et **exigeaient l'`ImportError`**. Ils étaient
écrits pour se retourner le jour où le cycle disparaîtrait. Ce jour est celui de cette tranche.

**La mesure**, et non la supposition :

| | `origin/master` | après la vidange |
|---|---:|---:|
| modules `engine.*` chargés par `import engine.entities` | 94 | **2** |
| `entities/effects/loki/hits.py` chargé | VRAI | **FAUX** |

C'est ce module qui fermait la boucle. Conséquences actées :

- `services/static_battle_rules.py` : ses deux imports d'enum sont **remontés en tête** ;
  l'étage 4 exige désormais qu'ils y soient, que la copie mutée **s'importe**, et que la cascade
  du paquet reste **courte** (il rougira si elle ré-enfle).
- l'étage 6 **déplace pour de vrai** les deux mirrors sous `entities/abilities/`, réécrit **tous**
  leurs importeurs (17 fichiers — une liste écrite à la main ratait
  `entities/abilities/triggered_ability.py`, et l'échec de MONTAGE aurait été imputé au cycle) et
  exige que ça **passe**. Contre-épreuve : avec l'`__init__.py` de `master`, le même montage
  rend l'`ImportError` de module partiellement initialisé.
- les mirrors **restent** sous `engine/entities/` : c'est désormais un choix, pas une obligation.
  Le `CLAUDE.md` est corrigé en conséquence.

## La contre-épreuve, et ce qu'elle vaut

Le seul contrôle qui voit un désarmement **silencieux** n'est ni l'empreinte ni le compte : c'est
de **neutraliser la pose du stub** et de vérifier que le test **rougit**. Fait sur copie :
**7 tests rougissent**. Un test qui reste vert sans son stub ne mesure plus.

⚠ Ce contrôle n'a été **joué** que sur les fichiers **offline**. Les **14 sites en probes** et les
**2 sites live** sont re-ciblés et relus, non joués — les probes ne se jouent pas (ce sont des
mesures), et un test live coûte un runner. C'est nommé, pas comblé.

## Résidus

- **#485-r1-r2** — câbler la forme `charger_tout()` sur les **4 barils à registre**
  (`engine.playbook`, `runner.abilities.loki`, `runner.operations.triggers.loki`, `utilities`),
  prototypée par `prototype_485r1_registre_explicite.py`. Non fait ici : le cran qui compte n'est
  pas `charger_tout()` mais que **toute lecture avant chargement LÈVE**, ce qui change le **type**
  de quatre registres lus par le moteur et par les probes — et « la racine de composition » n'existe
  pas dans ce dépôt, où chaque probe entre par son propre module. À spécifier avant d'écrire.
- **#485-r1-r3** — passer en forme B les **49 modules / 75 liaisons** qui rendent la banque
  **ordre-dépendante**. Compte re-dérivable ; le gisement préexiste au sweep (**32** couples sur
  `master`, **29** après).
- **#485-r1-r4** — les **166 porteurs restants**. Chiffré, non exécuté
  (`probe_485r1r1_leviers_des_porteurs.py`), partition exhaustive :

  | | n | % |
  |---|---:|---:|
  | `PAR_UN_PAQUET` — tous les chemins du cycle traversent un `__init__.py` ⇒ **levier 2** | **104** | 62,7 |
  | `MODULE_A_MODULE` — dépendance mutuelle réelle entre feuilles ⇒ **levier 1** | 62 | 37,3 |
  | `SANS_CHEMIN` — angle mort du graphe déclaré | 0 | 0 |

  ⚠ **« Distribution diffuse ⇒ pas de second sweep » est FAUX, et c'est la mesure qui le dit.**
  C'est vrai par **cible** (58 cibles distinctes, top 5 = 26 %) — mais le levier 2 ne se compte
  pas par cible, il se compte par **paquet fermant** : `runner.abilities.loki` **29**,
  `runner.operations.damage_ops` **26**, `runner.abilities` **22**, `playbook` **21** —
  **98 des 104** sur **quatre** `__init__.py`. Le gisement a donc bien un foyer ; c'est
  l'unité de comptage qui le cachait.
