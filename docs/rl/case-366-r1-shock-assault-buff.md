# case-366-r1 — `1000 ShockAssault_Buff` : PORTÉ

Le « +Damage for this attack » que le passif `ShockAssault` (`TriggeredAbilityType` 0x3ea = 1002) de
`ultraInceptorSgt` (« Bellator ») pose sur ses Inceptors avant de les faire attaquer.
i2 : « Whenever Bellator attacks, any Inceptor adjacent to him also attacks eligible targets,
dealing +{[extraDmg]} Damage for this attack. »

## 1. L'artefact natif (build `rnca9r7q6c`)

**Classe PROPRE**, `IdunBattle.Entities.Effects.Loki.ShockAssaultBuffEffect`, dérivée de
`IdunBattle.Entities.Effects.StaticStatModifierEffect` (`classes.tsv`). Son ctor est le corps FONDU
que Ghidra nomme `...Loki.SwarmHitReductionEffect$$.ctor` — **le nom du ctor ne fait pas l'identité**
(piège PR #411). L'identité est le slot `Il2CppClass*` `0x1833b6bc0` chargé par la fabrique
`IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_26`, dont
c'est **l'UNIQUE xref** sur tout le binaire : classe exclusive à l'id 1000. Le ctor ne fige **aucun**
argument (ni `AbilityOrEffect` source, ni stat, ni magnitude).

Son SEUL membre propre est le trigger de retrait.

### La pose — `ShockAssaultAbility$$CreateBehaviour` (non portée : l'ability 1002 est un item distinct)

    v   = GetVariableForLevel(config, 8 = extraDmg, <AbilityState du PASSIF>, fallback = 0)
    sel = GetAffectedUnits(Owner@DSLSelectors+0x30)
    AddStaticStatModifierEffect( targets = sel, effectType = 0x3e8 = 1000,
                                 statType = 0 = ATTACK, amount = Formulas.Get(v),
                                 turns = NULL, isHidden = true )
    & PerformAIAbility( sel, unit => UnitExtensions.GetNormalAttackType(unit), null,
                        <overrideMovement>, <utilityEntity>, customUtility = b__1_1 )

`GetAffectedUnits(origin)` = `EntitiesWithoutEffects( Filter( AdjacentUnits(origin, unique: 1, sel: 3),
IsUnitWithVisualId(It@DSLSelectors+0x68, GetStringConstant(config, 0 = unitId))
& AreFriends(Caster@DSLSelectors+0x48, It@+0x68) ), [0x4b9 = 1209 AttemptedPossession_Possessed] )`.

`CreateTrigger` = `On(0xa) & get_OwnerIsCaster & AmountIsGreaterThanZero(GetAffectedUnits(...))`.

### Le retrait — `ShockAssaultBuffEffect$$CreateRemoveEffectTrigger`

    On(0xa = AttackDamageAttack, ownerNeedsToBeAlive: 1) & get_OwnerIsCaster

greffé par `IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities` en
`Triggered(<ce trigger>, RemoveEffect(df@0x150))` — même greffe générique que `1180` (#114) et
`1550` (R9). **`turns = NULL` à la pose** : côté timer l'effet est PERMANENT, c'est ce trigger et
lui seul qui le borne.

⚠ Le MÊME event porte la pose et le retrait ; le seul discriminant est `OwnerIsCaster`, qui désigne
le **Bellator** pour l'une et l'**Inceptor** pour l'autre.

## 2. Ce que le montage live a mesuré

En régime NATUREL, 1000 est posé **et** retiré dans la même résolution — events d'un
`applyAction ability(69)` du Bellator :

    group 21 <bellator> Loki_NormalAttack · group 21 <bellator> ShockAssault
    group 22 <e103> ShockAssault_Buff · group 22 <e104> ShockAssault_Buff      # POSE (2 Inceptors)
    group 12/21 <inceptor-100> Loki_NormalAttack                                # PerformAIAbility
    group 22 <e103> ShockAssault_Buff                                           # RETRAIT (celui qui a frappé)

Il n'apparaît donc **jamais** dans un `decisionView`, même `includeInactive`, et l'ATTACK de
l'Inceptor est identique avant/après (997 → 997). Le levier qui ouvre la fenêtre est dans le
`customUtility` de `PerformAIAbility` (`...ShockAssaultAbility$$u003CCreateBehaviouru003Eb__1_1`) :
il rend **null** dès que `UnitExtensions.IsAlive(<cible>)` est faux. **Le Bellator tue sa cible ⇒
l'Inceptor ne joue pas et garde son buff.** Fabriqué par `--unit-stat <bellator>:Damage=500000`
(les Inceptors gardent leurs stats de kit, `WithStatsFromConfig`), avec un second ennemi pour garder
la bataille ouverte.

`probe_366r1_shock_assault_buff.py`, board MC1_67, seed 4471 — **deux régimes**, obtenus en
dissociant le niveau de PASSIF du poseur de son niveau d'ACTIF (que `buildNormalizedBC` met tous
deux à 50) :

| régime | `statMod.Amount` natif | `statModSources` (résidu) | gameconfig `extraDmg[L] × 180 %` | ATTACK avec / après |
|---|---|---|---|---|
| passif **50** (nominal) | **499** | 499 (résidu 0) | `extraDmg[50]` 277 → **499** | 1496 → **997** |
| passif **20**, actif 50 | **47** | 47 (résidu 0) | `extraDmg[20]` 26 → **47** | 1044 → **997** |

Trois canaux indépendants concordent, sur deux régimes : aucun scalaire n'est fitté, et le natif
indexe bien le **PASSIF** (réfute la lecture de l'ACTIF, qui donnerait 499 dans les deux).
`StatType = 0` (ATTACK), `ApplyCounter = 1`, `IsHidden = 1`.

### Le port, sur la même capture

| monde | ATTACK au seed | attribué | résidu opaque | après `On(0xa)` |
|---|---|---|---|---|
| LIVE (natif) | 1496 | 499 (source = l'entité-effet) | 0 | **997** |
| MOTEUR, inscrit | 1496 | **499** | **0** | **997** |
| MOTEUR, non inscrit | 1496 | 0 | 499 | **1496** — buff à vie |

## 3. Le canal `statMod` — la magnitude se LIT, elle ne se re-dérive pas

`decisionView.effects` publie, pour chaque effet, le `StatModifierComponent` de l'entité-effet, champ
par champ sous ses **noms natifs** (`frida/hooks/game/effects.ts::readStatModifier`, qui énumère les
champs DÉCLARÉS de la classe) : `{StatType, Amount, ApplyCounter, IsDynamic, IsHidden}`. Ces noms
concordent avec ce qu'écrit `AddStatModifierEffectBehaviour$$StatModifierBuilder` (`+0x10` statType,
`+0x14` amount, `+0x1c` isDynamic, `+0x1d` isHidden), et `Amount` est **exactement** ce que
`StaticStatModifierEffect$$GetStatModificationAmount` relit.

C'est décisif ici, parce que la re-dérivation gameconfig **ne peut pas** être exacte pour cet effet :
la feuille de pose passe `source = null`, donc `EffectComponent.SourceUnit` — le canal que
`effects_state.baked_ability_state` consulte — désigne le **PORTEUR** (le summon), pas le Bellator.
Mesuré : la re-dérivation rendait `extraDmg[1] = 5` là où le natif avait écrit `499`.

`BaseEffect.stat_mod` porte donc ce composant, `BaseEffect.captured_stat_mod_amount()` en extrait
`Amount`, et `ShockAssaultBuffEffect` le lit **en priorité**, avec repli sur `ConfigVar(8)` indexé
par le slot PASSIF quand le canal est absent (pose offline, capture antérieure au capteur). Le champ
est **inerte pour toutes les autres classes** : aucune ne le lit, aucune magnitude déjà validée ne
change.

⚠ Corollaire pour les cas voisins : la phrase de `case-371` « `decisionView.effects` n'expose ni le
stat ni le montant d'un effet capté » ne vaut plus **ni pour le montant ni pour le stat**. Le
recensement complet du gisement est fait — `case-366-r1-statmod-canal-capte.md` : sur les **31**
classes du registre qui déclarent une stat-modification, **deux** sont concernées (`1000` ici,
`1171 SereneUnifierStormOfFire` en régime cross-unité, basculé le 2026-08-01 — écart mesuré **721**
points d'ATTACK), 15 posent sur l'`Owner`, 1 reçoit sa source explicitement et 13 ont une magnitude
insensible à l'`AbilityState`. Le `source = null` n'est d'ailleurs pas un choix de `ShockAssault` :
**les trois surcharges `AddStaticStatModifierEffect` le passent**, et
`AddStatModifierEffectBehaviour$$Execute` retombe sur la cible. `captured_stat_mod_amount()` porte
depuis un gate `IsDynamic` (le natif recalcule pour cette famille, et le composant y vaut 0), et
`captured_stat_mod_stat()` fait le pendant sur `+0x10`.

## 4. Verdicts

* **`1000 ShockAssault_Buff` — PORTÉ**, les deux faces de son cycle de vie : la classe d'effet
  (`entities/effects/loki/shock_assault.py`, stat ATTACK + magnitude) et le trigger de retrait
  (`runner/operations/triggers/loki/shock_assault.py`, `On(0xa) & OwnerIsCaster`).
* **La POSE (ability `1002 ShockAssault`) reste NON PORTÉE** — item distinct (case-220 §6.9), et
  c'est ce qui rend le port de l'effet purement défensif côté moteur : offline, 1000 n'arrive que
  par le SEED. Ce que l'inscription ferme est donc (a) l'attribution par-source d'une capture qui
  porte le buff, et (b) sa durée.

## 5. Ce qui n'est PAS couvert

* **La pose offline** : le port ne pose jamais 1000 lui-même (l'ability 1002 n'est pas portée) — donc
  ni le sélecteur `GetAffectedUnits` (visualId + amis + `EntitiesWithoutEffects(1209)`), ni le nœud
  `PerformAIAbility` et son `customUtility`, ne sont portés. Ils sont lus et écrits ci-dessus.
* **La face DÉCISION** : `ShockAssaultPlaybook` (`SHOCKASSAULT_AdjacentSummon` = 25 par summon
  adjacent, cf. case-193) n'est pas touché par ce cas.
* **L'empilement** : `ApplyCounter` vaut 1 par construction (aucun `stacks_stat_mod_on_add`, gate
  « déjà présent » d'`AddEffectOperation`) ; le régime `ApplyCounter > 1` n'est ni atteint ni porté —
  le probe l'ASSERTE au lieu de le supposer.
* **`IsHidden`** : capté (`1`), non consommé par le port (c'est un flag d'affichage de la
  modification de stat).
* **Un seul board** (`MC1_67`) : la mécanique n'est pas positionnelle au-delà de l'adjacence
  Bellator↔Inceptor, que le montage vérifie explicitement (`dist = 1`).

## 6. Artefacts

| quoi | où |
|---|---|
| classe d'effet | `scripts/python/engine/entities/effects/loki/shock_assault.py` |
| trigger de retrait | `scripts/python/engine/runner/operations/triggers/loki/shock_assault.py` |
| registres | `entities/effects/factory.py`, `runner/operations/triggers/dispatch/registry.py` |
| canal `statMod` | `entities/effects/base.py` (`stat_mod`, `captured_stat_mod_amount`), `factory.py` |
| montage live | `scripts/python/probe_366r1_shock_assault_buff.py` (`--passive-level` = le 2ᵉ régime) |
| gardes | `tests/engine/runner/test_shock_assault_buff_expiry.py` (10, offline), `test_shock_assault_buff_live.py` (7, live) |
