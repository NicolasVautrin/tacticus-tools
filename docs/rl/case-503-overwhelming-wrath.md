# #503 — `1141 OverwhelmingWrath` : le cast ARME, il ne frappe pas

Build `rnca9r7q6c`. Porteur lineup : `worldEightbound` (Azkor), pool rank 17. 1 porteur npc
(`worldBossEightboundLHE`). Face COMBAT **portée** (`runner/abilities/worldeaters.py`) ; face
DÉCISION (`IdunBattle.AI.Playbook.Loki.OverwhelmingWrathPlaybook`) hors périmètre.

## Le contre-résultat

`IdunBattleLogic.Entities.Abilities.Active.Loki.OverwhelmingWrathAbility$$ExecuteBehaviour` ne porte
**aucun** nœud d'attaque. Mirror 1:1 du décompilé :

```
AActiveAbility.Execute(
    op_Addition(
      op_Addition(
        AddEffect(     0x515 = 1301 OverwhelmingWrath_RangeDmgReduction, AbilityStateReference,
                       source = Caster@DSLSelectors+0x48, targets = Caster@+0x48,
                       TurnsFromRounds(1) ),
        AddBondEffect( 0x1b  = 27 Taunted_OnlySpecificTargets, AbilityStateReference,
                       source  = Caster@+0x48,
                       targets = NormalUnits( AdjacentEnemies(Owner@+0x30, unique:1, sel:3), sel:3 ),
                       bondedEntity = Caster@+0x48, TurnsFromRounds(1) ) ),
      AddBondEffect(   0x514 = 1300 OverwhelmingWrath_PendingAttack, AbilityStateReference,
                       source = Caster@+0x48, targets = Caster@+0x48,
                       bondedEntity = Caster@+0x48, options = <Nullable ZERO> ) ),
    entities )
```

