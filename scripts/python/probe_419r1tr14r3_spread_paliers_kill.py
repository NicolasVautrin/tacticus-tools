"""#419-r1-tr14-r3 -- le spread +/-20 % DISCRIMINE-t-il, dans un regime ou la cible peut MOURIR ?

La tranche 14 avait mesure le mutant `spread0` **inerte aux quatre crans**, et l'avait dit sans
pouvoir trancher : a `Health = 10000` personne ne meurt, et le composite Damage ne consomme alors
que la MOYENNE des bornes -- `min_max_avg(healthDmgMin, healthDmgMax)`, qui vaut `base` que le
spread soit 0 ou 20. L'inertie y etait donc une propriete ALGEBRIQUE du regime, pas une preuve.

## L'ETAGE ou le spread devient OBSERVABLE

Le composite Damage (`DAMAGE_UTILITY` = `DamageUtility` + `KillUnitUtility` + `OverkillUnitUtility`)
consomme les bornes de DEUX facons :

    DamageUtility       min_max_avg(healthDmgMin, healthDmgMax)      <- MOYENNE : inerte au spread
    KillUnitUtility     killSure = rawMin >= hp   -> DefinitelyKill  <- PALIER sur la borne BASSE
                        kill     = rawMax >= hp   -> PossibleKill    <- PALIER sur la borne HAUTE
    OverkillUnitUtility WillBeOverkill  = rawMin >= 2*hp             <- PALIER (seuil 100 %)
                        MightBeOverkill = rawMax >= 2*hp             <- PALIER

Les paliers sont des COMPARAISONS `borne vs PV`. Ils ne peuvent donc distinguer `spread 0`
(`min == max == base`) de `spread 20` (`min = 0.8 base`, `max = 1.2 base`) que si les PV de la
cible tombent ENTRE les deux bornes. C'est exactement ce que ce probe installe -- et il DERIVE les
PV du cran depuis les bornes MESUREES, il ne les devine pas.

    cran                PV de la cible          ce qu'il installe
    `hp_hors`           10000 (>> rawMax)       AUCUN palier -- TEMOIN d'inertie EXIGEE
    `fenetre_kill`      (rawMin+rawMax)//2      `kill` sans `killSure` a spread 20 ; a spread 0 les
                                                deux basculent ENSEMBLE -> le terme SAUTE
    `fenetre_overkill`  (rawMin+rawMax)//4      `MightBeOverkill` sans `WillBeOverkill` -- et les PV
                                                y sont SOUS `rawMin`, donc kill+killSure sont vrais
                                                des DEUX cotes : ce cran ISOLE `OverkillUnitUtility`

## CE QUE LA RE A DEJA ETABLI, ET QUE LA MESURE VIENT ARBITRER (`#419-r1-tr5-r2`)

Les deux surcharges « a montant » de `IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction`
ne sont PAS deux chemins : celle a `casterPosition:IEntity` (slot **0x23**, celle de `psyker` et
d'`avalanche_of_muscle`) construit un `IdunBattle.Core.UnitPosition$$.ctor` depuis l'entite puis
**APPELLE** celle a `casterPosition:UnitPosition` (slot **0x24**, celle de CE module). C'est un
THUNK. Les deux atteignent donc le MEME
`IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction` (slot 10 d'
`IDamagePredictionQuery`), qui ecrit le meme octet `request+0x6a = 1` -- lu dans le decompile :
`uStack_1ce = 1`, recopie par `uStack_110 = CONCAT53(uStack_1cd, CONCAT12(uStack_1ce, uStack_1d0))`
a l'offset `+0x68 + 2`.

=> `psyker.py`/`avalanche_of_muscle.py` (`spread_pct=0`) et `heavy_bolt_pistol.py`/`light_im_up.py`
(spread par DEFAUT) modelisent le MEME appel natif de deux facons contradictoires. Un seul peut
etre juste, et c'est le TERME NATIF qui arbitre.

## LE MONTAGE

Celui de la tranche 14, REUTILISE tel quel (module `probe_419r1tr14_heavy_bolt_pistol`) : bras
APPARIE `graft` (1083 greffe sur `tauMarksman`) / `base` (le meme, MOINS 1083), board `MC1_67`,
caster place sur `A` (adjacent a la cible `T`) -- le seul emplacement ou le terme est NON NUL.
`terme_natif = natif_graft - natif_base`, `terme_porte = port - port_sans_playbook`.

Le seul degre de liberte ajoute est les **PV de la cible**, poses au build par `--unit-stat`. Les
bornes RAW (`rawHealthDmgMin`/`Max`) n'en dependent PAS -- le cap par PV restants ne touche que les
bornes CAPEES (`accurate_health_damage`) -- donc un calibrage mesure a `hp_hors` reste valide aux
autres crans. Le probe le RE-VERIFIE a chaque cran plutot que de le supposer.

## CONTRE-EPREUVES -- chacune DECLARE son observable

    `spread0`   `spread_pct = 0` sur la prediction du playbook
                 -> EXIGE l'INERTIE a `hp_hors` (propriete algebrique de la moyenne)
                 -> EXIGE de MORDRE a `fenetre_kill` et a `fenetre_overkill`

`a_mordu` est rendu SEPARE du verdict. L'inertie attendue est assertionnee A L'ENVERS (on EXIGE
qu'elle soit inerte) plutot que tue : c'est precisement ce qui a manque a la tranche d'origine.

Usage :
    python scripts/python/probe_419r1tr14r3_spread_paliers_kill.py --state-file <ABSOLU>
        [--state-file-base <ABSOLU>] [--crans hp_hors,fenetre_kill,fenetre_overkill]

ASCII only. Garde jumelle :
`scripts/python/tests/engine/test_419r1tr14r3_spread_paliers_kill_live.py`.
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

import probe_124_line_elevation_decision as P124                 # noqa: E402
import probe_419r1tr14_heavy_bolt_pistol as P14                  # noqa: E402
from engine.utilities.damage import (DamageUtility, KillUnitUtility,        # noqa: E402
                                     OverkillUnitUtility, might_be_overkill,
                                     will_be_overkill)

MontageError = P14.MontageError

#: Les PV du cran TEMOIN -- ceux de la tranche 14, ou aucun palier n'est franchissable.
HP_HORS = P14.HP
#: Le seed et le board sont ceux de la tranche 14 : le montage n'a QU'UN degre de liberte de plus.
SEED = P14.SEED
BOARD = P14.BOARD
EPS = 1e-4

#: `(nom du cran, comment ses PV se DERIVENT des bornes RAW mesurees)`. Aucun PV en dur hors du
#: temoin : les trois autres sont des FONCTIONS des bornes, donc le cran suit le montage s'il bouge.
CRANS = ("hp_hors", "fenetre_kill", "fenetre_overkill")


def bornes_attendues(raw_min: int, raw_max: int) -> tuple:
    """Les bornes RAW que le natif DOIT rendre, derivees d'une source INDEPENDANTE du code teste.

    ⚠ POINT DE METHODE, et il a ete trouve EN VOYANT LA GARDE ROUGE. Un premier jet calibrait les
    PV des crans sur les bornes MESUREES par le playbook. Mute (`spread_pct=0` pose dans le port
    LIVRE), il rendait `[299, 299]` -- amplitude nulle -- et la garde echouait en disant « le
    montage NE PEUT PAS discriminer ». Elle accusait donc le MONTAGE pour une faute du PORT : le
    lecteur aurait cherche un board casse au lieu d'une lecture fausse.

    Le calibrage prend desormais le seul CENTRE de l'intervalle mesure (`base`, que la mutation ne
    deplace pas) et lui applique le spread LU DE LA BATAILLE
    (`BattleConfiguration.Damage.DamageSpreadPercentage`, via le foyer
    `engine.services.damage_config.resolve_spread_pct`), qui n'est PAS ce que le playbook decide.
    Les PV des crans sont donc les MEMES que le port soit sain ou mute -- et c'est alors le port qui
    rougit, a l'etage 1 (temoin nul), 3 (terme != natif) et 4 (contre-epreuve inerte)."""
    from engine.services.damage_calculations import spread_to_min_max
    base = (int(raw_min) + int(raw_max)) // 2
    mm = spread_to_min_max(base)
    return int(mm.min), int(mm.max)


