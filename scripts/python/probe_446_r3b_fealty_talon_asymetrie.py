"""#446-r3b -- `Fealty` et `TalonOfHorus` : un MIRROR a ATTESTER, pas un trou a combler.

## Ce que dit le decompile (re-lu sur le build courant)

Les QUATRE `<X>_NormalAttackAbility` de la famille (`Boltstorm`, `RighteousRepugnance`, `Fealty`,
`TalonOfHorus`) ont la MEME forme d'EXECUTION :

    <X>_NormalAttackAbility$$ExecuteBehaviour(abilityState, entities):
        weapon = ALoki_NormalAttackAbility$$FindAttackWeapon(entities)
        if (weapon == null) return
        if (weapon.get_IsMelee())  return Execute<X>(abilityState, entities, weapon)
        else                       return ALoki_NormalAttackAbility$$ExecuteBehaviour(...)

    <X>_NormalAttackAbility$$Execute<X>(abilityState, entities, weapon):
        sel = <X>Ability$$GetAdditionalTargets(dsl)            # Triggered.Loki.<X>Ability
        ALoki_NormalAttackAbility$$ExecuteInformWeapon(weapon, entities, null)
        ALoki_NormalAttackAbility$$ExecuteNormalAttack(abilityState, entities, weapon)
        b = DSLBehaviors$$Foreach(sel, t => GetAdditionalTargetsAttackBehavior(t, abilityState))
        AActiveAbility$$ExecuteAtomic(b, entities, 0x2a)
        return ALoki_NormalAttackAbility$$ExecuteTriggerAbilities(entities, weapon)

    <X>_NormalAttackAbility$$GetAdditionalTargetsAttackBehavior(target, abilityState):
        return DSLBehaviors$$Attack(caster, target,
                                    GetAdditionalDamageBehaviour(abilityState, target), ctx)

⚠ L'UNIQUE consommateur de `<X>_NormalAttackAbility$$GetAdditionalDamageBehaviour` est donc
`$$GetAdditionalTargetsAttackBehavior`, et sa cible est une cible **ADDITIONNELLE** -- jamais la
cible PRIMAIRE. La face COMBAT n'est PAS un « fold sur la cible » : c'est un **CLEAVE**.

Cote DECISION, seuls `Boltstorm` et `RighteousRepugnance` portent `$$PredictAttack` +
`$$GetAdditionalDamagePrediction`, et ceux-la ATTRIBUENT un paquet de degat additionnel a la cible
PRIMAIRE (mesure #446-r1 / #446-r3, deja mirroree). `Fealty` et `TalonOfHorus` n'ont **ni l'un ni
l'autre** : leur prediction est la base `ALoki` NUE.

Le texte i2 corrobore, et c'est une SECONDE SOURCE independante du decompile :
  * `RighteousRepugnance` : « deal an additional [...] Damage **to the target** and to all enemy
    units adjacent to both the target and to Morvenn Vahl » ;
  * `TalonOfHorus`        : « he also deals [...] Damage to all enemies adjacent to both the target
    of the attack and to Abaddon » -- **aucune clause « to the target »**.

L'asymetrie est donc DESSINEE, pas un oubli. Inscrire ces deux abilities au registre
`_MELEE_FOLLOWUP_PASSIVES` « par coherence » serait un FORK de port.

## Ce que ce probe MESURE

UN seul runner, TROIS porteurs sur la MEME cible, et un DIFFERENTIEL a trois lignes -- c'est lui
qui interdit le regime degenere (« les deux modeles rendent la meme chose pour une raison
structurelle ») :

    natif  vs  port LIVRE                    -> ACCORD attendu sur les TROIS
    natif  vs  port SANS registre de fold    -> DIVERGE sur `adeptMorvenn` (le fold manque),
                                                ACCORDE sur les deux autres (rien a retirer)
    natif  vs  port AVEC le fold GREFFE      -> ACCORDE sur `adeptMorvenn`,
                                                DIVERGE sur les deux autres (fold ajoute a tort)

La 2e ligne prouve que la mesure SAIT VOIR un fold ; la 3e prouve qu'elle sait voir son ABSENCE.
Sans elles, « natif et port sont d'accord » ne vaudrait rien.

`adeptMorvenn` porte `RighteousRepugnance` NATURELLEMENT (aucune greffe) : c'est le TEMOIN POSITIF,
mesure sur le meme board, le meme seed et la meme cible que les deux porteurs greffes.

Le volet `combat` execute l'attaque normale LIVE et lit les PV de la cible ADDITIONNELLE : c'est la
mesure de la face COMBAT (« le degat additionnel est-il bien inflige ? »).

Usage :
    python scripts/python/probe_446_r3b_fealty_talon_asymetrie.py --state-file <ABSOLU>.json
        [--volet decision|combat|all] [--board MC1_67] [--seed 4463111]

ASCII only. Garde jumelle : `scripts/python/tests/engine/test_446_r3b_fealty_talon_live.py`.
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

import hexgeo                                                    # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType         # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402

BOARD = "MC1_67"
SEED = "4463111"
HP = 60000               # personne ne meurt : `Health` ET `RemainingHealth` (le cleave frappe fort)

TARGET = "astraBullgryn"     # la cible PRIMAIRE de l'attaque normale
ADDT = "necroWarden"         # la cible ADDITIONNELLE (ennemie du caster, adjacente au caster ET a T)

#: `(visualId, passif, TriggeredAbilityType, ActiveAbilityType de l'attaque normale, folde en
#: DECISION, doit etre GREFFE)`. `adeptMorvenn` est le TEMOIN POSITIF : il porte son passif
#: naturellement et le natif folde pour lui (#446-r3, mesure).
#: Les deux familles d'ids passent par leur ENUM -- un ordinal juste aujourd'hui devient faux au
#: changement de build, en silence (regle « un ENTIER qui DESIGNE passe par un ENUM »).
CARRIERS = (
    ("ultraTitus",   "Fealty",
     int(TriggeredAbilityType.Fealty), int(ActiveAbilityType.Fealty_NormalAttack), False, True),
    ("blackAbaddon", "TalonOfHorus",
     int(TriggeredAbilityType.TalonOfHorus), int(ActiveAbilityType.TalonOfHorus_NormalAttack),
     False, True),
    ("adeptMorvenn", "RighteousRepugnance",
     int(TriggeredAbilityType.RighteousRepugnance),
     int(ActiveAbilityType.RighteousRepugnance_NormalAttack), True, False),
)
CLEAVERS = ("ultraTitus", "blackAbaddon")    # ceux dont la cible ADDITIONNELLE doit etre installee

_CMP_KEYS = ("rawHealthDmgMin", "rawHealthDmgMax", "healthDmgMin", "healthDmgMax", "appliedHits")


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- geometrie OFFLINE

def _board_dump(board_id: str) -> dict:
    import rl_collect_batch as R
    for kind in ("pvp", "syncPvp", "global"):
        p = R.BOARDS_DIR / kind / f"{board_id}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise MontageError(f"board dump introuvable pour {board_id} -- `python dump_boards.py` "
                       f"le regenere (artefact per-hash)")


def board_geometry(board_id: str) -> tuple[dict, set]:
    """`{(col,row): elevation}` + l'ensemble des tuiles JOUABLES, lus OFFLINE dans le dump."""
    import board as B
    dump = _board_dump(board_id)
    bd = B.Board({"Board": dump["board"], "SpawnPointSetIndex": dump.get("spawnPointsSet", 0)})
    playable = set(bd.playable_tiles().keys())
    elev = {p: t.get("elevation", 0) for p, t in bd.playable_tiles().items()}
    return elev, playable


