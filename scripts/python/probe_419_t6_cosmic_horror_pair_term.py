"""#419 tranche 6 -- MONTAGE NOMME de la face ATTACK de `CosmicHorror` (1277), et mesure natif
contre port.

`IdunBattle.AI.Playbook.Loki.CosmicHorrorPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
rend `GetUtilityValue("COSMICHORROR_StepOnDecoyToAttack")` quand l'unite qui OCCUPE la tuile
d'attaque (`case.CasterPosition.MainTile`, `UtilityAttackCase@+0x18`) porte `UnitTrait.Decoy`
(0x41d) et est AMIE du caster (`case.Caster`, `@+0x10`) -- 0 sinon. C'est donc un terme de TUILE,
pas de cible : il ne bouge qu'en changeant la tuile d'attaque, jamais en changeant l'ennemi vise.

## Comment le regime s'installe -- SANS injection ni greffe

Le porteur `genesPatriarch` (HERO) est AU POOL (`rl_duel build --list-pool`), et son propre kit
FABRIQUE le decoy dont le playbook a besoin : `CosmicHorror` (face COMBAT) « places a decoy on the
hex of that enemy » quand le Patermine defait un ennemi. Le montage est donc entierement dans le
regime naturel du jeu :

    1. un Patermine tue une proie fragile a l'ecart -> un DECOY apparait sur l'hex de la proie ;
    2. la cible de mesure est AMENEE contre ce decoy (elle etait garee LOIN pendant le kill --
       cf. « pourquoi PARK » plus bas) ;
    3. on mesure la MEME paire (caster, cible) depuis TROIS tuiles d'attaque toutes adjacentes a
       la cible : `D` = l'hex du decoy, `F` = un hex LIBRE, `C` = l'hex du CASTER lui-meme.

Les trois tuiles sont un regime a trois occupants distincts, et c'est ce qui rend le montage
discriminant : `D` porte un leurre, `F` ne porte rien, `C` porte une unite AMIE QUI N'EST PAS un
leurre. Un port qui oublierait le gate `HasTrait` passerait `D` et `F` et ne se trahirait que sur
`C` ; un port qui lirait la tuile de la CIBLE au lieu de celle du caster passerait `F` et `C`.

## Les DEUX regimes du gate `IsFriend` -- `--regime friend` et `--regime enemy`

Le gate d'amitie ne s'exerce dans le sens PASSANT qu'avec un leurre AMI. Pour le prendre dans
l'autre sens il faut un leurre ENNEMI, ce que le jeu sait produire de la meme facon : un Patermine
ADVERSE tue une de NOS unites, et le leurre qu'il laisse appartient a SON camp.

  `--regime friend` (defaut) -- le caster est le tueur ; `D` porte un leurre AMI -> terme = 10.
  `--regime enemy`           -- un second Patermine, ADVERSE, tue notre proie ; `D` porte un
                               leurre ENNEMI -> terme = 0, alors que TOUT le reste de la
                               geometrie est identique. C'est la seule mesure qui distingue
                               `IsFriend` de « il y a un leurre ».

⚠ POURQUOI `PARK` : la meme ability pose, au meme moment, `Suppressed` sur les ennemis ENTOURANT
le defunt -- avec une CHANCE (60 % au palier haut ; `DisableRandomness` vaut `false` dans le seed
BC). Tuer la proie a cote de la cible de mesure rendrait donc l'etat de la cible ALEATOIRE d'un
run a l'autre. On tue la proie a l'ecart (`>= 3` de la cible), puis on amene la cible : le tirage
n'a alors aucun sujet, et le montage est reproductible.

`EXPECTED` est pose ICI, en dur, depuis le decompile (le poids BC lu quand la tuile porte un
leurre AMI, 0 partout ailleurs) : il n'est PAS relu du port, sinon la mesure ne trancherait rien.

⚠ NON COUVERT par ce montage : le regime « occupant Decoy NON Steppable » (aucune unite du
catalogue ne porte `Decoy` sans `Steppable`, il n'existe donc pas de donnee pour distinguer les
deux gates), et le regime « tuile d'attaque occupee par un STEPPABLE NON leurre » (les deux seuls
porteurs de `Steppable` du catalogue Genestealer portent aussi `Decoy` ; la tuile `C` en est le
substitut le plus proche -- occupant ami, non leurre).

Usage :
    python scripts/python/probe_419_t6_cosmic_horror_pair_term.py --state-file <chemin ABSOLU>
        [--regime friend|enemy] [--mutants]

ASCII only. Garde jumelle :
`scripts/python/tests/engine/test_419_t6_cosmic_horror_pair_term_live.py`.
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
import probe_124_line_elevation_decision as P124                 # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait          # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402

BOARD = "MC1_67"
SEED = "51277"
CASTER = "genesPatriarch"       # HERO AU POOL ; `CosmicHorror` est son SEUL triggered (kit = {1277})
# ⚠ Ni la proie ni la cible ne doivent INVOQUER : un summon adverse (mesure : `astraCreed` ->
# `astraSmnKell`) occupe des tuiles du montage et brouille la geometrie. Les deux ids ci-dessous
# sont pris dans la liste des unites du pool dont AUCUNE ability ne mentionne summon/spawn/place.
PREY = "tauAunShi"              # la proie : tuee a l'ecart, son hex devient le DECOY
TARGET = "astraBullgryn"        # la cible de mesure : amenee APRES le kill, doit survivre

ABILITY = int(TriggeredAbilityType.CosmicHorror)             # 1277
DECOY_TRAIT_ID = int(UnitTrait.Decoy)                        # 1053 = 0x41d (canal combatSnapshot)
WEIGHT_KEY = "COSMICHORROR_StepOnDecoyToAttack"
EPS = 1e-4                      # Fix64 natif contre float du port
HP_BIG = 400000                 # le caster et la cible ne doivent JAMAIS mourir
HP_PREY = 1                     # la proie meurt en UNE attaque (`Health` ET `RemainingHealth`)

_STATS = (f"{CASTER}:Health={HP_BIG},RemainingHealth={HP_BIG};"
          f"{TARGET}:Health={HP_BIG},RemainingHealth={HP_BIG};"
          f"{PREY}:Health={HP_PREY},RemainingHealth={HP_PREY},Armor=0,FixedArmor=0")

# `friend` : la proie est ADVERSE, le caster la tue -> leurre AMI.
# `enemy`  : la proie est A NOUS, un SECOND Patermine (adverse) la tue -> leurre ENNEMI.
BUILD_ARGS = {
    "friend": ["--board", BOARD, "--p-units", CASTER,
               "--a-units", f"{PREY},{TARGET}", "--unit-stat", _STATS],
    "enemy": ["--board", BOARD, "--p-units", f"{CASTER},{PREY}",
              "--a-units", f"{CASTER},{TARGET}", "--unit-stat", _STATS],
}

# Quelles contre-epreuves un regime EXERCE reellement -- mesure #419-t6, pas une intention.
# En `enemy` le port rend deja 0 sur les trois tuiles, donc `target_tile` (qui ne peut que RETIRER
# le terme) n'a rien a deplacer : son inertie y est le comportement CORRECT, et l'exiger mordante
# ferait rougir la garde pour une cause etrangere. `no_trait` mord dans les deux regimes (la tuile
# `C` porte un occupant AMI non leurre) et `invert_friend` aussi (il retire le terme en `friend`,
# il l'ajoute en `enemy`).
MUST_BITE = {
    "friend": ("no_trait", "invert_friend", "target_tile"),
    "enemy": ("no_trait", "invert_friend"),
}


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- oracles

def pair_native(rpc, rid, cid, tgt, ab, tile) -> float:
    r = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                            "abilityType": ab, "col": tile[0], "row": tile[1]}, 90)
    v = (r or {}).get("utility")
    if not isinstance(v, (int, float)):
        raise MontageError(f"pairUtility natif indisponible pour {tile} / cible {tgt}: {r}")
    return float(v)


def pair_port(ctx, ab, tgt, tile) -> float:
    cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
    if cand is None:
        raise MontageError(f"le port ne produit AUCUNE action depuis {tile} sur {tgt}")
    return float(cand["u"])


# --------------------------------------------------------------------------- geometrie

def native_neighbours(t: tuple, cells: set, elev: dict) -> list:
    """Voisins de `t` au sens NATIF (`IdunBattle.Core.Services.TileQuery.
    u003CIterateAdjacentTilesu003Ed__8$$MoveNext`) : ring-1 hex AVEC la porte `|delta elev| < 2`.
    Sur un board a relief, `hexgeo.distance == 1` ne vaut PAS adjacence native."""
    return [q for q in hexgeo.neighbors(t[0], t[1]) if q in cells and bq.is_adjacent(t, q, elev)]


def find_layout(cells: list, elev: dict, walk: dict) -> dict | None:
    """Cherche `(Ck, Pk, Tt, PARK, PARK2)` :

      `Pk`   -- l'hex ou la proie meurt, donc la future tuile du DECOY (`D`) ;
      `Ck`   -- la tuile du TUEUR pendant le kill (voisine NATIVE de `Pk` : l'attaque est en
                MELEE) ET la tuile du CASTER a la mesure -- elle doit donc etre AUSSI voisine
                native de `Tt`, sans quoi le natif refuse l'attaque depuis `C` et la troisieme
                ligne de mesure ne compare plus rien ;
      `Tt`   -- la tuile finale de la cible, voisine NATIVE de `Pk` et de `Ck` ;
      `PARK` -- ou la cible attend PENDANT le kill : a `>= 3` de `Pk` (aucun ennemi
                « surrounding » le defunt -> aucun tirage `Suppressed`) ;
      `PARK2`-- ou le TUEUR se gare apres coup dans le regime `enemy` (il n'est pas le caster).

    ⚠ La tuile TEMOIN `F` n'est PAS choisie ici : elle l'est APRES le montage, dans les tuiles
    d'action REELLES de l'oracle (`ctx.action_tiles`). Mesure #419-t6 : un `F` derive hors-ligne
    d'un chemin `_gated_path` (qui ignore les OCCUPANTS et le cout reel) tombe couramment hors du
    movable set, et `pairUtility` le refuse -- le montage echouait alors sur une tuile pourtant
    correcte geometriquement."""
    cs = set(cells)
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    for pk in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        nb_pk = native_neighbours(pk, cs, elev)
        if len(nb_pk) < 2:
            continue
        for ck in nb_pk:
            for tt in nb_pk:
                if tt == ck or not bq.is_adjacent(ck, tt, elev):
                    continue
                if len(native_neighbours(tt, cs, elev)) < 3:
                    continue                       # il faut de la place pour `D`, `C` et `F`
                far = [q for q in cells if hexgeo.distance(q, pk) >= 3 and q not in (pk, ck, tt)
                       and P124._gated_path(tt, q, walk, elev)]
                if len(far) < 2:
                    continue
                return {"Ck": ck, "Pk": pk, "Tt": tt, "PARK": far[0], "PARK2": far[-1]}
    return None


def pick_witness_tile(action_tiles, pos: dict, t_pos, d_tile, c_tile, elev) -> tuple | None:
    """La tuile d'attaque TEMOIN `F` : dans les tuiles d'action REELLES de l'oracle, voisine
    NATIVE de la cible, LIBRE de tout occupant, distincte de `D` et de `C`. C'est le pendant
    EXACT de `D` a un seul fait pres -- l'occupant."""
    busy = set(pos.values())
    for t in action_tiles:
        if t in (d_tile, c_tile) or t in busy:
            continue
        if bq.is_adjacent(t, t_pos, elev):
            return t
    return None


def attest_layout(pos: dict, ids: dict, lay: dict, f_tile, elev: dict) -> None:
    """RE-MESURE la geometrie sur les positions LIVE et refuse si le regime voulu n'est pas celui
    installe -- l'adjacence est celle du NATIF (porte d'elevation comprise)."""
    p_c, p_t = pos.get(ids["C"]), pos.get(ids["T"])
    if p_c is None or p_t is None:
        raise MontageError(f"montage NON INSTALLE : position inconnue caster={p_c} cible={p_t}")
    d = lay["Pk"]
    checks = [
        ("caster sur Ck", p_c == lay["Ck"]),
        ("cible sur Tt", p_t == lay["Tt"]),
        ("D voisin NATIF de la cible", bq.is_adjacent(d, p_t, elev)),
        ("F voisin NATIF de la cible", bq.is_adjacent(f_tile, p_t, elev)),
        ("C voisin NATIF de la cible", bq.is_adjacent(p_c, p_t, elev)),
        ("D, F, C distinctes", len({d, f_tile, p_c}) == 3),
        ("F LIBRE", f_tile not in set(pos.values())),
        ("D OCCUPEE", d in set(pos.values())),
    ]
    bad = [name for name, ok in checks if not ok]
    if bad:
        raise MontageError(f"montage NON INSTALLE : contraintes violees {bad} -- "
                           f"caster={p_c} cible={p_t} D={d} F={f_tile}")


# --------------------------------------------------------------------------- montage

def _fresh_ctx(rpc, rid, cid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return dv, _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))


