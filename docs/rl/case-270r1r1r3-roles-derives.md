# #270-r1-r1-r3 — les rôles DÉRIVÉS : 140 littéraux nommés, et l'ordinal n'a tranché aucun

> Suite de `#270-r1` (clés de dict, volets 1 et 2) et `#270-r1-r1` (élément de conteneur).
> Livré le 2026-08-05. Build `rnca9r7q6c`.

## 1. Ce que cette tranche avait de différent

Les trois volets précédents disposaient d'un discriminant **structurel** : la **couverture du
groupe**. Si toutes les clés d'un dict — ou tous les éléments d'un tuple — appartiennent au même
enum du build, le groupe *est* clé par cet enum, quoi que le fichier importe. C'est un signal fort,
et il se calcule.

Ici il n'y a **aucun groupe**. Les rôles que le recenseur exhaustif de #658 a fait apparaître sont
des positions **isolées** : `_STAT = 8`, `return 7`, `he(it, self.effect_type, 6, ...)`,
`cands[:8]`. Un littéral seul n'a pas de voisin qui le contraigne. Le seul discriminant disponible
est donc, **site par site** :

- le **NOM déjà écrit au site** (nom de la constante, commentaire de fin de ligne, nom du fichier
  ou de la classe consommatrice) ;
- ou le **TYPE DÉCLARÉ** du paramètre natif, **lu** dans `data/symbols/<build>/frida/methods.tsv`.

## 2. Chiffres re-dérivés (ne pas les citer — `probe_270r1_enum_candidates.py`)

| | avant | après |
|---|---|---|
| candidats retenus | 746 | **610** |
| `affectation` | 166 | **44** |
| `valeur de retour` | 18 | **6** |
| `branche de conditionnelle` | 31 | 30 |
| `valeur par défaut` | 20 | 19 |
| mirrors sous garde `probe_313` | 15 | **19** |

**141 littéraux convertis** (136 au recensement + 5 sous le seuil structurel `|n| <= 3` —
`UnitFlagsComponent.MOVED/ARRIVED_AT_FINAL_TILE/ACTIVE_ABILITY_USED/TURN_FINISHED`, plus `DEAD`,
convertis pour que la classe entière soit nommée). 102 membres distincts, 50 fichiers.

⚠ **Le 141ᵉ est arrivé AU REBASE**, et c'est le seul conflit de la tranche : `master` a ajouté
`DEAD = 6` à `UnitFlagsComponent` pendant le travail. Tranché par l'auteur — la classe est nommée
en entier, donc le laisser en ordinal nu aurait rouvert le gisement *dans le fichier même qui le
ferme*. Le conflit a donc **ajouté** une conversion, il n'en a repris aucune ; la table de garde
suit (140 → 141), sans quoi cette conversion-là n'aurait été gardée par rien.

## 3. Quatre mirrors NEUFS — le type est LU, jamais déduit d'un nom court

| mirror | membres | type DÉCLARÉ dont il vient (`frida/methods.tsv`) |
|---|---|---|
| `UnitFlag` | 27 | `IdunBattle.Entities.UnitExtensions.HasFlag(flag)` |
| `EntityType` | 9 | `IdunBattle.Core.Entity..ctor(type)` |
| `AbilityConstantType` | 141 | `IdunBattle.Configuration.AbilityConfiguration.GetNumberConstant(constantType)` |
| `AbilityVariableType` | 158 | `IdunBattle.Configuration.AbilityConfiguration.GetVariableForLevel(variableType)` |

Tous **inscrits au registre de `probe_313` dans le commit qui les crée**, appariés par leur **nom
plein**. Ce gisement s'est rouvert **quatre** fois par notre propre cadence (`PathfinderType`
#381-r5, `KillUnitStep` #389-r2, `DamageReason` #651 — qui rendait `master` rouge —, `Edge`
#270-r1-r1) ; l'étage 4 du test le referme de façon exécutable.

### 3bis. `UnitFlag` est un `IntEnum`, pas un `IntFlag`

Les valeurs sont des **index** contigus (0..28, trous à 7 et 10), indexés par
`UnitFlagsComponent`. Un `IntFlag` écrirait un masque et rendrait `Overkilled | Fled == 9` — faux.

### 3ter. Où vivent les deux index d'ability — et pourquoi ce n'est pas cosmétique

