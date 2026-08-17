# #433-r3-r2-r1 / #433-r3-r2-r1-r1 / #550-r4-r1 — qui POSE un `UnitFlag`, et a quel RANG il mord

Build : `t6dpr4k06g`. Trois residus, une seule question de fond. **Les trois enonces sont VRAIS**,
et les trois SOUS-ESTIMENT leur propre ecart.

## 1. Le trou etait dans la MOITIE DU PORT QUE PERSONNE N'AVAIT COMPTEE

La fiche #433-r3-r2-r1 dit : « le port n'inscrit JAMAIS `UnitFlag.Untargetable` (`0x11`) ».
Exact — `UnitFlagsComponent` n'avait meme pas le membre.

Ce qu'elle n'ecrit pas, c'est que le port a **DEUX familles de lecteurs**, et qu'une seule
fonctionnait :

| famille | ce qu'elle interroge | etat avant |
|---|---|---|
| EFFET | `state.effects` contre `UNTARGETABLE_EFFECT_TYPES` | **vivante** (`aura_selectors.is_targetable`, `ai.state_bridge._is_untargetable`, `playbook.adjacency.is_targetable`) |
| FLAG | `UnitFlagsComponent.has(0x11)` | **MORTE** |

`abilities/targeting.py::is_targetable` le DISAIT dans sa propre docstring : « le flag 0x11 n'est
pose par AUCUN chemin du port -> le predicat est constamment vrai offline ». Or
`IdunBattle.Entities.UnitExtensions$$IsTargetable` = `HasFlag(unit, 0x11) ^ 1` a **CINQ** appelants
natifs (xrefs relues), dont **QUATRE portes** :

- `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` — la regle `TargetIsTargetable`
- `IdunBattle.Core.Services.DamageCalculations$$ShouldApplyRangedInMelee`
- `IdunBattle.Operations.DisplaceUnitOperation$$ApplyKnockbackTo`
- `IdunBattle.Core.Services.BattleQuery$$IsTargetInAttackRangeForSummon`
- (le cinquieme, cote DECISION : `MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext`)

Les quatre etaient donc inertes. C'est ce qui rend la **voie (a)** de la fiche (« faire poser le
flag ») la bonne : elle ne double pas le canal EFFET, elle en ARME un second qui voit autre chose.

**PORTE** : `UnitFlagsComponent.UNTARGETABLE`, `AddEffectOperation._apply_untargetable_flag`
(mirror `UntargetableEffect$$ApplyInternal`, corps ENTIER = le gate virtuel `+0x728`
`IsUntargetableEnabled` puis `UnitFlagsComponent$$Add(0x11)`), et son pendant dans
`remove_effect_instance` (mirror `$$RevertInternal`, **tail call NU**).

### Le gate `IsUntargetableEnabled` est honore par le DOMAINE, pas par un predicat de plus

Une seule classe du build surcharge ce virtuel : `TitanhammerSquad_TeleportingInEffect`, corps
`32 c0 c3` = `xor al,al ; ret` = **false**. Son `EffectType 1573` est precisement celui que
`UNTARGETABLE_EFFECT_TYPES` EXCLUT. Toute autre derivee herite du corps de la base, dont la valeur
`true` est etablie par **MESURE** et non par lecture (le corps est deduplique, absent des deux
tables) : `1035` est dans le domaine ET confronte live (`darkaTerminator` en teleport-in ne recoit
RIEN de `LionHelm`), ce qui serait impossible si le defaut rendait faux.

### `1044` inscrit — et l'OBSERVABILITE est etablie par le NATIF, sans montage

C'etait le seul point que la fiche laissait ouvert : « si rien n'inspecte l'etat entre le
`AddEffect` et le `RemoveEffect` du meme arbre, l'inscription serait INERTE ».

Elle ne l'est pas, et la preuve est dans l'arbre natif lui-meme :

    WallOfMirrorsAbility$$ExecuteBehaviour :
        move = (AddEffect(1044, Caster) & FlyUnit(Caster, tiles)) & RemoveEffect(1044, Owner@+0x30)
        hit  = If(<DSLTriggers+0x20> = OwnerIsAlive, ...)          <-- ENTRE le vol et l'attaque

Le natif **TESTE que le caster a survecu au `FlyUnit`**. Une fenetre dont le natif verifie qu'elle
peut tuer son occupant n'est pas une fenetre morte. Cote `KissOfDeath`, c'est plus net encore : le
`ChainAttackDamage` ENTIER — jusqu'a `maxAdjacentTargets` coups — s'execute dedans.

