# #477-r15 tranche D — les tags d'ÉTAT COMPLET d'une unité, et la fermeture du registre

**Build** `rnca9r7q6c`. Mesure live session Frida **8** (3 runners de recon + 3 runners de mesure,
tous disposés). Code : `scripts/python/engine/streams/unit_extensions.py`. Probe :
`probe_477r15a_stream_conformance.py`. Garde : `tests/engine/test_477r15_stream_emitter_offline.py`.

## Verdict en une ligne

Le déploiement est **intégralement** égal au natif : **204 / 204** lignes sur `C1_02`,
**316 / 316** sur `MC1_67` (contre 161 et 273), **0 divergence CONNUE, 0 NOUVELLE**. Le registre
de divergences est **VIDE** — ses deux entrées ont été fermées, pas élargies.

## 1. Le producteur, et ce que la fiche parente disait de faux

`case-477r15` § 5 rangeait ces tags parmi les dix `IdunBattle.Core.Services.StreamHelper$$Get*Tags`.
Faux, et déjà corrigé par les tranches A + B + E : le producteur est
`IdunBattle.Entities.UnitExtensions$$GetFullStateUpdateTags`, en **trois surcharges** que la table
des méthodes du build distingue par leur signature.

**La RE reprise a été VÉRIFIÉE au décompilé, pas recopiée** — c'est ce qui a fait apparaître trois
points qu'aucune des deux fiches ne portait :

- la **garde d'entrée** de la première surcharge rend un dictionnaire **vide**, donc l'appelant
  émet une `Action=ChangeStats` **sans aucun tag** — ce n'est pas « pas de ligne » ;
- les deux tags conditionnels de munitions s'appellent `UnitStats_TriggeredAbility_AmmoCost` (29)
  et `_EnoughAmmo` (30) alors qu'ils sont écrits par la surcharge **ACTIVE**. Un port qui
  « corrigerait » ce nom écrirait de faux ordinaux ;
- `RemainingCooldownTurns` passe par `Nullable$$GetValueOrDefault` : le tag est **toujours** émis,
  à `0` quand le Nullable est vide. C'est l'**inverse** du couple munitions, dont c'est la
  PRÉSENCE du Nullable qui décide de l'émission.

### Le producteur est PARTAGÉ par quatre opérations

`AddUnitOperation$$Execute`, `AddMachineOperation$$Execute`, `ReAddMachineOperation$$Execute` et
`ResurrectUnitOperation$$SendStreamEvents` (xrefs exhaustives des trois surcharges). La séquence
d'émission est **identique** dans les quatre :

```
Action(ChangeStats,   unitEntity, GetFullStateUpdateTags(unit))
foreach a in ActiveAbilityComponent.Abilities(+0x20)     -> Action(ChangeAbility, unitEntity, …(a))
foreach t in TriggeredAbilityComponent.Abilities(+0x18)  -> Action(ChangeAbility, unitEntity, …(comp, t))
```

**Les ACTIVES d'abord, les DÉCLENCHÉES ensuite**, et l'`Entity=` de toutes ces lignes est
l'**unité**, jamais l'ability. `AddMachineOperation` ne diffère que par sa première ligne
(`GetFullMachineStateUpdateTags`, une cinquième fonction, non portée) — ses deux boucles d'ability
appellent bien les surcharges portées.

## 2. Les trois tables, lues au décompilé

### `GetFullStateUpdateTags(unit)` — 16 tags

L'appariement composant → `StatType` n'est **pas deviné** : c'est le même pointeur de classe que
le `switch` d'`IdunBattle.Entities.UnitExtensions$$GetStatComponent` associe à chaque valeur.

