"""probe #27-r4 -- TheLionsWrath (1217), le SEUL des 4 overrides « npc-only » de #27 dont le terme
custom soit DISCRIMINABLE par le choix de CIBLE du natif.

CE QUI EST TESTE
----------------
`IdunBattle.AI.Playbook.Loki.TheLionsWrathPlaybook$$CalculateCustomUtility` :

    n = |{ e in battleQuery.<slot itf 0x80>(casterPosition, caster, ignoreSteppables: false)
           : IsNormalUnit(e) && HasTrait(e, 0x7ea Chaos) && HasTrait(e, 0x10 Hero) }|
    hits = battleQuery.<slot itf 0xb2>(target)?.<+0x20>          // FindMeleeWeapon(CIBLE).Hits
    return Fix64(hits * 0x1e + n * 2000 + (HasTrait(target, Hero) ? 0x96 : 0))

Les deux premiers facteurs sont lus sur la **CIBLE** -> le terme departage deux cibles d'une MEME
ability, ce qu'aucun des trois autres customs de la tranche ne fait. C'est CE point que le probe
mesure, et il le mesure par DECOMPOSITION D'ETAGE, jamais en fittant un scalaire :

  etage 1  `pairUtility(1217, cible)` = `ComparablePlaybook$$CalculateUtilityFromPredictions` NATIF
           = exactement `u_full`, SANS le custom (le natif somme le custom au-dessus, dans
           `...$$CalculateActionUtility`). C'est donc la reference contre laquelle isoler le terme.
  etage 2  le custom PORTE, par cible.
  etage 3  le choix NATIF de cible (`aiDryRunAllUnits`), a comparer a `argmax(u_full + custom)`.

Le bras est CONCLUANT quand `argmax(u_full)` et `argmax(u_full + custom)` designent des cibles
DIFFERENTES : le natif ne peut alors suivre les deux, et son choix tranche.

MONTAGE (board MC1_67)
----------------------
PORTEUR GREFFE. Le seul porteur de 1217 est `darkaBossLion` [npc]. « npc-only » n'est PAS « non
confrontable » : le natif charge le playbook PAR ABILITY (`PlaybookDatabase.LoadPlaybook`), et de son
CASTER cette formule ne lit que le CAMP (`...$$GetAdjacentEnemies` n'interroge que
`OwnerComponent$$get_CurrentPlayerEntityId`). On remplace donc `ActiveAbilities` de `darkaAsmodai`
(Dark Angels comme `darkaBossLion`, melee, dans `rl_duel build --list-pool`) par `[1217]` dans une
COPIE du seed BC (`case-92` §5bis). La greffe ne couvre ni stats ni traits ni armes du vrai porteur :
c'est legitime ICI parce que la formule n'en lit AUCUN.

Le masque de 1217 est `0x4000 = TargetIsEnemy` SEUL, avec `range = RANGE_ADJACENT` : les cibles
legales sont les ENNEMIS ADJACENTS a la tuile du caster. Le montage amene donc DEUX ennemis sur deux
voisins de la tuile du caster, et laisse le troisieme au loin.

LES DEUX CIBLES, et pourquoi CELLES-LA : **les 97 unites du pool portent TOUTES le trait `Hero`**
(compte re-derive, pas herite) -- le terme `150 x [cible Hero]` est donc CONSTANT entre deux heros et
ne peut pas etre discrimine par ce montage. Ce qui reste discriminable sur l'axe CIBLE est
`30 x FindMeleeWeapon(cible).Hits`, et on prend les deux extremes disponibles :
`blackAbaddon` (hits = 5) contre `thousAhriman` (hits = 1) -> ecart de custom = 30 x 4 = **120**.
Les deux sont Chaos+Hero, donc `n` vaut 2 pour les DEUX et s'annule dans le departage de cible.

`--hp-ahriman` regle les PV de `thousAhriman` (`--unit-stat`) : c'est le levier qui deplace `u_full`
de CETTE cible seule, donc qui fabrique -- ou defait -- le desaccord entre les deux argmax.

Usage (depuis scripts/python, ASCII only) :
    python probe_27_r4_lions_wrath.py --build [--hp-ahriman N]
    python probe_27_r4_lions_wrath.py                      # re-joue sur le runner du state-file
    python probe_27_r4_lions_wrath.py --sweep A,B,C        # rebuild + mesure pour chaque PV
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L
from engine.entities.active_ability_type import ActiveAbilityType

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_lions_wrath_graft.json"
STATE = LOGS / "rs_27r4_lions_wrath.json"
BOARD = "MC1_67"
SEED = 909
RANK = 17

LIONS_WRATH = int(ActiveAbilityType.TheLionsWrath)        # 1217 = 0x4c1
NORMAL = 69

GRAFT_ON = "darkaAsmodai"
P_UNITS = "darkaAsmodai"
A_UNITS = "blackAbaddon,thousAhriman,necroWarden"

CASTER_VID = "darkaAsmodai"
HI_VID = "blackAbaddon"      # FindMeleeWeapon().Hits = 5 -> custom hits = 150
LO_VID = "thousAhriman"      # FindMeleeWeapon().Hits = 1 -> custom hits =  30
FAR_VID = "necroWarden"

NEAR_1 = "1,1"               # voisin de la tuile de spawn du caster (1,0)
NEAR_2 = "0,0"               # second voisin
TRANSIT = "2,0"              # 3e voisin, LIBRE : sert d'etape a l'ECHANGE des deux cibles
FAR = "6,7"


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _dv(rid: int) -> dict:
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row))} -- les ids ne sont JAMAIS hardcodes."""
    return {u["visualId"]: (u["id"], (u["pos"]["col"], u["pos"]["row"]))
            for u in (_dv(rid).get("units") or [])}


