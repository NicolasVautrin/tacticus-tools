# case-224 (item 2) — `CursedPlagueBell_ExtraMove` (1073) : le +1 Movement qui doit REDESCENDRE

Deuxième item de la fiche #224. Ne porte QUE la **classe d'effet** `CursedPlagueBell_ExtraMove`
(EffectType `0x431` = 1073) ; le vecteur de pose (`CursedPlagueBellMovementAbility`), la
`DangerZone` (1084) et la face attaque sont d'autres items. La face PLAYBOOK de `CursedPlagueBell`
(1071) est portée et validée par `case-211`.

Porteur de l'aura : `deathBlightbringer` (« Corrodius », Death Guard) — **POOL-HERO** rank 17,
présent tel quel dans `rl_duel.py build --list-pool`.

i2 `Abilities/CursedPlagueBell_CurrentLevelDescription` : « Friendly **Chaos** units **starting
their turn** within Corrodius' **Contagion** aura gain **+{[extraMovement]} Movement** for this
turn. »

---

## 1. Le décompilé (build `rnca9r7q6c`)

### 1.1 Une classe d'effet NATIVE bespoke, pas la feuille générique

C'est le fait qui distingue ce cas des deux autres +MOVEMENT déjà portés (`BlackRage_ExtraMove`
1342, `Waaagh_ExtraMovement` 1099) : ceux-là n'ont **aucune** classe native et reçoivent leur
stat-mod de la feuille `AddStaticStatModifierEffect`. Ici la classe existe, dérive directement de
`IdunBattle.Entities.Effects.BaseEffect` (classes.tsv, taille 1152), et **émet elle-même** son
`ChangeStat` — quatre corps natifs, **deux à deux identiques** (folding IL2CPP : `ApplyInternal`
délègue à `AddStatModifier`, `RevertInternal` à `RevertStatModifier`) :

```csharp
// IdunBattle.Entities.Effects.Loki.CursedPlagueBell_ExtraMoveEffect$$ApplyInternal
//   == IdunBattle.Entities.Effects.Loki.CursedPlagueBell_ExtraMoveEffect$$AddStatModifier
DSLBehaviors.ChangeStat( targets              = DSLSelectors.Entity(target),
                         stat                 = Stat(1 = Movement, 5 = Modification),
                         mode                 = 4 = ChangeStatMode.Modify,
                         amount               = DSLFormulas.Direct(
                                                    AbilityConfiguration.GetNumberConstant(
                                                        cfg@this+0x60, 0xe = extraMovement) ),
                         modificationEntity   = DSLSelectors.Entity(effect),
                         selectionType        = 1 = UnitSelectionType.OnlyAlive,
                         isModifiable         = false,
                         isHiddenModification = false )

// IdunBattle.Entities.Effects.Loki.CursedPlagueBell_ExtraMoveEffect$$RevertInternal
//   == IdunBattle.Entities.Effects.Loki.CursedPlagueBell_ExtraMoveEffect$$RevertStatModifier
//   le MEME appel, seuls la `part` et le montant changent :
                         stat   = Stat(1 = Movement, 6 = ResetModification),
                         amount = <DSLFormulas+0x18> = Direct(0)
```

`IdunBattleLogic.Entities.DSLBehaviors$$ChangeStat` a la signature
`(targets, stat: IdunBattleLogic.Battle.Stat, mode: ChangeStatMode, amount: IAmountFormula,
modificationEntity, selectionType, isModifiable, isHiddenModification)` (methods.tsv).

### 1.2 Les trois lectures qui ne se devinent pas

