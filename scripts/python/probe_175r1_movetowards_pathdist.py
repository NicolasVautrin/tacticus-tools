"""#175-r1 -- le producteur de `meta["movetowards_pathdist"]`, MESURE sur un ctx bati a la main.

    python scripts/python/probe_175r1_movetowards_pathdist.py

CE QUE CE PROBE MESURE
----------------------
Les deux feuilles `MoveTowardsUnitUtility` (62 `BioMinefield_MoveTowardsTarget`,
63 `MasterOfTheTutelaries_MoveTowardsTarget`) rendaient **0 partout** faute de producteur : la cle
`movetowards_hexdist` qu'elles lisaient n'avait AUCUN ecrivain dans le depot. Ce probe monte les
deux regimes sur un board reel (`data/boards/global/<id>.json`) et imprime, tuile par tuile, la
distance produite et le terme de la feuille.

Il imprime AUSSI les contre-epreuves qui separent ce port d'un port approximatif :
  * la distance est celle du CHEMIN (`IgnoreTerrainPathfinder`), pas `hexgeo.distance` -- un mur
    entre la tuile candidate et la cible les separe ;
  * `Count` compte les NOEUDS, extremites INCLUSES (tuile de la cible -> 1, pas 0) ;
  * la gate de trait de la feuille 63 (`OnlyUnitsWithAny = [Chaos, Daemon]`) eteint le terme ;
  * la branche EFFET de la feuille 62 exige `EffectComponent.SourceUnitId == GetParent(mover)`.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                    # noqa: E402
from engine.utilities import tile as T                                     # noqa: E402

REPO = HERE.parent.parent
BOARDS = REPO / "data" / "boards" / "global"

BIOMINE = int(EffectType.BioMinefield_Target)              # 1315
MOT = int(ActiveAbilityType.MasterOfTheTutelaries)         # 1096


def charger_board(board_id: str):
    """Cartes par-position d'un board du depot (`data/boards/global/<id>.json`, grille
    `board.Tiles[col][row]`) -- meme forme que celles des trois `leaf_ctx`.

    `neigh_by_pos` est laisse a `None` : le fichier disque ne porte PAS la liste d'adjacence
    stockee (elle vient du RPC `boardGraph`). Le producteur retombe alors sur le voisinage
    `hexgeo` restreint au domaine, degradation DOCUMENTEE de
    `ignore_terrain_pathfinder.get_path_node_counts_by_pos`. La porte d'elevation
    (`|dElev| <= 1`), elle, est portee par le predicat d'arete et reste exercee."""
    p = BOARDS / (board_id + ".json")
    if not p.exists():
        return None
    raw = json.loads(p.read_text(encoding="utf-8")).get("board") or {}
    cols = raw.get("Tiles") or []
    elev, walk = {}, {}
    for c, col in enumerate(cols):
        for r, t in enumerate((col or {}).get("Tile") or []):
            pos = (c, r)
            elev[pos] = t.get("Elevation")
            walk[pos] = not bool(t.get("ForceUnplayable"))
    return elev, walk, None


def ctx_mot(elev, walk, neigh, mover_pos, summoner_pos, traits):
    """Regime feuille 63 : le mover (Chaos/Daemon) et un AMI porteur de l'ACTIVE 1096."""
    return {"uid": 1, "self_pos": mover_pos, "unit_traits": list(traits),
            "unit_active_abilities": (), "unit_parent_id": None,
            "self_owned_effects": (),
            "friend_units": [{"id": 2, "pos": summoner_pos, "triggered": (), "active": (MOT,),
                              "traits": (), "effects": (), "owned_effects": (), "parent": None}],
            "enemy_units": [],
            "elev_by_pos": elev, "walkable_by_pos": walk, "neigh_by_pos": neigh}


