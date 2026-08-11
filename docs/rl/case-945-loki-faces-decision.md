# #945 — six faces DÉCISION du lot `IdunBattle.AI.Playbook.Loki.*`

Les six faces COMBAT étaient portées et fidèles ; ce qui manquait, c'est l'**utilité de scoring** —
donc l'IA les *choisissait* avec une politique qui n'était pas celle du natif.

## 0. Ce que le lot a rendu, en une table

| ability | id | classe native | base LUE (`frida/classes.tsv`) | verdict |
|---|---|---|---|---|
| `AdaptiveStrategy` | 1005 | `…Loki.AdaptiveStrategyPlaybook` | `NonComparablePlaybook\`1` | **portée** — non confrontée live (§2, résidu `#945-r3`) |
| `StormOfWrath` | 1019 | `…Loki.StormOfWrathPlaybook` | `NonComparablePlaybook\`1` | **portée + CONFRONTÉE** (MISS → MATCH) |
| `BrazierOfHolyFire` | 1041 | `…Loki.BrazierOfHolyFirePlaybook` | `ComparablePlaybook\`1` | **portée + CONFRONTÉE** (dégât prédit ×2, §6) |
| `AlphaWarrior` | 1112 | `…Loki.AlphaWarriorPlaybook` | `NonComparablePlaybook\`1` | **portée + CONFRONTÉE** (MISS → MATCH) |
| `CalibaniteGreatsword` | 1189 | `…Loki.CalibaniteGreatswordPlaybook` | `NonComparablePlaybook\`1` | **portée + CONFRONTÉE** (MISS → MATCH) |
| `LeadingTheCharge` | 1204 | `…Loki.LeadingTheChargePlaybook` | `ComparablePlaybook\`1` | **SANS CONTENU PROPRE** (§7) |

Les six sont **reachable** : `data/symbols/<build>/metadata/active_playbook_builders.tsv` les
liste toutes les six dans le dict `active` d'`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`
(un playbook chargé PAR ABILITY). Aucun code registered-but-dead.

## 1. Le patron ne se factorise PAS, et c'est la mesure la plus utile du lot

Le brief supposait un `GetUtility` commun à factoriser une fois. **Il n'existe pas.** Les six
classes ne déclarent, `frida/methods.tsv` en main, que :

    AdaptiveStrategyPlaybook       ..ctor + EvaluateNonComparable
    StormOfWrathPlaybook           ..ctor + EvaluateNonComparable
    CalibaniteGreatswordPlaybook   ..ctor + EvaluateNonComparable
    AlphaWarriorPlaybook           ..ctor + .cctor + EvaluateNonComparable
    BrazierOfHolyFirePlaybook      ..ctor + MakeDamagePredictions
    LeadingTheChargePlaybook       ..ctor + MakeDamagePredictions

Ce qui est partagé est le **squelette** (`new Bucket` → `GetEligibleTargets*` → `GenerateAction` →
`AddAction`), déjà porté depuis longtemps par `engine/playbook/noncomparable/_base.py`. Tout le
reste — la formule, le seuil, le domaine de cible, les gates — est **propre à chaque ability**, et
chacun a coûté sa propre RE :

* trois provenances différentes pour le même `MIN_UTILITY` (`.cctor` / littéral INLINE / **aucun**) ;
* quatre domaines de cible différents (allié, ennemi du plan, **tuile**, **le caster lui-même**) ;
* deux slots d'`IBattleQuery` distincts à résoudre (16 et 195), plus un slot d'`IMovementQuery` ;
* un gate de vtable (slot 4) qui n'apparaît dans AUCUNE table de symboles (corps foldé) ;
* une condition qui est un **XOR**, pas un score.

