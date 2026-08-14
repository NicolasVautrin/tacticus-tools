# #1024-r2 — `OnMyPosition` PORTÉE et CONFRONTÉE LIVE ; et la face DÉCISION de `BasiliskBarrage`, dont le verrou est LEVÉ mais qui reste à porter

**Verdict par item**

| item | verdict |
|---|---|
| `OnMyPosition` (`EffectType` 1444, MoW `astraOrdnanceBattery`) | **PORTÉE** (`EFFECT_CLASSES` + `ABILITY_INIT_OWNER_EFFECTS`), gardée offline (30 tests, **16 mutations adversariales / 16 rouges**) et **CONFRONTÉE LIVE en régime SÉPARANT** — accord `natif == port` sur **4/4** bras |
| face DÉCISION de `BasiliskBarrage` (1026, `astraOrdnance`) | **NON PORTÉE** — RE complète écrite ici, et la question binaire qui la bloquait est **TRANCHÉE PAR MESURE**. Résidu **`#1026-r1`** |

---

## 1. `OnMyPosition` — l'aura, portée

La RE et la première confrontation live datent de **`#1024`** (`case-1024-shield-of-faith-on-my-position.md`),
qui concluait « aucune des deux n'entre au port : leur gate commun est `HasRarity(·, Mythic)`, et le
port n'a **aucun canal de rareté** ». **Ce verrou est tombé** : `att_rarity` est threadé sur les deux
faces depuis `#999-r3-r1`, et l'univers de porteurs des deux agrégateurs d'aura est board-wide —
donc MoW-compatible — depuis `#999-r3-r1-r1`. Cette tranche est le volet PORT, rien d'autre.

### L'artefact natif, relu en entier

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.OnMyPositionAbility` dérive
d'`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` — **deux sources indépendantes
concordent** : `data/symbols/<build>/frida/classes.tsv` donne le parent, et
`search_symbols_by_name` ne rend pour cette classe que `$$GetEffectType`, dont le corps ENTIER est
`return 0x5a4` (= 1444). Le trigger et le behaviour sont ceux de la base (`OnOwnerSpecificAbilityInit`
→ `AddEffect(source = targets = Owner)`), d'où l'entrée `ABILITY_INIT_OWNER_EFFECTS["OnMyPosition"]`.

`IdunBattle.Entities.Effects.Loki.OnMyPosition_ExtraDamagePctEffect$$CreateTargetSelector` :

```
Enemies( Owner@<DSLSelectors+0x30>,
         AdjacentUnits(
           op_Addition(
             Friends( Owner@+0x30,
                      UnitsWithVisualId( VisualUnitIdFromUnitId( Get( ConfigConstString(<config>, 0) ) ),
                                         1 = UnitSelectionType.OnlyAlive ),
                      3 ),                                        # branche A -- Cadian Guardsman
             UnitsWithRarity( Friends( Owner@+0x30, HeroUnits( AllUnits@<DSLSelectors+0x20>, 3 ), 3 ),
                              5 = idun.meta.Rarity.Mythic, 3 ) ), # branche B -- Mythique HERO
           unique: true, 3 ),
         3 )
```

`...$$CreateEffectDamageBonusForAttack` :

```
EffectBonus.ForPercentIncrease(
    get_OwnerIsTarget
      & ( AreFriends( Caster@<DSLSelectors+0x48>, EffectSource@<DSLSelectors+0x38>, 0, false )
          & HasRarity( Caster@+0x48, 5 = idun.meta.Rarity.Mythic ) )
      & IsRangedAttack,
    ConfigVar( 0xa = extraDmgPct, GetAbilityState(this), <config@this+0x60> ) )
