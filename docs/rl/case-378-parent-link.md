# #378 — le lien enfant -> SUMMONER devient une LECTURE

**Question binaire** : le port sait-il, en lisant, quelle unite a INVOQUE quelle autre — ou
continue-t-il de le reconstruire par heuristique et de l'ignorer la ou il compte ?

**Reponse** : il le LIT desormais, sur les trois voies qui en dependaient. La face live attend une
fenetre de reinject (le capteur vit dans `frida/hooks/*`) ; tout le reste est confronte.

## 1. L'ancrage herite etait FAUX — c'est l'autre bout du lien

Le residu de #372 nommait « `ParentComponent`, id @+0x10 ». Verification, par DEUX sources
independantes sur `rnca9r7q6c` :

| composant | champ @+0x10 | type | sens |
|---|---|---|---|
| `IdunBattle.Entities.Components.ParentComponent` | `ChildrenIds` | `List` | parent -> ENFANTS |
| `IdunBattle.Entities.Components.ChildComponent` | **`ParentId`** | **`BEntityId`** (int32) | **enfant -> PARENT** |

* RPC `classFields` live : `ParentComponent.ChildrenIds` offset 16 type `List\`1` ;
  `ChildComponent.ParentId` offset 16 type `BEntityId`.
* Decompile : `IdunBattle.Entities.Components.ParentComponent$$.ctor` construit une `List` a
  `this+0x10` et `...$$ToString` la formate par `EnumerableExtensions$$ToStringIncludingContent` ;
  `IdunBattle.Entities.Components.ChildComponent$$ToString` fait `il2cpp_value_box(Int32,
  *(int *)(this + 0x10))`.

Les deux offsets valent 0x10, ce qui rendait l'erreur INVISIBLE : un port qui aurait lu
`ParentComponent+0x10` en croyant y trouver un id aurait lu un POINTEUR de `List`.

## 2. Le foyer natif : `UnitExtensions$$GetParent`

```
GetParent(childUnit, state, root):
    comp = TryGetComponent<ChildComponent>(childUnit)
    if (!found) return null
    parent = state.GetEntity(comp.ParentId)          // <- PAS de gate sur 0
    if (root && parent != null):
        p2 = GetParent(parent, state, root)
        if (p2 != null) parent = p2                  // remontee jusqu'a la RACINE
    return parent
```

`GetParentUnit(child, state)` = `GetParent(child, state, root = false)` filtre par
`EntityType == Unit`. Consommateurs :

* `IdunBattle.Entities.Selectors.ParentSelector$$Select` — noeud DSL
  `IdunBattleLogic.Entities.DSLSelectors$$Parent(units, root)`. Le ctor recopie `state`@+0x10,
  le selecteur source@+0x18 et le drapeau `root`@+0x20 ; `Select` resout la source puis
  accumule les `GetParent` non nuls dans un `OrderedSet`.
* `IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook$$IsFriendlyKell(unit, ownerUnit)` :
  `comp.ParentId == EntityId(ownerUnit)` puis `IdunBattle.Entities.UnitExtensions$$IsFriend`.
