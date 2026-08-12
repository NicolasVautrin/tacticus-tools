"""#953 / #954 -- CONFRONTATION LIVE des deux passifs portes : `Skullsmasher` (`worldJakhal`
<< Macer >>) et `ObsessiveAnnunciation` (`emperKakophonist` << Adamatar >>).

CE QUE CE PROBE MESURE, ET POURQUOI LA GEOMETRIE EST CALCULEE PLUTOT QUE SUBIE
-----------------------------------------------------------------------------
`ObsessiveAnnunciation` pose sur Adamatar DEUX effets-AURA dont le `CreateTargetSelector` est
`AdjacentEnemies(Owner)` : ils ne mordent que sur les ENNEMIS ADJACENTS AU PORTEUR, jamais sur le
porteur ni sur l'attaquant. Le seul discriminant honnete est donc **la position d'Adamatar, tout le
reste egal**, et le TEMOIN doit etre choisi pour qu'un port qui lirait la mauvaise adjacence rende
les deux bras IDENTIQUES :

    TILE_V   (0,0)  victime -- la cible de toutes les attaques mesurees
    TILE_R   (0,3)  attaquant RANGED (portee 3), a distance 3 de la victime
    TILE_A1  (0,1)  Adamatar ADJACENT A LA VICTIME et a distance 2 de l'attaquant  -> bras
    TILE_A2  (0,4)  Adamatar ADJACENT A L'ATTAQUANT et a distance 4 de la victime  -> TEMOIN

Un port qui lirait `AdjacentEnemies(attaquant)` au lieu d'`AdjacentEnemies(porteur)` -- ou qui
prendrait l'adjacence porteur/attaquant comme celle du gate -- rendrait `oa_away` EGAL a `oa_aura`.
C'est exactement le cran que #950 avait pose sur l'axe oppose.

`Skullsmasher` n'a AUCUNE geometrie : sa magnitude est `floor(pct de PV MANQUANTS / hpPct) x
extraDmg`. Son discriminant est donc les PV du porteur, et le bras blesse est produit en FAISANT
FRAPPER Macer par un adversaire (pilotage des deux camps), pas en fabriquant un etat.

LES BRAS
--------
  `oa_aura`   : Adamatar en A1, attaque RANGED sur la victime      -> +extraDmg (face DEGAT) ;
  `oa_away`   : Adamatar en A2, meme attaque RANGED                -> TEMOIN, aucun bonus ;
  `oa_melee`  : Adamatar en A1, attaque MELEE sur la victime       -> TEMOIN du gate `IsRangedAttack` ;
  `oa_crit`   : Adamatar en A1, un ennemi vient d'etre OVERKILL, attaque CRITIQUE d'un allie
                CHAOS d'Adamatar                                   -> +extraCritDmg (face CRIT) ;
  `oa_crit_ctl` : idem SANS l'overkill prealable                   -> TEMOIN (l'aura 1433 absente) ;
  `sk_full`   : Macer a PV PLEINS attaque la victime               -> TEMOIN, 0 palier ;
  `sk_hurt`   : Macer BLESSE attaque la victime                    -> +floor(pct/10) x extraDmg ;
  `sk_stun`   : Macer a deja TUE, il attaque la victime            -> elle devient `Stunned` (1162)
                et Macer porte le marqueur `Skullsmasher_StunEffect` (1264) ;
  `sk_nostun` : Macer n'a RIEN tue, meme attaque                   -> TEMOIN, aucun `Stunned`.

Chaque bras capture l'etat (`decisionView` + `observeBattle` + `combatSnapshot` + `dumpRng`) AVANT
l'attaque mesuree, joue l'attaque NATIVE (ledger par coup), puis REJOUE la meme attaque OFFLINE sur
le meme `State` et le meme flux RNG. Le verdict fort est **port == natif A L'UNITE, par coup**.

MUTATION (contre-epreuve). `--mutate` neutralise le port : les entrees `EFFECT_CLASSES` des trois
effets (1263, 1432, 1433) retombent sur `BaseEffect`, et les entrees `ABILITY_TRIGGERS` des deux
passifs sont retirees -- c'est EXACTEMENT l'etat d'`origin/master`. Le rejeu doit alors DIVERGER du
natif dans les bras porteurs et rester EGAL dans les temoins. Un bras mutant VERT est le resultat
SUSPECT (mutation qui ne mord pas), pas une bonne nouvelle : le verdict le dit.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import hexgeo                                                     # noqa: E402
from probe_r6_round_materialize import _mkrpc                     # noqa: E402

BOARD = "MC1_67"
SEED = "777"

ADA = "emperKakophonist"          # << Adamatar >>, porteur d'`ObsessiveAnnunciation`
MACER = "worldJakhal"             # << Macer >>, porteur de `Skullsmasher`
#: attaquant RANGED **CHAOS** (portee 2, 1 coup `HeavyRound`) : allie d'Adamatar, donc
#: `AreFriends(EffectSource, Caster)` VRAI, et `HasTrait(Caster, Chaos)` VRAI.
#:
#: ⚠ CE N'EST PAS LE PREMIER CHOISI, et le remplacement est une MESURE. `emperNoiseMarine` (r3,
#: 6 coups) porte QUATRE passifs qui touchent le degat RANGED -- `TerrifyingCrescendo`,
#: `SuppressiveFire`, `HeavyWeapon`, `ThrillSeekers` -- et le port DIVERGE du natif avec lui
#: **DANS LE TEMOIN** (`oa_away` : natif 4699, port 6396) comme avec `--mutate` : un ecart
#: PREEXISTANT, etranger a ce lot, qui rendrait TOUT bras illisible. `thousTzaangor` ne porte que
#: `RealityUnbound` (+MaxDamage par ennemi ayant subi du PSYCHIQUE ce tour) et `WeaverOfFate`
#: (max damage si 3+ ennemis ont subi du psychique) : sans aucune source psychique au montage, les
#: DEUX sont inertes -- et son unique coup rend l'ecart d'aura directement lisible.
ATT_CHAOS = "thousTzaangor"
#: attaquant RANGED **NON-CHAOS** (Imperial) : meme role, mais le gate `HasTrait(Caster, Chaos)`
#: de la moitie CRIT tombe -- c'est le TEMOIN du 3e conjoint.
ATT_IMPERIAL = "ultraEliminatorSgt"
#: victime NEUTRE : `orksNob` porte `SmashaEad` (bonus crit OFFENSIF) et `BeastSlayer` -- elle ne
#: projette RIEN sur ses allies, et elle ne fait qu'encaisser.
VICTIM = "orksNob"
#: SACRIFICE : l'unite qu'on OVERKILL pour armer l'aura de crit (bras `oa_crit`). PV forces a 1.
SACRIFICE = "astraBullgryn"
#: TUEUR DEDIE des bras CRIT : il OVERKILL le sacrifice LOIN de la zone de mesure, dans le MEME
#: tour que l'attaque mesuree (l'aura 1433 ne dure qu'UN tour). Son kit n'entre dans aucune mesure :
#: il n'attaque jamais la victime et ne projette rien (`TerrifyingCrescendo` est un bonus OFFENSIF
#: sur SES propres attaques ranged, `SuppressiveFire` frappe la cible qu'il tue).
KILLER = "emperNoiseMarine"

#: PV forces de Macer (`--hp-player`) -- cf. le commentaire de `run_sk` : la magnitude compte des
#: PALIERS de 10 % de PV MANQUANTS, donc le porteur doit pouvoir en perdre une FRACTION VISIBLE.
MACER_HP = 20000

EFF_SK_DMG = 1263                 # EffectType Skullsmasher_ExtraDamage
EFF_SK_MARK = 1264                # EffectType Skullsmasher_StunEffect (marqueur << a deja tue >>)
EFF_STUNNED = 1162                # EffectType Stunned
EFF_OA_DMG = 1432                 # EffectType ObsessiveAnnunciation_ExtraDmg
EFF_OA_CRIT = 1433                # EffectType ObsessiveAnnunciation_ExtraCritDmg


# --------------------------------------------------------------------------- montage live


def _build(units_p, units_a, places_p, places_a, *, seed=SEED, board=BOARD, rank=17,
           crit="0,0", extra=()):
    sf = ROOT / "logs" / "runners" / ("p953-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
           "--board", board, "--rank", str(rank),
           "--p-units", ",".join(units_p), "--a-units", ",".join(units_a),
           "--crit", crit, "--block-target", "0,0", "--block-player", "0,0", "--no-ai"]
    for vis, (c, r) in places_p:
        cmd += ["--place", "%s:%d,%d" % (vis, c, r)]
    for vis, (c, r) in places_a:
        cmd += ["--a-place", "%s:%d,%d" % (vis, c, r)]
    cmd += list(extra)
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, (proc.stderr or proc.stdout or "")[-1500:]
    return int(json.loads(sf.read_text())["runnerId"]), None


def _view(rpc, rid, inactive=False):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": bool(inactive)}, 180)


def _by_vis(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis), None)


def _unit(dv, uid):
    return next((x for x in (dv.get("units") or []) if int(x.get("id", -1)) == int(uid)), None)


def _pos(dv, uid):
    u = _unit(dv, uid)
    return None if u is None or not u.get("pos") else (int(u["pos"]["col"]), int(u["pos"]["row"]))


def _hp(dv, uid):
    u = _unit(dv, uid)
    return None if u is None else int(u.get("hp", 0))


def _effect_types(dv, uid):
    return sorted({int(e["effectType"]) for e in ((_unit(dv, uid) or {}).get("effects") or [])
                   if e.get("effectType") is not None})


def _normal_attack_id(dv, uid):
    for a in ((_unit(dv, uid) or {}).get("abilities") or []):
        if a.get("kind") == "normal":
            return int(a.get("id"))
    return None


def _attack(rpc, rid, cid, tid, ab):
    """Attaque NORMALE live + ledger par coup. Le discriminant du coup est `Attacker_Id` (un event
    de SOIN porte lui aussi une cle `Amount`, cf. #950)."""
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(cid), "targetId": int(tid),
        "abilityType": int(ab)}, "captureEvents": True}, 180)
    hits = []
    for act in (res.get("actions") or []):
        for ev in (act.get("events") or []):
            td = ev.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if "Amount" in td and "Attacker_Id" in td \
                    and int(td.get("Target_Id", -1)) == int(tid):
                hits.append(int(td["Amount"]))
    return res, hits


