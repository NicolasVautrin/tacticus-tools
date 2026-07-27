"""#174 -- le NIVEAU auquel une MACHINE OF WAR lit ses variables d'ability, et l'INDEX exact.

Ce probe MESURE trois choses distinctes que #162 avait melangees :

  [A] Ce que la ligne `EntityType.Machine` de `combatSnapshot` porte REELLEMENT (elle y est depuis
      `d9d0008`/#128). On imprime `unitConfig`, `stats`, `statDelta`, `shields`, `abilityStates` : le seul
      moyen de savoir ce qu'on PERD en sautant cette ligne dans `_load_stats_and_effects`.

  [B] Le niveau que `load_state` finit par poser sur le `StatsComponent` de la MoW, confronte au
      canal NATIF (`decisionView.mows[].abilities[].level` = `ActiveAbility.AbilityState.Level`,
      lu par `readAbilityState` -- mirror de
      `IdunBattle.Entities.Components.ActiveAbility$$get_AbilityState`).

  [C] L'INDEX. Le natif n'indexe pas « au niveau », il indexe a
      `Math.Max(0, Level.ToZeroBasedIndex(abilityState.Level))` clampe a `len-1` --
      `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`, et
      `Idun.Shared.Level$$ToZeroBasedIndex` rend `value - 1` (il LEVE `InvalidOperationException`
      si `value <= 0` : le niveau 0 n'existe pas nativement). Le probe imprime donc la table
      gameconfig ENTIERE avec l'index calcule, et dit si la valeur observee est DISCRIMINANTE
      (atteinte au seul index attendu) ou si plusieurs index la donnent -- sans quoi « les tests
      passent » ne prouve pas l'index.

Chaine natif (decompile, build gqfc5mff6c) :
    IdunBattle.Entities.Formulas.ConfigAmount$$Calculate
      -> IdunBattle.Entities.Formulas.ConfigAmount$$GetAbilityState
           -> IdunBattle.Entities.UnitExtensions$$GetAbilityState (entite, abilityType)
      -> IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(cfg, varType, &state)
           -> IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel
                idx = Math.Max(0, Idun.Shared.Level$$ToZeroBasedIndex(state.Level))
                idx = min(idx, arr.Length - 1)
                valeur = int.Parse(arr[idx].Split(',')[k])
                si varType est dans `VariablesAffectedByUnitRarityMultiplier` :
                  valeur = Fix64.Round(Fix64(state.VariableMultiplierPercentage) / 100 * valeur)

ASCII only. Ne modifie aucun fichier du moteur.

    python probe_174_mow_level_index.py --mow orksRukkatrukk --ability SquigMine --var nrOfTiles
    python probe_174_mow_level_index.py --mow deathCrawler --ability PlagueburstMortar --var nrOfTiles
    python probe_174_mow_level_index.py --mow adeptExorcist --ability ThriceBlessedConflagration --var nrOfRounds
    python probe_174_mow_level_index.py --mow orksRukkatrukk --ability EntropyCannons --var minDmg
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


def _rpc(sid, method, body, timeout=120):
    r = R._rpc(sid, method, [body], timeout=timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _index_report(table, level, observed):
    """[C] : ou tombe `observed` dans la table, et l'index attendu est-il DISCRIMINANT ?"""
    if not isinstance(table, list) or not table:
        return "table absente ou scalaire"
    idx_expected = max(0, min(level - 1 if level and level > 0 else 0, len(table) - 1))
    hits = [i for i, v in enumerate(table) if v == observed]
    out = [f"len={len(table)} idx_attendu={idx_expected} table[{idx_expected}]={table[idx_expected]}"]
    out.append(f"index donnant {observed} : {hits if len(hits) <= 12 else str(hits[:12]) + '...'}")
    out.append("DISCRIMINANT (1 seul index)" if len(hits) == 1
               else f"NON discriminant ({len(hits)} index) -- il faut une 2e variable")
    return " | ".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mow", default="orksRukkatrukk")
    ap.add_argument("--ability", default="SquigMine")
    ap.add_argument("--var", default="nrOfTiles")
    ap.add_argument("--board", default="C1_02")
    ap.add_argument("--seed", default="4242")
    args = ap.parse_args()

    import gameconfig as GC
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.components import StatsComponent
    from engine.runner.snapshot import load_state, _machine_ability_state

    sid = R._resolve_session()
    state_path = ROOT / "logs" / f"_probe174_{args.mow}.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.unlink(missing_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", args.seed, "--board", args.board,
         "--p-units", "necroDestroyer,necroWarden", "--a-units", "necroDestroyer,necroWarden",
         "--p-mow", args.mow, "--state-file", str(state_path)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_path.exists():
        print("[FAIL] build KO:\n" + (p.stderr or p.stdout or "")[-800:])
        return 2
    rid = json.loads(state_path.read_text())["runnerId"]
    print(f"[ok] runner {rid} mow={args.mow}")

    try:
        dec = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid})
        m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == args.mow), None)
        if m is None:
            print("[FAIL] MoW non deployee")
            return 3
        mid = int(m["casterId"])

        lvl, mult = _machine_ability_state(m)
        print(f"[B1] canal NATIF decisionView.mows -> level={lvl} multiplier={mult} casterId={mid}")

        # [A] ce que porte la ligne Machine du combatSnapshot
        rows = [u for u in (snap.get("units") or []) if u.get("entityType") == 6]
        print(f"[A ] combatSnapshot : {len(rows)} ligne(s) entityType=6 "
              f"(ids={[u.get('entityId') for u in rows]})")
        for u in rows:
            print(f"[A ]  id={u.get('entityId')} unitConfig={json.dumps(u.get('unitConfig'))}")
            print(f"[A ]  id={u.get('entityId')} stats={json.dumps(u.get('stats'))}")
            print(f"[A ]  id={u.get('entityId')} statDelta={json.dumps(u.get('statDelta'))} "
                  f"healthMax={u.get('healthMax')} shields={json.dumps(u.get('shields'))}")
            print(f"[A ]  id={u.get('entityId')} normalAttack={json.dumps(u.get('normalAttack'))}")
            print(f"[A ]  id={u.get('entityId')} abilityStates={json.dumps(u.get('abilityStates'))}")

        # [B] ce que load_state pose
        state = load_state(dec, ob, snap)
        ent = state.get_entity(mid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        got_lvl = getattr(sc.ctx, "active_ability_level", None) if sc is not None else None
        got_mult = getattr(sc.ctx, "ability_variables_multiplier", None) if sc is not None else None
        print(f"[B2] load_state -> ctx.active_ability_level={got_lvl} "
              f"ctx.ability_variables_multiplier={got_mult}")
        if sc is not None:
            print("[B3] load_state -> ctx stats "
                  f"attack={sc.ctx.attack} health={sc.ctx.health} fixedArmor={sc.ctx.fixed_armor} "
                  f"critChance={sc.ctx.crit_chance} critDamage={sc.ctx.crit_damage} "
                  f"blockChance={sc.ctx.block_chance} blockDamage={sc.ctx.block_damage} "
                  f"extraHits={sc.ctx.extra_hits}")
            print(f"[B4] load_state -> ctx.visual_id={sc.ctx.visual_id!r} traits={sc.ctx.traits}")
        # empreinte MULTI-HEX (#R30) : une MoW est hors-plateau -> aucune ligne `observeBattle`,
        # donc `_load_feet` ne la voit pas. On le VERIFIE au lieu de le supposer.
        ob_rows = [u for u in (ob.get("units") or []) if u.get("squadId") == mid]
        from engine.runner.components import UnitComponent
        uc = ent.get_component(UnitComponent) if ent is not None else None
        n_feet = len(getattr(uc, "feet", None) or []) if uc is not None else -1
        multi = [u.get("squadId") for u in (ob.get("units") or [])]
        multi = sorted({s for s in multi if multi.count(s) > 1})
        print(f"[F ] observeBattle lignes pour la MoW={len(ob_rows)} | UnitComponent.feet={n_feet} "
              f"| unites MULTI-HEX du plateau (squadId)={multi}")

        # [C] l'index
        table = ((GC.ability(args.ability) or {}).get("variables") or {}).get(args.var)
        v_bug = ability_var(args.ability, args.var, got_lvl, multiplier_pct=int(got_mult or 100))
        v_ref = ability_var(args.ability, args.var, lvl, multiplier_pct=int(mult or 100))
        print(f"[C1] {args.ability}.{args.var} : niveau LU={got_lvl} -> {v_bug} | "
              f"niveau NATIF={lvl} -> {v_ref}")
        print(f"[C2] {_index_report(table, lvl, v_ref)}")
        aff = (GC.ability(args.ability) or {}).get("variablesAffectedByRarityBonus") or []
        print(f"[C3] {args.var} affecte par le multiplicateur de rarete ? "
              f"{'OUI' if args.var in aff else 'NON'} (liste={aff})")
        if isinstance(table, list):
            print(f"[C4] table brute = {table}")
        print("[verdict] ECRASEMENT" if got_lvl != lvl else "[verdict] niveau CORRECT")
    finally:
        try:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
            print(f"[ok] runner {rid} dispose")
        except Exception as e:                                     # noqa: BLE001
            print(f"[warn] dispose KO: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
