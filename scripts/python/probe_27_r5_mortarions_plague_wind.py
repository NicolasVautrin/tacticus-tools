"""probe #27-r5 -- MortarionsPlagueWind (1093), 2e des 4 overrides « npc-only » de #27.

CE QUI EST TESTE
----------------
`IdunBattle.AI.Playbook.Loki.MortarionsPlagueWindPlaybook$$CalculateCustomUtility`, relu VERBATIM
sur `rnca9r7q6c` :

    t1  = <ability>.GetTarget()              // ghidra: StrikeFromTheShadowsAbility$$GetTarget
                                             //   = *(*(ability+0x30)+0x90)+0x60 = <DSLSelectors+0x60> = Target
    t2  = <ability>.b__1_0(t1)               // ghidra: StormOfWrathAbility$$<ExecuteBehaviour>b__1_0
                                             //   = Enemies(<+0x48> = Caster, AdjacentUnits(t1, 1, 3), 3)
    t3  = <ability>.GetTargets3(t1, t2)      // ghidra: PlagueWindAbility$$GetTargets3
                                             //   = Unique(Enemies(Caster, AdjacentUnits(t2, 1, 3), 3)) - t1 - t2
    sel = DSLSelectors.UnitsWithTrait(t1 + t2 + t3, 0x3ea = Psyker, 3)
    return Fix64.op_Implicit( sel.<vslot 0x18 = Count>(AbilityEntities(caster, caster, target)) )

**AUCUN `GetUtilityValue`, aucune constante : le COMPTE de PSYKERS *EST* l'utilite.**

TROIS points de RE qui ne se devinent pas
-----------------------------------------
1. **Le 3e argument d'`IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(this, origin, unique,
   selectionType)` est `unique`, PAS `includeCenter`** (piege #419) : son corps est
   `op_Subtraction(Units(AdjacentTiles(origin), unique, selectionType), origin)` -- le centre est
   TOUJOURS retire. Lire le `1` du call-site comme un `includeCenter` ferait entrer la cible dans sa
   propre vague 2.
2. **L'`AbilityEntities` ne porte QUE trois champs.**
   `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor(this, caster, actor, target, owner,
   casterTile, ...)` est appele avec `(caster, caster, target, 0, 0, ...)` apres un memset a ZERO de
   ses 0x128 octets : `owner` ET `casterTile` sont NULS. Le terme est donc **INDEPENDANT de la tuile
   d'attaque** -- il departage les CIBLES, jamais deux tuiles pour une meme cible.
3. **La chaine est celle de la face COMBAT de son jumeau `PlagueWind` (1035, `deathTyphus`)**, deja
   portee (`runner/abilities/deathguard.py::plague_wind_target_selectors`) : les trois corps natifs
   sont DEDUPLIQUES entre les deux abilities. Seule difference : les deux `ExecuteBehaviour` posent
   un `DSLSelectors$$Cache` sur chaque vague, que le playbook n'a pas.

LE VERROU ANNONCE PAR LA FICHE N'EN ETAIT PLUS UN
-------------------------------------------------
La fiche #27-r5 tenait « l'evaluateur DSL `UnitsWithTrait` + la chaine `AdjacentUnits` a 3 vagues
n'est pas portee cote decision ». Re-derive du code : les quatre primitives (`adjacent_units`,
`Enemies`, `Unique`, `UnitsWithTrait`) et les deux combinateurs (`Union`, `Sub`) sont TOUS dans
`entities/selectors/`, et la voie « playbook -> `DslContext` -> arbre de l'ability » a deja deux
precedents (`resurrection_orb`, `playbook/tile_targets`). Aucune primitive a porter.

MONTAGE (board MC1_67, seed 909)
--------------------------------
PORTEUR GREFFE. La seule unite qui porte 1093 est `deathBossMortarion` (npc). « npc-only » n'est pas
« non confrontable » : le natif charge le playbook PAR ABILITY, et cette formule ne lit NI stat NI
trait NI arme NI portee du CASTER (le trait `Psyker` teste est celui des unites SELECTIONNEES ; le
caster n'entre que comme referent d'inimitie, donc son CAMP). On greffe donc 1093 sur
`deathBlightlord` (MEME faction Death Guard, dans `rl_duel build --list-pool`), `case-92` §5bis.

`--hp-target` / `--armor-target` egalisent Health/RemainingHealth/Armor sur TOUT le camp adverse :
sans eux, l'ecart d'utilite de DEGAT entre deux cibles masque le terme, qui vaut 1 ou 2.

BRAS -- le discriminant est la POSITION DU PSYKER, a geometrie de grappe CONSTANTE
  A : le Psyker est le voisin de la cible T1  -> custom(T1) = 1, custom(T2) = 0
  B : le Psyker est le voisin de la cible T2  -> custom(T1) = 0, custom(T2) = 1
  (les DEUX bras ont exactement le meme nombre d'unites, aux memes tuiles ; seuls les OCCUPANTS de
   deux tuiles sont permutes -- c'est ce qui isole le trait.)
  C : vague 3 -- un Psyker adjacent a un SECONDAIRE (donc a distance 2 de la cible) doit compter.
  D : contre-epreuve moteur -- `calculate_custom_utility` force a 0.

Usage (depuis scripts/python, ASCII only) :
    python probe_27_r5_mortarions_plague_wind.py --build
    python probe_27_r5_mortarions_plague_wind.py            # re-joue sur le runner du state-file
    python probe_27_r5_mortarions_plague_wind.py --dispose
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
SEED_BC = LOGS / "bc_27r5_mortarions_graft.json"
STATE = LOGS / "rs_27r5_mortarions.json"
BOARD = "MC1_67"
SEED = 909

MPW = int(ActiveAbilityType.MortarionsPlagueWind)      # 1093 = 0x445

GRAFT_ON = "deathBlightlord"                            # Death Guard, dans --list-pool
P_UNITS = "deathBlightlord"
# `astraPrimarisPsy` = PSYKER (gameconfig traits ['Hero','Psyker']) ; les trois autres ne le sont
# pas. `thousSorcerer` est ECARTE a dessein : son `ArcaneShield` se declenche au deplacement de
# placement et poserait un bouclier, donc un ecart d'utilite de degat entre les deux bras.
A_UNITS = "astraPrimarisPsy,orksWarboss,necroWarden,astraBullgryn"

CASTER_VID = "deathBlightlord"
PSY_VID = "astraPrimarisPsy"

# PV de `orksWarboss` (cf. le commentaire du build). Les autres a-units restent a `--hp-target`.
HP_T1 = 300000


def _run(args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                          capture_output=True, text=True, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _move(rid: int, unit: int, to) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", "%d,%d" % (to[0], to[1]),
          "--state-file", str(STATE), "--runner", str(rid)])


def _dv(rid: int) -> dict:
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row))} -- les ids ne sont JAMAIS hardcodes."""
    return {u["visualId"]: (u["id"], (u["pos"]["col"], u["pos"]["row"]))
            for u in (_dv(rid).get("units") or []) if u.get("pos")}


