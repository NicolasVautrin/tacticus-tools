# case-443 — `SaviorProtocols` (1120), et le porteur qui s'invoque LUI-MÊME

Troisième des 20 résidus ATTACK de `case-419` §7 (6 porteurs dispatchés, **aucun `lineup`**).
Le corps n'avait pas été lu ; il ne ressemble à aucun de ses deux prédécesseurs.

**Résultat** : la face ATTACK est portée et confrontée live, sur un porteur **NATUREL** — pas une
greffe. Aucun canal nouveau n'a été nécessaire : le corps ne lit ni le caster, ni la tuile
d'attaque, ni la `DamagePrediction` ouverte par #438. Ce qu'il fallait établir, c'était le
**montage** : les deux moitiés (un porteur de 1120 en bataille, une cible marquée) tiennent dans
**une seule action native**.

## 1. Le corps natif — UN seul `yield`, deux sorties

`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook$$CalculateAttackUtilityInStepsInternal` monte
la SM `d__5` ; corps :
`SaviorProtocolsPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__5$$MoveNext`.

```
Fix64 u = Fix64.op_Implicit(0);
if (EntityExtensions.HasEffect(case.Target, this.<state>, (EffectType)0x462, onlyActive: true))
    u = Fix64.op_Addition(u, Fix64.op_Implicit(GetUtilityValue("SAVIORPROTOCOLS_MarkedTarget")));
yield return u;
```

* **La SM a TROIS champs** — case @+0x20, `this` (le playbook) @+0x28, délégué scorer @+0x30 — là
  où `BarbedOvipositorPlaybook$$CalculateAttackUtilityInStepsInternal` n'en écrit que **DEUX**
  (case @+0x20, délégué @+0x28). Le corps de 1204 n'a pas besoin du playbook ; celui-ci si, il y lit
  `state`. **Et la face MOVE du MÊME playbook les dispose encore autrement** — `d__4` :
  playbook @+0x20, case @+0x28, délégué @+0x30 (`$$CalculateMovementUtilityInStepsInternal`, lu).
  Trois dispositions pour trois state machines : elle se **lit** dans la méthode-usine, la
  transposer d'un voisin — fût-ce l'autre face de la même classe — donne le mauvais champ.
* **Le prédicat porte sur la CIBLE et sur rien d'autre** : ni stats, ni traits, ni faction, ni
  position du caster ; ni `case.CasterTile` (contrairement à `SuppressiveFire`, qui NIE
  `AreEntitiesAdjacent`) ; ni `case.DamagePrediction` (contrairement à `BarbedOvipositor`).
