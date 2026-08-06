# #477-r21-r2 volet B — le CACHE qui choisit ce qui s'active

**PORTÉ ET MESURÉ, PAS FERMÉ.** Build `rnca9r7q6c`, ghidra-mcp, session Frida **1** (chaude, aucun
reinject, **aucun capteur neuf**). La structure et les règles d'`IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache`
sont portées 1:1 dans `engine/runner/caches/ability_and_effect_cache.py`. Sa **séquence** est
confrontée au natif sur **312 passes complètes** de **30 `EventTriggerType`**, trois scénarios :
**0** divergence de stabilité, **0** re-dérivation fausse sur 25 événements applicables, **0** ordre
divergent côté registre du port.
**`Effect_Refresh` AUTONOMES reste 0/0/0**, et le § 7 dit pourquoi — ce volet ne pouvait pas le
bouger.

```powershell
python scripts/python/probe_477r21r2b_activation_cache.py            # live, 3 scenarios
python -m pytest scripts/python/tests/engine/test_477r21r2b_activation_cache_offline.py -q
```

## 1. L'INVENTAIRE — ce que le cache contient, qui le peuple, ce qui l'ordonne

Le résidu demandait un inventaire mesuré avant tout port. Le voici, entièrement **lu**.

### 1.1 La structure (7 conteneurs + 2 dépendances)

`frida/classes.tsv` donne `AbilityAndEffectCache` = **96 octets**, donc des champs `+0x10`..`+0x58` ;
le ctor les initialise un par un.

| offset | type | accesseur |
|---|---|---|
| `+0x10` | `IEffectsDatabase` | — (dépendance du ctor) |
| `+0x18` | `IAbilitiesDatabase` | — (dépendance du ctor) |
| `+0x20` | `Dictionary<EventTriggerType, List<SortedTriggered>>` | **`GetActiveTriggeredAbilitiesAndEffects(trigger)`** ← le slot 3 |
| `+0x28` | `Dictionary<EventTriggerType, List<SortedTriggeredAbility>>` | `GetSimulatedActiveTriggeredAbilities(trigger)` |
| `+0x30` | `List<SortedEffect>` | `GetEffects` |
| `+0x38` | `List<SortedEffect>` | **`GetRefreshingEffects`** |
| `+0x40` | `List<SortedEffect>` | **`GetEffectsWithBonuses`** |
| `+0x48` | `List<SortedEffect>` | `GetRefreshingInSimulatedEffects` |
| `+0x50` | `List<SortedTriggeredAbility>` | `GetTriggeredAbilityForNonOwnerPlaybook` |
| `+0x58` | *(non initialisé par le ctor)* | — lu par `AddAbility`, producteur **non identifié** |

⚠ **L'appariement offset → accesseur n'est PAS celui qu'on devine, et il se lit un par un** :
`+0x38` est `GetRefreshingEffects` et `+0x40` est `GetEffectsWithBonuses`, soit l'**inverse** de
l'ordre dans lequel `AddEffect` les alimente. Déduire l'un de l'autre interverti deux listes que
plus rien ne distingue ensuite.

⚠ **Les deux dictionnaires sont PRÉ-PEUPLÉS**, une entrée par valeur de
`Enum.GetValues<EventTriggerType>()`, liste vide. `get_Item` est donc **total** : une clé absente
n'existe pas, et un dictionnaire paresseux côté port lèverait là où le natif rend une liste vide.

### 1.2 Le slot 3 est RÉSOLU, pas supposé

`EvaluateTriggerOperation$$ExecuteInternal` appelle `FUN_1801e7040(cache, <itf>, 3)` puis
`(*puVar6)(cache, trigger, ...)`. La méthode d'arité 1 prenant un `EventTriggerType` et rendant
`DisposableList<SortedTriggered>` est **unique** : `$$GetActiveTriggeredAbilitiesAndEffects`
(signature LUE dans `frida/methods.tsv`). Son corps rend
`ListPool<SortedTriggered>.GetDisposable(this.<+0x20>[trigger])` — une **copie**, ce qui rend le
parcours insensible aux mutations que les triggers provoquent en s'exécutant.

### 1.3 Les quatre peupleurs

