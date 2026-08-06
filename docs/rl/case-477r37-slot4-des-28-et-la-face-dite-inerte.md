# #477-r37 — le `<slot 4>` a un NOM, et « terme inerte » avait compté dans le mauvais substrat

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp + un runner à la fois. Aucune injection.

```powershell
python scripts/python/probe_477r37_slot4_et_faces_restantes.py --offline-only
python scripts/python/probe_477r37_slot4_et_faces_restantes.py --board MC1_67 --seed 777 --montage abaddon
python scripts/python/probe_477r37_slot4_et_faces_restantes.py --board MC1_67 --seed 777 --montage abaddon-gate
python -m pytest scripts/python/tests/engine/test_477r37_slot4_et_faces_restantes_live.py -q
```

## 1. Les deux résultats, et ils corrigent tous les deux #477-r35

**(a) Le `<slot 4>` a un NOM.** C'est `get_ShouldIncludingEnemiesWhenCalculate`, la 5ᵉ méthode
d'`IdunBattle.AI.Playbook.ITriggeredAbilityNonOwnerPlaybook`, **lue** dans le `global-metadata.dat`
par `il2cpp_metadata.type_methods` — la voie qui produit déjà
`data/symbols/<build>/metadata/interface_slots.tsv` :

| slot | méthode | | slot | méthode |
|--:|---|---|--:|---|
| 0 | `CalculateMovementUtilityInSteps` | | 3 | `Init` |
| 1 | `CalculateAttackUtilityInSteps` | | 4 | **`get_ShouldIncludingEnemiesWhenCalculate`** |
| 2 | `CalculateRepairUtilityInSteps` | | | |

Sur les **28** concrets, **2** le surchargent et **26** l'héritent :

| classe | face | déclare | valeur |
|---|---|:--:|:--:|
| `HaywireMineNonOwnerPlaybook` | MOVE | oui, **AVANT** son `.ctor` | `true` |
| `NoHidingFromTheWatchersNonOwnerPlaybook` | ATTACK | oui, **APRÈS** son `.ctor` | `true` |
| les 26 autres | — | non | `false` (base) |

Le port était **JUSTE** : les 19 faces MOVE du registre portent la bonne valeur. Ce cas ne corrige
pas une valeur, il corrige la **LECTURE** — et rend le zéro *ratchetable*.

**(b) `1064 FirstAmongTraitors` n'est pas un terme inerte.** #477-r35 l'a classée « gate
`HasTrait(Chaos)`, **0 unité sur 1083** » en comptant `gameconfig.unit(vis).traits` — exactement la
source dont `engine/entities/traits/unit_trait.py` écrit qu'elle **ne contient jamais** le
pseudo-trait de grande-alliance (« AUCUNE unité ne le porte : la couche META l'injecte dans la
BattleConfiguration »). Le substrat que `BaseUnitComponent$$HasTrait` interroge (`+0x40`), porté par
`entity_trait_ids`, en donne **127 sur 683**. La face est portée, et confrontée LIVE.

## 2. Le critère de #477-r35 était faux DES DEUX CÔTÉS — et il rendait la bonne valeur

Il lisait l'entrée qui **PRÉCÈDE** le `.ctor` dans le bloc `methodPointers`. Or l'ordre de ce bloc
est celui du **metadata**, et une classe peut déclarer le getter n'importe où :

| | ce que le critère voyait | ce que le metadata dit |
|---|---|---|
| `NoHidingFromTheWatchers` | rien (le getter est **après** le `.ctor`) | déclare, `true` — **faux négatif** |
| `ECogSupport`, `KustomForceFieldReworked` | un override `return 0` (`UnityAdsIdentifier$$get_UserId`) | ne déclarent **RIEN** ; cette entrée est la dernière méthode du **type précédent** — **faux positif** |

La conséquence pratique était nulle (les deux faux positifs valaient `false` de toute façon), et
c'est précisément ce qui rendait le critère indétectable. Il est **retiré** : `probe_477r35 step0b`
délègue désormais au lecteur complet.

Ce qui SURVIT de #477-r35, intact : **le `<slot 4>` est une donnée PAR CLASSE.**

## 3. Trois sources, et chacune DIT ce qu'elle ne voit pas

| source | portée | ce qu'elle donne | angle mort |
|---|--:|---|---|
| `global-metadata.dat` | **28/28** | la DÉCLARATION | aucune valeur (pas de corps) |
| bloc `methodPointers` du PE | 2/2 déclarants | la VALEUR (`b0 01 c3` / `32 c0 c3`) | **ne tient pas** pour une définition GÉNÉRIQUE : le bloc de la base est entrelacé avec d'autres types (mesuré) |
| vtable RUNTIME (`resolveVtableSlot`) | **13/28** | la valeur, base comprise | les classes NON INITIALISÉES |