* **`0x462` = 1122 = `EffectType.Markerlight`**, enum QUALIFIÉ : dans `TriggeredAbilityType` 1122
  vaut `NoctilithBeacons`. (Symétriquement, 1120 est `SaviorProtocols` en `TriggeredAbilityType` et
  `TerrorsLament_HitReduction` en `EffectType` — deux pièges d'id sur la même paire de nombres.)
* **`onlyActive: true`, et c'est l'INVERSE de `SuppressiveFire`.** Le 4ᵉ argument est le littéral
  `1` (`SuppressiveFire` passe `0`, `ForwardObservers` passe `null`).
  `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` ne consulte
  `EffectComponent.IsActive @+0x5c` que si `onlyActive != 0` ⇒ le mirror est
  `EffectsState.active_effects`, **pas** `has_effect`. La seconde branche,
  `IdunBattle.Entities.EntityExtensions$$IsTargetOfEffect`, exige `+0x5c` **inconditionnellement**.
* **Pas de `.cctor`** : les trois clés sont des littéraux de chaîne du corps
  (`FUN_1801f4fb0(&DAT_…)` au prologue) — même forme que `BarbedOvipositor`, l'inverse de
  `Lakrimae`. Poids au gameconfig **et** au seed BC servi (concordants, pas de piège #271) :
  `SAVIORPROTOCOLS_MarkedTarget` = **60**, `_AdjacentTauFriend` = **20**, `_AdjacentTauParent` = **30**.

## 2. Le montage — une action native monte les DEUX moitiés

`SaviorProtocols` n'a **aucun porteur `lineup`** : 3 npc (`tauNpc{2,3,4}Drone*`) et 3 **SUMMONS**
(`tauSmnDroneSniper`, `tauSmnDroneShield`, `tauSmnDroneCommandLink`). C'est la voie SUMMON de la
gate de confrontabilité — et elle est ici particulièrement économique :

**l'attaque normale RANGED de `tauMarksman`** (ability 1076 `MV71SniperDroneSquadAttack`, constantes
`{unitId: tauSmnDroneSniper, maxSummons: 3}`) invoque `tauSmnDroneSniper` sur une tuile libre
**adjacente au caster** — le drone naît avec `TriggeredAbility_Id 1120` — **et** pose `Markerlight`
sur **la cible visée**, et sur elle seule. Une seconde cible, jamais visée, fait le régime témoin.

⚠ **L'attaque doit être RANGED.** `MV71SniperDroneSquadAttackAbility$$PredictAttack` bascule sur
`IsMeleeAttack` : au CONTACT elle délègue à `ALoki_NormalAttackAbility` — **MESURÉ** : cible
adjacente ⇒ `Attack_Weapon_IsMelee: 1`, `spawned: 0`, aucun effet 1122. Les cibles sont donc
placées à **distance 3** du Marksman. C'est le seul piège de ce montage, et il est silencieux :
le cast « réussit » (dégât appliqué) tout en ne produisant NI drone NI marque.

La greffe (`case-92` §5bis) n'a donc pas été nécessaire. Elle **aurait été légitime** — le corps ne
lit rien du caster — et reste le recours si le sniper venait à disparaître du pool.

## 3. Mesure — deux régimes, deux couples (board, seed)

`pairUtility` natif contre le port, depuis la tuile du drone, les deux cibles étant dans son
`abilityTargets.fromHere` (hors portée, natif et port ne mesurent pas la même chose) :

```
board MC1_67 / seed 41504 — drone u96 @(2,3), poids servi = 60.0
  astraBullgryn  marked=True   nat=78.062097  port=78.062097  d=-0.000000 | mute=18.062097  manque=+60.000000
  astraCreed     marked=False  nat= 6.959652  port= 6.959652  d=+0.000000 | mute= 6.959652  manque= -0.000000

board C4_09 / seed 777 — drone u100 @(3,5), poids servi = 60.0
  astraBullgryn  marked=True   nat=78.024599  port=78.024599  d=-0.000000 | mute=18.024599  manque=+60.000000
  astraCreed     marked=False  nat=10.439478  port=10.439478  d=+0.000000 | mute=10.439478  manque= -0.000000
```

Conformité exacte sur les deux régimes et les deux couples (les bases diffèrent — 6.96 contre
10.44 — donc c'est bien un autre état, pas un rejeu). Playbook retiré du registre ⇒ le port perd
**exactement 60** sur la cible marquée, **rien** sur la témoin. C'est cette mesure qui **TRANCHE
l'assignation du littéral** : les trois clés de la classe valent 60 / 20 / 30, donc un terme mesuré
à 60 désigne `MarkedTarget` sans ambiguïté — elle n'est pas déduite du nom.

**Le terme appartient au PORTEUR** (face ATTACK isolée, foyer
`engine.utilities.tile.triggered_abilities_attack_utility`) :

```
drone     -> astraBullgryn  60.000000      summoner -> astraBullgryn  0.000000
drone     -> astraCreed      0.000000      summoner -> astraCreed     0.000000
```

Le SUMMONER vise **la même cible marquée depuis la même tuile** et ne porte pas 1120 (son passif
est `MV71SniperDroneSquad` 1119, sans face ATTACK) : 0. Un port qui aurait posé la condition dans
le composite, ou qui lirait l'état de la cible sans consulter le kit de l'attaquant, verserait le
poids ici aussi.

### 3bis. Le terme change un RÉSULTAT OBSERVABLE, pas seulement un scalaire

Régime d'**inversion d'argmax** : la cible témoin est calée à **4 000 PV** (`--unit-stat` sur
`Health` ET `RemainingHealth`), donc son utilité de dégât de BASE passe au-dessus de celle de la
marquée et reste sous le poids 1120 — la fenêtre mesurée à `MC1_67`/41504 est `[18.06 ; 78.06[`.

```
astraBullgryn  marked=True   nat=78.062097  port=78.062097 | mute=18.062097
astraCreed     marked=False  nat=69.565217  port=69.565217 | mute=69.565217
CHOIX DE CIBLE (argmax) : natif=astraBullgryn  port=astraBullgryn  port_mute=astraCreed
```

Le choix de cible du port suit le natif **grâce au terme** ; le port qui en est privé vise l'autre
unité. Même foyer que le trou mesuré par #415 (« c'est ce trou qui faisait diverger le choix de
CIBLE de l'attaque normale »).

## 4. Contre-épreuves JOUÉES (sur une contre-épreuve, VERT est le résultat suspect)

L'ancre de chaque patch a été vérifiée présente **avant** application, et la restauration vérifiée
identique au commit (`git diff` vide) **après**.

| # | mutation | verdict |
|---|---|---|
| CE1 | clé `MarkedTarget` -> `AdjacentTauFriend` (60 -> 20) | **MORD** — 2 tests rouges, écart **exactement 40.0** |
| CE2 | prédicat porté sur le CASTER au lieu de la CIBLE | **MORD** — 2 tests rouges, écart **exactement 60.0** |
| CE3 | substrat `active_effects` -> `has_effect` (perte du filtre `IsActive`) | **NE MORD PAS** — 5/5 verts (cf. §5) |
| CE4 | entrée 1120 retirée de `TRIGGERED_ATTACK_PLAYBOOKS` | **MORD** — 4 tests rouges sur 5 |

## 5. Ce que ce cas ne couvre PAS

* **Le paramètre `onlyActive` n'est pas discriminé PAR CE MONTAGE** (résidu `#443-r2`, **CLOS** —
  `docs/rl/case-443-r2-only-active.md`). CE3 est verte : sur ce substrat, `active_effects` et
  `has_effect` rendent la même chose pour `Markerlight`. Deux raisons, mesurées :
  `readEffectsByUnit` ne publie pas les effets `IsActive == 0` (sauf `includeInactive`), et
  `MarkerlightEffect` n'a pas de `CreateActiveCondition`. Le choix `active_effects` reste ici un
  **mirror du décompilé** (le littéral `1` du call-site), pas un résultat de mesure.
  ⚠ **Mais « CE3 muette » ne voulait PAS dire « paramètre mort »** — l'hypothèse concurrente était
  la bonne. #443-r2 a DÉRIVÉ l'inventaire des call-sites `onlyActive` et trouvé le régime
  manquant : un effet PRÉSENT-mais-INACTIF, atteint **en un `endturn`** sur `Overwatch_AutoAttack`
  (1009), dont le tour du porteur désactive l'instance
  (`RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal`, 2ᵉ `Triggered`). Là, la MÊME
  mutation de substrat MORD de **35 points** — et la mesure a fait tomber un écart de port
  (résidu `#443-r2-b1`, la face DÉCISION est aveugle aux effets inertes).
* **La face MOVE de 1120 n'est PAS portée** (résidu `#443-r1`, item à part entière) — et son
  absence de `TRIGGERED_MOVE_PLAYBOOKS` est un **TROU**, pas le comportement natif, contrairement à
  `Lakrimae` et `BarbedOvipositor`. `SaviorProtocolsPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__4$$MoveNext`
  est décompilé LU et bien vivant : il itère une collection d'unités que le natif obtient d'un slot
  d'interface (`0x7a`) appelé sur un service du playbook avec `case.MovementTile` en argument, et
  pour chacune verse `+AdjacentTauFriend` si `SaviorProtocolsAbility$$TargetIsValidTrigger` passe
  (évalué au slot `+0x188` du trigger monté), puis `+AdjacentTauParent` si
  `UnitExtensions$$GetParent(case.unit, state)` **est** cette unité. Le
  playbook surcharge EN PLUS `SaviorProtocolsPlaybook$$FilterMovementTiles` (slot 1 d'`IPlaybook`,
  non porté globalement — `case-r1b`), qui délègue au même `TargetIsValidTrigger` après un
  court-circuit `UnitExtensions$$HasRangedWeapon(unit)`. Trois artefacts natifs à porter, et
  `SaviorProtocolsUtility` (`CanBeProtector` / `GetUnitsWithUtilityForMove` / `GetUtilityPerUnit`,
  poids `SaviorProtocols.PerUnitWithAbilityInRange` = 20) est un **quatrième**, distinct.
* **Les autres porteurs** : les 3 npc et les deux autres summons (`tauSmnDroneShield`,
  `tauSmnDroneCommandLink`) ne sont pas confrontés. Le corps ne lisant rien du caster, ils
  n'ajouteraient aucun régime — mais ce n'est pas mesuré.
* **Le régime MULTI-CIBLES (AoE)** : comme pour #438, le terme s'ajoute par event. L'arme du drone
  (Piercing, 1 coup, portée 4) n'a pas de Blast.
* **La face COMBAT de 1120** (`SaviorProtocolsAbility$$CreateBehaviour` = `TransferDamage`, cf.
  `dsl-usage-primitives.tsv`) est hors périmètre : ce cas ne porte que la face DÉCISION.

## 6. Fichiers

* Port : `scripts/python/engine/playbook/savior_protocols.py` (le module existait en vestige
  **DORMANT** — contrat `case: dict`, jamais branché ; remplacé par le mirror à la signature du
  dispatcher actuel) ; registre : `engine/playbook/psyker.py` ; en-tête corrigé :
  `engine/playbook/__init__.py`.
* Mesure : `scripts/python/probe_443_savior_protocols_pair_term.py`
  (`--board`/`--seed`/`--flip-hp`).
* Garde : `scripts/python/tests/engine/test_443_savior_protocols_pair_term_live.py` (5 tests).
