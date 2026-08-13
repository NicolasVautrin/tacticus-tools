# #1032 -- `1193 NovaCharge` et `1052 CallRipperSwarms` : deux no-op silencieux fermes

Numero **#1032** alloue par `probe_468_collision_numeros.py --suggere` (reservation exclusive dans
le `.git` commun).

Les deux actives etaient ABSENTES d'`ABILITY_CLASSES` : `ported:False`, 0 degat, 0 effet, aucune
erreur -- la DECISION pouvait les choisir pendant que l'EXECUTION les ignorait.

## 1. Ce que le natif fait, etage par etage

### 1.1 `1193 NovaCharge` (`tauBossRiptide`, NPC boss) -- MARQUAGE, pas attaque

`IdunBattleLogic.Entities.Abilities.Active.Loki.NovaChargeAbility$$ExecuteBehaviour` -- les trois
feuilles, dans l'ordre des deux `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd` :

```
lineTiles = Cache( NovaChargeAbility$$GetLineTiles(), matchAbilityEntities: true )
marked    = NovaChargeAbility$$GetAdditionalMarkedTiles(lineTiles)

pending = DSLBehaviors.AddBondEffect( 0x583 = 1411 NovaCharge_PendingAttack,
                                      AbilityStateReference,
                                      source       = Caster@DSLSelectors+0x48,
                                      targets      = Caster@+0x48,
                                      bondedEntity = Owner@+0x30,
                                      options      = <struct 0x20 octets ZERO> )
markLine = DSLBehaviors.AddEffect( 0x584 = 1412 NovaCharge_PendingTarget_Line,
                                   AbilityStateReference, source = Caster@+0x48,
                                   targets = lineTiles, <options ZERO> )      # surcharge 6-args
markOne  = DSLBehaviors.AddEffect( 0x585 = 1413 NovaCharge_PendingTarget_Single,
                                   AbilityStateReference, source = Caster@+0x48,
                                   targets = marked,    <options ZERO> )      # surcharge 6-args
Execute( (pending & markLine) & markOne )
```

