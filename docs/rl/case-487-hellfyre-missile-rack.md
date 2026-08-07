# #487 -- `1088 HellfyreMissileRack` : l'attaque qui RE-TIRE sur ce que le PSYCHIC a deja marque

**Verdict : RESOLU.** Le no-op silencieux est ferme, les deux faces sont confrontees live, per-coup
bit-exact sur TROIS regimes.

## 1. Identite

- `ActiveAbilityType.HellfyreMissileRack` = `1088`.
- Porteur **lineup** : `thousTerminator` (heros **Toth**), pool rank 17. 5 porteurs npc
  (`thousBossTerminator`, `...Camp`, `...LHE`, `...Surv`, `thousNpcTerminator`).
- Kit gameconfig 1088 : `attackRangeType = Ranged`, `damageProfile = HeavyRound`, `range = 3`,
  `nrOfHits = 1`, `minDmg`/`maxDmg`[level] (dans `variablesAffectedByRarityBonus`). Aucune variable
  `_2` -> les deux volets partagent plage, profil et nombre de coups.
- i2 : « Deals 1x [dmg] Heavy Round Damage to a target enemy unit within range 3 **and an additional
  1x [dmg] Heavy Round Damage to each enemy unit on the map that was dealt Psychic Damage this
  turn, which can include the initial target again**. »

Artefacts natifs :

- `IdunBattleLogic.Entities.Abilities.Active.Loki.HellfyreMissileRackAbility$$.ctor`
- `...HellfyreMissileRackAbility$$ExecuteBehaviour`
- `...HellfyreMissileRackAbility$$GetAffectedUnits`
- `IdunBattle.AI.Playbook.Loki.HellfyreMissileRackPlaybook$$EvaluateNonComparable`

## 2. `.ctor` -- forme PRESET STATIQUE, masque `0x4002`

Le ctor n'appelle **aucun** `IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie **0x40
octets** depuis `<TargetingOptions statics>+0x140 .. +0x178` et les passe tels quels a
`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(this, &opts, 0)`. C'est la **2e forme de piege**
du CLAUDE.md : le masque effectif est la constante ecrite par
`IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28`, c.-a-d. son
`*(lVar4 + 0x168) = 0x4002`.

    0x4002 = TargetingRule.TargetIsEnemy (0x4000) | TargetingRule.TargetMatchesDynamicRule (0x2)

⚠ **MEME masque que 1027 `PsychicMaelstrom` / 1069 `SeekerMissileFrequencyLock`, preset DIFFERENT** :
`forceMeleeTarget = *(preset+0x20)` vaut **0** ici (`<preset>+0x160 = 0`) = `RangedBool.True`
(l'enum natif est INVERSE : True=0, False=1), contre `1` chez eux. Le champ change le regime de
portee -- generaliser depuis une ability voisine aurait ecrit un masque faux.
Portee : le preset copie son `TargetingRange` depuis `<TargetingRange statics>+0x18` =
`RANGE_FROM_CONFIG` -> `SetConfigValuesInTargetingOptions` y pose `overrideRange = 3`.

**3e argument d'`AActiveAbility$$.ctor` = `0` = `AbilityAttackType.DirectTargetAttack`** (le champ
`+0x68`, cf. `abilities/attack_type.py`). Litteral LU, pas deduit de la forme du ciblage.

## 3. `ExecuteBehaviour` -- ATTAQUE, arbre `DSLFactory` pur