def hp_du_cran(cran: str, raw_min: int, raw_max: int) -> int:
    """Les PV a poser sur la cible pour installer le regime du cran, DERIVES des bornes."""
    if cran == "hp_hors":
        return HP_HORS
    if cran == "fenetre_kill":
        # rawMin < hp <= rawMax  ->  `kill` vrai, `killSure` faux (a spread 20)
        return (int(raw_min) + int(raw_max)) // 2
    if cran == "fenetre_overkill":
        # rawMin < 2*hp <= rawMax  ->  `MightBeOverkill` vrai, `WillBeOverkill` faux (a spread 20)
        return (int(raw_min) + int(raw_max)) // 4
    raise MontageError(f"cran inconnu : {cran}")


# --------------------------------------------------------------------------- montage

def build_args(logs_dir: str, arm: str, hp_cible: int) -> list:
    """Les arguments `rl_duel build`, identiques a ceux de la tranche 14 SAUF les PV de la cible."""
    stats = ";".join(f"{v}:Health={HP_HORS},RemainingHealth={HP_HORS}"
                     for v in P14.MINE + (P14.FOE1,))
    stats += f";{P14.T_MAIN}:Health={int(hp_cible)},RemainingHealth={int(hp_cible)}"
    return ["--board", P14.BOARD, "--p-units", ",".join(P14.MINE),
            "--a-units", ",".join(P14.FOES), "--unit-stat", stats,
            "--seed-bc", P14.seed_bc(logs_dir, arm)]