Le degat vient de la PHASE 2 (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.
NovaCharge_AttackAbility$$CreateBehaviour`, `TriggeredAbilityType` 1324), HORS de ce port --
exactement comme `NovaShield` 1194 / `NovaBoost` 1192 (cf. `runner/abilities/tau.py`).

`NovaChargeAbility$$GetLineTiles` (MIRROR) -- trois lignes paralleles issues du caster :

```
center = CenterTiles(CasterTile@DSLSelectors+0x58)
dir    = DSLFormulas.DirectionTo(center, Target@+0x60)               # IVectorFormula
next1  = NextTileInLine(center, dir)
cw     = NextTileClockwise(fromTile = Target@+0x60, aroundTile = center)
dir2   = DSLFormulas.DirectionTo(next1, cw)
next2  = NextTileInLine(cw, dir2)
s      = <TilesBehindInLineSettings : +0x10 = 0, +0x11 = 0>
lines  = ( Target@+0x60 + TilesBehindInLine(Target@+0x60, dir, s, maxAmount: null) )
       + ( cw           + TilesBehindInLine(cw,           dir, s, maxAmount: null) )
       + ( next2        + TilesBehindInLine(next2,        dir, s, maxAmount: null) )
return Filter( lines - CasterTile@+0x58, op_LogicalNot(DSLTriggers.IsTrenchTile(ActiveTarget@+0x68)) )
```

`NovaChargeAbility$$GetAdditionalMarkedTiles(lineTiles)` (MIRROR) :

```
n      = DSLFormulas.ConfigConst(0x11 = nrOfTargets, config@this+0x60)
rest   = Randomize( Filter( (AllTiles@+0x18 - lineTiles) - CasterTile@+0x58,
                            op_LogicalNot(IsTrenchTile(ActiveTarget@+0x68)) ) )
enemies = Enemies( Owner@+0x30, rest, UnitSelectionType 3 )
prio    = Tiles( NormalUnits(enemies, 3) )  +  Tiles(enemies)
        + ( rest & SurroundingTiles( TilesWithEnemies(Owner@+0x30),
                                     includeCenter: true, range: 2, onlyMovable: false ) )
return First( Unique(prio) & rest, amount = n, ignoreForcedTargets: false )
```

### 1.2 `1052 CallRipperSwarms` (`tyranBossHiveTyrantLeviathan`, NPC boss) -- SUMMON EN ATTENTE

`IdunBattleLogic.Entities.Abilities.Active.Loki.CallRipperSwarmsAbility$$ExecuteBehaviour`
(MIRROR 1:1, UNE seule feuille) :

```
n       = AbilityConfiguration.GetNumberConstant(config@this+0x60, 0x10 = nrOfSummons)
enemies = Enemies( Caster@DSLSelectors+0x48, AllAliveUnits@+0x20, UnitSelectionType 3 )
tiles   = First( SortByFormula( CanAddUnit(AllTiles@+0x18),
                                DSLFormulas.AverageDistance(ActiveTarget@+0x68, enemies),
                                ascending: false ),
                 amount = n, ignoreForcedTargets: false )
return Execute( DSLBehaviors.AddBondEffect( 0x446 = 1094 CallRipperSwarms_PendingSummon,
                                            AbilityStateReference,
                                            source       = Caster@+0x48,
                                            targets      = tiles,
                                            bondedEntity = Caster@+0x48,
                                            options      = <struct 0x20 octets ZERO> ) )
```

Le SPAWN reel vit dans `IdunBattle.Entities.Effects.Loki.CallRipperSwarms_PendingSummonEffect`
(deux `DSLFactory.Triggered` : `On(0x15) & IsTurnOf(bonded)` et `On(0x1f) & OwnerIsTargetTile`,
tous deux `-> TriggerAbility(CallRipperSwarms_Spawn*) & GetRemoveEffectBehaviour()`) puis dans
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.CallRipperSwarms_SpawnAbility$$CreateBehaviour`
(`Spawn(..., WithStatsFromConfig, onAppearance = PerformAIAttack(...))`). PHASE 2, HORS de ce port
-- meme decoupe que `TunnelingHorror` 1011 (`runner/abilities/necrons.py`).

## 2. Les deux donnees obligatoires du registre, LUES au decompile

| | `TARGETING_OPTIONS` | `ABILITY_ATTACK_TYPE` |
|---|---|---|
| `1193 NovaCharge` | forme **FLAGS DIRECTS** : `TargetingOptions..ctor(&opts, isSelfCasting: 0, range: TargetingRange.CustomRange(...), forceMeleeTarget: 1, rules: **0x2000000042**, 0, 0)` | `AActiveAbility..ctor(this, &opts, **2**)` = `AbilityAttackType.Others` |
| `1052 CallRipperSwarms` | forme **PRESET STATIQUE COPIE** : aucun `TargetingOptions..ctor` ; recopie des 0x40 octets de `<TargetingOptions statics>+0x280`. `IdunBattle.Core.Services.TargetingOptions$$.cctor` y ecrit `+0x00 = 1` (isSelfCasting), `+0x08` <- `<TargetingRange statics>+0x60`, `+0x20 = 1` (forceMeleeTarget = RangedBool.False), `+0x28 = **0x8004**` | `AActiveAbility..ctor(this, &opts, **2**)` = `AbilityAttackType.Others` |

Decomposition EXHAUSTIVE des masques (aucun bit residuel) :

* `0x2000000042` = `1 << 1` `TargetMatchesDynamicRule` + `1 << 6` `TargetIsTile` + `1 << 37`
  `CasterHas7Tiles` -- ce dernier est la signature du boss `tauBossRiptide`, une unite a 7 tuiles.
* `0x8004` = `1 << 2` `CasterMatchesDynamicRule` + `1 << 15` `CasterIsPossibleTarget`. Le preset
  `<statics>+0x280` est le MEME que celui d'`ExemplarOfTheMontkaAbility` (`runner/abilities/tau.py`,
  masque identique deja LU par une autre tranche) -- confirmation croisee, deux lectures
  independantes du meme bloc du `.cctor`.

## 3. Vocabulaire DSL neuf pose par cette tranche