Aucun etage imperatif (contraste `DoomboltAbility$$ExecuteBehaviour`, qui materialise et repartit) :

    dmg     = AActiveAbility.MinMaxDamage(this, abilityState)
    profile = DSLSelectors.Direct( AbilityConfiguration.GetDamageProfile(cfg) )        # HeavyRound
    hits    = DSLFormulas.Get( AbilityConfiguration.GetNumberConstant(cfg, 0x2f) )     # nrOfHits
    atk1    = DSLBehaviors.AbilityDamage(Caster@+0x48, ActiveTarget@+0x68, dmg, profile, hits,
                                         <AbilityOrEffect 1088>, isOutsideAttack=false,
                                         selectionType=2)
    atk2    = DSLBehaviors.AbilityDamage( <MEMES arguments> )                          # 2e instance
    extra   = DSLSelectors.FromTrigger(
                  DSLSelectors.NonSteppableOrObjectUnits(
                      DSLSelectors.Enemies(Caster@+0x48, AllUnits@+0x20, 3), 3),
                  DSLTriggers.HasTakenDamageOfDamageProfileThisTurn(ActiveTarget@+0x68, 0xd),
                  requireContinuous = 0)
    AActiveAbility.Execute(entities, this,
        DSLBehaviors.SortedAttackSeries(Caster@+0x48, Target@+0x60, atk1, extra, atk2,
                                        <AbilityOrEffect 1088>))

`$$GetAffectedUnits` re-construit **exactement** `extra` -- le 2e volet est bien ce sous-arbre.

