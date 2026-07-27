# Case PSYCHIC-AoE — PlagueWind (1035) et Doombolt (1102)

Deux actives **Psychic** de HEROS, jusqu'ici **NO-OP** côté COMBAT (absentes d'`ABILITY_CLASSES`,
donc `ported:False` silencieux). Les deux sont désormais portées, câblées et **confrontées LIVE
bit-à-bit** sur des cas discriminants.

| id | ability | porteur | famille de factory native | artefact natif |
|---|---|---|---|---|
| 1035 | `PlagueWind` | `deathTyphus` « Typhus » (HERO, dans `--list-pool`) | **ABILITY** (`DSLFactory$$AttackWithAbilityDamage`) | `IdunBattleLogic.Entities.Abilities.Active.Loki.PlagueWindAbility$$ExecuteBehaviour` |
| 1102 | `Doombolt` | `thousAhriman` « Ahriman » (HERO, dans `--list-pool`) | **ATTACK** (`DSLFactory$$AttackWithAttackDamage`) | `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomboltAbility$$ExecuteBehaviour` |

Ports : `engine/runner/abilities/deathguard.py` (PlagueWind) et
`engine/runner/abilities/thousandsons.py` (module neuf, Doombolt).
Probe de mesure : `scripts/python/probe_psychic_aoe.py` (montage réutilisable : build isolé, drive
des positions des DEUX camps, capture, replay offline, cast live, contre-épreuve).
Fixture pytest NOMMÉE qui l'expose : `psychic_aoe_case` (`tests/engine/runner/conftest.py`).
Gardes : `tests/engine/runner/test_plague_wind_live.py`, `tests/engine/runner/test_doombolt_live.py`.

### Registre — les deux données obligatoires, LUES au décompilé

