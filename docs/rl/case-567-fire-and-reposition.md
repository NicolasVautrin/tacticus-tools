# #567 — `1063 FireAndReposition` : trois mécaniques, une catégorie fausse, une durée à un tour près

Porteur : `eldarRanger` « Calandis » (HERO, **dans le pool** `rl_duel build --list-pool` rank 17).
Build : `rnca9r7q6c`.

## 1. La catégorie annoncée était fausse, et le COMPTE aussi

`docs/rl/combat-ability-coverage.md` classait 1063 en **EFFECT/BUFF**. Cette colonne dérive du
`damageProfile` de l'**arme** du porteur, jamais du behaviour — pour une ability non portée,
l'`ExecuteBehaviour` n'est connu de personne.

`IdunBattleLogic.Entities.Abilities.Active.Loki.FireAndRepositionAbility$$ExecuteBehaviour`, lu au
décompilé et remis en C# :

```
atk   = DSLBehaviors$$UseActiveAbility(
            subject     = Caster@DSLSelectors+0x48,
            targets     = Target@DSLSelectors+0x60,
            abilityType = DSLSelectors$$UnitNormalAttackType(Caster@+0x48),
            source      = Nullable(AbilityOrEffect$$op_Implicit(this)),
            <opts>, <opts> )
reset = DSLBehaviors$$ResetMovement( targets = Owner@DSLSelectors+0x30 )
eff   = DSLBehaviors$$AddEffect(
            effectType   = 0x456,                     # EffectType.FireAndReposition_ReduceDmg
            abilityState = AActiveAbility$$get_AbilityStateReference(this),
            source       = Caster@DSLSelectors+0x48,
            targets      = Caster@DSLSelectors+0x48,  # SUR ELLE-MEME
            turns        = DSLFormulas$$TurnsFromRounds(1) )
return AActiveAbility$$Execute(entities, this, op_Addition(op_Addition(atk, reset), eff))
```

**TROIS mécaniques**, et le tooltip i2 s'y apparie une à une — ce qui en fait un bon contrôle de
lecture :

| i2 (`Abilities/FireAndReposition_CurrentLevelDescription`) | nœud |
|---|---|
| « May move as normal and attack. » | [1] `UseActiveAbility` |
| « After attacking, she may make one more normal movement. » | [2] `ResetMovement` |
| « In the following enemy turn, she takes -{dmgReduction} Damage from ranged attacks. » | [3] `AddEffect(1110)` |
| « Can only be used if Calandis has a target in range. » | le masque de ciblage |

**Le cast FRAPPE**, mais par l'attaque **NORMALE** de l'unité. Deux sources concordantes : le nœud
`UnitNormalAttackType(Caster)`, et la config — `abilities.FireAndReposition` n'a **ni** `minDmg` /
`maxDmg`, **ni** `nrOfHits`, **ni** `damageProfile`, **ni** constante `range` ; **une seule
variable, `dmgReduction`** (65 niveaux, 30 → 2183, `variablesAffectedByRarityBonus`). Même
configuration que `HolyDuel` (1050) et `Drachnyen` (1029). Le `-2183` du tooltip n'est donc pas un
dégât : c'est la magnitude de [3].

L'effet **1110 `FireAndReposition_ReduceDmg` était DÉJÀ porté et validé live** (#366-r1,
`entities/effects/loki/damage_reduction.py`). Ce qui manquait, c'était sa **POSE** — 1063 était
absente d'`ABILITY_CLASSES`, donc `AbilityHandler.visit_ActiveAbilityMessage` l'ignorait : 0 dégât,
0 mouvement rendu, 0 effet, **aucune erreur**.

## 2. Ce que l'ORDRE coûte, et pourquoi il ne se déduit pas

Le décompilé emboîte `(atk + reset) + eff`. Le voisin `StrikeFromTheShadows` (1225) — **même patron
à trois feuilles, même famille de sélecteurs, même `ResetMovement(Owner@+0x30)`** — emboîte
`(atk + eff) + reset`. Deux ordres différents pour deux abilities jumelles : il se **lit**, il ne se
recopie pas.

