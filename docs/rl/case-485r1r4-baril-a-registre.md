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

## 6. Ce qui n'est PAS couvert

- Les **262** différés porteurs subsistants (le `430/430` reste **tenu par** eux).
- **Inscrire `probe_485_imports_differes.py` à la banque** — sans quoi le prochain glissement sera,
  lui aussi, invisible. C'est le vrai correctif de fond, et il reste ouvert sous `#485-r1-r4`.
- Les quatre autres barils (`#485-r3`).