def find_layout(elev: dict, playable: set) -> dict | None:
    """Cherche `T` (cible primaire), `A` (cible ADDITIONNELLE) et les TROIS tuiles de porteur.

    Contraintes, toutes au sens NATIF (`bq.is_adjacent`, porte d'elevation `|delta| < 2`) :
      * chaque porteur est ADJACENT a `T`   -> la gate `IsMelee` est exercee pour les trois ;
      * `A` est ADJACENTE a `T` **et** aux tuiles des DEUX porteurs greffes -> `A` appartient a
        `<X>Ability$$GetAdditionalTargets` pour eux, donc le CLEAVE natif a bien une cible.
        Sans cette derniere contrainte, « pas de fold en decision » se mesurerait dans un regime ou
        il n'y a de toute facon RIEN d'additionnel -- une mesure vide.
    """
    cells = sorted(playable)
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    for t in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        ring = [q for q in hexgeo.neighbors(t[0], t[1])
                if q in playable and bq.is_adjacent(t, q, elev)]
        if len(ring) < 4:
            continue
        for a in ring:
            near = [q for q in ring if q != a and bq.is_adjacent(a, q, elev)]
            far = [q for q in ring if q != a and q not in near]
            if len(near) < len(CLEAVERS) or not far:
                continue
            return {"T": t, "A": a,
                    "C": {CLEAVERS[0]: near[0], CLEAVERS[1]: near[1],
                          CARRIERS[2][0]: far[0]}}
    return None


