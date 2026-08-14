# #1050 — ZONE-GRISE tranchée : `OptimizedGait` PORTÉ, `AncientFury` NON COUVERT

Deux passifs que l'audit `docs/rl/passive-ability-coverage.md` classait « ZONE-GRISE confrontable » :
leur nom apparaissait en code (canal `R`), donc leur couverture était **supposée**, pas mesurée.
Verdict après RE : **le canal qui les nommait n'est pas un câblage de mécanique**, et les deux
étaient dans des états opposés.

## 1. Le canal qui trompait — `CUSTOM_NORMAL_ATTACK_BY_PASSIVE` n'est pas une couverture

Les deux noms ne vivaient que dans `engine/services/custom_normal_attack.py`, la table
{`TriggeredAbilityType` → `ActiveAbilityType`} de
`idun…StaticBattleRules.StaticBattleRules.TriggeredAbility$$.cctor`, que
`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` consulte :

| passif | entrée de la table | ce que ça dit | ce que ça NE dit PAS |
|---|---|---|---|
| `OptimizedGait` 1205 | → `OptimizedGait_NormalAttack` 1123 | quelle attaque normale l'entité MONTE | rien des DEUX triggered du passif |
| `AncientFury` 1256 | → `AncientFury_NormalAttack` 1162 | idem | rien du SÉLECTEUR élargi de cette attaque |

