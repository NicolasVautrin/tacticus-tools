# `data/symbols/` — qui ALIMENTE Ghidra, et qui en SORT

Le mot « symboles » désigne ici trois choses différentes, produites par trois outils, et **c'est
leur confusion qui a coûté une journée entière le 2026-07-29**. Ce fichier fixe le sens de
circulation. Il n'y a qu'une règle à retenir :

> **Deux familles ENTRENT dans Ghidra. Une SORT. Elles ne sont pas interchangeables, et la
> sortie ne doit JAMAIS être réinjectée.**

## Le sens de circulation

```
   jeu qui tourne ─┐
                   ├─► dump Frida ──► frida/{methods,classes,enums}.tsv ─┐
                   │                  (VERSIONNÉ ici)                    │
                   │                                                     ├─► [ GHIDRA ]
GameAssembly.dll ──┤                                                     │       │
+ global-metadata ─┴─► Il2CppDumper ─► logs/il2cppdumper/<build>/        │       │
                       (v39)           script.json  (GITIGNORÉ) ─────────┘       │
                                                                                 │
                       ghidra/functions.tsv  ◄──── ghidra_symbols.py dump ◄───────┘
                       (VERSIONNÉ ici)              (lit le SERVEUR ghidra-mcp)
```

### Ce qui ENTRE — deux producteurs, COMPLÉMENTAIRES

| fichier | produit par | appliqué par | ce qu'il apporte |
|---|---|---|---|
| `frida/methods.tsv`<br>`frida/classes.tsv`<br>`frida/enums.tsv` | `preprocess_il2cpp_dump.py` depuis un dump Frida du **jeu qui tourne** | `scripts/ghidra/GhidraApplyIl2CppSymbols.java` | **~171 000 noms ET les STRUCTS.** C'est le seul producteur de types : le binaire IL2CPP est strippé, Ghidra ne peut PAS retrouver seul la disposition d'un type C#. Une structure fausse ici devient une structure fausse dans tout le décompilé. |
| `logs/il2cppdumper/<build>/script.json` | `tools/Il2CppDumper_v39/.../Il2CppDumper.exe` depuis le **binaire sur disque** | `scripts/ghidra/GhidraApplyIl2CppDumperNames.java` | **~5 900 noms de plus, et EUX SEULS** : les corps génériques *pleinement partagés* (`__Il2CppFullySharedGeneric`), que les métadonnées lues par Frida n'exposent pas comme méthodes distinctes. |

**ORDRE OBLIGATOIRE : Frida d'abord, Il2CppDumper ensuite.** Le second ne renomme QUE les fonctions
encore appelées `FUN_*` — il ne peut donc pas écraser le premier. Mesure du 2026-07-29 :
`applied=5899`, `alreadyNamed=171057`, `refused=0`.

**Aucun des deux ne remplace l'autre**, et c'est mesuré, pas supposé : la chaîne Frida nomme
**3 165 adresses** que le dumper laisse anonymes ; le dumper nomme **4 882 corps partagés** que
Frida ne voit pas. Supprimer l'un perd ce que l'autre ne couvre pas.

⚠ `script.json` vit dans `logs/` (**gitignoré**, 84 Mo) : un clone frais ne peut pas ré-appliquer
ces noms sans relancer Il2CppDumper. Les TSV Frida, eux, sont versionnés ici.

### Ce qui SORT — un extrait, jamais une entrée

`ghidra/functions.tsv` est produit par `ghidra_symbols.py dump`, **qui lit le serveur `ghidra-mcp`,
pas le `.gpr`**. C'est un **instantané** de l'état de Ghidra, enrichi de ce que Ghidra seul possède :
les **frontières de fonctions** (Frida ne connaît que les points d'entrée — c'est ce qui permet
d'écrire `<symbole>+0x<offset>`).

Il est consommé par nos outils offline (`whereis`, les sondes, l'axe 5 de `symbols_sync.py`) et
**par personne d'autre**. Il n'est jamais réinjecté dans Ghidra.

**Corollaire, et c'est le piège du 2026-07-29** : appliquer des noms dans Ghidra sans relancer
`dump` laisse cet extrait périmé. Les deux consommateurs du projet se mettent alors à se
contredire — un agent interrogeant `mcp__ghidra__*` voit les nouveaux noms pendant que les outils
offline lisent les anciens. Deux réponses plausibles séparément, incohérentes ensemble.

## La forme `$$` et les `u003C` viennent d'Il2CppDumper

`Classe$$Membre`, avec `u003C` pour `<` et `u003E` pour `>`, est la convention **native
d'Il2CppDumper** — son parseur consomme le backslash des séquences d'échappement JSON et recopie
le reste tel quel. Tout le dépôt cite ses symboles sous cette forme.

La chaîne Frida, elle, rend une notation **pointée** (`Classe.Membre`).
`GhidraApplyIl2CppSymbols.canonicalName()` la **reconstruit** en `$$` par concaténation, pour que
les deux producteurs parlent la même langue. C'est une imitation, écrite le 2026-07-29 après que
la suppression de l'applier legacy eut fait tomber la résolution des citations à **0 sur 1 266**.

## Ce que le versionnement veut dire

`data/symbols/` est la **seule exception versionnée** de `data/`. Son diff **EST** le rapport de
changement du jeu : ce qui apparaît, disparaît ou se renomme entre deux builds est exactement ce
que la mise à jour a touché. Ne pas le commiter, c'est perdre le seul moyen de savoir ce qui a bougé.

`CURRENT` est un fichier texte contenant le hash du build courant. Il fait autorité pour tout le
monde : les outils offline, le lanceur de `ghidra-mcp`, et les appliers.

## Après une mise à jour du jeu

Procédure complète (durées mesurées incluses) : skill `tacticus-orchestration`, section
« Au changement de build du jeu ». Gardes à passer : `python scripts/python/symbols_sync.py`
(5 axes) et `python scripts/python/probe_257_scorer_rva_migration.py`.
