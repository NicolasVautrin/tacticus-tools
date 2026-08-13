# #1022 — `AetherStride` (1208) : la face COMBAT d'un `[-D]`, et pourquoi ce n'est pas `DutyEternal`

**Verdict : PORTÉ et CONFRONTÉ.** `AetherStride` était l'une des **deux seules** actives npc en
`[-D]` du registre (face DÉCISION portée, face COMBAT absente) : `ABILITY_CLASSES.get(1208)` rendait
`None`, donc l'IA la **choisissait** et le moteur ne l'**exécutait pas** — en silence, en consommant
le tour. Après cette tranche, `docs/rl/npc-registry.tsv` compte `[-D] = 1` (il ne reste que `1215
InstrumentsOfVengeance`, ouverte en résidu `#1022-r2` avec sa RE ci-dessous).

## 1. L'artefact natif

`IdunBattleLogic.Entities.Abilities.Active.Loki.AetherStrideAbility$$ExecuteBehaviour` est un
**arbre de nœuds `DSLFactory` PUR** — aucun `Operation.Execute`, aucun `ApplyModification`. La
forme du port est donc un arbre DSL, et c'est ce qui a été livré (`engine/runner/abilities/
thousandsons.py`, `aether_stride_tree` / `aether_stride_on_appearance`).

```
opts    = SpawnUnitOptions$$WithStatsFromConfig( config@this+0x60, abilityState, 0, 0 )
grant   = DSLBehaviors$$AddTrait( ActiveTarget@DSLSelectors+0x68, 0x418, null )
carry   = DSLBehaviors$$If(
              DSLTriggers$$ActorHasTriggeredAbility( Owner@DSLSelectors+0x30, 0x5d8 ),
              DSLBehaviors$$AddTriggeredAbility(
                  ActiveTarget@DSLSelectors+0x68, 0x5d8,
                  DSLSelectors$$AbilityState( Owner@DSLSelectors+0x30,
                                              AbilityType$$op_Implicit(abilityState) ) ),
              null )
psykers = DSLFormulas$$Count(
              DSLSelectors$$UnitsWithTrait(
                  DSLSelectors$$AdjacentFriends( ActiveTarget@DSLSelectors+0x68,
                                                 unique: true, selectionType: 3 ),
                  0x3ea, selectionType: 3 ) )
strike  = DSLBehaviors$$If( psykers,
              DSLBehaviors$$PerformAIAttack( ActiveTarget@DSLSelectors+0x68, allowOnlyMove: 0,
                                             overrideMovement: DSLFormulas+0x18,
                                             utilityEntity: null, customUtility: null ),
              null )
opts.<+0x18> = AbilityBehaviour$$op_Addition( AbilityBehaviour$$op_BitwiseAnd(grant, carry), strike )
opts.<+0x50> = UnitExtensions$$GetQuestUnitId( caster )        # champ de QUETE, non porte
opts.<+0x60> = 1                                               # UNE unite sur TOUTES les tuiles
return AActiveAbility$$Execute( entities, this,
           AbilityBehaviour$$op_BitwiseAnd(
               DSLBehaviors$$RemoveMachine( Caster@DSLSelectors+0x48 ),
               DSLBehaviors$$Spawn( Caster@DSLSelectors+0x48,
                                    DSLSelectors$$ThreeTileUnitSpawnShape( Target@DSLSelectors+0x60 ),
                                    AbilityConfiguration$$GetStringConstant( config, 0 ),
                                    opts ) ) )
