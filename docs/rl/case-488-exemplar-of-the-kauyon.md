# #488 -- `1087 ExemplarOfTheKauyon` : le port du TELEPORT-PUIS-ATTAQUE

Porteur lineup : `tauShadowsun` (Commander Shadowsun, HERO, rank 17, **dans le pool**).
Porteurs npc : `tauBossShadowsun`, `tauBossShadowsunInc`, `tauBossShadowsunLHE`, `tauNpcShadowsun`.

**Etat avant** : NO-OP SILENCIEUX. L'ability etait absente d'`ABILITY_CLASSES`, donc la decision la
choisissait et l'execution l'ignorait -- 0 deplacement, 0 spawn, 0 degat, **aucune erreur**. Son
entourage, lui, etait deja porte : le masque de ciblage, la regle dynamique et l'effet 1181. Ce qui
manquait etait l'ability qui les MET EN OEUVRE.

## 1. Ce que le natif ECRIT

`IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheKauyonAbility$$ExecuteBehaviour`, lu
noeud par noeud. Offsets de `IdunBattleLogic.Entities.DSLSelectors` (convention deja etablie dans le
port : `caster@0x48`, `target@0x60`, `ActiveTarget@0x68`, `AllTiles@0x18` -- ce dernier LU
directement dans `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`, seul champ dont le ctor
nomme sa classe : `IdunBattle.Entities.Selectors.AllTilesSelector`).

```
teleport = DSLBehaviors.Teleport( caster@0x48, target@0x60 )
aiAttack = DSLBehaviors.PerformAIAttackFromCurrentPosition( target@0x60, null, null, false )
exTile   = DSLSelectors.Entity( <AbilityEntities+0x40 = casterTile> )
unitId   = AbilityConfiguration.GetStringConstant( config@0x60, 0 )     # "unitId"
opts     = SpawnUnitOptions.WithStatsFromConfig( config@0x60, abilityState, null, null )
opts.<+0x18> = DSLBehaviors.AddTrait( ActiveTarget@0x68, 0x418, null )  # UnitTrait.Stationary
tileSel  = First( CanAddUnit( exTile + SortByDistance( Randomize( AllTiles@0x18 ), exTile ) ), 1, null )
spawn    = DSLBehaviors.Spawn( caster@0x48, tileSel, unitId, opts )
addEff   = DSLBehaviors.AddEffect( 0x49d, AbilityStateReference,
                                   source = caster@0x48, targets = caster@0x48, options = default )
remEff   = DSLBehaviors.RemoveEffect( caster@0x48, (int?)0x49d, null )

AActiveAbility.Execute( entities, this,
    ( teleport & If( <DSLTriggers+0x20 = OwnerIsAlive>, (addEff & aiAttack) & remEff ) ) & spawn )
```

`0x49d` = `EffectType.ExemplarOfTheKauyon_AdditionalHits` (1181) ; `0x418` = `UnitTrait.Stationary`
(1048). Config : `unitId=tauSmnDroneCommandLink`, `damageProfile=Blast`, `nrOfHits=2`,
`initialCooldownTurns=1`.

### Trois lectures qu'aucun nom ne laissait deviner

1. **`AbilityEntities+0x40` EST `casterTile`** -- etabli par les noms de parametres du
   `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` (32 arguments nommes : `+0x00` actor,
   `+0x08` caster, `+0x10` target, `+0x18` owner, `+0x20` activeTarget, `+0x28`
   previousActiveTarget, `+0x30` targetTile, `+0x38` targetTiles, **`+0x40` casterTile**, `+0x48`
   casterTiles, `+0x50` activePlayer, `+0x58` effect). C'est une entite CAPTUREE a la construction
   de l'`AbilityEntities`, donc **avant** le teleport -- d'ou l'i2 « summoned in the hex she
   **previously occupied** ». Un selecteur `CasterTile()` DYNAMIQUE rendrait la nouvelle tuile ;
   c'est precisement pourquoi le natif passe par `DSLSelectors.Entity(<entite>)`.
2. **Le `Spawn` est HORS du `If`.** Si Shadowsun meurt en se teleportant, ni l'effet ni l'attaque
   n'ont lieu -- mais le drone apparait quand meme.
