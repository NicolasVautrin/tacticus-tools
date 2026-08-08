# #448-r5 — un recenseur qui QUALIFIE son graphe puis JETTE la qualification blanchit tout

**Statut** : RÉSOLU. Le critère de liaison ne passe plus par des noms nus ; le témoin qui montre le
gisement mordre est **exécutable et sous cliquet**. Le recensement reste à **0 amputé / 0
indéterminé** — le fix ne change aucun verdict d'aujourd'hui, il rend impossible le verdict FAUX de
demain. Et il ferme la question restée ouverte du volet 2 de `#521-r5` : les sites `auto` sans
ambiant hors suspects ne sont pas à trancher un par un (§4).

## 1. Le vice — l'étage 4 aplatissait ce que les étages 2-3 venaient de qualifier

`probe_448_r3_r1_r1_greffe_sans_canal.py` calcule la fermeture arrière des appelants du foyer de
liaison sur des nœuds `(module, fn)` :

```python
reach_bind = reaching(graph, {("engine.runner.snapshot", b) for b in BINDERS})
lieurs = {n for _m, n in reach_bind}                  # <- LA FAUTE
```

`binds_ambient(p, lieurs)` testait ensuite `lieurs & (called_names(tree) | referenced_names(tree))` :
un fichier était déclaré « lie l'ambiant » dès qu'il **mentionnait l'un de ces noms**, quel que soit
son module. Or la fermeture contient `main`, `run` et `mesure`. Tout script qui finit par
`sys.exit(main())` était donc blanchi.

C'est **exactement** la faute que la fiche parente dit avoir corrigée un cran plus haut, sur le
graphe de GREFFE (`case-448-r3-r1-r1` §2 : « un graphe par nom terminal rendait `main` greffeur, donc
1842 fichiers sur 1842 »), réintroduite sur le graphe de LIAISON — et la docstring de
`binds_ambient` affirmait « CRITERE DERIVE, pas une liste de noms » alors que c'en était une, plus
grosse.

## 2. Mesure (2026-08-08, `02c90668`) — le blanchiment est TOTAL sur le périmètre gardé

| | aplati (`master`) | honnête |
|---|---|---|
| fermeture du foyer | **121** nœuds `(module, fn)` réduits à **70** noms | 121 nœuds, gardés |
| fichiers déclarés lieurs | **1526 / 2287** | **37 / 2287** |
| **SUSPECTS déclarés lieurs** | **37 / 37** | **21 / 37** |
| sites `load_state` `auto` sans ambiant (tout le corpus) | **0** | **388** |

**1489 fichiers blanchis à tort**, et surtout : **la totalité des 37 suspects**. Sept d'entre eux
sont hors `tests/` et ne sont sauvés que par leur régime `given` — `probe_366_r1_stormboyz_strike`,
`probe_419r1tr14r4_heavy_bolt_pistol_bonus_attack`, `probe_419r3_fold_attack_state`,
`probe_448_r1_r1_full_throttle`, `probe_448_r1_r1_r1_flying_movement_steps`,
`probe_448_r1_r1_r2_fly_override`, `probe_478_cleave_additional_targets`. Le jour où l'un d'eux
ajoute un `load_state` nu, le cliquet reste **VERT**.

⚠ Les chiffres du résidu (`117` nœuds / `291` fichiers / `550` sites) datent du 2026-08-07 : le
corpus a grossi. **Re-dériver**, jamais citer.

## 3. Le critère honnête est une UNION, et la mesure établit que les deux voies sont nécessaires

* **graphe QUALIFIÉ** — un fichier est lieur si l'une de SES fonctions est dans `reach_bind`. C'est
  le patron déjà employé pour `greffeurs` et `lecteurs`, deux lignes plus haut.
