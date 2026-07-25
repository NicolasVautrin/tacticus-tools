"""Probe #202-A — validation live du trait WeaverOfFate (triggered 1161, effet 1185).

Scenario crafte (case-202 §5-A) : Abraxas (thousInfernalMaster, SEUL porteur du trait) +
2x Njal (spaceStormcaller : Psyker NON-Chaos — l'aura InfernalPacts non portee reste inerte —
armes melee ET ranged profil Psychic) vs 4 necroWarden melee (ils se packent). HP gonfles
(personne ne meurt). Le walk natif produit du degat Psychic multi-cibles (armes Njal + splash
Psyker des 3 porteurs) -> on OBSERVE la pose native de WeaverOfFate_MaxOutDamage sur Abraxas
et on la confronte a NOTRE reconstruction du trigger (IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$CreateTrigger) :

    >=3 ennemis VIVANTS ayant recu du degat Psychic ce tour  &  !HasEffect(Abraxas, 1185)

Reconstruction offline des cles psychic (mirror IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterReceivedDamage) :
  - attaque NORMALE d'un de nos psykers : cible = profil d'ARME (Abraxas melee=Flame PAS tagge,
    ranged=Psychic ; Njal = Psychic partout) ; les autres ennemis touches le meme step (HP drop,
    adjacents a la cible) = SPLASH Psyker -> Psychic.
  - ABILITY : toutes les victimes = profil de l'ability (gameconfig constants.damageProfile).
  - reset des cles ENNEMIES quand LE JOUEUR ENNEMI commence son tour (mirror per-entering-player
    IdunBattle.Operations.StartTurnOperation$$ResetUnit) — detecte par transition d'equipe de l'acteur.

Sorties : timeline par step (cles/attendu/observe), verdict timing pose + duree observee de
l'effet (expiry Nullable(1) a confronter au modele duration_override=1). ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import gameconfig as GC  # noqa: E402
from engine import weights  # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.services.battle_query import are_tiles_adjacent  # noqa: E402
import engine_validate as EV  # noqa: E402

STATE = ROOT / "data" / "_probe202_duel_state.json"
OUT = ROOT / "data" / "_probe202_diag.json"
CARRIER_VIS = "thousInfernalMaster"
EFFECT_NAME = "WeaverOfFate_MaxOutDamage"
BUILD = ["--p-units", "thousInfernalMaster,spaceStormcaller,spaceStormcaller",
         "--a-units", "necroWarden,necroWarden,necroWarden,necroWarden",
         "--hp-target", "300000", "--hp-player", "300000", "--board", "MC1_67"]


def _ability_profile(ab_id) -> str:
    """Profil de degat d'une ability par id (gameconfig constants.damageProfile ; '' si inconnu)."""
    try:
        name = ActiveAbilityType(int(ab_id)).name
    except Exception:
        return ""
    return (((GC.ability(name) or {}).get("constants") or {}).get("damageProfile")
            or ((GC.ability(name) or {}).get("constants") or {}).get("affectedDamageProfile") or "")