L'alignement du bloc PE n'est pas supposé : **chaque méthode NOMMÉE de la classe doit tomber à SA
position metadata**, sinon le probe rougit. C'est ce contrôle qui manquait à #477-r35.

⚠ **Une vtable runtime NON BORNÉE ment** (piège #218). Sans la garde « slots 0..3 = les quatre
virtuels d'`Object` », `RelicOfLostCadiaNonOwnerPlaybook` — classe non initialisée — rendait un
`get_ShouldIncludingEnemiesWhenCalculate` à l'index **42** : c'était la vtable de l'`Il2CppClass`
**voisine**. Elle donnait la bonne valeur, par chance. Même forme que le faux positif du §2 : lire à
côté et tomber juste.

La table est **VERSIONNÉE** (`data/symbols/<build>/metadata/non_owner_slot4.tsv`, `--regenerer`) —
c'est ce qui rend le cliquet jouable sans le jeu installé.

## 4. Ce que le décompilé de `1064` tranche

`IdunBattle.AI.Playbook.Loki.FirstAmongTraitorsNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`
(SM `case @+0x20, playbook @+0x28, owner @+0x30`) :

```
if (case.unit == null) yield break;
if (!UnitExtensions.HasTrait(case.unit, 0x7ea)) yield break;      // UnitTrait.Chaos
int d = Query.<slot 0x6d = GetDistance, arite 2>(case.MovementTile,
                                                 EntityExtensions.GetTiles(owner, State));
if (playbook.<+0x58> == null) yield break;
if (d <= FirstAmongTraitorsAbility.GetRange(ability))
    yield return GetUtilityValue("FIRSTAMONGTRAITORS_SurroundingOwner");   // 20
```

* **ce n'est PAS de l'adjacence**, et c'est le seul de la famille dans ce cas. `0x6d` est
  `GetDistance` d'arité 2 (slot lu dans `metadata/interface_slots.tsv` — `IBattleQuery` 108/109/110
  partagent le nom) ; la surcharge est fixée par le TYPE des arguments, `(tileA: IEntity,
  tilesB: IList<IEntity>)`. Les quatre surcharges délèguent au même
  `IdunBattle.Core.Services.MovementQuery$$GetDistance` — distance **hexagonale minimale**, sans
  pathfinding ni élévation, `int.MaxValue` sur un ensemble vide ;
* **le rayon est une CONSTANTE, pas une variable de niveau** :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.FirstAmongTraitorsAbility$$GetRange` est
  `AbilityConfiguration.GetNumberConstant(config, 0x16)`, et `0x16` est un `AbilityConstantType`
  (`range`) — type DÉCLARÉ lu dans `frida/methods.tsv`. Vaut `2` au gameconfig vivant, comparaison
  `<=`, donc un **disque de rayon 2** tuile du porteur comprise ;
* **aucun `IsFriend` dans le corps** : le `<slot 4>` de cette classe vaut `false`, donc c'est le
  pré-gate d'`IterateAbilities` qui restreint aux porteurs AMIS.

**Porteur** : `blackAbaddon` — HERO **du pool**, passif de kit. Ni greffe, ni injection catalogue,
ni relique. C'est le seul confond armé **sans montage** que
`probe_477r33_non_owner_registry_gaps.py --offline-only` recense (étape 0bis) : tout montage qui
spawne Abaddon héritait de `+20` côté natif pendant que le port rendait 0.

## 5. Les mesures

`abaddon` / `MC1_67` / 777 — **4 tuiles hookées, 0 désaccord**. Mover `blackTerminator` (Chaos, pool).

| tuile | nA | nE | adj | `X_nat` | `X_port` |
|---|--:|--:|--:|--:|--:|
| (3,7) | 1 | 0 | 1 | 50 | 50 |
| (4,6) | 1 | 1 | 0 | 40 | 40 |
| (5,7) | 0 | 1 | 0 | 40 | 40 |
| (6,6) | 0 | 1 | 0 | 20 | 20 |

`abaddon-gate` / `MC1_67` / 777 — **8 tuiles, 0 désaccord**, gate `false` partout (mover
`eldarAutarch`, non Chaos).

### Contre-épreuve — `a_mordu` rendu SÉPARÉMENT du verdict

| modèle | `abaddon` (4) | `abaddon-gate` (8) |
|---|--:|--:|
| `PORT` | 0 | 0 |
| `CAMP-DEUX` | **2** | 0 (inerte) |
| `CAMP-ENNEMI` | **3** | 0 (inerte) |
| `ADJACENCE` | **1** | 0 (inerte) |
| `RAYON+1` | **1** | 0 (inerte) |
| `SANS-GATE` | 0 (non séparé) | **4** |
| `COUNT (x n)` | 0 (non séparé) | 0 (inerte) |
| `ABSENT` = l'état d'avant la tranche | **2** | 0 |

`ADJACENCE` et `RAYON+1` sont les deux mutants qui **valent** cette face : ils établissent que le
rayon est `GetDistance <= constants.range == 2`, ni l'adjacence (toute la famille l'est), ni 3.
`ABSENT` **chiffre le bug** : 2 tuiles × 20 sur 4 hookées. `CAMP-DEUX` re-confirme LIVE que le
`<slot 4>` de cette classe vaut `false`.

## 6. Les trois faces qui restent, et POURQUOI — aucune n'est un oubli

**`1451 WisdomOfTheAncients`, `1496 CabalOfSorcerers`, `1508 MastersOfManoeuvre` — un CAPTEUR
manque, pas un montage.** Les trois gates sont des raretés, lues au décompilé :

```
1451 : if (case.unit.BaseUnitComponent.<+0x74> != 5) break;            // Mythic
       foreach (u in Query.<slot 0x83 = GetAdjacentFriends>(MovementTile, case.unit))
           if (u != case.unit && ((u.rarity == 5 && HasTrait(u, 0x10 Hero)) || u == owner))
               yield 20;                                               // WisdomOfTheAncients_AffectUnits
