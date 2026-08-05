"""probe #305 -- le volet SPLASH de `MassDriverAcceleratorPlaybook$$MakeDamagePredictions` (1222).

LE CRITERE, pose AVANT toute methode
------------------------------------
Question binaire : **le port emet-il, pour CHAQUE ennemi du caster adjacent a la cible, l'event de
degat que le natif emet -- avec les MEMES valeurs ?**

Le natif (`IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$MakeDamagePredictions`,
decompile relu sur `rnca9r7q6c`) enchaine DEUX batchs
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`
et concatene le second dans la liste du premier :

    damage = <GetDamage>                       // AActiveAbility$$MinMaxDamage(state, isPrediction: false)
    list   = GenerateMultiHitAttackPredictions(caster, casterPosition, target, <Target>,
                 damage, AActiveAbility$$GetHits, Nullable(AActiveAbility$$GetDamageProfile), null, 0)
    foreach (e in <GetAdjacentAttackTargets>.Select(AbilityEntities(caster: caster, target: target)))
        list.AddRange( GenerateMultiHitAttackPredictions(caster, casterPosition, e,
                           DSLSelectors$$Entity(e), damage, AActiveAbility$$GetHits2,
                           Nullable(AActiveAbility$$GetDamageProfile2), null, 0) )

`GetAdjacentAttackTargets` = `Enemies(caster@0x48, AdjacentUnits(target@0x60, 1, 3), 3)`.
Chaque event SPLASH porte donc sur SON ennemi (selecteur `Entity(e)`), pas sur la cible principale
-- a la difference du quirk Stikkbomb/PlasmaGrenade, ou `param_5` reste le selecteur `Target`.

CE QUI REND LE VOLET OBSERVABLE, et pourquoi ce n'est pas les coups
-------------------------------------------------------------------
Sur la config 1222 : `nrOfHits` = `nrOfHits_2` = 1, et `minDmg_2`/`maxDmg_2` sont EGAUX a
`minDmg`/`maxDmg`. Le volet ne se distingue donc NI par les coups NI par la base. Le seul
discriminant de VALEUR est le PROFIL : `damageProfile` = `DirectDamage` (PiercingRatio **100**)
pour le batch principal, `damageProfile_2` = `Physical` (PiercingRatio **1**) pour le splash.
D'ou `--armor-target` HAUT dans ce montage : plus la cible est blindee, plus les deux profils
s'ecartent, et plus une confusion des deux serait VISIBLE.

MONTAGE (herite de `MDA_FIXTURE`, board MC1_67 seed 909, `votanChampion` injecte par catalog_inject)
----------------------------------------------------------------------------------------------------
  - Kimm (`votanChampion`) reste a son SPAWN -- **jamais deplacee** : un `act move` consomme son
    mouvement et rend 1222 ILLEGALE (`MassDriverAcceleratorAbility$$GetDynamicInvalidTargetReason`
    refuse quand `GetPossibleMoveTiles` est vide).
  - cible `tauCrisis` a distance hex 2 de Kimm (1222 refuse une cible adjacente).
  - **DEUX ennemis SUPPLEMENTAIRES** (`a_units` etendu) : ce sont EUX le levier. Bras n=0 -> tous
    deux LOIN de la cible ; n=1 -> un seul sur un voisin de la cible ; n=2 -> les deux.
    Un bras SANS ennemi adjacent est OBLIGATOIRE : sans lui, on ne saurait pas distinguer
    « le port emet le splash » de « le port emet toujours un event de trop ».
  - la tuile d'attaque reservee par la geometrie de la fixture reste LIBRE dans TOUS les bras :
    sans cela, 1222 n'aurait plus de tuile de charge et le bras ne mesurerait rien.
  - appats allies et porteurs d'aura de degat parques LOIN (`MDA.set_arm(rid, 0, geom)`), comme
    dans #27-r1 : leurs auras modifieraient la prediction et seraient un confond.

VERDICTS RENDUS
---------------
  V1 EXERCICE   : le natif emet bien `1 + n` events, et les `targetId` des events supplementaires
                  sont EXACTEMENT les ennemis poses adjacents -- sinon le montage n'exerce rien.
  V2 ACCORD     : port == natif sur l'ENSEMBLE des events (targetIds, coups, bornes de degat)
                  dans les TROIS bras.
  V3 MUTATION-A : SET du splash force a VIDE -> le port doit REDEVENIR rouge en n=1/n=2 et rester
                  vert en n=0. Prouve que l'accord vient du volet porte, pas d'un hasard.
  V4 MUTATION-B : `aoe_overrides` retire (le splash herite alors du profil DirectDamage du batch
                  principal) -> le port doit REDEVENIR rouge sur les VALEURS des events splash.
                  C'est la preuve que la GARDE `damageProfile_2` discrimine.
  V5 CONTRASTE  : ecart natif MESURE entre l'event principal et un event splash -- si les deux
                  profils rendaient la meme chose, V4 ne prouverait rien.

Usage :
    python probe_305_massdriver_splash.py                     # MC1_67 / 909
    python probe_305_massdriver_splash.py --board C4_09 --seed 31337
    python probe_305_massdriver_splash.py --armor 4000 --damage 1000
ASCII only.
"""
from __future__ import annotations

