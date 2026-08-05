"""LIVE #447-r1-r1 -- la branche INCLUSION du bit 15, sur la face DECISION.

L'ORACLE. `aiMovableTiles {threat: true}` = `MovementQuery$$GetMovableTilesFor` puis
`IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange(unit, <ce set>,
includeNormalAttack: 1)`. La surcharge 3 arguments ITERE les positions candidates
(`UnitPositionExtensions$$ToUnitPositionList`), donc la zone de chaque position `p` est calculee
avec `casterTiles = {p}` -- et `p` y figure ssi
`IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` ajoute `casterTiles`,
c'est-a-dire ssi le bit 15 `CasterIsPossibleTarget` est arme. C'est le MEME etage que la face
CIBLAGE de #447-r1, mais l'autre consommateur : `ability_range._zone_contains_distance` ->
`is_tile_in_range_of_any_ability`, qui n'avait qu'une garde OFFLINE pour la branche << bit arme >>.

⚠ CE QUE CE FICHIER GARDE EN PREMIER, C'EST LE REGIME. La reponse est une UNION sur toutes les
positions candidates : des que deux d'entre elles sont a portee l'une de l'autre, chacune est
couverte DEPUIS L'AUTRE par l'attaque normale et le bit 15 ne decide plus rien. Un accord lu la
serait un accord entre deux modeles algebriquement identiques -- zero preuve. Les quatre porteurs
sont donc places sur des CULS-DE-SAC (une seule voisine passe la porte d'elevation `|dElev| < 2`
de `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`), `overrideRange: 1` borne le pas, et
un CINQUIEME poste en terrain OUVERT MESURE le regime degenere au lieu de le supposer.

Le montage et les mesures vivent dans `probe_447_r1_r1_zone_inclusion_decision.py`
(probe = MESURE, test = GARDE). UN seul runner porte les cinq postes.

ASCII only. Detail : `docs/rl/case-447-r1-r1-inclusion-face-decision.md`.
"""
from __future__ import annotations

import pytest

import probe_447_r1_r1_zone_inclusion_decision as PROBE
from engine.runner.abilities.targeting_rule import TargetingRule as TR


@pytest.fixture(scope="module")
def mesure(live_session) -> dict:
    """UN runner pour les cinq postes -- le natif repond a tout dans le MEME etat.

    Un montage qui ne monte pas est un ECHEC, jamais un skip : `pytest.fail` explicite."""
    res = PROBE.live(live_session)
    if res.get("error"):
        pytest.fail("montage KO : %s" % res["error"], pytrace=False)
    for cle, d in (res.get("postes") or {}).items():
        if d.get("error"):
            pytest.fail("poste %s KO : %s" % (cle, d["error"]), pytrace=False)
    return res


@pytest.fixture(scope="module")
def greffe(live_session) -> dict:
    """Le second runner : `1215 InstrumentsOfVengeance` (portee NON RE-lue, bit 15 arme) GREFFEE sur
    une unite du pool, sur un cul-de-sac. C'est le volet qui a trouve un BUG."""
    res = PROBE.portee_non_lue(live_session)
    if res.get("error"):
        pytest.fail("montage greffe KO : %s" % res["error"], pytrace=False)
    return res


@pytest.fixture(scope="module")
def has_not_moved(live_session) -> dict:
    """La GENERALISATION, sur un porteur du POOL et SANS greffe : `spaceBlackmane` / `1106`, dont la
    portee EST lue et dont le masque porte `CasterHasNotMoved`. Il exerce la 2e clause par un chemin
    entierement different -- ce qui separe cette clause du correctif de PORTEE."""
    vis, aid = PROBE.POOL_HAS_NOT_MOVED
    res = PROBE.portee_non_lue(live_session, ability=aid, visual=vis)
    if res.get("error"):
        pytest.fail("montage has_not_moved KO : %s" % res["error"], pytrace=False)
    return res


