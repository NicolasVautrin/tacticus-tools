# #943-r7 — la crainte qui bloquait les 19 sites présupposait que les DEUX faces étaient nues

Les 19 sites `LISTE_STOCKEE` de `GEOMETRIE_NUE_CLASSEE` décidaient une adjacence par
`hexgeo.distance == 1` là où le natif énumère `ConnectivityComponent+0x10`. Ils n'avaient pas été
réparés pour une raison écrite noir sur blanc : « ce sont majoritairement des **couples
runner/décision**, et n'en câbler qu'un côté **crée** la divergence de faces que la réparation de
`_fighting_retreat_sets_flags` vient de résorber ».

**Cette raison est vraie pour UN site sur 19, et fausse pour huit.** Elle présuppose que les deux
faces sont nues. Mesuré : la face COMBAT de huit d'entre elles lit **déjà** la liste stockée.

## 1. Le tri, et son critère — l'ÉTAT DE LA FACE JUMELLE

Toute face COMBAT qui **exécute un arbre DSL** est déjà câblée, et par deux chemins lus :

* les sélecteurs d'unités `AdjacentFriends` / `AdjacentEnemies` / `AdjacentUnits`
  (`entities/selectors/units.py`) passent par `dsl/base._within(order='adjacent')` →
  `_adjacent_tiles_native(board, centers)` → `Board.neighbours_native` ;
* le sélecteur de tuiles `AdjacentTiles` (`entities/selectors/tiles.py`) lit directement
  `board.neighbours_native(tid)`.

Leur jumelle DÉCISION, elle, **recompose le sélecteur à la main** sur les tables de `Scene` — ces
sites l'écrivent eux-mêmes : « `Scene` n'a pas d'`AbilityEntities` pour exécuter l'arbre ». Et elle
le recomposait en couronne hex.

⇒ **La divergence de faces existait déjà, et dans l'autre sens.** Câbler la face nue la **résorbe**,
exactement comme `_fighting_retreat_sets_flags` (#943-r4). Ne pas la câbler, c'était la maintenir.

### Ventilation des 19

| # | site | face | verdict |
|---|---|---|---|
| 1 | `entities/effect_targets.py::_adjacent_friends` | **les DEUX** | **CÂBLÉ** — foyer commun |
| 2-5 | `playbook/scene.py` : `adjacent_taunted_enemies`, `adjacent_dark_angels_friends`, `_enmity_adjacent`, `_camo_cloak_cover_keys` | DÉCISION | **CÂBLÉ** — jumelle DSL déjà stockée |
| 6 | `playbook/prediction/abilities.py::make_hammer_wrath_events` | PRÉDICTION | **CÂBLÉ** — jumelle DSL déjà stockée |
| 7 | `playbook/psyker.py::possible_targets` | DÉCISION | **CÂBLÉ** — jumelle sur `board.neighbours` |
| 8 | `playbook/noncomparable/get_em_runtz.py::_spawn_tile_count` | DÉCISION | **CÂBLÉ** — jumelle tile-selector DSL |
| 9 | `runner/operations/triggers/loki/icon_of_obstinacy.py::icon_of_obstinacy_affected_units` | COMBAT | **NON** — couple non fermable |
| 10 | `runner/abilities/loki/momentum.py::_execute_behaviour_step` | COMBAT | **NON** — substrat DIFFÉRENT |
| 11-19 | 8 ctx d'AURA (`hits.py` ×3, `imperative.py` ×2, `extra_damage_aura.py`, `dark_angels_passives.py`) + `traits/combat.py::as_attacker_bonus_hits` | mixte | **NON** — `BLOCAGE: seeding` |

**Le n°1 n'est pas un couple : c'est le FOYER COMMUN.** `_adjacent_friends` est appelé par ses deux
substrats (`_SceneEffectTargetWorld`, `_RunnerEffectTargetWorld`), donc une seule édition déplace
les deux faces — le câblage y est structurellement incapable de créer une divergence. Le canal entre
par le **protocole** (`EffectTargetWorld.neigh_by_pos()` / `.elev_by_pos()`), jamais par une
dérivation locale : ce module ne connaît ni `Scene.board` ni `State.board`.

`Scene` et `NCContext` **portaient déjà les deux canaux** (`Scene.neigh_by_pos` est une propriété
dérivée du board, mémoïsée) — aucun seeding n'était requis pour les sept autres.

## 2. Les trois qui ne bougent pas, et pourquoi CHACUN

* **`icon_of_obstinacy` — le seul cas où la crainte fondatrice est VÉRIFIÉE.** L'autre expression du
  même `AIconOfObstinacyAbility$$GetAffectedUnits` est
  `effects/loki/icon_of_obstinacy.py::create_aura_attack_damage_bonus_for_ally`, un ctx d'aura (donc
  sous `GEOMETRIE_NUE_TOLEREE`, et bloqué comme les huit). Câbler le runner seul ferait diverger le
  buff d'armure du bonus de dégât, que le natif fait coïncider.
