# #462-r6 -- Le ROUGE DE SCENARIO a un nom, et il le porte jusqu'au ledger

`case-462` ventile les rouges live en **PORT / MONTAGE / HARNAIS**, et constate que la ventilation
ne suffit pas : **3 des 8 rouges n'accusent ni le port ni le harnais**. Ils accusent le SCENARIO --
l'echantillon n'est plus confrontable, ou le contre-controle a cesse de mordre.

Le probleme n'est pas qu'ils rougissent : **c'est le bon signe**, ces tests sont concus pour rougir
plutot que passer a vide (la lecon de #457 sur le « vert vacueux », appliquee, et qui rend). Le
probleme est qu'un rouge de scenario **ressemble trait pour trait a un rouge de port** dans le
message du test -- la forme de #533.

---

## 1. Les trois, tranches un par un

La question binaire **avant toute edition** : le contre-controle a-t-il cesse de mordre parce que le
PORT S'EST AMELIORE (re-crafter), ou parce qu'il a REGRESSE (reclasser en rouge de PORT) ? Le
discriminant est l'assertion de FOND du meme fichier. **Les trois ont la meme reponse -- le port
s'est ameliore -- mais par TROIS mecanismes differents**, et c'est ce qui compte.

| fichier | mecanisme | commit qui l'a rendu inerte | preuve |
|---|---|---|---|
| `test_placement_sort_rng_live.py` | **point d'ancrage disparu** | `54c04b59` (2026-07-29) | contre-epreuve A |
| `test_valkyrie_strike_targeting_live.py` | **mutation MASQUEE par une autre porte** | `a644607e` (2026-07-29) | lecture du decompile + C |
| `test_pick_randomly_one_rng_live.py` | **ecart connu FERME** | `70dc9769` (2026-07-29) | contre-epreuve D |

### 1.1 `placement_sort_rng` -- le simulacre patchait un nom que le port n'appelait plus

Le contre-controle substitue le **modele M0** (le port d'AVANT : 1 tirage des que le pool depasse 1)
et exige `m0_n > live_n`. Mesure : `m0_n == live_n == 10` sur `scarabhive` (`controledict`, lui,
mordait toujours : 3 vs 2).

`_LegacyPlacement` (dans `probe_130_placement_sort_rng.py`) monkeypatche `spawn._first`. Or
`SpawnUnitOperation.execute` ne l'appelait plus : `54c04b59` (« le tile-selecteur du spawn s'evalue
UNE fois ») a remplace la boucle `for i in range(count): tile = _first(_sort_by_distance(...))` par
un **snapshot + slice** `_sort_by_distance(...)[:count]`. Le changement est JUSTE -- il mirrore la
structure de `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute`, qui resout son
tile-selecteur une seule fois puis itere. Mais le noeud natif `First(source, count)` avait perdu son
NOM, et le simulacre s'ancrait dessus.

**Correctif** : le noeud est nomme. `spawn._first_n(tiles, count)` mirrore
`IdunBattleLogic.Entities.DSLFactory$$First(entities, count, ignoreForcedTargets=false)` -- le frere
a COUNT de `_first`, `min(count, len(source))` elements en tete, **zero tirage**. Strictement NO-OP
(c'est le slice, sous un nom). `_LegacyPlacement` patche desormais les DEUX.

> **La lecon generalisable** : un simulacre s'ancre sur le **MIRROR D'UN NOEUD NATIF**, jamais sur un
> detail de la facon dont le port l'ecrit. Le mirror est stable par construction -- il ne bouge que
> si le natif bouge ; une forme d'ecriture bouge au premier refactor, **en silence**.

### 1.2 `valkyrie_strike_targeting` -- la mutation etait masquee par une porte portee depuis

Le contrefactuel retire `TargetIsTile` (bit 6) du masque et exige un **FAUX-ACCEPT** sur les lignes
que le natif refuse. Mesure : 6 lignes refusees, **0 faux-accept**.

Cause, lue au port et au decompile : le bit 6 n'est pas seulement la regle « tuile non marchable »,
c'est **AUSSI le bit de DOMAINE**, en tete de la cascade
(`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`, surcharge 7 arguments). Le
retirer bascule l'ability en unit-targeting -- et depuis l'**elargissement #253**
(`get_target_domain_broken_rule`, commit `a644607e`), une cible qui est une TUILE du board **sans
occupant** y rompt `TargetIsUnit`. Le port refuse donc toujours, par une AUTRE porte, avec un AUTRE
code.

Chronologie mesuree : `697fd116` (#245, le test) est **ancetre** de `a644607e` (#253), **2 h 38**
plus tot le meme jour. Le contre-controle est ne discriminant et l'est reste... jusqu'a l'apres-midi.

**Correctif -- deux contrefactuels, deux propos** :

* **SUFFISANCE** (`desarme`) : masque **PLUS** `AllowUnwalkableTargetTile` (bit 43). Le filtre
  statique lit `if ((rules & 0x40) && !IsWalkable(mainTile) && (rules & AllowUnwalkableTargetTile)
  == 0) -> broken(1)` : poser le bit 43 eteint **exactement** ce refus et rien d'autre (le domaine
  reste TILE). C'est le desarmement que le NATIF lui-meme prevoit -- donc la mutation minimale qui
  isole la branche.
* **NECESSITE** (`sansTile`, conserve) : prive du bit 6, le port doit **cesser d'ACCORDER** avec le
  natif. C'est ce que le retrait prouve REELLEMENT, et l'assertion le dit maintenant.

### 1.3 `pick_randomly_one_rng` -- l'ecart fige a ete FERME, et c'est prouve par mutation

Le test figeait un **GAP CONNU** : `residu smite == 1 tirage par volet splash`. Mesure : `{1: 0,
2: 0}`. Le message anticipait les deux lectures (« le resolve slot-8 a ete porte (bonne nouvelle) ou
un autre etage a change ») **sans pouvoir choisir** -- c'est la limite d'un ecart fige : il n'accuse
personne.

Tranche : `70dc9769` (#221, 2026-07-29) a porte le resolve slot 8
`IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` sur la branche
reduce-then-roll de `_run_hits`, gate par la FAMILLE (`is_attack_damage_op`). Le smite Psyker est de
la famille ATTACK (`IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`), donc son tirage
sur cellule degeneree est desormais consomme.

Ce n'est pas une deduction d'historique : **contre-epreuve D** -- annuler #221 (retour a
`hd.get_damage(rng)` inconditionnel) restaure **exactement** `{1: 1, 2: 1}`.

**Correctif** : le contrat devient l'**EGALITE** aux trois regimes. Un ecart fige n'accuse personne ;
une egalite, elle, accuse le PORT quand elle tombe -- et le message nomme l'etage a instruire en
premier, avec le sens du signe.

---

## 2. Le mecanisme -- `scripts/python/counterproof.py`

### 2.1 Ce qui est livre

```
ScenarioRed(AssertionError)          # ni PORT ni HARNAIS
├── InertCounterproof                # "CONTRE-CONTROLE INERTE"
└── UnconfrontableSample             # "ECHANTILLON NON CONFRONTABLE"

assert_counterproof(bites, *, mutation, doit_casser, observe, remede)
assert_sample_confrontable(realise, *, mutation, doit_casser, observe, remede)
```

Les deux sous-classes couvrent **les deux faces que `case-462` §3 distingue deja** : la mutation qui
ne casse plus (`placement_sort_rng`, `valkyrie`) et l'echantillon qui ne realise plus le regime
(`damage_catalog`). Aucune n'est speculative : chacune a des porteurs REELS dans cette PR.

### 2.2 La granularite est l'ASSERTION, jamais le test

`test_valkyrie_strike_targeting_mask_matches_native` melange **trois natures** dans UNE fonction :
l'accord natif/port (fond), les gains (contre-controle), le contrefactuel (contre-controle). Un
`pytest.mark` au niveau du test serait **faux par construction**. C'est le point qui a decide la
forme.

### 2.3 Pourquoi un TYPE, et pas un prefixe de message

Un prefixe convenu ecrit a la main aurait suffi a un lecteur attentif. Il a trois defauts : il n'est
pas mecanique (rien ne le distingue d'un rouge de port dont la prose porte les memes mots), il n'a
pas de point d'ancrage (chacun l'ecrit a sa facon), et il ne force pas le **REMEDE**.

Le type, lui, traverse toute la chaine **sans qu'une ligne d'outillage change** :

```
pytest short summary : FAILED tests/...::test_x - InertCounterproof: CONTRE-CONTROLE INERTE ...
junitxml             : <failure message="InertCounterproof: CONTRE-CONTROLE INERTE -- ...">
ledger probe_462     : le symptome VERBATIM, donc le nom du type
```

Le dernier maillon est le decisif : `probe_462._parse_junit` conserve `child.get("message")` et
l'ecrit dans `scripts/ratchets-462-live-attestations.json`. **Le prochain balayage du parc live
lira donc la ventilation dans son propre ledger**, au lieu de la refaire a la main.

Rester une sous-classe d'`AssertionError` est delibere : meme couleur, meme comptage, meme
`<failure>`, et tout `except AssertionError` existant continue de la voir. Le rouge reste un rouge --
il dit seulement qui il accuse.

### 2.4 Ce que le mecanisme ne pretend PAS faire

Il ne **decide** pas qu'une assertion est un contre-controle : c'est indecidable (`m0_n > live_n` et
`m1_n == live_n` sont syntaxiquement jumeaux et de natures opposees). C'est une declaration
d'AUTEUR. Ce qui est garde mecaniquement, c'est que la declaration ne **mente** pas.

---

## 3. Ce qui garde le mecanisme -- et pourquoi AUCUNE entree neuve dans la banque

`scripts/python/tests/test_462r6_counterproof_marker_offline.py`, **19 tests**, trois volets :

1. **le CONTRAT** du helper -- silencieux quand la garde mord, bon type sinon, message COMMENCANT
   par le marqueur (probe_462 aplatit et tronque a 300), quatre champs presents, kwargs obligatoires ;
2. **le CANAL** -- un vrai pytest dans un tmpdir SYSTEME, dont le junitxml est relu par le **VRAI
   consommateur** (`probe_462._parse_junit`, avec son `_classname_index`). Pas une simulation : si
   pytest cessait d'y mettre le nom de la classe, le mecanisme deviendrait decoratif -- vert ici,
   muet la ou on le lit ;
3. **le GISEMENT d'usurpation** -- balayage AST de `git ls-files scripts/python` : le marqueur ne
   doit apparaitre dans AUCUN message d'echec ecrit a la main (`assert ..., msg` / `raise X(msg)`).
   Sinon un rouge de PORT porterait le nom d'un rouge de SCENARIO, et le lecteur -- ou le ledger --
   le classerait **a l'envers**, l'erreur exactement symetrique de celle qu'on ferme. Commentaires,
   docstrings et `print` de verdict restent libres.

**Pas d'entree neuve dans `scripts/ratchets.ps1`**, et c'est un choix, pas un oubli : ce fichier est
OFFLINE, donc dans le perimetre **DERIVE** de `probe_457` (`git ls-files scripts/python/tests`, tout
ce qui n'est pas `_live.py`), donc joue par la banque. La regle #427 (« un cliquet doit etre dans une
liste qu'on lance ») est satisfaite par ce canal -- et #457-r6 a precisement **retire** les trois
entrees `pytest_*` qui nommaient leurs fichiers a la main, parce que c'etaient des allowlists.

Perimetre du balayage : borne au checkout courant **par construction** (`git ls-files` depuis
`git rev-parse` -- depuis un worktree git ne liste que ce worktree ; depuis l'arbre principal,
`.claude/worktrees/` est un AUTRE checkout). Ni `rglob` depuis la racine, ni exclusion a saisir
(#434 / #440). Aucune ecriture sous `scripts/python/` (#455) : `mkdtemp()` sans `dir=`.
Le detecteur porte son propre **auto-test** dans les deux sens (9 cas) : ce qui doit etre vu l'est,
ce qui est legitime ne l'est pas.

---

## 4. Validation -- les quatre contre-epreuves

Un test qui passe ne prouve rien : ce qui compte est que **la mutation qu'il est cense attraper le
fasse rougir**, et que le NOM separe.

| # | mutation | attendu | mesure |
|---|---|---|---|
| **A** | `_LegacyPlacement` re-prive de son ancrage `_first_n` | `InertCounterproof` sur `test_previous_model_would_be_red_here[scarabhive]` | **1 failed, 21 passed** -- `counterproof.InertCounterproof: CONTRE-CONTROLE INERTE`, 4 champs imprimes |
| **B** | tirage parasite injecte dans le PORT (`_sort_by_distance`) | `AssertionError` NU sur l'assertion de FOND, contre-controle VERT | **1 failed, 21 passed** -- `test_placement_consumes_no_rng_live[scarabhive]`, `port 12 genrand vs live 10` |
| **C** | contrefactuel de suffisance remis sur `sansTile` | `InertCounterproof` | **1 failed** -- le rouge d'origine, rejoue, **sous son nom** |
| **D** | #221 annule (`hd.get_damage(rng)` inconditionnel) | `PORT : residu smite {1: 1, 2: 1}` | **1 failed, 14 passed** -- l'ecart d'origine restaure **a l'identique** |

**A + B forment la paire decisive** : meme fichier, meme scenario, deux mutations opposees --
l'une accuse le scenario et sort en `InertCounterproof`, l'autre accuse le port et sort en
`AssertionError` nu. C'est la separation, mesuree, pas argumentee.

**D est une preuve de CAUSALITE**, pas une correlation d'historique : le seul retrait de #221
restitue exactement `{1: 1, 2: 1}`.

### Avant / apres, sur les trois fichiers

| fichier | avant | apres |
|---|---|---|
| `test_placement_sort_rng_live.py` | 17 passed, **1 failed** | **22 passed** |
| `test_valkyrie_strike_targeting_live.py` | 0 passed, **1 failed** | **1 passed** |
| `test_pick_randomly_one_rng_live.py` | 14 passed, **1 failed** | **15 passed** |
| `test_462r6_counterproof_marker_offline.py` | -- | **19 passed** |

---

## 5. Ce qui n'est PAS couvert

* **`test_damage_catalog_live.py` n'est pas repare ICI** -- il etait hors du perimetre soumis (les
  trois fichiers de `#462-r6`). Il a ete ferme **en parallele** par `#462-r4e`
  (`case-462-r4e-echantillon-non-confrontable.md`), pendant cette tranche : c'est une confirmation
  INDEPENDANTE de la categorie -- son diagnostic (« l'echantillon n'avait JAMAIS ete confrontable »)
  est exactement `UnconfrontableSample`, et sa correction s'est revelee NON bornee (le pool est une
  donnee LIVE, la parametrisation tourne a la COLLECTE). Son assertion ne porte pas le marqueur : ce
  fichier reste a marquer, comme le reste du parc (`#462-r6-r2`).
* **Le marquage n'a ete pose que sur les trois fichiers touches.** Le reste du parc (419 fichiers
  live) contient des contre-controles non marques -- leurs rouges continueront de se lire comme des
  rouges de port. Le marquage se fera au fil des passages, pas par balayage : personne ne peut
  deriver « ceci est un contre-controle » sans lire l'intention.
* **Le trou B reste ouvert** (`#462-r1`) : rien ne voit un contre-controle qui devient inerte sous un
  changement qui ne touche pas son fichier. Les trois cas d'ici en sont exactement des instances --
  aucun des trois commits fautifs ne touchait le test. Le nom ne ferme pas ce trou ; il rend son
  diagnostic immediat quand le balayage periodique le trouve.
* **Aucun garde ne verifie qu'un contre-controle MORD encore** -- c'est structurellement le meme
  probleme que le trou B, et il coute le meme prix (rejouer du live).

---

## 6. Residus

* **`#462-r6-r1`** -- **Un contre-controle qui devient inerte n'est vu que par le balayage
  periodique.** Le marqueur rend le diagnostic immediat, il ne rend pas la detection plus precoce.
  Piste eventuelle et NON evaluee : faire declarer au contre-controle la marge dont il dispose
  (ex. `m0_n - live_n >= 1`) pour qu'il rougisse **avant** d'etre a egalite -- mais une marge est un
  scalaire, et le dépôt proscrit de fitter un scalaire. A instruire, pas a coder.
* **`#462-r6-r2`** -- **Le marquage du parc est incremental.** 3 fichiers sur 419. Rien ne mesure
  combien de contre-controles non marques existent : le recensement demanderait de lire l'intention
  de chaque assertion, ce qu'aucun balayage ne fait.
