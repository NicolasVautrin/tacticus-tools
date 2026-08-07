#!/usr/bin/env python
"""probe #512 -- `ExcruciatingFrequencies` (1197, `emperNoiseMarine` « Shiron ») vs le natif.

CE QUI EST MESURE
-----------------
Avant #512 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc le cast
partait, l'`AbilityHandler` rendait `ported=False` et RIEN ne se passait -- 0 degat, 0 effet,
AUCUNE erreur. Le probe monte trois regimes, prend une capture complete
(`decisionView`/`observeBattle`/`combatSnapshot`/`tileMeta`/`boardGraph` + `dumpRng`), rejoue le
cast HORS LIGNE par le CHEMIN COMPLET du moteur (`Runner.apply`), lance le cast NATIF sur le MEME
runner, et confronte QUATRE etages -- jamais un scalaire :

  E0  `ported`         -- l'observable qui distingue le port du no-op ;
  E1  LA CRIT CHANCE POSEE -- et c'est le coeur du cas. Le natif la PUBLIE :

          [Effect_Refresh e=106 «TemporaryStatModifier»]
            ChangeStats e=77  UnitStats_Modification_Hidden=1
                              UnitStats_CritChance_Modification=90
                              UnitStats_CritChance_Modification_Change=90

      `90 = 3 unites sur la ligne x extraCritChance(niveau 50) = 30`. C'est une mesure
      **DETERMINISTE** du `Multiply(Count(Cache(Units(GetAffectedTiles))), Direct(extraCritChance))`
      -- pas un effet de bord d'un tirage. Le couple R1/R2 la rend DISCRIMINANTE : les deux regimes
      ont EXACTEMENT les memes ennemis aux memes tuiles, et ne different QUE par la position d'un
      ALLIE (sur la ligne / loin). Un port qui compterait les ENNEMIS au lieu des UNITES rendrait
      la MEME valeur aux deux -- le natif, lui, rend 90 puis 60.
  E2  LA SEQUENCE coup par coup -- les `UnitDamaged` natifs (`Active_Ability_Type=1197`) confrontes
      aux `per_hit_health` du port, avec `Attack_DidCrit`. L'ALLIE de la ligne ne doit recevoir
      AUCUN coup (le `Count` porte sur toutes les unites, l'ATTAQUE sur les seuls ennemis : ce sont
      DEUX selecteurs distincts batis sur le meme `GetAffectedTiles`) ;
  E3  les TIRAGES `genrand_int32` consommes, PORT vs NATIF (`dumpRng` avant/apres). C'est l'etage
      qui LOCALISE une divergence : meme compte + montants differents = arithmetique ; comptes
      differents = STRUCTURE.

MONTAGE (board `MC1_67`) -- les positions sont DRIVEES, jamais subies
---------------------------------------------------------------------
La geometrie du rayon est DERIVEE (`battle_query.get_tiles_behind`, le foyer partage), jamais
supposee : sur un board hex la ligne CUBE n'est pas la ligne « row constante ». Le couple retenu est
`P=(4,5)`, `aim=(4,6)` -> ligne `[(4,6), (4,7), (4,8)]`, trois tuiles d'elevation 1 (le gate
`|Delta elev| < 2` de `TileUtil$$IsTileValidForList` ne tronque donc rien).

    emperNoiseMarine (4,5)  le caster (HERO, DANS le pool `--list-pool` rank 17)
    necroWarden      (4,6)  ennemi -- 1re tuile du rayon (= la tuile VISEE)
    ultraTitus       (4,7)  ALLIE   -- 2e tuile : il COMPTE pour le crit, il n'est PAS frappe
    orksNob          (4,8)  ennemi -- 3e tuile
    tauMarksman      (5,6)  ennemi HORS ligne -- temoin : il ne doit ni compter ni etre frappe

    `--crit 0,700` : la crit chance de BASE du caster est mise a ZERO, donc la seule source de crit
    est le buff de l'ability -- c'est ce qui rend `CritChance_Modification_Change` lisible tel quel.
    (Le trait `ThrillSeekers` d'`emperNoiseMarine` ajoute ENSUITE +15 sur `On(PreAttackHit)` ; c'est
    un AUTRE effet, `EffectType.ThrillSeekers` = 1434, et il est deja porte.)

REGIMES
-------
    R0 `isole`    MEME montage que R1, mais le caster est PRIVE de son passif
       (`--unit-stat emperNoiseMarine:PassiveAbilities=[]`). C'est le regime ou le DEGAT doit etre
       **BIT-EXACT** : il isole l'`ExecuteBehaviour` de la chaine de declencheurs du porteur.
    R1 `mixte`    l'allie est SUR la ligne  -> 3 unites comptees, 2 attaquees.
    R2 `ennemis`  l'allie est LOIN (0,3)    -> 2 unites comptees, 2 attaquees. MEMES ennemis, MEMES
       tuiles, MEME seed que R1 : le seul delta est le compte. C'est LE couple discriminant.
    R3 `borne`    caster en (4,8) visant (4,7) -> ligne `[(4,7), (4,6), (4,5)]`, et un ennemi pose
       sur la 4e tuile `(4,4)` : `nrOfTiles = 3` doit l'exclure du compte ET des cibles. Sans la
       borne, le rayon irait jusqu'au bord du plateau.

LA CHAINE DE DECLENCHEURS DU PORTEUR -- `#512-r1`, MESUREE PUIS FERMEE
----------------------------------------------------------------------
Avant `#512-r1` le port SOUS-TIRAIT en regime NOMINAL (R1/R2/R3), a **SEQUENCE, CIBLES, CRITS ET
NOMBRE DE TIRAGES IDENTIQUES** (6 = 6) : `u81` 9575 contre 10073, `u83` 7101 contre 7766. L'ecart
n'etait PAS dans le mirror d'`ExecuteBehaviour` -- R0 (le MEME montage, passif retire) rendait deja
9575 / 7101 des DEUX cotes, bit pour bit. C'est cette attribution qui a designe la chaine :

    natif : SuppressiveFire (TRAIT du caster) pose `Pinned` sur CHAQUE cible du rayon
            -> `On(PreEffectAdded = 0x3d)` -> `TerrifyingCrescendo` (passif) monte
               `TerrifyingCrescendo_ExtraDmg` (0x590) d'un niveau
            -> ce niveau ajoute son `extraDmg` au coup EN COURS.
    port  : `SuppressiveFireAddEffectAbility` ecoutait `On(NormalAttack = 38)`, donc RIEN n'etait
            pose sur une attaque d'ABILITY -> le crescendo ne montait jamais.

⚠ **L'argument qui justifiait l'abstention dans `suppressive_fire.py` etait FAUX**, et c'est la
lecture du decompile qui le montre : `On(PreAttack = 5)` n'est PAS emis « une fois par attaque, sur
la cible primaire ». `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` pousse
`processor.StartAttack` (slot 58) a chaque CHANGEMENT de cible, et
`IdunBattle.Operations.StartAttackOperation$$Execute` y emet
`EvaluateAbilitiesImmediately(EventTriggerType.PreAttack = 5, ...)` -- donc **une fois par cible
distincte**. Une feuille `IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage` NUE composee dans le
`Attack(...)` d'une AUTRE attaque (`isOutsideAttack = false`, `#419-r3`) n'ouvre aucun
`StartAttack` et n'emet donc rien : la distinction est STRUCTURELLE, pas « primaire vs toutes ».

Depuis `#512-r1`, `DEGAT_EXACT` vaut **True dans les quatre regimes** : R0 (la contre-epreuve
d'isolation, qui doit rester bit-exacte -- c'est elle qui garde le mirror d'`ExecuteBehaviour`
contre une regression de la chaine) ET R1/R2/R3 (le regime nominal, ou la chaine complete joue).
Le fix a trois volets, tous mesures ici : le VECTEUR (`On(5)` au lieu d'`On(38)`), le GATE
(`BattleQuery$$IsRangedAttack` slot 3 COMPLET -- 1197 est `attackRangeType = Ranged`, donc ranged
SANS lire la position, alors que sa 1re cible est ADJACENTE au caster), et la PLACE (l'event remonte
AVANT `attacker_modifiers`, sinon le niveau monte reste invisible du coup en cours).

CONTRE-EPREUVES (`--ab`, hors ligne, sur la MEME capture)
----------------------------------------------------------
Chaque variante ne change QU'UNE lecture. Si l'une rendait le MEME resultat que REF, la lecture
correspondante ne serait pas mesuree par ce montage -- et le vert de REF ne prouverait rien.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_512_excruciating_frequencies.py            # les trois regimes
    python probe_512_excruciating_frequencies.py --regime R1
    python probe_512_excruciating_frequencies.py --tables   # etage OFFLINE des registres (sans runner)
    python probe_512_excruciating_frequencies.py --ab       # + les contre-epreuves hors-ligne
    python probe_512_excruciating_frequencies.py --keep     # ne dispose PAS les runners
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

EXCRUCIATING_FREQUENCIES = 1197            # `ActiveAbilityType.ExcruciatingFrequencies`
TEMPORARY_STAT_MODIFIER = 0x56c            # `EffectType.TemporaryStatModifier` = 1388

CASTER = "emperNoiseMarine"                # « Shiron », seul porteur LINEUP de 1197
ALLY = "ultraTitus"                        # l'ALLIE dont la position fait tout le couple R1/R2
FOE_A = "necroWarden"                      # 1re tuile du rayon (= la tuile VISEE en R1/R2)
FOE_B = "orksNob"                          # 3e tuile du rayon
FOE_C = "tauMarksman"                      # temoin HORS rayon (R1/R2) / 4e tuile (R3)

BOARD = "MC1_67"
SEED = 512

#: (position du caster, position de la tuile VISEE) par regime -- DERIVEES du board (cf. l'en-tete),
#: et RE-VERIFIEES a l'execution par `assert_montage` (la ligne native est recalculee, jamais crue).
GEO = {"R0": ((4, 5), (4, 6)), "R1": ((4, 5), (4, 6)), "R2": ((4, 5), (4, 6)),
       "R3": ((4, 8), (4, 7))}
PLACES = {
    "R0": ((CASTER, "4,5"), (ALLY, "4,7")),
    "R1": ((CASTER, "4,5"), (ALLY, "4,7")),
    "R2": ((CASTER, "4,5"), (ALLY, "0,3")),
    "R3": ((CASTER, "4,8"), (ALLY, "0,3")),
}
A_PLACES = {
    "R0": ((FOE_A, "4,6"), (FOE_B, "4,8"), (FOE_C, "5,6")),
    "R1": ((FOE_A, "4,6"), (FOE_B, "4,8"), (FOE_C, "5,6")),
    "R2": ((FOE_A, "4,6"), (FOE_B, "4,8"), (FOE_C, "5,6")),
    #: R3 -- `FOE_C` est sur la **4e** tuile de la ligne : `nrOfTiles = 3` doit l'exclure.
    "R3": ((FOE_A, "4,7"), (FOE_B, "4,5"), (FOE_C, "4,4")),
}
#: R0 SEUL prive le caster de son passif -- c'est ce qui isole l'`ExecuteBehaviour` de la chaine
#: `SuppressiveFire -> Pinned -> TerrifyingCrescendo_ExtraDmg` (residu `#512-r1`, cf. l'en-tete).
#: Le TRAIT `SuppressiveFire` est CONSERVE : ce n'est pas lui qui manque au port, c'est le VECTEUR
#: sur lequel il ecoute -- et le retrait du seul passif suffit a rendre le degat bit-exact, ce qui
#: EST la mesure d'attribution.
UNIT_STAT = {"R0": ('%s:PassiveAbilities=[]' % CASTER,)}
#: L'unite dont la presence SUR LA LIGNE change le compte (et donc la crit chance) entre R1 et R2.
SUR_LIGNE = {"R0": (FOE_A, ALLY, FOE_B), "R1": (FOE_A, ALLY, FOE_B),
             "R2": (FOE_A, FOE_B), "R3": (FOE_A, FOE_B)}
#: Le DEGAT est bit-exact dans les QUATRE regimes depuis `#512-r1` (avant, seul R0 l'etait -- le
#: nominal sous-tirait de la chaine `SuppressiveFire -> Pinned -> TerrifyingCrescendo`, cf. l'en-tete).
#: R0 reste la contre-epreuve d'ISOLATION : il garde le mirror d'`ExecuteBehaviour` seul, donc un
#: R0 rouge accuse le mirror et un R1 rouge a R0 vert accuse la chaine de declencheurs. Ne JAMAIS
#: rabattre l'une de ces entrees sur False pour faire passer une passe : c'est le cliquet du cas.
DEGAT_EXACT = {"R0": True, "R1": True, "R2": True, "R3": True}

#: `UnitDamaged` natif : on lit la SEQUENCE coup par coup (attaquant, cible, montant, crit).
RE_DMG = re.compile(
    r"UnitDamaged e=(\d+).*?Attack_DidCrit=(\d).*?Attacker_Id=(\d+) Target_Id=(\d+) "
    r"Amount=(-?\d+) DamageProfileType=(\d+) Active_Ability_Type=(\d+)")
#: `ChangeStats` du bloc `TemporaryStatModifier` -- LA mesure native de
#: `Multiply(Count(Units(GetAffectedTiles)), Direct(extraCritChance))`. `_Change` = la contribution
#: de CETTE entite-effet (`_Modification` est le TOTAL, qui inclurait un autre poseur).
RE_CRIT_MOD = re.compile(r"UnitStats_CritChance_Modification=(\d+) "
                         r"UnitStats_CritChance_Modification_Change=(\d+)")
RE_HIDDEN = re.compile(r"UnitStats_Modification_Hidden=(\d)")
#: `LoseEffect` du meme bloc -- le `RemoveEffect(caster@0x48, Nullable(0x56c))` final.
RE_LOSE = re.compile(r"LoseEffect e=(\d+)\s+Effect_Id=(\d+)")


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
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--crit", "0,700",
            "--hp-target", "400000",
            "--p-units", ",".join(v for v, _t in PLACES[regime]),
            "--a-units", ",".join(v for v, _t in A_PLACES[regime]),
            "--state-file", state_file]
    for vid, tile in PLACES[regime]:
        argv += ["--place", "%s:%s" % (vid, tile)]
    for vid, tile in A_PLACES[regime]:
        argv += ["--a-place", "%s:%s" % (vid, tile)]
    for spec in UNIT_STAT.get(regime, ()):
        argv += ["--unit-stat", spec]
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


def ligne_native(cap, regime, n=3):
    """La ligne du rayon, RE-DERIVEE du board CAPTURE par le foyer partage
    (`battle_query.get_tiles_behind` avec les settings `{check_walkable: 1, update_reference: 1}` de
    `GetAffectedTiles`). On ne SUPPOSE jamais la geometrie : sur un board hex la ligne CUBE n'est pas
    la ligne « row constante », et un montage pose a l'oeil rendrait des bras vrais par VACUITE."""
    import engine.battle_query as bq
    elev, walk = {}, {}
    for t in cap["tiles"]:
        elev[(t["col"], t["row"])] = t.get("elevation", 0)
        walk[(t["col"], t["row"])] = bool(t.get("walkable", True))
    P, aim = GEO[regime]
    return bq.get_tiles_behind(P, aim, max_count=n, check_walkable=True, update_reference=True,
                               walkable_at=lambda q: walk.get(q, False),
                               elevation_at=lambda q: elev.get(q, 0),
                               tile_exists=lambda q: q in elev)


