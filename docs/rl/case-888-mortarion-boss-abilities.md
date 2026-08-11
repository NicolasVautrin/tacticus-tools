# #888 — Les trois actives de `deathBossMortarion` (GUILD BOSS)

RE + port COMBAT de `1093 MortarionsPlagueWind` et `1095 ReapingScythe` (**portées, confrontées
LIVE**) ; RE complète de `1094 TheLantern` (**NON portée**, résidu `#888-r1`).

Décompilé relu sur le build `rnca9r7q6c`. Board de confrontation : **`GB_Mortarion_05`**, la carte
que `battles/campaigns/*/battles[]` associe au boss (7×10, 64 tuiles jouables).

---

## 0. Le porteur, et ce que le montage a coûté

`deathBossMortarion` est `kind = npc`. Il se monte, et la recette tient en une ligne :

```
python scripts/python/rl_duel.py build --board GB_Mortarion_05 --seed 777 \
       --state-file <abs, hors data/> \
       --explicit-stats "deathBossMortarion:4" --p-units "deathBossMortarion:4"
```

`:4` = `units.npc[].stats[3]` (le palier haut) : `Health 128552`, `Damage 2630`,
`FixedArmor 8002`, `AbilityLevel 55`, `AbilityVariablesMultiplier 200 %`.

Trois faits de montage, tous MESURÉS :

* **Le garde de roster crie à tort.** Le jeu publie le boss sous l'id d'entité **remappé**
  `GuildBoss5Boss1DeathMortarion` ; `rl_duel build` compare les deux chaînes, conclut
  `roster NON MONTE ... demande x1 mais MONTE x0` et sort en `rc != 0` — **alors que le boss EST en
  bataille**. `TACTICUS_ALLOW_ROSTER_DEFICIT=1` lève le refus. Ne rien conclure de ce message.
* **Le boss BOUGE.** La supposition « les boss arrivent en `moveNone` » est fausse sur ce montage :
  `decisionView` lui rend `+move[2]` et les `move` du harnais l'ont effectivement déplacé.
* **Le boss porte `BigTarget`** (kit gameconfig : `Boss, Immune, ContagionsOfNurgle, Daemon,
  Flying, Psyker, BigTarget`) — mais `BigTarget` n'a rien à voir avec l'empreinte : c'est le
  3ᵉ trait que refuse `IdunBattle.Entities.UnitExtensions$$IsDisplaceable`.

### EMPREINTE — la mesure demandée, et ce qu'elle ne prouve PAS

`decisionView.units[].feet` sur `GB_Mortarion_05`, boss monté au palier 4 :

| unité | feet |
|---|---|
| `GuildBoss5Boss1DeathMortarion` | **1** — `[{col: 6, row: 1}]` |
| les 5 unités adverses | 1 chacune |

**Mortarion occupe UNE tuile.** ⚠ Le témoin **ne discrimine toujours pas** : aucun porteur à plus
d'un pied n'apparaît dans ce montage, donc « Mortarion occupe vraiment une tuile » et « le canal
rend 1 pour tout le monde » restent indistinguables **par cette mesure**. Ce qui EST acquis : le
canal existe et est branché — `runner/abilities/behaviours/context.py::_unit_dict` publie
`get_unit_feet(state, eid)` (mirror `IdunBattle.Entities.EntityExtensions$$GetTiles`), toujours une
liste. Trouver un porteur multi-pieds reste ouvert.

---

## 1. `1093 MortarionsPlagueWind` — PORTÉE

`IdunBattleLogic.Entities.Abilities.Active.Loki.MortarionsPlagueWindAbility$$ExecuteBehaviour`
(le lambda `<ExecuteBehaviour>b__0` de son `DisplayClass1_0` n'est que l'`Execute` différé) :

```
t1  = Cache(<DSLSelectors+0x60> = Target)
t2  = Cache(Enemies(<+0x48> = Caster, AdjacentUnits(t1, 1, 3), 3))
t3  = Cache(Unique(Enemies(<+0x48>, AdjacentUnits(t2, 1, 3), 3)) - t1 - t2)
d_i = If( DSLTriggers$$HasTrait(<+0x60> = Target, 2 = Summon),
          Multiply(MinMaxDamage{,2,3}Average, <DSLFormulas+0x28> = Direct(2)),
          MinMaxDamage{,2,3}Average )
a_i = AttackWithAbilityDamage(<+0x78 behaviors>, Caster, t_i, d_i,
                              Nullable(GetDamageProfile()), GetHits(), AbilityOrEffect(this), 2)
AtomicGroup(0x5c, Group(a1, Target, 0x5d) & Group(a2, Target, 0x5e) & Group(a3, Target, 0x5f))
```

