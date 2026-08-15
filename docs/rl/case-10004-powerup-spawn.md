# #10004 — les ONZE `PowerUp_*Spawn*` : DEUX corps natifs, neuf variantes de CONFIG

**Verdict en une ligne** : les onze ne sont pas onze mecaniques — ce sont **deux**
`CreateBehaviour` (`HeroSpawn`, `SummonSpawn`) au-dessus d'**une base commune**
`APowerup_SpawnAbility`, et les neuf autres entrees ne different que par **une cle de gameconfig**.

> RE faite contre le build **`t6dpr4k06g`** (Ghidra migre le 2026-08-15 : `named=124724`,
> `skipped=0`). Les deux `CreateBehaviour` sont a `1812aa540` et `1812aab10` — adresses citees
> uniquement pour attester la migration ; partout ailleurs, le **symbole**.
> ⚠ `data/symbols/t6dpr4k06g/ghidra/functions.tsv` n'etait pas encore extrait : le balayage
> exhaustif « qui surcharge quoi » a donc ete fait par `search_symbols_by_name`, **pas** par la
> table. C'est une source differente, et elle ne prouve pas la meme chose (cf. §1).

## 1. La partition — et ce que la mesure etablit VRAIMENT

`search_symbols_by_name` sur `Loki\.PowerUp_(HeroSpawn|SummonSpawn)\w*\$\$` rend **exactement
deux** corps de `CreateBehaviour` : `PowerUp_HeroSpawnAbility` et `PowerUp_SummonSpawnAbility`.
Les **neuf** variantes (`_VexilusPraetor`, `_BladeChampion`, `_Uthar`, `_ultraSmnInceptor`,
`_ultraSmnHeavyIntercessor`, `_bloodSmnIntercessor`, `_darkaSmnHellblaster`,
`_darkaSmnTerminator`, `_templSmnAggressor`) n'ont **aucun** symbole propre.

⚠ **Ce que cette absence prouve, et ce qu'elle ne prouve pas.** Le CLAUDE.md est explicite :
l'absence d'une methode dans une table indexee par ADRESSE ne prouve rien, IL2CPP deduplique les
corps triviaux. Ici la conclusion tient quand meme, mais **par une seconde source** : le
gameconfig montre que les neuf variantes portent chacune **une constante de plus** et rien
d'autre, ce qui est exactement le degre de liberte qu'un `GetStringConstant` laisse a une
sous-classe sans corps. Les deux mesures concordent ; aucune ne suffit seule.

