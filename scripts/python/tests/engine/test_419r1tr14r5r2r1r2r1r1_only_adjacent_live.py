"""#419-r1-tr14-r5-r2-r1-r2-r1-r1 -- le gate d'ADJACENCE sur une portee NON OBSERVABLE, CONFRONTE.

Ce que ces crans gardent, et pourquoi chacun est necessaire :

  1. **LE TRI-ETAT EST SUR LA VALEUR, PAS SUR LE `Range`.** `get_range` doit rendre un `Range` dont
     `only_adjacent` est exact meme quand `value is None` -- c'est la structure du natif, ou
     `onlyAdjacent` est calcule AVANT toute resolution d'arme et n'en depend jamais.
  2. **LE CONSOMMATEUR DESARME AU BON ETAGE.** `get_range_broken_rule` ne renonce que dans la branche
     DISTANCE ; la branche `only_adjacent` mord, exactement comme
     `TargetingQuery$$GetInvalidTargetReason`, qui teste `range._4_1_` EN PREMIER.
  3. **L'ETAGE JUMEAU N'EST PAS ALIGNE.** `tiles_in_range_reach` (mirror de `GetTilesInRange`) doit
     RESTER `None` : cette fonction-la lit `(int)range` AVANT `range._4_1_`. Aligner par symetrie
     serait un faux, et ce cran l'interdit.
  4. **LE MONTAGE A MORDU** (les deux bras), et un montage rate est un ECHEC, jamais un skip vert.
  5. **LE PORT CONTRE LE NATIF, SUR LA CAUSE.** Accord total sur le CODE du `TargetingRule` rendu --
     l'axe de cette tranche. Le VERDICT etait deja garde par #419-r1-tr14-r5-r2-r1-r2-r1 ; ici c'est
     la RAISON qui est en jeu, et une raison fausse se propage.
  6. **LE PORT CONTRE LE NATIF, SUR LE VERDICT** -- le bras GREFFE. Sur un masque `0x4000` (sans
     `TargetMatchesDynamicRule`), rien ne rattrape en aval : la baseline ACCEPTE ce que le natif
     REFUSE. C'est la preuve que l'ecart etait PERMISSIF, et pas seulement mal nomme.
  7. **LA CONTRE-EPREUVE MORD.** La baseline doit diverger -- sinon le regime est DEGENERE et un
     accord parfait ne prouverait rien.
  8. **AUCUNE LIGNE PERDUE, TEMOIN ARME INCHANGE.** Le risque symetrique : un gate arme trop large.
     Le temoin est un summon de la MEME equipe, MEME attaque normale, MEME geometrie -- seules ses
     armes different, donc sa portee est OBSERVABLE et rien ne doit y bouger.

RE et mesures : `docs/rl/case-419-r1-tr14-r5-r2-r1-r2-r1-r1-only-adjacent-portee-non-observable.md`.
ASCII only. Probes jumeaux : `probe_419r1tr14r5r2r1r2r1r1_only_adjacent_live.py` (live) et
`probe_419r1tr14r5r2r1r2r1r1_range_only_adjacent.py` (rayon de souffle, hors ligne).
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r5r2r1r2r1r1_only_adjacent_live as P
import probe_419r1tr14r5r2r1r2r1r1_range_only_adjacent as PR
from engine.runner.abilities.targeting import (
    NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE as OPTS, get_range)
from engine.runner.abilities.targeting_rule import TargetingRule as TR

IN_RANGE = int(TR.TargetIsInRange)


@pytest.fixture(scope="module")
def mesure(rpc):
    """Les DEUX bras, natif ET port. Un montage qui n'a pas mordu est un ECHEC (`MontageError`),
    jamais un skip vert."""
    from rl_collect_batch import _resolve_session
    sid = _resolve_session()
    try:
        res = P.run(sid)
        res.update(P.run_greffe(sid))
        return res
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


# ------------------------------------------------------------------------------- crans OFFLINE

def test_le_tri_etat_porte_sur_la_valeur_pas_sur_le_range():
    """(1) Sur un caster SANS ARME et le jeu generique `69` (`only_adjacent = IfNotRangedCaster`),
    `get_range` doit rendre un `Range` a `value is None` ET `only_adjacent is True` -- surtout pas
    `None`. C'est le mirror de `TargetingQuery$$GetRange`, ou les trois ecritures de `onlyAdjacent`
    (`IsTrue(options.Range.OnlyAdjacent)`, puis deux forcages) ignorent toutes la valeur."""
    st, cid = _etat_synthetique("genesSmnDecoy")
    rr = get_range(st, cid, OPTS[P.GENERIC_TYPE])
    assert rr is not None, "get_range ne doit plus abandonner le `Range` entier"
    assert rr.value is None, "la portee d'arme de `genesSmnDecoy` (weapons = []) n'est PAS observable"
    assert rr.only_adjacent is True, (
        "`IfNotRangedCaster` sur un caster sans arme -> vrai ; il ne depend pas de la valeur")


def test_letage_jumeau_get_tiles_in_range_reste_none():
    """(3) `TargetingQuery$$GetTilesInRange` teste `(int)range < 0` puis `== 0` AVANT
    `range._4_1_ OnlyAdjacent` : la valeur y est lue quoi qu'il arrive. `tiles_in_range_reach` a donc
    RAISON de rendre `None`, et ce cran interdit de l'aligner par symetrie sur le correctif."""
    assert PR.jumeau_toujours_none() is True


