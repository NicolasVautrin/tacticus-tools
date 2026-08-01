# case-439 — un cliquet doit pouvoir ROUGIR, et ça se garde mécaniquement

**L'artefact** : `scripts/python/probe_439_cliquet_peut_rougir.py`, entré dans la banque.
Il répond, pour **chaque entrée** de `scripts/ratchets.ps1`, à « celle-ci PEUT-elle rendre un
code de sortie non nul ? ».

## 1. Le fait

Trois occurrences du gisement, **toutes trouvées à l'œil** :

| # | Cliquet | Forme | Trouvé par |
|---|---|---|---|
| 1 | `probe_181` | `main` calculait les manquants puis `return 0` **inconditionnel** | #430 — mesuré : renommer un `TARGETING_OPTIONS` le laissait **VERT** tout en IMPRIMANT le trou |
| 2 | `probe_326` | même forme ; il INVENTORIE les verdicts, il n'en rougit d'aucun | #435 — c'est pour cela que `test_337` (et pas lui) est entré dans la banque |
| 3 | — | l'audit **manuel** de #430 sur les 13 scripts d'alors n'avait trouvé que le n° 1 | il a donc **raté le n° 2** |

La ligne 3 est le point : *un audit ponctuel ne tient pas ce critère*. `case-430` §8 le nommait
déjà comme résidu — « ce résidu n'est toujours pas gardé automatiquement, il a été vérifié à la
main ici, une **troisième** fois ».

## 2. Le critère

Est exigée au moins une sortie **ENTIÈRE non nulle** : `return <N>`, `sys.exit(<N>)`,
`raise SystemExit(<N>)`, `assert` — ou la même chose portée par une variable/appel dont la
nullité n'est pas prouvable. Deux exclusions, l'une et l'autre motivées :

- **`raise SystemExit("<message>")`** (valeur = chaîne) ne compte pas : c'est une garde
  d'**entrée**, pas un verdict. C'est exactement ce qui sépare un cliquet sain de `probe_326`.
- **une exception ordinaire** (`raise RuntimeError`) non plus : tout script en lève une sur une
  entrée cassée, donc l'admettre reviendrait à déclarer sain n'importe quel inventaire.

L'analyse est une **interprétation abstraite** du point d'entrée sur `{Z, N, S, U}`, avec
propagation des variables locales, des `AugAssign`, des branches et des boucles, et résolution
des appels intra-module.

## 3. Les formes de sortie — inventoriées, pas supposées

Le brief en nommait deux ; le balayage les re-dérive **à chaque passage** (ligne « formes de
sortie non nulle EN USAGE »), donc une forme neuve se voit sans relire les 22 scripts.
Mesure du 2026-08-01 : `assert x3, raise SystemExit x8, return x17, sys.exit x9` (une entrée
peut en cumuler plusieurs).

Deux formes auraient produit un **faux rouge** avec un balayage naïf de `return <non nul>` :

- **`probe_365`** porte son échec par `rc = 1` puis `return rc` — jamais un littéral ;
- **`probe_120`** ne rougit **que** par `assert` : son `main` rend `0` en toutes circonstances.
  Réserve inscrite dans le probe : `python -O` désarme les `assert` ; la banque lance `python` nu.

Les entrées **pytest** (`pytest_signatures`, `pytest_attestations`) sortent par le rc de pytest,
pas par un `return` : elles ne sont pas exemptées, elles sont jugées sur l'**équivalent** du
critère — au moins une fonction `test_*` **et** au moins un site de faute (`assert`,
`pytest.fail`, `raise`) dans l'une d'elles. Un fichier de tests sans site de faute est le même
inventaire-qui-ne-rougit-pas sous une autre forme. Toute **autre** forme d'invocation est ROUGE :
elle doit venir se déclarer, jamais être exemptée en silence.

## 4. La granularité est l'ENTRÉE de banque, pas le fichier

`probe_283` entre en **six** étapes qui partagent un `main`. Le probe lit l'`argparse` du script,
fixe les `args.<dest>` que l'`Argv` de l'entrée détermine, et **élimine** les branches alors
fausses. Conséquence mesurée : `--step diff` est prouvé incapable de rougir (il n'alimente aucun
`ko`) là où `--step mirror` l'est. Sans cela les six auraient hérité du verdict du fichier.

Ces deux compteurs portent désormais **`Rougit = 'compteur'`** dans la banque — une déclaration
**machine** au lieu de la prose de #430. Les deux directions sont gardées (règle #426) :