| tag | ordinal | lecture native |
|---|---:|---|
| `UnitStats_MaxHealth` | 9 | `FillUpStatComponent$$get_CurrentMaximumValue()` (santé) |
| `UnitStats_MaxArmor` | 13 | idem (armure) |
| `UnitStats_MaxMembers` | 17 | idem (membres) |
| `UnitStats_FixedArmor` | 42 | `StatComponent$$get_CurrentValue()`, `StatType.FixedArmor` |
| `UnitStats_InitRemainingHealth` | 2 | champ **brut** `RemainingValue(+0x18)` (santé) |
| `UnitStats_InitRemainingArmor` | 3 | champ brut `+0x18` (armure) |
| `UnitStats_InitAliveMembers` | 4 | champ brut `+0x18` (membres) |
| `UnitStats_Attack` | 35 | `get_CurrentValue()`, `StatType.Attack` |
| `UnitStats_Range` | 31 | `get_CurrentValue()`, `StatType.Range` |
| `UnitStats_Movement` | 47 | `get_CurrentValue()`, `StatType.Movement` |
| `UnitStats_BlockChance` | 54 | `get_CurrentValue()`, `StatType.BlockChance` |
| `UnitStats_BlockDamage` | 64 | `get_CurrentValue()`, `StatType.BlockDamage` |
| `UnitStats_CritChance` | 71 | `get_CurrentValue()`, `StatType.CritChance` |
| `UnitStats_CritDamage` | 75 | `get_CurrentValue()`, `StatType.CritDamage` |
| `UnitStats_TurnFinished` | 112 | `UnitFlagsComponent$$Has(UnitFlag.TurnFinished)` |
| `UnitStats_IsPlayDeathAnimationOnHit` | 118 | négation d'un OU à **trois** porteurs (ci-dessous) |

⚠ **Le dernier tag lit TROIS porteurs, et les deux enums en cause portent le même nom à des
ordinaux DIFFÉRENTS** :

```
!( BaseUnitComponent.HasTrait(UnitTrait.FinalJustice)            // 0x3f6 = 1014
 | TriggeredAbilityComponent.TryGetAbility(TriggeredAbilityType.FinalJustice)   // 0x400 = 1024
 | TriggeredAbilityComponent.TryGetAbility(TriggeredAbilityType.Bounce) )       // 0x509 = 1289
```

C'est le **type déclaré** du paramètre (`HasTrait(trait : UnitTrait)`,
`TryGetAbility(abilityType : TriggeredAbilityType)`, lus dans `frida/methods.tsv`) qui tranche —
jamais le nom, jamais l'ordinal. Les confondre était à portée de main : `FinalJustice` existe dans
les deux enums.

⚠ **Le natif LÈVE si un composant manque** : la cascade de `if (component != null)` se termine, en
sortie de la dernière garde, sur le thunk de levée. Un composant absent ne produit pas un tag
manquant — il fait échouer l'appel. Le port l'exprime par des champs obligatoires.

### `GetFullStateUpdateTags(activeAbility)` — 6 tags, +2 conditionnels