def write_graft_seed_bc() -> None:
    """Copie du seed BC PARTAGE avec `ActiveAbilities` de `GRAFT_ON` remplace par `[1217]`.
    N'ECRIT JAMAIS le seed BC partage (meme discipline que `catalog_inject --out`)."""
    import rl_collect_batch as R
    bc = R._load_seed_bc(None)
    n = 0
    for u in bc.get("Units") or []:
        if u.get("Id") == GRAFT_ON:
            u["ActiveAbilities"] = [LIONS_WRATH]
            n += 1
    if n != 1:
        raise SystemExit("greffe impossible : %d entree(s) %r dans BC.Units" % (n, GRAFT_ON))
    LOGS.mkdir(parents=True, exist_ok=True)
    SEED_BC.write_text(json.dumps(bc), encoding="utf-8")
    print("[graft] %s.ActiveAbilities = [%d]" % (GRAFT_ON, LIONS_WRATH))


def build(hp_lo: "int | None" = None) -> int:
    write_graft_seed_bc()
    args = ["build", "--seed", str(SEED), "--board", BOARD, "--rank", str(RANK),
            "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
            "--state-file", str(STATE)]
    if hp_lo is not None:
        # `--unit-stat` est le SEUL levier per-unit : il deplace `u_full` de CETTE cible seule.
        # `RemainingHealth` suit `Health`, sinon la cible spawnerait blessee d'un montant arbitraire.
        args += ["--unit-stat", "%s:Health=%d;%s:RemainingHealth=%d" % (LO_VID, hp_lo, LO_VID, hp_lo)]
    _run(args)
    return _runner_id()


def _move(rid: int, unit: int, to: str) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", to,
          "--state-file", str(STATE), "--runner", str(rid)])


def _assert_placed(rid: int, want) -> None:
    """Un `act move` REFUSE ne leve rien : sans cette assertion les bras degenerent en UN seul
    etat, ou l'accord natif<->attendu est trivialement vrai (piege mesure le 2026-07-30 sur #27-4)."""
    pos = {i: p for _v, (i, p) in _units(rid).items()}
    bad = [(u, to, pos.get(u)) for u, to in want
           if pos.get(u) != tuple(int(x) for x in to.split(","))]
    if bad:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s"
                         % ["u%s voulu=%s obtenu=%s" % (u, to, got) for u, to, got in bad])