```

### Les TROIS pièges que le voisin de forme aurait fait rater

1. **1444 n'a AUCUN seuil de compte.** Son jumeau `MoreGitzOverEre` (1449) exige `>= 2` amis
   Mythiques (`AmountIsEqualOrGreater(..., Direct(2))`, **dans** le sélecteur) ; ici les deux
   branches sont UNIES **avant** l'`AdjacentUnits`, donc **un seul** voisin suffit. Recopier le seuil
   du voisin donne un port qui se tait dans le cas le plus fréquent.
2. **La branche B porte un étage `HeroUnits` que 1449 n'a pas.**
   `IdunBattleLogic.Entities.DSLSelectors$$HeroUnits(entities, selectionType)` est **littéralement**
   `UnitsWithTrait(entities, 0x10 = UnitTrait.Hero, selectionType)` — un seul corps, rien d'autre.
   C'est lui qui écarte le summon `astraSmnGuardsman` (traits gameconfig `["Summon",
   "BattleFatigue"]`) de la branche B — et c'est précisément **pourquoi la branche A existe**.
3. **`IsRangedAttack`, polarité INVERSE du jumeau.** 1442 n'a aucun gate de nature ; 1449 porte
   `IsMeleeAttack & IsNormalAttack`. 1444 porte `IsRangedAttack` **seul** — pas d'`IsNormalAttack`.
   Et malgré l'i2 (« by mythic **characters** »), le trigger ne lit **aucun** trait `Hero` sur le
   caster : le `Hero` ne vit que dans le sélecteur, sur les voisins de la cible.

### Ce qui a été édité

- `engine/entities/effects/loki/extra_damage_aura.py` — classe `OnMyPositionExtraDamagePctEffect`
  (canal `create_aura_defense_damage_malus_for_ally`, `AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"`
  — même arbitrage que 1449 et `DaughterOfTheAbyss`, #437-r1-r1-r1) ; le nœud
  `VisualUnitIdFromUnitId(ConfigConstString(<config>, 0))` devient un **foyer unique**
  (`_ability_unit_id_visual_id`) partagé avec 1449 : c'est le MÊME arbre natif, un fork y ferait
  diverger deux mirrors du même nœud.
- `engine/entities/effects/factory.py` — `EFFECT_CLASSES["OnMyPosition_ExtraDamagePct"]` et
  `ABILITY_INIT_OWNER_EFFECTS["OnMyPosition"]`.