def _unit(dv, uid):
    return next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)


def _normal_ability(rpc, rid, uid) -> tuple:
    """(`abilityId` de l'attaque NORMALE de `uid`, cibles ce tour, cibles SANS bouger) --
    `abilityTargets`. `fromHere` est l'attestateur de LEGALITE du cast immediat : sans lui, un
    `applyAction` illegal est refuse SANS erreur exploitable et la boucle de kill tourne a vide."""
    r = rpc("abilityTargets", {"runnerId": rid, "unitId": uid}, 60) or {}
    for u in (r.get("units") or ()):
        if u.get("unitId") != uid:
            continue
        for a in (u.get("abilities") or ()):
            if a.get("kind") == "normal":
                return (a.get("abilityId"),
                        {t.get("targetId") for t in (a.get("targets") or ())},
                        {t.get("targetId") for t in (a.get("fromHere") or ())})
    return None, set(), set()


def _attest_decoy(rpc, rid, dv, pos_decoy, my_team) -> dict:
    """Le DECOY doit exister, etre VIVANT, occuper `pos_decoy` et porter `UnitTrait.Decoy`.
    Sans cette attestation, un terme manquant se lirait comme un bug de port alors que le regime
    ne serait tout simplement pas installe.

    ⚠ Le trait est lu au canal `combatSnapshot.units[].traits` (ids `UnitTrait` LUS de l'ECS,
    #267) et surtout PAS a `decisionView.units[].traits`, qui vaut `null` sur ce runner : une
    attestation batie dessus rendrait « pas un leurre » sur un montage pourtant correct. C'est
    aussi une source INDEPENDANTE du substrat que consomme le port (`_entity_traits`), donc un
    port aveugle aux traits ne pourrait pas se faire valider par sa propre cecite."""
    cs = rpc("combatSnapshot", {"runnerId": rid}, 90) or {}
    traits_by_eid = {u.get("entityId"): set(u.get("traits") or ())
                     for u in (cs.get("units") or ())}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        if not u.get("alive") or (p.get("col"), p.get("row")) != pos_decoy:
            continue
        traits = traits_by_eid.get(u.get("id"), set())
        return {"id": u.get("id"), "vis": u.get("visualId"), "team": u.get("team"),
                "trait_ids": sorted(traits), "is_decoy": DECOY_TRAIT_ID in traits,
                "is_friend": u.get("team") == my_team}
    raise MontageError(f"montage NON INSTALLE : AUCUNE unite vivante en {pos_decoy} apres le kill "
                       f"-- le decoy de `CosmicHorror` n'a pas ete pose")