**a) L'ORDRE du struct `Stat`.** Son ctor est mislabellé `UnityEngine.TerrainUtils.TerrainTileCoord$$.ctor`
par ghidra ; ses deux littéraux sont `(1, 5)` à l'apply et `(1, 6)` au revert. C'est donc
`(statType, part)` : `IdunBattle.Entities.Enum.StatPart` vaut `5 = Modification` /
`6 = ResetModification`, exactement la paire apply/revert que décrit déjà
`effects/__init__.py::effect_stat_mod_key` (« seule la `part` change, 5|9 à l'apply, 6 au revert »).
Lu comme `(part, statType)` on obtiendrait `Health -> Shield` entre l'apply et le revert.
`IdunBattle.Entities.Enum.StatType` : `1 = Movement`.

**b) `DSLFormulas+0x18` = `Direct(0)`.** `IdunBattleLogic.Entities.DSLFormulas$$.ctor` met en cache
cinq `Direct` constants aux slots `+0x18 .. +0x38` : `0, 1, 2, 100, -1`. Le revert passe donc un
montant **nul** — c'est la `part = ResetModification` qui retire la contribution, pas le montant.

**c) La source est l'ENTITÉ-EFFET** (`modificationEntity = Entity(effect)`), donc **une seule**
entrée `ValueModification.per_source` par instance. C'est ce qui rend le retrait exact — et c'est
vérifiable live : `statModSources` rend `movement = {total: 1, residual: 0, bySource: [{source:
<entité-effet>, amount: 1, sourceIsUnit: false}]}`.

### 1.3 Il n'y a RIEN d'autre à porter sur cette classe — bloc contigu, pas d'argument d'absence

Ce n'est pas « la méthode n'est pas dans la table » (qui ne prouve rien, cf. CLAUDE.md) : le bloc de
code des deux classes `CursedPlagueBell_*Effect` est **contigu et sans trou d'adresse** dans
`data/symbols/rnca9r7q6c/ghidra/functions.tsv`, encadré par `CrushingStrikeEffect$$.ctor` juste avant
et `SynapseEffect$$ApplyInternal` juste après :

```
CursedPlagueBell_DangerZoneEffect$$CreateRangeBonusForDangerZone
CursedPlagueBell_DangerZoneEffect$$CreateTargetSelector
CursedPlagueBell_DangerZoneEffect$$GetExtraMovementAmount
CursedPlagueBell_DangerZoneEffect$$.ctor
CursedPlagueBell_ExtraMoveEffect$$AddStatModifier
CursedPlagueBell_ExtraMoveEffect$$ApplyInternal
CursedPlagueBell_ExtraMoveEffect$$RevertInternal
CursedPlagueBell_ExtraMoveEffect$$RevertStatModifier
```

