# #931 — `TwistedScience` (`genesBiophagus` « Hollan »), face COMBAT

Passif `TriggeredAbilityType.TwistedScience` (0x4fe = 1278). La face **DÉCISION** était portée depuis
longtemps (playbook `TwistedScience_HealPlaybook`, prédiction de soin, gate d'énumération) ; la face
**COMBAT** était un **no-op complet** — l'IA choisissait le cast, l'exécution ne mutait rien.

## 1. Les cinq faces natives, et ce qu'aucune table ne disait

| # | artefact natif | statut |
|---|---|---|
| F1 | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TwistedScienceAbility` — `$$CreateTrigger` + `$$CreateBehaviour` | **non porté, verdict MESURÉ** (§2) |
| F2 | `IdunBattleLogic.Entities.Abilities.Active.Loki.TwistedScience_HealAbility` (1167) — `$$.ctor`, `$$GetDynamicInvalidTargetReason`, `$$ExecuteBehaviour` | **PORTÉ** (§3) |
| F3 | `IdunBattle.Entities.Effects.Loki.TwistedScience_ExtraDmgEffect` (1356) | **PORTÉ** |
| F4 | `EffectType.TwistedScience_ExtraHp` (1355) — **aucune classe native** | **PORTÉ** (§4) |
| F5 | `IdunBattle.AI.Playbook.Loki.TwistedScience_HealPlaybook` | déjà porté (`playbook/common.py`) |

**Aucune face DEAD dans le moteur.** La seule morte du kit est le VISUEL du passif :
`IdunBattle.View.AbilityConfigs.Loki.TwistedScienceVisuals$$ExecuteInternal` alloue son itérateur
`<ExecuteInternal>d__3` et le rend, mais le `MoveNext` de cet itérateur n'a **aucune entrée propre**
dans les deux tables — corps fondu par l'ICF avec un `MoveNext` trivial, donc **zéro étape
visuelle**. Elle vit côté VIEW, hors moteur ; son homologue `TwistedScience_HealVisuals`, lui, a un
`MoveNext` bien à lui.

### `$$CreateTrigger` n'est dans AUCUNE table, et il existe

Les deux tables (`frida/methods.tsv`, `ghidra/functions.tsv`) sont **dédupliquées par adresse** :
elles n'attribuent un corps partagé qu'à **un seul** propriétaire. `TwistedScienceAbility` n'y a donc
qu'une ligne (`$$CreateBehaviour`) — ni `.ctor`, ni `CreateTrigger`.

La table `methodPointers` du PE, elle, porte **une entrée par propriétaire** et les range **par
classe**. Les xrefs DATA de `$$CreateBehaviour` donnent sa position ; ses voisins immédiats sont les
autres méthodes de la MÊME classe :

```
… TrophyTakerAbility$$GetLocalizationData, …$$GetCritChanceMultiplier,
   RequiredByNativeCodeAttribute$$.ctor,                      <- le .ctor de TrophyTakerAbility
   SummaryExecutionAddBaseEffectAbility$$CreateTrigger,       <- le CreateTrigger de TwistedScienceAbility
   TwistedScienceAbility$$CreateBehaviour,
   RequiredByNativeCodeAttribute$$.ctor,                      <- le .ctor de TwistedScienceAbility
   UnbridledCarnageReworkedAbility$$CreateTrigger, …
```

Le corps ainsi trouvé porte **58 xrefs DATA** (58 abilities sans rapport le partagent) et vaut :

```csharp
CreateTrigger(this) => this.<dsl @+0x28>.<DSLTriggers @+0x88>.<+0x30>;
```

et `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` **écrit** ce champ `+0x30` :

```csharp
this.<+0x30> = On(0x21 = AbilityInit) & <trigger @+0x70> & get_OwnerIsActor;
```

Conclure « pas de `CreateTrigger` » de l'absence en table aurait été un faux négatif.

## 2. F1 — le SWAP, et pourquoi le port n'a pas à le rejouer

```csharp
// ...TwistedScienceAbility$$CreateBehaviour(entities, abilityState, triggerType)
RemoveActiveAbility(Owner@DSLSelectors+0x30, 0x12 = ActiveAbilityType.Heal)
  op_BitwiseAnd
AddActiveAbility(Owner@+0x30, 0x48f = ActiveAbilityType.Heal_TwistedScience, abilityState)
```

À `AbilityInit`, le soin **générique** que le trait `Healer` accorde est remplacé par 1167 — et
l'`AbilityState` transmis est celui du **PASSIF**. C'est ce qui fait que 1167 s'indexe sur le niveau
de `TwistedScience` et non sur une entrée gameconfig `Heal_TwistedScience`, **qui n'existe pas**.

**VERDICT : sans observable côté runner, et c'est mesuré** (`probe_931 --phase swap`). Le port
charge un état où le natif a déjà fait le swap. Le relevé est **croisé**, ce qui est ce qui le rend
concluant :

| unité | trait `Healer` | passif `TwistedScience` | abilities natives |
|---|---|---|---|
| `genesBiophagus` | oui | **oui** | `[69, 1166, **1167**]` — **18 absent** |
| `ultraApothecary` | oui | non | `[**18**, 69, 1002]` — 1167 absent |

Sans le contre-témoin, « Hollan a 1167 » serait compatible avec « tout le monde a 1167 ».

## 3. F2 — l'ability 1167

### `$$.ctor` — forme 1 « flags directs »

```
TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x00, 2, 0x8402, 0, 0)
AActiveAbility..ctor(this, &opts, 2)                     -> AbilityAttackType.Others
```

* masque `0x8402` = `TargetMatchesDynamicRule | TargetIsFriendly | CasterIsPossibleTarget` (reste 0) ;
* portée = `TargetingRange` **statics+0x00** = `RANGE_ADJACENT_IF_MELEE_CASTER`
  (`onlyAdjacent = IfNotRangedCaster`). ⚠ **Ce n'est pas `RANGE_ADJACENT`** (statics+0x30, celui de
  `RepairAbility`) : les deux coïncident sur un caster de mêlée — ce qu'est Hollan — mais ce sont
  deux constantes distinctes, lues au `.cctor` de `IdunBattle.Core.Services.TargetingRange`.

### `$$GetDynamicInvalidTargetReason`

```csharp
if (!UnitExtensions.IsAffectedByHealType(target, 0 = NonMechanical))  return 0x100;  // TargetIsHealable
if (caster == target) { ok = attackQuery.<slot 0x11>(caster, target, 0, true); }
else {
    if (UnitExtensions.IsEnemy(target, caster, state))                return 0x400;  // TargetIsFriendly
    if (!EntityExtensions.HasEffect(target, state, 0x54b, onlyActive: null)) return 0;
    ok = attackQuery.<slot 0x11>(caster, target, 0, true);
}
return ok ? 0 : 0x100;
```

Le slot `0x11` est **`AttackQuery$$EntityCanBeHealed`** — LU dans `metadata/interface_slots.tsv`
(`IAttackQuery` 17, 4 arguments), pas déduit de son voisin `0x12 EntityCanBeRepaired` qu'utilise
`RepairAbility`.

**La clause qui fait tout l'intérêt du gate** : un allié **non encore marqué** est valide *sans
passer par* `EntityCanBeHealed`, donc **même à PV pleins** — exactement l'i2 « *Hollan can heal
other unaffected units even if they are at full Health* ». Une cible déjà marquée retombe sur le
gate de soin ordinaire.

### `$$ExecuteBehaviour` — l'arbre, dans son ordre

```csharp
Execute(
    If( NOT HasEffect(Target@+0x60, 0x54b, onlyActive: false, EffectTargetType.Both)
        AND NOT get_OwnerIsTarget,
        ( AddDynamicStatModifierEffect(targets = Target@+0x60, source = Owner@+0x30,
                                       0x54b, statType = 5 Health,
                                       AbilityStateReference, turns = null, isHidden = false)
          op_Addition
          ChangeStat(Target@+0x60, Stat(5 Health), mode 2 Add,
                     ConfigVar(0x4fe TwistedScience, Owner@+0x30, 0x1d hp),
                     modificationEntity = null, selectionType = 3, false, false) )
        op_Addition
        If( HasFaction(Target@+0x60, 0xf Genestealers, 3),
            AddEffect(0x54c, AbilityStateReference, source = Owner@+0x30,
                      targets = Target@+0x60, options = default(0) -> PERMANENT) ) )
    op_Addition
    Heal(healer = Caster@+0x48, Target@+0x60, HealAbility.HealAmount(dsl),
         HealBehaviourOptions.ForHeal()) )
