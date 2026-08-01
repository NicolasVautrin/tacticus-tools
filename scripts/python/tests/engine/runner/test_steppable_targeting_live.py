"""GARDE live de la regle de ciblage `TargetIsNotSteppable` (bit 51, le DECOY) -- #442.

Le probe MESURE (`probe_442_steppable_targeting.py`), ce test GARDE : il rejoue, sur UN montage
monte une fois, l'accord entre le gate natif
(`abilityReason` -> `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`) et le port
(`engine/runner/abilities/targeting.get_invalid_target_reason`), pour l'ATTAQUE NORMALE d'une unite
qui a des DECOYS `Steppable` autour d'elle.

    genesPrimus --CultDemagogue(1179)--> un necroWarden   =>  N `genesSmnDecoy` ALLIES autour
    puis : le necroWarden ne peut PAS attaquer normalement un decoy.

CE QUE LE TEST EXIGE, ET POURQUOI CHAQUE EXIGENCE EST LA :
  * le SUBSTRAT d'abord -- l'etat RECHARGE depuis `combatSnapshot` porte `Steppable` sur les
    decoys. C'est la lecon de #436 : une regle dont la donnee n'est ecrite par personne est VERTE
    ET VIDE. Ici la donnee est un TRAIT, seede par `snapshot._load_unit_traits` ;
  * accord natif/port sur TOUTES les lignes -- le fond ;
  * au moins une ligne ou le natif rend `TargetIsNotSteppable` ;
  * cette ligne doit etre une ou le port DESARME (bit 20 `AllowSteppableUnit`, donc EXACTEMENT ce
    que `master` rendait) accepte : la degradation de cette regle est PERMISSIVE, donc un accord
    sur un cast ACCEPTE ne prouve RIEN ;
  * au moins une cible reste LEGALE -- sinon la mesure ne distingue pas « la regle mord » de
    « plus rien n'est ciblable » ;
  * le DESARMEMENT `AllowSteppableUnit` (bit 20) fait basculer les lignes refusees, et RIEN
    d'autre. NON CONFRONTE au natif : aucune ability du registre ne pose ce bit ;
  * la voie du BIT 51 : une ability qui le POSE refuse MALGRE le bit 20 et refuse aussi en mode
    TILE-targeting sur la tuile du decoy -- le regime de 1011 `TunnelingHorror`, dont le seul
    porteur est un summon d'ENVIRONNEMENT (`EnvFactionSummons:Necrons`), donc NON CONFRONTE.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import pytest

import probe_442_steppable_targeting as P
from engine.runner.abilities.targeting_rule import TargetingRule as TR


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


def test_le_substrat_porte_le_trait_sur_les_decoys(mesure):
    """ETAGE A. Sans ce canal, la regle serait juste et INERTE (mode de defaillance de #436)."""
    assert mesure["decoys"], "aucun decoy `genesSmnDecoy` en vie -- montage rate"
    manquants = [d for d in mesure["decoys"] if d not in mesure["steppable"]]
    assert not manquants, (
        "les decoys %s n'ont PAS le trait `Steppable` dans l'etat recharge -- "
        "`snapshot._load_unit_traits` ne publie pas le substrat que la regle lit" % manquants)


def test_accord_natif_port_sur_toutes_les_lignes(mesure):
    ko = [r for r in mesure["rows"] if r["nat"] != r["port"]]
    assert not ko, "desaccord natif/port : %s" % ko


def test_le_natif_refuse_bien_TargetIsNotSteppable(mesure):
    """Sans une ligne REFUSEE par le natif, l'accord ne prouve rien (degradation PERMISSIVE)."""
    refus = [r for r in mesure["rows"] if r["nat"] == int(TR.TargetIsNotSteppable)]
    assert refus, ("aucune ligne 0x%x -- aucun decoy n'a ete confronte au gate natif"
                   % int(TR.TargetIsNotSteppable))


def test_la_ligne_refusee_etait_ACCEPTEE_par_le_port_avant(mesure):
    """LE test de la tranche : la regle ferme une regression PERMISSIVE. `portDesarme` = le masque
    de l'attaque normale + `AllowSteppableUnit` = ce que `master` rendait (la regle portee ici est
    gatee par ce seul bit sur la voie unit-targeting)."""
    gains = [r for r in mesure["rows"]
             if r["nat"] == int(TR.TargetIsNotSteppable) and r["portDesarme"] == 0]
    assert gains, ("aucune ligne ou le natif REFUSE (Steppable) et ou le port AVANT ACCEPTAIT "
                   "(0x0) -- lignes : %s" % mesure["rows"])


def test_au_moins_une_cible_reste_legale(mesure):
    """La restriction porte sur les `Steppable`, pas sur tout le plateau."""
    ok = [r for r in mesure["rows"] if r["nat"] == 0 and r["port"] == 0]
    assert ok, "aucune cible legale -- la mesure ne discrimine plus rien : %s" % mesure["rows"]


def test_le_bit_20_desarme_la_regle_et_rien_d_autre(mesure):
    """`AllowSteppableUnit` : contrefactuel du CHAMP (offline, non confronte au natif)."""
    bascule = [r for r in mesure["rows"] if r["portDesarme"] != r["port"]]
    assert bascule, ("poser le bit 20 ne change AUCUNE ligne -- le desarmement n'est pas exerce "
                     "par cet etat")
    for r in bascule:
        assert r["port"] == int(TR.TargetIsNotSteppable), (
            "le bit 20 ne doit lever QUE le refus `TargetIsNotSteppable` : %s" % r)


def test_le_bit_51_refuse_malgre_le_desarmement_et_en_mode_tuile(mesure):
    """ETAGE D -- la voie du BIT. Le natif teste le bit 51 EN PREMIER (`else: goto TEST`), donc
    `AllowSteppableUnit` ne le desarme pas ; et sous `TargetIsTile` le predicat resout la TUILE en
    son occupant. C'est le regime de 1011 `TunnelingHorror`."""
    assert mesure["bit51"], "aucune ligne d'etage D"
    for r in mesure["bit51"]:
        assert r["bit51_unit"] == int(TR.TargetIsNotSteppable), (
            "bit51+bit20 devrait REFUSER (le desarmement ne vaut que pour unit-targeting) : %s" % r)
        assert r["bit51_tile"] == int(TR.TargetIsNotSteppable), (
            "bit51+bit6 sur la TUILE du decoy devrait REFUSER (GetUnit resout l'occupant) : %s" % r)


def test_verdict_global_du_probe(mesure):
    assert mesure["rc"] == 0, "le probe a rendu rc=%s" % mesure["rc"]
