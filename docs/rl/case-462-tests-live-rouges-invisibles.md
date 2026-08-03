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

### Ce qui EST exhaustif et abordable : la collecte

`--collect` joue `--collect-only` sur les 533 fichiers : **aucun runner monte**.
Mesure du 2026-08-03 : **36,8 s, rc=0, 3677 tests collectes, 0 erreur**.
La categorie HARNAIS/COLLECTE est donc **VIDE au niveau import** sur la totalite du parc -- et cette
affirmation-la, contrairement au reste, porte sur 417/417 fichiers.

---

## 2. L'inventaire

Balayage du 2026-08-03, 4 workers, ordre de visite par RISQUE (dernier commit le plus ANCIEN
d'abord). Chaque tranche fusionne dans le ledger.

<!-- INVENTAIRE -->

### Ce qui n'est PAS couvert

* Les fichiers ECARTES du balayage (voir le compte ci-dessus) : leur statut est **INCONNU**, pas
  vert. Le ledger le dit fichier par fichier ; `--report` imprime l'anciennete de chaque mesure.
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

Le probe ne CLASSE pas : il ne peut pas. Il rapporte le symptome VERBATIM ; la ventilation est un
acte de lecture.

<!-- VENTILATION -->

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
* **`#462-r4`** -- Les rouges inventories sont RAPPORTES, non repares (hors perimetre de cette
  passe). Chacun est un candidat de tache a part entiere.
