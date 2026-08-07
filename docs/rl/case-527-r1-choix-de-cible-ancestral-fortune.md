# #527-r1 — Le classement de cible de `SortUnitsByDamageUtilitySelector` : l'armure est ÉLIMINÉE, le canal BLOCK est le candidat

**Statut : NON RÉSOLU.** Ce dossier ne livre pas de fix. Il livre ce qui est **éliminé**, ce qui
reste **ouvert**, et l'instrument pour reprendre.

## 0. Le fait

`AncestralFortuneAbility$$GetAttackTarget` =
`First(SortUnitsByDamageUtility(NormalUnits(AdjacentEnemies(caster, 1), 3), MinMaxDamage(entities, 1), 3), 1)`.

Avec **deux** ennemis adjacents à `votanUthar`, le natif frappe `bloodMephiston` (79), le port
`necroWarden` (77).

L'étage **DÉGÂT est hors de cause** : cible **forcée** à celle du natif, le port est **bit-exact**
(per-hit `[993, 977, 1131]`, total 3101, mêmes verdicts de crit). C'est l'étage **CHOIX**.

## 1. Ce que la première explication disait — et pourquoi elle est FAUSSE

#527 avait conclu « l'armure de la cible entre dans l'utilité native, `_target_utility` la met à
zéro ». C'était l'inférence d'un A/B à deux bras. **Le calcul la réfute.**

