"""#448-r3-r1-r1-r1 OFFLINE -- une greffe faite par un AUTRE PROCESSUS devient visible du refus.

LE TROU. `snapshot._refuse_if_grafted` (#448-r3-r1-r1) LEVE quand un montage a greffe et que le
canal `unitAbilityStates` est muet -- sans quoi `collect_triggered_abilities` retombe sur le
gameconfig, aucune classe greffee n'est montee, et toute assertion NEGATIVE passe A VIDE, EN VERT.
Mais son registre est un fait de PROCESSUS : dans le patron « `rl_duel build --graft` ecrit le seed
BC, un second processus le recoit par `--seed-bc` », le consommateur a un registre VIDE et le refus
ne mord pas -- exactement le regime ou le port serait ampute.

LE CHAINON, et pourquoi c'est le RUNNER. `load_state` ne recoit ni la BC ni le state-file, mais
elle connait toujours le runner (`runner_label` -> `build#<id>`, porte par tout payload de
capture). C'est le seul identifiant que les deux processus partagent. Le greffeur PUBLIE donc son
registre sous ce label (`catalog_inject.publish_runner_grafts`, appele par `rl_duel build`), et
`_declared_grafts` le RELIT (`_grafts_du_runner`).

Ce fichier garde le chainage ET ses trois no-op : pas de label, pas de fichier, registre illisible.
"""
from __future__ import annotations

#: Perimetre : les deux bouts du canal (publication cote montage, lecture cote moteur) et le site
#: qui les relie (`rl_duel build`).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/catalog_inject.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/rl_duel.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Offline : garde que les greffes publiees par le processus qui a CONSTRUIT le runner "
              "sont relues par `_declared_grafts` (#448-r3-r1-r1-r1), que la fusion des deux "
              "sources ne double pas, et que toute lecture impossible rend [] au lieu de faire "
              "echouer un chargement -- ce garde-fou ne doit jamais casser par lui-meme.",
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

LABEL = "build#990001"          # id volontairement hors de portee d'un runner reel


@pytest.fixture(autouse=True)
def _propre():
    """Registre de PROCESSUS et registre de DISQUE remis a neuf autour de chaque test."""
    C.clear_declared_grafts()
    C.clear_runner_grafts(LABEL)
    yield
    C.clear_declared_grafts()
    C.clear_runner_grafts(LABEL)


# --------------------------------------------------- 1. les deux bouts du canal se rejoignent
def test_le_chemin_de_registre_est_le_meme_des_deux_cotes():
    """La publication et la lecture doivent viser le MEME fichier.

    Elles sont ecrites dans DEUX modules qui ne s'importent pas (`engine/` ne depend pas de
    `catalog_inject`, c'est l'invariant du refus) : rien d'autre que ce test ne peut voir un
    glissement de convention de nommage.
    """
    C.declare_graft("relic", "unitX", "AbilityY")
    ecrit = C.publish_runner_grafts(LABEL)
    assert ecrit is not None and ecrit.exists()
    lu = S._grafts_du_runner(LABEL)
    assert lu == [{"kind": "relic", "unitId": "unitX", "what": "AbilityY"}], lu


def test_le_consommateur_voit_la_greffe_avec_un_registre_de_processus_VIDE():
    """LE regime du residu : le greffeur est un AUTRE processus."""
    C.declare_graft("graft", "orksNob", "SavageEchoes")
    C.publish_runner_grafts(LABEL)
    C.clear_declared_grafts()                       # <- on redevient le processus CONSOMMATEUR
    assert C.declared_grafts() == [], "premisse : le registre de processus doit etre vide"
    assert S._declared_grafts(LABEL) == [
        {"kind": "graft", "unitId": "orksNob", "what": "SavageEchoes"}]


def test_la_fusion_des_deux_sources_ne_double_pas():
    """Le greffeur qui charge lui-meme son etat est present des DEUX cotes."""
    C.declare_graft("relic", "unitX", "AbilityY")
    C.publish_runner_grafts(LABEL)
    assert S._declared_grafts(LABEL) == [{"kind": "relic", "unitId": "unitX", "what": "AbilityY"}]


