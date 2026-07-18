# Chantier gen-stealer (Genestealer Cults) — Isaak & Judh

> Doc **vivant** du portage des mécaniques Genestealer Cults dans le moteur Python (`engine/`).
> Style #149 (RE décompilé = vérité, live = confirmation, mirror des fonctions natives nommées).
> Build ghidra de référence : **gqfc5mff6c** (`mcp__ghidra__*` sur 127.0.0.1:13337, en sync live).
> Recon (gameconfig + i2) faite le 2026-07-18. Les VA natives sont remplies au fur et à mesure des RE.

## 1. Recon du kit (gameconfig + i2, VÉRIFIÉ)

### Unités

| Unité (id) | Nom | Rareté / move | Armes | Traits | Abilities |
|---|---|---|---|---|---|
| `genesPrimus` | **Isaak** | Rare / 3 | 3× Bio melee (P30), 1× Bio r2 (P30) | Hero(16), **Ambush**(1052) | actif **CultDemagogue**(1179), passif **DecoysAndMisdirection** |
| `genesKelermorph` | **Judh** ("Jude") | Epic / 3 | 3× Projectile melee (P15), 3× Projectile r2 (P15) | Hero(16), **Ambush**(1052), **BeastSlayer**(1061) | actif **HeroicFusillade**(1180), passif **HypersensoryAbilities** |
| `genesDecoy` | **Decoy** (token) | npc / None | — | **Steppable**(27), **Decoy**(1053) | — (détruit si marché dessus / endommagé ; non ciblable) |
| `genesNpc3Neophyte` | **Neophyte Hybrid** | npc / 3 | 1× Physical melee (P1), 2× Projectile r2 (P15) | **Ambush**(1052), BattleFatigue | — |

Le token de decoy spawné par les abilities porte le visualId **`genesSmnDecoy`** (== `genesDecoy`).
Neophyte spawné = **`genesSmnNeophyte`** (stats fixes ability : **2183 HP / 1746 dmg / 437 armour**).

### Traits (variables gameconfig)

- **Ambush** = `{"ambushUnitToSpawn":"genesSmnDecoy"}`
  « La première fois que cette unité est vaincue, elle laisse un decoy ; au début de son tour suivant,
  s'il reste un decoy allié sur le terrain, elle est **ressuscitée à pleine vie sur un decoy allié
  aléatoire** et peut **jouer un tour immédiatement**. Les Characters ressuscitent avant les
  Non-Characters. »
- **BeastSlayer** = `{"beastSlayerExtraDmgPct":20,"beastSlayerBlockChance":10,"beastSlayerBlockAsMaxArmorPct":100}`
  « +20 % dégâts en **mêlée** vs **Big Targets** et **Vehicles** ; +10 % de chance de **Block** de 100 %
  de son Armure (⚠ var dit `MaxArmor`, texte i2 dit "current Armour" — à trancher au RE) en Damage. »
- **Steppable**(27) + **Decoy**(1053) : le token. Steppable déjà utilisé côté port comme gate d'immunité feu
  (`UnitsWithoutTraits([Steppable, Immune])` @18121e040) et exclu du ciblage ArcaneShield.

### Abilities (variables gameconfig + texte i2)

| Ability (id) | Owner | Profil | vars | Effet (i2) |
|---|---|---|---|---|
| **CultDemagogue** (1179) | Isaak | — (summon) | `unitId=genesSmnDecoy, unitId_2=genesSmnNeophyte, range=2, range_2=2` | Cible ennemi ≤2 → pose **≤8 decoys** sur hexes libres aléatoires ≤2 autour de la cible → summon **Neophytes sur la MOITIÉ** des decoys alliés de la zone → tous les Neophytes de la zone **jouent un tour immédiat**. |
| **DecoysAndMisdirection** (passif) | Isaak | Blast P15 `HitsMultipleMembers` | `range=2, unitToSpawn=genesSmnDecoy, nrOfHits=1`, dmg **1455-1746** @65 | Ennemi **move-onto** decoy allié → **1× Blast**. Allié **résurrecte/move-onto** decoy allié → **+582 dmg** jusqu'à fin de tour + (si GS Cult) **pose un nouveau decoy** dans un hex adjacent libre. |
| **HeroicFusillade** (1180) | Judh | Projectile P15 | `range=2, nrOfHits=6`, dmg **1455-1746** @65 | Cible ennemi ayant un hex libre voisin dans **move range 2** (ou déjà adjacent) → **Judh move** sur l'hex libre → **6× Projectile** à la cible ET **tous les ennemis l'entourant** (splash) → crits **+218 crit dmg PAR hex libre** entourant la cible. **Résurrection ré-arme** l'ability. |
| **HypersensoryAbilities** (passif) | Judh | Projectile P15 | `range=2, nrOfHits=3, unitToSpawn=genesSmnDecoy`, dmg **1455-2183** @65 | **1er hit chaque tour ennemi** → Judh **ne peut tomber sous 50 % de sa PV courante** (damage floor). Après l'attaque → **move** sur hex adjacent libre + **pose decoy** sur l'hex quitté → si **≤2 hex de l'attaquant** → **3× Projectile** à l'attaquant (contre-attaque). |

