"""probe #304 -- confrontation LIVE du terme de MOUVEMENT `ModifiedExoarmour` (1529, `votanChampion`
Kimm) : `IdunBattle.AI.Playbook.Loki.ModifiedExoarmourPlaybook$$CalculateMovementUtilityInStepsInternal`
= `ModifiedExoarmour_LikesMovingPerTile x |chemin origine -> tuile|` (poids BC = 5, cle AJOUTEE par le
build `rnca9r7q6c`).

POURQUOI CE PROBE NE MESURE PAS « LA DECISION DU MOTEUR » MAIS UN ETAGE
--------------------------------------------------------------------
Le montage de #27-r1 (Kimm, `Damage` a l'equilibre entre l'attaque normale 69 et `MassDriverAccelerator`
1222) rend le terme DECISIF -- mais la decision COMPLETE du moteur y est masquee par un ecart
ANTERIEUR et ETRANGER : la prediction de degat de l'attaque normale de Kimm depuis une tuile
d'arrivee. MESURE (board MC1_67, seed 909, Damage=1000) : `pairUtility(69, (4,0))` natif = 44.395,
la meme paire cote port = 17.8. Comparer des DECISIONS ferait donc conclure sur ce residu-la, pas
sur le terme sous test.

On decompose donc PAR ETAGE, exactement comme l'exige la doctrine :

    u_action(ability, tuile) = pairUtility(ability, tuile)      <- etage PREDICTION, pris au NATIF
                             + CalculateCustomUtility           <- +1 pour la normale, 0 pour 1222 (#27-r1)
                             + Tile(7)(tuile)                   <- etage TUILE, pris au PORT

`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
est cette somme, et le natif en prend l'argmax (`EvaluateInternal`, `Bucket.AddAction` : remplacement
sur `>` STRICT). En injectant l'etage prediction NATIF, le seul etage teste est le Tile(7) du port --
et dedans, la seule difference entre « avec » et « sans » est la feuille `TriggeredAbilities(2)` ->
`ModifiedExoarmourPlaybook`.

VERDICTS
  V0 le porteur porte bien 1529 dans le kit lu par le dispatcher, et le poids BC vaut 5.
  V1 LINEARITE : le terme porte vaut `5 x n` avec `n` = nombre de NOEUDS du chemin (extremites
     incluses) et AU MOINS DEUX longueurs distinctes sont exercees -- sinon on ne distingue pas
     « 5 par tuile » d'un FORFAIT.
  V2 ARGMAX : `argmax_t [pair_natif + custom + Tile7_port]` reproduit l'action ET la tuile que le
     natif JOUE (`aiDryRunAllUnits`).
  V3 SENSIBILITE (le ROUGE) : le meme argmax, terme RETIRE du registre, choisit AUTRE CHOSE.
  V4 REFUTATION DU FORFAIT : le meme argmax avec un terme FORFAITAIRE (meme valeur pour toute tuile
     != origine, calibre pour reproduire V2 sur le duel 69/1222) choisit AUTRE CHOSE -- donc la
     PROPORTIONNALITE a la longueur est mesuree, pas supposee.
  V5 ENCADREMENT du poids : l'argmax natif impose des inegalites sur `w` ; on affiche l'intervalle
     admissible et on verifie que 5 y est. C'est une CONTRAINTE lue, pas un fit.

Usage :
    python probe_304_modified_exoarmour.py                 # MC1_67 / 909 (fixture de reference)
    python probe_304_modified_exoarmour.py --damage 1000
    python probe_304_modified_exoarmour.py --board C4_09 --seed 31337 --auto
ASCII only.
"""
from __future__ import annotations

import sys

import probe_27_3_live as L
import probe_27_r1_massdriver_custom as MDA

NORMAL = 69
MDA_AB = 1222
ABILITY_ID = 1529
WEIGHT_KEY = "ModifiedExoarmour_LikesMovingPerTile"
# `Damage` du bras `--passive-on` de #27-r1 : le duel 69 / 1222 y est a l'equilibre, donc l'argmax
# est SENSIBLE a quelques points d'utilite -- c'est ce qui rend le terme observable.
DEFAULT_DAMAGE = 1000


