"""#925 -- le FOLD primaire de `Boltstorm` emettait un `On(PreAttack = 5)` que le natif n'emet pas.

## La question binaire

*Le paquet de degat que `<X>_NormalAttackAbility$$GetCustomNormalAttackBehaviour` ajoute sur la
cible PRIMAIRE ouvre-t-il sa propre attaque -- donc pousse-t-il `StartAttack`, donc emet-il
`On(PreAttack = 5)` ?*

**NON**, et c'est LU dans
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackDamageBehaviour`,
dont la queue est UN SEUL `IdunBattleLogic.Entities.DSLBehaviors$$Attack` qui englobe les trois
volets (coups d'ARME `&` FOLD `&` `ExecuteAdditionalHitsWithDamageProfileType`). Le FOLD est une
feuille NUE (`$$GetCustomNormalAttackBehaviour` rend un `DSLBehaviors$$If(<cond>, <AttackDamage>)`,
aucun `$$Attack`) ; `StartAttack` (slot 58) n'est pousse que par
`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`, une fois pour l'`Attack(...)` englobant.

Le CLEAVE, lui, EST emballe dans son propre `Attack(...)`
(`<X>_NormalAttackAbility$$GetAdditionalTargetsAttackBehavior`) : il emet bien un `On(5)` par cible
additionnelle. Les DEUX volets partagent la feuille `$$GetAdditionalDamageBehaviour` et DIFFERENT
sur ce point -- le port les traitait pareil (defaut `is_outside_attack=True` d'
`AttackWithAttackDamage`), donc **un `On(5)` de trop par cast**, sur la cible primaire.

## Pourquoi ca ne se voyait pas, et ce qu'il a fallu ARMER

Les DEUX seuls consommateurs portes de l'event 5 sont `SuppressiveFireAddEffectAbility` (pose
`Pinned`, AUCUN tirage -- et la cible primaire l'a deja recu de l'attaque primaire, donc la seconde
pose est refusee par le gate << deja present >> d'`IdunBattle.Operations.AddEffectOperation$$Execute` :
INERTE) et `LetTheGalaxyBurnArmAbility`, dont le `Maybe(ConfigConst(0x2a))` de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger`
**CONSOMME un `state.rng`**. Le porteur naturel de `Boltstorm` (`templAggressor`) porte
`SuppressiveFire` et PAS `LetTheGalaxyBurn` : le regime NOMINAL est donc structurellement INERTE sur
cet axe -- mesure a l'appui (`probe_478 --regime boltstorm` est VERT avant comme apres le fix).

Le montage GREFFE le trait canal sur l'ENTITE (`--unit-stat Traits=[...]`, qui reecrit le seed BC,
donc mord des DEUX cotes). Un `On(5)` de trop devient alors un TIRAGE de trop, qui deplace tout le
flux -- y compris le nombre de coups d'ARME (le flag `LetTheGalaxyBurn` vaut +1 coup).

## Le VERDICT porte sur la VENTILATION PAR COUP, pas sur le total de PV -- et c'est MOTIVE

Ce montage reveille une divergence TIERCE, ANTERIEURE a cette tranche et etrangere au fold : le port
attribue le +1 coup de `LetTheGalaxyBurn` a la cible PRIMAIRE la ou le natif l'attribue a une cible
du CLEAVE. Elle se lit sans ambiguite -- le natif est COHERENT (`sum(coups natifs) == delta de PV
natif`), le port ne l'est pas (il inflige a la primaire un coup que sa propre ventilation ne
rapporte pas). Le probe la MESURE et la RAPPORTE, sans la faire porter par le verdict : residu
`#925-r1`.

Ce qui reste PROPRE et discriminant, c'est la suite des `Amount` natifs sur la cible primaire,
confrontee a `coups d'ARME + coups de FOLD` du port. Le port CORRIGE l'egale exactement ; le port
MUTANT (l'ancien comportement) n'y arrive pas -- il n'a meme pas le bon NOMBRE de coups d'arme.

## Quatre etages, et l'inertie est assertionnee DANS LES DEUX SENS

  0. MONTAGE : le trait canal est sur l'ENTITE (lu dans les traits MESURES du port, canal
     `combatSnapshot` -- pas le kit gameconfig), plus toutes les attestations de `probe_478.stage`
     (regime d'arme RANGED, fold attendu, cardinal du cleave, cible primaire ciblable). Toute
     attestation manquante LEVE.
  1. STRUCTUREL (offline pur, aucun cast de plus) : le nombre d'emissions `On(5)` du port, regime
     NATIF (`fold_emits_pre_attack() == False`) contre regime MUTANT (`True`). L'ecart DOIT valoir
     exactement 1 -- sinon le drapeau ne pilote pas ce que la RE dit qu'il pilote.
  2. LIVE : la ventilation par coup du port CORRIGE == celle du natif.
  3. CONTRE-EPREUVE : celle du port MUTANT DOIT en differer. Si elle n'y arrive pas, le canal est
     inerte et l'etage 2 ne prouve rien : le probe REFUSE au lieu de rendre un vert (meme discipline
     que `probe_419r3_fold_attack_state.py`).

## Les DEUX porteurs de fold sont confrontes, et leurs gates sont INVERSES

`--regime boltstorm` (`templAggressor`, fold gate `DSLTriggers$$IsRangedPosition`) et `--regime rr`
(`adeptMorvenn`, fold gate `<DSLTriggers+0x18>` = `IsMeleePosition`). Le foyer porte est le MEME
(`additional_targets._attack_damage_leaf`), donc jouer les deux est ce qui distingue « le fix est
juste » de « le fix est juste sur CE porteur ». Mesure : `rr` rend `2 | 3` emissions et une
ventilation native `[1076, 1073, 964, 507, 563, 526]` que le corrige egale et que le mutant rate
(`[557, 614, 572]` au lieu de `[507, 563, 526]`).

Usage :
    python scripts/python/probe_925_fold_pre_attack.py --state-file <ABSOLU>.json
        [--regime boltstorm|rr] [--board MC1_67] [--seed 4463111] [--runner N]

ASCII only. Garde jumelle : `scripts/python/tests/engine/test_925_fold_pre_attack_live.py`.
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

import probe_478_cleave_additional_targets as P478                # noqa: E402
import probe_446_r3b_fealty_talon_asymetrie as R3B                # noqa: E402
from engine.entities.pathfinding.board import Board               # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait           # noqa: E402
from engine.runner.abilities.loki import additional_targets as AT  # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent   # noqa: E402
from engine.runner.messages import AttackUnitMessage              # noqa: E402
from engine.runner.runner import Runner                           # noqa: E402
from engine.runner.snapshot import load_state                     # noqa: E402

MontageError = R3B.MontageError

CARRIER = "templAggressor"          # porteur NATUREL de `Boltstorm` (passif 1090)

#: Les DEUX porteurs de FOLD primaire, et le regime de `probe_478` qui les met en position de
#: folder. Le foyer porte est le MEME (`additional_targets._attack_damage_leaf`), mais leurs gates
#: sont INVERSES -- `Boltstorm` folde a DISTANCE (`DSLTriggers$$IsRangedPosition`),
#: `RighteousRepugnance` au CONTACT (`<DSLTriggers+0x18>` = `IsMeleePosition`). Confronter les deux
#: est ce qui distingue « le fix marche » de « le fix marche sur CE porteur ».
REGIMES = {
    "boltstorm": ("templAggressor", "boltstorm"),
    "rr": ("adeptMorvenn", "rr"),
}

#: Les traits ECRITS sur l'entite du porteur. `--unit-stat Traits=[...]` REMPLACE la liste, donc
#: ceci EST le kit effectif du montage, des deux cotes (il part dans le seed BC).
#:   * `Hero`             : conserve le statut de heros (activation, ciblage IA).
#:   * `LetTheGalaxyBurn` : LE CANAL. Son triggered 1482 ecoute `On(PreAttack = 5)` et son
#:     `Maybe(ConfigConst(0x2a))` consomme un `state.rng` A CHAQUE emission.
#: `SuppressiveFire`, `MkXGravis` et `CrushingStrike` sont RETIRES : les deux derniers sont hors
#: canal, et le premier est justement le consommateur INERTE (re-pose refusee) qui masquait le
#: signal.
TRAITS = (UnitTrait.Hero.name, UnitTrait.LetTheGalaxyBurn.name)

#: La fonction ORIGINALE, capturee AVANT toute substitution : les restaurations la reposent, plutot
#: qu'un `lambda: False` qui perdrait la docstring et le point de mutation des autres cliquets.
_FOLD_NATIF = AT.fold_emits_pre_attack


def trait_arg(porteur: str) -> list:
    """L'argument `rl_duel build` qui GREFFE le trait canal sur l'ENTITE du porteur -- foyer UNIQUE,
    partage par le probe et la garde jumelle."""
    return ["--unit-stat",
            '%s:Traits=[%s]' % (porteur, ",".join('"%s"' % t for t in TRAITS))]


def build(state_file: str, board: str, seed: str, lay: dict, porteur: str = CARRIER) -> int:
    """Meme montage que `probe_478 --regime <x>`, PLUS la greffe du trait canal sur `porteur`.

    Le seed BC est celui de `probe_446_r3b` (foyer PARTAGE : il greffe `Fealty`/`TalonOfHorus` dans
    `BC.Abilities.PassiveAbilities` -- necessaire des que le regime monte ces porteurs-la, comme
    `rr`)."""
    bc_path = os.path.splitext(state_file)[0] + ".seedbc.json"
    R3B.write_seed_bc(bc_path)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", state_file,
            *P478.build_args(lay, bc_path, board), *trait_arg(porteur)]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-900:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def _load(bundle: dict):
    """L'etat offline PRE-CAST, recharge depuis le bundle (meme MT). Un rechargement par regime :
    le replay MUTE l'etat, donc deux mesures ne peuvent pas partager une instance."""
    board = Board(bundle["bg"]["tiles"], adjacency="native_sym")
    state = load_state(bundle["dv"], bundle["ob"], bundle["snap"], board=board,
                       ability_states=bundle["ast"])
    state.rng = P478._seed_rng(bundle["rng"])
    return state


