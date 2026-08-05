"""#478 -- le CLEAVE de la face COMBAT : `<X>_NormalAttackAbility$$Execute<X>` frappe des cibles
ADDITIONNELLES, et le port ne le faisait NULLE PART (0 site, ecart mesure 3104 / 3632 PV, #446-r3b).

## Ce que ce probe MESURE, et pourquoi il ne peut pas se fitter

Un REPLAY-DIFF d'attaque normale (meme etat, meme MT cale par `dumpRng`), lu **DELTA DE PV PAR
UNITE** -- pas un total. La decomposition est donc structurelle, en DEUX etages separes :

    etage 1 -- COMBIEN de cibles additionnelles ?   -> `set` des unites qui perdent des PV
                                                       hors la cible PRIMAIRE
    etage 2 -- COMBIEN sur chacune ?                -> le delta, unite par unite

Un total qui tomberait juste avec un mauvais decoupage (2 cibles a 1500 au lieu d'1 a 3000) est
donc VU. Et la comparaison porte sur le `per_hit` de l'attaque primaire en plus, ce qui interdit de
compenser un cleave faux par une primaire fausse.

## Le SECOND CAS DISCRIMINANT -- deux geometries, trois cardinaux

La geometrie hex borne le cardinal : deux tuiles ADJACENTES ont exactement DEUX voisins communs,
donc un porteur au contact de sa cible a **au plus 2** cibles additionnelles. Les deux regimes
montes ici couvrent les trois cas :

  * `--regime one` (le layout de #446-r3b) : `A` sur l'UNIQUE voisin commun -> `Fealty` et
    `TalonOfHorus` cleavent **1** cible ; `adeptMorvenn`, place sur un voisin NON adjacent a `A`,
    en cleave **0** -- un temoin NEGATIF gratuit, sur la meme passe ;
  * `--regime two` : les DEUX voisins communs occupes, pour les deux porteurs greffes -> **2**
    cibles chacun.

Sans le second regime, « le port rend le bon total » ne distinguerait pas un selecteur porte d'une
constante calee sur le premier montage.

## Le montage -- ce qui ECHOUE EN SILENCE si on l'oublie

⚠ `--unit-stat "X:PassiveAbilities=[<id>]"` NE SUFFIT PAS : `Fealty` et `TalonOfHorus` sont absentes
de `BC.Abilities.PassiveAbilities` du seed et `refresh_ability_configs` ne les derive pas. La face
COMBAT lit `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(0xc/0xd)` dans
`<X>_NormalAttackAbility$$GetAdditionalDamageBehaviour` -> config nulle -> « system error » au cast
(meme verrou que #226/#237). Le montage passe donc par `catalog_inject.write_grafted_seed_bc`
(foyer PARTAGE avec `probe_446_r3b_fealty_talon_asymetrie.write_seed_bc`).

`adeptMorvenn` porte `RighteousRepugnance` NATURELLEMENT : aucune greffe, c'est le TEMOIN.

Usage :
    python scripts/python/probe_478_cleave_additional_targets.py --state-file <ABSOLU>.json
        [--regime one|two] [--board MC1_67] [--seed 4463111] [--runner N]

ASCII only. Garde jumelle : `scripts/python/tests/engine/test_478_cleave_live.py`.
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
from engine.entities.pathfinding.board import Board              # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType         # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent      # noqa: E402
from engine.runner.messages import AttackUnitMessage              # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister            # noqa: E402
from engine.runner.runner import Runner                           # noqa: E402
from engine.runner.snapshot import load_state                     # noqa: E402

import probe_446_r3b_fealty_talon_asymetrie as R3B                # noqa: E402

BOARD = R3B.BOARD
SEED = R3B.SEED
HP = R3B.HP

TARGET = R3B.TARGET          # `astraBullgryn` -- la cible PRIMAIRE

#: `(visualId, passif, TriggeredAbilityType, ActiveAbilityType de l'attaque normale, greffe ?)`.
#: Les deux familles d'ids passent par leur ENUM (regle « un ENTIER qui DESIGNE passe par un ENUM »).
CARRIERS = (
    ("ultraTitus", "Fealty",
     int(TriggeredAbilityType.Fealty), int(ActiveAbilityType.Fealty_NormalAttack), True),
    ("blackAbaddon", "TalonOfHorus",
     int(TriggeredAbilityType.TalonOfHorus), int(ActiveAbilityType.TalonOfHorus_NormalAttack), True),
    ("adeptMorvenn", "RighteousRepugnance",
     int(TriggeredAbilityType.RighteousRepugnance),
     int(ActiveAbilityType.RighteousRepugnance_NormalAttack), False),
    # `templAggressor` << Burchard >> porte `Boltstorm` NATURELLEMENT (porteur confirme par #446-r1).
    ("templAggressor", "Boltstorm",
     int(TriggeredAbilityType.Boltstorm), int(ActiveAbilityType.Boltstorm_NormalAttack), False),
)

#: Les unites ADDITIONNELLES disponibles (ennemies du caster, alliees de la cible primaire). Les
#: QUATRE sont AU POOL au rank courant (`rl_duel build --list-pool`) -- un `visualId` hors pool fait
#: echouer le build en `rc=2`, jamais silencieusement.
ADDTS = ("necroWarden", "necroDestroyer", "necroSpyder", "astraCreed")

MontageError = R3B.MontageError


# --------------------------------------------------------------------------- geometrie OFFLINE

def layout_one(elev, playable):
    """Le layout de #446-r3b : `T`, `A` (UNIQUE voisin commun), et les TROIS porteurs.
    Cardinaux attendus : `Fealty` 1, `TalonOfHorus` 1, `RighteousRepugnance` 0."""
    lay = R3B.find_layout(elev, playable)
    if lay is None:
        return None
    return {"T": lay["T"], "A": [lay["A"]], "C": lay["C"],
            "want": {R3B.CLEAVERS[0]: 1, R3B.CLEAVERS[1]: 1, CARRIERS[2][0]: 0}}


def layout_two(elev, playable):
    """Le SECOND regime : les DEUX voisins communs occupes pour CHACUN des deux porteurs greffes.

    Construction, purement geometrique (aucune constante de board) : on cherche une tuile `T` dont
    l'anneau natif porte SIX voisins ordonnes en cycle `n0..n5` ; on pose alors

        n0 = porteur 1   n1 = A1   n2 = A2       (A1, A2 = les 2 voisins communs de n0 et T)
        n3 = porteur 2   n4 = A3   n5 = A4       (A3, A4 = les 2 voisins communs de n3 et T)

    ⚠ Le cycle est celui de l'ADJACENCE REELLE (`bq.is_adjacent`, porte d'elevation `|delta| < 2`),
    pas l'ordre `hexgeo.neighbors` : sur un board a relief, deux voisins consecutifs en coordonnees
    peuvent ne PAS etre adjacents. On ORDONNE donc l'anneau par adjacence mutuelle, et on refuse la
    tuile si le cycle n'est pas complet -- jamais un layout « presque bon » qui rendrait un cardinal
    de 1 la ou on en attend 2.

    Cardinaux attendus : `Fealty` 2 et `TalonOfHorus` 2."""
    cells = sorted(playable)
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    for t in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        ring = [q for q in hexgeo.neighbors(t[0], t[1])
                if q in playable and bq.is_adjacent(t, q, elev)]
        if len(ring) != 6:
            continue
        cyc = _order_ring(ring, elev)
        if cyc is None:
            continue
        c1, a1, a2, c2, a3, a4 = cyc
        return {"T": t, "A": [a1, a2, a3, a4],
                "C": {R3B.CLEAVERS[0]: c1, R3B.CLEAVERS[1]: c2},
                "want": {R3B.CLEAVERS[0]: 2, R3B.CLEAVERS[1]: 2}}
    return None


def _order_ring(ring, elev):
    """Ordonne les six tuiles de `ring` en CYCLE d'adjacence reelle (chaque tuile adjacente a la
    suivante, la derniere a la premiere). `None` si le cycle n'existe pas."""
    rest = list(ring)
    cyc = [rest.pop(0)]
    while rest:
        nxt = next((q for q in rest if bq.is_adjacent(cyc[-1], q, elev)), None)
        if nxt is None:
            return None
        rest.remove(nxt)
        cyc.append(nxt)
    return cyc if bq.is_adjacent(cyc[-1], cyc[0], elev) else None


