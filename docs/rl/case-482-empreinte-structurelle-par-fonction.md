# case-482 — une empreinte STRUCTURELLE par fonction : « même nom, corps changé »

> **Numéro.** Cette tranche a été dispatchée sous le libellé « #253 ». Ce numéro **était déjà
> pris** par `case-253-astramilitarum-targeting.md` (livrée). `probe_468 --suggere` a alloué
> **#482**, annoncé comme sa `PORTEE DE LA MESURE` l'exige.

`data/symbols/README.md` affirme que le diff de `data/symbols/<build>/` **EST** le rapport de
changement du jeu. C'est vrai de ce qui **apparaît, disparaît ou se renomme** — et faux de tout
le reste : la table est de la forme `<adresse>\t<symbole>`, donc **un corps modifié sous un nom
stable y est invisible**. C'est exactement ce qui périme un port en silence.

**Mesure principale** : entre `gqfc5mff6c` et `rnca9r7q6c`, sur **102 647** symboles présents
dans les deux builds, **11 186 (10,9 %) ont un corps différent** — dont **1 532** sont cités par
le dépôt (`engine/`, `docs/`, `scripts/`, `frida/hooks/`).

## 1. Le critère, avant la méthode

*« Pour un symbole présent dans les deux builds, son corps a-t-il changé ? »*

Le difficile n'est pas de hacher, c'est de hacher ce qui **survit à la relocation**. Entre deux
builds le layout est entièrement réorganisé : chaque `call rel32` porte un déplacement différent.
Un hash des octets bruts rendrait « 100 % changé ».

| neutralisé (relocalisé) | conservé (structurel) |
|---|---|
| cible d'appel / de saut externe → `<F>` + **empreinte** de la cible | mnémoniques, registres, ordre |
| référence RIP-relative vers du code → idem | offsets de struct (`[rcx+0xa8]`) |
| référence vers une donnée → `<X>` | constantes immédiates (les formules) |
| adresse absolue en immédiat → idem | branchement **interne** : son delta, déjà invariant |

Cinq couches, pour **ventiler** au lieu de dire seulement « ça a changé » : `h_local` (corps
propre — **le verdict**), `h_body` (corps + appelés), `h_mnem`, `h_calls`, `h_imm`, `n_ins`.

**Les bornes de fonction ne sont pas « jusqu'à la suivante »** — cette borne-là dépend du VOISIN,
et un voisin déplacé ferait bouger l'empreinte sans que le corps ait changé. On s'arrête au
premier flux terminal au-delà duquel aucun branchement interne ne pointe (31 / 62 fonctions
seulement finissent en `trunc`).

## 2. Le piège qui a fait échouer la première version : le NOM d'une cible n'identifie pas un corps

Une première version citait le **symbole** de la cible d'appel, par analogie avec la règle
« on cite un SYMBOLE, jamais une adresse ». Elle rendait **52,0 % de corps changés**.

Ce que la décomposition par étage a montré :

