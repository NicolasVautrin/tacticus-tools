"""Port de la section `BC.Victory` de la BattleConfiguration -- FOYER UNIQUE du PLAFOND DE ROUNDS
(#287-r11-r1-r1).

CE QUE LE NATIF FAIT, lu de bout en bout (build `rnca9r7q6c`) :

    IdunBattle.Core.Services.BattleQuery$$Initialize(..., victoryConfig, turnConfig)
        this.<+0xb0> = victoryConfig            # le 14e parametre, NOMME dans la metadonnee
    IdunBattle.Core.Services.BattleQuery$$GetMaxRounds()
        dict = this.<victoryConfig @+0xb0>.<Dictionary @+0x18>
        if (dict == null)                       -> throw
        if (!dict.TryGetValue(1, out v))        -> return default(Nullable<int>)   # VIDE
        return new Nullable<int>(v)

Le litteral `1` est `VictoryConditionType.MainPlayerRoundLimitation` (`enums.tsv`), donc le
dictionnaire `<victoryConfig @+0x18>` est **`BC.Victory.VictoryConditions`** -- que la seed
serialise PAR NOM (`{"MainPlayerHasNoHeroesAndSummons": 1, "KillAllEnemyUnits": 1}`).

⚠ **LE RETOUR EST UN `Nullable<int>`, PAS UN ENTIER.** La distinction est LOAD-BEARING : le seul
consommateur porte, `IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns`, teste
`HasValue` en PREMIER et rend `true` sans rien lire d'autre quand la valeur manque. Rabattre
l'absence sur `0` inverserait le verdict (`2 <= 0 - ended` est FAUX) et ferait refuser tous les
casts des trois porteurs du bit `CasterHas2TurnsLeft`.

CONSEQUENCE POUR LE PORT. Le defaut de ce module N'EST PAS un litteral : il est LU dans
`data/seed-bc.json` (entree VERSIONNEE, la seed dont partent tous les runners `rl_duel build`),
exactement comme `engine.services.damage_config`. Sur cette seed la cle
`MainPlayerRoundLimitation` est **ABSENTE** -> pas de plafond -> `has_minimum_remaining_turns`
rend `True`, et c'est une lecture, pas une convention permissive.

ASCII only (console cp1252).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from ..entities.victory_condition_type import VictoryConditionType

# `data/seed-bc.json` : ENTREE VERSIONNEE (CLAUDE.md, invariant 3 -- `data/` = ce qu'on LIT).
# engine/services/victory_config.py -> parents[4] == racine du depot.
SEED_BC = Path(__file__).resolve().parents[4] / "data" / "seed-bc.json"

#: Nom de la section dans la BC.
VICTORY_SECTION = "Victory"
#: Nom du dictionnaire dans `BC.Victory` -- le `<victoryConfig @+0x18>` du decompile.
CONDITIONS_KEY = "VictoryConditions"


@lru_cache(maxsize=1)
def seed_victory_conditions() -> dict:
    """`BC.Victory.VictoryConditions` de la seed versionnee. Une seule lecture par process.

    LEVE si la seed est absente ou illisible : un repli silencieux ici reproduirait le vice que
    `damage_config` a nomme (une valeur inventee qui se fait passer pour une lecture).

    ⚠ Une section `Victory` PRESENTE dont le dictionnaire est VIDE est un resultat legitime (le
    natif rendrait un `Nullable` vide) -- seule l'absence de la SECTION est une anomalie de seed."""
    try:
        bc = json.loads(SEED_BC.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(
            "seed BC illisible (%s): %s -- le defaut du plafond de rounds est LU dans cette entree "
            "versionnee, il n'est pas code en dur. Regenere-la: `python dump_boards.py`."
            % (SEED_BC, exc))
    vic = bc.get(VICTORY_SECTION)
    if not isinstance(vic, dict):
        raise RuntimeError("seed BC %s: section `%s` absente ou non-objet"
                           % (SEED_BC, VICTORY_SECTION))
    conds = vic.get(CONDITIONS_KEY)
    if conds is None:
        return {}
    if not isinstance(conds, dict):
        raise RuntimeError("seed BC %s: `%s.%s` n'est pas un objet"
                           % (SEED_BC, VICTORY_SECTION, CONDITIONS_KEY))
    return dict(conds)


def victory_conditions_from_bc(bc_victory: Any) -> Optional[dict]:
    """Le dictionnaire `VictoryConditions` d'une section `BC.Victory` fournie par l'appelant.

    `None` = canal NON FOURNI (l'appelant ne connait pas sa BC) -- a distinguer de `{}`, qui est
    « la BC a parle, et elle ne pose aucune condition ». C'est la meme discipline tri-etat que
    `DamageConfiguration.from_bc`."""
    if not isinstance(bc_victory, dict):
        return None
    conds = bc_victory.get(CONDITIONS_KEY)
    if conds is None:
        return {}
    if not isinstance(conds, dict):
        return {}
    return dict(conds)


def _read_round_limitation(conditions: dict) -> Optional[int]:
    """`conditions[MainPlayerRoundLimitation]` en `Nullable<int>` -- `None` = cle absente.

    La seed serialise les cles PAR NOM ; le natif indexe PAR ORDINAL. Les deux formes sont
    acceptees ici (c'est la MEME table), et le nom est celui du mirror, jamais un litteral."""
    key = VictoryConditionType.MainPlayerRoundLimitation
    for candidate in (key.name, int(key), str(int(key))):
        if candidate in conditions:
            val = conditions[candidate]
            if val is None:
                return None
            try:
                return int(val)
            except (TypeError, ValueError):
                return None
    return None


def get_max_rounds(state=None, victory_conditions=None) -> Optional[int]:
    """`IdunBattle.Core.Services.BattleQuery$$GetMaxRounds` -- mirror 1:1, `Nullable<int>`.

    `None` = le `Nullable` VIDE du natif (la cle `MainPlayerRoundLimitation` n'est pas dans
    `BC.Victory.VictoryConditions`), c'est-a-dire **le match n'a pas de plafond de rounds**.

    Ordre de resolution, du plus specifique au plus general -- calque sur
    `damage_config.resolve_damage_field` :
      1. `victory_conditions` explicite (l'appelant sait ce qu'il fait) ;
      2. la BC de CETTE bataille, portee par le `State` (`load_state(victory_config=...)`) ;
      3. le defaut DERIVE de la seed versionnee.

    ⚠ L'etage (2) porte le dictionnaire ENTIER, pas la valeur : `State.victory_conditions is None`
    signifie « canal non fourni », tandis qu'un dictionnaire fourni SANS la cle signifie « la BC a
    parle : pas de plafond ». Rabattre les deux sur `None` ferait de « je ne sais pas » et de
    « il n'y en a pas » la meme reponse -- or seule la seconde est une MESURE."""
    if victory_conditions is not None:
        return _read_round_limitation(victory_conditions)
    if state is not None:
        conds = getattr(state, "victory_conditions", None)
        if conds is not None:
            return _read_round_limitation(conds)
    return _read_round_limitation(seed_victory_conditions())
