# Cartographie DSL -- phase 1 : le graphe d'usage « primitive <-> ability »

> Fiche de METHODE et CONTRAT. Les donnees, elles, sont **generees** :
> `docs/rl/dsl-usage-map.md` (lisible) et `docs/rl/dsl-usage/*` (machine).
> En cas de conflit au rebase sur ces fichiers generes : **REGENERER**, ne pas fusionner.

## Le critere

> Pour chaque primitive DSL du build, sait-on dire QUELLES abilities / effets la
> composent -- et, pour une ability donnee, quel vocabulaire elle emploie ?

Avant : non. Le vocabulaire etait **classe** (`dsl-effect-nodes.md`, la question « ce noeud
est-il DSL ou imperatif ? ») mais son **graphe d'usage** n'existait nulle part. On ne pouvait
donc pas repondre a la seule question qui oriente le portage : *quelle primitive non portee
debloque le plus d'abilities ?*

Apres : oui, sur l'axe COMPOSITION, avec **11 180 aretes** mesurees reliant **609 primitives**
a **1 203 proprietaires**.

## Comment (et pourquoi c'est fiable)

Les primitives sont les methodes des fabriques statiques du DSL ; une ability compose son
arbre en les APPELANT. Le graphe d'usage est donc exactement l'ensemble des **xrefs entrantes
de type CALL** vers ces fabriques, et le nom de classe du site appelant donne le proprietaire.

Regeneration integrale (idempotente, ~10 s) :

```
python scripts/python/dsl_xref_map.py all        # scan ghidra-mcp + report
python scripts/python/probe_dsl_xref_crosscheck.py --sample 40 --seed 7
```

Le scan verifie d'abord que `ghidra-mcp` sert bien le build de `data/symbols/CURRENT` et
**s'arrete** sinon : citer les symboles d'un binaire pour un autre produit du travail a jeter
sans le savoir.

### Ce qui rend la mesure autre chose qu'une source qui se valide elle-meme

Tout le graphe vient d'UNE source (les xrefs Ghidra). Une source unique est coherente meme
quand elle est biaisee. On la recoupe donc par une source **independante** -- le texte du
decompile plus la liste `callees` -- via `probe_dsl_xref_crosscheck.py` :

* **40 / 40 sites en accord total** (seed 7), **0** citation du texte absente de la carte,
  **0** arete absente du texte. Aucune sur-attribution, aucun manque sur l'echantillon.

**Ce que cet accord ne prouve PAS** : un appel **inline** par le compilateur est invisible
des DEUX cotes. L'accord borne le biais *entre lectures*, il n'etablit pas l'exhaustivite.

## Le contrat MACHINE (chemins stables -- une phase avale les cite)

Le markdown est un rendu humain : **ne pas le parser**. Le contrat, c'est :

| fichier | une ligne par | schema declare |
|---|---|---|
| `docs/rl/dsl-usage/dsl-usage-edges.tsv` | **arete** primitive -> site | en-tete `#` |
| `docs/rl/dsl-usage/dsl-usage-primitives.tsv` | **primitive** (+ couverture) | en-tete `#` |
| `docs/rl/dsl-usage/dsl-usage-owners.tsv` | **proprietaire** | en-tete `#` |
| `docs/rl/dsl-usage/dsl-usage.json` | manifeste : schema, comptes, `coverage_axes` | JSON |

`schema_version = 1.0`. Chaque TSV porte en tete son build, ses colonnes, le vocabulaire
`coverage` et `scan_complete`. Le brut non versionne (`logs/dsl_xrefs_raw.json`) meurt avec le
worktree et se regenere.

### `coverage` : TRI-ETAT, et il se lit sans deviner

| valeur | signification |
|---|---|
| `measured` | au moins un site appelant **nomme** |
| `measured_empty` | a repondu, **aucune** xref CALL entrante |
| `callers_anonymous` | des appels entrent, mais l'appelant n'est **pas nomme** |
| `not_measured` | requete non aboutie / primitive non parcourue |

`measured_empty` ne dit **pas** « inutilisee » : le corps peut etre inline, deduplique, ou
n'etre atteint que par du code non nomme. La formule juste est **« aucun xref nomme »**.
`not_measured` ne doit jamais etre confondu avec `measured_empty` -- c'est pourquoi ce sont
deux valeurs et non un booleen.

**L'etat NON MESURABLE est un etat d'AXE, pas de primitive** : il vit dans
`coverage_axes` du manifeste, jamais dans la colonne `coverage`.

## Etat de ce tirage (build `rnca9r7q6c`, `scan_complete = true`)

| grandeur | valeur |
|---|---|
| corps de primitive interroges | 748 / 748 (0 echec) |
| noms de primitive distincts | 609 |
| xrefs d'appel retenues | 13 899 |
| aretes | 11 180 |
| proprietaires | 1 203 (ability 741, effect 367, utility 69, other 21, dsl-internal 5) |
| couverture | `measured` 593 · `measured_empty` 16 · `callers_anonymous` 0 · `not_measured` 0 |
| sites appelants non nommes | 0 |

