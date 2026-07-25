"""`IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility` (passiveAbility
`FleshmetalGuns` de `blackObliterator` << Volk >>, Black Legion) -- la ROTATION des 3 effets d'armes au
DEBUT DU TOUR du porteur.

Les 3 effets etaient deja portes et consommes (`FleshmetalGunsFocusedMaliceEffect` 0x42b=1067,
`FleshmetalGunsRuinousSalvoEffect` 0x4bc=1212, `FleshmetalGunsWarpHailEffect` 0x4c5=1221 --
`entities/effects/loki/hits.py`, canal #179 `additional_hit_groups`). Ce qui MANQUAIT = la ROTATION qui
les pose : un runner OFFLINE gardait indefiniment l'effet SEEDE au tour 1 (FocusedMalice/Melta), les deux
autres n'etaient JAMAIS materialises.

## RE native (decompile ghidra, build gqfc5mff6c)

| Symbole | VA |
|---|---|
| `FleshMetalGunsAbility$$CreateBehaviour`            | `IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour` |
| `FleshMetalGunsAbility$$CreateTrigger` (corps DEDUPLIQUE, symbole ghidra `ArchContaminatorAbility$$CreateTrigger`) | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArchContaminatorAbility$$CreateTrigger` |
| `BaseFleshmetalGunsEffect$$CreateAdditionalHits`    | `IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$CreateAdditionalHits` |
| `FleshMetalGuns_TileEffectAbility$$CreateTrigger`   | `IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateTrigger` |
| `FleshMetalGuns_TileEffectAbility$$CreateBehaviour` | `IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateBehaviour` |

### `CreateTrigger` = `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArchContaminatorAbility$$CreateTrigger` (identification)
`FleshMetalGunsAbility` n'a PAS de symbole `CreateTrigger` propre : son corps est DEDUPLIQUE avec celui
d'autres abilities. Identifie par la TABLE DE POINTEURS DE METHODES (adjacence par classe) : les xrefs
DATA de `IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour` tombent sur `0x1830f97c8` ; le slot precedent `0x1830f97c0` porte
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArchContaminatorAbility$$CreateTrigger`, et le motif par classe [.ctor, stub, CreateTrigger, CreateBehaviour] est confirme par le
couple voisin `FleshMetalGuns_TileEffectAbility` (`0x1830f97d8` = son IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateTrigger`,
`0x1830f97e0` = son IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateBehaviour`). Corps :
```
On(0x16 = TurnStart_Actions = 22) & df@0xa0
```
`df@0xa0` est construit par `IdunBattleLogic.Entities.DSLFactory$$InitializeShared` :
`new <DAT_18320cc68>(df@0x148, df@0x10)` -- MEME classe et MEMES arguments que `IdunBattleLogic.Entities.DSLFactory$$IsTurnOf` applique a `Self@0x148` => **`IsTurnOf(Self)`**. Donc : la rotation fire au debut du tour du
PROPRIETAIRE (et non a chaque debut de tour).

### `IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour` (chaine d'`AbilityBehaviour.op_Addition`)
```
Nothing()
+ RemoveEffect(Self@0x148, Nullable(0x42b))      # FocusedMalice
+ RemoveEffect(Self@0x148, Nullable(0x4bc))      # RuinousSalvo
+ RemoveEffect(Self@0x148, Nullable(0x4c5))      # WarpHail
+ If( Modulo(UnitTurnsStarted(Self@0x148), Get(3), Get(1)), AddEffect(0x42b, stateRef, Self@0x148, 0) )
+ If( Modulo(UnitTurnsStarted(Self@0x148), Get(3), Get(2)), AddEffect(0x4bc, stateRef, Self@0x148, 0) )
+ If( Modulo(UnitTurnsStarted(Self@0x148), Get(3), Get(0)), AddEffect(0x4c5, stateRef, Self@0x148, 0) )
```
- `Modulo(a,b,c)` (`IdunBattleLogic.Entities.DSLFactory$$Modulo` -> `IdunBattle.Entities.Conditions.ModuloAbilityTrigger$$ShouldTrigger`)
  est un **PREDICAT** : `(a mod b) == c`. `Get(n)` = noeud VALEUR constant.
- `UnitTurnsStarted(Self)` (`IdunBattleLogic.Entities.DSLFactory$$UnitTurnsStarted` -> `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate`) =
  `GetStat(unit, 0xc)`. Le compteur est incremente par `StartTurnOperation` **AVANT** l'emission de
  `On(0x16)` (mirror porte : `_bump_turns_started` puis `start_turn_triggers`) -> au 1er tour de Volk le
  compteur vaut deja **1**.
- Cycle observable : `turns%3 == 1` -> **FocusedMalice (Melta)**, `== 2` -> **RuinousSalvo (Flame)**,
  `== 0` -> **WarpHail (HeavyRound)**. Le seed live d'un runner frais montre bien `FleshmetalGunsFocused
  Malice` sur Volk (tour 1) -- cohérent.
- Les 3 `RemoveEffect` INCONDITIONNELS AVANT les 3 `If` = pas de double-pose ; l'effet du tour precedent
  part meme si aucune branche ne matche.

### Volet `FleshMetalGuns_TileEffectAbility` (DespoiledGround) -- NON porte ici
`IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateTrigger` = `On(0x10=DamageDealt) & OwnerIsCaster & HasEffect(Self@0x148, 0x4c5=WarpHail,
srcflag 6)` ; `IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateBehaviour` = `AddEffect(0x5c4=1476, stateRef, Tiles(Target@0x178))` = pose
l'effet de TUILE DespoiledGround sous la cible pendant le round WarpHail. Prerequis ABSENT : le vecteur
`On(DamageDealt=16)` n'existe pas dans le dispatch porte -> residu documente (hors perimetre << la pose
manque >> : l'effet de tuile 1476 n'est pas porte non plus).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent
from ....abilities.behaviours import AddEffect, RemoveEffect, entities_from_state
from .....entities.behaviours import op_add, If as IfBehaviour
from .....entities.formulas import UnitTurnsStarted
from .....entities.selectors import Caster
from .....entities.triggers import Modulo
from .....entities.effect_type import EffectType
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

# (EffectType, nom capte, reste attendu du modulo) — l'ORDRE est celui du decompile IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour.
FLESHMETAL_CYCLE = (
    (int(EffectType.FleshmetalGunsFocusedMalice), "FleshmetalGunsFocusedMalice", 1),   # 0x42b=1067 Melta
    (int(EffectType.FleshmetalGunsRuinousSalvo), "FleshmetalGunsRuinousSalvo", 2),     # 0x4bc=1212 Flame
    (int(EffectType.FleshmetalGunsWarpHail), "FleshmetalGunsWarpHail", 0),             # 0x4c5=1221 HeavyRound
)
_CYCLE_LEN = 3                              # `Get(3)` = le diviseur du Modulo
_ON_TURN_START = int(EventTriggerType.TurnStart_Actions)     # 0x16 = 22


def fleshmetal_guns_tree():
    """Mirror 1:1 de `IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour` (cf. en-tete). `Caster()` =
    `Self@0x148` (triggered Owner==Caster). `duration_rounds=None` = struct d'options ZERO du natif ->
    `DefaultAmountOfRounds` (aucun des 3 types n'y figure -> defaut 1 tour, re-pose chaque tour par la
    rotation). `scale_from_source=True` : les 3 effets tirent leur magnitude d'un `ConfigVar`
    (minDmg/maxDmg/nrOfHits indexes par le niveau d'ability du porteur x son multiplier de rarete)."""
    tree = None
    for eff_type, _name, _rest in FLESHMETAL_CYCLE:          # les 3 RemoveEffect INCONDITIONNELS
        node = RemoveEffect(eff_type, Caster())
        tree = node if tree is None else op_add(tree, node)
    for eff_type, name, rest in FLESHMETAL_CYCLE:            # puis les 3 If(Modulo(...))
        node = IfBehaviour(
            Modulo(UnitTurnsStarted(Caster()), Const(_CYCLE_LEN), Const(rest)),
            AddEffect(eff_type, name, Caster(), duration_rounds=None, scale_from_source=True))
        tree = op_add(tree, node)
    return tree


class FleshmetalGunsRotationAbility(TriggeredAbility):
    """`FleshMetalGunsAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArchContaminatorAbility$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour) — au DEBUT DU TOUR
    de Volk (`On(TurnStart_Actions=22) & IsTurnOf(Self)`), retire les 3 effets d'arme puis pose celui du
    tour courant selon `UnitTurnsStarted(Self) mod 3`. Les 3 effets (+2 coups bonus d'un profil donne)
    sont deja portes (`entities/effects/loki/hits.py`)."""
    event_id = _ON_TURN_START

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `IsTurnOf(Self@0x148)` (df@0xa0) : le tour qui demarre est celui du PROPRIETAIRE.
        e = state.get_entity(self.owner_id)
        oc = e.get_component(OwnerComponent) if e is not None else None
        return not (oc is None or ev.player_id is None or oc.player != int(ev.player_id))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        fleshmetal_guns_tree().execute(entities_from_state(state, self.owner_id, None), ectx)
        placed = [p.get("effect_type") for n, p in ectx.emitted if n == "AddEffect" and p.get("placed")]
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        return {"ability": "FleshmetalGuns", "unit": int(self.owner_id),
                "placed": placed, "removed": removed}
