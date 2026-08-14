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

### 2.2 `Enemies` part d'ENTITÉS-TUILES et rend l'ACTEUR RÉSOLU — l'étage `SelectAllActors`

La conversion tuile → occupant appartient au **SÉLECTEUR**, et il a fallu **deux passes** pour la
lire : le domaine de RETOUR a oscillé, et la seconde lecture était celle de `master`.

`IdunBattle.Entities.Selectors.UnitsByTeamSelector$$CountOrAdd` fait bien
`System.Collections.Generic.List<T>.Add(result, entity)` avec l'entité **itérée** — mais ce qu'il
itère n'est pas `Select(entities)`. C'est le **slot 5 d'`ITargetsSelector`**, appelé sur son
sélecteur source `<UnitsByTeamSelector+0x20>` avec le `selectionType` de `<+0x2c>` (le référent, lui,
vient du **slot 8**). Ces deux slots sont `SelectAllActors` et `SelectActor`
(`data/symbols/<build>/metadata/interface_slots.tsv`, entrée versionnée ; leur arité 2 concorde), et
`IdunBattle.DSL.TargetsSelector$$SelectAllActors` **résout chaque élément** :

```
raw = this.<slot 0x17 Select>(entities)
if (this.<slot 0x21 get_ReturnsOnlyActors>) return raw;          // déjà des acteurs
foreach (entity in raw)
    u = SelectUnit(this, entity, selectionType);                  // <- LA RÉSOLUTION
    if (u != null) result.Add(u); else if (IsMachine(entity)) result.Add(entity);
```

et `IdunBattle.DSL.TargetsSelector$$SelectUnit` porte le
`if (IsUnitFoot(entity) || IsTile(entity)) entity = GetUnit(entity, state);`. L'`entity` ajouté par
`CountOrAdd` est donc **l'acteur déjà résolu**, et `GetUnitOrMachine` n'y est plus que l'identité —
ce qui explique qu'il ne serve qu'au test de camp.

**Trois recoupements, aucun n'étant le raisonnement qui a échoué :**

| recoupement | ce qu'il établit |
|---|---|
| fonction SŒUR — `$$SelectAllUnits` teste `+0x278` (slot 20 `get_ReturnsOnlyUnits`), `$$SelectAllActors` teste `+0x288` (slot 21 `get_ReturnsOnlyActors`) | même forme, slots adjacents ⇒ la grille de vtable est la bonne |
| `...NovaChargeAbility$$GetAdditionalMarkedTiles` enchaîne `NormalUnits(Enemies(Owner@+0x30, <TUILES>, 3), 3)` | un sélecteur d'UNITÉS consomme la sortie d'`Enemies` — absurde sur des ids de tuile |
| `IdunBattle.Entities.Selectors.UnitsMainTilesSelector$$Select` (le nœud `Tiles`) appelle le **slot 3 `SelectAllUnits`** puis `GetMainTile` | un sélecteur nommé « UnitsMainTiles » qui demande « SelectAllUnits » : `DAT_183383210` **est** `ITargetsSelector` |

⚠ **Le raccourci qui a fermé la piste des deux côtés** : « `AddEffectBehaviour`/`AddEffectOperation`
sont ABSENTS des xrefs de `GetUnit`, donc rien ne re-résout ». L'absence ne conclut pas — la
résolution est **indirecte**, via `SelectUnit`. Les deux fonctions ont donc été lues *directement* :
`AddEffectBehaviour$$Execute` prend ses cibles au **slot 0 `Select`** (entités brutes, aucune
résolution) et `AddEffectOperation$$Execute`, lue **intégralement**, pose sur `owner` tel quel
(`EntityExtensions$$IsUnit` + `UnitExtensions$$HasFlag(owner, 6)`, aucun `GetUnit`). Le contrat
négatif est donc CONFIRMÉ, et il ne laisse qu'un seul emplacement possible à la résolution : le
sélecteur. **L'arbre de `1094` est juste** (décompilé relu mot pour mot : `Enemies` alimente
directement `AddEffect(0x429)`, sans `Units` intermédiaire) — c'est la FEUILLE qui ratait un étage.

**Deux fautes distinctes, deux gardes :** le port normalisait par `_units_of` puis jetait tout ce
qui n'était pas un `dict` (une source tile-domain rendait `[]`, **sans erreur**) ; puis, une fois
la résolution posée, il réinjectait l'entité SOURCE au lieu de l'acteur (même `[]` en aval, car
`AddEffect` recevait des `int`). Réparé dans `entities/selectors/units.py` sur `Enemies` **et**
`Friends` — même classe native, flag `+0x28` = 0/1 —, jamais contourné par un `Units(…)` que le
natif n'écrit pas. Second régime, plus discret : une ENTITÉ-TUILE (dict à `visualId` NUL) passait
le `isinstance(dict)` et, sa clé `team` étant absente, comptait pour un **ennemi**.