Le `DAMAGE(Eviscerate)` de `combat-ability-coverage.md` est le profil du **kit**
(`constants: damageProfile=Eviscerate, nrOfHits=2` + `minDmg`/`maxDmg`[level]) : il appartient à la
**phase 2**,
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.OverwhelmingWrath_AttackAbility$$CreateBehaviour`
(`TriggeredAbilityType.OverwhelmingWrath_Attack` = 0x4d5 = 1237, rendu par
`IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_PendingAttackEffect$$GetTriggeredAbilityType`).
Même patron 2-phases que `HeavyRailRifle` (1160) et `SeekerMissileFrequencyLock` (1069).

i2 (`Abilities/OverwhelmingWrath_CurrentLevelDescription`) découpe l'ability exactement ainsi :
« Until the beginning of his next turn Azkor **Taunts all adjacent enemies** and **takes
-{dmgReductionPct}% Damage from ranged attacks**. **Deals {nrOfHits}x {minDmg}-{maxDmg} Eviscerating
Damage to all adjacent enemies at the beginning of Azkor's next turn.** » — les deux premières
phrases sont l'ACTIVE (portée ici), la troisième est la phase 2.

## Le PARTAGE des quatre mécaniques du kit

Le profil kit annonce `dmg_bonus`, `dmg_reduction`, `crit`, `block`. Elles ne sont pas toutes
lisibles depuis l'`ExecuteBehaviour`, et le savoir se **mesure** :

| mécanique | où elle vit | confrontée |
|---|---|---|
| `dmg_reduction` | `AddEffect(1301)` du cast | **OUI** — étage [5] du probe : la prédiction NATIVE d'une attaque RANGED ennemie sur Azkor passe de `(2006, 3010)` à `(722, 1084)`, soit `x(100 − 64)/100` (encadrement, pas reconstitution d'arrondi) |
| `crit`, `block`, `dmg_bonus` | phase 2 (triggered 1237) | **INATTEIGNABLES depuis ce behaviour, MESURÉ** — cf. ci-dessous |

Le critère n'est pas « aucun dégât observé » mais « aucun dégât **et** flux MT strictement
identique » : un jet de crit ou de block **consomme** un tirage
(`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`). Mesure, régime nominal **et** régime
`--crit 100,700 --crit-target 100,700 --block-target 100,500 --block-player 100,500` (contre-épreuve
G4) : HP inchangés des deux côtés, `dumpRng` = `(callCount 0, mti 624, même état interne)` avant
**et** après, `call_count` offline `0 → 0` sur un MT **calé sur le live**. Un cast qui ne tire rien
ne peut ni critiquer ni être bloqué.

## Les deux slots de rôle, RE-DÉRIVÉS sur ce build

`Selectors+0x48` = **Caster**, `Selectors+0x30` = **Owner**. Ce n'est pas hérité d'une case-doc :

* `IdunBattleLogic.Entities.Abilities.Active.Loki.MomentShackleAbility$$ExecuteBehaviour` (relu ici)
  passe `+0x48` à `DSLBehaviors$$Heal` et à `DSLFormulas$$StatAmount` — que `case-231` avait lus
  `caster@0x160` — et `+0x30` aux deux `AddDynamicStatModifierEffect` + à l'`AddEffect(0x571)` — que
  `case-231` avait lus `owner@0x148` ;
* `IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$GetPossibleMovementTiles`
  passe `+0x48`, `+0x50`, `+0x78` aux paramètres **nommés** `caster`, `casterTiles`, `target` de
  `DSLSelectors$$TilesUnitCanMoveToChargeTarget` ;
* `IdunBattleLogic.Entities.Abilities.Active.TauntAbility$$AdjacentEnemies` = `Enemies(of = +0x48,
  AdjacentUnits(+0x50, 1, 3), 3)`.

⚠ **Ces classes de sélecteur ne sont PAS nommables offline** : leur `.ctor(state)` est un corps
trivial que IL2CPP **déduplique**, donc `frida/methods.tsv` n'en publie qu'un seul propriétaire
(`AbilitiesDatabase..ctor`) — « l'absence dans les tables ne prouve rien », version *ctor*.

Sur une ACTIVE, `Owner` et `Caster` désignent la même unité (le port ne matérialise pas de sélecteur
`Owner` distinct, convention actée `case-224`) : l'écart de slot est **sans effet** ici, et il est
écrit pour rester greppable.

## `NormalUnits` — un nœud natif neuf

`IdunBattleLogic.Entities.DSLSelectors$$NormalUnits(entities, selectionType)` (mirror
`engine/entities/selectors/units.py::NormalUnits`) :

```
u = Units(entities, unique: true, selectionType)     # UnitsOnTilesSelector
t = DSLTriggers.IsNormalUnit(It@DSLSelectors+0x68)   # IsNormalUnitTrigger
return FromTrigger(u, t, requireContinuous: false)
```

et `IdunBattle.Entities.UnitExtensions$$IsNormalUnit` = `!HasTrait(0xd = Object) &&
!HasTrait(0x1b = Steppable)`. **Même prédicat que `non_steppable_or_object_units`, pas le même
nœud natif** (celui-là compose deux `UnitsWithoutTrait` + `op_BitwiseAnd`) : on garde les deux
distincts pour que le site se re-greppe contre son symbole.

`AdjacentEnemies(unit, unique, selectionType)` natif =
`Enemies( of: unit, Units(AdjacentTiles(unit), unique, sel) − unit, sel )` : **la référence d'équipe
est le 1er argument**, pas un caster implicite. Le sélecteur porté filtre sur `ctx.caster.team` —
identique tant que le centre EST le caster, ce qui est le cas ici (contre-épreuve G3 : un allié
collé au caster n'est PAS taunté).

## Le masque de ciblage — forme FLAGS DIRECTS, et un `isSelfCasting` qui n'est pas ce qu'il dit

`...OverwhelmingWrathAbility$$.ctor` recopie les 24 octets du champ statique
`<TargetingRange statics>+0x30` dans un local puis appelle la surcharge **flags directs** :

```
TargetingOptions..ctor(&opts, isSelfCasting = 1, range = <TargetingRange statics+0x30>,
                       forceMeleeTarget = 1, rules = 0x4000, 0, 0)
