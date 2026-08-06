# #484 -- les rouges PERMANENTS de `master` : re-derivation, ventilation, cause unique

**Mesure re-derivee le 2026-08-06** sur `origin/master` = `959189f2`, worktree propre,
`probe_457_offline_tests_green.py` en 8 shards (`TACTICUS_ALLOW_RATCHETS=1`) :

| | |
| --- | --- |
| perimetre (`not name.endswith("_live.py")`) | **213** fichiers |
| shards rouges | **6 / 8** (`s1 s2 s3 s5 s6 s7`) |
| tests en echec | **42** |
| fichiers porteurs | **13** |

Le compte rapporte par l'agent de `#477-r33` etait **40**. L'ecart de **+2** n'est pas une
derive de mesure : ce sont deux gisements a SEUIL (`test_270r4r2r2::etage3`,
`test_270r4r2r2r3::etage6`) que des PR mergees entre-temps ont fait franchir. Les rouges se
comptent donc a la HAUSSE tant que personne ne les traite -- c'est le comportement attendu
d'un cliquet, et la raison pour laquelle un rouge permanent est pire qu'absent : il encaisse
la degradation sans que quiconque le lise.

## 1. LA CAUSE UNIQUE -- `492c722f`, et elle porte 25 des 42

> `refactor(#270-r4-r2-r2): hisser 624 imports differes d'engine/ au niveau module`
> (2026-08-05, 144 fichiers, 671 insertions / 707 suppressions)

Ce refactor est **value-preserving a l'execution** -- sa propre mesure le dit (0 divergence de
VALEUR sur 197 017 attributs) -- et c'est exactement ce qui l'a rendu invisible : il ne change
pas ce que le code CALCULE, il change **ou le nom est LIE**.

```python
# AVANT (differe, dans le corps de la fonction)
def invalid_caster_reason(...):
    from ..runner.abilities.targeting import targeting_options_for   # lu a CHAQUE appel
    opts = targeting_options_for(aid)

# APRES (hisse au niveau module)
from ..runner.abilities.targeting import targeting_options_for       # lu UNE fois, a l'import
```

Un `import` differe re-resout l'attribut **du module source** a chaque appel : un
`monkeypatch.setattr(<module source>, "<nom>", stub)` mord. Hisse, le nom est copie dans le
namespace du CONSOMMATEUR au moment de l'import -- le patch pose sur la source ne mord **plus
jamais**. Les tests concernes n'ont pas commence a mesurer FAUX : ils ont cesse de **mesurer**.

**Signature commune, et elle est reconnaissable** : ce ne sont pas des ecarts de valeur, ce
sont des messages d'auto-controle -- *« le montage ne teste rien »*, *« le mutant rend la MEME
valeur »*, *« observe 0 »*, `assert None == <attendu>`. Ces tests ont ete ecrits avec la garde
qui detecte leur propre inertie ; elle a fonctionne. Sans elle, les 25 seraient **VERTS et
vides**, ce qui est le vrai cout evite ici.

| test | site du patch | consommateur qui lie desormais au module | fails |
| --- | --- | --- | --- |
| `test_433_..._caster_reason_offline.py` | `TGT.targeting_options_for` | `engine/services/ability_caster_gates.py` | **21** |
| `test_344r2_sort_attackers_prediction_offline.py` | `engine.services.damage_prediction.get_attack_prediction` | `engine/runner/abilities/darkangels.py` | **2** |
| `test_383_ramming_speed_explosion_offline.py` | `PA.generate_multi_hit_attack_prediction` | `engine/playbook/prediction/ramming_speed.py` | **1** |
| `test_448_r1_r1_r1_r1_flying_tiles_moved_offline.py` | `_F.is_like_flying` | `engine/services/movement_query.py` | **1** |

Les quatre lignes hissees sont VISIBLES dans le diff de `492c722f` :
`ability_caster_gates.py` (`targeting_options_for`), `darkangels.py` (`get_attack_prediction`),
`ramming_speed.py` (`generate_multi_hit_attack_prediction`), `movement_query.py`
(`is_like_flying`).

### 1bis. Le degat NE SE LIT PAS au nombre de rouges

