# #477-r21-r2 volet A — les quatre gardes de `RefreshEffectsOperation`

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp, session Frida **1** (chaude, aucun reinject).
Les quatre fonctions nommées sont portées 1:1 dans `engine/runner/operations/refresh_effects.py`.
**289** sous-arbres `Effect_Refresh` du flux témoin les confrontent : **0 contre-exemple**,
**0 divergence** sur **273 + 265** actions re-dérivées.
**`Effect_Refresh` AUTONOMES reste 0/0/0**, et ce zéro est **mesuré** — § 6.

```powershell
python scripts/python/probe_477r21r2a_refresh_guards.py      # live, 2 boards
python -m pytest scripts/python/tests/engine/test_477r21r2a_refresh_guards_offline.py -q
```

## 1. La RE — ce que chaque garde LIT dans l'état ECS

| garde | statique | lit | écrit |
|---|---|---|---|
| `$$ShouldBeActive` | **oui** | `EffectComponent.<+0x5e>`, `.IsActive <+0x5c>` ; `IEffect.<slot 0xc>` puis `<slot 0xb>` | rien |
| `$$GetTargetsToAdd` | non | les deux listes de cibles | rien |
| `$$GetTargetsToRemove` | non | les deux listes de cibles | rien |
| `$$UpdateEffectTargets` | non | `EffectComponent.Targets <+0x48>` via `$$GetCurrentEffectTargets` | **`Targets`** (via `$$AddTargetsToEffect` / `$$RemoveTargetsFromEffect`) |

### `ShouldBeActive` — un `switch` puis deux régimes

```
static bool ShouldBeActive(RefreshEffectTrigger t, RefreshEffectType ty, IEffect e,
                           EffectComponent c, IEntity owner, IEntity activePlayer, IEntity fx)
    switch (ty) { case Automatically: break;
                  case ForceActivate:   return true;
                  case ForceDeactivate: return false;
                  default: throw new ArgumentOutOfRangeException(nameof(ty), ty, null); }
    if (c.<+0x5e>)                  return false;
    if (!e.ShouldRefreshForTrigger(t)) return c.IsActive;      // le FLAG COURANT, sans rien evaluer
    return e.ShouldBeActive(entities);                         // la `CreateActiveCondition`
```

La struct `entities` fait `0x128` octets, est **mise à zéro** juste avant, et seuls **quatre**
champs sont renseignés : `<+0x08>` = owner, `<+0x18>` = owner, `<+0x50>` = activePlayer,
`<+0x58>` = effectEntity. `GetDesiredEffectTargets` en construit une **identique** pour le
slot `<0xd>`.

`IdunBattle.Entities.Effects.BaseEffect$$ShouldRefreshForTrigger` : `Forced`/`Simulation`/`Custom`
sortent **avant** toute lecture ; `GetRefreshTriggers()` **`null` ou VIDE rend `true`** ; la seule
sortie fausse est un tableau non vide qui ne contient pas le déclencheur.
`IdunBattle.Entities.Effects.BaseEffect$$ShouldBeActive` évalue la `CreateActiveCondition` (cachée
en `<+0x90>`), puis, **en simulation seulement**, la croise avec une condition de simulation.

### `UpdateEffectTargets` — l'ORDRE **est** le contenu

```
var eventActions = new List<Action>();
var current   = GetCurrentEffectTargets(effectComponent, state);
var toRemove  = GetTargetsToRemove(current, desired);
var toAdd     = GetTargetsToAdd(current, desired);
if (current.Count == 0 && desired.Count >  0) eventActions.Add(b__0);   // AddActivateEffectAction
eventActions.AddRange(RemoveTargetsFromEffect(toRemove, ...));          // LoseEffect*
eventActions.AddRange(AddTargetsToEffect(toAdd, ...));                  // ReceiveEffect*
if (current.Count >  0 && desired.Count == 0) eventActions.Add(b__1);   // AddDeactivateEffectAction
if (toRemove.Count > 0) eventActions.Add(b__2);                         // RevertEffectsForTargets
if (toAdd.Count    > 0) eventActions.Add(b__3);                         // ApplyEffectsForTargets
```

⚠ **`DeactivateEffect` vient APRÈS les lignes de cible, pas avant.** C'est le point qu'un
assembleur naïf inverse, et c'est la contre-épreuve `plan_desactivation_en_tete` (49 + 47
divergences).

⚠ **La MUTATION de `Targets` a lieu à la CONSTRUCTION du plan, pas à l'invocation des actions.**
`AddTargetsToEffect` appelle `EffectComponent$$AddTargetId` dans sa boucle, `RemoveTargetsFromEffect`
fait `Targets.Remove` dans la sienne. Un refresh ultérieur voit donc la liste déjà à jour même si
aucune ligne n'a encore été écrite.

