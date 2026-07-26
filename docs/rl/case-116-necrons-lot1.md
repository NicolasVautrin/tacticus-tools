# case #116 — Necrons lot 1 : 4 actives NO-OP côté COMBAT

> Build `gqfc5mff6c`. Port + confront live : `scripts/python/probe_116_necrons.py`
> (`--phase orb|chrono|mte`). Tranche de classification d'origine :
> [`case-220/necrons.md`](case-220/necrons.md) §6.7 + [`case-219-hard-kit-re.md`](case-219-hard-kit-re.md) §2.

| ability | id | porteur | verdict |
|---|---|---|---|
| ResurrectionOrb | 1009 | `necroOverlord` (pool) | **PORTÉ + VALIDÉ LIVE** (4 rounds bit-exact) |
| Chronometron | 1226 | `necroChronomancer` (hors pool → `catalog_inject`) | **PORTÉ + VALIDÉ LIVE** (unités/types/durées) |
| MultiThreatEliminator | 1006 | `necroDestroyer` (pool) | **PORTÉ + VALIDÉ LIVE** (4 régimes, chaîne bit-exact) |
| AdaptiveStrategy | 1005 | `necroWarden` (pool) | **RÉSIDU** — 3 prérequis nommés, dont un HORS périmètre |

Substrat ajouté au passage (tous ADDITIFS) : sélecteur `AllDeadOrResurrectedUnits`, factory `hero_units`,
liaison `ActiveTarget` par `Foreach`, accès `ctx.has_unit_flag`, centre-ENTITÉ accepté par `_within`,
feuille `ChainLeftOverHitsAttackDamage`, `per_hit_health`/`hp_before` exposés par
`AttackDamageOperation.execute_ability_attack`.

---

## 1. ResurrectionOrb (1009) — SUMMON PUR, aucune résurrection

`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$ExecuteBehaviour` — un SEUL nœud,
`AActiveAbility.Execute` **plain** (pas d'`ExecuteAtomic`, pas de `Group`) :

```
unitId  = GetStringConstant(config, 0)                                   # necroSmnWarrior
count   = GetMaxSummonsFormula(this).Calculate(entities)                 # EAGER (int), pas un noeud
tiles   = CanAddUnit(AdjacentTiles(caster@0x160))
Execute( Spawn(caster@0x160, PickRandomly(tiles, count, 0, 0x7fffffff, false),
               unitId, SpawnUnitOptions.WithStatsFromConfig(config, entities)) )
```

`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetMaxSummonsFormula` :

```
Min( Sum( Count( Friends(caster@0x160, UnitsWithTrait(AllDeadOrResurrectedUnits, 1000 = UnitTrait.LivingMetal)) ),
          StatAmount(caster@0x160, 0xc = StatType.TURNS_STARTED) ),
     Direct(6) )
```

**Le nom est du flavor** : l'arbre ne contient NI `Revive` NI `Resurrect` (aucun appel à
`DSLFactory$$Revive`/`$$Resurrect`, aucun `ReviveEffect`). La base REVIVE portée (#66/#79) n'a rien à
faire ici — vérifié au décompilé AVANT de coder. Les morts n'interviennent que comme **compteur**.

`IdunBattle.Entities.Selectors.AllDeadOrResurrectedUnitsSelector$$Select` (mirror) : la liste des MORTS du
state, **plus** toute unité portant le `UnitFlag 0xe` (« ressuscitée » — le flag que
`ResurrectUnitOperation` pose, côté port `UnitFlagsComponent.AMBUSH_CONSUMED`), sans doublon.

**Aucun sous-behaviour on-appearance** dans les options de spawn (le natif passe
`WithStatsFromConfig(config, execCtx, 0, 0)`) → le Warrior n'agit PAS à son apparition.

### Validation live (`--phase orb`, seed 777, board MC1_67, `necroOverlord` + `necroDestroyer`)

Cast SELF (cible prise dans `abilityTargets(...).fromHere` = le caster lui-même), 4 rounds consécutifs :

| round | `TURNS_STARTED` → formule `count` | spawns OFFLINE | spawns LIVE |
|---|---|---|---|
| 0 | 1 | 1 | 1 |
| 1 | 2 | 2 | 2 |
| 2 | 3 | **2** | **2** |
| 3 | 4 | **2** | **2** |

4/4 bit-exact. Les rounds 2-3 exercent le **cap de tuiles** : la formule rend 3 puis 4, mais
`CanAddUnit(AdjacentTiles(caster))` n'offre plus que 2 hexes libres (les Warriors des rounds précédents
occupent le reste) — offline ET live posent 2. Le terme `StatAmount(TURNS_STARTED)` est donc confronté
sur 4 valeurs distinctes, et le cap `PickRandomly` sur 2.