1496 : idem + `HasTrait(case.unit, 0x3ea Psyker)` et `HasTrait(u, Psyker)` ;  // CabalOfSorcerers_AffectUnits
1508 : if (!HasRarity(case.unit, 5)) yield 0;
       foreach (u in Query.<slot 0x84 = GetAdjacentFriends>(case.Position, case.unit))
           if (u != case.unit && HasFaction(u, 0xa DarkAngels) && HasRarity(u, 5))
               yield 25;                                               // MastersOfManoeuvre_AdjacentFriendlyMythicDA
```

`IdunBattle.Entities.UnitExtensions$$HasRarity(unit, r)` est
`unit.GetComponent<BaseUnitComponent>().<+0x74> == r`, **égalité stricte** (pas `>=`).

Les deux moitiés du verrou, mesurées séparément :

* **MONTAGE : DISPONIBLE.** Le seed BC porte déjà **10 unités à `Rarity == 5`** (ventilation
  `{4: 83, 0: 69, 3: 11, 5: 10, 2: 2}` sur 175), `rl_duel build` ne pose **pas** `targetRarity`
  (donc la valeur par unité survit à la normalisation), et `--unit-stat "<vis>:Rarity=5"` écrit le
  champ verbatim. Reste à VÉRIFIER, comme #342 l'a fait pour `Shield`, que
  `BattleConfigBuilder$$GetUnitConfiguration` → `UnitFactory$$Build` recopie bien
  `UnitConfiguration.Rarity` dans `BaseUnitComponent+0x74` — un champ écrit dans le BC et jamais lu
  est un montage MUET ;
* **CAPTEUR : ABSENT, et il exige une fenêtre de reinject.** Le `ctx` des feuilles de tuile ne
  porte aucun canal `rarity`, ni pour le mover ni pour les voisins, et aucun RPC ne l'expose.
  L'ancrage exact : `frida/hooks/features/ai-step/rpc-snapshot.ts`, `combatSnapshot.units[]`, un
  champ `rarity` lu sur `IdunBattle.Entities.Components.BaseUnitComponent.Rarity` via
  `getFieldOffset` (jamais un offset en dur) — c'est **le champ que le natif lit**.
  ⚠ **Ne PAS le prendre sur `UnitConfiguration`** : le canal `unitConfig` existe déjà et lit
  `UnitConfiguration@0x74`… qui est `AbilityVariablesMultiplierPercentage`. Les deux structures
  portent un champ différent au **même offset** — un capteur posé là rendrait un multiplicateur
  déguisé en rareté, sans erreur.

**`1478 SabreOfSacrifice` — l'artefact natif est un ARBRE DSL, donc le port doit en être un (#149).**
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$IsAffectedSummon` ne
teste rien : il **construit** un `AbilityTrigger` —

```
AreEqual(DSLSelectors.Parent(unit, root: false), <caster>)
  & IsUnitWithVisualId(unit, GetStringConstant(0))      // AbilityConstantType.unitId = "astraNpc5DeathRider"
```

— que le playbook exécute par vtable `+0x188` sur une struct de contexte de **0x128 octets** dont le
champ `+0x18` reçoit l'`owner`. Le vocabulaire DSL existe côté port (`entities/triggers.py` :
`AreEqual`, `IsUnitWithVisualId`) ; ce qui manque est **le canal `UtilityMovementCase$$StaysOnTile`**,
première sortie du corps, et le montage du contexte DSL de ce call-site.

## 7. Le régime AUTOMATIQUE — la piste est OUVERTE, et elle ne demande AUCUN hook