def _kill_prey(sid, rpc, rid, killer_id, killer_owner, prey_id, lay, walk, elev,
               stage_prey) -> None:
    """Le tueur abat la proie -- DEPLACEMENT ET ATTAQUE DANS LE MEME TOUR.

    ⚠ Piege mesure : tout `endturn` rend la main a l'IA, qui ELOIGNE la proie. Il faut donc
    RE-PLACER (`_drive_to` compense) avant chaque tentative, et ne jamais laisser passer un tour
    entre le placement et le cast."""
    for _ in range(8):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        u = _unit(dv, prey_id)
        if u is None or not u.get("alive"):
            return
        P124._drive_to(sid, rid, walk, elev, stage_prey)
        P124._give_turn_back(sid, rid, killer_owner)
        ab, _all, here = _normal_ability(rpc, rid, killer_id)
        if ab is None:
            raise MontageError(f"montage NON INSTALLE : u{killer_id} n'a pas d'attaque normale")
        if prey_id not in here:
            _dv, pos = P124._positions(sid, rid)
            if pos.get(killer_id) != lay["Ck"]:
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": killer_id,
                    "to": {"col": lay["Ck"][0], "row": lay["Ck"][1]}}}, 60)
            ab, _all, here = _normal_ability(rpc, rid, killer_id)
        if prey_id in here:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": killer_id, "targetId": prey_id,
                "abilityType": ab}}, 120)
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            u = _unit(dv, prey_id)
            if u is None or not u.get("alive"):
                return
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    raise MontageError("montage NON INSTALLE : la proie a survecu a 8 tentatives du tueur "
                       "(cast jamais legal, ou degat insuffisant)")


