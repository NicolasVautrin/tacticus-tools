# #547-r5 -- le ledger invalidait ses propres attestations (et #485-r2, #547-r6)

**Le geste « rejouer le ledger au merge » n'etait pas impraticable : il etait SABOTE, et par le
ledger lui-meme.** Les merges qui coutaient le plus cher etaient exactement ceux qui ATTESTENT.

## 1. La cause, en une ligne

`probe_457 --measure` ECRIT `scripts/ratchets-457-durations.json` **pendant que son audit hook
tourne encore**. Un `open` en ecriture est un evenement d'audit : l'artefact entrait donc dans
`_globales` -- « lecture non attribuable, impacte TOUS les tests ». Son repertoire, `scripts/`,
entrait alors dans `dirs_glob`, et **tout voisin** y declenchait `TOUT rejoue`. Or `scripts/`
heberge les quatre artefacts versionnes de la machinerie a cliquets :

| chemin | ecrit par |
| --- | --- |
| `scripts/ratchets-457-durations.json` | `probe_457 --measure` |
| `scripts/ratchets-457-footprints.json` | `probe_457 --measure` |
| `scripts/ratchets-457-vert-offline.json` | `probe_457` (passe ordinaire) |
| `scripts/ratchets-468-numeros-attestes.json` | `probe_468` |

⇒ **attester invalidait toutes les attestations.** L'instrument se mesurait lui-meme.

## 2. Ce que ca coutait, mesure (2026-08-10, `fda03f7b`)

`--depuis-ledger` sur le perimetre offline (298 fichiers, poids mesures) :

| ancre | AVANT | APRES |
| --- | --- | --- |
| HEAD~1 | 19 fichiers / 179 s | 19 / 191 s |
| HEAD~2 | **298 / 1780 s** (`TOUT rejoue`) | 186 / 1098 s |
| HEAD~5 | **298 / 1780 s** | 186 / 1098 s |
| HEAD~9 | **298 / 1780 s** | 274 / 1475 s |