AActiveAbility..ctor(this, &opts, 2)          # 3e argument = AbilityAttackType.Others
```

soit `rules = TargetIsEnemy`, `range = RANGE_ADJACENT` (`onlyAdjacent = RangedBool.True`,
`overrideRange = 1`), `forceMeleeTarget = RangedBool.False`. Ces quatre valeurs **migrent** depuis
`TARGETING_OPTIONS_UNPORTED[1141]` (contrat de disjonction) après relecture au décompilé :
bit-identiques.

⚠ **`isSelfCasting = 1` ne veut PAS dire « castable à vide ».** Mesuré (contre-épreuve G1) : sans
aucun ennemi adjacent, `abilityTargets.fromHere` est **VIDE** et
`abilityReason(caster, 1141, caster)` rend **`0x800 AddCasterIfAtLeastOneTarget`**. Le caster
n'entre dans les cibles légales que s'il existe au moins une **autre** cible — c'est la branche
`else` de `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason`, qui appelle
`TargetingQuery$$GetValidTargets`. Le port rend `0` : **écart PERMISSIF ANTÉRIEUR (#447)**, déjà
nommé et mesuré sur `1226 Chronometron` dans la docstring de `get_caster_not_added_reason` ; #503
le re-mesure sur un **deuxième** porteur. Corollaire : le régime « cast LÉGAL avec un taunt VIDE »
est **nativement inatteignable**.

## Ce qui est porté

| Fichier | Contenu |
|---|---|
| `engine/entities/selectors/units.py` | `NormalUnits` (**neuf**) + son re-export dans `selectors/__init__.py` |
| `engine/runner/abilities/worldeaters.py` | `overwhelming_wrath_tree()` + `OverwhelmingWrathAbility` (`TARGETING_OPTIONS` posées) |
| `engine/runner/abilities/handler.py` | entrée `ABILITY_CLASSES[1141]` |
| `engine/runner/abilities/attack_type.py` | `ABILITY_ATTACK_TYPE[1141] = Others` (littéral du ctor) |
| `engine/runner/abilities/targeting.py` | ligne 1141 **retirée** de `TARGETING_OPTIONS_UNPORTED` + compteurs du bloc RE-COMPTÉS |
| `tests/engine/test_270r1_volet2_dict_keys_enum_offline.py` | snapshot **31**, cardinalités **115** — RE-COMPTÉES après le 2ᵉ rebase, union des retraits #503 + #504 |
| `tests/engine/test_433_r4_r2_r1_r2_ability_range_offline.py` | 1141 hors de `POOL_ABILITIES_WITHOUT_COMBAT_CLASS` + ligne-journal |
| `probe_503_overwhelming_wrath.py` | la MESURE (9 étages) |
| `probe_503_generalisation.py` | les 6 contre-épreuves |
| `tests/engine/runner/test_overwhelming_wrath_live.py` | la GARDE (10 tests) |

Déjà présent avant cette tranche : l'effet `1301` (`entities/effects/loki/damage_reduction.py::
OverwhelmingWrathRangeDmgReductionEffect`, #190) et l'effet `27` (`entities/effects/loki/status.py::
TauntedEffect`, #436) — c'est la **pose** qui manquait, donc les deux étaient inertes pour 1141.

## Le compteur périmé du bloc `TARGETING_OPTIONS_UNPORTED` — **trois** fois de suite

1. **Avant tout rebase**, le commentaire annonçait « 31 entrées ici » et « 5 / 1 / 12 » pour les
   trois autres surcharges. Re-compte mécanique : **33** dans le bloc POOL — périmé de 2 — et la
   ventilation ne correspondait à aucune section.
2. **Après le 1ᵉʳ rebase** (`origin/master` avait fait sortir 1019 #499, 1038 #500, 1165 #501,
   1064 #502), la version amont annonçait « 31 écrites, 10 / 4 / 1 / 16 » sur un arbre qui en
   portait **29**. Ma propre rédaction pré-rebase (« 32 ») était périmée au moment du merge.
3. **Après le 2ᵉ rebase** (#504 `1132 KillMaimBurn` a atterri pendant la validation), mon « 28 »
   l'était à son tour : #504 avait retiré 1132 de la section STATIC-COPY.

Compte **RE-DÉRIVÉ après la dernière résolution** : **27** entrées dans le bloc (`9 / 4 / 1 / 5` en
1ʳᵉ région, `3 / 1 / 4` en 2ᵉ), **4** hors-bloc en tête de table, **31** dans le dict entier
(`len(TARGETING_OPTIONS_UNPORTED)` — la seule mesure qui ne dépende d'aucun découpage). C'est
exactement le piège que le brief nomme : **re-compter, jamais soustraire du chiffre écrit**.

## Le croisement avec #504 — deux listes où `--ours`/`--theirs` aurait ressuscité une entrée

#503 et #504 touchent les mêmes cinq fichiers, et **deux d'entre eux sont des listes dont chaque
tranche ne retire que SON id** : `SNAP_TARGETING_UNPORTED` (1141 vs 1132) et
`POOL_ABILITIES_WITHOUT_COMBAT_CLASS` (idem). Prendre un côté entier y aurait **remis** l'entrée de
l'autre — et le test serait resté **VERT** des deux côtés pris isolément. La résolution est
l'**UNION des retraits**, puis un **re-compte** (`31`, `115`), jamais une soustraction.

⚠ Vérifié mécaniquement, pas supposé : #504 a changé la sémantique du foyer partagé
`engine/entities/behaviours.py::Group` (le sélecteur de groupe est désormais **évalué** avant le
child). Un walker complet de l'arbre de 1141 (`__slots__` **et** `__dict__`, 15 nœuds visités) rend
`{Seq, AddEffect, AddBondEffect, NormalUnits, AdjacentEnemies, Owner, Caster, Const}` et **0
`Group`** — le changement ne concerne donc pas ce port. Le premier walker n'avait visité que 6
nœuds (il suivait les seuls `__slots__`, et `AdjacentEnemies` n'en a pas) : un recenseur qui ne
visite pas ne peut pas rendre zéro.

## Validation

`probe_503_overwhelming_wrath.py` — **PROBE OK**, 9 étages, tous non dégénérés :

| étage | résultat |
|---|---|
| [1] exécution portée | `routed=handler ported=True`, cast natif sans erreur |
| [2] empreinte d'effets | port == natif : `{caster: {1301:2, 1300:0}, adj1: {27:2, 25:2, 26:2, 1237:2}, adj2: idem}` |
| [3] porteurs + bonds | 27 bondé au caster sur **les deux** adjacents, 1300 bondé au caster ; l'ennemi non adjacent **intact** ; bonds publiés par la cascade native et **identiques** |
| [4] 0 dégât 0 tirage | HP inchangés, MT figé des deux côtés (MT offline **calé** sur `dumpRng`) |
| [5] `dmg_reduction` | prédiction native `(2006, 3010) → (722, 1084)`, `x0.36` encadré, `pct=64 > 0` et la valeur **bouge** |
| [6] taunt opposable | `GetOnlyTargets` port = `{adj1:[caster], adj2:[caster], ranged:[]}` ; matrice `abilityReason` : l'allié sort des cibles des **deux** taunté(e)s sur le bit 23, le témoin non taunté ne perd rien, port == natif sur les 6 paires |
| [7] gate de ciblage | soi `0`, alliés `0x4000 TargetIsEnemy`, adjacents `0`, ennemi à distance 2 `0x8000000 TargetIsInRange` — **port == natif sur les 5** |

`probe_503_generalisation.py` — **PROBE OK**, 6 contre-épreuves :

* **G1** sélecteur VIDE → le natif REFUSE (`0x800`), l'arbre du port ne fabrique **aucun** taunt
  fantôme et ne perd **aucune** des deux poses self ; écart de gate = résidu #447, nommé.
* **G2** cast sur SOI vs cast sur un ENNEMI, mêmes montages → **empreintes strictement identiques**
  des deux côtés : l'arbre ne lit `Target()` nulle part (c'est la seule contre-épreuve où un port
  ayant glissé `Target()` diverge).
* **G3** allié ADJACENT au caster → épargné ; seuls les deux ennemis sont taunté(e)s.
* **G4** crit **et** block forcés à 100 → 0 dégât, MT figé : `crit`/`block` inatteignables, mesuré.
* **G5** autre board (`C1_02`) → accord port/natif identique.
* **G6** trait `Steppable` / `Object` greffé sur un adjacent → il **sort** du set taunté.
  **OFFLINE PUR, sans oracle natif** (résidu #503-r2).

`tests/engine/runner/test_overwhelming_wrath_live.py` — **10 passed**.

**Cliquets rejoués APRÈS le 2ᵉ rebase** (`origin/master` a pris 5 commits pendant la tranche, dont
#504 sur le même module) : `test_targeting_options_sources`,
`test_270r1_volet2_dict_keys_enum_offline`, `test_433_r4_r2_r1_r2_ability_range_offline`,
`test_366_r1_stormboyz_strike_offline`, `test_287r4_targeting_needs_instance_offline`,
`test_486r12_declencheurs_offline`, `test_486r15_empreinte_par_entree_offline` — **140 passed** ;
`test_ability_registry_ratchet` — **9 passed** ;
`probe_181_targeting_gaps` (**117/117**, 0 manquante) ;
`probe_120_pre_unit_ability_fork` étape 0 (« littéral de ctor manquant : aucun ») ;
`probe_433_r1_identity_shortcircuit` (rc 0), `probe_365_versioned_imports_gitignored` (rc 0),
`probe_273_gitignored_inputs --only-scan` (rc 0).

**Le VOISIN de module reste vert** : `test_504_kill_maim_burn_live` (**7 passed**),
`test_362_kill_maim_burn_nc_live` (**10 passed**) — les deux gardes de `1132 KillMaimBurn`, qui vit
dans le même `worldeaters.py`. Et les deux consommateurs de l'effet 27 :
`test_damage_crushingclaws_live` (1 passed), `test_taunt_targeting_live` (7 passed).

⚠ **Un cliquet a mordu, et c'était juste** : la première version du test déclarait
`TARGET_IS_ALLOWED_FOR_CASTER = 0x800000` en dur —
`test_ability_registry_ratchet::test_aucune_constante_de_ciblage_declaree_hors_du_module_genere`
l'a refusé. Corrigé : la constante vient du **membre** `TargetingRule.TargetIsAllowedForCaster` du
mirror généré, dans le probe comme dans le test.

**Deux rouges de la banque, PROUVÉS ANTÉRIEURS** (rejoués sur `origin/master` NU, HEAD détaché) :
`test_murderous_swing_live.py::test_murderous_swing_count_is_reevaluated_per_target` (1 failed,
message identique) et `test_jakhal_stimms_live.py` (3 skipped / 0 passed, rc 1 — le garde #455 ;
skip de montage `crit_chance=26 != 0`). Aucun des deux n'est imputable à cette tranche, et les
deux touchent pourtant `worldeaters.py`. Verts sur le même module : `test_damage_crushingclaws_live`
(1 passed) et `test_taunt_targeting_live` (7 passed) — les deux consommateurs de l'effet 27.

## Résidus

* **#503-r1** — la **phase 2** n'est pas portée :
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.OverwhelmingWrath_AttackAbility$$CreateBehaviour`
  = `AttackWithAttackDamage( caster = Caster@+0x48, target = AdjacentEnemies(Caster@+0x48, 1, 3),
  amount = BaseTriggeredAbility$$MinMaxDamage(abilityState),
  damageProfile = Nullable(GetDamageProfileOrDefault(0x14)),
  hits = GetNumberConstant(0x2f = nrOfHits) = 2, AbilityOrEffect(...), options ZERO,
  selectionType = 2 )`. Elle est armée par l'effet `1300` (posé par cette tranche) et déclenchée au
  début du tour suivant du porteur. Tant qu'elle n'est pas portée, `1300` est un **marqueur inerte**
  côté port — ce qui est exactement sa nature côté natif jusqu'au tour suivant. Même statut que la
  phase 2 de 1069 (#491-r1) et de 1160.
* **#503-r2** — le filtre `IsNormalUnit` de `NormalUnits` n'a **aucun oracle natif** : les 24
  porteurs `Steppable`/`Object` du gameconfig sont des `npc` (LootObj / powup / `genesDecoy` /
  `astarNpc1HaywireMine`) et deux summons (`genesSmnDecoy`, `astarSmnHaywireMine`) qui n'arrivent en
  bataille que par le cast de leur invocateur — donc aucun n'est spawnable **comme ennemi** par
  `rl_duel build`. G6 le mesure OFFLINE (greffe du trait sur `ctx.traits`, le substrat que lit
  `UnitsWithoutTrait`), et le dit. Montage qui le fermerait : `genesIsaak` côté adverse, tour IA
  ennemi pour caster `1179 CultDemagogue` (décoys `genesSmnDecoy`), puis déplacer Azkor au contact
  d'un décoy.
