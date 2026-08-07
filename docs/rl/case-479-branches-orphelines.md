# #479 — Les branches `worktree-agent-*` orphelines : ménage, et l'audit des non-ancêtres

**2026-08-05.** Chaque agent dispatché laisse une branche `worktree-agent-<id>` ; son worktree
est auto-supprimé bien avant elle. Le gisement **se reforme à chaque campagne** — d'où un probe,
pas un one-shot : `scripts/python/probe_479_branches_orphelines.py`.

Manifeste des suppressions (une ligne par branche, avec SHA, date, sujet, verdict et **la source
qui a tranché**) : `docs/rl/manifeste-479-branches-supprimees.tsv`.

## 1. Les chiffres, re-dérivés

| | |
|---|---|
| branches `worktree-agent-*` | **184** |
| protégées par un worktree | **7** (6 agents + `master`) |
| **orphelines** | **178** |
| ancêtres d'`origin/master` | **162** — contenu littéralement dans la ref |
| **non-ancêtres** | **16** — à auditer |
| non mesurées (git muet) | **0** |

**Supprimées : 177** (162 + 15). **Gardée : 1.**

⚠ Ces chiffres bougent pendant qu'on les lit — `origin/master` a avancé deux fois pendant cette
tranche (`dad57ca4` → `ce83f48c` → `8321653b`). Les re-dériver, jamais les citer.

## 2. « Pas ancêtre » ne prouve rien — quatre critères, et aucun ne suffit seul

Un squash-merge ou un cherry-pick laisse exactement la signature « pas ancêtre ». Sur les 16,
**15 portaient un contenu déjà dans `master`** : conclure de l'historique aurait détruit 15 refs
en croyant sauver du travail, ou — pire, dans l'autre sens — en aurait gardé 16 par précaution et
n'aurait rien tranché.

| critère | ce qu'il voit | son angle mort |
|---|---|---|
| `git merge-base --is-ancestor` | l'historique | aveugle au squash **et** au cherry-pick |
| `git cherry` (patch-id) | cherry-pick, rebase | aveugle au **squash** (N commits → 1 patch-id neuf) |
| sujet relivré (`log --fixed-strings --grep`) | la relivraison sous un autre SHA | aveugle au sujet **reformulé** |
| présence **ligne à ligne** dans la ref | le contenu réel | un fichier qui a évolué depuis fait chuter le taux sans rien prouver |

Deux mesures qui l'illustrent, et qui vont **en sens inverse** :

- `afd34bf8` (FragBomb/BasiliskBarrage) : `cherry +1` (aucun patch-id équivalent), **aucune PR** —
  et `master` porte pourtant le même port sous `aa3035a1`, qui **introduit** ses trois fichiers
  neufs (`git log --diff-filter=A`). Seul le critère du **sujet** l'a vu.
- `a1d0c085` (#365) : **0 sujet relivré** (le message a été reformulé avec des guillemets
  typographiques) et **6,5 %** de présence — mais `cherry -1/1`, et `git log -S "GetDamage rend un
  ARBRE DSL"` tombe sur `8e630125`. Le taux était bas parce que la case-doc a été **réécrite
  depuis**, pas parce que le travail manquait.

Le critère qui a tranché le plus souvent reste **la PR mergée** (9 cas sur 16) ; le **commit
d'introduction** d'un fichier neuf (`--diff-filter=A`) est le plus décisif quand la PR manque.

## 3. Le tableau des 16