def write_graft_seed_bc() -> None:
    """Seed BC (COPIE -- jamais le partage) ou `GRAFT_ON.ActiveAbilities` vaut `[1093]`.

    ⚠ POSER `BC.Units[].ActiveAbilities` NE SUFFIT PAS, et l'echec est SILENCIEUX cote build :
    `MortarionsPlagueWind` est ABSENTE de `BC.Abilities.ActiveAbilities` du seed capture (131
    entrees, mesure), et `refresh_ability_configs` ne fait que RATTRAPER les configs deja
    presentes -- il n'ajoute pas celle d'une ability que personne ne portait. La bataille se
    deploie, l'unite s'affiche avec l'ability... et `abilityTargets` rend `err = "system error"`
    (`AbilityConfiguration$$GetNumberConstant` leve sur cle absente). C'est le meme verrou que
    #226. `catalog_inject.write_grafted_seed_bc(..., kind="active")` fait LES DEUX ecritures
    (config synthetisee depuis le gameconfig VIVANT + liste de l'unite) : on passe par lui."""
    import catalog_inject as C
    LOGS.mkdir(parents=True, exist_ok=True)
    _p, reports = C.write_grafted_seed_bc(SEED_BC, ["%s:MortarionsPlagueWind" % GRAFT_ON],
                                          kind="active")
    import probe_380_seed_bc_patch_survival as S
    S.assert_survives(str(SEED_BC))
    for r in reports:
        print("[graft] %s.ActiveAbilities %s -> %s (configAdded=%s)"
              % (r["unitId"], r["activeAbilitiesBefore"], r["activeAbilitiesAfter"],
                 r["configAdded"]))


