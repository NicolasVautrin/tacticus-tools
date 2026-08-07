#!/usr/bin/env python
"""probe #525 -- `MassDriverAccelerator` (1222, `votanChampion` « Kimm ») CONFRONTEE au natif.

CE QUI EST MESURE
-----------------
Avant #525 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc le cast
partait, l'`AbilityHandler` rendait `ported=False` et RIEN ne se passait -- 0 buff, 0 deplacement,
0 degat, AUCUNE erreur. Le probe monte plusieurs regimes, prend une capture complete
(`decisionView`/`observeBattle`/`combatSnapshot`/`tileMeta`/`boardGraph` + `dumpRng`), rejoue le cast
HORS LIGNE par le CHEMIN COMPLET du moteur (`Runner.apply`), lance le cast NATIF sur le MEME runner,
et confronte SIX etages -- jamais un scalaire :

  E0  `ported`                -- l'observable qui distingue le port du no-op ;
  E1  le BUFF `MassDriverAccelerator_ExtraMovement` (1542) : QUI le recoit. C'est le seul etage ou
      `...MassDriverAcceleratorAbility$$GetBuffTargets` = `owner@0x30 + AdjacentFriends(owner@0x30)`
      est observable, et le montage porte EXPRES un allie ADJACENT et un allie LOINTAIN : un port
      qui aurait collapse le selecteur sur le seul caster laisserait l'adjacent SANS effet, et un
      port qui aurait pris tout le camp bufferait le lointain ;
  E2  la TUILE D'ATTERRISSAGE -- `GetMoveTile` = `First(SortTilesByUtility(GetPossibleMoveTiles(),
      caster@0x48, 0x21 = MovementSuggestion, null), 1)`. Deux lectures y sont observables : la
      PORTEE (`UnitMovementRangeWithBonus`, branche `HasEffect`) et l'utilite de tri ;
  E3  le degat sur la CIBLE PRINCIPALE -- profil `damageProfile` = `DirectDamage` (pierce 100) ;
  E4  le SPLASH -- `Alive(Cache(Enemies(caster@0x48, AdjacentUnits(target@0x60))))`, profil
      `damageProfile_2` = `Physical` (pierce 1) et coups `nrOfHits_2`. C'est l'etage qui separe
      1222 d'une attaque nue : QUI est frappe, et avec QUEL profil. R2 y met DEUX ennemis pour
      exercer le `multi` (une attaque PAR cible) ;
  E5  les TIRAGES `genrand_int32` consommes, PORT vs NATIF (`dumpRng` avant/apres). C'est l'etage
      qui LOCALISE une divergence : meme compte + montants differents = arithmetique ; comptes
      differents = STRUCTURE ;
  E6  le GATE DE CIBLE -- `get_invalid_caster_reason` + `get_invalid_target_reason` avec le masque
      `0x102004032` ET la regle dynamique, confrontes au `fromHere` d'`abilityTargets` (legalite
      EXACTE du cast IMMEDIAT). C'est l'etage qui verifie la face DECIDER, distincte d'EXECUTER.

MONTAGE -- les positions sont DRIVEES, jamais subies
----------------------------------------------------
Le porteur est HORS POOL et HORS CATALOGUE (`catalog_inject.py --missing` le liste parmi les 21
unites lineup manquantes) : le seed BC est AUGMENTE par `catalog_inject.write_augmented_seed_bc`
avant tout build. Ce n'est PAS un refus de confrontabilite -- aucun `data/unspawnable_rank*.json`
n'existe sur ce porteur.

Le masque de 1222 (preset `TargetingOptions statics+0x240`, `rules = 0x102004032`, IDENTIQUE a
1204) impose trois contraintes AVANT toute mesure, et un montage qui les viole ne mesure RIEN :
  * `CasterHasNotMoved`      -> le caster n'a pas bouge (vrai au 1er tour) ;
  * `TargetIsNotAdjacent`    -> la cible doit etre a distance >= 2 ;
  * `TargetHasFreeAdjacentTile` + `GetDynamicInvalidTargetReason` -> il faut au moins une tuile
    LIBRE adjacente a la cible, atteignable en <= `MOVEMENT + extraMovement` pas depuis le caster.

ROLES (les TUILES sont declarees PAR BOARD dans `GEOM`, cf. son commentaire) :

    votanChampion    le caster -- HERO, injecte au catalogue
    ultraApothecary  allie ADJACENT (d=1) -- il DOIT recevoir le buff 1542
    bloodIntercessor allie LOINTAIN + FIGURANT (garde le tour au camp joueur apres le cast, sinon
                     le turn-start ennemi rend a la cible les PV qu'on vient de lui prendre et le
                     delta lu vaut un FAUX ZERO) -- il ne DOIT PAS l'avoir
    astraBullgryn    R4 : allie ADJACENT A LA CIBLE -- il ne DOIT PAS etre frappe
    necroWarden      la CIBLE -- distance 3, hors adjacence, hex libres autour

REGIMES
-------
    R1 `simple`   UN ennemi adjacent a la cible -> le splash frappe une seule unite.
    R2 `double`   DEUX ennemis adjacents -> le `multi` du 2e `AttackWithAttackDamage` est exerce,
       et les deux tuiles occupees CHANGENT la tuile d'atterrissage (E2 devient non trivial).
    R3 `etroit`   TROIS ennemis adjacents -> la tuile d'atterrissage est contrainte et le splash
       porte sur trois unites.
    R4 `ami`      un ALLIE est adjacent a la cible -> SEUL regime ou le filtre `Enemies` du volet
       splash est observable (E4bis : friendly fire). Sans lui, AB3 ne discrimine rien.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_525_mass_driver_accelerator.py                       # les quatre regimes
    python probe_525_mass_driver_accelerator.py --regime R2
    python probe_525_mass_driver_accelerator.py --board C2_02 --seed 777   # 2e couple (geometrie)
    python probe_525_mass_driver_accelerator.py --tables    # etage OFFLINE des registres (sans runner)
    python probe_525_mass_driver_accelerator.py --ab        # + les contre-epreuves hors-ligne
    python probe_525_mass_driver_accelerator.py --keep      # ne dispose PAS les runners
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))

MASS_DRIVER_ACCELERATOR = 1222             # `ActiveAbilityType.MassDriverAccelerator`
MDA_EXTRA_MOVEMENT = 1542                  # `EffectType.MassDriverAccelerator_ExtraMovement`

CASTER = "votanChampion"                   # « Kimm », seul porteur LINEUP de 1222 (hors catalogue)
FRIEND_NEAR = "ultraApothecary"            # allie ADJACENT -- doit recevoir le buff
FRIEND_FAR = "bloodIntercessor"            # allie LOINTAIN + figurant -- ne doit PAS le recevoir
FRIEND_ON_TARGET = "astraBullgryn"         # R4 : allie ADJACENT A LA CIBLE -- ne doit PAS etre frappe
FOE_MAIN = "necroWarden"                   # la cible du message, a distance 3
FOE_A = "orksNob"                          # splash
FOE_B = "tauMarksman"                      # splash (R2/R3)
FOE_D = "astraBullgryn"                    # encerclement (R3)

#: Board et seed par DEFAUT. Les deux sont surchargeables (`--board` / `--seed`) : un resultat
#: obtenu sur UN SEUL board n'est pas un resultat des que la mecanique touche a la geometrie
#: (discipline #95). Second couple mesure : `C2_02` / 777 -- 7x9 tout Grass, elevations 2/3/4, donc
#: un voisinage complet au centre ET un etage d'elevation actif dans le calcul de degat.
BOARD = "MC1_67"
SEED = 525
#: GEOMETRIE PAR BOARD. Un board n'est pas une formalite : `C2_02` porte `(6,8)` en `Block` et
#: `(0,8)` en `ForceUnplayable`, donc les tuiles de `MC1_67` y sont REFUSEES par
#: `AddUnitOperation$$Execute` (retour NUL silencieux -- `rl_duel` le detecte et rend rc 3).
#: Chaque board declare donc SES tuiles, verifiees jouables sur son dump. Les ROLES, eux, sont
#: identiques : caster / allie adjacent au caster / allie lointain / cible / N ennemis adjacents
#: a la cible / allie adjacent a la cible (R4).
GEOM = {
    # `MC1_67` : l'arene par defaut, 7x9.
    "MC1_67": {"caster": "5,5", "near": "5,4", "far": "1,1", "on_target": "6,8",
               "main": "5,8", "foes": ("6,8", "4,8", "4,7"), "foe_r4": "4,8"},
    # `C2_02` : 7x9 tout Grass, elevations 2/3/4 -> un ETAGE D'ELEVATION actif dans le calcul de
    # degat, que `MC1_67` n'exerce pas. `(6,8)` y est `Block` et `(0,8)` `ForceUnplayable`.
    "C2_02": {"caster": "5,4", "near": "5,3", "far": "1,1", "on_target": "6,7",
              "main": "5,7", "foes": ("6,7", "4,7", "5,8"), "foe_r4": "4,7"},
}


def _geom():
    g = GEOM.get(BOARD)
    if g is None:
        raise SystemExit("board %r sans geometrie declaree : ajoute son entree a GEOM (les tuiles "
                         "de MC1_67 ne sont PAS transposables -- Block/ForceUnplayable)" % BOARD)
    return g


def places(regime):
    """Roster JOUEUR place. R4 ajoute un ALLIE sur un hex ADJACENT A LA CIBLE : c'est le seul
    montage ou le filtre `Enemies(caster@0x48, ...)` du volet splash est OBSERVABLE. Sans lui,
    `AdjacentUnits(target)` NU et `Enemies(AdjacentUnits(target))` rendent le MEME ensemble, et un
    port qui aurait oublie le filtre passerait -- il frapperait son propre allie sans qu'on le voie."""
    g = _geom()
    base = ((CASTER, g["caster"]), (FRIEND_NEAR, g["near"]), (FRIEND_FAR, g["far"]))
    return base + (((FRIEND_ON_TARGET, g["on_target"]),) if regime == "R4" else ())


