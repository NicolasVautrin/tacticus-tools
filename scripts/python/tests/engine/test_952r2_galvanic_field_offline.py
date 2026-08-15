"""#952-r2 -- le filet de spawn de `GalvanicField` (passif d'`admecManipulus` << Actus >>).

CE QUE CETTE TRANCHE A REFUTE, par MESURE :

  * la fiche annoncait `BLOCAGE: porteur`. `admecManipulus` est **DANS**
    `rl_duel build --list-pool` (rank 17) et se monte en une commande -- confronte live par
    `probe_a899_952r2_galvanic_field.py` (runner 57, board MC1_67, seed 777) ;
  * elle affirmait que `_seed_ability_owner_effects` n'a que DEUX call-sites (spawn de summon,
    atterrissage deep-strike). Il en a **TROIS** : `runner/snapshot.py` l'appelle sur CHAQUE entite
    chargee -- c'est la voie CAPTURE, et elle arrose donc un HERO deja sur le plateau.

CE QUE LA MESURE LIVE A CONFIRME (build `t6dpr4k06g`), avec son TEMOIN :

    admecManipulus  unitFlags=[24]  abilityStates=[(1117 DefendTheDivineWork, active),
                                                   (1119 Repair_GalvanicField, granted)]
    tauCrisis       unitFlags=[]                      <- TEMOIN : le flag n'est PAS universel

`28 Repair` est ABSENTE du porteur et `1119` presente : les trois feuilles du `CreateBehaviour`
natif (`AddFlag(0x18)`, `RemoveActiveAbility(0x1c)`, `AddActiveAbility(0x45f)`) sont confirmees.

CE QUE CE FICHIER GARDE -- le REGIME SEPARANT, et lui seul. Sur le chemin live, l'entree neuve est
un NO-OP EXACT (le capteur publie deja le flag, et le poseur est idempotent) : un test qui se
contenterait de charger un etat capte serait un ACCORD EN REGIME DEGENERE, donc zero preuve. On
construit donc l'etat que le capteur n'a PAS renseigne -- exactement le cas d'un spawn offline pur
-- et on verifie que le seed pose le flag LA, et seulement pour le porteur du passif.

VOLET NON COUVERT, et il reste ouvert : les deux ECHANGES D'ABILITY (`RemoveActiveAbility` /
`AddActiveAbility`) n'ont AUCUN canal d'init cote port. `ABILITY_INIT_OWNER_FLAGS` est un canal de
FLAGS ; ce filet ne porte donc qu'UNE des trois feuilles.
"""
from __future__ import annotations

import inspect

import pytest

from engine.entities.unit_context import UnitContext
from engine.entities.unit_flag import UnitFlag
from engine.runner.components import (HealthComponent, OwnerComponent, StatsComponent,
                                      UnitComponent, UnitFlagsComponent)
from engine.runner.operations.spawn import _seed_ability_owner_effects
from engine.runner.state import State

CARRIER = "admecManipulus"     # porte `GalvanicField` en `passiveAbilities`
WITNESS = "tauCrisis"          # ne le porte pas -> TEMOIN
_FLAG = int(UnitFlag.CanRepairFullHealthUnits)


def _unit(state, vis, team=1, passive_level=50):
    """Une entite MINIMALE, volontairement SANS `UnitFlagsComponent` : c'est le regime << etat
    construit sans capture de flags >>, le seul ou le filet est separant."""
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=vis, alive=True))
    e.add_component(OwnerComponent(team=team))
    ctx = UnitContext(entity_id=e.id, visual_id=vis)
    ctx.traits = []
    ctx.passive_ability_level = passive_level
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=9000, hp_max=9000))
    return e.id


def _flags(state, uid):
    c = state.get_entity(uid).get_component(UnitFlagsComponent)
    return set() if c is None else {int(f) for f in c.flags}


# ------------------------------------------------------------------- [1] le registre et sa forme
def test_1_entree_inscrite_avec_le_bon_flag():
    from engine.entities.effects.factory import (ABILITY_INIT_OWNER_FLAGS,
                                                 get_owner_flags_added_on_ability_init)
    assert ABILITY_INIT_OWNER_FLAGS["GalvanicField"] == [_FLAG]
    assert get_owner_flags_added_on_ability_init("GalvanicField") == [_FLAG]
    # MEME flag que son jumeau deja porte -- donc MEME lecteur, donc entree non inerte.
    assert ABILITY_INIT_OWNER_FLAGS["EcogSupport"] == [_FLAG]
    assert get_owner_flags_added_on_ability_init(WITNESS) == []


def test_2_le_lecteur_du_flag_EXISTE_et_MORD():
    """Une entree ici n'a de valeur QUE si le flag a un lecteur porte -- sinon c'est le
    << mensonge de couverture >> : l'audit passe de GAP a PORTE sans qu'aucun comportement ne
    change. On lit le SOURCE du foyer, pas un compte de mentions (une docstring compterait)."""
    from engine.runner.abilities import attack_query as AQ
    src = inspect.getsource(AQ.entity_can_be_repaired)
    assert "UNIT_FLAG_CAN_REPAIR_FULL_HEALTH" in src, "le disjunct du flag a disparu du gate"
    assert int(AQ.UNIT_FLAG_CAN_REPAIR_FULL_HEALTH) == _FLAG