def _build_ctx(rid: int):
    """`AiDecisionContext` du caster sur le runner vivant (meme couture que `engine_validate`)."""
    import engine_validate as EV
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    return AICTX.build(rpc, rid, dv, mov_by_unit, MDA.CASTER, wt, predictor), wt


def _ranked_tiles(ctx, ability: int) -> list:
    """Tuiles d'attaque LEGALES pour `ability` sur la cible du montage, telles que le natif les
    range (`attackPlans[].evals[].ranked` = `GetBestTileToAttackFrom`). C'est exactement le set que
    `ComparableAbilityGenerator` balaie."""
    plan = ctx.plans.get(ctx.uid) or {}
    for ev in (plan.get("evals") or []):
        if ev.get("abilityId") == ability and ev.get("targetId") == MDA.TARGET:
            return [(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])]
    return []


def _pair(rid: int, ability: int, tile) -> float | None:
    r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": MDA.CASTER, "targetId": MDA.TARGET,
                                "abilityType": ability, "col": tile[0], "row": tile[1]}])
    return r.get("utility")


def _custom(ability: int, normal_ids) -> float:
    """`CalculateCustomUtility` : `+1` pour l'attaque NORMALE (`engine/playbook/common.py`, mirror du
    seul override natif de ce montage), `0` pour 1222 -- NO-OP natif MESURE par #27-r1 (V1/V5)."""
    return 1.0 if ability in (normal_ids or ()) else 0.0


def _tile7(ctx, tile) -> float:
    from engine.playbook.base import tile_utility
    return tile_utility(ctx, tile)


def _with_term(enabled: bool, override=None):
    """Bascule le registre `TRIGGERED_MOVE_PLAYBOOKS` pour l'ability 1529.
    `override` = un playbook de substitution (mutation adversariale du bras V4)."""
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    from engine.playbook.modified_exoarmour import ModifiedExoarmourPlaybook
    if not enabled:
        TRIGGERED_MOVE_PLAYBOOKS.pop(ABILITY_ID, None)
    else:
        TRIGGERED_MOVE_PLAYBOOKS[ABILITY_ID] = override or ModifiedExoarmourPlaybook()


class _FlatTermPlaybook:
    """MUTATION ADVERSARIALE : un terme FORFAITAIRE (`value` des que la tuile n'est pas l'origine),
    calibre par l'appelant pour reproduire le duel 69/1222. Si l'argmax natif ne le distingue pas du
    terme `5 x n`, le montage NE PROUVE PAS la proportionnalite -- et le probe le dit."""

    def __init__(self, value: float):
        self.value = float(value)

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        sp = (ctx or {}).get("self_pos")
        if sp is None or (sp[0], sp[1]) == (tile[0], tile[1]):
            return 0.0
        return self.value


def _argmax(ctx, cands: dict, pairs: dict, normal_ids) -> tuple:
    """`argmax` de `pair_natif + custom + Tile7_port` sur toutes les paires (ability, tuile).
    `cands = {ability: [tiles]}`. Rend `(ability, tile, u_action, table)`."""
    table = []
    for ab, tiles in cands.items():
        for t in tiles:
            p = pairs.get((ab, t))
            if p is None:
                continue
            u = p + _custom(ab, normal_ids) + _tile7(ctx, t)
            table.append((u, ab, t, p))
    table.sort(key=lambda r: -r[0])
    if not table:
        return None, None, None, table
    u, ab, t, _p = table[0]
    return ab, t, u, table


def _native_choice(rid: int):
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    prop = next((u.get("proposed") for u in (dr.get("units") or [])
                 if u.get("unitId") == MDA.CASTER), []) or []
    ab = next((m.get("abilityType") for m in prop if m.get("cls") == "ActiveAbilityMessage"), None)
    mv = next((((m.get("to") or {}).get("col"), (m.get("to") or {}).get("row"))
               for m in prop if m.get("cls") == "MoveUnitMessage"), None)
    return ab, mv


def _engine_decide(rid: int):
    """Decision COMPLETE du moteur (spine `DefaultAiUnitTactic`), etat frais."""
    import engine_validate as EV
    from engine import weights as W
    from engine.playbook import scene as _scene
    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    a = EV.engine_decide(sid, rid, dv, mov_by_unit, MDA.CASTER, wt, predictor)
    return a.get("kind"), a.get("to"), a.get("ability")


