"""#970-r3 -- CONFRONTATION LIVE de la face DECISION `1200 SquigLaunchas` : le gate NATIF refuse-t-il
la ou le port refuse ?

CE QUE CE PROBE MESURE, ET CE QU'IL NE MESURE PAS
================================================================================================
L'utilite native de 1200 est un TIRAGE (`IPseudoRNG` slot 2 `Next(1, 10)`, refait A CHAQUE CIBLE) :
la CIBLE retenue par le natif est donc indeterminable dans un moteur deterministe (residu
`#970-r6`), et la confronter serait fitter du bruit. Ce probe confronte les TROIS choses qui SONT
etablies :

  1. **LE GATE SEPARE.** `...SquigLaunchasAbility$$FulfillsSummonCriteria` exige `>= nrOfUnits_3`
     Orks allies OU `>= nrOfUnits_4` allies adjacents A LA CIBLE. C'est PLUS STRICT que le gate de
     CIBLAGE (`...$$GetDynamicInvalidTargetReason`, `nrOfUnits` / `nrOfUnits_2`), qui est celui qui
     filtre deja `abilityTargets`. Le REGIME SEPARANT est donc : une cible LEGALE (elle est dans
     `fromHere`) que le playbook REFUSE. Le natif doit y rendre un `Bucket` VIDE.
  2. **LA BORNE DU TIRAGE.** Quand une action EST emise, son utilite doit tomber dans `[1, 9]` --
     `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal` rend `min + (g % (max - min))`,
     borne haute EXCLUE. Assertion de BORNE, pas de valeur.
  3. **C'EST BIEN UN TIRAGE.** Plusieurs invocations dans le MEME etat doivent rendre des utilites
     DIFFERENTES. C'est ce qui distingue << tirage >> de << constante >>, et donc ce qui justifie
     que le port ne porte PAS la valeur (residu `#970-r6`) au lieu de la fitter.

LE CAPTEUR, ET POURQUOI CE N'EST PAS `ncEvaluate`
================================================================================================
⚠ **`ncEvaluate` est STRUCTURELLEMENT AVEUGLE AUX MACHINES OF WAR**, et le decouvrir a coute une
fausse confrontation. Son hook (`frida/hooks/features/ai-step/rpc-predict.ts`) cherche le caster
par `forEachEntity(state, ...)` filtre sur `ty === EntityType.Unit` : une MoW est une
`EntityType.Machine`, donc il rend `{ok: false, error: "unit <id> not found"}` -- pour 1200 comme
pour `1201 SquigMine`, dont le playbook NC est pourtant porte et valide. Une premiere passe de ce
probe lisait `positions` d'une reponse `ok: false` et en concluait << 0 action >> : l'accord obtenu
en regime SEPARANT etait alors DEGENERE, il ne prouvait rien. D'ou les deux crans ci-dessous :
`_oracle_natif` LEVE sur `ok: false`, et le verdict exige un temoin NON NUL (au moins une action
emise quelque part).

Le capteur juste est **`ncPlaybookPredict` (`via: "evaluate"`)**, dont le hook
(`rpc-nc-predict.ts`) accepte `EntityType.Unit` **ou** `EntityType.Machine`. Il invoque le wrapper
`Evaluate/3` du playbook -- appeler la leaf `EvaluateNonComparable` nue crashe -- et rend
`bucketUtil` / `bucketActionCount` decodes de `Bucket+0x20`. Il echo aussi `playbookClass`, ce que
le probe VERIFIE : sans ce cran, un mauvais appariement d'ability rendrait des chiffres d'une AUTRE
classe.

CE QUE CE PROBE NE PROUVE PAS : le wrapper `Evaluate/3` donne l'utilite et la cible, pas la
decision finale de l'IA (qui passe encore par les tiers de priorite et le `Bucket` du tactic). Un
accord ici est necessaire, pas suffisant.

    python probe_970r3_squig_launchas_live.py --state-file <abs> [--board MC1_67] [--seed 777]

Discipline runner : `--state-file` ABSOLU et propre, runner DISPOSE en fin de run. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from engine.entities.active_ability_type import ActiveAbilityType   # noqa: E402

SQUIG = int(ActiveAbilityType.SquigLaunchas)      # 0x4b0 = 1200
MOW = "orksRukkatrukk"
#: Deux Orks (faction `Orks`, kind lineup) -- ce sont EUX qui font basculer le gate.
P_UNITS = "orksNob,orksWarboss,adeptCanoness"
A_UNITS = "necroWarden,necroDestroyer"

#: Placements : la CIBLE `necroWarden` en (3,4). `orksNob` est ADJACENT (3,5) -> 1 Ork = le gate
#: de CIBLAGE passe (`nrOfUnits` = 1) mais celui du SUMMON refuse (`nrOfUnits_3` = 2). `orksWarboss`
#: est a portee de move mais NON adjacent : on l'amenera au contact pour faire basculer le regime.
_PLACE = ["orksNob:3,5", "orksWarboss:5,5", "adeptCanoness:0,0"]
_A_PLACE = ["necroWarden:3,4", "necroDestroyer:6,6"]
CIBLE_POS = (3, 4)
#: Nombre d'invocations en regime PASSANT -- assez pour que << toutes egales >> soit invraisemblable
#: si c'est bien un tirage uniforme sur 9 valeurs (9 * (1/9)^7 ~= 2e-6).
N_TIRAGES = 8


def _rpc_mod():
    """Meme voie que `probe_977` : le resolveur de session et le client RPC du harnais."""
    from rl_collect_batch import _resolve_session, _rpc
    return _resolve_session, _rpc


def _r(rpc, sid, m, b, t=120):
    return (rpc(sid, m, [b], timeout=t).get("result") or {})


def build(state_file: Path, seed: int, board: str, verbose: bool) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--state-file", str(state_file), "--no-ai",
           "--p-units", P_UNITS, "--p-mow", MOW, "--a-units", A_UNITS]
    for p in _PLACE:
        cmd += ["--place", p]
    for p in _A_PLACE:
        cmd += ["--a-place", p]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-2000:]))
    rid = int(json.loads(state_file.read_text())["runnerId"])
    if verbose:
        print("[970-r3/live] runner %d, board %s, seed %d" % (rid, board, seed))
    return rid


def _mow_caster_id(rpc, sid, rid: int):
    """⚠ TROIS ids sur une MoW (`id` / `machineId` / `casterId`) et les RPC d'oracle n'acceptent
    que `casterId` (mesure #977, re-verifiee ici : `id` = 75, `casterId` = `machineId` = 77)."""
    dv = _r(rpc, sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    for m in (dv.get("mows") or []):
        if m.get("visualId") == MOW:
            return m.get("casterId"), dv
    return None, dv


def _cible_legale(rpc, sid, rid: int, caster_id: int):
    """La cible que le gate de CIBLAGE natif accepte -- `abilityTargets(...).fromHere`.

    C'est ce qui fait du regime A un SEPARANT et non un simple << pas de cible >> : la cible EST
    legale, seul le gate du PLAYBOOK la refuse."""
    at = _r(rpc, sid, "abilityTargets",
            {"runnerId": rid, "unitId": caster_id, "abilityId": SQUIG}, 180)
    for u in (at.get("units") or []):
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != SQUIG:
                continue
            for t in (a.get("fromHere") or []):
                if t.get("targetId") is not None:
                    return t.get("targetId"), len(a.get("fromHere") or [])
    return None, 0


def _adjacents_de_la_cible(rpc, sid, rid: int) -> dict:
    """Qui est adjacent a la cible, et de quelle faction -- l'etat MESURE, jamais presume."""
    import gameconfig as GC
    import hexgeo
    o = _r(rpc, sid, "observeBattle", {"runnerId": rid})
    ring = {p for p in hexgeo.disk(CIBLE_POS[0], CIBLE_POS[1], 1) if p != CIBLE_POS}
    out = {"orks": [], "autres": [], "cible_vivante": False}
    for u in (o.get("units") or []):
        if u.get("isDead"):
            continue
        p = (u.get("col"), u.get("row"))
        if p == CIBLE_POS:
            out["cible_vivante"] = True
            continue
        if p not in ring:
            continue
        f = (GC.unit(u.get("visualId")) or {}).get("FactionId")
        (out["orks"] if f == "Orks" else out["autres"]).append((u.get("visualId"), p, f))
    return out


def _oracle_natif(rpc, sid, rid: int, caster_id: int, target_id: int, n: int = 1) -> dict:
    """`ncPlaybookPredict(via="evaluate")` -> le `best` du `Bucket` natif.

    ⚠ UN ECHEC RENDU N'EST PAS UNE MESURE : `ok: false` LEVE. Sans ce cran, un capteur aveugle
    (c'est le cas d'`ncEvaluate` sur une MoW) ferait lire << 0 action >> comme un REFUS du gate."""
    tirages, classes = [], set()
    for _ in range(max(1, n)):
        r = _r(rpc, sid, "ncPlaybookPredict",
               {"runnerId": rid, "unitId": caster_id, "abilityType": SQUIG,
                "targetId": target_id, "via": "evaluate"}, 300)
        if not r.get("ok"):
            raise RuntimeError("ncPlaybookPredict a ECHOUE (capteur muet, PAS un refus du gate) : %s"
                               % json.dumps(r, default=str)[:400])
        classes.add(r.get("playbookClass"))
        tirages.append({"actions": int(r.get("bucketActionCount") or 0),
                        "util": r.get("bucketUtil"), "bucket": r.get("bucket")})
    return {"tirages": tirages, "playbookClass": sorted(classes),
            "actions": tirages[0]["actions"],
            "utils": [t["util"] for t in tirages if t["util"] is not None]}


def _port(rpc, sid, rid: int, caster_id: int) -> dict:
    from engine.ai import context as _ai_ctx
    from engine.playbook import noncomparable as PB
    from engine.playbook import scene as _scene
    from engine.playbook.noncomparable import _targets as TGT
    from engine import weights
    dv = _r(rpc, sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(rpc, sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(lambda m, b, t: _r(rpc, sid, m, b, t), rid)
    c = _ai_ctx.build(lambda m, b, t: _r(rpc, sid, m, b, t), rid, dv, mov_by_unit, caster_id,
                      weights.load(), predictor)
    nc = PB.NCContext(
        uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
        enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
        plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
        elev_by_pos=c.elev_by_pos, ability_targets=c.ability_targets, wt=c.wt,
        is_temporary_by_pos=c.is_temporary_by_pos, effects_by_pos=c.effects_by_pos,
        obs_units=c.obs_units, tile_id_by_pos=c.tile_id_by_pos,
        active_levels=c.active_ability_levels, ability_config=c.heal_config,
        units=c.units, cast_from_tiles=c.cast_from_tiles, scene=c.scene)
    return {"candidats": PB.PLAYBOOKS[SQUIG].generate_candidates(nc),
            "eligibles": TGT.eligible_units(nc, SQUIG)}


def _mesurer(rpc, sid, rid, caster_id, target_id, libelle, n, verbose) -> dict:
    adj = _adjacents_de_la_cible(rpc, sid, rid)
    nat = _oracle_natif(rpc, sid, rid, caster_id, target_id, n)
    prt = _port(rpc, sid, rid, caster_id)
    row = {"libelle": libelle, "orks_adjacents": len(adj["orks"]),
           "autres_adjacents": len(adj["autres"]), "cible_vivante": adj["cible_vivante"],
           "playbookClass": nat["playbookClass"], "natif_actions": nat["actions"],
           "natif_utils": nat["utils"], "port_candidats": len(prt["candidats"]),
           "port_eligibles": len(prt["eligibles"])}
    if verbose:
        print("  [%s] Orks adj=%d | eligibles(CIBLAGE natif)=%d | NATIF actions=%d utils=%s | "
              "PORT candidats=%d | classe=%s"
              % (libelle, row["orks_adjacents"], row["port_eligibles"], row["natif_actions"],
                 row["natif_utils"], row["port_candidats"], row["playbookClass"]))
    return row


def _amener_au_contact(rpc, sid, rid: int, out: dict, verbose: bool) -> bool:
    """DEPLACE le second Ork sur une tuile du ring-1 de la cible -- jamais << bloque par la
    geometrie de spawn >>. La tuile est CHOISIE dans `ring1 INTER atteignables INTER libres`,
    jamais ecrite en dur, et l'ARRIVEE est VERIFIEE."""
    import hexgeo
    o = _r(rpc, sid, "observeBattle", {"runnerId": rid})
    wb = next(((u.get("squadId") if u.get("squadId") is not None else u.get("id"))
               for u in (o.get("units") or [])
               if u.get("visualId") == "orksWarboss" and not u.get("isDead")), None)
    if wb is None:
        out["erreurs"].append("orksWarboss introuvable : REGIME B NON CONFRONTE")
        return False
    mov = _r(rpc, sid, "aiMovableTiles", {"runnerId": rid}, 60)
    atteignables = set()
    for u in (mov.get("units") or []):
        if u.get("unitId") == wb:
            for t in (u.get("tiles") or []):
                p = t if isinstance(t, (list, tuple)) else (t.get("col"), t.get("row"))
                if p and p[0] is not None:
                    atteignables.add((p[0], p[1]))
    ring = [p for p in hexgeo.disk(CIBLE_POS[0], CIBLE_POS[1], 1) if p != CIBLE_POS]
    occupees = {(u.get("col"), u.get("row")) for u in (o.get("units") or []) if not u.get("isDead")}
    contacts = [p for p in ring if p in atteignables and p not in occupees]
    out["contacts_possibles"] = contacts
    if not contacts:
        out["erreurs"].append("aucune tuile du ring-1 atteignable ET libre (atteignables=%d) -- "
                              "REGIME B NON CONFRONTE" % len(atteignables))
        return False
    contact = contacts[0]
    _r(rpc, sid, "applyAction",
       {"runnerId": rid, "action": {"kind": "move", "unitId": wb,
                                    "to": {"col": contact[0], "row": contact[1]}}}, 180)
    # ⚠ VERIFIER QUE LA MUTATION A MORDU : `applyAction` rend un dict truthy meme quand rien n'a
    # bouge (premiere passe : enveloppe `action`/`kind` oubliee -> unite immobile, et le regime B
    # mesurait en fait le regime A).
    o2 = _r(rpc, sid, "observeBattle", {"runnerId": rid})
    arrivee = next(((u.get("col"), u.get("row")) for u in (o2.get("units") or [])
                    if (u.get("squadId") if u.get("squadId") is not None else u.get("id")) == wb
                    and not u.get("isDead")), None)
    out["move"] = {"unitId": wb, "vise": contact, "arrivee": arrivee, "a_mordu": arrivee == contact}
    if verbose:
        print("[970-r3/live] move orksWarboss -> %s : arrivee=%s (a mordu: %s)"
              % (contact, arrivee, arrivee == contact))
    if arrivee != contact:
        out["erreurs"].append("le move n'a PAS mordu (arrivee=%s) -- REGIME B NON CONFRONTE"
                              % (arrivee,))
        return False
    return True


def run(state_file: str, seed: int = 777, board: str = "MC1_67", verbose: bool = True) -> dict:
    sf = Path(state_file).resolve()
    resolve, rpc = _rpc_mod()
    sid = resolve()
    rid = build(sf, seed, board, verbose)
    out = {"runnerId": rid, "board": board, "seed": seed, "regimes": [], "erreurs": []}
    try:
        caster_id, dv = _mow_caster_id(rpc, sid, rid)
        if caster_id is None:
            out["erreurs"].append("MoW %s absente de decisionView.mows" % MOW)
            return out
        out["casterId"] = caster_id
        target_id, n_legales = _cible_legale(rpc, sid, rid, caster_id)
        out["cible"] = {"targetId": target_id, "n_legales": n_legales}
        if target_id is None:
            out["erreurs"].append("aucune cible LEGALE : le regime SEPARANT n'existe pas")
            return out
        if verbose:
            print("[970-r3/live] MoW %s casterId=%s ; cible LEGALE=%s (%d dans fromHere)"
                  % (MOW, caster_id, target_id, n_legales))

        out["regimes"].append(_mesurer(rpc, sid, rid, caster_id, target_id,
                                       "A: 1 Ork adjacent (SEPARANT)", 1, verbose))
        if not _amener_au_contact(rpc, sid, rid, out, verbose):
            return out
        out["regimes"].append(_mesurer(rpc, sid, rid, caster_id, target_id,
                                       "B: 2 Orks adjacents", N_TIRAGES, verbose))
    finally:
        try:
            _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 60)
            if verbose:
                print("[970-r3/live] runner %d dispose" % rid)
        except Exception as exc:                      # pragma: no cover
            out["erreurs"].append("dispose KO: %s" % exc)
    return out


def verdict(r: dict) -> list:
    """Les fautes, une chaine par faute. Vide == confrontation OK."""
    f = list(r.get("erreurs") or [])
    regs = {x["libelle"][0]: x for x in r.get("regimes") or []}
    A, B = regs.get("A"), regs.get("B")
    if not A or not B:
        return f + ["regimes incomplets -- NON CONFRONTE"]
    if A["orks_adjacents"] != 1 or B["orks_adjacents"] < 2:
        f.append("MONTAGE CREUX : Orks adjacents A=%d B=%d (attendu 1 puis >= 2)"
                 % (A["orks_adjacents"], B["orks_adjacents"]))
    if A["port_eligibles"] < 1:
        f.append("MONTAGE CREUX : aucune cible LEGALE en A -- le regime separant exige une cible "
                 "que le CIBLAGE natif accepte")
    for row in (A, B):
        if row["playbookClass"] != ["SquigLaunchasPlaybook"]:
            f.append("le natif a charge %s, pas SquigLaunchasPlaybook" % row["playbookClass"])
    # TEMOIN NON NUL : sans une action emise QUELQUE PART, l'accord est degenere et ne prouve rien.
    if B["natif_actions"] < 1:
        f.append("TEMOIN NUL : le natif n'emet nulle part -- l'accord du regime A ne prouve RIEN")
    if A["natif_actions"] != 0:
        f.append("LE NATIF EMET en regime SEPARANT (%d) : la RE du gate est FAUSSE"
                 % A["natif_actions"])
    for u in (B["natif_utils"] or []):
        if not (1 <= float(u) <= 9):
            f.append("utilite native %s HORS [1,9] : la borne de `Next(1,10)` est mal lue" % u)
    if len(set(B["natif_utils"] or [])) < 2:
        f.append("les %d invocations rendent la MEME utilite %s : ce n'est pas un TIRAGE, donc "
                 "`#970-r6` (valeur non portable) serait a revoir"
                 % (len(B["natif_utils"] or []), sorted(set(B["natif_utils"] or []))))
    for tag, row, attendu in (("A", A, 0), ("B", B, 1)):
        if (row["port_candidats"] > 0) != (attendu > 0):
            f.append("PORT != attendu en regime %s : candidats=%d" % (tag, row["port_candidats"]))
        if (row["port_candidats"] > 0) != (row["natif_actions"] > 0):
            f.append("PORT != NATIF en regime %s : port=%d natif=%d"
                     % (tag, row["port_candidats"], row["natif_actions"]))
    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()
    r = run(a.state_file, a.seed, a.board, verbose=True)
    print()
    f = verdict(r)
    for x in f:
        print("[970-r3/live] FAUTE : %s" % x)
    B = next((x for x in (r.get("regimes") or []) if x["libelle"].startswith("B")), None)
    if B:
        print("[970-r3/live] tirages natifs en regime PASSANT : %s (bornes attendues [1,9])"
              % sorted(B["natif_utils"] or []))
    print("[970-r3/live] VERDICT : %s" % ("OK" if not f else "FAUTES (%d)" % len(f)))
    return 0 if not f else 1


if __name__ == "__main__":
    raise SystemExit(main())
