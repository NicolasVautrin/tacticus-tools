#!/usr/bin/env python
"""probe #504 -- `KillMaimBurn` (1132, `worldKharn`) CONFRONTEE au natif, bande par bande.

CE QUI EST MESURE
-----------------
Avant #504 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc la face
DECISION la choisissait (playbook porte depuis #362) et l'execution l'ignorait -- 0 degat, 0 effet,
AUCUNE erreur. Le probe monte QUATRE regimes, prend une capture complete
(`decisionView`/`observeBattle`/`combatSnapshot`/`tileMeta`/`boardGraph` + `dumpRng`), REJOUE le
cast hors-ligne sur cette capture par le CHEMIN COMPLET du moteur (`Runner.apply`), puis lance le
cast NATIF sur le MEME runner, et confronte la **SEQUENCE**, pas un scalaire :

  E1  QUI est frappe par CHAQUE bande  -- le vecteur `{unite: degat}` (les trois bandes ont des
      cibles DISTINCTES des que la precedente meurt : le vecteur EST la sequence) ;
  E1' la SEQUENCE coup par coup        -- les 8 `UnitDamaged` natifs (`Active_Ability_Type=1132`)
      confrontes aux `per_hit_health` du port, CAPES comme le natif cape (`Amount` = PV reellement
      retires). C'est le seul canal qui montre l'ORDRE des bandes ;
  E2  COMBIEN au total                 -- 1x Piercing + 6x Eviscerate + 1x Plasma ;
  E3  QUELLE BRANCHE de `GetNextTarget` -- `alive` / `retarget` / `otherwise`, lue du port ;
  E4' les TIRAGES `genrand_int32` consommes, PORT vs NATIF (`dumpRng` avant/apres). C'est l'etage
      qui LOCALISE une divergence : meme compte + montants differents = arithmetique ; comptes
      differents = STRUCTURE. Il a trouve les DEUX bugs de ce port (cf. ci-dessous).

MONTAGE (board `MC1_67`, seed 504) -- les positions sont DRIVEES, jamais subies
-------------------------------------------------------------------------------
    worldKharn        (5,5)   le caster (« Kharn », HERO du pool au rank 17)
    deathRotbone      (1,1)   FIGURANT (cf. `FILLER`) -- garde le tour au camp joueur
    necroWarden       (5,6)   ennemi ADJACENT  -> la cible du MESSAGE (bande 1)
    orksNob           (5,4)   ennemi ADJACENT  -> pool d'`AdjacentEnemies(caster)` (bande 2)
    tauMarksman       (6,5)   ennemi ADJACENT (R1..R3) / (5,3) DISTANCE 2 (R4)
    ultraApothecary   (5,7)   ennemi a DISTANCE 2 (NON adjacent) -> dans le pool de la bande 3
                              (`SurroundingEnemies(caster, range = 2)`) et ABSENT de celui de la
                              bande 2. C'est lui qui SEPARE les deux pools.

REGIMES -- chacun descend d'un cran dans la chaine de re-ciblage
----------------------------------------------------------------
    R1 `survivant`  personne ne meurt -> `IsAlive(previousTarget)` VRAI partout -> les TROIS bandes
       frappent la MEME cible, AUCUN tirage de tri. Isole les trois plages/profils/comptes de coups.
    R2 `une mort`   la bande 1 TUE la cible du message ; les bandes 2 et 3 frappent le survivant
       re-cible (qui SURVIT : un regime ou tout est surtue est degenere pour le total).
    R3 `deux morts` la bande 2 tue a son tour -- mais la bande 3 ne descend PAS pour autant a son
       propre pool : `t3` re-evalue `t2`, qui se re-cible seul tant qu'il reste un ADJACENT.
    R4 `pool elargi` les deux survivants sont a DISTANCE 2 -> le pool de `t2` est VIDE, `.Otherwise`
       rend le cadavre, `IsAlive` est FAUX, et `t3` consulte ENFIN
       `Unobscured(SurroundingEnemies(caster, range = 2))`. C'est le SEUL regime ou `AB5` diverge.

LES DEUX BUGS QUE CE PROBE A TROUVES (tous deux INVISIBLES d'un critere sur le total)
-------------------------------------------------------------------------------------
  * `Group` n'evaluait PAS son selecteur de groupe, alors que `GroupBehaviour$$Execute` fait
    `targets = (+0x68).Select(entities)` AVANT le child -> une evaluation de re-ciblage perdue
    PAR BANDE, donc des tirages perdus ;
  * `GetNextTarget` n'evaluait `previousTarget` QU'UNE FOIS, alors qu'`IfSelector.Select` l'evalue
    pour le TRIGGER (`IsAlive`) PUIS pour la branche VRAIE rendue.
  Effet cumule, mesure en R2 : port 20 tirages contre 24 natifs, et les 8 montants divergents --
  pendant que le DELTA PAR UNITE, lui, restait juste (les cibles etaient surtuees).

LES SEPT CONTRE-EPREUVES (`--ab`) -- mesurees en R4 le 2026-08-07, 7/7 DISCRIMINANTES
-------------------------------------------------------------------------------------
    REF                       14308  == NATIF
    AB1 profils permutes      15533  (memes coups, memes plages : seul le PROFIL tourne)
    AB2 un seul volet         18768  (les 3 bandes sur minDmg/maxDmg/nrOfHits)
    AB3 ordre inverse          9000  (bandes 3-2-1 : MEME nombre de coups, seule la SEQUENCE change)
    AB4 sans re-ciblage        4000  (les 3 bandes sur la cible du message, qui meurt a la 1re)
    AB5 pool bande 3 adjacent  9000  (la bande 3 ne trouve personne : le pool ELARGI est LU)
    AB6 tri sans tirage       13553  (le tri prend la borne MIN -> 2 tirages perdus, tout se decale)

Usage (depuis `scripts/python`, ASCII only) :
    python probe_504_kill_maim_burn.py                 # les quatre regimes
    python probe_504_kill_maim_burn.py --regime R4     # un seul
    python probe_504_kill_maim_burn.py --ab            # + les contre-epreuves hors-ligne
    python probe_504_kill_maim_burn.py --keep          # ne dispose PAS les runners
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))

KILL_MAIM_BURN = 1132                      # `ActiveAbilityType.KillMaimBurn`

CASTER = "worldKharn"                      # « Kharn the Betrayer », seul porteur LINEUP de 1132
FOE_MAIN = "necroWarden"                   # (5,6) adjacent -- cible du message
FOE_ADJ_A = "orksNob"                      # (5,4) adjacent
FOE_ADJ_B = "tauMarksman"                  # (6,5) adjacent
FOE_FAR = "ultraApothecary"                # (5,7) distance 2 -- SEPARE les pools des bandes 2 et 3
#: ⚠ FIGURANT OBLIGATOIRE, et c'est une MESURE, pas une precaution. Sans lui, `worldKharn` est la
#: SEULE unite du camp joueur : le cast termine son tour, `act` bascule sur le camp adverse, et le
#: TURN-START ennemi rend a `necroWarden` la totalite des PV qu'on venait de lui prendre
#: (mesure du 2026-08-07 : 400000 -> 360531 dans les events du cast, puis 400000 dans le
#: `decisionView` d'apres). Le delta lu valait alors `{}` -- un FAUX ZERO qui accusait le port
#: alors que les events natifs, eux, portaient EXACTEMENT le total du port (39469). Le figurant
#: garde le tour au camp joueur, donc la fenetre de mesure reste ouverte.
FILLER = "deathRotbone"

BOARD = "MC1_67"
SEED = 504
PLACES = ((CASTER, "5,5"), (FILLER, "1,1"))
A_PLACES = ((FOE_MAIN, "5,6"), (FOE_ADJ_A, "5,4"), (FOE_ADJ_B, "6,5"), (FOE_FAR, "5,7"))
TOUS = (CASTER, FILLER, FOE_MAIN, FOE_ADJ_A, FOE_ADJ_B, FOE_FAR)

#: `UnitDamaged` natif : on lit la SEQUENCE coup par coup (cible, montant, profil), pas un total.
RE_DMG = re.compile(
    r"UnitDamaged e=(\d+).*?Attacker_Id=(\d+) Target_Id=(\d+) Amount=(-?\d+) "
    r"DamageProfileType=(\d+) Active_Ability_Type=(\d+)")

#: PV per-unit des regimes a re-ciblage. ⚠ NE PAS tout faire mourir : un regime ou CHAQUE cible est
#: surtuee est DEGENERE pour le total (le delta vaut les PV, quelle que soit la bande qui frappe) --
#: mesure du 2026-08-07, six contre-epreuves sur sept y rendaient le MEME 13000. Les PV sont donc
#: choisis pour que la DERNIERE cible de la chaine SURVIVE, et distincts entre eux pour que le tri
#: par utilite ne soit pas un ex aequo (un ex aequo mesure le tie-break, pas ce qu'on croit).
#: R2 -- la bande 1 tue la cible du message ; les bandes 2 et 3 frappent le survivant re-cible.
R2_HP = {FOE_MAIN: 4000, FOE_ADJ_A: 200000, FOE_ADJ_B: 400000, FOE_FAR: 100000}
#: R3 -- deux morts : la bande 2 tue a son tour, donc la bande 3 re-cible sur son pool ELARGI
#: (`SurroundingEnemies(caster, range = 2)`), ou seul `FOE_FAR` (distance 2) est un candidat de plus
#: qu'`AdjacentEnemies`. Ses PV sont les plus bas des restants -> il GAGNE le tri par utilite, donc
#: la bande 3 le frappe : c'est ce qui SEPARE le pool de la bande 3 de celui de la bande 2.
#: `FOE_ADJ_A` a 5000 PV MEURT au 6e coup de la bande 2 (cumul mesure 5647) ; a 6000 il SURVIT et la
#: bande 3 le re-frappe sans jamais toucher au pool elargi -- le regime ne mesurerait alors pas ce
#: pour quoi il existe.
R3_HP = {FOE_MAIN: 4000, FOE_ADJ_A: 5000, FOE_ADJ_B: 400000, FOE_FAR: 60000}
#: R4 -- le SEUL regime qui atteigne le pool PROPRE de la bande 3. Mesure (#504) : en R3 la bande 3
#: ne consulte JAMAIS son pool, parce que `t3 = If(IsAlive(t2), t2, First(sorted3))` re-evalue `t2`,
#: lequel se re-cible tout seul tant qu'il RESTE un ennemi ADJACENT. Pour descendre d'un cran il
#: faut que le pool de `t2` (`AdjacentEnemies`) soit VIDE au moment de la bande 3 : les deux
#: survivants sont donc places a DISTANCE 2 (`A_PLACES_R4`), hors adjacence. La chaine devient
#: `t2` -> pool vide -> `First` vide -> `.Otherwise(previousTarget)` = le cadavre -> `IsAlive` FAUX
#: -> `t3` consulte ENFIN `Unobscured(SurroundingEnemies(caster, range = 2))`.
R4_HP = {FOE_MAIN: 4000, FOE_ADJ_A: 5000, FOE_ADJ_B: 400000, FOE_FAR: 60000}
HP_PAR_REGIME = {"R2": R2_HP, "R3": R3_HP, "R4": R4_HP}
#: (5,3) et (5,7) sont a distance hex 2 de (5,5) : hors `AdjacentEnemies`, dans
#: `SurroundingEnemies(caster, 2)`. `FOE_FAR` a les PV les plus bas -> il GAGNE le tri par utilite.
A_PLACES_R4 = ((FOE_MAIN, "5,6"), (FOE_ADJ_A, "5,4"), (FOE_ADJ_B, "5,3"), (FOE_FAR, "5,7"))


# ------------------------------------------------------------------ transport

def _sid():
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["session"]["id"]


def _rpc(sid, method, body=None, timeout=120):
    payload = json.dumps({"method": method,
                          "args": [body] if body is not None else []}).encode("utf-8")
    req = urllib.request.Request("%s/api/scripts/%s/rpc" % (HOST, sid), data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _duel(args, timeout=400):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=PYDIR,
                          capture_output=True, text=True, timeout=timeout)


# ------------------------------------------------------------------ montage

def build(state_file: str, regime: str):
    """Monte le runner du regime demande. Rend `runnerId`, ou `None` si le build echoue."""
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--crit", "0,0",
            "--p-units", ",".join(v for v, _t in PLACES),
            "--a-units", ",".join(v for v, _t in A_PLACES),
            "--state-file", state_file]
    if regime == "R1":
        argv += ["--hp-target", "400000"]
    else:
        # `--unit-stat` patche le BC NORMALISE per-unit : c'est le pendant per-unit de
        # `--hp-target`, indispensable des que la mesure porte sur un ECART entre deux unites du
        # meme camp (ici : des seuils de mort distincts + un ordre d'utilite non degenere).
        for vid, hp in HP_PAR_REGIME[regime].items():
            argv += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (vid, hp, hp)]
    for vid, tile in PLACES:
        argv += ["--place", "%s:%s" % (vid, tile)]
    for vid, tile in (A_PLACES_R4 if regime == "R4" else A_PLACES):
        argv += ["--a-place", "%s:%s" % (vid, tile)]
    p = _duel(argv)
    if p.returncode != 0:
        print("[build %s] rc=%s\n%s\n%s" % (regime, p.returncode, p.stdout[-1500:], p.stderr[-800:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def unites(sid, rid):
    """{visualId: {'id','pos','hp','alive'}} -- aucun id d'entite en dur."""
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = {"id": u.get("id"), "pos": (p.get("col"), p.get("row")),
                                  "hp": u.get("hp"), "alive": not u.get("isDead")}
    return out


