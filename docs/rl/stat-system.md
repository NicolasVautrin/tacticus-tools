# Systeme de stats natif — `UnitExtensions.GetStat` et ses dependances (port offline)

Build `gqfc5mff6c`. RE fidele (decompile = verite). Objectif : porter `GetStat` offline
= **calculer** `Initial + Sigma(stat-modifications actives)` par unite/StatType/StatPart, au
lieu de **capturer** la valeur Current resolue (combatSnapshot). Rend le moteur autonome +
modifiable (patch d'un stat/mod au bon endroit, comme le jeu).

Structure Python = mirror 1:1 (classe native -> classe homonyme, `# NomNatif @VA`).

## 1. Chaine d'appel (VAs)

```
GetStat(entity, statType, statPart, nullableSrc, flag)          @180ed30d0  (5-arg core)
  ` wrapper 4-arg (packe statType|statPart<<32)                 @180ed3cb0
  ` switch(statType) -> jumptable -> corps par-stat (inline, jumptable non recuperee)
      chaque corps -> composant du stat -> GetStatPart(part)
GetStatComponent(entity, statType)                             @180ed20c0  -> le StatComponent<T>
GetStatOverride(entity, statType, statPart)                    @180ed2800  -> struct override (5 dwords)

StatComponent.GetStatPart(comp, part, nullableSrc)            @180fa8bb0
StatComponent.get_CurrentValue(comp)                          @180fa91d0
StatComponent.GetClampedValue(comp, raw)                      @180fa8aa0
StatComponent.GetOverride(out, comp, src)                     @180fa8b80  -> ValueOverride.GetOverride
StatComponent.get_Modifications(comp)                         @180fa9340  -> ValueModification.get_Modifications
StatComponent.Modify(comp, ...)                               @180fa90d0

FillUpStatComponent.GetStatPart(comp, part, src)             @180f9b3a0  (Health/stat5 = "fill up")
FillUpStatComponent.GetOverride(out, comp, src)             @180f9b370
FillUpStatComponent.get_CurrentMaximumValue                  (max)

ValueModification.Modify(vm, src, amount, isMult, multVal)   @180fadfc0
ValueModification.ReverseModification(vm, src)               @180fae2d0
ValueModification.GetModificationFromEntity(vm, src)         @180fadf10
ValueModification.get_Modifications(vm)                      @180fae5a0
ValueModification.UpdateInitialValue(vm, ...)               @180fae3d0

ValueOverride.GetOverrideValueWithModification(vo, modTot)   @180fae700
ValueOverride.GetOverride(out, vo, src)                      @180fae860
ValueOverride.get_OverrideValue(vo)                          @180faeea0
ValueOverride.get_IsModifiable(vo)                           @180faedc0
ValueOverride.SetOverride / RemoveOverride                   @180faea70 / @180fae930
```

## 2. StatComponent — layout + resolution

Champs (offsets confirmes) :
- `+0x10` = **ValueModification** (`_modification`). Sous-champs : `+0x0`(int)=total Sigma, `+0x8`=Dict<srcEntity,Modifier>.
- `+0x20` = **ValueOverride** (`_override`).
- `+0x48` = **Initial** (int, la BASE pre-modifications).
- vtable `+0x1b8/+0x1c8` = GetMinValue / GetMaxValue (virtuels par-stat) pour le clamp.

`get_CurrentValue` @180fa91d0 :
```
ovr = ValueOverride.GetOverrideValueWithModification(comp+0x20, modTotal = comp[+0x10])
if ovr has NO value:  raw = comp[+0x48] + comp[+0x10]     # Initial + totalModification
else:                 raw = ovr.value                       # override (deja +mod si isModifiable)
return GetClampedValue(comp, raw)
```

`GetClampedValue(raw)` @180fa8aa0 : `Min(max, Max(min, raw))` (min/max = virtuels par-stat ; la
plupart min=0 max=+inf ; certains stats bornes).

`GetStatPart(part)` @180fa8bb0 :
- **0 (Current) / 2** -> `get_CurrentValue`
- **3 (Initial)** -> `comp[+0x48]`
- **5 / 9** -> `comp[+0x10]` (modTotal) ; si `nullableSrc` fourni -> `GetModificationFromEntity(src)`
- **7** -> ValueOverride path (`ValueOverride.GetOverrideFromEntity` + get_Value)
- **4** -> 0
- 6 / 8 -> NotImplemented

## 3. ValueModification — modifications ATTRIBUEES par source

`Modify(vm, src, amount, isMult, multVal)` @180fadfc0 :
- Dict `_modifications` keyed par **source entity** (lazy-cree). Un `Modifier` par source
  (additif ; ou `MultiplyModifier` si `isMult`).
- Si source absente : cree Modifier(amount), l'ajoute, `total += modifier.value`.
- Si source presente : `total = total - oldValue + newValue` ; si newValue==0 -> retire l'entree.
- => `total (+0x0)` = **Sigma sur les sources** de la contribution de chaque source.

`ReverseModification(vm, src)` @180fae2d0 : retire la contribution d'UNE source (total -= sa value).
`GetModificationFromEntity(vm, src)` @180fadf10 : contribution d'une source (0 si absente).

**Consequence cle** : une modification est **droppable individuellement** (par source). C'est ce
qui permet, offline, de retirer un buff conditionnel/expire pour recalculer Current sans lui.

**Sonde LIVE (RPC `statModSources`, rpc-view.ts)** : lit ce Dict par source SANS decoder son layout,
via `GetStat(entity, statType, StatPart=5, Nullable<BEntityId>=src)` (`GetStatPart @180fa8bb0` case 5/9,
decompile-verifie) : src null -> total `*(int*)(comp+0x10)` ; src fournie -> `GetModificationFromEntity
(comp+0x10, srcId) @180fadf10`. Le Dict est keye par l'entite **EFFET** qui a pose la modif (PAS le porteur
UNIT) -> `sourceIsUnit=false` pour une aura/effet ; mapper effet->owner pour remonter au UNIT. On scanne les
entites comme sources candidates -> `{source, amount, self, sourceIsUnit}` + `total` + `residual = total -
Sigma`. C'est la sonde DEFINITIVE pour SOURCER un `statDelta` opaque (ex. aura RitesOfBattle = LECTURE, pas
triangulation). Ne montre une aura d'adjacence que si l'unite est **actuellement adjacente** au porteur (la
ValueModification ne la contient qu'a cet instant). **VALIDE LIVE (demo #49)** : u82 bloodDeathCompany adjacent
Calgar -> `attack{total:1298, residual:0, source:97=effet RitesOfBattle_ExtraDmgImperial}` ; deplace hors
adjacence -> aura disparue. cf. `docs/rl/playbook/prediction.md` §8bis point 20.

## 4. ValueOverride

`GetOverrideValueWithModification(vo, modTotal)` @180fae700 :
```
if override HasValue: return override.value + (isModifiable ? modTotal : 0)   # Nullable
else:                 return no-value
```

## 5. FillUpStatComponent (Health-like, StatType 4/5)

Layout different : `+0x18`=valeur courante (ex. HP courant), max via `get_CurrentMaximumValue`,
`+0x10`/`+0x14`/`+0x28` = champs mod. `GetStatPart` : 0->courant(+0x18), 1->pourcentage
(`round(current/max*100)` en Fix64), 2->max, 3->+0x10, 4->max-current, 7->override.

## 6. Cote ECRITURE — d'ou viennent les modifications

Familles natives qui ecrivent dans `ValueModification` (via `StatComponent.Modify`) :
- **`AStatModifierEffect`** (effets stat-mod) : `GetStatModificationStat @180f0a890` (quel StatType),
  `GetStatModificationAmount` (magnitude), `GetIsStatModificationHidden @180f0a800`.
  - `StaticStatModifierEffect.GetStatModificationAmount @180f47430` (fixe).
  - `ADynamicStatModifierEffect.GetStatModificationAmount @180f090f0` + sous-classes
    `DynamicStatModifierEffect` (~30) : RitesOfBattleExtraDmg, Spotter_ExtraDmg, PathOfCommandExtraDmg,
    StandVigil_ExtraArmor, PowerUp_Armor, LionHelm_ExtraBlock*, Hypermorph, KustomForceField*,
    ContagionsOfNurgle_ArmorReduction, ContaminatedStatModifier, SummaryExecution*, PathOfCommandExtraCrit...
- **`SetupGameOperation.ModifyUnit*`** (setup-time, depuis la BC) : `ModifyUnitAttack @180e9afa0`,
  `ModifyUnitFixedArmor @180e9b770`, `ModifyUnitHits @180e9b910`, `ModifyUnitBlockChance @180e9b140`,
  `ModifyUnitCritChance @180e9b340`, `ModifyUnitCritDamage @180e9b540`, `ModifyUnitHp @180e9baa0`,
  `ModifyUnitMovement @180e9bc80`. Modifications **permanentes** (init de bataille), pas droppables.
- **`UnitExtensions.GetAbilityStatModification @180ece900`** (stat-mods portees par une ability).

**RapidAssault n'est PAS un `AStatModifierEffect`** (absent de la famille). Donc le `+1298` Attack de
u92 (bloodDeathCompany) N'EST PAS un stat-mod d'effet droppable connu -> candidat le plus probable :
une **modification SETUP** (`ModifyUnitAttack`, permanente) => base Current=4309 correcte en
permanence => la sur-prediction #49 serait **downstream** (agregation multi-coup / Blast vs armure /
RangedInMelee), pas la base. A CONFIRMER (RE `ModifyUnitAttack` + mesure live u92), ne PAS asserter.

