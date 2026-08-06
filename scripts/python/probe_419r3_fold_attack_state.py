"""#419-r3 -- le FOLD primaire herite-t-il de l'`OngoingAttack` de l'attaque primaire ?

## La question, et pourquoi elle n'est pas cosmetique

`IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage` rend un `AttackDamageBehaviour` **NU**
(aucun `IdunBattle.Entities.Behaviours.AttackBehaviour`). Compose dans le `Attack(...)` d'une autre
attaque, il lit donc l'`OngoingAttack` DEJA MUTEE -- et c'est ce que dit l'octet `+0` de son
`Nullable<AttackDamageBehaviourOptions>`, `isOutsideAttack` : **15 de ses 18 call-sites le posent a
`false`** (balayage exhaustif : `docs/rl/case-419-r3-is-outside-attack-inexprimable.md`).

Le port, lui, n'avait AUCUNE feuille d'attaque nue : `IdunBattleLogic.Entities.DSLFactory$$
AttackWithAttackDamage` finit par `AttackBehaviour$$.ctor`, donc pousse un `OngoingAttack` neuf par
cible. Sur 15 des 18 sites c'est sans consequence -- leur feuille est la PREMIERE de son propre
`Attack(...)`, donc l'attaque en cours y est neuve de toute facon. Le regime ou l'ecart MORD est le
**FOLD primaire** de `Boltstorm` et `RighteousRepugnance` : `<X>_NormalAttackAbility$$
GetCustomNormalAttackBehaviour` rend `If(<cond>, <la feuille NUE>)`, et `ALoki_NormalAttackAbility$$
GetAttackDamageBehaviour` le compose ENTRE les coups d'arme et
`ExecuteAdditionalHitsWithDamageProfileType`, le tout dans UN seul `Attack(...)`.

Trois canaux transitent par l'objet rendu, et le port les modelise deja -- il les remettait
simplement a NEUF pour le fold :

    `OngoingAttack+0x30`  index de coup      -> `hit_index0`     (`CurrentHitIndexFormula`, GetStuckIn)
    `OngoingAttack+0x40`  isCriticalDamageAllowed -> `crit_allowed0`  (gate << never crit >>, 0 TIRAGE)
    `OngoingAttack+0x48`  FailedBlockIds     -> `failed_block0`  (sources de block deja echouees)

## Les trois etages, et pourquoi l'ordre les rend infalsifiables

    etage 1 -- ARMEMENT   : l'etat de l'attaque primaire A L'ENTREE du fold est-il NON NEUTRE ?
                            (canal par canal, jamais un booleen global)
    etage 2 -- CONFRONTATION : natif vs port, ventilation PAR COUP sur la cible primaire
    etage 3 -- MUTANT     : `fold_inherits_attack_state()` -> False restaure le port d'AVANT.
                            `a_mordu` = l'observable CHANGE-T-IL ? -- rapporte SEPAREMENT du verdict.

`a_mordu` est separe du verdict parce qu'un mutant INERTE ne prouve pas que le port est juste : il
prouve que CE MONTAGE ne discrimine pas. Les deux sens sont assertionnes :

  * `a_mordu` VRAI  => au moins un des trois canaux est non neutre a l'entree du fold ;
  * `a_mordu` FAUX => les TROIS sont neutres (etat = attaque neuve).

Une violation de l'un ou l'autre est un ECHEC : elle signifierait qu'un canal non modelise porte la
difference, ou qu'un canal non neutre ne se voit pas -- dans les deux cas la mesure ment.

Usage :
    python scripts/python/probe_419r3_fold_attack_state.py --state-file <ABSOLU>.json
        [--regime rr] [--board MC1_67] [--seed 4463111] [--runner N]

ASCII only. Montage, greffes et geometrie : REUTILISES tels quels de
`probe_478_cleave_additional_targets.py` (foyer unique -- ce probe n'en fabrique aucun).
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

from engine.entities.pathfinding.board import Board          # noqa: E402
from engine.runner.components import HealthComponent         # noqa: E402
from engine.runner.messages import AttackUnitMessage         # noqa: E402
from engine.runner.runner import Runner                      # noqa: E402
from engine.runner.snapshot import load_state                # noqa: E402

import probe_478_cleave_additional_targets as P              # noqa: E402
import probe_446_r3b_fealty_talon_asymetrie as R3B           # noqa: E402
from engine.runner.abilities.loki import additional_targets as AT   # noqa: E402

MontageError = P.MontageError

#: L'etat d'une `OngoingAttack` NEUVE, LU dans `IdunBattle.Core.OngoingAttack$$.ctor` :
#: `+0x30 = 0` (index de coup), `+0x40 = 1` (`isCriticalDamageAllowed`), `+0x48 = new List<int>()`.
NEUVE = {"next_hit_index": 0, "crit_allowed": True, "failed_block": frozenset()}


def _neutre(st: dict) -> dict:
    """Canal par canal : ce champ vaut-il ce que porte une `OngoingAttack` NEUVE ?

    Jamais un booleen global -- un ARME qui ne dirait pas LEQUEL des trois canaux porte la
    difference ne permettrait pas d'attribuer un ecart."""
    return {"next_hit_index": int(st.get("next_hit_index") or 0) == NEUVE["next_hit_index"],
            "crit_allowed": bool(st.get("crit_allowed", True)) == NEUVE["crit_allowed"],
            "failed_block": not set(st.get("failed_block") or ())}


