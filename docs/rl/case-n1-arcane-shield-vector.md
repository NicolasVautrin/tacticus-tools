# N1 — `ArcaneShield` (Thaumachus / `thousSorcerer`) : vecteur `On(0x1c)` + formule de tri additive

**FERME.** Le vecteur est recable sur `On(0x1c=ArrivedAtFinalTile)` et le classement de la cible est
un score ADDITIF. RE au decompile du build `gqfc5mff6c` ; portage, mesure et gardes livres.

---

## 1. Critere binaire n°1 — le bouclier est-il accorde en fin de tour SANS deplacement ?

**OUI cote natif. Le port historique disait NON.**

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$CreateTrigger` (lu verbatim) :

    On(0x1c, ownerNeedsToBeAlive = 1)
      op_BitwiseAnd get_OwnerIsActor
      op_BitwiseAnd get_OwnerIsCaster

`0x1c = 28 = EventTriggerType.ArrivedAtFinalTile`. Il n'y a **aucune** branche `On(4=UnitAfterMove)`
dans le trigger natif. Le port etait route sur le MAUVAIS event
(`engine/runner/operations/triggers/loki/arcane_shield.py`, `event_id = EventTriggerType.UnitAfterMove`),
et sa docstring l'assumait comme une approximation.

Les deux emetteurs natifs de `On(0x1c)`, deja lus et deja PORTES (apportes par `SpiritualLeader`) :

  * `IdunBattle.Operations.MoveUnitOperation$$Execute` — `UnitFlagsComponent.Add(1 = ArrivedAtFinalTile)`
    puis, **apres** `EvaluateAfterMoveTriggers`, publie `On(0x1c)` SSI le flag venait d'etre AJOUTE
    (donc au 1er move de l'activation seulement) ;
  * `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` — `Add(1)` puis publie `On(0x1c)` SSI le
    flag venait d'etre ajoute **et** `!forced` — c'est **la cloture de tour d'une unite qui n'a pas
    bouge**.

=> `On(0x1c)` fire **AU PLUS UNE FOIS par activation d'unite** : a la fin de son 1er deplacement, ou
a la cloture de son tour si elle n'a pas bouge. Le gate par flag interdit la double pose. Le flag est
purge par `RemoveTurnFlags(new_activation=True)` au debut du tour suivant, ce qui re-arme l'event.

Cote port, le vecteur EXISTAIT DEJA, porte et valide : `arrived_at_final_tile_triggers`
(`triggers/dispatch/move_death.py`, appele (a) en queue d'`after_move_triggers` et (b) par
`FinishUnitTurnOperation.execute` avec `gate_already_consumed=True`). Le correctif n'a donc pas
construit de vecteur : il **recable `ArcaneShieldAbility.event_id`** sur
`EventTriggerType.ArrivedAtFinalTile`.

---

## 2. Critere binaire n°2 — les 4 paliers de priorite (fiche N1)

**La fiche `docs/rl/port-residuals-inventory.md` (entree N1) a tort sur les deux points.**

1. Le code cite (`prio = 0 if (own_fac == own_fac) else ...`, tautologie) **n'existe pas**.
   `arcane_shield.py:62` dit `prio = 0 if (own_fac is not None and fac == own_fac) else (1 if fac in
   CHAOS_FACTIONS else 2)` — pas de tautologie.
2. « le palier `2` retient un allie NON-Chaos alors que le montage de `21494b6` etablit l'inverse » :
   **faux**. Le natif retient bel et bien les allies non-Chaos — le pool
   `SurroundingFriends(...)` ne filtre QUE sur `UnitsWithoutTrait(Steppable)` +
   `UnitSelectionType.OnlyAliveAndTargetable`, jamais sur la faction ni sur le trait Chaos. Le trait
   Chaos n'est qu'une **penalite additive de +1** dans le score de tri.

**Mais le port se trompait quand meme, autrement, et plus gravement** : il n'y a **AUCUN ordre
lexicographique a 4 paliers**. Le natif construit un **score ADDITIF** ou la DISTANCE domine.

### `ArcaneShieldAbility$$CreateBehaviour` — arbre lu verbatim

    duration = TurnsFromRounds(1)

    pool     = Randomize( UnitsWithoutTrait(
                            SurroundingFriends( Caster@0x148,
                                                range = GetNumberConstant(config, 0x16),
                                                unique = true,
                                                UnitSelectionType.OnlyAliveAndTargetable = 3 ),
                            trait = 0x1b = 27 = Steppable,
                            UnitSelectionType.OnlyAliveAndTargetable = 3 ) )
               op_Addition Caster@0x148                       // TargetsSelector.op_Addition

    // les quatre termes sont aussi exportes comme helpers nommes :
    Distance = Multiply( AverageDistance(Caster@0x148, Units(It@0x180, unique, onlyAlive)), Get(3) )
    Faction  = ConditionalAmount( IsSameFaction(Caster@0x148, It@0x180), Zero, Get(1) )
    Chaos    = ConditionalAmount( HasTrait(It@0x180, 0x7ea = 2026 = UnitTrait.Chaos), Zero, Get(1) )
    Owner    = ConditionalAmount( op_LogicalNot(AreEqual(Caster@0x148, Units(It@0x180))),
                                  Zero, Get(range * 3 + 4) )

    best     = Cache( First( SortByFormula(pool, Sum(Distance, Faction, Chaos, Owner),
                                           ascending = true), 1 ), matchAbilityEntities = true )

    result   = CreateShield( best, ConfigVar(0x27 = shieldHp, abilityState, config),
                             AbilityOrEffect(self.Id), duration,
                             createdByEffect = null, stackable = true )

Les quatre termes ont chacun leur symbole natif dedie, ce qui confirme la lecture :
`ArcaneShieldAbility$$Distance`, `$$Faction`, `$$Chaos`, `$$Owner`.

### Preuves des primitives (lues, pas deduites)

  * `IdunBattleLogic.Entities.DSLFactory$$.ctor` remplit cinq constantes-formules :
    `+0xb8 = Direct(0)`, `+0xc0 = Direct(1)`, `+0xc8 = Direct(2)`, `+0xd0 = Direct(100)`,
    `+0xd8 = Direct(-1)`. Le `Zero` des trois `ConditionalAmount` est donc bien `+0xb8 = 0`.
    (Ghidra mislabel ce ctor `IceTileEffect_<FreezeCoroutine>d__5__.ctor` — c'est la STRUCTURE qui
    tranche, jamais le nom.)
  * `IdunBattle.Entities.Formulas.ConditionalAmount$$Calculate` : evalue le trigger `+0x10` ;
    VRAI -> `+0x18` (`formulaTrue`), FAUX -> `+0x20` (`formulaFalse`). L'ordre du call-site est donc
    `ConditionalAmount(trigger, formulaTrue, formulaFalse)` (confirme par la signature de
    `methods.tsv` : `abilityTrigger, formulaTrue, formulaFalse`).
  * `IdunBattle.Entities.Selectors.SortByFormulaSelector$$Select` : champ `+0x28` (`ascending`) ==
    0 -> `Enumerable.OrderByDescending`, sinon `Enumerable.OrderBy`. Le call-site passe `1` =>
    **tri ASCENDANT** (le plus PETIT score gagne), et `OrderBy` est **STABLE** => les ex aequo sont
    departages par l'ordre SOURCE, c'est-a-dire l'ordre rendu par `Randomize`.
  * `IdunBattle.Entities.Formulas.AverageDistanceFormula$$Calculate` ->
    `IdunBattle.Core.Services.BattleQuery$$GetAverageDistance(a, b, 10000)` : double boucle a x b,
    somme des `IdunBattle.Entities.Components.PositionComponent$$Distance`, division ENTIERE par le
    compte ; `10000` si le compte est nul. Ici `b` = un seul candidat => c'est la distance hex
    caster -> candidat.
  * `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(config, 0x16)` :
    `AbilityConstantType 0x16 = 22 = range` (deja documente dans `engine/entities/formulas.py`,
    classe `ConfigConst`). `ArcaneShield.constants = {'range': '2'}` => **range = 2**.
  * `UnitSelectionType` : `0=Any, 1=OnlyAlive, 2=OnlyTargetable, 3=OnlyAliveAndTargetable`.
  * `UnitTrait` : `27 = Steppable`, `2026 = Chaos`.

### Le score, chiffre (range = 2)

    score(candidat) = 3 * dist_hex(caster, candidat)
                    + (0 si meme FactionId que le caster,     sinon 1)
                    + (0 si le candidat a UnitTrait.Chaos,    sinon 1)
                    + (0 si le candidat n'est PAS le caster,  sinon range*3 + 4 = 10)

| candidat                        | score |
|---------------------------------|-------|
| ThousandSons a distance 1        | 3     |
| autre Chaos a distance 1         | 4     |
| non-Chaos a distance 1           | 5     |
| ThousandSons a distance 2        | 6     |
| autre Chaos a distance 2         | 7     |
| non-Chaos a distance 2           | 8     |
| le caster lui-meme (distance 0)  | 10    |

Deux consequences que le port historique ratait :

  * **La DISTANCE domine la faction** (poids 3 contre 1). Un allie **non-Chaos a distance 1** (5)
    passe DEVANT un **ThousandSons a distance 2** (6). Le tri lexicographique
    `(prio_faction, distance, id)` choisissait l'inverse. **C'est le scenario discriminant du lot**,
    monte et mesure au §4.
  * Le terme `Owner` (`range*3 + 4 = 10`) est calibre pour depasser strictement le pire score
    possible d'un autre candidat (`3*range + 1 + 1 = 8`) : le caster est **toujours dernier**, ce qui
    realise le « lastly casting it on himself ». Ce n'est pas un palier, c'est une penalite calibree.

### Piege de portage : le trait `Chaos` n'est PAS dans le gameconfig

`GC.unit('thousSorcerer')['traits'] = ['Hero','WeaverOfFate','Flying','Psyker']` — **aucun `Chaos`**.
Sur 669 unites du gameconfig, **ZERO** ne porte le trait `Chaos`.

Le trait de grande alliance est **injecte par la couche meta au moment de construire la
BattleConfiguration** : `data/seed-bc.json` -> `Units[*].Traits` pour `ultraTigurius` vaut
`["Imperial","Hero","Psyker"]` la ou le gameconfig ne donne que `["Hero","Psyker"]`. La table de
correspondance est `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` :

    "Imperial" -> 0x1a  = 26   = UnitTrait.Imperial
    "Xenos"    -> 0x3ee = 1006 = UnitTrait.Xenos
    "Chaos"    -> 0x7ea = 2026 = UnitTrait.Chaos

Or `UnitContext.from_snapshot` remplit `ctx.traits` depuis le **gameconfig** (`traits=list(cfg.get(
"traits") or [])`). Porter `HasTrait(It, Chaos)` naivement contre `ctx.traits` donnerait donc un
predicat **uniformement FAUX** — et ce ne serait pas inerte : un +1 constant sur tous les candidats
changerait le classement des non-Chaos face aux Chaos.

Le port derive donc le trait d'alliance de `GrandAllianceId`, comme le fait la BC, **via le maillon
deja porte** `grand_alliance_of` (`engine/entities/effects/loki/dark_angels_passives.py`) — le meme
que les passifs Dark Angels, dont la docstring documente deja ce piege mot pour mot. La constante
`CHAOS_FACTIONS` locale a `arcane_shield.py` (5 factions Chaos codees en dur) a ete SUPPRIMEE : elle
coincidait avec la verite, mais n'etait pas la source native, et dupliquait un maillon existant.

`IsSameFaction` reste, lui, un test de `FactionId` (helper porte `_faction_id`).

### Residu RNG assume

`Randomize(pool)` = `PickRandomAmountSelector(amount = 0x7fffffff)` (cf. `case-130-pick-randomly-rng.md`)
consomme `len(pool)` tirages et melange le pool AVANT le tri stable. Les ex aequo de score sont donc
departages **au hasard** cote natif.

**Choix du port : collapse deterministe** (ordre d'id croissant), meme choix et meme motif que
`genestealer.py`. Consommer `len(pool)` tirages ici decalerait le flux PRNG partage en aval
(crit/block/degat suivants) sur un chemin qu'aucune mesure ne valide, et le port historique ne les
consommait pas davantage — le collapse n'introduit donc aucune regression. Ce qui reste non fidele :
le DEPARTAGE des ex aequo (jamais le NOMBRE de tirages, qui est nul des deux cotes).

### Residus non couverts

  * `AverageDistance` est approxime par la distance hex du board (`_hex_dist`, BFS sur
    `board.neighbours`) et non par `IdunBattle.Entities.Components.PositionComponent$$Distance` —
    residu commun a tout le port, deja documente (`case-122-hits-malus-ability-vector.md`).
  * `CreateShield(..., stackable = true)` : le 7e argument natif est lu mais le port empile via
    `ShieldComponent.add_or_update_shield`, dont la semantique de cumul same-source n'a pas ete
    re-confrontee ici (inchangee par ce lot).

---

## 3. Ce qui a ete porte

1. `ArcaneShieldAbility.event_id` -> `EventTriggerType.ArrivedAtFinalTile`. Aucune autre ligne de
   dispatch n'a bouge : le vecteur `arrived_at_final_tile_triggers` existait et etait deja emis aux
   deux points natifs. Les commentaires qui affirmaient le contraire (`dispatch/registry.py`,
   `dispatch/move_death.py`, `operations/turnflow.py`, `abilities/behaviours/effects.py`) sont
   corriges — c'etaient des fausses verites lisibles.
2. `_arcaneshield_target` decompose en trois fonctions mirror : `_arcaneshield_candidates` (le pool
   `SurroundingFriends -> UnitsWithoutTrait -> Randomize op_Addition Caster`), `_arcaneshield_score`
   (les quatre termes `$$Distance` / `$$Faction` / `$$Chaos` / `$$Owner`), et le
   `First(SortByFormula(..., ascending))` lui-meme.
3. `range` n'est plus une constante gravee : il est lu de `ArcaneShield.constants.range`
   (`GetNumberConstant(config, 0x16)`), ce qui suit aussi la penalite `Owner` (`range*3 + 4`).
4. Le volet `Targetable` d'`OnlyAliveAndTargetable` est porte (reutilise `_is_targetable`, mesure
   live du port LionHelm) — il ne l'etait pas.

## 4. Mesure (probe `scripts/python/probe_n1_arcane_shield_target.py`, runner MC1_67 / seed 777)

Montage : `thousSorcerer` (owner) + `thousTzaangor` (ThousandSons) + `worldJakhal` (WorldEaters) +
`astraDreir` (AstraMilitarum) vs `necroWarden`. `range = 2`, penalite owner = `10`.

**Vecteur** — bouclier `5483`, duree `2` tours (`ConvertRoundsToTurns(TurnsFromRounds(1))`, 2 joueurs) :

    FinishUnitTurnOperation (n'a PAS bouge) : newly_arrived=True  -> 1 pose  (shield 0 -> 5483)
    after_move_triggers     (a bouge)       :                        1 pose  (shield 0 -> 5483)
    puis FinishUnitTurnOperation            : newly_arrived=False -> 0 pose  (shield 5483 -> 5483)

**Classement** — score decompose par candidat, et cible du port courant vs tri historique :

| configuration                                      | scores (role : total)                              | port | historique | verdict |
|----------------------------------------------------|----------------------------------------------------|------|------------|---------|
| `non_chaos` d1, `same_faction` d2, `other_chaos` d2 | non_chaos 5, same 6, other 7, owner 10             | **non_chaos** | same_faction | **DIVERGE** |
| tous a d2                                          | same 6, other 7, non_chaos 8, owner 10             | same_faction | same_faction | identique |
| `other_chaos` d1, `non_chaos` d1, `same_faction` d2 | other 4, non_chaos 5, same 6, owner 10             | **other_chaos** | same_faction | **DIVERGE** |
| `non_chaos` d1 seul                                | non_chaos 5, owner 10                              | non_chaos | non_chaos | identique |

**2 configurations sur 4** ou le port historique se trompait de cible.

## 5. Gardes

`scripts/python/tests/engine/runner/test_arcaneshield_vector_live.py` (6 tests) sur le montage
`arcaneshield_stage` (fixture nommee, `tests/conftest.py` -> `tests/engine/runner/_arcane_shield_stage.py`) :
fin de tour sans deplacement, non-doublement move+cloture, les trois configurations de classement
(parametrees), et le caster comme dernier recours (les deux moities : le pire ami possible le bat ;
le rayon vide le retient).

Le test « fin de tour sans deplacement » a ete vu ROUGE en re-posant `event_id =
EventTriggerType.UnitAfterMove` :

    AssertionError: fin de tour SANS deplacement : ArcaneShield n'a PAS ete accorde
    (grants=[], shield allie 0->0). Le trigger natif est On(0x1c=ArrivedAtFinalTile), emis par
    FinishUnitTurnOperation$$Execute quand l'unite n'a pas bouge -- un port route sur
    On(4=UnitAfterMove) rate ce cas.
    assert 0 == 1