def ctx_biomine(elev, walk, neigh, mover_pos, cible_pos, parent_id, source_id, active=True):
    """Regime feuille 62 : le mover est un summon (`unit_parent_id`), la cible porte l'effet 1315
    dont le `SourceUnitId` est (ou non) ce parent."""
    return {"uid": 1, "self_pos": mover_pos, "unit_traits": (), "unit_active_abilities": (),
            "unit_parent_id": parent_id, "self_owned_effects": (),
            "friend_units": [],
            "enemy_units": [{"id": 3, "pos": cible_pos, "triggered": (), "active": (),
                             "traits": (), "effects": (),
                             "owned_effects": ({"type": BIOMINE, "source": source_id,
                                                "active": active},),
                             "parent": None}],
            "elev_by_pos": elev, "walkable_by_pos": walk, "neigh_by_pos": neigh}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()

    b = charger_board(a.board)
    if b is None:
        print("PAS MESURE : board %s absent de data/boards/global" % a.board)
        return 99
    elev, walk, neigh = b
    postes = sorted(p for p, w in walk.items() if w)
    print("board %s : %d tuiles walkable, canal neigh %s"
          % (a.board, len(postes), "PRESENT" if neigh else "ABSENT"))

    mover = postes[0]
    cible = postes[len(postes) // 2]

    # --- feuille 63 : MasterOfTheTutelaries ---------------------------------------------------
    lc = ctx_mot(elev, walk, neigh, mover, cible, (int(UnitTrait.Chaos),))
    carte = T._movetowards_pathdist_by_pos(lc)
    print("\n[63 MoT] cible=%s mover=%s -> %d entree(s) de carte"
          % (cible, mover, len(carte.get(MOT) or {})))
    d_cible = (carte.get(MOT) or {}).get(cible)
    d_mover = (carte.get(MOT) or {}).get(mover)
    print("  Count(tuile de la cible) = %r   (extremites INCLUSES -> 1 attendu)" % (d_cible,))
    print("  Count(tuile du mover)    = %r" % (d_mover,))

    # gate de trait
    lc_nogate = ctx_mot(elev, walk, neigh, mover, cible, ())
    print("  gate OnlyUnitsWithAny=[Chaos,Daemon] : sans trait -> %d entree(s)"
          % len(T._movetowards_pathdist_by_pos(lc_nogate)))

    # ennemi au lieu d'ami : `Friends = true` doit couper
    lc_enn = ctx_mot(elev, walk, neigh, mover, cible, (int(UnitTrait.Chaos),))
    lc_enn["enemy_units"] = lc_enn.pop("friend_units")
    lc_enn["friend_units"] = []
    print("  porteur ENNEMI (Friends=true) -> %d entree(s)"
          % len(T._movetowards_pathdist_by_pos(lc_enn)))

    # --- feuille 62 : BioMinefield -------------------------------------------------------------
    lc2 = ctx_biomine(elev, walk, neigh, mover, cible, parent_id=7, source_id=7)
    c2 = T._movetowards_pathdist_by_pos(lc2)
    print("\n[62 BioMinefield] source == parent -> %d entree(s), Count(mover)=%r"
          % (len(c2.get(BIOMINE) or {}), (c2.get(BIOMINE) or {}).get(mover)))
    lc3 = ctx_biomine(elev, walk, neigh, mover, cible, parent_id=7, source_id=8)
    print("  source != parent            -> %d entree(s)"
          % len(T._movetowards_pathdist_by_pos(lc3)))
    lc4 = ctx_biomine(elev, walk, neigh, mover, cible, parent_id=None, source_id=7)
    print("  GetParent(mover) == null    -> %d entree(s)"
          % len(T._movetowards_pathdist_by_pos(lc4)))
    lc5 = ctx_biomine(elev, walk, neigh, mover, cible, parent_id=7, source_id=7, active=False)
    print("  effet 1315 INACTIF          -> %d entree(s)  (GetActiveEffects)"
          % len(T._movetowards_pathdist_by_pos(lc5)))

    # --- CHEMIN != HEX : combien de tuiles s'ecartent de la distance hexagonale ? --------------
    import hexgeo
    carte_mot = carte.get(MOT) or {}
    ecarts = [(p, n - 1, hexgeo.distance(p, cible)) for p, n in carte_mot.items()
              if (n - 1) != hexgeo.distance(p, cible)]
    print("\nCHEMIN vs HEX sur %s : %d tuile(s) sur %d s'ecartent"
          % (a.board, len(ecarts), len(carte_mot)))
    for p, dpath, dhex in sorted(ecarts)[:8]:
        print("  %s : chemin(aretes)=%d  hex=%d" % (p, dpath, dhex))
    inj = [p for p in postes if p not in carte_mot]
    print("tuiles walkable INJOIGNABLES depuis la cible : %d (GetPath -> null -> terme 0)"
          % len(inj))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
