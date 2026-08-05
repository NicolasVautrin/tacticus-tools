"""#433-r4-r2-r1-r2-r2-r1-r1-r1 -- la tuile SOURCE dans la zone de `GetTilesInRange`,
et les 8 masques du lot HORS POOL.

Ce que ces crans gardent, et pourquoi chacun peut ROUGIR :

  1. **LA PAIRE DISCRIMINANTE** -- `28 Repair` et `1053 DevoutPush` portent le MEME
     `TargetingRange` (`RANGE_ADJACENT`) et ne different QUE par `CasterIsPossibleTarget`. Le
     modele RAYON les rendait IDENTIQUES a `d = 0` (les deux `True`) ; le modele ZONE les SEPARE.
     Sans cette paire, un cran sur une seule ability serait compatible avec « le port exclut
     toujours la source », qui est FAUX.
  2. **Les quatre branches**, chacune sur son gisement REEL : `OnlyAdjacent` exclut,
     `(int)range == 0` sans le bit 15 rend une zone VIDE, le disque exclut son centre, et
     `UseWholeBoard` inclut tout.
  3. **L'ATTAQUE NORMALE** -- aucun de ses 18 profils ne porte `CasterIsPossibleTarget` ni
     `TargetIsCasterOrEnemy`, donc `d = 0` en est exclu quel que soit le caster. C'est le terme
     `includeNormalAttack: true` d'`AttackQuery$$GetAllTilesInAbilityRange`, et il etait faux pour
     TOUTE unite du catalogue.
  4. **LA BRANCHE ANNEAU EST UN MIRROR STRUCTUREL** : `TargetIsAtRange` a **0** porteur RE-lu, donc
     son cran est SYNTHETIQUE et le cran jumeau MESURE que le gisement est vide. Si celui-ci
     rougit, c'est qu'une ability neuve a ouvert le regime -> il faut le CONFRONTER live, pas
     ajuster le chiffre.
  5. **LA BORNE SUPERIEURE** -- `tiles_in_range_zone_contains` doit rester INCLUS dans le disque de
     `tiles_in_range_reach`. Les deux partagent `_range_terms` ; un desaccord signalerait le retour
     du FORK que `#433-r4-r2-r1-r2-r2-r1-r1` avait supprime.
  6. **LES 8 MASQUES DU LOT HORS POOL**, avec leur valeur EXACTE et la ventilation de leurs
     porteurs -- dont `1144 BioMinefield`, portee par la MoW `tyranBiovore` DU POOL, et dont le bit
     `AllowNullCasterTile` est la signature. `1091` doit rester ABSENTE (masque NON LU) et `1186`
     doit rester au registre COMBAT (contrat de disjonction).

RE et mesures : `docs/rl/case-433-r4-r2-r1-r2-r2-r1-r1-r1-tuile-source.md`.
Probe jumeau : `probe_433_r4_r2_r1_r2_r2_r1_r1_r1_source_tile_zone.py`. ASCII only.
"""
from __future__ import annotations

import probe_433_r4_r2_r1_r2_r2_r1_r1_r1_source_tile_zone as P
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import (TARGETING_OPTIONS_UNPORTED, targeting_options_for)
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.services import ability_range as AR


def _vis():
    return P.catalogue()[0]


# ------------------------------------------------------------------------------------------------
# 1. La paire discriminante -- meme portee, masques differents
# ------------------------------------------------------------------------------------------------