**Et il est INVISIBLE en live.** Les trois feuilles sont déterministes entre elles (ni
`ResetMovement` ni `AddEffect` ne tirent de rng), donc permuter l'attaque et le reset ne change **ni
le dégât, ni le flux `state.rng`, ni l'état final**. Mesuré : sous la mutation
`op_add(op_add(reset, atk), eff)`, **seul `test_ordre_des_feuilles_offline` rougit — les quatre
tests LIVE restent VERTS** (1 failed, 6 passed). Un test « ça fire, les trois volets sont là » ne
l'aurait pas vu.

## 3. La durée : `TurnsFromRounds(1)` NU — la soeur en a un de plus

Le décompilé passe le résultat de `DSLFormulas$$TurnsFromRounds(1)` **directement** en 6ᵉ argument
d'`AddEffect`. `StrikeFromTheShadows`, lui, passe `Sum(TurnsFromRounds(1), <DSLFormulas+0x20 =
Direct(1)>)` = `TurnsUntilEndOfCurrentPlayersNextTurn`.

**Confirmé live** : `decisionView` rend `remaining = 2` après le cast, exactement
`convert_rounds_to_turns(st, 1)` ; la durée voisine vaudrait **3**. Recopier la durée de la soeur
aurait débordé d'un tour sans rien casser d'observable au cast.

⚠ **Le bras live ne le voyait PAS au premier jet** : il comparait `remaining` natif à
`convert_rounds_to_turns(st, 1)` — **deux lectures de l'oracle, aucune du PORT**. Une mutation
`duration_turns=3` sur l'arbre le laissait VERT. C'est `inst.remaining_turns` (la valeur rendue par
le port) qui ferme le circuit ; après couplage, la même mutation rend **deux** rouges.

## 4. Le masque : forme STATIC-COPY, preset `+0x00`, et un `forceMeleeTarget` unique

`FireAndRepositionAbility$$.ctor` n'appelle **aucun** `TargetingOptions$$.ctor` : il recopie les
0x40 octets du champ statique `<TargetingOptions statics>+0x00` (le tout premier preset) puis
`AActiveAbility..ctor(this, &opts, 2)`. Le preset, lu **en entier** dans
`IdunBattle.Core.Services.TargetingOptions$$.cctor` :

| offset relatif | valeur | lecture |
|---|---|---|
| `+0x00` | `0` | `isSelfCasting = false` |
| `+0x08` | copie de `TargetingRange statics+0x00` | `RANGE_ADJACENT_IF_MELEE_CASTER` (`onlyAdjacent = IfNotRangedCaster`) |
| `+0x20` | `2` | `forceMeleeTarget = RangedBool.IfRangedCaster` |
| `+0x28` | `0x4002` | `TargetMatchesDynamicRule \| TargetIsEnemy` |

`forceMeleeTarget = 2` : **1063 était la seule de son lot** dans ce régime — recopier le `1`
(`RangedBool.False`) d'une voisine aurait produit un masque faux, qui ne rougit nulle part.
Ce n'est pas théorique : sous la mutation `2 → 1`, **le balayage LIVE rougit** — `necroWarden` à
distance 2 devient légal côté port alors que le natif le refuse (`GetRange` rabat la portée à 1 dès
qu'un ennemi est au contact, exactement ce que le champ encode).

Le `range` du preset est `RANGE_ADJACENT_IF_MELEE_CASTER` et **pas** `RANGE_FROM_CONFIG` : cohérent
avec une config 1063 qui ne porte aucune constante `range` — il n'y aurait rien à lire. La portée
effective est celle de l'**arme**, ce que dit l'i2.

Deux lectures indépendantes concordantes : ce masque était déjà transcrit dans
`TARGETING_OPTIONS_UNPORTED`, et la relecture du `.cctor` faite pour ce port le confirme champ pour
champ. Il **MIGRE** sur la classe (contrat de disjonction).

## 5. `AbilityAttackType` = **2 `Others`** — contre-intuitif, et transcrit

3ᵉ argument d'`AActiveAbility$$.ctor` = le littéral `2`. Le cast **frappe** pourtant, ce qui ferait
écrire `DirectTargetAttack` à l'œil. C'est la lecture **inverse** de `HolyDuel` (1050) et
`Drachnyen` (1029) — mêmes dispatcheurs d'attaque normale, littéral `0`. Même valeur que
`FoulInfusion` (1038) et `WallOfMirrors` (1186). Le littéral se lit ability par ability : ni le nom,
ni le profil de dégât, ni la forme de l'arbre ne le prédisent.

## 6. Ce qui est confronté LIVE, et ce qui ne l'est pas

`probe_567_fire_and_reposition.py` (quatre volets) et
`tests/engine/runner/test_567_fire_and_reposition_live.py` (3 bras offline + 4 bras live × **deux**
couples `(board, seed)` : `MC1_67/31337` et `C4_09/4242`).

| volet | mesure | verdict |
|---|---|---|
| dégât | deltas HP par unité + séquence coup par coup + **état MT final** | live = port = `{79: 2726}`, 1 tirage, MT identique (`mti` 6 → 7 des deux côtés) |
| reset | `aiMovableTiles` avant/après + **second pas JOUÉ** | natif 0 → 19 tuiles ; port `Moved` absent, `ActiveAbilityUsed` présent ; pas joué et muté |
| effet | pose sur le CASTER (pas la cible), `remaining`, niveau baké | natif = port ; `remaining = 2` ; `active_ability_level = 50`, mult 180, bonus `Subtraction 2992` |
| gate | `abilityTargets.fromHere` contre `get_invalid_target_reason`, **toutes** les unités vivantes | 4/4 concordantes, 1 acceptée, 3 refusées pour **deux** raisons distinctes (`0x8000000` portée, `0x4000` `TargetIsEnemy`) |

**NON confronté** : la face **DÉCISION**. `IdunBattle.AI.Playbook.Loki.FireAndRepositionPlaybook`
n'a aucun équivalent dans `engine/playbook/` — résidu **#567-r1** (§7).

## 7. #567-r1 — la face DÉCISION, **PORTÉE ET CONFRONTÉE** (2026-08-10)

> ⚠ **La phrase qui suivait ce titre était FAUSSE, et la mesure la réfute.** Elle concluait
> « `.ctor` appelle `ComparablePlaybook<T>$$.ctor(this, 0x427)` **donc COMPARABLE** ». Ce ctor est
> un corps TRIVIAL (`base(id)`) que IL2CPP **DÉDUPLIQUE** : `VexillaMagnificaPlaybook$$.ctor`
> (0x49f), `HammerOfWrathPlaybook$$.ctor` (0x481), `StormcallerPlaybook$$.ctor` (0x459) et
> `UnbreakableDutyPlaybook$$.ctor` (0x425) appellent **exactement le même corps**, et les quatre
> sont des NonComparable avérés. La hiérarchie se lit dans
> `data/symbols/<build>/frida/classes.tsv` :
> `IdunBattle.AI.Playbook.Loki.FireAndRepositionPlaybook  112  IdunBattle.AI.Playbook.NonComparablePlaybook`1`.
> C'est la **MÊME** correction que #487-r1 avait dû apporter à `case-487` §7, pour la même raison.
> Second discriminant, indépendant : la signature de `EvaluateNonComparable` dans
> `frida/methods.tsv` est identique à celle d'`UnbreakableDutyPlaybook`.
>
> **Port** : `engine/playbook/noncomparable/fire_and_reposition.py`, `_PlanTargetPlaybook`
> (1063 cible un ENNEMI — `rules = 0x4002`). **Confrontation** :
> `probe_567r1_fire_and_reposition_decision.py`, DEUX bras.
>
> | bras | NATIF | PORT | contre-épreuve `-20` | contre-épreuve `0` |
> |---|---|---|---|---|
> | `recul` (ennemi au contact) | `1063 → u79`, `move=(2,3)` (d 1 → 2) | identique | `to=None` **MORD** | `(2,3)` — NON discriminante |
> | `attribution` (ennemi en (1,4)) | `1063 → u79`, `move=(4,2)` | identique | `(2,3)` **MORD** | `(2,3)` **MORD** |
>
> Le bras `recul` **n'attribue rien**, et c'est une MESURE : la décomposition y montre **cinq**
> positions éligibles à la MÊME utilité `91.5` — `20·d` et `Tile(7)` se compensent exactement —
> donc c'est le keep-first du `Bucket` qui tranche. Le bras `attribution` place l'ennemi d'après la
> table `Tile(7)` **mesurée** du board pour rendre l'argmax **STRICT** (111.5 contre 91.5, marge
> 30) sur une tuile que `Tile(7)` seul ne désignerait pas en premier. Sans ce second bras, l'accord
> serait compatible avec le port sans en établir un seul terme.
>
> **`entities@+0x40` est la tuile du CASTER, pas celle de la cible** — offsets lus dans
> `BasePlaybook$$GetEligibleTargetsSelectable` (`+0x08`/`+0x18` = caster, `+0x10` = cible, `+0x30`
> = `GetMainTile(cible)`, `+0x40` = `possibleCasterTile`). Le paramètre natif s'appelle pourtant
> `targetTile` : le nom ne dit pas ce que l'appelant y met. Conséquence de fond — le terme de
> distance ne dépend **pas** de la cible.