def _port_run(bundle: dict, inherits: bool) -> dict:
    """Rejoue l'attaque normale OFFLINE sur le bundle PRE-CAST, avec ou sans heritage, et rend
    l'etat de l'attaque primaire + la ventilation par coup + les deltas de PV.

    La MUTATION porte sur `fold_inherits_attack_state` DANS LE MODULE QUI LE CONSOMME : le cablage
    l'importe depuis `engine.runner.abilities.loki.additional_targets`, et l'import est LOCAL a
    `DamageHandler.visit_AttackUnitMessage` -- patcher le module source est donc le seul point qui
    morde. Verifie ci-dessous (`a_mordu`), pas suppose."""
    board = Board(bundle["bg"]["tiles"], adjacency="native_sym")
    state = load_state(bundle["dv"], bundle["ob"], bundle["snap"], board=board,
                       ability_states=bundle["ast"])
    state.rng = P._seed_rng(bundle["rng"])
    before = {i: (state.get_entity(i).get_component(HealthComponent).hp
                  if state.get_entity(i) is not None
                  and state.get_entity(i).get_component(HealthComponent) is not None else None)
              for i in P._hp_by_id(bundle["dv"])}
    prev = AT.fold_inherits_attack_state
    AT.fold_inherits_attack_state = (lambda: bool(inherits))
    try:
        runner = Runner(state).install_default_handlers(20)
        runner.apply(AttackUnitMessage(bundle["cid"], bundle["tid"]))
        rr = runner.damage_handler.last or {}
    finally:
        AT.fold_inherits_attack_state = prev
    after = {i: (state.get_entity(i).get_component(HealthComponent).hp
                 if state.get_entity(i) is not None
                 and state.get_entity(i).get_component(HealthComponent) is not None else None)
             for i in before}
    d = {i: int(before[i]) - int(after[i]) for i in before
         if before.get(i) is not None and after.get(i) is not None and before[i] != after[i]}
    fold = (rr.get("primary_fold") or {}).get("attack") or {}
    return {"attack_state": dict(rr.get("attack_state") or {}),
            "arme": (list(rr.get("per_hit") or [])
                     + list((rr.get("additional_hits") or {}).get("per_hit") or [])),
            "fold": list(fold.get("per_hit") or []),
            "fold_crits": list(fold.get("crits") or []),
            "fold_rolls": list(fold.get("rolls") or []),
            "primaire": d.get(bundle["tid"], 0),
            "deltas": dict(d)}