def test_la_paire_qui_separe_les_deux_modeles():
    """`28 Repair` (`CasterIsPossibleTarget`) et `1053 DevoutPush` (sans) portent tous deux
    `RANGE_ADJACENT`. Le modele RAYON les rendait egaux a `d = 0` ; le natif les separe."""
    vis = _vis()
    a, b = targeting_options_for(28), targeting_options_for(1053)
    assert a.range == b.range, ("la paire ne separe plus rien : les deux `TargetingRange` ont "
                               "diverge, il faut choisir une autre paire ET le dire")
    assert bool(int(a.rules) & int(TR.CasterIsPossibleTarget))
    assert not (int(b.rules) & P.CASTER_ADDED)

    assert AR.tiles_in_range_zone_contains(28, vis, 0) is True, (
        "`CasterIsPossibleTarget` RE-AJOUTE `casterTiles` dans "
        "`GetPossibleTargetsForOptions` -- la tuile source DOIT etre dans la zone")
    assert AR.tiles_in_range_zone_contains(1053, vis, 0) is False, (
        "`GetAdjacentTiles(casterTiles, ...)` n'inclut PAS `casterTiles`, et aucun bit ne l'y "
        "remet : la tuile source ne doit PAS etre dans la zone")
    assert AR.tiles_in_range_zone_contains(1053, vis, 1) is True, (
        "contre-cran : la zone d'adjacence ne doit pas s'etre videe")


# ------------------------------------------------------------------------------------------------
# 2. Les quatre branches, sur leur gisement REEL
# ------------------------------------------------------------------------------------------------

def test_only_adjacent_exclut_la_source_sur_tout_son_gisement():
    """Les abilities `OnlyAdjacent` SANS bit 15/57 : `d = 0` exclu, `d = 1` inclus. Balayage du
    gisement entier, pas d'un exemple choisi."""
    vis = _vis()
    gisement = [a for a in P.ability_ids()
                if P.branche(a) == "only_adjacent" and not P.caster_ajoute(a)]
    assert len(gisement) >= 20, "gisement trop maigre (%d) -- substrat suspect" % len(gisement)
    fautes = [a for a in gisement
              if AR.tiles_in_range_zone_contains(a, vis, 0) is not False
              or AR.tiles_in_range_zone_contains(a, vis, 1) is not True]
    assert not fautes, "branche OnlyAdjacent fausse pour %s" % fautes[:8]


def test_portee_nulle_sans_le_bit_15_rend_une_zone_vide():
    """`(int)range == 0` : le natif rend `casterTiles` SEULEMENT sous `CasterIsPossibleTarget`,
    et un `OrderedSet` VIDE sinon. Le port rendait `d <= 0`, donc la source, toujours."""
    vis = _vis()
    gisement = [a for a in P.ability_ids()
                if P.branche(a) == "range_zero" and not P.caster_ajoute(a)]
    assert gisement, "aucune ability a portee nulle sans le bit -- le cran ne garde plus rien"
    for aid in gisement:
        assert AR.tiles_in_range_zone_contains(aid, vis, 0) is False, (
            "%d : zone VIDE attendue (branche `(int)range == 0` sans `CasterIsPossibleTarget`)"
            % aid)
        assert AR.tiles_in_range_zone_contains(aid, vis, 1) is False


def test_portee_nulle_avec_le_bit_15_rend_la_source_et_elle_seule():
    """Contre-cran du precedent : `1015 PrecisionShot` (`RANGE_SELF` + `CasterIsPossibleTarget`)
    doit rendre la source, et RIEN d'autre."""
    vis = _vis()
    assert AR.tiles_in_range_zone_contains(1015, vis, 0) is True
    assert AR.tiles_in_range_zone_contains(1015, vis, 1) is False


def test_le_disque_exclut_son_centre_mais_pas_sa_couronne():
    """Branche `GetSurroundingTiles`, `includeCenter = rules >> 0xf & 1` : sans le bit, `d = 0`
    est retire et le reste du disque subsiste."""
    vis = _vis()
    gisement = [a for a in P.ability_ids()
                if P.branche(a) == "radius" and not P.caster_ajoute(a)]
    assert len(gisement) >= 20, "gisement trop maigre (%d)" % len(gisement)
    vus = 0
    for aid in gisement:
        reach = AR.tiles_in_range_reach(aid, vis)
        if reach is None or int(reach) < 1:
            continue
        vus += 1
        assert AR.tiles_in_range_zone_contains(aid, vis, 0) is False, "%d : centre inclus" % aid
        assert AR.tiles_in_range_zone_contains(aid, vis, 1) is True, "%d : couronne perdue" % aid
    assert vus >= 10, "seulement %d abilities exercees -- substrat suspect" % vus


