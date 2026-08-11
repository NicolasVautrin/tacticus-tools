# #933 — Les prémisses de RÉGIME périmées par la bascule « items Best-In-Slot »

**Le fait.** Depuis `#419-r5`/`#419-r6`, `_normalize_and_extract_pool` équipe les items
Best-In-Slot **par défaut**. Aucune ligne de moteur n'a bougé, et pourtant tout test écrit
**avant** cette bascule qui présuppose un porteur **à zéro** est devenu rouge — ou, pire,
**trompeur-mais-vert**. Cinq victimes avaient été trouvées au 2026-08-11, dont **trois par
hasard**, en jouant une régression sans rapport ; une (`test_lion_helm_block_aura_live`) était
restée **rouge sur `master`** cinq jours, en accusant `SurroundingFriends`.

Cette tranche traite le gisement, pas les cinq cas.

---

## 1. Quelles stats, et l'asymétrie qui fait tout le tri

Mesure re-dérivée (`probe_933_premisses_regime.py --stats`, seed BC, rank 17, 106 unités) —
diff des templates entre `equip_items=False` et `equip_items=True` :

| champ | bouge | **0 → x** | x → 0 |
|---|---|---|---|
| `CritDamage` | 98 | **98** | 0 |
| `CritChance` | 98 | **98** | 0 |
| `BlockChance` | 46 | **46** | 0 |
| `BlockDamage` | 46 | **46** | 0 |
| `FixedArmor` | 49 | 0 | 0 |
| `Health` / `RemainingHealth` | 4 | 0 | 0 |

**La colonne qui compte est `0 → x`, pas `bouge`.** Une stat dont aucune unité ne passe de 0 à
non-0 ne peut pas périmer une prémisse `== 0`, et un `> 0` écrit sur elle était **déjà vrai**
avant la bascule. `FixedArmor` bouge sur 49 unités mais reste hors de ce canal : il relève du
canal (C) « valeur en dur » de `#419-r6`, déjà balayé. Les **quatre stats à zéro ouvert**
(crit/block), elles, périment **les deux formes d'un coup**.

## 2. Les trois formes du vice — et deux ne se voient dans aucun `rc`

* **(Z) PRÉMISSE-ZÉRO** — `assert stat == 0`, `== (0, 0)`. Devient **ROUGE**. Se voit.
* **(P) ATTENDU-POSITIF** — `assert stat > 0`. Reste **VERT** et cesse de mesurer : avec une
  base non nulle, il passe *même si le mécanisme testé est mort*. C'est le cas des deux
  `seed[...] > 0` de `test_lion_helm_block_aura_live`, dont le voisin `== (0, 0)` était rouge.
* **(G) GARDE / SKIP** — `if cc == 0: assert …` ou `if cc != 0: pytest.skip(…)`. La forme la
  plus dangereuse des trois : l'assertion **la plus forte** du fichier n'est plus jamais
  évaluée, `rc = 0`, et le fichier n'est **pas** intégralement skippé — donc **la garde #455 ne
  le voit pas non plus**. Deux fichiers rendaient `1 passed / 2 skipped`.

Le remède est le **même pour les trois** : rendre la base nulle **au montage**, ce qui refait de
la stat TOTALE la **CONTRIBUTION** — la seule grandeur que ces tests visent.
`--unit-stat <u>:<Stat>=0`, ou les **DEUX faces** de `--crit`/`--crit-target` (resp.
`--block-player`/`--block-target`). ⚠ **Jamais `TACTICUS_BIS_ITEMS=0`** : il déshabille tout le
roster et restitue le régime **dégénéré** que #419-r6 a supprimé (#914 §3.3). C'est
l'instrument de **diagnostic**, pas le remède.

## 3. Le recenseur, et ses TROIS faux négatifs — tous trouvés en le confrontant à la victime connue

`probe_933_premisses_regime.py --recenser`. Chacun de ces trois défauts rendait un compte
rassurant :