| Noeud | Mirror natif | Fichier |
|---|---|---|
| `AverageDistance` | `IdunBattleLogic.Entities.DSLFormulas$$AverageDistance` -> `AverageDistanceFormula$$Calculate` -> `BattleQuery$$GetAverageDistance` (slot 112) | `entities/formulas.py` |
| `TilesWithEnemies` | `IdunBattleLogic.Entities.DSLSelectors$$TilesWithEnemies` (= `Tiles(Enemies(of, AllAliveUnits, 3))`) | `entities/selectors/units.py` |
| `CenterTiles` | `IdunBattleLogic.Entities.DSLSelectors$$CenterTiles` -> `CenterTilesSelector$$Select` -> `IBattleQuery` slot 93 `BattleQuery$$GetCenterTiles` | `entities/selectors/geometry.py` |
| `NextTileInLine` | `IdunBattleLogic.Entities.DSLSelectors$$NextTileInLine` (= `TilesBehindInLineSelector` variante `IVectorFormula`, `maxAmount = DSLFormulas+0x20 = Direct(1)`) | `entities/selectors/geometry.py` |
| `NextTileClockwise` | `IdunBattleLogic.Entities.DSLSelectors$$NextTileClockwise` -> `NextTileInCircleSelector$$Select` (+2 crans, `RotationDirection.Clockwise = 0` LU aux octets) | `entities/selectors/geometry.py` |

`PickFirstN` existait DEJA et mirrore `PickFirstNSelector` : c'est lui que le natif construit, pas
le noeud `First` du port -- lequel prend un INDEX qu'aucune surcharge native n'expose (residu
`#1032-r2`).

## 4. Quatre REPARATIONS de noeuds PARTAGES, chacune mesuree avant edition

Aucune n'a ete faite « pendant que j'y suis » : chacune est un maillon que l'un des deux
`ExecuteBehaviour` traverse et que le port coupait EN SILENCE.