@pytest.fixture(scope="module")
def mesure_offline_portee():
    """Le GISEMENT de l'invariant << portee non lue + bit 15 >>, RE-DERIVE des deux sources du foyer
    `targeting_options_for` -- jamais une liste saisie. Rend (gisement, fautes, temoin) ou le TEMOIN
    est une ability a portee non lue SANS le bit : elle doit rester NON DECIDABLE."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (TARGETING_OPTIONS_UNPORTED,
                                                   targeting_options_for)
    from engine.services import ability_range as AR
    import gameconfig as GC

    ids = sorted({int(a) for a in ABILITY_CLASSES
                  if getattr(ABILITY_CLASSES[a], "TARGETING_OPTIONS", None) is not None}
                 | {int(a) for a in TARGETING_OPTIONS_UNPORTED})
    idx = GC.all_unit_ids()
    cat = sorted({u for k in ("lineup", "npc", "summons") for u in (idx.get(k) or [])})
    vis = PROBE.GRAFT_ON
    ajout = int(TR.CasterIsPossibleTarget) | int(TR.TargetIsCasterOrEnemy)
    gisement, fautes, temoins = [], [], []
    for aid in ids:
        r = int(getattr(targeting_options_for(aid), "rules", 0) or 0)
        if AR.tiles_in_range_reach(aid, vis) is not None:
            continue
        if r & ajout:
            gisement.append(aid)
            for v in cat[:40]:
                if AR.tiles_in_range_zone_contains(aid, v, 0) is not True:
                    fautes.append((aid, v))
        else:
            temoins.append((aid, AR.tiles_in_range_zone_contains(aid, vis, 0)))
    return gisement, fautes, temoins


def _p(mesure, cle):
    return mesure["postes"][cle]


# ------------------------------------------------------------------------------------------------
# OFFLINE -- ce qui rend le montage discriminant, RE-DERIVE et non affirme
# ------------------------------------------------------------------------------------------------

def test_le_board_porte_bien_les_culs_de_sac_du_montage():
    """Les tuiles du montage sont des CONSTANTES, mais leur PROPRIETE est re-derivee du board :
    degre 1 pour les quatre porteurs, degre 6 pour le temoin, et l'ennemi qui ouvre le gate
    adjacent a la SEULE sortie du Runtherd concerne. Si le board change, ceci rougit."""
    g = PROBE.geometrie()
    assert g["postes_isoles_sont_des_culs_de_sac"], g["culs_de_sac"]
    assert g["temoin_est_ouvert"]
    assert g["ennemi_ouvre_est_adjacent_a_la_sortie"]
    assert g["ennemi_loin_nest_adjacent_a_aucune_sortie"]


def test_les_masques_separent_le_bit_15_et_rien_d_autre():
    """Le CONTROLE ne doit differer du porteur que par ce qui est teste : meme `unit_threat_reach`,
    une seule ability active de chaque cote (sinon une autre pourrait verser `d = 0`), et les deux
    Runtherd strictement le MEME masque -- c'est ce qui fait du GATE leur unique difference."""
    m = PROBE.masques()
    faux = [nom for nom, ok in PROBE.masques_discriminants(m) if not ok]
    assert faux == [], "%r  (masques: %r)" % (faux, m)


# ------------------------------------------------------------------------------------------------
# LE REGIME -- a garder AVANT le discriminant
# ------------------------------------------------------------------------------------------------

def test_le_regime_est_NON_DEGENERE_sur_les_quatre_porteurs(mesure):
    """`n_move == 1`, et cette tuile est bien la sortie attendue du cul-de-sac. SANS CELA, la
    question << la position candidate est-elle menacee >> se repond toute seule et le reste du
    fichier ne demontre rien."""
    for cle in ("creed_bit", "bullgryn_sans_bit", "ork_gate_passe", "ork_gate_mord"):
        d = _p(mesure, cle)
        assert d["n_move"] == 1, "%s : n_move=%d move=%r" % (cle, d["n_move"], d["move"])
        assert d["move"] == [d["sortie_attendue"]], \
            "%s : move=%r attendu=%r" % (cle, d["move"], d["sortie_attendue"])


def test_le_temoin_OUVERT_mesure_le_regime_degenere(mesure):
    """LA CONTRE-PREUVE DU REGIME. Le meme masque SANS bit 15, en terrain ouvert : ses positions
    candidates sont TOUTES dans la menace -- couvertes les unes depuis les autres. Une lecture
    faite la serait un faux vert, et c'est mesure, pas suppose."""
    d = _p(mesure, "temoin_ouvert")
    assert d["n_move"] >= 2
    assert d["source_natif"] == d["move"], d
    assert d["source_port_sans_bit15"] == d["move"], \
        "le bit 15 desarme ne change RIEN ici : c'est bien le regime degenere"


