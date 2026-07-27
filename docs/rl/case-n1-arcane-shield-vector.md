# N1 — `ArcaneShield` (Thaumachus / `thousSorcerer`) : vecteur `On(0x1c)` + formule de tri additive

**Etat : RE TERMINEE, PORT NON ENCORE ECRIT.** Ce document fige la lecture du decompile
(build `gqfc5mff6c`) avant toute edition de code, pour que rien ne soit a re-lire.

---

## 1. Critere binaire n°1 — le bouclier est-il accorde en fin de tour SANS deplacement ?

**OUI cote natif. Le port dit NON aujourd'hui.**

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$CreateTrigger` (lu verbatim) :

    On(0x1c, ownerNeedsToBeAlive = 1)
      op_BitwiseAnd get_OwnerIsActor
      op_BitwiseAnd get_OwnerIsCaster

`0x1c = 28 = EventTriggerType.ArrivedAtFinalTile`. Il n'y a **aucune** branche `On(4=UnitAfterMove)`
dans le trigger natif. Le port
(`engine/runner/operations/triggers/loki/arcane_shield.py`, `event_id = EventTriggerType.UnitAfterMove`)
est donc route sur le MAUVAIS event, et la docstring l'assumait deja comme une approximation.

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

Cote port, le vecteur EXISTE DEJA, porte et valide : `arrived_at_final_tile_triggers` (module
`triggers/dispatch`, appele (a) en queue d'`after_move_triggers` et (b) par
`FinishUnitTurnOperation.execute` avec `gate_already_consumed=True`). Le travail n'est donc PAS de
construire un vecteur, mais de **recabler `ArcaneShieldAbility.event_id`** de
`EventTriggerType.UnitAfterMove` vers `EventTriggerType.ArrivedAtFinalTile`.

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

**Mais le port se trompe quand meme, autrement, et plus gravement** : il n'y a **AUCUN ordre
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

Deux consequences que le port actuel rate :

  * **La DISTANCE domine la faction** (poids 3 contre 1). Un allie **non-Chaos a distance 1** (5)
    passe DEVANT un **ThousandSons a distance 2** (6). Le port, qui trie lexicographiquement
    `(prio_faction, distance, id)`, choisit l'inverse. **C'est le scenario discriminant a monter
    live.**
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
predicat **uniformement FAUX** — un +1 constant sur tous les candidats, donc inerte... sauf qu'il
n'est PAS inerte : il changerait le classement des non-Chaos face aux Chaos. Le port fidele doit
deriver le trait d'alliance de `GrandAllianceId` (mirror de `GrandAlliance$$GetTrait`), comme le fait
la BC. C'est ce que le port actuel approxime avec sa constante `CHAOS_FACTIONS` (5 factions Chaos
codees en dur) — approximation qui *coincide* avec la verite tant que `GrandAllianceId == "Chaos"`
equivaut a « faction dans cette liste », mais qui n'est pas la source natif.

`IsSameFaction` reste, lui, un test de `FactionId` (helper porte `_faction_id`).

### Residu RNG identifie

`Randomize(pool)` = `PickRandomAmountSelector(amount = 0x7fffffff)` (cf. `case-130-pick-randomly-rng.md`)
consomme `len(pool)` tirages et melange le pool AVANT le tri stable. Les ex aequo de score sont donc
departages **au hasard** cote natif, la ou le port departage par `eid`. A trancher au moment du
port : collapse deterministe (comme `genestealer.py`, qui l'assume explicitement) ou mirror RNG
(`spawn.py::_randomize`). Le choix a une consequence sur le flux PRNG en aval.

---

## 3. Prochain geste (a la reprise, apres retour de la session Frida)

1. `git fetch origin && git rebase origin/master` — `#169` a scinde `dispatch.py` en package
   `triggers/dispatch/` (`registry.py` / `core.py` / `attack.py` / `ability.py` / `move_death.py` /
   `turn.py`). Re-localiser au grep : l'entree `TRAIT_TRIGGERS["ArcaneShield"]` et le vecteur
   `arrived_at_final_tile_triggers`.
2. Recabler `ArcaneShieldAbility.event_id` -> `EventTriggerType.ArrivedAtFinalTile` (aucune autre
   ligne de dispatch ne devrait bouger : le vecteur existe et est deja emis aux deux points).
3. Remplacer le tri lexicographique de `_arcaneshield_target` par le **score additif** ci-dessus,
   avec le trait `Chaos` derive de `GrandAllianceId`.
4. Fixture nommee reutilisable (roster ThousandSons + 1 autre Chaos + 1 non-Chaos, positions
   drivees, board fixe, seed fixe) + garde live :
   (a) owner qui bouge PUIS finit son tour -> UN seul bouclier ;
   (b) owner qui finit son tour SANS bouger -> bouclier accorde (doit etre ROUGE avant le fix) ;
   (c) multi-amis -> non-Chaos a distance 1 prefere a ThousandSons a distance 2.
5. Corriger l'entree N1 de `docs/rl/port-residuals-inventory.md` (cette seule ligne).