**Coût mesuré** : la première face (1005) a demandé toute la mise en place — hiérarchie lue dans
`classes.tsv`, résolution du triplet `Owner@+0x30`/`Caster@+0x48`/`Target@+0x60`, choix de la voie
d'énumération. Les cinq suivantes n'ont **rien** hérité de cette lecture : chacune a exigé son
propre décompilé d'ability (`GetNumberOfHits`, `GetSweepAdditionalTargets`,
`GetChainedUnitsInternal`, `IsTargetInAttackRangeForSummon`) et sa propre table de slots. Le
rendement d'un lot est donc dans le **squelette déjà porté**, pas dans une factorisation à faire ;
calibrer les lots suivants sur « N abilities du même NAMESPACE » plutôt que « du même patron ».

## 2. `1005 AdaptiveStrategy` — l'ancre est la CIBLE, et ça contredit la face COMBAT

`IdunBattle.AI.Playbook.Loki.AdaptiveStrategyPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>()                       # ctor 2-ARG : AUCUN minUtility
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition.MainTile):
        sel = DSLSelectors.Friends(Caster@+0x48,
                  DSLSelectors.UnitsWithoutTrait(
                      DSLSelectors.AdjacentUnits(Target@+0x60, unique: 1, sel: 3),
                      0x10 = UnitTrait.Hero, 3), 3)
        n = sel.Count(entities)                             # ITargetsSelector slot 2
        if (n > 1) bucket.AddAction(GenerateAction(casterPosition, entities@+0x10, Fix64(n)))

**Le piège** : `IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$ExecuteBehaviour`
construit son set avec `AdjacentUnits(Caster@+0x48, 1, 3)` puis
`…AdaptiveStrategyAbility$$GetNonCharacterFriendsSelector` — il **BUFFE les alliés adjacents au
CASTER**. Le playbook, lui, **COMPTE les alliés adjacents à la CIBLE**. Les deux corps sont dans le
même binaire à quelques fonctions d'écart et n'ancrent pas au même champ. On mirrore le code, pas
l'intention (même forme de quirk que `MassDriverAccelerator`, #27-r1).

Il n'y a **pas** de `.cctor` sur cette classe : le seuil réel est le `if (1 < n)` du corps, que le
port transcrit en `MIN_UTILITY = 2` (l'utilité ÉTANT `n`).

Voie d'énumération : `…AdaptiveStrategyAbility$$.ctor` appelle la surcharge à 7 arguments de
`IdunBattle.Core.Services.TargetingOptions$$.ctor` — celle où le littéral EST le masque : `0x402` =
`TargetIsFriendly | TargetMatchesDynamicRule`. Le plan (`computeAttackPlans`) ne boucle que sur les
ENNEMIS : un port branché dessus serait MUET sans erreur. D'où `abilityTargets(uid, 1005).fromHere`,
la voie déjà employée par `UnbreakableDuty` et `ThriceBlessedConflagration`.

**NON CONFRONTÉE live, cause MESURÉE** : sur les **97** entrées de `rl_duel build --list-pool`,
**0** unité ne manque le trait `Hero` — le gate `n >= 2` est donc inatteignable sans SUMMONS.
Résidu `#945-r3`, avec le montage à écrire.

## 3. `1019 StormOfWrath` — la chaîne inclut la cible, et c'est ce qui donne son sens au seuil

