"""#419-r1-tr14-r5-r2-r1-r1 -- le gate `ShouldExecute` des playbooks d'ATTAQUE NORMALE.

`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
appelle le slot de vtable **+0x328** APRES avoir somme `CalculateCustomUtility` et
`CalculateUtilityFromPredictions`, et AVANT les trois termes positionnels. `false` -> `Nullable`
VIDE : AUCUNE action n'est poussee dans le `Bucket` pour ce (tuile, cible).

Les deux corps, lus verbatim :

    // IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$ShouldExecute
    if (UnitExtensions.HasTriggeredAbility(target, 0x48)) return false;   // 0x48 = 72 = Explosive
    return attackHealUtility > Fix64(0);

    // IdunBattle.AI.Playbook.Loki.Loki_NormalBossAttackPlaybook$$ShouldExecute
    return attackHealUtility > Fix64(0);                                  // PAS de clause Explosive

`0x48` = 72 = `Explosive` dans `IdunBattle.Entities.Enum.TriggeredAbilityType` (qualifie sur
`data/symbols/<build>/frida/enums.tsv`). La lecture porte sur la **CIBLE** : 4e argument de
`ShouldExecute(this, caster, casterTile, target, attackHealUtility)`.

## Le PERIMETRE, mesure et non suppose

La cascade d'`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` distribue **16**
identites d'attaque normale (14 par la voie passive, `1126 RogalDorn_NormalAttack` par l'active,
`69 Loki_NormalAttack` en repli) plus `1030 Loki_NormalBossAttack` par la branche TRAIT. Les seize
premieres derivent toutes d'`ALoki_NormalAttackPlaybook<T>` et **aucune** ne redeclare
`ShouldExecute` -- mesure NIVEAU PAR NIVEAU (`class_get_methods` de la chaine de parents, RPC
`resolveMethodPtr`) : `depth 1` pour les seize, `depth 0` pour la seule
`Loki_NormalBossAttackPlaybook`. La table des symboles NOMMES ne suffisait pas a le conclure -- les
corps triviaux sont DEDUPLIQUES (`MortisRoundPlaybook` partage le corps que la table attribue a
`SpiritLeechPlaybook$$ShouldExecute`).

Le DEFAUT de `ComparablePlaybook<T>$$ShouldExecute` est `return true` : le slot +0x328 de
`DrachnyenPlaybook` pointe sur `b0 01 c3` (`mov al,1 ; ret`).

## LE DISCRIMINANT, ENONCE AVANT LA MESURE

Un carre 2x2 sur la **MEME** unite attaquante, la MEME cible, la MEME geometrie, le MEME seed --
deux axes independants, chacun ecrit dans `BC.Units[]` :

  * axe CIBLE   : `orksNob.PassiveAbilities` = `[Explosive]` (greffe) ou `[]` ;
  * axe CASTER  : `necroWarden.Traits` += `Boss` ou non -> attaque normale `1030` ou `69`.

  | bras        | cible Explosive | caster Boss | attaque normale | le natif attaque-t-il ? |
  |-------------|-----------------|-------------|-----------------|-------------------------|
  | `ctrl_gen`  | non             | non         | `69`            | OUI   (temoin)          |
  | `expl_gen`  | **oui**         | non         | `69`            | **NON** (la PREUVE)     |
  | `ctrl_boss` | non             | oui         | `1030`          | OUI   (temoin)          |
  | `expl_boss` | **oui**         | oui         | `1030`          | OUI   (la PREUVE boss)  |

Une seule case bascule, et c'est `expl_gen`. Un port qui ne gate RIEN attaque dans les quatre ; un
port qui gate TOUT (ou qui appliquerait le gate au boss) echoue sur `expl_boss` et sur les temoins.
Les deux temoins `ctrl_*` attestent AUSSI le montage : sans eux, un runner ou l'attaquant n'est pas
a portee rendrait « aucune attaque » partout et se lirait comme un gate qui mord.

Canal NATIF : `aiDryRunAllUnits` (= `IdunBattle.AI.Tactics.DefaultAiUnitTactic$$CalculateNextActionForUnit`,
sans commit) -- l'action proposee est un `ActiveAbilityMessage(<attaque normale>, <cible>)` ou, si le
gate a refuse et qu'il ne reste rien, un `FinishUnitTurnMessage`. Canal PORT : le playbook dispatche
par `engine.playbook.common.normal_attack_playbook(ability_id)`, interroge par
`calculate_action_utility` sur la tuile COURANTE.

Usage :
    python scripts/python/probe_419r1tr14r5r2r1r1_normal_attack_should_execute.py \\
        --volet all --state-file <ABSOLU>.json

ASCII only.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import catalog_inject                                              # noqa: E402
import probe_380_seed_bc_patch_survival as P380                    # noqa: E402
import probe_419r1tr14r5_r1r4_normal_attack_table as PT            # noqa: E402
from engine import weights as W                                    # noqa: E402
from engine.ai import context as _ai_ctx                           # noqa: E402
from engine.entities.triggered_ability_type import (                # noqa: E402
    TriggeredAbilityType, entity_triggered_ability_ids, triggered_ability_ids)
from engine.playbook import scene as _scene                        # noqa: E402
from engine.playbook.common import normal_attack_playbook          # noqa: E402

MontageError = PT.MontageError

BOARD = "MC1_67"
SEED = "9292901"
ATTACKER = "necroWarden"           # ranged r3 : arrive a portee sans dependre du spawn
TARGET = "orksNob"

#: Les litteraux, transcrits du decompile (cf. en-tete). `Explosive` n'a AUCUN porteur au seed BC
#: (verifie au montage) et sa config est absente de `BC.Abilities.PassiveAbilities` (194 entrees) --
#: `graft_passive_ability` ecrit LES DEUX cotes.
GATE_ABILITY = "Explosive"                       # `TriggeredAbilityType` 0x48 = 72
BOSS_TRAIT = "Boss"                              # `UnitTrait` 0x7e7 = 2023
GENERIC_NA = "Loki_NormalAttack"                 # `ActiveAbilityType` 69
BOSS_NA = "Loki_NormalBossAttack"                # `ActiveAbilityType` 1030

#: Les quatre bras. `(tag, cible Explosive, caster Boss, attaque normale attendue, natif attaque ?)`
ARMS = (
    ("ctrl_gen",  False, False, GENERIC_NA, True),
    ("expl_gen",  True,  False, GENERIC_NA, False),      # LA PREUVE
    ("ctrl_boss", False, True,  BOSS_NA,    True),
    ("expl_boss", True,  True,  BOSS_NA,    True),       # LA PREUVE boss (gate ABSENT)
)

#: Le chemin d'approche, rejoue A L'IDENTIQUE dans les quatre bras (l'adversaire ne joue jamais :
#: `--no-ai`). Il n'est pas une hypothese : les deux bras `ctrl_*` ATTESTENT qu'il amene bien le
#: caster a portee, et un bras ou le natif n'attaquerait pas leve `MontageError`.
APPROACH = ("3,2", "4,4", "5,6")


# --------------------------------------------------------------------------- montage

def _seed_bc(out: str, explosive: bool, boss: bool) -> str:
    """Ecrit un seed BC ou la CIBLE porte (ou non) `Explosive` et le CASTER porte (ou non) `Boss`.

    DEUX precautions, toutes deux heritees des tranches precedentes :
      * le trait est AJOUTE a la liste d'origine du caster, jamais substitue a elle (remplacer
        retirerait `Hero`/l'alliance et ferait varier autre chose que la variable etudiee) ;
      * la greffe `replace=True` VIDE `PassiveAbilities` de la cible -- on le fait donc DANS LES
        DEUX bras (`[]` cote `ctrl`), sans quoi les deux bras differeraient par plus que le seul
        `Explosive`.
    """
    base = PT.seed_traits_of([ATTACKER, TARGET])
    bc = catalog_inject._load_seed(None)
    rep = catalog_inject.graft_passive_ability(bc, TARGET, GATE_ABILITY, replace=True)
    if int(TriggeredAbilityType[GATE_ABILITY]) not in (rep.get("passiveAbilitiesAfter") or ()):
        raise MontageError(f"greffe RATEE : PassiveAbilities={rep.get('passiveAbilitiesAfter')}")
    for u in (bc.get("Units") or ()):
        if u.get("Id") == TARGET and not explosive:
            u["PassiveAbilities"] = []
        if u.get("Id") == ATTACKER:
            u["Traits"] = list(base[ATTACKER]) + ([BOSS_TRAIT] if boss else [])
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(bc))
    P380.assert_survives(out)
    return out


def _duel(*args) -> tuple:
    p = subprocess.run([sys.executable, "rl_duel.py", *args], cwd=_HERE, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def stage(rpc, build, logs: str, tag: str, explosive: bool, boss: bool) -> dict:
    """Monte UN bras : seed BC, runner, approche, puis re-mesure de tout ce dont la ligne depend."""
    sf = os.path.join(logs, f"tr14r5r2r1r1_{tag}.json")
    rid = build(sf, ["--board", BOARD, "--p-units", ATTACKER, "--a-units", TARGET,
                     "--seed-bc", _seed_bc(os.path.join(logs, f"tr14r5r2r1r1_{tag}_seedbc.json"),
                                           explosive, boss)])
    got = PT.normal_attack_by_unit(rpc, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 4}, 300)
    ids = {u.get("visualId"): u.get("id") for u in (dv.get("units") or ())}
    for key in (ATTACKER, TARGET):
        if ids.get(key) is None:
            raise MontageError(f"montage NON INSTALLE : {key} absent du board (bras {tag})")
    for to in APPROACH:
        _duel("act", "move", "--state-file", sf, "--unit", str(ids[ATTACKER]), "--to", to)
        for _ in range(4):
            if rpc("battleStatus", {"runnerId": rid}, 40).get("currentPlayer") == 3:
                break
            _duel("act", "endturn", "--state-file", sf, "--no-ai")
    return {"tag": tag, "rid": rid, "state_file": sf, "explosive": explosive, "boss": boss,
            "att": ids[ATTACKER], "tgt": ids[TARGET],
            "normal": None if got.get(ATTACKER) is None else got[ATTACKER][1],
            "normal_id": None if got.get(ATTACKER) is None else got[ATTACKER][0]}


# --------------------------------------------------------------------------- lectures

def native_attacks(rpc, case: dict) -> tuple:
    """`(le natif emet-il l'attaque normale sur la cible ?, les messages proposes)`.

    `aiDryRunAllUnits` = `CalculateNextActionForUnit` contre le MEME etat, sans appliquer. Une unite
    dont le gate a refuse l'unique cible n'a plus rien a faire -> `FinishUnitTurnMessage`."""
    dry = rpc("aiDryRunAllUnits", {"runnerId": case["rid"]}, 240)
    msgs = []
    for u in (dry.get("units") or ()):
        if u.get("unitId") != case["att"]:
            continue
        for m in (u.get("proposed") or ()):
            msgs.append((m.get("cls"), m.get("abilityType"), m.get("targetId")))
    hit = any(c == "ActiveAbilityMessage" and a == case["normal_id"] and t == case["tgt"]
              for c, a, t in msgs)
    return hit, msgs


def _ctx(rpc, case: dict):
    dv = rpc("decisionView", {"runnerId": case["rid"], "allAbilities": True, "maxRank": 32}, 240)
    mov = rpc("aiMovableTiles", {"runnerId": case["rid"]}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return _ai_ctx.build(rpc, case["rid"], dv, mbu, case["att"], W.load(),
                         _scene.build_predictor(rpc, case["rid"]))


def port_attacks(ctx, case: dict) -> bool:
    """Le PORT produit-il une action d'attaque normale sur la cible, depuis la tuile COURANTE ?

    `calculate_action_utility` rend `None` = le `Nullable` VIDE natif, c.-a-d. aucune action."""
    ab = case["normal_id"]
    pb = normal_attack_playbook(ab)
    return pb.calculate_action_utility(ctx, ctx.origin, case["tgt"], ab) is not None


@contextlib.contextmanager
def gate_cut():
    """COUPE le gate du port -- `should_execute` rend `True` quoi qu'il arrive, c.-a-d. STRICTEMENT
    le port d'avant cette tranche. On mute la METHODE, jamais le code livre.

    C'est la contre-epreuve : sans elle, un vert du volet ne prouverait pas que le gate est ce qui
    le produit (le port pourrait rendre `None` pour une tout autre raison -- pas de prediction, pas
    de cible a portee, montage mort)."""
    from engine.playbook.base import ComparablePlaybook
    from engine.playbook import common as C
    saved_g = C.NormalAttackPlaybook.should_execute
    saved_b = C.NormalBossAttackPlaybook.should_execute
    C.NormalAttackPlaybook.should_execute = ComparablePlaybook.should_execute
    C.NormalBossAttackPlaybook.should_execute = ComparablePlaybook.should_execute
    try:
        yield
    finally:
        C.NormalAttackPlaybook.should_execute = saved_g
        C.NormalBossAttackPlaybook.should_execute = saved_b


@contextlib.contextmanager
def triggered_channel_cut():
    """COUPE le canal MESURE du `TriggeredAbilityComponent` cote DECISION -- `build_predictor` ne
    seede plus rien, donc `entity_triggered_ability_ids` retombe sur le KIT gameconfig.

    C'est la contre-epreuve du SEED (`scene._seed_measured_triggered`) : sans lui, un passif GREFFE
    est monte LIVE et INVISIBLE cote port, et le gate ne peut pas mordre."""
    saved = _scene._seed_measured_triggered
    _scene._seed_measured_triggered = lambda ctx_by_id, ability_states: 0
    try:
        yield
    finally:
        _scene._seed_measured_triggered = saved


# --------------------------------------------------------------------------- volet CANAL

def run_canal(rpc, build, logs: str, verbose: bool = True) -> list:
    """FIDELITE DU CANAL, avant de s'en servir.

    Le natif lit le `TriggeredAbilityComponent` (`UnitExtensions$$HasTriggeredAbility` ->
    `TriggeredAbilityComponent$$TryGetAbility`). Le port lit `UnitContext.triggered_abilities`,
    seede depuis `unitAbilityStates`. Ce volet verifie les DEUX sens sur la cible :
      * bras `expl_*` : `72` DOIT etre mesure (sinon le port est aveugle a ce qu'on a ecrit) ;
      * bras `ctrl_*` : `72` NE DOIT PAS y etre (sinon il arrive par une autre voie -> faux positif).

    Il imprime AUSSI le kit gameconfig de chaque unite, c.-a-d. ce que le port lisait AVANT le seed
    -- le RAYON DE SOUFFLE du seed, mesure au lieu d'etre suppose."""
    rows = []
    for tag, expl, boss, _na, _hit in ARMS:
        case = stage(rpc, build, logs, f"canal_{tag}", expl, boss)
        try:
            ctx = _ctx(rpc, case)
            for who, uid in (("cible", case["tgt"]), ("caster", case["att"])):
                vis = (ctx.scene.vis_by_id or {}).get(uid)
                measured = entity_triggered_ability_ids(ctx.scene.ctx(uid), vis)
                kit = triggered_ability_ids(vis)
                has = int(TriggeredAbilityType[GATE_ABILITY]) in measured
                want = bool(expl) if who == "cible" else False
                rows.append({"arm": tag, "who": who, "unit": vis, "measured": sorted(measured),
                             "kit": sorted(kit), "has_key": has, "want_key": want,
                             "ok": has == want, "kit_differs": sorted(kit) != sorted(measured)})
        finally:
            _dispose(rpc, case["rid"])
    if verbose:
        for r in rows:
            print(f"  [{r['arm']:<10}][{r['who']:<6}] {r['unit']:<14} mesure={r['measured']} "
                  f"kit={r['kit']} contient {GATE_ABILITY} : {r['has_key']} "
                  f"(attendu {r['want_key']}) {'OK' if r['ok'] else 'MISMATCH'}")
    return rows


# --------------------------------------------------------------------------- volet GATE

def run_gate(rpc, build, logs: str, verbose: bool = True) -> list:
    """Les quatre bras : natif (`aiDryRunAllUnits`) et port (`calculate_action_utility`), plus les
    deux contre-epreuves jouees PENDANT que le bras est monte."""
    rows = []
    for tag, expl, boss, want_na, want_hit in ARMS:
        case = stage(rpc, build, logs, tag, expl, boss)
        try:
            if case["normal"] != want_na:
                raise MontageError(f"montage NON INSTALLE (bras {tag}) : attaque normale "
                                   f"{case['normal']}, attendue {want_na}")
            nat, msgs = native_attacks(rpc, case)
            ctx = _ctx(rpc, case)
            port = port_attacks(ctx, case)
            with gate_cut():
                cut = port_attacks(ctx, case)
            with triggered_channel_cut():
                ctx_nc = _ctx(rpc, case)
                nochan = port_attacks(ctx_nc, case)
            rows.append({"arm": tag, "explosive": expl, "boss": boss, "normal": case["normal"],
                         "native": nat, "port": port, "expected": want_hit, "msgs": msgs,
                         "port_gate_cut": cut, "port_no_channel": nochan,
                         "ok": nat == want_hit and port == want_hit})
        finally:
            _dispose(rpc, case["rid"])
    if verbose:
        for r in rows:
            print(f"  [{r['arm']:<10}] expl={str(r['explosive']):<5} boss={str(r['boss']):<5} "
                  f"na={r['normal']:<21} natif_attaque={str(r['native']):<5} "
                  f"port={str(r['port']):<5} attendu={str(r['expected']):<5} "
                  f"{'OK' if r['ok'] else 'MISMATCH'}   msgs={r['msgs']}")
        for r in rows:
            print(f"     contre-epreuve gate-coupe   [{r['arm']:<10}] -> port={r['port_gate_cut']} "
                  f"{'MORD' if r['port_gate_cut'] != r['port'] else 'inerte'}")
        for r in rows:
            print(f"     contre-epreuve canal-coupe  [{r['arm']:<10}] -> port={r['port_no_channel']} "
                  f"{'MORD' if r['port_no_channel'] != r['port'] else 'inerte'}")
    return rows


def _dispose(rpc, rid) -> None:
    try:
        rpc("disposeRunner", {"runnerId": rid}, 60)
    except Exception:
        pass


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU (prefixe des state-files)")
    ap.add_argument("--volet", default="all", choices=("all", "gate", "canal"))
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    logs = os.path.dirname(os.path.abspath(args.state_file))
    os.makedirs(logs, exist_ok=True)

    def build(state_file, extra):
        return PT._build(state_file, ["--seed", SEED, *extra])

    print("session", sid)
    rc = 0
    if args.volet in ("all", "canal"):
        print("== volet CANAL (TriggeredAbilityComponent mesure vs kit gameconfig) ==")
        rows = run_canal(rpc, build, logs)
        bad = [r for r in rows if not r["ok"]]
        print(f"   -> {len(rows) - len(bad)}/{len(rows)} conformes")
        rc |= 1 if bad else 0
    if args.volet in ("all", "gate"):
        print("== volet GATE (carre 2x2 : cible Explosive x caster Boss) ==")
        rows = run_gate(rpc, build, logs)
        bad = [r for r in rows if not r["ok"]]
        print(f"   -> {len(rows) - len(bad)}/{len(rows)} conformes")
        rc |= 1 if bad else 0
        # Les DEUX contre-epreuves doivent mordre sur la SEULE ligne `expl_gen`.
        for key, label in (("port_gate_cut", "gate-coupe"), ("port_no_channel", "canal-coupe")):
            wrong = [r["arm"] for r in rows if (r[key] != r["port"]) != (r["arm"] == "expl_gen")]
            print(f"   -> contre-epreuve {label} : "
                  f"{'conforme' if not wrong else 'INATTENDUE sur ' + str(wrong)}")
            rc |= 1 if wrong else 0
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
