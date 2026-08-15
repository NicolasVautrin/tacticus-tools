# #10018 — le foyer `effects/factory.py`, quatrieme passe : deux verrous leves par la MEME methode, et un rang de vecteur inverse depuis toujours

Tranche du 2026-08-15, build `t6dpr4k06g`. Les CINQ residus que la 3e passe (#1120) avait
re-mesures sans les porter.

| residu | premisse re-mesuree | verdict | `BLOCAGE` avant -> apres |
|---|---|---|---|
| `#1020-r5` | CONFIRMEE, et le verrou d'appariement est LEVE | **PORTE + confronte live** — ligne fermee | `etage` -> *(ferme)* |
| `#1020-r7` | CONFIRMEE | **PORTE** (registre par `EffectType` LU) — ligne fermee | `etage` -> *(ferme)* |
| `#894-r2` | **BLOCAGE REFUTE** — `seeding` etait un trou de MONTAGE, et il est comble | phase 2 **ECRITE**, cablage refuse (gate d'un autre foyer) | `seeding` -> `aucun` (residu `#894-r7`) |
| `#922-r1` | (b) perime, (a)/(c) tiennent | non resolu — re-mesure seule | `aucun` -> `aucun` |
| `#924-r1` | CONFIRMEE | non resolu — depend de `#924-r2` | `aucun` -> `aucun` |
| `#965-r2` | CONFIRMEE terme a terme | non resolu | `etage` -> `etage` |

Deux verrous que trois passes avaient laisses fermes sont tombes **par la meme methode** : cesser
de chercher la reponse dans les TABLES DE SYMBOLES et aller la lire dans le **code machine** ou
dans la **configuration de la bataille**.

## 1. `#1020-r7` — l'appariement lambda -> `EffectType`, lu dans 103 KB de code machine

`IdunBattle.Entities.Effects.BlockActiveAbilityEffect$$.ctor` a exactement TROIS appelants
(`list_xrefs`), tous des lambdas `EffectsDatabase.<>c$$<InitializeEffects>b__14_{14,165,581}` aux
memes litteraux `(hasAutomaticActivation = 1, includeNormalAttack = 0,
includeMachinePrimaryAbility = 1)`. Deux membres de la famille etaient nommes (`26
Taunted_CantUseAbility`, `1165 Stunned_CantUseAbility`) ; le troisieme ne l'avait jamais ete.

**Pourquoi c'etait bloque** : ces lambdas n'ont **aucune xref de CODE** — `InitializeEffects` ne les
designe que par leur `MethodInfo*`, resolu au runtime. Ni Ghidra ni les tables ne relient donc un
lambda a sa cle.

**Ce qui a marche** : la cle de chaque `Dictionary<EffectType, Func<BaseEffect>>.Add` est un
**immediat**, donc elle est dans le code, en clair. `probe_10018_effectsdatabase_registry.py`
desassemble `InitializeEffects` **depuis le PE** (capstone + pefile, RVA calculee en code) et rend
la sequence des cles. Six controles, et le probe REFUSE de conclure si l'un tombe :

| controle | mesure |
|---|---|
| 1 — cardinal | **607** cles pour **607** lambdas `b__14_N` (indices 0..606, aucun manquant) |
| 2 — temoins | les cles des trois lambdas sont `{26, 1137, 1165}` -> contient les DEUX deja nommes |
| 3 — unicite | 0 cle en double, 0 cle hors de l'enum `EffectType` |
| 4 — regularite | alternance STRICTE cle/delegue sur les 607 inscriptions |
| 5 — ordre declare | 144 inversions / 606 (**informatif** : l'ordre d'inscription n'est PAS celui de l'enum) |
| 6 — classe LUE | 6 lambdas decompiles, classe == nom de la cle 6/6 |

**Le controle 2 suffit a epingler l'alignement** : decale de +1 il rend `{25, 1136, 1162}`, de -1
`{1237, 1138, 1166}` — aucun des deux ne contient `26` ni `1165`.

⇒ **`b__14_165 -> 1137 RapidFire_BlockAbilities`.** Ce n'est plus « le seul candidat plausible ».

⚠ **DEUX pieges rencontres, tous deux du meme genre.** (a) Une premiere tentative voulait deduire
l'`EffectType` de la CLASSE construite par chaque lambda — refutee : les `.ctor` triviaux sont
**ICF-dedupliques**, donc `b__14_1` et `b__14_2` portent le MEME symbole de ctor pour deux classes
distinctes, et `b__14_583` porte `Test_CritDmgModifierEffect$$.ctor` alors que sa cle est
`Stunned_DamageModifier`. (b) Mon propre temoin de controle etait au depart un APPARIEMENT devine
(`b__14_165 -> 1165`) ; il est tombe, et c'est ce qui a rendu la mesure honnete — le controle porte
desormais sur l'**ENSEMBLE** des trois cles, pas sur un couple.

**Effet sur le port.** `engine/battle_query.py::can_use_ability` reconnaissait la famille par le
**SUFFIXE** `_CantUseAbility`, en se declarant « proxy offline du check par CLASSE d'effet, couvre
tout futur membre ». Mesure : le suffixe couvre **2 membres sur 3**. Remplace par le registre
`ACTIVE_ABILITY_BLOCKER_EFFECTS`, qui porte les DEUX booleens du ctor et dont le corps DERIVE les
branches natives d'`UnitExtensions$$IsAbilityBlocked` au lieu de les coder en dur.

## 2. `#1020-r5` — `RapidFire` porte, et le rang des drapeaux de tour etait INVERSE

Les deux arbres, LUS verbatim (build `t6dpr4k06g`) :

```
RapidFireAbility$$CreateTrigger =
      On(0xe = UnitPostAbility, alive = 1) & IsNormalAttack() & get_OwnerIsActor
    & NOT HasFlag(Caster@<DSLSelectors+0x48>, 0x0 = Moved)
    & NOT HasEffect(Caster@<+0x48>, 0x471 = 1137, onlyActive: 0, effectTarget: 6)

RapidFireAbility$$CreateBehaviour =
      ( ResetTurn(Owner@<+0x30>, resetMovement = 0)
      & AddEffect(0x471, get_AbilityStateReference(this), Owner, Owner, turns = <DSLFormulas+0x20> = Direct(1)) )
    & AddFlag(Caster@<+0x48>, 0x0)
```

**Le porteur n'est pas une greffe — la fiche l'annonçait a tort.** Elle prescrivait de greffer
l'ability sur `ultraEliminatorSgt` faute de porteur spawnable. Le recours 4 de `case-92` §5bis
(`--explicit-stats`, chemin de stats NPC) rend le VRAI porteur spawnable **avec ses stats, ses
traits et son arme** : `ultraNpc4HeavyIntercessor`. C'est load-bearing ici, parce que l'unique effet
DAMAGE de cette ability passe par le trait `HeavyWeapon` du caster — precisement ce qu'une greffe
n'aurait pas donne.

**Confrontation live** (`probe_10018_rapid_fire_live.py`, `MC1_67`, seed 777) — le natif publie
lui-meme l'appariement, ce qui est un TEMOIN INDEPENDANT du decompile :

```
effets APRES : [(1008, 0), (1137, 1)]
blocages     : {ability: 1080, blocked: 1, reason: 1137}   <- l'ACTIF est ferme
               {ability:   69, blocked: 0, reason: 1137}   <- l'attaque NORMALE ne l'est pas
TurnFinished : [1, 0]                                      <- pose PUIS reset
plan d'attaque : [69-102] sur 8 tuiles  ->  [54-81] sur 1 tuile
```

Les bornes chutent parce que l'`AddFlag(Moved)` eteint le conjoint `NOT HasFlag(Owner, 0)` de
`HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier`, et les 8 tuiles tombent a 1 pour la meme
raison. C'est tout le canal numerique de cette ability, et il est INDIRECT.

### Le fait de la tranche : `AddFlagsAfterAbilityExecution` etait joue APRES `On(0xe)`

La sequence d'`ActiveAbilityOperation$$ExecuteInternal` est LUE et deja citee dans le port
(`dispatch/ability.py`) :

```
On(0x2a) -> gates -> execution -> On(0xb) -> if (IsActiveAbility) On(0xc)
         -> **AddFlagsAfterAbilityExecution** -> On(0xe)
```

La voie **ABILITY** du port respecte ce rang depuis #120 (`abilities/handler.py` :
`_add_flags_after_execution` PUIS `_post_unit_ability`). La voie **NORMALE** posait ses drapeaux
**apres le retour** d'`after_hit_normal_attack`, donc **apres** `On(0xe)`.

**L'inversion etait silencieuse tant qu'aucun consommateur de `On(0xe)` ne touchait aux drapeaux de
tour.** Elle rend INERTE tout consommateur qui en RETIRE. Mesure, cote port, sur le meme etat :

| | avant correctif | apres |
|---|---|---|
| drapeaux a l'entree du trigger | `[]` (rien a retirer) | `[0,1,2,3,4]` |
| drapeaux RETIRES par `ResetTurn` | `[]` | `[2, 3, 4]` |
| drapeaux finaux | `[0,1,2,3,4]` | `[0, 1]` |
| `ActiveAbilityUsed` final | **True** (unite non re-activable) | **False** |

Le natif, lui, publie `UnitStats_TurnFinished = 1` PUIS `0` sur le meme coup, et rend
`a activer : [77]`.

**`Maugetar_ResetMovementAbility` est le SECOND consommateur touche** : son `ResetMovement` sur
`On(0xe)` etait soumis a la meme inversion. Le correctif le repare aussi — c'est ce qui rend la
correction du rang preferable a un contournement local.

Forme du correctif : `after_hit_normal_attack` prend un callable `avant_post_ability`, appele
exactement entre `On(0xb)` et `On(0xe)`. Le rang reste dans le foyer qui possede la sequence. Les
trois autres call-sites (`behaviours/combat.py`, `operations/summon_ai.py`,
`abilities/loki/mv71.py`) ne posent aucun drapeau et ne passent rien : no-op strict pour eux.

**Non-regression mesuree** : 21/21 (`test_unit_flags_live`, `test_turnflow_live`,
`test_anvil_shield_stun_live`, `test_521_talons_of_the_emperor_live`) puis 38/38
(`test_runner_attack_live`, `test_damage_roll_live`, `test_928_legacy_of_combat_live`,
`test_1006_reliques_aeldari_live`, `test_fuelled_by_fury_live`).

**`1137` n'entre PAS dans `EFFECT_CLASSES`, et c'est lu** : `BlockActiveAbilityEffect$$.ctor`
n'ecrit que deux booleens apres un `BaseEffect$$.ctor` a struct d'options ZEROEE — aucune
magnitude, aucun `ConfigVar`. Ses deux soeurs (26, 1165) sont traitees de meme. Materialiser une
classe sans magnitude serait une instance INERTE (le vice ferme par #462-r4b-r1-r1).

## 3. `#894-r2` — le blocage `seeding` etait un trou de MONTAGE, et il est comble

La fiche imputait le refus `CasterHas3Tiles` a « une variante guild-boss substituee par
`--explicit-stats` ». **Les deux moities sont fausses**, et la seconde est le fait interessant :

* `GuildBoss10Boss1AdmecBelisarius` n'est pas une variante — c'est le **`visualId`**
  d'`admecBossBelisarius` dans le gameconfig. Meme unite, vue par son champ visuel.
* **L'empreinte n'est pas une propriete de l'unite.** Elle vit sur le BOARD :
  `data/boards/global/GB_Belisarius_01.json` porte `IsBossBoard = true` et
  `BossPlatforms = [{Size: 3, Tiles: [(3,7),(2,7),(3,8)], InitialSpawnPosition: true}]`.

`IdunBattle.Operations.SetupGameOperation$$AddBossUnit` est le SEUL chemin qui pose une unite sur
**plusieurs** tuiles (il lit `BC.BossUnit` et la plateforme du board) ; `AddPredefinedUnits` n'en
pose qu'une. Or `BC.BossUnit` vaut `null` dans le seed partage et **le harnais ne l'ecrit nulle
part** — voila le `seeding`.

Forme exacte de `IdunBattle.Configuration.PredefinedBossUnit` (RPC `classFields`, 56 octets) :

```
Id              @0x10  PlayerId
UnitId          @0x18  String
Health          @0x20  Nullable<int>
RemainingHealth @0x28  Nullable<int>
Modifiers       @0x30  List<UnitModifier>
```

**Mesure et contre-epreuve** (`probe_10018r1_bossunit_footprint.py`), meme board, meme unite :

| | `feet` | `abilityReason` du cast 1174 |
|---|---|---|
| sans `BC.BossUnit` (regime d'avant) | **1** | `hex 0x1000000000`, `["CasterHas3Tiles"]` |
| avec `BC.BossUnit` | **3** | `hex 0x1`, `["ValidRequest"]` |

⚠ Le porteur ne doit PAS etre AUSSI dans `--p-units` : il spawnerait deux fois, une instance a 3
tuiles et une a 1.

### Phase 1 et phase 2 confrontees LIVE

Le cast passe et pose `1371 SolarAtomizer_PendingAttack` sur le caster + `1372
SolarAtomizer_PendingTarget` sur **3 tuiles** ; au tour suivant, l'attaque differee rend **3 coups**
`[AUTO:StartTurn]` (9062, 10494, 10598 sur `admecDestroyer`).

### Ce qui est ECRIT, ce qui n'est PAS cable, et pourquoi

L'arbre de phase 2 est porte (`triggers/loki/solar_atomizer_attack.py`,
`TRIGGERED_ABILITY_BEHAVIOURS[1297]`), mirror 1:1 du decompile. Sa **chaine de selecteurs est
confrontee** (`probe_10018r1_solar_atomizer_phase2_live.py`) :

```
tuiles 1372 seedees : 3     EntitiesWithAnyEffect : 3     Units : 1     Enemies : 1
```

exactement les 3 tuiles marquees et l'unique victime du natif.

**Mais `1371` n'entre PAS dans `PENDING_ATTACK_EFFECTS`**, parce que le
`TriggerAbility(Caster(), 1297)` du rail est refuse par son gate `GetAbilityState` :
`notCarrying = [<le boss>]`. DEUX causes, mesurees :

1. le repli kit est keye sur le **`visualId`**, et ici il differe de l'id gameconfig —
   `GC.unit("GuildBoss10Boss1AdmecBelisarius")` rend `None`, donc kit `[]` ;
2. meme avec le bon id, le kit vaut `[1474, 1293]` : `1297` n'y est pas, parce que le port ne
   modelise pas la voie **ACTIVE -> TRIGGERED DERIVEE**
   (`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities[1174] = [1297]`) dans le
   RECENSEMENT du kit. `ACTIVE_ABILITY_TRIGGERS` est un registre de DISPATCH, pas un kit.

Inscrire `1371` avant d'avoir ferme ce gate produirait exactement le vice que
`abilities/loki/instruments_of_vengeance.py` nomme : le `RemoveEffect` du meme arbre **consomme la
marque** (mesure : `removed: 1`) et rien ne frappe — un no-op SILENCIEUX, pire que le manque
visible. L'inscription est donc **ecrite en commentaire, prete**, et le gate est le residu
**#894-r7**.

## 4. Les trois residus re-mesures sans etre resolus

* **`#965-r2`** — premisse CONFIRMEE terme a terme : `hit_index` est absent des DEUX signatures
  (`defender_modifiers`, `attacker_modifiers`), `damage_hits.py` ne porte aucun `bounds_for`, et
  `WhisperingWeb` reste hors d'`EFFECT_CLASSES`. L'etage nomme (recalcul de bornes PAR COUP) n'a pas
  bouge. ⚠ **Fait utile pour la prochaine tranche** : `_run_hits` threade DEJA `hit_index0` et
  calcule l'index continu `hit_index0 + i` a chaque tour de boucle — le point d'accroche existe,
  c'est la RE-DERIVATION des bornes a cet index qui manque, pas l'index.
* **`#924-r1`** — premisse CONFIRMEE (`EarlyWarningOverride_*` toujours hors d'`EFFECT_CLASSES`).
  Dependance a `#924-r2` maintenue : livrer la face DEGAT avant que la magnitude ne soit localisee
  reproduirait le meme sur-degat.
* **`#922-r1`** — volet (b) confirme LIVRE ; restent (a) la decomposition du troisieme etage de
  l'ecart `[462, 1600, 988]` et (c) le balayage du rayon du harnais.

## 5. Validation adversariale

| volet | contre-epreuve | verdict |
|---|---|---|
| `RapidFire` porte | `RapidFire` retire d'`ABILITY_TRIGGERS` -> rien pose, drapeau `Moved` absent | **MORD** |
| famille de blocage | la reconnaissance par SUFFIXE ne voit PAS `1137` (2 membres sur 3) | **MORD** |
| rang des drapeaux | drapeaux retires par le trigger : `[]` avant / `[2,3,4]` apres | **MORD** |
| rail de phase 2 | `1371` hors de `PENDING_ATTACK_EFFECTS` -> 0 declenchement, 0 marque consommee | **MORD** |
| `BC.BossUnit` | temoin sans le champ -> `feet = 1` et `CasterHas3Tiles` | **MORD** |

Garde offline : `tests/engine/runner/test_10018_rapid_fire_offline.py` (9 etages), dont l'etage 8
est la contre-epreuve de la convention de nom et l'etage 9 la condition du repli documente
(`includeMachinePrimaryAbility` vrai pour TOUS les membres — le jour ou un membre ne le porte plus,
le test rougit et la branche machine doit etre separee, residu **#1020-r9**).

## Ce qui n'est PAS couvert

* **La MAGNITUDE de la phase 2 de `SolarAtomizer`** n'est pas confrontee : le rail ne fire pas cote
  port (gate `#894-r7`). Seule sa chaine de SELECTEURS l'est.
* **La face DECISION de `RapidFire`** (playbook) n'a pas ete retouchee — elle etait deja portee et
  confrontee (#419-r1-tr9). Ce qui est neuf est la face COMBAT et le canal de blocage.
* **Le rang corrige des drapeaux** est confronte sur `RapidFire` et non-regresse sur 59 tests live ;
  il n'a PAS ete re-confronte sur `Maugetar`, dont il repare pourtant le `ResetMovement`.
* `#922-r1` (a)/(c), `#924-r1`, `#965-r2` : re-mesures, non resolus.