def build() -> int:
    write_graft_seed_bc()
    cp = _run(["build", "--seed", str(SEED), "--board", BOARD, "--rank", "17",
               "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
               "--hp-target", "40000",
               # Le caster est FIGE et son attaque normale DESARMEE. Les deux leviers repondent a
               # une mesure, pas a une precaution :
               #  * `Movement=0` -> une seule tuile de cast possible, donc `tile_utility` IDENTIQUE
               #    pour les deux cibles : l'argmax natif ne compare plus que `u_full + custom`.
               #    `abilityTargets(1093).fromHere` vaut 2 depuis l'origine -> les DEUX cibles
               #    restent castables sans bouger (verifie par le probe).
               #  * `Damage=1` -> l'attaque NORMALE devient sans interet. Sans ca, le natif la
               #    prefere a 1093 (mesure : `aiDryRunAllUnits` rend `ActiveAbilityMessage(69)`) et
               #    aucun bras ne mesure quoi que ce soit. Le degat de 1093 n'en depend PAS : c'est
               #    une `AttackWithAbilityDamage` dont la base est `minDmg`/`maxDmg` de la config.
               "--unit-stat", "deathBlightlord:Movement=0,Damage=1",
               # Egalisation de `u_full` entre les deux grappes : a PV nominaux egaux, `orksWarboss`
               # encaisse 1.5x le degat Psychic de `necroWarden` (mesure `aiPlaybookPredict` :
               # 2693-4040 vs 1795-2693), d'ou un ecart de `pairUtility` de ~6.9 -- 7x le terme
               # mesure. On remonte donc SES PV pour ramener l'ecart sous le terme. C'est du
               # CRAFT D'ETAT (on rend le regime discriminant atteignable), pas un fit : la valeur
               # est derivee du ratio de degat MESURE, et le probe RE-VERIFIE l'ecart obtenu.
               "--unit-stat", "orksWarboss:Health=%d,RemainingHealth=%d" % (HP_T1, HP_T1),
               "--state-file", str(STATE)])
    if not STATE.exists():
        raise SystemExit("build KO:\n%s\n%s" % (cp.stdout[-2000:], cp.stderr[-2000:]))
    return _runner_id()


def dispose() -> None:
    if STATE.exists():
        _run(["dispose", "--state-file", str(STATE), "--runner", str(_runner_id())])
        print("[dispose] runner du state-file libere")


### -------------------------------------------------------------------- geometrie des deux bras
#
# Le caster spawne en (1,0) et NE BOUGE JAMAIS (Movement 2 ; ses 8 tuiles atteignables sont
# lues, pas supposees). La geometrie est SYMETRIQUE par construction -- c'est ce qui fait de
# A vs B une difference-de-differences propre :
#
#   T1 = (3,1) et T2 = (0,1) : distance 2 du caster TOUTES LES DEUX (= sa portee), distance 3
#                              l'une de l'autre, voisinages DISJOINTS, aucune n'est voisine de
#                              l'autre ni du caster.
#   V1 = (3,2) et V2 = (0,2) : l'unique voisin ennemi de T1 / de T2, a distance 3 du caster
#                              TOUS LES DEUX (donc NI l'un NI l'autre n'est ciblable directement),
#                              et a distance >= 2 l'un de l'autre (donc AUCUNE vague 3 parasite).
#
# Le voisinage est calcule avec la porte d'elevation `|delta| < 2` d'`IterateAdjacentTiles`.
T1 = (3, 1)
V1 = (3, 2)
T2 = (0, 1)
V2 = (0, 2)

# Les deux CIBLES sont les memes dans les deux bras ; seuls les OCCUPANTS de V1 et V2 sont
# permutes. L'asymetrie residuelle (orksWarboss != necroWarden) est donc CONSTANTE entre les bras :
# si le choix natif BASCULE, le seul terme qui a change est le compte de Psykers.
#
# Bras C -- la VAGUE 3. `W1 = (3,3)` est voisin de `V1 = (3,2)` et N'EST PAS voisin de `T1 = (3,1)`
# (lu au `boardGraph`, porte d'elevation comprise) : un Psyker pose la n'entre dans le compte QUE par
# `t3 = Unique(Enemies(AdjacentUnits(t2))) - t1 - t2`. Si le port ne portait que les deux premieres
# vagues, il rendrait 0 ici.
W1 = (3, 3)

ARMS = {
    "A": {"orksWarboss": T1, "necroWarden": T2, PSY_VID: V1, "astraBullgryn": V2},
    "B": {"orksWarboss": T1, "necroWarden": T2, PSY_VID: V2, "astraBullgryn": V1},
    "C": {"orksWarboss": T1, "necroWarden": T2, "astraBullgryn": V1, PSY_VID: W1},
}


