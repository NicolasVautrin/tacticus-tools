"""GARDE live de la VOIE DU BIT 51 de `TargetIsNotSteppable` -- #447, suite de #442.

#442 avait confronte la regle par son armement IMPLICITE (`get_IsUnitTargeting` sans
`AllowSteppableUnit`, 82 abilities + l'attaque normale). Son SECOND armement -- le BIT 51 pose
explicitement au masque, dont le SEUL porteur du registre est `1011 TunnelingHorror` -- n'y etait
confronte qu'OFFLINE. Ce test garde la confrontation NATIVE.

Le probe MESURE (`probe_447_bit51_native.py`), ce test GARDE. Montage : l'ACTIVE 1011 GREFFEE sur
une unite du pool (recours 3 de `case-92` §5bis -- son vrai porteur `necroSmnDestroyer` est un
summon d'ENVIRONNEMENT que `buildNormalizedBC` refuse), et des `genesSmnDecoy` poses par
`CultDemagogue` (1179) de `genesPrimus`.

CE QUE LE TEST EXIGE, ET POURQUOI :
  * le SUBSTRAT d'abord (lecon de #436) -- les decoys portent bien `Steppable` ;
  * accord natif/port sur TOUTES les lignes des deux etages ;
  * au moins une ligne ou le natif rend `TargetIsNotSteppable` sur une TUILE (voie du bit) ;
  * LE PARTAGE 51 / 12, qui est le point de la tranche : sur la MEME tuile de decoy, `1166`
    (`TargetIsTile|TargetTileIsFree`, PAS de bit 51) ACCEPTE la ou `1011` refuse. Sans cette ligne
    la mesure ne discrimine pas les deux regles -- le natif appelle
    `IdunBattle.Entities.TileExtensions$$IsFreeTile(tile, state, allowSteppable: 1, 0, 0)` pour le
    bit 12, qui rend « libre » une tuile portee par une unite `Steppable` ;
  * NON-DEGENERESCENCE des deux cotes : 1011 accepte des tuiles libres, 1166 refuse par 12 des
    tuiles occupees par une unite non-`Steppable`.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import pytest

import probe_447_bit51_native as P
from engine.runner.abilities.targeting_rule import TargetingRule as TR

STEPPABLE = int(TR.TargetIsNotSteppable)
TILE_FREE = int(TR.TargetTileIsFree)


@pytest.fixture(scope="module")
def mesure():
    """Rejoue le probe COMPLET et rend ses lignes. Le probe dispose SON runner (jamais ceux des
    autres) et rend 0 si les quatre etages passent."""
    import contextlib
    import io
    import json
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = P.main([])
    txt = buf.getvalue()
    print(txt[-4000:])
    raw = [ln for ln in txt.splitlines() if ln.startswith("[RAW] ")]
    assert raw, "le probe n'a pas rendu sa ligne [RAW] -- montage rate :\n" + txt[-3000:]
    data = json.loads(raw[-1][len("[RAW] "):])
    data["rc"] = rc
    return data


def test_le_substrat_porte_des_decoys(mesure):
    assert mesure["decoys"], "aucun decoy `genesSmnDecoy` en vie -- montage rate"


def test_accord_natif_port_etage_B(mesure):
    ko = [r for r in mesure["B"] if r["nat"] != r["port"]]
    assert not ko, "desaccord natif/port sur la voie du bit 51 : %s" % ko


def test_le_natif_refuse_par_le_BIT_51_sur_une_TUILE(mesure):
    """LA confrontation de la tranche : `1011 TunnelingHorror` est TILE-targeting, donc son
    `get_IsUnitTargeting` est FAUX -- la voie implicite de #442 ne l'arme PAS. Le refus mesure ici
    ne peut venir que du bit pose au masque."""
    refus = [r for r in mesure["B"] if r["nat"] == STEPPABLE]
    assert refus, ("aucune ligne 0x%x -- la voie du bit 51 n'a pas ete confrontee au natif : %s"
                   % (STEPPABLE, mesure["B"]))


def test_1011_accepte_encore_des_tuiles_libres(mesure):
    """Non-degenerescence : une ability qui refuserait TOUT rendrait le refus non informatif."""
    ok = [r for r in mesure["B"] if r["nat"] == 0]
    assert ok, "1011 ne rend 0x0 sur AUCUNE tuile -- la mesure ne discrimine plus : %s" % mesure["B"]


def test_le_bit_12_mord_aussi_chez_1011(mesure):
    """Le bit 12 est bien ARME sur ce caster : sans cette ligne, on ne pourrait pas conclure que
    l'acceptation de la tuile du decoy par le bit 12 (test suivant) est significative."""
    douze = [r for r in mesure["B"] if r["nat"] == TILE_FREE]
    assert douze, ("1011 ne rend `TargetTileIsFree` sur AUCUNE tuile occupee -- le bit 12 est "
                   "inerte, le partage 51/12 n'est pas mesurable : %s" % mesure["B"])