```
AddEntity(entity)                       -- l'aiguillage UNIQUE
    if (entity is EffectEntity ee) { AddEffect(ee, ee.<+0x20>); return; }
    if (entity.TryGetComponent<TriggeredAbilityComponent>(out c)) AddAbility(entity, false, c);

RefreshEntity(entity)                   -- le SEUL site a passer `checkIfAlreadyExist: true`
    if (entity.TryGetComponent<TriggeredAbilityComponent>(out c)) AddAbility(entity, true, c);

AddAbility(entity, checkIfAlreadyExist, abilities)
    foreach (configId in abilities.<+0x18>)                 // la KeyedCollection du composant
        foreach (ability in this.abilities.<slot 2>(configId))
            foreach (kvp in this.<+0x20>)                   // TOUTES les cles de l'enum
                if (ability.<slot 3>.Contains(kvp.Key)) {
                    if (checkIfAlreadyExist && kvp.Value.Any(<AddAbility>b__0)) continue;
                    AddAbilityOrEffect(new SortedTriggeredAbility(...), kvp.Value);
                    if (ShouldBeSimulated(order)) AddSimulatedTriggeredOrEffect(...);
                }
        if (<slot 0 de +0x58>(order, simulate) && list.Count > 0)
            AddSorted(new SortedTriggeredAbility(entity, configId, list.First()), this.<+0x50>);

AddEffect(effectEntity, effectComponent)
    var effect = this.effects.<slot 0>(effectComponent.<+0x58>);
    foreach (trigger in effect.<slot 0x12> aplati)          // GARDE d'unicite par entite
        if (!list.Any(s => s is SortedEffect se && se.entity == entity)) AddAbilityOrEffect(v, list);
    foreach (t in effect.<slot 0x2d> ?? [])                 // AUCUNE garde
        AddSorted(v, this.<+0x20>[t.<slot 0>]);
    if (effect.<slot 10> || effectComponent.<+0x5d> /*HasTurns*/) AddSorted(v, this.<+0x38>);
    if (Effect.ShouldRefreshDuringSimulation(effectType))         AddSorted(v, this.<+0x48>);
    if (effect.<slot 0x2e>)                                       AddSorted(v, this.<+0x40>);
                                                                  AddSorted(v, this.<+0x30>);
```

⚠ **Le balayage d'`AddAbility` porte sur les CLÉS DU DICTIONNAIRE, pas sur les triggers de
l'ability.** Le natif énumère `+0x20` et demande à l'ability si elle contient la clé. L'ensemble
obtenu est le même ; la **dépendance** ne l'est pas — une valeur d'enum absente du dictionnaire
serait ignorée en silence, et c'est exactement ce que le pré-peuplement du ctor empêche.

⚠ **`AddEntity` n'est PAS idempotent** (`checkIfAlreadyExist: false`) : appeler deux fois inscrit
deux fois. Seul `RefreshEntity` déduplique, et sa garde `<AddAbility>b__0` compare **trois**
choses — entité, `order`, **et l'identité de l'objet ability**. Ne comparer que l'entité
dédupliquerait des abilities distinctes du même porteur.

⚠ **Les deux boucles d'`AddEffect` ne se gardent pas pareil**, et c'est le piège : la première
refuse un second `SortedEffect` de la même entité dans une liste qui en contient déjà un, la
seconde n'a **aucune** garde. Uniformiser les deux ajoute — ou supprime — des entrées.

### 1.4 Les deux retraits

`RemoveEntity` a **deux branches asymétriques**, et l'asymétrie est réelle :

* **entité d'EFFET** → `FindIndex` + `RemoveAt` (**UN SEUL** retrait par liste), sur `+0x20` puis
  sur `+0x38`, `+0x48`, `+0x40`, `+0x30` **dans cet ordre** — un ordre **différent** de celui des
  ajouts d'`AddEffect` ;
* **entité UNITÉ** → `RemoveAll` sur `+0x20`, `+0x28`, `+0x50`. **Les quatre listes d'effet ne sont
  PAS touchées** : une unité qui meurt laisse dans `effects` les `SortedEffect` des entités-effet
  qu'elle portait ; c'est leur propre `RemoveEntity` qui les retire ;
* **ni l'un ni l'autre** → rien.

`RemoveTriggered(target, type)` n'itère que `+0x20`. Ni la simulation, ni la liste
non-owner-playbook, ni les listes d'effet ne sont purgées. Ce n'est pas un oubli qu'on corrige au
portage.

