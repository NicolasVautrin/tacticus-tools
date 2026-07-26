# Case — DoT de tuile `EnvFireTile` : migration de `execute_direct` vers `AbilityDamageOperation`

**Statut : RESOLU (2026-07-26).** Residu STRUCTUREL ouvert par `case-death-nova-explodes-putridexplosion`
§3. Il n'etait PAS latent : la route historique donnait un chiffre FAUX des que la cible portait un mod
defenseur ou un cap de trait — deux configurations courantes.

## 1. L'artefact natif

`IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour` (LU) :

```
Foreach( UnitsWithoutTraits([Steppable=0x1b, Immune=0x19]) & Units(EntitiesWithAnyEffect(Fire=5)),
         AttackWithAbilityDamage( Tiles(@0x180),                       # param_2
                                  @0x180,                              # param_3
                                  PercentageOf(StatAmount(@0x180, Health=5, Max=2),
                                               ConfigConst(0x12=fireDmgPct)),   # param_4 = amount
                                  AbilityOrEffect(Fire=5),             # param_5
                                  { 0, Direct(Nullable(3)), 0, 0 } ) ) # param_6
```

`IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` construit **`IdunBattle.Entities.
Behaviours.AbilityDamageBehaviour$$.ctor` + `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor`**
et rend l'`AttackBehaviour`. Il n'y a **AUCUN** `IdunBattle.Operations.DirectDamageOperation` sur ce
chemin : la famille est ABILITY (`IdunBattle.Operations.AbilityDamageOperation` ->
`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`).

Trois lectures qui tranchent des points restes ouverts :

1. **Qui est le caster.** `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` resout son champ
   **+0x50 en UNE entite** (`SelectOne`, `return` si nul) et son champ **+0x58 en une LISTE** (puis
   `OrderBy` si count > 1). La factory ecrit `param_2 -> +0x50` et `param_3 -> +0x58` ; le DoT passe
   `(Tiles(occupant), occupant)`. Donc **caster = la TUILE**, cibles = l'occupant. C'est deja ce que
   le port faisait (`entities.caster` = `owner_id`), mais la consequence n'avait pas ete tiree : le
   caster d'un `AbilityDamageOperation` n'est pas forcement une UNITE.