def layout_boltstorm(elev, playable):
    """Le regime RANGED -- `Boltstorm`, dont les DEUX gates sont INVERSEES (cleave sur
    `IsMelee == 0`, fold primaire sur `IsRangedPosition`).

    `templAggressor` porte `Boltstorm` NATURELLEMENT (aucune greffe). Il est place a distance hex
    **2** de la cible : assez loin pour que `FindAttackWeapon` choisisse l'arme a DISTANCE (la gate
    du cleave) et que `IsMeleePosition` soit FAUX (la gate du fold primaire, donc `IsRangedPosition`
    VRAI), assez pres pour que les cibles additionnelles restent dans la portee de l'arme.

    Deux cibles additionnelles : les deux voisins communs de `T` et d'une tuile de reference, tous
    deux a distance <= portee du caster. Le cardinal EFFECTIF est re-verifie par `stage` contre la
    geometrie NATIVE -- ce constructeur ne fait que proposer."""
    rng = weapon_range_of("templAggressor")           # `Boltstorm` : Bolter, portee 2
    cells = sorted(playable)
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    for t in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        ring = [q for q in hexgeo.neighbors(t[0], t[1])
                if q in playable and bq.is_adjacent(t, q, elev)]
        if len(ring) < 3:
            continue
        # la tuile du caster : a distance hex 2 de `T` (donc NON adjacente -> arme A DISTANCE et
        # `IsRangedPosition` vrai), et d'ou les deux cibles additionnelles sont DANS LA PORTEE et
        # NON OBSCURCIES -- les trois gates du selecteur de `Boltstorm`.
        far = [q for q in cells
               if hexgeo.distance(q, t) == 2 and not bq.is_adjacent(q, t, elev)]
        for c in far:
            adds = [q for q in ring
                    if q != c and hexgeo.distance(q, c) <= rng
                    and not bq.is_target_tile_obscured(c, q, elev)]
            if len(adds) < 2:
                continue
            # `want` = 0 : cf. `_expected_cardinal` -- l'ancre `Owner@0x30`. Ce regime exerce donc
            # la gate RANGED du **FOLD PRIMAIRE** (`IsRangedPosition`), pas le cleave.
            return {"T": t, "A": adds[:2], "C": {"templAggressor": c},
                    "want": {"templAggressor": 0}}
    return None


