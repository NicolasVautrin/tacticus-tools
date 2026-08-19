# Playbooks par-ability (2e étage de l'IA)

État faithful du **second étage** de l'IA Tacticus, sous le scorer `Utilities` : la couche de
décision **par-ability**. Les leaves Tile `TriggeredAbilities(2)` / `NonOwner(4)` /
`UnitSpecificBehaviours(3)` y délèguent — elles chargent un playbook via `PlaybookDatabase`,
énumèrent son `Calculate{Movement,Attack,Repair}UtilityInSteps` et **somment** les `Fix64` rendus.

Frères : [`architecture.md`](architecture.md) (le bucket-tree au-dessus), [`scoring.md`](scoring.md)
(`CalculateActionUtility` partagé), [`prediction.md`](prediction.md) (dégât/soin/repair),
[`pathfinding.md`](pathfinding.md), [`status.md`](status.md).

## PlaybookDatabase — factory + cache paresseuse (`..ctor` @1810e0380)

`PlaybookDatabase` est **sans état décisionnel** : pure factory. Le ctor reçoit **11 services
injectés** (champs `0x10–0x60` : match-state, battle-query, registres ability/config, config
`Utilities`, RNG — identités non toutes résolues) qu'il **forwarde dans CHAQUE playbook construit**.
Tout l'état vit dans ces refs.

Il expose **4 registres paresseux** (5 maps), chacun = une map `(int → builder Func)` + un cache
`(int → instance)`, peuplés à la 1ʳᵉ `Load`. Pattern uniforme :
`cache.TryGetValue → builder.TryGetValue → builder.Invoke(slot 0x18) → wrap-ctor (forward 0x10–0x60) → cache.Add`.

| champ map/cache | clé | overload | rôle |
|---|---|---|---|
| `0x68` / `0x70` | AbilityType id | `LoadPlaybook(int,bool)` @1810e0090 | **active-ability** (218 entrées) ; +fallback DEFAULT |
| `0x78` / `0x80` | (param. par la clé) | `LoadDefaultActiveAbilityPlaybook` @1810df810 | builder par **défaut** (1 délégué) |
| `0x88` / `0x90` | id (unit/type) | `LoadPlaybook(int)` @1810dfd10 | **owner/unit** (104 entrées) ; wrap 1-arg |
| `0x98` / `0xa0` | ability id | `LoadPlaybookNonOwner` @1810df9a0 | **non-owner**, SÉPARÉ (25), init-via-interface |
| `0xa8` / `0xb0` | behaviour `{0,1,2,3}` | `LoadPlaybook(int)` @1810dfed0 | **unit-specific behaviour** (4) |

`HasNonOwnerPlaybook` @1810d0250 = `ContainsKey(0x98)`. **351 registrations** au total (218 + 104 +
25 + 4) dans `InitializePlaybookBuilders` @1810d02b0.

## Catalogue (`InitializePlaybookBuilders` @1810d02b0 — ~62 KB, 351 `Add`)

- Chaque registration = `dict.Add(<keyImm32>, <lambda b__31_N>)`. **Clé = valeur enum AbilityType** :
  - `17` / `18` = **normal-attack** génériques ;
  - bloc contigu **1000–1230** = abilities **par-personnage** ;
  - outliers `1152`, `1182`, `1220`, `9007`.
- Chaque lambda = factory **singleton paresseuse** → `new <X>Playbook(...)`.
- Namespaces :
  - `Playbook.Common.*` — génériques (`DefaultActiveAbilityPlaybook` = fallback, `HealPlaybook`, `RepairPlaybook`) ;
  - `Playbook.Idun.*` — `NormalAttackPlaybook`, `GetOverHerePlaybook`, … ;
  - `Playbook.Loki.*` — par-personnage (`StormOfFlensingBlades`, `MortisRound`, `MightOfHeroes`,
    `PrecisionShot_Aim`/`_Attack`, `MultiThreatEliminator`, `FragBomb`, `SaviorProtocols`, …).

## Interface playbook (hiérarchie générique)

`Playbook<T>` → `TriggeredAbilityPlaybook<T>` → `TriggeredAbilityNonOwnerPlaybook<T>` ; sœur
non-triggered `BasePlaybook`. Branche **comparable** : `ComparablePlaybook<T> → Playbook<T>` (cf.
communs ci-dessous).

- `Calculate{Movement,Attack,Repair}UtilityInSteps` → **`IEnumerable<Fix64>`** (state-machines `d__N` ;
  `get_Current` boxe le `Fix64` @`iter+0x18`).
- `GetUtilityValue(key)` → `Dictionary<string,int>.TryGetValue` (défaut **0** + warn) lifté en `Fix64`.
- + `GenerateAction`, `ShouldEvaluate`/`Evaluate`, `GetAbilityState`.
- **Contrat de yield : un seul `Fix64` par (ability, case)** = l'utilité totale de l'ability, sommée
  par le dispatcher Tile.

## Modèle générique à porter

    score(case) = Σ_{candidat énuméré} [ gate(candidat) ? Σ weightKeys_applicables(candidat) : 0 ]

avec `weight = playbookWeights[key]` (int, défaut 0) → `Fix64`. **Par-ability = uniquement** :
(a) le **gate** (effet/trait/faction/adjacence + ids) ; (b) l'**énumération** (quel ensemble de
cibles/tuiles) ; (c) les **clés de poids** + l'arithmétique. Tout le reste (scaffolding itérateur,
`GetUtilityValue`, layout source) est dans la base.

## Playbooks COMMUNS = le scorer générique (la découverte qui dé-risque le port)

Les 4 playbooks à plus forte couverture (Default / NormalAttack / Heal / Repair) **ne sont PAS
bespoke à clés-strings**. Ce sont des sous-classes MINCES de `ComparablePlaybook<T> → Playbook<T>`
qui héritent du **scorer générique partagé** `ComparablePlaybook<T>.CalculateActionUtility`
@181406ee0 — **identique au pipeline de [`scoring.md`](scoring.md)** :

    score(action) = CustomUtility(hook)
                  + CalculateUtilityFromPredictions @181407890   # Σ dégât/soin/effet/repair events
                        #   dégât = (prédDmg × mult) × GetUtilityValue(ForDamagePrediction, idx 0x22=Damage34)
                        #   soin  = HealRatio × GetUtilityValue(ForHealPrediction,   idx 5   = Heal44)
                        #   effet = ForEffect (idx 5) × magnitude ; repair = ForRepairPrediction (idx 6 = Repair46)
                  + UtilityAttackCase.Base (idx 0x36 = 54)
                  + CalculateUtilityFromTilePrediction @181408740  # positional/move (Tile7, idx 8)

Le calcul **prédiction → utilité** est donc le **PIPELINE PARTAGÉ** (utilités composées
`Damage34`/`Heal44`/`Repair46`/`AddedTileEffects45`/`Tile7` déjà portées), **pas** du code
par-playbook. Les `GetUtilityValue` ici sont des génériques `GetUtilityValue<TCase>` sélectionnés par
**INDEX** (`0x22`/`5`/`6`/`8`/`0x36`), **pas** des clés-strings → **aucune nouvelle clé BC à
résoudre** pour les communs.

Chaque playbook commun n'override QUE : (a) le **tag** d'ability (ctor) ; (b) **ShouldExecute** (gate) ;
(c) **CalculateCustomUtility** (constante) ; (d) **Make{Damage,Heal,Repair}Predictions** (fournisseur).

| playbook | base | tag | ShouldExecute (gate) | CustomUtility | scoring |
|---|---|---|---|---|---|
| **DefaultActiveAbilityPlaybook** | `BasePlaybook` | per-id | ability usable | – | **flat 1.5 / cible éligible** (zéro prédiction/poids) — entièrement porté |
| **NormalAttackPlaybook** | `ComparablePlaybook<T>` | `0x11` (17) | `!HasTriggeredAbility(0x48=72)` ET dispo | **+1** | dégât = pipeline (`Damage34` = `damage.py`) |
| **HealPlaybook** | `ComparablePlaybook<T>` | `0x12` (18) | `heal>0` ET non(boss self-heal) | 0 | `HealRatio × Heal44` (montant bloqué) |
| **RepairPlaybook** | `ComparablePlaybook<T>` | `0x1c` (28) | off-cooldown | 0 | `Repair46` additif (montant bloqué) |

