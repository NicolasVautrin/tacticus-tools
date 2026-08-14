# #1083-r3 (tranche 2) — les `PowerUp_*` NON-BOOST : six mecaniques, six artefacts distincts

**Verdict en une ligne** : les six ne sont pas des variantes d'un patron — ils se separent en **deux
familles structurelles** que le decompile tranche sans ambiguite, et **trois d'entre eux ecrivent
dans un composant que nos batailles ne portent pas**.

> ⚠ **TOUTE la RE de cette fiche a ete faite contre le build `rnca9r7q6c`**, avant la mise a jour du
> jeu du 2026-08-14. Les **symboles** et les **structures** survivent a ~97,5 % d'un build a l'autre,
> mais **les ordinaux d'enum sont regeneres a chaque build** et une confusion d'ordinal est
> SILENCIEUSE. Tout appariement par ordinal cite ici (`0x12`, `0x13`, `0x16`, `0x50`, `0xc`, `0xd`,
> `3`, `0`/`4`) est donc **A RE-CONFIRMER** contre `data/symbols/<nouveau-hash>/frida/enums.tsv`
> avant d'etre traite comme un fait. Les ports ecrits par cette tranche passent tous par un membre
> d'enum NOMME, jamais par l'ordinal — c'est precisement ce qui rend la re-verification mecanique.

## 1. La partition, LUE et non supposee

Balayage **exhaustif** de `data/symbols/rnca9r7q6c/ghidra/functions.tsv` sur les quatre vslots de
`APowerUpAbility` (un override qui rend un record ou un behaviour a un corps NON trivial, donc un
proprietaire dans la table) :

| vslot | proprietaires |
|---|---|
| `get_PctBasedStatBoost` (`+0x378`) | `PowerUp_Damage`, `PowerUp_Health` — **et personne d'autre** |
| `get_AbsoluteStatBoost` (`+0x388`) | `PowerUp_Hits`, `PowerUp_MeleeHits` — **et personne d'autre** |
| `SelfContainedBoostEffect` (`+0x368`) | **0** (confirme la tranche 1) |
| `AdditionalBehavior` (`+0x398`) | `PowerUp_Armor`, `PowerUp_Bomb`, `PowerUp_Healing`, `PowerUp_ReactivateAbility` |
| `CreateTrigger` | **0 chez les 22** — tous heritent le trigger de base |

D'ou la partition des six de cette tranche :

| mecanique | forme | consequence |
|---|---|---|
| `PowerUp_ReactivateAbility` 1272 | `AdditionalBehavior` | herite la base -> **bouclier + son volet** |
| `PowerUp_Healing` 1273 | `AdditionalBehavior` | herite la base -> **bouclier + son volet** |
| `PowerUp_Bomb` 1282 | `AdditionalBehavior` | herite la base, **mais SANS bouclier** (cf. §3) |
| `PowerUp_Reinforcement` 1266 | `CreateBehaviour` **entier** | **aucun bouclier, aucun boost** |
| `PowerUp_ReinforcementShield` 1269 | `CreateBehaviour` **entier** | idem |
| `PowerUp_Resurrect` 1320 | `CreateBehaviour` **entier** | idem |

⚠ **Le trigger de base n'est PAS a re-porter** : `APowerUpAbility$$CreateTrigger` est deja porte par
la tranche 1 (`runner/operations/triggers/loki/power_up.py::APowerUpAbility.matches`), et le
balayage ci-dessus etablit que **les 22 s'en servent tels quels**. Les six heritent donc le meme
vecteur `On(PreUnitDeath)` + `DamageReason.Steppable` + `NOT HasTrait(Actor, Steppable)`.

## 2. Les six corps natifs, noeud par noeud

`DSLFactory+0x78` = DSLBehaviors, `+0x80` = DSLFormulas, `+0x88` = DSLTriggers, `+0x90` =
DSLSelectors ; `DSLSelectors+0x30` = `Owner`, `+0x40` = `Actor` (mapping mesure par la tranche 1).

### `PowerUp_ReactivateAbilityAbility$$AdditionalBehavior`

    return ResetActiveAbility(target, allowUseless = true);