def layout_rr(elev, playable):
    """Le regime qui exerce le CLEAVE de `RighteousRepugnance` -- l'autre surcharge de selecteur
    (ancre = l'UNITE, pas une tuile), et le seul porteur qui ait AUSSI un fold primaire.

    Meme geometrie que `one`, porteurs PERMUTES : `adeptMorvenn` prend une tuile ADJACENTE a `A`
    (cardinal 1 **et** fold primaire), `ultraTitus` la tuile eloignee (cardinal 0). C'est le montage
    qui a montre que l'ORDRE des deux volets compte : le port, quand il ne jouait que le cleave,
    appliquait a `A` les rolls `502, 506, 557` que le natif applique a la cible PRIMAIRE."""
    lay = layout_one(elev, playable)
    if lay is None:
        return None
    C = dict(lay["C"])
    C["adeptMorvenn"], C["ultraTitus"] = C["ultraTitus"], C["adeptMorvenn"]
    return {"T": lay["T"], "A": lay["A"], "C": C,
            "want": {"adeptMorvenn": 1, "blackAbaddon": 1, "ultraTitus": 0}}


LAYOUTS = {"one": layout_one, "two": layout_two, "rr": layout_rr, "boltstorm": layout_boltstorm}


# --------------------------------------------------------------------------- build

def build_args(lay: dict, bc_path: str, board: str = BOARD) -> list:
    """Les arguments `rl_duel build` du montage -- FOYER UNIQUE, partage par le probe et la garde."""
    carriers = [v for v in lay["C"]]
    addts = list(ADDTS[:len(lay["A"])])
    hp = [f"{v}:Health={HP},RemainingHealth={HP}" for v in carriers + [TARGET] + addts]
    places = []
    for v, tile in lay["C"].items():
        places += ["--place", f"{v}:{tile[0]},{tile[1]}"]
    places += ["--a-place", f"{TARGET}:{lay['T'][0]},{lay['T'][1]}"]
    for v, tile in zip(addts, lay["A"]):
        places += ["--a-place", f"{v}:{tile[0]},{tile[1]}"]
    return ["--board", board, "--seed-bc", bc_path,
            "--p-units", ",".join(carriers),
            "--a-units", ",".join([TARGET] + addts),
            *places, "--unit-stat", ";".join(hp)]


def build(state_file: str, board: str, seed: str, lay: dict) -> int:
    bc_path = os.path.splitext(state_file)[0] + ".seedbc.json"
    R3B.write_seed_bc(bc_path)                 # greffe Fealty + TalonOfHorus (DEUX ecritures)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", state_file,
            *build_args(lay, bc_path, board)]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-900:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


# --------------------------------------------------------------------------- oracle geometrique

def _CLEAVE_ENTRY(passive: str):
    from engine.runner.abilities.loki.additional_targets import NORMAL_ATTACK_CLEAVES
    return NORMAL_ATTACK_CLEAVES[passive]


