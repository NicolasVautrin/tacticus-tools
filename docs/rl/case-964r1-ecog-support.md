# #964-r1 — `EcogSupport` (1487) porté et confronté ; `WayOfTheShortBlade` face DÉCISION relue

Build `rnca9r7q6c`. Deux items, deux verdicts de nature différente : le premier est **porté et
confronté live 4/4**, le second est une **relecture** dont le résultat est que le port existant est
juste.

---

## 1. `EcogSupport` — PORTÉ, confronté

`TriggeredAbilityType` **0x5cf = 1487**, passif de `votanIronmaster` « Vynn » (HERO Leagues of
Votann, hors pool → injection catalogue). Face COMBAT, **deux classes natives**.

### 1.1 Les deux corps, relus verbatim

    ...ECogSupport_InitAbility$$CreateTrigger   = OnOwnerSpecificAbilityInit(0x5cf)
    ...ECogSupport_InitAbility$$CreateBehaviour = DSLBehaviors.AddFlag(Owner@+0x30, 0x18)

    ...ECogSupportAbility$$CreateTrigger =
        On(0x30 = 48 UnitRepaired, ownerNeedsToBeAlive: 1)  op_BitwiseAnd  get_OwnerIsCaster

    ...ECogSupportAbility$$CreateBehaviour(abilityState, triggerType) =
        If( AmountIsGreater( ConfigConst(0x3c = maxSummons), Count(AlreadySummonedUnits()) ),
            Spawn( Owner@+0x30, SummonTargetTile(), GetStringConstant(0), 
                   SpawnUnitOptions.WithStatsFromConfig(config, abilityState, 0, 0) ),
            PerformAIAbility( PickRandomly(GetPossibleTriggerRepairSummons(), 1, 0, MaxValue, false),
                              getAbilityType   = <>c.<CreateBehaviour>b__3_0,
                              allowOnlyMove    = 0,
                              overrideMovement = <DSLFormulas+0x18 = Direct(0)>,
                              utilityEntity = 0, customUtility = 0 ) )

    AlreadySummonedUnits()            = UnitsWithId(Children(Owner@+0x30), GetStringConstant(0), 3)
    GetPossibleTriggerRepairSummons() = UnitsWithAnyValidTarget(
                                            UnitsWithId(Children(Owner@+0x30), unitId, 3)
                                              op_BitwiseAnd AdjacentFriends(Caster@+0x48, unique:1, 3),
                                            UnitNormalRepairType(ActiveTarget@+0x68) )
    SummonTargetTile()                = PickRandomly(CanAddUnit(AdjacentTiles(Owner@+0x30)),
                                                     1, 0, int.MaxValue, false)

Gameconfig : `maxSummons = 3`, `unitId = "votanSmnEcog"`.

### 1.2 Les deux sélecteurs « manquants » : UN existait déjà, l'autre non

La fiche d'entrée en nommait deux. La mesure les sépare :

* **`UnitsWithAnyValidTarget`** — le nom est **SURCHARGÉ**, et les deux surcharges allouent des
  classes **différentes** : `UnitsWithAnyValidTarget(units)` → `HasAnyValidTargetSelector` (câble
  l'attaque normale, son `Select` appelle `GetNormalAttackType` lui-même) ;
  `UnitsWithAnyValidTarget(units, ability)` → `UnitsWithAnyValidTargetSelector` (l'ability est un
  paramètre). **La première ÉTAIT déjà portée, sous un autre nom et sous une autre forme** :
  `runner/abilities/targeting.valid_normal_attack_targets` (fonction) et le nœud
  `ValidNormalAttackTargets`. Seule la seconde manquait — c'est elle qu'appelle `EcogSupport`.
* **`UnitNormalRepairType`** — n'existait pas ; son jumeau `UnitNormalAttackType` si.

### 1.3 Cinq lectures qui ne se devinent pas

1. **`If` est ici la surcharge `abilityTrigger`**, pas la surcharge `formula` : `AmountIsGreater`
   rend un `IAbilityTrigger`, il n'y a rien à envelopper. La surcharge `formula` (celle de
   `FuryFromTheDelveAbility$$CreateBehaviour`) ajoute un `AmountIsGreaterThanZero` — recopier le
   voisin écrirait un test `> 0` sur un booléen déjà calculé.
