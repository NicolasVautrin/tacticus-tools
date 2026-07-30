# case-267 — la face PRÉDICTION lit les traits RUNTIME, elle ne les reconstruit plus

**Verdict : quirk porté et validé live.** `#264` (`1d798015`) avait fait consommer
`combatSnapshot.units[].traits` à `load_state`, donc à la face COMBAT. La face PRÉDICTION a son
PROPRE seam live (`engine/playbook/scene.py`) et **reconstruisait** toujours le substrat depuis
`gameconfig.unit(vis).traits`. Une face qui lit la mesure et l'autre qui la reconstruit, c'est le
fork « ce que le moteur fait ≠ ce que la prédiction annonce » — et il était **observable** :
sur `necroOverlord`, l'oracle natif annonce un coup `killSure`, le port d'avant annonçait un dégât
rogné à `HP−1` et donc « ne tue pas à coup sûr ».

## 1. Artefacts natifs (décompilé = vérité)

| Rôle | Symbole |
|---|---|
| Étage limites de la prédiction | `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` |
| Cap `Resilient` (appelé 2×, une par borne) | `IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` |
| **Le test de trait lui-même** | `IdunBattle.Entities.UnitExtensions$$HasTrait` |
| Résolution du composant | `IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent` |
| Les trois collections | `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` |
| Écriture en bataille | `IdunBattle.Operations.AddTraitOperation$$Execute` / `IdunBattle.Operations.RemoveTraitOperation$$RemoveTrait` |

### 1.1 La prédiction n'a AUCUN substrat de traits à elle

Corps de `ApplyResilientTraitDamageLimit(this, damage, defender, currentHealth, initialHealth,
isGuaranteedOverkill)`, lu verbatim :

```
if (!isGuaranteedOverkill) {
    if (UnitExtensions.HasTrait(defender, 0x3f1)          // 1009 = Resilient
        && initialHealth > 1 && currentHealth > 0) {
        y = Fix64(currentHealth - 1);
        if (damage > y) { *damage = y; return damage - y; }
    }
}
return Fix64(0);
```

`defender` est **l'entité ECS**, et `UnitExtensions$$HasTrait` est la MÊME fonction que la face
combat appelle — elle résout `GetBaseUnitComponent` puis délègue à
`BaseUnitComponent$$HasTrait` :

```
HasTrait(t) == !retirés(+0x50).Contains(t)
               && ( permanents(+0x40).Contains(t) || temporaires(+0x48).Contains(t) )
```

Aucune lecture de gameconfig nulle part sur ce chemin. Le canal `combatSnapshot.units[].traits`
(`#233`, `0231573`) est l'**invocation de cette fonction par valeur d'enum** : il rend l'ensemble
EFFECTIF, veto compris (structurellement inerte, `case-265`).

## 2. Le bug de port

`build_predictor` → `_hydrate_static_unit` → `UnitContext.from_snapshot(u, GC.unit(vis), …)`
posait `traits = gameconfig.unit(vis).traits` et laissait `traits_measured` à **faux** — si bien
qu'`entity_trait_names` re-dérivait par-dessus le pseudo-trait de grande-alliance. Deux
reconstructions empilées, là où le canal donne la réponse directement.

Or les traits de DÉPART viennent de `BattleConfiguration.Units[].Traits`, qui **n'est pas** le kit
gameconfig — et l'écart va **dans les deux sens** (mesure du 2026-07-30 sur les 175 unités du seed
BC : 5 en ont MOINS, 48 en ont PLUS). S'y ajoute ce que le kit ne peut pas porter par construction :
les traits **accordés en bataille** (`AddTraitOperation`).

## 3. Décomposition par étage (mesures)

Probe : `scripts/python/probe_267_predictor_traits.py`. Quatre montages, chacun avec sa contre-épreuve
« canal EFFACÉ » (`traits: null` sur toutes les lignes) qui rejoue **exactement l'état d'avant** sur
le MÊME pas et la MÊME tuile.

### 3.1 Le substrat (montages A / B)

| étage | mesure |
|---|---|
| A — égalité ligne à ligne, 2 lecteurs (`entity_trait_names`, `Scene.unit_state()["traits"]`) | 4/4 lignes, 0 écart |
| A — non-vacuité : ce que la reconstruction rate | `necroOverlord` +`Resilient` EN TROP |
| A — cas discriminant end-to-end | `_target_damage_limits(...)["target_has_resilient"]` : **True → False** |
| A — tri-état | `null` → reconstruction intacte (5 traits, `traits_measured` faux) ; `[]` → **0** trait, mesure |
| B — trait accordé en bataille (`DutyEternal` → `Stationary`) après `refresh_shields` | `Stationary` **présent** (absent avant) |