def a_places(regime):
    """Roster ADVERSE place.

    R1 -- geometrie ouverte : UN seul ennemi adjacent a la cible.
    R2 -- DEUX ennemis adjacents : le `multi` du 2e `AttackWithAttackDamage` est exerce, et les
          tuiles occupees sortent du pool d'atterrissage (E2 change de reponse par rapport a R1).
    R3 -- TROIS ennemis : la cible ne garde presque plus d'hex libre, la tuile d'atterrissage est
          contrainte et le splash porte sur trois unites.
    R4 -- l'allie occupe un hex adjacent a la cible, l'ennemi splash l'autre : `AdjacentUnits(target)`
          rend DEUX unites dont UNE amie, et seul le filtre `Enemies` fait la difference."""
    g = _geom()
    n = {"R1": 1, "R2": 2, "R3": 3}.get(regime)
    if n is not None:
        return ((FOE_MAIN, g["main"]),) + tuple(
            (v, t) for v, t in zip((FOE_A, FOE_B, FOE_D), g["foes"][:n]))
    return ((FOE_MAIN, g["main"]), (FOE_A, g["foe_r4"]))


# ------------------------------------------------------------------ transport

def _sid():
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["session"]["id"]


def _rpc(sid, method, body=None, timeout=180):
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

def seed_bc_augmente(path: str) -> str:
    """`votanChampion` est HORS CATALOGUE : le seed BC partage ne le porte pas.

    `catalog_inject.write_augmented_seed_bc` ecrit les DEUX blocs (`BC.Units` ET `BC.Abilities`) --
    injecter le premier seul donne un porteur qui se deploie, s'affiche, et FAUTE au cast
    (« system error » : config d'ability vide -> `AbilityConfiguration$$GetVariableForLevel` leve)."""
    sys.path.insert(0, PYDIR)
    import catalog_inject
    catalog_inject.write_augmented_seed_bc(path, [CASTER])
    return path


