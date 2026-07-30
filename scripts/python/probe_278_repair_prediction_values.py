"""probe_278 -- CONFRONTATION LIVE des valeurs du canal `repair_prediction`.

DERNIER PAS de #278. Le DECODAGE est deja livre (`ai-trace/predictions.ts` lit deux
int32 dans RAX, miroir exact de `PredictHeal`) et sa FORME est etablie par deux sources
independantes (RPC `classFields` + decompile). Ce qui manquait : la confrontation des
VALEURS a une mesure independante.

CE QUE LE NATIF DIT, lu au decompile (build rnca9r7q6c, ghidra-mcp) --
`IdunBattle.Core.Services.DamagePrediction$$PredictRepair` :

    eff = amount
    if EntityExtensions.IsActor(caster):
        eff = (int) Fix64(bonus + amount) * Fix64(multiplier)   # stats du caster
    currentHealth = UnitExtensions.GetStat(target, 5 /*Health*/, 0, 0)
    if scope == 1:  eff = Min(eff, GetGroupUnitHealLimit(this, target, currentHealth))
    if UnitExtensions.IsBoss(target):
        eff = Min(eff, GetStat(target, 5, 3, 0) - currentHealth)
    totalHeal = FillUpStatComponent.MaxFillUp(HealthComponent(target), eff)
    return CONCAT44(totalHeal, currentHealth)      # lo = currentHealth, hi = totalHeal

et `IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp` :

    MaxFillUp(amount) = Min(amount, get_CurrentMaximumValue() - <this+0x18 : Remaining>)

Le canal publie donc `{currentHealth: lo, totalHeal: hi}`.

TROIS CONTROLES, du moins cher au plus fort. Chacun est une EGALITE chiffree contre
une source qui n'est PAS le canal teste :

  C1  `prediction.currentHealth` == PV courants de la cible (`observeBattle` -> `hp`).
      N'exige AUCUNE execution. Discriminant : les PV sont POSES par le montage
      (`--unit-stat <cible>:RemainingHealth=N`), donc la valeur attendue est CHOISIE,
      pas constatee -- un decodage qui rendrait autre chose (le max, l'armure, un
      champ voisin) ne peut pas tomber dessus par hasard.

  C2  REGIME BORNE PAR LES PV MANQUANTS. Quand `hpMax - hp` est PLUS PETIT que le
      montant effectif, `MaxFillUp` sature : `totalHeal == hpMax - hp` EXACTEMENT.
      Cette borne se calcule depuis `observeBattle` seul -- aucun parametre du kit,
      aucun scalaire fitte. C'est le `MaxFillUp` natif recalcule a la main.

  C3  REGIME BORNE PAR LE MONTANT. Quand `hpMax - hp` est GRAND, `totalHeal` decroche
      de la borne et se fige sur le montant effectif : il devient INDEPENDANT des PV
      manquants. Deux profondeurs de blessure differentes doivent rendre le MEME
      `totalHeal` -- et ce plateau est ce que C4 execute.

  C4  EXECUTION NATIVE (le controle fort de #278). `applyAction {kind:"ability"}`
      fait CASTER la reparation par le moteur natif ; on relit `observeBattle`. Le
      delta de PV de la cible doit egaler le `totalHeal` predit. La face EXECUTION
      n'est pas portee cote Python (residu #299) -- mais elle n'a pas a l'etre :
      c'est le NATIF qui execute dans le runner.

C2 et C3 ne sont PAS redondants : sans C3, un canal qui publierait betement
`hpMax - hp` (sans jamais consulter le montant) passerait C2 les doigts dans le nez.
Sans C2, un canal qui publierait le montant brut passerait C3. Il faut les DEUX pour
que le montage discrimine.

SEQUENCE -- N'INTERCALE JAMAIS D'`aiturn` AVANT LA MESURE. Mesure du 2026-07-30 :
`aiDryRunAllUnits` IMMEDIAT apres build -> 5 `repair_prediction` ; le meme appel APRES
un tour IA -> 0, les abilities DERIVEES (`RepairType` @0x2c, `NormalAttackType` @0x28)
disparaissant ENSEMBLE de l'enumeration, sans erreur.

Usage (depuis scripts/python, `python` -- pas `py`, ASCII only) :
    python probe_278_repair_prediction_values.py
    python probe_278_repair_prediction_values.py --damaged 2000 --keep
    python probe_278_repair_prediction_values.py --mutate     # garde ROUGE (voir plus bas)

`--mutate` NE TOUCHE PAS au hook (aucune reinjection possible) : il fausse le DECODAGE
COTE LECTEUR -- il relit le meme event en echangeant lo/hi, exactement la faute que le
correctif a supprimee -- et verifie que chaque controle TOMBE. Une garde qu'on n'a pas
vue rouge ne garde rien.

NE REINJECTE PAS et n'active JAMAIS L3 (hooks session-globaux).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PYDIR))
sys.path.insert(0, str(_PYDIR / "tests" / "engine" / "runner"))

import host_inputs  # noqa: E402  (#273 : entrees gitignorees, resolution tri-etat)

TRACES = "frida/data/ai-traces"

# Ids d'ActiveAbilityType de la reparation REGULIERE, lus au decompile de
# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularRepair`
REGULAR_REPAIR_IDS = (28, 1119)


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


# ---- traces ---------------------------------------------------------------- #

def trace_file(sid: int) -> Path | None:
    """JSONL le plus recent de la session `sid`, ou None si PAS MESURE."""
    try:
        files = host_inputs.find(TRACES, f"{sid}-*.jsonl")
    except host_inputs.HostInputUnavailable as e:
        print("[traces] " + str(e))
        return None
    return files[-1] if files else None


def tail_mark(p: Path | None) -> int:
    """Offset de fin du JSONL.

    PIEGE D'OUTILLAGE, deja paye une fois : sous Windows `Get-ChildItem .Length`
    rend 0 tant que le host tient le handle ouvert, alors que le CONTENU est bien
    sur disque. On ne conclut donc JAMAIS "trace vide" d'une taille ; ici la taille
    ne sert que de MARQUE de depart, et c'est la relecture du CONTENU qui tranche.
    """
    if not (p and p.exists()):
        return 0
    try:
        with p.open("rb") as f:
            f.seek(0, 2)
            return f.tell()
    except OSError:
        return 0


def tail_read(p: Path | None, off: int) -> list[dict]:
    if not (p and p.exists()):
        return []
    out: list[dict] = []
    with p.open("r", encoding="utf-8", errors="replace") as f:
        f.seek(off)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _ent_name(e):
    """Projection d'entite des traces : `{"name": "<visualId>"}` (pas d'entityId)."""
    if isinstance(e, dict):
        v = e.get("name")
        return v if isinstance(v, str) else None
    return None


def collect_repairs(events: list[dict], roster: set[str] | None) -> list[dict]:
    """`repair_prediction` du roster. La trace est SESSION-GLOBALE : filtrer."""
    out = []
    for ev in events:
        if ev.get("evt") != "repair_prediction":
            continue
        nm = _ent_name(ev.get("caster"))
        if roster is not None and nm not in roster:
            continue
        out.append({"caster": nm, "target": _ent_name(ev.get("target")),
                    "amount": ev.get("amount"),
                    "prediction": ev.get("prediction") or {},
                    "playbook": ev.get("playbook"),
                    "ability": ev.get("playbookAbility")})
    return out


def read_prediction(entry: dict, mutate: bool = False) -> tuple[int | None, int | None]:
    """(currentHealth, totalHeal) de l'event. `mutate` ECHANGE lo/hi.

    C'est la MUTATION ADVERSARIALE : elle rejoue exactement la faute de decodage
    que le correctif a supprimee (lire le mauvais moitie du registre), sur les
    MEMES octets. Si les controles restent verts sous mutation, ils ne gardent rien.
    """
    p = entry.get("prediction") or {}
    ch, th = p.get("currentHealth"), p.get("totalHeal")
    return (th, ch) if mutate else (ch, th)


# ---- etat observe ---------------------------------------------------------- #

def observe(rpc, rid: int) -> dict:
    """`{visualId: {entityId, hp, hpMax, isDead}}`."""
    ob = _unwrap(rpc("observeBattle", {"runnerId": rid})) or {}
    obs = ob.get("units") or ob.get("observations") or []
    return {o.get("visualId"): o for o in obs if o.get("visualId")}


# ---- controles ------------------------------------------------------------- #

class Check:
    def __init__(self, name: str, ok: bool, detail: str):
        self.name, self.ok, self.detail = name, ok, detail

    def line(self) -> str:
        return "  [%s] %-6s %s" % ("OK" if self.ok else "ROUGE", self.name, self.detail)


def check_current_health(entries, units, mutate=False) -> Check:
    """C1 -- `currentHealth` == `observeBattle.hp` de la cible."""
    bad, seen = [], 0
    for e in entries:
        u = units.get(e["target"])
        if not u:
            continue
        seen += 1
        ch, _ = read_prediction(e, mutate)
        if ch != u.get("hp"):
            bad.append("%s: canal=%s observe_hp=%s" % (e["target"], ch, u.get("hp")))
    if not seen:
        return Check("C1", False, "aucun event exploitable (cible hors observeBattle)")
    return Check("C1", not bad,
                 "%d/%d events : currentHealth == observeBattle.hp%s"
                 % (seen - len(bad), seen, ("" if not bad else " ; ecarts=" + "; ".join(bad[:4]))))


def check_missing_bound(entries, units, mutate=False) -> Check:
    """C2 -- regime SATURE : `totalHeal` == `hpMax - hp` (MaxFillUp recalcule)."""
    bad, seen = [], 0
    for e in entries:
        u = units.get(e["target"])
        if not u:
            continue
        missing = (u.get("hpMax") or 0) - (u.get("hp") or 0)
        seen += 1
        _, th = read_prediction(e, mutate)
        if th != missing:
            bad.append("%s: canal=%s attendu(hpMax-hp)=%s" % (e["target"], th, missing))
    if not seen:
        return Check("C2", False, "aucun event exploitable")
    return Check("C2", not bad,
                 "%d/%d events : totalHeal == hpMax-hp%s"
                 % (seen - len(bad), seen, ("" if not bad else " ; ecarts=" + "; ".join(bad[:4]))))


def check_plateau(runs: list[dict], mutate=False) -> Check:
    """C3 -- regime BORNE PAR LE MONTANT : `totalHeal` independant des PV manquants.

    `runs` = liste de `{"missing": int, "heals": [totalHeal, ...]}` a profondeurs de
    blessure DIFFERENTES, toutes plus grandes que le montant effectif.
    """
    vals = []
    for r in runs:
        hs = sorted({h for h in r["heals"] if h is not None})
        vals.append((r["missing"], hs))
    tops = {tuple(hs) for _, hs in vals}
    detail = " ; ".join("missing=%d -> totalHeal=%s" % (m, hs) for m, hs in vals)
    if len(vals) < 2:
        return Check("C3", False, "moins de 2 profondeurs mesurees : " + detail)
    ok = len(tops) == 1 and all(hs and hs[0] < m for m, hs in vals)
    return Check("C3", ok, detail + ("" if ok else "  <- doit etre EGAL et < missing"))


def check_execution(before: dict, after: dict, target_vis: str,
                    predicted: int | None) -> Check:
    """C4 -- delta de PV apres un cast NATIF == `totalHeal` predit."""
    b, a = before.get(target_vis), after.get(target_vis)
    if not b or not a:
        return Check("C4", False, "cible absente d'un des deux observeBattle")
    delta = (a.get("hp") or 0) - (b.get("hp") or 0)
    return Check("C4", delta == predicted,
                 "hp %s -> %s (delta=%s) vs totalHeal predit=%s"
                 % (b.get("hp"), a.get("hp"), delta, predicted))


# ---- scenario -------------------------------------------------------------- #

def measure(rpc, sid: int, rid: int, unit_id: int, roster: set[str]) -> tuple[list[dict], dict]:
    """Une passe `aiDryRunAllUnits` IMMEDIATE ; rend (events repair, observeBattle)."""
    units = observe(rpc, rid)
    p = trace_file(sid)
    off = tail_mark(p)
    _unwrap(rpc("aiDryRunAllUnits", {"runnerId": rid}, timeout=300))
    ents = collect_repairs(tail_read(p, off), roster)
    return ents, units


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--damaged", type=int, default=None,
                    help="RemainingHealth pose sur la CIBLE (defaut: derive de hpMax)")
    ap.add_argument("--repairer", default=None,
                    help="visualId du repareur (ex. admecDominus -> ability 28)")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer les runners")
    ap.add_argument("--mutate", action="store_true",
                    help="GARDE ROUGE : echange lo/hi a la lecture ; tout doit tomber")
    ap.add_argument("--no-exec", action="store_true",
                    help="saute C4 (pas de cast natif)")
    args = ap.parse_args()

    import rl_collect_batch as R
    import _repair_stage as S

    if args.repairer:
        S.REPAIRER_VIS = args.repairer

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [],
                              timeout=timeout))

    print("session=%d" % sid)
    st = rpc("aiTraceStatus") or {}
    ist = st.get("installStatus") or {}
    print("capteur PredictRepair=%s  L1_evaluate=%s"
          % (ist.get("PredictRepair"), ist.get("L1_evaluate")))
    for lv in ("L1", "L2"):
        rpc("aiTraceEnable", lv)

    roster = {S.REPAIRER_VIS, S.REPAIREE_VIS}
    built: list[int] = []
    checks: list[Check] = []

    try:
        # --- sonde de calibrage : hpMax de la cible, sans rien poser ---------
        st0 = S.build_stage(rpc, hp_player=None, advance=0, damaged_repairee=None)
        built.append(st0["rid"])
        u0 = observe(rpc, st0["rid"])
        hp_max = (u0.get(S.REPAIREE_VIS) or {}).get("hpMax")
        print("cible %s : hpMax=%s (intact hp=%s)"
              % (S.REPAIREE_VIS, hp_max, (u0.get(S.REPAIREE_VIS) or {}).get("hp")))
        if not hp_max:
            print("VERDICT: hpMax introuvable -- montage a refaire")
            return 2

        # --- SHALLOW : blessure PLUS PETITE que le montant -> regime sature --
        shallow_remaining = max(1, hp_max - 1)
        stS = S.build_stage(rpc, hp_player=None, advance=0,
                            damaged_repairee=shallow_remaining)
        built.append(stS["rid"])
        entS, unitsS = measure(rpc, sid, stS["rid"], stS["repairer"], roster)
        uS = unitsS.get(S.REPAIREE_VIS) or {}
        print("\n== SHALLOW (RemainingHealth=%d) ==" % shallow_remaining)
        print("  cible hp=%s hpMax=%s missing=%s ; %d event(s) repair_prediction"
              % (uS.get("hp"), uS.get("hpMax"),
                 (uS.get("hpMax") or 0) - (uS.get("hp") or 0), len(entS)))
        for e in entS[:4]:
            print("    %s" % json.dumps(e, ensure_ascii=True))
        if not entS:
            print("VERDICT: 0 repair_prediction -- rien a confronter (sequence ?)")
            return 3
        checks.append(check_current_health(entS, unitsS, args.mutate))
        checks.append(check_missing_bound(entS, unitsS, args.mutate))

        # --- DEEP x2 : blessure PLUS GRANDE que le montant -> plateau -------
        runs = []
        deep_state = []
        for rem in (args.damaged or 2000, max(1, (args.damaged or 2000) // 2)):
            stD = S.build_stage(rpc, hp_player=None, advance=0, damaged_repairee=rem)
            built.append(stD["rid"])
            entD, unitsD = measure(rpc, sid, stD["rid"], stD["repairer"], roster)
            uD = unitsD.get(S.REPAIREE_VIS) or {}
            missing = (uD.get("hpMax") or 0) - (uD.get("hp") or 0)
            heals = [read_prediction(e, args.mutate)[1] for e in entD]
            print("\n== DEEP (RemainingHealth=%d) ==" % rem)
            print("  cible hp=%s missing=%s ; %d event(s) ; totalHeal=%s"
                  % (uD.get("hp"), missing, len(entD), sorted(set(heals))))
            for e in entD[:2]:
                print("    %s" % json.dumps(e, ensure_ascii=True))
            runs.append({"missing": missing, "heals": heals})
            deep_state.append((stD, entD, unitsD))
        checks.append(check_plateau(runs, args.mutate))
        # C1 tient AUSSI en regime non sature -- et c'est la que sa valeur est
        # CHOISIE par le montage, donc la plus discriminante.
        # DERNIER runner construit : `rl_duel build` REMPLACE le runner de SON
        # `--state-file`, donc les precedents sont deja rendus. Seul le dernier
        # est encore vivant -- c'est lui qu'on fait CASTER.
        stD, entD, unitsD = deep_state[-1]
        c1b = check_current_health(entD, unitsD, args.mutate)
        checks.append(Check("C1b", c1b.ok, c1b.detail))

        # --- C4 : EXECUTION NATIVE ------------------------------------------
        if not args.no_exec and entD:
            tgt = (unitsD.get(S.REPAIREE_VIS) or {}).get("entityId")
            ab = (stD.get("repair_ability") or {}).get("abilityId")
            predicted = read_prediction(entD[0], args.mutate)[1]
            before = observe(rpc, stD["rid"])
            r = rpc("applyAction", {"runnerId": stD["rid"],
                                    "action": {"kind": "ability",
                                               "casterId": stD["repairer"],
                                               "targetId": tgt,
                                               "abilityType": ab}}, timeout=120)
            after = observe(rpc, stD["rid"])
            print("\n== C4 -- cast natif ability=%s caster=%s target=%s ==" % (ab, stD["repairer"], tgt))
            print("  applyAction ok=%s" % (r or {}).get("ok"))
            checks.append(check_execution(before, after, S.REPAIREE_VIS, predicted))

        print("\n== VERDICT%s ==" % (" (MUTE lo<->hi)" if args.mutate else ""))
        for c in checks:
            print(c.line())
        all_ok = all(c.ok for c in checks)
        if args.mutate:
            print("  attendu sous mutation : TOUT ROUGE -> %s"
                  % ("ECHEC DE LA GARDE (des controles restent verts)"
                     if any(c.ok for c in checks) else "garde vue ROUGE, OK"))
            return 0 if not any(c.ok for c in checks) else 1
        return 0 if all_ok else 1
    finally:
        if not args.keep:
            for rid in built:
                try:
                    rpc("disposeRunner", {"runnerId": rid}, timeout=30)
                except Exception as e:          # noqa: BLE001
                    print("[dispose] runner %s : %s" % (rid, e))
            print("\n[dispose] %d runner(s) rendu(s)" % len(built))


if __name__ == "__main__":
    raise SystemExit(main())
