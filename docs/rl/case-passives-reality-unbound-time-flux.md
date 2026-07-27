# case — passifs `RealityUnbound` (thousTzaangor) et `TimeFlux` (thousTerminator)

> **ETAT : RE COMPLETE, PORT NON ECRIT** (mise en veille reseau du 2026-07-27). Ce document
> est l'etat FINAL de la retro-ingenierie ; le port et sa validation live restent a faire.

Build RE : `gqfc5mff6c`. Toutes les VA en hex natif (RVA = VA - 0x180000000, calculee en code).
Les deux items sortent de la file de `docs/rl/passive-ability-coverage.md` (GAP-ABSENT, porteurs
`L+` = heros presents dans `rl_duel.py build --list-pool`).

---

## 0. Premisse tranchee PAR LECTURE : l'audit a raison, le registre ne le contredit pas

Le registre `docs/rl/backlog.md` ligne #66-r2 nomme `TimeFlux` parmi « les 2 derniers consommateurs
de `DSLFactory.Revive` », et `docs/rl/case-66-revive-in-place.md` (statut « RETROFIT #79 LIVRE »)
le cite dans son en-tete. Lecture du code et des deux docs :

- le retrofit REVIVE a porte **5** consommateurs : `Narthecium`, `TaintedNarthecium`,
  `RitesOfMorkai`, `ReanimationBeam`, `PhoenixGem` (`case-66` §6.2) — **`TimeFlux` n'en fait pas
  partie** ;
- `case-66` **§8.2** classe explicitement `TimeFlux`/`GhostRevive` en **residu, port NON tente** ;
- grep du moteur : `TimeFlux` n'apparait que comme MEMBRE D'ENUM
  (`engine/entities/triggered_ability_type.py:300` = 1157, `engine/entities/effect_type.py:323` =
  `TimeFlux_Revive` 1186). Un catalogue n'est pas un cablage.

=> **l'audit (GAP-ABSENT) a raison** ; le registre disait vrai lui aussi (`TimeFlux` EST un
consommateur de `DSLFactory.Revive`) mais ne pretendait pas qu'il etait porte. Aucune des deux
entrees n'est perimee.

**Consequence de perimetre** : `TimeFlux` a **DEUX volets natifs DISTINCTS**, portes par deux
classes natives differentes. Seul le volet REGEN est dans ce case ; le volet ghost-revive reste
le residu `case-66` §8.2 (cf. §4 ci-dessous).

---

## 1. `RealityUnbound` — thousTzaangor « Yazaghor » (HERO, pool rank 17)

### 1.1 Kit gameconfig + i2 (autoritatif)

```
[passive] RealityUnbound  constants {"extraRange":"1","extraMovement":"1"}
« For each different enemy unit that was dealt Psychic Damage this turn Yazaghor deals
  +181 Maximum Damage with his normal ranged attacks. If three or more different enemy units
  have been dealt Psychic Damage this turn he gains +1 Movement and his normal ranged attack
  gets +1 Range until the end of this turn. »
```

