# #446 — `Boltstorm` (1090), face ATTACK : PORTÉ + CONFRONTÉ LIVE

Quatrième des résidus ATTACK de #419-r1 (5 porteurs) — #443 a livré `SaviorProtocols` 1120 pendant
cette tranche, le gisement retombe donc à **16**. Le corps n'avait **pas** été lu.

## 1. Ce que dit le décompilé

`IdunBattle.AI.Playbook.Loki.BoltstormPlaybook$$CalculateAttackUtilityInStepsInternal` monte la SM
`d__3` : `sm@+0x20 = this` (le playbook), `sm@+0x28 = case`, `sm@+0x30 = getUtilityVal`. Le corps est
`IdunBattle.AI.Playbook.Loki.BoltstormPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`,
**deux** états de yield :

```csharp
weapon = this.<IBattleQuery @playbook+0x60>.FindRangedWeapon(case.Caster);   // slot 0xb3
if (weapon == null)
    yield return Fix64.op_Implicit(0);                                       // état 1
else {
    int range = weapon.Range.Value;                        // Nullable<int> @ WeaponProfile+0x24
    var sel = BoltstormAbility.GetAllTargets(this.<DSLFactory @playbook+0x20>,
                                             DSLFormulas.Direct(range));
    var entities = new AbilityEntities {                   // struct 0x128 o, memset à 0 d'abord
        Actor = null, Caster = case.Caster, Target = case.Target, Owner = case.Caster };
    yield return Fix64.op_Implicit(
        GetUtilityValue("BOLTSTORM_AdjacentEnemies") * sel.Count(entities));  // état 2, vslot 0x18
}
```

Cinq lectures qui ne se devinent pas :

1. **PRODUIT poids × cardinal** — premier playbook attack porté dont la valeur croît avec le nombre
   de cibles (`local_res8[0] * iVar12`). Forme d'appel du délégué scorer identique à
   `BarbedOvipositor` : `(**(deleg+0x18))(*(deleg+0x40), <littéral de clé>, local_res8, *(deleg+0x28))`,
   la valeur revenant **dans** `local_res8`.
2. **Le `range` vient de l'ARME** — `FindRangedWeapon(unit)`, surcharge à **un** argument, identifiée
   par son proxy `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass213_0$$u003CFindRangedWeaponu003Eb__0`
   (tout son corps est cet appel d'interface). Ni distance, ni cible, ni porte de portée : elle rend
   l'arme de plus longue portée (`IdunBattle.Core.Services.BattleQuery$$SelectMaxRangeWeapon`, dont
   la comparaison est `<=` → à égalité le **dernier** max gagne). Le champ `+0x24` est qualifié par un
   **troisième** site qui le nomme : `IdunBattle.Entities.Formulas.AttackWeaponRangeFormula$$Calculate`
   (`get_IsMelee ? 1 : Range.Value`). Et `IdunShared.Battle.WeaponProfile$$get_IsMelee` n'est **pas**
   « Range absent » : c'est `!Range.HasValue || Range.Value < 2` — une arme de portée 1 est MÊLÉE.
3. **Le cardinal compte la CIBLE elle-même.**
   `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BoltstormAbility$$GetAllTargets(dsl, range)` :

   ```
   Target@0x60
   + ( SurroundingEnemies(Owner@0x30, range, unique: 1, unitSelectionType: 3)
       & Unobscured(Owner@0x30, Enemies(Caster@0x48, AdjacentUnits(Target@0x60, 1, 3), 3)) )
   ```

   (mapping `DSLSelectors` déjà établi par le port : `+0x30 Owner · +0x40 Actor · +0x48 Caster ·
   +0x60 Target`.) Toute cible vaut donc **déjà 1 × le poids**, même isolée. C'est l'ability prise à
   l'envers : la face COMBAT
   `IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$ExecuteBoltstorm`
   appelle `GetAdditionalTargets` — le **même** arbre sans `+ Target` — avec
   `Direct(attackWeapon.Range)`. Le playbook estime exactement le nombre d'unités que le tir touchera.
