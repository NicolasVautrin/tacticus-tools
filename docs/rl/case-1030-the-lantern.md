# #1030 — `1094 TheLantern` : le no-op silencieux fermé, et les deux corps que l'ICF avait fondus

Build `rnca9r7q6c`. Résidu parent : `#888-r1` (RE complète, port non fait) — **CLOS par cette
tranche**. Porteur : `deathBossMortarion` « Mortarion », GUILD BOSS Death Guard, kind `npc`.

**Avant** : `1094` absente d'`ABILITY_CLASSES` → le handler acceptait le cast, posait les flags de
tour, et n'exécutait RIEN. Zéro effet, zéro dégât, zéro erreur. La face DÉCISION n'existait pas
davantage. **Après** : les deux phases COMBAT + la face DÉCISION. Audit régénéré :
`no-op silencieux 8 → 7`, `portées 167 → 168`, `DAMAGE 5 → 4`.

## 1. Ce que le cast fait — et ce qu'il ne fait pas

`IdunBattleLogic.Entities.Abilities.Active.Loki.TheLanternAbility$$ExecuteBehaviour` — **trois
`AddEffect`, aucune attaque** :

```
ring1  = SurroundingTiles(<+0x60> = Target, includeCenter = 0, range = 1, onlyMovable = 0,
                          includeNonWalkable = 0)
ring2  = SurroundingTiles(<+0x60>,              includeCenter = 0, range = 2, 0, 0)
cring1 = SurroundingTiles(<+0x58> = CasterTiles, includeCenter = 0, range = 1, 0, 0)
area   = Unique( (<+0x60> op_Addition ring1) op_Addition (ring2 op_BitwiseAnd cring1) )
foes   = Enemies(<+0x48> = Caster, area, selectionType = 3)

b1 = AddEffect(0x4ab = 1195 TheLantern_PendingTarget, AbilityStateReference,
               source = Caster@+0x48, targets = area, options = <Nullable ZEROEE>)
b2 = AddEffect(0x429 = 1065 Pinned,                   AbilityStateReference,
               source = Caster@+0x48, targets = foes, options = <Nullable ZEROEE>)
b3 = AddEffect(0x4aa = 1194 TheLantern_PendingAttack, AbilityStateReference,
               source = Caster@+0x48, targets = Caster@+0x48, options = <Nullable ZEROEE>)
Execute( (b1 op_BitwiseAnd b2) op_BitwiseAnd b3 )
```

La colonne `DAMAGE(Energy)` de l'audit dérive du `damageProfile` de la **config**, pas du
behaviour. La même chaîne de zone est republiée par `…$$GetTilesForTargetAreaFromTargetTile` — la
face que lisent le ciblage **et** le playbook.

Phase 2 — `…Triggered.Loki.TheLantern_AttackAbility$$CreateBehaviour` (`1167`) :

```
cache   = Cache( EntitiesWithAnyEffect(<+0x18> = AllTiles, 0x4ab = 1195, effectTarget = 6 = Both),
                 matchAbilityEntities = 1 )
targets = Enemies( <+0x48> = Caster, cache, selectionType = 3 )
atk     = AttackWithAbilityDamage( caster = Owner@+0x30, target = targets,
                                   amount = BaseTriggeredAbility$$MinMaxDamage(this, abilityState),
                                   damageProfile = Nullable(GetDamageProfileOrDefault(this, 0x10)),
                                   hits = GetHits(), abilityOrEffect = AbilityOrEffect(this),
                                   selectionType = 2 )
rm      = RemoveEffect( cache, Nullable(0x4ab), null )
return AtomicGroup( 0x2a = GroupType.Ability_AtomicGroup, rm op_BitwiseAnd atk )
```

⚠ **La marque vit sur des TUILES et l'attaque frappe qui s'y trouve AU TOUR SUIVANT** — une unité
qui sort de la zone y échappe, une qui y entre la prend. `EntitiesWithAnyEffect` part d'`AllTiles`,
pas d'une liste figée au cast.

⚠ **Le `Cache` est load-bearing, et l'ordre `rm & atk` aussi** : le retrait s'exécute AVANT
l'attaque ; sans mémo, le second membre relirait un ensemble déjà vide.

## 2. Les trois lectures qui ne se devinent pas

### 2.1 `GetAttackingUnitSelector` est SURCHARGÉE, et ce n'est pas `BondedEntity`

`1194` est posé par `AddEffect`, **pas** `AddBondEffect`. `IdunBattle.Entities.Behaviours.
AddEffectBehaviour$$Execute` ne porte AUCUN sélecteur `bondedEntity` (ses champs sont `+0x60`
source, `+0x68` cibles, `+0x78` turns, `+0x80` niveau) et `GetEffectBuilder` ne bascule sur le
builder de bond que si l'id résolu est non nul. L'instance n'a donc **pas** de composant de bond, et
`IdunBattle.Entities.Selectors.SelectBondedEntityFromEffectSelector$$Select` rendrait une liste
**VIDE** (corps lu : `TryGet<BondComponent>` échoue → `return new List<>()`).

