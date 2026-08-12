# #935-r1 — L'empreinte savait déjà quels `.py` un cliquet BALAIE ; la sélection ne le lui demandait pas

**Base** : `origin/master` = `906b097b`. 100 % offline (aucun runner, aucun RPC, aucune session Frida).

## 1. Le fait, et pourquoi il n'était pas une question d'étroitesse

`probe_457 --since <merge>~1` manquait **6 des 13** cas rouges attribués par #935 — dont quatre à
**90 % de périmètre retenu**. Une sélection qui garde neuf dixièmes du périmètre et rate quand même
le cliquet fautif ne souffre pas d'un réglage : il lui manque un **AXE**.

`impacted_files` traitait les `.py` par le **seul graphe d'imports** ; l'empreinte (`dirs`) ne
servait que pour les changements **hors-`.py`**. Or un `.py` s'ouvre pour deux raisons sans rapport :
parce qu'on l'**importe**, ou parce qu'un test-BALAYAGE le lit comme **donnée** (`ast.parse` d'un
inventaire, `inspect.getsource` d'un foyer). La seconde n'a **aucune arête** dans le graphe.

## 2. La cause était LUE et écrite, jamais comblée

Le commentaire de #464-r2 la nomme mot pour mot :

> rien ne distingue, dans une empreinte déjà écrite, la lecture d'IMPORT de la lecture APPLICATIVE
> d'un `.py` par un conftest-balayage (qui n'est couverte par rien). **Le régime est garanti à
> l'ÉCRITURE, où l'information existe encore.**

Elle existe littéralement : au moment du `open`, la **frame appelante** dit qui lit. La machinerie
d'import passe par `<frozen importlib._bootstrap_external>.get_data` ; tout le reste est du code
applicatif. `_FilesPerTest._vient_d_un_import` ne regarde que la frame **immédiate**, et c'est
délibéré — un balayage déclenché *pendant* un import a bien une frame d'import plus haut dans sa
pile, et le compter comme import **effacerait** une dépendance réelle.

## 3. Ce qui est livré

**Un troisième axe dans l'empreinte**, `py` : les répertoires des `.py` lus **applicativement**,
écrits pour chaque entrée mesurée, **liste vide comprise** (même tri-état que `dirs` : clé absente
= axe non mesuré, jamais « ne balaie rien »). Le **FORMAT reste 2** : les clés sont additives, et
le bumper aurait rendu l'empreinte entière illisible (`TOUT rejoue`) jusqu'à une passe complète de
763 s — une dégradation plus grande que l'angle mort qu'on ferme.

**Un tri-état pour la SOUS-TRAITANCE**, `fils`. Un test qui lance un processus fils n'ouvre rien
lui-même : `test_host_inputs_offline.py` joue `probe_273` en entier et son empreinte mesurée est
littéralement `dirs: []`, `temoins: []` — ce qui se lit « il ne dépend de rien ». L'audit hook ne
franchit pas la frontière de process, donc cet axe n'est pas **vide**, il est **non mesurable** :
l'entrée le dit, et la sélection le rejoue sur tout changement `.py` (jamais sur un diff
documentaire — la sous-traitance ne dégénère pas en `toujours`).

**Un REPLI nommé pour les entrées antérieures.** Une entrée sans la clé `py` retombe sur les `.py`
de ses `temoins`. Ce repli ne sait pas séparer import et lecture applicative — il **sur-sélectionne
et le DIT** (`balayage .py (repli temoins)` dans la raison). Il s'éteint entrée par entrée à mesure
qu'une passe les remesure. Mesuré sur les 7 entrées qui portent **les deux** : le repli rend
**exactement** le même ensemble que l'axe mesuré (0 écart dans les deux sens) — parce qu'en régime
préchauffé les imports lisent le `.pyc` du miroir, **hors du checkout**, donc n'entrent jamais dans
l'empreinte. C'est ce que le préchauffage garantit ; le discriminant, lui, garantit la même chose
quand le régime est froid.