def build(state_file: str, board: str, seed: str, lay: dict, carrier: str,
          crit: int, crit_dmg: int) -> int:
    """Le montage de `probe_478`, PLUS UN SEUL degre de liberte : la `CritChance` du porteur.

    Pourquoi il faut l'ajouter, et pourquoi c'est le SEUL ajout : la premiere passe a mesure un
    etat d'attaque ARME (`next_hit_index = 2`, `crit_allowed = False`) pour un observable qui ne
    BOUGEAIT PAS -- les trois canaux y sont algebriquement inertes. `failed_block` est vide (aucune
    source de block au montage) ; `next_hit_index` ne se lit que par `getstuckin_combat_chance`, et
    `adeptMorvenn` ne porte pas `GetStuckIn` ; et `crit_allowed` ne peut pas se voir tant que
    `crit_enabled` est faux, car `_roll_crit` sort alors sur `False` SANS tirage des DEUX cotes.

    Une `CritChance` non nulle ouvre exactement ce canal-la : le gate << never crit >>
    (`IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` : `options[+0x29] |=
    (hitGroup.isCriticalDamageAllowed == 0)`) fait sortir `ExecuteHit` sur `isCrit = 0` **sans
    appeler `RollCritical`**. Heritage ON -> 0 tirage sur le fold ; heritage OFF -> un tirage par
    coup. C'est un ecart de FLUX RNG, pas un ecart de valeur : il deplace tous les coups suivants.

    `--crit-chance 0` reproduit le montage de `probe_478` a l'identique (temoin)."""
    bc_path = os.path.splitext(state_file)[0] + ".seedbc.json"
    R3B.write_seed_bc(bc_path)                 # greffe Fealty + TalonOfHorus (foyer #446-r3b)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", state_file,
            *P.build_args(lay, bc_path, board)]
    # ⚠ La `CritChance` entre DANS la clause `--unit-stat` deja produite par `probe_478`, pas dans
    # une SECONDE occurrence du drapeau : mesure du premier passage -- un `--unit-stat
    # "<porteur>:CritChance=30"` ajoute a cote a bien mordu cote NATIF (les coups ont change) et
    # PAS cote PORT (coups strictement identiques). Une mutation qui ne bouge qu'un cote fabrique
    # une divergence de MONTAGE et la ferait lire comme un bug de port.
    if int(crit):
        i = argv.index("--unit-stat")
        parts = []
        touche = False
        for part in argv[i + 1].split(";"):
            head, _, rest = part.partition(":")
            if head == carrier:
                # ⚠ `CritDamage` AUSSI, et ce n'est pas une precaution : `CouldCrit` est une
                # CONJONCTION (`GetStat(9) > 0 && GetStat(10) > 0`). Mesure du deuxieme passage --
                # avec la seule `CritChance`, le port lisait `(cc=30, cd=0, could_crit=False)` : le
                # canal restait ferme et la mutation restait inerte.
                part = f"{head}:CritChance={int(crit)},CritDamage={int(crit_dmg)},{rest}"
                touche = True
            parts.append(part)
        if not touche:
            raise MontageError(f"{carrier} absent de la clause --unit-stat du montage 478 "
                               f"({argv[i + 1]}) -- la CritChance ne serait posee nulle part")
        argv[i + 1] = ";".join(parts)
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-900:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def _canal_crit_ouvert(bundle: dict) -> tuple:
    """`(crit_chance, crit_damage, crit_enabled)` que le PORT lit pour le porteur, sur l'etat
    OFFLINE exact de la mesure.

    GARDE DE MONTAGE, et pas un diagnostic de confort. Le gate << never crit >> est le SEUL des
    trois canaux qui soit exercable ici (`failed_block` est vide -- aucune source de block au
    montage --, et `next_hit_index` ne se lit que par `getstuckin_combat_chance`, or le porteur ne
    porte pas `GetStuckIn`). S'il est ferme cote port (`CouldCrit` faux =
    `IdunBattle.Core.Services.DamageCalculations$$CouldCrit` : `GetStat(9) > 0 && GetStat(10) > 0`),
    alors `_roll_crit` sort sur `False` SANS tirage des DEUX cotes de la mutation : l'observable ne
    peut pas bouger, et un vert ne prouverait rien. On REFUSE plutot que de rendre ce vert-la."""
    from engine.runner.components import StatsComponent
    from engine.runner.operations.damage import AttackDamageOperation
    board = Board(bundle["bg"]["tiles"], adjacency="native_sym")
    state = load_state(bundle["dv"], bundle["ob"], bundle["snap"], board=board,
                       ability_states=bundle["ast"])
    ae = state.get_entity(bundle["cid"])
    sc = ae.get_component(StatsComponent) if ae is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        raise MontageError("porteur sans UnitContext offline -- le canal crit n'est pas lisible")
    return AttackDamageOperation._crit_params(ctx, [], state, bundle["cid"], bundle["tid"],
                                              is_ranged=False, is_normal_attack=False)


def mesurer(rpc, st: dict, vis: str) -> dict:
    """Le cast LIVE (une seule fois -- il consomme le tour) + les DEUX rejeux offline."""
    r = P.replay(rpc, st, vis)
    if not r["want_primary_fold"]:
        raise MontageError(
            f"montage NON DISCRIMINANT : {vis} n'exerce PAS le fold primaire sur cette geometrie "
            f"-- l'ecart #419-r3 ne peut pas se voir (il ne porte QUE sur le fold)")
    cc, cd, ce = _canal_crit_ouvert(r["bundle"])
    if not ce:
        raise MontageError(
            f"canal CRIT FERME cote port pour {vis} (cc={cc}, cd={cd}, could_crit={ce}) : le gate "
            f"<< never crit >> ne peut pas se voir, la mutation serait INERTE des deux cotes et le "
            f"vert ne prouverait rien. Relever `--crit-chance` (et verifier que la mutation MORD "
            f"cote port, pas seulement cote natif)")
    on = _port_run(r["bundle"], inherits=True)
    off = _port_run(r["bundle"], inherits=False)
    return {"vis": vis, "nat_hits": list(r["nat_primaire_hits"]),
            "nat_kinds": list(r["nat_primaire_kinds"]), "crit_params": (cc, cd, ce),
            "nat_primaire": r["nat_primaire"], "on": on, "off": off}


