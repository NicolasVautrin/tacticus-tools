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

## 7. Face DECISION -- PORTEE (#487-r1), apres DEUX corrections de cette fiche

`IdunBattle.AI.Playbook.Loki.HellfyreMissileRackPlaybook$$EvaluateNonComparable`, relu :

    bucket  = new Bucket(0, Nullable<Fix64>( <1er champ statique de la classe> ))   # = Fix64(1)
    ownerId = EntityExtensions.GetCurrentOwnerEntityId(caster)
    utility = Fix64( Sum( Select( battleQuery.<slot itf 0x8e = GetAllEnemiesOf>(ownerId),
                                  u => UnitExtensions.HasTakenDamageOfDamageProfileThisTurn(u, 0xd)
                                       ? 1 : 0 ) ) )                       # <>c.<...>b__2_0
    foreach (t in BasePlaybook.GetEligibleTargetsSelectable(this, caster, casterMainTile))
        bucket.AddAction( BasePlaybook.GenerateAction(this, casterPosition, t, utility) )

soit **une utilite CONSTANTE = le nombre d'ennemis ayant pris du Psychic ce tour**, identique pour
toutes les cibles eligibles. Elle est calculee **avant** la boucle : ni la cible ni la position ne la
font varier -> `AddAction` ne remplace que sur `>` STRICT, donc a utilite plate la PREMIERE paire
(position, cible) gagne, c.-a-d. l'ORIGINE et sa premiere cible `fromHere`.

**Les deux lectures que la version precedente de cette section portait FAUSSES**, et qu'il a fallu
corriger pour que le port soit juste :

1. **`Bucket(0, null)` etait faux : c'est `Bucket(0, Fix64(1))`, donc `MIN_UTILITY = 1`.** Le
   `.cctor` de la classe ecrit `Fix64(1)` dans son premier champ statique, et la leaf relit CE champ
   pour construire le `Nullable<Fix64>`. Le gate MORD : tant qu'aucun ennemi n'a pris de Psychic ce
   tour, l'utilite vaut `0 < 1` et le bucket reste **VIDE** -- l'ability n'est pas proposee. C'est le
   comportement le plus discriminant du playbook ; le porter a `0` l'aurait rendu inoffensif, et
   VERT sur tout test qui ne regarde que l'utilite.
2. **`$$.ctor -> ComparablePlaybook<...>..ctor` etait un MISLABEL de corps gshared FONDU.** La table
   de classes du build (`data/symbols/<build>/frida/classes.tsv`) donne le parent reel :
   **`IdunBattle.AI.Playbook.NonComparablePlaybook`1`**. Temoin de controle dans la MEME table :
   `ChronometronPlaybook` y est bien `ComparablePlaybook`1` -- et, coherent avec ca, elle n'a AUCUN
   `EvaluateNonComparable`, elle override `CalculateCustomUtility`/`ShouldExecute`. La distinction
   decide de la ROUTE : `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists` range les
   NonComparable dans `dict[get_Priority]`, evalues AVANT le fallback Comparable -- un port loge du
   mauvais cote aurait fait perdre (ou gagner) l'ability contre toute attaque, sans erreur.
   C'est exactement le piege que `CLAUDE.md` nomme : **lire la STRUCTURE d'un ctor gshared, jamais
   son NOM**.

