# #475 — Les adresses ÉPINGLÉES des hooks : refuser au lieu d'attacher en aveugle

## 1. Le défaut

Six RVA écrites en dur servaient d'ancrage dans `frida/hooks/**`, en violation de la règle
« résolution runtime, pas de RVA hardcodées ». La dégradation est **muette** :
`Interceptor.attach` réussit sur du code arbitraire. Une adresse périmée ne se voit ni à
l'erreur ni au crash — seulement à un capteur qui ne fire jamais. C'est ce qui a coûté à #597
de lire `IsValidAction` au décompilé.

**Mesure du 2026-08-04** (build courant `rnca9r7q6c`, table `data/symbols/<build>/ghidra/`) :
**6/6 périmées**, pas 4/6.

| constante | VA | ce qu'elle désigne sur le build COURANT |
|---|---|---|
| `bucket-audit RVA.addAction` | `1813fbcc0` | `thor.Client.Services.PlayerEventService$$SendPlayerEventu003Cobject,_objectu003E+0x1b0` |
| `bucket-audit RVA.addActionToBucket` | `1813fbb60` | `…SendPlayerEventu003Cobject,_objectu003E+0x50` |
| `bucket-audit RVA.isValidAction` | `1813fc660` | `UnityEngine.UIElements.PointerEventsHelper$$SendEnterLeaveu003Cobject,_objectu003E+0x550` |
| `bucket-audit RVA.chooseAction` | `1813fc0d0` | `…SendPlayerEventu003Cobjectu003E+0x260` |
| `modifier-observe CRIT_CTOR_RVA` | `180fff850` | `IdunBattle.Entities.Effects.AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal+0x130` |
| `modifier-observe DISPATCH_HELPER_RVA` | `1800267c0` | `FUN_180026780+0x40` |

Les six désignaient exactement leur cible sur `gqfc5mff6c` (vérifié dans la table archivée) :
la péremption est le changement de build, rien d'autre.

## 2. Verdict par constante

| # | constante | verdict ÉTABLI | traitement |
|---|---|---|---|
| 1-4 | `bucket-audit RVA.*` | **résoluble** — mais l'était MAL (§3) ; les 4 constantes étaient déjà **mortes** (`void RVA;`) | supprimées ; résolution refaite |
| 5 | `CRIT_CTOR_RVA` | **non résoluble** ET **morte** — `CritDamageInfo$$.ctor` est absent des DEUX tables du build courant (ghidra ET `frida/methods.tsv` ne déclare aucune méthode pour cette classe) ; corps de ctor de ValueType, dédupliqué. Aucun attachement depuis le retrait du hook (freeze `UnityFreezeDetector`) | supprimée |
| 6 | `DISPATCH_HELPER_RVA` | **non résoluble** — `FUN_1800267c0` est un placeholder sans `MethodInfo`. **La seule des six encore ARMÉE** | garde-fou : `pinnedAddress`, qui REFUSE (§4) |

## 3. `Bucket<T>` : résoluble, mais la résolution en place était FAUSSE

`findClassAnywhere("IdunBattle.AI.BucketSystem", "Bucket\`1")` **réussit** (classe présente au
runtime et dans `frida/classes.tsv`), et `findMethod` rend un pointeur. Mais c'est le **thunk
d'invocation de la définition générique**, pas le corps pleinement partagé (#259 §3).

Mesuré live le 2026-08-04, RPC `resolveMethodPtr`, confronté à `ghidra/functions.tsv` :

| méthode | ce que `findMethod` rendait | ce que Ghidra nomme à cette VA | le corps gshared attendu |
|---|---|---|---|
| `AddAction` | `180115160` | `Unity.Services.Core.Device.IUserIdentifierProvider$$set_UserId` | `1814eff60` |
| `IsValidAction` | `18011bc90` | `UnityEngine.Purchasing.ITransactionLog$$HasRecordOf` | `1814f0900` |
| `ChooseAction` | `1801221d0` | `IActivationFactory$$ActivateInstance` | `1814f0370` |
| `AddActionToBucket` | `18012bc30` | `MinimumBinaryHeap\`1$$u003CMinHeapifyu003Eg__UpdateSmallestIfCandidateIsSmaller|21_1` | `1814efe00` |

