# Case — les 3 abilities MoW a PREDICAT DE CIBLAGE conditionnel (tache #90 lot A)

**Statut** : LIVRE. Les 3 abilities sont PORTEES (face COMBAT) et CONFRONTEES LIVE (7 tests,
`tests/engine/runner/test_mow_targeting_predicate_live.py`). Build `gqfc5mff6c`, session Frida 71.
Correctif 100 % Python (`scripts/python/**`) — aucun changement `frida/hooks`, aucun reinject.

Prerequis : le debloqueur `case-mow-offboard-cast` (la MACHINE OF WAR est une entite ECS offline,
`MachineComponent` / `_load_machines`). Ces 3 abilities y etaient listees « 0 cible au spawn »
(§5) : **ce n'etait pas un defaut de harnais**, mais un PREDICAT DE CIBLAGE natif conditionne par la
configuration du plateau. Ce case le RE, le monte, et porte l'execution.

---

## 1. Les 3 predicats (decompile = verite)

| ability (id, porteur MoW) | fonction native | predicat |
|---|---|---|
| `SquigLaunchas` (1200, `orksRukkatrukk`) | `GetDynamicInvalidTargetReason` **@18120ab80** | `HasMinimumAdjacentOrks(0x78=nrOfUnits=1)` **OU** `HasMinimumAdjacentFriendlyUnits(0x79=nrOfUnits_2=2)` -> sinon reason **2** |
| `HadesAutocannons` (1147, `blackForgefiend`) | **aucun** `GetDynamicInvalidTargetReason` ; `TargetingOptions` du ctor **@1811e56b0** (`0x46006000`) + `GetAllTargets` **@1811e5480** (`UnitsWithTrait(..., 2=Summon)`) | la cible doit etre un **SUMMON** du camp adverse |
| `EntropyCannons` (1168, `deathCrawler`) | `GetDynamicInvalidTargetReason` **@1811bfc20** | `IsInTeamContagionsOfNurgleAura(target, caster)` **@180df3ea0** (effet **0x42f=1071** `ContagionsOfNurgle_ArmorReduction1`) **OU** (`comp+0x48 > 0` **ET** `HasNegativeModifier(target, 0x10=FixedArmor)` **@180df11e0**) |

### 1.1 `SquigLaunchasAbility` — deux helpers, DEUX jeux de seuils

```
HasMinimumAdjacentFriendlyUnits(n) @18120af30 =
    AmountIsEqualOrGreater( Friends( Owner@0x148,
                                     NonSteppableOrObjectUnits( AdjacentUnits(target@0x178, 1, 3) ) ),
                            n )
HasMinimumAdjacentOrks(n) @18120aff0 = idem + UnitsFromFaction(..., 5 = Orks)
```

- `Friends` a pour REFERENT l'**Owner** (= le caster MoW) : « friendly » = de MON camp.
- `NonSteppableOrObjectUnits` **@180df7420** = `src ∩ UnitsWithoutTrait(src, 0x1b=Steppable)
  ∩ UnitsWithoutTrait(src, 0xd=Object)` (un decoy ou un objet adjacent NE COMPTE PAS).
- `AmountIsEqualOrGreater.ShouldTrigger` **@180ee0e00** : slot +0x10 = selecteur **COMPTE**,
  +0x20 = seuil, `return seuil <= gauche` => `Count(sel) >= n`.
- **CIBLAGE** : 0x78 `nrOfUnits`=1 Ork / 0x79 `nrOfUnits_2`=2 allies.
  **SUMMON** (`FulfillsSummonCriteria` **@18120aac0**, `op_BitwiseOr` **@180ffb0a0**) :
  0x81 `nrOfUnits_3`=2 Orks / 0x82 `nrOfUnits_4`=4 allies. **Seuils DIFFERENTS** : une cible peut
  etre legale SANS que le Squig soit invoque — c'est le scenario discriminant du test.

### 1.2 `HadesAutocannonsAbility.GetAllTargets @1811e5480`

```
sel  = UnitsWithTrait( Friends( target@0x178,                                  # allies DE LA CIBLE
                                SurroundingUnits(target@0x178, GetNumberConstant(0x16)=range=2,
                                                 1, includeCenter=1, 3) ),
                       2 = Summon )
return If( AreEqual(CurrentPlayer, Player(1)),                                 # == IsTopPlayer @1811e5640
           SortByRow(Tiles(sel)), SortReverse(SortByRow(Tiles(sel))) )
```

