"""probe #27-r1 -- A/B causal LIVE de MassDriverAccelerator (1222, `votanChampion` Kimm) :
le terme `CalculateCustomUtility` est-il `W x |amis adjacents|` (formule heritee de case-27)
ou IDENTIQUEMENT NUL ?

CE QUE LE DECOMPILE DIT (cf. `engine.playbook.loki_custom.MassDriverAcceleratorPlaybook`) :
`IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$CalculateCustomUtility` evalue
`MassDriverAcceleratorAbility$$GetBuffTargets` = `Owner + AdjacentFriends(Owner, 1, 3)` contre un
`AbilityEntities` dont le champ **`owner` est NULL** (`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor`
ecrit `+0x18 = owner`, et le call-site passe 9 zeros en positions 4..12).
`IdunBattle.Entities.Selectors.OwnerSelector$$Select` lit `entities+0x18` et rend une liste VIDE ->
`Math.Max(0, 0 - 1) = 0` -> terme NUL. Ce probe le CONFRONTE.

MONTAGE (fixture nommee `MDA_FIXTURE`, reutilisable ; board MC1_67, seed 909) :
  - `votanChampion` (u79) reste a son SPAWN (1,0). **NE JAMAIS LE DEPLACER** : un `act move`
    consomme son mouvement, et 1222 devient alors ILLEGALE
    (`MassDriverAcceleratorAbility$$GetDynamicInvalidTargetReason` rend invalide quand
    `GetPossibleMoveTiles` est vide -- MESURE : `abilityTargets` passe de 1 a 0 cible).
    (1,0) est un coin a 3 voisins : (0,0), (1,1), (2,0) -- (2,0) reste LIBRE (chemin de charge).
  - cible `tauCrisis` (u77) en (3,1) : distance 2. 1222 est ILLEGALE sur une cible ADJACENTE
    (`abilityReason` -> `TargetIsNotAdjacent`, MESURE), il faut donc d >= 2. La cible n'a AUCUN
    ennemi adjacent -> le residu `MakeDamagePredictions` (splash sur `GetAdjacentAttackTargets`)
    est inerte, donc hors confond.
  - appats ALLIES `necroWarden` (u83) et `bloodIntercessor` (u87) : loin (5,7)/(5,6) pour n=0,
    puis (1,1) et (0,0) -- ADJACENTS a Kimm -- pour n=1 puis n=2.
  - `ultraCalgar` (u81) et `astraOrdnance` (u85) FIGES loin (6,7)/(6,6) dans TOUS les bras : leurs
    auras (`RitesOfBattle_ExtraDmg*`, `SpotterReworked_ExtraDamage`) modifient `pairUtility(69)` et
    seraient un confond -- MESURE : deplacer Calgar pres de Kimm fait passer pair69 de 22.02 a 37.95.
  - **le passif de Kimm `ModifiedExoarmour` est RETIRE du seed BC** (`PassiveAbilities: []`).
    MOTIF : son playbook `IdunBattle.AI.Playbook.Loki.ModifiedExoarmourPlaybook` porte un terme de
    TUILE `ModifiedExoarmour_LikesMovingPerTile` (= 5, cle AJOUTEE par ce build) que le port n'a PAS
    -- il vaut `5 x longueur du chemin` sur toute tuile de deplacement et fausserait toute
    comparaison entre une action jouee sur place et une action jouee apres deplacement. Le terme
    sous test ne lit ni ce passif ni aucun stat : le retirer est un CONTROLE de montage, pas une
    modification du mecanisme. Le bras `--passive-on` rejoue le scenario AVEC le passif.
  - `--unit-stat votanChampion:Damage=<D>` est le CURSEUR qui met 1222 et l'attaque normale 69 a
    egalite. `Damage` ne touche PAS 1222 (`DirectDamage` a partir des variables d'ability) --
    MESURE : `pairUtility(1222)` est bit-identique sur tout le balayage.

VERDICTS RENDUS :
  V1 le natif est INVARIANT en n (0/1/2) aux deux `Damage` encadrant sa bascule ;
  V2 le moteur (terme porte a 0) est d'accord avec le natif dans les 6 cellules ;
  V3 SENSIBILITE : le moteur PORTANT la formule heritee `W x n` DIVERGE des n=1 au Damage haut
     -- donc un terme de +5 aurait ete VISIBLE, et son absence est une mesure, pas un angle mort ;
  V4 largeur en UTILITE de la fenetre de bascule natif (pente `pairUtility(69,(3,0))`).

Usage :
    python probe_27_r1_massdriver_custom.py --build          # fixture + scenario de reference
    python probe_27_r1_massdriver_custom.py --build --passive-on
    python probe_27_r1_massdriver_custom.py --build --scan 3400,3500,3600
ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOGS = ROOT / "logs"
SEED_BC = LOGS / "bc_mda.json"                 # catalog_inject brut
SEED_BC_NP = LOGS / "bc_mda_nopassive.json"    # + PassiveAbilities vide (controle de montage)
STATE = LOGS / "rs_27r1_mda.json"

BOARD = "MC1_67"
SEED = 909
# Les ids d'entite dependent du plateau (nombre de points de spawn) : ils sont RESOLUS par
# `visualId` a chaque build (`_resolve_units`), jamais figes -- sur `C1_02` ils valent 49..59 la ou
# `MC1_67` rend 77..87. Les valeurs ci-dessous sont celles de la fixture de reference (MC1_67/909).
VID_CASTER = "votanChampion"   # SPAWN -- jamais deplace
VID_TARGET = "tauCrisis"
VID_AURA1, VID_AURA2 = "ultraCalgar", "astraOrdnance"     # porteurs d'aura de degat : figes loin
VID_BAIT1, VID_BAIT2 = "necroWarden", "bloodIntercessor"  # les deux leviers d'adjacence

CASTER = 79
TARGET = 77
AURA1, AURA2 = 81, 85
BAIT1, BAIT2 = 83, 87

KIMM_SPAWN = (1, 0)
ENEMY_TILE = "3,1"
AURA_FAR = {AURA1: "6,7", AURA2: "6,6"}
BAIT_FAR = {BAIT1: "5,7", BAIT2: "5,6"}
BAIT_ADJ = {BAIT1: "1,1", BAIT2: "0,0"}        # deux des trois voisins de (1,0) ; (2,0) reste libre

NORMAL = 69
MDA = 1222
# Les deux `Damage` qui ENCADRENT la bascule native, mesures par bisection (pas de 25) :
D_LOW, D_HIGH = 3525, 3550
D_LOW_PASSIVE, D_HIGH_PASSIVE = 900, 1000      # bras `--passive-on` : autre point d'equilibre
ATTACK_TILE = (3, 0)           # tuile d'attaque choisie par le natif pour 69 au Damage haut


# ------------------------------------------------------------------ harnais runner
def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _move(rid: int, unit: int, to: str) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", to,
          "--state-file", str(STATE), "--runner", str(rid)])


def _resolve_units(rid: int) -> None:
    """Re-lie les six roles a leurs ids d'entite REELS (par `visualId`). Sans cela, une fixture
    portee sur un autre plateau adresse des unites qui n'existent pas -- et tous les `act move`
    echouent en silence."""
    global CASTER, TARGET, AURA1, AURA2, BAIT1, BAIT2
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    by_vid = {u.get("visualId"): u.get("id") for u in (dv.get("units") or [])}
    want = (VID_CASTER, VID_TARGET, VID_AURA1, VID_AURA2, VID_BAIT1, VID_BAIT2)
    missing = [v for v in want if by_vid.get(v) is None]
    if missing:
        raise SystemExit("unites absentes du runner : %s (roster incomplet sur ce plateau ?)"
                         % missing)
    CASTER, TARGET = by_vid[VID_CASTER], by_vid[VID_TARGET]
    AURA1, AURA2 = by_vid[VID_AURA1], by_vid[VID_AURA2]
    BAIT1, BAIT2 = by_vid[VID_BAIT1], by_vid[VID_BAIT2]


def _positions(rid: int) -> dict:
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("id")] = (p.get("col"), p.get("row"))
    return out


def _assert_placed(rid: int, want) -> None:
    """Un `act move` REFUSE ne leve rien : l'unite reste ou elle est et le montage se degrade
    SILENCIEUSEMENT en un scenario ou tous les bras sont identiques -- l'invariance du natif y
    devient trivialement vraie, donc sans valeur. On refuse plutot que de mesurer du vide."""
    pos = _positions(rid)
    bad = [(u, to, pos.get(u)) for u, to in want
           if pos.get(u) != tuple(int(x) for x in to.split(","))]
    if bad:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s"
                         % ["u%s voulu=%s obtenu=%s" % (u, to, got) for u, to, got in bad])


def ensure_seed_bcs() -> None:
    """Seed BC augmentee de `votanChampion` (hors pool), + sa variante SANS le passif de Kimm."""
    if not SEED_BC.exists():
        subprocess.run([sys.executable, "catalog_inject.py", "--units", "votanChampion",
                        "--out", str(SEED_BC)], cwd=str(HERE), check=True)
    if not SEED_BC_NP.exists():
        bc = json.loads(SEED_BC.read_text(encoding="utf-8"))
        for u in bc["Units"]:
            if u.get("Id") == "votanChampion":
                u["PassiveAbilities"] = []
        SEED_BC_NP.write_text(json.dumps(bc), encoding="utf-8")


# ------------------------------------------------------------------ geometrie DERIVEE (--auto)
#
# La fixture de reference fige ses tuiles (MC1_67 / seed 909). Pour GENERALISER a un autre plateau,
# `derive_geometry` les RE-DERIVE du board vivant : elle part de la tuile de SPAWN de Kimm (jamais
# deplacee), prend ses voisins WALKABLE via `boardGraph` (adjacence NATIVE, pas hexgeo), en reserve
# UN comme chemin de charge et transforme les autres en emplacements d'appat, puis choisit une tuile
# ennemie a distance hex 2. Les memes invariants sont EXIGES qu'en dur, sinon on refuse de mesurer.
def derive_geometry(rid: int) -> dict:
    import hexgeo
    bg = L._rpc("boardGraph", [{"runnerId": rid}])
    tiles = bg.get("tiles") or []
    by_id = {t.get("id"): t for t in tiles}
    walk = {(t.get("col"), t.get("row")): bool(t.get("walkable")) for t in tiles}
    pos = _positions(rid)
    kimm = pos.get(CASTER)
    ktile = next((t for t in tiles if (t.get("col"), t.get("row")) == kimm), None)
    if ktile is None:
        raise SystemExit("tuile de spawn de Kimm introuvable au boardGraph")
    neigh = [(by_id[i]["col"], by_id[i]["row"]) for i in (ktile.get("neighbours") or [])
             if i in by_id and by_id[i].get("walkable")]
    if len(neigh) < 3:
        raise SystemExit("spawn de Kimm a %d voisin(s) walkable : il en faut >= 3 (2 appats + 1 "
                         "chemin de charge) -- changer de board/seed" % len(neigh))
    # Choix de la tuile ennemie : distance 2 (1222 refuse une cible adjacente), ET il doit rester
    # AU MOINS UN voisin de Kimm adjacent a elle -- c'est la tuile d'attaque de l'attaque NORMALE,
    # qui doit rester LIBRE. Sans cette contrainte, un appat vient se poser dessus et prive le duel
    # de son concurrent : le natif bascule alors sur 1222 pour une raison PUREMENT geometrique.
    # MESURE (board C1_02, geometrie naive) : natif [69, 1222, 1222] -- l'appat occupait (0,1),
    # la tuile ou le natif voulait aller frapper.
    others = set(neigh) | {kimm}
    enemy, baits_pool, attack_tile = None, [], None
    for p, w in sorted(walk.items()):
        if not w or hexgeo.distance(kimm, p) != 2 or p in others:
            continue
        attack_tiles = [q for q in neigh if hexgeo.distance(q, p) == 1]
        free_baits = [q for q in neigh if q not in attack_tiles]
        if attack_tiles and len(free_baits) >= 2:
            enemy, baits_pool, attack_tile = p, free_baits, attack_tiles[0]
            break
    if enemy is None:
        raise SystemExit("aucune tuile a distance 2 du spawn de Kimm qui laisse >= 1 tuile d'attaque "
                         "libre ET >= 2 emplacements d'appat -- changer de board/seed")
    baits = {BAIT1: baits_pool[0], BAIT2: baits_pool[1]}
    far = [p for p, w in sorted(walk.items())
           if w and hexgeo.distance(kimm, p) >= 6 and p != enemy]
    if len(far) < 4:
        raise SystemExit("moins de 4 tuiles walkable a distance >= 6 : impossible de parquer les "
                         "auras et les appats hors du montage")
    return {"kimm": kimm, "enemy": enemy, "baits": baits, "attack_tile": attack_tile,
            "aura_far": {AURA1: far[0], AURA2: far[1]},
            "bait_far": {BAIT1: far[2], BAIT2: far[3]}}


def _t(p) -> str:
    return "%d,%d" % (int(p[0]), int(p[1]))


def _geom_ref() -> dict:
    """Geometrie de REFERENCE (MC1_67 / seed 909), figee ; `--auto` la remplace par
    `derive_geometry`. Construite APRES `_resolve_units` -- les cles sont des ids d'entite."""
    return {"kimm": KIMM_SPAWN,
            "enemy": tuple(int(x) for x in ENEMY_TILE.split(",")),
            "attack_tile": ATTACK_TILE,
            "baits": {BAIT1: (1, 1), BAIT2: (0, 0)},
            "aura_far": {AURA1: (6, 7), AURA2: (6, 6)},
            "bait_far": {BAIT1: (5, 7), BAIT2: (5, 6)}}