| id | `ABILITY_ATTACK_TYPE` (3ᵉ arg d'`AActiveAbility$$.ctor`) | `TARGETING_OPTIONS.rules` | source du masque |
|---|---|---|---|
| 1035 | `0` = `DirectTargetAttack` | `0x4002` = `TargetIsEnemy \| TargetMatchesDynamicRule` | preset STATIQUE `TargetingOptions statics+0x180` → `cctor` écrit `statics+0x1a8` |
| 1102 | `2` = `Others` | `0x200000000000004` = `TargetIsCasterOrEnemy \| CasterMatchesDynamicRule` | preset STATIQUE `statics+0x3c0` → `cctor` écrit `statics+0x3e8` |

**Les deux ctors passent par un PRESET, pas par un littéral inline** — le piège nommé dans le
`CLAUDE.md`. `PlagueWindAbility$$.ctor` recopie les 0x40 octets de `statics+0x180` puis appelle
`AActiveAbility..ctor(this, &opts, 0, 0)` ; `DoomboltAbility$$.ctor` recopie `statics+0x3c0`, le
passe à l'**overload de COPIE** `TargetingOptions$$.ctor(&dest, &src)` (aucun flag ajouté) puis
`AActiveAbility..ctor(this, &opts, 2, 0)`. Le masque effectif a donc été lu **dans le `cctor`**, pas
recopié du ctor.

Deux conséquences non triviales, contre-intuitives, à ne pas « symétriser » :

- **Doombolt n'a PAS `TargetIsEnemy`.** Sa légalité de cible passe entièrement par
  `TargetIsCasterOrEnemy` (bit 57, règle NON portée par la cascade statique → dégradation
  permissive assumée) et par `CasterMatchesDynamicRule` (canal NON porté, cf. §5.1).
- **`forceMeleeTarget` vaut `1` dans les DEUX presets, et `1` = `RANGED_BOOL_FALSE`** (l'enum natif
  est inversé : `True = 0`). Aucun clamp `RangedInMelee` : lire `0`/`1` comme un booléen C aurait
  ramené la portée à l'adjacence et refusé des casts légaux.

`TargetingRange` : les deux presets copient le MÊME statique `TargetingRange statics+0x18` =
`RANGE_FROM_CONFIG` → `AActiveAbility$$SetConfigValuesInTargetingOptions` y pose
`overrideRange = GetNumberConstant(0x16 range)` = **2** pour les deux (config 1035 et 1102).

---

## 1. PlagueWind (1035) — AoE concentrique à TROIS bandes

### 1.1 Arbre natif (mirror 1:1)

```
t1 = Cache( target@0x178 )                                         # cible PRINCIPALE
t2 = Cache( Enemies(caster@0x160, AdjacentUnits(t1, 1, 3), 3) )    # SECONDAIRES
t3 = Cache( Unique(Enemies(caster@0x160, AdjacentUnits(t2, 1, 3), 3))
            op_Subtraction t1  op_Subtraction t2 )                 # TERTIAIRES
d1 = MinMaxDamage (this, level) = RandomAmount(var 0x0c minDmg  , var 0x0d maxDmg  )
d2 = MinMaxDamage2(this, level) = RandomAmount(var 0x36 minDmg_2, var 0x37 maxDmg_2)
d3 = MinMaxDamage3(this, level) = RandomAmount(var 0x38 minDmg_3, var 0x39 maxDmg_3)
a_i = AttackWithAbilityDamage(caster@0x160, t_i, d_i, GetDamageProfile(config,0) = Psychic,
                              GetNumberConstant(config, 0x2f) = nrOfHits,   # LA MEME pour les 3
                              AbilityOrEffect(this+0x10 = 0x40b = 1035))
b   = Group(a1, target, 0x4b) & Group(a2, target, 0x4c) & Group(a3, target, 0x4d)
ExecuteAtomic( 0x4a, <lambda qui Execute(b)>, target@0x178 )
```

Les indices de variable sont LUS dans `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage`
(0xc/0xd), `$$MinMaxDamage2` (0x36/0x37) et `$$MinMaxDamage3` (0x38/0x39) — pas déduits des noms
gameconfig. Le `nrOfHits` est relu **littéralement** (`GetNumberConstant(0x2f)`) aux trois
call-sites : une seule constante pour les trois bandes (config 1035 : `nrOfHits = 1`).

i2 concordant : « Deals 1x … to a target within 2 hexes. Any enemies **adjacent to the initial
target** take 1x … Any **further** enemies adjacent to **at least one secondary target** take 1x … ».

### 1.2 Points de fidélité tranchés

- **`Cache` n'est PAS un pass-through.** Les trois nœuds sont évalués **paresseusement**, chacun à
  l'exécution de SA bande : `t2` est figé APRÈS le dégât de la bande 1, `t3` APRÈS celui de la
  bande 2 — exactement comme le natif (`op_BitwiseAnd` = `CombinedBehaviour`, exécution
  gauche→droite). Le port reconstruit l'arbre à chaque cast → mémos **par-cast**, comme les `Cache`
  alloués dans `ExecuteBehaviour`.
- **`AdjacentUnits` sur un ENSEMBLE.** `IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits` ne
  construit AUCUN sélecteur dédié : il **compose** `op_Subtraction(Units(AdjacentTiles(s)), s)`
  (décompilé). La classe `AdjacentUnits` du port passe par `_within(units, center, radius)`, qui
  n'accepte qu'UN centre — suffisant pour ses call-sites historiques, impossible pour la bande
  TERTIAIRE dont la source est l'ENSEMBLE des secondaires. D'où le helper
  `entities/selectors/composites.adjacent_units`, mirror TEXTUEL de la factory. **La différence
  n'est pas cosmétique** : l'exclusion native est « appartenance à la source », pas « distance > 0
  par-centre » — une unité de la source adjacente à une AUTRE unité de la source doit sortir.
- **Aucun filtre `Alive` ajouté** : c'est `Units` (= `UnitsOnTilesSelector`) qui ne rend que les
  unités DEBOUT, comme le natif.
- **Famille ABILITY** (`AttackWithAbilityDamage`, classification par la CALLEE du décompilé) : 1
  tirage par coup, aucun crit, aucune feuille positionnelle, ordre « bouclier × limites » de
  `CalculateAbilityDamage`.
- `Group(0x4b/0x4c/0x4d)` = groupes de **présentation** (`GroupBehaviour$$Execute` = ouvre le
  groupe, exécute le child INLINE, ferme ; aucune mutation propre, aucun court-circuit). Porté comme
  nœud pass-through pour le mirror structurel (`entities/behaviours.Group`).

---

## 2. Doombolt (1102) — N coups répartis « evenly »

### 2.1 Corps natif (mirror 1:1)

`ExecuteBehaviour` est **impératif et CONSTRUIT un arbre** (matérialisation `ToList`, réordonnancement
`Remove`/`Insert`, division entière, accumulation `op_Addition`) — le port mirror cette structure :
étage impératif au-dessus, feuilles DSL en dessous.

```
N       = Min( Sum( ConfigConst(0x2f = nrOfHits),
                    Count( EntitiesWithAnyEffect(AllTiles@0x78, 5 = Fire, sourceFlag 6) ) ),
               Get(9) )                                   # cap LITTERAL 9, pas une constante config
targets = DoomboltAbility$$GetTargets()
        = Damageable( Unobscured( caster@0x160,
                                  SurroundingEnemies(caster@0x160, casterTile@0x168,
                                                     ConfigConst(0x16 = range), 1, 3) ) )
liste   = SortUnitsByDamageUtility(targets, owner@0x148, Direct(AbilityOrEffect(1102)),
                                   UtilityDefinition(0x22 = Damage),
                                   Direct(GetVariableForLevel(0xc = minDmg, level)),
                                   <dmgMax = null>).ToList()
if (liste.Count == 0) return;                             # SORTIE ANTICIPEE
if (caster != null && target != null && caster != target) { liste.Remove(target); liste.Insert(0, target); }
C = liste.Count ; r = N % C ; damage = MinMaxDamage(this, level)
behaviour = Nothing()
foreach u in liste :
    k = (r >= 1) ? N / C + 1 : N / C                      # division ENTIERE C#
    r = (r >= 1) ? r - 1     : r
    behaviour += AttackWithAttackDamage(owner@0x148, Get(u), damage, Nullable(Psychic), k,
                                        AbilityOrEffect(0x44e = 1102), <alwaysOverkilled = null>)
ExecuteAtomic( 0x61, <lambda qui Execute(behaviour)> )
```

`AllTiles@0x78` est le slot partagé `AllTilesSelector` posé par
`IdunBattleLogic.Entities.DSLFactory$$InitializeShared` → le compte de feu porte sur **tout le
plateau** (i2 : « each hex on the battlefield that is currently on Fire »). Nouveau nœud porté :
`entities/selectors/tiles.AllTiles`.

`SortUnitsByDamageUtility` reçoit `dmgMin = Direct(minDmg[level])` et **`dmgMax = null`** (8ᵉ argument
du factory = 0) ⇒ `dmax == dmin` (mirror `runner/operations/damage_utility.py`).

Le réordonnancement est **inconditionnel** dès que caster et cible existent et diffèrent : `Remove`
est un no-op si la cible n'était pas dans la liste, mais `Insert(0, …)` l'ajoute quand même — donc la
cible du message est TOUJOURS en tête et compte dans `C`. Porté tel quel.

### 2.2 Points de fidélité tranchés

- **Famille ATTACK** (contraste avec PlagueWind) : `AttackWithAttackDamage` LU au décompilé ⇒ crit +
  resolve slot-8, 2 tirages/coup à cc = 0.
- Le nombre de coups n'est PAS `GetNumberConstant(0x2f)` mais un **entier calculé** par cast →
  feuille `AttackWithAttackDamage(hits=k)`, une par cible (mono-cible, comme le natif qui construit
  UN behaviour par entité).
- `k` peut valoir **0** (quand `N < C`) : le natif construit **quand même** le behaviour — aucun
  court-circuit. Le port aussi (cf. §3, c'est ce qui a révélé le bug du plancher).

---

## 3. Divergence trouvée et corrigée : le PLANCHER DE COUPS n'est pas 1, il est borné par la BASE

**Symptôme mesuré** (`probe_psychic_aoe.py --case db-4` : 4 ennemis à portée, N = 3 ⇒ répartition
`[1, 1, 1, 0]`) : le natif ne porte **aucun** coup à la 4ᵉ cible, le port lui en portait **un**
(1603 de dégât fantôme).

**Étage localisé, LU** — `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` :

```
base = System.Math.Max(weaponHits + GetStat(0x11 ExtraHits) + (melee ? GetStat(0x17 ExtraHitsMelee)), 0)
…  hits += amount ; if (cap.HasValue) hits = Math.Max(hits, Math.Min(base, cap))   # clamp PAR-EFFET
return System.Math.Max(hits, 0)                                                    # PLANCHER = 0
```

Le natif **ne plancher jamais à 1**. Le « minimum 1 coup » observé sur LightCover/Parry vient du
**clamp par-effet** `Math.Max(hits, Math.Min(base, cap))`, que le port approxime historiquement par
un `max(1, …)` global. Cette approximation est correcte tant que la base est ≥ 1 et **fausse quand
elle vaut 0** : le clamp natif est borné par la BASE, donc rien ne peut remonter au-dessus de 0.

**Correctif** (borné, mirror du clamp dans le seul régime où les deux divergent) :
`services/attack_hits_formula.py` remplace ses deux `max(1, …)` par `max(min(1, base_default), …)`,
et `runner/operations/damage_ops/ability.py::execute_ability_attack` borne son plancher terminal par
la base DEMANDÉE (`_hits_floor = min(1, int(hits))`). Base ≥ 1 ⇒ plancher 1, comportement
**strictement inchangé** partout ailleurs.

**Le port INTÉGRAL des caps par-effet reste un chantier séparé** (composant PARTAGÉ prédiction +
combat, plusieurs tests live dédiés) : tant qu'il n'est pas fait, une base ≥ 1 ramenée sous 1 par un
malus SANS cap rendrait 1 côté port là où le natif rendrait 0. Non mesuré, non atteint par les
consommateurs actuels.

Non-régression rejouée après le correctif : `test_ability_hits_channel_live.py`,
`test_ability_hits_attack_nature_live.py`, `test_damage_ability_live.py`, `test_flail_swing_live.py`,
`test_damage_roll_live.py`, `test_predict_live.py`, `test_damage_crit_live.py`,
`test_damage_block_live.py` — 12/12 verts.

---

## 4. Validation live (board MC1_67, seed 31337, géométrie CRAFTÉE par `applyAction move`)

Protocole par cas : build isolé → **drive des positions des DEUX camps** → capture
(`decisionView`/`observeBattle`/`combatSnapshot`/`boardGraph`/`dumpRng`) → replay OFFLINE sur le MÊME
état et le MÊME `state.rng` → cast LIVE → comparaison **per-coup** → **contre-épreuve de
discriminance** (un port délibérément FAUX doit DIVERGER).

Toutes les valeurs du tableau ont été **RE-MESURÉES après rebase sur `738878c`** (95 commits en
amont de la base initiale, dont l'arrondi des bornes matérialisées, l'inversion de l'ordre
bouclier × limites par famille, le jet de block Daemon et le scindage de `damage_ops` en package) :
elles sont **inchangées, valeur par valeur**.

| cas | montage | attendu | LIVE (Amount par coup) | OFFLINE | verdict |
|---|---|---|---|---|---|
| `pw-solo` | cible isolée | bande 1 seule | u77 `[3706]` | `[3706]` | BIT-EXACT |
| `pw-chain` | cible + adjacent-cible + adjacent-du-secondaire (dist 2 de la cible) | 3 bandes, 3 plages | u77 `[3706]` · u79 `[3306]` · u81 `[3476]` | idem | BIT-EXACT |
| `db-1` | 1 ennemi à portée | `[3]` | u77 `[1518, 1359, 1464]` | idem | BIT-EXACT |
| `db-2` | 2 ennemis | `[2, 1]`, cible en tête | u77 `[1518, 1359]` · u79 `[1464]` | idem | BIT-EXACT |
| `db-3` | 3 ennemis | `[1, 1, 1]` | u77 `[1518]` · u79 `[1359]` · u81 `[1464]` | idem | BIT-EXACT |
| `db-4` | 4 ennemis, PV hétérogènes | `[1, 1, 1, 0]` | u77 `[1354]` · u81 `[1468]` · u79 `[1197]` · u83 `[]` | idem | BIT-EXACT |

**Contre-épreuves (discriminance prouvée, pas supposée)** :

- `pw-chain` avec un port FAUX où les trois bandes partagent `minDmg`/`maxDmg` →
  `3706 / 4464 / 6285` ≠ live `3706 / 3306 / 3476`. Le cas SÉPARE bien les trois plages.
- `db-*` avec un port FAUX en famille ABILITY (1 tirage/coup) → divergence dès le 2ᵉ coup.

**Ce que `db-4` prouve en plus** : l'ordre rendu par `SortUnitsByDamageUtility` n'y est **pas** l'ordre
par id (u77, **u81**, **u79**) ; comme le RNG avance dans l'ordre d'itération, l'égalité per-coup
valide la **permutation** elle-même, pas seulement le nombre de coups. C'est aussi le cas qui a
révélé le plancher (§3).

---

## 5. Résidus NOMMÉS (non portés, non couverts)

1. **`DoomboltAbility$$GetDynamicInvalidCasterReason`** — règle-déléguée `CasterMatchesDynamicRule`
   (bit `0x4`, slot vtable `this+0x470`) : rend `0x8000000` (TargetIsInRange) quand `GetTargets()`
   est VIDE. Le bit **est bien posé** dans le masque porté (`0x200000000000004`), mais le canal
   CASTER-dynamique **n'existe pas** dans `abilities/targeting.py` (seul le canal CIBLE-dynamique,
   bit `0x2`, y est porté) → aucun gate inventé. L'observable perdue est le **turn-flag** d'un cast
   sans cible (natif : cast refusé, `actionConsumed = false`) ; le DÉGÂT, lui, est identique — la
   sortie anticipée `list.Count == 0` EST portée.
   Idem pour `TargetIsCasterOrEnemy` (bit 57), non porté par la cascade statique.
2. **`Doombolt_ResetAbility$$CreateTrigger`** (triggered) — « Doombolt réutilisable si Ahriman tue
   avec son attaque normale ». Hors du périmètre de cet `ExecuteBehaviour`.
3. **`PsychicStalk`** (passif d'Ahriman : +33 % vs cible sur hex en feu, +364 pour les alliés Chaos,
   mise à feu de l'hex sur l'attaque NORMALE) — ABSENT du registre de triggers
   (`runner/operations/triggers/dispatch/registry.py`). **Inerte sans hex en feu** (le régime des mesures
   ci-dessus), manquant dès que le plateau brûle. Corollaire : le terme `Count(hexes en Feu)` de
   `N` n'a pas pu être confronté live à une valeur ≠ 0 — seule la branche `N = nrOfHits` l'est.
4. **`ContagionsOfNurgle`** (aura de Typhus, réduction d'armure) — canal d'aura non matérialisé
   offline (résidu connu, `DslContext.is_in_team_aura`). Inerte ici : `Psychic` a `PiercingRatio 100`
   (l'armure est intégralement percée), donc l'aura ne peut pas déplacer le dégât de PlagueWind.
5. **Caps par-effet de la formule de coups** — cf. §3 : le `max(1, …)` du port reste une
   approximation du clamp `Math.Max(hits, Math.Min(base, cap))` pour toute base ≥ 1.
6. **`WeaverOfFate` × Doombolt en régime max-out** : le trait EST porté (`loki/weaver_of_fate.py` +
   branche max-out de `damage_ops`, #202) et s'applique par le canal commun, mais aucune de nos
   mesures ne l'a armé — un seul Doombolt ne peut pas atteindre le seuil « ≥ 3 ennemis ayant subi du
   dégât Psychic » AVANT ses propres coups (le 3ᵉ ennemi est touché par le 3ᵉ coup). Le régime
   « action Psychic préalable dans le même tour, puis Doombolt » n'est pas couvert.

Face **DÉCISION** (playbooks `PlagueWindPlaybook` / `DoomboltPlaybook`) : **hors périmètre** de ce
case, qui ne porte que la face COMBAT (`ExecuteBehaviour`).
