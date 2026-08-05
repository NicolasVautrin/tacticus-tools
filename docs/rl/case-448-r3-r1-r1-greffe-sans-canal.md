# #448-r3-r1-r1 — un probe qui greffe sans alimenter le canal mesure un port amputé

**Statut** : RÉSOLU. Le foyer REFUSE désormais au lieu de se dégrader ; le recensement passe de
**2 sites amputés + 4 indéterminés** à **0 et 0**, sous cliquet. Le résultat le plus important n'est
pas la fermeture du gisement mais **une divergence de port qui n'en était pas une** : le résidu
`#419-r1-tr14-r5-r2-r1-r2-r1-r2` (« divergence des substrats ») est **fermé** — le port disait `69`
là où le natif dit `1126` *uniquement* parce que le canal n'était pas lié (§4).

## 1. Le recensement de la fiche parente était FAUX PAR EXCÈS, et son critère disait pourquoi

`case-448-r3-r1` §9 recensait « un fichier qui greffe **et n'appelle pas `bind_live_rpc`** » et
rendait **sept** probes. Ce critère ne voit qu'**UNE des deux voies** d'alimentation du canal
`unitAbilityStates`. `load_state` en accepte deux, et `_auto_ability_states` les nomme :

| voie | régime rendu | couvert ? |
|---|---|---|
| transport ambiant lié (`snapshot.bind_live_rpc`) | `auto` | oui |
| payload passé (`load_state(..., ability_states=<payload>)`) | `given` | **oui, et le critère ne le voyait pas** |

Ventilation des sept, re-dérivée :

| fichier | ce qu'il fait vraiment | verdict |
|---|---|---|
| `probe_366_r1_stormboyz_strike.py` | `ability_states=ast` | déjà couvert |
| `probe_448_r1_r1_r1_flying_movement_steps.py` | `ability_states=ast` | déjà couvert |
| `probe_448_r1_r1_r2_fly_override.py` | `ability_states=ast` | déjà couvert |
| `probe_478_cleave_additional_targets.py` | `ability_states=ast`, **+ assertion de non-vide** | déjà couvert |
| `probe_425_tile_effect_channel.py` | **n'appelle jamais `load_state`** | hors sujet |
| `probe_447_bit51_native.py` | `load_state(...)` nu | **AMPUTÉ** |
| `probe_448_r2b_stormboyz_teleporting_in.py` | corrigé par la tranche parente | — |

Soit **1 vrai positif sur 7**. Le critère correct est le **CANAL**, pas la **VOIE**.

## 2. Le recenseur ne pouvait pas être une liste — les cinq étages

`probe_448_r3_r1_r1_greffe_sans_canal.py`. Chaque étage est **dérivé** ; l'étage 5 imprime ce que la
mesure ne voit pas, à chaque run.

1. **PRIMITIVES** — dérivées de `catalog_inject.py` par data-flow intra-fonction : une fonction qui
   affecte `PassiveAbilities` / `ActiveAbilities` / `TertiaryAbility` sur une unité est
   **DIVERGENTE** si la valeur écrite dérive d'un paramètre hors `SUPPORT_PARAMS` (le BC, l'unité,
   le chemin de sortie) — c.-à-d. si l'**appelant choisit** ce qui est monté. Sinon
   **TRANSCRIPTION** : `augment` recopie le gameconfig de l'unité, et un port qui en dérive tombe
   juste. Troisième classe, trouvée par le data-flow et absente de toute liste :
   **`divergente-si:<param>`**.
2. **GREFFEURS** — fermeture transitive des appelants.
3. **LECTEURS** — fermeture transitive de `engine.runner.snapshot.load_state`, et la liste de ses
   **sites**.
4. **COUVERTURE par SITE** (pas par fichier) : `given`, ou ambiant atteint, ou ambiant hérité
   (`tests/conftest.py::live_session`).
5. **PORTÉE** — cf. §7.

### Deux fautes de méthode, mesurées sur ce recenseur même