def build_fixture(damage: int, with_passive: bool = False, board: str = BOARD, seed: int = SEED,
                  geom: dict | None = None, unit_stats=None) -> tuple[int, dict]:
    """`MDA_FIXTURE` -- monte le runner et POSE les positions (cf. docstring du module).
    Kimm n'est JAMAIS deplacee : elle reste sur sa tuile de spawn, sinon 1222 devient illegale.
    `geom=None` + `board/seed` non standard -> la geometrie est DERIVEE du board vivant.
    `unit_stats` = patchs `--unit-stat` SUPPLEMENTAIRES (`"VisualId:Champ=Valeur"`), ADDITIFS au
    `Damage` du curseur -- c'est le levier qui fait varier une entree de CONFIG (niveau de passif,
    multiplicateur de rarete) sans toucher a la geometrie du montage (#312)."""
    ensure_seed_bcs()
    extra = []
    for s in (unit_stats or ()):
        extra += ["--unit-stat", str(s)]
    _run(["build", "--seed", str(seed), "--board", board,
          "--seed-bc", str(SEED_BC if with_passive else SEED_BC_NP),
          "--p-units", "votanChampion,ultraCalgar,necroWarden,astraOrdnance,bloodIntercessor",
          "--a-units", "tauCrisis", "--state-file", str(STATE),
          "--unit-stat", "votanChampion:Damage=%d" % damage] + extra)
    rid = _runner_id()
    _resolve_units(rid)                       # ids d'entite reels AVANT tout `act move`
    if geom is None:
        geom = _geom_ref() if (board == BOARD and seed == SEED) else derive_geometry(rid)
    for u, to in geom["aura_far"].items():
        _move(rid, u, _t(to))
    _move(rid, TARGET, _t(geom["enemy"]))
    for u, to in geom["bait_far"].items():
        _move(rid, u, _t(to))
    want = ([(TARGET, _t(geom["enemy"]))]
            + [(u, _t(p)) for u, p in geom["aura_far"].items()]
            + [(u, _t(p)) for u, p in geom["bait_far"].items()])
    _assert_placed(rid, want)
    if _positions(rid).get(CASTER) != tuple(geom["kimm"]):
        raise SystemExit("Kimm n'est plus sur son spawn %s -- 1222 serait illegale" % (geom["kimm"],))
    return rid, geom


