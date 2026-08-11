# #916 — `DaemonfleshPlate` : le maximum est `(N-1) x extraArmor`, et le `CreateTrigger` qui l'arme est INVISIBLE des tables

Relique `R_Block_DaemonfleshPlate` — `TriggeredAbilityType` **1493**, **4 porteurs `lineup`**
(`blackTerminator`, `deathBlightlord`, `thousTerminator`, `worldTerminator`), **état 2** (aucun ne
l'équipe au seed : montage écrit par `--equip-relic`).

i2 `Abilities/DaemonfleshPlate_CurrentLevelDescription` : « Each time the relic bearer attacks, it
gains +`extraArmor` Armour. After attacking `nrOfAttacks` times, this bonus is reset and the relic
bearer can use its active ability again. »

---

## 1. Ce que la tranche a trouvé, et qui ne se devinait pas

### 1.1 `DaemonfleshPlateAbility$$CreateTrigger` n'existe dans AUCUNE table — et il existe

Ni `frida/methods.tsv` ni `ghidra/functions.tsv` ne le portent. IL2CPP a **dédupliqué** son corps
avec celui de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateTrigger`
— 112 octets identiques, un seul propriétaire dans la table.

L'appartenance est établie **slot à slot dans le bloc `methodPointers` du PE**. Le groupe de la
classe s'y lit entre deux occurrences du corps partagé
`UnityEngine.Scripting.RequiredByNativeCodeAttribute$$.ctor` — le `.ctor` trivial dédupliqué qui
sert de séparateur de fait — et vaut, dans l'ordre :

```
<sep>  <le corps partagé>  CreateBehaviour  GetLocalizationData  GetCurrentExtraArmor  <sep>
```

soit l'ordre de déclaration que porte aussi `DaemonfleshPlate_ResetActiveAbility` (`CreateTrigger`
puis `CreateBehaviour`, séparés du groupe voisin par le même `.ctor`). Le corps partagé a **trois**
xrefs DATA : une `.pdata` et **deux** entrées de `methodPointers` — une par classe propriétaire.

Conclure « la classe ne définit pas `CreateTrigger` » de son absence des tables aurait été **faux**,
et aurait fait porter l'ability sans son gate — c'est-à-dire permissive.

Valeur lue : `On(9 = EventTriggerType.Attack, ownerNeedsToBeAlive = true) & get_OwnerIsCaster`.

### 1.2 Le seuil est `>= nrOfAttacks - 1`, donc le maximum est `(N-1) x extraArmor`

`...DaemonfleshPlateAbility$$CreateBehaviour`, mirror :

```
counter = GetPersistentData( AbilityOrEffect(DaemonfleshPlate), Owner@DSLSelectors+0x30, Get(<literal>) )
cond    = AmountIsEqualOrGreater( counter, Subtract( ConfigVar(0x4e = nrOfAttacks), DSLFormulas+0x20 ) )
THEN    = ( RemoveEffect( Owner, Nullable(0x5d2 = DaemonfleshPlate_ExtraArmor) )
          & AddEffect( 0x5d3 = DaemonfleshPlate_ResetActive, AbilityStateReference,
                       source = Owner, targets = Owner, options ZERO ) )
          & ClearPersistentData( AbilityOrEffect(DaemonfleshPlate), Owner, Get(<literal>) )
ELSE    = AddStaticStatModifierEffect( targets = Caster@DSLSelectors+0x48,
                                       0x5d2, stat = 0x10 = FixedArmor,
                                       amount = ConfigVar(0x1b = extraArmor), turns = null,
                                       isHidden = false )
          & AddPersistentData( AbilityOrEffect(DaemonfleshPlate), Owner, Get(<literal>),
                               DSLFormulas+0x20 )
return    If( cond, THEN, ELSE )
```

`DSLFormulas+0x20` = `Direct(1)` — LU dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor`
(`+0x18` = 0, **`+0x20` = 1**, `+0x28` = 2, `+0x30` = 100, `+0x38` = -1). C'est le **MÊME nœud** aux
deux emplois : le seuil est `N - 1` et l'incrément est `+1`.

Conséquence, contre-intuitive et mesurée : l'armure culmine à **`(N-1) x extraArmor`** juste avant la
N-ième attaque, jamais à `N x extraArmor`. Confondre `>= N-1` avec `>= N` décale le reset d'une
attaque **et** ajoute une pile — un écart qu'aucun accord agrégé ne montre.

### 1.3 L'effet 1490 EMPILE — et ce verdict est une MESURE, pas une lecture

`AddStaticStatModifierEffect` passe par `IdunBattle.Operations.AddEffectOperation$$Execute`. Sa
branche d'update, `...$$UpdateExistingEffect`, **cherche** une instance à rafraîchir et **saute**
(`continue`) toute instance dont le prédicat de l'`IEffect` (slot 5 de l'interface, appelé juste
après `EffectsDatabase.Get(effectType)`) est vrai ; si aucune n'est retenue elle rend `false` et
l'appelant matérialise une NOUVELLE entité-effet. Le NOM de ce slot 5 n'est pas résoluble
statiquement (valeur runtime derrière la metadata IL2CPP) — donc **le décompilé seul ne ferme pas la
question**.