def _build(state_file: str, extra: list) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", P14.SEED,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def _dispose(rpc, rid) -> None:
    try:
        rpc("disposeRunner", {"runnerId": int(rid)}, 60)
    except Exception:
        pass


# --------------------------------------------------------------------------- etage 1 : les BORNES

def _capture_prediction(ctx, ab, tgt, tile, spread0: bool) -> dict:
    """ETAGE 1+2 : les BORNES que le playbook LIVRE fabrique, et les PALIERS qui en decoulent.

    Espionne `calculate_utility_from_damage_event` a l'interieur du module LIVRE plutot que de
    re-derouler sa logique : un espion qui re-implemente ne prouve rien sur le code livre."""
    from engine.playbook import heavy_bolt_pistol as HB
    vu = {}

    saved_u = HB.calculate_utility_from_damage_event
    saved_p = HB.get_attack_prediction

    def _espion(ev, wt, hpmax=None):
        vu["fields"] = ev.composite_fields()
        vu["hpmax"] = hpmax
        vu["wt"] = wt
        return saved_u(ev, wt, hpmax)

    HB.calculate_utility_from_damage_event = _espion
    if spread0:
        HB.get_attack_prediction = lambda **k: saved_p(**{**k, "spread_pct": 0})
    try:
        u = P14.pair_port(ctx, ab, tgt, tile)
    finally:
        HB.calculate_utility_from_damage_event = saved_u
        HB.get_attack_prediction = saved_p
    if "fields" not in vu:
        raise MontageError("le playbook 1083 n'a produit AUCUN event de degat -- la gate a coupe, "
                           "le cran ne mesure RIEN (jamais un vert silencieux)")
    f = vu["fields"]
    return {"u_pair": u,
            "healthDmgMin": f.get("healthDmgMin"), "healthDmgMax": f.get("healthDmgMax"),
            "rawHealthDmgMin": f.get("rawHealthDmgMin"), "rawHealthDmgMax": f.get("rawHealthDmgMax"),
            "hpBefore": f.get("hpBefore"),
            "kill": bool(f.get("kill")), "killSure": bool(f.get("killSure")),
            "willOverkill": bool(will_be_overkill(f)), "mightOverkill": bool(might_be_overkill(f)),
            # ETAGE 3 : les trois feuilles du composite, SEPAREES
            "u_damage": float(DamageUtility().evaluate(f, vu["hpmax"], vu["wt"])),
            "u_kill": float(KillUnitUtility().evaluate(f, vu["hpmax"], vu["wt"])),
            "u_overkill": float(OverkillUnitUtility().evaluate(f, vu["hpmax"], vu["wt"]))}


