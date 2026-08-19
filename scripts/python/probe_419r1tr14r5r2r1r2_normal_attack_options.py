"""probe #419-r1-tr14-r5-r2-r1-r2 -- les `TargetingOptions` de l'ATTAQUE NORMALE, PAR TYPE.

QUESTION BINAIRE
    Le port applique-t-il a chaque unite les `TargetingOptions` de SON type d'attaque normale, ou la
    meme constante a tout le monde ? Et l'ecart CHANGE-T-IL un verdict de ciblage que le natif rend ?

CHAINE NATIVE (decompile = verite, relue sur le build courant)

  `IdunBattle.Entities.Selectors.ValidNormalAttackTargetsSelector$$Select` ne porte AUCUN masque : il
  en DEMANDE un, PAR TYPE --

      opts = battleQuery.<slot 0x3e>(GetNormalAttackType(unit))
      return targetingQuery.<slot 2>(unit, tiles, opts, false).Targets

  et chaque `<X>NormalAttackAbility$$.ctor` pose les siennes. Trois familles, LUES ctor par ctor :

    * recopie du preset `<TargetingOptions statics>+0x00` -> `rules = 0x4002`,
      `range <- TargetingRange statics+0x00` (RANGE_ADJACENT_IF_MELEE_CASTER),
      `forceMeleeTarget = 2` (`RangedBool.IfRangedCaster`) ;
    * recopie du preset `<TargetingOptions statics>+0x80` -> MEME chose, `rules = 0x4000` : le seul
      ecart des deux presets est le bit 1 `TargetMatchesDynamicRule` ;
    * deux LITTERAUX, qui ne recopient aucun preset de `TargetingOptions` :
        `RogalDorn_NormalAttackAbility$$.ctor`     -> `forceMeleeTarget = 1` (`RangedBool.False`)
        `FloatingDeath_NormalAttackAbility$$.ctor` -> `range <- TargetingRange statics+0x30`
                                                      (RANGE_ADJACENT, `overrideRange = 1`)

LE DISCRIMINANT, ENONCE AVANT LA MESURE

  Ce n'est PAS le bit. `TargetMatchesDynamicRule` cable
  `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason`
  (= `FindAttackWeapon(...) != null ? 0 : 2`), une regle NON PORTEE : poser le bit ou non ne deplace
  AUCUN verdict du port aujourd'hui. Le dire, et le MESURER (etage 2), plutot que se declarer vert
  sur un accord degenere.

  Ce qui mord est le `TargetingRange`. Pour un caster RANGED sans ennemi adjacent :
    * `RANGE_ADJACENT_IF_MELEE_CASTER` -> `onlyAdjacent` FAUX -> test de DISTANCE contre la portee
      d'arme : une cible a d=2 ou d=3 est VALIDE ;
    * `RANGE_ADJACENT` (`onlyAdjacent = RangedBool.True`) -> ADJACENCE imposee : la meme cible est
      REFUSEE (`TargetIsInRange`).
  Le port appliquait le premier a TOUT LE MONDE. Donc, pour une unite dont l'attaque normale est
  `1146 FloatingDeath_NormalAttack`, il ACCEPTAIT des cibles que le natif REFUSE.

MONTAGE -- DEUX RUNNERS APPARIES, un seul champ de difference

  `AttackQuery$$GetInvalidTargetReason` commence par
  `ActiveAbilityComponent.GetOrNull(comp, abilityType)` et rend `ValidRequest` (0x1) si l'ability
  n'est pas MONTEE sur le caster : on ne peut donc PAS interroger un type que le caster ne porte pas.
  (MESURE de ce probe, premier jet : les 24 lignes rendaient `0x1`, y compris pour `69` sur un
  `tauMarksman` -- dont l'attaque normale est en fait `1076`.) Le type se MONTE donc, par le meme
  levier ECRIT que #419-r1-tr14-r5-r2-r1 : `BC.Units[].PassiveAbilities`.

    | bras    | `necroWarden.PassiveAbilities` | attaque normale attendue          |
    |---------|--------------------------------|-----------------------------------|
    | `float` | `["FloatingDeath"]`            | **1146** FloatingDeath_NormalAttack |
    | `ctrl`  | `[]`                           | **69**  Loki_NormalAttack          |

  `necroWarden` est RANGED (arme `Gauss` portee 3), HERO, au pool. `FloatingDeath` (1243) a pour
  seuls porteurs le npc et le SUMMON `SporeMine` -- montage ECRIT, comme `Boss` avant lui. La config
  d'ability est DEJA au seed (`BC.Abilities.PassiveAbilities`, verifie) : une seule ecriture suffit.

  Geometrie : spectre (2, 3, 5) autour du caster, et **aucun ennemi adjacent** -- volontaire. Un
  ennemi a d=1 declencherait le clamp de melee de `GetRange`
  (`forceMeleeTarget = IfRangedCaster` + `ShouldApplyRangedInMelee`), qui ramene DEJA la baseline a
  l'adjacence et RE-FERMERAIT le discriminant. MESURE au premier jet : avec un foe a d=1, les deux
  ports rendaient le meme refus a d=2.

VERDICT
  rc 0 si (a) le montage a MORDU dans les deux bras, (b) le port PAR TYPE est en accord TOTAL avec le
  natif, et (c) la BASELINE (la constante unique) diverge sur au moins une ligne. Un accord des deux
  ports serait un regime DEGENERE, et le probe le DIT au lieu de se declarer vert.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, bind_ambient_rpc      # noqa: E402

import probe_247_splash_targeting as P247                            # noqa: E402
import probe_436_taunt_targeting as P436                             # noqa: E402
import probe_419r1tr14r5r2r1_trait_normal_attack as PTRAIT           # noqa: E402

from engine.runner.abilities.targeting import (                      # noqa: E402
    NORMAL_ATTACK_TARGETING_OPTIONS, NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE as OPTS,
    _NormalAttackTargeting, get_invalid_target_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402

_seq = itertools.count(1)

CASTER_VIS = "necroWarden"          # RANGED (arme `Gauss` portee 3), HERO, au pool
PASSIVE = "FloatingDeath"           # `TriggeredAbilityType` 1243 -> attaque normale 1146
FLOAT_TYPE = 1146                   # `ActiveAbilityType.FloatingDeath_NormalAttack`
GENERIC_TYPE = 69                   # `ActiveAbilityType.Loki_NormalAttack`
P_UNITS = "necroWarden,necroSpyder"
#: PAS de `necroDestroyer` : son `Overwatch_AutoAttack` tue le caster pendant le montage geometrique
#: (MESURE : premier jet, `tauMarksman` absent de la vue apres `_drive_spectrum`).
A_UNITS = "tauMarksman,tauCrisis,tauDarkstrider"
#: AUCUN `1` : un ennemi adjacent armerait le clamp de melee et refermerait le discriminant.
WANTS = (2, 3, 5)

#: Les deux bras, et ce qui les separe : UNE liste de passifs sur UNE unite.
ARMS = (("float", [PASSIVE], FLOAT_TYPE), ("ctrl", [], GENERIC_TYPE))


def _build(sid, seed, board, seed_bc):
    """`rl_duel build --seed-bc` avec state-file PROPRE sous `logs/`. ATTEND si `MAX_RUNNERS` est
    sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe419r5r2r1r2-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--seed-bc", str(seed_bc), "--p-units", P_UNITS, "--a-units", A_UNITS]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-600:])
        time.sleep(10)