C'est un **dispatch**, pas une mécanique — exactement la divergence que `#1041-r2` a mesurée entre
`audit_passive_ability_coverage.channels()` et `kit_item_voies` (6 passifs vus PORTÉS par le foyer
et ratés par l'audit, tous par ce registre). Le foyer avait raison de dire « quelque chose est
porté » ; l'audit avait raison de dire « ce n'est pas la mécanique ».

## 2. `OptimizedGait` — TROIS classes natives, une seule était portée

    IdunBattleLogic.Entities.Abilities.Active.Loki.OptimizedGait_NormalAttackAbility     -> deja porte
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.OptimizedGait_TriggerAttackAbility -> PORTE ICI
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.OptimizedGaitAbility               -> PORTE ICI

Les deux triggered partagent le **même** `TriggeredAbilityType` (0x4b5 = 1205 ; l'enum n'a qu'un
`OptimizedGait`) — même forme que les trois classes de `StormboyzStrike` sous 1141. Ce partage
n'est pas décoratif : il **arme la seconde branche** du déplacement (§2.2).

### 2.1 `OptimizedGait_TriggerAttackAbility` — l'attaque réactive

    CreateTrigger = On(9 = Attack, ownerNeedsToBeAlive: true)
                  & NOT get_OwnerIsCaster
                  & AreEnemies (Owner@+0x30, Target@+0x60, 0)
                  & IsAdjacent (Owner@+0x30, Target@+0x60, 0)
                  & IsMechanical(Actor@+0x40, 0)
                  & AreFriends (Owner@+0x30, Actor@+0x40, 0, anyEntity: false)

    CreateBehaviour = InformWeapon( Nullable(profile), isMelee, useSpecial )
                    + Attack( Owner, Target,
                              AttackDamage( RandomAmount(GetVariableForLevel(0xc), …(0xd)),
                                            Direct(Nullable(GetDamageProfileOrDefault(0x10))),
                                            Direct(BaseTriggeredAbility$$GetHits()), source, {0} )
                            + ExecuteAdditionalHitsWithDamageProfileType(…, Nullable(0x4e2), true) )

`On(9, true)`, `IsMechanical(…, 0)` et `AreFriends(…, false, 0)` sont **décodés aux octets**
(`mov edx,9` / `mov r8b,1` ; `xor r8d,r8d` ×2 ; `mov byte [rsp+20],0` + `mov qword [rsp+28],0`) —
ghidra perd ces registres au trampoline.

**L'ANCRE des deux lectures d'entité est l'OWNER (`entities+0x18`), pas la cible.** Calcul
d'offset : ghidra déclare `undefined8 local_298[3]; void *pvStack_280;` donc
`pvStack_280 == local_298 + 0x18`, et `local_298` est la copie de l'`AbilityEntities`
(`+0x00 actor · +0x08 caster · +0x10 target · +0x18 owner`). Le second opérande d'`AreUnitsInMelee`
est `local_158 == local_168 + 0x10` = la cible.
⚠ **RECTIFICATION** : `case-419-r1-tr14-r4-r2-inform-weapon-tags.md` §7ter écrivait « ancre sur la
CIBLE » pour ce `HasEffect`-ci. L'écart est **INERTE sur ce porteur** (pour une triggered,
`owner == caster == le porteur`, et c'est ce même porteur que la mesure à 3 bras de
`#419-r1-tr14-r4-r2-r1-r2` a désigné pour l'attaque NORMALE) — mais il changerait tout si un
montage séparait owner et cible.

### 2.2 `OptimizedGaitAbility` — le pas sur l'hex du mort

    CreateTrigger = C & (A | B)
      C = OnDeath(overkill: true, steppable: false)          # = On(0 = UnitDeath) & NOT HasTrait(Target, Steppable)
        & IsAdjacent(Owner, Target, 0) & AreEnemies(Owner, Target, 0)
        & CanMove(Owner) & IsWalkable(Tiles(Target))
      A = NOT get_OwnerIsActor & IsMechanical(Actor, 0) & AreFriends(Owner, Actor, 0, false)
      B = get_OwnerIsActor & TriggeringAbilityIs( AbilityOrEffect(0x4b5 = 1205) )

    CreateBehaviour = MoveUnit( Owner, First(Tiles(Target), 1),
                                options{ +0x10 = <DSLTriggers+0x48> = le trigger TOUJOURS-FAUX } )

`0x4b5` est lu **à l'assembleur** (`mov edx,0x4b5` juste avant `AbilityOrEffect$$op_Implicit`).
⚠ `EventTriggerType.UnitDeath = 0`, PAS `PreUnitDeath_2 = 2` : `DSLTriggers$$OnDeath(a,b)` =
`OnDeathEvent(0, a, b)` — l'écart avec `HeadClaimer`, qui appelle `OnPreDeath2`.

**La branche B se ferme par le canal `killTrigger`, et le port l'avait déjà** : l'attaque réactive
s'exécute sous `CurrentAbility = 1205` (`dispatch/core.py` pose `state.triggering_ability`), la mort
qu'elle cause est enqueuée avec ce `killTrigger`, et `_verify_deaths` le repose sur
`state.trigger_ability_type` (le canal `AbilityEntities+0x98`) le temps du drain — précisément ce
que `TriggeringAbilityIs` lit. Sur le vecteur mort, `+0x60` est publié VIDE (#301) : lire l'autre
canal aurait rendu la branche B morte, en silence.

### 2.3 LE QUIRK — le pas ne consomme PAS le déplacement

Chaîne lue de bout en bout, quatre maillons :

    DSLBehaviors$$MoveUnit(unit, tiles, options)              options+0x10 -> MoveUnitBehaviour+0x70
    MoveUnitBehaviour$$Execute                                v = (+0x70 != null) ? ShouldTrigger : TRUE
                                                              puis MoveUnitOptions+0x11 = v ^ 1
    MoveUnitOperation$$Execute                                if (options+0x11 == 0) SetMovedFlag(unit)

`+0x10` est **le seul des sept sélecteurs d'options dont le défaut est VRAI**. Options nulles (les
29 autres call-sites) → `+0x11 = 0` → `UnitFlag.Moved` **posé**. Ici le trigger rend FAUX
(`<DSLTriggers+0x48> = op_LogicalNot(<+0x40>)`, lu dans `DSLTriggers$$.ctor`) → `+0x11 = 1` →
**`Moved` NON posé**. Côté port : `MoveUnit(set_moved=False)`, paramètre neuf de la feuille DSL
(défaut `True` = strict no-op ailleurs), threadé jusqu'à `MoveUnitOperation`, dont le mirror de
`+0x11` existait déjà.

### 2.4 CONFRONTATION LIVE — `probe_1050_optimized_gait.py`

Montage : `admecRuststalker` (porteur, **lineup et dans le pool**) + `necroWarden` (allié
`Mechanical`, arme **RANGED** portée 3) contre `orksRuntherd`, board `MC1_67`, seed 777 ; positions
DRIVÉES jusqu'à ce que le porteur soit adjacent à l'ennemi et l'allié **hors** adjacence.

| mesure | NATIF | PORT |
|---|---|---|
| déclenchement sur `On(9)` | `[Ability_Power e=79 «OptimizedGait»]` | inscrit + déclenché |
| coups | **2** | **2** |
| profil | `DamageProfileType=16` | `Energy` = **16** |
| source | `Passive_Ability_Type=1205` | `ability_type = 1205` |
| `Attack_Weapon_IsMelee` de la RÉACTION | **1** | `is_melee = True` |
| `Attack_Weapon_IsMelee` du DÉCLENCHEUR | **0** | — |

**Le discriminant est la dernière ligne.** L'attaque déclenchante est RANGED et la réaction est
MELEE : le natif lit `IBattleQuery.<slot 7> AreUnitsInMelee(owner, target)` (la GÉOMÉTRIE
porteur↔cible), pas la nature de l'arme du déclencheur. Un port qui aurait rabattu `is_melee` sur
`ev.ranged` — le réflexe — aurait rendu `0`. Le bras sépare les deux lectures.

⚠ **Les MONTANTS ne sont pas comparés bit-à-bit** sur ce montage, et le probe le dit : le port
rejoue le trigger SEUL sur l'état d'AVANT, le natif le joue APRÈS les coups d'arme du déclencheur —
deux positions différentes dans le même flux MT.
⚠ Trouvé par ce probe, au premier jet : sans `dumpRng`, `execute_ability_attack` **skippe le dégât
et rend `None`** — le port rendait le BON trigger, la BONNE cible… et `attack = null`. Une attaque
qui n'attaque pas, sans erreur (même vice que `probe_1013`).

### 2.5 NON COUVERT par cette tranche

* la face **MOUVEMENT** n'est pas confrontée live : il aurait fallu TUER l'ennemi adjacent au
  porteur (levier `--dmg-target`), et le montage n'a joué que l'attaque. Les gates sont couverts
  offline (les 4 bras d'`(A | B)` + le gate `Steppable`), pas l'exécution.
* `OptimizedGait_NormalAttackAbility$$AttackAmount` / `$$AttackHits` : les deux surchargent la base
  par un `ConditionalAmount(TriggeringAbilityIs(<X>), <bornes de config>, <arme>)`. Le port reste
  sur la voie ARME. Résidu ouvert ci-dessous.
* les 5 porteurs **npc** (`admecBossRuststalker*`) ne sont pas confrontés.

## 3. `AncientFury` — NON COUVERT, et ce n'est PAS la famille du cleave

Le seul artefact natif est
`IdunBattleLogic.Entities.Abilities.Active.Loki.AncientFury_NormalAttackAbility$$GetTarget`
(vslot `0x4a8`). Il n'y a **aucune** `AncientFuryAbility` triggered dans la table de symboles.

    GetTarget = Target@+0x60
              + ConditionalSelector( IsMeleeAttack,
                    AdjacentEnemies(Caster@+0x48, unique, 3) & AdjacentUnits(Target@+0x60, unique, 3),
                    AdjacentUnits(Target@+0x60, unique, 3)
                      & ( SurroundingEnemies(CasterTiles@+0x58, MinDistance(CasterTiles, TargetTiles), unique, 3)
                        - SurroundingEnemies(First(SortByDistance(CasterTiles, Tiles(Target)), 1),
                                             Sum(MinDistance, <DSLFormulas+0x38> = Direct(-1)), unique, 3) ) )

— mot pour mot l'i2 : « Normal **melee** attacks also deal damage to each enemy that is adjacent to
both the target and Galatian. Normal **ranged** attacks also deal damage to each enemy that is both
adjacent to the target and **exactly 2 hexes** away from Galatian » (l'anneau EXACT est la
soustraction `Surrounding(d) − Surrounding(d−1)`, `Direct(-1)` étant la constante partagée
`DSLFormulas+0x38`).

**Ce que ça change, et pourquoi ce n'est pas rangeable dans `NORMAL_ATTACK_CLEAVES`** :

    ALoki_NormalAttackAbility$$ExecuteNormalAttack :
        target = this.vslot(0x4a8)()                       # <- GetTarget, ELARGI ici
        b      = GetAttackDamageBehaviour(…, target)       # -> Attack(caster, target, …)

    AttackBehaviour$$Execute (relu) :
        targets = <sel>.Select(entities).ToList()
        if (targets.Count > 1) targets = targets.OrderBy(b__5_0).ToList()
        foreach t : StartAttack(slot 0x3a) ; <behaviour interne>.Execute(entities{target = t}) ; FinishAttack(0x3b)

⇒ chaque cible reçoit **l'attaque d'ARME COMPLÈTE** (et ses `ExecuteAdditionalHits`), dans l'ordre
**TRIÉ** — la cible primaire n'est pas forcément la première. La famille `#478`
(`$$GetAdditionalTargetsAttackBehavior` : `Fealty`, `TalonOfHorus`, `RighteousRepugnance`,
`Boltstorm`) fait l'inverse : un `Attack` PAR cible additionnelle, aux **bornes de la config du
passif**, APRÈS la primaire, dans l'ordre du SÉLECTEUR. Ranger `AncientFury` là-dedans écrirait les
mauvais montants ET le mauvais ordre RNG — deux écarts silencieux. Cran posé :
`test_1050_optimized_gait_offline.py` étage 4.

**Porteur** : `ultraSmnDreadnought` « Galatian », **summon** (unique porteur). Il s'observe en
spawnant son summoner ; et le passif se **greffe** sur une unité du pool (la cascade lit
`BC.Units[].PassiveAbilities`), voie déjà employée par `probe_419r1tr14r5_r1r4_normal_attack_table`.
Ce n'est donc PAS une limite de confrontabilité — c'est un périmètre de port distinct :
l'exécution multi-cible d'une attaque normale n'existe nulle part côté port et touche
`damage.py` / `damage_ops/normal.py`, la voie de TOUTE attaque normale.

## 3bis. `AncientFury` — PORTÉ (#1050-r1), et le vslot qui masquait le résidu

**La confusion qui tenait ce résidu fermé était une CITATION FAUSSE, pas une difficulté.** Trois
endroits du dépôt écrivaient `$$GetCustomNormalAttackBehaviour @ vslot 0x4a8`. Le fold est `0x4e8`,
appelé DANS `$$GetAttackDamageBehaviour` ; `0x4a8` est `$$GetTarget`, appelé en tête
d'`ExecuteNormalAttack` et passé en **5ᵉ argument**. `AncientFury_NormalAttackAbility$$GetTargets`
— un `return this.vslot(0x4a8)()` nu — apparie le slot à son unique surcharge nommée du build. Lire
le 5ᵉ argument comme un *behaviour* rendait invisible qu'il s'agit d'un **SÉLECTEUR**, donc qu'une
surcharge de `GetTarget` élargit l'attaque normale à N cibles.

**Ce que le port ajoute** (`engine/runner/abilities/loki/ancient_fury.py`) : l'arbre mirror 1:1, le
registre `WIDENED_NORMAL_ATTACKS` (dispatché par le MÊME foyer de cascade que `cleave_for`), et la
queue de la boucle d'`AttackBehaviour$$Execute`. Deux paramètres neufs au vecteur normal, chacun
mirror d'un étage que la boucle native **ne rejoue pas** : `in_attack_loop` (`On(0x2a)` et la
re-résolution de cible vivent dans `ActiveAbilityOperation$$ExecuteInternal` — un cast, une
émission) et `weapon_ref_target_id` (`FindAttackWeapon` est appelé une fois dans `ExecuteBehaviour`
et l'arme est PASSÉE : `$$AttackHits(abilityState, attackWeapon)` = `Direct(attackWeapon+0x20)`).

### CONFRONTATION LIVE — `probe_1050r1_ancient_fury_widened.py`

Montage : greffe d'`AncientFury` sur `necroWarden` (`catalog_inject.write_grafted_seed_bc`, les
DEUX écritures), board `MC1_67`, seed 4463111, régime **MELEE**. `A_IN` et `A_OUT` sont **toutes
deux** adjacentes à la cible ; seule l'ancre CASTER les sépare.

| | `necroDestroyer` (primaire) | `necroSpyder` (A_IN) | `astraCreed` (A_OUT) |
|---|---|---|---|
| NATIF | **1165** | **20** | — |
| PORT | **1165** | **20** | — |
| PORT *sans registre* (témoin) | 1165 | — | — |

Le témoin négatif restaure exactement le port d'AVANT la tranche et **diverge** : l'accord ne vient
pas d'un plan sans cible additionnelle.

### DEUX FAUX ZÉROS, et ce qui les a attrapés

* **`ok: true, mutated: false`.** Au premier plan, `applyAction` réussissait et ne faisait RIEN : un
  seul événement `group 12` (source `AncientFury_NormalAttack`), puis `FindAttackWeapon` rend `null`
  et `ALoki_NormalAttackAbility$$ExecuteBehaviour` no-ope. Un probe qui ne lit que `ok` conclurait
  « le natif n'élargit pas ». Parade : le cast doit être dans `fromHere` d'`abilityTargets`.
* **La cause de ce refus n'était PAS la substitution**, et seul un TÉMOIN pouvait le dire :
  `eldarRanger` (arme ranged portée 3, attaque normale NON substituée, même distance) a un
  `fromHere` **vide lui aussi** ⇒ c'est le PLAN (ligne de tir), pas `AncientFury`. Sans ce témoin, le
  verdict aurait été « l'attaque normale substituée est melee-only » — faux, et invérifiable.

### BUG TROUVÉ EN CHEMIN, hors `AncientFury`

`entities/formulas.py::MinDistance` ne visitait que le domaine UNITE (`isinstance(u, dict)`) alors
que le slot 10 natif (`IdunBattle.DSL.TargetsSelector$$SelectTiles`) est **DOMAINE MIXTE** par
construction (`if (<this est déjà un sélecteur de TUILES>) return sel`). Tout opérande déjà en
domaine TUILE était jeté **en silence** : les deux listes devenaient vides et la formule rendait
`int.MaxValue`. Le call-site qui l'exige est précisément
`MinDistance(CasterTiles@0x58, TargetTiles@0x78)` de `$$GetTarget`. Corrigé au foyer, par délégation
au helper `_select_tiles_positions` qui portait déjà le slot complet ; value-preserving pour le seul
autre call-site exécutable (`IsInUnitAura`, deux sélecteurs d'unités — `probe_293` étape 3 rejoué).

## 4. Résidus ouverts

* **`#1050-r1`** — **RÉSOLU** (§3bis) : `AncientFury_NormalAttackAbility$$GetTarget` est porté,
  confronté live bit-exact avec témoin négatif.
* **`#1076`** — le natif trie la cible PRIMAIRE **avec** les additionnelles ; le port la frappe
  toujours en tête (le préambule d'`ExecuteInternal` n'est pas détachable du premier coup côté
  port). Divergence d'ordre RNG dès qu'un id additionnel est inférieur à celui de la primaire.
* **`#1076-r1`** — la branche RANGED (l'anneau exact) est couverte OFFLINE mais **non confrontée**
  live : aucun plan de `MC1_67` ne laisse de ligne de tir vers une cible à distance 2, et le témoin
  non substitué ne tire pas davantage.
* **face DÉCISION** — `IdunBattle.AI.Playbook.Loki.AncientFury_NormalAttackAbilityPlaybook$$
  MakeDamagePredictions` existe et n'est pas porté : la prédiction de dégât de l'IA ignore les
  cibles additionnelles.
* **`#1050-r2`** — `OptimizedGait_NormalAttackAbility$$AttackAmount` / `$$AttackHits` : le
  `ConditionalAmount(TriggeringAbilityIs(<X>), …)` qui substitue les bornes de config aux dégâts
  d'arme. L'`<X>` reste à décoder à l'assembleur (ghidra perd le registre).
* **`#1050-r3`** — la face MOUVEMENT d'`OptimizedGait` n'est pas confrontée live (il faut tuer
  l'ennemi adjacent : `--dmg-target`).
