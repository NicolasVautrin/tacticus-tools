# #330-r3 / -r4 / -r5 — la forme du hash de build se DÉRIVE, et l'estampille d'un généré est confrontée

**2026-08-15.** Build qui fait foi : `t6dpr4k06g`. Tranche 100 % offline (jeu non lancé ;
`ghidra-mcp` chargé sur le build courant, analyse complète).

Trois résidus d'un même inventaire (`case-10012` §3) : deux recenseurs Python aveugles au build
courant, huit artefacts dont l'estampille n'était gardée par rien, et trois `.tsv` où l'estampille
est le **seul** signal disponible.

---

## 1. `#330-r3` — le suffixe `6c` en dur, dans les DEUX foyers Python

### La prémisse, re-vérifiée

`probe_330:77` et `probe_431:78` portaient le même littéral
`r"(?<![a-z0-9])([a-z0-9]{8}6c)(?![a-z0-9])"`. Une **troisième** copie vivait dans
`probe_330.DECLARES_RE` (ligne 81), que la fiche ne nommait pas.

Mesure, dépôt entier (fichiers suivis, hors `data/symbols/`) :

| | mesure |
|---|---|
| occurrences **vues** par l'ancienne forme | 2 905 (10 jetons distincts) |
| jetons réels | **7 builds** + 4 mutants synthétiques de `test_431_build_pin_offline.py` |
| occurrences du build **courant**, invisibles | 176 dans 67 fichiers |
| … dans le seau **exécutable** (périmètre du cliquet `probe_431`) | **68**, dont **une RESOLUTION d'artefact** |

Cette résolution est `probe_433r4r2r1r2r2r1r1r1r3_anneau_at_range.py:169`
(`BUILD_DE_LECTURE = "t6dpr4k06g"`) : un littéral que le cliquet des littéraux de build ne
pouvait pas voir, **parce que son motif était périmé**.

### Ce qui a été essayé et REJETÉ : la forme générique seule

Élargir en `[a-z0-9]{10}` mixte (au moins un chiffre et une lettre) est le remède qui vient à
l'esprit. Il est **inutilisable**, et c'est mesuré :

| périmètre | jetons de la forme générique | builds réels |
|---|---|---|
| seau exécutable | **128** distincts | 4 |
| prose `docs` + `.claude` | **70** distincts | 4 |

