# case-1203 — `OnToxicDamageAbility` : la contamination on-hit du profil `Toxic`

**Verdict du critère.** *« Quand un coup de profil `Toxic` touche, le moteur offline déclenche-t-il le
même canal que le natif — et si oui, avec quelle magnitude ? »* → **OUI, désormais**, avec une
**chance de 25 %** tirée **une seule fois par série de coups** (donc une fois par cible attaquée).
Avant ce port, le canal était **silencieusement muet** : aucun handler pour 1203, aucune contamination
posée, et **un tirage `NextBool` de retard** dans le flux `state.rng` dès la deuxième cible d'une
attaque `Toxic`.

Build de référence : `gqfc5mff6c`. Session Frida 3.

---

## 1. RE — ce qui est IDENTIQUE à `OnFire`, ce qui ne l'est PAS

```
IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateTrigger
    On(0x10, 1) & DamageProfileHasTrait(1 = OnFire)  & !TriggeringEffectIs(5)
IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateBehaviour
    AddEffect(5 = Fire, AbilityStateReference, Tiles(target@0x178))                    # INCONDITIONNEL

IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateTrigger
    On(0x10, 1) & DamageProfileHasTrait(4 = OnToxic) & !TriggeringEffectIs(0x4dc)
IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateBehaviour
    If( IsFirstHitInSeries() & Maybe( ConfigConst(0x4b3, Self@0x148, 0x2a = chance) ),
        AddEffect(0x4dc = 1244 Contaminated, AbilityStateReference, Tiles(target@0x178)) )
```

**Identique** — le vecteur d'événement (`On(0x10)`, émis par
`IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` après **chaque coup**, donc pour les
DEUX familles d'attaque), la forme du gate de profil, la feuille de pose (`AddEffect` TILE-DOMAIN
`Tiles(Target())` = la MainTile occupée de la cible), la surcharge d'`AddEffect` (5 arguments), la
durée (arg `0` → `DefaultAmountOfRounds(0x4dc) = 2 rounds`), et l'anti-boucle
`!TriggeringEffectIs(<le type posé>)`.

**Différent** — deux points, et ils commandent tout le port :

1. **Le behaviour est un `If(cond, then)`** (`IdunBattle.Entities.Behaviours.IfBehaviour$$Execute` :
   cond `+0x50`, then `+0x58`, else `+0x60` **absent** ici → résultat vide si la condition tombe), là où
   `OnFire` pose l'effet sans condition.
2. **La condition est un ET COURT-CIRCUITANT de deux prédicats** :
   `IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd` alloue un `MultipleAbilityTrigger` dont le
   `$$ShouldTrigger` n'évalue le droit **que si le gauche est vrai**.
   - `IsFirstHitInSeries()` → `IdunBattle.Entities.Triggers.IsFirstHitInSeriesTrigger$$ShouldTrigger` =
     `entities.IsFirstHit.HasValue ? .Value : false`, où
     `IdunBattle.Entities.Abilities.AbilityEntities$$get_IsFirstHit` lit le `DamageAppliedResult` du coup
     courant (champ `+0x110`) et rend
     `IdunBattle.Core.Services.DamageAppliedResult$$get_IsFirstHit` = `hitIndex == 0`.
   - `Maybe(chance)` — **surcharge à UN argument**, qui construit
     `IdunBattle.Entities.Triggers.MaybeTrigger` (un PRÉDICAT), à ne pas confondre avec le nœud EFFET
     homonyme `MaybeBehaviour` (surcharges à 3/4 args). Son `$$ShouldTrigger` calcule la formule puis
     `DisallowablePseudoRNG.NextBool(rng@+0x18, chance)` — **le PRNG est un champ de l'instance**, posé
     par la factory, pas une entrée du contexte.

**Conséquence RNG, qui EST le gap mesuré** : le natif exécute le behaviour à chaque coup, mais le
court-circuit fait que **le `Maybe` n'est évalué qu'au coup d'index 0** → **exactement un `NextBool` par
série de coups**, c.-à-d. **une fois par cible attaquée**. Un port qui ne tire pas prend un tirage de
retard sur toute la suite du flux ; un port qui tirerait par coup en prendrait N-1 d'avance.