# --------------------------------------------------------------------------- build

def write_seed_bc(out_path: str) -> str:
    """Le seed BC du montage : la GREFFE des deux passifs, par le foyer `catalog_inject`.

    ⚠ `--unit-stat "X:PassiveAbilities=[<id>]"` NE SUFFIT PAS, et le croire coute une mesure : il
    n'ecrit QUE `BC.Units[].PassiveAbilities`. Or `Fealty` et `TalonOfHorus` sont **absentes de
    `BC.Abilities.PassiveAbilities`** du seed (leurs porteurs de catalogue sont un npc et la voie
    ITEM, donc `refresh_ability_configs` ne les derive pas non plus -- MESURE, pas supposition).
    La face DECISION s'en moque (`PredictAttack` ne lit aucune config), mais la face COMBAT lit
    `AbilityConfiguration$$GetVariableForLevel(0xc/0xd)` dans
    `<X>_NormalAttackAbility$$GetAdditionalDamageBehaviour` : config nulle -> exception managee ->
    « system error » au cast, MEME verrou que #226/#237. MESURE du premier passage de ce probe :
    l'attaque PRIMAIRE passe (2493 PV retires) puis le cleave FAUTE -- ce qui prouve au passage que
    le natif entre bien dans la branche cleave en melee, mais rend la mesure inexploitable.
    `graft_passive_ability` fait les DEUX ecritures."""
    import catalog_inject
    import probe_380_seed_bc_patch_survival as P380
    specs = [f"{v}:{n}" for (v, n, _p, _a, _f, graft) in CARRIERS if graft]
    p, reports = catalog_inject.write_grafted_seed_bc(out_path, specs)
    for r in reports:
        if not r.get("unitsPatched"):
            raise MontageError(f"greffe NON INSTALLEE : {r}")
    P380.assert_survives(str(p))
    return str(p)


def build_args(lay: dict, bc_path: str, board: str = BOARD) -> list[str]:
    """Les arguments `rl_duel build` du montage -- FOYER UNIQUE, partage par le probe et par la
    garde jumelle (elle passe par la fixture `build_runner`, qui gere son propre state-file)."""
    hp = [f"{v}:Health={HP},RemainingHealth={HP}"
          for v in [c[0] for c in CARRIERS] + [TARGET, ADDT]]
    places = []
    for v, _n, _p, _a, _f, _g in CARRIERS:
        c, r = lay["C"][v]
        places += ["--place", f"{v}:{c},{r}"]
    for v, tile in ((TARGET, lay["T"]), (ADDT, lay["A"])):
        places += ["--a-place", f"{v}:{tile[0]},{tile[1]}"]
    return ["--board", board, "--seed-bc", bc_path,
            "--p-units", ",".join(v for v, *_ in CARRIERS),
            "--a-units", f"{TARGET},{ADDT}",
            *places, "--unit-stat", ";".join(hp)]


