# #287-r11-r2-r1-r1 — le `0` de `GetUnitMaxRange`, et le seed BC qui rend son régime atteignable

Le port mappait sur `1` le `0` que rend `IdunBattle.Core.Services.BattleQuery$$GetUnitMaxRange`.
Le résidu le donnait pour **NON EXERCÉ** (`tauSmnDroneSniper` porte une arme de portée 4). Il l'est
désormais : `GetUnitConfig` lit **`BC.Units[]`**, donc le régime se monte en vidant `Weapons` dans un
seed BC custom — et le natif y **refuse** un cast que le port acceptait.

## 1. Le corps natif, et les deux fautes du port

`BattleQuery$$GetUnitMaxRange(unitId)`, décompilé relu :

    config = GetUnitConfig(unitId);
    if (config == null)           return 0;
    if (config.Weapons == null)   return 0;
    max = 0;
    foreach (w in config.Weapons) max = Math.Max(max, w.Range.HasValue ? w.Range.Value : 1);
    return max;                                     // liste VIDE -> 0

`mv71._drone_attack_range` en portait une **copie locale** :
`[int(w.get("Range") or 0) ...]` puis `return mx if mx > 0 else 1`. Deux fautes, **de sens opposé** :
`or 0` lit `0` là où le natif lit `1` (arme sans portée), et `mx > 0 else 1` rend `1` là où le natif
rend `0`. Elles se **compensaient** exactement sur le seul régime exercé (mêlée pure, `[Range: None]`
→ `1` des deux côtés) — c'est ce qui les a laissées vivre. Les quatre régimes à `0` divergeaient
tous ; les trois régimes à portée non nulle s'accordaient déjà.

Réparation : `_drone_attack_range` **DÉLÈGUE** à `engine.services.battle_query.get_unit_max_range`
(déjà juste, écrit par #287-r11-r1), en **forme B** — deux mirrors de la même fonction native libres
de diverger étaient le vrai défaut.

## 2. Ce que la portée décide

`mv71._pick_tile` construit son anneau par `1 <= d <= rng`. À `rng = 0` l'intervalle est **vide** :
aucune candidate, `PickTile` rend `None`, et `MV71SniperDroneSquadAttackAbility$$GetDynamicInvalid
TargetReason` rend `1 = TargetingRule.ValidRequest` (refus). À `rng = 1` les tuiles **adjacentes** à
la cible redeviennent candidates. Direction **PERMISSIVE**, la même que celle que #287-r11-r2-r1
vient de fermer.

## 3. Le régime est atteignable — `GetUnitConfig` lit la BC

Son décompilé parcourt `this.<+0xa0 : BattleConfiguration>.<+0x80>` et compare `ConfigId` : c'est
`BC.Units[]`, que `rl_duel build --seed-bc` remplace. `buildNormalizedBC` ne touche **jamais**
`Weapons` (vérifié : aucune écriture dans `normalize-bc/json-build.ts`). Mesure du 2026-08-07 :
**12 des 175** entrées du seed portent déjà `Weapons: []` (MoW et décor), donc le régime existe en
vrai — mais pas sur le drone, d'où le montage.

## 4. La confrontation LIVE

`probe_287r11r2r1r1_portee_nulle_live.py`, board `C3_47`, montage **dérivé** de `degage`
(`probe_287r11r2r1_los_summon_live.MONTAGES`) **à une variable près** : `(0,2)` est LIBÉRÉE et
`(1,4)` occupée.

⚠ **La dérivation n'est pas cosmétique — elle est ce qui rend le témoin discriminant.** Joué sur
`degage` tel quel, le probe a rendu témoin `0x1` = port `0x1` et le contrôle « le montage ne
DISCRIMINE pas » a rougi : la seule tuile libre claire y est à **d=3**, donc l'anneau de rayon 1 du
port d'avant était vide lui aussi et refusait pour la mauvaise raison. `(0,2)` est claire et à
**d=1**.

⚠ **Le substrat du port est ALIGNÉ, et c'est déclaré** : le port lit le catalogue gameconfig, le
natif lit la BC. Sans alignement (`substrat_sans_armes()` fait voir `weapons: []` au port pour ce
seul unitId), le probe mesurerait la divergence des CANAUX, pas l'étage. Le témoin reçoit le même
substrat aligné.

| bras | seed BC | rayon vu par le port | natif | port | témoin (mapping `0 -> 1`) |
|---|---|---|---|---|---|
| `armes` | normal | 4 | `0x0` | `0x0` ×2 | `0x0` ×2 |
| `sans-armes` | `Weapons: []` | **0** | **`0x1`** | `0x1` ×2 | **`0x0` ×2** |

Géométrie mesurée sur les deux bras (contrôle de montage) : **1 libre claire** — `(0,2)`, à d=1 — et
**10 masquées**. **Les deux verdicts natifs sont exercés** ; la vue rouge est de **2 SOUS-refus**,
sur les deux porteurs du gate (la classe `1076` et l'aiguillage `_NormalAttackTargeting`).

## 5. Les cliquets et la non-régression

`tests/engine/test_287r11r2r1r1_portee_nulle_offline.py`, **16 tests / quatre étages** : la
délégation vérifiée par **MORSURE** (un patch sur le foyer doit se voir à l'appel) ; les **huit**
régimes de `GetUnitMaxRange`, chacun avec le fragment de décompilé qui le justifie ; la
**compensation** des deux fautes, re-jouée pour montrer où le corps d'avant ne divergeait PAS ;
l'effet sur l'anneau de `PickTile` (`0` refuse, `1` accepte, sur le MÊME état) ; et l'existence du
régime, **dérivée** du gameconfig avec assertion de non-vide.

Vue rouge sur l'arbre témoin (`git archive origin/master`) : **5 failed** pour ce fichier ;
**16 passed** après.

Non-régression : `probe_287r11r2r1_los_summon_live.py` reste **OK** (0 SUR-refus, 0 SOUS-refus,
vue rouge 2 SOUS-refus au témoin, `{0x1: 2, 0x0: 2}`), `test_mv71_sniper_drone_live.py` **5 passed**,
`test_419r1tr14r5_normal_attack_dispatch_live.py` **6 passed**.

## 6. Ce qui n'est PAS couvert

* **Le régime `Range` explicitement `0`** (config présente, valeur `0`) n'est exercé qu'offline : le
  seed n'en porte aucun exemplaire.
* **Le second consommateur du même foyer** — `SendInTheNextWaveAbility$$GetSpawnedUnitRange` — n'a
  pas été re-confronté ; il lisait déjà `get_unit_max_range`, donc rien n'a bougé pour lui.
* **La divergence de CANAL** (catalogue gameconfig côté port vs `BC.Units[]` côté natif) est
  contournée par alignement dans le probe, pas fermée. Elle est inerte tant que les deux coïncident,
  ce que `catalog_inject.validate` vérifie par ailleurs.