| mesure | valeur |
|---|---|
| `h_mnem` identique (n'utilise **aucun** nom) | **95,0 %** |
| `h_body` identique (utilisait les noms) | **48,0 %** |
| fonctions à opcodes identiques et `h_body` différent | **48 221** |

Cause, que le `CLAUDE.md` nomme déjà : **IL2CPP déduplique les corps**, et le « propriétaire » du
nom dans la table est **arbitraire** — il change d'un dump à l'autre. Mesuré ici : **53,5 %**
(gqfc) et **55,1 %** (rnca) des fonctions vivent dans un groupe de corps partagé, le plus gros
groupe comptant **3 196** fonctions. Témoin : `AK.Wwise.BaseType$$GetHashCode` « appelait »
`GooglePlayServices` dans un build et `BurstString.tBigInt$$GetLength` dans l'autre, pour **108
instructions rigoureusement identiques** des deux côtés.

⇒ **un appel se normalise par l'EMPREINTE de sa cible, jamais par son nom.** C'est la règle du
dépôt appliquée un cran plus bas : ce qui identifie du code, c'est le code. Effet mesuré :
**52,0 % → 10,9 %**.

## 3. Le résultat

```
gqfc5mff6c -> rnca9r7q6c      102 647 symboles communs
  IDENTIQUE          84 704   (82,5 %)
  APPELES_CHANGES     6 757   ( 6,6 %)   corps propre identique, une cible a change
  CORPS_CHANGE       11 186   (10,9 %)   <- le signal qui perime un port
  APPARU             14 892       DISPARU   5 007
```

**Périmètre non couvert, imprimé par l'outil** : `FUN_*` écartés (22 647 / 22 817 — le nom
contient l'adresse) et symboles ambigus écartés (4 901 / 5 341 — plusieurs corps sous un nom).

**Faux positif résiduel, borné** : sur les 11 186 changements, **10 026 (89,6 %)** ont un corps
**unique des deux côtés** — appariement sûr. Les **1 160 (10,4 %)** restants ont un corps partagé
d'au moins un côté : c'est la **borne haute** du faux positif résiduel, pas son estimation.

**Témoin de vrai positif, décompilé des deux côtés** —
`Core.Services.OperationProcessor$$AddTrait`, 8 instructions, appelant
`IdunBattle.Operations.AddTraitOperation$$Execute` dans les deux builds :

```c
gqfc5mff6c :  if (*(longlong *)(param_1 + 0x300) != 0)
rnca9r7q6c :  if (*(void **)((longlong)this + 0x2f8) != 0)
```

**Un champ a bougé de 0x300 à 0x2f8.** Aucun outil du dépôt ne le signalait.

## 4. Les outils

| fichier | rôle |
|---|---|
| `scripts/python/fingerprint_functions.py` | `empreinte` / `diff` / `enqueter` / `ventiler` / `impact` |
| `scripts/python/probe_482_empreinte_structurelle.py` | la garde, 5 étages |
| `scripts/ghidra/GhidraDumpCodeBytes.java` | octets d'un build **archivé** (`analyzeHeadless -readOnly`) |
| `scripts/ghidra/GhidraDecompileAt.java` | décompile **par adresse** (le nom ne désigne pas un corps) |

**Le binaire d'un build archivé existe encore** : le `.dll` est effacé par la mise à jour, mais
`ghidra-projects/ghidra_<hash>/` le conserve. `analyzeHeadless` l'ouvre **indépendamment du
serveur ghidra-mcp** (projets distincts, locks distincts) — c'est ce qui rend la confrontation
inter-builds possible. Deux autres projets existent (`kqkbjqfb6c`, `tacticus`).

```powershell
python fingerprint_functions.py empreinte --build rnca9r7q6c --pe <GameAssembly.dll>
python fingerprint_functions.py empreinte --build gqfc5mff6c --blocs logs/ghidra-dump/gqfc5mff6c
python fingerprint_functions.py diff --avant logs/fingerprints/gqfc5mff6c.tsv \
                                     --apres logs/fingerprints/rnca9r7q6c.tsv --ecrire <tsv>
python fingerprint_functions.py impact --diff <tsv>        # ce qui touche nos ports
```

Coût : **~135 s par build** (154 176 fonctions). Sorties dans `logs/` — **jamais** `data/`.

## 5. La garde — `probe_482`, 5 étages, `a_mordu` séparé du verdict

| étage | ce qu'il prouve | résultat |
|---|---|---|
| 1 | **invariance à la relocation** : corps réordonné, `call` à delta différent (y compris négatif) | 4/4 empreintes identiques, octets vérifiés différents |
| 2 | **sensibilité** : constante, offset de struct, opcode, registre, cible de saut, cible d'appel | 6/6 rougissent, sur la couche attendue |
| 3 | **limite assumée** : une référence de donnée différente reste invisible | confirmée, inchangée |
| 4 | auto-diff (un build contre lui-même) | 117 539 appariés, 0 changement |
| 5 | **symétrie des chaînes** PE ↔ Ghidra | 7/7 sondes identiques |

L'étage 5 conditionne toute comparaison PE (build courant) ↔ projet Ghidra (build archivé) :
sans lui, un écart pourrait venir de la chaîne d'extraction. Il se déclare **NON MESURÉ** si
ghidra-mcp est injoignable — jamais rabattu sur un vert. L'étage 3 **documente** un faux négatif
connu ; il rougit seulement si la limite s'agrandit.

## 6. Ce qui reste ouvert

- **`#482-r1`** — une référence vers une **donnée** est invisible (`<X>`). Il faudrait une table
  de symboles de données par build ; `functions.tsv` ne contient que des fonctions.
- **`#482-r2`** — les **1 160** changements à corps partagé ne sont pas départageables par le nom.
  Un appariement par **empreinte** (et non par nom) les trancherait.
- **`#482-r3`** — l'outil n'est **pas encore branché** sur la procédure de migration de build
  (skill `tacticus-orchestration`), où il a sa place à côté de `symbols_sync.py`.
- **`#482-r4`** — `FUN_*` (≈15 %) et symboles ambigus (≈4 %) restent hors appariement.
