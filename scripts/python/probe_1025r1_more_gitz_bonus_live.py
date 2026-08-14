"""#1025-r1 -- MESURE LIVE du BONUS de `MoreGitzOverEre_ExtraDamagePct` (1449), en regime SEPARANT.

QUESTION BINAIRE : le natif applique-t-il `+extraDmgPct %` au degat d'une attaque MELEE NORMALE
d'un ami **Mythique** de la MoW `orksRukkatrukk` contre un ennemi ayant **>= 2 amis Mythiques
adjacents** -- et le PORT rend-il la MEME chose, en s'ETEIGNANT aux memes endroits ?

POURQUOI CE PROBE EXISTE (et pourquoi un vert du regime par defaut ne vaut rien). `rl_duel build`
impose `targetRarity = 5` a toute unite normalisee : dans le regime PAR DEFAUT, toute unite est
`Mythic`, donc `HasRarity(Caster, Mythic)` ET `UnitsWithRarity(voisins, Mythic)` sont uniformement
VRAIS. Un port qui OUBLIERAIT ces deux etages serait d'accord avec le natif PARTOUT. Le probe
fabrique donc le regime SEPARANT par `--unit-stat "<vis>:Rarity=N"` (ecrit APRES la normalisation,
donc recopie par `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` dans
`BaseUnitComponent[+0x74]`, le SEUL champ que lisent les trois gates natifs).

GEOMETRIE FORCEE (`--place` / `--a-place`) -- jamais << bloque par la geometrie de spawn >> :

        (3,3) orksNob       -- l'ATTAQUANT (melee), ami de la MoW
        (2,4) orksWarboss   -- le SECOND ami adjacent a la cible (c'est lui qui fait passer
                               `AmountIsEqualOrGreater(..., Direct(2))`, l'attaquant comptant
                               deja pour un : `AdjacentUnits(<la cible>)` ne l'exclut pas)
        (3,4) necroWarden   -- la CIBLE, ENNEMIE de la MoW
        hors plateau        -- `orksRukkatrukk`, PORTEUSE de l'effet (aucune position)

QUATRE BRAS, et chacun eteint UN etage precis :

  `on`      mythique EQUIPEE, Nob et Warboss `Mythic`            -> bonus ATTENDU
  `off`     PAS de `--equip-mythic`                              -> l'effet n'existe pas (BASE)
  `caster`  Nob -> `Rarity.Epic`                                 -> `HasRarity(Caster, Mythic)` FAUX
  `count`   Warboss -> `Rarity.Epic`, Nob reste `Mythic`         -> il ne reste qu'UN ami Mythique
                                                                    adjacent -> `>= 2` FAUX

⚠ Le bras `count` est le SEUL qui isole la seconde branche du selecteur SANS toucher a l'attaquant :
dans `caster`, les deux gates tombent ensemble (le Nob sort du compte en meme temps qu'il perd son
`HasRarity`), donc `caster` seul ne separerait pas les deux causes. Le TEMOIN NON NUL est le couple
`on` / `count` : une unite PRISE (le Warboss Mythique) et une unite ECARTEE (le meme, Epic), toutes
choses egales par ailleurs.

CE QUI EST COMPARE : `aiPredict` = le PREVIEW natif `IdunBattle.Core.Services.DamagePredictionQuery
$$GetAllPredictions` de l'attaque NORMALE, contre la prediction du PORT sur le MEME etat
(`playbook/prediction`). Les DEUX doivent bouger ENSEMBLE d'un bras a l'autre.

Discipline runner : `--state-file` ABSOLU sous `logs/` du checkout, runner DISPOSE en sortie de
chaque bras (sauf `--keep`). On ne dispose JAMAIS le runner d'un autre agent. ASCII only.

Usage :
    python probe_1025r1_more_gitz_bonus_live.py                 # les quatre bras
    python probe_1025r1_more_gitz_bonus_live.py --arm on --keep
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

BOARD = "MC1_67"
SEED = 777
MOW = "orksRukkatrukk"
ATT = "orksNob"            # l'ATTAQUANT (melee)
FRIEND = "orksWarboss"     # le SECOND ami adjacent a la cible
FOE = "necroWarden"        # la CIBLE, ennemie de la MoW
POS_ATT, POS_FRIEND, POS_FOE = (3, 3), (2, 4), (3, 4)
#: `idun.meta.Rarity.Epic` = 3 -- la rarete NON-Mythic des bras separants.
RARETE_NON_MYTHIC = 3

#: Les quatre bras : (equip_mythic, {visualId: rarete forcee}).
ARMS = {
    "on":     (True,  {}),
    "off":    (False, {}),
    "caster": (True,  {ATT: RARETE_NON_MYTHIC}),
    "count":  (True,  {FRIEND: RARETE_NON_MYTHIC}),
}


def _unwrap(x):
    return x.get("result") if isinstance(x, dict) and "result" in x else x


def _state_file(nom: str) -> str:
    p = PYDIR.parents[1] / "logs" / ("probe1025r1_%s.json" % nom)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def dispose(res: dict) -> None:
    """Rend le runner du bras. Idempotent et silencieux : un teardown qui leve masque le verdict."""
    rid = (res or {}).get("runnerId")
    if rid is None:
        return
    try:
        B._rpc(B._resolve_session(), "disposeRunner", [{"runnerId": rid}], timeout=20)
    except Exception:
        pass
    res["runnerId"] = None


def _ids(dv: dict) -> dict:
    """`visualId -> id d'entite` des unites vivantes, plus `mow` pour la Machine of War.

    Les ids viennent de `decisionView` et de nulle part d'ailleurs : `aiPredict` et `applyAction`
    refusent ceux d'`observeBattle` (`unit <n> not found`)."""
    out = {u.get("visualId"): int(u["id"]) for u in (dv.get("units") or []) if u.get("alive")}
    for m in (dv.get("mows") or []):
        if m.get("casterId") is not None:
            out["mow"] = int(m["casterId"])
    return out


