# #241 — Gate de PORTÉE d'un cast (`TargetIsInRange`)

Le maillon qui manquait à `case-115` : la cascade de ciblage refusait bien l'ami, le caster, la
cible intouchable — mais **laissait caster hors portée**. Permissivité silencieuse, donc exactement
ce qu'un entraînement irait exploiter : l'espace d'action offline était plus large que le natif.

**Verdict du critère, dans les deux sens (mesuré) :**

| sens | question | verdict |
|---|---|---|
| ← | le moteur refuse-t-il hors portée là où le natif refuse ? | **oui** — 64 refus concordants, dont ~20 `TargetIsInRange`/`TargetIsAtRange` |
| → | refuse-t-il un cast que le natif ACCEPTE ? | **non** — 0 faux-refus, 0 bit divergent sur 78 lignes confrontées |

---

## 1. Pourquoi ce volet n'était pas gaté par un bit

Les ~25 autres règles du filtre statique sont chacune gardées par un flag de
`IdunBattle.Core.Services.TargetingRule` (`options+0x28`). **La portée, non.** Elle est armée par
un CHAMP des options — `TargetingRange`, logé à `options+0x08..0x1f` — et le filtre la teste pour
toute ability dont `UseWholeBoard` est faux. C'est pour ça qu'elle avait été laissée de côté : le
mécanisme d'armement du reste du module (« un bit du masque ») ne s'y applique pas.

Extrait VERBATIM de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge
7 arguments — `ignoreRangeChecks` vaut faux sur le chemin `ExecuteInternal`) :

```
if (!ignoreRangeChecks) {
    if (!range.OnlyAdjacent) {                        // Range+0x04
        if (!options.Range.UseWholeBoard) {           // options+0x0d
            d = movementQuery.GetDistance(casterTiles, target);
            if ((rules & TargetIsAtRange) == 0) { if (range.Value < d) -> broken(TargetIsInRange) }
            else                                 { if (d != range.Value) -> broken(TargetIsAtRange) }
        }
    } else if (!battleQuery.AreEntitiesAdjacent(casterTiles, target)) -> broken(TargetIsInRange)
    <ligne de vue : GetTilesObscuringTerrain, NON PORTÉE>
}
```

**Trois régimes**, à distinguer AVANT tout calcul de distance :

| `TargetingRange` | effet | abilities du registre |
|---|---|---|
| `UseWholeBoard` | **aucun** test de portée | 9 |
| `OnlyAdjacent` (résolu vrai) | test d'ADJACENCE, pas de `distance <= N` | 3 + les clampées |
| sinon | `hexDistance <= Range.Value` (ou `==` sous `TargetIsAtRange`) | 16 |

**Position dans la cascade** (elle fixe la RAISON rendue, pas seulement le verdict) : après
`TargetIsTargetable` / `TargetIsNotSteppable` / les `TargetHasNTiles`, **avant** la ligne de vue puis
tout le bloc `TargetIsSummon`/`TargetIsHero`/…/`TargetMatchesDynamicRule`/`TargetIsCasterOrEnemy`.

---

## 2. `TargetingRange` — la struct qui arme le volet

`IdunBattle.Core.Services.TargetingRange$$.ctor(onlyAdjacent, useRangeFromConfig, useWholeBoard,
overrideRange, overrideRangeFunc)`, 0x18 octets :

```
+0x00  RangedBool    onlyAdjacent
+0x04  bool          useRangeFromConfig
+0x05  bool          useWholeBoard      <- le fameux `options+0x0d`
+0x08  Nullable<int> overrideRange
+0x10  GetRange      overrideRangeFunc  (aucun porteur du registre)
```

Les **5 valeurs statiques** écrites par `IdunBattle.Core.Services.TargetingRange$$.cctor` (le dump
il2cpp ne porte pas les noms des champs statiques → désignés par leur offset RELATIF dans le bloc,
même convention que les presets `TargetingOptions` de `darkangels.py`) :