## 7. Le consommateur : base de degat = un GetStat

`ALoki_NormalAttackAbility.AttackAmount @1811ae260` -> `DSLFactory.NormalAttackDamage @180df75e0`
-> `StatAmountFormula(statType, statPart)` ; `Calculate @180f22d40` = `Sigma_{unit selectionne}
GetStat(unit, statType@+0x18, statPart@+0x1c)`. ctor @180f230f0 : `+0x18=statType`, `+0x1c=statPart`,
`+0x20=targetSelector`, `+0x10=selecteur a2`, `+0x28=a6`.

Pour l'attaque normale : `NormalAttackDamage(dsl, *(dsl+0x160))` -> ctor(self, a2, **0,0,0,0**) ->
**statType=0 (Attack), statPart=0 (Current)**. Donc **base normale = `GetStat(attacker, Attack=0,
Current)`** = exactement `combatSnapshot.stats.attack`.

NB : le `GetStat(*(state+0x38), 5, 0, 0, 0)` dans `GetAttackHitPrediction @1811af4e0` lit le champ
`param_3[2]` (=defenseur) -> **Health(5) du defenseur** (cap overkill), PAS la base attaquant. La note
compactee "base=GetStat(5)" / "3011 = 4309 - 1298 buff attack" etait un double mis-read.

