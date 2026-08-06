# #486-r11 -- La cle du critere CYCLE descend de l'ARBRE au SOUS-GRAPHE

Le cliquet `probe_270r4r2_import_en_premier` etablit qu'un module d'`engine/` s'importe EN
PREMIER dans un interpreteur FRAIS. C'est une mesure MATERIELLE, la seule qui voie les cycles
passant par un paquet ancetre -- et elle coute **un interpreteur par module**, 437 fois.

#486-r5 les a memoises. Sa cle etait `empreinte_engine()` : `(chemin, mtime, taille)` de CHAQUE
`.py` de l'arbre. Une seule ligne modifiee dans un seul module invalidait donc TOUT -- c'est-a-dire
exactement le regime d'une PR moteur. Cette tranche descend la cle a la **FERMETURE TRANSITIVE
DES IMPORTS** du module.

## 1. Le critere n'a PAS bouge -- et c'est verifiable

Ce qui change est ce qui est RECALCULE, jamais ce qui est JUGE. Controle de fidelite, sur
l'arbre courant, `--tous` :

| run | duree | stdout | stderr | rc |
| --- | ---: | --- | --- | --- |
| A FROID force (`TACTICUS_SANS_CACHE_CLIQUET=1`) | 128,2 s | temoin | temoin | 0 |
| A CHAUD | **5,4 s** | **identique** | **identique** | **0** |

La sortie COMPLETE est identique, pas seulement le `rc`. C'est ce qui a impose de sortir l'etat
du cache du regime normal : il vit derriere `--resume-cache`, et la ligne de REPLI (ci-dessous)
est ecrite de facon a etre STABLE entre froid et chaud -- un module opaque n'entrant jamais au
cache, il est relance a chaque passe, donc re-detecte a chaque passe.

## 2. La definition de fermeture retenue, et pourquoi elle est SURE

`fermeture(M)` = le plus petit ensemble F tel que : `M` est dans F ; les **paquets ancetres** de
tout X de F sont dans F ; les cibles des imports **NIVEAU MODULE** de tout X de F sont dans F.

Sur : `python -c "import M"` execute exactement les `__init__.py` ancetres, le corps de `M`, et
recursivement la meme chose pour chaque module importe au niveau module. Un fichier hors de F
n'est pas charge, donc il ne peut pas changer le `rc`.

**Les imports DIFFERES en sont EXCLUS**, et c'est un choix argumente : un `from .y import z` dans
un corps de fonction ne s'execute pas au chargement, un bloc `if TYPE_CHECKING:` jamais. Les
inclure serait sur-approximer -- sain, mais ruineux : le graphe TOUS IMPORTS exhibe un SCC geant
(`probe_270r4r2_cycles_imports` etape 2), donc la fermeture de presque tout module vaudrait
presque tout `engine/` et la cle redeviendrait la cle grossiere sous un autre nom.