### 1.5 CE QUI ORDONNE — `AddSorted`, et rien d'autre

```
static void AddSorted<T>(T value, List<T> list)
    int idx = list.FindIndex(x => x.CompareTo(value) == -1);
    if (idx < 0) idx = list.Count;
    list.Insert(idx, value);

int SortedTriggered.CompareTo(SortedTriggered other)
    if (other == null) return 1;
    return this.Priority.CompareTo(other.Priority);       // slot 0x188, `get_Priority` VIRTUEL
```

⇒ liste maintenue en ordre **décroissant de `Priority`**, insertion **stable** (on s'arrête au
premier **strictement** inférieur, donc on passe **après** les égaux).

⚠ **Le receveur de la comparaison est l'élément DÉJÀ EN PLACE** (`x.CompareTo(value)`), pas
l'arrivant. Inverser le sens rendrait un ordre croissant **et** — à priorités égales — une
insertion en tête au lieu de la queue : deux fautes qu'un corpus à priorités uniformes ne
distingue pas l'une de l'autre, mais qui changent toutes deux la séquence.

`SortedTriggeredAbility.Priority` = slot **7** de l'ability ; `SortedEffect.Priority` = slot **9**
de l'effet. Le type de retour est `IdunBattle.Entities.Abilities.AbilityPriority`
(`1000=First, 100=Early, 0=Normal, -100=Late, -1000=Last`), **lu** dans `frida/methods.tsv`.

## 2. Ce qui N'EST PAS LISIBLE, et c'est ce qui borne la tranche

Trois données que le cache **consomme** et que le décompilé ne rend pas :

| donnée | où elle vit | pourquoi illisible |
|---|---|---|
| `Priority` par porteur | slot 7 / slot 9 | corps `mov eax,<imm32> ; ret`, **dédupliqués** par IL2CPP — un seul propriétaire arbitraire dans `methods.tsv`, aucun nommé par Ghidra. **Même faux négatif que #170**, où 22 surcharges réelles n'occupaient que 3 lignes |
| les triggers d'une ability (`<slot 3>`) et d'un effet (`<slot 0x12>` / `<slot 0x2d>`) | mêmes corps | idem, plus les tableaux bâtis par `RuntimeHelpers.InitializeArray`, dont le blob vit dans `global-metadata.dat` — **même cause que #477-r26** |
| l'ordre INTRA-entité des abilities | `UnitFactory$$AddConfiguredAbilities` puis `TriggeredAbilityComponent$$TryAdd` | lisible, mais **hors de cette tranche** (§ 6) |

⚠ **`AbilityPriority` sert DEUX axes qu'il ne faut pas confondre** : le tier de **playbook**
(`IPlaybook` slot 0, table `engine/playbook/noncomparable/_base.py::NATIVE_PRIORITY`, case-170) et
la priorité de **cache** (slots 7 / 9). Deux slots, deux objets. Ordonner le cache par le tier de
décision de l'IA serait une confusion silencieuse — même forme que celle qu'a mesurée #270-r1-r1-r3
entre `AbilityConstantType` et `AbilityVariableType`.

## 3. L'ORACLE — un hook qui EXISTE DÉJÀ, aucun capteur neuf

Un cache n'émet aucune ligne : il rend un **ensemble ordonné**. On ne peut donc pas le confronter
en comparant deux textes de flux, comme les quatre crans #477-r18..r22. L'oracle est
`frida/hooks/features/trigger-trace.ts`, **armé par défaut**, en lecture seule : il intercepte
`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$ShouldTrigger`, appelée **une fois par entrée
retenue du parcours, dans l'ordre**. Sa trace **est** la séquence `active[trigger]`.

Le probe ne fait **jamais** `triggerTraceReset` — cela effacerait le ring des autres agents. Il lit
`totalFires` avant/après chaque étape courte et **déclare** ce qu'il a perdu quand une étape dépasse
le ring de 200 (mesuré : 18 à 90 fires perdus au `build`).

## 4. LES CINQ INVARIANTS, et ce que chacun a eu à trancher