Les voisins montrent qu'une classe d'effet émet bien toutes ses méthodes d'affilée — et
`DangerZoneEffect`, dans le MÊME bloc, y a son `CreateTargetSelector` là où `ExtraMoveEffect` n'en a
pas. `CursedPlagueBell_ExtraMoveEffect` **ne surcharge donc que ces quatre corps** : pas de
`CreateActiveCondition` (d'où le canal EAGER plutôt que déclaratif), pas de `CreateTargetSelector`,
aucune contribution aux canaux dégât/coups/perçage.

### 1.4 Le vecteur de pose (contexte — autre item)

```csharp
// IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellMovementAbility$$CreateBehaviour
DSLBehaviors.AddEffect( 0x431 = 1073 CursedPlagueBell_ExtraMove,
                        GetAbilityStateReference(this),
                        UnitsWithoutTrait(
                            UnitsWithTrait(
                                SurroundingFriends( Caster@dsl+0x30,
                                                    range  = ContagionsOfNurgleRange(Caster, 0, false),
                                                    unique = true, unitSelectionType = 3 ),
                                0x7ea = 2026 Chaos, 3 ),
                            0x418 = 1048 Stationary, 3 ),
                        turns = Nullable<int>(1) )
```

`SurroundingFriends(unit, range, unique, unitSelectionType)` est un **anneau** — le porteur de
l'aura est EXCLU de sa propre sélection (le 3e argument est `unique`, pas un « includeSelf »).
Le même sélecteur est réutilisé tel quel par
`IdunBattle.Entities.Effects.Loki.CursedPlagueBell_DangerZoneEffect$$CreateTargetSelector`.

---

## 2. Ce qui a été porté

| Fichier | Contenu |
|---|---|
| `engine/entities/effects/loki/cursed_plague_bell.py` (**neuf**) | `CursedPlagueBellExtraMoveEffect` — canal EAGER `applied_stat_mods` (= la forme OVERRIDE d'`ApplyModification`) + `reverted_stats` (= `Stat(Movement, ResetModification)`) |
| `engine/entities/effects/loki/__init__.py`, `factory.py` | export + entrée `EFFECT_CLASSES["CursedPlagueBell_ExtraMove"]` |
| `scripts/python/probe_224_cursed_plague_bell_extramove.py` (**neuf**) | mesure live en 7 étapes + mutation `--mutate registry` |
| `tests/engine/runner/test_cursed_plague_bell_extramove_live.py` (**neuf**) | 4 gardes live (attribution par-source, gate d'appartenance, revert à l'expiration, **absence de dérive** sur 3 cycles) |
| `tests/engine/runner/test_seeded_eager_statmod_expiry.py` | tableau des durées corrigé (2 membres à timer, plus 1) + garde offline du croisement R16 × O3 pour 1073 |

**Pourquoi le canal EAGER et pas le canal déclaratif** (`get_stat_modification_stat`/`_amount`, celui
de `DestroyTheWitch_ExtraMove`) : le natif n'appelle pas la base — il **override**, comme
`BlackRage_ExtraMove` / `Waaagh_ExtraMovement` / `ActOfFaithBuffEffect`. Et il n'y a **aucun**
`CreateActiveCondition` sur cette classe : la durée de vie vient du `turns = 1` du vecteur, pas
d'une condition d'activité — le canal déclaratif (piloté par `RefreshEffectsOperation`) n'aurait
donc rien à piloter.

**Ce que ça change réellement.** La stat MOVEMENT captée est déjà bonifiée : sans le port, la valeur
COURANTE est juste. Le port ferme le bout d'après — l'**attribution** : sans lui, le +1 reste dans
le résidu opaque `CAPTURED_SOURCE`, donc **non retirable**, et à l'expiration (l'effet dure UN tour)
l'unité garde son +1 à vie offline alors que le natif le retire. C'est l'incohérence « effet absent,
buff présent » que `test_seeded_eager_statmod_expiry.py` interdit déjà pour `Waaagh_ExtraMovement`.

`CursedPlagueBell_ExtraMove` est le **deuxième** membre du gisement EAGER à porter un vrai timer
(le premier était `Waaagh_ExtraMovement`) — le tableau des durées de ce fichier de garde est corrigé
en conséquence.

---

## 3. Validation live

Runner isolé, rosters explicites `deathBlightbringer, worldJakhal, blackAbaddon, astraBullgryn`
vs `necroWarden ×2`. **Deux couples (board, seed)** : `MC1_67/777` et `C4_09/31337`.

### 3.1 Le cycle de vie observé

Sur `MC1_67/777`, en enchaînant les `endturn` (`decisionView` + `combatSnapshot`) :

| instant | u83 `worldJakhal` | u85 `blackAbaddon` | u81 Corrodius | u87 `astraBullgryn` |
|---|---|---|---|---|
| tour du joueur | 1073 `remaining=1`, movement **4** | 1073 `remaining=1`, movement **4** | pas d'effet, movement 2 | pas d'effet, movement 3 |
| tour adverse | effet PARTI, movement **3** | effet PARTI, movement **3** | movement 2 | movement 3 |
| tour du joueur suivant | 1073 **re-posé** (nouvel `effectId`), movement **4** | idem | movement 2 | movement 3 |

Base gameconfig : `worldJakhal` 3, `blackAbaddon` 3 → le `+1` est bien `extraMovement`. Le champ
`statMod` de `decisionView.effects` est **`null`** pour 1073 : confirmation live que ce n'est pas un
`StaticStatModifierEffect` mais bien la classe bespoke.

Le **gate** est exercé sans montage supplémentaire : Corrodius ne se buffe pas lui-même
(`SurroundingFriends` = anneau) et l'ami **Imperial** ne reçoit rien (`UnitsWithTrait(Chaos)`).

### 3.2 Ce que le port reproduit (offline vs natif, valeurs ABSOLUES)

| étape | mesure | natif | port |
|---|---|---|---|
| [2] attribution | `movement` par source | `total=1, residual=0, bySource=[{source=<entité-effet>, amount=1}]` | `per_source = {('statmod', 1073, <uid>, 'CursedPlagueBell_ExtraMove'): 1}`, résidu opaque **0** |
| [3] valeur | `GetStat(MOVEMENT)` | 4 | 4 |
| [3b] incidence | tuiles atteignables (`aiMovableTiles`) | u85 : **22** | **22** (sym.diff 0) ; u90 (`C4_09/31337`) : **23** vs **23** |
| [4] expiration | `endturn` des deux côtés | 4 → **3** | 4 → **3** |
| [5] re-pose | tour suivant | 4 | 4 |
| [6] régime hors-aura | unité ÉLOIGNÉE de l'aura, tour suivant | 1073 absent, movement **3**, tuiles **19** | movement **3**, `per_source` **vide**, tuiles **19** (sym.diff 0) |

L'étape [6] applique la doctrine « drive positions » : on ÉLOIGNE l'ami Chaos hors de l'aura par un
`applyAction move`, puis on repasse au tour du joueur. Le natif ne re-pose alors pas l'effet — c'est
le régime « sans effet » confronté LIVE **sur la même unité**, et il colle au bit près sur `MC1_67`.

### 3.3 Mutation adversariale — la contre-épreuve mord

`probe_224_cursed_plague_bell_extramove.py --mutate registry` retire l'entrée du registre avant de
charger l'état (= l'arbre sans ce port) et rejoue les mêmes mesures :