def capture(sid, rid):
    """L'etat COMPLET juste avant le cast natif -- le substrat du rejeu porte."""
    return {
        "dv": _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "ob": _rpc(sid, "observeBattle", {"runnerId": rid}, 90),
        "snap": _rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
        "tm": _rpc(sid, "tileMeta", {"runnerId": rid}, 120),
        "tiles": _rpc(sid, "boardGraph", {"runnerId": rid}, 90)["tiles"],
        "rng": _rpc(sid, "dumpRng", {"runnerId": rid}, 60),
    }


def assert_montage(u, regime):
    """Un montage DEGENERE rendrait l'accord trivial : on echoue AVANT de mesurer, jamais apres."""
    manquants = [v for v in TOUS if v not in u]
    if manquants:
        raise SystemExit("montage invalide : unites absentes %r" % (manquants,))
    voulu = dict(PLACES) | dict(A_PLACES_R4 if regime == "R4" else A_PLACES)
    mauvais = [(v, u[v]["pos"], voulu[v]) for v in voulu
               if u[v]["pos"] != tuple(int(x) for x in voulu[v].split(","))]
    if mauvais:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %r" % (mauvais,))
    if regime in HP_PAR_REGIME:
        ecart = {v: u[v]["hp"] for v in HP_PAR_REGIME[regime]}
        if len(set(ecart.values())) != len(ecart):
            raise SystemExit("%s DEGENERE : PV non distincts %r" % (regime, ecart))
        voulus = HP_PAR_REGIME[regime]
        faux = {v: (ecart[v], voulus[v]) for v in voulus if ecart[v] != voulus[v]}
        if faux:
            raise SystemExit("%s : `--unit-stat` NON APPLIQUE %r" % (regime, faux))


