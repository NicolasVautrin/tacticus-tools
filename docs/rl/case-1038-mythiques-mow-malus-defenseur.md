# #1038 — `MastersOfManoeuvre` et `ContemptuousDisregard` : deux mythiques de MoW, un malus défenseur chacune, et deux verdicts OPPOSÉS

**Verdict** : `MastersOfManoeuvre` (1508 / effet 1510) est **PORTÉE et CONFRONTÉE LIVE** (trois bras
séparants sur `aiPredict`). `ContemptuousDisregard` (1450 / effet 1443) est **NON PORTÉE** sur sa
face dégât — et le port qui l'inscrivait a été **retiré dans la même tranche**, parce qu'il était
**permissif**.

En passant, cette tranche répare un gisement qui dépasse les deux items : **l'`AbilityState` baké
d'un effet posé par une ability TERTIAIRE SUR AUTRUI** n'était lu par personne.

---

## 1. Ce qui est LU au décompilé (build `rnca9r7q6c`)

### `MastersOfManoeuvreAbility` — `TriggeredAbilityType` 0x5e4 = **1508**

`frida/classes.tsv` : parent `IdunBattle.Entities.Abilities.BaseTriggeredAbility`, et la classe
DÉCLARE ses deux méthodes.

```
$$CreateBehaviour = DSLBehaviors.AddEffect(
        EffectType.MastersOfManoeuvre = 0x5e6 = 1510,
        get_AbilityStateReference(this),
        source  = Owner@<DSLSelectors+0x30>,
        targets = Actor@<DSLSelectors+0x40>,          <- l'ACTEUR, pas l'Owner
        turns   = TurnsFromRounds( GetNumberConstant(AbilityConstantType.nrOfRounds = 0x45) ) )

$$CreateTrigger = op_BitwiseOr( <A>, <B> ), avec
    COMMUN = AreFriends( Actor@<+0x40>, Owner@<+0x30>, 0, false )
           & HasRarity( Actor@<+0x40>, idun.meta.Rarity.Mythic = 5 )
           & op_LogicalNot( HasEffect( Actor@<+0x40>, 0x5e6, null, 6 ) )
    <A> = On( EventTriggerType.UnitAfterMove = 4, alive ) & COMMUN
          & AmountIsEqualOrGreater( TilesMovedThisTurn(Actor@<+0x40>),
                                    Get(GetNumberConstant(AbilityConstantType.tilesTraversed = 0x88)) )
    <B> = On( EventTriggerType.UnitFinishedTurn = 0x28, alive ) & COMMUN
          & AmountIsGreaterThanZero(
                Filter( AdjacentFriends(Actor@<+0x40>, true, 3),
                        HasRarity(Candidate@<+0x68>, 5) & HasFaction(Candidate@<+0x68>, 0xa, 3) ) )
```

`IdunBattle.Entities.Effects.Loki.MastersOfManoeuvreEffect` (parent `BaseEffect`), **une seule**
face propre :

```
$$CreateEffectDamageMalusForDefense = EffectBonus.ForPercentDecrease(
        get_OwnerIsTarget & IsRangedAttack(),
        ConfigVar( AbilityVariableType.dmgReductionPct = 0x46, GetAbilityState(this), config@+0x60 ) )
```

⚠ **AUCUN gate de rareté sur l'EFFET.** Toute la rareté vit dans le trigger de POSE. C'est
exactement ce qui rend la face dégât portable alors que la face pose ne l'est pas.

⚠ **Les ordinaux sont qualifiés par leur TYPE DÉCLARÉ, pas par leur valeur.** `frida/methods.tsv` :
`DSLTriggers.HasRarity(actor: ITargetsSelector, rarity: **idun.meta.Rarity**)` — pas
`IdunMetaLogic.UserProgress.Model.UnitRarity`, qui existe aussi avec les mêmes membres. Idem
`0x45`/`0x88`, qui sont des `AbilityConstantType` (`nrOfRounds`/`tilesTraversed`) là où
`AbilityVariableType` 69/136 nomment `summonArmor_2`/`spawnArmor_5`.
⚠ Et **`case-999` affirmait qu'aucun enum `UnitRarity` n'existait dans
`data/symbols/<build>/frida/enums.tsv`** : re-mesuré, il y en a **quatre** (`UnitRarity`,
`ItemRarity`, `UpgradeRarity`, `XpBookRarity`) plus `idun.meta.Rarity` — c'est ce dernier que le
type déclaré désigne.

