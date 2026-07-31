"""GARDE #363 -- une relique EQUIPEE arrive-t-elle cote port SANS que l'appelant la demande ?

LE RESIDU QUE CES GARDES FERMENT (#357-r1). #357 a pose le rail de la relique equipee et l'a
confronte live, mais son canal (`load_state(ability_states=...)`) etait OPT-IN et n'avait qu'UN
producteur -- `probe_357_relic_rail.py`. Hors de ce montage, une relique equipee restait INERTE cote
port : le trigger n'etait jamais inscrit, SANS erreur ni trace. Et cela valait pour les QUATRE unites
qui en portent une DES LE SEED BC, donc pour n'importe quelle bataille qui les aligne.

Depuis #363 le canal est ACTIF PAR DEFAUT : `load_state(dv, ob, snap)` va chercher
`unitAbilityStates` elle-meme des qu'un transport ambiant est lie (`snapshot.bind_live_rpc`, pose par
la fixture `live_session` pour toute la suite). Ces gardes verrouillent ce defaut -- il n'a AUCUN
autre lecteur, donc rien d'autre ne le ferait rougir s'il se debranchait.

CE QUE CHAQUE GARDE SEPARE
  * `auto` == oracle NATIF  -- le port voit ce que `IdunBattle.Entities.Factories.UnitFactory$$
    AddConfiguredAbilities` a REELLEMENT monte (entrees de hierarchie 3), pas ce qu'on croit ;
  * `auto` == oracle CONFIG -- et cela coincide avec `BC.Units[].TertiaryAbility` du seed, lu du
    disque et non recopie ici ;
  * `refused` == VIDE       -- l'etat d'AVANT, sur la MEME capture. Sans ce bras, le premier serait
    un vert qu'un debranchement ne ferait pas rougir ;
  * `given` == `auto`       -- le canal EXPLICITE de #357 reste la reference : le defaut ne doit pas
    diverger de lui.

Deux gardes OFFLINE ferment le contrat du tri-etat lui-meme (aucun build : c'est du contrat, pas de
la mesure de bataille).

Montage : `probe_363_ability_states_channel.py`, via la fixture `ability_states_default_case`.
ASCII only.
"""
from __future__ import annotations

import pytest

import probe_363_ability_states_channel as ASD


# ── Face LIVE : les quatre porteurs du seed ──────────────────────────────────────────────────────

def test_les_quatre_porteurs_du_seed_arrivent_avec_leur_relique(ability_states_default_case):
    """LE DEFAUT : `load_state(dv, ob, snap)` -- rien de demande -- voit les QUATRE reliques.

    L'egalite porte sur le TRIPLET (ability, niveau, multiplicateur), pas sur la seule presence : un
    port qui inscrirait la bonne ability au mauvais palier serait tout aussi faux, et c'est
    exactement l'erreur que #357 avait mesuree (les passifs valent 50 sur tout runner normalise)."""
    r = ability_states_default_case()
    assert r["ambient_bound_by"] == "caller", (
        "le transport ambiant a ete lie par %r et non par le HARNAIS : ce test mesurerait alors le "
        "mecanisme, pas le branchement -- il resterait vert avec un conftest debranche"
        % (r["ambient_bound_by"],))
    assert r["auto"]["trace"]["source"] == "auto", (
        "le canal n'a pas emprunte la voie AUTO (trace : %s) -- le transport ambiant n'est pas lie "
        "par le harnais, donc une relique equipee serait INERTE dans toute la suite live"
        % (r["auto"]["trace"],))
    assert len(r["oracle_native"]) == 4, (
        "le montage n'a pas amene les 4 porteurs en bataille : le natif n'a monte que %s"
        % (r["oracle_native"],))
    assert r["auto"]["seen"] == r["oracle_native"], (
        "le port ne voit pas ce que le natif a monte.\n  port  : %s\n  natif : %s"
        % (r["auto"]["seen"], r["oracle_native"]))
    assert r["auto"]["trace"]["seeded"] == 4, (
        "`State.ability_states_seed.seeded` = %s, attendu 4"
        % (r["auto"]["trace"]["seeded"],))


