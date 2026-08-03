# #462 -- L'etat des tests LIVE, que rien ne regarde

`probe_457` garde le VERT des tests OFFLINE, et son perimetre exclut `*_live.py` -- choix assume :
la suite live sature la session Frida partagee. La boucle de merge, elle, ne rejoue que les tests
live de la TRANCHE modifiee. **Entre les deux, personne ne regarde jamais l'etat des tests live sur
`master`.**

Meme famille que #455 : ce n'est pas le rouge le probleme, c'est l'INVISIBILITE.

Instrument : `scripts/python/probe_462_live_tests_status.py`.
Ledger versionne : `scripts/ratchets-462-live-attestations.json`.

---

## 1. Le parc, et ce qu'il coute

Comptes RE-DERIVES le 2026-08-03 (`git ls-files scripts/python/tests`, convention de collecte
pytest par defaut) :

| | fichiers |
|---|---|
| collectes par pytest | 533 |
| dont `*_live.py` | **417** |
| dont offline (perimetre `probe_457`) | 116 |

**Cout du balayage live, MESURE** (4 workers -- le plafond DUR du `CLAUDE.md`, le pump est partage) :

| passe | fichiers | mur | par fichier |
|---|---|---|---|
| pilote | 8 | 147,7 s | 18,5 s |
| tranche 0 | 60 | 971,9 s | 16,2 s |

Extrapolation du parc entier : **~1 h 50 a 4 workers**. C'est hors de portee d'une banque dont le
mur entier tient en ~300 s, et le rester : le cout est LINEAIRE en fichiers et le plafond de 4 est
une contrainte de plateforme, pas un reglage.

### Le shard tournant est REFUTE par le calcul

Proposition ecartee avant d'etre codee : faire tourner 1/N du parc a chaque passage de banque.
A ~16 s/fichier et un budget de +60 s de mur par passage, un passage couvre ~15 fichiers, donc
**~28 passages pour couvrir le parc une fois** -- et un fichier donne n'est revu qu'une fois sur 28.
Ce n'est pas un garde, c'est une loterie : un rouge y dort des semaines. Le gisement mesure en §3
(un fichier rouge depuis 22 jours) est precisement ce qu'une loterie ne rattrape pas.

### La collecte est exhaustive et quasi gratuite -- mais elle prouve MOINS qu'il n'y parait

`--collect` joue `--collect-only` sur tout le perimetre : **aucun runner monte**. Mesures du
2026-08-03 : **36,8 s** sur les 533 fichiers a froid, **273,8 s** sur les 417 live sous charge (un
mur se mesure dans ses conditions). Dans les deux cas **rc=0, 0 erreur**.

⚠ **ET POURTANT LE BALAYAGE A TROUVE UN ROUGE DE HARNAIS.** `test_fabricator_claw_cap_live.py` rend
**10 erreurs de SETUP** sur `ImportError: cannot import name 'BUILD_HASH' from
'probe_193c_move_playbook_terms'`. La collecte ne le voit pas, et c'est STRUCTUREL : l'import fautif
est **a l'interieur d'une fonction** (`test_fabricator_claw_cap_live.py` L71 importe
`probe_242_fabricator_claw_cap`, qui importe `BUILD_HASH` a sa L57), et `--collect-only`
**n'execute ni les fixtures ni les corps de test**.

**Ce que `--collect` prouve exactement** : les imports de NIVEAU MODULE resolvent, sur 417/417
fichiers. **Ce qu'il ne prouve pas** : qu'un import differe resolve. Ecrire << la categorie
HARNAIS est vide >> sur la foi de la collecte etait donc faux -- et c'est la meme faute que le
dossier documente ailleurs : une mesure PARTIELLE lue comme une couverture.

---

## 2. L'inventaire

Balayage du 2026-08-03, 4 workers, ordre de visite par RISQUE (dernier commit le plus ANCIEN
d'abord), tranches de 60 fusionnees dans le ledger.

| | fichiers |
|---|---|
| perimetre live | **419** |
| **JOUES** | **240** (57 %) |
| dont VERT | 232 |
| dont **ROUGE** | **8** |
| **ECARTES -- statut INCONNU, pas vert** | **179** |

**Taux de rouge sur l'echantillon : 3,3 %** (et il est reste a 3,3 % sur les quatre tranches :
3/60, 1/60, 2/60, 2/60). Extrapole naivement au parc : **~14 fichiers rouges**.
⚠ L'echantillon est la cohorte au dernier commit le plus ANCIEN. Que ce biais tire le taux vers le
haut ou vers le bas est **INCONNU** -- c'est le residu `#462-r3`. Ne pas presenter 3,3 % comme le
taux du parc.

