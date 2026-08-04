"""#419-r1-tr14-r5-r2-r1 -- la branche TRAIT du dispatch d'attaque normale.

`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` consulte TROIS sources, dans cet
ordre : `GetCustomNormalAttackTypeFromPassive` (`config@+0xa8`, table a 14 entrees, #419-r1-tr14-r5-r1),
puis `GetCustomNormalAttackTypeFromActive` (`config@+0xa0`, table a 1 entree, #419-r1-tr14-r5-r2), puis
-- et SEULEMENT si les deux ont rendu `null` -- un test de TRAIT, lu verbatim dans le meme `if/else` :

    else if (config.Traits.Contains(0x7e7)) { type = 0x406; state = activeAbilityState; }

Les deux litteraux, QUALIFIES sur le build courant (`data/symbols/<build>/frida/enums.tsv`) :
`0x7e7` = 2023 = `Boss` dans `IdunBattle.Entities.Enum.UnitTrait` ; `0x406` = 1030 =
`Loki_NormalBossAttack` dans `IdunBattle.Entities.Enum.ActiveAbilityType`. Ni l'un ni l'autre ne
s'infere d'un nom : `UnitTrait` porte AUSSI `Guild_Boss_01` (1045), `BossAdjutant_Old` (1040) et
`MachineOfWar` (1049), et l'entier 1030 y designe `BeastSnagga`.

## Le canal, et pourquoi aucun capteur neuf

Le MEME que les deux tranches precedentes : `decisionView.units[].abilities` avec `kind == "normal"`,
c.-a-d. `ActiveAbilityComponent.NormalAttackType@0x28`, LE champ que la fabrique ecrit. Le levier de
montage est `BC.Units[].Traits` -- ecrit, deja exerce par le volet `traits` de #419-r1-tr14-r5-r4.

## LE DISCRIMINANT, ENONCE AVANT LA MESURE

Le trait `Boss` a SIX porteurs au gameconfig, **tous npc** (`adeptBossCelestineCE`,
`admecBossBelisarius`, `darkaBossLion`, `deathBossMortarion`, `tauBossRiptide`,
`tyranBossHiveTyrantLeviathan`) -- ce sont les boss de GUILDE, pas des Machines of War. Zero porteur
dans le pool : le montage est donc ECRIT, exactement comme #419-r1-tr14-r5-r4 l'a fait pour
`Erratic`/`Harmless` (eux aussi a zero porteur).

DEUX runners APPARIES, memes quatre unites, meme board, meme seed, meme roster. **Seuls les
`BC.Units[].Traits` different** :

  | unite            | `PassiveAbilities` | `ActiveAbilities`  | bras `boss` | bras `ctrl` | role |
  |------------------|--------------------|--------------------|-------------|-------------|------|
  | `astraBullgryn`  | `[]`               | (origine)          | **`1030`**  | **`69`**    | PREUVE |
  | `orksNob`        | `[1090 Boltstorm]` | (origine)          | `1128`      | `1128`      | ORDRE / passive |
  | `eldarRanger`    | `[]`               | `[1124 PoundThemToDust]` | `1126` | `1126`      | ORDRE / active |
  | `necroWarden`    | `[]`               | (origine)          | `69`        | `69`        | TEMOIN sans trait |

* La ligne PREUVE est la seule que le trait deplace. Un port qui retomberait sur l'attaque generique
  `69 Loki_NormalAttack` -- c.-a-d. le port d'avant cette tranche -- y repondrait `69` la ou le natif
  dit `1030` : c'est LE resultat qui separe les deux.
* Les deux lignes ORDRE sont le coeur du cas : le trait COEXISTE avec une source gagnante. Si la
  branche TRAIT etait portee au mauvais rang (avant la voie passive, ou avant l'active), elles
  rendraient `1030` cote port et `1128`/`1126` cote natif. Elles ne prouvent rien SEULES (les deux
  modeles y coincident quand le rang est juste) : elles BORNENT, et c'est leur role.
* Le TEMOIN ne recoit JAMAIS le trait, dans AUCUN des deux bras. Sans lui, un montage qui n'aurait
  rien installe rendrait `69` partout dans `ctrl` et se lirait comme « la branche trait ne substitue
  pas » ; avec lui, `ctrl` contient a la fois une unite qu'on a voulu voir a `69` (temoin) et une
  qu'on a voulu voir passer a `1030` dans l'autre bras (preuve).

La CONTRE-EPREUVE coupe la branche TRAIT du port (nom de trait impossible, la table n'est pas touchee)
et doit MORDRE sur la seule ligne PREUVE du bras `boss`, et rester INERTE partout ailleurs. Un vert
partout dirait que la branche ne produit rien ; un rouge ailleurs, qu'elle deborde.

Usage :
    python scripts/python/probe_419r1tr14r5r2r1_trait_normal_attack.py \\
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
import probe_419r1tr14r5_r1r4_normal_attack_table as PT            # noqa: E402
import probe_380_seed_bc_patch_survival as P380                    # noqa: E402
from engine.entities.traits.unit_trait import entity_trait_names   # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                        # noqa: E402

MontageError = P14.MontageError

BOARD = "MC1_67"
SEED_TRAIT = "9292901"

#: Les litteraux de la branche, transcrits du decompile (cf. en-tete).
TRAIT_KEY = "Boss"                               # `UnitTrait` 0x7e7 = 2023
TRAIT_VALUE = "Loki_NormalBossAttack"            # `ActiveAbilityType` 0x406 = 1030
GENERIC = "Loki_NormalAttack"                    # `ActiveAbilityType` 69
PASSIVE_KEY = "Boltstorm"                        # `TriggeredAbilityType` 1090
PASSIVE_VALUE = "Boltstorm_NormalAttack"         # `ActiveAbilityType` 1128
ACTIVE_KEY = "PoundThemToDust"                   # `ActiveAbilityType` 1124
ACTIVE_VALUE = "RogalDorn_NormalAttack"          # `ActiveAbilityType` 1126

#: Les quatre bras. `gets_trait` = l'unite recoit `Boss` DANS LE BRAS `boss` (jamais dans `ctrl`).
#: `expected` = `(attendu bras boss, attendu bras ctrl)`.
ARMS = (
    # (visualId,       passives,       actives,       gets_trait, expected,                  role)
    ("astraBullgryn",  [],             None,          True,  (TRAIT_VALUE, GENERIC),        "preuve"),
    ("orksNob",        [PASSIVE_KEY],  None,          True,  (PASSIVE_VALUE, PASSIVE_VALUE), "ordre-pas"),
    ("eldarRanger",    [],             [ACTIVE_KEY],  True,  (ACTIVE_VALUE, ACTIVE_VALUE),  "ordre-act"),
    ("necroWarden",    [],             None,          False, (GENERIC, GENERIC),            "temoin"),
)
ARMS_P = ("astraBullgryn", "orksNob")
ARMS_A = ("eldarRanger", "necroWarden")


def _seed_bc(out: str, patches: dict) -> str:
    """Ecrit un seed BC ou `BC.Units[<id>]` recoit les trois listes demandees.

    `patches` = `{visualId: {"passives": [...] | None, "actives": [...] | None,
    "traits": [...] | None}}`, en NOMS. `None` = laisser la liste d'origine ; une liste (fut-elle
    vide) REMPLACE.

    Poser une active demande DEUX ecritures (#447) : l'id dans `BC.Units[].ActiveAbilities` ET la
    config dans `BC.Abilities.ActiveAbilities[<nom>]` -- `graft_active_ability` fait les deux.

    Les TRAITS sont poses en AJOUT a la liste d'origine par l'appelant (`_traits_for`), jamais en
    remplacement : remplacer retirerait `Hero`/l'alliance et ferait varier autre chose que la seule
    variable etudiee.
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
            if spec.get("traits") is not None:
                u["Traits"] = list(spec["traits"])
            if actives == []:
                u["ActiveAbilities"] = []
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(bc))
    P380.assert_survives(out)
    return out


