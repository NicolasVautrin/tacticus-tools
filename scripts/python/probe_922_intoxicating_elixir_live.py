#!/usr/bin/env python
"""probe #922 -- MESURE de la relique `IntoxicatingElixir` (`EffectType` 0x5b3 = 1459).

CRITERE BINAIRE, pose avant toute methode :

    « Le natif AJOUTE-t-il `extraCritDmg[niveau de RELIQUE] x min(<unites DEBUFFEES a portee 2 du
      porteur, PORTEUR COMPRIS>, 6) x (2 si le porteur est a <= healthPct % de vie, sinon 1)` au
      degat de CRIT que ce porteur INFLIGE, et le port fait-il pareil ? »

## L'ARTEFACT

`IdunBattle.Entities.Effects.Loki.IntoxicatingElixir_ExtraCritDmgEffect$$CreateCritDamageBonus`
= `ForAddition(get_OwnerIsCaster, GetCritAmount())`, ou

    GetCritAmount   = Multiply(Multiply(ConfigVar(0x42 = extraCritDmg), EffectLevel(Effect@+0x38)),
                               ConditionalAmount(HealthPctIsBelowOrEqual(Owner, Get(healthPct)),
                                                 Direct(2), Direct(1)))
    GetCalculateLevel / CreateActiveCondition partagent la MEME `$$GetLevelFormula` :
                      Min(Count(EntitiesWithAnyEffect(
                              SurroundingUnits(Tiles(Owner), range = 2, unique: 1,
                                               includeCenter: 1, selectionType: 3),
                              [Pinned, Stunned, Taunted_OnlySpecificTargets, ThrillSeekers])),
                          Get(nrOfUnits = 6))

Le bloc des quatre `EffectType` vient d'un `RuntimeHelpers.InitializeArray` (aucun immediat au
decompile) : il a ete LU dans `global-metadata.dat` -- l'UNIQUE fenetre de 4 int32 alignes du
fichier contenant a la fois 1065 et 1162 vaut `[1065, 1162, 27, 1434]`.

## LE MONTAGE, et pourquoi chaque piece y est

  * `emperKakophonist` est l'un des QUATRE porteurs autorises, il est AU POOL, et son arme est
    UNIQUE et MELEE (`weapons = [{hits: 3, DamageProfile: Eviscerate}]`) -- la salve est lisible
    coup par coup, sans arbitrage melee/distance. La relique est montee par `--equip-relic`
    (etat 2 de la gate relique, #237), seul moyen de MAITRISER le niveau.
  * Le DEBUFF est pose par le jeu lui-meme, jamais invente : `emperNoiseMarine` porte le trait
    `SuppressiveFire` (« An enemy hit by this unit's ranged attack becomes Suppressed »), donc son
    tir A DISTANCE pose `EffectType.Pinned` (1065) sur sa cible. C'est le premier des quatre
    membres du bloc.
  * Le SECOND membre exerce est `ThrillSeekers` (1434) : les cinq Emperor's Children portent le
    trait homonyme, et `ThrillSeekersAbility$$CreateTrigger` = `On(PreAttackHit=6) &
    IsFirstHitInSeries & get_OwnerIsCaster & NOT IsWounded(target)` les rend `Thrilled` des qu'ils
    frappent une cible a PLEINE VIE. C'est ce qui rend confrontables les DEUX quirks que le port
    ne partage avec aucun voisin de forme : le PORTEUR SE COMPTE LUI-MEME (`includeCenter = 1`) et
    un AMI compte aussi bien qu'un ennemi (AUCUN filtre d'equipe).
  * Le porteur est le **CASTER** (`get_OwnerIsCaster`), donc il est cote `p-units` et c'est LUI qui
    doit criter -> `--crit`, et non `--crit-target`.

## LES ETAGES, et pourquoi ils sont mesures SEPAREMENT

  E1 COMPTEUR -- `decisionView.effects[].level` publie le niveau STOCKE (`EffectComponent+0x68`),
     que `IdunBattle.Operations.RefreshEffectsOperation$$UpdateLevel` tient EGAL a
     `$$GetCalculateLevel`. C'est donc **le compteur natif LU DIRECTEMENT**, sans passer par le
     degat. Le flag `active` est le seLond observable : la `CreateActiveCondition` etant
     `AmountIsGreaterThanZero(<ce compteur>)`, il vaut `compteur > 0` -- contrairement a
     `KardiocoreGalvanus`, dont la condition est le `YesTrigger` CONSTANT.
     ⚠ MESURE : tant que l'effet est INACTIF, `level` reste a sa valeur d'initialisation (1) --
     `UpdateLevel` ne le rafraichit pas. Le `level` ne fait donc foi QUE lorsque `active` est vrai ;
     a `active == False` c'est `active` qui porte l'information (compteur nul).
  E2 DEGAT -- la salve du porteur, coup par coup, LIVE contre REJEU OFFLINE du meme etat.

## CE QUI N'EST PAS MESURE ICI, et pourquoi (residu #922-r1)

Un `On(PreAttackHit)` qui pose un des quatre debuffs PENDANT la salve fait varier le compteur d'un
coup a l'autre -- regime naturel du porteur, qui devient `Thrilled` apres son propre coup 0 quand
sa cible est a pleine vie. Le natif re-evalue `CalculateCriticalDamage` a CHAQUE coup (slot 0xb de
`IDamagePrediction`, appele DANS `AttackDamageOperation$$ExecuteHit`), le port ne le fait pas : il
ne relit apres l'event que la crit CHANCE (`crit_chance_after`), jamais la crit DAMAGE
(`crit_apres[1]` est calcule et JAMAIS consomme). Les bras de degat de ce probe evitent donc ce
regime en frappant une cible DEJA BLESSEE (`NOT IsWounded` faux -> `ThrillSeekers` ne mord pas), et
le bras `--thrilled` le MESURE explicitement au lieu de le supposer.

Usage :
    python probe_922_intoxicating_elixir_live.py --n 0,1,2
    python probe_922_intoxicating_elixir_live.py --n 1 --dist 3        # bras PORTEE
    python probe_922_intoxicating_elixir_live.py --n 1 --low-hp
    python probe_922_intoxicating_elixir_live.py --compteur            # E1 seul (self/ami)
    python probe_922_intoxicating_elixir_live.py --thrilled            # MESURE du residu

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

#: SORTIES du probe -> `logs/` (gitignore, meurt avec le worktree). `data/` est VERSIONNE (#349).
LOGS = PYDIR.parent.parent / "logs" / "runners"

CARRIER = "emperKakophonist"          # porteur AU POOL, arme UNIQUE melee 3 coups, trait ThrillSeekers
PINNER = "emperNoiseMarine"           # trait SuppressiveFire : son tir RANGED pose `Pinned`
FOE = "tauCrisis"                     # les cibles / victimes
EFFECT_NAME = "IntoxicatingElixir"    # cle EFFECT_CLASSES == nom decisionView
ABILITY_ID = "IntoxicatingElixir"     # TriggeredAbilityType 0x5b7 = 1463 (la CONFIG)
VAR_KEY = "extraCritDmg"              # AbilityVariableType 0x42 = 66
NORMAL_ATTACK = 69                    # `Loki_NormalAttack` -- l'id EXPOSE par `decisionView`
#: #922-r1 -- CANAL de la capture qui alimente `load_state` (`includeInactive`). Pose par `main`
#: depuis `--inactifs`. `False` = canal ACTIF-ONLY, le comportement historique de ce probe.
INACTIFS = False

#: les QUATRE `EffectType` du bloc, relus dans `global-metadata.dat` (jamais recopies a la main --
#: on les prend au module de port, qui les tient de l'enum).
def _debuff_ids():
    from engine.entities.effects.loki.intoxicating_elixir import DEBUFFS
    return tuple(int(e) for e in DEBUFFS)


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def config_du_gameconfig() -> dict:
    """`extraCritDmg` / `range` / `nrOfUnits` / `healthPct` RELUS du gameconfig, jamais en dur."""
    import gameconfig as GC
    a = GC.ability(ABILITY_ID) or {}
    arr = (a.get("variables") or {}).get(VAR_KEY)
    cst = a.get("constants") or {}
    if not arr:
        raise SystemExit("%s.variables.%s absent du gameconfig" % (ABILITY_ID, VAR_KEY))
    return {"paliers": [int(x) for x in arr],
            "range": int(cst["range"]), "nrOfUnits": int(cst["nrOfUnits"]),
            "healthPct": int(cst["healthPct"])}


def _garde_regime(level: int, cfg: dict) -> None:
    """GARDES DE REGIME, jouees AVANT tout montage.

    Pas de garde de SATURATION : le terme est ADDITIF et `CalculateCriticalDamage` fait
    `Math.Max(0, GetStat(10) + somme)` -- le clamp bas ne peut pas mordre (difference de fond avec
    les `ForSubtraction` de la meme famille).

      * niveau hors paliers -> `AbilityConfiguration$$TryGetVariableArrayForLevel` CLAMPE au
        dernier, donc le bras NIVEAU ne discriminerait plus rien ;
      * niveau == dernier palier -> le bras `PASSIF` ne peut PAS mordre (le repli clampe justement
        au dernier palier)."""
    p = cfg["paliers"]
    if not (1 <= level <= len(p)):
        raise SystemExit("niveau %d hors des %d paliers de %s : le clamp haut de "
                         "`AbilityConfiguration$$TryGetVariableArrayForLevel` rendrait le bras "
                         "NIVEAU non discriminant" % (level, len(p), ABILITY_ID))
    if level == len(p):
        print("   [note] niveau == dernier palier : le bras PASSIF ne peut pas mordre.")
    print("   %s.%s[%d] = %d  (paliers %s..%s) | range=%d nrOfUnits=%d healthPct=%d"
          % (ABILITY_ID, VAR_KEY, level, p[level - 1], p[0], p[-1],
             cfg["range"], cfg["nrOfUnits"], cfg["healthPct"]))


class MontageError(RuntimeError):
    """On REFUSE de rendre un verdict plutot que d'en fabriquer un depuis un montage muet."""


