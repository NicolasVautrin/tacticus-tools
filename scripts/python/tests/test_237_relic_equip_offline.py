"""CLIQUET #237 -- FORCER UNE RELIQUE EN BATAILLE : les TROIS ecritures du montage.

Le cas NOMME que ce fichier garde : l'ETAT 2 de la gate de confrontabilite (« porteur au pool,
relique NON equipee »), qui vaut pour 52 des 56 unites eligibles du seed BC. Tant qu'il n'y avait
pas de montage, toute une classe d'abilities etait declaree non confrontable -- et six verdicts
« 0 porteur, DEAD » en sont sortis FAUX (`docs/rl/case-323-unit-map-attribution-voies.md`).

LES TROIS ECRITURES, chacune avec son verrou natif (RE : `docs/rl/case-237-relique-forcee.md`) :

  1. `BC.Units[].TertiaryAbility` -- lu par
     `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` ; champ nul = l'ability
     n'entre jamais, SANS erreur.
  2. `BC.Abilities.PassiveAbilities[<nom>]` -- 29 des 32 abilities de relique sont ABSENTES du
     seed capture ; sans la config, `AbilityConfiguration$$GetVariableForLevel` tourne sur une
     config nulle -> « system error » au cast.
  3. `BC.Units[].TertiaryAbilityLevel >= 1` -- `Idun.Shared.Level$$ToZeroBasedIndex` LEVE
     `InvalidOperationException` sur `<= 0`, et une entree sans relique porte 0.

Ce que le cliquet mord (mutations verifiees ROUGE avant vert) :
  * retirer la garde `level < 1` de `equip_relic`         -> test_niveau_zero_refuse
  * ne plus poser `TertiaryAbility`                       -> test_les_trois_ecritures
  * ne plus injecter la config d'ability                  -> test_les_trois_ecritures,
                                                             test_29_configs_absentes
  * ne plus poser `TertiaryAbilityLevel`                  -> test_les_trois_ecritures
  * accepter un porteur hors `allowedUnits` par defaut    -> test_porteur_hors_allowed_refuse

100 % OFFLINE (gameconfig + `data/seed-bc.json`) -- aucune session Frida. ASCII only (cp1252).
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]          # scripts/python
ROOT = Path(__file__).resolve().parents[3]           # racine du checkout
sys.path.insert(0, str(PYDIR))

import catalog_inject as CI                                        # noqa: E402

SEED_BC = ROOT / "data" / "seed-bc.json"

# Deux reliques DIFFERENTES, portees par deux unites DIFFERENTES, choisies pour couvrir les deux
# regimes : `Dw02AdvancedBurstCannon` est ABSENTE du seed BC (il faut injecter sa config),
# `NetherRealmCasket` y est deja (config presente, relique deja equipee sur necroSpyder).
RELIC_ABSENT = ("tauCrisis", "Dw02AdvancedBurstCannon", 1476)
RELIC_PRESENT = ("necroSpyder", "NetherRealmCasket", 1462)


@pytest.fixture(scope="module")
def seed() -> dict:
    if not SEED_BC.exists():                                       # pragma: no cover
        pytest.fail(f"seed BC absent: {SEED_BC} (regenere: python dump_boards.py)")
    return json.loads(SEED_BC.read_text(encoding="utf-8"))


def _unit(bc: dict, uid: str) -> dict:
    hits = [u for u in bc["Units"] if u.get("Id") == uid]
    assert hits, f"{uid} absent de BC.Units"
    return hits[0]


def test_les_trois_ecritures(seed):
    """Un `equip_relic` pose les TROIS choses -- pas deux."""
    uid, ability, aid = RELIC_ABSENT
    bc = copy.deepcopy(seed)
    before = _unit(bc, uid)
    assert before.get("TertiaryAbility") in (None, 0), \
        f"{uid} porte deja une relique au seed -- choisir un autre porteur"
    assert before.get("TertiaryAbilityLevel") == 0, \
        "une entree sans relique porte TertiaryAbilityLevel = 0 (c'est le verrou 3)"
    assert ability not in bc["Abilities"]["PassiveAbilities"], \
        f"{ability} est deja au seed -- ce test veut le regime CONFIG ABSENTE"

    rep = CI.equip_relic(bc, uid, ability, level=4)

    u = _unit(bc, uid)
    assert u["TertiaryAbility"] == aid, "ecriture 1 : TertiaryAbility"
    assert u["TertiaryAbilityLevel"] == 4, "ecriture 3 : TertiaryAbilityLevel"
    assert ability in bc["Abilities"]["PassiveAbilities"], "ecriture 2 : config d'ability"
    cfg = bc["Abilities"]["PassiveAbilities"][ability]
    assert cfg["Variables"], "la config injectee doit porter les Variables du gameconfig"
    assert all(isinstance(v, list) and all(isinstance(x, str) for x in v)
               for v in cfg["Variables"].values()), \
        "Variables : valeurs en CHAINES (mirror des 325 entrees capturees)"
    assert rep["configAdded"] is True and rep["unitsPatched"] == 1


def test_config_deja_presente_non_ecrasee(seed):
    """Regime 2 : la relique est deja au seed -> on ne re-synthetise pas sa config."""
    uid, ability, aid = RELIC_PRESENT
    bc = copy.deepcopy(seed)
    original = copy.deepcopy(bc["Abilities"]["PassiveAbilities"][ability])
    rep = CI.equip_relic(bc, uid, ability, level=10)
    assert rep["configAdded"] is False
    assert bc["Abilities"]["PassiveAbilities"][ability] == original
    assert _unit(bc, uid)["TertiaryAbility"] == aid
    assert _unit(bc, uid)["TertiaryAbilityLevel"] == 10


@pytest.mark.parametrize("bad", [0, -1, -50])
def test_niveau_zero_refuse(seed, bad):
    """VERROU 3. `Idun.Shared.Level$$ToZeroBasedIndex` leve sur <= 0 : refuser AVANT le live."""
    uid, ability, _aid = RELIC_ABSENT
    bc = copy.deepcopy(seed)
    with pytest.raises(ValueError) as ei:
        CI.equip_relic(bc, uid, ability, level=bad)
    msg = str(ei.value)
    assert "ToZeroBasedIndex" in msg, \
        "le refus doit NOMMER le symbole natif qui leve, pas dire 'valeur invalide'"
    assert _unit(bc, uid).get("TertiaryAbility") in (None, 0), \
        "un refus ne doit RIEN avoir ecrit"
    assert ability not in bc["Abilities"]["PassiveAbilities"], \
        "un refus ne doit RIEN avoir ecrit (pas meme la config)"


def test_niveau_au_dela_des_paliers_accepte_et_signale(seed):
    """Pas de borne HAUTE : `TryGetVariableArrayForLevel` clampe (idx >= len -> len-1)."""
    uid, ability, _aid = RELIC_ABSENT
    bc = copy.deepcopy(seed)
    n = CI.ability_level_count(ability)
    assert n == 10, f"les abilities de relique ont 10 paliers, mesure {n}"
    rep = CI.equip_relic(bc, uid, ability, level=50)
    assert rep["clamped"] is True and rep["levelsAvailable"] == 10
    assert _unit(bc, uid)["TertiaryAbilityLevel"] == 50, \
        "on ecrit ce qui est demande : c'est le NATIF qui clampe, pas nous"


def test_porteur_hors_allowed_refuse(seed):
    """`allowedUnits` n'est pas une gate NATIVE de bataille -- mais un garde-fou de montage."""
    bc = copy.deepcopy(seed)
    with pytest.raises(ValueError) as ei:
        CI.equip_relic(bc, "necroSpyder", "Dw02AdvancedBurstCannon", level=1)
    assert "allowedUnits" in str(ei.value)
    # ... et la greffe explicite passe (le natif, lui, n'y voit rien a redire).
    rep = CI.equip_relic(bc, "necroSpyder", "Dw02AdvancedBurstCannon", level=1,
                         allow_unlisted=True)
    assert rep["abilityId"] == 1476


