"""#287-r11-r2-r1-r1 -- GARDE du `0` d'`IdunBattle.Core.Services.BattleQuery$$GetUnitMaxRange`, que
`mv71._drone_attack_range` MAPPAIT SUR `1`.

Le decompile, relu verbatim sur le build courant :

    config = GetUnitConfig(unitId);
    if (config == null)           return 0;
    if (config.Weapons == null)   return 0;
    max = 0;
    foreach (w in config.Weapons) max = Math.Max(max, w.Range.HasValue ? w.Range.Value : 1);
    return max;                                     // liste VIDE -> 0

Le corps LOCAL du port ecrivait `int(w.get("Range") or 0)` puis `return mx if mx > 0 else 1` : il
rendait **1** la ou le natif rend **0**, et **0** la ou le natif rend **1** pour une arme sans
portee. Les deux fautes se COMPENSAIENT sur le seul regime exerce (melee pure), ce qui est
exactement pourquoi elles ont survecu.

CE QUE CA CHANGE : `mv71._pick_tile` construit son anneau par `1 <= d <= rng`. A `rng = 0` l'anneau
est VIDE et `PickTile` rend `None` -> le gate REFUSE ; a `rng = 1` les tuiles ADJACENTES a la cible
redeviennent candidates -> le gate ACCEPTE une cible que le natif refuse. Direction PERMISSIVE, la
meme que celle que #287-r11-r2-r1 vient de fermer.

CONFRONTE LIVE : `probe_287r11r2r1r1_portee_nulle_live.py` -- board `C3_47`, seed BC dont
`BC.Units[tauSmnDroneSniper].Weapons` est VIDE (`BattleQuery$$GetUnitConfig` lit `BC.Units[]`, pas
un catalogue global). Natif `0x1 ValidRequest` contre `0x0` sous le mapping d'avant : **2 SOUS-refus
au temoin**, sur les deux porteurs du gate.

ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        # PROPRE A CE FICHIER, pris LARGE : le gate de 1076 traverse `abilities/loki/mv71.py`,
        # `services/battle_query.py` (le foyer `get_unit_max_range`), `abilities/targeting.py` et
        # la geometrie `services/movement_query.py`.
        "scripts/python/engine/**/*.py",
        # LA CASCADE DES CONFTEST, mesuree (`probe_486r15`), pas devinee : tout fichier de
        # `tests/engine/` traine ces 16 modules racine par la seule cascade des conftest, sans en
        # toucher aucun (residu #531).
        "scripts/python/board.py", "scripts/python/catalog_inject.py",
        "scripts/python/engine_agreement_stages.py", "scripts/python/engine_validate.py",
        "scripts/python/hexgeo.py", "scripts/python/host_inputs.py",
        "scripts/python/rl_collect_batch.py", "scripts/python/stream_events.py",
        "scripts/python/symbols_layout.py", "scripts/python/unit_map.py",
        "scripts/python/probe_17_active_ability_used_gate.py",
        "scripts/python/probe_17_hammer_corpse.py",
        "scripts/python/probe_17_martial_inspiration.py",
        "scripts/python/probe_308_normal_attack_bonus.py",
        "scripts/python/probe_316_ability_prediction_target_traits.py",
        "scripts/python/probe_350r3b_triggered_average_forms.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Garde OFFLINE d'un mirror de fonction native (`GetUnitMaxRange`) et de son effet sur "
              "l'anneau de `PickTile`. Aucun RPC, aucun runner : la confrontation live vit dans "
              "`probe_287r11r2r1r1_portee_nulle_live.py`.",
}

import gameconfig as GC                                                     # noqa: E402
import pytest                                                               # noqa: E402

from engine.runner.abilities.loki import mv71                               # noqa: E402
from engine.services import battle_query as BQ                              # noqa: E402

DRONE = "tauSmnDroneSniper"


# =================================================================================================
# ETAGE 1 -- LE FOYER EST UNIQUE, ET LA DELEGATION MORD
# =================================================================================================

def test_drone_attack_range_DELEGUE_au_foyer_natif(monkeypatch):
    """`_drone_attack_range` doit APPELER `services.battle_query.get_unit_max_range`, pas en porter
    une copie. Verifie par MORSURE : un patch pose sur le FOYER doit se voir a l'appel.

    Sans ce cran, une copie locale re-divergerait librement -- c'est exactement l'etat d'avant, ou
    deux mirrors de la MEME fonction native cohabitaient (`battle_query.get_unit_max_range`, juste,
    et `mv71._drone_attack_range`, faux)."""
    monkeypatch.setattr(BQ, "get_unit_max_range", lambda uid: 99)
    assert mv71._drone_attack_range(DRONE) == 99, (
        "le patch du foyer NE MORD PAS : `_drone_attack_range` porte une copie locale")


# =================================================================================================
# ETAGE 2 -- LA TABLE DES REGIMES, LUE AU DECOMPILE (deux `return 0` DISTINCTS de la boucle)
# =================================================================================================

@pytest.mark.parametrize("cfg,attendu,pourquoi", [
    (None, 0, "`GetUnitConfig(unitId) == null` -> `return 0`"),
    ({}, 0, "`config.Weapons == null` -> `return 0`"),
    ({"weapons": []}, 0, "liste VIDE : la boucle ne tourne pas, `max` reste a son initiale `0`"),
    ({"weapons": [{"Range": 0}]}, 0, "`HasValue` VRAI et valeur `0` -> `Math.Max(0, 0)`"),
    ({"weapons": [{"Range": None}]}, 1, "`HasValue` FAUX -> le litteral `uVar6 = 1`"),
    ({"weapons": [{}]}, 1, "champ absent = `Nullable` sans valeur -> `1`"),
    ({"weapons": [{"Range": None}, {"Range": 4}]}, 4, "`Math.Max(1, 4)`"),
    ({"weapons": [{"Range": 4}, {"Range": None}]}, 4, "l'ordre ne change rien : c'est un `max`"),
])
def test_les_regimes_de_GetUnitMaxRange(monkeypatch, cfg, attendu, pourquoi):
    monkeypatch.setattr(GC, "unit", lambda uid, *a, **k: cfg)
    assert mv71._drone_attack_range("peu-importe") == attendu, pourquoi


def test_les_DEUX_fautes_du_corps_local_et_leur_COMPENSATION():
    """CONTRE-EPREUVE de l'etage 2 : on RE-JOUE le corps d'avant et on montre OU il divergeait --
    et surtout ou il ne divergeait PAS, par compensation. Sans ce test, une lecture rapide
    conclurait « le corps d'avant etait faux partout », ce qui est faux et rendrait le regime
    exerce incomprehensible."""
    def avant(cfg):
        ranges = [int(w.get("Range") or 0) for w in ((cfg or {}).get("weapons") or [])]
        mx = max(ranges) if ranges else 0
        return mx if mx > 0 else 1

    def natif(cfg):
        if cfg is None or not cfg.get("weapons"):
            return 0
        return max(1 if (w or {}).get("Range") is None else int(w["Range"])
                   for w in cfg["weapons"])

    divergents = [c for c in (None, {}, {"weapons": []}, {"weapons": [{"Range": 0}]})
                  if avant(c) != natif(c)]
    accordants = [c for c in ({"weapons": [{"Range": None}]}, {"weapons": [{}]},
                              {"weapons": [{"Range": None}, {"Range": 4}]})
                  if avant(c) == natif(c)]
    assert len(divergents) == 4, ("les quatre regimes a `0` doivent TOUS diverger : %r"
                                  % divergents)
    assert len(accordants) == 3, ("les trois regimes a portee non nulle s'accordaient DEJA "
                                  "(compensation `or 0` / `mx > 0 else 1`) : %r" % accordants)


# =================================================================================================
# ETAGE 3 -- CE QUE LA PORTEE DECIDE : LE RAYON DE L'ANNEAU DE `PickTile`
# =================================================================================================

def _board(cols=7, rows=7):
    """Le VRAI `Board` du moteur (grille pleine, marchable, elevation 0) -- pas un stand-in : le
    chemin traverse `services.movement_query`, qui lit `by_coord` et les dimensions jouables."""
    from engine.entities.pathfinding.board import Board
    tiles, n = [], 1
    for col in range(cols):
        for row in range(rows):
            tiles.append({"id": n, "col": col, "row": row, "walkable": True, "elevation": 0})
            n += 1
    return Board(tiles, adjacency="evenq")


def _etat_pick_tile():
    """Un caster et une cible a d=3, sur un board plat et vide. A portee 4 l'anneau contient des
    tuiles ; a portee 1, seules les VOISINES de la cible ; a portee 0, AUCUNE."""
    from engine.runner.state import State
    from engine.runner.components import (OwnerComponent, PositionComponent, UnitComponent)
    st = State()
    st.board = _board()
    for uid, team, pos in ((1, 1, (3, 3)), (2, 2, (3, 6))):
        e = st.add_entity(uid)
        e.add_component(UnitComponent(visual_id="u%d" % uid, alive=True))
        e.add_component(OwnerComponent(team=team, player=team))
        e.add_component(PositionComponent(col=pos[0], row=pos[1]))
    return st


@pytest.mark.parametrize("rng,attendu", [(4, True), (1, True), (0, False)])
def test_l_anneau_de_pick_tile_suit_la_portee(monkeypatch, rng, attendu):
    """`1 <= d <= rng` : a `rng = 0` l'intervalle est VIDE, donc `PickTile` rend `None` et le gate
    REFUSE. C'est le seul etage par lequel le `0` natif se voit."""
    st = _etat_pick_tile()
    monkeypatch.setattr(mv71, "_drone_attack_range", lambda uid: rng)
    tid = mv71._pick_tile(st, 1, 2, DRONE, 3, first_only=True)
    assert (tid is not None) is attendu, (
        "portee %d -> tuile %r, attendu %s" % (rng, tid, "une tuile" if attendu else "None"))