### Magnitude — d'où vient `chance = 25`

`ConfigConst(0x4b3, <config>, 0x2a)` → `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate`, branche
`constantKey@+0x38` → `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant`. `0x4b3` = 1203
(l'ability elle-même) ; `0x2a` = `AbilityConstantType.chance` (calibré par `FireOfAbsolution`, dont
`GetNumberConstant(0x2a)` correspond à `abilities.FireOfAbsolution.constants.chance = "30"`).

La config de l'ability 1203 **n'est pas** dans `units.abilities` du gameconfig client (aucune entrée
`OnToxicDamage*`) : elle vit dans la **BattleConfiguration**, sous
`Abilities.PassiveAbilities.OnToxicDamageAbility.Constants.chance = "25"` (lu dans la BC capturée
`data/seed-bc.json`). Le gameconfig, lui, porte l'unique clé numérique correspondante :
`globalValues.toxicDamageContaminationChance = 25`. Le port lit **cette clé** ; un test ANCRE l'égalité
des deux, pour qu'une divergence de build casse un test au lieu de passer inaperçue.

### Source de l'effet posé = la TUILE, pas le caster

La surcharge `AddEffect` appelée prend 5 arguments et construit
`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor(this, X, effectType, stateRef, SOURCE = 0,
TARGETS, options)` (mapping des slots lu au ctor : `+0x50` effectType, `+0x58` stateRef, `+0x60`
sélecteur SOURCE, `+0x68` sélecteur CIBLES). Le sélecteur SOURCE étant **nul**,
`AddEffectBehaviour$$Execute` applique son fallback — `source = <cible courante>` sauf si le sélecteur
source rend quelque chose. **La source de la contamination est donc la tuile elle-même.** Le port
l'exprime par `source_from_target=True` (même motif et même port que le volet `Contaminated` de
`RadBombardmentAbility`).

---

## 2. Port

`scripts/python/engine/runner/operations/triggers/loki/on_toxic_damage.py` :

- `on_toxic_damage_tree(rng, chance, effect_type)` = mirror 1:1 de `CreateBehaviour` —
  `If(TriggerAnd(IsFirstHitInSeries(), MaybeTrigger(rng, Const(chance))),
  AddEffect(1244, "Contaminated", Tiles(Target()), duration_rounds=None, source_from_target=True))`.
- `_on_toxic_damage_ability(state, attacker, target, profile)` = le gate de DÉCLENCHEMENT
  (`DamageProfileHasTrait(OnToxic)` sur `gameconfig.damage_profile(profile)["Traits"]`) + l'exécution de
  l'arbre. `is_first_hit=True` est posé sur l'`AbilityEntities` : le vecteur du port est PER-ATTAQUE
  (une invocation par série), et cette invocation EST le coup d'index 0 — seul que le natif laisse
  passer. Le compte de tirages est donc celui du natif.

Nœuds DSL neufs (namespace `IdunBattle.Entities.Triggers`, dans `engine/entities/triggers.py`) :

- `MaybeTrigger(rng, chance)` — prédicat non déterministe, PRNG en champ (mirror `MaybeTrigger+0x18`).
  La branche `CanUseRandom == false` (BC `DisableRandomness`) n'est pas portée : le runner isolé tourne
  toujours avec le PRNG calé.
- `IsFirstHitInSeries()` — lit `ctx.is_first_hit`, nouveau champ `Nullable<bool>` du `DslContext`
  (défaut `None` → prédicat faux, mirror du `!HasValue`).

Câblage — les deux émetteurs d'attaque, exactement là où `OnFireDamageAbility` est déjà branché :

| vecteur | fichier | position |
|---|---|---|
| attaque NORMALE | `operations/triggers/dispatch.py::after_hit_normal_attack` | juste après `_on_fire_damage_ability` |
| attaque d'ABILITY / splash | `operations/damage_ops.py::execute_ability_attack` | après `_run_hits` + `_apply_damage_pipeline`, à côté de la pose de feu ; remonté dans le retour sous la clé `toxic` |