| branche (suffixe) | sujet | verdict | source qui a tranché |
|---|---|---|---|
| `a0c4c05c` | wip #350-r3b (slots `IAmountFormula`) | DANS MASTER | backlog **#350-r3b FERMÉ** ; la docstring master d'`AAmountFormula.calculate_average` **écarte explicitement** le seul écart (`is_range_amount`) et le justifie |
| `a0dba486` | #27-2 overrides `CalculateCustomUtility` | DANS MASTER | **PR #79 MERGED** + homonyme `8f4295cf` + `cherry -1/1` |
| `a10aaaf5` | wip #354-r1 `MyWillBeDoneOverlord` | DANS MASTER | `cherry -4/4` + **4 sujets relivrés** |
| `a143b810` | #90 abilities MoW B/C/D | DANS MASTER | **PR #77 MERGED** + homonyme `bf61e8be` |
| `a1d0c085` | #365 la seconde porte `GetDamage` | DANS MASTER | `cherry -1/1` + `log -S` → `8e630125` (sujet reformulé) |
| `a3ca8ad2` | #115 `TARGETING_OPTIONS` ×10 | DANS MASTER | **PR #126 MERGED** + homonyme `89518da9` |
| `a572d280` | passifs Genestealers | DANS MASTER | **PR #127 MERGED** + 2 sujets relivrés par `5c453899` |
| `a578b7a3` | #118 stat-mods des effets seedés | DANS MASTER | **PR #93 MERGED** + homonyme `47c8e68a` |
| **`a884d253`** | **#469-r2 admission sérialisée des banques** | **ABSENT — GARDÉE** | 3 fichiers (**1148 lignes**) absents de `master` ; **aucun** commit `#469-r2` ; **#469-r2 OUVERT** au backlog |
| `a9c06f9c` | #100 résidus AnvilShield | DANS MASTER | **PR #76 MERGED** + homonyme `9883d045` |
| `accb64ca` | Brazier / RadBombardment | DANS MASTER | **PR #128 MERGED** + 3 sujets relivrés par `825f69fe` |
| `ad832929` | #95 contributions Waaagh | DANS MASTER | **PR #75 MERGED** + homonyme `f6765ffd` |
| `ad8858d3` | wip #364 effet 1582 | DANS MASTER | `cherry -1/1` + `996bdced` « **reprise du WIP de l'agent interrompu** » (`--diff-filter=A`) |
| `ae2b1f75` | #101 `UnitFlag.Moved` | DANS MASTER | **PR #74 MERGED** + homonyme `1c091ee5` |
| `af7c9b76` | wip #350-r3a-r3 gate per-position | DANS MASTER | backlog **#350-r3a-r3 FERMÉ** ; probe repris par `65c3d413` puis mené à terme (340 → **580** lignes) |
| `afd34bf8` | FragBomb (1017) / BasiliskBarrage (1026) | DANS MASTER | homonyme `aa3035a1`, qui **introduit** les 3 fichiers neufs |

**La gardée** — `worktree-agent-a884d253a85a3b0c5`, 5 commits du 2026-08-05, tête `ce5830d4` :
sérialisation de l'admission des banques de cliquets (#469-r2). Elle porte
`scripts/python/probe_469r2_cout_concurrence.py`, `scripts/python/tests/test_469r2_admission_serialisee_offline.py`
et `scripts/ratchets-admission.ps1` — **aucun des trois n'existe dans `master`** —, plus des
modifications de `ratchets.ps1`, `ratchets-bg.ps1`, `CLAUDE.md` et de la case-doc
`case-469-mur-de-la-banque.md`. Rien n'a été relivré : le sujet est encore **ouvert** au backlog.
Cinq des sept WIP « état préservé à l'interruption réseau » ont été repris ; celui-ci non.

## 4. La protection par worktree ne peut PAS se lire sur la seule ligne `branch`

**Mesuré pendant cette tranche.** `worktree-agent-a403b7d0c9170ac76` est apparu **orphelin** entre
deux passages du probe, alors que son worktree existait, était `locked`, et que son agent
commitait (`db615aa4` → `4741e4c0` en quelques minutes).

Cause : `git worktree list --porcelain` **n'émet pas** de ligne `branch refs/heads/<x>` quand le
worktree est en **HEAD détaché** — et c'est exactement son état **pendant `git rebase`**, que la
doctrine impose à chaque agent avant d'ouvrir sa PR. Une dérivation fondée sur cette seule ligne
ouvre donc une fenêtre où la branche d'un agent en plein rebase se lit « orpheline ». Et le filet
supposé ne joue pas : `git branch -D` ne la refuserait **pas**, puisqu'elle n'est alors checkoutée
nulle part.

