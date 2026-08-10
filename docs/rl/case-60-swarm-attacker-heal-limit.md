# Case #60 — trait Swarm : face ATTAQUANT (hits = membres vivants) + heal-limit GroupUnit

> Suite #57a (feed `extra_hits_cur_by_id`, prédiction) et #57d (member-cap DÉFENSE bit-exact).
> Ici : la **dérivation offline autonome** du malus de hits (runner + attribution) et les faces
> heal-limit. Probe : `probe_60_swarm.py` (runners 23/24/25, seeds 60002-60005, session 71).

## 1. RE — l'artefact natif est un arbre DSL

`SwarmAbility` (ability **0x3ff=1023**, accordée par le trait `Swarm`) :

- **`CreateBehaviour @181225e20`** =
  `AddOrUpdateStaticStatModifierEffect(Self@+0x148, effectType 0x3fd=1021 Swarm_HitReduction,
  statType 0x11=EXTRA_HITS, Negative(Min(Difference(StatAmount(Self, 20, part 3=INITIAL),
  Const1@factory+0xc0), StatAmount(Self, 20, part 4=MISSING))))`
  = **`ExtraHits −= min(nrOfMembers − 1, membres MORTS)`** (plancher structurel 1 hit — i2 :
  « For each member defeated, the swarm attacks with 1 fewer hit »).
- **`CreateTrigger @181225f50`** = `(On(UnitRepaired=49,1) | On(UnitHealed=44,1) |
  On(UnitMemberDeath=48,0) | On(UnitRevived=46,1)) & OwnerIsTarget |
  OnOwnerSpecificAbilityInit(1023)` — exactement les événements qui changent le compte de membres.
- **Stat 20 (NUMBER_OF_MEMBERS)** : branche DÉDIÉE de `GetStat @180ed30d0` — la jumptable
  (@180ed3c40, entrée 0x14 → handler @180ed3929) fait `GetComponent<NumberOfMembersComponent>` puis
  **`FillUpStatComponent.GetStatPart @180f9b3a0`** direct. Layout fill-up du NumberOfMembersComponent :
  `+0x10` = nrOfMembers (base), `+0x18` = membres **restants** (champ MAINTENU par le jeu).
  `GetStatComponent @180ed20c0` n'a **pas** de case 0x14 (stat 20 ≠ StatComponent).
- **Parts de `GetStatPart @180f9b3a0`** (re-décompilé) : 0→current(+0x18), 1→pct,
  2→`get_CurrentMaximumValue @180f9c010` (= base + mod clampé), **3→champ base +0x10**,
  4→max−current, 5/9→modTotal (+source→`GetModificationFromEntity`), 7→override.
  ⚠ Le port avait transcrit **3→modTotal** (faux) — corrigé (`entities/stats.py`), et c'est
  précisément le part 3 que lit l'arbre Swarm (= nrOfMembers).

