# `#503-r1` — la PHASE 2 de `1141 OverwhelmingWrath` : la triggered `1237`

Build `rnca9r7q6c`. Porteur lineup `worldEightbound` (Azkor), **au pool**. #503 avait porté la face
COMBAT du CAST (trois poses d'effet, **zéro dégât**) et laissé le `2x Eviscerate` du kit à une
TRIGGERED non portée. Cette tranche la porte et la confronte.

## 1. L'artefact, lu en entier

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.OverwhelmingWrath_AttackAbility$$CreateBehaviour(abilityState, triggerType)` :

```
amount  = IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage(this, abilityState)
profile = IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetDamageProfileOrDefault(this, 0x14)
hits    = IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(config@+0x20, 0x2f)
target  = IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies(Caster@DSLSelectors+0x48,
                                                                 unique: 1, unitSelectionType: 3)
return    IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage(
              caster = Caster@+0x48, targets = target, amount, Nullable(profile), hits,
              abilityOrEffect = AbilityOrEffect(this), options = <struct ZEROEE>, selectionType = 2)
```

et les deux helpers, corps entiers :

* `$$MinMaxDamage` = `DSLFormulas$$RandomAmount( GetVariableForLevel(0xc = minDmg, abilityState),
  GetVariableForLevel(0xd = maxDmg, abilityState) )` — le mode **BORNES**, pas un dégât-node ;
* `$$GetDamageProfileOrDefault(d)` = `config.GetDamageProfile() ?? d`.

**Aucun `RemoveEffect` ici**, et ce n'est pas un oubli : le retrait appartient au `Triggered()` de
`IdunBattle.Entities.Effects.APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal`, qui
compose `TriggerAbility(...) op_BitwiseAnd RemoveEffect(Effect@DSLSelectors+0x38)`. Contraste **LU**
avec la phase 2 de `1069`, dont le `CreateBehaviour` porte **son propre** `RemoveEffect(1136)`.

## 2. Ce qui manquait vraiment — une classe et **une ligne de table**

L'infrastructure était déjà là (#513) : `runner/operations/triggers/pending_attack.py` porte le
`Triggered()` du foyer commun (`On(0x15 = TurnStart_DelayedAttacks) & IsTurnOf(bondé)` →
`TriggerAbility` & `RemoveEffect`). Le port de `1300` était déjà posé par #503. Il manquait donc
uniquement l'arbre de phase 2 et son inscription — et c'est la raison pour laquelle ce résidu, une
fois le foyer en place, coûte deux fichiers.

La dérivation d'`APendingAttackEffect` est **LUE**, pas déduite du nom :
`...OverwhelmingWrath_PendingAttackEffect$$.ctor` a pour corps entier
`APendingAttackEffect..ctor(this, Nullable(AbilityOrEffect(...)))`, et
`$$GetTriggeredAbilityType` pour corps entier `return 0x4d5`.

## 3. Cinq points de fidélité, tous lus

1. **`MinMaxDamage` est CONSOMMÉE** ici — chez `1069` elle est appelée et **jetée** (aucun registre
   ne porte son résultat au site d'appel). Deux abilities de la même famille, deux réponses.
2. **La config est celle de l'ACTIVE 1141.** `GC.ability("OverwhelmingWrath_Attack")` rend `None` :
   la triggered n'a **aucune** entrée gameconfig, alors que `this@+0x20` est non nul au runtime.
   `OverwhelmingWrath.constants` porte **exactement** `{damageProfile: Eviscerate, nrOfHits: 2}` —
   les deux seules constantes que ce behaviour lit. Le site natif de cette attribution n'est pas
   RE'd (résidu #513-r3, partagé avec 1069).
3. **`GetDamageProfileOrDefault(0x14)`** : le défaut n'est jamais atteint (le kit porte le profil).
   L'écrire en dur serait un fit (résidu #513-r2, partagé).
4. **`is_melee=None`, LU et non choisi.** Les **cinq** surcharges de
   `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` ont été décompilées : toutes
   construisent le même couple `AttackDamageBehaviour` + `AttackBehaviour` à partir de
   `(caster, target, amount, damageProfile, hits, abilityOrEffect, options, selectionType)`, et
   **aucune ne porte de bit melee/ranged** — le constat déjà écrit pour `AttackWithAbilityDamage`.
   Écrire `True` (ce que le porteur mêlée et le sélecteur `AdjacentEnemies` invitent à faire) serait
   une **déduction**. Sur ce profil l'axe perçage est **inerte** (`Eviscerate` =
   `{PiercingRatio: 50}` seul, aucun `ExtraPierceMelee`/`Ranged`) → résidu **#503-r5**.
5. **`multi=True`** — différence **structurelle** avec le cleave de #478. Ici le natif passe le
   sélecteur multi **directement**, donc **un seul** `AttackBehaviour` porte N cibles et son
   `OrderBy(b__5_0)` s'applique (`if (Count > 1) targets.OrderBy(...)`). Le cleave, lui, enveloppe
   chaque cible dans son propre `DSLBehaviors$$Attack` via un `Foreach` — l'`OrderBy` ne s'y
   applique pas, d'où son `multi=False`. Confondre les deux déplacerait la consommation RNG dès
   que deux cibles sont adjacentes.

## 4. La mesure — 5 étages verts, 1 écart de magnitude

`probe_503r1_overwhelming_wrath_phase2.py`, board `MC1_67`, seed 777, placement **forcé**, deux
`endturn` **nus** :

| étage | résultat |
|---|---|
| [1] CAST | port == natif, empreinte d'effets identique |
| [2] TOUR ENNEMI | **rien** ne part, des deux côtés — témoin NÉGATIF |
| [3] TOUR DU PORTEUR | ensembles de cibles **identiques** `{81, 83}` ; `u81` **8761 == 8761** (bit-exact) ; `u83` port **12049** vs natif **10957** |
| [4] EFFETS | `1300` disparaît des deux côtés |
| [5] TIRAGES | **28 == 28** — le flux MT est identique |
| [6] CARDINAL | 2 cibles → `multi=True` **exercé** |

**Ce que ça établit** : structure et rang justes. Le tir part au début du tour du porteur et pas
avant, il frappe exactement les ennemis adjacents au **caster**, l'effet se retire, et le port
consomme **exactement les mêmes tirages** que le natif — donc l'écart restant est un étage
d'**application**, ni de tirage ni de ciblage.

### L'écart, décomposé — résidu `#503-r4`

```
u81  crits [true, false]  rolls [6609, 2152]  armor 2161  ->  8761   == natif
u83  crits [true, true]   rolls [6531, 6162]  armor 2460  ->  12693 brut, 12049 appliqué (TUE)
                                                              natif : 10957 (la cible survit à 1092)
```

Trois causes **éliminées par la mesure** :

* **BLOCK** — `block_chance` de `u83` vaut **0** ;
* **ORDRE des cibles** — s'il était inversé, `u81` recevrait les rolls de `u83` (avec son armure à
  elle) et ne serait pas bit-exact ; il l'est ;