Deux indices convergents la posaient : `...$$GetCurrentExtraArmor` =
`Multiply(Direct(GetVariableForLevel(0x1b)), GetPersistentData(...))` = `extraArmor x compteur`, et
c'est l'alimentation de l'`extraArmorCurrent` du descriptif d'effet
(`UnitEffects/DaemonfleshPlate_ExtraArmor_Description`). La **mesure live** tranche :

| action | 1 | 2 | 3 | 4 | 5 | 6 | 7 | **8** | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| `fixedArmor` natif (niveau 1) | 145 | 290 | 435 | 580 | 725 | 870 | **1015** | **0** | 145 | 290 |

Côté port, cela s'écrit `stacks_stat_mod_on_add = True` sur la classe d'effet 1490 (patron
`ActOfFaithBuffEffect` / `RealityUnbound_ExtraMaxDamage`). Sans ce drapeau, le gate « déjà-présent »
d'`AddEffectOperation.execute` no-opère toute pose après la première et l'armure plafonne à **un**
cran : `[145, 145, 145, …]`.

### 1.4 Le cast d'une ability OFFENSIVE compte comme une attaque

`On(9)` est l'événement **générique** de fin d'attaque (`IdunBattle.Operations.FinishAttackOperation$$Execute`),
émis pour l'attaque normale **comme** pour une ability. Mesuré : compteur à 2 (armure 290), cast de
`BringerOfDespair` → 3 crans, puis 4, 5, 6, 7, puis reset. Traiter le cast comme « hors série »
décalerait tout l'attendu d'un cran — et ferait lire un port juste comme faux.

C'est aussi ce qui rend le volet reset **observable** : sans un cast qui consomme l'active,
`IdunBattle.Core.Services.BattleQuery$$EntityCanHaveActiveAbilityReset` refuse tout re-armement
(rien à re-armer) et le bras serait un vert vide.

### 1.5 L'effet 1491 est posé ET consommé dans la MÊME action

`...DaemonfleshPlate_ResetActiveAbility$$CreateTrigger` = `On(0x3a = PhaseEnd, true) &
HasEffect(Owner, 0x5d3, onlyActive = false, sourceFlags = 6)` ;
`...$$CreateBehaviour` = `ResetActiveAbility(Owner, allowUseless = true) + RemoveEffect(Owner, Nullable(0x5d3))`.

