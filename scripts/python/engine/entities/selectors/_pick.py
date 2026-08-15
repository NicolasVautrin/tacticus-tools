"""`IdunBattle.DSL.APickSelector` et ses deux selecteurs concrets de PRELEVEMENT ORDONNE.

Module FEUILLE (il n'importe que `...dsl.base`) : c'est ce qui permet a `selectors/geometry.py`
ET a `selectors/units.py` de partager le MEME foyer sans fermer de cycle -- et c'est le
DEPLACEMENT prescrit par la doctrine d'import, pas un differe (#1032-r2).

TROIS artefacts natifs, lus terme a terme :

  * `IdunBattleLogic.Entities.DSLSelectors$$First(entities, amount, ignoreForcedTargets)` --
    DEUX surcharges : celle qui prend un `amount` NOEUD-VALEUR, et celle qui prend un `amount`
    INT et le BOXE dans un fournisseur constant avant de deleguer a la premiere. Les deux
    allouent le MEME type de selecteur (`PickFirstNSelector`). Ghidra mislabelle les deux ctors
    gshared (`UnitsThatCanHaveActiveAbilityResetSelector$$.ctor`,
    `Stash.Native.StashNative.u003COpenCardOrModalInternalu003Ed__46$$.ctor`) : on lit la
    STRUCTURE (`+0x10 state`, `+0x18 source`, `+0x20 amount`, `+0x28 ignoreForcedTargets`),
    jamais le nom.
  * `IdunBattleLogic.Entities.DSLSelectors$$Last(entities, amount, ignoreForcedTargets)` -- meme
    forme, type DISTINCT (`PickLastNSelector`), et c'est la SEULE ligne du ctor qui differe.
  * `IdunBattle.DSL.APickSelector$$AddForcedTargetsAndUpdateCandidates` -- la base commune.

⚠ **`DSLFactory$$First` N'EXISTE PAS DANS CE BUILD, ET LE `First` NATIF PREND UN NOMBRE, PAS UN
INDICE.** Le build `t6dpr4k06g` ne porte que **5** methodes `IdunBattleLogic.Entities.DSLFactory$$`
(`Init`, `SetAllowRandom`, `SetDisallowRandom`, `Triggered`, `.ctor`) contre **232**
`IdunBattleLogic.Entities.DSLSelectors$$` : toute citation `DSLFactory$$<selecteur>` est PERIMEE.
Le selecteur qui prend un INDICE est `PickAtIndexSelector`, et sa factory s'appelle
`IdunBattleLogic.Entities.DSLSelectors$$AtIndex` (`selectors/geometry.py::AtIndex`) -- **6**
call-sites dans tout le binaire, contre **145** pour `First`.

CENSUS DES LITTERAUX (lecture PE de TOUS les call-sites, pas d'un echantillon ; build
`t6dpr4k06g`, 2026-08-15) :
    `First`   : 145 call-sites -- `amount` = 1 (104), = 3 (4), calcule (37) ;
                                  `ignoreForcedTargets` = 0 (**144**), = 1 (1).
    `Last`    :   5 call-sites -- `ignoreForcedTargets` = 0 (4), = 1 (1).
    `AtIndex` :   6 call-sites.
Autrement dit la branche FORCED-TARGETS est prise sur **148 des 150** call-sites des deux
selecteurs : ne pas la porter n'etait pas un detail de bord.
"""
from __future__ import annotations

from ...dsl.base import TargetsSelector


def _entity_id(item):
    """`IEntity.Id` de l'element courant -- le slot que lit
    `IdunBattle.DSL.APickSelector$$AddForcedTargetsAndUpdateCandidates` avant son `Contains`.

    ⚠ DOMAINE : le natif compare un `BEntityId` et une TUILE en est une entite ; cote port, les
    ids de TUILE vivent dans `state.board` et les ids d'UNITE dans `state.entities` -- **deux
    espaces de numerotation disjoints** (cf. `runner/components.py`, « les tuiles vivent dans
    `state.board`/`EffectsState`, jamais dans `state.entities` »). Traiter un id de tuile comme un
    `IEntity.Id` fabriquerait donc des faux positifs. On ne resout donc que le domaine UNITE, et
    ca ne retire AUCUN cas natif : le seul ecrivain de `ForcedAttackTargetsComponent` est
    `IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` (+ la voie incrementale
    `AddForcedAttackTargetBehaviour` du trait `InstinctiveBehaviour`), qui bondent une UNITE."""
    if isinstance(item, dict):
        v = item.get("id")
        return int(v) if v is not None else None
    return None