Ce sont des **corps triviaux dédupliqués** — les quatre partagent le même `invoker`
(`FUN_1801f8600`). Symptôme concordant : `bucketAuditStatus` rendait `enabled: true`,
`listeners: 5` et **0 fire** sur les cinq compteurs. Un capteur qui se déclare armé et ne
mesure rien.

**La correction** applique la recette mesurée de #259-b (« le `MethodInfo` d'une instance
INFLATÉE porte le corps partagé »), par le **type de RETOUR** d'un playbook concret :
`EvaluateNonComparable` / `EvaluateInternal` rendent
`IdunBattle.AI.BucketSystem.Bucket<IdunBattle.AI.ActionGenerators.UnitAction>` ;
`il2cpp_method_get_return_type` (export **présent**, vérifié dans la table d'export du PE)
+ `il2cpp_type_get_class_or_element_class` donnent l'`Il2CppClass*` inflaté, et `findMethod`
dessus donne le corps.

**Garde structurel** : si l'instance inflatée rend la **même** adresse que la définition
ouverte, on est retombé sur le thunk → on **refuse d'attacher** et on le dit. Sans ce test,
une régression redeviendrait indiscernable d'un capteur qui marche.

⚠ **NON CONFRONTÉ — attend une fenêtre de reinject** (résidu `#475-r3`, montage décrit au
backlog). Ce qui EST vérifié sans reinject : que la classe et les méthodes existent, et que le
corps visé est bien celui que Ghidra nomme.

## 4. Le foyer — `frida/hooks/il2cpp/build-pin.ts`

Pendant **live** de `scripts/python/build_pin.require_pinned` (#431), qui tient le même
contrat pour la face **offline**. Même sémantique, délibérément : le porteur **déclare** son
build, le foyer le **confronte** au build réellement chargé, et **refuse en le disant**.

- Le build chargé se lit sur `Module.path` (`…/tacticus/games/<build>/GameAssembly.dll`).
- **Tri-état** : `null` ne veut jamais dire « autre build », il veut dire « pas mesurable »,
  et chaque panne porte son nom (module introuvable / chemin absent / disposition inattendue).
  Dans les deux cas le pin est refusé — on n'attache pas sur un doute.
- Un pin porte `va` (VA ghidra **complète** — la RVA se calcule en code), `build`, `symbol`
  verbatim, `what`, et `how` (la procédure de re-dérivation, sinon le refus est un cul-de-sac).
- C'est le **seul** module où `il2cppBase.add(<constante>)` a le droit d'exister.

`DISPATCH_HELPER_PIN` a été épinglé sur `gqfc5mff6c` — c'est-à-dire **refusé** sur les builds
suivants. C'était la réponse honnête : la VA est mesurée sur ce build-là, la re-mesurer demande
une session ghidra. **Fait le 2026-08-15, cf. §8** (résidu `#475-r2` fermé).

**`scorer-damage-trace.ts` y passe aussi** : ses **13** adresses épinglées (11 code + 2 `DAT_`)
ont été déclarées sur `rnca9r7q6c`, donc le pin était un **no-op** — aucun changement de
comportement, et la mine désarmée pour le prochain build. Son en-tête disait déjà « au
prochain build ces RVA pointent du code aléatoire » ; il ne l'**empêchait** pas. Les 8
re-dérivables par symbole ont migré avec #10011, les **5 derniers** au §8.

## 5. Le cliquet — `probe_475_pinned_addresses.py`

**R1 — arithmétique d'adresse hors foyer.** Interdits : `il2cppBase.add(`,
`Module.findBaseAddress(`, tout littéral hexa dans `]0x180000000, 0x190000000[` hors d'un pin
déclaré, et tout `.add(<littéral ≥ 0x100000>)` (un champ de struct ne va pas à un mégaoctet,
une RVA dans une image de 60 Mo si — **0 occurrence** sur les 193 fichiers du périmètre, donc
aucun faux positif).

**R2 — le pin est confronté à la table versionnée du build DÉCLARÉ.** Symbole exact à cette VA ;
forme `<symbole>+0x<n>` → le symbole doit être à `va - n` ; `kind: "data"` → le symbole doit
être `DAT_<va>` et la VA doit tomber **après** la dernière fonction de la table. C'est le seul
contrôle qui attrape une transcription fausse **à l'intérieur du bon build** — la faute déjà
commise ici (`RVA_VALUE_MOD_MODIFY` valait `0x1fadfc0` pour une VA dont la RVA est `0xfadfc0`).

**Ce sur quoi il NE rougit PAS**, et c'est le critère central : masques de bits (`0x1000000` =
`TargetIsUnobscured`), base ghidra `0x180000000` employée pour **afficher** une VA, codes
d'exception (`0xE06D7363`, `0xC0000005`), `POISON_OFFSET`, arithmétique 64 bits, sens inverse
`p.sub(il2cppBase)`, offsets de struct et de vtable, VA en commentaire ou en chaîne.

⚠ **`.base.add(` a été essayé et REJETÉ, sur mesure** : au premier passage il rougissait sur
`r.base.add(offset)` (base d'une plage mémoire + offset de boucle, dans un `Memory.scan`) et
`lib.base.add(lib.size)` (borne haute d'un test d'appartenance). Les deux sont runtime et
n'ancrent rien. Les deux formes sont entrées dans le jeu de non-régression.

**Auto-épreuve à chaque run** : 5 formes fautives doivent rougir, 13 légitimes rester vertes.
Un cliquet dont le détecteur a cessé de mordre rend vert sur un dépôt fautif (`probe_181`
avant #430).

## 6. Contre-épreuve — sur le gisement RÉEL, pas sur du synthétique

Injection dans l'arbre des formes exactes que le correctif a retirées, rejeu, restauration à
l'octet près. Chaque scénario vérifie d'abord que **sa mutation a mordu** — sur une
contre-épreuve, VERT est le résultat suspect.

| scénario | verdict |
|---|---|
| `il2cppBase.add(DISPATCH_HELPER_RVA)` + attach (la forme retirée de `modifier-observe`) | ROUGE + nommé |
| `const RVA = { addAction: 0x13fbcc0 }` + `il2cppBase.add(RVA.addAction)` + attach | ROUGE + nommé |
| `mod.base.add(0x14eff60)` (la RVA nue sur une autre base) | ROUGE + nommé |
| pin dont le SYMBOLE ne colle pas à la table du build déclaré | ROUGE + nommé |
| pin dont la VA est transcrite faux **dans le bon build** | ROUGE + nommé |
| pin sur un build dont la table n'est pas versionnée | ROUGE + nommé |
| arbre restauré | VERT (rc 0) |

**6/6.** Un septième scénario a été essayé et **retiré comme hors gisement** : la constante RVA
**inerte** (déclarée, jamais armée) n'est pas vue — résidu `#475-r1`, avec la mesure qui dit
pourquoi la fermer coûterait 20 faux positifs légitimes.

## 7. Ce qui n'est PAS couvert

- **L'activation attend une fenêtre de reinject** : le correctif vit dans `frida/hooks/*`. Le
  bundle est construit (`frida-compile`, rc 0) et typecheck sans erreur nouvelle, mais aucun
  comportement de hook n'a été confronté live. Résidus `#475-r3` (montage de confrontation de
  `bucket-audit`) et `#475-r4` (§8 — les six pins re-mesurés).
- **La RVA inerte** (`#475-r1`).
- **Les autres langages** : le périmètre est `frida/hooks/**/*.ts`. `scripts/frida/*.js` et
  `frida/host/*.ts` n'attachent pas d'`Interceptor` et ne sont pas balayés.

## 8. Les SIX pins que `probe_475` R3 déclarait NON re-dérivables offline (2026-08-15)

`#475-r2` + `#10011-r1`. R3 les nommait et les comptait sans bloquer — **6 pins périmés sur 14**,
tous « exigent de lire le binaire ». Ils ont été lus. **14/14 sur `t6dpr4k06g`, 0 périmé.**

Aucun ne s'est re-dérivé par un grep de symbole, et **aucun n'est une transposition** :

| pin | ancien (build) | neuf (`t6dpr4k06g`) | ce qui l'établit |
|---|---|---|---|
| `modifier-observe` dispatch-42 | `FUN_1800267c0` (`gqfc5mff6c`) | **`FUN_180028580`** | CALL SITE dans `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (7 args, le 2ᵉ vaut `0x42`) **+ le CORPS du callee** : walk d'itable `klass+0xb0` / count `klass+0x12e` / `vid = klass+0x138 + (off+slot)*0x10`, repli `FUN_1801e72b0` — exactement ce que le hook réplique |
| `GetMultiplierFromDamageBonus` | `18110bed0` (`rnca9r7q6c`) | **`18110c980`** | DEUX occurrences du symbole PLEINEMENT QUALIFIÉ (`18110c980`, `18110ca70`) ; départagées par les **trois** critères du site, tous concordants sur la même : param `damageBonus` SINGULIER, Nullable lu via `in_R8`, appel de `IdunBattle.Core.Services.BaseCalculations$$GetFloatMultiplierFromPercentage`. L'autre est la LIST (`damageBonuses`, énumère, rappelle la single). ⚠ Le nom COURT en rend **trois** — `IdunBattle.Core.Services.RepairCalculations$$GetMultiplierFromDamageBonus` est une AUTRE classe |
| iface ability de `b__1` | `DAT_1833407b0` | **`DAT_1833419e0`** | LU dans le corps de `…u003CGetAttackHitPredictionu003Eb__1` (l'opérande comparée aux entrées d'itable). `ATTACK_IFACE_IDX` **relu**, toujours `0xb5`, aux DEUX endroits (scan + repli) |
| iface de l'override de base | `DAT_18334a0c8` | **`DAT_18334b2f8`** | LU dans `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`, opérande du `mov r8, [rip+…]` qui précède le call idx-`0xd` |
| invocateur d'interface | `FUN_180031990` | **`FUN_180031990`** (inchangé) | XREF ENTRANTE (le callee du call idx-`0xd`) **+ le CORPS** (même walk d'itable). L'adresse identique est une **observation**, pas la preuve — le nom d'un `FUN_*` étant son ancienne adresse. Les deux invocateurs portent aussi une référence **DATA** : « 2 appelants » borne les appels DIRECTS, pas les invocations indirectes — d'où le filtre `returnAddress` |
| return-addr du call idx-`0xd` | `181115e0b` | **`1811168bb`** | DÉSASSEMBLÉ : `e8 d5 b0 f1 fe` à `1811168b6`, 5 octets, cible `180031990` (vérifiée par le rel32) |

**Trois résultats de plus, qui ne sont pas des adresses :**

1. **Le résidu nommé dans le commentaire de `PIN_OVERRIDE_RETADDR` est FERMÉ.** Il demandait
   l'index du **second** call de l'invocateur dans `PredictAttackRaw`, « s'il vaut aussi `0xd`,
   ce filtre sélectionne un site parmi deux équivalents ». Il vaut **`0xe`**
   (`FUN_180031990(&local_7c8, 0xe, DAT_18334b2f8)` à `181116e18`) : le filtre `returnAddress`
   isole bien un site UNIQUE.
2. **Le filtre `slot == 0x42` de `modifier-observe`, lui, N'ISOLE PAS `ExecuteHit`.**
   L'invocateur n'a que **deux** appelants DIRECTS et **les deux** passent `0x42` sur la **même**
   interface : `…AttackDamageOperation$$ExecuteHit` et
   `IdunBattle.Operations.DisplaceUnitOperation$$ApplyKnockbackTo` (`mov edx,0x42` lu à
   l'octet à `180f5cc51`, iface `18336edb0` par le `mov r8,[rip+…]` à `180f5cc3f`). Conséquence
   sur la **lecture**, pas sur la sûreté : le dump peut porter deux entrées, discriminées par
   `topRva` et `cls`. Écrit au site.
3. **`b__0` n'a PAS rechangé de forme** : toujours
   `(*(code **)(*plVar1 + 0x4d8))(plVar1, &arg, *(plVar1 + 0x4e0))`. Le hook lit le bon slot.

**Ce qui n'est PAS prouvé, et c'est tout le reste** : qu'un seul de ces pins **FIRE**. La tranche
est offline par construction (armer un pin exige un reinject). Montage de vérification écrit dans
`#475-r4`.