`IdunBattle.AI.Playbook.Loki.StormOfWrathPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(Fix64.op_Implicit(2)))     # minUtility INLINE
    foreach e in BasePlaybook.GetEligibleTargetsEntities(caster, casterPosition.MainTile):
        n = battleQuery.<slot itf 16>(e, onlyFriends: true, additionalCondition: null).Count
        bucket.AddAction(GenerateAction(casterPosition, e, Fix64.op_Implicit(n)))

Le slot **16 d'`IBattleQuery` est `GetChainedUnits`** (`metadata/interface_slots.tsv`), et son
`onlyFriends` vaut `true` (littéral `1` du call-site) : ce n'est PAS un comptage d'ennemis autour de
la cible, c'est la taille de la **composante connexe d'unités amies de proche en proche** à partir
d'elle. `IdunBattle.Core.Services.BattleQuery$$GetChainedUnitsInternal` fait
`adj.Add(tile)` **avant** d'énumérer : la cible entre donc dans le set dès le premier niveau
(`IsFriend(cible, cible)` est vrai). **Une cible isolée vaut 1, pas 0** — et `MIN_UTILITY = 2`
signifie « il faut au moins un rebond ».

## 4. `1112 AlphaWarrior` — un VETO booléen, et un gate qu'aucune table ne montre

    bucket   = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))     # .cctor : Fix64(1)
    summonId = <AlphaWarriorAbility>$$GetSummonId(this.ability)        # corps DÉDUPLIQUÉ, étiqueté
                                                                      # `SporeMineLauncherAbility$$GetSummonId`
    foreach entities in GetEligibleTargetsSelectable(caster, casterPosition.MainTile):
        b = battleQuery.<slot itf 195>(caster, summonId, entities@+0x10)
        bucket.AddAction(GenerateAction(casterPosition, entities@+0x10, Fix64(b ? 1 : 0)))

Slot **195 = `HasSummonTargetInAttackRangeAtTile`**. L'utilité ne vaut que 0 ou 1 et le
`MIN_UTILITY` du `.cctor` vaut 1 : le playbook est un **VETO**, pas un score. La cible est une
**TUILE** (3ᵉ argument du slot), d'où la voie `fromHere` filtrée `kind == "tile"` +
`ctx.tile_id_by_pos`, comme `DarkTalonStrike`.

Chaîne native portée étage par étage (`GetNearestEnemy` depuis la tuile de spawn →
`IsTargetInAttackRangeForSummon` : portée `Max(w.Range ?? 1)` du summon, distance, puis
`IMovementQuery` slot 16 = `GetTilesObscuringTerrain(tile, t, 6, 2)` — mask et seuil identiques à
ceux que `battle_query.is_target_tile_obscured` mirrore déjà).

**Trois branches inertes, et l'inertie est MESURÉE** : `ShouldApplyRangedInMelee` est gaté sur
`HasTrait(0xb = UnitTrait.Ranged)`, trait qu'aucune unité ne porte ; les deux gates `range == 1`
sont morts car `tyranSmnWarrior` (le `constants.unitId` de 1112) porte une arme `Range: 2` ; et la
branche `IsMachine(parent)` n'est pas atteignable par ce porteur — **résidu `#945-r1`**.

**Le gate `ShouldEvaluate` était déjà porté sans qu'on le sache** :
`IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate` est le corps FOLDÉ (COMDAT) que
`_base._turns_started_gate` cite déjà — `GetStat(unit, 0xc = TurnsStarted) > 1`. Il n'apparaît dans
AUCUNE table de méthodes (corps partagé, un seul propriétaire par RVA) : c'est exactement le faux
négatif que le CLAUDE.md documente, et la classe qui NOMME ce corps est celle-ci.

## 5. `1189 CalibaniteGreatsword` — un INTERRUPTEUR, pas un score

