# #479-r4 / #467-r2 / #479-r1 / #467-r8 — Le critère de livraison : une cause, quatre symptômes

**2026-08-07.** Quatre résidus du nettoyage de livraison, un seul fait :

> **Le squash-merge est notre SEUL mode de merge, et il détruit l'ancestralité.**

Un squash recopie l'**arbre**, pas les commits : le tip d'une branche mergée n'est donc **jamais**
un ancêtre d'`origin/master`. Tout outil qui demande « cette branche est-elle ancêtre ? » répond
**non sur nos propres livraisons** — et du côté **muet**, donc lu comme « rien à faire ».

Le fait est **démontré**, pas cité : `probe_479r4_critere_livraison.py` étape 1 monte un dépôt,
squash-merge une branche, et vérifie que le contenu est dans `master` pendant que
`for-each-ref --merged` ne la voit pas. Avec, en contre-épreuve, un `--no-ff` qui, lui, rend
bien ancêtre — sans quoi « pas ancêtre » pourrait venir du montage.

## 1. Ce que ça coûtait, re-dérivé le 2026-08-07

| | ancêtres | livrées par PR **seulement** | ni l'un ni l'autre |
|---|---|---|---|
| branches `worktree-agent-*` **locales** (20) | **3** | **16** | 1 |
| branches `worktree-agent-*` sur **`origin`** (431) | 272 | **146** | 13 |

Le critère d'ancestralité seul voyait donc **15 %** du gisement local. Les deux outils de la
même étape du protocole se contredisaient : `nettoyer_livraison` proposait **0** suppression et
classait 14 branches « NON LIVREES — aucun gisement ne peut y toucher » (14/14 **mergées**),
pendant que `loop_status`, qui avait le rattrapage `gh`, en signalait 3. **C'est le plus prudent
qui armait le geste.**

⚠ Ces chiffres bougent à chaque campagne — les re-dériver (`probe_479 --pr`).

## 2. Le critère : `scripts/python/livraison.py`, TROIS états

```
LIVREE        une voie POSITIVE a répondu oui (ancêtre, ou PR mergée sur cette head)
NON LIVREE    les DEUX voies ont répondu, et toutes deux disent non
NON TRANCHEE  au moins une voie n'a pas conclu -- ON NE SUPPRIME RIEN, ET ON LE DIT
```

**Le négatif exige les deux voies.** C'est ce qui rend l'ajout de `gh` acceptable dans un outil
qui **supprime** : `gh` a trois pannes distinctes plus un `rc=1` qui couvre token invalide /
dépôt inconnu / erreur d'usage, que seul le stderr sépare (#467-r6). On ne supprime jamais sur
son **silence**, seulement sur son **oui**.

### La FENÊTRE SATURÉE ferme `#467-r2`

`gh pr list --limit N` rend au plus N lignes. Si le rendu **vaut** N, la fenêtre est **saturée**
et peut cacher n'importe quelle PR plus ancienne : l'absence d'une branche n'y prouve **rien**.
Elle ne conclut donc **qu'au positif**. C'est exactement le trou de `#467-r2` (« au-delà de
120 PR »), transformé en **état nommé** au lieu d'un faux négatif silencieux.

Mesure : `--limit 120` rend 120 (**saturée**) ; `--limit 2000` rend 822 pour 822 PR réelles
(**non saturée**) en 4,5 s. D'où deux réglages du **même** critère — `LIMITE_HOOK = 120` (budget
de 3 s, positifs seulement) et `LIMITE_MANUELLE = 2000` (outil manuel, négatif atteignable).

## 3. Le discriminant sûr n'est pas le NOM, c'est le WORKTREE — deux voies

`livraison.branches_protegees_par_worktree` protège par **deux** voies : la ligne
`branch refs/heads/<x>` du porcelain, **et** la convention de nom du répertoire
(`.claude/worktrees/agent-<id>` protège `worktree-agent-<id>`). La seconde a été mesurée
**deux fois, pour deux causes différentes** :

- **2026-08-05** — HEAD **détaché** : un worktree en cours de `git rebase` (l'état que la
  doctrine impose à chaque agent avant sa PR) **n'émet aucune ligne `branch`**.
- **2026-08-07** — branche **RENOMMÉE** : `worktree-agent-a209ad485d64a730e` a été proposé au
  gisement B (tip = un vieux `master`, donc ancêtre, donc « livrée ») alors que **son agent
  travaillait** — il était passé sur `agent/486r24-bypass-declare`. L'outil voyait **les deux
  faces du même agent sans les relier** : la branche neuve figurait dans sa liste `INTACT`.

C'est le **symétrique** du §1 : là l'ancestralité rendait un faux « NON LIVRÉE » ; ici elle
rend un vrai « LIVRÉE » assorti d'un faux « sans worktree ». Même cause — un critère
**structurel** employé comme critère de **propriété**.

La voie 2 sur-protège légèrement. C'est le bon sens de l'erreur.

## 4. « LIVRÉE » n'est pas « À RETIRER » (`#467-r8`)

Le protocole exige un **second terme** — « je n'ai plus rien à demander à l'agent » — qui ne se
dérive d'**aucun** état git. Il se **dépose** : un fichier `.keep-agent` à la racine du worktree,
dont le contenu est la raison. `loop_status` le retire des `nettoyables` et le publie sous
`gardes` **avec sa raison** ; `nettoyer_livraison` le refuse. Ni compteur d'avertissements ni
`--quiet` : ceux-là supprimeraient le signal au lieu de le rendre juste.

