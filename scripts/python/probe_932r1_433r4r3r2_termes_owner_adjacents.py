"""probe #932-r1 / #433-r4-r3-r2 -- CONFRONTATION LIVE des termes OWNER << +w par ami adjacent >>.

TROIS termes, UN moteur. Ils vivent tous dans la feuille `TriggeredAbilities(2)` du composite
`Tile(7)` (dispatcher `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`),
et ils ont tous la MEME forme : `w x |amis a distance 1 de la tuile candidate qui satisfont P|`.

  * **1510 `DeathwingKnight`** (#932-r1) --
    `IdunBattle.AI.Playbook.Loki.DeathwingKnightPlaybook$$GetAdjacentFriendUtility` :
    `if (!UnitExtensions.HasFaction(friend, 0xa)) return 0; return getUtilityVal(DAT_1833fc908);`
    ou `0x33fc908` = `"DEATHWINGKNIGHT_AdjacentDAFriend"` (`metadata/string_literals.tsv`), poids
    `Utilities.Default.TriggeredAbilities` = 10. Porteurs : `darkaNpc3Terminator` (**npc**) et
    `darkaSmnTerminator` (**summon**) -- aucun hero du pool. Le npc entre par le chemin de stats
    EXPLICITE (`--explicit-stats`, case-92 recours 4), donc avec SES stats, SES traits et SON
    passif : c'est mieux qu'une greffe, qui perdrait les trois.
  * **1000 `PsychicFortress`** (#433-r4-r3-r2) --
    `...PsychicFortressPlaybook$$GetAdjacentFriendUtility` : LOOKUP PLAT sur
    `"PSYCHICFORTRESS_AdjacentFriend"` (5), aucun gate sur le voisin. Porteur `ultraTigurius`,
    HERO du pool.
  * **1487 `EcogSupport`** (#433-r4-r3-r2) --
    `...ECogSupportPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :
    `+30` par ami adjacent dont `UnitExtensions$$GetParent(u, State, root:false) == case.Unit`.
    Porteur `votanIronmaster`, HERO **hors pool** -> injection catalogue, et l'E-Cog n'apparait
    qu'a la REPARATION (`ECogSupportAbility$$CreateTrigger` = `On(0x30 = UnitRepaired)`).

CE QUE LA MESURE ETABLIT, ET CE QU'ELLE NE PEUT PAS ETABLIR. On ne compare pas un scalaire : on
cherche une configuration ou le terme **RENVERSE l'argmax** du sweep de tuiles du PORTEUR, puis on
demande au natif quelle tuile il joue (`aiDryRunAllUnits` -> `MoveUnitMessage`). Un accord sur une
configuration ou le terme ne renverse rien ne prouverait RIEN (regime degenere) : le probe REFUSE
alors de conclure et le dit. C'est le critere de `probe_433_r4_r3_non_owner_playbooks.py`,
transpose de la face NON-OWNER a la face OWNER.

Usage (ASCII only, depuis scripts/python) :
  python probe_932r1_433r4r3r2_termes_owner_adjacents.py --offline-only
  python probe_932r1_433r4r3r2_termes_owner_adjacents.py --terme deathwingknight
  python probe_932r1_433r4r3r2_termes_owner_adjacents.py --terme psychicfortress --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

#: `TriggeredAbilityType` -- membres NOMMES, jamais l'ordinal nu (cf. CLAUDE.md).
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402

#: Les trois montages. `qualifie(u)` mirrore le gate LU dans l'accesseur de poids ; `None` = aucun
#: gate (le natif ne lit pas son argument `friend`).
MONTAGES = {
    "deathwingknight": {
        "ability": int(TriggeredAbilityType.DeathwingKnight),        # 0x5e6 = 1510
        "key": "DEATHWINGKNIGHT_AdjacentDAFriend",                   # literal 0x33fc908
        "carrier": "darkaNpc3Terminator",
        "carrier_arg": "darkaNpc3Terminator:20",                     # palier npc (case-92 recours 4)
        "explicit_stats": "darkaNpc3Terminator:20",
        "p_units": "darkaNpc3Terminator:20,darkaAsmodai,darkaHellblaster,darkaCompanion,astraBullgryn",
        "a_units": "worldKharn,templChampion",
        "faction": "DarkAngels",                                     # `HasFaction(friend, 0xa)`
        "seed_bc": None,
        # ⚠ LEVIER DE MONTAGE, pas de mecanique. Les amis spawnent groupes dans un coin et le
        # classement des tuiles du porteur (deep-strike, 52 tuiles) est domine par
        # `MinDistanceToEnemy` : sans portee de mouvement, AUCUN ami n'atteint le voisinage des
        # tuiles de tete, et le terme ne peut rien renverser. `Movement` est un champ de
        # `BC.Units` que `--unit-stat` patche APRES la normalisation. Il ne touche ni le poids, ni
        # le gate de faction, ni l'adjacence -- les trois etages que la mesure interroge.
        "unit_stat": "darkaAsmodai:Movement=20;darkaHellblaster:Movement=20;"
                     "darkaCompanion:Movement=20",
    },
    "psychicfortress": {
        "ability": int(TriggeredAbilityType.PsychicFortress),        # 1000
        "key": "PSYCHICFORTRESS_AdjacentFriend",                     # literal 0x3372ba8
        "carrier": "ultraTigurius",
        "carrier_arg": "ultraTigurius",
        "explicit_stats": None,
        "p_units": "ultraTigurius,astraBullgryn,necroWarden,orksNob,orksWarboss",
        # UN SEUL ennemi, et c'est un choix MESURE. `MinDistanceToEnemy` est le terme dominant du
        # sweep ; avec trois ennemis disperses, ses paliers se croisent et le classement des tuiles
        # du porteur est strictement etale (tete a -290, suivante a -305, puis un mur a -380). Avec
        # UN ennemi, les tuiles equidistantes forment des ANNEAUX, et l'anneau de tete est une
        # EGALITE que le poids 5 suffit a trancher. On ne cherche pas un regime commode : on
        # fabrique le seul ou un terme de 5 points soit observable.
        "a_units": "worldKharn",
        "faction": None,                                             # le parametre `friend` est IGNORE
        "seed_bc": None,
        # Meme levier de MONTAGE que ci-dessus, PORTEUR COMPRIS -- et ici il est INDISPENSABLE, pour
        # une raison mesuree : le poids ne vaut que **5**, alors que le classement natif des 15
        # tuiles de `ultraTigurius` est etale sur 300 points par `MinDistanceToEnemy` (tete a -670,
        # suivante a -750). Aucun nombre d'amis realiste ne renverse un ecart de 80 avec un pas de
        # 5. En elargissant SA portee, son ensemble candidat inclut des tuiles a MEME distance
        # d'ennemi, donc a MEME utilite sans terme -- et c'est cette EGALITE que le terme tranche.
        # Ce que ce levier ne touche pas : le poids, le gate (il n'y en a pas) et l'adjacence.
        # VOIE ATTAQUE, et c'est MESURE, pas choisi : `ultraTigurius` propose
        # `[MoveUnitMessage, ActiveAbilityMessage]` a toute portee de mouvement testee (8, 10, 12,
        # 20 -- il a une arme a distance). Retirer ses `ActiveAbilities` ne l'en prive pas non
        # plus : l'ATTAQUE NORMALE est elle-meme une ability concrete. Le composite `Tile(7)`
        # entre dans les DEUX sweeps -- on compare donc sa destination d'ATTAQUE.
        "voie": "attaque",
        "unit_stat": "ultraTigurius:Movement=20;astraBullgryn:Movement=20;necroWarden:Movement=20;"
                     "orksNob:Movement=20;orksWarboss:Movement=20",
    },
    "ecogsupport": {
        "ability": int(TriggeredAbilityType.EcogSupport),            # 0x5cf = 1487
        "key": "EcogSupport_EcogSummonsInRange",                     # literal 0x335e288
        "carrier": "votanIronmaster",
        "carrier_arg": "votanIronmaster",
        "explicit_stats": None,
        # CINQ unites, et le compte est MESURE : chaque passe de craft consomme UN ami mobile (une
        # unite qui a bouge a agi). Le seul ami QUALIFIANT etant l'E-Cog, immobile, il faut autant
        # d'amis NON qualifiants que de tuiles a retirer du sommet avant que la bande de 30 points
        # n'atteigne une tuile voisine de l'E-Cog.
        "p_units": "votanIronmaster,admecRuststalker,astraBullgryn,necroWarden,orksNob",
        "a_units": "worldKharn,templChampion",
        "faction": None,                                             # gate = PARENT, pas faction
        "parent_is_carrier": True,                                   # `GetParent(u) == case.Unit`
        "seed_bc": "AUGMENTE",                                       # porteur HORS pool
        # `RemainingHealth` : la cible doit etre ENDOMMAGEE, sinon `EntityCanBeRepaired` refuse et
        # l'E-Cog n'apparait pas. `Movement` : meme levier de montage que les deux autres.
        "unit_stat": "admecRuststalker:RemainingHealth=1200;votanIronmaster:Movement=20;"
                     "admecRuststalker:Movement=20;astraBullgryn:Movement=20;"
                     "necroWarden:Movement=20;orksNob:Movement=20",
        # ⚠ La cible de reparation porte AU SEED la relique `TertiaryAbility = 1457`
        # (`KardiocoreGalvanus`), dont la face NON-OWNER verse +20 aux tuiles adjacentes a son
        # porteur sous le gate `IsMechanical(case.Unit)`. Le mover ici est `votanIronmaster`, qui
        # est mecanique : le terme se superposerait au notre. On DESEQUIPE, comme #433-r4-r3.
        "desequiper": "admecRuststalker",
        # Le seul ami QUALIFIANT est l'E-Cog, et il est immobile (#291). Le montage passe donc par
        # la phase OCCUPER, qui retire une tuile de tete a chaque passe : il en faut plusieurs pour
        # amener le sommet dans la bande de 30 points ou l'E-Cog decide.
        "passes_craft": 4,
        # VOIE ATTAQUE, MESUREE comme pour `psychicfortress` : `votanIronmaster` porte
        # `GravitonRifle` et propose `[MoveUnitMessage, ActiveAbilityMessage]`.
        "voie": "attaque",
    },
}

DEFAULT_BOARD = "MC1_67"
DEFAULT_SEED = "777"
#: `admecRuststalker` a le trait `Mechanical` -> `AttackQuery$$EntityCanBeRepaired`. C'est la
#: REPARATION qui fait apparaitre l'E-Cog (trigger `On(0x30 = UnitRepaired) & OwnerIsCaster`).
ECOG_REPAIREE = "admecRuststalker"
#: `ActiveAbilityType.Repair` -- l'active DERIVEE du trait `Mechanic`, que le porteur n'a pas dans
#: ses `activeAbilities` gameconfig (il n'y porte que `GravitonRifle`).
REPAIR_ABILITY = 28


def _r(sid, m, b, t=120):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(seed, board, cfg, seed_bc_path=None):
    """Runner ISOLE, `--state-file` ABSOLU a nom unique (discipline `runner.md` §3)."""
    state = ROOT / "logs" / "runners" / ("probe932r1-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", str(state),
            "--p-units", cfg["p_units"], "--a-units", cfg["a_units"]]
    if cfg.get("explicit_stats"):
        argv += ["--explicit-stats", cfg["explicit_stats"]]
    if cfg.get("unit_stat"):
        argv += ["--unit-stat", cfg["unit_stat"]]
    if seed_bc_path:
        argv += ["--seed-bc", str(seed_bc_path)]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, None, (p.stderr or p.stdout or "")[-1200:]
    return json.loads(state.read_text())["runnerId"], state, None


def _dispose(sid, rid):
    if rid is None:
        return
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception:                                    # pragma: no cover - nettoyage best-effort
        pass


# --------------------------------------------------------------------------------------------
# ETAPE 0 -- garde de MONTAGE : le poids est-il non nul, et le registre porte-t-il la classe ?
# --------------------------------------------------------------------------------------------
def etape0_poids(nom, verbose=True) -> int:
    import contextlib
    import io
    from engine import weights as W
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS

    cfg = MONTAGES[nom]
    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    cap = ((bc.get("Utilities") or {}).get("Default") or {}).get("TriggeredAbilities") or {}
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        wt = W.load()
    fell_back = "REPLI sur BC.Utilities" in err.getvalue()
    w = wt.sub("TriggeredAbilities", cfg["key"])
    inscrit = cfg["ability"] in TRIGGERED_MOVE_PLAYBOOKS
    if verbose:
        print("[etape0] %-14s cle=%-34s capture=%-5s moteur=%-5s registre=%s"
              % (nom, cfg["key"], cap.get(cfg["key"]), w, inscrit))
    if fell_back:
        print("[etape0] REFUS : `engine.weights.load` est retombe sur la table de la CAPTURE.")
        return 1
    if not w:
        print("[etape0] REFUS : poids nul cote moteur -- terme INERTE, rien a mesurer.")
        return 1
    if not inscrit:
        print("[etape0] REFUS : %d absent de `TRIGGERED_MOVE_PLAYBOOKS` -- le dispatcher ne "
              "chargera jamais ce playbook." % cfg["ability"])
        return 1
    return 0


# --------------------------------------------------------------------------------------------
# Le moteur d'A/B
# --------------------------------------------------------------------------------------------
def _score_map(ctx, wt, *, with_term: bool, ability: int):
    """`UnitMovement(6)` du port par tuile candidate, terme `ability` ACTIF ou AMPUTE du registre.

    Amputer le REGISTRE (et non le poids) est ce qui isole le terme : `load_playbook` rend `None` et
    le dispatcher fait `continue`, exactement comme le natif quand `LoadPlaybook` rend null."""
    from engine.playbook.base import tile_utility
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    from engine.utilities.move import MIN_DIST_UTILITY
    saved = None
    if not with_term:
        saved = TRIGGERED_MOVE_PLAYBOOKS.pop(ability, None)
    try:
        out = {}
        for t in (ctx.move_tiles or []):
            p = (t["col"], t["row"])
            out[p] = tile_utility(ctx, p) + MIN_DIST_UTILITY.evaluate_movement(
                p, ctx.tgt_epos or ctx.epos, wt, ctx.pathdist_by_pos, case=ctx.mindist_case)
        return out
    finally:
        if saved is not None:
            TRIGGERED_MOVE_PLAYBOOKS[ability] = saved


def _score_map_attaque(ctx, wt, *, with_term: bool, ability: int):
    """MEME A/B, mais sur la voie ATTAQUE : `{tuile d'action -> utilite d'action}` pour la paire
    (ability, cible) que `ComparableAbilityGenerator._best_attack` retient.

    Elle existe parce qu'un porteur qui a une attaque a portee ne propose PAS un mouvement pur : le
    natif rend `[MoveUnitMessage, ActiveAbilityMessage]`, et sa destination est alors la TUILE
    D'ATTAQUE (`UtilityAttackCase`), pas la sortie d'`UnitMovement(6)`. Comparer la premiere au
    second serait comparer deux modeles differents. Le composite `Tile(7)` -- donc la feuille
    `TriggeredAbilities(2)` et le terme mesure -- entre dans les DEUX.
    C'est le vehicule de `tests/engine/_move_tile_sweep_order.py` (garde N13)."""
    from engine.ai.action_generators import ComparableAbilityGenerator
    from engine.playbook import noncomparable as playbooks
    from engine.playbook import get_playbook_or_default
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK
    saved = None
    if not with_term:
        saved = TRIGGERED_MOVE_PLAYBOOKS.pop(ability, None)
    try:
        gen = ComparableAbilityGenerator()
        best = gen._best_attack(ctx)
        if best is None:
            return {}, None
        _, _u_action, tgt, ab, _tile = best
        ev = next((e for e in ((ctx.plans.get(ctx.uid) or {}).get("evals") or [])
                   if e.get("abilityId") == ab and e.get("targetId") == tgt
                   and e.get("rankCount") and (e.get("ranked") or [])
                   and not playbooks.is_noncomp(e.get("abilityId"))), None)
        legal = ({(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])}
                 if ev is not None else set())
        pb = NORMAL_ATTACK_PLAYBOOK if ab in ctx.normal_ids else get_playbook_or_default(ab)
        out = {}
        for tile in (ctx.action_tiles or []):
            if legal and tile not in legal:
                continue
            cand = gen._action_utility(ctx, pb, ab, tgt, tile)
            if cand is not None:
                out[tile] = cand[0]
        return out, best
    finally:
        if saved is not None:
            TRIGGERED_MOVE_PLAYBOOKS[ability] = saved