JUMEAU STRUCTUREL de `1035 PlagueWind` — mêmes corps de sélecteur (dédupliqués par IL2CPP), et
**deux différences LUES** :

1. **La MOYENNE, pas le tirage.** 1035 passe `MinMaxDamage{,2,3}` = `RandomAmount(min, max)` ;
   1093 passe leurs variantes `…Average` = `Half(Sum(Direct(min), Direct(max)), 0)`. Le dégât de
   1093 est **déterministe** et ne consomme aucun tirage de valeur.
2. **Le gate `Summon` ×2**, et il porte sur la **CIBLE PRINCIPALE**, pas sur l'unité frappée : si la
   cible est un `Summon`, les **trois** bandes doublent, y compris sur des unités qui n'en sont pas.
   `<DSLFormulas+0x28>` est LU (`DSLFormulas$$.ctor` alloue `+0x18 Direct(0)`, `+0x20 Direct(1)`,
   `+0x28 Direct(2)`, `+0x30 Direct(100)`, `+0x38 Direct(-1)`) : le facteur vaut **2**.

Config : `damageProfile = Psychic`, `nrOfHits = 1` (la même pour les trois bandes), `range = 2`,
`attackRangeType = Ranged`. ⚠ Le dégât **CROÎT** avec la bande (20-25 / 30-35 / 50-70 au niveau 1),
à l'**inverse** de 1035 (36-45 / 27-34 / 20-25) : aucune symétrie à supposer entre les deux.