- entrée **sans** déclaration qui ne peut pas rougir → ROUGE (le vice de #430/#435) ;
- entrée **déclarée** compteur qui **peut** rougir → ROUGE, *déclaration MORTE*. C'est le
  « pour qu'un futur `ko +=` sur eux soit vu » que `ratchets.ps1` appelait de ses vœux ;
- entrée dont le script / le fichier de test n'existe plus → ROUGE, *entrée MORTE*.

## 5. La liste se DÉRIVE (règle #421) — deux fois, et l'accord est prouvé

Aucune liste saisie. Source A = **exécution** `pwsh -File scripts/ratchets.ps1 -List` (ids,
`Rougit`, doc) ; source B = **parse textuel** du même fichier (ids, `Argv` élément par élément,
donc sans le découpage par espaces qu'imposerait la colonne `commande`). `A \ B` et `B \ A`
doivent être vides toutes les deux. Si la banque ne peut pas être dérivée (pas de `pwsh`,
`-List` en erreur), le probe le **DIT** et rend 1 — il ne rend jamais 0 faute d'avoir su lire.

## 6. Le garde s'auto-éprouve, à chaque passage

Un garde-fou dont le verdict dérive ne vaut rien (leçon de `probe_319` sur `probe_273`), et ici
la dérive serait **muette** : l'analyse rendrait « capable » pour tout le monde et la banque
resterait verte. Neuf formes réelles, prises sur des cliquets existants, sont soumises à
l'analyseur **avant** la banque, avec leur verdict attendu **dans les deux sens** — 3 attendues
défaillantes, 6 attendues saines. Deux d'entre elles partagent la **même source** et ne diffèrent
que par leur `Argv` : c'est la preuve exécutable du §4.

## 7. Contre-épreuves — mutation vérifiée AVANT lecture du verdict

Sur une contre-épreuve, **VERT est le résultat suspect** : chaque mutation est relue dans
`-List` avant qu'on lise quoi que ce soit du probe.

| Mutation | Verdict |
|---|---|
| **cliquet factice** `probe_999_factice_muet.py` (`return 0` inconditionnel) ajouté à la banque, **run complet** (jamais `-Only`) | `rc 1`, banque ROUGE 1/23, `probe_439` nommé, et **le fautif nommé dans l'extrait** : `ROUGE probe_999factice — toutes les voies de sortie sont NULLES ou des gardes d'entrée` |
| `Rougit = 'compteur'` posé sur `probe_181` (qui, lui, peut rougir) | `rc 1` — `DÉCLARE 'compteur' mais PEUT rougir — déclaration MORTE` |
| valeur de déclaration inconnue (`Rougit = 'jamais'`) | `rc 1` — `déclaration 'rougit' inconnue` |
| `Argv` remplacé par `node garde.js` | `rc 1` — `FORME D'INVOCATION INCONNUE` |
| script renommé (`probe_120_renomme_ailleurs.py`) | `rc 1` — `script INTROUVABLE (entrée MORTE)` |
| entrée visible du **texte** seul (bloc `@{ Id = 'zombie'` en commentaire) | `rc 1` — `COUVERTURE : texte \ exécution : zombie` |
| script à la syntaxe cassée | `rc 1` — `source ILLISIBLE (ligne 1) : invalid syntax`. Une analyse qui échoue rend un verdict **indéterminé**, jamais un vert par défaut |

Le premier passage a trouvé **un défaut réel dans la banque** : les lignes de faute de `probe_439`
ne passaient pas le motif `$rxFail` de `ratchets.ps1`, si bien que l'extrait affichait
« 1 entrée(s) » **sans nommer laquelle**. Les lignes sont désormais ancrées sur `ROUGE`.
Le factice et l'entrée temporaire ont été retirés ; l'arbre est revenu à un `git diff` propre.

## 8. Ce que ce cliquet NE garde PAS — mesuré, imprimé à chaque passage

**« peut rendre un code non nul » n'est PAS « rougit sur son gisement ».** `probe_326` le
prouve : sa valeur de retour est bien un `return 0` inconditionnel (voies non nulles de la
famille return/exit : **0**), mais il porte un `assert sum(tot.values()) == len(rows)` — un
invariant **interne** de son propre comptage — donc il **peut** rendre 1 sans jamais rougir d'un
verdict. La fonction `limite_du_critere()` re-mesure ce cas et l'imprime à chaque passage, pour
qu'on ne lise jamais ce probe comme plus fort qu'il n'est.

Le second critère se garde autrement : par un **test du gisement** (pour `probe_326`, c'est
`test_337`, entré dans la banque par #435). Reste ouvert : rien ne garantit mécaniquement qu'un
cliquet capable de rougir rougisse **sur ce qu'il prétend mesurer** — c'est le résidu `#439-r1`,
inscrit au backlog.

Deux autres limites, assumées et inscrites dans l'auto-épreuve pour rester visibles :

- **un appel hors module n'est pas résolu** — `return verifier()` où `verifier` est importé est
  classé CAPABLE. On ne rougit que sur **preuve** d'impossibilité ; l'inverse ferait de ce cliquet
  un générateur de faux rouges, et c'est le plus sûr moyen de faire désactiver un garde-fou.
- **le raffinement par `Argv` ne porte que sur les conditions décidables** (`args.<dest> ==` /
  `in` / truthiness). Une étape sélectionnée autrement — dispatch par table, `getattr` — retombe
  sur la granularité du fichier. Aucune entrée de la banque n'est dans ce cas au 2026-08-01.

## 9. Coût

`probe_439` seul : **5,9 s**. En parallèle il disparaît sous le mur — coût marginal nul, le
critère d'admission. Banque **verte 22/22**, deux fois : mur **111,7 s** machine calme (tenu par
`probe_319`), puis **170,8 s** au re-jeu **après rebase** sur `origin/master` (+5 commits, #438),
sous la charge des autres agents. ⚠ Chiffres à re-dériver, pas à citer.

## 10. Fichiers

| quoi | où |
|---|---|
| le cliquet | `scripts/python/probe_439_cliquet_peut_rougir.py` |
| la banque (champ `Rougit`, colonne `rougit` de `-List`, entrée `probe_439`) | `scripts/ratchets.ps1` |
| le résidu qu'il ferme | `docs/rl/case-430-banque-de-cliquets.md` §8 |