| Noeud | Ce que le natif fait | Ce que le port faisait | Rayon de souffle MESURE |
|---|---|---|---|
| `DirectionTo` | `AxialCoordinate$$DirectionTo` NORMALISE le vecteur cube (annulation de la plus petite composante, tie-break `x1,01` sur x, arrondi vers l'exterieur) | `_CUBE_DIRECTIONS.index(delta)` -> `None` des que les deux tuiles ne sont PAS adjacentes | **1** call-site executable (`admec.py` SolarAtomizer), en regime adjacent -> value-preserving |
| `Enemies` | `UnitsByTeamSelector$$CountOrAdd` applique `GetUnitOrMachine` (tuile -> occupant) puis ajoute l'ENTITE SOURCE | filtrait `isinstance(u, dict)` -> `[]` sur tout domaine TUILE | **58** call-sites, **0** avec plus d'un argument positionnel -> le parametre `reference` (pendant exact de celui de `Friends`) est value-preserving |
| `Tiles` | `GetMainTile` est l'IDENTITE sur une tuile (domaine MIXTE, cf. `_entity_pos`) | `_pos` seul -> `[]` sur des ids de tuile | inchange pour un dict (`_entity_pos` y delegue a `_pos`) |
| `Unique` | `Distinct` sur l'identite d'entite | `u.get("id")` INCONDITIONNEL -> `AttributeError` sur un int | idem |

## 5. Ce que cette tranche NE porte PAS

* **La PHASE 2 des deux abilities**, et c'est la meme decoupe que pour `NovaShield` 1194 /
  `NovaBoost` 1192 / `TunnelingHorror` 1011 : `NovaCharge_AttackAbility$$CreateBehaviour`
  (`TriggeredAbilityType` 1324) et le couple `CallRipperSwarms_PendingSummonEffect` +
  `CallRipperSwarms_SpawnAbility$$CreateBehaviour` (1099/1100/1101).
* **Les faces DECISION** -- residu `#1032-r1`, inscrit au registre de dette de
  `probe_1021_face_decision_au_registre` (etat `SANS_VERDICT`, avec la raison qui cite le playbook
  natif et ses methodes). Les deux corps sont LUS et courts ; `NovaChargePlaybook` REUTILISE
  `NovaChargeAbility$$GetLineTiles`, que cette tranche vient de porter.
* **`CasterHas7Tiles`** (bit 37 du masque de 1193) : aucun gate de cardinal d'empreinte n'existe
  cote port -> degradation PERMISSIVE, nommee dans le commentaire de `TARGETING_OPTIONS`.
* **La confrontation LIVE** sur les deux boss npc (`tauBossRiptide`, `tyranBossHiveTyrantLeviathan`)
  -- cf. §7.

## 6. Un ecart LU qui n'etait pas attendu, et qui a REFUTE une hypothese de la tranche

L'hypothese initiale etait : « `direction_to` ne rend une direction que sur les tuiles ALIGNEES,
donc exactement celles que le gate dynamique accepte ». **C'est FAUX**, et c'est le test de garde
qui l'a etabli en rougissant (`test_1032_...::test_etage5_...`).

Mesure : sur les **12** tuiles du ring 2 d'un caster a sept tuiles, `direction_to` en normalise
**10**. Les deux qui rendent vide sont celles dont le delta cube a la forme `(+-2, -+1, -+1)` --
`|dx|` y vaut 2 et les deux autres 1, donc le tie-break ne mord pas (il exige `|nx| == |ny|` ou
`|nx| == |nz|`) et aucune composante n'est strictement minimale. Les QUATRE autres diagonales
(`(-1,2,-1)`, `(-1,-1,2)`, `(1,-2,1)`, `(1,1,-2)`) passent bien par le tie-break et rendent une
arete.

Ce qui reste vrai, et qui est ce que la garde exige, est une **INCLUSION** : les six tuiles que le
gate accepte portent toutes une direction, donc `GetLineTiles` n'est jamais vide sur une cible que
le natif juge legale. Les trois docstrings qui affirmaient l'egalite ont ete corrigees.

## 7. Validation

**Cliquets du registre, rejoues** (derives, pas enumeres) :
`probe_120` etape 0 (registre = **176**, littéral de ctor manquant : **aucun**), `probe_181`
(**176/176** portent leur `TARGETING_OPTIONS`, **0** manquante),
`test_ability_registry_ratchet`, `test_targeting_options_sources`,
`test_996_no_op_silencieuses_offline`, `test_1021_face_decision_au_registre_offline`,
`test_287r12_role_target_tuile_offline` (obligatoire des qu'un port pose `TargetIsTile`),
`test_287r11r1_regles_ciblage_offline`, `test_503r3_registre_trigger_peuple_offline`,
`test_270r1_volet2_dict_keys_enum_offline`, `test_894_routage_ability_par_nom_offline`,
`test_1027_belisarius_actives_offline` (le call-site de `DirectionTo`).

⚠ `test_1021` a d'abord ROUGI, et c'est le cliquet qui a fait son travail : deux entrees neuves
au registre COMBAT sans verdict de face DECISION. Resolu par l'elargissement EXPLICITE du registre
de dette (deux lignes relues) + le residu `#1032-r1`.

**Contre-epreuves ADVERSARIALES** -- chaque garde VUE ROUGE par mutation, message verbatim :

| Mutation | Test qui rougit | Message |
|---|---|---|
| tie-break `x1,01` desarme (`101` -> `100`) | `test_etage5_gate_dynamique_ne_laisse_que_les_tuiles_alignees` | le compte de tuiles normalisantes du ring 2 quitte 10 |
| masque de 1193 ampute de `CasterHas7Tiles` | `test_etage1_les_deux_ids_au_registre_avec_leurs_deux_donnees` | `masque de NovaChargeAbility : 0x2000000042 attendu (LU au decompile), 0x42 pose` |
| un `Spawn` INVENTE au cast de 1052 | `test_etage4_aucun_noeud_d_attaque_ni_de_spawn_dans_les_deux_arbres` | `l'arbre de CallRipperSwarms porte un noeud 'Spawn' : le cast ne frappe PAS et ne spawne PAS` |

**Ce qui n'est PAS couvert** : la confrontation LIVE. Les deux porteurs sont des BOSS npc, montables
par `--explicit-stats` sur leur carte dediee ; `1193` est en outre GREFFABLE (precedent mesure :
`1194 NovaShield` sur `tauCrisis`, `case-92` SS5bis, greffe qui avait trouve un bug de port). La
tranche livre donc un port MIRROR-OFFLINE + gardes, pas un port live-confronte.