3. **`PerformAIAttackFromCurrentPosition` recoit un selecteur de TUILE**, pas d'unite, et son corps
   `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute` le resout par le **slot 4**
   de l'`ITargetsSelector` (« resoudre en UNITES »), puis ecrit `get_Id` de chaque element dans
   `AbilityEntities+0x00` (l'ACTEUR). L'acteur est donc l'occupant de la tuile -- Shadowsun, qui vient
   d'y arriver.

## 2. Ciblage

`...ExemplarOfTheKauyonAbility$$.ctor` emprunte la forme **7 arguments explicites** (ni preset copie,
ni surcharge PRESET+FLAGS) :

```
TargetingOptions..ctor(&opts, isSelfCasting = 0, range = &<TargetingRange statics+0x48>,
                       forceMeleeTarget = 1, rules = 0x6001042, null, null)
AActiveAbility..ctor(this, &opts, 2)
```

-> `ABILITY_ATTACK_TYPE[1087] = 2` = `AbilityAttackType.Others` (3e argument, ecrit en `this+0x68`).
-> masque `0x6001042`, decompose EXHAUSTIVEMENT (aucun bit residuel) :
`TargetMatchesDynamicRule (0x2) | TargetIsTile (0x40) | TargetTileIsFree (0x1000) |
AllowObscuredTargetByElevation (0x2000000) | AllowObscuredTargetByWalls (0x4000000)`.
Portee `RANGE_WHOLE_BOARD`, `forceMeleeTarget = 1 = RangedBool.False`.

Le masque et la regle dynamique **existaient deja**, dans `TARGETING_OPTIONS_UNPORTED` (#241) et
`DYNAMIC_TARGET_RULE_UNPORTED` (#287-r4-r1). Les deux **MIGRENT** sur la classe avec la face COMBAT,
et leurs entrees des tables `*_UNPORTED` sont RETIREES dans le meme commit -- c'est le contrat de
disjonction que garde `tests/engine/runner/test_targeting_options_sources.py`. Le CORPS de la regle
(`targeting.py::_dynamic_rule_exemplar_of_the_kauyon`, avec sa RE du `Remove(caster)`) reste a sa
place : un seul foyer, la methode de la classe l'appelle.

## 3. Ce que la tranche a AJOUTE au port

| Piece | Fichier |
|---|---|
| `DirectDisplaceOperation` -- case **4** (`Direct`) de `IdunBattle.Operations.DisplaceUnitOperation$$Execute` | `engine/runner/operations/displace.py` |
| Feuille DSL `Teleport` (mirror `IdunBattleLogic.Entities.DSLBehaviors$$Teleport`) | `engine/runner/abilities/behaviours/movement.py` |
| `PerformAIAttack` : resolution d'un selecteur de TUILE en **occupant**, pas seulement en enfant du cast | `engine/runner/abilities/behaviours/summon.py` |
| `ExemplarOfTheKauyonAbility` + son arbre | `engine/runner/abilities/tau.py` |
| Registre, attack-type, migration des deux tables `*_UNPORTED` | `handler.py`, `attack_type.py`, `targeting.py` |

Le case 4 etait **attendu** : le `record_tiles` de `DisplaceUnitOperation` portait deja le commentaire
« le parametre existe pour que la seule feuille `Direct` qui l'active (`DSLBehaviors$$Teleport`, non
encore portee) trouve son gate en place ». `Teleport` et `SwitchPosition` sont les deux SEULES
feuilles a poser `+0x1c = 1` : le teleport COMPTE ses tuiles (`RecordTilesMoved`), un push non.

`set_moved=False` : la queue commune d'`Execute` n'appelle PAS `MoveUnit`, elle ecrit la position par
le slot `0x7e` = `IdunBattle.Operations.SetUnitPositionOperation$$Execute`, dont le corps -- relu en
entier -- ne contient **aucun** `SetMovedFlag`. Meme verdict que le switch, lui mesure (#287).

## 4. LE CRAN SOUS LE COMPTE DE COUPS

L'`AddEffect` du natif porte un 2e argument, l'`AbilityStateReference`. Le port l'exprime par
`scale_from_source=True`. **Sans lui, l'effet 1181 retombe au niveau 1** :
`...ExemplarOfTheKauyon_AdditionalHitsEffectEffect$$CreateAdditionalHits` lit son degat par
`DSLFormulas.ConfigVar(0xb = dmg, GetAbilityState(effet), config)`, donc contre le niveau d'ability
**de l'unite qui a pose l'effet**.

Mesure #488, `MC1_67` / `orksNob` : les 2 coups additionnels valaient **40** au lieu de **3979** --
alors que la phase ARME etait **deja bit-exacte** (`3162`, `2678`). Un critere qui n'aurait regarde
que le NOMBRE de coups serait reste **VERT** : 4 coups des deux cotes. C'est pourquoi le probe et le
test comparent la **SEQUENCE**, jamais un total agrege (deux coups justes et deux faux peuvent donner
la meme somme), et pourquoi `test_e3bis_les_coups_additionnels_portent_le_niveau_du_caster` garde
separement la queue de la sequence.

## 5. Validation

`probe_488_exemplar_of_the_kauyon.py` (MESURE) / `tests/engine/runner/test_exemplar_of_the_kauyon_live.py`
(GARDE). Le port rejoue le cast depuis le snapshot pris **juste avant** le cast natif -- meme substrat,
meme RNG. Quatre etages, chacun son verdict :

| Etage | Contenu | `MC1_67` | `C1_21` | `C2_02` | `--loin` |
|---|---|---|---|---|---|
| E0 CIBLAGE | tuiles legales natives (`abilityTargets.fromHere`) vs balayage du gate porte sur TOUT le plateau | 4 = 4 | 4 = 4 | 5 = 5 | 4 = 4 |
| E1 TELEPORT | le caster atterrit sur la tuile cible | OK | OK | OK | OK |
| E2 SPAWN | `tauSmnDroneCommandLink` `Stationary` sur l'EX-tuile | OK | OK | OK | OK |
| E3 COUPS | SEQUENCE identique | `[3162, 2678, 3979, 3979]` | `[2820, 2622, 2992, 2992]` | `[2820, 2622, 2992, 2992]` | `[]` = `[]` |

E0 balaye **tout** le plateau et pas seulement ce que le natif accepte : un port trop PERMISSIF
(masque absent -> retour 0 immediat) accepterait des tuiles que le natif refuse, et une inclusion
simple ne le montrerait pas.

`--loin` vise la destination legale la plus ELOIGNEE de l'ennemi : le gate de portee de l'IA ferme
**des deux cotes** (0 coup), et le teleport + le spawn ont quand meme lieu -- c'est la generalisation
qui separe les trois etages.

**CONTRE-EPREUVE** (`--mutant`, 1087 retire d'`ABILITY_CLASSES`) : `ported=False`, caster immobile,
0 spawn, 0 coup -- les quatre etages rougissent. C'est exactement l'etat d'avant la tranche.

### Ce qui n'est PAS couvert

* **Le repli de tuile de spawn** (`SortByDistance(Randomize(AllTiles), exTile)`) : il n'entre en jeu
  que si l'EX-tuile du caster est occupee a l'instant du `Spawn`. Le cast etant atomique et le
  teleport LIBERANT cette tuile, aucun montage ne produit ce regime -- il est INATTEIGNABLE par le
  jeu normal. Le `Randomize` est neanmoins evalue (le `+` evalue ses deux operandes avant que
  `First(1)` ne tranche), donc sa consommation RNG a lieu ; elle n'est pas confrontee.
* **La branche `If(OwnerIsAlive)` FAUSSE** (caster tue pendant le teleport, par overwatch ou piege) :
  non montee. Shadowsun porte `Infiltrate` (ne declenche pas l'overwatch), ce qui rend le regime
  difficile a atteindre avec ce porteur.
* **Le cooldown initial** (`initialCooldownTurns=1`) : non confronte.

## Residus

* **#488-r1 -- `case-72` (OnMelta dead-code) est peut-etre PERIME sur `rnca9r7q6c`.** En generalisant
  l'ennemi (`--enemy admecDestroyer`, un `Vehicle`/`Mechanical`), la phase ARME diverge : natif
  `[4497, 5349]`, port `[3162, 2678]`. **Ce n'est PAS #488** -- un bras de CONTROLE, Shadowsun posee a
  la main sur la meme tuile et faisant une attaque NORMALE NUE (aucun cast de 1087, code non modifie
  par cette tranche), rend le MEME ecart ; le meme bras contre `orksNob` (non-Vehicle) est
  bit-exact. Or `engine/entities/damage_trait.py` declare le `+50 %` Melta vs `Vehicle`
  (`Melta_ExtraDmgEffect`, `OnMeltaDamageAbility` sans `CreateTrigger`) DEAD-CODE et NON porte, sur
  la foi d'une mesure faite dans le build **`gqfc5mff6c`** et pour ce couple exact
  (`tauShadowsun` Melta ranged vs `admecDestroyer`). A re-mesurer sur le build courant : soit le
  trigger existe desormais, soit un autre canal explique l'ecart. Reproduction :
  `python probe_488_exemplar_of_the_kauyon.py --enemy admecDestroyer` (E0/E1/E2 verts, E3 rouge sur
  la seule phase ARME, les coups additionnels restant bit-exacts).
