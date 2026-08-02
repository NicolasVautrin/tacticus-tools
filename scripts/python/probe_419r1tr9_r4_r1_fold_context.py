"""#419-r1-tr9-r4-r1 -- QUEL `AbilityOrEffect` le fold additional-damage passe-t-il a `GetAttackHits` ?

LA QUESTION. `IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$GetAdditionalDamagePrediction`
construit un `AbilityOrEffect` et le passe au slot `0xb5` de l'`IBattleQuery`
(`IdunBattle.Core.Services.BattleQuery$$GetAttackHits`, surcharge `ability:IdunBattle.Core.AbilityOrEffect`).
Le residu #419-r1-tr9-r4-r1 affirmait que ce contexte est celui du PASSIF de fold, et que le port --
qui reutilise les arguments de coups de l'ATTAQUE PORTEUSE (donc `is_normal_attack=True`) -- divergeait.

CE QUE LE DECOMPILE TRANCHE (et que ce probe CONFRONTE). La signature reelle est
`GetAdditionalDamagePrediction(entities:AbilityEntities, abilityState:AbilityState)` -- ghidra INVERSE
les noms (son `entities` est le `this` de l'ability, son `abilityState` est le vrai `entities`, et le
vrai `abilityState` est un 4e argument qu'il ne montre pas). L'`AbilityOrEffect` sort de
`IdunBattle.Core.AbilityOrEffect$$op_Implicit` (surcharge `activeAbility` -> `set_ActiveAbility`)
applique a CE parametre `abilityState` -- que `Boltstorm_NormalAttackAbility$$PredictAttack` recopie
depuis SON PROPRE parametre avant de le retransmettre. Le contexte du fold est donc celui de
l'ATTAQUE PORTEUSE, pas celui d'un passif.

CE QUE CE PROBE MESURE, SANS LE PORT. `IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack` finit sur
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularAttack`,
evalue sur l'`ActiveAbilityType` porte par cet `AbilityOrEffect`. Un effet dont le bonus de coups est
gate `IsNormalAttack` discrimine donc les deux lectures :

  * contexte = attaque porteuse -> `IsRegularAttack(<attaque normale>)` VRAI  -> le fold gagne le coup ;
  * contexte = passif           -> `IsRegularAttack(<passif>)`          FAUX  -> le fold ne le gagne pas.

Le porteur du gate : `IdunBattle.Entities.Effects.Loki.PowerTrip_FullHealthEffect$$CreateEffectHitsBonusForAttack`
= `EffectBonus.ForAddition(IsNormalAttack & get_OwnerIsCaster, Direct(GetNumberConstant(0x2b)))`, soit
`extraHit = 1` tant que le porteur est a PV pleins (`$$CreateActiveCondition` = `!IsDamaged`).

LE MONTAGE (la fiche le disait NON CONFRONTE faute de porteur cumulant). `PowerTrip` (1285) est le
passif d'`orksKillaKan` et `Boltstorm` (1090) celui de `templAggressor` : aucune unite ne les cumule.
On GREFFE donc `PowerTrip` sur `templAggressor` -- `case-92` §5bis, volet PASSIF, outille par
`catalog_inject.graft_passive_ability`. Les QUATRE bras partagent le MEME catalogue (la config
`PowerTrip` est posee dans les quatre) et ne different QUE par `BC.Units[templAggressor].PassiveAbilities` :

    fold_pt = [1090, 1285]     base_pt = [1285]     fold = [1090]     base = []

    fold_natif(sans PT) = fold    - base
    fold_natif(avec PT) = fold_pt - base_pt
    VERDICT = fold_natif(avec PT).hits - fold_natif(sans PT).hits   -> +1 = attaque porteuse, 0 = passif

Les quatre mesures sont NATIVES : le port n'entre pas dans la definition du verdict. Le port est
mesure en plus, sur chaque bras, pour verifier qu'il suit.

ATTESTATION DU MONTAGE (jamais un vert silencieux) : `base_pt.hits - base.hits` DOIT valoir `+1` --
c'est la preuve que la greffe a MORDU sur la base. S'il vaut 0, PowerTrip n'est pas actif et le
verdict du fold ne veut rien dire -> `MontageError`. De meme, l'attaque normale CONCRETE doit valoir
`1128` dans les bras `fold*` et autre chose dans les bras `base*`.

    python probe_419r1tr9_r4_r1_fold_context.py --state-file <ABS>
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import catalog_inject as CI                                       # noqa: E402
import probe_124_line_elevation_decision as P124                  # noqa: E402
import probe_419r1tr9_r4_boltstorm_pred as P419                   # noqa: E402
from probe_419r1tr9_r4_boltstorm_pred import MontageError         # noqa: E402

BOARD = P419.BOARD
SEED = P419.SEED
CASTER = P419.CASTER                       # `templAggressor`, passif `Boltstorm` (1090)
FOES = P419.FOES
HP = P419.HP
GRAFT = "PowerTrip"                        # 1285 -- passif d'`orksKillaKan`
REGIME = "plain"                           # 3 cibles a distance 2, meme elevation, hors cover :
                                           # AUCUN malus de coups en jeu -> le +1 de PowerTrip est
                                           # le SEUL terme qui bouge d'un bras a l'autre.
# `BC.Units[CASTER].PassiveAbilities` de chaque bras. L'ordre compte : `fold_pt` est joue en premier
# et FIXE la geometrie que les trois autres rejouent (appariee par `visualId`).
ARMS = ("fold_pt", "base_pt", "fold", "base")


def arm_passives(arm: str) -> list:
    bolt, pt = CI.triggered_ability_id("Boltstorm"), CI.triggered_ability_id(GRAFT)
    return {"fold_pt": [bolt, pt], "base_pt": [pt], "fold": [bolt], "base": []}[arm]


# --------------------------------------------------------------------------- montage

def write_arm_bc(out_path: str, arm: str) -> str:
    """Ecrit le seed BC du bras. La greffe pose la config `PowerTrip` dans
    `BC.Abilities.PassiveAbilities` (sans elle : « system error », meme verrou que #226/#237) ; la
    liste par unite est ensuite REECRITE a la valeur du bras. Les quatre fichiers ne different donc
    QUE par cette liste."""
    bc = CI._load_seed(None)
    CI.graft_passive_ability(bc, CASTER, GRAFT, replace=False)     # pose la config + [1090, 1285]
    want = arm_passives(arm)
    hits = [u for u in (bc.get("Units") or []) if u.get("Id") == CASTER]
    if not hits:
        raise MontageError(f"{CASTER} absent de BC.Units")
    for u in hits:
        u["PassiveAbilities"] = list(want)
    node = (bc.get("Abilities") or {}).get("PassiveAbilities") or {}
    if GRAFT not in node:
        raise MontageError(f"config {GRAFT} absente de BC.Abilities.PassiveAbilities")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(bc, fh)
    return out_path


def build_args(bc_path: str) -> list:
    """Arguments `rl_duel build` d'un bras, SANS `--seed` ni `--state-file` -- meme forme que
    `probe_419r1tr9_r4_boltstorm_pred.build_args`, pour que la garde jumelle puisse les passer
    telles quelles a la fixture `build_runner`."""
    stats = ";".join(f"{v}:Health={HP},RemainingHealth={HP}" for v in (CASTER,) + FOES)
    return ["--board", BOARD, "--seed-bc", bc_path, "--p-units", CASTER,
            "--a-units", ",".join(FOES), "--unit-stat", stats]


def build_arm(state_file: str, bc_path: str) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            *build_args(bc_path), "--state-file", state_file]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def dispose(state_file: str) -> None:
    subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", state_file],
                   cwd=_HERE, capture_output=True, text=True)


# ------------------------------------------------------- contre-epreuve : le port en contexte PASSIF

def port_fields_ctx_passive(scene, cid, tgt, tile) -> dict:
    """MUTANT `ctx_passive` -- le port sous l'HYPOTHESE DU RESIDU : le fold passerait a la facade de
    coups le contexte du PASSIF, donc `IsNormalAttack` FAUX. C'est le seul bras qui prouve que ce
    probe SAIT rougir : sans lui, l'accord port/natif ne distingue pas « le port modelise le
    contexte » de « le port ignore ce noeud ».

    Le port ne pose pas la cle `is_normal_attack` dans `_hits_kw` (il prend le defaut `True`) : on
    l'injecte donc au passage du fold, la ou le residu la voulait fausse."""
    import engine.playbook.prediction.normal_attack as NA
    saved = NA.get_additional_damage_prediction

    def _passive_ctx(*a, **k):
        hc = k.get("hits_ctx")
        if hc is not None:
            k = {**k, "hits_ctx": {**hc, "is_normal_attack": False}}
        return saved(*a, **k)

    NA.get_additional_damage_prediction = _passive_ctx
    try:
        return P419.port_fields(scene, cid, tgt, tile, fold=True)
    finally:
        NA.get_additional_damage_prediction = saved


# --------------------------------------------------------------------------- mesure d'un bras

def run_arm(sid, rpc, rid: int, arm: str, layout: dict | None) -> dict:
    """Monte la geometrie (celle de `layout` si fournie, sinon la cherche) et rend, par cible, la
    prediction NATIVE et celle du PORT. `layout` = `{visualId: tuile}` + `{"C": tuile du caster}`."""
    elev, walk, _tid = P124._board(sid, rid)
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    dv, _pos = P124._positions(sid, rid)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mine = [u for u in units if u.get("ctrl")]
    if not mine:
        raise MontageError(f"[{arm}] montage NON INSTALLE : aucune unite controlee")
    cid, myplayer = mine[0]["id"], mine[0]["owner"]
    vis_uid = {}
    for vis in FOES:
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"[{arm}] montage NON INSTALLE : {vis} absent du roster adverse")
        vis_uid[vis] = u["id"]

    if layout is None:
        _dv0, ctx0 = P419._fresh_ctx(rpc, rid, cid)
        tid = P419._terrain_map(ctx0.scene, cells)
        C, want_vis = P419._find_layout(cells, elev, walk, tid, REGIME)
        if C is None:
            raise MontageError(f"montage NON INSTALLE : aucune geometrie `{REGIME}` sur {BOARD}")
        layout = {"C": C, **want_vis}
    C = layout["C"]
    want = {cid: C}
    want.update({vis_uid[v]: layout[v] for v in FOES})
    if not P124._drive_to(sid, rid, walk, elev, want):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"[{arm}] montage NON INSTALLE : placement incomplet -- voulu {want}, "
                           f"obtenu { {u: pos.get(u) for u in want} }")
    P124._give_turn_back(sid, rid, myplayer)

    dv, ctx = P419._fresh_ctx(rpc, rid, cid)
    if ctx.origin != C:
        raise MontageError(f"[{arm}] montage NON INSTALLE : le caster est en {ctx.origin}, voulu {C}")
    ab = P419._normal_ability_id(rpc, rid, cid)
    rows = {}
    for vis in FOES:
        uid = vis_uid[vis]
        nat = P419.native_fields(rpc, rid, cid, uid, ab, C)
        prt = P419.port_fields(ctx.scene, cid, uid, C, fold=True)
        # Le port dispatche le fold par le KIT GAMECONFIG (`GC.unit_abilities(visualId)`), que le
        # bras `base*` ne touche PAS : il folde donc meme la ou le natif ne folde plus. Ce n'est pas
        # une divergence -- c'est le protocole de mesure de #446-r1 SS4 (retirer le passif du BC pour
        # rendre la base NATIVE mesurable). On neutralise le registre cote port pour l'apparier,
        # exactement comme `probe_419r1tr9_r4_boltstorm_pred.port_fields(fold=False)`.
        prt_base = P419.port_fields(ctx.scene, cid, uid, C, fold=False)
        rows[vis] = {"uid": uid, "native": nat, "port": prt, "port_base": prt_base,
                     "port_fold": P419._sub(prt, prt_base),
                     "port_mut": port_fields_ctx_passive(ctx.scene, cid, uid, C)}
    eff = [e.name for e in (ctx.scene.effects(cid) or [])]
    return {"arm": arm, "rid": rid, "cid": cid, "C": C, "ab": ab, "rows": rows,
            "caster_effects": eff, "layout": layout}