def set_arm(rid: int, n: int, geom: dict) -> None:
    """n = nombre d'ALLIES ADJACENTS a Kimm (0, 1 ou 2)."""
    order = [BAIT1, BAIT2]
    want = [(u, _t(geom["baits"][u] if i < n else geom["bait_far"][u]))
            for i, u in enumerate(order)]
    for u, to in want:
        _move(rid, u, to)
    _assert_placed(rid, want)


# ------------------------------------------------------------------ mesures
def native_choice(rid: int):
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    prop = next((u.get("proposed") for u in (dr.get("units") or [])
                 if u.get("unitId") == CASTER), []) or []
    ab = next((m.get("abilityType") for m in prop if m.get("cls") == "ActiveAbilityMessage"), None)
    mv = next((((m.get("to") or {}).get("col"), (m.get("to") or {}).get("row"))
               for m in prop if m.get("cls") == "MoveUnitMessage"), None)
    return ab, mv


def native_pair(rid: int, ability: int, tile) -> float | None:
    r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": CASTER, "targetId": TARGET,
                                "abilityType": ability, "col": tile[0], "row": tile[1]}])
    return r.get("utility")


def _adjacent_friend_count(ctx) -> int:
    """Le compte que la formule HERITEE (case-27) attribuait au terme : amis adjacents a Kimm."""
    from engine import battle_query as bq
    here = ctx.origin
    return 0 if here is None else bq.count_adjacent(here, ctx.fpos, ctx.elev_by_pos)


