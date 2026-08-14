# #889-r6 — `InstrumentsOfVengeance` (1215) : la face COMBAT, et l'étage qui la rendait fausse

**Verdict : PORTÉE et CONFRONTÉE (phase 1) ; phase 2 NON PORTÉE, résidu nommé `#889-r7`.**

`1215` était l'un des derniers **no-op silencieux** d'active du registre : `ABILITY_CLASSES.get(1215)`
rendait `None`, donc `AbilityHandler` acceptait le cast, posait les flags de tour et n'exécutait
RIEN — alors que la face DÉCISION est portée depuis `#27-r6`, avec une base d'utilité de **20000**
(dès que 1215 est légale, elle est l'action la plus prioritaire du jeu). L'IA choisissait donc, tous
les tours, une ability qui ne faisait rien. Le compte courant des no-op se **re-dérive**
(`python scripts/python/audit_combat_ability_coverage.py`), il ne se cite pas.

## 1. L'artefact natif — un arbre DSL pur, sur DEUX fonctions

`IdunBattleLogic.Entities.Abilities.Active.Loki.InstrumentsOfVengeanceAbility$$ExecuteBehaviour` :

```
a = GetEffectBehavior(direction = 1, first = true) + GetEffectBehavior(direction = 5, first = false)
b = GetEffectBehavior(direction = 2, first = true) + GetEffectBehavior(direction = 4, first = false)
r = DSLBehaviors$$If( DSLTriggers$$Maybe(0x32 = 50), a, b )
  + DSLBehaviors$$AddBondEffect( 0x5ef = 1519 InstrumentsOfVengeance_PendingAttack,
                                 AActiveAbility$$get_AbilityStateReference(this),
                                 source/targets/bondedEntity = Owner@DSLSelectors+0x30,
                                 options = <struct ZEROEE> )
  + DSLBehaviors$$If( AbilityTrigger$$op_LogicalNot(
                          DSLTriggers$$HasAdjacentEnemies(Owner@+0x30, Owner@+0x30, false, false) ),
                      DSLBehaviors$$ActivateEffect( Owner@+0x30, 0x3f1 = 1009 Overwatch_AutoAttack ),
                      null )
return AActiveAbility$$Execute(entities, this, r)
```

et `...InstrumentsOfVengeanceAbility$$GetEffectBehavior(direction, first)` :

```
i      = first ? 0 : 1                                   # `((byte)first & 0xff) ^ 1`
behind = DSLSelectors$$TilesBehindInLine( origin = ActiveTarget@DSLSelectors+0x68,
             direction = DSLFormulas$$Get(EdgeExtensions$$Rotate(direction, 3)) )
edge   = DSLSelectors$$EdgeTilesByDirection( DSLFormulas$$Get(direction) )
if (!first)
    edge -= DSLSelectors$$TilesBehindInLine(
                Entity(GetPersistentData(AbilityOrEffect(this), Owner@+0x30, KEY_TARGET + "0")),
                Entity(GetPersistentData(AbilityOrEffect(this), Owner@+0x30, KEY_DIR    + "0")) )
sel = DSLSelectors$$Randomize(edge)
sel = SortByFormula(sel, Count(behind),                                        ascending = 0)
sel = SortByFormula(sel, Count(Friends(Owner@+0x30, Units(behind + ActiveTarget, true, 3), 3)),
                                                                               ascending = 1)
sel = SortByFormula(sel, Count(Enemies(Owner@+0x30, Units(behind + ActiveTarget, true, 3), 3)),
                                                                               ascending = 0)
sel  = DSLSelectors$$Cache( DSLSelectors$$First(sel, 1, 0), true )
line = DSLSelectors$$TilesBehindInLine( sel, Get(EdgeExtensions$$Rotate(direction, 3)) )
r = SetPersistentData( AbilityOrEffect(this), Caster@+0x48, KEY_TARGET + i, EntityId(sel) )
  + SetPersistentData( AbilityOrEffect(this), Caster@+0x48, KEY_DIR    + i,
                       EntityId(First(line, 1, 0)) )
return r + DSLBehaviors$$AddEffect( 0x5ee = 1518 InstrumentsOfVengeance_LocationTarget,
                                    AbilityStateReference, source = Owner@+0x30,
                                    targets = sel + line, options = <struct ZEROEE> )
```

**Ordinaux qualifiés** : `0x5ee` = 1518 `EffectType.InstrumentsOfVengeance_LocationTarget` ;
`0x5ef` = 1519 `EffectType.InstrumentsOfVengeance_PendingAttack` ; `0x3f1` = 1009
`EffectType.Overwatch_AutoAttack` (ordinal **partagé** — `ActiveAbilityType(1009)` est
`ResurrectionOrb` ; c'est l'`ActivateEffect` qui fixe l'enum) ; `0x32` = 50 % (un pourcentage, pas
un enum) ; `1/5/2/4` = des `IdunBattle.Utils.Hex.Edge`.

**Les deux clés persistantes sont LUES**, pas inventées : string literals du build résolus par
`data/symbols/<build>/metadata/string_literals.tsv` (slots `0x3364300` et `0x3364070`) —
`"InstrumentsOfVengeance_TargetTile_"` et `"InstrumentsOfVengeance_DirectionTile_"`, concaténées à
`i.ToString()`.

### Ctor — forme STATIC-COPY, et le bit ABSENT est le sujet

`...InstrumentsOfVengeanceAbility$$.ctor` **n'appelle aucune** surcharge de
`IdunBattle.Core.Services.TargetingOptions$$.ctor` : il recopie les 0x40 octets du preset
`<TargetingOptions statics>+0x280` et les passe tels quels à `AActiveAbility..ctor(this, &opts, 2)`.
Le masque effectif est la constante que `TargetingOptions$$.cctor` écrit en `<preset>+0x28` —
**relue pour CETTE ability** : `*(statics + 0x2a8) = 0x8004` = `CasterIsPossibleTarget |
CasterMatchesDynamicRule`. `isSelfCasting = 1`, `forceMeleeTarget = 1` (`RangedBool.False`),
`range = RANGE_SELF`. `AbilityAttackType` = littéral **2** = `Others`.

⚠ **C'est le MÊME preset que `1216 MartialExemplar`**, mais 1216 enchaîne la surcharge PRESET+FLAGS
avec `additionalRules = 0x10` → `0x8014`. **1215 n'a donc PAS `CasterHasNotMoved`** : elle reste
castable après déplacement. Recopier le masque de la voisine l'aurait rendue incastable après
mouvement — et c'est précisément ce que sa face DÉCISION exploite (utilité évaluée **par tuile
atteignable**, `playbook/loki_custom.py`).

