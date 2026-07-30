# Carte du vocabulaire DSL : couverture du port, ponderee par le levier (#326)

> **DOCUMENT GENERE** -- `python scripts/python/probe_326_dsl_join.py [--p1 <table #325>]`.
> En cas de conflit au rebase : **on REGENERE, on ne fusionne pas**. Les chiffres se periment a
> chaque build et a chaque port ; les re-deriver plutot que citer cette page.

Chaine de production (trois probes, trois tables machine dans `logs/`) :

| etage | probe | sortie | question |
|---|---|---|---|
| A1 | `probe_326_dsl_primitive_inventory.py` | `logs/326_dsl_primitives_native.tsv` | quelles PRIMITIVES le build expose-t-il ? |
| A2 | `probe_326_dsl_port_matching.py` | `logs/326_dsl_primitive_coverage.tsv` | laquelle est PORTEE, par quel artefact ? |
| B | `probe_326_ability_reachability.py` | `logs/326_ability_reachability.tsv` | quelle ability est CONFRONTABLE, par quel chemin ? |
| C | `probe_326_dsl_join.py` | `logs/326_dsl_primitive_leverage.tsv` | quelle primitive NON PORTEE debloque le plus d'abilities confrontables ? |


Build mesure : `rnca9r7q6c`. Table phase 1 (#325) : **ABSENTE -- la colonne de levier vaut `NON_MESURABLE_P1`**.

## 1. Couverture du port, par famille de primitive

| famille | PORTE | PORTE_ALIAS_FACADE | PORTE_HORS_FACADE | PORTE_ARTEFACT_AUTRE | PORTE_SANS_CITATION | CITE_A_QUALIFIER | NON_PORTE | total |
|---|---|---|---|---|---|---|---|---|
| DSLBehaviors | 46 | 5 | 3 | 0 | 0 | 16 | 57 | 127 |
| DSLFactory | 0 | 0 | 0 | 0 | 0 | 2 | 3 | 5 |
| DSLFormulas | 30 | 1 | 1 | 0 | 3 | 18 | 60 | 113 |
| DSLSelectors | 64 | 3 | 2 | 0 | 0 | 20 | 106 | 195 |
| DSLTriggers | 32 | 1 | 1 | 1 | 0 | 46 | 84 | 165 |
| **TOTAL** | **172** | **10** | **7** | **1** | **3** | **102** | **310** | **605** |

**Porte atteste** (`PORTE` + `PORTE_ALIAS_FACADE` + `PORTE_HORS_FACADE`) = **189 / 605**.
`CITE_A_QUALIFIER` (102) n'est NI porte NI absent : l'artefact apparait dans `engine/**` sans porteur Python identifiable. C'est un etat A TRANCHER, pas un zero.

## 2. Joignabilite des abilities (etage B)

| verdict | abilities |
|---|---:|
| CONFRONTABLE_POOL | 221 |
| SANS_PORTEUR_MESURE | 82 |
| HORS_KIT_UNITE | 82 |
| CONFRONTABLE_INJECTION | 52 |
| NON_PERTINENT_NPC | 50 |
| SUMMON_SANS_SUMMONER_MESURE | 32 |
| CONFRONTABLE_SUMMON | 25 |
| CONFRONTABLE_RELIQUE_A_EQUIPER | 24 |
| CONFRONTABLE_SUMMON_INJECTION | 4 |

La voie RELIQUE a **trois** etats et non deux (`RELIQUE_EQUIPEE_SEED` / `RELIQUE_POOL_A_EQUIPER` / `RELIQUE_HORS_POOL`) : « porteur dans le pool » ne dit pas « arrive en bataille AVEC sa relique ».

## 3. Classement des primitives NON PORTEES par levier

**NON MESURABLE** -- la table `primitive <-> abilities` de la phase 1 (#325) n'a pas
atterri. Le classement n'est PAS estime : un ordre invente sur des xrefs devinees
vaudrait moins que son absence. Relancer avec `--p1 <table>` le produit sans autre
changement (le lecteur accepte TSV/JSON et trois formes de nom de chaque cote ;
cf. `scripts/python/tests/test_326_dsl_join_offline.py`).

## 4. Ce qui n'est PAS mesurable, et pourquoi

* **Levier natif** : le nombre d'abilities qui APPELLENT une primitive vient des xrefs
  du binaire (phase 1 / #325). Ce document ne le re-derive pas.
* **Voies d'attribution non couvertes** (`trait`, `liveevent`, `summon`, `tile`, cf.
  `unit_map.VOIES_NON_COUVERTES`) : toute ability rendue `SANS_PORTEUR_MESURE` les porte
  en colonne. Ce zero ne prouve pas qu'elle est morte.
* **Abilities sans classe native reperee** (0) : le mapping ability <-> classe native lit
  `classes.tsv` (et non `methods.tsv`, ou une classe sans methode nommee manque -- ex.
  `AblativePlatingAbility`). Ce qui reste est un NON MESURE, pas une absence de code.

### L'axe UTILITY / gshared est MESURABLE sur ce checkout -- verifie, pas suppose

La consigne heritee dit que les corps pleinement partages ne sont plus nommes
(`4882 -> 0`, `docs/rl/case-259-couverture-gshared.md`). **Re-derive le 2026-07-31 sur les
tables VERSIONNEES, ce n'est pas l'etat courant** :

| table | `gqfc5mff6c` | `rnca9r7q6c` |
|---|---:|---:|
| `ghidra/functions.tsv`, marqueur `__Il2CppFullySharedGeneric` | 4882 | 4874 |
| `frida/methods.tsv`, meme marqueur | 0 | 0 |

Le `0` cote Frida est STRUCTUREL et vaut pour les deux builds (le `methodPointer` d'une
definition generique est un thunk, pas le corps) : le lire comme l'effondrement decrit
par #259 serait un faux. `probe_259_gshared_coverage.py` re-joue confirme -- famille
`GSHARED` 4882 -> 4874 (ratio 0.998), *familles en chute : 0*, et 100 % des methodes
frida retrouvent leur nom Ghidra sur le build courant (contre 91,1 % a la reference).
Mesurer soi-meme : `python scripts/python/probe_326_dsl_primitive_inventory.py
--compare gqfc5mff6c`.

## 5. Citations PERIMEES du port (symbole absent du build courant)

| primitive citee | citations | premier site |
|---|---:|---|
| `Difference` | 2 | `scripts/python/engine/entities/formulas.py:43` (Difference) |
| `Null` | 1 | `scripts/python/engine/entities/selectors/geometry.py:553` (Null) |

Ces noms ne sont plus dans les classes-factory du build : soit la primitive a
ete RETIREE du jeu, soit elle a ete RENOMMEE. Dans les deux cas la citation ne se
resout plus par grep, et le port qui s'en reclame n'est plus atteste.