⚠ **Ce qui rend l'exclusion sure n'est pas ce raisonnement, c'est le CONTROLE.** Chaque
interpreteur reellement lance rend AUSSI ce qu'il a charge (`sys.modules` filtre sur l'arbre), et
cette fermeture MESUREE est confrontee a la fermeture CALCULEE. Mesure sur les **437 modules** :
**0 sous-approximation** (`taille mesuree vs calculee : 176,2 vs 176,2, ratio 1,00` sur
l'echantillon detaille). Le calcul statique n'est donc pas seulement sur : il est **exact** sur ce
depot.

**La cle porte CONTENU et COMPOSITION.** Le hash couvre, par module de la fermeture, son NOM et le
sha256 de son TEXTE (sur le texte, pas les octets : `core.autocrlf`, meme raison que
`verdict_cache.sha_texte`). Les deux sont necessaires -- ajouter une ARETE fait entrer un fichier
neuf dans la fermeture sans qu'aucun contenu deja present ne change.

## 3. Les trois pieges, traites

**(1) La fermeture statique peut SOUS-APPROXIMER.** `importlib.import_module`, `__import__`, un
nom assemble a l'execution, ou un differe execute au chargement parce que sa fonction est appelee
au niveau module : rien de tout cela ne se voit dans l'AST. Le repli n'est pas une heuristique --
le debordement se **mesure**, et le module concerne retombe sur la cle GROSSIERE, **le dit**
(`REPLI sur la cle GROSSIERE : N module(s) ...`) et n'entre **jamais** au cache versionne.

Mesure a la livraison (`probe_486r11_fermeture_imports.py --formes --debordements`) : **0 module
sur 437** retombe sur la cle grossiere ; `engine/**` porte **0** site d'import dynamique et **0**
import optionnel `engine.*` dont la cible n'existe pas.

**(2) Les differes.** Traites au §2 : exclus par definition, et l'exclusion est gardee par la
mesure runtime, pas par la confiance.

**(3) Un `__init__.py` est dans la fermeture de TOUT son paquet.** C'est une consequence directe
de la regle des ancetres, et c'est mesure : toucher `engine/__init__.py` relance **437/437**
modules, `engine/entities/__init__.py` en relance **397**. Le fichier le plus structurant du depot
invalide donc large -- ce qui est le comportement voulu, pas une deception.

## 4. Les trois regimes, chiffres

Coût fixe a chaud : ~5 a 9 s (calcul des 437 fermetures ~3,9 s, lecture du cache, demarrage).
Le nombre d'interpreteurs est instrumente (`--resume-cache`) : c'est le chiffre robuste, un
chronometre melangeant le cout du cliquet et la charge de la machine.

| regime (`--tous`) | interpreteurs | duree | cle grossiere (#486-r5) |
| --- | ---: | ---: | ---: |
| **0 fichier** d'`engine/` touche | **0** | **7,0 s** | 437 / ~130-180 s |
| 1 fichier, rayon 1 (feuille) | 1 | 11,1 s | 437 |
| 1 fichier, rayon 181 (median) | 181 | 84,4 s | 437 |
| 1 fichier, `engine/__init__.py` (rayon 437) | 437 | 143,3 s | 437 |
| 5 fichiers de rayon 1 | 5 | 7,9 s | 437 |
| 5 fichiers au hasard (union 324) | 324 | 153,3 s | 437 |

Sur la PASSE des deux fichiers de test qui consomment ce cliquet
(`test_270r4r2_cycles_imports_offline` + `test_270r4r2r2_differes_offline`) : **191,4 s** avant
#486-r5, **127,9 s** apres, **19,4 s** ici.

⚠ **Le gain n'est PAS uniforme, et le moyenner le maquillerait.** Distribution du nombre de
modules a re-tester quand on touche `k` fichiers pris au hasard (4 000 tirages, `--granularite`) :

| k | min | p25 | med | moy | p75 | max |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 89 | **181** | 173 | 250 | 437 |
| 5 | 10 | 270 | **319** | 304 | 336 | 437 |

Autrement dit : le regime « 0 fichier » gagne **tout** (437 -> 0), une PR d'un fichier gagne
**~59 %** en mediane, une PR de cinq fichiers **~27 %**. Le graphe d'`engine/` est dense
(fermeture mediane de **191** modules sur 437) : c'est une propriete du depot, pas une limite de
la cle. Une cle plus fine que le sous-graphe n'existe pas -- au-dela, il faudrait changer le
critere.

## 4bis. Le CHURN du fichier versionne, et pourquoi il est acceptable

Le cache vit dans `scripts/cliquets-cache/probe_270r4r2_import_en_premier.tsv` : **437 lignes,
56 Ko**, une par module. Toucher un fichier de rayon `r` fait changer `r` lignes -- jusqu'a **437**
pour `engine/__init__.py`. C'est plus que le churn des trois caches de #486-r1 (« au plus N lignes
pour N fichiers touches »), et c'est structurel : la cle d'un module PORTE ses dependances, donc
elle bouge quand elles bougent. C'est le prix exact du gain.

Ce que cela n'entraine pas : un conflit de merge se resout en **REGENERANT** (`--tous`), jamais en
fusionnant -- l'en-tete du fichier le dit, et le fichier porte en plus une note propre a ce
cliquet, parce que l'en-tete generique de `verdict_cache` annonce « sha256 du CONTENU » et
qu'un lecteur pourrait croire pouvoir recalculer la cle depuis le seul fichier nomme en 1re
colonne. Un cache non regenere ne ment pas : ses entrees perimees MANQUENT, et le run repaie.

⚠ **Un run PARTIEL n'ecrit pas.** `CacheCliquet.enregistrer` reecrit avec exactement les entrees
vues -- c'est ce qui fait le menage, et c'est ce qui RETRECIRAIT le fichier si un run sur un
sous-ensemble (un seul des deux fichiers de test, `--modules a,b`) l'ecrivait. Le refus est
explicite (`_enregistrer_si_complet`) et garde par l'etage 7.

## 4ter. Un defaut TROUVE en chemin : le CONTEXTE n'etait pas portable

Le cache est reparti a ZERO apres un `git rebase` qui n'avait touche **aucune** de ses trois
sources -- **119 s au lieu de 20 s**. Cause : `verdict_cache.sha_fichiers`, qui produit le
CONTEXTE, hache les **OCTETS**, et `core.autocrlf=true` fait passer un fichier de LF a CRLF au
checkout. Sur une plateforme a LF, un cache VERSIONNE serait ainsi froid **en permanence** --
c'est-a-dire inutile la ou il existe, puisque sa raison d'etre est qu'un worktree frais demarre
chaud.

C'est exactement le piege que `sha_texte` documente pour la cle de LIGNE ; le contexte y
echappait. `sha_fichiers_texte` le corrige, et la contre-epreuve MORD : conversion de
`import_closure.py` en LF, run complet -> **cache CHAUD, 437 reutilisees, 0 interpreteur** (avec
l'ancien contexte : 437 recalculs). Garde : `test_486_r1_cache_verdict_offline.py`, avec ses deux
moities -- la variante portable IGNORE la fin de ligne, l'ancienne la VOIT encore (sans quoi le
test comparerait deux fonctions identiques).

⚠ **Les trois cliquets de #486-r1 portent toujours ce defaut** : ils utilisent `sha_fichiers`
pour leur contexte. La bascule n'est pas faite ici (hors perimetre) ; elle coute une invalidation
unique de leurs caches, et rien d'autre. C'est le residu #486-r17.

## 5. La contre-epreuve, dans les DEUX sens

Le VERT est le resultat suspect sur une contre-epreuve : chaque mutation doit avoir MORDU.

* **DANS la fermeture** -> le module DOIT etre re-teste. L'echec ici serait un **faux vert** :
  un verdict perime servi comme frais. Garde : `test_486r11_cle_sous_graphe_offline.py` etage 5.
* **HORS de la fermeture** -> il ne doit PAS l'etre, **et son verdict doit etre inchange**. Le
  test exige d'abord que le fichier touche relance **son propre** module -- sans quoi le vert
  dirait seulement « rien n'a change ».

⚠ **Sur l'ARBRE REEL, avec une mutation DESTRUCTIVE.** Un commentaire ajoute ne prouve rien : il
change le sha, rien de plus. La contre-epreuve insere un `raise ImportError` en tete du fichier
touche, puis recalcule les verdicts A LA MAIN (interpreteur frais, hors de tout cache) :

| cible touchee | dans sa fermeture | SENS 1 (temoin de morsure) | SENS 2 (6 modules hors fermeture) |
| --- | ---: | --- | --- |
| `engine/ai/tactic.py` (rayon 1) | 1 / 437 | `engine.ai.tactic` **rc 0 -> 1**, cle changee | verdict inchange **6/6**, cle inchangee **6/6** |
| `.../triggers/loki/phoenix_gem.py` (rayon 181) | 181 / 437 | `engine.ai.action_generators` **rc 0 -> 1**, cle changee | verdict inchange **6/6**, cle inchangee **6/6** |

Le SENS 1 est ce qui rend le SENS 2 lisible : sans temoin de morsure, « 6/6 inchanges » dirait
seulement que la mutation n'a rien casse nulle part.

Et la RE-VERIFICATION integrale (`--verifier-cache`, mode espion, 128,4 s) : **437 entrees sur
disque, 437 recalculees, 0 divergence**. C'est le seul controle qui verrait une entree FALSIFIEE
de facon coherente -- aucune cle ne le peut, par construction.

Sont gardes en plus : le passage par le cache VERSIONNE (un process frais demarre chaud), un
contexte different qui vide tout, un ECHEC jamais cache (`sys.modules` est a mi-chemin, sa
fermeture n'est pas celle du verdict), le tri-etat `None` = « pas mesure » (meme repli qu'un
debordement), et le refus d'ecrire sur un run PARTIEL (`enregistrer` reecrit avec exactement les
entrees vues : un run sur un sous-ensemble RETRECIRAIT le fichier versionne).

