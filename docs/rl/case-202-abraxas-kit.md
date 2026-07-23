# Case #202 — Kit d'Abraxas (`thousInfernalMaster`) : port complet

> **Statut : EN COURS (recon fait, tranches à porter).** Chantier demandé le 2026-07-23 :
> porter le kit complet d'Abraxas (DECISION + COMBAT + PRÉDICTION).

## 1. Recon (gameconfig + i2 + unit_map)

**Unité** : `thousInfernalMaster` (Abraxas), Thousand Sons / Chaos, Rare, lineup (spawnable
runner). Move 3. Melee `Flame` 2 hits pierce 25 (profil `OnFire`) ; ranged `Psychic` portée 2,
1 hit, pierce 100 (`NoBlocking`). Traits : `Hero`, `WeaverOfFate`, `Psyker`.

**Abilities** :
- **`MasterOfTheTutelaries`** (active 1096 ; constants `unitId=thousSmnPinkHorror`,
  `unitId_2=thousSmnScreamer`) — i2 : « Summon a Pink Horror on a free hex adjacent to
  Abraxas. Until the end of this turn, whenever an enemy unit is dealt Psychic Damage,
  summon a Screamer of Tzeentch on a free hex adjacent to Abraxas, preferring hexes
  adjacent to enemy units. Newly summoned units can immediately attack an enemy in range
  but cannot move. »
- **`InfernalPacts`** (triggered/passif 1170 ; constants `affectedDamageProfile=Psychic`,
  `nrOfHits=1`, dmg 10-20 L1 → 728-1455 L65) — i2 : « Friendly Chaos units adjacent to
  Abraxas deal an additional 1x N Psychic Damage with their normal ranged attacks.
  Affected Daemons also gain the bonus hit on their normal melee attack. » → AURA
  d'adjacence.
- **Trait `WeaverOfFate`** (trait 1041, triggered ability 1161) — i2 : « In any turn where
  3 or more enemy units have taken Psychic Damage, this unit will deal the maximum
  possible Damage with its attacks and abilities on that turn. »

**Enums (déjà présents côté moteur)** : Active 1096 ; Triggered 1161 (WeaverOfFate),
1170 (InfernalPacts), 1173 (MasterOfTheTutelaries_Summon) ; Effects 1185
(WeaverOfFate_MaxOutDamage), 1197 (MasterOfTheTutelaries), 1198
(InfernalPacts_AdditionalHits) ; UnitTrait 1041 ; UtilityType 62.

## 2. Carte des artefacts natifs (énumération ghidra 2026-07-23, build gqfc5mff6c)

### WeaverOfFate (1161 → effet 1185)
- `WeaverOfFateAbility.CreateTrigger @1811acc50`, `GetTrigger @1811acd60`,
  `CreateBehaviour @1811acb90` (Triggered.Loki).
- Consommation du max-out : `UnitExtensions.IsAttackMaxOutDamage @180ed7a50`, appelé par
  `AttackDamageOperation.ExecuteHit @180e5fb1b`, `AbilityDamageBehaviour.GetDamage
  @180f8c638`, `AttackDamageBehaviour.GetDamage @180fbb32b`, et côté prédiction
  `DamagePrediction.IsAttackMaxOutDamage @1810329f0` ← `PredictAttackRaw @181034aba`.

### InfernalPacts (1170 → effet aura 1198)
- `InfernalPacts_AdditionalHitsEffect` : `.ctor @180f527a0` (enregistré par
  `EffectsDatabase.<InitializeEffects>b__14_225` — effet auto-porteur, pas de classe
  `InfernalPactsAbility` dédiée), `CreateAdditionalHits @180f52430`,
  `CreateTargetSelector @180f52650`, `GetRefreshTriggers @180f52730`.

### MasterOfTheTutelaries (1096 + triggered 1173 → effet 1197)
- Active : `MasterOfTheTutelariesAbility.ctor @1811f3310`, `ExecuteBehaviour @1811f30c0`.
- Effet until-EoT : `MasterOfTheTutelariesEffect` `.ctor @180f59300`,
  `ApplyInternal @180f59090`, `RevertInternal @180f591f0`.
- Summon triggered (Screamer sur dégât Psychic) : `MasterOfTheTutelaries_SummonAbility`
  `CreateTrigger @18110be00`, `CreateBehaviour @18110bb30`,
  `CreateSummonBehaviour @18110bba0`, `GetPossibleSummonTiles @18110bf30`,
  `GetPreferredSummonTiles @18110bf70`.