**L'attribution, elle, était dérivable depuis toujours** : `fleet_board.session_de_l_agent` lit
la session dans l'**emplacement** du transcript (`<projet>/<session>/subagents/agent-<id>.jsonl`)
— c'est le harnais qui écrit, donc c'est vrai rétroactivement et sans marque à poser. Un
worktree avait été défendu **quatre tours** sur une attribution supposée, et **fausse**.
⚠ Limite dite, pas tue : un petit-fils (un `re-expert` lancé par un solveur) remonte sous la
session **racine**. Le champ répond à « ma boucle ? », jamais à « moi directement ? ».

## 5. Le volet DISTANT (`#479-r1`) — DRY-RUN, et il le reste

`nettoyer_livraison.py --distant` applique le **même** critère aux 431 branches d'`origin`
(**418** livrées). Trois protections, dont deux que le local n'a pas besoin d'avoir :

1. **le worktree** (deux voies) — un agent en vol **pousse** sur sa branche : la supprimer la
   casserait sous ses pieds, et `origin` ne serait plus là comme filet ;
2. **la PR OUVERTE** — une branche de PR ouverte ne se distingue pas d'une orpheline sur le
   seul nom. `gh` muet ⇒ **aucune** suppression distante, quel que soit le verdict
   d'ancestralité : la protection par PR est une **condition** du geste, pas un bonus ;
3. **le manifeste VERSIONNÉ** (`docs/rl/manifeste-479r1-branches-distantes-supprimees.tsv`),
   écrit **avant** le premier `push --delete` — `logs/` meurt avec le worktree qui l'écrit.
   Résurrection : `git push origin <sha>:refs/heads/<branche>`.

L'ancestralité distante se lit sur les refs de suivi, **mais seulement si leur SHA égale celui
du serveur** ; sinon `NON TRANCHEE` (« ref périmée, `git fetch --prune` puis relancer »). Un
verdict lu sur un instantané périmé porterait sur un autre commit que celui qu'on efface.

⚠ **Le geste n'a PAS été appliqué** : quatre agents avaient une branche en vol. DRY-RUN et
rapport.

⚠ **Coût** : la version naïve (`cat-file` + `merge-base --is-ancestor` par branche) faisait
862 process pour 431 branches, soit plus de deux minutes. Deux `for-each-ref` font le même
travail en 20 s. Un outil qu'on n'ose pas lancer ne sert à rien.

## 6. La contre-épreuve : vue ROUGE avant d'être verte

`probe_479r4_critere_livraison.py` — 6 étapes, dépôts git **réels**, et une étape 6 qui
**désarme chaque cran** et exige que l'épreuve correspondante rougisse :

| mutation | ce qui doit rougir |
|---|---|
| le critère retombe sur l'ancestralité seule | `worktree-agent-sq` redevient invisible |
| la saturation n'est plus dérivée | une fenêtre pleine conclut à tort au négatif |
| la protection retombe sur la voie 1 | la branche **renommée** redevient supprimable |
| une fenêtre muette passe pour mesurée | le `NON TRANCHEE` devient un `NON LIVREE` |

Un cliquet qu'on n'a jamais vu rouge peut garder une propriété que le code satisfait pour une
tout autre raison.

⚠ **Et il assertionne son propre non-vide** : « `sq` n'est pas dans `merged` » serait vrai même
si le glob ne voyait rien du tout — un test **vide** passerait pour un vert. Un témoin vérifie
d'abord que le glob voit bien la branche **sans** `--merged`.

## 7. Ce qui n'est PAS couvert

- **Le geste distant n'a jamais été JOUÉ** (`--appliquer`). Le DRY-RUN, le manifeste et les
  protections sont testés ; le `push --delete` lui-même ne l'est que par lots dans le code.
- **La fenêtre reste bornée.** Si le dépôt dépasse `LIMITE_MANUELLE`, elle saturera — l'outil
  le **dira** et cessera de conclure au négatif, mais le gisement redeviendra partiellement
  invisible. `trancher_par_pr_ciblee` (`--head`, 1,4 s/branche) est la voie qui ignore la
  fenêtre ; elle est **écrite et non câblée**, faute de lot assez petit pour la justifier.
- **`loop_status` ne dit pas « MA boucle ».** Il publie la session mesurée ; il ne connaît pas
  la sienne, donc il ne peut pas comparer. Le rapprochement reste à l'orchestrateur.
- **Aucun cliquet ne garde le VOLUME.** Rien n'empêche une campagne de laisser 400 branches
  distantes : la garde serait un seuil, et un seuil se dégrade en silence.

## Résidus

- **`#479-r5`** — Le `push --delete` distant n'a jamais été joué en vrai : le DRY-RUN, le
  manifeste et les trois protections sont sous contre-épreuve, l'application ne l'est pas
  (elle exige un `origin` jetable, montable — `probe_467r4_scene_git_reelle` en monte déjà un).
  **FOYER:** `scripts/python/nettoyer_livraison.py`, `scripts/python/probe_479r4_critere_livraison.py` — **BLOCAGE:** `aucun`