⚠ **`desiredTargets` VIDE est le chemin de DÉSACTIVATION**, pas un cas dégénéré :
`RefreshEffectsOperation$$DeactivateEffect` met `IsActive` à 0 puis appelle littéralement
`UpdateEffectTargets(new List<IEntity>(), ...)`.

### Le TRI, et pourquoi il est observable

`IdunBattle.Entities.Components.EffectComponent$$AddTargetId` fait `Targets.Add(id); Targets.Sort();`
— **un tri après chaque ajout**. Donc `GetCurrentEffectTargets` parcourt une liste croissante, donc
les `Action=LoseEffect` d'un groupe sortent en ids **croissants**. Les `Action=ReceiveEffect`, eux,
suivent l'ordre du **sélecteur** et ne sont pas triés : le flux témoin le montre (49, 55, 53).
Un port qui trierait les deux serait indiscernable sur le premier et **faux** sur le second.

### Les noms de champs sont LUS, pas devinés

La format-string d'`IdunBattle.Entities.Components.EffectComponent$$GetPropertiesString` est
`"EffectType: {0}, IsActive: {1}, Removed: {2}, CasterId: {3}, Targets: {4}, HasTurns: {5},
RemainingTurns: {6}"`, et le décompilé y place `<+0x58>`, `<+0x5c>`, `<+0x5f>`, `<+0x14>`,
`<+0x48>`, `<+0x5d>`, `<+0x64>`. **`<+0x5e>` n'y est pas** — il reste écrit par son offset.

## 2. Où le port vit, et pourquoi

**`engine/runner/operations/refresh_effects.py`.** Les quatre gardes LISENT l'état ECS,
l'ÉCRIVENT (`Targets`) et rendent un **plan** (`List<Action>`), pas des lignes.
`engine/streams/refresh_effects.py` n'écrit jamais dans l'état et n'a aucune notion de cible.
La frontière est le `.Invoke()` de chaque `Action` : au-dessus (quoi, sur qui, dans quel ordre) =
runner ; en-dessous (quelle ligne, quels tags) = streams. Le port rend des **descripteurs**
(`RefreshAction`) plutôt que des closures sur un dispatcher, et l'unique point de recollement
(`bind_refresh_actions`) vit **du côté émission**, en lecture **canard** — importer `RefreshAction`
depuis `streams` créerait une dépendance à rebours.

Deux mirrors d'enum NEUFS, inscrits au registre `probe_313` **dans le commit qui les crée** :
`RefreshEffectType` (3) et `RefreshEffectTrigger` (9). Leur type est **lu** dans `frida/methods.tsv`
(`refreshTrigger:IdunBattle.Operations.RefreshEffectTrigger, refreshType:...RefreshEffectType`) —
le nom court ne tranche pas, `enums.tsv` porte cinq autres `Refresh*`, dont **deux à 3 valeurs**.

⚠ **L'ORDRE DES CHAMPS DE `RefreshEffectOptions` EST L'INVERSE DE L'ORDRE DE SON CTOR**, et c'est un
piège lu : le ctor déclare `(refreshType, refreshTrigger, effectId, entityId)` alors que `<+0x0>`
est le **trigger** et `<+0x4>` le **type**. Deux usages indépendants le fixent dans `RefreshEffect`.

## 3. La confrontation live — six invariants DÉRIVÉS, refutables

`probe_477r21r2a_refresh_guards.py` ne compare pas deux textes : les gardes **décident**, elles
n'écrivent rien. Il confronte ce que le décompilé **impose** au flux.

| | invariant | `C1_02` | `MC1_67` |
|---|---|---|---|
| (I1) | `Activate` ⟹ 0 `Lose` **et** ≥1 `Receive` | 77 exercés, **0** | 75, **0** |
| (I2) | `Deactivate` ⟹ 0 `Receive` **et** ≥1 `Lose` | 49 exercés, **0** | 47, **0** |
| (I3) | les deux ne coexistent jamais | **0** | **0** |
| (I4) | ids des `Lose` strictement croissants (le `Sort()`) | **1** exercé, 0 | **NON EXERCÉ** |
| (I5) | ids des `Receive` **non** contraints | 2 témoins | 3 témoins |
| (I6) | séquence `(step, entité)` re-dérivée par le port | 138 exercés, **0 divergent**, 273 actions | 135, **0**, 265 |