## 8. Plan de port offline (full layer)

`engine/entities/stats.py` (nouveau, layer partage sous runner ET prediction) :
- `ValueModification` : `total:int`, `per_source:dict[src,int]` ; `modify(src, amount)`,
  `reverse(src)`, `get_modification_from_entity(src)`. `# @180fadfc0/@180fae2d0/@180fadf10`.
- `ValueOverride` : `override:int|None`, `is_modifiable:bool` ;
  `get_override_value_with_modification(mod_total)`. `# @180fae700`.
- `StatComponent` : `initial:int`, `modification:ValueModification`, `override:ValueOverride`,
  `min_value/max_value` ; `get_current_value()` `# @180fa91d0`, `get_clamped_value(raw)` `# @180fa8aa0`,
  `get_stat_part(part)` `# @180fa8bb0`.
- `FillUpStatComponent` (Health) : `current`, `max`, parts (0/1/2/3/4/7). `# @180f9b3a0`.
- `UnitStats` : `dict[StatType, StatComponent]` ; `get_stat(statType, statPart)` = `UnitExtensions.GetStat`
  `# @180ed30d0`.

Enum `StatType` (rpc-view STAT_IDS + switch GetStatComponent/GetStatOverride) :
`Attack=0, Movement=1, ?=2, Defense=3, ?=4(fillup), Health=5(fillup), BlockChance=7, BlockDamage=8,
CritChance=9, CritDamage=10, ..., FixedArmor=16, ExtraHits=17`. Enum `StatPart` :
`Current=0, ?=2, Initial=3, mod=5/9, override=7`.

**Seeding** (`UnitContext.from_snapshot` / `snapshot.py`) depuis `combatSnapshot` :
- `initial = stats[k] - statDelta.get(k, 0)`  (statDelta = Current-Initial, deja emis).
- `modification.total` = `statDelta[k]` seede en une source "captured" (opaque) -> `get_stat(Current)`
  reproduit EXACTEMENT Current (zero regression). Quand une source est CONNUE (effet stat-mod porte,
  ou ModifyUnit* setup), la remplacer par sa contribution calculee/attribuee.

**Canal stat-mod effets** : `BaseEffect.get_stat_modification_stat()` + `get_stat_modification_amount()`
(homonymes `AStatModifierEffect`) pour les effets modeles ; NE PAS forker l'infra ActOfFaith (#32).

**Consommateurs** : `ctx.attack` etc. -> delegation a `get_stat(Attack, Current)` (behavior-preserving) ;
`StatAmountFormula`/prediction/crit/block lisent via `get_stat`.