**`--measure-only <liste>`.** Un axe neuf périme toutes les entrées d'un coup, et
`--measure-missing` ne peut rien pour elles (son critère est l'**absence** d'entrée). Sans ce mode,
le seul geste capable de rafraîchir une entrée est la passe complète — exactement l'incitation que
#547-r6 nomme : « un rouge qu'on ne peut éteindre qu'en payant la passe complète » est la forme qui
fait désarmer un cliquet.

**Le retrait de SA PROPRE source.** pytest lit le source d'un test **qui tombe** pour composer sa
traceback. Sans ce retrait, tout fichier **rouge** se déclarerait balayeur du répertoire de ses
voisins de test — une dépendance fabriquée par son propre échec. Il reste couvert par la cause
`diff` (un fichier de test modifié est toujours retenu), donc rien n'est perdu.

## 4. La mesure — avant / après, sur les mêmes merges témoins

Méthode de `case-935` §2 : worktree **détaché** au commit de chaque merge, `probe_457 --since
<merge>~1 --list` joué **sur l'arbre de ce merge**, l'empreinte étant celle qui y est versionnée.
Le régime « après » est donc celui du **repli** — l'empreinte de ces commits n'a évidemment pas
l'axe.

| merge | AVANT | APRÈS | cliquet rouge | rattrapé ? |
|---|---|---|---|---|
| #911 | 45/313 | **68/313** | `test_314_absolute_repo_path` | **oui** |
| #911 | 45/313 | 68/313 | `test_host_inputs` | non — cf. §4.1 |
| #888 | 273/305 | **289/305** | `test_366_r1_bcpatch_port_blindspot` | **oui** |
| #893 | 275/307 | **291/307** | `test_step_ordinal_ratchet` | **oui** |
| #900 | 283/309 | **296/309** | `test_449_r2_spread_face_combat` | **oui** |
| #909 | 284/312 | **297/312** | `test_366_r1_bcpatch_port_blindspot` | **oui** |
| #913 | 288/315 | 301/315 | `test_host_inputs` | oui (déjà avant) |
| #922 | 189/318 | 209/318 | `test_337_dsl_triggers_attestation` | oui (déjà avant) |
| #923 | 319/319 | 319/319 | `test_host_inputs` | oui (déjà avant) |
| #924 | 292/320 | 306/320 | `test_485r2` + `test_463r1` | oui (déjà avant) |
| #926 | 292/322 | 307/322 | `test_463r1` | oui (déjà avant) |
| #927 | 189/323 | 214/323 | `test_463r1` | oui (déjà avant) |

**6 manqués → 1.** Périmètre moyen retenu : **74,8 % → 79,9 %**, soit **+5,1 points** — de **+13 à
+25 fichiers** par merge, tous imputés à la cause neuve (`balayage .py (repli temoins)` dans la
ventilation). **Ce n'est pas « presque tout »**, et le cas le plus économe le montre : le merge
d'outillage #911 passe de 14 % à **22 %**, pas à 100 %.

⚠ La médiane de rétention était **déjà** de 90 % avant cette tranche, et la cause est structurelle
(un merge de ce dépôt touche `engine/**`, dont la clôture arrière du graphe remonte vers presque
tout le périmètre). Cette tranche ne la répare pas et ne le prétend pas : elle ferme l'**angle
mort**, pas le coût.

### 4.1 Le rattrapage est-il CAUSAL, ou incident ?

Un cas rattrapé par sur-sélection ne compte pas. Vérification : pour chacun, on intersecte l'axe du
test avec les répertoires des `.py` du diff et l'on regarde si le fichier **que le cliquet accuse**
y est.

* `test_314` / #911 — 4 `.py` au diff, **4** dans l'axe, dont `probe_468_collision_numeros.py`,
  l'accusé exact. **CAUSAL.**
* `test_366_r1` / #888 — 8/8 dans l'axe, dont `probe_605_hellfire_hits.py`. **CAUSAL.**
* `test_step_ordinal` / #893 — 7/7 dans l'axe, dont `probe_893_crusade_of_wrath_events.py`.
  **CAUSAL.**