4. **Le terme ne dépend PAS de la tuile d'attaque.** La struct `AbilityEntities` est memset à 0 puis
   ne reçoit que `Caster`, `Target`, `Owner` : `CasterTile` (`+0x40`) et `TargetTile` (`+0x30`)
   restent nuls, et `case.CasterPosition` (`UtilityAttackCase+0x18`) n'est jamais lu. Or
   `SurroundingEnemies` (surcharge 5 args) et `Unobscured` ancrent sur la MainTile **réelle**
   (`EntityExtensions.IterateTiles` / `GetMainTile`) — même quirk que
   `IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetDamage` (#216). Le terme
   discrimine les **cibles**, jamais les tuiles d'une même cible. Offsets lus dans
   `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` (`+0x00 actor · +0x08 caster · +0x10 target
   · +0x18 owner · +0x30 targetTile · +0x40 casterTile`).
5. **Le poids est `BOLTSTORM_AdjacentEnemies` = 10** (`Utilities.Default.TriggeredAbilities`) — seule
   clé `BOLTSTORM_*` du BC. Le littéral de chaîne n'est pas lisible au décompilé (cache `DAT_` posé au
   runtime) : l'identification passe par le BC servi, et elle est **confrontée live** (le terme
   observé vaut exactement `10 × cardinal`, et les deltas natifs valent `+10` par cran).

Le vslot `0x18` est `Count` : `IdunBattle.DSL.TargetsSelector$$Count` n'a aucun appel direct (2 xrefs
DATA), son propre corps invoque le vslot `0x17` (= `Select`, celui qu'invoque aussi
`AttackWeaponRangeFormula$$Calculate`) puis `Enumerable.Count`, et c'est la seule méthode de
`TargetsSelector` rendant un `int`. Les deux volets de l'`op_Addition` sont **disjoints** par
construction (`AdjacentUnits(Target)` exclut son origine) : la question « union distincte ou
concaténation » est sans objet pour le cardinal.

## 2. Face MOVE

`BoltstormPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` rend 0 (déjà
inventorié par #193 parmi les 13 corps MOVE triviaux) → pas d'entrée au registre
`TRIGGERED_MOVE_PLAYBOOKS`, et son absence EST le comportement natif.

## 3. Montage, et le piège qu'il a révélé

`templAggressor` « Burchard » (HERO, **au pool**) + 4 npc `templBossAggressor*`. Board `MC1_67`,
seed `41504`. Arme distance : `Bolter`, `Range = 2` → `range = 2`.

Géométrie **construite** (les unités sont déplacées) : caster `C` ; cible entourée `T` à distance 2 ;
deux voisins `N1`/`N2` de `T` à portée (ils comptent) ; deux voisins `F`/`F2` de `T` hors portée (ils
ne comptent pas) ; cible isolée `A` à portée, sans aucun voisin. D'où `count(T) = 3`, `count(A) = 1`.

⚠ **PIÈGE MESURÉ** — la première version cherchait les voisins de `T` avec `hexgeo.neighbors` **nu**.
Sur `MC1_67`, `(1,3)` est à élévation 4 et `(2,2)`/`(1,2)` à élévation 2 : `|Δ| = 2`, donc la porte
d'élévation d'`IterateAdjacentTiles` les exclut **déjà**. Le témoin « hors portée » n'était donc pas
exclu par la portée mais par l'élévation — le gate `SurroundingEnemies(Owner, range)` n'était **pas
exercé**, et rien ne le signalait : le cran qui devait le montrer donnait `dNat = 0` ET `dPort = 0`
(accord parfait pour rien). Le montage exige désormais l'adjacence **native** (`bq.is_adjacent`).

⚠ **Second piège, sur le CRITÈRE de contre-épreuve** — le premier jet déclarait un mutant
« MORD » sur `abs(port - native) > EPS`. Or cette paire porte un écart constant hors périmètre (§5) :
le critère était vrai même pour un mutant **inerte**, et c'est ainsi que `no_range` était rapporté
mordant alors qu'il ne déplaçait rien. Le critère est maintenant le **déplacement par rapport au port
NON MUTÉ**. Même forme que le bras vert sous mutation trouvé par #441.

## 4. Mesures (runner `MC1_67`/`41504`, `templAggressor`)

Niveau, layout `C=(3,4) T=(1,3) N1=(1,4) N2=(2,3) F=(0,3) A=(2,5)` :

| cible | cardinal | natif | port | port sans 1090 | port − port muté | attendu |
|---|---|---|---|---|---|---|
| `T` (entourée) | 3 | 38.219589 | 34.059797 | 4.059797 | **30.000000** | 30 |
| `A` (isolée) | 1 | 20.974451 | 15.334733 | 5.334733 | **10.000000** | 10 |

Balayage isolant — seule la **distance au caster** de voisins qui restent voisins de `T` change
(`adj = [N1, N2]` aux trois crans) :

| cran | cardinal | exclus par la portée | natif | port | ΔNatif | ΔPort |
|---|---|---|---|---|---|---|
| `count1` | 1 | `N1`, `N2` | 18.219589 | 14.059797 | — | — |
| `count2` | 2 | `N2` | 28.219589 | 24.059797 | **+10.000000** | **+10.000000** |
| `count3` | 3 | — | 38.219589 | 34.059797 | **+10.000000** | **+10.000000** |

Contre-épreuves (déplacement du port vs port non muté) : `no_range` **+10** sur `T` ; `no_target`
**−10** sur les deux ; `not_adjacent` **+10** sur `T` et **+30** sur `A`. Les trois mordent.

Le test-garde a lui-même été **éprouvé par deux mutants du port** (gate de portée retiré → 4 rouges
sur 5 ; terme rendu plat → 3 rouges sur 5).

## 5. Résidu NOMMÉ, hors périmètre : l'écart constant de la paire

Le port reste **sous** le natif de `4.159792` sur `T` et de `5.639718` sur `A`. Trois mesures
établissent que cet écart n'appartient pas à cette tranche :

* il est **invariant** aux trois crans du balayage (`−4.159792003` à chaque cran) alors que le terme
  de 1090 varie de 10 en 10 — il est donc **additif et indépendant** du cardinal ;
* `port − port_muted` vaut **exactement** `10 × cardinal`, et les deltas natifs valent **exactement**
  `+10` par cran : tout le mouvement de l'oracle est capté par le terme porté ;
* il **diffère par cible** (4.16 vs 5.64) → il dépend de la cible, donc du composite de DÉGÂT, pas
  d'un terme triggered constant. Candidats à instruire : les traits `CrushingStrike` / `MkXGravis` de
  `templAggressor`, non confrontés ici.

C'est pour cela que la garde n'asserte **pas** `natif == port` en niveau (elle rougirait pour une
cause étrangère) mais l'**invariance** de cet écart à travers le balayage — strictement plus fort sur
l'axe testé. Résidu ouvert : `#446-r1`.

Une tentative de contrôle sur un caster sans playbook triggered (`astraCreed`) n'a **rien conclu** :
sans drive, les cibles étaient hors portée et `pairUtility` rendait 0 sur toutes les paires (régime
« pas de paire légale », que le montage principal évite en attestant `action_tiles` + distance).

## 6. Non couvert

* **`Unobscured`** — le montage l'atteste absent (`is_target_tile_obscured` faux partout sur les
  tuiles retenues) mais ne l'exerce pas : il faudrait un couple de tuiles à distance 2 avec un relief
  bloquant.
* **`FindRangedWeapon == null`** (état 1, terme 0) — régime d'une unité mêlée-only ; `templAggressor`
  a une arme distance, et aucun autre porteur de 1090 n'est spawnable. Le mirror est lu au décompilé,
  non confronté.
* **Le seuil `Range < 2` de `get_IsMelee`** — aucun porteur confronté n'a d'arme à portée 1. Le tri
  historique de `get_attack_weapon_for_default_normal_attack` (`bool(w.get("Range"))`) diverge de ce
  seuil ; les deux coexistent volontairement (résidu nommé dans la docstring de `weapon_is_melee`).

## 7. Livré

* `scripts/python/engine/playbook/boltstorm.py` — le playbook + `count_all_targets`.
* `scripts/python/engine/services/battle_query.py` — foyers `weapon_is_melee`,
  `select_max_range_weapon`, `find_ranged_weapon`.
* `scripts/python/engine/playbook/psyker.py` — entrée `TRIGGERED_ATTACK_PLAYBOOKS[1090]`.
* `scripts/python/probe_446_boltstorm_pair_term.py` — montage, mesure, balayage, contre-épreuves.
* `scripts/python/tests/engine/test_446_boltstorm_pair_term_live.py` — 5 gardes.
