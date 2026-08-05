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

def test_aucun_site_greffeur_sans_canal():
    """CLIQUET. Tout site `load_state` d'un fichier qui GREFFE doit alimenter le canal --
    `ability_states=<payload>`, transport ambiant lie, ou ambiant herite de `tests/conftest.py`."""
    m = P.measure(PYDIR)
    amputes = [r for r in m["rows"]
               if not r["couvert"] and r["regime"] not in ("refused", "indirect")]
    indet = [r for r in m["rows"] if r.get("indirect") and not r["couvert"]]
    assert m["suspects"], "aucun fichier SUSPECT : le recenseur ne visite plus rien"
    assert m["rows"], "aucun SITE mesure : le recensement serait vide, donc vert a tort"
    assert not amputes, "sites AMPUTES (greffe montee, canal muet) : %s" % (
        [(P.rel(r["file"]), r["line"]) for r in amputes],)
    assert not indet, "sites INDETERMINES (greffe ici, `load_state` ailleurs, aucun ambiant) : %s" % (
        [P.rel(r["file"]) for r in indet],)


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

def _payloads():
    """Le plus petit triplet que `load_state` accepte, avec un label de runner LISIBLE (sans lui le
    canal sortirait en `no-runner-label`, un autre regime)."""
    return ({"units": [], "runner": "build#99"}, {"counts": {"player": 3}, "units": []},
            {"units": []})


@pytest.fixture(autouse=True)
def _registre_propre():
    """Le registre est un etat de PROCESSUS : on le laisse comme on l'a trouve."""
    import catalog_inject as CI
    avant = CI.declared_grafts()
    CI.clear_declared_grafts()
    yield
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
    CI.declare_graft("passive", "tauCrisis", "Cleave")
    with pytest.raises(GraftedStateWithoutChannel) as e:
        load_state(dv, ob, snap)
    msg = str(e.value)
    assert "tauCrisis" in msg and "Cleave" in msg, "le refus doit NOMMER la greffe : %r" % msg
    assert "no-transport" in msg, "le refus doit NOMMER le regime muet : %r" % msg


def test_le_refus_EXPLICITE_reste_possible():
    """`ability_states=False` = la contre-epreuve assumee (`--mutate-nograft` et compagnie). Elle ne
    doit PAS lever : c'est l'echappatoire consciente, la seule."""
    import catalog_inject as CI
    from engine.runner.snapshot import load_state
    dv, ob, snap = _payloads()
    CI.declare_graft("relic", "tauCrisis", "AmuletOfTheVoidwyrm")
    st = load_state(dv, ob, snap, ability_states=False)
    assert st.ability_states_seed["source"] == "refused"


def test_sans_combatSnapshot_le_refus_ne_mord_pas():
    """`no-snapshot` n'est PAS une degradation a fermer : sans `combatSnapshot` il n'y a aucun
    `StatsComponent`, donc `collect_triggered_abilities` ne derive rien du gameconfig non plus. Le
    seed serait un no-op -- lever la serait un faux positif."""
    import catalog_inject as CI
    from engine.runner.snapshot import load_state
    dv, ob, _ = _payloads()
    CI.declare_graft("active", "necroWarden", "TunnelingHorror")
    st = load_state(dv, ob, None)
    assert st.ability_states_seed["source"] == "no-snapshot"


def test_le_canal_ALIMENTE_ne_leve_pas():
    """Le cas nominal : l'appelant fournit le payload -> `source == "given"`, aucun refus."""
    import catalog_inject as CI
    from engine.runner.snapshot import load_state
    dv, ob, snap = _payloads()
    CI.declare_graft("passive", "tauCrisis", "Cleave")
    st = load_state(dv, ob, snap, ability_states={"units": []})
    assert st.ability_states_seed["source"] == "given"


def test_le_transport_AMBIANT_suffit():
    """L'autre voie : transport lie -> `source == "auto"`, aucun refus. On substitue un transport
    factice (aucune session Frida n'est requise par ce fichier)."""
    import catalog_inject as CI
    import engine.runner.snapshot as S
    dv, ob, snap = _payloads()
    CI.declare_graft("passive", "tauCrisis", "Cleave")
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
    CI.declare_graft("passive", "tauCrisis", "Cleave")
    S.clear_ability_states_cache("build#99")
    prev = S.bind_live_rpc(lambda method, body=None, timeout=60: {"error": "runner dispose"})
    try:
        with pytest.raises(GraftedStateWithoutChannel) as e:
            S.load_state(dv, ob, snap)
        assert "unavailable" in str(e.value)
    finally:
        S.bind_live_rpc(prev)
        S.clear_ability_states_cache("build#99")
