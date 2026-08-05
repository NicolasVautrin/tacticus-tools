"""Port de `IdunBattle.Configuration.DamageConfiguration` -- la section `BC.Damage` de la
BattleConfiguration, cote VARIANCE DE DEGAT. FOYER UNIQUE du `spread_pct` (#449-r2-r4).

CE QUE LE NATIF FAIT, lu de bout en bout (build `rnca9r7q6c`) :

    IdunBattle.Runner.IdunRunner$$Initialize
      -> IdunBattle.Core.Services.DamageCalculations$$Init(configuration = BattleConfiguration.Damage)
             `configuration` est range en `DamageCalculations+0x18` (2e argument).
      -> IdunBattle.Core.Services.DamageCalculations$$get_DamageSpreadPercentageFix64
             pct = Fix64(*(uint*)(configuration + 0x20)) / Fix64(100)
             cache paresseux dans le `Nullable<Fix64>` `DamageCalculations+0x38`.
             ⚠ `configuration == null` -> `FUN_1801f51f0` (NullReferenceException) : le natif
             ne fabrique AUCUN repli, il LEVE.
      -> IdunBattle.Core.Services.DamageCalculations$$CalculateDamageSpread(damage)
             (le corps du getter y est INLINE -- meme sequence, meme cache)
             delta = Fix64.Round(damage * pct, AwayFromZero)
      -> IdunBattle.Core.Services.DamageCalculations$$CalculateMinDamage = Round(damage - delta, 1)
         IdunBattle.Core.Services.DamageCalculations$$CalculateMaxDamage = Round(damage + delta, 1)
             (aucun appelant DIRECT : atteints par les slots 8 et 9 de l'interface)
      -> IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64   (slots 8/9)
      -> IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw     (branche SPREAD)

LE CHAMP N'A PAS DE DEFAUT NATIF. `IdunBattle.Configuration.DamageConfiguration$$.ctor`
n'initialise QUE le `Dictionary` `+0x40` (DamageProfiles) : tout champ absent du JSON reste a la
valeur par defaut de son type C#, donc `DamageSpreadPercentage` absent vaut **0** (bornes plates),
jamais 20. C'est mesure, cf. `docs/rl/case-449-r2-r4-spread-lu-de-la-bc.md`.

CONSEQUENCE POUR LE PORT. Le defaut de ce module N'EST PAS un litteral : il est LU dans
`data/seed-bc.json` (entree VERSIONNEE, la seed dont partent tous les runners `rl_duel build`).
Ecrire `20` en dur ici recreerait exactement le vice que `#449-r2-r4` a nomme -- un couplage non
lu, muet le jour ou la BC vaut autre chose.

SECOND CHAMP DE LA MEME SECTION, lu au meme decompile : `IgnoreDamageSpread` (`+0x31`, bool),
via `IdunBattle.Core.Services.DamagePrediction$$get_IgnoreDamageSpread` (`this+0x10` =
`configuration`, pose par `IdunBattle.Core.Services.DamagePrediction$$.ctor`). C'est le SECOND
aiguillage vers la branche plate de `PredictAttackRaw` (residu `#449-r2-r2`, ferme ici cote RE).
Le port le rabat sur `spread_pct = 0`, la facon dont il modelise deja la branche plate (#449-r2).

ASCII only (console cp1252).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

# `data/seed-bc.json` : ENTREE VERSIONNEE (CLAUDE.md, invariant 3 -- `data/` = ce qu'on LIT).
# engine/services/damage_config.py -> parents[4] == racine du depot.
SEED_BC = Path(__file__).resolve().parents[4] / "data" / "seed-bc.json"

#: Nom du champ dans la BC, tel qu'il apparait dans `BC.Damage`.
SPREAD_KEY = "DamageSpreadPercentage"
IGNORE_KEY = "IgnoreDamageSpread"


@lru_cache(maxsize=1)
def seed_damage_section() -> dict:
    """La section `Damage` de la seed BC versionnee. Une seule lecture par process.

    LEVE si la seed est absente ou illisible : un repli silencieux ici reproduirait le vice
    (une valeur inventee qui se fait passer pour une lecture)."""
    try:
        bc = json.loads(SEED_BC.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(
            "seed BC illisible (%s): %s -- le defaut de DamageSpreadPercentage est LU dans cette "
            "entree versionnee, il n'est pas code en dur. Regenere-la: `python dump_boards.py`."
            % (SEED_BC, exc))
    dmg = bc.get("Damage")
    if not isinstance(dmg, dict):
        raise RuntimeError("seed BC %s: section `Damage` absente ou non-objet" % (SEED_BC,))
    return dmg


@lru_cache(maxsize=1)
def default_damage_spread_percentage() -> int:
    """Le defaut du port pour `BattleConfiguration.Damage.DamageSpreadPercentage`.

    DERIVE, jamais ecrit : c'est la valeur de `data/seed-bc.json`, la seed dont partent tous les
    runners. Un appelant qui connait SA BC ne passe pas par ici (`load_state(damage_config=...)`
    ou l'argument explicite)."""
    dmg = seed_damage_section()
    val = dmg.get(SPREAD_KEY)
    if val is None:
        raise RuntimeError(
            "seed BC %s: `Damage.%s` absent. Le natif rendrait 0 (le ctor "
            "`IdunBattle.Configuration.DamageConfiguration$$.ctor` n'initialise que "
            "DamageProfiles), mais le port refuse de DEVINER ce que la seed ne dit pas : "
            "cable le canal `load_state(damage_config=...)`." % (SEED_BC, SPREAD_KEY))
    return int(val)


class DamageConfiguration:
    """`IdunBattle.Configuration.DamageConfiguration`, restreint aux deux champs de la VARIANCE.

    Layout relu (build `rnca9r7q6c`, cf. en-tete du module) :
        +0x20 DamageSpreadPercentage (uint)  -- `$$get_DamageSpreadPercentageFix64`
        +0x31 IgnoreDamageSpread     (bool)  -- `$$get_IgnoreDamageSpread`
    """
    __slots__ = ("damage_spread_percentage", "ignore_damage_spread")

    def __init__(self, damage_spread_percentage: int, ignore_damage_spread: bool = False):
        self.damage_spread_percentage = int(damage_spread_percentage)
        self.ignore_damage_spread = bool(ignore_damage_spread)

    @classmethod
    def from_bc(cls, bc_damage: Any) -> Optional["DamageConfiguration"]:
        """Depuis la section `BC.Damage` d'une BattleConfiguration. `None` si le canal n'est pas
        fourni (l'appelant ne connait pas sa BC) -- PAS un zero fabrique.

        ⚠ Champ ABSENT de la section = **0**, comme le natif (le DTO C# ne porte aucun
        initialiseur ; seul `DamageProfiles` est construit par le ctor). Ce n'est pas le meme cas
        que « section non fournie » : ici la BC a parle, et elle dit zero."""
        if not isinstance(bc_damage, dict):
            return None
        return cls(int(bc_damage.get(SPREAD_KEY) or 0), bool(bc_damage.get(IGNORE_KEY) or False))


def resolve_spread_pct(spread_pct=None, state=None) -> int:
    """LE point unique ou un `spread_pct` non fourni prend sa valeur.

    Ordre, du plus specifique au plus general :
      1. `spread_pct` explicite (l'appelant sait ce qu'il fait -- ex. le `0` LU des porteurs a
         `Nullable<AttackDamageBehaviourOptions>` vide, cf. `#449-r2`) ;
      2. la BC de CETTE bataille, portee par le `State` (`load_state(damage_config=...)`) ;
      3. le defaut DERIVE de la seed versionnee.

    `IgnoreDamageSpread` de l'etat court-circuite (2) et (3) a `0` -- mirror du second aiguillage
    de `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` vers la branche plate. Il ne
    court-circuite PAS (1) : un appelant qui impose sa variance a lu son propre decompile."""
    if spread_pct is not None:
        return int(spread_pct)
    if state is not None:
        if getattr(state, "ignore_damage_spread", False):
            return 0
        val = getattr(state, "damage_spread_percentage", None)
        if val is not None:
            return int(val)
    return default_damage_spread_percentage()