def _move(rpc, rid, uid, col, row):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 120)


def _ensure_can_act(rpc, rid, uid, max_turns=4) -> list:
    """Rend la main jusqu'a ce que `uid` soit DE NOUVEAU activable, en cloturant des tours.

    ⚠ Sans ce filet, une attaque preparatoire (le KILL de `sk_stun`, l'OVERKILL d'`oa_crit`)
    CONSOMME l'activation de son auteur -- et comme il est seul dans son camp, le natif cloture
    AUSSITOT le tour. L'attaque MESUREE qui suit est alors REFUSEE cote natif (`ok: true`,
    `actionConsumed: false`, ledger VIDE) alors que le rejeu offline la joue : une divergence de
    HARNAIS qui se lirait comme un bug de port. Mesure : `n=0 / total=0` cote natif contre
    `n=3 / total=2487` cote port, sur un bras ou le port etait parfaitement juste.

    Rend la trace des `currentPlayer` traverses (elle entre dans le rapport : un bras dont le
    filet a boucle sans rendre la main est un bras a REFUSER, pas a interpreter)."""
    seen = []
    for _ in range(max_turns):
        dv = _view(rpc, rid)
        seen.append({"currentPlayer": dv.get("currentPlayer"), "toActivate": dv.get("toActivate")})
        if int(uid) in [int(x) for x in (dv.get("toActivate") or [])]:
            return seen
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    dv = _view(rpc, rid)
    seen.append({"currentPlayer": dv.get("currentPlayer"), "toActivate": dv.get("toActivate"),
                 "exhausted": True})
    return seen


def _capture(rpc, rid):
    return {"dec": _view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
            "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
            "rng": rpc("dumpRng", {"runnerId": rid}, 30)}


# --------------------------------------------------------------------------- rejeu offline

#: `EFFECT_CLASSES` neutralises par `--mutate` = l'etat d'`origin/master`.
_MUTATED_EFFECTS = ("Skullsmasher_ExtraDamage", "ObsessiveAnnunciation_ExtraDmg",
                    "ObsessiveAnnunciation_ExtraCritDmg")
#: `ABILITY_TRIGGERS` retires par `--mutate` -- idem.
_MUTATED_TRIGGERS = ("Skullsmasher", "ObsessiveAnnunciation")
#: `ABILITY_INIT_OWNER_EFFECTS` retires par `--mutate` -- idem.
_MUTATED_SEEDS = ("Skullsmasher", "ObsessiveAnnunciation")