2. **`UnitNormalRepairType` prend `ActiveTarget@+0x68`.** `UnitsWithAnyValidTargetSelector$$Select`
   **ÉCRIT** l'unité courante dans `AbilityEntities+0x20` avant chaque évaluation du sélecteur
   d'ability : c'est ce qui rend le filtre PAR E-COG. Évaluer la formule hors boucle rendrait un
   repair-type constant.
   ⚠ **Le dépôt citait `+0x68` de deux façons contradictoires.** `runner/abilities/admec.py` et
   `triggers/loki/synaptic_linchpin.py` disent `ActiveTarget` — **juste** ;
   `triggers/loki/fury_from_the_delve.py` disait `Current` — **faux**, corrigé ici. Le
   discriminant : `ActiveTargetSelector$$Select` lit `entities+0x20` (repli `+0x10`) et
   `PreviousActiveTargetSelector$$Select` lit `+0x28`. Aucun sélecteur `Current` n'existe, ni au
   natif ni au port.
3. **Le `Func<IEntity,int>` de `PerformAIAbility` n'est PAS l'attaque normale.** C'est
   `...ECogSupportAbility.u003Cu003Ec$$u003CCreateBehaviouru003Eb__3_0`, dont le corps entier est
   `UnitExtensions$$GetRepairType(e)` (`<ActiveAbilityComponent>+0x2c`). Les quatre AUTRES nœuds de
   cette famille cachent leur `Func` dans un `<>c` et il vaut `GetNormalAttackType` (`+0x28`) : le
   port le codait en dur. Sans le threader, l'E-Cog **attaquerait** au lieu de réparer.
4. **`overrideMovement = Direct(0)`, pas `null`** (`DSLFormulas+0x18`). Passé à
   `GenerateActionTiles(maxDistance)`, `0` = la tuile COURANTE seule ; `null` ouvrirait la plage de
   déplacement normale. L'E-Cog répare **sans bouger**.
5. **Le cap compte les enfants VIVANTS ET CIBLABLES** (`3`) : `Children` ne filtre rien, donc sans
   le mode un E-Cog mort tiendrait un slot que le natif a libéré (même piège que `SynapticLinchpin`).

### 1.4 L'émetteur : il N'EXISTAIT PAS, et la fiche disait le contraire

La fiche d'entrée donnait `On(0x30 UnitRepaired)` pour **OUI**, émetteur
`runner/operations/repair.py`. **C'est faux, et c'est le piège « mention vs définition »** : ce
fichier *nommait* le vecteur — dans sa liste de NON-PORTÉS. Aucun `TriggerEvent(UnitRepaired)`
n'existait dans `engine/**`. Inscrire la classe au registre aurait produit un *registered-but-dead*
parfait.

Le vecteur est ajouté (`triggers/dispatch/repair.py`), à sa place native : **après** la mutation
`FillUp` et **après** le gate de sortie anticipée. Le raccourci `Swarm`
(`on_group_unit_hp_changed`) n'est **pas doublé** — le trait n'a pas d'entrée `event_id == 48` dans
`TRAIT_TRIGGERS`, vérifiable d'un grep.

### 1.5 Le volet `_InitAbility` : NON inerte, et c'est ce qui l'a fait porter

La fiche d'entrée rapportait qu'un port du seul `_InitAbility` aurait été un mensonge de
couverture. **La mesure dit l'inverse** : son LECTEUR existait déjà.
`AttackQuery$$EntityCanBeRepaired` porte comme 4ᵉ disjunct
`caster != null && HasFlag(caster, 0x18 CanRepairFullHealthUnits)`, et ce disjunct est **porté**
(`runner/abilities/attack_query.py`). Ce qui manquait était le **POSEUR**, pas le lecteur.