`APowerup_SpawnAbility` — la base intermediaire — n'a que **trois** methodes : `GetSpawnTile`,
`GetPreferredTiles`, `GetKillBehaviour. **Pas de `CreateTrigger`**, ce qui confirme sur ce build le
fait etabli par la tranche 2 : **aucun** des 22 `PowerUp_*` ne surcharge le trigger. Le vecteur
`On(PreUnitDeath)` + `DamageReason.Steppable` de #1083-r1 vaut donc pour ces onze aussi.

## 2. Les deux corps

`DSLSelectors+0x18` = `AllTiles`, `+0x30` = `Owner`, `+0x40` = `Actor`, `+0x68` = `ActiveTarget`.

### `PowerUp_HeroSpawnAbility$$CreateBehaviour`

    unitId  = GetStringConstant(config, 0x7e = heroId)
    tuile   = Cache( GetSpawnTile(), unique = 1 )
    parent  = Player(1)
    options = new SpawnUnitOptions();  options.<+0x61> = 1
    spawn   = Spawn(parent, tuile, unitId, options)
    kill    = GetKillBehaviour(tuile)
    return If( IsInTeam(Actor, 1), kill & spawn, null )

### `PowerUp_SummonSpawnAbility$$CreateBehaviour`

    unitId  = GetStringConstant(config, 0x0 = unitId)
    tuile   = Cache( GetSpawnTile(), unique = 1 )
    options = SpawnUnitOptions.WithStatsFromConfig(config, abilityState, null, null)
    options.<+0x18> = PerformAIAttackFromCurrentPosition(ActiveTarget, null, null, false)
    parent  = Player(1)
    spawn   = Spawn(parent, tuile, unitId, options)
    kill    = GetKillBehaviour(tuile)
    return If( IsInTeam(Actor, 1), kill & spawn, null )

**Structure identique, TROIS differences, toutes lues** : la cle de config (`heroId` vs `unitId`) ;
la fabrique d'options (`new` + `<+0x61> = 1` vs `WithStatsFromConfig`) ; et le fait que le summon
recoit un ordre d'attaque IA immediat (`<+0x18>`), que le heros ne recoit pas.

⚠ **`IsInTeam(Actor, 1)` est LOAD-BEARING** — meme famille que l'`IsHumanPlayer` de
`PowerUp_Bomb` (#1083-r4) : **rien ne spawne** si l'unite qui ecrase le power-up n'est pas dans la
team 1. Contrairement a `PlayerType`, la **team** EST portee par le moteur, donc ce gate-ci est
evaluable — c'est la difference qui rend cette tranche portable la ou #1083-r4 est bloquee.

⚠ Le `1` de `Player(1)` et celui d'`IsInTeam(..., 1)` ne sont **pas le meme axe** (parent du spawn
vs team du ramasseur) : deux arguments homonymes, deux roles. Ne pas les fusionner en une
constante.

## 3. La base commune

### `APowerup_SpawnAbility$$GetSpawnTile` — une CASCADE de preferences

    ennemis = NormalUnits( Enemies(Actor, AllUnits(), 3), 3 )
    tuilesE = Filter( Tiles(ennemis), NOT IsSpawnTile(ActiveTarget) )
    libres  = SortByDistance( CanAddUnit( Randomize(AllTiles) ), Actor )
    return First( GetPreferredTiles(tuilesE)
                    .Otherwise( GetPreferredTiles(libres) )
                    .Otherwise( tuilesE )
                    .Otherwise( libres ), 1, 0 )

Soit quatre rangs de preference : tuiles d'ennemis normaux **preferees**, sinon tuiles libres
**preferees**, sinon tuiles d'ennemis, sinon tuiles libres. `Otherwise` n'est pas un `or`
booleen : c'est le repli d'un SELECTEUR vide sur le suivant.

### `APowerup_SpawnAbility$$GetPreferredTiles(validTiles)`

    return TilesWithoutPowerUps( Filter(validTiles, NOT IsTerritoryTile(ActiveTarget)) )

### `APowerup_SpawnAbility$$GetKillBehaviour(spawnTile)`

    cond = HasUnit(spawnTile, 3) & NOT HasTrait( Units(spawnTile, 1, 3), 0x1b = Steppable )
    return If( cond, Kill(Owner, spawnTile, KillUnitBehaviourOptions.ForClearTile()), null )

C'est-a-dire : **si la tuile choisie porte deja une unite non-`Steppable`, elle est TUEE pour
liberer la place**. Le `NOT HasTrait(Steppable)` evite de detruire un autre power-up ; et l'ordre
du `&` dans `CreateBehaviour` (`kill & spawn`) fait que le nettoyage precede le spawn.

## 4. Le gameconfig — et les DEUX entrees qui ne peuvent rien spawner

| id | entree | constantes |
|---|---|---|
| 1434 | `PowerUp_HeroSpawn` | **aucune** |
| 1436 | `PowerUp_HeroSpawn_VexilusPraetor` | `heroId = custoVexilusPraetor` |
| 1437 | `PowerUp_HeroSpawn_BladeChampion` | `heroId = custoBladeChampion` |
| 1517 | `PowerUp_HeroSpawn_Uthar` | `heroId = votanUthar` |
| 1532 | `PowerUp_SummonSpawn` | **aucune** |
| 1533/1536/1537/1538/1539/1540 | les six `_<summon>` | `unitId = <summon>`, `nrOfSummons = 1` |

⚠ **1434 et 1532 n'ont AUCUNE constante** : leur `GetStringConstant(heroId|unitId)` ne peut pas
rendre d'identifiant, donc elles ne spawnent rien. Ce sont les entrees de BASE, et le fait qu'elles
soient inertes se lit dans la config, pas dans le code. Un port qui les inscrirait sans le dire
ferait croire a onze mecaniques vivantes la ou il y en a **neuf**.

## 5. Etat

RE **complete** des onze (deux corps + base + config). Portage et confrontation : en cours.
Le gate `IsInTeam(Actor, 1)` est evaluable cote port, et le montage de confrontation est celui,
deja mesure, des tranches 1 et 2 (`catalog_inject` + `--explicit-stats` + `--a-units`, board
indifferent) — dans lequel le ramasseur cote joueur est **team 1**, donc le gate passe.