Validation : cibles ciblees (test_predict_live, test_damage_*), + confrontation live u92 (#49) pour
trancher base-vs-downstream.

## 9. Cote ECRITURE porte : apply/revert stat-mod (FAIT)

Modele natif verifie (RE) :
- `AStatModifierEffect.ApplyInternal @180f0a180` -> `ApplyModification @180f0a2f0` : emet un
  `DSLFactory.ChangeStat` sur la **modification** du stat, `Position(statType, part=5|9)` (5/9 = branche
  modification de `GetStatPart`), magnitude = `GetStatModification` (tuple statType/amount/bool),
  attribue a la **source** (`DSLFactory.Entity(param_4)` = owner). `RevertModification @180f0aa40` =
  meme ChangeStat `part=6` (retrait).
- Magnitude : `StaticStatModifierEffect.GetStatModificationAmount @180f47430` = `EffectComponent+0x14`
  (fixe) ; `ADynamicStatModifierEffect.GetStatModificationAmount @180f090f0` = calcule (virtuel
  `GetDynamicStatModificationAmount`). StatType = `GetStatModificationStat @180f0a890` = `EffectComponent+0x10`.
- `SetupGameOperation.ModifyUnitAttack @180e9afa0` (+ ModifyUnit{FixedArmor,Hits,BlockChance,CritChance,
  CritDamage,Hp,Movement}) : setup-time, lit `Initial(+0x48)`, `CalculatePercentage(Initial, cfg%@param4+0x2c)`,
  emet un ChangeStat delta `Initial - pct`. **Valeurs = data BC** (non derivables du code) et **deja
  bakees dans la capture Current** -> l'offline ne les re-derive pas (placement Initial vs modification
  = `ValueModification.UpdateInitialValue @180fae3d0` pour le setup permanent, a confirmer).

`ValueModification.Modify @180fadfc0` (branche additive) — ISO porte :
- garde `if (amount != 0)` => `Modify(*, 0)` = **no-op** (retrait uniquement via `ReverseModification`).
- nouvelle source : `Modifier.value = amount`, `total += amount`. Source existante : `SetValue(amount)`
  (SET, PAS ADD ; `FUN_180003b40` = setter), `total = total - old + amount`.
- branche **MultiplyModifier** (`isMult`/`multVal`) NON portee (additif seulement).
`ValueModification.ReverseModification @180fae2d0` — ISO porte : `total -= contribution(source)` +
`Remove(source)` (no-op si absente).

Port (engine/entities/) :
- `StatComponent.modify(source, amount)` / `revert(source)` ; `UnitStats.change_stat(statType, source,
  amount)` / `revert_stat(...)` = ChangeStat apply(5/9)/revert(6). Cree le composant si absent.
- `BaseEffect.get_stat_modification_stat()` / `get_stat_modification_amount()` (homonymes, `None` defaut).
- `effects.apply_effect_stat_modifications(unit_stats, effects, source_of=None)` = mirror ApplyModification
  (itere les effets StatModifier, applique attribue par source). Revert = `unit_stats.revert_stat`.
- Valide en logique pure (SET/no-op-0/reverse iso + apply/revert canal).

Seeding-attribution (FAIT) :
- `stats.seed_unit_stats(stats, delta, ids, attributed=None)` : `attributed = {idxStat: {source: amount}}`
  applique les contributions attribuees PUIS le RESIDU `delta - Sigma attribuees` en `CAPTURED_SOURCE`
  -> `get_stat(Current)` reste EXACT ; `residu == 0` quand les effets modelises expliquent tout le delta
  = **validation non-circulaire** (Sigma magnitudes config == delta natif).
- `effects.stat_modifications_by_source(effects, source_of=None)` -> le dict `attributed`.
- `UnitContext.from_snapshot(..., effects=None)` calcule `attributed` si `effects` (BaseEffect materialises)
  fourni ; cable LIVE dans `runner/snapshot.py` (`load_state` materialise les effets par unite -> ctx.stats
  attribue). Prediction (scene.py) : opaque pour l'instant (la base = Current, correcte).