**Non couvert** : le terme `Count(amis LivingMetal morts/ressuscités)` (aucun allié LivingMetal n'est mort
dans ces runs) ; le cap `Direct(6)`.

---

## 2. Chronometron (1226) — poseur d'effets pur

`IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$ExecuteBehaviour` :

```
Execute( Foreach( GetAffectedEnemies,
                  op_BitwiseAnd( GetApplyStunOrPinToActiveTarget,
                                 GetAddExtraDamageEffectToActiveTarget ) ) )
```

- `$$GetAffectedEnemies` = `SurroundingEnemies(caster@0x160, GetNumberConstant(0x16) = range, 1, 3)`
  (surcharge 5-args : le même nœud est CENTRE **et** référence d'équipe) → ennemis du caster dans le
  disque `range` autour de sa tuile, caster exclu.
- `$$GetApplyStunOrPinToActiveTarget` =
  `If( HasTrait(It@0x180, 2 = UnitTrait.Summon), AddEffect(0x48a = EffectType.Stunned, …),
       AddEffect(0x429 = EffectType.Pinned, …) )`, durée `TurnsFromRounds(GetNumberConstant(0x45) = nrOfRounds)`.
- `$$GetAddExtraDamageEffectToActiveTarget` =
  `AddEffect(0x60e = EffectType.Chronometron_ExtraDamage, Owner@0x148 → It@0x180, <struct durée ZÉRO>)`
  → **pas** de `TurnsFromRounds` : durée par DÉFAUT de l'effet (même convention que le `Pinned` de
  CrushingClaws).

