# #464-r1 — un script lancé depuis le mauvais répertoire

Résidu ouvert par #561, qui avait fermé le cas mordant (`probe_457` écrivait une empreinte
vidée dans un fichier versionné) et recensé ses frères sans les corriger. Ce document
**re-dérive** ce recensement, le corrige, et tranche quoi corriger.

## 1. Le critère, et pourquoi il se ventile en trois

Un script de `scripts/python/` lancé d'ailleurs que `scripts/python` peut échouer de trois
façons, et **elles n'ont pas la même gravité** :

| issue | ce qui se passe | gravité |
| --- | --- | --- |
| (a) | il **plante bruyamment** (`can't open file`, `FileNotFoundError`) | bénigne — l'échec se voit |
| (b) | il rend une sortie **fausse** sans rien écrire | moyenne |
| (c) | il **écrit** une sortie fausse dans un fichier **versionné** | c'est #464 |

Le cas qui a payé était (c) : `pytest rc=4`, 630 lignes retirées d'un JSON versionné, et le
dégât réel — une empreinte vidée fait **sauter** des tests au lieu d'en sur-sélectionner —
lu comme un rouge de gisement.

## 2. Le recensement re-dérivé — trois chiffres de #561 corrigés

Balayage AST de `git ls-files scripts/python`. Périmètre mesuré **sur l'arbre rebasé** :
**1 099** fichiers hors `tests/`, **1 693** avec. (Il valait 1 091 / 1 681 au début de ce
travail — trois PR ont été mergées entre-temps. Les chiffres ci-dessous se **re-dérivent**,
ils ne se citent pas.)

### 2.1 L'axe qui a mordu — écriture versionnée : **AUCUN cas ouvert**

