# #270-r4-r2 / #949-r1 / #486-r24 — trois rouges d'outillage, trois verdicts DIFFÉRENTS

`master` = `dc30a1ad`. Les trois tests étaient rouges ensemble ; ils n'avaient **pas** la même
maladie. C'est le point de la fiche : un rouge d'outillage se diagnostique d'après le rouge
COURANT, jamais d'après son en-tête.

| test | verdict | ce qui l'établit |
|---|---|---|
| `test_270r4r2_cycles_imports_offline::test_etage1_aucun_cycle_module_level` | **le cliquet a RAISON** | l'invariant a été ATTEINT (SCC=0 mesuré à `1370d930`) puis a décliné à 4 SCC |
| `test_949r1_lecteurs_de_ledger_offline::test_aucun_lecteur_neuf_n_entre_dans_la_dette` | **le cliquet a RAISON** | le site accusé confronte bien un ledger incomplet à `rec["live_per_hit"]` |
| `test_486r24_bypass_confrontation_offline::test_un_import_RELATIF_ne_se_resout_PAS_contre_la_racine` | **PRÉMISSE EXPIRÉE** + **INVENTAIRE FAUX** | deux assertions, fausses pour des raisons OPPOSÉES |

---

## 1. #270-r4-r2 — les 4 SCC, et pourquoi personne ne pouvait les voir

### Le cliquet AVAIT été satisfait — mesure, pas souvenir

Le probe **courant** rejoué sur des arbres historiques (`git archive <rev> scripts/python/engine`
dans un temporaire, `CY.RACINE` repointée) :

| rev | date | modules | SCC > 1 |
|---|---|---|---|
| `1370d930~1` | 2026-08-05 | 409 | **2** |
| `1370d930` (la coupe) | 2026-08-05 | 409 | **0** |
| `c0831857` | 2026-08-07 | 437 | **0** |
| `dc30a1ad` | 2026-08-18 | 721 | **4** (17, 14, 7, 5) |