import sys

import probe_27_3_live as L
import probe_27_r1_massdriver_custom as MDA
from engine.entities.active_ability_type import ActiveAbilityType

#: MEMBRE (#270-r1 volet 2), et LOAD-BEARING : ce probe ECRIT cette cle dans
#: `_MAKE_DMG_INPUT_OVERRIDES` pour poser sa contre-epreuve, puis la restaure. Toute ecriture sur
#: ces tables porte un membre -- une affectation sur cle ABSENTE creerait sinon une cle non typee.
MDA_AB = ActiveAbilityType.MassDriverAccelerator  # 1222
DEFAULT_DAMAGE = 1000
DEFAULT_ARMOR = 3000

# Camp ADVERSE : la cible de la fixture + DEUX ennemis qui servent de leviers d'adjacence.
VID_SPLASH1, VID_SPLASH2 = "ultraTitus", "emperNoiseMarine"
A_UNITS = "%s,%s,%s" % (MDA.VID_TARGET, VID_SPLASH1, VID_SPLASH2)

# ARMURES DISTINCTES pour les deux ennemis-leviers -- ce n'est pas du confort d'affichage, c'est ce
# qui rend la confrontation PAR CIBLE probante. `--armor-target` pose la MEME armure sur tout le
# camp adverse ; les trois events sortent alors avec des bornes IDENTIQUES (mesure du premier
# lancement : principal [5385,8078], splash(79) [54,2453], splash(81) [54,2453]). Un port qui
# predirait le splash contre la MAUVAISE entite -- par exemple contre la cible principale, le quirk
# de `StikkbombPlaybook`/`PlasmaGrenadePlaybook` -- passerait alors sur les VALEURS et ne serait
# attrape que par le `targetId`. En donnant a chaque levier SON armure, chaque event a SA borne :
# le contenu discrimine autant que l'etiquette.
SPLASH_STATS = ("%s:Armor=1200,FixedArmor=1200" % VID_SPLASH1,
                "%s:Armor=5200,FixedArmor=5200" % VID_SPLASH2)

# Champs confrontes event par event. `kill`/`killSure` sont EXCLUS a dessein : ils derivent d'un
# `block_amount` que le decodeur natif n'expose pas et que `engine_agreement_stages` RECALCULE --
# les inclure melangerait un desaccord de recalcul a la mesure du volet.
CMP_KEYS = ("appliedHits", "healthDmgMin", "healthDmgMax", "rawHealthDmgMin", "rawHealthDmgMax")