Corpus : **145 + 144** sous-arbres `Effect_Refresh` lus à **toute profondeur** du flux (1 + 2
illisibles, comptés). (I1)…(I5) ne copient **rien** : ce sont des implications à sens unique sur
les seuls comptes observés. (I6) copie une seule chose, déclarée : la **présence**
d'`Activate`/`Deactivate`, qui choisit la reconstruction de `(current, desired)` — le sous-ensemble
inchangé `kept` n'étant pas observable (le flux n'écrit de ligne que pour ce qui bouge).

⚠ **(I4) est FAIBLEMENT EXERCÉ, et c'est dit** : les cibles se perdent presque toujours une par une.
Le `Sort()` est donc gardé **offline**, pas par le live.

⚠ **`ShouldBeActive` N'EST PAS CONFRONTABLE PAR CE CANAL.** Le flux porte les **conséquences** d'un
verdict déjà rendu, jamais le verdict, et la donnée qui le produit (`CreateActiveCondition`,
`GetRefreshTriggers`) n'y est pas. Son **câblage** est confronté par non-régression sur les cinq
tests live du driver (§ 5) ; sa **structure** l'est par le cliquet offline.

## 4. Les cinq contre-épreuves — `a_morde` publié SÉPARÉMENT

| mutation | seam | `C1_02` | `MC1_67` |
|---|---|---|---|
| `sens_de_la_difference` | primitive (`add` ↔ `remove`) | mord, **138/138** rouges | mord, **135/135** |
| `cibles_courantes_vides` | primitive (`get_current_effect_targets`) | mord, **61** | mord, **60** |
| `cibles_courantes_inversees` | primitive | mord, **1** | **NON EXERCÉE** (0 applicable) |
| `plan_desactivation_en_tete` | sortie (le plan) | mord, **49** | mord, **47** |
| `plan_receive_avant_lose` | sortie (le plan) | mord, **2** | mord, **1** |

⚠ **LE COMPTE `applicable sur N` A TROUVÉ UNE FAUTE DU PROBE, et c'est sa raison d'être.** Sans lui,
un `a_morde=false` confond deux états que rien ne distingue : *inerte par construction* (faute du
probe) et *inerte par les données* (limite du montage). `cibles_courantes_inversees` affichait
`a_morde=false` avec **8 cas applicables** — donc une faute : (I6) ne comparait que les **noms**
d'action, et inverser l'ordre des cibles n'en change aucun. Comparer aussi l'**entité** sur
`Lose`/`Receive` (les seules que le port dérive) la rend mordante. Sur `MC1_67` elle reste non
exercée, **0 cas applicable** — cette fois c'est bien une limite des données, et elle est déclarée
au lieu d'être comptée verte.

Le cliquet offline (**20 tests**) couvre ce que le live ne tient pas : les quatre branches de
`ShouldBeActive` (dont le `throw` hors domaine), ses **deux régimes** rendus discernables par un
montage où condition et flag **se contredisent**, les 9 déclencheurs de `ShouldRefreshForTrigger`
et sa seule sortie fausse, le `Sort()` de bout en bout, et le chemin `DeactivateEffect`.

## 5. Le câblage — exact, et INERTE sur `Automatically`

`refresh_stat_modifier_effects` prend désormais son déclencheur et passe par `should_be_active` ;
`movement.py` (×2) et `turnflow.py` cessent de ne porter le leur qu'en **commentaire**
(`UnitPositionChanged`, `TurnChanged`). `damage.py` reste au défaut `Forced` : le déclencheur natif
n'est pas lu à ce site, et `Forced` est **la seule valeur qui ne suppose rien** (elle rend
`ShouldRefreshForTrigger` vrai inconditionnellement, donc « ré-évaluer », le comportement actuel).

⚠ **LE CÂBLAGE NE CHANGE RIEN AUJOURD'HUI SOUS `Automatically`, ET LE DIRE EST LE POINT.** Aucune
classe d'effet du port ne déclare `REFRESH_TRIGGERS`, donc `GetRefreshTriggers()` est `null`
partout, donc la bascule « rendre le flag courant » n'est jamais prise. Cause **lue** : les **12**
classes natives qui surchargent `GetRefreshTriggers` construisent leur tableau par
`System.Runtime.CompilerServices.RuntimeHelpers$$InitializeArray`, dont le blob vit dans
`global-metadata.dat` et **pas dans la DLL** — Ghidra ne peut pas les rendre. Une seule est lisible
en clair (`BlockEnteringUnitsTileEffect` → `{EffectsChanged}`, écrit en ligne), et elle n'a pas
d'équivalent porté. Résidu **#477-r26**.