def main() -> int:
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "20201",
         "--state-file", str(STATE), *BUILD],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[probe202] build KO:", (proc.stderr or proc.stdout or "")[-300:])
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    sid = _resolve_session()
    print(f"[probe202] runner={rid}")

    def _r(method: str, body: dict, t: float = 60) -> dict:
        return _rpc(sid, method, [body], timeout=t).get("result") or {}

    psychic_keys: set = set()          # squadIds ennemis tagges Psychic CE TOUR (reconstruction)
    prev_obs: dict = {}                # squadId -> {"hp":, "pos":, "team":, "dead":}
    prev_act: dict = {}                # action native du step precedent {actor, ab, tgt, actor_team}
    prev_team = [None]                 # equipe de l'acteur du step precedent (detection turn-flip)
    rows: list = []
    carrier = {"sq": None, "team": None}

    def _snap(obs: dict) -> dict:
        out = {}
        for u in (obs.get("units") or []):
            sq = u.get("squadId")
            if sq is None:
                continue
            cur = out.setdefault(sq, {"hp": 0, "pos": None, "team": u.get("teamId"),
                                      "dead": bool(u.get("isDead")), "vis": u.get("visualId")})
            cur["hp"] = max(cur["hp"], int(u.get("hp") or 0))          # 1 ligne par UnitFoot
            if cur["pos"] is None:
                cur["pos"] = (u.get("col"), u.get("row"))
        return out

    def diag(step, uid, dv, mov_by_unit, nat, eng, predictor):
        obs = _r("observeBattle", {"runnerId": rid}, 60)
        snap = _snap(obs)
        if carrier["sq"] is None:
            for sq, u in snap.items():
                if u["vis"] == CARRIER_VIS:
                    carrier["sq"], carrier["team"] = sq, u["team"]
        # 1) attribuer les HP-drops du step PRECEDENT (l'action prev_act vient d'etre appliquee)
        if prev_act and prev_obs:
            actor_t = prev_act.get("actor_team")
            if actor_t is not None and actor_t == carrier["team"]:     # nos psykers seulement
                ab = prev_act.get("ab")
                tgt = prev_act.get("tgt")
                a_pos = (prev_obs.get(prev_act.get("actor")) or {}).get("pos")
                t_pos = (prev_obs.get(tgt) or {}).get("pos")
                normal = GC.unit((prev_obs.get(prev_act.get("actor")) or {}).get("vis") or "")
                normal_id = (normal or {}).get("normalAttackType")
                is_normal = (normal_id is not None and ab == normal_id) or ab in (69,)
                for sq, u in snap.items():
                    if u["team"] == carrier["team"]:
                        continue                                        # allies : pas des cibles
                    hp0 = (prev_obs.get(sq) or {}).get("hp")
                    if hp0 is None or u["hp"] >= hp0:
                        continue                                        # pas de degat recu
                    if is_normal:
                        if sq == tgt:
                            # cible directe : profil d'ARME par distance (Abraxas melee=Flame)
                            adj = (a_pos and t_pos
                                   and are_tiles_adjacent(tuple(a_pos), tuple(t_pos), None))
                            vis = (prev_obs.get(prev_act.get("actor")) or {}).get("vis") or ""
                            w = next((w for w in ((GC.unit(vis) or {}).get("weapons") or [])
                                      if bool(w.get("Range")) != bool(adj)), None)
                            prof = (w or {}).get("DamageProfile") or ""
                        else:
                            prof = "Psychic"                            # splash Psyker (adjacent cible)
                    else:
                        prof = _ability_profile(ab)
                    if prof == "Psychic":
                        psychic_keys.add(sq)
        # 2) reset per-entering-player : l'ENNEMI commence son tour -> ses cles sautent
        cur_team = snap.get(uid, {}).get("team")
        if cur_team is not None and prev_team[0] is not None and cur_team != prev_team[0] \
                and cur_team != carrier["team"]:
            psychic_keys.clear()
        prev_team[0] = cur_team
        # 3) confrontation : notre attendu vs l'effet natif OBSERVE sur Abraxas
        alive_keys = {q for q in psychic_keys if not snap.get(q, {}).get("dead")}
        me = next((u for u in (dv.get("units") or []) if u.get("id") == carrier["sq"]), None)
        native_eff = any((e if isinstance(e, str) else (e.get("name") if isinstance(e, dict) else None))
                         == EFFECT_NAME for e in ((me or {}).get("effects") or []))
        expected_new = (len(alive_keys) >= 3 and not native_eff)
        nat_ab = (nat.get("ability") or {}).get("ability") if isinstance(nat, dict) else None
        nat_tg = (nat.get("ability") or {}).get("target") if isinstance(nat, dict) else None
        row = {"step": step, "actor": uid, "team": cur_team, "nat_ab": nat_ab, "nat_tgt": nat_tg,
               "keys": sorted(alive_keys), "native_eff": native_eff, "would_fire": expected_new}
        rows.append(row)
        print(f"  s{step:02d} actor={uid} team={cur_team} ab={nat_ab} keys={sorted(alive_keys)} "
              f"eff_native={int(native_eff)} would_fire={int(expected_new)}")
        # 4) memoriser l'action du step courant pour l'attribution au prochain appel
        prev_act.clear()
        prev_act.update({"actor": uid, "ab": nat_ab, "tgt": nat_tg, "actor_team": cur_team})
        prev_obs.clear()
        prev_obs.update(snap)

    wt = weights.load()
    try:
        EV.run_agreement(sid, rid, 44, wt, log=lambda *a, **k: None, probe=diag)
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, timeout=20)
        try:
            STATE.unlink()
        except OSError:
            pass
    OUT.write_text(json.dumps({"rows": rows}, indent=1), encoding="utf-8")
    # bilan : steps ou l'effet natif est apparu vs nos would_fire
    appear = [r["step"] for i, r in enumerate(rows)
              if r["native_eff"] and (i == 0 or not rows[i - 1]["native_eff"])]
    fires = [r["step"] for r in rows if r["would_fire"]]
    print(f"[probe202] poses natives (transitions off->on): {appear}")
    print(f"[probe202] steps ou NOTRE gate aurait fire: {fires}")
    print(f"[probe202] dump -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
