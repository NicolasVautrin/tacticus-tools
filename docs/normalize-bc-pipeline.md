# Normalize BC Pipeline — snapshot 2026-05-23

État validé end-to-end pour reprendre après compact.

## Objectif

Construire une `BattleConfiguration` avec units **normalisées** (level/rank/rarity choisis, ability levels, gear synthétique) — **déterministe et reproductible**, indépendant du player state. Pour usage RL.

## Pipeline validé

### 1. Calcul stats via `IStatsFormula` direct call (bypass cascade UnitProgression.GetStats)

Signature C# cible :
```csharp
IdunMetaLogic.Formulas.StatsFormula.StatsUsingProgressionIndexFor(
    string unitId,
    bool isMachineOfWar,
    int unitRank,                      // tier 1-17 (Stone1..Adamantium3)
    int progressionIndex,              // **= unitRank** dans le call (NOM TROMPEUR — pas Rarity)
    List<int> indicesOfAppliedUpgradesOfCurrentRank,
    List<IItemModel> items
) -> UnitDynamicStats
```

Call Frida via NativeFunction direct (bypass `il2cpp_runtime_invoke` qui gère mal big struct return) :
```
fn(outBuf48b, statsFormula, idStr, isMow, rank, progIdx, listInt, listItems) -> void
```

`IStatsFormula` instance = `unitProgression.add(0x80).readPointer()`. Concrete class = `StatsFormula`.

### 2. Construction `List<T>` empty propre

```ts
function _createEmptyList(listClass: NativePointer): NativePointer {
    il2cpp_runtime_class_init(listClass);  // ensure cctor
    const obj = il2cpp_object_new(listClass);
    const ctor = findCtorByParamCount(listClass, 1);  // ctor(int capacity)
    invokeMethod(ctor.info, obj, [allocS32(0)]);  // capacity=0
    return obj;
}
```

Classe `List<T>` exacte obtenue via :
```ts
const typePtr = il2cpp_method_get_param(statsForMi.info, paramIdx);
const klass = il2cpp_class_from_type(typePtr);
```

⚠️ **PAS** matérialiser les Lists via game helpers (`GetCappedItemModelsOfUnit(id, invalidRarity)` retourne un objet avec layout corrompu → silent crash).

### 3. Construction `ItemModel` synthétique

```csharp
ItemModel.ctor(ItemConfigId configId, IItemProgression itemProgression, Nullable<Level> levelOverride)
```

- `ItemConfigId` = struct `{ string _value; }` 8 bytes (string ptr at offset 0)
- `IItemProgression` = service à `unitProgression.add(0xD8).readPointer()`
- `Nullable<Level>` = 8 bytes : `hasValue@0x0 (1B) + pad(3B) + val@0x4 (int 4B)`
- `Level` = struct `{ int val; }` 4 bytes

Classe concrète : `IdunMetaLogic.UserProgress.Model.ItemModel` (PAS `IdunMetaLogic.UserProgress.ItemModel` — namespace specific).

### 4. Ajout à `List<IItemModel>`

```ts
const listClass = list.readPointer();
const addMi = findMethodByParamCount(listClass, "Add", 1);
invokeMethod(addMi.info, list, [item]);
```

### 5. Patch metadata progression

Pour chaque unit dans BC.Units[] :
- `Health/Damage/Armor/FixedArmor/CritChance/CritDamage/BlockChance/BlockDamage` ← lus de `outBuf` (UnitDynamicStats 48 bytes)
- `Rank`, `Rarity`, `Level`, `StarLevel` ← écrits depuis `targetXxx`
- `ActiveAbilityLevel`, `PassiveAbilityLevel`, `TertiaryAbilityLevel` ← écrits **inconditionnellement** (`ActiveAbilities[]` vide = pas d'override, le level s'applique aux abilities natives stockées dans `gameConfig.units.lineup[id]`)
- `RemainingHealth = Health` (reset full HP)

## Découvertes critiques

### Levels effectifs vs initialLevel

Le player a 3 items équipés sur Tigurius (tous `initialLevel=4` dans la BC) mais leurs **effectiveLevel** sont différents :
- `I_Booster_Crit_L001` : initialLevel=4, **effectiveLevel=1**
- `I_Defensive_L002` : initialLevel=4, **effectiveLevel=5**
- `I_Crit_E002` : initialLevel=4, **effectiveLevel=1**

`Stats()` utilise `effectiveLevel` (probably issu de `_initialItemLevel + _levelOverride.value` ou similaire). Pour matcher player **exactement**, passer `levelOverride` = effectiveLevel observé.

Validé : avec `[{Booster_Crit:1}, {Defensive:5}, {Crit:1}]`, stats output Tigurius matche player **au bit près** (HP=3467, Crit=40/412, etc.).

### Sémantique `progressionIndex`