#: MUTATION SELECTIVE : ne neutraliser QU'UN effet (et aucun trigger). Sans elle, `--mutate`
#: neutralise 1432 ET 1433 a la fois, et l'ecart du bras `oa_crit` MELANGE les deux faces (l'aura
#: de DEGAT s'y applique aussi, l'attaque etant RANGED et Adamatar adjacent a la victime) -- la
#: face CRIT n'y serait alors pas falsifiable SEULE.
MUTATE_ONLY: "list | None" = None


class _Mutation:
    """Neutralise le port DANS LES TROIS REGISTRES a la fois. Un seul suffirait a faire diverger le
    bras `oa_aura`, mais pas le bras `sk_stun` (dont le vecteur est un TRIGGER) ni le seed de 1263
    (que le canal ACTIF-ONLY ne publie pas quand Macer est a PV pleins) : la contre-epreuve doit
    reproduire l'ETAT COMPLET d'avant, pas seulement le morceau que le bras courant exerce."""

    def __init__(self, on: bool):
        self.on = bool(on)
        self._eff, self._trg, self._seed = {}, {}, {}

    def __enter__(self):
        if not self.on:
            return self
        from engine.entities.effects.factory import EFFECT_CLASSES, ABILITY_INIT_OWNER_EFFECTS
        from engine.entities.effects.base import BaseEffect
        from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
        for n in (MUTATE_ONLY or _MUTATED_EFFECTS):
            self._eff[n] = EFFECT_CLASSES.get(n)
            EFFECT_CLASSES[n] = BaseEffect
        if MUTATE_ONLY:                      # mutation SELECTIVE : aucun trigger, aucun seed touche
            return self
        for n in _MUTATED_TRIGGERS:
            if n in ABILITY_TRIGGERS:
                self._trg[n] = ABILITY_TRIGGERS.pop(n)
        for n in _MUTATED_SEEDS:
            if n in ABILITY_INIT_OWNER_EFFECTS:
                self._seed[n] = ABILITY_INIT_OWNER_EFFECTS.pop(n)
        return self

    def __exit__(self, *exc):
        if not self.on:
            return False
        from engine.entities.effects.factory import EFFECT_CLASSES, ABILITY_INIT_OWNER_EFFECTS
        from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
        for n, cls in self._eff.items():
            if cls is None:
                EFFECT_CLASSES.pop(n, None)
            else:
                EFFECT_CLASSES[n] = cls
        ABILITY_TRIGGERS.update(self._trg)
        ABILITY_INIT_OWNER_EFFECTS.update(self._seed)
        return False


