"""Namespace `IdunBattle.AI.Playbook` — les playbooks par-ability (2ᵉ étage sous le scorer Utilities).

RE : docs/rl/playbook/architecture.md §2.2 + playbooks.md. Hiérarchie `BasePlaybook -> {ComparablePlaybook,
NonComparablePlaybook}`. Le générateur d'action (engine/ai) fait `LoadPlaybook(ability) -> Evaluate`.

- **Comparable** (attaques/soins) : `base.ComparablePlaybook` -> `common.py` (NormalAttack/Default/
  Heal/Repair). Prédiction déléguée à `prediction.py` (modèle objet : Scene + ability + services).
- **NonComparable** (summons/buffs/retraite) : package `noncomparable/` (1 module par playbook natif).
- **Triggered** (face ATTACK/MOVE, à clés-strings) : registres `psyker.TRIGGERED_ATTACK_PLAYBOOKS` /
  `adjacent_unit_preference.TRIGGERED_MOVE_PLAYBOOKS`, 1 module par playbook natif (`savior_protocols`…).
- Prédiction : `prediction.py` (à venir) = orchestration mince (MakeDamagePredictions) sur le modèle objet
  `engine/entities` + services `engine/services` + `ProbableDamageEvent`. Remplace `predict_validate` (PV).

CE BARIL PORTE DEUX CHOSES DISTINCTES, ET UNE SEULE EST NÉGOCIABLE (#485-r1-r4)
------------------------------------------------------------------------------
- Les **ENREGISTREURS** (`from . import <x>`) : l'import EST l'effet — l'enfant s'inscrit à
  `base.REGISTRY` au chargement. Les retirer vide un registre **en silence** (`.get(cle)` rend
  `None`, le moteur repart sur le playbook par défaut). Ils restent, et le cliquet
  `probe_485r1r4_baril_playbook.py` étage [2] garde que le baril les tire **tous**.
- Les **RE-EXPORTS** (`from .base import ...`) : du confort d'appel, sans effet de bord propre.
  Ils faisaient tirer leur module au chargement du paquet, donc fermaient des cycles que
  d'autres payaient ensuite en imports DIFFÉRÉS.

MESURE (`probe_485_imports_differes`, arbre témoin à `62db139d`) : sur 33 symboles re-exportés,
**4** étaient consommés — `REGISTRY` (29 fichiers, dont **32 accès attributaires** `PB.REGISTRY`
qu'aucun recensement d'`ImportFrom` ne voit), `get_playbook_or_default` (24), `tile_utility` (2),
`get_playbook` (1). Retirer les **29** morts fait passer les différés PORTEURS de `engine/**` de
**277 à 262** pour **0** lecteur cassé. Le sweep #485-r1-r1 avait exclu ce baril EN BLOC parce
qu'il est « à registre » — l'exclusion était trop large : elle ne vaut que pour les enregistreurs.
"""
from __future__ import annotations

#: Les 4 symboles EFFECTIVEMENT consommés hors du paquet. Tout ajout ici doit avoir un lecteur —
#: `probe_485r1r4_baril_playbook.py` étage [1] refuse un re-export mort.
from .base import REGISTRY, get_playbook, tile_utility
#: Dépendance INTERNE de `get_playbook_or_default`, pas un re-export : le `_` le dit, et c'est
#: ce qui la distingue des 4 symboles ci-dessus pour l'étage [1] du cliquet.
from .common import DEFAULT_PLAYBOOK as _DEFAULT_PLAYBOOK

#: ENREGISTREURS — l'import EST l'effet. Ne pas retirer sans jouer l'étage [2] du cliquet :
#: un registre sous-peuplé ne lève pas, il rend le playbook par défaut.
from . import loki_custom  # noqa: F401  (#27) enregistre les overrides CalculateCustomUtility par-ability
from . import normal_attack_kill_gate  # noqa: F401  (#419-r1-tr14-r5-r2-r1-r1-r1) gate !WillNormalAttackKill x17
from . import resurrection_orb  # noqa: F401  (#289) 1009 -> route non-attaque (register_nonattack)
from . import plagueburst_mortar  # noqa: F401  (#302) 1169 -> route non-attaque, domaine TUILE
from . import daemonic_ordnance  # noqa: F401  (#302 tranche 3) 1148 -> meme route, domaine TUILE
from . import static_threshold_gate  # noqa: F401  (#419-r1-tr14-r5-r2-r1-r1-r1-r2) gate `utility > <static>` x10
from . import should_execute_gates  # noqa: F401  (#419-r1-tr14-r5-r2-r1-r1-r1) les 4 derniers corps propres portables
from . import spirit_leech  # noqa: F401  (#419-r1-tr14-r5-r2-r1-r1-r3) 1104 : lifesteal au rang natif
from . import might_from_below  # noqa: F401  (#970) 1165 : le terme CalculateCasterPositionUtility (+0x348)


def get_playbook_or_default(ability_id: int):
    """Playbook Comparable porté pour `ability_id`, sinon le fallback DefaultActiveAbilityPlaybook.
    Reproduit `PlaybookDatabase.LoadPlaybook(...) ?? LoadDefaultActiveAbilityPlaybook(...)`."""
    return REGISTRY.get(ability_id) or _DEFAULT_PLAYBOOK


__all__ = ["REGISTRY", "get_playbook", "get_playbook_or_default", "tile_utility"]