`ability_constant_type.py` / `ability_variable_type.py` vivent sous **`engine/entities/`**, pas
sous `engine/entities/abilities/`. Le second emplacement a été **essayé** et rend les modules
**inimportables** : importer quoi que ce soit du sous-paquet exécute son `__init__.py`, qui tire
`active_ability` → `services.damage_prediction` → `ImportError: cannot import name
'get_default_attack_hits' ... (most likely due to a circular import)`. **Cycle mesuré**, même forme
que celui de `services/static_battle_rules.py` (#270-r1-r1).

Règle qui en sort : **un mirror d'enum est une FEUILLE**. Le ranger dans un paquet à `__init__`
lourd le rend inatteignable depuis la moitié du moteur. L'étage 6 du test reproduit la contrainte
et **se retourne tout seul** (il rougit) le jour où `entities/abilities/__init__.py` cesserait
d'importer `active_ability`.

## 4. L'ordinal ne tranche pas — mesuré DE L'INTÉRIEUR de la tranche

La première version du convertisseur portait le membre **en dur**. Elle a écrit
`TriggeredAbilityType.PathOfCommand_ExtraDmg` pour `1111` — qui est **`WireweaveNet`** côté
triggered, et `PathOfCommand_ExtraDmg` côté `EffectType`. Deux enums mélangés de mémoire, sur une
tranche dont c'est précisément le sujet.

Le convertisseur a **refusé** (le mirror ne connaît pas ce nom). Sa table ne porte plus depuis que
**l'enum** — mon seul arbitrage — et le **membre est DÉRIVÉ du mirror**. C'est la parade
structurelle : il n'existe plus de chemin par lequel un nom de mémoire entre dans le code.

Le convertisseur refuse aussi d'écrire si la ligne visée ne porte pas la valeur attendue, ou si
l'enum ne connaît pas cette valeur. **140/140 sites, 0 refus** à l'écriture finale.

## 5. Deux erreurs de NOM trouvées dans le port

| site | ce que le port disait | ce que le build dit |
|---|---|---|
| `runner/operations/effects.py` `_EFFECT_NOT_UPDATABLE = 0x472` | « 1138 `Wraithcannon_NormalAttack` » | c'est l'**`ActiveAbilityType`** 1138. Le paramètre d'`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect.IsUpdatable` est **DÉCLARÉ `IdunBattle.Entities.Enum.EffectType`**, où 1138 = **`PowerUp_Armor`** |
| `runner/components.py` `TURN_FINISHED_FORCED = 27` | « hors enum du dump — ajout post-dump ; nom descriptif » | le build le porte : **`UnitFlag.TurnTerminated`**. L'affirmation était **périmée** |

Le second cas est exactement la péremption silencieuse que la règle vise : une note juste au moment
où elle a été écrite, fausse depuis, et que rien ne relisait. `AMBUSH_CONSUMED = 14` est le cas
voisin, **non** fautif : le nom est local au port (le rôle qu'il joue), l'ordinal est celui du
natif (`Resurrected`), et la sémantique décrite au site concorde.

## 6. Value-preserving — l'empreinte hache la VALEUR, pas la représentation

Empreinte de **tout** l'arbre `engine/` (attributs de module **et** attributs de classe), prise sur
l'arbre de base extrait par `git archive HEAD` puis sur l'arbre livré, dans deux processus
distincts. Canonicalisation par **`int(x)`, récursive** dans listes/tuples/sets/dicts ; un `bool`
n'est jamais rabattu sur son `int`.

```
AVANT = 9516   APRES = 9851            (re-calcule APRES rebase, contre origin/master)
DISPARUES = 0   COMMUNES = 9516   DIVERGENTES = 0
NOUVELLES = 335  (= 158 AbilityVariableType + 141 AbilityConstantType + 27 UnitFlag + 9 EntityType)
```

⚠ **La portée de l'empreinte est délibérément large** : on ne hache pas une liste de structures
choisies. Une liste choisie ne peut pas montrer la valeur qu'elle a oubliée — le vice même que
#270-r1-r1 a corrigé côté recenseur.

⚠ **Un premier passage a rendu 3 divergences, toutes fausses** : l'arbre de base avait été extrait
avec `git archive HEAD scripts/python` seulement, donc sans `data/` — et les caches *lazy*
`_DMG_CFG` / `_EFF_CFG`, alimentés par le gameconfig, restaient vides d'un côté. Ce n'était pas une
divergence de conversion mais un **artefact du montage**. Extraire l'arbre **complet** l'a dissous.
La leçon de #270-r1-r1 (« hacher la valeur, pas `repr` ») était déjà appliquée ; celle-ci s'y
ajoute : **l'arbre témoin doit voir les mêmes ENTRÉES que l'arbre mesuré**.

## 7. La garde — six étages, et ce que `probe_313` ne peut pas faire

`scripts/python/tests/engine/test_270r1r1r3_role_enum_offline.py` (12 tests, 100 % offline).

1. **RENUMÉROTAGE** — chaque membre écrit vaut toujours l'ordinal **figé** à la conversion.
   *C'est le cran qui manque à `probe_313`* : lui compare le **mirror** au **build**, donc il
   redevient **vert** dès qu'on régénère le mirror — alors que la valeur écrite au site a changé.
2. **CLIQUET DE FORME** — chaque fichier porte toujours ≥ le nombre d'occurrences de chaque membre
   que la tranche y a mis. Clé = un **compte**, pas un numéro de ligne : survit au déplacement de
   code, et un compte qui baisse signale un retour à l'ordinal nu.
3. **ACCESSEURS PUBLICS** — `UnitFlagsComponent.has` / `remove_turn_flags`,
   `BaseTriggeredAbility.VAR_*`, avec l'ordinal **et** avec le membre, plus anti-dégénérescence
   (les réponses doivent DISCRIMINER).
4. **REGISTRE** — les quatre mirrors neufs y sont, `garde=True`, `strict=True`, clé = nom plein ;
   et la bijection est rejouée.
5. **NON-DÉGÉNÉRESCENCE `AbilityConstantType` / `AbilityVariableType`** (§8).
6. **PLACEMENT DES MIRRORS** — §3ter, avec la condition de retournement.

Plus un bloc **« ce qui reste en littéral »** rendu **exécutable** : les scalaires assumés doivent
rester des `int` purs (§9).

## 8. Le danger que la tranche éteint n'est PAS celui qu'on croit

Première formulation de l'étage 5, **fausse** : « les ordinaux utilisés des deux côtés doivent
nommer autre chose ». Elle rendait un ensemble **vide** — les 19 ordinaux `AbilityConstantType` et
les 10 `AbilityVariableType` de la tranche sont **disjoints**. Un test vide serait passé pour vert.
Il a rougi parce qu'il assertionne son propre non-vide ; sans cette assertion, il aurait menti.

Le vrai danger, mesuré :

- les **19/19** ordinaux `AbilityConstantType` utilisés sont **aussi** des membres valides
  d'`AbilityVariableType` (et **10/10** dans l'autre sens) ⇒ **une confusion des deux accesseurs
  n'aurait levé AUCUNE erreur** : elle aurait lu la mauvaise clé du gameconfig, en silence ;
- mais **28/29 nomment autre chose** (`22` = `range` / `blockDmg_2`, `14` = `extraMovement` /
  `minAdjacentDmg`, `16` = `nrOfSummons` / `dmgToAdjacent`) ⇒ **c'est l'écriture par NOM qui rend
  la confusion visible**. Globalement : 140 ordinaux partagés, **1 seul** nommé pareil.
- L'exception est **nommée, pas absorbée** : `47` s'appelle `nrOfHits` des deux côtés — même clé
  gameconfig, donc confusion sans effet observable. L'étage 5 fige cet ensemble ; si un autre
  apparaît, il faut relire, pas élargir.

## 9. Ce qui reste en littéral — un RÉSULTAT, pas un oubli

Nommé, et rendu exécutable par `SCALAIRES_ASSUMES` :

- tous les `100` de **pourcentage** (`ability_variables_multiplier`, `PercentageOf`, `cc = 100`) ;
- `INT_MAX` / `DISTANCE_UNREACHABLE` / `MIN_DISTANCE_EMPTY` (`0x7FFFFFFF`), `BB_MAX_REPEATS` ;
- l'état interne du **Mersenne Twister** (`_N = 624`, `_M = 397`, `_MATRIX_A`, `_U32`, `_UPPER`) ;
- les **coûts de pathfinding** (`WEIGHT_BASE = 10`, `WEIGHT_BLOCKED = 10000`) ;
- les **poids d'utilité** (`W_HEAL`, `W_HP`, `W_LASCANNON_PIERCE_BONUS`, `_ADJACENT_ENEMIES_UTILITY`,
  `SERENE_UNIFIER_PER_ADJACENT_FRIEND`), `MAX_ITERATIONS`, `WHOLE_BOARD_REACH`, les **timeouts RPC** ;
