# #363 — Le canal de la relique ÉQUIPÉE, branché PAR DÉFAUT (résidu `#357-r1`)

**Question binaire.** Le canal `load_state(ability_states=…)` posé par #357 n'avait qu'**un**
producteur. Faut-il le brancher par défaut — et à quel prix ?

**Réponse.** Oui, et le prix est **33 ms par bataille**, invariant à l'effectif, contre 312 à
1347 ms pour la capture que l'appelant fait déjà. Le canal est désormais **ON PAR DÉFAUT**.

Build de mesure : `rnca9r7q6c`. Montage : `probe_363_ability_states_channel.py`.

---

## 1. Le coût, mesuré AVANT de décider

Brancher d'abord et mesurer ensuite, ce serait décider sans son critère. La question posée n'est
pas « combien coûte le RPC » mais « quelle FRACTION de la capture il ajoute » : 33 ms sont
négligeables devant 900 ms et prohibitifs devant 5.

Médianes sur 12–15 appels, **premier appel exclu** (il paie la résolution IL2CPP — un coût
d'amorçage une-fois-par-session, pas le coût récurrent cherché).

| roster | unités | `decisionView` | `observeBattle` | `combatSnapshot` | `boardGraph` | **capture** | **`unitAbilityStates`** | part ajoutée |
|---|---|---|---|---|---|---|---|---|
| 2v2 | 4 | 178,3 | 33,8 | 36,7 | 63,4 | **312,2 ms** | **33,4 ms** | **+10,7 %** |
| 5v5 | 10 | 1174,9 | 34,0 | 74,5 | 63,9 | **1347,3 ms** | **33,4 ms** | **+2,5 %** |

Deux faits tranchent, et aucun n'était devinable :

* `unitAbilityStates` est le **moins cher des cinq** RPC de la capture ;
* il **ne scale pas** avec l'effectif (33,4 ms des deux côtés) là où `decisionView` est multiplié
  par 6,6 — donc sa part **recule** quand la bataille grossit. Mesurer une seule taille aurait
  laissé croire l'inverse.

Le seed Python lui-même est dans le bruit (< 0,3 ms, signe négatif compris).

## 2. Coût sur un batch : NUL — et c'est mesuré, pas affirmé

Le résidu désignait « `engine_validate`, `rl_collect_batch` et les ~200 call-sites ». Pour les deux
premiers c'est une **non-question** : ils ne construisent **jamais** de `State` ECS. La face
DÉCISION lit déjà le kit déclenché par un autre chemin — `engine/ai/context.py::live_triggered_ability_ids`,
sur le **même** RPC.

L'écrire sans le mesurer aurait été le geste qu'on corrige. `probe_363 --volet scan` balaie l'AST
(un grep compterait l'homonyme `rl_duel._load_state`, l'état du duel sur disque) :

| où | appels | fichiers |
|---|---|---|
| `tests/` | **333** | 197 |
| `probe_*.py` | **236** | 172 |
| `engine/` | **0** | — |
| outils (`rl_collect_batch`, `engine_validate`, …) | **0** | — |
| **total** | **569** | |

`load_state` n'est donc **pas** une API de moteur : c'est une API de **capture**, utilisée
exclusivement par les tests et les probes. C'est ce qui rend le branchement bon marché — et c'est
aussi ce qui dit **où** le brancher.

## 3. Ce qui est posé

### 3.1 Un TRI-ÉTAT, là où il n'y avait qu'un binaire

`load_state(ability_states=…)` distinguait `None` (rien) d'un payload. Trois états maintenant :

| valeur | sens |
|---|---|
| `<payload>` | l'appelant a déjà fait le RPC — comportement #357 inchangé |
| `None` (défaut) | **AUTO** : le canal se sert lui-même s'il le peut |
| `False` | **REFUS explicite** — l'état d'avant #357, pour une contre-épreuve |

Le troisième état n'est pas décoratif : sans lui, la contre-épreuve « sans rail » de #357
deviendrait, sous pytest, identique à son bras nominal — un vert qui ment. `probe_357` a été
corrigé pour l'utiliser.

### 3.2 Un transport AMBIANT, parce que `load_state` ne reçoit que des payloads

`load_state` ne peut pas aller chercher ce qui lui manque : elle ne voit pas de transport. Faire
remonter le besoin aux appelants voudrait dire éditer **569** sites sur **369** fichiers — et
surtout, chaque nouveau montage devrait y **repenser**, ce qui est exactement la dette que le
résidu constate.

`snapshot.bind_live_rpc(rpc)` lie le transport **une fois par harnais**.
`conftest.live_session` le fait pour toute la suite : les **333** appels des tests sont couverts
**sans éditer un seul call-site**. Un probe lancé en CLI ne l'est pas — c'est voulu, une mesure
historique doit rester reproductible telle quelle ; il lui suffit d'une ligne s'il en veut.

Le runner est identifié depuis les payloads eux-mêmes : `decisionView` / `observeBattle` /
`combatSnapshot` / `boardGraph` portent tous `runner` = `"build#<id>"` ou `"live"` — la seconde
forme se résout côté capteur sur `state.liveRunner`.

### 3.3 Le cache est une condition de DÉTERMINISME, pas une optimisation

Un probe rejoue couramment la **même** capture plusieurs fois (`probe_357` la rejoue trois fois pour
contraster ses bras). Si le canal repartait au live à chaque `load_state`, deux rejeux de la même
capture pourraient lire deux états différents : le rejeu offline cesserait d'être reproductible.

On capture donc **une fois par runner**. C'est fidèle : l'entrée tertiaire est **figée au montage de
l'unité** (`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`, appelé par
`UnitFactory$$Build`) — aucune Operation ne la réécrit, et les seules unités qui apparaissent ensuite
sont des summons, qui n'ont pas d'état JOUEUR donc pas de relique équipée. Le cache est purgé au
dispose d'un runner (`_release_runners`) : un `rid` est **recyclé** par un build ultérieur, et sans
cette purge le prochain runner du même id hériterait des reliques du précédent, en silence.

