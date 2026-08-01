"""`1109 DrawFire` -- le TRANSFERT DE COUP, et la route de block GARANTI qu'il ouvre (#411).

i2 (`DrawFire`, passif de `blackNpc2Terminator` / `blackSmnTerminator`) : « Any friendly adjacent
units hit by enemy attacks have half of the hits (rounded down) hit the Terminator instead. »

RE complete : `docs/rl/case-411-transfer-hit-guaranteed-block.md`. Resume de ce qui est porte ici.

## 1. L'arbre natif

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DrawFireAbility$$CreateTrigger` --

    On(EventTriggerType.PreAttackDamageHit = 7, ownerNeedsToBeAlive: <slot 0x298 de la classe>)
  & !AreEqual(Owner@DSLSelectors+0x30, Target@+0x60)
  &  AreFriends(Owner@+0x30, Target@+0x60, ByCurrentTeam, anyEntity: false)
  &  IsAdjacent(Owner@+0x30, Target@+0x60, UnitSelectionType.OnlyTargetable = 2)
  &  AreEnemies(Caster@+0x48, Target@+0x60, ByCurrentTeam)
  &  AmountIsOdd(CurrentHitIndex)                    <-- « half of the hits (rounded down) »

`...DrawFireAbility$$CreateBehaviour` --

    Inform({ 0x83 : TriggerBoolNumber(AmountIsEqual(CurrentHitIndex, <DSLFormulas+0x20>)) })
  & TransferHit(caster: Caster@+0x48, originalTarget: Target@+0x60, transferTarget: Owner@+0x30)

Sur le vecteur `On(7)` emis par `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`,
l'`AbilityEntities` porte **caster = l'ATTAQUANT** et **target = le DEFENSEUR** (meme couple que
`On(6)`, cf. `harlequins_panoply.py`). Les cinq gates se lisent donc : le PORTEUR n'est pas le
defenseur, il est son ALLIE, il lui est ADJACENT, l'attaquant leur est ENNEMI, et l'index du coup
courant est IMPAIR.

`CurrentHitIndex` = `OngoingAttack+0x30` (`IdunBattle.Entities.Formulas.CurrentHitIndexFormula$$
Calculate`), le compteur PERSISTANT de l'attaque -- exactement le `hit_index0 + i` que threade
`operations/damage_hits.py`. 0-based : les coups transferes sont donc 1, 3, 5 d'une serie de 6,
soit bien la MOITIE ARRONDIE VERS LE BAS.

## 2. Ce que fait `TransferHit`, et pourquoi il ne boucle pas

`IdunBattle.Operations.TransferHitOperation$$Execute(caster, originalTarget, transferTargets,
abilityOrEffect)` LIT-PUIS-EFFACE le `Nullable<AttackHit>` de `UnitComponent+0x98` du defenseur
(le `PendingHit` que `ExecuteHit` vient d'y poser), puis, pour chaque cible de transfert :

    opts = new AttackDamageOptions(new HitDamage(hit.damage))
    opts[+0x10] = Nullable<DamageProfileType>(hit.damageProfile)
    opts[+0x28] = 1 ; opts[+0x2E] = 1 ; opts[+0x50] = 1
    result.Combine( processor.<slot 0x3c AttackDamage>(caster, t, abilityOrEffect, opts) )

Les trois octets, nommes par leur LECTEUR UNIQUE (cf. la fiche §6.2) :
  * `+0x28` -> `AttackDamageOperation$$GetAttackHits` sort AVANT la requete de modificateurs de
    nombre de coups ; combine au `Nullable<int> hits` laisse VIDE par le ctor, le coup transfere
    vaut **exactement 1 coup**. C'est le `skip_hit_count_query` de `_Normal.execute`.
  * `+0x2E` -> `ADamageOperation$$GetCurrentAttackOrDefault` : le parametre PORTE le nom
    `isOutsideAttack` dans la metadonnee (slot 201 au lieu de 200). Le coup transfere s'execute
    dans une attaque SEPAREE, dont le compteur de coups repart a 0.
  * `+0x50` -> gate d'`ExecuteAdditionalHitsWithoutDamageProfileType`.

⚠ **AUCUN des trois n'interdit la re-transmission.** Le dispatch `On(7)` du coup transfere est
inconditionnel. Ce qui rompt la chaine est le prédicat `AmountIsOdd(CurrentHitIndex)` : l'attaque
separee ouverte par `+0x2E` repart a l'index **0**, qui est PAIR. Le port herite exactement de
cette garde -- la sous-attaque est lancee avec le `hit_index0` par defaut (0), donc son unique
coup ne peut pas retransferer. La garde est donc PROPRE AU PREDICAT DE L'ABILITY, pas au
mecanisme : une ability de transfert sans gate de parite bouclerait.

## 3. La base de degat du coup transfere -- AUCUN second tirage

`IdunBattle.Core.HitDamage$$.ctor(damage)` (surcharge a UN argument, dont `TransferHit` est le
SEUL appelant de code) pose `min = max = damage`. Or `HitDamage$$GetDamage` commence par
`if (min == max) return min` : sortie immediate, le PRNG n'est jamais touche. La base est donc
`hit.damage`, la valeur de tete d'`ExecuteHit` sur la cible ORIGINALE -- pour une attaque normale,
la struct y est degeneree `(Attack, Attack)`, donc la **stat Attack brute**, pre-armure et
pre-percage. Elle repasse ensuite TOUT le pipeline contre le PORTEUR (spread, percage, armure,
%-mods, limites) : c'est exactement ce que recalcule `_reduced_bounds` de `damage_ops/normal.py`
depuis `ctx.stat(StatType.ATTACK)`. D'ou le port par RE-ENTREE dans `AttackDamageOperation.execute`
plutot que par un montant recopie -- aucun scalaire n'est ajuste.

Le coup transfere **peut criter** : rien dans les options ne pose `+0x29` (never crit) ni `+0x2c`
(always crit), donc son `ExecuteHit` tire son `RollCritical` sur le porteur.

## 4. Cote cible ORIGINALE : `DealDamageInfo[+0x1D]`

La relecture d'`UnitComponent+0x98` rend `!HasValue` (le `PendingHit` vient d'etre efface) ->
degat 0, `critInfo = {0,0,0}`, `DealDamageInfo[+0x1D] = 1`. `CalculateDamageOperation` route alors
vers `ApplyBlockDamage` (slot 4, arithmetique pur) avec `didBlock = 1` en dur : **zero tirage** de
block, **zero** d'evasion. Porte par `guaranteed_block` (`services/damage_combat.py`) et branche
par `_transferred` (`operations/damage_hits.py`).

## 5. Ce qui n'est PAS porte ici

* **`1511 PrimarchOfTheFirstLegion`** : PORTE et CONFRONTE depuis #418
  (`primarch_first_legion.py`, `docs/rl/case-411-r3-primarch-of-the-first-legion.md`). Les deux
  lectures qui manquaient sont faites -- le `Randomize` coute **un tirage par candidat** (bornes
  decroissantes, aucun court-circuit a 1) et l'ordre du pool est celui d'`AdjacentTilesSelector`,
  DEJA porte (`order="adjacent"`, R28-1). Son trigger est `On(7) & AreEqual(Owner, Target) &
  AmountIsOdd(CurrentHitIndex)` : le porteur y **EST** le defenseur (pas de negation, contrairement
  a la ligne 13 ci-dessus), et il a bien un `AmountIsOdd` -- ce que la fiche #411 par.6.2 niait.
* **`ownerNeedsToBeAlive`** du `On(7)` : l'argument est le retour d'un virtuel de la classe
  d'ability (slot `+0x298`), NON RESOLU. Le port exige le porteur VIVANT (choix conservateur : un
  porteur mort ne peut de toute facon pas encaisser).
* **`Inform({0x83: ...})`** : ecriture de contexte DSL sans consommateur identifie. Non porte.
* **`options[+0x50]`** : le port FUSIONNE les deux voies natives de coups additionnels dans
  `execute_additional_hits` (voie AVEC profil et voie SANS profil), alors que `+0x50` ne gate que
  la seconde. Aucun gate n'est donc pose -- en poser un SUR-APPLIQUERAIT le natif. Ecart nomme :
  un coup transfere d'un attaquant portant des coups additionnels SANS profil en jouerait, la ou
  le natif n'en joue pas. Non discrimine par le regime confronte (`necroDestroyer`, canal #179 vide).

ASCII only.
"""
from __future__ import annotations

