"""#448-r3-r1-r1 -- CLIQUET : un montage qui GREFFE doit ALIMENTER le canal `unitAbilityStates`.

POURQUOI UN CLIQUET ET PAS UN SEUIL. Ce gisement est de ceux que NOTRE PROPRE CADENCE rouvre :
chaque probe greffeur neuf le rouvre s'il oublie le canal. Un `count <= N` cesserait de mordre des
qu'un contributeur ne remonte pas N ; l'invariant est `AMPUTES == 0 and INDETERMINES == 0`.

CE QUE LA DEGRADATION COUTE, MESURE (#448-r3-r1) : `probe_448_r2b_stormboyz_teleporting_in.py`
rendait 0 echec en CLI contre 3 sous pytest -- MEME code, MEME seed, MEME board. Sans canal,
`triggers/dispatch/core.py::collect_triggered_abilities` retombe sur `gameconfig.unit(<greffon>)`,
aucune classe greffee n'est montee, et toute assertion NEGATIVE passe A VIDE, EN VERT.

TROIS ETAGES, et ils gardent des choses DIFFERENTES :
  1. le RECENSEMENT est a zero (statique, tout le corpus `scripts/python`) ;
  2. le RECENSEUR SAIT ECHOUER (contre-epreuve synthetique -- un zero d'instrument aveugle ne
     vaut rien, cf. `probe_181` qui rendait `0` inconditionnellement) ;
  3. le CHOKE POINT REFUSE (`snapshot._refuse_if_grafted`) -- l'etage EXECUTABLE, celui qui tient
     quand le balayage statique ne voit pas (greffe faite par un autre chemin dans le processus).

100 % OFFLINE : aucun runner, aucune session Frida.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_448_r3_r1_r1_greffe_sans_canal as P                      # noqa: E402


# ─────────────────────────────────────────── etage 1 : le recensement est a zero

@pytest.fixture(scope="module")
def mesure_corpus():
    """UNE seule mesure pour tout le fichier. Elle indexe 2287 fichiers (`ast.parse` de tout
    `scripts/python`) : la payer par test ferait de chaque garde ajoutee un cout de ~90 s."""
    return P.measure(PYDIR)


def test_aucun_site_greffeur_sans_canal(mesure_corpus):
    """CLIQUET. Tout site `load_state` d'un fichier qui GREFFE doit alimenter le canal --
    `ability_states=<payload>`, transport ambiant lie, ou ambiant herite de `tests/conftest.py`."""
    m = mesure_corpus
    amputes = [r for r in m["rows"]
               if not r["couvert"] and r["regime"] not in ("refused", "indirect")]
    indet = [r for r in m["rows"] if r.get("indirect") and not r["couvert"]]
    assert m["suspects"], "aucun fichier SUSPECT : le recenseur ne visite plus rien"
    assert m["rows"], "aucun SITE mesure : le recensement serait vide, donc vert a tort"
    assert not amputes, "sites AMPUTES (greffe montee, canal muet) : %s" % (
        [(P.rel(r["file"]), r["line"]) for r in amputes],)
    assert not indet, "sites INDETERMINES (greffe ici, `load_state` ailleurs, aucun ambiant) : %s" % (
        [P.rel(r["file"]) for r in indet],)


def test_le_jeu_de_lieurs_reste_un_ensemble_de_CHEMINS(mesure_corpus):
    """#448-r5 -- GARDE STRUCTURELLE contre le retour de l'aplatissement.

    La fermeture arriere des appelants du foyer de liaison porte sur des noeuds `(module, fn)`.
    La version #448-r3-r1-r1 la reduisait a ses seuls NOMS TERMINAUX avant de s'en servir --
    `main`, `run`, `mesure` en font partie --, si bien que **37 SUSPECTS sur 37** etaient declares
    « lient l'ambiant » (1526 fichiers sur 2287 a l'echelle du corpus). Garder le TYPE du jeu est
    ce qui empeche la reecriture de revenir : un ensemble de `str` ne peut pas contenir un `Path`.

    NB -- la degradation serait desormais dans le sens SUR ; `path in {<noms>}` est toujours faux,
    donc un retour aux noms nus rendrait le probe ROUGE, pas silencieux."""
    m = mesure_corpus
    lieurs = m["lieurs_qualifies"]
    assert lieurs, "aucun fichier lieur : la fermeture du foyer ne visite plus rien"
    assert all(isinstance(p, Path) for p in lieurs), (
        "le jeu de lieurs doit etre des CHEMINS, pas des noms : %r" % (lieurs[:5],))
    assert all(p.exists() for p in lieurs), "des lieurs hors corpus : %r" % (lieurs[:5],)
    # La fermeture QUALIFIEE compte plus de noeuds que de fichiers -- si l'inverse arrivait, c'est
    # qu'on aurait recommence a compter autre chose que des `(module, fn)`.
    assert m["n_reach_bind"] >= len(lieurs), (
        "%d noeuds pour %d fichiers lieurs" % (m["n_reach_bind"], len(lieurs)))


def test_un_HOMONYME_ne_fait_pas_un_lieur():
    """#448-r5 -- LE TEMOIN, et il MORD.

    Couple synthetique : `mutant_vrai_lieur.mesure` lie l'ambiant (donc le nom `mesure` entre dans
    la fermeture), `mutant_faux_lieur.mesure` porte le MEME NOM et ne lie rien -- il greffe puis
    charge a canal muet. Le test assertionne les DEUX cotes : que le critere APLATI de `master`
    blanchissait ce fichier, et que le critere QUALIFIE l'accuse. Sans le premier volet, le temoin
    ne prouverait pas que le gisement existait ; sans le second, qu'il est ferme."""
    import ast
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "mutant_vrai_lieur.py").write_text(P.MUTANT_VRAI_LIEUR, encoding="utf-8")
        (base / "mutant_faux_lieur.py").write_text(P.MUTANT_FAUX_LIEUR, encoding="utf-8")
        idx = P.index(P.corpus(base), base)
        reach_bind = P.reaching(idx["graph"],
                                {("engine.runner.snapshot", b) for b in P.BINDERS})
        lieurs = {p for p, m in idx["mods"].items()
                  if any((m, fn) in reach_bind for fn in idx["per_file"].get(p, {}))}
        vrai, faux = base / "mutant_vrai_lieur.py", base / "mutant_faux_lieur.py"

        # (1) le critere APLATI -- reproduit ici a l'identique -- blanchissait le faux lieur.
        noms_nus = {n for _m, n in reach_bind}
        assert "mesure" in noms_nus, (
            "le montage du temoin ne reproduit plus la faute : `mesure` doit entrer dans la "
            "fermeture par le VRAI lieur (noms=%r)" % (sorted(noms_nus),))
        arbre = ast.parse(faux.read_text(encoding="utf-8"))
        assert noms_nus & (P.called_names(arbre) | P.referenced_names(arbre)), (
            "le critere APLATI ne blanchit plus le faux lieur : le temoin ne mord plus")

        # (2) le critere QUALIFIE l'accuse, et reconnait toujours le vrai lieur.
        assert vrai in lieurs, "le VRAI lieur n'est plus reconnu : le critere est devenu aveugle"
        assert faux not in lieurs, "un HOMONYME redevient lieur : l'aplatissement est de retour"
        assert not P.binds_ambient(faux, lieurs), (
            "`binds_ambient` blanchit un fichier qui ne nomme ni n'atteint le foyer")
        assert P.binds_ambient(vrai, lieurs)