def _traits_for(arm: str) -> dict:
    """`{visualId: [noms]}` -- les `Traits` d'origine du seed, AUGMENTES de `Boss` pour les unites
    qui doivent le porter dans CE bras."""
    base = PT.seed_traits_of([vis for vis, *_ in ARMS])
    out = {}
    for vis, _pas, _act, gets, _exp, _role in ARMS:
        tr = list(base[vis])
        if arm == "boss" and gets and TRAIT_KEY not in tr:
            tr.append(TRAIT_KEY)
        out[vis] = tr
    return out


@contextlib.contextmanager
def trait_way_cut():
    """COUPE la branche TRAIT du port -- on pose un nom de trait qu'aucune unite ne porte, c.-a-d.
    STRICTEMENT le port d'avant -r2-r1. On mute le LITTERAL, jamais le code livre.

    C'est la contre-epreuve : sans elle, un vert du volet ne prouverait pas que la branche TRAIT est
    ce qui le produit."""
    from engine.services import custom_normal_attack as CNA
    saved = CNA.NORMAL_BOSS_ATTACK_TRAIT
    CNA.NORMAL_BOSS_ATTACK_TRAIT = "__aucun_trait_de_ce_nom__"
    try:
        yield
    finally:
        CNA.NORMAL_BOSS_ATTACK_TRAIT = saved