| | invariant | `MC1_67` 2v2 | `C1_02` 2v2 | `C1_02` 5v5 |
|---|---|---|---|---|
| | événements observés | 10 | 9 | 11 |
| (I1) | **STABILITÉ** — deux publications du même trigger parcourent la même séquence | **0** divergente / **136** passes complètes | **0** / **135** | **0** / **41** |
| (I2) | **MONOTONIE inter-entité** — les identifiants porteurs sont non décroissants | **1** rupture / 9 couples | **1** / 4 | **3** / 20 |
| (I3) | **RE-DÉRIVATION** par le port, alimenté dans l'ordre des identifiants | **0 ROUGE** / 9 applicables (+1 hors régime) | **0** / 8 (+1) | **0** / 8 (+3) |
| (I4) | **CROISSANCE** — les passes courtes sont des sous-séquences de la modale | **0** hors sous-séquence | **0** | **0** |
| (I5) | l'ORDRE du **registre du port** est une sous-séquence du natif | 4 exercés, **0 discriminant** | 4, **0** | 5 exercés, **3 discriminants**, **0 divergent** |

(I1) ne copie **rien** : c'est ce que « cache » veut dire, et le port actuel — qui **reconstruit**
son registre à chaque événement (`dispatch/core.py`) — n'a aucune raison structurelle de rendre deux
fois la même séquence. Il la rend quand même : mesuré.

