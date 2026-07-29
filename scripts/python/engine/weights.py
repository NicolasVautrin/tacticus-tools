"""Loader des poids d'utilité de l'IA native (`BattleConfiguration.Utilities`).

Config NOMMÉ (pas d'offsets binaires) → on charge tel quel depuis la BC JSON sur disque.
2 profils : `Default` (scoring d'action) et `MovementSuggestion`. cf. docs/rl/playbook-engine.md §1.5.

Testable 100 % OFFLINE (la BC JSON est sur disque, pas besoin du jeu).
"""
from __future__ import annotations

import json
from pathlib import Path

# scripts/python/engine/weights.py -> parents: [0]=engine [1]=python [2]=scripts [3]=repo
_REPO = Path(__file__).resolve().parents[3]
# seed BC template (data/ gitignore, per-hash) — regenere par `dump_boards.py` (#159).
DEFAULT_BC = _REPO / "data" / "seed-bc.json"


class Weights:
    """Accès typé aux poids `Utilities`. Structure RÉELLE (vérifiée sur la BC) =
    dict 2 niveaux : `Default.<Category>.<SubKey> -> number` (les 54 catégories de
    Default sont TOUTES des objets). Tout best-effort : clé absente = poids 0."""

    def __init__(self, utilities: dict):
        self.default: dict = utilities.get("Default", {}) or {}
        self.movement: dict = utilities.get("MovementSuggestion", {}) or {}
        self.active: dict = self.default.get("ActiveAbilities", {}) or {}

    def sub(self, category: str, subkey: str, default: float = 0) -> float:
        """Poids `Default.<category>.<subkey>` (ex. sub('KillUnit','DefinitelyKill')=100).
        0 si la catégorie ou la sous-clé manque."""
        cat = self.default.get(category)
        if isinstance(cat, dict):
            v = cat.get(subkey, default)
            return v if isinstance(v, (int, float)) else default
        return default

    def category(self, name: str) -> dict:
        """Le dict d'une catégorie Default (pour itérer / matcher des sous-clés nommées
        type TriggeredAbilities, ActiveAbilities, UnitOrder)."""
        c = self.default.get(name)
        return c if isinstance(c, dict) else {}

    def movement_sub(self, category: str, subkey: str, default: float = 0) -> float:
        """Poids du profil `MovementSuggestion.<category>.<subkey>` (ex.
        movement_sub('RangedAdjacentEnemy','HasAdjacentEnemy')=-50). 0 si absent."""
        cat = self.movement.get(category)
        if isinstance(cat, dict):
            v = cat.get(subkey, default)
            return v if isinstance(v, (int, float)) else default
        return default

    # --- raccourcis nommés (les termes du barème de §1.1) ---
    def kill(self, definite: bool) -> float:
        return self.sub("KillUnit", "DefinitelyKill" if definite else "PossibleKill")

    def overkill(self, definite: bool) -> float:
        return self.sub("OverkillUnit", "DefinitelyOverkill" if definite else "PossibleOverkill")

    def active_knob(self, name: str, default: float = 0) -> float:
        v = self.active.get(name, default)
        return v if isinstance(v, (int, float)) else default

    def triggered(self, name: str, default: float = 0) -> float:
        return self.sub("TriggeredAbilities", name, default)

    def unit_order(self, trait_or_ability: str, default: float = 0) -> float:
        return self.sub("UnitOrder", trait_or_ability, default)

    def __repr__(self) -> str:
        return (f"Weights(default_categories={len(self.default)}, "
                f"active_knobs={len(self.active)}, "
                f"triggered={len(self.category('TriggeredAbilities'))}, "
                f"unit_order={len(self.category('UnitOrder'))})")


def load(bc_path: str | Path | None = None) -> Weights:
    """Charge les poids depuis une BC JSON (défaut = la seed PvP sur disque).

    #27-4 — la table est RE-SYNTHÉTISÉE depuis le gameconfig VIVANT (`aiUtilities`), exactement
    comme le fait `rl_collect_batch._load_seed_bc` pour le runner NATIF
    (`catalog_inject.refresh_ai_utilities`, mirror de
    `Idun.Source.IdunBattle.View.BattleConfigBuilder$$ParseAIUtilitiesConfiguration`). Sans ça les
    deux côtés divergeraient dès qu'un build ajoute une ability : le natif verrait les poids neufs
    (BC rafraîchie) et le moteur les poids de la capture. Repli SILENCIEUX sur la table de la BC si
    le gameconfig n'est pas lisible — `engine.weights` doit rester chargeable 100 % offline."""
    p = Path(bc_path) if bc_path else DEFAULT_BC
    bc = json.loads(p.read_text(encoding="utf-8"))
    try:
        import catalog_inject                     # import tardif : charge le gameconfig (~19 MB)
        live = catalog_inject.ai_utilities_from_gameconfig()
    except Exception:                             # noqa: BLE001 — pas de gameconfig sur disque
        live = None
    return Weights(live or bc.get("Utilities", {}) or {})


if __name__ == "__main__":  # smoke test offline
    wt = load()
    print(wt)
    print("kill(definite)   =", wt.kill(True), "| kill(possible) =", wt.kill(False))
    print("overkill(def)    =", wt.overkill(True), "| overkill(poss) =", wt.overkill(False))
    print("MinDistEnemy/Tile=", wt.sub("MinDistanceToClosestEnemy", "PerTileDistance"))
    print("UnitOrder.Psyker =", wt.unit_order("Psyker"),
          "| WeaverOfFate =", wt.unit_order("WeaverOfFate"))
    print("trig.SUPPRESSIVEFIRE_TargetWithOverwatch =",
          wt.triggered("SUPPRESSIVEFIRE_TargetWithOverwatch"))
    print("knob ArcScourge_AdjacentEnemies =", wt.active_knob("ArcScourge_AdjacentEnemies"))