def place(rid: int, layout: dict) -> None:
    """Deplace les 4 ENNEMIS. Le CASTER n'est jamais deplace.

    ⚠ `rl_duel act move` sur une unite du camp ADVERSE rapporte `ok=False err=system error` alors
    que le deplacement EST applique (mesure 2026-08-03) : le rc ne vaut rien ici, seule la position
    relue fait foi -- d'ou `_assert_placed`, qui est la vraie garde du montage."""
    u = _units(rid)
    for vid, to in layout.items():
        if vid not in u:
            raise SystemExit("unite %r absente du runner" % vid)
        _move(rid, u[vid][0], to)
    _assert_placed(rid, layout)


def _assert_placed(rid: int, layout: dict) -> None:
    """Un `act move` REFUSE ne leve rien : les bras degenereraient en UN seul etat, ou l'accord
    natif<->moteur serait trivialement vrai (piege mesure sur #27-4)."""
    got = {v: p for v, (_i, p) in _units(rid).items()}
    bad = [(v, to, got.get(v)) for v, to in layout.items() if got.get(v) != to]
    if bad:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s" % bad)


def _native_choice(rid: int, cid: int) -> list:
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    for u in (dr.get("units") or []):
        if u.get("unitId") == cid:
            return [(m.get("cls"), m.get("abilityType"), m.get("targetId"))
                    for m in (u.get("proposed") or [])]
    return []


def _engine(rid: int, cid: int, targets: dict) -> dict:
    """Decision MOTEUR sur le MEME etat, telle quelle PUIS avec le custom force a 0.

    La seconde est la CONTRE-EPREUVE : si le choix ne bouge pas quand on desarme le terme, c'est
    que l'accord ne vient pas de lui. On rend aussi le custom PAR CIBLE, qui est ce que le port
    calcule et ce que la RE predit."""
    import engine_validate as EV
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
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
    pb = PB.REGISTRY.get(MPW)
    custom = {name: pb.calculate_custom_utility(ctx, ctx.origin, tid, MPW)
              for name, tid in targets.items()}
    # `u_full` du PORT, a comparer au NATIF : c'est lui qui porte le RESIDU de cette tranche
    # (`MortarionsPlagueWindPlaybook$$MakeDamagePredictions` = TROIS batchs
    # `GenerateMultiHitAttackPredictions`, un par vague et par formule ; le port herite du chemin
    # generique mono-cible et n'en rend qu'UN). Mesure, pas supposition.
    uf_port = {}
    for name, tid in targets.items():
        ev = pb.make_damage_predictions(ctx, ctx.origin, tid, MPW)
        uf_port[name] = float(pb.calculate_utility_from_predictions(
            ctx, ctx.origin, tid, MPW, ev)[0])

    on = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = lambda self, c, t, target, aid: 0.0
    try:
        zero = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    return {"on": (on.get("ability"), on.get("target")), "to": on.get("to"),
            "zero": (zero.get("ability"), zero.get("target")), "custom": custom,
            "uf_port": uf_port}


def _pair_utility(rid: int, cid: int, tid: int) -> float:
    """`u_full` NATIF de la paire (1093, cible) = `ComparablePlaybook$$
    CalculateUtilityFromPredictions`. **N'inclut PAS le custom** (`CalculateActionUtility` l'ajoute
    par-dessus) : c'est exactement la reference qui permet de mesurer le terme par difference."""
    return float(L._rpc("pairUtility", [{"runnerId": rid, "unitId": cid, "targetId": tid,
                                         "abilityType": MPW}]).get("utility"))


def run_arm(name: str, rid: int, expect: dict) -> dict:
    place(rid, ARMS[name])
    u = _units(rid)
    cid = u[CASTER_VID][0]
    targets = {"T1": u["orksWarboss"][0], "T2": u["necroWarden"][0]}
    uf = {k: _pair_utility(rid, cid, t) for k, t in targets.items()}
    nat = _native_choice(rid, cid)
    eng = _engine(rid, cid, targets)
    nat_t = [t for _c, ab, t in nat if ab == MPW]
    chosen = ("T1" if nat_t and nat_t[0] == targets["T1"]
              else "T2" if nat_t and nat_t[0] == targets["T2"] else None)
    d_uf = uf["T1"] - uf["T2"]
    print("[bras %s] natif=%s -> cible=%s" % (name, nat, chosen))
    print("          u_full NATIF T1=%.4f T2=%.4f  delta(T1-T2)=%+.4f" % (uf["T1"], uf["T2"], d_uf))
    print("          custom PORT=%s (attendu %s)" % (eng["custom"], expect["custom"]))
    print("          moteur on=%s zero=%s to=%s  [u_full PORT T1=%.4f T2=%.4f]"
          % (eng["on"], eng["zero"], eng["to"], eng["uf_port"]["T1"], eng["uf_port"]["T2"]))
    ok_custom = eng["custom"] == expect["custom"]
    ok_native = chosen == expect["chosen"]
    # LE POINT DE MESURE : le natif retient la cible que le TERME designe, alors que son PROPRE
    # `u_full` favorise l'AUTRE. Sans le terme, l'argmax natif serait celui de `u_full`.
    against = (d_uf < 0 and expect["chosen"] == "T1") or (d_uf > 0 and expect["chosen"] == "T2")
    print("          natif attendu=%s -> %s | custom -> %s | choix CONTRE u_full -> %s"
          % (expect["chosen"], "OK" if ok_native else "KO",
             "OK" if ok_custom else "KO", "OUI" if against else "non"))
    return {"arm": name, "native": nat, "chosen": chosen, "targets": targets, "uf_native": uf,
            "d_uf": d_uf, "against": against, **eng,
            "ok_custom": ok_custom, "ok_native": ok_native}