Montage B : le `predictor` est bâti **COLD avant** le cast et rafraîchi **après** — c'est le régime
réel de la boucle de décision (build 1×/runner, refresh 1×/pas). Sans la re-capture par pas, un trait
posé après le déploiement resterait invisible à la prédiction pour toute la bataille.

### 3.2 Agreement contre l'oracle natif (montage C) — le retournement de décision

Le cap borne à `currentHealth − 1` : l'écart de dégât qu'il induit vaut **structurellement 1 PV**, et
une tolérance d'arrondi le masquerait. On compare donc à l'**exact**, et surtout sur le `killSure`.

Régime nécessaire : `dmg ≥ PV` **sans** overkill. `overkillDmgPctOfHealth` vaut 100, et
`accum = (maxHP − curHP) + dmgMin` ⇒ à PV pleins, pas d'overkill tant que `dmgMin < 2 × PV`. Le probe
**calibre** donc les PV de la cible à 75 % du `dmgMin` natif mesuré sur un premier runner à PV énormes.

| couple (board, seed, attaquant) | PV cible | ORACLE natif | port MESURÉ | port RECONSTRUIT |
|---|---|---|---|---|
| `MC1_67` / 26701 / `ultraTitus` | 6267 | `(6267, 6267)` **killSure=True** | `(6267, 6267)` écart **0**, killSure=True | `(6266, 6267)` écart **1**, **killSure=False** |
| `C4_09` / 909 / `deathBlightlord` | 4695 | `(4695, 4695)` **killSure=True** | `(4695, 4695)` écart **0**, killSure=True | `(4694, 4695)` écart **1**, **killSure=False** |

Ce n'est pas « 1 PV » : c'est un **retournement de verdict**. La face prédiction d'avant déclarait
`necroOverlord` non tuable de façon garantie, sur un coup que le natif dit létal.

### 3.3 Non-régression à l'échelle (montage D)