# ------------------------------------------------------------------------------------------------
# LE DISCRIMINANT
# ------------------------------------------------------------------------------------------------

def test_INCLUSION_le_natif_verse_la_tuile_source_quand_le_bit_est_arme(mesure):
    """LE LIVRABLE. `astraCreed` / `1028 SupremeCommander` : `RANGE_SELF` + bit 15, AUCUN gate
    caster -- la zone de l'ability est EXACTEMENT `casterTiles`. Le natif verse la position
    candidate elle-meme."""
    d = _p(mesure, "creed_bit")
    assert d["source_natif"] == d["move"], d
    assert d["source_port"] == d["source_natif"], d


def test_EXCLUSION_sans_le_bit_le_natif_ne_la_verse_pas(mesure):
    """LE CONTROLE, meme runner, meme instant, meme `unit_threat_reach` : `1017 FragBomb` n'a ni
    bit 15 ni bit 57, et sa position candidate n'est PAS dans la menace."""
    d = _p(mesure, "bullgryn_sans_bit")
    assert d["source_natif"] == []
    assert d["source_port"] == []


def test_l_attaque_normale_ne_verse_jamais_la_tuile_source(mesure):
    """L'ETAGE ISOLE. Aucun des masques d'attaque normale ne porte le bit 15 : le terme d'attaque
    normale ne peut donc PAS etre l'auteur de l'inclusion mesuree ci-dessus."""
    for cle in ("creed_bit", "bullgryn_sans_bit", "ork_gate_passe", "ork_gate_mord"):
        assert _p(mesure, cle)["source_port_normale_seule"] == [], cle


# ------------------------------------------------------------------------------------------------
# LE BLOCAGE NOMME PAR #447-r1 §8, MESURE
# ------------------------------------------------------------------------------------------------

def test_le_gate_caster_separe_deux_exemplaires_du_MEME_masque(mesure):
    """`1045 GetEmRuntz` porte le bit 15 ET `CasterMatchesDynamicRule`. Deux exemplaires du MEME
    Runtherd, MEME masque, MEME cul-de-sac de degre 1 : celui qui a un ennemi contre sa sortie voit
    `GetSpawnTileSelector` non vide (`casterReason == 0`) et le natif VERSE la tuile source ;
    l'autre est refuse (`TargetMatchesDynamicRule`) et le natif ne verse RIEN.

    C'est la mesure du << blocage >> : il est reel, mais c'est un fait de MONTAGE -- il ne dit rien
    du bit 15, et il se leve en posant un ennemi."""
    passe, mord = _p(mesure, "ork_gate_passe"), _p(mesure, "ork_gate_mord")
    assert passe["natif_caster_reason"] == 0, passe["natif_caster_noms"]
    assert mord["natif_caster_reason"] == int(TR.TargetMatchesDynamicRule)
    assert mord["natif_caster_noms"] == ["TargetMatchesDynamicRule"]
    assert passe["source_natif"] == passe["move"]
    assert mord["source_natif"] == []


def test_le_port_suit_le_gate_sur_les_deux_Runtherd(mesure):
    """`AttackQuery$$GetInvalidCasterReason` EST porte (`ability_caster_gates.invalid_caster_reason`,
    #433-r4-r2-r1-r2-r2-r1-r1-r1-r4) : le port doit reproduire la separation, pas seulement le
    verdict le plus frequent."""
    for cle in ("ork_gate_passe", "ork_gate_mord"):
        d = _p(mesure, cle)
        assert d["source_port"] == d["source_natif"], (cle, d)
        assert int(d["port_caster_reason"] or 0) == int(d["natif_caster_reason"]), (cle, d)


# ------------------------------------------------------------------------------------------------
# LES DEUX CONTRE-EPREUVES
# ------------------------------------------------------------------------------------------------