def _stage(sid, rpc, rid: int, regime: str) -> dict:
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mine = [u for u in units if u.get("ctrl")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    myplayer = mine[0].get("owner")
    cid = next((u["id"] for u in mine if u.get("visualId") == CASTER), None)
    if cid is None:
        raise MontageError(f"montage NON INSTALLE : {CASTER} absent de mon roster")
    my_team = next((u.get("team") for u in mine if u.get("id") == cid), None)
    foes = [u for u in units if u.get("owner") != myplayer]
    tgt_id = next((u["id"] for u in foes if u.get("visualId") == TARGET), None)
    if tgt_id is None:
        raise MontageError(f"montage NON INSTALLE : {TARGET} absent du roster adverse")
    if regime == "friend":
        prey_id = next((u["id"] for u in foes if u.get("visualId") == PREY), None)
        killer_id, killer_owner = cid, myplayer
    else:
        prey_id = next((u["id"] for u in mine if u.get("visualId") == PREY), None)
        killer_id = next((u["id"] for u in foes if u.get("visualId") == CASTER), None)
        killer_owner = next((u.get("owner") for u in foes), None)
        if killer_id is None:
            raise MontageError(f"montage NON INSTALLE : pas de {CASTER} ADVERSE (regime enemy)")
    if prey_id is None:
        raise MontageError(f"montage NON INSTALLE : {PREY} absent (regime {regime})")

    # (a) LE PASSIF EST-IL DANS L'AbilitiesComponent du CASTER ? Sans 1277 dedans, le dispatcher
    #     ne l'itere pas et la mesure ne prouverait rien (moitie CABLAGE du patron #419).
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live_ids = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
    if ABILITY not in live_ids:
        raise MontageError(
            f"montage NON INSTALLE : {ABILITY} n'est PAS dans l'AbilitiesComponent de {CASTER} "
            f"-- triggered live lus = {sorted(set(live_ids))}")

    # (b) La geometrie, puis le DRIVE (jamais « bloque par le spawn »).
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    lay = find_layout(cells, elev, walk)
    if lay is None:
        raise MontageError("montage NON INSTALLE : aucune configuration (Ck,Pk,Tt,PARK) sur ce "
                           "board -- le regime a trois tuiles d'attaque ne serait pas installe")
    ids = {"C": cid, "P": prey_id, "T": tgt_id, "K": killer_id}
    # La proie sur `Pk` et la cible GAREE loin : c'est ce qui prive le tirage `Suppressed` de tout
    # sujet au moment du kill. Le tueur, lui, est amene par `_kill_prey` DANS le tour du cast --
    # le placer ici ne servirait a rien, l'IA deplacant la proie entre-temps.
    stage_prey = {prey_id: lay["Pk"], tgt_id: lay["PARK"]}
    if cid not in (prey_id, killer_id):
        # Regime `enemy` : le caster n'est pas le tueur -- il doit juste s'ECARTER, pour ne pas
        # occuper une tuile du montage NI se retrouver « surrounding » le defunt (le tirage
        # `Suppressed` frappe les ENNEMIS DU TUEUR, donc notre camp). Le BUT est une distance,
        # pas une tuile : exiger `PARK2` au pas pres fait echouer le montage pour rien (mesure
        # #419-t6 : arrive en (5,8) au lieu de (6,8), sans consequence sur le regime).
        P124._drive_to(sid, rid, walk, elev, {**stage_prey, cid: lay["PARK2"]})
    if not P124._drive_to(sid, rid, walk, elev, stage_prey):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement de kill incomplet -- voulu "
                           f"{stage_prey}, obtenu { {u: pos.get(u) for u in stage_prey} }")
    if cid not in (prey_id, killer_id):
        _dv, pos = P124._positions(sid, rid)
        if hexgeo.distance(pos.get(cid) or (99, 99), lay["Pk"]) < 2:
            raise MontageError(f"montage NON INSTALLE : le caster {pos.get(cid)} est adjacent au "
                               f"defunt {lay['Pk']} -- il serait sujet au tirage `Suppressed`")

    # (c) LE KILL -- c'est lui qui FABRIQUE le decoy (face COMBAT de la meme ability 1277).
    _kill_prey(sid, rpc, rid, killer_id, killer_owner, prey_id, lay, walk, elev, stage_prey)

    # (d) La cible rejoint le decoy, le caster prend `Ck`, le tueur (s'il n'est pas le caster)
    #     se gare loin.
    stage2 = {cid: lay["Ck"], tgt_id: lay["Tt"]}
    if killer_id != cid:
        stage2[killer_id] = lay["PARK2"]
    if not P124._drive_to(sid, rid, walk, elev, stage2):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement de mesure incomplet -- voulu "
                           f"{stage2}, obtenu { {u: pos.get(u) for u in stage2} }")
    P124._give_turn_back(sid, rid, myplayer)

    _dv2, pos = P124._positions(sid, rid)
    dv, ctx = _fresh_ctx(rpc, rid, cid)
    decoy = _attest_decoy(rpc, rid, dv, lay["Pk"], my_team)
    if not decoy["is_decoy"]:
        raise MontageError(f"montage NON INSTALLE : l'occupant de {lay['Pk']} ne porte pas "
                           f"`UnitTrait.Decoy` -- {decoy}")
    want_friend = regime == "friend"
    if decoy["is_friend"] != want_friend:
        raise MontageError(f"montage NON INSTALLE : leurre ami={decoy['is_friend']} alors que le "
                           f"regime `{regime}` en attend {want_friend} -- {decoy}")
    # Les tuiles de mesure doivent etre dans les tuiles d'action de l'oracle, sinon natif et port
    # ne compareraient pas la meme chose. `D` en fait partie parce que le natif laisse une tuile
    # a occupant STEPPABLE dans le movable set (`TileExtensions$$IsEmptyOrSteppable`) -- c'est le
    # fait meme dont vit ce playbook, donc son absence invaliderait le montage.
    act = [t for t in (ctx.action_tiles or []) if t and t[0] is not None]
    if lay["Pk"] not in act:
        raise MontageError(f"montage NON INSTALLE : la tuile du DECOY {lay['Pk']} n'est pas dans "
                           f"les tuiles d'action de l'oracle ({sorted(act)})")
    f_tile = pick_witness_tile(act, pos, pos[tgt_id], lay["Pk"], lay["Ck"], elev)
    if f_tile is None:
        raise MontageError(f"montage NON INSTALLE : aucune tuile TEMOIN libre, voisine NATIVE de "
                           f"la cible {pos[tgt_id]} et dans les tuiles d'action {sorted(act)}")
    attest_layout(pos, ids, lay, f_tile, elev)
    tgt_u = _unit(dv, tgt_id) or {}
    return {"rid": rid, "cid": cid, "myplayer": myplayer, "my_team": my_team, "ids": ids,
            "regime": regime, "ctx": ctx, "dv": dv, "layout": lay, "decoy": decoy, "F": f_tile,
            "target_effects": [e.get("effectType") for e in (tgt_u.get("effects") or ())],
            "walk": walk, "elev": elev}