def test_les_primitives_divergentes_sont_derivees_et_non_vides():
    """Le perimetre vient d'un DATA-FLOW sur `catalog_inject`, pas d'une liste de noms. S'il devient
    vide, l'etage 1 rendrait zero sans rien visiter -- et le cliquet au-dessus serait tautologique."""
    prims, indet = P.derive_primitives(P.CATALOG)
    divergentes = {k for k, v in prims.items() if str(v).startswith("divergente")}
    assert not indet, "catalog_inject INDETERMINE : %s" % (indet,)
    # Les trois ECRITURES du montage doivent y etre -- elles sont le coeur du gisement.
    for attendu in ("graft_passive_ability", "graft_active_ability", "equip_relic",
                    "write_grafted_seed_bc"):
        assert attendu in divergentes, (
            "`%s` n'est plus derivee comme primitive DIVERGENTE (prims=%r)" % (attendu, prims))
    # Et la TRANSCRIPTION doit rester distincte : `augment` recopie le gameconfig, le port qui en
    # derive tombe juste -- la compter greffeuse ferait rougir des dizaines de montages sains.
    assert prims.get("write_augmented_seed_bc") == "divergente-si:restrict_abilities", (
        "`write_augmented_seed_bc` doit etre CONDITIONNELLE (divergente seulement avec "
        "`restrict_abilities`) ; obtenu %r" % (prims.get("write_augmented_seed_bc"),))


# ────────────────────────────────── etage 2 : le recenseur sait ECHOUER

def test_le_recenseur_discrimine():
    """CONTRE-EPREUVE. Un zero ne vaut que si l'instrument sait rendre autre chose : quatre fichiers
    synthetiques (ampute / couvert / vice reparti sur deux modules / appelant indirect)."""
    assert P.mutate() == 0, "le recenseur ne discrimine plus ses propres mutants"


