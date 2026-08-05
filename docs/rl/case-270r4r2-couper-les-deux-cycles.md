# #270-r4-r2 — couper les deux cycles d'import module-level d'`engine/`

**Livré le 2026-08-05.** Instruments : `probe_270r4r2_cycles_imports.py`,
`probe_270r4r2_import_en_premier.py`, `probe_270r4r2_empreinte_valeurs.py`.
Cliquet : `tests/engine/test_270r4r2_cycles_imports_offline.py`.

## 1. Ce qui a été coupé, et ce qui ne l'a pas été

| | avant (`origin/master` `778c2ea5`) | après |
|---|---|---|
| arêtes module-level | 2329 | 2334 |
| **SCC > 1 (module-level)** | **2** (7 et 6 modules) | **0** |
| instructions d'import différées vers `engine/` | 990 / 195 fichiers | **971 / 194** |
| SCC du graphe « tous imports » | 284 modules | 275 |

Les deux SCC avaient la **même forme** : un `__init__.py` qui ré-exporte ses enfants, et des
enfants qui ré-importent **à travers le paquet** (`from . import fix64`, `from . import
prediction`). La coupe porte sur les **enfants**, jamais sur les ré-exportations.

**Invariant, mesuré et non espéré** : **224** fichiers hors de ces deux paquets lisent un attribut
d'`engine.playbook` ou d'`engine.services` ; **0** d'entre eux n'a changé **un seul import**
(comparaison AST des lignes d'import contre la base de rebase, pas comparaison de fichiers — un
test peut changer ses assertions sans que l'API d'import bouge).

## 2. La forme de la coupe

