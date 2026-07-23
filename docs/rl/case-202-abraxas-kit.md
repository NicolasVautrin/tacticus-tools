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

## 7. Découvertes / résidus (autres tranches)

(à remplir au fil des tranches B/C)
