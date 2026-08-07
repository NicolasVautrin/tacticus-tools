#!/usr/bin/env python
"""#287-r11-r2-r1-r1 -- CONFRONTATION LIVE du `0` d'`IdunBattle.Core.Services.BattleQuery$$
GetUnitMaxRange`, que `mv71._drone_attack_range` MAPPAIT SUR `1`.

CE QUE #287-r11-r2-r1 A LAISSE OUVERT. Le decompile de `GetUnitMaxRange`, relu verbatim :

    config = GetUnitConfig(unitId);
    if (config == null)           return 0;
    if (config.Weapons == null)   return 0;
    max = 0;
    foreach (w in config.Weapons) max = Math.Max(max, w.Range.HasValue ? w.Range.Value : 1);
    return max;                                     // liste VIDE -> 0

C'est le MEME corps que la boucle INLINE de `BattleQuery$$IsTargetInAttackRangeForSummon`
(`IBattleQuery` slot 196), et c'est la portee que `MV71SniperDroneSquadAttackAbility$$PickTile`
donne a son anneau. Le port ecrivait `return mx if mx > 0 else 1` : il rendait **1** la ou le natif
rend **0**. Portee 1 ⇒ l'anneau `1 <= d <= rng` garde les tuiles ADJACENTES a la cible, la ou le
natif n'en garde AUCUNE (`1 <= d <= 0` est vide) ⇒ `PickTile` non nul ⇒ le gate ACCEPTE une cible
que le natif REFUSE. MEME direction PERMISSIVE que l'ecart que #287-r11-r2-r1 vient de fermer.

POURQUOI CE REGIME EST ATTEIGNABLE LIVE, ET COMMENT. `GetUnitConfig` ne lit PAS un catalogue global
-- son decompile parcourt `this.<+0xa0 : BattleConfiguration>.<+0x80>` (la liste des
`UnitConfiguration`) et compare `ConfigId`. C'est donc **`BC.Units[]`**, que le seed BC porte sur
disque et que `rl_duel build --seed-bc` remplace. Vider `BC.Units[tauSmnDroneSniper].Weapons` fait
donc rendre `0` au natif -- et `buildNormalizedBC` ne touche JAMAIS ce champ (verifie : aucune
ecriture `Weapons` dans `normalize-bc/json-build.ts`). Mesure du 2026-08-07 : **12 des 175** entrees
du seed portent deja `Weapons: []` (MoW et decor), donc le regime existe en vrai -- mais pas sur
`tauSmnDroneSniper`, d'ou le montage.

⚠ LE SUBSTRAT DU PORT EST ALIGNE, ET C'EST DECLARE. Le port lit le CATALOGUE gameconfig
(`GC.unit(...)["weapons"]`), le natif lit la BC : deux canaux distincts qui coincident normalement.
Sans alignement, ce probe mesurerait la divergence des CANAUX, pas l'etage `GetUnitMaxRange`.
`substrat_sans_armes()` fait donc voir `weapons: []` au port pour ce seul unitId, exactement ce que
le seed BC custom fait voir au natif. Le TEMOIN recoit le MEME substrat aligne -- c'est ce qui rend
l'attribution valable.

LES DEUX BRAS (montage `degage` de `probe_287r11r2r1_los_summon_live.py`, sa SOURCE UNIQUE) :

  `armes`      -- seed BC NORMAL. `GetUnitMaxRange = 4`, une tuile libre CLAIRE dans le disque.
                  NATIF ATTENDU : `0x0` (le cast est legal).
  `sans-armes` -- seed BC ou `tauSmnDroneSniper.Weapons = []`. `GetUnitMaxRange = 0`, l'anneau est
                  VIDE. NATIF ATTENDU : `0x1 ValidRequest` (refus). Port d'avant : `0x0` -> SOUS-refus.

Un seul bras ne prouverait rien : `sans-armes` seul serait compatible avec « le port refuse
toujours », `armes` seul avec « le port accepte toujours ».

Usage (session warmee ; le probe monte et DISPOSE ses propres runners, un a la fois) :
    python scripts/python/probe_287r11r2r1r1_portee_nulle_live.py
    python scripts/python/probe_287r11r2r1r1_portee_nulle_live.py --only sans-armes
ASCII only ; exit 0 = les deux verdicts natifs exerces, port d'accord, temoin en desaccord.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gameconfig as GC                                                    # noqa: E402
import hexgeo                                                              # noqa: E402
import oracle_targeting as O                                               # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
import probe_287r11r1_regles_ciblage_live as R1                            # noqa: E402
import probe_287r11r2r1_los_summon_live as LOS                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.runner.abilities.loki import mv71 as MV                        # noqa: E402
from engine.runner.abilities.targeting import (                            # noqa: E402
    _NormalAttackTargeting, is_invalid_target, normal_attack_targeting_options)
from engine.runner.snapshot import load_state                              # noqa: E402

ROOT = HERE.parents[1]
LOGS = ROOT / "logs"

MV71 = int(ActiveAbilityType.MV71SniperDroneSquadAttack)       # 1076
CASTER = LOS.CASTER                                            # "tauMarksman"
DRONE = LOS.DRONE                                              # "tauSmnDroneSniper"

#: `nom -> (armes du drone dans le seed BC, verdict natif ATTENDU sur la cible cle)`
BRAS = {
    "armes": (True, 0x0),
    "sans-armes": (False, 0x1),
}

#: LE MONTAGE, DERIVE de `degage` (`probe_287r11r2r1_los_summon_live.MONTAGES`) A UNE VARIABLE PRES,
#: et cette variable est ce qui rend le TEMOIN discriminant.
#:
#: `degage` laisse UNE tuile libre claire, `(1,4)`, a **d=3** de la cible. C'est parfait pour la
#: LIGNE DE VUE (l'objet de #287-r11-r2-r1) et INUTILISABLE ici : sous le port d'AVANT, la portee
#: rabattue vaut **1**, donc son anneau `1 <= d <= 1` ne contient AUCUNE tuile libre et il refuse
#: comme le natif. Mesure du 2026-08-07 sur `degage` : temoin `0x1` = port `0x1`, « le montage ne
#: DISCRIMINE pas » -- l'accord y etait obtenu par la geometrie, pas par l'etage porte.
#:
#: On LIBERE donc `(0,2)` (claire, **d=1**) et on occupe `(1,4)` a la place. Effet :
#:   * portee 4 (bras `armes`)      -> `(0,2)` est candidate                 -> natif `0x0` ;
#:   * portee 0 (bras `sans-armes`) -> l'anneau `1 <= d <= 0` est VIDE       -> natif `0x1` ;
#:   * portee 1 (le port d'AVANT)   -> `(0,2)` redevient candidate           -> `0x0`, SOUS-refus.
#: Le caster reste en `(0,3)`, a d=2 de la cible et sans ennemi adjacent -- meme precaution que le
#: probe LOS : un ennemi au contact ferait clamper la portee du CASTER et `TargetIsInRange`
#: masquerait la regle.
def _montage() -> dict:
    m = dict(LOS.MONTAGES["degage"])
    m["place"] = ["tauMarksman:0,3", "ultraTitus:1,4", "ultraTitus:2,4", "ultraTitus:5,5"]
    return m


#: Distance a laquelle une tuile libre CLAIRE doit exister pour que le temoin (portee 1) puisse
#: diverger. Le probe le VERIFIE sur la geometrie LIVE plutot que de le supposer.
D_TEMOIN = 1


def _seed_bc_sans_armes(out: Path) -> tuple[Path, dict]:
    """Ecrit un seed BC ou l'entree `BC.Units[]` du drone porte `Weapons: []`.

    Rend aussi le CONSTAT de la mutation (`{avant, apres, trouvee}`) : une entree non trouvee
    rendrait un seed IDENTIQUE a l'original et le bras se lirait comme un accord, alors qu'aucune
    mutation n'aurait eu lieu."""
    src = ROOT / "data" / "seed-bc.json"
    bc = json.loads(src.read_text(encoding="utf-8"))
    constat = {"trouvee": 0, "avant": None}
    for u in bc.get("Units") or []:
        if str(u.get("Id") or "").split(":")[0] != DRONE:
            continue
        constat["trouvee"] += 1
        constat["avant"] = copy.deepcopy(u.get("Weapons"))
        u["Weapons"] = []
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")
    return out, constat