def assert_montage(u, cap, regime):
    """Un montage DEGENERE rendrait l'accord trivial : on echoue AVANT de mesurer, jamais apres."""
    attendus = set(v for v, _t in PLACES[regime]) | set(v for v, _t in A_PLACES[regime])
    manquants = [v for v in attendus if v not in u]
    if manquants:
        raise SystemExit("montage invalide : unites absentes %r" % (manquants,))
    voulu = dict(PLACES[regime]) | dict(A_PLACES[regime])
    mauvais = [(v, u[v]["pos"], voulu[v]) for v in voulu
               if u[v]["pos"] != tuple(int(x) for x in voulu[v].split(","))]
    if mauvais:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %r" % (mauvais,))
    L = ligne_native(cap, regime)
    if len(L) != 3:
        raise SystemExit("ligne DEGENEREE (%d tuiles au lieu de 3) : le gate d'elevation ou le "
                         "bord du plateau la tronque -- aucun bras ne serait exerce" % len(L))
    poses = {u[v]["pos"] for v in SUR_LIGNE[regime]}
    if not poses <= set(L):
        raise SystemExit("les unites annoncees SUR LA LIGNE n'y sont pas toutes : posees=%r "
                         "ligne=%r" % (sorted(poses), L))
    # ... et rien d'AUTRE ne doit s'y trouver : un occupant oublie fausserait le `Count` sans que
    # rien ne le dise (le compte est justement ce que ce probe mesure).
    intrus = [v for v in u if v not in SUR_LIGNE[regime] and u[v]["pos"] in set(L)]
    if intrus:
        raise SystemExit("unites NON DECLAREES sur la ligne (le `Count` serait fausse) : %r"
                         % (intrus,))
    # Le couple R1/R2 n'est DISCRIMINANT que si l'allie est SUR la ligne en R1 et HORS en R2.
    if regime in ("R0", "R1") and u[ALLY]["pos"] not in set(L):
        raise SystemExit("%s : l'ALLIE n'est PAS sur la ligne -- le couple R1/R2 ne mesure rien"
                         % regime)
    if regime == "R2" and u[ALLY]["pos"] in set(L):
        raise SystemExit("R2 : l'ALLIE est sur la ligne -- R1 et R2 seraient le MEME regime")
    # R3 -- la 4e tuile DOIT exister et porter le temoin, sinon la borne `nrOfTiles` n'est pas
    # exercee (le rayon s'arreterait tout seul, et le vert serait vrai par vacuite).
    if regime == "R3":
        L4 = ligne_native(cap, regime, n=4)
        if len(L4) != 4:
            raise SystemExit("R3 : pas de 4e tuile -- la borne `nrOfTiles` n'est PAS exercee")
        if u[FOE_C]["pos"] != L4[3]:
            raise SystemExit("R3 : le temoin n'est pas sur la 4e tuile (%r vs %r)"
                             % (u[FOE_C]["pos"], L4[3]))


