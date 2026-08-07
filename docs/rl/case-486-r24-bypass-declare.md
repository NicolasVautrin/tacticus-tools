# #486-r24 / #531 — le bypass DÉCLARÉ, et la cascade de harnais dérivée

**Mesures du 2026-08-07, base `origin/master` `22fdb030`.** Tous les comptes de cette fiche se
re-dérivent (`probe_486r15_declencheurs_tests.py`) ; ils bougent à chaque tranche livrée.

## 1. Le constat, et pourquoi ce n'était pas de la négligence

`probe_486r15` rougissait sur le **TROP ÉTROIT** et bénissait le **TROP LARGE**. L'auteur
rationnel écrivait donc un glob couvrant tout le Python : vert pour toujours, aucune maintenance.
Une déclaration fine, elle, rougit au premier import ajouté — souvent **par quelqu'un d'autre**,
dans un `conftest.py` partagé.

Mesuré : sur **63** déclarations bien formées (766 fichiers de test versionnés), **54** portaient
au moins un glob **INDISCRIMINANT** — un glob à joker qui couvre un fichier de test ou un probe
**tiers**, alors qu'aucun test ne dépend d'un consommateur du socle qu'il n'importe pas. **0**
déclarait honnêtement `toujours: True`.

⚠ **Le bypass existait donc déjà — il était juste invisible.** Un glob universel rend la
confrontation toujours satisfaite : c'est exactement l'effet de la clé. Ce qu'il coûte en plus :

- il **ment au sélecteur**. `probe_457.impacted_files` sert les globs déclarés, donc un fichier
  portant `scripts/python/**/*.py` est retenu par **toute** PR Python — 25 des fichiers concernés
  sont des tests **live** ;
- il n'est **pas comptable** — personne ne peut dire combien de fichiers se sont dérobés ;
- il ne dit **pas pourquoi**.

## 2. La ventilation — deux causes distinctes, deux réponses distinctes

Mesure : on retire les globs indiscriminants, on dérive la cascade de harnais, on recompte les
découverts.

| population | n | découverts après | réponse |
|---|---:|---|---|
| **CASCADE** | 29 | **0** | le foyer dérive la cascade — pas de bypass |
| **DÉCORATIF** | 2 | 0 | le glob ne couvrait rien de plus — le retirer |
| **À RESSERRER** | 19 | 1 à 12, **nommables** | une ou deux lignes (souvent le probe frère du test) |
| **BALAYAGE** | 4 | 40 à 67, structurels | `hors_confrontation` — les **seuls** candidats |
| déjà serrés | 9 | 0 | — |

**4 sur 63.** C'est pourquoi le cliquet **refuse un bypass qui ne masque rien** : sans ce cran,
les 29 de la cascade et les 2 décoratifs auraient posé la clé par imitation, et l'échappatoire
aurait simplement changé de nom. Le gisement se propage par imitation, c'est mesuré ailleurs
(32 des 52 imports différés gratuits vivaient dans un module portant déjà un différé légitime).

## 3. Ce que le foyer dérive maintenant (ajout 3, #531)

`declencheur_cliquet.chemins_du_harnais` rend les `conftest.py` applicables **et leur fermeture
d'imports** : **435** chemins pour `tests/`, **446** pour `tests/engine/`, **472** pour
`tests/engine/runner/`. Le déclarant ne les écrit plus.

- **Ce n'est pas un assouplissement** : le périmètre effectif est le **même** qu'avec les lignes
  recopiées, en plus fidèle. Seul l'auteur change — le foyer, une fois, par dérivation.
- **C'est un prérequis de la sélection.** `impacted_files` a deux moitiés, et la **DÉCLARÉE
  court-circuite la MESURÉE** : un fichier qui déclare ne passe **jamais** par le graphe
  d'imports. Resserrer sans dériver la cascade aurait fabriqué le faux vert exact que #486
  combat — un changement dans la fermeture du conftest ne rejouerait plus les tests concernés.
- **Témoin** : trois déclarations portaient, mot pour mot, un bloc « SOCLE COMMUN à TOUT fichier
  de test » — douze chemins recopiés, avec le commentaire expliquant qu'aucun test ne les
  importe. La dérivation rend **exactement ces douze**, et davantage. Le travail était juste, il
  était fait au mauvais endroit.

## 4. Deux corrections de fidélité trouvées en chemin

`Fermeture` ne résolvait **pas** les imports relatifs (`ast.ImportFrom` avec `level >= 1`).

1. **Elle sous-approximait.** `engine/runner/snapshot.py`, que le conftest de `tests/` importe,
   n'écrit que des imports relatifs (`from .state import State`). Le nom rendu était `state`,
   cherché à `scripts/python/state.py` — introuvable. La cascade de `tests/` valait **12**
   chemins au lieu de 435. Une sous-approximation dans un garde de couverture est un faux vert.
2. **Elle fabriquait des cibles FAUSSES.** `from .board import` résolvait
   `scripts/python/board.py`, qu'**aucun** module du dépôt n'importe (0 sur 4 189 fichiers
   versionnés). C'est précisément ce faux positif que la fiche #531 citait comme preuve que « le
   harnais live tire `board` ».

`Fermeture` déménage de `probe_486r15` vers `declencheur_cliquet` : le **périmètre effectif** en
dépend désormais, et il est servi au cliquet **comme** à la sélection de `probe_457`. En garder
deux copies rouvrirait l'écart silencieux que #463-r1 a fermé sur le recensement offline.

## 5. La forme de la clé

```python
DECLENCHEUR = {
    "chemins": (...), "build": False, "toujours": False, "raison": "...",
    "hors_confrontation": "<pourquoi la fermeture d'imports ne borne PAS ce fichier>",
}
```

