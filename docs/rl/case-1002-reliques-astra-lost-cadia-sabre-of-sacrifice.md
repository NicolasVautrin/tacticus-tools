# Reliques ASTRA MILITARUM : `RelicOfLostCadia` (1459) et `SabreOfSacrifice` (1478)

Build de reference : `rnca9r7q6c`. Les deux abilities sont des `TriggeredAbilityType` de relique,
voie `item` — elles n'entrent NI dans `ABILITY_CLASSES`, NI dans `TARGETING_OPTIONS`, NI dans
`ABILITY_ATTACK_TYPE`. Canal etabli au decompile : `$$CreateTrigger` + `$$CreateBehaviour` sur les
deux ⇒ `RELIC_ABILITY_TRIGGERS`.

## 1. `RelicOfLostCadia` 1459 — DEUX classes natives

Porteurs (pool rank 17) : `astraBullgryn`, `astraOrdnance`, `astraPrimarisPsy`.
i2 : « Friendly surrounding Imperial Summons have Final Vengeance. When the relic bearer is
defeated, summons a Cadian Guardsman in its hex with 5817 Health, 3492 Damage and 1166 Armour. »

### 1.a `RelicOfLostCadiaAbility` — la pose de l'effet

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicOfLostCadiaAbility$$CreateTrigger` :

```
  On(0x4  = UnitAfterMove,        ownerNeedsToBeAlive: 1)
| ( On(0x32 = UnitAdded,          ownerNeedsToBeAlive: 1) & IsAlive(Actor@DSLSelectors+0x40) )
| On(0x3b = UnitBecameTargetable, ownerNeedsToBeAlive: 1)
| On(0x2d = UnitRevived,          ownerNeedsToBeAlive: 1)
| OnOwnerSpecificAbilityInit(this.AbilityType = 0x5b3 = 1459)
```

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicOfLostCadiaAbility$$CreateBehaviour` :

```
If( get_OwnerIsCaster,
    AddEffect( 0x5ae = 1454 EffectType.FinalVengeance_UnitEffect,
               AbilityStateReference,
               source  = Owner@DSLSelectors+0x30,
               targets = IsImperialAndSummon( SurroundingFriends(
                             unit  = Owner@DSLSelectors+0x30,
                             range = <DSLFormulas+0x20> = Direct(1),
                             unique: 1, unitSelectionType: 3) ),
               options = default(Nullable<AddEffectBehaviourOptions>) ),
    If( AreFriends(Owner@+0x30, Caster@+0x48, comparisonType: 0, anyEntity: 0)
        op_BitwiseAnd IsInRange(Owner@+0x30, Caster@+0x48, range = <DSLFormulas+0x20> = Direct(1)),
        AddEffect( 0x5ae, AbilityStateReference, source = Owner@+0x30,
                   targets = IsImperialAndSummon(Caster@+0x48), options = default ),
        null ) )
```

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicOfLostCadiaAbility$$IsImperialAndSummon`
= `UnitsWithTraits(targets, [0x1a = 26 Imperial, 0x2 = 2 Summon], selectionType: 3)`.

### 1.b `RelicOfLostCadiaAbility_SummonUnit` — le spawn a la mort

```
CreateTrigger   = On(0x0 = UnitDeath, ownerNeedsToBeAlive: 0) & get_OwnerIsTarget
CreateBehaviour = Spawn( parentSelector = Owner@DSLSelectors+0x30,
                         tiles = PickRandomly( FreeTilesOrAdjacentFreeTiles( Tiles(Target@+0x60) ),
                                               amount: 1, allowDuplicates: 0,
                                               maxDuplicatesAllowed: 0x7fffffff,
                                               ignoreForcedTargets: 0 ),
                         spawnUnitId = Config.GetStringConstant(0x0),
                         options = SpawnUnitOptions.WithStatsFromConfig(Config, abilityState,
                                                                        null, null) )
```

## 2. `SabreOfSacrifice` 1478 — UNE classe native

Porteur (pool rank 17) : `astraDreir`.
i2 : « When Dreir or Death Riders adjacent to Dreir are charging, their attacks Suppress their
targets for 1 round. After charging and until the start of their next turn, they additionally have
+1018 Armour for each friendly unit that has been defeated this battle. »

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$CreateTrigger` :

```
On(0x9 = Attack, ownerNeedsToBeAlive: 1)
  op_BitwiseAnd IsCharging(Caster@DSLSelectors+0x48, Target@DSLSelectors+0x60)
  op_BitwiseAnd ( get_OwnerIsCaster
                  op_BitwiseOr ( AreEqual(Parent(Caster@+0x48, root: 0), Owner@+0x30)
                                 op_BitwiseAnd IsUnitWithVisualId(Caster@+0x48,
                                                                  Config.GetStringConstant(0x0))
                                 op_BitwiseAnd IsAdjacent(Owner@+0x30, Caster@+0x48,
                                                          selectionType: 3) ) )
```

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$CreateBehaviour` :

```
  AddEffect( 0x429 = 1065 EffectType.Pinned, AbilityStateReference,
             source = Owner@+0x30, targets = Target@+0x60,
             options = default(Nullable<AddEffectBehaviourOptions>) )