* **un CRIT de trop au 2ᵉ coup** — le surplus de crit mesuré sur `u81` (~4300, écart entre le coup
  crit et la fenêtre non-crit) ne rend pas compte des **1736** manquants sur le 2ᵉ coup de `u83`.

**Ce qui bloque** : la ventilation par coup **native**. `captureEvents: True` sur un `endturn` rend
`{}` — les événements du turn-start ne passent pas par `applyAction`, alors que c'est par ce canal
que #478 avait tranché la même forme de question. Point d'ancrage nommé dans le résidu.

## 5. Trouvé en passant, mesuré, non corrigé — `#503-r3`

`TRIGGERED_ABILITY_BEHAVIOURS` n'est peuplé que par `runner/abilities/handler.py`. En process
**frais**, en n'important que la chaîne trigger (`dispatch/registry.py`) :

```
1134 FullThrottle             présent   (import pour EFFET DE BORD explicite dans registry.py)
1127 SeekerMissile_Attack     ABSENT    (dépend de abilities/tau.py)
1237 OverwhelmingWrath_Attack ABSENT    (dépend de abilities/worldeaters.py)
```

Ce n'est pas théorique : sans le module de phase 2, le `Triggered()` rend `dispatched: False`
**et retire l'effet quand même** — un marqueur qui disparaît sans que rien ne frappe, le régime que
`pending_attack.py` déclare lui-même **pire que le statu quo**. En régime réel le runner charge
`handler`, donc le port fonctionne ; la dépendance reste **implicite**, et elle vaut aussi pour
`1127`, livré par #513.