def test_porteur_hors_catalogue_leve(seed):
    """Un porteur absent de BC.Units doit etre INJECTE d'abord (write_augmented_seed_bc)."""
    bc = copy.deepcopy(seed)
    with pytest.raises(KeyError):
        CI.equip_relic(bc, "tauFarsight", "DawnBlade", level=1)


def test_29_configs_absentes(seed):
    """La MESURE qui justifie l'ecriture 2 : 29 des 32 abilities de relique manquent au seed."""
    pa = seed["Abilities"]["PassiveAbilities"]
    aa = seed["Abilities"]["ActiveAbilities"]
    abilities = sorted({m["ability"] for m in CI.relic_items().values()})
    assert len(abilities) == 32, f"32 abilities de relique attendues, mesure {len(abilities)}"
    present = [a for a in abilities if a in pa or a in aa]
    assert sorted(present) == ["KardiocoreGalvanus", "NetherRealmCasket", "SupaCyborkBody"], \
        f"seules les 3 abilities EQUIPEES au seed y ont leur config ; mesure {present}"
    assert len(abilities) - len(present) == 29


def test_ventilation_trois_etats(seed):
    """Les TROIS etats de la gate, re-derives -- pas cites de memoire."""
    st = CI.relic_state_of_seed_bc(seed)
    assert len(st["equipped"]) == 4, st["equipped"]
    assert len(st["eligible_no_relic"]) == 52
    assert len(st["equipped"]) + len(st["eligible_no_relic"]) == 56, \
        "56 unites du seed sont eligibles a une relique (case-323)"
    assert {a for _u, a, _l in st["equipped"]} == {1457, 1462, 1475}
    assert all(lvl == 1 for _u, _a, lvl in st["equipped"]), \
        "le seed capture porte TertiaryAbilityLevel = 1 (pas 50) sur les 4"