⚠ **LE ROSTER 2v2 NE DISCRIMINE PAS (I5), ET LE PROBE LE DIT AU LIEU DE LE COMPTER VERT.** Sur les
deux scénarios 2v2, aucune suite du port n'atteint **deux** porteurs communs avec le natif : elles
tiennent toutes en un seul, et une suite d'un élément ne peut révéler aucun ordre faux. Le roster
**5v5** est le seul régime du corpus où (I5) mord — c'est pourquoi il est joué **par défaut**
(`--sans-roster-large` pour l'écarter), et non laissé en option.

## 5. (I2) A ROMPU — et (I4) DIT POURQUOI, au lieu de le supposer

**Cinq** ruptures sur les trois scénarios (1 + 1 + 3, pour 33 couples inter-entité). La plus nette,
sur `SpecificAbilityInit` :

```
77/1142, 77/1142, 79/1217, 79/1216, 83/1028, 83/1030, 77/1482, 77/1037
                                                      ^^^^^^^^^^^^^^^^ l'entite 77 REVIENT
```

Deux causes **rendent la même séquence finale**, et une seule est vraie :

* **(a) PRIORITÉ** — les entrées de queue auraient un `get_Priority` strictement inférieur, donc
  `AddSorted` les aurait poussées derrière tout le monde **dès leur insertion** ;
* **(b) AJOUT TARDIF** — elles ont été inscrites par un **second** appel (`RefreshEntity`), après
  les entités suivantes, et `AddSorted` les a donc appendées **à priorité égale**.

⚠ **Ce qui les sépare est l'HISTOIRE, pas la séquence finale** : sous (b), une passe **antérieure**
à l'ajout est un **préfixe strict** ; sous (a), toutes les passes sont identiques dès la première.
C'est (I4). Mesuré : **toutes** les passes courtes sont des préfixes de la passe finale — **0** hors
sous-séquence sur les trois scénarios. ⇒ **cause (b), AJOUT TARDIF**. La donnée qui manque au port
est la **séquence d'appels**, pas la priorité.

⚠ **Sans (I4), le probe AFFIRMAIT une priorité qu'il n'avait pas lue.** Sa première version
imprimait « un porteur dont `get_Priority` ne rend pas `Normal` — c'est une DÉCOUVERTE ». C'était
une déduction non lue sur le seul canal qui aurait pu la porter, donc invérifiable. Le compte de
passes courtes est le **compte d'exercice** de cette discrimination : **zéro passe courte =
INDISCRIMINÉ**, et le probe l'écrit (cas de `TurnEnd` sur `C1_02`).

Corollaire pour (I3) : le critère d'applicabilité porte sur **les deux** — bloc contigu **et**
absence de rupture. Le seul `bloc_contigu` ne suffisait pas, et la mesure l'a montré :
`UnitFinishedTurn` rend `[67, 53, 53, 53, 53]`, deux blocs contigus, mais le cadet passe **devant**
son aîné.

## 6. (I5) — le registre du PORT n'est PAS en divergence d'ordre, et c'est un résultat

`evaluate_trigger_operation` concatène `abilities(par entité) + globals + effets(par unité)` là où
le natif **lit** une liste persistante. Les deux ordres n'ont aucune raison de coïncider ; sur ce
corpus ils coïncident : **3 événements discriminants, 0 ordre divergent** — et les trois viennent du
seul scénario **5v5**, les deux 2v2 étant non discriminants (§ 4).

⚠ **LE PREMIER CRITÈRE ACCUSAIT LE PORT À TORT, et le chiffre le disait sans le dire** : comparé à
l'**égalité**, le registre du port rendait **4 divergences sur 5** — dont **trois** n'étaient que
des porteurs qu'il ne connaît pas (`port=[49]` vs `natif=[53, 49]`). Le port ne couvre que 86
classes de triggers : sa suite est un **sous-ensemble**. Le critère juste est la **sous-séquence**,
et les porteurs qu'il inscrit sans que le natif les montre sont comptés **à part** —
`ShouldTrigger` n'est appelée qu'**après** `EvaluateTriggerOperation$$CanGetAbilityTrigger`, donc
une entrée filtrée en amont (owner mort, triggers désactivés) est absente de la trace sans être
absente du cache. **1** tel porteur, déclaré.

**Conséquence assumée : le cache porté N'EST PAS CÂBLÉ dans `dispatch/core.py`.** Le brancher
changerait l'ordre d'exécution des triggers — donc le RNG, donc les cascades — pour un gain
**mesuré nul** sur ce corpus. Un changement à ce blast radius se justifie par une divergence
mesurée ; il n'y en a pas. Le câblage devient donc un résidu **conditionné à une mesure**, pas une
tâche en attente (§ 8).

## 7. `Effect_Refresh` AUTONOMES : toujours **0 / 0 / 0 / 0** — et ce volet ne pouvait pas le bouger

`probe_477r21_activation_tree.py` re-joué **après rebase** sur `5d5fad32` (qui livre #477-r21-r1) :
**VERT**, 4 scénarios, `447/447`, `491/491`, `131/131`, `199/199`, **0 ligne hors périmètre**,
`Effect_Refresh` reproduits 40 / 42 / 12 / 18 — et **AUTONOMES 0 / 0 / 0 / 0**, inchangé.
`probe_477r15a_stream_conformance.py` : **VERT**, `204/204` et `316/316`, registre à jour.

Ce n'est pas un maquillage, c'est la conséquence de ce que le § 2 énumère. Pour qu'un
`Effect_Refresh` devienne autonome, il faut que le port **choisisse** l'effet : savoir **quels
effets écoutent `MatchInit`/`MatchStart`**. Cette donnée est `effect.<slot 0x12>` / `<slot 0x2d>` —
non lisible.

Ce que ce volet apporte, et qui n'est pas rien : la **règle** d'ordonnancement est portée et
**mesurée**, et l'entrée copiée en borne (c) se **ventile** désormais en deux termes qui n'étaient
pas distingués :

* la **SÉLECTION** — quels effets/abilities écoutent quel trigger : bloquée par la même cause que
  #477-r26 (blobs `global-metadata.dat`) ;
* l'**ORDRE** — la structure (`AddSorted`, le pré-peuplement, les deux dictionnaires) est portée, et
  la séquence native est **conforme** aux invariants qu'elle impose sur **178 passes complètes**.

Le second terme cesse d'être une inconnue. Le premier reste, et c'est lui qui tient le 0/0/0.

## 8. Les contre-épreuves — `a_morde` publié SÉPARÉMENT

**Live** (5 mutants, cible = l'événement au plus grand nombre de couples inter-entité) :

| mutant | seam | verdict (3 scénarios) |
|---|---|---|
| `ordre_de_creation_ignore` | l'ordre d'appel d'`AddEntity` | mord, rougit |
| `insertion_en_tete` | `add_sorted` (module) | mord, rougit |
| `sans_pre_peuplement` | le ctor | mord, rougit |
| `comparaison_inversee` | `add_sorted` | **NON MORDANT** |
| `append_nu` | `add_sorted` | **NON MORDANT** |

⚠ **Les deux derniers sont inertes PAR LES DONNÉES, pas par construction, et c'est déclaré** : sur
les trois scénarios, toutes les priorités valent `Normal`, donc `AddSorted` **dégénère exactement en
`append`** et `compare_to` ne rend jamais `-1`. Aucun verdict qu'ils rendraient n'aurait de sens.
Le tri est donc gardé **offline**, avec des priorités hétérogènes — le seul endroit où il est
exerçable.

⚠ **UN `a_morde=True` PEUT ÊTRE FAUX, ET IL L'A ÉTÉ 5 FOIS SUR 5.** La première version mutait en
réaffectant `cache.add_ability_or_effect` **sur l'instance** ; `AbilityAndEffectCache` déclare
`__slots__`, donc l'affectation **lève** `AttributeError`, l'exception était capturée par
l'appelant et rendue comme un résultat différent — les cinq mutations se déclaraient mordantes
**sans avoir jamais muté quoi que ce soit**. Le seam correct est le **module** (`add_sorted` y est
résolu par son nom global).

**Offline** (23 tests) : **6 mutants vus ROUGES**, restauration vérifiée —
`append_nu`, `compare_to_inverse`, `remove_triggered_purge_simulated`,
`add_effect_gardes_uniformisees`, `dict_paresseux`, `remove_entity_effet_removeall`.

## 9. Ce qui n'est PAS couvert

* **La SÉLECTION** (§ 7) — la seule chose qui bougerait le 0/0/0.
* **L'ordre INTRA-entité** : `UnitFactory$$AddConfiguredAbilities` est **lu** — passives (`+0xa8`,
  hiérarchie 2) → relique (`+0xb0`, hiérarchie 3) → actives (`+0xa0`, via `AddActiveAbility`) — mais
  ni lui ni `TriggeredAbilityComponent$$TryAdd` ne sont portés. ⚠ Le port range ses cinq chemins de
  registration dans un ordre **différent** (traits → passives → actives → reliques) : la relique y
  est **dernière** là où le natif la met **deuxième**. Non confronté — (I5) ne porte que sur l'axe
  inter-entité.
* **La séquence d'appels `AddEntity` / `RefreshEntity`** — ce que (I4) a nommé comme la donnée
  manquante réelle. Les sites appelants ne sont pas recensés.
* **`+0x58`** : le champ existe (96 octets) mais **le ctor ne l'initialise pas** ; son producteur
  n'est pas identifié, et son slot 0 décide de `GetTriggeredAbilityForNonOwnerPlaybook`.
* **Le volet SIMULATION** (`+0x28`, `+0x48`, `+0x50`) : `StaticBattleRules.TriggeredAbility$$ShouldBeSimulated`
  et `Effect$$ShouldRefreshDuringSimulation` ne sont pas portés — le port rend `False`, ce qui laisse
  ces listes vides. C'est le régime d'un déroulé **réel**, le seul que le harnais joue
  (`ExecuteSimulation` est l'autre voie). Un `True` par défaut peuplerait une liste que personne ne
  relit.
* **Les deux gardes d'`EvaluateAbilityTrigger`** (volet C) et la **séquence de création** des
  entités d'effet (volet D) : hors périmètre, inchangés.

## Résidus

* **#477-r27** — **CÂBLER le cache dans `evaluate_trigger_operation`**, *conditionné à une mesure* :
  (I5) rend **0 divergence d'ordre** sur les deux boards, donc le brancher aujourd'hui changerait
  l'ordre d'exécution des triggers (RNG, cascades) pour un gain nul. Le déclencheur est une
  **divergence (I5) mesurée** — le probe la rendrait ROUGE. Deux régimes candidats, non couverts par
  le corpus actuel et identifiés par la structure : une **unité spawnée** en cours de partie (son
  identifiant dépasse ceux des entités d'effet déjà créées, donc le natif la place **après** elles
  alors que le port place toutes les abilities avant tous les effets), et un porteur dont la
  priorité de cache ne serait pas `Normal`. **Monter ces deux scénarios est la tranche.**
* **#477-r26** (existant, non ouvert ici) s'élargit : à `GetRefreshTriggers` par classe s'ajoutent
  `ITriggeredAbility.<slot 3>` et `IEffect.<slot 0x12>` / `<slot 0x2d>` — **même cause**, mêmes blobs.
  **Point d'ancrage natif à hooker** pour les rendre : le slot `+0x188` de la vtable
  (`get_Priority`) et les slots 3 / 0x12 / 0x2d, invoqués sur les instances du catalogue — la même
  méthode que le `pbGate` de #170, transposée d'`IPlaybook` à `ITriggeredAbility`/`IEffect`. Ce
  capteur exige une fenêtre de reinject ; il n'est pas posé par cette tranche.