# --------------------------------------------------------------------------- verdict

def verdict(res: dict) -> dict:
    """`fold(avec PT) - fold(sans PT)` sur le compte de coups, par cible. `+1` = le contexte du fold
    est celui de l'ATTAQUE PORTEUSE (`IsNormalAttack` VRAI) ; `0` = celui du passif."""
    out = {"per_target": {}, "attest": {}}
    for vis in FOES:
        n = {a: res[a]["rows"][vis]["native"] for a in ARMS}
        fold_pt = n["fold_pt"]["hits"] - n["base_pt"]["hits"]
        fold = n["fold"]["hits"] - n["base"]["hits"]
        base_gain = n["base_pt"]["hits"] - n["base"]["hits"]
        out["per_target"][vis] = {
            "hits": {a: n[a]["hits"] for a in ARMS},
            "fold_hits_with_pt": fold_pt, "fold_hits_without_pt": fold,
            "fold_gain": fold_pt - fold, "base_gain": base_gain,
            "raw": {a: (n[a]["rawMin"], n[a]["rawMax"]) for a in ARMS}}
    # MEME decomposition, cote PORT : son fold est `total - total(registre de fold vide)`, mesure
    # DANS le bras (aucun re-montage). Le port doit gagner le meme +1 que le natif.
    for vis in FOES:
        pf = {a: res[a]["rows"][vis]["port_fold"]["hits"] for a in ARMS}
        out["per_target"][vis]["port_fold_hits"] = pf
        out["per_target"][vis]["port_fold_gain"] = pf["fold_pt"] - pf["fold"]
    gains = {v: out["per_target"][v]["base_gain"] for v in FOES}
    folds = {v: out["per_target"][v]["fold_gain"] for v in FOES}
    out["attest"] = {"base_gain": gains, "installed": all(g == 1 for g in gains.values())}
    out["fold_gain"] = folds
    if not out["attest"]["installed"]:
        raise MontageError(
            f"montage NON INSTALLE : le +1 coup de {GRAFT} ne mord PAS sur la BASE "
            f"(base_pt - base = {gains}) -- le verdict du fold ne veut rien dire. "
            f"Verifier que l'effet PowerTrip_FullHealth est actif (PV pleins) et greffe.")
    if all(g == 1 for g in folds.values()):
        out["verdict"] = "ATTAQUE PORTEUSE"
    elif all(g == 0 for g in folds.values()):
        out["verdict"] = "PASSIF"
    else:
        out["verdict"] = f"INDETERMINE (gains heterogenes {folds})"
    return out