# ---------------------------------------------------------------- montage

def build(a, tag: str, level: int, extra=()) -> tuple:
    LOGS.mkdir(parents=True, exist_ok=True)
    sf = str(LOGS / ("_922_%s.json" % tag))
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            # DEUX tireurs : chacun n'a qu'UNE action par tour, donc `n = 2` en exige deux. Ils sont
            # repousses hors du disque apres leur tir (leur propre `Thrilled` compterait sinon).
            "--p-units", "%s,%s,%s" % (CARRIER, PINNER, PINNER),
            "--a-units", ",".join([FOE] * 3),
            "--equip-relic", "%s:%s:%d" % (CARRIER, ABILITY_ID, level),
            "--hp-target", "900000", "--hp-player", "900000",
            "--no-ai", "--crit", "100,%d" % a.crit_damage, "--block-target", "0,0"]
    if getattr(a, "low_hp", False):
        # PV du PORTEUR sous le seuil, PATCHES SUR LE BC NORMALISE (`--unit-stat`) : `--hp-player`
        # force `Health == RemainingHealth`, donc 100 %, et n'exercerait JAMAIS le facteur x2.
        # ⚠ CE MONTAGE VIT ICI ET NULLE PART AILLEURS : quand il etait dans `run_degat`, le
        # cliquet -- qui appelle `build` directement -- construisait un porteur A PLEINE VIE et
        # accusait le port d'un « regime non atteint » que le probe, lui, atteignait.
        argv += ["--unit-stat", "%s:Health=100000,RemainingHealth=%d"
                 % (CARRIER, 100000 * config_du_gameconfig()["healthPct"] // 100 - 1)]
    argv += list(extra)
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s] build KO : %s" % (tag, (p.stderr or p.stdout or "")[-900:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def _pos(u) -> tuple:
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


def _effet_natif(h, carrier_id: int):
    """`(active, level)` de l'effet sur le porteur, LUS sur `decisionView` (`includeInactive`), ou
    `None` si l'effet est ABSENT du canal (= la relique n'est PAS montee -> montage mort).

    ⚠ `level` ne fait foi QUE si `active` : `RefreshEffectsOperation$$UpdateLevel` ne rafraichit pas
    le niveau d'un effet inactif, qui reste a sa valeur d'initialisation (mesure : `1` a compteur
    nul). C'est `active` qui porte l'information dans ce regime."""
    dvi = h.rpc("decisionView", {"runnerId": h.rid, "maxRank": 1, "allAbilities": True,
                                 "includeInactive": True}, 120)
    cu = next((u for u in (dvi.get("units") or []) if u.get("id") == carrier_id), None)
    for e in ((cu or {}).get("effects") or []):
        if e.get("name") == EFFECT_NAME:
            lvl = e.get("level")
            return bool(e.get("active")), (None if lvl is None else int(lvl))
    return None


def _debuffs_of(h, unit_id: int) -> list:
    dv = h.dview()
    ids = set(_debuff_ids())
    u = next((x for x in (dv.get("units") or []) if x.get("id") == unit_id), None)
    return [e.get("name") for e in ((u or {}).get("effects") or []) if e.get("effectType") in ids]


def _targets_from_here(h, caster_id: int) -> set:
    """Les cibles LEGALES **sans bouger** de l'attaque normale (`abilityTargets.fromHere`).

    On demande au JEU au lieu de re-deriver portee et ligne de vue : un tir refuse rend
    `applyAction ok:true, changes:[]` SANS erreur, et le montage se lirait alors comme un compteur
    nul -- exactement le faux negatif que ce probe doit eviter."""
    tg = h.rpc("abilityTargets", {"runnerId": h.rid, "casterId": int(caster_id),
                                  "abilityType": NORMAL_ATTACK}, 60)
    out = set()
    for u in (tg.get("units") or []):
        if u.get("unitId") != int(caster_id):
            continue
        for ab in (u.get("abilities") or []):
            for t in (ab.get("fromHere") or []):
                # ⚠ la cle est `targetId`, PAS `unitId` (qui designe le CASTER dans l'enveloppe).
                # Lire `unitId` ici rendait un ensemble VIDE en silence, et le montage se refusait
                # (« aucun TIR possible ») sur une geometrie pourtant legale -- mesure du montage.
                tid = t.get("targetId") if isinstance(t, dict) else t
                if tid is not None:
                    out.add(int(tid))
    return out


def _tirer(h, pinner_id: int, victim_id: int) -> bool:
    """Le pinner TIRE sur `victim_id` -- rend True SSI le tir a REELLEMENT eu lieu."""
    if victim_id not in _targets_from_here(h, pinner_id):
        return False
    r = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": int(pinner_id), "targetId": int(victim_id),
        "abilityType": NORMAL_ATTACK}}, 60)
    a0 = (r.get("actions") or [{}])[0]
    return bool(a0.get("ok")) and bool(a0.get("events"))


