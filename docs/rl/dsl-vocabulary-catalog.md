# Catalogue exhaustif du vocabulaire DSL Tacticus (build gqfc5mff6c)

RE PURE / READ-ONLY. Source = table de symboles + decompile ghidra-mcp (binaire `/GameAssembly.dll`,
base VA `0x180000000`). Port Python cross-referencé : `scripts/python/engine/dsl/nodes.py` (+ arbres
d'abilities dans `entities/abilities/active_ability.py`).

## 0. Structure du DSL confirmee par decompilation

Le DSL = arbre d'expression LAZY. Chaque `DSLFactory$$X(...)` **construit et retourne un objet-noeud**
(pas d'evaluation immediate) dont le ctor est celui d'une classe de noeud. Les operandes passees a la
factory sont les enfants (sous-arbres). L'evaluation se fait ailleurs (Formula.Calculate / Selector.Select
/ Behaviour.Execute / Trigger).

**4 familles de classes de noeuds** (namespaces natifs, lus via le ctor REEL quand non-mislabele) :

| Famille native | Role | Exemples de ctors REELS observes |
|----------------|------|----------------------------------|
| `IdunBattle.Entities.Formulas.*` | valeur numerique / predicat (lazy `Calculate`) | `ConfigAmount` (ConfigVar @180decac0), `PercentageOf` (@180df8720), `CurrentShieldAmountFormula` (mislabel du ctor de HasTrait @180df14c0) |
| `IdunBattle.Entities.Selectors.*` | ciblage -> list unit/tile (`Select`) | `TilesOnSameElevationSelector.Select @180efa8a0`, `ValidNormalAttackTargetsSelector`, `UnitForcedAttackTargetsSelector` |
| `IdunBattle.Entities.Behaviours.*` | action/mutateur ECS (`Execute`) | `AddEffectBehaviour` (AddEffect @180de6d20), `AttackDamageBehaviour`+`AttackBehaviour` (AttackWithAttackDamage @180de9fb0), `SpawnUnitBehaviour` (Spawn @180dfbd50), `ForeachBehaviour` (mislabel du ctor de If @180df1960) |
| `IdunBattle.Logic.Entities.Triggers.*` | contexte/flow declenche | mislabel : le ctor de Sum/Multiply/Difference @180dfc200/df6d00/dedfe0 s'affiche `HasUsedActiveAbilityThisTurnTrigger.ctor` = en realite le noeud ARITHMETIQUE gshared generique |

### CAVEAT MISLABEL (confirme) - lire la STRUCTURE, jamais le nom du ctor
Preuves lues :
- `Sum @180dfc200` et `Multiply @180df6d00` construisent le MEME type de ctor mislabele
  (`HasUsedActiveAbilityThisTurnTrigger.ctor`) mais depuis DEUX singletons de classe distincts
  (`DAT_183249cf8` pour Sum, `DAT_18325be78` pour Multiply) => 2 classes de noeud numerique differentes,
  meme forme de ctor gshared `(this, childA, childB, 0)`.
- `Difference(a,b) @180dedfe0` = compose 2 noeuds : inner = ctor(child=b, `*(param_1+0xd8)`) puis
  outer = ctor(child=a, inner). Structure = `a + (b * -1)` (const -1 = champ +0xd8 du factory-this).
  => confirme `a - b`, conforme au port.
- `Count @180decfa0` ctor mislabele `thor.Menu.WaitForCondition.ctor` = noeud qui compte un selecteur.
- `Get @180df05d0` ctor mislabele `IceTileEffect<FreezeCoroutine>d__5.ctor` (DAT_183202d40) = noeud
  accesseur generique (meme classe reutilisee par AttackWithAttackDamage pour un sous-noeud).

Le port Python respecte deja ce caveat (docstring nodes.py L10-12).

### Signature d'evaluation
Pas UNE seule `evaluate(ctx)` native : selon la famille, c'est `Formula.Calculate(evalCtx)` (->Fix64/int),
`Selector.Select(evalCtx)` (->list), `Behaviour.Execute(...)` (mutation+events), `Trigger` (flow). Le port
Python les unifie derriere un `Node.evaluate(ctx)` unique typé par retour (int/bool/pos/list) — divergence
de forme ASSUMEE et documentee (nodes.py L14-16), fidele en semantique arbre-lazy.

## 1. Volumetrie de l'enumeration

- `IdunBattleLogic.Entities.DSLFactory$$*` : **~495 methodes** (pagine 0->560, refcount 404 -> 3, traine
  epuisee). C'est le gros du vocabulaire.
- `IdunBattle.DSL.TargetsSelector$$*` : **~30 methodes** (couche ciblage separee, combinateurs d'ensembles).
- Overloads regroupes ci-dessous en **concepts** (un concept = 1 type de noeud, N signatures/VAs).

Refcount = nb de sites d'appel dans le binaire = frequence d'usage reelle a travers toutes les abilities
=> **signal direct de priorite de port**.

---

## 2. CATALOGUE PAR CATEGORIE

Legende PORT : PORTE (dans nodes.py) / PARTIEL (porte inline dans une ability precise, pas generalise) /
MANQUANT (aucun equivalent Python). Le port actuel de `nodes.py` = 24 classes de noeud generiques ;
beaucoup de primitives sont portees "inline" par ability (active_ability.py compose les arbres).

### A. Arithmetique / combinateur numerique

| Concept | VA(s) principales | refcount~ | Semantique | PORT |
|---|---|---|---|---|
| Direct / DirectDamage | 180dee2a0, dee300, dee230, dee1c0, dee0a0 | 404+61+20+20+8 | constante litterale (valeur/damage) | PORTE (`Const`) |
| Sum | 180dfc200 | 100 | a+b (ctor mislabel Trigger) | PORTE (`Sum`) |
| Multiply | 180df6d00 | 112 | a*b | PORTE (`Multiply`) |
| Difference | 180dedfe0 | 27 | a-b = Sum(a,Mul(b,-1)) confirme | PORTE (`Difference`) |
| Min | 180df6930 | 31 | min(a,b) | PORTE (`Min`) |
| Max | 180df62e0 | 16 | max(a,b) | MANQUANT |
| Divide | 180dee5a0 | 14 | a/b | MANQUANT |
| Modulo | 180df69a0 | 16 | a mod b | MANQUANT |
| Negative | 180df7090 | 18 | -a | MANQUANT |
| Half | 180df0840 | 11 | a/2 | MANQUANT |
| Double | 180dee6f0 | 5 | a*2 | MANQUANT |
| PercentageOf | 180df8720, df87a0 | 55+17 | ctor REEL Formulas.PercentageOf = pct*base/100 | MANQUANT |
| Count | 180decfa0 | 85 | cardinal d'un selecteur | MANQUANT (fort refcount) |
| RandomAmount | 180df96a0, df97a0 | 37+14 | tirage aleatoire [min,max] | MANQUANT |
| ConditionalAmount | 180dec5c0, dec4c0, dec640 | 50+15+8 | valeur conditionnelle (if->amount) | MANQUANT (fort refcount) |
| Average / AverageDistance | 180deac90, deac10 | 4+7 | moyenne | MANQUANT |
| IncreasedAmount / IncreasedAmount | 180df1e30 | 3 | amount augmente | MANQUANT |
| AbilityLevelAmount | 180de5d80 | 6 | montant scale par niveau | MANQUANT |
| TurnsFromRounds | 180dfec50, dfecd0 | 108+17 | conversion rounds->turns | MANQUANT (tres fort refcount) |
| StatAmount | 180dfbf60 | 119 | lit une stat d'une unite (Health, etc.) | PARTIEL (inline via OwnerTile/StatAmount@0x160 docs) |

### B. Logique / predicat (retour bool)

| Concept | VA(s) | refcount~ | Semantique | PORT |
|---|---|---|---|---|
| If | 180df1960 (+df1ab0, df18c0, df1b30, df1c30, df19e0, df1bb0) | 266+63+18+6+6+5+3 | branche cond?a:b (ctor mislabel ForeachBehaviour) | PORTE (`If`) |
| AreEqual | 180de9000 (+de9070, de8dc0, de8f20, de8e30) | 84+5+4+4+3 | egalite | MANQUANT |
| AreEquivalent | 180de9120 | 4 | equivalence | MANQUANT |
| AmountIsGreater | 180de8a40 | 41 | a>b | MANQUANT |
| AmountIsGreaterThanZero | 180de88f0, de8960 | 71+69 | a>0 | MANQUANT (fort refcount) |
| AmountIsEqual | 180de8820, de8740 | 37+3 | a==b | MANQUANT |
| AmountIsEqualOrGreater | 180de8660, de86d0 | 29+26 | a>=b | MANQUANT |
| AmountIsZero | 180de8b10, de8b80 | 20+7 | a==0 | MANQUANT |
| AmountIsOdd | 180de8ab0 | 9 | a impair | MANQUANT |
| HasTrait | 180df14c0 | 161 | unite a le trait (ctor mislabel CurrentShieldAmountFormula) | PARTIEL (via `HasFlag`/inline) |
| HasEffect / HasAnyEffect | 180df0fb0, df0b70 | 140+4 | unite a l'effet | MANQUANT (tres fort refcount) |
| HasFlag / DoesNotHaveFlag | 180df10d0, dee680 | 30+3 | flag present/absent | PORTE (`HasFlag`) |
| HasFaction / HasRarity | 180df1050, df1280 | 27+9 | appartenance | MANQUANT |
| IsAlive / Alive | 180df2fa0, de8390 | 63+14 | vivant | PARTIEL (`Damageable` filtre alive) |
| IsDead | 180df3370 | 17 | mort | MANQUANT |
| IsMeleeAttack | 180df43f0, df4300 | 72+6 | attaque de melee | MANQUANT (fort refcount) |
| IsRangedAttack | 180df4d90, df4e90 | 54+6 | attaque a distance | MANQUANT |
| IsNormalAttack | 180df47c0, df4690 | 35+8 | attaque normale | MANQUANT |
| IsOverwatchAttack | 180df4a60, df4980 | 8+3 | attaque d'overwatch | MANQUANT |
| IsAdjacent | 180df2f00 | 46 | adjacence hex | MANQUANT (fort refcount) |
| IsInRange / IsInAttackRange / IsAtRange | 180df3d80, df3c50, df3010 | 15+8+5 | portee | MANQUANT |
| IsCharging | 180df3210 | 18 | en charge | MANQUANT |
| IsMechanical / IsMachine | 180df4230, df41d0 | 9+5 | mecanique | MANQUANT |
| IsUnit / IsHero / IsNormalUnit | 180df5ab0, df3ac0, df47d0 | 18+4+9 | type d'entite | MANQUANT |
| IsTurnOf / IsEnemyTurn | 180df5780, df3840 | 18+4 | proprio du tour | MANQUANT |
| Contains / HasUnit / Any | 180deceb0, df15a0, de8c90 | 12+12+10 | appartenance a un set | MANQUANT |
| CurrentAbilityIs / TriggeringAbilityIs | 180ded1f0, dfe9c0 | 19+36 | identite d'ability courante/declencheuse | MANQUANT (fort refcount) |
| DamageProfileIs / DamageProfileHasTrait | 180dedc40, deda70 | 16+5 | profil de degat | MANQUANT |
| WasCrit / WasBlock / AttackDamageIsCritical | 180e02000, e01fb0, de9590 | 6+5+5 | resultat de hit | MANQUANT |
| HasAdjacentEnemies | 180df0900 | 15 | a des ennemis adjacents | MANQUANT |
| HealthPctIsBelowOrEqual | 180df1830 | 10 | seuil de PV% | MANQUANT |
| (~80 autres predicats Is*/Has*/Can* refcount<=10, longue traine) | ... | <=10 | conditions specialisees (IsWalkable, CanMove, CanUseAbility, IsObscured, IsTrenchTile, ...) | MANQUANT |

### C. Geometrie / selecteur (retour list unit ou tile)

| Concept | VA(s) | refcount~ | Semantique | PORT |
|---|---|---|---|---|
| Enemies | 180deedd0, deee70 | 168+5 | filtre equipe adverse | PORTE (`Enemies`) |
| Friends | 180df0040 | 116 | filtre equipe alliee | MANQUANT (tres fort refcount) |
| Units | 180e01340, e013e0 | 128+10 | tiles->unites dessus | PARTIEL (compose dans SurroundingUnits) |
| Tiles | 180dfdc60 | 118 | unites->leurs tiles | MANQUANT (fort refcount) |
| AdjacentTiles | 180de82a0 | 152 | anneau adjacent (tiles) | PARTIEL (inline) |
| AdjacentUnits | 180de8320 | 117 | unites adjacentes | PARTIEL (`AdjacentEnemies` sous-cas) |
| AdjacentEnemies | 180de80c0, de8030 | 61+13 | ennemis adjacents | PORTE (`AdjacentEnemies`) |
| AdjacentFriends | 180de81d0, de8140 | 69+16 | allies adjacents | MANQUANT (fort refcount) |
| SurroundingTiles | 180dfca70, dfc980 | 40+18 | anneau rayon R (tiles) | PARTIEL (inline via SurroundingUnits) |
| SurroundingUnits | 180dfcb70, dfcbd0 | 21+6 | unites dans rayon R | PORTE (`SurroundingUnits`) |
| SurroundingEnemies | 180dfc570, dfc4a0, dfc300, dfc3d0 | 16+13+7+4 | ennemis dans rayon | MANQUANT |
| SurroundingFriends | 180dfc640, dfc7e0, dfc710, dfc8b0 | 16+9+8+5 | allies dans rayon | MANQUANT |
| AllUnits / AllAliveMachines / NormalUnits | 180de85f0, de8430, df7770 | 26+3+21 | ensembles globaux | MANQUANT |
| Damageable | 180dedd90 | 33 | filtre ciblable vivant | PORTE (`Damageable`) |
| Attackable / Attacker / AttackableEnemies | 180deaa50, deaa70, dea990 | 6+6+4 | filtres attaque | MANQUANT |
| Filter / FilterContinuous / FilterByDirection | 180def870, def7b0, def700 | 75+4+5 | filtre generique par predicat | MANQUANT (fort refcount) |
| First / Last / AtIndex / AtItem | 180defae0, df5f50, de9310 | 128+6+8 | selection ordinale | MANQUANT (tres fort refcount) |
| Unique | 180dfeec0 | 45 | dedup | MANQUANT (fort refcount) |
| Foreach | 180defcd0, defd50 | 40+19 | map sur set | MANQUANT (fort refcount) |
| Nearest / Nearest / MinDistance | 180df6f90, df6820 | 9+17 | plus proche / dist min | MANQUANT |
| SortByDistance | 180dfb020 | 21 | tri par distance | MANQUANT |
| SortByFormula | 180dfb0a0 | 46 | tri par formule DSL | MANQUANT (fort refcount) |
| SortByRow / SortReverse | 180dfb1c0, dfb270 | 8+5 | tri | MANQUANT |
| SortTilesByUtility(+ForSummon) | 180dfb5f0, dfb530, dfb450, dfb3b0 | 15+12+14+5 | tri tiles par utilite | MANQUANT |
| SortUnitsByDamageUtility | 180dfb8f0, dfb820, dfb690 | 11+6+4 | tri unites par utilite degat | MANQUANT |
| SortTargetsByDamagePredictionSelector | 180dfb2e0 | 7 | tri par prediction degat | MANQUANT |
| TilesBehindInLine | 180dfd2d0, dfd380 | 16+13 | tiles derriere en ligne | MANQUANT |
| UnitsDirectlyBehind | 180dff5e0 | 6 | unites derriere la cible | PORTE (`UnitsDirectlyBehind`) |
| TilesAtDistance / TilesAtRow / TilesInPath | 180dfd1b0, dfd250, dfd6b0 | 13+6+8 | geometrie tiles | MANQUANT |
| TilesInDiamondShape/Cone/Triangle/Line | 180dfd570, dfd4d0, dfd750, dfd610 | 8+6+5+5 | formes AoE | MANQUANT |
| TilesOnSameElevation | 180dfd8b0 | 7 | meme elevation | PARTIEL (inline dans UnitsDirectlyBehind via elev_by_pos) |
| Walkable / IsWalkable / MovableTilesInRange | 180e01f30, df5b10, df6a20 | 16+7+11 | tiles marchables | PARTIEL — `Walkable` PORTE ; `MovableTilesInRange` PORTE (#115, feuille DSL -> `WalkPathfinder.GetMovablePositions` ; `canReachOnly=0` => `visited`, `=1` => `stop_set`) + le combinateur `TilesUnitCanMoveToChargeTarget` (= `CanAddUnit(AdjacentTiles(target)) op_And MovableTilesInRange`) |
| Unobscured / UnobscuredTiles / IsObscured | 180e01540, e01480, df48e0 | 21+7+6 | ligne de vue | MANQUANT |
| UnitsWithTrait / UnitsWithoutTrait(s) | 180e00b10, e01040, e010e0, e00bb0 | 90+39+10+6 | filtre par trait | MANQUANT (tres fort refcount) |
| UnitsWithRangedWeapons | 180e00850 | 6 | arme ranged au kit (UnitsWithWeaponsSelector type 2) | PORTE (gates ExplosiveMaladies/Spotter `att_has_ranged_weapon`) |
| UnitsWithRangedAttacks | 180e00610 | 5 | **UNION** {arme ranged} + {TilesOnSameElevationSelector ref porteur, abs(delta elev)<=2 via GetElevationDifference @180ec4ee0} — PAS un filtre arme pur (mesure live probe_66 : melee-only inclus par elevation) | PORTE (`_SpotterReworkedAuraBase._in_ranged_attacks_selector`) |
| UnitsFromFaction/Team/Player | 180dff960, dffad0, dffa30 | 30+13+4 | filtre appartenance | MANQUANT |
| UnitsWithId(s)/VisualId/Rarity | 180e00170, e00230, e00e90, e00900 | 19+7+8+13 | filtre identite | MANQUANT |
| MechanicalUnits / HeroUnits / NormalUnits | 180df66a0, df18a0, df7770 | 15+8+21 | filtres type | MANQUANT |
| CenterTiles / CornerTiles / EdgeTiles | 180deb630, decf20, dee960 | 8+5+4 | tiles de terrain | MANQUANT |
| EmptyTiles / FreeTilesNearUnits / EmptyOrHasSteppableUnit | 180deed60, defdd0, deecf0 | 3+6+6 | tiles libres | MANQUANT |
| (~50 selecteurs specialises refcount<=7) | ... | <=7 | ForcedAttackTargets, TargetableUnits, ValidNormalAttackTargets, SafestTiles, ... | MANQUANT |

### D. Etat / contexte (accesseurs)

| Concept | VA(s) | refcount~ | Semantique | PORT |
|---|---|---|---|---|
| ConfigVar | 180decac0 (+deca30, decc00, decb60, decca0) | 193+80+29+10+8 | ctor REEL Formulas.ConfigAmount = variable de config d'ability | PARTIEL (`ConfigConst` couvre le const, pas la var runtime) |
| ConfigConst / ConfigConstString | 180dec9c0 (+dec8a0, dec800, dec940, dec770) | 164+10+7+7+4 | constante de config | PORTE (`ConfigConst`) |
| Get | 180df05d0 (+df0690, df0630, df04f0, df0560) | 198+102+45+23+6 | accesseur generique (ctor mislabel IceTileEffect...) | PARTIEL (selon usage) |
| Entity / EntityId | 180def540, def470, def4d0 | 124+36+8 | reference d'entite / id | MANQUANT (tres fort refcount) |
| Cache / SetCache | 180deb0d0 (+deb070, deb010), dfa950... | 123+24+6 / 8+7 | memoisation de sous-arbre | MANQUANT (tres fort refcount) |
| Owner* (get_OwnerIsTarget/Caster/Actor/...) | 180e026f0, e02610, e02530, e02760, e02680, e025a0 | 207+186+97+10+5+3 | proprietes de l'owner (booleennes contextuelles) | PARTIEL (`OwnerTile` couvre la position) |
| Caster* (get_CasterIsCasterTile/IsTarget) | 180e02450, e024c0 | 3+3 | proprietes du caster | PARTIEL (`CasterTile`) |
| StatAmount | 180dfbf60 | 119 | lit stat d'entite | PARTIEL (inline) |
| EffectSource / EffectFromOwner / EffectLevel / EffectConfig | 180deeb90, deea50, deead0, dee9e0 | 85+21+27+18 | acces a l'effet courant | MANQUANT (fort refcount) |
| Parent / Children | 180df83c0, debed0 | 27+26 | arbre d'entites | MANQUANT |
| GetPersistentData / SetPersistentData / AddPersistentData | 180df0390(+df0460,df0300), dfac60(+...), de73a0 | 30+8+6 / 9x / 7+7 | data persistante d'ability | MANQUANT |
| TriggeringEffectIs / TriggerBoolNumber | 180dfea90, dfe730 | 10+7 | contexte de trigger | MANQUANT |
| TotalTimesAttacked | 180dfe1c0 | 5 | compteur runtime d'attaques (Formula@180f26620) | PORTE (`TotalTimesAttacked`) |
| TimesRepaired-equivalent (via TimesReceivedAttackedThisTurn, TotalAttacksMade, etc.) | 180dfde60, dfe090 | 8+5 | compteurs runtime | PARTIEL (`TimesRepaired` porte inline) |
| RoundsStarted / UnitTurnsStarted / TotalTurnsFinished | 180dfa6c0, dff280, dfe220 | 11+13+11 | compteurs temporels | MANQUANT |
| CurrentPlayer / CurrentDamage / CurrentHitIndex / CurrentAttackDamageProfile | 180ded610, ded510, ded560, ded3e0 | 11+5+9+3 | etat de l'attaque en cours | MANQUANT |
| Null / Nothing | 180df74f0, df7870 | 23+52 | noeud vide/neutre | MANQUANT (Nothing fort refcount) |
| (~60 accesseurs d'etat refcount<=10) | ... | <=10 | WeaponHighestHits, AttackHits, UnitLevel, LastAttackDamageMade, ... | MANQUANT |

### E. Effet / action / mutateur (Behaviours - retour Behaviour, execute une mutation)

| Concept | VA(s) | refcount~ | Semantique | PORT |
|---|---|---|---|---|
| AddEffect | 180de6d20, de6990, de6bb0, de6e20 | 144+139+90+30 | ctor REEL Behaviours.AddEffectBehaviour | MANQUANT (tres fort refcount) |
| RemoveEffect | 180df9cc0, df9c60 | 115+15 | retire effet | MANQUANT (tres fort refcount) |
| AddEffectOrIncreaseLevel / IncreaseEffectLevel / SetEffectLevel / DecreaseEffectLevel | 180de6860, df1d90(+df1d00), dfaa30, dedf60 | 11+7+7+3 | gestion niveau d'effet | MANQUANT |
| AddBondEffect / AddDynamicStatModifierEffect(ToOwner) / AddStaticStatModifierEffect(+ToOwner) / AddStatOverrideEffect | 180de6340(+de61c0), de6560(+de6670,de6760), de7b20(+de7c60,de79a0,de71d0...), de76b0 | 29+17 / 24+11+11 / 32+26+12+20 / 13 | familles d'ajout de modificateurs | MANQUANT (StaticStatModifier fort refcount cumule) |
| ChangeStat | 180debdc0 | 48 | modifie une stat | MANQUANT (fort refcount) |
| Attack / AttackWithAttackDamage / AttackWithAbilityDamage | 180dea8f0(+dea840), de9fb0(+dea520,dea6b0,dea350,dea180), de9c90(+de9dd0,de9e50,de9c10,de9e10) | 17+4 / 113+29+22+9+4 / 46+18+17+3+3 | ctor REEL Behaviours.AttackBehaviour(+AttackDamageBehaviour) | MANQUANT (tres fort refcount) |
| Heal | 180df1680 | 31 | soigne | MANQUANT (fort refcount) |
| Repair | 180dfa030 | 15 | repare (mecanique) | MANQUANT |
| Kill / KillDeadUnits | 180df5cb0, df5bf0(+df5c60) | 26+9+8 | tue | MANQUANT |
| Spawn / SpawnRandom | 180dfbd50, dfbc60, dfbb10 | 85+10+5 | ctor REEL Behaviours.SpawnUnitBehaviour | MANQUANT (tres fort refcount) |
| MoveUnit / PushUnit / PullUnitOneTile / DisplaceUnit / SwitchPosition | 180df6ae0, df9540, df92b0, dee4f0(+dee440), dfcc30 | 38+9+4+5+3 / 5 | deplacements | MANQUANT (fort refcount) |
| UseActiveAbility / UseNormalAttack(IfAble) / TriggerAbility(Delayed) | 180e015e0(+e016f0), e019f0(+e01870), dfe670(+dfe510) | 19+6 / 8+10 / 18+15 | declenche ability | MANQUANT (fort refcount) |
| Revive / Resurrect | 180dfa4f0, dfa420 | 9+7 | ressuscite | MANQUANT |
| CreateShield / CreateSnapshot | 180ded000, ded0c0 | 11+9 | bouclier / snapshot | MANQUANT |
| AddFlag / RemoveFlag / AddTrait / AddActiveAbility / AddTriggeredAbility | 180de70f0, df9d40, de7e80, de60d0, de7fa0(+de7f00) | 11+4+8+5+4+3 | mutations de composants | MANQUANT |
| ChangeCooldown / ResetActiveAbility / RefreshEffects / ChangeEffectTurns | 180debb90(+debc20), dfa260, df9b20, debd20 | 6+4+9+6+7 | gestion cooldown/effets | MANQUANT |
| PerformAIAttack(FromCurrentPosition)/Ability/Action/Movement | 180df8b60, df8a10, df8860, df8990, df8d30 | 11+27+8+9+5 | actions AI DSL | MANQUANT (fort refcount) |
| (~70 mutateurs specialises refcount<=10) | ... | <=10 | Flee, RotateUnit, Reserve, RemoveUnit, TransferDamage, ... | MANQUANT |

### F. Controle / flow (Triggers + composition)

| Concept | VA(s) | refcount~ | Semantique | PORT |
|---|---|---|---|---|
| On | 180df8010, df80a0, df7f40 | 379+9+4 | attache un behaviour a un evenement | MANQUANT (TRES fort refcount - 2e le plus utilise) |
| Triggered | 180dfe790 | 68 | ability declenchee | MANQUANT (fort refcount) |
| Group | 180df07a0, df0700 | 49+4 | sequence de behaviours | MANQUANT (fort refcount) |
| AtomicGroup | 180de9390, de9490, de9410 | 18+15+5 | groupe atomique (transaction) | MANQUANT |
| PickRandomly | 180df8e70, df8db0 | 84+20 | choix aleatoire pondere | MANQUANT (tres fort refcount) |
| Randomize | 180df9820 | 46 | randomise l'ordre | MANQUANT (fort refcount) |
| Maybe | 180df6610, df6470, df6540, df6350 | 14+11+8+7 | DEUX familles homonymes : surcharges 3/4-args -> `MaybeBehaviour` (EFFET) ; surcharges 1/2-args (`df6350`, `df6470`) -> `MaybeTrigger` (PREDICAT, PRNG en champ `+0x18`) | PORTÉ : EFFET = `entities/behaviours.py::Maybe` ; PREDICAT = `entities/triggers.py::MaybeTrigger` (case-1203) |
| IsFirstHitInSeries | 180df3a70 | 4 | predicat « coup d'index 0 de la serie » (`AbilityEntities.IsFirstHit` = `DamageAppliedResult.hitIndex == 0`) | PORTÉ `entities/triggers.py::IsFirstHitInSeries` (case-1203). Frere `IsFirstHitGroupInAttack` (180df3a20, champ +0x118) MANQUANT |
| Inform / InformWeapon / InformList | 180df2380(+df2450,df2300,df2510,df24b0,df25e0), df2010(+df2260), df1f60 | 15+14+12+6+5+4 / 9+3 / 5 | emet une info/event | MANQUANT (fort refcount cumule) |
| OnDeath / OnPreDeath(2) / OnDeathEvent | 180df7c40, df7f10(+df7ee0), df7ad0 | 17+19+6+5 | hooks de mort | MANQUANT |
| OnOwnerSpecificAbilityInit / OnNormalAttackOrSmite | 180df7db0, df7c70 | 20+4 | hooks d'init | OnNormalAttackOrSmite PORTÉ collapsé (#35 `lord_of_tempests.py` : `On(38) \| (On(9) & kind==0x3f5)` — la branche 2 = le MÊME nœud DAT_18322f680+DirectAbilitySelector(1013) que la branche 2 d'IsNormalAttack, cf. dsl-wave3) ; OnOwnerSpecificAbilityInit MANQUANT |
| FromTrigger | 180df00e0 | 17 | valeur depuis le contexte du trigger | PARTIEL (inline dans UnitsDirectlyBehind) |
| Do / Repeat / Repeat | 180dee620, dfa180 | 4+10 | execute / repete | MANQUANT |
| Nothing / Null | 180df7870, df74f0 | 52+23 | no-op / vide | MANQUANT (fort refcount) |
| ConditionalSelector | 180dec6d0 | 8 | selecteur conditionnel | MANQUANT |

### G. TargetsSelector (couche ciblage DSL separee - `IdunBattle.DSL.TargetsSelector`)

Algebre d'ensembles de cibles (op sur selecteurs), au-dessus des selecteurs DSLFactory.

| Concept | VA | refcount | Semantique | PORT |
|---|---|---|---|---|
| op_Addition (+) | 181010e80 | 179 | union de selecteurs | MANQUANT (tres fort refcount) |
| op_Subtraction (-) | 181010fa0 | 134 | difference d'ensembles | PORTE (`Sub`) |
| op_BitwiseAnd (&) | 181010f10 | 73 | intersection | PORTE (`And`) |
| Otherwise | 18100e820 | 44 | fallback si vide | MANQUANT (fort refcount) |
| SelectUniqueUnits | 1810108b0 | 26 | unites uniques | PARTIEL (dedup logique) |
| SelectTiles / SelectTile | 18100fdf0, fb90 | 13+12 | resout en tiles | MANQUANT |
| SelectAllUnits / SelectUnit | 18100ee50, 810bc0(+810de0) | 11+8+8 | resout en unites | MANQUANT |
| SelectFirst | 18100f740 | 7 | premier | MANQUANT |
| And | 18100e680 | 4 | ET logique de selecteurs | PORTE (`And` couvre &) |
| SelectActor/AllActors/UniqueActors | 18100e8b0, eb00, 810190 | 3+2+2 | resout en acteurs | MANQUANT |
| SelectEffects / SelectMachine / SelectUniqueTiles | 18100f170, f950(+f980), 810500 | 2+2+2 | resolutions specialisees | MANQUANT |
| Count / MatchesUnitSelectionType | 18100e710, e800 | 2+2 | cardinal / typage | MANQUANT |

---

## 3. Classes de noeud specialisees hors DSLFactory (Selectors nommes)

Selecteurs implementes en classe C# dediee (pas via factory), decompilables individuellement :
`IdunBattle.Entities.Selectors.TilesOnSameElevationSelector.Select @180efa8a0` (PARTIEL, inline),
`ValidNormalAttackTargetsSelector`, `UnitForcedAttackTargetsSelector`,
et les selecteurs par-ability (`BlightGrenadesAbility$$GetValidSecondaryTargetsSelector @1811bb340`,
`GauntletsOfUltramarAbility$$Get*TargetsSelector @1811e20xx`, `CatalystAbility$$GetEffectTargetsSelector`,
`StaffOfStarsAbility$$GetSecondaryTargetsSelector`) — ce sont des ARBRES specifiques composes des primitives
ci-dessus, pas de nouvelles primitives.

---

## 4. Synthese couverture (concepts distincts, overloads regroupes)

Comptage par concept de noeud (un concept = 1 type de noeud logique, N VAs) :

- Total concepts distincts identifies : **~185** (dont ~155 cote DSLFactory a refcount>=3, ~13 TargetsSelector,
  ~17 selecteurs/formules nommes). En comptant la longue traine refcount<=2, le vocabulaire depasse 200.
- **PORTE (nodes.py, generique)** : 24 concepts
  = Const, ConfigConst, Sum, Min, Multiply, Difference, If, TotalTimesAttacked, TimesRepaired, HasFlag,
    CasterTile, TargetTile, OwnerTile, SurroundingUnits, AdjacentEnemies, Enemies, Damageable, And, Sub,
    UnitSet, UnitsDirectlyBehind (+ Sub/And couvrant op_Subtraction/op_BitwiseAnd).
- **PARTIEL (inline dans une ability, non generalise)** : ~14 concepts
  = ConfigVar, Get, StatAmount, HasTrait, IsAlive, Units, AdjacentTiles/Units, SurroundingTiles,
    TilesOnSameElevation, Owner*/Caster* props, FromTrigger, SelectUniqueUnits, TimesReceived*.
- **MANQUANT** : ~150 concepts (dont ~30 a fort refcount).

Repartition par categorie (concepts, hors traine refcount<=2) :
- A. Arithmetique/combinateur : ~20 concepts (6 portes, 1 partiel, 13 manquants)
- B. Logique/predicat : ~40 concepts (2 portes, 3 partiels, ~35 manquants)
- C. Geometrie/selecteur : ~55 concepts (5 portes, 7 partiels, ~43 manquants)
- D. Etat/contexte : ~35 concepts (2 portes, 8 partiels, ~25 manquants)
- E. Effet/action/mutateur : ~45 concepts (0 porte, 0 partiel generique, ~45 manquants)
- F. Controle/flow : ~18 concepts (0 porte, 1 partiel, ~17 manquants)
- G. TargetsSelector : ~13 concepts (2 portes, 1 partiel, ~10 manquants)

Observation cle : le port actuel couvre bien l'axe **numerique de calcul de hits** (Sum/Min/Multiply/
Difference/ConfigConst/If) et un AoE de ciblage minimal, mais **zero mutateur (Behaviours)** et **zero
controle de flow (On/Group/Triggered)** en generique — le runner Python porte ces effets par un autre
chemin (operations/ et abilities/handler), pas via le moteur de noeuds DSL. La categorie E/F est donc
"MANQUANT au sens noeud-DSL" mais partiellement couverte par l'archi runner (a arbitrer selon le but :
si le but est un evaluateur d'arbres d'ability fidele, E/F sont a porter comme noeuds ; si c'est juste la
prediction/scoring, A/B/C/D priment).

---

## 5. TOP-15 des noeuds MANQUANTS a plus fort refcount (ordre de port prioritaire)

Priorite = refcount cumule (frequence d'usage reelle = combien d'abilities en dependent). Restreint aux
noeuds pertinents pour un evaluateur d'arbres (les mutateurs E/F fort-refcount sont listes mais notes
[runner] car deja couverts hors-DSL) :

