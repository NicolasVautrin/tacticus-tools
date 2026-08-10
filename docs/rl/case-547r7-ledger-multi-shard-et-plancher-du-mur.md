# #547-r7 / #547-r8 -- le ledger sait s'ecrire en MULTI-SHARD, et le mur a un PLANCHER

Deux residus, un meme objet : le cout de rejouer le vert offline. Le premier levait un verrou
d'ECRITURE, le second cherchait un levier de CALCUL. Le premier est livre ; le second est
**instruit et sa piste principale est REFUTEE PAR MESURE**.

## 1. #547-r7 -- ce que le refus protegeait n'etait pas ce qu'il interdisait

`probe_457._ecrire_ledger` refusait toute ecriture des que `n_shards > 1` :

> `%d shards = autant de processus concurrents sur un fichier VERSIONNE ; chacun n'a joue que sa
> part et ecraserait celle des autres.`

**La lecture du risque etait JUSTE**, et elle le reste : huit `read-modify-write` sur un meme JSON
perdent des ecritures, et chaque shard ne connait que sa part -- il ecrirait donc un ledger ampute
des 7/8 restants. Le refus n'etait pas de la prudence decorative.

Mais ce qu'il protegeait, c'est **l'ecriture CONCURRENTE du fichier versionne**, pas
« l'ecriture multi-shard ». La distinction est tout le correctif : chaque shard depose une **PART**
sous `logs/ratchets/457-ledger-parts/`, **un fichier par `(jeton, n, k)`** -- donc DISJOINT, donc
**aucune course** -- et un seul processus ecrit le fichier versionne (`--consolider-ledger`).

**Supprimer la course plutot que la serialiser** : pas de verrou, donc rien a liberer si un shard
meurt. C'est ce qui rend le mecanisme sur sans ajouter d'etat a nettoyer.

### Le jeton de run est OBLIGATOIRE, et c'est le cran qui ferme le faux vert

Une part qui traine sans identite de run porte des verts gagnes sur un **AUTRE arbre**. Les
consolider serait le faux vert exact que `#465` interdit -- et il serait **silencieux**, puisqu'un
vert au ledger fait SAUTER le test.

`parts_retenues` est le foyer unique du refus, sur **trois criteres dont aucun n'est redondant** :

| critere | ce qu'il attrape, et que les autres ne voient pas |
| --- | --- |
| `_jeton` | deux passes lancees au MEME `HEAD` sur le MEME arbre (rejeu apres interruption) |
| `_head` | un jeton recycle a la main ; il dit sur quel commit la part a ete gagnee |
| `_perimetre_sha` | l'arbre qui BOUGE pendant le run (fichier de test ajoute/retire entre deux shards) |

Le troisieme n'est pas du zele : consolider avec un perimetre different de celui qu'ont vu les
shards ferait EFFACER par `fusionner(perimetre=...)` des attestations qu'aucun d'eux n'a remises
en cause.

Sans jeton, `_ecrire_ledger` ne depose RIEN et le dit -- le refus historique tient donc toujours
pour qui lance des shards a la main.

### Le bug que la relecture n'aurait pas trouve

`--jobs` posait le jeton dans l'environnement de ses **ENFANTS** et consolidait dans le **SIEN**.
Resultat : `CONSOLIDATION IMPOSSIBLE` a la fin de CHAQUE passe -- les shards attestaient, personne
ne fusionnait. Le probe l'a rendu visible d'un chiffre (**8 entrees en mono, 0 en multi**) ; aucune
lecture du diff ne le montrait. Le jeton passe desormais en argument explicite.

## 2. La contre-epreuve : une acceleration qui change un verdict est un bug

`probe_547r7_ledger_multi_shard.py` monte un depot git JETABLE (tmpdir systeme), joue la passe
MONO puis, **apres avoir SUPPRIME le ledger** (sinon une part perdue serait invisible -- l'entree
de la passe mono survivrait a la fusion), la passe `--jobs 4`, et confronte les deux ledgers
**entree par entree**.

* **8 entrees, 11 champs compares par entree** : `_base`, `_blob`, `_commit`, `_depuis`, `error`,
  `failed`, `messages`, `passed`, `skipped`, `verdict`, `xfailed` -- **identiques**.