def test_les_noms_lus_sont_ceux_que_le_seed_bc_declare(ability_states_default_case):
    """SECOND ORACLE, INDEPENDANT du live : `data/seed-bc.json`.

    Le bras precedent compare le port au payload `unitAbilityStates` ; les deux pourraient se
    tromper ensemble si le capteur lisait le mauvais champ. La CONFIG est une source distincte --
    elle ne passe ni par le meme code ni par le meme processus."""
    r = ability_states_default_case()
    attendu = {vis: r["oracle_config"][vis] for vis in r["auto"]["seen"]}
    lu = {vis: t[0] for vis, t in r["auto"]["seen"].items()}
    assert lu == attendu, (
        "les abilities lues ne sont pas celles que `BC.Units[].TertiaryAbility` declare.\n"
        "  lu      : %s\n  seed-bc : %s" % (lu, attendu))
    assert set(r["auto"]["seen"]) == set(ASD.SEED_RELIC_UNITS), (
        "le port ne voit pas exactement les 4 porteurs du seed : %s" % (sorted(r["auto"]["seen"]),))


def test_sans_le_canal_le_port_n_en_voit_aucune(ability_states_default_case):
    """CONTRE-EPREUVE -- l'etat d'AVANT #363, rejoue sur LA MEME capture.

    `ability_states=False` = refus explicite. Si ce bras voyait quoi que ce soit, c'est qu'une AUTRE
    voie (gameconfig, derivation) poserait la relique -- et le test nominal ne prouverait rien du
    canal."""
    r = ability_states_default_case()
    assert r["refused"]["trace"]["source"] == "refused", (
        "trace attendue `refused`, lue %s" % (r["refused"]["trace"],))
    assert r["refused"]["seen"] == {}, (
        "canal REFUSE : aucune relique ne doit etre vue, or le port en voit %s"
        % (r["refused"]["seen"],))
    assert r["refused"]["trace"]["seeded"] is None, (
        "`seeded` doit rester None quand le seed n'a pas tourne (lu %s) -- un 0 se lirait comme "
        "« mesure et vide »" % (r["refused"]["trace"]["seeded"],))


def test_le_defaut_ne_diverge_pas_du_canal_explicite(ability_states_default_case):
    """Le defaut #363 et le canal explicite #357 lisent la MEME chose.

    Ce n'est pas une tautologie : le bras `auto` refait le RPC lui-meme (et le sert d'un cache),
    tandis que `given` recoit le payload que le montage a capture. Deux chemins, un resultat."""
    r = ability_states_default_case()
    assert r["given"]["trace"]["source"] == "given"
    assert r["auto"]["seen"] == r["given"]["seen"], (
        "le canal AUTO et le canal EXPLICITE divergent.\n  auto  : %s\n  given : %s"
        % (r["auto"]["seen"], r["given"]["seen"]))


# ── Face OFFLINE : le contrat du tri-etat, sans build ────────────────────────────────────────────

def test_sans_transport_le_defaut_ne_pose_rien():
    """NON-REGRESSION des ~620 call-sites hors harnais live.

    Un `State` reconstruit d'une capture sur disque (aucun `bind_live_rpc`) doit se comporter
    EXACTEMENT comme avant #363 : le canal ne se declenche pas, et la trace le DIT (`no-transport`)
    au lieu de laisser croire qu'aucune relique n'est equipee."""
    from engine.runner import snapshot as S
    prev = S.unbind_live_rpc()
    try:
        payload, source = S._auto_ability_states(None, {"runner": "build#1"}, {}, {})
    finally:
        S.bind_live_rpc(prev)
    assert (payload, source) == (None, "no-transport")