def traits_mesures(bundle: dict) -> set:
    """Les traits que le PORT lit sur l'entite du porteur -- canal `combatSnapshot`, c'est-a-dire ce
    que porte l'ENTITE NATIVE, jamais le kit gameconfig.

    C'est l'attestation que la greffe a MORDU cote natif : `--unit-stat Traits=[...]` ecrit le seed
    BC, `IdunBattle.Entities.Factories.UnitFactory` monte l'entite depuis lui, et le snapshot la
    relit. Un montage ou le trait serait reste au kit rendrait ici l'ancienne liste."""
    state = _load(bundle)
    e = state.get_entity(bundle["cid"])
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    return {str(t) for t in (getattr(ctx, "traits", None) or ())}


def rejoue(bundle: dict, fold_emet: bool) -> dict:
    """Rejoue l'attaque normale OFFLINE sous le regime demande, et rend la VENTILATION COMPLETE.

    `arme` = les coups d'ARME **plus** ceux du canal `ExecuteAdditionalHitsWithDamageProfileType`
    (`additional_hits`) : les deux appartiennent a l'attaque NORMALE et portent l'`ActiveAbilityType`
    concret cote natif. `fold` = les coups du paquet `$$GetCustomNormalAttackBehaviour`.
    `on5` = le nombre d'emissions `On(PreAttack = 5)`, compte par SUBSTITUTION du foyer
    `pre_attack_triggers` -- ses appelants l'importent DANS la fonction, donc le patch mord ; on
    appelle quand meme l'original, pour que le flux `state.rng` reste celui du regime mesure."""
    from engine.runner.operations.triggers.dispatch import attack as ATK
    state = _load(bundle)
    before = {i: (state.get_entity(i).get_component(HealthComponent).hp
                  if state.get_entity(i) is not None
                  and state.get_entity(i).get_component(HealthComponent) is not None else None)
              for i in P478._hp_by_id(bundle["dv"])}
    vrai, n = ATK.pre_attack_triggers, []

    def compteur(*a, **k):
        n.append(1)
        return vrai(*a, **k)

    AT.fold_emits_pre_attack = (lambda: True) if fold_emet else (lambda: False)
    ATK.pre_attack_triggers = compteur
    try:
        runner = Runner(state).install_default_handlers(20)
        runner.apply(AttackUnitMessage(bundle["cid"], bundle["tid"]))
    finally:
        ATK.pre_attack_triggers = vrai
        AT.fold_emits_pre_attack = _FOLD_NATIF
    rr = runner.damage_handler.last or {}
    after = {i: (state.get_entity(i).get_component(HealthComponent).hp
                 if state.get_entity(i) is not None
                 and state.get_entity(i).get_component(HealthComponent) is not None else None)
             for i in before}
    by_vis = {v: k for k, v in bundle["uid"].items()}
    d = {i: int(before[i]) - int(after[i]) for i in before
         if before.get(i) is not None and after.get(i) is not None and before[i] != after[i]}
    return {"on5": len(n),
            "primaire": d.get(bundle["tid"], 0),
            "addts": {by_vis.get(i, i): v for i, v in d.items() if i != bundle["tid"]},
            "arme": (list(rr.get("per_hit") or [])
                     + list((rr.get("additional_hits") or {}).get("per_hit") or [])),
            "fold": list(((rr.get("primary_fold") or {}).get("attack") or {}).get("per_hit") or [])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--board", default=P478.BOARD)
    ap.add_argument("--seed", default=P478.SEED)
    ap.add_argument("--runner", type=int, default=None, help="reutilise un runner deja monte")
    ap.add_argument("--regime", default="boltstorm", choices=tuple(REGIMES),
                    help="le porteur de FOLD confronte (leurs gates sont INVERSES)")
    args = ap.parse_args()
    porteur, layout = REGIMES[args.regime]

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    elev, playable = R3B.board_geometry(args.board)
    lay = P478.LAYOUTS[layout](elev, playable)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucun layout {layout} sur {args.board}")
    print(f"board {args.board} seed {args.seed} | regime {args.regime} (porteur {porteur}, "
          f"layout {layout}) + trait canal {TRAITS[-1]}")
    print(f"  T={lay['T']} A={lay['A']} porteurs={lay['C']} cardinaux={lay['want']}")

    rid = (args.runner if args.runner is not None
           else build(args.state_file, args.board, args.seed, lay, porteur))
    print(f"  runner {rid}")
    bad = []
    try:
        st = P478.stage(rpc, rid, lay, elev)
        r = P478.replay(rpc, st, porteur)
        bundle = r["bundle"]

        # --- etage 0 : la GREFFE a mordu sur l'ENTITE (sinon aucun consommateur d'`On(5)` ne tire)
        tr = traits_mesures(bundle)
        if TRAITS[-1] not in tr:
            raise MontageError(
                f"canal NON ARME : l'entite de {porteur} porte {sorted(tr)} -- {TRAITS[-1]} n'y est "
                f"pas, donc aucun consommateur d'`On(5)` ne consomme de tirage. Un accord a "
                f"l'etage 2 ne prouverait RIEN.")
        print(f"  traits MESURES sur l'entite : {sorted(tr)}")

        corr = rejoue(bundle, fold_emet=False)      # le port CORRIGE (#925) == le natif
        mut = rejoue(bundle, fold_emet=True)        # le port MUTANT == l'ancien comportement

        # --- etage 1 : STRUCTUREL
        print(f"  [etage 1] emissions On(PreAttack=5) : corrige {corr['on5']} | mutant "
              f"{mut['on5']}")
        if mut["on5"] - corr["on5"] != 1:
            bad.append(f"etage 1 : `fold_emits_pre_attack` change le nombre d'`On(5)` de "
                       f"{mut['on5'] - corr['on5']}, attendu exactement 1 (corrige {corr['on5']}, "
                       f"mutant {mut['on5']}) -- le drapeau ne pilote pas ce que la RE dit")

        # --- etage 2 : LIVE, la VENTILATION PAR COUP sur la cible primaire
        nat = list(r["nat_primaire_hits"])
        got = list(corr["arme"]) + list(corr["fold"])
        print(f"  [etage 2] NATIF   coups primaire {nat}")
        print(f"            CORRIGE arme {corr['arme']} + fold {corr['fold']}")
        if not nat:
            bad.append("etage 2 : le NATIF ne rapporte AUCUN coup sur la cible primaire -- rien "
                       "n'a eu lieu, la mesure serait vide")
        # NON-TRIVIALITE : ce montage doit exercer le FOLD, sinon `is_outside_attack` du fold n'est
        # meme pas atteint et les trois etages jugeraient une branche morte. Les coups de FOLD sont
        # ceux dont l'`Active_Ability_Type` natif est NUL (feuille `AttackDamageBehaviour` nue), par
        # opposition aux coups d'ARME qui portent l'`ActiveAbilityType` concret.
        n_fold_nat = sum(1 for k in r["nat_primaire_kinds"] if k is None)
        if not (r["want_primary_fold"] and n_fold_nat and corr["fold"]):
            bad.append(f"etage 2 : montage TRIVIAL -- fold attendu par la RE "
                       f"{r['want_primary_fold']}, coups de fold natifs {n_fold_nat}, coups de fold "
                       f"du port {corr['fold']}. Sans fold, le drapeau teste n'est pas atteint.")
        if got != nat:
            bad.append(f"etage 2 : ventilation par COUP -- port corrige {got} != natif {nat}")

        # --- etage 3 : CONTRE-EPREUVE
        mgot = list(mut["arme"]) + list(mut["fold"])
        print(f"  [etage 3] MUTANT  arme {mut['arme']} + fold {mut['fold']}")
        if mgot == nat:
            bad.append("etage 3 : le port MUTANT (un `On(5)` de trop) rend EXACTEMENT la "
                       "ventilation native -- le canal est INERTE sur ce montage, donc l'accord de "
                       "l'etage 2 ne discrimine rien. REFUSE.")
        else:
            print("  [etage 3] a_mordu = True (le mutant s'ecarte de la ventilation native)")

        # --- PV : la divergence TIERCE que ce montage revelait est FERMEE (#925-r1)
        # A l'ecriture de #925, le port rendait 4134 sur la primaire pour 3508 natifs et 1129 sur
        # `necroDestroyer` pour 1654 -- rapporte, hors verdict, comme residu `#925-r1`. Cause
        # trouvee depuis : le FOLD, feuille NUE, rejouait le canal #179
        # (`ExecuteAdditionalHitsWithDamageProfileType`), qui est un VOLET FRERE du `Attack(...)`
        # dans `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour`, jamais un enfant de la
        # feuille. Le PV est donc EXACT des deux cotes desormais, et ce cran le GARDE au lieu de
        # l'imprimer. Detail : `docs/rl/case-925r1-ltgb-coup-hors-ventilation.md`.
        s_nat = sum(int(x) for x in nat)
        print(f"  [PV] primaire natif {r['nat_primaire']} (somme des coups {s_nat}) | corrige "
              f"{corr['primaire']} (somme {sum(int(x) for x in got)})")
        print(f"       addts    natif {r['nat_addts']} | corrige {corr['addts']}")
        print(f"       MUTANT primaire {mut['primaire']} addts {mut['addts']}")
        if corr["primaire"] != r["nat_primaire"] or corr["addts"] != r["nat_addts"]:
            bad.append(f"etage 2ter (#925-r1) : PV -- port corrige primaire {corr['primaire']} "
                       f"addts {corr['addts']} != natif primaire {r['nat_primaire']} addts "
                       f"{r['nat_addts']}. Le canal #179 est rejoue par une feuille NUE, ou un "
                       f"autre coup part hors ventilation.")
        if s_nat != int(r["nat_primaire"]):
            bad.append(f"etage 2bis : le NATIF est INCOHERENT (somme des coups {s_nat} != delta de "
                       f"PV {r['nat_primaire']}) -- la ventilation ne peut pas servir de verdict")
    finally:
        AT.fold_emits_pre_attack = _FOLD_NATIF
        if args.runner is None:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass

    if bad:
        print("[925] ECHEC")
        for b in bad:
            print("   - " + b)
        return 1
    print("[925] OK -- le FOLD primaire n'emet PAS `On(PreAttack=5)` ; le port corrige egale la "
          "ventilation native coup par coup, le mutant non")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MontageError as e:
        print(f"[925] MONTAGE : {e}")
        sys.exit(2)