| offset | contenu | nom donné au port |
|---|---|---|
| `statics+0x00` | `onlyAdjacent = IfNotRangedCaster` | `RANGE_ADJACENT_IF_MELEE_CASTER` |
| `statics+0x18` | `useRangeFromConfig = true` | `RANGE_FROM_CONFIG` |
| `statics+0x30` | `onlyAdjacent = True`, `overrideRange = 1` | `RANGE_ADJACENT` |
| `statics+0x48` | `useWholeBoard = true` | `RANGE_WHOLE_BOARD` |
| `statics+0x60` | `overrideRange = 0` | `RANGE_SELF` |

`IdunBattle.Core.Services.TargetingRange$$CustomRange(int)` construit en plus
`{onlyAdjacent = False, overrideRange = n}` (seul usage du registre : RadBombardment, n = 1).

**Le masque ne prédit PAS la portée.** Trois presets `TargetingOptions` distincts portent le même
`Rules = 0x4002` avec des `TargetingRange` DIFFÉRENTS (`+0x140` → fromConfig + `forceMeleeTarget =
True` ; `+0x180` → fromConfig + `False` ; `+0x00` → adjacent-si-mêlée). Les 28 `TargetingRange` du
registre ont donc été lus **un par un** au ctor, comme les masques.

---

## 3. `GetRange` — décomposition, confrontée live

Mirror de `IdunBattle.Core.Services.TargetingQuery$$GetRange(caster, casterTiles, options)` :

```
if (casterTiles vide)                 return default(Range);
if (options.Range.UseWholeBoard)      return <Range sans OnlyAdjacent>;      // court-circuit
onlyAdjacent = RangedBoolExtensions.IsTrue(options.Range.OnlyAdjacent, caster);

if      (!HasAnyWeapon(caster))    v = GetStat(caster, StatType.Range = 2);
else if (!HasRangedWeapon(caster)) v = 1;
else                               v = GetStat(caster, StatType.ExtraRange = 0x18)
                                       + FindLongestRangedWeapon(caster).Range;

v = options.Range.OverrideRange.GetValueOrDefault(v);          // ctor, ou config (cf. ci-dessous)
if (options.Range.OverrideRangeFunc != null) v = OverrideRangeFunc(caster);

if (HasEffect(caster, ForcedInMelee = 0x529))            { v = Math.Min(1, v); onlyAdjacent = true; }
if (RangedBoolExtensions.IsTrue(options.ForceMeleeTarget, caster)
    && attackQuery.ShouldApplyRangedInMelee(caster, casterTiles, ignoreTrait: true))
                                                          { v = Math.Min(1, v); onlyAdjacent = true; }
return new Range(v, onlyAdjacent);
```

**L'ordre est le port** : la valeur d'abord (arme → override → config), les deux CLAMPS ensuite. Un
clamp appliqué avant l'override serait écrasé par lui.

### 3.a `useRangeFromConfig` → la constante d'ability

`IdunBattle.Entities.Abilities.AActiveAbility$$SetConfigValuesInTargetingOptions` tourne AVANT la
query, sur la copie locale des options :

```
if (Configuration != null && options.Range.UseRangeFromConfig && !options.Range.OverrideRange.HasValue)
    options.Range.OverrideRange = Configuration.GetNumberConstant(0x16);
```

`AbilityConstantType` **0x16 = `range`** → clé `constants.range` de gameconfig-abilities. Les 12
porteurs `useRangeFromConfig` du registre l'ont tous (2 ou 3).

### 3.b Le clamp mêlée — l'étage le plus risqué, et le seul qui EXIGEAIT une mesure