L'utilité émise est la constante `Fix64.op_Implicit(0x7fffffff)`, la cible est **le caster**, et le
Bucket n'a aucun `minUtility`. Tout le contenu est dans la condition, et cette condition est un
**XOR** :

    A    = ∃ (tuile d'attaque, cible) : WillBeKill ET |extra| > 0
    B    = ∃ (tuile d'attaque, cible) : WillBeKill                       (A ⇒ B)
    C    = ∃ (tuile d'attaque, cible) : |extra| > 0
    cond = A ∨ (¬B ∧ C)
    ÉMET  ⟺  cond ≠ HasEffect(caster, 0x57d = EffectType.CalibaniteGreatswordSweep)

soit : **allume le sweep quand il servirait, éteins-le quand il ne sert plus**. Porter la moitié de
la formule laisserait l'ability collée en position haute (ou basse) sans que rien ne le signale.

**L'ORDRE des deux boucles natives n'a aucun observable** — et ce n'est pas une approximation :
le `return` du passage 1 ne se déclenche que sur `WillBeKill && |extra| > 0`, donc il est atteint
quel que soit l'ordre ; `found` n'est lu qu'après épuisement complet ; et l'utilité étant CONSTANTE
sur une cible unique (le caster), deux couples ne peuvent pas se départager.

`extra` = `…CalibaniteGreatswordAbility$$GetSweepAdditionalTargets` =
`AdjacentEnemies(Caster@+0x48, CasterTile@+0x50, unique: 1) op_BitwiseAnd AdjacentUnits(Target@+0x60, 1, 3)`
— une **INTERSECTION**, évaluée sur un `AbilityEntities` dont le `casterTile` est la **tuile
d'attaque candidate**. Deux gates amont : `HasTriggeredAbility(caster, 0x5f2 = RedemptionOfTheRisen)`
(résidu `#945-r2`) et `casterPosition != GetUnitPosition(caster)` — qui rejette **toutes** les tuiles
de move : l'ability n'est proposée que depuis l'origine.

## 6. `1041 BrazierOfHolyFire` — le nombre de coups DOUBLE contre un Daemon

`…BrazierOfHolyFirePlaybook$$MakeDamagePredictions` n'appelle PAS `AActiveAbility$$GetHits` : il
construit une formule et l'évalue sur la cible —
`…BrazierOfHolyFireAbility$$GetNumberOfHits` =
`ConditionalAmount(DSLTriggers.HasTrait(target, 0x3fb = UnitTrait.Daemon), nrOfHits_2, nrOfHits)`.
Config `rnca9r7q6c` : `nrOfHits = 2`, `nrOfHits_2 = 4`.

Deux écarts avec le chemin générique, tous deux dans le même sens :

* la branche `Daemon` était ignorée — **la moitié du dégât prédit** face aux 24 unités `Daemon` ;
* le résultat de la formule est passé **BRUT** : `GetDefaultAttackHits` (donc `ExtraHits`)
  n'intervient pas, alors que le générique l'appliquait. Même quirk que `HellfireShells` (#173).

La BASE, elle, était déjà juste : 1041 figure dans `_A_VIA_GET_DAMAGE_AMOUNT_MAIN` (#344) —
`<X>Ability$$GetDamageAmountMain` est le corps dédupliqué → `AActiveAbility$$MinMaxDamageAverage`.

**MESURE LIVE** (`probe_344_ability_damage_average.py`, `adeptCanoness` vs `worldEightbound`
[Daemon], board MC1_67 seed 909, deux niveaux d'ability) — oracle `aiPlaybookPredict` :

| bras | natif | port SANS #945 | port AVEC #945 |
|---|---|---|---|
| niveau 2 | `(36, 52, 4)` | `(18, 26, 2)` | `(36, 52, 4)` **== natif** |
| niveau 5 | `(52, 76, 4)` | `(26, 38, 2)` | `(52, 76, 4)` **== natif** |

Le troisième champ est le nombre de coups. Le port rendait exactement la MOITIÉ du dégât prédit.

## 7. `1204 LeadingTheCharge` — SANS CONTENU PROPRE, et c'est un résultat

`…LeadingTheChargePlaybook$$MakeDamagePredictions` est **structurellement identique** à
`IdunBattle.AI.Playbook.LightOfSanguiniusPlaybook$$MakeDamagePredictions` (les deux corps ont été
décompilés et comparés) :

    list   = new List<ProbableDamageEvent>()
    damage = <X>Ability$$GetDamage(abilityState, isPrediction: 1)    # corps DÉDUPLIQUÉ, étiqueté
                                                                    # `StaffOfStarsAbility$$GetDamage`
                                                                    # -> `AActiveAbility$$MinMaxDamage`
    hits   = AActiveAbility$$GetHits()
    prof   = AActiveAbility$$GetDamageProfile()
    list.AddRange(GenerateMultiHitAttackPredictions(caster, casterPosition, target, Target@+0x60,
                                                    damage, hits, Nullable(prof), null, 0))
    return list

Que des appels DIRECTS (non virtuels) aux corps de la classe de base : c'est **exactement** le
chemin générique du port, et `LightOfSanguinius` y est déjà traité ainsi. 1204 est déjà dans
`_A_VIA_STAFF_OF_STARS_GET_DAMAGE` (#344). Il n'y a **rien** à porter.

Le verdict est verrouillé par `test_945_loki_decision_faces_offline.py` : 1204 ne doit apparaître
dans AUCUN des cinq registres d'override — sans cette garde, la seule trace serait la prose, et le
prochain lecteur re-porterait un handler inutile (ou faux).

⚠ **La base `ComparablePlaybook<T>$$MakeDamagePredictions` est ABSTRAITE** (son corps lève) : ce
n'est donc pas elle le « générique ». Le générique est le corps de `DefaultActiveAbilityPlaybook`,
qu'IL2CPP réplique dans chaque spécialisation — d'où un symbole `MakeDamagePredictions` par classe,
y compris pour celles qui n'ajoutent rien. **Compter les symboles ne dit pas ce qui est surchargé.**

## 8. Validation

**Oracle = un TOUR D'IA OBSERVÉ** (`engine_validate.py`), jamais `aiPredict`. Chaque confrontation
est doublée d'une **contre-épreuve** : le MÊME montage rejoué avec le port DÉSARMÉ
(`git checkout HEAD~1 --` sur les foyers), pour établir que le MATCH vient de la tranche.

| montage | avec #945 | sans #945 |
|---|---|---|
| `necroWarden,ultraTigurius,tyranWingedPrime` vs `orksWarboss,tauCrisis,darkaCompanion`, MC1_67 seed 777 | ability **15/17 (88 %)**, sur-place **3/4** | 13/17 (76 %), 1/4 |
| `darkaCompanion@(3,4)` vs `tauCrisis@(3,5)`,`orksWarboss@(4,4)`, MC1_67 seed 2468 | ability **5/6 (83 %)** | 4/6 (66 %) |
| `adeptCanoness` vs `blackObliterator,worldEightbound`, MC1_67 seed 909 | 3/3 casts, 6/6 positions | idem (choix non discriminant) |

Les casts qui basculent, nommément :

* `step 7 u85 [ultraTigurius]` : natif `ab=1019 → tgt=123`. Sans la tranche, le moteur proposait
  `ab=69` (attaque normale) **et bougeait** — deux MISS ; avec, MATCH sur l'ability ET la position.
* `step 8 u87 [tyranWingedPrime]` : natif `ab=1112 → tgt=51` (une **TUILE**). Sans, `ab=69,tgt=123`
  — deux MISS ; avec, MATCH sur les deux.
* `step 0 u77 [darkaCompanion]` : natif `ab=1189 → tgt=77` (**le caster**, self-cast, en place).
  Sans, MISS ; avec, MATCH.
* `1041` : cf. §6 — le CHOIX concordait déjà (une seule ability offensive), c'est la MAGNITUDE qui
  était fausse d'un facteur 2.

**Offline** : `test_945_loki_decision_faces_offline.py` — 30 tests. Contre-épreuve de mutation :
**18 mutants du code de production, 18 mordent** (filtre `Hero` retiré, ancre `Caster` au lieu de
`Target`, seuil `1<n` abaissé, cible exclue de la chaîne, `onlyFriends` désarmé, `MIN_UTILITY`
abaissé, morts comptés, `>` → `>=` sur la portée du summon, gate `turnsStarted` retiré, cible nulle
acceptée, XOR → `cond` seul, intersection → union, gate triggered retiré, branches `nrOfHits`
inversées, handler retiré du registre, handler INVENTÉ pour 1204, playbook retiré de `PLAYBOOKS`,
`StormOfWrath` redevenue Comparable).

**Ce qui n'est PAS couvert** : la confrontation native de `1005` (résidu `#945-r3`) ; la branche MoW
du slot 195 (`#945-r1`) ; le gate `HasTriggeredAbility` sur une ability posée en cours de bataille
(`#945-r2`) ; le tirage aléatoire de `GetUseProbability` (écart assumé du moteur déterministe,
statut commun à `BlackRage` / `ItItches` / `ScarabSummon`) ; et la branche `range == 1` du slot 195,
morte pour le seul porteur connu.
