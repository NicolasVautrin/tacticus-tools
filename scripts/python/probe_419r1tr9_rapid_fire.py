"""#419-r1 tranche 9 -- MONTAGE NOMME de la face ATTACK de `RapidFire` (1135), natif contre port.

`IdunBattle.AI.Playbook.Loki.RapidFirePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`
estime l'utilite du SECOND tir qu'une unite immobile obtient de ce passif : 0 si la tuile evaluee
n'est pas celle ou le caster se tient, 0 si l'ability du case n'est pas une attaque reguliere, 0 si
le caster porte `UnitFlag.Moved`, 0 si l'attaque normale GENERIQUE (`ActiveAbilityType.
Loki_NormalAttack` = 0x45) n'a aucune cible legale depuis cette tuile ; sinon le MAXIMUM, borne en
bas par 0, de `CalculateUtilityFromDamageEvent` sur chacune de ces cibles. RE complete et lectures
non devinables : `engine/playbook/rapid_fire.py` (en-tete).

## Pourquoi une GREFFE, et sur quel hote

Les 4 porteurs de `RapidFire` sont 3 npc `ultra*Intercessor*` + le SUMMON `ultraSmnHeavyIntercessor`
-- aucun HERO, donc aucun `--p-units` possible (`buildNormalizedBC` refuse tout npc), et un summon
s'OBSERVE mais ne se COMMANDE pas (#291). La greffe est LEGITIME ici et c'est LU, pas suppose : le
corps ne consulte du caster que sa POSITION (`GetMainTile`), son FLAG `Moved` et son ensemble de
cibles d'attaque normale -- ni stat, ni trait, ni variable d'ability (le delegue `getUtilityVal`
n'est meme pas capture par la SM). `catalog_inject.graft_passive_ability` pose les deux ecritures.

## Les TROIS regimes, et ce que chacun est SEUL a trancher

* `--regime home` (defaut) -- hote `orksWarboss` (HERO au pool, attaque normale = 69), passifs
  REMPLACES par le seul `RapidFire`. Trois cibles a portee depuis la tuile de mesure. Lignes :
  - `HOME`  : la tuile COURANTE du caster, une ligne par cible -> le terme est NON NUL ;
  - `MOVE`  : une tuile de DEPLACEMENT d'ou l'attaque reste legale -> gate 1, terme NUL ;
  - `MOVED` : le caster est REELLEMENT deplace sur cette meme tuile, puis on re-mesure DEPUIS elle
              -> la gate 1 est desormais satisfaite, et le terme reste NUL : c'est la gate `Moved`.
  ⚠ C'est le couple `MOVE`/`MOVED` qui epingle les deux gates sans circularite : le natif rend la
  MEME valeur, au bit pres, avant et apres le deplacement. Si seule la gate 1 existait, la seconde
  mesure porterait le terme ; si seule la gate 3 existait, la premiere le porterait.

* `--regime kill` -- meme hote, mais deux cibles aux PV COURANTS abaisses (`RemainingHealth`, le
  champ que le natif lit vraiment) : l'une dans `]rawMin, rawMax]` (kill POSSIBLE, pas garanti),
  l'autre `<= rawMin` (kill GARANTI). C'est le seul regime ou `Fix64.Half` et le `ValidTargets.
  Remove` mordent -- les deux sont inertes a PV pleins.

* `--regime foreign` -- hote `templAggressor`, dont l'attaque normale est CONCRETE
  (`Boltstorm_NormalAttack` = 1128, greffe en `replace=False` pour la conserver). Son
  `ActiveAbilityComponent` ne contient PAS `0x45`, donc `AttackQuery$$GetValidTargets` LogError et
  rend `ValidTargets.Empty` : le terme natif est NUL alors que les memes cibles sont a portee. Ce
  regime est le SEUL a distinguer le LITTERAL `0x45` du `NormalAttackType` du caster -- et il
  MESURE le trou qu'un port ecrit avec `case.AbilityType` laisserait.

`EXPECTED` n'est pas un scalaire pose en dur ici : le terme est une utilite de degat complete. Ce
qui est pose en dur, c'est le SIGNE de chaque ligne (`> 0` en `HOME`, `== 0` en `MOVE`/`MOVED`/
`foreign`) et l'egalite natif/port a `EPS` pres, plus les contre-epreuves ci-dessous.

## Contre-epreuves -- critere = DEPLACEMENT par rapport au port NON MUTE

Jamais l'ecart au natif : la paire porte des residus hors-perimetre (mesure : 0.0234 sur une tuile
du board `MC1_67`), donc `abs(port - natif) > EPS` serait VRAI meme pour un mutant inerte.

  `no_home_gate`   -- gate 1 retiree               -> mord en `home` (ligne MOVE)
  `no_moved_gate`  -- gate 3 (`UnitFlag.Moved`) retiree -> mord en `home` (ligne MOVED)
  `sum_not_max`    -- somme au lieu de `Fix64.Max` -> mord des qu'il y a >= 2 cibles
  `pred_target_hp` -- PV/bouclier repris de la PREDICTION au lieu de l'ENTITE de l'event -> mord
                      des que deux cibles n'ont pas les memes PV
  `always_one`     -- `Fix64.One` inconditionnel   -> mord en `kill` (cible a kill POSSIBLE)
  `no_remove`      -- `ValidTargets.Remove` saute  -> mord en `kill` (cible a kill GARANTI)
  `case_ability`   -- ensemble de cibles demande a l'attaque normale CONCRETE du caster au lieu du
                      litteral `0x45`               -> mord en `foreign`

Usage :
    python scripts/python/probe_419r1tr9_rapid_fire.py --state-file <chemin ABSOLU>
        [--regime home|kill|foreign] [--mutants]

ASCII only. Garde jumelle :
`scripts/python/tests/engine/test_419r1tr9_rapid_fire_live.py`.
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

import catalog_inject                                            # noqa: E402
import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
import probe_380_seed_bc_patch_survival as P380                  # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType         # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402

BOARD = "MC1_67"
SEED = "41135"
ABILITY = int(TriggeredAbilityType.RapidFire)                    # 1135
NORMAL_69 = int(ActiveAbilityType.Loki_NormalAttack)             # 0x45
EPS = 1e-4                      # Fix64 natif contre float du port

# Hote de greffe par regime. `home`/`kill` : `orksWarboss` -- HERO au pool, attaque normale = 69,
# et REPLACE=True le prive de son propre passif (`LightImUp`) pour isoler la mesure. `foreign` :
# `templAggressor`, dont le passif `Boltstorm` porte l'attaque normale CONCRETE 1128 -> greffe
# ADDITIVE (`replace=False`), sans quoi le regime disparaitrait avec le passif.
HOSTS = {"home": ("orksWarboss", True), "kill": ("orksWarboss", True),
         "remove": ("orksWarboss", True), "foreign": ("templAggressor", False)}
# Geometrie par regime : `near` = les trois cibles a distance 2 (le `Fix64.Max` tranche entre
# elles) ; `solo` = UNE cible a distance 2 et les deux autres HORS de toute portee (>= 5), pour que
# `ValidTargets.Remove` de la cible du case vide reellement l'ensemble.
LAYOUT = {"home": "near", "kill": "near", "remove": "solo", "foreign": "near"}
# Les trois cibles : aucune n'INVOQUE (un summon adverse occuperait des tuiles du montage) et leurs
# PV max sont distincts, ce qui rend le `combinedMax` par cible discriminant.
FOES = "astraBullgryn,tauAunShi,necroWarden"
HP_CASTER = 400000              # le caster ne doit jamais mourir pendant le placement
# `kill` : PV COURANTS abaisses (`RemainingHealth`, le champ que le natif lit ; `Health` seul NE
# MORD PAS). Les seuils sont VERIFIES contre les verdicts natifs MESURES, jamais supposes -- et le
# montage REFUSE si l'un des deux regimes ne s'installe pas.
# ⚠ `necroWarden` est ECARTE de ce patch : mesure #419-r1-tr9, `RemainingHealth=300` y ressort a
# 2008 apres le placement (cause non etablie -- l'unite est la seule Necron du roster) alors que le
# meme patch mord sur `tauAunShi` et `astraBullgryn`. On ne devine pas : on choisit les deux cibles
# ou le levier est MESURE mordant, et on laisse la troisieme a PV pleins.
KILL_STATS = {
    "kill": "astraBullgryn:RemainingHealth=300;tauAunShi:RemainingHealth=1000",
    "remove": "astraBullgryn:RemainingHealth=300",
}

MUST_BITE = {
    "home": ("no_home_gate", "no_moved_gate", "sum_not_max", "pred_target_hp"),
    "kill": ("sum_not_max", "pred_target_hp", "always_one"),
    "remove": ("no_remove",),
    "foreign": ("case_ability",),
}
MUTANTS = ("no_home_gate", "no_moved_gate", "sum_not_max", "pred_target_hp",
           "always_one", "no_remove", "case_ability")


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


def pair_port_muted(ctx, ab, tgt, tile) -> float:
    """Le port avec le playbook 1135 RETIRE du registre -- la reference qui isole le terme."""
    import engine.playbook.psyker as PSY
    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
    if saved is None:
        raise MontageError(f"le playbook {ABILITY} n'est PAS au registre -- rien a isoler")
    try:
        return pair_port(ctx, ab, tgt, tile)
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved


# --------------------------------------------------------------------------- montage

def _seed_bc(regime: str, logs_dir: str, arm: str) -> str:
    """Le seed BC du bras `graft` (le passif 1135 EST monte) ou du bras `base` (il ne l'est PAS,
    tout le reste identique -- meme hote, memes autres passifs, memes stats, meme catalogue).

    Le bras `base` est ce qui rend le terme MESURABLE : `terme_natif = natif_graft - natif_base`.
    Sans lui, on ne pourrait qu'opposer le natif au port MUTE, ce qui MELANGE le terme et les
    residus hors-perimetre du couple (caster, cible) -- et il y en a (mesure : 0.022 sur une paire
    du montage)."""
    host, replace = HOSTS[regime]
    out = os.path.join(logs_dir, f"rf_{regime}_{arm}_seedbc.json")
    p, reports = catalog_inject.write_grafted_seed_bc(
        out, [f"{host}:{TriggeredAbilityType(ABILITY).name}"], replace=replace)
    rep = reports[0]
    after = list(rep.get("passiveAbilitiesAfter") or ())
    if ABILITY not in after:
        raise MontageError(f"greffe RATEE : PassiveAbilities={after} ne contient pas {ABILITY}")
    if arm == "base":
        # Le bras apparie est le bras greffe MOINS 1135 -- surtout PAS « les passifs d'origine » :
        # avec `replace=True`, la greffe a DEJA retire le passif natif de l'hote (`LightImUp` sur
        # `orksWarboss`), et le remettre ici ferait differer les deux bras de DEUX abilities. Mesure
        # #419-r1-tr9 : `LightImUp` valait +16.75 sur une tuile de melee du montage, entierement
        # attribue au socle par un bras mal apparie.
        bc = json.loads(open(p, encoding="utf-8").read())
        keep = [a for a in after if a != ABILITY]
        for u in (bc.get("Units") or ()):
            if u.get("Id") == host:
                u["PassiveAbilities"] = keep
        open(p, "w", encoding="utf-8").write(json.dumps(bc))
    P380.assert_survives(p)
    return str(p)


def _build(state_file: str, regime: str, logs_dir: str, arm: str = "graft") -> int:
    host, _replace = HOSTS[regime]
    stats = f"{host}:Health={HP_CASTER},RemainingHealth={HP_CASTER}"
    if regime in KILL_STATS:
        stats = stats + ";" + KILL_STATS[regime]
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
            "--seed-bc", _seed_bc(regime, logs_dir, arm), "--p-units", host, "--a-units", FOES,
            "--unit-stat", stats, "--state-file", state_file]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def _fresh_ctx(rpc, rid, cid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return dv, _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))


def _normal_ability_id(rpc, rid, uid) -> int:
    """L'`ActiveAbilityType` CONCRET de l'attaque normale de `uid` (`abilityTargets`, `kind ==
    normal`). C'est ce que le case porte -- et ce que le litteral `0x45` du playbook n'est PAS
    forcement."""
    r = rpc("abilityTargets", {"runnerId": rid, "unitId": uid}, 60) or {}
    for u in (r.get("units") or ()):
        if u.get("unitId") != uid:
            continue
        for a in (u.get("abilities") or ()):
            if a.get("kind") == "normal":
                return int(a.get("abilityId"))
    raise MontageError(f"u{uid} n'a pas d'attaque normale au canal abilityTargets")


def _from_here(rpc, rid, uid, ability_id) -> list:
    r = rpc("abilityTargets", {"runnerId": rid, "unitId": uid, "abilityType": ability_id}, 60) or {}
    for u in (r.get("units") or ()):
        for a in (u.get("abilities") or ()):
            if int(a.get("abilityId") or -1) == int(ability_id):
                return [t.get("targetId") for t in (a.get("fromHere") or ())
                        if t.get("kind") == "unit"]
    raise MontageError(f"abilityTargets({ability_id}) n'a pas rendu d'entree pour u{uid} : {r}")


def _find_layout(cells, elev, walk, mode: str = "near"):
    """`(C, [E1, E2, E3])`.

    `near` : une tuile de caster a >= 3 voisins de mouvement, et TROIS tuiles d'ennemi a distance
    EXACTEMENT 2 de `C` (JAMAIS adjacentes -- l'adjacence bascule l'arme en melee et changerait le
    regime de degat d'une cible a l'autre), mutuellement non adjacentes, atteignables a pied.

    `solo` : E1 a distance 2, E2 et E3 a distance >= 5 -- au-dela de toute portee du roster, pour
    que l'ensemble de `GetValidTargets` depuis `C` soit un SINGLETON. C'est la seule geometrie ou
    `ValidTargets.Remove` de la cible du case le vide, donc la seule ou son absence se voit."""
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    for c in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        if len(P124._move_ring(c, walk, elev)) < 3:
            continue
        near = [q for q in cells if q != c and hexgeo.distance(c, q) == 2
                and P124._gated_path(c, q, walk, elev)]
        if mode == "solo":
            far = [q for q in cells if hexgeo.distance(c, q) >= 5
                   and P124._gated_path(c, q, walk, elev)]
            picked_far = []
            for q in far:
                if all(hexgeo.distance(q, r) >= 2 for r in picked_far):
                    picked_far.append(q)
                if len(picked_far) == 2:
                    break
            if near and len(picked_far) == 2:
                return c, [near[0]] + picked_far
            continue
        picked = []
        for q in near:
            if all(hexgeo.distance(q, r) >= 2 for r in picked):
                picked.append(q)
            if len(picked) == 3:
                return c, picked
    return None, None


def _legal_tiles(st, tgt) -> set:
    """Tuiles-caster d'ou l'attaque `st["ab"]` sur `tgt` est LEGALE (`decisionView.attackPlans`,
    `ranked`)."""
    plan = (st["ctx"].plans.get(st["cid"]) or {})
    for ev in (plan.get("evals") or ()):
        if ev.get("abilityId") == st["ab"] and ev.get("targetId") == tgt:
            return {(rk["col"], rk["row"]) for rk in (ev.get("ranked") or ())}
    return set()


def _attest_damage_bounds(ctx, cid, ab, tile, foes) -> dict:
    """`{cible: {"nat": [min, max], "port": [min, max], "d_avg": ...}}` sur la tuile de mesure.

    ATTRIBUTION, pas decor : le terme de ce playbook est une utilite de DEGAT, donc tout residu de
    PREDICTION deja present sur la paire (caster, cible) s'y propage MECANIQUEMENT -- mis a
    l'echelle par le rapport des `combinedMax`, puisque la meme prediction est notee contre une
    AUTRE cible (en-tete du port, point 5). Sans cette lecture, un residu de prediction d'un point
    de degat se lirait comme un bug du playbook. Bornes natives = `decisionView.attackPlans`,
    `ranked[].dmgMin/dmgMax` (= `AccurateHealthDamage`, le meme champ que le port publie)."""
    from engine.playbook.prediction import make_normal_attack_predictions
    from engine.services.min_max_damage import min_max_avg
    out = {}
    plan = (ctx.plans.get(cid) or {})
    for ev in (plan.get("evals") or ()):
        if ev.get("abilityId") != ab or ev.get("targetId") not in foes:
            continue
        rk = next((r for r in (ev.get("ranked") or ())
                   if (r.get("col"), r.get("row")) == tuple(tile)), None)
        if rk is None:
            continue
        pev = make_normal_attack_predictions(ctx.scene, cid, ev["targetId"], tile)
        pr = getattr(pev, "prediction", None) if pev is not None else None
        if pr is None:
            continue
        nat = [rk.get("dmgMin"), rk.get("dmgMax")]
        prt = [pr.accurate_health_damage.min, pr.accurate_health_damage.max]
        out[ev["targetId"]] = {
            "nat": nat, "port": prt,
            "d_avg": min_max_avg(nat[0] or 0, nat[1] or 0) - min_max_avg(prt[0], prt[1])}
    return out


def build_case(sid, rpc, rid: int, regime: str) -> dict:
    elev, walk, _tid = P124._board(sid, rid)
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    dv, pos = P124._positions(sid, rid)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mine = [u for u in units if u.get("ctrl")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    cid, myplayer = mine[0]["id"], mine[0]["owner"]
    foes = [u["id"] for u in units if not u.get("ctrl")]
    if len(foes) != 3:
        raise MontageError(f"montage NON INSTALLE : {len(foes)} ennemis au lieu de 3")

    # (a) LE PASSIF EST-IL DANS L'AbilitiesComponent ? Sans 1135 dedans, le dispatcher ne l'itere
    #     pas et la mesure ne prouverait rien (moitie CABLAGE du patron #419).
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live_ids = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
    if ABILITY not in live_ids:
        raise MontageError(f"montage NON INSTALLE : {ABILITY} n'est PAS dans l'AbilitiesComponent "
                           f"du caster -- triggered live lus = {sorted(set(live_ids))}")

    # (b) La geometrie, puis le DRIVE (jamais « bloque par le spawn »).
    C, EP = _find_layout(cells, elev, walk, LAYOUT[regime])
    if C is None:
        raise MontageError(f"montage NON INSTALLE : aucune geometrie `{LAYOUT[regime]}` sur ce "
                           f"board (tuile de caster a 3 voisins + positions d'ennemi voulues)")
    want = {cid: C}
    want.update(dict(zip(foes, EP)))
    if not P124._drive_to(sid, rid, walk, elev, want):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {want}, "
                           f"obtenu { {u: pos.get(u) for u in want} }")
    P124._give_turn_back(sid, rid, myplayer)
    dv, ctx = _fresh_ctx(rpc, rid, cid)
    if ctx.origin != C:
        raise MontageError(f"montage NON INSTALLE : le caster est en {ctx.origin}, voulu {C}")
    if ctx.scene.has_moved(cid) is not False:
        raise MontageError(f"montage NON INSTALLE : `UnitFlag.Moved` du caster vaut "
                           f"{ctx.scene.has_moved(cid)} -- la gate 3 couperait DEJA en HOME")

    ab = _normal_ability_id(rpc, rid, cid)
    here69 = _from_here(rpc, rid, cid, NORMAL_69)
    here_ab = _from_here(rpc, rid, cid, ab)
    if regime == "foreign":
        if ab == NORMAL_69:
            raise MontageError(f"montage NON INSTALLE : l'attaque normale du caster est {ab} = "
                               f"le litteral du playbook -- le regime ne distingue rien")
        if here69:
            raise MontageError(f"montage NON INSTALLE : `GetValidTargets(caster, pos, 0x45)` rend "
                               f"{here69} sur un caster sans l'ability 0x45")
        if len(here_ab) < 2:
            raise MontageError(f"montage NON INSTALLE : seulement {len(here_ab)} cible(s) legale(s) "
                               f"a l'attaque normale {ab} -- le mutant `case_ability` n'aurait "
                               f"rien a deplacer")
    else:
        if ab != NORMAL_69:
            raise MontageError(f"montage NON INSTALLE : l'attaque normale du caster est {ab}, "
                               f"attendu {NORMAL_69} pour le regime `{regime}`")
        if regime == "remove":
            if len(here69) != 1:
                raise MontageError(f"montage NON INSTALLE : {len(here69)} cible(s) legale(s) sans "
                                   f"bouger ({here69}), il en faut EXACTEMENT une pour que "
                                   f"`ValidTargets.Remove` vide l'ensemble")
        elif len(here69) < 2:
            raise MontageError(f"montage NON INSTALLE : seulement {len(here69)} cible(s) legale(s) "
                               f"sans bouger -- le `Fix64.Max` ne trancherait rien")

    # (c) La tuile de DEPLACEMENT : legale pour la cible de reference, DANS les tuiles d'action de
    #     l'oracle, et dont le socle natif/port S'ACCORDE DEJA sans le playbook. Cette derniere
    #     condition n'est pas un tri de complaisance : elle ne peut qu'ECHOUER bruyamment (si le
    #     natif portait un terme sur une tuile de deplacement, AUCUNE tuile ne la satisferait).
    ref_tgt = here69[0] if regime != "foreign" else here_ab[0]
    legal = _legal_tiles({"ctx": ctx, "cid": cid, "ab": ab}, ref_tgt)
    # (b bis) Le regime `kill` n'existe QUE si les deux verdicts natifs sont installes : une cible a
    # kill POSSIBLE mais NON garanti (c'est elle qui exerce `Fix64.Half`) et une a kill GARANTI
    # (c'est elle qu'exerce `ValidTargets.Remove`). On les LIT sur la prediction, jamais on ne les
    # suppose des PV poses au build.
    verdicts = {}
    if regime in ("kill", "remove"):
        from engine.playbook.prediction import make_normal_attack_predictions
        for t in foes:
            pev = make_normal_attack_predictions(ctx.scene, cid, t, C)
            pr = getattr(pev, "prediction", None) if pev is not None else None
            if pr is None:
                raise MontageError(f"montage NON INSTALLE : pas de prediction normale vs u{t}")
            verdicts[t] = (pr.might_be_kill(), pr.will_be_kill())
        if regime == "kill" and not any(m and not w for m, w in verdicts.values()):
            raise MontageError(f"montage NON INSTALLE : aucune cible a kill POSSIBLE-non-garanti "
                               f"-- `Fix64.Half` serait inerte. verdicts={verdicts} "
                               f"hp={ {t: ctx.scene.hp(t) for t in foes} }")
        if regime == "remove" and not any(w for _m, w in verdicts.values()):
            raise MontageError(f"montage NON INSTALLE : aucune cible a kill GARANTI -- "
                               f"`ValidTargets.Remove` serait inerte. verdicts={verdicts} "
                               f"hp={ {t: ctx.scene.hp(t) for t in foes} }")

    _dv3, pos = P124._positions(sid, rid)
    act = {t for t in (ctx.action_tiles or ()) if t and t[0] is not None}
    busy = set(pos.values())
    cands = sorted((legal & act) - busy - {C})
    if not cands and regime in ("home", "kill"):
        raise MontageError(f"montage NON INSTALLE : aucune tuile de deplacement legale et libre "
                           f"pour la cible de reference u{ref_tgt}")
    move_tile = cands[0] if cands else None
    vis = {u.get("id"): u.get("visualId") for u in (dv.get("units") or ())}
    return {"rid": rid, "cid": cid, "myplayer": myplayer, "foes": foes, "regime": regime,
            "dmg": _attest_damage_bounds(ctx, cid, ab, C, foes), "verdicts": verdicts,
            "ctx": ctx, "C": C, "EP": EP, "ab": ab, "here69": here69, "here_ab": here_ab,
            "move_tile": move_tile, "ref_tgt": ref_tgt, "walk": walk, "elev": elev,
            "vis": vis, "layout_by_vis": {vis[u]: p for u, p in want.items()},
            "hp": {u: ctx.scene.hp(u) for u in foes},
            "hpmax": {u: (ctx.hpmax_by_id or {}).get(u) for u in foes}}


def measure_native_baseline(sid, rpc, st: dict, lines: list, logs_dir: str,
                            state_file: str) -> dict:
    """BRAS APPARIE : re-monte la MEME bataille avec l'hote PRIVE du passif 1135, y rejoue le MEME
    placement (apparie par `visualId`, les ids d'entite differant d'un runner a l'autre) et rend le
    `pairUtility` NATIF de chaque ligne. `terme_natif = natif_graft - natif_base` devient une
    difference de deux mesures NATIVES -- le port n'entre pas dans sa definition.

    Le runner du bras est DISPOSE des la mesure faite (discipline `runner.md` : liberer au fil de
    l'eau)."""
    rid = _build(state_file, st["regime"], logs_dir, arm="base")
    try:
        elev, walk, _tid = P124._board(sid, rid)
        dv, _pos = P124._positions(sid, rid)
        units = [u for u in (dv.get("units") or ()) if u.get("alive")]
        by_vis = {u.get("visualId"): u.get("id") for u in units}
        want = {by_vis[v]: p for v, p in st["layout_by_vis"].items() if v in by_vis}
        if len(want) != len(st["layout_by_vis"]):
            raise MontageError(f"bras apparie NON INSTALLE : visualId manquants "
                               f"{set(st['layout_by_vis']) - set(by_vis)}")
        mine = [u for u in units if u.get("ctrl")]
        cid, myplayer = mine[0]["id"], mine[0]["owner"]
        stg = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
        live = [i for u in (stg.get("units") or ()) for t in (u.get("triggered") or ())
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
        if ABILITY in live:
            raise MontageError(f"bras apparie NON INSTALLE : {ABILITY} est ENCORE dans "
                               f"l'AbilitiesComponent -- les deux bras seraient identiques")
        if not P124._drive_to(sid, rid, walk, elev, want):
            _d, p2 = P124._positions(sid, rid)
            raise MontageError(f"bras apparie NON INSTALLE : placement incomplet -- voulu {want}, "
                               f"obtenu { {u: p2.get(u) for u in want} }")
        P124._give_turn_back(sid, rid, myplayer)
        tgt_of = {st["vis"][u]: by_vis[st["vis"][u]] for u in st["foes"]}
        inv = {u: tgt_of[st["vis"][u]] for u in st["foes"]}
        out = {}
        for r in lines:
            tile = st["C"] if r["tag"] == "HOME" else r["tile"]
            out[(r["tag"], r["tile"], r["target"])] = pair_native(
                rpc, rid, cid, inv[r["target"]], st["ab"], tile)
        return out
    finally:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", state_file],
                       cwd=_HERE, capture_output=True, text=True)


# --------------------------------------------------------------------------- mesure

def _row(rpc, st, tag, tile, tgt) -> dict:
    ctx, rid, cid, ab = st["ctx"], st["rid"], st["cid"], st["ab"]
    nat = pair_native(rpc, rid, cid, tgt, ab, tile)
    port = pair_port(ctx, ab, tgt, tile)
    muted = pair_port_muted(ctx, ab, tgt, tile)
    return {"tag": tag, "tile": tile, "target": tgt, "native": nat, "port": port,
            "port_muted": muted, "term_port": port - muted}


def measure(rpc, st: dict) -> list:
    """Lignes de reference. En `home`, la phase 2 DEPLACE le caster -- elle est donc jouee APRES
    toutes les lectures de la phase 1, et sur un `ctx` re-construit.

    Les lignes `MOVE` sont jouees pour LES TROIS cibles, pas seulement la cible de reference : le
    terme y est nul des DEUX cotes (gate 1), donc `natif - port_muted` y mesure le SOCLE de la paire
    (caster, cible) hors playbook. C'est ce qui permet d'ATTRIBUER un ecart de la ligne `HOME` --
    au playbook, ou a un residu du moteur qui suit la CIBLE et non la tuile."""
    tgts = st["here69"] if st["regime"] == "remove" else st["foes"]
    rows = [_row(rpc, st, "HOME", st["C"], t) for t in tgts]
    if st["regime"] in ("home", "kill"):
        for t in st["foes"]:
            if st["move_tile"] in _legal_tiles(st, t):
                rows.append(_row(rpc, st, "MOVE", st["move_tile"], t))
    return rows


def measure_moved(rpc, sid, st: dict) -> dict:
    """Phase 2 : le caster est REELLEMENT deplace sur `move_tile`, puis on re-mesure DEPUIS elle.
    La gate 1 y est satisfaite ; ce qui coupe est `UnitFlag.Moved`. Le `ctx` est reconstruit et
    REMPLACE dans `st` (les mutants de phase 2 doivent tourner dessus)."""
    rid, cid, tile = st["rid"], st["cid"], st["move_tile"]
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": cid, "to": {"col": tile[0], "row": tile[1]}}}, 60)
    _dv, ctx = _fresh_ctx(rpc, rid, cid)
    if ctx.origin != tile:
        raise MontageError(f"montage NON INSTALLE : le caster n'a pas rejoint {tile} "
                           f"(il est en {ctx.origin})")
    if ctx.scene.has_moved(cid) is not True:
        raise MontageError(f"montage NON INSTALLE : `UnitFlag.Moved` vaut "
                           f"{ctx.scene.has_moved(cid)} apres un deplacement REEL -- la gate 3 "
                           f"ne serait pas exercee")
    st["ctx"] = ctx
    return _row(rpc, st, "MOVED", tile, st["ref_tgt"])


# --------------------------------------------------------------------------- contre-epreuves

def _mutant_class(mutant: str, ctx_ab: int):
    from engine.playbook import rapid_fire as RF
    from engine.playbook.probable_damage_event import (ProbableDamageEvent,
                                                       calculate_utility_from_damage_event)

    class _Mut(RF.RapidFirePlaybook):
        def calculate_attack_utility_in_steps(self, ctx, attacker_uid, ability_id, case_tgt_id,
                                              attack_tile, prediction=None):
            sc = getattr(ctx, "scene", None)
            if sc is None or attack_tile is None:
                return 0.0
            cur = sc.pos(attacker_uid)
            if mutant != "no_home_gate":
                if cur is None or tuple(attack_tile) != tuple(cur):
                    return 0.0
            from engine.runner.abilities.attack_type import is_regular_attack
            if ability_id is None or not is_regular_attack(int(ability_id)):
                return 0.0
            if mutant != "no_moved_gate" and sc.has_moved(attacker_uid) is True:
                return 0.0
            which = ctx_ab if mutant == "case_ability" else RF._LOKI_NORMAL_ATTACK
            targets = _targets_for(ctx, attacker_uid, which)
            if not targets or prediction is None:
                return 0.0
            if mutant != "no_remove" and prediction.will_be_kill():
                targets = [t for t in targets if t != case_tgt_id]
                if not targets:
                    return 0.0
            from engine.playbook.prediction import make_normal_attack_predictions
            ev = make_normal_attack_predictions(sc, attacker_uid, case_tgt_id, attack_tile)
            pred = getattr(ev, "prediction", None) if ev is not None else None
            if pred is None:
                return 0.0
            might = prediction.might_be_kill()
            acc = 0.0
            for t in targets:
                p = 1.0 if mutant == "always_one" else (
                    0.5 if (t == case_tgt_id and might) else 1.0)
                kw = {} if mutant == "pred_target_hp" else {"target_hp": sc.hp(t),
                                                            "target_shield": sc.shield(t)}
                u = calculate_utility_from_damage_event(
                    ProbableDamageEvent(target=t, prediction=pred, probability1=p, **kw),
                    ctx.wt, (ctx.hpmax_by_id or {}).get(t))
                acc = (acc + u) if mutant == "sum_not_max" else max(acc, u)
            return acc

    return _Mut


def _targets_for(ctx, uid, ability_id):
    """Meme lecture que `rapid_fire.valid_normal_attack_targets`, mais pour un id ARBITRAIRE (le
    mutant `case_ability` interroge l'attaque normale CONCRETE)."""
    r = ctx.ability_targets(uid, int(ability_id)) or {}
    for u in (r.get("units") or ()):
        if u.get("unitId") != uid:
            continue
        for a in (u.get("abilities") or ()):
            if int(a.get("abilityId") or -1) != int(ability_id):
                continue
            fh = a.get("fromHere")
            if fh is None:
                continue
            return [t.get("targetId") for t in fh
                    if t.get("kind") == "unit" and t.get("targetId") is not None]
    return None


def measure_mutant(rpc, st: dict, mutant: str, lines: list) -> list:
    """Re-mesure le port avec 1135 REMPLACE par un mutant, sur les `lines` deja jouees.
    Critere : DEPLACEMENT par rapport au port NON MUTE (cf. en-tete)."""
    import engine.playbook.psyker as PSY
    ctx, ab = st["ctx"], st["ab"]
    ref = {(r["tag"], r["tile"], r["target"]): r["port"] for r in lines}
    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY]
    PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = _mutant_class(mutant, ab)()
    try:
        out = []
        for r in lines:
            k = (r["tag"], r["tile"], r["target"])
            out.append({"mutant": mutant, "tag": r["tag"], "tile": r["tile"],
                        "target": r["target"], "port": pair_port(ctx, ab, r["target"], r["tile"]),
                        "port_ref": ref[k]})
        return out
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file (le probe construit SON runner dessus)")
    ap.add_argument("--regime", choices=tuple(HOSTS), default="home")
    ap.add_argument("--mutants", action="store_true",
                    help="joue aussi les contre-epreuves (elles doivent MORDRE)")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    logs = os.path.abspath(os.path.join(_HERE, "..", "..", "logs"))
    os.makedirs(logs, exist_ok=True)
    rid = _build(args.state_file, args.regime, logs)
    st = build_case(sid, rpc, rid, args.regime)
    print(f"runner {rid} | regime {args.regime} | caster u{st['cid']} @ {st['C']} "
          f"| attaque normale = {st['ab']}")
    print(f"  ennemis {st['EP']} hp={st['hp']} hpmax={st['hpmax']}")
    print(f"  fromHere(0x45)={st['here69']} fromHere({st['ab']})={st['here_ab']} "
          f"| tuile MOVE={st['move_tile']}")
    for t, d in sorted(st["dmg"].items()):
        print(f"  degat HOME vs u{t}: natif={d['nat']} port={d['port']} d_avg={d['d_avg']:+d}")
    if st["verdicts"]:
        print("  verdicts (mightBeKill, willBeKill) = "
              + " ".join(f"u{t}:{v}" for t, v in sorted(st["verdicts"].items())))
    rows = measure(rpc, st)
    if args.mutants:
        muts = {m: measure_mutant(rpc, st, m, rows) for m in MUTANTS}
    if args.regime in ("home", "kill"):
        moved = measure_moved(rpc, sid, st)
        rows.append(moved)
        if args.mutants:
            for m in MUTANTS:
                muts[m].extend(measure_mutant(rpc, st, m, [moved]))
    base = measure_native_baseline(sid, rpc, st, rows, logs,
                                   args.state_file.replace(".json", "_base.json"))
    for r in rows:
        nb = base[(r["tag"], r["tile"], r["target"])]
        r["native_base"] = nb
        r["term_native"] = r["native"] - nb
        r["socle"] = nb - r["port_muted"]
        print(f"  [{r['tag']:<5}] {r['tile']} tgt=u{r['target']:<3} nat={r['native']:.6f} "
              f"port={r['port']:.6f} | base={nb:.6f} socle={r['socle']:+.9f} "
              f"terme_natif={r['term_native']:+.6f} terme_port={r['term_port']:+.6f} "
              f"ecart_terme={r['term_port'] - r['term_native']:+.9f}")
    if args.mutants:
        for m in MUTANTS:
            worst = max(abs(x["port"] - x["port_ref"]) for x in muts[m])
            detail = " ".join(f"{x['tag']}/u{x['target']}:{x['port'] - x['port_ref']:+.4f}"
                              for x in muts[m])
            need = m in MUST_BITE[args.regime]
            verdict = "MORD" if worst > EPS else "NE MORD PAS"
            print(f"  [mutant {m:<14}] deplacement max = {worst:+.9f} [{detail}] ({verdict}"
                  f"{'' if need else ' -- non exige dans ce regime'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