* **mention du FOYER** — `bind_live_rpc` / `live_rpc` nommés dans le fichier. Rattrape les formes
  que le graphe syntaxique ne résout pas (112 993 appels non résolus à l'étage 5).

Mesuré : **11** fichiers ne sont vus que par le graphe, **7** que par la mention, **19** par les
deux. Aucune des deux ne se suffit — et la mention porte sur **deux** noms, pas soixante-dix : c'est
là toute la différence avec la version fautive.

**La dégradation a changé de sens, et c'est ce qui rend le fix sûr.** Un retour aux noms nus donne
`path in {<str>}` toujours faux ⇒ le probe devient **sur-accusateur** (rouge), plus jamais
silencieux.

## 4. Le volet 2 de `#521-r5` est CLOS — et la réponse n'est pas « trancher les 291 »

Le résidu demandait de trancher les sites `auto` sans ambiant. Re-dérivés : **388 sites sur 293
fichiers**, et parmi eux **0 fichier GREFFEUR** (0 aussi sous `tests/`). Ces sites chargent un état
que **rien n'a greffé** : `collect_triggered_abilities` retombe sur le gameconfig, ce qui est
**correct**, pas amputé. Ils sont hors gisement **par construction du recenseur** (SUSPECTS =
greffeurs ∩ lecteurs), et la mesure le confirme au lieu de le supposer.

Ce qui reste ouvert est l'angle mort déjà nommé, pas celui-ci : un seed BC greffé par un **autre
processus** (`--seed-bc <chemin>`), résidu `#448-r3-r1-r1-r1`.

## 5. Le témoin — un critère qu'on n'a jamais vu rouge ne garde rien

La contre-épreuve `--mutate` **ne pouvait pas voir cette faute** : elle appelait `binds_ambient(p)`
sans jeu de lieurs, donc elle validait le **repli**, jamais le critère réellement appliqué par
`measure`. Deux mutants la referment :

```
mutant_vrai_lieur.mesure(rpc) -> S.bind_live_rpc(rpc)      # fait entrer le NOM `mesure` dans la fermeture
mutant_faux_lieur.mesure(x)   -> x + 1                     # HOMONYME : greffe + load_state nu, ne lie rien
```

```
fichiers LIEURS (qualifie) : mutant_vrai_lieur.py
verdicts : {..., 'mutant_faux_lieur.py': False}
TEMOIN #448-r5 : critere APLATI blanchit le faux lieur = True (attendu True)
```

Le test assertionne les **deux** côtés — que le critère de `master` blanchissait ce fichier, et que
le critère corrigé l'accuse. Sans le premier volet, le témoin ne prouverait pas que le gisement
existait ; sans le second, qu'il est fermé. Et il **assertionne son propre montage** (`"mesure" in
noms_nus`) : si la fermeture cessait de porter cet homonyme, le témoin deviendrait vide — donc vert
à tort.

## 6. Le cliquet

`tests/engine/test_448_r3_r1_r1_greffe_sans_canal_offline.py` — **15 passed** (était 13), 100 %
offline. Deux gardes ajoutés :

1. `test_le_jeu_de_lieurs_reste_un_ensemble_de_CHEMINS` — garde de **TYPE**, pas de seuil : un
   ensemble de `str` ne peut pas contenir un `Path`. C'est ce qui empêche la réécriture de revenir.
2. `test_un_HOMONYME_ne_fait_pas_un_lieur` — le témoin du §5.

Les 13 tests existants sont inchangés, et la mesure du corpus est désormais partagée par une
fixture `scope="module"` : sans elle, chaque garde ajoutée coûtait ~90 s de `ast.parse`.

## 7. Ce qui n'est PAS couvert

* **La mention du foyer compte la simple RÉFÉRENCE** : un fichier qui DÉLIE puis RESTAURE
  (`prev = unbind_live_rpc()` … `bind_live_rpc(prev)`) est compté lieur alors qu'il tourne délié.
  Prix assumé du rattrapage des formes non résolues ; imprimé à l'étage 5 de chaque run.
* Les trois angles morts hérités de la fiche parente (autre processus, appels dynamiques, payload
  non vérifié non vide) sont inchangés.
* **Le fix ne fait bouger aucun verdict d'aujourd'hui** : 0 amputé / 0 indéterminé avant comme
  après. C'est un cliquet réparé, pas un bug de port trouvé — et le §2 dit précisément quels sept
  fichiers ce cliquet ne gardait pas.

## 8. Reproduction

```
python scripts/python/probe_448_r3_r1_r1_greffe_sans_canal.py
python scripts/python/probe_448_r3_r1_r1_greffe_sans_canal.py --mutate
python -m pytest scripts/python/tests/engine/test_448_r3_r1_r1_greffe_sans_canal_offline.py -q
```