def add_forced_targets_and_update_candidates(ctx, candidates: list, picked: list,
                                             allow_duplicates: bool, max_amount: int) -> None:
    """`IdunBattle.DSL.APickSelector$$AddForcedTargetsAndUpdateCandidates(caster, candidates,
    picked, allowDuplicates, maxAmount)` -- MIRROR du decompile, terme a terme :

        if (caster == null) return;
        if (UnitExtensions.GetOnlyTargets(caster).Count <= 0) return;
        for (i = candidates.Count - 1 ; i >= 0 ; i--) {
            if (picked.Count >= maxAmount) return;
            onlyTargets = UnitExtensions.GetOnlyTargets(caster);      // relu a chaque tour
            if (onlyTargets.Contains(candidates[i].Id)) {
                picked.Add(candidates[i]);
                if (!allowDuplicates) candidates.RemoveAt(i);
            }
        }

    DEUX points que le sens commun aurait rates :
      * le balayage part de la **FIN** des candidats -- les cibles forcees entrent donc dans
        `picked` dans l'ordre INVERSE de la source, pas dans son ordre ;
      * `candidates` est **MUTE** (`RemoveAt`), et c'est ce qui evite que l'appelant re-copie une
        cible forcee : le port mute donc la MEME liste, comme le natif.

    `caster` = `AbilityEntities+0x8`. L'offset est LU, pas suppose : `ActorSelector$$Select` lit
    `+0x0`, `IdunBattle.Entities.Selectors.CasterSelector$$Select` lit `+0x8` et
    `IdunBattle.Entities.Selectors.TargetSelector$$Select` lit `+0x10` -- et Ghidra nomme bien
    `caster` le 2e parametre de cette fonction, depuis les metadonnees IL2CPP.

    SUBSTRAT : `ctx.only_targets(unitId)` (cable sur le foyer UNIQUE
    `runner/abilities/targeting.get_only_targets`, mirror de
    `IdunBattle.Entities.UnitExtensions$$GetOnlyTargets`). Accesseur absent (contexte hors runner)
    -> aucune cible forcee, donc AUCUN reordonnancement : degradation NOMMEE, et c'est exactement
    le comportement du natif quand `GetOnlyTargets` rend une liste vide (le cas de la
    quasi-totalite des unites)."""
    caster = getattr(ctx, "caster", None)
    if not isinstance(caster, dict) or caster.get("id") is None:
        return                                            # `caster == null`
    fn = getattr(ctx, "only_targets", None)
    if fn is None:
        return                                            # canal non branche (cf. docstring)
    forced = set(int(x) for x in (fn(int(caster["id"])) or ()))
    if not forced:
        return                                            # `GetOnlyTargets(caster).Count <= 0`
    i = len(candidates) - 1
    while i >= 0:
        if len(picked) >= int(max_amount):
            return
        eid = _entity_id(candidates[i])
        if eid is not None and eid in forced:
            picked.append(candidates[i])
            if not allow_duplicates:
                del candidates[i]                         # `candidates.RemoveAt(i)`
        i -= 1


class APickSelector(TargetsSelector):
    """Base commune `IdunBattle.DSL.APickSelector` (taille 0x30) : `+0x18 source`, `+0x20 amount`
    (noeud VALEUR ou int), `+0x28 ignoreForcedTargets`.

    `ignore_forced_targets` PORTE desormais son effet -- il etait TRANSCRIT et inerte jusqu'a
    #1032-r2. Le litteral se lit au call-site ; le defaut `False` est celui de **144 call-sites
    de `First` sur 145** et de **4 sur 5** de `Last` (census PE ci-dessus)."""
    __slots__ = ("source", "amount", "ignore_forced_targets")

    def __init__(self, source: TargetsSelector, amount, ignore_forced_targets: bool = False):
        self.source, self.amount = source, amount
        self.ignore_forced_targets = bool(ignore_forced_targets)

    def _amount(self, ctx) -> int:
        n = self.amount.evaluate(ctx) if hasattr(self.amount, "evaluate") else self.amount
        return int(n or 0)