def _ancre(h, cfg: dict):
    """Une tuile a >= 5 voisins NATIFS, >= 5 tuiles a distance 2 et >= 5 a distance 3 : c'est ce
    qu'il faut pour poser une cible au contact, des victimes a 2 et a 3, et un tireur au large."""
    import hexgeo
    board = h.board
    for t in sorted(board.by_id):
        if not board.walkable(t):
            continue
        c = board.coord(t)
        nn = [v for v in board.neighbours_native(t) if board.walkable(v)]
        d2 = [x for x in board.by_id if board.walkable(x)
              and hexgeo.distance(c, board.coord(x)) == 2]
        d3 = [x for x in board.by_id if board.walkable(x)
              and hexgeo.distance(c, board.coord(x)) == 3]
        if len(nn) >= 5 and len(d2) >= 5 and len(d3) >= 5:
            return c
    return None


def _occupe(h, exclure=()):
    ex = set(exclure)
    return {_pos(u) for u in h.alive() if u.get("id") not in ex}


def _libres_a(h, centre, d, exclure=()):
    import hexgeo
    occ = _occupe(h, exclure)
    board = h.board
    return [board.coord(t) for t in sorted(board.by_id)
            if board.walkable(t) and hexgeo.distance(tuple(centre), board.coord(t)) == d
            and board.coord(t) not in occ]


#: MUTANTS du COMPTEUR. Chacun est une lecture PLAUSIBLE et FAUSSE de `$$GetLevelFormula` -- la
#: plupart sont le geste « recopier le voisin de forme ». Un mutant VERT dit que le temoin est
#: aveugle : chaque entree declare donc dans QUEL regime il DOIT mordre.
#:   `enn`  = regime des victimes ENNEMIES a portee (le bras de degat)
#:   `self` = regime `--compteur` : le PORTEUR et un AMI, tous deux `Thrilled`
_MUTANTS = {
    # `includeCenter: 1` lu comme 0 -- le porteur ne se compterait plus lui-meme.
    "SANS_CENTRE": {"self": True, "enn": False},
    # la geometrie de `KardiocoreGalvanus` : ring-1 STOCKE, filtre d'EQUIPE, centre EXCLU.
    "VOISIN_KARDIOCORE": {"self": True, "enn": True},
    # `GetNumberConstant(0x16 = range)` lu a 1 au lieu de 2. Il mord dans les DEUX regimes : le
    # tireur AMI du bras `--compteur` est pose a distance `range` EXACTEMENT (c'est la contrainte
    # qui le fait tirer sans etre au contact), donc un rayon rabattu a 1 le perd aussi.
    "PORTEE_1": {"self": True, "enn": True},
    # le bloc `EffectType[4]` ampute de `Pinned` (1065).
    "SANS_PINNED": {"self": False, "enn": True},
    # ... ou de `ThrillSeekers` (1434).
    "SANS_THRILLED": {"self": True, "enn": False},
    # `Min(Count(...), Get(nrOfUnits))` avec un plafond de 1 : le PRODUIT ne discrimine plus.
    "PLAFOND_1": {"self": True, "enn": True},
}


def _selecteur_mutant(nom: str):
    """Reconstruit l'arbre du compteur avec UNE lecture fausse. Ce n'est PAS le port : c'est une
    copie deliberement alteree, dont le seul role est de faire ROUGIR le temoin."""
    from engine.dsl.base import Const
    from engine.entities.effects.loki.intoxicating_elixir import (DEBUFFS, _CONST_NR_OF_UNITS,
                                                                  _CONST_RANGE, _SEL, _const)
    from engine.entities.formulas import Count, Min
    from engine.entities.selectors.accessors import Owner
    from engine.entities.selectors.geometry import EntitiesWithAnyEffect
    from engine.entities.selectors.units import AdjacentFriends, SurroundingUnits, Tiles

    rng = int(_const(_CONST_RANGE))
    cap = int(_const(_CONST_NR_OF_UNITS))
    ids = [int(e) for e in DEBUFFS]
    centre = True
    if nom == "SANS_CENTRE":
        centre = False
    elif nom == "PORTEE_1":
        rng = 1
    elif nom == "SANS_PINNED":
        ids = [i for i in ids if i != 1065]
    elif nom == "SANS_THRILLED":
        ids = [i for i in ids if i != 1434]
    elif nom == "PLAFOND_1":
        cap = 1
    if nom == "VOISIN_KARDIOCORE":
        disque = AdjacentFriends(Owner(), Const(1), Owner(), _SEL)
    else:
        disque = SurroundingUnits(Tiles(Owner()), Const(rng), include_center=centre,
                                  selection_type=_SEL)
    return Min(Count(EntitiesWithAnyEffect(disque, ids)), Const(cap))


