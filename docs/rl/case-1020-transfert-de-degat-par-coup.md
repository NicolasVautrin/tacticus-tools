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
      & !TriggeringAbilityIs(<AbilityOrEffect A>)      // NON LU -> #1020-r3
      & !TriggeringAbilityIs(<AbilityOrEffect B>)      // NON LU -> #1020-r3

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
   drone porteur ne peut jamais être la VICTIME d'un transfert. C'est ce qui rend l'omission des
   deux `!TriggeringAbilityIs` (#1020-r3) sans danger de boucle.

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

* **`#1020-r1`** — le BOUCLIER de la victime n'est pas restitué sur un coup transféré. Le natif
  annule aussi `ReduceShield` (il lit `pending.shieldDamage`, donc 0) ; le port déplète le bouclier
  dans `_deplete_shield`, appelé par les APPELANTS **avant** le chokepoint. `kept_shield` est juste
  pour les étages en aval, mais la déplétion du `ShieldComponent` a déjà eu lieu. Régime d'exercice :
  victime portant un `ShieldComponent` non nul au moment d'un coup transféré. **Non atteint** par
  les porteurs de `SaviorProtocols` (cibles T'au sans bouclier).
* **`#1020-r2`** — `transferAbility` / `attackAbility` (`<DSLSelectors+0x88>` / `<+0x90>`) sont
  portées en argument nommé mais pas consommées : l'attribution de mort du protecteur passe par
  `caster`, comme tous les autres vecteurs portés.
* **`#1020-r3`** — les deux `!TriggeringAbilityIs(<AbilityOrEffect>)` du trigger ne sont **pas
  lus** : le décompilé perd l'argument d'`IdunBattle.Core.AbilityOrEffect$$op_Implicit` (seul le
  buffer de retour est visible) et `read_bytes` plafonne à 32 octets. Les omettre est PERMISSIF ;
  la récursion drone → drone, seul régime dangereux, est déjà fermée (§4).
* **`#1020-r4`** — la POSITION du `Maybe` dans le flux RNG (§6). La granularité est juste, l'ordre
  des tirages non.
* **`#1020-r5`** — `RapidFire` face COMBAT (§9).
* **Le régime MULTI-PROTECTEURS n'a pas été confronté** : un seul drone était adjacent. Le natif
  boucle sur `transferTargets` et le pending est consommé au PREMIER, donc les suivants voient un
  `Nullable` vide — le port le reproduit (`consume_pending_damage` rend `None`), mais aucune mesure
  live ne l'exerce.
* **Le drone MOURANT sous un transfert** n'a pas été mesuré en confrontation : observé une fois lors
  du dégrossissage (le drone est mort d'un transfert, le natif a émis `RemoveUnit`), mais le montage
  final borne le dégât (`--dmg 900`) pour garder la série entière observable.