```

`gameconfig` : `constants = {unitId: thousSmnDaemonPrince, initialCooldownTurns: 1,
munitionsCost: 1}` ; variables `summonHp` / `summonDmg` / `summonArmor`.

### Le ctor — forme FLAGS DIRECTS

`...AetherStrideAbility$$.ctor` appelle `IdunBattle.Core.Services.TargetingOptions$$.ctor(&opts, 0,
&<TargetingRange statics>+0x48, 1, 0x20000040000042, 0, 0)` puis `AActiveAbility..ctor(this, &opts,
2)`. Le littéral **EST** le masque effectif (ni overload PRESET+FLAGS, ni recopie de champ statique) :

| donnée | valeur | lecture |
|---|---|---|
| `rules` | `0x20000040000042` | `TargetMatchesDynamicRule \| TargetIsTile \| AllowNullCasterTile \| CasterIsMachine` |
| `range` | `<TargetingRange statics>+0x48` | `RANGE_WHOLE_BOARD` |
| `forceMeleeTarget` | `1` | `RangedBool.False` |
| `AbilityAttackType` | `2` | `Others` |

## 2. Ce n'est PAS son voisin de forme, et c'est le cœur du cas

`DutyEternalAbility` (1158) partage **mot pour mot** les deux derniers nœuds et le ctor **octet pour
octet** (mêmes classe statique, offset `+0x48`, littéral de flags, littéral `2` — les deux décompilés
ont été comparés côte à côte, pas déduits l'un de l'autre). Trois divergences, toutes **lues** :

1. **Le transfert de triggered ability n'est pas le même nœud.** 1158 lit le
   `TriggeredAbilityComponent` du caster **à la construction** (`if (coll.Count > 0)` puis
   `Enumerable.First`) et appelle la surcharge `AddTriggeredAbility(sel, id, levelInfo)`. 1208 ne lit
   rien à la construction : c'est un `If(ActorHasTriggeredAbility(Owner, 0x5d8), ...)` DSL sur un id
   **fixe**, et il vise l'**autre** surcharge, dont le 4ᵉ paramètre est un `abilityStateSelector`.
   Les deux surcharges portent le même nom affiché ; **seules les xrefs entrantes les séparent**
   (l'appel de `...AetherStrideAbility$$ExecuteBehaviour` vise celle à `abilityStateSelector`).
2. **1208 porte un second terme absent de 1158** : le Daemon Prince attaque immédiatement s'il
   apparaît au contact d'un allié Psyker.
3. **Les deux opérateurs de jointure diffèrent** : `op_BitwiseAnd` puis `op_Addition`. Voir §4.

Même piège sur `AdjacentFriends` : **deux surcharges d'arité 4**, indiscernables dans le pseudo-C.
La xref entrante donne la **variante A** `(this, unit, unique, selectionType)` =
`Friends(reference = unit, Units(AdjacentTiles(unit), unique, selectionType) - unit, selectionType)`.
La référence d'équipe est donc `ActiveTarget` (le summon), **pas le caster** — le port passe
`reference=ActiveTarget()` explicitement, le collapse historique pariant sur l'équipe d'une MoW que
le même arbre vient de retirer.

Et `PerformAIAttack` : `DSLFormulas$$.ctor` construit `+0x18` comme la formule constante `0`
(voisins `+0x20 = 1`, `+0x28 = 2`, `+0x30 = 100`, `+0x38 = -1`), et
`DSLBehaviors$$PerformAIAttackFromCurrentPosition` construit son `PerformAIAbilityUnitBehaviour`
avec exactement `allowOnlyMove = 0` / `overrideMovement = <DSLFormulas+0x18>`. Le call-site de 1208,
bien qu'il passe par la fabrique « générale », **est** le régime « depuis la position courante » —
donc les défauts de la feuille portée. Lui donner `allow_move_action=True` au motif que la fabrique
s'appelle `PerformAIAttack` produirait le régime de `ForwardSpotterAbility`, qui passe
`allowOnlyMove = 1`.

## 3. Le montage — GREFFE, et **deux** écritures dont une échoue en silence

Porteur unique : `thousNpcMowDaemonPrince` (npc, **absent de `BC.Units` du seed**). Greffe sur
`ultraDreadnought` (MoW du pool, porteur natif de 1158) — condition vérifiée au décompilé : le natif
charge le playbook **par ability**, et l'arbre de 1208 ne lit du caster ni stat ni trait (seulement
`Caster@+0x48` et `Owner@+0x30`).

⚠ **La greffe passe par `catalog_inject.graft_active_ability`, jamais par un
`u["ActiveAbilities"] = [aid]` à la main.** Mesuré ici : `_load_seed_bc` re-synthétise bien
`BC.Abilities`, mais **seulement pour les abilities déjà présentes** — `AetherStride` n'y figurait pas
(131 clés). Sans la seconde écriture (la **config** d'ability), la greffe passe **tous** les gates
(`casterReason` et `targetReason` valent `0x0`, `decisionView` la dit `usable`) et le cast rend
**« system error » en consommant le tour** (`actionConsumed: true`, `spawned: 0`,
`UnitStats_ActionsAvailable: 0`) — verrou #226. **Ce symptôme est indiscernable du bug qu'on
cherche** (« l'IA choisit, le moteur n'exécute rien ») et l'aurait donc confirmé à tort.

⚠ Deuxième canal lu à côté, même famille de faute : `abilityReason` prend `casterId`/`abilityType`
et rend son verdict dans **`targetReason`**, pas à la racine. Lu à côté (`reason` à la racine), il
« accepte » **toute** tuile : la première passe rendait 15 accords / 9 écarts avec `reason=None`
partout — un oracle structurellement muet. Corrigé : **24/24 d'accord, les deux verdicts présents**.
Troisième : `observeBattle.units[]` **ne publie pas les traits** ; les lire au gameconfig par
`visualId`, sinon « aucun psyker adjacent » pour toute unité.

## 4. Ce que la validation a trouvé — et un écart antérieur, nommé

`IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd` et `$$op_Addition` ont le **même corps**
(`+0x50 = left`, `+0x58 = right`) mais allouent **deux pointeurs de classe distincts** : ce sont deux
classes de behaviour, pas un alias. **Le port les collapse en un seul `Seq`** — écart **antérieur à
cette tranche**, assumé et documenté sur `entities/behaviours.py::Seq`. La première rédaction de
cette tranche affirmait le contraire (« `Seq` porte le flag ») et posait une assertion sur un attribut
`stop_on_result` **qui n'existe pas** ; corrigé. L'écart est **inerte ici**, et la raison se vérifie
au lieu de se supposer : les trois termes de l'arbre (`AddTrait`, les deux `If`) sont **purs**, donc
aucun ne pose le flag qui ferait court-circuiter la jointure de gauche. Le site écrit quand même
`op_and` puis `op_add` aux bons endroits.

## 5. Mesures

Montage : `probe_1022_aether_stride.py` (board `MC1_67`, seed 777, `ultraDreadnought` greffé,
`ultraTigurius` déplacé au contact de l'empreinte). Garde : `tests/engine/runner/
test_1022_aether_stride_live.py`, **7 tests verts**.

| étage | natif | port | verdict |
|---|---|---|---|
| A — `GetDynamicInvalidTargetReason` | 15 tuiles acceptées / 9 refusées sur 24 | idem | **24/24**, non dégénéré |
| B — empreinte du spawn | `[(1,2),(2,1),(2,2)]`, 1 squad, `thousSmnDaemonPrince` | mêmes 3 pieds, même ordre | **ACCORD** |
| C — `AddTrait` / `RemoveMachine` | non lisible directement | `Stationary` posé, 0 position mobile, `MachineComponent.removed`, `alive` inchangé | conforme |
| D — prédicat `PerformAIAttack` | — | `ai_attacks` **vide** sans psyker adjacent, **non vide** avec | contraste **net** |

**Mutants** (le mécanisme cassé, la garde doit tomber) :

| mutation | test rouge | message |
|---|---|---|
| terme `PerformAIAttack` retiré (= recopier 1158) | `test_tree_is_not_its_form_neighbour` | ``` `DSLBehaviors$$If(formula, ...)` est litteralement `If(DSLTriggers$$AmountIsGreaterThanZero(formula), ...)` -- le seuil est `> 0` ``` |
| `spawn_as_single_unit=False` | `test_port_cast_matches_the_native_footprint` | `empreinte portee [(1, 2)] != native [(1, 2), (2, 1), (2, 2)]` |
| `UnitTrait.Psyker` -> `BigTarget` | `test_port_perform_ai_attack_fires_only_with_an_adjacent_psyker_friend` | `avec un allie Psyker au contact de l'empreinte, le noeud PerformAIAttack DOIT s'executer` |

### NON couvert, et nommé

- **L'attaque elle-même** (`PerformAIAbilityUnitBehaviour$$Execute`) : le summon se pose hors de
  portée de tout ennemi dans ce montage, donc `attacks` est vide **des deux côtés** — accord en
  régime dégénéré, qui ne dit rien du choix de cible ni du dégât. Le prédicat, lui, est confronté par
  contraste. Résidu `#1022-r3`.