def build(state_file: str, seed_bc: str, regime: str):
    """Monte le runner du regime demande. Rend `runnerId`, ou `None` si le build echoue."""
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--seed-bc", seed_bc,
            "--crit", "0,0", "--crit-target", "0,0", "--hp-target", "400000",
            "--hp-player", "400000",
            "--p-units", ",".join(v for v, _t in places(regime)),
            "--a-units", ",".join(v for v, _t in a_places(regime)),
            "--state-file", state_file]
    for vid, tile in places(regime):
        argv += ["--place", "%s:%s" % (vid, tile)]
    for vid, tile in a_places(regime):
        argv += ["--a-place", "%s:%s" % (vid, tile)]
    p = _duel(argv)
    if p.returncode != 0:
        print("[build %s] rc=%s\n%s\n%s" % (regime, p.returncode, p.stdout[-1500:], p.stderr[-800:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def unites(sid, rid):
    """{visualId: {'id','pos','hp','alive','eff'}} -- aucun id d'entite en dur."""
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = {
            "id": u.get("id"), "pos": (p.get("col"), p.get("row")), "hp": u.get("hp"),
            "alive": not u.get("isDead"),
            "eff": sorted(int(e.get("type") or e.get("effectType") or 0)
                          for e in (u.get("effects") or []))}
    return out


def capture(sid, rid):
    """L'etat COMPLET juste avant le cast natif -- le substrat du rejeu porte."""
    return {
        "dv": _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}),
        "ob": _rpc(sid, "observeBattle", {"runnerId": rid}),
        "snap": _rpc(sid, "combatSnapshot", {"runnerId": rid}),
        "tm": _rpc(sid, "tileMeta", {"runnerId": rid}),
        "tiles": _rpc(sid, "boardGraph", {"runnerId": rid})["tiles"],
        "rng": _rpc(sid, "dumpRng", {"runnerId": rid}),
    }


def assert_montage(u, regime):
    """Un montage DEGENERE rendrait l'accord trivial : on echoue AVANT de mesurer, jamais apres."""
    voulu = dict(places(regime)) | dict(a_places(regime))
    manquants = [v for v in voulu if v not in u]
    if manquants:
        raise SystemExit("montage invalide : unites absentes %r" % (manquants,))
    mauvais = [(v, u[v]["pos"], voulu[v]) for v in voulu
               if u[v]["pos"] != tuple(int(x) for x in voulu[v].split(","))]
    if mauvais:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %r" % (mauvais,))
    sys.path.insert(0, PYDIR)
    import hexgeo
    # `TargetIsNotAdjacent` : une cible ADJACENTE serait refusee par le masque -> aucune mesure.
    d = hexgeo.distance(u[CASTER]["pos"], u[FOE_MAIN]["pos"])
    if d < 2:
        raise SystemExit("montage DEGENERE : cible ADJACENTE (d=%d), `TargetIsNotAdjacent` "
                         "refuserait le cast" % d)
    # E1 n'a de sens que si l'allie ADJACENT l'est vraiment ET que le LOINTAIN ne l'est pas :
    # sans ce contraste, un port qui buffe tout le camp et un port fidele rendraient la meme chose.
    if hexgeo.distance(u[CASTER]["pos"], u[FRIEND_NEAR]["pos"]) != 1:
        raise SystemExit("montage DEGENERE : l'allie 'adjacent' ne l'est PAS")
    if hexgeo.distance(u[CASTER]["pos"], u[FRIEND_FAR]["pos"]) <= 1:
        raise SystemExit("montage DEGENERE : l'allie 'lointain' est ADJACENT")
    # E4 : sans ennemi adjacent a la cible, le volet SPLASH est structurellement VIDE et l'accord
    # sur un ensemble vide ne prouve rien.
    voisins = [v for v, _t in a_places(regime) if v != FOE_MAIN
               and hexgeo.distance(u[v]["pos"], u[FOE_MAIN]["pos"]) == 1]
    if not voisins:
        raise SystemExit("montage DEGENERE : aucun ennemi adjacent a la cible -> splash VIDE")
    return voisins


# ------------------------------------------------------------------ rejeu hors-ligne

def etat_porte(cap):
    """`State` charge depuis la capture, PRNG cale sur `dumpRng`.

    Sans ce calage `execute_ability_attack` SKIPPE le degat par repli defensif : on lirait un faux
    `0` et l'accord ne prouverait rien."""
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


def _pos(st, uid):
    from engine.runner.components import PositionComponent
    e = st.get_entity(int(uid))
    p = e.get_component(PositionComponent) if e is not None else None
    return None if p is None else (p.col, p.row)


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
                                      ability_type=MASS_DRIVER_ACCELERATOR))
    last = getattr(runner.ability_handler, "last", None) or {}   # `diag` est SPREAD dans `last`
    apres = _hp(st, ids)
    atk = (last.get("attack") or {})
    splash = last.get("splash") or []
    return {
        "ported": last.get("ported"),
        "pos_apres": _pos(st, caster_id), "dest": last.get("dest"),
        "move_range": last.get("move_range"), "extra_movement": last.get("extra_movement"),
        "buffed": sorted(int(x) for x in (last.get("buffed") or [])),
        "delta": {i: (avant[i] - apres[i]) for i in avant
                  if avant[i] is not None and apres[i] is not None and avant[i] != apres[i]},
        "total_principal": atk.get("total"),
        "pierce_principal": ((atk.get("attack") or {}).get("pierce")),
        "splash": {int(s.get("target")): {"total": s.get("total"),
                                          "pierce": (s.get("attack") or {}).get("pierce"),
                                          "hits": (s.get("attack") or {}).get("hits")}
                   for s in splash},
        "effets_1542": sorted(int(i) for i in ids
                              if st.effects is not None
                              and st.effects.has_effect(int(i), effect_type=MDA_EXTRA_MOVEMENT)),
        "mt": (list(st.rng.mt), st.rng.mti),
    }