### `ContemptuousDisregardAbility` — `TriggeredAbilityType` 0x5aa = **1450**

`frida/classes.tsv` : parent `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`, et la
classe n'override QUE `$$GetEffectType`, corps entier `return 0x5a3` (= 1443
`EffectType.ContemptuousDisregard_DamageReduction`). Le reste vient de la base : owner-effect
PERMANENT posé à l'init, patron `Vitarus` / `NornCrown` / `MoreGitzOverEre`.

`IdunBattle.Entities.Effects.Loki.ContemptuousDisregard_DamageReductionEffect` (parent
`BaseEffect`), **DEUX** faces propres :

```
$$CreateEffectDamageMalusForDefense (corps INLINE) =
        EffectBonus.ForPercentDecrease( get_OwnerIsTarget,          <- SEUL noeud
                                        ConfigVar(0x46 = dmgReductionPct) )

$$CreateTargetSelector = DSLSelectors.Filter(
        DSLSelectors.UnitsWithRarity( DSLSelectors.Friends(Owner@<+0x30>, AllUnits(), 3),
                                      idun.meta.Rarity.Mythic = 5, 3 ),
        DSLTriggers.HasTileStatusEffect( DSLSelectors.Tiles(<DSLSelectors+0x68>) ) )
```

#### Le `ForPercentDecrease` inline se lit à la CONSTRUCTION, pas au nom

Le corps de `ContemptuousDisregard` n'appelle aucune fabrique : il construit la struct à la main.
Ce qui tranche, c'est que la construction est **identique bit pour bit** à celle de
`IdunBattle.Entities.Effects.EffectBonus$$ForPercentDecrease` — les **mêmes** deux classes globales
(`DAT_183395500` puis `DAT_1833fe9f0`), le premier ctor recevant le littéral `0xffffffff` (= -1), le
second composant `(<ce -1>, <le montant>)`, et le résultat écrit au champ **+0x08**.

Or `...$$ForPercentIncrease` écrit le montant **BRUT** en +0x08, sans rien construire : **le slot
est PARTAGÉ**, et c'est la négation `Multiply(-1, pct)` qui sépare les deux fabriques. Lire
« +0x08 ⇒ PercentIncrease » (comme le font, à juste titre, les commentaires qui listent
`ForAddition@+0x10` / `ForSubtraction@+0x18` / `ForOverride@+0x28`) aurait **inversé le signe**.

---

## 2. Le gisement transverse : l'`AbilityState` BAKÉ d'un effet posé SUR AUTRUI

`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultEffectBuilder(id, abilityState)` COPIE
l'`AbilityStateReference` reçue dans `EffectComponent+0x18`, et
`IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference` relit ce champ **et rien
d'autre** : l'effet ne consulte JAMAIS son porteur. Pour une ability TERTIAIRE, cet état est
`level 1..4 / mult 100` (fabriqué par `UnitFactory$$Build` depuis `config+0xc0
TertiaryAbilityLevel`), là où les passifs de la MÊME unité portent `50 / 180`.