| fichier ROUGE | bilan | symptome (verbatim, tronque) |
|---|---|---|
| `test_terrifying_defense_live.py` | p=4 f=1 | `per-hit offline != live : off=[433,402,434,378,350,403] live=[434,403,435,379,351,404]` |
| `test_nightshroud_combat_live.py` | p=1 f=1 | `per-hit offline != live : off=[180,180,112,158,240,183] live=[250,212,168,122,220,221]` |
| `test_chain_after_refused_addeffect_live.py` | p=3 f=1 | `PORT: Pinned refuse sur une cible sans TerminatorArmour` |
| `test_fabricator_claw_cap_live.py` (**REPARE #462-r4c** -> p=10) | p=0 **e=10** | `failed on setup with ImportError: cannot import name 'BUILD_HASH' from 'probe_193c_move_playbook_terms'` |
| `test_damage_catalog_live.py` | p=0 f=4 | `build runner KO (rl_duel) [...] --p-units: hors pool / non spawnables au rank 17: ['adeptSmnGeminaeSuperia']` |
| `test_placement_sort_rng_live.py` | p=17 f=1 | `le modele d'avant rend 10 genrand pour 10 live -- il devrait SUR-tirer [...] le scenario n'est plus discriminant` |
| `test_valkyrie_strike_targeting_live.py` | p=0 f=1 | `le masque prive de TargetIsTile devrait faux-accepter les 6 lignes refusees, il n'en faux-accepte que 0` |
| `test_pick_randomly_one_rng_live.py` | p=14 f=1 | `residu smite {1: 0, 2: 0} != 1 tirage par volet splash (attendu, cf. docstring)` |

**Cout de ce balayage** : 4 tranches, murs **971,9 / 1000,0 / 1975,1 / 2227,8 s**. Le cout par
fichier passe de **16,2 s** (machine calme) a **37,1 s** (5 agents + un `--collect` concurrent).
Meme lecon que `probe_457` : un mur se MESURE dans ses conditions, il ne se cite pas.

### Pourquoi le balayage s'arrete a 180 : QUATRE etats, pas deux

Ce dossier existe parce que « pas rouge » se lit comme « vert ». Son propre inventaire doit donc
distinguer ce que le parc distingue :

| etat | ce que ca veut dire | compte |
|---|---|---|
| **VERT** | joue, tous ses tests passent, a CE commit | 232 |
| **ROUGE** | joue, au moins un echec -- ou 0 assertion evaluee (#455 / #455-r3) | 8 |
| **ECARTE / NON MESURE** | jamais atteint, ou atteint sans produire de report | 179 |

Quatre tranches de 60 sont completes. Une cinquieme a ete **INTERROMPUE a son demarrage** par une
fenetre de maintenance (restart du jeu + reinject) : ses workers ont ete arretes et ses runners
rendus avant tout report. Ses fichiers ont ete **REJOUES apres la reouverture** via `--unmeasured`,
donc ils ne restent pas dans un demi-etat.

⚠ **Un fichier non joue a cause du drain n'est ni rouge ni vert : il est NON MESURE.** Le confondre
avec « vert » reproduirait exactement l'invisibilite que ce dossier ferme. Le probe le tient
mecaniquement : un fichier sans report est classe `NON JOUE`, il **COMPTE dans le code de sortie**,
et il n'entre PAS au ledger avec un verdict vert.

### Ce qui n'est PAS couvert

* Les 237 fichiers ECARTES + NON MESURES : leur statut est **INCONNU**, pas vert. Le ledger le dit
  fichier par fichier ; `--report` imprime l'anciennete de chaque mesure et le nombre de
  **JAMAIS mesures**.
* Un fichier VERT au balayage l'etait **a ce commit-la**. Rien ne promet qu'il le reste.
* Le balayage tourne sur une session partagee par 4 autres agents. Un rouge de CONTENTION
  (cap de runners, pump sature) est converti en ECHEC par le conftest (#77) -- c'est voulu, mais il
  faut le relire comme tel : la ventilation ci-dessous distingue ce cas.

---

## 3. La ventilation -- un rouge n'accuse pas forcement le PORT

C'est la lecon de #533 : le rouge y accusait le MONTAGE, et le message du `pytest.fail` disait vrai
sur le FAIT et FAUX sur la CAUSE. Trois categories :

* **PORT** -- le moteur diverge reellement du natif ;
* **MONTAGE** -- le harnais n'exerce pas le regime voulu (pilotage, board, seed, unite non spawnable) ;
* **HARNAIS/COLLECTE** -- le test ne s'execute meme pas.

Le probe ne CLASSE pas : il ne peut pas. Il rapporte le symptome VERBATIM (le ledger le conserve) ;
la ventilation est un acte de lecture.

### `test_terrifying_defense_live.py` -- **PORT**

```
off =[433, 402, 434, 378, 350, 403]
live=[434, 403, 435, 379, 351, 404]
```

**+1 exactement sur les six coups.** Ce n'est donc pas un facteur (les bases different d'un coup a
l'autre : 501 a 621) mais un etage d'**ARRONDI**.

⚠ **L'identite `live = b - floor(0,3b)` contre `off = floor(0,7b)` colle 6/6, et elle est meme
structurelle** -- `frac(0,3b) + frac(0,7b) = 1` des que `0,3b` n'est pas entier, donc l'ecart vaut
1 TOUJOURS. **Ce n'est pas pour autant le diagnostic**, et le dire serait fitter un scalaire : le
moteur ne travaille pas en `floor` mais en **Fix64** avec `Round(., AwayFromZero)`
(`engine/services/damage_modifiers.py`, `apply_pct_entries`). L'identite DECRIT le symptome.

Foyer a instruire en premier : la materialisation INTERMEDIAIRE de
`IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`, que
`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` appelle **deux
fois** (face attaquant puis face defenseur) avec un `Round` **inconditionnel** des que le
`Nullable<DamageModifiers>` correspondant `HasValue` -- y compris a multiplicateur neutre. C'est
exactement le foyer de **#446-r2**, qui y avait mesure un `-1` par coup, de signe oppose.

### `test_nightshroud_combat_live.py` -- **PORT** (TRANCHE : `case-462-r4d-arrondi-inter-faces-combat.md`)

```
off =[180, 180, 112, 158, 240, 183]
live=[250, 212, 168, 122, 220, 221]
```

Ecarts **non monotones**, et le 4e coup est **INVERSE** (offline > live). Une divergence de formule
donnerait un signe constant ; ici la signature ressemble a un desalignement (ordre des coups, cible,
ou flux RNG qui a diverge). **Ne pas conclure sans decomposer par etage.**

Ce fichier est le porteur du **trou B** : valide **bit-exact** par `51a16cba` (2026-07-12), touche
depuis uniquement par `5fa788b7` et `6c112458` (deux refactors de masse), **ROUGE** au balayage.
Personne ne l'a casse dans un diff qui le contenait.

> **TRANCHE : PORT, et NI l'un NI l'autre des deux refactors.** La bissection designe **`0ad4b9e8`
> (#446-r2, 2026-08-02)** -- un commit qui **ne touchait pas ce fichier** : son parent rend
> `2 passed`, lui rend les valeurs exactes ci-dessus. **Le trou B a donc enfin un coupable nomme.**
>
> L'ecart n'avait « aucune forme » parce que ce n'est pas la valeur qui diverge mais la **borne
> basse de la cellule tiree** (`[109,282]` port contre `[108,282]` natif) : le tirage est un modulo,
> donc une largeur decalee de 1 diffracte les six coups. Le flux RNG, lui, etait **synchronise**
> (6 tirages des deux cotes) -- ce qui ecarte d'emblee l'hypothese du desalignement ci-dessus.
> ⚠ Le decalage ne se lit PAS par soustraction quand il n'est pas constant : il a fallu **INVERSER**
> le tirage a etat PRNG connu (`probe_462d_nightshroud_stage_diff.py --solve`).
>
> **Ferme par #462-r4a**, qui reparait la meme cause en parallele -- cf. l'avertissement sous la
> ventilation.

### `test_damage_catalog_live.py` -- **MONTAGE** (REPARE : `case-462-r4e-echantillon-non-confrontable.md`)

```
[error] --p-units: hors pool / non spawnables au rank 17: ['adeptSmnGeminaeSuperia']
        pool = 97 units (voir `build --list-pool`)
```

`_catalog_units()` trie les candidats et prend `cands[:4]`. Le tri etant alphabetique, la tete est
`adeptSmn*` (un **SUMMON** -- il arrive en bataille par son summoner, jamais par `--p-units`) puis
`admecBoss*` (**npc**). **Aucun filtre de spawnabilite** : les 4 parametres du regime par defaut
sont tous non spawnables, donc le fichier ne peut que rougir. La gate de confrontabilite du
`CLAUDE.md` n'est pas appliquee au choix de l'echantillon.

### `test_pick_randomly_one_rng_live.py` -- **ATTENTE PERIMEE**

```
AssertionError: residu smite {1: 0, 2: 0} != 1 tirage par volet splash (attendu, cf. docstring).
S'il a bouge, le resolve slot-8 a ete porte (bonne nouvelle) ou un autre etage a change.
```

Le test fige un **GAP CONNU** (1 tirage residuel) ; le residu est passe a **0**. L'auteur avait
anticipe les deux lectures. A trancher : soit le resolve slot-8 a ete porte -- l'attente est
perimee et se met a jour ; soit un etage a cesse de consommer du RNG -- c'est une regression. Le
message ne permet pas de choisir, et c'est exactement la forme #533 (vrai sur le fait, muet sur la
cause).

### `test_chain_after_refused_addeffect_live.py` -- **PORT**

```
AssertionError: PORT: Pinned refuse sur une cible sans TerminatorArmour
```

Le test NOMME lui-meme la face fautive. Le port refuse un `AddEffect` que le natif accepte : la
chaine d'effets s'interrompt la ou elle devrait continuer. Degradation **silencieuse** hors de ce
test -- un effet qui n'est pas pose n'emet rien (« l'absence d'un EVENEMENT ne prouve rien »).

### `test_placement_sort_rng_live.py` -- **MONTAGE (controle negatif devenu VACUEUX)**

```
scarabhive : le modele d'avant rend 10 genrand pour 10 live -- il devrait SUR-tirer (1 par tuile
placee). S'il ne sur-tire plus, le pool du scenario est tombe a 1 (re-crafter la geometrie : le
scenario n'est plus discriminant).
```

Ce test est un **CONTRE-CONTROLE** : il verifie que l'ANCIEN modele serait rouge sur ce scenario,
donc que le scenario DISCRIMINE. Il rougit parce que la geometrie ne separe plus les deux modeles
(pool tombe a 1 tuile) -- le test ne dit plus rien du port, il dit que sa propre garde est devenue
creuse. **Meme famille que le << vert vacueux >> de #457**, mais ici l'auteur avait arme le detecteur :
le test rougit AU LIEU de passer a vide. C'est la bonne conception, et elle a mordu.

### `test_fabricator_claw_cap_live.py` -- **HARNAIS**, et c'est le trou B a l'etat pur

```
failed on setup with "ImportError: cannot import name 'BUILD_HASH'
from 'probe_193c_move_playbook_terms'"          (x10 tests)
```

Chaine lue : le test importe `probe_242_fabricator_claw_cap` (L71, **dans une fonction**), qui
importe `BUILD_HASH` de `probe_193c_move_playbook_terms` (sa L57). Ce nom a ete **RETIRE le
2026-08-01 par `8be764fb`** -- le nettoyage des litteraux de build de #431, un **bon** changement.

Le fichier est donc mort depuis **2 jours**, et rien ne pouvait le dire :
* ce n'est pas le port ;
* le commit fautif ne touchait pas ce fichier de test (**trou B**) ;
* `probe_365` garde << un fichier versionne qui importe une cible GITIGNOREE ou absente >> -- ici le
  MODULE existe, seul le NOM a disparu : hors de son gisement ;
* `--collect` ne le voit pas (import differe, cf. §1).

### `test_valkyrie_strike_targeting_live.py` -- **MONTAGE (contre-controle vacueux), a trancher**

```
le masque prive de `TargetIsTile` devrait faux-accepter les 6 lignes refusees,
il n'en faux-accepte que 0
```

Meme forme que `placement_sort_rng` : le test MUTE le masque et exige que la mutation CASSE. Elle
ne casse plus -- soit une autre porte refuse desormais ces 6 lignes (le contre-controle est masque,
donc creux), soit le flag n'est plus lu (et la c'est un PORT). Le message ne separe pas les deux.

<!-- VENTILATION -->

### Bilan de la ventilation

| categorie | fichiers |
|---|---|
| **PORT** | 2 (`terrifying_defense`, `chain_after_refused_addeffect`) |
| **PORT ou MONTAGE, a trancher** | 1 (`nightshroud_combat`) -- TRANCHE : **PORT**, MEME cause que `terrifying_defense` (#462-r4d) |
| **MONTAGE / SCENARIO** | 3 (`damage_catalog` echantillon non spawnable ; `placement_sort_rng` et `valkyrie_strike_targeting` contre-controles devenus creux) |
| **HARNAIS** | **1** (`fabricator_claw_cap` -- import mort depuis 2 jours) |
| **Attente perimee** | 1 (`pick_randomly_one_rng`) |

⚠ **Et elle SUR-COMPTE les causes.** `terrifying_defense` et `nightshroud_combat` y sont deux
entrees, et ont ete dispatches comme **deux taches** ; ils n'avaient qu'**UNE** cause, fermee d'un
seul fix (#462-r4a). Rien dans les symptomes ne le disait : regimes sans rapport (`-30 %`
`Terrifying_ExtraDefense` contre `-20 %` `MartialKatah`), ecarts de signes **OPPOSES**, l'un
CONSTANT et l'autre diffracte par le modulo. Le seul indice etait que cette meme section designait
**deja le meme etage** (`CalculateBaseDamageWithModifiers`) pour les deux -- et c'etait le bon.
Cout : deux solveurs ont instruit le meme foyer en parallele. **Un inventaire compte des SYMPTOMES ;
le nombre de causes ne se decouvre qu'en les reparant** -- quand deux rouges pointent le meme etage
nomme, les grouper est le pari le moins cher. Detail : `case-462-r4d-...md` §6.

⚠ **La ventilation a TROIS cases ne suffit pas.** Trois des huit rouges n'accusent ni le port ni le
harnais : ils accusent le **SCENARIO** -- l'echantillon n'est plus confrontable, ou le
contre-controle ne discrimine plus. Un rouge de scenario ressemble trait pour trait a un rouge de
port dans le message du test, et c'est exactement la forme de #533.

> **RESOLU (#462-r6) -- `docs/rl/case-462-r6-le-rouge-de-scenario.md`.** La quatrieme case existe
> desormais, et elle a un NOM que l'echec porte lui-meme : `counterproof.py` livre
> `ScenarioRed(AssertionError)` -> `InertCounterproof` (« CONTRE-CONTROLE INERTE ») et
> `UnconfrontableSample` (« ECHANTILLON NON CONFRONTABLE »), poses au niveau de l'ASSERTION. Le nom
> du TYPE traverse pytest, le junitxml et **le ledger de ce probe** sans qu'une ligne d'outillage
> change -- le prochain balayage lira donc sa ventilation dans `ratchets-462-live-attestations.json`
> au lieu de la refaire. Les trois rouges sont repares a leur cause reelle : `placement_sort_rng`
> (ancrage disparu -> le noeud natif `First(source, count)` porte un nom), `valkyrie_strike_targeting`
> (mutation MASQUEE par l'elargissement #253 -> contrefactuel sur le desarmement natif
> `AllowUnwalkableTargetTile`), `pick_randomly_one_rng` (ecart figE FERME par #221 -> contrat =
> egalite). Reste `damage_catalog` (echantillon alphabetique), au backlog sous `#462-r4`.
>
> Le point le plus reutilisable est la **paire de contre-epreuves A/B** : meme fichier, meme
> scenario, deux mutations opposees -- l'une accuse le scenario et sort en `InertCounterproof`,
> l'autre accuse le port et sort en `AssertionError` NU. La separation est mesuree, pas argumentee.

⚠ **Et un rouge sur trois vient d'un CONTRE-CONTROLE qui rougit parce qu'il a cesse de mordre.**
C'est le bon signe : ces tests-la sont concus pour rougir plutot que passer a vide. La leçon de
#457 (le << vert vacueux >>) a ete appliquee, et elle rend ici.

---

## 4. DEUX trous, pas un -- et ils n'ont pas le meme prix

L'enquete sur l'origine des rouges separe nettement deux mecanismes.

### Trou A -- le fichier est DANS le diff de son propre commit, et part rouge

C'est **exactement** #533. `test_env_fire_tile_dot_applies_resilient_cap_live` a ete **introduit**
par `ad5692e7` (2026-07-26), dans un commit qui modifiait **398 lignes** de son propre fichier, et
il est reste rouge jusqu'a `7b38fbe4` (2026-08-03) -- **8 jours**.

Le fichier etait dans le diff. N'importe quelle gate portant sur les fichiers live du diff l'aurait
vu **par construction**.

**Cout d'une telle gate, mesure sur 1706 commits non-merge (45 jours)** :

| | min | mediane | moyenne | q3 | max |
|---|---|---|---|---|---|
| fichiers live DANS le diff | 0 | **0** | 0,6 | 1 | 100 |

**1158/1706 commits (68 %) ne touchent AUCUN fichier live** -- cout nul. Au q3, 1 fichier, ~18 s.

### Trou B -- le fichier pourrit sous un changement qui ne l'a jamais touche

`test_nightshroud_combat_live.py` a ete valide **bit-exact** par `51a16cba` (2026-07-12). Depuis, il
n'a ete touche que par **deux refactors de masse** (`5fa788b7` #64 state.board, 68 fichiers live ;
`6c112458` citations par symbole, 103 fichiers live). Il est **ROUGE** au balayage du 2026-08-03.
Personne n'a introduit ce rouge dans un diff qui contenait le fichier.

**COUPABLE NOMME (#462-r4d)** : ni l'un ni l'autre de ces deux refactors -- c'est **`0ad4b9e8`
(#446-r2, 2026-08-02)**, etabli par BISSECTION (parent `2 passed`, lui `1 failed` aux valeurs
exactes du balayage). Ce commit ne touchait **aucun** fichier live : il a change un foyer PARTAGE
(`apply_pierce_and_modifiers`) en ne migrant qu'une de ses deux faces. **Le trou B n'est donc pas
theorique, et sa fenetre ici est d'UN JOUR** -- le rouge est ne le 2026-08-02 et a ete vu le
2026-08-03, par ce balayage. Ce qui l'aurait vu au plus tot : la cloture arriere du graphe
d'imports, chiffree ci-dessous.

**Cout de la gate qui le verrait** (cloture arriere du graphe d'imports, machinerie `--since` de
`probe_457`), meme echantillon :

| | min | mediane | moyenne | q3 | max |
|---|---|---|---|---|---|
| + cloture du graphe d'imports | 0 | 2 | 48,8 | **64** | 394 |

**320/1706 commits (19 %) selectionnent plus de 100 fichiers** -- soit plus d'une demi-heure de live
par PR, et **109 commits** en selectionnent plus de la moitie du parc. La queue tombe precisement
sur les commits qui touchent le coeur du moteur, c'est-a-dire ceux qui comptent.

---

## 5. La forme du garde retenue

**Ce qui est soutenable : la gate du trou A. Ce qui ne l'est pas : une gate du trou B.**

### Livre -- `--gate` (OFFLINE, entre dans la banque)

Tout fichier `*_live.py` touche par le diff doit porter une **attestation VERTE a son blob courant**
dans le ledger versionne.

* **Offline et deterministe** : la gate ne lit que git et le ledger. Ce qui coute (jouer les tests)
  est fait UNE FOIS par l'auteur, via `--run --since <ref>`, dont le perimetre est le meme.
* **Keye sur le BLOB du fichier de test, pas sur le commit.** Sur le commit, toute avancee de HEAD
  invaliderait toutes les attestations -- la gate serait inapplicable. Sur le blob, une attestation
  survit tant que le fichier ne change pas, et meurt des qu'il change.
* **Contre-epreuve** (2026-08-03) : `--gate 7b38fbe4~1` rend `rc=1` en nommant
  `tests/engine/runner/test_env_fire_tile_migration_live.py` -- c'est-a-dire le fichier de #533,
  reconnu par le mecanisme sur le commit meme ou il aurait fallu le voir. Sur `origin/master` sans
  diff, elle rend `rc=0` sans rien exiger.

### Non livre, et pourquoi

* **Gate du trou B** : refusee sur son cout (q3 = 64 fichiers, 19 % des commits > 100). Elle
  transformerait une PR de coeur de moteur en heure de live. Le substitut est le balayage periodique.
* **Shard tournant dans la banque** : refute au §1.
* **Rougir sur l'ANCIENNETE du ledger** : un cliquet qui rougit tant que personne n'a joue 1 h 50 de
  live rougirait en permanence sur `master`. Un garde qui rougit toujours est un garde qu'on
  desarme. Le ledger EXPOSE l'anciennete (`--report`) ; il ne la sanctionne pas.

### Ce que la gate ne pretend pas faire

Elle ne voit **pas** le trou B, par construction. Un fichier live inchange garde son attestation
meme si tout le moteur change sous lui -- et c'est le compromis qui la rend applicable. La dire
suffisante serait exactement la faute que ce dossier documente.

---

## 6. Residus

* **`#462-r1`** -- Le trou B reste OUVERT. Aucune gate par PR n'est abordable ; le seul instrument
  est le balayage periodique (`--run --sample N --offset K`, ~1 h 50 pour le parc). A rattacher a un
  travail hors banque.
* **`#462-r2`** -- Le ledger versionne est un point de CONFLIT : toute PR qui touche un fichier live
  y ecrit une ligne. Meme arbitrage que `ratchets-457-footprints.json`. Un conflit s'y resout par
  UNION (les cles sont des chemins, triees) -- jamais en gardant un seul cote.
* **`#462-r3`** -- L'ordre de visite par RISQUE (dernier commit le plus ancien) est un pari, pas une
  mesure : le parc est tres jeune (mediane 4,5 j, q3 6,9 j ; 317/417 fichiers touches dans la
  semaine), et cette jeunesse est en partie l'effet de 3 refactors de masse (191 touches). Un
  meilleur ordre serait << le plus longtemps sans MESURE >>, que le ledger permettra une fois peuple.
* **`#462-r4`** -- Les 8 rouges inventories sont RAPPORTES, non repares (hors perimetre de cette
  passe). Chacun est un candidat de tache a part entiere.
* **`#462-r5`** -- **FERME le 2026-08-03 par #462-r4c** (`docs/rl/case-462-r4c-imports-differes-morts.md`).
  Un import DIFFERE mort n'etait garde par rien : `probe_365` couvre << importe une cible gitignoree
  ou ABSENTE >>, ici le module existe et seul le NOM a disparu, et l'import est dans une fonction
  (donc invisible a la collecte). Le cliquet `probe_462r5_dead_imports.py` (banque) resout les
  `from X import Y` de premiere partie a l'AST. ⚠ Le perimetre reel etait de **CINQ** sites, pas
  quatre : le grep de `BUILD_HASH` ne pouvait pas voir `GHOST_EFFECT` (`probe_230.case_ghost`,
  renomme par #366-r1) -- partir du symptome borne le perimetre au symptome.
* ~~**`#462-r6`**~~ -- **LIVRE (2026-08-03)**, `case-462-r6-le-rouge-de-scenario.md`. La quatrieme
  case a un nom, porte par le TYPE de l'exception, et les trois rouges sont repares a leur cause
  (ancrage disparu / mutation masquee / ecart ferme). Le cas `damage_catalog` reste ouvert sous
  `#462-r4` -- sa correction est bornee : filtrer les candidats par `build --list-pool` avant
  d'echantillonner, avec `counterproof.assert_sample_confrontable` pour le dire.
  Deux residus neufs : `#462-r6-r1` (la detection reste au balayage periodique) et `#462-r6-r2`
  (le marquage du parc est incremental -- 3 fichiers sur 419).
