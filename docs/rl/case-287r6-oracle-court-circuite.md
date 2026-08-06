# #287-r6 — l'oracle de ciblage n'avait pas traversé la cascade

Le rouge annoncé : `SquigMine` (1201) refuse une tuile OCCUPÉE pour la **mauvaise raison** — natif
`0x1` (`ValidRequest`), port `0x1000` (`TargetTileIsFree`), 4 couples sur `MC1_67`, survivants au
désarmement des quatre règles de #287-r4-r1.

**Le port avait raison.** Une fois l'oracle rendu passant, le natif rend `0x1000` sur les mêmes
4 tuiles — **des deux côtés, à l'identique**. Ce qui était faux, c'est le POINT D'OBSERVATION.

## 1. Où le `0x1` est posé, et ce qu'il refuse

`abilityReason` appelle `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`, qui place
deux étages **avant** la cascade de ciblage :

```
ability = ActiveAbilityComponent.GetOrNull(<collection de l'unite>, abilityType);
if (ability == null || !ability.CanCurrentlyBeUsed || *(int*)(ability+0x44) == 0)
    -> GenericBrokenTargetingRule(1)                        // TargetingRule.ValidRequest
if (IsDamagedMachine(unit) && !IsMachinePrimaryAbilityType(unit, abilityType))
    -> GenericBrokenTargetingRule(1)
if (AttackQuery.IsAlreadyUsedThisTurn(...))                 -> 0x40000000000000
sinon -> <ITargetingQuery>.GetInvalidTargetReason(...)       // LA cascade
```

Le port, lui, mirror `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` : il résout la
config d'ability puis appelle **directement** le même slot d'`ITargetingQuery`. Aucun de ces étages.
Les deux ne répondent donc pas à la même question dès que l'étage amont mord — et il rend alors `1`
pour **toute** cible, ce qui explique les 4 « violations » : elles ne portaient pas sur la tuile.

**Le terme qui mord ici est le COOLDOWN INITIAL**, et il est dans le gameconfig, pas dans le
montage : `SquigMine.constants.initialCooldownTurns = 1`, donc `ActiveAbility.Cooldown == 1` au
tour 1, donc `IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed` rend `false`
(son terme `cooldown.HasValue && cooldown.Value < 1`). Mesuré : `abilityState = {"usable": true,
"cooldown": 1, "disabled": false}`.

⚠ **`usable` n'est PAS `CanCurrentlyBeUsed`** — il valait `true` pendant que le natif refusait.

## 2. `1` est réutilisé à DEUX rangs — seul `casterReason` les sépare