Slots du `DSLSelectors` (mapping etabli en CONFRONTANT le decompile de `FragBombAbility$$
ExecuteBehaviour` a son port deja valide, jamais par le nom d'un ctor gshared) : `+0x20` `AllUnits`,
`+0x48` `Caster`, `+0x60` `Target`, `+0x68` `ActiveTarget`.

Trois points de fidelite :

1. **`AActiveAbility$$Execute`, PAS `$$ExecuteAtomic`** -> aucun `AtomicGroup` (FragBomb, lui, finit
   par `ExecuteAtomic(..., 0x43)`).
2. **`Target@+0x60` NU** pour le 1er selecteur : le natif ne l'enveloppe PAS dans `Units(...)`
   (contraste FragBomb, qui passe `Units(Target@+0x60, 1, 1)`).
3. **Famille ABILITY** : `DSLBehaviors$$AbilityDamage` -> `AbilityDamageBehaviour` ->
   `AbilityDamageOperation$$ExecuteHits` (1 tirage/coup, pas de crit/block), d'ou
   `native_factory="ability"`. FragBomb a la MEME forme `SortedAttackSeries` mais route
   `DSLBehaviors$$AttackDamage` (famille ATTACK). Classification par la CALLEE, jamais au juge.

`SortedAttackSeries$$GetAttacks` resout les DEUX selecteurs **d'abord**, puis rejoue par cible dans
l'ordre d'insertion : une unite presente dans les deux recoit les deux attaques consecutivement --
le « can include the initial target again » de l'i2. Le coup du volet 1 etant `HeavyRound`, il ne
rend jamais sa propre cible eligible au volet 2 (et de toute facon le selecteur est deja resolu).

## 4. Qualification des ordinaux -- le piege central de cette ability

| ordinal | ou | enum | membre |
|---|---|---|---|
| `0x2f` | `GetNumberConstant` | `AbilityConstantType` | `nrOfHits` |
| `0x1b` | `NonSteppableOrObjectUnits` | `UnitTrait` | `Steppable` |
| `0xd` | `NonSteppableOrObjectUnits` | `UnitTrait` | `Object` |
| `0xd` | `HasTakenDamageOfDamageProfileThisTurn` | `DamageProfileType` | **`Psychic`** |
| (config) | `GetDamageProfile` | `DamageProfileType` | **`HeavyRound`** |

⚠ **`0xd` designe DEUX enums differents dans la MEME expression**, et le profil INFLIGE
(`HeavyRound`) n'est pas le profil TESTE (`Psychic`). L'ordinal nu aurait confondu les deux **sans
lever la moindre erreur** -- c'est exactement le regime que la regle « un entier qui DESIGNE passe
par son membre » vise.

## 5. Ce qui a ete porte

| fichier | ajout |
|---|---|
| `engine/runner/abilities/thousandsons.py` | `HellfyreMissileRackAbility`, `hellfyre_missile_rack_tree`, `hellfyre_extra_targets_selector` |
| `engine/runner/abilities/handler.py` | entree `ABILITY_CLASSES[1088]` |
| `engine/runner/abilities/attack_type.py` | entree `ABILITY_ATTACK_TYPE[1088] = DirectTargetAttack` |
| `engine/runner/abilities/targeting.py` | entree 1088 **RETIREE** de `TARGETING_OPTIONS_UNPORTED` (migration vers la classe -- contrat de disjonction, comme 1100 `SorcerousFacade`) |
| `engine/entities/triggers.py` | noeud `HasTakenDamageOfDamageProfileThisTurn` (mirror de `HasTakenDamageOfDamageProfileThisTurnTrigger$$ShouldTrigger`) |
| `engine/entities/selectors/units.py` | `non_steppable_or_object_units` (mirror de la FACTORY de composition) |
| `engine/dsl/base.py` | champ `DslContext.has_taken_damage_of_profile_this_turn` |
| `engine/runner/abilities/behaviours/context.py` | l'accesseur, branche sur `UnitComponent.received_damage_this_turn` |

Le noeud `SortedAttackSeries` (`abilities/behaviours/combat.py`) et le dict
`received_damage_this_turn` (`runner/components.py`, alimente par `operations/damage.py`) existaient
deja -- rien de duplique.

**PRESENCE / ABSENCE, distinguees** : le trigger porte ici est
`HasTakenDamageOfDamageProfileThisTurnTrigger$$ShouldTrigger` = `ContainsKey(receivedDamageThisTurn,
profile)`. C'est **une presence de cle**, pas un compte -- a ne pas confondre avec
`...AmountOfTimesTrigger$$ShouldTrigger`, deja porte pour `RealityUnbound`, qui exige `== times`
(EGALITE STRICTE). Le mauvais choix change le resultat des le 2e coup Psychic sur la meme cible.

## 6. Validation live -- `probe_487_hellfyre_missile_rack.py`, 3 regimes

Montage : Toth + Ahriman contre 4 orks, positions posees par `--place`/`--a-place`. L'armement
Psychic vient de `Doombolt` (1102, deja porte).

⚠ **Pourquoi le rejeu offline part d'AVANT l'armement** : `receivedDamageThisTurn`
(`ActorStatisticsComponent+0x80`) n'est expose par AUCUN canal de seed -- ni `decisionView`, ni
`combatSnapshot`, ni le hook `actorStats`. Un rejeu partant d'APRES verrait un dict VIDE et rendrait
un volet 2 vide *pour une raison qui n'est pas Hellfyre*. On capture donc l'etat avant le Doombolt et
on rejoue les DEUX casts.

⚠ **Pourquoi EXACTEMENT 3 ennemis a portee du Doombolt** : `Doombolt` repartit `nrOfHits = 3`
« evenly », donc `3 % 3 == 0` -> 1 coup chacun, et l'ensemble arme ne depend pas de l'ordre de
`SortUnitsByDamageUtility`. **Le 1er montage en mettait QUATRE** : la 4e cible ne recevait rien, et
live/port ne choisissaient pas la meme (live laissait `orksBigMek`, le port `orksRuntherd`). C'etait
un **ecart de TRI de Doombolt**, pas de Hellfyre -- voir le residu §8.

| regime | live | offline | verdict |
|---|---|---|---|
| **arme, cible armee** | `{81:2, 83:1, 85:1}` per-coup `[2792, 2792, 3989, 2792]` | identique | la cible prend `2 x nrOfHits` |
| **arme, cible = temoin** | `{87:1, 81:1, 83:1, 85:1}` per-coup `[5984, 2792, 3989, 2792]`, ordre `[87, 81, 83, 85]` | identique | la cible NON armee prend `nrOfHits` **seul** |
| **non arme** | `{81:1}` per-coup `[1463]` | identique | volet 2 **VIDE** |

Ce que chaque regime elimine :

- **temoin negatif** (`orksRuntherd` hors portee du Doombolt) jamais frappe -> le predicat mord
  vraiment ; un volet 2 degenere en « tous les ennemis » passerait tous les autres etages ;
- **cible = temoin** -> le doublement vient du PREDICAT, pas d'un forfait « la cible compte deux
  fois » ;
- **non arme** -> le volet 2 n'est pas un forfait.

⚠ **`--seed` NE FAIT PAS varier le MT du runner** (mesure : `777` et `31337` rendent le MEME per-coup
`[2792, 2792, 3989, 2792]`). Une « generalisation par seed » ne prouve donc rien sur la consommation
de RNG. Ce qui l'exerce ici, c'est l'ETAT du MT au cast : les trois regimes rendent **trois** valeurs
distinctes sur la meme cible (`2792` / `5984` / `1463`), toutes bit-exactes des deux cotes.

Garde commite : `tests/engine/runner/test_487_hellfyre_missile_rack_live.py` (4 tests) + fixture
`hellfyre_case` (`tests/engine/runner/conftest.py`).

## 7. Face DECISION -- lue, NON portee (residu nomme)

`IdunBattle.AI.Playbook.Loki.HellfyreMissileRackPlaybook$$EvaluateNonComparable` (RE complete) :

    bucket  = new Bucket(0, null)
    utility = Fix64( Sum( Select( <unites du proprietaire adverse>,
                                  u => UnitExtensions.HasTakenDamageOfDamageProfileThisTurn(u, 0xd)
                                       ? 1 : 0 ) ) )                       # <>c.<...>b__2_0
    foreach (t in BasePlaybook.GetEligibleTargetsSelectable(this, caster, casterMainTile))
        bucket.AddAction( BasePlaybook.GenerateAction(this, casterPosition, t, utility) )

soit **une utilite CONSTANTE = le nombre d'ennemis ayant pris du Psychic ce tour**, identique pour
toutes les cibles eligibles. `$$.ctor` -> `ComparablePlaybook<...>..ctor(this, 0x440 = 1088)`.

Ce playbook **n'est pas porte** (aucune entree 1088 dans `engine/playbook/`). Consequence : la face
DECISION ne sait pas encore *quand* preferer ce cast. Ce n'est pas un no-op de COMBAT (celui-la est
ferme), mais un residu de SCORING. Il est petit et entierement lu -- candidat direct pour une tranche
suivante.