**Montants Soin/Repair** : Heal = `StatAmount(weapon) × max(WeaponHighestHits,1)` clampé HP-manquant
→ `HealRatio = min(1, usefulHeal/predHeal)` ; Repair = prédiction (`IBattleQuery` idx `0x29`, sœur du
heal idx `0x28`). `aiPredict` est dégât-only → ces montants restent **BLOQUÉS** (cf.
[`prediction.md`](prediction.md)) ; gates/tags/custom portés, le scoring soin/repair s'active dès
qu'un RPC de prédiction complet existe.

### MAJ #37 (2026-07-09) — montants Soin/Repair NON bloqués (offline-sourceables) + 2 régimes heal

**Correction du « BLOQUÉ » ci-dessus** : la magnitude soin/repair N'A PAS besoin d'`aiPredict`. Elle vit
dans une **variable de config d'ability** `hpToHeal` / `hpToRepair` (tableau per-niveau, flaggé
`variablesAffectedByRarityBonus`), exactement comme `minDmg`/`maxDmg` du dégât → **offline-sourceable**
via `engine.entities.effects.magnitude.ability_var(name, "hpToHeal"|"hpToRepair", level, multiplier_pct)`.
22 abilities la portent (CombatRestoratives, DefendTheDivineWork, MedicusMinistorum, RitesOfRestoration,
HealingBalms…). Vérifié desc↔variable sur 5 (MedicusMinistorum 14, RitesOfRestoration 36, CombatRestoratives
72, BloodChalice 60, HealingBalms 60 = tous `hpToHeal[lvl]` **exactement**, sans `×hits`). Chaîne native
confirmée : `HealAbility.HealAmount @180e345b0` = `StatAmount(weapon@+0x160) × Max(WeaponHighestHits,1)` ;
`RepairAbility.RepairAmount @1811c4860` = idem (sans modifier ⇒ = base). Effectif = `min(amount, missing)`
(`predict_heal_effective`/`predict_repair_effective`, déjà portés). Gap wiring RESTANT (`action_generators.py`) :
`_heal_candidates`/`_repair_candidates` saturent à `missing` au lieu d'`ability_var(hpToHeal/hpToRepair)` ;
identification heal par `"Heal" in name` INCOMPLÈTE (rate MedicusMinistorum/CombatRestoratives/… ; devrait
être par présence de `hpToHeal` / ActiveAbilityType) ; terme ARMOR repair = 0.

**DEUX régimes de soin distincts** (routage par le flag Comparable/NonComparable du playbook) :
- **Comparable** (`HealPlaybook.MakeHealPredictions @181184a70` → `GenerateHealPredictions`) : HealingBalms,
  TwistedScience, base Heal(18). Utilité = `Σ HealUtility = Σ (effective/(maxHP+1))×100×friendSign×bossMod`.
- **NonComparable** (`CombatRestorativesPlaybook.EvaluateNonComparable @181125fd0`, id 1002 ; et
  `RitesOfRestorationPlaybook` id 1039) : ciblage `HealTargets @1811cca50 = Friends(AdjacentUnits(caster,r=1))
  + self` (self + alliés adjacents, PAS de wrapper `Healable` ⇒ inclut les mécaniques). Utilité =
  **`Σ (1 − FillUpStatComponent.RemainingPercentage @180f9be60)`** avec `RemainingPercentage = max(0,cur/max)`
  ⇒ `Σ (missing/maxHP)` = somme des fractions de PV manquantes des cibles. **N'utilise PAS `hpToHeal`**
  (magnitude ≠ utilité dans ce régime). Gate `MIN_UTILITY = Fix64.FromIntFraction(9,10) = 0.9` (cctor
  @1811265c0). Sweep positions caster → argmax.
  → **CombatRestoratives PORTÉ** dans `engine/playbook/noncomparable/heals.py` (`CombatRestorativesPlaybook`,
    smoke-test OK) ; **agreement LIVE encore à confirmer** (exige un état mid-combat avec alliés blessés
    current<max ; `--hp-target` met current=max donc ne blesse pas → driver un échange ou patcher la BC).

**Implication** : le cœur générique (`CalculateActionUtility`) déjà construit EST le moteur des
abilities COMMUNES (= la grande majorité des actions). Le dégât marche (`damage.py`) ; soin/repair ne
manquent que la prédiction. Les playbooks **bespoke** sont des **ajouts incrémentaux à clés-strings**
par-dessus ce cœur.

### MAJ #76 (2026-07-09) — tie-break du sweep NonComparable = ORIGINE préférée (confirmé LIVE)

**Cause d'un MISS de positionnement/cible sur les self-cast heal** (le port bougeait pour rien : tgt=23
tuile de move vs natif 22 origine). Ce N'ÉTAIT PAS l'adjacence — c'est le **TIE-BREAK du balayage de
positions**.