# ──────────────────────── etage 3 : le CHOKE POINT refuse au lieu de se degrader

GREFFON = "tauCrisis"


def _payloads(avec_greffon: bool = True, visual_id_nul: bool = False):
    """Le plus petit triplet que `load_state` accepte, avec un label de runner LISIBLE.

    `avec_greffon` : l'etat porte-t-il l'unite sur laquelle les tests greffent ? C'est ce qui
    decide si le refus doit mordre (cf. `snapshot._grafts_concerning`)."""
    if visual_id_nul:
        units = [{"id": 1, "visualId": None, "alive": True}]
    elif avec_greffon:
        units = [{"id": 1, "visualId": GREFFON, "alive": True}]
    else:
        units = [{"id": 1, "visualId": "necroWarden", "alive": True}]
    return ({"units": units, "runner": "build#99"}, {"counts": {"player": 3}, "units": []},
            {"units": []})


@pytest.fixture(autouse=True)
def _regime_maitrise():
    """LE TEST CONTROLE SON REGIME -- registre de greffes ET transport ambiant.

    ⚠ CE QUI L'IMPOSE, MESURE LE 2026-08-05. Deux tests de ce fichier assertionnaient
    `source == "no-transport"` sans delier le transport. Joues SEULS : verts. Joues APRES un
    fichier live (`tests/conftest.py::live_session` lie l'ambiant, etat GLOBAL de processus) :
    **2 failed** -- `_auto_ability_states` ne s'arretait plus a `no-transport` mais allait jusqu'a
    `unavailable:runner 99 not found`. Un vert qui depend de l'ISOLEMENT ne tient pas en compagnie,
    et c'est exactement la famille de faute que cette tranche ferme.

    Corollaire : delier rend le regime `no-transport` INDEPENDANT de la session Frida (numero,
    bundle, runners vivants). Aucun test de ce fichier ne touche le reseau.

    Le registre est lui aussi un etat de PROCESSUS -- on le laisse comme on l'a trouve."""
    import catalog_inject as CI
    import engine.runner.snapshot as S
    avant = CI.declared_grafts()
    CI.clear_declared_grafts()
    prev_rpc = S.unbind_live_rpc()
    S.clear_ability_states_cache("build#99")
    try:
        yield
    finally:
        S.clear_ability_states_cache("build#99")
        S.bind_live_rpc(prev_rpc)
        CI.clear_declared_grafts()
        for g in avant:
            CI.declare_graft(g["kind"], g["unitId"], g["what"])


def test_sans_greffe_le_canal_muet_ne_leve_pas():
    """NON-REGRESSION : un rejeu de capture hors harnais live reste legitime. Le refus ne doit
    mordre QUE sur un processus qui a greffe."""
    from engine.runner.snapshot import load_state
    dv, ob, snap = _payloads()
    st = load_state(dv, ob, snap)
    assert st.ability_states_seed["source"] == "no-transport"


def test_avec_greffe_le_canal_muet_LEVE():
    """LE CRAN. Sans lui la degradation est PERMISSIVE : le port est ampute et les assertions
    negatives passent a vide."""
    import catalog_inject as CI
    from engine.runner.snapshot import load_state, GraftedStateWithoutChannel
    dv, ob, snap = _payloads()
    CI.declare_graft("passive", GREFFON, "Cleave")
    with pytest.raises(GraftedStateWithoutChannel) as e:
        load_state(dv, ob, snap)
    msg = str(e.value)
    assert GREFFON in msg and "Cleave" in msg, "le refus doit NOMMER la greffe : %r" % msg
    assert "no-transport" in msg, "le refus doit NOMMER le regime muet : %r" % msg


def test_une_greffe_qui_ne_concerne_PAS_cet_etat_ne_leve_pas():
    """LA PORTEE DU REFUS -- l'ETAT, pas le PROCESSUS.

    MESURE QUI L'IMPOSE (2026-08-05) : une passe pytest sur `test_366_r1_stormboyz_strike_live.py`
    laisse **3 greffes** au registre, et un `load_state` a canal muet dans le meme processus levait
    ensuite -- sur un etat qui n'a aucun rapport. Le porteur greffe n'est pas dans cet etat-ci :
    rien a amputer, donc rien a refuser."""
    import catalog_inject as CI
    from engine.runner.snapshot import load_state
    dv, ob, snap = _payloads(avec_greffon=False)
    CI.declare_graft("passive", GREFFON, "Cleave")
    st = load_state(dv, ob, snap)
    assert st.ability_states_seed["source"] == "no-transport"