def test_les_deux_sources_s_additionnent_quand_elles_different():
    C.declare_graft("relic", "unitA", "Ab1")
    C.publish_runner_grafts(LABEL, [{"kind": "graft", "unitId": "unitB", "what": "Ab2"}])
    lu = S._declared_grafts(LABEL)
    assert len(lu) == 2 and {g["unitId"] for g in lu} == {"unitA", "unitB"}


# ------------------------------------------------------------- 2. les NO-OP, un par cause
def test_sans_label_aucune_lecture():
    """`runner_label` rend `None` sur une capture fabriquee a la main : le canal ne se declenche pas."""
    C.publish_runner_grafts(LABEL, [{"kind": "graft", "unitId": "u", "what": "w"}])
    assert S._grafts_du_runner(None) == []
    assert S._declared_grafts(None) == []


def test_sans_fichier_aucune_greffe():
    assert S._grafts_du_runner(LABEL) == []


def test_registre_illisible_rend_une_liste_vide():
    """Un JSON corrompu ne doit PAS faire echouer un chargement : ce garde-fou ne casse jamais
    par lui-meme."""
    p = C.runner_graft_path(LABEL)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ ceci n'est pas du json", encoding="utf-8")
    assert S._grafts_du_runner(LABEL) == []


def test_registre_de_forme_inattendue_rend_une_liste_vide():
    p = C.runner_graft_path(LABEL)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pas": "une liste"}), encoding="utf-8")
    assert S._grafts_du_runner(LABEL) == []


def test_rien_a_publier_n_ecrit_aucun_fichier():
    """Un fichier VIDE se lirait « mesure, et aucune greffe » alors que rien n'a ete monte."""
    assert C.publish_runner_grafts(LABEL) is None
    assert not C.runner_graft_path(LABEL).exists()


def test_le_registre_meurt_avec_son_runner():
    """L'id de runner est RECYCLE par un build ulterieur : un registre survivant ferait refuser
    un etat qui n'a aucune greffe."""
    C.declare_graft("relic", "unitX", "AbilityY")
    C.publish_runner_grafts(LABEL)
    assert C.runner_graft_path(LABEL).exists()
    C.clear_runner_grafts(LABEL)
    assert not C.runner_graft_path(LABEL).exists()
    assert S._grafts_du_runner(LABEL) == []


# --------------------------------------- 3. le REFUS lui-meme voit la greffe d'un autre processus
def test_le_refus_leve_sur_une_greffe_publiee_par_un_autre_processus():
    """Bout en bout : `_refuse_if_grafted` doit LEVER dans le regime du residu."""
    C.publish_runner_grafts(LABEL, [{"kind": "graft", "unitId": "orksNob",
                                     "what": "SavageEchoes"}])
    C.clear_declared_grafts()
    decision = {"runner": LABEL, "units": [{"visualId": "orksNob:2"}, {"visualId": "ultraTitus"}]}
    with pytest.raises(S.GraftedStateWithoutChannel) as exc:
        S._refuse_if_grafted("no-transport", {"units": []}, decision)
    assert "orksNob" in str(exc.value)


def test_le_refus_se_TAIT_si_la_greffe_ne_concerne_aucune_unite_de_cet_etat():
    """La portee reste l'ETAT, pas le processus -- l'invariant de `_grafts_concerning` tient
    aussi pour la source DISQUE."""
    C.publish_runner_grafts(LABEL, [{"kind": "graft", "unitId": "unitAbsente",
                                     "what": "Quelque chose"}])
    C.clear_declared_grafts()
    decision = {"runner": LABEL, "units": [{"visualId": "ultraTitus"}]}
    S._refuse_if_grafted("no-transport", {"units": []}, decision)      # ne doit pas lever


def test_le_refus_se_TAIT_quand_le_canal_n_est_PAS_muet():
    """`source` hors des regimes muets par accident : aucune raison de refuser."""
    C.publish_runner_grafts(LABEL, [{"kind": "graft", "unitId": "orksNob", "what": "X"}])
    C.clear_declared_grafts()
    decision = {"runner": LABEL, "units": [{"visualId": "orksNob"}]}
    S._refuse_if_grafted("auto", {"units": []}, decision)              # ne doit pas lever
    S._refuse_if_grafted("refused", {"units": []}, decision)           # ni sur le refus EXPLICITE