### 3.4 Pourquoi ce canal, et pas ses trois voisins

C'est le seul des quatre seeds de `load_state` qui cesse d'être opt-in, et la raison n'est pas le
coût :

* `tiles=` (#102) et `actor_stats=` (#340-r1) décrivent un **état qui bouge** (effets de tuile posés
  en cours de bataille, compteur remis à zéro chaque tour) : les fournir change ce que le port
  **calcule**, donc les activer partout serait un changement de comportement à évaluer scénario par
  scénario ;
* l'ability tertiaire est une donnée d'**identité**, du même ordre que le `visualId` ou les traits.
  Ne pas la poser n'est pas « un canal en moins », c'est une unité **décrite faux**.

### 3.5 La trace tri-état

`State.ability_states_seed` = `{"source": …, "seeded": …}`. `seeded = None` veut dire « le seed n'a
pas tourné », et `source` dit pourquoi : `given`, `auto`, `refused`, `no-snapshot`, `no-transport`,
`no-runner-label`, `unavailable:<msg>`.

C'est la discipline tri-état de `host_inputs.py` appliquée à un seed. Sans elle, un état sans relique
se lit comme « aucune relique équipée » alors qu'il peut signifier « le capteur est tombé ». On ne
**lève** pas sur une panne — un runner disposé entre la capture et le rejeu est un cas légitime —
mais on l'**écrit**.

## 4. Ce qui a été MESURÉ live

Les **4** unités qui équipent une relique dès le seed BC, montées d'un coup (deux par camp — le seed
ne doit pas dépendre du propriétaire), même capture lue de trois façons :

