# Decompilation Ghidra

## Installation

- Ghidra 12.0.4 : `C:/Users/nicolasv/ghidra_12.0.4_PUBLIC/`
- JDK 21 : `C:/Program Files/Eclipse Adoptium/jdk-21.0.9.10-hotspot`
- Projet : `data/ghidra_tacticus/` (1.8 GB, 49625 fonctions renommees)
- Image base Ghidra : `0x100000`

## Referentiels d'adresses

| Contexte | Base | Exemple (IdunRunner.Initialize) |
|----------|------|------|
| Sources enrichies (RVA) | `0x0` | `0x29384F4` |
| Ghidra | `0x100000` | `0x29484F4` |
| Runtime Frida | `il2cppBase` (ASLR) | `il2cppBase + 0x29384F4` |

Conversions :
- Source RVA → Ghidra : `+ 0x100000`
- Ghidra → Source RVA : `- 0x100000`
- Source RVA → Runtime : `il2cppBase + RVA`
- Ghidra → Runtime : `il2cppBase + (ghidraAddr - 0x100000)`

## Donnees d'entree

| Fichier | Description |
|---------|-------------|
| `data/libil2cpp.so` | Binaire ARM64 (73 MB), extrait du device |
| `data/symbols.json` | 168K methodes + 2015 enums + fields (dump IL2CPP runtime) |
| `sources/**/*.cs` | 9600+ fichiers C# enrichis (voir ci-dessous) |

## sources/ — stubs C# enrichis

Repertoire gitignored contenant les stubs de toutes les classes C# du jeu, enrichis avec les offsets de champs et les RVA des methodes.

### Contenu

- 9600+ fichiers `.cs` organises par assembly et namespace
- Chaque fichier = une classe avec ses champs, methodes (signatures uniquement, pas de corps)
- Annotations ajoutees : `// 0xNN` sur les champs (offset memoire), `// RVA: 0xNNNN` sur les methodes

### Exemple

```csharp
namespace IdunBattle.Configuration
{
    public class UnitConfiguration
    {
        public System.String Id; // 0x10
        public System.Int32 Health; // 0x30
        public System.Int32 Damage; // 0x48
        public System.Void .ctor() { }
        public System.Int32 GetMaxAmountOfUnitsToBring(...) { } // RVA: 0x2BEE2E8
    }
}
```

### Generation

1. **Dump initial** : il2cppdumper ou outil similaire → stubs `.cs` bruts (signatures sans offsets)
2. **Dump des symboles** : `hooks/_oneshot/dump-symbols.js` via Frida → `data/symbols.json` (fields avec offsets, methods avec RVA)
3. **Enrichissement** : `scripts/python/enrich-sources.py` lit `symbols.json` et annote les `.cs` avec les offsets et RVA

### Arborescence

```
sources/
├── Assembly-CSharp/          # Code du jeu (Snowprint)
│   ├── Thor/                 # Namespace thor (menus, settings, UI)
│   ├── Idun/                 # Namespace idun (meta, combat view, UI)
│   ├── Runner/               # AutomaticBattleRunner, ValidationResult
│   └── ...
├── BattleLogicAssembly/      # Moteur de combat pur (pas de Unity)
│   ├── IdunBattle/           # Core ECS, config, messages, AI, operations
│   └── IdunBattleLogic/      # Replay, validation, AI utilities
├── MetaLogicAssembly/        # Logique meta (progression, DTOs, configs)
└── ClientSdk/                # SDK client Snowprint
```

### Usage

- **Lecture** : comprendre la structure des classes, les types des champs, les signatures de methodes
- **Offsets** : pour lire/ecrire des champs en memoire via Frida (`ptr.add(0x30).readS32()`)
- **RVA** : pour hooker des methodes (`Interceptor.attach(il2cppBase.add(0x29384F4), ...)`)
- **Renommage Ghidra** : `GhidraRename.java` lit les RVA des sources pour renommer les fonctions

## Contenu de data/

### Sources binaires

| Fichier | Description | Origine |
|---------|-------------|---------|
| `libil2cpp.so` | ARM64 (73 MB) | `adb pull` du device (APK) |
| `symbols.json` | 168K methodes + 2015 enums + fields | `hooks/_oneshot/dump-symbols.js` via Frida runtime |

### Donnees de jeu

| Fichier | Description | Origine |
|---------|-------------|---------|
| `gameconfig-abilities.json` | 599 configs abilities | Capture Frida (autoplay hooks) |
| `gameconfig-units.json` | 117 unites | Capture Frida |
| `gameconfig-summons.json` | 55 summons | Capture Frida |
| `i2_en.json` | 17810 termes localisation I2 | Capture Frida |