## 8. Residu OUVERT trouve en chemin (hors #487) -- **#494**

**`DoomboltAbility` : la cible ECARTEE differe entre le natif et le port quand `nrOfHits % C != 0`.**
Mesure du 2026-08-07, geometrie `Ahriman@(3,3)` + 4 ennemis tous a `d <= 2`
(`orksNob@(3,4)`, `orksWarboss@(4,4)`, `orksBigMek@(2,4)`, `orksRuntherd@(3,5)`), board `MC1_67`,
seed 777 :

    LIVE Doombolt : {81: 1, 83: 1, 87: 1}      # orksBigMek (85) ecarte
    PORT Doombolt : {81: 1, 83: 1, 85: 1}      # orksRuntherd (87) ecarte

Les DEUX cotes frappent bien 3 cibles sur 4 (`N = 3`, `C = 4` -> `r = 3`, les 3 premieres prennent
1 coup, la 4e 0) : la repartition est juste, c'est l'**ORDRE** de
`SortUnitsByDamageUtilitySelector$$Select` qui diverge -- donc *qui* est la 4e. Reproductible par
`probe_487_hellfyre_missile_rack.py` en replacant `orksRuntherd` a `3,5`.
`test_doombolt_live.py` reste VERT : son montage ne produit pas de reste non nul.
Non investigue ici (hors perimetre) ; **un numero de residu reste a demander**.