| # | Noeud | Categorie | refcount~ (cumule) | VA principale | Note |
|---|-------|-----------|-------------------|---------------|------|
| 1 | On | F.controle | 379+ | 180df8010 | attache behaviour->event ; socle de tout arbre "actif" [runner] |
| 2 | Get | D.etat | 198+102+... ~370 | 180df05d0 | accesseur generique omnipresent |
| 3 | Owner* (props) | D.etat | 207+186+97 ~490 | 180e026f0 | OwnerIsTarget/Caster/Actor (predicats contextuels) |
| 4 | ConfigVar | D.etat/A | 193+80+29 ~312 | 180decac0 | variable config runtime (complement de ConfigConst deja porte) |
| 5 | HasTrait | B.predicat | 161 | 180df14c0 | condition trait (partiel inline -> a generaliser) |
| 6 | AddEffect | E.mutateur | 144+139+90+30 ~403 | 180de6d20 | ajout d'effet [runner] |
| 7 | HasEffect | B.predicat | 140+4 ~144 | 180df0fb0 | condition effet present |
| 8 | Count | A.arith | 85 | 180decfa0 | cardinal d'un selecteur |
| 9 | Friends | C.geometrie | 116 | 180df0040 | filtre allies (symetrique d'Enemies porte) |
| 10 | Units | C.geometrie | 128+10 ~138 | 180e01340 | tiles->unites (generaliser hors SurroundingUnits) |
| 11 | Tiles | C.geometrie | 118 | 180dfdc60 | unites->tiles |
| 12 | First | C.geometrie | 128+19 ~147 | 180defae0 | selection ordinale (tres utilise en ciblage) |
| 13 | TurnsFromRounds | A.arith | 108+17 ~125 | 180dfec50 | conversion duree (effets/cooldowns) |
| 14 | UnitsWithTrait | C.geometrie | 90+39 ~129 | 180e00b10 | filtre par trait |
| 15 | Filter | C.geometrie | 75 | 180def870 | filtre generique par predicat (debloque tous les Is*/Has*) |

Suivants immediats (16-25) : Cache (123), AmountIsGreaterThanZero (140 cumule), IsMeleeAttack (72),
Entity/EntityId (160 cumule), PickRandomly (104 cumule), Spawn (100 cumule [runner]), Attack* (200+ [runner]),
Unique (45), SortByFormula (46), CurrentAbilityIs/TriggeringAbilityIs (55 cumule).

Ordre de port recommande pour un evaluateur d'arbres pur (hors mutateurs runner) :
1. **Filter + les predicats feuille** (Filter debloque la categorie B entiere : HasTrait, HasEffect,
   IsMeleeAttack/RangedAttack, IsAlive/IsDead, AmountIs*). C'est le multiplicateur de couverture #1.
2. **Selecteurs de base** : Friends, Units, Tiles, First, Unique, UnitsWithTrait, SortByFormula/Distance.
3. **Accesseurs d'etat** : Get, ConfigVar, StatAmount (generaliser), Owner*/Caster* props, Entity/EntityId,
   Count, Cache.
4. **Arith restante** : Max, Divide, Modulo, Negative, Half, Double, PercentageOf, TurnsFromRounds,
   RandomAmount, ConditionalAmount.
5. **TargetsSelector** : op_Addition (union) + Otherwise (fallback) — completent Sub/And deja portes.
6. **Controle/flow + mutateurs (E/F)** : uniquement si le but est un evaluateur d'arbres d'ability complet
   (sinon deja couverts par runner/operations). On, Group, Triggered, PickRandomly, Maybe, Inform,
   AddEffect/RemoveEffect, ChangeStat, Heal, Spawn, Attack*, MoveUnit.

---

## 6. Points a confirmer / limites de ce catalogue (statique)

- Les refcounts sont ceux de la table de symboles ghidra (sites d'appel dans le binaire), pas ponderes par
  la frequence d'execution runtime — bon proxy de "combien d'abilities l'utilisent", pas de "hot path".
- La distinction PORTE/PARTIEL cote Python est basee sur `nodes.py` (generique) + le scan des arbres inline
  dans `active_ability.py`. Un concept "PARTIEL" est porte pour UNE ability precise, pas comme primitive
  reutilisable — a generaliser lors du scaling.
- Semantique des noeuds a ctor MISLABELE lue par STRUCTURE (classe-singleton DAT_*, arite, arithmetique du
  ctor) — jamais par le nom affiche. Cas confirmes ambigus signales en section 0. Tout concept dont je n'ai
  PAS decompile le ctor garde sa semantique deduite du NOM natif explicite (ex. Max/Divide/Modulo/Friends :
  noms non-ambigus, non-decompiles) — a verifier au moment du port si un doute apparait.
- Non couvert ici : la semantique fine des ~120 primitives a refcount<=3 (longue traine tres specialisee :
  ContagionsOfNurgle*, BloodRunsAngerRises*, per-boss shapes...). Elles sont listees par categorie mais leur
  port se fera a la demande, ability par ability, quand une ability concrete les reference.