## 2. Le substrat DECOY (cœur du kit — tout en dépend)

```
                 ┌──────────────────────────────────────────────┐
                 │  DECOY (genesSmnDecoy) : token Steppable+Decoy │
                 │  posé sur une tuile, non ciblable              │
                 └──────────────────────────────────────────────┘
   PLACEMENT (spawn)                 │              CONSOMMATION (step-on)
   ├─ CultDemagogue : ≤8 autour cible│              ├─ ennemi move-onto → decoy détruit (Steppable)
   ├─ Hypersensory  : hex quitté     │                +  DecoysAndMisdirection → Blast
   ├─ Ambush        : à la mort      │              ├─ allié move-onto/résurrect → +582 dmg + nouveau decoy
   └─ DecoysAndMisd : hex adjacent   │              └─ RESURRECTION (Ambush) : sur un decoy allié
```

Deux primitives partagées à porter EN PREMIER (slice G1) :
1. **Placement d'un decoy** sur une tuile (feuille `Spawn`/`AddUnit` — `spawn.py`/`AddUnitOperation` porte
   déjà ScarabHive ; à confirmer si réutilisable tel quel pour un token sans stats).
2. **Steppable "crushed when stepped on"** : mécanique native qui détruit un token Steppable quand une unité
   move sur sa tuile (point d'insertion dans `movement.py` : `MoveUnitOperation.execute` /
   `MovementHandler.visit_MoveUnitMessage` / after-move).

## 3. Roadmap des slices (tâches #8–#14)

| Slice | Tâche | Contenu | Dépend de |
|---|---|---|---|
| **G1** | #8 | **Fondation Decoy** : placement (Spawn) + Steppable step-on crush | — (base) |
| **G2** | #9 | **DecoysAndMisdirection** — ✅ **PORTÉ + LIVE-VALIDÉ** (2 triggers step-on : ennemi Blast / allié buff+decoy) | G1 |
| **G3** | #10 | **Ambush** (mort→decoy, résurrection sur decoy + tour immédiat, ordre Character-first) | G1 |
| **G4** | #11 | **CultDemagogue** — ✅ **PORTÉ + LIVE-VALIDÉ** (arbre DSL `genestealer.py`) | G1 |
| **G5** | #12 | **HeroicFusillade** — ✅ **PORTÉ + LIVE-VALIDÉ** (move + splash target+voisins + crit ×hex-libres ; ré-arme post-résurrection = tranche G3) | (move+splash) |
| **G6** | #13 | **HypersensoryAbilities** (HP floor 50 % + reactive move + decoy + contre-attaque 3×) | G1 |
| **G7** | #14 | **BeastSlayer** — ✅ **DÉJÀ PORTÉ** (trait générique, live-validé orksNob #72) : reste un guard live Judh | — (couche damage-mod) |

Ordre d'attaque conseillé : **G1 → G2/G3 (decoy consommateurs) → G4 → G6 → G5 → G7**. G7 (BeastSlayer) et
G5 (HeroicFusillade, hors decoy) sont portables en parallèle du reste.

## 4. Substrat Python existant (à réutiliser, NE PAS re-porter)

- **`engine/runner/operations/spawn.py`** = port de `ScarabHiveAbility.ExecuteBehaviour @181204cb0` →
  `DSLFactory.Spawn` → `AddUnitOperation.Execute` (visualId / count / placement / owner=team+player caster /
  stats via `ability_var` / on-appearance). **Base du placement de decoy/Neophyte.**
- **Traits enum** `entities/traits/unit_trait.py` : `Steppable=27`, `Decoy=1053`, `Ambush=1052`,
  `BeastSlayer=1061`, `Hero=16` déjà présents.
- **Summon team model** (memory `project_summon_team_model`) : summons spawnent sur la team+player du
  summoner ; jouent à l'apparition. Neophytes/decoys = même modèle.