def place(rid: int, swap: bool = False) -> dict:
    """Amene HI et LO sur deux voisins de la tuile du caster, FAR au loin. Le CASTER n'est jamais
    deplace (l'ability est ADJACENT-only : le bouger changerait l'ensemble des cibles legales).

    `swap` ECHANGE les deux tuiles : c'est la contre-epreuve de l'ORDRE D'ENUMERATION. Le natif
    balaie les cibles par rang cube croissant (`IterateSurroundingTiles`) et garde le premier maximum
    STRICT ; si son choix venait de l'ordre et non du custom, il changerait de cible ici."""
    import hexgeo
    u = _units(rid)
    cid, cpos = u[CASTER_VID]
    t_hi, t_lo = (NEAR_2, NEAR_1) if swap else (NEAR_1, NEAR_2)
    _move(rid, u[FAR_VID][0], FAR)
    if swap:
        # ECHANGE : les deux tuiles cibles sont OCCUPEES l'une par l'autre -> un `act move` croise
        # est REFUSE (mesure : les deux unites restent en place, et `_assert_placed` le voit). On
        # passe par une 3e tuile adjacente au caster, LIBRE.
        _move(rid, u[LO_VID][0], TRANSIT)
    _move(rid, u[HI_VID][0], t_hi)
    _move(rid, u[LO_VID][0], t_lo)
    u = _units(rid)
    _assert_placed(rid, [(u[HI_VID][0], t_hi), (u[LO_VID][0], t_lo)])
    # FAR n'a pas de position IMPOSEE (une seule detente de mouvement ne porte pas jusqu'a `FAR`) :
    # ce qui compte est qu'il ne soit NI adjacent au caster (il entrerait dans le compte `n` et
    # deviendrait une 3e cible legale) NI ailleurs qu'a distance >= 2.
    if hexgeo.distance(cpos, u[FAR_VID][1]) < 2:
        raise SystemExit("montage invalide : %s est adjacent au caster (%s vs %s)"
                         % (FAR_VID, u[FAR_VID][1], cpos))
    return {"caster": (cid, cpos), "hi": u[HI_VID], "lo": u[LO_VID], "far": u[FAR_VID]}


def _pair_utility(rid: int, cid: int, tgt: int, ability: int) -> float:
    """`pairUtility` = `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
    NATIF pour (ability, cible) DEPUIS LA POSITION COURANTE du caster = exactement `u_full`, le
    custom EXCLU (le natif le somme au-dessus, dans `...$$CalculateActionUtility`)."""
    r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": cid, "targetId": tgt,
                               "abilityType": int(ability)}])
    v = r.get("utility") if isinstance(r, dict) else r
    return float(v if v is not None else 0.0)


def _playbook_predict_count(rid: int, cid: int, tgt: int) -> "int | None":
    """`aiPlaybookPredict` = `<Playbook>$$MakeDamagePredictions` NATIF. `count == 0` avec
    `listNull == false` = l'override rend une liste VIDE (et non : l'appel a echoue)."""
    r = L._rpc("aiPlaybookPredict", [{"runnerId": rid, "unitId": cid, "targetId": tgt,
                                     "abilityType": LIONS_WRATH}])
    if not isinstance(r, dict) or r.get("listNull") is not False:
        return None
    return int(r.get("count") or 0)


def _native_choice(rid: int, cid: int) -> list:
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    for u in (dr.get("units") or []):
        if u.get("unitId") == cid:
            return [(m.get("cls"), m.get("abilityType"), m.get("targetId"))
                    for m in (u.get("proposed") or [])]
    return []


