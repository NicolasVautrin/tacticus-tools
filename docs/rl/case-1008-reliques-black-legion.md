# #1008 — Reliques BLACK LEGION : `BookOfFate` (1461) et `Helspear` (1558)

Build `rnca9r7q6c`. Deux `TriggeredAbilityType` de la voie `item`, un seul montage
(`blackPossession` et `blackHaarken` sont tous deux Black Legion et dans le pool rank 17).

| Item | Porteur confronté | Verdict |
|---|---|---|
| `BookOfFate` 1461 | `blackPossession` | **PORTÉ** — arbre DSL 1:1, 24 assertions offline. Les deux porteurs ThousandSons (`thousInfernalMaster`, `thousSorcerer`) **NON CONFRONTÉS**. |
| `Helspear` 1558 | `blackHaarken` | **PORTÉ PARTIEL** — les deux classes natives + l'effet 1583 sont câblés ; **deux résidus nommés** (`#1008-r2` magnitude non branchée, `#1008-r3` conjoint non identifié). |

---

## 1. `BookOfFate` — une cascade de priorité à TROIS étages que l'i2 ne dit pas

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BookOfFateAbility`, une seule classe.

```
CreateTrigger =
    On(0x26 = NormalAttack, alive) & get_OwnerIsCaster & IsAlive(Owner@+0x30)
  & AmountIsGreaterThanZero( UnitsWithTrait(AdjacentFriends(Owner, unique, 3), Summon, 3) )

CreateBehaviour =
    pool = UnitsWithAnyValidTarget( UnitsWithTrait(AdjacentFriends(Owner, unique, 3), Summon, 3) )
    pipe(X) = First(SortByFormula(Cache(Randomize(X)), UnitLevel(ActiveTarget), desc), 1)
    sel  = pipe(UnitsWithId(pool, affectedUnitId)).Otherwise(pipe(UnitsWithTrait(pool, Daemon)))
                                                  .Otherwise(pipe(UnitsWithoutTrait(pool, Daemon)))
    return (AddStaticStatModifierEffect(UnitsWithTrait(sel, Daemon), 1452, Attack, Get(extraDmg),
                                        turns = NULL, isHidden = true)
            & Group(PerformAIAttackFromCurrentPosition(sel), sel, GroupType.Ability_Attack))
           & RemoveEffect(sel, Nullable(1452))
```

Trois choses que **seul le décompilé donne** :

1. **La priorité de cible est un `Otherwise` à trois étages** — le `thousSmnDaemonPrince` nommé par
   `AbilityConstantType.affectedUnitId` d'abord, puis un Daemon quelconque, puis un non-Daemon.
   L'i2 dit « a friendly adjacent Summon », sans ordre.
2. **L'ordre `(buff & attaque) & retrait` est lu au dernier `op_BitwiseAnd`.** Le buff 1452 vit le
   temps d'UN coup. Inverser les deux derniers termes le retirerait avant qu'il ne serve, et l'effet
   ne changerait jamais aucun dégât — dégradation strictement silencieuse.
3. **Le `UnitsWithTrait(sel, Daemon)` du buff n'est pas redondant** avec l'étage B : quand la cascade
   tombe à l'étage C, le filtre rend vide → le summon attaque **sans** buff. C'est le « If the summon
   is a Daemon » de l'i2, et c'est ce qui rend l'étage C observable.

### L'i2 décale d'un palier — ne jamais s'en servir comme oracle de magnitude

`gameconfig.ability_description("BookOfFate", 1)` affiche **928**, alors que `extraDmg[0] = 880`.
L'i2 indexe le tableau par le niveau **brut** ; le natif passe par `Idun.Shared.Level$$ToZeroBasedIndex`.
Figé par `test_book_of_fate_extraDmg_par_palier`.

---

## 2. `Helspear` — deux classes natives, aucune i2

**Aucune description i2 n'existe pour cette relique** (balayage clé ET valeur de `data/i2_en.json` :
seul `items/R_Crit_Helspear/name` répond). Le décompilé est la seule source — donc pas d'i2 sur
laquelle se tromper (contraste #1006), mais pas non plus de garde-fou externe.

```
Helspear_BuffActiveAbility :
  On(9 = Attack, alive) & get_OwnerIsCaster & CurrentAbilityIs(HeraldOfTheApocalypse = 0x3fc)
  -> AddEffect(1583 Helspear_IgnoreArmor, targets = Target@+0x60)
   + AddEffect(1476 DespoiledGround,     targets = Tiles(Target@+0x60))          [op_Addition]