* **Un graphe d'appels par NOM TERMINAL ne discrimine rien.** Première version : `catalog_inject.main`
  appelle les primitives ⇒ `main` devient « greffeur » ⇒ **1842 fichiers sur 1842**. Le graphe est
  donc **QUALIFIÉ PAR MODULE** (résolution des imports, y compris relatifs).
* **Un critère par APPEL rate le montage le plus utilisé du dépôt.** `write_grafted_seed_bc` fait
  `graft = graft_active_ability if kind == "active" else graft_passive_ability` puis `graft(...)` :
  aucun appel nommé. Le graphe compte donc l'**appel ET la simple RÉFÉRENCE de nom**.
* **Et le critère de LIAISON a reproduit la faute d'origine** : écrit par nom terminal
  `bind_live_rpc`, il était aveugle au wrapper `rl_collect_batch.bind_ambient_rpc` — **4 faux
  positifs**, sur les fichiers que cette tranche venait de corriger. Il prend désormais la
  **fermeture transitive** des appelants du foyer : un wrapper futur y entre seul.

## 3. Le foyer : `load_state` REFUSE au lieu de se dégrader

Le vice n'est pas qu'un probe oublie une ligne — c'est que l'oubli soit **permissif** : sans canal,
`triggers/dispatch/core.py::collect_triggered_abilities` retombe sur `gameconfig.unit(<greffon>)`,
**aucune** classe greffée n'est montée, et toute assertion NÉGATIVE passe **à vide, en vert**.

* `catalog_inject` tient un **registre de PROCESSUS** (`declare_graft` / `declared_grafts` /
  `clear_declared_grafts`), alimenté par les primitives elles-mêmes — un appelant n'a jamais à y
  penser.
* `snapshot._refuse_if_grafted` LÈVE `GraftedStateWithoutChannel` quand le processus a greffé **et**
  que le canal est muet **par accident** (`no-transport`, `no-runner-label`, `unavailable:…`).
* **Deux régimes en sont exclus, et c'est raisonné** : `refused` (`ability_states=False`) est le
  refus EXPLICITE, l'échappatoire consciente ; **`no-snapshot`** est un **no-op structurel** — sans
  `combatSnapshot` il n'y a aucun `StatsComponent`, donc `collect_triggered_abilities` ne dérive
  rien du gameconfig non plus. Y lever serait un faux positif.
* La lecture passe par `sys.modules.get("catalog_inject")` : si le module n'a jamais été importé,
  aucune greffe n'a pu être faite — le test est **exact**, et `engine/` ne gagne **aucune**
  dépendance vers un module de montage.

**`restrict_abilities` est une greffe en sens INVERSE**, et personne ne l'avait comptée :
`write_augmented_seed_bc(restrict_abilities={...})` fait porter au BC **MOINS** que le gameconfig.
Sans canal, le port monte alors des abilities que la bataille **n'a pas** montées. Même signature
muette. Elle déclare donc aussi.

**Hors périmètre, et c'est mesuré** : `add_unit_trait`. Un trait greffé est lu par le port sur
`combatSnapshot.units[].traits` (`snapshot._load_unit_traits` → `ctx.traits`, que
`collect_triggered_abilities` itère en PREMIER) — substrat **UNIQUE** avec le natif, aucune
dépendance au canal. C'est le constat déjà écrit dans `catalog_inject.add_unit_trait`.

## 4. Verdicts AVANT / APRÈS — la pièce maîtresse

Régime AVANT reproduit par `--sans-canal` (canal muet **et** registre purgé, donc sans le refus) :
c'est *exactement* ce que le probe mesurait.

| probe | AVANT | APRÈS | changement |
|---|---|---|---|
| `probe_447_bit51_native.py` (MC1_67/777) | PASS, B 16/16, C 11/11 | PASS, **valeurs bit-identiques** | aucun |
| `probe_226r_skystrike_spread.py` (MC1_67/777) | A/B `[3334, 3156, 2477]` == live, C `!=` | **identique** | aucun |
| `probe_419…r1_r1_only_adjacent_live.py` (MC1_67/4192) | 9 lignes PASS — **voie implicite `69`, natif `1126` : DIVERGENCE** | 9 lignes PASS — **voie implicite `1126` : ACCORD** | **OUI** |

