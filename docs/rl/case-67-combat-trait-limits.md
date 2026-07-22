# Case #67 — étage LIMITES du COMBAT (member-cap / Resilient / bypass Blast) à l'EXÉCUTION

> Frère de #30/#60bis (member-cap du DIRECT) et de #56/#57d (limites côté PRÉDICTION). Ici : le
> câblage de l'étage `ApplyTraitDamageLimitsToDamage` dans l'EXÉCUTION offline des attaques et
> abilities (`_run_hits`), avec trois découvertes discriminées live. Probe :
> `probe_67_combat_limits.py` (runs 670xx, session 71, build gqfc5mff6c).

## 1. RE — où vivent les limites à l'exécution

- **Attaque normale** : `AttackDamageOperation.ExecuteHit @180e5eff0` appelle PAR COUP une
  routine de prédiction per-coup (slot 4 de l'interface `DAT_183287ef8`) qui produit les cellules
  min/max du coup, **capées par les limites AVANT la résolution** ; le slot 8 résout la plage
  (mirror `RandomlyResolveMinMaxDamage @181038600` = `rng.Next(min, max+1)` **SANS gate
  min==max** — largeur 1 consomme quand même 1 tirage) ; puis `CalculateDamageOperation
  @18102dc30` (slot 0x42 de `DAT_1831d3468`) splitte bouclier/armure-pool/block. Les wrappers
  mode-1 `ApplyTraitDamageLimitsToAttackDamage @18102c510/@18102c5b0` sont virtual-only
  (la variante @18102c5b0 cape les cellules `struct+0x10/+0x18`).
- **Ability/splash** : `CalculateAbilityDamage @18102cb50` reçoit le dégât DÉJÀ résolu et appelle
  `ApplyTraitDamageLimitsToDamage(2, &dmg, &dmg, profil, cible, attaquant, 0, hp=hc+0x18, 0,
  param_6, param_7, ...)` — la MÊME cellule deux fois (dégénéré par construction) → cap
  SCALAIRE post-tirage. Ordre natif : part bouclier `iVar20 = min(dmg, shield)` soustraite AVANT
  le pipeline, ré-additionnée après (résidu documenté §5).
- **Core `ApplyTraitDamageLimitsToDamage @18102c650`** (déjà porté #56, partagé prédiction) :
  1. `total = Fix64(param_11 − param_9) + Fix64(param_12) + *param_3` (cellule MIN pré-cap) ;
  2. `ApplyGroupUnitDamageLimit @18102bfe0` sur les 2 cellules — **flag = octet 0 CONSTANT**
     (`in_stack & 0xffffff00`) : l'overkill ne bypasse JAMAIS le member-cap (seul Resilient est
     gaté) — l'orchestrateur du port passait `overkill` comme flag : **déviation corrigée** ;
  3. `IsOverkill @181032db0` (une fois, depuis la cellule MIN) ;
  4. `ApplyResilientTraitDamageLimit @18102c3a0` ×2 (trait 0x3f1=1009 : cap à `param_9 − 1`,
     gates `param_11 > 1` et `param_9 > 0`, sauté si overkill) ;
  5. mode 1 seulement : `ApplyImperviousTraitDamageLimit @18102c190` (trait 0x1c=28, gauge
     StatComponent : <100 → 0 dégât, ≥100 → param_6+param_7) ;
  6. `HasTriggeredAbility(0x5d4=1492)` → cap boss `max(param_9 − maxHp×const(0x12)/100, 0)`.
- Rappel #30 : `ApplyTraitDamageLimitsToDirectDamage @18102c9b0` = group-cap SEUL (profile=NULL,
  pas de Resilient) — le port `execute_direct` est complet tel quel.

## 2. Découvertes discriminées LIVE (probe_67_combat_limits.py)

1. **Cap des BORNES avant le tirage (attaque)** — run 67101 tour létal : live
   `[505, 541, 602, 206]` avec coups 1-2 bit-exacts offline puis coup 3 divergent (offline tirait
   ≥809 en pleine largeur puis capait ; live a tiré 602 DANS `[lo, cap=808]`). La largeur du
   modulo change quand le cap est partiel (`min < cap ≤ max`) ⇒ « caper la valeur tirée » n'est
   équivalent que pour les caps totaux. Fix : capage des bornes puis
   `next_internal(lo_c, hi_c+1)` TOUJOURS consommé (mirror slot 8 : largeur 1 = 1 tirage).
   Après fix : tours létaux bit-exacts (67111 `[628,539,345,0]`, 67121 `[574,519,28,0]`,
   67301 `[794,592,19,0]`).
2. **Ancrage de la porte overkill : `param_11` = HP AU DÉBUT DE L'ATTAQUE** (pas hpMax) et
   `param_12` = ROGNÉ cumulé de la cellule MIN des coups précédents. Discriminants :
   - 67201 tour létal `hp_départ 784 ≠ hpMax 7530` : le coup rem=1 a TUÉ (accum
     `(784−1)+rogné(584)+lo(630) = 1997 ≥ 2×784` — l'ancrage hpMax prédisait « fermé ») ;
   - 67111 `hp_départ 1513` : rem=1 TENU à 0 (`2167 < 2×1513`) ;
   - 67081 coup2-capé/coup3-létal : excluent `p12 = 0` ET `p12 = brut-cumulé`.
   La PRÉDICTION garde son ancrage hpMax (`compute_prediction_overkill`, appelant
   PredictAttackRaw distinct, validé tel quel).
3. **Amount-0 émis** : un coup capé à 0 (rem=1, Resilient) émet un event step-4 `Amount: 0`
   (67111) ; en revanche le natif N'ÉMET PLUS de coups après la MORT de la cible (67071 : 1 seul
   event pour 3 hits offline) — gate natif = cible vivante, pas amount>0.