# ------------------------------------------------------------------ rejeu hors-ligne

def etat_porte(cap):
    """`State` charge depuis la capture, PRNG cale sur `dumpRng`.

    ⚠ Sans ce calage `execute_ability_attack` SKIPPE le degat par repli defensif : on lirait un
    faux `0` et l'accord ne prouverait rien."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    board = Board(cap["tiles"], adjacency="native_sym")
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"])
    d = cap["rng"]
    if not (isinstance(d, dict) and d.get("mt")):
        raise SystemExit("dumpRng VIDE -- MT non calable, aucune mesure de degat n'a de sens")
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(d["mt"]), d["mti"]
    st.rng = rng
    return st


def _hp(st, ids):
    from engine.runner.components import HealthComponent
    out = {}
    for i in ids:
        e = st.get_entity(int(i))
        h = e.get_component(HealthComponent) if e is not None else None
        out[int(i)] = None if h is None else h.hp
    return out


def rejeu_porte(cap, caster_id, target_id, ids):
    """Rejoue le cast par le CHEMIN COMPLET du moteur (`Runner.apply(ActiveAbilityMessage)`), pas
    par un appel direct a `execute_behaviour` : c'est ce qui exerce le registre `ABILITY_CLASSES`
    et rend `ability_handler.last['ported']` -- l'observable qui distingue le port du NO-OP."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    st = etat_porte(cap)
    avant = _hp(st, ids)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_id), target_id=int(target_id),
                                      ability_type=KILL_MAIM_BURN))
    last = getattr(runner.ability_handler, "last", None) or {}   # `diag` est SPREAD dans `last`
    apres = _hp(st, ids)
    # SEQUENCE au format NATIF : `UnitDamaged.Amount` est la part de PV REELLEMENT retiree, donc
    # CAPEE par les PV restants (mesure : bande 1 a 11603 sur une cible a 4000 PV -> event 4000).
    # On applique le meme cap au port, sinon on comparerait deux grandeurs differentes.
    hp_run, seq = dict(avant), []
    for a in (last.get("attacks") or []):
        t, atk = int(a.get("target")), (a.get("attack") or {})
        for m in (atk.get("per_hit_health") or []):
            applique = max(0, min(int(m), int(hp_run.get(t) or 0)))
            hp_run[t] = int(hp_run.get(t) or 0) - applique
            seq.append((t, applique))
    return {
        "ported": last.get("ported"),
        "delta": {i: (avant[i] - apres[i]) for i in avant
                  if avant[i] is not None and apres[i] is not None and avant[i] != apres[i]},
        "attaques": [(a.get("target"), a.get("total")) for a in (last.get("attacks") or [])],
        "seq": seq,
        "seq_brute": [(int(a.get("target")), int(m)) for a in (last.get("attacks") or [])
                      for m in ((a.get("attack") or {}).get("per_hit_health") or [])],
        "mt": (list(st.rng.mt), st.rng.mti),
        "nt2": last.get("next_target_2"), "nt3": last.get("next_target_3"),
    }