* **EXCLUS, et imprimes** : `_at` (deux passes ne partagent pas leur instant) et `sec` (ni leur
  chronometre). Une exclusion muette serait la porte par laquelle une divergence reelle passerait.
* **Les 4 verdicts sont couverts** -- `VERT` 5, `ROUGE` 1, `VIDE` 1 (tout skippe, garde `#455`),
  `SETUP` 1. L'etape ASSERTIONNE cette couverture : un accord mesure sur des verts seuls serait un
  accord en **regime DEGENERE**, incapable de separer « meme mecanisme » de « cas facile ».
* Les trois refus MORDENT (part fabriquee portant un `VERT` sur le fichier que l'on sait ROUGE) et
  **le ledger versionne ne bouge pas** -- l'artefact est verifie, pas seulement le compte-rendu.

Le test-garde `tests/test_547r7_ledger_multi_shard_offline.py` (**14 cas, 1,2 s**) tient le
cartesien des trois criteres (**36 combinaisons, 1 seule retenue**, anti-vacuite assertionnee), la
disjonction des ecritures, la restriction au perimetre et l'abandon d'un fichier atteste par deux
shards.

## 2bis. Le bug que le multi-shard a REVELE : l'impact etait juge par l'UNION des ancres

Le mecanisme livre ci-dessus ne rendait presque RIEN, et ce n'etait pas sa faute. Mesure prise
juste apres la premiere passe `--jobs 8` qui venait d'attester 282 fichiers :

    --depuis-ledger : 282/306 fichier(s) SANS vert atteste valable  [~1474 s]

Attester ne servait donc a rien -- **la meme phrase que #547-r5**, a un autre etage. La cause est
dans `ledger_vert_offline.a_rejouer` : il calculait l'impact **par ancre**, puis en prenait
**l'UNION**, et appliquait cet ensemble a **TOUS** les fichiers :

| ancre | entrees qui la portent | fichiers impactes depuis elle |
| --- | --- | --- |
| `15fc2a4c` (fraiche, la passe qui vient de finir) | 282 | **9** |
| `0d6283b6` (ancienne) | 24 | **282** |

⇒ **24 vieilles entrees peremaient les 282 qu'on venait de gagner**, dont ~273 a tort. Un fichier
atteste a une ancre RECENTE etait declare impacte parce qu'un AUTRE fichier, atteste a une ancre
ANCIENNE, l'etait.

Le correctif juge l'impact **par ancre** : un fichier est impacte si **SON** `_depuis..HEAD` le
dit. Ce n'est pas un assouplissement -- c'est l'application LITTERALE de la cle de validite ecrite
en tete du module (« le fichier ne doit pas etre IMPACTE par le diff `_depuis..HEAD` »), `_depuis`
etant le sien et non celui d'un voisin. Une panne de mesure sur une ancre ne fait rejouer que
**ses** fichiers, et le dit.

**AVANT / APRES, sur le meme arbre, a la seconde pres :**

| | fichiers a rejouer | cout annonce | attestations valables |
| --- | --- | --- | --- |
| union des ancres | 282 / 306 | 1474 s | **24 / 306** |
| par ancre | **11 / 306** | **135 s** | **295 / 306** |

La contre-epreuve est EXERCEE, pas supposee : la mutation qui remet l'union fait tomber
`test_l_impact_d_une_VIEILLE_ancre_ne_CONTAMINE_pas_une_attestation_FRAICHE` (1 failed / 15
passed), et le retrait de la mutation le fait remonter (16 passed).

⚠ **Ce bug preexistait a #486-r23 ; ce qui l'a rendu VISIBLE, c'est d'avoir enfin une passe qui
atteste en masse.** Tant que le ledger n'etait rafraichi que par bribes, toutes les entrees
partageaient a peu pres la meme ancre et l'union ne se distinguait pas du par-ancre.

## 3. #547-r8 -- la piste du residu, MESUREE puis REFUTEE

Le residu proposait : « un balayage d'arbre peut-il etre MEMOISE entre fichiers de test d'une meme
passe (cache de session pytest) ? Quatre d'entre eux recalculent le MEME recensement de
`scripts/python/**` ». `probe_547r8_concentration_du_mur.py` mesure les deux faits supposes.

**(a) Un cache de SESSION est intra-PROCESSUS, et les lourds sont separes par construction.**
`bins_of` (LPT) place le plus lourd d'abord, toujours dans le paquet le moins charge. Mesure a
8 shards : les **12 lourds occupent 8 shards DISTINCTS**, dont **4 ou ils sont SEULS**. Le cache
de session ne peut rien partager entre eux -- quelle que soit sa qualite. La memoisation intra-passe
est donc **antagoniste du sharding** livre en #547-r7, pas complementaire.

**(b) Quatre des six meta-cliquets NE SONT PAS des balayeurs.** L'empreinte mesuree dit combien de
repertoires chaque fichier ouvre reellement. Quatre lourds en ouvrent **moins de 10** :

| fichier | poids | repertoires ouverts | ou va le temps |
| --- | --- | --- | --- |
| `test_547r1_...` | 139,1 s | **2** | deux montages de **worktree git** + sous-processus |
| `test_468_...` | 62,8 s | **4** | 8 sous-processus (`git log`, `git grep`) |
| `test_host_inputs_...` | 60,0 s | **0** | sous-processus |
| `test_465_...` | 54,0 s | **1** | sous-processus (`probe_462`) |

**316 s, soit 16,6 % du perimetre entier, qu'AUCUN cache de balayage n'atteindra** -- et le
premier d'entre eux est le PLANCHER lui-meme.

⚠ **Ce que la mesure ne tranche PAS, et qui est dit** : `dirs` compte les lectures d'IMPORT au
meme titre que celles d'un balayage. Les **33 couples sur 55 a recouvrement >= 90 %** ne prouvent
donc **aucun** balayage commun -- deux fichiers qui importent `engine` partagent ses ~35
repertoires sans que l'un refasse le travail de l'autre. Le seuil de 10 dit ce qu'il ecarte
(**8 lourds non tranches ici**).

## 4. Ou est vraiment le mur, et ce qui le franchit

Mur simule sur les poids mesures (`bins_of`, perimetre entier : **304 fichiers, 1903 s**) :

| shards | mur | ideal (charge/N) | ce qui decide |
| --- | --- | --- | --- |
| 1 | 1903 s | 1903 s | la CHARGE |
| 4 | 476 s | 476 s | la CHARGE |
| 8 | 238 s | 238 s | la CHARGE |
| **16** | **139 s** | 119 s | **le PLANCHER** |
| 32 | 139 s | 59 s | le PLANCHER |

**Deux conclusions chiffrees, et elles se suffisent :**

1. **Entre 8 et 16 shards il reste 99 s a prendre, sans toucher a AUCUN cliquet** -- le mecanisme
   de #547-r7 le permet deja (`--jobs 16`). C'est le levier le moins cher, et il n'a aucun cout de
   fidelite : la partition est deterministe et le ledger consolide est identique.
2. **On ne descend pas sous 139 s sans abaisser `test_547r1` lui-meme**, dont le cout est
   **deux montages de worktree git**, pas un balayage. Et l'abaisser ne rendrait que jusqu'a
   **128 s** (`test_enum_ordinal_ratchet`) : le plancher n'est pas un fichier, c'est une **plage**.

Le levier restant n'est donc ni un cache de session ni un recensement partage : c'est la
**mutualisation du worktree temoin** entre les etages qui en montent un. Il n'est pas instruit
ici -- residu **#547-r9**.

## Pointeurs

* Mecanisme : `scripts/python/ledger_vert_offline.py` (section PARTS / MULTI-SHARD),
  `scripts/python/probe_457_offline_tests_green.py` (`_ecrire_ledger`, `_consolider_ledger`,
  `_lancer_jobs`).
* Mesure : `scripts/python/probe_547r7_ledger_multi_shard.py`,
  `scripts/python/probe_547r8_concentration_du_mur.py`.
* Garde : `scripts/python/tests/test_547r7_ledger_multi_shard_offline.py`.
* Amont : `docs/rl/case-547r5-le-ledger-invalidait-ses-propres-attestations.md` (le chiffrage qui
  a ouvert les deux residus), `docs/rl/case-486r23-ledger-du-vert-offline.md` (le ledger lui-meme).
