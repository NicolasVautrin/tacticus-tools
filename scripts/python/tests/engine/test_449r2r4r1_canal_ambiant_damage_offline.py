"""#449-r2-r4-r1 OFFLINE -- la section `BC.Damage` de CETTE bataille atteint `load_state`.

LE TROU. `load_state(damage_config=...)` existait mais n'etait alimente par AUCUN appelant reel
(mesure : seuls `probe_449r2r4_spread_from_bc.py` et `probe_449r2r4r4_bc_damage_fields.py` le
passent). Tous les runners retombaient donc sur le defaut DERIVE de `data/seed-bc.json` -- exact
tant qu'ils partent de cette seed, et FAUX des qu'un montage passe `--seed-bc` avec une section
`Damage` modifiee. Muet, en prime : le port lisait la variance d'une AUTRE BC que celle qui court.

LE CHAINON. `load_state` ne recoit ni la BC ni le state-file, mais elle connait le RUNNER
(`runner_label`). Le montage, qui tient la BC, depose donc la section sous ce label
(`catalog_inject.publish_runner_bc_sections`, appele par `rl_duel build`), et `load_state` la lit
quand l'appelant n'a rien fourni. C'est le meme patron que le registre de greffes
(#448-r3-r1-r1-r1), et c'est ce qui fait TOMBER le blocage `seeding` de la fiche : le canal ne
manquait pas au substrat, il manquait entre deux processus du harnais.

⚠ TRI-ETAT STRICT, et c'est tout l'interet : `None` = pas mesure -> defaut derive de la seed ;
un dict VIDE reste un dict -- la BC a parle et elle dit zero. Fabriquer le second a partir du
premier est exactement le vice que ce canal ferme.
"""
from __future__ import annotations

#: Perimetre : les deux bouts du canal et le site qui les relie.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/catalog_inject.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/services/damage_config.py",
        "scripts/python/rl_duel.py",
        "data/seed-bc.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Offline : garde que la section BC.Damage publiee par le build atteint load_state "
              "(#449-r2-r4-r1), que l'argument EXPLICITE prime toujours sur le canal, et que "
              "toute lecture impossible retombe sur le defaut DERIVE de la seed au lieu de "
              "fabriquer une section.",
}

import json          # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)
import sys           # noqa: E402
from pathlib import Path                                                      # noqa: E402

import pytest        # noqa: E402

_SP = Path(__file__).resolve().parents[2]
if str(_SP) not in sys.path:
    sys.path.insert(0, str(_SP))

import catalog_inject as C                                                    # noqa: E402
from engine.runner import snapshot as S                                       # noqa: E402
from engine.services import damage_config as DC                               # noqa: E402

LABEL = "build#990002"          # id volontairement hors de portee d'un runner reel


@pytest.fixture(autouse=True)
def _propre():
    C.clear_runner_bc_sections(LABEL)
    yield
    C.clear_runner_bc_sections(LABEL)


# ------------------------------------------------ 1. la PREMISSE : le defaut n'est pas la BC
def test_le_defaut_derive_de_la_seed_et_diffe_de_notre_temoin():
    """Sans cet ecart, tous les etages suivants seraient d'accord PAR HASARD."""
    defaut = DC.default_damage_spread_percentage()
    assert isinstance(defaut, int)
    assert defaut != 7, ("la seed versionnee vaut maintenant 7 : choisir un autre temoin, sinon "
                         "l'accord ne prouve plus rien")


# ---------------------------------------------------- 2. les deux bouts du canal se rejoignent
def test_le_chemin_est_le_meme_des_deux_cotes():
    """Publication et lecture vivent dans deux modules qui ne s'importent pas (`engine/` ne depend
    pas de `catalog_inject`) : rien d'autre que ce test ne verrait un glissement de convention."""
    assert C.publish_runner_bc_sections(LABEL, {"Damage": {"DamageSpreadPercentage": 7}})
    assert S._section_bc_du_runner(LABEL, "Damage") == {"DamageSpreadPercentage": 7}