**Le cout du ledger AU MERGE** (un commit d'ecart, les 12 derniers de `master`) :

* **APRES : 735 s de moyenne, mediane 795 s** ; 5 merges sur 12 tiennent sous **275 s** ;
* **AVANT : 1015 s de moyenne**, dont **3 merges sur 12 a 1902 s** (le perimetre ENTIER) ;
* le cas le plus net : `5ec7bab8` (`fix(#468)`, **1 seul fichier change** -- un ledger de numeros)
  passait de **9 fichiers / 131 s** a **299 / 1902 s**. Facteur **14,5**, entierement artefactuel.

**RE-MESURE APRES REBASE** sur `a9073ac5` (6 merges de plus, perimetre 303, 1903 s) -- c'est le
chiffre a citer, il porte sur l'arbre LIVRE :

* **APRES : 868 s de moyenne** ; **AVANT : 1312 s**. Facteur **1,5** ;
* **les merges qui rendaient le perimetre ENTIER passent de 5 sur 12 a 1 sur 12** ;
* le merge de CETTE PR (`a45f5068`, qui ecrit les TROIS artefacts a cliquet) : **303 / 1903 s**
  avant, **54 / 793 s** apres -- l'auto-invalidation de l'attestation a disparu ;
* **`--since origin/master` rend 54/303 pour 793 s** : c'est ce que coute le ledger a qui mergera
  cette PR.

⚠ **LE `1 SUR 12` QUI RESTE EST LE CRAN (b), ET IL EST VOULU.** `449880e8` (merge #880) AJOUTE
`scripts/declencheurs-durees.json` et `scripts/declencheurs-empreinte.tsv` -- deux fichiers NEUFS
dans le repertoire d'une globale. Le sens sur est alors de tout rejouer : un nouveau voisin PEUT
etre lu par le lecteur global (pytest, par exemple, choisit son fichier d'ini en le CHERCHANT --
un `pyproject.toml` neuf a cote de `pytest.ini` changerait la configuration de toute la passe).
Narrower serait un pari, pas une mesure.

## 3. Le correctif, deux crans

1. **`_FilesPerTest` ferme son seau GLOBAL a `pytest_sessionfinish`.** Ce que le probe ouvre dans
   son epilogue est le fait de l'INSTRUMENT, pas du depot. Rien de ce qu'une collecte, un import
   de module ou un `conftest` ouvre n'est retranche -- tout cela precede la fin de session.
   Verifie par la passe `--measure` du 2026-08-10 : **5 lectures globales -> 4**, la disparue
   etant exactement `scripts/ratchets-457-durations.json`.
2. **L'elargissement au REPERTOIRE d'une globale devient l'UNION de ses deux raisons d'etre** :
   (a) la globale est un **module du domaine** -- le regime de bytecode froid de #464-r2, ou
   l'empreinte est douteuse pour tout le repertoire ; (b) le fichier change est **NEUF**, ce que
   le code donnait deja comme justification de la granularite repertoire. Le chemin EXACT d'une
   globale, lui, est teste AVANT tout elargissement : le fichier de dette de `declencheur_guard`
   garde donc tout son effet.

⚠ **Le cran (a) n'est pas une precaution : c'est un garde VERSIONNE.** La premiere version du
correctif ne gardait que (b) et a fait rougir
`test_457_r8::test_AUCUNE_lecture_globale_n_est_retiree_a_la_lecture`, qui exige noir sur blanc
qu'un module du domaine laisse en globale **morde encore par son repertoire**. La regle a ete
re-derivee depuis la raison de ce garde, pas contre lui.

⚠ **Ce que (b) ne couvre pas** : un voisin apparu ENTRE la mesure de l'empreinte et l'ancre. Il
n'est ni dans `_globales` (il n'existait pas a la mesure) ni dans les ajouts depuis l'ancre. La
parade est le rafraichissement de l'empreinte -- pas un elargissement qui coute le perimetre.

## 4. Ce qui reste, et le verdict franc

**Ce qui reste est IRREDUCTIBLE sur l'axe actuel** : la fermeture arriere du graphe d'imports. Un
merge qui touche `engine/runner/components.py` ou `engine/entities/triggers.py` impacte
legitimement **~2/3 du perimetre** (266-270 fichiers, ~1400 s). Ce n'est pas un defaut de l'outil,
c'est la forme du depot.

**Mais le mur, lui, n'est pas irreductible -- et le blocage est nomme.** A poids mesures
(`equilibre_des_bins`) :

| selection | serie | 4 shards | 8 shards |
| --- | --- | --- | --- |
| perimetre entier (299) | 1902 s | 476 s | 238 s |
| merge median (186) | 1098 s | 275 s | 139 s |
| merge leger (9-33) | 131-248 s | 63-66 s | 63-66 s |

`_ecrire_ledger` **REFUSE d'ecrire des que `n_shards > 1`** (« chacun n'a joue que sa part et
ecraserait celle des autres »). Le mode qui rendrait le geste parallelisable existe donc a un
verrou pres : c'est le residu **#547-r7**.

