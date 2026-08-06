# case-cvc — le CYCLE DE VIE du debuff d'aura `ContagionsOfNurgle` (1071 / 1072)

**Critère (binaire)** : quand le nombre d'auras Contagion couvrant une unité CHANGE, le natif
change-t-il l'état ACTIF des instances 1071/1072 qu'elle porte — et son `FixedArmor` suit-il ? Le
port rend-il le MÊME couple `(instance active, FixedArmor)`, **en dérivant par sa propre
mécanique**, pas seulement en relisant un snapshot ?

**Réponse** : oui, et les trois manques listés par `case-dpw` §5 (aura qui grandit, unité qui sort,
bascule 1071 ↔ 1072) **sont un seul mécanisme** — la fenêtre `[min, max]` de
`CreateActiveCondition`, ré-évaluée à chaque refresh, sur DEUX instances qui **coexistent**.

| | avant | après |
|---|---|---|
| instances posées sur la cible | **une** (celle qui est active) | **1071 ET 1072** |
| `CreateActiveCondition` | non portée | `min <= ContagionsOfNurgleAmount <= max` |
| flag `EffectComponent.IsActive` | seedé, **jamais réécrit** | écrit par le driver à chaque refresh |
| sortie d'aura, armure | figée (mesuré : port 1387, natif 2312) | **2312 = natif** |

---

## 1. L'artefact natif

### 1.1 La condition

`IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$CreateActiveCondition`,
lu verbatim :

```
  AmountIsEqualOrGreater( ContagionsOfNurgleAmount(EffectSource(effect@0x150), Owner@0x30),
                          Get(this+0x48c = min) )
& AmountIsEqualOrGreater( Get(this+0x490 = max),
                          ContagionsOfNurgleAmount(...) )
```

soit `min <= amount <= max`.

> ⚠ **Ordinaux d'`EventTriggerType` re-dérivés du build COURANT**, jamais recopiés d'une fiche
> antérieure : l'enum a été **renuméroté**, et les valeurs héritées de `case-dpw`
> (`UnitAdded = 0x33`, `UnitResurrected = 0x2f`, `UnitRevived = 0x2e`) désignent aujourd'hui
> `PreUnitFled`, `UnitMemberDeath` et `UnitResurrected`. Les vraies, lues dans
> `data/symbols/<build>/frida/enums.tsv` : **`UnitAdded = 0x32`, `UnitResurrected = 0x2e`,
> `UnitRevived = 0x2d`, `PreUnitAbility = 0x2a`, `PreEffectAdded = 0x3d`**. Même gisement que le
> balayage #292 (728 citations) — une citation périmée ne se trompe pas de chiffre, elle **nomme
> un autre événement**.

Les DEUX (et seules) constructions, par
`IdunBattle.Core.Services.EffectsDatabase` `b__14_93` / `b__14_94` :

| effet | ctor `(clé de constante, min, max)` | variable de trait | fenêtre |
|---|---|---|---|
| `0x42f` = 1071 `_ArmorReduction1` | `(0x41, 1, 1)` | `contagionsOfNurgleArmorOneAura` = **−20** | exactement 1 aura |
| `0x430` = 1072 `_ArmorReduction2` | `(0x42, 2, 0x7fffffff)` | `contagionsOfNurgleArmorTwoOrMoreAuras` = **−40** | 2 auras ou plus |

Les fenêtres sont **disjointes** : « basculer » n'est pas un remplacement d'effet, c'est l'une qui
s'éteint pendant que l'autre s'allume. Ce qui n'a de sens que parce que **les deux coexistent** —
`ContagionsOfNurgle_AddEffectToNewUnit_Ability$$CreateBehaviour` et son frère `AddEffectInitially`
posent `AddEffect(0x42f) & AddEffect(0x430)` derrière **le même sélecteur caché**.

⚠ **Le parent n'est PAS `ADynamicStatModifierEffect`** (correction de `case-dpw` §4.2). Le `.ctor`
appelle `IdunBattle.Entities.Effects.AStatModifierEffect$$.ctor(this, AbilityOrEffect(0x431), 0, 0,
1, 1)` puis écrit `+0x488` (clé de constante), `+0x48c` (min), `+0x490` (max). Or
`ADynamicStatModifierEffect$$CreateTargetTrigger` utilise `+0x488` comme **cache de pointeur** de son
trigger : les deux usages sont incompatibles. Conséquence : aucun `RefreshValueInternal`
(revert+apply de magnitude) sur cette famille — sa magnitude est une **constante de config**.