⚠ **LA GARDE D'ÉCRITURE `_active_condition_is_ported` RESTE, et ce n'est pas une infidélité.**
`should_be_active` mirrore ce que le **natif** décide ; `_active_condition_is_ported` décide si le
**port** a le droit d'écrire ce verdict dans le flag. Côté natif la `CreateActiveCondition` existe
toujours — `IdunBattle.Entities.Effects.BaseEffect$$NeedsRefreshing` sait même dire qu'elle est
**constante**, et `RefreshEffect` saute alors la garde entière sous `Automatically`. Côté port,
`BaseEffect.is_active` rend `True` par **défaut** : un placeholder, pas une lecture. L'écrire est
exactement la régression mesurée par #366-r1b (riposte fantôme de `1111` à 2849 PV). Fusionner les
deux gardes serait une fidélité **apparente** payée d'une régression **réelle**.

Non-régression mesurée : `test_contagions_lifecycle_live` + `test_anvil_shield_stun_live` (11),
`test_psychic_stalk_visual_effect_live` + `test_martial_superiority_visual_live` (17),
`test_wireweave_net_counter_live`, `test_refresh_active_flag_discriminant_offline` +
`test_477r21_activation_tree_offline` + `test_477r21r3_entity_allocator_offline` (68).

## 6. `Effect_Refresh` AUTONOMES : toujours **0 / 0 / 0** — et c'est un résultat

`probe_477r21_activation_tree.py` re-joué : **VERT**, 363/363, 392/392, 131/131, `Effect_Refresh`
reproduits **34 / 36 / 12**, **AUTONOMES 0 / 0 / 0**. `probe_477r15a_stream_conformance.py` :
**204/204** et **316/316**, registre à jour.

**Ce volet ne pouvait pas bouger ce chiffre, et il ne prétend pas l'avoir fait.** Les deux entrées
copiées par ce probe sont (a) la **sélection** — quels effets sont rafraîchis, dans quel ordre —
qui vit dans `AOperation.AbilityAndEffectCache.<slot 3>` parcouru par
`EvaluateTriggerOperation$$ExecuteInternal` (**volet B**, hors périmètre), et (b) les identifiants
d'entité, qui en **dérivent** (#477-r21-r3). Les gardes portées ici décident ce qui se passe
**une fois l'effet choisi** ; elles ne le choisissent pas. Le chiffre a été **re-mesuré**, pas
déduit de la livraison.

## 7. Ce qui n'est PAS couvert

- **`GetRefreshTriggers` par classe** — non lisible au décompilé (`global-metadata.dat`), aucune
  des 12 classes natives n'a d'équivalent porté → **#477-r26**.
- **`BaseEffect$$NeedsRefreshing`** — lu (§ 5), non porté : il n'y a pas de notion de « condition
  constante » côté port → **#477-r26**.
- **Le modèle de CIBLES lui-même.** Le natif porte **une** entité-effet dont `Targets` liste N
  unités ; le port matérialise **N instances**, une par unité (`state.effects.by_unit`).
  `EffectComponentView.from_effect` rend donc `targets` **vide** : les trois gardes de ciblage sont
  portées et confrontées **sur le flux**, mais aucun consommateur du moteur ne les appelle encore.
  Les brancher est un changement de modèle → **#477-r26**.
- **La garde de simulation** `state.<slot 0xb>()` + `StaticBattleRules.Effect$$ShouldRefreshDuringSimulation`,
  et la sortie `EffectComponent.Removed <+0x5f>` : lues, hors de la garde, non portées.
- **`<+0x5e>`** : le champ existe et est porté (`blocked`), mais rien ne l'écrit — aucun accesseur
  natif ne le nomme, et son producteur n'est pas identifié.
- **Les volets B / C / D de #477-r21-r2** : le cache d'abilities et d'effets, les deux gardes
  d'`EvaluateAbilityTrigger`, la séquence de création des entités d'effet. **Ce volet ne les a pas
  rendus atteignables** : il agit en aval de la sélection.

## Résidus

- **#477-r26** — **les données que les gardes consomment et que le port n'a pas** : les ensembles
  `GetRefreshTriggers` par classe (blob `global-metadata.dat`, invisible de Ghidra — un capteur
  live sur le slot de vtable `<+0x5c8>` les rendrait), `BaseEffect$$NeedsRefreshing` (la notion de
  condition **constante**), et le branchement des trois gardes de ciblage sur un modèle de cibles
  que le port ne porte pas encore (`by_unit` vs `EffectComponent.Targets`). Tant que ces trois
  manquent, le câblage du déclencheur est **exact et inerte** sous `Automatically`.
