# case-366-r1-bcpatch-invisible — un patch de variable d'ability est INVISIBLE du port

**Le fait.** `BC.Abilities.<node>[<ability>].Variables[<var>]` n'est lu que par le NATIF. Le moteur
Python lit `gameconfig` — foyer unique `engine/entities/effects/magnitude.py::ability_var`, qui ne
touche jamais le BC. Toute fixture qui patche une variable d'ability y arme donc une
désynchronisation : elle est **inerte tant que l'effet visé n'est pas porté**, et devient **fausse
le jour du port**. Mesuré le 2026-08-01 en portant `1116` — `InescapableAccuracy.extraCritDmg = 0`,
neutralisation la veille, erreur de **997 points** le lendemain.

**Le cliquet.** `python scripts/python/probe_366_r1_bcpatch_port_blindspot.py` (rc 0 attendu,
~30 s, 100 % offline) + garde pytest `scripts/python/tests/test_366_r1_bcpatch_port_blindspot_offline.py`
(14 tests). Il croise deux recensements statiques et **rougit sur l'intersection** :

| côté | ce qui est recensé | mesure du 2026-08-01 |
|---|---|---|
| SEED BC | `patch_ability_variables`, `write_variable_patched_seed_bc`, écriture directe dans `BC.Abilities` (alias de sous-arbre suivis) | **3 couples**, 4 modules |
| PORT | `ability_var(<ability>, <var>)` sous `engine/**`, **relais propagés** | **938 couples**, 261 sites |

**La prémisse est MESURÉE, pas supposée** (`test_le_patch_arrive_au_natif_et_PAS_au_port`) : on
force `InescapableAccuracy.extraCritDmg = 12345`, puis on lit des deux côtés — par le chemin du
build (`_load_seed_bc`, ce que le runner natif reçoit) on relit `12345` ; par `magnitude.ability_var`
on relit la valeur du gameconfig, intacte. Si ce test rougit un jour, `ability_var` a changé de
source et tout le cliquet est à re-dériver.

**Une SECONDE SOURCE le contrôle** (`grep_literal_pairs`) : les couples littéraux repérés au grep,
sans le moindre AST, doivent tous figurer au recensement. Elle a trouvé **3 faux négatifs** que
rien d'autre n'aurait montrés — `FleshmetalGuns`, dont la variable s'écrit `"minDmg" + sfx`.

**Pourquoi la propagation des relais n'est pas un luxe.** Les gros consommateurs
(`ability_attack_params`, `AttackWithAttackDamage`, `ConfigVarForEntity`, `build_summon_context`)
reçoivent ability/variable de leur APPELANT. Sans point fixe, 310 axes sortaient « dynamiques » —
donc un joker qui fait rougir n'importe quel patch et n'apprend rien. Trois règles ont fait la
différence, chacune payée par une mesure fausse : retirer `self` de la signature vue de l'appelant
(sinon on lit l'argument du voisin — l'axe ABILITY résolvait sur `"chance"`, et le recensement
rendait des « abilities » nommées `hp`, `hpPct`), lire les **défauts** de la signature (un argument
non passé n'est pas indéterminé — 310 axes sortaient « dynamiques »), et refuser d'attribuer un
appel dont le nom est ambigu (`execute` a 18 définitions dans `engine/`, une seule porte
`summon_ability` ; la règle qui tranche est celle de Python — un paramètre requis non fourni rend
l'appel impossible, donc ce n'est pas cette définition).

**Invariant, pas seuil** : `intersection == 0`, avec des exceptions **nommées** et justifiées une
par une (`_EXCEPTIONS`), plus deux listes du même genre pour ce que le balayage ne peut pas
décider : `_UNRESOLVED_PATCHES` (patch à clé calculée) et `_COVERAGE_HOLES` (site du moteur où ni
l'ability ni la variable ne sont déterminables). Une exception **orpheline** rougit aussi.

**Ce qu'il a trouvé sur `origin/master`** (avant nommage) : **3 couples** patchés ET lus.
`InescapableAccuracy/extraCritDmg` (déjà connu, `--zero-crit-dmg`, défaut `False`) et
`LightImUp/minDmg` + `LightImUp/maxDmg` — le montage #369, jamais recensé sur cet axe. Les trois
sont des désynchronisations **inhérentes** (le régime `minDmg + maxDmg == 3 mod 4` n'existe à aucun
niveau du gameconfig : l'atteindre EXIGE d'écrire dans le BC) et **sans conséquence tant que le
montage ne confronte que le natif** — condition désormais écrite dans la docstring de
`probe_369.build_regime_seed_bc` et dans `_EXCEPTIONS`.

**La morsure, vérifiée** (`--self-test`) : le geste de `1115` réintroduit rougit sous ses **quatre**
formes d'écriture (helper, constante + ternaire, écriture directe, alias de sous-arbre), un couple
lu seulement à travers un relais rougit aussi, et une variable de la **même ability** que le port ne
lit pas reste **verte**.

**Ce qui n'est PAS couvert** : balayage statique de `scripts/python/**` — un appelant hors Python
qui poserait `--seed-bc <fichier patché>` est invisible (même limite que `probe_380`) ; le CONTENU
d'un seed BC sur disque se mesure par `probe_380 --check <bc>` ; 1 abstention d'attribution
(`behaviours/summon.py` `execute(summon_ability)`) et 1 trou de couverture nommé
(`operations/spawn.py`, variable bâtie par concaténation `summon* + key_suffix`).

**Complémentaire de `probe_380`, pas redondant** : celui-là demande « le NATIF voit-il le patch ? »
(survie au rattrapage `refresh_ability_configs`), celui-ci « le PORT le voit-il aussi ? ». Un patch
qui SURVIT est précisément celui qui peut désynchroniser.
