# #10015 — `fire_on_death` mirrore `get_AllowForDeadOwner`, pas un `IsAtomic`

**Build mesuré : `t6dpr4k06g` (2026-08-15).** Tout chiffre de cette fiche se re-dérive
(`python scripts/python/probe_10015_allow_for_dead_owner.py`), il ne se cite pas.

## 1. Le faux nom, et pourquoi il ne pouvait pas se voir

Le gate de `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` qui dispense une
triggered-ability du test `UnitExtensions$$IsAlive(owner)` était cité dans tout le dépôt comme
`IsAtomic(ability)` — dans `dispatch/core.py`, dans `triggers/base.py`, dans le probe et le test de
la famille #462, dans trois case-docs et trois lignes de `backlog.md`. Le pseudo-C ne porte aucun
nom : il rend `FUN_180002590(8, DAT_183389188, ability)`, c'est-à-dire **un appel au slot 8 d'une
interface** (`FUN_180002590(slot, interface, obj)` parcourt `klass->interfaceOffsets` à `+0xb0`,
compte à `+0x12e`, puis saute dans la vtable à `klass + 0x138 + idx*0x10`).

Les deux inconnues se **lisent** :

* `DAT_183389188` = `IdunBattle.Entities.Abilities.ITriggeredAbility` — c'est le type **déclaré**
  du paramètre (`frida/methods.tsv` :
  `CanGetAbilityTrigger(owner: IEntity, ability: ITriggeredAbility, onlyNonAtomic: bool)`), et
  **trois** concordances slot/arité le confirment indépendamment dans
  `...$$EvaluateEffectTriggerEffectAbilities` : slot 2 = `ShouldTrigger` (2 args), slot 4 =
  `ExecuteBy` (3 args), slot 8 = `get_AllowForDeadOwner` (0 arg, booléen) ;
* la table des slots vient du champ `slot` d'`Il2CppMethodDefinition` dans `global-metadata.dat` —
  même dérivation que `data/symbols/<build>/metadata/interface_slots.tsv` (`il2cpp_metadata.locate_types`).

**Une propriété d'atomicité existe bel et bien**, et c'est là que le faux nom devient dangereux :
`ITriggerable` slot 0 = `get_AllowInAtomicMode`, lue par la **même** fonction quelques instructions
plus bas, sous `IMatchState` slot 22 = `get_InAtomicMode` et sous le paramètre `onlyNonAtomic`. Les
deux jeux de déclarants sont quasi disjoints — **44** types déclarent `get_AllowForDeadOwner`,
**25** déclarent `get_AllowInAtomicMode`, et quatre seulement portent les deux (`ThrillSeekers`,
`DrawFire`, `FloatingDeath_Attack`, `Lifewards`). Confondre les deux, c'est lire la mauvaise
propriété **sans qu'aucune erreur ne soit levée**.

## 2. La méthode : lire la valeur d'un corps DÉDUPLIQUÉ

`get_AllowForDeadOwner` a un corps trivial. Sur les 44 déclarants, **zéro** n'apparaît dans
`frida/methods.tsv` ni dans `ghidra/functions.tsv` : les deux tables sont indexées par ADRESSE, et
IL2CPP n'y laisse qu'un propriétaire arbitraire par corps partagé. « `<Classe>$$get_AllowForDeadOwner`
n'y est pas » ne prouvait donc rien — c'est le faux négatif que le CLAUDE.md décrit, rencontré ici en
grandeur nature.

La RVA se résout par le **TOKEN** :

1. `Il2CppMethodDefinition` porte `token` à `entry_size - 12` (préfixe `0x06` vérifié) ;
   `rid = token & 0xFFFFFF`.
2. `Il2CppCodeGenModule.methodPointers` est indexée par `rid - 1`. On ne suppose **aucun** layout :
   on prend des couples `(rid, VA)` **connus** (méthodes au nom unique dans leur classe et dans
   `methods.tsv`), on cherche chaque VA dans le PE, et on retient l'**intersection** des bases
   `pos - (rid-1)*8`. Une base unique ⇒ table identifiée ; puis **tous** les couples connus sont
   relus. Mesure : **414/414 justes**.
3. Le corps se lit : `b0 01 c3` = `mov al,1 ; ret` = vrai ; `32 c0 c3` = `xor al,al ; ret` = faux.

