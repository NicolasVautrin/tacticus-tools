# case-1020 — l'étage `PreDamageTaken` (par COUP, retour LU) et `SaviorProtocols`

Tranche d'**ÉTAGE**. La RE de `SaviorProtocols` était déjà faite et mergée
(`docs/rl/case-1019-way-of-the-short-blade.md` §4) ; ce qui manquait vivait dans le pipeline de
dégât. Numéro alloué par `probe_468_collision_numeros.py --suggere` → **#1020**.

RE : décompilé ghidra, build `rnca9r7q6c`.

---

## 1. Ce que le port n'avait pas, et pourquoi ça bloquait

`engine/runner/operations/damage.py::_apply_damage_pipeline` — le chokepoint des **quatre** vecteurs
de dégât — avait deux trous, tous deux nommés par #1019 :

1. il émettait `On(0x39 = EventTriggerType.PreDamageTaken)` **une fois par GROUPE** de coups, là où
   le natif appelle `IdunBattle.Operations.ApplyDamageOperation$$Execute` **une fois par COUP** ;
2. il **JETAIT le retour** de `pre_damage_taken_triggers(...)`, deux lignes avant
   `applied = thc.reduce(total)`. Aucun canal ne permettait à un trigger d'annuler ou de détourner
   le dégât.