def test_whole_board_inclut_la_source():
    """`GetAllTiles()` ne retire rien : la source en fait partie. Contre-cran global -- un port qui
    excluerait la source PARTOUT passerait tous les crans precedents et casserait celui-ci."""
    vis = _vis()
    gisement = [a for a in P.ability_ids() if P.branche(a) == "whole_board"]
    assert len(gisement) >= 20, "gisement trop maigre (%d)" % len(gisement)
    fautes = [a for a in gisement if AR.tiles_in_range_zone_contains(a, vis, 0) is not True]
    assert not fautes, "UseWholeBoard doit inclure la source : %s" % fautes[:8]


# ------------------------------------------------------------------------------------------------
# 3. L'attaque normale
# ------------------------------------------------------------------------------------------------

def test_attaque_normale_exclut_la_source_pour_tous_ses_profils():
    """Aucun des 18 masques d'attaque normale ne porte `CasterIsPossibleTarget` ni
    `TargetIsCasterOrEnemy` -- la tuile du caster est donc hors zone, et `d = 1` reste dedans."""
    from engine.runner.abilities.targeting import NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE as BY
    assert len(BY) >= 15, "table des attaques normales trop maigre (%d)" % len(BY)
    porteurs = [t for t, o in BY.items() if int(o.rules) & P.CASTER_ADDED]
    assert not porteurs, (
        "des profils d'attaque normale portent desormais un bit qui RE-AJOUTE le caster (%s) : "
        "le raccourci de ce cran ne vaut plus, il faut ventiler" % porteurs)
    vis = [v for v in P.catalogue()
           if AR.normal_attack_zone_contains(69, v, 1) is True][:40]
    assert len(vis) >= 20, "seulement %d unites a portee d'arme lisible" % len(vis)
    for v in vis:
        for t in sorted(BY):
            assert AR.normal_attack_zone_contains(t, v, 0) is False, (
                "profil %d / %s : la tuile du caster ne peut pas etre a portee de son attaque "
                "normale" % (t, v))


# ------------------------------------------------------------------------------------------------
# 4. La branche ANNEAU -- mirror structurel + mesure du gisement
# ------------------------------------------------------------------------------------------------

def test_target_is_at_range_rend_un_anneau_mirror_structurel():
    """`rules & TargetIsAtRange` -> `GetTilesAtDistance(casterTiles, (int)range, false)`, une
    distance EXACTE. Cran SYNTHETIQUE : le gisement reel est vide (cran suivant)."""
    rules = int(TR.TargetIsEnemy | TR.TargetIsAtRange)
    assert AR._zone_contains_distance(rules, 3, False, False, 3) is True
    assert AR._zone_contains_distance(rules, 3, False, False, 2) is False
    assert AR._zone_contains_distance(rules, 3, False, False, 0) is False
    # contre-cran : sans le bit, la MEME portee rend un DISQUE
    nu = int(TR.TargetIsEnemy)
    assert AR._zone_contains_distance(nu, 3, False, False, 2) is True


def test_le_gisement_de_at_range_est_vide_et_cest_une_mesure():
    """Aucune ability RE-lue ne pose `TargetIsAtRange` : c'est ce qui classe la branche en mirror
    NON CONFRONTE. Si ce cran rougit, la branche devient confrontable -- il faut la mesurer live."""
    porteurs = [a for a in P.ability_ids()
                if int(targeting_options_for(a).rules) & int(TR.TargetIsAtRange)]
    assert len(P.ability_ids()) >= 100, "perimetre trop maigre pour conclure"
    assert not porteurs, (
        "%s posent desormais `TargetIsAtRange` : la branche ANNEAU est ATTEIGNABLE et doit etre "
        "CONFRONTEE live, pas laissee en mirror structurel" % porteurs)