# --------------------------------------------------------------------------- une passe = un cran

def mesure_sur_runners(sid, rpc, rid_g: int, rid_b: int, cran: str, hp_cible: int,
                       layout) -> dict:
    """Les QUATRE etages sur deux runners DEJA construits aux PV du cran.

    Separee de `mesure_cran` pour que la garde pytest reutilise le cycle de vie de la conftest
    (`build_runner`) au lieu de re-piloter `rl_duel` en sous-processus."""
    graft = P14.stage(sid, rpc, rid_g, layout, True)
    base = P14.stage(sid, rpc, rid_b, graft["layout"], False)
    P14.place(sid, graft, "A")
    P14.place(sid, base, "A")
    _dv, ctx = P14._fresh_ctx(rpc, graft["rid"], graft["cid"])
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")
    tile = graft["layout"]["A"]
    tgt = graft["ids"]["T"]
    if tile not in [t for t in (ctx.action_tiles or []) if t and t[0] is not None]:
        raise MontageError(f"cran {cran} NON MESURABLE : tuile {tile} hors des tuiles d'action")

    # ETAGE 4 -- le TERME, natif (bras apparie) contre porte (playbook retire du registre).
    nat_g = P14.pair_native(rpc, graft["rid"], graft["cid"], tgt, ab, tile)
    nat_b = P14.pair_native(rpc, base["rid"], base["cid"], base["ids"]["T"], ab, tile)
    muted = P14.pair_port_muted(ctx, ab, tgt, tile)

    s20 = _capture_prediction(ctx, ab, tgt, tile, spread0=False)
    s00 = _capture_prediction(ctx, ab, tgt, tile, spread0=True)
    return {"cran": cran, "hp_cible": int(hp_cible), "tile": tile, "ab": ab,
            "rid_graft": rid_g, "rid_base": rid_b, "layout": graft["layout"],
            "native_graft": nat_g, "native_base": nat_b, "native_term": nat_g - nat_b,
            "port_muted": muted,
            "spread20": s20, "spread0": s00,
            "port_term_20": s20["u_pair"] - muted,
            "port_term_00": s00["u_pair"] - muted,
            # `a_mordu` = DEPLACEMENT du port mute par rapport au port NON mute (jamais l'ecart
            # au natif -- un mutant inerte le franchirait aussi, piege #441/#446).
            "deplacement_spread0": s00["u_pair"] - s20["u_pair"]}


def mesure_cran(sid, rpc, logs: str, sf_g: str, sf_b: str, cran: str, hp_cible: int,
                layout) -> dict:
    """Monte les DEUX bras aux PV du cran, mesure, puis DISPOSE ses propres runners."""
    rid_g = _build(sf_g, build_args(logs, "graft", hp_cible))
    rid_b = _build(sf_b, build_args(logs, "base", hp_cible))
    try:
        return mesure_sur_runners(sid, rpc, rid_g, rid_b, cran, hp_cible, layout)
    finally:
        _dispose(rpc, rid_g)
        _dispose(rpc, rid_b)


# --------------------------------------------------------------------------- attestations

