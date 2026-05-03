# Decompilation Ghidra + transpilation Java

## Tacticus Windows PC (pipeline actif)

Cible : `GameAssembly.dll` (x86_64, ~60 MB) à
`C:\Users\nicolasv\AppData\Local\tacticus\games\nb3o9lmt6c\GameAssembly.dll`.

Scripts dédiés Windows :
- `scripts/ghidra/GhidraApplyIl2CppNamesWin.java` — apply symbols + void* sigs
- `scripts/ghidra/GhidraDecompileGameAssembly.java` — full batch decompile
- `scripts/ghidra/GhidraDecompileCampaignBuilder.java` — ciblé sur le code campaign builder
- `scripts/ghidra/GhidraDecompileCrashSite.java` — décompile autour d'un RVA donné (diagnostic)
- `scripts/python/gen_full_game_targets.py` / `gen_win_targets.py` — listes de targets par RVA
- `scripts/python/gen_campaign_builder_targets.py` — focus campaign code
- `scripts/python/rebuild_sources_win.py` — réassemble les .c sous `sources_win/`

Outputs sous `sources_win/` (gitignored, plusieurs GB).

Notes spécifiques x86_64 vs ARM64 :
- Calling convention différente (RCX/RDX/R8/R9 + stack vs X0..X7)
- HFA (homogeneous float aggregate) sur ARM64 ne s'applique pas à x86_64
  (vector types passent dans XMM)
- Les RVA de cellules PTR_DAT diffèrent entre les builds Android et PC
- Image base Ghidra = 0 reste valide

---

## Historique : Tacticus Android (libil2cpp.so, ARM64)

Pipeline original sur le build mobile. Conservé pour référence
historique — concepts (void* sigs, PTR_DAT, transpilateur) restent
valables pour le port PC ci-dessus.

```
1. Frida dump IL2CPP runtime
   → data/il2cpp_full.json (169k methodes, 30k classes avec kp/mp pointeurs runtime)

2. Frida scan memoire .data de libil2cpp.so
   → data/ptr_dat_map.json (5924 cellules PTR_DAT resolues en class/method)

3. Ghidra Apply Symbols (void* signatures)
   → data/ghidra_tacticus/ : 30k fonctions renommees, signatures {void* params, undefined8 return}

4. Ghidra Decompile batch (16 threads, 120s timeout, 0% fail attendu)
   → data/decompiled_tacticus/ (3982 fichiers .c groupes par top-level class)

5. Transpileur Python (package modulaire scripts/python/transpile/)
   → data/transpiled_tacticus/ (hiearchy Java complete)
```

## Principes cles

### Image base Ghidra = 0

Les RVA du dump Frida, du binaire ELF et des adresses Ghidra sont **alignes** (pas d'offset `0x100000` comme dans l'ancien pipeline). `FUN_01c21420` dans le C decompile = RVA 0x01c21420 = offset 0x01c21420 dans `libil2cpp.so`.

### void* signatures partout (decouverte cle)

Ghidra diverge sur les signatures typees quand :
- La fonction a > 8 params (premier stack-spill sur ARM64)
- Le `this` pointe sur une struct "vide-mais-grosse" (classe heritant tout du parent, size > 0 fields=[])
- Presence de generiques imbriques dans les params

**Solution** : appliquer `void*` a TOUS les params et `undefined8` au return. Le calling convention ARM64 reste correct, les noms de params restent, mais la propagation inter-procedurale de types est desactivee → 100% de convergence.

Validation : 6/6 methodes "irrecuperables" en typed passent en void* a 120s.

### PTR_DAT / DAT_ = pointeurs runtime

Les `PTR_DAT_xxxxxxxx` et `DAT_xxxxxxxx` dans les .c sont des cellules de la `.data` section de libil2cpp.so que le runtime IL2CPP remplit a l'init avec des `Il2CppClass*` ou `MethodInfo*` heap-allocated. `scan-ptr-dat.js` lit ces cellules au runtime et produit un mapping offset → nom C#.