def build(state_file: str, board: str, seed: str, lay: dict, extra: list[str]) -> int:
    bc_path = os.path.splitext(state_file)[0] + ".seedbc.json"
    write_seed_bc(bc_path)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", state_file,
            *build_args(lay, bc_path, board), *extra]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-900:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


# --------------------------------------------------------------------------- montage

def _fresh_ctx(rpc, rid, cid, dv=None, mbu=None):
    if dv is None:
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    if mbu is None:
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
        mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))


def stage(sid, rpc, rid: int, lay: dict, elev: dict) -> dict:
    """Installe et ATTESTE tout ce dont la mesure depend. Toute attestation manquante leve
    `MontageError` -- jamais un vert silencieux."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mine = [u for u in units if u.get("ctrl")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    myplayer = mine[0].get("owner")
    uid = {}
    for v, *_ in CARRIERS:
        u = next((x for x in mine if x.get("visualId") == v), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {v} absent du roster controle")
        uid[v] = u["id"]
    for v in (TARGET, ADDT):
        u = next((x for x in units if x.get("owner") != myplayer and x.get("visualId") == v), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {v} absent du roster adverse")
        uid[v] = u["id"]

    pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units if u.get("pos")}
    # (a) LES POSITIONS voulues -- `--place`/`--a-place` les pose au build ; on VERIFIE, on ne
    #     suppose pas (le natif refuse silencieusement une tuile reservee/en fog).
    want = {uid[v]: tuple(lay["C"][v]) for v, *_ in CARRIERS}
    want[uid[TARGET]] = tuple(lay["T"])
    want[uid[ADDT]] = tuple(lay["A"])
    bad = {u: (pos.get(u), w) for u, w in want.items() if pos.get(u) != w}
    if bad:
        raise MontageError(f"montage NON INSTALLE : placement {bad} (obtenu, voulu)")

    tp = pos[uid[TARGET]]
    ap_ = pos[uid[ADDT]]
    # (b) LE REGIME MELEE, porteur par porteur. Sans lui la gate `IsMelee` n'est pas exercee.
    for v, *_ in CARRIERS:
        if not bq.is_adjacent(pos[uid[v]], tp, elev):
            raise MontageError(f"regime MELEE NON INSTALLE : {v} {pos[uid[v]]} n'est PAS adjacent "
                               f"NATIF a la cible {tp}")
    # (c) LE CLEAVE ARME pour les deux porteurs greffes : `A` adjacente a `T` ET au porteur.
    if not bq.is_adjacent(ap_, tp, elev):
        raise MontageError(f"regime CLEAVE NON INSTALLE : {ADDT} {ap_} n'est PAS adjacent NATIF "
                           f"a la cible {tp}")
    for v in CLEAVERS:
        if not bq.is_adjacent(ap_, pos[uid[v]], elev):
            raise MontageError(f"regime CLEAVE NON INSTALLE : {ADDT} {ap_} n'est PAS adjacent "
                               f"NATIF au porteur {v} {pos[uid[v]]} -- « pas de fold en decision » "
                               f"se mesurerait la ou il n'y a RIEN d'additionnel")

    # (d) L'ATTAQUE NORMALE LIVE, porteur par porteur : c'est L'ATTESTATION centrale. `1220`/`1205`
    #     prouvent que la greffe a mordu (sans elle, `ultraTitus`/`blackAbaddon` rendraient `69`) ;
    #     `1182` prouve que le temoin positif est bien la sous-classe surchargeante.
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    cases = {}
    for v, passive, tid, want_ab, folds, _g in CARRIERS:
        ctx = _fresh_ctx(rpc, rid, uid[v], dv, mbu)
        ab = next(iter(ctx.normal_ids or ()), None)
        if ab is None or int(ab) != want_ab:
            raise MontageError(f"montage NON INSTALLE : l'attaque normale live de {v} est {ab}, "
                               f"attendu {want_ab} -- la sous-classe n'est PAS instanciee")
        st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": uid[v]}, 60) or {}
        live = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
        if tid not in live:
            raise MontageError(f"montage NON INSTALLE : {tid} ({passive}) n'est PAS dans "
                               f"l'AbilitiesComponent de {v} -- triggered lus {sorted(set(live))}")
        cases[v] = {"vis": v, "passive": passive, "uid": uid[v], "ab": int(ab), "ctx": ctx,
                    "tile": tuple(pos[uid[v]]), "folds": folds}
    return {"rid": rid, "myplayer": myplayer, "uid": uid, "pos": pos, "cases": cases,
            "tpos": tp, "apos": ap_, "dv": dv}


# --------------------------------------------------------------------------- oracles

def native_fields(rpc, rid, cid, tgt, ab, tile) -> dict:
    """`aiPlaybookPredict` -- les champs de l'event que le playbook NATIF construit pour la paire,
    predits DEPUIS `tile`. Oracle de l'etage PREDICTION (cf. #446-r3 : surtout pas `pairUtility`,
    qui porte encore l'ecart du playbook TRIGGERED non porte)."""
    import engine_agreement_stages as EAS
    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                                  "abilityType": ab, "col": tile[0], "row": tile[1]}, 60) or {}
    if not r.get("ok"):
        raise MontageError(f"aiPlaybookPredict indisponible depuis {tile} / cible {tgt} : {r}")
    evs = r.get("events") or []
    ev = next((e for e in evs if e.get("targetId") == tgt), evs[0] if evs else None)
    if ev is None:
        raise MontageError(f"aiPlaybookPredict ne rend AUCUN event depuis {tile} / cible {tgt}")
    return EAS._fields_from_native_event(ev, block_amount=0)