def mutants_compteur(st, uid: int, attendu: int, regime: str) -> int:
    """Rejoue le COMPTEUR sous chaque mutation et exige qu'il MORDE la ou il doit.

    La substitution porte sur `engine.runner.components.debuffed_units_in_range_selector` -- la
    LIAISON REELLEMENT appelee par `debuffed_units_in_range_count` (l'import y est de forme A, donc
    patcher le module d'origine serait INERTE, cf. CLAUDE.md)."""
    import engine.runner.components as C
    orig = C.debuffed_units_in_range_selector
    rc = 0
    try:
        for nom, ou in _MUTANTS.items():
            C.debuffed_units_in_range_selector = (lambda _n=nom: _selecteur_mutant(_n))
            got = C.debuffed_units_in_range_count(st, int(uid))
            mord = (got != attendu)
            doit = bool(ou[regime])
            marque = "OK " if mord == doit else "!! "
            print("        %sMUTANT %-18s -> %s (attendu %s, mord=%s doit=%s)"
                  % (marque, nom, got, attendu, mord, doit))
            if mord != doit:
                rc |= 1
    finally:
        C.debuffed_units_in_range_selector = orig
    return rc


def _pose(h, uid, cands):
    """Un `place` peut echouer sur une tuile pourtant libre AU MOMENT DU CALCUL : on essaie les
    candidats dans l'ordre plutot que d'abandonner sur le premier."""
    occ = _occupe(h, (uid,))
    for c in cands:
        if c not in occ and h.place(uid, c):
            return c
    return None


# ---------------------------------------------------------------- E2 : montage DEGAT

def stage_degat(h, a, n: int, cfg: dict):
    """Monte le regime « `n` unites DEBUFFEES a portee du porteur » et rend `(rec, raison)`.

    ORDRE, et il est CONTRAINT :
      1. cycle de tour d'abord (les `place` sont de VRAIS `MoveUnitOperation`) ;
      2. tout le monde LOIN, puis le porteur sur son ancre, puis les autres -- amener une unite
         ADVERSE au contact APRES le porteur declencherait ses reactions et consommerait son action ;
      3. les TIRS, qui posent les `Pinned` ;
      4. les tireurs REPOUSSES a >= 3 du porteur : leur propre `Thrilled` (pose par
         `ThrillSeekersAbility` a leur premier coup sur une cible pleine vie) compterait sinon ;
      5. LECTURE de l'etat, jamais supposition.

    La cible de MELEE du porteur est TOUJOURS une victime DEJA BLESSEE : `ThrillSeekersAbility`
    exige `NOT IsWounded(target)`, donc le porteur ne devient PAS `Thrilled` pendant sa salve et le
    compteur reste CONSTANT d'un coup a l'autre (cf. le residu #922-r1 en tete de module)."""
    import hexgeo
    dv = h.dview()
    carrier = h.by_visual(CARRIER, dv)
    if carrier is None:
        return None, "porteur absent du deploiement"
    h.my_player = carrier.get("owner")
    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"
    dv = h.dview()
    carrier = h.by_visual(CARRIER, dv)
    mine = [u for u in h.alive(dv) if u.get("owner") == h.my_player]
    pinners = [u for u in mine if u.get("id") != carrier["id"]]
    foes = [u for u in h.alive(dv) if u.get("owner") != h.my_player]
    if len(pinners) < 2 or len(foes) < 2:
        return None, "roster insuffisant (2 tireurs + 2 victimes attendus)"

    anchor = _ancre(h, cfg)
    if anchor is None:
        return None, "aucune ancre a >= 5 voisins natifs sur ce board"
    board = h.board

    # 2. tout le monde LOIN d'abord
    loin = _libres_a(h, anchor, 5) + _libres_a(h, anchor, 4)
    for u in pinners + foes:
        if _pose(h, u["id"], loin) is None:
            return None, "impossible d'eloigner %s" % u.get("id")
        loin = [c for c in loin if c not in _occupe(h)]
    if _pose(h, carrier["id"], [anchor]) is None:
        return None, "placement du porteur refuse (ancre %s)" % (anchor,)

    # V0 = la cible de MELEE, sur un voisin NATIF du porteur (l'adjacence du jeu, pas hexgeo)
    ctile = board.id_at(*anchor)
    adj = [board.coord(v) for v in board.neighbours_native(ctile) if board.walkable(v)]
    v0, v1 = foes[0], foes[1]
    if _pose(h, v0["id"], adj) is None:
        return None, "placement de la cible de melee refuse"
    # V1 = la SECONDE victime, a la distance demandee (2 = comptee, 3 = hors portee). Sous
    # `--thrilled` c'est ELLE qui porte le `Pinned` (V0 doit rester a PLEINE VIE pour que
    # `ThrillSeekersAbility` morde), donc elle est posee des `n >= 1`.
    seuil_v1 = 1 if getattr(a, "thrilled", False) else 2
    if n >= seuil_v1 and _pose(h, v1["id"], _libres_a(h, anchor, a.dist)) is None:
        return None, "placement de la 2e victime refuse (distance %d)" % a.dist

    # 3. les TIRS. Un tir RANGED pose `Pinned` (trait `SuppressiveFire`) ; un coup de MELEE, NON --
    # c'est ce qui donne le regime `n = 0` : la cible est BLESSEE sans etre DEBUFFEE.
    def _tirer_sur(pinner, victime, ranged: bool) -> bool:
        # ⚠ POSITION RELUE, jamais celle du dict capte avant les placements : les deux unites ont
        # bouge depuis. Un `vpos` perime faisait chercher les tuiles de tir autour de l'ANCIENNE
        # case et le bras REFUSAIT (« aucun TIR possible ») sur un montage pourtant realisable.
        vpos = _pos(next((u for u in h.alive() if u.get("id") == victime["id"]), None))
        if vpos == (None, None):
            return False
        ds = [2, 3] if ranged else [1]
        for d in ds:
            for c in _libres_a(h, vpos, d, (pinner["id"],)):
                if hexgeo.distance(c, anchor) < 3 and ranged:
                    continue            # le tireur ne doit pas compter par son propre `Thrilled`
                if not h.place(pinner["id"], c):
                    continue
                if _tirer(h, pinner["id"], victime["id"]):
                    return True
        return False

    if getattr(a, "thrilled", False):
        # BRAS MI-SALVE : la cible de MELEE reste a PLEINE VIE, donc `ThrillSeekersAbility`
        # (`On(6) & IsFirstHitInSeries & get_OwnerIsCaster & NOT IsWounded(target)`) rend le
        # PORTEUR `Thrilled` apres son coup 0 -- le compteur MONTE D'UN CRAN EN COURS DE SALVE.
        # ⚠ A `n = 0` l'effet est INACTIF au snapshot, donc ABSENT du canal `decisionView`
        # (ACTIF-ONLY, #100) et donc de l'etat OFFLINE : le port ne peut alors RIEN verser, quoi
        # que fasse le compteur (residu de SEEDING, cf. le rapport). A `n >= 1` l'effet EST capte,
        # et la montee du compteur devient confrontable.
        if n >= 1 and not _tirer_sur(pinners[0], v1, ranged=True):
            return None, "aucun TIR possible sur la victime de fond (bras --thrilled)"
    elif n == 0:
        if not _tirer_sur(pinners[0], v0, ranged=False):
            return None, "aucun coup de MELEE possible sur la cible (regime n=0)"
    else:
        if not _tirer_sur(pinners[0], v0, ranged=True):
            return None, "aucun TIR possible sur la cible de melee"
        if n >= 2 and not _tirer_sur(pinners[1], v1, ranged=True):
            return None, "aucun TIR possible sur la 2e victime"

    # 4. les tireurs REPOUSSES hors du disque de rayon `range`
    for pn in pinners:
        if hexgeo.distance(_pos(pn), anchor) <= cfg["range"]:
            cands = [c for d in (4, 5, 3) for c in _libres_a(h, anchor, d, (pn["id"],))]
            if _pose(h, pn["id"], cands) is None:
                return None, "impossible de repousser le tireur hors du disque"

    # 5. l'etat MESURE, jamais suppose
    dv = h.dview()
    carrier = h.by_visual(CARRIER, dv)
    cible = next((u for u in h.alive(dv) if u.get("id") == v0["id"]), None)
    if carrier is None or cible is None:
        return None, "porteur ou cible disparu pendant le montage"
    if not carrier.get("hasAction"):
        return None, "le porteur a perdu son action pendant le montage"
    ids = set(_debuff_ids())
    n_mesure = 0
    for u in h.alive(dv):
        if u.get("id") == carrier["id"]:
            continue
        if hexgeo.distance(_pos(u), _pos(carrier)) > cfg["range"]:
            continue
        if any(e.get("effectType") in ids for e in (u.get("effects") or [])):
            n_mesure += 1
    porteur_debuffe = any(e.get("effectType") in ids for e in (carrier.get("effects") or []))
    if porteur_debuffe:
        n_mesure += 1                       # `includeCenter = 1`

    lu = _effet_natif(h, carrier["id"])
    if lu is None:
        return None, ("l'effet %s est ABSENT du canal (meme `includeInactive`) -- la relique n'est "
                      "PAS montee sur %s" % (EFFECT_NAME, CARRIER))
    actif, niveau_natif = lu
    rec = {"caster": carrier["id"], "target": cible["id"], "porteur": carrier["id"],
           "ability_type": NORMAL_ATTACK, "step_to": None,
           "n": n_mesure, "anchor": anchor, "actif_natif": bool(actif),
           "niveau_natif": niveau_natif,
           "hp": carrier.get("hp"), "debuffs_porteur": _debuffs_of(h, carrier["id"]),
           "cible_hp": cible.get("hp")}
    rec["snapshot"] = h.snapshot(inactifs=INACTIFS)
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    return rec, None