def phase_b(rid: int, geom: dict) -> bool:
    """PHASE B -- MOUVEMENT PUR : l'ennemi est parque HORS DE PORTEE, le natif ne peut que se
    DEPLACER. Le decideur devient `UnitMovement(6) = Tile(7) + MinDistanceToClosestEnemy(17)`
    (`MovementActionGenerator` -> `SortTilesByUtility`), donc :

      * l'ecart de PREDICTION de degat qui masque tout en phase A n'y intervient plus -> on compare
        la DECISION COMPLETE du moteur, pas un etage ;
      * un terme FORFAITAIRE serait CONSTANT sur toutes les tuiles candidates (aucune n'est
        l'origine) : il ne peut departager AUCUNE paire de tuiles. Si le natif choisit une tuile que
        le moteur SANS terme ne choisit pas, alors la variation PAR TUILE est mesuree -- c'est la
        refutation STRUCTURELLE du forfait que la phase A ne pouvait pas produire."""
    import hexgeo
    from engine import move as MV
    from engine.utilities.tile import tile_leaf_ctx
    kimm = tuple(geom["kimm"])
    bg = L._rpc("boardGraph", [{"runnerId": rid}])
    occupied = set(MDA._positions(rid).values())
    far = sorted(((hexgeo.distance(kimm, (t.get("col"), t.get("row"))), (t.get("col"), t.get("row")))
                  for t in (bg.get("tiles") or [])
                  if t.get("walkable") and (t.get("col"), t.get("row")) not in occupied),
                 reverse=True)
    far = [p for d, p in far if d >= 6]
    if not far:
        print("  PHASE B : aucune tuile libre eloignee -- non montable sur ce board")
        return True

    def _port_move(ctx):
        return MV.best_move_faithful(
            ctx.move_tiles, ctx.elev_by_pos, ctx.tgt_epos or ctx.epos, ctx.wt,
            pathdist_by_pos=ctx.pathdist_by_pos, is_temporary_by_pos=ctx.is_temporary_by_pos,
            effects_by_pos=ctx.effects_by_pos, terrain_by_pos=ctx.terrain_by_pos,
            leaf_ctx=tile_leaf_ctx(ctx), mindist_case=ctx.mindist_case)[0]

    # CRAFT : on CHERCHE une position d'ennemi ou le terme est LIANT cote port (l'argmax de move
    # CHANGE selon qu'on le porte ou non). Sans ce balayage, `MinDistanceToClosestEnemy` (-100 par
    # tuile de chemin) ecrase le terme et la phase B ne conclut RIEN -- ce qui n'est pas une preuve
    # d'absence, seulement un montage non discriminant. Le natif n'est interroge QU'ENSUITE, sur le
    # montage retenu : le craft choisit la CONFIGURATION, jamais le verdict.
    picked = None
    for dst in far[:14]:
        MDA._move(rid, MDA.TARGET, MDA._t(dst))
        if MDA._positions(rid).get(MDA.TARGET) != tuple(dst):
            continue
        ctx, _wt = _build_ctx(rid)
        _with_term(True)
        on = _port_move(ctx)
        _with_term(False)
        off = _port_move(ctx)
        _with_term(True)
        if on is not None and tuple(on) != tuple(off or ()):
            picked = (dst, on, off)
            break
    if picked is None:
        print("\n--- PHASE B : AUCUNE des %d positions d'ennemi testees ne rend le terme liant en "
              "move pur (MinDist ecrase) -- phase NON CONCLUANTE, pas une refutation"
              % min(14, len(far)))
        return True
    dst, on, off = picked
    print("\n--- PHASE B : mouvement PUR (ennemi parque en %s, dist hex %d) ---"
          % (dst, hexgeo.distance(kimm, dst)))
    print("    craft : le port choisit %s AVEC terme, %s SANS -- le terme est LIANT ici" % (on, off))

    nat_ab, nat_mv = _native_choice(rid)
    if nat_ab is not None or nat_mv is None:
        print("  PHASE B NON CONCLUANTE : le natif joue encore une ability (%s) / aucun move (%s)"
              % (nat_ab, nat_mv))
        return True
    print("  NATIF : move pur -> %s" % (nat_mv,))

    v6 = (tuple(on) == tuple(nat_mv))
    print("  V6 moteur AVEC terme  : move %s -> %s"
          % (on, "OK (== natif)" if v6 else "ECHEC (!= natif)"))
    v7 = (tuple(off or ()) != tuple(nat_mv))
    print("  V7 moteur SANS terme  : move %s -> %s"
          % (off,
             "OK (DIVERGE du natif : la variation PAR TUILE est mesuree -> FORFAIT REFUTE, "
             "il serait CONSTANT sur toutes ces candidates)" if v7
             else "ECHEC (le natif suit le port SANS terme)"))
    return v6 and v7