def port_fields(scene, cid, tgt, tile) -> dict:
    from engine.playbook.prediction import make_normal_attack_predictions
    ev = make_normal_attack_predictions(scene, cid, tgt, tile)
    if ev is None:
        raise MontageError(f"le port ne produit AUCUNE prediction depuis {tile} sur {tgt}")
    return ev.composite_fields()


def compare(off_f: dict, nat_f: dict) -> dict:
    """Diff CHAMP A CHAMP restreint aux champs qu'un fold peut deplacer. Dict VIDE = accord."""
    return {k: {"port": off_f.get(k), "nat": nat_f.get(k)}
            for k in _CMP_KEYS if off_f.get(k) != nat_f.get(k)}


# --------------------------------------------------------------------------- volet DECISION

def _port_all(case_all: dict, tgt: int) -> dict:
    return {v: port_fields(c["ctx"].scene, c["uid"], tgt, c["tile"])
            for v, c in case_all["cases"].items()}


def measure_decision(rpc, st: dict) -> dict:
    """Le DIFFERENTIEL a trois lignes. Rend `{visualId: {...}}`."""
    import engine.playbook.prediction.normal_attack as NA
    tgt = st["uid"][TARGET]
    nat = {v: native_fields(rpc, st["rid"], c["uid"], tgt, c["ab"], c["tile"])
           for v, c in st["cases"].items()}
    livre = _port_all(st, tgt)

    saved = NA._MELEE_FOLLOWUP_PASSIVES
    try:
        NA._MELEE_FOLLOWUP_PASSIVES = ()
        nofold = _port_all(st, tgt)
        NA._MELEE_FOLLOWUP_PASSIVES = tuple(saved) + tuple(
            st["cases"][v]["passive"] for v in CLEAVERS)
        foldall = _port_all(st, tgt)
    finally:
        NA._MELEE_FOLLOWUP_PASSIVES = saved

    out = {}
    for v, c in st["cases"].items():
        out[v] = {"passive": c["passive"], "ab": c["ab"], "tile": c["tile"], "folds": c["folds"],
                  "nat": {k: nat[v].get(k) for k in _CMP_KEYS},
                  "port": {k: livre[v].get(k) for k in _CMP_KEYS},
                  "d_livre": compare(livre[v], nat[v]),
                  "d_nofold": compare(nofold[v], nat[v]),
                  "d_foldall": compare(foldall[v], nat[v])}
    return out