* `test_366_r1` / #909 — 12/12 dans l'axe, dont `engine/predict.py`. **CAUSAL.**
* `test_449_r2` / #900 — 17 des 19 `.py` du diff dans l'axe, dont `engine/dsl/base.py`, qui porte
  le nœud `UseNormalAttack` accusé ; `probe_449r2_spread_inventory.py` `rglob('*.py')` **tout**
  `engine/`, donc chacun des 17 est une dépendance réelle. **CAUSAL.**

**Le sixième cas, `test_host_inputs` à #911, ne se rattrape PAS par le repli** — et c'est cohérent :
il sous-traite, donc son empreinte est vide, donc il n'y a **rien** sur quoi retomber. Ce que la
réparation lui apporte est le marqueur `fils`, qui n'existe que dans une entrée **re-mesurée**.
Vérifié en transplantant l'entrée mesurée aujourd'hui dans l'arbre témoin de #911 — transplant
légitime, `git diff 38b8e1b5 906b097b` étant **vide** sur `test_host_inputs_offline.py`,
`host_inputs.py` et `probe_273_gitignored_inputs.py` : sélection **69/313**, cible **RETENUE**,
cause `sous-traite 1`. **0 manqué sur 13** une fois l'empreinte à jour.

### 4.2 La propriété de sûreté

Le mécanisme est **purement additif** : il ne peut pas fabriquer de faux vert, au pire il fait
payer du temps de test. C'est gardé (`test_l_axe_py_n_OTE_jamais_un_fichier_de_la_selection`).

## 5. Volet (a) — la contre-épreuve de `probe_935`, et les 19 faux négatifs qu'elle a trouvés

`probe_935` classe INSÉLECTIONNABLE par lecture d'AST. Sa doc annonçait que le compte des deux
classes est imprimé « donc une dérive de l'approximation se voit ». **Rien ne la voyait** : un
compte imprimé n'est pas un garde-fou — le vice exact de `probe_181` avant #430.

`probe_935r1_contre_epreuve_classes.py` oppose à cette **déduction** une **mesure** (l'axe `py`, ou
le repli témoins, source dite ligne à ligne). Les deux sens n'ont pas le même poids :

