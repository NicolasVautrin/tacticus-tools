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

**Implication** : le cœur générique (`CalculateActionUtility`) déjà construit EST le moteur des
abilities COMMUNES (= la grande majorité des actions). Le dégât marche (`damage.py`) ; soin/repair ne
manquent que la prédiction. Les playbooks **bespoke** sont des **ajouts incrémentaux à clés-strings**
par-dessus ce cœur.

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