def _port_normal_attack(predictor, uid):
    """Ce que le FOYER du port repond pour cette entite, sur les canaux de PRODUCTION
    (`UnitContext.passive_abilities` / `.active_abilities` / `.traits`, seedes par
    `scene.build_predictor`). `None` = aucune substitution, ce qui correspond au `69
    Loki_NormalAttack` du natif."""
    from engine.services.custom_normal_attack import custom_normal_attack
    c = (predictor.get("ctx_by_id") or {}).get(uid)
    vis = (predictor.get("vis_by_id") or {}).get(uid)
    return custom_normal_attack(passive_abilities=getattr(c, "passive_abilities", None),
                                active_abilities=getattr(c, "active_abilities", None),
                                visual_id=vis,
                                traits=entity_trait_names(c, vis))


def _measured_traits(predictor, uid) -> list:
    """Les traits que le CANAL a mesures pour cette entite -- imprimes pour que le lecteur voie que
    le montage est bien arrive jusqu'au port, et pas seulement jusqu'au natif."""
    c = (predictor.get("ctx_by_id") or {}).get(uid)
    vis = (predictor.get("vis_by_id") or {}).get(uid)
    return sorted(entity_trait_names(c, vis))


# --------------------------------------------------------------------------- volet TRAIT

def run_trait(rpc, build, verbose: bool = True) -> list:
    """Les deux bras apparies. Le natif ET le port, sur les canaux de production."""
    logs = os.environ.get("A35_LOGS") or _HERE
    rows = []
    for i, arm in enumerate(("boss", "ctrl")):
        traits = _traits_for(arm)
        patches = {vis: {"passives": pas, "actives": act, "traits": traits[vis]}
                   for vis, pas, act, _g, _e, _r in ARMS}
        seed_bc = _seed_bc(os.path.join(logs, f"tr14r5r2r1_{arm}_seedbc.json"), patches)
        rid = build(SEED_TRAIT, ["--board", BOARD, "--p-units", ",".join(ARMS_P),
                                 "--a-units", ",".join(ARMS_A), "--seed-bc", seed_bc])
        got = PT.normal_attack_by_unit(rpc, rid)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 4}, 300)
        id_by_vis = {u.get("visualId"): u.get("id") for u in (dv.get("units") or ())}
        predictor = _scene.build_predictor(rpc, rid)
        if predictor is None:
            raise MontageError("canal MUET : build_predictor a rendu None (combatSnapshot KO)")
        for vis, pas, act, gets, expected, role in ARMS:
            if vis not in got:
                raise MontageError(f"montage NON INSTALLE : {vis} absent du board (bras {arm})")
            nat = got.get(vis)
            uid = id_by_vis.get(vis)
            port = _port_normal_attack(predictor, uid) if uid is not None else None
            with trait_way_cut():
                cut = _port_normal_attack(predictor, uid) if uid is not None else None
            exp = expected[i]
            # `None` cote port == `Loki_NormalAttack` cote natif (aucune substitution).
            port_as_native = port or GENERIC
            cut_as_native = cut or GENERIC
            want_trait = (arm == "boss" and gets)
            has_trait = TRAIT_KEY in _measured_traits(predictor, uid) if uid is not None else False
            rows.append({"arm": arm, "unit": vis, "role": role, "passives": pas, "actives": act,
                         "expected": exp, "native": None if nat is None else nat[1],
                         "native_id": None if nat is None else nat[0],
                         "port": port_as_native, "port_cut": cut_as_native,
                         "trait_seen": has_trait, "trait_wanted": bool(want_trait),
                         "ok": (nat is not None and nat[1] == exp and port_as_native == exp
                                and has_trait == bool(want_trait)),
                         "cut_bites": cut_as_native != exp})
    if verbose:
        for r in rows:
            print(f"  [{r['arm']:<4}][{r['role']:<9}] {r['unit']:<16} "
                  f"trait_mesure={str(r['trait_seen']):<5}(voulu {str(r['trait_wanted']):<5}) "
                  f"natif={str(r['native']):<24} port={r['port']:<24} "
                  f"attendu={r['expected']:<24} {'OK' if r['ok'] else 'MISMATCH'}")
        for r in rows:
            print(f"     contre-epreuve branche-trait-coupee [{r['arm']:<4}][{r['role']:<9}] -> "
                  f"{r['port_cut']:<24} {'MORD' if r['cut_bites'] else 'inerte'}")
    return rows


# --------------------------------------------------------------------------- volet CANAL