Structure de son évaluation, lue :

```
bucket = new Bucket<...>(0, Nullable(<statics+0x00>))          # cctor : Fix64.op_Implicit(1)
foreach (entry in BasePlaybook$$GetEligibleTargetsSelectable(this, caster, casterPosition.MainTile)) {
    u   = Fix64.FromIntFraction(3, 2)                          # 1.5
    sel = TargetsSelector$$SelectUniqueUnits(
              DSLSelectors$$Enemies(Caster@+0x48, AllAliveUnits@+0x20, 3), entry, 3)
    u  += Fix64(GetAverageDistance(this, <tile>, sel) * 20)
    u  += GetTileUtility(this, entry)
    bucket.AddAction(BasePlaybook$$GenerateAction(this, casterPosition, <..>, u))
}
```

`GetAverageDistance(targetTile, otherUnits)` = somme des distances (slot `+0x6c` du
`IBattleQuery` de `this+0x28`) divisée par `Count(otherUnits)` — **division ENTIÈRE**.
`GetTileUtility(targetEntities)` passe par `UnitExtensions$$GetNormalAttackType` puis
`IdunBattle.AI.Utilities.UtilityAttackCase$$Base` et un slot d'interface `+5`.

`GetAverageDistance` rend un `System.Int32` (type de RETOUR lu dans `frida/methods.tsv`) et son
corps fait `(longlong)sum / (longlong)count` : la division est **ENTIÈRE**. Le slot `0x6c` = **108**
= `IBattleQuery.GetDistance` (arité 2), résolu dans
`data/symbols/<build>/metadata/interface_slots.tsv` — 108/109/110 sont trois surcharges homonymes,
c'est le TYPE des arguments qui fixe celle-ci.