def _ctx_for(sid, rid, uid, wt):
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    pred = _scene.build_predictor(lambda m, b, t=120: _r(sid, m, b, t), rid)
    ctx = _ai_ctx.build(lambda m, b, t=120: _r(sid, m, b, t), rid, dv, mov_by_unit, uid, wt, pred)
    return ctx, dv, mov_by_unit


def _qualifie(cfg, u: dict, carrier_id) -> bool:
    """Le gate LU dans l'accesseur natif, mirror du port -- jamais une paraphrase."""
    if cfg.get("faction") is not None:
        import gameconfig as GC
        return (GC.unit(u.get("vis") or "") or {}).get("FactionId") == cfg["faction"]
    if cfg.get("parent_is_carrier"):
        par = u.get("parent")
        return par is not None and int(par) == int(carrier_id)
    return True                                          # aucun gate (le natif ignore `friend`)


def _n_qualifiants(cfg, ctx, tile, carrier_id) -> int:
    """`|amis a distance 1 de <tile> qui satisfont P|`, meme adjacence NATIVE que le port
    (`battle_query.is_adjacent` : liste STOCKEE du voisinage + porte d'elevation `|dElev| < 2`)."""
    from engine import battle_query as bq
    from engine.utilities.tile import tile_leaf_ctx
    leaf = tile_leaf_ctx(ctx)
    elev = leaf.get("elev_by_pos")
    neigh = bq.neigh_map(leaf)
    n = 0
    for u in (leaf.get("friend_units") or ()):
        p = u.get("pos")
        if p and bq.is_adjacent(tile, p, elev, neigh) and _qualifie(cfg, u, carrier_id):
            n += 1
    return n