* **`momentum` — substrat DIFFÉRENT, pas un blocage de contexte.**
  `TileExtensions$$IsNeighbourOf` énumère `ConnectivityComponent+0x10` **sans porte d'élévation**.
  `is_adjacent` y serait **faux** (il ajoute la porte), et `neighbours_native` aussi — le champ capté
  **est** `connectivity INTERSECTE {|dElev| < 2}` (identité lue dans `Board.base_add_neighbours`). Le
  canal juste est `Board.neighbours_connectivity`, tri-état et **absent des boards versionnés** :
  non confrontable offline. `BLOCAGE: capteur`.
* **Les neuf ctx d'AURA / de trait** — des dicts que l'agrégateur remplit
  (`effects/__init__.py::aura_*`), sans board ni carte. Les câbler exige de publier les deux cartes
  en amont, dans `damage_model.attacker_modifiers` **et** dans la face PRÉDICTION : un foyer partagé
  bien au-delà de l'adjacence. `BLOCAGE: seeding`.

## 3. Ce que le décompilé a fixé et que la géométrie masquait — la DIRECTION

`GetEmRuntzAbility$$GetSpawnTileSelector`, relu :

```
CanAddUnit( AdjacentTiles(Caster@+0x50) )
&  Unique( AdjacentTiles( UnitsWithoutTrait(Enemies(Caster@+0x48, AllUnits@+0x20, 3), 0x1b, 3) ) )
```

Deux `AdjacentTiles`, donc **les deux** comparaisons du port portent le substrat stocké. Surtout :
`AdjacentTiles(source)` énumère le voisinage de la tuile **SOURCE**, et le champ `neighbours` est le
champ **brut** (ni trié ni symétrisé). Le second terme s'écrit donc `is_adjacent(ennemi, T)` — pas
l'inverse. `hexgeo.distance`, symétrique par construction, **ne pouvait pas** exprimer cet axe : il
ne devient observable qu'après le câblage, et il a son test dédié.

Relevé, **non porté** (ce n'est pas de l'adjacence) : l'étage `UnitsWithoutTrait(…, 0x1b Steppable)`
du second terme et le `selectionType 3` du `Enemies`. Direction permissive.

## 4. Deux défauts trouvés en CRAFTANT — l'un réparé par un TIERS pendant la tranche, l'autre ouvert

Monter le scénario a fait lever un `AttributeError` **à chaque appel** de `Scene._enmity_adjacent` :
il appelait `self.traits(oid)` alors que **`Scene` n'a aucun attribut `traits`** (le seul `def
traits` du fichier appartient à `_SceneEffectTargetWorld`, une autre classe ; la méthode était
**présumée** par #948, dont le commentaire de `_TRAIT_STEPPABLE` affirme « `Scene.traits` publie des
NOMS »). Patron **exact** du troisième défaut d'`admec.py` (#943-r4, `state.units()`) : **bruyant**,
donc invisible aux lectures qui cherchent une dégradation *silencieuse*.

⚠ **Ce défaut-là n'est PAS livré ici — le rebase a montré qu'une autre tranche l'avait réparé
pendant celle-ci.** `origin/master` porte désormais la lecture inline (`c = self.ctx(oid)` puis
`getattr(c, "traits", None)`) et le commentaire qui le nomme (« rouge de `master` introduit par
#947+#948, latent parce que la boucle sort AVANT sur un board où personne n'est au contact »). La
`Scene.traits` que cette tranche avait ajoutée est **retirée au rebase** : sans appelant, elle serait
devenue exactement le mort-né que le §suivant dénonce. Le constat reste vrai, la réparation revient à
l'autre tranche.

⚠ **Le second défaut, lui, TIENT — re-mesuré APRÈS rebase : résidu #943-r8.** Les deux accesseurs
publics `Scene.enmity_adjacent_units` / `..._dark_angels_friends` n'ont **aucun appelant** dans
`engine/` — `unit_state` ne les appelle pas, et les clés `CTX_ADJACENT_UNITS` / `CTX_ADJACENT_DA` ne
sont posées que par `damage_model.py` (face COMBAT). La face DÉCISION d'Enmity ne contribue donc à
rien, alors que la face COMBAT applique le bonus.

## 5. L'effet sur le cliquet — et l'étape 5 a demandé un armement

`probe_433r4r1r4r2_neigh_channel_wired`, avant → après :

```
etape 1 : call-sites gates par l'elevation   108 -> 117   (0 sans voisinage, inchange)
etape 3 : fonctions qui touchent le canal    133 -> 143   (0 derivation morte, inchange)
etape 6 : geometries nues sans canal          27 ->  19
          dont MUETTES                        24 ->  16
          ventilation            GEOMETRIQUE=5, LISTE_STOCKEE=19 -> 11