## 2. Ce que la confrontation a trouvé — un étage, pas un scalaire

Premier accord partiel : **une ligne exacte, l'autre décalée**. La décomposition par étage a
écarté trois causes avant d'atteindre la bonne.

| étage | mesure | verdict |
|---|---|---|
| choix de branche (`Maybe`) | port toujours `b`, natif `a` | **PRNG non calé** — `load_state` laisse `state.rng` à `None`, et `MaybeTrigger` sans PRNG rend `99 < chance` (le mirror de `!CanUseRandom`), donc `99 < 50` = faux. Corrigé en calant `dumpRng`. |
| consommation PRNG | `mti` 624 → 20 **des deux côtés** | identique — ce n'était pas un désalignement de tirages |
| bordure + direction + longueur | ligne 1 identique tuile à tuile, **deux montages** | exact |
| **`Count(TilesBehindInLine(...))`, clé de tri** | natif 6, port **5** sur la même tuile | **PORT FAUX** — cause ci-dessous |

### La cause : `IsTileValidForList` fondait deux gates que le natif sépare

```
if (tileComponent+0x41 != 0)            return false            # MUR, INCONDITIONNEL
if (!checkWalkable)                     return tileComponent+0x40 == 0
if (!TileExtensions.IsWalkable(tile))   return false            # DANS la branche walkable
```