Canal choisi : `ABILITY_INIT_OWNER_FLAGS` (`entities/effects/factory.py`), pendant exact
d'`ABILITY_INIT_OWNER_EFFECTS` — même trigger natif, même boucle
`InitializeActorAbilitiesOperation$$Execute`, seule la mutation diffère.

### 1.6 Le substrat du repair-type : le TRAIT, pas le kit — mode de panne MUET évité

Le jumeau `UnitNormalAttackType` dérive du `visualId` + gameconfig. **Ce raccourci ne marche pas
ici** : `votanSmnEcog` — le seul porteur qui compte — a `activeAbilities = []` et répare quand
même, via son trait `Mechanic`. Une dérivation par kit aurait rendu `None`, donc un filtre
**toujours vide** et un port **muet** : aucune erreur, aucune trace.

La dérivation vit dans `targeting.normal_repair_type_for` (trois voies, dans l'ordre :
`<nom>_Repair`, ability générique du kit, puis trait `Mechanic` → `28 Repair`) ; la formule la
consomme par `ctx.normal_repair_type`. **Confirmé live** : `decisionView` publie `28 Repair` en
`kind: granted` sur Vynn, et le stream du spawn écrit `ChangeAbility e=103 ActiveAbility_Id=28`
sur l'E-Cog.

### 1.7 Confrontation LIVE — 4 étages, 4 OK

`scripts/python/probe_964r1_ecog_support.py`, runner `build#1233`, board `MC1_67`, seed 777,
seed BC augmenté par `catalog_inject.write_augmented_seed_bc(["votanIronmaster"])`.

| étage | mesure | verdict |
|---|---|---|
| 1. MONTAGE | Vynn porte `(28, Repair, granted)` — la voie TRAIT, pas `activeAbilities` | **OK** |
| 2. FLAG **avec TÉMOIN** | deux cibles mécaniques forcées à PV PLEINS ; Vynn cible les deux (`targets` ET `fromHere`), `necroSpyder` — **même trait `Mechanic`, même ability 28, sans `EcogSupport`** — rend `[]`, `abilityReason = TargetIsRepairable` | **OK** |
| 3. SUBSTRAT | `votanSmnEcog` : `activeAbilities = []`, trait `Mechanic` présent → la dérivation par kit seul rendrait `None` | **OK** |
| 4. TRIGGER | `[Ability_Power e=79 «EcogSupport»]` → `AddUnit e=103` (`Unit_Parent_Id=79`, `Unit_IsSummoned=1`), `ActiveAbility_Id=28`, `TriggeredAbility_Id=1514`, `Level=50 mult=180` | **OK** |

⚠ **L'étage 2 ne vaut que par son témoin**, et le probe le dit : une cible acceptée pourrait l'être
parce qu'elle est entamée. Le témoin partage tout avec le porteur sauf `EcogSupport` — c'est
l'unique variable, et il rend `[]`.

