"""GARDE LIVE #1023 -- `OmnissiahsBlessing` (passif 1299), confronte au natif.

Ce que cette garde exige, et de quel artefact : que le natif, apres une REPARATION dont le porteur
est le caster et dont il n'est pas la cible, ait DEPLACE la pile `1365 MachineVengeance` du porteur
vers la cible reparee -- et que le port, rejoue depuis la MEME capture, rende exactement les memes
niveaux des deux cotes.

Montage : `probe_1023_omnissiahs_blessing.py`. Les DEUX porteurs du passif sont hors pool (npc +
summon d'un npc), et les trois sources de l'effet transfere aussi -> GREFFE declaree sur
`admecManipulus` (HERO du pool, trait `Mechanic`), `ArcScourge` en vecteur de pose. La condition de
greffe est verifiee dans l'en-tete du probe : le passif n'a aucune variable de config et ne lit ni
stat ni trait du caster.

⚠ LE NIVEAU DU TEMOIN EST LOAD-BEARING. `--chain 2` place l'allie MECANIQUE au contact de l'ennemi
pour que la chaine d'`ArcScourge` fasse DEUX maillons, donc une pile de **2**. A une pile de 1,
<< transfere TOUT >> et << transfere UN >> rendraient le meme nombre et la mesure ne conclurait
RIEN -- le test le verifie explicitement avant d'assertionner le transfert. ASCII only.
"""
from __future__ import annotations

#: LIVE : le verdict depend du NATIF, donc de la session et du build -- aucun ensemble de chemins du
#: depot ne le determine. `toujours: True` est un RESULTAT : ce fichier doit se rejouer des qu'une
#: session tourne, y compris quand rien du port n'a bouge.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_1023_omnissiahs_blessing.py",
        "scripts/python/engine/runner/operations/triggers/loki/omnissiahs_blessing.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/repair.py",
        "scripts/python/engine/runner/abilities/admec.py",
        "scripts/python/engine/runner/abilities/repair.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/catalog_inject.py",
        "data/symbols/*/gameconfig.json",
    ),
    "build": True,
    "toujours": True,
    "raison": "Confrontation AU NATIF : le passif est monte par GREFFE (`PassiveAbilities += 1299`) "
              "sur `admecManipulus`, la pile de `1365 MachineVengeance` est posee par un cast reel "
              "d'`ArcScourge`, et les niveaux confrontes sortent du jeu (`decisionView.units[]."
              "effects`), pas du depot. Se rejoue donc a chaque passe live.",
}

import pytest        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)

import probe_1023_omnissiahs_blessing as P                                    # noqa: E402


@pytest.fixture(scope="module")
def blessing_case(rpc):
    """Le dict de mesure du montage. Le runner est monte ET dispose PAR LE PROBE (`keep=False`).
    ⚠ Montage non installe => ECHEC, jamais skip (#268)."""
    r = P.run(rpc, chain=2)
    if not r.get("ok"):
        pytest.fail("montage OmnissiahsBlessing NON INSTALLE : %s" % (r.get("why"),))
    return r


def test_la_greffe_a_pris_et_le_porteur_repare(blessing_case):
    """Sans `1173` monte, aucune pile ; sans `1119` (accordee par `GalvanicField` conserve), aucune
    reparation -- donc aucun `On(0x30 = UnitRepaired)`. Les deux sont des PREMISSES du montage, pas
    des observables : leur absence doit faire ECHOUER, jamais passer a vide."""
    ids = {a.get("id") for a in (blessing_case.get("carrier_abilities") or [])}
    assert P.ARC_SCOURGE_ID in ids, (
        "`ArcScourge` (%d) n'est pas montee sur %s : %s"
        % (P.ARC_SCOURGE_ID, P.CARRIER, blessing_case.get("carrier_abilities")))
    assert P.REPAIR_GALVANIC_ID in ids, (
        "`Repair_GalvanicField` (%d) n'est pas accordee -- `GalvanicField` (1199) a-t-il ete "
        "retire des passifs ? : %s" % (P.REPAIR_GALVANIC_ID, blessing_case.get("carrier_abilities")))


def test_le_temoin_est_NON_DEGENERE(blessing_case):
    """La pile posee doit valoir AU MOINS 2 : a 1, << transfere TOUT >> et << transfere UN >>
    rendent le meme nombre, et le reste du fichier ne conclurait RIEN."""
    n = int(blessing_case.get("niveau_pose") or 0)
    assert n >= 2, ("pile posee = %s -- le montage NE SEPARE PAS les deux hypotheses ; la chaine "
                    "d'`ArcScourge` doit faire au moins 2 maillons (cf. `--chain`)" % n)


def test_NATIF_la_pile_passe_du_porteur_a_la_cible_reparee(blessing_case):
    """L'observable : avant, la pile est sur le porteur ; apres, elle est sur la cible, ENTIERE, et
    le porteur n'en a PLUS."""
    n = int(blessing_case["niveau_pose"])
    avant = blessing_case["mv_avant_repair"]
    apres = blessing_case["mv_apres_repair"]
    assert avant.get(P.CARRIER) == n, "avant reparation, la pile doit etre sur %s : %s" % (
        P.CARRIER, avant)
    assert P.ALLY not in avant, "la cible ne doit RIEN porter avant : %s" % (avant,)
    assert apres.get(P.ALLY) == n, (
        "apres reparation, la cible doit porter la pile ENTIERE (%d) : %s" % (n, apres))
    assert P.CARRIER not in apres, (
        "le porteur doit avoir PERDU sa pile (`RemoveEffect(Owner, 0x555)`) : %s" % (apres,))


def test_PORT_rejoue_la_MEME_capture_et_rend_les_MEMES_niveaux(blessing_case):
    """Le port, seede depuis la capture d'AVANT la reparation, doit produire le meme deplacement --
    et il doit avoir FIRE exactement une fois."""
    n = int(blessing_case["niveau_pose"])
    port = blessing_case["port"]
    assert not port.get("error"), port
    assert port["before"] == {"carrier": n, "ally": 0}, port["before"]
    assert port["after"] == {"carrier": 0, "ally": n}, (
        "le port doit rendre le MEME etat que le natif (%s) : %s"
        % (blessing_case["mv_apres_repair"], port["after"]))
    assert port["fired"] == 1, "le passif doit fire EXACTEMENT une fois : %s" % (port,)
    assert port["event"]["level"] == n and port["event"]["target_level"] == n


def test_SANS_LE_RAIL_le_port_ne_fait_RIEN(blessing_case):
    """Contre-bras : `ability_states=False` -> le canal de greffe est MUET,
    `collect_triggered_abilities` retombe sur le kit gameconfig d'`admecManipulus` (qui ne contient
    PAS `OmnissiahsBlessing`), et le passif n'est pas monte. Sans ce bras, le test precedent
    pourrait passer pour une raison qui n'a rien a voir avec le port du passif."""
    n = int(blessing_case["niveau_pose"])
    sans = blessing_case["port_sans_rail"]
    assert not sans.get("error"), sans
    assert sans["fired"] == 0, "sans le rail, le passif ne doit PAS fire : %s" % (sans,)
    assert sans["after"] == {"carrier": n, "ally": 0}, (
        "sans le rail, RIEN ne doit bouger : %s" % (sans["after"],))