⚠ **La garde est bon marche.** La premiere version de celle de #486-r5 coutait **+150 s** parce
qu'elle re-balayait le corpus : un cliquet qui rouvre le gisement qu'il ferme. Ici tout ce qui est
CRITERE se joue sur un paquet `engine` JOUET (hub, deux branches disjointes, un differe, un
`TYPE_CHECKING`), ou « dans la fermeture » et « hors fermeture » sont tous deux non vides. L'arbre
REEL n'est touche que par deux etages qui ne peuvent pas se jouer ailleurs : la COINCIDENCE de
l'accelerateur groupe avec le calcul naif (3 modules), et le TEMOIN de granularite (sans lui, une
fermeture valant tout l'arbre laisserait tous les etages synthetiques verts et la descente de cle
serait FICTIVE).

## 6. Un trou HERITE qui se referme au passage

La cle grossiere ne regardait que `engine/**`. Or **deux** modules freres de `scripts/python/`
entrent dans les fermetures -- **`gameconfig` (317 modules)** et **`hexgeo` (351)**. Les modifier
ne reinvalidait donc **rien**. La fermeture, elle, ne filtre sur aucun prefixe
(`_Visiteur(..., prefixes=None)`, parametre ajoute a `probe_270r4r2_cycles_imports` sans changer
son defaut) et les porte. Ce n'est pas une precaution : c'est un faux vert qui existait et qui
n'existe plus.