`from . import <frère>` déclare le **paquet** comme source (il en lit l'attribut).
`import engine.<pkg>.<frère> as X` déclare le **module**, et lie par `sys.modules`. C'est le seul
changement, une ligne par fichier — donc **zéro réécriture des sites d'usage**, ce qui est ce qui
rend l'invariance de comportement vérifiable.

13 fichiers : `services/{damage_calculations,damage_modifiers,damage_prediction,min_max_damage,
static_battle_rules,ability_range,targeting_query}.py`,
`playbook/{base,common,daemonic_ordnance,excruciating_frequencies,loki_custom,plagueburst_mortar}.py`.

## 3. Le graphe ne voit pas tout, et c'est pourquoi il y a DEUX cliquets

Le graphe modélise la **source déclarée**. Il est **aveugle** aux cycles qui passent par un paquet
**ancêtre**, que Python exécute quoi qu'on écrive :

```
engine.dsl.base -> engine.entities (init) -> effects_state -> effects -> factory
                -> effects.loki -> ability_modifications -> entities.selectors
                -> selectors._shared -> `from ...dsl.base import TargetsSelector`   <- casse
```

Cette boucle **n'apparaît dans aucun SCC** et lève pourtant un `ImportError`. Le second cliquet
(`probe_270r4r2_import_en_premier.py`) importe chaque module **EN PREMIER** dans un interpréteur
frais — **191/191** verts. Un cycle ne se voit que dans **un sens** ; un seul ordre d'entrée ne
prouverait rien.

## 4. Les trois sites de `#270-r4` — les trois fermés, mais pas par la coupe

- **`entities/triggers.py` → `UnitTrait`** (2 différés) : leur motif écrit (« lazy — même garde
  anti-circulaire ») est **RÉFUTÉ**. Le hissage passe depuis 8 ordres d'entrée, et il passait
  **déjà avant la coupe**. Différé **gratuit**, pas un brise-cycle.
- **`dsl/base.py` → `StatType`** : le différé brisait un **vrai** cycle (§3). Hissé **en fin de
  fichier** : `TargetsSelector`, le seul symbole que la boucle lit, est défini plus haut. Reste un
  import **module-level** (échec déterministe à l'import) au lieu d'un différé (payé à chaque
  appel, échec dépendant du chemin d'exécution).
- **`services/static_battle_rules.py` → `EffectType`/`UnitTrait`** : **converti**, 5
  collections/constantes passent des ordinaux aux membres. Même recette : la boucle ne lit qu'**un**
  symbole (`TILE_STATUS_EFFECT_NAMES`), les imports sont placés juste après lui. 11 ordres
  d'entrée, 0 échec.

⚠ **La condition de retournement écrite par `#270-r1-r1-r1` était TROP FORTE.** Elle disait :
« convertir le jour où `engine.entities` n'importera plus `services.static_battle_rules` ». Cette
condition est **toujours fausse** — le paquet tire encore cet arbre — et la conversion est faite.
Ce qui débloquait n'était pas la disparition du cycle mais sa **lecture** : compter ce que la
boucle consomme vraiment. Une condition de retournement formulée en « le jour où le monde
changera » fait attendre pour rien.

## 5. Ce qui reste ouvert

`engine/entities/__init__.py` tire l'arbre complet des effets ; toute couche basse qui importe
quoi que ce soit sous `engine.entities` ferme donc une boucle, et la parade est à chaque fois un
**placement**. Rayon mesuré de la coupe qui rendrait le placement indifférent : **41** fichiers
lisent **9** symboles du paquet `engine.entities` (aucun n'est dans le paquet lui-même). Résidu
**#270-r4-r2-r1**.

Restent **971** instructions d'import différées vers `engine/` dans `engine/` (43 `TYPE_CHECKING`,
928 en corps de fonction). Elles n'ont **pas** été triées — le tri se fait fichier par fichier, par
hissage + import depuis plusieurs ordres d'entrée (protocole du §3). Les 8 traitées ici
(6 `turnflow.py`, 2 `entities/triggers.py`) l'ont toutes été **sans qu'aucune ne brise de cycle** ;
seul le différé de `dsl/base.py` en brisait un. Résidu **#270-r4-r2-r2**.

## 6. Invariance de comportement

`probe_270r4r2_empreinte_valeurs.py` hache la **valeur** (`int(x)` récursif dans les conteneurs,
jamais `repr`) de **tout** attribut de module ET de classe d'`engine/`, contre un arbre témoin
extrait par `git archive` **complet** (sans `data/`, les caches *lazy* du gameconfig rendent des
divergences fausses).

**0 divergence de VALEUR sur 188 138 attributs.** Les noms apparus sont listés, jamais tus : ce
sont les imports hissés (et les ~116 membres d'un enum hissé, résumés par classe). Contrôle
dirimant : les 5 collections converties de `static_battle_rules` **n'apparaissent pas** dans les
noms — leur valeur est identique, `frozenset({58, 5, …}) == frozenset({EffectType.Darkness, …})`.

## 7. Ce qui a été rejoué

**Offline** : 125 passed sur le lot ciblé (dont `test_287r1r1_verify_turn_ended_offline` et
`test_287r1_no_action_available_offline`, les deux gardes de `turnflow.py`), 8 passed sur
`test_270r1r1_container_enum_offline` (étage 4 réécrit), 4 passed sur le cliquet neuf.

**Live** : 31 passed — `test_daemonic_ordnance_decision_live` (18),
`test_plagueburst_mortar_prediction_live` (9), `test_noblocking_prediction_live` (2, il exerce
`not_blocking_movement_of_traits`, la fonction dont les tuples ont été convertis),
`test_damage_roll_live` (2, la chaîne `services/damage_*`).

**Contre-épreuve du cliquet** : réintroduire un seul `from . import fix64` dans
`min_max_damage.py` le fait rougir avec `SCC de 4`. Sans cette mutation, un `_cycles` cassé
rendrait `[]` pour toujours.

**Non couvert** : les **386** tests impactés (fermeture module-level) n'ont pas été joués — 4
fichiers live l'ont été, choisis sur les chemins réellement modifiés. Le filet réel n'est pas le
volume de tests mais l'empreinte du §6, qui porte sur **tout** `engine/` et qui, elle, est
exhaustive.

## 8. Le coût d'import n'est pas un motif pour différer

Mesuré sur `turnflow.py` (18 mesures par variante, `.pyc` chauds) : hisser ses 3 derniers différés
porte le chargement de **276 à 341** modules `engine`. C'est payé **une fois** par processus,
là où un différé dans une fonction chaude coûte un lookup `sys.modules` **à chaque appel**. Les
6 ont été hissés.
