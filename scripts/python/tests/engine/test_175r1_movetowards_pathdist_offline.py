"""#175-r1 -- le producteur de `movetowards_pathdist`, et la FORME COMMUNE des trois `leaf_ctx`.

CE QUE CE FICHIER GARDE
-----------------------
Les deux feuilles `MoveTowardsUnitUtility` (62 `BioMinefield_MoveTowardsTarget` -100/tuile,
63 `MasterOfTheTutelaries_MoveTowardsTarget` -20/tuile) lisaient une cle de `meta` qu'AUCUN
producteur du depot n'ecrivait : elles rendaient 0 partout. Le producteur est livre, et ce fichier
fige ce qui commande son resultat -- tout est LU au decompile (`t6dpr4k06g`) :

  1. les CINQ parametres par sous-classe (identifiant + famille, `Friends`,
     `EffectSourceMustBeParent`, `OnlyUnitsWithAny`). Leur source est le `.ctor` (`mov edx, <imm>`
     puis la surcharge d'`IdunBattle.Core.AbilityOrEffect$$op_Implicit`, qui NOMME la famille) et
     les DECLARATIONS Il2CppDumper, corroborees par les tailles d'instance de
     `data/symbols/<build>/frida/classes.tsv` : base 112, BioMinefield 120, MoT 128 -- donc le
     `+0x70` ecrit par chaque `.ctor` est un champ DE LA SOUS-CLASSE, et les deux drapeaux ne sont
     PAS le meme champ ;
  2. `Count` = NOEUDS, extremites INCLUSES (`route+0x18` = `List<T>._size`) : la tuile de la cible
     vaut **1**, pas 0. Un off-by-one y coute une tuile entiere de poids (-100 pour BioMinefield) ;
  3. la distance est celle du CHEMIN (`PathfinderType.IgnoreTerrain`), jamais `hexgeo.distance` --
     et le TEMOIN de non-degenerescence est assertionne NON VIDE ;
  4. les quatre coupures du corps : gate de trait, `Friends`, `SourceUnitId == GetParent(mover)`,
     `GetActiveEffects` (un effet INACTIF ne designe aucun porteur).

Et la FORME COMMUNE des trois jumeaux de `leaf_ctx` (`_unit_record` pour les deux regimes runner,
`scene_tile_leaf_ctx`, `_adjacent_units`) : une cle presente d'un seul cote rendrait la feuille
muette sur les deux autres chemins, SANS ERREUR. C'est le trou que `#922-r2` nomme pour
`self_effects` ; il est garde ici pour les quatre cles d'enregistrement et les deux cles de sujet.

100 % OFFLINE : aucun runner, aucun RPC. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PY = Path(__file__).resolve().parents[2]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

import hexgeo                                                              # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                    # noqa: E402
from engine.utilities import tile as T                                     # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LE FOYER : producteur, feuilles, et les trois constructeurs de ctx.
        "scripts/python/engine/utilities/tile.py",
        # LE PATHFINDER dont ce producteur consomme le jumeau en domaine POSITION.
        "scripts/python/engine/entities/pathfinding/ignore_terrain_pathfinder.py",
        # Le voisinage et la porte d'elevation partages.
        "scripts/python/engine/battle_query.py",
        "scripts/python/hexgeo.py",
        # Les enums cites au site (identifiants et traits) : un renumerotage change la valeur
        # ECRITE, que l'etage 1 gele.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/utilities/utility_type.py",
        "scripts/python/engine/weights.py",
        # Les boards du depot : l'etage 3 mesure l'ecart chemin/hex sur eux.
        "data/boards/**",
    ),
    # `True` : l'etage 1 gele des ORDINAUX d'enum, que le mirror re-derive du build ; l'etage 3
    # lit `data/boards/`, entree versionnee qui bouge avec le jeu.
    "build": True,
    "toujours": False,
    "raison": ("garde un producteur de `meta` et sa feuille ; ne monte aucun runner et ne lit que "
               "les foyers ci-dessus + les boards versionnes"),
}

BIOMINE = int(EffectType.BioMinefield_Target)              # 1315
MOT = int(ActiveAbilityType.MasterOfTheTutelaries)         # 1096
BOARDS = _PY.parents[1] / "data" / "boards" / "global"


# ================================================================================================
# ETAGE 1 -- les CINQ parametres par sous-classe, GELES a la valeur LUE
# ================================================================================================
def test_les_parametres_lus_au_ctor_sont_ceux_ecrits_au_site():
    """`probe_313` confronte un MIRROR au build ; il redevient vert des qu'on regenere le mirror.
    Ce qu'il ne garde pas, c'est l'ordinal ECRIT ICI -- d'ou ce gel."""
    bm = T.BioMinefield_MoveTowardsTargetUtility()
    mt = T.MasterOfTheTutelaries_MoveTowardsTargetUtility()

    # `mov edx, 0x523` puis `AbilityOrEffect.op_Implicit(EffectType)` -> `set_Effect`.
    assert bm._ABILITY_ID == 1315 == BIOMINE
    assert bm._IDENTIFIER_KIND == "effect"
    # `+0x70` de la SOUS-CLASSE (taille 120 vs base 112) = `EffectSourceMustBeParent`.
    assert bm._EFFECT_SOURCE_MUST_BE_PARENT is True
    # NON override -> backing field de la base, JAMAIS ecrit.
    assert bm._FRIENDS is False
    assert bm._TRAIT_GATE is None

    # `mov edx, 0x448` puis `AbilityOrEffect.op_Implicit(ActiveAbilityType)` -> `set_ActiveAbility`.
    assert mt._ABILITY_ID == 1096 == MOT
    assert mt._IDENTIFIER_KIND == "active"
    # `+0x70` de CETTE sous-classe (taille 128) = `Friends` ; `+0x78` = `OnlyUnitsWithAny`.
    assert mt._FRIENDS is True
    assert mt._EFFECT_SOURCE_MUST_BE_PARENT is False
    assert {int(x) for x in mt._TRAIT_GATE} == {2026, 1019}
    assert {int(x) for x in mt._TRAIT_GATE} == {int(UnitTrait.Chaos), int(UnitTrait.Daemon)}


def test_les_deux_identifiants_ne_designent_PAS_la_meme_famille():
    """CONTRE-EPREUVE de l'appariement : `1315` n'est PAS un `ActiveAbilityType` et `1096` n'est
    PAS un `EffectType` de ce build. Si l'un des deux l'etait, une confusion de famille serait
    silencieuse en ordinal -- exactement le mode de defaillance que le CLAUDE.md nomme."""
    actifs = {int(x) for x in ActiveAbilityType}
    effets = {int(x) for x in EffectType}
    # Le NON-VIDE des deux jeux, sinon l'assertion suivante serait vacante.
    assert len(actifs) > 100 and len(effets) > 100
    assert BIOMINE in effets
    assert MOT in actifs
    # Ce qui rend l'appariement DISCRIMINANT : au moins un des deux ordinaux ne vit pas dans
    # l'autre enum (s'ils y vivaient tous les deux, seule la LECTURE du `.ctor` trancherait).
    assert (BIOMINE not in actifs) or (MOT not in effets)


# ================================================================================================
# ETAGE 2 -- le producteur, ses quatre coupures et son off-by-one
# ================================================================================================
def _cartes_plates(w=5, h=5):
    """Board PLAT et pleinement walkable : le voisinage `hexgeo` restreint au domaine suffit, et la
    distance de chemin y coincide avec la distance hex -- c'est le regime ou l'etage 2 mesure la
    MECANIQUE, pas la geometrie."""
    pos = [(c, r) for c in range(w) for r in range(h)]
    return ({p: 0 for p in pos}, {p: True for p in pos}, None)


def _lc_mot(mover, porteur, traits=(int(UnitTrait.Chaos),), ami=True):
    elev, walk, neigh = _cartes_plates()
    rec = {"id": 2, "pos": porteur, "triggered": (), "active": (MOT,), "traits": (),
           "effects": (), "owned_effects": (), "parent": None}
    return {"uid": 1, "self_pos": mover, "unit_traits": list(traits),
            "unit_active_abilities": (), "unit_parent_id": None, "self_owned_effects": (),
            "friend_units": [rec] if ami else [], "enemy_units": [] if ami else [rec],
            "elev_by_pos": elev, "walkable_by_pos": walk, "neigh_by_pos": neigh}


def _lc_bio(mover, cible, parent_id=7, source_id=7, active=True):
    elev, walk, neigh = _cartes_plates()
    return {"uid": 1, "self_pos": mover, "unit_traits": (), "unit_active_abilities": (),
            "unit_parent_id": parent_id, "self_owned_effects": (), "friend_units": [],
            "enemy_units": [{"id": 3, "pos": cible, "triggered": (), "active": (), "traits": (),
                             "effects": (),
                             "owned_effects": ({"type": BIOMINE, "source": source_id,
                                                "active": active},),
                             "parent": None}],
            "elev_by_pos": elev, "walkable_by_pos": walk, "neigh_by_pos": neigh}


def test_count_compte_les_noeuds_extremites_incluses():
    """`route+0x18` = `List<T>._size` : la tuile de la CIBLE vaut 1, sa voisine 2. Le port qui
    rendrait le nombre d'ARETES sous-compterait d'exactement une tuile de poids."""
    lc = _lc_mot((0, 0), (2, 2))
    carte = T._movetowards_pathdist_by_pos(lc)[MOT]
    assert carte[(2, 2)] == 1
    voisines = [q for q in hexgeo.neighbors(2, 2) if q in carte]
    assert voisines, "temoin degenere : aucune voisine de la cible dans la carte"
    assert all(carte[q] == 2 for q in voisines), {q: carte[q] for q in voisines}


def test_les_quatre_coupures_du_corps():
    """Chacune ETEINT le terme, et le temoin ON est non nul dans les quatre cas."""
    # ON : mover Chaos, porteur AMI de l'ACTIVE 1096.
    assert MOT in T._movetowards_pathdist_by_pos(_lc_mot((0, 0), (2, 2)))
    # 1. `OnlyUnitsWithAny = [Chaos, Daemon]` : sans trait, l'iterateur ne yielde RIEN.
    assert T._movetowards_pathdist_by_pos(_lc_mot((0, 0), (2, 2), traits=())) == {}
    # 1bis. Daemon suffit AUSSI (le gate est un `Any`, pas un `All`).
    assert MOT in T._movetowards_pathdist_by_pos(
        _lc_mot((0, 0), (2, 2), traits=(int(UnitTrait.Daemon),)))
    # 2. `Friends = true` : un porteur ENNEMI ne devient jamais la cible.
    assert T._movetowards_pathdist_by_pos(_lc_mot((0, 0), (2, 2), ami=False)) == {}
    # 3. `EffectComponent.SourceUnitId == GetParent(mover).Id`, et `GetParent == null` -> 0.
    assert BIOMINE in T._movetowards_pathdist_by_pos(_lc_bio((0, 0), (2, 2)))
    assert T._movetowards_pathdist_by_pos(_lc_bio((0, 0), (2, 2), source_id=8)) == {}
    assert T._movetowards_pathdist_by_pos(_lc_bio((0, 0), (2, 2), parent_id=None)) == {}
    # 4. `GetActiveEffects(1315)` : un effet POSE mais INACTIF ne designe aucun porteur.
    assert T._movetowards_pathdist_by_pos(_lc_bio((0, 0), (2, 2), active=False)) == {}


def test_la_feuille_lit_la_cle_RENOMMEE_et_multiplie_par_le_poids_BC():
    """Le port lisait `movetowards_hexdist`, un nom qui MENTAIT et qu'aucun ecrivain ne posait.
    Ici : la cle est `movetowards_pathdist`, et le terme vaut `Count x PerTileDistance`."""
    from engine.weights import load as load_weights
    wt = load_weights()
    lc = _lc_mot((0, 0), (2, 2))
    meta = T.apply_tile_attributes({}, (0, 0), lc)
    assert "movetowards_hexdist" not in meta
    d = meta["movetowards_pathdist"][MOT]
    assert d > 1
    leaf = T.MasterOfTheTutelaries_MoveTowardsTargetUtility()
    attendu = d * wt.sub("MasterOfTheTutelaries_MoveTowardsTarget", "PerTileDistance")
    assert leaf.evaluate((0, 0), meta, lc, wt) == attendu
    # Le poids est NEGATIF au gameconfig : le terme tire donc vers la cible.
    assert attendu < 0, attendu
    # Et la feuille SANS la cle rend 0 (degradation, pas erreur).
    assert leaf.evaluate((0, 0), {}, lc, wt) == 0.0


def test_le_terme_DECROIT_quand_on_se_rapproche():
    """Le gradient observable : le poids est negatif, donc la tuile la plus proche marque le
    MOINS mal. Sans cette assertion, un signe inverse passerait."""
    from engine.weights import load as load_weights
    wt = load_weights()
    lc = _lc_mot((0, 0), (2, 2))
    leaf = T.MasterOfTheTutelaries_MoveTowardsTargetUtility()
    vals = {}
    for p in [(0, 0), (1, 1), (2, 2)]:
        vals[p] = leaf.evaluate(p, T.apply_tile_attributes({}, p, lc), lc, wt)
    assert vals[(2, 2)] > vals[(1, 1)] > vals[(0, 0)], vals


def test_le_memo_ne_sert_pas_une_carte_perimee():
    """La carte est memoisee sur le `leaf_ctx` (une passe de Dijkstra par decision). La cle du
    memo est l'ensemble des cibles RESOLUES : deplacer le porteur DOIT recalculer."""
    lc = _lc_mot((0, 0), (2, 2))
    avant = T._movetowards_pathdist_by_pos(lc)[MOT][(0, 0)]
    lc["friend_units"][0]["pos"] = (0, 1)
    apres = T._movetowards_pathdist_by_pos(lc)[MOT][(0, 0)]
    assert apres != avant, (avant, apres)


