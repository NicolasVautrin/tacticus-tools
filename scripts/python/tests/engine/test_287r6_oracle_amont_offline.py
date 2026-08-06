"""#287-r6 -- GARDE du cran d'ORACLE : `abilityReason` n'est un oracle de CIBLAGE que s'il a
traverse la cascade. OFFLINE (aucun runner, aucun RPC).

POURQUOI OFFLINE, ET POURQUOI CE CRAN. `abilityReason` appelle
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`, qui refuse EN AMONT -- code `1`,
`TargetingRule.ValidRequest` -- des que l'ability est indisponible ; le port, lui, mirror
`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget`, qui n'a PAS cet etage. Dans ce
regime l'oracle rend `1` pour TOUTE cible : la confrontation compare deux fonctions natives
differentes, et le desaccord se lit comme un bug du port. C'est arrive -- QUATRE couples
`SquigMine` sur `MC1_67` comptes « violations preexistantes » (natif `0x1`, port `0x1000`) alors
que la cascade, une fois traversee, rend `0x1000` DES DEUX COTES.

La degradation est SILENCIEUSE et ne rougit nulle part ailleurs : le probe live etait VERT (il
attribuait les 4 couples a « preexistant »), et aucun test offline ne regarde l'oracle.

CINQ ETAGES, chacun voyant une faute que le precedent declare verte :

  1. LE GISEMENT EXISTE, et le recensement ASSERTIONNE SON PROPRE NON-VIDE. Un ensemble vide
     passerait pour un vert -- exactement le vice releve dans CLAUDE.md sur les ordinaux communs.
  2. TRI-ETAT de `cooldown_initial` : `None` (cle absente) / `0` (mesure) / `>= 1` (arme). Rabattre
     `None` sur `0` ferait croire la constante mesuree partout.
  3. ORDINAL FIGE AU SITE : `CODE_AMONT` vaut la valeur MESUREE au decompile. `probe_313` compare
     le mirror au build et redeviendrait vert apres un renumerotage qui aurait deja fausse le site.
  4. LE DISCRIMINANT BASCULE, et son MUTANT effondre la bascule.
  5. LE CHAINON COMPLET : `probe_287r4r1_generalisation_live.mesurer` ne classe PLUS un couple
     court-circuite en VIOLATION. Etage indispensable -- les etages 1-4 testent le helper isole et
     resteraient verts si le probe cessait de l'appeler. Son MUTANT (cran desarme) doit re-produire
     la violation, sinon le substrat ne teste rien.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[2]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import oracle_targeting as O                                          # noqa: E402
import probe_287r4r1_generalisation_live as G                         # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType     # noqa: E402
from engine.entities.pathfinding.board import Board                   # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR  # noqa: E402

# Les trois etats du tri-etat, chacun sur un id MESURE au gameconfig `rnca9r7q6c`.
ID_ARME = int(ActiveAbilityType.SquigMine)              # 1201, initialCooldownTurns = 1
ID_MESURE_ZERO = int(ActiveAbilityType.SporeMineLauncher)   # 1145, initialCooldownTurns = 0
ID_SANS_CLE = int(ActiveAbilityType.AdaptiveStrategy)   # 1005, la cle est ABSENTE


# ------------------------------------------------------------------ 1. LE GISEMENT

def test_le_gisement_existe_et_le_recensement_assertionne_son_non_vide():
    """Des abilities PORTEES court-circuitent l'oracle au tour 1 -- et on l'assertionne.

    Sans ce cran, un recensement qui rendrait un ensemble VIDE (cle renommee au build suivant,
    gameconfig introuvable) laisserait les etages suivants verts par vacuite."""
    armes = O.ids_a_cooldown_initial()
    assert armes, ("recensement VIDE : soit `constants.initialCooldownTurns` a change de nom au "
                   "build, soit le gameconfig n'est pas lu -- dans les deux cas le cran est aveugle")
    assert ID_ARME in armes, "1201 SquigMine est le cas MESURE de #287-r6 ; il doit etre recense"
    assert armes[ID_ARME] >= 1


# ------------------------------------------------------------------ 2. TRI-ETAT

def test_cooldown_initial_distingue_absent_de_zero():
    """`None` (pas de cle) et `0` (cle a zero) sont DEUX etats, pas un.

    Les rabattre l'un sur l'autre est la faute que `host_inputs` interdit partout ailleurs : ici
    elle ferait declarer « cooldown mesure a 0 » une ability dont la constante n'existe pas."""
    assert O.cooldown_initial(ID_SANS_CLE) is None
    assert O.cooldown_initial(ID_MESURE_ZERO) == 0
    assert O.cooldown_initial(ID_ARME) >= 1
    # ... et le recensement n'admet QUE le troisieme etat.
    armes = O.ids_a_cooldown_initial([ID_SANS_CLE, ID_MESURE_ZERO, ID_ARME])
    assert set(armes) == {ID_ARME}


