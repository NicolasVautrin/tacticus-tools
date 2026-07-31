"""#270-d -- GARDE : une entree injectee au catalogue ne peut porter QUE des membres de `UnitTrait`.

CE QUE CETTE GARDE TIENT. `IdunBattle.Configuration.UnitConfiguration.Traits` est TYPE
`List<IdunBattle.Entities.Enum.UnitTrait>` :

  * `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` recopie
    `UnitProperties+0x18` dans `UnitConfiguration+0xd0` ;
  * `IdunMetaLogic.UserProgress.Model.UnitPropertiesExtensions$$GetPlayerFacingTraits` lit ce MEME
    `UnitProperties+0x18` et sa signature rend `List<IdunBattle.Entities.Enum.UnitTrait>`.

Un nom hors enum est donc INEXPRIMABLE dans ce champ, et le BC entier devient indeserialisable :
`initAndStart` step=deserialize BC -> `Newtonsoft.Json.Converters.StringEnumConverter$$ReadJson`
-> `Newtonsoft.Json.Utilities.EnumUtils$$ParseEnum` -> `$$MatchName`/`$$FindIndexByName` rendent un
`Nullable` vide -> `System.ArgumentException` LEVEE -> Frida rend « system error ». La degradation
n'est ni permissive ni localisee : elle emporte TOUT le montage, y compris les autres unites.

POURQUOI UNE GARDE ET PAS UN CONSTAT. Le gisement est reouvert par le JEU, pas par nous : le
gameconfig VIVANT est livre EN AVANCE sur le binaire. Mesure du 2026-07-31 (`rnca9r7q6c`) --
`astarLysander` (releaseStatus 2026-08-26) apporte `Subfaction: ImperialFists` quand `UnitTrait`
s'arrete a quatre sous-factions (9000..9003). Chaque livraison de contenu peut en apporter un autre,
et le symptome (« initAndStart: system error ») ne nomme jamais le coupable.

Ces tests sont 100 % OFFLINE (gameconfig + table d'enums versionnee) : aucun runner, aucune session.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import catalog_inject as CI  # noqa: E402
import gameconfig as G  # noqa: E402

# Le porteur de #270-d : le montage NOMME du cas, jamais un id inline ailleurs.
LYSANDER = "astarLysander"

# NOM de l'enum, lu par `enum_map` -- l'API qui existait DEJA avant le correctif. La garde doit
# rougir sur la SUBSTANCE (un nom hors vocabulaire), pas sur un helper absent.
UNIT_TRAIT_ENUM = "IdunBattle.Entities.Enum.UnitTrait"


def _members() -> frozenset:
    return frozenset(CI.enum_map(UNIT_TRAIT_ENUM))


def _all_gameconfig_units() -> list:
    idx = G._index()
    return [(kind, uid, gc)
            for kind in ("lineup", "npc", "summons")
            for uid, gc in idx[kind].items()]


def test_synthese_ne_produit_que_des_membres_de_unit_trait():
    """AUCUNE des unites du gameconfig ne doit sortir du vocabulaire de l'enum.

    ROUGE avant le fix -- verbatim mesure le 2026-07-31 sur `rnca9r7q6c` :
        AssertionError: ces entrees porteraient un nom hors
        IdunBattle.Entities.Enum.UnitTrait -> le BC ENTIER devient indeserialisable
        (initAndStart: system error) : {'astarLysander': ['ImperialFists']}
    """
    members = _members()
    hors = {uid: [t for t in CI._traits(gc) if t not in members]
            for _kind, uid, gc in _all_gameconfig_units()}
    hors = {k: v for k, v in hors.items() if v}
    assert hors == {}, (
        "ces entrees porteraient un nom hors %s -> "
        "le BC ENTIER devient indeserialisable (initAndStart: system error) : %r"
        % (UNIT_TRAIT_ENUM, hors))


def test_lysander_est_deployable_et_ce_qui_est_ecarte_est_dit():
    """Le porteur de #270-d passe la gate, et ce qui a ete retire est NOMME (jamais silencieux)."""
    gc = G.unit(LYSANDER)
    assert gc is not None, "%s absent du gameconfig" % LYSANDER
    members = CI.unit_trait_members()
    garde = CI._traits(gc)
    ecarte = CI.dropped_traits(gc)
    assert set(garde) <= members
    assert set(ecarte).isdisjoint(members)
    # partition stricte : rien n'est invente, rien ne disparait sans etre compte
    assert sorted(garde + ecarte) == sorted(CI._traits_raw(gc))
    # le kit de combat proprement dit survit -- seule la sous-faction inconnue tombe
    for t in ("Hero", "TeleportStrike", "TerminatorArmour", "Resilient", "CrushingStrike"):
        assert t in garde, "%s a perdu %s" % (LYSANDER, t)


def test_les_175_entrees_capturees_ne_sont_pas_touchees_par_le_filtre():
    """Le filtre n'a AUCUN effet sur la cohorte que le jeu a reellement construite.

    C'est ce qui distingue un mirror d'une rustine : `--validate` doit rester ce qu'il etait.
    """
    if not CI.SEED_BC.exists():
        pytest.skip("seed BC absent (%s) -- regenere: python dump_boards.py" % CI.SEED_BC)
    bc = json.loads(CI.SEED_BC.read_text(encoding="utf-8"))
    members = _members()
    hors_capture = {u["Id"]: [t for t in (u.get("Traits") or []) if t not in members]
                    for u in bc["Units"]}
    hors_capture = {k: v for k, v in hors_capture.items() if v}
    assert hors_capture == {}, (
        "la capture elle-meme porte des traits hors enum -- le build a change sous nos "
        "pieds : %r" % hors_capture)
    touchees = {}
    for u in bc["Units"]:
        gc = G.unit(u["Id"].split(":")[0])
        if gc is None:
            continue
        drop = [t for t in CI._traits_raw(gc) if t not in members]
        if drop:
            touchees[u["Id"]] = drop
    assert touchees == {}, (
        "le filtre retirerait un trait d'entrees CAPTUREES, donc il change le catalogue au "
        "lieu de le mirrorer : %r" % touchees)