@contextlib.contextmanager
def substrat_sans_armes():
    """ALIGNE le substrat du PORT sur celui du natif : `weapons: []` pour le drone, et pour lui
    seul. Substitution de l'attribut de module `gameconfig.unit` -- `get_unit_max_range` y accede
    par attribut, donc le patch MORD (forme B)."""
    orig = GC.unit

    def patched(uid, *a, **k):
        cfg = orig(uid, *a, **k)
        if uid == DRONE and isinstance(cfg, dict):
            cfg = dict(cfg)
            cfg["weapons"] = []
        return cfg

    GC.unit = patched
    try:
        yield
    finally:
        GC.unit = orig


@contextlib.contextmanager
def portee_avant():
    """LE PORT D'AVANT #287-r11-r2-r1-r1, substitue EN PLACE : le corps LOCAL de
    `_drone_attack_range`, qui lisait `int(w.get("Range") or 0)` puis mappait `0` sur `1`.

    Substitution d'ATTRIBUT DE MODULE (forme B) : `_pick_tile` et `pick_tile_scene` lisent ce nom
    comme une globale de `mv71`, donc le patch MORD."""
    old = MV._drone_attack_range

    def ancien(unit_id):
        ranges = [int(w.get("Range") or 0) for w in ((GC.unit(unit_id) or {}).get("weapons") or [])]
        mx = max(ranges) if ranges else 0
        return mx if mx > 0 else 1

    MV._drone_attack_range = ancien
    try:
        yield
    finally:
        MV._drone_attack_range = old