`GeminaeSuperia` (#963), seul consommateur porté du vecteur, n'avait besoin ni de l'un ni de l'autre.

---

## 2. LE CANAL N'EST PAS LE RETOUR DU DISPATCH — c'est le CHAMP PENDANT

C'est la lecture qui débloque tout, et elle ne se devine pas. `ApplyDamageOperation$$Execute`, lu
aux octets :

```
healthComp[+0x64] = Nullable<DamageAppliedResult>(result);   // ECRITURE, avant toute emission
...
if (0 < DamageAppliedResult.get_Damage(&result))             // le GATE d'emission
    <publish 0x39>                                           // les triggers ont la main ICI
...
GetValueOrDefault(healthComp[+0x64], &pending);              // RELECTURE
local_7dc = FillUpStatComponent.Reduce(hp, pending.healthDamage);   // <- LE PENDING RELU
ReduceShield(.., pending.shieldDamage);
```

**Le dégât appliqué n'est pas le dégât calculé : c'est ce qui RESTE dans `healthComp+0x64` après que
les triggers `PreDamageTaken` ont eu la main.** La relecture est un
`System.Nullable<T>$$GetValueOrDefault` : un pending vidé rend la struct **ZÉRO**, donc `Reduce(0)`
n'enlève rien.

Et `IdunBattle.Operations.TransferDamageOperation$$GetDamage` le **CONSOMME** :

```
d = <healthComponent>+0x64
if (!d.HasValue) return null;
dmg = DamageAppliedResult.get_Damage(d.Value);   // = +0x08 shieldDamage + +0x04 healthDamage
*(qword*)(comp+0x64) = 0;                        // <-- LA CONSOMMATION
*(qword*)(comp+0x6c) = 0;
return new Damage(d.Value.<+0x00 damageProfileType>, dmg);
```

⚠ **Ce n'est donc PAS un bonus, c'est un DÉPLACEMENT.** Un port qui ajouterait le dégât au drone
sans le retirer à la victime **doublerait** le total.

`IdunBattle.Core.Services.DamageAppliedResult$$.ctor` donne les offsets (17 paramètres nommés) :
`+0x00 damageProfileType`, `+0x04 healthDamage`, `+0x08 shieldDamage`, `+0x14 hitIndex`,
`+0x18 isFirstDamagingHit`, `+0x94 wasHitTransferred`, `+0x98 initialDamage`. Et
`DamageAppliedResult$$get_Damage` = `*(int*)(this+8) + *(int*)(this+4)`, verbatim.

⚠ **`+0x94 wasHitTransferred` ferme l'émission d'`On(0x10 = DamageDealt)`** — c'est le
« l'octet `hitInfo+0x94` reste NON modélisé » du CLAUDE.md, désormais lu. Le port le porte
indirectement : `total` devenant `kept_health`, un groupe entièrement transféré ne passe plus le
gate `>= 1`.

---

## 3. Le port

| pièce | rôle |
|---|---|
| `engine/runner/components.py::PendingDamage` | mirror des 3 champs LUS du `DamageAppliedResult` ; `total()` = `get_Damage` |
| `engine/runner/components.py::HealthComponent.pending_damage` | `FillUpStatComponent+0x64` |
| `engine/runner/operations/damage_hits.py` → `per_hit_pending` | le `(health, shield)` DEMANDÉ de chaque coup atteignant le point d'écriture (même population que `per_hit`, donc SITE (A) déjà filtré) |
| `engine/runner/operations/damage.py::_pre_damage_taken_per_hit` | pose / émet / relit, rend `(kept_health, kept_shield, transfers)` |
| `engine/runner/operations/transfer_damage.py` | `IdunBattle.Operations.TransferDamageOperation` |
| `engine/runner/abilities/behaviours/transfer.py::TransferDamage` | la feuille DSL |
| `engine/runner/operations/triggers/loki/savior_protocols.py` | la `TriggeredAbility` 1120 |

**L'invariant de non-régression** : sans consommateur qui consomme le pending,
`kept_health == total` et `kept_shield == shield_dmg` **à l'identique**. C'est ce qui rend la
tranche sûre sur un foyer partagé par quatre vecteurs.

**`isFirstDamagingHit` devient PROPRE AU COUP** : seul le premier coup damageant le porte. Effet
mesuré sur `GeminaeSuperia` : **AUCUN** — son `matches` commence par
`if not ev.is_first_damaging_hit: return False`, donc les coups 2..N sortent avant toute évaluation
de `SummonLimit` ou de `GetPossibleSpawnTiles`. Le passage par-groupe → par-coup ne lui ajoute ni
spawn, ni évaluation, ni tirage.

⚠ **`#963-r3` n'est PAS fermé — son BLOCAGE l'est.** Ce résidu vise `Lifewards` (1049), le passif du
summon `adeptSmnGeminaeSuperia`, dont le `CreateBehaviour` se termine lui aussi par un
`TransferDamage(<+0x48>, <+0x60>, <+0x30>, <+0x88>, <+0x90>)` — **exactement la même signature que
`SaviorProtocols`**. La brique manquante (`TransferDamage` + le canal pendant) existe désormais ; ce
qui reste à porter, ce sont les trois artefacts propres à `Lifewards` (le trigger, les deux
`AddBondEffect`, `LifewardsBondEffect` / `LifewardsProtectingEffect`). Sa ligne de backlog est mise
à jour en conséquence.

⚠ **`CalculateDirectDamage` n'applique NI perçage NI armure**, et c'est LU en entier :

```
Fix64 d = (Fix64)damage;
ApplyGroupUnitDamageLimit(this, &d, null, target, <unitComp+0x18>, hitsMultipleMembers);
return (int)d;
```

Le montant transféré arrive **déjà résolu** (il sort d'un `DamageAppliedResult`, donc après crit /
block / armure côté victime) : le re-réduire côté protecteur serait une double application. Seul le
**member-cap** s'applique.

---

## 4. `SaviorProtocols` — l'artefact natif, RE-CONFRONTÉ

```
SaviorProtocolsAbility$$CreateTrigger =
    On(0x39 = EventTriggerType.PreDamageTaken, ownerNeedsToBeAlive = 0)
      & TargetIsValidTrigger()
      & IsAdjacent(Owner@<DSLSelectors+0x30>, Target@<+0x60>, 0 = UnitSelectionType.Any)
      & !TriggeringAbilityIs(0x530 = 1328 PinpointCounterOffensive)   // LU aux octets (§11)
      & !TriggeringAbilityIs(0x52f = 1327 ATemptingTrap)              // LU aux octets (§11)

SaviorProtocolsAbility$$TargetIsValidTrigger =            // PARTAGÉ avec la face MOVE (#443-r1)
    AreFriends(Target@<+0x60>, Owner@<+0x30>)
      & HasFaction(Target@<+0x60>, 9 = UnitFaction.Tau, 3)
      & !ActorHasTriggeredAbility(Target@<+0x60>, 0x460 = 1120 SaviorProtocols)
      & !AreEqual(Target@<+0x60>, Owner@<+0x30>)

SaviorProtocolsAbility$$CreateBehaviour =
    If( Maybe( ConfigConst(0x2a = AbilityConstantType.chance, abilityState) ),   // gameconfig : 50
        TransferDamage( caster = Caster@<+0x48>, originalTarget = Target@<+0x60>,
                        transferTarget = Owner@<+0x30>, <+0x88>, <+0x90> ),
        null )
```

**Deux lectures qui ne se devinent pas**

1. **Le `Maybe` est la surcharge PRÉDICAT** (`IdunBattleLogic.Entities.DSLTriggers$$Maybe` →
   `IdunBattle.Entities.Triggers.MaybeTrigger`), donc la **condition** de l'`If` — pas le nœud EFFET
   homonyme `IdunBattle.Entities.Behaviours.MaybeBehaviour` qui *enveloppe* un behaviour. Les deux
   rendent le même résultat observable ; seule la STRUCTURE de l'arbre diffère.
2. **La récursion drone → drone est fermée par `!ActorHasTriggeredAbility(Target, 1120)`** : un
   drone porteur ne peut jamais être la VICTIME d'un transfert. C'est ce qui rendait l'omission des
   deux `!TriggeringAbilityIs` sans danger de BOUCLE — mais pas sans conséquence : elle restait
   PERMISSIVE sur l'axe de la source du dégât, et §11 la ferme.

`TargetIsValidTrigger` est mirroré **deux fois**, et ce n'est pas un fork : la face MOVE le porte en
SCALAIRE (`playbook/savior_protocols.py::_target_is_valid_trigger`) parce que son substrat est un
contexte tile-leaf **sans `AbilityEntities`** ; ici le substrat EST un `AbilityEntities`, donc le
mirror est l'ARBRE, nœud pour nœud.

---

## 5. La confrontabilité — le VRAI porteur, pas une greffe

Les six porteurs sont `tauNpc2DroneSniper` / `tauNpc3DroneShield` / `tauNpc4DroneCommandLink` (npc)
et `tauSmnDroneSniper` / `tauSmnDroneShield` / `tauSmnDroneCommandLink` (summons). Aucun n'est au
pool.

Le chemin retenu n'est ni la greffe ni le summoner : c'est le **chemin de stats EXPLICITE**
(`--explicit-stats tauNpc2DroneSniper:65`, #419-r1-tr12-r2). Le drone arrive avec SES stats, SES
traits et SES armes — 4321 PV et `FixedArmor` 1114 au palier 65.

> Le chemin summoner aurait été inutilisable de toute façon : `tauMarksman` porte
> `MV71SniperDroneSquad` (1119, `constants.unitId = tauSmnDroneSniper`), et **cette ability n'est
> pas portée côté COMBAT** — le port ne spawnerait aucun drone.

**Le montage est INVERSÉ, et c'est délibéré** (`probe_1020_savior_protocols_live.py::stage()`) : le
couple protégé/protecteur est mis du côté ADVERSE, donc l'attaque est jouée par MOI, déterministe et
pilotable à l'action près, au lieu de dépendre du choix de cible de l'IA.

```
ultraTitus @(2,3) (MOI, mêlée)  --attaque-->  tauMarksman @(3,3) (ENNEMI, T'au, ne porte PAS 1120)
                                                    ^ ADJACENT
                                              tauNpc2DroneSniper:65 @(3,4) (ENNEMI, PORTE 1120)
```

---

## 6. La mesure — trois canaux indépendants, et un TÉMOIN qui tranche

`probe_1020_savior_protocols_live.py`, `MC1_67`, `--dmg 900`, trois seeds.

| seed | NATIF coups victime | NATIF coups drone | pas de flux `TransferDamage` | PORT coups | PORT transférés |
|---|---|---|---|---|---|
| 777   | `[0, 314, 0, 0]` | `[2581, 272, 216]` | **3** | `[2581, 250, 314, 275]` | 4 / 4 |
| 31337 | `[0, 0, 0, 0]`   | `[285, 322, 310, 286]` | **4** | `[285, 227, 322, 297]` | **3 / 4** |
| 4242  | `[323, 264, 0, 0]` | `[308, 233]` | **2** | `[323, 291, 264, 267]` | **3 / 4** |

**Ce qui est établi** :

* **RÉGIME MIXTE des DEUX côtés.** Le natif transfère un sous-ensemble STRICT des coups ; le port
  aussi (3 sur 4, seeds 31337 et 4242). **Un port PAR GROUPE ne peut pas produire ce régime** — il
  transfère tout ou rien. C'est le discriminant direct de la granularité, et il ne demande aucune
  arithmétique.
* **CONSERVATION.** Côté port, `victime_perdu + drone_perdu == total` sur les trois seeds
  (0+3420=3420, 285+846=1131, 264+881=1145). Le dégât se DÉPLACE.
* **La contre-épreuve SANS RAIL mord.** Registre désinscrit → victime `-3420 / -1131 / -1145`,
  drone `0`. Le verdict change, donc la mesure regarde bien le rail.
* **Le pas de flux natif est un témoin DIRECT** : `StepType.TransferDamage` (0x23 = 35) avec les tags
  `Caster_Id` / `Original_Target_Id` / `Final_Target_Id` — il ne se déduit d'aucun delta de PV. Les
  `hpDelta` du RPC (canal indépendant) concordent.

**LE TÉMOIN qui décompose l'écart** (`--temoin`, drone hors adjacence → zéro transfert des deux
côtés) :

| seed | NATIF | PORT |
|---|---|---|
| 777   | `[2581, 250, 314, 275]` | `[2581, 250, 314, 275]` |
| 31337 | `[285, 227, 322, 297]`  | `[285, 227, 322, 297]` |
| 4242  | `[323, 291, 264, 267]`  | `[323, 291, 264, 267]` |

**BIT-EXACT sur les quatre coups, sur les trois seeds.** Donc le montage est fidèle, le flux RNG est
aligné, et **l'écart n'existe QUE quand le transfert joue** — il n'est pas un écart pré-existant
d'étage de dégât. Sans ce bras, on aurait pu attribuer l'écart au mauvais étage.

**Ce qui RESTE ouvert, et sa cause exacte → `#1020-r4`.** Le nombre de coups transférés diffère
(natif 3/4 contre port 4/4 sur seed 777). La cause est la **POSITION du `Maybe` dans le flux RNG**,
pas la granularité : le natif entrelace `[valeur coup i][Maybe coup i]`, le port tire TOUTES les
valeurs (`_run_hits`) puis émet les `On(0x39)`. C'est visible directement — avec transfert, les
montants natifs des coups 2+ CHANGENT (`250, 314, 275` → `272, 216`), ceux du port non. Conséquence
mesurée : ~1 % sur le total (3383 natif contre 3420 port, seed 777).

---

## 7. Le bug que seul le LIVE a trouvé, et il était SILENCIEUX

`TransferDamage.execute` itérait **nu** le sélecteur `transferTargets`. Or `SaviorProtocols` y passe
`Owner@<DSLSelectors+0x30>`, un sélecteur **mono-entité** qui rend un **DICT** — l'itérer donne ses
CLÉS (des chaînes), donc `isinstance(u, dict)` est faux, donc `continue`, donc **aucune cible**.

Le trigger matchait, le behaviour s'exécutait, `execute_behaviour` rendait
`{"transferred": false}` — **aucune erreur, aucun crash, aucun transfert**. Même piège et même
parade que `entities/behaviours.py::Foreach`, qui le documente depuis longtemps. Gardé par l'étage 7
du cliquet.

---

## 8. Le cliquet, et pourquoi il n'a AUCUN plancher de population

`tests/engine/test_1020_transfert_par_coup_offline.py` — 18 tests, 7 étages. Chaque invariant porte
son **TÉMOIN** : un consommateur qui DOIT faire tomber `kept`, un groupe entièrement à zéro qui ne
DOIT rien émettre, un nom d'ability FABRIQUÉ que le registre DOIT refuser. Un étage dont le témoin
ne mordrait pas serait un vert vide.

**Vu ROUGE sous trois mutants** :

| mutation | rouges |
|---|---|
| normalisation dict retirée de `TransferDamage` | 1 (étage 7) |
| retour à l'émission PAR GROUPE | **8** |
| transfert en BONUS (pending non consommé) | 1 (étage 5) |

### Deux gardes #963 réécrites — elles approximaient leur invariant par la SYNTAXE

* `test_963_red_rampage_geminae_offline.py` comparait des **numéros de ligne** contre la chaîne
  `applied = thc.reduce(total)`. Elle a rougi sur un refactoring FIDÈLE (le chokepoint réduit
  désormais `kept_health`), et surtout : **deux appels peuvent être dans le bon ordre TEXTUEL et le
  mauvais ordre D'EXÉCUTION**.
* `test_963r2_first_damaging_hit_offline.py` exigeait un `ast.IfExp` **littéral** à l'argument
  `is_first_damaging_hit=`. Le repli existe toujours, un cran plus haut.

Les deux sont désormais **comportementales** : les PV n'ont pas bougé quand l'event part ; le repli
`None → is_first_hit` rend la bonne valeur pour LES DEUX valeurs de `is_first_hit`. Elles sont
**DURCIES, pas assouplies** — vues ROUGES sous une mutation (réduction de PV avant l'émission) que
l'ancienne version ne voyait PAS.

---

## 9. `RapidFire` — le troisième item, ÉCARTÉ sur lecture du décompilé

Le brief nommait `RapidFire` (Ultramarines) comme second mécanisme de validation de l'étage. **La RE
répond (c) : il ne traverse PAS le pipeline de dégât.**

```
RapidFireAbility$$CreateTrigger =
    On(0xe = EventTriggerType.UnitPostAbility, ownerNeedsToBeAlive = 1)
      & IsNormalAttack() & get_OwnerIsActor
      & !HasFlag(Caster@<+0x48>, 0x0 = UnitFlag.Moved)
      & !HasEffect(Caster@<+0x48>, 0x471 = 1137 RapidFire_BlockAbilities, 0, 6)

RapidFireAbility$$CreateBehaviour =
    ResetTurn(Owner@<+0x30>, resetMovement = 0)
      & AddEffect(0x471, ..., turns = <DSLFormulas+0x20> = Direct(1))
      & AddFlag(Caster@<+0x48>, 0x0 = UnitFlag.Moved)
```

Aucun des trois events d'`ApplyDamageOperation$$Execute`, et **aucun nœud producteur de dégât** :
ni `AttackWithAttackDamage`, ni `DirectDamage`, ni coup additionnel, ni `UseNormalAttackIfAble`.
Le mécanisme est **turn-economy** : il ROUVRE le tour, et la seconde attaque est une action neuve.

Le forcer dans cette tranche aurait été exactement l'ajustement qu'elle cherche à éviter : il ne
valide **rien** de l'étage. Ouvert en résidu **`#1020-r5`**, avec deux briques manquantes déjà
identifiées (une feuille `AddFlag`, et un substrat de blocage d'ability — `IsAbilityBlocked` n'en a
aucun côté port, cf. `runner/operations/turnflow.py`).

---

## 10. Ce qui n'est PAS couvert

* ~~**`#1020-r4`**~~ — **FERMÉ**, cf. §12.
* **`#1020-r6`** — `source_ability` n'est pas threadé par `execute_additional_hits` (§11). Le §12
  ne le change pas : le sink de ce vecteur reçoit donc `None`, comme le chokepoint avant lui.
* **`#1020-r5`** — `RapidFire` face COMBAT (§9).
* **Le régime MULTI-PROTECTEURS n'a pas été confronté** : un seul drone était adjacent. Le natif
  boucle sur `transferTargets` et le pending est consommé au PREMIER, donc les suivants voient un
  `Nullable` vide — le port le reproduit (`consume_pending_damage` rend `None`), mais aucune mesure
  live ne l'exerce.
* **Le drone MOURANT sous un transfert** n'a pas été mesuré en confrontation : observé une fois lors
  du dégrossissage (le drone est mort d'un transfert, le natif a émis `RemoveUnit`), mais le montage
  final borne le dégât (`--dmg 900`) pour garder la série entière observable.

---

## 11. Les trois résidus du foyer, FERMÉS — et le canal qui les tenait tous les trois

Les trois (`#1020-r1`, `#1020-r2`, `#1020-r3`) tombent sur **une seule lecture** : ce que
`IdunBattle.Operations.ApplyDamageOperation$$Execute` met dans l'`AbilityEntities` qu'il publie avec
`On(0x39)`, et ce qu'il relit APRÈS l'émission.

### 11.1 La lecture qui a failli conclure l'INVERSE

Le `.ctor` de cet `AbilityEntities` porte **neuf `(void *)0x0` consécutifs**. Les lire comme « les
emplacements d'ability sont nuls » mène tout droit à « le canal `+0x98` est vide sur ce vecteur,
donc les deux `!TriggeringAbilityIs` ne refusent jamais rien, donc le port n'est pas permissif ».
**C'est faux, et c'est la signature LUE qui le réfute** — celle de
`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor`, dans `data/symbols/<build>/frida/methods.tsv` :

```
caster, actor, target, owner, casterTile, activePlayer, casterTiles, effect, targetTile,
targetTiles, activeTarget, previousActiveTarget,
currentAbilityOrEffect, parentAbilityOrEffect, triggerAbilityOrEffect, damageReason, ...
```

Les neuf zéros sont les paramètres **4 à 12** — des ENTITÉS. Les trois `AbilityOrEffect` viennent
juste après, et l'appel réel passe `&local_788`, `&local_428`, `&local_4e8`. Deux des trois sont
**non nuls**, et leurs deux locales sont deux copies du **même** bloc `DamageAppliedResult+0x40` (le
`Nullable<AbilityOrEffect>` de son champ `source: IdunBattle.Operations.DamageSource`) :

| paramètre | → champ | contenu |
|---|---|---|
| `currentAbilityOrEffect` | `+0x60` | `damageResult[+0x40..+0x58]` |
| `parentAbilityOrEffect`  | `+0x7c` | **mis à zéro** |
| `triggerAbilityOrEffect` | `+0x98` | `damageResult[+0x40..+0x58]` — le MÊME |

Côté port ce bloc EST `source_ability`, déjà résolu par `_damage_source_ability` (mirror de
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules$$GetDamageSourceAbility`). Il ne
restait qu'à le publier sur le vecteur.

**Leçon de méthode** : une position d'argument ne se compte pas à l'œil sur un `.ctor` à 32
paramètres — elle se LIT dans la table des signatures.

### 11.2 `#1020-r3` — le port ÉTAIT permissif

Les deux immédiats sont lus **AUX OCTETS** (ghidra ne montre que le buffer de retour d'
`IdunBattle.Core.AbilityOrEffect$$op_Implicit`) : `mov edx, 0x530` puis `mov edx, 0x52f`, juste avant
le `call`, et les deux `call` visent la surcharge dont le paramètre de métadonnée se nomme
`triggeredAbility` et dont le corps appelle `IdunBattle.Core.AbilityOrEffect$$set_TriggeredAbility`.
Donc `TriggeredAbilityType.PinpointCounterOffensive` (1328) et `TriggeredAbilityType.ATemptingTrap`
(1327) — ni `ActiveAbilityType`, ni `EffectType`, que le seul ordinal n'aurait pas séparés.

Le nœud `TriggeringAbilityIs` mirror `IdunBattle.Entities.Triggers.AbilitiesAreEqualTrigger$$ShouldTrigger` :
`HasValue` faux d'un côté ou de l'autre → **FAUX** ; sinon `op_Equality`. Ce faux est la réponse
NATIVE, pas une dégradation choisie — et il est load-bearing : sous `op_LogicalNot`, un canal vide
**OUVRE** le gate. **Porter le nœud sans porter le canal aurait donc été un vert vide.**

### 11.3 `#1020-r1` — le bouclier suit les PV, sur le même pending relu

`ApplyDamageOperation$$Execute` relit le pending APRÈS l'émission et en tire les DEUX parts depuis le
MÊME `GetValueOrDefault` :

```
GetValueOrDefault(healthComp[+0x64], &pending);
local_7c8 = FillUpStatComponent$$Reduce(hp, pending.healthDamage);
ApplyDamageOperation$$ReduceShield(this, target, pending.shieldDamage);
```

Un coup consommé par `TransferDamageOperation$$GetDamage` met les deux à zéro : le natif n'enlève NI
PV NI BOUCLIER. `_deplete_shield` a donc quitté les APPELANTS pour le chokepoint.
**Second effet, lu au même endroit** : il passe ainsi sous le gate `Overkilled` du SITE (A), qui
`return` avant l'écriture du pending — une cible déjà overkillée ne perd plus son bouclier, ce que le
natif ne faisait déjà pas.

### 11.4 `#1020-r2` — un GATE et une ATTRIBUTION, pas « deux noms »

Les deux `Nullable<AbilityOrEffect>` n'ont pas le même rôle :

* **GATE** — `IdunBattle.Entities.Behaviours.TransferDamageBehaviour$$Execute` exige `HasValue` sur
  LES DEUX et `return` sans rien faire sinon. Un dégât qui ne nomme aucune ability source ne se
  transfère PAS. Le port transférait toujours.
* **ATTRIBUTION** — `attackAbility` est le SEUL que `TransferDamageOperation$$Execute` consomme :
  recopié sur 0x18 octets, passé en 5e argument `abilityOrEffect` du slot **64 = `DirectDamage`**
  (slot RÉSOLU dans `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`, jamais deviné).
  `transferAbility`, lui, n'a aucun usage au-delà du null-check du pointeur.

**L'ASYMÉTRIE DE MOMENT est ce qui donne leurs valeurs.**
`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` écrit `+0x60` **AVANT** d'appeler le
behaviour et `+0x98` **APRÈS**. Donc pendant le behaviour : `transferAbility` (= `+0x60`) vaut la
triggered elle-même, et `attackAbility` (= `+0x98`) a gardé l'ability qui inflige le dégât. Si
l'écriture `+0x98` arrivait avant, `attackAbility` vaudrait `SaviorProtocols` au lieu de l'attaque.

### 11.5 Le bug LATENT trouvé dans le même foyer

`transfer_damage_operation` déplétait le bouclier du PROTECTEUR à la main, avant le chokepoint, via
`shc.shield` — **un attribut qui n'existe pas** (`ShieldComponent.__slots__` vaut
`('shields', 'next_id')`). Reproduit : `AttributeError: 'ShieldComponent' object has no attribute
'shield'` dès qu'un protecteur porte un bouclier. Jamais atteint parce que les six porteurs sont des
drones T'au sans bouclier, et que **rien ne montait ce régime** — il est sorti en écrivant la fixture
de `#1020-r1`. La ligne disparaît : avec `r1`, la déplétion vit dans le chokepoint, qui la fait
correctement et **une seule fois**.

### 11.6 Ce que la fermeture a OUVERT

`#1020-r6` : `execute_additional_hits` est le SEUL des quatre vecteurs de dégât qui ne threade pas
`source_ability`. Le gate de `r2` y devient donc **RESTRICTIF** — un transfert déclenché par un
groupe de coups additionnels est refusé côté port alors que le natif l'accepterait. C'est **nommé
plutôt que masqué** : rendre le gate permissif « au cas où » ré-ouvrirait le trou que `r2` ferme.

### 11.7 Validation

Chaque garde a été **vue ROUGE avant son fix**, par mutation adversariale du PORT (jamais du test) :

| résidu | mutation | rouge obtenu |
|---|---|---|
| `r3` | les deux conjoints retirés de l'arbre | 3 failed / 9 passed — « le gate DOIT fermer, or il a laissé passer » |
| `r1` | le foyer relit `shield_dmg` (calculé) au lieu de `kept_shield` (relu) | `assert 80 == 200` sur le bouclier de la victime |
| `r2` | gate retiré + `source_ability` coupé | 4 failed / 23 passed — « la `DamageSource` doit NOMMER `attackAbility` (1013), obtenue None » |

Le bras **TÉMOIN** du probe live (drone hors adjacence, zéro transfert) reste **BIT-EXACT** sur
3 seeds après les trois fix — `[2581, 250, 314, 275]` / `[285, 227, 322, 297]` /
`[283, 279, 315, 268]`, totaux 3420 / 1131 / 1145 des deux côtés — ce qui établit qu'aucun des
**quatre** vecteurs de dégât n'a bougé (le fix `r1` les touche tous). Le bras NOMINAL transfère
toujours (4 transferts sur 4 coups), donc le gate de `r2` ne ferme pas le régime réel.
## 12. `#1020-r4` — la POSITION du tirage, et pourquoi la granularité ne suffisait pas

`#1020` avait rendu la GRANULARITÉ juste (une émission par COUP). Le §6 mesurait pourtant encore un
écart : natif 3 transferts sur 4, port 4 sur 4, et **les montants natifs des coups 2+ CHANGEAIENT
dès que le transfert jouait** (`250, 314, 275` -> `272, 216`) là où ceux du port ne bougeaient pas.
C'est la signature d'un décalage de FLUX, pas d'un étage de dégât — et le bras `--temoin`
(bit-exact) l'avait déjà établi.

### Ce que dit le décompilé

`IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` :

```
while (i < numHits) {
    ...  ExecuteHit(this, attaquant, defenseur, profil, ability, options, initialHealth, denied);
    ADamageOperation$$UpdateHitGroupAfterHit(this, hitGroup);
    ADamageOperation$$UpdateCurrentAttackAfterHit(this, attack, &res);
    ...  i++;
}
```

Un coup est donc **intégralement** résolu avant que le suivant ne tire quoi que ce soit. Et dans
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, l'ordre lu est :

```
IdunBattle.Core.HitDamage$$GetDamage           <- LA VALEUR
IdunBattle.Core.AttackHit$$.ctor
RollCritical (slot 0xa)
IdunBattle.Entities.Abilities.AbilityEntities$$.ctor
On(6 = PreAttackHit) ; On(7)
<sous-operation de split>                       <- le port : calculate_damage_operation
IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers
```

L'émission d'`On(0x39 = EventTriggerType.PreDamageTaken)` vit dans
`IdunBattle.Operations.ApplyDamageOperation$$Execute`, dont
`IdunBattle.Core.Services.OperationProcessor$$ApplyDamage` est le **SEUL** appelant (xref unique) :
elle tombe donc **entre le split et l'after-hit**. D'où l'entrelacement
`[valeur i][trigger i][valeur i+1]...`, et jamais `[toutes les valeurs][tous les triggers]`.

### Le port

| pièce | rôle |
|---|---|
| `damage_hits._run_hits(pending_sink=...)` | appelle le chokepoint AU POINT où `per_hit_pending` est renseigné — le seul point du port qui satisfait la lecture ci-dessus |
| `damage.AttackDamageOperation.make_pre_damage_taken_sink` | le CORPS du chokepoint (pose du pending, gate `0 < get_Damage`, émission, relecture `GetValueOrDefault`, purge) |
| `damage.AttackDamageOperation.pre_damage_taken_of` | le foyer UNIQUE de lecture du cumul |
| `damage._apply_damage_pipeline(pre_damage_taken=...)` | ne fait plus qu'en LIRE le cumul |

⚠ **LE CUMUL VIT SUR LE SINK — il ne transite NI par `hits_result`, NI par le retour de
`_run_hits`.** Les deux raccourcis ont été essayés et ont **cassé du code existant** :

1. **clé de `hits_result`** — `operations/additional_hits.py` ne threade **pas** `hits_result` au
   chokepoint, donc ce vecteur émettait **deux fois** (une fois dans la boucle, une fois au
   groupe) : ni erreur ni crash, juste un tirage de trigger de trop par groupe additionnel.
   Trouvé par l'étage 5 du cliquet.
2. **clé du retour de `_run_hits`** — ce dict est le **CONTRAT DE SORTIE** du canal. Plusieurs
   harnais SUBSTITUENT `_run_hits` par un stub qui le rend *en entier* ; lire une clé de plus les
   fait lever `KeyError`. **Deux gardes existantes l'ont attrapé** —
   `test_failed_block_attack_scope_offline.py::test_execute_additional_hits_CHAINE_l_etat_de_groupe_en_groupe`
   et `test_additional_hits_variant_signatures_offline.py::test_toute_substitution_expose_le_contrat_de_SORTIE`.
   Aucune des deux n'a été touchée : elles gardaient un contrat **réel**.

La leçon est la même dans les deux cas : **le cumul appartient à son PRODUCTEUR**. L'appelant
possède déjà le sink — le faire transiter par un canal partagé, c'est élargir un contrat que
d'autres tiennent. D'où `_PreDamageTakenSink.cumul()` et le foyer de lecture `pre_damage_taken_of`.

Les **quatre** call-sites moteur threadent leur sink (`damage_ops/normal.py`,
`damage_ops/ability.py`, `damage_ops/normal_like.py`, `additional_hits.py`) ; tout autre appelant
(DoT, knockback, dégât direct) laisse `pending_sink=None` et le chokepoint de groupe reprend la
main — strictement le comportement d'avant.

### La mesure

`probe_1020_savior_protocols_live.py`, `MC1_67`, `--dmg 900` :

| seed | NATIF victime / drone | PORT victime / drone | transferts natif / port |
|---|---|---|---|
| 777   | `[0, 314, 0, 0]` / `[2581, 272, 216]`  | idem | 3/4 · 3/4 |
| 31337 | `[0, 0, 0, 0]` / `[285, 322, 310, 286]` | idem | 4/4 · 4/4 |
| 4242  | `[323, 264, 0, 0]` / `[308, 233]`      | idem | 2/4 · 2/4 |

**Coup à coup, et le CARDINAL des transferts avec.** Total seed 777 : **3420 -> 3383**, la valeur
native. Le bras `--temoin` (drone hors adjacence) reste bit-exact `[2581, 250, 314, 275]` : le
changement est inerte quand aucun trigger ne consomme.

### Le cliquet, et la prémisse qu'il a failli faire accuser au port

`tests/engine/test_1020r4_position_du_tirage_offline.py` — 15 tests. L'étage 1 est arithmétique :
le sink d'index `k` doit voir `(k+1) * cout_coup + k * cout_sink` tirages déjà consommés, là où un
port par-groupe les verrait tous à `4 * cout_coup + k * cout_sink`.

⚠ **Écrite avec des coûts CODÉS EN DUR (« 1 tirage par coup »), cette arithmétique rougissait sur un
port JUSTE.** Le mode ATTACK en consomme 2 (la valeur plus le resolve slot 8 d'
`IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage`), et `next_bool` 2 aussi.
Les deux coûts sont donc **dérivés du montage** (`_couts()`), qui vérifie au passage que le coût
d'un coup est CONSTANT et que le sink consomme réellement — sans quoi le témoin serait dégénéré et
les deux hypothèses de position coïncideraient (l'étage l'assertionne explicitement).

**L'étage 4 existe parce que cette tranche a causé la régression qu'il garde** : le retour de
`_run_hits` doit être **IDENTIQUE avec et sans sink**. Il voit la fuite **à la source** ; les deux
gardes existantes, elles, ne la voient qu'une fois qu'elle atteint `additional_hits` — vérifié, en
remettant la clé : l'étage 4 rougit (2 tests) pendant que les deux gardes restent **VERTES**.

**Deux gardes `#963-r2` réécrites**, pour la même raison que les deux gardes `#963` du §8 : elles
ancraient sur le **littéral** d'un call-site (`is_first_damaging_hit=(not _damaging_done)`) et sur
un jeu de `ast.Name` NUS. Une variable intermédiaire les faisait rougir sur un câblage fidèle et --
symétriquement -- les aurait laissées **vertes** si cette variable avait été rebranchée sur
`g_first_hit`. Elles résolvent désormais les alias (`_noms_sources`) et ancrent sur la LECTURE de
l'état, pas sur son écriture textuelle. Vues rouges avant, re-vues rouges après sous deux mutations
(flag rebranché sur l'index ; bascule déplacée avant la lecture).

### Ce que `#1020-r4` ne ferme pas

* **Rien du bouclier** : `#1020-r1` est fermé par le §11, qui a déplacé `_deplete_shield` des
  appelants vers le chokepoint. Les deux tranches se composent proprement — la déplétion consomme
  `kept_shield`, et le sink alimente `kept_shield` coup par coup au lieu du groupe.
* ⚠ **Ce que le rebase a failli PERDRE, et qui est le vrai point d'attention de cette composition :
  le canal `source_ability` (`AbilityEntities+0x98`) du §11.3.** L'émission ayant migré dans la
  boucle, ce canal doit l'y suivre : il est résolu au call-site AVANT `_run_hits`, donné au **sink**
  ET au chokepoint. Le laisser au seul chokepoint — ce que produit une résolution naïve du conflit —
  rendrait les deux `!TriggeringAbilityIs` **aveugles pour les quatre vecteurs moteur**, c'est-à-dire
  pour tous ceux qui ont une décomposition par coup, et **sans aucune erreur**.
* **`#1020-r6` n'est pas affecté** : `execute_additional_hits` ne threade toujours pas
  `source_ability`, donc son sink le reçoit `None` — exactement l'état que ce résidu décrit.
* Le régime **MULTI-PROTECTEURS** et le drone **MOURANT** restent non confrontés (§10).
* Les vecteurs **sans décomposition par coup** (DoT, knockback, dégât direct) gardent l'émission de
  groupe : côté natif le groupe EST le coup, donc la position y est déjà juste.