---

## 3. Porteurs (gate de confrontabilité)

Le canal est **transverse** : il se déclenche sur tout coup dont le profil porte `DamageTrait.OnToxic`,
c.-à-d. le seul profil `Toxic` (`damageProfiles.Toxic.Traits`, `PiercingRatio` 70).

| catégorie | porteurs | chemin d'arrivée en bataille |
|---|---|---|
| **HERO** | `admecMarshall` (arme ranged `Toxic` r2), `deathPutrifier` (arme mêlée `Toxic` + `FoulInfusion`), `genesBiophagus` (arme mêlée `Toxic`), `tyranParasite` (arme mêlée `Toxic`), `deathBlightlord` (`HazeOfCorruption`), `admecDominus` (`RadBombardment`) | **les 6 sont dans `rl_duel.py build --list-pool`** (rank 17, 97 unités régulières) |
| **MoW** | `deathCrawler` (`PlagueburstMortar`, 3 coups `Toxic`) | dans les **8 MoW spawnables** du même `--list-pool` |
| **SUMMON** | `admecSmnVanguard` (3 coups `Toxic` r2) via `ControlEdict` d'`admecMarshall` ; `tyranSmnSporeMine` (`FloatingDeath`, kit non porté) | spawn par leur summoner |
| **NPC** | ~20 doublons boss/npc (`admecBossMarshall*`, `deathNpcPutrifier`, `tyranBossParasite*`, `admecNpc1Vanguard`…) | hors jeu |

→ largement confrontable. Le porteur retenu pour la validation est `genesBiophagus` (« Hollan ») :
**une seule arme, mêlée, profil `Toxic`, 1 coup** — le cas le plus lisible (une attaque = une série = un
tirage).

---

## 4. Validation

### 4.1 Agrément LIVE bout-en-bout (`test_on_toxic_damage_live.py`)

Replay-diff : la même attaque normale rejouée LIVE et OFFLINE sur le même état MT (`dumpRng`). Le test
boucle jusqu'à ce qu'**au moins une pose** ait été confrontée (sinon il ne prouverait que le
non-déclenchement) et vérifie à chaque attaque : profil du coup, PV de la cible bit-exacts, et verdict
de contamination de la tuile de la cible identique des deux côtés. Deux rosters adverses (board MC1_67,
seed 777, Hollan) :

```
[toxic live/necroWarden #0]      profile=Toxic hp live=5365  off=5365   contaminated live=True  off=True   tile=73
[toxic live] attaques confrontees=1 poses observees=1

[toxic live/blackObliterator #0] profile=Toxic hp live=9258  off=9258   contaminated live=False off=False  tile=73
[toxic live/blackObliterator #1] profile=Toxic hp live=10289 off=10289  contaminated live=False off=False  tile=74
[toxic live/blackObliterator #2] profile=Toxic hp live=8022  off=8022   contaminated live=True  off=True   tile=74
[toxic live] attaques confrontees=3 poses observees=1
```

**Le second roster est le CROISEMENT avec #221** (`case-221-daemon-extrablock-rng.md`) :
`blackObliterator` porte le trait `Daemon`, donc son jet de block `Daemon_ExtraBlock` **et** le `Maybe`
de 1203 tombent dans la MÊME attaque — les deux moitiés du même étage RNG, portées à quelques heures
d'intervalle. Trois attaques consécutives restent bit-exactes (PV) **et** concordantes sur le verdict
de contamination (deux tirages perdus, puis un gagné) : la séquence MT ne dérive pas, donc les deux
tirages neufs sont au bon endroit et comptés une seule fois chacun. Même Daemon que la garde #221
(trait `Daemon` sans `Resilient`/`Terrifying` → géométrie propre).

### 4.2 Compte et position du tirage (`test_on_toxic_damage_live.py`, état LIVE / exécution offline)