Helspear_ResetActiveAbility :
  On(0x36 = UnitDefeated, alive) & get_OwnerIsActor & NOT IsSteppableUnit(Target)
  & NOT AreFriends(Owner, Target, ByCurrentTeam, false) & NOT TriggeringAbilityIs(0x3fc)
  & <DSLTriggers+0x58>                                        <-- NON IDENTIFIÉ, cf. #1008-r3
  -> AddPersistentData(1558, Owner, "helspear_defeat_count", Direct(1))
   + If(compteur >= ConfigVar(nrOfUnits), ResetActiveAbility(Owner, allowUseless)
                                          + ClearPersistentData(1558, Owner, clé))
```

**L'increment est à GAUCHE** du `op_Addition` final : le seuil porte sur le compteur **déjà
incrémenté** (forme `VolummsMasterArtifice`, l'inverse de `DaemonfleshPlate` qui teste avant
d'incrémenter et compare à `n − 1`). Et le reset **vide la clé** (`ClearPersistentData`) là où
`VolummsMasterArtifice` la remet à 0 (`SetPersistentData`) — deux fabriques natives distinctes.

### Le `1020` a été qualifié par l'ADRESSE, pas par l'ordinal

Le pseudo-C perd le littéral (il part par `edx`). Relu à l'assembleur : `mov edx, 0x3fc` précède un
`call` dont la cible est `IdunBattle.Core.AbilityOrEffect$$op_Implicit` **RVA `166a000`** = la
surcharge `activeAbility: ActiveAbilityType`. Les surcharges `triggeredAbility` (`1669f80`),
`effect` (`166a080`) et `abilityType` (`1669f30`) sont à des RVA différentes.

C'est load-bearing : **1020 est un membre valide de `TriggeredAbilityType` ET d'`EffectType`**, où il
nomme `LivingLightning_MoveEffect`. Une lecture par ordinal aurait écrit le mauvais gate sans lever
la moindre erreur. Figé par `test_le_1020_de_helspear_est_un_ActiveAbilityType_et_pas_un_autre`,
qui **assertionne son propre non-vide**.

---

## 3. Ce que la tranche a trouvé en dehors de son périmètre

### `UnitsWithAnyValidTarget` à UN argument n'était PAS portée, contrairement à ce qui était écrit

`entities/selectors/valid_targets.py` déclarait la surcharge à un argument « DÉJÀ portée, sous un
autre nom », en renvoyant vers `targeting.valid_normal_attack_targets` et le nœud
`ValidNormalAttackTargets`. **Faux** : ces deux-là portent le *prédicat*, pas le *sélecteur*. Ils
rendent **les cibles d'UNE unité** ; `IdunBattle.Entities.Selectors.HasAnyValidTargetSelector`
**filtre un ENSEMBLE d'unités** sur « en a-t-elle au moins une ». Domaines disjoints — l'un rend des
cibles, l'autre des attaquants.

Aucun consommateur ne l'avait révélé jusqu'ici parce qu'aucune ability portée n'appelait cette
surcharge. `BookOfFate` est la première. Mirror ajouté (`HasAnyValidTarget`), prose corrigée.

### `ConfigConstString` ≠ `ConfigConst` — trouvé par le test offline de la tranche

`ability_var(..., is_constant=True)` termine par `int(v)`. Sur `affectedUnitId`
(`"thousSmnDaemonPrince"`), il levait **`ValueError`**. Le natif a deux foyers distincts
(`AbilityConfiguration$$GetNumberConstant` / `$$GetStringConstant`) lus par deux nœuds DSL distincts
(`DSLFormulas$$ConfigConst` / `$$ConfigConstString`) ; le port n'avait que l'axe numérique.
Accesseur `ability_const_str` ajouté ; l'axe numérique **conserve** son `int()` et le dit en
commentaire.

---

## 4. Résidus

| # | Objet | Blocage |
|---|---|---|
| `#1008-r1` | `UnitLevel` n'a pas de substrat — le dict d'unité ne porte pas de niveau. La clé de tri vaut 0 partout ⇒ tri **stable** ⇒ l'ordre reste celui du `Randomize`. Fidèle au régime « tous les niveaux égaux » (une bataille normalisée au même rank), pas au cas général. | `seeding` |
| `#1008-r2` | La magnitude `armorIgnored` de l'effet 1583 **n'atteint pas le calcul**. `get_armor_penetration` (le canal de `IgnoreArmor`) n'est appelé que par `_attacker_effect_bonuses` ; ce porteur-ci est le **DÉFENSEUR**. Côté natif, `CalculateDefenderModifiersForPrediction` appelle les slots `0x19`/`0x1a`/`0x1b` — **aucun n'est `IgnoreArmor`** (`0x19` rend un `Nullable`, `IgnoreArmor` rend un `IAmountFormula`). Le port **expose** la magnitude sans la brancher : un câblage sur le canal attaquant serait un no-op silencieux qui se lirait comme « porté ». | `etage` |
| `#1008-r3` | `<DSLTriggers+0x58>`, sixième conjoint du trigger de reset, **non identifié**. Établi : le slot `DAT_183328470` n'a que 2 xrefs (toutes dans `DSLTriggers$$.ctor`) ⇒ aucun `DSLTriggers$$<X>` nommé ne l'alloue ; le ctor ne lui pose aucun champ ⇒ classe sans état ; il ne reste que **`NoTrigger`** et **`HasActiveAbilityBeenUsedByOwnerAbilityTrigger`** pour `<+0x50>` et `<+0x58>`. **Rien ne dit lequel est lequel.** Le port **omet** le conjoint. Effet mesurable si c'est le gate : le port compterait les kills faits avant le premier usage de l'active, le natif non. | `capteur` |