- `engine/runner/damage_model.py` + `engine/playbook/prediction/_shared.py` — le profil de voisinage
  `tgt_adjacent_unit_profiles` passe de `(uid, team, visual_id, rarity)` à
  **`(uid, team, visual_id, rarity, is_hero)`**, sur les DEUX faces. `is_hero` lit le même foyer de
  traits que `_friend_heroes_adjacent_to` (#1019). Les témoins qui MIMENT le producteur
  (`test_1035r2_1025r1_...`, `test_1025_electrochaff_...`) suivent le contrat.

### Confrontation LIVE — 4 bras, régime SÉPARANT

`probe_1024r2_on_my_position_bonus_live.py`, board `MC1_67`, seed 777, géométrie **pilotée**
(`--place`/`--a-place`). Attaquant `adeptRetributor` (`Range = 2`) placé à **distance 2** de la cible :
il n'est donc pas lui-même un voisin du sélecteur, et c'est ce qui rend les deux bras séparants
NON redondants.

| bras | aura posée | `targetIds` de 1444 | natif | port | témoin MÊLÉE |
|---|---|---|---|---|---|
| `off` (pas de `--equip-mythic`) | non | `[]` | 3012 – 4520 | 3012 – 4520 | 963 – 1446 |
| `on` | oui | `[85]` | **3312 – 4972** | **3312 – 4972** | 963 – 1446 |
| `caster` (attaquant `Rarity=3`) | oui | **`[85]`** | 3012 – 4520 | 3012 – 4520 | 963 – 1446 |
| `selecteur` (les 2 voisins `Rarity=3`) | oui | **`[]`** | 3012 – 4520 | 3012 – 4520 | 963 – 1446 |

- **accord `natif == port` : 4/4**, sur l'attaquant DISTANCE comme sur le témoin MÊLÉE ;
- `caster` et `selecteur` rendent le MÊME nombre mais pour des raisons OPPOSÉES, et `targetIds` les
  sépare **directement** : le trigger tombe pendant que le sélecteur tient, puis l'inverse ;
- le témoin MÊLÉE est invariant sur les quatre bras **alors que la cible porte l'effet dans `on`** :
  c'est `IsRangedAttack`, exercé.

⚠ **On ne fitte pas le scalaire.** Le rapport `on/off` vaut 1,0996 sur la borne basse et 1,1000 sur
la haute pour un `extraDmgPct = 10` — le natif accumule le % dans `attackModifiers`, consommé
AVANT perçage/armure avec un `Fix64.Round` par accumulateur. Le test compare la **décomposition par
étage** (`base`, `pierce`, `armor`, `hits` identiques, la pct-list différant de la SEULE entrée
`PercentIncrease(10)`).

### Validation adversariale du fix

**16 mutations, 16 rouges** (`logs/mut_1024r2*.py`, jetables) : `HeroUnits` retiré · rareté retirée ·
seuil `>= 2` recopié de 1449 · branche A retirée · `IsRangedAttack` retiré · `IsRangedAttack`
permissif sur `None` · `HasRarity(Caster)` retiré · exclusion `att_id == owner_id` ajoutée · face
native → `defender` · `Friends(Owner)` du sélecteur retiré · `is_hero` retiré du producteur COMBAT ·
idem PRÉDICTION · `Enemies(Owner)` retiré · branche A comparée au mauvais `visualId` · magnitude
figée · `GetAbilityState` ignoré.

⚠ **Deux mutations sont d'abord ressorties VERTES, et c'était le HARNAIS.** Leur ancre de texte est
**identique** dans les deux classes (`MoreGitzOverEreExtraDamagePctEffect` et
`OnMyPositionExtraDamagePctEffect`) : `str.replace(..., 1)` mutait le **voisin**, et le test de 1444
restait vert parce que 1444 n'avait pas bougé. Re-jouées en découpant le fichier à la classe visée,
elles rougissent toutes deux. Une mutation dont on ne vérifie pas qu'elle a MORDU se lit comme une
lacune de garde.

### Ce qui n'est PAS couvert

- **La branche A (`UnitsWithVisualId(astraSmnGuardsman)`) n'est pas confrontée LIVE** — elle l'est
  offline (`test_branche_A_le_guardsman_seul_suffit`, plus le `visualId` lu au gameconfig), mais
  aucun garde impérial n'est amené en bataille dans le montage. C'était déjà le résidu **`#1024-r4`**,
  et il reste ouvert tel quel.
- L'étage exact où le `+extraDmgPct %` entre dans le pipeline natif (rapporté, pas décomposé —
  `case-1024` §3 le disait déjà).
- Les paliers 2/3/4 de la mythique ne sont pas joués LIVE (seul le palier 1 l'est, via
  `--equip-mythic` sans niveau) ; les quatre le sont offline.

---

## 2. `BasiliskBarrage` (1026), face DÉCISION — RE complète, verrou LEVÉ, port À FAIRE (`#1026-r1`)

**Décider ≠ exécuter** : la face COMBAT de 1026 est portée et fidèle (`runner/abilities/
astramilitarum.py::BasiliskBarrageAbility`, tirage des obus confronté live sur 7 seeds). Ce qui
manque est l'**utilité de décision** — invisible en replay, puisque l'exécution est juste.

### Le playbook natif, lu en entier

`data/symbols/<build>/metadata/active_playbook_builders.tsv` apparie `1026` à
`IdunBattle.AI.Playbook.Loki.BasiliskBarragePlaybook` — **ce n'est donc PAS un
`DefaultActiveAbilityPlaybook`, il y a quelque chose de propre à porter**. Confirmé LIVE :
`pairUtility` rend `playbookClass = "BasiliskBarragePlaybook"`.

`...BasiliskBarragePlaybook$$.ctor` = `ComparablePlaybook<T>..ctor(this, 0x402 = 1026)` — c'est un
**Comparable**, pas un NonComparable : il n'y a ni `EvaluateNonComparable` ni `ShouldEvaluate` à
chercher. Les seuls corps propres sont `$$MakeDamagePredictions` et son helper
`$$GenerateAttackPredictionsForShells`.

