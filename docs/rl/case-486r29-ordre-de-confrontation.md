# #486-r29 / #486-r27 / #486-r30 / #486-r31 — les gardes qui se trompent sur eux-mêmes

Quatre résidus, **une** cause : *le seul gate qu'un auteur interroge réellement ne juge pas ce qui
compte*. Trois d'entre eux ont rendu `master` rouge.

## 1. `#486-r29` — l'ORDRE rendait le rouge invisible à son auteur

`probe_486r15` confronte une déclaration à l'**UNION** de deux sources : la fermeture d'imports et
les **témoins** de l'empreinte `probe_457`. Sans entrée d'empreinte, la seconde est **vide** — le
cliquet vérifie la première **seule**, strictement plus étroite. L'ordre prescrit partout était
`probe_486r15` **puis** `probe_457 --measure-missing` : l'auteur jouait donc à **une** source,
gravait l'empreinte juste après, livrait ; la confrontation passait à **deux** sources **au merge**.

**Mesuré** : PR #832, verte chez son auteur, rouge sur `master` au commit `18edd540` — 8 chemins
manquants, **tous** par les témoins, **0** par la fermeture, empreinte arrivée dans la même PR.

Ampleur du régime à une source (2026-08-08) : **28 des 74** déclarations (38 %) sans empreinte ;
**206** chemins apportés par les témoins et invisibles de la fermeture sur les 46 restantes.

**Fermé par deux crans.** (a) L'ordre est **inversé** dans le SKILL, et il est désormais
**imprimé par l'outil**, avec la mesure qui le fonde — une prescription qui ne vit que dans un
gabarit de brief se recopie sans être relue. (b) Le **verdict se qualifie** :
`PASS SOUS RESERVE`, avec le compte, la liste et l'ordre à jouer. Le `rc` reste 0 : ce n'est pas
une faute, c'est une **portée**. Le compte des « confrontée(s) » valait `len(ok) - len(bypass)`,
donc il rangeait les 28 non mesurées parmi les confrontées — **c'était faux**.

⚠ **Témoin d'usage, pas seulement mutation** : dans l'ordre corrigé, le test neuf arrivé avec
#833 a été confronté à **deux** sources du premier coup (75 déclarations, 72 confrontées, PASS).

## 2. `#486-r27` — le hook pytest ne validait que la PRÉSENCE

`declencheur_guard` n'exposait que `manquants()` et n'appelait **jamais**
`declencheur_cliquet.valider`. Mesuré (PR #824) :
`test_448_r1_r1_r2_r2_gates_abandon_offline.py` est passé avec **deux clés sur quatre**, son
auteur écrivant « `DECLENCHEUR` posé pour garder rc 0 » — le gate interrogé lui a répondu vert.

**L'arbitrage est tranché par le coût, et les deux moitiés sont gardées** :

| étage | où | pourquoi |
|---|---|---|
| FORME | **descend dans le hook** | `valider` est **pur** : un `dict` déjà en mémoire, aucune I/O, stdlib seul. Coût = celui du `getattr` déjà fait. |
| CONFRONTATION | **reste au probe** | une fermeture d'imports **par fichier** (~440 modules pour un test) : impayable à chaque passe, y compris les passes live à 4 workers. |

Un test garde explicitement que la confrontation **n'est pas** descendue : si quelqu'un l'y met
« pendant qu'il y est », il tombe et l'arbitrage est ré-instruit au lieu d'être subi.

La **dette ne tolère que l'ABSENCE** : un fichier qui écrit la constante a cessé de s'appuyer sur
elle. Innocuité mesurée avant livraison : **0** déclaration mal formée sur les 777 fichiers.

## 3. `#486-r30` — un rouge qui ne dit pas ce qu'il n'a pas regardé

`probe_486r15` s'arrêtait à la déclaration mal formée **avant** de confronter le périmètre. Sur
`test_175e_175r_tile_meta_live.py`, une seconde faute (6 chemins de fermeture non déclarés) était
**cachée** par la première — deux tranches pour trouver les deux. Le probe confronte désormais
aussi les déclarations mal formées et rend **trois** réponses distinctes : périmètre **TROP
ÉTROIT** (chemins nommés) · **COUVERT** (seule la forme est en faute) · **NON EXAMINÉ** (la
déclaration n'a pas pu être lue — jamais deviné).

## 4. `#486-r31` — deux gardes de la même famille se contredisaient sur `master`

Sur `tests/engine/runner/test_refresh_active_flag_discriminant_offline.py` (PR #834), au **même
commit** : `chemins=() build=False toujours=False` → `valider` rendait **1 erreur** quand
`perimetre` rendait **475 chemins**, et `probe_486r15` rendait PASS. La règle jugeait le dict
**DÉCLARÉ** pendant que sa justification parlait du périmètre **EFFECTIF**.

Deux populations, deux vérités : pour un **cliquet** rien ne s'ajoute au déclaré (la règle est
juste) ; pour un **test**, le foyer dérive la cascade des `conftest.py` et le fichier lui-même.
`valider` prend un `perimetre_derive` explicite ; les trois appelants qui jugent des tests le
passent, celui qui juge des cliquets non.

⚠ **Ce n'était pas optionnel** : `#486-r27` fait appeler `valider` par le hook sur **chaque**
module collecté — sans `#486-r31`, ce fichier de `master` aurait rougi toute passe qui le
collecte. Les deux crans se tiennent.

⚠ **La borne ne disparaît pas pour les tests, elle change de cran** : un test qui déclare
`chemins: ()` en important quelque chose reste **rouge**, par la confrontation. On déplace la
faute vers le cran qui sait la voir.

⚠ **Diagnostic écarté** (celui de la PR #834) : `--proposer` n'est pas fautif — il dit
explicitement « RIEN A DECLARER hors de la cascade » et sa sortie est acceptée. L'aide avait
raison ; c'est la règle qui avait dérivé de sa propre justification.

## 5. Témoins

`scripts/python/tests/test_486r29_ordre_de_confrontation_offline.py` (7) — le central : **même
arbre, même déclaration, même cliquet**, la seule gravure de l'empreinte fait passer le `rc` de
**0 à 1**. C'est le régime de la PR #832 reproduit de bout en bout.

`scripts/python/tests/test_486r27_forme_au_hook_offline.py` (22) — la déclaration **exacte** de la
PR #824 refusée ; six formes fautives passant par `valider` et non par des règles recopiées ; le
témoin **non nul dans les deux populations** de `#486-r31` (un cliquet à périmètre vide reste
ROUGE, un test dont tout tient dans la cascade est VERT) — une correction qui ne garderait qu'un
des deux sens rouvrirait l'autre.