def test_parse_spec():
    assert CI.parse_relic_spec("tauCrisis:Dw02AdvancedBurstCannon") == \
        ("tauCrisis", "Dw02AdvancedBurstCannon", 1)
    assert CI.parse_relic_spec("tauCrisis:Dw02AdvancedBurstCannon:7") == \
        ("tauCrisis", "Dw02AdvancedBurstCannon", 7)
    for bad in ("tauCrisis", "", ":X", "a:b:c:d"):
        with pytest.raises(ValueError):
            CI.parse_relic_spec(bad)


def test_write_relic_seed_bc(tmp_path, seed):
    """La FIXTURE : un seed BC ecrit, relisible, avec les trois ecritures pour DEUX reliques."""
    out = tmp_path / "relic_fixture.json"
    p, reports = CI.write_relic_seed_bc(
        out, ["tauCrisis:Dw02AdvancedBurstCannon:10", "eldarAutarch:PhoenixGem:7"],
        seed_bc=seed)
    bc = json.loads(p.read_text(encoding="utf-8"))
    assert [r["abilityId"] for r in reports] == [1476, 1458]
    assert _unit(bc, "tauCrisis")["TertiaryAbility"] == 1476
    assert _unit(bc, "tauCrisis")["TertiaryAbilityLevel"] == 10
    assert _unit(bc, "eldarAutarch")["TertiaryAbility"] == 1458
    assert _unit(bc, "eldarAutarch")["TertiaryAbilityLevel"] == 7
    for ability in ("Dw02AdvancedBurstCannon", "PhoenixGem"):
        assert ability in bc["Abilities"]["PassiveAbilities"]
    # le seed PARTAGE n'a pas bouge
    assert seed["Abilities"]["PassiveAbilities"].get("PhoenixGem") is None


def test_seed_bc_partage_intact(seed):
    """Garde-fou : `data/seed-bc.json` est une ENTREE VERSIONNEE -- jamais mutee."""
    on_disk = json.loads(SEED_BC.read_text(encoding="utf-8"))
    assert len([u for u in on_disk["Units"] if u.get("TertiaryAbility")]) == 4