# ================================================================================================
# ETAGE 3 -- CHEMIN != HEX, avec temoin NON VIDE (assertionne)
# ================================================================================================
def _board_du_depot(board_id: str):
    p = BOARDS / (board_id + ".json")
    if not p.exists():
        return None
    import json
    raw = json.loads(p.read_text(encoding="utf-8")).get("board") or {}
    elev, walk = {}, {}
    for c, col in enumerate(raw.get("Tiles") or []):
        for r, t in enumerate((col or {}).get("Tile") or []):
            elev[(c, r)] = t.get("Elevation")
            walk[(c, r)] = not bool(t.get("ForceUnplayable"))
    return elev, walk


def test_la_distance_est_celle_du_CHEMIN_pas_hexgeo():
    """Sur un board a RELIEF, `Count - 1` s'ecarte de `hexgeo.distance` -- c'est exactement ce que
    le nom `movetowards_hexdist` niait. Le temoin est ASSERTIONNE NON VIDE : un board plat rendrait
    un accord trivial, donc zero preuve.

    ⚠ Une amplitude ne s'estime pas depuis UN board : le balayage porte sur PLUSIEURS boards du
    depot, et le compte par board est imprime dans le message d'assertion."""
    par_board = {}
    for bid in ("MC1_67", "C1_74", "C3_59", "C4_09", "C6_09"):
        b = _board_du_depot(bid)
        if b is None:
            continue
        elev, walk = b
        postes = sorted(p for p, w in walk.items() if w)
        if len(postes) < 10:
            continue
        cible = postes[len(postes) // 2]
        lc = {"uid": 1, "self_pos": postes[0], "unit_traits": [int(UnitTrait.Chaos)],
              "unit_active_abilities": (), "unit_parent_id": None, "self_owned_effects": (),
              "friend_units": [{"id": 2, "pos": cible, "triggered": (), "active": (MOT,),
                                "traits": (), "effects": (), "owned_effects": (), "parent": None}],
              "enemy_units": [], "elev_by_pos": elev, "walkable_by_pos": walk,
              "neigh_by_pos": None}
        carte = T._movetowards_pathdist_by_pos(lc).get(MOT) or {}
        par_board[bid] = (sum(1 for p, n in carte.items()
                              if (n - 1) != hexgeo.distance(p, cible)), len(carte))
    assert par_board, "PAS MESURE : aucun board du depot n'a pu etre charge"
    assert any(e > 0 for e, _n in par_board.values()), par_board


def test_une_cible_injoignable_ne_pose_aucune_cle():
    """`GetPath` rend `null` -> `min` reste `null` -> la feuille yielde 0. Le port ne pose PAS la
    cle plutot que d'inventer une distance."""
    elev = {(0, 0): 0, (0, 1): 0, (4, 4): 0}
    walk = {(0, 0): True, (0, 1): True, (4, 4): True}
    lc = {"uid": 1, "self_pos": (0, 0), "unit_traits": [int(UnitTrait.Chaos)],
          "unit_active_abilities": (), "unit_parent_id": None, "self_owned_effects": (),
          "friend_units": [{"id": 2, "pos": (4, 4), "triggered": (), "active": (MOT,),
                            "traits": (), "effects": (), "owned_effects": (), "parent": None}],
          "enemy_units": [], "elev_by_pos": elev, "walkable_by_pos": walk, "neigh_by_pos": None}
    carte = T._movetowards_pathdist_by_pos(lc)[MOT]
    assert (4, 4) in carte and (0, 0) not in carte, carte
    assert "movetowards_pathdist" not in T.apply_tile_attributes({}, (0, 0), lc)


# ================================================================================================
# ETAGE 4 -- la FORME COMMUNE des trois jumeaux de `leaf_ctx` (#922-r2, transpose)
# ================================================================================================
class _Pos:
    def __init__(self, col, row):
        self.col, self.row = col, row


class _EntiteNue:
    """Entite de runner sans AUCUN composant -- le regime le plus degrade, et donc celui ou une
    cle ABSENTE d'un seul des trois jumeaux se verrait le moins."""

    def get_component(self, _cls):
        return None


class _SceneDouble:
    """Double minimal de `Scene` -- exactement ce que `scene_tile_leaf_ctx` interroge."""

    def __init__(self):
        self.units = [{"id": 1, "visualId": "tyranBiovore", "alive": True, "team": 0,
                       "pos": {"col": 0, "row": 0}},
                      {"id": 2, "visualId": "tyranBiovore", "alive": True, "team": 0,
                       "pos": {"col": 1, "row": 1}}]
        self.vis_by_id = {1: "tyranBiovore", 2: "tyranBiovore"}
        self.eff_state = None
        self.board = None
        self.elev_by_pos = {}
        self.hpmax_by_id = {}
        self.tile_effects_by_pos = {}

    def team(self, _uid):
        return 0

    def ctx(self, _uid):
        return None

    def hp(self, _uid):
        return 10

    def hpmax(self, _uid):
        return 10

    def parent(self, _uid):
        return None

    def pos(self, uid):
        return (0, 0) if uid == 1 else (1, 1)


class _CtxDouble:
    """Double minimal d'`AiDecisionContext` -- ce que `tile_leaf_ctx` / `_adjacent_units` lisent."""

    def __init__(self):
        self.uid = 1
        self.units = [{"id": 1, "visualId": "tyranBiovore", "alive": True, "ctrl": True,
                       "pos": {"col": 0, "row": 0}, "hp": 10, "effects": ()},
                      {"id": 2, "visualId": "tyranBiovore", "alive": True, "ctrl": True,
                       "pos": {"col": 1, "row": 1}, "hp": 10,
                       "effects": ({"name": "BioMinefield_Target", "effectType": BIOMINE,
                                    "source": 9, "active": True},)}]
        self.me = self.units[0]
        self.scene = None
        self.hpmax_by_id = {}
        self.fpos = [(1, 1)]


#: Les cles d'ENREGISTREMENT que les trois jumeaux doivent porter a l'identique. `owned_effects` et
#: `parent` sont celles que #175-r1 / #433-r4-r3-r2 ajoutent ; les deux autres sont la pour que le
#: cliquet ne se reduise pas a ce que cette tranche vient d'ecrire.
CLES_ENREGISTREMENT = {"pos", "id", "triggered", "active", "traits", "effects", "hp", "hp_max",
                       "parent", "owned_effects"}

#: Les cles de SUJET, meme raison (c'est le trou nomme par #922-r2 pour `self_effects`).
CLES_SUJET = {"uid", "self_pos", "self_effects", "self_owned_effects", "unit_parent_id",
              "unit_traits", "unit_active_abilities", "unit_triggered_abilities"}


def _rec_runner():
    return T._unit_record(_EntiteNue(), 2, _Pos(1, 1), None)


def _rec_scene():
    lc = T.scene_tile_leaf_ctx(_SceneDouble(), 1)
    return (lc.get("friend_units") or lc.get("enemy_units"))[0]


def _rec_decision():
    lc = T.tile_leaf_ctx(_CtxDouble())
    return (lc.get("friend_units") or lc.get("enemy_units"))[0]


def test_les_trois_jumeaux_portent_LA_MEME_forme_d_enregistrement():
    """Une cle presente d'un seul cote rend la feuille muette sur les deux autres chemins, SANS
    ERREUR -- c'est le mode de defaillance que `_unit_record` documente pour lui-meme."""
    recs = {"runner": _rec_runner(), "scene": _rec_scene(), "decision": _rec_decision()}
    for nom, rec in recs.items():
        manquantes = CLES_ENREGISTREMENT - set(rec)
        assert not manquantes, "%s : cles manquantes %r" % (nom, sorted(manquantes))
    # ... et le TYPE de la cle neuve est le meme des trois cotes (tuple de dicts a 3 champs).
    for nom, rec in recs.items():
        oe = rec["owned_effects"]
        assert isinstance(oe, tuple), (nom, type(oe))
        for e in oe:
            assert set(e) == {"type", "source", "active"}, (nom, e)


def test_les_trois_jumeaux_portent_LES_MEMES_cles_de_sujet():
    lcs = {"scene": T.scene_tile_leaf_ctx(_SceneDouble(), 1),
           "decision": T.tile_leaf_ctx(_CtxDouble())}
    for nom, lc in lcs.items():
        manquantes = CLES_SUJET - set(lc)
        assert not manquantes, "%s : cles de sujet manquantes %r" % (nom, sorted(manquantes))


def test_le_canal_decision_publie_bien_type_et_source():
    """La reserve de `case-175r` Sec.3 -- << `decisionView.effects` publie-t-il un `source` ? non
    verifie >> -- est LEVEE : `frida/hooks/game/effects.ts::EffectInfo` publie `effectType`,
    `source` et `active`, et le jumeau DECISION les fait remonter tels quels."""
    rec = _rec_decision()
    assert rec["owned_effects"] == ({"type": BIOMINE, "source": 9, "active": True},), rec