`ValidRequest` ici (amont, ability indisponible) **et** le littéral que la branche `TargetIsTile` de
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` rend pour une tuile non marchable
(`TileExtensions$$IsWalkable(mainTile, checkFog: true)` faux). Un `targetReason == 1` isolé ne permet
donc **rien** de conclure — et `probe_243_not_adjacent.py --case generalise` mesure déjà 5 tuiles de
`C3_30` du second cas.

Le discriminant est **`IdunBattle.Core.Services.AttackQuery$$GetInvalidCasterReason`** : il porte le
**même** étage de disponibilité, rend le **même** `1`, et **ne dépend pas de la cible**. Il est déjà
publié par le RPC (`casterReason`) — aucun capteur, aucune fenêtre de reinject.

Une troisième source de `1`, lue au passage et non exercée ici : `GetInvalidCasterReason` refuse
aussi toute unité **multi-tuile** sans le trait `0x418`. Et la cascade a, **avant** toute lecture
d'options, une boucle qui rend `InFogOfWarBrokenTargetingRule` (`ToString` boxe le littéral `1`,
comme `ObscuredTerrainBrokenTargetingRule$$get_Type` boxe le sien) — le hook ne la décode pas et la
publierait en `hex: "0x0"` avec sa `ruleClass`.

## 3. Le correctif : débloquer, pas exclure

Foyer unique **`scripts/python/oracle_targeting.py`** : `oracle_court_circuite(réponse)`,
`cause_du_court_circuit`, `cooldown_initial` (tri-état `None` / `0` / `>= 1`),
`ids_a_cooldown_initial()`, `rendre_oracle_passant(rpc, rid)`. **59** fichiers citent
`abilityReason` ; **2** consomment ce cran ; **24** ne lisent même pas `casterReason` (re-dériver,
ne pas citer).

`probe_287r4r1_generalisation_live.py` lit désormais `casterReason` **une fois par couple, avant
toute cible**, et **laisse retomber le cooldown** (fin de tour + tour adverse) quand un porteur
présent est concerné. Écarter ces couples les laisserait non confrontés pour toujours — un zéro de
méthode. Un couple présent qui reste court-circuité après déblocage fait **rougir** : la mesure n'a
pas eu lieu, et un vert le dirait à tort.

## 4. Avant / après, `MC1_67` (seed 777, mêmes 18 couples)

| | avant | après |
|---|---|---|
| violations **PRÉEXISTANTES** | **4** | **0** |
| violations imputables | 0 | 0 |
| accord sur zéro | 1 | **7** |
| refus reproduits, bit dynamique posé | 2 | 2 |
| refus reproduits hors bit dynamique | 4 | **8** |
| permissif | 7 | **1** |

Les 4 tuiles OCCUPÉES passent de `natif 0x1 / port 0x1000` à **`0x1000` des deux côtés** ; les
6 tuiles LIBRES de `natif 0x1 / port 0` à **`0` des deux côtés**. `C1_02` reste vert avec
`orksRukkatrukk` (déblocage joué) **et** avec `tyranBiovore` (`1145`, `initialCooldownTurns = 0` :
« déblocage non nécessaire » — le probe ne joue le tour que s'il le faut).

## 5. Généralisation : 15 ids du registre sont dans ce régime

`initialCooldownTurns >= 1` sur **15** des 104 entrées d'`ABILITY_CLASSES` — re-dérivé du
gameconfig, jamais écrit en dur (`oracle_targeting.ids_a_cooldown_initial()`) : 1025, 1115, 1142,
1143, 1148, 1150, 1158, 1159, 1160, 1169, 1187, 1188, 1200, 1201, 1232. Pour chacune, **tout**
`abilityReason` pris au tour 1 court-circuite, quel que soit le board et quel que soit le porteur.

## 6. La garde

`tests/engine/test_287r6_oracle_amont_offline.py`, cinq étages : gisement non vide **assertionné** ;
tri-état ; ordinal figé au site ; bascule du discriminant + panne de capteur ; et le **chaînon
complet** — `probe_287r4r1_generalisation_live.mesurer` ne classe plus un couple court-circuité en
violation, avec son **mutant** qui re-produit exactement le rouge d'origine (`natif 0x1`,
`port 0x1000`). Une garde structurelle vérifie en plus que le probe consomme bien le **foyer**
(`G.O is O`) : recopier le prédicat rendrait le mutant inerte sans que rien ne rougisse.

Contre-épreuve, arbre témoin complet (`scripts/python` **plus** `data/` et `frida/hooks/data` —
sans elles la référence est rouge et aucun mutant ne prouve rien) : **5 mutations, 5 rouges**, la
référence verte à 8 passed.

## 7. Ce qui n'est PAS couvert

- **Résidu #287-r9 — les 57 autres consommateurs d'`abilityReason` ne consultent pas le cran.**
  Le foyer existe ; deux fichiers l'appellent. Les ids exposés sont connus (§5) : par exemple
  `probe_91_duty_eternal.py` / `test_multihex_dutyeternal_live.py` (1158, deux tours) et
  `probe_589r1r1r1_empyric_ambush_pose_live.py` (1232). Aucun n'est démontré faux ici — ils sont
  **non vérifiés**.
- **Les deux autres termes amont ne sont pas exercés** : `*(int*)(ability+0x44) == 0` et
  `IsDamagedMachine && !IsMachinePrimaryAbilityType`. `abilityState` ne les publie pas ; le cran les
  range en `indéterminée` plutôt que de supposer.
- **`InFogOfWarBrokenTargetingRule` n'est pas décodée par le hook** — elle sortirait en
  `hex: "0x0"`, donc « cible valide », pour un refus. Même signature que le défaut fermé par #444
  sur `ObscuredTerrainBrokenTargetingRule`. Non rencontrée sur `MC1_67`/`C1_02` ; la corriger
  demande une entrée dans `NON_GENERIC_RULE_CODES` (`frida/hooks/features/ai-step/rpc-targeting.ts`),
  donc **une fenêtre de reinject**. Son code se lit dans
  `IdunBattle.Core.Services.InFogOfWarBrokenTargetingRule$$ToString`, qui boxe le littéral `1`.
- **Le mirror du bit 12 cite `TileExtensions$$CanAddUnit`, la cascade appelle
  `TileExtensions$$IsFreeTile`** (`allowSteppable: 1, allowTemporaryTile: 0, allowAnyUnit: 0`). Les
  deux corps coïncident sur les termes portés (blocker, contenu, steppable, réservation) ;
  `IsFreeTile` teste en plus le brouillard, que `CanAddUnit` n'a pas. Aucune divergence observée
  (10/10 tuiles concordantes) — écart de CITATION, pas de comportement mesuré.