# ------------------- 4. l'AUTRE porte : la marque portee par le SEED BC (sidecar `declaredGrafts`)
#
# Le registre par runner ne suffit PAS seul, et c'est la mesure qui l'a montre : dans le patron de
# la fiche, le processus qui CONSTRUIT le runner peut n'avoir rien greffe lui-meme -- il ne fait
# que charger un BC deja greffe par un autre. Rien ne serait alors publie.
def test_la_greffe_est_estampee_dans_le_sidecar_du_seed_bc(tmp_path):
    bc = tmp_path / "seed.json"
    bc.write_text(json.dumps({"Units": []}), encoding="utf-8")
    C.declare_graft("relic", "unitX", "AbilityY")
    assert C.stamp_grafts(bc) is not None
    assert C.read_grafts(bc) == [{"kind": "relic", "unitId": "unitX", "what": "AbilityY"}]


def test_un_autre_processus_re_declare_depuis_le_sidecar(tmp_path):
    bc = tmp_path / "seed.json"
    bc.write_text(json.dumps({"Units": []}), encoding="utf-8")
    C.declare_graft("relic", "unitX", "AbilityY")
    C.stamp_grafts(bc)
    C.clear_declared_grafts()                       # <- on redevient le processus CONSOMMATEUR
    assert C.redeclare_grafts_from(bc) == 1
    assert C.declared_grafts() == [{"kind": "relic", "unitId": "unitX", "what": "AbilityY"}]


def test_la_re_declaration_est_idempotente(tmp_path):
    """Greffer PUIS recharger son propre fichier ne doit pas gonfler le registre."""
    bc = tmp_path / "seed.json"
    bc.write_text(json.dumps({"Units": []}), encoding="utf-8")
    C.declare_graft("relic", "unitX", "AbilityY")
    C.stamp_grafts(bc)
    assert C.redeclare_grafts_from(bc) == 0
    assert len(C.declared_grafts()) == 1


def test_rien_a_estamper_n_ecrit_aucun_sidecar(tmp_path):
    bc = tmp_path / "seed.json"
    bc.write_text(json.dumps({"Units": []}), encoding="utf-8")
    assert C.stamp_grafts(bc) is None
    assert not C.pins_path(bc).exists()


def test_estamper_PRESERVE_epingles_et_retenues(tmp_path):
    """Le sidecar porte TROIS mecanismes ; en ecraser un depuis l'autre ferait disparaitre un
    montage en silence -- la panne meme que #375 et #380 existent pour empecher."""
    bc = tmp_path / "seed.json"
    bc.write_text(json.dumps({"Units": []}), encoding="utf-8")
    C.write_pins(bc, ["ActiveAbilities/Foo"], withheld=["PassiveAbilities/Bar"])
    C.declare_graft("relic", "unitX", "AbilityY")
    C.stamp_grafts(bc)
    assert C.read_pins(bc) == ["ActiveAbilities/Foo"]
    assert C.read_withheld(bc) == ["PassiveAbilities/Bar"]
    assert C.read_grafts(bc) == [{"kind": "relic", "unitId": "unitX", "what": "AbilityY"}]


def test_write_pins_PRESERVE_les_greffes_deja_estampees(tmp_path):
    """Le sens INVERSE du test precedent : `write_pins` est un autre ecrivain du meme fichier."""
    bc = tmp_path / "seed.json"
    bc.write_text(json.dumps({"Units": []}), encoding="utf-8")
    C.declare_graft("relic", "unitX", "AbilityY")
    C.stamp_grafts(bc)
    C.write_pins(bc, ["ActiveAbilities/Foo"])
    assert C.read_grafts(bc) == [{"kind": "relic", "unitId": "unitX", "what": "AbilityY"}]
    assert C.read_pins(bc) == ["ActiveAbilities/Foo"]


def test_sidecar_sans_greffes_ne_fabrique_aucun_verdict(tmp_path):
    """Les sidecars ecrits AVANT ce mecanisme ne portent que pins/withheld."""
    bc = tmp_path / "seed.json"
    bc.write_text(json.dumps({"Units": []}), encoding="utf-8")
    C.write_pins(bc, ["ActiveAbilities/Foo"])
    assert C.read_grafts(bc) == []
    assert C.redeclare_grafts_from(bc) == 0