def tirages(rng_initial, mt_cible, mti_cible, cap=600):
    """Nombre de `genrand_int32` consommes pour aller de l'etat INITIAL a l'etat CIBLE.

    C'est l'etage qui LOCALISE une divergence de sequence : deux moteurs qui rendent des montants
    differents mais consomment le MEME nombre de tirages ont un bug d'ARITHMETIQUE ; s'ils n'en
    consomment pas le meme nombre, c'est la STRUCTURE (un tirage en trop ou en moins) -- et un
    tirage manquant decale TOUT l'aval, ce qu'un total peut masquer. Rend None si non atteint."""
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt, r.mti = list(rng_initial["mt"]), rng_initial["mti"]
    for n in range(cap + 1):
        if r.mti == mti_cible and r.mt == mt_cible:
            return n
        r.genrand_int32()
    return None


# ------------------------------------------------------------------ contre-epreuves

def contre_epreuves(cap, caster_id, target_id, ids):
    """Chaque variante ne change QU'UNE lecture du mirror. Si l'une rendait le MEME resultat que
    REF, la lecture correspondante ne serait pas mesuree par ce montage."""
    from engine.dsl.base import Const
    from engine.dsl.effects import ExecutionContext
    from engine.entities.behaviours import op_and, AtomicGroup, Group
    from engine.entities.selectors.accessors import CasterTile, Target
    from engine.entities.selectors.units import AdjacentEnemies, SurroundingEnemies, Unobscured
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.abilities.behaviours.context import entities_from_state
    import engine.runner.abilities.worldeaters as WE

    aid = int(ActiveAbilityType.KillMaimBurn)
    grp = int(WE.KILL_MAIM_BURN_GROUP)

    def _bande(sel, profil, mn, mx, hk):
        return AttackWithAttackDamage(sel, WE.KILL_MAIM_BURN_ID, profil, is_melee=True, multi=True,
                                      min_key=mn, max_key=mx, hits_key=hk,
                                      native_factory="attack", ability_type=aid)

    def _ref(st):
        t2, t3 = WE.kill_maim_burn_selectors(st, int(caster_id))
        return WE.kill_maim_burn_tree(t2, t3)

    def _profils_permutes(st):
        """Les trois profils tournes d'un cran : meme nombre de coups, meme plages."""
        t2, t3 = WE.kill_maim_burn_selectors(st, int(caster_id))
        b1 = _bande(Target(), "Eviscerate", "minDmg", "maxDmg", "nrOfHits")
        b2 = _bande(t2, "Plasma", "minDmg_2", "maxDmg_2", "nrOfHits_2")
        b3 = _bande(t3, "Piercing", "minDmg_3", "maxDmg_3", "nrOfHits_3")
        return AtomicGroup(op_and(op_and(Group(b1, grp, Target()), Group(b2, grp, t2)),
                                  Group(b3, grp, t3)))

    def _un_seul_volet(st):
        """Les trois bandes sur le volet 1 (l'erreur qu'on ferait en ignorant MinMaxDamage2/3)."""
        t2, t3 = WE.kill_maim_burn_selectors(st, int(caster_id))
        b1 = _bande(Target(), "Piercing", "minDmg", "maxDmg", "nrOfHits")
        b2 = _bande(t2, "Piercing", "minDmg", "maxDmg", "nrOfHits")
        b3 = _bande(t3, "Piercing", "minDmg", "maxDmg", "nrOfHits")
        return AtomicGroup(op_and(op_and(Group(b1, grp, Target()), Group(b2, grp, t2)),
                                  Group(b3, grp, t3)))

    def _ordre_inverse(st):
        """Bandes jouees 3-2-1 : MEME nombre de coups, seule la SEQUENCE change."""
        t2, t3 = WE.kill_maim_burn_selectors(st, int(caster_id))
        b1 = _bande(Target(), "Piercing", "minDmg", "maxDmg", "nrOfHits")
        b2 = _bande(t2, "Eviscerate", "minDmg_2", "maxDmg_2", "nrOfHits_2")
        b3 = _bande(t3, "Plasma", "minDmg_3", "maxDmg_3", "nrOfHits_3")
        return AtomicGroup(op_and(op_and(Group(b3, grp, t3), Group(b2, grp, t2)),
                                  Group(b1, grp, Target())))

    def _sans_retarget(st):
        """`GetNextTarget` remplace par « toujours la cible du message » : le mirror SANS le
        `If(IsAlive(prev), prev, First(sorted))`. Aucun tirage de tri consomme."""
        b1 = _bande(Target(), "Piercing", "minDmg", "maxDmg", "nrOfHits")
        b2 = _bande(Target(), "Eviscerate", "minDmg_2", "maxDmg_2", "nrOfHits_2")
        b3 = _bande(Target(), "Plasma", "minDmg_3", "maxDmg_3", "nrOfHits_3")
        return AtomicGroup(op_and(op_and(Group(b1, grp, Target()), Group(b2, grp, Target())),
                                  Group(b3, grp, Target())))

    def _pool_bande3_adjacent(st):
        """Bande 3 re-ciblee sur `AdjacentEnemies` au lieu de
        `Unobscured(SurroundingEnemies(caster, range))` : la seule difference est l'unite a
        DISTANCE 2. Mesure que le pool elargi de la bande 3 est bien LU."""
        t2 = WE.KillMaimBurnNextTarget(Target(), AdjacentEnemies(CasterTile()), st,
                                       *_bornes2(st, caster_id))
        t3 = WE.KillMaimBurnNextTarget(t2, AdjacentEnemies(CasterTile()), st,
                                       *_bornes2(st, caster_id))
        b1 = _bande(Target(), "Piercing", "minDmg", "maxDmg", "nrOfHits")
        b2 = _bande(t2, "Eviscerate", "minDmg_2", "maxDmg_2", "nrOfHits_2")
        b3 = _bande(t3, "Plasma", "minDmg_3", "maxDmg_3", "nrOfHits_3")
        return AtomicGroup(op_and(op_and(Group(b1, grp, Target()), Group(b2, grp, t2)),
                                  Group(b3, grp, t3)))

    def _tri_sans_tirage(st):
        """Le tri prend la BORNE MIN au lieu du `RandomAmount.Calculate()` : AUCUN
        `genrand_int32` consomme -> tout le degat aval se decale."""
        mn, mx = _bornes2(st, caster_id)
        t2 = WE.KillMaimBurnNextTarget(Target(), AdjacentEnemies(CasterTile()), st, mn, mn)
        t3 = WE.KillMaimBurnNextTarget(
            t2, Unobscured(SurroundingEnemies(CasterTile(), Const(_portee(st)))), st, mn, mn)
        for n in (t2, t3):
            n.state = _SansRng(st)
        b1 = _bande(Target(), "Piercing", "minDmg", "maxDmg", "nrOfHits")
        b2 = _bande(t2, "Eviscerate", "minDmg_2", "maxDmg_2", "nrOfHits_2")
        b3 = _bande(t3, "Plasma", "minDmg_3", "maxDmg_3", "nrOfHits_3")
        _ = mx
        return AtomicGroup(op_and(op_and(Group(b1, grp, Target()), Group(b2, grp, t2)),
                                  Group(b3, grp, t3)))

    variantes = {"REF": _ref, "AB1_profils_permutes": _profils_permutes,
                 "AB2_un_seul_volet": _un_seul_volet, "AB3_ordre_inverse": _ordre_inverse,
                 "AB4_sans_retarget": _sans_retarget,
                 "AB5_pool_bande3_adjacent": _pool_bande3_adjacent,
                 "AB6_tri_sans_tirage": _tri_sans_tirage}
    out = {}
    for nom, fabrique in variantes.items():
        st = etat_porte(cap)
        avant = _hp(st, ids)
        ectx = ExecutionContext(state=st, rng=st.rng)
        fabrique(st).execute(entities_from_state(st, int(caster_id), int(target_id)), ectx)
        apres = _hp(st, ids)
        out[nom] = {
            "delta": {i: (avant[i] - apres[i]) for i in avant
                      if avant[i] is not None and apres[i] is not None and avant[i] != apres[i]},
            "total": sum((avant[i] - apres[i]) for i in avant
                         if avant[i] is not None and apres[i] is not None and i != int(caster_id)),
        }
    return out