`thousTzaangor` porte aussi le trait `WeaverOfFate` (deja porte, #202-A) : **le meme substrat
« unites ayant pris du degat Psychic ce tour »** sert aux deux.

### 1.2 Artefacts natifs CONFIRMES en ghidra (`search_symbols_by_name`)

| symbole | VA | role |
|---|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RealityUnboundAbility$$CreateBehaviour` | `@1811162a0` | volet Movement+Range |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RealityUnboundAbility$$CreateTrigger` | `@181116420` | **ICF-fold** : tail-call `WeaverOfFateAbility$$GetTrigger(factory, 0x4b5)` |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RealityUnboundExtraMaxDamageAbility$$CreateTrigger` | `@181116620` | volet ExtraMaxDamage |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RealityUnboundExtraMaxDamageAbility$$CreateBehaviour` | `@181116530` | idem (corps identique a `$$AddModifier @181116440`) |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$GetTrigger` | `@1811acd60` | trigger PARAMETRE par effectType, partage |

> **`RealityUnboundAbility$$CreateTrigger` n'existe PAS comme fonction ghidra** : la table de
> methodes Frida donne RVA `1116420`, mais `functions.tsv` n'a rien a `181116420`. Lecture des
> octets (`read_bytes`) : `48 8b 49 28 | 45 33 c0 | ba b5 04 00 00 | e9 2f 69 09 00` =
> `mov rcx,[this+0x28] (la factory) ; r8d=0 ; edx=0x4b5 ; jmp +0x9692f` -> cible
> `0x181116431 + 0x9692F = 0x1811ACD60` = `WeaverOfFateAbility$$GetTrigger`. **Ne pas se fier au
> nom** : c'est un fold ICF, pas une parente.

### 1.3 Arbres LUS

**`WeaverOfFateAbility$$GetTrigger(factory, effectType)`** (generique, deja porte pour WeaverOfFate) :
```
On(9 = Attack, subject=1)
& AmountIsEqualOrGreater(
      UnitsThatTakenDamageThisTurn( Enemies(self@0x148, AllUnits), 0xd = Psychic ),
      Get(3) )                                   # seuil 3 EN DUR
& Not( HasEffect(self@0x148, <effectType>, activeOnly=1, flags=6) )
```

**`RealityUnboundAbility$$CreateBehaviour @1811162a0`** :
```
op_Addition(
  AddStaticStatModifierEffect(self@0x148, 0x4b5 = 1205 RealityUnbound_Movement,
                              stat = 1  = MOVEMENT,
                              amount = GetNumberConstant(cfg, 0xe = extraMovement),
                              turns = Nullable<int>(1), isHidden = 0),
  AddStaticStatModifierEffect(self@0x148, 0x4b6 = 1206 RealityUnbound_Range,
                              stat = 0x18 = 24 = EXTRA_RANGE,
                              amount = GetNumberConstant(cfg, 0xd = extraRange),
                              turns = Nullable<int>(1), isHidden = 0) )
```
=> le trigger de CE volet est `GetTrigger(0x4b5)`, donc le `Not(HasEffect(...))` porte sur
**1205** : l'anti-re-trigger du tour est l'effet Movement lui-meme.

**`RealityUnboundExtraMaxDamageAbility$$CreateTrigger @181116620`** :
```
On(0x43 = 67 = FinalDamage, subject=1)
& HasTakenDamageOfDamageProfileThisTurnAmountOfTimes(
      unit = target@0x178, damageProfile = 0xd = Psychic, times = 1, unitSelectionType = 2)
& AreEnemies(target@0x178, self@0x148)
```

**`RealityUnboundExtraMaxDamageAbility$$CreateBehaviour @181116530`** :
```
AddStaticStatModifierEffect(self@0x148, 0x4b7 = 1207 RealityUnbound_ExtraMaxDamage,
                            stat = 0x19 = 25 = EXTRA_MAX_DAMAGE,
                            amount = GetVariableForLevel(cfg, 0x49 = extraMaxDmg, abilityState),
                            turns = Nullable<int>(1), isHidden = 0)
```

### 1.4 Qualification des enums (dump `data/symbols/gqfc5mff6c/frida/enums.tsv`)

- `IdunBattle.Configuration.AbilityConstantType` : **13 (0xd) = `extraRange`**, **14 (0xe) = `extraMovement`**.
- `IdunBattle.Configuration.AbilityVariableType` : **73 (0x49) = `extraMaxDmg`**.
- `IdunBattle.DSL.EventTriggerType` : **67 (0x43) = `FinalDamage`**, 9 = `Attack`.
- `DamageProfileType` : **13 (0xd) = `Psychic`**.
- `StatType` (engine/entities/stats.py, mirror natif) : 1 = MOVEMENT, **24 = EXTRA_RANGE**,
  **25 = EXTRA_MAX_DAMAGE**.
- `EffectType` : 1205 `RealityUnbound_Movement`, 1206 `RealityUnbound_Range`,
  1207 `RealityUnbound_ExtraMaxDamage`.
- `TriggeredAbilityType.RealityUnbound = 1174` (le passif).

### 1.5 `HasTakenDamageOfDamageProfileThisTurnAmountOfTimes` — LU, pas devine

- `DSLFactory$$HasTakenDamageOfDamageProfileThisTurnAmountOfTimes @180df12f0`
  (signature Frida : `unit:ITargetsSelector, damageProfile:DamageProfileType, times:Int32,
  unitSelectionType:UnitSelectionType`).
- `...Trigger$$.ctor @180f9e2d0` : `+0x10 = selecteur`, `+0x18 = damageProfile`,
  `+0x1c = times`, `+0x20 = unitSelectionType`.
- `...Trigger$$ShouldTrigger @180f9e0f0` : resout le selecteur, prend
  `ActorStatisticsComponent` de l'unite, et rend
  `ContainsKey(receivedDamageThisTurn, profile) && receivedDamageThisTurn[profile] == times`.
  **EGALITE STRICTE** (`local_res10[0] == *(int *)(param_1 + 0x1c)`), pas `>=`.
  `unitSelectionType (+0x20)` n'est **PAS LU** par `ShouldTrigger`.

=> `times = 1` = « c'est la PREMIERE instance de degat Psychic que cette cible prend ce tour » :
c'est exactement le « for each DIFFERENT enemy unit » de l'i2 (chaque ennemi ne compte qu'une fois).

### 1.6 Le vecteur `On(FinalDamage = 67)` : MANQUANT dans le port

- Emetteur natif : `IdunBattle.Operations.ADamageOperation$$RegisterFinalDamage @180e26610`
  (derniere instruction : `FUN_180026490(0x50, …, 0x43, entities)`).
- `AbilityEntities.ctor(caster = param_3 = l'ATTAQUANT, owner = actor = target = param_4 = la
  VICTIME, casterTiles = GetTiles(attaquant), targetTiles = GetTiles(victime))`.
- **XREFS EXHAUSTIVES** : seuls `IdunBattle.Operations.AttackDamageOperation$$Execute` et
  `IdunBattle.Operations.AbilityDamageOperation$$Execute` l'appellent -> l'event est emis
  **une fois par ATTAQUE** (et par degat d'ability), **jamais** pour un DoT/knockback.
- Cote port : `grep FinalDamage engine/` = uniquement la definition d'enum
  (`dsl/event_trigger_type.py:96`). **Aucun vecteur** -> a creer
  (`final_damage_triggers` dans `triggers/dispatch.py`), appele depuis `execute` (voie attaque
  normale, `damage_ops.py`) et `execute_ability_attack`.
- ORDRE requis : le compteur `received_damage_this_turn` doit etre incremente AVANT l'emission
  (sinon `times == 1` ne peut jamais etre vrai) -> apres `_register_received_damage`.

### 1.7 Substrat deja porte (#202, ZERO primitive nouvelle)

- `UnitComponent.received_damage_this_turn` (`runner/components.py`) = mirror du dict
  `ActorStatisticsComponent @+0x80` ; ecrit par
  `AttackDamageOperation._register_received_damage` (mirror
  `IdunBattle.Operations.RegisterDamageOperation$$Execute` ->
  `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterReceivedDamage`, TryAdd(p,1)
  sinon +1) ; reset par-unite du joueur ENTRANT dans `StartTurnOperation.execute` (mirror
  `IdunBattle.Operations.StartTurnOperation$$ResetUnit` ->
  `...$$ResetReceivedDamageThisTurn`).
- `units_that_taken_damage_this_turn` + `_alive_enemies_of` :
  `runner/operations/triggers/loki/weaver_of_fate.py` (reutilisables tels quels).
- Feuille `AddStaticStatModifierEffect` : `runner/abilities/behaviours/effects.py:494`
  (parametre `duration_turns` = le noeud `Direct(n)` deja en TOURS = le `Nullable<int>(1)` natif ;
  NE PAS utiliser `duration_rounds`, qui est `TurnsFromRounds`).

### 1.8 Points a trancher AVANT / PENDANT le port

1. **STACK de l'effet 1207.** L'i2 (« for EACH different enemy unit … +181 ») impose le CUMUL, et
   le natif appelle `AddStaticStatModifierEffect` une fois par ennemi distinct **sans
   `RemoveEffect` prealable** (contraste explicite avec `MasterAnnihilator` et `FleshmetalGuns`,
   qui font Remove+Add). Or `AddEffectOperation.execute` du port a un gate « deja-present »
   (`return None`) sauf si la classe d'effet porte `stacks_stat_mod_on_add = True` (patron
   ActOfFaith). => la classe d'effet 1207 doit porter ce flag. **A CONFIRMER LIVE**
   (1 ennemi Psychic -> +181 ; 2 ennemis -> +362).
2. **`EXTRA_MAX_DAMAGE` (25) et `EXTRA_RANGE` (24) n'ont AUCUN consommateur dans `engine/`**
   (grep : seules les definitions d'enum dans `entities/stats.py`). Poser le stat-mod ne suffira
   donc pas : il faut verifier (et, si necessaire, cabler) leur lecture dans le calcul de degat
   (borne MAX de l'attaque normale RANGED) et dans la portee d'attaque. **C'est le vrai risque
   de no-op silencieux de cet item.** `MOVEMENT` (1), lui, est un stat consomme.
3. `unitSelectionType = 2` non lu par `ShouldTrigger` -> aucun impact (a documenter, pas a porter).

---

## 2. `TimeFlux` — thousTerminator « Toth » (HERO, pool rank 17) — VOLET REGEN

### 2.1 i2 (autoritatif, volet regen seulement)

« At the beginning of his turn, Toth **regenerates 873 Health** plus an additional amount equal to
**the Damage of the last hit he received in the last enemy turn**. The total amount restored
**cannot exceed 4365 Health**. »

### 2.2 Artefacts natifs CONFIRMES

| symbole | VA |
|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimeFluxAbility$$CreateTrigger` | `@1811a8850` |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimeFluxAbility$$CreateBehaviour` | `@1811a8690` |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimeFluxReviveAbility$$.ctor` | `@1811a88a0` (volet ghost, HORS perimetre) |

### 2.3 Arbres LUS

**`TimeFluxAbility$$CreateTrigger @1811a8850`** :
```
<trigger de base factory@0xa0>  &  On(0x13 = 19 = TurnStart_Other, subject=1)
```
`factory@0xa0` = **`OwnerIsActor`** (« le proprietaire est le joueur ENTRANT ») — meme cache que
`LivingMetalRepairAbility$$CreateTrigger`, ou il est PROUVE live (`probe_203`, regen nulle au tour
adverse). Noter l'absence de `IsDamaged(self)` (contraste LivingMetal) : le clamp a `hp_max` du
`HealUnitOperation` rend le heal nul a PV pleins, donc pas d'ecart observable.

**`TimeFluxAbility$$CreateBehaviour @1811a8690`** :
```
Heal( source = self@0x148, targets = self@0x148,
      amount = Min( Sum( Direct(GetVariableForLevel(cfg, 0x20 = hpToHeal,    abilityState)),
                         LastHitDamageTakenLastTurn(self@0x148) ),
                    Direct(GetVariableForLevel(cfg, 0x47 = maxHpToHeal, abilityState)) ),
      options = HealBehaviourOptions.ForRegenerate( AbilityOrEffect(this.Id) ) )
```
`AbilityVariableType` : **32 (0x20) = `hpToHeal`**, **71 (0x47) = `maxHpToHeal`**.
=> `amount = min(hpToHeal + lastHitDamageTakenLastTurn, maxHpToHeal)` — mirror exact de l'i2
(873 / 4365 au niveau du porteur mesure).

### 2.4 `LastHitDamageTakenLastTurn` — substrat NEUF, entierement LU

- `IdunBattleLogic.Entities.DSLFactory$$LastHitDamageTakenLastTurn @180df5e80` ->
  `IdunBattle.Entities.Formulas.LastHitDamageTakenLastTurnFormula$$Calculate @180f1be80` :
  resout le selecteur, prend `ActorStatisticsComponent` de l'unite, **rend `*(int *)(comp + 0x70)`**.
- **Ecriture** : `IdunBattle.Operations.ApplyDamageOperation$$Execute @180e5a540`, dans le bloc
  `if (local_528 != 0)` (ou `local_528 = GetComponent<ActorStatisticsComponent>(param_4)`,
  **param_4 = la VICTIME** — etabli par l'appel
  `RecordHitStatistics(param_2, param_3 = attaquant, param_4 = victime, …)`) :
  ```
  *(int *)(stats + 0x68) = (int)*param_1;      # lastHitDamageTaken (all-time)
  *(int *)(stats + 0x6c) = (int)*param_1;      # lastHitDamageTaken THIS TURN
  ```
  `(int)*param_1` = 1er champ de `DamageAppliedResult` = **la somme des reductions REELLEMENT
  appliquees** au coup (`FillUpStatComponent.Reduce` sante + 2e pool + `ReduceShield`), et
  `ApplyDamageOperation$$Execute` est appelee **PAR COUP** (cf. `RecordHitStatistics`,
  `DamageAppliedResult`).
- **Roulement** : `IdunBattle.Operations.StartTurnOperation$$ResetUnit @180ea5a10`, juste apres
  `ResetReceivedDamageThisTurn` :
  ```
  stats[0x70] = stats[0x6c];    # lastTurn <- thisTurn
  stats[0x6c] = 0;
  ```
  Donc @0x70 = **le degat du DERNIER COUP recu depuis le debut du tour precedent du proprietaire**.
- `ActorStatisticsComponent$$ResetThisTurn @180f924a0` ne touche NI 0x6c NI 0x70 (il roule
  0xfc<-0xf8 et fait `Max` sur les paires 0x78/0x7c, 0xec/0xf0, 0x58/0x5c, 0xa0/0xa4) : le
  roulement du « last hit » est **exclusivement** dans `ResetUnit`.

### 2.5 Point d'ancrage cote port

- `runner/components.py` : 2 champs neufs sur `UnitComponent`
  (`last_hit_damage_taken_this_turn` / `..._last_turn`), mirror de
  `ActorStatisticsComponent @+0x6c / @+0x70`.
- Ecriture : `AttackDamageOperation._apply_damage_pipeline` (`runner/operations/damage.py`) —
  **la valeur est le TOTAL DU DERNIER COUP** (`r["per_hit"][-1]`, deja expose par
  `damage_hits.py::_run_hits` : `per_hit` = PV + bouclier + armure-pool par coup = exactement
  `(int)*param_1`), PAS le total de l'attaque. Un port qui prendrait `total` surestimerait
  massivement sur une attaque multi-coups.
- Roulement : `runner/operations/turnflow.py::StartTurnOperation.execute`, dans la boucle
  par-unite du joueur ENTRANT **deja presente** (celle qui fait
  `received_damage_this_turn.clear()`), juste apres — ordre ligne-a-ligne de `ResetUnit`, et
  **avant** l'emission de `turn_start_other_triggers` (0x13).
- `HealUnitOperation` (`runner/operations/heal.py`) existe deja (utilise par LivingMetal).

---

## 3. Plan de port (a executer)

| fichier | nature | contenu |
|---|---|---|
| `engine/runner/operations/triggers/loki/reality_unbound.py` | **NEUF** | `RealityUnboundAbility` (On(9), gate WeaverOfFate-like sur 1205) + `RealityUnboundExtraMaxDamageAbility` (On(67)) + les 2 arbres DSL de behaviour |
| `engine/runner/operations/triggers/loki/time_flux.py` | **NEUF** | `TimeFluxRegenAbility` (On(19), OwnerIsActor) + arbre `Heal(Min(Sum(...)))` |
| `engine/entities/effects/loki/…` + `entities/effects/factory.py` | ajout | classes d'effet 1205/1206/1207 (dont `stacks_stat_mod_on_add` pour 1207) |
| `engine/runner/operations/triggers/dispatch.py` | ajout | `ABILITY_TRIGGERS["RealityUnbound"]`, `ABILITY_TRIGGERS["TimeFlux"]`, vecteur `final_damage_triggers` |
| `engine/runner/components.py` | ajout | 2 champs `last_hit_damage_taken_*` |
| `engine/runner/operations/damage.py` + `damage_ops.py` | ajout | ecriture du last-hit + emission `On(FinalDamage)` sur les 2 seules voies natives |

**Criteres de validation (2 cas discriminants par passif, dont un cas NEGATIF)** :

- `RealityUnbound` / Movement+Range : (+) 3 ennemis distincts ayant pris du Psychic ce tour ->
  +1 Move et +1 Range pour 1 tour ; (-) **2** ennemis seulement -> AUCUN effet 1205/1206
  (c'est le gate `>= 3` qui doit se trahir).
- `RealityUnbound` / ExtraMaxDamage : (+) 1er coup Psychic sur un ennemi -> +extraMaxDmg ;
  (-) 2e coup Psychic sur le MEME ennemi -> **aucun bonus supplementaire** (gate
  `times == 1`, egalite stricte).
- `TimeFlux` : (+) Toth encaisse un coup au tour adverse -> au debut de SON tour, heal =
  `min(hpToHeal + degat du DERNIER coup, maxHpToHeal)` ; (-) tour adverse SANS coup recu ->
  heal = `hpToHeal` seul (et non le residu du tour d'avant).

---

## 4. Hors perimetre — `TimeFlux` volet GHOST-REVIVE (residu confirme)

Deuxieme volet, classe native DISTINCTE : `TimeFluxReviveAbility$$.ctor @1811a88a0` =
`GhostReviveAbility` parametree par `EffectType.TimeFlux_Revive = 0x4a2 = 1186` (le ctor affiche
`EnvDefenderHealthBuffAbility..ctor` est un fold ICF — **ne pas se fier au nom**). Arbres deja LUS
et documentes par `case-66` §8.2 (`GhostReviveAbility$$CreateTrigger @180f83800` /
`$$CreateBehaviour @180f83600` ; le revive vit dans `GhostEffect$$CreateTargetTrigger @180f4bb90`
/ `$$CreateTargetTriggerBehaviour @180f4b680` / `$$CreateHandleTriggerAbilitiesInternal @180f4b1f0`).
Trois debloqueurs manquants, aucun devinable : (a) vecteur `On(PreUnitMove = 31)` absent du port ;
(b) effet portant une TUILE (le ghost) avec sa condition de disparition ; (c) revive **NON
in-place** (`SetRevivePosition @180e936e0` parametree par la tuile du ghost). Reste classe
`[fable]` par `docs/rl/case-220/thousand-sons.md`.
