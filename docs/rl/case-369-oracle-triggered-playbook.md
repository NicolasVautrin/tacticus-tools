# #369 — `ncPlaybookPredict` indexé sur le MAUVAIS key-space d'enum

Build lu : `rnca9r7q6c`. Suite de #350-r3b (`docs/rl/case-350r3b-moyennes-triggered.md`), qui a
nommé le verrou sans pouvoir le lever.

## 0. La question binaire

> Peut-on faire charger à `ncPlaybookPredict` le playbook désigné par `TriggeredAbilityType`, de
> sorte qu'un id triggered rende SON playbook (ou une ERREUR FRANCHE), et jamais celui d'une autre
> ability ?

**Oui.** Le natif expose l'overload voulu, et — c'est le point qui rend le durcissement gratuit —
la face TRIGGERED **n'a aucun fallback par défaut** : elle rend `null` quand l'id est inconnu.

## 1. Les QUATRE entrées de `PlaybookDatabase`, et leurs key-spaces

Lues dans la table versionnée `data/symbols/rnca9r7q6c/frida/methods.tsv` (colonnes : type de
retour, puis paramètres avec leur type) — pas déduites d'un nom :

| symbole | paramètres | retour |
|---|---|---|
| `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook` | `ability: ActiveAbilityType, fallbackToDefault: Boolean` | `IPlaybook` |
| `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook` | `ability: TriggeredAbilityType` | `ITriggeredAbilityPlaybook` |
| `IdunBattle.AI.PlaybookDatabase$$LoadPlaybookNonOwner` | `ability: TriggeredAbilityType` | `ITriggeredAbilityNonOwnerPlaybook` |
| `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook` | `specificBehaviour: UnitSpecificBehaviourType` | `IUnitSpecificBehaviourPlaybook` |

Quatre corps DISTINCTS, quatre paires de dictionnaires DISTINCTES sur l'instance — lues au
décompilé, champ par champ :

| face | cache `_loadedX` | registry `_XBuilders` | cache défaut | builder défaut | absent du registry |
|---|---|---|---|---|---|
| ACTIVE | `+0x70` | `+0x68` | `+0x78` | `+0x80` | **fallback** si `fallbackToDefault`, sinon `0` |
| TRIGGERED | `+0x90` | `+0x88` | — | — | **`return 0`** |
| TRIGGERED non-owner | `+0xa0` | `+0x98` | — | — | **`return 0`** |

Les trois corps ont la même forme : `TryGetValue(cache)` → hit ⇒ retour ; sinon
`TryGetValue(builders)` → miss ⇒ sortie ; hit ⇒ appel du builder (slot `+0x18` du delegate),
injection des services de la db, `Add(cache)`.

⚠ **La différence structurante est l'absence de la paire `+0x78`/`+0x80` sur les deux faces
triggered.** Côté ACTIVE, `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook` construit un
`DefaultActiveAbilityPlaybook` quand rien ne matche et que `fallbackToDefault` est vrai ; côté
TRIGGERED, le miss du registry sort par un `return 0` sec. **Le natif lui-même rend donc l'erreur
franche que le harnais devait fabriquer.**

## 2. Le mode de panne — c'est le piège de qualification d'enum, en acte

`playbook-predict.ts::loadPlaybook` résout par
`findMethodByParamClasses(db, "LoadPlaybook", ["ActiveAbilityType", null])`. La désambiguïsation
par TYPE est correcte et délibérée (sans elle, un `findMethodByParamCount(1)` aveugle tombait sur
l'overload `UnitSpecificBehaviourType`) — mais elle fige le key-space sur **ACTIVE**. Un appelant
qui passe un id `TriggeredAbilityType` obtient donc le playbook de l'ability ACTIVE de même id.

Mesuré (#384, runner `MC1_67`, seed 350363, `orksWarboss` u79) :

| `abilityType` demandé | key-space voulu | playbook réellement chargé |
|---|---|---|
| `1103` `LightImUp` | TRIGGERED | `SuperchargePlaybook` (`1103 Supercharge`, ACTIVE homonyme) |
| `1054` `MassiveScythingTalons` | TRIGGERED | `CallRipperSwarmsPlaybook` (`1054 CallRipperSwarms2`) |
| `1247` `FuryOfTheAncients` | TRIGGERED | `DefaultActiveAbilityPlaybook` (aucune correspondance) |

Les deux premières lignes rendent un playbook PLAUSIBLE d'une autre ability ; la troisième rend le
fallback. **Aucune des trois ne signale d'erreur** — un accord obtenu sur cet oracle validerait le
mauvais objet.