- **Explicite** — se lit sans jouer le cliquet.
- **Motivée** — la clé **EST** sa raison (chaîne ASCII, `>= RAISON_MIN`). Il n'existe **aucune
  valeur « vraie »** à copier-coller : c'est ce qui distingue « ce test dépend vraiment de tout »
  d'un « j'ai pas eu le temps ». Un `bypass: True` n'aurait pas cette propriété.
- **Comptable** — le cliquet imprime la population, le motif, **et le nombre de chemins masqués**.
  Ce chiffre est ce qui rend la relecture décidable : un bypass qui masque **un** chemin nommable
  n'est pas de la même nature qu'un bypass qui en masque soixante.
- **Sous cliquet** — trois crans :
  1. un bypass qui ne masque **rien** est un ROUGE (déclaration morte, même règle que la clé
     morte de `valider_par_entree`) ;
  2. la population est **attestée** dans `scripts/ratchets-486r24-bypass-confrontation.txt` : un
     bypass non inscrit est un ROUGE, donc toute croissance passe par un diff ;
  3. `hors_confrontation` avec `toujours: True` est **sans objet** (un `toujours` n'est déjà
     jamais confronté) — refusé à la forme.

⚠ **L'attestation n'est pas une dette à résorber**, et c'est la différence assumée avec
`ratchets-486r15-dette-declencheurs.txt`. Un bypass peut être pleinement légitime : un test qui
balaie l'arbre dépend réellement de tout. Ce qui est gardé, ce n'est pas le zéro — c'est qu'on
sache toujours **qui** se dérobe et **sur quel motif**.

## 6. Ce que ça laisse passer — et la mesure qui le borne

Un fichier bypassant peut déclarer un périmètre **faux** sans que rien ne le dise, et `probe_457`
servira ce périmètre faux : le test ne sera pas rejoué quand son gisement se rouvre.

**Ce que le cliquet a réellement attrapé depuis qu'il existe** — 5 commits `fix(#486-r15)`,
**tous le 2026-08-07**, 9 fichiers :

| commit | fichiers | nature |
|---|---|---|
| `30744f10` | `test_511_…_live`, `test_514_allunits_pool8_offline` | 1 ABSENTE, 1 tronquée |
| `984b5b6e` | `test_519_comptes_derives_offline`, `test_520_heal_pipeline_offline` | 1 ABSENTE, 1 trop étroite |
| `36eb3690` | `test_287r11r2_mv71_gate_offline` | trop étroite — `frida/hooks/data/ability-names.ts` |
| `37387f68` | `test_287r12_role_target_tuile_offline` | trop étroite — même table + `data/seed-bc.json` |
| `4339665f` | `test_457_r5`, `test_463r1`, `test_486r15_empreinte` | trop étroites — `ledger_vert_offline.py` |

Ventilation : **3 ABSENTES** (étage 1, que le bypass ne touche pas) et **6 TROP ÉTROITES**.

⇒ **0 des 9 prises n'aurait été masquée par le bypass tel que livré.** Les deux fichiers de la
population BALAYAGE qui apparaissent dans cette liste (`test_514`, `test_519`) ont été pris sur
une déclaration **ABSENTE**, pas sur la confrontation.

⚠ **Deux des six prises portent sur des chemins HORS `scripts/python/`** (`ability-names.ts`,
`data/seed-bc.json`). C'est le seul régime où la confrontation mord **malgré** un glob universel :
`scripts/python/**` ne couvre rien de ce que le paquet va chercher ailleurs dans le dépôt. Le
mécanisme punissait donc les honnêtes **et** les tricheurs, mais seulement sur cet axe-là.

## 7. Exemplaires posés — 5 fichiers, pas 43

Réécrire les 43 en masse produirait un conflit avec chaque PR en vol pour un gain nul : elles sont
inoffensives une fois le harnais dérivé.

- **BALAYAGE / bypass** : `test_464_sibling_script_offline.py`,
  `test_457_r8_selection_par_diff_offline.py`, et
  `test_486r24_bypass_confrontation_offline.py` — le garde appliqué à lui-même (il relit les
  767 fichiers de test pour confronter l'attestation au dépôt : c'est un balayage, le nier en
  énumérant `scripts/python/tests/**` réécrirait le glob universel sous un autre nom).
- **CASCADE** : `test_524r1_bond_sous_effets_offline.py` (les 16 chemins recopiés retirés — c'est
  le fichier qui avait rendu `master` rouge pour avoir déclaré honnêtement) et
  `test_505_bloody_fury_offline.py` (`scripts/python/*.py` retiré : il couvrait les ~830 probes
  de la racine, dont aucun ne peut changer son verdict).

## 8. Ce qui reste ouvert

- **#486-r26** — les **48** déclarations restantes (29 cascade + 19 à resserrer). Au fil de l'eau,
  jamais en masse.
- **#531-r1** — le **plancher** : la sélection d'un test déclarant est bornée par la cascade des
  `conftest.py`, soit **435 à 472** chemins qu'il ne choisit pas. Alléger le conftest est le seul
  levier ; aucune déclaration ne peut descendre sous ce plancher.
- **#486-r25** — les 8 shards de `probe_457` ne sont toujours pas affinés par entrée. Non traité
  ici : `probe_457` déclare déjà `toujours: True` au niveau fichier, donc un affinage ne pourrait
  que **restreindre**, et un shard se dérive d'un `md5` du chemin — un sous-ensemble calculé,
  qu'aucun glob statique n'exprime. La clé livrée ici ne l'adresse pas.
