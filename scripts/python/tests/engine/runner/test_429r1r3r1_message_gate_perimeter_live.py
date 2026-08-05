"""#429-r1-r3-r1 -- LE PERIMETRE du gate de message : quels messages, quel bout, quel predicat.

CE QUI EST GARDE ICI, ET EN QUOI CE N'EST PAS #429-r1-r3
--------------------------------------------------------
#429-r1-r3 a pose le gate sur la voie d'ABILITY et mesure son ETAGE sur la CIBLE MORTE. Trois
trous restaient, tous NON MESURES -- ils sont fermes ici, et chacun par une MESURE :

1. **QUELS MESSAGES.** Les XREFS d'`IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled` :
   **2 appels** dans tout `rnca9r7q6c`, tous deux dans
   `IdunBattle.Messages.InputMessageProcessor$$Visit(ActiveAbilityMessage)`.
   `Visit(MoveUnitMessage)`, lue au decompile, n'a AUCUN gate de liveness.
   Et il n'existe **aucun** `AttackUnitMessage` natif (41 classes de message, 37 surcharges de
   `Visit`) : l'attaque normale COMMANDEE est un `ActiveAbilityMessage` (#139), donc elle traverse
   ce MEME gate. Le port a deux visiteurs pour cet unique site natif ; seul celui des abilities
   portait le gate.

2. **QUEL BOUT.** Le volet CASTER n'avait jamais ete confronte. Il l'est, par le meme capteur
   d'etage que #429-r1-r3 (le groupe de stream `User_UseAbility`, ouvert par la lambda du `Visit`).

3. **QUEL PREDICAT.** `UnitFlag.Fled` (9) est le SEUL regime qui separe `IsAliveAndNotFled` de
   « pas mort » : sur la MORT les deux etages convergent. Il est confronte ici en LIVE, par un
   montage `BattleFatigue` (seul declencheur d'`IdunBattle.Operations.FleeOperation$$Execute`,
   seul ecrivain du flag 9 dans le binaire).

CHIFFRES MESURES (build `rnca9r7q6c`, board MC1_67, seed 777) :
  * CASTER  -- temoin (meme caster VIVANT) : 2 evenements, groupe [12] ; caster CADAVRE : **0**.
  * ATTAQUE -- natif sur cadavre : 0 evenement ; port : refus, et le refus SURVIT a la
    neutralisation du gate de message (le gate d'operation prend le relais) ; les DEUX
    neutralises : **10375 degats sur le cadavre** + flags de tour poses.
  * FLED    -- temoin : 2 evenements, groupe [12] ; cible ENFUIE a **hp 1000/1000** : **0**.
    PV PLEINS => aucun predicat « pas mort » ne peut expliquer ce refus.

LIVE-agreement, ASCII only. Cf. docs/rl/case-429r1r3r1-perimetre-gate-message.md.
"""
from __future__ import annotations

import pytest

import probe_429r1r3r1_message_gate_perimeter as P

STREAM_GROUP_USER_USE_ABILITY = P.STREAM_GROUP_USER_USE_ABILITY


@pytest.fixture(scope="module")
def caster(live_session, tmp_path_factory):
    sf = tmp_path_factory.mktemp("t429r1r3r1c") / "state.json"
    r = P.scenario_caster(str(sf), seed="777", board="MC1_67", verbose=False)
    if r.get("why"):
        pytest.fail("montage CASTER non installe : %s" % r["why"], pytrace=False)
    return r


@pytest.fixture(scope="module")
def attaque(live_session, tmp_path_factory):
    sf = tmp_path_factory.mktemp("t429r1r3r1a") / "state.json"
    r = P.scenario_attaque(str(sf), seed="777", board="MC1_67", verbose=False)
    if r.get("why"):
        pytest.fail("montage ATTAQUE non installe : %s" % r["why"], pytrace=False)
    return r


@pytest.fixture(scope="module")
def fled(live_session, tmp_path_factory):
    """Le regime FLED. La fuite est un TIRAGE (`BattleFatigue` : `chance`=10, `chance_2`=40 en
    overkill, `BC.Abilities.PassiveAbilities.BattleFatigue`), donc le montage joue jusqu'a DEUX
    evenements de mort, chacun faisant tirer chaque garde adjacent. Mesure du 2026-08-05 : 4
    tirages joues, 4 fuites. Un montage rate est un `fail`, jamais un skip (#455)."""
    sf = tmp_path_factory.mktemp("t429r1r3r1f") / "state.json"
    r = P.scenario_fled(str(sf), seed="777", board="MC1_67", essais=2, verbose=False)
    if r.get("why"):
        pytest.fail("montage FLED non installe : %s" % r["why"], pytrace=False)
    return r