Couverture : ~5924 classes/methods, ~40% des PTR_DAT observees. Le reste (type descriptors internes, metadata tagges) ne se resout pas directement via heap pointer matching.

## Installation

- Ghidra 12.0.4 : `C:/Users/nicolasv/ghidra_12.0.4_PUBLIC/`
- JDK 21 : `C:/Program Files/Eclipse Adoptium/jdk-21.0.9.10-hotspot`
- **MAXMEM = 16G** dans `analyzeHeadless.bat` (etait 2G par defaut → OOM sur decompile volume)

## Donnees d'entree

| Fichier | Description | Origine |
|---------|-------------|---------|
| `data/libil2cpp.so` | Binaire ARM64 (~76 MB) | `adb pull` depuis l'APK |
| `data/il2cpp_full.json` | Dump complet : 169k methodes + 30k classes + enums + `kp`/`mp` runtime ptrs | `hooks/_oneshot/dump-il2cpp-full.js` via Frida |
| `data/ptr_dat_map.json` | 5924 cellules PTR_DAT resolues | `hooks/_oneshot/scan-ptr-dat.js` |
| `data/all_battlelogic_targets.tsv` | Liste `top_class_fs_path \t method_fqn \t rva_hex` pour le batch | `scripts/python/gen_battlelogic_targets.py` |

## Scripts Ghidra (`scripts/ghidra/`)

| Script | Role | Quand lancer |
|--------|------|--------------|
| `GhidraApplyIl2CppSymbols.java` | Cree structs + applique noms + signatures **void*** | 1x apres dump Frida frais (~30 s) |
| `GhidraDecompileBattleLogicParallel.java` | Decompile batch 16 threads, 120s timeout, sortie groupee par top-level class | Apres apply (~1-2 h) |
| `GhidraTestUntypedDecompile.java` | Test diagnostique : strip signature + decompile (preuve que types causent les hangs) | Sur besoin |
| `GhidraTestVoidStarSigs.java` | Test : retype params en void* + decompile | Sur besoin |
| `GhidraTestTimeout120.java` | Test : relance methodes failed avec timeout 120s | Sur besoin |

## Scripts Python (`scripts/python/`)

| Script | Role |
|--------|------|
| `gen_battlelogic_targets.py` | Lit `il2cpp_full.json` → `all_battlelogic_targets.tsv` (groupage top-level class via declaring chain) |
| `preprocess_il2cpp_dump.py` | `il2cpp_full.json` → TSV (methods/classes/enums) pour lookup rapide |
| `extract_failed_targets.py` | Parse decompiled_tacticus/ → `data/failed_targets.tsv` (pour 2e passe ciblee si besoin) |
| `transpile_v2.py` | Shim CLI → `transpile/cli.py` |

## Transpileur `scripts/python/transpile/` (package modulaire)

| Module | LOC | Role |
|--------|----:|------|
| `paths.py` | 9 | Constantes chemins |
| `naming.py` | 128 | camelCase, mots-cles Java, generiques, backing fields |
| `mapping.py` | 200 | Classe Mapping (csharp↔java tables + il2cpp index + ptr_dat) |
| `parser.py` | 151 | tree-sitter, Method, parse_file, declarators |
| `walker.py` | 712 | AST → corps Java (plus gros module) |
| `emitter.py` | 213 | emit_class / emit_method / emit_stub |
| `cli.py` | 124 | main, run_batch, worker pool |

### Features transpileur