def run(arm: str = "on", seed: int = SEED, board: str = BOARD, keep: bool = False,
        verbose: bool = False) -> dict:
    """Monte UN bras et rend sa mesure. Leve `RuntimeError` si le montage ne s'installe pas --
    jamais de retour degrade qui se lirait comme une mesure (#268)."""
    if arm not in ARMS:
        raise RuntimeError("bras inconnu : %s (connus : %s)" % (arm, sorted(ARMS)))
    equip, rarites = ARMS[arm]
    sf = _state_file(arm)
    argv = ["build", "--seed", str(int(seed)), "--board", str(board),
            "--p-mow", MOW, "--p-units", "%s,%s" % (ATT, FRIEND), "--a-units", FOE,
            "--place", "%s:%d,%d" % (ATT, POS_ATT[0], POS_ATT[1]),
            "--place", "%s:%d,%d" % (FRIEND, POS_FRIEND[0], POS_FRIEND[1]),
            "--a-place", "%s:%d,%d" % (FOE, POS_FOE[0], POS_FOE[1])]
    if equip:
        argv += ["--equip-mythic", MOW]
    for vis, r in rarites.items():
        argv += ["--unit-stat", "%s:Rarity=%d" % (vis, int(r))]
    argv += ["--state-file", sf]
    if verbose:
        print("[1025-r1] build %s" % " ".join(argv))
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
        ob = rpc("observeBattle", {}, 60)
        cs = rpc("combatSnapshot", {}, 90)
        ids = _ids(dv)
        for k in (ATT, FRIEND, FOE):
            if k not in ids:
                raise RuntimeError("montage NON INSTALLE (bras=%s) : %s absent du roster vivant "
                                   "(%s)" % (arm, k, sorted(ids)))
        res["ids"] = ids
        res["rarityEnum"] = cs.get("rarityEnum")
        res["rarityByEntity"] = {u.get("entityId"): u.get("rarity") for u in (cs.get("units") or [])}
        res["posByVis"] = {u.get("visualId"): (u.get("pos") or {}).get("col") is not None
                           and ((u["pos"]["col"], u["pos"]["row"])) or None
                           for u in (dv.get("units") or []) if u.get("alive")}
        # L'effet est-il POSE sur la MoW ? (bras `off` : il ne doit PAS l'etre.)
        res["mowEffects"] = sorted({e.get("name") for m in (dv.get("mows") or [])
                                    for e in (m.get("effects") or [])})
        res["auraPosee"] = "MoreGitzOverEre_ExtraDamagePct" in res["mowEffects"]

        # ---- NATIF : le preview `GetAllPredictions` de l'attaque NORMALE, depuis la tuile COURANTE
        p = rpc("aiPredict", {"unitId": ids[ATT], "targetId": ids[FOE]}, 90).get("pred") or {}
        res["natif"] = (p.get("healthDmgMin"), p.get("healthDmgMax"))
        if res["natif"][0] is None:
            raise RuntimeError("aiPredict MUET (bras=%s) : %r" % (arm, p))

        # ---- PORT : la MEME prediction, sur le MEME etat, par la face DECISION.
        # `build_predictor` prend le SEAM RPC (pas les vues deja tirees) : c'est lui qui confronte
        # `rarityEnum` au nom PLEIN attendu (#999-r3), donc on le laisse faire ses propres appels.
        from engine.playbook.scene import Scene, build_predictor, step_context
        from engine.playbook.prediction.normal_attack import make_normal_attack_predictions

        def _seam(method, body, timeout=90):
            return _unwrap(B._rpc(sid, method, [body], timeout=timeout)) or {}

        predictor = build_predictor(_seam, rid)
        if predictor is None:
            raise RuntimeError("build_predictor MUET (bras=%s)" % arm)
        sctx = step_context(predictor, dv)
        # ⚠ `elev_by_pos` et `tile_effects_by_pos` sont OBLIGATOIRES, et les omettre est un vice de
        # MONTAGE, pas une simplification : `engine/ai/context.py` les construit toujours depuis
        # `tileMeta`, et sans eux la `Scene` degrade en silence tout gate positionnel ou de tuile.
        # MESURE (#1035-r2) : sur le jumeau `BlightedLand`, la sonde SANS ces deux tables rendait
        # 4341 contre 4773 cote natif -- une fausse divergence de 10 % imputable au harnais seul.
        tm = rpc("tileMeta", {}, 60)
        tiles = tm.get("tiles") or []
        elev = {(t.get("col"), t.get("row")): t.get("elevation") for t in tiles}
        fx = {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
              for t in tiles}
        scene = Scene.from_predictor_sctx(predictor, sctx, elev, tile_effects_by_pos=fx)
        res["tuileAttaquant"] = fx.get(POS_ATT)
        ev, meta = make_normal_attack_predictions(scene, ids[ATT], ids[FOE], POS_ATT, meta=True)
        pr = getattr(ev, "prediction", None)
        ahd = getattr(pr, "accurate_health_damage", None) if pr is not None else None
        res["port"] = ((getattr(ahd, "min", None), getattr(ahd, "max", None))
                       if ahd is not None else (None, None))
        # `mods_detail` = la LISTE des contributions %-attaquant, une par `EffectBonus`. C'est LA
        # que la contribution de 1449 se lit NOMMEMENT (`('PercentIncrease', <extraDmgPct>, True)`),
        # et c'est ce qui distingue << le total concorde >> de << c'est bien CET effet qui l'a
        # produit >> : deux erreurs compensatoires donneraient le meme total.
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
        print("[1025-r1] bras=%-7s aura_posee=%-5s natif=%s port=%s pct=%s rarites=%s"
              % (arm, r["auraPosee"], r["natif"], r["port"], r["portPctList"],
                 r["rarityByEntity"]))
    if len(out) == len(ARMS):
        base = out["off"]["natif"]
        print()
        print("=== ECARTS (par rapport au bras `off`, qui n'a PAS l'effet) ===")
        for arm in ("on", "caster", "count"):
            n, p = out[arm]["natif"], out[arm]["port"]
            print("  %-7s natif %s (x%.4f) | port %s | pct-list %s"
                  % (arm, n, (n[0] / base[0]) if base[0] else float("nan"), p,
                     out[arm]["portPctList"]))
        print()
        accord = all(tuple(out[a]["natif"]) == tuple(out[a]["port"]) for a in ARMS)
        separe = tuple(out["on"]["natif"]) != tuple(out["off"]["natif"])
        temoin = (tuple(out["count"]["natif"]) == tuple(out["off"]["natif"])
                  and tuple(out["caster"]["natif"]) == tuple(out["off"]["natif"]))
        print("ACCORD natif==port sur les 4 bras : %s" % accord)
        print("SEPARATION `on` != `off`          : %s" % separe)
        print("GATES eteints (`caster`,`count`)  : %s" % temoin)
        return 0 if (accord and separe and temoin) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