`target` est l'`Actor` que `APowerUpAbility$$CreateBehaviour` passe a tous ses volets.

### `PowerUp_HealingAbility$$AdditionalBehavior`

    healOpts   = new HealBehaviourOptions   { <+0x33> = 1, <+0x34> = 1 }
    amountHeal = PercentageOf( StatAmount(target, 5 = Health, 2 = Maximum, null, 0),
                               Get(GetNumberConstant(config, 0x13 = HealPercentage)), 0 )
    heal       = Heal(Owner@sel+0x30, target, amountHeal, healOpts)

    repairOpts = new RepairBehaviourOptions { <+0x16> = 1, <+0x10> = 0, <+0x14> = 1 }
    amountRep  = <la MEME expression, re-construite a l'identique>
    repair     = Repair(Owner@sel+0x30, target, amountRep, AbilityOrEffect(this), repairOpts)

    return If( IsMechanical(target, 0), repair, heal )

⚠ Le stat lu est `Health / **Maximum**` (`StatPart` 2), **pas** `Initial` (3) — la meme distinction
que celle deja nommee pour `PowerUp_ArmorEffect` par la tranche 1. Le bouclier commun, lui, lit
bien `Initial`. Les deux parts coexistent donc dans le MEME arbre pour `PowerUp_Healing`.

### `PowerUp_BombAbility$$AdditionalBehavior`

    origOwner = OriginalOwner(Actor@sel+0x40)
    radius    = ConfigConst(0x16 = range, config)
    cibles    = SurroundingEnemies(Actor@sel+0x40, radius, unique = true, UnitSelectionType = 3)
    montant   = RandomAmount( GetMinDamage(origOwner), GetMaxDamage(origOwner) )
    profil    = Direct( Nullable( GetDamageProfileOrDefault(0x12) ) )
    degat     = AbilityAreaDamage(Owner@sel+0x30, cibles, montant, profil, AbilityOrEffect(this))
    return If( IsHumanPlayer(origOwner), Inform(0x95, radius) & degat, null )

avec, tous deux passant par le niveau d'ability derive de la RARETE du joueur :

    GetMinDamage(player) = ConfigVar(0xc = minDmg,
                              AbilityStateFromLevel(AbilityLevelFromPlayerCurrentRarity(player)),
                              config)
    GetMaxDamage(player) = ConfigVar(0xd = maxDmg, <idem>, config)

⚠ **`IsHumanPlayer` est LOAD-BEARING, et il n'est pas un simple booleen** :

    IsHumanPlayer(p) = <PlayerTypeTrigger>(p, 0) | <PlayerTypeTrigger>(p, 4)

soit une DISJONCTION sur deux valeurs d'un enum de type de joueur. Sans lui, la bombe exploserait
aussi pour une equipe pilotee par l'IA — ce que le natif REFUSE (`If(..., ..., null)`).

### `PowerUp_ReinforcementAbility$$CreateBehaviour`

    return AddReinforcementPoint(Actor@sel+0x40);

### `PowerUp_ReinforcementShieldAbility$$CreateBehaviour`

    return Do( e => {
        player = StateExtensions.GetCurrentPlayer(<state>)
        pct    = GetNumberConstant(config, 0x50 = shieldPct)
        <processor>.AddReinforcementShield(player, pct)
    } );

⚠ La cible est le **joueur COURANT**, pas l'`Actor` — c'est le seul des six a passer par
`GetCurrentPlayer` plutot que par un selecteur, et c'est aussi le seul a utiliser `Do` (lambda
imperative), donc a n'avoir **aucune structure DSL** a mirrorer.

### `PowerUp_ResurrectAbility$$CreateBehaviour`

    morts   = Friends( Actor@sel+0x40, HeroUnits(AllDeadUnits(), 0), 0 )
    return If( NOT AmountIsZero(morts),
               AddResurrectDraftPoint(Actor@sel+0x40),
               AddReinforcementPoint(Actor@sel+0x40) );

C'est-a-dire : *s'il existe au moins un HEROS ALLIE MORT, un point de resurrection ; sinon, un point
de renfort.*

