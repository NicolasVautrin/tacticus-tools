# Case #572 — `1061 UnbreakableDuty` (`templAncient` « Ancient Thoread ») : face COMBAT

**Statut : PORTÉ + CONFRONTÉ LIVE (build `rnca9r7q6c`, board `MC1_67`, seed 112112).**
Trois bras live, tous BIT-EXACTS ; huit mutations, huit rouges.

---

## 1. Ce qui était cassé

`1061` était un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc
`AbilityHandler.visit_ActiveAbilityMessage` l'ignorait — 0 effet, 0 soin, 0 dégât, aucune erreur.
Seuls **deux** des trois effets existaient côté port (`UnbreakableDuty_Health` 1251 et
`UnbreakableDuty_Damage` 1256, inscrits par #371 pour l'**attribution** du seed) ; rien ne les
posait, et le troisième — l'aura `UnbreakableDuty_DamageReduction` 1097 — se matérialisait en
`BaseEffect` NU (présent dans `decisionView.effects`, contribuant **zéro**).

## 2. La catégorie annoncée était INCOMPLÈTE — et c'est un résultat

`docs/rl/combat-ability-coverage.md` classait 1061 en **EFFECT/BUFF** (colonne dérivée du
`damageProfile` de l'**arme du porteur**, pas du behaviour). C'est vrai d'**une mécanique sur
cinq** :

| # | mécanique | nœud natif | ce que « EFFECT/BUFF » en dit |
|---|---|---|---|
| 1 | AURA −33 % de dégât REÇU, porteur + alliés ≤ 2 hexes, 1 round | `AddEffect(0x449)` | rien de la PROJECTION |
| 2 | +7275 PV MAX, permanent | `AddStaticStatModifierEffectToOwner(0x4e3, Health)` | ✔ |
| 3 | +7275 PV **COURANTS** | `ChangeStat(Owner, Health, mode 2 = Add)` | un SOIN, pas un buff |
| 4 | +1455 ATTACK, permanent | `AddStaticStatModifierEffectToOwner(0x4e8, Attack)` | ✔ |
| 5 | attaque NORMALE gratuite sur un ennemi adjacent | `UseActiveAbility(…, 0x45 = Loki_NormalAttack)` | **le cast FRAPPE** |

Les cinq s'apparient **une à une** aux cinq propositions de l'i2 (le +extraHp couvrant les deux
nœuds MAX et COURANT). Même configuration de « cast qui frappe par l'attaque NORMALE » que
`HolyDuel` 1050 et `Drachnyen` 1029 : `abilities.UnbreakableDuty` n'a NI `minDmg`/`maxDmg`, NI
`nrOfHits`, NI `damageProfile` (gameconfig : trois variables `dmgReductionPct`/`extraDmg`/`extraHp`,
une constante `range`).

## 3. L'arbre, LU au décompilé

`IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDutyAbility$$ExecuteBehaviour` —
**un seul** nœud terminal passé à `AActiveAbility$$Execute` :

```
extraHp  = DSLFormulas.ConfigVar(0x1e = extraHp,  AbilityState, config@this+0x60)
extraDmg = DSLFormulas.ConfigVar(8    = extraDmg, AbilityState, config@this+0x60)

[A] hpBuff  = AddStaticStatModifierEffectToOwner(0x4e3, statType = 5 Health,  extraHp,  turns = null, hidden = 0)
[B] hpFill  = ChangeStat(Owner@DSLSelectors+0x30, Stat(5 Health, part 0 Current), mode 2 = Add,
                         extraHp, modificationEntity = null, selectionType = 3, isModifiable = 0, isHidden = 0)
[C] dmgBuff = AddStaticStatModifierEffectToOwner(0x4e8, statType = 0 Attack, extraDmg, turns = null, hidden = 0)
[D] sel     = ValidNormalAttackTargets(CasterTile@+0x50, CasterTile@+0x50, null, null, null)
              op_BitwiseAnd AdjacentEnemies(Caster@+0x48, unique = 1, selectionType = 3)
    attack  = UseActiveAbility(Owner@+0x30, PickRandomly(sel, 1, 0, 0x7fffffff, 0), 0x45 = Loki_NormalAttack, …)
    free    = If(AmountIsGreaterThanZero(Count(sel)), attack, null)
[E] dead    = UnitsWithTraits(Friends(of = Owner@+0x30, entities = AllDeadOrResurrectedUnits(), 0),
                              [0x1a = Imperial, 0x10 = Hero], 0)
    gate    = AmountIsEqualOrGreater(Count(dead), Direct(2))
    gated   = If(gate, ((A + B) + C) + free, null)
[F] aura    = AddEffect(0x449, AbilityStateReference, Owner@+0x30, TurnsFromRounds(1))

Execute(entities, this, aura op_Addition gated)
```

Trois lectures qui n'étaient pas déductibles :

* **`AddStaticStatModifierEffectToOwner`** — la surcharge appelée est celle dont `turns` est un
  `IAmountFormula` (xrefs sur les deux corps : les deux call-sites de 1061 pointent le second) ⇒
  `turns = null` ⇒ **PERMANENT**, pas « 0 tour ».
* **`UnitsWithTraits`** est une **CONJONCTION** : le corps folde
  `left = op_BitwiseAnd(left, UnitsWithTrait(entities, t))` en repartant à chaque tour de la
  SOURCE. « Imperial **Characters** » = les deux traits, pas l'un ou l'autre.
* **`ValidNormalAttackTargets` reçoit `CasterTile` dans les DEUX slots** — lu aux octets du
  call-site (`mov r8,[r10+0x50]` puis `mov rdx,r8` : un seul chargement, deux registres), là où
  `SorcerousFacadeAbility$$GetTarget` passe `(Caster@+0x48, CasterTile@+0x50)` et
  `FinalJusticeAbility$$GetTarget` `(Owner@+0x30, Tiles(Owner))`. Sans conséquence de
  comportement : le slot `unit` est consommé par `SelectSingle` →
  `IdunBattle.DSL.TargetsSelector$$SelectUnit`, dont la tête est
  `if (IsUnitFoot(e) || IsTile(e)) e = UnitExtensions.GetUnit(e, state);` — une tuile résout en son
  occupant. Le port fait la même résolution (foyer `dsl/base._occupants_by_tile`).

### L'effet 1097

`IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDuty_DamageReductionEffect`, parent
`IdunBattle.Entities.Effects.BaseEffect` (⇒ face **DÉFENSEUR**) :

```
$$CreateEffectDamageMalusForDefense = EffectBonus.ForPercentDecrease(
        DSLTriggers.get_OwnerIsTarget,
        DSLFormulas.ConfigVar(0x46 = dmgReductionPct, GetAbilityState(effet), mult@+0x60))
$$CreateTargetSelector = TargetsSelector.op_Addition(
        Owner@DSLSelectors+0x30,
        DSLSelectors.SurroundingFriends(Owner@+0x30, ConfigConst(0x16 = range), unique = 1, 3))
```

Aucun gate mêlée/ranged, aucun gate de profil, aucune `ActiveCondition`.

## 4. Ce que le port a dû ouvrir

| foyer | ce qui a changé | pourquoi |
|---|---|---|
| `entities/effects/loki/unbreakable_duty.py` | +`UnbreakableDutyDamageReductionEffect` (DEUX pattes) | l'effet vit sur le CASTER et se PROJETTE |
| `entities/effects/factory.py` | inscription de `"UnbreakableDuty_DamageReduction"` | sinon `BaseEffect` NU |
| `entities/selectors/units.py` | +`units_with_traits` ; `ValidNormalAttackTargets` résout un slot TILE | deux nœuds natifs sans port |
| `runner/abilities/behaviours/stats.py` | branche **HEALTH** du `ChangeStat` mode 2 | Health est une stat **FILL-UP** |
| `runner/abilities/blacktemplars.py` | l'arbre + la classe + `TARGETING_OPTIONS` | le port |
| `runner/abilities/{handler,attack_type,targeting}.py` | les trois registres | contrat |

**Les DEUX pattes de 1097 sont DISJOINTES**, et c'est structurel : les deux agrégateurs state-wide
(`damage_model.defender_modifiers`, `playbook/prediction/_shared.py`) **écartent le porteur** de la
liste des `carriers` quand il EST la cible du coup. La patte SELF (`op_Addition(<Owner>, …)`) passe
donc par `create_effect_damage_malus_for_defense` (la boucle DÉFENSEUR standard, l'effet est dans
SA liste) et la patte projetée (`SurroundingFriends`) par
`create_aura_defense_damage_malus_for_ally`. Ni trou, ni double-compte. Même découpage que
`DestroyTheWitch_ExtraDamage` / `PsychicStalk_FriendlyChaosExtraDamage`.

⚠ **`SereneUnifierSenseOfStone` est un JUMEAU STRUCTUREL trompeur** : même
`ForPercentDecrease(OwnerIsTarget seul, ConfigVar 0x46)`, mais il n'a **aucun**
`CreateTargetSelector` — sa sélection est faite UNE FOIS à la pose, par l'`AddEffect(…, targets =
<sélecteur>)` de son poseur, donc l'effet est **matérialisé sur chaque bénéficiaire**. Recopier son
canal (`create_effect_damage_malus_for_defense` seul) aurait laissé les alliés **sans réduction**.
Ici l'`AddEffect` cible `Owner@+0x30` : **une** entité-effet.

## 5. Le `ChangeStat` sur HEALTH — un canal où le port perdait le soin SANS ERREUR

`IdunBattle.Entities.Behaviours.ChangeStatBehaviour$$Execute` branche `iVar1 == 2` construit
`StatModifier(Position(Health, Current), GetStat(Health) + delta)` — une valeur **ABSOLUE**, pas un
delta — puis `DSLBehaviors$$Transform`. Health est une stat **FILL-UP** (`HealthComponent`, PAS un
`StatComponent`) : c'est le même fait que portent déjà les deux feuilles voisines `SetHealth`
(mode 0) et `SubtractHealthPercent` (mode 3), qui mutent `hc.hp` directement. Router HEALTH vers
`apply_change_stat` écrivait dans `ctx.stats[5]`, **que rien ne relit pour les PV**.

**Mesure de la mutation M3** (branche désarmée) : natif **+9970 PV**, port **+0**. Silencieux.

**AUCUN clamp sur `hp_max`**, et c'est délibéré : le natif clampe contre un maximum qui vient
d'être relevé du même montant par le `AddStaticStatModifierEffectToOwner(HEALTH)` qui **précède**
dans la même séquence — son clamp est donc INERTE sur ce call-site. Côté port, `HealthComponent.hp_max`
est un champ FIGÉ que les stat-mods HEALTH (qui vivent dans `ctx.stats`) ne relèvent pas : clamper
introduirait un écart que le natif n'a pas. Le résidu est l'absence de propagation, pas le
non-clamp — **#572-r1**.

## 6. Confrontation LIVE

`probe_572_unbreakable_duty.py` — trois pas, chacun montant SON runner et le disposant.
Board `MC1_67`, seed 112112, rank 17, géométrie **choisie** (tuile à 6 voisins jouables, camps posés
à la main via `initAndStart`, cf. #477-r5).

⚠ **`legal_from_here` rend une liste VIDE pour toute unité dont ce n'est pas le tour** — mesuré le
2026-08-08, les trois unités adverses rendaient `legal=[]` sur leur propre attaque normale. Faire
mourir un **allié** du porteur, ou le faire **frapper par l'ennemi**, exige donc de rendre la main à
l'IA (`endturn`) puis de la reprendre.

| bras | natif | port | contre-modèle / contrôle |
|---|---|---|---|
| gate **FERMÉ** (0 mort) | effets `[1097 rem 2]`, gain PV **0**, attaque **0** | identique | — |
| gate **OUVERT** (2 morts) | `[1097 rem 2, 1251 rem 0, 1256 rem 0]`, gain PV **+9970**, attaque libre **7077** | `[1097 rem 2, 1251 None, 1256 None]`, **+9970**, **7077** | — |
| aura, ami **d = 1** | dégât reçu **2086** | **2086** | port sans 1097 : **3255** |
| aura, ami **d = 3** (contrôle) | **3255** | **3255** | port sans 1097 : **3255** (l'aura ne mord pas) |

`rem 0` natif ≡ `None` port : `EffectFactory` mappe un `remaining` capté à 0 vers « pas de compte à
rebours » (permanent). Magnitudes du banc : `level = 50`, `mult = 180 %` ⇒ `extraHp = 9970`,
`extraDmg = 1996`, `dmgReductionPct = 33` (HORS `variablesAffectedByRarityBonus`, donc non scalé).

## 7. Mutations — huit posées, huit rouges

| # | mutation | rouge offline | rouge live |
|---|---|---|---|
| M1 | `+extraDmg` posé APRÈS l'attaque libre | ordre + couple | dégât **7077 → 2606** |
| M2 | `units_with_traits` en UNION | conjonction + gate | — |
| M3 | branche HEALTH désarmée | `ctx.stats` au lieu de `hc.hp` | gain **+9970 → +0** |
| M4 | l'aura passe SOUS le gate | ordre + « hors du gate » | gate fermé : `[1097] → []` |
| M5 | gate de portée de l'aura inerte | patte AURA | hors portée : **3255 → 2086** |
| M6 | `AbilityAttackType` = `DirectTargetAttack` | registre | — |
| M7 | masque `rules`/`range` faux | registre | — |
| M8 | 1097 retiré de la factory | 4 tests | contre-modèle **2086 → 3255** |

**M1 est la mutation qui justifie la garde d'ORDRE** : permuter `[C]` et `[D]` ne change ni la
structure des effets, ni le flux RNG (les feuilles sont déterministes entre elles) — le banc live
aurait été vert sur tout SAUF le scalaire de l'attaque. C'est le seul couple ordonné observable.

## 8. Constat INDÉPENDANT — `master` (`ba6e78d2`) était ROUGE sur `test_519_comptes_derives_offline`

Mesuré en restaurant `targeting.py` à `HEAD` : le bloc généré annonçait
`len(TARGETING_OPTIONS_UNPORTED) = 22`, la mesure rendait **19**. Trois entrées avaient migré sans
régénération. Cette tranche le répare mécaniquement (`probe_519 --ecrire`, `22 → 18` dont **une
seule** de mon fait). Ce n'est pas une régression de ce port ; c'est le gisement que la doctrine
nomme déjà (« nos livraisons périment nos citations »).

## 9. Résidus ouverts

* ~~**#572-r1**~~ — **FERMÉ le 2026-08-10** par `ea55462c` : `docs/rl/case-572-r1-564-r1-r2-r3-reservoirs-de-pv.md`.
  Son successeur ouvert est **#572-r3** (`Armor` et `NumberOfMembers`, les deux autres stats
  fill-up). Ligne rectifiée au rebase : la laisser « ouverte » ici aurait été exactement le vice
  que la doctrine nomme — nos livraisons périment nos citations.
* ~~**#572-r2**~~ — **FERMÉ le 2026-08-10** : `engine/playbook/noncomparable/unbreakable_duty.py`.

### #572-r2, fermé — et le `BLOCAGE: etage` était résoluble OFFLINE

Les deux slots que la fiche déclarait non résolus se lisent dans
`data/symbols/<build>/metadata/interface_slots.tsv`, et l'**ARITÉ** tranche la surcharge (les deux
noms sont homonymes plusieurs fois) — signatures dans `frida/methods.tsv` :

| slot | méthode | signature retenue |
|---|---|---|
| `0x75` = 117 | `IBattleQuery.GetSurroundingUnits` (4 params) | `(from: IEntity, range: Int32, **friendsOf: IEntity**, includeCenter: Boolean)` |
| `0x7d` = 125 | `IBattleQuery.GetAdjacentEnemies` (3 params) | `(from: IEntity, playerEntityId: BEntityId, ignoreSteppables: Boolean)` |

⚠ **Le `friendsOf` était OMIS par la fiche**, et il est load-bearing : le premier terme ne compte
pas « des unités » autour du caster, il compte ses **ALLIÉS**, centre EXCLU.

`GetUseProbability`, relu terme à terme, rend un **POURCENTAGE** : le helper terminal fait
`Round(Fix64(p) / 100 * 100, 0) / 100`. Sans cette lecture, `p` valant 10/40/70 serait toujours
`>= 1` et le gate ne pourrait **jamais** rendre faux — la lecture change le comportement, elle ne
le décore pas. Et `GetAmountOfDeadImperialUnits` rend un `IdunBattle.DSL.IAmountFormula` (signature
lue), invoqué au slot **1 = `Calculate`** : c'est un COMPTE, le MÊME sous-arbre que le gate de la
face COMBAT.

**`EvaluateNonComparable` rend une utilité CONSTANTE** — `<statics+0x00>` = `Fix64(1)`, le MÊME
statique que `MIN_UTILITY`. Le playbook ne départage rien ; tout le discriminant est le gate.

⚠ **`_PlanTargetPlaybook` est le MAUVAIS générateur, et c'est mesuré.** Le masque de 1061 est
`0x8400` = `TargetIsFriendly | CasterIsPossibleTarget` ⇒ la cible est **ALLIÉE**, or
`computeAttackPlans` (`frida/hooks/features/ai-step/projection.ts`) boucle `for (const tgt of
enemies)` : le plan rend `(1061, u87, rankCount 0)` pendant que le natif propose `1061 → u79`, un
allié. Un port branché sur le plan serait **MUET, sans erreur**. Voie employée :
`abilityTargets.fromHere`, la même que `ThriceBlessedConflagrationPlaybook`.

**Confrontation** (`probe_572r2_unbreakable_duty_decision.py`, deux bras, oracle
`aiDryRunAllUnits`) :

| bras | `p` (port) | NATIF | PORT | contre-épreuve (registre sans 1061) |
|---|---|---|---|---|
| `isole` (0 allié à portée, 0 mort) | **0 %** | **0 cast sur 12** tirages | attaque normale | attaque normale — non discriminante, et le probe le DIT |
| `entoure` (4 alliés) | **40 %** | `1061 → u79` (1 cast sur 5) | `1061 → u79` | attaque normale — **MORD** |

⚠ **Le régime `prob >= 1` n'est PAS atteignable sur ce harnais**, et c'est une mesure : il faudrait
dix alliés dans le disque, or le maximum de spawns côté JOUEUR sur les 400+ boards de
`data/boards/global` est **7** (`C1_75`, `MC1_64`, `MC1_75`, `EMC4_05`, `survival_01`) — MC1_67 en
a **5**, et un build à 11 unités est refusé en amont du placement. Le critère du bras `entoure` est
donc l'**EXISTENCE** (≥ 1 cast sur N), pas la fréquence. Côté port le moteur est déterministe : il
propose dès que `p > 0` — écart de FRÉQUENCE assumé, même statut que `BlackRage` / `ItItches` /
`ScarabSummon`.

Non traité et NOMMÉ, hors des deux résidus :

* le volet `Targetable` du `unitSelectionType = 3` de `SurroundingFriends` n'est pas évalué dans le
  canal AURA (le `ctx` de l'agrégateur ne porte pas le `State`) — écart PERMISSIF borné aux
  porteurs d'un `UntargetableEffect`, qui n'encaissent aucun dégât pendant leur disparition. **Même
  limite que `PsychicFortress_DmgReduction` sur le même canal** ;
* aucune entrée dans `engine/entities/effect_targets.py::EFFECT_TARGET_SELECTORS` pour 1097 : aucun
  prédicat `IsTargetOfEffectOfType` ne le consomme dans le build courant, et une entrée
  spéculative serait un ajout sans mesure.
