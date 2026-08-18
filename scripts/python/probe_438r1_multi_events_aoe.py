"""probe #438-r1 -- le regime MULTI-EVENTS (AoE) de la feuille ATTACK, MESURE.

CE QUE #438 A LAISSE OUVERT. La feuille `TriggeredAbilities(2)` de la face ATTACK est evaluee
**PAR EVENT** du composite `Damage(35)`, et chaque event porte SA propre `DamagePrediction` (le
`case` natif est un `UtilityAttackCase.ForDamagePrediction`). La boucle du port
(`engine/playbook/base.py::calculate_utility_from_predictions`) passe bien `ev.prediction` de
l'event COURANT -- correct par construction, mais **jamais mesure** : `tyranParasite`, seul porteur
HERO de `1204 BarbedOvipositor`, n'a pas d'attaque AoE, et les six autres porteurs sont npc. Tant
qu'un seul event existe, << la prediction de l'event courant >> et << la prediction du premier
event >> sont la MEME CHOSE : le regime est DEGENERE et n'atteste rien.

LE MONTAGE, et pourquoi il est legitime. `BarbedOvipositorPlaybook$$CalculateAttackUtilityInStepsInternal`
ne lit du case que `DamagePrediction` (`MightBeKill`, `WillBeKill`) et le TRAIT de la cible
(`HasTrait(case.Target, UnitTrait.Mechanical)`) -- ni stat, ni trait, ni arme du CASTER. Le natif
charge d'ailleurs le playbook PAR ABILITY (`PlaybookDatabase$$LoadPlaybook(abilityType)`), jamais
par unite. La GREFFE (`case-92` §5bis) est donc une MESURE, pas un contournement : on pose
`PassiveAbilities = [1204]` sur `astraOrdnance`, dont l'arme est un **Blast** (portee 3, 3 coups)
-- son attaque normale produit donc une cible PRINCIPALE **et** des cibles de SPLASH, c'est-a-dire
plusieurs events, chacun avec sa prediction.

CE QUE LA MESURE TRANCHE. On calibre les PV pour que DEUX events du meme cast tombent dans des
regimes DIFFERENTS (kill GARANTI -> `BARBEDOVIPOSITOR_DefinitelyKill` = 50 ; kill POSSIBLE ->
`_PossibleKill` = 25). Le natif (`pairUtility`) et le port doivent alors s'accorder. Un port qui
reutiliserait la prediction du PREMIER event pour tous rendrait `50 + 50` ou `25 + 25` la ou le
natif rend `50 + 25` : l'ecart est de 25 points d'utilite, et c'est ce que la contre-epreuve
`--mutant premiere-prediction` rejoue.

⚠ CE QUE LA GREFFE NE COUVRE PAS, et qu'il faut ecrire : les stats, traits et armes du VRAI
porteur. Elle est legitime ICI parce que le terme mesure ne les lit pas ; elle ne le serait pas
pour une prediction de degat.

Usage (ASCII only, depuis scripts/python) :
  python probe_438r1_multi_events_aoe.py
  python probe_438r1_multi_events_aoe.py --mutant premiere-prediction
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

from rl_collect_batch import _resolve_session, _rpc                       # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402

BOARD = "MC1_67"
SEED = "777"
#: Le GREFFON. ⚠ **DEUX PISTES MESUREES ET ECARTEES avant celle-ci** -- les nommer evite de les
#: rejouer :
#:   * une ARME `Blast` (`astraOrdnance`, `{"hits": 3, "DamageProfile": "Blast", "Range": 3}`) :
#:     AUCUN cast ne produit plus d'UN event. Le profil d'arme ne multiplie pas les events du
#:     composite `Damage(35)`, il multiplie les COUPS d'un seul event ;
#:   * le SPLASH PSYKER (`astraPrimarisPsy`) : idem, **1** event. Le splash Psyker n'est pas un
#:     event de plus -- c'est un TERME evalue DANS la feuille `TriggeredAbilities(2)` du composite
#:     (cf. `playbook/psyker.py` et le commentaire de `base.py`).
#: La source multi-events est une **ABILITY ACTIVE A ZONE** : `make_damage_predictions` rend alors
#: un event PAR CIBLE de la zone, chacun avec SA `DamagePrediction`. `astraBullgryn` porte
#: `FragBomb (1017)` et est HERO du pool.
CASTER = "astraBullgryn"
#: L'ability AoE dont le cast produit les events. `None` = on la CHERCHE dans les plans.
ABILITY_AOE = 1017                                                # ActiveAbilityType.FragBomb
#: Trois cibles NON `Mechanical` (le trait coupe le terme a 0 : c'est le regime R4 de #438, deja
#: mesure la-bas ; ici on veut deux regimes de KILL differents, pas la coupure de trait).
FOES = ("astraCreed", "astraDreir", "templChampion")
#: ⚠ **DEUX REGIMES DE KILL DANS LE MEME CAST, et c'est ce qui rend la mesure DISCRIMINANTE.**
#: Sans calibrage, les trois events de la zone tombent tous dans `WillBeKill` (mesure : `will=True`
#: x3, poids 50 x3) -- et dans CE regime, << la prediction de l'event courant >> et << celle du
#: premier >> donnent le MEME total. Le montage serait alors parfaitement lisible et entierement
#: vide. On releve donc les PV de DEUX des trois cibles tres au-dessus du degat de zone : elles
#: passent en `will=False, might=False` (terme 0), la troisieme reste a 1 PV (terme 50).
#: `Health` SEUL ne mord pas -- `RemainingHealth` est le PV COURANT, et c'est lui que lit
#: `CurrentHealth@0x00` (mesure de #438 §3).
CALIBRAGE = ("astraCreed:Health=1,RemainingHealth=1;"
             "astraDreir:Health=400000,RemainingHealth=400000;"
             "templChampion:Health=400000,RemainingHealth=400000")
ABILITY = int(TriggeredAbilityType.BarbedOvipositor)              # 1204
KEY_DEFINITELY = "BARBEDOVIPOSITOR_DefinitelyKill"                # 50
KEY_POSSIBLE = "BARBEDOVIPOSITOR_PossibleKill"                    # 25
EPS = 1e-3                                                        # Fix64 natif contre float du port


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


def _r(sid, m, b, t=180):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _seed_bc_greffe() -> Path:
    """`PassiveAbilities = [1204]` sur le greffon, dans une COPIE du seed BC.

    ⚠ C'est bien `PassiveAbilities` et non `ActiveAbilities` (le recours 3 de `case-92` §5bis est
    ecrit pour une ACTIVE) : `1204` est un `TriggeredAbilityType`, et le champ que
    `UnitFactory$$AddConfiguredAbilities` lit pour les declenchees est celui-la.

    ⚠ ET ON **AJOUTE**, on ne REMPLACE PAS. Le recours 3 de `case-92` ecrase `ActiveAbilities`
    parce que l'ability greffee y est la seule qui compte ; ici le greffon doit GARDER son kit,
    puisque c'est SON passif `Psyker` qui fabrique le regime multi-events qu'on veut mesurer.
    Remplacer le detruirait, et le montage rendrait un seul event -- donc un regime DEGENERE.
    Le seed BC PARTAGE n'est jamais touche : la copie vit sous `logs/`."""
    import rl_collect_batch as R
    bc = R._load_seed_bc(None)
    vu = False
    for u in bc.get("Units") or []:
        if u.get("Id") == CASTER:
            deja = list(u.get("PassiveAbilities") or [])
            u["PassiveAbilities"] = deja + ([ABILITY] if ABILITY not in deja else [])
            u["PassiveAbilityLevel"] = max(1, int(u.get("PassiveAbilityLevel") or 1))
            vu = True
    if not vu:
        raise MontageError("greffon %s absent du catalogue du seed BC" % CASTER)
    out = ROOT / "logs" / "runners" / ("probe438r1-bc-%s.json" % uuid.uuid4().hex[:8])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")
    return out