Conséquence si l'on avait porté le corps hérité : `IsTurnOf(<vide>)` **fire au tour de n'importe
quel joueur** — `IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger$$ShouldTrigger` est un ALL, et son
ALL sur vide rend TRUE (corps lu : la sortie de boucle sur `MoveNext == 0` fait `return 1`) — pendant
que le `TriggerAbility` ne déclenche RIEN. Un no-op silencieux de plus, déguisé en port.

**Deux corps existent, et l'ICF les fond.** `ghidra/functions.tsv` comme `frida/methods.tsv` n'en
publient que DEUX lignes pour les 20 dérivées d'`APendingAttackEffect` :

| corps | propriétaire publié | contenu LU |
|---|---|---|
| A | `IdunBattle.Entities.Effects.Loki.ValkyrieStrikeEffect$$GetAttackingUnitSelector` | `ABondEffect$$BondedEntitySelector(this)` |
| B | `Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.InstrumentsOfVengeance_PendingAttackEffect$$GetAttackingUnitSelector` | `DSLSelectors$$EffectSource(Effect@+0x38)` — corps INLINE **identique** à `IdunBattleLogic.Entities.DSLSelectors$$EffectSource` (recoupé par `search_code` littéral : cette classe est le SEUL autre porteur du même `Il2CppClass*`) |

Le nom du propriétaire ne dit RIEN de l'appelant. Ce qui tranche, en deux temps :

1. **le `global-metadata.dat`** établit QUI DÉCLARE la surcharge —
   `IdunBattle.Entities.Effects.Loki.TheLantern_PendingAttackEffect` déclare
   `[.ctor, GetAttackingUnitSelector (slot 98), GetTriggeredAbilityType (99),
   IsExecutedIfOwnerDies (100)]` (lecture par `il2cpp_metadata.noms_declares`, grille ancrée sur
   `OperationProcessor`/`BattleQuery`/…) ;
2. **le vecteur de pose** tranche LEQUEL des deux corps : sans composant de bond, seul B a un sens.

⚠ **Ce que cette lecture ne prouve PAS** : le choix entre A et B repose sur l'argument fonctionnel
ci-dessus, pas sur une lecture du slot de vtable (qui n'est rempli qu'au runtime). Il est
**falsifiable en une mesure** — si le tir ne part pas live, c'est A. Résidu `#1030-r3`.

### 2.2 `Enemies` part d'ENTITÉS-TUILES, et le port ne le faisait pas

`IdunBattle.Entities.Selectors.UnitsByTeamSelector$$Select` passe par
`IdunBattle.DSL.TargetsSelector$$SelectUniqueUnits` → `$$SelectUnit`, dont la première ligne est
`if (IsUnitFoot(entity) || IsTile(entity)) entity = GetUnit(entity, state);`. La conversion
tuile → occupant appartient donc au SÉLECTEUR.

Le port normalisait par `_units_of` puis jetait tout ce qui n'était pas un `dict` : une source en
domaine TUILE rendait `[]`, **sans erreur**. Deux régimes touchés — le `foes` de la phase 1 et le
`targets` de la phase 2, tous deux `Enemies(…, <ensemble de tuiles>)`. Réparé dans
`entities/selectors/units.py` (`Enemies` **et** `Friends` — même classe native, flag 0/1), pas
contourné par un `Units(…)` que le natif n'écrit pas. Second régime, plus discret : une
ENTITÉ-TUILE (dict à `visualId` NUL) passait le `isinstance(dict)` et, sa clé `team` étant absente,
comptait pour un **ennemi**.

### 2.3 `range = CustomRange(2)`

`…TheLanternAbility$$.ctor` est appelante de la surcharge `range:System.Int32` (XREF entrante ; elle
est ABSENTE de la liste des appelants de `getRange:GetRange`), et le littéral est relu **aux octets**
du call-site (`ba 02 00 00 00` = `mov edx, 2` immédiatement avant le `call`) — Ghidra ne l'affiche
pas. Confirmé par le port : une cible à distance 3 est refusée (`invalid_target = 0x8000000`).

## 3. Masque et attack type

Forme **FLAGS DIRECTS** (le littéral EST le masque), surcharge à 6 paramètres
`TargetingOptions$$.ctor(isSelfCasting, range, forceMeleeTarget, rules,
getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)` :

```
TargetingOptions..ctor(&opts, 0, &CustomRange(2), 1, 0x2000100042, 0, 0)
AActiveAbility..ctor(this, &opts, 2)                       // AbilityAttackType.Others
```