Six artefacts versionnés sont générés par un script Python. Audités un par un (sortie
absolue ? entrées résolues depuis le CWD ? survit-il à l'import ?) :

| artefact | producteur | verdict |
| --- | --- | --- |
| `scripts/ratchets-457-footprints.json` | `probe_457` | **corrigé par #561** |
| `scripts/ratchets-462-live-attestations.json` | `probe_462` | sain — `cwd=_PYDIR` sur ses 2 pytest, `git -C` sur ses 10 subprocess |
| `docs/rl/kit-coverage.md` | `audit_kit_coverage.py` | sain — aucune entrée CWD |
| `docs/rl/combat-ability-coverage.md` | `audit_combat_ability_coverage.py` | sain — idem |
| `docs/rl/passive-ability-coverage.md` | `audit_passive_ability_coverage.py` | sain — `cwd=_PYROOT` sur son `rl_duel --list-pool` |
| `docs/rl/unit-trait-coverage.md` | **aucun** | doc maintenue à la main (son en-tête le dit) |

Le discriminant vérifié est `sys.path` : les trois audits font
`sys.path.insert(0, _PYROOT)` dérivé de `__file__`, donc ils **survivraient** à l'import
depuis n'importe quel CWD et iraient jusqu'à l'écriture — c'est précisément ce qui aurait
rendu (c) possible. Ils sont saufs parce que leurs **entrées** ne dépendent pas du CWD :
leur unique source externe est `gameconfig`, ancrée sur `Path.home()`.

L'asymétrie avec `probe_457` est structurelle, pas accidentelle : son jumeau `probe_462` —
même forme, même ledger versionné — passe `cwd=str(_PYDIR)` à ses deux invocations pytest.

> **`probe_457` était donc le seul, et il est fermé.** Le patron (c) n'a aujourd'hui aucun
> autre porteur dans le dépôt.

### 2.2 La banque n'est pas fragile — mesuré, pas supposé

L'hypothèse à écarter était plus grave que l'écriture : un **cliquet** lancé à la main
depuis la racine (geste courant) rendrait-il un faux `PASS` ? Quatre cliquets joués depuis
les deux répertoires :

| cliquet | racine | `scripts/python` |
| --- | --- | --- |
| `probe_181` | rc 0 — 102 abilities | rc 0 — 102 abilities |
| `probe_313` | rc 0 — total 2100 | rc 0 — identique |
| `probe_365` | rc 0 — 871 imports | rc 0 — identique |
| `probe_455` | rc 0 — `VERDICT: PASS` | — |

Verdicts **et dénominateurs** identiques : ils sont tous ancrés sur `__file__`.

### 2.3 L'axe « script frère » — **15** fichiers, pas 13

`subprocess.run([sys.executable, "rl_duel.py", ...])` sans `cwd=` : **22 sites, 15
fichiers**. Les 2 que #561 ne voyait pas passent leur argv par une **variable**
(`cmd = [...]` puis `run(cmd)`), forme que son détecteur ne suivait pas.

Preuve mécanique, depuis la racine :

```
AVANT   python rl_duel.py --help   ->  rc=2  can't open file '<racine>\rl_duel.py'
APRES   chemin ancré               ->  usage: rl_duel.py [-h] ...
```

Gravité réelle : **(a)**, et #561 avait raison sur ce point. Nuance mesurée qui la relève
un peu — **8 des 15 ne lisent pas le `rc`** (`subprocess.run(...)` en instruction seule) :
l'échec se rejoue plus loin en `FileNotFoundError` sur le state-file, **qui accuse le
mauvais coupable**.

### 2.4 Le « 183 » ne comptait pas des fichiers

Mesure : **467** appels de sous-processus passent `cwd=` explicite, répartis dans **414**
fichiers. Ni l'un ni l'autre n'est 183, et `13 + 183 = 196` additionnait des fichiers et
des appels. Le chiffre à retenir est le **ratio de forme** : le patron sûr est massivement
majoritaire, ce qui reste vrai.

## 3. L'arbitrage : ANCRER, et surtout pas `cwd=`

#561 a fait **refuser** `probe_457` (rc 99). Ce n'est **pas** ce qu'il fallait faire ici, et
la raison est précise : la contrainte de `probe_457` est **irréductible** — les chemins
qu'il passe à pytest sont relatifs au *rootdir* que fixe `pytest.ini`, on ne peut pas les
absolutiser sans déplacer le rootdir. Un appel `subprocess` n'a aucune contrainte de ce
genre : `str(_PYDIR / "rl_duel.py")` marche depuis partout.

Refuser **contraindrait** ces probes — on les lance à la main depuis la racine aussi souvent
que depuis `scripts/python`. Ancrer les **répare**. Le foyer est
`scripts/python/sibling_script.py`, appelé aux 22 sites.

### ⚠ Le piège mesuré : la correction « naturelle » aurait cassé les 15

Le réflexe est d'ajouter `cwd=_PYDIR` — c'est ce que font les 467 autres appels. **Ici
c'est une régression.** `rl_duel.py` ancre déjà un `--state-file` **relatif** sur la
**racine du dépôt**, pas sur le CWD :

```python
STATE = sf if sf.is_absolute() else (ROOT / sf)
```

avec pour intention explicite « même chemin nominal = même fichier, quel que soit le cwd de
l'acteur ». Un `cwd=` différent de celui de l'appelant **découple** les deux : `rl_duel`
écrirait le state-file sous `<dépôt>/logs/x.json` pendant que le probe le relirait sous
`<son cwd>/logs/x.json`. Ancrer le seul chemin de **script** laisse les deux côtés partager
le même CWD, donc la même résolution.

Second effet, voulu : `sibling_script()` **lève** si le frère est absent — le rc que 8
appelants ignoraient devient un échec immédiat qui **nomme** le frère.

## 4. Le cliquet — pourquoi corriger ne suffisait pas

22 sites, **un seul littéral**, 15 fichiers : personne n'écrit ce patron deux fois, on le
**copie du voisin**. C'est donc, comme `TARGETING_OPTIONS` et `ABILITY_ATTACK_TYPE`, un
gisement que **notre propre cadence** alimente — le prochain probe live naîtra du
copier-coller d'un de ces 15.

`probe_464_sibling_script_cwd.py` (dans la banque). Périmètre **dérivé**
(`git ls-files scripts/python`), `tests/` **compris** — un test qui invoque un frère a le
même défaut, et pytest fixe le *rootdir*, pas le CWD. Ancré sur `__file__` : un cliquet qui
garde le vice du CWD ne peut pas le porter — vérifié, **même dénominateur** depuis la racine
**comme** depuis `scripts/python` (1 693 fichiers après rebase ; c'est l'**égalité** qui est le
résultat, le nombre bouge à chaque PR).

**Coût** : 87 s en série → **25,2 s** via `repo_read.read_texts` (recette #457-r6 — sur cet
arbre, l'`open()` domine l'`ast.parse`). Il n'est pas le mur de la banque (161 s sous charge,
contre 438 s pour `probe_457:s7`), donc son coût marginal en parallèle est nul.

Contre-épreuves #439, mutation vérifiée **appliquée** avant de conclure :

| mutation | verdict |
| --- | --- |
| forme littérale en place (`probe_106`) | **FAIL rc=1**, site nommé |
| forme argv en **variable** (`probe_114`) | **FAIL rc=1**, site nommé |

La seconde est exactement ce que le détecteur de #561 ratait.