class _SansRng:
    """Proxy d'etat dont `rng` est None : `RandomAmount` degrade alors sur la borne MIN sans
    consommer de tirage (cf. sa docstring). Sert UNIQUEMENT a la contre-epreuve AB6."""
    __slots__ = ("_st", "rng")

    def __init__(self, st):
        self._st, self.rng = st, None

    def __getattr__(self, k):
        return getattr(self._st, k)


def _bornes2(st, caster_id):
    from engine.runner.abilities.base import ability_attack_params
    bmin, bmax, _p, _h = ability_attack_params(st, int(caster_id), "KillMaimBurn", "Eviscerate",
                                               ranged=False, min_key="minDmg_2",
                                               max_key="maxDmg_2", hits_key="nrOfHits_2")
    return bmin, bmax


def _portee(_st):
    from engine.entities.ability_constant_type import AbilityConstantType
    import engine.runner.abilities.worldeaters as WE
    return WE._kill_maim_burn_const(AbilityConstantType.range)


# ------------------------------------------------------------------ mesure

def mesure(sid, state_file, regime, avec_ab=False, garder=False):
    rid = build(state_file, regime)
    if rid is None:
        return None
    try:
        u = unites(sid, rid)
        assert_montage(u, regime)
        ids = [u[v]["id"] for v in TOUS]
        cid, tid = u[CASTER]["id"], u[FOE_MAIN]["id"]
        cap = capture(sid, rid)
        port = rejeu_porte(cap, cid, tid, ids)
        ab = contre_epreuves(cap, cid, tid, ids) if avec_ab else None
        p = _duel(["act", "ability", "--caster", str(cid), "--ability", str(KILL_MAIM_BURN),
                   "--target", str(tid), "--state-file", state_file, "--runner", str(rid)])
        apres = unites(sid, rid)
        # SEQUENCE native, coup par coup : `UnitDamaged` filtre sur `Active_Ability_Type=1132`.
        # C'est le SEUL canal qui montre l'ordre des bandes ; un total ne le montrerait pas.
        seq_n = [(int(t), int(a), int(pr)) for _e, at, t, a, pr, ab in RE_DMG.findall(p.stdout or "")
                 if int(ab) == KILL_MAIM_BURN and int(at) == int(cid)]
        natif = {"delta": {u[v]["id"]: u[v]["hp"] - apres[v]["hp"] for v in u
                           if v in apres and u[v]["hp"] is not None and apres[v]["hp"] is not None
                           and u[v]["hp"] != apres[v]["hp"]},
                 "seq": [(t, a) for t, a, _pr in seq_n], "profils": [pr for _t, _a, pr in seq_n],
                 "tronque": "(+" in (p.stdout or "") and "events)" in (p.stdout or ""),
                 "rc": p.returncode, "out": (p.stdout or "")[-2500:] + (p.stderr or "")[-800:]}
        rng_apres = _rpc(sid, "dumpRng", {"runnerId": rid}, 60)
        natif["tirages"] = (tirages(cap["rng"], rng_apres.get("mt"), rng_apres.get("mti"))
                            if isinstance(rng_apres, dict) and rng_apres.get("mt") else None)
        port["tirages"] = tirages(cap["rng"], port["mt"][0], port["mt"][1])
        return {"regime": regime, "rid": rid, "caster": cid, "cible": tid,
                "ids": {v: u[v]["id"] for v in u},
                "hp_avant": {v: u[v]["hp"] for v in u},
                "port": port, "natif": natif, "ab": ab}
    finally:
        if not garder:
            _duel(["dispose", "--state-file", state_file, "--runner", str(rid)], timeout=120)