Le port appliquait `board.walkable` **inconditionnellement** — une dégradation RESTRICTIVE, qui
coupe la ligne là où le natif la continue. Sa propre docstring la déclarait « inerte pour les
call-sites portés » (tous filtraient `HasUnit` en aval) : **elle ne l'est plus**, parce que 1215
fait de la LONGUEUR de la ligne une clé de tri.

**Mesure directe** (board `CE6_boss`, `settings = null` donc `checkWalkable = 0`) : le natif MARQUE
`(6,4)` et `(6,6)`, deux tuiles `Unplayable` (`walkable = false`, `isWall = false`), et traverse
aussi les `Block`. Donc **ni `Block` ni `Unplayable` ne posent `+0x40`**.

Réparation : `battle_query.is_tile_valid_for_list` prend un accesseur `is_wall_at` et applique
l'ORDRE natif quand il est fourni ; `TilesBehindInLine` le câble depuis le champ `isWall` du
`boardGraph`. **Accesseur absent ⇒ ancien comportement**, donc aucun call-site qui ne câble pas le
nouveau substrat ne change.
Reste NON PORTÉ, nommé : `+0x40` lui-même — aucun champ du `boardGraph` ne le publie (`walkable`,
`isWall`, `isTemporary`, `isInFog`, `tileDefId` : aucun ne concorde avec les deux mesures
ci-dessus). Le gate reste INERTE, borne SUPÉRIEURE, comme tout accesseur absent.

## 3. Mesures

Montage : `probe_889r6_instruments_of_vengeance.py` (board `CE6_boss`, `darkaBossLion:4` monté par
`--explicit-stats`, comme `#889-r5`). Deux régimes, et le second existe pour que la branche
conditionnelle ne soit pas confrontée en régime dégénéré.

| régime | natif | port | verdict |
|---|---|---|---|
| `isole` (aucun ennemi au contact) | 14 tuiles marquées | 14 | **ensembles IDENTIQUES**, même ordre |
| `contact` (un ennemi collé) | 13 tuiles | 13 (+1 re-pose) | **ensembles IDENTIQUES** |
| armement `1519` | 1 | 1 | posé sur le caster |
| overwatch `1009` | isole **1** / contact **0** | isole **1** / contact **0** | **contraste net des DEUX côtés** |

⚠ **Le critère est l'ENSEMBLE des tuiles, jamais le cardinal brut.** Quand les deux lignes se
croisent, le port émet un `AddEffect` par cible — donc deux fois sur la tuile d'intersection, la
seconde avec `placed = False` — là où le flux natif ne publie qu'un `Effect_Refresh` par tuile.
Comparer les cardinaux accusait le port d'un écart qui n'existait pas.

⚠ **Le témoin natif a DEUX étages, et lire le mauvais rend 14 entiers plausibles et faux** : le
`group` porte l'entité-EFFET, l'`action` qui suit porte l'entité qui le REÇOIT. L'appariement passe
par `Effect_Id`. Les ids de tuile du `boardGraph` **sont** les ids d'entité ECS — c'est ce qui rend
la comparaison d'ensembles possible.

**Montage DISCRIMINANT** (celui qui a trouvé le bug) : un ennemi sur une tuile de chaque bordure,
de sorte que le tri `Count(Enemies)` DESC désigne un vainqueur UNIQUE au lieu d'un ex aequo. Sans
lui, les deux côtés départageaient des ex aequo par `Randomize` et l'écart se lisait comme du bruit.

Garde offline : `tests/engine/runner/test_889r6_instruments_of_vengeance_offline.py`, **16 tests**.

## 4. Ce qui n'est PAS couvert, et c'est dit

- **La PHASE 2** — `InstrumentsOfVengeance_AttackAbility$$CreateBehaviour` (+ `$$AttackLine`,
  `$$AttackTargetTiles`, `$$AttackTileBehavior`). Résidu `#889-r7`, RE écrite ci-dessous.
  **Conséquence assumée** : les marques `1518` ne sont jamais consommées, et aucun dégât ne part au
  tour suivant. Dégradation par DÉFAUT (le moteur fait MOINS que le natif), à l'opposé du no-op
  silencieux qu'elle remplace — où l'IA dépensait un tour pour rien ET sans trace.
