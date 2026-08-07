#!/usr/bin/env python
"""#419-r6-r1 -- la face DECISION du canal CRIT : `MightCrit` dans le SELECTEUR de cible.

CE QUE CE PROBE ETABLIT
-----------------------
#R34 a porte `MightCrit@+0xB1` sur la chaine PLAYBOOK (`probable_damage_event.composite_fields`
et `engine_agreement_stages._fields_from_native_event`), et a NOMME en residu le seul producteur
restant : `runner/operations/damage_utility._target_utility`, qui fabrique un `pred` synthetique
SANS la cle. Le residu disait << non porte faute de pouvoir le VALIDER >>, et c'etait exact : tant
que le canal crit etait muet (`CouldCrit` faux sur 106/106 unites normalisees, #419-r5), la cle
absente et la cle a `False` sont le MEME dict. La bascule du defaut a << equiper >> (#419-r6)
ouvre `CouldCrit` sur 98/106 -- l'ecart devient REEL, et le montage devient CONSTRUCTIBLE.

Le natif, lui, ne fabrique aucun dict : `IdunBattle.Entities.Selectors.
SortUnitsByDamageUtilitySelector$$Select` appelle le service de prediction (`this+0x50`) avec
l'OWNER (`this+0x18`) et recopie la `DamagePredictionResult` COMPLETE dans son etat de boucle
(les 0x9c octets `+0x10..+0xac` du decompile), FLAGS COMPRIS -- donc avec le `MightCrit` que
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` y ecrit depuis
`IdunBattle.Core.Services.DamageCalculations$$CouldCrit(owner)`
(`GetStat(owner, 9) >= 1 && GetStat(owner, 10) >= 1`, relu au decompile sur le build courant).

TROIS ETAGES, ET LE 3e EST CE QUI ETABLIT LA CAUSALITE
-------------------------------------------------------
  1. `--regime`  (OFFLINE pur) : BALAYAGE du regime discriminant. On cherche des PV pour lesquels
     l'argmax du composite Damage(34) CHANGE entre `might_crit=False` (le CONTREFACTUEL) et
     `might_crit=True` (la PRODUCTION, depuis #494-r1-r1). Si l'ensemble est VIDE, le probe le DIT et rend rc=1 : un montage qui ne
     discrimine pas ne prouve rien (cf. << accord en regime DEGENERE >>).
  2. `--live`    : le montage Doombolt (`thousAhriman`, actif 1102) monte AVEC ces PV. L'ordre du
     selecteur gouverne la repartition des coups, donc l'ordre des tirages RNG, donc les degats
     PAR CIBLE -- le live tranche entre les deux ordres, sans qu'aucun hook nouveau soit requis.
  3. `--temoin`  : le MEME montage en `--no-bis-items`. Le canal y est ferme, donc les deux ordres
     doivent redevenir IDENTIQUES. Sans ce bras, on ne saurait pas si l'ecart vient de la bascule
     ou d'autre chose.

Aucune assertion : c'est un probe, il MESURE. Le cliquet vit dans
`tests/engine/test_419r6r1_face_decision_live.py`. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

_HERE = Path(__file__).resolve().parent
#: RACINE du depot. Les sorties de run vont dans `<racine>/logs/`, JAMAIS dans
#: `scripts/python/logs/` -- `_HERE / "logs"` fabriquait ce second arbre, que `probe_273`
#: rougit a bon droit (il ne peut pas distinguer une SORTIE d'une entree gitignoree lue
#: depuis une racine inattendue). Les 40+ autres probes ecrivent tous `ROOT / "logs" / "runners"`.
_ROOT = _HERE.parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from engine.runner.components import HealthComponent, StatsComponent   # noqa: E402
from engine.runner.operations.damage_utility import (          # noqa: E402
    _target_utility, damage_utility_weights)
from engine.services.damage_prediction import attacker_could_crit      # noqa: E402
from engine.entities.effects.magnitude import ability_var      # noqa: E402


#: #494-r1 -- GEOMETRIE PLATE de `MC1_67`, MESUREE par `tileMeta` le 2026-08-07 : le caster et les
#: quatre cibles y sont TOUS a l'elevation 3, donc `…$$CalculateElevationBonusModifier` (« +% si
#: l'attaquant est plus HAUT que la cible ») ne joue nulle part et la cle de tri redevient purement
#: fonction des PV -- ce que ce montage doit mesurer. `cibles[0]` est a distance 1 du caster (les
#: trois autres a 2), donc c'est elle que le natif prend comme cible du MESSAGE.
GEO_PLATE = {"board": "MC1_67", "caster": (3, 3),
             "cibles": [(3, 4), (1, 4), (2, 4), (5, 4)]}


def owner_might_crit(state, owner_id) -> bool:
    """`CouldCrit(owner)` -- le flag que le natif POSERAIT sur la prediction du selecteur.

    Il vit ICI et non dans `engine/` parce qu'il DIT si le canal est ouvert (etage temoin) et sert
    au
    CONTREFACTUEL (jouer le port comme s'il NE lisait PAS le flag) et a DIRE si le canal est ouvert.

    FOYER UNIQUE reutilise, pas de second mirror : `services.damage_prediction.attacker_could_crit`
    (#R34). `UnitContext.crit_chance`/`.crit_damage` sont des proprietes adossees a
    `get_stat(Current)` = `IdunBattle.Entities.UnitExtensions$$GetStat` NU -- exactement le niveau
    de lecture de `IdunBattle.Core.Services.DamageCalculations$$CouldCrit`."""
    e = state.get_entity(owner_id) if owner_id is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    return bool(attacker_could_crit(sc.ctx if sc is not None else None))

DOOMBOLT = 1102
CASTER = "thousAhriman"


# --------------------------------------------------------------------------------------------
# etage 1 -- le REGIME discriminant, cherche sur le VRAI code d'utilite
# --------------------------------------------------------------------------------------------

class _StubHealth:
    """Porteur minimal de `HealthComponent` pour le BALAYAGE. Il n'est utilise QUE par l'etage 1
    (recherche de regime) : les etages live passent le VRAI `State` du runner. Le point est que le
    balayage exerce `_target_utility` LUI-MEME -- pas une copie de sa formule."""

    def __init__(self, hp: int, hp_max: int):
        self._hc = HealthComponent(hp=hp, hp_max=hp_max)

    def get_component(self, cls):
        return self._hc if cls is HealthComponent else None


class _StubState:
    def __init__(self, par_id: dict):
        self._e = {int(k): _StubHealth(v[0], v[1]) for k, v in par_id.items()}

    def get_entity(self, eid):
        return self._e.get(int(eid))


def _substrat(par_id: dict, reco: "dict | None"):
    """L'ETAT sur lequel l'etage 1 balaie, et QUI il est.

    ⚠ **#494-r1-r1 -- CE SUBSTRAT DOIT ETRE CELUI DE LA CLE DE PRODUCTION.** Tant que la cle de tri
    etait PRE-ARMURE, un stub a PV seuls la calculait exactement ; depuis qu'elle passe par la
    PREDICTION COMPLETE par cible (`IBattleQuery` slot `0x26`), un stub sans `StatsComponent` fait
    emprunter a `_target_utility` son chemin DEGRADE -- et l'etage 1 reglait alors le regime sur une
    cle qui n'est plus celle qui tourne en live. Mesure du 2026-08-07 : le montage rendait
    `montage_discriminant = False` (les deux valeurs du flag donnaient le meme ordre), c.-a-d. un
    ROUGE de MONTAGE, pas un verdict sur le port.

    `reco` = la RECONNAISSANCE (`_reco_du_runner`) : `{"state", "caster", "cibles"}` d'un runner
    monte avec la MEME geometrie et la MEME neutralisation d'armure que le build final. On y MUTE
    les PV des trois roles, donc le balayage exerce la cle REELLE (armure, defense, modificateurs,
    part positionnelle). `None` -> repli sur le stub a PV seuls (chemin DEGRADE), qui reste utile
    hors runner mais ne regle plus rien de discriminant."""
    if reco is None:
        return _StubState(par_id), None, {int(k): int(k) for k in par_id}
    st, cibles = reco["state"], reco["cibles"]
    mapping = {}
    for role in sorted(int(k) for k in par_id):
        # Le role N est TOUJOURS la N-ieme cible apres celle du MESSAGE -- c'est l'appariement que
        # `etage_live` pose par `--unit-stat` sur `noms[1:]`. Un `zip` sur les seuls roles PRESENTS
        # le casserait des qu'on evalue un role isolement (balayage separable).
        eid = int(cibles[role - 1])
        hp, mx = par_id[role]
        hc = st.get_entity(eid).get_component(HealthComponent)
        hc.hp, hc.hp_max = int(hp), int(mx)
        mapping[role] = eid
    return st, reco["caster"], mapping


def _ordre(par_id: dict, d: int, might_crit: bool, reco: "dict | None" = None) -> list:
    """L'argmax-ordre que `sort_units_by_damage_utility` rendrait pour ces PV, a `might_crit` IMPOSE.

    On appelle `_target_utility` (le vrai) et on re-fait le tri ici plutot que d'appeler
    `sort_units_by_damage_utility`, uniquement parce que cette derniere DERIVE `might_crit` de
    l'owner : l'etage 1 doit pouvoir imposer les DEUX valeurs sur le meme etat."""
    u = _utilites(par_id, d, might_crit, reco)
    return sorted(sorted(int(k) for k in par_id), key=lambda r: -u[r])


def _utilites(par_id: dict, d: int, might_crit: bool, reco: "dict | None" = None) -> dict:
    st, owner, mapping = _substrat(par_id, reco)
    wt = damage_utility_weights()
    # Les kwargs sont ceux du call-site Doombolt (`abilities/thousandsons.doombolt_ordered_targets`)
    # -- l'etage 1 doit exercer LA MEME cle, pas une variante.
    kw = ({} if owner is None
          else {"owner_id": owner, "ability_type": DOOMBOLT, "is_melee": False})
    return {int(k): _target_utility(st, mapping[int(k)], d, d, wt, might_crit, **kw)
            for k in par_id}


def _bornes_brutes(d: int, reco: "dict | None", role: int = 1) -> tuple:
    """Les bornes du degat sante BRUT que la cle predit REELLEMENT pour un role, DERIVEES d'une
    prediction et non d'une formule supposee.

    Elles bornent la fenetre << letal MAIS sous le seuil >>, et elles ont change avec la cle : le
    chemin DEGRADE rendait `raw == (d, d)` (bornes brutes de l'appelant), le chemin MIRROR rend le
    `{0.8 x d, 1.2 x d}` de `GetBaseDamageFix64` compose des modificateurs de l'attaquant et du
    defenseur. Les LIRE evite de recopier ici des facteurs qui appartiennent a `predict_attack_raw`.
    """
    if reco is None:
        return int(d), int(d)
    from engine.runner.operations import damage_utility as _DU
    f = _DU._prediction_fields(reco["state"], reco["caster"], reco["cibles"][role - 1], int(d), 1,
                               DOOMBOLT, False) or {}
    return int(f.get("rawHealthDmgMin") or d), int(f.get("rawHealthDmgMax") or d)


def etage_regime(d: int, verbose: bool = True, reco: "dict | None" = None) -> dict:
    """Cherche des (hp, hp_max) pour lesquels l'ordre BASCULE entre les deux valeurs du flag.

    Le seul terme que `MightCrit` gouverne est `OverkillUnit` (38) par `MightBeOverkill`, et il ne
    mord QUE dans la fenetre << letal MAIS sous le seuil >> :
    `is_overkill` rend `isCritical` quand `hp <= rawMax` ET
    `(rawMax - hp) / hp * 100 < overkillDmgPctOfHealth`.
    Il faut donc une cible A dans cette fenetre, et une cible B qui la DEVANCE sans le flag et la
    SUIT avec -- ce qui demande de regler le terme `DamageDealt` (35), gouverne par `MaxHealth`.

    `reco` (#494-r1-r1) = la reconnaissance sur runner, qui donne a ce balayage le SUBSTRAT de la
    cle de production (cf. `_substrat`). Sans elle, le balayage exerce le chemin DEGRADE."""
    _rmin, rmax = _bornes_brutes(d, reco, 1)
    lo, hi = rmax // 2 + 1, rmax    # la fenetre, DERIVEE de la borne haute MESUREE
    if lo > hi:
        return {"ok": False, "raison": "fenetre vide : rawMax=%d" % rmax}
    hp_a = hi                       # A : haut de fenetre = le plus favorable au terme DamageDealt
    trouve = None
    marge_max = -1.0
    # TROIS roles, pas deux -- et c'est une correction MESUREE, pas un raffinement.
    #
    # Avec deux roles seulement, le montage db-4 place DEUX cibles au role A : elles ont la MEME
    # utilite, et l'ordre entre elles est alors decide par le TIE-BREAK, que le port approxime par
    # `id` croissant la ou le natif garde la stabilite de l'`OrderBy` sur l'ordre SOURCE. Mesure du
    # 2026-08-06 : le live rendait `[77, 81, 83, 79]` -- un ordre qu'AUCUNE des deux valeurs du
    # flag ne produit cote port. Un montage qui cree une egalite ne mesure pas le flag, il mesure
    # le tie-break.
    #
    # Le critere retenu est ce que le montage rend OBSERVABLE : `N = 3` coups sur 4 cibles donne
    # `[1, 1, 1, 0]`, donc c'est le DERNIER qui se lit sans ambiguite. On exige donc que le
    # dernier CHANGE entre les deux valeurs du flag :
    #     sans flag : B > C > A   -> A dernier  (le CONTREFACTUEL depuis #494-r1-r1)
    #     avec flag : B > A > C   -> C dernier  (la PRODUCTION depuis #494-r1-r1)
    # ce qui demande `u(A) < u(C) < u(A) + PossibleOverkill` et `u(B)` au-dessus des deux.
    #
    # ⚠ On ne prend PAS le premier triplet qui bascule : on garde celui dont la MARGE MINIMALE est
    # la plus grande. Une bascule a 0,5 point tiendrait a un arrondi, et un montage qui ne tient
    # qu'a un arrondi ne DISCRIMINE pas -- il attribuerait au flag un ecart venu d'ailleurs.
    # ⚠ **LES PV DE C SE DERIVENT D'UNE CONDITION, ILS NE SE BALAIENT PAS AU HASARD (#494-r1-r1).**
    # C doit s'INTERCALER entre `u(A)` et `u(A) + PossibleOverkill` -- donc etre INSENSIBLE au flag,
    # et pourtant proche. Le flag ne gouverne QUE `MightBeOverkill`, et il n'y mord que dans le cas
    # « letal MAIS sous le seuil » (`hp <= rawMax` et `(rawMax - hp) / hp * 100 < 100`) : c'est ce
    # cas-la, et lui seul, qu'il faut EVITER pour C. Les trois regimes possibles, derives de
    # `is_overkill` :
    #     hp_c > rawMax            -> ni kill ni overkill : `u(C) <= 100`, sous la fenetre ;
    #     rawMax / 2 < hp_c        -> LETAL SOUS LE SEUIL : C bouge AVEC le flag, comme A -> inutile
    #                                 (c'est ce que ce balayage faisait, d'ou son ensemble VIDE) ;
    #     rmin / 2 < hp_c <= rawMax / 2 -> `MightBeOverkill` VRAI inconditionnellement (rawMax >= 2 hp)
    #                                 et `WillBeOverkill` FAUX (rawMin < 2 hp, et cette borne-la passe
    #                                 `isCritical = 0` EN DUR) -> `PossibleOverkill` FIXE, plus
    #                                 `DefinitelyKill` (rawMin >= hp). Seul terme libre : `DamageDealt`,
    #                                 que `max_c` regle finement.
    # ⚠ La borne BASSE compte autant que la haute : sous `rmin / 2`, C devient `WillBeOverkill` et
    # empoche 40 au lieu de 15 -- il repasse au-dessus de la fenetre.
    hp_b = max(1, _rmin // 3)       # B : overkill GARANTI -> utilite HAUTE, au-dessus des deux
    c_hp_lo, c_hp_hi = _rmin // 2 + 1, rmax // 2
    # Le balayage est SEPARABLE, et il DOIT l'etre desormais : l'utilite d'un role ne depend que de
    # SES PV. Le produit cartesien naif (~34 000 couples x 6 evaluations) etait tenable tant que
    # `_target_utility` fabriquait un dict ; il ne l'est plus depuis qu'il monte une PREDICTION
    # COMPLETE. On evalue chaque (role, PV) UNE fois, puis on combine en pur numerique.
    def _u(role: int, hp: int, mx: int, mc: bool) -> float:
        return _utilites({role: (hp, mx)}, d, mc, reco)[role]

    pas = max(1, rmax // 40)
    if c_hp_lo > c_hp_hi:
        return {"ok": False, "raison": "fenetre C vide : rawMin=%d rawMax=%d" % (_rmin, rmax)}
    b_vals = [(hp_b, m) for m in range(hp_b, int(rmax * 1.2), pas)]
    c_vals = [(h, m) for h in range(c_hp_lo, c_hp_hi + 1, max(1, (c_hp_hi - c_hp_lo) // 8 or 1))
              for m in range(max(1, rmax // 2), int(rmax * 40), max(1, rmax // 4))]
    uA = {mc: _u(1, hp_a, hp_a, mc) for mc in (False, True)}
    uB = {mc: {v: _u(2, v[0], v[1], mc) for v in b_vals} for mc in (False, True)}
    uC = {mc: {v: _u(3, v[0], v[1], mc) for v in c_vals} for mc in (False, True)}
    for v_c in c_vals:
        for v_b in b_vals:
            u_off = {1: uA[False], 2: uB[False][v_b], 3: uC[False][v_c]}
            u_on = {1: uA[True], 2: uB[True][v_b], 3: uC[True][v_c]}
            o_off = sorted((1, 2, 3), key=lambda r: -u_off[r])
            o_on = sorted((1, 2, 3), key=lambda r: -u_on[r])
            if o_off[-1] == o_on[-1]:
                continue            # le DERNIER ne change pas -> rien d'observable
            marge = min(min(abs(u_off[x] - u_off[y]) for x, y in ((1, 2), (1, 3), (2, 3))),
                        min(abs(u_on[x] - u_on[y]) for x, y in ((1, 2), (1, 3), (2, 3))))
            if marge > marge_max:
                marge_max = marge
                trouve = {"hp_a": hp_a, "max_a": hp_a, "hp_b": v_b[0], "max_b": v_b[1],
                          "hp_c": v_c[0], "max_c": v_c[1],
                          "ordre_sans_crit": o_off, "ordre_avec_crit": o_on,
                          "u_sans": u_off, "u_avec": u_on, "marge": marge}
    if verbose:
        print("=== etage 1 -- REGIME discriminant (offline pur) ===")
        print("  degat du noeud de tri (dmin == dmax)      : %d" % d)
        print("  fenetre `letal SOUS le seuil` (hp in ...) : [%d, %d]" % (lo, hi))
        if not trouve:
            print("  AUCUN couple trouve -- le montage ne DISCRIMINE pas, la mesure live ne")
            print("  prouverait rien (les deux ordres seraient identiques quoi qu'il arrive).")
        else:
            print("  A : hp=%-6d maxHealth=%-6d  (DANS la fenetre)" % (trouve["hp_a"], trouve["max_a"]))
            print("  B : hp=%-6d maxHealth=%-6d  (SOUS la fenetre -> overkill inconditionnel)"
                  % (trouve["hp_b"], trouve["max_b"]))
            print("  C : hp=%-6d maxHealth=%-6d  (idem B, mais utilite INTERCALEE)"
                  % (trouve["hp_c"], trouve["max_c"]))
            print("  ordre SANS crit : %s   utilites %s"
                  % (trouve["ordre_sans_crit"],
                     {k: round(v, 4) for k, v in trouve["u_sans"].items()}))
            print("  ordre AVEC crit : %s   utilites %s"
                  % (trouve["ordre_avec_crit"],
                     {k: round(v, 4) for k, v in trouve["u_avec"].items()}))
            print("  marge MINIMALE des deux cotes            : %.4f" % trouve["marge"])
            print("  ecart d'utilite du flag sur A            : %.4f"
                  % (trouve["u_avec"][1] - trouve["u_sans"][1]))
            print("  -> l'argmax CHANGE : le flag deplace un CHOIX, pas un scalaire.")
    return {"ok": bool(trouve), **(trouve or {}), "d": d, "fenetre": [lo, hi]}


# --------------------------------------------------------------------------------------------
# etages 2 et 3 -- LIVE
# --------------------------------------------------------------------------------------------

def _dmg_min(level: int, mult: int) -> int:
    """Le noeud de degat que ce call-site branche sur `+0x40` :
    `Direct(GetVariableForLevel(0xc = minDmg, level))`, `+0x48` recevant null -> `dmax == dmin`."""
    return int(ability_var("Doombolt", "minDmg", level, multiplier_pct=mult) or 0)


def _ability_state_of(state, caster_id: int):
    """(level, multiplier) de l'ability du caster -- MEME foyer que l'ability elle-meme, pour que le
    degat du tri mesure ne puisse pas diverger de celui qu'elle utilise."""
    from engine.runner.abilities.thousandsons import _ability_state
    return _ability_state(state, caster_id)


def _reco_du_runner(a_units: str, regime_items: str, seed: str, board: str) -> "dict | None":
    """RECONNAISSANCE : le degat que le noeud de tri recevra REELLEMENT **et l'ETAT sur lequel la
    cle se calcule**, lus sur un runner.

    ⚠ Le degat ne se DEDUIT pas : `dmg_min = ability_var(minDmg, level, multiplier_pct=mult)` et les
    deux entrees viennent de l'UNITE (`_ability_state`). Supposer `level=50, mult=100` a donne 665
    la ou le runner rend une autre valeur -- et le regime calcule sur 665 ne discriminait alors RIEN
    (les deux ordres identiques). Un montage regle sur une valeur SUPPOSEE ne prouve rien.

    ⚠ **L'ETAT non plus (#494-r1-r1).** Depuis que la cle de tri passe par la PREDICTION COMPLETE
    par cible, un balayage sur stub a PV seuls regle le regime sur le chemin DEGRADE -- donc sur une
    cle qui n'est plus celle qui tourne. Ce runner est monte avec la MEME geometrie PLATE et la MEME
    neutralisation d'armure que le build final, pour que l'etage 1 balaie le bon substrat.

    Rend `{"d", "state", "caster", "cibles"}` (`cibles` = les ids des roles A / B / C, dans l'ordre
    des `--a-units` apres la cible du MESSAGE), ou `None` si le montage n'a pas tenu."""
    import probe_psychic_aoe as PA
    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state

    sid = R._resolve_session()
    noms = [s.strip() for s in a_units.split(",") if s.strip()]
    state_file = _ROOT / "logs" / "runners" / ("419r6r1-reco-%s.json" % uuid.uuid4().hex[:6])
    state_file.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
            "--roster", "1", "--p-units", CASTER, "--a-units", a_units,
            "--state-file", str(state_file)]
    if board == GEO_PLATE["board"]:
        argv += ["--place", "%s:%d,%d" % (CASTER, GEO_PLATE["caster"][0], GEO_PLATE["caster"][1])]
        for nom, pos in zip(noms, GEO_PLATE["cibles"]):
            argv += ["--a-place", "%s:%d,%d" % (nom, pos[0], pos[1])]
    for nom in noms[1:]:
        argv += ["--unit-stat", "%s:FixedArmor=0,Armor=0" % nom]
    if regime_items == "0":
        argv.append("--no-bis-items")
    subprocess.run(argv, cwd=str(_HERE), capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    if not state_file.exists():
        return None
    rid = json.loads(state_file.read_text())["runnerId"]
    live = PA.Live(sid, rid)
    try:
        bg = live.rpc("boardGraph", {"runnerId": rid}, 60)
        dec = live.dec()
        ob = live.rpc("observeBattle", {"runnerId": rid}, 60)
        snap = live.rpc("combatSnapshot", {"runnerId": rid}, 90)
        st = load_state(dec, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
        cid = next((u["id"] for u in (dec.get("units") or [])
                    if u.get("visualId") == CASTER), None)
        if cid is None:
            return None
        cibles = []
        for nom in noms[1:]:
            eid = next((u["id"] for u in (dec.get("units") or [])
                        if u.get("visualId") == nom and u.get("id") != cid), None)
            if eid is not None:
                cibles.append(int(eid))
        if len(cibles) < 3:
            return None
        lvl, mult = _ability_state_of(st, cid)
        return {"d": _dmg_min(lvl, mult), "state": st, "caster": int(cid), "cibles": cibles}
    finally:
        try:
            live.rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state_file.unlink()
        except Exception:
            pass


def _dmg_tri_du_runner(a_units: str, regime_items: str, seed: str, board: str) -> "int | None":
    """Alias historique : le seul degat, sans l'etat. Conserve pour les appelants qui n'ont pas
    besoin du substrat (`--etage regime` en ligne de commande)."""
    r = _reco_du_runner(a_units, regime_items, seed, board)
    return None if r is None else r["d"]


def etage_live(regime: dict, a_units: str, regime_items: str, seed: str, board: str,
               verbose: bool = True, crit: "str | None" = None) -> dict:
    """Monte le cas Doombolt avec les PV du regime et confronte l'ORDRE au live.

    `regime_items` : "defaut" (equipe -- ce que porte le code) ou "0" (temoin `--no-bis-items`).
    `crit` : `--crit <chance>,<degat>` epingle sur le CASTER (p-unit). C'est le CONTREFACTUEL qui
    separe << `CouldCrit(owner)` est faux >> de << le flag n'atteint pas ce chemin >> : a
    `100,700` la conjonction de `CouldCrit` est vraie de facon INCONTESTABLE, donc si l'ordre live
    ne bouge toujours pas, la premiere branche est ELIMINEE."""
    import probe_psychic_aoe as PA                       # montage partage, pas un second harnais
    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.abilities.handler import ABILITY_CLASSES
    Live = PA.Live                                        # le meme client RPC, pas un second

    sid = R._resolve_session()
    state_file = _ROOT / "logs" / "runners" / ("419r6r1-%s-%s.json" % (regime_items,
                                                                      uuid.uuid4().hex[:6]))
    state_file.parent.mkdir(parents=True, exist_ok=True)
    noms = [s.strip() for s in a_units.split(",") if s.strip()]
    # Les PV : la cible du MESSAGE est forcee en tete (Remove+Insert(0)) donc elle ne discrimine
    # rien ; ce sont les SUIVANTES qu'on regle sur les deux bandes du regime.
    #
    # ⚠ L'ARMURE EST MISE A ZERO, et ce n'est pas un confort. Le port tient la prediction IA pour
    # PRE-armure (`armor = 0`, en-tete de `services/damage_prediction`), donc il donne la MEME
    # plage a toutes les cibles ; si le natif, lui, reduisait par l'armure de CHAQUE cible, une
    # cible bien blindee cesserait d'etre `MightBeKill` et le classement basculerait pour une
    # raison qui n'a RIEN a voir avec `MightCrit`. Sans neutraliser cet etage, le montage ne
    # ISOLE pas le flag -- il attribuerait au flag un ecart d'armure.
    roles = [("hp_a", "max_a"), ("hp_b", "max_b"), ("hp_c", "max_c")]
    patchs = []
    for i, nom in enumerate(noms[1:]):
        if i >= len(roles):
            break
        k_hp, k_mx = roles[i]
        patchs.append("%s:Health=%d,RemainingHealth=%d,FixedArmor=0,Armor=0"
                      % (nom, regime[k_mx], regime[k_hp]))
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
            "--roster", "1", "--p-units", CASTER, "--a-units", a_units,
            "--state-file", str(state_file)]
    # #494-r1 : geometrie PLATE POSEE au build (cf. le bloc de commentaire de `etage_live`).
    # L'ordre des `--a-place` suit celui des `--a-units`, donc `noms[0]` = cible du MESSAGE (la
    # plus proche du caster) et `noms[1:]` = les roles A / B / C, dans l'ordre des `--unit-stat`.
    if board == GEO_PLATE["board"]:
        argv += ["--place", "%s:%d,%d" % (CASTER, GEO_PLATE["caster"][0], GEO_PLATE["caster"][1])]
        for nom, pos in zip(noms, GEO_PLATE["cibles"]):
            argv += ["--a-place", "%s:%d,%d" % (nom, pos[0], pos[1])]
    if regime_items == "0":
        argv.append("--no-bis-items")
    if crit:
        argv += ["--crit", crit]
    for p in patchs:
        argv += ["--unit-stat", p]
    p = subprocess.run(argv, cwd=str(_HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        return {"error": "build KO: " + (p.stderr or p.stdout or "")[-400:]}
    rid = json.loads(state_file.read_text())["runnerId"]
    live = Live(sid, rid)
    try:
        bg = live.rpc("boardGraph", {"runnerId": rid}, 60)
        board_o = Board(bg["tiles"], adjacency="native_sym")
        units = live.units()
        caster = next((u for u in units if u.get("visualId") == CASTER), None)
        if caster is None:
            return {"error": "caster %s absent du runner" % CASTER}
        enemies = [u for u in units if u.get("id") != caster["id"]]
        # #494-r1 -- GEOMETRIE SANS BONUS D'ELEVATION, obligatoire ici, et PLACEE et non DRIVEE.
        #
        # Ce montage mesure le flag `MightCrit`, qui ne mord que dans la fenetre « letal MAIS sous
        # le seuil d'overkill ». Depuis #494-r1 la cle de tri porte sa part POSITIONNELLE : une
        # cible plus BASSE que le caster voit sa plage predite multipliee par
        # `1 + ElevationBonus/100`, ce qui la fait SORTIR de la fenetre. Mesure : sur les 1870
        # regimes de PV qui rendent le montage discriminant a plat, **0** survit des qu'une des
        # trois cibles classantes recoit le bonus. Il FAUT donc une geometrie plate.
        #
        # `PA.pick_geometry` ne peut pas la fournir : elle cherche un HUB A 6 VOISINS, et sur les
        # boards du depot aucun n'a ses trois cibles classantes a une elevation >= celle du caster.
        # Une geometrie plate existe pourtant (`GEO_PLATE` ci-dessous, mesuree par `tileMeta` sur
        # `MC1_67` : tout le monde a l'elevation 3) -- elle n'est simplement pas un hub. On la POSE
        # donc au build (`--place` / `--a-place`), ce qui supprime au passage tout le drive et sa
        # part de contingence.
        if board == GEO_PLATE["board"]:
            geo = {"target": GEO_PLATE["cibles"][0], "extra": list(GEO_PLATE["cibles"][1:]),
                   "caster": GEO_PLATE["caster"]}
        else:
            geo = PA.pick_geometry(board_o, "db-4", set(), sans_bonus_elevation=True)
            if geo is None:
                return {"error": "aucune geometrie SANS bonus d'elevation sur " + board}
            wanted = [(enemies[0]["id"], geo["target"])]
            for i, pos in enumerate(geo["extra"]):
                if i + 1 < len(enemies):
                    wanted.append((enemies[i + 1]["id"], pos))
            wanted.append((caster["id"], geo["caster"]))
            for uid, dest in wanted:
                PA.drive_to(live, board_o, uid, dest)
        for _ in range(6):
            dv = live.dec()
            cu = next((u for u in (dv.get("units") or []) if u.get("id") == caster["id"]), None)
            if cu is not None and cu.get("owner") == dv.get("currentPlayer"):
                break
            live.endturn()
        dec1 = live.dec()
        ob1 = live.rpc("observeBattle", {"runnerId": rid}, 60)
        snap1 = live.rpc("combatSnapshot", {"runnerId": rid}, 90)
        s_cast = live.rpc("dumpRng", {"runnerId": rid}, 30)
        if not (isinstance(s_cast, dict) and s_cast.get("ok")):
            return {"error": "dumpRng KO"}
        cid = caster["id"]
        tid = next((u["id"] for u in (dec1.get("units") or [])
                    if PA._pos(u) == geo["target"] and u.get("alive")), None)
        if tid is None:
            return {"error": "cible introuvable sur " + str(geo["target"])}
        st = load_state(dec1, ob1, snap1, board=Board(bg["tiles"], adjacency="native_sym"))
        st.rng = PA._seed_rng(s_cast)
        mc = owner_might_crit(st, cid)
        # Les PV LUS PAR LE PORT (`HealthComponent`), pas ceux affiches par `decisionView` : c'est
        # `hp_max` qui gouverne `combinedMax`, donc le terme `DamageDealt`. Les confondre a deja
        # fait croire a un montage regle alors que `--unit-stat` n'avait pas mordu sur `Health`.
        pv = {}
        for eid, e in st.entities.items():
            hc = e.get_component(HealthComponent)
            if hc is not None:
                pv[int(eid)] = (int(hc.hp or 0), int(hc.hp_max or 0))
        # Les utilites PAR CIBLE, aux DEUX valeurs du flag, sur l'etat D'AVANT LE CAST. Les calculer
        # apres `execute_behaviour` les lirait sur des PV DEJA amputes -- c'est la faute que la
        # premiere ecriture de ce probe a commise, et elle rendait l'affichage incoherent avec
        # l'ordre imprime juste en dessous.
        _d = _dmg_min(*_ability_state_of(st, cid))
        _wt = damage_utility_weights()
        _cands = sorted(int(u["id"]) for u in (dec1.get("units") or [])
                        if u.get("alive") and int(u["id"]) != int(cid))
        res_u_sans = {t: _target_utility(st, t, _d, _d, _wt, False) for t in _cands}
        res_u_avec = {t: _target_utility(st, t, _d, _d, _wt, True) for t in _cands}
        # ORACLE NATIF du flag, INDEPENDANT du port : `combatSnapshot.normalAttack.mightCrit` est
        # le `MightCrit@0x8a` que le NATIF publie sur sa propre prediction d'attaque normale du
        # caster (`engine/predict.py::WeaponBase.from_snapshot` le lit deja). Si le natif y dit
        # `True` alors que le classement du selecteur se comporte comme si le flag valait `False`,
        # ce n'est PAS `CouldCrit` qui est en cause -- c'est que le flag n'atteint pas CE chemin.
        _sc = None
        for u in ((snap1 or {}).get("units") or []):
            if int(u.get("id") or -1) == int(cid):
                _sc = u
                break
        _na = (_sc or {}).get("normalAttack") or {}
        _cctx = st.get_entity(cid).get_component(StatsComponent)
        _cctx = _cctx.ctx if _cctx is not None else None
        oracle = {"snap.normalAttack.mightCrit": _na.get("mightCrit"),
                  "snap.critChance": (_sc or {}).get("critChance"),
                  "snap.critDamage": (_sc or {}).get("critDamage"),
                  "ctx.crit_chance": getattr(_cctx, "crit_chance", None),
                  "ctx.crit_damage": getattr(_cctx, "crit_damage", None)}
        diag = ABILITY_CLASSES[DOOMBOLT]().execute_behaviour(st, cid, tid)
        off = {}
        for a in (diag.get("attacks") or []):
            atk = a.get("attack") or {}
            off.setdefault(a["target"], []).extend(atk.get("per_hit") or [])
        # --- le MEME etat, mais avec le flag FORCE a l'autre valeur = le port d'AVANT -----------
        st2 = load_state(dec1, ob1, snap1, board=Board(bg["tiles"], adjacency="native_sym"))
        st2.rng = PA._seed_rng(s_cast)
        # CONTREFACTUEL : le port tel qu'il SERAIT s'il ne faisait PAS entrer `MightCrit` dans le
        # classement. `_target_utility` porte le parametre exactement pour ca (il n'est alimente
        # par aucune entree publique -- cf. son commentaire `#419-r6-r1`).
        import engine.runner.operations.damage_utility as DU
        _vrai = DU._target_utility
        # ⚠ Le substitut RELAIE TOUT ce que l'appelant passe, par `**kw` (#494-r1 puis #494-r1-r1) :
        # depuis que la cle porte sa part POSITIONNELLE puis la PREDICTION COMPLETE, les entrees
        # publiques appellent `_target_utility(..., owner_id=<caster>, ability_type=..., is_melee=
        # ...)`. Un substitut qui NOMME les kwargs mesurerait un AUTRE port que celui qui tourne des
        # qu'un s'ajoute -- il levait `TypeError` et faisait passer le rouge pour un echec de
        # montage. Le `**kw` est donc VOULU : il suit le foyer.
        #
        # ⚠ **LE CONTREFACTUEL A CHANGE DE SENS (#494-r1-r1).** Il jouait « le port s'il LISAIT le
        # flag » ; la production LE LIT desormais (le natif l'ecrit dans `PredictAttackRaw`, et la
        # mesure sur la cle corrigee le confirme). Le contrefactuel est donc « le port s'il ne le
        # lisait PAS » : on FORCE `might_crit=False`. `owner_might_crit` reste appele -- il DIT si le
        # canal est ouvert, ce que l'etage temoin exige.
        DU._target_utility = (lambda s, t, dm, dx, w, mc=None, _f=_vrai, _o=cid, **kw:
                              _f(s, t, dm, dx, w, False if owner_might_crit(s, _o) else None, **kw))
        try:
            diag_avant = ABILITY_CLASSES[DOOMBOLT]().execute_behaviour(st2, cid, tid)
        finally:
            DU._target_utility = _vrai
        off_avant = {}
        for a in (diag_avant.get("attacks") or []):
            atk = a.get("attack") or {}
            off_avant.setdefault(a["target"], []).extend(atk.get("per_hit") or [])
        # --- LIVE --------------------------------------------------------------------------------
        cast = live.rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": DOOMBOLT},
            "captureEvents": True}, 150)
        if not (isinstance(cast, dict) and cast.get("ok")):
            return {"error": "cast KO: " + str(cast)[:300]}
        a0 = (cast.get("actions") or [{}])[0]
        livehits = {}
        for e in (a0.get("events") or []):
            tg = PA._tags(e)
            if "Amount" in tg and tg.get("Active_Ability_Type") == DOOMBOLT:
                livehits.setdefault(tg.get("Target_Id"), []).append(int(tg.get("Amount") or 0))
        res = {"regime_items": regime_items, "runner": rid, "caster": cid, "target": tid,
               "might_crit_owner": bool(mc), "pv": pv, "dmg_tri": _d, "oracle_natif": oracle,
               "u_sans": res_u_sans, "u_avec": res_u_avec,
               "ordre_production": diag["targets"], "hits_production": diag["hits"],
               "ordre_contrefactuel": diag_avant["targets"], "hits_contrefactuel": diag_avant["hits"],
               "off_production": off, "off_contrefactuel": off_avant, "live": livehits}
        allt = sorted(set(list(off.keys()) + list(off_avant.keys()) + list(livehits.keys())))
        res["exact_production"] = all(livehits.get(t, []) == off.get(t, []) for t in allt)
        res["exact_contrefactuel"] = all(livehits.get(t, []) == off_avant.get(t, []) for t in allt)
        res["montage_discriminant"] = diag["targets"] != diag_avant["targets"]
        if verbose:
            print("\n=== etage %s -- LIVE (TACTICUS_BIS_ITEMS=%s) ==="
                  % ("2" if regime_items != "0" else "3 (TEMOIN)", regime_items))
            print("  caster u%s  cible-du-message u%s  CouldCrit(owner)=%s" % (cid, tid, bool(mc)))
            print("  stats crit du caster : %s" % oracle)
            print("  PV LUS PAR LE PORT (id: hp/hp_max) : %s" % pv)
            print("  utilites par cible  SANS le flag : %s"
                  % {k: round(v, 3) for k, v in res_u_sans.items()})
            print("  utilites par cible  AVEC le flag : %s"
                  % {k: round(v, 3) for k, v in res_u_avec.items()})
            print("  ordre PORT (production, AVEC flag) : %-24s hits=%s"
                  % (diag["targets"], diag["hits"]))
            print("  ordre CONTREFACTUEL (SANS flag)    : %-24s hits=%s"
                  % (diag_avant["targets"], diag_avant["hits"]))
            for t in allt:
                print("    u%-4s live=%-22s production=%-22s contrefactuel=%-22s"
                      % (t, livehits.get(t, []), off.get(t, []), off_avant.get(t, [])))
            print("  BIT-EXACT vs live : PRODUCTION=%s  CONTREFACTUEL=%s"
                  % (res["exact_production"], res["exact_contrefactuel"]))
            print("  montage DISCRIMINANT (les deux ordres different) : %s"
                  % res["montage_discriminant"])
            if res["montage_discriminant"] and res["exact_production"] \
                    and not res["exact_contrefactuel"]:
                print("  => le NATIF ne fait PAS entrer `MightCrit` dans ce classement.")
        return res
    finally:
        try:
            live.rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state_file.unlink()
        except Exception:
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--regime", action="store_true", help="etage 1 seul (offline pur)")
    ap.add_argument("--live", action="store_true", help="etage 2 (regime EQUIPE, le defaut)")
    ap.add_argument("--temoin", action="store_true", help="etage 3 (--no-bis-items)")
    ap.add_argument("--level", type=int, default=50, help="niveau d'ability normalise")
    ap.add_argument("--mult", type=int, default=100)
    ap.add_argument("--dmg-tri", type=int, default=None,
                    help="degat du noeud de tri IMPOSE (sinon LU sur un runner de reconnaissance)")
    ap.add_argument("--crit", default=None,
                    help="CONTREFACTUEL : `--crit <chance>,<degat>` epingle sur le caster. A "
                         "`100,700`, `CouldCrit(owner)` est vrai de facon incontestable -- si "
                         "l'ordre live ne bouge PAS, la cause n'est pas le flag du caster")
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--a-units", default="necroOverlord,necroWarden,eldarRanger,orksNob")
    a = ap.parse_args(argv)
    if not (a.regime or a.live or a.temoin):
        a.regime = a.live = a.temoin = True

    d, reco = a.dmg_tri, None
    if d is None and (a.live or a.temoin):
        reco = _reco_du_runner(a.a_units, "defaut", a.seed, a.board)
        d = None if reco is None else reco["d"]
        print("[419-r6-r1] degat du noeud de tri LU sur un runner : %s" % d)
    if d is None:
        d = _dmg_min(a.level, a.mult)
        print("[419-r6-r1] degat du noeud de tri SUPPOSE (level=%d, mult=%d) : %d -- une mesure"
              " live le REMPLACERAIT" % (a.level, a.mult, d))
    if reco is None:
        print("[419-r6-r1] ATTENTION : etage 1 SANS substrat reel -> chemin DEGRADE : le regime trouve peut"
              " ne PAS discriminer en live (#494-r1-r1).")
    reg = etage_regime(d, verbose=True, reco=reco)
    if not reg.get("ok"):
        print("[419-r6-r1] etage 1 SANS regime discriminant -- rien a mesurer live.")
        return 1
    rc = 0
    if a.live:
        r2 = etage_live(reg, a.a_units, "defaut", a.seed, a.board, crit=a.crit)
        if r2.get("error"):
            print("  [etage 2] ERREUR :", r2["error"])
            rc = 2
    if a.temoin:
        r3 = etage_live(reg, a.a_units, "0", a.seed, a.board, crit=a.crit)
        if r3.get("error"):
            print("  [etage 3] ERREUR :", r3["error"])
            rc = rc or 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