- **RE tie-break** (LU) : `Bucket.AddAction @1813fbcc0` **seed** la 1ʳᵉ action ajoutée puis ne la remplace
  QUE si la nouvelle est **STRICTEMENT supérieure** (`System.TimeSpan.op_GreaterThan`) → **keep-first au
  tie**. Le générateur `ActiveAbilityActionGenerator.<GenerateActions>d__7 @18119a3f0` évalue les positions
  de move puis évalue **TOUJOURS** la `NullPosition` (cast EN PLACE) ; chaque position → `EvaluateNonComparable`
  → `Merge` dans le bucket. Une tuile de move n'est retenue (`FUN_18000c1b0(0x3f)` = `HasValidTargets(unit,
  movePos, ability)`) que si elle a des cibles valides.
- **Observable CONFIRMÉ LIVE (4/4)** : à utilité CONSTANTE (self-heal, seul le caster blessé → terme
  adjacents = 0), le natif **RESTE EN PLACE** (target = MainTile origine, pas de MoveUnitMessage). Il ne
  **bouge que si une tuile de move AMÉLIORE STRICTEMENT** la somme de soin (`Σ (1−RemainingPercentage)` des
  cibles couvertes). Règle nette : **origine préférée au tie ; move sur gain strict**.
- **Adjacence `HealTargets`** : `DSLFactory.AdjacentUnits @180de8320` = `AdjacentTiles + Units − unit@pos`,
  via `IterateAdjacentTiles` = **même porte d'élévation `|Δelev|<2`** que les comptages `GetAdjacent*`
  (#45). Le port des heals utilisait `hexgeo.distance==1` brut (fork) → factorisé en `bq.is_adjacent`
  (comptages ET heals partagent 1 primitive).
- **Fix** (`engine/playbook/noncomparable/_base.py`) : `_sweep_origin_first(ctx) = [origine] + moves`, appliqué
  aux 4 self-cast (CombatRestoratives 1002, RevitalizingMalignancy 1037, DefendTheDivineWork 1117,
  RitesOfRestoration 1039) + `bq.is_adjacent` partagé. **Validé LIVE** (deathRotbone/ultraApothecary/
  admecManipulus self + →destroyer : tous in-place, MATCH target+ability natif).
- ~~**NovaBoost/NovaShield RÉCONCILIÉS (#80) par CLASSE de cible**~~ — **la dichotomie tombe (R1).** Elle
  supposait que l'ordre BRUT du générateur plaçait l'origine en DERNIER, et faisait dépendre le tie-break
  de `HasValidTargets(0x3f)` par-tuile-de-move (fonction derrière un trampoline, jamais lue). Le décompilé
  tranche autrement : la liste `tiles` vient de `IBattleQuery`+0xe =
  `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor`, un `OrderedSet` **SEEDÉ avec la
  position courante** ⇒ **origine PREMIÈRE pour TOUT le monde**, self-target comme tile-target. Il n'y a
  donc qu'UNE classe d'ordre : `ctx.reach_nc` est origine-first (`engine.ai.context.action_tiles_for`), et
  `_sweep_origin_first` en devient l'identité. Ce qui reste vrai de #80 : l'utilité de NovaShield DÉPEND de
  la position (100·ennemis marqués) → son argmax est non-trivial et le tie-break n'y est que secondaire.
  Détail et mesures : `docs/rl/case-r1-origin-action-tile.md`.

### MAJ #78 (2026-07-09) — InspiredToGreatness (tauAunShi) : refresh d'ability alliée level-weighted

`InspiredToGreatnessPlaybook.EvaluateNonComparable @181145b80` (id 0x43a=1082) — playbook NonComparable
**bespoke** (≠ Σ wound-fraction des heals) porté + **VALIDÉ LIVE** (MATCH ability+cible).

- **Mécanisme** : l'ability refresh (`RepairOrHeal @1811eb050` = `If(IsRepairable, Repair, Heal)` +
  `InspiredToGreatness_OverrideLevelEffect`) l'ability d'un **ALLIÉ**. La cible = l'allié (unit-id), pas
  une tuile.
- **Ciblage** (`GetDynamicInvalidTargetReason @1811eaec0`) : cible != caster, PAS trait `0x7e7`, ET
  (repairable | healable-blessé | ability-en-cooldown) [slots `0x11/0x12/0x31`]. -> l'AI ne peut cibler un
  allié QUE s'il est blessé/réparable **ou** a une ability en cooldown.
- **Utilité** : la boucle sur les cibles éligibles ajoute une action **UNIQUEMENT** pour l'allié dont
  l'ACTIVE ability (`ActiveAbilityComponent.GetActive`) est `CanCurrentlyBeUsed == FALSE` (= EN COOLDOWN),
  avec `util = Fix64.FromInt(Level.ToZeroBasedIndex(AbilityState.Level))` = **NIVEAU zero-based** de cette
  ability. `Bucket.AddAction` argmax STRICT -> refresh l'ability EN COOLDOWN de **plus HAUT NIVEAU**. cctor
  `NonComparablePlaybook(0x43a)` SANS min -> `MIN_UTILITY=0`.
- **Data offline** (aucun changement de hook) : éligibilité = `abilityTargets` (le jeu applique les 3
  checks ; `Tgt.targetId` = l'allié) ; cooldown = entrée active de `dv.units[ally].abilities` (`usable`) ;
  niveau = `combatSnapshot.unitConfig.activeAbilityLevel` (cfg+0xb8 ; `GetStat(18)`=null en snapshot).
  Plumbing : `NCContext.{active_levels(callable), units}` + `AiDecisionContext.active_ability_levels()`
  (combatSnapshot cache/rid).
- **Validation** (`val78` craft) : drive `tauShadowsun` à caster son active (1087 -> cooldown) ->
  `abilityTargets(tauAunShi,1082)` surface tauShadowsun -> **natif ET port castent 1082 tgt=86, util=49**
  (level 50). MATCH ability+cible.
- **Positionnement move-to-reach (#81, RÉSOLU + VALIDÉ)** : le natif **BOUGE** pour atteindre l'allié hors
  portée in-place (casté 1082 avec un move to (1,1)). Porté via un **nouvel RPC hook `castFromTiles`**
  (`rpc-view.ts`) = les tuiles (courante + move) d'où `AttackQuery.GetInvalidTargetReason(caster, tile, ally,
  ability)` est **valide** (`NoBrokenTargetingRule`) — la tuile est un param EXPLICITE (`IEntity`), donc pas
  de construction `UnitPosition` par tuile. Aucun RPC existant ne le donnait (attackPlans évalue 1082 vs
  ENNEMIS `rankCount=0` ; abilityTargets agrège ; `GetBestTileToAttackFrom` vide pour cible alliée) ; la
  reachability offline (range+LoS) n'est pas fiable (natif non-obvie : allié hex-adjacent mais `fromHere`
  vide). Le port émet `to` = origine si `currentValid` (origine-préf #76) sinon 1re tuile de move légale
  (`moveTiles[0]`). **VALIDÉ LIVE** : port `to=(1,1)` == natif move-to (1,1) — MATCH ability+cible+POSITION.
  NB : le cas `currentValid=True` (origine castable) émet `to=None` (origine-préf #76 self-cast) — non
  crafté pour l'ally-target (keep-first-move-first pourrait BOUGER si des tuiles de move sont aussi légales).

### MAJ #79 (2026-07-09) — magnitude du régime COMPARABLE heal câblée (fin du gap wiring #37)

Clôt le **gap wiring** signalé en MAJ #37 : `_heal_candidates` (générateur Comparable) **saturait** le soin
effectif à `missing` (`maxHP - curHP`) au lieu de la vraie magnitude `HealAmount`. Fidélité restaurée par
câblage du helper `ability_var` (déjà RE'd en #37, jamais appelé) — **structure 1:1 du natif**.

- **Chaîne native (décompilée, build gqfc5mff6c)** : `HealPlaybook.MakeHealPredictions @181184a70`
  (identique pour `TwistedScience_HealPlaybook @18116fc60` et `HealingBalms_HealPlaybook @181143100` : les
  bespoke ne diffèrent QUE par `CalculateCustomUtility`/`ShouldExecute`) → `HealAbility.HealAmount @180e345b0`
  = `StatAmount(weapon@+0x160) × Max(WeaponHighestHits,1)` → `GenerateHealPredictions @181409810` (par cible :
  évalue `HealAmount` puis `PredictHeal`) → **`DamagePrediction.PredictHeal @181037180`** = accumule les
  bonus-soin d'effets, puis `MaxFillUp @180f9b790` = **`min(healAmount, missing)`** (+ caps group/boss).
- **Magnitude OFFLINE** = `HealAmount` résolu = la variable de config `hpToHeal` de l'ability, indexée par
  niveau (arme-soin synthétique : `StatAmount(weapon) = hpToHeal[level]`, `hits=1` ⇒ **pas de `×hits`** ;
  vérifié desc↔variable sur 5 abilities en #37). Via **`ability_var(key,"hpToHeal",level,multiplier_pct)`**
  (`engine/entities/effects/magnitude.py`, mirror `ConfigAmount.Calculate @180f171c0`) : gère l'index +
  le **scaling rareté** `AbilityVariablesMultiplierPercentage` (`hpToHeal` ∈ `variablesAffectedByRarityBonus`).
- **Port** (`engine.predict.heal_amount_config` + `_heal_config_key`) : le nom runtime → clé gameconfig
  (soin accordé par un passive `Heal_<P>`/`<P>_Heal` → clé = le passive + **niveau PASSIF** unitConfig+0xBC ;
  soin natif → **niveau ACTIF** +0xB8) ; `multiplier_pct` = `unitConfig.abilityVariablesMultiplier` (+0x74).
  `_heal_candidates` : `effective = predict_heal_effective(heal_amt, cur, max) = min(heal_amt, missing)`
  au lieu de `missing`. Plumbing : `AiDecisionContext.heal_config(uid)` (combatSnapshot cache/rid, expose
  active/passif/multiplier ; `active_ability_levels` #78 préservé).
- **Résidus DOCUMENTÉS (fallback saturation, `heal_amt=None`, sans régression)** : base `Heal(18)` = arme
  RÉELLE (pas de `hpToHeal`) ; `Heal_TwistedScience(1167)` = magnitude SPÉCIALE (`hp` = bump de max-PV, heals
  full-HP ⇒ le custom +100 pilote la décision, pas la magnitude). Seul `HealingBalms_Heal(1212)` a un
  `hpToHeal` propre parmi les 3 routés par le filtre `"Heal" in name`.
- **Validation LIVE (bornée par le pool)** : `HealingBalms`/Baldr (le porteur `hpToHeal` propre) **n'est PAS
  spawnable au rank 17** (blocage pool confirmé, cf. tâche). Validé sur ce qui EST in-pool :
  (a) **resolver live-consistent** — Nicodemus/`BloodChalice` (niveau LIVE 50, mult 180) : port
  `heal_amount_config=4986 = hpToHeal[49](2770) × 180/100` — confirme clé+index+**multiplier rareté** ;
  (b) **non-régression + wiring-safe** — Hollan/`Heal_TwistedScience` (routé, `heal_amt=None → saturation`) :
  port **ET** natif castent 1167 tgt=86 (MATCH ability+cible ; le nouveau chemin `heal_config`/
  `heal_amount_config` tourne live sans erreur).
- **RESTE (tâches créées)** : identification `"Heal" in name` INCOMPLÈTE — les heals Comparable BESPOKE
  in-pool (`BloodChalice`/Nicodemus, `MomentShackle`/Trajann, `SpiritLeech`) ne sont **pas routés** par
  `_heal_candidates` (nom sans "Heal") et ont chacun leur **playbook propre** (`BloodChalicePlaybook`
  deal-dmg+heal+extraPierce…) → à porter séparément (leur portage rendrait la cap `hpToHeal` **live-observable**
  via Nicodemus, in-pool). Repair `_repair_candidates` : même câblage `hpToHeal`→`hpToRepair` à faire + terme
  ARMOR=0.

### MAJ #82 (2026-07-09) — heals COMPARABLE BESPOKE (BloodChalice / MomentShackle / SpiritLeech)

Route les 3 heals Comparable BESPOKE que `_heal_candidates` ratait (nom sans "Heal" -> identification par
**ID**, pas substring). Chacun OVERRIDE le scoring générique (`ComparablePlaybook<T>.EvaluateInternal
@181408980` / `CalculateActionUtility @181406ee0`) par une utilité PROPRE. Poids `GetUtilityValue` résolus
OFFLINE depuis `BattleConfiguration.Utilities.Default.ActiveAbilities` (clés du dump `stringliteral.json`).

**BloodChalice (0x497=1175 ; bloodSanguinary/Nicodemus) — PORTÉ** (`bespoke.BloodChalicePlaybook`) :
- `EvaluateInternal @1811224c0` = override TOTAL (PAS de HealUtility) : util = `count(alliés NON-mécaniques
  ADJACENTS au caster, PV% < seuil) × W`. Self-cast AoE (cible = MainTile ; `GenerateAction(this,casterTile)`).
- seuil = `GetNumberConstant(0x4f)` = config `healthPct` = 50 ; PV% = `GetStat(Health, StatPart=1)` =
  `round(cur/max×100)`. W = `BloodChalice_AdjacentDamagedNonMechanicalFriend` = **50**. MIN_UTILITY=1
  (cctor @181122b10). `ShouldExecute @1811228b0` : `Σ(seuil − PV%)` sur amis non-méca > 0.

**MomentShackle (0x4a0=1184 ; custoTrajann/Trajann) — PORTÉ** (`bespoke.MomentShacklePlaybook`) :
- Util = HealUtility(SELF-heal) + `CalculateCasterPositionUtility`. Cible = SOI. Position-swept.
- Self-heal : `MakeHealPredictions @18114c7f0` -> `GetHealAmount = ConfigVar(0x20)` = **`hpToHeal[level]`**
  (MomentShackle config a `hpToHeal`) -> `PredictHeal` (`min(healAmount, missing_self)`, #79) -> HealUtility
  (POSITION-INDÉP). Position : `CalculateCasterPositionUtility @18114c6e0` = `count(ennemis ADJACENTS@T) × W`,
  W = `MomentShackle_AdjacentEnemy` = **25**. MIN_UTILITY=1 (cctor @18114c960).
- **Exerce la cap #79** (self-heal via ConfigVar(0x20)=hpToHeal) : magnitude live-consistante confirmée
  (Trajann rank-17 : `heal_amount_config("MomentShackle")` = 5983 = hpToHeal[L]×mult).

**SpiritLeech (0x450=1104 ; tyranNeurothrope/Neurothrope, Tyranids) — RE COMPLET, PORT EN ATTENTE** :
- PAS un self-cast : per-ENNEMI (attaque psychique range 3) + lifesteal. Régime `_best_attack`/registry.
- Dégât (`MakeDamagePredictions @18115d490` / `GetAttackDamage @181209dd0`) = `base(minDmg/maxDmg) +
  extraDmg SSI la cible est Suppressed(Pinned 0x429)` (`ConditionalAmount(NOT HasEffect, base, base+extra)`).
- Effet (`MakeEffectPredictions @18115d690`) = pose `Pinned(1065)` sauf si déjà présent (poids BC ~0/inerte).
- **Lifesteal** (`GetHealAmountForPrediction @181209fa0`) = `round_up(dégât PRÉDIT × hpToHealPct/100)`
  (`PercentageOf @180df8720` ; `hpToHealPct` = var 0x4b=75, [40..60], **PAS** rareté). Cibles heal
  (`GetHealTargets @18120a1e0`) = **self + alliés Tyranids ADJACENTS (1 hex)** ; N heal-events même montant.
- Combinaison (`CalculateActionUtility @181406ee0` -> `CalculateUtilityFromPredictions @181407890`) =
  `Σ DamageUtility + Σ(EffectUtility×prob) + Σ HealUtility` (position/custom base = 0). **GAP** : le
  `heal_amount_config` (#79) lit `hpToHeal`, PAS `hpToHealPct` -> SpiritLeech doit calculer explicitement
  `heal = PercentageOf(predicted_damage, hpToHealPct)`. À porter comme `SpiritLeechPlaybook(ComparablePlaybook)`
  (make_damage/effect/heal_predictions + override calculate_action_utility pour ajouter le lifesteal).

**Câblage** : `ComparableAbilityGenerator._bespoke_candidates` (identification par ID + `usable`) ->
`BESPOKE_SELFCAST[id].generate_candidates(ctx)`. **VALIDÉ LIVE (increment 1, session 44)** : port ROUTE
BloodChalice(1175)+MomentShackle(1184) sans crash ; candidats corrects (BloodChalice `None` sans allié
blessé ; MomentShackle util=25 dès 1 ennemi adjacent) ; port == natif (MATCH ability+cible) sur tous les
pas observés. NON encore confirmé : agreement quand la bespoke est l'action CHOISIE (nécessite un craft où
sa util bat l'attaque — enemies tanky + condition remplie).

### MAJ #83 (2026-07-09) — magnitude du régime COMPARABLE repair câblée (jumeau #79) + hook armure

Clôt le **gap wiring** repair (jumeau exact de #79) : `_repair_candidates` **saturait** `fill_hp = missing`
et `fill_armor = 0` au lieu de la vraie magnitude `RepairAmount` sur les DEUX stats. Fidélité restaurée.

- **Chaîne native (décompilée, gqfc5mff6c)** : `RepairAbility.RepairAmount @1811c4860` =
  `StatAmount(weapon@+0x160) × Max(WeaponHighestHits,1)` — **structure BIT-IDENTIQUE à `HealAbility.HealAmount`**.
  → `DamagePrediction.PredictRepair @181038280` : lit `GetStat(Health=5,Current)` + `GetStat(Armor=4,Current)`,
  applique le RepairModifier caster (`floor((floor(modAdd)+amt)×modMul)`, no-op ⇒ amt), caps group/boss, puis
  **DEUX** `FillUpStatComponent.MaxFillUp @180f9b790` : Health (→`fill_hp`) + **Armor** (→`fill_armor`), chacun
  `min(repairAmount, maximum_i − current_i)`. Utilité = `RepairedAmountUtility` (#37) : `fill_hp/(maxHP+1)×100
  + fill_armor/(maxArmor+1)×50`, **pas** de friendSign (répare ses propres machines).
- **Magnitude OFFLINE** = `hpToRepair[activeLevel]` × rareté, via `ability_var` (comme #79). **NUANCE vs heal**
  (piège) : le nom runtime de la réparation est l'enum **GÉNÉRIQUE** (`Repair`=28 / `Repair_GalvanicField`=1119),
  PAS la clé de config (contrairement au soin dont le nom accordé EST la clé). La magnitude vit sous une clé
  **PAR-UNITÉ** (`ReanimationBeam`, `FabricatorClawArray`, …). Résolue par
  `predict._repair_config_key(unit.activeAbilities)` = l'entrée `hpToRepair` de la liste `activeAbilities` du
  gameconfig qui n'est PAS une réparation NonComparable (`{NanoscarabRepairProtocols(1224),
  DefendTheDivineWork(1117)}`). Ex. necroReanimator `{ReanimationBeam, NanoscarabRepairProtocols}` →
  `ReanimationBeam` → `hpToRepair[17]=228` (×1.8 rareté = 410). `repair_amount_config(visualId, activeLvl,
  mult)` renvoie None si pas de réparation Comparable → saturation `fill=missing` (fallback documenté).
- **Hook ARMURE (nouveau)** : le terme armure exige l'armure courante/max, ABSENTE d'`observeBattle`. Ajouté :
  `match-state.ts` lit `ArmorComponent` (StatType.Armor=4, même layout FillUpStatComponent que Health :
  Maximum@0x14 / Remaining@0x18 ; distinct de `FixedArmorComponent=16` = mitigation) → `observeBattle.armor/
  armorMax`. **Validé live** : lecture correcte (renvoie 0 réel, pas le `null` défaut → le composant EST trouvé)
  — mais la POOL d'armure (StatType.Armor=4) est **0 au spawn** pour Necron/Marine/AdMech (mitigation =
  `fixedArmor`, PAS ce pool). Donc le terme armure = 0 fidèle (natif lit le même `GetStat(Armor=4)=0`) ; il ne
  contribue que si une unité a une pool d'armure non-nulle (non observé sur ces rosters).
- **Câblage** : `predict.repair_amount_config`/`_repair_config_key` + `_repair_candidates`
  (`predict_repair_effective(repair_amt, hp_cur, hp_max, arm_cur, arm_max)` → `fill_hp`/`fill_armor`).
- **Validation LIVE — IMPOSSIBLE (blocage dur, cause = MoW non unlocké)** : `_repair_candidates` (id 28/1119)
  n'a **qu'UN SEUL** porteur — **necroReanimator** (`ReanimationBeam`) ; les autres clés `hpToRepair`
  (FabricatorClawArray, RelentlessMarch, SelfRepairMechanism) sont des **PASSIFS** (ne déclenchent jamais
  `_repair_candidates`), et admecManipulus utilise le NonComparable `DefendTheDivineWork` (#77). Or
  **necroReanimator est un MACHINE OF WAR** (signature gameconfig identique à ultraDreadnought = MoW connu :
  `upgrades`+`upgradesStatIncrease`, PAS de champ `Movement` — les units régulières ont `Movement`) **que le
  compte n'a PAS unlocké** → absent du roster que la BC campagne (amorce) reflète → **UNSPAWNABLE**. Confirmé
  EXHAUSTIVEMENT : `--p-units` (blocklist `unspawnable_rank17.json`), `buildPatchedRunner aiUnits` côté AI
  (**silently dropped** : 11/12 spawnent, le slot Reanimator disparaît — normal, c'est un MoW pas une PredefinedUnit),
  format `:17`, variante NPC `necroNpcMoWReanimator` (droppée aussi), **pas dans le pool MoW spawnable** (8 MoW :
  adeptExorcist/astraOrdnanceBattery/blackForgefiend/deathCrawler/orksRukkatrukk/tauBroadside/tyranBiovore/
  ultraDreadnought — aucun Reanimator, car non possédé). ⇒ aucune unité spawnable n'exerce le chemin
  Comparable-repair. **Validation atteignable** : chaîne magnitude numériquement EXACTE offline (228 / ×1.8=410 /
  caps HP+Armor / non-repair→None) + hook armure live-prouvé + no-régression STRUCTURELLE (aucune unité pool n'a
  de repair Comparable → décisions pool inchangées, le gate `id∈{28,1119}` reste vide) + glue = jumeau
  ligne-à-ligne de `_heal_candidates` (#79). **RÉSIDU ACTIONNABLE** : si le compte **unlocke le MoW Reanimator**,
  il entre dans le pool MoW → spawnable via `rl_duel build --p-mow/--a-mow necroReanimator` (les MoW SONT
  AI-joués, cf. mémoire « MoW deploy gate ») → la décision-agreement live de `_repair_candidates` devient
  testable (craft : allié adjacent blessé + MoW Reanimator).
- **CORRECTION (val #77) — un carrier Comparable-repair EST in-pool** : `admecManipulus`/Actus (IN-POOL) porte
  `Repair_GalvanicField(1119)` GRANTED par son passif `GalvanicField` (id 1119 ∈ `_COMPARABLE_REPAIR_IDS`). Ma
  recension « aucun porteur Comparable-repair spawnable » ne regardait que `activeAbilities` -> a raté les
  repairs GRANTED-par-passif. ⇒ `_repair_candidates` (id 1119) EST exercé live par admecManipulus (vu step 14/17
  seed-909 : port == natif). Gap observé (step 8 seed-202) : port SOUS-évalue le repair 1119 (razor-thin 0.25,
  attaque 72.85 vs repair 72.59) → tâche **#85**. (Le blocage necroReanimator/MoW reste vrai pour SA magnitude
  `hpToRepair` propre, mais la décision-agreement Comparable-repair N'EST PLUS bloquée.)

### MAJ #77 (2026-07-10) — DefendTheDivineWork : terme +0.5 combat-readiness porté + LIVE-validé

Clôt #77. `DefendTheDivineWorkPlaybook.EvaluateNonComparable @18112b9b0` (NonComparable, id 1117 ; admecManipulus/
Actus) : la boucle sur HealTargets (self + amis adjacents) ajoute PAR CIBLE `(1 - RemainingPercentage_health)`
+ `Fix64.FromIntFraction(1,2)=0.5` SSI `IBattleQuery.HasValidTargets(cible, GetUnitPosition(cible),
GetNormalAttackType(cible))` (slot 0x40 d'`IBattleQuery` → `BattleQuery$$HasValidTargets`, qui delegue a `AttackQuery$$HasValidTargets @181057540`). Gate MIN_UTILITY = 0.9
(cctor @18112c070). Le +0.5 = « la cible réparée peut-elle attaquer un ennemi DEPUIS SA POSITION FIXE » (combat-
readiness). Le port l'OMETTAIT (borne inf, #37).

- **HasValidTargets OFFLINE** = `abilityTargets(cible, GetNormalAttackType(cible))` → `usable`
  (CanCurrentlyBeUsed) ET `fromHereCount > 0` (`fromHere` = `AttackQuery.GetValidTargets(unit, pos_FIXE,
  ability)`, DÉJÀ exposé par le RPC = cibles légales SANS bouger). La note tâche « couche targeting absente
  offline » était **PÉRIMÉE** (le flag `fromHere` existe). POSITION-INDÉP du sweep du caster → calculé 1x par
  cible via `noncomparable._has_valid_targets(ctx, unit_id)`.
- **Câblage** : `DefendTheDivineWorkPlaybook.generate_candidates` = Σ `[(1-hp%) + 0.5×readiness]` sur {self +
  adjacents} (readiness par cible), gate 0.9, sweep origine-first.
- **VALIDÉ LIVE (admecManipulus IN-POOL, seed 909, engine_validate runner)** : step 12 — natif ET port castent
  `1117` tgt=26 à pos (1,4) [EXACT + MATCH]. util = **1.079** (selfReady=0.5). Le +0.5 est **LOAD-BEARING** :
  sans lui, util ≤ 1.079 − 0.5 = 0.579 < 0.9 → l'ability ne passerait PAS le gate → le port tomberait sur une
  Comparable (attaque/repair) = MISS. Avec, MATCH exact. No-régression (10/12 casts match ; les 2 misses =
  sélection de cible d'attaque d'ennemis Necron, hors #77).

### MAJ #85 (2026-07-10) — `Repair_GalvanicField(1119)` : playbook BESPOKE distinct du repair générique

Clôt #85. **Prémisse RÉFUTÉE puis vrai gap FORMULE corrigé.** La tâche disait « step 8 seed-202 : natif cast
`1119`, port cast attaque → MISS ». **Re-vérification live** : à seed-202 le natif **ne caste JAMAIS `1119`**
en 14 pas ; à seed-909 le port **matchait déjà** les 2 casts de `1119` (steps 14/17). Le « MISS » (et le
« razor-thin 0.25 » noté en MAJ #83) **ne reproduit pas** — artefact d'un résumé /compact. MAIS un vrai gap de
**fidélité de formule** existait : le port routait `1119` dans le repair GÉNÉRIQUE (`_repair_candidates`, saturation
`fill=missing` + pas de terme bespoke), décision-juste par chance mais util-number faux.

- **RE (ghidra gqfc5mff6c) — `Repair_GalvanicFieldPlaybook @181155b80`** (`ComparablePlaybook<0x45f=1119>`,
  admecManipulus/**codename interne « Loki »**, GRANTED par le passif `GalvanicField`). C'est un playbook
  **BESPOKE**, PAS le `RepairPlaybook` générique (id 28). Overrides : `MakeRepairPredictions @1811557b0`,
  `CalculateCustomUtility @181155520`, `ShouldExecute @181155b20`.
- **MAGNITUDE `GetOverrideAttackDamageAmount @181200080` = `PercentageOfAttackCappedAtMax @180df8530`** :
  `M = min(round(cible.Attack_INITIALE × dmgPct/100), maxDmg)`. **PIÈGES corrigés par le re-expert** : (a) c'est
  l'Attack de la **CIBLE réparée** (`DSLFactory.ActiveTarget@0x180`), PAS du caster — le tooltip « 100% of *its
  own* Damage » ; (b) `StatType=0=Attack`, `StatPart=3=Initial` (le `3` du décompilé est un StatPart, pas un
  StatType — ne PAS lire Defense) ; (c) `ConfigVar 0xd=maxDmg=CAP`, `0x4a=dmgPct=PERCENT` (GalvanicField vars, au
  niveau **PASSIF du caster** ; `maxDmg` seul rarity-scaled). **PAS `hpToRepair`.** (dmgPct[L50]=100 → `M =
  min(Attack_cible, maxDmg)`.)
- **UTILITÉ `CalculateActionUtility @181406ee0` (chemin repair) = SOMME ADDITIVE** (lu dans le décompilé, slots
  virtuels 0x328=ShouldExecute / 0x338=CustomUtility / 0x348=CasterPositionUtility) : (1) `RepairedAmountUtility`
  générique (`fill = min(M, manquant)` sur Health+Armor, `repair_utility`, cf. #83) **+** (2) `CalculateCustomUtility`
  bespoke = `M/(cible.maxHP+1) × 50`, **GATÉ** par `HasValidTargets(cible)` (même prédicat combat-readiness que
  #77, slot 0x40 d'`IBattleQuery` → `BattleQuery$$HasValidTargets` → `AttackQuery$$HasValidTargets` → 0 si la cible ne peut pas attaquer depuis sa position) **+**
  termes de position/tuile (framework, communs à l'attaque).
- **Ciblage** : ami + Mechanical. Le re-expert a lu une garde `target != caster` (pas de self), MAIS le
  **self-repair est OBSERVÉ LIVE** (seed-909 step 14, `1119` tgt=84=caster). → le port s'appuie sur `abilityTargets`
  (énumération live = vérité), PAS sur une règle self/ally codée en dur.
- **Câblage** : `1119` RETIRÉ de `_COMPARABLE_REPAIR_IDS` (générique = `{28}` seul) → nouvelle méthode dédiée
  `_repair_galvanic_candidates` (homonyme `Repair_GalvanicFieldPlaybook`) : `M` via
  `ctx.scene.ctx_by_id[cible].get_stat(Attack, Initial)` + `ability_var(GalvanicField, maxDmg/dmgPct, passiveLvl,
  mult)` ; pred = `repair_utility(fill) + (HasValidTargets ? M/(maxHP+1)×50 : 0)`.
- **VALIDÉ LIVE (seed 909, engine_validate)** : step 14 `1119` tgt=**84 (SELF)** + step 17 tgt=**86 (allié)** =
  **MATCH** (les deux). Chiffres : cible Attack=2512, maxDmg=5983 → **M=2512** ; step-14 self `repaired=26.34 +
  custom=0` (HasValidTargets(self) false à ce pas) `= 26.34` ; allié `26.34 + 13.17 = 39.51`. La correction fait
  passer l'util self de 38.27 (saturation) → 26.34 (fidèle) **sans changer la décision** (repair > attaque). Overall
  **10/12** casts match = INCHANGÉ vs avant-fix (2 misses = cibles d'attaque Necron, hors #85). Test de garde
  `test_playbook_live.py` = **3 passed** (no-régression autres rosters).

## Exemple bespoke — `Loki.SaviorProtocolsPlaybook` (base `TriggeredAbilityPlaybook<T>`)

ctor pose l'ability id **`0x460` (1120)**. Deux scorers :

- **ATTACK** (`d__5.MoveNext` @18118ff00) : gate `HasEffect(target, 0x462 (1122) marker)` →
  `+weight[KEY_A]`. 1 yield.
- **MOVEMENT** (`d__4.MoveNext` @181195b10) : énumère les **alliés près de la tuile caster**
  (query `0x79`) ; par candidat valide (`TargetIsValidTrigger` : `AreFriends` + `HasFaction(9)` +
  `NOT casterHasAbility(1120)` + `target≠self`) → `+weight[KEY_M1]`, et `+weight[KEY_M2]` si le
  caster est le parent/owner du candidat. Somme sur les candidats → 1 yield. `FilterMovementTiles`
  @181188150 élague (melee only ; ranged skip) aux seules tuiles d'où le trigger peut partir
  (adjacence à un allié protégeable).

## Leaf NonComparable (summon) + sélection bucket-tree

- **`1166 = AberrantHypermorph` = SUMMON, NonComparable** (vrai leaf NonComparable du plan ; les
  `1167 = Heal_TwistedScience` et `1171 = DakkaDakkaDakka` sont des HEAL/attaque **Comparable**).
- `AberrantHypermorphPlaybook.GetUtility(tile)` / `EvaluateNonComparable` = **utilité d'une tuile de
  spawn = NOMBRE d'ennemis ADJACENTS** (hex-dist 1) à la tuile (`FUN_180007c20(0x7e)` →
  get-adjacent-enemies → `.Count` → `Fix64`). L'IA invoque là où le summon engage le plus d'ennemis.
  Candidats = `GetEligibleTargetsSelectable` (= les tuiles `abilityTargets`). Porté dans
  `engine/leaves.py` (registre `abilityType → scoreur`, extensible).
- **Sélection (bucket-tree)** : `Bucket.ChooseAction` retourne l'action **DÉFAUT** du nœud (field
  `0x20`) si elle passe la gate de faisabilité `FUN_18004cc80`, sinon descend dans les enfants
  (`SortedList` field `0x28`) **ordonnés par utilité**, et renvoie la **première faisable**. Le
  `UnitAction` = (position, target, **abilityType**) — pas de priorité dedans. → l'ordre
  **inter-CATÉGORIE** (summon vs move vs attack) vient de l'assemblage du bucket racine + des clés de
  catégorie (utilités non comparables : summon ~0-6 vs kill ~100 vs move ~100s). Détail amont :
  [`architecture.md`](architecture.md).

## POIDS de playbook = EXTRACTIBLES OFFLINE (`playbook_keys.py`)

Correction d'une claim erronée antérieure (« capture live requise ») : les poids sont **statiques**.

Pipeline : décompile → `DAT_<VA>` passé à `GetUtilityValue` → `RVA = VA − 0x180000000` →
`data/dumps/<hash>/stringliteral.json` → clé string → valeur dans `Utilities.Default.<catégorie>`.

Vérifié sur **SaviorProtocols** :

| VA literal | clé | valeur | catégorie |
|---|---|---|---|
| `0x18325a560` | `SAVIORPROTOCOLS_MarkedTarget` | 60 | `TriggeredAbilities` |
| `0x18325a2e0` | `SAVIORPROTOCOLS_AdjacentTauFriend` | 20 | `TriggeredAbilities` |
| `0x18325a420` | `SAVIORPROTOCOLS_AdjacentTauParent` | 30 | `TriggeredAbilities` |

Les poids playbook vivent dans `Utilities.Default.TriggeredAbilities` (owner, ~107 clés) /
`TriggeredAbilitiesNonOwner` (~24) / `UnitSpecificBehaviours` (~3) / `ActiveAbilities` (~18), sous des
clés `<ABILITY>_<Condition>` (**PAS** sous le nom de l'ability). Plus généralement, **tout `DAT_`
métadonnée** (string/type/méthode/champ) est résoluble via `stringliteral.json` + `script.json`
(`ScriptMetadata`/`ScriptMethod`) → RE EXACTE sans inférence ; seuls les globals mutables runtime
(gardes cctor `init-once`) n'ont pas de valeur statique.

## État du portage

- **Communs** : `engine/playbook/common.py` (NormalAttack / Heal / Repair / Default +
  `get_playbook_or_default`), base étendue (`should_execute` / `custom_utility`). **Validé OFFLINE
  (19/19)** : registry 17/18/28/1120, fallback, gates, custom +1, Default 1.5.
- **Leaf summon** `1166` : porté + correct (wiring `argmax adjacent-enemy` validé) mais **non
  exercé** seed 777 (ennemis non en mêlée → 0 adjacent → utilité 0, cohérent avec le natif qui ne
  summon pas non plus).
- **Bespoke** (`Loki.*`, `SaviorProtocols`, …) : portage **incrémental agreement-driven** par-dessus
  le cœur générique.

## BLOQUÉ / RESTE

- **Join clé ↔ classe des 351 `b__31_N`** : à finir en décompilant chaque lambda (mécanique, ~1 ctor
  chacun ; l'ordre de registration == ordre des lambdas par map). Indispensable au registry complet.
- **Bespoke = longue traîne** : ~351 abilities portables une à une (gate + énumération + clés) ;
  commencer par les abilities réellement présentes dans les batailles ciblées.
- **Prédiction soin/repair** : `aiPredict` dégât-only → montants Heal/Repair (et donc le scoring de
  `HealPlaybook`/`RepairPlaybook`, et le heal `1167` du seed 777) restent **bloqués**. C'est le
  **SEUL vrai prérequis live restant** pour le port complet (cf. [`prediction.md`](prediction.md)).
- **Bucket-tree par-catégorie** : la clé d'ordre inter-type (summon/heal/move/attack) n'est **pas
  encore RE** ; suivi dans [`architecture.md`](architecture.md).

## MAJ #84 (2026-07-10) — SpiritLeech lifesteal : le vrai gap = `OverkillUnit` MORT (pas le lifesteal)

**Question de la tâche** : « pourquoi le natif GARDE la normale malgré un self blessé + lifesteal ? »
**Réponse RE** (décompilé = vérité) : `CalculateActionUtility @181406ee0` est ADDITIF —
`DamageDealt + KillUnit + OverkillUnit + Σheal + effet`. Sur une cible **bas-PV que les deux tuent**,
`DamageDealt`+`DefinitelyKill` sont ÉGAUX ; le SEUL terme dégât qui diffère = **`OverkillUnit`** : la
normale (gros marteau) sur-tue davantage → `DefinitelyOverkill(+40)` vs SpiritLeech (psy faible)
`PossibleOverkill(+15)`/0 → +25 qui dépasse le lifesteal (~2.81) → le natif garde la normale.

**Bug latent trouvé** : le port `OverkillUnitUtility` lisait `AccurateHealthDamage` **CAPÉ à HP**
(`min(dmg,hp) > hp` = TOUJOURS faux) → util **globalement INERTE** pour TOUTE attaque. Le natif lit
`WillBeOverkill @18102ba40`/`MightBeOverkill` = `IsOverkill @181032db0` sur le dégât **BRUT** (over-shoot
`(dmg−hp)/hp×100 >= overkillDmgPctOfHealth(100)` ⇒ `dmg >= 2×hp`). **Fix** : `DamagePredictionResult`
porte désormais `raw_health_damage` (@0x24/@0x28, NON capé) distinct de `accurate_health_damage` (@0x58,
capé) ; `OverkillUnit` utilise le brut via `is_overkill` (over-shoot déjà porté pour le cap Resilient).

**Lifesteal SpiritLeech porté fidèlement** (`SpiritLeechPlaybook.MakeHealPredictions @18115d7a0`) :
`lifesteal = ceil(dégât × hpToHealPct/100)` (var 0x4b ∈ [40..60], PAS rarity) sur `GetHealTargets
@18120a1e0` = **self + Tyranids adjacents** → `Σ CalculateUtilityFromHealEvent`. Sommé au dégât dans
`_best_attack` (id 1104). i2 confirme : « heals itself and friendly Tyranids adjacent to it for 60% of
the total damage dealt ».

**Validé LIVE** (Neuro BLESSÉ à 5805/8533 via **BloodChalice** de Nicodemus même-team — « set to 50%
Health » — sans contact ennemi) : vs orksNob (10040 PV, NON tuable → pas de kill/overkill),
`lifestealU=18.23` fait passer SpiritLeech (44.0) devant la normale (26.6) → **port ET natif castent
SpiritLeech = MATCH**. Sans le lifesteal, SpiritLeech=25.8 < 26.6 → miss. Les deux régimes (cible bas-PV
→ overkill garde la normale ; cible haute-PV + self blessé → lifesteal prend SpiritLeech) collent au
natif. **Non-régression** : miss-sets IDENTIQUES vs baseline sur seeds 777/31337/909/202.

**Harnais durci — découverte Actif/Passif** (`gameconfig.py`) : `unit(uid)["abilities"]` est **VIDE/None**
(champ legacy) — les vrais actifs/passifs sont `activeAbilities`/`passiveAbilities` (des NOMS). Ajout de
`ability_id(name)`/`ability_name(id)` (mirroir de l'enum `ActiveAbilityType` depuis
`frida/hooks/data/ability-names.ts`) + `unit_abilities(uid)` → `{active/passive: [{name, id}]}`, et
`card_unit`/`--unit` affiche `[active id=1104]`. **Fin du hardcode d'id** (piège répété #82/#84/#85).

**Gaps SÉPARÉS révélés** (ni lifesteal ni overkill — tâches #86/#87) : (a) SpiritLeech SOUS-prédit le
dégât (3110 vs natif 3221) — passif **Neuroparasite** (+1237 psy/niveau) non porté ; (b) tie-break
normale-vs-spéciale (natif garde la spéciale 1104 au tie sur seed 202 step-11, la normale sur seed 777
step-9) ; (c) le moteur ne score AUCUNE attaque du Neuro dans certains runners (`attack_cands=[]`).

## MAJ #116 (2026-07-12) — HammerOfWrath `+5·CanAddUnit` : le terme de déplacement (slot-78 résolu)

`HammerOfWrathPlaybook.EvaluateNonComparable @181141680` (id 1153, bloodIntercessor) ajoute, après
`Σ CalcUtilFromDamageEvent(primary+secondary)` + `100·HasTrait(Overwatch)`, un terme
**`+5 · Σ_{n ∈ GetAdjacentTiles(cible)} CanAddUnit(n)`** — OMIS en v1 (#114). Porté ici.

**RE — résolution du sélecteur (re-expert, décompilé = vérité).** ⚠ **Les numéros de slot ci-dessous ont
été RE-DÉRIVÉS sur `rnca9r7q6c` le 2026-08-10 (#433-r3-r3) : ils avaient GLISSÉ D'UN CRAN depuis
`gqfc5mff6c`, où cette section les avait écrits (`0x4e`).** Le bloc de queue fait
`tiles = <invocateur d'interface>(0x4f, <IBattleQuery>, query = playbook+0x28, target = local_508, 1, 1, 1)`
= **slot `0x4f` = 79 de l'interface `IBattleQuery`** = **`IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles`**
(surcharge à 4 paramètres — ring-1 hex, voisins `boardGraph.neighbours` via `IterateAdjacentTiles` — la
MÊME famille dont #45 a porté la porte `|Δelev|<2`).
- **DEUX sources concordantes, aucune devinette.** (1) L'entrée VERSIONNÉE
  `data/symbols/rnca9r7q6c/metadata/interface_slots.tsv` (champ `slot` d'`Il2CppMethodDefinition`) :
  `IBattleQuery 78 GetMinimumTiles180BehindFromTile/2 · 79 GetAdjacentTiles/4 · 80 IterateAdjacentTiles/4 ·
  81 GetAdjacentTiles/4 · 82-83 GetFreeAdjacentTiles/1 · 84 GetTilesBehind/5`. (2) Les lambdas du décorateur
  `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery` — `u003Cu003Ec__DisplayClass98_0$$u003CGetMinimumTiles180BehindFromTileu003Eb__0`,
  `…DisplayClass99_0$$u003CGetAdjacentTilesu003Eb__0`, `…DisplayClass100_0$$u003CIterateAdjacentTilesu003Eb__0`,
  `…DisplayClass101_0$$u003CGetAdjacentTilesu003Eb__0`, `…DisplayClass104_0$$u003CGetTilesBehindu003Eb__0` :
  même ORDRE, décalage uniforme (DisplayClass N ↔ slot N−20 sur cette plage). Le NUMÉRO du DisplayClass
  n'est PAS le slot — c'est l'ordre qui apparie.
- **Corroboration au call-site** : `IdunBattle.Core.Services.MovementQuery$$IsAdjacent`, relu sur
  `rnca9r7q6c`, appelle `<invocateur>(0x4f, <IBattleQuery>, this+0x30, unitTile1, 0, 1, 1)` puis
  `Contains(ring1, unitTile2)` — i.e. « les tuiles adjacentes de `unit`, `tile` en fait-il partie ? ».
- **`GetTilesBehind` RÉFUTÉ** comme slot de ce call-site : il prend **5** paramètres (deux unités →
  `CubeCoordinate.DirectionTo(A,B)`), or l'appel Hammer ne passe qu'UNE unité (`local_508`) + bools. C'est
  le slot **`0x54` = 84**, pas `0x4f`.

**RE — prédicat de tuile libre.** ⚠ Le nom a lui aussi GLISSÉ : sur `rnca9r7q6c` le call-site invoque
`IdunBattle.Entities.TileExtensions$$IsFreeTile(tile, playbook+0x20, 1, 0, false)` — il n'existe AUCUN
`IdunBattle.Entities.TileExtensions$$CanAddUnit` dans ce build (le nom `CanAddUnit` n'y vit plus que côté
DSL : `IdunBattleLogic.Entities.DSLSelectors$$CanAddUnit`, `IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select`,
`IdunBattleLogic.Entities.DSLTriggers$$IsCanAddUnit`, plus `TileExtensions$$CanAddUnitFromAbility`).
Le prédicat (args du call : `arg3=1, arg4=0, arg5=false`) se
réduit à : tuile de board réelle **placeable** (walkable, non-wall) ET **VIDE** (`TileContentComponent
.IsEmpty @180fa9ed0`). `arg2 = playbook+0x20` = l'aiPlayer (qui place). Sens du terme : **biais du natif
vers les cibles entourées d'ESPACE LIBRE** (place pour le knock-back de la charge). Le terme dépend de la
CIBLE (pas de la tuile de charge) → il influe l'**argmax de cible** (pas cosmétique).

**Port** (homonymes natifs + VA citées) :
- `engine/battle_query.py` : `can_add_unit(pos, walkable_by_pos, occupied)` (=
  `IdunBattle.Entities.TileExtensions$$IsFreeTile`) +
  `adjacent_addable_count(tile, neigh_by_pos, walkable_by_pos, occupied, elev)` (= `GetAdjacentTiles`
  slot **`0x4f`** filtré — `0x4e` sur `gqfc5mff6c`, cf. l'avertissement ci-dessus —, porte `|Δelev|<2`
  réutilisée de #45).
- `engine/playbook/noncomparable/hammer_of_wrath.py` : `HammerOfWrathPlaybook._displacement_bonus` = `5 ·
  adjacent_addable_count(cible.tile)`, wiré dans `evaluate_non_comparable`. Occupation LIVE = `epos ∪ fpos
  ∪ origine` (FRAÎCHE — PAS le `occupantUnitId` du boardGraph caché = périmé).
- `engine/ai/context.py` + `action_generators.py` : plumbing `walkable_by_pos` (boardGraph
  `walkable`/`IsWalkableTile`, seule donnée offline manquante ; `boardGraph` l'émet déjà — **aucun RPC/
  reinject requis**).

**Validation** : offline unit-tests VERTS (porte élévation, walkable, occupation, `disp=5×count`, cible
introuvable→0). **Live non-régression** (seed 114010, bloodIntercessor Hammer-carrier, 26 pas) : Gauntlets
step-9 `(1000,tgt=118)` toujours **MATCH** (#117 intact), miss-set = gap summon-attack préexistant (grots
u114/u118/u123), PAS ce changement.

**Validator FEU VERT COMMIT** (adversarial, worktree sur `5ac53ca`) — le terme `+5` **EXERCÉ LIVE** via
positions drivées (le RE l'avait laissé non exercé) : runner 85 (4 candidats Hammer, `disp` par cible
78=10/82=25/84=30/86=10, compté voisin-par-voisin vs board) → natif `u88→Hammer(1153)→target=84`, engine
`target=84` **MATCH ability+cible** ; runner 87 (2 orksNob, disp 80=20/78=15) → natif+engine `target=80`
**MATCH**. Occupation `epos∪fpos∪origine` == toutes unités vivantes (0 manquant/extra). **Over-count
élévation RÉFUTÉ** : `boardGraph.neighbours` natif pré-exclut déjà les arêtes dElev≥2 (20 confirmées sur pvp)
→ le port itère cette liste → ni sur- ni sous-compte (la porte `|Δelev|<2` re-appliquée = redondance sûre).
Non-régression : diff confinée à `HammerOfWrathPlaybook` + helpers additifs ; autres NC intacts.

**FLAGS / limitations** (dans `can_add_unit`) : (a) co-location trait `0x1b` (arg3=1 admet un occupant
pass-through) → tuile occupée = fail (borne INF, corner négligeable) ; (b) tuiles walkable-mais-réservées
(`tile[4]+0x40`/`+0x2c` runtime) non modélisées si `walkable` ne les folds pas (HYPOTHÈSE : `walkable==
false` couvre `+0x40`) ; (c) **IsTemporary** de l'itérateur natif `GetAdjacentTiles` : **RÉSOLU #118 —
non-issue** (voir MAJ #118 ci-dessous). [L'ancien flag « over-count élévation » est RÉFUTÉ par le
validator, cf. ci-dessus.]

### MAJ #118 (2026-07-13, CORRIGÉE #148) — mapping des 3 bools de `GetAdjacentTiles` (via les CTORs)

Suivi de #116 flag (c). Question : le filtre `IsTemporary` exclut-il les tuiles temporaires ACTIVES du
`+5·CanAddUnit` (auquel cas le port les sur-compterait) ? **RE (décompilé = vérité, build gqfc5mff6c).**

> ⚠️ **CORRECTION #148** : la 1re passe (lue sur le seul `MoveNext`) avait le mapping À L'ENVERS
> (param3=allowTemporary / param5=requireEmptyOrSteppable). Les **CTORs** des itérateurs le tranchent :
> `BattleQuery.IterateAdjacentTiles @181070df0` range param3/4/5 en ASCENDANT (`+0x41/+0x43/+0x45`) mais
> `TileQuery.IterateAdjacentTiles @1810acae0` les range en **INVERSE** (param3→`+0x45`, param5→`+0x41`).
> `d__8.MoveNext @1810acef0` lit ascendant = (IsTemporary, IsWalkable, IsEmptyOrSteppable). Net :

- **Mapping RÉEL** : **param3 = requireEmptyOrSteppable** (occupance), **param4 = requireWalkable** (murs),
  **param5 = allowTemporary** (polarité inversée : `(field != 0) || !IsTemporary` → 1=inclure).
- Le call Hammer `HammerOfWrathPlaybook.EvaluateNonComparable @181141680` passe `(1,1,1)` = requiert
  emptyOrSteppable + requiert walkable + **INCLUT temporaires** (param5=1).
- Le call jumeau `MovementQuery.IsAdjacent` passe `(0,1,1)` = param3=0 (inclut occupées) + param4=1
  (walkable) + param5=1 (inclut temporaires) → occupance-indépendant, adapté à un test d'adjacence.

**Conclusion #118 : NO-OP** (inchangée). Le natif INCLUT les tuiles temporaires au site Hammer (param5=1),
comme le port (`can_add_unit` ne teste pas IsTemporary) → aucune exclusion à ajouter. `requireWalkable=1`
/ `requireEmptyOrSteppable=1` subsumés par `CanAddUnit` (walkable + empty ; empty ⊂ emptyOrSteppable →
intersection = {walkable, empty} = ce que le port compte). **Ce mapping corrigé est ce qui a débloqué #148**
(la capture `boardGraph` passait `(1,1,1)` = requireEmptyOrSteppable=1 → excluait les tuiles OCCUPÉES ;
le complet = `(0,0,1)`). Port `can_add_unit`/`adjacent_addable_count` inchangé, docstrings corrigées.