def test_3_le_passif_est_bien_au_kit_du_porteur():
    """Le seed lit `gameconfig.unit(vid).passiveAbilities` : si `GalvanicField` en sortait, l'entree
    du registre deviendrait inatteignable SANS qu'aucun test de registre ne bouge."""
    import gameconfig as GC
    assert "GalvanicField" in (GC.unit(CARRIER) or {}).get("passiveAbilities", [])
    assert "GalvanicField" not in ((GC.unit(WITNESS) or {}).get("passiveAbilities", []) +
                                   (GC.unit(WITNESS) or {}).get("activeAbilities", []))


# ------------------------------------------------------- [4] LE REGIME SEPARANT (le coeur du test)
def test_4_le_seed_pose_le_flag_sur_un_etat_SANS_capture():
    """L'entite est construite sans `UnitFlagsComponent` : c'est ce que produit un spawn offline
    pur. Le natif, lui, pose le flag a l'init de l'ability (`InitializeActorAbilitiesOperation`).

    AVANT le seed le port n'a rien ; APRES il a le flag. Les deux etats sont assertes -- un test qui
    ne verifierait que l'etat final passerait aussi sur un flag pose par un autre chemin."""
    st = State()
    uid = _unit(st, CARRIER)
    assert _flags(st, uid) == set(), "premisse : aucun flag avant le seed (sinon test vacant)"
    _seed_ability_owner_effects(st, uid, CARRIER, 100, ability_level=50)
    assert _FLAG in _flags(st, uid), \
        "le filet ne mord pas : un `admecManipulus` materialise sans capture reste sans le flag"


def test_5_le_TEMOIN_ne_recoit_rien():
    """Contre-epreuve indispensable : si le seed posait ce flag a tout le monde, le test 4 passerait
    pour une raison FAUSSE (accord en regime degenere)."""
    st = State()
    uid = _unit(st, WITNESS)
    _seed_ability_owner_effects(st, uid, WITNESS, 100, ability_level=50)
    assert _FLAG not in _flags(st, uid), \
        "une unite sans `GalvanicField` ne doit PAS recevoir CanRepairFullHealthUnits"


def test_6_re_seeder_laisse_l_ensemble_INCHANGE():
    """Re-seeder la meme unite (voie capture PUIS atterrissage differe, ou deux chargements) ne doit
    RIEN changer.

    ⚠ CE QUE CE TEST NE PROUVE PAS, et il faut le dire : l'idempotence du FLAG est STRUCTURELLE --
    `UnitFlagsComponent.flags` est un `set` Python (mirror de l'`OrderedSet` natif), donc un doublon
    est impossible par construction et un test qui compterait les occurrences serait VACANT (il
    passerait quoi qu'on ecrive). Ce qui est reellement garde ici, c'est la STABILITE de l'ensemble
    COMPLET : le seed ne doit ni retirer, ni ajouter autre chose au fil des passes."""
    st = State()
    uid = _unit(st, CARRIER)
    _seed_ability_owner_effects(st, uid, CARRIER, 100, ability_level=50)
    apres_1 = _flags(st, uid)
    assert apres_1 == {_FLAG}, "le seed pose EXACTEMENT ce flag, rien d'autre"
    for _ in range(3):
        _seed_ability_owner_effects(st, uid, CARRIER, 100, ability_level=50)
    assert _flags(st, uid) == apres_1, "re-seeder a modifie l'ensemble des flags"


def test_7_le_flag_deja_capte_n_est_pas_perdu():
    """Regime LIVE : le capteur a deja pose le flag. Le seed doit etre un NO-OP EXACT -- ni retrait,
    ni doublon, ni perte des autres flags que l'unite portait."""
    st = State()
    uid = _unit(st, CARRIER)
    c = UnitFlagsComponent()
    c.add(_FLAG)
    c.add(int(UnitFlag.Moved))
    st.get_entity(uid).add_component(c)
    _seed_ability_owner_effects(st, uid, CARRIER, 100, ability_level=50)
    assert _flags(st, uid) == {_FLAG, int(UnitFlag.Moved)}


# ------------------------------------------------------------- [8] les TROIS call-sites du canal
@pytest.mark.parametrize("module, symbole", [
    ("engine.runner.snapshot", "_seed_ability_owner_effects"),
    ("engine.runner.operations.spawn", "_seed_ability_owner_effects"),
])
def test_8_le_canal_est_arrose_par_la_voie_CAPTURE_aussi(module, symbole):
    """LE fait qui refute la fiche : `snapshot.py` (voie CAPTURE) appelle le seed sur CHAQUE entite
    chargee. La fiche n'en comptait que deux (summon, deep-strike) et concluait qu'aucun chemin ne
    materialise un HERO -- d'ou son `BLOCAGE: porteur`."""
    import importlib
    from pathlib import Path
    src = Path(importlib.import_module(module).__file__).read_text(encoding="utf-8")
    assert symbole in src, "%s n'appelle plus le seed -- le canal serait mort" % module


def test_9_le_seed_consomme_bien_le_registre_de_FLAGS():
    """Le seed a DEUX registres (effets et flags) : celui des flags est le seul qui nous concerne,
    et rien d'autre ne le lit."""
    src = inspect.getsource(_seed_ability_owner_effects)
    assert "get_owner_flags_added_on_ability_init" in src
    assert "_add_owner_flag_on_ability_init" in src
