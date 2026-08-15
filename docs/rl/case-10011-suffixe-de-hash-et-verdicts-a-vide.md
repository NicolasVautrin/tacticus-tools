# #10011 — un suffixe de hash codé en dur a tué le capteur, et le verdict a passé À VIDE

**2026-08-15.** Deux rouges de `master` (`test_spiritual_leader_tile_term_live.py` 1 F / 9 P,
`test_477r33_non_owner_playbooks_live.py` 12 F / 29 P). Causes **différentes** ; le second est
cross-cutting et c'est l'objet de cette fiche. Le premier est dans
[`case-212`](case-212-spiritual-leader-bc-key.md) § « L'oracle du comptage ».

## 1. Le fait, mesuré

`frida/hooks/il2cpp/build-pin.ts` testait la forme d'un hash de build par
`/^[a-z0-9]{8}6c$/`. Le suffixe `6c` n'était pas une **règle**, c'était une **régularité
accidentelle** des six premiers builds observés. Le build courant finit en `6g`.

Conséquence en chaîne, chaque maillon mesuré et non supposé :

| étage | mesure |
|---|---|
| `installedBuild()` | `build: null`, `buildWhy: "le segment ... n'a pas la forme d'un hash de build"` |
| `pinnedAddress` | **11 refus** (RPC `nameResolutionStatus`, champ `pinnedAddressRefusals`) |
| `scorerTileTermTraceDump` | **14 entrées** — il survit, il se résout au RUNTIME (`resolveSharedPlaybookBody`) |
| `scorerElevTraceDump` | **0 entrée** |
| `scorerLeafTraceDump` | **0 entrée** |
| `X_nat = Tile(7) − Elevation − TileEffects` | `None` sur **11 tuiles hookées sur 11** |
| `divergences()` | **0 pour TOUS les modèles**, `ABSENT` compris — qui vaut pourtant `0.0` par construction |
| `test_le_natif_suit_le_PORT` | **VERT, sur zéro assertion évaluée** |