# ------------------------------------------------------------------ 1. LE PERIMETRE (OFFLINE)
def test_le_gate_vit_dans_les_DEUX_portes_du_port_et_nulle_part_ailleurs():
    """OFFLINE. Le natif teste `IsAliveAndNotFled` sur UN SEUL message (2 xrefs, meme `Visit`).
    Le port scinde ce message en deux visiteurs -- le gate doit donc vivre dans EXACTEMENT ces
    deux-la. La contre-epreuve est INTEGREE et porte sur des NOMS, pas sur un seuil : le scan doit
    RETROUVER les visiteurs connus SANS gate, sinon son silence sur eux ne vaudrait rien."""
    r = P.volet_scan(verbose=False)
    assert r["manquants"] == [], (
        "un visiteur du port modelise `Visit(ActiveAbilityMessage)` SANS son gate de liveness "
        "(%s) -- c'est le trou #429-r1-r3-r1" % r["manquants"])
    assert r["en_trop"] == [], (
        "un visiteur porte le gate alors qu'aucune surcharge native de `Visit` ne le teste pour "
        "son message (%s) -- re-lire les XREFS d'`IsAliveAndNotFled` avant d'elargir" % r["en_trop"])
    assert r["temoins_invisibles"] == [], (
        "le scan ne VOIT plus les visiteurs sans gate %s -- son silence ci-dessus ne prouve donc "
        "rien" % r["temoins_invisibles"])


# ------------------------------------------------------------------ 2. LE VOLET CASTER (LIVE)
def test_le_temoin_prouve_qu_un_cast_ADVERSE_atteint_bien_l_operation(caster):
    """PREALABLE INDISPENSABLE. Le caster du bras suivant est une unite ADVERSE : sans ce temoin,
    « 0 evenement » se lirait aussi bien « le pipeline refuse les casts adverses »."""
    t = caster["temoin_caster_vivant"]
    assert t["events"] and t["events"] > 0, (
        "temoin : un cast d'un caster ADVERSE VIVANT doit produire des evenements, obtenu %s" % t)
    assert STREAM_GROUP_USER_USE_ABILITY in (t["groups"] or []), (
        "temoin : le groupe `User_UseAbility` doit etre OUVERT (refus au rang OPERATION), "
        "obtenu %s" % t["groups"])


def test_le_volet_CASTER_du_gate_est_au_rang_MESSAGE(caster):
    """LA MESURE. MEME caster, MEME message, MEME cible -- seul son etat a change. Le groupe n'est
    plus ouvert : le refus est en amont de la lambda du `Visit`, donc au rang du MESSAGE."""
    assert caster["caster_alive"] is False, "prealable : le caster doit etre un CADAVRE"
    b = caster["caster_cadavre"]
    assert b["events"] == 0, (
        "caster mort : 0 evenement attendu (rang MESSAGE), obtenu %s" % b)
    assert b["groups"] == [], (
        "caster mort : AUCUN groupe ne doit s'ouvrir, obtenu %s" % b["groups"])
    assert b["action_consumed"] is False


def test_le_port_attribue_le_refus_du_CASTER_etage_par_etage(caster):
    """DECOMPOSITION PAR ETAGE cote port : on neutralise les gates UN A UN et le refus DESCEND.
    C'est ce qui distingue « le gate est ecrit » de « le gate est celui qui mord »."""
    assert caster["port_nominal"].get("not_alive_and_not_fled") == "caster", (
        "rang MESSAGE attendu, obtenu %s" % caster["port_nominal"])
    assert caster["port_sans_gate_message"].get("actor_dead") is True, (
        "gate de message neutralise : le refus doit DESCENDRE au gate acteur-mort #70, "
        "obtenu %s" % caster["port_sans_gate_message"])
    assert caster["port_sans_les_deux"].get("invalid_target") is not None, (
        "les deux gates de liveness neutralises : le refus doit descendre encore, au gate de "
        "CIBLE #115 -- obtenu %s" % caster["port_sans_les_deux"])


# ------------------------------------------------------------------ 3. LA VOIE ATTAQUE (LIVE)
def test_le_natif_refuse_l_attaque_normale_COMMANDEE_au_rang_MESSAGE(attaque):
    """L'attaque normale commandee EST un `ActiveAbilityMessage` : elle doit tomber au MEME rang
    que les abilities. 0 evenement, aucun groupe."""
    n = attaque["natif_attaque_cadavre"]
    assert n["events"] == 0, ("natif : 0 evenement attendu, obtenu %s" % n)
    assert n["groups"] == []
    assert n["action_consumed"] is False


def test_sur_la_MORT_les_deux_etages_du_port_CONVERGENT_et_c_est_MESURE(attaque):
    """LA CONVERGENCE, mesuree et non supposee. Sur un CADAVRE, neutraliser le seul gate de
    MESSAGE ne doit RIEN changer : le gate d'OPERATION (#429-r1) prend le relais. C'est ce qui
    explique que le trou de la voie `AttackUnitMessage` ait pu vivre sans casser un seul test."""
    assert attaque["port_nominal"] is None, (
        "port : aucun coup attendu sur un cadavre, obtenu %s" % attaque["port_nominal"])
    assert attaque["port_sans_gate_message"] is None, (
        "gate de MESSAGE neutralise : le gate d'OPERATION doit encore refuser -- obtenu %s"
        % attaque["port_sans_gate_message"])