def test_la_bascule_0_vers_1_est_ce_qui_SEPARE_le_port_du_natif(monkeypatch):
    """LE TEMOIN NON NUL de la tranche, en une ligne : sur le MEME etat, `rng = 0` refuse et
    `rng = 1` accepte. Un port qui mappe `0` sur `1` accepte donc une cible que le natif refuse.

    Le test assertionne son propre non-vide : si les deux portees rendaient la meme chose, la
    tranche ne changerait aucun observable et ce cliquet ne garderait rien."""
    st = _etat_pick_tile()
    monkeypatch.setattr(mv71, "_drone_attack_range", lambda uid: 0)
    zero = mv71._pick_tile(st, 1, 2, DRONE, 3, first_only=True)
    monkeypatch.setattr(mv71, "_drone_attack_range", lambda uid: 1)
    un = mv71._pick_tile(st, 1, 2, DRONE, 3, first_only=True)
    assert zero is None and un is not None, (zero, un)


# =================================================================================================
# ETAGE 4 -- LE REGIME EXISTE : des unites SANS ARME, dans les deux substrats
# =================================================================================================

def test_le_regime_sans_arme_existe_dans_le_catalogue():
    """« NON EXERCE » n'est pas « inoffensif ». Le compte est DERIVE, pas cite -- et le test
    assertionne son propre non-vide : un catalogue ou toutes les unites porteraient une arme
    rendrait cette tranche purement theorique, et il faudrait le savoir."""
    sans = [uid for uid in GC.all_unit_ids() if not (GC.unit(uid) or {}).get("weapons")]
    assert sans, ("aucune unite du gameconfig sans arme : le regime `GetUnitMaxRange == 0` serait "
                  "inatteignable et ce cliquet ne garderait rien")
    assert DRONE not in sans, (
        "`%s` porte une arme -- c'est ce qui rend le regime NON EXERCE sans montage, et ce qui "
        "impose le seed BC mute du probe live" % DRONE)


def test_le_drone_du_gameconfig_rend_bien_sa_portee_mesuree():
    """Anti-regression du regime NOMINAL : la delegation ne doit pas changer la valeur que le port
    lisait deja (l'arme de portee 4 du drone)."""
    assert mv71._drone_attack_range(DRONE) == 4
    assert BQ.get_unit_max_range(DRONE) == 4, "les deux voies doivent rendre la MEME valeur"
