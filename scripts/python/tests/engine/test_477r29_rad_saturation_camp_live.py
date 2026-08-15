"""GARDE #477-r29 -- `RadSaturationPlaybook` (1202) compte les AMIS, pas les DEUX CAMPS.

CE QUE CETTE GARDE PROTEGE. `case-26` specifiait le terme de mouvement de 1202 comme
« slot 0x82 = adjacent units, ring-1, BOTH teams » x `Utilities.Default.Contaminated.AffectedUnit`
(= -25), avec un predicat « allie non immunise a Contaminated ». Les TROIS faits sont faux sur le
build courant, et le decompile les remplace un par un :

  * le slot appele par `IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook.
    u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` est `0x83`, un
    `GetAdjacentFriends` a DEUX arguments -- donc les ALLIES du caster ;
  * le poids est `Utilities.Default.TriggeredAbilities.RadSaturation_AdjacentMarshals` = **+10** ;
  * le predicat `IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook.u003Cu003Ec$$
    u003CCalculateMovementUtilityInStepsInternalu003Eb__2_0` est
    `HasActiveAbility(f, 0x45e = ActiveAbilityType.DoctrinaImperatives)`.

⚠ LE CONFOND, et c'est lui qui rend la question NON RHETORIQUE : le MEME predicat `0x45e` est lu
par `IdunBattle.AI.Utilities.AttractMechanicalsUtility.u003CEvaluateMovementInStepsu003Ed__1$$
MoveNext` (feuille `DoctrinaImperatives_AttractMechanicals`), qui, LUI, interroge le slot `0x7a` =
`GetAdjacentUnits` a QUATRE arguments. Deux slots, deux noms, deux arites.
⚠ Ce fichier a ecrit ici « -- les DEUX CAMPS ». **FAUX**, mesure par #477-r31 : le call-site passe
`friendsOf = case.Unit`, donc cette feuille compte les AMIS elle aussi ; le nom du slot ne dit pas
le camp, ses ARGUMENTS si. Ce qui separe reellement les deux feuilles est le gate (`Mechanical`),
le self (exclu la, INCLUS ici) et l'agregation (`Any` la, `Count` ici).
Cette feuille est PORTEE et CONFRONTEE depuis #477-r31 -- et le greffon de CE montage reste choisi
NON Mechanical, sans quoi `X_nat` porterait deux `+10` sur les memes tuiles et la mesure ne
trancherait rien. Ce choix est donc devenu le CONTROLE du gate `Mechanical` de la feuille voisine :
mesure du 2026-08-06, retirer ce gate rend `test_le_natif_suit_le_modele_ALLIES` rouge (-10/tuile).

MONTAGE -- ON PILOTE LES POSITIONS (`--place`/`--a-place`) : une CIBLE NEUTRE au milieu, un Marshal
ALLIE et un Marshal ENNEMI a distance 2 d'elle, de part et d'autre, sur une zone STRICTEMENT PLATE.
Les tuiles d'attaque de la cible se ventilent alors en trois groupes MIROIR (adjacentes au Marshal
ALLIE seul / au Marshal ENNEMI seul / a aucun des deux) -- **seul le CAMP change**.

Le porteur reel de 1202 est un SUMMON (`admecSmnVanguard`) : le passif est GREFFE sur un heros du
pool, ce qui est ici une MESURE (le corps natif ne lit ni stats ni traits du caster).

Mesure fondatrice (`probe_477r29_rad_saturation_camp.py`, `MC1_67`/777, decomposition
`X = Tile(7) - Elevation - TileEffects` aux hooks EXISTANTS de `scorer-damage-trace`) :
`X_nat` = 10 sur les deux tuiles du bras ALLIE, **0** sur les quatre du bras ENNEMI, 0 sur le
temoin ; 0 desaccord `X_nat` vs `X_port` sur 8 tuiles. AUCUNE de ces valeurs n'est gelee ici : les
assertions re-derivent tout de la mesure du pas.

ASCII only.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine -> import du helper sibling

from counterproof import assert_sample_confrontable  # noqa: E402

import probe_477r29_rad_saturation_camp as P        # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MAX_STEPS = 25


#: DEUX couples board/seed, pour que le verdict ne tienne pas a UNE geometrie. Les positions sont
#: CHERCHEES par board (cf. `P.LAYOUTS`) : deux boards sur quatre essayes admettent une zone plate
#: ou les voisines de la cible se ventilent en trois groupes miroir.
CASES = [("MC1_67", "777"), ("C4_09", "31337")]


@pytest.fixture(scope="module", params=CASES, ids=lambda c: "%s-%s" % (c[0], c[1]))
def rad_case(request, rpc, build_runner):
    """La mesure du pas ou les DEUX bras (ALLIE / ENNEMI) sont HOOKES, hooks armes UNE fois.

    Le montage vit dans le probe (`P.build_extra` + `P.mesurer`, `call` INJECTE) : un seul foyer,
    deux consommateurs -- la garde ne re-code ni les placements ni la marche."""
    board, seed = request.param
    tag = uuid.uuid4().hex[:8]
    seed_bc = ROOT / "logs" / "runners" / ("test477r29-seedbc-%s.json" % tag)
    bc = P.catalog_inject._load_seed(None)
    P.catalog_inject.graft_passive_ability(bc, P.GRAFT, "RadSaturation", replace=True)
    seed_bc.parent.mkdir(parents=True, exist_ok=True)
    seed_bc.write_text(json.dumps(bc), encoding="utf-8")
    extra = P.build_extra(board)                       # FOYER UNIQUE du montage (cf. le probe)
    extra[1] = str(seed_bc)
    rid = build_runner(seed, extra=extra, board=board)["rid"]
    mes = P.mesurer(lambda m, b, t=90: rpc(m, b, t), rid, MAX_STEPS, trace=lambda *_a: None)
    try:
        seed_bc.unlink()
    except OSError:
        pass
    return SimpleNamespace(rid=rid, mes=mes)


def _rows(rad_case) -> list:
    """Les lignes de la mesure, ou un ROUGE qui NOMME la panne au lieu d'un `KeyError`.

    Mesure du 2026-08-06 : en retirant 1202 du registre (le mutant « etat d'AVANT la tranche »),
    `mesurer` rend `{"erreur": ...}` et cinq gardes tombaient sur `KeyError: 'rows'` -- un rouge
    juste, illisible. Le message doit dire CE QUI MANQUE."""
    mes = rad_case.mes
    assert not mes.get("erreur"), (
        "aucune mesure : %s. Les gardes suivantes ne disent RIEN tant que ce point n'est pas "
        "regle (cf. `test_le_montage_a_bien_ete_mesure`)" % mes.get("erreur"))
    # SECONDE panne, DISTINCTE (#10011) : le montage a abouti et les tuiles sont hookees, mais le
    # canal NATIF est muet -- `X_nat` n'existe sur aucune ligne. Sans ce cran, `divergences` rend 0
    # pour TOUS les modeles et le verdict d'accord passe A VIDE. Les gardes de MONTAGE, elles,
    # restent vertes a bon droit : ce n'est pas le montage qui est en cause.
    assert not mes.get("x_nat_indisponible"), (
        "le montage a ABOUTI (%d tuiles hookees) mais le canal NATIF est MUET : ce n'est PAS le "
        "port qui est en cause, c'est le CAPTEUR. %s"
        % (len(mes.get("rows") or ()), mes.get("x_nat_indisponible")))
    return mes["rows"]


def test_le_slot_du_playbook_est_un_getadjacentfriends():
    """ETAGE 1 (offline, aucun runner) : la table VERSIONNEE des slots d'interface.

    Deux assertions SYMETRIQUES, et c'est le couple qui porte le sens : le slot du playbook est un
    `GetAdjacentFriends` d'arite 2, celui de la feuille CONFOND un `GetAdjacentUnits` d'arite 4.
    Un renumerotage qui echangerait les deux ferait passer un port « deux camps » pour juste."""
    tbl = P._slot_table(P._build_hash())
    assert tbl.get(("IBattleQuery", 0x83)) == ("GetAdjacentFriends", 2), (
        "slot 0x83 = %r : le corps de RadSaturationPlaybook l'appelle avec 2 arguments "
        "(tile, case.Unit) -- si ce n'est plus un GetAdjacentFriends, c'est la RE qu'il faut "
        "refaire, pas le port" % (tbl.get(("IBattleQuery", 0x83)),))
    assert tbl.get(("IBattleQuery", 0x7a)) == ("GetAdjacentUnits", 4), (
        "slot 0x7a = %r : c'est celui de AttractMechanicalsUtility. Le contraste d'ARITE avec 0x83 "
        "est reel ; ce qu'il ne dit PAS, c'est le camp -- celui-la est un ARGUMENT du call-site "
        "(#477-r31)" % (tbl.get(("IBattleQuery", 0x7a)),))


def test_le_poids_bc_est_positif_et_sous_sa_vraie_cle():
    """ETAGE 1 (offline) : la cle LUE au litteral, et le multiplicateur que `case-26` lui pretait.

    Assertions dans les DEUX sens : la cle reelle rend un poids non nul, et la cle que la fiche
    citait (`Contaminated.AffectedUnit`) est un AUTRE poids -- confondre les deux inverserait le
    signe du terme."""
    from engine import weights as W
    from engine.playbook.rad_saturation import RadSaturationPlaybook
    wt = W.load()
    w = wt.sub("TriggeredAbilities", RadSaturationPlaybook.WEIGHT_KEY)
    assert w > 0, (
        "la cle BC %r rend %r : le litteral resolu par `probe_212_bc_key_literals.py --symbol "
        "IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook.u003CCalculateMovementUtilityInSteps"
        "Internalu003Ed__2$$MoveNext` a disparu de `Utilities.Default.TriggeredAbilities`"
        % (RadSaturationPlaybook.WEIGHT_KEY, w))
    faux = wt.sub("Contaminated", "AffectedUnit")
    assert faux != w, (
        "le multiplicateur que `case-26` pretait a ce terme (%r) vaut desormais la meme chose que "
        "le vrai (%r) : le montage ne separe plus les deux lectures" % (faux, w))


def test_le_port_lit_le_kit_ACTIF_du_voisin_pas_son_kit_declenche():
    """ETAGE 1 (offline) : le predicat porte sur `HasActiveAbility`, pas `HasTriggeredAbility`.

    Contre-epreuve OFFLINE a deux bras sur un `ctx` synthetique : le MEME id 1118 range en
    `triggered` ne doit RIEN valoir. `TriggeredAbilityType(1118)` existe et nomme autre chose
    (`TerrorsLament`) -- l'ordinal ne discrimine pas, seule la CALLEE le fait."""
    from engine import weights as W
    from engine.playbook.rad_saturation import RadSaturationPlaybook
    from engine.entities.active_ability_type import ActiveAbilityType
    pb = RadSaturationPlaybook()
    wt = W.load()
    aid = int(ActiveAbilityType.DoctrinaImperatives)
    neigh = {(1, 1): [(1, 0), (1, 2), (0, 1), (2, 1), (0, 0), (2, 0)]}
    base = {"self_pos": None, "unit_active_abilities": (), "elev_by_pos": {},
            "neigh_by_pos": neigh, "enemy_units": []}
    actif = dict(base, friend_units=[{"pos": (1, 0), "active": (aid,)}])
    declenche = dict(base, friend_units=[{"pos": (1, 0), "triggered": (aid,), "active": ()}])
    w = float(wt.sub("TriggeredAbilities", RadSaturationPlaybook.WEIGHT_KEY))
    assert pb.calculate_movement_utility_in_steps((1, 1), actif, wt) == w
    assert pb.calculate_movement_utility_in_steps((1, 1), declenche, wt) == 0.0, (
        "le port compte un voisin dont 1118 est un id DECLENCHE : il lirait alors "
        "`HasTriggeredAbility`, quand le natif appelle `HasActiveAbility`")


def test_le_montage_a_bien_ete_mesure(rad_case):
    """ROUGE DE SCENARIO (#462-r6) : sans mesure, aucune des gardes suivantes ne dit rien."""
    assert_sample_confrontable(
        not rad_case.mes.get("erreur"),
        mutation="build MC1_67/777 avec `--place`/`--a-place` (cible neutre au centre, un Marshal "
                 "ALLIE et un Marshal ENNEMI a distance 2, de part et d'autre) puis marche de la "
                 "trajectoire native jusqu'au pas ou les DEUX bras sont HOOKES",
        doit_casser="un pas ou les hooks `scorerTileTermTrace` couvrent a la fois une tuile "
                    "adjacente au Marshal ALLIE seul et une tuile adjacente au Marshal ENNEMI seul",
        observe=str(rad_case.mes.get("erreur")),
        remede="rejouer `python probe_477r29_rad_saturation_camp.py --board MC1_67 --seed 777` : "
               "il imprime, pas par pas, le nombre de candidates et la taille des deux bras. Les "
               "hooks ne voient que les tuiles du tier COMPARABLE (les tuiles d'ATTAQUE) : si un "
               "bras est vide, c'est la geometrie des placements qu'il faut re-etalonner")


def test_les_deux_bras_sont_hookes(rad_case):
    """ROUGE DE SCENARIO : sans les DEUX bras, le modele DEUX CAMPS n'est pas separable."""
    mes = rad_case.mes
    assert_sample_confrontable(
        bool(mes.get("bras_allie")) and bool(mes.get("bras_ennemi")),
        mutation="ventilation des tuiles HOOKEES par camp du Marshal adjacent",
        doit_casser="au moins une tuile par bras (ALLIE seul / ENNEMI seul)",
        observe="bras ALLIE=%s bras ENNEMI=%s" % (mes.get("bras_allie"), mes.get("bras_ennemi")),
        remede="cf. `test_le_montage_a_bien_ete_mesure`")


def test_le_natif_suit_le_modele_ALLIES(rad_case):
    """LE VERDICT : `X_nat == X_port`, tuile par tuile, sur toutes les tuiles hookees."""
    rows = _rows(rad_case)
    ecarts = [(r["tile"], r["na"], r["ne"], r["x_nat"], r["x_port"])
              for r in rows
              if r["x_nat"] is not None and abs(r["x_nat"] - r["x_port"]) > 1e-6]
    assert not ecarts, (
        "%d tuile(s) en desaccord X_nat vs X_port sur %d : %r -- le natif ne suit pas le modele "
        "ALLIES du port" % (len(ecarts), len(rows), ecarts))


def test_le_modele_DEUX_CAMPS_est_refute_par_la_mesure(rad_case):
    """LA QUESTION DU CAS : le modele de `case-26` DOIT diverger du natif.

    Sans cette divergence la garde precedente passerait a vide -- un montage ou les deux modeles
    coincident est un REGIME DEGENERE, pas une preuve."""
    div = P.divergences(_rows(rad_case))
    assert div.get("DEUX-CAMPS", 0) > 0, (
        "le modele DEUX CAMPS rend exactement ce que rend le modele ALLIES sur les %d tuiles "
        "mesurees (divergences par modele : %r) : la mesure ne tranche RIEN"
        % (len(_rows(rad_case)), div))


def test_les_mutants_du_terme_mordent_tous(rad_case):
    """CONTRE-EPREUVE : chaque lecture ALTERNATIVE du corps natif doit diverger de la mesure.

    `ABSENT (avant)` est l'etat du port AVANT cette tranche (1202 hors de
    `TRIGGERED_MOVE_PLAYBOOKS`, donc terme nul partout) : sa divergence chiffre le BUG corrige.
    `SELF-EXCLU` est traite a part -- il est INERTE PAR ALGEBRE (cf. le test suivant)."""
    div = P.divergences(_rows(rad_case))
    muets = [nom for nom in ("DEUX-CAMPS", "ENNEMIS", "SANS-PREDICAT", "POIDS -25",
                             "ABSENT (avant)")
             if not div.get(nom)]
    assert not muets, (
        "mutant(s) qui ne MORDENT PAS sur ce montage : %r (divergences mesurees : %r). Un mutant "
        "muet ne condamne pas le port -- il dit que ce montage ne le separe pas, et il faut soit "
        "le montage qui le separe, soit la declaration d'inertie qui l'explique" % (muets, div))
    assert not div.get("PORT (allies)"), (
        "le modele du port diverge de la mesure : c'est le verdict d'accord qui est rouge, pas "
        "la contre-epreuve (divergences : %r)" % div)


def test_le_volet_SELF_est_inerte_PAR_ALGEBRE_et_c_est_assertionne(rad_case):
    """Le corps natif n'exclut PAS `case.Unit` -- le port non plus. Ce volet ne peut pas mordre ici.

    Assertion dans les DEUX SENS, parce qu'une inertie non assertionnee est un trou :
      * AUCUNE ligne mesuree n'a `self = 1` -> le mover n'est jamais un Marshal ;
      * donc le mutant `SELF-EXCLU` ne DOIT pas mordre. S'il mordait, l'inertie declaree serait
        fausse et il faudrait relire la mesure, pas le port.
    La cause est structurelle sur ce build : `admecMarshall` porte 1118 en ACTIVE et n'a pas 1202
    en passif, `admecSmnVanguard`/`admecNpc1Vanguard` portent 1202 et n'ont AUCUNE active."""
    rows = _rows(rad_case)
    self_actif = [r["tile"] for r in rows if r["self"]]
    div = P.divergences(rows)
    assert not self_actif, (
        "le mover compte comme Marshal sur %r : l'inertie declaree est fausse, le volet SELF est "
        "exerce et la contre-epreuve doit inclure `SELF-EXCLU` parmi les mutants qui mordent"
        % (self_actif,))
    assert not div.get("SELF-EXCLU"), (
        "`SELF-EXCLU` diverge (%d tuiles) alors qu'aucune ligne n'a self=1 : la mesure et le "
        "modele ne lisent pas le meme substrat" % div["SELF-EXCLU"])