Dans la signature C# de `UnitProgression.GetStats(string, int unitProgressionLevel, int rank)` :
- Le nom `unitProgressionLevel` est TROMPEUR
- Au final, **le `progressionIndex` passé au StatsFormula = Rank tier** (1-17), pas une Rarity (0-5)
- Pour Tigurius Legendary Diamond3 : `unitRank=14, progIdx=14` (identiques)

## RPCs exposées

| RPC | Action |
|---|---|
| **`normalizeBcAndBuildRunner(args)`** | **All-in-one**: normalize live BC.Units[] templates + build runner + AddUnitMessage spawn player units. Voir signature ci-dessous. |
| `buildNormalizedBC(args)` | Recalcule stats de tous les units BC + patch metadata (workflow JSON offline) |
| `probeStatsViaFormula(args)` | Test unitaire stats via formula direct (sans items) |
| `dumpListItemsContents({listPtrHex})` | Lecture des items d'une `List<IItemModel>` (configId, initialLevel, levelOverride, effectiveLevel, maxLevel) |
| `installStatsFormulaTrap()` + `getStatsFormulaCaptures()` | Passive trap pour observer les calls naturels du game |
| `applyBattleConfigPatchNow({templateOverrides})` | Mute en mémoire `_currentBattle.Templates[]` |
| `buildPatchedRunner({templateOverrides})` | Apply patch + crée runner isolé |
| `applyAddUnit({runnerId, unitId, playerId, col, row})` | Single-unit spawn via AddUnitMessage |
| `observeBattle({runnerId})` | Liste les units spawned |
| `inspectBattleConfig()` | État du `_currentBattle` |
| `inspectSpawnPoints()` | Détail des SpawnPointSets + groups pour choisir col/row |

### `normalizeBcAndBuildRunner(args)` — signature

```ts
{
    targetRank: number;          // 1-17 (= progressionIndex passé au formula)
    targetRarity?: number;       // 0-5 (Stone..Mythic)
    targetLevel?: number;        // 1-50
    targetStarLevel?: number;
    targetAbilityLevel?: number; // applique aux 3 ability levels
    itemSpecs?: Record<string, Array<{ configId: string; level?: number }>>;
    unitsFilter?: string[];      // whitelist; absent = tous les templates
    playerUnits: Array<{
        unitId: string; playerId: number; col: number; row: number;
    }>;
}
```

Retourne `{ ok, runnerId, runner, seed, bcPtr, normalized[], skipped[], spawned[] }`.

Mute les BC.Units[] templates IN-PLACE (offsets 0x38 Health, 0x50 Damage,
0x48 FixedArmor, 0x60 CritChance, 0x64 CritDamage, 0x68 BlockChance,
0x6C BlockDamage, 0x7C Level, 0x80 Rarity, 0x84 Rank, 0x88 StarLevel,
0xB8/0xBC/0xC0 ability levels, RemainingHealth reset).

## Injection live validée

Confirmation que `templateOverrides` mute bien les `Templates[]` :

| Unit | HP avant | HP après (Mythic R17 baseline) |
|---|---|---|
| ultraTigurius | 3467 | **6525** |
| ultraInceptorSgt | 7758 | **8533** |
| ultraEliminatorSgt | 1754 | **6025** |
| adeptRetributor | 5800 | **7029** |
| ultraApothecary | 6521 | **10038** |

## Limitation actuelle