### Decompilation

| Fichier/Dossier | Description | Genere par |
|-----------------|-------------|------------|
| `ghidra_tacticus/` | Projet Ghidra (1.8 GB), 49625 fonctions renommees | `GhidraRename.java` |
| `decompiled_tacticus/` | 1065 fichiers C decompiles (5.9 MB) | `GhidraDecompileAI.java` + `GhidraDecompileAICore.java` |
| `ai_targets.json` | RVAs des 1878 methodes IA | `scripts/gen_ai_targets.py` |
| `ai_coroutine_targets.json` | RVAs coroutines + playbook core (97) | Manuel + merge dans gen script |
| `resolved_symbols.json` | Mapping FUN_xxx → noms (76 C# + runtime connus) | `scripts/gen_ai_targets.py` (offline) + constantes runtime |

### Combats headless

| Fichier | Description | Genere par |
|---------|-------------|------------|
| `arena-battle-config-newtonsoft.json` | Config PvP capturee (525 KB, Newtonsoft natif) | `hooks/_oneshot/capture-battle-config.js` |
| `headless-battle-result.json` | Resultat simulation (1.4 MB) | `hooks/_oneshot/run-headless-battle.js` |

## Scripts Ghidra (Java, dans scripts/ghidra/)

| Script | Role |
|--------|------|
| `GhidraRename.java` | Renomme les fonctions depuis les sources enrichies (49625 methodes) |
| `GhidraDecompile.java` | Decompile des methodes ciblees par RVA + analyse call sites (XREF) |
| `GhidraDecompileAI.java` | Batch — lit `data/ai_targets.json`, ecrit dans `data/decompiled_tacticus/` |
| `GhidraDecompileAICore.java` | Idem pour coroutines — lit `data/ai_coroutine_targets.json`, append |

## Generateurs de cibles (Python, dans scripts/python/)

| Script | Role |
|--------|------|
| `gen_ai_targets.py` | Genere `data/ai_targets.json` depuis `symbols.json` |
| `enrich-sources.py` | Enrichit les `.cs` avec offsets de champs et RVA |
| `rebuild-i2-lookup.py` | Reconstruit le lookup I2 localisation |

## Commande type

```bash
JAVA_HOME="C:/Program Files/Eclipse Adoptium/jdk-21.0.9.10-hotspot" \
"C:/Users/nicolasv/ghidra_12.0.4_PUBLIC/support/analyzeHeadless.bat" \
  "C:/Users/nicolasv/tacticus-tools/data/ghidra_tacticus" tacticus \
  -process libil2cpp.so -noanalysis \
  -scriptPath "C:/Users/nicolasv/tacticus-tools/scripts/ghidra" \
  -postScript GhidraRename.java \
  -postScript GhidraDecompileAI.java
```

- `-process` : reutilise le projet existant
- `-noanalysis` : skip l'analyse (deja faite, 30 min)
- `-postScript` : enchaine plusieurs scripts

## Decompiler de nouvelles methodes

1. Trouver les RVAs dans les sources (`// RVA: 0x...`) ou `symbols.json`
2. Ecrire un JSON de cibles : `{"NomMethode": rva_int, ...}`
3. Pointer un script Ghidra vers ce JSON
4. Lancer headless avec `-noanalysis -postScript`
5. Post-traitement : appliquer `data/resolved_symbols.json` (search/replace FUN_ → noms)

## Symboles non resolus dans le code decompile

| Pattern | Signification |
|---------|---------------|
| `FUN_xxxxxxxx` | Fonction runtime IL2CPP ou generique (List, Dict) |
| `PTR_DAT_xxxxxxxx` | Pointeur vers metadonnees de type (Il2CppClass*) |
| `DAT_xxxxxxxx` | Flag d'initialisation statique |
| `thunk_FUN_xxx` | Trampoline vers une autre fonction |

Runtime connus (deja remplaces dans `decompiled_tacticus/`) :
- `il2cpp_runtime_class_init`, `il2cpp_raise_null_reference`, `il2cpp_object_new_checked`
- `il2cpp_resolve_interface_method`, `il2cpp_codegen_no_return`

Les `PTR_DAT_` ne sont resolvables qu'au runtime (Frida) — crash le jeu (segfault). Les generiques (`List<T>.Add`, etc.) ne sont pas dans `symbols.json`.