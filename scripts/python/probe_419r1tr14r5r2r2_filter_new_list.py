"""#419-r1-tr14-r5-r2-r2 -- la garde `FilterNewList` du REPLI GENERIQUE de l'attaque normale.

Dernier etage de `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`, apres PASSIVE
(-r1), ACTIVE (-r2) et TRAIT (-r2-r1). Lu verbatim, le `else` final :

    var list = ListExtensions.FilterNewList(comp@+0x20, <Func statique mis en cache>);
    if (0 < list.Count) return;                  // <-- LA GARDE : rien n'est ajoute
    type  = this@+0x20;                          // le generique, parametre du ctor du factory
    state = new AbilityState(new Level(1, 0), config@+0x74);

CE QUE LA RE A ETABLI, ET QUI N'AVAIT PAS ETE LU (le predicat) :

  * `UnitFactory.u003Cu003Ec$$u003CAddNormalAttackAbilityu003Eb__10_0` =
    `a => StaticBattleRules.ActiveAbility.IsRegularAttack(a@+0x44)`. `a@+0x44` est
    l'`ActiveAbilityType` de l'entree, ecrit par `ActiveAbilityComponent$$Add`.
  * `comp@+0x20` = la `KeyedCollection` de l'`ActiveAbilityComponent` de l'entite.
  * `ListExtensions$$FilterNewList` GARDE ce qui rend vrai (copie + `FilterInPlace`, qui
    `RemoveAt` en boucle DESCENDANTE quand le predicat est faux) -- c'est un `Where`, pas un
    `RemoveAll`.
  * `IsRegularAttack` = `Contains` sur l'`OrderedSet` statique `StaticBattleRules.ActiveAbility`
    @+0x18 : les 18 attaques normales, deja portees en `REGULAR_ATTACK_ABILITY_TYPES`.

La garde se lit donc : « si l'entite tient DEJA une attaque reguliere, ne lui superpose pas la
generique ». Elle est NON VIDE parce que `UnitFactory$$Build` appelle
`UnitFactory$$AddConfiguredAbilities` AVANT `AddNormalAttackAbility`, et que
`UnitFactory$$AddActiveAbility` y monte INCONDITIONNELLEMENT chaque `config.ActiveAbilities`
(= `BC.Units[].ActiveAbilities`) dans ce meme composant.

## LE DISCRIMINANT, ENONCE AVANT LA MESURE

Le seul levier est `BC.Units[].ActiveAbilities` -- ECRIT, comme en -r2 et -r2-r1. Quatre unites,
UN seul build, chacune sa configuration ; la variable etudiee est la NATURE (reguliere ou non) de
l'active montee :

  | role           | actives                       | passives     | attendu natif                |
  |----------------|-------------------------------|--------------|------------------------------|
  | preuve         | [TemplarInitiateNormalAttack] | []           | TemplarInitiateNormalAttack  |
  | temoin-nonreg  | [UnstoppableMomentumReworked] | []           | Loki_NormalAttack            |
  | temoin-origine | (origine)                     | []           | Loki_NormalAttack            |
  | ordre-pas      | [TemplarInitiateNormalAttack] | [Boltstorm]  | Boltstorm_NormalAttack       |

* `preuve` est LA ligne qui separe les deux modeles. Un moteur SANS la garde repliera sur le
  generique et rendra `Loki_NormalAttack` ; le natif, garde comprise, doit rendre l'active montee.
* `temoin-nonreg` et `temoin-origine` BORNENT : la garde ne doit pas mordre sur une active
  ordinaire, sinon toute unite perdrait son attaque normale.
* `ordre-pas` borne le RANG : la garde vit dans le `else` du `else` du `else`, donc une voie de
  rang superieur gagne meme quand une reguliere est montee.

`TemplarInitiateNormalAttack` (1046) est choisie parce qu'elle est reguliere SANS etre la valeur
d'aucune voie exercee ici : elle n'est cle d'aucune des deux tables `GetCustomNormalAttack`, et son
antecedent passif (`HeavyBoltPistol`) n'est monte dans aucun bras.

## LE MONTAGE : ECRITURE DIRECTE DE L'ID, ET POURQUOI

`catalog_inject.graft_active_ability` est INUTILISABLE ici : il synthetise une config d'ability, et
AUCUNE des 18 n'a d'entree `units.abilities` au gameconfig (mesure : 0/18) ni dans
`BC.Abilities.ActiveAbilities` du seed (0/131). C'est structurel -- une attaque normale n'est pas
une ability de catalogue, le natif la resout PAR TYPE. On ecrit donc l'id directement dans
`BC.Units[].ActiveAbilities`, ce qui est exactement ce que la fabrique consomme.

## CE QUE LE VOLET `canal` TRANCHE

`UnitContext.active_abilities` est documente comme un SUR-ENSEMBLE ASSUME (cf.
`snapshot.active_ability_names_by_unit`) : il lit l'`ActiveAbilityComponent` APRES la fabrique,
donc il porterait AUSSI l'attaque normale qu'elle vient d'y ecrire. Si c'est exact, la garde n'est
PAS portable sur ce canal -- un predicat `IsRegularAttack` y trouverait toujours quelque chose et
le repli generique ne s'appliquerait JAMAIS. Le volet le MESURE au lieu de le supposer.

Usage :
    python scripts/python/probe_419r1tr14r5r2r2_filter_new_list.py --state-file <ABSOLU>.json

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
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.entities.traits.unit_trait import entity_trait_names   # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                        # noqa: E402
from engine.runner.abilities.attack_type import REGULAR_ATTACK_ABILITY_TYPES  # noqa: E402

MontageError = P14.MontageError

BOARD = "MC1_67"
SEED = "9292901"

GENERIC = "Loki_NormalAttack"                    # `ActiveAbilityType` 69
REGULAR_GRAFT = "TemplarInitiateNormalAttack"    # `ActiveAbilityType` 1046, REGULIERE
NON_REGULAR = "UnstoppableMomentumReworked"      # `ActiveAbilityType` 1152, NON reguliere
PASSIVE_KEY = "Boltstorm"                        # `TriggeredAbilityType` 1090
PASSIVE_VALUE = "Boltstorm_NormalAttack"         # `ActiveAbilityType` 1128

#: (visualId, actives|None, passives|None, attendu natif, role)
ARMS = (
    ("astraBullgryn", [REGULAR_GRAFT], [],           REGULAR_GRAFT, "preuve"),
    ("orksNob",       [NON_REGULAR],   [],           GENERIC,       "temoin-nonreg"),
    ("eldarRanger",   None,            [],           GENERIC,       "temoin-origine"),
    ("necroWarden",   [REGULAR_GRAFT], [PASSIVE_KEY], PASSIVE_VALUE, "ordre-pas"),
)

ARMS_P = ("astraBullgryn", "orksNob")
ARMS_A = ("eldarRanger", "necroWarden")


def _seed_bc(out: str, patches: dict) -> str:
    """Seed BC ou `BC.Units[<id>]` recoit les listes demandees, en NOMS.

    ECRITURE DIRECTE de l'`ActiveAbilityType` (pas `graft_active_ability`) : aucune des 18
    attaques regulieres n'a de config d'ability derivable, et la fabrique n'en lit aucune pour
    monter l'entree (`AddActiveAbility` -> `ActiveAbilityComponent$$Add` ne consulte que le TYPE).
    """
    bc = catalog_inject._load_seed(None)
    present = {u.get("Id") for u in (bc.get("Units") or ())}
    missing = sorted(set(patches) - present)
    if missing:
        raise MontageError(f"montage NON INSTALLE : {missing} absent(s) du seed BC")
    for vis, spec in patches.items():
        for u in (bc.get("Units") or ()):
            if u.get("Id") != vis:
                continue
            if spec.get("actives") is not None:
                u["ActiveAbilities"] = [int(ActiveAbilityType[n]) for n in spec["actives"]]
            if spec.get("passives") is not None:
                u["PassiveAbilities"] = [int(TriggeredAbilityType[n]) for n in spec["passives"]]
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(bc))
    P380.assert_survives(out)
    return out


@contextlib.contextmanager
def guard_cut():
    """COUPE la garde du port -- `normal_attack_already_present` rendue muette, c.-a-d.
    STRICTEMENT le port d'avant -r2-r2 (le repli generique s'appliquait toujours). On neutralise le
    FOYER, jamais le code livre.

    Sans cette contre-epreuve, un vert du volet ne prouverait pas que c'est la garde qui le
    produit."""
    from engine.services import custom_normal_attack as CNA
    saved = CNA.normal_attack_already_present
    CNA.normal_attack_already_present = lambda _actives: None
    try:
        yield
    finally:
        CNA.normal_attack_already_present = saved


def _ctx(predictor, uid):
    return (predictor.get("ctx_by_id") or {}).get(uid)


def _port_normal_attack(predictor, uid):
    """Ce que le FOYER du port repond, sur les canaux de PRODUCTION. `None` = aucune
    substitution, ce qui correspond au `69 Loki_NormalAttack` du natif."""
    from engine.services.custom_normal_attack import custom_normal_attack
    c = _ctx(predictor, uid)
    vis = (predictor.get("vis_by_id") or {}).get(uid)
    return custom_normal_attack(passive_abilities=getattr(c, "passive_abilities", None),
                                active_abilities=getattr(c, "active_abilities", None),
                                visual_id=vis,
                                traits=entity_trait_names(c, vis))


def _measured_actives(predictor, uid) -> list:
    """`UnitContext.active_abilities` tel que le canal le MESURE (noms d'`ActiveAbilityType`)."""
    c = _ctx(predictor, uid)
    got = getattr(c, "active_abilities", None)
    return list(got) if got is not None else []


def run(rpc, build, verbose: bool = True) -> list:
    """UN build, quatre unites. Natif, port, et le CONTENU du canal."""
    logs = os.environ.get("A35_LOGS") or _HERE
    patches = {vis: {"actives": act, "passives": pas} for vis, act, pas, _e, _r in ARMS}
    seed_bc = _seed_bc(os.path.join(logs, "tr14r5r2r2_seedbc.json"), patches)
    rid = build(SEED, ["--board", BOARD, "--p-units", ",".join(ARMS_P),
                       "--a-units", ",".join(ARMS_A), "--seed-bc", seed_bc])
    got = PT.normal_attack_by_unit(rpc, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 4}, 300)
    id_by_vis = {u.get("visualId"): u.get("id") for u in (dv.get("units") or ())}
    predictor = _scene.build_predictor(rpc, rid)
    if predictor is None:
        raise MontageError("canal MUET : build_predictor a rendu None (combatSnapshot KO)")
    rows = []
    for vis, act, pas, expected, role in ARMS:
        if vis not in got:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du board")
        nat = got.get(vis)
        uid = id_by_vis.get(vis)
        port = _port_normal_attack(predictor, uid) if uid is not None else None
        with guard_cut():
            cut = _port_normal_attack(predictor, uid) if uid is not None else None
        seen = _measured_actives(predictor, uid) if uid is not None else []
        seen_reg = [n for n in seen
                    if int(ActiveAbilityType[n]) in REGULAR_ATTACK_ABILITY_TYPES]
        # `None` cote port == `Loki_NormalAttack` cote natif (aucune substitution).
        port_as_native, cut_as_native = port or GENERIC, cut or GENERIC
        rows.append({"unit": vis, "role": role, "actives": act, "passives": pas,
                     "expected": expected,
                     "native": None if nat is None else nat[1],
                     "native_id": None if nat is None else nat[0],
                     "port": port_as_native, "port_cut": cut_as_native,
                     "canal_actives": seen, "canal_regulars": seen_reg,
                     "ok": (nat is not None and nat[1] == expected
                            and port_as_native == expected),
                     "cut_bites": cut_as_native != expected})
    if verbose:
        for r in rows:
            print(f"  [{r['role']:<14}] {r['unit']:<16} natif={str(r['native']):<30} "
                  f"attendu={r['expected']:<30} port={r['port']:<30} "
                  f"{'OK' if r['ok'] else 'MISMATCH'}")
        for r in rows:
            print(f"     contre-epreuve garde-coupee [{r['role']:<14}] -> {r['port_cut']:<30} "
                  f"{'MORD' if r['cut_bites'] else 'inerte'}")
        print("  -- canal `UnitContext.active_abilities` (sur-ensemble ?) --")
        for r in rows:
            print(f"     [{r['role']:<14}] {r['unit']:<16} actives={r['canal_actives']} "
                  f"dont REGULIERES={r['canal_regulars']}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU (prefixe des state-files)")
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
    rc = 0
    try:
        print("== garde FilterNewList : 4 unites, 1 build ==")
        rows = run(rpc, build)
        bad = [r for r in rows if not r["ok"]]
        print(f"   -> {len(rows) - len(bad)}/{len(rows)} conformes (natif ET port)")
        rc |= 1 if bad else 0
        wrong = [r["role"] for r in rows if r["cut_bites"] != (r["role"] == "preuve")]
        print(f"   -> contre-epreuve : "
              f"{'conforme' if not wrong else 'INATTENDUE sur ' + str(wrong)}")
        rc |= 1 if wrong else 0
    finally:
        for rid in rids:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