# ------------------------------------------------------------------ geometrie du splash
def derive_splash_geometry(rid: int, geom: dict) -> dict:
    """Tuiles ou poser les deux ennemis-leviers, DERIVEES du board vivant.

    `adj` = voisins WALKABLE de la tuile de la CIBLE (adjacence NATIVE du `boardGraph`, jamais
    hexgeo), MOINS la tuile d'attaque reservee par la fixture et MOINS la tuile de Kimm : la tuile
    d'attaque doit rester LIBRE, sinon 1222 perd sa tuile de charge et le bras ne mesure rien.
    `far` = tuiles walkable a distance >= 4 de la cible ET >= 4 de Kimm : le bras n=0."""
    import hexgeo
    bg = L._rpc("boardGraph", [{"runnerId": rid}])
    tiles = bg.get("tiles") or []
    by_id = {t.get("id"): t for t in tiles}
    enemy = tuple(geom["enemy"])
    kimm = tuple(geom["kimm"])
    attack_tile = tuple(geom["attack_tile"])
    etile = next((t for t in tiles if (t.get("col"), t.get("row")) == enemy), None)
    if etile is None:
        raise SystemExit("tuile de la cible %s introuvable au boardGraph" % (enemy,))
    banned = {attack_tile, kimm} | set(map(tuple, geom["baits"].values()))
    adj = [(by_id[i]["col"], by_id[i]["row"]) for i in (etile.get("neighbours") or [])
           if i in by_id and by_id[i].get("walkable")
           and (by_id[i]["col"], by_id[i]["row"]) not in banned]
    if len(adj) < 2:
        raise SystemExit(
            "la cible n'a que %d voisin(s) walkable LIBRE(s) hors tuile d'attaque : il en faut >= 2 "
            "pour les bras n=1 et n=2 -- changer de board/seed" % len(adj))
    far = [(t.get("col"), t.get("row")) for t in tiles
           if t.get("walkable") and hexgeo.distance((t.get("col"), t.get("row")), enemy) >= 4
           and hexgeo.distance((t.get("col"), t.get("row")), kimm) >= 4
           and (t.get("col"), t.get("row")) not in banned]
    far = sorted(set(far) - set(map(tuple, geom["aura_far"].values()))
                 - set(map(tuple, geom["bait_far"].values())))
    if len(far) < 2:
        raise SystemExit("moins de 2 tuiles walkable a distance >= 4 de la cible ET de Kimm : "
                         "impossible de parquer les ennemis-leviers hors du montage")
    return {"adj": adj[:2], "far": far[:2]}


def _report_armor(rid: int) -> None:
    """CONTROLE DE MONTAGE : `--unit-stat` doit bien AVOIR MORDU par-dessus `--armor-target` (qui
    pose une valeur unique sur tout le camp). Si les trois armures sortent egales, la confrontation
    par cible perd son mordant -- on le DIT au lieu de le decouvrir dans les chiffres."""
    obs = L._rpc("observeBattle", [{"runnerId": rid}])
    for u in (obs.get("units") or []):
        vid = u.get("visualId")
        if vid in (MDA.VID_TARGET, VID_SPLASH1, VID_SPLASH2):
            print("    armure vue : %-18s id=%-4s armor=%-6s hp=%s"
                  % (vid, u.get("id"), u.get("armor"), u.get("hp")))


def resolve_splash_units(rid: int) -> tuple[int, int]:
    """Ids d'entite REELS des deux ennemis-leviers (par `visualId`) -- ils dependent du plateau,
    comme les six roles de la fixture ; jamais figes."""
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    by_vid = {u.get("visualId"): u.get("id") for u in (dv.get("units") or [])}
    missing = [v for v in (VID_SPLASH1, VID_SPLASH2) if by_vid.get(v) is None]
    if missing:
        raise SystemExit("ennemis-leviers absents du runner : %s (roster incomplet ?)" % missing)
    return by_vid[VID_SPLASH1], by_vid[VID_SPLASH2]


def set_splash_arm(rid: int, n: int, sg: dict, units: tuple) -> None:
    """n = nombre d'ENNEMIS DU CASTER adjacents a la CIBLE (0, 1 ou 2)."""
    want = [(u, "%d,%d" % (sg["adj"][i] if i < n else sg["far"][i]))
            for i, u in enumerate(units)]
    for u, to in want:
        MDA._move(rid, u, to)
    MDA._assert_placed(rid, want)


# ------------------------------------------------------------------ mesure
def _ranked_tiles(ctx, ability: int) -> list:
    """Tuiles d'attaque LEGALES pour `ability` sur la cible du montage, telles que le natif les
    range (`attackPlans[].evals[].ranked` = `GetBestTileToAttackFrom`)."""
    plan = ctx.plans.get(ctx.uid) or {}
    for ev in (plan.get("evals") or []):
        if ev.get("abilityId") == ability and ev.get("targetId") == MDA.TARGET:
            return [(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])]
    return []


def _native_events(rid: int, tile) -> list:
    """`aiPlaybookPredict` = `<Ability>Playbook.MakeDamagePredictions` NATIF, depuis `tile`
    (`UnitPosition` a la tuile candidate). C'est LA liste que le scorer de decision consomme."""
    r = L._rpc("aiPlaybookPredict", [{"runnerId": rid, "unitId": MDA.CASTER,
                                      "targetId": MDA.TARGET, "abilityType": MDA_AB,
                                      "col": int(tile[0]), "row": int(tile[1])}])
    return (r.get("events") or []) if r.get("ok") else []