def verdict(rows: list) -> list:
    """Les assertions NOMMEES. Rend la liste des echecs."""
    bad = []
    for r in rows:
        v, on, off = r["vis"], r["on"], r["off"]
        neutre = _neutre(on["attack_state"])
        arme = bool([c for c in neutre.values() if not c])
        a_mordu = (on["fold"] != off["fold"]) or (on["primaire"] != off["primaire"])

        # --- etage 1/3 : ALGEBRE, assertionnee DANS LES DEUX SENS (cf. en-tete).
        if a_mordu and all(neutre.values()):
            bad.append(f"{v} : l'observable CHANGE alors que les TROIS canaux sont NEUTRES "
                       f"({on['attack_state']}) -- la difference vient d'un canal NON MODELISE")
        if (not a_mordu) and arme:
            bad.append(f"{v} : au moins un canal est NON NEUTRE ({on['attack_state']}) et pourtant "
                       f"l'observable ne bouge pas -- le canal est ALGEBRIQUEMENT INERTE sur ce "
                       f"montage, la mesure ne prouve RIEN sur lui")

        # --- etage 2 : le port AVEC heritage doit egaler le natif, coup par coup.
        got = list(on["arme"]) + list(on["fold"])
        want = [int(x) for x in r["nat_hits"] if x is not None]
        if [int(x) for x in got] != want:
            bad.append(f"{v} : ventilation par coup PORT(heritage) {got} != NATIF {want}")

        # --- etage 3 : et le port SANS heritage doit en DIVERGER. Sans ce cran, un etage 2 vert ne
        #     distingue pas << le port est juste >> de << ce montage ne discrimine pas >>.
        got_off = [int(x) for x in (list(off["arme"]) + list(off["fold"]))]
        if arme and got_off == want:
            bad.append(f"{v} : le port SANS heritage rend AUSSI {got_off} -- le montage n'exerce "
                       f"pas le canal, l'etage 2 est un vert qui ne prouve rien")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--board", default=P.BOARD)
    ap.add_argument("--seed", default=P.SEED)
    ap.add_argument("--regime", default="rr", choices=tuple(P.LAYOUTS))
    ap.add_argument("--carrier", default="adeptMorvenn",
                    help="porteur mesure (doit avoir un fold primaire sur cette geometrie)")
    ap.add_argument("--crit-chance", type=int, default=30,
                    help="CritChance du porteur : le SEUL degre de liberte ajoute au montage de "
                         "probe_478 (cf. `build`). 0 = montage temoin, canal crit inerte.")
    ap.add_argument("--crit-damage", type=int, default=352,
                    help="CritDamage du porteur -- le SECOND conjoint de `CouldCrit` (352 = la "
                         "valeur du seed BC pour adeptMorvenn). Sans lui le canal reste ferme.")
    ap.add_argument("--runner", type=int, default=None, help="reutilise un runner deja monte")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    elev, playable = R3B.board_geometry(args.board)
    lay = P.LAYOUTS[args.regime](elev, playable)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucun layout '{args.regime}' sur {args.board}")
    if args.carrier not in lay["C"]:
        raise MontageError(f"porteur {args.carrier} absent du layout '{args.regime}' "
                           f"(porteurs : {sorted(lay['C'])})")
    print(f"board {args.board} seed {args.seed} | regime {args.regime} | porteur {args.carrier} "
          f"| CritChance {args.crit_chance}")

    rid = args.runner or build(args.state_file, args.board, args.seed, lay,
                               args.carrier, args.crit_chance, args.crit_damage)
    stg = P.stage(rpc, rid, lay, elev)
    print(f"  runner {rid}")
    rows = [mesurer(rpc, stg, args.carrier)]

    for r in rows:
        on, off = r["on"], r["off"]
        neutre = _neutre(on["attack_state"])
        print(f"  [{r['vis']}] crit params PORT (cc, cd, could_crit) = {r['crit_params']}")
        print(f"  [{r['vis']}] etat de l'attaque primaire A L'ENTREE du fold : {on['attack_state']}")
        print(f"      neutre par canal : {neutre}  -> ARME={not all(neutre.values())}")
        print(f"      NATIF coups primaire {r['nat_hits']} kinds {r['nat_kinds']}")
        print(f"      PORT  heritage ON  : arme {on['arme']} + fold {on['fold']} "
              f"(crits {on['fold_crits']}, primaire {on['primaire']})")
        print(f"      PORT  heritage OFF : arme {off['arme']} + fold {off['fold']} "
              f"(crits {off['fold_crits']}, primaire {off['primaire']})")
        print(f"      a_mordu = {(on['fold'] != off['fold']) or (on['primaire'] != off['primaire'])}")

    bad = verdict(rows)
    for b in bad:
        print(f"  [ECHEC] {b}")
    print("[419-r3] " + ("OK -- le fold herite de l'OngoingAttack, et le mutant en diverge"
                         if not bad else f"{len(bad)} ECHEC(S)"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