def test_contre_epreuve_le_masque_est_REELLEMENT_mute(mesure):
    """UNE CONTRE-EPREUVE QUI NE S'APPLIQUE PAS REND UN VERT QUI NE PROUVE RIEN. Le masque est relu
    PAR LE CHEMIN DU PORT (`ability_range._options_of`, import paresseux) pendant la mutation."""
    d = _p(mesure, "creed_bit")
    assert int(d["masque_mute_sans_bit15"], 16) & int(TR.CasterIsPossibleTarget) == 0, d


def test_contre_epreuve_sans_le_bit_15_le_port_PERD_la_tuile(mesure):
    """Le bras mute doit DIFFERER du bras temoin : sur les deux porteurs qui versent la tuile, le
    port desarme ne la verse plus -- donc il DESACCORDE avec le natif, qui la verse toujours."""
    for cle in ("creed_bit", "ork_gate_passe"):
        d = _p(mesure, cle)
        assert d["source_port"] != [], cle
        assert d["source_port_sans_bit15"] == [], (cle, d["source_port_sans_bit15"])
        assert d["source_natif"] != [], cle          # le natif, lui, n'a pas bouge


def test_contre_epreuve_le_controle_ne_bouge_pas(mesure):
    """Le TEMOIN de la contre-epreuve : desarmer un bit qui n'est pas arme ne change rien. Sans
    lui, une mutation qui casserait TOUT passerait le test precedent."""
    d = _p(mesure, "bullgryn_sans_bit")
    assert d["source_port_sans_bit15"] == d["source_port"]


def test_contre_epreuve_sans_le_4e_gate_le_port_verse_ce_que_le_natif_REFUSE(mesure):
    """L'autre moitie : sur le Runtherd que le natif refuse, un port SANS
    `invalid_caster_reason` verserait la tuile source. C'est ce que le port faisait avant
    #433-r4-r2-r1-r2-r2-r1-r1-r1-r4, et c'est ce qui rendait la branche INCLUSION non confrontable
    sur ce porteur."""
    d = _p(mesure, "ork_gate_mord")
    assert d["source_natif"] == []
    assert d["source_port_sans_gate4"] == d["move"], d["source_port_sans_gate4"]


# ------------------------------------------------------------------------------------------------
# LA ZONE ENTIERE, VENTILEE
# ------------------------------------------------------------------------------------------------

def test_une_portee_NON_RE_LUE_ne_retire_plus_l_ajout_aval(mesure_offline_portee):
    """L'INVARIANT, pas un compte : pour TOUTE ability dont le masque porte le bit 15 (ou le 57) et
    dont `tiles_in_range_reach` rend `None`, la zone doit contenir `d = 0`.

    Les deux `AddRange(casterTiles)` vivent dans `GetPossibleTargetsForOptions`, l'APPELANT de
    `GetTilesInRange`, et ne consultent NI la portee NI la branche. Un `None` de portee ne peut donc
    pas les annuler. Avant #447-r1-r1 la fonction rendait `None` pour ces couples -- ecart
    RESTRICTIF mesure live sur `1215`."""
    gisement, fautes, temoins = mesure_offline_portee
    assert gisement, "gisement VIDE : cet invariant ne garde plus rien, le re-deriver"
    assert fautes == [], "portee non lue + bit 15 mais zone(d=0) != True : %r" % fautes[:8]
    assert temoins, "aucun TEMOIN : le rabattement du triplet ne serait pas discrimine"
    assert all(z is None for _a, z in temoins), \
        "le TEMOIN (portee non lue SANS le bit) doit rester NON DECIDABLE : %r" % temoins


def test_la_greffe_est_effective_et_le_regime_non_degenere(greffe):
    """L'ENTITE ne porte QUE l'ability greffee -- lu dans `decisionView`, jamais dans le kit
    gameconfig (une greffe change `BC.Units[].ActiveAbilities`, PAS le gameconfig). Et son movable
    set est un SINGLETON."""
    assert greffe["kit_de_l_entite_est_le_bon"], greffe["abilities_de_l_entite"]
    assert greffe["n_move"] == 1 and greffe["move"] == [greffe["sortie_attendue"]], greffe
    assert greffe["reach_port"] is None, "la portee de 1215 est devenue lisible : re-choisir l-item"
    assert greffe["natif_caster_reason"] == 0, greffe["natif_caster_noms"]
    assert not greffe["porte_caster_has_not_moved"], \
        "1215 ne doit PAS porter le bit 4, sinon la 2e clause masque ce que ce volet mesure"