| bras | trace | ce que le port voit |
|---|---|---|
| **`auto`** (le défaut, rien demandé) | `auto` | les **4**, `(ability, 50, 200)` |
| `refused` (`ability_states=False`) | `refused` | **{}** |
| `given` (payload explicite, #357) | `given` | les **4**, identiques à `auto` |

Deux oracles **indépendants** l'encadrent, et le port coïncide avec les deux :

| unité | oracle CONFIG (`seed-bc.json`) | oracle NATIF (hiérarchie 3) |
|---|---|---|
| `necroSpyder` | `NetherRealmCasket` (1462) | `NetherRealmCasket` 50 / 200 |
| `orksRuntherd` | `SupaCyborkBody` (1475) | `SupaCyborkBody` 50 / 200 |
| `admecMarshall` | `KardiocoreGalvanus` (1457) | `KardiocoreGalvanus` 50 / 200 |
| `admecRuststalker` | `KardiocoreGalvanus` (1457) | `KardiocoreGalvanus` 50 / 200 |

Le bras `refused` n'est pas une redondance : s'il voyait quoi que ce soit, une **autre** voie
poserait la relique et le bras nominal ne prouverait rien du canal.

## 5. La garde, et le fait qu'elle rougisse

`tests/engine/runner/test_363_ability_states_default_live.py` — **10 tests**, 4 live + 6 offline.

Le point de conception qui compte : sous pytest, le probe **ne lie pas** le transport
(`bind_if_unbound=False`). Le bras `auto` s'appuie donc sur celui que le **harnais** a lié. Un probe
qui se lierait tout seul resterait vert avec un `conftest` débranché — il garderait le mécanisme,
pas le branchement, et c'est le branchement qui est le livrable.

Mutation `TACTICUS_NO_AMBIENT_RPC=1` (débranche l'ambiant) : **3 rouges ciblés** — les trois tests
qui portent sur le défaut ; `test_sans_le_canal_le_port_n_en_voit_aucune` reste vert, ce qui est
exact (il teste le refus).

Les six gardes offline verrouillent le contrat sans coûter un build : non-régression hors harnais
(`no-transport`), **1 RPC par bataille** et re-capture après purge, panne du capteur tracée et non
muette, tri-état de l'argument, et l'invariant « aucun outil de batch n'appelle `load_state` » — le
jour où l'un s'y mettrait, le calcul de coût serait à refaire, et cette garde le dirait.

## 6. Ce qui a été corrigé en route

* **`probe_357._port_repair`** passait `None` pour ses bras négatifs. Sous pytest, avec l'ambiant
  lié, ces bras auraient re-tiré le payload eux-mêmes et rendu le résultat du nominal. Passés à
  `False`.
* **`test_357::test_le_canal_reste_opt_in`** verrouillait la forme du `if` dans `load_state`. Le
  contrat qu'il protégeait vraiment — « un état chargé hors harnais live se comporte comme avant » —
  tient toujours ; il est désormais verrouillé par **mesure** (`_auto_ability_states` rend
  `no-transport`) et non par lecture de source, et un second test verrouille que le refus reste
  exprimable.

## 7. Ce qui n'est PAS couvert

* **Les 236 appels des probes** ne sont couverts que lorsqu'un probe est invoqué **via pytest**.
  Lancé en CLI, il garde le comportement d'avant tant qu'il ne lie pas le transport. Délibéré : une
  mesure historique doit rester reproductible telle quelle.
* **1 relique sur 32 est portée** (`DawnBlade`). Le rail inscrit ce qu'il trouve ; les 31 autres
  n'ont pas d'entrée dans `RELIC_ABILITY_TRIGGERS`, donc le branchement est pour elles un **no-op**
  fidèle — y compris pour les 3 abilities des 4 porteurs du seed (1462, 1475, 1457). La garde porte
  donc sur le **substrat** (`UnitContext.tertiary_ability`), pas sur un effet de jeu : c'est ce qui
  est mesurable aujourd'hui, et c'est ce qui rendra les 31 autres vivantes le jour de leur port.
* **Le canal `tiles=` et `actor_stats=` restent opt-in**, et gardent chacun leur unique producteur.
  Le raisonnement du §3.4 dit pourquoi ce n'est pas le même arbitrage — il ne dit pas que le leur
  est tranché.
* **Aucune mesure sous concurrence** : le transport ambiant est un état de module. Deux sessions
  pytest dans le même process partageraient le binding — cas qui n'existe pas aujourd'hui (une
  session pytest = un process), mais qui n'est pas gardé.
