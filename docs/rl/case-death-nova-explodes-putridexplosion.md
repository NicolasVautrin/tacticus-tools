# Case DEATH-NOVA — traits `Explodes` (1008) et `PutridExplosion` (2028)

**Status : PORTE + VALIDE LIVE (5/5 `test_death_nova_live.py`, agreement live==port PAR CIBLE sur
3 geometries + cascade). RE COMPLETE, decompile-citee (build `gqfc5mff6c`). Ordre des evenements de
mort `1 -> 2 -> 55` TRANCHE au decompile (etait une inference). Zero regression : les 3 vecteurs de
mort existants + les familles de degat rejoues (15/15 death-vector, 10/10 famille ability, fire DoT
OK).**

## 1. Ce que c'est

Deux traits qui font EXPLOSER le porteur a sa mort, en zone, sur ses adjacents :

| trait | id `UnitTrait` | ability accordee (`TriggeredAbilityType`) | porteurs lineup |
|---|---|---|---|
| `Explodes` | 1008 | `Explodes` **1021** | `adeptMorvenn`, `necroSpyder`, `orksKillaKan` (+ 12 npc dont `orksRedGobbo`) |
| `PutridExplosion` | 2028 | `PutridExplosion_Ability` **1074** | `deathPutrifier` (+ 5 npc, + summon `deathSmnNurglings`) |

Le registre trait -> ability est `StaticBattleRules.Trait$$.cctor` **@18157f650** (lu par
`Trait$$GetTriggeredAbility` **@18157ed10**) ; la materialisation dans l'`AbilitiesComponent` se fait
par `AddTraitOperation$$AddDerivedAbilities` **@180e513c0** (op 0x29).

