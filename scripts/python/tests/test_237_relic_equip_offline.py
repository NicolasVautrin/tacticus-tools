"""CLIQUET #237 -- FORCER UNE RELIQUE EN BATAILLE : les TROIS ecritures du montage.

Le cas NOMME que ce fichier garde : l'ETAT 2 de la gate de confrontabilite (« porteur au pool,
relique NON equipee »), qui vaut pour 61 des 65 unites eligibles du catalogue. Tant qu'il n'y avait
pas de montage, toute une classe d'abilities etait declaree non confrontable -- et six verdicts
« 0 porteur, DEAD » en sont sortis FAUX (`docs/rl/case-323-unit-map-attribution-voies.md`).

⚠ L'ETAT 3 (« porteur hors pool ») EST VIDE DEPUIS #10039 : `data/seed-bc.json` n'est plus la
capture d'UNE bataille mais un catalogue FORGE par
`Idun.Source.IdunBattle.View.BattleConfigBuilder`, qui porte les 127 `lineup`. Les 9 porteurs qui
exigeaient une injection catalogue prealable y sont entres, donc la ventilation est passee de
4 / 52 / 9 a 4 / 61 / 0. L'etat 3 n'est pas supprime pour autant -- il se rouvre des que le jeu
livre un heros que la fabrique ne monte pas, et `test_porteur_hors_catalogue_leve` le garde.

LES TROIS ECRITURES, chacune avec son verrou natif (RE : `docs/rl/case-237-relique-forcee.md`) :

  1. `BC.Units[].TertiaryAbility` -- lu par
     `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` ; champ nul = l'ability
     n'entre jamais, SANS erreur.
  2. `BC.Abilities.PassiveAbilities[<nom>]` -- 11 des 32 abilities de relique sont ABSENTES du
     catalogue ; sans la config, `AbilityConfiguration$$GetVariableForLevel` tourne sur une
     config nulle -> « system error » au cast. (C'etait 29 sur 32 quand le seed BC etait la
     capture d'UNE bataille ; le catalogue FORGE en porte 21 -- exactement celles qu'une entree
     `Units` porte deja en `TertiaryAbility`. Le regime n'a pas disparu, il a retreci : c'est
     `test_le_regime_CONFIG_ABSENTE_existe_encore_et_se_derive` qui le garde.)
  3. `BC.Units[].TertiaryAbilityLevel >= 1` -- `Idun.Shared.Level$$ToZeroBasedIndex` LEVE
     `InvalidOperationException` sur `<= 0`, et une entree sans relique porte 0.

Ce que le cliquet mord (mutations verifiees ROUGE avant vert) :
  * retirer la garde `level < 1` de `equip_relic`         -> test_niveau_zero_refuse
  * ne plus poser `TertiaryAbility`                       -> test_les_trois_ecritures
  * ne plus injecter la config d'ability                  -> test_les_trois_ecritures,
                                                             test_11_configs_absentes
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
# regimes : `ChaliceOfBaal` est ABSENTE du catalogue (il faut injecter sa config),
# `NetherRealmCasket` y est deja (config presente, relique deja equipee sur necroSpyder).
#
# ⚠ LE PORTEUR DU REGIME « CONFIG ABSENTE » A CHANGE (#10039), ET C'EST UNE MESURE, PAS UN GOUT.
# `Dw02AdvancedBurstCannon` etait ABSENTE du seed BC tant qu'il etait la capture d'UNE bataille.
# Le catalogue est desormais FORGE par `Idun.Source.IdunBattle.View.BattleConfigBuilder` et porte
# 21 des 32 abilities de relique -- exactement celles qu'une entree `Units` porte deja en
# `TertiaryAbility` (`tauNpcCrisis:17` pour celle-ci). Le regime « config absente » existe
# toujours, sur les 11 autres ; `bloodSanguinary` / `ChaliceOfBaal` en fait partie, et le couple
# est RE-DERIVABLE (cf. `test_le_regime_CONFIG_ABSENTE_existe_encore_et_se_derive`).
RELIC_ABSENT = ("bloodSanguinary", "ChaliceOfBaal", 1550)
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
    """Un porteur absent de BC.Units doit etre INJECTE d'abord (write_augmented_seed_bc).

    ⚠ L'ETAT 3 DE LA GATE EST VIDE, ET C'EST LE FAIT NEUF (#10039). « Porteur hors pool » etait le
    troisieme etat de la ventilation des abilities de relique (case-323) : `tauFarsight` en etait
    l'exemple, absent de la capture. Le catalogue forge porte les 127 `lineup`, donc
    `relic_state_of_seed_bc(...)["off_catalog"]` vaut **0** -- plus AUCUNE ability de relique
    n'exige une injection catalogue prealable.

    Le refus, lui, garde toujours quelque chose : un seed BC custom peut avoir ecarte un porteur
    (c'est ce que fait n'importe quel montage filtre). On le DEMONTRE en retirant l'entree, jamais
    avec un id imaginaire -- un `KeyError` sur `"cetIdNexistePas"` ne dirait rien du cas reel.
    """
    st = CI.relic_state_of_seed_bc(seed)
    assert st["off_catalog"] == [], (
        "des porteurs de relique sont hors catalogue : l'etat 3 de la gate se rouvre, et ces "
        "abilities exigent a nouveau `write_augmented_seed_bc` -- %r" % st["off_catalog"])

    uid, ability, _aid = RELIC_ABSENT
    bc = copy.deepcopy(seed)
    bc["Units"] = [u for u in bc["Units"] if u.get("Id") != uid]
    with pytest.raises(KeyError):
        CI.equip_relic(bc, uid, ability, level=1)


def test_11_configs_absentes(seed):
    """La MESURE qui justifie l'ecriture 2 : des abilities de relique manquent au catalogue.

    ⚠ 29 -> 11 (#10039), et le critere se DERIVE au lieu d'etre nomme. Sur la capture, seules les
    3 abilities EQUIPEES au seed avaient leur config. Le catalogue forge en porte 21 -- et la
    regle est EXACTE : `BC.Abilities` porte la config d'une ability de relique si et seulement si
    une entree `Units` la porte en `TertiaryAbility`. Bijection mesuree 21/21, aucune config sans
    porteur, aucun porteur sans config. Enumerer trois noms en dur, comme avant, aurait masque
    cette regle -- et se serait perime au premier boss ajoute.
    """
    pa = seed["Abilities"]["PassiveAbilities"]
    aa = seed["Abilities"]["ActiveAbilities"]
    abilities = sorted({m["ability"] for m in CI.relic_items().values()})
    assert len(abilities) == 32, f"32 abilities de relique attendues, mesure {len(abilities)}"
    present = sorted(a for a in abilities if a in pa or a in aa)
    absent = sorted(a for a in abilities if a not in present)
    assert len(absent) == 11, f"11 configs de relique absentes attendues, mesure {absent}"

    # LA REGLE, dans les deux sens : config presente <=> une entree la porte en TertiaryAbility.
    portes = {u["TertiaryAbility"] for u in seed["Units"] if u.get("TertiaryAbility")}
    ids_presents = {CI.triggered_ability_id(a) for a in present}
    assert ids_presents == portes, {
        "config sans porteur": sorted(ids_presents - portes),
        "porteur sans config": sorted(portes - ids_presents)}

    # ... et le regime « config absente » que ce fichier exerce en est bien un.
    assert RELIC_ABSENT[1] in absent, RELIC_ABSENT
    assert RELIC_PRESENT[1] in present, RELIC_PRESENT


def test_le_regime_CONFIG_ABSENTE_existe_encore_et_se_derive(seed):
    """Le couple `RELIC_ABSENT` n'est pas choisi a la main : il DOIT sortir du balayage.

    Sans ce garde, le jour ou le catalogue portera les 32 configs, `test_les_trois_ecritures`
    deviendrait un test du regime PRESENT deguise en test du regime ABSENT -- vert, et vide.
    """
    pa, aa = seed["Abilities"]["PassiveAbilities"], seed["Abilities"]["ActiveAbilities"]
    have = {u.get("Id") for u in seed["Units"]}
    porte = {u["Id"] for u in seed["Units"] if u.get("TertiaryAbility")}
    candidats = []
    for ability in sorted({m["ability"] for m in CI.relic_items().values()}):
        if ability in pa or ability in aa:
            continue
        for uid in CI.relic_carriers(ability):
            if uid in have and uid not in porte:
                candidats.append((uid, ability))
    assert candidats, (
        "plus AUCUN couple (porteur au catalogue, sans relique, config absente) : le regime que "
        "ce fichier exerce a disparu -- le DIRE, ne pas laisser RELIC_ABSENT pointer sur un "
        "regime qui n'existe plus")
    assert (RELIC_ABSENT[0], RELIC_ABSENT[1]) in candidats, sorted(candidats)[:8]


def test_ventilation_trois_etats(seed):
    """Les TROIS etats de la gate, re-derives -- pas cites de memoire.

    ⚠ 52 -> 61 et 9 -> 0 (#10039). Le nombre d'unites eligibles a une relique n'a PAS bouge (65,
    c'est le gameconfig qui le dit via `items[*].allowedUnits`) ; ce qui a bouge, c'est leur
    repartition : les 9 qui etaient HORS catalogue y sont entrees avec la forge, donc l'etat 3 est
    vide et l'etat 2 les recupere. Le total, lui, garde le compte honnete : 4 + 61 + 0 = 65.
    """
    st = CI.relic_state_of_seed_bc(seed)
    assert len(st["equipped"]) == 4, st["equipped"]
    assert len(st["eligible_no_relic"]) == 61
    assert st["off_catalog"] == [], st["off_catalog"]
    assert len(st["equipped"]) + len(st["eligible_no_relic"]) + len(st["off_catalog"]) == 65, \
        "65 unites du gameconfig sont eligibles a une relique (items[*].allowedUnits)"
    assert {a for _u, a, _l in st["equipped"]} == {1457, 1462, 1475}
    assert all(lvl == 1 for _u, _a, lvl in st["equipped"]), \
        "les 4 heros equipes portent TertiaryAbilityLevel = 1 (pas 50)"


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
    """Garde-fou : `data/seed-bc.json` est une ENTREE VERSIONNEE -- jamais mutee.

    ⚠ 4 -> 55 (#10039). Les 4 comptees jusqu'ici etaient les seuls HEROS equipes de la capture ;
    le catalogue forge porte en plus 51 entrees npc/boss qui arrivent avec leur relique (les
    `*Boss*` / `*Npc<Hero>` -- `tauNpcCrisis:17` porte `Dw02AdvancedBurstCannon`,
    `adeptBossCelestine:19` porte `1468` au niveau 10, ...). Ce sont elles qui expliquent les 21
    configs de relique presentes au catalogue (cf. `test_11_configs_absentes`).
    """
    on_disk = json.loads(SEED_BC.read_text(encoding="utf-8"))
    porteurs = [u for u in on_disk["Units"] if u.get("TertiaryAbility")]
    assert len(porteurs) == 55
    # ... dont EXACTEMENT les 4 heros du gameconfig, les 51 autres etant des entrees npc/boss.
    lineup = set(CI.G._index()["lineup"])
    heros = sorted(u["Id"] for u in porteurs if u["Id"] in lineup)
    assert heros == ["admecMarshall", "admecRuststalker", "necroSpyder", "orksRuntherd"], heros