Magnitude concrete (FAIT) : `RitesOfBattleExtraDmgEffect` (loki.py) — `GetDynamicStatModificationAmount
@180f69810` = `ConfigVar(0x3f6, source, 8)` = `ability_var("RitesOfBattle","extraDmg",level)` (=9 @L1,
27 @L10), StatType=Attack. Enregistre `RitesOfBattle_ExtraDmg` (nom d'EffectType a confirmer live).
Valide bout-en-bout (materialise -> attribue -> residu 0 explique / 11 partiel ; load_state synthetique).
⚠ **Gap source-level cross-unite** : le niveau exact d'un buff applique par UN AUTRE (RitesOfBattle =
buff d'allie) est celui du SOURCE, absent de la capture -> on utilise l'ablvl de l'unite PORTEUSE ; le
residu opaque absorbe l'ecart (Current exact). A fermer par capture du niveau-source si besoin de residu 0.

Magnitude SELF-buff (FAIT, residu 0) : `StandVigilExtraArmorEffect` (loki.py) — `GetDynamicStat
ModificationAmount @180f6d910` = `ConfigVar(0x51c, source, 0x1b)` = `ability_var("StandVigil",
"extraArmor", level)` (=4 @L1, 13 @L10), StatType=FixedArmor(16). Enregistre `StandVigil_ExtraArmor`.
SELF-buff (source = l'unite) => niveau = le SIEN (capte) => magnitude EXACTE => **residu 0** (pas de
gap source-level, contrairement a RitesOfBattle). Valide bout-en-bout via `load_state` (attribue 4,
residu 0). ⚠ raffinement : le niveau vient de `passiveAbilityLevel` a la materialisation ; si l'ability
source est ACTIVE, utiliser `activeAbilityLevel` (le residu absorbe l'ecart sinon).

Operation runner ChangeStat (FAIT) : `engine/runner/operations/stat_ops.py` — `apply_change_stat(state,
unit, statType, source, amount)` / `revert_change_stat(...)` = mirror `ModifyStatMessage` (apply part
5/9 -> `UnitStats.change_stat` ; revert part 6 -> `revert_stat`) + **clamp** par-stat (`STAT_CLAMP_MAX` :
BlockChance/CritChance 100). AUCUNE synchro de champ plat : muter `UnitStats` suffit, le combat lit
`ctx.stat(type)` = `get_stat`. `_ensure_component` : `initial=0` si le composant est absent (les 8 stats
de base sont deja seedees a la construction -> ce chemin ne sert qu'aux StatTypes non-seedes, 0 = defaut
natif). GENERALISE la mutation ad-hoc ActOfFaith : revert EXACT par-source (`ReverseModification`) SANS
stocker de delta (plus fidele que `cc_delta/cd_delta`). Valide : apply/revert/clamp/ensure.

Integration runner (FAIT) :
- **ActOfFaith rewire** (`operations.triggers`) : `_apply/_reset_act_of_faith` utilisent `apply_change_stat`
  / `revert_change_stat` (source unique par stack) ; base crit-dmg = `get_stat(CRIT_DAMAGE, Initial)`
  (remplace la reconstruction courante-Σdeltas, exact aussi pour stacks seedes). Revert par-source, plus
  de `cc_delta/cd_delta` fonctionnel (informatif seulement). VALIDE live (accumulation + reset bit-exact).
- **Niveau-source active/passive** : `BaseEffect.active_ability_level` (unitConfig.activeAbilityLevel)
  threade via EffectFactory + snapshot.py ; StandVigil (active) indexe dessus. Buff passif = `ability_level`.
- **Migration consommateurs -> `UnitContext.stat(type)`** : tous les reads combat/prediction
  (`attack/crit_chance/crit_damage/fixed_armor/extra_hits`) dans damage.py / prediction.py / damage_model.py
  / active_ability.py / abilities/loki.py / triggers.py passent par `ctx.stat(StatType.X)` (enum).
  **Synchro de champ plat RETIREE** de `apply_change_stat` : muter `UnitStats` suffit.

- **Les 8 stats de base = PROPRIETES `get_stat` (FAIT)** : `attack/health/fixed_armor/extra_hits/crit_chance/
  crit_damage/block_chance/block_damage` ne sont plus des CHAMPS plats du dataclass `UnitContext` mais des
  **proprietes lecture-seule** adossees a `get_stat(Current)` (`ctx.attack` == GetStat natif, effet-inclusif ;
  ecriture -> `AttributeError`, muter = `apply_change_stat`). Source unique : `stats.CORE_STAT_FIELDS`
  (nom prop -> StatType). Le seeding est GARANTI : `from_snapshot` gap-fill via `UnitStats.ensure_seeded`
  (idempotent — ne clobbere pas le composant delta/attribue de `seed_unit_stats` ; couvre `stat_ids`
  absent/incomplet), `build_summon_context` seede les 8 depuis les variables `summon*` (block/hits = 0).
  Consequences : `_FLAT_FIELD` (unit_context) + `FLAT_FIELD` (stat_ops) SUPPRIMES, plus de double stockage
  ni de fallback. VALIDE live : test_getstat + test_summon_spawn + test_summon_trigger + test_act_of_faith
  (accumulation+reset) + test_runner_attack, tous verts ; + smoke pur-Python (from_snapshot/gap-fill/clamp/
  read-only/apply-revert/idempotent).

RESTE : confrontation live non-circulaire (residu 0) sur une unite portant StandVigil (craft via unit_map) ;
porter le canal aux StatModifier DYNAMIQUES concrets (cartographie ci-dessous, RE 2026-07-07).

## Magnitudes des StatModifier DYNAMIQUES (ADynamicStatModifierEffect) — RE 2026-07-07 (re-expert)

### Mecanique de base (PROUVE, VAs lues)
- `ADynamicStatModifierEffect.GetStatModificationAmount @180f090f0` = `round( virtuel[vtable+0x798](this) )`
  (arrondi NumberFormat). La VRAIE magnitude par sous-classe = son override **`GetDynamicStatModificationAmount`
  (vtable+0x798)**. Les sous-classes n'overrident PAS GetStatModificationAmount.
- **StatType = PAS dans l'override d'amount** : `AStatModifierEffect.GetStatModificationStat @180f0a890` (seule
  impl, aucun override) mappe le descripteur `AbilityOrEffect` (stocke au ctor base `@180f09280`, champ
  `Nullable<AbilityOrEffect>` @+0x14) -> `StatType` via un **dict statique `DAT_1831b92c8`** (valeur @+0x10).
  -> pour figer les StatType exacts, SOURCE = un champ de CONFIG lu au build (RESOLU 2026-07-08, cf. sous-section "StatType source" ci-dessous) ; RitesOfBattle StatType=Attack confirme
  live #49). Champs d'instance communs : `+0x48`=DSLFactory, `+0x60`=AbilityConfiguration, `+0x50`=contexte.

### StatType source = champ de CONFIG au build (RESOLU 2026-07-08, VAs lues)

Question item-2 ("decoder le dict AbilityOrEffect->StatType @180f0a890") tranchee par lecture :
le StatType d'un stat-mod N'EST PAS a decoder depuis le binaire ; c'est un CHAMP DE CONFIG lu au
build de l'effet.

- `DAT_1831b92c8` = Dictionary IL2CPP **metadata-populated** : les 18 xrefs sont TOUS des READ
  (lookups via `FUN_180007ae0`), AUCUN site d'ecriture / `.cctor Add` -> contenu issu de la
  metadata IL2CPP (init paresseuse `FUN_1801f2030(&DAT_1831b92c8)`), **non decodable statiquement**.
  Dans les builders, l'acces au dict sert la resolution du TYPE de composant (allocation blueprint),
  PAS la valeur du StatType.
- Build de l'effet : `AddStatModifierEffectBehaviour$$StatModifierBuilder @180fb7680` (et le lambda
  `<>c__DisplayClass11_1$$<Execute>b__0 @180fd9180`, invoque par delegate -> xrefs DATA) ecrit les
  champs de l'EffectComponent DEPUIS la config capturee (`ctx = *(param_1+0x18)`,
  `configDesc = *(ctx+0x10)`) :
    - `effect+0x10` = **StatType** = `*(configDesc + 0x6c)`
    - `effect+0x14` = descripteur `AbilityOrEffect` = `param_1+0x10`
    - `effect+0x1c`/`+0x1d` = flags (hidden...) = `configDesc+0x50`/`+0x80`
    - `effect+0x18..+0x38` = **DSL magnitude** (5 champs) = `ctx+0x18/+0x20/+0x28/+0x30/+0x38`
  Donc `StatType` = un NOMBRE de config (`config+0x6c`) fige au build, comme le jeu ; la magnitude
  (arbre DSL `ConfigVar`/`EffectSource`) = les 5 champs `ctx+0x18..` (miroir Pattern A/B).

