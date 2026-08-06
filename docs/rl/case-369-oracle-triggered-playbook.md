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

## 3. `TriggeredAbilityPlaybook<T>` est une hiérarchie SÉPARÉE — pas d'`Evaluate`

Lu dans `data/symbols/rnca9r7q6c/frida/classes.tsv` (colonne « parent ») :

```
IdunBattle.AI.Playbook.Playbook`1                  -> IdunBattle.AI.Playbook.BasePlaybook
IdunBattle.AI.Playbook.ComparablePlaybook`1        -> IdunBattle.AI.Playbook.Playbook`1
IdunBattle.AI.Playbook.NonComparablePlaybook`1     -> IdunBattle.AI.Playbook.Playbook`1
IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1  -> System.Object          <-- AUCUN ancêtre commun
```

⇒ **Corriger le seul chargement ne suffit PAS.** `ncPlaybookPredict` invoque `Evaluate(unit,
UnitPosition[, tiles])`, méthode de `Playbook<T>` : un playbook triggered ne l'a pas. Sa surface,
lue exhaustivement dans `data/symbols/rnca9r7q6c/ghidra/functions.tsv` (les gshared sont absents du
dump Frida, présents dans Ghidra) :

```
CalculateAttackUtilityInSteps / ...Internal     GetAbilityEntities   GetUtilityValue
CalculateMovementUtilityInSteps                 GetAbilityState (x2) Init
CalculateRepairUtilityInSteps / ...Internal     GetAbility<T>        IsMeleeAttack / IsRegularAttack
CalculateUtilityFromDamageEvent                 FilterMovementTilesForMaxMovement
```

Les trois porteurs de #350-r3b sont bien de cette branche (`classes.tsv`, taille 96) :
`LightImUpPlaybook`, `MassiveScythingTalonsPlaybook`, `FuryOfTheAncientsPlaybook`.

⚠ **`HeavyRailRiflePlaybook` n'en est PAS** : son parent est `NonComparablePlaybook`1`. C'est un
playbook de la branche ACTIVE qui va chercher une ability triggered par
`Playbook<T>$$GetAbility<T>` — il répond donc déjà à `ncPlaybookPredict` tel quel, par la voie
`evaluate`. #350-r3b le rangeait avec les trois autres ; la hiérarchie dit le contraire.

## 4. Le chemin natif à mirrorer, de bout en bout

`IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext`,
lu ligne à ligne (c'est la boucle qui fait jouer TOUS les playbooks triggered d'un caster) :

```
total = Fix64(0)
si case.caster != null :
    foreach abilityEntity dans <composant d'abilities du caster> :
        abilityType = <getter d'enum sur l'entité d'ability>
        playbook   = PlaybookDatabase$$LoadPlaybook(this.<+0x48>, abilityType)   # overload TRIGGERED
        si playbook == 0 : CONTINUE                                              # <-- null = « pas de playbook »
        it = <ITriggeredAbilityPlaybook slot 3>.CalculateAttackUtilityInSteps(playbook,
                 case, this.<+0x58 : getUtilityVal>)
        total += chaque Fix64 yieldé
yield total
```

Trois enseignements, tous lus :

1. **Le natif charge par l'overload `TriggeredAbilityType`** — confirmation directe du fix.
2. **`playbook == 0` est un cas NORMAL du natif** (`continue`). Rendre une erreur franche sur null
   ne fabrique donc rien : c'est la seule lecture fidèle.
