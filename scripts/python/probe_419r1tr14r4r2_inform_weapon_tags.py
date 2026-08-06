#!/usr/bin/env python
"""Probe #419-r1-tr14-r4-r2 -- CONFRONTATION LIVE des trois tags d'`InformWeapon`.

`IdunBattleLogic.Entities.DSLBehaviors$$InformWeapon(damageProfileType, isMelee, useSpecial)`
construit un `Dictionary<TagKey,int>` puis l'emballe dans un
`IdunBattle.Entities.Behaviours.InformBehaviour`. Ce dictionnaire part vers
`IdunBattle.Operations.InformOperation$$Execute`, qui le dispatche en `StepType.Info` --
DONC LES TROIS CLES SONT DIRECTEMENT OBSERVABLES DANS LE FLUX. C'est ce que ce probe mesure.

Les cles, LUES dans `data/symbols/<CURRENT>/frida/enums.tsv` (`IdunBattle.Streams.TagKey`) :

    0x93 Attack_Weapon_DamageProfile = damageProfileType.HasValue ? (int)value : -1   INCONDITIONNEL
    0x92 Attack_Weapon_IsMelee       = le 2e argument `isMelee`                       INCONDITIONNEL
    0x94 Attack_Weapon_Use_Special   = le 3e argument `useSpecial`                    SI NON NUL

LE DISCRIMINANT (et la raison de mesurer DEUX porteurs) : `isMelee` n'est PAS une constante du
noeud, c'est un LITTERAL DE CHAQUE APPELANT, et il DIFFERE --
`FlailSwingAbility$$ExecuteBehaviour` passe `CONCAT71(..., 1)` = **1**, quand
`SentinelDirectivesAbility$$ExecuteBehaviour` passe `(void *)0x0` = **0**. Un probe qui ne
mesurerait qu'un seul porteur ne pourrait pas distinguer « le port lit le litteral » de « le port
ecrit une constante » : l'etape [3] ASSERTIONNE donc que les deux valeurs natives DIFFERENT
(anti-regime-degenere), et rougit si le montage rend deux fois la meme chose.

Ce que CE probe ne montre pas : un porteur a `useSpecial != 0`. Sur les 6 xrefs de la surcharge a
3 arguments, **5** passent le litteral `0` et la sixieme
(`OptimizedGait_TriggerAttackAbility$$CreateBehaviour`, `useSpecial = HasEffect(target, 0x4e2)`)
est DYNAMIQUE et non portee -- la cle `0x94` est donc ABSENTE du flux des deux porteurs mesures
ici, et cette absence est VERIFIEE comme une PREDICTION du port, pas contournee : etape [2c].

⚠ « Le probe ne peut PAS montrer » ne veut PAS dire « le natif ne la pose jamais » : sur l'AUTRE
voie (`ALoki_NormalAttackAbility$$ExecuteInformWeapon`, 9 appelants), **DEUX** sites la posent au
litteral `1`, et `FeederTendrils` en charge a ete CONFRONTE -- le flux ecrit alors
`Tag=Attack_Weapon_Use_Special:1`. Detail et port : `probe_419r1tr14r4r2r1_normal_attack_
inform_weapon.py`, `case-419-r1-tr14-r4-r2-inform-weapon-tags.md` §6.

ASCII only (cp1252). Usage: python probe_419r1tr14r4r2_inform_weapon_tags.py [--seed N]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
import stream_events as SE  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.dsl.effects import ExecutionContext  # noqa: E402
from engine.streams.tag_key import TagKey  # noqa: E402
from engine.runner.abilities.deathguard import flail_swing_tree  # noqa: E402
from engine.runner.abilities.admec import sentinel_directives_tree  # noqa: E402
from engine.runner.abilities.behaviours.combat import InformWeapon  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
BOARD = "MC1_67"

# (visualId du porteur, ability, litteral `isMelee` LU au decompile, profil LU au gameconfig, portee)
#   `FlailSwingAbility$$ExecuteBehaviour`          -> InformWeapon(profile, CONCAT71(..,1), 0)
#   `SentinelDirectivesAbility$$ExecuteBehaviour`  -> InformWeapon(profile, (void*)0x0,     0)
PORTEURS = [
    {"vis": "admecDestroyer", "ability": 1139, "nom": "SentinelDirectives",
     "is_melee": False, "profil": "Physical", "contact": False},
    {"vis": "deathBlightlord", "ability": 1042, "nom": "FlailSwing",
     "is_melee": True, "profil": "Power", "contact": True},
]


def _r(sid, method, body, t=120):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _tags(ev) -> dict:
    try:
        return json.loads(ev.get("tags") or "{}")
    except Exception:
        return {}


def _cascade(r) -> list:
    out = list(r.get("cascade") or [])
    for a in (r.get("actions") or []):
        out += list(a.get("events") or [])
    return out


def _find(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def build(seed: int):
    sf = ROOT / "logs" / "runners" / f"iw-tags-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", BOARD, "--roster", "1",
         "--p-units", ",".join(p["vis"] for p in PORTEURS),
         "--a-units", "necroWarden,necroWarden,necroWarden",
         "--hp-target", "400000", "--hp-player", "400000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print(f"[iw] build KO: {(proc.stderr or proc.stdout or '')[-400:]}")
        return None, None
    return int(json.loads(sf.read_text())["runnerId"]), sf


def _mon_tour(rpc, rid, vis):
    for _ in range(20):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        u = _find(dv, vis)
        if u is None:
            return None, None
        if dv.get("currentPlayer") == u.get("owner"):
            return dv, u
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _place(rpc, rid, board, dv, caster, contact: bool):
    """DRIVE les positions (`applyAction move` ignore portee et propriete) : parque tous les
    ennemis LOIN, puis pose UNE cible soit au CONTACT (melee), soit a distance EXACTEMENT 2
    (ranged -- desactive au contact). Rend l'id de la cible, ou None."""
    myp = caster.get("owner")
    cpos = _pos(caster)
    ctile = board.id_at(*cpos)
    enemies = [u for u in (dv.get("units") or []) if u.get("alive") and u.get("owner") != myp]
    if not enemies:
        return None
    tgt, autres = enemies[0], enemies[1:]
    far = [t for t in sorted(board.by_id)
           if board.walkable(t) and hexgeo.distance(board.coord(t), cpos) > 5]
    it = iter(far)
    for e in autres:
        ft = next(it, None)
        if ft is None:
            break
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": e["id"],
            "to": {"col": board.coord(ft)[0], "row": board.coord(ft)[1]}}}, 60)
    if contact:
        cands = [n for n in board.neighbours(ctile) if board.walkable(n)]
    else:
        cands = [t for t in sorted(board.by_id)
                 if board.walkable(t) and hexgeo.distance(board.coord(t), cpos) == 2]
    for t in cands:
        tc = board.coord(t)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": tgt["id"], "to": {"col": tc[0], "row": tc[1]}}}, 60)
        dv2 = rpc("decisionView", {"runnerId": rid}, 90)
        t2 = next((u for u in (dv2.get("units") or []) if u.get("id") == tgt["id"]), None)
        if t2 is not None and _pos(t2) == tc:
            return tgt["id"]
    return None