`get_Priority` : 1088 est ABSENTE de `NATIVE_PRIORITY` (sweep exhaustif #170) -> tier **0** =
`AbilityPriority.Normal`. Aucun override de `ShouldEvaluate` -> base `True`.

### Ce qui a ete porte (#487-r1)

| fichier | ajout |
|---|---|
| `engine/playbook/noncomparable/hellfyre_missile_rack.py` | `HellfyreMissileRackPlaybook` (utilite, gate, cible `fromHere`) |
| `engine/playbook/noncomparable/__init__.py` | entree `PLAYBOOKS[1088]` + facade |
| `engine/playbook/scene.py` | canal `received_damage_profiles_by_id` (`from_state`) + accesseur `has_taken_damage_of_profile_this_turn` |

Le registre `ABILITY_CLASSES` / `TARGETING_OPTIONS` / `ABILITY_ATTACK_TYPE` n'est PAS touche :
l'ability y est entree avec la face COMBAT (#487), et une face DECISION n'y ajoute rien.

### Le canal, et pourquoi il est TRI-ETAT

`receivedDamageThisTurn` (`ActorStatisticsComponent + 0x80`) n'est publie par **AUCUN** canal de
seed -- ni `decisionView`, ni `combatSnapshot`, ni le hook `actorStats` (qui ne porte que `+0x20`).
C'est la MEME absence que celle deja nommee au §6 pour le rejeu COMBAT.

- **Rejeu OFFLINE** : le runner TIENT le compteur (`UnitComponent.received_damage_this_turn`,
  alimente par `runner/operations/damage.py`, vide au boundary par `turnflow`), et
  `Scene.from_state` le transporte -> c'est le regime dans lequel ce playbook est confrontable.
- **LIVE** : `Scene.has_taken_damage_of_profile_this_turn` rend `None` = **NON MESURE**, et le
  playbook rend alors AUCUN candidat **en le disant**. Un `0` servi a la place serait une
  AFFIRMATION (« personne n'a pris de Psychic ») et prononcerait un refus que le natif n'a pas
  prononce -- degradation RESTRICTIVE silencieuse. Les deux sorties se ressemblent (liste vide) et
  n'ont pas la meme cause : `test_487r1_hellfyre_playbook_offline.py` etage 5 les separe.

Garde commite : `tests/engine/test_487r1_hellfyre_playbook_offline.py` (10 tests, 100 % offline).
Contre-epreuves jouees -- chacune ROUGE avant le vert : `MIN_UTILITY = 0.0` (2 rouges),
compter les ALLIES au lieu de `GetAllEnemiesOf` (1), `TESTED_PROFILE = HeavyRound` (5).

### Residu ouvert : **#487-r2** -- la face DECISION n'est pas CONFRONTEE au natif

Le port est valide par ses invariants (10 tests offline, 3 mutations mordues), **pas** contre
l'oracle natif. Deux raisons cumulees, et la seconde est la vraie :

1. `ncPlaybookPredict` s'ancre sur `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor` : ce playbook
   ne construit **aucune** prediction (son utilite est un comptage), donc cet oracle-la ne dirait
   rien de lui. Confronter exige d'observer l'ACTION que l'IA EMET (tour IA observe), pas une
   capture de predictions.
2. Le montage discriminant est le gate `MIN_UTILITY = 1` : « non arme -> le natif ne propose PAS
   1088 » contre « arme -> il la propose ». Il faut donc le montage de `probe_487` (Toth + Ahriman
   contre 4 orks, armement par `Doombolt`) **plus** un tour IA joue sur Toth. Non joue dans cette
   tranche.

Ce n'est PAS un blocage de capteur pour le port offline (le rejeu voit le compteur), mais c'en est
un pour toute confrontation LIVE de cette face : le point d'ancrage a hooker est
`ActorStatisticsComponent + 0x80` cote `frida/hooks/features/ai-step/rpc-snapshot.ts` -- **la meme
fenetre de reinject que le residu `#545-r1`**, qui vise `+0x24` du meme composant.

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
`test_doombolt_live.py` reste VERT : son montage produit BIEN un reste non nul (`N = 3` sur 4
cibles) mais sur la SEULE geometrie ou les deux cotes tombent d'accord.

⚠ **INSTRUIT DEPUIS** (#494, `case-494-doombolt-ordre-des-cibles.md`) : l'ecart tient a DEUX causes
que ce montage MELANGE. `orksBigMek` porte le trait `Mechanic` et pose un `statDelta
{fixedArmor: +1197}` sur ses voisins -- le DEPLACER change l'armure des autres, donc ce roster ne
peut pas servir d'A/B de position. Sur un roster de N `orksNob` IDENTIQUES, l'ecart residuel est un
TIE-BREAK : `sorted(by id)` cote port contre l'enumeration de tuiles `cube-lex (x,y)` rotee d'un
cran cote natif. Residu **`#494-r1`** ; rejouer `probe_494_doombolt_sort_order.py`.

## 9. `#487-r2` : la face DECISION est CONFRONTEE -- et le foyer declare etait incomplet

Probe neuf : `probe_487r2_hellfyre_decision_live.py`. Deux regimes, deux oracles natifs, un temoin
negatif, et un releve du canal BRUT qui NOMME le maillon quand le port s'abstient.

### Le natif, mesure

| regime | `ncPlaybookPredict(via="evaluate")` | `aiDryRunAllUnits` |
|---|---|---|
| aucun Psychic ce tour | bucket **VIDE**, `actions = 0` | `ability = 69` (attaque normale) |
| apres `1102 Doombolt` d'Ahriman | bucket **`util = 3`**, `actions = 1` | **`ability = 1088`** |

Le gate `MIN_UTILITY = 1` MORD donc, l'utilite EST un comptage, et le 4e ork -- hors portee du
Doombolt, vivant et a portee de Hellfyre -- en est **exclu** (3 sur 4). Les deux oracles sont lus
parce qu'ils ne voient pas la meme chose : `Evaluate/3` ne traverse pas `ShouldEvaluate`, le
generateur si. Un `ok: false` LEVE dans les deux cas -- un capteur muet se lirait sinon comme le
refus meme qu'on cherche a mesurer.

### Le port, premier jet : `util = None`, zero candidat AUX DEUX BRAS

Accord APPARENT a vide, desaccord arme. C'est la degradation RESTRICTIVE que la docstring du
playbook annoncait : sans canal, on s'abstient et on le DIT.

### Le maillon defaillant n'etait NI le capteur NI le seeder

Le canal brut, lu sans passer par le port :

    actorStats.units[] -> 81: {profiles: {"13": 1}}   83: {profiles: {"13": 1}}
                          85: {profiles: {"13": 1}}   87: {profiles: {}}
    receiveDamageLayout -> channelResolved: true, fieldOffset: 128 (= 0x80),
                           errors: [], drift: []

Le capteur (#10008) rend **exactement** l'etat natif, et concorde au bit pres avec `util = 3`. La
cause est ailleurs : **la face DECISION LIVE ne passe pas par `snapshot.load_state`**. Elle batit sa
`Scene` par `scene.build_predictor` + `Scene.from_predictor_sctx`, qui tiraient **deja** cet appel
`actorStats` pour `totalAttacksMade` -- sans lire ce champ-la.

⚠ Le **FOYER** que le residu declarait (`receive-damage-types.ts`, `rpc-snapshot.ts`,
`runner/snapshot.py`) etait donc incomplet : ces trois-la servent la voie COMBAT. La voie DECISION
LIVE vit dans `engine/playbook/scene.py`.

### Le cablage, et le piege du voisinage

Deux hunks additifs, **aucun RPC de plus** : `_received_damage_profiles_from_actor_stats` +
le passage dans `from_predictor_sctx`. Le tri-etat y est **inverse de celui des voisins**, et c'est
tout le piege : la quinzaine de champs adjacents s'ecrivent `predictor.get(<nom>) or {}`, parce que
pour eux un dict vide est la bonne valeur neutre (l'accesseur rend `None` par absence de CLE). Ici
le tri-etat est porte par la **TABLE ENTIERE** -- un `or {}` affirmerait « personne n'a pris de
degat ce tour » et ferait **REFUSER** l'ability (`0 < MIN_UTILITY = 1`), degradation restrictive et
silencieuse. Le defaut est donc `None`, explicitement.

### Apres cablage

| regime | natif | port |
|---|---|---|
| non arme | bucket vide | `util = 0.0`, 0 candidat |
| arme | `util = 3`, propose 1088 | `util = 3.0`, 1 candidat, **meme cible** |

Generalise : board `C1_74` + seed `31337` -> accord identique, et la cible CHANGE (85 au lieu de
87), donc le montage n'est pas degenere.

### Cliquets

`tests/engine/runner/test_10008_487r2_419_canaux_offline.py`, trois etages neufs :
`a4bis` (le helper, aux quatre formes de non-mesure + le mixte), `a4ter` (l'accesseur `Scene`, ou
`None` et `False` se separent), et `a4quater` -- qui lit le **CODE SOURCE** du site et rougit sur un
`or {}`, la faute la plus probable puisque tous les voisins l'ecrivent. Ce dernier porte sa propre
contre-epreuve (le motif `or {}` doit exister chez les voisins, sinon l'assertion serait vraie pour
une raison sans rapport) et sa morsure a ete **jouee** : mutation appliquee -> rouge, mutation
retiree -> vert.