* le noeud `If( AmountIsGreaterThanZero(Parent(EffectSource)), Parent(EffectSource), EffectSource )`
  de `IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`
  (#372).

## 3. `ParentId == 0` VAUT « pas de parent » — structurel, pas empirique

`IdunBattle.Entities.Components.MatchComponent$$NextId` :

```
uVar1 = *(int *)(this + 0x10) + 1 ;  *(uint *)(this + 0x10) = uVar1 ;  return uVar1
```

PRE-incrementeur sur un champ zeroe a la construction — donc le **premier id emis est `1`**. Et
c'est la source UNIQUE : ses xrefs sont exactement les `Add*Operation$$Execute` (unite, machine,
plateforme de MoW, tuile, effet, joueur, ability d'environnement). `0` n'est donc **jamais** un id
d'entite ; c'est le zero d'un champ que `ChildComponent$$.ctor` n'ecrit pas.

MESURE (2026-07-31, `probe_378_parent_link.py`, runner 264, MC1_67/777, `orksWarboss` castant
`Waaagh`(1058)) :

| entite | `decisionView.parentId` (hook courant) |
|---|---|
| u77, u81, u83 (warboss), u85 — roster initial | **0** |
| u108, u110 — les deux `orksOrkBoys` invoques | **83** |

et `dumpEntityComponents(entityId: 0)` rend `entity 0 not found`.

Le capteur normalise donc `0 -> null`. Ce n'est pas un raccourci : `GetParent` ne gate pas sur
zero, il appelle `state.GetEntity(0)` qui rend null — rendre `null` EST le mirror.

Second fait mesure : **chaque unite porte `ChildComponent` ET `ParentComponent`** (l'ECS les cree
systematiquement). La branche « composant absent » du capteur ne se declenche donc pas en pratique ;
on la garde parce qu'elle mirrore la sortie `TryGetComponent == false` du natif.

## 4. Le capteur — TRI-ETAT, et il est LOAD-BEARING

`frida/hooks/features/ai-step/projection.ts::readParentLink` est la source UNIQUE des DEUX canaux
(`decisionView.units[]` via `projectUnitsFull`, `combatSnapshot.units[]` via `rpc-snapshot.ts`) :

| situation | `parentMeasured` | `parentId` |
|---|---|---|
| classe `ChildComponent` irresolue / lecture en erreur | `false` | `null` |
| composant absent (mirror `TryGetComponent == false`) | `true` | `null` |
| `ParentId == 0` (champ jamais ecrit) | `true` | `null` |
| parent reel | `true` | l'id |

Pourquoi DEUX champs plutot que le seul `null` des canaux voisins (`unitFlags`, `traits`) : ici les
deux sens de `null` ne collapsent PAS sur le meme comportement de port. Le seed doit savoir s'il
peut ECRIRE — ecrire le `null` d'une non-mesure EFFACERAIT un `parent_id` que la simulation offline
avait correctement pose au spawn, transformant un capteur muet en REGRESSION de la voie qui
marchait deja.

⚠ Le discriminant ne peut PAS etre `parentId` : le hook courant le publiait deja cote
`decisionView` (depuis `3b9a3b79`), et il vaut `null` (ou `0`) dans les deux mondes.

## 5. Le recensement — qui devinait le parent, et qui le lit maintenant

| site | voie AVANT | APRES |
|---|---|---|
| `runner/components.py::parent_of` / `children_of` | ECS `UnitComponent.parent_id`, pose au spawn par `SpawnUnitOperation` — donc **absent sur tout etat HYDRATE** | seede par `snapshot._load_unit_parent` |
| `entities/selectors/tiles.py::Parent` (noeud DSL) | idem (dict d'unite alimente par l'ECS) | idem |
| `runner/damage_model.py::build_hits_board` -> `parent_by_id` | idem | idem |
| `playbook/prediction/normal_attack.py` | **rien** — la cle etait absente du board | `Scene.parent_by_id` |
| `playbook/noncomparable/supreme_commander.py::_has_friendly_kell` | **heuristique config** `_kit_spawn_visual_ids` (visualId de summon + equipe) | LIT `parentId`, repli PAR LIGNE sur l'heuristique |

Un seul site etait vraiment HEURISTIQUE (le dernier) ; les autres etaient des lectures ECS
AVEUGLES sur etat hydrate — un mode de panne different, et plus silencieux.

Le repli de `_has_friendly_kell` reste PAR LIGNE et non global : `observeBattle` (source des MORTS —
le gate natif accepte un Kell tombe, son selecteur etant `baseSelector + AllDeadUnits()`) ne porte
pas le champ, et la couverture ne doit pas baisser.

## 6. Le port

| piece | fichier |
|---|---|
| capteur TRI-ETAT, source unique des 2 canaux | `frida/hooks/features/ai-step/projection.ts::readParentLink` |
| publication dans `combatSnapshot.units[]` | `frida/hooks/features/ai-step/rpc-snapshot.ts` |
| seed COMBAT | `engine/runner/snapshot.py::_load_unit_parent` |
| table PREDICTION + accesseurs tri-etat | `engine/playbook/scene.py` (`parent_by_id`, `parent`, `parent_measured`, `_parent_from_snapshot`) |
| cablage PREDICTION | `engine/playbook/prediction/normal_attack.py` |
| gate DECISION | `engine/playbook/noncomparable/supreme_commander.py::_has_friendly_kell` |
| probe live (4 etages, verdicts purs) | `scripts/python/probe_378_parent_link.py` |
| garde offline | `scripts/python/tests/engine/test_378_parent_link_offline.py` |

## 7. Validation

**15 gardes offline VERTES**, quatre mutations adversariales confrontees (messages verbatim en tete
du fichier de test) :

| mutant | ce qu'on retire | garde qui rougit |
|---|---|---|
| (a) | le gate `parentMeasured` de `_load_unit_parent` | `test_seed_un_capteur_MUET_ne_touche_a_RIEN` |
| (b) | le filtre `parentMeasured` de `_parent_from_snapshot` (remplace par `parentId is not None`) | `test_scene_distingue_MESURE_SANS_PARENT_de_NON_MESURE` |
| (c) | le cablage `"parent_by_id": scene.parent_by_id` | `test_la_face_PREDICTION_threade_bien_le_substrat` |
| (d) | la LECTURE dans `_has_friendly_kell` (heuristique seule = le port d'AVANT) | `test_isfriendlykell_LIT_le_parent_quand_il_est_mesure` |

⚠ Le mutant (d) d'abord essaye — `elif` change en `if` — s'est revele **NON DISCRIMINANT** : il
DURCIT le gate (conditions conjointes) au lieu de l'assouplir, et les gardes restaient toutes
vertes. La degradation a chasser etant PERMISSIVE, le mutant doit RETIRER la lecture, pas la
doubler.

**Tests cibles rejoues** : `test_dotgg_extra_hits_live.py` 12/12, `test_supreme_commander_live.py`
+ `test_supreme_commander_decision_live.py` 18/18, `test_load_state_turn_state_live.py` 4/4.
Cliquets : `probe_181` (98/98, 0 manquante), `probe_120 --step 0`, `probe_273 --only-scan`,
`probe_365`. `frida-compile` rc 0.

**Face LIVE — NON CONFRONTEE, fenetre de reinject.** `probe_378_parent_link.py` rend **rc 7** avec
le verdict nomme :

```
E0 canal   [not_reinjected] NON CONFRONTE -- le capteur #378 n'est PAS charge : aucune ligne de
`combatSnapshot.units[]` ne porte `parentMeasured`. [...] Rien n'est conclu du natif : ni « pas de
summon », ni « lien absent ».
```

Le MONTAGE, lui, est PRET et discriminant — il a produit les mesures du SS 3. Les quatre etages
(canal / spawn / lecture + coherence des deux canaux / seed) sont cables et s'inverseront seuls.

## 8. Ce qui n'est PAS couvert

* **Le drapeau `root` de `GetParent`** (remontee recursive jusqu'a la racine) n'est pas porte : le
  capteur publie le lien DIRECT et `entities/selectors/tiles.py::Parent` resout un seul niveau. Le
  natif l'expose (`ParentSelector`@+0x20, 2e argument de `DSLSelectors$$Parent`) ; aucun call-site
  porte ne le demande a `true` a ce jour. Une chaine summon-de-summon serait donc tronquee.
* **Le lien RECIPROQUE `ParentComponent.ChildrenIds`** n'est toujours pas lu : `children_of` le
  DERIVE par balayage de `state.entities`. Equivalent tant que le port materialise toutes les
  entites de la bataille ; le natif, lui, tient la liste.
* **Le regime `parentMeasured=false`** n'a pas ete OBSERVE (il exigerait que `findClassAnywhere`
  echoue sur `ChildComponent`). Il est exerce offline, pas live.
* La confrontation live du chemin `combatSnapshot -> _load_unit_parent -> parent_of` attend la
  fenetre — voir SS 7.
