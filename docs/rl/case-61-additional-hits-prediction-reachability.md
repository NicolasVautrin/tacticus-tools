# Case #61 — canal additional-hits (#179) côté PRÉDICTION : preuve de reachability

> **Statut : la tâche telle que déposée est INVALIDE** (2026-07-22). #61 demandait de câbler le
> canal `EffectAdditionalHits` (#179) dans les prédictions d'ABILITY. La recon décompilée montre
> qu'**aucun consommateur générique de ce canal n'existe côté ability** : le porter serait un
> *fork* (inventer un comportement que le natif n'a pas). Ce qui subsiste est une tâche
> DIFFÉRENTE et bien plus étroite — §4.
> Prérequis appliqué : `feedback_verify_reachability_before_porting_decision` (prouver la
> reachability AVANT de porter une face) et `feedback_check_own_port_before_re` (1 natif → N ports
> = divergence structurelle).

## 1. Surface complète du canal côté PRÉDICTION

Deux fonctions, et deux seulement :

- `AActiveAbility.GetAdditionalHitsFromEffectsForPrediction @180fb0ed0` — recopie le contexte
  d'attaque puis délègue à `AdditionalHitsFromEffects.GetAdditionalHitsFromEffects @180e59e50`
  (champs lus : `+0x18` monde, `+0x40`, `+0x48` de l'ability).
- `AActiveAbility.AddAdditionalHitsToPrediction @180faff30` — itère les hits collectés, construit
  chaque hit via `AActiveAbility.GetEffectAdditionalHitPrediction @180fb1260` (1 seul appelant :
  celle-ci) et empile par `DamagePredictionResult.Add`. Le blocage de bloc par défaut passe par
  `DamagePredictionResult.get_DefaultBlockScenario`.

**Appelants (xrefs exhaustives, les 2 fonctions ont le MÊME couple) :**

| Appelant | VA | Statut |
|---|---|---|
| `ALoki_NormalAttackAbility.PredictAttack` | `@1811affda` / `@1811b010a` | **déjà porté** — `make_normal_attack_predictions` (`playbook/prediction.py`, consommation `additional_hit_groups`) |
| `MV71SniperDroneSquadAttackAbility.PredictAttack` | `@18110af1a` / `@18110b04d` | **non porté** (cf. §3) |

Il n'existe donc **aucun** chemin natif où une prédiction d'ability générique
(`generate_multi_hit_attack_prediction`, `make_damage_predictions` côté offline) consulte ce
canal. Le gap constaté offline (canal absent de ces deux fonctions) **mirrore fidèlement le natif**.

## 2. Surface côté EXÉCUTION (distincte, pour mémoire)

`AdditionalHitsFromEffects.GetAdditionalHitsData @180e589b0` et
`GetAdditionalHitsFromEffects @180e59e50` sont appelées par :

- `AttackDamageOperation.ExecuteAdditionalHitsWithoutDamageProfileType @180e5ec32` ;
- `ExecuteAdditionalHitsWithDamageProfileTypeOperation.Execute @180e707d2` / `@180e7082d`
  (nœud DSL `DSLFactory.ExecuteAdditionalHitsWithDamageProfileType @180def640`).

Conforme à `case-65` : les bornes du roll d'exécution diffèrent de l'affichage de la prédiction
(`amount = midpoint` + spread) — incohérence native à mirrorer telle quelle, toujours sans
consommateur combat porté offline.

## 3. Le seul appelant non porté : `MV71SniperDroneSquadAttackAbility`

`PredictAttack @18110a5f0` se scinde sur `MV71SniperDroneSquadAttackAbility.IsMeleeAttack` :

- **mêlée** → délègue intégralement à `ALoki_NormalAttackAbility.PredictAttack` (donc rien de neuf) ;
- **distance** → chemin propre : résout une cible (aucune cible ⇒ **prédiction vide** — `memset`
  0xc0 + liste vide) ; lit un `StatComponent.CurrentValue` et stocke `valeur + 1` (rôle non établi,
  cf. §5) ; résout une **configuration d'unité** depuis la constante chaîne de l'ability (l'unique
  constante chaîne de `MV71SniperDroneSquad` est `unitId = tauSmnDroneSniper`) ; construit la
  prédiction via le service de prédiction (slot `0x24`) **avec cette config** ; puis
  `GetAdditionalHitsFromEffectsForPrediction` + `AddAdditionalHitsToPrediction`.

Autrement dit : l'attaque à distance du Marksman est prédite **avec les stats du drone sniper**.
Cohérent avec l'observé (`hypotheses.md` H50/H53, `journal.md` : « MV71 drone-summons utilisant le
stat de Sho'syl »).

**Porteurs (gameconfig)** — la tâche successeur est donc VALIDABLE au sens de
`feedback_no_unvalidatable_ability_ports` :

- `tauMarksman` (**lineup**, spawnable en runner) porte le passif `MV71SniperDroneSquad`
  (triggered `1119`) ; ability d'attaque = `MV71SniperDroneSquadAttack` (`1076`).
  Aussi sur `tauNpcMarksman`, `tauBossMarksman{,LHE,Inc}`.
- Drone invoqué : `tauSmnDroneSniper` (mêlée Physical 1 coup ; **distance Piercing portée 4,
  1 coup** ; traits Summon/Flying/Mechanical/RangedSpecialist ; passif SaviorProtocols).
- **Levier additional-hits pour la validation** : `AstartesBanner` (`templAncient`, **lineup**,
  Black Templars) = constantes `{range: 2, extraHits: 1}` — aura d'alliés à portée 2, donc un
  drone sniper placé près de l'Ancient PORTE bien un `EffectAdditionalHits` pendant son attaque à
  distance. Le scénario discriminant est craftable (`feedback_adapt_teams_to_validation_objective`).

État offline : seules les entrées d'énumération existent (`active_ability_type.MV71SniperDroneSquadAttack
= 1076`, `triggered_ability_type.MV71SniperDroneSquad = 1119`, `effect_type.MV71SniperDroneSquad_InitialDmg
= 1132` / `_ResetInitialDmg = 1133`, `utility_type.MV71SniperDroneSquad_ClosestToParent = 55`) —
**aucune implémentation**.

## 4. Conclusion et tâche successeur

- **#61 (câbler le canal dans les prédictions d'ability) : CLOS, sans port.** Le natif n'a pas ce
  chemin ; l'absence offline est correcte. Toute écriture dans
  `generate_multi_hit_attack_prediction` / `make_damage_predictions` serait une invention.
- **Successeur — porter `MV71SniperDroneSquadAttack` (1076)** `[opus]` : attaque déclenchée dont la
  prédiction à distance utilise la config du drone, avec la branche mêlée qui retombe sur l'attaque
  normale, et le canal #179 en aval. Validable (roster `tauMarksman` + `templAncient`).
  Ampleur réelle à cadrer : la sélection de cible, le compteur `+1` (§5) et les effets 1132/1133
  ne sont pas encore établis.

## 5. Points non établis (à trancher au moment du port)

- Rôle du `StatComponent.CurrentValue + 1` stocké dans l'état de `PredictAttack` (nombre de drones
  en jeu ? index de coup ?) — le stat lu n'a pas été identifié.
- Sémantique de la sélection de cible du drone (la requête passe par un service ; H53 soupçonne une
  **portée minimale ~2 hexes**, jamais confirmée en duel contrôlé).
- Effets `MV71SniperDroneSquad_InitialDmg (1132)` / `ResetInitialDmg (1133)` : non lus.
