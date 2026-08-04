"""#419-r1-tr14-r5-r2 -- la voie ACTIVE du dispatch d'attaque normale.

`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` consulte DEUX voies, dans cet
ordre : `GetCustomNormalAttackTypeFromPassive` (`config@+0xa8`, table a 14 entrees, portee et
fermee par #419-r1-tr14-r5-r1) puis, SEULEMENT si la premiere rend `null`,
`GetCustomNormalAttackTypeFromActive` (`config@+0xa0`).

La table de la voie ACTIVE est celle de
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$GetCustomNormalAttack`
-- statics `+0xb8` -> `+0x28`, une AUTRE table que la passive (`+0x50` de
`StaticBattleRules.TriggeredAbility`). Son `.cctor` empile UN SEUL `Add` a litteraux constants :
`1124 PoundThemToDust` -> `1126 RogalDorn_NormalAttack`, les deux `ActiveAbilityType`.

## Le canal, et pourquoi aucun capteur neuf

Meme canal que le volet `table` de -r1 : `decisionView.units[].abilities` avec `kind == "normal"`,
c.-a-d. `ActiveAbilityComponent.NormalAttackType@0x28`, LE champ que la fabrique ecrit. Il couvre
toutes les unites du board.

## LE DISCRIMINANT, ENONCE AVANT LA MESURE

`PoundThemToDust` n'a AUCUN porteur : 0 sur les 683 kits gameconfig (5 voies), 0 sur les 175 unites
du seed BC. Le substrat `BC.Units[].ActiveAbilities` est en revanche ECRIVABLE
(`catalog_inject.graft_active_ability`, #447) -- c'est le meme levier que le chemin B de -r1, sur
l'AUTRE champ.

* `--volet active` -- QUATRE unites, un seul runner, chacune son bras. La table native ne peut rendre
  que `1126` ; toute autre reponse la refute.

  | unite            | `PassiveAbilities` | `ActiveAbilities` | natif ATTENDU | role |
  |------------------|--------------------|-------------------|---------------|------|
  | `astraBullgryn`  | `[]`               | `[1124]`          | **`1126`**    | PREUVE : la voie active substitue |
  | `necroWarden`    | `[]`               | (origine)         | **`69`**      | TEMOIN : montage vivant, pas de substitution |
  | `orksNob`        | `[1090 Boltstorm]` | `[1124]`          | **`1128`**    | BORNE : la voie PASSIVE gagne |
  | `eldarRanger`    | `[1090 Boltstorm]` | (origine)         | **`1128`**    | controle apparie du precedent |

  Le TEMOIN n'est pas decoratif : sans lui, un montage qui n'aurait rien installe rendrait des `69`
  partout et se lirait comme « la voie active ne substitue pas ». Le bras BORNE est le regime ou
  les deux modeles (avec et sans voie active) COINCIDENT -- il ne prouve rien, il BORNE : un port
  qui deborderait et laisserait la voie active gagner sur `orksNob` le ferait rougir.

* `--volet pred` -- ce que la substitution CHANGE, en degat. DEUX runners identiques a UNE ecriture
  pres (`astraBullgryn.ActiveAbilities`), meme board, meme seed, meme cible, meme tuile :

  - bras `act`  : `ActiveAbilities = [1124]`  -> attaque normale native `1126`
  - bras `ctrl` : `ActiveAbilities` d'origine -> attaque normale native `69`

  On lit `aiPlaybookPredict` (`healthDmgMin/Max`, `appliedHits`) sur les deux, et le port sur les
  deux. Question BINAIRE tranchee par cette mesure, et posee AVANT elle :

    si `nat(act) == nat(ctrl)`  -> la substitution ne change QUE l'identite de l'ability ;
                                   porter la table ne deplacerait aucun chiffre de prediction.
    si `nat(act) != nat(ctrl)`  -> le port, qui ignore la voie active, reste sur le chemin ARME et
                                   DIVERGE ; l'ecart mesure est le prix du residu.

  ⚠ Ce n'est pas une question rhetorique : `IdunBattleLogic.Entities.Abilities.Active.Loki.RogalDorn_NormalAttackAbility$$.ctor`
  appelle `IdunBattle.Entities.Abilities.ADeprecatedActiveAbility$$.ctor`, PAS
  `ALoki_NormalAttackAbility` -- l'attaque normale substituee par la voie active n'a donc pas le
  meme socle que celles de la voie passive.

* `--volet mow` -- le PIEGE annonce. `engine/ai/context.py::build_machine` pose `normal_ids = set()`
  au motif que « les 8 MoW du pool ont `weapons=[]` en gameconfig », c.-a-d. une derivation du KIT
  -- exactement la forme de raisonnement que #551 a fermee sur la voie passive. Ce que le natif dit,
  lui : `IdunBattle.Entities.Factories.MachineFactory$$Build` n'appelle JAMAIS
  `AddNormalAttackAbility` (xrefs : cette fonction a UN SEUL appelant de code,
  `UnitFactory$$Build`). Une Machine n'a donc structurellement aucune attaque normale, quelle que
  soit sa configuration. Le volet le CONFRONTE : `decisionView.mows[].abilities` ne doit contenir
  AUCUN `kind == "normal"`, et le contre-bras ecrit (`ActiveAbilities = [1124]` pose sur la MoW)
  ne doit RIEN y changer -- c'est ce second bras qui separe « juste par lecture du natif » de
  « juste par coincidence du kit ».

Usage :
    python scripts/python/probe_419r1tr14r5r2_active_normal_attack.py \\
        --volet all --state-file <ABSOLU>.json

ASCII only.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import catalog_inject                                              # noqa: E402
import probe_419r1tr14_heavy_bolt_pistol as P14                    # noqa: E402
import probe_419r1tr14r5_normal_attack_stages as P5                # noqa: E402
import probe_419r1tr14r5_r1r4_normal_attack_table as PT            # noqa: E402
import probe_380_seed_bc_patch_survival as P380                    # noqa: E402
from engine import weights as W                                    # noqa: E402
from engine.ai import context as _ai_ctx                           # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                        # noqa: E402

MontageError = P14.MontageError

BOARD = "MC1_67"
SEED_ACTIVE = "9191901"
SEED_MOW = "9191903"

#: L'unique entree de la table ACTIVE, transcrite du `.cctor` (cf. en-tete).
ACTIVE_KEY = "PoundThemToDust"                   # `ActiveAbilityType` 1124
ACTIVE_VALUE = "RogalDorn_NormalAttack"          # `ActiveAbilityType` 1126
GENERIC = "Loki_NormalAttack"                    # `ActiveAbilityType` 69
PASSIVE_KEY = "Boltstorm"                        # `TriggeredAbilityType` 1090
PASSIVE_VALUE = "Boltstorm_NormalAttack"         # `ActiveAbilityType` 1128

#: Volet ACTIVE -- les quatre bras. `passives=None` / `actives=None` = « laisser l'origine ».
ARMS = (
    # (visualId,        passives,        actives,       attendu,        role)
    ("astraBullgryn",   [],              [ACTIVE_KEY],  ACTIVE_VALUE,   "preuve"),
    ("necroWarden",     [],              None,          GENERIC,        "temoin"),
    ("orksNob",         [PASSIVE_KEY],   [ACTIVE_KEY],  PASSIVE_VALUE,  "borne"),
    ("eldarRanger",     [PASSIVE_KEY],   None,          PASSIVE_VALUE,  "controle"),
)
ARMS_P = ("astraBullgryn", "necroWarden")
ARMS_A = ("orksNob", "eldarRanger")

#: Volet PRED -- le MEME montage que la generalisation de #419-r1-tr14-r5 (`P5.G_*`, board `C2_02`,
#: `templAggressor` -> `astraBullgryn`), pour que les chiffres se RACCORDENT a ceux deja publies :
#: le bras `ctrl` d'ici EST le bras `strip` de la-bas (passifs vides -> attaque normale native `69`).
#: Le bras `act` n'y ajoute QUE `ActiveAbilities = [PoundThemToDust]`.
PRED_HOST = P5.G_HOST                # `templAggressor`
PRED_SEED = P5.G_SEED

#: Volet MOW -- une MoW du pool (`rl_duel build --list-pool`, rank 17).
MOW = "ultraDreadnought"


def _seed_bc(out: str, patches: dict) -> str:
    """Ecrit un seed BC ou `BC.Units[<id>]` recoit les listes demandees.

    `patches` = `{visualId: {"passives": [...] | None, "actives": [...] | None}}`, en NOMS.
    `None` = laisser la liste d'origine ; une liste (fut-elle vide) REMPLACE.

    Poser une active demande DEUX ecritures (#447) : l'id dans `BC.Units[].ActiveAbilities` ET la
    config dans `BC.Abilities.ActiveAbilities[<nom>]` -- sans la seconde, le cast rend « system
    error » (meme verrou que #226). `graft_active_ability` fait les deux ; on ne la court-circuite
    que pour le cas « liste vide », qu'elle ne sait pas exprimer.
    """
    bc = catalog_inject._load_seed(None)
    present = {u.get("Id") for u in (bc.get("Units") or ())}
    missing = sorted(set(patches) - present)
    if missing:
        raise MontageError(f"montage NON INSTALLE : {missing} absent(s) du seed BC")
    for vis, spec in patches.items():
        actives = spec.get("actives")
        if actives:
            for nm in actives:
                catalog_inject.graft_active_ability(bc, vis, nm, replace=True)
        for u in (bc.get("Units") or ()):
            if u.get("Id") != vis:
                continue
            if spec.get("passives") is not None:
                u["PassiveAbilities"] = [int(TriggeredAbilityType[n]) for n in spec["passives"]]
            if actives == []:
                u["ActiveAbilities"] = []
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(bc))
    P380.assert_survives(out)
    return out


def _mow_normal_abilities(rpc, rid: int) -> dict:
    """`{casterId: [abilities kind == "normal"]}` pour les MACHINES -- canal `decisionView.mows`,
    SEPARE de `.units` cote natif (une Machine n'est jamais dans `.units`)."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 4}, 300)
    out = {}
    for m in (dv.get("mows") or ()):
        out[m.get("casterId")] = [a for a in (m.get("abilities") or ())
                                  if a.get("kind") == "normal"]
    return out


# --------------------------------------------------------------------------- volet ACTIVE

@contextlib.contextmanager
def active_way_cut():
    """COUPE la voie ACTIVE du port -- table VIDE, c.-a-d. STRICTEMENT le port d'avant -r2. On mute
    la TABLE, jamais le code livre.

    C'est la contre-epreuve : sans elle, un vert du volet ne prouverait pas que la voie active EST
    ce qui le produit. Elle doit MORDRE sur le bras `preuve` et rester INERTE sur les trois autres
    (la reciproque : un port qui deborderait ferait bouger la borne aussi)."""
    from engine.services import custom_normal_attack as CNA
    saved = CNA.CUSTOM_NORMAL_ATTACK_BY_ACTIVE
    CNA.CUSTOM_NORMAL_ATTACK_BY_ACTIVE = {}
    try:
        yield
    finally:
        CNA.CUSTOM_NORMAL_ATTACK_BY_ACTIVE = saved


def _port_normal_attack(predictor, uid):
    """Ce que le FOYER du port repond pour cette entite, sur les canaux de PRODUCTION
    (`UnitContext.passive_abilities` / `.active_abilities`, seedes par `scene.build_predictor` via
    `_seed_measured_passives` / `_seed_measured_actives`). `None` = aucune substitution, ce qui
    correspond au `69 Loki_NormalAttack` du natif."""
    from engine.services.custom_normal_attack import custom_normal_attack
    c = (predictor.get("ctx_by_id") or {}).get(uid)
    return custom_normal_attack(passive_abilities=getattr(c, "passive_abilities", None),
                                active_abilities=getattr(c, "active_abilities", None),
                                visual_id=(predictor.get("vis_by_id") or {}).get(uid))


def run_active(rpc, build, verbose: bool = True) -> list:
    """Le natif ET le port, sur le MEME runner et les MEMES quatre bras.

    Le port n'est pas interroge sur une liste fabriquee a la main : il lit les canaux de production
    (`build_predictor` -> `_seed_measured_passives` / `_seed_measured_actives`), donc ce volet
    confronte la CHAINE ENTIERE -- capteur, parsing, seed, foyer -- au champ que la fabrique ecrit."""
    logs = os.environ.get("A35_LOGS") or _HERE
    patches = {vis: {"passives": pas, "actives": act} for vis, pas, act, _e, _r in ARMS}
    seed_bc = _seed_bc(os.path.join(logs, "tr14r5r2_active_seedbc.json"), patches)
    rid = build(SEED_ACTIVE, ["--board", BOARD, "--p-units", ",".join(ARMS_P),
                              "--a-units", ",".join(ARMS_A), "--seed-bc", seed_bc])
    got = PT.normal_attack_by_unit(rpc, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 4}, 300)
    id_by_vis = {u.get("visualId"): u.get("id") for u in (dv.get("units") or ())}
    predictor = _scene.build_predictor(rpc, rid)
    if predictor is None:
        raise MontageError("canal MUET : build_predictor a rendu None (combatSnapshot KO)")
    rows = []
    for vis, pas, act, expected, role in ARMS:
        if vis not in got:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du board")
        nat = got.get(vis)
        uid = id_by_vis.get(vis)
        port = _port_normal_attack(predictor, uid) if uid is not None else None
        with active_way_cut():
            cut = _port_normal_attack(predictor, uid) if uid is not None else None
        # `None` cote port == `Loki_NormalAttack` cote natif (aucune substitution).
        port_as_native = port or GENERIC
        cut_as_native = cut or GENERIC
        rows.append({"unit": vis, "role": role, "passives": pas, "actives": act,
                     "expected": expected, "native": None if nat is None else nat[1],
                     "native_id": None if nat is None else nat[0],
                     "port": port_as_native, "port_cut": cut_as_native,
                     "ok": (nat is not None and nat[1] == expected and port_as_native == expected),
                     "cut_bites": cut_as_native != expected})
    if verbose:
        for r in rows:
            print(f"  [{r['role']:<9}] {r['unit']:<16} passifs={str(r['passives']):<13} "
                  f"actives={str(r['actives']):<19} natif={str(r['native']):<26} "
                  f"port={r['port']:<26} attendu={r['expected']:<26} "
                  f"{'OK' if r['ok'] else 'MISMATCH'}")
        for r in rows:
            print(f"     contre-epreuve voie-active-coupee [{r['role']:<9}] -> {r['port_cut']:<26} "
                  f"{'MORD' if r['cut_bites'] else 'inerte'}")
    return rows


# --------------------------------------------------------------------------- volet CANAL

def run_canal(rpc, build, verbose: bool = True) -> list:
    """FIDELITE DU CANAL, et c'est un controle qu'il faut faire AVANT de s'en servir.

    Le natif lit `config@+0xa0` = `UnitConfiguration.ActiveAbilities`. Le port n'a pas ce champ : ce
    que le RPC `unitAbilityStates` publie est l'`ActiveAbilityComponent` (`actives[].type`), un
    SUR-ENSEMBLE -- il contient l'attaque normale que la fabrique vient de poser, et les abilities
    ajoutees par `UnitFactory$$AddDerivedAbilities`.

    Le sur-ensemble n'est SUR que si la seule cle de la table (`1124`) ne peut y entrer QUE par
    `config.ActiveAbilities`. C'est ce que ce volet mesure, sur le montage du volet `active` :

      * bras `preuve`  : `1124` DOIT etre dans `actives[].type` (sinon le canal ne voit pas ce qu'on
                         a ecrit, et tout port bati dessus serait aveugle) ;
      * bras `temoin`  : `1124` NE DOIT PAS y etre (sinon la cle arrive par une autre voie, et le
                         sur-ensemble produirait un FAUX POSITIF).

    On imprime aussi le contenu complet, parce que c'est lui qui montre le sur-ensemble a l'oeuvre.
    """
    logs = os.environ.get("A35_LOGS") or _HERE
    patches = {vis: {"passives": pas, "actives": act} for vis, pas, act, _e, _r in ARMS}
    seed_bc = _seed_bc(os.path.join(logs, "tr14r5r2_canal_seedbc.json"), patches)
    rid = build(SEED_ACTIVE, ["--board", BOARD, "--p-units", ",".join(ARMS_P),
                              "--a-units", ",".join(ARMS_A), "--seed-bc", seed_bc])
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 4}, 300)
    id_by_vis = {u.get("visualId"): u.get("id") for u in (dv.get("units") or ())}
    states = rpc("unitAbilityStates", {"runnerId": rid}, 120)
    actives_by_uid = {su.get("entityId"): [int(a.get("type")) for a in (su.get("actives") or ())]
                      for su in (states.get("units") or ())}
    key_id = int(catalog_inject.active_ability_id(ACTIVE_KEY))
    rows = []
    for vis, _pas, act, _expected, role in ARMS:
        uid = id_by_vis.get(vis)
        if uid is None or uid not in actives_by_uid:
            raise MontageError(f"canal MUET : {vis} absent de unitAbilityStates")
        got = actives_by_uid[uid]
        want = act is not None and ACTIVE_KEY in act
        rows.append({"unit": vis, "role": role, "actives_component": got,
                     "has_key": key_id in got, "want_key": want,
                     "ok": (key_id in got) == want})
    if verbose:
        for r in rows:
            print(f"  [{r['role']:<9}] {r['unit']:<16} ActiveAbilityComponent={r['actives_component']} "
                  f"contient {key_id} : {r['has_key']} (attendu {r['want_key']}) "
                  f"{'OK' if r['ok'] else 'MISMATCH'}")
    return rows