Le bruit est structurel : `0x7fffffff` (33 jetons, 422 occurrences — un littéral hexadécimal fait
exactement dix caractères), `undefined8`, `cibles1444`, `c4battle75`, `probe366r1`, `287r11r2r1`,
`ctionsu003` (fragment d'échappement `u003C`). Substituée telle quelle dans `probe_431`, elle fait
passer le cliquet de **3 à 27 RESOLUTIONs, dont 24 de bruit pur** — un cliquet qui rougit à tort se
fait désarmer.

### Le critère qui discrimine : la POSITION, pas la forme

C'est la conclusion de `#10011` sur `build-pin.ts`, transposée : *ce qui identifie le build est sa
position (le segment juste après `games/`), pas sa forme*. Mesure sur le dépôt entier :

    (?:games|dumps|symbols)[\\/]+<forme>   ->   7 jetons, qui sont EXACTEMENT
                                               les 7 builds observés. ZÉRO bruit.

`scripts/python/build_hash.py` est le foyer unique. Trois sources, toutes **dérivées** :

| source | ce qu'elle apporte | état |
|---|---|---|
| tables versionnées `data/symbols/*` + `CURRENT` | garantit que le build **courant** est vu, par construction | toujours mesurable |
| position de chemin (balayage de l'arbre) | récupère les builds **historiques** sans table (`nb3o9lmt6c`, `uu2fr8mv6c`, `rmvdp0v56c`) | `None` si git est muet |
| installation locale `%LOCALAPPDATA%` | un build installé pas encore versionné | **tri-état**, `None` ≠ `[]` |

`BUILD_RE` est l'alternance de ces builds. La **forme générique** subsiste, avec deux rôles et
seulement deux : (a) **mourir bruyamment** — `verifier_la_forme()` la confronte à chaque build
connu et lève `FormeRefusee` si l'un lui échappe ; (b) **inventorier** les jetons qui lui
ressemblent sans être connus, seul canal par lequel un build neuf peut se signaler avant d'avoir
une table ou un chemin. Cet inventaire est imprimé, jamais compté dans un verdict.

### Comment ce correctif ROUGIT

Deux invariants, et ils ne se valent pas :

* `build_re()` voit le build courant — vrai **par construction** (il vient de `CURRENT`). Vérifié
  quand même : un invariant qu'on croit impossible à violer est celui qu'on cesse de mesurer.
* la **forme générique** voit chaque build connu — c'est l'hypothèse, et c'est là que le cran
  mord. Rebranchée sur `[a-z0-9]{8}6c`, `verifier_la_forme()` **lève** sur `t6dpr4k06g`,
  `probe_431 --cliquet` rend `rc=1` et imprime `FORME REFUSEE`.
  Contre-épreuves exécutables : `test_CONTRE_EPREUVE_l_ANCIENNE_forme_fait_REFUSER` et
  `test_CONTRE_EPREUVE_le_cliquet_431_ROUGIT_quand_la_forme_est_REFUSEE`, plus leur **témoin**
  inverse (le motif de refus est absent avec la forme courante).

### Le piège propre à cette réparation, rendu exécutable

Écrire `t6dpr4k06g` en dur aurait fait passer `probe_431` au vert **en gagnant son propre
gisement**. `test_aucun_hash_de_build_n_est_ECRIT_EN_DUR_dans_les_foyers` parcourt l'AST des trois
modules et refuse tout hash connu dans une constante exécutable — docstrings et commentaires
restent libres, c'est là qu'on cite les builds observés.

### L'AUTO-CONTAMINATION, trouvée en jouant le cliquet neuf

Les trois témoins du test de position sont écrits **en position de chemin**
(`games\aaaa1111zz\GameAssembly.dll`) — c'est ce qui les rend probants. Le balayage positionnel les
a donc **avalés** : `builds_connus()` a rendu **10** builds au lieu de 7, et `probe_330` /
`probe_431` auraient compté `aaaa1111zz` comme un build réel. Un recenseur qui fabrique sa propre
cible rassure *et* ment.

`build_hash` écarte désormais les fichiers qui l'**importent** (exemption **dérivée**, jamais
saisie, et **imprimée** à chaque run — pendant exact de `probe_431.AUTO_TEST_MODULE`).
`test_le_module_s_EXEMPTE_de_ses_PROPRES_TEMOINS_et_le_DIT` le garde, en assertionnant d'abord que
les témoins sont bien écrits en position de chemin — sinon il serait vacant.

### Effet mesuré

| | avant | après |
|---|---|---|
| `probe_431` — occurrences en position exécutable | 34 | **44** |
| `probe_431` — RESOLUTIONs | 3 | **4** (la nouvelle : `BUILD_DE_LECTURE`) |
| `probe_431` — mentions en prose | 1 451 | **1 561**, dont **110 sur le build COURANT** |
| `probe_330` — estampilles d'en-tête périmées | 688 | **691** |

La RESOLUTION révélée est corrigée dans le même geste : `BUILD_DE_LECTURE` passe par
`build_pin.archived_build`, qui **contrôle** que la table de ce build est encore versionnée. Le
littéral n'est pas interdit — il est interdit **hors du foyer**.

**Régression, mesurée** : les jetons que l'ancienne forme voyait et que la nouvelle ne voit pas
sont les **4 mutants synthétiques** de `test_431_build_pin_offline.py`, fichier de toute façon
**exempté** du cliquet au titre d'auto-test.
`test_AUCUN_build_vu_par_l_ANCIENNE_forme_n_est_PERDU` balaie l'arbre et exige que tout jeton perdu
vive dans un fichier de test.

**Coût** : `probe_431 --cliquet` passe de ~30 s à ~42 s (balayage positionnel ~6 s, inventaire de
forme ~6 s). `probe_330` : ~17 s.

---

## 2. `#330-r4` — l'estampille n'était gardée par RIEN

### La prémisse, re-mesurée : 8 annoncés, **12** trouvés

Critère : l'en-tête (≤ 14 lignes) porte **à la fois** une marque de génération et une déclaration
de source datée.

| artefact | source déclarée | générateur |
|---|---|---|
| `frida/hooks/data/{ability,effect-type,event-trigger-type,triggered-ability,utility-type}-names.ts` | `data/symbols/rnca9r7q6c/frida/enums.tsv` | `regen_hook_name_tables.py` |
| `frida/hooks/data/targeting-rule-names.ts` | `data/dumps/kqkbjqfb6c/dump.cs` — **supprimée** | **aucun** |
| `scripts/python/enum_maps.py` | `data/symbols/rnca9r7q6c/frida/enums.tsv` | `regen_enum_maps.py` |
| `scripts/python/engine/entities/active_ability_type.py` | idem | `regen_active_ability_tables.py` |
| `docs/rl/dsl-usage/{edges,owners,primitives}.tsv` | `build=rnca9r7q6c` | `dsl_xref_map.py` (= `#330-r5`) |
| `scripts/cliquets-cache/probe_326_inventaire_natif.tsv` | `data/symbols/{gqfc5mff6c,rnca9r7q6c}` | **pas une estampille** : cache multi-build, une CLÉ par build |

### L'accord contenu ↔ build était bien un ACCIDENT

Les trois régénérateurs, en simulation, rendent **0 ajouté / 0 retiré / 0 renommé** partout
(6 tables TS, 6 blocs d'`enum_maps`, 4 recopies d'`ActiveAbilityType`, 29 mirrors `IntEnum`). Seule
l'estampille mentait. La correction est un **re-jeu**, jamais une réécriture de champ : réécrire
l'estampille à la main la rendrait vraie et le contenu invérifiable — on perdrait le seul signal
restant.

⚠ **Les 6 tables `frida/hooks/data/*.ts` ne changent QUE d'en-tête** : aucun rebuild ni reinject
n'est requis pour cette correction, le hook injecté portant déjà les bonnes valeurs.

### L'ORPHELIN est adopté

`targeting-rule-names.ts` était le seul artefact généré du dépôt **sans générateur**.
`regen_hook_name_tables.py` le refusait explicitement : « la projection enum → bits est lossy, ça
demanderait une règle propre, pas ce moule-ci ». Le fond était juste, la forme périmée : **la règle
propre existait déjà** — `probe_252` la joue depuis #252 pour *vérifier* cette table
(`{v.bit_length()-1: n for v, n in jeu.items() if v > 0 and (v & (v-1)) == 0}`). Elle est reprise
**mot pour mot** dans `regen_hook_name_tables._par_bit` : le cliquet et le générateur doivent
projeter à l'identique, sinon le second écrit ce que le premier refusera.

Contenu inchangé (58 bits simples), estampille juste, `probe_252` toujours vert. L'en-tête générée
**dit** que la projection est lossy — sans quoi un lecteur qui y cherche un composite conclurait
que le membre n'existe pas dans le jeu.

---

## 3. `#330-r5` — le scan DSL, où aucune bijection ne rattrape le contenu

`docs/rl/dsl-usage/*.tsv` sort d'un balayage des **xrefs du binaire**. La différence avec `#330-r4`
est décisive : là-bas une bijection membre à membre rattrape le contenu ; ici un simple déplacement
de code périme la mesure sans qu'aucun contrôle le voie. **L'estampille est le seul signal.**

Re-joué sur le build courant : `dsl_xref_map.py scan --batch 4` (609 primitives, 13 899 xrefs,
**16 s** — `ghidra-mcp` était déjà chargé sur `t6dpr4k06g`, analyse complète) puis `report`.

| grandeur | `rnca9r7q6c` | `t6dpr4k06g` |
|---|---|---|
| arêtes | 11 180 | **11 180** |
| primitives | 609 | **609** |
| propriétaires | 1 203 | **1 203** |
| coverage | measured 593 / measured_empty 16 / callers_anonymous 0 / not_measured 0 | **identique** |

Le contenu n'a pas bougé — **et cela ne se savait pas avant de rejouer**. C'est tout l'argument du
résidu. L'axe UTILITY gagne sa ligne `t6dpr4k06g` (ghidra = 2 830, frida = 0) : PARTIELLEMENT
MESURABLE, même régime que le build précédent.

Le scan est écrit pour la contention partagée (batchs, cooldown, réduction automatique, jamais de
relance du serveur) ; aucun incident.

---

## 4. Le CRAN qui manquait — `probe_330r4_estampilles_des_generes.py`

Entré à la banque (`scripts/ratchets.ps1`). Il voit ce qu'**aucune bijection ne peut voir** :
`probe_252`, `probe_275`, `probe_270` et `probe_313` comparent une **table** au build courant ; ils
ne lisent jamais ce que le fichier **déclare**. Les quatre étaient verts pendant que douze artefacts
déclaraient un build antérieur.

Verdict après les re-jeux : **VERT** — 5 376 fichiers balayés, 81 portant une marque de génération,
**0 estampille périmée**.

Ce qu'il **écarte**, et il le compte à chaque run :

| motif | compte |
|---|---|
| pas de marque de génération dans l'en-tête (prose historique — axe `#330-r1`/`-r2`) | 5 295 |
| déclare le build courant | 10 |
| ligne de **données** (clé de cache, pas estampille) | 7 |

Ce qu'il **ne peut pas voir**, et qu'il dit : **65** artefacts générés sans aucune déclaration de
source. Non bloquant — beaucoup ne dérivent d'aucun build (audits de couverture, index de foyers) —
mais compté, parce qu'un artefact dérivé du build qui n'écrit pas d'où il sort est invisible ici.

---

## 5. Trouvaille collatérale : le RÉPARATEUR casse le moteur

`regen_enum_mirrors.py --ecrire` **casse** `engine/entities/pathfinding/pathfinders.py`
(`SyntaxError`), et annonce `ajoutes=0 retires=0 noms corriges=0` juste avant de le faire.

Deux causes distinctes :

1. le fichier portait un **FORM FEED** (`\x0c`) au milieu d'un commentaire — un `\f` d'échappement
   mal interprété, le mot `from` écrit `\x0crom`. **Corrigé ici** (le commentaire était illisible) ;
2. le régénérateur reconstruit par `splitlines()` puis `"\n".join()`, qui **n'est pas l'identité** :
   `splitlines()` coupe sur huit caractères Unicode que `join` ne restitue pas. Il **réordonne**
   aussi les membres (`for v in sorted(jeu)`) alors qu'il vient d'annoncer que rien ne change — sur
   un `IntEnum`, l'ordre de déclaration commande l'itération et le membre canonique d'un alias.

Le point 2 reste **ouvert** : résidu **`#313-r2`**. Le générateur n'a pas été rejoué en écriture sur
les mirrors ; les quatre fichiers qu'il avait touchés ont été restaurés un par un.

---

## Résidus

* **`#313-r2`** — `regen_enum_mirrors.py --ecrire` réécrit un fichier qu'il déclare inchangé :
  `splitlines()`/`"\n".join()` n'est pas l'identité (mesuré sur un `\x0c`), et les membres sont
  réordonnés par valeur croissante. Un réparateur qui corrompt ce qu'il répare est pire qu'absent.
  FOYER: scripts/python/regen_enum_mirrors.py — BLOCAGE: aucun.
* **`#10011-r2`** est le **doublon** de ce `#330-r3` (même gisement, même correctif) : le fermer avec
  lui.