def _verdicts(rid, ctx, cible_xy):
    """Les verdicts NATIF et PORT sur la cible cle. Les DEUX porteurs du gate sont interroges
    (la classe 1076 et l'aiguillage `_NormalAttackTargeting`), comme dans le probe LOS.

    Rend aussi la GEOMETRIE mesuree (tuiles libres claires du disque r=4, calculee sur le board et
    l'occupation LIVE) : c'est le CONTROLE DE MONTAGE -- un `--place` non honore est SILENCIEUX, et
    sans cette mesure le verdict porterait sur une geometrie qui n'est pas celle qu'on croit."""
    dec, ob, snap, board, alive, by_vis = ctx
    state = load_state(dec, ob, snap, board=board)
    clairs, masques = LOS._geometrie(board, alive, tuple(cible_xy), 4)
    caster = by_vis.get(CASTER)
    if caster is None:
        return {"absent": CASTER}
    r0 = R1._rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                   "abilityType": MV71}, 60000) or {}
    if O.oracle_court_circuite(r0):
        return {"court_circuite": O.cause_du_court_circuit(r0)}
    porteurs = {
        "classe": P._porteur(MV71),
        "normale": _NormalAttackTargeting(
            normal_attack_targeting_options(state, int(caster["id"]))),
    }
    mine = caster.get("team")
    for u in alive:
        if u.get("id") == caster.get("id") or u.get("team") == mine:
            continue
        if R1._pos(u) != tuple(cible_xy):
            continue
        tid = int(u["id"])
        r = R1._rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                      "abilityType": MV71, "targetId": tid}, 60000) or {}
        tr = r.get("targetReason") or {}
        nat = int(tr.get("hex") or "0x0", 16)
        ports = {k: int(is_invalid_target(state, int(caster["id"]), tid, ab) or 0)
                 for k, ab in porteurs.items()}
        with portee_avant():
            temoin = {k: int(is_invalid_target(state, int(caster["id"]), tid, ab) or 0)
                      for k, ab in porteurs.items()}
        return {"cible": tid, "natif": nat, "port": ports, "temoin": temoin,
                "rayon": MV._drone_attack_range(DRONE),
                "clairs": clairs, "masques": masques,
                "clairs_d1": [q for q in clairs
                              if hexgeo.distance(q, tuple(cible_xy)) == D_TEMOIN]}
    return {"cible_absente": tuple(cible_xy), "clairs": clairs, "masques": masques}


