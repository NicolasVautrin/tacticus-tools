# `frida/hooks/probes/` — sondes d'introspection IL2CPP

**Code de production, versionné, embarqué dans le bundle injecté.** 66 de ces modules sont
dans `dist/hooks.js` ; ils sont atteignables depuis `hooks/main.ts` via `hooks/controller.ts`.
Ce répertoire s'appelait `scratch/` jusqu'au 2026-08-05 (#480-r6) — un nom qui le déclarait
jetable et faisait écarter son code des périmètres d'audit.

## Ce qu'est une sonde

Un module qui **lit la disposition mémoire du build** — champs, offsets, méthodes, types,
instances — et l'imprime. Exposée en RPC, appelée **à la main** quand on rétro-ingénie une
structure. Une sonde :

- **n'arme aucun `Interceptor`** et ne pose aucun hook permanent ;
- **n'a pas d'appelant automatique** : son absence dans `scripts/python/` est sa nature, pas sa
  mort (mesuré #480-r6 : 155 des 321 RPC du bundle n'ont aucun appelant, l'essentiel étant ces
  sondes) ;
- **est jetée après usage par le lecteur, pas par le dépôt** : le coût de la garder est nul,
  celui de la réécrire ne l'est pas.

C'est ce qui la distingue d'une `features/` — laquelle s'enregistre pour **observer en continu**
(traces, capteurs d'état, pilotage de runner).

## Nommage

Le verbe dit ce que la sonde fait, le complément dit sur quoi :
`dump-*` (imprimer une disposition), `check-*` (vérifier une hypothèse ponctuelle),
`find-*` (localiser une classe ou une instance), `inspect-*`, `search-*`, `test-*`.

## Conventions

- Résolution **runtime** via `../il2cpp/helpers.js` — aucune RVA en dur (règle du `CLAUDE.md`).
- Le RPC est câblé dans `hooks/controller.ts`, qui importe le symbole exporté.
- ⚠ `find-prog-instances.ts` fait un **heap scan** (`Process.enumerateRanges` + `Memory.scanSync`).
  C'est conforme *parce que* l'appel est on-demand ; ne jamais l'appeler depuis un chemin
  automatique — Frida suspend les threads pendant le scan.
