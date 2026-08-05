# #429-r1-r3-r1 — Le périmètre du gate de message : un message, deux bouts, un prédicat

**Livré le 2026-08-05.** Build de référence : `rnca9r7q6c`.

`#429-r1-r3` avait posé le gate `IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled` sur la voie
d'ABILITY et mesuré son étage sur la CIBLE MORTE. Il laissait **trois** questions non mesurées : la
voie `AttackUnitMessage`, l'axe `UnitFlag.Fled`, et le volet CASTER. Les trois sont **une seule**
question — le périmètre du gate — et les trois sont fermées ici, chacune par une mesure.

## 1. QUELS MESSAGES — deux xrefs, un seul `Visit`

`IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled` n'a que **2 appelants** dans tout le
binaire, tous deux dans `IdunBattle.Messages.InputMessageProcessor$$Visit(ActiveAbilityMessage)`.
Ce n'est donc pas « le gate des messages » : c'est le gate **d'un** message.

Le pendant négatif est lu, pas supposé : `Visit(MoveUnitMessage)` n'a **aucun** gate de liveness —
elle résout l'unité, construit sa liste de tuiles et entre en `RunPhase(5)`.

**Et il n'existe AUCUN `AttackUnitMessage` natif.** Compte exhaustif sur `rnca9r7q6c` :
`IdunBattle.Messages` publie **41** classes de message, `InputMessageProcessor` porte **37**
surcharges de `Visit`, aucune ne prend ce type. L'attaque normale COMMANDÉE est un
`ActiveAbilityMessage` portant le `NormalAttackType` per-unité (#139) — elle traverse donc le même
`Visit` et le même gate. Le port, lui, a **deux** visiteurs pour cet unique site natif
(`AbilityHandler.visit_ActiveAbilityMessage` et `DamageHandler.visit_AttackUnitMessage`) et seul le
premier portait le gate : c'est le fork qu'avait fermé #120 sur l'axe des VECTEURS, rouvert ici sur
l'axe LIVENESS.

## 2. QUEL BOUT — le CASTER aussi, et c'est au rang MESSAGE

Les deux appels sont le caster puis la cible, dans un `||`. Le volet caster n'avait jamais été
confronté. Il l'est par le capteur d'étage de `#429-r1-r3` (le groupe de stream `User_UseAbility`,
ouvert par la lambda du `Visit`, donc **après** son gate) :

| bras (même caster, même message, même cible) | événements | groupes |
|---|---|---|
| témoin — caster **VIVANT** (unité ADVERSE, cible son propre allié → refus au rang OPÉRATION) | **2** | `[12]` |
| caster **CADAVRE** | **0** | `[]` |

Le témoin n'est pas décoratif : le caster est une unité **adverse**, et sans lui « 0 événement » se
lirait aussi bien « le pipeline refuse les casts adverses ».

Côté port, l'attribution est directe et se lit dans `AbilityHandler.last` — on débranche les gates
un à un et le refus **descend** :

| | verdict du port |
|---|---|
| nominal | `not_alive_and_not_fled = "caster"` (rang MESSAGE) |
| gate de message débranché | `actor_dead = True` (#70, rang OPÉRATION) |
| les deux débranchés | `invalid_target = 4096` (#115, gate de CIBLE) |

## 3. QUEL PRÉDICAT — `Fled`, confronté, et la réfutation de « pas mort »

`UnitFlag.Fled` (9) est le **seul** régime qui sépare `IsAliveAndNotFled` de « pas mort » : sur la
MORT les deux étages convergent. La chaîne de production est **unique**, et mesurée :

* **un seul écrivain du flag** — `IdunBattle.Operations.FleeOperation$$Execute` (1 seul des 42
  appels de `IdunBattle.Entities.Components.UnitFlagsComponent$$Add` passe `9`) ;
* **un seul déclencheur** — `IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateBehaviour`,
  unique appelant d'`IdunBattleLogic.Entities.DSLBehaviors$$Flee` ;
* **le trait `BattleFatigue`** : « si une unité alliée est vaincue dans un hex adjacent, chance que
  cette unité fuie » — `chance` = 10, `chance_2` = 40 (overkill), lus dans
  `BC.Abilities.PassiveAbilities.BattleFatigue`.

**Le montage** (`probe_429r1r3r1_message_gate_perimeter.py --volet fled`) : les 12 entrées
`BattleFatigue` du seed BC sont des SUMMONS, donc **absentes du pool** (`buildNormalizedBC` les
skippe, cf. `case-92` §5bis) — mais `applyAddUnit` les pose directement à l'hex voulu. Elles portent
`Health = 0` au catalogue (les stats d'un summon viennent des constantes de son invocateur), d'où
`--unit-stat astraNpc1Guardsman:Health=1000,RemainingHealth=1000`. On pose des gardes sur les hexes
libres adjacents à une unité adverse à 1 PV, on la tue en overkill, chaque garde adjacent tire.

**Deux pièges de montage, tous deux mesurés :**

* le second adversaire de roster ne peut **pas** être `tyranWingedPrime` : son trait `Synapse` fait
  IGNORER `BattleFatigue` aux alliés dans 2 hexes — il aurait désarmé le montage en silence. Même
  raison d'écarter `astraYarrick` (`SummaryExecution` : la première fuite devient une exécution et
  les autres porteurs ignorent le trait) et `orksRuntherd` (`SquigHound` : « les Grots amis ignorent
  Battle Fatigue ») ;
* les gardes posés ne tiennent **pas** l'équipe adverse en vie pour la condition de victoire : avec
  la seule victime comme a-unit, sa mort termine la bataille et `decisionView` cesse de publier
  **toutes** les unités.

**La mesure :**

| bras | événements | groupes |
|---|---|---|
| témoin — cible VIVANTE hors portée | **2** | `[12]` |
| cible **ENFUIE**, `hp = 1000 / 1000` | **0** | `[]` |

La cible a ses **PV pleins** : `IdunBattle.Entities.Components.HealthComponent$$IsDead` est FAUX sur
elle. **Aucun prédicat « pas mort » ne peut expliquer ce refus** — c'est la réfutation live de
l'hypothèse `!IsDead` et la confirmation de la branche `HasFlag(unit, 9)`.

## 4. Le fix, et ce qu'il change

`engine/runner/operations/damage.py::visit_AttackUnitMessage` — le gate en tête, caster puis cible,
mirror exact de `visit_ActiveAbilityMessage`, **import paresseux** (c'est ce qui fait mordre la
substitution du foyer dans les contre-épreuves). Convention permissive identique : entité non
résolue ⇒ aucun refus.

**Sur la MORT, il ne change rien — et c'est MESURÉ, pas supposé** : sur un cadavre, neutraliser le
seul gate de message laisse le gate d'OPÉRATION (#429-r1) refuser. C'est précisément pourquoi le
trou a pu vivre sans casser un test. Il faut débrancher **les deux** pour que le port frappe :
**10 375 dégâts** sur le cadavre, flags de tour posés.

## 5. Ce que le régime FLED a révélé — le canal de seed était aveugle

Sur le **même état** que la mesure du §3, le port, gate **armé**, frappe l'unité enfuie pour
**10 375** :

| | valeur |
|---|---|
| `hp` vu par le port | **1000** |
| `UnitFlag.Fled` vu par le port | **absent** |
| `is_alive_and_not_fled` | **True** |
| `unit_is_dead` | **False** |

Cause **localisée** : `combatSnapshot` — le canal qui seede `UnitFlagsComponent` — n'énumère que
les unités **vivantes** (`if (!invokeBool(isAliveMi, [e, statePtr])) return;`). Or
`IdunBattle.Entities.UnitExtensions$$IsAlive` rend FAUX sur une unité enfuie (le prédicat teste
**aussi** le flag 6 `Dead` et l'appartenance à la collection d'unités, pas seulement
`HealthComponent.IsAlive`). Le flag `Fled` n'atteignait donc **jamais** le port : son gate, pourtant
correct, ne pouvait pas mordre.

⚠ **Le capteur de flags avait aussi une seconde cécité, et c'est le TRI-ÉTAT qui l'a trouvée** :
`combatSnapshot` nomme sa clé `entityId`, pas `id`. Un lecteur qui lisait `id` rendait un dict VIDE,
donc « aucun flag » sur **toute** unité — un « aucune fuite » parfaitement muet. Rabattre
`absent`/`null` sur `[]` l'aurait rendu invisible.

**Le correctif est livré mais NON ACTIVÉ** : bloc additif `unitsNotAlive` (`entityId` + `unitFlags`,
aucune stat — les sous-lectures lourdes supposent une unité en jeu) dans
`frida/hooks/features/ai-step/rpc-snapshot.ts`, et lecture tri-état dans
`snapshot.py::_load_unit_flags`. Il **exige une fenêtre de reinject** ; le lecteur Python est inerte
tant que le champ est absent.

## 6. Les gardes

`tests/engine/runner/test_429r1r3r1_message_gate_perimeter_live.py` — **11 tests, ~46 s** : le
périmètre offline (le gate vit dans les 2 portes du port et nulle part ailleurs, contre-épreuve par
NOM et non par seuil), le volet CASTER avec son témoin et sa décomposition par étage, la voie
`AttackUnitMessage` (convergence mesurée + mordant), et le régime FLED (témoin, réfutation de « pas
mort », attribution de la divergence de seed).

Le dernier test **asserte dans les deux régimes**, et son discriminant est mesuré (présence du champ
`unitsNotAlive`) : tant que le bundle chargé est antérieur, il garde l'ATTRIBUTION de la divergence ;
dès que le champ apparaît, il exige l'ACCORD avec le natif.

**Un test existant a rougi, et il a été DÉCOMPOSÉ, jamais affaibli** :
`test_429r1r1_normal_attack_dead_target_live::test_contre_epreuve_sans_le_gate_le_port_frappait_le_cadavre`
débranchait le seul gate d'opération et attendait une frappe. Le probe gagne une **étape 3ter** (gate
de message seul débranché → le port refuse ENCORE, ce qui ré-asserte la morsure du gate d'OPÉRATION
sur cette porte), son étape 4 débranche désormais **les deux**, et la porte DÉCLENCHÉE (l'opération
nue, qui n'emprunte aucun visiteur) garde seule la garantie du gate d'opération.

Non régressé (re-joué après le fix) : `test_429r1r1r1_ability_attack_dead_target_live` (9),
`test_429r1_dead_target_gate_live` (7), `test_429r1r3_dead_target_message_gate_live` (12).

## 7. Ce qui n'est PAS couvert

* **La distinction « flag 9 » / « entité non résolue »** dans le refus natif du §3 n'est pas séparée
  par ce montage : `IsAliveAndNotFled(null)` rend faux lui aussi. Elle ne change **rien** à la
  conclusion — les deux réfutent également « pas mort », puisque `IsDead(null)` est faux et que la
  cible a ses PV pleins.
* **Un seul board** (`MC1_67`) et **un seul seed utile** pour le régime FLED. La fuite est un
  tirage du jeu, mais son issue est **déterministe par seed** (la séquence d'actions du montage est
  fixe, donc le flux MT aussi) : sur 2 tirages, **777 → 2 fuites** (trois runs identiques),
  **31337 → 0**, **123 → 0**. La liste de seeds du test est un **repli** en cas de dérive du flux,
  pas une loterie relancée jusqu'au vert. Le second événement de mort (celui qui aurait amorti le
  tirage) n'est **pas** installé sur 31337/123 : `spaceWulfen` n'y a aucune victime adverse
  adjacente, et un garde posé à côté de lui n'est pas ressorti adjacent dans la vue — cause non
  élucidée, montage laissé en l'état puisque 777 fournit le régime.
* **Les gates 9 et 10 du `Visit`** (deux appels d'interface non résolus par Ghidra, postérieurs au
  gate cible-morte) restent non lus — résidu hérité de `case-429r1r3` §7.

## 8. Résidus nommés

* **`#429-r1-r3-r1-r1` — le canal de seed n'atteint pas `UnitFlag.Fled`, et le correctif est livré
  NON ACTIVÉ.** Mesuré : port 10 375 dégâts sur une unité que le natif refuse. Le bloc
  `unitsNotAlive` (`rpc-snapshot.ts`) + le lecteur `_load_unit_flags` sont écrits et le bundle
  compile ; il manque **une fenêtre de reinject**. Tant qu'elle n'a pas eu lieu, la divergence est
  OUVERTE et le test la garde par attribution.
* **`#429-r1-r3-r1-r2` — le port n'a aucun mirror d'`IdunBattle.Entities.UnitExtensions$$IsAlive`.**
  Il n'a que `unit_is_alive` = `IdunBattle.Entities.Components.HealthComponent$$IsAlive` (hp ≥ 1),
  alors que le natif teste **trois** choses : `HasFlag(unit, 6 = Dead)`, l'appartenance à la
  collection d'unités du match, puis seulement `HealthComponent.IsAlive`. Conséquence mesurée : une
  unité enfuie à PV pleins est « vivante » pour **tout le reste** du moteur (ciblage, IA,
  prédiction), pas seulement pour le gate de message. Périmètre à chiffrer avant de porter.

## 9. Re-dériver

```
python scripts/python/probe_429r1r3r1_message_gate_perimeter.py --volet scan
python scripts/python/probe_429r1r3r1_message_gate_perimeter.py --volet caster  --state-file <ABSOLU>
python scripts/python/probe_429r1r3r1_message_gate_perimeter.py --volet attaque --state-file <ABSOLU>
python scripts/python/probe_429r1r3r1_message_gate_perimeter.py --volet fled    --state-file <ABSOLU>
python -m pytest tests/engine/runner/test_429r1r3r1_message_gate_perimeter_live.py -q
```