def _tags_info_du_cast(cast) -> list:
    """Les dicts de tags des pas `StepType.Info` de la cascade qui portent un
    `Attack_Weapon_DamageProfile` -- c'est-a-dire ceux emis par `InformOperation$$Execute`."""
    s_info = SE.step_id("Info")
    out = []
    for ev in _cascade(cast):
        if ev.get("step") != s_info:
            continue
        t = _tags(ev)
        if "Attack_Weapon_DamageProfile" in t:
            out.append(t)
    return out


def _tags_du_port(tree) -> dict:
    """Rejoue l'arbre DSL PORTE hors ligne et rend le dict de tags que sa feuille `InformWeapon`
    pose. On n'execute QUE la feuille (les autres exigent un `state`), en la retrouvant dans
    l'arbre -- donc la valeur mesuree est bien celle que le port a CABLEE au site."""
    feuille = _feuille_inform(tree)
    assert feuille is not None, "aucune feuille InformWeapon dans l'arbre porte"
    ctx = ExecutionContext(state=None, rng=None)
    feuille.execute(None, ctx)
    return dict(next(p["tags"] for n, p in ctx.emitted if n == "InformWeapon"))


def _feuille_inform(node):
    if isinstance(node, InformWeapon):
        return node
    for attr in ("left", "right", "a", "b", "first", "second", "nodes", "children"):
        v = getattr(node, attr, None)
        if v is None:
            continue
        for sub in (v if isinstance(v, (list, tuple)) else [v]):
            f = _feuille_inform(sub)
            if f is not None:
                return f
    return None


# MESURE LIVE du 2026-08-06 (runner MC1_67, seed 41902, session Frida 1) -- figee pour que la
# CONTRE-EPREUVE s'exerce sans re-monter un runner. Le flux natif ne porte que DEUX cles : c'est
# la prediction `useSpecial == 0` de l'etape [2c], verifiee et non contournee.
MESURE_NATIVE = {
    "SentinelDirectives": {"Attack_Weapon_DamageProfile": 0, "Attack_Weapon_IsMelee": 1 - 1},
    "FlailSwing": {"Attack_Weapon_DamageProfile": 14, "Attack_Weapon_IsMelee": 1},
}