def test_load_state_lit_la_section_publiee(_dec_obs_snap):
    dec, obs, snap = _dec_obs_snap
    C.publish_runner_bc_sections(LABEL, {"Damage": {"DamageSpreadPercentage": 7}})
    st = S.load_state(dec, obs, snap, ability_states=False)
    assert st.damage_spread_percentage == 7
    assert DC.resolve_spread_pct(state=st) == 7


def test_sans_publication_le_defaut_derive_de_la_seed_s_applique(_dec_obs_snap):
    """Le comportement d'AVANT, strictement conserve hors du regime du canal."""
    dec, obs, snap = _dec_obs_snap
    st = S.load_state(dec, obs, snap, ability_states=False)
    assert DC.resolve_spread_pct(state=st) == DC.default_damage_spread_percentage()


def test_l_argument_explicite_PRIME_sur_le_canal(_dec_obs_snap):
    """Un appelant qui passe sa section a lu son propre decompile : le canal ne s'y substitue pas."""
    dec, obs, snap = _dec_obs_snap
    C.publish_runner_bc_sections(LABEL, {"Damage": {"DamageSpreadPercentage": 7}})
    st = S.load_state(dec, obs, snap, ability_states=False,
                      damage_config={"DamageSpreadPercentage": 3})
    assert st.damage_spread_percentage == 3


# ------------------------------------------------------------- 3. les NO-OP, un par cause
def test_sans_label_aucune_lecture():
    C.publish_runner_bc_sections(LABEL, {"Damage": {"DamageSpreadPercentage": 7}})
    assert S._section_bc_du_runner(None, "Damage") is None


def test_section_absente_rend_None():
    C.publish_runner_bc_sections(LABEL, {"Damage": {"DamageSpreadPercentage": 7}})
    assert S._section_bc_du_runner(LABEL, "Targeting") is None


def test_fichier_illisible_rend_None():
    p = C.runner_bc_sections_path(LABEL)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ pas du json", encoding="utf-8")
    assert S._section_bc_du_runner(LABEL, "Damage") is None


def test_bc_sans_section_n_ecrit_aucun_fichier():
    """Ecrire `{}` ferait passer « pas mesure » pour « la BC dit zero »."""
    assert C.publish_runner_bc_sections(LABEL, {"Units": []}) is None
    assert not C.runner_bc_sections_path(LABEL).exists()


def test_une_section_VIDE_reste_un_dict(_dec_obs_snap):
    """La BC a parle et elle dit zero -- distinct de « pas de canal », que le natif traite en
    levant (`DamageCalculations$$get_DamageSpreadPercentageFix64` sur `configuration == null`)."""
    dec, obs, snap = _dec_obs_snap
    C.publish_runner_bc_sections(LABEL, {"Damage": {}})
    assert S._section_bc_du_runner(LABEL, "Damage") == {}
    st = S.load_state(dec, obs, snap, ability_states=False)
    assert st.damage_spread_percentage == 0, (
        "une section presente mais vide doit valoir 0, comme le DTO C# sans initialiseur")


def test_les_sections_publiees_sont_celles_qui_sont_LUES():
    """Publier une section que personne ne lit fabriquerait du code mort a l'air de canal."""
    assert C.BC_SECTIONS_PUBLIEES == ("Damage",)


def test_le_depot_meurt_avec_son_runner():
    C.publish_runner_bc_sections(LABEL, {"Damage": {"DamageSpreadPercentage": 7}})
    assert C.runner_bc_sections_path(LABEL).exists()
    C.clear_runner_bc_sections(LABEL)
    assert S._section_bc_du_runner(LABEL, "Damage") is None


# ------------------------------------------------------------------------ payloads minimaux
@pytest.fixture
def _dec_obs_snap():
    """Le plus petit triplet que `load_state` accepte, porteur du label -- c'est le label qui est
    le sujet du test, pas la bataille."""
    dec = {"runner": LABEL, "units": []}
    obs = {"runner": LABEL, "units": [], "counts": {}}
    snap = {"runner": LABEL, "units": []}
    return dec, obs, snap