def _nat_fields(ev: dict) -> dict:
    hp = ev.get("hpBefore") or 0
    return {"appliedHits": ev.get("appliedHits") or 0,
            "healthDmgMin": min(ev.get("healthDmgMin") or 0, hp),
            "healthDmgMax": min(ev.get("healthDmgMax") or 0, hp),
            "rawHealthDmgMin": ev.get("willKillDmg") or 0,
            "rawHealthDmgMax": ev.get("mightKillDmg") or 0}


def _by_target(rows: list) -> dict:
    out: dict = {}
    for tid, f in rows:
        out.setdefault(tid, []).append(f)
    return out


def confront(ctx, rid: int, tile) -> dict:
    """Confronte l'ENSEMBLE des events (pas seulement l'event principal) pour la paire
    (Kimm, cible) depuis `tile`. Rend {nat, off, deltas, missing, extra}."""
    from engine.playbook import get_playbook_or_default
    nat = _by_target([(e.get("targetId"), _nat_fields(e)) for e in _native_events(rid, tile)])
    pb = get_playbook_or_default(MDA_AB)
    off_evs = pb.make_damage_predictions(ctx, tile, MDA.TARGET, MDA_AB) or []
    off = _by_target([(e.target, {k: e.composite_fields().get(k) for k in CMP_KEYS})
                      for e in off_evs])
    deltas, missing, extra = [], [], []
    for tid, nevs in nat.items():
        oevs = off.get(tid)
        if not oevs:
            missing.append(tid)
            continue
        if len(oevs) != len(nevs):
            deltas.append({"target": tid, "field": "n_events",
                           "nat": len(nevs), "off": len(oevs)})
        for nf, of in zip(nevs, oevs):
            for k in CMP_KEYS:
                if nf.get(k) != of.get(k):
                    deltas.append({"target": tid, "field": k, "nat": nf.get(k), "off": of.get(k)})
    for tid in off:
        if tid not in nat:
            extra.append(tid)
    return {"nat": nat, "off": off, "deltas": deltas, "missing": missing, "extra": extra,
            "match": not deltas and not missing and not extra}


def measure_arm(rid: int, n: int, sg: dict, units: tuple) -> dict:
    """Un bras complet : pose les ennemis, reconstruit le contexte, confronte sur CHAQUE tuile
    d'attaque rankee par le natif pour 1222."""
    import probe_312_votan_prediction_gap as P312
    set_splash_arm(rid, n, sg, units)
    ctx, _wt, _sid, _dv, _mov = P312._build_ctx(rid)
    tiles = _ranked_tiles(ctx, MDA_AB)
    if not tiles:
        raise SystemExit(
            "aucune tuile d'attaque rankee pour 1222 au bras n=%d -- l'ability est devenue "
            "ILLEGALE (tuile de charge occupee ? Kimm deplacee ?). On ne mesure PAS." % n)
    return {"n": n, "tiles": tiles,
            "rows": [{"tile": t, "res": confront(ctx, rid, t)} for t in tiles],
            "ctx": ctx}


# ------------------------------------------------------------------ mutations adversariales
def _mutate(kind: str):
    """Rend `(restore_callable)` apres avoir MUTE le port. Deux mutations INDEPENDANTES :

      'set'      -- `MassDriverAcceleratorAbility.get_aoe_targets` rend [] : le volet n'existe plus.
      'profile'  -- `_mass_driver_accelerator_inputs` ne rend plus `aoe_overrides` : le splash
                    HERITE alors des coups ET du profil du batch principal (DirectDamage), donc
                    des valeurs FAUSSES. C'est la garde de VALEUR qu'on veut voir discriminer."""
    from engine.entities.abilities import active_ability as AA
    from engine.playbook.prediction import abilities as PA
    if kind == "set":
        orig = AA.MassDriverAcceleratorAbility.get_aoe_targets
        AA.MassDriverAcceleratorAbility.get_aoe_targets = lambda self, ctx: []

        def _restore():
            AA.MassDriverAcceleratorAbility.get_aoe_targets = orig
        return _restore
    if kind == "profile":
        orig = PA._MAKE_DMG_INPUT_OVERRIDES[MDA_AB]

        def _no_aoe(scene, caster_id, target_id, ab, cfg):
            d = dict(orig(scene, caster_id, target_id, ab, cfg))
            d.pop("aoe_overrides", None)
            return d
        PA._MAKE_DMG_INPUT_OVERRIDES[MDA_AB] = _no_aoe

        def _restore():
            PA._MAKE_DMG_INPUT_OVERRIDES[MDA_AB] = orig
        return _restore
    raise SystemExit("mutation inconnue: %s" % kind)