L'oracle de consommation est l'**état MT** (`mt`/`mti`) d'un clone avancé d'exactement un
`next_bool(chance)` — pas `rng.call_count`, qui est incrémenté par `next_internal` **et** par
`genrand_int32` (+2 par `NextBool`).

- coup `Toxic` → MT == clone après **un** `next_bool(25)`, et le verdict de pose == celui prédit par ce
  tirage ; la tuile posée est la MainTile de la cible ; la **source** de l'effet est cette même tuile ;
- coup `Power` (profil sans `OnToxic`) → aucune pose et **MT inchangé** (0 tirage) ;
- tuile déjà contaminée → le tirage a **quand même** lieu (le `Maybe` précède l'`AddEffect` dans
  l'arbre) mais aucune pose n'est rapportée.

### 4.3 Ancrage de la magnitude (offline, sans live)

`globalValues.toxicDamageContaminationChance` **==**
`seed-bc.Abilities.PassiveAbilities.OnToxicDamageAbility.Constants.chance` **== 25**, et le seul profil
portant `OnToxic` est `Toxic`.

### 4.4 Contre-épreuve (`probe_1203_toxic_contamination.py`)

Le même coup rejoué sur deux états offline issus du **même** snapshot et du **même** MT — canal ARMÉ
(le port) vs canal DÉSARMÉ (l'état du dépôt avant ce port) — puis confrontés au live :

```
[A] tirages traces=1 (attendu 1) ; MT == 1x next_bool ? True ; verdict predit=True ; pose=True
    roll 0 via next_internal : ... on_toxic_damage.py -> behaviours.py:If.execute
                               -> triggers.py:TriggerAnd -> triggers.py:MaybeTrigger -> prng.next_bool
[B] attaque #0 tuile=73 live=True arme=True desarme=False
[B] confrontees=1 poses_live=1 accord_canal_ARME=1/1 accord_canal_DESARME=0/1
```

### 4.5 Non-régression re-jouée — **APRÈS rebase sur `e52d774`** (qui contient #221)

| suite | avant | après |
|---|---|---|
| `test_on_toxic_damage_live.py` | (n'existait pas) | **7/7** (6 d'origine dont le croisement `daemon`, + la garde RANGED `admecMarshall` ajoutée par la passe §5.2) |
| `test_daemon_extra_block_live.py`, `test_block_chances_order_offline.py` (gardes #221) | — | **5/5** — mon canal n'a pas décalé le jet de block Daemon |
| `test_rad_bombardment_live.py` | 4 tests, dégât per-coup **borné à la 1ʳᵉ cible** (`compare_damage_targets=1`) à cause de ce gap | **4/4**, `compare_damage_targets` revenu au défaut (**toutes** les cibles) → le retard d'un tirage a disparu. `off_cont` devient l'**union** des deux poseurs de `Contaminated` (volet `AddEffect(GetAffectedTiles())` + canal on-hit), puisque la tuile d'une cible touchée est désormais contaminée par le coup avant que le volet de l'ability n'y passe — exactement ce que fait le natif |
| `test_brazier_of_holy_fire_live.py` (bridage `compare_hits` levé par #221) | — | **3/3**, dont la cible Daemon à **4 coups** bit-exacts |
| `test_rad_saturation_live.py`, `test_on_fire_damage_migration_live.py`, `test_control_edict_live.py`, `test_death_nova_live.py` | — | **15/15** |
| `test_damage_roll_live.py`, `test_runner_attack_live.py`, `test_damage_ability_live.py`, `test_damage_block_live.py`, `test_damage_crit_live.py` | — | **9/9** |
| `probe_120_pre_unit_ability_fork.py` | — | `PROBE OK` (étape 0 : aucun littéral de ctor manquant) |
| `symbols_sync.py` | — | axes 1-2 SYNCHRONES (`build=gqfc5mff6c`) ; les 24 symboles cités par ce port existent tous dans `data/symbols/gqfc5mff6c/ghidra/functions.tsv` |

`test_skitarii_turn_live.py::test_skitarii_played_by_generic_ai_pass` échoue — **échec PRÉ-EXISTANT**,
reproduit à l'identique avec le port retiré (`git stash`) : `d_bfs 3->3`, `hp 8536->8536`, même
`moved=(6,5)`. Sans rapport avec ce canal (l'attaque du Vanguard n'inflige aucun dégât et le pass IA ne
le rapproche pas). Les 8 autres tests du fichier passent.

---

## 5. Ce qui n'est PAS couvert

- **Granularité per-coup du vecteur**. Le port émet le vecteur after-hit **une fois par attaque** ; le
  natif l'émet par coup. Pour CE canal, le gate `IsFirstHitInSeries` rend les deux **observationnellement
  équivalents** (un seul coup passe, donc un seul tirage, à la même place du flux : après les tirages
  dégât/crit/block de la série). Si un futur consommateur de `On(0x10)` avait besoin des coups 2..N, il
  faudrait propager un vrai index de coup — même réserve que celle déjà documentée pour
  `unit_blocked_triggers`.
- **`CanUseRandom == false`** (BC `DisableRandomness` → `return 99 < chance`) : branche non portée, le
  runner isolé tourne toujours avec le PRNG calé.
- **Magnitude du sous-effet `Contaminated_Unit` (1245)** : hors périmètre, et toujours ouverte
  (`terrain-effects.md` §6.1 : le pourcentage vient d'un appel d'interface, pas d'une clé gameconfig).
- **Chaînes multi-coups d'un même porteur `Toxic`** — la question de FOND est **tranchée par RE**
  (cf. §5.1) ; ce qui reste ouvert n'est que sa **confirmation live**, et le porteur nécessaire n'est
  pas activable par le joueur (§5.2).
- **Face DÉCISION** : la contamination on-hit n'est pas modélisée dans les prédictions du playbook (une
  ability `Toxic` ne « vaut » pas plus pour l'IA offline parce qu'elle contaminera). Le natif ne le
  modélise pas non plus dans les canaux portés, mais ça n'a pas été vérifié.

### 5.1 « Série » = les coups sur UNE cible — tranché au décompilé

Le point restait posé comme une hypothèse (« 1 tirage par série, donc par cible »). Il est désormais
**lu**, et il tient sur trois appuis indépendants du même build :

- `IdunBattle.Entities.Triggers.IsFirstHitInSeriesTrigger$$ShouldTrigger` délègue à
  `IdunBattle.Entities.Abilities.AbilityEntities$$get_IsFirstHit`, qui lit un `Nullable<int>` au champ
  `AbilityEntities+0x110` et rend `HasValue && index == 0` ;
- son **frère** `get_IsFirstHitGroup` lit un champ **DISTINCT**, `AbilityEntities+0x118` (exposé par
  `IdunBattleLogic.Entities.DSLFactory$$IsFirstHitGroupInAttack`). Deux compteurs séparés ⇒ « coup dans
  la série » n'est **pas** « groupe dans l'attaque » : si une série valait toute l'attaque, le second
  compteur n'aurait aucune raison d'exister ;
- `IdunBattle.Operations.ADamageOperation$$SetupHitGroup` construit un groupe **par cible** — il y
  stocke `IdunBattle.Entities.UnitExtensions$$GetStat(<cible>, 5)` à `+0x50` — et
  `IdunBattle.Operations.ADamageOperation$$UpdateCurrentAttackAfterHit` incrémente le compteur de
  groupes de l'attaque courante.

⇒ une **série** est le groupe de coups porté sur **une** cible. Le tirage de 1203 est donc **un par
cible**, jamais un par coup ni un par attaque AoE. C'est exactement ce que fait le port (une invocation
du vecteur par cible, `is_first_hit=True`), y compris sur une ability multi-cibles comme
`PlagueburstMortar` (`nrOfTiles = 3`), où natif et port tirent **3 fois, une par cible**.

### 5.2 Confirmation live du multi-COUPS : porteur non activable (mesuré)

Le seul porteur d'**arme** `Toxic` multi-coups confrontable est le SUMMON `admecSmnVanguard`
(3 coups, r2) — tous les autres sont NPC, et la MoW `deathCrawler` est écartée à dessein
(`combatSnapshot` corrompt un runner contenant une `Machine`, résidu **O7** de
`port-residuals-inventory.md`, or tout ce montage repose sur `combatSnapshot`).

Mesuré avec `probe_1203_toxic_multihit.py` : le summon **arrive bien** en bataille (`admecMarshall` le
spawne via `ControlEdictAbility$$SummonMinion`), mais **n'entre jamais dans `decisionView.toActivate`** —
il joue par la passe IA / la branche Conqueror (`ControlEdictAbility$$AttackWithMinions`), pas par une
activation du joueur. `applyAction` accepte alors le cast (`ok=True`) **sans rien muter ni tirer**
(`mutated=False`, 0 événement, MT inchangé). Deux pièges à retenir, tous deux encapsulés depuis dans
la fixture `tests/engine/runner/_on_hit_tile_effect_replay.py` :

1. le `visualId` LIVE du summon est **`admecNpc1Vanguard`**, pas la clé de config `admecSmnVanguard`
   (même piège que le bug **#38b**) — chercher la clé rend « 0 summon » et fait conclure à tort
   « pas de porteur » ;
2. `currentPlayer == moi` **ne suffit pas** : la porte d'activation est `toActivate`. Sans ce gate, le
   no-op silencieux se lit comme une divergence géante (mesuré : `hp live=5387 / off=3840`,
   soit exactement le dégât d'une attaque **non jouée** côté live) — on aurait imputé à 1203 un écart
   qui n'était qu'un coup manquant.

Ce qui **a** été confronté à la place : un **second porteur, RANGED** (`admecMarshall`, arme `Toxic`
r2), là où la couverture d'origine n'avait que du MELEE (`genesBiophagus`). Le gate natif porte sur le
PROFIL du coup et non sur sa portée : confronter les deux chemins ferme le risque « câblé sur un seul ».
**6 attaques consécutives bit-exactes** (PV **et** état MT, +2 `genrand_int32` par attaque = l'unique
`NextBool` du canal), **dont une pose** confrontée — garde `test_toxic_ranged_carrier_agrees_with_live`.

Reste donc ouvert, et uniquement cela : la confirmation live sur une **série de ≥ 2 coups**. Le chemin
existe (faire jouer le summon par la passe IA, ou porter/valider la branche Conqueror
`AttackWithMinions`) ; il n'a pas été emprunté ici car il déborde du canal 1203.

---

## 6. Résidu ADJACENT (non corrigé ici, hors périmètre)

**`OnFireDamageAbility` et `RadSaturationAbility` posent leur effet avec `source = caster` côté port,
alors que le décompilé donne `source = la tuile`.** Les trois call-sites (`OnFire`, `RadSaturation`,
`OnToxic`) utilisent la **même** surcharge `AddEffect` à 5 arguments, qui passe littéralement `0` en
sélecteur SOURCE (`AddEffectBehaviour+0x60`) ; `AddEffectBehaviour$$Execute` retombe alors sur la cible
courante. `RadBombardment` (surcharge 4 args, même conclusion) porte déjà `source_from_target=True`, et
ce port le fait pour `OnToxic` — restent les deux autres.

Impact observable aujourd'hui : nul pour le port (aucun consommateur de la source de `Fire` (5) ou de
`Contaminated` (1244) — ni `EffectsFromUnitSource`, ni remove-by-source, ni scaling). Il le deviendrait
dès qu'un trigger lirait l'`actor` du message `On(PreEffectAdded = 0x3e)` émis par
`AddEffectOperation`, ou la `SourceUnit` de ces effets. Correction = ajouter `source_from_target=True`
aux deux arbres (`fire.py::on_fire_damage_tree`, `rad_saturation.py::rad_saturation_tree`) et re-jouer
`test_on_fire_damage_migration_live.py` + `test_rad_saturation_live.py` + les tests de tuiles en feu.
