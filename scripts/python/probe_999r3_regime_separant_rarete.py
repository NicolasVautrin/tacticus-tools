"""#999-r3 -- MONTAGE NOMME du REGIME SEPARANT de la RARETE, et sa contre-epreuve degeneree.

POURQUOI CE PROBE EXISTE. `rl_duel build` impose `targetRarity = 5` a toute unite normalisee
(`rl_collect_batch._TARGET_RARITY`) : dans le regime PAR DEFAUT du harnais, les dix unites d'une
bataille rendent `rarity = 5` et **tout gate de rarete y est uniformement VRAI**. Un port SANS
gate y est donc d'accord avec le natif partout -- un vert obtenu dans ce regime ne mesure RIEN.
C'est exactement le vice que le capteur #1039 a ete ecrit pour lever, et le reproduire dans la
validation d'un port de rarete serait le rejouer.

La SORTIE est `--unit-stat "<VisualId>:Rarity=N"`, ecrit **APRES** la normalisation (`rl_duel`
applique ces patchs sur le BC deja normalise) : la fabrique
`IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` recopie alors `config->[+0x80]`
(`UnitConfiguration.Rarity`) dans `BaseUnitComponent[+0x74]`, qui est le champ -- le SEUL -- que
lisent les trois gates natifs (`IdunBattle.Entities.UnitExtensions$$HasRarity`,
`IdunBattle.Entities.Triggers.HasRarityTrigger$$ShouldTrigger`,
`IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select`).

DEUX BRAS, exposes par la MEME fabrique :

  * `rarity=None`  -- bras DEGENERE (temoin) : aucun `--unit-stat`, donc `distinct == {5}`. Il
    n'est pas la pour conclure mais pour ETABLIR que le bras separant separe vraiment : c'est le
    couple qui vaut mesure, jamais le second seul ;
  * `rarity=<N>`   -- bras SEPARANT : le `VisualId` vise descend a `N`, les autres restent a `5`.

Le montage REFUSE de rendre un bras separant qui ne separe pas (`RuntimeError`) -- un montage qui
ne s'installe pas ECHOUE, il ne skippe pas (#268), sinon la garde qui le consomme rend un VERT
VIDE.

CE QU'IL MESURE, DES DEUX COTES DU PORT :

  * `by_entity` / `by_visual` -- l'ordinal `idun.meta.Rarity` que le CAPTEUR publie
    (`combatSnapshot.units[].rarity`), plus `rarityEnum` (nom PLEIN) et `rarityLayout` (offsets
    resolus + panne eventuelle : un `null` de PANNE ne doit pas se lire comme un `null` de mesure) ;
  * `ctx_by_entity` -- ce que le PORT en fait apres `load_state` (`UnitContext.rarity`). Comparer
    les deux est le seul controle qui montre que le canal traverse : le capteur peut emettre
    pendant que le port jette.

Discipline runner : `--state-file` ABSOLU sous `logs/` du checkout (jamais sous `data/`, qui ne
porte que des ENTREES versionnees), runner DISPOSE en sortie de `run()` sauf `keep=True`. ASCII
only (cp1252). On ne dispose JAMAIS le runner d'un autre agent.

Usage :
    python probe_999r3_regime_separant_rarete.py                     # les deux bras
    python probe_999r3_regime_separant_rarete.py --vis orksKillaKan --rarity 3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rl_duel as R  # noqa: E402

#: Board EXPLICITE (jamais le defaut implicite) : `runner.md` l'exige, et il fixe la geometrie de
#: spawn dont depend le nombre d'unites vivantes au tour 0.
BOARD = "MC1_67"
SEED = 777

#: Le `VisualId` que le bras separant fait descendre. Choisi parce qu'il est PRESENT EN DOUBLE dans
#: le roster par defaut de ce couple (board, seed) : le patch touche donc DEUX entites, ce qui
#: interdit de confondre << l'unite visee >> avec << une unite au hasard >>. Re-mesure a chaque run
#: (`separating` echoue si le VisualId est absent).
VIS_SEPARE = "orksKillaKan"
RARETE_SEPARANTE = 3            # `Rarity.Epic` -- differe de `Mythic` (5) que le harnais impose


def _unwrap(x):
    return x.get("result") if isinstance(x, dict) and "result" in x else x


def _est_machine(ent) -> bool:
    """Une MoW porte un `MachineComponent`, frere du `UnitComponent` issu du meme
    `IdunBattle.Entities.Components.BaseUnitComponent$$.ctor`. C'est LA raison pour laquelle #1039
    ne passe PAS par `readUnitConfig` (qui filtre sur la classe `UnitComponent` et rend
    `{"error": "visualId introuvable"}` pour toute Machine, `case-1039` Sec.4) : on veut donc SAVOIR
    si le roster d'un bras en contient une, pour ne pas croire couvert ce qui ne l'est pas."""
    from engine.runner.components import is_machine_of_war
    try:
        return bool(is_machine_of_war(ent))
    except Exception:
        return False


def _state_file(nom: str) -> str:
    p = Path(__file__).resolve().parents[2] / "logs" / ("probe999r3_%s.json" % nom)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def dispose(res: dict) -> None:
    """Rend le runner du bras. Idempotent, silencieux : un teardown qui leve masque le verdict."""
    rid = (res or {}).get("runnerId")
    if rid is None:
        return
    try:
        import rl_collect_batch as B
        B._rpc(B._resolve_session(), "disposeRunner", [{"runnerId": rid}], timeout=20)
    except Exception:
        pass
    res["runnerId"] = None


def run(rarity: "int | None" = RARETE_SEPARANTE, vis: str = VIS_SEPARE,
        seed: int = SEED, board: str = BOARD, state_file: "str | None" = None,
        p_mow: "str | None" = None, keep: bool = False, verbose: bool = False) -> dict:
    """Monte UN bras et rend sa mesure. `rarity=None` = bras DEGENERE (temoin, sans `--unit-stat`).

    `p_mow` ajoute une MACHINE OF WAR au roster. Ce n'est pas un ornement : `readUnitConfig` est
    AVEUGLE aux Machines (il filtre sur la classe `UnitComponent`), et c'est precisement pour ca que
    #1039 lit `GetBaseUnitComponent` -- un montage sans MoW ne mesurerait donc PAS ce que le capteur
    a de particulier.

    Leve `RuntimeError` si le build echoue, si le canal est muet, ou si un bras SEPARANT ne separe
    pas -- jamais de retour degrade qui se lirait comme une mesure."""
    nom = "degenere" if rarity is None else ("separant_%s_%d" % (vis, int(rarity)))
    if p_mow:
        nom += "_mow"
    sf = state_file or _state_file(nom)
    argv = ["build", "--seed", str(int(seed)), "--board", str(board), "--state-file", sf]
    if rarity is not None:
        argv[-2:-2] = ["--unit-stat", "%s:Rarity=%d" % (vis, int(rarity))]
    if p_mow:
        argv[-2:-2] = ["--p-mow", str(p_mow)]
    if verbose:
        print("[999-r3] build %s" % " ".join(argv))
    if R.main(argv) != 0:
        raise RuntimeError("build ECHOUE (bras=%s) : %s" % (nom, " ".join(argv)))
    rid = json.loads(Path(sf).read_text(encoding="utf-8")).get("runnerId")
    if rid is None:
        raise RuntimeError("build sans runnerId (bras=%s, state-file=%s)" % (nom, sf))

    import rl_collect_batch as B
    sid = B._resolve_session()

    def rpc(method, body, timeout=90):
        return _unwrap(B._rpc(sid, method, [body], timeout=timeout)) or {}

    res: dict = {"bras": nom, "runnerId": rid, "stateFile": sf, "board": board, "seed": int(seed),
                 "vis": vis, "rarityDemandee": rarity, "pMow": p_mow}
    try:
        cs = rpc("combatSnapshot", {"runnerId": rid}, 90)
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        rows = cs.get("units") or []
        res["rarityEnum"] = cs.get("rarityEnum")
        res["rarityTypes"] = cs.get("rarityTypes")
        res["rarityLayout"] = cs.get("rarityLayout")
        res["by_entity"] = {u.get("entityId"): u.get("rarity") for u in rows}
        res["by_visual"] = {}
        for u in rows:
            v = (u.get("unitConfig") or {}).get("visualId")
            if v is None:
                v = next((d.get("visualId") for d in (dv.get("units") or [])
                          if d.get("id") == u.get("entityId")), None)
            res["by_visual"].setdefault(v, set()).add(u.get("rarity"))
        res["by_visual"] = {k: sorted(x for x in vs if x is not None)
                            for k, vs in res["by_visual"].items()}
        # Le TEMOIN de la fabrique : `UnitConfiguration.Rarity` (+0x80), la source que
        # `InitBaseComponent` recopie. Il n'est PAS le canal (le composant fait foi) -- il sert a
        # dire, quand les deux divergent, LEQUEL des deux etages a bouge.
        res["config_by_entity"] = {u.get("entityId"): (u.get("unitConfig") or {}).get("rarity")
                                   for u in rows}
        mesurees = [r for r in res["by_entity"].values() if r is not None]
        res["distinct"] = sorted(set(mesurees))
        res["nMesurees"] = len(mesurees)
        res["nLignes"] = len(rows)
        res["separating"] = len(res["distinct"]) >= 2

        if not mesurees:
            raise RuntimeError(
                "canal MUET (bras=%s) : aucune des %d lignes de combatSnapshot ne porte de "
                "`rarity`. rarityEnum=%r rarityLayout=%r -- le capteur #1039 n'est pas arme dans "
                "cette session." % (nom, len(rows), res.get("rarityEnum"), res.get("rarityLayout")))

        # CE QUE LE PORT EN FAIT. `load_state` fait passer les lignes par
        # `UnitContext.from_snapshot` -> `entities.rarity.measured_rarity`. Sans ce volet, le probe
        # ne mesurerait que le capteur, jamais la traversee.
        from engine.runner.snapshot import load_state
        from engine.runner.components import StatsComponent
        st = load_state(dv, ob, cs)
        ctx_rar = {}
        for eid, ent in st.entities.items():
            sc = ent.get_component(StatsComponent)
            c = getattr(sc, "ctx", None) if sc is not None else None
            ctx_rar[eid] = None if c is None else (None if c.rarity is None else int(c.rarity))
        res["ctx_by_entity"] = ctx_rar
        res["ctxDistinct"] = sorted({r for r in ctx_rar.values() if r is not None})
        res["machineIds"] = sorted(eid for eid, ent in st.entities.items()
                                   if _est_machine(ent))

        # LES DEUX NOEUDS, evalues sur l'etat LIVE. Sans ce volet on ne mesurerait que la
        # TRAVERSEE d'un scalaire : le port pourrait porter la rarete et n'en rien faire. Ici la
        # sortie des noeuds est un ENSEMBLE OBSERVABLE, et le bras separant le CHANGE.
        from engine.entities.rarity import Rarity
        from engine.entities.selectors.units import UnitSet, UnitsWithRarity
        from engine.entities.triggers import HasRarity
        from engine.runner.abilities.behaviours.context import entities_from_state
        premier = next(iter(st.entities), None)
        if premier is not None:
            dsl = entities_from_state(st, int(premier))
            res["hasRarityMythicByEntity"] = {
                int(u["id"]): bool(HasRarity(UnitSet([u]), Rarity.Mythic).should_trigger(dsl))
                for u in dsl.units if u.get("id") is not None}
            res["unitsWithRarityMythic"] = sorted(
                int(u["id"]) for u in UnitsWithRarity(UnitSet(list(dsl.units)),
                                                      Rarity.Mythic).select(dsl))
            res["unitsWithRarityEpic"] = sorted(
                int(u["id"]) for u in UnitsWithRarity(UnitSet(list(dsl.units)),
                                                      Rarity.Epic).select(dsl))

        if rarity is not None and not res["separating"]:
            raise RuntimeError(
                "bras SEPARANT qui ne SEPARE PAS (vis=%s, rarity=%d) : distinct=%s sur %d lignes "
                "mesurees. Soit le VisualId est absent du roster de (%s, seed=%d), soit "
                "`--unit-stat` n'atteint plus `UnitConfiguration.Rarity`. Rien n'est conclu."
                % (vis, int(rarity), res["distinct"], len(mesurees), board, int(seed)))
        if rarity is None and res["separating"]:
            raise RuntimeError(
                "bras DEGENERE qui SEPARE (distinct=%s) : la premisse `targetRarity = 5` du "
                "harnais ne tient plus. Le couple de bras ne prouve alors plus rien -- re-mesurer "
                "avant de s'en servir." % (res["distinct"],))
        if verbose:
            print("[999-r3] bras=%s  rarityEnum=%s" % (nom, res.get("rarityEnum")))
            print("[999-r3]   capteur : distinct=%s  (%d/%d lignes mesurees)"
                  % (res["distinct"], res["nMesurees"], res["nLignes"]))
            print("[999-r3]   port    : distinct=%s" % (res["ctxDistinct"],))
            for v, vs in sorted(res["by_visual"].items(), key=lambda kv: str(kv[0])):
                print("[999-r3]   %-24s %s" % (v, vs))
    finally:
        if not keep:
            dispose(res)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="#999-r3 -- regime SEPARANT de la rarete")
    ap.add_argument("--vis", default=VIS_SEPARE)
    ap.add_argument("--rarity", type=int, default=RARETE_SEPARANTE)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--bras", choices=["degenere", "separant", "les-deux"], default="les-deux")
    ap.add_argument("--p-mow", default=None,
                    help="ajoute une MoW au roster (le capteur #1039 les sert, `readUnitConfig` "
                         "non -- cf. case-1039 Sec.4)")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    rc = 0
    if a.bras in ("degenere", "les-deux"):
        print("=== BRAS DEGENERE (temoin : ce que le harnais donne SANS montage) ===")
        try:
            run(rarity=None, seed=a.seed, board=a.board, p_mow=a.p_mow, keep=a.keep, verbose=True)
        except RuntimeError as exc:
            print("  ECHEC : %s" % exc)
            rc = 2
    if a.bras in ("separant", "les-deux"):
        print()
        print("=== BRAS SEPARANT (%s -> Rarity=%d) ===" % (a.vis, a.rarity))
        try:
            r = run(rarity=a.rarity, vis=a.vis, seed=a.seed, board=a.board, p_mow=a.p_mow,
                    keep=a.keep, verbose=True)
            print()
            print("VERDICT : capteur %s ; port %s ; concordance capteur/port = %s"
                  % (r["distinct"], r["ctxDistinct"], r["distinct"] == r["ctxDistinct"]))
            print("  MoW du roster : %s" % (r.get("machineIds") or "aucune"))
            print("  UnitsWithRarity(Mythic) = %s" % (r.get("unitsWithRarityMythic"),))
            print("  UnitsWithRarity(Epic)   = %s" % (r.get("unitsWithRarityEpic"),))
        except RuntimeError as exc:
            print("  ECHEC : %s" % exc)
            rc = 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
