"""#940 -- `KissOfDeath` (ActiveAbilityType **1108**) confrontee au NATIF sur un runner live.

Avant #940 la face COMBAT etait un **NO-OP SILENCIEUX** : `ABILITY_CLASSES` ne connaissait pas
1108, donc l'IA la choisissait et l'execution n'en faisait RIEN -- zero degat, aucune erreur.

CE QUE CE PROBE MESURE (chaque etage a son propre oracle NATIF) :

  [1] CIBLAGE        : `abilityTargets` du natif vs le masque porte. Le `.ctor` RECOPIE le preset
                       statique `<TargetingOptions statics>+0x40`, donc le masque effectif est la
                       constante du `.cctor` a `<preset>+0x28` = `<statics>+0x68` = **0x4000** =
                       `TargetIsEnemy` SEUL. L'oracle est le natif lui-meme : il n'enumere que des
                       ennemis, et refuse l'allie comme le self.
  [2] CIBLES DE LA CHAINE : l'ENSEMBLE exact des unites frappees, port (pre-cast) vs natif (events
                       du cast). Le montage est construit pour que ce soit DISCRIMINANT :
                       `M2` n'est adjacent QU'A `M1`, jamais a la cible designee -- il n'est donc
                       atteignable que si le `jumpTargetSelector` recoit la LISTE COMPLETE des
                       cibles deja piquees (`Entities(pickedTargets)`), ce que dit l'i2 par
                       « adjacent to A PREVIOUS target ». Et `W`, adjacent a `M2`, ne doit PAS
                       etre frappe : `maxAdjacentTargets = 2` BORNE les sauts.
  [3] ATTERRISSAGE   : la tuile finale du Harlequin. Le natif la choisit par
                       `First(SortTilesByUtility(CanAddUnit(AdjacentTiles(Last(
                       UnitsAttackedThisTurn(Caster), 1))) - CasterTile, Caster, 7 = Tile), 1)`.
                       On assertionne la PROPRIETE que l'i2 enonce (« reappears in a hex adjacent
                       to the last target hit ») ET l'egalite exacte avec le natif.
  [4] EFFET 1044     : `Untargetable` est POSE sur le caster puis RETIRE dans le MEME cast --
                       les deux membres extremes de l'`op_BitwiseAnd`. Oracle = les events
                       `ReceiveEffect` / `LoseEffect` sur l'entite du caster.
  [5] DEGAT          : profil et `Active_Ability_Type` des events, et le montant NU du port
                       (`Direct(GetVariableForLevel(0xb = dmg))`) rapporte a cote du natif.
                       ⚠ Cet etage RAPPORTE plus qu'il n'assertionne le montant : les cibles du
                       montage portent des passifs orks de reduction que le port ne modelise pas
                       tous, et un montant qui « tombe juste » sur une cible ne prouverait rien
                       (loi « jamais fitter un scalaire »). Ce qui est ASSERTIONNE : le profil
                       (`DamageProfileType 15 = DirectDamage`, la constante LUE de la config) et
                       l'id d'ability threade.
  [6] MUTANTS        : cinq mutations du port, chacune doit MORDRE (changer le resultat observable).
                       Un mutant inerte est une question, pas un succes.

MONTAGE -- il est CHOISI, pas subi (`docs/rl/case-92-catalog-injection.md` §5bis point 4) :
`eldarNpc3Harlequin` est un **npc** porteur de 1108, et `--explicit-stats <id>:<palier>` le monte
avec SES stats, SES traits et SON arme (`GetNpcStats` -> `units.npc[id].stats[]`) -- c'est le
MIRROR, pas la greffe. L'autre porteur, `eldarSmnHarlequin`, est un **summon** dont le summoner
n'est PAS une unite : l'unique ability dont `constants.unitId` vaut `eldarSmnHarlequin` est
`EnvFactionSummons:Aeldari`, rattachee a AUCUNE unite du catalogue (spawner d'ENVIRONNEMENT) --
la voie « spawner son summoner » est donc FERMEE, et c'est mesure, pas suppose.

GEOMETRIE (board `MC1_67`, calculee par `hexgeo.neighbors`, jamais subie) :

    H  (3,3)  le Harlequin
    T  (3,4)  adjacent a H            <- la cible DESIGNEE (preselectedTargets)
    M1 (3,5)  adjacent a T, PAS a H   <- 1er saut
    M2 (2,5)  adjacent a M1, PAS a T  <- 2e saut : LE DISCRIMINANT du `jumpTargetSelector`
    W  (1,6)  adjacent a M2 SEUL      <- temoin de la BORNE `maxTargets`

Sortie ASCII stricte (console cp1252). Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_940_kiss_of_death_live.py [--state-file <absolu>] [--keep]
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"       # SORTIES -> logs/, jamais data/ (#349)

KISS_OF_DEATH = 1108                # ActiveAbilityType.KissOfDeath
UNTARGETABLE = 1044                 # EffectType.Untargetable
DIRECT_DAMAGE = 15                  # DamageProfileType.DirectDamage
BOARD = "MC1_67"
CARRIER = "eldarNpc3Harlequin:40"   # npc porteur de 1108, monte par --explicit-stats (case-92 §5bis.4)
FOES = "orksNob,orksRuntherd,orksBigMek,orksWarboss"

#: Le placement, en DEUX passes : chaque `move` est borne par le `Movement` de l'unite, donc les
#: deux unites les plus lointaines franchissent la distance en deux sauts. Les tuiles finales sont
#: celles de l'en-tete ; les intermediaires n'ont aucune signification.
PLACEMENT = (
    # (unit_key, (col, row)) -- `unit_key` est resolu en entityId a l'execution
    [("T", (5, 5)), ("T", (3, 4)), ("M1", (3, 5)), ("M2", (4, 6)), ("M2", (2, 5)),
     ("W", (3, 7)), ("W", (1, 6)), ("H", (3, 3))]
)
TILES = {"H": (3, 3), "T": (3, 4), "M1": (3, 5), "M2": (2, 5), "W": (1, 6)}

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/aeldari.py",
                "scripts/python/engine/runner/abilities/handler.py",
                "scripts/python/engine/runner/abilities/attack_type.py",
                "scripts/python/engine/runner/abilities/targeting.py",
                "scripts/python/engine/runner/abilities/behaviours/**",
                "scripts/python/engine/runner/components.py",
                "scripts/python/engine/entities/selectors/**",
                "scripts/python/engine/dsl/**",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte le port de 1108 au NATIF via un runner live : il depend du code du "
              "port (arbre DSL + la chaine + les deux selecteurs neufs + le substrat "
              "`unitsAttackedThisTurn` + le registre + le masque) ET du build charge (le natif "
              "est l'oracle du ciblage, des cibles de la chaine et de la tuile d'atterrissage).",
}


def _session() -> int:
    st = requests.get(f"{HOST}/api/admin/status", timeout=20).json()
    return int(st["session"]["id"])


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 5).json()
    return r.get("result", r)


def _cli(state_path: Path, args: list) -> str:
    proc = subprocess.run([sys.executable, "rl_duel.py"] + args
                          + ["--state-file", str(state_path)],
                          cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return (proc.stdout or "") + (proc.stderr or "")


def build(state_path: Path) -> int:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    out = _cli(state_path, ["build", "--seed", "777", "--board", BOARD,
                            "--explicit-stats", CARRIER, "--p-units", CARRIER,
                            "--a-units", FOES, "--hp-target", "90000", "--no-ai"])
    if not state_path.exists():
        print(out[-1800:])
        raise SystemExit("build KO")
    return int(json.loads(state_path.read_text())["runnerId"])


def seed_rng(s):
    """MT offline == MT live : `dumpRng` rend l'etat COMPLET (`mt[624]`, `mti`).

    ⚠ **SANS CE CALAGE, LE PIPELINE DE DEGAT EST INERTE** -- `execute_normal_like` (comme
    `execute_ability_attack`) commence par `if state.rng is None: return None`. C'est une
    degradation DEFENSIVE documentee, pas un bug ; mais pour CE port elle est particulierement
    traitresse : sans degat, `register_attack_made` n'est jamais appele, donc
    `UnitsAttackedThisTurn` rend VIDE, donc l'atterrissage tombe sur son 3e repli
    (`AdjacentTiles(Target)`) au lieu de la derniere cible -- une tuile PLAUSIBLE, et fausse.
    Mesure du 2026-08-11 : sans calage, le port atterrissait en (2,3) (voisine de la CIBLE) la ou
    le natif atterrit en (2,4) (voisine de la DERNIERE victime), et les trois mutants
    d'atterrissage sortaient INERTES -- un banc de mutants qui ne mord pas est le symptome, pas
    le verdict."""
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    tiles = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    st = load_state(dec, ob, snap, board=board, tiles=tiles)
    st.rng = seed_rng(rpc(sid, "dumpRng", {"runnerId": rid}, 40))
    return st, dec


def _ids(dec) -> dict:
    """`{role -> entityId}` : le porteur (team 1) et les quatre orks, ordonnes par leur visualId."""
    mine, foes = [], []
    for u in dec.get("units", []) or []:
        (mine if int(u.get("team", 0)) == 1 else foes).append(u)
    order = ("orksNob", "orksRuntherd", "orksBigMek", "orksWarboss")
    by_vis = {}
    for u in foes:
        by_vis.setdefault(str(u.get("visualId") or u.get("unitId") or ""), []).append(int(u["id"]))
    out = {"H": int(mine[0]["id"])}
    for role, vis in zip(("T", "M1", "M2", "W"), order):
        cand = [v for k, v in by_vis.items() if vis in k]
        out[role] = min(cand[0]) if cand else None
    return out


def native_targets(sid, rid, uid: int, ability: int) -> list:
    """`abilityTargets` -- format MESURE (2026-08-11) : `{units:[{unitId, abilities:[{abilityId,
    fromHere:[{targetId,...}], targets:[...], usable}]}]}`. Le RPC est GLOBAL (aucun `unitId` en
    argument) ; `fromHere` = castable SANS bouger, c'est-a-dire la legalite EXACTE du cast qu'on
    va jouer."""
    a = rpc(sid, "abilityTargets", {"runnerId": rid, "allAbilities": True}, 60) or {}
    for u in a.get("units") or []:
        if int(u.get("unitId", -1)) != int(uid):
            continue
        for ab in u.get("abilities") or []:
            if int(ab.get("abilityId", -1)) == int(ability):
                return sorted({int(t["targetId"]) for t in (ab.get("fromHere") or [])
                               if t.get("targetId") is not None})
    return []


def native_events(act: dict) -> list:
    """Events d'`applyAction` -- format MESURE : ils vivent sous `actions[*].events` (la cle
    `events` de premier niveau existe mais reste VIDE), chaque event etant PLAT
    `{kind, entity, group?, step?, tags?}` ou `tags` est une **chaine JSON**."""
    out = []
    for a in (act.get("actions") or []) + [act]:
        for ev in (a.get("events") or []):
            if not isinstance(ev, dict):
                continue
            tg = ev.get("tags")
            if isinstance(tg, str):
                try:
                    tg = json.loads(tg)
                except Exception:
                    tg = {}
            out.append({"kind": ev.get("kind"), "entity": ev.get("entity"),
                        "group": ev.get("group"), "step": ev.get("step"),
                        "tags": tg if isinstance(tg, dict) else {}})
    return out


def _pos_of(state, eid):
    from engine.runner.components import PositionComponent
    e = state.get_entity(eid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (int(pc.col), int(pc.row)) if pc is not None else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=str(LOGS / "st_940_kiss_of_death.json"))
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    sp = Path(a.state_file).resolve()

    sid = _session()
    rid = build(sp)
    print("[940] runner %d  board %s  porteur %s" % (rid, BOARD, CARRIER))
    fails = []
    try:
        _, dec = load(sid, rid)
        ids = _ids(dec)
        print("[940] entites : " + "  ".join("%s=u%s" % (k, ids[k]) for k in ("H", "T", "M1", "M2", "W")))
        if any(v is None for v in ids.values()):
            raise SystemExit("roster incomplet : %r" % (ids,))

        # ---------------- PLACEMENT (drive, jamais subir la geometrie de spawn) ----------------
        for role, (c, r) in PLACEMENT:
            _cli(sp, ["act", "move", "--unit", str(ids[role]), "--to", "%d,%d" % (c, r)])
        state, dec = load(sid, rid)
        for role, want in TILES.items():
            got = _pos_of(state, ids[role])
            if got != want:
                fails.append("[placement] %s attendu %r, obtenu %r" % (role, want, got))
        import hexgeo
        adj = {k: set(hexgeo.neighbors(*v)) for k, v in TILES.items()}
        # Le montage n'a de valeur que si ces quatre proprietes tiennent : on les MESURE.
        for cond, txt in ((TILES["T"] in adj["H"], "T adjacent a H"),
                          (TILES["M1"] in adj["T"] and TILES["M1"] not in adj["H"],
                           "M1 adjacent a T mais PAS a H"),
                          (TILES["M2"] in adj["M1"] and TILES["M2"] not in adj["T"],
                           "M2 adjacent a M1 mais PAS a T (LE discriminant)"),
                          (TILES["W"] in adj["M2"] and TILES["W"] not in adj["M1"],
                           "W adjacent a M2 seul (temoin de la borne)")):
            print("[montage] %-46s : %s" % (txt, "OK" if cond else "NON -- montage DEGENERE"))
            if not cond:
                fails.append("[montage] " + txt)

        # ---------------- [1] CIBLAGE : le natif est l'oracle du masque -------------------------
        nat = native_targets(sid, rid, ids["H"], KISS_OF_DEATH)
        from engine.runner.abilities.handler import ABILITY_CLASSES
        from engine.runner.abilities.targeting import get_invalid_target_reason
        cls = ABILITY_CLASSES.get(KISS_OF_DEATH)
        if cls is None:
            fails.append("[1] 1108 ABSENTE d'ABILITY_CLASSES -- l'ability est un NO-OP")
        else:
            ab = cls()
            allowed, refused = [], []
            for role in ("T", "M1", "M2", "W", "H"):
                # signature NATIVE du port : `(state, caster_id, target_id, ability)`. L'inverser
                # fait lire `TARGETING_OPTIONS` sur un ENTIER -> `None` -> retour 0 -> le gate se
                # tait et TOUT passe : c'est exactement la degradation PERMISSIVE que la regle du
                # masque decrit, et elle a d'abord accuse le port ici (2026-08-11).
                rsn = get_invalid_target_reason(state, ids["H"], ids[role], ab)
                (allowed if not rsn else refused).append(role)
            print("[1] natif fromHere = %r | port accepte %r, refuse %r"
                  % (nat, allowed, refused))
            if nat != sorted([ids["T"]]):
                fails.append("[1] natif attendu [T], obtenu %r" % (nat,))
            if allowed != ["T"]:
                fails.append("[1] le port accepte %r au lieu de ['T'] -- le masque TargetIsEnemy "
                             "ne mord pas (self ou hors-portee acceptes)" % (allowed,))

        # ---------------- LE PORT, sur l'etat PRE-CAST (State Python independant) ---------------
        from engine.runner.components import HealthComponent
        port_state = state

        def _hp(st):
            out_ = {}
            for role in ("T", "M1", "M2", "W"):
                e = st.get_entity(ids[role])
                hc = e.get_component(HealthComponent) if e is not None else None
                out_[role] = int(hc.hp) if hc is not None and hc.hp is not None else None
            return out_
        hp0 = _hp(port_state)
        out = cls().execute_behaviour(port_state, ids["H"], ids["T"]) if cls else None
        hp1 = _hp(port_state)
        port_damage = {k: (hp0[k] - hp1[k]) for k in hp0
                       if hp0[k] is not None and hp1[k] is not None and hp0[k] != hp1[k]}
        port_targets = sorted(int(t) for t in (out or {}).get("targets", []) if t is not None)
        port_tile = _pos_of(port_state, ids["H"])
        print("[port] dmg=%s hits=%s maxTargets=%s | cibles=%r | atterrissage=%r"
              % ((out or {}).get("dmg"), (out or {}).get("hits"), (out or {}).get("maxTargets"),
                 port_targets, port_tile))

        # ---------------- LE NATIF : on caste, puis on lit la cascade ---------------------------
        res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ids["H"], "targetId": ids["T"],
            "abilityType": KISS_OF_DEATH}}, 120)
        flat = native_events(res)
        hits = [n for n in flat if n["tags"].get("Target_Id") is not None
                and n["tags"].get("Amount") is not None]
        nat_targets = sorted({int(n["tags"]["Target_Id"]) for n in hits})
        profiles = sorted({int(n["tags"]["DamageProfileType"]) for n in hits
                           if n["tags"].get("DamageProfileType") is not None})
        abil_ids = sorted({int(n["tags"]["Active_Ability_Type"]) for n in hits
                           if n["tags"].get("Active_Ability_Type") is not None})
        amounts = {int(n["tags"]["Target_Id"]): int(n["tags"].get("Amount") or 0) for n in hits}
        state2, _ = load(sid, rid)
        nat_tile = _pos_of(state2, ids["H"])
        # `Effect_SourceId` n'est pose QUE par `ReceiveEffect` ; `LoseEffect` porte `Effect_Id` seul.
        got_eff = [n for n in flat if n["tags"].get("Effect_SourceId") is not None
                   and int(n.get("entity") or -1) == ids["H"]]
        lost_eff = [n for n in flat if n["tags"].get("Effect_Id") is not None
                    and n["tags"].get("Effect_SourceId") is None
                    and int(n.get("entity") or -1) == ids["H"]]

        # ---------------- [2] CIBLES DE LA CHAINE ---------------------------------------------
        want = sorted([ids["T"], ids["M1"], ids["M2"]])
        role_of = {v: k for k, v in ids.items()}
        print("[2] natif frappe %r = %r"
              % (nat_targets, [role_of.get(i, i) for i in nat_targets]))
        print("[2] port  frappe %r = %r"
              % (port_targets, [role_of.get(i, i) for i in port_targets]))
        if nat_targets != want:
            fails.append("[2] NATIF : attendu {T,M1,M2} = %r, obtenu %r" % (want, nat_targets))
        if port_targets != nat_targets:
            fails.append("[2] PORT != NATIF : %r vs %r" % (port_targets, nat_targets))
        if ids["M2"] not in nat_targets:
            fails.append("[2] M2 non frappe -- le jumpTargetSelector ne recoit PAS la liste "
                         "COMPLETE des cibles piquees (montage DEGENERE ou port faux)")
        if ids["W"] in nat_targets:
            fails.append("[2] W frappe -- `maxAdjacentTargets` ne borne pas les sauts")

        # ---------------- [3] ATTERRISSAGE ----------------------------------------------------
        last = TILES["M2"]          # la DERNIERE cible frappee, par construction du montage
        print("[3] natif atterrit %r | port %r | adjacent a la derniere cible %r : nat=%s port=%s"
              % (nat_tile, port_tile, last,
                 nat_tile in set(hexgeo.neighbors(*last)) if nat_tile else None,
                 port_tile in set(hexgeo.neighbors(*last)) if port_tile else None))
        if nat_tile is None or nat_tile not in set(hexgeo.neighbors(*last)):
            fails.append("[3] NATIF : la tuile finale %r n'est PAS adjacente a la derniere cible %r"
                         % (nat_tile, last))
        if port_tile != nat_tile:
            fails.append("[3] PORT != NATIF sur la tuile d'atterrissage : %r vs %r"
                         % (port_tile, nat_tile))

        # ---------------- [4] EFFET 1044, POSE PUIS RETIRE ------------------------------------
        # ⚠ `Effect_Id` d'un event est un id d'ENTITE-effet, PAS un `EffectType` : le RPC ne NOMME
        # pas l'effet. Ce qui est verifiable sans nom, et qui suffit : le caster RECOIT un effet
        # dont il est LUI-MEME la source (`Effect_SourceId == entity == caster`) PUIS le PERD, dans
        # la MEME cascade. C'est la signature exacte de la paire `AddEffect(Untargetable, source =
        # Caster, targets = Caster)` / `RemoveEffect(Untargetable, Caster)` -- aucun autre membre de
        # l'arbre ne pose ni ne retire d'effet sur le caster.
        self_src = [n for n in got_eff if int(n["tags"]["Effect_SourceId"]) == ids["H"]]
        print("[4] natif : effets RECUS par le caster et dont il est la source = %d ; PERDUS = %d"
              % (len(self_src), len(lost_eff)))
        if not self_src:
            fails.append("[4] NATIF : le caster ne recoit AUCUN effet dont il est la source "
                         "-- l'`AddEffect(1044 Untargetable, source = Caster)` n'a pas eu lieu")
        if not lost_eff:
            fails.append("[4] NATIF : le caster ne PERD aucun effet dans la cascade "
                         "-- le `RemoveEffect(1044, Caster)` n'a pas eu lieu")
        emitted = (out or {}).get("emitted") or []
        if emitted.count("AddEffect") < 1 or emitted.count("RemoveEffect") < 1:
            fails.append("[4] le PORT n'emet pas AddEffect ET RemoveEffect : %r" % (emitted,))

        # ---------------- [5] DEGAT : DECOMPOSE PAR ETAGE, jamais fitte -------------------------
        # Les DEUX cotes tournent sur le MEME etat MT (`dumpRng`), donc l'egalite attendue est
        # BIT-EXACTE, pas approchee. Le montant NU (`dmg`) est imprime a cote pour que l'ecart, s'il
        # revient, se lise a l'ETAGE ou il nait : `abilityState` -> `ability_var` -> pipeline.
        nat_damage = {role_of.get(k, k): v for k, v in sorted(amounts.items())}
        print("[5] profils natifs %r (attendu [%d = DirectDamage]) | ability ids %r"
              % (profiles, DIRECT_DAMAGE, abil_ids))
        print("[5] degat NATIF %r" % (nat_damage,))
        print("[5] degat PORT  %r" % (port_damage,))
        print("[5] montant NU du port (`Direct(GetVariableForLevel(0xb = dmg))`) = %s "
              "-- ce n'est PAS le degat applique : le pipeline (percage, armure, crit, effets de "
              "la cible) le transforme, et c'est CE resultat-la qu'on confronte."
              % ((out or {}).get("dmg"),))
        if profiles != [DIRECT_DAMAGE]:
            fails.append("[5] profil natif %r != [%d]" % (profiles, DIRECT_DAMAGE))
        if abil_ids != [KISS_OF_DEATH]:
            fails.append("[5] Active_Ability_Type natif %r != [%d]" % (abil_ids, KISS_OF_DEATH))
        if not nat_damage:
            fails.append("[5] le natif n'a inflige AUCUN degat -- montage degenere")
        if port_damage != nat_damage:
            fails.append("[5] degat PORT != NATIF (rng CALE, donc egalite bit-exacte attendue) : "
                         "%r vs %r" % (port_damage, nat_damage))

        # ---------------- [6] MUTANTS : chacun doit MORDRE -------------------------------------
        import engine.runner.abilities.aeldari as A
        from engine.entities.selectors.geometry import PickFirstN
        from engine.dsl.base import Const
        muts = []

        # Les mutants tournent sur un runner NEUF monte a l'identique : muter puis rejouer sur un
        # etat DEJA caste ne prouverait rien. Chaque `_run` recharge un etat PRE-CAST frais depuis
        # CE runner-la, qu'aucun cast n'a touche.
        sp2 = sp.with_name(sp.stem + "_mut.json")
        rid2 = build(sp2)
        st0, dec0 = load(sid, rid2)
        ids2 = _ids(dec0)
        for role, (c, r) in PLACEMENT:
            _cli(sp2, ["act", "move", "--unit", str(ids2[role]), "--to", "%d,%d" % (c, r)])

        def _run(mutate=None):
            """Rejoue le port sur un etat PRE-CAST FRAIS, eventuellement mute. `mutate` rend
            `{(module_ou_classe, nom_d_attribut): valeur_originale}`, restaure en `finally` --
            forme B (substitution d'un ATTRIBUT DE MODULE), la seule qui morde (#923)."""
            st, _d = load(sid, rid2)
            saved = mutate() if mutate else {}
            try:
                o = A.KissOfDeathAbility().execute_behaviour(st, ids2["H"], ids2["T"])
            finally:
                for (obj, attr), val in (saved or {}).items():
                    setattr(obj, attr, val)
            return (sorted(int(t) for t in (o or {}).get("targets", []) if t is not None),
                    _pos_of(st, ids2["H"]))

        base = _run()
        print("[6] temoin (port non mute) : cibles=%r tuile=%r" % base)
        if base[0] != want and base[0] != sorted(port_targets):
            fails.append("[6] le TEMOIN du banc de mutants ne reproduit pas la mesure : %r" % (base,))

        def _mut_max_targets_zero():
            f = A.kiss_of_death_max_targets
            A.kiss_of_death_max_targets = lambda *a, **k: 0
            return {(A, "kiss_of_death_max_targets"): f}

        def _mut_jump_adjacent_to_caster():
            """Le lambda saute depuis le CASTER au lieu des cibles deja piquees."""
            from engine.entities.selectors.units import AdjacentUnits, Enemies
            from engine.entities.selectors.tiles import Caster as _C
            f = A.kiss_of_death_jump_targets
            A.kiss_of_death_jump_targets = (lambda picked: Enemies(
                AdjacentUnits(_C(), Const(1), selection_type=A.SELECTION),
                selection_type=A.SELECTION))
            return {(A, "kiss_of_death_jump_targets"): f}

        def _mut_landing_first_instead_of_last():
            """`Last(attacked, 1)` -> `First(attacked, 1)` : on atterrit a cote de la PREMIERE
            cible frappee au lieu de la derniere."""
            from engine.entities.selectors.units import UnitsAttackedThisTurn as _U
            from engine.entities.selectors.tiles import (AdjacentTiles as _AT, CanAddUnit as _CAU,
                                                         Caster as _C, SortTilesByUtility as _S)
            from engine.entities.selectors.accessors import CasterTile as _CT, Target as _T
            from engine.entities.selectors.units import Sub as _Sub
            from engine.entities.selectors.geometry import Otherwise as _O, AtIndex as _AI
            f = A.kiss_of_death_landing_tiles

            def _first_variant():
                att = _U(_C())
                g = lambda o: _Sub(_CAU(_AT(o)), _CT(as_ids=True))
                r = _O(_O(g(PickFirstN(att, Const(1))), g(_AI(att, 1))), g(_T()))
                return PickFirstN(_S(r, unit_sel=_C(), utility_type=A.UTILITY_TYPE_TILE), Const(1))
            A.kiss_of_death_landing_tiles = _first_variant
            return {(A, "kiss_of_death_landing_tiles"): f}

        def _mut_no_live_attacked():
            """`unitsAttackedThisTurn` HORS `_LIVE_KEYS` : le champ est fige au seed, donc VIDE au
            moment ou `FlyUnit` le lit -- exactement le regime d'avant #940."""
            import engine.runner.abilities.behaviours.context as C
            f = C._LIVE_KEYS
            C._LIVE_KEYS = frozenset(x for x in f if x != "unitsAttackedThisTurn")
            return {(C, "_LIVE_KEYS"): f}

        def _mut_unordered_attacked():
            """Le substrat redevient un `set` NON ordonne : `Last(...)` designe alors une cible
            arbitraire. Le mutant MORD si l'ordre du set differe de l'ordre d'insertion."""
            import engine.runner.abilities.behaviours.context as C
            f = C._unit_dict

            def _shuffled(state, eid, entity=None):
                d = f(state, eid, entity)
                if d and d.get("unitsAttackedThisTurn"):
                    d["unitsAttackedThisTurn"] = list(reversed(d["unitsAttackedThisTurn"]))
                return d
            C._unit_dict = _shuffled
            return {(C, "_unit_dict"): f}

        for label, fn in (("maxTargets = 0 (aucun saut)", _mut_max_targets_zero),
                          ("jump depuis le CASTER au lieu des cibles piquees",
                           _mut_jump_adjacent_to_caster),
                          ("atterrissage sur la PREMIERE cible au lieu de la derniere",
                           _mut_landing_first_instead_of_last),
                          ("`unitsAttackedThisTurn` HORS _LIVE_KEYS (regime d'avant #940)",
                           _mut_no_live_attacked),
                          ("ordre d'insertion INVERSE (substrat non ordonne)",
                           _mut_unordered_attacked)):
            got = _run(fn)
            mord = got != base
            muts.append((label, mord, got))
            print("[6] %-58s : %s  %r" % (label[:58], "MORD" if mord else "INERTE", got))
            if not mord:
                fails.append("[6] mutant INERTE : %s -> %r (identique au temoin)" % (label, got))

    finally:
        _cli(sp, ["dispose"])
        try:
            _cli(sp.with_name(sp.stem + "_mut.json"), ["dispose"])
        except Exception:
            pass

    print("")
    if fails:
        print("[940] ECHEC -- %d point(s) :" % (len(fails),))
        for f in fails:
            print("   - " + f)
        return 1
    print("[940] OK -- les 6 etages concordent avec le natif.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
