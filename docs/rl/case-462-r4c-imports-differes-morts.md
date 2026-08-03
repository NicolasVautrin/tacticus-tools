# #462-r4c — la chaîne d'import MORTE de `BUILD_HASH`, et le cliquet qui voit les imports DIFFÉRÉS

**Statut : LIVRÉ (2026-08-03).** 5 sites réparés, cliquet `probe_462r5` dans la banque.
Le résidu `#462-r5` est FERMÉ par la même passe.

---

## 1. Le fait

`test_fabricator_claw_cap_live.py` rendait **0 passed / 10 errors** :

```
failed on setup with ImportError: cannot import name 'BUILD_HASH'
from 'probe_193c_move_playbook_terms'
```

`BUILD_HASH` a été retiré le 2026-08-01 par `8be764fb` (#431) — et c'était un **bon**
changement : un hash de build en dur court-circuite `data/symbols/CURRENT`. Le foyer légitime
est `build_pin`, et `probe_431` garde précisément ce motif. Ce que #431 n'a pas fait, c'est
suivre les **consommateurs** du symbole qu'il retirait.

## 2. Le périmètre réel est de CINQ sites, pas quatre — et le cinquième a une AUTRE cause

Un grep de `BUILD_HASH` rend **quatre** probes (`probe_211`, `probe_212`, `probe_241`,
`probe_242`), tous porteurs de la même garde recopiée. La **résolution** (§4) en rend un
cinquième, qu'aucun grep de `BUILD_HASH` ne pouvait atteindre :

| site | symbole | cause | visible au grep du symptôme ? |
|---|---|---|---|
| `probe_211_cursed_plague_bell.py:46` | `BUILD_HASH` | retiré par #431 | oui |
| `probe_212_spiritual_leader_tile_term.py:37` | `BUILD_HASH` | retiré par #431 | oui |
| `probe_241_decoy_tile_leaves.py:43` | `BUILD_HASH` | retiré par #431 | oui |
| `probe_242_fabricator_claw_cap.py:56` | `BUILD_HASH` | retiré par #431 | oui |
| `probe_230_load_state_turn_state.py:129` | `GHOST_EFFECT` | **RENOMMÉ** `TIME_FLUX_GHOST_EFFECT` par `2742ad35` (#366-r1) | **non** |

C'est le point de méthode de la tranche : **partir du symptôme borne le périmètre au symptôme**.
`GHOST_EFFECT` est mort de la même façon (un nom retiré chez la cible, un import différé chez
l'appelant) mais par un autre commit, sur un autre symbole, dans un autre sous-arbre. Seul un
balayage qui *résout* les imports les met dans le même sac.

`probe_230.case_ghost` lève donc en `ImportError` depuis #366-r1 — plus longtemps que
`BUILD_HASH`, et sans aucun test pour le dire.

## 3. Pourquoi ça a survécu : l'import est DANS UN CORPS DE FONCTION

C'est la seule chose à retenir. La fixture de `test_fabricator_claw_cap_live.py` (L71) fait

```python
from probe_242_fabricator_claw_cap import _drive_cluster, _seed_bc_montage
```

**dans son corps**, et `probe_242` importe `BUILD_HASH` à son niveau module. Donc :

* `pytest --collect-only` sur tout le parc : **417/417 fichiers, rc 0** — SAIN. La collecte
  n'exécute ni fixtures ni corps de test, donc elle n'atteint jamais `probe_242` ;
* `python -c "import <module>"` ne visite pas non plus les corps de fonction ;
* `probe_365` est aveugle **deux fois** : il ne lit que le TypeScript de `frida/`, et son critère
  est « la CIBLE est absente ou gitignorée » — ici la cible EXISTE, seul le NOM a disparu.

C'est exactement ce que §1 de `case-462` avait mesuré et écrit : la collecte prouve que les
imports de **niveau module** résolvent, et rien de plus.

## 4. La réparation

**Les quatre gardes `BUILD_HASH` re-pointent vers le foyer par une DÉCLARATION UNIQUE.** #431
avait déjà migré `probe_193c` : sa fonction `_exiger_build_des_rva` appelle
`build_pin.require_pinned("rnca9r7q6c", ...)`. Les quatre probes l'**importent** au lieu d'en
porter une copie — ils importaient déjà sept helpers privés de ce module, et c'est le **même**
pin, transcrit du **même** hook (`frida/hooks/features/scorer-damage-trace.ts`, `installRvaHooks`).

Recopier `require_pinned("rnca9r7q6c", ...)` dans les quatre aurait rendu le cliquet vert pour
**quatre endroits à migrer** au prochain build — la forme même de la faute que #431 combat.

`probe_230` : `GHOST_EFFECT` → `TIME_FLUX_GHOST_EFFECT` (0x4a2 = 1186, ce que la ligne de sortie
du probe annonçait déjà : « le ghost 1186 »).

## 5. Le cliquet — `probe_462r5_dead_imports.py`

Résolution **statique** des `from X import Y` de première partie, **imports différés compris**.

| étape | ce qu'elle fait |
|---|---|
| 0 | auto-test des détecteurs sur **21** mini-dépôts synthétiques (`--self-test`) |
| 1 | index des modules de 1re partie : tout `.py` **suivi par git** sous `scripts/python` |
| 2 | pour chaque `from X import Y` où `X` est à l'index : `Y` est-il lié par `X` ? |

**Ce qu'il lit chez la cible** (niveau MODULE seulement — un corps de `def`/`class` n'expose
rien) : `def`/`class`, affectations sous n'importe quel `if`/`try`/`for`/`with`/`match`, imports
et alias, `with … as`, cible de `for`, `except … as`, walrus, `global X` assigné depuis une
fonction, et **résolution récursive des `import *`** (avec coupure de cycle).

**Ce qu'il refuse de trancher, et c'est ce qui tient le zéro faux positif :**

* `import X` **nu** ne rend **aucun** signal — un nom absent de l'index peut être stdlib ou tiers,
  et rien dans l'arbre ne permet de trancher. Seul `from X import Y` porte de l'information,
  parce qu'il faut déjà que `X` soit à nous pour qu'on lise `Y` ;
* un module **OPAQUE** est écarté et le DIT (`--verbose`) : `import *` d'une cible hors index,
  `globals()[…] = …`, `__getattr__` de module (PEP 562). **Coût mesuré : UN module sur tout
  l'arbre** (`engine_agreement_stages`, par `globals()`) — l'opacité ne coûte que là où
  quelqu'un importe-de ce module, et les deux autres porteurs de `globals()[` ne sont la cible
  d'aucun `from … import` ;
* un `from X import Y` dont le `try` englobant attrape `ImportError`/`Exception` est **exempté** :
  l'auteur a DÉCLARÉ que l'import peut échouer. Le jumeau négatif est dans l'auto-test — le même
  import placé **dans le handler** n'a plus de filet et compte.

**Périmètre** : `git ls-files`, donc le checkout COURANT et lui seul. C'est ce qui satisfait #434
**sans un seul filtre à écrire** — depuis l'arbre principal git ne descend pas dans
`.claude/worktrees` (autres checkouts, hors index), et depuis un worktree il ne s'auto-exclut
pas. Aucune énumération depuis la racine, donc rien à déclarer à `probe_440`.

**Il peut ROUGIR, et pas seulement en théorie** : joué sur l'arbre AVANT la réparation il rend
**rc=1 et nomme les 5 sites**. La contre-épreuve n'est pas synthétique, c'est le gisement lui-même.
`probe_439` le classe `OK` (`sys.exit(main(sys.argv[1:]))`).

**L'ANCRAGE du périmètre — ce qui l'empêche de verdir à vide.** Un balayage qui rend zéro fichier
rend aussi zéro hit, et se lit « rien à signaler » : c'est le faux vert que #440 a mesuré sur la
correction naïve du filtre de worktrees (0 fichier, `VERDICT: PASS`). Le témoin ne se saisit pas
— **c'est le fichier du cliquet lui-même** : s'il n'est ni suivi par git, ni sous la racine
d'import, ni à l'index, le probe FAIL. Contre-épreuve mesurée (racine d'import mutée à
`scripts/pythonn`) : **0 module à l'index, `FAIL`, rc=1** — au lieu du `PASS` qu'il aurait rendu
sans l'ancrage.

**Le faux positif qu'il faut chercher avant de le croire : la COLLISION de nom de module.** Le
dépôt compte **861** basenames partagés entre `scripts/python/*.py` et un fichier plus profond
(`base`, `context`, `nodes`, `utilities`…), et **362** fichiers insèrent un chemin littéral dans
`sys.path`. Un fichier qui insère un répertoire profond puis fait `from <basename> import X`
résoudrait, chez le cliquet, vers l'homonyme de premier niveau — et rougirait à tort. **Mesuré :
ZÉRO occurrence** (croisement des chemins insérés × modules bare importés × basenames présents des
deux côtés). Le risque est latent, pas actuel — résidu `#462-r4c-r4`.

**Coût** : **35,5 s** de mur isolé pour 1 638 fichiers, **61,1 s** dans la banque à 16 en
parallèle (20e sur 37, très en dessous du mur de **391,7 s** que dominent les shards `probe_457`) — dont ~25 s de lecture+parse (le filtre système
sur les extensions exécutables, cf. `repo_read`). Deux décisions de conception l'ont amené là
depuis **~85 s** : index **PARESSEUX** (quelques centaines de modules sont réellement cible d'un
`from … import`, pas 1 635) et **une seule descente d'AST** par fichier (l'import différé et la
garde `try` se lisent du même parcours ; la collecte des walrus s'élague aux `def`/`class`).

## 6. Validation

Tout ce qui suit est **re-joué APRÈS rebase** sur `origin/master` (28 commits d'écart, conflit
`backlog.md` résolu à la main).

| | avant | après |
|---|---|---|
| `tests/engine/test_fabricator_claw_cap_live.py` | **0 passed / 10 errors** | **10 passed** |
| `tests/engine/test_spiritual_leader_tile_term_live.py` | — | 10 passed |
| `tests/engine/test_steppable_decoy_tile_leaves_live.py` | — | 14 passed |
| `tests/engine/test_tile_term_unit_gated_playbooks_live.py` | — | 30 passed |
| `probe_462r5_dead_imports.py` | rc=1, **5 sites** | rc=0 |
| `probe_462r5 --self-test` | — | 21/21 |
| `probe_439` (banque augmentée) | — | PASS, `probe_462r5` = capable de rougir |
| `probe_440` | — | PASS (0/0/0) |
| **banque complète** `ratchets.ps1 -Since origin/master` | — | **VERTE, 37 cliquets, mur 275,9 s** |
| `probe_462 --run --since origin/master` | — | 0 fichier live touché, rien à attester |

Les **quatre** fichiers de test ci-dessus sont **tous** les consommateurs des probes modifiés
(dérivé par grep sur `scripts/python/tests/**`) — **64 tests, 0 échec**. Ce n'est pas un
échantillon : c'est la clôture.

Les quatre probes `BUILD_HASH` **s'exécutent** : elles franchissent la garde `build_pin`, montent
leur runner et jouent leur boucle de mesure (`probe_211` passe aussi son étape 0 hors ligne —
175 unités, 246 armes, traits KO=0, armes KO=0).

`probe_230 --case ghost` ne se contente pas de ne plus lever : il **va au bout de son verdict**,
et il ACCORDE — `move (1,0) -> (0,0)`, tuiles portant le ghost 1186 = `[21]`, attendu `[21]`,
`VERDICT ghost = BONNE TUILE`, rc=0. Premier accord mesuré de ce probe depuis #366-r1.

**Les DEUX branches de la garde sont mesurées**, pas seulement celle qui passe : sur le build
courant `installed_build() == versioned_build() == rnca9r7q6c` et `_exiger_build_des_rva()`
accepte ; `require_pinned("nb3o9lmt6c", …)` lève bien `BuildPinRefused` (« NON MESURE : valeurs
epinglees sur un AUTRE build »). Une garde qui n'a été vue que du côté qui passe n'est pas une
garde — c'est le vice que #431 a nommé sur ce même `probe_193c` (un refus FAUX, indistinguable
d'un refus légitime).

**Ce qui n'est PAS couvert** (et le canal qui l'établirait) :

* un attribut mort atteint par `mod.NOM` après `import mod` — autre gisement, même famille ;
  le canal serait une extension du même AST, à la charge d'une passe dédiée ;
* un nom qui existe mais dont la **valeur** a changé de sens (un renommage *silencieux* dans
  l'autre sens) — hors de portée d'une résolution par nom ;
* le rot d'un fichier live que personne ne touche (trou B, `#462-r1`) : ce cliquet garde les
  IMPORTS, pas les verdicts.

## 7. Résidus

* ~~**`#462-r4c-r1`**~~ — **FERMÉ le 2026-08-03**, voir
  `case-462-r4c-r1-probes-qui-ne-discriminent-plus.md`. Le diagnostic « montage subi » était juste,
  mais il n'était **qu'un des trois vices** : la MESURE elle-même était fausse (retranchement de
  `X_port` sur les littéraux `8`/`9`, périmés depuis #254 — `probe_241` rendait 3 désaccords qui
  valaient exactement `−TileEffects`), et `probe_212` **rendait `0` inconditionnellement**, ce qui
  masquait le sien. Corrigés par un foyer unique (`x_port`), un verdict à deux volets, et
  `walk_driven` / `_drive_carrier_toward` qui PILOTENT les positions.
* **`#462-r4c-r2`** — `probe_230.case_ghost` re-mesure et ACCORDE (§6), mais **seulement sur la
  face `TimeFlux`**. La 2e instanciation qui a causé le renommage — `EchoesFromTheWarp_Revive`
  (0x504 = 1284, `ECHOES_GHOST_EFFECT`) — n'a **aucun** équivalent dans ce probe : il n'existe
  toujours qu'un seul `case`, monté sur `thousTerminator`. Canal : un `--case ghost-echoes` sur
  un porteur de `EchoesFromTheWarp` (1219), même décomposition.
* **`#462-r4c-r4`** — **Risque LATENT de faux positif par collision de nom de module** : un
  fichier qui insère un répertoire profond dans `sys.path` puis importe un bare name homonyme
  d'un `scripts/python/*.py` serait résolu vers le mauvais fichier. **861** basenames en
  collision, **362** fichiers qui insèrent un chemin littéral, **0** occurrence du croisement
  aujourd'hui. Canal si ça survient : ne résoudre un bare name que si les racines `sys.path`
  déclarées par le fichier ne l'exposent pas ailleurs — écarter (`--verbose`) au lieu de rougir.
* **`#462-r4c-r3`** — Le cliquet ne balaie **que le Python**. Le pendant TypeScript existe
  (`probe_365`) mais son critère est la CIBLE (absente/gitignorée/vide), jamais le **NOM** :
  un `import { X } from "./y.js"` où `y.ts` n'exporte plus `X` n'est gardé par rien côté
  `frida/`. Canal : `frida-compile` le voit (`TS-2305`), mais rien ne le joue en cliquet.