4. **`--hp-target` fausse les bornes de roll** (artefact HARNAIS) : rolls dérivés de ±0,3 à 2,4 %
   vs natif (67081/67091) ; à hp NATIF les mêmes rolls sont bit-exacts (67093 : `[768,635,742,
   859]` à l'unité). Ne JAMAIS valider des valeurs de roll sous hp-target ; s'en servir seulement
   quand le verdict est masqué (`Amount = min(roll, hp)`).
5. **Découvertes opérationnelles harnais** : `applyAction` accepte les gestes des unités
   ENNEMIES hors de leur tour (le cast manuel du hive ennemi ne nécessite aucun flip) ; une
   unité qui a déjà agi no-op silencieusement (`ok=True, mutated=false`) → tour frais requis ;
   la réponse `applyAction` embarque la cascade complète (events step-4 avec `Amount`,
   `UnitStats_RemainingHealth`, `Attack_WasMemberKilled`, `Active_Ability_Type`) — plus besoin
   d'`aiPlayByUnit captureEvents` pour mesurer per-coup ; le volet feu de FireOfAbsolution
   (event `eff=5, ab=None`, probabiliste ~1 run/2) arrive DANS l'action de l'attaque — à
   filtrer par `Active_Ability_Type`.

## 3. Port (#67)

- `runner/operations/damage.py` :
  - `_target_limits` (helper) : champs statiques cible depuis ECS+gameconfig (mirror du
    `_target_damage_limits` prédiction) — `max_health` = **hp au début de l'attaque** (cf. §2.2),
    fast-path None si cible mono-membre sans Resilient ;
  - `_run_hits` : étage limites per-coup — voie ATTAQUE (mode 1) = cap des bornes
    puis `next_internal(lo, hi+1)` toujours consommé ; voie ABILITY (mode 2) = cap scalaire
    post-tirage ; porte overkill `(hp_départ − rem) + rogné + cellule_MIN ≥ 2×hp_départ` ;
  - les 3 appelants (`execute` mode 1 ; `execute_ability_attack`/`execute_normal_like` mode 2)
    threadent `limits` + `limits_hp`.
- `services/trait_damage_limits.py` : flag du group-cap = `False` constant (mirror octet 0 du
  core) — l'ex-passage d'`overkill` était une déviation inexercée (le member-cap tiendrait
  désormais même sous overkill massif, conforme live).

## 4. Validation

- `probe_67_combat_limits.py` — 4 scénarios, verdict 4/4 OK (seeds 673xx, re-runs 670xx-672xx) :
  - **swarm** : Vindicta 4×Flame r2 vs scarab PLEIN 2218/5 → live == offline == `[443,443,444,
    444]`, hp final 444 exact (mirror du ground-truth 60102) ;
  - **blast** : astraOrdnance (profil Blast = HitsMultipleMembers) → la frontière est TRAVERSÉE
    (1 coup 2218, kill), off == live — bypass confirmé à l'exécution ;
  - **résilient** (astraYarrick hp natif, attaques répétées) : 3 tours bit-exacts par run, tour
    létal capé `rem−1` puis queue à 0, tenu à EXACTEMENT 1 PV des deux côtés ;
  - **overkill** (hp-target 300) : porte ouverte dès le coup 1, mort des deux côtés.
- Régression : gardes `test_damage_roll_live` + `test_runner_attack_live` 4/4 ; stages 12345 =
  100 % partout (pred 9/9, util 9/9, ability 10/10, move 15/15) ; 2468 = baseline exacte
  (8/8, 8/8, 12/12, move 15/17 = generator-overfire + pos-downstream-of-ability).

## 5. Restes / résidus documentés

- **Bouclier × limites (ability)** : `CalculateAbilityDamage` cape le reste POST-part-bouclier
  (`iVar20 = min(dmg, shield)` ré-additionné) ; le port cape AVANT le split (= ordre
  attaque/prédiction). Identique tant que shield=0 — à départager si un swarm/Resilient
  BOUCLIER apparaît un jour.
- **Coups post-mortem** : le natif cesse d'émettre (et probablement d'exécuter) les coups après
  la mort de la cible ; `_run_hits` continue de tirer les coups restants → dérive du flux MT
  APRÈS un kill mi-attaque dans une sim multi-actions offline (les replays per-action
  re-synchronisent via dumpRng). Axe séparé si un cas d'agreement le remonte.
- **Impervious (28)** : gauge StatComponent non captée offline → no-op documenté (comme la
  prédiction). Porteurs = boss (non spawnables runner) — invalidable, non porté (doctrine).
- **Cap boss 0x5d4=1492** : `HasTriggeredAbility` non vérifié offline → no-op documenté.
- **FireOfAbsolution** : le volet feu-sur-cible probabiliste (event `eff=5` dans l'action,
  ~1 run/2) n'est pas modélisé par `execute()` offline — vecteur after-hit d'ability séparé,
  hors périmètre limites (le feu-TUILE, lui, est porté #136/#30).