def test_accord_natif_port_etage_C_sur_les_DEUX_abilities(mesure):
    ko = [r for r in mesure["C"]
          if r["nat1166"] != r["port1166"] or r["nat1011"] != r["port1011"]]
    assert not ko, "desaccord natif/port sur le partage 51/12 : %s" % ko


def test_LE_PARTAGE_51_12_la_tuile_du_decoy_est_refusee_par_51_et_NON_par_12(mesure):
    """Le coeur de la tranche. Les deux masques ne different, sur ce point, que par le bit 51 :

        1011 TunnelingHorror   0x8000000001042 = bits 1 | 6 | 12 | 51
        1166 AberrantHypermorph        0x1040  = bits     6 | 12

    Si le natif rend `TargetIsNotSteppable` pour l'un et `ValidRequest` pour l'autre SUR LA MEME
    TUILE, le refus est attribue au bit 51 et a lui seul."""
    disc = [r for r in mesure["C"]
            if r["label"].startswith("DECOY") and r["nat1166"] == 0 and r["nat1011"] == STEPPABLE]
    assert disc, (
        "aucune tuile de decoy ou 1011 refuse (51) ET 1166 accepte (0x0) -- la mesure ne "
        "DISCRIMINE pas le bit 51 du bit 12 : %s" % mesure["C"])


def test_1166_sait_refuser_par_le_bit_12(mesure):
    """Contre-partie du test precedent : 1166 n'accepte pas TOUT. Sans ca, son `0x0` sur la tuile
    du decoy ne prouverait rien."""
    refus = [r for r in mesure["C"] if r["nat1166"] == TILE_FREE]
    assert refus, ("1166 n'oppose `TargetTileIsFree` a AUCUNE tuile occupee -- son acceptation de "
                   "la tuile du decoy est degeneree : %s" % mesure["C"])


def test_sans_le_bit_51_le_port_n_oppose_plus_le_refus(mesure):
    """ETAGE D2 -- contrefactuel du CHAMP sur la VRAIE classe du registre : le bit est NECESSAIRE."""
    assert mesure["D"]["sans51"], "aucune ligne d'etage D"
    assert all(v != STEPPABLE for v in mesure["D"]["sans51"]), (
        "1011 privee du bit 51 refuse encore : l'armement ne vient pas du bit %s"
        % mesure["D"]["sans51"])


def test_le_bit_20_ne_desarme_PAS_le_bit_51(mesure):
    """ETAGE D3. Le natif teste le bit 51 EN PREMIER et saute au predicat (`else: goto TEST`) :
    `AllowSteppableUnit` ne vaut QUE pour la voie unit-targeting. NON CONFRONTE au natif -- aucune
    ability du registre ne pose le bit 20."""
    assert mesure["D"]["avec20"], "aucune ligne d'etage D"
    assert all(v == STEPPABLE for v in mesure["D"]["avec20"]), (
        "poser `AllowSteppableUnit` leve le refus du bit 51 : %s" % mesure["D"]["avec20"])


def test_verdict_global_du_probe(mesure):
    assert mesure["rc"] == 0, "le probe a rendu rc=%s" % mesure["rc"]