`branches_a_worktree()` protège donc par **deux** voies : la ligne `branch`, **et** la convention
de nom du répertoire (`.claude/worktrees/agent-<id>` ⇒ `worktree-agent-<id>`), qui survit au
détachement. Elle sur-protège légèrement — c'est le bon sens de l'erreur.

## 5. Réversibilité

Le manifeste porte le **SHA de pointe** de chaque branche supprimée : `git branch <nom> <sha>` la
restaure. Fenêtre : les objets devenus injoignables survivent au moins `gc.pruneExpire`
(2 semaines par défaut). Au-delà, deux ancrages subsistent — **`origin`** (les 162 ancêtres sont
dans `master` ; 7 des 15 autres ont une copie distante identique) et, pour les **8** dont le SHA
local n'existe nulle part ailleurs, un tag local `archive/<nom>` posé avant suppression.

La suppression **re-mesure à l'instant**, branche par branche, et refuse sur trois motifs :
protégée par un worktree, **SHA changé depuis le manifeste** (un agent aurait repris la branche),
statut d'ancêtre perdu. Mesure : **177 supprimées, 0 refusée**, puis contrôle a posteriori —
aucune branche du manifeste ne subsiste, les 6 branches à worktree et la gardée sont intactes.

## 6. Ce qui n'est PAS couvert

> ⚠ **Deux points de cette section sont RÉSOLUS depuis le 2026-08-07** — voir
> `case-479r4-critere-de-livraison-partage.md`. Le critère « pas ancêtre ⇒ à auditer » du §2
> est **outillé** : `probe_479 --pr` applique la voie PR mergée et rend, sur la même mesure,
> **16 non-ancêtres → 16 livrées par PR → 0 à auditer**. Le nettoyage distant existe
> (`nettoyer_livraison.py --distant`, DRY-RUN par défaut, manifeste versionné). Les chiffres
> ci-dessous sont ceux du 2026-08-05 : les re-dériver.

- **Les branches distantes.** `git ls-remote --heads origin "worktree-agent-*"` en rendait
  **284** le 2026-08-05, soit **100 de plus** que localement (**431** le 2026-08-07). Elles
  survivent au squash-merge. Le probe ne mesure que le local ; le nettoyage distant est un
  autre geste — désormais outillé (`--distant`), mais **jamais joué** (`#479-r5`).
- **Les worktrees de `pytest`** (`Temp/pytest-of-*/arbre*/wt`) et `Temp/ratchets-bg-wt` sont en
  HEAD détaché et ne portent aucune branche `worktree-agent-*` : hors périmètre, mais ils
  expliquent pourquoi `git worktree list` compte plus d'entrées que d'agents.
- **Aucun test ne garde ce ménage.** `probe_479` **mesure** ; rien n'empêche une future campagne
  de laisser 200 branches. Un cliquet devrait viser un **seuil d'orphelines**, ce qui est
  précisément la forme de garde qui se dégrade en silence — d'où le choix de ne pas en poser.

## Résidus

- ~~**`#479-r1`**~~ — **FERMÉ le 2026-08-07.** Les branches d'`origin` sont outillées par
  `nettoyer_livraison.py --distant` : même critère partagé, DRY-RUN par défaut, manifeste
  **versionné** écrit avant tout `push --delete`, et les PR **ouvertes** protégées par leur PR
  (pas par leur nom). ⚠ Le critère « ancêtre s'y applique tel quel » qu'annonçait ce résidu
  était **faux pour la même raison que tout le reste** : 431 branches distantes, **272**
  ancêtres, **146** livrées par la seule PR. Détail :
  `case-479r4-critere-de-livraison-partage.md` §5. Reste ouvert : `#479-r5` (l'application
  n'a jamais été jouée).