- **La branche « le caster possède `0x5d8` »** : `ultraDreadnought` n'a pas `CabalOfSorcerers`, donc
  `carry` ne s'assemble pas. Même statut que la branche jumelle de 1158 (résidu de `case-91` §7).
- **Le 4ᵉ argument d'`AddTriggeredAbility`** (`AbilityState(Owner, AbilityType)`) : la feuille portée
  n'expose que `(units_sel, ability_id)` — le niveau/cooldown hérités ne sont pas reportés. Inerte
  tant qu'aucun consommateur porté ne les lit. Résidu `#1022-r1`.

## 6. `audit_npc_registry.py` était INEXÉCUTABLE sur `master`

Constaté en régénérant l'artefact que ce cas fait bouger : `#1015` a supprimé
`audit_kit_coverage.TRAIT_COMMON_MAX` (remplacé par `trait_channels`), mais `audit_npc_registry.py`
l'importait encore (3 sites) → `ImportError`, donc `npc-registry.tsv` — **la source de la mesure qui
définit ce lot** — ne pouvait plus être régénéré. Réparé **dans le sens de #1015** : on n'écarte plus
aucun trait par fréquence, `_trait_couvert` répond trait par trait.

## 7. La RE d'`InstrumentsOfVengeance` (1215) — résidu `#1022-r2`