> **FAUX-AMIS (espaces de numerotation DISTINCTS, verifies au dump d'enums)** :
> `ActiveAbilityType.HarbingerOfDestruction`=1008, `ActiveAbilityType.Incursion`=1021,
> `ActiveAbilityType.ScytheOfDust`=1074, `EffectType.Swarm_HitReduction`=1021,
> `EffectType.FoulInfusion_ExtraHits`=1074, `EffectType.HeavyWeapon_ExtraDmg`=1008.
> Aucun rapport avec ce cluster (le port #44 HarbingerOfDestruction en particulier).

## 2. RE native (decompile = verite)

### Symboles

| Symbole | VA |
|---|---|
| `ExplodesAbility$$CreateTrigger` | `0x18121e6f0` |
| `ExplodesAbility$$CreateBehaviour` | `0x18121e450` |
| `PutridExplosion_Ability$$CreateTrigger` | `0x1812248f0` |
| `PutridExplosion_Ability$$CreateBehaviour` | `0x181224710` |
| `DSLFactory$$OnPreDeath2` -> `DSLFactory$$OnDeathEvent` | `0x180df7ee0` -> `0x180df7ad0` |
| `DSLFactory$$AbilityAreaDamage` | `0x180de5920` |
| `DSLFactory$$AttackWithAbilityDamage` (7 args) -> core | `0x180de9c90` -> `0x180de9e50` |
| `DSLFactory$$AdjacentUnits` | `0x180de8320` |
| `DSLFactory$$UnitsFromFaction` | `0x180dff8c0` |
| `DSLFactory$$ConditionalAmount` | `0x180dec5c0` |
| **emetteur des events de mort** `KillUnitOperation$$Execute` | `0x180e76470` |

### 2.1 L'ORDRE DES EVENEMENTS DE MORT — TRANCHE (etait le seul point non resolu)

L'emetteur reel est **`KillUnitOperation$$Execute` @180e76470** — et non `ApplyDamageOperation$$Execute`
@180e5a540 (qui n'emet que `0x3a`/`0xf`/`0x10`), ni `RemoveUnitOperation$$Execute` @180e8add0 (`0x25`),
ni les lambdas de `InputMessageProcessor$$VerifyDeaths` @180ebb0a0 (qui ne font qu'appeler
`OperationProcessor$$KillUnit` @180e0a9f0 -> `KillUnitOperation$$Execute`).

Ordre des INSTRUCTIONS (adresses de retour des call-sites de dispatch d'interface) :

| # | event | slot | ret-addr |
|---|---|---|---|
| 1 | `PreUnitDeath` = **1** | 0x4d | `0x180e76c4c` |
| — | *garde* `if (*pcVar21 == '\0')` | — | `0x180e76c9e` |
| 2 | `PreUnitDeath_2` = **2** | 0x50 | `0x180e76dea` |
| 3 | `UnitDeath` = 0 | 0x4d | `0x180e77269` |
| 4 | `UnitDefeated` = **55** (0x37) | 0x4d | `0x180e7731c` |
| 5 | `PostUnitKill` = 54 (0x36) | 0x4d | `0x180e7749c` |

=> **`1 -> 2 -> 55` CONFIRME** (la numerotation etait une inference ; elle se trouve juste). Les
dispatchs sont SYNCHRONES (`EvaluateTriggerOperation$$Execute` @180e6fd60 et `$$ExecuteImmediately`
@180e6ec90 terminent tous deux par `ExecuteInternal` @180e6ef40 hors mode record/replay), donc ordre
d'emission == ordre d'execution.

**Asymetrie de garde — RESOLUE (#88/#89, 2026-07-25)** : `On(1)` est emis AVANT la garde
`@0x180e76c9e` ; `On(2)`, `On(0)`, `On(55)`, `On(54)` sont DEDANS (profondeur d'accolades 7 vs 9, et
AUCUN `else`). Ce n'est PAS un lookup de dictionnaire mais le `hasValue` du **`Nullable<ReviveData>`
@`UnitComponent + 0xa8`** — le MEME champ qu'ECRIT `ReviveBehaviour.Execute @180fd1230` et que
LIT+PURGE `ReviveUnitOperation.Execute @180e91bd0`. **Consequence : un REVIVE declenche sur `On(1)`
COURT-CIRCUITE `On(2)` — donc la death-nova NE PART PAS si le mourant est revive.** Le port applique la
garde (`kill_unit_revive_gate`, `runner/operations/revive.py`) ; scenario live discriminant
`test_revive_cancels_death_events_live.py` (Narthecium adjacent a un `deathPutrifier` : nova annulee vs
nova emise sur la face negative). Detail : `case-66-revive-in-place` §7.

### 2.2 Les triggers

`OnPreDeath2(a, b)` @180df7ee0 = `OnDeathEvent(eventId=2, a, b)` @180df7ad0, qui construit :

```
On(eventId)
  & (a == 0 ? NOT HasFlag(dying@0x178, UnitFlag.Overkilled = 8) : TRUE)
  & (b == 0 ? NOT HasTrait(dying@0x178, UnitTrait.Steppable = 0x1b = 27) : TRUE)
```

| ability | appel | => gates |
|---|---|---|
| `Explodes` @18121e6f0 | `OnPreDeath2(1, 1) & OwnerIsTarget` | **AUCUN** (ni overkill, ni Steppable) |
| `PutridExplosion` @1812248f0 | `OnPreDeath2(1, 0) & OwnerIsTarget` | pas d'overkill ; `NOT Steppable` |

> **LE PIEGE** : `a=1` => l'explosion part **MEME EN OVERKILL**. Contraste `FinalJusticeAbility$$
> CreateTrigger` @18121f180 = `OnPreDeath(1, 0)` -> event **1**, dont le gate overkill vit dans son
> **BEHAVIOUR** (`NOT TargetIsOverkilled`). Un port copie sur FinalJustice serait FAUX.

### 2.3 Les behaviours

**`ExplodesAbility$$CreateBehaviour` @18121e450**

```
amount = PercentageOf( StatAmount(Self@0x148, Health=5, Max=2),
                       Sum( ConfigConst(0x3fd=1021 Explodes, Self, key 0xf=extraDmgPct),
                            ConditionalAmount( HasEffect(Self, 0x44a=1098
                                                         EffectType.RammingSpeed_ExtraExplode, 1, 6),
                                               ConfigConst(0x423=1059 ActiveAbilityType.RammingSpeed,
                                                           Self, key 0xf=extraDmgPct),
                                               Get(0) ) ) )
AbilityAreaDamage( Self@0x148, AdjacentTiles(Self@0x148), amount,
                   profile = Direct(Nullable(15 = DamageProfileType.DirectDamage)),
                   src     = AbilityOrEffect(this.Id) )
```

`AbilityAreaDamage @180de5920` n'est PAS un noeud : c'est un helper qui se deplie en

```
AttackWithAbilityDamage(caster, Units(area, 0, 3), amount, profile, src)
  & RefreshDynamicStatModifierValueBehaviour(AllAliveMachinesSelector(area))
```

=> **maxPV(mourant) x (25% [+50% si effet 1098])**, profil `DirectDamage`, **1 coup**, sur **TOUTES**
les unites adjacentes — **AUCUN filtre d'equipe => FRIENDLY-FIRE**.

**`PutridExplosion_Ability$$CreateBehaviour` @181224710**

```
targets = AdjacentUnits(Self@0x148, 0, 3)
          - UnitsFromFaction(<les memes>, GetStringConstant(cfg, 0x3d), 3)
amount  = PercentageOf( StatAmount(Self@0x148, Health=5, Max=2),
                        Direct(GetNumberConstant(cfg, 0xf)) )
AttackWithAbilityDamage( Self@0x148, targets, amount, GetDamageProfile(cfg), nrOfHits = 1,
                         src = AbilityOrEffect(this.Id) )
```

=> **25% du maxPV** en **Toxic** a tous les adjacents **SAUF la faction DeathGuard**. L'exclusion est
par **FACTION** (`FactionId` gameconfig), **PAS par equipe** : un ennemi Death Guard est epargne, un
ALLIE non-DeathGuard est touche.

### 2.4 Constantes — LUES EN CONFIG, zero hardcode

Les DEUX abilities n'ont **aucune** entree `abilities` en gameconfig : leur `AbilityConfiguration`
vient des `globalValues.traitVariables` du trait homonyme.

| cle | valeur | usage |
|---|---|---|
| `explodesDmg` | 25 | `ConfigConst(1021, key 0xf)` |
| `putridExplosionDmgPct` | 25 | `GetNumberConstant(cfg, 0xf)` |
| `putridExplosionFactionId` | `DeathGuard` | `GetStringConstant(cfg, 0x3d)` |
| `putridExplosionDamageProfile` | `Toxic` | `GetDamageProfile(cfg)` |
| `abilities.RammingSpeed.constants.extraDmgPct` | 50 | `ConfigConst(1059, key 0xf)` |

Profils : `DirectDamage` PiercingRatio **100** ; `Toxic` PiercingRatio **70** (+ trait `OnToxic`).

## 3. Port (mirror 1:1)

- **Module** : `engine/runner/operations/triggers/loki/death_nova.py` — `ExplodesAbility`,
  `PutridExplosionAbility` (base commune `_DeathNovaAbility` : `event_id = PreUnitDeath_2`,
  `fire_on_death = True`, `matches` = `OwnerIsTarget` + gate `b` Steppable, **aucun** gate overkill) +
  les deux arbres DSL `explodes_tree` / `putrid_explosion_tree`.
- **Vecteur** : `pre_unit_death_2_triggers` (`triggers/dispatch.py`), appele par
  `AttackDamageOperation._fire_death_if_killed` (`operations/damage.py`) **entre** `after_death_triggers`
  (`On 1`) et `unit_defeated_triggers` (`On 55`) — a la position LUE au decompile (§2.1).
- **Registre** : `TRAIT_TRIGGERS["Explodes"] / ["PutridExplosion"]`.
- **Feuilles** : toutes existantes sauf deux ajouts mineurs, tous deux homonymes natifs —
  `ConditionalAmount` (`entities/formulas.py`, `DSLFactory.ConditionalAmount @180dec5c0`) et
  `RefreshDynamicStatModifierValue` (`runner/abilities/behaviours/stats.py`, STRUCTURAL NO-OP : le port
  n'a aucune machinerie de stat-modifier dynamique a rafraichir — precedent `Inform`/`KillDeadUnits`).
- **`AttackWithAbilityDamage`** (`behaviours/combat.py`) etendue de deux parametres :
  - `multi=True` — mirror de l'`AttackBehaviour.Execute @180fb91a0` que la factory native enveloppe
    TOUJOURS (selecteur -> N cibles, `OrderBy` = ordre de lecture == id) ;
  - `native_operation="ability"` — route sur `AbilityDamageOperation`
    (`execute_ability_attack(..., is_attack_damage_op=False)`) et non sur la route `execute_direct`
    HISTORIQUE du DoT de tuile. **Justification RE** : `DSLFactory.AttackWithAbilityDamage
    @180de9e50` construit `AbilityDamageBehaviour` + `AttackBehaviour` -> `AbilityDamageOperation.
    ExecuteHits @180e2a860` (percage/armure + mods DEFENSEUR + block + bouclier + caps
    member/Resilient, AUCUN crit — la famille ABILITY n'a pas de slot `RollCritical`, cf. #45f).
    La route `"direct"` reste le DEFAUT -> le DoT feu est INCHANGE (residu documente : sa migration
    est un chantier separe).
- **Face PREDICTION** : `TRAIT_TRIGGERED_ABILITY_IDS += {"Explodes": (1021,), "PutridExplosion":
  (1074,)}` — mirror fidele du contenu de l'`AbilitiesComponent`. **Mesure d'inertie** : aucun symbole
  `Explodes*Playbook` / `PutridExplosion*Playbook` n'existe dans le binaire, donc
  `PlaybookDatabase.LoadPlaybook(1021/1074)` rend `null` et le dispatcher `TriggeredAbilitiesUtility`
  SKIPPE — l'ajout est structurellement correct mais **observablement inerte cote utilite, comme dans
  le jeu** (l'IA native n'anticipe pas non plus la nova).

### 3.1 Etage d'ARRONDI corrige (mesure live, perimetre etroit)

`CalculateBaseDamageWithAllModifiers @18102d3f0` applique, a l'etape MULTIPLICATEUR (slot 0x10 ->
`DamageCalculations.CalculateBaseDamageWithModifiers @1810021c0`), un `Fix64.Round(Mul(v, multiplier),
AwayFromZero=1)` (`Round` @181002308 ; `Fix64.Round @1815636e0` flag=1 = half-away-from-zero). Ce Round
est **inconditionnel des qu'un `Nullable<DamageModifiers>` HasValue** — et dans `CalculateAbilityDamage
@18102cb50` le `param_7` defenseur est TOUJOURS construit. Le port ne materialisait ce Round que dans
`apply_capped_modifiers` **quand la %-list est NON vide** ; %-list vide -> valeur fractionnaire puis
**troncature** du caller (`op_Explicit` @181564100 = `raw >> 32`).

Divergence de ±1 quand le produit du percage tombe juste sous un entier (`Fix64.Div(70,100)` =
0.6999999999534) :

| base | Fix64 apres percage | port (floor) | **natif (live)** |
|---|---|---|---|
| 200 | 139.99999999068 | 139 | **140** |
| 201 | 140.69999999 | 140 | **141** |

Corrobore par le DoT feu, qui materialise DEJA par `int(round(...))` dans `execute_direct`
(1908 x 25% = 476.99999999 -> live 477).

**Fix** : `apply_all_modifiers(..., round_materialize=False)` (defaut = comportement historique
STRICTEMENT inchange) ; le flag n'est active QUE par la feuille `AttackWithAbilityDamage` en
`native_operation="ability"`. **Generaliser aux autres vecteurs COMBAT (bornes d'attaque NORMALE
`damage_ops:177/179`, ability bounds-mode `:353`, normal-like `:472`, additional-hits) est un CHANTIER
SEPARE** : ces chemins sont live-valides bit-exact AVEC la troncature et exigeraient leur propre
campagne de mesure. Voir backlog.

## 4. Validation live ADVERSARIALE

`tests/engine/runner/test_death_nova_live.py` — **5/5 pass**, rejoue 2x (stable). Protocole :
board `MC1_67`, geometrie DRIVEE (porteur au centre, roles choisis sur le ring 1, controles hors ring),
`--hp-player` = maxPV CONNU, `--block-target 0,0`, coup letal LIVE, puis comparaison **PAR CIBLE** du
delta de PV live contre le delta produit OFFLINE par `pre_unit_death_2_triggers` rejoue **depuis la meme
capture d'etat** (decisionView + observeBattle + combatSnapshot + boardGraph + dumpRng).

| # | scenario | observe LIVE | port | verdict |
|---|---|---|---|---|
| 1 | Explodes, maxPV 804, allie + tueur adjacents, controle hors ring | allie 201, tueur 201, controle **0** | idem | **agreement 4/4** ; friendly-fire PROUVE ; gate de zone PROUVE ; 201 = 25% du **maxPV** |
| 2 | Explodes, maxPV 300, mort **OVERKILL CERTAINE** (degat BRUT [8356,12532] >= 2 x 300) | nova part : allie 75, tueur 75 | idem | **le piege est tenu** : aucun gate overkill |
| 3 | PutridExplosion, maxPV 300, allie Aeldari + ENNEMI DeathGuard + tueur adjacents | ennemi DeathGuard **0**, allie 75, tueur < 75 | idem | exclusion par **FACTION** (pas equipe) PROUVEE ; profil Toxic p70 decompose |
| 4 | (probe) CHAINE : nova de A tue un 2e porteur `Explodes` B adjacent | allie = 1325 = **1200 (A) + 125 (B)** | idem | **cascade re-entrante** `On(2)` -> mort de B -> `On(2)` de B |
| 5 | offline : gates `a`/`b` | — | — | `Explodes` matche AVEC et SANS overkill ; `PutridExplosion` SUPPRIMEE si le mourant est `Steppable`, `Explodes` non ; `OwnerIsTarget` rejette la mort d'une AUTRE unite |

Scenario 4 = `probe_deathnova.py --case chain` (commite), qui donne aussi le datapoint
**NON-OVERKILL CERTAIN** (degat BRUT [4812,7224] < 2 x 4800) : la nova part la aussi.

**Preuve d'OVERKILL, observable et non devinee** : `healthDmg*` d'`aiPredict` est CAPE a `hpBefore`
(inutilisable) ; on lit `totalDmg*` (degat BRUT) quand la cible n'a ni armure-pool ni bouclier, et on
compare a `2 x PV` (`is_overkill @181032db0`, `overkillDmgPctOfHealth`=100). Preuve STRUCTURELLE
complementaire pour PutridExplosion : `deathPutrifier` est **`Resilient`** — hors overkill,
`ApplyResilientTraitDamageLimit @18102c3a0` cape le degat a `curHP-1` : s'il meurt d'un coup, le coup
ETAIT un overkill.

### Non-regression rejouee

| suite | resultat |
|---|---|
| `test_finaljustice_live` + `test_ambush_migration_live` + `test_tainted_narthecium_revive_live` (les 3 vecteurs de mort existants) | **15/15 pass** |
| `test_harbinger_of_destruction_live` + `test_vigilance_eternal_live` + `test_damage_crit_live` (famille ability + crit) | **10/10 pass** |
| `test_env_fire_tile_migration_live` (route `"direct"` de `AttackWithAbilityDamage`) | pass |
| `test_damage_ability_live` | pass |

L'ajout de `On(2)` ne peut deplacer AUCUN trigger existant : aucun autre consommateur n'ecoute
l'event 2, et un dispatch sans match ne consomme AUCUN tirage RNG -> bit-exactness preservee.

## 5. Ce qui n'est PAS couvert (residus honnetes)

1. **Bonus RammingSpeed (+50%)** : porte STRUCTURELLEMENT (`ConditionalAmount(HasEffect(Self, 1098))`)
   mais **branche MORTE** — (a) aucune unite du gameconfig (lineup/npc/summons) ne porte l'ability
   `RammingSpeed`, donc personne ne peut poser l'effet 1098 ; (b) `ctx.has_effect` n'est pas cable par
   `entities_from_state` -> `HasEffect` rend False. Non confrontable live : mirror + branche inerte,
   AUCUN scenario invente.
2. **Gate `Steppable` de PutridExplosion** : aucun porteur `Steppable` en gameconfig -> valide par
   TOGGLE OFFLINE du set de traits (test 5), pas live.
3. **Tirage de BLOCK dans la nova** : le block EST tire dans la famille ABILITY (PROUVE live : un Titus
   a encaisse **0** d'une nova de 75) et le port le modelise. Mais le rejeu offline part d'un RNG cale
   AVANT le coup letal alors que le natif a deja consomme des tirages -> l'ISSUE du tirage n'est pas
   comparable dans ce protocole. Les scenarios neutralisent donc le block (`--block-target 0,0` +
   tueur sans `BeastSlayer_ExtraBlock`) pour mesurer l'etage DEGAT. Le modele de block reste couvert
   par les tests block dedies.
4. ~~**Garde `@0x180e76c9e` entre `On(1)` et `On(2)`**~~ — **RESOLU (#88/#89)** : c'est le `hasValue` du
   `Nullable<ReviveData>` @`UnitComponent+0xa8` ⇒ un revive sur `On(1)` **annule** la nova `On(2)`.
   Porte + valide live (cf. §2.1 et `case-66-revive-in-place` §7).
5. **Arrondi `round_materialize`** : corrige pour la famille ABILITY amount-mode SEULEMENT ;
   generalisation = chantier separe (cf. §3.1 + backlog).
6. **`RefreshDynamicStatModifierValueBehaviour`** : STRUCTURAL NO-OP cote port.
7. **Face DECISION** : les ids 1021/1074 sont dans le kit declenche, mais aucun playbook natif
   n'existe pour eux -> aucune utilite AI n'en decoule (conforme au jeu).