def verdict_decision(rows: dict) -> list[str]:
    """Les trois lignes du differentiel, en assertions NOMMEES. Rend la liste des echecs."""
    bad = []
    for v, r in rows.items():
        if r["d_livre"]:
            bad.append(f"{v} : le port LIVRE diverge du natif -- {json.dumps(r['d_livre'])}")
        if r["folds"]:
            if not r["d_nofold"]:
                bad.append(f"{v} (temoin POSITIF) : vider le registre de fold ne DEPLACE RIEN -- "
                           f"la mesure ne sait pas voir un fold, l'accord des autres est vide")
            if r["d_foldall"]:
                bad.append(f"{v} (temoin POSITIF) : greffer le fold des DEUX autres le fait "
                           f"diverger -- {json.dumps(r['d_foldall'])}")
        else:
            if r["d_nofold"]:
                bad.append(f"{v} : vider le registre DEPLACE le port -- il foldait donc, "
                           f"contrairement au natif : {json.dumps(r['d_nofold'])}")
            if not r["d_foldall"]:
                bad.append(f"{v} : greffer le fold « par analogie » ne DEPLACE RIEN -- le "
                           f"discriminant est MORT, l'accord natif/port ne prouve rien")
    return bad


# --------------------------------------------------------------------------- volet COMBAT

def _hp(rpc, rid) -> dict:
    """PV par `visualId`. ⚠ La cle est le VISUALID, pas l'id : `observeBattle` indexe par
    `entityId` (78, 84, 86...) tandis que `decisionView` rend le `squadId` (77, 83, 85...) --
    croiser les deux directement rend un dict de deltas NULS qui se lit comme « rien n'a bouge ».
    Mesure du premier passage : l'attaque avait bien retire 2493 et 3104 PV, sur `u84`/`u86`, alors
    que les cibles etaient nommees `u83`/`u85`. Les visualIds du montage sont UNIQUES (verifie)."""
    ob = rpc("observeBattle", {"runnerId": rid}, 60) or {}
    out, seen = {}, set()
    for u in (ob.get("units") or []):
        v, h = u.get("visualId"), u.get("hp")
        if v is None or h is None:
            continue
        if v in seen:
            raise MontageError(f"visualId {v} en double dans observeBattle -- la cle de PV ne "
                               f"discrimine plus les unites")
        seen.add(v)
        out[v] = int(h)
    if not out:
        raise MontageError(f"observeBattle ne rend aucun PV lisible : {str(ob)[:200]}")
    return out


def measure_combat(rpc, st: dict, vis: str) -> dict:
    """Execute l'attaque normale LIVE de `vis` sur la cible PRIMAIRE et lit les PV AVANT/APRES.

    Ce que ca tranche : la cible ADDITIONNELLE perd-elle des PV ? Si oui, la face COMBAT native
    inflige bien le degat du cleave -- ce que le port, lui, ne modelise NULLE PART (son unique
    vecteur d'attaque normale est `damage_ops._Normal.execute(attacker, target)`, MONO-cible)."""
    c = st["cases"][vis]
    before = _hp(rpc, st["rid"])
    res = rpc("applyAction", {"runnerId": st["rid"], "captureEvents": True,
                              "action": {"kind": "ability", "casterId": c["uid"],
                                         "targetId": st["uid"][TARGET],
                                         "abilityType": c["ab"]}}, 120) or {}
    acts = (res.get("actions") or [{}])[0]
    if res.get("ok") is False or acts.get("ok") is False or acts.get("error"):
        raise MontageError(f"cast live REFUSE pour {vis} : {str(res)[:400]}")
    after = _hp(rpc, st["rid"])
    dmg = {v: before[v] - after.get(v, 0) for v in before if before[v] != after.get(v, 0)}
    return {"vis": vis, "ability": c["ab"],
            "primaire": before.get(TARGET, 0) - after.get(TARGET, 0),
            "additionnelle": before.get(ADDT, 0) - after.get(ADDT, 0),
            "tous_deltas": dmg}


