# #479-r5 — le geste distant joué, et le défaut d'argument qui l'avait rendu inéprouvable

`nettoyer_livraison --distant` applique le critère partagé aux branches d'`origin`. Le DRY-RUN,
le manifeste versionné et les trois protections étaient sous contre-épreuve ; l'**application**,
non — personne n'avait jamais vu `git push origin --delete` partir depuis cet outil.

## 1. La cause racine — un défaut d'argument, sur la seule fonction qui supprime

```python
def git(*args: str, cwd: Path = REPO)      # ❌ évalué à l'IMPORT : la racine est FIGÉE
def git(*args: str, cwd: Path | None = None)   # ✅ REPO lu au moment de l'APPEL
```

Le module était donc **insubstituable** : toute contre-épreuve qui croit viser une scène jetable
vise en réalité le **vrai** dépôt. C'est exactement pourquoi ce geste n'avait jamais été éprouvé.

Ce dépôt documente déjà cet idiome ailleurs (`probe_486r12`, `Empreinte.chemin=None` : « une
valeur par défaut est évaluée À L'IMPORT, donc elle FIGE le chemin et rend `EMPREINTE`
insubstituable »). La faute vivait sur la **seule** fonction du dépôt qui porte `push --delete`.

## 2. L'incident, rapporté en entier

La première tentative a substitué `NL.REPO`, cru viser un `origin` monté par `git init --bare`,
et adressé le **vrai** `origin` : le recensement a rendu les branches réelles et le
`push --delete` est parti. Bilan **établi après coup**, pas supposé :

- toutes les branches supprimées étaient **ancêtres d'`origin/master`** — leur contenu est
  intégralement dans `master` (vérifié : 171 branches `worktree-agent-*` restantes, dont
  **0 ancêtre**) ;
- **0 PR ouverte** à cet instant, donc aucune PR n'a perdu sa branche (vérifié par `gh`) ;
- les branches des agents **en vol** ont été protégées par la voie worktree — qui, elle, tournait
  bien contre le vrai dépôt — et leurs refs locales sont toutes intactes ;
- le manifeste avait été redirigé vers le tmp et a disparu avec lui : le filet n'a **pas** joué,
  et c'est la seule perte réelle — la trace, pas le contenu.

Aucune perte de contenu, mais un geste irréversible joué hors mandat.

## 3. Le garde est par CONSTRUCTION, pas par discipline

`probe_479r4._exige_scene_jetable` demande au module **lui-même** quel `origin` il joindrait
(`NL.git("remote","get-url","origin")`) et refuse si ce n'est pas sous son `tmp`.

**Interroger le module plutôt qu'inspecter ses attributs est le point** : une substitution qui ne
mord pas est invisible d'une inspection d'attributs, elle ne l'est pas d'un appel. C'est
« vérifier que la MUTATION a mordu », appliqué à un geste irréversible — sauf qu'ici le prix d'un
vert qui ment n'est pas un faux verdict, c'est une suppression.

Un **second** garde porte sur le résultat : le recensement ne doit rendre que des branches de la
scène. Deux crans indépendants pour un geste irréversible.

## 4. Ce que l'étape 7 joue

Un `origin` jetable à quatre branches, **une par verdict** : `livree` (supprimée), `ouverte`
(PR OUVERTE → protégée), `montee` (worktree → protégée), `en-vol` (non mergée → NON LIVRÉE).

Elle vérifie que le manifeste est écrit **avant**, que le `push --delete` agit **réellement**, que
les trois autres sont **intactes** — *ce qu'un geste irréversible épargne compte autant que ce
qu'il supprime* — et que la **résurrection** depuis le seul manifeste fonctionne : sans elle, le
filet ne serait qu'une trace. Puis `gh` **muet** : aucune suppression, pas même sur un ancêtre, et
la cause nommée branche par branche.

**Témoin non nul du garde** : *avant* substitution, le module vise le vrai `origin` et le garde
refuse en **nommant** la cible — la configuration exacte de l'incident, et la preuve que ce cran
l'aurait arrêtée.

## 5. Ce qui reste ouvert

Le geste n'a **jamais** été joué sur le vrai `origin` de façon délibérée, et cette tranche ne le
propose pas : c'est un arbitrage d'orchestrateur, à faire hors fenêtre d'agents en vol.

**Cliquet** : `python scripts/python/probe_479r4_critere_livraison.py` — étape 7.