def gate_porte(cap, caster_id, ids):
    """Le GATE DE CIBLE porte : `TargetingQuery$$GetInvalidCasterReason` puis
    `$$GetInvalidTargetReason` avec les `TARGETING_OPTIONS` de la classe (= le masque
    `0x102004032` du preset `TargetingOptions statics+0x240`), plus la regle DYNAMIQUE
    `...MassDriverAcceleratorAbility$$GetDynamicInvalidTargetReason`.

    Rend l'ensemble des cibles pour lesquelles le port rend `0` -- a confronter au `fromHere` de
    `abilityTargets`, qui est l'ensemble que le NATIF accepte SANS deplacement prealable."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (get_invalid_caster_reason,
                                                   get_invalid_target_reason)
    st = etat_porte(cap)
    ability = ABILITY_CLASSES[MASS_DRIVER_ACCELERATOR]()
    if get_invalid_caster_reason(st, int(caster_id), ability) != 0:
        return set()
    return {int(i) for i in ids
            if int(i) != int(caster_id)
            and get_invalid_target_reason(st, int(caster_id), int(i), ability) == 0}


def tirages(rng_initial, mt_cible, mti_cible, cap=3000):
    """Nombre de `genrand_int32` consommes pour aller de l'etat INITIAL a l'etat CIBLE.

    C'est l'etage qui LOCALISE une divergence de sequence : deux moteurs qui rendent des montants
    differents mais consomment le MEME nombre de tirages ont un bug d'ARITHMETIQUE ; s'ils n'en
    consomment pas le meme nombre, c'est la STRUCTURE. Rend None si non atteint."""
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt, r.mti = list(rng_initial["mt"]), rng_initial["mti"]
    for n in range(cap + 1):
        if r.mti == mti_cible and r.mt == mt_cible:
            return n
        r.genrand_int32()
    return None