def port_cleave_sites() -> list[str]:
    """Recense, DANS le port COMBAT, ce qui implementerait le cleave. Perimetre DERIVE (balayage de
    `engine/runner/**`), pas une liste ecrite a la main : si quelqu'un le porte un jour, ce
    recensement le voit."""
    import re
    root = os.path.join(_HERE, "engine", "runner")
    # Perimetre : les symboles du CLEAVE **de cette famille** uniquement. `GetAdditionalTargets`
    # NU est un nom partage par d'autres abilities (`MalleusRocketLauncher`,
    # `HarbingerOfDestruction`) deja portees -- le qualifier evite un faux positif.
    fam = "(Fealty|TalonOfHorus|RighteousRepugnance|Boltstorm)"
    pat = re.compile(fam + r"\w*(Ability)?\$\$(GetAdditionalTargets"
                     r"|GetAdditionalTargetsAttackBehavior|GetAdditionalDamageBehaviour)"
                     r"|\$\$Execute" + fam
                     + r"|execute_(fealty|talon_of_horus|righteous_repugnance|boltstorm)_cleave")
    hits = []
    for base, _d, files in os.walk(root):
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(base, f)
            with open(p, encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    if pat.search(line):
                        hits.append(f"{os.path.relpath(p, _HERE)}:{n}")
    return hits


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--runner", type=int, default=None, help="reutilise un runner deja monte")
    ap.add_argument("--volet", default="all", choices=("decision", "combat", "all"))
    ap.add_argument("--armor-target", default=None, help="generalisation : armure des a-units")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    elev, playable = board_geometry(args.board)
    lay = find_layout(elev, playable)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucune configuration (T, A, 3 porteurs) sur "
                           f"{args.board} -- il faut une tuile a >=4 voisins natifs")
    extra = ["--armor-target", args.armor_target] if args.armor_target else []
    rid = args.runner or build(args.state_file, args.board, args.seed, lay, extra)
    st = stage(sid, rpc, rid, lay, elev)
    print(f"runner {rid} | board {args.board} seed {args.seed}")
    print(f"  layout T={lay['T']} A={lay['A']} porteurs={lay['C']}")

    rc = 0
    if args.volet in ("decision", "all"):
        rows = measure_decision(rpc, st)
        print("  --- DECISION (aiPlaybookPredict vs make_normal_attack_predictions) ---")
        for v, r in rows.items():
            tag = "FOLDE" if r["folds"] else "NE FOLDE PAS"
            print(f"  [{v:<13} {r['passive']:<20} attaque normale {r['ab']}] natif {tag}")
            print(f"      NAT ={r['nat']}")
            print(f"      PORT={r['port']}   -> "
                  f"{'ACCORD' if not r['d_livre'] else 'DELTA ' + json.dumps(r['d_livre'])}")
            print(f"      port SANS registre  : "
                  f"{'accord' if not r['d_nofold'] else 'DIVERGE ' + json.dumps(r['d_nofold'])}")
            print(f"      port fold GREFFE    : "
                  f"{'accord' if not r['d_foldall'] else 'DIVERGE ' + json.dumps(r['d_foldall'])}")
        bad = verdict_decision(rows)
        for b in bad:
            print(f"  [ECHEC] {b}")
        rc |= 1 if bad else 0

    if args.volet in ("combat", "all"):
        print("  --- COMBAT (execution live de l'attaque normale) ---")
        sites = port_cleave_sites()
        print(f"      port COMBAT : {len(sites)} site(s) implementant le cleave -> {sites}")
        for v in CLEAVERS:
            m = measure_combat(rpc, st, v)
            print(f"  [{v:<13} ability {m['ability']}] PV perdus : "
                  f"cible PRIMAIRE {TARGET} = {m['primaire']} | "
                  f"cible ADDITIONNELLE {ADDT} = {m['additionnelle']}")
            print(f"      tous les deltas de PV = {m['tous_deltas']}")
            if m["additionnelle"] <= 0:
                print(f"  [ECHEC] {v} : la cible ADDITIONNELLE ne perd AUCUN PV -- le cleave natif "
                      f"n'a pas eu lieu, la face COMBAT n'est PAS mesuree")
                rc |= 2
    print(f"  (runner {rid} -- pense a le disposer)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
