# #465 — un verdict du ledger n'est un FAIT que sur l'arbre où il a été mesuré

Le ledger `probe_462` (`scripts/ratchets-462-live-attestations.json`) keye ses attestations sur le
**BLOB** du fichier de test. Cette clé répond à « ce CONTENU a-t-il été mesuré ? », **jamais** à
« l'a-t-il été dans un ENVIRONNEMENT valide ? ». Un rouge d'environnement était donc **gelé à vie** :
rien ne le rejouait, puisque `--run --since <ref>` ne rejoue que les fichiers du DIFF.

## 1. La mesure qui l'a ouvert (2026-08-04)

Sur la tête de fusion de #555/#556/#557, `--report` rendait **3 ROUGES**. Les trois étaient
**périmés** — vérifié en les JOUANT :

| fichier | ledger | rejoué |
|---|---|---|
| `tests/engine/runner/test_nightshroud_combat_live.py` | ROUGE `p=1 f=1` | **2 passed** |
| `tests/engine/runner/test_terrifying_defense_live.py` | ROUGE `p=4 f=1` | **5 passed** |
| `tests/engine/test_fabricator_claw_cap_live.py` | ROUGE `e=10` (setup) | **4 passed** |

Le troisième portait sa propre réfutation : son `ImportError` citait
`.claude/worktrees/agent-a80ffd5838308fd70/…/probe_193c_move_playbook_terms.py` — un worktree
disparu, et un `BUILD_HASH` retiré par #431 (cause fermée depuis par **#462-r4c**).

**Coût réel, évité de justesse : trois PR ont failli être renvoyées à leurs auteurs.**

## 2. Le chiffre qui a tranché entre les trois pistes

Relevé sur les **254** entrées du ledger, à `e814745d` :

| position du `_commit` de mesure | entrées |
|---|---|
| au HEAD courant | **0** |
| sur un ANCÊTRE | 17 |
| **HORS de l'histoire** | **237** |

Les 3 non-VERTS étaient **tous les trois** « HORS histoire ». Et **234 des 251 VERTS aussi** — le
régime **NOMINAL**, car une attestation est écrite par un agent **avant son rebase**, donc son sha
meurt au rebase.

### Piste 1 — la RACINE git : retenue comme TRACE, **écartée comme critère**

