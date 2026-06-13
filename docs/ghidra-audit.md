# Audit projet — leviers d'amélioration via le serveur ghidra-mcp

> Date : 2026-06-13 · Binaire analysé : `GameAssembly.dll` build **kqkbjqfb6c**
> (= build courant du jeu, pas de désync). `analysis_complete: true`, ~121k
> fonctions renommées en noms C#. Audit centré sur : **où le projet fait du
> runtime-discovery / heap-scan / devinette que Ghidra résout statiquement.**

## Ce que Ghidra apporte (validé en live)

| Capacité | Outil MCP | Validé sur |
|---|---|---|
| Catalogue classes/méthodes par nom | `search_symbols_by_name` | ~50 classes `IdunBattle.AI.Utilities.*Utility`, `OverwatchAutoAttackAbility`, `TriggeredAbilitiesNonOwnerUtility` |
| Code décompilé + offsets de champs | `decompile_function` | `TriggeredAbilitiesNonOwnerUtility$$IsInvalidEntityForPlaybook` (appelle `UnitExtensions.IsFriend`, offsets `+0x10`) |
| Qui appelle quoi | `list_xrefs` | xrefs DATA sur le playbook filter |
| Graphe d'appels | `gen_callgraph` | — |

**Limite actuelle** : `code_indexed:false` / `strings_indexed:false` → la
recherche **sémantique** (`search_code`, `search_strings`) est vide tant que
l'index ChromaDB n'est pas construit. Les 4 outils ci-dessus marchent direct
sur le programme analysé (pas besoin d'index). → *Action : lancer la
construction d'index si on veut la recherche sémantique.*

## Opportunités priorisées

### P1 — Retirer/recadrer les ~70 probes `scratch/` → découverte statique
`frida/hooks/scratch/` = ~70 scripts `dump-*` / `find-*` / `check-*` /
`inspect-*` qui découvrent **layout de structs, offsets de champs, signatures
de méthodes** en injectant une probe live + en cliquant une battle.

- **Tout ça est désormais une requête Ghidra** : `decompile_function` donne le
  corps + les offsets, `search_symbols_by_name` donne la signature exacte.
- **Bénéfices** : zéro inject, zéro clic battle, **zéro risque de
  déstabilisation IL2CPP** (cf. règle « no broad-hooks / no heap scan »),
  répétable, instantané.
- **Garder en `scratch/` uniquement** ce qui a besoin de **valeurs runtime**
  (état heap réel), pas du **layout/signature** (→ Ghidra).

### P2 — Modèle de scoring AI : carte statique complète (objectif n°1 du projet)
`features/ai-utility-trace.ts` (1040 lignes) trace les utilities **au runtime**,
découverte au fil de l'eau. Ghidra énumère les **~50 `*Utility` d'un coup** et
décompile leurs méthodes de calcul **offline** :

- Catalogue exhaustif des entrées de scoring (vs. trace partielle).
- **Blind-spot overwatch** : décompiler
  `TriggeredAbilitiesNonOwnerUtility$$EvaluateMovementInSteps` (RVA `181185b20`)
  + son `MoveNext` (`18118a5e0`) montre **pourquoi** l'AI ne pénalise pas un
  déplacement dans la portée overwatch — confirmer le trou **dans le code**,
  pas par hooking à l'aveugle.
- `gen_callgraph` depuis l'entrée de décision AI → liste **tous** les utilities
  qui alimentent un choix de déplacement → hooks **ciblés et minimaux** au lieu
  d'un tracing large (qui est justement interdit sur les hot paths).

### P3 — Root-cause des crashs (0x2c, AutoTestFactory Zenject) — plus haut levier
La mémoire projet documente ces sujets comme **mystères runtime-only**
(métadonnée IL2CPP non initialisée, `TypeDefIndex 0x2c`, factory Zenject jamais
instanciée) — « plusieurs heures de debug », « no offline solution ».

- Ghidra peut décompiler le **chemin d'init de classe IL2CPP / cctor** et le
  **binding Zenject de la factory** pour voir exactement ce qui déclenche
  l'init → transformer « exhausted » en réponse niveau code.
- C'est l'usage à plus fort ROI : ces blocages ont coûté le plus de temps.

### P4 — Offsets de struct hardcodés → vérifiés par Ghidra
La règle « pas de RVA hardcodée » est **respectée** (grep `il2cppBase.add(0x` /
`RVA_` = 0 hit). MAIS il reste des **offsets de layout** inline :
`ai-trace/ai-control.ts:37` (`base.add(0x4)` col/row),
`ai-trace/state.ts:243-253` (`+0x4/+0x8/+0xC/+0x10/+0x14`), lecture System.String
`+0x14` un peu partout. Ce ne sont pas des RVA, mais ce sont des **hypothèses de
layout** qui cassent silencieusement au changement de build.
→ `decompile_function` permet de **vérifier/regénérer** ces offsets par build
(effort faible, évite la corruption silencieuse).

### P5 — Tables de noms : Ghidra comme source de validation
`data/ability-names.ts` (336) + `data/triggered-ability-names.ts` (567) sont
« auto-generated from sources_win … Regenerate when GameAssembly.dll is updated »
→ étape **manuelle par build**. Câbler `search_symbols_by_name` sur l'enum comme
**cross-check** que la regen colle au binaire actif → attrape la classe de bug
« désync de hash » que le CLAUDE.md décrit.

## Findings d'hygiène projet (connexes, hors-Ghidra)

1. **`!include` cassés dans CLAUDE.md** : les 7 docs référencés
   (`.claude/skills/tacticus/references/*.md`) **n'existent pas** dans l'arbre
   principal — ils sont dans `docs/ai/` (2) et dans des worktrees agent
   périmés. Les includes résolvent silencieusement à vide → cette doc
   **n'atteint jamais le contexte**. *Corriger les chemins ou rapatrier.*
2. **Worktrees agent périmés** : `.claude/worktrees/agent-*` contiennent des
   copies dupliquées des docs de référence → candidats au nettoyage.
3. **Index sémantique Ghidra non construit** (cf. limite ci-dessus).

## Workflow « refresh Ghidra par build » à formaliser
Au changement de hash : le pipeline dump→analyse→symbolize existe déjà. Ajouter :
(re)pointer le MCP sur le nouveau `.gpr` (fait), reconstruire l'index ChromaDB,
regénérer les tables de noms, re-vérifier les offsets de struct. Le MCP rend la
vérif « ce hook target existe-t-il dans le binaire actif ? » = **1 appel** →
adresse directement le footgun de désync décrit dans le CLAUDE.md.