def _cartes(ctx, wt, cfg, *, with_term: bool):
    """La carte de tuiles a comparer, selon la VOIE que le porteur emprunte (cf. `voie`)."""
    if cfg.get("voie") == "attaque":
        return _score_map_attaque(ctx, wt, with_term=with_term, ability=cfg["ability"])[0]
    return _score_map(ctx, wt, with_term=with_term, ability=cfg["ability"])


def _crafter(sid, rid, ctx, cfg, carrier, off, w, wt) -> "tuple | None":
    """CHERCHE une configuration DISCRIMINANTE, et la fabrique.

    Le montage naturel ne l'est presque jamais : les amis spawnent groupes dans un coin et le
    classement des tuiles du porteur est domine par `MinDistanceToEnemy`. On DEPLACE donc les amis
    qualifiants -- << bloque par la geometrie de spawn >> n'est pas un resultat.

    Critere : un couple `(T1, T2)` du classement SANS terme tel que `off[T1] - off[T2] < w x k`
    avec `k` amis qualifiants placables sur des tuiles LIBRES adjacentes (voisinage NATIF) a `T2`
    et PAS a `T1`. Le terme verse alors `+w x k` a `T2` et `0` a `T1` : il RENVERSE l'argmax, et
    l'accord du natif devient une information. Rend `(T1, T2, [(uid, slot), ...])` ou `None`."""
    from engine import battle_query as bq
    from engine.utilities.tile import tile_leaf_ctx

    leaf = tile_leaf_ctx(ctx)
    elev = leaf.get("elev_by_pos")
    neigh = bq.neigh_map(leaf)
    tous = list(leaf.get("friend_units") or ())
    amis = [u for u in tous if _qualifie(cfg, u, carrier)]
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    joignables = {u.get("unitId"): {(t["col"], t["row"]) for t in (u.get("tiles") or ())}
                  for u in (mov.get("units") or ())}
    # ⚠ Un SUMMON n'a AUCUNE tuile dans `aiMovableTiles` -- son tour est termine des son apparition
    # (`SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` -> `FinishUnitTurn(isTerminated: true)`,
    # #291). Sur le montage `EcogSupport`, le seul ami QUALIFIANT est donc IMMOBILE : la premiere
    # phase (deplacer des amis vers T2) est structurellement vide, et c'est la phase OCCUPER qui
    # porte le montage -- elle n'a pas besoin d'un ami qualifiant, seulement d'un ami MOBILE.
    mobiles = [u for u in tous if joignables.get(u.get("id"))]
    if not amis and not mobiles:
        return None
    occupees = {tuple(p) for p in (list(ctx.epos or ()) + list(ctx.fpos or ()))}

    order = sorted(off.items(), key=lambda kv: -kv[1])
    t1 = order[0][0]
    for t2, s2 in order[1:]:
        # Tuiles LIBRES adjacentes a T2, les NON-adjacentes a T1 d'abord : une tuile adjacente aux
        # DEUX verse `w` des deux cotes et n'avance a rien, mais elle reste utilisable pour loger un
        # ami en surplus. Le critere est le NET, jamais << pas adjacent a T1 >> : c'est ce qui
        # permet d'exploiter un voisinage etroit.
        slots = [p for p in (neigh.get(t2) or ())
                 if bq.is_adjacent(t2, p, elev, neigh)
                 and p not in occupees and p not in (t1, t2)]
        slots.sort(key=lambda p: 1 if bq.is_adjacent(t1, p, elev, neigh) else 0)
        if not slots:
            continue
        for k in range(1, min(len(amis), len(slots)) + 1):
            choisies = slots[:k]
            gain2 = w * k
            gain1 = w * sum(1 for p in choisies if bq.is_adjacent(t1, p, elev, neigh))
            if off[t2] + gain2 <= off[t1] + gain1:
                continue
            plan, pris = [], set()
            for u in amis:
                if len(plan) == k:
                    break
                reach = joignables.get(u.get("id")) or set()
                for s in choisies:
                    if s in pris or s not in reach:
                        continue
                    plan.append((u.get("id"), s))
                    pris.add(s)
                    break
            if len(plan) == k:
                return t1, t2, plan
    # SECOND RECOURS -- OCCUPER T1. Une tuile occupee sort de l'ensemble candidat du porteur (le
    # natif ne propose pas d'aller sur une case prise) : le sommet tombe alors sur le rang suivant,
    # qui est tres souvent une EGALITE (trois tuiles a la meme distance d'ennemi). Une egalite se
    # tranche avec UN seul ami, quel que soit l'ecart d'origine. C'est ce qui rend un poids de 5
    # observable la ou l'ecart de tete vaut 30.
    for u in mobiles:
        if t1 in (joignables.get(u.get("id")) or set()):
            return t1, None, [(u.get("id"), t1)]
    return None