`AncestralFortune` porte le profil **`Plasma`**, dont le `PiercingDamageRatio` du gameconfig vaut
**65**. Le foyer natif est
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`
= `max(0, d − armure, d × pierce%)` — le perçage est un **plancher**. Sur la moyenne des bornes de
l'ability (`avg = 2044`) :

| armure | `d − armure` | `d × 65 %` | résultat |
|---|---|---|---|
| 2662 | −618 | 1328.6 | **1328.6** |
| 2008 | 36 | 1328.6 | **1328.6** |
| 300 | 1744 | 1328.6 | **1744.0** |

⇒ à 2662 et à 2008 le dégât est **identique**. L'armure ne mord qu'à 300. Donc l'armure explique le
seul bras `basse` de l'A/B — pas le régime nominal ni le bras `haute`, qui sont précisément les deux
où le port diverge.

**Bilan sur les 4 régimes mesurés** (maxHP et armures posés par `--unit-stat`) :

| régime | necro (maxHP / armure) | meph (maxHP / armure) | NATIF | PORT | verdict |
|---|---|---|---|---|---|
| nominal | 8536 / 2662 | 9537 / 2008 | `bloodMephiston` | `necroWarden` | **diverge** |
| `haute` | 8536 / 2662 | 8536 / 2008 | `bloodMephiston` | `necroWarden` | **diverge** |
| `basse` | 8536 / **300** | 8536 / 2008 | `necroWarden` | `necroWarden` | concorde |
| `hp` | 8536 / 2008 | 9537 / 2008 | `necroWarden` | `necroWarden` | concorde |

Un modèle « plus de dégât relatif = mieux » — pré-armure **comme** post-armure — donne `necroWarden`
en nominal (moins de PV à dégât égal). Le natif dit l'inverse. **Aucun des deux modèles ne rend
compte du nominal.**

## 1bis. Le SEUIL D'ARMURE, qui MESURE le dégât employé — et réhabilite l'armure, autrement

La réfutation du §1 vaut contre la formulation « l'armure entre **parce que** 2662 et 2008 donnent
des dégâts différents » — ils n'en donnent pas, **à `d = 2044`**. Mais `GetDamageWithPiercing`
bascule de la branche PERÇAGE à la branche ARMURE quand `armure < d × 35 %` : ce **seuil dépend de
`d`**, donc le localiser **mesure `d`**.

Les régimes déjà joués le bornent : `necroWarden` reste préféré à armure **2008**, il perd à
**2662** ⇒ seuil ∈ ]2008, 2662[ ⇒ `d = seuil / 0.35` ∈ ]5737, 7606[.

- un **seul** coup (`avg = 2044`) donnerait un seuil de **715** — **RÉFUTÉ**, `necroWarden` gagne
  encore à 2008 ;
- les **trois** coups de l'ability (`3 × 2044 = 6132`) donnent **2146**.

**Prédit avant de mesurer, puis mesuré** — encadrement à 2100 / 2200, tout le reste inchangé :

| armure `necroWarden` | NATIF frappe | PORT |
|---|---|---|
| 2100 | `necroWarden` | `necroWarden` |
| 2200 | `bloodMephiston` | `necroWarden` |

⇒ **la bascule est entre 2100 et 2200**, et `2146` y tombe. `d` mesuré ∈ [6000, 6286] — soit
`3 × 2044`. Ce n'est pas un ajustement : la valeur sort de la loi native et du nombre de coups de
l'ability, la mesure n'a fait que la confirmer dans une fenêtre de largeur 100 sur une plage
possible de 0..3513.

**DEUX écarts du port sont donc nommés**, et ils se cumulent :

1. il passe le dégât d'**UN** coup (`first_by_damage_utility(state, cands, avg, avg)`) là où le
   natif emploie celui des **TROIS** ;
2. il n'applique **aucune armure** (`_target_utility` fabrique `healthDmg = dmin/dmax` bruts), donc
   il ne peut pas franchir de seuil.

## 2. Le candidat BLOCK — ÉLIMINÉ, lui aussi

`aiPredict` (attaque normale d'Uthar, régime nominal) :

| cible | armure | `armorBefore` | `healthDmgMin..Max` | scénario de block |
|---|---|---|---|---|
| `necroWarden` | 2662 | `null` | `3720..5577` | `blockScenarioCount = 0` |
| `bloodMephiston` | 2008 | `null` | `2604..3903` | `blockScenarioCount = 1`, `blockProbability = 30`, `blockKillDmg = 0`, `blockMightDmg = 0`, `willKillDmgEffective = 0` |

Deux faits, tous deux gênants pour l'explication par l'armure :

1. `armorBefore` est **`null`** — la prédiction est bien pré-armure **au sens du champ publié** ;
2. les dégâts prédits **diffèrent par cible** et **ne sont pas monotones en armure** : la cible la
   **plus** blindée prend le **plus** de dégât. L'armure ne peut donc pas être le facteur.

Ce qui distingue structurellement les deux cibles dans le résultat natif, c'est le **canal BLOCK** —
et `_target_utility` (`engine/runner/operations/damage_utility.py`) n'en modélise **rien** : son dict
pose `shieldBefore = 0` et ne porte aucune clé de block. Or c'est la cible **porteuse** du block que
le natif préfère.

**A/B joué, à une variable — le block est ÉLIMINÉ.** Régime nominal, `bloodMephiston` privé de son
block (`--unit-stat bloodMephiston:BlockChance=0,BlockDamage=0`, rien d'autre touché) : le natif
frappe **toujours `bloodMephiston`**. Le canal block n'est donc pas le facteur du classement, et
l'absence de cette clé dans le dict du port n'est pas la cause de la divergence.

⚠ `aiPredict` est **Attack-based** (`GetAllPredictions`, ability `69 Loki_NormalAttack`) : ce n'est
**pas** le nœud de dégât que le sélecteur branche sur son slot `+0x40`
(`MinMaxDamage(entities, 1)`). Il répond à une seule question — « le dégât prédit dépend-il de la
cible, et comment ? » — et sa réponse suffit à **éliminer** l'armure, pas à établir la loi.

## 3. Ce qui reste ouvert

- **La surcharge exacte.** `SortUnitsByDamageUtilitySelector$$Select` appelle le slot **`0x26`** de
  son service `(this+0x50)` avec `(owner, target, ownerPosition, Nullable<AbilityOrEffect>, deux
  `Func`, …, &minmax)`. Les slots `0x23..0x27` d'`IBattleQuery` sont les `GetAttackPrediction` ; la
  surcharge la plus référencée, `IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction`, a pour
  signature `(caster, target, casterPosition, ability, amount, damageProfileType,
  defenderInitialHealth, previousHitsPrediction)` et délègue au **slot 10** du service porté par
  `caster+0x30`, avec **`hits = 1`** en littéral. Ce n'est **pas** celle du sélecteur (qui passe des
  `Func`) — la bonne reste à isoler.
- **La NORMALISATION du composite.** À `d = 6132`, l'armure explique la bascule en dégât
  **ABSOLU** (`necroWarden` 3985.8 contre `bloodMephiston` **4124** au nominal ⇒ meph gagne), mais
  le composite du port normalise par `maxHP`, et cette normalisation rend `necroWarden` gagnant
  (`0.4669` contre `0.4324`). Or le bras `hp` (armures **égales**, maxHP différents) exige au
  contraire une normalisation — dégâts identiques, et le natif prend celle qui a le moins de PV.
  Les deux bras contraignent donc en sens opposés le même terme : **c'est là que la loi reste à
  lire**, et c'est le point à trancher AVANT tout fix. `UtilityType.Damage` = `DamageDealt` +
  `KillUnit` + `OverkillUnit` ; ici aucune cible n'est tuable (`willBeKill` et `mightBeKill` faux
  des deux côtés), donc seul `DamageDealt` est en jeu.
- **Les 4 consommateurs** du foyer partagé (`votann.AncestralFortune`, `final_justice`,
  `worldeaters`, `thousandsons`) n'ont donc **pas** été re-validés : il n'y a pas de fix à valider.

## 4. Pourquoi le trou a survécu à sa validation — et ce que ça prescrit

#419-r6-r1 a confronté ce foyer sur **Doombolt (1102)**, avec `FixedArmor = Armor = 0` sur toutes
ses cibles. Le régime était **doublement** dégénéré : profil `Psychic`, `PiercingDamageRatio =
**100**` ⇒ `max(0, d − armure, d × 100 %) = d` **quelle que soit l'armure**, et en plus l'armure
était nulle. Aucun montage sur ce profil ne peut discriminer l'étage armure.

⇒ **Toute garde future de ce foyer doit REFUSER un régime à perçage 100 % ou à armure nulle**, et
l'assertionner, sinon elle sera verte pour la même mauvaise raison. Les profils utilisables se
lisent dans `BC.Damage.DamageProfiles[].PiercingDamageRatio` : `Physical` 1, `Las` 10, `Blast` 15,
`Projectile` 15, `Bolter` 20, `Chain` 20, `Pulse` 20 … `Plasma` 65 ; **`DirectDamage` et `Psychic`
valent 100** et sont donc inutilisables pour cet axe.

## 5. Instrument, rejouable

```
python probe_527_votann_lot1_rouges.py --etage armure  --regime haute|basse|hp
python probe_527_votann_lot1_rouges.py --etage predict --regime nominal
python probe_527_votann_lot1_rouges.py --etage replay
```

`--etage replay` sépare **choix** et **dégât** (il rejoue le cast port avec la cible forcée à celle
du natif) ; `--etage armure` porte les trois bras de l'A/B ; `--etage predict` interroge la
prédiction native cible par cible.