- les **VALEURS** de constante gameconfig — `FIRE_OF_ABSOLUTION_IGNITE_CHANCE = 30` est la valeur
  (30 %), **l'index est 42** (`chance`) ; et les **fallbacks** de `dsl.ConfigConst("maxNrOfHits", 99)`.

**Non tranchés, et dits comme tels** (ni convertis, ni déclarés scalaires) :

- **`1013` / `0x3f5`** — `attack_type.NORMAL_ATTACK_KIND`, `lord_of_tempests.SMITE_KIND`,
  `triggers.IsNormalAttack`. C'est un `AbilityOrEffect`, type **union** natif ; `1013` vaut
  `PrecisionShot_Attack` en `ActiveAbilityType` et `PsykerExtraAttack` en `TriggeredAbilityType`,
  et le site lui-même porte déjà « la valeur 1013-vs-id-concret = à confirmer ». Trancher sans lire
  `DirectAbilitySelector` écrirait un nom au jugement. Résidu **#270-r1-r1-r3-r1**.
- **`services/damage_combat.STAT_HEALTH = 4` / `STAT_ARMOR = 5`** — les deux noms **contredisent**
  `StatType` (4 = `ARMOR`, 5 = `HEALTH`). Les deux constantes sont **mortes** : aucun lecteur dans
  tout `engine/` (vérifié, et **sous cliquet** — un test rougit si un lecteur apparaît). Tant que
  rien ne les lit, la contradiction est inerte et en figer un sens serait choisir au jugement.
  Résidu **#270-r1-r1-r3-r1**.