`Id`(18) ← `AbilityName(+0x44)` · `Level`(24) et `VariableMultiplierPercentage`(25) ←
`get_AbilityState()` (l'override prime sur `_abilityState`) · `CanStillBeUsed`(19) ← `+0x28` ·
`RemainingCooldownTurns`(20) ← `GetValueOrDefault(+0x2c)` · `IsDisabled`(21) ← `+0x35`.
Puis, **si et seulement si** `AmmoCost(+0x38).HasValue` : `…_AmmoCost`(29) et `…_EnoughAmmo`(30)
← `+0x40`.

### `GetFullStateUpdateTags(component, triggeredAbility)` — 3 tags

`Id`(26) ← l'argument · `Level`(27) et `VariableMultiplierPercentage`(28) ←
`TriggeredAbilityComponent$$GetAbilityState`, qui fait un `KeyedCollection.TryGetValue` sur
`Abilities(+0x18)` et lit `+0x20` / `+0x24` de l'instance trouvée.

## 3. Ce qui rend la mesure honnête — des canaux INDÉPENDANTS DU FLUX

Le port ne matérialise aucun composant ECS : il reçoit le substrat résolu, comme
`get_add_unit_tags` recevait déjà `owner_id` / `parent_id`. Le probe le remplit depuis des canaux
qui lisent l'**ECS par réflexion IL2CPP** — jamais le flux, qui est l'oracle.

| grandeur | canal |
|---|---|
| 8 stats à `get_CurrentValue` | `combatSnapshot.units[].stats` (`GetStat(<StatType>, Current)`) |
| santé / armure, max et restant | `observeBattle` (`MaximumValue@0x14` / `RemainingValue@0x18` bruts) |
| `TurnFinished`, porteur de trait | `combatSnapshot.unitFlags` / `.traits` |
| **ordre** et identité des abilities | `unitAbilityStates` — il lit les DEUX collections natives élément par élément, donc dans l'ordre qu'itère `AddUnitOperation` |
| cooldown / disabled / munitions | `decisionView.units[].abilities[]` (`readAbilityState`), apparié par id |

**L'ordre des abilities est la mesure la plus forte du lot** : `unitAbilityStates` rend
`[1100, 69]` puis `[1174, 1180, 1161]` pour `thousTzaangor`, exactement l'ordre des cinq
`Action=ChangeAbility` natives. Un tri du port aurait divergé sur les cinq blocs d'un coup.

⚠ **Tri-état partout** : un canal muet lève `MesureImpossible`, il ne rend pas de valeur par
défaut. Une stat rabattue sur `0` produirait une divergence de VALEUR qui accuserait le port alors
que c'est le CAPTEUR qui n'a rien dit.

## 4. Le non-comparé, PUBLIÉ — la borne (c) passe de 1 à 5 entrées

**Non comparé ≠ égal.** Quatre grandeurs de la tranche D ne sont pas mesurées (la cinquième
entrée, `Tile_IsTerritory`, vient des tranches précédentes), et le rapport les nomme à chaque run :

- **`UnitStats_Range`** — `StatType.Range` (2) est absent de `COMBAT_STAT_IDS` : **aucun RPC ne le
  publie**. Émis à `0`, valeur observée sur **8 unités / 6 kits / 2 boards**, jamais lue
  (`#477-r15-r4`) ;
- **`UnitStats_MaxMembers`** — le seul canal (`stats.numberOfMembers`) est le `StatPart.Current`,
  alors que le natif appelle `get_CurrentMaximumValue()`. Il **ne discrimine pas** ce tag de
  `UnitStats_InitAliveMembers` (`#477-r15-r5`) ;
- **`UnitStats_ActiveAbility_{CanStillBeUsed, RemainingCooldownTurns, IsDisabled}` de la SEULE
  entrée d'attaque normale** — `decisionView` la sort de `AbilityComponent.NormalAttackType` sans
  objet `ActiveAbility` derrière (`GetActives()` la filtre), donc sans état. Posés à l'état neuf ;
  **mesurés pour toutes les autres actives** (`#477-r15-r6`) ;
- **`UnitStats_TriggeredAbility_{AmmoCost, EnoughAmmo}`** — **NON CONFRONTÉS** : `AmmoCost` est nul
  sur toute unité régulière ; les munitions ne mordent que sur les Machines of War, qui passent par
  `AddMachineOperation`, hors de ce groupe. Le port les émet, la garde offline les exerce, le live
  ne les voit pas.

⚠ **Le REBASE a retiré une sixième entrée, et c'est le bon sens de circulation** : `#477-r16-r1`
(mergé pendant cette tranche) a rendu `GetDerivedEnvironmentAbilities` **LU** dans une table
statique au lieu d'être obtenu par différence contre le flux. Le probe ne le prend donc plus du
natif : la base de tuile est désormais une **prédiction**, sortie de la borne (c) et entrée dans
les recoupements qui font **rougir** (`base_tuile != base_natif`). C'est exactement ce qu'un rebase
doit produire — un chiffre qui cesse d'être une entrée, pas un conflit textuel.

⚠ **`max_health` / `max_armor` sont lus au champ BRUT `MaximumValue@0x14`** là où le natif appelle
`get_CurrentMaximumValue()`. Ce n'est pas une approximation aveugle : le décompilé de cet accesseur
donne `MaximumValue + clamp(Modification(+0x28), …)`, ou l'override de `+0x38` s'il existe — les
deux sont **nuls au déploiement**, donc les deux lectures coïncident **par construction**, pas par
chance. Hors déploiement elles divergeraient, et c'est pourquoi c'est écrit ici.

## 5. La contre-épreuve — 7 mutations du PORT, 7 détectées

Un « 204/204 » ne vaut rien sans elle. Chaque mutation casse un choix, et chacune doit faire rougir
la garde offline ; le bras témoin établit d'abord que le port intact est vert, et **chaque bras
vérifie que la mutation a MORDU** (texte du fichier réellement changé) avant de conclure.

| mutation | détectée |
|---|---|
| `Tag=UnitStats_Range` non émis | oui |
| tags de munitions émis inconditionnellement | oui |
| garde d'entrée `EntityType.Unit` supprimée | oui |
| `IsPlayDeathAnimationOnHit` ne lit que le trait (1 porteur sur 3) | oui |
| cooldown omis quand le `Nullable` est vide | oui |
| déclenchées émises AVANT les actives | oui |
| `ChangeStats` émis avec `StepType.ChangeAbility` | oui |

Un huitième bras, dans la garde elle-même, **permute le texte** des blocs `ChangeAbility` pour
vérifier que le comparateur est sensible à leur ordre — sans quoi l'assertion d'ordre ne prouverait
pas que le cliquet saurait la faire respecter.

## 6. Généralisation — le scénario que la mesure de référence ne joue pas

La mesure de référence n'a **qu'une** unité adverse et **un** kit. Les rosters du probe sont donc
devenus paramétrables (`--p-units` / `--a-units`, défauts inchangés), et le scénario joué est
`MC1_67` avec **4 kits adverses distincts** (`adeptRetributor`, `admecDestroyer`, `astraOrdnance`,
`blackTerminator`) et 2 unités côté joueur : **464 / 464 lignes égales, 0 nouvelle**. Il exerce
4 `ChangeStats` et **10** `ChangeAbility` de plus, avec des multiplicateurs (160 / 180 / 200) et
des nombres de déclenchées (2 à 4) différents — dont une unité portant un `UnitFlag` non nul
(`Untargetable`), qui vérifie que `TurnFinished` ne se contente pas de « la liste de flags est
vide ».

## Résidus

- **#477-r15-r4** — **`UnitStats_Range` est émis à 0 EN DUR.** `StatType.Range` (2) n'est dans
  aucune table de capteur (`COMBAT_STAT_IDS` du hook), donc aucun RPC ne publie la valeur que le
  natif lit. `0` est ce que le flux porte sur tout le corpus mesuré (8 unités, 6 kits, 2 boards),
  mais la constante passerait aussi si elle était fausse. **Condition de retournement
  exécutable** : ajouter `range: 2` à `COMBAT_STAT_IDS` (`frida/hooks/features/ai-step/rpc-snapshot.ts`,
  **exige une fenêtre de reinject**), alimenter `UnitFullState.range` depuis ce canal, et vérifier
  que le probe reste à 0 divergence.
- **#477-r15-r5** — **`UnitStats_MaxMembers` et `UnitStats_InitAliveMembers` viennent du MÊME
  canal.** `stats.numberOfMembers` est `GetStat(NumberOfMembers, StatPart.Current)` ; le natif lit
  `get_CurrentMaximumValue()` pour le premier et le champ brut `+0x18` pour le second. Au
  déploiement aucun membre n'est mort, donc les deux coïncident — et le corpus ne peut pas les
  séparer : les **8** unités mesurées valent toutes `1`. **Condition de retournement exécutable** :
  publier `GetStat(…, StatPart.Maximum)` pour `numberOfMembers` comme le hook le fait déjà pour
  `health` (`getStatP(e, "health", partBufMax)`), ou trouver une unité multi-membres et lui faire
  perdre un membre avant la capture.
- **#477-r15-r6** — **L'entrée `ActiveAbility` de l'attaque normale n'a AUCUN état publié.**
  `unitAbilityTypes` la pousse depuis `AbilityComponent.NormalAttackType` sans objet
  `ActiveAbility` derrière, et `GetActives()` la filtre : ni `usable`, ni `cooldown`, ni
  `disabled`. Ses trois tags sont donc posés à l'état neuf — juste au déploiement, non mesuré.
  **Condition de retournement exécutable** : `unitAbilityStates` lit DÉJÀ chaque instance de
  `ActiveAbilityComponent.Abilities` ; y ajouter `...readAbilityState(inst)` (fonction exportée
  d'`ai-step/internals.ts`) publierait les cinq champs pour **toutes** les entrées, attaque normale
  comprise. **Exige une fenêtre de reinject.**

## Ce que je n'ai PAS fait

- **Aucune tranche C** : l'émetteur reçoit toujours ses ids d'entité ; `#477-r16` a rendu la règle
  mécanique et le probe la consomme, mais rien de `MatchComponent$$NextId` n'est porté.
- **`GetFullMachineStateUpdateTags` non portée** : c'est la première ligne du groupe d'une Machine
  of War (`AddMachineOperation` / `ReAddMachineOperation`). Les deux boucles d'ability de ces
  opérations, elles, sont couvertes par ce qui est livré ici.
- **Aucune confrontation hors DÉPLOIEMENT** : `ResurrectUnitOperation$$SendStreamEvents` émet la
  même séquence plus un `Action=ChangeStats` à un seul tag (`UnitStats_ActionsAvailable` ←
  `!HasFlag(NoActionAvailable)`) ; rien de tout cela n'est joué par un scénario de déploiement.
- **Aucun scénario destiné à élargir la couverture du vocabulaire** (`#477-r13` intact) : le
  déploiement exerce désormais **6 `StepType` sur 62** et **36 `TagKey` sur 244**.
- **Aucune modification du bundle Frida** : les deux capteurs qui fermeraient `r4` et `r6` sont
  **nommés** ci-dessus mais pas écrits — ils exigeraient une fenêtre de reinject.