**Masque** — FORME STATIC-COPY. Le `.ctor` n'appelle **aucun** `TargetingOptions$$.ctor` : il
recopie les 0x40 octets de `<TargetingOptions statics>+0x180` puis
`AActiveAbility$$.ctor(this, &opts, 0)`. Le masque effectif est la constante que
`TargetingOptions$$.cctor` écrit à `<preset>+0x28` = **`0x4002`** (`TargetIsEnemy` +
`TargetMatchesDynamicRule`, qu'aucun `…$$GetDynamicInvalidTargetReason` ne surcharge). `range` ←
`TargetingRange statics+0x18` = `RANGE_FROM_CONFIG` ; `forceMeleeTarget = 1` = `RangedBool.False`.
`AbilityAttackType = 0` = `DirectTargetAttack`. Le masque **MIGRE** de
`TARGETING_OPTIONS_UNPORTED` vers la classe (contrat de disjonction).

---

## 2. `1095 ReapingScythe` — PORTÉE

`…ReapingScytheAbility$$ExecuteBehaviour` tient en trois lignes (aucun lambda, aucun groupe) :

```
targets = <+0x60> op_Addition DSLSelectors$$AdjacentFriends(<+0x60>, unique = 1, selType = 3)
b = AttackWithAttackDamage(behaviors, Caster, targets, MinMaxDamage(this, state, 0),
                           Nullable(GetDamageProfile()), GetHits(), AbilityOrEffect(this),
                           <AttackOptions VIDE>, 2)
Execute(this, b)
```

Le même sélecteur est republié mot pour mot par `…$$GetDamageTargetsSelector` (la face que lit
`ReapingScythePlaybook$$MakeDamagePredictions`).

⚠ **`AdjacentFriends` est ANCRÉ SUR LA CIBLE ⇒ ce sont les ENNEMIS du caster.** La surcharge lue est
la **variante A** (`DSLSelectors$$AdjacentFriends(this, unit, unique, selectionType)` =
`Friends(unit, Units(AdjacentTiles(unit), unique, selectionType) - unit, selectionType)`), tranchée
par ses **XREFS ENTRANTES** — `ReapingScytheAbility$$ExecuteBehaviour` est **absente** de la liste
des appelants de la variante B. La référence d'équipe y est le **centre**, donc `Target` : collapser
la référence sur le caster (le défaut du nœud porté) rendrait le camp **inverse**.

**Famille = ATTACK** (`DSLBehaviors$$AttackWithAttackDamage`, pas `…AbilityDamage`) : crit et block
actifs, 2 tirages par coup. Le 8ᵉ argument `Nullable<AttackDamageBehaviourOptions>` est passé
**vide** (ni `alwaysOverkilled`, ni `alwaysCrit`, ni variance d'arme).

Config : `damageProfile = Chain`, **`nrOfHits = 7`**, `attackRangeType = Melee`.

**Masque** — FORME STATIC-COPY, preset `<TargetingOptions statics>+0x40` (le **même** que
`1217 TheLionsWrath`) : `isSelfCasting = 0`, `range` ← `TargetingRange statics+0x30` =
`RANGE_ADJACENT`, `forceMeleeTarget = 1`, `rules = ` **`0x4000`** = `TargetIsEnemy` **et rien
d'autre**. `AbilityAttackType = 0` = `DirectTargetAttack`.

⚠ Les deux ctors copient des presets **différents** (`+0x180` vs `+0x40`) et portent pourtant le
**même** 3ᵉ argument : le preset ne prédit pas ce littéral, il a été relu.

---

## 3. Le bug de SEEDING que ce cas a trouvé — un GUILD BOSS n'a AUCUN `unitConfig`

MESURE : `combatSnapshot.units[]` rend, pour l'entité du boss,
`unitConfig = {"error": "config null"}` — aucun niveau, aucun multiplicateur. Les cinq unités
adverses, elles, portent `level 50 / activeAbilityLevel 50 / abilityVariablesMultiplier 180`.

Conséquence, avant réparation : `ctx.active_ability_level` restait `None` ⇒ **index 0** de chaque
tableau de variables ⇒ le niveau **1** au lieu du **55** que l'entité porte. Les trois vagues de
1093 sortaient à **45 / 65 / 120** contre **3080 / 4448 / 8211** live.

Le canal qui porte l'information est `combatSnapshot.units[].abilityStates` — l'`AbilityState`
**PER-ABILITY** (`ActiveAbility._abilityState` @0x4c) — que la face DÉCISION consomme déjà
(`playbook/scene.py`) et que le COMBAT ignorait :

```json
[{"id": 1093, "kind": "active", "level": 55, "multiplier": 200}, ...]
```

C'est le gisement de **#174** (MoW) et de **#570-r5** (unités invoquées) sur un **troisième**
porteur : même cause (pas de `unitConfig`), même parade (lire l'`AbilityState`, qui est de toute
façon ce que `AbilityConfiguration$$GetVariableForLevel(config, var, abilityState, 0)` consomme).

Réparation : `snapshot._ability_state_from_rows` + `_ability_state_with_rows`, posés sous la **même
garde** que leurs deux jumeaux (« on n'écrit QUE si le trou existe »). ⚠ **Rien n'est deviné** : le
port ne dispose que d'UN `active_ability_level` par unité là où le natif porte un état par ABILITY,
donc la fonction ne rend un scalaire que si toutes les entrées concernées **s'accordent** ; sinon
`None`. Sur le porteur mesuré, les trois actives portent `(55, 200)` à l'identique.

---

## 4. Ce que la confrontation LIVE discrimine — et ce qu'elle ne discrimine pas

`tests/engine/runner/test_888_mortarion_boss_abilities_live.py`, **4 tests, 4 verts**.

| bras | ce qu'il mesure |
|---|---|
| `1093` 3 anneaux | 4 unités frappées sur 3 anneaux, ventilation par bande issue des memos `Cache`, per-coup live == offline, **trois dégâts distincts et croissants** (3080 / 4448 / 8211) |
| `1093` gate `Summon` (offline) | variation d'entrée : le seul trait de la cible change ⇒ **les trois bandes** doublent, pas seulement la vague 1 |
| `1095` cible ISOLÉE | 1 seule unité frappée — le contre-cas |
| `1095` cible + 2 voisins | 3 unités frappées, per-coup live == offline **bit pour bit** |

**Ce qui discrimine** : les trois anneaux de 1093 ne rendent **pas** le même dégât (un port à base
unique passerait tout le reste) ; les deux bras de 1095 n'ont pas le même **cardinal** (aucun
scalaire ne passe les deux) ; et le bras à 2 voisins **réfute** le collapse `reference = caster` —
Mortarion n'a aucun allié, donc un port collapsé ne frapperait que la cible dans les deux bras.

**Ce qui ne discrimine PAS, et il faut le dire :**

* le dégât de 1093 étant **déterministe**, ces tests ne prouvent **rien** sur sa consommation RNG ;
* le gate `Summon` de 1093 n'est confronté qu'**OFFLINE** (aucun summon comme cible principale d'un
  cast du boss dans ce montage) ;
* le boss est monté côté **JOUEUR** pour être pilotable, là où le gameconfig le place côté ennemi
  (`TeamWithPlayerIndex 1`) — aucun volet mesuré ici ne lit le camp du caster, mais l'écart est réel ;
* `AttackWithAbilityDamage` ne thread pas le `pierce_effect_bonus` des effets du caster (son jumeau
  `AttackWithAttackDamage` le fait) — inerte sur ce porteur, résidu nommé dans `#888-r1`.

### Deux vices de MONTAGE que ce cas a rencontrés, et leur parade

1. **`reach_my_turn()` APRÈS les placements rend la main à l'IA adverse**, qui joue entre le
   placement et le cast : la cible ressortait **morte** (`hp = 0`) et le port refusait alors le cast
   (`not_alive_and_not_fled`) pendant que le natif l'acceptait — un rouge qui **accusait le PORT
   pour une faute de MONTAGE**. L'ordre canonique du harnais existe pour `CasterHasNotMoved`, que ni
   1093 (`0x4002`) ni 1095 (`0x4000`) ne portent : on atteint donc son tour **d'abord**, on place
   ensuite. Une garde `_geometry_holds` revalide juste avant le cast.
2. **Chaque `place` d'une unité adverse consomme SON activation.** Mettre 4 unités à l'écart pour
   monter une cible isolée faisait basculer le tour, et le natif refusait alors le cast **en
   silence** (`ok = True`, `damage_by_target` VIDE, signature #111) — le bras se **skippait** au lieu
   de mesurer. Parade : **dimensionner le roster adverse sur le bras** (1 ennemi pour le bras isolé,
   3 pour le bras à 2 voisins), ce qui supprime tout déplacement de mise à l'écart. Une assertion
   nomme désormais ce régime au lieu de le laisser se déguiser en divergence de ciblage.

⚠ **`darkaCompanion` reçoit 6 coups de 1095 là où les deux autres en prennent 7** — elle porte
`Parry_ReduceHits`, et le port le reproduit exactement. Figer `len(per_hit) == nrOfHits` partout
serait un **faux rouge sur le natif** : le test asserte l'égalité live/offline du compte par cible,
plus le fait que le **plafond** observé vaut `nrOfHits`.

---

## 5. `1094 TheLantern` — RE COMPLÈTE, PORT NON FAIT (résidu `#888-r1`)

**C'est un patron 2-PHASES : le cast NE FRAPPE PAS.** La colonne `DAMAGE(Energy)` de l'audit dérive
du `damageProfile` de la config, pas du behaviour.

### Phase 1 — `…TheLanternAbility$$ExecuteBehaviour`

```
ring1  = SurroundingTiles(<+0x60> = Target,     includeCenter = 0, range = 1, onlyMovable = 0, includeNonWalkable = 0)
ring2  = SurroundingTiles(<+0x60>,              includeCenter = 0, range = 2, 0, 0)
cring1 = SurroundingTiles(<+0x58> = CasterTile, includeCenter = 0, range = 1, 0, 0)
area   = Unique( (<+0x60> op_Addition ring1) op_Addition (ring2 op_BitwiseAnd cring1) )
foes   = Enemies(<+0x48> = Caster, area, 3)

b1 = AddEffect(behaviors, 0x4ab = 1195 TheLantern_PendingTarget, AbilityStateReference, Caster, area)
b2 = AddEffect(behaviors, 0x429 = 1065 Pinned,                   AbilityStateReference, Caster, foes)
b3 = AddEffect(behaviors, 0x4aa = 1194 TheLantern_PendingAttack, AbilityStateReference, Caster, Caster)
Execute(this, (b1 & b2) & b3)
```

La zone est le disque de rayon 1 autour de la **tuile ciblée**, étendu aux tuiles à distance 2 de la
cible qui sont **adjacentes au caster** — le « pont » entre Mortarion et la zone. La même chaîne est
republiée par `…$$GetTilesForTargetAreaFromTargetTile` (la face que lit le ciblage).

**Les six arguments de `SurroundingTiles` sont tranchés par XREF** : `TheLanternAbility` est absente
des appelants de la surcharge à 5 arguments, donc c'est celle à 6 —
`(origin, includeCenter, range, onlyMovable, includeNonWalkable)` ; `includeCenter = 0` la fait
récurser avec `1` puis retrancher `Tiles(origin)`.

**`<DSLSelectors+0x58>` = un `CasterTile`, et les deux lectures du dépôt sont CONCILIÉES.**
`DSLSelectors$$InitializeShared` alloue `+0x50` **et** `+0x58` depuis la **MÊME classe**
(`DAT_183342968`), là où `+0x48` (Caster) en a une autre : ce sont deux instances du même sélecteur.
`case-287r11r1` (`get_CasterIsCasterTile = AreEqual(+0x48, +0x50)`) et
`playbook/resurrection_orb.py` (`+0x58` = CasterTile) disent donc la même chose.

### Phase 2 — le déclencheur, LU sur la base de famille

`TheLantern_PendingAttackEffect$$GetTriggeredAbilityType` rend `0x48f = 1167 TheLantern_Attack`, et
le déclenchement appartient à `APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal` (foyer
commun aux 20 dérivées, **déjà porté** : `runner/operations/triggers/pending_attack.py`) :

```
Triggered( On(0x15) & IsTurnOf(<owner>),
           TriggerAbility(<owner>, GetTriggeredAbilityType(), ...) & RemoveEffect(Effect) )
```

`…TheLantern_AttackAbility$$CreateBehaviour` :

```
cache   = Cache(EntitiesWithAnyEffect(<+0x18> = AllTiles, 0x4ab = 1195, effectTarget = 6))
targets = Enemies(<+0x48> = Caster, cache, 3)
atk     = AttackWithAbilityDamage(behaviors, <+0x30> = Owner, targets,
                                  BaseTriggeredAbility$$MinMaxDamage(this, state),
                                  Nullable(GetDamageProfileOrDefault(this, 0x10)), GetHits(),
                                  AbilityOrEffect(this), 2)
rm      = RemoveEffect(behaviors, cache, Nullable(0x4ab), 0)
AtomicGroup(0x2a, rm & atk)
```

⚠ **La marque est posée sur des TUILES et l'attaque frappe qui s'y trouve AU TOUR SUIVANT** — une
unité qui sort de la zone y échappe, une unité qui y entre la prend. C'est le seul volet de ce
cas qui exige une confrontation sur **deux tours**.

### Masque — FORME FLAGS DIRECTS (le littéral EST le masque)

`TheLanternAbility$$.ctor` appelle la surcharge à 7 arguments
`TargetingOptions$$.ctor(this, isSelfCasting, range, forceMeleeTarget, rules,
getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)` — **tranché par XREF entrante** :

```
TargetingOptions..ctor(&opts, 0, &CustomRange(), 1, 0x2000100042, 0, 0)
AActiveAbility..ctor(this, &opts, 2)                        // AbilityAttackType.Others
```

`0x2000100042` = `TargetMatchesDynamicRule (0x2)` | `TargetIsTile (0x40)` |
`AllowSteppableUnit (0x100000)` | `CasterHas7Tiles (0x2000000000)`. Le bit `TargetMatchesDynamicRule`
est **portant** ici : `…$$GetDynamicInvalidTargetReason` **est** surchargée (et
`…$$IsValidCenterTileForTargetArea` avec elle).

### Pourquoi ce port n'est pas fait ici

Il exige, dans un même commit : deux classes d'effet neuves (1194 dérivée d'`APendingAttackEffect`,
1195 marqueur de TUILE), l'entrée dans `PENDING_ATTACK_EFFECTS`, un module de phase 2 sous
`operations/triggers/loki/` (sans lequel le `Triggered()` **retire la marque sans que rien ne
frappe** — régime que le module déclare PIRE que le statu quo), l'arbre de phase 1, le ciblage
TILE-TARGET avec sa règle dynamique, et une confrontation live sur **deux tours**. L'infrastructure
`PendingAttack` étant déjà là, c'est une tranche bornée — mais c'en est une.

---

## Résidu ouvert

* **`#888-r1`** — porter `1094 TheLantern` (les deux phases + les deux effets), et threader le
  `pierce_effect_bonus` dans `AttackWithAbilityDamage`.