* **sur-approximation** (AST dit balayeur, la mesure n'en voit pas) — le prix est du temps de test.
  Tolérée, comptée, ventilée par module accusant ;
* **faux négatif** (AST dit sélectionnable, la mesure voit un balayage) — le prix est un cliquet
  qu'une composition `{insélectionnables} ∪ {sélection}` laisserait tomber. **INVARIANT à zéro.**

**Premier passage : 19 faux négatifs.** Trois formes, toutes réelles :

1. **`inspect.getsource(...)`** (17 cas) — aucune énumération n'est en jeu, donc le critère par
   appel de balayage était structurellement aveugle. L'arête est pourtant réelle : le test change
   d'avis quand le **corps** de la fonction lue change, ce qu'aucun `import` ne dit ;
2. **l'import DYNAMIQUE** — `test_519_comptes_derives_offline.py` charge
   `probe_519_comptes_de_table` par `importlib.import_module("…")` : la clôture s'arrêtait là et le
   balayage du probe restait invisible ;
3. **`Path(MODULE.__file__).read_text()`** et `p = _PYDIR / … / "normal.py"` puis `p.read_text()` —
   le chemin et sa lecture sont deux instructions, donc un critère exigeant le littéral **dans**
   l'appel les rate.

Après extension du critère (les trois formes, plus une liaison de nom simple) : **0 faux négatif**,
classe **180 / 155**, accords **257**, sur-approximations **76 (22,8 % des confrontables)**,
**2 non confrontables** — une entrée absente sort en NON CONFRONTABLE, **jamais** en accord.

⚠ Deux des dix-neuf premiers n'étaient pas des balayeurs : leur seul `.py` mesuré était **leur
propre source**, lue par la traceback de pytest parce qu'ils sont **rouges**. D'où le retrait du §3.

### 5.1 Le plafond de sur-approximation est un détecteur de RÉGIME, et c'est délibératif

Un cliquet sur le **compte absolu** rougirait dès qu'un fichier de test neuf entre par un module
déjà balayeur — `symbols_layout.py` en accuse **15** à lui seul, pour **55** modules accusants
distincts. Toute PR sans rapport paierait la maintenance d'un artefact partagé : l'incitation exacte
qui fait désarmer un cliquet. Ce qu'on veut voir est la **dégénérescence du critère**, et elle est
massive quand elle arrive — mesure de #935, un critère par nom d'appel seul rendait **289
insélectionnables sur 323**. Le plafond est donc un **taux** (35 % pour 22,8 % mesurés).
L'**invariant**, lui, ne tolère rien : faux négatifs `== 0`.

## 6. Contre-épreuves de la réparation elle-même

Chaque cran a été **muté** et le cliquet doit rougir :

| mutation | tests tombés |
|---|---|
| la branche `balayage .py` + `sous-traite` neutralisées | **3** |
| `_vient_d_un_import` rendu `False` (le discriminant désarmé) | **1** |
| le retrait de sa propre source, à l'écriture | **1** |
| le retrait de sa propre source, dans le repli | **1** |
| un faux négatif **injecté** dans la contre-épreuve | elle le VOIT |

⚠ Une contre-épreuve d'écriture a d'abord été **fausse** : l'événement d'audit `open` couvre aussi
les **écritures**, et la sonde posée par la fixture enregistrait le `write_text` qui **fabrique** le
module du cas — donc l'import « entrait dans l'axe » pour une raison qui n'était pas la sienne. La
fixture est devenue une **fabrique** : les fichiers se créent AVANT la sonde.

Coût du parc, mesuré : `probe_935` **79,0 s → 16,1 s** (mémoïsation du parse de la clôture ;
`_module_local` en `lru_cache`), et sa sortie est devenue **déterministe** — `_imports_locaux` rend
un `set`, donc le module **accusé** changeait d'un run à l'autre (20 lignes sur 160) sans que la
classe bouge. `probe_935r1` : **24,7 s**. `tests/test_935r1_axe_py_offline.py` : **27 tests, 28 s**.

## 7. Ce qui n'est PAS couvert

* **L'axe `py` n'est MESURÉ que pour 10 entrées sur 336** ; les 326 autres passent par le repli
  témoins, qui ne sait pas séparer import et lecture applicative. Le repli est prouvé **identique**
  à l'axe sur les 7 entrées qui portent les deux, mais cette égalité tient au **régime préchauffé**,
  pas à une propriété du repli. Une passe `--measure` complète la referme. Résidu **#935-r2**.
* **La sous-traitance est rendue grossièrement** : `fils: true` ⇒ rejeu sur **tout** changement
  `.py`. Instrumenter le process fils (propager l'audit hook, ou lire ce qu'il ouvre) donnerait le
  vrai axe. Résidu **#935-r2**.
* **La sur-approximation de `probe_935` (76) n'est pas résorbée**, seulement mesurée et bornée en
  régime. Les 15 cas de `symbols_layout.py` viennent d'un module partagé dont un `iterdir` suffit à
  contaminer toute la clôture.
* **Deux rouges de `probe_486r15` restent** (`test_940_kiss_of_death_offline`,
  `test_932_deathwing_offline` : déclarations trop étroites), et ils sont **antérieurs** — hors
  périmètre de cette tranche.
* **`tests/test_449_r2_spread_face_combat_offline.py` est ROUGE sur `906b097b`** (4 tests),
  attribué sur arbre témoin détaché **avant** toute édition. Il n'est nommé ni par #934 ni par la
  liste des neuf de #941-r1 : c'est un **dixième** rouge non nommé de cette famille.
* **Aucune confrontation live** : tout est offline, aucune session n'a été touchée.