def test_un_visualId_NUL_rend_le_refus_CONSERVATEUR():
    """TROISIEME ETAT. Une unite SANS TUILE arrive dans `decisionView` avec `visualId = null`
    (mesure #366-r1) : on ne peut NI confirmer NI exclure qu'elle porte la greffe. On leve, et le
    message DIT que c'est indecidable -- jamais un silence."""
    import catalog_inject as CI
    from engine.runner.snapshot import load_state, GraftedStateWithoutChannel
    dv, ob, snap = _payloads(visual_id_nul=True)
    CI.declare_graft("passive", GREFFON, "Cleave")
    with pytest.raises(GraftedStateWithoutChannel) as e:
        load_state(dv, ob, snap)
    assert "indecidable" in str(e.value), "le refus conservateur doit se NOMMER : %r" % str(e.value)


def test_le_suffixe_d_instance_ne_masque_pas_le_porteur():
    """`BC.Units[].Id` porte un suffixe d'instance (`orksNob:2`) que `visualId` n'a pas. Le
    rapprochement retire le suffixe DES DEUX COTES -- sinon le refus serait muet sur tout montage
    multi-instances, c.-a-d. exactement ceux qui greffent plusieurs copies du greffon."""
    import catalog_inject as CI
    from engine.runner.snapshot import load_state, GraftedStateWithoutChannel
    dv, ob, snap = _payloads()
    CI.declare_graft("passive", "%s:2" % GREFFON, "Cleave")
    with pytest.raises(GraftedStateWithoutChannel):
        load_state(dv, ob, snap)


def test_le_refus_EXPLICITE_reste_possible():
    """`ability_states=False` = la contre-epreuve assumee (`--mutate-nograft` et compagnie). Elle ne
    doit PAS lever : c'est l'echappatoire consciente, la seule."""
    import catalog_inject as CI
    from engine.runner.snapshot import load_state
    dv, ob, snap = _payloads()
    CI.declare_graft("relic", GREFFON, "AmuletOfTheVoidwyrm")
    st = load_state(dv, ob, snap, ability_states=False)
    assert st.ability_states_seed["source"] == "refused"


def test_sans_combatSnapshot_le_refus_ne_mord_pas():
    """`no-snapshot` n'est PAS une degradation a fermer : sans `combatSnapshot` il n'y a aucun
    `StatsComponent`, donc `collect_triggered_abilities` ne derive rien du gameconfig non plus. Le
    seed serait un no-op -- lever la serait un faux positif."""
    import catalog_inject as CI
    from engine.runner.snapshot import load_state
    dv, ob, _ = _payloads()
    CI.declare_graft("active", GREFFON, "TunnelingHorror")   # le GREFFON est dans cet etat
    st = load_state(dv, ob, None)
    assert st.ability_states_seed["source"] == "no-snapshot"


def test_le_canal_ALIMENTE_ne_leve_pas():
    """Le cas nominal : l'appelant fournit le payload -> `source == "given"`, aucun refus."""
    import catalog_inject as CI
    from engine.runner.snapshot import load_state
    dv, ob, snap = _payloads()
    CI.declare_graft("passive", GREFFON, "Cleave")
    st = load_state(dv, ob, snap, ability_states={"units": []})
    assert st.ability_states_seed["source"] == "given"


def test_le_transport_AMBIANT_suffit():
    """L'autre voie : transport lie -> `source == "auto"`, aucun refus. On substitue un transport
    factice (aucune session Frida n'est requise par ce fichier)."""
    import catalog_inject as CI
    import engine.runner.snapshot as S
    dv, ob, snap = _payloads()
    CI.declare_graft("passive", GREFFON, "Cleave")
    S.clear_ability_states_cache("build#99")
    prev = S.bind_live_rpc(lambda method, body=None, timeout=60: {"units": []})
    try:
        st = S.load_state(dv, ob, snap)
        assert st.ability_states_seed["source"] == "auto"
    finally:
        S.bind_live_rpc(prev)
        S.clear_ability_states_cache("build#99")


def test_le_capteur_EN_PANNE_leve_aussi():
    """`unavailable:<msg>` -- transport lie mais le capteur RENVOIE une erreur. Le port serait
    ampute exactement comme sans transport : un zero d'ici doit se lire comme une PANNE."""
    import catalog_inject as CI
    import engine.runner.snapshot as S
    from engine.runner.snapshot import GraftedStateWithoutChannel
    dv, ob, snap = _payloads()
    CI.declare_graft("passive", GREFFON, "Cleave")
    S.clear_ability_states_cache("build#99")
    prev = S.bind_live_rpc(lambda method, body=None, timeout=60: {"error": "runner dispose"})
    try:
        with pytest.raises(GraftedStateWithoutChannel) as e:
            S.load_state(dv, ob, snap)
        assert "unavailable" in str(e.value)
    finally:
        S.bind_live_rpc(prev)
        S.clear_ability_states_cache("build#99")