def engine_choice(rid: int, mutate_inherited: bool = False):
    """Decision MOTEUR. `mutate_inherited` remplace le terme porte par la formule HERITEE
    `W x |amis adjacents|` -- c'est la MUTATION ADVERSARIALE qui prouve la SENSIBILITE du montage."""
    import engine_validate as EV
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)                    # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, CASTER, wt, predictor)
    pb = PB.REGISTRY.get(MDA)
    ported = pb.calculate_custom_utility(ctx, ctx.origin, TARGET, MDA)
    n_adj = _adjacent_friend_count(ctx)

    orig = type(pb).calculate_custom_utility
    if mutate_inherited:
        w = wt.sub("ActiveAbilities", "MassDriverAccelerator_AdjacentFriendly")
        type(pb).calculate_custom_utility = (
            lambda self, c, tile, target, ab: float(_adjacent_friend_count(c)) * w)
    try:
        a = EV.engine_decide(sid, rid, dv, mov_by_unit, CASTER, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    return a.get("ability"), a.get("target"), ported, n_adj


# ------------------------------------------------------------------ scenarios
def run_cell(rid: int, damage: int, n: int, rows: dict, geom: dict) -> None:
    set_arm(rid, n, geom)
    nab, nmv = native_choice(rid)
    eab, etgt, ported, n_adj = engine_choice(rid)
    mab, _, _, _ = engine_choice(rid, mutate_inherited=True)
    rows[(damage, n)] = {"native": nab, "native_move": nmv, "engine": eab,
                         "engine_mutated": mab, "ported": ported, "n_adj": n_adj}
    print("   n=%d (amis adjacents mesures=%d) : natif ab=%-5s mv=%-8s | moteur ab=%-5s "
          "(terme porte=%.1f) | moteur MUTE `W x n` ab=%-5s"
          % (n, n_adj, nab, nmv, eab, ported, mab))


def scenario(damages, with_passive: bool, board: str = BOARD, seed: int = SEED,
             attack_tile=None):
    """Rend `(rows, dernier runnerId)`. Chaque `build` REMPLACE le scope du meme `--state-file`,
    donc un seul runner reste vivant a la fin -- c'est celui-la que l'appelant dispose."""
    rows: dict = {}
    rid, geom = None, None
    for d in damages:
        rid, geom = build_fixture(d, with_passive=with_passive, board=board, seed=seed, geom=geom)
        print("--- Damage=%d runner=%d board=%s seed=%d passif=%s ---"
              % (d, rid, board, seed, "ON" if with_passive else "RETIRE"))
        print("    geometrie : Kimm=%s ennemi=%s appats=%s"
              % (geom["kimm"], geom["enemy"], list(geom["baits"].values())))
        for n in (0, 1, 2):
            run_cell(rid, d, n, rows, geom)
        # Ancre de la pente (V4) : la tuile de melee reservee par la geometrie (voisin de Kimm
        # ADJACENT a l'ennemi), IDENTIQUE a tous les `Damage`. Prendre la tuile effectivement
        # choisie par le natif melangerait DEUX tuiles differentes et la "pente" ne voudrait rien
        # dire (mesure : 22.52 au lieu de 0.4458 sur la fixture de reference).
        at = tuple(attack_tile) if attack_tile else tuple(geom["attack_tile"])
        rows[(d, "pair69")] = native_pair(rid, NORMAL, at)
        rows[(d, "pair1222")] = native_pair(rid, MDA, geom["kimm"])
        print("   natif pairUtility(69,%s)=%r  pairUtility(1222,%s)=%r"
              % (at, rows[(d, "pair69")], geom["kimm"], rows[(d, "pair1222")]))
    rows["geom"] = geom
    return rows, rid


def bisect_flip(board: str, seed: int, with_passive: bool, lo: int = 200, hi: int = 24000,
                tol: int = 25) -> tuple[int, int]:
    """Cherche l'encadrement du `Damage` ou le natif BASCULE de 1222 vers l'attaque normale, a n=0.
    C'est ce qui rend la fixture portable : sur un autre plateau, le point d'equilibre du duel n'est
    pas le meme, et un `Damage` fige mesurerait un bras hors zone de bascule (donc rien)."""
    def picks_mda(d: int) -> bool:
        rid, geom = build_fixture(d, with_passive=with_passive, board=board, seed=seed)
        set_arm(rid, 0, geom)
        ab, _ = native_choice(rid)
        print("    bisect Damage=%-6d -> natif %s" % (d, ab))
        return ab == MDA
    if not picks_mda(lo):
        raise SystemExit("a Damage=%d le natif ne prend deja PLUS 1222 : borne basse trop haute" % lo)
    if picks_mda(hi):
        raise SystemExit("a Damage=%d le natif prend ENCORE 1222 : borne haute trop basse" % hi)
    while hi - lo > tol:
        mid = (lo + hi) // 2
        if picks_mda(mid):
            lo = mid
        else:
            hi = mid
    return lo, hi


def verdicts(rows: dict, damages, strict_agreement: bool = True) -> int:
    """`strict_agreement=False` (bras `--passive-on`) : V2/V3 deviennent INFORMATIFS. Avec le passif,
    `ModifiedExoarmourPlaybook` ajoute au terme de TUILE natif `ModifiedExoarmour_LikesMovingPerTile
    x longueur du chemin` (poids = 5, cle AJOUTEE par ce build) que le port n'a pas -> le moteur et
    le natif peuvent choisir des actions differentes pour une raison ETRANGERE au terme sous test.
    Ce qui reste PROBANT dans ce bras, c'est V1 : le natif ne bouge pas quand n varie."""
    print("\n=== VERDICTS ===")
    ok = True
    # V0 -- l'appat ne doit JAMAIS occuper la tuile ou le natif veut aller frapper : sinon le bras
    # n>=1 prive le duel de son concurrent et le natif bascule pour une raison GEOMETRIQUE.
    bait_tiles = set(map(tuple, (rows.get("geom") or {}).get("baits", {}).values()))
    clash = [(d, rows[(d, 0)]["native_move"]) for d in damages
             if rows[(d, 0)]["native_move"] and tuple(rows[(d, 0)]["native_move"]) in bait_tiles]
    ok = ok and not clash
    print("  V0 tuile d'attaque du natif (bras n=0) hors des emplacements d'appat %s : %s"
          % (sorted(bait_tiles),
             "OK" if not clash else "COLLISION %s -- le montage confond adjacence et geometrie, "
                                    "il ne conclut RIEN" % clash))
    # V1 -- le natif est INVARIANT en n
    for d in damages:
        got = [rows[(d, n)]["native"] for n in (0, 1, 2)]
        inv = (len(set(got)) == 1)
        ok = ok and inv
        print("  V1 Damage=%-6d natif(n=0,1,2) = %s -> %s"
              % (d, got, "INVARIANT" if inv else "VARIE (le terme n'est PAS nul)"))
    # V1b -- les deux Damage encadrent bien une bascule (sinon le montage ne teste rien)
    if len(damages) >= 2:
        lo, hi = damages[0], damages[-1]
        bracket = rows[(lo, 0)]["native"] != rows[(hi, 0)]["native"]
        ok = ok and bracket
        print("  V1b bascule natif entre Damage=%d (%s) et %d (%s) : %s"
              % (lo, rows[(lo, 0)]["native"], hi, rows[(hi, 0)]["native"],
                 "OUI -- le duel est bien a l'equilibre" if bracket
                 else "NON -- montage hors zone de bascule, ne conclut RIEN"))
    # V2 -- accord moteur/natif dans toutes les cellules
    bad = [(d, n) for d in damages for n in (0, 1, 2)
           if rows[(d, n)]["engine"] != rows[(d, n)]["native"]]
    if strict_agreement:
        ok = ok and not bad
    print("  V2%s accord moteur<->natif : %s"
          % ("" if strict_agreement else " [INFO]",
             "%d/%d cellules" % (len(damages) * 3 - len(bad), len(damages) * 3)
             + (" -- DIVERGE sur %s" % bad if bad else "")))
    # V3 -- sensibilite : la formule HERITEE aurait ete VISIBLE
    seen = [(d, n) for d in damages for n in (1, 2)
            if rows[(d, n)]["engine_mutated"] != rows[(d, n)]["native"]]
    if strict_agreement:
        ok = ok and bool(seen)
    print("  V3%s sensibilite (moteur MUTE `W x n` vs natif) : %s"
          % ("" if strict_agreement else " [INFO]",
             "DIVERGE sur %s -> un terme de +5 aurait ete OBSERVABLE" % seen if seen
             else "aucune divergence -> le montage NE PROUVE RIEN"))
    # V3b -- le compte d'amis adjacents varie bien d'un bras a l'autre
    counts = sorted({rows[(damages[0], n)]["n_adj"] for n in (0, 1, 2)})
    ok = ok and (len(counts) >= 2)
    print("  V3b configurations d'adjacence distinctes : n_adj = %s %s"
          % (counts, "OK" if len(counts) >= 2 else "-- ecart NUL, ne conclut RIEN"))
    # V4 -- largeur en utilite de la fenetre de bascule
    if len(damages) >= 2:
        p_lo, p_hi = rows[(damages[0], "pair69")], rows[(damages[-1], "pair69")]
        if p_lo is not None and p_hi is not None:
            width = abs(p_hi - p_lo)
            print("  V4 fenetre de bascule : Damage %d -> %d = %.4f point(s) d'utilite ; "
                  "borne sur |C(n=2) - C(n=0)| < %.4f (la formule heritee predisait 10)"
                  % (damages[0], damages[-1], width, width))
    # V5 -- le terme porte est nul partout
    nz = [(d, n) for d in damages for n in (0, 1, 2) if rows[(d, n)]["ported"] != 0.0]
    ok = ok and not nz
    print("  V5 terme porte == 0 partout : %s" % ("OUI" if not nz else "NON sur %s" % nz))
    print("\n%s" % ("PROBE OK -- le terme custom de 1222 est un NO-OP natif, le port le mirroir"
                    if ok else "PROBE KO -- voir les lignes ci-dessus"))
    print("(pense a disposer le runner : python rl_duel.py dispose --state-file %s)" % STATE)
    return 0 if ok else 1


def _opt(argv, name, default=None):
    for a in argv:
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    if name in argv:
        i = argv.index(name)
        return argv[i + 1] if i + 1 < len(argv) else None
    return default


def main() -> int:
    argv = sys.argv[1:]
    with_passive = "--passive-on" in argv
    board = _opt(argv, "--board", BOARD)
    seed = int(_opt(argv, "--seed", str(SEED)))
    scan = _opt(argv, "--scan")
    if "--auto" in argv:
        # GENERALISATION : re-derive la geometrie ET le point d'equilibre sur le plateau demande.
        print("=== --auto : bisection du point de bascule natif (board=%s seed=%d) ==="
              % (board, seed))
        lo, hi = bisect_flip(board, seed, with_passive)
        damages = [lo, hi]
        print("=== encadrement trouve : Damage %d (1222) / %d (normale) ===" % (lo, hi))
    elif scan:
        damages = [int(x) for x in scan.split(",")]
    else:
        # Le passif change la puissance de l'attaque normale ET ajoute son terme de tuile :
        # le point d'equilibre du duel n'est PAS le meme -> son propre encadrement, mesure.
        damages = [D_LOW_PASSIVE, D_HIGH_PASSIVE] if with_passive else [D_LOW, D_HIGH]
    rows, _rid = scenario(damages, with_passive, board=board, seed=seed)
    return verdicts(rows, damages, strict_agreement=not with_passive)


if __name__ == "__main__":
    sys.exit(main())