**Non corrigé, et la raison est une mesure** : les deux arêtes candidates ne sont pas de la même
classe (protocole du CLAUDE.md — charger la cible seule dans un process frais) —
`pending_attack -> worldeaters` est **GRATUITE**, `pending_attack -> tau` est **PORTEUSE**. Hisser
l'une et différer l'autre inscrirait une asymétrie que rien dans le natif ne justifie.

### 5bis. RÉSOLU le 2026-08-10 — par DÉPLACEMENT, pas par import

Le constat ci-dessus tenait ; la conclusion « il faut choisir entre hisser et différer » était le
faux dilemme. Le point **(1)** de la doctrine — *déplacer le code vers un module que la cascade ne
ré-entre pas* — **supprime** l'arête au lieu de la fermer. Une ability TRIGGERED n'a rien à faire
dans le module des ACTIVES : les deux phases 2 vivent désormais sous
`operations/triggers/loki/` (`seeker_missile_attack.py`, `overwhelming_wrath_attack.py`), là où
`full_throttle.py` (1134) portait **déjà exactement ce patron**. `registry.py` les importe pour
effet de bord, comme lui ; les modules d'abilities gardent leur phase 1.

La chaîne porteuse a été **tracée**, pas supposée :

```
tau -> attack_query -> revive_effect -> dispatch.ability -> dispatch.core -> dispatch.registry
```

Après déplacement, `registry.py` seul peuple **les deux** entrées, et ne charge **ni** `tau` **ni**
`worldeaters` (cran gardé). Cliquet : `tests/engine/runner/test_503r3_registre_trigger_peuple_offline.py`,
dont le **périmètre est DÉRIVÉ de `PENDING_ATTACK_EFFECTS`** — une entrée future ajoutée à la table
sans phase 2 atteignable depuis la chaîne trigger le fait rougir. Rouge avant fix, verbatim :

```
phases 2 ABSENTES du registre en process frais : [1127, 1237]
(exigees [1127, 1237], registre 1 entrees)
la phase 2 de ...SeekerMissileFrequencyLockTargetEffect (1127) est definie
dans engine.runner.abilities.tau
```

### 4ter. `#503-r4` RÉSOLU (2026-08-10) — l'étage était un EFFET ABSENT, pas un montant

`SupaCyborkBody_CritDmgReduction` (`EffectType` **1468**) n'avait **aucun mirror**. `u83`
(`orksRuntherd`) le porte, `u81` (`orksNob`) **non** — et le port fait criter les **deux** coups
sur `u83` contre **un seul** sur `u81`. Une réduction du dégât de **CRIT** ne pouvait donc
diverger que là, ce qui explique pourquoi une seule des deux cibles était bit-exacte.

Ce qui l'a nommé n'est pas une nouvelle décomposition arithmétique mais la comparaison des
**effets portés** par les deux cibles au moment du tir : `u83` en porte trois que `u81` n'a pas
(`1078 SquigHound_IgnoreBattleFatigue`, `1292 SquigHound_AdditionalHits`, **`1468`**).

Mirror : `engine/entities/effects/loki/supa_cybork_body.py` (les quatre méthodes natives, dont
`$$GetCalculateLevel = Count(AdjacentEnemies(Owner, 1, 3))`, que
`IdunBattle.Operations.RefreshEffectsOperation$$UpdateLevel` tient égal au champ que
`DSLFormulas.EffectLevel` relit). Config = la TRIGGERED `0x5c3 = 1475 SupaCyborkBody`, littéral du
`.ctor` relu **à l'assembleur** (`ba c3 05 00 00`).

