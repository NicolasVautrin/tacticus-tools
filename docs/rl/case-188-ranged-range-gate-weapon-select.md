# Case #188 — Weapon-select : porte de PORTÉE ranged + fallback MÊLÉE hors portée

**Status : PORTÉ (offline smoke + décompilé). Gap LATENT** (jamais exercé par l'IA : une tuile
d'attaque légale a toujours la cible dans la portée de l'arme choisie → la porte ne mord que les
prédictions HORS-PORTÉE que l'IA n'émet jamais). Zéro régression sur les chemins exercés **par
construction**. Découvert par fable-solver pendant #184 (sweep aiPredict, cf. case-184 §gaps#2).

## RE natif (VAs gqfc5mff6c)

`GetAttackWeaponForDefaultNormalAttack @18105ea60` (variante complète, distance-aware) :

1. `rangeType = GetAbilityAttackRangeType @181059fe0` de l'attaque normale (69).
   - `0` (défaut) / `2` (Ranged) → branche ranged (fall-through).
   - `1` (Melee) → `FindMeleeWeapon` ; return.
   - `3` (MeleeOrRanged) → `!HasFlag(att, 0x15) && AreUnitsInMelee @1810584d0` → `FindMeleeWeapon` ;
     sinon branche ranged. (`AreUnitsInMelee` = `AreTilesAdjacent @18109d740` att↔cible = adjacence
     HEX élévation-gatée, cf. #187.)
2. Branche ranged (queue) : `dist = FUN_1800051a0(...tiles...)` puis
   `FindRangedWeapon @181059ae0(att, ..., dist)`.

**`FindRangedWeapon @181059ae0` — LA PORTE DE PORTÉE :**
```
iVar6 = StatComponent.get_CurrentValue(rangeStat)          // bonus de portée (DAT_1831b8008)
for each weapon w of att:
    if !WeaponProfile.get_IsMelee(w)                        // arme ranged
       && dist <= w.Range + iVar6:                          // (param_5 <= local_88[0] + iVar6)
        set.Add(w)                                          // incluse SEULEMENT si en portée
return SelectMaxRangeWeapon(set)    (ou SelectBestDamageWeapon si tuile cible fournie)
```
`w.Range` = `weapon+0x24` (Nullable<int>). `SelectMaxRangeWeapon @181071dd0` sur set VIDE → renvoie
`0` (null). Quand `FindRangedWeapon` renvoie null (aucune ranged en portée), le jeu retombe sur
l'arme MÊLÉE. `rangeStat` (iVar6) = **0 sur tous les units connus** (sweep case-184 : boundary
exactement à `Range`, pas `Range+bonus`).

**Règle nette (rangeType 3) :** `dist==1` (adjacent) → mêlée ; `2 <= dist <= Range` → ranged ;
`dist > Range` → mêlée (fallback). Overloads : `@181059730` (2-arg, sans porte, collecte toutes les
ranged), `@181059a40`/`@181059ae0` (dist-gated). La queue de `@18105ea60` appelle la dist-gated.

## Mesure (fable, sweep aiPredict seed 2024 MC1_67, case-184 §gaps#2)

bloodMephiston (RapidAssault, mêlée 3 coups / ranged Range-2 2 coups) : natif prédit **mêlée
(3 coups)** depuis TOUTES les tuiles movables SAUF (4,6)/(3,7) à hex-dist 2 = Range → **ranged
(2 coups)**. dist 1 (adjacent) = mêlée, dist 2 = ranged, dist >=3 = mêlée. Confirme `rangeStat=0`
(boundary à Range) et le fallback mêlée hors portée.

## Port

`engine/services/battle_query.py::get_attack_weapon_for_default_normal_attack(..., dist=None)` :
branche ranged filtre `in_range = [w for w in ranged if dist <= w.Range]` ; `cand = in_range or
melee or ranged` (hors portée + mêlée dispo → mêlée = null natif ; pas de mêlée → garde ranged, tuile
illégale). `dist=None` → legacy (ranged dès non-adjacent). `select_weapon_pierce(ctx, is_adjacent,
dist=None)` propage `dist`. Threadé depuis :
- `prediction._weapon_pierce(scene, att_id, is_adjacent, dist)` ← `make_normal_attack_predictions` :
  `dist = hexgeo.distance(attack_pos, t_pos)`.
- `runner/damage_model.select_weapon` / `select_weapon_pierce` : `dist` hex déjà porté.

`is_adjacent` (porte d'élévation #187) reste le déclencheur mêlée ; `dist` ne pilote QUE la porte de
portée ranged. `rangeStat` omis (=0) — à réintroduire si un unit à stat de portée positif surgit
(`DAT_1831b8008`, `StatComponent.get_CurrentValue @181059ae0`).

## Zéro régression (par construction) + validation

Sur une tuile d'attaque LÉGALE, la cible est dans la portée de l'arme choisie → `dist <= Range` pour
toute tuile ranged légale → `in_range` non vide → ranged INCHANGÉ ; dist 1 → mêlée inchangé. Le
fallback ne mord que `dist > Range` (tuiles hors-portée = jamais évaluées par l'IA). smoke_188 9/9
(mixed adjacent→mêlée, dist2==Range→ranged, dist3>Range→FALLBACK mêlée, dist=None legacy→ranged,
ranged-only sans fallback, melee-only jamais ranged) + import-sanity prediction/damage_model.
**Honest closer déferré** : confront LIVE sur une prédiction hors-portée (l'IA ne l'émet pas
naturellement → nécessiterait de forcer une query hors-portée).
