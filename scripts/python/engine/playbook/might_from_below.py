"""`MightFromBelowPlaybook` (1165, `genesPatriarch` « The Patriarch », Genestealer Cults) -- #970.

## Ce que la classe native SURCHARGE, et ce qu'elle ne surcharge pas

`data/symbols/<build>/frida/classes.tsv` : `IdunBattle.AI.Playbook.Loki.MightFromBelowPlaybook` a
pour base `IdunBattle.AI.Playbook.ComparablePlaybook`1` -- lue LA, pas dans le nom du corps de
`.ctor` (que ghidra etiquette `ComparablePlaybook<T>$$.ctor`, ce qui est ici juste, mais ne l'est
PAS pour les trois NonComparable de la meme tranche). `IdunBattle.AI.Playbook.Loki.
MightFromBelowPlaybook$$.ctor` = `ComparablePlaybook<T>..ctor(this, 0x48d)` -> ability_id 1165.

La classe ne porte que DEUX methodes propres :

* `MightFromBelowPlaybook$$MakeDamagePredictions` -- la forme CANONIQUE, mot pour mot :

      damage  = ability.GetDamage(abilityState)          // corps dedup `VigilanceEternalAbility$$
                                                         //   GetDamage` = MinMaxDamage(state, FALSE)
      hits    = AActiveAbility$$GetHits()                // GetNumberConstant(0x2f = nrOfHits) = 5
      profile = AActiveAbility$$GetDamageProfile()       // config `damageProfile` = Psychic
      return ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions(
                 caster, casterPosition, target, <selecteur Target>, damage, hits,
                 Nullable(profile), default, 0)

  Aucune entree n'est surchargee : c'est EXACTEMENT le chemin generique du port
  (`prediction/abilities.py::make_damage_predictions`), et 1165 figure DEJA dans
  `entities/abilities/active_ability.py::_PREDICTION_MINMAX_RANDOM_READ` -- la famille (b), LUE et
  confirmee, qui coincide avec le defaut. Rien a poser de ce cote.

* `MightFromBelowPlaybook$$CalculateCasterPositionUtility` -- **le seul delta**, et il etait
  INATTEIGNABLE : le slot +0x348 n'etait sommé nulle part sur la route Comparable d'attaque
  (residu nomme de `case-27`). #970 pose le crochet sur `ComparablePlaybook`
  (`playbook/base.py`, defaut `0.0` = le corps natif de base EXACT) et le somme a son RANG.

## Le corps, relu VERBATIM

    Fix64 CalculateCasterPositionUtility(caster, casterPosition, abilityState) {
        sel = MightFromBelowAbility$$GetPossibleSpawnTiles();
        e   = new AbilityEntities(caster: caster, casterTile: casterPosition, <tout le reste NUL>);
        n   = sel.<slot itf 2 = Count>(e);
        return Fix64(n) * Playbook<T>$$GetUtilityValue("MIGHTFROMBELOW_ExistingAdjacentDecoy");
    }

et le selecteur, lui aussi VERBATIM
(`IdunBattleLogic.Entities.Abilities.Active.Loki.MightFromBelowAbility$$GetPossibleSpawnTiles`) :

    DSLSelectors.Tiles( DSLSelectors.UnitsWithTrait(
                            DSLSelectors.AdjacentFriends(<Self>, <CasterTile>, true), 0x41d ) )

`0x41d` = **1053** = `UnitTrait.Decoy` (`data/symbols/<build>/frida/enums.tsv`, ordinal LU) -- et le
nom de la cle de poids le confirme independamment (`ExistingAdjacentDecoy`). `Tiles(...)` ne change
pas le COMPTE (une unite = une tuile) : il change le DOMAINE, ce dont l'utilite ne se sert pas.

`Playbook<T>$$GetUtilityValue(cle)` (relu) = `utilities.GetDict(0x44 = UtilityType.ActiveAbilities)
.TryGetValue(cle)` ; ABSENTE -> log + `Fix64(0)`. Sur le seed BC courant la cle vaut **3** -- lue a
l'execution par `ctx.wt.sub("ActiveAbilities", ...)`, JAMAIS en dur.

## Ce que le terme fait, et ce qu'il ne fait pas

Il ne prend NI la cible NI l'utilite deja sommee : il departage les POSITIONS du caster, pas les
cibles. Sur un plateau sans allie `Decoy` adjacent il vaut 0 -- c'est-a-dire le regime de TOUTE
bataille ou le Patriarch n'a pas encore invoque ses leurres. Il n'est donc PAS un terme de fond :
c'est un bonus de +3 par leurre adjacent a la tuile de cast.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.active_ability_type import ActiveAbilityType
from ..entities.traits.unit_trait import UnitTrait, entity_trait_names, has_any_trait
from .base import register
from .common import DefaultActiveAbilityPlaybook

#: Cle du poids plat `Utilities.Default.ActiveAbilities` que `Playbook<T>$$GetUtilityValue` lit.
_W_KEY = "MIGHTFROMBELOW_ExistingAdjacentDecoy"


class MightFromBelowPlaybook(DefaultActiveAbilityPlaybook):
    """1165 -- `MakeDamagePredictions` GENERIQUE (rien a surcharger), plus le terme de POSITION.

    L'heritage de `DefaultActiveAbilityPlaybook` n'est pas un raccourci : c'est la lecture. Les
    trois entrees de `GenerateMultiHitAttackPredictions` sont les accesseurs de BASE
    (`GetDamage`/`GetHits`/`GetDamageProfile`), donc `make_damage_predictions`, `should_execute`
    (corps trivial `return 1`) et `calculate_custom_utility` (`Fix64(0)`) restent EXACTEMENT ce
    qu'ils etaient avant cette entree au registre."""

    ability_id = int(ActiveAbilityType.MightFromBelow)  # 1165

    def calculate_caster_position_utility(self, ctx, caster_tile, ability_id) -> float:
        """`MightFromBelowPlaybook$$CalculateCasterPositionUtility` (slot +0x348) =
        `Count(Tiles(UnitsWithTrait(AdjacentFriends(caster @ casterPosition), Decoy))) x W`.

        Trois lectures de substrat, chacune nommee :
          * `AdjacentFriends(<Self>, <CasterTile>)` -> `ctx.fpos` (positions ALLIEES, self exclu --
            le meme canal que `GetAdjacentFriends`), porte d'adjacence `bq.is_adjacent` (|dElev| < 2
            + voisinage NATIF stocke) ;
          * `UnitsWithTrait(., 0x41d = Decoy)` -> traits d'ENTITE (`entity_trait_names`), jamais le
            kit par visualId seul ;
          * `W` -> `ctx.wt.sub("ActiveAbilities", "MIGHTFROMBELOW_ExistingAdjacentDecoy")`. Cle
            absente du BC -> le natif rend `Fix64(0)`, donc un poids nul ; le port doit rendre 0 lui
            aussi, jamais un defaut invente.

        `caster_tile is None` (position non mesuree) -> `0.0` : le natif ne peut pas recevoir de
        position nulle ici, donc il n'y a pas de branche a mirrorer -- c'est une garde de PORT, et
        elle rend le NEUTRE du terme."""
        if caster_tile is None:
            return 0.0
        w = ctx.wt.sub("ActiveAbilities", _W_KEY) if getattr(ctx, "wt", None) is not None else 0
        if not w:
            return 0.0
        fpos = set(getattr(ctx, "fpos", None) or [])
        if not fpos:
            return 0.0
        scene = getattr(ctx, "scene", None)
        neigh = bq.neigh_map(ctx)
        n = 0
        for u in (getattr(ctx, "units", None) or []):
            p = u.get("pos") or {}
            if p.get("col") is None or not u.get("alive"):
                continue
            pos = (p["col"], p["row"])
            if pos not in fpos:
                continue                       # pas un ALLIE (self exclu par construction de fpos)
            if not bq.is_adjacent(caster_tile, pos, ctx.elev_by_pos, neigh):
                continue                       # `AdjacentFriends` : ring 1 de la tuile de cast
            uctx = scene.ctx(u.get("id")) if scene is not None else None
            if has_any_trait(entity_trait_names(uctx, u.get("visualId")), (UnitTrait.Decoy,)):
                n += 1                         # `UnitsWithTrait(., 0x41d = Decoy)`
        return float(n) * float(w)


register(MightFromBelowPlaybook())