- **Résurrection** : machinerie partielle (memory : `RitesOfRestoration` resurrect gate via `obs_units`
  filtré `isDead`) — à croiser pour Ambush (G3).
- **damage_modifiers** (couche prédiction) : point d'accroche probable de BeastSlayer (G7).
- **`after_move_triggers`** (`operations/triggers/dispatch.py`) + `MovementHandler.visit_MoveUnitMessage` :
  chaîne d'events post-move (overwatch On(4)) — la crush-on-step + les step-on-decoy s'y raccrochent.

## 4bis. Substrat de validation live (feasibility, PROUVÉ 2026-07-18)

Runner isolé monté avec Isaak (`--p-units genesPrimus`) — confirmé live :
- **CultDemagogue (id=1179) `usable=True`** sur Isaak (u79) → l'actif est **jouable live** (`applyAction`).
  `abilityTargets` = 0 tant que l'ennemi est hors des 2 hexes → pour la validation-oracle G4, **driver** un
  ennemi à ≤2 hexes d'Isaak (technique standard « drive positions ») puis caster → decoys+Neophytes natifs
  apparaissent → confronter le port.
- **Ambush est ACTIF live** : Isaak porte l'effet `Ambush_CanResurrect` dès le spawn (utile pour G3 — le
  trait Ambush matérialise un effet-état `Ambush_CanResurrect`, à recon au moment de G3).

## 5. RE en attente (verdicts à intégrer)

### G1 — VERDICT re-expert (2026-07-18, ghidra gqfc5mff6c, PROUVÉ)