```

L'**étape 5** est passée au rouge d'elle-même : après le câblage de `make_hammer_wrath_events`, son
**dernier foyer**, armer `AdjacentTiles` ne faisait plus rougir personne — la suspension était
devenue le vice. `AdjacentTiles` **quitte** `NATIFS_LISTE_STOCKEE_SUSPENDUS` et entre dans
`NATIFS_LISTE_STOCKEE`. `AdjacentUnits` y reste, justifiée par un foyer encore ouvert
(`extra_damage_aura.create_aura_attack_bonus`).

`test_433r4r1r4r2r1r1_derivation_morte_offline::test_la_JUSTIFICATION_de_la_tolerance_se_re_mesure`
a rougi lui aussi, **pour la bonne raison** : deux de ses trois témoins nommés venaient d'être
câblés. Les témoins sont **re-choisis parmi les sites BLOQUÉS** (ceux dont on sait qu'ils ne
bougeront pas par inadvertance), jamais retirés.

## 6. Validation

**Offline** — `tests/engine/test_943r7_faces_jumelles_adjacence_offline.py`, 21 tests, 0 skip. Le
board témoin porte deux tuiles à distance hex **1** qui ne sont **pas** voisines dans la liste
stockée : le régime que la mesure live de #943-r4 établit comme réel (22 arêtes sur `MC2_60`, 8 sur
`C4_69`, 0 dans l'autre sens). Chaque site est exercé dans les **deux** régimes (arête coupée /
arête portée), plus le no-op sans canal et les prémisses de montage.

**Contre-épreuve, arbre témoin détaché sur `b6d3749d`** : **11 des 21 échouent**. Les 10 verts sont
exactement ceux qui doivent l'être — 2 prémisses de montage, 5 cas « arête portée » (le verdict ne
change pas), 1 témoin non nul, 2 no-op sans canal. Aucun faux vert.

**Live** — 43 tests verts sur les gardes des sites câblés : `test_911_daemonic_patrons_live.py`,
`test_hammer_of_wrath_corpse_decision_live.py`, `test_psyker_suppression_live.py`,
`test_566_vexilla_magnifica_live.py`. Non-régression, pas confirmation du gisement.

**Cliquets** : le probe lui-même (PASS), `probe_433_r1_identity_shortcircuit` (rc 0 — quatre arêtes
d'import ajoutées vers `engine.battle_query`, qui n'importe que `hexgeo` + `.hex_corner`, donc aucun
cycle), et 163 tests offline des foyers touchés.

### Ce qui n'est PAS couvert

* **Le comportement observable des 8 abilities en bataille.** Il faudrait un board où la liste
  stockée contredit la couronne **sous** les unités concernées, **et** un porteur de chacune — ce
  qu'un spawn de runner ne donne pas par construction. Même verrou que #943-r4.
* **Deux mesures DISJOINTES, qui ne se valident pas l'une l'autre** : offline, 8,9 % des arêtes des
  779 boards versionnés tombent par la seule porte `|dElev| >= 2` ; live, les 22 arêtes de `MC2_60`
  ont toutes `|dElev| ∈ {0,1}` — elles tombent par l'**énumération**. Ce fichier exerce
  l'énumération ; la porte a ses gardes dans `test_943r4_adjacence_cablee_offline.py`.
* **Les 11 sites non câblés**, dont les raisons sont au §2.
* **`probe_486r15` est ROUGE**, sur `test_955_summary_execution_possession_offline.py` — rouge
  **préexistant**, vérifié identique sur l'arbre témoin, autre tranche.

## 7. Résidus ouverts

* **#943-r7** reste ouvert sur les **11** sites non câblés (le résidu change de contenu, pas de
  numéro : 19 → 11).
* **#943-r8** — la face DÉCISION d'`EnmityForTheUnworthy` est **débranchée** (§4).