1. **Le lien nom ↔ valeur ne se fait PAS dans l'expression.** La première écriture exigeait que
   l'expression comparée NOMME la stat — elle ratait donc son propre cas d'entrée,
   `assert seed[az] == (0, 0)`, où le mot « block » n'apparaît que dans le nom de la *fonction*
   qui a produit `seed`. Le rattachement se fait au niveau du **FICHIER** ; le fait que
   l'expression nomme la stat n'est plus qu'un attribut de tri. **1 suspect → 60.**
2. **Le classement LIVE par marqueurs de harnais rate la moitié de la population.** Les
   marqueurs de #419-r6 (`build_runner`, `live_session`, `rl_duel build`) n'apparaissent pas
   chez les fichiers qui prennent leur fixture dans un module partagé (`_pierce_floor_regime`,
   `_summon_montage`) : `test_448r2dr2_titanhammer_active_live.py`, dont l'en-tête **déclare**
   pourtant « `BlockChance = 0` sur un terminator », était classé OFFLINE. Le suffixe `_live.py`
   est la convention du dépôt et la rend fiable. **437 → 567 fichiers live.**
3. **La prémisse écrite en PROSE n'est dans aucune comparaison.** #914 §4.1 l'avait nommée sans
   l'outiller (« une prémisse en commentaire n'est PAS exécutable ») : un recenseur qui ne lit
   que les `assert` ne peut par construction pas la voir. Un canal TEXTE la cherche
   (« sans crit », « aucune source de block », `BlockChance = 0`…). **+82 positions.**

**Ce que ce balayage NE couvre PAS**, imprimé à chaque exécution :
une stat lue **sans que son nom soit écrit** (helper opaque, index numérique, `*u`) — le
rapprochement reste une heuristique de NOM ; les **probes** `scripts/python/probe_*.py` ; la
face **DÉCISION hors tests** (`engine_validate.py`, `predict_sweep.py`), qui monte pourtant des
runners ; les mots courts (`cc`, `bd`, `hp`) en **identifiant nu**, écartés parce qu'ambigus
(`hexgeo.distance(cc, tc)`, `bc` = BattleConfiguration) et **comptés** comme écartés.

## 4. Le cliquet — `tests/engine/test_933_premisse_regime_offline.py`

Cinq étages, tous offline (donc joués par la banque `probe_457` à chaque PR) :

* le jeu de stats **assertionne son propre non-vide** (un recenseur muet passerait sinon pour
  vert) ;
* **anti-tautologie à DEUX bras** : sur un arbre témoin, le recenseur DOIT voir le patron exact
  de la victime connue, et NE DOIT PAS voir la même source une fois neutralisée — sans le second
  bras, un recenseur qui rendrait « suspect » pour tout passerait ;
* la liste attestée **ne pourrit pas** (chaque chemin existe) ;
* **LE CLIQUET** : aucun **NOUVEAU** fichier à prémisse de régime non déclarée ; le message
  nomme le remède et interdit explicitement `TACTICUS_BIS_ITEMS=0` ;
* les fichiers **réparés** ont **quitté** la liste — c'est ce qui transforme l'allowlist en
  cliquet : perdre leur montage les fait revenir dans `nouveaux`, donc **rougir**.

Le bloc `_ATTESTES` se **régénère** (`--attester`), il ne se tient pas à la main.

## 5. Ce qui reste ouvert

* Les deux rouges rencontrés en balayant — `test_harlequins_panoply_live` (2 failed) et
  `test_heroic_fusillade_migration_live` (1 failed) — sont **PRÉEXISTANTS** : ils tombent **à
  l'identique** sous `TACTICUS_BIS_ITEMS=0`. Ce n'est pas la bascule ; ils sont hors de cette
  tranche et rendus tels quels (résidu `#933-r1`).
* La face **DÉCISION** hors tests et les **probes** ne sont pas balayés (portée imprimée).