def _normal_attack_id(dv, uid):
    """L'id CONCRET publie par `decisionView` pour l'attaque normale de `uid` -- c'est
    `ActiveAbilityComponent.NormalAttackType@0x28`, LE champ que la fabrique ecrit. `None` = non
    publie (et alors le montage n'a rien a prouver)."""
    for u in (dv.get("units") or []):
        if int(u.get("id") or -1) == int(uid):
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal" and ab.get("id") is not None:
                    return int(ab["id"])
    return None


def _rows(sid, rid, st, dv, caster_u, aid):
    """Une ligne par cible vivante : natif, port PAR TYPE, port BASELINE (constante unique)."""
    cid = int(caster_u["id"])
    p_new = _NormalAttackTargeting(OPTS[aid])
    p_old = _NormalAttackTargeting(NORMAL_ATTACK_TARGETING_OPTIONS)
    out = []
    for u in (dv.get("units") or []):
        if not u.get("alive") or int(u["id"]) == cid:
            continue
        tid = int(u["id"])
        nat = P247._nat(sid, rid, cid, aid, tid)
        tr = (nat or {}).get("targetReason") or {}
        out.append({
            "tid": tid, "vis": u.get("visualId"),
            "d": hexgeo.distance(P247._pos(caster_u), P247._pos(u)),
            "cote": "ALLIE" if u.get("owner") == caster_u.get("owner") else "ENNEMI",
            "nat": P247._hexval(tr),
            "new": int(get_invalid_target_reason(st, cid, tid, p_new)),
            "old": int(get_invalid_target_reason(st, cid, tid, p_old))})
    return out