def measure_mutated(rid: int, arm: dict, kind: str) -> dict:
    """RE-confronte le MEME bras (memes positions, meme contexte) avec le port MUTE."""
    restore = _mutate(kind)
    try:
        ctx = arm["ctx"]
        return {"n": arm["n"],
                "rows": [{"tile": r["tile"], "res": confront(ctx, rid, r["tile"])}
                         for r in arm["rows"]]}
    finally:
        restore()


# ------------------------------------------------------------------ rapport
def _arm_ok(arm: dict) -> bool:
    return all(r["res"]["match"] for r in arm["rows"])


def report(arms: list, muts: dict, adj_ids: dict) -> int:
    ok = True
    print("\n=== V1 -- EXERCICE : le natif emet-il 1 + n events, sur les BONNES cibles ? ===")
    for arm in arms:
        n = arm["n"]
        want = set(adj_ids[n])
        for r in arm["rows"]:
            nat = r["res"]["nat"]
            got = set(nat) - {MDA.TARGET}
            n_ev = sum(len(v) for v in nat.values())
            good = (n_ev == 1 + n) and (got == want)
            ok = ok and good
            print("  n=%d tuile=%-8s natif: %d event(s), cibles=%s (attendu %d, %s) -> %s"
                  % (n, str(r["tile"]), n_ev, sorted(nat), 1 + n, sorted(want) or "aucune",
                     "OK" if good else "NON EXERCE -- ce bras ne conclut RIEN"))

    print("\n=== V2 -- ACCORD port <-> natif sur l'ENSEMBLE des events ===")
    for arm in arms:
        for r in arm["rows"]:
            res = r["res"]
            print("  n=%d tuile=%-8s %s" % (arm["n"], str(r["tile"]),
                                            "MATCH" if res["match"] else "DELTA"))
            for d in res["deltas"]:
                print("        cible=%-4s %-16s natif=%-9s port=%-9s"
                      % (d["target"], d["field"], d["nat"], d["off"]))
            for tid in res["missing"]:
                print("        cible=%-4s ABSENTE du port (le natif la predit)" % tid)
            for tid in res["extra"]:
                print("        cible=%-4s EN TROP dans le port (le natif ne la predit pas)" % tid)
        ok = ok and _arm_ok(arm)

    for kind, label, why in (("set", "V3 MUTATION-A (SET du splash force a VIDE)",
                              "un terme de splash aurait ete OBSERVABLE"),
                             ("profile", "V4 MUTATION-B (aoe_overrides retire -> profil du "
                                         "batch principal)",
                              "la garde `damageProfile_2` DISCRIMINE")):
        print("\n=== %s ===" % label)
        seen = []
        for arm in muts[kind]:
            for r in arm["rows"]:
                m = r["res"]["match"]
                if arm["n"] > 0 and not m:
                    seen.append((arm["n"], r["tile"]))
                print("  n=%d tuile=%-8s port MUTE %s%s"
                      % (arm["n"], str(r["tile"]), "MATCH" if m else "DELTA",
                         "" if arm["n"] else "   (bras n=0 : le volet est inerte, MATCH attendu)"))
                if arm["n"] == 0 and not m:
                    ok = False
                    print("        ^ ATTENDU MATCH : la mutation touche un bras SANS ennemi "
                          "adjacent -> elle deborde de son perimetre")
        ok = ok and bool(seen)
        print("  -> %s" % ("DIVERGE sur %s : %s" % (seen, why) if seen
                           else "aucune divergence -> le montage NE PROUVE RIEN"))

    print("\n=== V5 -- CONTRASTE natif principal (DirectDamage) vs splash (Physical) ===")
    contrast = False
    for arm in arms:
        if arm["n"] == 0:
            continue
        for r in arm["rows"]:
            nat = r["res"]["nat"]
            main = (nat.get(MDA.TARGET) or [{}])[0]
            for tid, evs in nat.items():
                if tid == MDA.TARGET:
                    continue
                s = evs[0]
                diff = (main.get("rawHealthDmgMin"), s.get("rawHealthDmgMin"))
                contrast = contrast or (diff[0] != diff[1])
                # `health` est le RAW cape par les PV de la cible : les afficher tous deux rend
                # visible le regime `--splash-hp` (cap actif <=> health < raw).
                print("  n=%d tuile=%-8s principal raw=[%s,%s] health=[%s,%s] | splash(cible %s) "
                      "raw=[%s,%s] health=[%s,%s]"
                      % (arm["n"], str(r["tile"]), main.get("rawHealthDmgMin"),
                         main.get("rawHealthDmgMax"), main.get("healthDmgMin"),
                         main.get("healthDmgMax"), tid, s.get("rawHealthDmgMin"),
                         s.get("rawHealthDmgMax"), s.get("healthDmgMin"),
                         s.get("healthDmgMax")))
    print("  -> %s" % ("les deux profils rendent des valeurs DIFFERENTES : V4 a du mordant"
                       if contrast else "valeurs IDENTIQUES -- V4 ne prouve rien sur ce montage "
                                        "(monter `--armor` ou changer de cible)"))

    print("\n%s" % ("PROBE OK -- le volet splash de 1222 est porte, exerce et discrimine"
                    if ok else "PROBE KO -- voir les lignes ci-dessus"))
    print("(pense a disposer le runner : python rl_duel.py dispose --state-file %s)" % MDA.STATE)
    return 0 if ok else 1