## 2bis. Les etages SOUS les feuilles — ce qui est LU, et ce qui reste une hypothese

### `ResetActiveAbility` : le parametre s'appelle `allowUseless`, et le port le nomme autrement

Chaine complete, **signatures lues** dans `frida/methods.tsv` :

    DSLBehaviors.ResetActiveAbility(units: ITargetsSelector, allowUseless: bool)
      -> ResetActiveAbilityBehaviour..ctor(units, allowUseless)
      -> ResetActiveAbilityBehaviour$$Execute : foreach u in units : processor.ResetActiveAbility(u, allowUseless)
      -> OperationProcessor.ResetActiveAbility(unit: IEntity, allowUseless: bool)
      -> ResetActiveAbilityOperation$$Execute(unit, allowUseless)

et le corps de l'Operation :

    if (!BattleQuery.EntityCanHaveActiveAbilityReset(unit, allowUseless))  return;
    foreach ab in unit.<ActiveAbilitiesComponent+0x20> :
        if (StaticBattleRules.ActiveAbility.IsRegularAttack(ab.<+0x44>))  continue;
        if (<predicat de config sur AbilitiesDatabase.Get(ab.<+0x44>)>) {
            ab.<+0x18> = 0;  ab.<+0x10> = 0;  ab.<+0x28> = 1;   # cooldown remis a zero, re-arme
            ...
        }

⚠ Le port existant (`runner/abilities/behaviours/ability_state.py::ResetActiveAbility`) nomme ce
parametre **`ignore_turn_flag`**, alors que la signature native le nomme **`allowUseless`**. La
POSITION et la destination sont les memes (il est transmis tel quel au gate
`EntityCanHaveActiveAbilityReset`), donc le port est fonctionnellement juste — mais le nom porte ne
correspond a rien dans le binaire. `PowerUp_ReactivateAbility` passe `allowUseless = true`.

### Les options de `Heal` / `Repair` : les DEFAUTS sont poses par le ctor, pas par l'appelant

Mesure comparative des trois constructions (offsets relatifs, donc stables) :

| champ | `HealBehaviourOptions()` ctor | `ForHeal(src)` | `ForRegenerate(src)` | ce que pose `PowerUp_Healing` |
|---|---|---|---|---|
| `+0x2c` | *(non pose)* | `0` | `1` | *(non touche)* |
| `+0x30` | `1` | `1` | `0` | *(non touche)* |
| `+0x33` | *(non pose)* | *(non pose)* | *(non pose)* | **`1`** |
| `+0x34` | `3` | *(non pose)* | *(non pose)* | **`1`** |

| champ | `RepairBehaviourOptions()` ctor | `ForRepair()` | `ForRegenerate()` | ce que pose `PowerUp_Healing` |
|---|---|---|---|---|
| `+0x10` | *(non pose)* | `0` | `1` | **`0`** |
| `+0x14` | `1` | `1` | `0` | **`1`** |
| `+0x16` | *(non pose)* | *(non pose)* | *(non pose)* | **`1`** |
| `+0x18` | `3` | *(non pose)* | *(non pose)* | *(non touche, reste `3`)* |

Ce qui se LIT de ce tableau, sans interpretation :

- le volet REPAIR de `PowerUp_Healing` pose **exactement** ce que pose `ForRepair()` (`+0x10 = 0`,
  `+0x14 = 1`), **plus** un `+0x16 = 1` qu'aucune des deux factories ne touche ;
- le couple `+0x2c` / `+0x10` est ce qui **distingue** `Heal` de `Regenerate` dans les deux
  familles (`0` vs `1`), et `PowerUp_Healing` le laisse a `0` cote heal / le pose a `0` cote
  repair — donc **soin franc, pas regeneration**, des deux cotes ;
- `+0x34` (heal) et `+0x18` (repair) occupent la meme position relative dans leurs structures et
  ont le meme defaut `3` ; `PowerUp_Healing` ramene le premier a `1` et **laisse le second a `3`**.