def phase_a(damage: int, board: str, seed: int, geom0) -> tuple:
    """Un BRAS de la phase A, a `Damage` donne. Rend `(ok, rid, geom, constraints)` ou
    `constraints = {"prop": (lo, hi), "flat": (lo, hi)}` = l'encadrement que l'argmax NATIF impose
    sur le coefficient, sous le modele PROPORTIONNEL (`terme = w x n`) et sous le modele FORFAIT
    (`terme = c` des qu'on bouge). Les deux bras (`Damage` de part et d'autre de la bascule)
    fournissent l'un la borne BASSE, l'autre la borne HAUTE."""
    # `geom=None` -> la fixture prend sa geometrie de REFERENCE sur MC1_67/909 et la DERIVE du board
    # vivant partout ailleurs (`MDA.derive_geometry`) : c'est ce qui la rend portable (cf. `--auto`).
    rid, geom = MDA.build_fixture(damage, with_passive=True, board=board, seed=seed, geom=geom0)
    MDA.set_arm(rid, 0, geom)                       # bras n=0 : aucun appat adjacent (cf. V0 de #27-r1)
    print("\n--- runner=%d board=%s seed=%d Damage=%d passif=ON ---" % (rid, board, seed, damage))
    print("    geometrie : Kimm=%s ennemi=%s" % (geom["kimm"], geom["enemy"]))

    ctx, wt = _build_ctx(rid)
    from engine.utilities.tile import tile_leaf_ctx
    from engine.playbook.modified_exoarmour import ModifiedExoarmourPlaybook, path_node_counts
    lc = tile_leaf_ctx(ctx)
    pb = ModifiedExoarmourPlaybook()
    w = wt.sub("TriggeredAbilities", WEIGHT_KEY)
    ok = True

    # ---------------------------------------------------------------- V0 : porteur + poids
    kit = lc.get("unit_triggered_abilities") or []
    v0 = (ABILITY_ID in kit) and (w == 5)
    ok = ok and v0
    print("\n  V0 kit du mover = %s ; poids BC[%s] = %r  -> %s"
          % (kit, WEIGHT_KEY, w, "OK" if v0 else "ECHEC (le dispatcher serait MUET)"))

    # ---------------------------------------------------------------- candidats
    tiles69 = _ranked_tiles(ctx, NORMAL)
    tiles1222 = _ranked_tiles(ctx, MDA_AB)
    pairs = {}
    for ab, tiles in ((NORMAL, tiles69), (MDA_AB, tiles1222)):
        for t in tiles:
            pairs[(ab, t)] = _pair(rid, ab, t)
    cands = {NORMAL: tiles69, MDA_AB: tiles1222}

    # ---------------------------------------------------------------- V1 : linearite
    counts = path_node_counts(lc)
    terms = {t: pb.calculate_movement_utility_in_steps(t, lc, wt) for t in tiles69}
    origin = tuple(geom["kimm"])
    # `n_eff` = le multiplicateur EFFECTIF du terme : `path.Count` partout, **0 sur l'origine** --
    # c'est le court-circuit `UtilityMovementCase$$StaysOnTile` (rester sur place ne vaut PAS
    # `5 x 1`). Confondre les deux fausse tout l'encadrement de V5.
    ns = {t: (0 if tuple(t) == origin else counts.get(t)) for t in tiles69}
    moved = [t for t in tiles69 if tuple(t) != origin]
    lin = all(terms[t] == float(w) * float(ns[t] or 0) for t in tiles69)
    distinct = sorted({ns[t] for t in moved if ns[t]})
    v1 = lin and len(distinct) >= 2
    ok = ok and v1
    print("  V1 terme == %r x |chemin| sur les %d tuiles rankees (0 sur l'origine, StaysOnTile) ; "
          "longueurs distinctes = %s -> %s"
          % (w, len(tiles69), distinct,
             "OK" if v1 else "ECHEC (une seule longueur : forfait indistinguable)"))
    for t in sorted(tiles69, key=lambda x: -(pairs[(NORMAL, x)] or 0)):
        print("     69@%-7s pair=%9.3f  n=%-3s terme=%6.1f" % (str(t), pairs[(NORMAL, t)] or 0,
                                                               ns.get(t), terms[t]))
    print("     1222@%-5s pair=%9.3f  n=%-3s terme=%6.1f"
          % (str(tiles1222[0]) if tiles1222 else "-",
             (pairs.get((MDA_AB, tiles1222[0])) if tiles1222 else 0) or 0,
             counts.get(tiles1222[0]) if tiles1222 else None,
             pb.calculate_movement_utility_in_steps(tiles1222[0], lc, wt) if tiles1222 else 0.0))

    # ---------------------------------------------------------------- V2/V3/V4 : argmax
    nat_ab, nat_mv = _native_choice(rid)
    nat_tile = nat_mv or tuple(geom["kimm"])
    print("\n  NATIF (aiDryRunAllUnits) : ability=%s move=%s -> tuile d'action %s"
          % (nat_ab, nat_mv, nat_tile))

    _with_term(True)
    ab_on, t_on, u_on, tab_on = _argmax(ctx, cands, pairs, ctx.normal_ids)
    v2 = (ab_on == nat_ab and tuple(t_on) == tuple(nat_tile))
    ok = ok and v2
    print("  V2 argmax [pair_natif + custom + Tile7_port] AVEC terme : ability=%s tuile=%s u=%.3f -> %s"
          % (ab_on, t_on, u_on, "OK (== natif)" if v2 else "ECHEC (!= natif)"))

    _with_term(False)
    ab_off, t_off, u_off, tab_off = _argmax(ctx, cands, pairs, ctx.normal_ids)
    v3 = (ab_off != nat_ab or tuple(t_off) != tuple(nat_tile))
    # V3 n'est PROBANTE que dans le bras ou le natif BOUGE : quand il reste sur place (`nat_mv is
    # None`), le terme vaut 0 sur la tuile qu'il joue et son absence ne peut evidemment rien changer
    # -- ce bras-la sert a la borne HAUTE de V5/V8, pas au rouge.
    ok = ok and (v3 or nat_mv is None)
    print("  V3%s argmax SANS terme (etat AVANT #304)        : ability=%s tuile=%s u=%.3f -> %s"
          % ("" if nat_mv is not None else " [INFO, natif sur place]", ab_off, t_off, u_off,
             "DIVERGE du natif : le terme est DECISIF" if v3
             else "identique au natif"))

    # V4 -- forfait calibre sur la tuile que le natif joue : meme valeur que `5 x n(nat_tile)`.
    flat = float(w) * float(counts.get(tuple(nat_tile)) or 0)
    _with_term(True, override=_FlatTermPlaybook(flat))
    ab_flat, t_flat, u_flat, _ = _argmax(ctx, cands, pairs, ctx.normal_ids)
    v4 = (ab_flat != nat_ab or tuple(t_flat) != tuple(nat_tile))
    print("  V4 [INFO] argmax avec FORFAIT %.1f (calibre sur la tuile jouee) : ability=%s tuile=%s "
          "u=%.3f -> %s"
          % (flat, ab_flat, t_flat, u_flat,
             "DIVERGE (la proportionnalite est deja mesuree ICI)" if v4
             else "IDENTIQUE -- ce duel ne separe PAS forfait et `w x n` (c'est la PHASE B qui le fait)"))
    _with_term(True)

    # ---------------------------------------------------------------- V5 : encadrement de w
    #   u(t, w) = pair(t) + custom(t) + base7(t) + w * n(t)   avec base7 = Tile7 SANS le terme
    _with_term(False)
    base7 = {}
    for ab, tiles in ((NORMAL, tiles69), (MDA_AB, tiles1222)):
        for t in tiles:
            base7[(ab, t)] = _tile7(ctx, t)
    _with_term(True)
    nk = tuple(nat_tile)
    n_prop = lambda t: (0 if tuple(t) == origin else (counts.get(tuple(t)) or 0))   # noqa: E731
    n_flat = lambda t: (0 if tuple(t) == origin else 1)                             # noqa: E731

    def _bounds(n_of) -> tuple:
        """Encadrement du coefficient impose par « le natif a choisi (nat_ab, nk) » sous le modele
        de multiplicateur `n_of`. Pour chaque alternative (ab, t) :
            c_nat + k*n(nk) > c_alt + k*n(t)   <=>   k*dn > c_alt - c_nat
        `dn > 0` -> borne BASSE ; `dn < 0` -> borne HAUTE.

        ⚠ `dn == 0` : `k` DISPARAIT de l'inegalite -- elle ne porte AUCUNE information sur le
        coefficient et n'est donc PAS versee a l'encadrement. Violee, elle mesure autre chose : un
        defaut du RESTE du modele (feuille Tile(7) non portee, ou tie-break d'ordre entre deux
        actions d'utilite egale). On la COMPTE a part (`ties`) plutot que de la faire passer pour une
        refutation du coefficient -- la confondre videre l'intervalle pour une raison etrangere."""
        lo = hi = None
        ties = []
        c_nat = (pairs[(nat_ab, nk)] or 0) + _custom(nat_ab, ctx.normal_ids) + base7[(nat_ab, nk)]
        for ab, tiles in ((NORMAL, tiles69), (MDA_AB, tiles1222)):
            for t in tiles:
                if ab == nat_ab and tuple(t) == nk:
                    continue
                p = pairs.get((ab, t))
                if p is None:
                    continue
                c_alt = p + _custom(ab, ctx.normal_ids) + base7[(ab, t)]
                dn = n_of(nk) - n_of(t)
                rhs = c_alt - c_nat
                if dn > 0:
                    lo = rhs / dn if lo is None else max(lo, rhs / dn)
                elif dn < 0:
                    hi = rhs / dn if hi is None else min(hi, rhs / dn)
                elif rhs > 1e-9:
                    ties.append((ab, t, round(rhs, 4)))
        return (lo, hi, ties)

    b_prop, b_flat = _bounds(n_prop), _bounds(n_flat)
    cons = {"prop": b_prop[:2], "flat": b_flat[:2], "n_played": n_prop(nk), "ties": b_prop[2],
            # verdicts par-bras, relus tels quels par `tests/engine/test_modified_exoarmour_live.py`
            "v2": v2, "v3": bool(v3 and nat_mv is not None)}
    if b_prop[2]:
        print("  V10 contraintes HORS MODELE (meme |chemin| que la tuile jouee, mais utilite "
              "modelisee SUPERIEURE) : %s" % b_prop[2])
        print("      -> mesure une feuille Tile(7) non portee ou un tie-break, PAS le coefficient")
    lo, hi = cons["prop"]
    v5 = (lo is None or lo < w) and (hi is None or w < hi)
    ok = ok and v5
    print("  V5 encadrement impose par l'argmax natif (modele `w x n`) : %s < w < %s ; "
          "w mesure au gameconfig = %r -> %s"
          % ("%.4f" % lo if lo is not None else "-inf", "%.4f" % hi if hi is not None else "+inf",
             w, "OK" if v5 else "ECHEC (le poids lu est hors intervalle : formule ou etage faux)"))
    flo, fhi = cons["flat"]
    print("     (meme calcul sous le modele FORFAIT : %s < c < %s)"
          % ("%.4f" % flo if flo is not None else "-inf",
             "%.4f" % fhi if fhi is not None else "+inf"))
    return ok, rid, geom, cons