**P1 — placement d'un decoy.** Même feuille `DSLFactory$$Spawn @180dfbc60` → `SpawnUnitBehaviour.ctor`
→ `SpawnUnitBehaviour.Execute` → **`AddUnitOperation.Execute`** que ScarabHive (socle `spawn.py` réutilisé,
PAS une variante d'Operation). La différence = les **options** : `SpawnUnitOptions$$ForSteppable @180fd60a0`
= `Level(1)` + `CreateSpawnOptions(state,0,0,0,0)` (aucun override) :
- **owner** = team+player du **caster** (hérité du contexte Spawn, comme ScarabHive `CopyOwner`) ;
- **stats** = kit BRUT de la config `genesDecoy` (level 1, **PAS de summon-scaling `ability_var`**) ;
- **traits** = Steppable(27) + Decoy(1053) depuis la config ;
- **`ai_controlled=False`, AUCUNE on-appearance** (pas de `UseNormalAttackIfAble`/`PerformAIAttack`) — le
  token est **inerte** (`move=None`, non-ciblable). ⚠ Différence #1 avec `SpawnUnitOperation.execute` de
  `spawn.py` qui force `ai_controlled=True` + on-appearance attaque + stats summon-scaled + placement
  adjacent-cible → **il faut une variante `spawn_decoy`** (réutilise `AddUnitOperation`, options propres).
- **Appels prouvés** : `CultDemagogueAbility$$ExecuteBehaviour @1811cdc30` (Isaak) et
  `HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour @180f878f0` (Judh) appellent tous
  `DSLFactory$$Spawn(..., ForSteppable, 0)`.
- **Sélecteurs de tuiles (S, par-ability, différés)** : Judh = `PreviousTile → FreeTilesOrAdjacentFreeTiles
  → First` ; Isaak = `SurroundingTiles(target, radius=0x44) → CanAddUnit → PickRandomly(n=GetVariableForLevel
  0x4f)`. `CanAddUnit`/`PickRandomly`/`First` déjà portés.
- Classification : feuille `Spawn` + sélecteurs tuile = **DSL** ; `AddUnitOperation.Execute` = **impératif ECS**.

**P2 — Steppable "crushed when stepped on".** `MoveUnitOperation$$Execute @180e79ff0` appelle **INLINE**
`KillSteppableUnits @180e7c410` (PAS un CreateTrigger) : `GetSteppableUnits(tuile_dest)` → pour chaque
occupant `IsSteppable @180ed8fc0` (= `HasTrait(0x1b=27)`) **vivant** → enqueue `KillUnitOperation` avec options
`KillUnitOperationOptions$$ForSteppable @180e762c0` (type=2, flags 0x0101 = **kill propre/silencieux**,
partagé Displace/Resurrect). **Ordre dans `Execute`** : `AddMoveEvent` → **`KillSteppableUnits`** →
`UpdateCharging` → `SetMovedFlag` → `RemoveReservation` → **`EvaluateAfterMoveTriggers`**. ⇒ le decoy est
**crushé AVANT** les after-move triggers.
- **DecoysAndMisdirection** (G2) est un `CreateTrigger @180e20050` = `(On(0x2f)|On(0x1d)) & AreFriends &
  AmountIsGreaterThanZero(GetValidDeadDecoys)` → il LIT le decoy DÉJÀ mort (`GetValidDeadDecoys`), d'où
  l'ordre crush-avant-event obligatoire.
- **Insertion Python** (`movement.py`) : dans `MoveUnitOperation.execute`, APRÈS le positionnement sur la
  tuile dest, **AVANT** `after_move_triggers` (là où est le TODO "INCRÉMENT 1b"), ajouter une étape
  `_kill_steppable_units(state, dest_tile)` : énumère les occupants Steppable vivants de la tuile dest → les
  tue via un kill **propre** (`alive=False`, PAS de death-trigger de combat).
- Classification : `KillSteppableUnits` + `KillUnitOperation ForSteppable` = **impératif ECS** (mutateur inline
  du move pipeline) ; le passif DecoysAndMisdirection qui réagit ensuite = **DSL** (G2).

**Hypothèses à confirmer au port (hors structure) :**
1. Le token `genesDecoy` a-t-il un `HealthComponent` (destructible par damage) — lire la config `genesDecoy`.
2. Coût RNG exact de `PickRandomly` pour le placement Isaak (raffinement).
3. `FUN_180002560` = `GetSteppableUnits(tile)` (structure certaine ; symbole gshared non nommé).

**Pièges validator au port :** (1) la crush NE doit PAS déclencher les death-triggers de combat normaux
(`ForSteppable` = kill silencieux) ; (2) ordre crush→after-move ; (3) le decoy n'agit JAMAIS
(`ai_controlled=False`, pas d'on-appearance) — piège si on réutilise `SpawnUnitOperation.execute` tel quel.

### G4 — VERDICT + PORT + LIVE (2026-07-18, ghidra gqfc5mff6c)

**Arbre natif** (`CultDemagogueAbility$$ExecuteBehaviour @1811cdc30`) = `op_Addition` de 3 étages, mirroré
`op_add(SpawnDecoys, op_add(SpawnNeophytesOnDecoys, PerformAINeophyteTurn))` (`entities.behaviours.op_add`) :
1. **SpawnDecoys** : `Spawn(PickRandomly(CanAddUnit(SurroundingTiles(target, range)), n=GetVariableForLevel
   0x4f), genesSmnDecoy, ForSteppable)`. `0x4f`=var **`nrOfSummons`** (config-scalé par niveau, 4→8 ; NON
   rarity-scaled) = nombre de decoys. `0x44`=`constants.range`=2. → feuille `spawn_decoy` (G1).
2. **SpawnNeophytesOnDecoys** : sur **`ceil(count/2)`** (`Half`=`DivideAmount mode1=Ceiling @180f19800`) des
   decoys ALLIÉS dans le disk `range` autour de la cible → `Spawn(genesSmnNeophyte, WithStatsFromConfig)`
   stats **`summon*_2`** (config-scalées × mult). `ai_controlled=False` (Neophyte = Ambush+BattleFatigue, PAS
   Summon). Cohabitation decoy+neophyte (Q3c : aucun nœud kill-decoy dans l'arbre — CONFIRMÉ live).
3. **PerformAINeophyteTurn** : `PerformAIAction(FriendlyNeophytesAroundTarget, 0, 1) @180fcba10` = chaque
   Neophyte joue un **TOUR AI COMPLET** (move+attaque) → `decide_and_apply` (PAS 1-attaque type ScarabHive).
Cible ennemie `Target()@0x178` collapsée. Sélecteurs S (SurroundingTiles/CanAddUnit/Half/friendly-decoys)
collapsés impérativement dans les feuilles (résolus à l'exécution, data-dep : les neophytes lisent les decoys
posés). Port : `runner/abilities/genestealer.py` (module dédié, `behaviours.py`/`loki.py` déjà > 1000 l.) +
`build_summon_context`/`_spawn_config_grot` généralisés (`key_suffix`, `ai_controlled`). Registré `handler.py`.

**Confirmé live (probe cast Isaak dist 2 d'un ennemi central)** : `mutated=True`, decoys+Neophytes apparaissent.
**Neophyte hpMax = 2992 = `summonHp_2[L50]=1662 × mult 180% = 2992`** (Isaak L50/mult180) — le PORT reproduit
**BIT-EXACT** (`test_neophyte_stats_bit_exact_vs_live`). Neophytes = ceil(decoys/2) (port).

**⚠ FINDING durable — END-STATE ENTANGLED (à retenir pour G2/G6)** : les tours AI immédiats des Neophytes
(étage 3) **déclenchent `DecoysAndMisdirection` (G2, passif Isaak NON porté)** → des decoys SUPPLÉMENTAIRES
(live : **10 decoys** pour ~5-6 posés de base + doublons de tuiles), et l'**overwatch ennemi TUE des Neophytes**
pendant leur tour (hp=0, hpMax intact). ⇒ le comptage de decoys/positions end-state n'est PAS confrontable en
isolé ; l'invariant robuste confronté = **hpMax de spawn du Neophyte** (indépendant du bruit) + relation
`neo_count == ceil(decoys/2)` (port). La validation end-state COMPLÈTE de G4 nécessitera **G2**.

**Test** : `tests/engine/runner/test_cultdemagogue_migration_live.py` (3/3 ✓, drive Isaak→dist≤2 + cast live +
confronte hpMax bit-exact). Gardes vertes : scarab_hive/scarab_summon (build_summon_context), summon_ability_
ports/summon_trait_effects (`_spawn_config_grot` : 7✓) → 0 régression. ⚠ NON committé.

### Table mirror native → Python (G1)

| Native (VA) | Python cible |
|---|---|
| `DSLFactory$$Spawn @180dfbc60` → `SpawnUnitBehaviour.Execute` → `AddUnitOperation.Execute` | socle `spawn.py` `AddUnitOperation` (réutilisé) |
| `SpawnUnitOptions$$ForSteppable @180fd60a0` | variante `spawn_decoy` (level 1, `ai_controlled=False`, no on-appearance, stats config brute) |
| `MoveUnitOperation$$KillSteppableUnits @180e7c410` | étape inline `movement.py` avant after-move |
| `KillUnitOperationOptions$$ForSteppable @180e762c0` (type=2, flags 0x0101) | options du kill propre |
| `UnitExtensions$$IsSteppable @180ed8fc0` = `HasTrait(27)` | filtre trait Steppable=27 |

### G1 — PORTÉ + VALIDÉ (2026-07-18)

- **`spawn_decoy` + `build_decoy_context`** (`runner/operations/spawn.py`) : réutilisent le socle
  `AddUnitOperation` ; token genesSmnDecoy owner=caster, traits Steppable+Decoy, `ai_controlled=False`, INERTE,
  stats config brute (level 1, PAS de summon-scaling). Le decoy n'a **aucun HP de config** (`genesDecoy.stats`
  = juste `AbilityLevel:1`) → `HealthComponent(hp=1)` = sentinelle token (flaggé HARDCODE ; « destroyed if
  damaged » = instakill, à raffiner G2).
- **`_kill_steppable_units`** (`runner/operations/movement.py`) : étape INLINE dans `MoveUnitOperation.execute`,
  AVANT `after_move_triggers` (ordre natif). Kill **propre** (`alive=False`+hp0, SANS `after_death_triggers`)
  des occupants Steppable de la tuile d'arrivée, mover exclu. Fire pour TOUT move (decoy/spore-mine).
- **Test** : `tests/engine/runner/test_decoy_foundation_live.py` (3/3 ✓) — MÉCANISME sur substrat runner live
  (spawn fidèle + crush-on-step + kill propre scoped). Gardes vertes : `test_runner_move_live` (2✓+1xfail
  pré-existant), `test_overwatch_live` (1✓) → 0 régression sur le move pipeline / la cascade after-move.
- **Reste (deferred)** : la confrontation live-oracle de la CHAÎNE COMPLÈTE (natif pose le decoy → ennemi
  marche dessus → crush + Blast) vient à **G2/G4** (aucune ability native ne place de decoy en autonome).
  ⚠ NON committé.

### G2 — VERDICT + PORT + LIVE (2026-07-18, ghidra gqfc5mff6c)

**CORRECTION de la structure G1** : DecoysAndMisdirection n'est PAS 1 trigger qui branche enemy/ally — c'est
**DEUX abilities-triggers DISTINCTES** (2 entrées `AbilityAndEffectCache`), split par la **condition de
faction** (`AreEnemies` vs `AreFriends`), PAS par l'event :

| Ability native | CreateTrigger | CreateBehaviour |
|---|---|---|
| `DecoysAndMisdirection_DamageEnemiesAbility` (path ENNEMI) | @180e20310 | @180e20190 |
| `DecoysAndMisdirection_BuffFriendsAbility` (path ALLIÉ) | @180e20050 | @180e1fe30 |
| base `ADecoysAndMisdirectionAbility` : `GetValidDeadDecoys` @180e13550, `DidPositionChangeKillFriendlyDecoy` @180e13520 | — | — |

**Events** (enum natif) : `0x1d=29=UnitPositionChanged_2` (move-onto), `0x2f=47=UnitResurrected` (résurrect →
G3). `MoveUnitOperation.EvaluateAfterMoveTriggers @180e79770` émet `On(0x24)` (aucun conso porté) → `On(4=
UnitAfterMove)` (overwatch) → `On(0x1d)`. Le decoy est crushé INLINE (`_kill_steppable_units`, G1) AVANT →
`GetValidDeadDecoys` le lit **déjà mort**. `dispatch.after_move_triggers` émet désormais On(4) PUIS On(0x1d).

**Conditions** (slots : 0x148=owner Isaak, 0x158=stepper, 0x180=decoy) :
- DamageEnemies @180e20310 = `On(0x1d) & AreEnemies(owner, stepper) & AmountIsGreaterThanZero(GetValidDeadDecoys)`.
- BuffFriends @180e20050 = `(On(0x2f)|On(0x1d)) & AreFriends(owner, stepper) & AmountIsGreaterThanZero(...)`.
- `GetValidDeadDecoys @180e13550` = `Filter(AllDeadUnits, AreFriends(owner, decoy) & HasTrait(decoy, 0x41d=1053
  Decoy) & IsKilledThisTurn(decoy) & AreEqual(Killer(decoy), stepper) & Contains(Tiles(stepper),
  MainTileOfUnits(decoy)))` → collapse `_valid_dead_decoys` (decoy mort, ami owner, co-localisé au stepper ;
  Killer/IsKilledThisTurn approximés par la co-localisation — positions exclusives, count 1 en pratique).

**Behaviours** :
- **DamageEnemies @180e20190** = `Repeat(AttackWithAbilityDamage(owner, stepper, MinMaxDamage, Blast, GetHits=1),
  Count(GetValidDeadDecoys))`. ⚠ **DÉCOMPILE VÉRIFIÉ (moi, pas juste le re-expert)** : la feuille
  `DSLFactory$$AttackWithAbilityDamage @180de9c90` (overload avec hits) → base @180de9e50 =
  `AttackBehaviour(AbilityDamageBehaviour(MinMaxDamage, Blast, source))` = **pipeline crit/block/after-hit
  COMPLET** (PAS le direct pierce-only de la feuille port homonyme fire-DoT). Porté par le leaf
  `AttackWithAttackDamage` (`execute_ability_attack`, config MinMaxDamage 1455-1746@L65) — même pipeline que
  Stikkbomb/Fragstorm/Plasma. Cible = le **stepper** (0x158). Le profil Blast porte `HitsMultipleMembers`
  (splash) → **FLAG** : le splash multi-membres n'est PAS re-dérivé (leaf attaque le stepper seul) — à
  confirmer live si un scénario stable existe.
- **BuffFriends @180e1fe30** = `AddEffect(1379 DecoysAndMisdirection_ExtraDamage +582, on=stepper)` +
  `If(HasFaction(stepper, 0xf=GenestealerCults), spawn_decoy(First(SortTilesByUtilityForSummon(CanAddUnit(
  AdjacentTiles(stepper))))))`. L'effet 1379 **existait déjà** (`effects/loki.py`
  `DecoysAndMisdirectionExtraDamageEffect`, ForAddition `extraDmg` query-time au niveau du SOURCE ; leçon
  *check-own-port-before-RE* : j'avais créé un doublon, supprimé) — le trigger le POSE + initialise son
  niveau/mult depuis l'owner Isaak. Nouveau decoy = réutilise `spawn_decoy` (G1).

**Port** : `runner/operations/triggers/genestealer.py` (2 classes `TriggeredAbility` + helpers `_valid_dead_
decoys`/`_are_friends`/`_are_enemies`/`_adjacent_free_tile`) ; registré `ABILITY_TRIGGERS["DecoysAndMisdirection"]`
(dispatch.py) ; `after_move_triggers` émet On(0x1d).

**⚠ FINDING durable — ORACLE LIVE ENTANGLED (prouvé live 2026-07-18)** : la SEULE source live de decoy
(CultDemagogue G4) voit ses decoys **CONSOMMÉS par les tours AI immédiats des Neophytes** → **0 decoy vivant
post-cast** (probe : 1 decoy placé/mort, 0 neophyte survivant sur target cornered ; même dynamique que le
"10 decoys" G4). Donc **pas de decoy stable à driver un ennemi dessus** → confrontation du MONTANT natif du
Blast infaisable proprement. **Validation retenue = WIRING DÉTERMINISTE sur ÉTAT LIVE RÉEL** : `spawn_decoy`
(G1, live-validé) pose un decoy ami près d'une unité réelle → rejeu du step-on (`MoveUnitOperation` +
`after_move_triggers` = code natif-mirror) → assert le bon trigger fire. Le MONTANT du Blast vient du pipeline
`execute_ability_attack` déjà live-validé.

**Test** : `tests/engine/runner/test_decoys_misdirection_migration_live.py` (3/3 ✓) — enemy-step→Blast+crush,
friendly-step→effet 1379+nouveau decoy (GS), garde no-over-fire (move sans decoy → 0 trigger). Gardes vertes :
`test_overwatch_live` (1✓, On(4) intact), `test_runner_move_live` (2✓+1xfail préexistant),
`test_decoy_foundation_live` (3✓ G1) → **0 régression** sur le vecteur after-move. **COMMITTÉ `d3126db`**.

### G5 — PORTÉ + LIVE-VALIDÉ (2026-07-18) — decompile @1811e8de0 re-confirmé

**PORT** : `HeroicFusilladeAbility` + `heroic_fusillade_tree()` (`abilities/genestealer.py`), registré
`handler.py[1180]`. Nouveaux nœuds DSL : `IsSurrounding` (`entities/triggers.py`, mirror `@180df5320`),
`ChangeStat` (`runner/abilities/behaviours.py`, mirror `DSLFactory.ChangeStat @180debdc0` →
`ChangeStatBehaviour.Execute @180fbfb10`, modes 2=Add / 3=Sub via `apply_change_stat`/`revert_change_stat`).
Test `test_heroic_fusillade_migration_live.py` (3/3) : move+splash+crit_bonus+revert net-nul ; gate
déjà-adjacent ; **crit-buff OBSERVABLE au roll** (CC forcé 100 : l'ability inflige > la même attaque splash
sans le buff, même seed). Guards plasma+stikkbomb OK.

**3 CORRECTIONS tirées du décompile @1811e8de0 (vs le verdict RE ci-dessous)** :
1. **SPLASH inclut la CIBLE** : natif `SurroundingUnits(target, radius, includeCenter=1)` → `SurroundingTiles(
   target, includeCenter=1, radius) @180dfca70` = disk INCLUANT la tuile cible (le MOVE-ring passe
   `includeCenter=0` = exclu-centre). i2 « 6x ... to the **target AND** all other enemies surrounding it ».
   Porté = `Union(Target(), Alive(SurroundingEnemies(TargetTile(), 1)))`.
2. **surrounding radius = 1** (DslContext `@+0xc0` = adjacence, i2 « surrounding **hex** »), **DISTINCT** du
   `range` config = **2** (`GetNumberConstant(0x16)`, portée de MOUVEMENT `MovableTilesInRange`). Le natif lit
   `@0xc0` (PAS `GetNumberConstant` — contraste CultDemagogue @1811cdc30 qui passe `GetNumberConstant(0x44)=range`).
   `constants` = `{range:2, nrOfHits:6}` ; `variables` = `minDmg/maxDmg/extraCritDmg` (rarity-scaled, `extraCritDmg[65]=218`).
3. **MoveUnit options NULL** (`local_1b8..local_188 = 0`) → **AUCUN after-move crush/overwatch** (feuille
   `MoveUnit` fidèle, cf. #4). Le verdict RE « déclenche crush/overwatch » était **imprécis** — corrigé au décompile.

---

### G5 — VERDICT re-expert (2026-07-18, ghidra gqfc5mff6c, PROUVÉ) — [porté, cf. ci-dessus]

HeroicFusillade (id **1180**, Judh `genesKelermorph`, namespace natif `Abilities.Active.Loki`). Actif —
**décompilé = arbre DSL** ; à porter comme CultDemagogue (`ActiveAbility` dans `abilities/genestealer.py`,
`ABILITY_TYPE=1180`, registré `handler.py`).

**`HeroicFusilladeAbility$$ExecuteBehaviour @1811e8de0`** = `op_add` de 3 étages :
```
op_add(
  If( Not(IsSurrounding(target, caster, radius)), MoveUnit(caster, destTile) ),        # 1. MOVE
  If( IsAlive(target),
      op_add( ChangeStat(CritDamage=10, mode=2=Add, mag),                              # 2a. buff crit (pose)
      op_add( AttackWithAttackDamage(caster, splash, Projectile, hits=6),              # 2b. ATTACK 6x splash
              ChangeStat(CritDamage=10, mode=3=Sub, mag) ) ) ) )                       # 2c. buff crit (retire)
```
- **MOVE** : dest = `First(SortTilesByUtility(CanAddUnit(SurroundingTiles(target, range)) &
  MovableTilesInRange(caster, Direct(GetNumberConstant(0x16)=range=2), reachOnly), 7))` @180df6a20/…/180df6ae0.
  Vraie `MoveUnitOperation` (déclenche crush/overwatch). Gate `Not(IsSurrounding(target, caster, radius))
  @180df5320` = move SEULEMENT si la cible n'entoure pas déjà le caster (sinon skip = déjà adjacent).
  Sélecteur S lourd → COLLAPSER en `_move_dest_tile(state, caster, target, range=2)` (tuiles libres autour
  cible ∩ atteignables ≤range, tri utilité, first) → `MoveUnit(Caster(), FixedTiles([dest]))`.
- **ATTACK** : splash = `Unobscured(Enemies(SurroundingUnits(target, radius)))` @180dfcb70 = ennemis-du-caster
  VIVANTS entourant la cible (cible incluse, splash cible-centré comme PlasmaGrenade), **enemies-only** (pas
  friendly-fire). `hits = GetNumberConstant(0x2f) = nrOfHits = 6` (gameconfig). Profil Projectile P15. →
  leaf `AttackWithAttackDamage(splash_sel, "HeroicFusillade", "Projectile", is_melee=False)` mode `multi=True`
  (sélecteur `Alive(SurroundingEnemies(TargetTile(), radius))` ; `Unobscured`/LoS collapsé = no-op board
  dégagé, HYPOTHÈSE à valider si cover).
- **CRIT-PER-FREE-HEX** : `mag = Multiply(Direct(GetVariableForLevel(0x42)=extraCritDmg), nbFree)` où
  `nbFree = Count(Unobscured(CanAddUnit(SurroundingTiles(target))))` = tuiles LIBRES entourant la cible au
  cast. **`extraCritDmg[L]=218@L65` rarity-scaled** → `mag = 218 × nbFree`. Appliqué par **2× ChangeStat sur
  CRIT_DAMAGE (StatType 10)** (`ChangeStatBehaviour.Execute @180fbfb10`, mode2=Add avant l'attaque, mode3=Sub
  après) = **buff crit temporaire net-nul scopé à l'attaque**, cible = le caster (self-buff). Port : ops
  `apply_change_stat`/`revert_change_stat` (stat_ops.py) sur CRIT_DAMAGE=10 encadrant l'attaque, OU paramètre
  d'attaque si l'engine ne relit pas CRIT_DAMAGE au roll.
  **⚠ VALIDATOR PRIORITÉ #1** : vérifier LIVE que le crit-bonus est OBSERVABLE (hits critiques +218×nbFree,
  retiré après) — dépend que `ApplyCritDamage @181000210` lise `GetStat(CRIT_DAMAGE)` au moment du roll.
- **RÉ-ARME post-résurrection** = trigger SÉPARÉ `HeroicFusillade_ResurrectAbility$$CreateTrigger @180f86590`
  = `On(0x2f=UnitResurrected=47) & OwnerIsTarget` → reset flag "ability used" (mécanisme exact = tranche
  trigger, avec G3-Ambush ; PAS dans l'ability active).

**Insertion** : `HeroicFusilladeAbility(ActiveAbility)` dans `abilities/genestealer.py` (`heroic_fusillade_tree()`
= l'op_add ci-dessus, sélecteurs S collapsés), registré `handler.py` `ABILITY_CLASSES[1180]`. Ajouter
`HeroicFusillade` à l'enum `ActiveAbilityType` si absent. Émet `{move, main_attack, splash, crit_bonus, dsl}`.
Validator : (1) crit-bonus observable, (2) `nbFree` compté correctement (drive positions), (3) MOVE sur la
bonne tuile + gate déjà-adjacent, (4) splash enemies-only + cible incluse. ✅ PORTÉ + live-validé 2026-07-18
(cf. section « PORTÉ + LIVE-VALIDÉ » ci-dessus) ; ⚠ NON committé.