def _run_arm(sid, seed, board, arm, passives, want_type, tmpdir):
    seed_bc = PTRAIT._seed_bc(str(Path(tmpdir) / ("seed-%s.json" % arm)),
                              {CASTER_VIS: {"passives": passives}})
    rid, state = _build(sid, seed, board, seed_bc)
    print("\n=== BRAS `%s` -- %s.PassiveAbilities = %s  (runner %d)"
          % (arm, CASTER_VIS, passives, rid))
    try:
        # `initialCooldownTurns` non purges -> `AttackQuery.GetInvalidTargetReason` rend
        # `ValidRequest` (0x1) pour TOUT. MESURE : sans ces endturns, rien n'est mesurable.
        for _ in range(P247.TOURS_DE_CHAUFFE):
            P247._act(sid, rid, {"kind": "endturn"}, 60)
        P247._drive_spectrum(sid, rid, CASTER_VIS, wants=WANTS)
        dv, payloads = P436._capture(sid, rid)
        st = P436._mk_state(payloads)
        me = P247._by_vis(dv, CASTER_VIS)
        if me is None:
            print("  [FAIL] caster `%s` absent ou mort" % CASTER_VIS)
            return None
        got_type = _normal_attack_id(dv, int(me["id"]))
        print("  montage : attaque normale NATIVE de u%s = %s (attendu %d) -> %s"
              % (me["id"], got_type, want_type, "MORD" if got_type == want_type else "N'A PAS MORDU"))
        if got_type != want_type:
            return None
        dists = sorted(hexgeo.distance(P247._pos(me), P247._pos(u)) for u in dv["units"]
                       if u.get("alive") and u.get("owner") != me.get("owner"))
        print("  geometrie : distances ENNEMIES atteintes %s (visees %s)" % (dists, list(WANTS)))
        rows = _rows(sid, rid, st, dv, me, want_type)
        print("      %-5s %-16s %-7s %-3s %-12s %-12s %-12s"
              % ("id", "cible", "cote", "d", "natif", "portParType", "portBaseline"))
        for r in rows:
            print("      %-5d %-16s %-7s %-3d %-12s %-12s %-12s%s"
                  % (r["tid"], r["vis"], r["cote"], r["d"],
                     "?" if r["nat"] is None else hex(r["nat"]), hex(r["new"]), hex(r["old"]),
                     "" if r["new"] == r["old"] else "   <- DISCRIMINANT"))
        return {"rows": rows, "state": st, "caster": int(me["id"]), "dv": dv}
    finally:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state)],
                       cwd=str(PYDIR), capture_output=True, text=True)


class MontageError(RuntimeError):
    """Le montage n'a pas MORDU (bras non montable, caster mort, type non substitue). C'est un
    ECHEC DE MONTAGE, pas un verdict sur le port -- il doit ROUGIR, jamais partir en skip vert."""


def run(sid, seed: str = "4192", board: str = "MC1_67") -> dict:
    """La MESURE, sans verdict : les deux bras + l'inertie du bit. Leve `MontageError` si un bras
    n'a pas mordu -- le test jumeau en fait un ECHEC, pas un skip."""
    import tempfile
    tmpdir = tempfile.mkdtemp()
    res = {}
    for arm, passives, want in ARMS:
        got = _run_arm(sid, seed, board, arm, passives, want, tmpdir)
        if got is None:
            raise MontageError("bras `%s` non montable -> rien n'est mesure" % arm)
        res[arm] = got

    # ------------------------------------------- ETAGE 2 : le bit sur un caster ARME -> sans effet
    # Contre-epreuve OFFLINE sur l'etat du bras `ctrl` : `1030` et `69` ne different QUE par
    # `TargetMatchesDynamicRule`.
    #
    # ⚠ CE QUE CE ZERO SIGNIFIE A CHANGE avec #419-r1-tr14-r5-r2-r1-r2-r1, et le confondre serait
    # une regression silencieuse. La regle dynamique EST desormais portee
    # (`targeting.normal_attack_dynamic_invalid_target_reason`) : le bit n'est plus inerte EN SOI.
    # S'il ne deplace aucun verdict ICI, c'est pour une raison MESURABLE et bien plus interessante --
    # le caster du bras `ctrl` est `necroWarden`, qui porte une arme de MELEE **et** une arme a
    # DISTANCE, donc `FindMeleeWeapon` et `FindRangedWeapon` rendent tous deux non-null, quelle que
    # soit l'adjacence de la cible. La regle ne peut alors PAS refuser.
    # Ce zero garde donc la NON-REGRESSION : la regle portee ne retire AUCUNE cible a un caster arme.
    # Son activite, elle, se mesure la ou elle mord -- caster SANS ARME :
    # `probe_419r1tr14r5r2r1r2r1_normal_attack_dynamic_rule.py`.
    st = res["ctrl"]["state"]
    cid = res["ctrl"]["caster"]
    p69, p1030 = _NormalAttackTargeting(OPTS[69]), _NormalAttackTargeting(OPTS[1030])
    res["bit_diff"] = sum(1 for r in res["ctrl"]["rows"]
                          if get_invalid_target_reason(st, cid, r["tid"], p69)
                          != get_invalid_target_reason(st, cid, r["tid"], p1030))
    print("\n=== ETAGE 2 -- le bit `TargetMatchesDynamicRule` (69 contre 1030), offline")
    print("  lignes ou le port DIFFERE entre 69 et 1030 : %d / %d"
          % (res["bit_diff"], len(res["ctrl"]["rows"])))
    print("  -> %s" % ("SANS EFFET sur un caster ARME (necroWarden a melee ET distance) : la regle "
                       "portee ne lui retire aucune cible" if res["bit_diff"] == 0
                       else "le bit deplace un verdict sur un caster ARME -- la regle dynamique ne "
                            "devrait PAS pouvoir refuser ici, a re-examiner"))
    return res