Les deux faces sont portees aux deux sites (`kiss_of_death_tree`, `wall_of_mirrors_tree`), donc les
trois criteres d'entree au domaine (classe derivee, poseur porte, retireur porte) sont satisfaits.

### Ce qui RESTE ouvert : `#433-r5`

`$$RevertInternal` retire le flag **NU** — aucun comptage de references. Deux effets untargetable
simultanes partagent UN element d'`OrderedSet` : le premier retrait rend l'unite ciblable alors que
le second effet vit encore. Le port reproduit ce quirk. Consequence : dans ce regime, canal FLAG et
canal EFFET divergent, et le OU de `selection_ok_from_ctx` choisit le canal EFFET (donc le port est
plus RESTRICTIF que le natif). Grave par l'etage 4 de la garde, non tranche.

## 2. `#433-r3-r2-r1-r1` — les deux fenetres hors-effet, et le bloc « non lu » l'est

Mesure exhaustive : **TROIS poseurs, TROIS retireurs** de `0x11`. Outre l'effet :

| Operation | ce qu'encadre la fenetre |
|---|---|
| `ResurrectUnitOperation$$Execute` | `KillSteppableUnits` + `RemoveTurnFlags` + `SendStreamEvents` |
| `AddUnitOperation$$Execute` | `ClearFeet` + la boucle `Blueprints$$UnitFoot`/`AddFoot` + **`AddUnitOperation$$KillSteppableUnits`** + `RemoveTraitsThatAreNotInheritedWhenCloned` / `GetFullStateUpdateTags` |

Le second bloc, que la fiche declarait « NON LU » (fonction trop volumineuse pour le decompilateur
en un bloc), a ete obtenu par extraction des appels entre les deux instructions. **Meme nature que
le premier, et pas plus morte** : `KillSteppableUnits` passe par `KillUnitOperation$$Execute` en
entier — cinq evenements de mort, trois `RemoveEffects` — donc du code de jeu s'y execute et peut
enumerer des cibles. La voie **(b)** du residu (porter) etait donc la bonne, pas la voie (a).

Les deux fenetres sont portees en `try/finally` : sans lui, une exception laisserait l'unite non
ciblable POUR LE RESTE DE LA BATAILLE — le mode de defaillance que #1074 avait deja nomme.

**Corrige aussi** : la prose de `unit_selection_type.py` et d'`aura_selectors.py`, qui laissait
croire qu'un domaine d'`EffectType` couvre TOUTE la non-ciblabilite native. Les deux canaux ne sont
pas redondants — le canal EFFET ne peut PAS voir ces deux fenetres.

## 3. `#550-r4-r1` — « mauvais rang » est une affirmation de STRUCTURE, et elle tient

`IdunBattle.Operations.DisplaceUnitOperation$$Execute` **ne teste la mort NULLE PART** (relu
verbatim : `IsDisplaceable`, `IsSteppable`, `switch(direction)`, partie commune). Le seul test du
chemin est le 2e gate de `SetUnitPositionOperation$$Execute` — le slot `0x7e` par lequel
l'operation ECRIT — et il **loggue puis sort**, sans que l'appelant le regarde :

    if (!content.IsFilled()) {
        prevTiles = GetTiles(target)
        processor.<0x7e>(target, new UnitPosition(tile), false)    <- REFUSE si HasFlag(unit, 6)
        AddTilesMoved(this, caster, target, prevTiles, tile, options)
        return EventAndAbilitiesAndEffects(this, caster, target, prevTiles, tile, ...)
    }

Sur une cible morte le natif **n'ecrit pas la position mais emet quand meme** les trois vecteurs
`0x24` / `0x23` / `0x1d` et le refresh `0x2f(7)`. Le `return` sec de tete du port n'emettait rien.

### L'atteignabilite est STRUCTURELLE, pas speculative

`DisplaceUnitBehaviour` resout ses cibles avec `targetSelectionType = 2 = OnlyTargetable`, et
`MatchesUnitSelectionType` **n'appelle PAS `IsAlive` a ce selectionType** (fait etabli par
#433-r3-r2). Un cadavre reste donc selectionnable. Il suffit que le knockback de collision d'un
push precedent ait tue une unite encore dans la liste du `Foreach`.

### Le SECOND volet du residu : le bloc (c) n'appartenait pas a cette Operation