- **`1519` n'entre PAS dans `PENDING_ATTACK_EFFECTS`**, et c'est délibéré : l'y mettre ferait firer
  `TriggerAbility(Caster(), 1519)` sur une ability triggered absente du registre, tandis que le
  `RemoveEffect` du même arbre consommerait la marque. Le port retirerait l'armement sans jamais
  frapper — un no-op silencieux de plus. Un cran offline garde cette absence **en négatif**.
- **Le départage des EX AEQUO par `Randomize`** : quand plusieurs tuiles de bordure ont les mêmes
  trois clés, le vainqueur sort de la permutation. Les deux côtés consomment le MÊME nombre de
  tirages (mesuré) mais n'en tirent pas la même permutation — foyer `PickRandomly` /
  `loki/splash.py::_pick_randomly_n`, **antérieur à cette tranche**. Les deux montages joués ici
  rendent le tri discriminant, donc l'accord n'en dépend pas.
- **La magnitude** : le cast ne frappe pas. Rien de ce qu'il fait ne se lit dans un total de dégât ;
  tous les crans portent sur des ENSEMBLES et des présences d'effet.
- **`GetDynamicInvalidCasterReason`** : le masque pose `CasterMatchesDynamicRule`, et 1215 reste en
  `CASTER_GATE_NOT_READ` — trancher exigerait le slot de vtable de l'INSTANCE au runtime, que cette
  tranche n'a pas fait. Dégradation PERMISSIVE, déjà nommée dans `services/ability_caster_gates.py`.

## 5. La RE de la PHASE 2 — résidu `#889-r7`

Écrite ici pour que le successeur n'ait pas à la refaire.
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.InstrumentsOfVengeance_AttackAbility$$CreateBehaviour` :

```
eA0..eB1 = Entity(GetPersistentData(AbilityOrEffect(this), Owner@+0x30, <KEY> + "0"|"1"))   # 4 lectures
r   = DSLBehaviors$$RemoveEffect( AllTiles@DSLSelectors+0x18, Nullable(0x5ee) )
    + ( AttackLine(abilityState, eA0, eB0) + AttackLine(abilityState, eA1, eB1) )
    + DSLBehaviors$$ClearAllPersistentData( AbilityOrEffect(this), Owner@+0x30 )
n     = AbilityConfiguration$$GetVariableForLevel(0x4f, abilityState)
t1    = Randomize( CanAddUnit( AdjacentTiles(Owner@+0x30) ) )
t2    = Randomize( CanAddUnit( AdjacentTiles( UnitsDamagedThisPhase(Owner@+0x30) ) ) )
t3    = Randomize( Filter( CanAddUnit(AllTiles@+0x18),
                           NOT HasAdjacentEnemies(Owner@+0x30, ActiveTarget@+0x68, 0, false) ) )
tiles = First( (t2 + t1) + t3, n, 0 )
opts  = SpawnUnitOptions$$WithStatsFromConfig( config@this+0x20, abilityState, 0, 0 )
opts.<+0x18> = DSLBehaviors$$PerformAIAttackFromCurrentPosition( ActiveTarget@+0x68, null, null, false )
return r + DSLBehaviors$$Group(
               DSLBehaviors$$Spawn( Owner@+0x30, tiles,
                                    AbilityConfiguration$$GetStringConstant(config, 0), opts ),
               Owner@+0x30, 0x22 )
```

```
AttackLine(abilityState, edge, direction) =
    Group( Foreach( edge + TilesBehindInLine(edge, direction),      # surcharge DEUX SELECTEURS
                    AttackTileBehavior(abilityState) ),
           Owner@+0x30, 0x31 )