### Ce qui n'est PAS couvert

* **Aucune confrontation LIVE** : la tranche s'arrête à la validation offline (24 assertions). Le
  montage prévu était `rl_duel build --equip-relic "blackPossession:BookOfFate:3"` +
  `"blackHaarken:Helspear:3"` (niveau 3 = `nrOfUnits` 7, qui **sépare** du palier clampé 4).
* Les deux porteurs ThousandSons de `BookOfFate` (`thousInfernalMaster`, `thousSorcerer`) :
  même classe native, même arbre (le kit du porteur n'entre dans aucun nœud), mais ce n'est pas une
  mesure.
* Le `PerformAIAttack` de `BookOfFate` délègue au corps unique déjà porté (`#338`) : son choix de
  cible n'est pas re-validé ici.

---

## 5. Note d'attribution — homonymie `#1008`

`probe_468 --suggere` a alloué et **réservé** `#1008`. Le numéro entre en homonymie avec la **PR**
#1008 (couple VOTANN), dont la *tâche* est `#1001` : c'est l'angle mort documenté `#468-r8` (`#<n>`
désigne à la fois une tâche et une PR, ce qui rend `git log --grep` ambigu). L'allocateur ne voit
pas les mentions `PR #<n>` des messages de merge. Signalé, pas contourné — on ne recycle pas un trou.