def attester_regime(r: dict) -> list:
    """Le cran installe-t-il REELLEMENT le regime qu'il annonce ? Rend la liste des manquements.

    C'est l'anti-regime-degenere : un cran qui n'installe pas son palier rendrait la meme chose des
    deux cotes, et cette egalite ne prouverait RIEN."""
    bad = []
    a, b = r["spread20"], r["spread0"]
    cran = r["cran"]
    # TEMOIN NON NUL : sans lui, `spread0` inerte ne veut rien dire. Le reproche vise le PORT, et il
    # NOMME la source independante qui le contredit (le spread de la BATAILLE), pour qu'un lecteur
    # n'aille pas soupconner le montage.
    att = bornes_attendues(a["rawHealthDmgMin"], a["rawHealthDmgMax"])
    if a["rawHealthDmgMin"] == a["rawHealthDmgMax"]:
        bad.append(f"[{cran}] TEMOIN NUL : le PORT rend des bornes RAW EGALES "
                   f"({a['rawHealthDmgMin']}) la ou le spread LU DE LA BATAILLE "
                   f"(`DamageSpreadPercentage`) en exige {list(att)} -- c'est la LECTURE du port "
                   f"qui est en cause, pas le montage")
    if b["rawHealthDmgMin"] != b["rawHealthDmgMax"]:
        bad.append(f"[{cran}] la mutation `spread0` N'A PAS MORDU sur les bornes : "
                   f"[{b['rawHealthDmgMin']}, {b['rawHealthDmgMax']}] au lieu d'un point")
    if cran == "hp_hors":
        if a["kill"] or a["killSure"] or a["mightOverkill"]:
            bad.append(f"[{cran}] regime NON INSTALLE : un palier est franchi "
                       f"(kill={a['kill']} killSure={a['killSure']} might={a['mightOverkill']})")
    elif cran == "fenetre_kill":
        if not (a["kill"] and not a["killSure"]):
            bad.append(f"[{cran}] regime NON INSTALLE : voulu kill=True killSure=False, "
                       f"obtenu kill={a['kill']} killSure={a['killSure']} "
                       f"(PV={r['hp_cible']}, RAW=[{a['rawHealthDmgMin']}, {a['rawHealthDmgMax']}])")
    elif cran == "fenetre_overkill":
        if not (a["mightOverkill"] and not a["willOverkill"]):
            bad.append(f"[{cran}] regime NON INSTALLE : voulu might=True will=False, obtenu "
                       f"might={a['mightOverkill']} will={a['willOverkill']} "
                       f"(PV={r['hp_cible']}, RAW=[{a['rawHealthDmgMin']}, {a['rawHealthDmgMax']}])")
        if not (a["kill"] and a["killSure"]):
            bad.append(f"[{cran}] cran NON ISOLANT : kill={a['kill']} killSure={a['killSure']} -- "
                       f"ce cran doit avoir le kill acquis des DEUX cotes pour isoler l'overkill")
    return bad


def attendu_mord(cran: str) -> bool:
    """L'observable DECLARE de la contre-epreuve `spread0`, cran par cran."""
    return cran != "hp_hors"


def verdict(rows: list) -> list:
    """Rend la liste des DESACCORDS. Vide = le probe a tranche dans le sens du spread +/-20 %."""
    bad = []
    for r in rows:
        bad += attester_regime(r)
        cran = r["cran"]
        mordu = abs(r["deplacement_spread0"]) > EPS
        veut = attendu_mord(cran)
        if mordu != veut:
            bad.append(f"[{cran}] contre-epreuve `spread0` : a_mordu={mordu} (attendu {veut}), "
                       f"deplacement={r['deplacement_spread0']:+.6f}")
        # ARBITRAGE : le terme NATIF tranche entre les deux lectures du port.
        e20 = r["port_term_20"] - r["native_term"]
        e00 = r["port_term_00"] - r["native_term"]
        if abs(e20) > EPS:
            bad.append(f"[{cran}] le port au spread +/-20 % NE reproduit PAS le natif : "
                       f"terme porte {r['port_term_20']:+.6f} vs natif {r['native_term']:+.6f} "
                       f"(ecart {e20:+.6f})")
        if veut and abs(e00) <= EPS:
            bad.append(f"[{cran}] le port a `spread_pct=0` reproduit AUSSI le natif "
                       f"(ecart {e00:+.6f}) -- ce cran ne DISCRIMINE donc pas les deux lectures")
    return bad


# --------------------------------------------------------------------------- CLI