def test_le_canal_ne_paie_qu_un_rpc_par_bataille():
    """CACHE PAR RUNNER -- et c'est une condition de DETERMINISME, pas une optimisation.

    Un probe rejoue couramment la MEME capture plusieurs fois. Si le canal repartait au live a
    chaque `load_state`, deux rejeux pourraient lire deux etats differents et le rejeu offline
    cesserait d'etre reproductible. On verifie donc les DEUX faces : un seul RPC pour N charges du
    meme runner, et un RPC de nouveau apres purge (un rid recycle ne doit pas heriter du precedent).
    """
    from engine.runner import snapshot as S
    appels = []

    def fake(method, body=None, timeout=60):
        appels.append((method, body))
        return {"ok": True, "runner": "build#4242", "units": []}

    prev = S.bind_live_rpc(fake)
    S.clear_ability_states_cache()
    try:
        for _ in range(3):
            payload, source = S._auto_ability_states(None, {"runner": "build#4242"}, {}, {})
            assert source == "auto" and payload is not None
        assert len(appels) == 1, "attendu 1 RPC pour 3 charges, mesure %d" % len(appels)
        S.clear_ability_states_cache("build#4242")
        S._auto_ability_states(None, {"runner": "build#4242"}, {}, {})
        assert len(appels) == 2, (
            "apres purge, le canal doit RE-capturer (sinon un rid recycle herite du runner "
            "precedent) ; RPC mesures : %d" % len(appels))
    finally:
        S.bind_live_rpc(prev)
        S.clear_ability_states_cache()


def test_une_panne_du_capteur_ne_se_lit_pas_comme_une_absence_de_relique():
    """« Un echec RENDU se lit comme une mesure » -- le piege que la trace ferme.

    Quand le capteur repond une ERREUR, le port ne seede rien : sans trace, cet etat serait
    INDISCERNABLE d'une bataille sans relique. La trace porte donc la raison, prefixee
    `unavailable:`."""
    from engine.runner import snapshot as S

    def broken(method, body=None, timeout=60):
        return {"ok": False, "error": "runner 9 introuvable"}

    prev = S.bind_live_rpc(broken)
    S.clear_ability_states_cache()
    try:
        payload, source = S._auto_ability_states(None, {"runner": "build#9"}, {}, {})
    finally:
        S.bind_live_rpc(prev)
        S.clear_ability_states_cache()
    assert payload is None
    assert source.startswith("unavailable:"), (
        "une panne du capteur doit etre TRACEE, source lue : %r" % (source,))
    assert "runner 9 introuvable" in source, (
        "la raison rendue par le capteur doit etre conservee, source lue : %r" % (source,))


def test_les_outils_de_batch_ne_chargent_aucun_etat():
    """CE QUI FONDE « cout NUL sur un batch », et qui doit le rester.

    L'arbitrage de #363 tient parce que `rl_collect_batch` et `engine_validate` ne construisent
    JAMAIS de `State` ECS : le canal ne les traverse pas, donc il ne leur coute rien. Le jour ou
    l'un des deux se mettrait a charger des etats, le calcul de cout serait a REFAIRE -- et cette
    garde est ce qui le dirait. Balayage AST (`probe_363 --volet scan`), pas un grep : `rl_duel.py`
    definit un homonyme `_load_state()` sans rapport."""
    r = ASD.run_scan()
    assert r["batch_tools_sans_load_state"] == ["rl_collect_batch.py", "engine_validate.py"], (
        "un outil de BATCH s'est mis a appeler `load_state` : le cout du branchement #363 n'est "
        "plus nul sur un batch, il faut le RE-MESURER (outils vus : %s)" % (r["outils"],))
    assert r["engine"] == {}, (
        "`engine/` appelle desormais `load_state` (%s) -- le canal deviendrait actif dans du code "
        "de moteur, ce que la mesure de cout de #363 n'a pas couvert" % (r["engine"],))
    assert r["tests"] > 0 and r["probes"] > 0, (
        "balayage vide : le volet `scan` ne mesure plus rien (tests=%s probes=%s)"
        % (r["tests"], r["probes"]))


@pytest.mark.parametrize("arg,attendu", [(False, "refused"), ({"units": []}, "given")])
def test_le_tri_etat_de_l_argument(arg, attendu):
    """`False` = REFUS, un payload = fourni. Le troisieme etat (`None` = AUTO) est couvert par les
    gardes ci-dessus. C'est ce tri-etat qui distingue « je ne veux pas du canal » de « je n'ai rien
    a passer » -- une distinction que l'ancien binaire `None`/payload ne savait pas exprimer."""
    from engine.runner import snapshot as S
    payload, source = S._auto_ability_states(arg, {"runner": "build#1"}, {}, {})
    assert source == attendu
    assert (payload is None) == (arg is False)