def run_scenario(board: str = MDA.BOARD, seed: int = MDA.SEED, damage: int = DEFAULT_DAMAGE,
                 armor: int = DEFAULT_ARMOR, splash_hp: int = 0, verbose: bool = True) -> dict:
    """Monte le montage complet et rend `{arms, muts, adj_ids, rid, geom, sg}`.
    SOURCE UNIQUE du scenario : le `main()` de ce probe ET le test de garde
    `tests/engine/test_mass_driver_splash_prediction_live.py` passent par ICI."""
    stats = list(SPLASH_STATS)
    if splash_hp:
        # REGIME « splash LETAL » : PV bas sur les deux leviers -> `healthDmg` est CAPE par les PV
        # et decroche de `rawHealthDmg`. Exerce l'etage de cap sur des events SPLASH, pas seulement
        # sur l'event principal. (`--hp-target` est INUTILISABLE ici : il remettrait Armor et
        # FixedArmor a 0 sur TOUT le camp adverse, donc supprimerait le discriminant de profil.)
        stats += ["%s:Health=%d,RemainingHealth=%d" % (v, splash_hp, splash_hp)
                  for v in (VID_SPLASH1, VID_SPLASH2)]
    # `derive=True` : le roster ADVERSE est etendu, donc les tuiles FIGEES de la fixture de
    # reference ne sont plus libres (mesure : `ultraTitus` spawne sur le `aura_far` (6,7)).
    rid, geom = MDA.build_fixture(damage, with_passive=False, board=board, seed=seed,
                                  a_units=A_UNITS, derive=True, unit_stats=stats,
                                  extra_args=["--armor-target", str(armor)])
    if verbose:
        print("--- runner=%d board=%s seed=%d Damage=%d armor-target=%d splash-hp=%s ---"
              % (rid, board, seed, damage, armor, splash_hp or "-"))
        print("    leviers : %s" % " ".join(stats))
        _report_armor(rid)
    MDA.set_arm(rid, 0, geom)               # appats allies + auras : LOIN dans tous les bras
    units = resolve_splash_units(rid)
    sg = derive_splash_geometry(rid, geom)
    if verbose:
        print("    geometrie : Kimm=%s cible=%s tuile d'attaque=%s | splash adj=%s far=%s"
              % (geom["kimm"], geom["enemy"], geom["attack_tile"], sg["adj"], sg["far"]))
    arms, adj_ids = [], {}
    for n in (0, 1, 2):
        arms.append(measure_arm(rid, n, sg, units))
        adj_ids[n] = list(units[:n])
    muts = {}
    for kind in ("set", "profile"):
        muts[kind] = []
        for arm in arms:
            set_splash_arm(rid, arm["n"], sg, units)     # re-pose les positions du bras
            muts[kind].append(measure_mutated(rid, arm, kind))
    return {"arms": arms, "muts": muts, "adj_ids": adj_ids, "rid": rid, "geom": geom, "sg": sg}


def main() -> int:
    argv = sys.argv[1:]
    res = run_scenario(board=MDA._opt(argv, "--board", MDA.BOARD),
                       seed=int(MDA._opt(argv, "--seed", str(MDA.SEED))),
                       damage=int(MDA._opt(argv, "--damage", str(DEFAULT_DAMAGE))),
                       armor=int(MDA._opt(argv, "--armor", str(DEFAULT_ARMOR))),
                       splash_hp=int(MDA._opt(argv, "--splash-hp", "0")))
    return report(res["arms"], res["muts"], res["adj_ids"])


if __name__ == "__main__":
    sys.exit(main())
