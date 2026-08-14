"""#1035-r2 -- MESURE LIVE du BONUS de `BlightedLand_ExtraDamagePct` (1442), en regime SEPARANT.

QUESTION BINAIRE : le natif applique-t-il `+extraDmgPct %` au degat d'un ami **Mythique** de la MoW
`deathCrawler` qui attaque depuis une tuile **Contaminee** -- et le PORT rend-il la MEME chose, en
s'eteignant aux memes endroits ?

i2 `Abilities/BlightedLand_CurrentLevelDescription` : << Friendly **Mythic** characters deal
+{extraDmgPct}% Damage while on a **Contaminated** hex. >>

COMMENT LA TUILE DEVIENT CONTAMINEE, ET POURQUOI C'EST LA MEME MoW. `deathCrawler` porte l'ACTIVE
`PlagueburstMortar` (1169), dont
`IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$ExecuteBehaviour` finit par
`AddEffect(0x4dc = 1244 Contaminated, <tuile ciblee> + <nrOfTiles tirees>)`. Le montage n'a donc
besoin d'AUCUNE unite tierce : la porteuse de l'aura fabrique elle-meme le terrain que son aura
lit. La tuile ciblee est le PREMIER terme de l'union, donc DETERMINISTE (les autres sont tirees).

GEOMETRIE FORCEE (`--place` / `--a-place`) -- jamais << bloque par la geometrie de spawn >> :

        (2,3) orksNob      -- l'ATTAQUANT, ami de la MoW ; sa tuile sera CONTAMINEE
        (3,4) necroWarden  -- la CIBLE
        hors plateau       -- `deathCrawler`, PORTEUSE de l'aura (aucune position)

TROIS BRAS :

  `on`      mythique EQUIPEE + mortier tire     -> bonus ATTENDU
  `off`     mortier tire, PAS de `--equip-mythic` -> l'effet n'existe pas (BASE)
  `rarity`  mythique EQUIPEE + mortier tire, attaquant force a `Rarity.Epic`
                                                -> `UnitsWithRarity(..., Mythic)` FAUX

⚠ Le bras `off` TIRE QUAND MEME LE MORTIER, et ce n'est pas un detail : sans cela il differerait du
bras `on` par DEUX choses (l'aura ET l'etat du terrain, `Contaminated_Unit` compris, qui reduit
l'armure de l'occupant). L'ecart mesure ne serait alors plus imputable a l'aura seule.

⚠ Le TEMOIN NON NUL est le couple `on`/`rarity` : la MEME unite, sur la MEME tuile contaminee, est
PRISE quand elle est Mythique et ECARTEE quand elle est Epic. Dans le regime PAR DEFAUT du harnais
(`targetRarity = 5` partout) ce gate est uniformement VRAI et un vert n'y separerait RIEN.

⚠ MONTAGE : `elev_by_pos` ET `tile_effects_by_pos` sont threades dans la `Scene`, comme le fait
`engine/ai/context.py`. Les omettre est un vice de HARNAIS, MESURE ici : sans eux la sonde rendait
4341 cote port contre 4773 cote natif -- une fausse divergence de 10 % due au seul montage.

Discipline runner : `--state-file` ABSOLU sous `logs/`, runner DISPOSE en sortie de chaque bras
(sauf `--keep`). On ne dispose JAMAIS le runner d'un autre agent. ASCII only.

Usage :
    python probe_1035r2_blighted_land_bonus_live.py            # les trois bras
    python probe_1035r2_blighted_land_bonus_live.py --arm on --keep
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import rl_duel as R                                                            # noqa: E402
import rl_collect_batch as B                                                   # noqa: E402
from engine.entities.effect_type import EffectType                             # noqa: E402

BOARD = "MC1_67"
SEED = 777
MOW = "deathCrawler"
ATT = "orksNob"            # l'ATTAQUANT, ami de la MoW
FOE = "necroWarden"        # la CIBLE
POS_ATT, POS_FOE = (2, 3), (3, 4)
#: La tuile visee par `PlagueburstMortar` -- premier terme de l'union `Contaminated`, DETERMINISTE.
POS_MORTIER = (3, 3)
#: `ActiveAbilityType.PlagueburstMortar` -- l'active de `deathCrawler` qui pose `Contaminated`.
MORTIER = 1169
#: `EffectType` 0x4dc = 1244 -- l'effet de TUILE que lit `UnitsOnTilesWithEffect`.
CONTAMINATED = EffectType.Contaminated.name
RARETE_NON_MYTHIC = 3      # `idun.meta.Rarity.Epic`

#: Les trois bras : (equip_mythic, {visualId: rarete forcee}).
ARMS = {
    "on":     (True,  {}),
    "off":    (False, {}),
    "rarity": (True,  {ATT: RARETE_NON_MYTHIC}),
}


def _unwrap(x):
    return x.get("result") if isinstance(x, dict) and "result" in x else x


def _state_file(nom: str) -> str:
    p = PYDIR.parents[1] / "logs" / ("probe1035r2_%s.json" % nom)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def dispose(res: dict) -> None:
    """Rend le runner du bras. Idempotent et silencieux."""
    rid = (res or {}).get("runnerId")
    if rid is None:
        return
    try:
        B._rpc(B._resolve_session(), "disposeRunner", [{"runnerId": rid}], timeout=20)
    except Exception:
        pass
    res["runnerId"] = None


def run(arm: str = "on", seed: int = SEED, board: str = BOARD, keep: bool = False,
        verbose: bool = False) -> dict:
    """Monte UN bras et rend sa mesure. Leve `RuntimeError` si le montage ne s'installe pas."""
    if arm not in ARMS:
        raise RuntimeError("bras inconnu : %s (connus : %s)" % (arm, sorted(ARMS)))
    equip, rarites = ARMS[arm]
    sf = _state_file(arm)
    argv = ["build", "--seed", str(int(seed)), "--board", str(board),
            "--p-mow", MOW, "--p-units", ATT, "--a-units", FOE,
            "--place", "%s:%d,%d" % (ATT, POS_ATT[0], POS_ATT[1]),
            "--a-place", "%s:%d,%d" % (FOE, POS_FOE[0], POS_FOE[1])]
    if equip:
        argv += ["--equip-mythic", MOW]
    for vis, r in rarites.items():
        argv += ["--unit-stat", "%s:Rarity=%d" % (vis, int(r))]
    argv += ["--state-file", sf]
    if verbose:
        print("[1035-r2] build %s" % " ".join(argv))
    if R.main(argv) != 0:
        raise RuntimeError("build ECHOUE (bras=%s) : %s" % (arm, " ".join(argv)))
    rid = json.loads(Path(sf).read_text(encoding="utf-8")).get("runnerId")
    if rid is None:
        raise RuntimeError("build sans runnerId (bras=%s)" % arm)

    sid = B._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(B._rpc(sid, method, [{**(body or {}), "runnerId": rid}],
                              timeout=timeout)) or {}

    res: dict = {"arm": arm, "runnerId": rid, "stateFile": sf, "equipMythic": equip,
                 "raritesForcees": dict(rarites)}
    try:
        dv = rpc("decisionView", {"maxRank": 1, "allAbilities": True}, 120)
        ids = {u.get("visualId"): int(u["id"]) for u in (dv.get("units") or []) if u.get("alive")}
        mow_id = next((int(m["casterId"]) for m in (dv.get("mows") or [])
                       if m.get("casterId") is not None), None)
        for k in (ATT, FOE):
            if k not in ids:
                raise RuntimeError("montage NON INSTALLE (bras=%s) : %s absent (%s)"
                                   % (arm, k, sorted(ids)))
        if mow_id is None:
            raise RuntimeError("montage NON INSTALLE (bras=%s) : aucune MoW" % arm)
        res["ids"] = dict(ids, mow=mow_id)

        # ---- LE TERRAIN : la MoW tire son mortier sur `POS_MORTIER`, DANS TOUS LES BRAS.
        at = rpc("abilityTargets", {"casterId": mow_id, "abilityType": MORTIER}, 90)
        cible = next((t for u in (at.get("units") or []) if u.get("unitId") == mow_id
                      for a in (u.get("abilities") or []) for t in (a.get("targets") or [])
                      if (t.get("tile") or {}).get("col") == POS_MORTIER[0]
                      and (t["tile"]).get("row") == POS_MORTIER[1]), None)
        if cible is None:
            raise RuntimeError("montage NON INSTALLE (bras=%s) : la tuile %s n'est pas ciblable "
                               "par %d" % (arm, POS_MORTIER, MORTIER))
        cast = rpc("applyAction", {"action": {"kind": "ability", "casterId": mow_id,
                                              "targetId": cible["targetId"],
                                              "abilityType": MORTIER}}, 90)
        if not cast.get("ok"):
            raise RuntimeError("cast du mortier REFUSE (bras=%s) : %s" % (arm, str(cast)[:200]))

        dv = rpc("decisionView", {"maxRank": 1, "allAbilities": True}, 120)
        cs = rpc("combatSnapshot", {}, 90)
        tm = rpc("tileMeta", {}, 60)
        tiles = tm.get("tiles") or []
        elev = {(t.get("col"), t.get("row")): t.get("elevation") for t in tiles}
        fx = {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
              for t in tiles}
        res["tuileAttaquant"] = fx.get(POS_ATT) or []
        res["attaquantContamine"] = CONTAMINATED in res["tuileAttaquant"]
        if not res["attaquantContamine"]:
            raise RuntimeError("montage NON INSTALLE (bras=%s) : la tuile de l'attaquant %s ne "
                               "porte pas %s (%s)" % (arm, POS_ATT, CONTAMINATED,
                                                      res["tuileAttaquant"]))
        res["rarityEnum"] = cs.get("rarityEnum")
        res["rarityByEntity"] = {u.get("entityId"): u.get("rarity") for u in (cs.get("units") or [])}
        res["mowEffects"] = sorted({e.get("name") for m in (dv.get("mows") or [])
                                    for e in (m.get("effects") or [])})
        res["auraPosee"] = "BlightedLand_ExtraDamagePct" in res["mowEffects"]

        # ---- NATIF : le preview `GetAllPredictions` de l'attaque NORMALE.
        p = rpc("aiPredict", {"unitId": ids[ATT], "targetId": ids[FOE]}, 90).get("pred") or {}
        res["natif"] = (p.get("healthDmgMin"), p.get("healthDmgMax"))
        if res["natif"][0] is None:
            raise RuntimeError("aiPredict MUET (bras=%s) : %r" % (arm, p))

        # ---- PORT : la MEME prediction, sur le MEME etat.
        from engine.playbook.scene import Scene, build_predictor, step_context
        from engine.playbook.prediction.normal_attack import make_normal_attack_predictions

        def _seam(method, body, timeout=90):
            return _unwrap(B._rpc(sid, method, [body], timeout=timeout)) or {}

        predictor = build_predictor(_seam, rid)
        if predictor is None:
            raise RuntimeError("build_predictor MUET (bras=%s)" % arm)
        sctx = step_context(predictor, dv)
        scene = Scene.from_predictor_sctx(predictor, sctx, elev, tile_effects_by_pos=fx)
        ev, meta = make_normal_attack_predictions(scene, ids[ATT], ids[FOE], POS_ATT, meta=True)
        pr = getattr(ev, "prediction", None)
        ahd = getattr(pr, "accurate_health_damage", None) if pr is not None else None
        res["port"] = ((getattr(ahd, "min", None), getattr(ahd, "max", None))
                       if ahd is not None else (None, None))
        res["portMeta"] = {k: v for k, v in (meta or {}).items()
                           if k in ("base", "pierce", "armor", "hits", "mods", "mods_detail")}
        res["portPctList"] = [tuple(x) for x in ((meta or {}).get("mods_detail") or ())]
    finally:
        if not keep:
            dispose(res)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=sorted(ARMS) + ["all"], default="all")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    arms = sorted(ARMS) if a.arm == "all" else [a.arm]
    out = {}
    for arm in arms:
        r = run(arm=arm, seed=a.seed, board=a.board, keep=a.keep, verbose=True)
        out[arm] = r
        print("[1035-r2] bras=%-7s aura=%-5s tuile=%s natif=%s port=%s pct=%s rar=%s"
              % (arm, r["auraPosee"], r["tuileAttaquant"], r["natif"], r["port"],
                 r["portPctList"], r["rarityByEntity"]))
    if len(out) == len(ARMS):
        accord = all(tuple(out[x]["natif"]) == tuple(out[x]["port"]) for x in ARMS)
        separe = tuple(out["on"]["natif"]) != tuple(out["off"]["natif"])
        temoin = tuple(out["rarity"]["natif"]) == tuple(out["off"]["natif"])
        print()
        print("ACCORD natif==port sur les 3 bras : %s" % accord)
        print("SEPARATION `on` != `off`          : %s" % separe)
        print("GATE de rarete eteint (`rarity`)  : %s" % temoin)
        return 0 if (accord and separe and temoin) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