# --------------------------------------------------------------------------- volet PRED

def run_pred(sid, rpc, build, verbose: bool = True) -> dict:
    """Le MEME porteur dans deux runners qui ne different que par `ActiveAbilities`."""
    logs = os.environ.get("A35_LOGS") or _HERE
    # Les Health par `--unit-stat` (comme P5) ; les DEUX listes d'abilities par le seed BC, jamais
    # par `--unit-stat` : melanger les deux leviers ferait dependre le montage de leur ORDRE
    # d'application, et c'est exactement le piege du niveau de relique (#237).
    stats = ";".join(f"{v}:Health={P14.HP},RemainingHealth={P14.HP}"
                     for v in (P5.G_HOST, P5.G_ALLY, P5.G_TARGET, P5.G_FOE1))
    out = {}
    for arm in ("ctrl", "act"):
        patches = {PRED_HOST: {"passives": [],
                               "actives": [ACTIVE_KEY] if arm == "act" else None}}
        seed_bc = _seed_bc(os.path.join(logs, f"tr14r5r2_pred_{arm}_seedbc.json"), patches)
        rid = build(PRED_SEED, ["--board", P5.G_BOARD,
                                "--p-units", f"{P5.G_HOST},{P5.G_ALLY}",
                                "--a-units", f"{P5.G_TARGET},{P5.G_FOE1}",
                                "--unit-stat", stats, "--seed-bc", seed_bc])
        nat_ab = PT.normal_attack_by_unit(rpc, rid).get(PRED_HOST)
        case = P5.g_stage(sid, rpc, rid, None)
        P14.place(sid, case, "B")
        tile = case["layout"]["B"]
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
        mbu = {u.get("unitId"): u for u in (mov.get("units") or ())}
        ctx = _ai_ctx.build(rpc, rid, dv, mbu, case["cid"], W.load(),
                            _scene.build_predictor(rpc, rid))
        ab = P5._normal_ability(ctx)
        tgt = case["ids"]["T"]
        if tile not in [t for t in (ctx.action_tiles or ()) if t and t[0] is not None]:
            raise MontageError(f"volet pred NON MESURABLE : tuile {tile} hors des tuiles d'action")
        out[arm] = {"rid": rid, "tile": tile, "ab": ab,
                    "native_normal": None if nat_ab is None else nat_ab[1],
                    "nat": P5._native_prediction(rpc, rid, case["cid"], tgt, ab, tile),
                    "port": P5._port_prediction(ctx.scene, case["cid"], tgt, tile)}
    if verbose:
        for arm, r in out.items():
            print(f"  [{arm:<4}] attaque-normale-native={str(r['native_normal']):<26} ab={r['ab']:<5} "
                  f"tuile={r['tile']} natif={r['nat']['dmin']}..{r['nat']['dmax']} "
                  f"(hits={r['nat']['hits']}) port={r['port']['dmin']}..{r['port']['dmax']}")
        a, c = out["act"]["nat"], out["ctrl"]["nat"]
        same = (a["dmin"], a["dmax"]) == (c["dmin"], c["dmax"])
        print(f"   -> natif act vs ctrl : {'IDENTIQUES' if same else 'DIFFERENTS'} "
              f"({c['dmin']}..{c['dmax']} -> {a['dmin']}..{a['dmax']})")
    return out