def _rapport(m) -> bool:
    ids = m["ids"]
    inv = {i: v for v, i in ids.items()}
    print("[504:%s] runner=%s caster=u%s cible=u%s" % (m["regime"], m["rid"], m["caster"], m["cible"]))
    print("        unites : " + " ".join("%s=u%s(hp%s)" % (v, ids[v], m["hp_avant"][v])
                                         for v in sorted(ids)))
    fmt = lambda d: {("%s/u%s" % (inv.get(i, "?"), i)): v for i, v in sorted(d.items())}
    print("  E1 delta hp PORT =%s" % (fmt(m["port"]["delta"]),))
    print("             NATIF=%s" % (fmt(m["natif"]["delta"]),))
    tp = sum(v for i, v in m["port"]["delta"].items() if i != m["caster"])
    tn = sum(v for i, v in m["natif"]["delta"].items() if i != m["caster"])
    print("  E2 total    PORT=%s  NATIF=%s   (ported=%s, rc natif=%s)"
          % (tp, tn, m["port"]["ported"], m["natif"]["rc"]))
    sp, sn = m["port"]["seq"], m["natif"]["seq"]
    print("  E1' SEQUENCE coup par coup (cible, degat)")
    print("        PORT (%d coups) =%s" % (len(sp), [("u%s" % t, a) for t, a in sp]))
    print("        NATIF(%d coups) =%s" % (len(sn), [("u%s" % t, a) for t, a in sn]))
    print("        profils natifs  =%s   (events tronques=%s)"
          % (m["natif"]["profils"], m["natif"]["tronque"]))
    print("  E4' TIRAGES genrand_int32 consommes : PORT=%s  NATIF=%s"
          % (m["port"].get("tirages"), m["natif"].get("tirages")))
    print("  E3 bandes   %s" % ([(("u%s" % t), tot) for t, tot in m["port"]["attaques"]],))
    print("  E4 nt2=%s" % (m["port"]["nt2"],))
    print("     nt3=%s" % (m["port"]["nt3"],))
    if m["ab"]:
        print("  -- contre-epreuves (hors-ligne, meme capture) --")
        for nom, r in m["ab"].items():
            print("     %-26s total=%-8s delta=%s" % (nom, r["total"], fmt(r["delta"])))
    ok = (m["port"]["delta"] == m["natif"]["delta"] and sp == sn and len(sn) > 0)
    if not ok:
        print("  -- sortie du cast NATIF (diagnostic) --")
        print(m["natif"].get("out", ""))
    print("[504:%s] %s" % (m["regime"], "ACCORD port/natif sur E1+E2" if ok else "DESACCORD"))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="probe #504 -- KillMaimBurn (1132) vs natif")
    ap.add_argument("--regime", default="all", choices=("all", "R1", "R2", "R3", "R4"))
    ap.add_argument("--ab", action="store_true", help="joue aussi les contre-epreuves")
    ap.add_argument("--keep", action="store_true", help="ne dispose PAS les runners")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    base = a.state_file or os.path.join(tempfile.gettempdir(), "p504_kmb_%d" % os.getpid())
    sid = _sid()
    regimes = ("R1", "R2", "R3", "R4") if a.regime == "all" else (a.regime,)
    verdicts = []
    for reg in regimes:
        sf = "%s_%s.json" % (base[:-5] if base.endswith(".json") else base, reg)
        m = mesure(sid, sf, reg, avec_ab=a.ab, garder=a.keep)
        if m is None:
            print("[504:%s] build KO -- rien mesure" % reg)
            return 99
        verdicts.append(_rapport(m))
    return 0 if all(verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