def test_le_rayon_de_souffle_est_chiffre_et_ne_perd_rien():
    """(1)+(2) Le balayage hors ligne : le correctif ARME des gates, n'en PERD aucun, et ne touche
    AUCUN couple dont la portee etait deja observable."""
    res = PR.run(verbose=False)
    assert res["gagnes"], "rayon VIDE : le correctif ne deplacerait rien"
    assert res["perdus"] == [], "le correctif desarme un gate qui etait arme"
    assert res["bouges_obs"] == [], "un couple a portee OBSERVABLE a bouge -- le correctif deborde"


def test_le_chiffrage_decrit_bien_le_code():
    """(1)+(2) LE CRAN QUI FAIT ROUGIR LE CHIFFRAGE. Les deux crans qui l'encadrent raisonnent sur un
    MODELE de `get_range` ; sans cette confrontation au CODE REEL ils resteraient VERTS si le port
    repartait en arriere -- exactement le vice d'un inventaire deguise en garde-fou."""
    ac = PR.accord_modele_code(verbose=False)
    assert ac["verifies"] > 1000, "echantillon trop maigre pour garder quoi que ce soit"
    assert ac["ecarts"] == [], (
        f"{len(ac['ecarts'])} ecart(s) entre le modele du chiffrage et `get_range` : "
        f"{ac['ecarts'][:3]}")


def test_le_rayon_reel_a_des_porteurs():
    """(1) Le produit cartesien est un MAJORANT ; ce cran exige des porteurs REELS (l'unite porte
    vraiment le jeu d'options), sans quoi le correctif serait theorique."""
    rr = PR.couples_reels(verbose=False)
    vis = {v for (_o, _a, v) in rr["reels"]}
    assert rr["reels"], "aucun porteur reel -- le correctif serait theorique"
    assert "genesSmnDecoy" in vis, (
        "le caster du montage live doit etre dans le rayon REEL, sinon la mesure porte sur un cas "
        "de bord fabrique pour l'occasion")


# --------------------------------------------------------------------------------- crans LIVE

def test_le_montage_a_mordu(mesure):
    """(4) Les deux bras existent, avec le bon type d'attaque normale, et le gisement de CETTE
    tranche (des cibles a `d >= 2`) est present."""
    assert mesure["decoy"], "aucune ligne pour le caster SANS ARME"
    assert mesure["anchor"], "aucune ligne pour le temoin ARME"
    assert mesure["greffe"], "aucune ligne pour le bras GREFFE (masque 0x4000)"
    assert any(r["d"] >= 2 for r in mesure["decoy"]), (
        "aucune cible a d >= 2 : le gisement de cette tranche n'est pas monte")
    assert any(r["d"] >= 2 for r in mesure["greffe"]), (
        "aucune cible a d >= 2 sur le bras greffe")


def test_le_port_est_daccord_avec_le_natif_sur_la_cause(mesure):
    """(5) Accord TOTAL sur le CODE du `TargetingRule` -- pas seulement sur « refuse / accepte »."""
    t = P.tally(mesure)
    assert t["after"] == t["tot"], (
        f"{t['tot'] - t['after']} ligne(s) ou le port et le natif divergent SUR LA CAUSE")