2. **Ce qu'est `Direct(Nullable(3))`.** `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$
   GetDamageProfile` est exactement `if (this+0x90) return eval(this+0x90, entities); return 0;` — et
   le ctor ecrit `param_6[1] -> +0x90`. Le `Direct(Nullable(3))` **EST le noeud DAMAGE PROFILE**, et
   `3` = `DamageProfileType.Flame`. Le port utilisait `"Flame"`, mais **par deduction** (le perçage
   mesure valait 25 % = `Flame.PiercingRatio`) ; c'est desormais une LECTURE. Les champs voisins
   `+0x98` (nrOfHits, defaut 1) et `+0xa0` (ability id) sont NULS pour le feu.
   L'ancienne note « le 3 n'est pas RE'd et reste INERTE » est **caduque** : ce profil pilote les
   gates `DamageProfileIs` des mods defenseur (cf. §3).

3. **Pas de comptabilite d'attaque.** Le corps d'`IdunBattle.Operations.AbilityDamageOperation$$
   Execute` (boucle `ExecuteHits` + chain + `IdunBattle.Operations.ADamageOperation$$
   RegisterFinalDamage`) n'enqueue JAMAIS `IdunBattle.Operations.RegisterAttackOperation`, seul
   appelant de `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterAttackReceived`.
   La famille ABILITY n'incremente donc pas `HasBeenAttackedAmountThisTurn`.

## 2. Ce que la route historique ratait

`AttackDamageOperation.execute_direct` mirrore `IdunBattle.Core.Services.DamagePrediction$$
CalculateDirectDamage` : perçage/armure SEULS, `mods=None`, aucun etage limites hors member-cap.
Manquaient donc, pour le DoT de tuile : mods DEFENSEUR, block, bouclier, cap `Resilient`,
materialisation d'arrondi.

## 3. Les mesures (runner isole, board MC1_67, ennemi JAMAIS active)

Montage commun : `--p-units adeptRetributor` (arme `hits=4 DamageProfile=Flame Range=2` -> son
attaque normale POSE le feu via `OnFireDamageAbility`) contre une a-unit unique, `--hp-target 500000`
(Health = RemainingHealth = 500000 **et armure forcee a 0**) -> `dot = 20 % de PVmax = 100000`. Le
tour ennemi est passe par `endturn` : les seules mutations de PV entre deux de mes tours sont les
ticks de debut de tour. Probe : `scripts/python/probe_envfire_resilient_cap.py`.

| cible | trait | hp avant tick | **tick NATIF** | port legacy (`execute_direct`) | verdict |
|---|---|---|---|---|---|
| `darkaTerminator` | `TerminatorArmour` | 473240 | **25000** | 100000 | mods defenseur x0.25 APPLIQUES |
| `astraYarrick` | `Resilient` | 62076 | **62075 = hp-1**, survit a 1 PV | 100000 -> **MORTE** | cap `ApplyResilientTraitDamageLimit` APPLIQUE |
| `astraBullgryn` (TEMOIN) | aucun | 61362 | **MORTE** | MORTE | montage valide : c'est bien `Resilient` qui sauve |

Le couple Yarrick / Bullgryn est le controle : montage STRICTEMENT identique, une seule variable (le
trait), resultats opposes. La fenetre discriminante du cap est `(dot/2, dot]` — au-dela,
`IdunBattle.Core.Services.DamagePrediction$$IsOverkill` (seuil `overkillDmgPctOfHealth` = 100)
BYPASSE le cap ; a `hp == 1` le gate `max_health > 1` le desarme aussi.

Reproduction (2 seeds) du cap Resilient : 90101 (hp 61903 -> 1) et 90103 (hp 62076 -> 1). La tuile
est verifiee EN FEU au moment du tick via le RPC `tileMeta` (`remaining=2`).

## 4. Le port

- `runner/operations/triggers/loki/fire.py::env_fire_tile_tree` : `native_operation="ability"` et
  **`is_melee=None`**. L'`AbilityOrEffect` du coup est l'EFFET `Fire(5)`, pas une ability a
  `attackRangeType` -> `IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType` rend 0, donc
  `IsMeleeAttack` ET `IsRangedAttack` sont FAUX (table de verite de `hits_channel_is_melee`). Les
  malus defenseur gates `IsMeleeAttack` (`Terrifying_ExtraDefense`) restent inertes, comme le natif.
  Le perçage est inchange (`profile_pierce(ctx=None, ...)` ignore `ranged`).
- `runner/operations/damage_ops.py::execute_ability_attack` — trois ajustements, tous gates de sorte
  que **les appelants historiques sont strictement inchanges** :
  1. **caster NON-UNITE toleré** : `sc is None` (entite TUILE, absente de `State.entities`) ->
     mods attaquant VIDES + crit 0, au lieu de `return None`. C'est ce que `CalculateAbilityDamage`
     recoit de toute facon pour la famille ABILITY (struct zeroee, mesure #45f). On NE passe PAS par
     `attacker_modifiers`, dont la collecte `state.effects.active_effects(<id de tuile>)` rendrait
     les effets DE LA TUILE (le FEU lui-meme) comme des effets d'ATTAQUANT.
  2. **`is_attack` gate par famille** : `_apply_damage_pipeline(..., is_attack=is_attack_damage_op)`
     — cf. §1.3. Sans ce gate, un tick de DoT compterait comme une attaque recue (plancher PV
     Hypersensory, MoveAndSpawnDecoy, formule `TimesReceivedAttackedThisTurn`).
  3. **garde-fou `rng` raffine** (ce n'est PAS un mirror natif) : le vecteur ne tire que si les
     bornes sont non degenerees, qu'un crit est possible, qu'une source de block existe, ou que le
     resolve slot-8 de la famille ATTACK tourne. Un DoT de tuile est 0-tirage ; le skipper aurait
     rendu la feuille NO-OP hors runner. `hp_after` est ajoute au retour (purement additif).
- `runner/abilities/behaviours/context.py::entities_from_state` — **deux bugs de la slice-19 fermes** :
  1. **caster TUILE materialise.** `caster` n'etait cherche que dans `state.entities` (unites/MoW) :
     pour un `TileEffectTrigger` il restait `None`, donc `AttackWithAbilityDamage.execute` sortait sur
     `src is None` — **le DoT de tuile etait un NO-OP SILENCIEUX**. On materialise un caster minimal
     porteur du seul `id`. Il n'entre PAS dans `units` (le natif non plus ne met pas la tuile dans la
     liste d'unites de l'`AbilityEntities`), donc aucun selecteur ne peut le ramasser.
  2. **`HEALTH` est une stat « fill-up ».** `IdunBattle.Entities.UnitExtensions$$GetStat` route la PV
     sur un `FillUpStatComponent` (+0x10 = maximum, +0x18 = courant) et delegue a
     `IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart` — exactement comme
     `NUMBER_OF_MEMBERS`, deja traite. Le port passait par le `StatComponent` generique, dont
     l'`initial` est la PV COURANTE captee : **`StatAmount(x, HEALTH, Maximum)` rendait la PV
     COURANTE des que l'unite etait blessee.** MESURE : DoT sur `darkaTerminator` a 473240/500000 ->
     base offline 94648 (= 20 % de 473240) au lieu de 100000, tick natif 25000. Corrige pour les 5
     parts. Beneficiaire collateral : `living_metal.py` (meme patron `PercentageOf(StatAmount(self,
     HEALTH, MAXIMUM), pct)`).

## 5. Validation

- `tests/engine/runner/test_env_fire_tile_migration_live.py` — REECRIT (3 tests, tous verts). Son
  ancienne raison d'etre (« la feuille DSL reproduit l'ancien corps imperatif ») etait caduque, et il
  masquait le bug du caster-tuile en passant une UNITE comme source.
  1. `..._applies_defender_modifiers_live` : cible `TerminatorArmour` — le port doit predire le tick
     natif ET differer de la valeur legacy (l'assertion `native != legacy` interdit un montage non
     discriminant qui passerait « par accident »).
  2. `..._applies_resilient_cap_live` : cible `Resilient` pilotee jusque dans la fenetre — survie a
     1 PV + egalite port/natif.
  3. `..._unchanged_on_neutral_targets` : NON-REGRESSION property-based sur les cibles sans mod ni
     cap ni bouclier.
- Gardes rejouees, toutes vertes : `test_death_nova_live`, `test_on_fire_damage_migration_live`,
  `test_fire_of_absolution_migration_live`, `test_load_state_tile_effects_live`,
  `test_arcaneshield_live`, `test_anvil_shield_stun_live` (`StatAmount(Self, HEALTH, CURRENT_PCT)`),
  `test_hypersensory_hpfloor_live` + `test_hypersensory_moveandspawndecoy_live` (consommateurs du
  compteur d'attaques recues).
- `test_hailstrike_phase2_live` : **2 echecs PRE-EXISTANTS**, verifies a l'identique sur l'arbre sans
  ces changements (`degat live 2700 hors des bornes [1688, 2532]`). Hors perimetre.

## 6. Ce qui n'est PAS couvert

- **L'arrondi `AwayFromZero`.** La route ABILITY materialise `Round(dmg x multiplier, AwayFromZero)`
  (`IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`, cf. §3.1 du case
  death-nova) la ou `execute_direct` faisait `int(round(...))` — donc un arrondi au PAIR en Python.
  Sur un demi-entier l'ecart est de +1 (mesure offline : `tauDarkstrider` base 1506 / armure 1707 ->
  376.5 ; legacy 376, nouveau 377). C'est l'ANCIENNE valeur qui etait fausse, mais **aucun montage
  live n'a pu l'exercer** : `--hp-target` force l'armure a 0, or sans armure le net vaut la base
  entiere (pas de demi-entier), et sans `--hp-target` la cible ne survit pas a une attaque de
  Vindicta. Le test de non-regression encode l'attendu `AwayFromZero`, adosse a la seule RE.
- **Bouclier et block sur un tick de feu** : desormais traverses par construction (meme Operation),
  jamais exerces live (aucune unite du pool n'a de `blockChance` de base ; les deux porteurs de
  bouclier — `spaceRockfist`/`AnvilShield`, `thousSorcerer`/`ArcaneShield` — exigent un montage ou
  le porteur bouclie est LUI-MEME sur une tuile en feu au tick, non monte ici).
- **Le gate `is_attack` sur les AUTRES consommateurs de la famille ABILITY** (Hailstrike,
  PutridExplosion) : fonde sur la lecture d'`AbilityDamageOperation$$Execute`, non mesure
  independamment. Leurs tests de garde passent.