# ------------------------------------------------------------------ etage OFFLINE des registres

def etage_tables() -> bool:
    """Le CONTRAT du registre, RE-COMPTE par le code (jamais par soustraction)."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   TARGETING_OPTIONS_UNPORTED)
    ok = True
    print("[525:tables] ABILITY_CLASSES=%d  TARGETING_OPTIONS_UNPORTED=%d  "
          "DYNAMIC_TARGET_RULE_UNPORTED=%d"
          % (len(ABILITY_CLASSES), len(TARGETING_OPTIONS_UNPORTED),
             len(DYNAMIC_TARGET_RULE_UNPORTED)))
    inter = sorted(set(ABILITY_CLASSES) & set(TARGETING_OPTIONS_UNPORTED))
    if inter:
        print("  KO disjonction rompue (deux sources de masque) : %r" % (inter,))
        ok = False
    cls = ABILITY_CLASSES.get(MASS_DRIVER_ACCELERATOR)
    if cls is None:
        print("  KO 1222 ABSENTE d'ABILITY_CLASSES -- le no-op n'est pas leve")
        ok = False
    else:
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is None or int(opts.rules) != 0x102004032:
            print("  KO masque de 1222 : %r (attendu 0x102004032, preset statics+0x240)"
                  % (None if opts is None else hex(int(opts.rules)),))
            ok = False
        else:
            print("  OK masque 1222 = 0x%x (preset `TargetingOptions statics+0x240`)"
                  % int(opts.rules))
    at = ABILITY_ATTACK_TYPE.get(MASS_DRIVER_ACCELERATOR)
    if at != AbilityAttackType.DirectTargetAttack:
        print("  KO ABILITY_ATTACK_TYPE[1222]=%r (attendu DirectTargetAttack=0, 3e arg du ctor)"
              % (at,))
        ok = False
    else:
        print("  OK ABILITY_ATTACK_TYPE[1222] = DirectTargetAttack (3e argument du ctor)")
    if MASS_DRIVER_ACCELERATOR in DYNAMIC_TARGET_RULE_UNPORTED:
        print("  KO 1222 encore dans DYNAMIC_TARGET_RULE_UNPORTED alors que la classe SURCHARGE")
        ok = False
    # Les DEUX profils de degat de la config -- ils sont DIFFERENTS, et c'est ce qui rend le volet
    # splash observable (pierce 100 contre 1).
    import gameconfig as GC
    consts = (GC.ability("MassDriverAccelerator") or {}).get("constants") or {}
    p1, p2 = consts.get("damageProfile"), consts.get("damageProfile_2")
    if p1 == p2:
        print("  KO damageProfile == damageProfile_2 (%r) : le volet splash n'est plus "
              "discriminable par le profil sur ce build" % (p1,))
        ok = False
    else:
        print("  OK damageProfile=%s  damageProfile_2=%s (profils DISTINCTS)" % (p1, p2))
    print("[525:tables] %s" % ("OK" if ok else "KO"))
    return ok


# ------------------------------------------------------------------ contre-epreuves

def contre_epreuves(cap, caster_id, target_id):
    """Chaque variante ne change QU'UNE lecture du mirror. Si l'une rendait le MEME resultat que
    REF, la lecture correspondante ne serait pas mesuree par ce montage."""
    import engine.runner.abilities.votann as V
    from engine.dsl.base import Const
    from engine.entities.selectors.accessors import Owner, Target
    from engine.entities.selectors.tiles import Caster
    from engine.entities.selectors.units import (AdjacentFriends, AdjacentUnits, Enemies, Union,
                                                 _units_of)
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.utilities.tile import first_tile_by_utility
    from engine.utilities.utility_type import UtilityType

    st = etat_porte(cap)
    ents = entities_from_state(st, int(caster_id), int(target_id))
    board = st.board
    out = {}

    # --- volet BUFF : qui est cible ---------------------------------------------------------
    # `_units_of` NORMALISE l'operande : un noeud-role (`Owner()`) rend un DICT, pas une liste --
    # l'iterer nu rendrait ses CLES (meme piege que `Tiles`/`Sub`, cf. `selectors/units.py`).
    def _ids(sel):
        return sorted(int(u.get("id")) for u in (_units_of(sel, ents) or [])
                      if isinstance(u, dict) and u.get("id") is not None)

    out["REF buff owner + AdjacentFriends(owner)"] = _ids(V.mass_driver_buff_targets_selector())
    out["AB1 buff owner SEUL (collapse)"] = _ids(Owner())
    out["AB2 buff AdjacentFriends(TARGET) (mauvais ancrage)"] = _ids(
        Union(Owner(), AdjacentFriends(Target(), Const(1), reference=Target())))

    # --- volet SPLASH : quel ensemble --------------------------------------------------------
    out["REF splash Enemies(AdjacentUnits(target))"] = _ids(
        V.mass_driver_adjacent_attack_targets_selector())
    out["AB3 splash AdjacentUnits(target) NU (sans Enemies)"] = _ids(AdjacentUnits(Target(),
                                                                                   Const(1)))
    out["AB4 splash Enemies(AdjacentUnits(CASTER)) (mauvais ancrage)"] = _ids(
        Enemies(AdjacentUnits(Caster(), Const(1))))

    # --- volet TUILE : portee et utilite -----------------------------------------------------
    ref_range = V.mass_driver_move_range(st, int(caster_id))
    cands = V.mass_driver_possible_move_tiles_selector(ref_range).evaluate(ents)

    def _first(tiles, **kw):
        t = first_tile_by_utility(st, tiles, unit_id=int(caster_id), **kw)
        return None if t is None else tuple(board.coord(t))

    out["REF tuile MovementSuggestion(33)"] = _first(
        cands, utility_type=int(UtilityType.MovementSuggestion))
    out["AB5 tuile Tile(7)"] = _first(cands, utility_type=int(UtilityType.Tile))
    out["AB6 portee SANS la branche HasEffect (range+1)"] = sorted(
        tuple(board.coord(t)) for t in
        V.mass_driver_possible_move_tiles_selector(ref_range + 1).evaluate(ents))
    out["REF pool de tuiles (range=%d)" % ref_range] = sorted(
        tuple(board.coord(t)) for t in cands)
    return out


def verdict_ab(out: dict) -> bool:
    """Une contre-epreuve qui rend le MEME resultat que sa REF ne MESURE RIEN -- et c'est un
    resultat qu'il faut DIRE, pas taire. Chaque couple est donc explicitement classe
    DISCRIMINANT / NON DISCRIMINANT, avec la raison quand le montage ne l'exerce pas."""
    couples = [
        ("REF buff owner + AdjacentFriends(owner)", "AB1 buff owner SEUL (collapse)",
         "l'allie ADJACENT sort du buff"),
        ("REF buff owner + AdjacentFriends(owner)",
         "AB2 buff AdjacentFriends(TARGET) (mauvais ancrage)", "le buff part sur le camp ADVERSE"),
        ("REF splash Enemies(AdjacentUnits(target))",
         "AB3 splash AdjacentUnits(target) NU (sans Enemies)",
         "exige un ALLIE adjacent a la cible -- regime R4"),
        ("REF splash Enemies(AdjacentUnits(target))",
         "AB4 splash Enemies(AdjacentUnits(CASTER)) (mauvais ancrage)",
         "le splash change d'ancre"),
        ("REF tuile MovementSuggestion(33)", "AB5 tuile Tile(7)",
         "exige un pool ou les deux utilites departagent differemment"),
    ]
    # AB6 se compare au POOL, pas a la tuile : sa cle porte la portee mesuree.
    ref_pool = next((k for k in out if k.startswith("REF pool de tuiles")), None)
    if ref_pool is not None:
        couples.append((ref_pool, "AB6 portee SANS la branche HasEffect (range+1)",
                        "le pool est deja sature par CanAddUnit(AdjacentTiles(target)) -- "
                        "la branche est prouvee par move_range, pas par le pool"))
    print("\n  -- pouvoir DISCRIMINANT de chaque contre-epreuve sur CE montage --")
    for ref, ab, raison in couples:
        if out.get(ref) == out.get(ab):
            print("     NON DISCRIMINANT : %-52s (%s)" % (ab, raison))
        else:
            print("     discriminant     : %-52s %r != %r" % (ab, out.get(ab), out.get(ref)))
    return True