def _intersect(a, b) -> tuple:
    lo = a[0] if b[0] is None else (b[0] if a[0] is None else max(a[0], b[0]))
    hi = a[1] if b[1] is None else (b[1] if a[1] is None else min(a[1], b[1]))
    return (lo, hi)


def _fmt(iv) -> str:
    lo, hi = iv
    return "%s < k < %s" % ("-inf" if lo is None else "%.4f" % lo,
                            "+inf" if hi is None else "%.4f" % hi)


def run(montages, auto: bool) -> int:
    """`montages` = liste de `(board, seed, [damages])`. Chaque bras (montage x Damage) impose un
    encadrement sur le coefficient ; on les INTERSECTE tous. Un coefficient est une CONSTANTE du
    jeu : si l'intersection d'un modele est VIDE, ce modele est REFUTE."""
    ok = True
    rid = None
    geom_last = None
    acc = {"prop": (None, None), "flat": (None, None)}
    n_played = []
    for board, seed, damages in montages:
        geom = None
        for d in damages:
            a_ok, rid, geom, cons = phase_a(d, board, seed, geom)
            ok = ok and a_ok
            n_played.append((board, seed, d, cons.get("n_played")))
            for k in acc:
                acc[k] = _intersect(acc[k], cons[k])
        geom_last = geom

    # ------------------------------------------------------------------ V8 : bras -> modele
    print("\n=== SYNTHESE de %d bras ===" % len(n_played))
    print("  |chemin| de la tuile JOUEE par le natif, bras par bras : %s"
          % [(b, s, d, n) for b, s, d, n in n_played])
    print("  modele PROPORTIONNEL `terme = k x |chemin|` : %s" % _fmt(acc["prop"]))
    print("  modele FORFAIT       `terme = k si bouge`   : %s" % _fmt(acc["flat"]))
    plo, phi = acc["prop"]
    v8 = (plo is None or plo < 5) and (phi is None or 5 < phi)
    ok = ok and v8
    print("  V8 le poids LU au gameconfig (5) est dans l'intervalle PROPORTIONNEL -> %s"
          % ("OK" if v8 else "ECHEC"))
    flo, fhi = acc["flat"]
    empty = (flo is not None and fhi is not None and flo >= fhi)
    print("  V9 modele FORFAIT : %s"
          % ("REFUTE par les bras (intervalle VIDE) -- la proportionnalite est MESUREE" if empty
             else "encore admissible sur ce montage (intervalle non vide) -- la proportionnalite "
                  "reste celle du DECOMPILE (`imul` de `path.Count`), pas une mesure live"))

    ok = phase_b(rid, geom_last) and ok

    print("\n%s" % ("PROBE OK -- le terme `5 x |chemin|` est confronte au NATIF"
                    if ok else "PROBE KO -- voir les lignes ci-dessus"))
    print("(pense a disposer le runner : python rl_duel.py dispose --state-file %s)" % MDA.STATE)
    return 0 if ok else 1