### « Vert avant, vert après » : pourquoi, LU dans le code

* **`probe_447`** instancie son ability par `ABILITY_CLASSES[TUNNELING_HORROR]()` — le **registre
  statique**, indexé par `ActiveAbilityType`, jamais dérivé du kit monté sur l'unité — et
  `get_invalid_target_reason` ne lit **que** `ability.TARGETING_OPTIONS`. Aucun des quatre champs
  seedés par le canal n'entre dans ce chemin : le seul lecteur de `passive_abilities` /
  `active_abilities` / `config_active_abilities` dans `targeting.py` est `normal_attack_type_for`,
  qui ne sert **que** quand l'ability n'est pas fournie. Le probe était donc sain **par accident de
  sa question**, pas par construction.
* **`probe_226r`** : la seule passive que `restrict_abilities` retire est `GeminaeSuperia`, et
  `ABILITY_TRIGGERS["GeminaeSuperia"]` est **VIDE** (aucun trigger porté). Le second lecteur possible
  est écarté par mesure : `custom_normal_attack` rend `None` dans les **trois** régimes (canal muet,
  kit gameconfig explicite, kit restreint mesuré) — aucune substitution d'attaque normale. Les traits
  (`ActOfFaith`) ne passent pas par `PassiveAbilities` et ne sont donc pas touchés.

### Le résultat neuf : un résidu qui n'existait pas

`probe_419…only_adjacent` **contournait** le vice — sa docstring l'écrit noir sur blanc : « le port
tire son type d'attaque normale du KIT gameconfig, donc il continuerait de dire `69` : c'est
pourquoi le jeu d'options `1126` est passé EXPLICITEMENT aux deux modèles » — et le rangeait en
résidu `#419-r1-tr14-r5-r2-r1-r2-r1-r2`, « divergence des substrats ». Une ligne de mesure ajoutée
(`normal_attack_type_for`, offline, coût nul) tranche :

```
--sans-canal : voie IMPLICITE du port = 69   (natif 1126) -> DIVERGENCE (substrat gameconfig)
canal lie    : voie IMPLICITE du port = 1126 (natif 1126) -> ACCORD
```

**Ce n'était pas une divergence de port.** Le contournement rendait les 9 lignes du probe
insensibles au canal — c'est précisément pourquoi personne ne l'avait vu : le probe était vert des
deux côtés.

## 5. Le cliquet

`tests/engine/test_448_r3_r1_r1_greffe_sans_canal_offline.py` — **10 passed, 100 % offline**. Trois
étages, qui gardent des choses différentes :

