#!/usr/bin/env python
"""Probe #237 -- FORCER UNE RELIQUE EN BATAILLE : les trois verrous, MESURES en live.

LA QUESTION. « Peut-on amener en bataille une unite du pool AVEC une relique qu'elle n'equipe pas
au seed, et a quelle condition exacte ? » -- l'ETAT 2 de la gate de confrontabilite, qui vaut pour
52 des 56 unites eligibles du seed BC.

LA REPONSE, LUE AU DECOMPILE (`docs/rl/case-237-relique-forcee.md`), puis mesuree ici :

  verrou 1  `BC.Units[].TertiaryAbility` (id `TriggeredAbilityType`) --
            `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` ne monte l'ability
            que si le `Nullable` a une valeur, via
            `IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd(id, state, 3)`.
            Le `3` est la HIERARCHIE Tertiary (les passives entrent avec `2`) -- c'est le
            discriminant que ce probe lit.
  verrou 2  `BC.Abilities.PassiveAbilities[<nom>]` -- 29 des 32 abilities de relique sont absentes
            du seed capture ; sans config, `AbilityConfiguration$$GetVariableForLevel` tourne sur
            une config nulle.
  verrou 3  `BC.Units[].TertiaryAbilityLevel >= 1` --
            `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel` (foyer
            UNIQUE des quatre accesseurs de variable) convertit par
            `Idun.Shared.Level$$ToZeroBasedIndex`, qui LEVE `InvalidOperationException` sur <= 0.
            PAS de borne haute : le meme foyer clampe (`idx >= len` -> `len - 1`).

CE QUE LE PROBE MESURE (observable INDEPENDANT de ce que fait la relique -- on ne mesure pas un
effet de jeu, on mesure que l'ability est MONTEE et a QUEL niveau) : le RPC `unitAbilityStates`
dumpe `TriggeredAbilityComponent+0x18` instance par instance ; `raw` y est la fenetre 12 x int32
depuis `+0x10`, donc `raw[0]` = id, `raw[4]` = Level, `raw[5]` = mult, `raw[10]` = hierarchie.
Une relique montee = une entree de hierarchie 3.

Les regimes joues (deux reliques DIFFERENTES sur deux porteurs DIFFERENTS, plus les negatifs) :

  VERT    --equip-relic <uid>:<ability>:<lvl>                 -> hierarchie 3, id et niveau attendus
  ROUGE A relique posee, config d'ability NON injectee        -> ce que le natif fait sans verrou 2
  ROUGE B relique posee + config, TertiaryAbilityLevel = 0    -> ce que le natif fait sans verrou 3
  TEMOIN  aucun --equip-relic                                 -> 0 entree de hierarchie 3

ASCII only (cp1252). Discipline runner : `--state-file` absolu, dispose en fin, un seul runner a la
fois. Usage :
    python probe_237_relic_equip.py                       # les 4 regimes, 2 reliques
    python probe_237_relic_equip.py --board C4_09 --seed 31337
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_inject as CI                                              # noqa: E402
from rl_collect_batch import (                                           # noqa: E402
    _resolve_session, _load_seed_bc, _load_board_dump, _rpc,
    _normalize_and_extract_pool, _spawn_points_by_twpi,
    _patch_predefined_units, PLAYER_ID_HUMAN,
)

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "logs" / "runners" / "probe_237_state.json"

# Deux reliques DIFFERENTES, deux porteurs DIFFERENTS, deux regimes de config :
#   RelicBoltPistol         -> config ABSENTE du seed BC (le cas des 29/32)
#   KardiocoreGalvanus      -> config PRESENTE (equipee au seed par admecMarshall), mais
#                              admecDestroyer, lui, arrive SANS -- c'est bien l'etat 2.
CASES = [
    ("ultraTitus", "RelicBoltPistol", 6),
    ("admecDestroyer", "KardiocoreGalvanus", 3),
]

TERTIARY_HIERARCHY = 3      # AddConfiguredAbilities : TryAdd(..., 3) pour la tertiaire


def _build(sid: int, bc: dict, seed: int, p_units: list, label: str) -> tuple[int | None, str]:
    """initAndStart d'un BC deja normalise. Rend (runnerId|None, message d'erreur)."""
    spawns = _spawn_points_by_twpi(bc)
    pts = spawns.get(0) or []
    if len(pts) < len(p_units):
        return None, f"{len(pts)} spawns joueur < {len(p_units)} units"
    player_units = [{"unitId": p_units[i], "playerId": PLAYER_ID_HUMAN,
                     "col": int(pts[i][0]), "row": int(pts[i][1])}
                    for i in range(len(p_units))]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    resp = _rpc(sid, "initAndStart",
                [{"configJson": json.dumps(bc), "seed": seed,
                  "playerUnits": player_units, "owner": str(STATE.resolve())}], timeout=60)
    res = resp.get("result") or {}
    rid = res.get("runnerId")
    if rid is None:
        return None, str(resp.get("error") or resp)[:400]
    STATE.write_text(json.dumps({"runnerId": rid, "label": label}), encoding="utf-8")
    return rid, ""


def _dispose(sid: int, rid: int | None) -> None:
    if rid is not None:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=15)
        except Exception:                                     # pragma: no cover - diagnostic
            pass


def _tertiary_rows(sid: int, rid: int) -> tuple[list, str]:
    """Entrees TriggeredAbility de hierarchie 3, toutes unites confondues."""
    resp = _rpc(sid, "unitAbilityStates", [{"runnerId": rid}], timeout=60)
    res = resp.get("result") or {}
    if not res.get("ok"):
        return [], str(resp.get("error") or res.get("error") or resp)[:400]
    rows = []
    for u in res.get("units") or []:
        for t in u.get("triggered") or []:
            raw = t.get("raw") or []
            if len(raw) > 10 and raw[10] == TERTIARY_HIERARCHY:
                rows.append({"entityId": u.get("entityId"), "abilityId": raw[0],
                             "level": t.get("level"), "mult": t.get("mult")})
    return rows, ""


def _probe_variable(sid: int, rid: int, ability_id: int, var_type: int,
                    grid: list) -> dict:
    """abilityConfigProbe : demande au NATIF de resoudre une variable aux (niveau, mult) donnes.

    Deux choses d'un coup :
      * `AbilitiesDatabase.GetConfig(TriggeredAbilityType)` -> `config null` si la config
        d'ability n'est PAS dans `BC.Abilities` (verrou 2, regime ROUGE_A) ;
      * `AbilityConfiguration$$GetVariableForLevel` -> passe par
        `TryGetVariableArrayForLevel` -> `Idun.Shared.Level$$ToZeroBasedIndex` (verrou 3).
        Niveau <= 0 doit FAUTER ; niveau au-dela des paliers doit CLAMPER, pas fauter.
    """
    resp = _rpc(sid, "abilityConfigProbe",
                [{"runnerId": rid, "id": ability_id, "kind": "triggered",
                  "varType": var_type, "grid": grid}], timeout=60)
    return resp.get("result") or resp.get("error") or resp


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="#237 -- forcer une relique en bataille")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--rank", type=int, default=17)
    a = ap.parse_args(argv)

    sid = _resolve_session()
    seed_bc = _load_seed_bc(None)
    board = _load_board_dump(a.board)
    print(f"[probe237] session={sid} board={a.board} seed={a.seed} rank={a.rank}")

    # Volet 0 -- ce que le seed BC donne SANS montage (les trois etats, re-derives).
    st = CI.relic_state_of_seed_bc(seed_bc)
    print(f"[etat1] relique EQUIPEE au seed         : {len(st['equipped'])}")
    print(f"[etat2] au catalogue, relique ABSENTE   : {len(st['eligible_no_relic'])}")
    print(f"[etat3] porteur HORS catalogue          : {len(st['off_catalog'])}")

    rc = 0
    for uid, ability, level in CASES:
        aid = CI.triggered_ability_id(ability)
        n_lvl = CI.ability_level_count(ability)
        # varType = une variable REELLE de CETTE ability (le defaut 8 = extraDmg n'existe pas
        # sur toutes) -- sinon `GetVariableForLevel(noThrow=true)` rendrait 0 sans rien exercer.
        var_name = sorted((__import__("gameconfig").ability(ability) or {})
                          .get("variables") or {})[0]
        var_type = CI.ability_variable_id(var_name)
        in_seed = ability in ((seed_bc.get("Abilities") or {}).get("PassiveAbilities") or {})
        print(f"\n=== {uid} <- {ability} (TriggeredAbilityType={aid}, {n_lvl} paliers, "
              f"var {var_name}={var_type}, "
              f"config {'DEJA au seed' if in_seed else 'ABSENTE du seed'}) ===")

        # --- le seed BC de CE cas : config d'ability injectee AVANT normalisation.
        seed_with_cfg = copy.deepcopy(seed_bc)
        node = seed_with_cfg.setdefault("Abilities", {}).setdefault("PassiveAbilities", {})
        if ability not in node:
            node[ability] = CI.synthesize_ability(ability)

        # Une normalisation par SOURCE (avec / sans config), pas par regime : le RPC est cher.
        templates = {}
        for key, src in (("cfg", seed_with_cfg), ("nocfg", seed_bc)):
            templates[key] = _normalize_and_extract_pool(sid, src, a.rank, board_dump=board)

        for regime in ("TEMOIN", "VERT", "ROUGE_A_sans_config", "ROUGE_B_niveau_0"):
            key = "nocfg" if regime == "ROUGE_A_sans_config" else "cfg"
            template, pool, _mow = templates[key]
            if uid not in pool:
                print(f"  [{regime}] SKIP -- {uid} hors pool rank {a.rank}")
                continue
            bc = copy.deepcopy(template)
            if regime != "TEMOIN":
                lvl = 0 if regime == "ROUGE_B_niveau_0" else level
                for u in bc["Units"]:
                    if u.get("Id") == uid:
                        u["TertiaryAbility"] = aid
                        u["TertiaryAbilityLevel"] = lvl
            p_units = [uid]
            a_units = [uid]
            _patch_predefined_units(bc, a_units)
            rid, err = _build(sid, bc, a.seed, p_units, f"{uid}/{ability}/{regime}")
            if rid is None:
                print(f"  [{regime}] initAndStart REFUSE -> {err}")
                continue
            try:
                rows, rerr = _tertiary_rows(sid, rid)
                if rerr:
                    print(f"  [{regime}] unitAbilityStates -> {rerr}")
                else:
                    print(f"  [{regime}] tertiaires montees = {len(rows)} : {rows}")
                if regime == "TEMOIN" and rows:
                    print("  [FAIL] le temoin ne doit porter AUCUNE tertiaire")
                    rc = 1
                if regime == "VERT":
                    ok = any(r["abilityId"] == aid and r["level"] == level for r in rows)
                    print(f"  [VERT] attendu id={aid} level={level} -> "
                          f"{'OK' if ok else 'MANQUANT'}")
                    if not ok:
                        rc = 1
                    # niveaux 1, demande, dernier palier, et TRES au-dela (clamp attendu).
                    grid = [[1, 100], [level, 100], [n_lvl, 100], [n_lvl + 40, 100], [50, 100]]
                    out = _probe_variable(sid, rid, aid, var_type, grid)
                    print(f"  [VERT] GetVariableForLevel({var_name}) : "
                          f"{json.dumps(out.get('values') if isinstance(out, dict) else out)[:500]}")
                if regime == "ROUGE_A_sans_config":
                    out = _probe_variable(sid, rid, aid, var_type, [[level, 100]])
                    print(f"  [ROUGE_A] GetConfig sans config au BC : {json.dumps(out)[:400]}")
                if regime == "ROUGE_B_niveau_0":
                    out = _probe_variable(sid, rid, aid, var_type, [[0, 100], [-1, 100]])
                    print(f"  [ROUGE_B] niveau <= 0 (LEVEE attendue) : "
                          f"{json.dumps(out.get('values') if isinstance(out, dict) else out)[:500]}")
            finally:
                _dispose(sid, rid)
    print("\n[probe237] rc =", rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