`0x2000100042` = `TargetMatchesDynamicRule (0x2) | TargetIsTile (0x40) |
AllowSteppableUnit (0x100000) | CasterHas7Tiles (0x2000000000)` — décomposition **complète** : la
somme des quatre bits REND le littéral.

⚠ **La règle dynamique reste NON PORTÉE** (résidu `#1030-r1`), et c'est un **choix**. Le corps de
`…$$IsValidCenterTileForTargetArea` (dont `…$$GetDynamicInvalidTargetReason` est le jumeau, à
l'encodage du retour près) est lu à un slot près :

```
A = battleQuery.<slot 0x51 GetAdjacentTiles>(casterTiles, 0, 1, 1)
B = battleQuery.<slot 0x4f GetAdjacentTiles>(targetTile,  0, 1, 1)
A.<ISet<T> slot 1>(B)
return (A.Count == 1) ? 0 : 2
```

Les deux slots d'`IBattleQuery` sont NOMMÉS par `data/symbols/<build>/metadata/interface_slots.tsv`
(entrée versionnée, dérivée du metadata). Ce qui reste ouvert est le **slot 1 d'`ISet<T>`** :
`ExceptWith` et `IntersectWith` y sont adjacents dans l'ordre du source de référence, et les deux
donnent des ensembles **différents**. Écrire l'un des deux serait un fit ; ne rien écrire laisse le
gate PERMISSIF (`ActiveAbility.get_dynamic_invalid_target_reason` de base rend `0`).
**Aucune entrée dans `DYNAMIC_TARGET_RULE_UNPORTED`** : cette table n'est lue que par
`UnportedAbilityTargeting`, donc inatteignable pour une ability PORTÉE (mesure déjà écrite à
l'entrée 1185 de `targeting.py`).

## 4. La face DÉCISION — un coût SYSTÉMATIQUE du port de face combat

Porter la face COMBAT fait entrer l'ability dans `ABILITY_CLASSES`, et le cliquet `#1021`
(`test_1021_face_decision_au_registre_offline.py`) exige alors qu'un verdict dise ce qu'il en est de
sa face DÉCISION. **Mesuré** : `test_etage1_cranA_aucun_sans_verdict_hors_dette` rougissait sur
`[1094]` juste après le commit de la face combat, vert après le port du playbook. Attester
`RIEN_A_PORTER` aurait été FAUX — `TheLanternPlaybook` a du contenu.

```
IdunBattle.AI.Playbook.Loki.TheLanternPlaybook$$EvaluateNonComparable
    bucket = new Bucket(0, Nullable(<statics+0x00>))
    foreach (entities in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition)) {
        n = <ability>.GetTilesForTargetAreaFromTargetTile().<ITargetsSelector slot 2 Count>(entities)
        if ( !(Fix64(n) < Fix64(7)) )
            bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, <element>,
                                                          GetEnemiesHitUtilityForTarget(entities)))
    }

IdunBattle.AI.Playbook.Loki.TheLanternPlaybook$$GetEnemiesHitUtilityForTarget
    units = <zone>.<ITargetsSelector slot 4 SelectUniqueUnits>(entities, selectionType = 3)
    units.FilterInPlace(u => UnitExtensions$$IsEnemy(u, <caster>, <matchState>))   # b__0
    n1 = units.Count
    units.FilterInPlace(u => UnitExtensions$$HasTrait(u, 0x3ea = 1002 Psyker))     # b__5_1
    n2 = units.Count
    return Fix64(n1) * <statics+0x00> + Fix64(n2) * <statics+0x08>
```

`…$$.cctor` : `<statics+0x00> = Fix64(1)`, `<statics+0x08> = Fix64.FromIntFraction(1,10) = 0,1`.
La PREMIÈRE constante sert **deux fois** — `minUtility` du `Bucket` ET poids du terme d'ennemis ; le
même champ statique est chargé aux deux sites.

`…$$ShouldEvaluate(unit)` = `<IBattleQuery slot 0x1b>(unit, 2)` = `HasMinimumRemainingTurns(unit, 2)`
(slot nommé par `interface_slots.tsv`). Le gate a un sens mécanique : le cast n'inflige rien, son
dégât part au tour suivant.

⚠ **L'ORDRE des deux `FilterInPlace` est load-bearing** : `n2` compte les ennemis PSYKER, pas les
psykers de la zone. La garde le discrimine en plaçant un ALLIÉ psyker dans la zone.

## 5. Validation

**OFFLINE — `tests/engine/runner/test_1030_the_lantern_offline.py`, 11 tests, tous verts.**
Six étages, **quatre contre-épreuves** (chacune assertionne que la mutation CHANGE le résultat) :

| étage | ce qu'il fige | sa mutation |
|---|---|---|
| 1 | les trois registres ; masque `== 0x2000100042` (somme des bits) ; `CustomRange(2)` ; `Others` | — |
| 2 | la zone == oracle RE-DÉRIVÉ ; le « pont » non vide ET strictement inclus dans `ring2` | `op_BitwiseAnd` → `op_Addition` : la zone grossit |
| 3 | trois poses, `Pinned` sur le seul ennemi DANS la zone, **zéro dégât** | `Enemies` sans résolution de tuile : `Pinned` posé sur PERSONNE |
| 4 | l'attaquant = `EffectSource` ; l'instance porte bien `bonded is None` | table déclarée `ATTACKER_BONDED` : l'attaquant devient introuvable |
| 5 | le tir frappe les occupants COURANTS (une unité SORT, une ENTRE) ; les deux effets retirés | tour ADVERSE : rien ne part, la marque reste |
| 6 | `n1 + 0,1·n2` avec un ALLIÉ psyker dans la zone ; le gate `>= 7` mord au coin du board | — |

**DEUX ROUGES RÉELS rencontrés au montage**, tous deux instructifs :

* cible à distance 3 → `invalid_target = 134217728 = 0x8000000` : le `CustomRange(2)` est armé ;
* sans le seed `unitAbilityStates`, le nœud `TriggerAbility` rend
  `dispatched: True, notCarrying: [caster]` et le tir ne part pas — `1167` est une ability DÉRIVÉE
  (`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities`, peuplé au runtime), invisible du
  kit gameconfig. Même régime que 1069 (#513 §5).

**CLIQUETS DE REGISTRE**, dérivés (`git grep -l ABILITY_CLASSES -- scripts/python/tests`) :
`test_ability_registry_ratchet`, `test_targeting_options_sources`,
`test_503r3_registre_trigger_peuple_offline`, `test_996_no_op_silencieuses_offline`,
`test_287r12_role_target_tuile_offline` — **38 tests verts** ; `probe_181` **175/175, 0 manquante** ;
`probe_1021` **CRAN A/B/C OK** ; `test_1021` + `test_519` + `test_957` + `test_945` — **85 verts**.

**RAYON DE SOUFFLE de la réparation d'`Enemies`/`Friends`** (foyer très partagé) : 16 fichiers
offline choisis parmi ses consommateurs — **216 tests verts**. La réparation ne peut qu'ÉLARGIR
(les éléments non-`dict` étaient auparavant jetés en silence).

**CE QUI N'EST PAS COUVERT — et c'est le trou principal.**

* **NON CONFRONTÉ LIVE.** Le montage exact, prêt à jouer, est celui de
  `test_888_mortarion_boss_abilities_live.py` : `TACTICUS_ALLOW_ROSTER_DEFICIT=1`,
  `--explicit-stats deathBossMortarion:4`, board **`GB_Mortarion_05`**, `--hp-target 500000`
  `--crit 0,0` `--block-target 0,0`, boss côté joueur. Ce qu'il faut y ajouter, et qui n'existe dans
  aucun test live du dépôt : **DEUX bornes de tour** (`endturn` nu au tour adverse, puis `endturn`
  jusqu'au tour du boss) avec la mesure des PV **entre les deux** — c'est la seule façon de
  discriminer `EffectSource` de `BondedEntity` (§2.1) et de confirmer que la marque est relue au
  tir. Résidu `#1030-r3`.
* **L'empreinte 7-hex du caster côté DÉCISION** n'est reconstituée qu'à l'ORIGINE (résidu `#459-r1`,
  qui mord ici plus qu'ailleurs). Résidu `#1030-r2`.
* **La règle dynamique de ciblage** (§3), résidu `#1030-r1`.
* Le résidu d'étage annoncé par `#888-r1` — `AttackWithAbilityDamage` ne thread pas le
  `pierce_effect_bonus` des effets du caster, là où `AttackWithAttackDamage` le fait — **n'est pas
  traité ici** : il est inerte sur ce porteur (aucun effet de perçage sur Mortarion) et son foyer
  (`behaviours/combat.py`) est partagé par toute la famille ABILITY. Résidu `#1030-r4`.

## Résidus ouverts

* `#1030-r1` — la règle dynamique `…$$IsValidCenterTileForTargetArea` (slot 1 d'`ISet<T>` non
  départagé).
* `#1030-r2` — l'empreinte 7-hex du caster sur une position de MOUVEMENT, face DÉCISION.
* `#1030-r3` — la confrontation LIVE sur DEUX tours (elle falsifierait §2.1 en une mesure).
* `#1030-r4` — `pierce_effect_bonus` non threadé par `AttackWithAbilityDamage`.