# ------------------------------------------------------------------ un regime

def joue(regime: str, seed_bc: str, keep: bool) -> bool:
    state_file = os.path.join(tempfile.gettempdir(), "probe525_%s_%d.json" % (regime, os.getpid()))
    sid = _sid()
    rid = build(state_file, seed_bc, regime)
    if rid is None:
        print("[%s] BUILD KO -- aucune mesure" % regime)
        return False
    try:
        u = unites(sid, rid)
        voisins = assert_montage(u, regime)
        caster_id, target_id = u[CASTER]["id"], u[FOE_MAIN]["id"]
        ids = [v["id"] for v in u.values()]
        cap = capture(sid, rid)

        # --- E6 : le GATE DE CIBLE, AVANT tout cast (l'etat doit etre vierge des deux cotes) ---
        at = _rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": int(caster_id),
                                          "abilityType": MASS_DRIVER_ACCELERATOR}, 120)
        # Schema : `units[*].abilities[*].fromHere[*] = {kind, targetId, visualId, pos}`.
        # `fromHere` = legalite EXACTE du cast IMMEDIAT (sans deplacement prealable) -- c'est
        # exactement ce que le gate porte evalue, `CasterHasNotMoved` etant dans le masque.
        nat_from_here = set()
        for un in (at.get("units") or []):
            for ab in (un.get("abilities") or []):
                if int(ab.get("abilityId") or 0) != MASS_DRIVER_ACCELERATOR:
                    continue
                for t in (ab.get("fromHere") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        nat_from_here.add(int(t["targetId"]))
        port_gate = gate_porte(cap, caster_id, ids)

        port = rejeu_porte(cap, caster_id, target_id, ids)

        # --- cast NATIF sur le MEME runner, depuis le MEME etat ------------------------------
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(caster_id), "targetId": int(target_id),
            "abilityType": MASS_DRIVER_ACCELERATOR}}, 300)
        rng2 = _rpc(sid, "dumpRng", {"runnerId": rid})
        u2 = unites(sid, rid)

        n_port = tirages(cap["rng"], port["mt"][0], port["mt"][1])
        n_nat = tirages(cap["rng"], list(rng2["mt"]), rng2["mti"])

        ok = True
        print("\n=== %s (%d ennemi(s) adjacent(s) a la cible : %s) ===" % (regime, len(voisins),
                                                                          ",".join(voisins)))
        # E0
        if port["ported"] is not True:
            print("  E0 KO ported=%r -- l'ability est encore un NO-OP" % (port["ported"],))
            ok = False
        else:
            print("  E0 OK ported=True")
        # E1 -- le buff 1542
        nat_buffed = sorted(v["id"] for v in u2.values() if MDA_EXTRA_MOVEMENT in v["eff"])
        if port["effets_1542"] != nat_buffed:
            print("  E1 KO buff 1542 : port=%r natif=%r" % (port["effets_1542"], nat_buffed))
            ok = False
        else:
            noms = [k for k, v in u2.items() if v["id"] in nat_buffed]
            print("  E1 OK buff 1542 sur %r (= %r)" % (nat_buffed, sorted(noms)))
        # E2 -- la tuile d'atterrissage
        nat_pos = u2[CASTER]["pos"]
        if tuple(port["pos_apres"]) != tuple(nat_pos):
            print("  E2 KO tuile : port=%r natif=%r (dest=%r, range=%r)"
                  % (port["pos_apres"], nat_pos, port["dest"], port["move_range"]))
            ok = False
        else:
            print("  E2 OK tuile d'atterrissage = %r (move_range=%r, extraMovement=%r)"
                  % (nat_pos, port["move_range"], port["extra_movement"]))
        # E3/E4 -- les degats, PAR CIBLE
        nat_delta = {v["id"]: (u[k]["hp"] - v["hp"]) for k, v in u2.items()
                     if u.get(k) and u[k]["hp"] is not None and v["hp"] is not None
                     and u[k]["hp"] != v["hp"]}
        if port["delta"] != nat_delta:
            print("  E3/E4 KO degats par cible : port=%r natif=%r" % (port["delta"], nat_delta))
            ok = False
        else:
            print("  E3 OK cible principale u%d : %s (pierce %s = damageProfile)"
                  % (target_id, port["total_principal"], port["pierce_principal"]))
            print("  E4 OK splash %r (pierce %s = damageProfile_2)"
                  % ({k: v["total"] for k, v in port["splash"].items()},
                     next((v["pierce"] for v in port["splash"].values()), None)))
            if len(port["splash"]) != len(voisins):
                print("  E4 KO le splash a frappe %d unite(s) pour %d ennemi(s) adjacent(s)"
                      % (len(port["splash"]), len(voisins)))
                ok = False
        # E4bis -- FRIENDLY FIRE : le volet splash est un `Enemies(caster@0x48, ...)`. En R4 un
        # ALLIE est pose adjacent a la cible ; s'il perd le moindre PV, le filtre est absent.
        # ⚠ Le test se fait sur le ROSTER du regime, PAS sur le `visualId` : `astraBullgryn` sert
        # d'allie en R4 et d'ENNEMI d'encerclement en R3 -- le frapper y est CORRECT, et un garde
        # qui ne regarde que le nom rougirait sur un port juste (mesure du 2026-08-07).
        if FRIEND_ON_TARGET in dict(places(regime)) and FRIEND_ON_TARGET in u:
            aid = u[FRIEND_ON_TARGET]["id"]
            if aid in port["splash"] or aid in nat_delta or aid in port["delta"]:
                print("  E4bis KO FRIENDLY FIRE : l'allie u%d adjacent a la cible a ete frappe "
                      "(port=%r natif=%r)" % (aid, port["delta"].get(aid), nat_delta.get(aid)))
                ok = False
            else:
                print("  E4bis OK aucun friendly fire : l'allie u%d adjacent a la cible est "
                      "INTACT des DEUX cotes (le filtre `Enemies` mord)" % aid)
        # E6 -- le GATE DE CIBLE (`TARGETING_OPTIONS` + regle dynamique) contre `abilityTargets`
        if not nat_from_here:
            print("  E6 NON MESURE : `abilityTargets` n'a rendu aucun `fromHere` pour 1222 "
                  "(schema du RPC ?) -- port=%r" % (sorted(port_gate),))
        elif port_gate != nat_from_here:
            print("  E6 KO gate : port=%r natif(fromHere)=%r"
                  % (sorted(port_gate), sorted(nat_from_here)))
            ok = False
        else:
            print("  E6 OK gate de cible = %r (masque 0x102004032 + regle dynamique)"
                  % sorted(nat_from_here))
        # E5 -- les tirages
        if n_port != n_nat:
            print("  E5 KO tirages : port=%r natif=%r (STRUCTURE)" % (n_port, n_nat))
            ok = False
        else:
            print("  E5 OK tirages genrand_int32 = %r (port == natif)" % (n_port,))
        print("[%s] %s" % (regime, "OK" if ok else "KO"))
        return ok
    finally:
        if not keep:
            _duel(["dispose", "--state-file", state_file])


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser(description="probe #525 -- MassDriverAccelerator (1222)")
    ap.add_argument("--regime", choices=("R1", "R2", "R3", "R4"), action="append")
    ap.add_argument("--tables", action="store_true", help="etage OFFLINE des registres, sans runner")
    ap.add_argument("--ab", action="store_true", help="+ contre-epreuves hors-ligne (regime R4)")
    ap.add_argument("--keep", action="store_true", help="ne dispose PAS les runners")
    ap.add_argument("--board", default=BOARD, help="board (defaut %s ; 2e couple mesure : C2_02)"
                                                   % BOARD)
    ap.add_argument("--seed", type=int, default=SEED, help="seed (defaut %d)" % SEED)
    a = ap.parse_args()
    sys.path.insert(0, PYDIR)
    globals()["BOARD"], globals()["SEED"] = a.board, a.seed

    if a.tables:
        return 0 if etage_tables() else 1

    ok = etage_tables()
    seed_bc = seed_bc_augmente(os.path.join(tempfile.gettempdir(),
                                            "probe525_seedbc_%d.json" % os.getpid()))
    regimes = a.regime or ["R1", "R2", "R3", "R4"]
    for r in regimes:
        ok = joue(r, seed_bc, a.keep) and ok

    if a.ab:
        # Les contre-epreuves tournent sur **R4** : c'est le seul montage ou un ALLIE est adjacent
        # a la cible, donc le seul ou AB3 (splash sans le filtre `Enemies`) peut diverger.
        state_file = os.path.join(tempfile.gettempdir(), "probe525_ab_%d.json" % os.getpid())
        sid = _sid()
        rid = build(state_file, seed_bc, "R4")
        if rid is not None:
            try:
                u = unites(sid, rid)
                cap = capture(sid, rid)
                print("\n=== contre-epreuves hors-ligne (R4) ===")
                out = contre_epreuves(cap, u[CASTER]["id"], u[FOE_MAIN]["id"])
                for k, v in out.items():
                    print("  %-52s %r" % (k, v))
                print("  (ids : %s)" % {k: v["id"] for k, v in u.items()})
                verdict_ab(out)
            finally:
                if not a.keep:
                    _duel(["dispose", "--state-file", state_file])
    print("\n[525] %s" % ("OK" if ok else "KO"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