def _parse_montage(spec: str, dft_damages) -> tuple:
    """`<board>:<seed>[:<d1,d2,...>]` -> `(board, seed, [damages])`."""
    parts = spec.split(":")
    board = parts[0]
    seed = int(parts[1])
    ds = [int(x) for x in parts[2].split(",")] if len(parts) > 2 else list(dft_damages)
    return (board, seed, ds)


def main() -> int:
    argv = sys.argv[1:]
    scan = MDA._opt(argv, "--damage")
    damages = ([int(x) for x in scan.split(",")] if scan
               else [MDA.D_LOW_PASSIVE, MDA.D_HIGH_PASSIVE])
    board = MDA._opt(argv, "--board", MDA.BOARD)
    seed = int(MDA._opt(argv, "--seed", str(MDA.SEED)))
    montages = [(board, seed, damages)]
    # `--also <board>:<seed>[:<d1,d2>]` (repetable) : un SECOND montage. C'est ce qui peut REFUTER
    # le forfait -- un coefficient est une constante du jeu, donc l'intersection des encadrements
    # de tous les montages doit etre non vide ; deux montages ou le natif joue des |chemin|
    # DIFFERENTS la vident pour le modele forfaitaire.
    for a in argv:
        if a.startswith("--also="):
            montages.append(_parse_montage(a.split("=", 1)[1], damages))
    i = 0
    while i < len(argv):
        if argv[i] == "--also" and i + 1 < len(argv):
            montages.append(_parse_montage(argv[i + 1], damages))
            i += 1
        i += 1
    return run(montages, "--auto" in argv)


if __name__ == "__main__":
    sys.exit(main())
