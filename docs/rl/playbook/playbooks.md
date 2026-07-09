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
  → **CombatRestoratives PORTÉ** dans `engine/playbook/noncomparable.py` (`CombatRestorativesPlaybook`,
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
- **Fix** (`engine/playbook/noncomparable.py`) : `_sweep_origin_first(ctx) = [origine] + moves`, appliqué
  aux 4 self-cast (CombatRestoratives 1002, RevitalizingMalignancy 1037, DefendTheDivineWork 1117,
  RitesOfRestoration 1039) + `bq.is_adjacent` partagé. **Validé LIVE** (deathRotbone/ultraApothecary/
  admecManipulus self + →destroyer : tous in-place, MATCH target+ability natif).
- **NovaBoost/NovaShield RÉCONCILIÉS (#80)** — par CLASSE de cible (le tie-break dépend de
  `HasValidTargets(0x3f)` par-tuile-de-move ; sa fonction exacte est derrière un dispatch d'interface
  `@180028910` = trampoline, NON lisible statiquement → résolution par **cohérence générateur + la classe
  confirmée**, PAS par agreement arène-inagréable) :
  - **NovaBoost = SELF-target** (util=1, cible=self) → MÊME classe que les self-cast heals → la self-cible
    est position-indépendante → le générateur gate les tuiles de move → **RESTE EN PLACE** au tie (comme
    deathRotbone #76). **FIX : `_sweep_origin_first`** (origine d'abord → `to=None`).
  - **NovaShield = TILE-target** (marque un centre, cible kind=tile) → classe DIFFÉRENTE : les hex à marquer
    existent depuis la plupart des positions → tuiles de move NON gatées → au tie **BOUGE** (keep-first) ; +
    utilité position-dépendante (100·ennemis) → argmax non-trivial. **On GARDE origine-LAST.** *UNVERIFIED*
    (arène-inagréable ; la classe tile-target n'a pas de confirmation live comme la self-target) → ne pas
    asserter fermement.

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
