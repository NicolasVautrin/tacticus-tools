# #456-r2 — la DÉCOMPOSITION du terme MOVE, confrontée (le reste de #456)

**Question binaire** : le canal `contribs` du capteur `#443-r1a` TRANSPORTE-t-il une
décomposition par playbook, et cette décomposition est-elle JUSTE ?

> NOTES DE TRAVAIL — en cours de mesure. L'état final remplacera ce bloc.

## Ce que le brief tenait pour l'état, et ce que la mesure dit

Le brief #456 décrit la fenêtre #4 (2026-08-02) : `bondedEntityId` null sur 36/36, buffer MOVE
vide. Cet état est **PÉRIMÉ** — `master` porte déjà `case-456-deux-canaux-confrontes.md` et
`case-456-r1-terme-move-kit-et-playbook.md`, tous deux fermés le 2026-08-02.

Mesure d'entrée (2026-08-04, ce worktree) :

| ce qui est mesuré | valeur |
|---|---|
| session Frida | id **2**, pid 52708, `running`, démarrée **2026-08-03T22:47:52Z** |
| build | `rnca9r7q6c` |
| bundle chargé | `frida/dist/hooks.js`, **1 092 308 o**, mtime **2026-08-02 10:42:23** |
| `triggeredMoveTraceStatus` | répond (`installDone: false`, capteur présent, non armé) |
| `resolveByStructure` dans le bundle | **5** occurrences |
| `:ambiguous(` dans le bundle | **1** occurrence |

Les deux dernières lignes sont le discriminant : ces littéraux n'existent QUE dans le correctif
structurel de #456 §3.4, livré **non chargé** le 2026-08-02. Le bundle qui les porte est celui du
02/08 10:42, et la session 2 (injectée le 03/08 22:47) l'a chargé.

**La fenêtre de reinject qu'attendait #456 a donc EU LIEU.** Le seul reste nommé du cas — la
DÉCOMPOSITION (E3) et la valeur du terme `SaviorProtocols` (E4) — devient confrontable.