def _confronter(natif: dict, porte: dict, prefixe: str = "iw", bavard: bool = True) -> int:
    """Le controle, PARTAGE par le mode live et la contre-epreuve : [1] les deux cles
    inconditionnelles concordent, [2c] la conditionnelle est absente des deux cotes, [3] les deux
    porteurs DIFFERENT sur `IsMelee` (anti-regime-degenere). Rend le nombre d'ecarts."""
    ko = 0
    for nom, t in natif.items():
        p = porte[nom]
        for cle in (TagKey.Attack_Weapon_DamageProfile, TagKey.Attack_Weapon_IsMelee):
            v_nat, v_port = t.get(cle.name), p.get(cle)
            etat = "OK" if v_nat is not None and v_port is not None and int(v_nat) == int(v_port) else "KO"
            ko += (etat == "KO")
            if bavard:
                print(f"[{prefixe}][1] {nom:20s} {cle.name:30s} natif={v_nat} port={v_port} {etat}")
    for nom, t in natif.items():
        n_abs = TagKey.Attack_Weapon_Use_Special.name not in t
        p_abs = TagKey.Attack_Weapon_Use_Special not in porte[nom]
        etat = "OK" if (n_abs and p_abs) else "KO"
        ko += (etat == "KO")
        if bavard:
            print(f"[{prefixe}][2c] {nom:20s} Use_Special absente natif={n_abs} port={p_abs} {etat}")
    if len(natif) == 2:
        vals = {n: int(t.get(TagKey.Attack_Weapon_IsMelee.name, -99)) for n, t in natif.items()}
        etat = "OK" if len(set(vals.values())) == 2 else "KO"
        ko += (etat == "KO")
        if bavard:
            print(f"[{prefixe}][3] discriminant IsMelee natif {vals} (doivent DIFFERER) {etat}")
    else:
        if bavard:
            print(f"[{prefixe}][3] NON CONFRONTE -- {len(natif)}/2 porteurs, le discriminant exige les DEUX")
        ko += 1
    return ko


def _porte_courant() -> dict:
    return {"FlailSwing": _tags_du_port(flail_swing_tree()),
            "SentinelDirectives": _tags_du_port(sentinel_directives_tree())}