def confronter(nom, seed=DEFAULT_SEED, board=DEFAULT_BOARD, verbose=True) -> dict:
    """Rend le dict de mesure. Dispose SES runners (jamais ceux des autres)."""
    from engine import weights as W

    cfg = MONTAGES[nom]
    sid = _resolve_session()
    if not sid:
        return {"error": "aucune session Frida"}
    wt = W.load()
    w = float(wt.sub("TriggeredAbilities", cfg["key"]))
    if w <= 0:
        return {"error": "%s vaut 0 cote moteur" % cfg["key"]}

    seed_bc = None
    if cfg.get("seed_bc") == "AUGMENTE":
        import catalog_inject
        bc = catalog_inject._load_seed(None)
        if cfg.get("desequiper"):
            catalog_inject.unequip_relic(bc, cfg["desequiper"])
        seed_bc = ROOT / "logs" / "runners" / ("probe932r1-bc-%s.json" % uuid.uuid4().hex[:8])
        seed_bc.parent.mkdir(parents=True, exist_ok=True)
        catalog_inject.write_augmented_seed_bc(str(seed_bc), [cfg["carrier"]], seed_bc=bc)

    rid, state, err = _build(seed, board, cfg, seed_bc)
    if rid is None:
        return {"terme": nom, "error": "build KO : %s" % err}
    try:
        dv0 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        ids = {u.get("visualId"): u.get("id") for u in (dv0.get("units") or []) if u.get("ctrl")}
        carrier = ids.get(cfg["carrier"])
        if carrier is None:
            res = {"terme": nom, "error": "porteur %s absent de la bataille (ids=%r)"
                                          % (cfg["carrier"], sorted(ids))}
            if verbose:
                _dire(res)
            return res

        if nom == "ecogsupport":
            out = _spawn_ecog(sid, rid, ids, state)
            if out is not None:
                out.setdefault("terme", nom)
                if verbose:
                    _dire(out)
                return out

        # GARDE DE SOURCE : le kit DECLENCHE que le dispatcher va iterer porte-t-il l'ability ?
        # Un playbook enregistre mais jamais appele est un port SPECULATIF.
        ctx, _, _ = _ctx_for(sid, rid, carrier, wt)
        from engine.utilities.tile import tile_leaf_ctx
        kit = list(tile_leaf_ctx(ctx).get("unit_triggered_abilities") or ())
        if cfg["ability"] not in kit:
            return {"error": "ability %d absente du kit declenche du porteur (%r) -- le playbook "
                             "ne sera JAMAIS appele" % (cfg["ability"], kit)}

        off = _cartes(ctx, wt, cfg, with_term=False)
        on = _cartes(ctx, wt, cfg, with_term=True)
        if len(off) < 2:
            return {"error": "le porteur n'a que %d tuile(s) candidate(s)" % len(off)}

        # (a) le terme est-il bien `w x n` par tuile, et le montage est-il NON DEGENERE ?
        ns = {p: _n_qualifiants(cfg, ctx, p, carrier) for p in off}
        ecarts = {p: round(on[p] - off[p], 6) for p in off}
        mauvais = [(p, ecarts[p], w * ns[p]) for p in off
                   if abs(ecarts[p] - w * ns[p]) > 1e-6]
        distincts = sorted(set(ns.values()))
        p_off = max(off, key=lambda k: off[k])
        p_on = max(on, key=lambda k: on[k])
        # EGALITE EN TETE SANS TERME = le port ne DECIDE pas (keep-first arbitraire). Si le terme
        # rend un maximum STRICT, il est decisif meme quand `max()` avait deja rendu la meme tuile
        # par hasard -- c'est exactement le << tie artefact >> que garde `test_tile_term_*`.
        _tete = lambda m: [p for p in m if abs(m[p] - max(m.values())) < 1e-9]      # noqa: E731

        res = {"terme": nom, "ability": cfg["ability"], "cle": cfg["key"], "poids": w,
               "carrier": carrier, "board": board, "seed": seed, "kit": kit,
               "n_tuiles": len(off), "n_distincts": distincts,
               "delta_incoherent": mauvais[:5],
               "argmax_off": p_off, "argmax_on": p_on,
               "u_off": round(off[p_off], 6), "u_on": round(on[p_on], 6),
               "tete_off": len(_tete(off)), "tete_on": len(_tete(on)),
               "renverse": (p_off != p_on) or (len(_tete(off)) > 1 and len(_tete(on)) == 1),
               "native": None, "accord": None}

        # (b) MONTAGE NON DISCRIMINANT -> on le FABRIQUE (jamais << bloque par la geometrie >>).
        # DEUX passes : la premiere cherche un couple (T1, T2) que des amis peuvent renverser ; si
        # elle echoue, la seconde OCCUPE le sommet et retente sur l'egalite qui apparait dessous.
        res["craft"] = []
        for _passe in range(cfg.get("passes_craft", 2)):
            if res["renverse"]:
                break
            plan = _crafter(sid, rid, ctx, cfg, carrier, off, w, wt)
            if plan is None:
                res["error"] = ("aucun couple (T1, T2, amis placables) discriminant sur %s/%s -- "
                                "montage a re-etalonner" % (board, seed))
                break
            t1, t2, moves = plan
            res["craft"].append(plan)
            for uid, slot in moves:
                r = _r(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": uid, "to": {"col": slot[0], "row": slot[1]}}}, 120)
                if not (r.get("actions") or [{}])[0].get("ok"):
                    res["error"] = "applyAction move u%s -> %s KO : %r" % (uid, slot, r)
                    break
            if res.get("error"):
                break
            ctx, _, _ = _ctx_for(sid, rid, carrier, wt)
            off = _cartes(ctx, wt, cfg, with_term=False)
            on = _cartes(ctx, wt, cfg, with_term=True)
            if len(off) < 2:
                res["error"] = "apres craft, le porteur n'a plus que %d tuile(s)" % len(off)
                break
            ns = {p: _n_qualifiants(cfg, ctx, p, carrier) for p in off}
            res["delta_incoherent"] = [(p, round(on[p] - off[p], 6), w * ns[p]) for p in off
                                       if abs((on[p] - off[p]) - w * ns[p]) > 1e-6][:5]
            res["n_distincts"] = sorted(set(ns.values()))
            res["n_tuiles"] = len(off)
            p_off = max(off, key=lambda k: off[k])
            p_on = max(on, key=lambda k: on[k])
            res.update({"argmax_off": p_off, "argmax_on": p_on,
                        "renverse": (p_off != p_on)
                        or (len(_tete(off)) > 1 and len(_tete(on)) == 1),
                        "tete_off": len(_tete(off)), "tete_on": len(_tete(on)),
                        "u_off": round(off[p_off], 6), "u_on": round(on[p_on], 6),
                        "craft_cible": t2, "craft_t1": t1})
        if res.get("error"):
            if verbose:
                _dire(res)
            return res

        if res["renverse"]:
            allu = _r(sid, "aiDryRunAllUnits", {"runnerId": rid}, 300)
            row = next((u for u in (allu.get("units") or []) if u.get("unitId") == carrier), None)
            if row is None:
                res["native_erreur"] = "porteur absent de aiDryRunAllUnits"
            else:
                msgs = row.get("proposed") or []
                mv = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
                attaque = any(m.get("cls") == "ActiveAbilityMessage" for m in msgs)
                res["native_cls"] = [m.get("cls") for m in msgs]
                if mv is None or (attaque != (cfg.get("voie") == "attaque")):
                    res["native_erreur"] = (
                        "proposition native %r incompatible avec la voie '%s' -- une destination "
                        "d'ATTAQUE et une sortie d'`UnitMovement(6)` sont deux modeles differents"
                        % (res["native_cls"], cfg.get("voie") or "move"))
                else:
                    res["native"] = (mv["to"]["col"], mv["to"]["row"])
                    res["accord"] = (res["native"] == p_on)
        if verbose:
            _dire(res)
        return res
    finally:
        _dispose(sid, rid)


def _spawn_ecog(sid, rid, ids, state):
    """Fait REELLEMENT apparaitre l'E-Cog, PUIS rend la main a son invocateur.

    Le trigger natif est `On(0x30 = EventTriggerType.UnitRepaired) & OwnerIsCaster`
    (`ECogSupportAbility$$CreateTrigger`) : c'est la REPARATION qui fait apparaitre le summon, pas
    le debut de bataille (`ECogSupport_InitAbility` ne fait qu'un `AddFlag(0x18)`). Le porteur n'a
    qu'une active (`GravitonRifle`) -- la reparation vient de son trait `Mechanic`, donc
    `ActiveAbilityType.Repair = 28`, et la cible doit etre MECANIQUE **et endommagee**
    (`AttackQuery$$EntityCanBeRepaired`).

    ⚠ Le porteur a AGI en reparant : son tour est fini, donc il n'a plus de tuile candidate. Le
    terme OWNER se mesure sur SON sweep -- il faut donc boucler un tour complet pour le retrouver
    activable, l'E-Cog etant desormais sur le plateau. C'est la difference de fond avec la face
    NON-OWNER de #433-r4-r3, ou le MOVER etait le summon (jamais dans `toActivate`, #291) : ici le
    mover est un HERO, et c'est ce qui rend la face OWNER confrontable.

    Rend `None` si tout va bien, un dict d'erreur sinon."""
    cible = ids.get(ECOG_REPAIREE)
    porteur = ids.get(MONTAGES["ecogsupport"]["carrier"])
    if cible is None or porteur is None:
        return {"error": "montage ECog : %s ou le porteur absent (ids=%r)"
                         % (ECOG_REPAIREE, sorted(ids))}
    res = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": porteur, "targetId": cible,
        "abilityType": REPAIR_ABILITY}}, 180)
    act = (res.get("actions") or [{}])[0]
    if not act.get("ok"):
        return {"error": "cast Repair KO : %r" % res}
    if not [c for c in (act.get("changes") or []) if c.get("appeared")]:
        return {"error": "aucun summon apparu au Repair -- `On(UnitRepaired)` n'a pas tire"}
    # Boucler le tour : fin de MON tour, puis le tour de l'IA ADVERSE. On passe par les
    # sous-commandes `rl_duel act endturn` / `aiturn` et NON par `aiPlayByUnit` en direct : ce RPC
    # joue l'equipe du joueur COURANT, et l'appeler sans avoir verifie la bascule fait jouer MA
    # team (mesure : `turnsPlayed=9` et bataille terminee des le premier tour). `cmd_aiturn` porte
    # precisement la garde de bascule (quirk H19 : le `endturn` ne flippe pas toujours).
    for _ in range(4):
        for cmd in (["act", "endturn"], ["aiturn"]):
            subprocess.run([sys.executable, "rl_duel.py"] + cmd + ["--state-file", str(state)],
                           cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 120)
        # ⚠ `toActivate` est une liste d'IDS (des entiers), pas de dicts -- mesure.
        if porteur in [int(x) for x in (dv.get("toActivate") or []) if isinstance(x, int)]:
            return None
    return {"error": "le porteur n'est pas redevenu activable apres 4 bascules de tour"}


