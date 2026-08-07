# #486-r19 — un DÉCLENCHEUR par ENTRÉE DE BANQUE, et la première faute qu'il rend visible

**Verdict : la déclaration peut désormais s'affiner par entrée (`DECLENCHEUR_PAR_ENTREE`), les
six étapes de `probe_283` la portent, et l'étage 2 a NOMMÉ dès son premier passage une lecture
hors périmètre que l'union rendait structurellement invisible.**

## 1. L'asymétrie, et pourquoi elle désarmait le cliquet

`scripts/declencheurs-empreinte.tsv` est **keyé par entrée de banque** depuis le premier jour ;
la déclaration, elle, ne pouvait porter que sur le **fichier**. L'étage 2 de `probe_486r12`
confrontait donc une mesure FINE à une déclaration GROSSIÈRE.

**14 des 25 entrées du groupe C** sont dans ce cas : `probe_283` en porte 6 (`--step
diff|mirror|exec|tables|prose|on`), `probe_457` en porte 8 (shards). Ventilation mesurée
(#486-r14, coûts isolés du 2026-08-07) :

| entrée | coût | ce qu'elle lit |
|---|---|---|
| `283:diff` | 1,1 s | **uniquement** `data/symbols/<build>/frida/enums.tsv` |
| `283:mirror` | 32,6 s | tout `.py` du dépôt |
| `283:tables` | 12,3 s | tout `.py` / `.ts` / `.js` du dépôt |
| `283:exec` | 80,0 s | `scripts/python/**/*.py` seulement |
| `283:prose` | 66,1 s | `scripts/python/**` en `.py`/`.md`/`.ts`/`.js` |
| `283:on` | 15,7 s | `scripts/python/**` en `.py`/`.md` |

Deux effets, et **le premier est le grave** :

* **la confrontation est désarmée** — `probe_283:diff` était jugé contre l'union des six, qui
  couvre tout `.py`/`.ts`/`.js`. Il ne pouvait pas rougir, et surtout il ne DISAIT rien ;
* la déclaration est **inexploitable** par une future sélection : un `.ts` de `frida/`
  rejouerait `exec` + `prose` + `on` (**161,8 s**) qui ne le lisent pas.

⚠ **Ne PAS le simuler en scindant `probe_283` en six fichiers** : ses six étapes partagent
`_fichiers_du_depot` et `_sources`, et c'est la mémoïsation de ces deux-là (lecture parallèle
#457-r6 payée UNE fois par process) qui tient leur coût.

## 2. Le contrat (foyer unique : `scripts/python/declencheur_cliquet.py`)

```python
DECLENCHEUR_PAR_ENTREE = {
    "probe_283:diff": {"chemins": (...), "build": True, "toujours": False, "raison": "..."},
}
```

* **facultatif** — un cliquet à une seule entrée n'a rien à affiner ;
* le `DECLENCHEUR` de **fichier reste obligatoire** : il est l'UNION et le **repli** de toute
  entrée non affinée. Sans lui, une entrée neuve serait indéclarée en silence ;
* **pas d'héritage partiel** : les quatre clés sont exigées de chaque entrée. Une clé héritée
  serait un défaut IMPLICITE, donc invisible ;
* une clé qui ne désigne **aucune entrée de banque de ce script** est une **déclaration MORTE**
  ⇒ ROUGE. Même règle que la direction morte de `Rougit` (#426) : sans elle, une entrée renommée
  laisserait derrière un périmètre fin que plus rien ne résout, et l'entrée retomberait en
  silence sur l'union.

Lecture par **AST**, comme `DECLENCHEUR` : importer un cliquet pour lire sa déclaration serait
absurde (un cliquet dont l'import PLANTE est exactement l'état où l'on veut le savoir).

`hors_de_l_union` reste **INFORMATIF**, pour la même raison que `redondants` : `_couvre_glob`
teste par substitution, donc il est conservateur, et un rouge fondé dessus serait fragile.

## 3. La prise, dès le premier passage

`probe_283:diff` a d'abord été déclaré `"chemins": ()` + `build: True`, sur la lecture du code
de `step_diff` — qui n'ouvre effectivement **aucun** fichier de code. L'étage 2 a répondu :

```
ROUGE -- 1 cliquet(s) LISENT hors de leur perimetre DECLARE :
    probe_283:diff (probe_283_enum_ordinal_sweep.py)
        declare : data/symbols/**, scripts/python/probe_283_enum_ordinal_sweep.py
        LU hors perimetre : scripts/python/symbols_layout.py   (groupe de 3 fichier(s))
```

La faute n'est pas dans `step_diff` : c'est le **chargement du module** qui importe `repo_read`
et `symbols_layout` (`_ARCHIVES = tuple(archived_builds())` s'évalue à l'import). Le périmètre
d'une ENTRÉE inclut donc toujours la fermeture d'imports du fichier, si étroite que soit
l'étape. **Sous l'union, cette faute était structurellement invisible** — `**/*.py` couvre tout.

C'est la démonstration que la finesse n'est pas cosmétique : elle rend jugeable ce qui ne
l'était pas.

Empreinte re-mesurée (`--mesurer --only probe_283`) : `diff` **0,5 s / 6 lectures**,
`tables` 9,6 s, `on` 15,5 s, `mirror` 25,2 s, `prose` 59,3 s, `exec` 67,7 s.

## 4. Cliquet

`tests/test_486r19_declencheur_par_entree_offline.py` — 8 étages (12,5 s), dont :

* le détecteur de **clé morte** mord, et la même clé valide ne dit rien ;
* **chaque étape ÉCARTE quelque chose que l'union accepte** — sans cette assertion, six
  déclarations identiques à l'union passeraient pour un affinage. Les témoins sont choisis dans
  la ventilation mesurée (`diff` refuse un `.py`, `mirror` refuse un `.ts`, `exec`/`prose`/`on`
  refusent `frida/host/router.ts`), et chaque témoin est d'abord vérifié **couvert par l'union**,
  sans quoi il ne prouverait rien ;
* l'étage 1 du probe sur la **vraie banque**, avec le compte d'entrées affinées assertionné
  **non nul**.

⚠ **Le fichier de test a lui-même été pris en TROP ÉTROIT par `probe_486r15`**, et pas sur son
propre code : `scripts/python/tests/conftest.py` et `scripts/python/engine/runner/snapshot.py`.
C'est la **cascade des conftest** — tout fichier posé sous `tests/` la traîne, qu'il la touche
ou non. C'est exactement le résidu **#531** que `d57293b9` vient de nommer sur
`test_524r1_bond_sous_effets_offline.py` (« une déclaration HONNÊTE punie par la cascade des
conftest »), en plus court ici parce que ce fichier n'est pas sous `tests/engine/`. Elle est
déclarée explicitement plutôt que noyée dans un `scripts/python/*.py`.

## 5. Ce qui reste ouvert

* **`probe_457` (8 shards) n'est pas affiné** — l'autre moitié des 14 entrées. Ses shards
  dérivent d'un md5 du chemin, donc leur périmètre n'est pas descriptible par un glob statique :
  c'est un cas de forme différente, pas une simple recopie. Résidu **#486-r25**.
* **La SÉLECTION n'est toujours pas câblée** dans `scripts/ratchets.ps1` (« les déclarations se
  posent d'abord ») : le gain de temps décrit au §1 n'est pas encore réalisé. Cette tranche rend
  la déclaration EXPLOITABLE, elle ne l'exploite pas.
* **22 entrées de banque restent NON MESURÉES** dans l'empreinte (20 absentes, 2 périmées),
  état largement préexistant — `probe_486r12` rend `99` de ce fait. La mesure ne porte ici que
  sur `probe_283` (6) et `probe_120`.
* **#486-r24** (le déclencheur trop large est béni) : cette forme lui donne un levier direct.
  Les 43/52 déclarations qui portent un glob couvrant tout le Python le font en partie **parce
  qu'elles doivent couvrir l'union de leurs entrées** ; l'affinage retire cette excuse pour les
  14 entrées du groupe C. Il ne la retire pas pour les autres : la cause y est ailleurs
  (asymétrie du critère), et c'est bien ce que #486-r24 décrit.

## 6. Reproduire

```
python scripts/python/probe_486r12_declencheurs.py
python -m pytest scripts/python/tests/test_486r19_declencheur_par_entree_offline.py -q
```