- **Referent de `Friends` = la CIBLE**, pas le caster -> les summons du camp de la cible (= les
  summons ENNEMIS du caster). C'est le SEUL call-site porte ou le referent n'est pas le caster.
- **`includeCenter=1`** : `DSLFactory.SurroundingTiles @180dfca70` fait
  `SurroundingTiles(includeCenter=1) op_Subtraction Tiles(center)` quand son `param_3` vaut 0, et
  rend le selecteur DIRECT sinon -> ici la CIBLE elle-meme est dans l'ensemble (i2 : « a targeted
  enemy summon AND all other enemy summons within 2 hexes »).
- **`SortByRow`/`SortReverse` NON portes** : l'ordre du selecteur est ECRASE en aval par l'`OrderBy`
  qu'applique `AttackBehaviour.Execute` **@180fb91a0** des que le set a >= 2 cibles
  (`if (1 < count) OrderBy(<>c.b__5_0 @180fd9150)`, cle par-entite du slot vtable +0x158). Le port
  garde son tri par `id` (== tous les autres multi-cibles valides bit-exact). **HYPOTHESE explicite**
  (la cle +0x158 n'a pas ete relue) — discriminable avec >= 2 summons dont l'ordre de `row`
  contredit l'ordre d'`id`.

### 1.3 `EntropyCannonsAbility.GetDynamicInvalidTargetReason @1811bfc20`

`HasNegativeModifier.ShouldTrigger` **@180f9db90** itere le dictionnaire de modifications de la stat
filtree et rend vrai au 1er montant `< 0` (champ +0x14) dont le StatType (+0x10) est dans le filtre
(array a 1 element = `{16 = FixedArmor}`). Le port a DEJA ce mirror :
`UnitStats.has_negative_modifier` (`entities/stats.py`, porte pour `ConquerorImperative`).

---

## 2. Ce qui est PORTE (face COMBAT)

| ability | `ExecuteBehaviour` | port |
|---|---|---|
| 1168 `EntropyCannons` | **@1811bfa40** : `Execute(AttackWithAbilityDamage(caster@0x160, target@0x178, MinMaxDamage, Energy, GetHits=2, AbilityOrEffect(1168)))` | `deathguard.py::entropy_cannons_tree` |
| 1147 `HadesAutocannons` | **@1811e50e0** : `Execute( (ChangeStat(Owner, CriticalDamage=10, Add, extraCritDmg) + AttackWithAttackDamage(Owner, Units(GetAllTargets()), MinMaxDamage, Flame, GetHits=6, AbilityOrEffect(1147))) + ChangeStat(Owner, CriticalDamage, Subtract, extraCritDmg) )` | `blacklegion.py::hades_autocannons_tree` (+ `hades_autocannons_get_all_targets`) |
| 1200 `SquigLaunchas` | **@18120a720** : `Execute( (SetCache(cond) + AttackWithAbilityDamage(Owner, target, MinMaxDamage, Physical, GetHits=3, AbilityOrEffect(1200))) + If(cond, Spawn(caster, PickRandomly(CanAddUnit(AdjacentTiles(TargetTiles)),1), "orksSmnSquig", WithStatsFromConfig)) )` avec `cond = Cache(FulfillsSummonCriteria)` | `orks.py::squig_launchas_tree` (+ les 3 helpers homonymes) |

Points de fidelite notables :

- **FAMILLE de factory** (classifiee par XREF de chaque `ExecuteBehaviour`, jamais au nom) :
  1168 et 1200 appellent `DSLFactory.AttackWithAbilityDamage @180de9c90` (famille **ABILITY** :
  1 tirage/coup, AUCUN crit, aucune feuille positionnelle) ; 1147 appelle
  `AttackWithAttackDamage @180de9fb0` (famille **ATTACK** : crit actif — c'est ce que le buff
  `extraCritDmg` alimente).
- **TIMING du critere de summon** (1200) : `SetCacheBehaviour.Execute` **@180fd2470** evalue le nœud
  cache et rend un resultat VIDE (aucune mutation) — son SEUL effet est de FIGER le verdict AVANT
  l'attaque. Consequence mecanique : meme si les 3 coups tuent la cible, le Squig est invoque des lors
  que le critere etait rempli avant. Porte par `CacheTrigger` (`entities/triggers.py`) + `SetCache`
  (`entities/behaviours.py`), mirror des overloads `DSLFactory.Cache @180deb010` / `SetCache @180dfa8f0`.
- **1168 `is_melee=None`** : la config 1168 n'a **pas** d'`attackRangeType` (contraste 1147/1200 =
  `Ranged`) -> nature du coup NON declaree -> gates defenseur melee/ranged inertes (convention
  `execute_ability_attack(is_melee=None)`). Rien d'invente.
- **Buff crit 1147** : jumeau structurel de `HeroicFusilladeAbility @1811e8de0` (couple `ChangeStat`
  Add/Sub sur `CRIT_DAMAGE`, source PARTAGEE). INERTE tant que la `CritChance` de la MoW est 0
  (seed a 0, cf. residu `case-mow-offboard-cast` §8) mais porte 1:1.

### 2.1 Socle DSL etendu (mirror d'arguments natifs qui manquaient au port)

| nœud | changement | pourquoi |
|---|---|---|
| `Friends` (`entities/selectors.py`) | parametre `reference` (defaut = caster) | le referent est le **1er argument natif** de `DSLFactory.Friends @180df0040` ; Hades passe la CIBLE |
| `SurroundingUnits` | parametre `include_center` (defaut False) | mirror de `param_3` de `DSLFactory.SurroundingTiles @180dfca70` |
| `non_steppable_or_object_units` | nouvelle factory (composition pure) | mirror `DSLFactory.NonSteppableOrObjectUnits @180df7420` |
| `TriggerOr` (`entities/triggers.py`) | nouveau nœud | `AbilityTrigger.op_BitwiseOr @180ffb0a0` (201 call-sites natifs ; les disjonctions etaient recablees a la main dans les triggers imperatifs) |
| `CacheTrigger` / `SetCache` | nouveaux nœuds | overloads PREDICAT de `Cache @180deb010` + `SetCacheBehaviour @180fd2470` |

---

## 3. Bug de socle trouve par le port : `att_ctx` None pour un attaquant SANS POSITION

`damage_model.attacker_modifiers` faisait `att_ctx["trigger_ability_type"] = ...` sur le retour de
`_positional_att_ctx`, qui rend **None** quand l'attaquant n'a pas de `PositionComponent` — le cas
d'une MoW hors-plateau. `TypeError` au 1er attaquant de la famille ATTACK sans position
(HadesAutocannons). Corrige : `att_ctx = dict(att_ctx or {})` (le contexte natif porte l'ability
declenchante independamment de la position). Inerte pour tous les attaquants positionnes.

---

## 4. Etage d'ARRONDI de la famille ABILITY — residu RESOLU (mode bornes)

Le residu « `Fix64.Round` du multiplicateur non materialise quand la %-list est vide »
(`case-death-nova-explodes-putridexplosion` §3.1, `backlog`) etait corrige **uniquement** pour la
famille ABILITY *amount-mode*. Le port de `SquigLaunchas` (famille ABILITY **mode bornes**) l'a fait
resurgir, et la DECOMPOSITION PAR ETAGE l'a localise :

```
probe_mow_targeting_predicate.py decomp --stage   (cible astraBullgryn armure 3513, Physical pierce=1 %, 3 coups)
  seed 12345 : off 86 [28,29,29]   live 86    (+0)
  seed 4242  : off 87 [28,29,30]   live 89    (+2)
  seed 777   : off 91 [32,29,30]   live 93    (+2)
  seed 31337 : off 87 [29,30,28]   live 90    (+3)
```

L'ecart **VARIE dans [0, hits]** => signature d'un ARRONDI par coup (un additif systematique donnerait
`+hits` constant). `CalculateAbilityDamage @18102cb50` construit TOUJOURS le `Nullable<DamageModifiers>`
defenseur (slot 0xf) -> l'etage `Round(dmg x multiplier, AwayFromZero)` (`@1810021c0`, slot 0x10 de
`CalculateBaseDamageWithAllModifiers @18102d3f0`) passe TOUJOURS pour ce vecteur, **mode bornes
inclus**. Correctif : `execute_ability_attack` active `round_materialize` des que
`is_attack_damage_op=False`. **4/4 seeds bit-exact apres fix** (90/90, 86/86, 89/89, 93/93).