Releve complet (`--granularite`) : **439** fichiers gouvernent au moins un module ; rayon
`min=1 med=181 moy=172,5 max=437` ; **30** fichiers de rayon 1 ; les huit plus larges sont
`effect_type=343, traits/unit_trait=344, entities/stats=345, entities/traits=349, hexgeo=351,
services=353, entities=397, engine=437`.

## 7. Ce qui reste HORS de portee, et il faut le lire

* **Les fichiers NON-`.py` lus au chargement** (JSON, TSV). La cle grossiere ne les couvrait pas
  davantage : trou herite, pas regression -- mais il est nomme.
* **La CREATION d'un fichier qui satisfait un import jusque-la en echec** (`try: import
  engine.futur / except ImportError:`). Le fichier neuf n'est dans aucune fermeture, donc aucune
  cle ne bouge. Mesure : **0 site** de cette forme dans `engine/**`. Recenser :
  `probe_486r11_fermeture_imports.py --formes`.
* **Le `DECLENCHEUR` de #486-r13 n'est PAS pose ici.** Ce cliquet n'en portait pas et n'en porte
  toujours pas -- ce n'est pas une regression, mais son perimetre de lecture s'est ELARGI avec
  cette tranche (`import_closure.py`, `verdict_cache.py`, `scripts/cliquets-cache/`, et les
  modules freres `gameconfig`/`hexgeo`). Le poser sans la RE de #486-r13 risquerait une
  declaration TROP ETROITE, c'est-a-dire un cliquet qui se rejoue MOINS souvent que son gisement
  ne bouge -- exactement les 4 declarations que la trace de #486-r13 a dû corriger. Nomme, pas fait.
* **`probe_485_imports_differes`** porte le MEME critere et n'est pas cable au cache. Son entree
  dans `NON_CACHABLES` disait « non cachable, le verdict depend du sous-graphe » ; c'est desormais
  la description d'une cle qui existe. Il reste non cache -- **residu**, pas impossibilite.
* **Le cout fixe de ~3,9 s** du calcul des fermetures (parse de 439 fichiers) est paye a chaque
  passe, cache chaud compris. Il est memoisable par fichier (sha -> cibles) dans un second cache
  versionne ; non fait, le rapport gain/complexite ne le justifiait pas a ce stade.

⚠ **Le montage est GENERALISABLE, et un residu ouvert le decrit deja.** `#486-r9` (`probe_273`)
nomme exactement la meme forme : « une cle A DEPENDANCES -- `(sha du fichier, sha des modules dont
il emprunte)` », parce que 58 fichiers sur 2 090 empruntent une racine a un AUTRE module. C'est le
meme objet que `import_closure` : un verdict local a un SOUS-GRAPHE, pas a un fichier. Ce dossier
en fournit l'implementation de reference (calcul groupe par composantes fortement connexes,
controle runtime de la sous-approximation, repli nomme) ; le cabler ailleurs n'est pas fait ici.

## 8. Ce qui a ete refuse

* **Stocker la fermeture MESUREE dans le cache** au lieu de la recalculer : 437 x ~173 noms
  ~= 3 Mo de TSV versionne, pour une cle deja exacte a 1,00.
* **Inclure les differes dans la fermeture** (sur-approximation « sure ») : le SCC geant du graphe
  TOUS IMPORTS ramenerait la cle a l'arbre entier. Le controle runtime rend l'exclusion sure sans
  ce prix.
* **Une clef de contexte incluant la LISTE des fichiers d'`engine/`** (pour voir un fichier
  AJOUTE) : elle invaliderait tout le cache a chaque ajout de fichier, c'est-a-dire le vice meme
  qu'on corrige. Le cas est nomme au §7 a la place.
