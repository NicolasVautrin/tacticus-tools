# #485-r5 — Quatre différés déclarés CYCLE, mesurés GRATUITS 4/4

**Critère binaire.** Les quatre différés laissés par #1167 ferment-ils une boucle ?

**Non — aucun des quatre.** La classe annoncée au site et dans `case-485-le-recenseur-visait-le-paquet.md`
§4 (« CYCLE ») est fausse pour les quatre ; le verdict du cliquet (GRATUIT) est juste. C'était
l'objet de la tranche : deux lectures se contredisaient, une seule pouvait tenir.

## 1. La mesure qui tranche — `import <cible>` seul, process FRAIS

Contre-épreuve **à la main**, pas au travers du cliquet (c'est la leçon de #1167 : la mesure d'un
cliquet se contre-éprouve, elle aussi). Un interpréteur neuf par ligne, `import <cible>`, puis
`<appelant> in sys.modules` :

| cible chargée seule | appelant | dans `sys.modules` ? | modules `engine.*` chargés |
|---|---|---|---|
| `engine.runner.abilities.custodes` | `engine.playbook.prediction.abilities` | **NON** | 287 |
| `engine.entities.effects.base` | `engine.services.movement_query` | **NON** | 174 |
| `engine.runner.components` | `engine.services.movement_query` | **NON** | 178 |
| `engine.services.range_bonus` | `engine.services.movement_query` | **NON** | 3 |

**4 APPELANT_ABSENT sur 4.** Hisser ne referme aucune boucle : les quatre sont GRATUITS, donc
hissables — c'est exactement la conclusion que #1167 tirait des huit raisons écrites qu'il a
contre-éprouvées, et ces quatre-ci en sont la suite directe.

Deux d'entre eux portaient une raison plus précise que « CYCLE », et **aucune des deux n'était un
cycle** :

* `playbook/prediction/abilities.py` écrivait « ce serait une arête `playbook -> runner` que la
  couche prediction n'a nulle part ailleurs » — un argument d'**ARCHITECTURE** (vrai : le fichier
  n'a effectivement aucun autre import `runner`), pas de cycle. La doctrine tranche : un différé
  est un outil à CYCLE, pas un moyen de tenir une frontière de couche.
* `services/movement_query.py:490` visait `..runner.components`, **déjà importé cinq fois au
  préambule du même fichier** (lignes 44-48). Le différé ne protégeait rien et ne coûtait rien à
  supprimer — c'est le seul des quatre que `test_270r4r2r2::etage1` voyait, et le seul rouge de cet
  étage.

## 2. Ce qui a été joué AVANT le hissage, et ce que ça a dit

`migrate_485r1_barils_reexport.py morsure` : un seul `HISSAGE_DESARMERAIT` sur tout l'arbre —
`engine.runner.abilities.targeting . targeting_options_for` @ `playbook/nonattack.py:214`, qui est
un des trois imports **optionnels sous `try/except`** de la base attestée. **Hors périmètre**, il ne
bouge pas. Aucun des quatre symboles hissés n'est substitué par un patcheur.

`_lancer` de `probe_270r4r2r2_tri_differes` (hissage SIMULÉ, segment source exact exécuté avant le
corps du module) sur les segments **réellement écrits**, dans les deux ordres d'entrée : témoin vert
6/6, hissage vert 8/8.

**FORME B partout**, y compris là où le site liait un symbole :

```
from ..entities.effects import base as _effects_base      ->  _effects_base.BaseEffect
from ..runner import components as _components            ->  _components.unit_state_for_effects
from ..services import range_bonus as _range_bonus        ->  _range_bonus.MovementBonusContext
import engine.runner.abilities.custodes as CUSTODES       ->  inchangé (déjà forme B)
```

Les liaisons de forme A **préexistantes** du préambule de `movement_query.py` ne sont pas
converties : les toucher changerait la morsure de call-sites que cette tranche n'a pas mesurés.

## 3. Contrôle d'après coup

* `probe_477r35_import_isole` : **721 modules, 0 en échec**. C'est le seul contrôle qui voie
  l'entrée par un **TIERS** — les deux ordres du hissage simulé ne la couvrent pas (mesure #962 :
  hisser `battle_query.py:340` passait les deux ordres et cassait pourtant l'import des `selectors`
  par un troisième module).
* `probe_485_imports_differes` : **rc 0 VERT**, 274 recensés / 271 porteurs / **3 gratuits**, tous
  attestés (les trois optionnels sous `try/except`). 0 neuf, 0 périmé.
* `probe_485 --verifier-cache` (mode espion, recalcul intégral) : **77 entrées, 0 divergence**.
* `test_270r4r2r2_differes_offline::etage1` : `[]`.

**La base attestée n'a pas été touchée.** Elle ne devait pas l'être : l'attestation est une
conclusion, pas un remède.

### Le coût de cascade, chiffré — l'argument du site était vrai en topologie, nul en volume