def tally(res: dict) -> dict:
    """Le BILAN chiffre des deux bras : accord par-type, accord baseline, lignes gagnees/perdues."""
    out = {"tot": 0, "new": 0, "old": 0, "gain": 0, "perte": 0}
    for arm, _p, _t in ARMS:
        rows = [r for r in res[arm]["rows"] if r["nat"] is not None]
        out["tot"] += len(rows)
        out["new"] += sum(1 for r in rows if r["new"] == r["nat"])
        out["old"] += sum(1 for r in rows if r["old"] == r["nat"])
        out["gain"] += sum(1 for r in rows if r["new"] == r["nat"] and r["old"] != r["nat"])
        out["perte"] += sum(1 for r in rows if r["new"] != r["nat"] and r["old"] == r["nat"])
    return out


def print_table() -> int:
    """ETAGE 0 -- la table du port, relue depuis le module. Rend le nombre de jeux DISTINCTS."""
    print("\n=== ETAGE 0 -- la table du port, relue depuis le module")
    print("  %-6s %-10s %-14s %-14s %s" % ("type", "rules", "onlyAdjacent", "overrideRange",
                                           "forceMeleeTarget"))
    for t in sorted(OPTS):
        o = OPTS[t]
        print("  %-6d %-10s %-14s %-14s %s"
              % (t, hex(int(o.rules)), o.range.only_adjacent, o.range.override_range,
                 o.force_melee_target))
    distinct = {(int(o.rules), o.range, o.force_melee_target) for o in OPTS.values()}
    print("  %d types portes, %d jeux d'options DISTINCTS" % (len(OPTS), len(distinct)))
    return len(distinct)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="4192")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args(argv)

    print("=== #419-r1-tr14-r5-r2-r1-r2 -- options d'attaque normale PAR TYPE ===")
    print_table()
    try:
        sid = _resolve_session()
        # #448-r3-r1-r1 : ce montage GREFFE (par les modules qu'il pilote). Sans le canal
        # `unitAbilityStates`, `services.custom_normal_attack` derive le type d'attaque normale du
        # KIT gameconfig, qui ne connait pas la greffe -- le port serait AMPUTE et les assertions
        # negatives passeraient a vide. Le foyer (`snapshot._refuse_if_grafted`) LEVE sans cela.
        bind_ambient_rpc(sid)
        print("[canal] `unitAbilityStates` LIE en ambiant (bind_live_rpc)")
        res = run(sid, a.seed, a.board)
    except MontageError as e:
        print("\n[FAIL] %s" % e)
        return 2
    t = tally(res)

    print("\n=== BILAN")
    for arm, _p, _t in ARMS:
        rows = [r for r in res[arm]["rows"] if r["nat"] is not None]
        print("  bras %-6s : %d lignes, %d accord PAR TYPE, %d accord BASELINE"
              % (arm, len(rows), sum(1 for r in rows if r["new"] == r["nat"]),
                 sum(1 for r in rows if r["old"] == r["nat"])))
    print("  TOTAL       : %d lignes, %d accord PAR TYPE, %d accord BASELINE"
          % (t["tot"], t["new"], t["old"]))
    print("  lignes GAGNEES (baseline fausse, par-type juste) : %d" % t["gain"])
    print("  lignes PERDUES (baseline juste, par-type fausse) : %d" % t["perte"])
    if t["tot"] == 0 or t["new"] != t["tot"] or t["perte"]:
        print("\n[FAIL] le port PAR TYPE n'est pas en accord total avec le natif")
        return 1
    if t["gain"] == 0:
        print("\n[FAIL] REGIME DEGENERE -- la baseline est d'accord partout. Le vert ne prouverait")
        print("       rien : il faut une cible a d>1 DANS la portee d'arme et AUCUN ennemi adjacent.")
        return 1
    print("\n[PASS] accord total avec le natif, et %d ligne(s) que la constante unique ratait"
          % t["gain"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