⚠ **HYPOTHESE NON TRANCHEE, et elle le reste** : que `+0x34`/`+0x18` soient un `UnitSelectionType`
(`3 = OnlyAliveAndTargetable`, `1 = OnlyAlive`) est **coherent avec les valeurs** mais n'a pas ete
LU — aucun accesseur nomme n'a ete decompile pour ces champs, et la mise a jour du build a ferme la
fenetre. De meme pour `+0x33`/`+0x16`. Le port ne fait donc porter **aucune decision** a ces
champs : il appelle les feuilles portees `Heal`/`Repair` avec leurs defauts, et l'ecart eventuel
est nomme en residu plutot que devine.

## 3. Le gameconfig — et le fait que `PowerUp_Bomb` n'a PAS de bouclier

Constantes lues (gameconfig du build `rnca9r7q6c`) :

| passif | constantes |
|---|---|
| `PowerUp_ReactivateAbility` | `nrOfRounds = 1`, `shieldPct = 100` |
| `PowerUp_Healing` | `nrOfRounds = 1`, `HealPercentage = 100`, `shieldPct = 100` |
| `PowerUp_Bomb` | `damageProfile = Blast`, `nrOfHits = 1`, `range = 4` — **ni `shieldPct` ni `nrOfRounds`** |
| `PowerUp_Reinforcement` | *(aucune)* |
| `PowerUp_ReinforcementShield` | `shieldPct = 10` |
| `PowerUp_Resurrect` | *(aucune)* |

⚠ **L'absence de `shieldPct` chez `PowerUp_Bomb` n'est pas un trou de donnee, c'est la branche
`Nothing()` du natif** : `APowerUpAbility$$AddShield` commence par
`if (!TryGetNumberConstant(config, 0x50 = shieldPct)) return Nothing();`. Bomb herite donc la base
mais son volet bouclier est **eteint par la config**, pas par le code. Un port qui poserait un
bouclier « parce que les autres en ont un » serait faux.

⚠ Et le `shieldPct = 10` de `PowerUp_ReinforcementShield` **ne pose aucun bouclier d'unite** : sa
classe surcharge `CreateBehaviour` en entier, donc `AddShield` n'est jamais appele. Cette constante
est lue par le **lambda**, et designe un pourcentage de bouclier de RENFORT accorde au joueur. Deux
usages homonymes de la meme cle, dans le meme lot — l'ordinal ne les distingue pas.

## 4. Ce que la couche cible NE PORTE PAS (mesure sur l'arbre, pas suppose)

| noeud natif | port |
|---|---|
| `ResetActiveAbility` | **present** (`runner/abilities/behaviours/ability_state.py`) |
| `Heal`, `Repair`, `is_mechanical` | **presents** (`behaviours/stats.py`, `entities/triggers.py`) |
| `If`, `op_and`, `CreateShield`, `Inform` | **presents** |
| `SurroundingEnemies`, `AllDeadUnits`, `hero_units`, `Friends` | **presents** |
| `RandomAmount`, `ConfigVar`, `PercentageOf`, `StatAmount` | **presents** |
| `AbilityAreaDamage` | **ABSENT** — le port deplie ce patron (precedent : `loki/death_nova.py`) |
| `OriginalOwner` | **ABSENT** comme selecteur |
| `IsHumanPlayer` | **ABSENT** — aucune notion humain-vs-IA dans le moteur |
| `AddReinforcementPoint`, `AddResurrectDraftPoint` | **ABSENTS** |
| `Do` (lambda) | **ABSENT** |

## 5. Etat de la tranche

RE **complete** pour les six. Portage et confrontation live : en cours — la fenetre DRAIN du
2026-08-14 (capteurs #1091) a suspendu toute creation de runner au moment ou cette RE s'achevait.

## 6. Residu deja constate, hors perimetre du portage

`POWER_UP_STAT_BOOST_ABILITIES` (`runner/operations/triggers/loki/power_up.py`) est **reference
nulle part** : une seule occurrence dans tout le depot, sa propre definition. Sa docstring annonce
« les CINQ entrees de `ABILITY_TRIGGERS` de cette tranche », mais le registre
(`triggers/dispatch/registry.py`) est alimente par **cinq lignes manuelles** qui citent les classes.
Le dict est donc un DOUBLON MORT, et toute divergence entre lui et le registre resterait
silencieuse.
