"""GARDE LIVE #237 -- une relique NON equipee au seed arrive-t-elle en bataille ?

Ce que le test EXIGE du natif (montage : `rl_duel build --equip-relic`, RE :
`docs/rl/case-237-relique-forcee.md`) :

  * l'ability entre au `TriggeredAbilityComponent` avec la hierarchie **3** (Tertiary) --
    `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` la monte par
    `TriggeredAbilityComponent$$TryAdd(id, tertiaryState, 3)` ; les passives du kit entrent
    avec `2`, ce qui rend le discriminant net ;
  * son `AbilityState.Level` est EXACTEMENT celui demande (le montage patche le BC APRES
    `buildNormalizedBC`, qui sinon ecrase le niveau a 50) ;
  * le natif resout ses variables au bon palier, et **clampe** au-dela
    (`AbilityConfiguration$$TryGetVariableArrayForLevel` : `idx >= len` -> `len - 1`) ;
  * un niveau `<= 0` **faute** (`Idun.Shared.Level$$ToZeroBasedIndex` leve
    `InvalidOperationException`) -- c'est le verrou que le montage empeche d'armer.

Deux reliques DIFFERENTES sur deux porteurs DIFFERENTS, et les deux regimes de config :
`RelicBoltPistol` (config ABSENTE du seed BC : il faut l'injecter) et `KardiocoreGalvanus`
(config presente, mais `admecDestroyer` arrive sans la relique).

Discipline runner : `build_runner` (fixture), rosters 1v1, board MC1_67. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]          # scripts/python
sys.path.insert(0, str(PYDIR))

import catalog_inject as CI                                          # noqa: E402

TERTIARY_HIERARCHY = 3          # AddConfiguredAbilities : TryAdd(..., 3)
BOARD = "MC1_67"
SEED = "777"

# (unitId, ability, niveau demande, id TriggeredAbilityType attendu, config deja au seed ?)
CASES = [
    ("ultraTitus", "RelicBoltPistol", 6, 1467, False),
    ("admecDestroyer", "KardiocoreGalvanus", 3, 1457, True),
]


def _tertiaries(rpc, rid: int) -> list:
    """Instances TriggeredAbility de hierarchie 3 (`raw` = 12 x int32 depuis +0x10 :
    raw[0] = id, raw[4] = Level, raw[5] = mult, raw[10] = hierarchie)."""
    res = rpc("unitAbilityStates", {"runnerId": rid}, timeout=60)
    assert res.get("ok"), f"unitAbilityStates KO: {res}"
    out = []
    for u in res.get("units") or []:
        for t in u.get("triggered") or []:
            raw = t.get("raw") or []
            if len(raw) > 10 and raw[10] == TERTIARY_HIERARCHY:
                out.append({"entityId": u.get("entityId"), "abilityId": raw[0],
                            "level": t.get("level"), "mult": t.get("mult")})
    return out


def _var_type(ability: str) -> int:
    """Une variable REELLE de l'ability -- le defaut 8 (extraDmg) n'existe pas partout,
    et `GetVariableForLevel(noThrow)` rendrait 0 sans rien exercer."""
    import gameconfig as G
    name = sorted((G.ability(ability) or {}).get("variables") or {})[0]
    return CI.ability_variable_id(name)


@pytest.mark.parametrize("uid,ability,level,aid,cfg_in_seed", CASES,
                         ids=[c[1] for c in CASES])
def test_relique_non_equipee_arrive_en_bataille(build_runner, rpc, uid, ability, level,
                                                aid, cfg_in_seed):
    assert CI.triggered_ability_id(ability) == aid, \
        f"id TriggeredAbilityType de {ability} change de build -- re-deriver"
    r = build_runner(SEED, extra=["--board", BOARD, "--p-units", uid, "--a-units", uid,
                                  "--equip-relic", f"{uid}:{ability}:{level}"])
    rows = _tertiaries(rpc, r["rid"])
    assert rows, (f"AUCUNE ability de hierarchie 3 sur le runner : la relique {ability} "
                  f"n'est PAS montee (verrou 1 -- BC.Units[].TertiaryAbility)")
    mine = [x for x in rows if x["abilityId"] == aid]
    assert mine, f"hierarchie 3 presente mais pas {ability} (id {aid}) : {rows}"
    for x in mine:
        assert x["level"] == level, (
            f"TertiaryAbilityLevel attendu {level}, lu {x['level']} -- signe que le couple "
            f"est pose AVANT buildNormalizedBC (qui ecrase a 50)")


def test_temoin_sans_montage_aucune_tertiaire(build_runner, rpc):
    """Sans `--equip-relic`, le meme roster ne porte AUCUNE ability de hierarchie 3."""
    uid = CASES[0][0]
    r = build_runner(SEED, extra=["--board", BOARD, "--p-units", uid, "--a-units", uid])
    rows = _tertiaries(rpc, r["rid"])
    assert rows == [], (f"temoin pollue : {uid} porte deja une tertiaire {rows} -- "
                        f"le test ne mesurerait plus le montage")


def test_niveau_clampe_en_haut_et_faute_a_zero(build_runner, rpc):
    """Le foyer `TryGetVariableArrayForLevel` : clamp HAUT, LEVEE sur `<= 0`."""
    uid, ability, level, aid, _cfg = CASES[0]
    vt = _var_type(ability)
    n = CI.ability_level_count(ability)
    assert n == 10, f"les abilities de relique ont 10 paliers, mesure {n}"
    r = build_runner(SEED, extra=["--board", BOARD, "--p-units", uid, "--a-units", uid,
                                  "--equip-relic", f"{uid}:{ability}:{level}"])
    res = rpc("abilityConfigProbe",
              {"runnerId": r["rid"], "id": aid, "kind": "triggered", "varType": vt,
               "grid": [[1, 100], [n, 100], [n + 40, 100], [0, 100], [-1, 100]]},
              timeout=60)
    assert res.get("ok"), f"abilityConfigProbe KO: {res}"
    by_level = {v["level"]: v for v in res["values"]}
    v1, vmax, vover = by_level[1], by_level[n], by_level[n + 40]
    assert v1["value"] and vmax["value"], f"variables non resolues : {res['values']}"
    assert v1["value"] < vmax["value"], "les paliers doivent croitre"
    assert vover["value"] == vmax["value"], (
        f"CLAMP HAUT attendu : niveau {n + 40} doit rendre le palier {n} "
        f"({vmax['value']}), lu {vover['value']}")
    for bad in (0, -1):
        assert by_level[bad].get("err"), (
            f"niveau {bad} : `Idun.Shared.Level$$ToZeroBasedIndex` doit LEVER, "
            f"or le natif a rendu {by_level[bad]}")


def test_config_dability_injectee_sinon_variables_muettes(build_runner, rpc):
    """VERROU 2 : sans la config au BC, la config resolue est VIDE -> variable a 0.

    En usage REEL c'est FATAL, pas seulement muet : le noeud DSL du behaviour
    (`IdunBattle.Entities.Formulas.ConfigAmount$$Calculate`) appelle
    `GetVariableForLevel(..., fallbackToDefault = false)`, qui LEVE quand le tableau
    manque. Le RPC de sonde, lui, passe `noThrow = true` : il rend 0 la ou le jeu faute.
    """
    uid, ability, level, aid, _cfg = CASES[0]
    vt = _var_type(ability)
    # avec le montage complet -> valeur du gameconfig
    r_ok = build_runner(SEED, extra=["--board", BOARD, "--p-units", uid, "--a-units", uid,
                                     "--equip-relic", f"{uid}:{ability}:{level}"])
    ok = rpc("abilityConfigProbe",
             {"runnerId": r_ok["rid"], "id": aid, "kind": "triggered", "varType": vt,
              "grid": [[level, 100]]}, timeout=60)
    assert ok.get("ok"), ok
    val_ok = ok["values"][0]["value"]
    assert val_ok, f"montage complet : la variable doit etre resolue, lu {ok['values']}"
    # sans le montage : la config n'est pas au BC -> variable muette
    r_ko = build_runner(SEED, extra=["--board", BOARD, "--p-units", uid, "--a-units", uid])
    ko = rpc("abilityConfigProbe",
             {"runnerId": r_ko["rid"], "id": aid, "kind": "triggered", "varType": vt,
              "grid": [[level, 100]]}, timeout=60)
    assert ko.get("ok"), ko
    assert ko["values"][0]["value"] in (0, None), (
        f"sans la config au BC, {ability} ne doit resoudre AUCUNE variable ; "
        f"lu {ko['values']} (attendu 0/None, la valeur montee vaut {val_ok})")