La famille ATTACK reste TRONQUANTE (chemins live-valides bit-exact ainsi) : chantier separe.

Non-regression rejouee sur les autres consommateurs famille ABILITY : `test_spirit_leech_combat_live`,
`test_death_nova_live`, `test_lord_of_tempests_ice_live`, `test_plasma_grenade_splash_live`,
`test_stikkbomb_migration_live`, `test_fragstorm_migration_live`, `test_scything_talons_migration_live`,
`test_damage_ability_live` — tous verts.

---

## 5. Validation live (7 tests, `test_mow_targeting_predicate_live.py`)

| test | ce qu'il prouve | mesure |
|---|---|---|
| `squig_launchas_one_ork_damage_no_summon` | 1 Ork adjacent = cible LEGALE, critere de summon FAUX | off 1954 == live 1954, 0 spawn des 2 cotes |
| `squig_launchas_two_orks_summons_squig` | 2 Orks adjacents = summon | off 1954 == live 1954 ; 1 Squig, meme team/PV, adjacent a la cible |
| `squig_launchas_non_ork_allies_branch` | 2e branche (allies NON-Orks) : ciblage OK a 2, summon KO a 3 (<4) | off 90 == live 90, 0 spawn |
| `hades_autocannons_hits_target_and_nearby_enemy_summons` | 0 cible tant qu'aucun summon ennemi ; puis SET = cible + summons ennemis <= 2 hex | `off_hit == live_hit == [71, 73]` |
| `hades_autocannons_range_excludes_far_summon` | borne `range`=2 (autre board `C2_02`, autre seed) | summon a 6 hex frappe par PERSONNE ; SET egal |
| `hades_autocannons_spares_friendly_summons` | referent `Friends` = la CIBLE (mes summons a <= 2 hex EPARGNES) | allie proche `66` absent des DEUX sets |
| `entropy_cannons_requires_contagion_aura_then_damages` | 0 cible sans aura ; ciblage ouvert par un porteur `ContagionsOfNurgle` allie adjacent ; degat mono-cible | off 1631 == live 1631, aucun degat hors-cible |