`test_383` le montre : **trois** tests partagent le meme montage `_capture`, **un seul**
rougit. Les deux autres passent parce qu'ils n'assertionnent que sur la valeur de retour
(`evs`), que le vrai service continue de produire -- ils sont devenus des tests du **code
reel** la ou ils devaient tester le **cablage**. Meme forme sur `test_344r2` : deux des trois
parametres de `test_each_test_is_read_on_its_own_prediction` attendent `weak-first`, qui est
aussi l'ordre des ids en cas d'egalite -- ils passent **par coincidence**. Le rouge sous-compte
donc le degat : **42 rouges** signalent un nombre inconnu et superieur de tests **devenus
vacueux**.

### 1ter. La reparation, et pourquoi elle ne touche AUCUN contrat

On deplace le site d'injection la ou le nom est **effectivement lu** -- le module
CONSOMMATEUR -- sans toucher une seule assertion, une seule valeur attendue, un seul
`parametrize`. Le contrat teste (l'ordre des onze clauses, l'appariement borne <-> prediction,
la branche volante) est inchange. C'est la seule reparation qui soit mecanique ici :
re-differer les imports rouvrirait le gisement que `492c722f` a ferme, et le cliquet
`test_270r4r2r2` l'interdit executablement.

## 2. Ventilation des 42 -- la somme vaut le total