def weapon_range_of(vis: str) -> int:
    """Portee de l'arme A DISTANCE du kit -- l'argument `Direct(attackWeapon.Range)` du selecteur de
    `Boltstorm`. Lu du gameconfig (le montage place le caster a distance, donc `FindAttackWeapon`
    choisit bien cette arme-la). `0` pour les porteurs melee, ou l'oracle ne l'utilise pas."""
    import gameconfig as GC
    ws = (GC.unit(vis) or {}).get("weapons") or []
    # une arme SANS cle `Range` est l'arme de MELEE (`WeaponProfile.Range` = `Nullable<int>` vide,
    # cf. `IdunBattle.Entities.Formulas.AttackWeaponRangeFormula$$Calculate` : `IsMelee ? 1 : Range`)
    rs = [int(w["Range"]) for w in ws if w.get("Range")]
    return max(rs) if rs else 0


def _expected_cardinal(passive: str, cpos, tpos, apos: list, elev, wrange: int) -> int:
    """L'ORACLE du cardinal, ECRIT A LA MAIN depuis les quatre `<X>Ability$$GetAdditionalTargets`
    LUS -- il ne partage AUCUNE ligne avec le port qu'il juge, sinon il ne jugerait rien.

    Les quatre arbres, developpes en geometrie (toutes les unites de `apos` sont ENNEMIES du caster
    et ALLIEES de la cible, par construction du montage) :

      * `Fealty`      : adjacent(a, caster) ET adjacent(a, cible)                   [ - cible ]
      * `TalonOfHorus`: adjacent(a, caster) ET adjacent(a, cible)
      * `RighteousRepugnance` : idem (l'autre surcharge, meme geometrie sur des unites MONO-hex)
      * `Boltstorm`   : **ZERO**, et ce n'est pas une paresse -- son arbre ancre sur `Owner@0x30`
        (`SurroundingEnemies(Owner, range)` ET `Unobscured(Owner, ...)`), un slot que
        l'`AbilityEntities` d'une ATTAQUE NORMALE ne renseigne pas. MESURE : dans un montage ou les
        trois gates geometriques sont satisfaites (deux ennemis adjacents a la cible, a portee, non
        obscurcis), le natif ne frappe AUCUNE cible additionnelle -- la ou le MEME montage fait
        cleaver `Fealty`/`TalonOfHorus`, qui ancrent sur `Caster@0x48`. Residu `#478-r4`.
        L'oracle rend donc `0` **par la RE**, pas par constat : si un jour le natif se met a
        frapper, c'est CE zero qui rougira, et il faudra reprendre l'ancre.
    """
    if passive == "Boltstorm":
        _ = (cpos, tpos, apos, elev, wrange)     # gates geometriques SANS OBJET tant que Owner nul
        return 0
    return sum(1 for a in apos
               if bq.is_adjacent(a, tpos, elev) and bq.is_adjacent(a, cpos, elev))


# --------------------------------------------------------------------------- montage