Mise en scene (drive-positions, jamais « bloque par la geometrie ») :
- **Squig** : l'ennemi est d'abord amene sur la tuile a MAXIMUM de voisins libres — sinon les Orks
  occupent les 2 seuls voisins et `CanAddUnit(AdjacentTiles(target))` est vide (le natif ne spawne
  alors PAS, ce qui masquerait le critere).
- **Hades** : on fait invoquer l'adversaire (`SpawnPoxwalkers` 1040 / `ScarabHive` 1007 castes via
  `applyAction`, qui ne verifie pas la propriete du caster) ; pour le test « friendly » les DEUX camps
  ont un `necroSpyder` et leurs swarms s'entremelent autour de la zone de contact.
- **Entropy** : `deathTyphus` (porteur du trait `ContagionsOfNurgle`) amene au contact de l'ennemi.

---

## 6. Ce qui n'est PAS couvert

- **2e branche d'`EntropyCannons`** (`HasNegativeModifier(FixedArmor)` sans aura) : non montee live
  (il faudrait un reducteur d'armure spawnable applique a la cible). Le mirror OFFLINE existe deja
  (`UnitStats.has_negative_modifier`), et la branche AURA est validee.
- **`SortByRow`/`SortReverse`/`IsTopPlayer` de `GetAllTargets`** : non portes (ecrases par l'`OrderBy`
  de `AttackBehaviour.Execute` — hypothese, cf. §1.2).
- **Confront NUMERIQUE par cible pour Hades** : les summons meurent (6 coups Flame >> leurs PV) ->
  le test confronte le SET frappe + l'issue par cible (mort/PV), pas une valeur intermediaire.
- **Buff `extraCritDmg` de 1147 non observable** : la `CritChance` d'une MoW est seedee a 0 (residu
  `case-mow-offboard-cast` §8, `combatSnapshot` filtre `EntityType.Unit`) -> aucun coup critique.
- **Face DECISION** des 3 abilities : hors perimetre (les MoW sont volontairement exclues de
  `decisionView.units`, `case-mow-offboard-cast` §4/§8).
- **`test_harvester_live` (2 cas) est ROUGE** — verifie sur base propre (patch stashe) : **echec
  PRE-EXISTANT** au commit `9eedcbc`, sans rapport avec ce lot (MAIN [2694,2896] vs LIVE [2155,2317],
  ratio 1.25 = HeavyWeapon). Consigne au backlog.