Le refus était **correct** (c'est le contrat de `pinnedAddress` depuis #475). Ce qui manquait,
c'est quelqu'un pour le **dire** avant qu'un consommateur lise ce silence comme une mesure.

⚠ **Le foyer a nommé sa panne, et personne ne l'a lue.** `pinnedAddressRefusals` existait,
`nameResolutionStatus` l'exposait, le refus portait le symbole de sa cible. Onze messages
parfaitement exacts, zéro lecteur. Un capteur qui sait nommer sa panne ne sert à rien tant
qu'aucun consommateur ne l'interroge sur le chemin de son propre verdict.

## 2. Pourquoi `probe_475` était VERT

Sa règle R2 résout chaque pin dans la table du build que **le pin DÉCLARE** — et cette table-là
reste versionnée pour l'éternité. Le cliquet était donc **structurellement incapable** de voir un
pin épinglé sur un build disparu : R1 verte, R2 verte, verdict VERT, capteur mort.

L'étage **R3** confronte le build **déclaré** au build **installé** et TRIE :

* **re-dérivable offline** (symbole UNIQUE, début de fonction) → *migration manquante*, ROUGE,
  avec la VA neuve ;
* **quatre formes qui ne le sont pas** — donnée `DAT_*`, placeholder `FUN_*` (son nom **est** son
  ancienne adresse : le retrouver ne prouve rien), point **interne** (transposer l'offset est déjà
  tombé 243 octets à côté), symbole à plusieurs occurrences — **nommées et comptées**, jamais
  bloquantes ;
* **build installé illisible** → `NON MESURÉ`, ni vert ni rouge (aucun zéro fabriqué).

**Contre-épreuve**, jouée sur le contenu d'`origin/master` sans toucher l'arbre : R3 rend
**8 migrations manquantes** là-bas et **0** ici.

## 3. Ce qui est réparé, ce qui attend une fenêtre

**Réparé et actif tout de suite** (Python, aucun reinject) :

* `cause_x_nat_non_mesurable` (`probe_193c_move_playbook_terms.py`, là où vivent déjà `x_port` et
  `x_excluded`) : la panne est **nommée** — comptes par canal, sous-hooks morts, build chargé,
  refus de pins, et le remède ;
* `mesurer` pose **`x_nat_indisponible`** quand aucune ligne ne porte de `X_nat` — un **CHAMP**, pas
  un écrasement, et la différence porte : rendre `{"erreur": …}` détruirait `bras_a` / `bras_b` /
  `prof`, qui sont **mesurés et justes** (le montage a bien placé ses deux bras, la trajectoire a
  bien été marchée, les tuiles ont bien été hookées). Seul le canal **natif** manque. Les gardes de
  **montage** restent donc VERTES — elles ne mentent pas — et seules celles qui consomment `X_nat`
  rougissent. Mesuré sur `#477-r33` : l'écrasement rend **36 F / 5 P**, le champ **24 F / 17 P**,
  pour la même panne. Faire accuser le montage par la panne du capteur est exactement le vice
  qu'on répare : le rejouer à l'envers serait le rouvrir ;
* le cran est posé sur les **cinq** consommateurs de `X_nat` (`#477-r29`, `-r31`, `-r33`, `-r35`,
  `-r37`), foyer partagé ; `test_le_natif_suit_le_PORT` assertionne en outre son **propre non-vide**
  en second verrou, pour qu'un changement de `mesurer` ne rouvre pas le trou ; `probe_212._verdict`
  volet B de même ;
* `probe_475` étage R3 + son auto-épreuve (6 formes, les deux sens).

**Livré, INERTE jusqu'à une fenêtre de reinject** (`frida/hooks/**` vit dans Frida) :

* `BUILD_SHAPE` → `/^[a-z0-9]+$/`. Le raisonnement est sur la **direction de panne**, pas sur un
  relâchement : une forme trop STRICTE dégrade en refus de **tout**, en silence ; une forme trop
  LARGE dégrade en `probe.build != pin.build`, donc en refus **de ce pin**. Aucun chemin ne fait
  **accepter** un pin par erreur — il faudrait que le segment lu soit **égal** au build déclaré.
  Ce qui identifie le build est sa **position** (le segment après `games/`), pas sa forme.
* **8 pins re-dérivés** par symbole unique contre `data/symbols/<build>/ghidra/functions.tsv` ;
* `rvaHooks` : `rvaInstalled` disait « on a **essayé** », `rvaHooks` dit **ce qui est attaché**,
  sous-hook par sous-hook. `installLeafHooks` / `installBonusHook` rendaient `true` avec zéro
  attache.

## 4. Le rayon — ce n'est pas un fichier, c'est une famille

`X_nat` est le socle de toute la famille des termes de tuile : **18 fichiers** arment
`scorerDamageTraceOn` (11 probes + 2 tests + les probes d'isolement), **9 fichiers de test** en
dépendent. Ils sont tous dans le même état tant que la fenêtre n'a pas eu lieu.

## Résidus

* ~~**#10011-r1**~~ — **FERMÉ le 2026-08-15**, `case-475-adresses-epinglees.md` §8. Les **5** pins
  (2 `DAT_*`, 1 placeholder `FUN_*`, 1 point interne, 1 symbole à deux occurrences) sont LUS au
  binaire — plus le 6ᵉ de `modifier-observe` (`#475-r2`). `probe_475` R3 : **0 périmé sur 14**. Le
  résolveur d'override de base ne refuse plus en bloc ; il n'est pas encore confronté (`#475-r4`).
* **#10011-r2** — `probe_330.BUILD_RE` et `probe_431.BUILD_RE` codent le même `6c` en dur : les
  deux cliquets sont **aveugles au build courant**. L'inventaire de `probe_330` en est la preuve
  directe — il liste 489 mentions de six hashes et **zéro** du hash courant.
* **#10011-r3** — re-valider les **offsets de struct** lus par les hooks Elevation / feuille après
  la fenêtre. La migration restaure le **tir** ; elle ne prouve pas le **décodage** (précédent :
  les offsets de `DamagePredictionResult` avaient survécu à un build en rendant du garbage
  silencieux).