Le second `[-D]` déborde du plafond de cette tranche (deux factions, deux montages). Sa RE est
écrite ici pour que le successeur n'ait pas à la refaire.

**Artefact** : `IdunBattleLogic.Entities.Abilities.Active.Loki.InstrumentsOfVengeanceAbility$$
ExecuteBehaviour` — arbre DSL, mais **d'un ordre de grandeur au-dessus** de 1208.

```
a = GetEffectBehavior(direction: 1, first: true) + GetEffectBehavior(direction: 5, first: false)
b = GetEffectBehavior(direction: 2, first: true) + GetEffectBehavior(direction: 4, first: false)
r = DSLBehaviors$$If( DSLTriggers$$Maybe(0x32 = 50 %), a, b )
r = r + DSLBehaviors$$AddBondEffect( 0x5ef, get_AbilityStateReference(this),
                                     Owner@+0x30, Owner@+0x30, Owner@+0x30, <options nulles> )
r = r + DSLBehaviors$$If(
            AbilityTrigger$$op_LogicalNot( DSLTriggers$$HasAdjacentEnemies(Owner, Owner, 0, ...) ),
            DSLBehaviors$$ActivateEffect( Owner@+0x30, 0x3f1 ), null )
return AActiveAbility$$Execute(entities, this, r)
```

et `...InstrumentsOfVengeanceAbility$$GetEffectBehavior(direction, first)` :

