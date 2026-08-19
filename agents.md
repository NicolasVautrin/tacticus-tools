# tacticus-tools - Instructions pour les Agents IA

Bienvenue sur le projet `tacticus-tools`. Ce document contient les règles critiques, le contexte technique et les workflows nécessaires pour manipuler ce repo de manière sécurisée et efficace.

## Identité du Projet
Hooking Frida de **WH40K Tacticus** (Windows PC build, Unity 6 IL2CPP) — Monorepo TypeScript.
- **Host** : Serveur Node.js (Express + WS) pilotant les sessions Frida.
- **Hooks** : Scripts TypeScript injectés dans le processus Unity.
- **Frontend** : Interface web de pilotage.

## ⚠️ RÈGLES D'OR (NE JAMAIS DÉROGER)

### 1. Résolution Runtime obligatoire (Pas de RVAs)
**Tout hook doit résoudre son point d'entrée dynamiquement** via les helpers IL2CPP.
- Utiliser `findClassAnywhere` et `findMethod` (dans `helpers.ts`).
- **INTERDICTION** d'utiliser des adresses mémoires (RVAs) hardcodées. Elles changent à chaque mise à jour du jeu.
- Si une méthode n'est pas trouvée, c'est un problème d'indexation IL2CPP à investiguer, pas une raison pour utiliser une RVA offline.

### 2. Le Piège du "Hash de Build"
Le jeu est stocké dans un dossier dont le nom est un `<HASH>` (ex: `nb3o9lmt6c`).
- Ce hash **change à chaque mise à jour**.
- Avant toute analyse offline (Ghidra, Dumps), **VÉRIFIER** que le hash du build courant match le hash du dump dans `data/dumps/<HASH>/`.
- En cas de désynchro, refuser l'analyse et demander un re-dump.

### 3. Stabilité & Performance (Frida)
- **UnityFreezeDetector** : Le jeu possède un watchdog qui tue le process si le thread principal est figé trop longtemps.
- **Heap Scans** : Interdiction de lancer des scans mémoire automatiques (`Process.enumerateRanges`). Ils doivent être déclenchés uniquement par action utilisateur explicite (`allowHeapScan: true`).
- **Hot Paths** : Ne jamais hooker de manière permanente des getters de propriétés appelés massivement (ex: par Newtonsoft lors de la sérialisation), sous peine de crash immédiat (27 000 appels/s).

## Workflows Standards

### Démarrage du projet
```bash
cd frida && npm run dev
```
- Host sur `http://127.0.0.1:8765`.
- Front sur `http://127.0.0.1:8765/view/`.

### Cycle d'Injection
1. Lancer Tacticus, attendre le menu principal.
2. Cliquer **INJECT** dans l'UI Web.
3. **Amorce** : Cliquer sur un battle de campagne en jeu pour capturer les sources (`lastSource`, `Universe`, etc.).

### Build des Hooks
Si tu modifies le code dans `frida/hooks/` :
```bash
cd frida && npm run build:hooks
```

## Structure & Connaissances
Les détails techniques approfondis sont situés dans le dossier `docs/ai/` :

- [Architecture Frida & Host](file:///C:/Users/nicolasv/tacticus-tools/docs/ai/frida-host.md)
- [Fonctionnement des Hooks](file:///C:/Users/nicolasv/tacticus-tools/docs/ai/hooks.md)
- [Référence API RPC](file:///C:/Users/nicolasv/tacticus-tools/docs/ai/rpc-api.md)
- [Connaissance du Jeu (Tacticus)](file:///C:/Users/nicolasv/tacticus-tools/docs/ai/knowledge.md)
- [Architecture Interne Unity/Game](file:///C:/Users/nicolasv/tacticus-tools/docs/ai/game-architecture.md)
- [Décompilation & Ghidra](file:///C:/Users/nicolasv/tacticus-tools/docs/ai/decompilation.md)
- [Audit Engine IA](file:///C:/Users/nicolasv/tacticus-tools/docs/ai/ai-engine-audit.md)