class PickFirstN(APickSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$First(entities, amount, ignoreForcedTargets)` ->
    `IdunBattle.Entities.Selectors.PickFirstNSelector$$Select`, MIRROR du decompile :

        candidates = <source>.Select(entities).ToList()
        n          = <amount>.Calculate(entities)
        picked     = candidates                       // la MEME liste, rendue telle quelle
        if (n < candidates.Count) {
            picked = new List<IEntity>()
            if (!<+0x28 ignoreForcedTargets>)
                AddForcedTargetsAndUpdateCandidates(caster, candidates, picked, false, n)
            for (i = 0 ; i < candidates.Count ; i++) {
                if (n <= picked.Count) return picked
                picked.Add(candidates.ElementAt(i))
            }
        }
        return picked

    ⚠ `n >= Count` rend la source ENTIERE **SANS PASSER PAR LES CIBLES FORCEES** : le
    reordonnancement n'a lieu que quand il y a effectivement un choix a faire. C'est LU, pas
    deduit -- le `if` enveloppe les deux.
    ⚠ `n <= 0` : `0 < Count` est vrai des que la source est non vide -> `picked` neuf, boucle qui
    rend immediatement -> liste VIDE ; source vide -> `0 < 0` faux -> la source (vide). Le port
    reproduit les deux sans clamp maison.

    `amount` = noeud VALEUR (`Direct(nrOfSummons)`) ou int."""
    __slots__ = ()

    def select(self, ctx):
        n = self._amount(ctx)
        candidates = list(self.source.evaluate(ctx))          # `.ToList()`
        if n >= len(candidates):                              # `n < candidates.Count` FAUX
            return candidates
        picked: list = []
        if not self.ignore_forced_targets:
            add_forced_targets_and_update_candidates(ctx, candidates, picked,
                                                     allow_duplicates=False, max_amount=n)
        for item in candidates:                               # `candidates` a pu RETRECIR
            if n <= len(picked):
                return picked
            picked.append(item)
        return picked


class PickLastN(APickSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$Last(entities, amount, ignoreForcedTargets)` ->
    `IdunBattle.Entities.Selectors.PickLastNSelector$$Select` (#940). PENDANT EXACT de
    `PickFirstN`, et le decompile ne differe que par l'indice de depart de la copie :

        candidates = <source>.Select(entities).ToList()
        n          = <amount>.Calculate(entities)
        picked     = candidates
        if (n < candidates.Count) {
            picked = new List<IEntity>()
            if (!<+0x28 ignoreForcedTargets>)
                AddForcedTargetsAndUpdateCandidates(caster, candidates, picked, false, n)
            for (i = picked.Count + candidates.Count - n ; i < candidates.Count ; i++)
                picked.Add(candidates.ElementAt(i))
        }
        return picked

    ⚠ Il n'y a PAS de garde `if (n <= picked.Count) return` dans cette boucle-ci : c'est
    l'indice de depart qui absorbe ce que les cibles forcees ont deja pose dans `picked` (et qui
    peut le porter au-dela de `candidates.Count`, auquel cas zero iteration).
    ⚠ L'indice de depart reste INVARIANT sous le retrait des cibles forcees : la passe deplace
    `k` elements de `candidates` vers `picked`, donc `picked.Count + candidates.Count` ne bouge
    pas et `i = Count_initial - n`. Aucune garde `i >= 0` n'est ajoutee -- elle serait du code
    que le natif n'a pas, et elle est de toute facon inatteignable dans cette branche
    (`n < Count`)."""
    __slots__ = ()

    def select(self, ctx):
        n = self._amount(ctx)
        candidates = list(self.source.evaluate(ctx))
        if n >= len(candidates):                              # `n < candidates.Count` FAUX
            return candidates
        picked: list = []
        if not self.ignore_forced_targets:
            add_forced_targets_and_update_candidates(ctx, candidates, picked,
                                                     allow_duplicates=False, max_amount=n)
        i = len(picked) + len(candidates) - n
        while i < len(candidates):
            picked.append(candidates[i])
            i += 1
        return picked