from typing import Optional

from ....components import OwnerComponent, PositionComponent, StatsComponent, UnitComponent
from ....state import State

DRAW_FIRE = 1109
PRIMARCH_OF_THE_FIRST_LEGION = 1511


def _carries_draw_fire(state: State, uid: int) -> bool:
    """MEME source que `make_hit_interceptor` / `collect_triggered_abilities` : les passives
    MESUREES (`UnitContext.passive_abilities`, hierarchie 2) quand le canal a parle, sinon la
    derivation gameconfig par `visualId`. C'est ce qui rend une GREFFE
    (`catalog_inject.graft_passive_ability`) visible ici -- la SEULE voie de confrontation, les
    deux porteurs etant npc et summon-sans-invocateur (cf. la fiche §4)."""
    import gameconfig as GC
    e = state.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return False
    measured = getattr(sc.ctx, "passive_abilities", None)
    if measured is None:
        vid = getattr(sc.ctx, "visual_id", None)
        measured = list(((GC.unit(vid) or {}) if vid else {}).get("passiveAbilities") or [])
    return "DrawFire" in (measured or [])


def find_transfer_carrier(state: State, attacker_id: Optional[int],
                          defender_id: Optional[int]) -> Optional[int]:
    """Le `transferTarget` de `DrawFireAbility$$CreateBehaviour` = `Owner@DSLSelectors+0x30`,
    c.-a-d. le PORTEUR du passif -- resolu par les gates de `CreateTrigger` (cf. en-tete §1) :

        !AreEqual(Owner, Target) & AreFriends(Owner, Target) & IsAdjacent(Owner, Target)
                                 & AreEnemies(Caster, Target)

    Le gate `AreEnemies(Caster, Target)` ne porte QUE sur l'attaquant et le defenseur : il ne
    filtre aucun porteur, il conditionne le declenchement (« hit by ENEMY attacks »).

    Le natif evalue le trigger PAR PORTEUR (chaque unite qui porte le passif s'abonne a `On(7)`) ;
    plusieurs porteurs adjacents declencheraient donc plusieurs `TransferHit` sur le MEME coup.
    Le port rend UN porteur -- **l'id le plus petit** -- et c'est un ECART NOMME : l'ordre
    d'abonnement natif n'est pas lu, et aucun regime confronte n'a deux porteurs adjacents.
    Rendre `None` = pas de transfert (le coup suit son chemin ordinaire)."""
    if state is None or attacker_id is None or defender_id is None:
        return None
    from ..base import _is_adjacent_units          # lazy : cycle triggers <-> loki
    d = state.get_entity(int(defender_id))
    a = state.get_entity(int(attacker_id))
    doc = d.get_component(OwnerComponent) if d is not None else None
    aoc = a.get_component(OwnerComponent) if a is not None else None
    if doc is None or aoc is None:
        return None
    if doc.team == aoc.team:                        # AreEnemies(Caster, Target)
        return None
    out: list[int] = []
    for eid, e in state.entities.items():
        if int(eid) == int(defender_id):            # !AreEqual(Owner, Target)
            continue
        oc = e.get_component(OwnerComponent)
        if oc is None or oc.team != doc.team:       # AreFriends(Owner, Target)
            continue
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:         # `ownerNeedsToBeAlive` (cf. en-tete §5)
            continue
        if e.get_component(PositionComponent) is None:
            continue
        if not _is_adjacent_units(state, int(eid), int(defender_id)):   # IsAdjacent(Owner, Target)
            continue
        if _carries_draw_fire(state, int(eid)):
            out.append(int(eid))
    return min(out) if out else None