| | avant | après |
|---|---|---|
| `u81` | 8761 == 8761 | 8761 == 8761 |
| `u83` | port 12693 brut / 12049 appliqué vs natif **10957** | **10957 == 10957**, coup à coup `[5663, 5294]`, survit à 1092 |

Aucun scalaire fitté : la valeur écrite est `critDmgReduction[50] × niveau 1` = **579** ; les
868 PV par coup sont ce que le pipeline en fait, mesurés et non choisis. Le cliquet
`ECART_ATTENDU_MAX` du garde passe de **1092 à 0**, et la magnitude est désormais gardée sur
**toutes** les cibles.

⚠ **Le capteur `initialHealth` NE DONNE PAS le montant par coup, et c'est LU.**
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` passe `*(int*)(hitGroup + 0x50)` à
**chaque** `ExecuteHit` et **ne le réécrit jamais** dans la boucle : ce sont les PV avant le
**GROUPE** de coups. Mesure : `10040/10040` et `12049/12049`. Ce que ce capteur tranche reste le
**CARDINAL** et l'**ORDRE** — ce qu'il avait déjà tranché.
⚠ Piège de lecture du décompilé : les noms de paramètres ghidra d'`ExecuteHit` sont **décalés d'un
cran** (buffer de retour caché en slot 0), donc le paramètre que ghidra nomme `deniedDamage` est
en réalité `initialHealth`. C'est le call-site de `ExecuteHits` qui tranche, pas la signature.

### 4bis. `#503-r4` — le capteur EXISTAIT, et la 4ᵉ cause est éliminée (2026-08-10)

La §4 ci-dessus déclare `BLOCAGE: capteur` et nomme
`IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` comme point d'ancrage « à
hooker ». **C'était faux.** Le capteur existe et répond : `frida/hooks/features/hit-trace.ts` hooke
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` — l'étage **en dessous** — et son en-tête
nomme littéralement ce blocage (« déclenchement au début de tour → `applyAction endturn` +
`captureEvents` = 1 action / **0 event** »). Il s'arme par RPC (`hitTraceArm` →
`{ok: true, installed: true, on: true}`), donc **sans reinject**. Le résidu n'était pas bloqué par
un capteur manquant, mais par le fait que ce capteur-là n'avait pas été essayé.

Mesure jouée (`probe_503r4_ventilation_par_coup.py`, même montage `MC1_67`/777, layout calibré
`attackerSlot=3`, 4 fires) :

| | natif | port |
|---|---|---|
| cardinal par cible | `{81: 2, 83: 2}` | `{81: 2, 83: 2}` |
| ordre des cibles | `[81, 81, 83, 83]` | idem |
| delta PV | `81: 8761` · `83: 10957` | `81: 8761` · `83: 12049` |

⇒ **4ᵉ cause éliminée** : ni le CARDINAL ni l'ORDRE ne diffèrent. L'écart de 1092 PV (1736 bruts)
est bien un étage d'**APPLICATION du montant**, ce que la §4 posait en hypothèse sans pouvoir le
trancher.

**Ce qui reste, et ce qu'il faut jouer.** `ExecuteHit(hitIndex, attacker, defender,
damageProfileType, abilityOrEffect, attackDamageOptions, initialHealth, deniedDamage)` porte les PV
**avant** chaque coup en 7ᵉ argument — donc le montant par différence — mais le hook ne calibrait
que trois slots. L'extension qui les publie est **livrée** (`initialHealthSlot = attackerSlot + 5`,
**dérivé** de la calibration et non figé ; hors plage → `null`, jamais un entier non validé) et
attend une **fenêtre de reinject**. Une fois chargée : rejouer
`probe_503r4_ventilation_par_coup.py` et confronter `initialHealth` coup à coup aux `rolls` du port
(`u83` port `[6531, 6162]`, armure 2460, crits `[true, true]`).

## 6. Ce qui est livré

| Fichier | Contenu |
|---|---|
| `engine/runner/abilities/worldeaters.py` | `overwhelming_wrath_attack_tree()` + `TRIGGERED_ABILITY_BEHAVIOURS[1237]` |
| `engine/runner/operations/triggers/pending_attack.py` | l'entrée `1300 -> 1237` + la §3 (dépendance mesurée) |
| `probe_503r1_overwhelming_wrath_phase2.py` | la MESURE (6 étages) |
| `tests/engine/runner/test_503r1_overwhelming_wrath_phase2_live.py` | la GARDE (9 tests) |

`ABILITY_CLASSES` n'est **pas** touché (`1237` est une TRIGGERED, comme `1127`) : rien à poser côté
`TARGETING_OPTIONS` / `ABILITY_ATTACK_TYPE`. `probe_181` rejoué : **141/141, 0 manquante**.

Le garde a été **vu rouge** par mutation adversariale (retrait de l'entrée `1300` de
`PENDING_ATTACK_EFFECTS`) :

```
>       assert len(tirs) == 1
E       assert 0 == 1
E        +  where 0 = len([])
```

Le garde générique de #513 (`test_la_phase2_de_1069_est_inscrite`) itère `PENDING_ATTACK_EFFECTS` :
il couvre donc **automatiquement** toute entrée neuve, y compris celle-ci.

### 4quater. `#503-r5` RÉSOLU (2026-08-10) — `is_melee=None` RÉFUTÉ, le natif dit MÊLÉE