# ------------------------------------------------------------------ rejeu hors-ligne

def etat_porte(cap):
    """`State` charge depuis la capture, PRNG cale sur `dumpRng`.

    ⚠ Sans ce calage `execute_ability_attack` SKIPPE le degat par repli defensif : on lirait un
    faux `0` et l'accord ne prouverait rien.

    ⚠ **Appeler sous `snapshot.live_rpc(...)`** (cf. `mesure`), sinon `_auto_ability_states` rend
    `no-transport` et TOUS les canaux mesures restent `None` -- dont `UnitContext.passive_abilities`.
    `collect_triggered_abilities` retombe alors sur le kit GAMECONFIG, et le regime R0
    (`--unit-stat <caster>:PassiveAbilities=[]`) ne retire RIEN cote port : le porteur y garde
    `TerrifyingCrescendo` que le BC ne porte plus. C'etait invisible tant que le port ne posait
    aucun `Pinned` (le crescendo restait a 0 des deux cotes, donc R0 passait par COINCIDENCE) ;
    des que `#512-r1` a cable le vecteur, R0 est devenu ROUGE -- et c'etait le MONTAGE, pas le port.
    Meme gisement que le residu `#521-r5`."""
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


def rejeu_porte(cap, caster_id, tile_id, ids):
    """Rejoue le cast par le CHEMIN COMPLET du moteur (`Runner.apply(ActiveAbilityMessage)`), pas
    par un appel direct a `execute_behaviour` : c'est ce qui exerce le registre `ABILITY_CLASSES` et
    rend `ability_handler.last['ported']` -- l'observable qui distingue le port du NO-OP."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    st = etat_porte(cap)
    avant = _hp(st, ids)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_id), target_id=int(tile_id),
                                      ability_type=EXCRUCIATING_FREQUENCIES))
    last = getattr(runner.ability_handler, "last", None) or {}   # `diag` est SPREAD dans `last`
    apres = _hp(st, ids)
    seq = []
    for a in (last.get("attacks") or []):
        t = a.get("target")
        atk = a.get("attack") or {}
        for m in (atk.get("per_hit_health") or []):
            seq.append((int(t), int(m), bool((atk.get("crits") or [False])[0])
                        if atk.get("crits") else None))
    return {
        "ported": last.get("ported"),
        "crit_chance": last.get("crit_chance"),
        "extra_crit_chance": last.get("extra_crit_chance"),
        "units_on_line": last.get("units_on_line"),
        "tiles": last.get("tiles"),
        "nr_of_tiles": last.get("nr_of_tiles"),
        "delta": {i: (avant[i] - apres[i]) for i in avant
                  if avant[i] is not None and apres[i] is not None and avant[i] != apres[i]},
        "seq": [(t, m) for t, m, _c in seq],
        "crits": [c for _t, _m, c in seq],
        "mt": (list(st.rng.mt), st.rng.mti),
    }


def tirages(rng_initial, mt_cible, mti_cible, cap=1200):
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
    """Le CONTRAT DE DISJONCTION, RE-COMPTE par le code (jamais par soustraction) -- c'est ce que
    demande le paragraphe « CE COMPTE SE RE-COMPTE » de `runner/abilities/targeting.py`."""
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.base import ActiveAbility
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   TARGETING_OPTIONS_UNPORTED)
    ok = True
    print("[512:tables] ABILITY_CLASSES=%d  TARGETING_OPTIONS_UNPORTED=%d  "
          "DYNAMIC_TARGET_RULE_UNPORTED=%d"
          % (len(ABILITY_CLASSES), len(TARGETING_OPTIONS_UNPORTED),
             len(DYNAMIC_TARGET_RULE_UNPORTED)))
    inter = sorted(set(ABILITY_CLASSES) & set(TARGETING_OPTIONS_UNPORTED))
    if inter:
        print("  KO disjonction rompue (deux sources de masque) : %r" % (inter,))
        ok = False
    cls = ABILITY_CLASSES.get(EXCRUCIATING_FREQUENCIES)
    if cls is None:
        print("  KO 1197 ABSENTE d'ABILITY_CLASSES -- le no-op n'est pas leve")
        ok = False
    else:
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is None or int(opts.rules) != 0x20000000042:
            print("  KO masque de 1197 : %r (attendu 0x20000000042, FLAGS DIRECTS du ctor)"
                  % (None if opts is None else hex(int(opts.rules)),))
            ok = False
        else:
            print("  OK masque 1197 = 0x%x (bit 41 `AllowUntargetableTarget` inclus -- masque 64 "
                  "bits)" % int(opts.rules))
        if cls.get_dynamic_invalid_target_reason is ActiveAbility.get_dynamic_invalid_target_reason:
            print("  KO la classe ne SURCHARGE pas `get_dynamic_invalid_target_reason` : le bit "
                  "`TargetMatchesDynamicRule` du masque serait DESARME")
            ok = False
    at = ABILITY_ATTACK_TYPE.get(EXCRUCIATING_FREQUENCIES)
    if at != AbilityAttackType.Others:
        print("  KO ABILITY_ATTACK_TYPE[1197]=%r (attendu Others=2, 3e arg d'AActiveAbility..ctor)"
              % (at,))
        ok = False
    else:
        print("  OK ABILITY_ATTACK_TYPE[1197] = Others (3e argument du ctor, TRANSCRIT)")
    if ActiveAbilityType.ExcruciatingFrequencies in DYNAMIC_TARGET_RULE_UNPORTED:
        print("  KO 1197 encore dans DYNAMIC_TARGET_RULE_UNPORTED alors que la classe SURCHARGE")
        ok = False
    print("[512:tables] %s" % ("OK" if ok else "KO"))
    return ok


# ------------------------------------------------------------------ contre-epreuves

def contre_epreuves(cap, caster_id, tile_id, regime):
    """Chaque variante ne change QU'UNE lecture du mirror, sur la MEME capture. Si l'une rendait le
    MEME resultat que REF, la lecture correspondante ne serait pas mesuree par ce montage."""
    from engine.dsl.base import Const
    from engine.dsl.effects import ExecutionContext
    from engine.entities.behaviours import op_and
    from engine.entities.formulas import Count, Multiply
    from engine.entities.selectors.geometry import Cache
    from engine.entities.selectors.tiles import Caster
    from engine.entities.selectors.units import Enemies, Units
    import engine.runner.abilities.emperorschildren as EC
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.abilities.behaviours.effects import (AddStaticStatModifierEffect,
                                                            RemoveEffect)
    from engine.runner.abilities.targeting import excruciating_frequencies_affected_tiles

    def _joue(arbre_fn):
        st = etat_porte(cap)
        n = EC.excruciating_frequencies_nr_of_tiles()
        crit = EC.excruciating_frequencies_extra_crit_chance(st, int(caster_id))
        ents = entities_from_state(st, int(caster_id), int(tile_id))
        ectx = ExecutionContext(state=st, rng=st.rng)
        arbre_fn(n, crit).execute(ents, ectx)
        pose = next((p for nm, p in ectx.emitted if nm == "AddStaticStatModifierEffect"), None)
        cibles = sorted(p.get("target") for nm, p in ectx.emitted
                        if nm == "AttackWithAttackDamage")
        return {"crit": (pose or {}).get("amount"), "cibles": cibles}

    def ab1(n, crit):
        """AB1 -- le `Count` sur les ENNEMIS au lieu de TOUTES les unites de la ligne."""
        ennemis = Cache(Enemies(Units(excruciating_frequencies_affected_tiles(n))))
        stat = AddStaticStatModifierEffect(
            Caster(), EC.EF_TEMPORARY_STAT_MODIFIER, EC.EF_CRIT_CHANCE,
            Multiply(Count(ennemis), Const(int(crit))), duration_turns=1)
        atk = AttackWithAttackDamage(ennemis, EC.EXCRUCIATING_FREQUENCIES_ID, "Blast",
                                     is_melee=False, multi=True)
        return op_and(op_and(stat, atk), RemoveEffect(EC.EF_TEMPORARY_STAT_MODIFIER, Caster()))

    def ab2(n, crit):
        """AB2 -- AUCUN buff de crit (le `AddStaticStatModifierEffect` retire de l'arbre)."""
        ennemis = Cache(Enemies(Units(excruciating_frequencies_affected_tiles(n))))
        return AttackWithAttackDamage(ennemis, EC.EXCRUCIATING_FREQUENCIES_ID, "Blast",
                                      is_melee=False, multi=True)

    def ab3(n, crit):
        """AB3 -- l'attaque sur TOUTES les unites de la ligne (le filtre `Enemies` retire)."""
        tous = Cache(Units(excruciating_frequencies_affected_tiles(n)))
        stat = AddStaticStatModifierEffect(
            Caster(), EC.EF_TEMPORARY_STAT_MODIFIER, EC.EF_CRIT_CHANCE,
            Multiply(Count(tous), Const(int(crit))), duration_turns=1)
        atk = AttackWithAttackDamage(tous, EC.EXCRUCIATING_FREQUENCIES_ID, "Blast",
                                     is_melee=False, multi=True)
        return op_and(op_and(stat, atk), RemoveEffect(EC.EF_TEMPORARY_STAT_MODIFIER, Caster()))

    def ab4(n, crit):
        """AB4 -- la borne `nrOfTiles` DESARMEE (rayon jusqu'au bord du plateau)."""
        return EC.excruciating_frequencies_tree(n + 3, crit)

    out = {"REF": _joue(EC.excruciating_frequencies_tree)}
    for nom, fn in (("AB1 Count(Enemies) au lieu de Count(Units)", ab1),
                    ("AB2 aucun buff de crit", ab2),
                    ("AB3 attaque TOUTES les unites", ab3),
                    ("AB4 borne nrOfTiles desarmee", ab4)):
        out[nom] = _joue(fn)
    return out


# ------------------------------------------------------------------ mesure

def mesure(sid, state_file, regime, avec_ab=False, garder=False):
    rid = build(state_file, regime)
    if rid is None:
        return None
    try:
        u = unites(sid, rid)
        cap = capture(sid, rid)
        assert_montage(u, cap, regime)
        noms = list(dict(PLACES[regime])) + list(dict(A_PLACES[regime]))
        ids = [u[v]["id"] for v in noms]
        cid = u[CASTER]["id"]
        bypos = {(t["col"], t["row"]): t["id"] for t in cap["tiles"]}
        tile_id = bypos[GEO[regime][1]]
        # TRANSPORT RPC LIE pour tout le rejeu hors-ligne : sans lui les canaux MESURES
        # (`unitAbilityStates` -> `passive_abilities`, `config_active_abilities`, ...) restent `None`
        # et le port retombe sur le kit gameconfig -- ce qui DESARME `--unit-stat PassiveAbilities=[]`
        # du regime R0 (cf. `etat_porte`). Le canal est un cache par runner, donc les deux rejeux
        # (REF et contre-epreuves) lisent le MEME etat.
        from engine.runner.snapshot import live_rpc
        with live_rpc(lambda method, body=None, timeout=120: _rpc(sid, method, body, timeout)):
            port = rejeu_porte(cap, cid, tile_id, ids)
            ab = contre_epreuves(cap, cid, tile_id, regime) if avec_ab else None
        p = _duel(["act", "ability", "--caster", str(cid),
                   "--ability", str(EXCRUCIATING_FREQUENCIES), "--target", str(tile_id),
                   "--state-file", state_file, "--runner", str(rid)])
        apres = unites(sid, rid)
        out = p.stdout or ""
        dmg = [(int(at), int(t), int(a), int(cr))
               for _e, cr, at, t, a, _pr, aid in RE_DMG.findall(out)
               if int(aid) == EXCRUCIATING_FREQUENCIES]
        mods = RE_CRIT_MOD.findall(out)
        natif = {
            "delta": {u[v]["id"]: u[v]["hp"] - apres[v]["hp"] for v in u
                      if v in apres and u[v]["hp"] is not None and apres[v]["hp"] is not None
                      and u[v]["hp"] != apres[v]["hp"]},
            "seq": [(t, a) for at, t, a, _c in dmg if at == int(cid)],
            "crits": [bool(c) for at, _t, _a, c in dmg if at == int(cid)],
            # LA mesure native du montant du buff : la 1re `ChangeStats` du bloc
            # `TemporaryStatModifier` (le buff de l'ability), AVANT celle de `ThrillSeekers`.
            "crit_mod": int(mods[0][1]) if mods else None,
            "crit_mods_tous": [(int(a), int(b)) for a, b in mods],
            "hidden": RE_HIDDEN.findall(out)[:1],
            "lose": RE_LOSE.findall(out),
            "tronque": "(+" in out and "events)" in out,
            "rc": p.returncode, "out": out[-3500:] + (p.stderr or "")[-800:]}
        rng_apres = _rpc(sid, "dumpRng", {"runnerId": rid}, 60)
        natif["tirages"] = (tirages(cap["rng"], rng_apres.get("mt"), rng_apres.get("mti"))
                            if isinstance(rng_apres, dict) and rng_apres.get("mt") else None)
        port["tirages"] = tirages(cap["rng"], port["mt"][0], port["mt"][1])
        return {"regime": regime, "rid": rid, "caster": cid, "tuile": tile_id,
                "ligne": ligne_native(cap, regime),
                "ids": {v: u[v]["id"] for v in u},
                "hp_avant": {v: u[v]["hp"] for v in u},
                "pos_avant": {v: u[v]["pos"] for v in u},
                "port": port, "natif": natif, "ab": ab}
    finally:
        if not garder:
            _duel(["dispose", "--state-file", state_file, "--runner", str(rid)], timeout=120)


def _rapport(m) -> bool:
    ids = m["ids"]
    inv = {i: v for v, i in ids.items()}
    print("[512:%s] runner=%s caster=u%s tuile-visee=%s ligne=%s"
          % (m["regime"], m["rid"], m["caster"], m["tuile"], m["ligne"]))
    print("        unites : " + " ".join("%s=u%s@%s(hp%s)" % (v, ids[v], m["pos_avant"][v],
                                                              m["hp_avant"][v])
                                         for v in sorted(ids)))
    fmt = lambda d: {("%s/u%s" % (inv.get(i, "?"), i)): v for i, v in sorted(d.items())}
    p, n = m["port"], m["natif"]
    print("  E0 ported = %s   (False = le NO-OP n'est pas leve)" % (p["ported"],))
    print("  E1 CRIT CHANCE posee   PORT=%s  (=%s unites x %s)   NATIF=%s   (hidden=%s, tous=%s)"
          % (p["crit_chance"], len(p["units_on_line"] or []), p["extra_crit_chance"],
             n["crit_mod"], n["hidden"], n["crit_mods_tous"]))
    print("     unites SUR LA LIGNE (port) = %s   tuiles = %s (nrOfTiles=%s)"
          % ([("%s/u%s" % (inv.get(i, "?"), i)) for i in (p["units_on_line"] or [])],
             p["tiles"], p["nr_of_tiles"]))
    print("  E2 delta hp PORT =%s" % (fmt(p["delta"]),))
    print("             NATIF=%s" % (fmt(n["delta"]),))
    print("     SEQUENCE  PORT (%d coups) =%s crits=%s"
          % (len(p["seq"]), [("u%s" % t, a) for t, a in p["seq"]], p["crits"]))
    print("               NATIF(%d coups) =%s crits=%s (tronque=%s)"
          % (len(n["seq"]), [("u%s" % t, a) for t, a in n["seq"]], n["crits"], n["tronque"]))
    print("     RemoveEffect natif (LoseEffect) = %s" % (n["lose"],))
    print("  E3 TIRAGES genrand_int32 consommes : PORT=%s  NATIF=%s"
          % (p.get("tirages"), n.get("tirages")))
    if m["ab"]:
        print("  -- contre-epreuves (hors-ligne, meme capture) --")
        ref = m["ab"]["REF"]
        for nom, r in m["ab"].items():
            marque = "" if nom == "REF" else ("  <- INERTE (ne mesure rien)" if r == ref else "")
            print("     %-42s crit=%-5s cibles=%s%s" % (nom, r["crit"], r["cibles"], marque))
    exact = DEGAT_EXACT.get(m["regime"], True)
    base = (bool(p["ported"]) and p["crit_chance"] == n["crit_mod"]
            and [t for t, _a in p["seq"]] == [t for t, _a in n["seq"]]
            and p["crits"] == n["crits"] and p.get("tirages") == n.get("tirages")
            and len(n["seq"]) > 0)
    ok = base and (p["seq"] == n["seq"] if exact else True)
    if base and p["seq"] != n["seq"]:
        # Ecart de MONTANT a cibles/crits/tirages identiques = un etage d'ARITHMETIQUE, jamais une
        # divergence de structure. Sur ce cas, c'etait la chaine
        # `SuppressiveFire -> Pinned -> TerrifyingCrescendo` (`#512-r1`) : si ce message revient avec
        # R0 VERT, c'est elle qu'il faut regarder d'abord, pas le mirror d'`ExecuteBehaviour`.
        print("     ECART DE MONTANT %s, a cibles/crits/tirages IDENTIQUES (R0 vert => regarder la "
              "chaine de declencheurs du porteur, pas ExecuteBehaviour)"
              % ([nb - pb for (_t, pb), (_u, nb) in zip(p["seq"], n["seq"])],))
    if not ok:
        print("  -- sortie du cast NATIF (diagnostic) --")
        print(n.get("out", ""))
    print("[512:%s] %s" % (m["regime"],
                           ("ACCORD port/natif%s" % (" BIT-EXACT (degat compris)" if exact else
                                                     " sur E0+E1+E2(cibles/crits)+E3"))
                           if ok else "DESACCORD"))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="probe #512 -- ExcruciatingFrequencies (1197) vs natif")
    ap.add_argument("--regime", default="all", choices=("all", "R0", "R1", "R2", "R3"))
    ap.add_argument("--tables", action="store_true", help="etage OFFLINE des registres, sans runner")
    ap.add_argument("--ab", action="store_true", help="joue aussi les contre-epreuves")
    ap.add_argument("--keep", action="store_true", help="ne dispose PAS les runners")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    if a.tables:
        return 0 if etage_tables() else 1
    base = a.state_file or os.path.join(tempfile.gettempdir(), "p512_ef_%d" % os.getpid())
    sid = _sid()
    regimes = ("R0", "R1", "R2", "R3") if a.regime == "all" else (a.regime,)
    verdicts = [etage_tables()]
    mesures = []
    for reg in regimes:
        sf = "%s_%s.json" % (base[:-5] if base.endswith(".json") else base, reg)
        m = mesure(sid, sf, reg, avec_ab=a.ab, garder=a.keep)
        if m is None:
            print("[512:%s] build KO -- rien mesure" % reg)
            return 99
        mesures.append(m)
        verdicts.append(_rapport(m))
    # LE COUPLE DISCRIMINANT : R1 et R2 n'ont que la POSITION DE L'ALLIE de different. Si les deux
    # rendaient la MEME crit chance, ce montage ne mesurerait PAS le `Count(Units)` -- et son vert
    # ne prouverait rien sur la lecture centrale du cas.
    par_reg = {m["regime"]: m for m in mesures}
    if "R1" in par_reg and "R2" in par_reg:
        c1 = par_reg["R1"]["natif"]["crit_mod"]
        c2 = par_reg["R2"]["natif"]["crit_mod"]
        discrimine = c1 is not None and c2 is not None and c1 != c2
        print("[512] COUPLE R1/R2 (seul delta = la position de l'ALLIE) : natif %s vs %s -- %s"
              % (c1, c2, "DISCRIMINANT" if discrimine
                 else "INERTE : ce montage ne mesure PAS le Count(Units)"))
        verdicts.append(discrimine)
    return 0 if all(verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