⚠ **Deux clés de RPC ont d'abord rendu un faux négatif silencieux** : `abilityTargets` prend
`abilityType` (pas `abilityId`) et ventile `targets`/`fromHere` ; un `applyAction` brut revient
`ok = None` sans muter le runner (même symptôme que #966 étage 5) — la voie écrite est
`rl_duel act ability --state-file`.

### 1.8 Garde offline, et la preuve qu'il MORD

`tests/engine/test_964r1_ecog_support_offline.py` — **30 tests, 7 étages, 4,5 s**, déclencheur
déclaré (`chemins` vide : la cascade dérivée du foyer couvre les 568 modules ; `build: True` pour
le gameconfig).

`scripts/python/probe_964r1_contre_epreuve.py` mute une **copie** de l'arbre et vérifie que le
garde rougit sur les quatre modes de panne silencieux — **4/4 MORDENT** : `Func` d'ability retiré,
sens de l'`If` inversé, `override_movement` à `None`, émetteur retiré.

### 1.9 Ce que ce port n'établit PAS

* **la branche ELSE (`PerformAIAbility`) n'est pas confrontée** : il faudrait 3 E-Cogs déjà posés
  pour fermer le cap. Résidu **#964-r2** ;
* `utilityEntity` / `customUtility` sont nuls au call-site — rien à porter ;
* le second appel natif `processor.<slot 0x51>(target, target, target, 0x1e, ...)` reste
  non porté (aucun consommateur porté ; l'ajouter serait un vecteur mort), et reste nommé dans
  `operations/repair.py`.

---

## 2. `WayOfTheShortBlade` — face DÉCISION relue : **JUSTE**

`WayOfTheShortBladeNonOwnerPlaybook` (`engine/playbook/non_owner_attack.py`, #477-r33) confronté
terme à terme à
`...WayOfTheShortBladeNonOwnerPlaybook.u003CCalculateAttackUtilityInStepsu003Ed__2$$MoveNext` :

    caster = case@+0x10
    if (!HasTrait(caster, 0x10 Hero))                              yield break;
    a = HasFaction(caster, 9 Tau); b = HasRangedWeapon(caster, null);
    c = Query.<slot 0x61 AreEntitiesAdjacent>(case@+0x18, case@+0x20);
    if ((a & (c & b)) == 0)                                        yield break;
    range = GetNumberConstant(playbook@+0x58 -> +0x20, 0x16 = range);
    if (Query.<slot 0x6d GetDistance>(owner@this+0x30, case@+0x18) <= range)
        yield GetUtilityValue(<literal>);

Les six gates sont présents, avec les mêmes constantes (`Hero 0x10`, `Tau 9`, `range 0x16`), la même
comparaison **`<=`**, le même ordre d'arguments de `GetDistance(owner, casterPosition)`, et le
`int.MaxValue` sur ensemble vide correctement reproduit. Le seul écart est l'**ordre d'évaluation**
des trois conjoints (`a & (c & b)` au natif, faction → arme → adjacence au port) : sans effet, ces
prédicats n'ayant pas d'effet de bord.

**Verdict : JUSTE.** Aucune correction.

## 3. `WayOfTheShortBlade` face COMBAT — toujours NON PORTÉE

RE **entièrement re-vérifiée** sur `rnca9r7q6c` (tous les corps relus, pas recopiés de la fiche) ;
elle **confirme** #966 §4, avec deux précisions que la fiche n'avait pas :

* `_InitAbility$$CreateBehaviour` appelle la surcharge d'`AddEffect` à **six** paramètres avec
  `source = targets = Owner@+0x30` pour les DEUX effets (1499 puis 1500), liés par
  `op_BitwiseAnd` ;
* `WayOfTheShortBladeEffect$$CreateTargetSelector` **inline `GetAffectedUnits()` DEUX FOIS** (deux
  constructions séparées de `UnitsWithTrait(SurroundingFriends(Owner, range, unique, 3), Hero, 3)`)
  — équivalent en valeur, mais c'est la forme réelle ; et il porte un `Unique` final que le
  sélecteur du **marqueur** n'a **pas**.

Le reste est conforme à ce que #966 avait consigné : les deux sélecteurs diffèrent d'un seul terme
(`+ Owner` sur le marqueur, pas sur le buff), le buff est une **union**
(`UnitsWithRangedWeapons(...) op_Addition UnitsFromFaction(..., Tau)`), et `IsValidAttackForBonus`
regarde les voisins de la **CIBLE** (`Friends(Owner, AdjacentUnits(Target))`).

**Pourquoi elle n'est pas portée ici** : le canal du port pour un buff d'aura source-side est
`create_aura_attack_damage_bonus_for_ally`, dont le `ctx` fourni par l'agrégateur ne porte **pas**
l'adjacence à la cible — or c'est le 5ᵉ conjoint d'`IsValidAttackForBonus`. Fermer ce canal est une
tranche à soi seule (le `ctx` est partagé par tous les effets de la famille). Le résidu **#966-r4**
reste donc ouvert, avec cette cause désormais **nommée** — ce qu'il ne disait pas.
