"""#1024-r2 -- MESURE LIVE du BONUS d'`OnMyPosition_ExtraDamagePct` (1444), en regime SEPARANT.

QUESTION BINAIRE : le natif applique-t-il `+extraDmgPct %` au degat d'une attaque A DISTANCE d'un
ami **Mythique** de la MoW `astraOrdnanceBattery` contre un ennemi voisin d'un ami **Mythique
HERO** -- et le PORT rend-il la MEME chose, en s'ETEIGNANT aux memes endroits ?

POURQUOI CE PROBE EXISTE (et pourquoi un vert du regime par defaut ne vaut rien). `rl_duel build`
impose `targetRarity = 5` a toute unite normalisee : dans le regime PAR DEFAUT, toute unite est
`Mythic`, donc `HasRarity(Caster, Mythic)` (le BONUS) ET `UnitsWithRarity(..., Mythic)` (le
SELECTEUR) sont uniformement VRAIS. Un port qui OUBLIERAIT ces deux etages serait d'accord avec le
natif PARTOUT. Le regime SEPARANT se fabrique par `--unit-stat "<vis>:Rarity=N"`, ECRIT APRES la
normalisation, donc recopie par `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` dans
`BaseUnitComponent[+0x74]`, le SEUL champ que lisent les trois gates natifs (#1039).

GEOMETRIE FORCEE (`--place` / `--a-place`) -- jamais << bloque par la geometrie de spawn >> :

        (3,3) adeptRetributor   -- l'ATTAQUANT, arme DISTANCE (`Range = 2`), a distance 2 de la
                                   cible : il n'est donc PAS lui-meme un voisin Mythique de la
                                   cible. C'est ce qui rend le bras `selecteur` possible.
        (2,5) adeptCanoness     -- l'ANCRE : ami HERO Mythique ADJACENT a la cible (branche B)
        (4,5) adeptHospitaller  -- le TEMOIN MELEE (`Range = null` -> melee au sens
                                   d'`IdunBattle.Entities.WeaponProfile$$get_IsMelee`), lui aussi
                                   adjacent : il est donc AUSSI dans le selecteur, d'ou son
                                   passage en `Rarity` non-Mythic dans le bras `selecteur`.
        (3,5) tyranTyrantGuard  -- la CIBLE, ENNEMIE de la MoW
        hors plateau            -- `astraOrdnanceBattery`, PORTEUSE de l'effet (aucune position)

CINQ BRAS, et chacun eteint UN etage precis :

  `on`        mythique EQUIPEE, tout le monde `Mythic`        -> bonus ATTENDU, effet SUR la cible
  `off`       PAS de `--equip-mythic`                         -> l'effet n'existe pas (BASE)
  `caster`    attaquant -> `Rarity.Epic`, ancre restee Mythic -> `HasRarity(Caster, Mythic)` FAUX,
                                                                 mais l'effet est TOUJOURS pose sur
                                                                 la cible (le SELECTEUR tient)
  `selecteur` ancre ET temoin -> `Rarity.Epic`, attaquant     -> plus AUCUN voisin Mythique HERO :
              reste Mythic                                       `targetIds` de l'effet devient VIDE
  (le TEMOIN MELEE est mesure DANS chaque bras : sa prediction ne doit JAMAIS bouger -- c'est le
   gate `IsRangedAttack`, que ses DEUX voisins de famille (1442, 1449) n'ont pas.)

⚠ Les bras `caster` et `selecteur` sont ce qui SEPARE les deux usages de la rarete. Un seul des
deux ne suffirait pas : dans `caster` le selecteur TIENT et seul le bonus tombe ; dans `selecteur`
c'est l'inverse. Le discriminant DIRECT est `targetIds` de l'effet 1444, lu sur la MoW.

⚠ UNE AURE NE SE LIT PAS SUR SA CIBLE. `decisionView` publie l'entite-EFFET une seule fois, portee
par sa SOURCE (ici la MoW, qui vit dans `.mows` et PAS dans `.units`), et c'est son champ
`targetIds` qui enumere les affectes (mesure #1024).

CE QUI EST COMPARE : `aiPredict` = le PREVIEW natif `IdunBattle.Core.Services.DamagePredictionQuery
$$GetAllPredictions` de l'attaque NORMALE, contre la prediction du PORT sur le MEME etat
(`playbook/prediction`). Les DEUX doivent bouger ENSEMBLE d'un bras a l'autre.

Discipline runner : `--state-file` ABSOLU sous `logs/` du checkout, runner DISPOSE en sortie de
chaque bras (sauf `--keep`). On ne dispose JAMAIS le runner d'un autre agent. ASCII only.

Usage :
    python probe_1024r2_on_my_position_bonus_live.py                # les quatre bras
    python probe_1024r2_on_my_position_bonus_live.py --arm on --keep
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
MOW = "astraOrdnanceBattery"
ATT = "adeptRetributor"      # ATTAQUANT, arme DISTANCE (Range 2)
ANCRE = "adeptCanoness"      # ami HERO Mythique adjacent a la cible (branche B du selecteur)
MELEE = "adeptHospitaller"   # TEMOIN melee (Range null), adjacent lui aussi
FOE = "tyranTyrantGuard"     # la CIBLE, ennemie de la MoW
POS_ATT, POS_ANCRE, POS_MELEE, POS_FOE = (3, 3), (2, 5), (4, 5), (3, 5)
#: `idun.meta.Rarity.Epic` = 3 -- la rarete NON-Mythic des bras separants.
RARETE_NON_MYTHIC = 3
EFFET_1444 = "OnMyPosition_ExtraDamagePct"

#: Les quatre bras : (equip_mythic, {visualId: rarete forcee}).
ARMS = {
    "on":        (True,  {}),
    "off":       (False, {}),
    "caster":    (True,  {ATT: RARETE_NON_MYTHIC}),
    "selecteur": (True,  {ANCRE: RARETE_NON_MYTHIC, MELEE: RARETE_NON_MYTHIC}),
}


def _unwrap(x):
    return x.get("result") if isinstance(x, dict) and "result" in x else x


def _state_file(nom: str) -> str:
    p = PYDIR.parents[1] / "logs" / ("probe1024r2_%s.json" % nom)
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
    """`visualId -> id d'entite` des unites vivantes, plus `mow` pour la Machine of War."""
    out = {u.get("visualId"): int(u["id"]) for u in (dv.get("units") or []) if u.get("alive")}
    for m in (dv.get("mows") or []):
        if m.get("casterId") is not None:
            out["mow"] = int(m["casterId"])
    return out


def _cibles_de_l_aure(dv: dict) -> list:
    """Union des `targetIds` des entrees d'effet 1444, lues sur `.units` ET `.mows`.

    C'est le discriminant DIRECT du `$$CreateTargetSelector` : il ne passe par aucun degat."""
    hit = set()
    for u in list(dv.get("units") or []) + list(dv.get("mows") or []):
        for e in (u.get("effects") or []):
            if e.get("name") == EFFET_1444:
                hit.update(e.get("targetIds") or [])
    return sorted(hit)