### 1.2 `ContagionsOfNurgleAmount` — RÉSOLU, le collapse est défait

`IdunBattle.Entities.Triggers.ContagionsOfNurgleAmountFormula$$Calculate` :

```csharp
entity = <sélecteur team>.SelectSingle(entities);  if (entity == null) return 0;
teamId = EntityExtensions.GetCurrentTeamId(entity, state);
target = <sélecteur unit>.SelectSingle(entities);  if (target == null) return 0;
return battleQuery.<slot 0x95>(0x42f /* figé par le ctor */, teamId, target, returnFirst: false);
```

et le slot `0x95` d'`IBattleQuery` est `IdunBattle.Core.Services.BattleQuery$$GetTeamActiveAuraAmount`, qui delegue a `IdunBattle.Core.Services.BattleQuery$$GetInRangeAuraAmount`
(même signature `(effectType, team, target, returnFirst)`) — **déjà porté par case-224**. Deux
conséquences **mesurables** par rapport au collapse de `case-dpw` (« porteurs ENNEMIS à distance
`<= CalculateRange` ») :

* le comparateur est **INCLUSIF** (`dist <= GetCurrentRange(porteur)`), pas le STRICT de
  `IsInUnitContagionsOfNurgleAura` — c'est la version d'ÉQUIPE du prédicat que la condition
  consomme, et le §4.3 le **mesure live** (mutation 4) ;
* le filtre d'appartenance est `GetCurrentTeamId(porteur) == team(EffectSource(effect))`, donc
  « porteurs **alliés de la SOURCE de l'effet** », pas « ennemis de la cible ».

### 1.3 L'évaluateur, et ce que devient l'effet quand la condition tombe

`IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect`, dans l'ordre du décompilé :

```
active = ShouldBeActive(refreshTrigger, refreshType, effect, effComp, owner, activePlayer, effectEntity)
if (!active)  DeactivateEffect(...)          # IsActive@+0x5c = 0 PUIS UpdateEffectTargets([])
                                             #   -> RemoveTargetsFromEffect -> <UpdateEffectTargets>b__2
                                             #   -> RevertEffectsForTargets -> slot 0xf = RevertModification
else          effComp.IsActive@+0x5c = 1 ; UpdateEffectTargets(GetTargets(entities))
                                             #   -> <UpdateEffectTargets>b__3 -> ApplyEffectsForTargets
```

⇒ **l'entité-effet n'est JAMAIS retirée** : elle est rendue INERTE et sa `ValueModification` est
REVERSÉE. Même forme que `PinnedEffect` (case-224/#208 §4) — la mise en garde de l'énoncé (« ne
présuppose pas le retrait ») est donc justifiée, et le décompilé la tranche.

`RefreshEffectsOperation$$ShouldBeActive` :

```
refreshType 1 (ForceActivate)   -> true            # enum IdunBattle.Operations.RefreshEffectType
refreshType 2 (ForceDeactivate) -> false           #   0=Automatically 1=ForceActivate 2=ForceDeactivate
autre != 0                      -> ArgumentOutOfRangeException
effectComponent+0x5e (verrou)   -> false
!effect.ShouldRefreshForTrigger(trigger) -> return effectComponent.IsActive @+0x5c   # flag COURANT
sinon                            -> effect.<slot 0xb = ShouldBeActive>(entities)
                                    = CreateActiveConditionAndCache().ShouldTrigger(entities)
```

`IdunBattle.Entities.Effects.BaseEffect$$ShouldRefreshForTrigger(t)` =
`t <= 2 || GetRefreshTriggers() == null || GetRefreshTriggers().Contains(t)`. L'enum du build :

```
IdunBattle.Operations.RefreshEffectTrigger
  0=Forced 1=Simulation 2=Custom 3=UnitStateChanged 4=EffectsChanged
  5=UnitsChanged 6=TurnChanged 7=UnitPositionChanged 8=MatchStart
```