def test_portee_NON_LUE_le_natif_verse_quand_meme_la_tuile_source(greffe):
    """LE PREMIER BUG TROUVE PAR CETTE TRANCHE. `1215` a un `TargetingRange` que le port ne sait pas
    lire ; le natif verse pourtant la tuile source, parce que l'ajout aval ne consulte pas la
    portee. Le port refusait tout (`_ability_covers_tile` : `if base is None: return False`)."""
    assert greffe["source_natif"] == greffe["move"], greffe
    assert greffe["source_port"] == greffe["source_natif"], greffe
    assert greffe["source_port_normale_seule"] == [], greffe["source_port_normale_seule"]


def test_portee_NON_LUE_contre_epreuve_sans_le_bit_le_port_perd_la_tuile(greffe):
    """Sans quoi l'accord ci-dessus pourrait venir d'un autre etage."""
    assert int(greffe["masque_mute_sans_bit15"], 16) & int(TR.CasterIsPossibleTarget) == 0
    assert greffe["source_port"] != []
    assert greffe["source_port_sans_bit15"] == []


# ------------------------------------------------------------------------------------------------
# LA 2e CLAUSE DE `CasterHasNotMoved` -- le SECOND bug, sur un porteur du POOL
# ------------------------------------------------------------------------------------------------

def test_CasterHasNotMoved_2e_clause_le_natif_refuse_une_position_BALAYEE(has_not_moved):
    """LE SECOND BUG. `GetTiles(caster).IsEquivalentTo(casterTiles)` n'est INERTE que chez
    `BattleQuery$$IsTileInRangeOfAnyAbility` (qui passe `{GetMainTile}`). Chez
    `AttackQuery$$GetAllTilesInAbilityRange(unit, possiblePositions, true)` -- l'oracle
    `aiMovableTiles` -- `casterTiles` est la position CANDIDATE, et le natif REFUSE des qu'elle
    differe de la tuile courante : il ne verse RIEN, alors que `abilityReason.casterReason`, evalue
    DEPUIS LA TUILE COURANTE, rend `0`.

    Porteur du POOL, kit d'origine, portee LUE : ce chemin n'a rien de commun avec la greffe."""
    d = has_not_moved
    assert d["kit_de_l_entite_est_le_bon"], d["abilities_de_l_entite"]
    assert d["porte_caster_has_not_moved"] and d["est_son_tour"] is True, d
    assert d["reach_port"] is not None, "ce porteur doit avoir une portee LUE"
    assert d["n_move"] == 1 and d["move"] == [d["sortie_attendue"]], d
    assert d["natif_caster_reason"] == 0, d["natif_caster_noms"]
    assert d["source_natif"] == [], d
    assert d["source_port"] == [], d


def test_CasterHasNotMoved_2e_clause_contre_epreuve(has_not_moved):
    """Le bras mute doit DIFFERER du temoin : sans la clause, le port verse la tuile que le natif
    refuse. C'est exactement ce que le port faisait avant cette tranche."""
    d = has_not_moved
    assert d["source_port_sans_clause2"] == d["move"], d["source_port_sans_clause2"]
    assert d["source_port"] == []


def test_aucun_ecart_imputable_a_la_couche_ability_sur_la_zone_entiere(mesure):
    """Pas seulement la tuile source : l'ensemble COMPLET rendu par le natif, ventile. `fp_normale`
    est le residu PREEXISTANT du terme d'attaque normale (LoS / elevation / walkability) ; ce qui
    est imputable a la couche ability est `fp \\ fp_normale`, plus tout `fn`."""
    for cle in ("creed_bit", "bullgryn_sans_bit", "ork_gate_passe", "ork_gate_mord"):
        d = _p(mesure, cle)
        impute = [t for t in d["fp"] if t not in d["fp_normale"]]
        assert impute == [] and d["fn"] == [], \
            "%s : fp_impute=%r fn=%r (residu normale=%r)" % (cle, impute, d["fn"],
                                                             d["fp_normale"])