## 5. La convention `rc=99` — sans emploi ici, et le point de `ratchets.ps1` reste dormant

`EX_NON_MESURE = 99` signifie « aucun verdict sur le dépôt ». Elle n'a de sens que pour un
script qui **rend un verdict** et refuse de le rendre. Aucun cas restant n'est dans ce cas :
les 15 corrigés sont des probes de mesure live, et `probe_464` rend 0/1.

Le point signalé par #561 — `ratchets.ps1` compte **tout** rc non nul comme rouge, 99
compris — **n'est donc pas rendu actif** par ce travail. Sur périmètre vide, `probe_464`
rend `1` avec un message explicite, en suivant le précédent de `probe_273` étape 0c
(« le verdict serait rendu contre un référentiel vide, donc faux dans les deux sens »).

## 6. Résidus

### `#464-r1b` — 7 fichiers consomment un chemin de dépôt relatif tel quel, 4 **écrivent**

Famille du vieux pipeline Ghidra offline. Critère : littéral partant d'une racine du dépôt,
passé directement à `open`/`os.walk`/`Path`, sans ancrage et sans `host_inputs`.

| fichier | sortie | |
| --- | --- | --- |
| `gen_ai_targets.py` | `data/ai_targets.json` | **écrit** |
| `gen_battlelogic_targets.py` | `data/all_battlelogic_targets.tsv` | **écrit** |
| `gen_campaign_builder_targets.py` | `data/campaign_builder_targets.tsv` | **écrit** |
| `gen_full_game_targets.py` | `data/all_game_targets.tsv` | **écrit** |
| `check_decompilation_quality.py`, `enrich-sources.py`, `resolve_fun_symbols.py` | — | lisent |

**Risque actuel : nul.** Aucune de leurs entrées (`data/symbols.json`,
`data/il2cpp_full.json`, `data/decompiled_tacticus`) n'existe dans le checkout — ils
plantent en `FileNotFoundError` à la première ouverture, quel que soit le CWD (issue (a)).

**Non corrigés, et c'est un arbitrage, pas un oubli** — les deux corrections possibles
cassent quelque chose de vérifiable :

1. **Déplacer la sortie vers `logs/`** (ce que prescrit l'invariant 3) **casse le contrat
   inter-langage** : les consommateurs Ghidra lisent ces TSV par chemin **absolu en dur** —
   `GhidraDecompileBattleLogicParallel.java:28`,
   `GhidraDecompileCampaignBuilder.java:28`, `GhidraDiagnoseFailedMethods.java:19` — et
   `frida/host/router.ts:50` lit `data/all_game_targets_win.tsv`. Ce ne sont pas des sorties
   de run RL, ce sont des **entrées** du pipeline d'analyse.
2. **Ancrer sur `REPO_ROOT`** en gardant la destination rendrait le chemin **composé**, donc
   visible de `probe_273` étape 0c — qui **rougirait**, à juste titre selon sa propre
   doctrine (« une ÉCRITURE de run n'entre JAMAIS ici »). Les y inscrire via `_ALLOWED_DATA`
   demanderait de trancher si une entrée du pipeline Ghidra est une « sortie de run » — un
   arbitrage de doctrine sur un cliquet **partagé**, que ce cas ne peut pas prendre seul.

Ni l'une ni l'autre n'est validable aujourd'hui (entrées absentes, Ghidra headless éteint).
Le geste juste est donc de **nommer**, pas d'uniformiser.

### `#464-r1c` — l'étape 0c de `probe_273` est aveugle au littéral MONOLITHIQUE

Cause lue dans son code : ses candidats sont les expressions **composées** —
`os.path.join`, `.joinpath`, `BinOp/Div`. Un chemin d'un seul tenant
(`open("data/ai_targets.json", "w")`) n'a ni `join` ni `/` comme **nœud**, donc il n'entre
jamais dans `cands`.

Mesuré : **243** littéraux `data/...` dans **148** fichiers ; 0c en rapporte **215** avec
**8** hors entrée versionnée, tous `[OK]`. Les **4 écrivains** de `#464-r1b` n'y figurent
pas. Le trou est réel et son gisement est exactement ces 4 — fermer l'un ferme l'autre.

⚠ Un premier comptage de ce même trou a rendu **1** site au lieu de 4 : le détecteur ne
suivait pas les constantes de module (`OUT_TSV = 'data/x.tsv'` puis `open(OUT_TSV, 'w')`).
Même angle mort que celui qui a fait écrire « 13 » — **suivre une indirection par variable
n'est pas un raffinement, c'est le minimum** pour ce genre de balayage.