def _tiles(case: dict) -> tuple:
    """Les trois tuiles d'attaque mesurees, dans l'ordre `D` (leurre), `F` (libre), `C` (caster)."""
    lay = case["layout"]
    return (("D", lay["Pk"]), ("F", case["F"]), ("C", lay["Ck"]))


def _rows(rpc, st: dict) -> list[dict]:
    """Une ligne par tuile d'attaque : natif, port, et port SANS le playbook 1277. `expected` est
    pose en dur -- le poids BC lu si et seulement si la tuile porte un leurre AMI."""
    import engine.playbook.psyker as PSY
    weight = float(st["ctx"].wt.triggered(WEIGHT_KEY))
    if weight <= 0:
        raise MontageError(f"montage NON INSTALLE : le poids {WEIGHT_KEY} vaut {weight} dans le BC "
                           f"servi -- le terme serait nul et la mesure ne trancherait rien")
    tgt, out = st["ids"]["T"], []
    ab, _all, _here = _normal_ability(rpc, st["rid"], st["cid"])
    if ab is None:
        raise MontageError("montage NON INSTALLE : le caster n'a pas d'attaque normale")
    for key, tile in _tiles(st):
        expected = weight if (key == "D" and st["decoy"]["is_friend"]) else 0.0
        nat = pair_native(rpc, st["rid"], st["cid"], tgt, ab, tile)
        port = pair_port(st["ctx"], ab, tgt, tile)
        saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
        if saved is None:
            raise MontageError(f"le playbook {ABILITY} n'est PAS au registre -- rien a muter")
        try:
            muted = pair_port(st["ctx"], ab, tgt, tile)
        finally:
            PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
        out.append({"tile_key": key, "tile": tile, "weight": weight, "expected": expected,
                    "native": nat, "port": port, "port_muted": muted, "ability": ab})
    return out