`ContagionsOfNurgle_ArmorReduction_Effect` **ne déclare pas** de `GetRefreshTriggers` (12 classes
seulement en ont un dans tout le binaire, aucune n'est celle-ci) ⇒ sa condition est ré-évaluée à
**chaque** refresh, quel qu'en soit le trigger. Et `RefreshEffectsOperation$$Execute` avec un
`effectEntity` nul boucle sur **tous** les effets de la bataille.

### 1.4 Le flag naît FAUX

`IdunBattle.Entities.Components.EffectComponent$$.ctor` écrit `+0x48`/`+0x50`/`+0x78` (listes),
`+0x68` et `+0x6c` (= 1) — et **n'écrit pas `+0x5c`**, qui reste zéro-initialisé. C'est donc le
premier `RefreshEffect` qui active l'instance ET applique sa modification : côté natif,
`AddEffectOperation` ne pose **aucune** `ValueModification`.

---

## 2. Classification : DÉCLARATIF ou IMPÉRATIF ?

**`CreateActiveCondition` est un artefact DÉCLARATIF** — un arbre de nœuds
(`DSLTriggers$$AmountIsEqualOrGreater` ×2, `DSLFormulas$$ContagionsOfNurgleAmount`,
`DSLFormulas$$Get`, joints par `AbilityTrigger$$op_BitwiseAnd`), mémoïsé par
`BaseEffect$$CreateActiveConditionAndCache` dans le champ `+0x90`. Il vit donc **au-dessus** de la
frontière « `.Execute` d'une feuille ».

**Mais il ne devient pas un arbre `engine/dsl` pour autant**, et c'est un choix argumenté :

* le port a **déjà un foyer unique** pour cet artefact — `BaseEffect.is_active(unit_state)`, établi
  par #208 et alimenté par le constructeur unique `components.unit_state_for_effects`. Neuf classes
  d'effet y portent leur condition, dont `PinnedEffect` (`Not(HasTrait(Self, TerminatorArmour))`) et
  `DestroyTheWitch_*` (`AmountIsEqualOrGreater(Enemies(Owner, UnitsWithTrait(Psyker)), One)` — le
  **même patron** que le nôtre : cardinal d'un sélecteur comparé à une constante) ;
* en construire un second par arbre DSL serait exactement le fork « 1 nœud natif → 2 portes
  offline » que la doctrine interdit : `active_effects` lit `is_active`, le driver aussi ; un arbre
  parallèle exigerait un `AbilityEntities` complet là où le natif, lui, n'a besoin que de
  `(owner, activePlayer, effectEntity)` ;
* la frontière est **respectée là où elle compte** : ce qui reste impératif ici, ce sont les
  Operations (`RefreshEffectsOperation`, `ApplyModification`/`RevertModification` → `ChangeStat`),
  et elles sont mirrorées telles quelles. **Aucune logique de la condition n'est recâblée dans un
  `execute_*`** : elle est entièrement dans la classe d'effet, en mirror littéral, et son terme
  variable (`ContagionsOfNurgleAmount`) **délègue** au mirror `GetInRangeAuraAmount` déjà porté.

Autrement dit : **déclaratif dans sa forme, porté dans le foyer déclaratif existant du port** (la
paire `CreateActiveCondition` ↔ `is_active`), pas re-implémenté à la main dans un vecteur.

---

## 3. Ce qui est porté

| Fichier | Contenu |
|---|---|
| `engine/entities/effects/loki/status.py` | `CTOR_ARGS` (les deux fenêtres), `aura_amount_window`, **`is_active`** (mirror littéral de la condition), **`applied_stat_mods`** (magnitude contextuelle, gatée par le flag), en-tête RE corrigé (parent = `AStatModifierEffect`) |
| `engine/runner/components.py` | **`contagions_of_nurgle_amount(state, unit, source)`** = mirror DÉLÉGUÉ de `ContagionsOfNurgleAmountFormula$$Calculate` → `battle_query.get_in_range_aura_amount` ; clé-CALLABLE `contagions_of_nurgle_amount` du `unit_state` |
| `engine/runner/operations/refresh_effects.py` | le driver **ÉCRIT le flag `IsActive`** (le producteur qui manquait), skippe sur la **clé de pose** et non sur la méthode déclarée, et lit `effect_stat_modifications` (point de vérité R16) |
| `engine/runner/operations/effects.py` | `AddEffectOperation.execute(..., active=True)` — mirror du ctor natif, qui laisse `+0x5c` à faux |
| `engine/runner/operations/triggers/loki/contagions_of_nurgle.py` | pose des **DEUX** instances (collapse défait) puis refresh immédiat ; `aura_carriers` re-qualifié (sélection de l'`EffectSource`, PAS le compte) |
| `engine/runner/operations/movement.py` | refresh après un pas — `RefreshEffectTrigger.UnitPositionChanged` |
| `engine/runner/operations/turnflow.py` | refresh au début de tour, APRÈS le bump de `TurnsStarted` — `RefreshEffectTrigger.TurnChanged` |

### 3.1 Les deux points qui ne se devinent pas

**(a) Le gate `self.active` d'`applied_stat_mods` est load-bearing.** Les deux instances coexistent,
mais une seule porte une `ValueModification` côté natif. Sans le gate, la passe 2 de
`UnitContext.from_snapshot` (`stat_modifications_by_source(effects, stats_ctx=ctx)`) attribuerait
−20 % **et** −40 % alors que le `statDelta` capté n'en porte qu'un — mesuré sous mutation 2 :
armure 925 au lieu de 1850, soit −60 % cumulés.

**(b) Le skip du driver porte sur la CLÉ, pas sur la méthode déclarée.** Il testait « l'effet
déclare-t-il `applied_stat_mods` ? », ce qui excluait du driver **tout** effet à magnitude
contextuelle, y compris SEEDÉ (donc sans clé de pose) et dont la contribution est attribuée sous
`statmod_source_key`. Mesure directe : sortie d'aura, natif 1387 → 2312, port **figé à 1387**, avec
`per_source = [(CAPTURED, -925)]` — la contribution était dans le résidu opaque, irretirable.
Inventaire du blast radius (introspection) : **11 classes** déclarent `applied_stat_mods`, une seule
déclare aussi `get_stat_modification_stat` (`AnvilShield_FrozenAttackerAdvantage`) et **aucune** ne
surcharge `is_active` ⇒ pour toutes, `is_active` rend `True` et le driver ré-écrit exactement la
valeur déjà posée sous la MÊME clé (`Modify` = replace par-source) : **no-op exact**.

---

## 4. Mesure live

`probe_cvc_contagions_lifecycle.py` — 3 porteurs Contagion (`deathTyphus`, `deathBlightlord`,
`deathPutrifier`) côté adverse, 3 victimes côté joueur, `--no-ai`, positions **pilotées**.
Le port est chargé par le canal LARGE (`decision_view_seed_body`, `includeInactive`) : sans lui les
instances inertes n'existent pas côté port et la confrontation comparerait deux canaux (#219).

### 4.1 Étape A — les DEUX instances sont posées (réfutation du collapse)

`decisionView { includeInactive: true }`, runner frais, victimes hors de toute aura :

```
ultraTitus    1071 active=false   1072 active=false
necroWarden   1071 active=false   1072 active=false
adeptMorvenn  1071 active=false   1072 active=false
```

Le canal par DÉFAUT n'en publie **aucune** (il droppe `IsActive == 0`). Le port matérialise les
mêmes deux instances, inertes — **3/3**.

### 4.2 Étapes B / C / D / E — les quatre faces du cycle, board `MC1_67`, seed 4242

| étape | ce qui change | natif | port |
|---|---|---|---|
| **B** géométrie, d=4 (Putrifier à 1) | `amount = 1` | actif `[1071]`, armure **1850** | idem |
| **B** d=3 | `amount = 1` | `[1071]`, 1850 | idem |
| **B** d=2 (Blightlord ET Putrifier à 1) | `amount = 2` | actif **`[1072]`**, armure **1387** | idem |
| **B** d=1 (les autres à 2) | `amount = 1` | `[1071]`, 1850 | idem |
| **C** aura qui GRANDIT, **personne ne bouge** — victime à d=2 d'un porteur isolé | `TurnsStarted` 0 → 3, rayon 1 → 2 | `[]` armure **2312** → `[1071]` armure **1850** | idem |
| **D** 2e porteur amené au contact | `amount` 1 → 2 | `[1072]`, **1387** | idem |
| **E** SORTIE d'aura, **dérive offline pure** | — | `[]` armure **2312** | `[]` armure **2312** |

`2312` est le `FixedArmor` de base ; `1850 = 2312 − round(2312 × 20/100)` et
`1387 = 2312 − round(2312 × 40/100)`, bit-exact des deux côtés.

Les étapes **C** et **E** sont celles qui comptent : le port n'y est **jamais re-seedé**. Il joue le
même pas par SON propre vecteur — `StartTurnOperation.execute` pour la croissance,
`MoveUnitOperation(...).execute` pour la sortie — et produit le même couple que le natif. Les étapes
A/B/D, elles, ne prouvent que la LECTURE.

**La variante −40 % (1072) EST confrontée live**, contrairement à ce qu'indiquait `case-dpw` §7 :
deux porteurs Contagion dans le même roster adverse suffisent, et `rl_duel build --a-units` les met
tous les deux. Elle est mesurée aux étapes B (d=2) et D, sur deux boards.

### 4.3 Généralisation et mutations

**2e géométrie** : `--board C4_09 --seed 999` → VERDICT OK, **A/B/D/E exercées**, même dérive
`1387 → 2312` à l'étape E. La ligne `d=4` y donne `amount = 0` (armure **2312**, aucune instance
active), ce que `MC1_67` ne produisait pas : le contre-cas « hors de toute aura » est donc exercé
là aussi.

> **`C1_02` a été ÉCARTÉ, et c'est une mesure, pas une préférence.** Un scan offline des dumps
> (`board.Board.playable_tiles` + distance inter-spawns) donne : `C1_02` = **35 tuiles jouables**,
> spawns à distance 5 ; `MC1_67` = **63** ; `C4_09` = **70**, spawns à distance 1. Sur 35 tuiles il
> n'existe aucune case à distance ≥ 4 des trois porteurs (le seuil natif — `GetMaxRange = Direct(3)`
> avec comparateur inclusif), donc l'étape E ne peut pas s'y monter ; et l'approche y coûte
> 16 tours, ce qui pousse `TurnsStarted` bien au-delà du palier 1 et interdit l'étape C. Le premier
> run sur `C1_02` affichait pourtant `VERDICT: OK` : c'est ce faux vert qui a motivé le garde-fou
> `NOT_EXERCISED` ci-dessous.

**Garde-fou anti-faux-vert (`NOT_EXERCISED`)** — une étape qui n'a rien mesuré ne compte JAMAIS
comme un succès. Trois causes distinctes sont désormais détectées et **nommées** au lieu d'être
silencieusement vertes : (a) le montage ne se monte pas (isolation impossible, palier déjà dépassé,
aucune tuile hors aura, pas live avorté) ; (b) la victime **meurt** pendant l'approche par cycles
`endturn` — le probe bascule alors sur une autre victime du roster plutôt que de lire une unité
absente du snapshot ; (c) **l'accord VIDE** : si l'état actif live est identique avant et après la
transition censée le changer, `[] == []` ne prouve rien. Le VERDICT porte le compte d'étapes non
exercées, et la garde pytest les traduit en `skip` EXPLICITE.

**Répartition mesurée** : l'étape C (croissance d'aura) n'est discriminante que sur `MC1_67`, où
elle produit même mieux qu'attendu — `[1071]` 1850 → `[1072]` 1387, c'est-à-dire la **bascule
1071 → 1072 déclenchée par la seule croissance du rayon, sans aucun mouvement**. Sur `C4_09` les
spawns au contact font que plusieurs porteurs couvrent déjà la victime : l'isolation à un seul
porteur n'y tient pas et l'étape est rapportée NON EXERCÉE. Les deux boards sont donc
**complémentaires**, et chaque run le dit explicitement.