def run_canal(rpc, build, verbose: bool = True) -> list:
    """FIDELITE DU CANAL, avant de s'en servir.

    Le natif lit `config@+0xd0` = `UnitConfiguration.Traits`. Le port lit
    `combatSnapshot.units[].traits`, c.-a-d. l'ensemble EFFECTIF que rend
    `IdunBattle.Entities.UnitExtensions$$HasTrait` -- un SUR-ENSEMBLE de la configuration (il inclut
    les traits ACCORDES en bataille par `IdunBattle.Operations.AddTraitOperation$$AddTrait`).

    Le sur-ensemble n'est SUR, au turn 1, que si `Boss` n'y entre QUE par `BC.Units[].Traits`. Ce
    volet le mesure sur le montage du volet `trait` :

      * bras `boss`, unites `gets_trait` : `Boss` DOIT etre mesure (sinon le canal ne voit pas ce
        qu'on a ecrit, et tout port bati dessus serait aveugle) ;
      * partout ailleurs : `Boss` NE DOIT PAS y etre (sinon il arrive par une autre voie, et le
        sur-ensemble produirait un FAUX POSITIF).
    """
    logs = os.environ.get("A35_LOGS") or _HERE
    rows = []
    for arm in ("boss", "ctrl"):
        traits = _traits_for(arm)
        patches = {vis: {"passives": pas, "actives": act, "traits": traits[vis]}
                   for vis, pas, act, _g, _e, _r in ARMS}
        seed_bc = _seed_bc(os.path.join(logs, f"tr14r5r2r1_canal_{arm}_seedbc.json"), patches)
        rid = build(SEED_TRAIT, ["--board", BOARD, "--p-units", ",".join(ARMS_P),
                                 "--a-units", ",".join(ARMS_A), "--seed-bc", seed_bc])
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 4}, 300)
        id_by_vis = {u.get("visualId"): u.get("id") for u in (dv.get("units") or ())}
        predictor = _scene.build_predictor(rpc, rid)
        if predictor is None:
            raise MontageError("canal MUET : build_predictor a rendu None (combatSnapshot KO)")
        for vis, _pas, _act, gets, _exp, role in ARMS:
            uid = id_by_vis.get(vis)
            if uid is None:
                raise MontageError(f"canal MUET : {vis} absent de decisionView (bras {arm})")
            seen = _measured_traits(predictor, uid)
            want = (arm == "boss" and gets)
            rows.append({"arm": arm, "unit": vis, "role": role, "traits": seen,
                         "has_key": TRAIT_KEY in seen, "want_key": bool(want),
                         "ok": (TRAIT_KEY in seen) == bool(want)})
    if verbose:
        for r in rows:
            print(f"  [{r['arm']:<4}][{r['role']:<9}] {r['unit']:<16} traits={r['traits']} "
                  f"contient {TRAIT_KEY} : {r['has_key']} (attendu {r['want_key']}) "
                  f"{'OK' if r['ok'] else 'MISMATCH'}")
    return rows


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU (prefixe des state-files)")
    ap.add_argument("--volet", default="all", choices=("all", "trait", "canal"))
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
    print("branche TRAIT portee :", _branch())
    rc = 0
    try:
        if args.volet in ("all", "canal"):
            print("== volet CANAL (combatSnapshot.traits = SUR-ENSEMBLE de config.Traits) ==")
            rows = run_canal(rpc, build)
            bad = [r for r in rows if not r["ok"]]
            print(f"   -> {len(rows) - len(bad)}/{len(rows)} conformes")
            rc |= 1 if bad else 0
        if args.volet in ("all", "trait"):
            print("== volet TRAIT (2 bras apparies x 4 unites) ==")
            rows = run_trait(rpc, build)
            bad = [r for r in rows if not r["ok"]]
            print(f"   -> {len(rows) - len(bad)}/{len(rows)} conformes")
            rc |= 1 if bad else 0
            # La contre-epreuve doit MORDRE sur la seule ligne PREUVE du bras `boss`.
            wrong = [f"{r['arm']}/{r['role']}" for r in rows
                     if r["cut_bites"] != (r["arm"] == "boss" and r["role"] == "preuve")]
            print(f"   -> contre-epreuve : {'conforme' if not wrong else 'INATTENDUE sur ' + str(wrong)}")
            rc |= 1 if wrong else 0
    finally:
        for rid in rids:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass
    return rc


def _branch() -> str:
    """Les deux litteraux de la branche TRAIT du port -- lus par `getattr` pour que le probe TOURNE
    avant le port (c'est lui qui etablit s'il y a quelque chose a porter)."""
    from engine.services import custom_normal_attack as CNA
    return (f"{getattr(CNA, 'NORMAL_BOSS_ATTACK_TRAIT', None)} -> "
            f"{getattr(CNA, 'NORMAL_BOSS_ATTACK', None)}")


if __name__ == "__main__":
    raise SystemExit(main())