def _replay(cap, board_id, att_id, tgt_id, mutate=False):
    """Rejoue l'attaque OFFLINE sur le `State` capte et le flux RNG capte."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage

    with _Mutation(mutate):
        st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board_id)
        rng = IntBasedMersenneTwister()
        rng.mt = list(cap["rng"]["mt"])
        rng.mti = cap["rng"]["mti"]
        st.rng = rng
        hc = st.get_entity(int(tgt_id)).get_component(HealthComponent)
        hp0 = int(hc.hp)
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(int(att_id), int(tgt_id)))
        last = runner.damage_handler.last or {}
        eff = st.effects
        return {"hp_delta": hp0 - int(hc.hp), "total": last.get("total"),
                "per_hit": list(last.get("per_hit") or []),
                "tgt_effects": sorted({int(e.effect_type) for e in (eff.by_unit.get(int(tgt_id)) or [])
                                       if getattr(e, "effect_type", None) is not None})
                if eff is not None else None,
                "att_effects": sorted({int(e.effect_type) for e in (eff.by_unit.get(int(att_id)) or [])
                                       if getattr(e, "effect_type", None) is not None})
                if eff is not None else None}


def _replay_port_effects(cap, board_id, uid, mutate=False):
    """Etat des effets PORTES sur `uid` apres chargement seul (sans rejouer d'attaque) -- sert a
    confronter le SEED des owner-effects (1263 inactif, 1432 actif)."""
    from engine.runner.snapshot import load_state
    with _Mutation(mutate):
        st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board_id)
        eff = st.effects
        if eff is None:
            return None
        return sorted({int(e.effect_type) for e in (eff.by_unit.get(int(uid)) or [])
                       if getattr(e, "effect_type", None) is not None})


# --------------------------------------------------------------------------- bras


def _geo_assert(rpc, rid, want: dict) -> dict:
    """La geometrie EST le discriminant : elle est ASSERTIONNEE contre le `boardGraph` LIVE, jamais
    supposee. Rend `{"pos": {...}, "elev": {...}, "fail": [...]}`."""
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    dv = _view(rpc, rid, inactive=True)
    elev = {}
    for t in (bg.get("tiles") or []):
        elev[(int(t["col"]), int(t["row"]))] = t.get("elevation")
    pos, fail = {}, []
    for vis, tile in want.items():
        u = _by_vis(dv, vis)
        if u is None:
            fail.append("[geo] unite absente du build : %s" % vis)
            continue
        p = _pos(dv, int(u["id"]))
        pos[vis] = p
        if tile is not None and p != tile:
            fail.append("[geo] %s en %s, attendu %s" % (vis, p, tile))
    evs = {str(k): elev.get(k) for k in set(want.values()) if k is not None}
    if len({v for v in evs.values() if v is not None}) > 1:
        fail.append("[geo] elevations INEGALES entre les tuiles du montage : %s" % evs)
    return {"pos": pos, "elev": evs, "fail": fail, "bg": bg}


def run_oa(arm: str, mutate=False, verbose=True, seed=SEED, board=BOARD) -> dict:
    """Les bras d'`ObsessiveAnnunciation`."""
    g = geometry(board)
    ada_tile = g["A2"] if arm == "oa_away" else g["A1"]
    melee = (arm == "oa_melee")
    crit_arm = arm.startswith("oa_crit")
    att = ATT_IMPERIAL if arm == "oa_crit_nonchaos" else ATT_CHAOS
    att_tile = g["M"] if melee else g["R"]
    p_units = [ADA, att]
    a_units = [VICTIM, SACRIFICE]
    places_p = [(ADA, ada_tile), (att, att_tile)]
    # Le SACRIFICE est LOIN par defaut : un ennemi ADJACENT a l'attaquant RANGED reduit son
    # `fromHere` a ce SEUL ennemi (mesure : la victime a 2 hex disparait de `fromHere` et le bras
    # rendait `n=0` cote natif). Seul `oa_crit` le met au contact -- et il y MEURT au premier coup,
    # donc l'attaque MESUREE qui suit retrouve sa portee.
    places_a = [(VICTIM, g["V"]), (SACRIFICE, g["SACFAR"])]
    extra = ["--hp-target", "400000", "--hp-player", "400000"]
    if arm in ("oa_crit", "oa_crit_nonchaos"):
        # ⚠ L'AURA 1433 NE DURE QU'UN TOUR (`turns = <DSLFormulas+0x20> = Direct(1)`) : l'overkill
        # et l'attaque MESUREE doivent tomber dans le MEME tour. Un `endturn` entre les deux la
        # ferait EXPIRER -- mesure : `[1432, 1433]` juste apres le kill, `[1432]` apres le passage
        # de tour, et le bras rendait alors un TEMOIN deguise en bras. D'ou un TUEUR DEDIE (une 3e
        # unite de mon camp), loin de la zone de mesure, plutot qu'un passage de tour.
        # Le SACRIFICE a `Health = 1` : `DamagePrediction$$IsOverkill` compare
        # `(healthDamage - initialHealth) / initialHealth x 100` au seuil `overkillDmgPctOfHealth`,
        # donc un coup de plusieurs milliers sur 1 PV le franchit largement (MESURE : `[1432, 1433]`
        # a `Health = 1`, `[1432]` seul a `Health = 2000`, ou la cible SURVIT).
        p_units = [ADA, att, KILLER]
        places_p = [(ADA, ada_tile), (att, att_tile), (KILLER, g["KILLER"])]
        places_a = [(VICTIM, g["V"]), (SACRIFICE, g["SACFAR"])]
        # `--armor-target 0` : sans lui l'ARMURE de la victime reste celle du rank (les PV sont
        # forces par `--unit-stat`, qui ne la touche pas, la ou `--hp-target` la met a zero) et
        # elle ECRASE la contribution CRIT -- mesure : l'ecart de la face crit tombe a 155 points
        # avec armure, la face DEGAT restant a 974 (elle est versee APRES l'etage armure).
        extra = ["--hp-player", "400000", "--armor-target", "0",
                 "--unit-stat", "%s:Health=1,RemainingHealth=1" % SACRIFICE,
                 "--unit-stat", "%s:Health=400000,RemainingHealth=400000" % VICTIM]
    crit = "100,700" if crit_arm else "0,0"
    rid, err = _build(p_units, a_units, places_p, places_a, seed=seed, board=board,
                      crit=crit, extra=extra)
    if rid is None:
        return {"arm": arm, "error": "build KO : %s" % err}
    rpc = _mkrpc()
    try:
        geo = _geo_assert(rpc, rid, {ADA: ada_tile, att: att_tile, VICTIM: g["V"]})
        from engine.entities.pathfinding.board import Board
        bobj = Board(geo["bg"]["tiles"], adjacency="native_sym")
        dv = _view(rpc, rid, inactive=True)
        ids = {v: int(_by_vis(dv, v)["id"]) for v in (ADA, att, VICTIM, SACRIFICE, KILLER)
               if _by_vis(dv, v) is not None}
        out = {"arm": arm, "mutate": bool(mutate), "runner": rid, "ids": ids, "tiles": g,
               "geo": {"pos": geo["pos"], "elev": geo["elev"], "fail": geo["fail"]}}
        if geo["fail"]:
            return _done(out, verbose)
        att_id, tgt_id = ids[att], ids[VICTIM]
        out["geo"]["d_ada_victim"] = hexgeo.distance(geo["pos"][ADA], geo["pos"][VICTIM])
        out["geo"]["d_ada_att"] = hexgeo.distance(geo["pos"][ADA], geo["pos"][att])
        out["geo"]["d_att_victim"] = hexgeo.distance(geo["pos"][att], geo["pos"][VICTIM])
        na = _normal_attack_id(dv, att_id)
        if na is None:
            out["error"] = "id d'attaque normale introuvable pour %s" % att
            return _done(out, verbose)
        # --- OVERKILL prealable : les DEUX bras qui exercent la face CRIT -----------------------
        # `oa_crit_nonchaos` le fait AUSSI : sans lui, son temoin serait ambigu (aucune aura 1433
        # posee du tout), alors qu'on veut isoler le SEUL gate `HasTrait(Caster, Chaos)`.
        # C'est le TUEUR DEDIE qui frappe -- l'attaquant mesure garde son activation, et l'aura
        # d'UN TOUR est encore la quand il tire.
        if arm in ("oa_crit", "oa_crit_nonchaos"):
            sac, kid = ids.get(SACRIFICE), ids.get(KILLER)
            kna = _normal_attack_id(dv, kid)
            _res, sac_hits = _attack(rpc, rid, kid, sac, kna)
            out["overkill"] = {"sacrifice": sac, "killer": kid, "hits": sac_hits,
                               "ada_effects_after": _effect_types(
                                   _view(rpc, rid, inactive=True), ids[ADA])}
        out["ada_effects"] = _effect_types(_view(rpc, rid, inactive=True), ids[ADA])
        cap = _capture(rpc, rid)
        out["port_ada_effects"] = _replay_port_effects(cap, bobj, ids[ADA], mutate=mutate)
        _res, hits = _attack(rpc, rid, att_id, tgt_id, na)
        port = _replay(cap, bobj, att_id, tgt_id, mutate=mutate)
        out["native"] = {"hits": hits, "n": len(hits), "total": sum(hits)}
        out["port"] = {"per_hit": port["per_hit"], "n": len(port["per_hit"]),
                       "total": port["total"]}
        return _done(out, verbose)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def run_sk(arm: str, mutate=False, verbose=True, seed=SEED, board=BOARD) -> dict:
    """Les quatre bras de `Skullsmasher`.

    `sk_hurt` BLESSE Macer en le faisant frapper par un adversaire (les deux camps sont pilotables) ;
    `sk_stun` lui fait TUER un sacrifice a 1 PV avant l'attaque mesuree."""
    g = geometry(board)
    hurt = (arm == "sk_hurt")
    kill = (arm == "sk_stun")
    #: `sk_nostun` est le TEMOIN de `sk_stun` : MEME montage (memes `--unit-stat`, donc MEME armure
    #: de la victime) et MEME passage de tour -- seul le KILL prealable change. Sans cette symetrie,
    #: comparer les deux mesurerait l'armure et le tour, pas le marqueur.
    stun_montage = arm in ("sk_stun", "sk_nostun")
    melee_tile = g["M"]
    p_units = [MACER]
    a_units = [VICTIM, SACRIFICE]
    places_p = [(MACER, melee_tile)]
    places_a = [(VICTIM, g["V"]), (SACRIFICE, g["SAC"])]
    # ⚠ Les PV de Macer sont volontairement BAS (`--hp-player`) : la magnitude est
    # `floor(pct de PV MANQUANTS / hpPct = 10) x extraDmg`, donc un porteur a 400 000 PV ne franchit
    # AUCUN palier meme apres un coup de 10 000 -- le bras << blesse >> serait alors un second
    # temoin, et la mesure VIDE. Mesure : a 400 000 PV, un retour de 10 526 = 2,6 % = 0 palier.
    extra = ["--hp-target", "400000", "--hp-player", str(MACER_HP)]
    if stun_montage:
        # Le SACRIFICE est place au CONTACT de Macer (`SACM`) et ses PV sont a 1 : un seul coup
        # suffit a le TUER, donc a poser le marqueur `Skullsmasher_StunEffect`.
        extra = ["--hp-player", str(MACER_HP),
                 "--unit-stat", "%s:Health=1,RemainingHealth=1" % SACRIFICE,
                 "--unit-stat", "%s:Health=400000,RemainingHealth=400000" % VICTIM]
        places_a = [(VICTIM, g["V"]), (SACRIFICE, g["SACM"])]
    rid, err = _build(p_units, a_units, places_p, places_a, seed=seed, board=board, extra=extra)
    if rid is None:
        return {"arm": arm, "error": "build KO : %s" % err}
    rpc = _mkrpc()
    try:
        geo = _geo_assert(rpc, rid, {MACER: melee_tile, VICTIM: g["V"]})
        from engine.entities.pathfinding.board import Board
        bobj = Board(geo["bg"]["tiles"], adjacency="native_sym")
        dv = _view(rpc, rid, inactive=True)
        ids = {v: int(_by_vis(dv, v)["id"]) for v in (MACER, VICTIM, SACRIFICE)
               if _by_vis(dv, v) is not None}
        out = {"arm": arm, "mutate": bool(mutate), "runner": rid, "ids": ids, "tiles": g,
               "geo": {"pos": geo["pos"], "elev": geo["elev"], "fail": geo["fail"]}}
        if geo["fail"]:
            return _done(out, verbose)
        mid, tgt_id = ids[MACER], ids[VICTIM]
        out["geo"]["d_macer_victim"] = hexgeo.distance(geo["pos"][MACER], geo["pos"][VICTIM])
        na = _normal_attack_id(dv, mid)
        if na is None:
            out["error"] = "id d'attaque normale introuvable pour %s" % MACER
            return _done(out, verbose)
        if hurt:
            # BLESSER Macer : c'est la VICTIME qui le frappe (les deux camps sont pilotables).
            vna = _normal_attack_id(dv, tgt_id)
            _r, back = _attack(rpc, rid, tgt_id, mid, vna)
            out["hurt"] = {"hits_on_macer": back, "total": sum(back)}
        if kill:
            sac = ids.get(SACRIFICE)
            _r, sac_hits = _attack(rpc, rid, mid, sac, na)
            # ⚠ TUER CONSOMME L'ACTIVATION DE MACER : sans passage de tour, l'attaque mesuree qui
            # suit est REFUSEE par le natif (`n=0`, ledger vide) alors que le rejeu offline, lui,
            # la joue -- une divergence de HARNAIS qui se lirait comme un bug de port. On rend donc
            # la main aux deux camps (`endturn` x2, `--no-ai` : l'adversaire ne joue pas), ce que le
            # marqueur PERMANENT `Skullsmasher_StunEffect` traverse sans etre consomme.
            out["kill"] = {"sacrifice": sac, "hits": sac_hits,
                           "turns": _ensure_can_act(rpc, rid, mid)}
        elif arm == "sk_nostun":
            # MEME passage de tour que `sk_stun`, SANS le kill : les deux bras doivent differer par
            # le MARQUEUR, pas par le tour ni par l'armure.
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
            out["kill"] = {"sacrifice": None, "hits": [],
                           "turns": _ensure_can_act(rpc, rid, mid)}
        d_now = _view(rpc, rid, inactive=True)
        out["macer_hp"] = (_hp(d_now, mid), (_unit(d_now, mid) or {}).get("maxHp"))
        out["macer_effects"] = _effect_types(d_now, mid)
        cap = _capture(rpc, rid)
        out["port_macer_effects"] = _replay_port_effects(cap, bobj, mid, mutate=mutate)
        _res, hits = _attack(rpc, rid, mid, tgt_id, na)
        port = _replay(cap, bobj, mid, tgt_id, mutate=mutate)
        d_after = _view(rpc, rid, inactive=True)
        out["native"] = {"hits": hits, "n": len(hits), "total": sum(hits),
                         "tgt_effects_after": _effect_types(d_after, tgt_id),
                         "macer_effects_after": _effect_types(d_after, mid)}
        out["port"] = {"per_hit": port["per_hit"], "n": len(port["per_hit"]),
                       "total": port["total"], "tgt_effects_after": port["tgt_effects"],
                       "macer_effects_after": port["att_effects"]}
        return _done(out, verbose)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


# --------------------------------------------------------------------------- geometrie derivee


_BOARD_CACHE = {}
_GEO_CACHE = {}


def _board(board_id):
    """Le dump OFFLINE du board (`data/boards/`) -- `board.Board` expose l'adjacence STOCKEE
    (`neighbors`), la MEME liste que `TileQuery.IterateAdjacentTiles`, et l'ELEVATION par tuile."""
    if board_id in _BOARD_CACHE:
        return _BOARD_CACHE[board_id]
    import rl_collect_batch as R
    import board as B
    for kind in ("pvp", "syncPvp", "global"):
        p = R.BOARDS_DIR / kind / ("%s.json" % board_id)
        if p.exists():
            dump = json.loads(p.read_text(encoding="utf-8"))
            bd = B.Board({"Board": dump["board"],
                          "SpawnPointSetIndex": dump.get("spawnPointsSet", 0)})
            _BOARD_CACHE[board_id] = bd
            return bd
    raise SystemExit("[953] board dump introuvable : %s (python dump_boards.py)" % board_id)


#: Distance V<->R du montage RANGED. Elle est MESUREE, pas lue dans le gameconfig : la portee
#: `r3` affichee par `gameconfig.py` pour `emperNoiseMarine` ne rend PAS la victime castable
#: `fromHere` a 3 hex (`abilityTargets` : elle est dans `targets`, superset MOVE inclus, et ABSENTE
#: de `fromHere`). A 2 hex, elle l'est. On prend donc la plus grande distance REELLEMENT castable
#: qui laisse `d(A1,R) >= 2` -- sans quoi le TEMOIN cesserait de discriminer.
RANGED_DIST = 2


def geometry(board_id, dist=None) -> dict:
    """CALCULE le montage, il ne le devine pas. Cinq tuiles, toutes JOUABLES et **A LA MEME
    ELEVATION** (sans quoi le terme d'elevation de
    `DamageCalculations$$CalculateAttackerModifiersForPrediction` separerait les bras au lieu de
    l'aura -- ecart deja paye en #63) :

        V   la victime ;
        A1  Adamatar, ADJACENT a V (adjacence STOCKEE) et a distance >= 2 de R  -> bras ;
        R   l'attaquant RANGED, a distance EXACTEMENT 3 de V (portee de `emperNoiseMarine`) ;
        A2  Adamatar, ADJACENT a R et a distance >= 2 de V                      -> TEMOIN ;
        M   une tuile ADJACENTE a V, distincte de A1/A2/R                       -> attaque MELEE.

    `A2` est le cran qui rend le temoin DISCRIMINANT : un port qui lirait l'adjacence a
    l'ATTAQUANT au lieu de l'adjacence a la VICTIME rendrait `oa_away` identique a `oa_aura`.

    ⚠ L'adjacence vient de `Board.neighbors` (liste STOCKEE du dump), la distance de
    `hexgeo.distance` (la portee d'arme, elle, est une distance hex). Les DEUX sont ensuite
    ASSERTIONNEES LIVE contre le `boardGraph` du runner (`_geo_assert`)."""
    dist = RANGED_DIST if dist is None else int(dist)
    key = (board_id, dist)
    if key in _GEO_CACHE:
        return _GEO_CACHE[key]
    bd = _board(board_id)
    def elev(p):
        t = bd.tile(p[0], p[1])
        return None if not t else t.get("elevation")
    def _ok(c, r):
        """JOUABLE **et** franchissable. ⚠ `Board.is_playable` rend VRAI sur une tuile `Block`
        (elle ne lit que `ForceUnplayable`) -- MESURE : `--place` sur `(0,8)` de `MC1_67`
        (`TileId = Block`) ne LEVE PAS, l'unite est simplement ABSENTE du build, et le bras se lit
        alors comme une geometrie ratee. Le `TileId` est donc filtre ICI."""
        t = bd.tile(c, r)
        return bool(t) and bd.is_playable(c, r) and t.get("tileId") != "Block"

    cells = [(c, r) for c in range(bd.width) for r in range(bd.height) if _ok(c, r)]
    for v in cells:
        ev = elev(v)
        if ev is None:
            continue
        same = lambda p: _ok(p[0], p[1]) and elev(p) == ev                       # noqa: E731
        nv = [tuple(x) for x in bd.neighbors(*v) if same(tuple(x))]
        if len(nv) < 2:
            continue
        for r_ in cells:
            # `has_los` : une attaque RANGED exige la ligne de vue (le board porte des `Block`).
            if not same(r_) or hexgeo.distance(v, r_) != dist or not bd.has_los(v, r_):
                continue
            nr = [tuple(x) for x in bd.neighbors(*r_) if same(tuple(x))]
            for a1 in nv:
                if hexgeo.distance(a1, r_) < 2:
                    continue
                for a2 in nr:
                    if hexgeo.distance(a2, v) < 2 or a2 in (a1, v, r_):
                        continue
                    for m in nv:
                        if m in (a1, a2, r_, v):
                            continue
                        sac = next((tuple(x) for x in bd.neighbors(*r_)
                                    if same(tuple(x)) and tuple(x) not in (v, a1, a2, r_, m)), None)
                        if sac is None:
                            continue
                        # `SACM` : le sacrifice du bras MELEE (`sk_stun`) doit etre AU CONTACT de
                        # `M`, d'ou un voisin propre a `M` -- Macer n'a qu'une arme de melee.
                        sacm = next((tuple(x) for x in bd.neighbors(*m)
                                     if same(tuple(x))
                                     and tuple(x) not in (v, a1, a2, r_, m, sac)), None)
                        if sacm is None:
                            continue
                        # `SACFAR` : le figurant ennemi des bras SANS overkill. Il doit etre LOIN
                        # de l'attaquant RANGED -- MESURE : un ennemi ADJACENT a l'attaquant reduit
                        # son `fromHere` a CE SEUL ennemi (l'attaque normale ne peut plus viser la
                        # victime a 2 hex), et le bras rendait alors `n=0` cote natif.
                        far = next((p for p in cells
                                    if same(p) and min(hexgeo.distance(p, q)
                                                       for q in (v, a1, a2, r_, m)) >= 3), None)
                        if far is None:
                            continue
                        # `KILLER` : la tuile du TUEUR d'`oa_crit`, AU CONTACT de `SACFAR` et loin
                        # de la zone de mesure. L'overkill et l'attaque mesuree doivent tomber dans
                        # le MEME tour (l'aura 1433 ne dure qu'UN tour) : il faut donc DEUX unites
                        # de mon camp, pas un passage de tour.
                        killer = next((tuple(x) for x in bd.neighbors(*far)
                                       if same(tuple(x))
                                       and min(hexgeo.distance(tuple(x), q)
                                               for q in (v, a1, a2, r_, m)) >= 2), None)
                        if killer is None:
                            continue
                        g = {"V": v, "A1": a1, "A2": a2, "R": r_, "M": m, "SAC": sac,
                             "SACM": sacm, "SACFAR": far, "KILLER": killer,
                             "elev": ev, "board": board_id, "dist": dist}
                        _GEO_CACHE[key] = g
                        return g
    raise SystemExit("[953] aucune geometrie a elevation CONSTANTE trouvee sur %s (dist=%d)"
                     % (board_id, dist))


# --------------------------------------------------------------------------- sortie


def _done(out, verbose):
    if verbose:
        _report(out)
    return out


def _report(r):
    print("[953/954] arm=%-14s mutate=%-5s runner=%s ids=%s"
          % (r["arm"], r.get("mutate"), r.get("runner"), r.get("ids")))
    if r.get("error"):
        print("       ERREUR : %s" % r["error"])
        return
    g = r.get("geo") or {}
    print("       geo pos=%s elev=%s" % (g.get("pos"), g.get("elev")))
    for k in ("d_ada_victim", "d_ada_att", "d_att_victim", "d_macer_victim"):
        if k in g:
            print("       %s = %s" % (k, g[k]))
    if g.get("fail"):
        for f in g["fail"]:
            print("       %s" % f)
        return
    if "overkill" in r:
        print("       OVERKILL prealable : hits=%s -> effets d'Adamatar %s"
              % (r["overkill"]["hits"], r["overkill"]["ada_effects_after"]))
    if "hurt" in r:
        print("       BLESSURE de Macer : %s (total %s)"
              % (r["hurt"]["hits_on_macer"], r["hurt"]["total"]))
    if "kill" in r:
        print("       KILL prealable : hits=%s" % r["kill"]["hits"])
    if "macer_hp" in r:
        print("       Macer hp=%s effets(natif)=%s effets(port)=%s"
              % (r["macer_hp"], r.get("macer_effects"), r.get("port_macer_effects")))
    if "ada_effects" in r:
        print("       Adamatar effets(natif)=%s effets(port)=%s"
              % (r["ada_effects"], r.get("port_ada_effects")))
    n, p = r.get("native") or {}, r.get("port") or {}
    print("       NATIF  n=%-2s total=%-9s hits=%s" % (n.get("n"), n.get("total"), n.get("hits")))
    print("       PORT   n=%-2s total=%-9s hits=%s" % (p.get("n"), p.get("total"), p.get("per_hit")))
    if n.get("tgt_effects_after") is not None:
        print("       cible APRES : natif=%s port=%s"
              % (n.get("tgt_effects_after"), p.get("tgt_effects_after")))
        print("       Macer APRES : natif=%s port=%s"
              % (n.get("macer_effects_after"), p.get("macer_effects_after")))


ARMS_OA = ("oa_aura", "oa_away", "oa_melee", "oa_crit", "oa_crit_ctl", "oa_crit_nonchaos")
ARMS_SK = ("sk_full", "sk_hurt", "sk_stun", "sk_nostun")


# --------------------------------------------------------------------------- facade + verdicts


def run(arm: str, mutate: bool = False, verbose: bool = True, seed=SEED, board=BOARD,
        mutate_effect=None) -> dict:
    """Facade UNIQUE (le test de garde n'appelle que celle-ci). `mutate_effect` = mutation
    SELECTIVE par nom d'`EffectType` (aucun trigger, aucun seed touche)."""
    global MUTATE_ONLY
    old = MUTATE_ONLY
    MUTATE_ONLY = list(mutate_effect) if mutate_effect else None
    if MUTATE_ONLY:
        mutate = True
    try:
        fn = run_oa if arm.startswith("oa_") else run_sk
        return fn(arm, mutate=mutate, verbose=verbose, seed=seed, board=board)
    finally:
        MUTATE_ONLY = old


def verdict_geometry(res: dict) -> list:
    """La geometrie EST le discriminant : si elle n'est pas celle demandee, tout verdict d'aval est
    VIDE. Elle est verifiee AVANT tout, bras par bras, contre le `boardGraph` LIVE."""
    f = list((res.get("geo") or {}).get("fail") or [])
    if res.get("error"):
        f.append("[geo] %s : %s" % (res.get("arm"), res["error"]))
    g, arm = res.get("geo") or {}, res.get("arm")
    if arm in ("oa_aura", "oa_melee", "oa_crit", "oa_crit_ctl", "oa_crit_nonchaos"):
        if g.get("d_ada_victim") != 1:
            f.append("[geo] %s : Adamatar doit etre ADJACENT a la victime (d=%s)"
                     % (arm, g.get("d_ada_victim")))
    if arm == "oa_away":
        if (g.get("d_ada_victim") or 0) < 2:
            f.append("[geo] oa_away : Adamatar doit etre HORS contact de la victime (d=%s)"
                     % g.get("d_ada_victim"))
        if g.get("d_ada_att") != 1:
            f.append("[geo] oa_away : Adamatar doit etre ADJACENT a l'ATTAQUANT -- c'est CE cran "
                     "qui rend le temoin discriminant (d=%s)" % g.get("d_ada_att"))
    if arm in ("oa_aura", "oa_away", "oa_crit", "oa_crit_ctl", "oa_crit_nonchaos"):
        if g.get("d_att_victim") == 1:
            f.append("[geo] %s : l'attaquant doit tirer A DISTANCE (d=%s)"
                     % (arm, g.get("d_att_victim")))
    if arm == "oa_melee" and g.get("d_att_victim") != 1:
        f.append("[geo] oa_melee : l'attaquant doit etre AU CONTACT (d=%s)" % g.get("d_att_victim"))
    if arm and arm.startswith("sk_") and g.get("d_macer_victim") != 1:
        f.append("[geo] %s : Macer doit etre AU CONTACT de sa cible (d=%s)"
                 % (arm, g.get("d_macer_victim")))
    evs = {v for v in (g.get("elev") or {}).values() if v is not None}
    if len(evs) > 1:
        f.append("[geo] %s : elevations INEGALES %s -- le terme d'elevation separerait les bras"
                 % (arm, g.get("elev")))
    return f


def verdict_carrier_effects(res: dict) -> list:
    """Le porteur PORTE bien ses effets -- sans ce cran, un zero de canal ne se distinguerait pas
    d'un zero de POSE (et le port ne serait pas confronte, juste muet des deux cotes)."""
    f, arm = [], res.get("arm")
    if arm and arm.startswith("oa_"):
        nat, port = res.get("ada_effects") or [], res.get("port_ada_effects") or []
        if EFF_OA_DMG not in nat:
            f.append("[pose] %s : Adamatar ne porte PAS 1432 cote natif (%s)" % (arm, nat))
        if EFF_OA_DMG not in port:
            f.append("[pose] %s : le port ne materialise PAS 1432 (%s)" % (arm, port))
        want_crit = arm in ("oa_crit", "oa_crit_nonchaos")
        if want_crit and EFF_OA_CRIT not in nat:
            f.append("[pose] %s : l'OVERKILL n'a PAS arme l'aura 1433 cote natif (%s)" % (arm, nat))
        if want_crit and EFF_OA_CRIT not in port:
            f.append("[pose] %s : le port ne materialise PAS l'aura 1433 (%s)" % (arm, port))
        if not want_crit and EFF_OA_CRIT in nat:
            f.append("[pose] %s : l'aura 1433 est presente alors qu'AUCUN overkill n'a eu lieu (%s)"
                     % (arm, nat))
    if arm and arm.startswith("sk_"):
        nat, port = res.get("macer_effects") or [], res.get("port_macer_effects") or []
        if EFF_SK_DMG not in nat:
            f.append("[pose] %s : Macer ne porte PAS 1263 cote natif (%s)" % (arm, nat))
        if EFF_SK_DMG not in port:
            f.append("[pose] %s : le port ne materialise PAS 1263 -- c'est le seed "
                     "`ABILITY_INIT_OWNER_EFFECTS` qui le pose quand la condition est FAUSSE et que "
                     "le canal ACTIF-ONLY ne le publie donc pas (%s)" % (arm, port))
        if arm == "sk_stun":
            if EFF_SK_MARK not in nat:
                f.append("[pose] sk_stun : le KILL n'a PAS pose le marqueur 1264 cote natif (%s)"
                         % nat)
            if EFF_SK_MARK not in port:
                f.append("[pose] sk_stun : le port ne pose PAS le marqueur 1264 (%s)" % port)
        if arm == "sk_nostun" and EFF_SK_MARK in nat:
            f.append("[pose] sk_nostun : le marqueur 1264 est la sans aucun kill (%s)" % nat)
    return f


def verdict_port_matches_native(res: dict) -> list:
    """Le rejeu OFFLINE egale le natif A L'UNITE, coup par coup."""
    n, p = res.get("native") or {}, res.get("port") or {}
    f = []
    if not n.get("n"):
        f.append("[port] %s : le NATIF n'a rendu AUCUN coup -- la mesure est VIDE, pas verte"
                 % res.get("arm"))
        return f
    if list(n.get("hits") or []) != list(p.get("per_hit") or []):
        f.append("[port] %s : natif %s (n=%s, %s) != port %s (n=%s, %s)"
                 % (res.get("arm"), n.get("hits"), n.get("n"), n.get("total"),
                    p.get("per_hit"), p.get("n"), p.get("total")))
    return f


def verdict_stun(stun: dict, nostun: dict) -> list:
    """Le NATIF pose bien `Stunned` sur la cible quand Macer a deja tue, et PAS sinon ; le PORT
    rend la MEME liste d'effets des deux cotes."""
    f = []
    for tag, res, want in (("sk_stun", stun, True), ("sk_nostun", nostun, False)):
        nat = set((res.get("native") or {}).get("tgt_effects_after") or [])
        port = set((res.get("port") or {}).get("tgt_effects_after") or [])
        if (EFF_STUNNED in nat) is not want:
            f.append("[stun] %s : NATIF %s `Stunned` (%s)"
                     % (tag, "sans" if want else "avec", sorted(nat)))
        if nat != port:
            f.append("[stun] %s : effets de la cible natif=%s != port=%s"
                     % (tag, sorted(nat), sorted(port)))
    return f


def verdict_aura_discriminant(aura: dict, away: dict) -> list:
    """Le NATIF dit bien ce qu'on porte : a geometrie d'attaque IDENTIQUE, Adamatar ADJACENT A LA
    VICTIME fait encaisser STRICTEMENT plus que le meme Adamatar adjacent a l'ATTAQUANT."""
    f = []
    na, nw = (aura.get("native") or {}).get("total"), (away.get("native") or {}).get("total")
    if na is None or nw is None:
        return ["[natif] mesure absente (aura=%s away=%s)" % (na, nw)]
    if na <= nw:
        f.append("[natif] l'aura ne discrimine PAS : oa_aura=%s <= oa_away=%s" % (na, nw))
    return f


def verdict_mutation(base: dict, mut: dict, porteur: bool) -> list:
    """CONTRE-EPREUVE. Le port NEUTRALISE doit DIVERGER dans un bras porteur et rester EGAL dans un
    temoin. Premier cran : les deux mesures NATIVES doivent coincider, sans quoi l'A/B n'est pas
    attribuable (le natif n'a pas bouge entre les deux runs)."""
    f = []
    nb, nm = (base.get("native") or {}).get("total"), (mut.get("native") or {}).get("total")
    if nb != nm:
        f.append("[mutation] le NATIF differe entre les deux runs (%s vs %s) : l'A/B n'est pas "
                 "attribuable" % (nb, nm))
        return f
    pb, pm = (base.get("port") or {}).get("total"), (mut.get("port") or {}).get("total")
    if porteur:
        if pm == pb:
            f.append("[mutation] %s : port NEUTRALISE mais le rejeu rend TOUJOURS %s -- la mutation "
                     "NE MORD PAS, le bras ne prouve donc rien" % (base.get("arm"), pm))
    else:
        if pm != pb:
            f.append("[mutation] %s (TEMOIN) : le port neutralise CHANGE le resultat (%s -> %s) -- "
                     "le port contribuait la ou il ne devrait pas" % (base.get("arm"), pb, pm))
    return f


def main(argv=None):
    ap = argparse.ArgumentParser(description="#953/#954 -- confrontation live")
    ap.add_argument("--arm", action="append",
                    help="bras a jouer (defaut : tous). %s" % (ARMS_OA + ARMS_SK,))
    ap.add_argument("--mutate", action="store_true", help="contre-epreuve : port NEUTRALISE")
    ap.add_argument("--mutate-effect", action="append",
                    help="mutation SELECTIVE : ne neutraliser QUE ces EffectType (par nom), et "
                         "aucun trigger ni seed -- pour falsifier UNE face a la fois")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--json", help="ecrit le resultat brut dans ce fichier")
    a = ap.parse_args(argv)
    global MUTATE_ONLY
    MUTATE_ONLY = list(a.mutate_effect) if a.mutate_effect else None
    if MUTATE_ONLY:
        a.mutate = True
    arms = a.arm or list(ARMS_OA + ARMS_SK)
    res = {}
    for arm in arms:
        fn = run_oa if arm.startswith("oa_") else run_sk
        res[arm] = fn(arm, mutate=a.mutate, seed=a.seed, board=a.board)
    MUTATE_ONLY = None
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


if __name__ == "__main__":
    main()