op_BitwiseAnd
  AddStaticStatModifierEffect( targets = Caster@+0x48,
                               effectType = 0x5c1 = 1473 SabreOfSacrifice_ExtraArmor,
                               statType   = 0x10 = 16 StatType.FixedArmor,
                               amount     = GetCurrentExtraArmor(abilityState),
                               turns      = TurnsFromRounds(<DSLFormulas+0x20> = Direct(1)),
                               isHidden   = 0 )
```

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$GetCurrentExtraArmor` :

```
Multiply( Count( Filter( AllUnits(),
                           AreFriends(Owner@+0x30, It@+0x68, comparisonType: 0, anyEntity: 0)
                           op_BitwiseAnd HasBeenDefeated(It@+0x68)
                           op_BitwiseAnd IsNormalUnit(It@+0x68) ) ),
          Get( Config.GetVariableForLevel(0x1b = 27 extraArmor, abilityState, null) ) )
```

## 3. Ce que le port ajoute, et ou

| quoi | ou |
|---|---|
| les deux `TriggeredAbility` de `SabreOfSacrifice` | `engine/runner/operations/triggers/loki/sabre_of_sacrifice.py` |
| les deux `TriggeredAbility` de `RelicOfLostCadia` | `engine/runner/operations/triggers/loki/relic_of_lost_cadia.py` |
| inscription (cle = NOM d'ability) | `.../triggers/dispatch/registry.py` -> `RELIC_ABILITY_TRIGGERS` |
| noeuds T `IsNormalUnit` / `HasBeenDefeated` | `engine/entities/triggers.py` (DEPLACES depuis `leading_the_charge.py`) |
| slot `Owner` threade | `engine/runner/abilities/behaviours/context.py` -> `entities_from_state(..., owner_id=)` |
| site `AllUnits` pool-8 declare | `probe_514_allunits_rayon_de_souffle.py` -> `SITES_POOL8` |
| mesure LIVE | `probe_1002_reliques_astra_live.py` (3 bras) |
| garde OFFLINE | `tests/engine/runner/test_1002_reliques_astra_offline.py` (12 tests) |

Ni `ABILITY_CLASSES`, ni `TARGETING_OPTIONS`, ni `ABILITY_ATTACK_TYPE` : les deux sont des
`TriggeredAbilityType`, aucune n'est une active.

### 3.a Trois reparations que la tranche a rendues necessaires

1. **`IsNormalUnit` / `HasBeenDefeated` etaient des helpers PRIVES** de
   `runner/abilities/loki/leading_the_charge.py`. `SabreOfSacrificeAbility$$GetCurrentExtraArmor`
   construit le MEME filtre que `LeadingTheChargeAbility$$GetExtraPierceRatio` (meme heros,
   `astraDreir`) : les deux corps sont **deplaces** au foyer des noeuds T et l'ancien site
   **delegue** (aucun call-site ni patch desarme).
2. **Le slot `Owner` n'etait threade NULLE PART** : `entities_from_state` ne posait pas
   `ctx.owner`, donc `Owner()` retombait TOUJOURS sur `ctx.caster`. C'est exact pour la quasi-
   totalite des triggered-abilities (`Owner == Caster`), mais FAUX pour la branche Death Rider de
   `SabreOfSacrifice`, ou le caster est le summon et l'owner reste Dreir. Parametre `owner_id=`
   ajoute, defaut `None` = comportement inchange pour les ~459 autres appelants.
3. **`IsUnitWithVisualId` comparait deux substrats differents.** Le champ `visualId` du dict
   d'unite porte l'id de CONFIG pour une unite spawnee offline (`astraSmnDeathRider`) et l'id
   VISUEL pour une unite seedee live (`astraNpc5DeathRider`) ; le natif lit TOUJOURS l'id visuel.
   Le noeud resout desormais la forme portee avant de comparer. Rayon de souffle MESURE au moment
   du changement : **0 consommateur EXECUTABLE** (les 4 autres occurrences du depot sont des
   citations de decompile). Le residu etait deja nomme par la docstring d'`UnitsWithIds`.

## 4. Ce que la MESURE LIVE a rendu (2026-08-13, build `rnca9r7q6c`, board `MC1_67`)

`probe_1002_reliques_astra_live.py`, trois bras, tous VERTS **sur le natif** :

| bras | montage | mesure |
|---|---|---|
| `SABRE_CHARGE` | Dreir part d'une tuile NON adjacente, se deplace au contact, attaque ; UN allie normal a ete abattu avant | `Pinned` sur la cible, `SabreOfSacrifice_ExtraArmor` sur Dreir, `fixedArmor` **0 -> 1018** = `extraArmor[10] x 1` |
| `SABRE_SANS_CHARGE` | Dreir DEJA adjacent, n'a pas bouge (`chargedUnitIds` VIDE), attaque | **aucun** des deux effets, `fixedArmor` inchange |
| `CADIA_MORT` | le porteur est abattu | `astraNpc1Guardsman` apparait **dans SON hex**, **dans SON camp**, stats **5817 / 3492 / 1166** |

Les trois stats du Guardsman sont EXACTEMENT `summonHp[10]` / `summonDmg[10]` / `summonArmor[10]`
du gameconfig -- c'est la signature de `WithStatsFromConfig(config, abilityState)` avec
l'`AbilityState` **TERTIAIRE**, pas l'`active_ability_level` du porteur.

### 4.a Quatre pieges de MONTAGE, tous mesures, aucun devine

* **Le regime DEGENERE.** Le premier jet du bras `SABRE_CHARGE` ne faisait mourir personne :
  `Multiply(Count(vaincus) = 0, extraArmor)` rend **0**, l'effet est pose mais ne contribue a rien,
  et `fixedArmor` ne bouge pas. Le bras rendait donc « rien ne se passe » -- ce qu'un port ABSENT
  rendrait aussi. Un allie sacrifiable est desormais abattu AVANT la charge.
* **`--unit-stat X:Health=N` ne suffit pas** : `--hp-player` ecrit `Health` **ET**
  `RemainingHealth`. Ne patcher que le premier laisse l'unite a 900000 PV courants -- 30 coups sans
  la tuer.
* **Il n'existe pas de `kind: "attack"`** : l'attaque normale EST une `ability` dont
  l'`abilityType` est le `NormalAttackType` **per-unit**. Le host REFUSE l'action (et le dit), donc
  aucune mesure n'etait produite.
* **Les effets ne sont PAS a la racine du `decisionView`** mais sous `units[].effects`. Lire la
  racine rend `None` -> liste vide -> « aucun effet », pour toute unite.

## 5. Verdicts, et ce qui n'est PAS couvert

* **`SabreOfSacrifice` 1478 : PORTEE et CONFRONTEE LIVE**, branche `get_OwnerIsCaster`
  (Dreir charge lui-meme), y compris la contre-epreuve du gate `IsCharging`.
  ⚠ La branche **Death Rider** (`Parent(Caster) == Owner & IsUnitWithVisualId & IsAdjacent`) est
  PORTEE et gardee OFFLINE (slot `Owner` distinct), **pas confrontee live** : elle exige de faire
  caster `LeadingTheCharge` puis de faire CHARGER un summon, ce que le harnais n'a pas joue ici.
* **`RelicOfLostCadia` 1459, volet `_SummonUnit` : PORTE et CONFRONTE LIVE** (hex, camp, et les
  trois stats au niveau tertiaire).
* **`RelicOfLostCadia` 1459, volet AURA** (pose de `1454 FinalVengeance_UnitEffect` sur les summons
  imperiaux adjacents) : **PORTE, NON CONFRONTE LIVE** -> residu **`#1002-r2`**.
* **`1454 FinalVengeance_UnitEffect` n'a PAS de classe d'effet** : le port le pose, mais il est
  materialise en `BaseEffect` nu, donc INERTE -> residu **`#1002-r1`**.
* **Porteurs non confrontes de `RelicOfLostCadia`** : `astraBullgryn` et `astraPrimarisPsy`
  (l'ability est UNE, confrontee sur `astraOrdnance`). ⚠ `astraBullgryn` s'est revele
  **non abattable** par le harnais : `applyAction` rend `ok:true, changes:[]` et ses PV ne bougent
  pas, sur 30 coups au contact. Cause non elucidee (trait `BigTarget` ?) ; ce n'est pas un fait sur
  la relique, c'est un fait sur le MONTAGE.
* **Pas de classe d'effet pour `1473 SabreOfSacrifice_ExtraArmor`, et c'est DELIBERE.** La voie
  native est `AddStaticStatModifierEffect`, dont le port applique le stat-mod A LA POSE
  (`apply_change_stat` + `stat_mod_source`/`reverted_stats` poses sur l'instance) : la classe
  d'effet n'est pas le canal. Precedent du MEME heros : `LeadingTheCharge_ExtraPierce` n'est pas
  davantage dans `EFFECT_CLASSES`. La regle « il en faut DEUX » (#1004) vaut pour les effets poses
  par `AddEffect` (patron `DaemonfleshPlate`), pas pour cette voie-la.