def _build(seed_bc, extra=None):
    state = ROOT / "logs" / "runners" / ("probe438r1-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
            "--state-file", str(state), "--seed-bc", str(seed_bc),
            "--p-units", CASTER, "--a-units", ",".join(FOES)] + list(extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise MontageError("build KO : %s" % (p.stderr or p.stdout or "")[-1200:])
    return json.loads(state.read_text())["runnerId"], state


def _ctx(sid, rid, uid, wt):
    from engine.ai import context as AC
    from engine.playbook import scene as SC
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32})
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    pred = SC.build_predictor(lambda m, b, t=120: _r(sid, m, b, t), rid)
    return AC.build(lambda m, b, t=120: _r(sid, m, b, t), rid, dv, mbu, uid, wt, pred), dv


def _regime(ev) -> tuple:
    """`(WillBeKill, MightBeKill)` de l'event -- les DEUX scalaires que lit
    `BarbedOvipositorPlaybook$$CalculateAttackUtilityInStepsInternal`.

    ⚠ CE SONT DES **METHODES**, pas des proprietes. Un `getattr(pred, "will_be_kill", False)` rend
    la methode LIEE, donc un objet TOUJOURS VRAI : le cran anti-degenere lisait `(True, True)` pour
    les trois events d'un montage ou DEUX etaient a 400 000 PV contre 3 de degat. Un cran qui ne
    peut pas rendre Faux ne garde rien -- il faut APPELER."""
    p = getattr(ev, "prediction", None)
    if p is None:
        return (False, False)
    return (bool(p.will_be_kill()), bool(p.might_be_kill()))