def jouer(nom: str, keep: bool) -> dict:
    avec_armes, natif_attendu = BRAS[nom]
    m = _montage()                             # `degage`, A UNE VARIABLE PRES (cf. `_montage`)
    tag = uuid.uuid4().hex[:8]
    state_file = LOGS / ("rs_287r11r2r1r1_%s_%s.json" % (nom, tag))
    args = ["build", "--seed", str(m["seed"]), "--board", m["board"], "--rank", "17",
            "--p-units", m["p_units"], "--a-units", m["a_units"], "--no-ai",
            "--state-file", str(state_file)]
    out: dict = {"nom": nom, "natif_attendu": natif_attendu, "fails": []}
    if not avec_armes:
        seed_path, constat = _seed_bc_sans_armes(
            LOGS / ("seed_bc_287r11r2r1r1_%s.json" % tag))
        out["mutation"] = constat
        if not constat["trouvee"]:
            out["fails"].append("aucune entree `BC.Units[]` pour %s : le seed n'a PAS ete mute"
                                % DRONE)
            return out
        args += ["--seed-bc", str(seed_path)]
    for p in m.get("place") or []:
        args += ["--place", p]
    for p in m.get("a_place") or []:
        args += ["--a-place", p]
    sortie = R1._run(args)
    out["refus_placement"] = [ln.strip() for ln in sortie.splitlines()
                              if "placement REFUSE" in ln]
    if not state_file.exists():
        out["fails"].append("build KO : " + " | ".join(
            ln.strip() for ln in sortie.splitlines() if ln.startswith("[error]"))[:400])
        return out
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    out["rid"] = rid
    try:
        ctx = R1._contexte(rid)
        if avec_armes:
            out.update(_verdicts(rid, ctx, m["cible"]))
        else:
            with substrat_sans_armes():
                out.update(_verdicts(rid, ctx, m["cible"]))
    finally:
        if not keep:
            R1._run(["dispose", "--state-file", str(state_file)])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="#287-r11-r2-r1-r1 : le zero de GetUnitMaxRange, confronte live")
    ap.add_argument("--only", default=None, choices=sorted(BRAS))
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    rc = 0
    natifs = []
    for nom in sorted(BRAS):
        if a.only is not None and nom != a.only:
            continue
        r = jouer(nom, a.keep)
        print("")
        print("[287r11r2r1r1-live] bras %s -- porteur %s -- board %s -- runner %s"
              % (nom, CASTER, _montage()["board"], r.get("rid")))
        if r.get("mutation"):
            print("   seed BC mute : %d entree(s) `%s`, Weapons %s -> []"
                  % (r["mutation"]["trouvee"], DRONE,
                     [w.get("Range") for w in (r["mutation"]["avant"] or [])]))
        for ln in (r.get("refus_placement") or []):
            print("   !! PLACEMENT REFUSE : %s" % ln)
            rc = max(rc, 1)
        for f in r["fails"]:
            print("   PAS MESURE : %s" % f)
            rc = 2
        if r["fails"]:
            continue
        for cle, msg in (("absent", "porteur ABSENT"), ("court_circuite", "oracle COURT-CIRCUITE"),
                         ("cible_absente", "cible cle hors du domaine")):
            if r.get(cle):
                print("   PAS MESURE : %s (%s)" % (msg, r[cle]))
                rc = 2
        if any(r.get(c) for c in ("absent", "court_circuite", "cible_absente")):
            continue
        print("   disque r=4 de %s -- libres CLAIRES %s (dont a d=%d : %s) | libres MASQUEES %s"
              % (tuple(_montage()["cible"]), r.get("clairs"), D_TEMOIN, r.get("clairs_d1"),
                 r.get("masques")))
        # CONTROLE DE MONTAGE : sans tuile libre CLAIRE a d=1, le temoin (portee 1) ne peut PAS
        # diverger, et l'accord port <-> natif serait obtenu par la geometrie, pas par l'etage.
        if not r.get("clairs_d1"):
            print("   !! MONTAGE NON HONORE : aucune tuile libre CLAIRE a d=%d -- le temoin ne "
                  "peut pas discriminer" % D_TEMOIN)
            rc = max(rc, 2)
        print("   rayon du drone vu par le port : %s | natif=%s | port=%s | temoin (le mapping "
              "0->1 d'avant)=%s"
              % (r["rayon"], hex(r["natif"]), {k: hex(v) for k, v in r["port"].items()},
                 {k: hex(v) for k, v in r["temoin"].items()}))
        natifs.append(r["natif"])
        # LA RE PREDIT LE VERDICT NATIF : si le natif dit autre chose, c'est la LECTURE du
        # decompile qui est fausse, et ca doit etre BRUYANT.
        if r["natif"] != r["natif_attendu"]:
            print("   !! PREDICTION DE LA RE NON CONFIRMEE : natif %s, attendu %s"
                  % (hex(r["natif"]), hex(r["natif_attendu"])))
            rc = max(rc, 1)
        for k, v in r["port"].items():
            if v != r["natif"]:
                print("   !! ECART DE PORT (%s) : natif %s, port %s"
                      % (k, hex(r["natif"]), hex(v)))
                rc = max(rc, 1)
        # VUE ROUGE : sur `sans-armes`, le port d'AVANT doit ACCEPTER (SOUS-refus). S'il refuse
        # aussi, le montage ne discrimine pas et l'accord ci-dessus ne prouve rien.
        if r["natif_attendu"] != 0:
            perdus = [k for k, v in r["temoin"].items() if v != r["natif"]]
            print("   VUE ROUGE : porteurs qui SOUS-refusaient sous le mapping `0 -> 1` : %s"
                  % (perdus or "AUCUN"))
            if not perdus:
                print("   !! le montage ne DISCRIMINE pas : sous le port d'avant, le verdict est "
                      "le meme")
                rc = max(rc, 1)
    print("")
    print("[287r11r2r1r1-live] NON-DEGENERESCENCE : verdicts natifs = %s -> %s"
          % (sorted({hex(x) for x in natifs}),
             "les DEUX exerces" if len(set(natifs)) == 2
             else "!! REGIME DEGENERE : un seul verdict, l'accord ne prouve rien"))
    if a.only is None and len(set(natifs)) < 2:
        rc = max(rc, 1)
    print("[287r11r2r1r1-live] VERDICT : %s" % ("OK" if rc == 0 else "ROUGE (rc=%d)" % rc))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