**`It@0x180` = le slot ActiveTarget** : `IdunBattle.Entities.Behaviours.ForeachBehaviour$$Execute` écrit
`entities[slot 4] = élément` avant d'exécuter un corps STATIQUE (branche `+0x60`), et c'est ce slot que
lit le sélecteur caché `factory+0x180`. Le `Foreach` du port lie désormais `subject` **et**
`active_target` (mirror des deux branches natives : lambda `Entity(elem)` d'un côté, écriture du slot de
l'autre). L'ability est **self-castée** : le `target` du message n'apparaît nulle part dans l'arbre.

### Validation live (`--phase chrono`, `catalog_inject` du porteur, seed 4242)

`necroChronomancer` + `necroOverlord` (allié témoin) vs `eldarRanger`, `astraBullgryn`, `tauMarksman`.
Le caster est AVANCÉ (`aiMovableTiles` + `applyAction move`, boucle endturn/aiturn) jusqu'à avoir une
cible légale `fromHere`.

```
OFFLINE  {77: [1065, 1550], 79: [1065, 1550], 81: [1065, 1550]}
LIVE     {77: [(1065, 2), (1550, 0)], 79: [(1065, 2), (1550, 0)], 81: [(1065, 2), (1550, 0)]}
VERDICT  unites=OK  types=OK  durees=OK
```

- les 3 ENNEMIS du disque rayon 2 sont touchés, **l'allié `necroOverlord` ne l'est pas**, le caster non
  plus → le filtre `Enemies` et l'exclusion du centre sont confrontés ;
- `Pinned` `remaining = 2` = `TurnsFromRounds(nrOfRounds = 1)` × 2 joueurs
  (`BattleQuery$$ConvertRoundsToTurns`) — offline identique ;
- `Chronometron_ExtraDamage` `remaining = 0` = durée par défaut — offline identique.

**Branche `Stunned` (trait `Summon`)** : aucun porteur `Summon` ENNEMI n'est spawnable directement
(`rl_duel build` refuse les ids `units.summons`, y compris injectés) et les summoners adverses
n'invoquent pas de façon déterministe sur ces boards. Confrontée **OFFLINE**, le trait étant la SEULE
variable (même état, même cast, `Summon` ajouté aux ennemis) : types posés `[1162, 1550]` au lieu de
`[1065, 1550]` → la branche route correctement. **Résidu de couverture assumé** : branche non confrontée
LIVE.

### Résidu : l'effet 1550 est MATÉRIALISÉ mais INERTE

`IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` :

```
EffectBonus( OwnerIsTarget & IsUnit(caster@0x160) & AreFriends(caster@0x160, EffectSource(Effect@0x150)),
             Multiply( If(IsMechanical(caster@0x160), ConfigVar(9 = extraDmg_2), ConfigVar(8 = extraDmg)),
                       TimesEffectApplied(Effect@0x150) ),
             AbilityOrEffect(0x4ca = 1226) )
```
+ `$$CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget & IsUnit(caster) & AreFriends(caster, EffectSource)`
(l'effet est CONSOMMÉ au premier coup d'un allié du Chronomancer).

Les **trois** entrées dont dépend la magnitude sont absentes du contexte que le port passe au hook
défenseur (`attacker_ctx` = `{id, is_normal_attack, faction}`) : (a) équipe de l'ATTAQUANT vs équipe de la
SOURCE de l'effet, (b) trait `Mechanical` de l'attaquant, (c) compteur `TimesEffectApplied` par instance
d'effet. Les câbler est un chantier transverse (élargissement d'`attacker_ctx` côté prédiction ET runner
+ compteur d'applications) — **volontairement non entrepris ici** : l'effet est posé et visible
(`decisionView`), sa contribution au dégât est nulle. Dégradation fidèle documentée
(« présent ≠ appliqué »), pas une magnitude inventée.

---

## 3. MultiThreatEliminator (1006) — `ChainLeftOverHitsAttackDamage`

`IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$ExecuteBehaviour` — UN nœud,
`ExecuteAtomic(this, tree, entities, 0x41)` :

```
ChainLeftOverHitsAttackDamage(
    caster@0x160, target@0x178,
    MinMaxDamage(minDmg/maxDmg[level]),                     # +0x68
    Direct(Nullable(GetDamageProfile(this)))                # +0xa0  -> config damageProfile = Gauss
    Direct(<champ STATIQUE de la classe> = 6),              # +0x98  hits
    AbilityOrEffect(this+0x10),                             # +0x70
    GetNextHitTargetSelector(this),                         # +0x88
    Get(GetNumberConstant(0x2b) = extraHit))                # +0x90
```

`nrOfHits` **n'est pas** dans la config de 1006 : les 6 coups viennent du champ statique posé par
`…MultiThreatEliminatorAbility$$.cctor` (`**(class+0xb8) = 6`) — déjà établi côté DÉCISION
([case-166-168](case-166-168-playbook-hits-and-min-damage-floor.md)).

`$$GetNextHitTargetSelector` =
`Unobscured(caster, Enemies(caster, SurroundingUnits(casterTile@0x168, range, 1, includeCenter=false, 3)))
 op_BitwiseAnd AdjacentUnits(Last(It@0x180, 1), 1, 3)` — « ennemi du caster dans le disque `range` autour de
sa tuile, non obscurci, ET adjacent à la DERNIÈRE cible frappée ».

### La boucle native (`ChainLeftOverHitsAttackDamageBehaviour$$Execute`)

```
hits = (+0x98).Calculate ; target = (+0x60).SelectSingle ; guard = 100
while guard > 0 and target != null:
    <attaque construite a la volee>.Execute(entities)
    entities[slot 4] = target                        # ActiveTarget = la cible qu'on vient de frapper
    hits   = GetLeftOverHits(this, target, entities)
    target = (+0x88).SelectSingle(entities)
    if hits <= 0 : return
    guard -= 1
```

`$$GetLeftOverHits` = « nb d'entrées `LeftOverDamage` de la cible portant notre `AbilityOrEffect` et dont
le flag est vrai » + `extraHits` si la liste est non vide. Les entrées sont posées par
`IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit` : (a) cible portant déjà le flag de mort
(`HasFlag(.., 8)`) → flag littéral 1 ; (b) coup FATAL → entrée portant le reste d'overkill
(`Damage(requested − applied)`), flag = `IsDead` **avant**, donc 0.

### ⚠ Ce que la MESURE a tranché (et ce qu'elle a réfuté)

La lecture naturelle — « le report vaut le nombre de coups tombés sur le cadavre » — est **RÉFUTÉE**.
Mesure live (`--phase mte`, une seule variable : les PV de la 1re cible, donc le nombre de coups
gaspillables) :

| PV 1re cible | coups gaspillés après sa mort | coups reçus par la 2e cible, LIVE |
|---|---|---|
| 8000 | 1 | **2** (2987 dmg, bit-exact sur 3 seeds) |
| 4000 | 3 | **2** (2987 dmg — IDENTIQUE) |
| 2500 | 4 | **2** (puis 3e cible : 2 coups) |

Le report est **CONSTANT = 1 + `extraHit`** dès que la cible MEURT, **0** sinon : le prédicat de flag ne
compte QU'UNE entrée par attaque tuante (celle du coup fatal), pas les coups gaspillés. Le modèle
« 1 par coup gaspillé » aurait donné 4 coups à la 2e cible sous PV 4000 → **sur-tir**. Le port mirror la
mesure ; la première version (sur-tirante) a été corrigée, pas ajustée par un scalaire.

Corollaire lu dans la même mesure : le natif **roule bien les 6 coups** même après la mort (le dégât de la
2e cible est bit-exact sur 3 seeds, ce qui exige un flux `state.rng` aligné) — il cesse seulement de les
APPLIQUER. Le port applique le total en un bloc : aucune différence observable (la cible est morte des deux
côtés) et aucune différence de consommation RNG.

### Validation live (`--phase mte`, board MC1_67, `--crit 0,0`)

| régime | offline | live | verdict |
|---|---|---|---|
| aucun kill (`--hp-target 60000`) | chaîne 1 maillon, 10786 | 10786 sur la cible | **bit-exact** |
| 1 kill (`--hp-target 8000`, seed 4242) | 79 : 6 coups 10786 → 77 : 2 coups **2987** | 77 : **2987** | **bit-exact** |
| 1 kill (seed 31337) | 79 : 10518 → 77 : **2687** | 77 : **2687** | **bit-exact** |
| 1 kill (seed 777) | 79 : 10666 → 77 : **2667** | 77 : **2667** | **bit-exact** |
| 1 kill, cible plus fragile (`--hp-target 4000`) | 79 → 77 : 2 coups **2987** | 77 : **2987** | **bit-exact** (discriminant du compteur) |
| 2 kills (`--hp-target 2500`, sans porteur Camouflage) | 81 : 9746 → 79 : 3733 | mêmes 2 morts, mêmes deltas | **bit-exact** |

Le delta systématique sur le CASTER (`83`) dans les traces live est la RÉACTION adverse
(`Overwatch_AutoAttack` / `WireweaveNet_CounterAttack` de l'`eldarRanger`) — hors ability, non rejouée
offline sur ce chemin.

**Résidu chiffré, INDÉPENDANT de la chaîne** : 3e maillon posé sur un porteur de
`Camouflage_HitReduction` (`tauMarksman`) — offline 2 coups (2613), live 1 coup (2423). Le canal de
RÉDUCTION DE COUPS défenseur sur le vecteur ability est en cause, pas le report : le MÊME régime
(`--hp-target 2500`) avec un 3e ennemi sans Camouflage est bit-exact. À traiter avec le canal
`hits_malus_from_defender_effects` (axe séparé).

**Résidu structurel** : `SelectSingle` du sélecteur de cible suivante prend le PREMIER élément dans
l'ordre d'énumération natif (tuiles, `UnitsOnTilesSelector`) ; le port prend le premier dans l'ordre
`ctx.units` (ordre d'entité ECS). Quand PLUSIEURS candidats satisfont l'intersection, la cible suivante
peut différer. Déterministe et identique dès que l'intersection a ≤ 1 élément (le régime mesuré ici).

---

## 4. AdaptiveStrategy (1005) — RÉSIDU, 3 prérequis nommés

RE COMPLÈTE (rien à re-faire au moment du déblocage).
`IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$ExecuteBehaviour` :

```
dmg    = MinMaxDamage(minDmg/maxDmg[level])
adjSel = GetNonCharacterFriendsSelector( AdjacentUnits(caster@0x160, 1, 3) )
allSel = GetNonCharacterFriendsSelector( <selecteur factory+0x80> )
tree   = If( ActorHasTriggeredAbility(caster@0x160, 0x3ec = TriggeredAbilityType.RelentlessMarch),
             TriggerAbility(caster@0x160, 0x3ec, …, 3) )
       + AddStatOverrideEffect(adjSel, 0x3f4 = EffectType.AdaptiveStrategy_DmgOverride, 0, dmg, 0, 1)
       + PerformAIAction(adjSel, asGroup=0, resetTurnFlags=1)
       + RemoveEffect(allSel, Nullable(0x3f4))
Execute(this, tree, entities)
```

`$$GetNonCharacterFriendsSelector(sel)` = `Friends(Self@0x148, sel, 3) op_Subtraction HeroUnits(sel, 3)`,
et `DSLFactory$$HeroUnits(sel, mask)` **délègue** à `UnitsWithTrait(sel, 0x10 = UnitTrait.Hero, mask)`
(pas de classe dédiée — la factory de composition est portée, `selectors.hero_units`).

Légalité : `$$GetDynamicInvalidTargetReason` = `HasTrait(target, 0x10 = Hero)` → raison **2** (invalide).
La cible doit être un allié NON-Hero.

`AddStatOverrideEffectBehaviour$$.ctor` (mapping lu) : `+0x58` sélecteur d'unités · `+0x60` effectType ·
`+0x64` → champ `+0x10` du blueprint `Blueprints.StatOverrideEffect` (valeur 0 ici) · `+0x68` nœud de
montant · `+0x78` flag (1). Le lambda `…u003CExecuteu003Eb__0` construit, PAR unité, un
`StatOverrideEffect{+0x10 = <+0x64>, +0x14 = <montant calculé>, +0x18 = <flag>}`.

**Les 3 prérequis, tous hors de ce port :**

1. **`RelentlessMarch` (TriggeredAbilityType 1004)** — passif de `necroWarden`,
   `…RelentlessMarchAbility$$CreateBehaviour`. **Explicitement hors périmètre de #116** (« ni les 3
   passifs Necrons »). Sans lui, la branche `If(ActorHasTriggeredAbility) TriggerAbility(…)` est un
   no-op structurel : porter AdaptiveStrategy avant lui livrerait la moitié de l'ability.
2. **Sous-système OVERRIDE-ATTAQUE** (`AddStatOverrideEffect` + blueprint `StatOverrideEffect` +
   `RemoveEffect` d'encadrement) — prérequis TRANSVERSE déjà inventorié
   ([case-220-classification-campaign](case-220-classification-campaign.md) : « Pattern OVERRIDE-ATTAQUE …
   SternguardFocus, ExemplarOfHate »). Le port n'a AUCUNE machinerie d'override de stat (il n'a que des
   modificateurs additifs/pourcentage).
3. **Nœuds `TriggerAbility` et `ActorHasTriggeredAbility`** — non portés (le second est une FORMULE côté
   natif : `DSLFactory$$ActorHasTriggeredAbility` alloue un objet à 2 champs `(unit, abilityType)`).

`PerformAIAction` (le 3e terme) est le SEUL prérequis déjà disponible
(`behaviours/ai_control.py` + `operations/summon_ai.py`).

---

## 5. Ce qui n'est PAS couvert

- **AdaptiveStrategy** : aucune ligne portée (cf. §4).
- **Chronometron** : branche `Stunned` confrontée offline seulement ; magnitude de l'effet 1550 non câblée.
- **MultiThreatEliminator** : régime « cible DÉJÀ morte à l'entrée de l'attaque » (site (a) de
  `AddLeftoverHit`) non atteignable dans une chaîne (le sélecteur de cible suivante filtre les vivants) —
  modélisé mais non confronté ; ordre de `SelectSingle` quand ≥ 2 candidats ; interaction avec le canal
  de réduction de coups défenseur (Camouflage, chiffré ci-dessus).
- **ResurrectionOrb** : terme « alliés LivingMetal morts » et cap `Direct(6)` non exercés.
- **Face DÉCISION** des 3 abilities portées : hors périmètre (elles étaient NO-OP côté COMBAT seulement).