def run(arm: str = "on", seed: int = SEED, board: str = BOARD, keep: bool = False,
        verbose: bool = False) -> dict:
    """Monte UN bras et rend sa mesure. Leve `RuntimeError` si le montage ne s'installe pas --
    jamais de retour degrade qui se lirait comme une mesure (#268)."""
    if arm not in ARMS:
        raise RuntimeError("bras inconnu : %s (connus : %s)" % (arm, sorted(ARMS)))
    equip, rarites = ARMS[arm]
    sf = _state_file(arm)
    argv = ["build", "--seed", str(int(seed)), "--board", str(board),
            "--p-mow", MOW, "--p-units", "%s,%s,%s" % (ATT, ANCRE, MELEE), "--a-units", FOE,
            "--place", "%s:%d,%d" % (ATT, POS_ATT[0], POS_ATT[1]),
            "--place", "%s:%d,%d" % (ANCRE, POS_ANCRE[0], POS_ANCRE[1]),
            "--place", "%s:%d,%d" % (MELEE, POS_MELEE[0], POS_MELEE[1]),
            "--a-place", "%s:%d,%d" % (FOE, POS_FOE[0], POS_FOE[1])]
    if equip:
        argv += ["--equip-mythic", MOW]
    for vis, r in rarites.items():
        argv += ["--unit-stat", "%s:Rarity=%d" % (vis, int(r))]
    argv += ["--state-file", sf]
    if verbose:
        print("[1024-r2] build %s" % " ".join(argv))
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
        cs = rpc("combatSnapshot", {}, 90)
        ids = _ids(dv)
        for k in (ATT, ANCRE, MELEE, FOE):
            if k not in ids:
                raise RuntimeError("montage NON INSTALLE (bras=%s) : %s absent du roster vivant "
                                   "(%s)" % (arm, k, sorted(ids)))
        res["ids"] = ids
        res["rarityEnum"] = cs.get("rarityEnum")
        # ⚠ Cle par `entityId` : `combatSnapshot.units[].visualId` est `None` sur ce montage (mesure
        # du 2026-08-14 -- un `rarityByVis` s'effondrait sur une seule cle `None`, et le TEMOIN de
        # non-degenerescence de la rarete se lisait alors comme un accord VIDE).
        res["rarityByEntity"] = {u.get("entityId"): u.get("rarity")
                                 for u in (cs.get("units") or [])}
        res["posByVis"] = {u.get("visualId"): ((u.get("pos") or {}).get("col"),
                                               (u.get("pos") or {}).get("row"))
                           for u in (dv.get("units") or []) if u.get("alive")}
        res["mowEffects"] = sorted({e.get("name") for m in (dv.get("mows") or [])
                                    for e in (m.get("effects") or [])})
        res["auraPosee"] = EFFET_1444 in res["mowEffects"]
        res["cibles1444"] = _cibles_de_l_aure(dv)
        res["cibleEstVisee"] = ids[FOE] in res["cibles1444"]

        # ---- NATIF : le preview `GetAllPredictions` de l'attaque NORMALE, depuis la tuile COURANTE.
        p = rpc("aiPredict", {"unitId": ids[ATT], "targetId": ids[FOE]}, 90).get("pred") or {}
        res["natif"] = (p.get("healthDmgMin"), p.get("healthDmgMax"))
        if res["natif"][0] is None:
            raise RuntimeError("aiPredict MUET (bras=%s) : %r" % (arm, p))
        pm = rpc("aiPredict", {"unitId": ids[MELEE], "targetId": ids[FOE]}, 90).get("pred") or {}
        res["natifMelee"] = (pm.get("healthDmgMin"), pm.get("healthDmgMax"))

        # ---- PORT : la MEME prediction, sur le MEME etat, par la face DECISION.
        from engine.playbook.scene import Scene, build_predictor, step_context
        from engine.playbook.prediction.normal_attack import make_normal_attack_predictions

        def _seam(method, body, timeout=90):
            return _unwrap(B._rpc(sid, method, [body], timeout=timeout)) or {}

        predictor = build_predictor(_seam, rid)
        if predictor is None:
            raise RuntimeError("build_predictor MUET (bras=%s)" % arm)
        sctx = step_context(predictor, dv)
        # ⚠ `elev_by_pos` et `tile_effects_by_pos` sont OBLIGATOIRES (mesure #1035-r2 : sans eux, une
        # fausse divergence de 10 % imputable au seul harnais).
        tm = rpc("tileMeta", {}, 60)
        tiles = tm.get("tiles") or []
        elev = {(t.get("col"), t.get("row")): t.get("elevation") for t in tiles}
        fx = {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
              for t in tiles}
        scene = Scene.from_predictor_sctx(predictor, sctx, elev, tile_effects_by_pos=fx)
        ev, meta = make_normal_attack_predictions(scene, ids[ATT], ids[FOE], POS_ATT, meta=True)
        pr = getattr(ev, "prediction", None)
        ahd = getattr(pr, "accurate_health_damage", None) if pr is not None else None
        res["port"] = ((getattr(ahd, "min", None), getattr(ahd, "max", None))
                       if ahd is not None else (None, None))
        # `mods_detail` = la LISTE des contributions %-attaquant, une par `EffectBonus`. C'est LA que
        # la contribution de 1444 se lit NOMMEMENT -- deux erreurs compensatoires donneraient le
        # meme total.
        res["portPctList"] = [tuple(x) for x in ((meta or {}).get("mods_detail") or ())]
        # DECOMPOSITION PAR ETAGE : c'est elle qu'on compare entre bras, JAMAIS le rapport des
        # scalaires finaux (le natif accumule le %% dans `attackModifiers`, consomme AVANT
        # percage/armure avec un `Fix64.Round` par accumulateur -- fitter `on/off` ferait rougir un
        # port JUSTE, mesure #1025-r1).
        res["portMeta"] = {k: v for k, v in (meta or {}).items()
                           if k in ("base", "pierce", "armor", "hits", "mods")}
        evm, _mm = make_normal_attack_predictions(scene, ids[MELEE], ids[FOE], POS_MELEE, meta=True)
        prm = getattr(evm, "prediction", None)
        ahdm = getattr(prm, "accurate_health_damage", None) if prm is not None else None
        res["portMelee"] = ((getattr(ahdm, "min", None), getattr(ahdm, "max", None))
                            if ahdm is not None else (None, None))
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
    arms = ["off", "on", "caster", "selecteur"] if a.arm == "all" else [a.arm]
    out = {}
    for arm in arms:
        r = run(arm=arm, seed=a.seed, board=a.board, keep=a.keep, verbose=True)
        out[arm] = r
        print("[1024-r2] bras=%-10s aura=%-5s cibles1444=%s natif=%s port=%s melee_nat=%s pct=%s"
              % (arm, r["auraPosee"], r["cibles1444"], r["natif"], r["port"], r["natifMelee"],
                 r["portPctList"]))
        print("            rarites=%s pos=%s" % (r["rarityByEntity"], r["posByVis"]))
    if len(out) == len(ARMS):
        base = out["off"]["natif"]
        print()
        print("=== ECARTS (par rapport au bras `off`, qui n'a PAS l'effet) ===")
        for arm in ("on", "caster", "selecteur"):
            n, p = out[arm]["natif"], out[arm]["port"]
            print("  %-10s natif %s (x%.4f) | port %s | cibles1444 %s | pct-list %s"
                  % (arm, n, (n[0] / base[0]) if base[0] else float("nan"), p,
                     out[arm]["cibles1444"], out[arm]["portPctList"]))
        print()
        accord = all(tuple(out[a]["natif"]) == tuple(out[a]["port"]) for a in ARMS)
        accord_melee = all(tuple(out[a]["natifMelee"]) == tuple(out[a]["portMelee"])
                           for a in ARMS)
        separe = tuple(out["on"]["natif"]) != tuple(out["off"]["natif"])
        gate_bonus = (tuple(out["caster"]["natif"]) == tuple(out["off"]["natif"])
                      and out["caster"]["cibleEstVisee"])
        gate_selecteur = (tuple(out["selecteur"]["natif"]) == tuple(out["off"]["natif"])
                          and not out["selecteur"]["cibleEstVisee"])
        temoin_melee = (len({tuple(out[a]["natifMelee"]) for a in ARMS}) == 1)
        print("ACCORD natif==port (attaquant DISTANCE) : %s" % accord)
        print("ACCORD natif==port (temoin MELEE)       : %s" % accord_melee)
        print("SEPARATION `on` != `off`                : %s" % separe)
        print("GATE du BONUS seul (`caster`)           : %s" % gate_bonus)
        print("GATE du SELECTEUR seul (`selecteur`)    : %s" % gate_selecteur)
        print("TEMOIN MELEE invariant (IsRangedAttack) : %s" % temoin_melee)
        return 0 if (accord and accord_melee and separe and gate_bonus and gate_selecteur
                     and temoin_melee) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
