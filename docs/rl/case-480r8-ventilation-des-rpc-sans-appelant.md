# #480-r8 — les 155 RPC sans appelant : aucun n'est une feature retirée

Probe : `scripts/python/probe_480r8_rpc_ventilation.py` (7 étapes, `--cliquet`, `--catalogue`,
`--archeologie`). Cliquet : `scripts/python/tests/test_480r8_rpc_joignable_offline.py`.
Tranche 100 % offline : aucun runner, aucun RPC live, aucun reinject.

## Verdict en une ligne

Les 155 ne sont **pas** « les enveloppes des sondes » comme l'annonçait #480-r6 : **4 seulement**
viennent de `hooks/probes/`, et **61** de `controller.ts`. L'archéologie tranche le reste —
sur les 84 sans aucune trace, **84/84 n'ont JAMAIS eu d'appelant écrit** : zéro feature retirée,
zéro remplacé. Ils n'ont pas été tués, ils n'ont **jamais été câblés**. Le seul mort *démontré*
par le code rendait `{ ok: false, msg: "Not implemented yet" }`.

---

## 1. Le compte parent était juste par COMPENSATION de deux erreurs opposées

`155` re-tombe sur `155`, et **ce n'est pas le même ensemble** :

| | effet |
|---|---|
| `classFields` | **faux mort** — appelé par `frida/tools/probe-279-layout-by-name.ts:257` (`{ method: "classFields" }`). `frida/tools/` n'était dans **aucun** des 6 groupes de #480-r6. |
| `ping` | **faux vivant** — son seul appelant est `hooks-legacy/_test/`, une **archive** dont le CLAUDE.md pose que rien de vivant ne dépend. |

Cause commune : le corpus était une **liste de 6 groupes écrits à la main**, et une liste ne peut
pas montrer le répertoire qu'elle a oublié. Ici il est pris par **complément** — tout fichier
versionné d'extension exécutable hors `frida/hooks/` (**2 033**), groupe **dérivé** du chemin, un
chemin inconnu sortant sous `autre (<racine>)`. Deux erreurs qui se compensent rendent un total
juste et un verdict faux sur deux items.

## 2. Ventilation des 155 — cinq canaux, mesurés indépendamment