def build_case(sid, rpc, rid: int, regime: str = "friend") -> dict:
    return _stage(sid, rpc, rid, regime)


def measure(rpc, case: dict) -> list[dict]:
    return _rows(rpc, case)


# --------------------------------------------------------------------------- contre-epreuves

def measure_mutant(rpc, case: dict, mutant: str) -> list[dict]:
    """Re-mesure le port avec le playbook 1277 REMPLACE par un mutant. Chaque mutant doit MORDRE :
    DEPLACER le port par rapport au port NON MUTE sur au moins une tuile.

      `no_trait`      -- gate `HasTrait(u, Decoy)` retire : la tuile `C` (occupee par le caster,
                         AMI mais pas leurre) prend le poids a tort.
      `invert_friend` -- gate `IsFriend` INVERSE : `D` change de valeur dans les DEUX regimes
                         (il perd le poids en `friend`, il le gagne en `enemy`).
      `target_tile`   -- la tuile lue devient celle de la CIBLE au lieu de celle du caster : `D`
                         perd le poids (la cible n'est sur aucun leurre).

    ⚠ Le critere est le DEPLACEMENT par rapport au port NON MUTE, JAMAIS l'ecart au natif : la
    paire porte un residu constant hors-perimetre, et un `abs(port - native) > EPS` serait donc
    VRAI meme pour un mutant parfaitement inerte."""
    import engine.playbook.psyker as PSY
    from engine.playbook import cosmic_horror as CH
    from engine.playbook.prediction._shared import _entity_traits

    class _Mut(CH.CosmicHorrorPlaybook):
        def calculate_attack_utility_in_steps(self, ctx, attacker_uid, ability_id, case_tgt_id,
                                              attack_tile, prediction=None):
            sc = getattr(ctx, "scene", None)
            if sc is None:
                return 0.0
            tile = sc.pos(case_tgt_id) if mutant == "target_tile" else attack_tile
            occ = CH.tile_occupant(sc, tile)
            if occ is None:
                return 0.0
            if mutant != "no_trait" and UnitTrait.Decoy.name not in _entity_traits(sc, occ):
                return 0.0
            same = sc.team(occ) == sc.team(attacker_uid)
            if (not same) if mutant != "invert_friend" else same:
                return 0.0
            return float(ctx.wt.triggered(WEIGHT_KEY))

    tgt = case["ids"]["T"]
    ab, _all, _here = _normal_ability(rpc, case["rid"], case["cid"])
    ref = {k: pair_port(case["ctx"], ab, tgt, t) for k, t in _tiles(case)}
    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY]
    PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = _Mut()
    try:
        return [{"mutant": mutant, "tile_key": k, "tile": t,
                 "port": pair_port(case["ctx"], ab, tgt, t), "port_ref": ref[k]}
                for k, t in _tiles(case)]
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved


# --------------------------------------------------------------------------- CLI

def _build(state_file: str, extra: list[str]) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file (le probe construit SON runner dessus)")
    ap.add_argument("--regime", choices=("friend", "enemy"), default="friend",
                    help="leurre AMI (defaut) ou leurre ENNEMI -- les deux sens du gate IsFriend")
    ap.add_argument("--mutants", action="store_true",
                    help="joue aussi les trois contre-epreuves (elles doivent MORDRE)")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(args.state_file, BUILD_ARGS[args.regime])
    case = build_case(sid, rpc, rid, args.regime)
    lay, dec = case["layout"], case["decoy"]
    print(f"runner {rid} | regime {args.regime} | caster u{case['cid']} @ {lay['Ck']}")
    print(f"  decoy u{dec['id']} ({dec['vis']}) @ {lay['Pk']} traits={dec['trait_ids']} "
          f"ami={dec['is_friend']} | tuile LIBRE F={case['F']} | effets sur la cible="
          f"{case['target_effects']}")
    for row in measure(rpc, case):
        d = row["port"] - row["native"]
        dm = row["native"] - row["port_muted"]
        print(f"  [{row['tile_key']}] {row['tile']} nat={row['native']:.6f} "
              f"port={row['port']:.6f} d={d:+.9f} | mute={row['port_muted']:.6f} "
              f"manque={dm:+.9f} attendu={row['expected']:.6f}")
    if args.mutants:
        for m in ("no_trait", "invert_friend", "target_tile"):
            rows = measure_mutant(rpc, case, m)
            worst = max(abs(r["port"] - r["port_ref"]) for r in rows)
            detail = " ".join(f"{r['tile_key']}:{r['port'] - r['port_ref']:+.4f}" for r in rows)
            print(f"  [mutant {m:<13}] deplacement max du port = {worst:+.9f} [{detail}] "
                  f"({'MORD' if worst > EPS else 'NE MORD PAS'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