=> **Port offline** : sourcer le StatType de chaque stat-mod dynamique depuis **gameconfig** (le
   champ stat-modifie declare par l'ability/effet), PAS via un decode du dict binaire. La
   correlation `varType->StatType` (0x1b=Armor, 0x14/15=Block, 0x41=Crit, 8/9=Damage) reste un
   raccourci de lecture, mais l'AUTORITE est la config (`config+0x6c`). RitesOfBattle=Attack et
   StandVigil=Armor (deja portes) sont coherents avec ce chemin.

### Deux patterns de magnitude (PROUVE)
- **PATTERN A** (~14 sous-classes) = arbre DSL `ConfigVar(configId, EffectSource(Get(target)), varType)` eval
  via `ConfigAmount.Calculate @180f171c0` = lit un NOMBRE DE CONFIG `configId` sur l'unite **SOURCE** resolue
  (son AbilityConfiguration), soit `GetVariableForLevel(configId, source.level)` soit `GetNumberConstant`. **=>
  la valeur (ex. +1298) est dans gameconfig/BC, PAS dans le binaire.** Port = `effects/magnitude.py::ability_var`
  (deja le miroir de `ConfigAmount.Calculate`) ; SEUL travail par effet = resoudre le `configId` numerique ->
  nom camelCase du `var_key` gameconfig (enum cle->nom absent du dump ; cas par cas, ex. RapidAssault 0xf =
  `rapidAssaultExtraDmgPct`).
- **PATTERN B** (~4 sous-classes) = lit une stat (`GetStat`) + scaling/negation (Hypermorph/PowerUp =
  `stat * GetNumberConstant(0x4f)/100` ; Contaminated = `-GetStat(6)`).

### Table des sous-classes (18) — configId/varType/pattern/aura
| Sous-classe | override @VA | Pat | Magnitude | Stat (hyp sauf note) | Aura/Self | Porteur (hyp) |
|--|--|--|--|--|--|--|
| **RitesOfBattleExtraDmg** | 180f69810 | A | `ConfigVar(0x3f6,vt=8)` | Attack (**confirme #49**) | **AURA r1** | Rites of Battle (Calgar) |
| RitesOfBattleExtraDmgImperial | 180f69a60 | A | `ConfigVar(0x3f6,vt=9)` | Attack | AURA | RoB Imperial |
| Spotter_ExtraDmg | 180f6cce0 | A | `ConfigVar(0x417,vt=8)` | Attack | AURA | Spotter |
| PathOfCommandExtraCrit | 18119c5f0 | A | `ConfigVar(0x458,vt=0x41)` | Crit | AURA/buff | Loki PoC |
| KustomForceField (+_Orks 180f53d00, Reworked 180f537c0) | 180f53a40 | A | `ConfigVar(0x44e,vt=0x1b)` | Armor | AURA/buff | Orks KFF |
| StandVigil_ExtraArmor | 180f6d910 | A | `ConfigVar(0x51c,vt=0x1b)` | Armor | buff | Stand Vigil |
| LionHelm_ExtraBlockChance | 180f55d80 | A | `ConfigVar(0x48b,vt=0x15)` | BlockChance | buff | Lion Helm |
| LionHelm_ExtraBlockDamage | 180f56000 | A | `ConfigVar(0x48b,vt=0x14)` | BlockAmount | buff | Lion Helm |
| SummaryExecution | 180f6f910 | A | `ConfigVar(0x409,vt=9)` | Attack | buff | Summary Execution |
| SummaryExecution_Always | 180f6fb90 | A | `ConfigVar(0x409,vt=8)` | Attack | buff | Summary Execution |
| **DynamicStatModifierEffect** (generique) | 180f3fe00 | A | `ConfigVar(this[+0x490\|+0x498], vt=this[+0x4a0])`, signe nie si `+0x4a4` | variable | selon usage | stat-mods config-driven (BEAUCOUP) |
| Contaminated | 180f3a460 | B | `-GetStat(stat=6)` | stat#6 negation | self debuff | Nurgle Contaminated |
| Hypermorph | 180f519f0 | B | `GetStat(5,part0) * GetNumberConstant(0x4f)/100` | (stat propre) | self | Tyranid Hypermorph |
| PowerUp_Armor | 180f45e20 | B | `GetStat(5,part2) * frac(GetNumberConstant(0x4f))` | Armor | self | PowerUp |
| PathOfCommandExtraDmg | 18119c7b0 | mixte | `If(IsSameFaction(owner,target), v8+v9, v8)` (vars 8/9 per-level de l'ability 0x458) | Attack | buff cond. faction | Loki PoC |
| ContagionsOfNurgle_ArmorReduction | override DIRECT `GetStatModificationAmount @180f39ce0` | config | `GetNumberConstant(cle=+0x488)` ; ctor `@180f39d20` AbilityOrEffect=0x431 | Armor (reduc) | AURA (ContagionsRange) | Nurgle Contagions |

### RitesOfBattleExtraDmg = gap #49 (effet 97 = +1298 Attack) — DETAIL
- **AURA prouve** `CreateTargetSelector @180f69770` = `AdjacentUnits(source, range=1) -> Friends ->
  UnitsWithoutTrait(0x1a)` = allies ADJACENTS (r1) de la source sans trait 0x1a. Match exact du +1298 adjacent a Calgar.
- **Magnitude** `@180f69810` = `ConfigVar(0x3f6, EffectSource, vt=8)` -> `config[0x3f6]` sur l'AbilityConfiguration
  de la SOURCE (Calgar) a son niveau. **Le 1298 = config[0x3f6] de RitesOfBattle pour Calgar** (gameconfig, pas binaire).
- **Port** : `amount = ability_var(rites_of_battle_id, var_key=<nom de 0x3f6>, level=source.level)`, applique en
  +Attack a chaque allie adjacent (r1, Friends, sans trait 0x1a). StatType=Attack confirme live #49.

### PROUVE vs HYPOTHESE
- PROUVE : chaine base->virtuelle+0x798->round ; Pattern A = ConfigVar/EffectSource/ConfigAmount lisant la SOURCE ;
  (configId,varType) par sous-classe (VAs) ; RitesOfBattle aura r1 ; ContagionsOfNurgle override direct ;
  Pattern B lecture GetStat+scaling ; PathOfCommand If(IsSameFaction).
- HYPOTHESE (a fermer) : (1) mapping `configId -> var_key camelCase -> valeur` = gameconfig, cas par cas ;
  (2) enum exact `varType` (StatType RESOLU = champ config `config+0x6c`, cf. sous-section "StatType source" ; correlation varType observee 0x1b=Armor, 0x14/0x15=Block,
  0x41=Crit, 8/9=Damage) ; (3) `statType=5/6` Pattern B ; (4) porteurs gameconfig (colonne Porteur) ;
  (5) branche `+0x490` vs `+0x498` du generique.

### Etat du port (MAJ 2026-07-07)
- **RitesOfBattleExtraDmg (#49)** : DEJA PORTE avant cette session (loki.py `RitesOfBattleExtraDmgEffect.
  create_aura_attack_bonus`, wire `prediction.py:189` via `aura_attack_bonus_from_allies`, RE-valide
  `extraDmg_2[L50]x1.8=1298`). Rien a refaire (verifie apres une fausse relance).
- **PathOfCommandExtraDmg (1112, Loki)** : PORTE cette session. `loki.py::PathOfCommandExtraDmgEffect.
  create_aura_attack_bonus` = AURA `SurroundingFriends @180dfc640` (`SurroundingTiles(range) - Tiles(self)`,
  self EXCLU) rayon 2 (`GetNumberConstant(0x16)=range=2`), meme equipe ; montant `@18119c7b0` =
  `If(IsSameFaction(owner,target), extraDmg+extraDmg_2, extraDmg)[niveau SOURCE] x mult SOURCE`. Wire :
  factory `PathOfCommand_ExtraDmg`, carrier etendu a 7-tuple avec `owner_grand_alliance`
  (`prediction.py`, type-level via vis_by_id -> GrandAllianceId, miroir-safe). Sanity offline OK (388
  same-faction / 222 autre faction / None hors-rayon,self,ennemi ; RitesOfBattle non regresse = 1298).
  **LIVE a valider** (Loki + allie a distance <=2 -> +extraDmg dans la prediction d'attaque de l'allie).
- **PathOfCommandExtraCrit (1107, extraCritChance)** : NON porte. Axe CRIT -> `create_aura_attack_bonus`
  ne couvre que Attack ; il faut un canal AURA-CRIT dedie (`create_aura_crit_bonus` + agregateur + wire
  dans la crit chance de prediction). `@18119c5f0` = `ConfigVar(0x458, EffectSource, varType=0x41)` =
  `extraCritChance[niveau SOURCE]` (NON scale rarete). TODO.

### Ordre de port suivant (recommande)
1. Canal AURA-CRIT (debloque PathOfCommand ExtraCrit + futurs crit-auras).
2. [RESOLU 2026-07-08] StatType = champ de CONFIG au build (`config+0x6c`) ; le dict `DAT_1831b92c8`
   est metadata-populated (NON decodable statiquement). -> sourcer le StatType depuis gameconfig
   (cf. sous-section "StatType source"). Plus de decode binaire a faire.
3. Generique `DynamicStatModifierEffect` (couvre beaucoup de stat-mods config-driven) une fois (1)+(2) surs.