3. **L'entrée invocable est `CalculateAttackUtilityInSteps(UtilityAttackCase, getUtilityVal)`**, et
   elle exige un `UtilityAttackCase`. Celui-ci se construit par la factory statique
   `IdunBattle.AI.Utilities.UtilityAttackCase$$Base(caster, casterPosition, target, abilityType)`
   (overload `casterPosition: UnitPosition` — celui qu'utilisent
   `ComparablePlaybook<T>$$CalculateActionUtility` et `Playbook<T>$$GetTargetUtilityDiffOnDisplace` ;
   l'autre overload prend un `casterTile: IEntity`).

`IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GetUtilityValue`
**tolère un `getUtilityVal` nul** : `if (dict == null || !TryGetValue(...)) { log(warning); return 0; }`.
Un appel sans les poids ne lève donc pas — il rend 0 sur chaque poids, ce qui décale l'UTILITÉ mais
laisse intacte la prédiction de dégât capturée au ctor.

## 5. Re-confrontation du capteur hérité — CONFIRMÉ, avec une précision

#350-r3b affirmait « le capteur `ProbableDamageEvent$$.ctor` déjà posé est le bon : les 4 call-sites
half-to-even le traversent ». Re-dérivé des **xrefs entrantes** du ctor, pas hérité :

| call-site half-to-even | traverse le ctor |
|---|---|
| `LightImUpPlaybook$$CalculateAttackUtilityForMainTarget` | **appel DIRECT** |
| `LightImUpPlaybook$$CalculateAttackUtilityForSecondaryTarget` | **appel DIRECT** |
| `MassiveScythingTalonsPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext` | **appel DIRECT** |
| `LightImUpPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext` | **INDIRECT** — absent des xrefs du ctor ; il appelle `…ForMainTarget` et `…ForSecondaryTarget`, qui le construisent |

**Verdict : le capteur est le bon.** Et la chaîne qui le rend DISCRIMINANT est lue dans
`LightImUpPlaybook$$CalculateAttackUtilityForMainTarget` :

```
state  = TriggeredAbilityPlaybook<T>$$GetAbilityState(this, case.caster)
node   = MassiveScythingTalonsAbility$$GetAverageDamage(this.<+0x58 : ability>, state)   # corps DEDUPLIQUE
damage = node.<IAmountFormula slot 1 = Calculate>(...)                                   # <-- half-to-even
profile= BaseTriggeredAbility$$GetDamageProfile(this.<+0x58>)
pred   = <IBattleQuery slot 0x28 = GetMultiHitAttackPrediction>(query, case.caster, case.target,
                                                        case.<+0x18>, case.<+0xf0..+0x108>,
                                                        damage, profile, hits)
ProbableDamageEvent$$.ctor(&pde, case.target, &pred, &probability, &weight)
TriggeredAbilityPlaybook<T>$$CalculateUtilityFromDamageEvent(this, &pde, ...)
```

La valeur half-to-even entre dans le `DamagePredictionResult` **par l'argument `damage` de
`GetAttackPrediction`** : un écart de 1 sur la moyenne se propage donc dans les bornes capturées.
C'est précisément ce que le capteur lit — il est discriminant, pas seulement présent.

⚠ Nuance mesurée : `LightImUpPlaybook.u003C…u003Ed__2$$MoveNext` appelle AUSSI `GetAverageDamage`
sur un chemin qui ne construit AUCUN `ProbableDamageEvent`. **Cette lecture-là n'est pas
observable par ce capteur** — résidu nommé, hors périmètre.

## 6. Ce qui est livré

- **`frida/hooks/features/ai-step/triggered-predict.ts`** (NEUF) — `loadPlaybookByKeySpace`
  (`active` | `triggered` | `triggeredNonOwner`), `buildUtilityAttackCase`,
  `invokeTriggeredAttackUtility`. Tout est résolu par `findMethodByParamClasses` sur le TYPE du
  paramètre : c'est la seule chose qui sépare les overloads homonymes.
- **`frida/hooks/features/ai-step/rpc-nc-predict.ts`** — champ `abilityKind` (défaut `active`,
  **ÉCHOÉ dans la réponse**), refus explicite d'un `via` de l'autre famille, et **`allowDefault`
  à `false` par défaut** : un id ACTIVE sans playbook bespoke rend désormais une ERREUR au lieu du
  `DefaultActiveAbilityPlaybook`.
- **`scripts/python/catalog_inject.py`** — `patch_ability_variables` /
  `write_variable_patched_seed_bc` : le montage nommé qui force un régime `minDmg + maxDmg ==
  3 mod 4`. Il **neutralise le multiplicateur de rareté** (`minDmg`/`maxDmg` sont dans
  `VariablesAffectedByUnitRarityMultiplier`) pour que la valeur ÉCRITE soit la valeur LUE — sans
  quoi la parité visée, seul axe discriminant, serait perdue en silence.
- **`scripts/python/probe_369_playbook_keyspace.py`** + **`tests/test_369_playbook_keyspace_offline.py`**.

⚠ **L'ÉCHO D'`abilityKind` EST LA PIÈCE QUI REND LE RESTE HONNÊTE.** Sans lui, un appelant ne peut
pas distinguer « le hook a interrogé le key-space triggered » de « le hook est antérieur et a
répondu par l'ACTIVE ». Il lirait alors des `captured` fidèles… d'une autre ability.

## 7. Validation

### Confronté (mesuré ce jour, runner `MC1_67`, seed 36901, `orksWarboss` u81)

**Le mode de panne, re-mesuré sur mon propre montage** — pas hérité de #384 :

| id demandé (`abilityKind: "triggered"`) | `playbookClass` rendu par le hook DÉPLOYÉ | `abilityKind` dans la réponse |
|---|---|---|
| `1103` | `SuperchargePlaybook` | **absent** |
| `1054` | `CallRipperSwarmsPlaybook` | **absent** |
| `1247` | `DefaultActiveAbilityPlaybook` | **absent** |

**Le durcissement ne casse aucun consommateur** — les **8** abilities interrogées par tous les
appelants existants de `ncPlaybookPredict` (`probe_344`, `probe_350r3*`, `probe_360`, `probe_362`,
`test_356`, `test_350r3`, `test_360`) chargent un playbook BESPOKE, donc aucune ne dépend du
fallback :

```
1040 SpawnPoxwalkersPlaybook   1042 FlailSwingPlaybook        1111 LivingBatteringRamPlaybook
1132 KillMaimBurnPlaybook      1147 HadesAutocannonsPlaybook  1148 DaemonicOrdnancePlaybook
1173 ArcScourgePlaybook        1202 VigilanceEternalPlaybook
```

**Le montage s'installe** : `rl_duel build --seed-bc <seed patché>` monte une bataille saine avec
`orksWarboss` déployé, sans « system error ».

**La collision est massive** (`data/symbols/rnca9r7q6c/frida/enums.tsv`) : **233** ids présents dans
les deux enums, dont **231** désignant des membres de nom différent. Ce n'est pas un cas limite.

### Garde vue ROUGE — trois mutations adversariales

| mutation | résultat |
|---|---|
| (a) `triggered: "TriggeredAbilityType"` → `"ActiveAbilityType"` (le bug, réintroduit) | **1 failed, 9 passed** |
| (b) suppression de l'écho `abilityKind: keySpace` du littéral `out` | **1 failed, 10 passed** |
| (c) montage reposé sur le couple nominal `831 + 1109` (≡ 0 mod 4) | **1 failed, 10 passed** |

⚠ **La mutation (b) est passée VERTE au premier essai, et c'est le fait le plus utile de cette
validation.** La garde cherchait `"abilityKind: keySpace"` dans TOUT le fichier ; comme la même
chaîne apparaît dans les retours d'ERREUR (`return { ok: false, abilityKind: keySpace, … }`),
supprimer l'écho du chemin SUCCÈS ne la faisait pas bouger. Corrigé par une extraction ciblée du
littéral `out` (`_success_payload`), et figé par un test sur sources synthétiques.
**Une garde qui matche n'importe où dans un fichier ne garde rien.**

### Confronté après reinject (2026-07-31) — les TROIS contrôles sont joués

Le correctif a été réinjecté, puis exercé. `probe_369_playbook_keyspace.py` rend **`rc = 0`** sur ses
cinq étapes. Détail des deux verrous qui restaient, et de leur levée : **`case-375-capteur-triggered-muet.md`**.

1. **Routage** — VERT : `1103 → LightImUpPlaybook`, `1054 → MassiveScythingTalonsPlaybook`,
   `1247 → FuryOfTheAncientsPlaybook`.
2. **L'invocation `CalculateAttackUtilityInSteps` aboutit** — le doute portait sur la résolution du
   corps **gshared** depuis la classe concrète : il est levé, `findMethodByParamCount` remonte
   jusqu'au parent INFLATÉ et l'`IEnumerator<Fix64>` s'itère. Elle rend `[0]` et ne capture rien, et
   **c'est la réponse correcte du natif** : le `UtilityAttackCase` construit par le harnais ne NOMME
   aucune ability, donc `TriggeredAbilityPlaybook<T>$$IsRegularAttack` refuse en tête des deux
   machines à états (#375 §1). `1247` est muet pour une raison DIFFÉRENTE — son playbook ne surcharge
   pas la voie attaque.
3. **Les `captured` portent 972, pas 971** — CONFRONTÉ par
   `via: "attackUtilityForMainTarget"` (call-site natif qui appelle `ProbableDamageEvent$$.ctor`
   directement, sans gate), sur une échelle à trois montages :
   `831+1111 → (1166, 1748…)`, `831+1112 → (1167, 1749…)`, `831+1113 → (1167, 1749…)`.
   Le régime discriminant tombe sur la référence HAUTE. Reproduit sur un second couple discriminant
   (`700+1003`) et un second couple (board, seed) (`C4_09`/999).

⚠ **La fixture de cette fiche était ÉCRITE mais jamais JOUÉE** jusqu'à #375 :
`rl_collect_batch._load_seed_bc` re-synthétisait `LightImUp` depuis le gameconfig vivant et revertait
`minDmg`/`maxDmg`, EN SILENCE (le couple réellement joué était le nominal `831+1109 ≡ 0 mod 4`, non
discriminant). Le montage exige donc, désormais, le sidecar d'épinglage
`<seed-bc>.pins.json` — que `write_variable_patched_seed_bc` pose tout seul.

⚠ **Et l'écart de 1 n'est observable qu'armure de la cible à 0** : à l'armure nominale l'étage aval
(profil × armure) écrase l'écart, les trois montages coïncident, et le verdict serait vert et vide.

Non couvert : `getUtilityVal` n'est pas fourni, donc l'UTILITÉ rendue est minorée (chaque poids vaut
0). La réponse le dit (`utilityWeightsProvided: false`). Les `captured`, eux, ne dépendent pas des
poids. La voie `attackUtilityInSteps` reste muette tant que le correctif `attackAbility` de #375
n'est pas réinjecté.