# ------------------------------------------------------------------ 3. ORDINAL FIGE AU SITE

def test_le_code_amont_est_fige_a_la_valeur_lue_au_decompile():
    """`AttackQuery` rend le litteral `1`, et ce `1` EST `TargetingRule.ValidRequest`.

    On garde les DEUX faces : la valeur (figee au site, ce que `probe_313` ne peut pas voir) et
    l'appariement au membre nomme (ce qui rendrait visible un renumerotage de l'enum)."""
    assert O.CODE_AMONT == 1
    assert O.CODE_AMONT == int(TR.ValidRequest)
    assert TR.ValidRequest.name == "ValidRequest"


# ------------------------------------------------------------------ 4. LE DISCRIMINANT

def _reponse(caster_hex: str, target_hex: str = "0x0000000000000001", etat=None) -> dict:
    return {"casterReason": {"hex": caster_hex, "reasons": []},
            "targetReason": {"hex": target_hex, "reasons": []},
            "abilityState": etat}


def test_le_discriminant_bascule_sur_caster_reason():
    """Le cran lit `casterReason`, JAMAIS `targetReason` -- et c'est tout l'interet.

    Les deux reponses ci-dessous portent le MEME `targetReason == 1` ; seule la premiere est un
    court-circuit. Un cran ecrit sur `targetReason` les confondrait, et ecarterait a tort les refus
    que la branche `TargetIsTile` de
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` rend pour une tuile non
    marchable -- meme ordinal, autre sens."""
    assert O.oracle_court_circuite(_reponse("0x0000000000000001")) is True
    assert O.oracle_court_circuite(_reponse("0x0000000000000000")) is False
    # PANNE DE CAPTEUR : pas de `casterReason` mesure -> on ne FABRIQUE pas un court-circuit.
    assert O.oracle_court_circuite({"targetReason": {"hex": "0x1"}}) is False
    assert O.oracle_court_circuite(None) is False


def test_la_cause_publiee_ne_suppose_rien_de_ce_qui_n_est_pas_mesure():
    """`abilityState` ne publie que cooldown/disabled/usable : les autres termes natifs
    (`ability+0x44`, `IsDamagedMachine`) sortent en `indeterminee`, jamais en supposition."""
    assert "cooldown=1" in O.cause_du_court_circuit(
        _reponse("0x1", etat={"usable": True, "cooldown": 1, "disabled": False}))
    assert "disabled" in O.cause_du_court_circuit(
        _reponse("0x1", etat={"usable": True, "cooldown": 0, "disabled": True}))
    assert "non publie" in O.cause_du_court_circuit(_reponse("0x1", etat=None))
    assert "indeterminee" in O.cause_du_court_circuit(
        _reponse("0x1", etat={"usable": True, "cooldown": 0, "disabled": False}))


# ------------------------------------------------------------------ 5. LE CHAINON COMPLET

COLS = ROWS = 4