```
behind = DSLSelectors$$TilesBehindInLine( ActiveTarget@+0x68,
                                          DSLFormulas$$Get(EdgeExtensions$$Rotate(direction, 3)) )
edge   = DSLSelectors$$EdgeTilesByDirection( DSLFormulas$$Get(direction) )
if (!first)                       # la SECONDE passe retranche les tuiles deja prises
    edge -= TilesBehindInLine( Entity(GetPersistentData(<cle A>)), Entity(GetPersistentData(<cle B>)) )
sel = DSLSelectors$$Randomize(edge)
sel = SortByFormula( sel, Count(behind) )
sel = SortByFormula( sel, Count(Friends(Owner, Units(behind + ActiveTarget@+0x68, true, 3), 3)), desc )
sel = SortByFormula( sel, Count(Enemies(Owner, Units(behind + ActiveTarget@+0x68, true, 3), 3)) )
sel = DSLSelectors$$Cache( DSLSelectors$$First(sel, 1) )
r   = SetPersistentData( <cle A + i>, EntityId(sel) )
    + SetPersistentData( <cle B + i>, EntityId(First(TilesBehindInLine(sel, ...))) )
return r + DSLBehaviors$$AddEffect( 0x5ee, get_AbilityStateReference(this), Owner@+0x30,
                                    sel + TilesBehindInLine(sel, ...), <options nulles> )
```

**Ordinaux qualifiés** : `0x5ee` = 1518 `EffectType.InstrumentsOfVengeance_LocationTarget` ;
`0x5ef` = 1519 `EffectType.InstrumentsOfVengeance_PendingAttack` ; `0x3f1` = 1009
`EffectType.Overwatch_AutoAttack` ; `0x32` = 50 (pourcentage de `Maybe`, **pas** un enum) ;
`1/5/2/4` = des `IdunBattle.Utils.Hex.Edge` (argument de `EdgeExtensions$$Rotate`).

**Ctor — forme STATIC-COPY** : `...InstrumentsOfVengeanceAbility$$.ctor` **n'appelle aucun**
`TargetingOptions$$.ctor` ; il recopie les 0x40 octets de `<TargetingOptions statics>+0x280` puis
`AActiveAbility..ctor(this, &opts, 2)` → `Others`. Le masque effectif est la constante écrite par
`TargetingOptions$$.cctor` en `<preset>+0x28` : **`0x8004` = `CasterIsPossibleTarget |
CasterMatchesDynamicRule`**, `range = RANGE_SELF`, `forceMeleeTarget = 1`. Cette lecture est **déjà
faite et déjà écrite** dans `TARGETING_OPTIONS_UNPORTED[1215]` (`abilities/targeting.py`, #27-r6) —
l'entrée sera **migrée vers la classe** au portage, comme l'ont été 1216 et 1093.

**Ce qui manque au port** (les étages, dans l'ordre de coût) :

| étage | état |
|---|---|
| `DSLSelectors$$EdgeTilesByDirection` | **absent** du port (0 occurrence) |
| `DSLBehaviors$$SetPersistentData` | 1 seule occurrence — à vérifier |
| `DSLSelectors$$Randomize`, `SortByFormula` | 1 occurrence chacune |
| effets `1518` / `1519` | classes d'effet à porter (`_LocationTargetEffect`, `_PendingAttackEffect`) |
| `...InstrumentsOfVengeance_AttackAbility` | triggered ability séparée (`AttackLine`, `AttackTileBehavior`, `AttackTargetTiles`, `CreateBehaviour`) |

**Confrontabilité** : porteur `darkaBossLion` (npc). `1215` étant `self_cast` avec un masque armé
par des bits de domaine, la greffe sur une unité du pool est licite (même argument qu'ici) — mais
`darkaSmnTerminator` (`constants.unitId`) et la présence des configs d'effet dans `BC` sont à
vérifier avant. `probe_27_r6_instruments_of_vengeance.py` et `probe_513_pending_attack_family.py`
existent déjà comme points d'entrée.

## Résidus ouverts

- `#1022-r1` — le 4ᵉ argument d'`AddTriggeredAbility` (`AbilityState(Owner, AbilityType)`) n'est pas
  porté : niveau/cooldown hérités non reportés.
- `#1022-r2` — face COMBAT d'`InstrumentsOfVengeance` (1215), RE ci-dessus.
- `#1022-r3` — l'attaque de `PerformAIAttack` non confrontée (aucun ennemi à portée du point de
  spawn dans le montage).