def port_agreement(res: dict) -> list:
    """Ecart port - natif sur chaque bras et chaque cible. Sur les bras `base*` (le passif RETIRE du
    BC), on apparie le port a registre de fold VIDE : le port, lui, dispatche par le gameconfig."""
    out = []
    for arm in ARMS:
        folds = CI.triggered_ability_id("Boltstorm") in arm_passives(arm)
        for vis in FOES:
            r = res[arm]["rows"][vis]
            n, p = r["native"], r["port"] if folds else r["port_base"]
            out.append({"arm": arm, "vis": vis, "folds": folds,
                        "d": (p["rawMin"] - n["rawMin"], p["rawMax"] - n["rawMax"],
                              p["hits"] - n["hits"]),
                        "nat": (n["rawMin"], n["rawMax"], n["hits"]),
                        "port": (p["rawMin"], p["rawMax"], p["hits"])})
    return out


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file (prefixe)")
    ap.add_argument("--keep", action="store_true", help="ne dispose pas les runners")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    stem = os.path.splitext(args.state_file)[0]
    bc_dir = os.path.join(_HERE, "..", "..", "logs", "probe_419r1tr9_r4_r1")
    res, layout = {}, None
    for arm in ARMS:
        st = f"{stem}_{arm}.json"
        bc = write_arm_bc(os.path.abspath(os.path.join(bc_dir, f"seed_{arm}.json")), arm)
        rid = build_arm(st, bc)
        try:
            res[arm] = run_arm(sid, rpc, rid, arm, layout)
            layout = res[arm]["layout"]
        finally:
            if not args.keep:
                dispose(st)
        r = res[arm]
        print(f"[{arm:<8}] runner {rid} | caster u{r['cid']} @ {r['C']} | attaque normale = {r['ab']}"
              f" | PassiveAbilities={arm_passives(arm)}")
        print(f"           effets du caster : {r['caster_effects']}")
        for vis in FOES:
            n, p = r["rows"][vis]["native"], r["rows"][vis]["port"]
            print(f"           {vis:<15} nat=({n['rawMin']}, {n['rawMax']}, h{n['hits']})  "
                  f"port=({p['rawMin']}, {p['rawMax']}, h{p['hits']})")

    # l'attaque normale CONCRETE doit basculer avec la presence de `Boltstorm` -- sinon les bras
    # `base*` ne sont pas des bras SANS fold et la difference ne mesure rien.
    if res["fold_pt"]["ab"] != res["fold"]["ab"]:
        raise MontageError(f"bras fold incoherents : ab {res['fold_pt']['ab']} vs {res['fold']['ab']}")
    if res["base_pt"]["ab"] != res["base"]["ab"]:
        raise MontageError(f"bras base incoherents : ab {res['base_pt']['ab']} vs {res['base']['ab']}")
    if res["fold_pt"]["ab"] == res["base_pt"]["ab"]:
        raise MontageError(f"montage NON INSTALLE : l'attaque normale vaut {res['fold_pt']['ab']} "
                           f"dans les DEUX familles de bras -- `PassiveAbilities` n'a pas mordu")

    v = verdict(res)
    print("\n=== VERDICT ===")
    print(f"  attestation : base_pt - base = {v['attest']['base_gain']} "
          f"(le +1 coup de {GRAFT} MORD sur la base)")
    for vis in FOES:
        d = v["per_target"][vis]
        print(f"  {vis:<15} hits {d['hits']} | fold sans PT = {d['fold_hits_without_pt']} | "
              f"fold avec PT = {d['fold_hits_with_pt']} | GAIN natif = {d['fold_gain']:+d} | "
              f"GAIN port = {d['port_fold_gain']:+d}")
    print(f"  -> contexte du fold = {v['verdict']}")

    print("\n=== ACCORD PORT/NATIF (par bras) ===")
    bad = 0
    for row in port_agreement(res):
        ok = row["d"] == (0, 0, 0)
        bad += 0 if ok else 1
        print(f"  [{row['arm']:<8}] {row['vis']:<15} nat={row['nat']} port={row['port']} "
              f"d={row['d']} {'OK' if ok else 'DIVERGE'}")
    print(f"  {bad} divergence(s) port/natif")
    port_ok = all(v["per_target"][x]["port_fold_gain"] == 1 for x in FOES)
    if not port_ok:
        print("  ! le PORT ne gagne pas le +1 sur son fold : "
              + str({x: v["per_target"][x]["port_fold_gain"] for x in FOES}))

    # CONTRE-EPREUVE : le mutant `ctx_passive` doit DEPLACER le port -- et seulement la ou un bonus
    # gate `IsNormalAttack` est en jeu (bras `*_pt`). S'il ne mord nulle part, ce probe ne teste rien.
    print("\n=== CONTRE-EPREUVE `ctx_passive` (le port sous l'hypothese du residu) ===")
    bites = {}
    for arm in ARMS:
        for vis in FOES:
            r = res[arm]["rows"][vis]
            m, p = r["port_mut"], r["port"]
            d = (m["rawMin"] - p["rawMin"], m["rawMax"] - p["rawMax"], m["hits"] - p["hits"])
            bites[(arm, vis)] = d
            print(f"  [{arm:<8}] {vis:<15} deplacement du port {d} "
                  f"{'MORD' if any(d) else 'ne mord pas'}")
    mut_ok = (all(any(bites[("fold_pt", v)]) for v in FOES)
              and not any(any(bites[("fold", v)]) for v in FOES))
    print(f"  mutant {'DISCRIMINANT' if mut_ok else 'NON DISCRIMINANT'} "
          f"(doit mordre sur `fold_pt`, pas sur `fold`)")
    return 0 if (v["verdict"] == "ATTAQUE PORTEUSE" and bad == 0 and port_ok and mut_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