Le modèle du probe n'a pas bougé entre-temps : le seul diff depuis la coupe est l'ajout du
paramètre `prefixes` (#486-r11), qui ne change pas ce que ce cliquet-ci mesure. Donc ni prémisse
expirée ni inventaire faux : **décroissance pure**, alimentée par notre propre cadence.

### Les 4 SCC se referment TOUS par la même arête, et elle a un nom

21 lignes, 21 fichiers, un seul patron : **un enfant qui déclare son PAQUET ANCÊTRE** pour
atteindre un module.

```
from ..   import ctx_keys as _ctx_keys          13 x  effects/loki/*        -> declare `entities.effects`
from ..   import base as _abase                  2 x  runner/abilities      -> declare `runner.abilities`
from .    import _targets as T|_T                4 x  playbook/noncomparable-> declare le paquet
from .    import displace_utility as _displace   1 x  playbook              -> declare `playbook`
from engine.playbook import should_evaluate_target as _SET   1 x            -> declare `playbook`
```

Sans ces 21 arêtes, aucun SCC ne se referme : le reste est `__init__` -> enfants (descendant) et
enfant -> frère (latéral).

### La réparation NE change pas le régime d'import, seulement la VOIE DÉCLARÉE

Les 21 lignes sont **déjà** en FORME B (liaison de MODULE) et le **restent** :

```
from .. import ctx_keys as _ctx_keys
->  import engine.entities.effects.ctx_keys as _ctx_keys
```

Même module chargé, même objet lié, même morsure sous `monkeypatch`. Ce qui change est la
**source déclarée** : le paquet ancêtre disparaît du graphe. Contrôle : `6498 -> 6477` arêtes,
soit **exactement** les 21 arêtes de paquet retirées, et `migrate_485r1_barils_reexport.py
morsure` **inchangé** (`DEJA_INERTE 66 / DIFFERE_MORDANT 12 / HISSAGE_DESARMERAIT 1 / 396 / 475`).

⚠ **L'idiome n'est pas une invention de cette tranche** : `attempted_possession.py:113` le porte
depuis #547-r2, avec sa raison écrite — « ABSOLUE ... le MODULE, pas le paquet parent, pas le
symbole ». Il fallait l'appliquer aux 21 autres.

⚠ **Et il n'y a AUCUNE écriture RELATIVE qui satisfasse les deux doctrines.** `from ..frere import
X` est la forme A (elle ne mord pas, #484 / #429-r1) ; `from .. import frere` est la forme B mais
déclare le paquet. La seule qui tienne les deux est l'`import` **absolu et pointé**.

### TROIS commentaires disaient « ne ferme aucune boucle ». Les TROIS étaient FAUX.

Sur les trois lignes qui refermaient précisément un SCC :

* `behaviours/combat.py` — « l'ajout ne coûte AUCUN module et **ne ferme aucune boucle** » ;
* `loki/attempted_possession.py` — « donc l'ajout ne coûte AUCUN module et **ne ferme aucune
  boucle** » ;
* `playbook/nonattack.py` — « **Feuille, aucune arête de cycle.** »

C'est la leçon #485-r5 à l'identique, sur un autre axe : **une raison ÉCRITE survit à la
disparition de son objet, et elle décourage la vérification.** Les trois sont corrigés avec la
mesure qui les contredit.

### La décroissance était INVISIBLE, et elle avait DEUX causes

1. `probe_270r4r2_cycles_imports.py` **n'est pas une entrée de `scripts/ratchets.ps1`** ;
2. le test **ne portait aucun `DECLENCHEUR`** (il est dans la dette de 701). Or il lit `engine/**`
   par **`rglob`**, et ni lui ni ses deux probes n'importent quoi que ce soit d'`engine` : la
   sélection `probe_457.impacted_files` le passait donc par le **graphe d'imports**, où **aucune
   arête** ne le relie au gisement qu'il garde. **Aucun diff d'`engine/**` ne l'a jamais rejoué.**

Le `DECLENCHEUR` est posé, dérivé par `probe_486r15 --proposer` et élargi à
`scripts/python/engine/**/*.py`, qui EST le gisement.

⚠ **`--proposer` conseille d'écrire AUSSI `engine/*.py`** (« dans ce matcher, `**/` exige un
segment »). **Mesuré faux pour le matcher en jeu** : `declencheur_cliquet.couvre` — que
`probe_457` appelle lui aussi (l. 2383) — donne `scripts/python/engine/**/*.py` pour
`engine/battle_query.py` **et** `engine/__init__.py`. La seconde forme ne serait qu'un
`redondants` de plus. Le conseil est resté générique là où le foyer est unique.

---

## 2. #949-r1 — le cliquet a RAISON, mais il a mordu pour la mauvaise raison

L'accusé : `tests/engine/runner/test_1049_red_thirst_walking_pox_live.py`.

**L'accusation est juste.** Ses deux bras de contre-épreuve rendaient `last["per_hit"]` **seul**,
et `test_redthirst_charge_blesse_les_deux_canaux` met ce retour EN FACE d'un ledger NATIF :

```python
assert len(rec["live_per_hit"]) == len(ctl) + 1
deltas = {a - b for a, b in zip(rec["live_per_hit"], ctl)}
```

C'est exactement la forme #949 (« 8 coups natif contre 6 port ») et #1065 (`FragLanceEffect`,
live n=5 / `per_hit` n=4).

**Réparé au SITE** — un foyer `_ledger_complet(runner)` recolle les deux canaux, même convention
que `_charge_regime.replay_offline::per_hit_all`. **Jamais par ajout à la dette** : le message du
cliquet l'interdit, et il a raison de l'interdire.

**Value-preserving, et c'est MESURÉ** : le `+extraHit` de `RedThirst` est un HITS BONUS
(`..._ExtraDamageAndHitEffect$$CreateEffectHitsBonusForAttack` ->
`damage_model.py::build_hits_board`), donc il grossit la phase d'ARME et ne passe pas par le canal
#179. Le fichier live rejoué APRÈS édition : **7 passed**, identique.

**Le cran qui empêche la sortie de vider le test** : le fichier entre dans `RECOLLENT_ATTESTES`.
Sortir de la dette sans entrer dans l'attestation rendrait la régression à nouveau invisible.

⚠ **Mais la RAISON pour laquelle le recenseur a mordu est un accident**, et ça ouvre `#949-r3`.
Son étage 3 (« la fonction qui contient la lecture met-elle celle-ci en face d'une valeur
native ? ») a trouvé le token `live` dans la **DOCSTRING** de `_replay_with_effect_forced`
(« le bras prouvait donc « live == offline » »). Symétriquement, il a **manqué**
`_replay_without_effect`, dont le retour est confronté **une fonction plus haut**. Le périmètre
est la FONCTION ; la confrontation, elle, traverse les frontières de fonction.

---

## 3. #486-r24 — deux assertions, fausses pour des raisons OPPOSÉES

### (a) L'assertion 1 était VACUEUSE depuis le premier jour

Elle interrogeait `engine/entities/pathfinding/pathfinders.py`, qui **n'a JAMAIS porté**
`from .board import` (`git log -S` rend **zéro** commit) — et `Fermeture.cibles` ne rend que les
cibles **DIRECTES**.

**Contre-épreuve** (2026-08-18) : en remettant la résolution buguée (`_paquet` -> `[]`),
`walk_pathfinder.py` **et** `beeline_pathfinder.py` fabriquent bien `scripts/python/board.py` ;
`pathfinders.py` ne le fabrique **PAS**. Le témoin cité n'aurait pas pu voir le bug qu'il
prétendait garder.

Le témoin est désormais **DÉRIVÉ** de l'arbre (tous les modules qui écrivent `from .board
import`), sa liste doit être **NON VIDE**, et chaque porteur doit rendre la **BONNE** cible autant
que ne pas rendre la fausse — retirer l'import relatif fait donc **rougir** au lieu de rendre le
test muet.

### (b) L'assertion 2 accusait une bonne nouvelle

`assert "scripts/python/board.py" not in casc` était un témoin **INDIRECT** : il ne tenait que
tant qu'aucun membre de la cascade n'importait `board` pour de bon. `897590ea` (#1044,
2026-08-14) a fait entrer `probe_1044_levier_traits` dans `tests/engine/conftest.py`, qui tire
`rl_duel`, qui écrit `from board import Board` **depuis le 2026-06-15**. La cible est RÉELLE.

### Le cran n'est pas retiré, il est REMPLACÉ par un invariant PLUS GÉNÉRAL

`test_aucune_cible_TOP_LEVEL_de_la_cascade_n_est_FABRIQUEE` : **une cible top-level n'est
attribuée à un module que s'il l'importe en NIVEAU 0** — pour n'importe quel nom, pas seulement
`board`.

* sans le bug : **0 faute sur 725 modules**, **306** attributions top-level examinées
  (l'anti-vacuité est assertionnée sur ce 306, pas supposée) ;
* avec le bug remis : **1 faute** (`walk_pathfinder.py -> scripts/python/board.py`), et la
  cascade tombe de 725 à **128** modules — la sous-approximation que #531 décrivait.

Les trois modules qui atteignent `scripts/python/board.py` aujourd'hui (`oracle.py`,
`rl_duel.py`, `rl_probe_step.py`) l'importent **absolument** : le nouvel invariant les accepte et
accepterait tout futur importateur honnête, sans jamais accepter une cible fabriquée.

---

## Ce que la tranche NE couvre PAS

* **`probe_270r4r2_cycles_imports.py` n'entre pas dans `scripts/ratchets.ps1`.** Le
  `DECLENCHEUR` posé suffit à faire rejouer le TEST sur tout diff d'`engine/**`, ce qui exécute
  la même mesure ; l'entrée de banque serait un second canal, pas un cran manquant.
* **L'étage 1 reste un modèle de la source DÉCLARÉE**, pas du graphe Python réel — son propre
  en-tête le dit. Un `__init__` qui importe ses enfants forme toujours un cycle *réel* par le
  paquet ancêtre ; c'était déjà vrai au commit où le cliquet valait 0. Ce que 0 SCC garantit est
  exactement ce que le cliquet annonce : aucun enfant ne lit l'attribut d'un paquet qui est en
  train de l'importer.
* **La cécité inter-fonctions du recenseur #949-r1** (`#949-r3`, ouvert) : les autres fichiers de
  `DETTE_ATTESTEE` n'ont pas été re-triés site par site.
* `tests/engine/test_nc_priority_tiers_offline.py` est rouge (2 failed / 3 passed,
  `AttributeError: 'types.SimpleNamespace' object has no attribute 'machine_of_war_position'` dans
  `engine/ai/action_generators.py:220`) — **déjà rouge sur `dc30a1ad`**, vérifié en rejouant le
  fichier contre l'`engine` de base. Hors périmètre (fichier réservé).