class DrawFireTransfer:
    """L'accroche per-coup de `1109 DrawFire`, branchee dans l'intercepteur d'`ExecuteHit`.

    Le natif execute `TransferHit` DANS le dispatch d'`On(7)`, donc **AVANT** que le coup courant
    ne soit resolu : l'attaque de transfert consomme ses tirages (crit + resolve + block/evasion
    sur le PORTEUR) AVANT le resolve `[0,0]` du coup original. `transfer(hit_index)` respecte cet
    ordre -- c'est pour ca qu'il LANCE l'attaque au lieu de la differer.

    ANTI-RECURSION : la sous-attaque part avec le `hit_index0` par defaut (0), donc son unique coup
    est d'index PAIR et `AmountIsOdd` y est faux. C'est la garde NATIVE (cf. en-tete §2), pas un
    garde-fou ajoute."""
    __slots__ = ("state", "attacker_id", "defender_id", "events")

    def __init__(self, state: State, attacker_id: Optional[int], defender_id: Optional[int]):
        self.state = state
        self.attacker_id = attacker_id
        self.defender_id = defender_id
        self.events: list[dict] = []

    def transfer(self, hit_index: int) -> bool:
        if int(hit_index) % 2 == 0:                 # AmountIsOdd(CurrentHitIndex), 0-based
            return False
        carrier = find_transfer_carrier(self.state, self.attacker_id, self.defender_id)
        if carrier is None:
            return False
        from ...damage import AttackDamageOperation      # lazy : cycle operations <-> triggers
        res = AttackDamageOperation.execute(
            self.state, int(self.attacker_id), int(carrier),
            # `opts[+0x28]` + `Nullable<int> hits` vide -> le coup transfere vaut 1 coup, sans
            # passer par la requete de modificateurs de nombre de coups.
            skip_hit_count_query=True,
            # `abilityOrEffect` est repasse TEL QUEL par `TransferHitOperation$$Execute` : c'est
            # l'ability qui a declenche le transfert qui est portee par la sous-attaque.
            triggering_ability=DRAW_FIRE,
            # le porteur peut etre tombe entre-temps ; le natif ne re-teste pas le caster ici.
            allow_dead_caster=True)
        self.events.append({"ability": DRAW_FIRE, "carrier": int(carrier),
                            "hit": int(hit_index),
                            "transferred": int((res or {}).get("total") or 0)})
        return True