def _engine(rid: int, cid: int, targets: list) -> dict:
    """Le custom PORTE par cible + la decision moteur, et ses TROIS contre-epreuves."""
    import engine_validate as EV
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook import nonattack as NA
    from engine.ai import context as AICTX

    sid = L.INV._session_id()

    def rpc(m, b, t):
        return EV._r(sid, m, b, t)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, cid, wt, predictor)
    pb = PB.REGISTRY.get(LIONS_WRATH)
    custom = {t: pb.calculate_custom_utility(ctx, ctx.origin, t, LIONS_WRATH) for t in targets}
    elig = pb.eligible_targets(ctx, LIONS_WRATH)
    preds = pb.make_damage_predictions(ctx, ctx.origin, targets[0], LIONS_WRATH)

    on = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    # CE1 -- custom force a 0 : le terme est-il ce qui produit l'action ?
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = lambda self, c, t, target, aid: 0.0
    try:
        zero = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    # CE2 -- terme `30 x Hits` NIE : c'est le SEUL des trois facteurs qui departage deux cibles ici
    # (les deux sont Hero, et `n` ne depend pas de la cible). S'il ne departageait pas, le nier ne
    # changerait pas la cible, et l'accord du bras principal ne prouverait rien.
    saved_w = type(pb).TARGET_MELEE_HIT_UTILITY
    type(pb).TARGET_MELEE_HIT_UTILITY = -saved_w
    try:
        neg = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    finally:
        type(pb).TARGET_MELEE_HIT_UTILITY = saved_w
    # CE3 -- registre de route VIDE : sans `NONATTACK_PLAYBOOKS`, 1217 n'a AUCUNE route (elle est
    # invisible de `_best_attack`), donc le moteur doit retomber sur une autre action.
    saved_r = dict(NA.NONATTACK_PLAYBOOKS)
    NA.NONATTACK_PLAYBOOKS.clear()
    try:
        noroute = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    finally:
        NA.NONATTACK_PLAYBOOKS.update(saved_r)
    return {"custom": custom, "eligible": elig, "n_preds": len(preds or []),
            "on": (on.get("ability"), on.get("target")), "to": on.get("to"),
            "zero": (zero.get("ability"), zero.get("target")),
            "neg": (neg.get("ability"), neg.get("target")),
            "noroute": (noroute.get("ability"), noroute.get("target"))}


def measure(rid: int, label: str, swap: bool = False) -> dict:
    p = place(rid, swap=swap)
    cid, cpos = p["caster"]
    hi_id, hi_pos = p["hi"]
    lo_id, lo_pos = p["lo"]
    # ETAGE 1 -- `u_full` NATIF de 1217 par cible. MESURE, jamais postulat : c'est lui qui etablit
    # que le custom est le SEUL departageur de cible.
    uf = {hi_id: _pair_utility(rid, cid, hi_id, LIONS_WRATH),
          lo_id: _pair_utility(rid, cid, lo_id, LIONS_WRATH)}
    nat_preds = {hi_id: _playbook_predict_count(rid, cid, hi_id),
                 lo_id: _playbook_predict_count(rid, cid, lo_id)}
    # La PREVIEW (utilite de l'attaque NORMALE sur la meme cible) : l'ordre que suivrait le choix si
    # le degat comptait. CONTRASTE, pas reference.
    pv = {hi_id: _pair_utility(rid, cid, hi_id, NORMAL),
          lo_id: _pair_utility(rid, cid, lo_id, NORMAL)}
    e = _engine(rid, cid, [hi_id, lo_id])
    cu = e["custom"]
    arg_cu = max(cu, key=lambda t: cu[t])
    arg_pv = max(pv, key=lambda t: pv[t])
    ch = _native_choice(rid, cid)
    nat = [(a, t) for c, a, t in ch if c == "ActiveAbilityMessage"]
    nat_t = nat[-1][1] if nat else None
    nat_a = nat[-1][0] if nat else None
    name = {hi_id: HI_VID, lo_id: LO_VID}
    print("  [%s%s] caster u%d @%s | %s u%d @%s | %s u%d @%s"
          % (label, " SWAP" if swap else "", cid, cpos, HI_VID, hi_id, hi_pos,
             LO_VID, lo_id, lo_pos))
    for t in (hi_id, lo_id):
        print("        %-14s u_full(1217)=%8.4f  nPredsNatif=%s  custom(porte)=%8.1f  preview(69)=%9.4f"
              % (name[t], uf[t], nat_preds[t], cu[t], pv[t]))
    print("        nPreds(porte)=%d | argmax custom=%s | argmax preview=%s | CONTRASTE=%s"
          % (e["n_preds"], name[arg_cu], name[arg_pv], "OUI" if arg_cu != arg_pv else "non"))
    print("        natif  : %s -> ability=%s cible=%s (%s)"
          % ([c for c, _a, _t in ch], nat_a, nat_t, name.get(nat_t, "?")))
    print("        moteur : on=%s to=%s cibles_eligibles=%s" % (e["on"], e["to"], e["eligible"]))
    print("        contre-epreuves : custom=0 -> %s | terme Hits NIE -> %s | route OFF -> %s"
          % (e["zero"], e["neg"], e["noroute"]))
    return {"label": label + (" SWAP" if swap else ""), "swap": swap, "caster": cid,
            "hi": hi_id, "lo": lo_id, "u_full": uf, "custom": cu, "preview": pv,
            "native_preds": nat_preds, "engine_preds": e["n_preds"],
            "arg_custom": arg_cu, "arg_preview": arg_pv,
            "native_ability": nat_a, "native_target": nat_t,
            "engine": e["on"], "zero": e["zero"], "neg": e["neg"], "noroute": e["noroute"]}