⚠ **Pourquoi la faute était INVISIBLE**, et c'est ce qui l'a fait survivre : sur les ~600
call-sites unit-domain, `GetUnitOrMachine(unit) == unit` rend les **deux lectures identiques**. Et
chez le seul autre call-site tile-domain (`1032 NovaCharge`), la sortie passe par `Tiles(…)`, qui
re-résout lui-même (slot 3) et rend le **même ensemble** dans les deux lectures. Le domaine ne se
voit que là où la sortie est consommée **sans re-résolution** : `AddEffect`, ici.

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

**OFFLINE — `tests/engine/runner/test_1030_the_lantern_offline.py`, 12 tests, tous verts.**
Six étages, **cinq contre-épreuves** (chacune assertionne que la mutation CHANGE le résultat) :

| étage | ce qu'il fige | sa mutation |
|---|---|---|
| 1 | les trois registres ; masque `== 0x2000100042` (somme des bits) ; `CustomRange(2)` ; `Others` | — |
| 2 | la zone == oracle RE-DÉRIVÉ ; le « pont » non vide ET strictement inclus dans `ring2` | `op_BitwiseAnd` → `op_Addition` : la zone grossit |
| 3 | trois poses, `Pinned` sur le seul ennemi DANS la zone, **zéro dégât** | `Enemies` sans résolution de tuile : `Pinned` posé sur PERSONNE |
| 3bis | le DOMAINE DE RETOUR d'`Enemies` est l'ACTEUR, pas la TUILE (§2.2) | `out.append(e)` — la forme de `master` : résolution correcte, camp correct, et `Pinned` sur PERSONNE |
| 4 | l'attaquant = `EffectSource` ; l'instance porte bien `bonded is None` | table déclarée `ATTACKER_BONDED` : l'attaquant devient introuvable |
| 5 | le tir frappe les occupants COURANTS (une unité SORT, une ENTRE) ; les deux effets retirés | tour ADVERSE : rien ne part, la marque reste |
| 6 | `n1 + 0,1·n2` avec un ALLIÉ psyker dans la zone ; le gate `>= 7` mord au coin du board | — |

L'étage **3bis** existe parce que les gardes d'origine visaient toutes l'ABSENCE DE RÉSOLUTION,
jamais le DOMAINE DE RETOUR — l'axe qui a réellement oscillé. **Mutation adversariale jouée sur le
code source** (les 2 sites remis à `out.append(e)`) : **4 gardes rougissent** — les trois étages 3
ci-dessus et `test_1032…::test_etage3_enemies_resout_la_tuile_en_son_occupant` — puis 23/23 verts
après restauration.

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

**RAYON DE SOUFFLE de la réparation d'`Enemies`/`Friends`** — foyer très partagé : **616
call-sites sur 141 fichiers**. Mesuré par **empreinte des DEUX arbres** sur les **395** fichiers
`*_offline.py` du dépôt (~5 700 tests, ~30 min en 10-12 lots parallèles), et non sur une sélection
de consommateurs choisie à la main : **43 échecs avant, 41 après**. Bascules — **2 réparés** (les
deux rouges cibles) et **1 seul nouveau rouge** :
`test_1032_novacharge…::test_etage3_enemies_resout_la_tuile_en_son_occupant`.

Ce test unique attendait `[<id de tuile>]` et portait mot pour mot l'énoncé que la RE réfute. Il
est corrigé **par la mesure**, son INTENTION préservée (le nœud ne rend toujours pas `[]` sur un
domaine TUILE, et sélectionne toujours la seule tuile à occupant ENNEMI ; seul le domaine de RETOUR
change), et il gagne un **cliquet de domaine** (`isinstance(x, dict)`). Le choix d'une batterie
DÉRIVÉE plutôt que choisie est ce qui a rendu ce test visible : une sélection « parmi les
consommateurs » ne l'aurait pas contenu.

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
* `#1030-r6` — les DEUX écarts que la lecture de `$$SelectAllActors` laisse non portés (§2.2) :
  **(a)** le court-circuit `get_ReturnsOnlyActors` / `get_ReturnsOnlyUnits` rend `Select(entities)`
  TEL QUEL, donc **sans appliquer le `selectionType`**, là où le port applique toujours
  `_selection_ok` ; **(b)** la branche `else if (IsMachine(entity)) result.Add(entity)` ajoute une
  MACHINE qui a échoué `SelectUnit` — donc y compris quand elle ne matche pas le `selectionType` —,
  alors que le port n'a pas de domaine machine distinct (`unit_or_machine` rend un dict d'unité).
  Aucun des deux n'est atteint par les régimes portés à ce jour ; les écrire sans porteur
  confrontable serait spéculatif.