1. **le recensement est à zéro** — invariant `AMPUTES == 0 and INDETERMINES == 0`, jamais un seuil
   (un `<= N` cesse de mordre dès qu'un contributeur ne remonte pas N) ; plus deux gardes
   d'auto-tautologie (`suspects` non vide, `rows` non vide) ;
2. **le recenseur SAIT ÉCHOUER** — quatre fichiers synthétiques (amputé / couvert / vice réparti sur
   **deux modules** / appelant indirect). Un zéro d'instrument aveugle ne vaut rien : `probe_181`
   rendait `0` inconditionnellement ;
3. **le choke point REFUSE** — plus ses quatre non-régressions : sans greffe, refus explicite,
   `no-snapshot`, canal alimenté (`given` **et** `auto`), et le capteur en panne (`unavailable`) qui
   doit lever aussi.

L'étage 1 garde aussi que le **périmètre reste dérivé** : les quatre primitives divergentes doivent
y être, et `write_augmented_seed_bc` doit rester **conditionnelle** — la compter greffeuse
inconditionnellement ferait rougir des dizaines de montages sains.

## 6. Validation

* **Tests ciblés rejoués, tous verts** : `test_448_r2b_stormboyz_teleporting_in_live` (12),
  `test_bit51_native_live` (11), `test_357_relic_rail_live` (12),
  `test_363_ability_states_default_live` (10), `test_366_r1_stormboyz_strike_live` (8),
  `test_425_tile_effect_channel_live` (4), `test_sky_strike_live` (6),
  `test_448_r3_r1_noms_non_resolvables_offline` (3). Les deux tests `#357`/`#363` sont ceux qui
  **délient volontairement** le transport : ils passent parce que leurs reliques viennent du seed BC
  natif, pas d'une greffe.
* **Probes touchés rejoués en entier** : `probe_447` (PASS), `probe_226r` (PASS),
  `probe_419…only_adjacent` (PASS), `probe_419…normal_attack_options` (rc 0),
  `probe_419…r4_melee_clamp` (rc 0), `probe_589r1 --only EXO` (PASS).

## 7. Ce qui n'est PAS couvert

* **Une greffe faite par un AUTRE PROCESSUS** — résidu `#448-r3-r1-r1-r1`, §8. Ni le balayage
  statique (aucun appel de primitive dans le fichier) ni le registre (fait de processus) ne la
  voient.
* **Les appels DYNAMIQUES** (`getattr(CI, nom)`, callable stocké dans un dict) : le graphe est
  syntaxique.
* **Un site couvert par `ability_states=<expr>` n'est pas vérifié NON VIDE** par le recenseur : un
  payload en erreur y passerait pour une mesure. Seul `probe_478` l'assertionne — c'est le cran
  au-dessus, et il n'est pas généralisé.
* **Les quatre probes corrigés par liaison ambiante n'ont pas tous été mesurés AVANT/APRÈS** :
  `probe_419…normal_attack_options`, `probe_419…r4_melee_clamp` et `probe_589r1` ont été rejoués
  APRÈS (rc 0) mais leur bras AVANT n'a pas été isolé — le coût était trois montages de plus pour
  une question à laquelle le voisin `only_adjacent` (même greffe, même substrat) répond déjà.

## 8. Résidu ouvert — `#448-r3-r1-r1-r1`

**Un seed BC greffé par un AUTRE processus reste invisible des deux gardes.** Le patron :
`rl_duel build --graft <spec>` (ou un probe amont) écrit le seed BC, un second processus le reçoit
par `--seed-bc <chemin>` et charge l'état sans canal. Il ne porte aucun appel de primitive (le
balayage ne le voit pas) et son registre est vide (le refus ne mord pas).

Piste, non instruite : faire porter la marque par le **seed BC lui-même** (une clé au niveau
racine, écrite par `write_grafted_seed_bc` / `write_relic_seed_bc`) et la faire remonter jusqu'au
`load_state` — ce qui suppose un canal qui n'existe pas aujourd'hui (`load_state` reçoit des
payloads, jamais le BC ni le state-file). Chiffrer d'abord le gisement : combien de probes
reçoivent un `--seed-bc` qu'ils n'ont pas écrit ?

## 9. Reproduction

```
python scripts/python/probe_448_r3_r1_r1_greffe_sans_canal.py
python scripts/python/probe_448_r3_r1_r1_greffe_sans_canal.py --details
python scripts/python/probe_448_r3_r1_r1_greffe_sans_canal.py --mutate
python -m pytest scripts/python/tests/engine/test_448_r3_r1_r1_greffe_sans_canal_offline.py

python scripts/python/probe_447_bit51_native.py --sans-canal      # regime d'AVANT
python scripts/python/probe_447_bit51_native.py
python scripts/python/probe_226r_skystrike_spread.py --sans-canal
python scripts/python/probe_226r_skystrike_spread.py
python scripts/python/probe_419r1tr14r5r2r1r2r1r1_only_adjacent_live.py --sans-canal
python scripts/python/probe_419r1tr14r5r2r1r2r1r1_only_adjacent_live.py
```