`Campaign1_64` (résultat de l'amorce) est un **Drafting battle** :
- Les **enemies** spawn auto via `Initialize()` du runner (visibles dans `observeBattle`)
- Les **player units** ne spawn PAS — ils doivent être ajoutés via **`AddUnitMessage`** sent au runner avant `StartBattle`

`AddUnitMessage` (RVA = 0xEFEE60 pour ctor 4-arg) :
```csharp
class AddUnitMessage {
    public string UnitId;                    // 0x10
    public PlayerId PlayerId;                // 0x18
    public List<Position> UnitFeetPositions; // 0x20
    public SpawnSource SpawnSource;          // 0x28
    public BEntityId ParentId;               // 0x2C
    public bool IsBoss;                      // 0x30
    public List<StatModifier> OverrideStats; // 0x38
    public bool ExecuteInPhase;              // 0x40

    .ctor(string unitId, PlayerId playerId, int column, int row);
}
```

Doit être envoyé via `runner.Apply(message)` (pattern similaire à `CheatRunAIMessage` qui existe déjà dans `cheat.ts`).

## Méthodologie crash silencieux validée

Pour les crashs où `il2cpp_runtime_invoke` retourne Frida "system error" SANS qu'aucun hook ne fire :
- `il2cpp_raise_exception` silent (runtime catch internal try/catch)
- `Process.setExceptionHandler` (SEH) silent
- `_CxxThrowException` (ucrtbase) silent
- `Interceptor.attach(KiUserExceptionDispatcher)` → buggy si reading `this.context.rcx` (le trampoline Frida altère les registres)

**Solution validée** : **passive trap** sur la méthode cible (`Interceptor.attach(method.ptr, { onEnter(args) {...} })`) + trigger via cascade naturelle du game (clic sur une battle puis observer ce que le game passe). Capture les args réels du game, compare avec nos inputs → identifier la divergence.

C'est cette méthode qui a débloqué après 5h de tâtonnements et révélé que :
1. `progIdx ≠ Rarity` (était la cause #1 du crash)
2. Les Lists matérialisées via game helpers étaient corrompues (cause #2)

## Fichiers modifiés (non committés)

- `frida/hooks/features/normalize-bc.ts` — main entry (**445 lignes**), wrapper RPC `normalizeBcAndBuildRunner`, register
- **NEW** `frida/hooks/features/normalize-bc/formula.ts` (254 lignes) — `FormulaState`, `resolveFormulaState`, `createEmptyList`, `ensureEmptyLists`, `readUnitDynamicStats`, synthetic `ItemModel` ctor
- **NEW** `frida/hooks/features/normalize-bc/live-bc.ts` (263 lignes) — `UC.*` offsets, `getLiveBC`, `iterTemplates`, `writeTemplateStats/Progression`, `readSpawnPointsForTwpi`, `findHumanPlayerId`, `buildAddUnitMsg`
- **NEW** `frida/hooks/features/normalize-bc/items-catalog.ts` (350 lignes) — Dictionary `_entries` walking, item catalog builder, BiS picker
- **NEW** `frida/hooks/features/normalize-bc/json-build.ts` (175 lignes) — `buildNormalizedBC` JSON workflow (anciennement V2 ; V1 supprimé)
- **NEW** `frida/hooks/features/normalize-bc/debug-rpcs.ts` (340 lignes) — `probeStatsViaFormula`, `probeFindHumanPlayer`, `installStatsFormulaTrap`, `getStatsFormulaCaptures`, `dumpListItemsContents`

**Total**: 1827 lignes réparties sur 6 fichiers focused (vs 2469 monolithique au départ).
**Supprimés**: V1 legacy (GetStats path player-state-dependent) + 12 RPCs debug résidus de l'investigation crash (`listModules`, `findThrowExports`, `listImages`, `listIl2cppExports`, `probeStatsWithSyntheticItems`, `probeStatsRawLists`, `attachThread`, `probeStatsViaDirectCall`, `checkParamTypes`, `testSimpleManagedCall`, `probeExceptionResolution`, `triggerKnownException`).
- `frida/hooks/il2cpp/invoke.ts` — fallback multi-image pour Exception, lecture directe `_message` field
- `frida/hooks/runtime/exception-tracer.ts` — nouveau, hook `il2cpp_raise_exception` + `_CxxThrowException` (ucrtbase)
- `frida/hooks/main.ts` — install exception-tracer
- `frida/dist/hooks.js` — rebuild

## État Tacticus / session au moment du snapshot

- Tacticus running, build hash `rmvdp0v56c`, version 1.39.62
- Session Frida 37 active (peut nécessiter reinject après compact)
- `lastSource._currentBattle` = `Campaign1_64` avec templates patché Mythic R17 (Tigurius HP=6525 etc.)
- Runner #1 créé, observe les enemies necroNpc* (level approprié pour Indomitus 65, non patché car pas dans le filter)

## Prochains steps

| # | Action | Effort | Statut |
|---|---|---|---|
| G | **AddUnitMessage** → spawn player units dans le runner avant StartBattle | 30-60 min | ✅ validé (`applyAddUnit` existait dans `launch.ts`) |
| I | Wrapper RPC tout-en-un `normalizeBcAndBuildRunner(opts)` | 15 min | ✅ validé end-to-end (5 player units Mythic R17 + 10 enemies auto-spawn) |
| H | Auto-BiS via `gameConfig.items` catalog (filtre par slot + faction + rarity cap) | 1-2h | ✅ validé (`autoBis:true` injecte Mythic items max-level; crit 26/3248) |
| J | Auto-pick player spawn coords depuis SpawnPointGroup (TWPI=0/playerIdx=0) — éviter de devoir spec col/row | 30 min | ✅ validé (`playerUnits: ["ultraTigurius", ...]` strings suffisent; playerId auto via FindPlayerConfigByType(Human)) |
| - | Documenter méthodologie debug crash + pipeline normalize dans CLAUDE.md | 30 min | ⏳ après validation totale |

## Validation `normalizeBcAndBuildRunner` (2026-05-23)

Test 1 : 1 unit (Tigurius seul, Mythic R17) → ok, normalized=[Tigurius], spawned=[ok=true],
runnerId=1, HP=6525, Dmg=3011, FixedArmor=1408.

Test 2 : 5 units roster (Tigurius, InceptorSgt, EliminatorSgt, adeptRetributor,
Apothecary) à (col, 0) → 15 units total dans le runner (10 necron AI + 5 player),
toutes stats Mythic R17 attendues écrites. Runner stage=Setup, prêt pour startBattle.

Note : `armor`, `critChance/Damage`, `blockChance/Damage` retournent 0 sans items
(formula sans gear). Pour stats complètes avec items synthétiques, passer
`itemSpecs` (BiS roster TODO H).