Un RPC est joignable s'il porte au moins un canal. C0 = archive `hooks-legacy/` ; C1 = appel
exécutable (critère #480-r6) ; C2 = token nu exécutable ; C3 = cité dans un `.md` versionné ;
C4 = cité dans un message de commit (`git log --all`, 3 254 messages) ; C5 = un **frère** du même
module a C1.

| classe | n | ce que c'est |
|---|---|---|
| **AUCUN CANAL** | **84** | écrit nulle part hors de son déclarant — §3 |
| C3 / C3+C5 / C3+C4 / … | 51 | documenté : geste de diagnostic connu |
| **C5 seul** | 11 | moitié de paire — lecteurs de trace (`scorer*Dump`, `hitTrace*`) |
| C4 seul | 4 | **fragiles** : plus aucune trace dans l'arbre, seulement l'historique |

⚠ **C3 existait chez le parent mais n'entrait pas dans son verdict** : il construisait le corpus
`doc` puis ne s'en servait pas. 165 RPC étaient documentés et comptés « sans appelant ».

## 3. Les 84 sans trace — l'archéologie dit *jamais câblés*, pas *tués*

`git log --all -S<nom>` restreint au code vivant (hors `frida/hooks/`, hors `hooks-legacy/`, hors
`.md`), 8 en parallèle, ~173 s : **84/84 rendent VIDE**.

Le zéro a été retourné contre son capteur avant d'être cru — même commande sur des témoins :
`classFields` **10** commits, `playTurn` **5**, `dumpEnums` **4**. Le capteur discrimine, donc le
zéro est réel.

**Ce qu'ils sont** : 57 sont des enveloppes d'introspection IL2CPP de `controller.ts`
(`dump*`/`check*`/`search*`/`inspect*`). Leur sortie **ne revient pas dans la réponse RPC** — ils
rendent `{ ok: true }` et écrivent par `console.log`, que `sessions.ts` publie et journalise
(`onMessage` → `publish` + `appendLog`). Ils restent donc exploitables : on lit le **log de
session**. *(Hypothèse « inutilisables par construction » : posée, puis réfutée par ce chemin.)*

**Morts démontrés, et retirés** :

| | preuve |
|---|---|
| `searchMethods` | corps = `return { ok: false, msg: "Not implemented yet" }` — jamais fini |
| `dumpStatComp` (1ʳᵉ des 2) | **déclaré deux fois dans `controller.ts`**, corps identiques : la 1ʳᵉ est écrasée |

Invariant du bundle (`probe_480r6_bundle_equivalent.py`) : **N1 321 → 320, perdu = `searchMethods`
seul** ; **N2 identique** (228) ; N3 divergent au point exact de la coupe. Le doublon ne change pas
le contrat — confirmation qu'il était inerte.

**Non touchés, car documentés comme intentionnels** : `battleStatus` (`status.ts`) et
`dumpEntityComponents` (`observe.ts`) sont **écrasés** par leurs homonymes d'`ai-step`
(`.forEach` de `wireRpc`, `aiStep` après `status`/`observe`). Ce sont deux implémentations mortes
— mais `rpc-api.md:26` le **documentait déjà**. Le seul appelant (`router.ts:232`) lit le contrat
du survivant : l'écrasement n'a rien cassé.

## 4. Le cliquet — et l'échappatoire trouvée en le posant

**Invariant** : tout RPC déclaré porte un canal **NOMINATIF** (C1/C2/C3/C4) — son nom est écrit
quelque part hors de son fichier déclarant. Critère dérivé du corpus, jamais une liste de noms :
il mord au 156ᵉ comme au 1ᵉʳ.

⚠ **La 1ʳᵉ version ne mordait pas.** Contre-épreuve par mutation : un `ctx.rpc.<neuf>` ajouté dans
`status.ts`, sans appelant ni doc ni commit, laissait **VERT** — parce que **C5** (un frère est
câblé) le blanchissait. C5 aurait donc cessé de mordre exactement sur le gisement visé, notre
propre cadence d'ajout. **C5 est un canal de TRI, jamais une preuve** ; C0 (archive) est exclu au
même titre. Après correction, la même mutation rend **rc 1**.

**Ce qui l'a rendu vert** : les 83 + 11 sont désormais **NOMMÉS** dans `rpc-api.md`
(`--catalogue` produit le bloc). La section existait mais décrivait par **patron** (`dump*`) —
un patron ne rend aucun nom découvrable, et on ne peut invoquer que ce qu'on connaît. C3 : **165
→ 248**. L'en-tête annonçait par ailleurs **257 handlers, « synchronisé le 2026-07-02 »** pour une
surface qui en portait **321**.

## 5. Croisement avec `#480-r3` — mesuré par le bout statique

Un module importé par `controller.ts` mais absent de ses appels `register` ne publie aucun de ses
RPC. Foyer unique vérifié (`main.ts` → `wireRpc` ; aucun `Object.assign(rpc, …)` ni `rpc[nom] =`).
Résultat : **1 module, 4 RPC** — `movement-trace.ts` (`clearMovementTrace`, `dumpMovementTrace`,
`movementTraceInstallStatus`, `movementTraceStats`), désactivé **volontairement** et commenté
(`void movementTrace`, `/* movementTrace, */` : 39 `Interceptor.attach` et un lag de navigation).

⚠ **La 1ʳᵉ version de cette étape rendait 216 RPC « non exposés »**, dont `autoBootExtraire`,
`playTurn`, `initRunner` — la classe négative `[^)]*register` bute sur la parenthèse de `(f) =>`,
donc le motif ne matchait jamais. Rattrapé parce que le résultat contredisait un fait connu, **pas**
parce que le probe s'en est aperçu : il porte depuis un **témoin auto-vérifiant dérivé** — un RPC
appelé par le **host** est nécessairement exposé, s'il apparaît ici c'est le capteur qui ment (rc 2).

## 6. Le rebase a trouvé un défaut que la 1ʳᵉ passe ne pouvait pas voir

Re-joué après rebase (**37** commits) : l'étage 2 du cliquet est passé au **ROUGE**. Cause réelle,
pas artefact — le test est un `.py` **versionné**, donc il appartient au corpus qu'il interroge :
son témoin « nom qui n'existe pas », écrit en littéral, était vert tant que le fichier n'était pas
suivi, puis s'est **auto-accusé** dès son entrée dans `git ls-files`. Le témoin est désormais
**tiré au hasard** (`uuid4`), donc incontaminable. Un contrôle qui contamine son propre corpus finit
par rougir sur son artefact, pas sur son sujet.

Autre effet du rebase, sans action : **SANS C1 154 → 153** — un RPC a gagné un appelant dans les
commits arrivés entre-temps. Le corpus bouge ; ces chiffres se **re-dérivent**, ils ne se citent pas.

## 7. Ce qui n'est PAS couvert

- **Aucune confrontation live.** Le retrait de 2 RPC touche `frida/hooks/*` : il n'est **actif
  qu'après un reinject** — fenêtre à planifier, non prise ici.
- Un RPC **invoqué à la main et jamais écrit nulle part** reste indiscernable d'un mort par toute
  mesure statique. C'est la borne du probe, imprimée à chaque passe.
- Ce que la **session expose réellement** — `#480-r3` reste ouvert ; §5 n'en couvre que la face
  statique.
- **Les 83 ne sont pas tranchés un par un** : ils sont documentés, pas jugés utiles. Retrait ou
  conservation reste une décision à prendre.

## Résidus

- **`#480-r10`** — **le cliquet ne mord que dans UN sens.** Il exige qu'un RPC soit nommé ;
  rien n'interdit à `rpc-api.md` de citer un RPC **disparu**. Mesure tentée : 198 identifiants
  camelCase en backticks, **32** non déclarés — mais ce sont des noms de **champs** (`args`,
  `targets`, `null`), donc le critère **ne discrimine pas** et ne permet pas de conclure « 0
  périmé ». *Retournement* : un critère de **position** (nom en forme de RPC : `**\`nom(…)\`**`,
  `"method": "nom"`) rend un compte assumé, et un nom cité comme RPC sans déclaration rougit.
- **`#480-r7`** (hérité, ouvert) — 13 exports sans aucun usage.