```
BasiliskBarragePlaybook$$MakeDamagePredictions(caster, casterPosition, target, abilityState) :

    entities   = { owner/caster: caster, target: target }
    nMiss      = BasiliskBarrageAbility$$GetNumShellsMiss      .Evaluate(entities)
    nMaybe     = BasiliskBarrageAbility$$GetNumShellsMaybe     .Evaluate(entities)
    nGuar      = BasiliskBarrageAbility$$GetNumShellsGuaranteed.Evaluate(entities)
    tilesMiss  = BasiliskBarrageAbility$$GetPossibleTargetTilesMiss     # TilesAtDistance(Target, 2)
    tilesMaybe = BasiliskBarrageAbility$$GetPossibleTargetTilesMaybe    # TargetTiles + TilesAtDistance(Target, 1)

    list  = GenerateAttackPredictionsForShells(caster, casterPosition, target, abilityState, nMiss,  tilesMiss)
    list += GenerateAttackPredictionsForShells(caster, casterPosition, target, abilityState, nMaybe, tilesMaybe)
    list += GenerateAttackPredictionsForShells(caster, casterPosition, target, abilityState, nGuar,
                                              DSLSelectors$$Entity(target))
    return list
```

⚠ **Le troisième groupe n'utilise PAS `GetPossibleTargetTileGuaranteed`** (que la face COMBAT, elle,
appelle) : le playbook lui substitue `DSLSelectors$$Entity(target)`. Les deux valent
`TargetTiles@<DSLSelectors+0x78>` sur le chemin normal, mais c'est une différence ÉCRITE.

```
GenerateAttackPredictionsForShells(caster, casterPosition, target, abilityState, numShells, shellTargets) :

    if (int)numShells < 1: return []                     # <- les groupes vides ne coutent RIEN
    dmg     = <ability>$$GetDamageAmountMain(abilityState)          # corps DEDUPLIQUE etiquete
                                                                   # StranglethornCannonAbility$$GetDamageAmountMain
                                                                   # -> AActiveAbility$$MinMaxDamageAverage
    hits    = AActiveAbility$$GetHits                              # GetNumberConstant(0x2f = nrOfHits) = 2
    profile = <ability>$$GetDamageProfileType                      # corps DEDUPLIQUE etiquete
                                                                   # BaseFleshmetalGunsEffect$$GetDamageProfileType
    entities = { caster, target, targetTiles: EntityExtensions$$GetTiles(target, state) }
    tiles = shellTargets.Select(entities)
    for i in 0 .. tiles.Count - 1 :
        e     = tiles[i]
        ratio = Fix64(numShells) / Fix64(tiles.Count)               # <- LE POIDS
        list += ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions(
                    caster, casterPosition, e, DSLSelectors$$Entity(e),
                    dmg, hits, profile, Nullable<Fix64>(ratio), weightSelector: 0 )
    return list
```

Mapping des arguments de `GenerateMultiHitAttackPredictions`, **lu dans son corps** :
`(this, caster, casterPosition, target, targetsSelector, damageFormula, hits, damageProfile,
probability1, weightSelector)`. Le `Nullable<Fix64>` de rang 9 va **tel quel** dans
`ProbableDamageEvent+0xC8` = **`probability1`** ; `weightSelector = 0` ⇒ `probability2 = Fix64(1)`.
C'est exactement la sémantique déjà écrite dans `engine/playbook/probable_damage_event.py`.

Le playbook **ÉNUMÈRE** le pool et pondère par `numShells / |pool|` : **aucun tirage n'entre dans la
décision**, contrairement à la face COMBAT (trois `PickRandomly` avec remise). Les deux faces
partagent les mêmes nœuds de pool, déjà portés côté runner (`basilisk_num_shells`,
`basilisk_tiles_at_distance`).

La base de dégât est déjà classée : `ActiveAbilityType.BasiliskBarrage` est dans
`_A_VIA_GET_DAMAGE_AMOUNT_MAIN` (`entities/abilities/active_ability.py`) ⇒ `MinMaxDamageAverage`,
arrondi demi-vers-le-pair. Rien à re-lire de ce côté.