Une **phase** = un message top-level (`IdunBattle.Messages.InputMessageProcessor$$RunPhase`,
`isInternalPhase: false`) : l'attaque qui pose 1491 est elle-même une phase, donc le `PhaseEnd` qui
le consomme tombe **avant** que quiconque puisse lire l'état. 1491 n'apparaît jamais dans un
`decisionView` pris entre deux actions — il n'est visible que dans les **events** de l'`applyAction`
(deux groupes sur l'entité-effet, la pose et le retrait). L'observable utile est donc l'**état de
l'active**, pas la présence de l'effet.

---

## 2. Ce qui a été confronté live

Probe : `scripts/python/probe_916_daemonflesh_plate_live.py` (**rc = 0**, trois bras).
Cliquet : `scripts/python/tests/engine/runner/test_916_daemonflesh_plate_live.py` (**4 passed**).

Montage : `rl_duel build --equip-relic "<porteur>:DaemonfleshPlate:<niveau>"`, board `MC1_67`,
seed 777, `--hp-player/--hp-target 900000` (ils mettent `Armor`/`FixedArmor` à **0** des deux côtés,
donc `fixedArmor` mesure EXACTEMENT la contribution de la relique), `--crit 0,0`,
`--block-target 0,0`, `--no-ai`.

**Garde de montage** — les trois écritures de #237 échouent deux fois en silence : la garde LIT
`unitAbilityStates.triggered[]` et exige `raw[0] == 1493` **et** `raw[10] == 3` (hiérarchie
TERTIAIRE) **et** le `level` demandé. Mesure du montage : `{"level": 1, "mult": 100, "raw": [1493,
0, 0, 0, 1, 100, 0, 0, 0, 0, **3**, 0]}`.

| bras | `extraArmor` | `nrOfAttacks` | armure natif = port = attendu | active `usable` natif = port |
|---|---|---|---|---|
| NOMINAL (niveau 1) | 145 | 8 | `145 290 435 580 725 870 1015 0 145 290` | `F F F F F F F T T T` |
| NIVEAU6 (niveau 6) | 184 | **7** | `184 368 552 736 920 1104 0 184 368` | `F F F F F F T T T` |
| SPECTATEUR | 145 | 8 | `0 0 0 0 0 0 0 0 0 0` | (canal non armé) |

Le bras **NIVEAU6** n'est pas un doublon : `nrOfAttacks` passe de 8 à 7 au 6ᵉ palier — c'est la seule
variable de la relique qui change de palier. Il discrimine donc **le seuil** *et* **le fait que le
niveau lu est le TERTIAIRE** : un port qui lirait le niveau des PASSIFS (50 sur tout runner
normalisé) rendrait le dernier palier dans les deux bras.

Le bras **SPECTATEUR** (relique sur `worldTerminator`, `blackTerminator` frappe) est le SEUL qui
exerce `get_OwnerIsCaster` : en régime nominal le porteur EST l'attaquant par construction.

### Mutants — sept, tous conformes

| mutant | canal ARMURE | canal ACTIVE | ce qu'il ferme |
|---|---|---|---|
| `SEUIL_N` (`>= N`) | MORD | MORD | le `Subtract(…, Direct(1))` du seuil |
| `NOCLEAR` | MORD | se tait (dérivé) | le `ClearPersistentData` de la branche THEN |
| `INCREMENT_2` | MORD | MORD | le `DSLFormulas+0x20 = Direct(1)` de l'incrément |
| `NOSTACK` | MORD | se tait | `stacks_stat_mod_on_add` (§1.3) |
| `NIVEAU_PASSIF` | MORD | **dérivé** | le couple TERTIAIRE de `triggered_ability_state` |
| `OWNERISCASTER_OFF` | se tait en nominal, **MORD en SPECTATEUR** | se tait | le gate `get_OwnerIsCaster` |
| `RESET_NOGATE` | se tait | MORD | le `HasEffect(Owner, 1491)` du reset |

Deux attentes sont **calculées, pas écrites en dur**, et c'est le point :

* `NOCLEAR` — sans clear, le compteur reste `>= N-1` pour toujours, donc la branche THEN est prise à
  chaque action à partir de la N-ième : l'ACTIVE est re-armée à la N-ième *et le reste*, exactement
  comme en nominal. Ce canal **ne peut pas** distinguer, et le dire est le rôle du mutant.
* `NIVEAU_PASSIF` — le repli passif CLAMPE au dernier palier, donc il ne déplace le reset que si
  `nrOfAttacks[niveau] != nrOfAttacks[-1]` : VRAI au niveau 1 (8 vs 7), **FAUX au niveau 6** (7 vs 7).
  L'écrire en dur ferait rougir le bras NIVEAU6 sur une **dégénérescence du gameconfig**, pas sur un
  défaut du port. L'attente est donc dérivée dans `mutants_pour`.

---

## 3. Face DÉCISION — mesurée, pas supposée

**Aucun artefact natif de décision.** `search_symbols_by_name "Daemonflesh"` rend **5** fonctions,
toutes sous `IdunBattleLogic.Entities.Abilities.Triggered.Loki` ; aucune classe `*Playbook`, aucune
entrée dans `data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv`. Les deux méthodes
restantes (`$$GetCurrentExtraArmor`, `$$GetLocalizationData`) n'ont **aucune xref d'APPEL** — que des
DATA (`.pdata` + `methodPointers`) : elles sont invoquées par slot d'interface depuis la couche VUE
(`extraArmorCurrent` du descriptif d'effet). Rien à porter côté décision.

La contribution de la relique entre néanmoins dans la prédiction par le canal ORDINAIRE : la
`ValueModification` posée sur `FixedArmor` est lue par `GetStat`, comme n'importe quel stat-mod.

---

## 4. Résidus

* **`#916-r1`** — le **slot 5 de l'`IEffect`** que `AddEffectOperation$$UpdateExistingEffect`
  consulte n'est pas NOMMÉ. C'est le prédicat natif qui décide « empiler ou rafraîchir », et il
  gouverne toute la famille `stacks_stat_mod_on_add` (ActOfFaith 1017, RealityUnbound 1207,
  DaemonfleshPlate 1490). Aujourd'hui chacun de ces trois drapeaux est posé par une **mesure live**
  distincte ; le prochain effet empilable repartira de zéro, et un effet qu'on croirait empilable
  sans le mesurer serait faux **en silence** (l'armure plafonne, aucune erreur).
* **la `dataKey`** — le natif la fabrique par `DSLFormulas$$Get(<littéral de chaîne>)`, non résoluble
  statiquement (cache de metadata). Le littéral est PARTAGÉ avec `Dw02AdvancedBurstCannonAbility`
  (xrefs), donc générique. Sans conséquence : le sac est indexé par
  `(GetPersistentDataId(abilityOrEffect), key)` et le port porte la même clé composite.
* **`isHidden = false`** (7ᵉ argument d'`AddStaticStatModifierEffect`) — cosmétique (icône
  d'effet), aucun observable d'état ; la feuille portée ne le modélise pas.

---

## 5. Où c'est

| quoi | fichier |
|---|---|
| arbre DSL + les deux `TriggeredAbility` | `scripts/python/engine/runner/operations/triggers/loki/daemonflesh_plate.py` |
| classe d'effet 1490 (EMPILABLE) | `scripts/python/engine/entities/effects/loki/daemonflesh_plate.py` |
| inscription au registre (5ᵉ chemin, relique équipée) | `scripts/python/engine/runner/operations/triggers/dispatch/registry.py` (`RELIC_ABILITY_TRIGGERS`) |
| inscription de la classe d'effet | `scripts/python/engine/entities/effects/factory.py` |
| probe (montage + attendus, foyer partagé) | `scripts/python/probe_916_daemonflesh_plate_live.py` |
| cliquet | `scripts/python/tests/engine/runner/test_916_daemonflesh_plate_live.py` |