⚠ **ET LE COMPTE DE `probe_547` NE RESTE PAS A 295/299 -- il n'est PAS un cliquet de fraicheur.**
Juste apres la passe : **295 / 299 VALABLES, 0 PAS MESURE**, la ou #877 mesurait **0 / 290** le
meme jour. Apres le rebase sur 6 merges : **0 / 303**, cause `une dependance MESUREE a change` --
ce qui est VRAI (ces 6 merges touchent `engine/runner/components.py`, `damage_model.py`,
`effects/base.py`). La staleness ne rougit pas, par choix DIT (#547-r2) : ce qui est exigible,
c'est que le chiffre soit LU. Ce que #547-r5 change, c'est qu'il est desormais **ATTEIGNABLE** --
avant, ecrire le ledger le remettait a 0 par construction, donc le 295/299 n'existait a aucun
instant.

**Second levier chiffre, non traite** : **12 fichiers pesent 50,6 % du perimetre** (962 s sur
1902 s), et **6 des 12 sont des META-CLIQUETS** qui rebalaient l'arbre a chaque appel
(`test_547r1` 139 s, `test_468` 63 s, `test_host_inputs` 60 s, `test_465` 54 s, `test_480r8` 53 s,
`test_485r2` 78 s). Ils declarent des perimetres larges, donc ils sont retenus par presque tout
diff : ils fixent le **plancher insecable** de 63-66 s qu'on lit ci-dessus. Residu **#547-r8**.

## 5. #485-r2 -- le faux positif etait une table de noms AVEUGLE AUX PORTEES

`probe_485r1r1` accusait `engine.utilities.sworn_protector.evaluate`, 5 acces, dans
`tests/engine/runner/test_120bis_spawn_tile_offline.py`. Le fichier lie `F` **deux fois**, dans
deux fonctions differentes : `import engine.utilities.sworn_protector as F` (ligne 108, un MODULE)
et `from ... import SWORN_PROTECTOR_AVOID_ADJACENT_ENEMIES as F` (lignes 182/199/205, un OBJET).
`migrate_485r1_barils_reexport._table_modules` construit une table PLATE du fichier : la liaison de
la ligne 108 etait attribuee aux sites des lignes 182-208.

Le correctif est un resolveur PAR PORTEE dans le foyer (`ResolveurDeModules`), a **tri-etat** :

* **module** -- la liaison resout comme module ;
* **connu NON-module** (`from x import OBJET as M`, `def M`, `class M`, `except E as M`) --
  valeur `None`, PLEINE : elle MASQUE une liaison de module d'une portee englobante ;
* **INCONNU** (parametre, affectation, cible de boucle) -- absent de la table : le nom continue de
  se resoudre plus haut, puis en **dernier recours** dans la table plate.

**Les deux crans du tri-etat sont des MESURES, pas des principes.** Rendre l'inconnu opaque
retirait **8 acces VRAIS** (un module importe puis passe en PARAMETRE HOMONYME : `adj` dans
`probe_419r1tr10r2`, `EF` dans `probe_124`, `ar` dans `probe_433_r4_r2_r1_r1`) ; supprimer le
dernier recours en retirait encore **7** (module importe dans une fonction, passe a une autre).
Etat final mesure : **5 acces retires, 0 ajoute** -- exactement les 5 faux positifs, sur 4 776.

Contre-epreuve : `tests/test_485r2_portee_des_noms_offline.py` (10 cas). Le mutant
« `resoudre` retombe sur la table plate » en fait tomber **5 sur 10**, dont l'etage de bout en bout.

## 6. #547-r6 -- deux rouges reels, et un DIAGNOSTIC FAUX

* **`test_host_inputs_offline::test_probe_273_passe`** -- la fiche accusait le regime worktree
  (« etage 3, `frida/data/_absent_273 : INTROUVABLE (pas mesure)` »). **C'etait la sortie ATTENDUE
  d'un controle qui PASSE.** La vraie cause est a l'**etape 0** : `probe_448r1r1r2r2r1_gates_amont.py`
  ecrivait son state-file dans `scripts/python/logs/`, ce que #455 interdit (la banque enumere cet
  arbre en parallele) et que `probe_273` sort en `[FAIL]`. Corrige vers `parents[2] / "logs" /
  "runners"`, la convention que 12 probes portent deja. **14 passed.**
* **`test_463r1_ecart_empreinte_offline::test_l_ecart_est_NUL_sur_ce_checkout`** -- le FANTOME
  `test_576_war_howl_pose_offline.py`. Cause structurelle : `_empreinte_fusionnee` conservait les
  anciennes entrees **sans les restreindre au perimetre**, donc `--measure-missing` ne purgeait
  jamais un fichier supprime ou renomme -- sa propre doc le constatait. Un renommage a 1 s creait
  un rouge qu'on ne pouvait eteindre qu'en payant `--measure` (2 220 s). Restriction ajoutee, de
  meme forme que `ledger_vert_offline.fusionner`.
* **Deux rouges NEUFS, trouves par la passe complete et reparés au passage** :
  `test_refresh_active_flag_discriminant_offline` (`SupaCyborkBody_CritDmgReduction` entre au port
  sans sa ligne d'attestation -- la famille « registre a cliquet » que le CLAUDE.md nomme) et
  `test_603_index_foyers_offline` (index DERIVE, regenere).

## Pointeurs

* `scripts/python/probe_457_offline_tests_green.py` -- `_FilesPerTest.pytest_sessionfinish`,
  `_ajoutes`, `impacted_files`, `_empreinte_fusionnee`
* `scripts/python/migrate_485r1_barils_reexport.py` -- `_liaisons_de_portee`, `ResolveurDeModules`
* `scripts/python/tests/test_485r2_portee_des_noms_offline.py` -- la contre-epreuve
* `docs/rl/case-547r2-attestation-qui-ne-porte-sur-aucun-arbre.md` -- le tri-etat que ce residu
  prolonge : il a MESURE le probleme (0 attestation valable sur 290) ; celui-ci en trouve la cause