| couple | écarts | le plus parlant |
|---|---|---|
| `MC1_67/777` | **6** | `[4] offline MOVEMENT=4, natif 3 (écart +1 conservé)` sur les DEUX porteurs, et `per_source = {'captured': 1}` là où le natif a `residual = 0` |
| `C4_09/31337` | **3** | idem sur u90 ; `[4b] tuiles offline 23 -> 23 après expiration (le +1 fantôme en valait 0)` alors que le port juste les fait tomber à 17 |

Les gardes pytest mordent de la même façon : registre muté ⇒ **2 failed** sur 3
(`..._is_attributed_per_source`, `..._reverts_at_expiry_like_live`), le 3e (gate) restant vert
puisqu'il ne mesure que le natif.

### 3.4 L'articulation avec le VECTEUR (item 1) — pas de dérive du +1

`case-224-cursed-plague-bell-movement` (le vecteur, mergé pendant ce travail) fait que l'effet est
désormais **re-posé offline** à chaque début de tour du porteur — sur un état où une **première**
instance est déjà seedée. Deux instances = deux clés de source distinctes : si le revert à
l'expiration manquait ou tombait au mauvais tour, le +1 **s'empilerait** au lieu d'osciller. Ce
risque n'existait pas avant que les deux moitiés se rencontrent ; il est donc **mesuré après le
rebase**, pas avant.

Trois cycles complets, `applyAction endturn` natif vs `EndTurnOperation.execute(advance=True)`
offline (qui enchaîne `ChangeTurn` + `StartTurn`, donc le trigger `On(TurnStart_Other)` du vecteur) :

| | tour 0 | +1 | +2 | +3 | +4 | +5 | +6 |
|---|---|---|---|---|---|---|---|
| natif (u83, u85) | 4 | 3 | 4 | 3 | 4 | 3 | 4 |
| port | 4 | 3 | 4 | 3 | 4 | 3 | 4 |
| clés de source `1073` offline | 1 | 0 | 1 | 0 | 1 | 0 | 1 |

**Jamais plus d'une clé simultanée**, jamais de dérive. Registre muté : le port rend
`[4, 4, 4, 4, 4, 4, 4]` contre `[4, 3, 4, 3, 4, 3, 4]` natif — vérifié.
Garde : `test_cursed_plague_bell_extramove_does_not_drift_over_turns`.

### 3.5 Non-régression

