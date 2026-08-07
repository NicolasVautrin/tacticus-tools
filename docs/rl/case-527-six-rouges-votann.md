# #527 — Six rouges de `test_votann_lot1_live.py` : l'attribution héritée était fausse, et six rouges ne font pas six causes

`scripts/python/tests/engine/runner/test_votann_lot1_live.py` rendait **6 failed / 13 passed /
2 skipped** sur `master`. L'héritage les imputait à la tranche #525 (`1222 MassDriverAccelerator`,
porteur `votanChampion` — même faction que les tests rouges).

## 1. Étage 0 — l'attribution est RÉFUTÉE

Reproduction sur `9ff99a18` (HEAD, après #521 `5bd5aa5d` et #525 `9ff99a18`) **et** sur un worktree
témoin détaché sur `40917cd0`, **antérieur aux deux ports** : **mêmes 6 tests, mêmes chiffres**
(`9785 != 8536`, `critChance = 26`, `12880 != 0`), 6 failed / 13 passed / 2 skipped des deux côtés.
Ce n'est donc pas une régression livrée ; la proximité de faction était une coïncidence.

## 2. Ventilation — TROIS causes

Mesures : `scripts/python/probe_527_votann_lot1_rouges.py` (étages `stats` / `graviton` /
`fortune` / `replay` / `armure`).

### (A) La cible MEURT — le delta de PV n'est plus le total (3 rouges)

`necroWarden` porte `health = 8536` sur `rnca9r7q6c` ; un cast `1206 GravitonRifle` en fait **9785**.
Elle tombe à 0 PV. Or `_live_total` du test est un **delta de PV**, donc **plafonné** ; `_port_total`
est le total **brut**. Le port, lui, est **bit-exact** : per-hit `[4667, 2526, 1343]` et verdicts de
crit `[True, False, False]` **identiques** des deux côtés (étage `replay`). Le dernier coup est
tronqué côté natif, pas côté port.

Même cause pour `graviton_live_stuns_the_target` : une cible à 0 PV perd **tous** ses effets
(`effects = []`), donc le `Stunned` posé n'est plus lisible.

S'y ajoutait une seconde péremption sur le même montage : l'en-tête affirmait « **MÊME `fixedArmor`
(2008)** que `necroWarden` » — faux sur ce build (`necroWarden` **2662**, `bloodMephiston` **2008**).
Le contraste `graviton_mech` / `graviton_plain` confondait donc le **trait qualifiant** et
l'**armure**.

**Réparé** en POSANT les deux invariants (`_GRAVITON_UNIT_STATS`) : PV à 60000 sur les deux cibles
(elles survivent) et `Armor`/`FixedArmor` **égalisés** à 2008 (le seul écart restant est le trait).
Et `_live_total` **lève** désormais quand `hp_after <= 0`, au lieu de rendre un nombre qui ment.

### (B) Le régime « base nulle » de `fortune_gated` n'existe plus (2 rouges)

Le montage supposait qu'un `votanUthar` frais a `critChance = blockChance = 0` (« ces stats viennent
des ITEMS, strippés par la normalisation »). Mesuré sur `rnca9r7q6c` : **`critChance = 26`,
`blockChance = 30`**. Les deux gates `AncestralFortuneAbility$$CanAddCritChance` /
`$$CanAddBlockChance` **passent**, live comme port — le port avait **raison** de poser les buffs.

Un régime obtenu par effet de bord d'une normalisation n'est pas un régime : c'est une coïncidence
qui expire. **Réparé** en le POSANT (`_UTHAR_BASE_ZERO` :
`--unit-stat votanUthar:CritChance=0,CritDamage=0,BlockChance=0,BlockDamage=0`).

### (C) Divergence RÉELLE de choix de cible — le seul rouge qui accuse le port

Uthar était adjacent à **deux** ennemis. Le natif frappe `bloodMephiston` (79) ; le port choisit
`necroWarden` (77). Cible **forcée** à celle du natif, le dégât du port est **bit-exact** (per-hit
`[993, 977, 1131]`, total 3101, mêmes verdicts de crit) — c'est donc l'étage **CHOIX**, pas l'étage
**DÉGÂT**.

**A/B discriminant** (étage `armure`), maxHP **égalisés** à 8536 des deux côtés pour que les deux
cibles soient ex æquo en pré-armure, une seule variable qui bouge :

| régime | `necroWarden` fixedArmor | `bloodMephiston` fixedArmor | NATIF frappe | PORT choisit |
|---|---|---|---|---|
| `haute` | 2662 | 2008 | `bloodMephiston` | `necroWarden` |
| `basse` | 300 | 2008 | `necroWarden` | `necroWarden` |

La victime **native BASCULE par la seule armure**. Le port ne bascule pas : `_target_utility`
(`engine/runner/operations/damage_utility.py`) fabrique une prédiction **pré-armure** — son
en-tête l'écrit (« la plage de dégât est la MÊME pour toutes les cibles ; le classement ne dépend
que des PV courants/max et des flags kill/overkill ») — donc à maxHP égaux les deux cibles sont ex
æquo et le tie-break (id croissant) tranche.

⚠ **Pourquoi ce trou a survécu à sa validation** : la confrontation live du foyer (#419-r6-r1,
Doombolt) tournait `FixedArmor = Armor = 0` sur **toutes** ses cibles — un régime où l'armure ne
peut, par construction, rien discriminer. Un accord obtenu là ne dit rien de l'étage armure.

**NON RÉPARÉ** — résidu **#527-r1**. Le foyer est PARTAGÉ : `AncestralFortune` (`votann.py`),
`FinalJustice` (`operations/triggers/loki/final_justice.py`), `worldeaters.py`, `thousandsons.py`
(via `sort_units_by_damage_utility`). La réparation demande de lire quel étage de prédiction le
sélecteur emprunte réellement — `SortUnitsByDamageUtilitySelector$$Select` appelle le slot `0x26`
de son service `(this+0x50)` avec `(owner, target, ownerPosition, Nullable<AbilityOrEffect>, deux
Func, …, &minmax)` — puis de re-valider les quatre consommateurs. Porter « l'armure » sans lire ce
chemin serait un fit.

Les deux fixtures `fortune_*` montent désormais **un seul** ennemi adjacent (`_FORTUNE_A_UNITS`) :
elles retrouvent ce qu'elles prétendent mesurer (gates, magnitudes, total), et le classement est
confronté par le probe, pas noyé dans un test de total.

## 3. Le skip qui masquait le plus intéressant

Les `2 skipped` (« events per-coup indisponibles », les deux paramétrisations de
`test_fortune_port_matches_live_hit_by_hit_where_verdicts_agree`) n'étaient pas une indisponibilité
de harnais : `live_hits` était vide **parce que le natif frappait l'autre ennemi**. Le skip est
devenu un **échec** explicite (#268) qui nomme le résidu.

## Résidus

- **#527-r1** — `SortUnitsByDamageUtilitySelector$$Select` : l'armure de la cible entre dans
  l'utilité native, `_target_utility` la met à zéro. Mesuré, non réparé. Rejouer :
  `python probe_527_votann_lot1_rouges.py --etage armure --regime haute|basse`.