# ------------------------------------------------------------------------------------------------
# 5. La borne superieure -- pas de fork entre le rayon et la zone
# ------------------------------------------------------------------------------------------------

def test_la_zone_reste_incluse_dans_le_disque_du_rayon():
    """`tiles_in_range_reach` doit rester la borne SUPERIEURE exacte de la zone."""
    testes, fautes = P.borne_superieure_tient()
    assert testes > 10000, "seulement %d points testes -- substrat suspect" % testes
    assert fautes == 0, ("%d points de la zone tombent HORS du disque du rayon : les deux "
                         "fonctions ne partagent plus `_range_terms`" % fautes)


# ------------------------------------------------------------------------------------------------
# 6. Le lot HORS POOL -- les 8 masques
# ------------------------------------------------------------------------------------------------

#: Masque EFFECTIF lu au ctor, et forme qui l'a produit. Valeurs BRUTES ici A DESSEIN : ce cran
#: confronte le port a la lecture du decompile, donc il doit porter le nombre, pas le re-deriver
#: depuis le port qu'il garde.
LOT_HORS_POOL = {
    1010: (0x4010, "flags directs"),
    1015: (0x8014, "preset +0x280 | 0x10"),
    1044: (0x4002, "static-copy +0x140"),
    1053: (0x4000, "static-copy +0x40"),
    1080: (0x4002, "static-copy +0x140"),
    1108: (0x4000, "static-copy +0x40"),
    1144: (0x40004020, "flags directs"),
    1185: (0x200004002, "flags directs"),
}


def test_les_huit_masques_du_lot_hors_pool_sont_poses():
    for aid, (attendu, forme) in sorted(LOT_HORS_POOL.items()):
        opts = targeting_options_for(aid)
        assert opts is not None, "%d n'a plus de masque (forme : %s)" % (aid, forme)
        assert int(opts.rules) == attendu, (
            "%d : masque %#x, attendu %#x (%s)" % (aid, int(opts.rules), attendu, forme))
        assert opts.range is not None, "%d : portee non posee" % aid


def test_bio_minefield_porte_la_signature_MoW():
    """`1144 BioMinefield` est portee par `tyranBiovore`, une MACHINE OF WAR : son masque porte
    `AllowNullCasterTile`, la PERMISSION sans laquelle aucune ability de MoW ne serait castable
    (une machine n'a aucune tuile)."""
    opts = targeting_options_for(1144)
    assert int(opts.rules) & int(TR.AllowNullCasterTile)
    assert opts.range is not None and opts.range.use_whole_board


def test_1091_reste_non_lu_et_1186_reste_au_registre():
    """Les deux exclusions du lot, et elles ne sont PAS de meme nature :
      * `1091 SlashingDive` -- aucune classe d'ability a lire (le corps du ctor est deduplicable) :
        un masque devine serait pire que l'absence ;
      * `1186 WallOfMirrors` -- sa face COMBAT est portee, donc son masque vit dans
        `ABILITY_CLASSES` et le dupliquer ici casserait le contrat de disjonction."""
    assert 1091 not in TARGETING_OPTIONS_UNPORTED
    assert targeting_options_for(1091) is None, (
        "1091 a desormais un masque : verifier qu'il a ete LU (ctor ou slot de vtable), pas devine")
    assert 1186 not in TARGETING_OPTIONS_UNPORTED, "doublon avec `ABILITY_CLASSES[1186]`"
    assert getattr(ABILITY_CLASSES[1186], "TARGETING_OPTIONS", None) is not None


def test_les_deux_sources_de_masques_restent_disjointes():
    inter = sorted(set(TARGETING_OPTIONS_UNPORTED) & set(ABILITY_CLASSES))
    assert not inter, (
        "%s figurent dans les DEUX sources : `targeting_options_for` en servirait une et "
        "l'autre deviendrait du code mort qui derive en silence" % inter)