- **Signature Java** depuis `il2cpp_methods.tsv` (vrais types C#, pas `Object` void*)
- **Register alias ARM64** : `unaff_x19` → `this`, `unaff_x20` → premier param explicite, etc.
- **Field resolver** : `*(T*)(this + 0x28)` → `this.dsl` via `il2cpp_classes[fqn].fields[offset]`
  - Couvre aussi : `(base + off).method()` → `base.fieldName.method()`, `base[N]` → `base.fieldAtN*8`
- **PTR_DAT safety** : `PTR_DAT_xxx` / `DAT_xxx` → `null /* class|method ref: Full.Name */` (Java compile toujours)
- **`this =` safety** : assignment a `this` commented-out (Java interdit)

## Commandes types

### Re-apply + re-decompile complet

```bash
# 1. Re-apply symbols (void*)
JAVA_HOME="C:/Program Files/Eclipse Adoptium/jdk-21.0.9.10-hotspot" \
"C:/Users/nicolasv/ghidra_12.0.4_PUBLIC/support/analyzeHeadless.bat" \
  data/ghidra_tacticus tacticus \
  -process libil2cpp.so -noanalysis \
  -scriptPath scripts/ghidra \
  -postScript GhidraApplyIl2CppSymbols.java

# 2. Re-decompile
rm -rf data/decompiled_tacticus && mkdir data/decompiled_tacticus
JAVA_HOME="C:/Program Files/Eclipse Adoptium/jdk-21.0.9.10-hotspot" \
"C:/Users/nicolasv/ghidra_12.0.4_PUBLIC/support/analyzeHeadless.bat" \
  data/ghidra_tacticus tacticus \
  -process libil2cpp.so -noanalysis \
  -scriptPath scripts/ghidra \
  -postScript GhidraDecompileBattleLogicParallel.java
```

### Transpile

```bash
# Un seul fichier pour debug
python scripts/python/transpile_v2.py one data/decompiled_tacticus/IdunBattle/Entities/Components/ActiveAbility.c

# Batch complet (16 workers)
python scripts/python/transpile_v2.py batch
```

### Frida dumps

```bash
cd server
# Dump metadata il2cpp complet
PID=12345
node -e "
const fs=require('fs');
const source=fs.readFileSync('../hooks/_oneshot/dump-il2cpp-full.js','utf-8');
fs.writeFileSync('C:/tmp/inject.json', JSON.stringify({serial:'f32224e7',mode:'attach',pid:$PID,source,log_dir:'logs'}));
"
curl -s -X POST http://127.0.0.1:8765/api/scripts/run -H "Content-Type: application/json" -d @C:/tmp/inject.json
```

## Symboles non resolus restants

| Pattern | Signification | Sort |
|---------|---------------|------|
| `FUN_xxxxxxxx` | Fonction runtime IL2CPP ou generique non dumpee | Laisse en commentaire TODO |
| `thunk_FUN_xxx` | Trampoline vers fonction IL2CPP | Laisse en commentaire TODO |
| `PTR_DAT_xxxxxxxx` | Cellule data section (hors scope Frida scan) | `null /* unresolved ... */` |
| `DAT_xxxxxxxx` | Idem variant | `null /* unresolved ... */` |
| `unaff_xN` (N > 19+params) | Registre callee-saved sans alias | `// synthetic` comment |

## Metriques cibles

- **Decompile** : < 1 % TIMEOUT/NULL sur 30443 cibles (void*, timeout 120s). 99 %+ de recuperation vs 91 % avec typed.
- **Transpile** : 0 erreur syntaxe Java, 3982 fichiers .java (parite avec .c)
- **FUN_ unique restants** : ~1500 apres pipeline (runtime IL2CPP + generic instantiations non-dumpees — acceptable)

## Historique des approches

Les approches suivantes ont ete testees puis abandonnees :
- **Signatures typees (typed class*/interface\* params)** : ~2648 timeouts sur 30443 (8,7 %)
- **Fallback `normalize` simplification style** : 0 recuperation en 20s (pas efficace)
- **Fallback `paramid`** : pas teste, mais meme pathologie attendue (garde les types)
- **Flatten parent fields dans child struct** : n'aide pas (pas le probleme de Ghidra)
- **Composition (parent embedded at offset 0)** : idem

La **void\*** approche est le premier fix qui fait converger 100 % des cas.

## Backups

- `data/ghidra_tacticus_typed_backup/` — etat du projet avec signatures typees (4GB, gardons en cas de regression)
- `data/ghidra_tacticus_untyped/` — projet duplique utilise pour tests (dirty, peut etre supprime)