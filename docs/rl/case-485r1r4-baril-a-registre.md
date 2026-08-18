# #485-r1-r4 / #485-r1-r2 — un baril à REGISTRE porte DEUX choses, et une seule justifie l'exclusion

Le sweep `#485-r1-r1` a vidé les barils de re-export d'`engine/`, en **excluant les barils à
registre**. L'exclusion était juste dans son principe et **trop large dans sa portée** : ces barils
portent deux choses indépendantes, et le sweep les a traitées comme une seule.

| | ce que c'est | les retirer |
|---|---|---|
| **ENREGISTREURS** | `from . import loki_custom` — l'import **EST** l'effet (l'enfant s'inscrit au chargement) | vide un registre **en silence** (`.get(clé)` rend `None`, le moteur repart sur le défaut) |
| **RE-EXPORTS** | `from .base import BasePlaybook, …` — du confort d'appel | ne vide **rien** ; casse seulement des lecteurs, qui sont **dénombrables** |

## 1. La mesure qui renverse la priorité

Arbre témoin à `62db139d`, `probe_485_imports_differes.py` :

| variante du baril `engine.playbook` | différés PORTEURS | Δ |
|---|---|---|
| tel quel | 277 | — |
| les 9 **enregistreurs** retirés | 273 | −4 |
| les **re-exports MORTS** retirés, enregistreurs gardés | **262** | **−15** |
| baril entièrement vidé | 253 | −24 |

⚠ **Ce tableau compare quatre VARIANTES sur une base FIGÉE (`62db139d`)** — c'est ce qui rend les
quatre chiffres comparables entre eux. L'effet réellement **livré** se mesure, lui, contre la base
sur laquelle la PR atterrit : re-mesuré après rebase sur `d3547dfb` (16 commits plus loin),
`origin/master` porte **279** porteurs / **55** gratuits neufs, la branche **264** / **49** — soit
le **même −15**, et un compteur de rouge qui **baisse** de 6. Les deux mesures sont vraies ; citer
la première comme si elle décrivait la livraison serait faux dès le premier merge intercalé.

**83 % du gain est du côté qui ne coûte rien.** Sur 33 symboles re-exportés, **4** sont consommés —
`REGISTRY` (30 fichiers), `get_playbook_or_default` (24), `tile_utility` (2), `get_playbook` (1) ;
les **29** autres ne sont réclamés nulle part.

⚠ **Les DEUX voies de consommation comptent.** `REGISTRY` est réclamé **4** fois par `ImportFrom` et
**32** fois par **accès attributaire** (`import engine.playbook as PB` puis `PB.REGISTRY`), que
ne voit aucun recensement d'imports. Sans cette seconde voie, `get_playbook` serait passé pour MORT
avec 12 lecteurs — la faute exacte qui a vidé 4 couples sous les pieds de leurs lecteurs en
`#485-r1-r1`.

## 2. Pourquoi `#485-r1-r2` est REFUSÉ

Le résidu visait les **enregistreurs** : `charger_tout()` (`pkgutil`) + « toute lecture avant
chargement LÈVE ». Trois raisons de ne pas le faire, chacune mesurée.