def contre_epreuve() -> int:
    """Chaque mutation doit MORDRE (changer la sortie du port) PUIS faire ROUGIR le controle.
    `a_mordu` est publie SEPAREMENT du verdict : une mutation NON EXERCEE se declare, elle ne se
    compte pas verte.

    ⚠ M4b est INERTE PAR ALGEBRE, et c'est MESURE, pas subi : sur `SentinelDirectives` le profil
    `Physical` vaut 0 et `isMelee` vaut 0 -- intervertir 0x92 et 0x93 (la faute EXACTE de l'ancienne
    docstring) ne change donc RIEN sur ce porteur. C'est pourquoi le controle a besoin de
    `FlailSwing` (14 vs 1), ou la meme mutation mord. On assertionne l'equivalence DANS LES DEUX
    SENS : M4b ne doit PAS mordre, M4a doit mordre."""
    base = _porte_courant()
    ref_ko = _confronter(MESURE_NATIVE, base, prefixe="ce-ref", bavard=False)
    print(f"[ce] reference (port intact) ecarts={ref_ko} -> {'PASS' if ref_ko == 0 else 'FAIL'}")
    if ref_ko:
        print("[ce] ABANDON : la reference ne passe pas, une mutation ne prouverait rien")
        return 1

    def _mute_feuille(nom_arbre, **kw):
        tree = flail_swing_tree() if nom_arbre == "FlailSwing" else sentinel_directives_tree()
        f = _feuille_inform(tree)
        for k, v in kw.items():
            setattr(f, k, v)
        ctx = ExecutionContext(state=None, rng=None)
        f.execute(None, ctx)
        out = dict(base)
        out[nom_arbre] = dict(next(p["tags"] for n, p in ctx.emitted if n == "InformWeapon"))
        return out

    def _mute_interversion(nom_arbre):
        """La faute de l'ancienne docstring, appliquee au CODE : 0x92 <- profil, 0x93 <- isMelee."""
        out = dict(base)
        src = base[nom_arbre]
        out[nom_arbre] = {TagKey.Attack_Weapon_DamageProfile: src[TagKey.Attack_Weapon_IsMelee],
                          TagKey.Attack_Weapon_IsMelee: src[TagKey.Attack_Weapon_DamageProfile]}
        return out

    def _mute_use_special_inconditionnelle(nom_arbre):
        out = dict(base)
        out[nom_arbre] = dict(base[nom_arbre])
        out[nom_arbre][TagKey.Attack_Weapon_Use_Special] = 0    # posee meme a `useSpecial == 0`
        return out

    mutations = [
        ("M1 FlailSwing isMelee 1->0", lambda: _mute_feuille("FlailSwing", is_melee=False), True),
        ("M2 SentinelDir isMelee 0->1", lambda: _mute_feuille("SentinelDirectives", is_melee=True), True),
        ("M3 Use_Special inconditionnelle", lambda: _mute_use_special_inconditionnelle("FlailSwing"), True),
        ("M4a interversion 0x92/0x93 FlailSwing", lambda: _mute_interversion("FlailSwing"), True),
        ("M4b interversion 0x92/0x93 SentinelDir", lambda: _mute_interversion("SentinelDirectives"), False),
    ]
    ko = 0
    for nom, faire, mord_attendu in mutations:
        mute = faire()
        a_mordu = any(mute[n] != base[n] for n in base)
        ecarts = _confronter(MESURE_NATIVE, mute, prefixe="ce", bavard=False)
        rougit = ecarts > 0
        # verdict : une mutation qui doit mordre DOIT mordre ET faire rougir ; une mutation
        # algebriquement inerte NE doit PAS mordre (et donc ne pas rougir).
        ok = (a_mordu == mord_attendu) and (rougit == mord_attendu)
        ko += (not ok)
        print(f"[ce] {nom:42s} a_mordu={a_mordu!s:5s} (attendu {mord_attendu!s:5s}) "
              f"rougit={rougit!s:5s} ecarts={ecarts} {'OK' if ok else 'KO'}")
    print(f"[ce] BILAN CONTRE-EPREUVE: {'PASS' if ko == 0 else 'FAIL'} ({ko} ecart(s))")
    return 0 if ko == 0 else 1


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=41902)
    ap.add_argument("--contre-epreuve", action="store_true",
                    help="mutations hors ligne contre la MESURE_NATIVE figee (aucun runner)")
    args = ap.parse_args(argv)

    if args.contre_epreuve:
        return contre_epreuve()

    sid = _resolve_session()
    rid, sf = build(args.seed)
    if rid is None:
        return 2

    def rpc(m, b, t=120):
        return _r(sid, m, b, t)

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (bg or {}).get("tiles"):
        print("[iw] NON CONFRONTE -- boardGraph indispo")
        return 2
    board = Board(bg["tiles"], adjacency="native_sym")
    natif = {}
    try:
        for p in PORTEURS:
            dv, caster = _mon_tour(rpc, rid, p["vis"])
            if caster is None:
                print(f"[iw] {p['nom']}: NON CONFRONTE -- tour/unite indisponible")
                continue
            tid = _place(rpc, rid, board, dv, caster, p["contact"])
            if tid is None:
                print(f"[iw] {p['nom']}: NON CONFRONTE -- geometrie non montable")
                continue
            cast = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": caster["id"], "targetId": tid,
                "abilityType": p["ability"]}, "captureEvents": True}, 180)
            if not (isinstance(cast, dict) and cast.get("ok")):
                print(f"[iw] {p['nom']}: NON CONFRONTE -- cast refuse: "
                      f"{str(cast)[:200]}")
                continue
            infos = _tags_info_du_cast(cast)
            if not infos:
                print(f"[iw] {p['nom']}: NON CONFRONTE -- aucun pas Info porteur")
                continue
            natif[p["nom"]] = infos[0]
            print(f"[iw] {p['nom']} natif -> {json.dumps(infos[0], sort_keys=True)}")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
        if sf is not None:
            Path(sf).unlink(missing_ok=True)

    ko = _confronter(natif, _porte_courant())
    # garde de non-derive : la mesure du jour doit reproduire celle qu'a figee `MESURE_NATIVE`.
    for nom, t in natif.items():
        attendu = MESURE_NATIVE.get(nom)
        if attendu is not None and t != attendu:
            ko += 1
            print(f"[iw][4] {nom}: le flux natif a DERIVE depuis la mesure figee "
                  f"{attendu} -> {t} (la contre-epreuve hors ligne est PERIMEE)")
    print(f"[iw] BILAN: {'PASS' if ko == 0 else 'FAIL'} ({ko} ecart(s))")
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