def _dire(res):
    if res.get("error"):
        print("[%s] ERREUR : %s" % (res.get("terme", "?"), res["error"]))
        return
    print("[%s] ability=%d cle=%s poids=%s porteur=u%s tuiles=%d"
          % (res["terme"], res["ability"], res["cle"], res["poids"], res["carrier"],
             res["n_tuiles"]))
    print("    |amis qualifiants| distincts sur les tuiles candidates : %r" % (res["n_distincts"],))
    print("    delta ON-OFF incoherent avec w x n : %r" % (res["delta_incoherent"],))
    for i, pl in enumerate(res.get("craft") or ()):
        print("    CRAFT[%d] : T1=%s T2=%s ; deplacements %r" % (i, pl[0], pl[1], pl[2]))
    print("    argmax SANS terme=%s (u=%s, %d ex aequo)  AVEC terme=%s (u=%s, %d ex aequo)  "
          "renverse=%s" % (res["argmax_off"], res["u_off"], res.get("tete_off", -1),
                           res["argmax_on"], res["u_on"], res.get("tete_on", -1), res["renverse"]))
    if res.get("native_erreur"):
        print("    NATIF : non exploitable -- %s" % res["native_erreur"])
    else:
        print("    NATIF joue %s -> accord=%s" % (res["native"], res["accord"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--terme", choices=sorted(MONTAGES), default=None)
    ap.add_argument("--seed", default=DEFAULT_SEED)
    ap.add_argument("--board", default=DEFAULT_BOARD)
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    noms = [a.terme] if a.terme else sorted(MONTAGES)
    rc = 0
    for n in noms:
        rc |= etape0_poids(n)
    if a.offline_only or rc:
        return rc

    sorties = []
    graines = [g.strip() for g in str(a.seed).split(",") if g.strip()]
    for n in noms:
        res = None
        for g in graines:
            # BALAYAGE DE GRAINES : la geometrie de spawn decide s'il existe un couple de tuiles
            # que le terme puisse departager. Une graine qui n'en offre pas n'est pas un verdict --
            # c'est un montage a re-etalonner, et on re-etalonne.
            res = confronter(n, seed=g, board=a.board, verbose=not a.json)
            if not res.get("error") and res.get("renverse"):
                break
        sorties.append(res)
        if res.get("error"):
            rc = 1
        elif res.get("delta_incoherent"):
            rc = 1
        elif res.get("renverse") and res.get("accord") is False:
            rc = 1
        elif not res.get("renverse"):
            print("[%s] NON DISCRIMINANT sur les graines %r -- aucune conclusion tiree." % (n, graines))
            rc = 1
    if a.json:
        print(json.dumps(sorties, indent=2, default=str))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