**Mutations du fix** — cinq, toutes détectées, avec des signatures **disjointes** :

| mutation | tests rouges |
|---|---|
| 1 · `is_active` neutralisée (rend le flag) | `windows_disjoint`, `poser`, `growing`, `leaving` |
| 2 · fenêtre de 1072 élargie à `[1, +inf[` | `windows_disjoint` (et armure 925 = −60 % cumulés) |
| 3 · le driver n'écrit plus le flag `IsActive` | `poser`, `growing` |
| 4 · comparateur du compte rendu **STRICT** | `poser`, `growing`, `geometry` |
| 5 · le vecteur ne pose que l'instance active (collapse) | `poser` |

La **mutation 4** est celle qui vaut le plus : elle **mesure live** que le comparateur consommé par
`CreateActiveCondition` est bien l'INCLUSIF de la version d'ÉQUIPE (4 lignes de géométrie rouges
d'un coup), là où case-224 §5 notait que seul le décompilé l'établissait.

### 4.4 Non-régression

Toutes VERTES : `test_contagions_of_nurgle_new_unit_live` + `test_contagions_aura_range_live` (6) ·
`test_effect_immunity_live` + `test_load_state_inactive_effects_live` (18) ·
`test_anvil_shield_stun_live` + `test_destroy_the_witch_live` (11) · `test_damage_roll_live` +
`test_runner_attack_live` + `test_effect_duration_rounds_live` (9) · `test_aura_position_live` +
`test_seeded_eager_statmod_expiry` + `test_seeded_eager_statmod_revert_live` +
`test_lion_helm_block_aura_live` (12) · `test_chain_after_refused_addeffect_live` +
`test_tile_effect_dynamics_live` + `test_suppressive_fire_live` (13).
Garde-fous de registre : `probe_181` (94/94, 0 manquante) et `probe_120` étape 0 (aucun littéral de
ctor manquant) — le registre d'abilities n'est pas touché par ce cas.

---

## 5. Reproduire

```bash
cd scripts/python
python probe_cvc_contagions_lifecycle.py --offline-only
python probe_cvc_contagions_lifecycle.py --board MC1_67 --seed 4242    # A-E, C discriminante
python probe_cvc_contagions_lifecycle.py --board C4_09  --seed 999     # 2e geometrie (A,B,D,E)
python -m pytest tests/engine/runner/test_contagions_lifecycle_live.py -q
```

Le probe n'arme **aucun hook** : `decisionView` (deux canaux), `observeBattle`, `combatSnapshot`,
`boardGraph`, et pilotage par `applyAction`. Aucune réinjection.

---

## 6. Ce qui n'est PAS couvert

* **Une instance SEEDÉE peut être retirée mais pas RE-posée si sa `value` manque.** Le canal de
  capture ne publie pas la magnitude ; la forme OVERRIDE `applied_stat_mods(ctx)` la re-dérive
  depuis `GetStat(FixedArmor, INITIAL)`, ce qui couvre le cas mesuré — mais un porteur dont
  l'armure de base aurait été modifiée par ailleurs verrait le pourcentage appliqué à la base
  courante, pas à celle du moment de la pose. Non exercé.
* **La part MULTIPLICATIVE (`part 9`) n'est pas portée** : le natif pose
  `Position(stat, isMultiply ? 9 : 5)` et cette famille a `isMultiply = 1` ; le port matérialise un
  delta plat équivalent. Les deux coïncident sur toutes les mesures (2312 → 1850 → 1387), mais la
  distinction mordrait si une AUTRE modification d'armure coexistait — non exercé.
* **`RefreshEffectTrigger.UnitsChanged` (5) et `UnitStateChanged` (3)** ne sont pas câblés : le port
  refresh sur `UnitPositionChanged` (move) et `TurnChanged` (start-turn), plus le refresh ciblé
  après dégât préexistant. La MORT d'un porteur d'aura ne rafraîchit donc les cibles que si un
  mouvement ou un tour survient ensuite — ce qui est le cas en pratique, mais l'ordre exact n'est
  pas confronté.
* **Les branches `UnitResurrected` (0x2e) / `UnitRevived` (0x2d)** du trigger de pose restent non
  câblées (hors périmètre du cas, résidu inchangé).
* **`AddEffectInitially`** (`OnOwnerSpecificAbilityInit`) reste délibérément non porté : le runner
  recharge un `combatSnapshot` où le debuff est déjà cuit. Ce cas ne change rien à cette décision —
  il exploite au contraire le fait que le NATIF l'a joué (c'est ce qui met les deux instances sur
  les victimes de l'étape A).
* **La face PRÉDICTION** : `playbook/scene.py::Scene.unit_state` ne fournit pas la clé
  `contagions_of_nurgle_amount`, donc `is_active` y dégrade sur le flag `active`. Inoffensif —
  cette classe ne contribue à rien via `active_effects` (aucun `create_effect_*`), son seul canal
  est le stat-layer, qui lit `GetStat(FixedArmor)`. À câbler le jour où un consommateur de
  prédiction lira l'effet par présence.
* **Le champ `unitSelectionType`** et `GetNextTurnRange` restent non exercés (résidus case-224
  inchangés).