def _print(r: dict) -> None:
    a, b = r["spread20"], r["spread0"]
    print(f"  [{r['cran']:<17}] PV cible={r['hp_cible']} tile={r['tile']}")
    print(f"      etage 1 BORNES   spread20 raw=[{a['rawHealthDmgMin']}, {a['rawHealthDmgMax']}] "
          f"cap=[{a['healthDmgMin']}, {a['healthDmgMax']}] | "
          f"spread00 raw=[{b['rawHealthDmgMin']}, {b['rawHealthDmgMax']}]")
    print(f"      etage 2 PALIERS  spread20 kill={a['kill']} sure={a['killSure']} "
          f"might={a['mightOverkill']} will={a['willOverkill']} | "
          f"spread00 kill={b['kill']} sure={b['killSure']} "
          f"might={b['mightOverkill']} will={b['willOverkill']}")
    print(f"      etage 3 FEUILLES spread20 dmg={a['u_damage']:.6f} kill={a['u_kill']:.6f} "
          f"over={a['u_overkill']:.6f} | spread00 dmg={b['u_damage']:.6f} "
          f"kill={b['u_kill']:.6f} over={b['u_overkill']:.6f}")
    print(f"      etage 4 TERME    natif={r['native_term']:+.6f} port20={r['port_term_20']:+.6f} "
          f"(ecart {r['port_term_20'] - r['native_term']:+.9f}) "
          f"port00={r['port_term_00']:+.6f} "
          f"(ecart {r['port_term_00'] - r['native_term']:+.9f})")
    mordu = abs(r["deplacement_spread0"]) > EPS
    print(f"      contre-epreuve `spread0` : deplacement={r['deplacement_spread0']:+.9f} "
          f"a_mordu={mordu} (attendu {attendu_mord(r['cran'])})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du bras GREFFE")
    ap.add_argument("--state-file-base", help="chemin ABSOLU du bras APPARIE")
    ap.add_argument("--crans", default=",".join(CRANS))
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    sf_g = args.state_file
    sf_b = args.state_file_base or (os.path.splitext(sf_g)[0] + "_base.json")
    logs = os.path.dirname(os.path.abspath(sf_g))
    os.makedirs(logs, exist_ok=True)
    crans = [c.strip() for c in args.crans.split(",") if c.strip()]
    if "hp_hors" not in crans:
        raise MontageError("`hp_hors` est le cran de CALIBRAGE (il fournit les bornes RAW dont les "
                           "autres crans derivent leurs PV) -- il ne peut pas etre retire")

    rows = []
    # Passe 1 : le TEMOIN, qui est AUSSI le calibrage.
    r0 = mesure_cran(sid, rpc, logs, sf_g, sf_b, "hp_hors", HP_HORS, None)
    rows.append(r0)
    layout = r0["layout"]
    mes = (int(r0["spread20"]["rawHealthDmgMin"]), int(r0["spread20"]["rawHealthDmgMax"]))
    raw_min, raw_max = bornes_attendues(*mes)
    print(f"calibrage (cran `hp_hors`) : bornes RAW mesurees = {list(mes)} ; ATTENDUES du spread "
          f"de bataille = [{raw_min}, {raw_max}] -- amplitude {raw_max - raw_min} "
          f"(les PV des crans derivent des ATTENDUES, pas des mesurees)")
    if raw_max - raw_min < 2:
        raise MontageError(
            f"amplitude ATTENDUE du spread trop faible ({raw_max - raw_min}) : elle vient de "
            f"`BattleConfiguration.Damage.DamageSpreadPercentage`, donc c'est bien le MONTAGE (ou "
            f"la BC) qui ne peut pas discriminer -- pas le port")

    for cran in crans:
        if cran == "hp_hors":
            continue
        hp = hp_du_cran(cran, raw_min, raw_max)
        rows.append(mesure_cran(sid, rpc, logs, sf_g, sf_b, cran, hp, layout))

    for r in rows:
        _print(r)
    bad = verdict(rows)
    if bad:
        print("DESACCORDS :")
        for b in bad:
            print(f"  - {b}")
        return 1
    print("OK -- le spread +/-20 % est CONFIRME : il discrimine des que la cible peut mourir, "
          "et le port au spread par defaut reproduit le natif a chaque cran.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