EXPECT = {"A": {"custom": {"T1": 1.0, "T2": 0.0}, "chosen": "T1"},
          "B": {"custom": {"T1": 0.0, "T2": 1.0}, "chosen": "T2"},
          # C : le Psyker n'est atteint QUE par la vague 3. `chosen` = T1 sans surprise (T1 porte
          # alors DEUX unites secondaires/tertiaires, donc un `u_full` bien plus haut) -- ce bras ne
          # mesure PAS une preference, il mesure que le PORT compte la 3e vague.
          "C": {"custom": {"T1": 1.0, "T2": 0.0}, "chosen": "T1"}}

# Encadrement de la MAGNITUDE (bras A). On fait varier `u_full(T1)` par les PV de T1 -- le seul
# levier qui bouge `u_full` SANS toucher a la geometrie ni aux traits -- et on lit ou le natif
# BASCULE. Si le terme vaut 1 par Psyker, il tient T1 tant que `u_full(T2) - u_full(T1) < 1` et
# lache au-dela. Les deux points encadrent donc la constante, qui cesse d'etre seulement LUE.
MAGNITUDE = ((512000, -0.90, "T1"), (736000, -1.10, "T2"))


def run_magnitude() -> bool:
    ok = True
    for hp, d_want, chosen_want in MAGNITUDE:
        global HP_T1
        HP_T1 = hp
        rid = build()
        place(rid, ARMS["A"])
        u = _units(rid)
        cid, t1, t2 = u[CASTER_VID][0], u["orksWarboss"][0], u["necroWarden"][0]
        d = _pair_utility(rid, cid, t1) - _pair_utility(rid, cid, t2)
        nat = _native_choice(rid, cid)
        sel = [t for _c, ab, t in nat if ab == MPW]
        got = "T1" if sel and sel[0] == t1 else "T2" if sel and sel[0] == t2 else str(nat)
        good = abs(d - d_want) < 0.02 and got == chosen_want
        ok = ok and good
        print("[magnitude] HP(T1)=%-7d delta(T1-T2)=%+.4f (vise %+.2f) natif -> %s (attendu %s) %s"
              % (hp, d, d_want, got, chosen_want, "OK" if good else "KO"))
    print("[magnitude] => terme natif pour 1 Psyker encadre dans (%.2f, %.2f) ; le port rend 1.0"
          % (-MAGNITUDE[0][1], -MAGNITUDE[1][1]))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--dispose", action="store_true")
    ap.add_argument("--arm", choices=sorted(ARMS), help="joue UN bras sur le runner courant")
    ap.add_argument("--magnitude", action="store_true", help="encadre la constante par bascule")
    ap.add_argument("--all", action="store_true", help="A + B + C + magnitude (rebuild par bras)")
    a = ap.parse_args()
    if a.dispose:
        dispose()
        return 0
    if a.all:
        ok = True
        for arm in ("A", "B", "C"):
            rid = build()
            r = run_arm(arm, rid, EXPECT[arm])
            ok = ok and r["ok_custom"] and r["ok_native"]
        ok = run_magnitude() and ok
        print("VERDICT: %s" % ("PASS" if ok else "FAIL"))
        return 0 if ok else 1
    if a.magnitude:
        return 0 if run_magnitude() else 1
    rid = build() if a.build else _runner_id()
    print("[runner] %d" % rid)
    for vid, (uid, pos) in sorted(_units(rid).items()):
        print("   %-22s id=%-5s pos=%s" % (vid, uid, pos))
    if a.arm:
        r = run_arm(a.arm, rid, EXPECT[a.arm])
        return 0 if (r["ok_custom"] and r["ok_native"]) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