Rejoués verts, sans aucun skip : `test_cursed_plague_bell_extramove_live.py` (4),
`test_cursed_plague_bell_movement_live.py` (7, le VECTEUR — c'est lui que ce port pourrait faire
dériver), `test_contagions_aura_range_live.py` (3),
`test_seeded_eager_statmod_expiry.py` (6, dont le nouveau cas 1073),
`test_seeded_eager_statmod_revert_live.py` (3, le foyer R16 partagé),
`test_destroy_the_witch_live.py` (7, l'autre +MOVEMENT),
`test_tile_term_unit_gated_playbooks_live.py -k deathBlightbringer` (10, la face playbook de
case-211, même porteur). `probe_r16_eager_statmod_revert.py` intègre la nouvelle classe à son
inventaire « toutes retirables ». Les deux garde-fous du registre d'abilities passent
(`probe_181_targeting_gaps.py` 94/94 ; `probe_120_pre_unit_ability_fork.py` « littéral de ctor
manquant : aucun ») — vérifiés, pas supposés : ce port n'entre AUCUNE ability dans
`ABILITY_CLASSES`, donc ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` ne le concernent.

---

## 4. Ce que ce cas n'établit PAS

* **Le vecteur de pose** (`CursedPlagueBellMovementAbility$$CreateBehaviour`, son trigger de début de
  tour, `ContagionsOfNurgleRange` et les deux gates de trait) : autre item, **mergé pendant ce
  travail** (`case-224-cursed-plague-bell-movement`). Son articulation avec ce port est mesurée en
  §3.4 (aucune dérive) ; ce cas-ci ne valide ni son trigger ni son arbre de cibles.
* **`CursedPlagueBell_DangerZoneEffect` (1084)** — même constante `extraMovement`, mais axe
  PRÉDICTION de zone de danger (`CreateRangeBonusForDangerZone` -> `RangeBonusForDangerZone`), pas un
  stat-mod. Non porté.
* **Le trait `Stationary` (1048) comme contre-cas** : aucune des 22 unités Chaos du pool rank 17 ne le
  porte, donc la branche `UnitsWithoutTrait(Stationary)` n'est pas exercée. Elle relève du vecteur.
* **Un bénéficiaire SUMMON** : aucun des montages n'en a dans l'aura.

### Résidus observés, hors périmètre

* **Étage PATHFINDING : le port SUR-ATTEINT d'une tuile** sur certaines configurations, et c'est
  **indépendant de ce port** — la preuve est dans la mesure : le même écart tombe sur des unités qui
  ne portent PAS 1073, à la même tuile (`MC1_67/777` : u87 `astraBullgryn` (sans effet) et u83 (avec)
  sur-atteignent tous deux `(2,3)` ; u79 `necroWarden` sur-atteint `(3,6)` ; `C4_09/31337` : u92
  `blackAbaddon` (sans effet) sur-atteint `(4,4)`). Signature constante : toujours `offline \ natif`,
  toujours **une** tuile. Le probe le mesure, le soustrait comme bruit et le REPORTE au lieu de
  l'imputer. Point d'ancrage pour le fermer : `engine/ai/state_bridge._move_tiles` /
  `get_movable_positions` confrontés à `IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor`
  sur ces tuiles précises.
* **`docs/rl/kit-coverage.md` et `docs/rl/passive-ability-coverage.md` sont PÉRIMÉS sur `master`** :
  les régénérer produit **203 + 169 lignes** de diff dont l'essentiel est étranger à cet item (les
  compteurs sautent de 123 à **127** unités lineup). Non régénérés ici — le faire noierait l'apport
  de la PR dans un inventaire d'un autre état. À régénérer d'un coup, dans un commit dédié.

---

## 5. Reproduire

```bash
cd scripts/python
python probe_224_cursed_plague_bell_extramove.py --offline-only            # substrat du port
python probe_224_cursed_plague_bell_extramove.py --seed 777   --board MC1_67
python probe_224_cursed_plague_bell_extramove.py --seed 31337 --board C4_09
python probe_224_cursed_plague_bell_extramove.py --seed 777   --board MC1_67 --mutate registry
python -m pytest tests/engine/runner/test_cursed_plague_bell_extramove_live.py -q
python -m pytest tests/engine/runner/test_seeded_eager_statmod_expiry.py -q
```

Le probe construit et **dispose** son runner ; `--runner <id>` réutilise un runner existant,
`--keep` le conserve.