# --------------------------------------------------------------------------- volet MOW

def run_mow(rpc, build, verbose: bool = True) -> list:
    """Deux bras : la MoW telle quelle, puis la MoW avec `ActiveAbilities = [1124]` ECRIT.

    Le second bras est ce qui separe « le port a raison parce que le natif ne monte jamais
    d'attaque normale sur une Machine » de « le port a raison parce que le kit de CES 8 MoW-la est
    vide » : si la voie active mordait sur une Machine, elle mordrait ici."""
    logs = os.environ.get("A35_LOGS") or _HERE
    rows = []
    for arm in ("ctrl", "active"):
        extra = ["--board", BOARD, "--p-units", ",".join(ARMS_P), "--a-units", ",".join(ARMS_A),
                 "--p-mow", MOW]
        if arm == "active":
            seed_bc = _seed_bc(os.path.join(logs, "tr14r5r2_mow_seedbc.json"),
                               {MOW: {"passives": None, "actives": [ACTIVE_KEY]}})
            extra += ["--seed-bc", seed_bc]
        rid = build(SEED_MOW, extra)
        by_caster = _mow_normal_abilities(rpc, rid)
        if not by_caster:
            raise MontageError(f"montage NON INSTALLE : aucune MoW sur le board (bras {arm})")
        for cid, nas in by_caster.items():
            rows.append({"arm": arm, "casterId": cid, "normal_abilities": nas,
                         "ok": not nas})
    if verbose:
        for r in rows:
            print(f"  [{r['arm']:<6}] mow casterId={r['casterId']} "
                  f"abilities kind=='normal' : {r['normal_abilities']} "
                  f"{'OK (aucune)' if r['ok'] else 'INATTENDU'}")
    return rows


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU (prefixe des state-files)")
    ap.add_argument("--volet", default="all",
                    choices=("all", "active", "canal", "pred", "mow"))
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    logs = os.path.dirname(os.path.abspath(args.state_file))
    os.makedirs(logs, exist_ok=True)
    os.environ["A35_LOGS"] = logs
    stem = os.path.splitext(os.path.basename(args.state_file))[0]
    seq, rids = {"n": 0}, []

    def build(seed, extra):
        seq["n"] += 1
        sf = os.path.join(logs, f"{stem}_{seq['n']}.json")
        rid = PT._build(sf, ["--seed", str(seed), *extra])
        rids.append(rid)
        return rid

    print("session", sid)
    print("table ACTIVE portee :", dict(_table()))
    rc = 0
    try:
        if args.volet in ("all", "active"):
            print("== volet ACTIVE (la table, 4 bras) ==")
            rows = run_active(rpc, build)
            bad = [r for r in rows if not r["ok"]]
            print(f"   -> {len(rows) - len(bad)}/{len(rows)} conformes")
            rc |= 1 if bad else 0
            # La contre-epreuve doit MORDRE sur `preuve` et rester INERTE ailleurs. Un vert
            # partout dirait que la voie active ne produit rien ; un rouge partout, qu'elle
            # deborde.
            want = {r["role"]: (r["role"] == "preuve") for r in rows}
            wrong = [r["role"] for r in rows if r["cut_bites"] != want[r["role"]]]
            print(f"   -> contre-epreuve : {'conforme' if not wrong else 'INATTENDUE sur ' + str(wrong)}")
            rc |= 1 if wrong else 0
        if args.volet in ("all", "canal"):
            print("== volet CANAL (unitAbilityStates.actives = SUR-ENSEMBLE de config.ActiveAbilities) ==")
            rows = run_canal(rpc, build)
            bad = [r for r in rows if not r["ok"]]
            print(f"   -> {len(rows) - len(bad)}/{len(rows)} conformes")
            rc |= 1 if bad else 0
        if args.volet in ("all", "pred"):
            print("== volet PRED (ce que la substitution change en degat) ==")
            run_pred(sid, rpc, build)
        if args.volet in ("all", "mow"):
            print("== volet MOW (une Machine n'a jamais d'attaque normale) ==")
            rows = run_mow(rpc, build)
            bad = [r for r in rows if not r["ok"]]
            print(f"   -> {len(rows) - len(bad)}/{len(rows)} conformes")
            rc |= 1 if bad else 0
    finally:
        for rid in rids:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass
    return rc


def _table() -> dict:
    """La table ACTIVE du port -- vide tant que -r2 n'est pas porte. Lue par `getattr` pour que le
    probe TOURNE avant le port (c'est lui qui etablit s'il y a quelque chose a porter)."""
    from engine.services import custom_normal_attack as CNA
    return getattr(CNA, "CUSTOM_NORMAL_ATTACK_BY_ACTIVE", {})


if __name__ == "__main__":
    raise SystemExit(main())
