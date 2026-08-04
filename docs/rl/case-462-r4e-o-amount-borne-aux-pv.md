# #462-r4e-o — le tag `Amount` per-coup est BORNÉ aux PV restants

Trouvé en généralisant #462-r4e (3 boards × 3 seeds) : `astraBullgryn` vs `eldarFarseer`, le port
rendait le dégât **brut** là où le natif écrit le retrait **effectif**. `hp_after` identique des deux
côtés — écart de **RAPPORT**, pas de calcul.

## 1. L'étage qui borne, et sa valeur exacte

Trois maillons, tous lus au décompilé (`rnca9r7q6c`) :

1. `IdunBattle.Core.Services.StreamHelper$$GetDamageTags` écrit le tag `Amount` (`TagKey` **225**)
   depuis le champ **@+0** de la valeur de retour d'`IdunBattle.Operations.ApplyDamageOperation$$Execute`
   — pas depuis le `DamageAppliedResult`.
2. Ce champ est un **accumulateur** (memset à 0 en tête d'`Execute`) alimenté par **exactement deux**
   termes, tous deux des retraits **réellement appliqués** :

   ```
   amount  = FillUpStatComponent.Reduce(healthComponent, dar.healthDamage, ignoreMinimum: false)
   amount += ApplyDamageOperation.ReduceShield(unit, dar.shieldDamage)
   ```

3. `IdunBattle.Entities.Components.FillUpStatComponent$$Reduce` **est la borne** :

   ```
   applied = Math.Min(Math.Max(0, damage), Current)                 # Current @+0x18
   if (!ignoreMinimum && Minimum.HasValue)                          # Minimum @+0x1c, Nullable<int>
       applied = Math.Min(Current - Math.Min(Current, Minimum.Value), applied)
   Current -= applied ; <compteur @+0x24> += Math.Max(0, damage - applied) ; return applied
   ```

   Le **surplus** part dans le compteur @+0x24, jamais dans le retour.

**L'armure-pool n'entre pas dans `Amount`** : `IdunBattle.Core.Services.DamageAppliedResult$$.ctor`
reçoit un `armorDamage` et **ne le stocke dans aucun champ** ; `…$$get_Damage` rend `@+0x8 + @+0x4`
= bouclier + santé. Sans effet mesurable ici : aucun call-site de `_run_hits` ne passe `armor_pool`.

**L'application est PAR COUP**, et c'est structurel, pas déduit d'un chiffre : le `DamageAppliedResult`
que reçoit `Execute` porte un `hitIndex` **@+0x14**.

Recoupement indépendant : le **même** accumulateur est gravé dans `ActorStatisticsComponent+0x68`/`+0x6c`
(`last_hit_damage_taken`), ce que `components.py` documentait déjà.

## 2. Port

`damage_amount_applied` (`engine/runner/operations/damage_hits.py`), fonction de **module** — donc
point de mutation des contre-épreuves, comme `crit_gate_open`. `_run_hits` prend `hp_current` /
`hp_floor` (4 call-sites : normal, normal_like, ability, additional_hits) et compose `per_hit` avec
des PV restants **décroissants coup par coup**.

`total`, `per_hit_health` et `rolls` restent le **demandé** — `record_left_over_damages` et le
`didOverkill` per-coup en dépendent, et le natif y met bien le demandé (`dar.healthDamage`).
L'état final était déjà correct (`thc.reduce(total)` bornait) : **rien ne change côté PV**.

## 3. Rayon de souffle de `per_hit`

| lecteur | effet |
|---|---|
| `last_hit = per_hit[-1]` → `_record_last_hit_damage_taken` | **corrigé** — le natif y grave le même accumulateur (TimeFlux de `thousTerminator`) |
| dicts de diagnostic d'abilities (`blacklegion`, `spacewolves`, `behaviours/combat`) | comparés au live par leurs tests — alignés |
| `additional_hits.out["per_hit"]` | concaténation, même sémantique |
| `tools/damage_decomp.py` | outil de mesure, lit les deux côtés |

**Traces RL déjà ingérées : non contaminées.** La colonne `stream_events.amount` est peuplée depuis
`tags->>'Amount'` (`scripts/sql/012_stream_event_attribution.sql`), donc depuis le **live natif** —
déjà borné. Aucune trace ingérée ne porte la valeur brute du port.

## 4. Confrontation live

Probe `probe_462_r4e_o_overkill_amount.py` (4 régimes) + `test_overkill_amount_live.py` (3 tests) :

| régime | `live` | `off` avant | `off` après |
|---|---|---|---|
| `letal` MC1_67/31337 | `[1975, 1573, 2339, 1643]` | `[…, 2404]` (Σ 8291) | **identique** (Σ 7530) |
| `cadavre` C3_01/777 | `[2764, 3787, 979, 0]` | `[…, 2289, 2203]` (Σ 11043) | **identique** (Σ 7530) |
| `survivant` (`--hp-target 999999`) | `[3583, 3181, 3947, 4012]` | identique | identique |

`cadavre` est le régime **discriminant** : le coup 3 est écrêté *partiellement* (979) et le coup 4
tombe sur un cadavre (0) — « borner le coup létal » aurait rendu `2289` / `2203`.
Généralisation : `tauAunShi` (5 coups) bit-exact sur les trois régimes.

**Contre-épreuve** (`--mutate brut`) : `letal` et `cadavre` divergent et **retrouvent exactement**
les valeurs d'avant ; `survivant` reste identique — pas de sur-ajustement.

## 5. Résidu `#462-r4e-o-r1` — CARDINALITÉ des events (NON porté)

Quand **au moins deux** coups tombent après la mort (régime `multi_cadavre` : `--hp-target 2000`), le
natif émet le coup létal **puis un seul** event à `Amount` 0, et **rien** ensuite ; le port en émet un
par coup restant :

```
live=[2000, 0]     off=[2000, 0, 0, 0]        # meme etat, meme somme
```

Même motif sur `astraBullgryn` (4 coups) et `tauAunShi` (5 coups). Foyer natif : le **SITE (A)**
d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` —
`if (UnitExtensions.HasFlag(target, 8 = Overkilled)) { RecordHitStatistics ; AddLeftoverHit(…, 1) ; return; }`
— qui **précède** toute émission ; le flag est posé par
`IdunBattle.Entities.Components.UnitFlagsComponent$$Add(comp, 8)` sous
`dar.didOverkill && UnitExtensions.CanBeOverkilled(target)`. Le port n'évalue cette garde qu'à
l'**entrée du groupe** (`_apply_damage_pipeline`) : résidu de **granularité** déjà nommé dans
`damage.py`.

**Ouvert** : pourquoi le flag n'est posé qu'au coup *suivant* le coup létal. Candidat lu mais non
tranché — `Execute` **efface** `dar[+0xf]` (`didOverkill`) sous une condition qui dépend des
**membres** du squad (`if (uVar28 != 0) dar[+0xf] = 0`, où `uVar28` dérive du compte de membres tués).

Le probe **garde la forme** de l'écart (`live` préfixe de `off`, reste nul, sommes égales) : il rougit
si l'écart change de nature, et aussi le jour où le résidu sera porté.

## 6. Non couvert, nommé

* le terme `+ ReduceShield` de la formule n'a **pas** été exercé sur une cible à **bouclier non nul**
  (les trois régimes ont `shield = 0`) — la borne santé, elle, l'est ;
* le plancher `Minimum` (HP-floor Hypersensory) n'est **pas** confronté live (aucun régime ne le pose) ;
  il est porté à l'identique du natif et couvert par `HealthComponent.reduce`, déjà en place ;
* la borne sur le chemin **ABILITY** et **coups additionnels** est câblée (mêmes call-sites) mais
  confrontée seulement en **non-régression** (`test_damage_ability_live`,
  `test_additional_hits_amount_bounds_live`), pas dans un régime overkill dédié ;
* le résidu `#462-r4e-o-r1` ci-dessus.