Le câblage déplace la source des traits **sous tous** les gates de prédiction (limites de dégât,
conditions d'effets, pierce par trait, cardinal `Psyker`) : un cas discriminant vert ne dit rien des
autres paires. Roster aléatoire plein, drive au contact, agreement `±3` contre
`decisionView.attackPlans`, MÊME état, MÊME pas, seul le canal change :

| couple | paires comparables | MESURÉ | RECONSTRUIT |
|---|---|---|---|
| `MC1_67` / 777 | 11 | 11/11 | 11/11 |
| `MC1_67` / 31337 | 8 | 8/8 | 8/8 |
| `C4_09` / 909 | 13 | 12/13 | 12/13 |

Aucune paire ne change de verdict hors du cas discriminant ; le miss de `C4_09` est présent des DEUX
côtés, donc antérieur.

## 4. Fix

`engine/playbook/scene.py`, un seul foyer :

- `_seed_measured_traits(ctx_by_id, snap)` — écrit `ctx.traits = sorted(trait_names_from_ids(...))`
  et pose `ctx.traits_measured` sur chaque ligne du snapshot qui a un ctx. **TRI-ÉTAT** identique à
  `_unit_flag_from_snapshot` : champ absent ou `null` = non mesuré → on ne touche à rien (la
  reconstruction d'avant, à l'identique) ; une LISTE, `[]` comprise = mesure, on écrit.
- appelé à la fin de `build_predictor` (seed cold) **et** à la fin de `refresh_shields`, **après**
  l'hydratation des arrivants (`#53`), pour que les summons frais ne gardent pas le kit.

Portée : lignes `EntityType.Unit` **et** `Machine`. `build_predictor` hydrate les deux, et une ligne
`Machine` n'a pas de `visualId` — la reconstruction par kit y rendait donc un ensemble **vide** alors
que `HasTrait` répond bien sur elle (`ultraDreadnought` → `MachineOfWar`+`Imperial`, mesuré).

La troisième voie de construction de `Scene`, `from_state` (offline, sans RPC), lit
`StatsComponent.ctx` — le MÊME objet que `load_state` seede depuis le canal : elle hérite donc de la
mesure sans changement.

## 5. Validation

### 5.1 Garde dédiée — `tests/engine/test_predictor_traits_live.py` (nouveau)

7 tests, deux montages + un troisième pour la polarité inverse (`custoAtlacoya` +`SistersSilence`,
`astraDreir` +`DeathKorpsKrieg` — traits de DÉPART portés par le seul BC, sur `C4_09`/909, donc un
second couple (seed, board)). Chaque assertion positive est doublée de sa **contre-épreuve** sur
l'état canal-effacé : sans elle, un montage où la reconstruction tomberait juste ne prouverait rien.

**Rouge provoqué avant fermeture** : câblage neutralisé (`return 0` en tête de `_seed_measured_traits`),
la passe rend **5 failed / 1 passed** — le seul vert étant, par construction, la garde de non-vacuité
(elle mesure la reconstruction, pas le seed). Câblage rétabli : **7 passed**.

### 5.2 Non-régression (tests ciblés)

| lot | résultat |
|---|---|
| `test_predict_live`, `test_noblocking_prediction_live` | 4 passed |
| `runner/test_heavy_weapon_moved_prediction_live`, `runner/test_load_state_traits_live` (#266 / #264) | 7 passed |
| `test_aura_position_live`, `test_savage_echoes_prediction_live` | 2 passed |
| `runner/test_effect_immunity_live`, `runner/test_load_state_inactive_effects_live` (conditions de trait) | 18 passed |
| `runner/test_lascannon_pierce_offline`, `runner/test_ability_hits_channel_live` (pierce par trait, canal hits) | 16 passed |

### 5.3 Ce qui n'est PAS couvert

- Le montage C ne confronte que l'**attaque normale** (`decisionView.attackPlans`, filtre
  `kind == "normal"`). Les prédictions d'**ability** passent par le même `_target_damage_limits`,
  mais aucune paire ability n'a été confrontée dans le régime « cap mordant ».
- `Impervious` (2ᵉ trait de l'étage limites) reste un **no-op documenté** côté prédiction : sa charge
  runtime n'est pas captée par `combatSnapshot`. Le câblage rend son gate `target_has_impervious`
  fidèle, pas la charge.

## 6. Résidus documentés

- **`#267-r1` — 7 sites de la face PRÉDICTION relisent encore le kit gameconfig PAR `visualId`**, là
  où leur pendant COMBAT lit le substrat d'entité (`damage_model.target_trait_names(state, uid)` =
  `StatsComponent.ctx.traits`, donc la mesure depuis `#264`) :
  `prediction/_shared.py` (`_tgt_traits_names` de l'agrégateur DÉFENSE, `att_traits` et `tgt_traits`
  de `_apply_ally_attack_dmg_bonus`), `prediction/normal_attack.py` (4 sites, dont le `_tgt_traits`
  qui alimente `target_hit_multiplier`), `prediction/abilities.py` (`BigTarget`). Le pendant exact
  côté prédiction est `scene.ctx(uid).traits`. Tant qu'ils ne sont pas basculés, la face prédiction
  lit la mesure sur une partie de ses gates et le kit sur l'autre. Consommateurs concernés :
  `BeastSlayer_ExtraDmg`, `ConquerorImperative` (`Mechanical`), `LordOfTheHost_ExtraDamage`
  (`RapidAssault`/`Flying`), `target_hit_multiplier` (`BigTarget`).
- **`Scene.unit_state()["traits"]` lit `ctx.traits` BRUT**, pas `entity_trait_names(ctx, vis)` : en
  régime MESURÉ c'est correct (la mesure porte la grande-alliance — vérifié sur `necroOverlord`, qui
  y a bien `Xenos`), mais en régime NON mesuré (canal absent, ou ctx issu d'un spawn offline
  `operations/spawn.py`) le pseudo-trait d'alliance manque au contexte des `CreateActiveCondition`.
  Écart antérieur, désormais inerte dans le régime normal.
- **`UnitContext.from_snapshot` détecte `Swarm` via le kit** (`cfg.get("traits")`) pour attribuer le
  malus `Swarm_HitReduction` : cette lecture-là tourne AVANT le seed et reste sur le gameconfig.
  Même limite côté combat depuis `#264` ; aucune des divergences BC/kit mesurées ne porte sur `Swarm`.
- **`charged_by_id` reste VIDE** sur ce seam (aucun RPC n'expose `UnitComponent+0x190`) — inchangé,
  cf. l'en-tête de `Scene`.