def test_la_mutation_MORD_quand_les_DEUX_gates_tombent(attaque):
    """Sans cette ligne, les deux verts precedents pourraient venir d'un montage inerte."""
    assert attaque["port_sans_les_deux_total"] and attaque["port_sans_les_deux_total"] > 0, (
        "les deux gates neutralises : le port doit frapper le cadavre, obtenu %s"
        % attaque["port_sans_les_deux_total"])
    assert attaque["port_sans_les_deux_flags"] is True, (
        "les deux gates neutralises : le port consommait AUSSI l'action de l'attaquant")


# ------------------------------------------------------------------ 4. LE REGIME FLED (LIVE)
def test_le_montage_produit_une_unite_ENFUIE_A_PV_PLEINS(fled):
    """PREALABLE, et c'est LUI qui rend la mesure discriminante : l'enfui n'est PAS un cadavre.
    `IdunBattle.Entities.Components.HealthComponent$$IsDead` est FAUX sur lui."""
    assert fled["fled_id"] is not None
    assert fled["enfui_hp"] and fled["enfui_hp"] > 0, (
        "l'enfui doit garder ses PV -- sinon le regime se confond avec la MORT, obtenu %s"
        % fled["enfui_hp"])
    assert fled["enfui_alive"] is False, (
        "`UnitExtensions.IsAlive` doit rendre FAUX sur l'enfui (il teste aussi le flag 6 et "
        "l'appartenance a la collection), obtenu %s" % fled["enfui_alive"])


def test_le_temoin_FLED_prouve_que_le_capteur_d_etage_est_arme(fled):
    """Meme role que le temoin du volet CASTER : un « 0 evenement » n'est interpretable que
    confronte a un refus dont on SAIT qu'il est au rang de l'OPERATION."""
    t = fled["temoin_cible_vivante"]
    assert t is not None and t["events"] and t["events"] > 0, (
        "temoin : cible VIVANTE, le pipeline doit produire des evenements, obtenu %s" % t)
    assert STREAM_GROUP_USER_USE_ABILITY in (t["groups"] or [])


def test_le_natif_refuse_une_cible_ENFUIE_donc_le_predicat_n_est_PAS_pas_mort(fled):
    """LA REFUTATION. La cible a ses PV PLEINS : un gate « pas mort » ne la refuserait PAS.
    Le natif la refuse quand meme, et au rang du MESSAGE (aucun groupe ouvert). C'est la
    confirmation LIVE de la branche `HasFlag(unit, 9 = UnitFlag.Fled)` d'`IsAliveAndNotFled`."""
    n = fled["natif_sur_enfui"]
    assert n["events"] == 0, ("natif sur enfui : 0 evenement attendu, obtenu %s" % n)
    assert n["groups"] == []
    assert n["action_consumed"] is False


def test_le_flag_FLED_atteint_le_port_ou_son_ABSENCE_est_ATTRIBUEE(fled):
    """PENDANT DE CAPTEUR, et il est ASSUME. Le canal de seed (`combatSnapshot`) n'enumerait que
    les unites VIVANTES : `UnitFlag.Fled` n'atteignait donc JAMAIS le port, et son gate -- pourtant
    correct -- ne pouvait pas mordre. Le correctif (bloc `unitsNotAlive`) vit dans
    `frida/hooks/features/ai-step/rpc-snapshot.ts` et EXIGE UNE FENETRE DE REINJECT.

    Ce test ASSERTE dans les deux regimes, et le discriminant est MESURE (presence du champ), pas
    suppose : tant que le bundle charge est anterieur, il garde l'ATTRIBUTION de la divergence ;
    des que le champ apparait, il exige l'ACCORD avec le natif."""
    if fled["snapshot_porte_unitsNotAlive"]:
        assert fled["port_voit_le_flag"] is True, (
            "le capteur publie `unitsNotAlive` mais le port n'a pas pose `UnitFlag.Fled` -- "
            "le lecteur `_load_unit_flags` ne consomme pas le bloc")
        assert fled["port_attaque_nominal"] is None, (
            "flag vu : le port doit refuser comme le natif, obtenu %s"
            % fled["port_attaque_nominal"])
    else:
        assert fled["port_voit_le_flag"] is False
        assert (fled["port_attaque_nominal"] or {}).get("total"), (
            "sans le bloc `unitsNotAlive`, le port DOIT encore frapper l'enfui -- si ce n'est plus"
            " le cas, l'attribution de la divergence a change et cette tranche est a re-lire")
        assert fled["port_is_alive_and_not_fled"] is True, (
            "attribution : c'est bien parce que le port croit l'unite VIVANTE que son gate ne "
            "mord pas -- obtenu %s" % fled["port_is_alive_and_not_fled"])
        assert fled["port_unit_is_dead"] is False, (
            "et le gate d'OPERATION ne peut pas rattraper : `IsDead` exclut expressement `Fled`")