`snapshot._rebake_tertiary_owner_effects` (#1009) portait déjà ce mirror — mais **clé par
PORTEUR**. Un behaviour qui pose sur autrui lui est donc structurellement invisible, et c'est le cas
de `MastersOfManoeuvre` (`targets = Actor`).

**MESURE** (live, `darkaStormSpeeder` + `--equip-mythic ...:MastersOfManoeuvre:1`, board `MC1_67`) :
l'instance captée sur l'ami arrivait avec `ability_level = None` et `mult = 160` — le repli sur le
PORTEUR (`effects_state.baked_ability_state`). `ConfigVar(0x46)` ne trouvait donc **aucun**
`AbilityState`, et la classe rendait `None` : l'effet était **matérialisé et pourtant ENTIÈREMENT
INERTE**.

⇒ `snapshot._rebake_tertiary_posed_effects` — même mirror, balayage par **SOURCE**. Portée stricte :
la source porte une tertiaire **débloquée** (`tertiary_ability_level > 0`) ET le nom de l'effet
figure dans `factory.TERTIARY_ABILITY_POSED_EFFECTS[<cette tertiaire>]`. Un effet homonyme posé par
un passif d'une autre unité n'est jamais touché.

⚠ **Sans le re-bake, le port ne rendait pas « rien » : il rendait `32`.** Mesuré par la mutation
adversariale du cliquet offline — `pct 32 au lieu du palier tertiaire 10` — c'est-à-dire
`dmgReductionPct[palier 4] = 20` × `mult 160 / 100`. L'écart entre le port et le natif était donc
d'un facteur **3,2**, pas d'un arrondi.

---

## 3. La mesure — trois bras natifs SÉPARANTS

`aiPredict` (preview `GetAllPredictions`, **déterministe**, sans RNG). Les trois bras finissent sur
la MÊME tuile (3,3), le tireur `necroWarden` en (3,6) — seuls changent le NOMBRE de tuiles
traversées et le NIVEAU de la mythique. La MoW est montée dans les **trois** (`darkaStormSpeeder`
est hors seed : l'injection catalogue passe par `--equip-mythic`), donc le contre-bras isole le
**gate**, pas la présence de la MoW.

| bras | tuiles traversées | niveau | `healthDmgMin` / `Max` | rapport |
|---|---|---|---|---|
| **B** contre-bras | 1 (< `tilesTraversed` = 2) | 1 | 2890 / 4334 | 1.0000 |
| **A** | 3 | 1 | 2600 / 3900 | **0.8997** |
| **C** | 3 | 4 | 2312 / 3468 | **0.8000** |

`dmgReductionPct = [10, 13, 16, 20]` ⇒ A confirme le palier **1** (10 %), C le palier **4** (20 %),
B confirme le **seuil** `tilesTraversed`. Le port lit `ability_level` 1 puis 4 et rend
`PercentDecrease(10)` puis `(20)`.

⚠ **UN A/B PAR REJEU DE COMBAT NE MESURE RIEN ICI, ET C'EST MESURÉ.** Le premier bras/contre-bras
tenté (rejouer `AttackUnitMessage` côté port avec et sans l'instance, RNG dumpé identique) rendait
`2128` **avec** et `2008` **sans** — une AUGMENTATION. Balayage du pourcentage de 0 à 20 :
`2008, 2162, 2421, 2102, 2208, 1794, 2096, …` — **non monotone**. Le tirage de dégât consomme le
RNG différemment selon les modificateurs (le rejeu est déterministe : trois exécutions rendent trois
fois le même nombre). Seule une preview **sans RNG** sépare les bras.

⚠ **Une MoW n'est PAS dans `decisionView.units`** : elle vit dans `mows[]`, clé `casterId`, et
`pos is null`.

---

## 4. Pourquoi `ContemptuousDisregard` a été RETIRÉE d'`EFFECT_CLASSES`

L'effet 1443 expose un `$$CreateTargetSelector` : c'est un **`EffectWithTarget`**. Or
`IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` itère
`<effet> × <CIBLES de son sélecteur>` — boucle externe sur le couple (effet, liste), boucle interne
sur chaque cible, puis appel des slots **0x1a / 0x1b / 0x19** avec les `AbilityEntities` construites
pour cette cible. **Le porteur de l'instance n'est donc pas le bénéficiaire.**

**MESURE** (live, `blackForgefiend` + `--equip-mythic ...:ContemptuousDisregard:1`, board `MC1_67`,
un ami MYTHIQUE placé sur une tuile `DryBush` portant `LightCover`) : l'instance 1443 est bien posée
**sur la MoW** (`decisionView.mows[].effects`), avec **`targetIds: []`**.

Deux raisons de ne pas l'inscrire, **la seconde suffisant seule** :

1. le gate `UnitsWithRarity(…, Mythic)` lit `GetBaseUnitComponent(e)+0x74`
   (`IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select`, même champ que
   `UnitExtensions$$HasRarity` et `Triggers.HasRarityTrigger$$ShouldTrigger`) — canal **absent** du
   port, même verrou que `#1025-r1` ;
2. l'inscrire sur `create_effect_damage_malus_for_defense` (canal des effets portés par la CIBLE)
   donnerait la réduction **à la MoW elle-même**, que le natif n'en fait **jamais** bénéficier : une
   MoW n'occupe aucune tuile, donc `HasTileStatusEffect(Tiles(elle))` est **FAUX par
   construction**. Ce serait **PERMISSIF**.

Ce qui RESTE porté : `ABILITY_INIT_OWNER_EFFECTS["ContemptuousDisregard"]`, qui matérialise la POSE
(un `BaseEffect` nu, sans face de dégât) — même patron que `MoreGitzOverEre` (#1025), dont l'effet
est lui aussi hors `EFFECT_CLASSES`.

⚠ **Conséquence sur l'audit** : `audit_kit_coverage` compte désormais `ContemptuousDisregard` par le
canal **O** (owner-effect). C'est exact au sens du canal, et **incomplet** au sens du comportement —
c'est dit ici plutôt que laissé à deviner.

`HasTileStatusEffect` n'a pas été creusé au-delà : `TileExtensions$$HasTileStatusEffect` teste
l'appartenance de chaque effet de la tuile à l'`OrderedSet` statique de
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect` (+0x28), lu par
`...$$IsTileStatusEffect`. Le contenu de cet ensemble n'est pas dérivé ici — il ne changerait pas le
verdict, que le gate de rareté suffit à fixer.

---

## 5. Ce qui n'est PAS couvert

- **La face DÉCISION de `MastersOfManoeuvre`** — `IdunBattle.AI.Playbook.Loki.
  MastersOfManoeuvreNonOwnerPlaybook$$CalculateMovementUtilityInSteps` n'est pas portée. Elle est
  l'un des 11 items de `#433-r4-r3-r1-r1`, et son blocage est **le même** `HasRarity` : il n'y a
  rien à arbitrer entre les deux faces.
- **La POSE de `MastersOfManoeuvre`** (les deux vecteurs `<A>`/`<B>` du trigger) : non portée,
  blocage rareté. Sur un runner live le natif pose et le port consomme ; sur un chemin **purement
  offline** l'effet n'apparaît jamais — un MANQUE, jamais un sur-compte.
- **Le vecteur `<B>`** (`On(UnitFinishedTurn)` + un ami Mythic Dark Angels adjacent) n'a pas été
  confronté : le vecteur `<A>` suffisait à poser l'effet, et c'est l'effet que ce port traite. La
  faction `0xa` n'a pas été qualifiée.
- **`ContemptuousDisregard`** : aucune mesure du régime où son sélecteur sélectionne réellement
  quelqu'un (aucun montage n'a produit un `targetIds` non vide).

---

## 6. Résidus

- **`#1038-r1`** — la face dégât de `ContemptuousDisregard_DamageReduction` (1443) : canal AURA
  (`create_aura_defense_damage_malus_for_ally`), gaté `UnitsWithRarity(…, Mythic)` +
  `HasTileStatusEffect`. `BLOCAGE: capteur` (le même que `#1025-r1` : `combatSnapshot.units[].rarity`
  ← `BaseUnitComponent.Rarity @+0x74`). Le contexte du canal aura porte DÉJÀ
  `tile_effects_by_pos` (`tile_status_effects_by_pos`), donc seule la rareté manque.