1. **Sa prémisse est périmée** : les barils à registre sont **5**, pas 4 (`engine.runner.abilities`
   s'est ajouté), et `playbook` porte **9** effets de bord + **6** enregistreurs, pas 6+4.
2. **Le gain est de −4 porteurs sur 277**, pour un rayon de 405 sites, un `charger_tout()` à placer
   et le **type** de 4 registres à changer.
3. **Le cran proposé est inatteignable tel quel**, et la fiche le disait elle-même : « la racine de
   composition n'existe pas dans ce dépôt, où chaque probe entre par son propre module ». Un
   registre qui lève à la lecture ferait tomber ~500 probes.

### Ce qui est livré à la place

Le cran qui compte — **supprimer la panne silencieuse** — s'obtient **sans** changer le régime de
chargement : `probe_485r1r4_baril_playbook.py`.

- **[2] le baril peuple AUTANT que le chargement exhaustif.** Invariant **DÉRIVÉ** (comparaison
  dans un process frais), jamais une liste attestée qui se périmerait au prochain enregistreur.
  ⚠ **Un process PAR REGISTRE**, et c'est le point : une première écriture les mesurait tous dans le
  même interpréteur — importer `noncomparable` pour lire `PLAYBOOKS` y exécutait ses `@register`,
  donc `base.REGISTRY` était lu **après** avoir été enrichi par un import que le mode « baril »
  n'aurait jamais dû faire. Le capteur mesurait sa propre sonde et rendait le même chiffre quoi
  qu'on retire.
- **[2b] la CONTRE-ÉPREUVE.** On ampute un enregistreur pour de vrai (module vide posé dans
  `sys.modules` avant le chargement) et on exige que [2] le voie : `REGISTRY` **53 → 35**. Sans
  elle, [2] serait un inventaire déguisé en garde — le vice de `probe_181` d'avant `#430`.

## 3. Hisser ce que le dégraissage libère : FORME B, et la morsure APRÈS

Les 21 différés rendus gratuits sont hissés **en forme B**. Ce n'est pas une précaution de
principe : `migrate_485r1_barils_reexport.py morsure` passe de **4 à 7** `HISSAGE_DESARMERAIT`
**après** le dégraissage, et **trois des nouveaux sont ceux-là** — `will_normal_attack_kill`,
`generate_multi_hit_attack_prediction` (4 sites, 5 patcheurs), `make_normal_attack_predictions`
(3 sites). Un hissage en forme A aurait désarmé **6 fichiers de tests, en silence**.

⚠ **Corollaire de procédure** : la morsure se rejoue **après** avoir vidé, pas avant — sa base de
gratuits est mesurée par rapport à l'arbre courant.

**Non touchés, pour une raison LUE** :

- `nonattack.py:214` — import **optionnel sous `try/except`** : le hisser déplacerait l'échec du
  site d'appel, où il est rattrapé, vers le chargement du module.
- `prediction/abilities.py:454` (`CUSTODES`) — raison **architecturale** écrite au site par `#974` :
  hisser créerait une arête `playbook -> runner` que la couche prédiction n'a nulle part ailleurs.
- `_targets.py:238` — différé **REDONDANT** (`bq` était déjà au préambule depuis `#485-r1-r1`) :
  **supprimé**, pas hissé, et son commentaire périmé avec lui.

## 4. Deux rouges de `master` trouvés en passant

- **`probe_485_imports_differes.py` est ROUGE sur `master`** (53 gratuits neufs) et **n'est pas dans
  `scripts/ratchets.ps1`** — il a donc dérivé de 3 à 60 gratuits sans que rien ne le joue. Le
  compte annoncé par le `CLAUDE.md` (169 différés / 166 porteurs / 3 gratuits) est re-mesuré à
  **337 / 277 / 60**. Après cette tranche : **262 porteurs, 47 gratuits neufs**.
- **`test_359r5_selector_only_event_order_offline.py`** — 2 tests rouges, vérifiés **identiques sur
  un arbre témoin à `62db139d`** : préexistant, sans rapport avec cette tranche.

## 5. Le gisement restant — `#485-r3`

L'étage [0] du cliquet balaie les cinq barils et **re-dérive** le compte à chaque run :

| baril | re-exports | MORTS |
|---|---|---|
| `engine.playbook` | 4 | **0** ← bloquant |
| `engine.runner.abilities` | 4 | 4 |
| `engine.runner.abilities.loki` | 106 | **92** |
| `engine.runner.operations.triggers.loki` | 62 | **51** |
| `engine.utilities` | 32 | 30 |

**177 morts hors `playbook`**, et ce sont exactement les paquets qui ferment le plus de cycles
(`runner.abilities.loki` 45, `runner.abilities` 40, `utilities` 7 — `probe_485r1r1_leviers_des_porteurs.py`).

⚠ L'étage [0] est **non bloquant** hors `playbook` : ces quatre barils sont les foyers d'autres
tranches, et un cliquet qui rougit sur ce qu'on n'a pas le droit de réparer se fait désarmer.

## 6. `#485-r3` FERMÉ — et le tableau du §5 comptait **36 morts qui n'existaient pas**

**Le recenseur déclarait mort ce qu'il ne savait pas lire.** `consommateurs()` exigeait
`n.level == 0` sur ses `ImportFrom` : il ne voyait donc **aucun import relatif**, alors que c'est
la forme dominante *dans* `engine/**`, où presque tout consommateur est un voisin de paquet.
Mesuré le 2026-08-18, avant toute vidange :

| baril | re-exports | morts ANNONCÉS | morts RÉELS | faux morts |
|---|---|---|---|---|
| `engine.playbook` | 4 | 0 | 0 | 0 |
| `engine.runner.abilities` | 4 | 4 | 4 | 0 |
| `engine.runner.abilities.loki` | 106 | 92 | **68** | **24** |
| `engine.runner.operations.triggers.loki` | 62 | 51 | **39** | **12** |
| `engine.utilities` | 32 | 30 | 30 | 0 |
| | | **177** | **141** | **36** |

Les 24 faux morts d'`abilities.loki` sont réclamés par **`runner/abilities/handler.py`**, qui écrit
`from .loki import (...)` ; les 12 de `triggers.loki` par **`triggers/dispatch/registry.py`**. Agir
sur le **177** aurait retiré des noms que `handler.py` importe : `ImportError` au chargement, donc
`ABILITY_CLASSES` **entier** hors service. C'est le vice symétrique de celui que `probe_270r1` a dû
corriger — *un recenseur ne rend pas zéro sur ce qu'il ne visite pas* ; ici il rendait **MORT**.

`_cible_absolue` résout désormais `level`, et un **auto-test de 7 cas** est joué à chaque run : une
erreur de **un cran** sur `level` n'omet pas des consommateurs, elle en **invente**, donc aucun
compte n'aurait l'air anormal. Le jeu de cas **asserte son propre non-vide**.

### Deux défauts du vidangeur, dont un DANGEREUX

**(a) Sûreté — un baril protège ses CHARGEUSES, pas ses ENREGISTREURS.** `vider` gardait les imports
visant un *baril à registre* (`_cibles_chargeuses_de_registre`) mais ignorait `Baril.enregistreurs`,
que `derive_barils` remplit pourtant : la cible est un module **feuille** dont le top-level mute un
conteneur du moteur. Sans ce cran, vider `engine.utilities` **supprime**
`from .move import MinDistanceToClosestEnemyUtility, MIN_DIST_UTILITY, UNIT_MOVEMENT` — ses trois
noms sont morts — donc `UTILITY_BY_TYPE[UtilityType.UnitMovement]` n'est plus jamais inscrit et
`utilities_database()` rend `None` là où elle rendait l'utilité de mouvement. Aucune erreur, aucun
test rouge : la panne même que l'exclusion en bloc de `#485-r1-r1` devait empêcher, **rouverte par
le bas** dès qu'on vide baril par baril.

**(b) Précision — un seul `import … as` gelait un baril entier.** `probe_r28_pick_order.py` écrit
`import engine.runner.abilities.loki as LK` et ne demande que `LK._pick_randomly_n` ; le repli
conservateur réclamait les **114** symboles, d'où **0 retirable sur 68 morts réels**. Or
`_table_modules` **suit déjà** cette liaison et `_attributs_lus` rend les attributs exacts plus un
drapeau d'**échappement**. Le repli n'est donc plus appliqué quand la table résout l'`asname` **vers
ce module-là** (sinon deux `as` homonymes dans un même fichier se masqueraient, et l'attribution
deviendrait *fausse* au lieu d'être *large*).

### Ce qui est protégé, c'est l'EXÉCUTION de l'import — pas les noms qu'il lie

Le premier garde gelait *tous* les noms d'un import enregistreur. Or
`from .facade import (SorcerousFacadeAbility, <3 morts>)` continue de s'exécuter une fois les morts
retirés, puisqu'un vivant subsiste. Seul l'import dont **tous** les noms meurent doit être préservé —
et il passe alors à la forme **enregistreur**, `from . import <enfant>  # noqa: F401`, qui *déclare*
l'effet de bord au lieu de le faire porter par des noms que plus personne ne lit. Le prochain
dégraissage ne le supprimera donc pas par mégarde. `engine/runner/abilities/__init__.py` est réduit
à cette seule ligne, `__all__ = []`.

**Bilan : 177 annoncés → 141 réels → 149 retirés (138 + 11) → étage [0] rend 0 mort sur les CINQ
barils.** Trois imports restent gardés nommément : `loki.facade`, `triggers.loki.final_justice`,
`utilities.move`.

### Contre-épreuves

- **Registres identiques** avant/après : `TRIGGERED_ABILITY_BEHAVIOURS`,
  `TRIGGERED_ABILITY_DELAYED_BEHAVIOURS`, `UTILITY_BY_TYPE`, sous **six** points d'entrée, chacun
  mesuré dans son **propre process frais**.
- **Le mutant mord, et la multiplicité des entrées est ce qui le fait mordre** : amputer
  `from .move import …` fait tomber `UTILITY_BY_TYPE` de **7 à 6** sous l'entrée `engine.utilities`
  — et **pas** sous `engine.runner.abilities.handler`, où un autre chemin tire `move`. Un témoin à
  point d'entrée unique aurait été vert sur une panne réelle.
- `probe_477r35` **723/723** modules importables seuls ; `probe_462r5` **0** import non résolu sur
  3 367 fichiers ; `probe_485r1r1` **7 623** accès attributaires, **0** non résolu.

## 7. `probe_485_imports_differes` est ENTRÉ à la banque

C'était le volet resté ouvert de `#485-r1-r4`. Les trois entrées `485` déjà présentes gardent des
**conséquences** d'un hissage (cible absente, attribut absent, forme A qui ne mord plus) ; celle-ci
garde la **population** — le compte des différés gratuits. Mutant : un différé gratuit ajouté dans
`engine/utilities/heal.py` fait passer le cliquet de `rc=0` à `rc=1` et **nomme** le couple.

⚠ **Portée** : la banque n'est plus obligatoire avant PR (retirée le 2026-08-05 ; elle refuse par
`rc=64` hors `TACTICUS_ALLOW_RATCHETS`). L'inscription rend le glissement visible aux passes de
**diagnostic** de l'orchestrateur, pas à chaque PR.

## 8. Ce qui n'est PAS couvert

- **La vidange des quatre barils ne libère AUCUN différé** — `probe_485` rend **273 / 270 / 3**
  avant comme après. L'énoncé de `#485-r3` (« même gisement, même forme et même remède » que le
  `−15` de `playbook`) est **réfuté sur l'axe du gain** : il reste vrai sur l'axe du *code mort* et
  sur celui de la *panne silencieuse*, pas sur celui des porteurs. Ces quatre barils ne sont pas
  sur les chemins qui ferment les cycles mesurés.
- Les **270** différés porteurs subsistants (le `723/723` reste **tenu par** eux).
- **`BARILS_A_REGISTRE` est une liste ATTESTÉE dans le probe**, alors que
  `migrate_485r1_barils_reexport.derive_barils` la **dérive** (`Baril.registre` = effets de bord ∪
  enregistreurs). Un sixième baril à registre qui apparaîtrait ne serait donc **pas balayé**, et le
  `0 mort` ci-dessus se lirait comme exhaustif sur un ensemble incomplet — exactement le vice que
  l'étage [0] existe pour ne pas commettre. Résidu **`#485-r7`**.
- **L'angle mort relatif n'a JAMAIS touché l'ACTEUR**, seulement l'inventaire : `vider` passe par
  `cible_absolue`, qui résout `level` depuis toujours. Les barils vidés par `#485-r1-r1` n'ont donc
  pas été traités sur un faux compte — c'est vérifié, pas supposé, et c'est ce qui borne la portée
  de cette correction au **rapport**, pas aux écritures passées.