`SetUnitPositionOperation$$Execute` relu verbatim : `GetUnitFeet` -> S1 -> S2 -> `GetUnitPosition`
-> boucle d'ecriture par pied -> `SavePreviousPosition` -> `VerifyTerritoryCapture`. **Aucun appel
au publieur d'evenements, aucune reservation.** Les cinq stand-ins jouaient pourtant :

- `SetReservation` sur la destination ;
- `On(PreUnitMove = 0x1f)` — un vecteur **FANTOME**, dont `HatefulAssaultAbility` (l'attaque
  d'opportunite) est le consommateur le plus visible : le port la declenchait sur un DEPLACEMENT
  FORCE ;
- le bloc d'override (a)/(b)/(c), dont le bras `IsDead` DOUBLAIT S2 et rendait son ajout
  inobservable.

Les quatre morceaux sont **solidaires** — (c) CONSOMME ce que (b) ecrit — donc ils sont eteints
ensemble, sous le meme discriminant que S1/S2.

### Deux ajouts du port, NOMMES plutot que tus

- une garde d'idempotence sur le crush steppable (ne pas rejouer la sequence de mort d'un cadavre,
  doctrine #462-r4b...-r4). Le natif ne peut pas atteindre ce regime : un Steppable mort a ete
  retire du plateau ;
- le gate `alive` de `_apply_knockback_to` reste, en plus du vrai `IsTargetable` desormais joue.

## 4. Validation

`scripts/python/tests/engine/runner/test_433r3r2r1_550r4r1_untargetable_et_rang_offline.py` —
16 etages, chacun avec sa contre-epreuve dans le meme montage, fixture nommee `_monter_etat`.

**Joue sur un `git archive` de l'arbre de depart (arbre COMPLET, `data/` inclus) : 13 rouges /
3 verts.** Les 3 verts d'avant sont exactement les TEMOINS de discrimination (push bloque, push
nominal, `MoveUnitOperation` nominal) — ils doivent passer des deux cotes.

Deux details de methode qui ont failli rendre un etage muet :

- la destination du push de reference est **(4,2)** et non (4,3) — parite even-q. Figee sous
  `DEST_PUSH` plutot que recopiee au juge ;
- l'assertion de la QUEUE passe **AVANT** celle du libelle : dans l'autre ordre, l'arbre d'avant
  rougissait sur `reason: dead` (un libelle) au lieu de l'absence des trois vecteurs, qui est le
  FAIT que le residu accuse.

### Trois tests existants mis a jour, tous parce que le fix change delibérement leur verdict

- `test_498r3_is_displaceable_offline.py` etage 5 — gardait « le gate `alive` est CONSERVE » ;
- `test_550r4_462r5r3_can_add_unit_offline.py::test_S2_...` — **son propre message d'assertion
  demandait cette mise a jour** (« S2 n'est donc PLUS double... Mettre a jour cette docstring ») ;
- `test_448_r2b_...::test_the_untargetable_domain_holds_only_the_confronted_slices` — le domaine
  gagne `1044`, et la raison d'exclusion de `1573` change de nature (refus PROUVE, plus « poseur
  non porte »).

### Un rouge PREEXISTANT de `master` repare au passage

`test_270r1r1_container_enum_offline.py::test_etage2_anti_deplacement` rougissait **deja** sur
l'arbre de depart : #1074 avait inscrit `1061` au domaine sans mettre a jour le snapshot
value-preserving. Le snapshot passe de `(1035, 1140, 1238)` a `(1035, 1140, 1238, 1061, 1044)` et
le total de `159` a `161`.

## 5. Ce qui n'est PAS couvert

- **Aucune confrontation LIVE.** Les deux porteurs de `1044` sont hors pool (npc + summon a
  spawner d'ENVIRONNEMENT) ; la voie est la GREFFE (`case-92` §5bis), dont la condition est
  etablie dans les deux modules mais qui n'a pas ete jouee.
- La fenetre de **spawn** est gardee par une garde STRUCTURELLE (AST), pas comportementale :
  monter un `AddUnitOperation` complet demande un `summon_context` gameconfig.
- Le regime **MULTI-EFFETS** (divergence FLAG / EFFET) est grave, pas tranche — `#433-r5`.
- Les autres ecarts du stand-in de `SetUnitPositionOperation` (le port joue encore
  `CalculatePaths`, `KillSteppableUnits`, `SetMovedFlag`, `AddMoveEvent`, `UpdateCharging`,
  `EvaluateAfterMoveTriggers` la ou le natif n'a qu'une boucle d'ecriture) restent ouverts.