def _playbook(ctx, ab):
    from engine.playbook import get_playbook_or_default
    from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK
    return NORMAL_ATTACK_PLAYBOOK if ab in (ctx.normal_ids or ()) else get_playbook_or_default(ab)


def _events(ctx, ab, tgt, tile):
    """Les events du composite `Damage(35)` pour ce cast -- c'est LA liste que la boucle de
    `playbook/base.py::calculate_utility_from_predictions` itere, un `ev.prediction` par element."""
    return _playbook(ctx, ab).make_damage_predictions(ctx, tile, tgt, ab) or []


def mesurer(verbose=True) -> dict:
    from engine import weights as W
    from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK

    sid = _resolve_session()
    if not sid:
        return {"error": "aucune session Frida"}
    wt = W.load()
    w_def = float(wt.sub("TriggeredAbilities", KEY_DEFINITELY))
    w_pos = float(wt.sub("TriggeredAbilities", KEY_POSSIBLE))
    if not w_def or not w_pos or w_def == w_pos:
        return {"error": "poids inexploitables (%s / %s) -- les deux regimes ne se separeraient pas"
                         % (w_def, w_pos)}

    bc = _seed_bc_greffe()
    rid, _state = _build(bc, ["--unit-stat", CALIBRAGE])
    try:
        dv0 = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 120)
        ids = {u.get("visualId"): u.get("id") for u in (dv0.get("units") or [])}
        cid = ids.get(CASTER)
        if cid is None:
            return {"error": "greffon absent de la bataille (%r)" % sorted(ids)}
        ctx, _dv = _ctx(sid, rid, cid, wt)

        # GARDE DE SOURCE : le kit DECLENCHE lu LIVE porte-t-il 1204 ? Sans elle, le playbook
        # serait enregistre et jamais appele -- exactement le patron << porte + non cable >>.
        st = _r(sid, "unitAbilityStates", {"runnerId": rid}, 180)
        row = next((u for u in (st.get("units") or []) if u.get("entityId") == cid), None)
        kit = [(t.get("raw") or [None])[0] for t in ((row or {}).get("triggered") or [])]
        if ABILITY not in kit:
            return {"error": "la greffe n'a pas pris : kit declenche LIVE = %r" % kit}

        # Un triplet (ability, cible, tuile) dont le cast produit AU MOINS DEUX events -- c'est la
        # seule chose qui rend le regime non degenere, et on le CHERCHE au lieu de le supposer.
        # ⚠ On balaie TOUTES les abilities des plans, pas la seule `ABILITY_AOE` : si le montage
        # devait changer de porteur, la recherche resterait valable, et un echec DIT ce qu'il a
        # visite au lieu de rendre un refus opaque.
        candidates = sorted({ABILITY_AOE} | {e.get("abilityId")
                                             for e in ((ctx.plans.get(cid) or {}).get("evals") or [])
                                             if e.get("abilityId") is not None})
        trouve, vus = None, {}
        for ab in candidates:
            for tgt_vis in FOES:
                tgt = ids.get(tgt_vis)
                if tgt is None:
                    continue
                for tile in (ctx.action_tiles or []):
                    evs = _events(ctx, ab, tgt, tile)
                    vus[ab] = max(vus.get(ab, 0), len(evs))
                    if len(evs) >= 2:
                        trouve = (ab, tgt_vis, tgt, tile, evs)
                        break
                if trouve:
                    break
            if trouve:
                break
        if trouve is None:
            return {"error": "aucun cast a >= 2 events sur %s/%s -- le regime MULTI-EVENTS n'est "
                             "pas installe, la mesure n'a pas eu lieu. Max d'events VU par "
                             "ability : %r" % (BOARD, SEED, vus)}
        ab, tgt_vis, tgt, tile, evs = trouve
        # ⚠ CRAN ANTI-DEGENERE : deux events dans le MEME regime ne peuvent RIEN separer -- << la
        # prediction de l'event courant >> et << celle du premier >> y donnent le meme total, et un
        # accord y serait parfaitement lisible et entierement vide.
        vus_reg = {_regime(e) for e in evs}
        if len(vus_reg) < 2:
            return {"error": "les %d events sont tous dans le MEME regime %r -- montage DEGENERE, "
                             "le calibrage des PV n'a pas mordu" % (len(evs), vus_reg)}

        u_port = float((_playbook(ctx, ab).calculate_action_utility(ctx, tile, tgt, ab)
                        or {"u": float("nan")})["u"])
        nat = _r(sid, "pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                                      "abilityType": ab, "col": tile[0], "row": tile[1]}, 90)
        u_nat = nat.get("utility")
        regimes = [{"target": e.target, "will": _regime(e)[0], "might": _regime(e)[1]}
                   for e in evs]
        out = {"caster": cid, "ability": ab, "cible": tgt_vis, "tuile": tile, "n_events": len(evs),
               "regimes": regimes, "port": u_port, "natif": u_nat,
               "accord": (isinstance(u_nat, (int, float)) and abs(u_port - float(u_nat)) <= EPS),
               "kit": kit, "poids": (w_def, w_pos)}
        if verbose:
            _dire(out)
        return out
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:                                    # pragma: no cover - nettoyage
            pass
        try:
            bc.unlink(missing_ok=True)
        except Exception:                                    # pragma: no cover
            pass


def _dire(o):
    if o.get("error"):
        print("[438-r1] ERREUR : %s" % o["error"])
        return
    print("[438-r1] greffon u%s, ability %s, cible %s, tuile %s -- %d events dans le composite Damage(35)"
          % (o["caster"], o.get("ability"), o["cible"], o["tuile"], o["n_events"]))
    print("         regimes par event : %r" % (o["regimes"],))
    print("         pairUtility natif = %s ; port = %.6f ; accord = %s"
          % (o["natif"], o["port"], o["accord"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mutant", choices=("premiere-prediction",), default=None,
                    help="contre-epreuve : le port passe la prediction du PREMIER event a TOUS")
    a = ap.parse_args(argv)

    restaure = None
    if a.mutant == "premiere-prediction":
        # CONTRE-EPREUVE : on remplace `prediction=ev.prediction` par la prediction du PREMIER
        # event. C'est exactement la faute que le regime MULTI-EVENTS peut montrer et que le
        # regime a un seul event ne peut PAS montrer.
        import engine.playbook.base as B
        vrai = B.triggered_abilities_attack_utility

        def _fige(ctx, uid, ability_id, target, caster_tile, prediction=None, _p=[None]):
            if _p[0] is None:
                _p[0] = prediction
            return vrai(ctx, uid, ability_id, target, caster_tile, prediction=_p[0])
        B.triggered_abilities_attack_utility = _fige
        restaure = (B, vrai)

    try:
        res = mesurer()
    finally:
        if restaure:
            restaure[0].triggered_abilities_attack_utility = restaure[1]
    if res.get("error"):
        _dire(res)              # un refus se DIT ; un rc 1 muet ne s'instruit pas
        return 1
    if a.mutant:
        # Sous mutation, l'accord DOIT tomber -- sinon la garde ne mord pas et ne garde rien.
        print("[438-r1] MUTANT : accord=%s (on ATTEND False)" % res["accord"])
        return 0 if not res["accord"] else 1
    return 0 if res["accord"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