| # | famille | fichiers | verdict |
| ---: | --- | --- | --- |
| **28** | MONTAGE coupe par un hissage d'import (`492c722f`) | 433, 344r2, 381r4, 383, 448 | **REPARE** |
| **2** | test PERIME par un changement DELIBERE | 381r1 (#287-r5-r1), 270r4 etage5 (#270-r4-r2) | **REPARE** (contrat change, dit) |
| **4** | DETTE d'import differe rouverte par notre cadence | 270r4r2r2 etage1, 270r4r2r2r3 etages 1 et 6, 270r4r2r2 etage3 | **3 REPARES, 1 NOMME (#484-r2)** |
| **2** | RECENSEMENT non tenu a jour | 337 (attestation), 366-r1 (trou de couverture) | **REPARE** |
| **5** | ENTREE de donnees devenue muette | `test_enum_ordinal_ratchet` | **REPARE** |
| **1** | CONTENTION, pas un verdict | 480r8 | **NON REPRODUIT** (2 re-jeux) |
| **42** | | **13 fichiers** | **41 fermes, 1 nomme (#484-r2)** |

Aucun des 42 n'accuse un **defaut de calcul du port**. C'est le resultat le plus important de
cette tranche, et il n'etait pas acquis d'avance : la moitie des messages ressemblait a des
divergences (`assert None == 16`, `ordre observe [2, 3], attendu [3, 2]`).

### 2.1. Vacuite -- ce que le compte de rouges SOUS-ESTIME

Le rouge ne mesure pas le degat, il en mesure la partie **assertionnee**. Deux mesures :

* `test_383` -- **trois** tests partagent le montage `_capture`, **un seul** rougit. Les deux
  autres n'assertionnent que sur la valeur de retour, que le VRAI service continue de produire :
  ils sont devenus des tests du **code reel** la ou ils devaient tester le **cablage**.
* `test_344r2` -- deux des trois parametres de `test_each_test_is_read_on_its_own_prediction`
  attendent `weak-first`, qui est aussi l'ordre des ids **a cle egale**. Ils passaient donc par
  COINCIDENCE, avec un stub qui n'etait jamais appele.

⇒ **42 rouges signalent un nombre inconnu et SUPERIEUR de tests devenus vacueux.** La parade
posee ici est une **garde d'inertie** au montage (`test_433`, `test_381r4`) : le montage
ASSERTIONNE que sa propre mutation a mordu, avant de mesurer quoi que ce soit.

### 2.2. Datation -- deux regimes, deux traitements

Toutes les causes sont **recentes** (2026-08-05 et 2026-08-06). Aucun rouge ne « traine depuis
trois semaines » : ce gisement est **integralement produit par notre propre cadence de PR**, ce
qui est cohérent avec le retrait de la banque de cliquets le 2026-08-05 -- plus rien ne les
voyait.

| cause | date | ce qu'elle a rougi |
| --- | --- | --- |
| `492c722f` hissage de 624 imports | 2026-08-05 | 28 |
| `980173f9` fermeture du cycle sans conversion | 2026-08-05 | 1 |
| `d696530f` (#722) tuile de depart hors du pool | 2026-08-06 | 1 (+4 differes gratuits) |
| `c919fdd9` (#707) cles par constante d'enum | 2026-08-06 | 1 |
| `630a9c59` (#699) archivage PARTIEL d'un build | 2026-08-06 | 5 |
| accretion `#419-r3` / `#419-r1-tr14` | 2026-08-06 | 2 differes gratuits, +3 sur le seuil |

Bisection reelle pour les deux datations non triviales : `test_366_r1` (vert a `0b8982a9`,
rouge a `c919fdd9`) et le comptage des differes (`git archive` de `492c722f` re-collecte :
**347**, contre **349** aujourd'hui).

## 3. Ce qui n'est PAS repare, et pourquoi

### `#484-r2` -- `test_270r4r2r2::etage3`, un SEUIL que notre cadence depasse

`349` instructions differees sous `engine/` pour un plafond de `346`. Mesure du delta depuis
`492c722f` : **+15 sites, -13 sites**, net **+2** (l'arbre de reference en portait 347, et le
plafond a ete BAISSE a 346 par `dda52692`, comme sa docstring le prescrit).

**Rien n'est mecaniquement retirable** : l'etage 1 du meme fichier -- l'INVARIANT « 0 differe
GRATUIT » -- est desormais VERT, donc chacun des 349 restants a une cible qui n'est PAS deja
importee au niveau module. Les 15 entrants portent d'ailleurs leur motif en clair
(`# lazy : cycle damage<->abilities`, `# lazy : utilities <- battle_query`).

Le seuil dit lui-meme qu'il attrape « une REPRISE DE MASSE, pas un site isole ». `+3` (0,9 %)
n'est pas ce phenomene. **Mais re-baser un seuil chaque fois qu'il mord en fait un tampon**, et
c'est la degradation silencieuse que la doctrine proscrit. Les deux cotes sont donc laisses au
relecteur, sans que rien ne soit touche.

### `#484-r1` -- le resolveur de `probe_366_r1` et les constantes derivees d'enum

Nomme dans `_COVERAGE_HOLES` avec sa perte mesuree. Le point saillant : **la regle
« un entier/nom qui DESIGNE passe par un ENUM » rend ce recenseur statique aveugle**, parce
que `AbilityVariableType.dmg.name` n'est pas un litteral. Le patron va donc se repandre. Deux
crans a poser : la semantique syntaxique de `<Enum>.<membre>.name` (qui vaut `"<membre>"` sans
aucun import), et un env CROSS-MODULE (le second appelant ecrit `M._VAR_DAMAGE`).

## 3bis. CE QUE LE RE-JEU APRES REBASE A TROUVE -- y compris contre moi

Le rebase sur `origin/master` (6 commits arrives pendant la tranche) suivi d'un re-jeu COMPLET
des 8 shards a produit **26** rouges, dont **23 causes par MOI**. C'est la mesure qui justifie a
elle seule la regle « rebaser puis RE-JOUER ».

**La faute.** `probe_270r4r2r2` etage 1 dit : « differes GRATUIT(s) : leur **cible** est DEJA
importee au niveau module dans le preambule du meme fichier ». J'ai lu « cible » = **les noms**,
et j'ai SUPPRIME les instructions. Or « cible » y designe le **MODULE** -- c'est ce qui etablit
qu'il n'y a ni cycle possible ni cout evite, donc que le differe ne se justifie pas. Les NOMS,
eux, n'etaient lies nulle part ailleurs : `Caster`, `CasterTile`, `Enemies`,
`MovableTilesInRange`, `SelectTile`, `Sub`, `unit_of_entity`, `get_feet_count`,
`has_effect_of_type`. Le geste que le probe prescrit est **HISSER** (« hisser l'instruction est
sans effet de bord »), pas supprimer.

Deux gardes que j'avais pourtant en main n'ont PAS suffi :

* le grep « un test monkeypatche-t-il ce nom ? » -- il repondait `0`, et c'etait vrai ; la faute
  n'etait pas la ;
* le re-jeu des fichiers de test **du gisement** (`test_270r4r2r2*`) -- ils sont passes au VERT,
  puisqu'ils comptent des differes, pas des `NameError`.

Ce qui l'a trouvee est le re-jeu du **PERIMETRE ENTIER**, avec un **temoin sur `origin/master`
PUR** (`git archive` + pytest) qui rend les memes fichiers VERTS. Sans ce temoin, les 23 rouges
etaient indistinguables des rouges apportes par les 6 commits du rebase.

**Distinguer les deux formes**, parce qu'une seule autorise la suppression :

| forme | critere | geste |
| --- | --- | --- |
| differe **GRATUIT** | le MODULE cible est deja importe en tete | **HISSER** l'instruction |
| differe **OMBRAGE** | le **NOM** est deja lie en tete | **SUPPRIMER** (l'ombre rend le nom local) |

Un seul des six sites d'`engine/` etait un ombrage (`quickening:292 entities_from_state`), plus
un septieme apparu **avec le rebase** (`genestealer:210 import gameconfig as GC`, laisse par le
hissage de `#419-r5`), tous deux supprimes ; les cinq autres sont hisses.

### Deux rouges NEUFS, arrives pendant la tranche

* `genestealer:210` ci-dessus -- **REPARE**.
* `test_477r25::test_etage3_aucune_citation_fausse` -- **NON REPARE, hors perimetre, et c'est le
  PROBE qui a tort.** Introduit par `58a9c183` (PR #737), rebase pendant la tranche ; aucun
  fichier touche par #484 n'entre dans ce que ce test lit, et il n'appartient pas aux 42
  (mesures a `959189f2`, avant ce merge).

  La FENETRE d'appariement de `#477-r30`/`#477-r32` apparie le **slot** d'une ligne au **nom**
  de la ligne SUIVANTE. Confronte au metadata, le document est **JUSTE sur les trois lignes** :

  | ligne de `case-287r11` | nom cite | slot cite | metadata |
  | --- | --- | ---: | --- |
  | 39 | `GetFreeSurroundingTiles` | 104 = 0x68 | 0x68 = `GetFreeSurroundingTiles` ✔ |
  | 40 | `GetAllAliveUnits` | 137 = 0x89 | 0x89 = `GetAllAliveUnits` ✔ |
  | 41 | `GetSurroundingEnemies` | 120 = 0x78 | 0x78 = `GetSurroundingEnemies` ✔ |

  Le probe accuse « slot 0x68 : le site nomme `GetAllAliveUnits` » -- le nom de la ligne 40 --
  puis ajoute lui-meme « `GetAllAliveUnits` est aux slots 0x89 », ce qui **confirme** la ligne 40
  et le decale d'un cran. Meme forme sur 0x89 -> `GetSurroundingEnemies`. **A re-attribuer a
  `#477-r30`/`#477-r32`** (la fenetre), pas a #737 : c'est un FAUX POSITIF, et le corriger
  cote document ecrirait des slots FAUX. Non touche ici -- deux tranches `#477-r*` sont en vol.

### `test_480r8` -- rouge de CONTENTION, pas de gisement

Rouge au run 1 (`rc = 0xFFFFFFFF` du sous-processus = terminaison anormale, jamais un verdict :
le test traite deja `rc=2` comme « capteur casse » mais pas celui-la), **vert en isolation** et
**vert au run 2** sous la meme charge de 8 shards. Signature de contention (8 shards + les
processus des autres agents), pas du depot.

## 4. La lecon transportable

**Un refactor value-preserving A L'EXECUTION peut casser des tests sans changer un seul
resultat** -- il suffit qu'il change **ou un nom est LIE**. `492c722f` a mesure ce qu'il fallait
mesurer (0 divergence de valeur sur 197 017 attributs, 409/409 modules important en premier) et
n'a rien vu, parce que la propriete cassee n'est pas dans l'axe VALEUR : c'est
l'**observabilite** du code par ses tests.

Le seul signal qui a survecu est celui que les auteurs des montages avaient pose eux-memes --
`« le montage ne teste rien »`, `« le mutant rend la MEME valeur »`, `« observe 0 »`. **Ecrire
cette assertion-la est ce qui a transforme 28 faux verts en 28 rouges lisibles.** C'est la
generalisation a retenir : un montage qui SUBSTITUE doit VERIFIER que sa substitution a mordu,
et il doit le faire au montage, pas seulement dans l'assertion finale.