⚠ **SURCHARGER NE VEUT PAS DIRE VRAI.** `BaseTriggeredAbility` rend FAUX (le défaut) et **4 des 43
surcharges rendent FAUX aussi** (`DevastatingRefrain_AttackAbility`,
`MalleusRocketLauncher_AttackAbility`, `GazeOfMagnus_ApplyEngagementAbility`,
`GazeOfMagnus_AttackAbility`). Un a priori « override ⇒ vrai » — le raccourci naturel, et celui
qu'on allait prendre — aurait écrit **4 valeurs fausses**. C'est la raison d'être de l'étage 0.

⚠ **ET LA VALEUR D'UNE FEUILLE PEUT VENIR D'UN ANCÊTRE.** `PowerUpHealingAbility` ne déclare rien et
hérite le VRAI d'`APowerUpAbility` : sans remontée de chaîne (`frida/classes.tsv`), la confrontation
port ↔ build rend **trois faux désaccords**. La chaîne est remontée jusqu'au premier déclarant.

## 3. Ce que la confrontation port ↔ build a trouvé

`fire_on_death` du port doit valoir `get_AllowForDeadOwner` du build. Sur les **190** classes
ability du registre de triggers : **98 accords, 10 désaccords, 82 non appariées** par l'appariement
heuristique (le symbole natif cité en docstring).

⚠ **L'APPARIEMENT HEURISTIQUE NE PEUT PAS NOURRIR UN CLIQUET**, et c'est mesuré : sur les 10, **5**
sont de faux appariements — il rattache `FuelledByFuryReviveAbility` à
`FuelledByFury_ExtraDamageAbility` (la native de la revive est `FuelledByFury_ReviveAbility`, qui est
VRAIE), `RelicOfLostCadiaSummonUnitAbility` à `RelicOfLostCadiaAbility` (au lieu de
`RelicOfLostCadiaAbility_SummonUnit`, VRAIE), et les **trois** classes Haywire du port à la **même**
native. Un cliquet nourri d'un appariement devinable se ferait désarmer à la première fausse alerte.
Le cliquet porte donc sur `NATIF_DU_PORT`, écrit **à la main** et seulement pour ce qui a été lu
(9 entrées) ; l'heuristique reste un **inventaire** (`--croiser`), jamais bloquant.

Les désaccords **instruits** :