Faces heal-limit (pures, `DamageCalculations` déjà portées #57d) :

- `DamagePrediction.GetGroupUnitHealLimit @1810325e0` : héros → int.MaxValue ; sinon
  `maxHealthWith(restants) − hp` (« soin sans réveiller de membre »).
- `AttackQuery.IsAtGroupUnitHealLimit @181057b30` : `maxHealthWith(restants) <= hp`.
- Consommateurs et leurs GATES :
  - `PredictHeal @181037180` : `if (param_6 == 1) amount = min(amount, healLimit)` ;
  - `PredictRepair @181038280` : idem `param_7 == 1` (avant cap boss et `MaxFillUp` ×2) ;
  - `EntityCanBeHealed @181054fa0` / `EntityCanBeRepaired @181055080/@181055170` :
    sous flag (param 4/3), cible « at limit » NON éligible.

## 2. Findings ground-truth (probe live)

1. **Formule confirmée** : à chaque état observé (k = 0 et 3 morts, + résurrections LivingMetal),
   `statDelta.extraHits natif == −min(n_base−1, morts)` — 9/9 (runners 23-25).
2. **Dérivation hp→membres == champ natif** : `group_unit_stat_part(4, hpMax, n, hp)` (calculé du
   hp) == `−statDelta.numberOfMembers` (le champ +0x18 maintenu) sur tous les états — la dérivation
   offline est exacte, les mainteneurs natifs étant exactement les événements PV du CreateTrigger.
3. **EXTRA_HITS est NÉGATIF live** : scarab 3 morts → `GetStat(17, Current) = −3`. Le port clampait
   TOUTES les stats à min 0 au seed → Current offline valait 0 (bug latent depuis le seed initial,
   masqué par le feed #57a). Le `Max(0)` natif vit à la FIN de `GetDefaultAttackHits @181032520`,
   pas dans le clamp du stat. Fix : `STAT_CLAMP_MIN = {17: None}` (stats.py).
4. **Le stat capté `numberOfMembers` = GetStat(20, Current) = RESTANTS** (5→2 sur un scarab blessé),
   pas la base ; base = Current − statDelta. `UnitContext.number_of_members` = base désormais.
5. **Flags du cap groupe = 0 sur les chemins IA** (mesure directe, runner 25) : scarab
   hp=888/2218 = PILE la frontière de 2 membres (`at_limit=True`, `group_limit=0`) →
   `aiPlaybookPredict.repairs.hpFill = 1330` (= missing ENTIER, **non capé**) et
   `pairUtility = 59.9369 = 1330/2219×100` EXACT — pour Repair 28 (spyder, granted trait Mechanic)
   ET Repair_GalvanicField 1119 (manipulus). Éligibilité (abilityTargets) : cible at-limit LÉGALE →
   gate de `EntityCanBeRepaired` aussi à 0. Cohérent i2 : « Healing this unit can revive dead
   members ». ⇒ `_HEAL_GROUP_CAP = _REPAIR_GROUP_CAP = False` (action_generators) ; helpers +
   plomberie `group_limit` en place pour un futur chemin à flag 1.

## 3. Port (#60)

- `services/trait_damage_limits.py` : `get_group_unit_heal_limit`, `is_at_group_unit_heal_limit`,
  `group_unit_stat_part` (résolution stat 20 offline, parts 0/1/2/3/4).
- `entities/stats.py` : fix `FillUpStatComponent.get_stat_part` (3→base max, 5/9→modTotal) +
  `STAT_CLAMP_MIN` (ExtraHits sans plancher).
- `entities/effects/loki/hits.py` : `Swarm_HitReductionEffect` (1021) + clé partagée
  `SWARM_HIT_REDUCTION_SOURCE` ; factory `"Swarm_HitReduction"`.
- `entities/unit_context.py` : attribution d'hydratation — la part `−min(n−1, morts)` du delta
  EXTRA_HITS est attribuée sous la clé partagée (résidu CAPTURED_SOURCE = 0, validé 9/9) ;
  `number_of_members` = base.
- `runner/abilities/loki/swarm.py` : arbre VALEUR en vrais nœuds DSL
  (`StatAmount/Difference/Min/Negative/Const`) + `refresh_swarm_hit_reduction` = AddOrUpdate
  (revert+change_stat sous la clé partagée ; `Modify(*,0)` natif est no-op → retour à 0 par revert).
- Choke-points PV (chacun annoté de son bras natif) : `operations/damage.py` ×4
  (On(UnitMemberDeath=48)), `operations/heal.py` (On(UnitHealed=44) + UnitRepaired=49),
  `operations/resurrect.py` (On(UnitRevived=46)) ; init = l'attribution d'hydratation
  (OnOwnerSpecificAbilityInit(1023)).
- `runner/abilities/behaviours.py` : branche stat 20 dans le `_get_stat` du DslContext (mirror du
  handler jumptable — NumberOfMembersComponent, PAS UnitStats).
- `ai/action_generators.py` : `_group_heal_limit` + wiring `group_limit` aux 3 call-sites
  heal/repair, **gaté OFF** par les flags mesurés.

## 4. Validation

- `probe_60_swarm.py` (60003/60004) : ground truth 9/9 · attribution 9/9 (résidu 0, Current == natif
  y compris −3) · rows normal-attack 9/9 EXACTES (k=3 → hits 5→2 : oracle (1596,2396) = 2×(798,1198)
  vs k=0 (3990,5990) = 5×) · heal natif (LivingMetal full-revive) suivi (delta 0 après régen).
- Volet runner-face (état hydraté live + ops OFFLINE) : dégât direct 2.2 membres → xh **−2** ;
  heal 1 membre → **−1** ; full heal → **0** avec source revertée (scratch check, runner 60005).
- Régression stages 12345/2468 : voir commit.

## 5. Restes / flags

- **DirectDamage member-cap — RÉSOLU (#30/#60bis, 2026-07-22, `probe_60bis_directcap.py`)** :
  le natif CAPE le dégât direct à la frontière de membre. RE : `DirectDamageOperation.Execute
  @180e677f0` (nœud DSL `DirectDamage @180dee0a0`) route par `IDamagePrediction.CalculateDirectDamage`
  (slot 7, `@18102f130`) → `ApplyGroupUnitDamageLimit @18102bfe0` avec **profile=NULL** (pas de
  bypass Blast possible), skip si flag payload ; la route ATTAQUE-pipeline du DoT feu passe par
  `ApplyTraitDamageLimitsToDirectDamage @18102c9b0` (= même wrapper, dispatch virtuel — les bytes
  de mode du hit-struct dans `CalculateDamageOperation @18102dc30` sélectionnent la variante).
  **Prouvé live** (seeds 60112/60113, scénario ennemi-verrouillé + tour ennemi sauté) : scarab
  PLEIN (2218, 5 membres, LivingMetal inerte à PV pleins → diff pur) posé sur tuile en feu →
  tick natif = **443** = `hp − maxHealthWith(4)` (vs 444 non-capé ; modèle du tick vérifié exact
  par ailleurs : 444 nu à rem=1, 111 sous aura Protector +886). Port : `execute_direct` applique
  `apply_group_unit_damage_limit(dmg_net, False, n, hpMax, hp)` post perçage/armure.
  Apprentissages scénario (durement acquis, runs 60101-60113) : per-hit de TOUT attaquant lineup
  ≥ PV membre (444) → la défense #57d fait TOUJOURS atterrir la victime sur une frontière (rem=1
  au tick) ; tick 20 % PVmax == PV d'un membre (n=5) → seul un scarab PLEIN donne un état
  discriminant (gap 443 < 444) ; le hive ne spawn PAS sur tour ennemi inerte ; la capture des
  événements de frontière exige un tour ennemi AVEC activations ; `--hp-target` ne protège pas
  du feu (20 % du max/tick) ; LivingMetal peut réviver massivement (444→1775) → canal diff
  inutilisable sur unité endommagée.
- **Étage limites du COMBAT (attaque/ability) — RÉSOLU (#67, 2026-07-22)** : l'étage entier
  (member-cap + Resilient + bypass Blast + porte overkill) est câblé dans `_run_hits` et validé
  live 4/4 scénarios — détail, découvertes (cap des BORNES avant tirage, ancrage hp_départ de la
  porte, flag group-cap ≠ overkill) et résidus : `docs/rl/case-67-combat-trait-limits.md`.
- Le flag=1 des caps heal/repair n'a AUCUN chemin natif identifié à ce jour ; si un apparaît
  (ability « ne peut pas réveiller »), rebrancher les booleans par chemin.
- `necroSmnSwarm.ScarabSummon` (split) agit à l'apparition — bruit de scénario, sans impact port.