`GetTileUtility` lit `utilitiesDatabase<this+0x40>.Get(7 = UtilityType.Tile)` puis invoque le slot
`+5` sur un `UtilityAttackCase$$Base(caster, casterTile, cible, Nullable(AbilityOrEffect(
GetNormalAttackType(...))))` : c'est le composite **Tile(7)** évalué sur la tuile de CAST, dont le
port a déjà le foyer unique (`engine.playbook.base.tile_utility`).

## 8. Réparé au passage — un rouge de `master`

`test_the_pool_abilities_carry_a_read_mask` (`tests/engine/test_433_r4_r2_r1_r2_ability_range_offline.py`)
rendait `manquants = [1050, 1121, 1164]` **sur `edfdda38`** : trois tranches ont migré leur masque
sur la classe sans retirer leur id de `POOL_ABILITIES_WITHOUT_COMBAT_CLASS`. **Rouge reproduit sur
un `git archive HEAD` intact**, hors de toute modification de #567 — il préexiste. Résolution par
**UNION** des retraits (1050, 1063, 1121, 1164), re-vérifiée par le code (`manquants` == `intrus`
== `[]`). C'est exactement le croisement de branches que le commentaire du fichier décrit déjà.

## 9. Table des mutations adversariales

Chaque garde a été vue ROUGE par une mutation **appliquée**, la passe rejouée, la source restaurée,
`git status` propre après.

| mutation | rouges |
|---|---|
| `op_add(op_add(reset, atk), eff)` (ordre) | `ordre_offline` **SEUL** — les 4 bras live restent VERTS |
| `force_melee_target` 2 → 1 | `registre_offline` + **`gate_de_cible_live`** |
| `duration_rounds=1` → `duration_turns=3` | `duree_offline` + **`effet_pose_live`** (après couplage §3) |
| effet sur `Target()` au lieu de `Caster()` | `ordre_offline` + `effet_pose_live` |
| `ResetMovement(Target())` au lieu d'`Owner()` | `ordre_offline` + `reset_movement_live` |
| `scale_from_source=False` | `ordre_offline` + `effet_pose_live` |
| `ABILITY_ATTACK_TYPE` 2 → 0 | `registre_offline` |