Le site `abilities.py` invoquait « aucune cascade au chargement ». Mesuré des deux côtés
(`origin/master` `8b2a2e35` vs cette branche), en process frais :

| `import <module>` | master | branche | écart |
|---|---|---|---|
| `engine.playbook.prediction.abilities` | 507 modules `engine.*` | 508 | **+1** |
| `engine.services.movement_query` | 180 | 180 | **0** |

L'arête `playbook -> runner` existe bel et bien maintenant — mais elle coûte **un module**, pas une
cascade, parce que `runner.abilities.custodes` était déjà à un module près de la fermeture. Pour
`movement_query`, les trois cibles étaient **déjà dans sa fermeture** : le coût est **nul**, ce qui
était prévisible pour `..runner.components` (déjà au préambule) et ne l'était pas pour les deux
autres. Durées à cache `.pyc` chaud : 1,23-1,49 s contre 1,48-1,73 s — dans le bruit.

### La forme B MORD — vérifié, et le cliquet qui le garde

`probe_485r5_forme_b_mord.py`, **inscrit à `scripts/ratchets.ps1` dans le même commit** (un cliquet
que rien ne joue est exactement le vice `#485-r4`). Il garde les quatre sites :

* la **liaison** désigne bien le module cible (le registre décrit l'arbre, il ne peut pas se périmer
  en silence) ;
* le porteur ne porte **aucune copie gelée** du symbole — ni attribut de module, ni nom nu à l'AST ;
* un patch posé sur le module cible est **vu** à travers la liaison.

**Témoin de discrimination obligatoire (étape 0)** : les deux formes sont construites dans un paquet
jetable et doivent **diverger** — A ne mord pas, B mord. Sans ce cran, l'étape 1 serait verte sur un
mécanisme cassé.

**Contre-épreuve du cliquet lui-même**, deux mutations en mémoire, `rc 1` les deux fois :
poser `movement_query.BaseEffect` (exactement ce qu'un hissage en forme A produirait) →
`FAUTE : ... porte une liaison DIRECTE` ; casser `movement_query._components` → `FAUTE : ... ne
désigne PAS le module`. Il n'est pas vert à vide.

## 4. L'étage 3, qui ne dépend PAS de ces quatre — et la mesure de référence qui était déjà fausse

Le second rouge du fichier de test est un **SEUIL**, et les quatre hissages ne le font tomber que de
4 (335 → 331). Il vient d'ailleurs : de 860 commits de dérive unitaire.

**Attribution.** Commit qui a posé la mesure : `869b9760` (#962, 2026-08-12). 860 commits jusqu'à
cet arbre, pour **+37** instructions — soit **0,043 par commit**, **cinq à six fois SOUS** le débit
qui a justifié les relèvements précédents (0,23 ; 0,27 ; 0,24). Ce n'est pas la reprise de MASSE que
ce seuil surveille.

**Dispersion.** Diff site-à-site contre l'arbre de `869b9760` : 34 modules montent (+54), 12
baissent (-17) ; la plus grosse contribution vaut **+6** (`runner.components`,
`runner.abilities.behaviours.context`). Aucun module ne remonte le plafond à lui seul — il faudrait
+29. Les deux reprises de masse au dossier valent 625 et 122.

**L'OUTIL n'a pas bougé**, et il fallait l'établir avant d'attribuer quoi que ce soit au code :
`git diff 869b9760 HEAD -- probe_270r4r2r2_tri_differes.py` est **vide**, et les quatre croisements
(outil ancien/neuf × arbre ancien/neuf) rendent les mêmes couples 294/186 et 331/218. Le +37 est
**intégralement du code**.

**Et la mesure inscrite était déjà FAUSSE à son propre commit.** Le fichier porte
`MESURE_DIFFERES = 290` « mesuré après rebase sur `origin/master` » ; l'arbre de `869b9760` en porte
**294**. L'écart de 4 n'est pas une dérive : c'est une mesure prise sur un arbre qui n'a pas été
livré. Conséquence directe, chiffrée : la marge annoncée de 12 n'en valait réellement que **8**.
Cette tranche inscrit donc la mesure prise **APRÈS son rebase**, sur l'arbre exactement livré, et
c'est ce que le résidu **#485-r6** rend exécutable — un seuil écrit à la main ne peut pas dire s'il
juge l'arbre qu'on livre.

## 5. Ce que la tranche NE couvre PAS

* Les **187 porteurs sans raison écrite** restent sans raison écrite (`--porteurs` la dérive ;
  recopier en masse est le sweep que la doctrine interdit).
* Le gisement restant ne se ferme plus par hissage : il faut DÉPLACER le code partagé
  (doctrine (1)). C'est le résidu `#270-r4-r2-r2-r4`, hors d'une tranche de réparation de cliquets.
* `probe_485_imports_differes.py` n'est **toujours pas dans `scripts/ratchets.ps1`** — volet (a) de
  `#485-r4`, non résorbé ici (fichier hors du territoire de la tranche).
