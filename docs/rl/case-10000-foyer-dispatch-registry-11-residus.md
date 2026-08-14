# #10000 — Le foyer `triggers/dispatch/registry.py` (11 résidus) : un LEVIER ou 11 TRANCHES ?

**Question posée** : `dispatch/registry.py` est le fichier le plus nommé du backlog en `FOYER:`
(11 résidus ouverts). Est-ce un **vrai levier** — une édition qui sert N résidus — ou **11 tranches
qui partagent un fichier** ?

---

## 1. Le verdict, et la mesure qui le tranche

**11 TRANCHES QUI PARTAGENT UN FICHIER. Le levier existe, mais il n'est PAS dans `registry.py`.**

Trois mesures, toutes re-dérivables :

1. **`registry.py` ne contient AUCUNE logique.** 2 443 lignes : un bloc d'imports (l. 13-358), huit
   dicts littéraux, et **exactement deux instructions exécutables** — les boucles de fusion
   `bond_removal_registry_entries()` / `pending_attack_registry_entries()` en fin de fichier. Aucun
   `def`, aucune `class`, aucun `if`. C'est une **surface de déclaration**, pas du code partagé.
2. **Les 11 résidus visent CINQ dicts différents**, à raison de 1 à 3 lignes chacun :
   `ABILITY_TRIGGERS` (#1019-r2, #963-r3, #1020-r5), `EFFECT_TRIGGERS` (#1074, #1002-r1),
   `RELIC_ABILITY_TRIGGERS` (#462-…, #999-r1), `PASSIVE_HELPER_ABILITY_TRIGGERS` (#521-r4),
   `CUSTOM_TRIGGERED_ABILITIES` (#1001-r1). Aucune paire ne se recouvre.
3. **Deux des onze ne touchent même pas le fichier** : `#419-r1-tr9-r4-r1-r2-r1c` (dont le `FOYER:`
   est FAUX, cf. §3) et `#443-r2-b2` (une confrontation, sans code).

**Le vrai levier, lui, est mesuré et il vit ailleurs** : la paire de feuilles DSL
`AddFlag`/`RemoveFlag` (`engine/runner/abilities/behaviours/flags.py`), qui n'existait pas et que
**deux** résidus du lot exigent — `#1019-r2` et `#1020-r5`. C'est la seule dépendance partagée du
lot, et elle est livrée par cette tranche.

**Conséquence pour le dispatch** : grouper des résidus par `registry.py` ne réduit PAS le coût, ça
sérialise onze tranches indépendantes derrière un fichier qu'elles ne modifient qu'à la marge. Le
critère de groupage utile sur ce foyer est le **vocabulaire manquant**, pas le registre.

---

## 2. Ce que la tranche a trouvé — DEUX étages, tous deux invisibles

Les deux sont des **paramètres natifs que le port codait en dur**, donc des divergences dont
aucun test ne pouvait rougir.

### 2.1 `!HasFlag(attacker, 0x15 = UnitFlag.ForceRangedAttack)` — le 2e conjoint de la branche MÊLÉE

`IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack` (slot `0xaf`) :

```
if (rangeType == Normal && !UnitExtensions.HasFlag(attacker, 0x15) && AreEntitiesAdjacent(..))
    return FindMeleeWeapon(...);
return FindRangedWeapon(attacker, attackerTiles, target, distance);
```

Le conjoint du milieu n'était porté **nulle part** sur la voie de l'attaque normale : le port
choisissait la branche mêlée sur la seule adjacence. Il est désormais au **foyer partagé**
(`services/battle_query.py`, donc visible des deux faces), défaut `False` = strict no-op.

**Effet de bord réparé au passage** : le SECOND appel à `select_weapon_pierce` de
`damage_ops/normal.py` (celui du bonus de perçage) perdait déjà `is_adjacent` — régression
préexistante de #419-r1-tr14-r1-r1, qui ne mordait que si un `Hailstrike_ExtraPierce` était posé.
Le laisser aurait **défait** l'étage ci-dessus.

### 2.2 `ignoreUnitHavingAbility` — le 8e argument de `TriggerAbility`

`IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` :

```
abilityState = ignoreUnitHavingAbility ? new Nullable<AbilityState>(default)
                                       : UnitExtensions.GetAbilityState(entity);
if (abilityState.HasValue) { ... }
```

Les deux call-sites déjà portés (`HeraldOfTheApocalypse`, `StormboyzStrike_Miss`) passent `false` —
le paramètre était donc invisible, et le port l'avait figé. Le troisième,
`…FinalVengeance_UnitEffect$$CreateTargetTriggerBehaviour`, passe **`true`**, et c'est
**littéralement ce bit qui fait fonctionner la mécanique** : le summon impérial qui reçoit l'effet
`1454` ne PORTE pas `FinalJustice`, l'effet la lui prête.

**La faute qu'il aurait produite est silencieuse et permissive-en-moins** : `notCarrying` aurait
avalé 100 % des déclenchements, l'événement serait parti avec `dispatched: True`, et aucune
assertion d'état n'aurait bougé.

---

## 3. Le `FOYER:` d'un résidu peut être FAUX — mesuré sur `#419-r1-tr9-r4-r1-r2-r1c`

La fiche dit : « `LegendaryCommander` n'est pas dans `ABILITY_TRIGGERS` », `FOYER: registry.py`.
La **prémisse est vraie**, le **foyer ne l'est pas**.

`…Triggered.Loki.LegendaryCommanderAbility$$CreateTrigger` est **absent des tables** (corps
dédupliqué par ICF). Résolu **slot à slot dans le bloc `methodPointers` du PE** — la classe déclare
exactement `[CreateTrigger, CreateBehaviour, .ctor]` —, son `CreateTrigger` **EST** le corps que la
table nomme `…Active.Loki.SummaryExecutionAddBaseEffectAbility$$CreateTrigger`, c'est-à-dire
`return <DSLFactory+0x88 = DSLTriggers>+0x30`. Et `IdunBattleLogic.Entities.DSLTriggers$$
InitializeShared` écrit ce slot verbatim :

```
<DSLTriggers+0x30> = On(0x21 = AbilityInit) & <+0x70 = YesTrigger> & get_OwnerIsActor
```

C'est donc la branche **INCONDITIONNELLE** de la famille — celle que le port matérialise par
**SEEDING** (`ABILITY_INIT_OWNER_EFFECTS`, `entities/effects/factory.py`), exactement comme
`AllIsDust` (#1052) et `SynapticInsight` (#1073), **qui partagent le même corps de trigger**.
L'inscrire dans `ABILITY_TRIGGERS` aurait fait un **DOUBLE FIRE** avec ce seed.

**Méthode réutilisable** : quand un `CreateTrigger` manque des tables, ses voisins dans
`methodPointers` (8 octets, dense) donnent la déclaration de la classe ; `.pdata` (12 octets,
`begin/end/unwind`) ne donne, lui, que le voisinage d'ADRESSE et **ne dit rien** de la classe — les
deux voisins de `LegendaryCommanderAbility$$CreateBehaviour` y appartiennent à deux autres classes.

---

## 4. Une MAJ mesurée DÉTRUITE PAR UN MERGE — `#521-r4`

Le bloc « MAJ 2026-08-14 » de `#521-r4` (2 255 caractères : le dict `<statics>+0x78` relu verbatim,
le **vrai NOM et le vrai NAMESPACE** des deux classes de `1244`, leurs trois arbres, le piège
d'enum dans les deux sens, et le porteur `blackForgefiend` mesuré DANS le pool) était présent à
`81b8809e` **et** à `a0d3d8ba`, et a **DISPARU** à `5c4c1bf2` — une PR qui traitait `#521-r9`, la
ligne **voisine de la même famille**.

Diff caractère par caractère des deux versions de la ligne : **un seul opcode, un `insert` de
2 255 caractères**. Rien d'autre n'avait bougé ⇒ la restauration ne pouvait rien écraser, et elle
est faite.

**C'est exactement le risque que le CLAUDE.md décrit** pour ce fichier (90 % des PR le touchent) :
une PR en vol tombe dans un hunk adjacent, sur des lignes de tableau modifiées des deux côtés, et
écrase une ligne que personne n'a relue. Le coût ici n'est pas cosmétique : sans cette MAJ, la
fiche **re-affirme** que la classe de `1244` est « INTROUVABLE sous tout nom essayé » — un blocage
de lecture **déjà levé** — et enverrait un agent refaire la recherche pour re-conclure faux.

**Ce que ça suggère** : un cliquet qui compare, pour chaque ligne de `backlog.md`, la longueur du
corps entre `HEAD` et la base de merge, et qui ROUGIT sur une ligne qui RÉTRÉCIT sans que la PR
courante l'ait touchée. Résidu à ouvrir si le gisement se confirme.

---

## 5. Le témoin de `#1019-r2` était DÉGÉNÉRÉ, et la fiche le proposait

La fiche nomme `tauAunShi` comme « PORTEUR CONFRONTABLE IDENTIFIÉ ». Mesure sur le gameconfig :
`tauAunShi` porte `melee=[Power]`, **`ranged=[]`**. Or l'ability force une attaque **à distance** :
le natif y prend `FindRangedWeapon -> null`, et `ALoki_NormalAttackAbility$$ExecuteBehaviour`
retourne sans rien faire (`if (weapon == null) return;`). L'attaque supplémentaire est un **NO-OP
des deux côtés** — un test monté dessus aurait été **vert sans rien mesurer**.

Le vrai témoin est **`tauFarsight` lui-même** : il porte les DEUX armes (`Power` en mêlée, `Plasma`
portée 2) et il est dans son propre marqueur, parce que le `CreateTargetSelector` de l'effet `1500`
finit par `op_Addition Owner@<DSLSelectors+0x30>` — branche que son jumeau `1499` n'a **pas**.

### La cascade native, mesurée (build `t6dpr4k06g`, `MC1_67`/777, Farsight injecté)

```
[Ability_Power e=77 «Loki_NormalAttack»]
  Info  Attack_Weapon_DamageProfile=14  Attack_Weapon_IsMelee=1      <- 4 coups, Power
  [Ability_Power e=77 «WayOfTheShortBlade»]                          <- le trigger FIRE
    [Ability_Power e=77 «Loki_NormalAttack»]
      Info  Attack_Weapon_DamageProfile=7  Attack_Weapon_IsMelee=0   <- 2 coups, Plasma, AU CONTACT
```

Trois faits qu'aucune lecture seule ne donnait : (1) Farsight déclenche sur **sa propre** attaque ;
(2) la seconde attaque est **RANGED alors que le caster est ADJACENT** — le `ForceRangedAttack`, et
donc le « even if they are adjacent to it » de l'i2 ; (3) **il n'y a pas de troisième attaque** — le
garde-fou de ré-entrance tient, et il tient **parce que** l'étage §2.1 existe : la sous-attaque étant
ranged, le `IsMeleeAttack()` du `CreateTrigger` est faux pour elle.

**Confrontation port↔natif** : `Power`/4 coups sans le drapeau, `Plasma`/2 coups avec — le port rend
**exactement** le même couple. Témoin non dégénéré par construction (`Power ≠ Plasma`, `4 ≠ 2`), et
le test l'assertionne avant de conclure.

---

## 6. Verdicts par résidu

| résidu | verdict | `BLOCAGE` avant | après |
|---|---|---|---|
| `#419-r1-tr9-r4-r1-r2-r1c` | **FERMÉ** — prémisse vraie, **`FOYER:` faux** (§3). Pose portée par `ABILITY_INIT_OWNER_EFFECTS`. Résidu ouvert : `#419-…-r1c-r1` (classe d'effet de `1394`) | `aucun` | — |
| `#1019-r2` | **FERMÉ** — prémisse re-lue VERBATIM et conforme ; 3 briques manquantes livrées (§2.1, §5) | `aucun` | — |
| `#1002-r1` | **FERMÉ** — prémisse re-lue VERBATIM et conforme ; étage `ignoreUnitHavingAbility` ouvert (§2.2). Résidu ouvert : `#1002-r3` (l'Operation d'`ApplyInternal`) | `aucun` | — |
| `#963-r3` | prémisse **CONFIRMÉE** par mesure ; **correction de NAMESPACE** (`…Abilities.Triggered.LifewardsAbility`, sans `.Loki`) et les 2 effets nommés (`Lifewards_BondEffect` 1060, `Lifewards_Protecting` 1240) | `aucun` | `aucun` |
| `#999-r1` | prémisse **CONFIRMÉE** sur ses 4 points ; seul `DSLFormulas$$TilesMovedThisTurn` manque, substrat présent | `aucun` | `aucun` |
| `#1074` | prémisse **CONFIRMÉE** (`EFFECT_TRIGGERS[1061]` absent, `1061 ∉ UNTARGETABLE_EFFECT_TYPES`, pose déjà portée) ; arbre **NON RE-LU** | `aucun` | `aucun` |
| `#1001-r1` | structure **CONFIRMÉE** (`1018 ∉ CUSTOM_TRIGGERED_ABILITIES`) ; la question de RE **NON TRANCHÉE** | `aucun` | `aucun` |
| `#1020-r5` | prémisse **PÉRIMÉE DE MOITIÉ** : la feuille `AddFlag` EXISTE désormais. Reste le seul substrat `IsAbilityBlocked` + l'effet `1137` (nom réel : `RapidFire_BlockAbilities`) | `etage` | `etage` |
| `#462-…-r4-r1` | prémisse **CONFIRMÉE** (les 2 nœuds bien absents, les 5 autres bien présents) ; **correction de NOM** (`Lakrimae_SummonPoxwalker_Ability`) | `etage` | `etage` |
| `#443-r2-b2` | prémisse **CONFIRMÉE** ; la classe `EarlyWarningOverrideHitReductionPurge` est inscrite sous `1145`, pas `1146` | `etage` | `etage` |
| `#521-r4` | prémisse **CONFIRMÉE**, MAJ **RESTAURÉE** (§4) ; les 3 pièges d'enum **vérifiés exécutablement** ; **manque non dit** : l'effet `1316` n'est pas dans `EFFECT_CLASSES` | `porteur` | `porteur` |

---

## 7. Ce qui n'est PAS couvert

* **La face DÉCISION de `WayOfTheShortBlade`** : le playbook `WayOfTheShortBladeNonOwnerPlaybook`
  était déjà porté ; la tranche ne l'a pas re-confronté.
* **L'effet `1394`** reste un `BaseEffect` nu (résidu `#419-…-r1c-r1`).
* **L'Operation d'`ApplyInternal`/`RevertInternal` de `1454`** (résidu `#1002-r3`).
* **La confrontation live de `#1002-r1`** : le montage (`--equip-relic` sur un porteur Astra + un
  summon impérial adjacent qui MEURT sans overkill) n'a pas été joué. Le port est confronté sur
  l'ÉTAGE (`ignoreUnitHavingAbility`, garde offline à mutation) mais pas sur l'observable complet.
* **Les arbres non re-lus** (`#1074`, `#1001-r1`, `#521-r4`/1244) : Ghidra servait encore le build
  précédent (`rnca9r7q6c`) pendant toute la tranche — **NON TRANCHÉ, migration de build**.
* **`probe_229` est ROUGE sur `master` avant cette tranche** : trois classes déjà au registre
  (`FiringPositionReactivateOverwatch`, `FiringPositionHitReductionPurge`,
  `BattleFocusEffectTrigger`) n'ont pas d'entrée dans sa table `RAIL`. La classe ajoutée ici, elle,
  est déclarée et passe. Compléter les trois demande de lire leur rail au décompilé.

---

## 8. Re-confirmation des citations après changement de build

Toute la RE de cette tranche a été faite contre `rnca9r7q6c` ; le build est passé à `t6dpr4k06g`
en cours de route. Les citations ont été **re-confirmées PAR NOM** contre le dump frida du nouveau
build (les adresses, elles, ne sont jamais citées) : **24/26 classes** et **27/29 méthodes**
présentes telles quelles, les 2+2 manquantes n'étant **que** les deux corrections de nommage
signalées au §6 (`LifewardsAbility` sans `.Loki`, `Lakrimae_SummonPoxwalker_Ability` avec suffixe).
`UnitFlag.ForceRangedAttack` vaut toujours **21**.