AttackTileBehavior(abilityState) =
    inform = DSLBehaviors$$Inform( 0xc1, EntityId(ActiveTarget@+0x68) )
    cond   = DSLTriggers$$HasUnit(ActiveTarget@+0x68, 3)
             & DSLTriggers$$AreEnemies(Owner@+0x30, ActiveTarget@+0x68, 0)
    atk    = DSLBehaviors$$AttackWithAttackDamage(
                 caster = Owner@+0x30, target = ActiveTarget@+0x68,
                 amount = BaseTriggeredAbility$$MinMaxDamage(this, abilityState),
                 damageProfile = Direct(BaseTriggeredAbility$$GetDamageProfile(this)),
                 hits = Get(BaseTriggeredAbility$$GetHits(this)),
                 abilityOrEffect, options = <ZEROEE>, selectionType = 2 )
    return Group( If(cond, atk + inform, inform), Owner@+0x30, 0x31 )

AttackTargetTiles(edge, direction) = edge + TilesBehindInLine(edge, direction)   # non appelée par CreateBehaviour
```

Et `Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.InstrumentsOfVengeance_PendingAttackEffect` :
`$$.ctor` = `APendingAttackEffect..ctor(this, Nullable(AbilityOrEffect(...)))` — la dérivation est
**LUE**, pas déduite du nom ; `$$GetTriggeredAbilityType` a pour corps entier `return 0x5ef` (un
`TriggeredAbilityType`, pas un `EffectType`) ; `$$GetAttackingUnitSelector` est **surchargée** en
`DSLSelectors$$EffectSource(Effect@DSLSelectors+0x38)`, donc l'entrée à écrire dans
`PENDING_ATTACK_EFFECTS` porte `ATTACKER_EFFECT_SOURCE` — et non le `ATTACKER_BONDED` hérité, même
si le call-site de pose passe `bondedEntity = Owner` (les deux coïncident ici, ce qui rendrait
l'erreur INVISIBLE sur ce porteur).

`1518 InstrumentsOfVengeance_LocationTarget` reste un MARQUEUR pur : son `$$.ctor` est
`BaseEffect..ctor(this, AbilityOrEffect(...), 1)` et la classe ne porte aucun canal — même statut
que `1195 TheLantern_PendingTarget` (`#1030`), qui n'a pas non plus d'entrée dans `EFFECT_CLASSES`.

## 6. Deux nœuds neufs, et deux normalisations de domaine mixte

- **`EdgeTilesByDirection`** (`entities/selectors/geometry.py`) — la bordure du plateau désignée par
  une arête. `North_East`/`South_East` partagent LITTÉRALEMENT le même bloc du `switch` natif, et de
  même `South_West`/`North_West` : les deux branches du `Maybe` visent donc le même couple de
  bordures et ne diffèrent que par l'INCLINAISON des lignes.
- **`hex_edge.rotate`** — `EdgeExtensions$$Rotate`, un `%` sur `int` signé (quotient TRONQUÉ VERS
  ZÉRO). Ce n'est PAS `EdgeExtensions$$Next` (un cran, sens porté par un bool), déjà inline dans
  `NextTileClockwise`.
- **`EntityId`** accepte le domaine TUILE (un id nu) et réduit au PREMIER élément (`SelectSingle`) ;
  il rend `None`, jamais `0` — et `SetPersistentData` n'écrit rien sur `None`, là où un `0` poserait
  une clé que `GetPersistentData` relirait comme une entité.
- **`TileUnion`** accepte un opérande MONO-ENTITÉ (`list(<int>)` levait `TypeError`) : même lecture
  que celle déjà écrite sur `Sub` — l'`op_Addition` natif prend un sélecteur **ou** une entité.

## Résidus ouverts

- `#889-r7` — la PHASE 2 de 1215 (RE ci-dessus, §5) : la triggered `InstrumentsOfVengeance_Attack`,
  l'entrée `1519` dans `PENDING_ATTACK_EFFECTS` (avec `ATTACKER_EFFECT_SOURCE`), et le volet SPAWN
  de son `CreateBehaviour`. Tant qu'elle manque, les marques `1518` ne sont jamais consommées.