#477-r35 a conclu « `aiStepDryRun` ne marche pas ce régime ». C'est vrai, et c'est **la mauvaise
frontière**. Le décompilé d'`IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute` :

```
foreach (id in player.CurrentlyOwnedUnitIds) {
    u = State.<slot 0x29>(id);
    if (u != null && IsAlive(u) && !HasFlag(u, 3) && IsAutomatic(u)) list.Add(u);
}
foreach (u in list) {
    if (!skipAction)
        for (int i = 0; i < 5; i++)
            if (HasActionLeft(u)) Processor.<slot 0x34>(u, null);   // ComputerAction
    Processor.<slot 0x23>(u, null);                                 // FinishUnitTurn
}
```

Les deux slots sont **lus** dans `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv` :
`0x34` = **52** = `ComputerAction`, `0x23` = **35** = `FinishUnitTurn`. Donc l'unité automatique
passe par **le même `ComputerAction`** que n'importe quelle unité — le scorer de mouvement tourne
dedans, et `scorerTileTermTrace` est armé au niveau de la SESSION, pas de la trajectoire
d'activation.

⚠ **Ce n'est pas une mesure, c'est une piste dérivée du décompilé.** Le protocole à jouer :
armer `scorerDamageTraceOn(runnerId)`, faire **DÉMARRER** le tour de l'équipe propriétaire (finir
celui d'en face) plutôt qu'appeler `aiStepDryRun`, puis vider `scorerTileTermTraceDump`. Si les
events sortent, tout gate en `HasTrait(mover, Summon)` — dont `1469 MawClawsOfThyrax`, exercé
offline seulement — devient confrontable sans le moindre capteur neuf.

## 8. Ce qui est livré

* `engine/playbook/non_owner.py` — `FirstAmongTraitorsNonOwnerPlaybook` (registre **18 → 19**), la
  docstring de tête **réécrite** (le `<slot 4>` a un nom, trois sources, les deux faux du critère
  précédent), et la docstring de `HaywireMine` corrigée ;
* `probe_477r37_slot4_et_faces_restantes.py` — les trois sources, le contrôle d'alignement du bloc
  PE, la garde #218 sur la vtable, le cliquet contre la table versionnée ET contre le port, la
  contre-mesure des deux substrats de traits, 2 montages ;
* `data/symbols/rnca9r7q6c/metadata/non_owner_slot4.tsv` — entrée **VERSIONNÉE** (28 lignes) ;
* `probe_477r35_non_owner_gates_montables.py` — `step0b` **délègue** ; le critère faux est retiré,
  pas commenté ;
* `test_477r37_slot4_et_faces_restantes_live.py` — 4 étages offline + 2 × 4 cas live (16 passed).

## 9. Ce qui n'est PAS couvert

* **le `<slot 4>` de 15 des 28 classes n'est pas lisible au RUNTIME** (non initialisées dans la
  session). Les deux autres sources sont complètes, mais le recoupement à trois ne porte que sur
  13 classes — et le probe le DIT au lieu d'en faire un vert ;
* **`NoHidingFromTheWatchersNonOwnerPlaybook` vaut `true` et n'est PAS portée** : c'est une face
  ATTACK, qui passe par `TriggeredAbilitiesNonOwnerUtility.EvaluateAttackInSteps` — même
  `IterateAbilities`, donc même pré-gate. Le jour où la face ATTACK sera portée, cette classe devra
  entrer avec `SLOT_4 = True`, sans quoi sa branche ennemi sera structurellement inatteignable :
  exactement le bug de #477-r35, transposé d'une face ;
* **la branche SPAWN** de la feuille (`case.unit == null && case.parent != null`) — résidu
  pré-existant, inchangé ;
* **les 3 faces restantes** (§6) et **le régime automatique** (§7).

## Résidus

- **#477-r43 — le canal `rarity`, et le piège du même offset dans deux structures** (§6). Trois
  faces MOVE (`1451`, `1496`, `1508`) l'attendent. Le montage est DISPONIBLE (10 unités `Rarity == 5`
  au seed, `--unit-stat` écrit le champ) ; le capteur, non — il exige une **fenêtre de reinject**.
- **#477-r44 — le régime AUTOMATIQUE se lit peut-être SANS hook** (§7). `PlayAutomaticUnitsOperation`
  passe par `ComputerAction` (slot 52, LU) : armer la trace et faire démarrer le tour, au lieu de
  marcher `aiStepDryRun`. Débloquerait `1469 MawClawsOfThyrax`, exercé offline seulement.
- **#477-r45 — `1478 SabreOfSacrifice`, en ARBRE DSL** (§6). Le vocabulaire existe ; manquent le
  canal `StaysOnTile` et le montage du contexte DSL du call-site.
