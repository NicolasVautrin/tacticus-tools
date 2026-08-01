"""`1511 PrimarchOfTheFirstLegion` -- le SECOND (et dernier) declencheur de `TransferHit` (#418).

Passif de `darkaBossLion` (Lion El'Jonson, npc). i2 : le Lion redirige une partie des coups qu'il
recoit vers un allie Dark Angels adjacent, qui gagne en echange un bonus de degat.

RE complete : `docs/rl/case-411-r3-primarch-of-the-first-legion.md`. Ce module porte l'arbre.

## 1. L'arbre natif, lu

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PrimarchOfTheFirstLegionAbility$$CreateTrigger` :

    On(EventTriggerType.PreAttackDamageHit = 7, ownerNeedsToBeAlive: <litteral 1>)
  & AreEqual(Owner@DSLSelectors+0x30, Target@DSLSelectors+0x60)
  & AmountIsOdd(CurrentHitIndex)

⚠ DEUX ecarts avec `1109 DrawFire`, tous deux LUS et tous deux structurants :

  * `AreEqual` **SANS negation** -- le PORTEUR **EST** le defenseur. DrawFire, lui, porte
    `!AreEqual` (le porteur est un ALLIE ADJACENT du defenseur). La detection est donc ici
    strictement locale : « le defenseur porte-t-il 1511 ? », sans balayage du voisinage ;
  * `ownerNeedsToBeAlive` est un **litteral `1`** dans l'appel a `DSLTriggers$$On`, pas le retour
    d'un virtuel de classe (slot `+0x298`) comme chez DrawFire. Le porteur vivant est donc EXIGE
    par lecture, pas par choix conservateur.

⚠ ET UNE REFUTATION : `docs/rl/case-411-…` §6.2 ecrivait « `PrimarchOfTheFirstLegion` n'a pas
d'`AmountIsOdd` -- sa garde reste NON LUE ». **C'est faux** : `CreateTrigger` porte bien
`AmountIsOdd(CurrentHitIndex)`, troisieme conjoint. La garde anti-recursion est donc EXACTEMENT
celle de DrawFire (cf. §3).

`...PrimarchOfTheFirstLegionAbility$$CreateBehaviour` :

    target = Cache(
               First(
                 SortByFormula(
                   Randomize(UnitsFromFaction(AdjacentFriends(Owner@+0x30, unique:1, selType:3),
                                              faction: 0xa = DarkAngels, selType:3)),
                   If(Contains(GetPersistentDataListAsEntities(<this>, Owner@+0x30, <key>),
                               It@DSLSelectors+0x68),
                      <DSLFormulas+0x18 = 0>, <DSLFormulas+0x20 = 1>),
                   ascending: 0 -> DESCENDANT),
                 amount: 1, ignoreForcedTargets: 0),
               matchAbilityEntities: 1)

    return If(AmountIsGreaterThanZero(target),
              ( Inform({0x83: TriggerBoolNumber(AmountIsEqual(CurrentHitIndex,
                                                             <DSLFormulas+0x20 = 1>))})
              & TransferHit(Caster@+0x48, Target@+0x60, target, <this>)
              & IfAlive(target,
                          AddEffect(0x5f3 = 1523, <abilityStateRef>, target,
                                    TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds)))
                        + AddToPersistentDataList(<this>, Owner@+0x30, Get(<key>),
                                                  EntityId(target))) ),
              null)

Les deux constantes de `DSLFormulas` sont LUES dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor`,
qui construit cinq formules-constantes : `+0x18 = 0`, `+0x20 = 1`, `+0x28 = 2`, `+0x30 = 100`,
`+0x38 = -1`. Le `If` de tri rend donc **0 pour un allie DEJA servi, 1 sinon** ; combine au tri
DESCENDANT, cela remonte les allies **pas encore servis**, l'ordre du melange etant preserve au
sein de chaque classe (`OrderByDescending` LINQ est STABLE).

## 2. Le RNG -- ce qui rendait ce port faux-ou-juste de facon INVISIBLE

`IdunBattleLogic.Entities.DSLSelectors$$Randomize(x)` construit
`IdunBattle.Entities.Selectors.PickRandomAmountSelector` avec
`requestedAmount = 0x7fffffff`, `allowDuplicates = false`, `maxDuplicatesAllowed = 0x7fffffff`,
`ignoreForcedTargets = false`. Et `...PickRandomAmountSelector$$Select` :

    candidates = source.Select(ctx).ToList()
    picked = new List<T>()
    if (!ignoreForcedTargets) AddForcedTargetsAndUpdateCandidates(...)     # no-op sans forced target
    for (i = picked.Count ; i < requestedAmount ; i++) {
        if (candidates.Count < 1) return picked                            # LA sortie effective
        idx = random.Next(0, candidates.Count)                             # <-- LE TIRAGE
        picked.Add(candidates[idx])
        if (!allowDuplicates) candidates.RemoveAt(idx)
    }

`requestedAmount` valant `int.MaxValue`, la boucle ne s'arrete QUE par l'epuisement des candidats :
un pool de **N** allies consomme donc **N tirages**, de bornes DECROISSANTES `N, N-1, …, 1`.

⚠ **Le dernier tirage n'est PAS court-circuite.** `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$
IdunBattle.Utils.PRNG.IPseudoRNG.Next(min, max)` est `[min, max)` et commence par
`genrand_int32()` quel que soit le range -- `Next(0, 1)` (range 1, puissance de 2) consomme un
`genrand_int32` et rend toujours `0`. Un pool d'**UN SEUL** allie consomme donc **UN tirage**, dont
la valeur ne discrimine rien. C'est exactement le piege que nomme la tranche : un port qui rendrait
la bonne cible en sautant ce tirage decalerait tout le flux aleatoire en aval, et le symptome
n'apparaitrait PAS sur la valeur mesuree.

Un pool **VIDE** consomme **zero** tirage (`candidates.Count < 1` sort avant le premier `Next`).

Le port ne reecrit pas cette boucle : il passe par le noeud `PickRandomly`, qui delegue au foyer
UNIQUE `runner/abilities/loki/splash.py::_pick_randomly_n` (mirror 1:1 deja valide live, #130/#215).

### Pourquoi le `Cache` ne fait PAS economiser de tirages entre deux coups

`IdunBattleLogic.Entities.DSLSelectors$$Cache(x, matchAbilityEntities: 1)` ->
`IdunBattle.Entities.Selectors.CacheSelector$$Select`, qui memoise dans un
`Dictionary<AbilityEntities, List<T>>` keye par le CONTEXTE. Or `IdunBattle.Entities.Abilities.
AbilityEntities$$.ctor` (33 parametres, tous nommes dans la metadonnee) place **`hitIndex` a
`+0x108`** : la cle change donc a CHAQUE coup. Le cache mord a l'interieur d'un declenchement --
et c'est tout son role, `target` etant lu SIX fois dans l'arbre (condition du `If`, `TransferHit`,
`AddEffect`, `IfAlive`, `EntityId`, et la cible du `AddToPersistentDataList`) -- mais jamais entre
deux coups. **Une evaluation, donc N tirages, par declenchement.**

Cote port, l'arbre est rebati a chaque declenchement (`primarch_transfer_target_selector()`), donc
le `Cache` a slot unique du noeud porte est EXACTEMENT equivalent au dict natif sur ce chemin.

## 3. L'anti-recursion -- HERITEE, comme DrawFire

`IdunBattle.Operations.TransferHitOperation$$Execute` pose `opts[+0x2E] = 1` (`isOutsideAttack`,
le parametre PORTE ce nom dans la metadonnee de `ADamageOperation$$GetCurrentAttackOrDefault`) :
l'attaque de transfert est SEPAREE, son compteur de coups repart a **0**. `AmountIsOdd(0)` est
faux -> le coup transfere ne peut pas retransferer. C'est la garde NATIVE, propre au predicat de
parite, pas un garde-fou ajoute -- et le residu « garde NON LUE » de `case-411` §6.2 tombe.

## 4. Ce qui n'est PAS porte ici (residus NOMMES)

  * **`PrimarchOfTheFirstLegion_EndTurnAbility`** (le `ClearAllPersistentData(<this>, Owner@+0x30)`
    qui PURGE la memoire anti-repetition) : son `CreateBehaviour` est lu, mais son **`CreateTrigger`
    est ABSENT des DEUX tables de symboles** (`frida/methods.tsv` ET `ghidra/functions.tsv`) --
    corps deduplique, la classe heritant directement de `IdunBattle.Entities.Abilities.
    BaseTriggeredAbility` (lu dans `frida/classes.tsv`). L'EVENT n'est donc PAS lu, et poser le
    clear sur un event suppose serait une invention. Consequence BORNEE et unilaterale : la liste
    persistante ne se vide jamais, donc apres avoir servi tous les allies eligibles le tri
    `If(Contains, 0, 1)` rend 0 pour TOUS et redevient neutre -> le choix repasse au premier du
    melange. **Le ledger RNG est INCHANGE** (meme pool, meme compte de tirages) ; seul le CHOIX
    peut diverger apres saturation.
  * **`Inform({0x83: …})`** : ecriture de contexte DSL sans consommateur identifie, comme chez
    DrawFire. Non porte (le bus n'est pas modelise cote port).
  * **`AddForcedTargetsAndUpdateCandidates`** : `ignoreForcedTargets = false` fait entrer la branche,
    mais elle est un no-op sans `GetOnlyTargets` sur le caster -- non porte, verdict deja rendu par
    le foyer `_pick_randomly_n`.
  * **La collision `1109` x `1511` sur un MEME coup** : les deux abilities s'abonnent a `On(7)` et
    le natif evalue chaque abonne. Le port teste `1511` PUIS `1109` et s'arrete au premier qui
    transfere -- l'ordre d'abonnement natif n'est pas lu. Regime jamais atteint (il exigerait un
    porteur `DrawFire` adjacent a un porteur `1511` en train d'etre frappe).
  * **La face ABILITY** (`AbilityDamageOperation$$ExecuteHit`) : le cablage la couvre (meme
    intercepteur), elle n'est pas confrontee -- meme etat que `1109`.

ASCII only.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....entities.effect_type import EffectType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_faction import UnitFaction
from ....components import OwnerComponent, StatsComponent, UnitComponent

# `TriggeredAbilityType.PrimarchOfTheFirstLegion` = 0x5e7 ; l'effet pose vaut `EffectType` 0x5f3.
PRIMARCH_OF_THE_FIRST_LEGION = int(TriggeredAbilityType.PrimarchOfTheFirstLegion)      # 1511
PRIMARCH_EXTRA_DAMAGE = int(EffectType.PrimarchOfTheFirstLegion_ExtraDamage)           # 1523
ABILITY_ID = "PrimarchOfTheFirstLegion"                # la cle gameconfig (variables / constants)
DARK_ANGELS = UnitFaction.DarkAngels.name              # `UnitsFromFaction(0xa)` -- `Enum.ToString`

# La `dataKey` du sac persistant. Le natif passe une chaine litterale (`DSLFormulas$$Get(<DAT>)`)
# que le dump statique ne resout pas (globale initialisee au runtime). Elle est INOBSERVABLE : la
# cle du port est composite `(abilityOrEffect, dataKey)`, `1511` n'a qu'UNE dataKey, et les trois
# consommateurs (le selecteur, la feuille d'ajout, la purge) portent la MEME. On la nomme donc
# d'apres l'ability, comme `my_will_be_done_overlord.py`.
PERSISTENT_DATA_KEY = ABILITY_ID


def _carries_primarch(state, uid: int) -> bool:
    """MEME source que `make_hit_interceptor` / `_carries_draw_fire` : les passives MESUREES
    (`UnitContext.passive_abilities`, hierarchie 2) quand le canal a parle, sinon la derivation
    gameconfig par `visualId`. C'est ce qui rend une GREFFE
    (`catalog_inject.graft_passive_ability`) visible ici -- la SEULE voie de confrontation, le seul
    porteur (`darkaBossLion`) etant npc."""
    import gameconfig as GC
    e = state.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return False
    measured = getattr(sc.ctx, "passive_abilities", None)
    if measured is None:
        vid = getattr(sc.ctx, "visual_id", None)
        measured = list(((GC.unit(vid) or {}) if vid else {}).get("passiveAbilities") or [])
    return ABILITY_ID in (measured or [])


def _n_rounds(state, owner_id: int) -> int:
    """`GetNumberConstant(config, 0x45)` -- la constante `nrOfRounds` de l'entree gameconfig de
    `PrimarchOfTheFirstLegion` (`constants: {"nrOfRounds": "1"}`), passee a `TurnsFromRounds`.
    Absente -> 1, la seule valeur que le gameconfig porte."""
    import gameconfig as GC
    c = ((GC.ability(ABILITY_ID) or {}).get("constants") or {}).get("nrOfRounds")
    try:
        return int(c)
    except (TypeError, ValueError):
        return 1


def primarch_transfer_target_selector():
    """L'arbre de ciblage de `...PrimarchOfTheFirstLegionAbility$$CreateBehaviour` -- MIRROR 1:1
    (cf. l'en-tete §1). Rebati a chaque declenchement, comme le natif rebatit sa cle de `Cache`.

    `Owner()` retombe sur `ctx.caster`, et c'est EXACT ici : le contexte est monte avec le PORTEUR
    en caster (cf. `PrimarchTransfer._entities`).

    `AdjacentFriends(Owner, reference=Owner)` = la surcharge 4-args native
    `Friends(reference = X, Units(AdjacentTiles(X), unique, selType) - X, selType)` : la REFERENCE
    d'equipe EST le centre. On la passe explicitement bien que le collapse caster soit exact ici,
    pour citer la forme que le natif cite.

    L'ORDRE du pool est celui d'`IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select`
    (`OrderedSet` alimente par la requete de voisinage du `BattleQuery`, ordre d'insertion
    preserve), que `Units`/`Friends`/`UnitsFromFaction` ne retrient PAS -- c'est le `order="adjacent"`
    de `_within` (R28-1). Il DECIDE qui est pioche : `Randomize` tire un INDEX dans cette liste."""
    from .....entities.formulas import If as FIf
    from .....entities.selectors.accessors import Owner, Subject
    from .....entities.selectors.geometry import Cache, PickRandomly
    from .....entities.selectors.units import (AdjacentFriends, EntitiesFromPersistentDataList,
                                               First, SortByFormula, UnitsFromFaction)
    from .....entities.triggers import Contains

    it = Subject()                       # `It@DSLSelectors+0x68` = l'element courant du tri
    pool = UnitsFromFaction(AdjacentFriends(Owner(), reference=Owner()), DARK_ANGELS)
    # `Randomize(x)` = `PickRandomly(x, amount=int.MaxValue, allowDuplicates=false,
    # maxDuplicatesAllowed=int.MaxValue, ignoreForcedTargets=false)` -- les cinq litteraux sont ceux
    # que `DSLSelectors$$Randomize` ecrit lui-meme (cf. en-tete §2).
    shuffled = PickRandomly(pool, amount=0x7FFFFFFF, allow_duplicates=False,
                            max_duplicates=0x7FFFFFFF, ignore_forced_targets=False)
    already = EntitiesFromPersistentDataList(PRIMARCH_OF_THE_FIRST_LEGION, Owner(),
                                             PERSISTENT_DATA_KEY)
    # `If(Contains(deja_servis, It), <+0x18 = 0>, <+0x20 = 1>)` + tri DESCENDANT -> les allies
    # PAS ENCORE servis passent devant, a ordre de melange preserve (tri stable).
    rank = FIf(Contains(already, it), Const(0), Const(1))
    return Cache(First(SortByFormula(shuffled, rank, ascending=False)))


def primarch_reward_tree(target, rounds: int):
    """La branche `IfAlive` de `...$$CreateBehaviour` : ce que l'allie recoit APRES avoir encaisse.

        IfAlive(target, AddEffect(0x5f3, <abilityStateRef>, target, TurnsFromRounds(nrOfRounds))
                      + AddToPersistentDataList(<this>, Owner@+0x30, Get(<key>), EntityId(target)))

    ⚠ `IfAlive` est evalue APRES `TransferHit` : un allie que le coup transfere a TUE ne recoit ni
    l'effet ni la memorisation. L'identite `IfAlive(sel, then) == If(IsAlive(sel), then)` est celle
    du natif (`DSLBehaviors$$IfAlive` appelle `DSLTriggers$$IsAlive` puis `DSLBehaviors$$If`).

    ⚠ `source_from_target=True` est LU, pas suppose : la surcharge
    `DSLBehaviors$$AddEffect(effectType, abilityState, targets, turns)` -- celle que Primarch
    appelle, 4 arguments -- passe litteralement **`0`** en parametre `source` du
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor` (la surcharge 5-args, elle, en pose
    un explicite). Selecteur source nul => la source EST la cible."""
    from .....entities.behaviours import If as BIf, Seq
    from .....entities.formulas import EntityId
    from .....entities.selectors.accessors import Owner
    from .....entities.triggers import IsAlive
    from ....abilities.behaviours import AddEffect, AddToPersistentDataList

    reward = Seq(AddEffect(PRIMARCH_EXTRA_DAMAGE, "PrimarchOfTheFirstLegion_ExtraDamage", target,
                           duration_rounds=int(rounds), source_from_target=True),
                 AddToPersistentDataList(PRIMARCH_OF_THE_FIRST_LEGION, Owner(), PERSISTENT_DATA_KEY,
                                         EntityId(target)))
    return BIf(IsAlive(target), reward)


class PrimarchTransfer:
    """L'accroche per-coup de `1511`, JUMELLE de `DrawFireTransfer`, branchee dans le meme point
    d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (l'etape 5, relecture du
    `Nullable<AttackHit>` juste apres l'emission d'`On(7)`).

    Comme pour `1109`, `TransferHit` reste IMPERATIF (re-entree dans `AttackDamageOperation`) et
    seul le CIBLAGE est un arbre DSL : la frontiere natif est le `.Execute` de la feuille.

    Le natif execute le behaviour DANS le dispatch d'`On(7)`, donc AVANT que le coup courant ne
    soit resolu -- d'ou l'ordre : tirages du `Randomize`, puis l'attaque de transfert (crit +
    resolve + block/evasion sur l'allie), puis seulement le resolve `[0,0]` du coup original."""
    __slots__ = ("state", "attacker_id", "defender_id", "events")

    def __init__(self, state, attacker_id: Optional[int], defender_id: Optional[int]):
        self.state = state
        self.attacker_id = attacker_id
        self.defender_id = defender_id
        self.events: list[dict] = []

    def _matches(self, hit_index: int) -> bool:
        """Les TROIS conjoints de `CreateTrigger` que le port doit tester ici (`On(7)` etant le
        point d'accroche lui-meme) :

          * `AreEqual(Owner, Target)` -> le DEFENSEUR porte 1511 ;
          * `ownerNeedsToBeAlive` (litteral 1) -> il est vivant ;
          * `AmountIsOdd(CurrentHitIndex)` -> l'index du coup est IMPAIR (0-based, c'est le
            `OngoingAttack+0x30` que threade `damage_hits.py`).

        Aucun gate `AreEnemies` : contrairement a DrawFire, `CreateTrigger` n'en porte pas. Un
        allie qui frappe le porteur (friendly fire) declencherait donc aussi -- c'est LU."""
        if self.state is None or self.attacker_id is None or self.defender_id is None:
            return False
        if int(hit_index) % 2 == 0:                       # AmountIsOdd(CurrentHitIndex)
            return False
        d = self.state.get_entity(int(self.defender_id))
        if d is None or d.get_component(OwnerComponent) is None:
            return False
        uc = d.get_component(UnitComponent)
        if uc is not None and not uc.alive:               # `ownerNeedsToBeAlive` = litteral 1
            return False
        return _carries_primarch(self.state, int(self.defender_id))   # AreEqual(Owner, Target)

    def _entities(self):
        """L'`AbilityEntities` du behaviour, montee avec le PORTEUR en caster.

        Le natif y met `caster = l'ATTAQUANT`, `target = le DEFENSEUR`, `owner = le PORTEUR`. Le
        gate `AreEqual(Owner, Target)` du trigger rend `owner == target == le defenseur`, et le
        port n'a pas de slot `owner` distinct (`Owner()` retombe sur `ctx.caster`) : on monte donc
        le contexte sur le DEFENSEUR, ce qui rend `Owner()` EXACT.

        Le `caster` natif (l'attaquant) n'est lu par AUCUN noeud de l'arbre porte -- il ne sert
        qu'au `TransferHit(Caster, …)`, qui est la feuille imperative et recoit `attacker_id`
        en argument. L'ecart est donc INERTE, et il est nomme ici plutot que masque."""
        from ....abilities.behaviours import entities_from_state
        return entities_from_state(self.state, int(self.defender_id), int(self.defender_id))

    def transfer(self, hit_index: int) -> bool:
        if not self._matches(hit_index):
            return False
        entities = self._entities()
        ectx = ExecutionContext(state=self.state, rng=self.state.rng)
        # L'arbre est evalue ICI : c'est ce qui consomme les N tirages du `Randomize` (cf. §2).
        # Le `Cache` du noeud garantit une SEULE evaluation malgre les six lectures qui suivent,
        # exactement comme le dict keye par `AbilityEntities` du natif.
        # `n0` : le compteur du MT AVANT l'evaluation, pour ventiler le cout du CIBLAGE dans
        # l'evenement (observabilite pure -- c'est ce que le probe confronte au ledger attendu).
        n0 = int(getattr(self.state.rng, "call_count", 0))
        target = primarch_transfer_target_selector()
        picked = [u for u in (target.evaluate(entities) or []) if (u or {}).get("id") is not None]
        select_cost = int(getattr(self.state.rng, "call_count", 0)) - n0
        # `If(AmountIsGreaterThanZero(target), …, null)` : pool vide -> le behaviour ne fait RIEN.
        # (Le `Randomize` n'a alors consomme aucun tirage -- sa boucle sort avant le premier `Next`.)
        if not picked:
            return False
        ally = int(picked[0]["id"])
        from ...damage import AttackDamageOperation      # lazy : cycle operations <-> triggers
        res = AttackDamageOperation.execute(
            self.state, int(self.attacker_id), ally,
            # `opts[+0x28]` + `Nullable<int> hits` vide -> le coup transfere vaut 1 coup.
            skip_hit_count_query=True,
            triggering_ability=PRIMARCH_OF_THE_FIRST_LEGION,
            allow_dead_caster=True)
        # `IfAlive(target, AddEffect + AddToPersistentDataList)` -- APRES le transfert (cf.
        # `primarch_reward_tree`). Le contexte est re-monte : l'etat a change (l'allie a pu mourir).
        rewarded = self._reward(ally)
        self.events.append({"ability": PRIMARCH_OF_THE_FIRST_LEGION, "carrier": ally,
                            "hit": int(hit_index),
                            "transferred": int((res or {}).get("total") or 0),
                            # `select_cost` = ce que le CIBLAGE a coute au MT (compteur `call_count`,
                            # qui avance de 2 par `next_internal`). Le natif tire une fois par
                            # candidat -> `select_cost / 2` DOIT valoir la taille du pool.
                            "select_cost": select_cost,
                            **rewarded})
        return True

    def _reward(self, ally: int) -> dict:
        """La branche `IfAlive` du natif, jouee APRES le transfert.

        ⚠ Le contexte est RE-MONTE (l'etat a change : l'allie a pu mourir du coup transfere) et
        l'allie deja elu y entre par le slot `Target`. C'est ce qui evite de RE-EVALUER l'arbre --
        donc de RE-TIRER les N tirages du `Randomize`. Le natif obtient la meme economie par son
        `Cache` (meme `AbilityEntities`, donc meme cle) ; ici la memoisation est explicite parce
        que le port re-monte le contexte."""
        from .....entities.selectors.accessors import Target
        from ....abilities.behaviours import entities_from_state
        entities = entities_from_state(self.state, int(self.defender_id), int(ally))
        ectx = ExecutionContext(state=self.state, rng=self.state.rng)
        primarch_reward_tree(Target(), _n_rounds(self.state, self.defender_id)).execute(entities, ectx)
        placed = [p for (n, p) in ectx.emitted if n == "AddEffect"]
        added = [p for (n, p) in ectx.emitted if n == "AddToPersistentDataList"]
        return {"effect": bool(any(p.get("placed") for p in placed)),
                "remembered": [u["unit"] for p in added for u in (p.get("added") or [])]}