Le point 4 de la §3 concluait `None` de l'**absence de bit melee/ranged dans le nœud**. Le constat
structurel tient ; la conclusion était un raccourci : ce n'est pas le nœud qui décide, c'est
`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack`, qui part de
`GetAbilityAttackRangeType(<l'ability du coup>)` — donc de la **config**. L'absence dans le nœud ne
prouve rien sur la valeur que le gate lira.

Le montage annoncé (« une cible portant un réducteur gaté RANGED », puis « greffer `HeavyWeapon`
sur l'**attaquant** ») visait le mauvais axe **deux fois** : le gate `IsRangedAttack` n'a **0**
implémenteur posable sur ce scénario, et un trait de l'attaquant ne change pas la nature du coup.
Ce qui tranche est un gate **défensif** sur une **cible** — trait `Terrifying` greffé sur
`orksNob`, qui dérive `TerrifyingAbility` → `78 Terrifying_ExtraDefense`, dont l'**unique** gate
est `IsMeleeAttack`.

| | `u81` GREFFÉE | `u83` TÉMOIN (non greffé) |
|---|---|---|
| port `is_melee=None` | 8761 vs natif **6132** (écart 2629) | 10957 == 10957 |
| port `is_melee=True` | **6132 == 6132** | 10957 == 10957 |

`8761 × 0,7 = 6132,7` — exactement `globalValues.terrifyingBonus` = 30 %. Le témoin est aussi
important que le positif : la greffe réécrit le seed BC, donc sans lui un écart sur `u81` ne se
distinguerait pas d'un montage qui aurait déplacé autre chose. Sans greffe, `is_melee=True` laisse
les deux cibles bit-exactes — la correction ne bouge rien là où aucun gate de nature n'est armé.

Sonde `probe_503r5_is_melee.py` (son verdict se lit contre la valeur **réellement écrite** dans
l'arbre, jamais contre une valeur en dur), garde `tests/engine/runner/test_503r5_is_melee_live.py`.

## 7. Ce qui n'est PAS couvert
* **`GetAttackingUnitSelector`** — ce porteur ne peut pas le trancher : `1300` est posé **sur** le
  caster et bondé **au** caster (les deux slots coïncident). La lecture reste attestée par la mesure
  de #513, où les deux candidats appartiennent à deux **joueurs** différents.
* **La face DÉCISION** (`IdunBattle.AI.Playbook.Loki.OverwhelmingWrathPlaybook`) — hors périmètre,
  inchangée.

## 8. Résidus ouverts par cette tranche — **les trois sont fermés**

* `#503-r3` — RÉSOLU par DÉPLACEMENT (§5bis).
* `#503-r4` — RÉSOLU : l'étage était `SupaCyborkBody_CritDmgReduction` (1468), absent du port
  (§4ter).
* `#503-r5` — RÉSOLU : `is_melee=None` réfuté, le natif tient le coup pour MÊLÉE (§4quater).