def verdict(rows: list) -> int:
    """CINQ exigences, et chacune ferme une explication concurrente de l'accord :

      V1 le natif emet `ActiveAbilityMessage(1217)` -- l'ability est CONFRONTEE (greffe operante) ;
      V2 le natif choisit la cible d'argmax(CUSTOM), et le moteur la MEME -- le terme departage ;
      V3 au moins un bras a `argmax(custom) != argmax(preview)` -- le choix ne s'explique donc pas
         par l'utilite de degat ;
      V4 les DEUX arrangements de positions donnent le meme vainqueur -- le choix ne s'explique pas
         par l'ordre d'enumeration des cibles ;
      V5 `MakeDamagePredictions` rend une liste VIDE des DEUX cotes (natif ET port).
    Plus les contre-epreuves : `custom = 0` et `route OFF` doivent DEPLACER la decision moteur, et
    NIER le terme `30 x Hits` doit changer la CIBLE (sans quoi ce terme serait decoratif)."""
    fails = []
    if not rows:
        return 2
    for r in rows:
        tag = r["label"]
        for t, n in r["native_preds"].items():
            if n != 0:
                fails.append("%s V5: MakeDamagePredictions natif rend %s event(s) sur u%s" % (tag, n, t))
        if r["engine_preds"] != 0:
            fails.append("%s V5: le port rend %d prediction(s)" % (tag, r["engine_preds"]))
        if r["native_ability"] != LIONS_WRATH:
            fails.append("%s V1: le natif n'a pas emis 1217 (ability=%s)" % (tag, r["native_ability"]))
            continue
        if r["native_target"] != r["arg_custom"]:
            fails.append("%s V2: natif cible=%s, argmax(custom)=%s"
                         % (tag, r["native_target"], r["arg_custom"]))
        if r["engine"] != (LIONS_WRATH, r["native_target"]):
            fails.append("%s V2: moteur=%s, natif=(%s, %s)"
                         % (tag, r["engine"], LIONS_WRATH, r["native_target"]))
        if r["zero"] == r["engine"]:
            fails.append("%s CE1: custom force a 0 ne deplace pas la decision (%s)" % (tag, r["zero"]))
        if r["noroute"] == r["engine"]:
            fails.append("%s CE3: route OFF ne deplace pas la decision (%s)" % (tag, r["noroute"]))
        if r["neg"] == r["engine"]:
            fails.append("%s CE2: nier `30 x Hits` ne change pas la cible (%s) -- terme decoratif"
                         % (tag, r["neg"]))
    if not any(r["arg_custom"] != r["arg_preview"] for r in rows):
        fails.append("V3: aucun bras avec argmax(custom) != argmax(preview) -- non discriminant")
    winners = {r["native_target"] for r in rows if r["native_ability"] == LIONS_WRATH}
    if len({r["swap"] for r in rows}) < 2:
        fails.append("V4: les deux arrangements de positions n'ont pas ete joues")
    elif len(winners) > 1:
        fails.append("V4: le vainqueur natif CHANGE avec l'arrangement des positions (%s)" % winners)
    print("")
    for f in fails:
        print("  FAIL " + f)
    if fails:
        return 1
    print("  VERDICT: PASS (%d bras, vainqueur natif stable = u%s)"
          % (len(rows), sorted(winners)[0]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--hp-ahriman", type=int, default=100,
                    help="PV de thousAhriman : bas -> sa PREVIEW ecrase celle de blackAbaddon, "
                         "ce qui rend le bras discriminant (V3)")
    a = ap.parse_args()
    rid = build(a.hp_ahriman) if a.build else _runner_id()
    rows = [measure(rid, "hp(%s)=%s" % (LO_VID, a.hp_ahriman), swap=False),
            measure(rid, "hp(%s)=%s" % (LO_VID, a.hp_ahriman), swap=True)]
    return verdict(rows)


if __name__ == "__main__":
    raise SystemExit(main())