| classe du port | port | build | verdict |
|---|---|---|---|
| `SynapticLinchpinAbility` | ~~False~~ **True** | TRUE | **CORRIGÉ** (#937-r1) — corps partagé avec `FinalJusticeAbility` |
| `EnvAmbushResurrectAbility` | True | FALSE (hérité) | **GARDÉ** — l'owner natif d'une `Env*Ability` n'est peut-être pas une unité ; cf. §5 |
| `ControlEdictAbility` | False | TRUE | dette `#10015`, face non relue |
| `LightImUpAbility` | False | TRUE | dette `#10015`, face non relue |
| `LordOfTempestsAddIceAbility` | False | TRUE | dette `#10015`, face non relue |

## 4. `#937-r1` — la branche `owner MORT + FinalJustice` de `SynapticLinchpin` vit

`SynapticLinchpinAbility` **surcharge** `get_AllowForDeadOwner` (slot 22 de sa vtable,
`flags=0x08c6` : pas de `NewSlot`, donc un override), et son corps est **le même que celui de
`FinalJusticeAbility$$get_AllowForDeadOwner`** — `b0 01 c3` = **VRAI**. Le natif laisse donc passer
un porteur mort jusqu'à `ShouldTrigger`, où le disjunct tranche.

Le disjunct, relu : `SynapticLinchpinAbility$$CreateTrigger` bâtit
`Not(OwnerIsActor & TriggeringAbilityIs(FinalJustice))` puis le passe à
`IdunBattleLogic.Entities.DSLTriggers$$On(triggerType, ownerNeedsToBeAlive: IAbilityTrigger)`, dont
le corps est `Event(t) & (this.<+0x20> | Not(X))`. L'identité de `<+0x20>` se lit sur **l'autre**
surcharge, booléenne : elle choisit `<+0x20>` quand `ownerNeedsToBeAlive` est vrai et `<+0x70>`
sinon ⇒ `<+0x20>` = `OwnerIsAlive`, `<+0x70>` = le nœud toujours-vrai. Le gate effectif est donc
`OwnerIsAlive | (OwnerIsActor & TriggeringAbilityIs(FinalJustice))`.

**Correctif** : `fire_on_death = True`. **Garde** :
`tests/engine/runner/test_937r1_synaptic_linchpin_porteur_mort_offline.py`, 8 bras. L'assertion
porte sur le **comportement** (`matches` est-il APPELÉ ?) et non sur la valeur de l'attribut :
`fire_on_death` n'a qu'un seul lecteur dans tout `engine/**`, donc un retrait ne casserait aucun
test existant et la branche redeviendrait inatteignable **en silence**. Contre-épreuve jouée :
`fire_on_death = False` ⇒ **2 bras indépendants** rougissent.

⚠ **LE TÉMOIN A DÛ ÊTRE CORRIGÉ, et l'erreur est instructive** : première écriture, le témoin
« porteur vivant » était un allié Synapse qui ne **porte pas** le passif — il n'entre donc à aucun
titre au registre, et son rouge n'avait rien à voir avec la vivacité. Seul un second porteur, vivant,
isole l'axe mesuré.

**Non confronté live** : résidu `#937-r2`. La contrainte non évidente y est écrite —
`FinalJusticeAbility.matches` refuse sur `ev.overkill`, et l'overkill natif est `dmg >= 2*PV`, donc
le coup fatal doit tomber dans `PV_restants <= dmg < 2*PV_restants` : user le porteur par attrition
fait justement **échouer** le montage.

## 5. Ce que la mesure a **retourné** — #462-…-r3-r1-r2-r1

La fiche de ce résidu affirmait qu'`EnvAmbushResurrectAbility` « est ATOMIQUE, donc dispensée du
gate `IsAlive` ». **Deux erreurs en une** : le nom, et le fait. Sa table de méthodes ne porte que
`CreateTrigger`, `CreateBehaviour`, `GetValidDecoys`, `GetUnitsEligibleForResurrect`,
`GetIsAlliedWithCurrentPlayerUnitTrigger`, `GetIsCurrentPlayerUnitTrigger`, `.ctor` — elle **hérite**
donc le FAUX de `BaseTriggeredAbility`. Si son owner natif était une unité, le natif gaterait le
cadavre dehors exactement comme le port, et c'est le port qui serait trop **permissif**.

Ce qui reste ouvert n'est donc plus l'atomicité mais **l'identité de l'owner** : `Env*Ability` est
une famille de **25** classes d'environnement, `EnvAmbushResurrect` n'apparaît **nulle part** dans le
gameconfig (0 occurrence — aucune voie de kit ne l'attribue), et son `CreateTrigger` ne porte **aucun**
prédicat d'owner. Si l'owner n'est pas une unité, `IsUnit(owner)` est faux et les **deux** gates sont
sautés. L'attribut est gardé : le retirer sur la seule foi d'une valeur héritée alignerait le code sur
une prémisse non établie — le vice que `#1045-r2` documente.

## 6. Résidus

* `#10015` — la dette (4 désaccords instruits) et les **181** classes du registre sans appariement
  natif déclaré. `NATIF_DU_PORT` n'en porte que 9.
* `#10015-r1` — le gate ATOMIQUE (`get_InAtomicMode` + `get_AllowInAtomicMode` + `onlyNonAtomic`)
  n'est porté sur **aucune** des deux faces. 24 abilities déclarent `get_AllowInAtomicMode = true`,
  donc il n'est pas décoratif. `BLOCAGE: etage` — le substrat manquant est le compteur de mode
  atomique (`MatchState$$Increase/DecreaseAtomicModeCounter`).
* `#10015-r2` — la chaîne native qui retire du plateau une unité **tuée** (cf.
  `case-462-r4b-substrat-mort-cinq-residus.md` §1).
* `#937-r2` — la confrontation live de la branche `owner MORT + FinalJustice`.
* **Sites encore au faux nom, hors foyer de cette tranche** :
  `engine/runner/operations/triggers/loki/haywire_mine.py` et `.../shield_of_faith.py`, plus
  `case-462-r4b-r1-r1-r1-r1-c-r1-effets-de-tuile.md`. Ils entrent dans `#10015`.