```

Trois lectures que la STRUCTURE donne et que l'i2 seul ne donnerait pas :

1. **le soin est INCONDITIONNEL** — il est le second terme du `op_Addition` FINAL, hors du `If`.
   Une cible déjà marquée, ou le caster lui-même, est soignée sans recevoir aucun buff ;
2. **le gate de buff a DEUX termes, tous deux niés** : `!HasEffect(1355)` (« *Affected units cannot
   gain the effects of Twisted Science again* ») et `!OwnerIsTarget` (« *Units healed by Hollan,
   **other than himself*** ») ;
3. **seul `AddEffect(1356)` est sous le gate de FACTION** — pas le `+hp`, qui va à n'importe quel
   allié (« *If they are a Genestealer Cults unit, they **also** deal +extraDmg* »).

`HealAmount(dsl)` = `Multiply(StatAmount(Caster, ATTACK, Current), Max(WeaponHighestHits(Caster), 1))`
— l'arbre identique à `RepairAbility$$RepairAmount`, déjà porté en `engine.predict.heal_amount_weapon`.

## 4. F4 — l'effet 1355 : le chemin, pas seulement la valeur

1355 n'a **aucune classe native** : c'est un `IdunBattle.Entities.Effects.DynamicStatModifierEffect`
générique, construit par `EffectsDatabase$$InitializeEffects` (`variableType = 0x1d = hp`,
`isNegative = 0`) et posé avec `statType = 5 = Health`, littéral de la feuille. Sa magnitude :

```csharp
// ...DynamicStatModifierEffect$$GetDynamicStatModificationAmount
v = ConfigVar(<abilityType>, DSLSelectors.EffectSource(Get(effect)), <variableType>);
return isNegative ? -v : v;
```

Côté port, `EFFECT_CLASSES` est la **seule** voie par laquelle un stat-mod s'applique : un effet hors
registre est matérialisé en `BaseEffect` nu, donc **posé mais inerte**. D'où
`TwistedScienceExtraHpEffect` — le mirror du **couple** (base d'effets + ctor générique), pas
l'invention d'une classe native qui n'existe pas. Même arbitrage que `unbreakable_duty.py`.

⚠ **Et `get_stat_modification_stat`/`_amount` ne suffisent pas : il faut `applied_stat_mods`.**
Les deux chemins du port ne mutent pas le même objet :

* `AddEffectOperation._apply_stat_mods` (chemin de la **POSE**) ne lit que `applied_stat_mods`, et
  exécute par `stat_ops.apply_change_stat`, qui **route `StatType.Health` vers
  `HealthComponent.modify_max`** — donc vers `get_CurrentMaximumValue()`, le plafond que lit le
  `Heal` qui SUIT dans le même arbre ;
* `refresh_stat_modifier_effects` (chemin du **REFRESH**, qui lit la forme de BASE) écrit dans
  `UnitStats`, que **rien ne relit pour les PV**.

**Mesuré** : sur une cible à 1000 PV (max 6023), sans `applied_stat_mods` le port finit à **6023** là
où le natif rend **7606** — écart 1583, soit 21 % du résultat. Avec, **écart 0**.
Précédent identique et documenté : `AnvilShieldFrozenAttackerAdvantageEffect` (`hits.py`).

## 5. Confrontation LIVE — `probe_931_twisted_science.py`, 8 phases

Montage : `genesBiophagus` + `genesKelermorph` (Genestealers) + `ultraApothecary` (Ultramarines,
trait `Healer` → contre-témoin du swap), board `MC1_67`, seed 777. Le porteur est **dans le pool** :
aucune injection.

| phase | ce qu'elle exerce | résultat |
|---|---|---|
| `swap` | l'inventaire natif d'abilities, relevé croisé | 4/4 |
| `gates` | `abilityTargets.fromHere` vs port, avant/après marquage | `{83,85}` → `{85}`, **égal des deux côtés** |
| `meca` | le 1ᵉʳ gate (allié MÉCANIQUE) **et** la portée (allié ÉLOIGNÉ par `--place`) | tous deux exclus des deux côtés |
| `cast` | PV pleins, 2 bras | GS : 6023 → **9015** + `{1355,1356}` · non-GS : 10038 → **13030** + `{1355}` |
| `blesse` | le clamp du `Heal` sur le plafond relevé | 1000 → **7606** des deux côtés (écart 0) |
| `self` | `!OwnerIsTarget` (Hollan blessé se cible) | 1000 → **4614**, **aucun effet posé** des deux côtés |
| `pauvre` | sépare le `ChangeStat` du `Heal` (attaque à 100) | delta natif **+2992** = `hp` exactement |
| `dmg` | 1356 sur les DEUX voies d'arrivée, multiplicateurs distincts | `Addition` **499** = `extraDmg[50] × 180 %` |

⚠ **Trois de ces phases n'existaient pas au premier jet, et c'est un mutant qui les a exigées.**
`self`, `pauvre` et `meca` construisent des régimes que le montage nominal n'atteint pas ; sans elles
les mutants M10, M3, M7 et M12 passaient **verts**.

## 6. Mutants — `probe_931_mutants.py` : 10 mordent, 2 inerties DÉMONTRÉES

Chaque mutation réécrit temporairement le source et rejoue la phase visée **dans un sous-processus**
(sans quoi le module déjà importé resterait celui d'avant la mutation, et le mutant passerait vert
sans avoir mordu).

**Mordent (10)** : gate de non-repose inversé · gate de faction déplacé · `ChangeStat` à zéro ·
`applied_stat_mods` retiré · clause « full HP » retirée · `IsAffectedByHealType` retiré ·
`scale_from_source=False` · `!OwnerIsTarget` retiré · verdict `EntityCanBeHealed` ignoré ·
portée élargie au plateau.

**INERTES, avec leur cause mesurée** :

* **M4 — l'ORDRE des deux volets** (`statMod` avant `ChangeStat`, `buffs` avant `Heal`) est
  **algébriquement inobservable** : le `ChangeStat` du port ne clampe pas et le stat-mod est un pur
  décalage additif du plafond, donc
  `min(hp + heal, old_max) + extra ≡ min(hp + heal + extra, old_max + extra)` pour tout quadruplet.
  Vérifié exhaustivement par `_demo_m4()`, qui est **le cliquet** : il rougit le jour où l'un des
  deux faits change, et M4 redevient alors exerçable. L'ordre reste gardé **structurellement** par
  `test_931_twisted_science_offline.py`.
* **M8 — le refus des ENNEMIS** dans la règle dynamique est **redondant avec le bit
  `TargetIsFriendly` (0x400) du masque STATIQUE**, évalué en amont. La redondance est **native** :
  le masque du ctor porte 0x400 *et* `$$GetDynamicInvalidTargetReason` refait `IsEnemy → 0x400`.

## 7. Ce qui n'est PAS couvert

* **le `18 Heal` générique** (et `1212 HealingBalms_Heal`) restent hors `ABILITY_CLASSES` : un cast
  du soin de trait est toujours un no-op. Résidu **#931-r1**. Le couple 1167/18 est l'exact
  symétrique de `1119 Repair_GalvanicField` / `28 Repair` (#299), à ceci près que la voie de
  spécialisation est un **swap DSL** et non un héritage de classe.
* **la face DÉCISION dérive 1167 du KIT gameconfig**, pas de `BC.Units[].PassiveAbilities` —
  `state_bridge._granted_abilities` lit `GC.unit(vid)["passiveAbilities"]`. Même vice de substrat que
  #264 / #366-r1 / #419-r1-tr14-r5. Résidu **#931-r2**.
* **la magnitude de 1356 sur un effet arrivé par `load_state`** retombe sur les champs de l'unité
  PORTEUSE, alors que le natif la résout contre l'`AbilityState` du POSEUR (résidu hérité #68, cf.
  `PrimarchOfTheFirstLegionExtraDamageEffect`). La voie POSE, elle, est correcte et **mesurée**
  (phase `dmg`, multiplicateurs 180/100).
* **le comportement de `1355`/`1356` à l'EXPIRATION** : les deux sont permanents (`turns = null`,
  `options = default(0)`), donc rien ne les fait expirer — mais aucun montage n'a exercé un chemin
  de RETRAIT (mort et résurrection du porteur, dissipation forcée).
* **`probe_457 --since origin/master`** (307 fichiers, ~1912 s) a été lancé, mais **avant** le
  rebase, et l'arbre a changé sous ses pieds pendant son exécution (rebase + trois régénérations
  d'artefacts) : son `rc 1` n'est **attribuable à rien** et n'est pas rapporté comme verdict. Ce qui
  a été joué de ciblé : les deux fichiers #931 (20 tests), `test_519` / `test_603` / `test_909`
  (24 tests), et neuf cliquets — tous APRÈS rebase.

## 8. Deux défauts d'OUTILLAGE trouvés en chemin, tous deux fermés

Aucun des deux n'appartient à la mécanique portée ; les deux sont des **faux verts** que cette
tranche a rendus visibles.

1. **`probe_931_mutants.py` réécrivait les fichiers en CRLF et ses ancres parlaient LF.** Sur un
   checkout Windows (le cas par défaut ici), les 12 ancres à `\n` étaient **introuvables** — soit
   **12 mutants non appliqués**, donc 12 phases jouées sur du code intact. Seul le garde « ancre
   introuvable = anomalie » l'a attrapé ; sans lui, la passe aurait affiché douze verts. Corrigé par
   `newline=""` des deux côtés + normalisation de l'ancre sur le séparateur du fichier.

2. **`test_927_fury_offline.py` déclarait TROP ÉTROIT, et rien ne pouvait le voir.** Son `BUILD_DIR`
   n'était pas `normpath`é, donc le capteur d'empreinte de `probe_457` inscrivait le témoin sous
   `scripts/python/tests/engine/../../../../data/symbols/<build>/frida/methods.tsv` — que le
   `data/symbols/**` ajouté par son `build: True` ne peut pas apparier. Le défaut est **invisible
   tant que l'empreinte du fichier n'est pas mesurée** : il est apparu au premier `--measure-missing`
   (ordre #486-r29), et `probe_486r15` est passé ROUGE. Corrigé (un `normpath`), l'empreinte
   re-mesurée ; le cliquet repasse PASS et le nombre de déclarations confrontées **aux DEUX sources**
   monte de 103 à 108.

## 9. Un rouge de `master` croisé en chemin — attribué, PAS corrigé (#934)

Le `probe_457 --since` lancé pendant cette tranche a écrit **7 fichiers ROUGES** dans le ledger,
faisant passer `probe_547` en FAIL. **Attribution faite avant d'accuser**, sur un worktree témoin :

| arbre | verdict |
|---|---|
| `be6245f6` (la base annoncée « verte ») | **9 échecs** |
| `bade659e` (`origin/master` au rebase) | **10 échecs / 48 passés** |
| mon arbre après rebase | **10 échecs / 48 passés — les MÊMES** |

Ils sont donc **étrangers à #931**. Le mécanisme de leur invisibilité est le point intéressant :
aucun de ces fichiers n'a d'entrée dans `scripts/ratchets-457-vert-offline.json`, et
`probe_547_ledger_sans_verdict_non_vert.py` ne juge que ce qui y est **écrit** — un « trou » y est
donc structurellement indiscernable d'un vert. Ils ne sont apparus qu'au moment où un run les a
JOUÉS. Résidu **#934**.

Conséquence pour cette PR : le ledger versionné a été **restauré** (les 14 attestations gagnées
comme les 7 rouges sont hors périmètre, et figer ces rouges ferait rougir `probe_547` sur `master`).
Seules l'empreinte et le poids des deux fichiers de test #931/#927 sont livrés.