`GetRange` appelle `AttackQuery$$ShouldApplyRangedInMelee` avec **`ignoreTrait = 1`**. Ça change
tout : le gate `HasTrait(0xb Ranged)` — inerte partout ailleurs, aucune unité ne porte ce trait
(#161) — est **court-circuité**. Ce chemin-ci MORD donc pour tout caster.

Ghidra affiche `uStack…28 = 0` dans le thunk d'`AttackQuery`, ce qui se lit comme
« `ignoreTrait` forcé à 0 » — et aurait rendu tout l'étage mort. **Lecture à l'octet** du thunk :

```
49 8b c0  mov rax, r8            ; rax = attackerTiles
48 c7 44 24 28 00…  mov [rsp+28], 0   ; <- le slot MethodInfo*, PAS ignoreTrait
4c 8b 41 20  mov r8, [rcx+0x20]  ; r8 = this.state
4c 8b d2 / 48 8b d0 / 49 8b ca   ; rcx = attacker, rdx = tiles
e9 …        jmp DamageCalculations$$ShouldApplyRangedInMelee   ; r9 = ignoreTrait, INTACT
```

`r9` traverse le thunk sans être touché : `ignoreTrait` est bien celui du call-site, donc 1.
**Confirmé live** (§5, scénario S1/S2).

Corps de `IdunBattle.Core.Services.DamageCalculations$$ShouldApplyRangedInMelee` : il existe une
tuile adjacente à une tuile du caster portant une unité ENNEMIE, vivante, `IsTargetable`,
NON-`Steppable` (trait 0x1b) et `CanMeleeAttackOverElevationDifference` (`|ΔElev| < 2`).

### 3.c `AreTilesAdjacent` ≠ « distance hex 1 »

`IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(tileA, tileB)` :

```
dElev    = |tileB.Elevation - tileA.Elevation|;
adjacent = (tileA == tileB) ? true : tileA.Connectivity.IsNeighbour(tileB);
return dElev < 2 && adjacent;
```

Deux quirks que la paraphrase manque, **les deux mesurés** :
* **la MÊME tuile compte comme adjacente** — c'est ce qui fait que le natif, pour IronkinSteeljack
  ciblant sa propre tuile, passe la portée et rend `TargetTileIsFree` (0x1000). Un port en
  `dist == 1` rendait `TargetIsInRange` : **BIT-DIFF mesuré**, puis corrigé ;
* **l'adjacence est GATÉE EN ÉLÉVATION** (`|ΔElev| < 2`).

### 3.d Ce que le port NE PEUT PAS mesurer → aucun gate

`get_range` rend `None` (⇒ aucun refus) dans quatre cas, tous délibérés :

1. `TargetingRange` non RE-lu (`options.range is None`) ;
2. caster sans tuile (`casterTiles` vide côté natif) ;
3. `UseWholeBoard` (le filtre ne teste rien) ;
4. **portée d'arme NON OBSERVABLE** : la branche `!HasAnyWeapon` rend `GetStat(StatType.Range = 2)`,
   et le StatType 2 (`[Obsolete] Idun Concept`) n'est PAS au catalogue de `combatSnapshot`. Rendre
   0 pour les **81 unités sans arme du gameconfig** (les Machines of War, les objets de décor)
   ferait refuser TOUTES leurs cibles. On rend `None`.

---

## 4. Le stat 24 `ExtraRange` — le verrou d'outillage

`GetRange` ajoute `GetStat(caster, ExtraRange = 0x18)` sur la branche ranged. Ce stat manquait au
catalogue de `combatSnapshot` (la table sautait de 23 à 25) : **le canal même par lequel la portée
d'une unité est observable était invisible**. Il est exposé depuis le reinject du 2026-07-27, ce qui
rend `unit_weapon_range` confrontable unité par unité au lieu d'être déduit.

**Dé-fork** : `triggers/base.py::_max_attack_range` (le `DSLFactory.IsInAttackRange` de l'overwatch)
était un SECOND port des mêmes trois branches d'arme. Il DÉLÈGUE désormais à
`targeting.unit_weapon_range`. Seule différence, assumée et écrite aux deux endroits : sur la branche
`!HasAnyWeapon`, `IsInAttackRange` substitue **1** (son comportement historique — un 0 fermerait
l'overwatch d'une MoW) là où le gate de cible préfère ne poser AUCUN refus.

---

## 5. Validation

### 5.a Scénario discriminant du clamp mêlée — `probe_range_gate_melee_clamp.py`

Deux états qui ne diffèrent QUE par la présence d'un ennemi adjacent au caster
(`necroDestroyer` / MultiThreatEliminator 1006, `constants.range = 2`, `forceMeleeTarget = True`) :

| état | cible | natif | port |
|---|---|---|---|
| S1 — aucun ennemi adjacent, cible à distance 2 | u79 | `0x0` accepté | `0x0` accepté |
| S2 — un ennemi adjacent, **même** cible à distance 2 | u79 | `0x8000000 TargetIsInRange` | `0x8000000` |
| S2 — même état, cible ADJACENTE | u77 | `0x0` accepté | `0x0` accepté |

Sans le clamp, S1 et S2 rendraient le même verdict côté port (cible acceptée) et la divergence
serait PERMISSIVE, donc invisible en self-play. C'est ce test qui prouve `ignoreTrait = 1`.

### 5.b Confrontation par masque — `probe_targeting_masks_lot4.py` (5 groupes)

`78 lignes | FAUX_REFUS = 0 | BIT_DIFF = 0 | refus concordants = 64 | permissifs = 10`.

`0x8000000 TargetIsInRange` a été RETIRÉ de `UNPORTED_RULES` : le laisser masquerait désormais de
vraies divergences.

### 5.c Résidus PERMISSIFS restants (natif refuse, port accepte) — tous expliqués

| ability | raison native | pourquoi le port ne la voit pas |
|---|---|---|
| HeroicFusillade 1180 | `TargetMatchesDynamicRule` | prédicat dynamique de l'ability non porté |
| VigilanceEternal 1202 | `TargetIsInRange` | **par sa règle DYNAMIQUE**, pas par ce volet (`UseWholeBoard`) — même patron que Waaagh |
| Chronometron 1226 (self) | `AddCasterIfAtLeastOneTarget` | `GetValidTargets` non porté (cf. §6) |
| IronkinSteeljack 1219 | `TargetTileIsFree` | domaine TILE non porté |

### 5.d Cas où le port refuse par la PORTÉE et le natif par une règle ANTÉRIEURE

`AncestralFortune 1207` : le natif rend `0x2` — c'est
`AncestralFortuneAbility$$GetDynamicInvalidCasterReason` (`return 2`), donc le volet **CASTER**, qui
court-circuite AVANT tout le filtre de cible. Le port, lui, n'ayant pas ce prédicat, atteint la
portée (`overrideRange = 0`) et refuse. **Les deux refusent** — pas de faux-refus — mais le code
diffère parce que la cascade native s'est arrêtée plus tôt.

---

## 6. Ce qui n'est PAS couvert

- **Ligne de vue** (`TargetingQuery$$GetTilesObscuringTerrain`) : même emplacement de cascade que la
  portée, non portée. Résidu PERMISSIF.
- **`GetCasterNotAddedReason`** rend toujours 0. Ce n'est plus la portée qui bloque (elle est
  portée) : c'est `TargetingQuery$$GetValidTargets`, qui ÉNUMÈRE toutes les cibles légales du
  plateau. Écart connu et mesuré : Chronometron, natif `0x800`.
- **Unités MULTI-TUILES** (`GetFeetCount` 3/7) : le natif prend le MIN sur toutes les tuiles
  occupées, le port compare la tuile PRINCIPALE (une seule `PositionComponent` offline). Écart
  possible d'au plus 1 hex, et seulement pour un caster/cible multi-tuiles.
- **Cibles-TUILE** : `_tile_of` ne les résout pas (une tuile n'est pas une entité du `State`) → le
  gate de portée ne mord pas pour RadBombardment (1116) ni SquigMine (1201). L'annotation est
  exacte et s'activera d'elle-même le jour où les tuiles seront des entités.
- **`overrideRangeFunc`** : aucun porteur du registre ne le pose ; non modélisé.
- **Dette CONNUE, laissée exprès** : les 28 constantes `RULE_*` écrites à la main en tête de
  `targeting.py` s'arrêtent au bit 31 et font doublon avec le module généré
  `abilities/targeting_rule.py` (58 bits). La cascade — donc le code neuf de #241 — continue
  d'utiliser les `RULE_*` par cohérence locale ; la convergence est un chantier à part.