## Le classement par levier -- le livrable a plus fort effet

`n_composers` = nombre d'abilities/effets **distincts** qui appellent la primitive. Porter
celle du haut sert `n_composers` abilities d'un coup. Tete du classement :

| # | primitive | n_composers |
|---:|---|---:|
| 1 | `AbilityTrigger$$op_BitwiseAnd` | 540 |
| 2 | `DSLTriggers$$On` | 277 |
| 3 | `DSLBehaviors$$AddEffect` | 274 |
| 4 | `AbilityBehaviour$$op_BitwiseAnd` | 229 |
| 5 | `DSLFormulas$$ConfigVar` | 229 |
| 6 | `DSLFormulas$$Direct` | 228 |
| 7 | `AbilityTrigger$$op_LogicalNot` | 222 |

Le depot portait l'intuition « porter les PRIMITIVES, pas les abilities » sans l'avoir jamais
chiffree. La voici chiffree.

## Deux pieges que cette carte a rencontres -- ils valent pour tout balayage du meme genre

### 1. Les combinateurs ne sont pas dans les fabriques

`&`, `|`, `!`, `+`, `-` sont des **operateurs surcharges** des types de noeud
(`IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd`...), pas des methodes de fabrique. Definir
« primitive = methode de `DSLBehaviors`/`DSLSelectors`/`DSLTriggers`/`DSLFormulas` » les rate
entierement -- alors que `AbilityTrigger$$op_BitwiseAnd` est **la primitive n° 1 du jeu**
(540 composers) et que les 8 operateurs pesent **+3 113 xrefs**, soit 22 % du total. Une
definition du vocabulaire qui omet son combinateur de sequence n'est pas incomplete a la
marge : elle rate le sommet.

### 2. Les points de composition observes debordent largement l'a priori

Un balayage limite a `CreateBehaviour` raterait la majorite des sites. La distribution
**mesuree** (`composition_sites.methods_observed`) montre `ExecuteBehaviour`, `CreateTrigger`,
mais aussi `CreateEffectDamageBonusForAttack`, `CreateTargetSelector`, `GetAttackBehaviour`,
`Attack`, des lambdas... **506 proprietaires** composent depuis une methode auxiliaire et
seraient invisibles a un balayage naif. La liste des methodes de composition doit etre
**derivee**, jamais presupposee.

## Ce qui est hors d'atteinte, et pourquoi (a dire, jamais a masquer)

### L'axe UTILITY : PARTIELLEMENT mesurable -- pas « non mesurable »

Le trou gshared de `case-259-couverture-gshared.md` est reel, mais il frappe la chaine
**FRIDA**, et cette carte est batie sur les xrefs **GHIDRA**. Mesure, par chaine :

| build | `u003C__Il2CppFullySharedGenericTypeu003E` nommes (ghidra) | (frida) |
|---|---:|---:|
| `gqfc5mff6c` | 2 844 | 0 |
| `rnca9r7q6c` | 2 830 | 0 |

Sur `rnca9r7q6c`, Ghidra nomme **2 184** symboles du namespace `IdunBattle.AI.Playbook`
(dont 97 pleinement partages) et **196** `Playbook$$Calculate*`. **69 playbooks apparaissent
effectivement comme proprietaires d'aretes.** Declarer cet axe « NON MESURABLE » en bloc
aurait ete **aussi faux qu'un zero silencieux** : un « non mesurable » fabrique fait
abandonner une mesure disponible.

Restent hors d'atteinte, et c'est borne explicitement :

1. les corps gshared que Ghidra n'a **pas** nommes -- leur nombre n'est **pas bornable** par
   cette methode (l'absence d'un symbole ne prouve rien) ;
2. tout **probe live** sur cette couche (chaine Frida a 0) ;
3. l'axe **scoring** -- *quel playbook evalue quelle ability* -- absent **par construction**
   et non par mesure vide : ce graphe ne passe pas par les fabriques DSL. Declare
   `utility_scoring.status = OUT_OF_SCOPE_PHASE_1`.

### Les 16 `measured_empty`

Elles n'ont que des xrefs **DATA** (table de methodes IL2CPP), aucun appel. Cas d'ecole :
`DSLTriggers$$Not` est a 0 composer alors que la negation est partout -- parce qu'elle passe
en realite par `AbilityTrigger$$op_LogicalNot` (222 composers). L'API de fabrique existe et
n'est pas empruntee. **Conclure « inutilisee » depuis un xref vide serait faux ici et le
raisonnement inverse -- chercher par ou la semantique passe VRAIMENT -- est ce qui a
retrouve le combinateur.**

## Perimetre : ce que la phase 1 ne fait pas

Pas de jointure avec le gameconfig (ability -> unite, ids d'effet, cles de poids), pas
d'evaluation de ce qui est porte cote Python, aucun port. C'est la phase 2, qui consomme le
contrat ci-dessus.