def _board() -> Board:
    import hexgeo
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [c * ROWS + r + 1 for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": col * ROWS + row + 1, "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return Board(out, adjacency="evenq")


def _contexte_1201():
    """Le contexte minimal que `mesurer` consomme, avec `orksRukkatrukk` en acteur MoW.

    Une unite occupe la tuile 1 : c'est elle qui fait rendre `TargetTileIsFree` au port sur la
    tuile OCCUPEE -- donc un `port != 0` face a un oracle qui, court-circuite, rendrait `1`. Sans
    cette occupation le substrat serait DEGENERE (port `0` partout) et l'etage passerait pour vert
    sans rien exercer."""
    board = _board()
    dv = {"currentPlayer": 3,
          "units": [{"id": 90, "visualId": "necroWarden", "alive": True, "team": 1, "owner": 1,
                     "pos": {"col": 0, "row": 0}, "effects": []}],
          "mows": [{"casterId": 91, "visualId": "orksRukkatrukk"}]}
    ob = {"units": [{"squadId": 90, "hp": 100, "hpMax": 100}]}
    snap = {"units": [{"entityId": 90, "traits": []}]}
    alive = [u for u in dv["units"] if u["alive"]]
    by_vis = {"necroWarden": {"id": 90}, "orksRukkatrukk": {"id": 91}}
    return dv, ob, snap, board, alive, by_vis


def _mesure_avec_oracle_court_circuite(monkeypatch, cran_arme: bool) -> dict:
    """Joue `mesurer` contre un oracle qui court-circuite, cran ARME ou DESARME."""
    monkeypatch.setattr(G, "PORTEES", [(ID_ARME, "orksRukkatrukk")])
    monkeypatch.setattr(G, "_rpc", lambda m, b, t=90000: _reponse("0x0000000000000001"))
    if not cran_arme:
        # LE MUTANT : le cran ne voit plus rien. C'est litteralement l'etat d'avant #287-r6.
        monkeypatch.setattr(G.O, "oracle_court_circuite", lambda _r: False)
    return G.mesurer(0, _contexte_1201())


def test_un_couple_court_circuite_n_est_PAS_compte_en_violation(monkeypatch):
    """Le chainon : le probe live CONSULTE le cran, et range le couple en NON CONFRONTE."""
    res = _mesure_avec_oracle_court_circuite(monkeypatch, cran_arme=True)
    assert res["viol"] == [], "un oracle court-circuite ne peut pas produire une VIOLATION"
    assert [x[0] for x in res["court_circuite"]] == [ID_ARME]
    assert res["cibles"] == 0, "aucune cible ne doit avoir ete confrontee pour ce couple"


def test_le_mutant_reproduit_la_violation_de_287r4r1(monkeypatch):
    """MUTANT -- et il DOIT mordre : sans lui, l'etage precedent serait vrai par vacuite.

    Cran desarme, le meme substrat re-produit exactement le rouge d'origine : natif `0x1`
    (`ValidRequest`), port `0x1000` (`TargetTileIsFree`) sur la tuile OCCUPEE."""
    res = _mesure_avec_oracle_court_circuite(monkeypatch, cran_arme=False)
    assert res["court_circuite"] == []
    assert res["viol"], ("MUTATION INERTE : le substrat ne produit aucune violation meme cran "
                         "desarme -- l'etage precedent ne prouverait alors rien")
    natifs = {r[4] for r in res["viol"]}
    ports = {r[6] for r in res["viol"]}
    assert natifs == {hex(int(TR.ValidRequest))}
    assert hex(int(TR.TargetTileIsFree)) in ports


def test_le_probe_live_importe_bien_le_foyer_partage():
    """Le cran vit dans UN foyer (`oracle_targeting`), pas recopie dans chaque probe.

    Garde structurelle : si un refactor recopiait le predicat dans le probe, le mutant de l'etage
    precedent cesserait de mordre sans que rien ne rougisse."""
    assert G.O is O


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