### Le verrou : `EntitySelector$$Select` ne résout PAS l'occupant — et la mesure tranche

`IdunBattle.Entities.Selectors.EntitySelector$$Select` rend l'entité **telle quelle** (elle appelle
`GetEntity`, jamais `GetUnit`). Or le pool d'obus est fait de **TUILES**. Le
`ProbableDamageEvent.Target` du natif est donc une entité-TUILE, et le décompilé seul ne dit pas si
l'occupant est résolu en aval (`PredictAttack` est un dispatch par objet-requête). **Un port écrit
sans cette réponse inventerait ou perdrait de l'utilité.**

**MESURE** (`probe_1026_face_decision_live.py`, board `MC1_67`, seed 777, géométrie pilotée) —
oracle `pairUtility(unitId, targetId, abilityType)` = `ComparablePlaybook$$
CalculateUtilityFromPredictions` sur une cible TUILE, c.-à-d. **le terme PRÉDICTION seul** (même
oracle que `probe_302_2` pour 1169). Caster `astraOrdnance` en (1,1), cible T1 `tyranTyrantGuard` en
(4,5), témoin `necroWarden` **déplacé** entre les deux bras, témoin de contrôle T3
`tyranNeurothrope` en (1,7) — dont aucune tuile d'anneau ne change.

| bras | témoin `necroWarden` | `u(T1)` tuile | `u(T1)` unité | `u(T3)` (contrôle) |
|---|---|---|---|---|
| `isole` | (0,3) — hors anneaux 1 et 2 | **4,161933** | 4,161933 | 20,868692 |
| `voisin` | (4,6) — anneau 1 de T1 | **20,194460** | 20,194460 | 20,868692 |

- **écart sur T1 : +16,032527** ; **témoin T3 : +0,000000 exactement** ⇒ le montage SÉPARE.
- ⇒ **le natif RÉSOUT l'occupant de chaque tuile d'obus et SOMME leurs contributions.** Le port doit
  mapper tuile → occupant, comme la face COMBAT.
- Corollaire mesuré : `u(<tuile>)` == `u(<unité qui l'occupe>)` à la dernière décimale dans les deux
  bras (`utilRaw` identique) — même propriété que 1169 (#302-2), donc la résolution matérialisée
  côté port serait value-identique.

⚠ **Ce montage-ci ne sépare rien** et il a d'abord été écrit ainsi : comparer `u(T1)` à `u(T3)` sur
un seul build fait varier **la cible** (armures, PV, traits différents — les plans d'attaque natifs
donnent déjà 1114–1670 contre 2302–6010). La seule variable admissible est la POSITION du témoin,
tout le reste identique.

### Ce qui reste OUVERT — `#1026-r1`

1. **La ROUTE.** 1169 (`PlagueburstMortar`) et 1148 (`DaemonicOrdnance`) sont sur la route
   NON-ATTAQUE parce qu'elles sont invisibles de `_best_attack`. **1026 ne l'est pas** : mesuré sur
   le montage ci-dessus, `decisionView.attackPlans` porte bien
   `[BasiliskBarrage] vs u79 / u81 / u83` avec des bornes par cible. Inscrire 1026 dans
   `register_nonattack` sans trancher ce point **doublerait** sa contribution. À établir avant tout
   port.
2. **Le substrat des pools côté DÉCISION.** `basilisk_tiles_at_distance` / `basilisk_num_shells`
   prennent un `State` de runner ; la face DÉCISION travaille sur un `AiDecisionContext` /
   `Scene`. C'est le même nœud natif — il faut un foyer partagé, pas un fork (le vice que #197 et
   #950-r2 ont payé).
3. **La confrontation par tuile.** L'oracle existe et répond (`pairUtility` par tuile éligible,
   comme `probe_302_2::per_tile`) : la confrontation doit porter sur CHAQUE tuile candidate, pas sur
   un scalaire agrégé.

Rien de tout cela n'est bloqué par un capteur : porteur au pool (`astraOrdnance` est dans
`--list-pool`), oracle disponible, RE écrite.