def frappe(h, rec):
    live = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
        "abilityType": int(rec["ability_type"])}}, 60)
    a0 = (live.get("actions") or [{}])[0]
    hits = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if ("Amount" in td and td.get("Attacker_Id") == rec["caster"]
                and td.get("Target_Id") == rec["target"]):
            hits.append(int(td["Amount"]))
    if not a0.get("ok") or not hits:
        return None, "attaque live refusee/vide (%s)" % str(live)[:200]
    if not any(u.get("id") == rec["target"] for u in h.alive()):
        return None, "cible MORTE pendant la salve -- flux live tronque"
    return hits, None


def rejeu(h, rec, mutate=None):
    """Rejeu OFFLINE de la MEME attaque, RNG neutralise par le dump pris apres le montage.

    `NOCHANNEL` : l'effet retire d'`EFFECT_CLASSES` AVANT `load_state` -- la FACTORY le fait alors
    retomber sur `BaseEffect`, dont `create_effect_crit_damage_bonus_for_attack` rend `None`.
    C'est la vue « d'AVANT ce port ».

    `PASSIF` : le callable `tertiary_ability_state_of` retire du contexte -- le port retombe sur
    `ability_level` (le niveau des PASSIFS, 50 en runner normalise -> dernier palier).

    `SANSSANTE` : le callable `unit_health_of` retire -- le facteur `ConditionalAmount` retombe sur
    sa branche NON DOUBLEE. Ne peut mordre que si le porteur est REELLEMENT sous le seuil.

    `CRITDMG_AVANT` : la crit DAMAGE figee sur sa PREMIERE mesure (celle d'AVANT `On(6)`) -- c'est
    exactement l'etat du port AVANT le correctif #922 des trois vecteurs. Ne peut mordre que si un
    ecouteur d'`On(6)` change la crit damage EN COURS DE SALVE (bras `--thrilled`)."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.runner.operations import damage as D
    saved = EFFECT_CLASSES.get(EFFECT_NAME)
    orig = D.AttackDamageOperation._crit_board
    orig_params = D.AttackDamageOperation._crit_params
    try:
        if mutate == "CRITDMG_AVANT":
            memo = {}

            def _fige(ctx, attacker_effects, state=None, att_id=None, tgt_id=None, **kw):
                cc, cd, en = orig_params(ctx, attacker_effects, state, att_id, tgt_id, **kw)
                cle = (id(state), att_id, tgt_id)
                if cle in memo:
                    cd = memo[cle]
                else:
                    memo[cle] = cd
                return cc, cd, en
            D.AttackDamageOperation._crit_params = staticmethod(_fige)
        if mutate == "NOCHANNEL":
            EFFECT_CLASSES.pop(EFFECT_NAME, None)
        if mutate in ("PASSIF", "SANSSANTE"):
            cle = "tertiary_ability_state_of" if mutate == "PASSIF" else "unit_health_of"

            def _sans(state, att_id, tgt_id, _c=cle, _o=orig):
                d = dict(_o(state, att_id, tgt_id))
                d.pop(_c, None)
                return d
            D.AttackDamageOperation._crit_board = staticmethod(_sans)
        return h.replay_offline(rec)["per_hit"]
    finally:
        if saved is not None:
            EFFECT_CLASSES[EFFECT_NAME] = saved
        D.AttackDamageOperation._crit_board = orig
        D.AttackDamageOperation._crit_params = orig_params


def etages(h, rec) -> dict:
    """DECOMPOSITION PAR ETAGE du port sur l'etat OFFLINE -- jamais un scalaire fitte.

    Rend, dans l'ordre du natif : le COMPTEUR PLAFONNE (`GetCalculateLevel`), l'activite de
    l'effet (`CreateActiveCondition`), le couple `(level, mult)` de `GetAbilityState(effet)`, la
    sante lue par `HealthPctIsBelowOrEqual`, et le scalaire SIGNE que le canal verse."""
    from engine.runner.components import debuffed_units_in_range_count, unit_state_for_effects
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.triggers.base import triggered_ability_state
    st = h.offline_state(rec)
    aid, tid = int(rec["caster"]), int(rec["target"])
    oid = int(rec.get("porteur", aid))
    out = {"compteur": debuffed_units_in_range_count(st, oid),
           "ability_state": triggered_ability_state(st, oid, ABILITY_ID)}
    effs = st.effects.active_effects(oid, unit_state_for_effects(st, oid)) if st.effects else []
    cible = next((e for e in effs if getattr(e, "name", None) == EFFECT_NAME), None)
    out["effet_actif_port"] = cible is not None
    # #1081 -- SEPARER « pas d'instance du tout » de « instance presente mais INACTIVE ». Les deux
    # rendent `effet_actif_port = False`, donc le diagnostic ecrit (« ABSENT de l'etat offline »)
    # n'etait PAS mesure : il supposait le premier cas. Or le canal de seed passe
    # `includeInactive: true` (`snapshot.decision_view_seed_body`), donc la seconde lecture est
    # possible -- et c'est elle qui dit si le residu porte sur le SEED ou sur la REACTIVATION.
    _bu = getattr(st.effects, "by_unit", None) if st.effects else None
    _inst = [e for e in ((_bu or {}).get(oid) or []) if getattr(e, "name", None) == EFFECT_NAME]
    out["instance_dans_by_unit"] = len(_inst)
    ctx = dict(AttackDamageOperation._crit_board(st, aid, tid))
    ctx.update({"att_id": aid, "tgt_id": tid, "owner_id": oid})
    out["sante"] = ctx["unit_health_of"](oid)
    out["bonus_signe"] = (cible.create_effect_crit_damage_bonus_for_attack(ctx)
                          if cible is not None else None)
    return out


def run_degat(a, rpc, Board, Harness, n: int, cfg: dict) -> int:
    # le montage `--low-hp` vit dans `build` (foyer UNIQUE, partage avec le cliquet).
    rid, sf = build(a, "deg_n%d_%s" % (n, "low" if a.low_hp else "full"), a.level)
    if rid is None:
        return 2
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = stage_degat(h, a, n, cfg)
        if rec is None:
            print("[n=%d] REFUS : %s" % (n, why))
            return 2
        live, why = frappe(h, rec)
        if live is None:
            print("[n=%d] REFUS : %s" % (n, why))
            return 2
        off = rejeu(h, rec)
        k = len(live)
        accord = (off[:k] == live)
        et = etages(h, rec)

        if a.thrilled:
            # MESURE du residu #922-r1, jamais une supposition. Le NATIF doit STEPPER en cours de
            # salve (coup 0 sans bonus, coups 1+ avec, le porteur etant devenu `Thrilled`) ; le
            # PORT, lui, calcule sa crit-DAMAGE une seule fois (`crit_apres[1]` n'est jamais
            # consomme par `_run_hits`, seul `crit_chance_after` l'est).
            after = _debuffs_of(h, rec["porteur"])
            mut = rejeu(h, rec, mutate="NOCHANNEL")
            avant = rejeu(h, rec, mutate="CRITDMG_AVANT")
            print("[--thrilled n=%d] debuffs du PORTEUR APRES la salve = %s | compteur natif au "
                  "snapshot = %s (actif %s)" % (n, after, rec["niveau_natif"], rec["actif_natif"]))
            print("        LIVE          %s" % (live[:6],))
            print("        OFFLINE       %s  accord=%s" % (off[:k][:6], accord))
            print("        NOCHANNEL     %s  (le port SANS le canal)" % (mut[:k][:6],))
            print("        CRITDMG_AVANT %s  (le port AVANT le correctif #922 des 3 vecteurs)"
                  % (avant[:k][:6],))
            rc = 0
            if not after:
                print("        !! le porteur n'est PAS devenu Thrilled -- bras degenere")
                rc |= 2
            if not rec["actif_natif"]:
                # A `n = 0` l'effet est INACTIF au snapshot, donc ABSENT du canal `decisionView`
                # (ACTIF-ONLY) et de l'etat OFFLINE : le port ne peut RIEN verser. C'est un residu
                # de SEEDING, pas une faute de ce port -- on le MESURE et on le DIT.
                _n = et.get("instance_dans_by_unit")
                print("        [residu SEEDING] l'effet est INACTIF au snapshot. Instance(s) dans "
                      "l'etat offline (`EffectsState.by_unit`) = %s -> %s" % (
                          _n, "PRESENTE, le residu porte sur la REACTIVATION"
                          if _n else "AUCUNE, le residu porte sur le SEED"))
                print("        Ecart par coup = %s"
                      % ([l - o for l, o in zip(live, off[:k])],))
                return rc
            if not accord:
                print("        !! LIVE != OFFLINE : ecart par coup = %s"
                      % ([l - o for l, o in zip(live, off[:k])],))
                rc |= 1
            if off[:k] == mut[:k]:
                print("        !! le canal ne verse RIEN offline -- bras degenere")
                rc |= 2
            if avant[:k] == off[:k]:
                print("        !! CRITDMG_AVANT ne mord PAS : ce bras n'exerce pas le correctif")
                rc |= 2
            return rc

        # ATTENDU, DERIVE des etages MESURES (jamais un scalaire code en dur) :
        #   bonus = extraCritDmg[level] x min(n, nrOfUnits) x (2 si hp <= healthPct % sinon 1)
        v = cfg["paliers"][a.level - 1]
        n_eff = min(rec["n"], cfg["nrOfUnits"])
        hp, mx = et["sante"]
        double = (hp is not None and mx and 100 * int(hp) <= cfg["healthPct"] * int(mx))
        bonus_attendu = (v * n_eff * (2 if double else 1)) or None

        rc = 0
        # E1 -- l'ACTIVITE : `AmountIsGreaterThanZero(<compteur>)`.
        if bool(rec["actif_natif"]) != (n_eff > 0):
            print("        !! ACTIF natif = %s, attendu %s (compteur mesure %d)"
                  % (rec["actif_natif"], n_eff > 0, n_eff))
            rc |= 1
        if et["effet_actif_port"] != (n_eff > 0):
            print("        !! ACTIF port = %s, attendu %s" % (et["effet_actif_port"], n_eff > 0))
            rc |= 1
        # E1 -- le NIVEAU STOCKE, qui ne fait foi que si l'effet est ACTIF (cf. `_effet_natif`).
        if rec["actif_natif"] and rec["niveau_natif"] != n_eff:
            print("        !! COMPTEUR NATIF (decisionView.effects[].level) = %s, attendu %d"
                  % (rec["niveau_natif"], n_eff))
            rc |= 1
        if et["compteur"] != n_eff:
            print("        !! COMPTEUR du port = %s, attendu %d" % (et["compteur"], n_eff))
            rc |= 1
        if et["bonus_signe"] != bonus_attendu:
            print("        !! BONUS du port = %s, attendu %s" % (et["bonus_signe"], bonus_attendu))
            rc |= 1
        if not accord:
            rc |= 1

        # CONTRE-EPREUVES -- un mutant VERT dit que le temoin est aveugle.
        mut = rejeu(h, rec, mutate="NOCHANNEL")
        mord = (mut[:k] != off[:k])
        attendu = (bonus_attendu is not None)
        if mord != attendu:
            rc |= 1
        passif_attendu = attendu and (a.level != len(cfg["paliers"]))
        mut2 = rejeu(h, rec, mutate="PASSIF")
        mord2 = (mut2[:k] != off[:k])
        if mord2 != passif_attendu:
            rc |= 1
        sante_attendu = attendu and double
        mut3 = rejeu(h, rec, mutate="SANSSANTE")
        mord3 = (mut3[:k] != off[:k])
        if mord3 != sante_attendu:
            rc |= 1

        print("[n=%d dist=%d lvl=%d low_hp=%s] compteur natif=%s port=%s (attendu %d) | "
              "actif natif=%s port=%s | hp=%s/%s double=%s | bonus port=%s (attendu %s)"
              % (n, a.dist, a.level, a.low_hp, rec["niveau_natif"], et["compteur"], n_eff,
                 rec["actif_natif"], et["effet_actif_port"], hp, mx, double,
                 et["bonus_signe"], bonus_attendu))
        print("        debuffs du PORTEUR %s | ability_state %s"
              % (rec["debuffs_porteur"], et["ability_state"]))
        print("        LIVE      %s" % (live[:6],))
        print("        OFFLINE   %s  accord=%s" % (off[:k][:6], accord))
        print("        NOCHANNEL %s  mord=%s (attendu %s)" % (mut[:k][:6], mord, attendu))
        print("        PASSIF    %s  mord=%s (attendu %s)" % (mut2[:k][:6], mord2, passif_attendu))
        print("        SANSSANTE %s  mord=%s (attendu %s)" % (mut3[:k][:6], mord3, sante_attendu))
        if a.mutants and n >= 2 and a.dist <= cfg["range"]:
            rc |= mutants_compteur(h.offline_state(rec), rec["porteur"], n_eff, "enn")
        return rc
    finally:
        from engine.runner.snapshot import clear_ability_states_cache
        clear_ability_states_cache("build#%s" % rid)
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


# ---------------------------------------------------------------- E1 : les DEUX quirks de geometrie

def run_compteur(a, rpc, Board, Harness, cfg: dict) -> int:
    """Le compteur SEUL, sur les deux quirks que le port ne partage avec AUCUN voisin de forme :

      * `includeCenter = 1` -- le PORTEUR SE COMPTE LUI-MEME. Exerce en le rendant `Thrilled` :
        il frappe une cible a PLEINE VIE, `ThrillSeekersAbility` pose `1434` sur LUI ;
      * AUCUN FILTRE D'EQUIPE -- un AMI compte. Exerce par le tireur, qui devient `Thrilled` a son
        propre tir et qu'on laisse DANS le disque de rayon `range`.

    Aucune comparaison de DEGAT ici : cet etage est immunise au residu #922-r1 (le compteur est lu
    APRES la salve, pas pendant)."""
    import hexgeo
    rid, sf = build(a, "cpt", a.level)
    if rid is None:
        return 2
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        dv = h.dview()
        carrier = h.by_visual(CARRIER, dv)
        h.my_player = carrier.get("owner")
        if h.reach_my_turn(force_cycle=True) is None:
            print("[compteur] REFUS : mon tour non atteint")
            return 2
        dv = h.dview()
        carrier = h.by_visual(CARRIER, dv)
        mine = [u for u in h.alive(dv) if u.get("owner") == h.my_player]
        pinners = [u for u in mine if u.get("id") != carrier["id"]]
        foes = [u for u in h.alive(dv) if u.get("owner") != h.my_player]
        anchor = _ancre(h, cfg)
        board = h.board
        loin = _libres_a(h, anchor, 5) + _libres_a(h, anchor, 4)
        for u in pinners + foes:
            _pose(h, u["id"], loin)
            loin = [c for c in loin if c not in _occupe(h)]
        _pose(h, carrier["id"], [anchor])
        ctile = board.id_at(*anchor)
        adj = [board.coord(v) for v in board.neighbours_native(ctile) if board.walkable(v)]
        if _pose(h, foes[0]["id"], adj) is None:
            print("[compteur] REFUS : cible de melee non posable")
            return 2
        # le TIREUR reste DANS le disque (distance `range`), et tire au LARGE sur une cible pleine
        # vie -> il devient `Thrilled` et doit COMPTER, alors qu'il est AMI.
        pn, victime = pinners[0], foes[1]
        pose_ok = False
        for c in _libres_a(h, anchor, cfg["range"], (pn["id"],)):
            for cv in _libres_a(h, c, 2, (victime["id"],)) + _libres_a(h, c, 3, (victime["id"],)):
                if hexgeo.distance(cv, anchor) <= cfg["range"]:
                    continue                    # la victime ne doit PAS compter, elle
                if not h.place(victime["id"], cv):
                    continue
                if h.place(pn["id"], c) and _tirer(h, pn["id"], victime["id"]):
                    pose_ok = True
                    break
            if pose_ok:
                break
        if not pose_ok:
            print("[compteur] REFUS : aucun couple (tireur a %d, victime au large) tirable"
                  % cfg["range"])
            return 2
        av = _effet_natif(h, carrier["id"])
        # le PORTEUR frappe une cible a PLEINE VIE -> `ThrillSeekers` le rend `Thrilled`
        if not _tirer(h, carrier["id"], foes[0]["id"]):
            print("[compteur] REFUS : le porteur ne peut pas frapper sa cible")
            return 2
        ap = _effet_natif(h, carrier["id"])
        dv = h.dview()
        carrier = h.by_visual(CARRIER, dv)
        rec = {"caster": carrier["id"], "target": foes[0]["id"], "porteur": carrier["id"],
               "ability_type": NORMAL_ATTACK, "step_to": None, "snapshot": h.snapshot(inactifs=INACTIFS)}
        rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
        st = h.offline_state(rec)
        from engine.runner.components import debuffed_units_in_range_count
        port = debuffed_units_in_range_count(st, int(carrier["id"]))
        d_porteur = _debuffs_of(h, carrier["id"])
        d_tireur = _debuffs_of(h, pn["id"])
        # POSITION RELUE : `pn` est le dict d'AVANT les placements (meme piege que dans
        # `stage_degat`) -- l'afficher tel quel imprimait une distance FAUSSE, qui a fait ecrire une
        # attente de mutant erronee avant d'etre corrigee par la mesure.
        pn = next((u for u in h.alive() if u.get("id") == pn["id"]), pn)
        print("[compteur] AVANT la salve du porteur : actif/level natif = %s" % (av,))
        print("[compteur] APRES : actif/level natif = %s | port = %s" % (ap, port))
        print("           debuffs PORTEUR %s (includeCenter) | debuffs TIREUR AMI %s (aucun filtre "
              "d'equipe) | d(tireur, porteur) = %d"
              % (d_porteur, d_tireur, hexgeo.distance(_pos(pn), _pos(carrier))))
        rc = 0
        # Le TEMOIN doit etre NON DEGENERE : sans les deux `Thrilled` le bras ne prouverait rien.
        if not d_porteur:
            print("        !! le porteur n'est PAS debuffe -- bras degenere, verdict REFUSE")
            rc |= 2
        if not d_tireur:
            print("        !! le tireur AMI n'est PAS debuffe -- bras degenere, verdict REFUSE")
            rc |= 2
        attendu = (1 if d_porteur else 0) + (1 if d_tireur else 0)
        if ap is None or not ap[0]:
            print("        !! l'effet n'est pas ACTIF alors que %d unites sont debuffees a portee"
                  % attendu)
            rc |= 1
        elif ap[1] != attendu:
            print("        !! COMPTEUR NATIF = %s, attendu %d" % (ap[1], attendu))
            rc |= 1
        if port != attendu:
            print("        !! COMPTEUR du port = %s, attendu %d" % (port, attendu))
            rc |= 1
        if a.mutants:
            rc |= mutants_compteur(st, int(carrier["id"]), attendu, "self")
        return rc
    finally:
        from engine.runner.snapshot import clear_ability_states_cache
        clear_ability_states_cache("build#%s" % rid)
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="922")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--crit-damage", type=int, default=2000,
                    help="CritDamage des p-units. Pas de garde de saturation : le terme est "
                         "ADDITIF, donc le `Math.Max(0, .)` de CalculateCriticalDamage ne peut pas "
                         "mordre. La valeur ne sert qu'a rendre la salve lisible.")
    ap.add_argument("--n", default="0,1,2", help="unites DEBUFFEES a portee (un runner par n)")
    ap.add_argument("--dist", type=int, default=2,
                    help="distance hex de la 2e victime. `range` (=2) -> elle COMPTE ; "
                         "`range + 1` -> le disque `SurroundingUnits` doit l'EXCLURE.")
    ap.add_argument("--level", type=int, default=3, help="niveau de la RELIQUE (1..10)")
    ap.add_argument("--low-hp", action="store_true",
                    help="BRAS SANTE : le porteur sous `healthPct` %% de vie -> le "
                         "`ConditionalAmount` doit DOUBLER le bonus.")
    ap.add_argument("--thrilled", action="store_true",
                    help="BRAS RESIDU #922-r1 : la cible reste a PLEINE VIE, donc le PORTEUR "
                         "devient `Thrilled` apres son coup 0 et le compteur STEPPE EN COURS DE "
                         "SALVE. MESURE l'ecart au lieu de le supposer.")
    ap.add_argument("--mutants", action="store_true",
                    help="rejoue le COMPTEUR sous SIX lectures fausses de `$$GetLevelFormula` et "
                         "exige que chacune MORDE dans son regime. Un mutant VERT dit que le "
                         "temoin est aveugle.")
    ap.add_argument("--inactifs", action="store_true",
                    help="#922-r1 : capture `decisionView` avec `includeInactive: true`. "
                         "`IntoxicatingElixir` est un owner-effect a condition GEOMETRIQUE : il "
                         "est POSE mais INACTIF a l'instant de la capture (le compteur ne devient "
                         "positif que PENDANT la salve), donc le canal par defaut le DROPPE avant "
                         "`load_state` et le port ne verse RIEN. OPT-IN : le drapeau elargit "
                         "l'etat charge, et `ChargeRegimeHarness` est partage par 53 fichiers.")
    ap.add_argument("--compteur", action="store_true",
                    help="ETAGE E1 SEUL : les deux quirks de geometrie (`includeCenter` et "
                         "l'absence de filtre d'equipe), sans aucune comparaison de degat.")
    a = ap.parse_args()
    # #922-r1 -- le CANAL de la capture qui alimente `load_state`, porte en global parce que les
    # DEUX sites de capture (`_mesure_une_cible` et le bras temoin) sont hors de `main`. Defaut
    # `False` : aucune mesure existante ne change de canal.
    global INACTIFS
    INACTIFS = bool(a.inactifs)

    cfg = config_du_gameconfig()
    print("== #922 IntoxicatingElixir (EffectType 1459 / TriggeredAbility 1463)")
    _garde_regime(a.level, cfg)

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    # ⚠ CANAL RELIQUE. `load_state` tire `unitAbilityStates` elle-meme, mais SEULEMENT si un
    # transport AMBIANT est lie (`snapshot.bind_live_rpc`, #357/#363). Sans lui,
    # `UnitContext.tertiary_ability` reste `None` et `triggered_ability_state` retombe sur le
    # couple PASSIF, donc `extraCritDmg` au dernier palier.
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(rpc)

    rc = 0
    if a.compteur:
        rc |= run_compteur(a, rpc, Board, ChargeRegimeHarness, cfg)
    else:
        for n in [int(x) for x in a.n.split(",") if x.strip()]:
            rc |= run_degat(a, rpc, Board, ChargeRegimeHarness, n, cfg)
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
