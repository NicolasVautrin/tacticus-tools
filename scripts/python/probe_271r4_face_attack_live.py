#!/usr/bin/env python
"""#271-r4 -- CONFRONTATION de la face ATTACK du dispatcher non-owner, sur bataille REELLE.

    python probe_271r4_face_attack_live.py --montage nohiding [--board MC1_67 --seed 777]
    python probe_271r4_face_attack_live.py --montage nohiding-gate     # le CONTROLE

CE QUE CE PROBE MESURE, ET CE QU'IL NE MESURE PAS
--------------------------------------------------
La feuille `TriggeredAbilitiesNonOwner(4)` est membre du composite `Damage(35)` (carte de
composition MESUREE par `probe_271r4_composition_map.py` : 13 membres). Sa face ATTACK n'a AUCUN
canal d'observation direct -- les hooks par-tuile de `scorer-damage-trace` portent des RVA
`gqfc5mff6c` et ne se ré-arment pas sans reinject (meme limite que `case-271` §7.4). Ce probe
mesure donc, sur un ETAT LIVE REEL :

  1. **ATTEIGNABILITE** -- le dispatcher yielde-t-il la paire `(playbook, owner)` ? C'est le point
     que le pre-gate `<slot 4>` decide, et c'est CE terme qui etait structurellement inatteignable
     dans le bug de #477-r35 ;
  2. **VALEUR** -- le corps rend-il la cle BC (`10` pour 1523) sur un etat qui realise ses gates ?
  3. **A/B OFF-vs-ON** -- l'utilite d'action de la paire (ability, cible) CHANGE-t-elle quand le
     registre ATTACK est desarme ? Sans ecart, le terme ne pese rien d'observable et la
     confrontation d'argmax n'aurait rien a trancher.

⚠ **CE QU'IL NE MESURE PAS** : l'ARGMAX NATIF. Faire basculer le choix du natif demande un etat ou
le terme (10) depasse l'ecart entre les deux meilleures paires, ce qui ne se fabrique pas a la
demande sur cette face (le composite `Damage(35)` est domine par `DamageDealt` ~[0,100] et
`KillUnit` ~[0,100]). Ce qui est rendu ici est donc « le terme MORD et il DEPLACE l'utilite »,
pas « le natif suit ». Residu ouvert, dit tel quel.

LE MONTAGE -- GREFFE, et pourquoi elle est LICITE
--------------------------------------------------
Les deux porteurs natifs de `1523 NoHidingFromTheWatchers` sont `darkaSmnWatcher` (SUMMON) et
`darkaNpc4Watcher` (npc). Le summon n'a AUCUN invocateur derivable du gameconfig (balayage :
`darkaSmnWatcher` n'apparait dans AUCUNE constante d'ability -- 1 seule occurrence dans tout le
fichier, sa propre entree d'unite). Recours 3 de `case-92` §5bis : la GREFFE du passif sur une
unite DU POOL.

Elle est licite ici et la condition est VERIFIEE au decompile, pas supposee : le corps de
`NoHidingFromTheWatchersNonOwnerPlaybook` ne lit du PORTEUR que sa POSITION
(`GetMainTile(owner)`, `GetUnitPosition(owner)`, `GetAdjacentFriends(pos, owner)`) et son identite
(`case.Target == owner`, `IsFriend(caster, owner)`) -- **aucune stat, aucun trait**. Le natif
charge le playbook PAR ABILITY (`LoadPlaybookNonOwner(ta.Type)`), jamais par unite.

`nohiding-gate` est le CONTROLE : meme montage, mais le caster est un AMI de l'owner. Le corps
ouvre sur `if (IsFriend(caster, owner)) yield break`, donc le terme doit TOMBER a 0 -- et c'est ce
bras qui separe « le terme mord » de « le terme est constant ».

ASCII only (cp1252). Dispose SON runner.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import probe_112_darkangels as PR                                            # noqa: E402
import rl_collect_batch as R                                                 # noqa: E402

#: le PORTEUR greffe (l'OWNER) et le CASTER, tous deux DU POOL. `--p-units` / `--a-units` les
#: placent dans des camps OPPOSES pour le montage nominal (le corps exige `!IsFriend`).
OWNER_VIS = "worldKharn"          # camp ADVERSE -- c'est LUI la cible de l'attaque
OWNER_AMI = "worldTerminator"     # son ami : `GetAdjacentFriends(owner).Count != 0`
CASTER_VIS = "ultraCalgar"        # camp joueur -- l'attaquant
CASTER_AMI = "ultraApothecary"
ABILITY = 1523                    # NoHidingFromTheWatchers


def _seed_bc(out: Path, gate: bool) -> Path:
    import catalog_inject as CI
    bc = CI._load_seed(None)                                                 # noqa: SLF001
    # GATE : le porteur greffe est place du COTE DU CASTER -> `IsFriend` vrai -> le corps break.
    owner = CASTER_AMI if gate else OWNER_VIS
    rep = CI.graft_passive_ability(bc, owner, "NoHidingFromTheWatchers")
    print("  greffe : %s -> NoHidingFromTheWatchers (id %s), %s entree(s), avant=%s"
          % (owner, rep.get("abilityId"), rep.get("unitsPatched"),
             rep.get("passiveAbilitiesBefore")))
    if not rep.get("unitsPatched"):
        print("  ATTENTION : AUCUNE entree BC.Units patchee -- le montage est MUET")
    out.write_text(json.dumps(bc), encoding="utf-8")
    return out


def _build(seed: str, board: str, seed_bc: Path, state: Path) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
            "--state-file", str(state), "--seed-bc", str(seed_bc),
            "--p-units", "%s,%s" % (CASTER_VIS, CASTER_AMI),
            "--a-units", "%s,%s" % (OWNER_VIS, OWNER_AMI)]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise SystemExit("BUILD KO rc=%d\n%s" % (p.returncode, (p.stderr or "")[-1200:]))
    return json.loads(state.read_text(encoding="utf-8"))["runnerId"]


def mesurer(rpc, rid: int, gate: bool, max_steps: int = 14) -> dict:
    """Cherche un pas ou le CASTER est active, et evalue la face ATTACK sur son etat de decision."""
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    from engine.utilities.tile import triggered_abilities_non_owner_attack_utility as F
    import engine.playbook.non_owner_attack as NA
    sys.path.insert(0, str(PYDIR / "tests" / "engine"))
    from _move_tile_sweep_order import _apply_native                          # noqa: E402

    wt = W.load()
    for step in range(max_steps):
        dry = rpc("aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            return {"ok": False, "raison": "trajectoire finie au pas %d (%s)"
                    % (step, dry.get("error"))}
        uid = dry.get("activatedUnitId")
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
        if me is None or me.get("visualId") != CASTER_VIS:
            _apply_native(rpc, rid, dry)
            continue
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        predictor = _scene.build_predictor(lambda m, b, t: rpc(m, b, t), rid)
        ctx = _ai_ctx.build(lambda m, b, t: rpc(m, b, t), rid, dv, mov_by_unit, uid, wt, predictor)
        sc = ctx.scene
        # les porteurs de 1523 VUS par le dispatcher, et leur camp relatif au caster.
        porteurs = []
        for u in (sc.units or []):
            oid = u.get("id")
            if oid is None or int(oid) == int(uid):
                continue
            kit = list(ctx.live_triggered_ability_ids(oid) or ())
            if ABILITY in kit:
                porteurs.append({"id": int(oid), "vis": sc.vis_by_id.get(int(oid)),
                                 "ami": sc.team(int(oid)) == sc.team(uid),
                                 "pos": sc.pos(int(oid))})
        cpos = sc.pos(uid)
        rows = []
        for p in porteurs:
            on = F(ctx, uid, p["id"], cpos)
            anc = dict(NA.NON_OWNER_ATTACK_PLAYBOOKS)
            try:
                NA.NON_OWNER_ATTACK_PLAYBOOKS.clear()          # A/B : registre DESARME
                off = F(ctx, uid, p["id"], cpos)
            finally:
                NA.NON_OWNER_ATTACK_PLAYBOOKS.update(anc)
            rows.append(dict(p, on=on, off=off))
        return {"ok": True, "step": step, "caster": uid, "caster_pos": cpos,
                "porteurs": porteurs, "rows": rows, "gate": gate}
    return {"ok": False, "raison": "le caster %s n'a pas ete active en %d pas"
            % (CASTER_VIS, max_steps)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--montage", default="nohiding",
                    choices=["nohiding", "nohiding-gate"])
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--state-file", default="")
    a = ap.parse_args()
    gate = a.montage.endswith("-gate")

    sid = R._resolve_session()                                               # noqa: SLF001
    tmp = Path(a.state_file or (Path(tempfile.gettempdir())
                                / ("p271r4_%s.json" % uuid.uuid4().hex[:8])))
    bcp = tmp.with_suffix(".bc.json")
    print("[0] montage %s (board %s, seed %s)" % (a.montage, a.board, a.seed))
    _seed_bc(bcp, gate)
    rid = _build(a.seed, a.board, bcp, tmp)
    print("[1] runner %d" % rid)

    def rpc(m, b, t=60):
        return PR.rpc(sid, m, b, t)

    try:
        res = mesurer(rpc, rid, gate)
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        tmp.unlink(missing_ok=True)
        bcp.unlink(missing_ok=True)

    if not res.get("ok"):
        print("[2] NON MESURE : %s" % res.get("raison"))
        return 1
    print("[2] pas %d, caster u%s en %r" % (res["step"], res["caster"], res["caster_pos"]))
    print("[3] porteurs de %d vus par le dispatcher : %d" % (ABILITY, len(res["porteurs"])))
    for r in res["rows"]:
        print("      owner u%-4s %-20s ami=%-5s pos=%-8s  ON=%-6s OFF=%-6s  DELTA=%s"
              % (r["id"], r["vis"], r["ami"], r["pos"], r["on"], r["off"], r["on"] - r["off"]))
    if not res["rows"]:
        print("[4] AUCUN porteur : la greffe n'a pas pris, ou le kit live ne la remonte pas")
        return 1
    mordent = [r for r in res["rows"] if r["on"] != r["off"]]
    if gate:
        print("[4] CONTROLE : le terme doit etre NUL sur tous les porteurs AMIS -> %d qui mordent"
              % len(mordent))
        return 0 if not mordent else 1
    print("[4] %d porteur(s) sur %d font BOUGER l'utilite (ON != OFF)"
          % (len(mordent), len(res["rows"])))
    return 0 if mordent else 1


if __name__ == "__main__":
    raise SystemExit(main())