- les **189 `argument d'appel`**, **49 `comparaison`**, **41 `élément de conteneur`** et **103
  `expression`** restants : majoritairement des timeouts RPC, des pourcentages et des index de
  slot. Un tri site par site reste à faire, il n'a rien de mécanique.

## 10. Validation adversariale — 20 mutants, 20 détectés

`scripts/python/probe_270r1r1r3_mutants.py` — **commité**, parce qu'une garde verte ne prouve rien
si le harnais qui l'a validée meurt avec un scratchpad. Chaque mutation est appliquée sur l'arbre
réel, le test joué, puis `git checkout` restaure ; le probe **refuse de démarrer** si
`scripts/python` porte des modifications non commitées (il les détruirait).

Il distingue **trois** issues, et c'est le point : `ROUGE` (garde mordante), `VERT` (mutation
appliquée, garde muette) et `MOTIF ABSENT` (mutation jamais appliquée) — les confondre fait accuser
la mauvaise pièce.

Renumérotage d'un membre utilisé (×2) · retour à l'ordinal nu (×2) · confusion des deux index ·
membre supprimé · membre renommé · mirror retiré du registre · mirror mis en dette · clé de
registre par nom court · scalaire assumé converti en enum · lecteur apparu pour une constante
morte · `has` qui rend toujours `True` · `remove_turn_flags` qui retire un flag de trop ·
permutation de deux membres · homonymie créée entre les deux index · disparition du cycle
d'import · table `SITES` vidée · ordinal figé aligné sur un mirror muté · mirror redéplacé sous
`entities/abilities/`.

⚠ **Deux mutants sont d'abord restés VERTS, et l'accusé était le MUTANT, pas la garde** — ce qui
ne se voit qu'en allant lire *pourquoi* :

- `W_HEAL = 100` apparaît **dans la docstring avant le code** ; `replace(..., 1)` mutait donc de la
  prose. La garde n'avait rien à détecter.
- le mutant « mirror déplacé » se contentait de renommer un titre de docstring : il ne déplaçait
  rien.

Refaits pour mordre réellement (mutation dans le code ; déplacement de fichier + réécriture des 10
imports), les deux sont **détectés**. Un mutant vert oblige à trancher entre « garde trouée » et
« mutant inopérant » — et la réponse n'est pas devinable, elle se lit. Les deux corrections sont
**dans le probe commité**, y compris le mutant M20 qui déplace physiquement le fichier.

## 11. Ce qui a été rejoué

**Tout ci-dessous a été rejoué APRÈS le rebase** (14 commits d'écart avec `origin/master`) :

- `probe_313` (19 mirrors sous garde, bijection, 0 dette) · `probe_181` (104 abilities, 0 masque
  manquant) · `probe_365` · `probe_468` (PASS) · `probe_273 --only-scan` — tous **verts** ;
- `probe_270r1r1r3_mutants.py` — **20/20 mutants détectés**, PASS ;
- **752 tests offline** (`tests/engine/*offline*.py`, 54 fichiers) — **752 passed** ;
- import de **393 modules** `engine/` — **0 KO** ;
- la garde de la tranche — **12 passed**.

**Non couvert** : aucun test **live** n'a été rejoué. La tranche est value-preserving *prouvée par
empreinte* (0 divergence sur 9 515 valeurs), donc le runtime ne peut pas voir de différence ; mais
c'est une preuve par la valeur, pas une confrontation live. La fenêtre DRAIN #10 était par ailleurs
ouverte pendant la tranche — aucun runner n'a été monté, et rien n'en a été conclu.

## Résidus

- **#270-r1-r1-r3-r1** — les deux non-tranchés du §9 : `1013` / `0x3f5` (`AbilityOrEffect`, union
  native : lire `DirectAbilitySelector` et la 2ᵉ branche d'`IsNormalAttack`), et les deux
  constantes mortes de `damage_combat` qui contredisent `StatType`. Les deux sont sous cliquet
  exécutable, pas seulement écrits.