def test_le_port_est_daccord_avec_le_natif_sur_le_verdict(mesure):
    """(6) Et sur le VERDICT -- le bras greffe le rend non trivial."""
    t = P.tally(mesure)
    assert t["v_after"] == t["tot"], (
        f"{t['tot'] - t['v_after']} ligne(s) ou le port et le natif divergent SUR LE VERDICT")


def test_la_baseline_diverge_du_natif(mesure):
    """(7) LA CONTRE-EPREUVE. Sans elle, les deux verts precedents seraient un accord DEGENERE :
    partout ou la portee est observable, les deux modeles coincident par construction."""
    t = P.tally(mesure)
    assert t["gain"] >= 1, (
        "REGIME DEGENERE : la baseline nomme la MEME regle partout -- cette geometrie ne separe "
        "pas les deux modeles (il faut un caster SANS ARME et une cible NON adjacente)")


def test_lecart_etait_permissif_pas_seulement_mal_nomme(mesure):
    """(6) LE BRAS GREFFE, et c'est le cran le plus fort : sur `1126` (masque `0x4000`, donc AUCUN
    `TargetMatchesDynamicRule` pour rattraper en aval), la baseline ACCEPTAIT (`0x0`) ce que le natif
    REFUSE (`TargetIsInRange`). L'ecart n'etait donc pas une simple erreur d'imputation."""
    loin = [r for r in mesure["greffe"] if r["d"] >= 2 and r["nat"] is not None]
    assert loin, "aucune ligne a d >= 2 sur le bras greffe"
    for r in loin:
        assert r["nat"] == IN_RANGE, (
            f"cible u{r['tid']} d={r['d']} : le natif doit rompre TargetIsInRange, "
            f"trouve {hex(r['nat'])}")
        assert r["before"] == 0, (
            f"cible u{r['tid']} d={r['d']} : la baseline devait l'ACCEPTER (ecart PERMISSIF), "
            f"trouve {hex(r['before'])}")
        assert r["after"] == IN_RANGE


def test_la_cause_est_nommee_sur_le_bras_generique(mesure):
    """(5) Sur `69` (masque `0x4002`), le VERDICT etait deja juste depuis
    #419-r1-tr14-r5-r2-r1-r2-r1 -- mais par la MAUVAISE regle. Ce cran nomme les trois valeurs."""
    loin = [r for r in mesure["decoy"] if r["d"] >= 2 and r["nat"] is not None]
    assert loin, "aucune ligne a d >= 2 pour le caster sans arme"
    for r in loin:
        assert r["nat"] == IN_RANGE
        assert r["before"] == int(TR.TargetMatchesDynamicRule), (
            f"cible u{r['tid']} d={r['d']} : la baseline imputait le refus a la regle DYNAMIQUE, "
            f"trouve {hex(r['before'])}")
        assert r["after"] == IN_RANGE


def test_aucune_ligne_perdue_et_temoin_arme_inchange(mesure):
    """(8) Le sens INVERSE. Aucune cause juste deplacee, et le temoin ARME (portee OBSERVABLE) doit
    etre strictement identique avant/apres -- le correctif ne touche que le regime non observable."""
    t = P.tally(mesure)
    assert t["perte"] == 0, f"{t['perte']} ligne(s) dont la cause etait juste et ne l'est plus"
    assert t["v_perte"] == 0, f"{t['v_perte']} cible(s) que le natif accepte et que le port REFUSE"
    for r in mesure["anchor"]:
        assert r["after"] == r["before"], (
            f"temoin ARME, cible u{r['tid']} d={r['d']} : {hex(r['before'])} -> {hex(r['after'])} ; "
            "sa portee est OBSERVABLE, le correctif ne doit rien y changer")


# --------------------------------------------------------------------------------------- outil

def _etat_synthetique(visual_id: str):
    """Un `State` MINIMAL portant une seule unite de `visual_id`, pose sur une tuile. Suffit a
    `get_range`, qui ne lit que la tuile du caster, son `visualId` et ses stats."""
    from engine.runner.state import State
    from engine.runner.components import (OwnerComponent, PositionComponent, UnitComponent)
    st = State()
    ent = st.add_entity()
    ent.add_component(UnitComponent(visual_id=visual_id, alive=True))
    ent.add_component(PositionComponent(col=3, row=3))
    ent.add_component(OwnerComponent(team=0))
    cid = next(k for k, v in st.entities.items() if v is ent)
    return st, int(cid)