Tentante (les 3 rouges venaient d'un worktree mort), mais la mesure l'interdit : **237/254** entrées
viennent d'un worktree d'agent disparu. Invalider là-dessus invaliderait aussi **234 verts sur 251**
et redonnerait les « non mesuré » silencieux — exactement le trou de #462. `_root` est donc **stocké
et affiché**, jamais évalué.

### Piste 3 — l'ÂGE : **RÉFUTÉE par mesure**

Les trois rouges gelés avaient **0,4 JOUR** d'âge. Tout seuil temporel utile (≥ 1 j) les laissait
passer ; tout seuil qui les aurait capturés aurait périmé les mesures fraîches. Sur ce dépôt
(~40 commits/jour) le temps est un **proxy bruité du churn**. `_at` reste au ledger pour la lecture,
il ne doit **jamais** redevenir le critère (test dédié).

### Retenu — le COMMIT, et l'unité est le commit

`etat_commit` ventile en quatre : `HEAD` / `ancetre` (+ distance) / `HORS` / `INCONNU`. Un non-vert
mesuré `HORS`, `INCONNU`, ou à plus de `DISTANCE_MAX_COMMITS` (20) devient **`A RECONFRONTER`**.
La distance ferme **l'autre porte du même gel** : un rouge mesuré sur master 200 commits en arrière
n'est pas davantage un fait sur cet arbre.

### Piste 2 — SETUP vs ASSERTION : retenue, **indépendamment**

`_verdict` ventile `ROUGE` (un `<failure>`, assertion évaluée) de `SETUP` (que des `<error>`). Cela
qualifie un verdict **frais**, avant toute péremption. Deux garde-fous :

- **SETUP dit OÙ l'échec est survenu, pas À QUI il est imputable** — une fixture casse aussi quand
  le dépôt régresse. Le probe ne classe pas (#533), il situe.
- **SETUP est aussi bloquant qu'un ROUGE** et pèse autant dans le code de sortie.

## 3. L'asymétrie est tout le dispositif

`verdict_effectif` est le **foyer UNIQUE** de la validité (un garde-fou dont le verdict dérive entre
ses lecteurs ne vaut rien) :

- **VERT ne périme JAMAIS.** Un vert périmé est *conservateur* — c'est le trou B (**#462-r1**),
  ouvert et chiffré.
- **Un NON-VERT mesuré ailleurs devient `A RECONFRONTER`** : listé, comptant, **bloquant**. Seul le
  RÉCIT change — « rejoue-le » au lieu de « c'est cassé ».

**La péremption ne peut pas desserrer la gate** : `_do_gate` ne laisse passer que `VERT`, et `VERT`
ne traverse aucune branche de péremption. C'est **structurel**, pas une précaution.

**Le code de sortie ne bouge pas.** `SETUP` et `A RECONFRONTER` sont des **ré-étiquetages** de ce qui
comptait déjà. Le défaut mesuré était un défaut de **LECTURE**, pas de rc — ne pas y toucher supprime
tout risque de permissivité non prévu.

## 4. Ce que la réparation a trouvé en chemin

Deux trous **antérieurs**, tous deux invisibles à l'œil :

- **`--report --since` était AVALÉ en silence** : le mode sortait avant de regarder `--since`, donc
  une lecture qu'on croyait bornée au diff rendait TOUT le ledger. C'est le contributeur direct à la
  mauvaise lecture du 2026-08-04. Corrigé.
- **Un verdict INCONNU s'évaporait du code de sortie** : la sélection par étiquette
  (`ROUGE`/`VIDE`/`NON JOUE`) ignorait toute autre valeur, donc une entrée tronquée se lisait comme
  un vert. Même vice que **#455-r3**, une porte plus loin. Trouvé par le **test cartésien**, pas à
  l'œil. Le rc est désormais la **formule invariante** « nombre d'entrées dont le verdict n'est pas
  VERT » — une catégorie oubliée ne peut plus rendre une entrée invisible.

## 5. La voie de sortie — `--run --stale`

Sans elle, `A RECONFRONTER` nommerait le problème et le figerait ailleurs. `_stale` reste **distinct**
de `_unmeasured` : l'un dit « on n'a AUCUNE mesure », l'autre « on en a une, il faut savoir si elle
est encore vraie ICI ». Joué le 2026-08-04 : **3 fichiers, 3 VERTS, mur 47,7 s**, ledger à 254 VERT
et `--report` à rc 0.

## 6. Contre-épreuves

`scripts/python/tests/test_465_ledger_validite_offline.py` (25 tests, offline, ~40 s). Le test
central est **`test_AUCUN_chemin_ne_rend_la_gate_permissive`** : produit **cartésien** verdict ×
position-du-commit × blob (7 × 5 × 2 = 70 gates), qui exige que la gate ne passe QUE sur
(`VERT`, blob courant). Un test cas-par-cas aurait laissé le trou là où on n'aurait pas pensé à
regarder — et c'est ce balayage qui a exhibé le trou des verdicts inconnus.

Les états de commit sont prouvés contre un **vrai dépôt git jetable** avec une branche divergente
(monkeypatcher `etat_commit` aurait testé le câblage, pas la détection).

**Quatre mutations, toutes mordent** :

| mutation | tests tombés |
|---|---|
| péremption PERMISSIVE (non-vert périmé → `VERT`) | **4**, dont le cartésien |
| faire périmer les VERTS aussi (rouvrir #462) | **6** |
| `SETUP` toléré par la gate | **2** |
| rc = somme des catégories (au lieu de l'invariant) | **1** |

## 7. Ce que ça NE couvre PAS

- **Le trou B (#462-r1) reste ouvert, et volontairement** : un fichier live que personne ne touche
  peut rotter sans que rien ne le voie. La réparation ne l'élargit ni ne le réduit — elle refuse
  seulement de présenter un rouge non reproduit comme un fait.
- **`A RECONFRONTER` n'est pas un diagnostic.** Le seul critère vraiment direct est « est-ce
  reproductible ICI ? », et la seule façon de le savoir est de **rejouer**. Tout le reste est un
  proxy ; `--run --stale` est la sortie, pas la péremption.
- **`DISTANCE_MAX_COMMITS = 20` est un curseur, pas un seuil dérivé.** Aucune entrée non-verte du
  ledger n'était dans ce régime au 2026-08-04 : la règle « distance » est donc **non confrontée sur
  gisement réel** (prouvée seulement contre le dépôt jetable). Se tromper vers le haut reconduit le
  statu quo ; vers le bas ne coûte qu'un rejeu.
- **Un `SETUP` n'innocente personne** : il situe l'échec, il ne l'impute pas.
- **Rien n'empêche un rouge d'être RÉEL et périmé à la fois.** Un rouge « hors histoire » qui serait
  encore vrai ici est correctement bloquant, mais il est présenté comme « à reconfronter » — il
  faut le rejouer pour le ré-établir.
- **#462-r2 (conflit du ledger) n'est pas traité** — cf. §8.

## 8. Effet sur #462-r2 (le conflit à chaque merge chaîné)

Le format gagne **une clé par entrée** (`_root`). Le régime de conflit est **inchangé en nature** :
JSON versionné, `indent=1`, `sort_keys=True`, résolution invariable **`--ours` puis RÉGÉNÉRER**. Le
nombre d'entrées en conflit ne bouge pas — c'est toujours « deux PR qui touchent le même fichier
live » qui collisionnent. L'aggravation est **marginale et textuelle** : ~13 lignes par entrée au
lieu de ~12, donc un hunk un peu plus large, jamais un hunk de plus.

**Piste non prise** (hors périmètre, à instruire séparément) : sérialiser chaque entrée sur **UNE
ligne** ferait tomber la résolution au niveau de la ligne et supprimerait l'essentiel des conflits.
Gain probable, mais c'est #462-r2, pas #465.

## 9. Fichiers

- `scripts/python/probe_462_live_tests_status.py` — `etat_commit`, `verdict_effectif`,
  `_verdict` (ventilation SETUP), `_relire`, `_stale`, `--report --since`, `--run --stale`.
- `scripts/python/tests/test_465_ledger_validite_offline.py` — les 25 contre-épreuves.
- `scripts/python/tests/test_462_gate_offline.py` — `test_un_echec_est_NON_VERT` reformulé sur le
  bon axe (la promesse « un `error` ne passe pas » est **inchangée**).