def stage(rpc, rid: int, lay: dict, elev: dict) -> dict:
    """Installe et ATTESTE tout ce dont la mesure depend -- toute attestation manquante LEVE."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mine = [u for u in units if u.get("ctrl")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    myplayer = mine[0].get("owner")
    uid, want_ab = {}, {}
    for v, passive, tid, ab, _g in CARRIERS:
        if v not in lay["C"]:
            continue
        u = next((x for x in mine if x.get("visualId") == v), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {v} absent du roster controle")
        uid[v] = u["id"]
        want_ab[v] = ab
    addts = list(ADDTS[:len(lay["A"])])
    for v in [TARGET] + addts:
        u = next((x for x in units if x.get("owner") != myplayer and x.get("visualId") == v), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {v} absent du roster adverse")
        uid[v] = u["id"]

    pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units if u.get("pos")}
    want_pos = {uid[v]: tuple(t) for v, t in lay["C"].items()}
    want_pos[uid[TARGET]] = tuple(lay["T"])
    for v, t in zip(addts, lay["A"]):
        want_pos[uid[v]] = tuple(t)
    bad = {u: (pos.get(u), w) for u, w in want_pos.items() if pos.get(u) != w}
    if bad:
        raise MontageError(f"montage NON INSTALLE : placement {bad} (obtenu, voulu)")

    tp = pos[uid[TARGET]]
    passive_of = {v: p for v, p, _t, _a, _g in CARRIERS}
    # (a) LE REGIME D'ARME voulu, porteur par porteur. La gate du cleave est
    #     `attackWeapon.IsMelee`, et elle est INVERSEE pour `Boltstorm` : exiger « adjacent » pour
    #     tous ferait mesurer `Boltstorm` dans la branche ou il ne cleave PAS.
    for v in lay["C"]:
        adj = bq.is_adjacent(pos[uid[v]], tp, elev)
        want_melee = _CLEAVE_ENTRY(passive_of[v]).cleaves_when_melee
        if bool(adj) != want_melee:
            raise MontageError(
                f"regime d'ARME NON INSTALLE : {v} {pos[uid[v]]} est "
                f"{'adjacent' if adj else 'a distance'} de la cible {tp}, or son cleave part sur "
                f"{'IsMelee' if want_melee else '!IsMelee'} -- la gate n'est pas exercee")
    # (b) LE CARDINAL VOULU, calcule sur la GEOMETRIE NATIVE par un ORACLE ECRIT A LA MAIN depuis
    #     la RE (`_expected_cardinal`), jamais depuis le port qu'on teste. C'est ce chiffre-la que
    #     le natif ET le port devront rendre, et c'est lui qui separe les regimes.
    got = {v: _expected_cardinal(passive_of[v], pos[uid[v]], tp,
                                 [pos[uid[a]] for a in addts], elev, weapon_range_of(v))
           for v in lay["C"]}
    if got != lay["want"]:
        raise MontageError(f"regime NON INSTALLE : cardinaux geometriques {got}, voulus "
                           f"{lay['want']} -- le second cas discriminant n'existe pas")

    # (c) L'ATTAQUE NORMALE LIVE, porteur par porteur : `1220`/`1205` prouvent que la greffe a mordu
    #     (sans elle, `ultraTitus`/`blackAbaddon` rendraient la generique 69) ; `1182` que le temoin
    #     est bien la sous-classe surchargeante. On lit l'id que le CAST utilisera (l'ability de
    #     `kind == "normal"` de `decisionView`), pas une table -- meme source que `_combat_replay`.
    for v in lay["C"]:
        u = next(x for x in mine if x.get("visualId") == v)
        norm = next((a for a in (u.get("abilities") or []) if a.get("kind") == "normal"), None)
        if norm is None or int(norm.get("id") or -1) != want_ab[v]:
            raise MontageError(f"montage NON INSTALLE : l'attaque normale live de {v} est "
                               f"{None if norm is None else norm.get('id')}, attendu {want_ab[v]} "
                               f"-- la sous-classe n'est PAS instanciee")
    # (d) LE VOLET « FOLD PRIMAIRE » attendu, DERIVE de la table de RE (`primary_fold_when_melee
    #     _position`) et de la geometrie -- pas du resultat. Il ne sert pas de verdict (celui-la
    #     compare la ventilation par coup du natif a celle du port) mais d'ATTESTATION : il dit
    #     lequel des deux volets ce montage exerce, et fait echouer un montage qui n'en exercerait
    #     aucun.
    from engine.runner.abilities.loki.additional_targets import NORMAL_ATTACK_CLEAVES
    fold = {}
    for v, passive, _tid, _ab, _g in CARRIERS:
        if v not in lay["C"]:
            continue
        e = NORMAL_ATTACK_CLEAVES[passive]
        melee_pos = bq.is_adjacent(pos[uid[v]], tp, elev)     # `IsMeleePosition` == AreUnitsInMelee
        fold[v] = (e.primary_fold_when_melee_position is not None
                   and bool(melee_pos) == e.primary_fold_when_melee_position)
    if not any(fold.values()) and not any(lay["want"].values()):
        raise MontageError(f"montage VIDE : ni fold primaire ({fold}) ni cible additionnelle "
                           f"({lay['want']}) -- la mesure n'exercerait aucun des deux volets")
    return {"rid": rid, "uid": uid, "pos": pos, "addts": addts, "want": dict(lay["want"]),
            "fold": fold, "ab": want_ab, "tpos": tp, "carriers": list(lay["C"])}


# --------------------------------------------------------------------------- replay-diff

def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _hp_by_id(dv) -> dict:
    return {u["id"]: int(u.get("hp") or 0) for u in (dv.get("units") or []) if u.get("id") is not None}


def _native_hits(a0) -> dict:
    """`{targetId: [Amount, ...]}` -- les coups NATIFS de l'action, dans l'ORDRE d'emission, et
    la liste des `Active_Ability_Type` en regard.

    C'est le troisieme etage de la decomposition : le delta de PV dit COMBIEN, la ventilation par
    coup dit COMMENT. Elle a deja tranche une fois -- c'est elle qui a montre que le port appliquait
    a la CIBLE ADDITIONNELLE les rolls (`502, 506, 557`) que le natif applique a la cible PRIMAIRE,
    donc qu'il MANQUAIT un volet et non qu'il se trompait de montant."""
    out, kinds = {}, {}
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" not in td:
            continue
        t = td.get("Target_Id")
        out.setdefault(t, []).append(td.get("Amount"))
        kinds.setdefault(t, []).append(td.get("Active_Ability_Type"))
    return {"amounts": out, "kinds": kinds}


def replay(rpc, st: dict, vis: str) -> dict:
    """Rejoue l'attaque normale de `vis` sur la cible PRIMAIRE, LIVE **et** OFFLINE (meme etat, meme
    MT), et rend les DELTAS DE PV PAR UNITE des deux cotes.

    C'est la decomposition par etage : `cible additionnelle -> delta` est un DICT, jamais un total.
    """
    rid = st["rid"]
    cid, tid = st["uid"][vis], st["uid"][TARGET]
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        raise MontageError("boardGraph indisponible -- l'etat offline serait sans geometrie")
    # ⚠ `ability_states` est OBLIGATOIRE ici, et l'oublier ne RATE PAS : il MENT. Sans lui,
    # `UnitContext.passive_abilities` reste `None` (canal muet) et
    # `engine.services.custom_normal_attack` retombe sur le KIT gameconfig -- lequel ne connait PAS
    # les greffes de ce montage. Le port conclurait alors « pas de substitution, pas de cleave »
    # sur des porteurs que le natif fait bel et bien cleaver. C'est le vice #419-r1-tr14-r5 exactement.
    ast = rpc("unitAbilityStates", {"runnerId": rid}, 90)
    if not (isinstance(ast, dict) and (ast.get("units") or [])):
        raise MontageError(f"unitAbilityStates ne rend aucune unite : {str(ast)[:200]} -- le canal "
                           f"des passifs MESURES serait muet et le dispatch retomberait sur le KIT")
    board = Board(bg["tiles"], adjacency="native_sym")
    state = load_state(dv, ob, snap, board=board, ability_states=ast)
    ae = state.get_entity(cid)
    if ae is None or ae.get_component(StatsComponent) is None:
        raise MontageError(f"{vis} sans StatsComponent offline -- l'etat n'est pas chargeable")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and s0.get("ok")):
        raise MontageError(f"dumpRng indisponible : {str(s0)[:200]}")
    state.rng = _seed_rng(s0)

    # Le BUNDLE d'etat PRE-CAST. Il rend les contre-epreuves GRATUITES : le port peut etre rejoue
    # autant de fois qu'on veut sur ce meme etat (meme MT), avec une mutation differente a chaque
    # fois, sans re-monter un runner ni re-jouer le cast LIVE (qui, lui, n'a lieu qu'UNE fois --
    # il consomme le tour et mute l'etat).
    bundle = {"dv": dv, "ob": ob, "snap": snap, "bg": bg, "ast": ast, "rng": s0,
              "cid": cid, "tid": tid, "uid": dict(st["uid"])}

    before = _hp_by_id(dv)
    off_before = {i: (state.get_entity(i).get_component(HealthComponent).hp
                      if state.get_entity(i) is not None
                      and state.get_entity(i).get_component(HealthComponent) is not None else None)
                  for i in before}

    res = rpc("applyAction", {"runnerId": rid, "captureEvents": True,
                              "action": {"kind": "ability", "casterId": cid, "targetId": tid,
                                         "abilityType": st["ab"][vis]}}, 120) or {}
    a0 = (res.get("actions") or [{}])[0]
    if res.get("ok") is False or a0.get("ok") is False or a0.get("error"):
        raise MontageError(f"cast live REFUSE pour {vis} : {str(res)[:400]}")
    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    after = _hp_by_id(dv2)

    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(cid, tid))
    rr = runner.damage_handler.last or {}
    off_after = {i: (state.get_entity(i).get_component(HealthComponent).hp
                     if state.get_entity(i) is not None
                     and state.get_entity(i).get_component(HealthComponent) is not None else None)
                 for i in before}

    def _deltas(b, a):
        return {i: int(b[i]) - int(a[i]) for i in b
                if b.get(i) is not None and a.get(i) is not None and int(b[i]) != int(a[i])}

    nat = _deltas(before, after)
    off = _deltas(off_before, off_after)
    by_vis = {v: k for k, v in st["uid"].items()}
    nh = _native_hits(a0)
    off_fold = rr.get("primary_fold") or None
    return {"vis": vis, "ability": st["ab"][vis], "caster": cid, "target": tid, "bundle": bundle,
            "want_cardinal": st["want"][vis],
            "want_primary_fold": st["fold"][vis],
            "nat": {by_vis.get(i, i): d for i, d in nat.items()},
            "off": {by_vis.get(i, i): d for i, d in off.items()},
            "nat_primaire": nat.get(tid, 0), "off_primaire": off.get(tid, 0),
            "nat_addts": {by_vis.get(i, i): d for i, d in nat.items() if i != tid},
            "off_addts": {by_vis.get(i, i): d for i, d in off.items() if i != tid},
            # ventilation par COUP sur la cible PRIMAIRE : les coups d'ARME portent l'
            # `ActiveAbilityType` concret, ceux du FOLD portent `None` (`AttackDamageBehaviour`).
            "nat_primaire_hits": nh["amounts"].get(tid, []),
            "nat_primaire_kinds": nh["kinds"].get(tid, []),
            # `per_hit` = les coups d'ARME ; `additional_hits.per_hit` = les coups du canal #179
            # (`ExecuteAdditionalHitsWithDamageProfileTypeOperation`, SOUS-OPERATIONS jouees APRES
            # les coups d'arme). Les deux portent l'`ActiveAbilityType` CONCRET cote natif -- ils
            # appartiennent a l'attaque NORMALE, pas au fold. Les omettre faisait rougir
            # `blackAbaddon` (natif 6 coups, port 5) alors que le delta de PV etait exact.
            "off_primaire_arme_hits": (list(rr.get("per_hit") or [])
                                       + list((rr.get("additional_hits") or {}).get("per_hit")
                                              or [])),
            "off_primaire_fold_hits": list(((off_fold or {}).get("attack") or {}).get("per_hit")
                                           or []),
            "off_cleave_events": [(by_vis.get(e.get("target"), e.get("target")),
                                   (e.get("attack") or {}).get("per_hit"))
                                  for e in (rr.get("additional_targets") or [])]}


def port_only(bundle: dict) -> dict:
    """Rejoue l'attaque normale OFFLINE sur le bundle d'etat PRE-CAST, et rend
    `{"primaire": <PV>, "addts": {visualId: <PV>}, "arme": [...], "fold": [...]}`.

    Sert aux CONTRE-EPREUVES : on mute le port (registre vide, fold greffe par analogie, ordre des
    deux volets inverse...) puis on rappelle cette fonction. Aucun runner, aucun cast live -- donc
    une contre-epreuve coute ZERO montage, et rien n'empeche d'en jouer quatre."""
    board = Board(bundle["bg"]["tiles"], adjacency="native_sym")
    state = load_state(bundle["dv"], bundle["ob"], bundle["snap"], board=board,
                       ability_states=bundle["ast"])
    state.rng = _seed_rng(bundle["rng"])
    before = {i: (state.get_entity(i).get_component(HealthComponent).hp
                  if state.get_entity(i) is not None
                  and state.get_entity(i).get_component(HealthComponent) is not None else None)
              for i in _hp_by_id(bundle["dv"])}
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(bundle["cid"], bundle["tid"]))
    rr = runner.damage_handler.last or {}
    after = {i: (state.get_entity(i).get_component(HealthComponent).hp
                 if state.get_entity(i) is not None
                 and state.get_entity(i).get_component(HealthComponent) is not None else None)
             for i in before}
    by_vis = {v: k for k, v in bundle["uid"].items()}
    d = {i: int(before[i]) - int(after[i]) for i in before
         if before.get(i) is not None and after.get(i) is not None and before[i] != after[i]}
    return {"primaire": d.get(bundle["tid"], 0),
            "addts": {by_vis.get(i, i): v for i, v in d.items() if i != bundle["tid"]},
            "arme": list(rr.get("per_hit") or []),
            "fold": list(((rr.get("primary_fold") or {}).get("attack") or {}).get("per_hit") or [])}


def verdict(rows: list) -> list:
    """Les assertions NOMMEES, ETAGE PAR ETAGE. Rend la liste des echecs.

    Quatre etages, du plus grossier au plus fin -- et c'est l'ordre qui interdit de fitter :
      0. l'attaque PRIMAIRE a bien eu lieu, et son delta de PV est le meme des deux cotes ;
      1. le CARDINAL des cibles additionnelles est celui que la GEOMETRIE impose, et les MEMES
         unites sont frappees ;
      2. le MONTANT par cible additionnelle, unite par unite ;
      3. la VENTILATION PAR COUP sur la cible primaire -- `coups d'arme + coups de FOLD` du port
         doit egaler, dans l'ordre, la suite des `Amount` natifs. C'est cet etage-la qui a trouve
         le volet manquant : un total juste avec un mauvais decoupage y rougit."""
    bad = []
    for r in rows:
        v = r["vis"]
        # etage 0 -- l'attaque PRIMAIRE : sans elle, un accord sur le cleave ne vaudrait rien
        if r["nat_primaire"] <= 0:
            bad.append(f"{v} : la cible PRIMAIRE ne perd aucun PV cote NATIF -- rien n'a eu lieu")
        if r["off_primaire"] != r["nat_primaire"]:
            bad.append(f"{v} : PRIMAIRE port {r['off_primaire']} != natif {r['nat_primaire']}")
        # etage 1 -- le CARDINAL
        if len(r["nat_addts"]) != r["want_cardinal"]:
            bad.append(f"{v} : le NATIF frappe {len(r['nat_addts'])} cible(s) additionnelle(s), "
                       f"la geometrie en attendait {r['want_cardinal']} -- {r['nat_addts']}")
        if set(r["off_addts"]) != set(r["nat_addts"]):
            bad.append(f"{v} : cibles additionnelles port {sorted(r['off_addts'])} != natif "
                       f"{sorted(r['nat_addts'])}")
        # etage 2 -- le MONTANT par cible
        for k, d in r["nat_addts"].items():
            if r["off_addts"].get(k) != d:
                bad.append(f"{v} : cible additionnelle {k} -- port {r['off_addts'].get(k)} PV, "
                           f"natif {d} PV")
        # etage 3 -- la VENTILATION PAR COUP sur la cible primaire (arme PUIS fold)
        got = list(r["off_primaire_arme_hits"]) + list(r["off_primaire_fold_hits"])
        if got != list(r["nat_primaire_hits"]):
            bad.append(f"{v} : ventilation par COUP sur la cible primaire -- port {got} "
                       f"(arme {r['off_primaire_arme_hits']} + fold {r['off_primaire_fold_hits']}) "
                       f"!= natif {r['nat_primaire_hits']} (kinds {r['nat_primaire_kinds']})")
        # etage 3bis -- le fold ATTENDU par la RE est-il celui qui a mordu ? Les coups natifs de
        # FOLD sont ceux dont l'`Active_Ability_Type` est nul (`AttackDamageBehaviour`), par
        # opposition aux coups d'ARME qui portent l'`ActiveAbilityType` concret.
        nat_fold_hits = sum(1 for k in r["nat_primaire_kinds"] if k is None)
        if bool(nat_fold_hits) != bool(r["want_primary_fold"]):
            bad.append(f"{v} : le NATIF applique {nat_fold_hits} coup(s) de FOLD a la cible "
                       f"primaire, la table de RE en attendait "
                       f"{'un paquet' if r['want_primary_fold'] else 'AUCUN'}")
    return bad


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--regime", default="one", choices=tuple(LAYOUTS))
    ap.add_argument("--runner", type=int, default=None, help="reutilise un runner deja monte")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    elev, playable = R3B.board_geometry(args.board)
    lay = LAYOUTS[args.regime](elev, playable)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucun layout '{args.regime}' sur {args.board}")
    print(f"board {args.board} seed {args.seed} | regime {args.regime}")
    print(f"  T={lay['T']} A={lay['A']} porteurs={lay['C']} cardinaux voulus={lay['want']}")

    # UN ETAT VIERGE PAR PORTEUR -- et ce n'est pas du confort. Mesure du premier passage : joues a
    # la SUITE sur le meme runner, les deux premiers casts sont bit-exacts (2493/2493, 3756/3756) et
    # le TROISIEME diverge (natif 7830, port 2081) avec un `necroWarden` qui REGAGNE 6000 PV --
    # un canal d'etat que les casts precedents ont ouvert, sans rapport avec le cleave. Un montage
    # qui laisse deriver l'etat fait donc rougir la mesure pour une cause qui n'est pas la sienne.
    # `rl_duel build` sur le MEME state-file REMPLACE le runner : le budget partage reste a 1.
    rows = []
    for vis in list(lay["C"]):
        rid = args.runner or build(args.state_file, args.board, args.seed, lay)
        st = stage(rpc, rid, lay, elev)
        print(f"  runner {rid} -- porteur isole {vis}")
        rows.append(replay(rpc, st, vis))
    for r in rows:
        print(f"  [{r['vis']:<13} attaque normale {r['ability']}] cardinal voulu "
              f"{r['want_cardinal']} | fold primaire attendu {r['want_primary_fold']}")
        print(f"      NATIF primaire={r['nat_primaire']:<7} addts={r['nat_addts']}")
        print(f"      PORT  primaire={r['off_primaire']:<7} addts={r['off_addts']}")
        print(f"      NATIF coups primaire {r['nat_primaire_hits']} kinds {r['nat_primaire_kinds']}")
        print(f"      PORT  coups arme {r['off_primaire_arme_hits']} + fold "
              f"{r['off_primaire_fold_hits']}")
        print(f"      PORT  cleave : {r['off_cleave_events']}")
    bad = verdict(rows)
    for b in bad:
        print(f"  [ECHEC] {b}")
    print("[478] " + ("OK -- natif et port frappent les MEMES cibles pour les MEMES montants"
                      if not bad else f"{len(bad)} ECHEC(S)"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