- Décision : `MasterOfTheTutelariesPlaybook` `.ctor @18114ba20`, `.cctor @18114b9b0`,
  `EvaluateNonComparable @18114b300` (+ lambda DisplayClass6_0 `@181163730`).

## 3. Déjà porté (ne pas refaire)

- `MasterOfTheTutelaries_MoveTowardsTargetUtility @1810f0130` (UtilityType 62) —
  `engine/utilities/tile.py` (#158).
- Trait `Psyker` (splash #45-s18), profil `OnFire` (DoT feu, triggers/loki/fire.py),
  poids `unit_order("WeaverOfFate")` (weights.py).
- Machinerie summon runner-face existante : `execute_control_edict_summon` (spawn.py,
  #38) — patron à réutiliser/généraliser, summons = équipe du summoner, agissent au spawn.

## 4. Plan de tranches

| Tranche | Contenu | Faces |
|---|---|---|
| A | **WeaverOfFate** : trigger (≥3 ennemis Psychic-damaged ce tour) → effet 1185 ; mirror `IsAttackMaxOutDamage` dans le roll de dégât ET dans la prédiction (`PredictAttackRaw` le lit nativement) | COMBAT + PRÉDICTION |
| B | **InfernalPacts** : aura 1198 (sélecteur adjacents-alliés-Chaos, refresh triggers) ; +1 hit Psychic ranged, Daemons aussi melee ; face prédiction (l'attaque d'un allié bufé gagne le hit) | COMBAT + PRÉDICTION |
| C | **MasterOfTheTutelaries** : execute (summon Pink Horror + pose effet 1197) ; trigger 1173 (Screamer sur Psychic damage, tuiles préférées adjacentes-ennemis) ; décision `EvaluateNonComparable @18114b300` | COMBAT + DÉCISION |

Classification DSL/impératif (#149) à faire par tranche au moment du RE (CreateTrigger/
CreateBehaviour/CreateTargetSelector = arbres DSL ; GetDamage/ApplyModification/
GetPossibleSummonTiles = impératif appelé par les feuilles).

## 5. Validation prévue

Porteur spawnable (lineup) ; Pink Horror/Screamer = summons listés (spawn via ability).
- A : duel crafté Abraxas + sources Psychic vs ≥3 ennemis — comparer roll min/max avant/
  après le seuil, agreement sur le tour ; vérifier la prédiction (decisionView) reflète le max.
- B : allié Chaos ranged adjacent (± Daemon melee) — nrOfHits observé ±1, statDelta
  vs `statModSources` (doctrine aura = delta inexpliqué).
- C : walk avec Abraxas — cast 1096, spawn Horror, puis dégât Psychic ennemi → Screamer ;
  agreement décision (le natif cast-il quand nous castons ?).

## 6. Tranche A — WeaverOfFate : LIVRÉE

**Port** (COMBAT + PRÉDICTION) :
- `runner/operations/triggers/loki/weaver_of_fate.py` : `WeaverOfFateAbility` (On(9) brut,
  seuil 3 EN DUR `Get(3)`, `!HasEffect(1185)` → AddEffect self durée 1) + sélecteur
  `units_that_taken_damage_this_turn` (ContainsKey — la présence de la clé seule compte) +
  prédicat `is_attack_max_out_damage` (face ECS). Registre : `TRAIT_TRIGGERS["WeaverOfFate"]`.
- Store : `UnitComponent.received_damage_this_turn` (mirror dict ActorStatistics @+0x80,
  écrit par le chokepoint, reset par-joueur-ENTRANT dans `StartTurnOperation` — la portée
  du reset compte : les clés adverses survivent à leur propre tour).
- **Chokepoint `_apply_damage_pipeline`** (damage.py) : le bloc post-dégât (reduce + mort +
  compteurs + `RegisterDamage` + swarm), inliné ×4 avant, n'existe plus qu'une fois — mirror
  du pipeline natif unique `ApplyDamageOperation` → `RegisterDamageOperation @180e86de0`.
  DoT : `is_attack=False` (pas de compteur d'attaques).
- Consommation combat : `_apply_max_out` aux 3 constructions de `HitDamage` — bornes
  dégénérées (max, max) = mirror `HitDamage(GetMax, null)` des deux `GetDamage` jumeaux
  (@180fbb250/@180f8c560). Voie `get_damage` : ZÉRO tirage RNG (gate min==max) ; voie
  slot-8 mode-1 (#67) : le tirage toujours-consommé tire dans [max,max] — consommation
  bit-exacte préservée. Crit : base = max (branche crit d'`ExecuteHit`, couverte par
  la dégénérescence de `hit_cr`). `execute_direct` (DoT) NE maxe PAS (aucun call site natif).
- Prédiction : `is_attack_max_out_damage` évalué DANS `predict_attack_raw` (foyer unique,
  mirror du call site natif @181034aba) → `get_base_damage_fix64(is_max_out)` → min=max ;
  les appelants passent `attacker_effects` (l'entité aplatie à sa seule facette consommée —
  le natif ne passe AUCUNE liste d'effets : entités + state du service `this+0x40`,
  lecture à la demande ; AUCUN équivalent défenseur — rien dans PredictAttackRaw ne lit
  les effets du défenseur, ses mods arrivent pré-construits d'amont @181002c30).

**Validation** :
- Garde 31337 post-refactors : ability 13/13, move 18/18, prédiction 10/10, utilité 10/10.
- Live crafté (`probe_202_weaver.py`, seed 20201 : Abraxas + 2× Njal [Psyker non-Chaos,
  armes 100 % Psychic — l'aura InfernalPacts non portée reste inerte] vs 4 necroWarden,
  HP gonflés, MC1_67) : **3/3 poses natives** de l'effet 1185 aux événements exacts où
  notre compte reconstruit atteint 3 (s09/s24/s31), zéro faux positif (comptes 1-2 → pas de
  pose ; compte 3 + effet déjà posé → gate HasEffect), **On(9) brut confirmé** (les poses
  suivent des attaques de Njal, pas du porteur), expiry au EndTurn de l'équipe du porteur
  (disparu au tour ennemi s11/s25/s32), reset per-entering-player confirmé.
- Sanity offline : clamp (max,max) deux voies, zéro conso RNG voie get_damage, prédiction
  1000±20 % → 1200==1200 (témoin sans effet : 800-1200).

**Résidus tranche A** :
- Branche `HasTriggeredAbility(1494 ParagonSpear)` d'`IsAttackMaxOutDamage @180ed7a50` non
  mirrorée (porteur hors kit, appel inliné mangé par ghidra) — à porter avec le kit ParagonSpear.
- Gate exact d'enregistrement de `RegisterDamage` (dégât 0 / full-block ?) non RE'd (dispatch
  virtuel) — sans effet tant que seul WeaverOfFate lit le dict.
- `received_damage_this_turn` logé sur `UnitComponent` (précédent times_attacked) alors que le
  foyer natif est un `ActorStatisticsComponent` dédié — résidu structurel.
- Le roll=max en RUNNER-SIM (nos ops exécutant un combat maxé) n'est exercé que par le sanity
  offline — un replay-diff live d'un tour maxé le confronterait bit-exact (à faire si un miss
  d'agreement le fait surfacer).

## 7. Tranche B — InfernalPacts : RE (décompilé 2026-07-23)

**Arbre natif complet** (`InfernalPacts_AdditionalHitsEffect`, effet 1198, auto-porteur
enregistré par `EffectsDatabase.b__14_225`) :

- `.ctor @180f527a0` : `BaseEffect(AbilityOrEffect(0x492=1170 InfernalPacts), 1, 0)`.
- `CreateAdditionalHits @180f52430` → `EffectAdditionalHits.Create @180f405b0` avec :
  - trigger = `OwnerIsCaster & (IsRangedAttack | HasTrait(Caster, 0x3fb=1019 Daemon))` ;
  - dégât = `BaseEffect.GetMinMaxDamage(this, 0)` `@180f11cc0` (wrapper `@180f11da0`
    défauts 0xc/0xd) = **`RandomAmount(ConfigVar(0xc=minDmg), ConfigVar(0xd=maxDmg))`**
    sur l'AbilityState de l'EFFET (courbe InfernalPacts 10-20 L1 → 728-1455 L65) — plage
    DIRECTE, pas de re-spread ±20 % ; la variante `(this, 1)` = **`Average(min,max)`**
    (canal prédiction/display, champ [2] du descripteur) ;
  - nrOfHits = `GetNumberConstant(0x2f)` = 1 ; profil = `GetAffectedDamageProfile` = Psychic.
- `CreateTargetSelector @180f52650` :
  `Unique( UnitsWithRangedWeapons(UnitsWithTrait(AdjacentFriends(Caster,1), 0x7ea=2026 Chaos))
  + UnitsWithTrait(AdjacentFriends(Caster,1)∩Chaos, 0x3fb=1019 Daemon) )` — bénéficiaires =
  amis Chaos adjacents ring-1 avec arme ranged, OU Daemons Chaos adjacents (sans condition
  d'arme — leur volet melee vient du disjunct Daemon du trigger).
- `GetRefreshTriggers @180f52730` : `[PreAttack(5), PreAttackDamageHit(7)]` — l'aura est
  réévaluée AU MOMENT de l'attaque → le modèle offline « adjacence à la tuile candidate,
  rien n'est posé sur le bénéficiaire » (#49/#153, mold ExplosiveMaladies) est fidèle.

**Exécution COMBAT native** : les coups additionnels à profil PROPRE passent par
`ExecuteAdditionalHitsWithDamageProfileTypeOperation.Execute @180e70600` (via
`OperationProcessor.ExecuteAdditionalHitsWithDamageProfileType @180e07fb0`, dispatch virtuel)
→ `AdditionalHitsFromEffects.GetAdditionalHitsFromEffects @180e59e50` /
`GetAdditionalHitsFromEffectsInternal @180e59150` (énumération GLOBALE des effets, éval du
trigger dans le contexte d'attaque via AbilityEntities) + `GetAdditionalHitsData @180e589b0`,
puis chaque descripteur qualifié exécute son coup comme sous-opération de dégât (résultats
`OperationResult.Combine`). Le jumeau même-profil (`ExecuteAdditionalHitsWithoutDamageProfileType
@180e5e7c0`) est le coup bonus BASE déjà documenté (damage.py). **GAP CONSTATÉ : le canal #179
n'a AUCUNE face runner-combat offline aujourd'hui** (SquigHound/ExplosiveMaladies = prédiction
seule) — la tranche B doit câbler ce consommateur combat.

**Port livré (tranche B)** :
1. `entities/effects/loki/hits.py` : `InfernalPactsAdditionalHitsEffect` —
   `create_aura_additional_hits_for_ally` (mold ExplosiveMaladies) : gates allié même team,
   ring-1, **Chaos** (GrandAllianceId — les traits gameconfig ne portent pas Chaos), et
   (attaque ranged) OU (attaquant **Daemon**, melee inclus). Groupe **BI-CANAL** :
   `{count, amount, min, max, profile}` — `amount` = Average EXACT (.5 gardé, précédent
   FleshmetalGuns) consommé par la PRÉDICTION ; `min`/`max` = plage RandomAmount consommée
   par le COMBAT.
2. `factory.py` : `EFFECT_CLASSES["InfernalPacts_AdditionalHits"]` +
   `ABILITY_INIT_OWNER_EFFECTS["InfernalPacts"]` (filet ; le nom capté live confirme la clé).
3. PRÉDICTION : ctx aura +`att_traits` (gate Daemon) aux 2 call-sites de prediction.py.
4. COMBAT (**nouveau canal — le #179 n'avait AUCUNE face runner-combat**) :
   `AttackDamageOperation._collect_additional_hit_groups` (mirror énumération globale
   @180e59150, positions ECS réelles) + `_execute_additional_hits` (mirror @180e70600) dans
   `execute` : sous-opérations APRÈS les coups d'arme, bornes = plage [min,max] réduite
   (perce du profil DU GROUPE + armure + MÊMES mods attaquant/défenseur que l'arme), tirage
   mode-1 toujours-consommé, PAS de crit-roll (1er jet), pipeline par groupe avec SON profil
   (`is_attack=False`) ⇒ le Psychic bonus alimente `received_damage_this_turn`/WeaverOfFate.
   Max-out #202-A : bornes dégénérées (max,max), symétrique de la prédiction.

**Découverte de RE — dégât BI-CANAL du descripteur (mesuré live, probe_202b)** : le
descripteur `EffectAdditionalHits` porte DEUX nœuds — field[1] = `RandomAmount(min,max)`
(résolution COMBAT) et field[2] = `Average(min,max)` (param_8 de Create, canal
PRÉDICTION/display). Preuves : (a) prédiction native du bonus = paire ±20 % sum-preserving
((3248,4871) ≈ centre 4059.5) ≠ plage brute — la courbe InfernalPacts (max=2×min)
DISCRIMINE là où SquigHound (max=1.5×min) rendait les deux modèles identiques ; (b) 10
tirages combat no-crit [1122…1872] ⊂ [997,1996] (RandomAmount) et VIOLENT le support
avg±20 % (1197-1796) aux deux bouts. ⚠ Les groupes house `{min,max}` historiques
(SquigHound…) restent fidèles en prédiction PARCE QUE leur ratio 1.5 fait coïncider les
modèles — ne pas « corriger » sans courbe discriminante.

**Validation live (probe_202b_infernal.py, seed 20203, Abraxas + Toth thousTerminator +
Azkor worldEightbound vs 3 necroWarden, MC1_67)** :
- Capture : effet `InfernalPacts_AdditionalHits` (1198) présent sur Abraxas (clé factory OK).
- PRÉDICTION per-tuile (canal ranked natif) : **10/10 MATCH exact** — Toth ranged ADJ
  (weapon+bonus, tuiles plates ET élevées, rows optimistes incluses), Azkor Daemon melee ADJ
  (7584-11373 == off, élévation ×1.5), contrôles non-adjacents, et gate melee-non-Daemon
  (Toth melee ADJ : AUCUN bonus des deux côtés).
- COMBAT : comptes 6=5+1 (Toth ADJ), 5 (contrôle non-adj), 3=2+1 (Azkor Daemon melee ADJ) ;
  distribution des tirages bonus ⊂ RandomAmount (cf. ci-dessus).
- Garde 31337 : 100 % sur les 4 étages (relancée après chaque évolution du modèle).
- Piège de porteur documenté : emperNoiseMarine ÉCARTÉ (son passif `TerrifyingCrescendo`
  1424, NON porté, stacke un additif à chaque round → pollue toute confrontation
  post-combat). Toth = porteur Chaos ranged le plus propre (WeaverOfFate contrôlé en
  restant <3 ennemis Psychic-touchés/tour).

**Résidus tranche B** :
- Crit-roll des coups bonus en combat NON discriminé (Toth cc=0 → aucun tirage crit dans le
  sample ; le port ne crit-rolle pas les coups bonus — un replay-diff avec porteur cc>0
  trancherait). Position RNG exacte du tirage bonus dans le flux = idem.
- `failed_block` remis à zéro entre phase d'arme et sous-opérations bonus (le natif persiste
  la failedList PAR ATTAQUE) — sans effet tant que les cibles de test n'ont pas de block multi-échec.
- Gate `hp > 0` (cible morte pendant la phase d'arme → sous-opérations non émises) :
  hypothèse cessation-post-mortem, non exercée live.
- La face combat du canal #179 s'active AUSSI pour les groupes historiques (SquigHound
  {min,max} ; ExplosiveMaladies/FoulInfusion/CyclicIonBlaster/FleshmetalGuns forme `amount`
  → spread ±20 %) — leur modèle de résolution combat propre n'a jamais été mesuré (validé
  prédiction only) ; à confronter si un replay-diff les fait surfacer.
- `TerrifyingCrescendo` (1424, Emperor's Children) : effet stacking NON porté découvert au
  probe — candidat backlog (famille traits/passifs restants).
- Défenseur : les %-gates par profil des mods défenseur du coup bonus héritent du ctx de
  l'ARME (mirror prédiction) — un cas TerminatorArmour-vs-bonus-Psychic discriminerait.

## 8. Tranche C — MasterOfTheTutelaries : LIVRÉE (COMBAT + DÉCISION portées ; décision non confrontée oracle)

### RE (décompilé, VAs §2 ; corrections MESURÉES live diag/probe 202c, runners 181-189)

**Active 1096 `ExecuteBehaviour @1811f30c0`** (cast TILE-target : hex libre adjacent) :
`op_BitwiseAnd( AddEffect(0x4ad=1197, stateRef, caster@0x160, caster@0x160, durée@dsl+0xc0),
Spawn(caster@0x160, Target@0x178=TUILE, unitId="thousSmnPinkHorror",
WithStatsFromConfig(config, AbilityLevelAmount(Self@0x148, 1096)) .onAppearance =
PerformAIAttackFromCurrentPosition) )` — AddEffect AVANT Spawn : l'attaque immédiate du Horror
déclenche déjà la chaîne. Mesures : Horror hp 3589 = `summonHp[50]×180 %`, atk 898 =
`summonDmg[50]×180 %` ; tuile = la tuile CIBLÉE ; le cast pose `TurnFinished` d'Abraxas.

**Effet 1197 `MasterOfTheTutelariesEffect`** (ctor @180f59300 = BaseEffect(1096, 1)) :
`ApplyInternal @180f59090` = `AddTriggeredAbility(Entity(target), 0x495=1173, state)` ;
`RevertInternal @180f591f0` = `RemoveTriggeredAbility(…, 0x495)`. Cascade : posé
`Effect_RemainingTurns=1`, décrément + revert à la FIN DU TOUR D'ÉQUIPE (cascade v1 :
`RemainingTurns 1→0` puis `UnitStats_RemoveTriggeredAbility:1173` juste avant le
`Match_CurrentPlayerId` flip). ⚠ decisionView FILTRE cet effet (jamais visible) — le lire
dans la cascade (action s=16 `Effect_SourceActiveAbility:1096`).

**Triggered 1173 `MasterOfTheTutelaries_SummonAbility`** :
- `CreateTrigger @18110be00` = `On(9,1) & HasEffect(owner,1197) & AreEnemies(owner, target)
  & !IsObjectOrSteppable(target) & CurrentAttackDamageProfilesContain(0xd=13 Psychic)`.
  **Lois mesurées** : (a) UN fire max par ATTAQUE (pas par coup) ; (b) le SET de profils
  inclut les BONUS-HITS #179 — une attaque melee Physical/Power portant le bonus
  InfernalPacts Psychic QUALIFIE → chaîne Horror→Screamer→Screamer… bornée par les POSITIONS
  (summon sans cible à portée n'attaque pas) et non par le profil d'arme ; (c) aucun gate
  « dégât > 0 » dans l'arbre (une attaque Psychic bloquée qualifierait — non exercé).
- `CreateBehaviour @18110bb30` (gshared, précédent ActOfFaith #151) : branche `!=0x20` =
  `TriggerAbilityDelayed(owner, 0x495, kind=3)` (fire initial → différé), branche `==0x20` =
  `CreateSummonBehaviour @18110bba0` (réveil différé → spawn). Les DEUX branches vivantes
  (self-delayed). Ordre observé : enregistrement PENDANT l'attaque (groupe 21 vide), spawn
  APRÈS la résolution de l'attaque.
- `CreateSummonBehaviour @18110bba0` : `RemoveEffect(EntitiesWithAnyEffect(@0x80, 0x425=1061
  GeminaeSuperia_JustSummonedEffect)) & Spawn(owner@0x148, PickRandomly(
  TilesUnitCanAttackFrom(CanAddUnit(AdjacentTiles(owner)), owner, unitId_2)
  .Otherwise(possible), 1), "thousSmnScreamer", WithStatsFromConfig2 + onAppearance
  PerformAIAttackFromCurrentPosition)`. **Screamer stats = variables SUFFIXÉES `_2`**
  (`summonHp_2`/`summonDmg_2` — mesuré : 4487 = 2493×180 %), niveau/mult = ceux de l'active
  1096 du caster (propagés par l'ability-state de 1197). `GetPossibleSummonTiles @18110bf30`
  / `GetPreferredSummonTiles @18110bf70` = les mêmes sélecteurs exposés (face décision).

**Découvertes transverses (cascade spawn)** :
- **`Daemon` → ability dérivée → `Daemon_ExtraBlock`** posé au spawn de CHAQUE Daemon
  (+25 block chance, +449 = 50 % Attack block damage) — chemin `TRAIT_DERIVED_ABILITIES`
  ajouté offline (classe `DaemonExtraBlockEffect` déjà portée).
- Le summon reçoit l'aura InfernalPacts (1198) DÈS le spawn (refresh immédiat) + triggered
  1156/1161/1036/1013 (kit du Horror) — son attaque porte donc le bonus Psychic si adjacent.
- **Ranged désactivé AU CONTACT** (règle légalité, diag v5 : sorcier adjacent à un ennemi →
  `actionConsumed=False` sur son tir) — légalité d'action en amont, pas un étage du pipeline
  dégât (le driver/fromHere l'exclut nativement).

**Décision `MasterOfTheTutelariesPlaybook.EvaluateNonComparable @18114b300`** (cctor MIN=1 ;
slots IBattleQuery résolus via le dump vtable #38b : 0x49=`GetNearestEnemy @181066440`,
0x52=`GetFreeAdjacentTiles(target) @181061570`, 0x6b=`GetDistance @181061040`,
0x72=`GetUnitsAtDistance @18106c9a0` ring EXACT) : par tuile de spawn candidate ST —
gates `freeAdj(ST) > 2` && `#ennemis à dist==2 de la tuile RÉELLE > 0` ; utilité
`1 + (nE2-1)×10 + (nFree-3)×10 + 100 si dist(nearestEnemyTile, ST) == 2`.
`GetNearestEnemy` : plus-proche strict avec PRIORITÉ aux ennemis en mêlée (AreUnitsInMelee
supplante la distance) ; tie = 1er énuméré.

### Port

- `effects/loki/status.py` : `MasterOfTheTutelariesEffect` (marqueur 1197) + factory.
- `abilities/loki/summon.py` : `MasterOfTheTutelariesAbility` (1096, arbre
  `Seq(AddEffect, SpawnTutelaryHorror)`) + `perform_ai_attack_from_current_position`
  (on-appearance pipeline attaque normale COMPLET, cible = `_nearest_enemy` gaté portée) ;
  handler 1096.
- `spawn.py` : `execute_master_of_tutelaries_screamer` (possible/preferred/PickRandomly,
  `key_suffix="_2"`, RemoveEffect(1061) no-op mirroré).
- `triggers/loki/master_of_the_tutelaries.py` : `MasterOfTheTutelariesSummonAbility`
  (`EffectTrigger`, `EFFECT_TRIGGERS[1197]` = mirror du Add/RemoveTriggeredAbility) ; gate
  profils via `TriggerEvent.profiles` (NOUVEAU : set arme+bonus threadé par les vecteurs
  after-attack — damage.py / summon_ai.py / on-appearance).
- `factory.py` : `TRAIT_DERIVED_ABILITIES["Daemon"]` + `ABILITY_INIT_OWNER_EFFECTS["Daemon"]`.
- `playbook/noncomparable/master_of_the_tutelaries.py` : playbook NC 1096 (registre).

### Validation (probe_202c_tutelaries.py, seed 20203 — PASS)

A1 effet 1197 posé (RemainingTurns=1, cascade) ; A2 Horror tuile ciblée + hp EXACT offline ;
A3 Screamer hp EXACT (`summonHp_2`) + tuile adjacente ; A4 #Screamers == #attaques
qualifiantes ; B tir Psychic ALLIÉ même tour → chaîne loi-conforme (2 spawns == 2 attaques
Psychic de la cascade B) → 1197 armé jusqu'à FIN DE TOUR D'ÉQUIPE ; C tour suivant → +0
(expiry). Garde 31337 : cf. journal de commit.

### Résidus tranche C

- **Face DÉCISION non confrontée à l'oracle** : le playbook NC est porté (slots résolus) mais
  aucun A/B `ncEvaluate` ni walk avec Abraxas n'a encore confronté gates/utilité/tie —
  à faire au premier walk Thousand Sons (le seed 31337 n'a pas Abraxas → inerte).
- Tuile du Screamer : `PickRandomly(1)` sur le set preferred — coût RNG exact / ordre du set
  natif non mesurés (les scénarios probe avaient 1-2 candidats) ; mirror `_pick_randomly`.
- Cible de l'on-appearance : approx `_nearest_enemy` (précédent ScarabSummon) — le choix AI
  natif complet (utilité) non mirroré ; scénarios multi-cibles à portée divergeraient.
- `RemoveEffect(1061)` : poseur de `GeminaeSuperia_JustSummonedEffect` hors périmètre (aucun
  AddEffect(1061) dans ce kit) — no-op offline documenté.
- Attaque Psychic entièrement BLOQUÉE (0 dégât) → qualifie selon l'arbre (pas de gate
  dégât>0) — non exercé live.
- `On(9,1)` : le 2e arg (1) commun à WoF/ActOfFaith/1173 — sémantique du flag non tranchée
  (sans effet observable ici).
- Durée @dsl+0xc0 : nœud singleton non résolu au décompilé — comportement MESURÉ (1 tour
  d'équipe) mirroré via `duration_rounds=1` ; l'identité exacte du nœud reste ouverte.
