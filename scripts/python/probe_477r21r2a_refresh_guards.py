#!/usr/bin/env python3
"""#477-r21-r2 volet A -- les quatre gardes de `RefreshEffectsOperation`, confrontees.

    python probe_477r21r2a_refresh_guards.py [--session N] [--boards C1_02,MC1_67] [--tours 2]

CE QU'IL MESURE, ET CE QU'IL NE PEUT PAS MESURER
------------------------------------------------
Les quatre gardes DECIDENT ; elles n'ecrivent aucune ligne. On ne peut donc pas les confronter
comme une face stream (#477-r18..r22), en comparant deux textes. Ce probe confronte ce que le
decompile IMPOSE au flux -- des invariants DERIVES de la structure des gardes, refutables par un
seul contre-exemple, et qui n'exigent AUCUNE entree copiee du flux :

  (I1) `Action=ActivateEffect` present dans un `Group=Effect_Refresh`
       =>  0 `Action=LoseEffect`  ET  au moins 1 `Action=ReceiveEffect`.
       Derive de `UpdateEffectTargets` : la lambda `b__0` n'est ajoutee que sous
       `currentTargets.Count == 0 && desiredTargets.Count > 0`, et `currentTargets` vide force
       `targetsToRemove` vide (`GetTargetsToRemove` itere `currentTargets`) et
       `targetsToAdd == desiredTargets` (`GetTargetsToAdd` ne peut rien exclure).

  (I2) `Action=DeactivateEffect` present
       =>  0 `Action=ReceiveEffect`  ET  au moins 1 `Action=LoseEffect`.
       Symetrique, via `b__1` sous `currentTargets.Count > 0 && desiredTargets.Count == 0`.

  (I3) Les deux ne coexistent JAMAIS (`currentTargets.Count` ne peut pas etre a la fois nul et
       strictement positif).

  (I4) Les ids des `Action=LoseEffect` d'un meme groupe sont STRICTEMENT CROISSANTS.
       Derive d'`IdunBattle.Entities.Components.EffectComponent$$AddTargetId`, qui fait
       `Targets.Add(id); Targets.Sort();` -- donc `GetCurrentEffectTargets` parcourt une liste
       triee, donc `GetTargetsToRemove` rend ses cibles en ids croissants.

  (I5) Les ids des `Action=ReceiveEffect` NE SONT PAS contraints a croitre : ils suivent l'ordre
       du SELECTEUR (`GetDesiredEffectTargets`), que `GetTargetsToAdd` parcourt tel quel.
       ⚠ CETTE LIGNE NE SE COMPTE VERTE QUE SI LE FLUX LA DISCRIMINE. Un flux ou tous les
       `ReceiveEffect` seraient croissants rendrait (I4) et (I5) indiscernables, et le probe
       l'ecrit alors NON DISCRIMINE au lieu de vert.

  (I6) L'ORDRE d'assemblage : `[Activate] Lose* Receive* [Deactivate]`. Le port RE-DERIVE la
       sequence des `Action=` de chaque groupe a partir des seuls ensembles observes, par un
       appel reel a `update_effect_targets`, et elle doit egaler la sequence observee.
       ⚠ `Deactivate` APRES les cibles est le point contre-intuitif : un assembleur naif le met
       en tete. C'est ce que mesure la contre-epreuve `plan_desactivation_en_tete`.

⚠ `ShouldBeActive` N'EST PAS CONFRONTABLE PAR CE CANAL, ET C'EST DIT PLUTOT QUE CONTOURNE. Le flux
porte les CONSEQUENCES d'un verdict deja rendu, jamais le verdict ; et la donnee qui le produit
(`CreateActiveCondition`, `GetRefreshTriggers`) n'est pas dans le flux. Son cablage dans
`refresh_stat_modifier_effects` est confronte AILLEURS, par non-regression des tests live du
driver -- pas ici.

BORNE (c) -- CE QUI EST COPIE DU FLUX. Pour (I6) seulement : la PRESENCE d'`Activate`/`Deactivate`
sert a choisir la reconstruction de `(currentTargets, desiredTargets)` (le sous-ensemble
INCHANGE, `kept`, n'est pas observable). (I1)..(I3) ne copient rien : ce sont des implications a
sens unique sur les seuls comptes observes.

DISCIPLINE : un runner a la fois, dispose dans le `finally`, state-files sous `logs/`.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe_477r15a_stream_conformance as R15A  # noqa: E402
import probe_477r19_process_removals as R19  # noqa: E402
import probe_477r20_start_match as R20  # noqa: E402
import probe_477r21_activation_tree as R21  # noqa: E402
from engine.runner.operations import refresh_effects as RE  # noqa: E402
from engine.streams import GroupType, StepType  # noqa: E402
from engine.streams import conformance as CONF  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "logs"

MesureImpossible = R15A.MesureImpossible
BOARDS_DEFAUT = ("C1_02", "MC1_67")

#: Les quatre formes d'action que les gardes produisent. Tout le reste d'un `Effect_Refresh`
#: (`ChangeStats`, `ChangeAbility`) sort d'`Effect.ApplyModification` -- #477-r21-r1 -- et n'est
#: PAS filtre ici : un sous-arbre qui en porte reste MESURE sur ses quatre formes.
ACT = StepType.ActivateEffect.name
DEACT = StepType.DeactivateEffect.name
LOSE = StepType.LoseEffect.name
RECV = StepType.ReceiveEffect.name


# --------------------------------------------------------------------------- capture et lecture
def capturer(session: int, board: str, tours: int, p_units: str, a_units: str) -> str:
    """Monte un runner, joue `tours` tours d'IA, rend le flux de replay ENTIER."""
    state = OUT / ("state-477r21r2a-%s.json" % board)
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = R19.build(board, state, p_units, a_units)
    try:
        for _ in range(tours):
            q = subprocess.run([sys.executable, "rl_duel.py", "aiturn",
                                "--state-file", str(state)],
                               cwd=str(HERE), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900)
            if q.returncode != 0:
                break
        flux = (R15A.rpc(session, "replayOutputStream",
                         {"runnerId": rid, "maxChars": 8000000}).get("outputStream") or "")
    finally:
        R15A.dispose(state)
    if not flux:
        raise MesureImpossible("`replayOutputStream` rend un flux VIDE")
    return flux


def sous_arbres(flux: str) -> Tuple[list, int]:
    """TOUS les `Group=Effect_Refresh` du flux, a TOUTE profondeur.

    ⚠ On ne se restreint PAS au bloc 1 de `System_StartMatch` (le perimetre de #477-r21) : les
    gardes tournent a chaque `RefreshEffects`, donc chaque tour d'IA en produit. Un probe qui ne
    lirait que le demarrage se priverait de la majorite du corpus -- et c'est exactement le
    regime ou (I2) a une chance d'etre exercee, une desactivation supposant un etat anterieur.

    Rend `(liste d'EffectRefreshObs, nombre de sous-arbres illisibles)`. Un sous-arbre illisible
    (groupe imbrique inattendu) est COMPTE, jamais tu."""
    lignes = [l for l in flux.split("\n") if l != ""]
    out, illisibles, i = [], 0, 0
    while i < len(lignes):
        m = CONF.RE_GROUP.match(lignes[i])
        if m and m.group("sym") == GroupType.Effect_Refresh.name:
            try:
                fin = R21._bloc(lignes, i)
            except MesureImpossible:
                illisibles += 1
                i += 1
                continue
            try:
                out.append(R21._lire_sous_arbre(lignes[i:fin + 1]))
            except MesureImpossible:
                illisibles += 1
            i = fin + 1
            continue
        i += 1
    return out, illisibles


def _ids(obs, step: str) -> List[int]:
    return [a.entity for a in obs.actions if a.step == step]


def _sequence(obs) -> List[tuple]:
    """La sequence des QUATRE formes portees, dans l'ordre du flux, avec l'entite PORTEE.

    ⚠ L'ENTITE N'EST COMPAREE QUE SUR `Lose` / `Receive`, ET C'EST LA LIGNE DE PARTAGE ENTRE CE
    QUI EST DERIVE ET CE QUI EST COPIE. Celles-la sortent des cibles, donc de
    `GetTargetsToRemove` / `GetTargetsToAdd` : le port les DERIVE de `(current, desired)`, ordre
    compris. Celle d'`Activate` / `Deactivate` est l'`owner` -- une entree que rien dans les
    gardes ne calcule (mesure #477-r21 : un groupe d'entite 82 porte un `ActivateEffect` sur 51).
    La comparer serait circulaire ; on la met a `None` des deux cotes.

    ⚠ UNE PREMIERE VERSION NE COMPARAIT QUE LES NOMS D'ACTION, ET C'EST LE COMPTE
    `applicable sur N` QUI L'A TROUVEE : `cibles_courantes_inversees` avait 8 cas applicables et
    ne changeait RIEN, parce qu'inverser l'ordre des cibles ne change aucun nom d'action. Sans ce
    compte, le `a_morde=false` se serait lu comme « le corpus ne l'exerce pas »."""
    return [(a.step, a.entity if a.step in (LOSE, RECV) else None)
            for a in obs.actions if a.step in (ACT, DEACT, LOSE, RECV)]


# ------------------------------------------------------------------------------- les invariants
def _croissant(ids: List[int]) -> bool:
    return all(ids[k] < ids[k + 1] for k in range(len(ids) - 1))


def invariants(arbres: list) -> dict:
    """(I1)..(I5). Chaque verdict publie son EXERCICE : un invariant qu'aucun sous-arbre ne met en
    jeu est NON EXERCE, pas vert."""
    i1_ex = i1_ko = i2_ex = i2_ko = i3_ko = 0
    i4_ex = i4_ko = 0
    i5_temoins = 0
    for o in arbres:
        a, d = _ids(o, ACT), _ids(o, DEACT)
        lo, rc = _ids(o, LOSE), _ids(o, RECV)
        if a:
            i1_ex += 1
            if len(lo) != 0 or len(rc) == 0:
                i1_ko += 1
        if d:
            i2_ex += 1
            if len(rc) != 0 or len(lo) == 0:
                i2_ko += 1
        if a and d:
            i3_ko += 1
        if len(lo) >= 2:
            i4_ex += 1
            if not _croissant(lo):
                i4_ko += 1
        if len(rc) >= 2 and not _croissant(rc):
            i5_temoins += 1
    return {"i1": (i1_ex, i1_ko), "i2": (i2_ex, i2_ko), "i3": i3_ko,
            "i4": (i4_ex, i4_ko), "i5_temoins": i5_temoins}


def _reconstruire(o) -> Optional[Tuple[List[int], List[int]]]:
    """`(currentTargets, desiredTargets)` reconstruits pour (I6) -- LA SEULE ENTREE COPIEE.

    Le sous-ensemble INCHANGE (`kept = current & desired`) n'est pas observable : le flux n'ecrit
    de ligne que pour ce qui BOUGE. On le choisit minimal et compatible avec la presence
    observee d'`Activate`/`Deactivate`, en prenant un id SYNTHETIQUE hors de tout ensemble
    observe (donc jamais confondu avec une cible reelle) :

      * `Activate` observe   -> `current = []`,            `desired = toAdd`
      * `Deactivate` observe -> `current = toRemove`,       `desired = []`
      * ni l'un ni l'autre   -> `kept = {K}` ; `current = sorted(toRemove + [K])`,
                                `desired = toAdd + [K]`

    ⚠ `current` EST TRIE, PARCE QUE LE NATIF LE TRIE (`AddTargetId`). Ne pas le trier ici
    fabriquerait un `currentTargets` qu'aucun `EffectComponent` ne peut porter.

    Rend `None` quand le sous-arbre ne porte AUCUNE des quatre formes (rien a rederiver)."""
    a, d = _ids(o, ACT), _ids(o, DEACT)
    lo, rc = _ids(o, LOSE), _ids(o, RECV)
    if not (a or d or lo or rc):
        return None
    if a and d:
        return None                       # (I3) deja rouge : ne pas fabriquer un montage absurde
    if a:
        return [], list(rc)
    if d:
        return list(lo), []
    k = max([0] + lo + rc) + 1
    return sorted(lo + [k]), list(rc) + [k]


def rederiver(arbres: list, mutation: str = "") -> Tuple[int, int, int]:
    """(I6). Rend `(exerces, divergents, actions_rederivees)`.

    Le port est appele POUR DE VRAI : `update_effect_targets` construit le plan, et l'on compare
    la sequence des `StepType` a celle du flux. Les mutations agissent SOIT sur une primitive que
    la garde appelle (seam de code), SOIT sur le plan rendu (seam de sortie) -- l'ordre
    d'assemblage etant en ligne dans la garde, il n'a pas d'autre seam."""
    par_step = {int(StepType.ActivateEffect): ACT, int(StepType.DeactivateEffect): DEACT,
                int(StepType.LoseEffect): LOSE, int(StepType.ReceiveEffect): RECV}
    exerces = divergents = total = 0
    orig_add, orig_rem = RE.get_targets_to_add, RE.get_targets_to_remove
    orig_cur = RE.get_current_effect_targets
    try:
        if mutation == "sens_de_la_difference":
            RE.get_targets_to_add, RE.get_targets_to_remove = orig_rem, orig_add
        elif mutation == "cibles_courantes_vides":
            RE.get_current_effect_targets = lambda comp: []
        elif mutation == "cibles_courantes_inversees":
            RE.get_current_effect_targets = lambda comp: list(reversed(orig_cur(comp)))
        for o in arbres:
            rec = _reconstruire(o)
            if rec is None:
                continue
            current, desired = rec
            exerces += 1
            comp = RE.EffectComponentView(targets=list(current))
            plan = RE.update_effect_targets(desired, comp, owner_id=o.effect_entity)
            if mutation == "plan_desactivation_en_tete":
                dea = [p for p in plan if p.action == RE.ACTION_DEACTIVATE]
                plan = dea + [p for p in plan if p.action != RE.ACTION_DEACTIVATE]
            elif mutation == "plan_receive_avant_lose":
                rcv = [p for p in plan if p.action == RE.ACTION_RECEIVE]
                plan = ([p for p in plan if p.action == RE.ACTION_ACTIVATE] + rcv
                        + [p for p in plan if p.action not in (RE.ACTION_ACTIVATE,
                                                               RE.ACTION_RECEIVE)])
            seq = [(par_step[p.step],
                    p.entity if par_step[p.step] in (LOSE, RECV) else None)
                   for p in plan if p.step in par_step]
            total += len(seq)
            if seq != _sequence(o):
                divergents += 1
    finally:
        RE.get_targets_to_add, RE.get_targets_to_remove = orig_add, orig_rem
        RE.get_current_effect_targets = orig_cur
    return exerces, divergents, total


MUTATIONS = ("sens_de_la_difference", "cibles_courantes_vides", "cibles_courantes_inversees",
             "plan_desactivation_en_tete", "plan_receive_avant_lose")


def applicables(arbres: list) -> dict:
    """POUR CHAQUE MUTATION, LE NOMBRE DE SOUS-ARBRES OU ELLE PEUT MORDRE.

    ⚠ SANS CE COMPTE, UN `a_morde=false` EST UN TROU MUET. Il confond deux etats que rien ne
    distingue dans la sortie : une mutation inerte PAR CONSTRUCTION (elle ne mute pas ce qu'elle
    croit muter -- une faute du probe) et une mutation inerte PAR LES DONNEES (le corpus ne
    contient aucun cas ou elle changerait quelque chose -- une limite du montage). La premiere
    se corrige, la seconde se DECLARE et se couvre offline. Le compte ci-dessous tranche."""
    out = {m: 0 for m in MUTATIONS}
    for o in arbres:
        rec = _reconstruire(o)
        if rec is None:
            continue
        current, desired = rec
        lo, rc = _ids(o, LOSE), _ids(o, RECV)
        if sorted(RE.get_targets_to_add(current, desired)) \
                != sorted(RE.get_targets_to_remove(current, desired)):
            out["sens_de_la_difference"] += 1
        if len(current) > 0:
            out["cibles_courantes_vides"] += 1
        # ⚠ LE CRITERE EST L'ORDRE RENDU, PAS LA TAILLE DE L'ENTREE. `len(current) >= 2` a d'abord
        # ete pris et il SURCOMPTE : `current = sorted(lo + [k])` a deja 2 elements des que `lo`
        # en a UN, et inverser une liste dont la difference ne rend qu'un element ne change rien.
        if len(RE.get_targets_to_remove(list(reversed(current)), desired)) >= 2:
            out["cibles_courantes_inversees"] += 1
        if _ids(o, DEACT) and (lo or rc or _ids(o, ACT)):
            out["plan_desactivation_en_tete"] += 1
        if lo and rc:
            out["plan_receive_avant_lose"] += 1
    return out


# ------------------------------------------------------------------------------------- scenario
def scenario(session: int, board: str, tours: int, p_units: str, a_units: str) -> dict:
    flux = capturer(session, board, tours, p_units, a_units)
    arbres, illisibles = sous_arbres(flux)
    if not arbres:
        raise MesureImpossible("aucun `Group=%s` dans le flux -- rien a confronter"
                               % GroupType.Effect_Refresh.name)
    inv = invariants(arbres)
    ex, div, nact = rederiver(arbres)
    app = applicables(arbres)
    ce = []
    for nom in MUTATIONS:
        mex, mdiv, mact = rederiver(arbres, mutation=nom)
        ce.append((nom, mdiv != div or mact != nact, mdiv, mex, app[nom]))
    with open(OUT / ("477r21r2a-%s-flux.txt" % board), "w",
              encoding="utf-8", newline="") as f:
        f.write(flux)
    return {"board": board, "lignes_flux": flux.count("\n"), "arbres": len(arbres),
            "illisibles": illisibles, "inv": inv,
            "rederivation": (ex, div, nact), "contre_epreuve": ce}


def imprimer(res: dict) -> int:
    inv = res["inv"]
    ex, div, nact = res["rederivation"]
    rouge = 0
    print("  flux : %d lignes, %d sous-arbre(s) `Effect_Refresh` lus (%d illisible(s))"
          % (res["lignes_flux"], res["arbres"], res["illisibles"]))
    for cle, nom in (("i1", "(I1) Activate => 0 Lose et >=1 Receive"),
                     ("i2", "(I2) Deactivate => 0 Receive et >=1 Lose"),
                     ("i4", "(I4) ids des Lose STRICTEMENT croissants")):
        e, k = inv[cle]
        if e == 0:
            print("    %-46s NON EXERCE (0 sous-arbre le met en jeu)" % nom)
        else:
            print("    %-46s %s  exerce=%d  contre-exemples=%d"
                  % (nom, "OK  " if k == 0 else "ROUGE", e, k))
            rouge += 1 if k else 0
    print("    %-46s %s  contre-exemples=%d"
          % ("(I3) Activate et Deactivate exclusifs",
             "OK  " if inv["i3"] == 0 else "ROUGE", inv["i3"]))
    rouge += 1 if inv["i3"] else 0
    t = inv["i5_temoins"]
    print("    %-46s %s  temoins non croissants=%d"
          % ("(I5) ids des Receive NON contraints",
             "OK  " if t > 0 else "NON DISCRIMINE", t))
    if ex == 0:
        print("    %-46s NON EXERCE" % "(I6) sequence rederivee par le port")
    else:
        print("    %-46s %s  exerce=%d  divergents=%d  actions=%d"
              % ("(I6) sequence rederivee par le port",
                 "OK  " if div == 0 else "ROUGE", ex, div, nact))
        rouge += 1 if div else 0
    print("  CONTRE-EPREUVE (a_morde publie SEPAREMENT du verdict) :")
    for nom, morde, mdiv, mex, papp in res["contre_epreuve"]:
        etat = "ROUGIT" if mdiv > 0 else "reste vert"
        print("    %-34s a_morde=%-5s %s (divergents=%d / %d ; applicable sur %d)"
              % (nom, str(morde).lower(), etat, mdiv, mex, papp))
        if not morde and papp == 0:
            print("      ! NON EXERCEE PAR LES DONNEES (0 sous-arbre applicable) -- se declare, "
                  "ne se compte PAS verte. Couverture offline exigee.")
        elif not morde:
            print("      ! la mutation a %d cas applicables et n'a RIEN change -- c'est une "
                  "faute du probe, pas une limite du corpus." % papp)
            rouge += 1
        elif mdiv == 0:
            print("      ! la mutation a MORDU sans rougir -- l'invariant ne la couvre pas.")
            rouge += 1
    return rouge


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--boards", default=",".join(BOARDS_DEFAUT))
    ap.add_argument("--tours", type=int, default=2)
    ap.add_argument("--p-units", default="")
    ap.add_argument("--a-units", default="")
    args = ap.parse_args()
    session = args.session if args.session is not None else R15A.session_courante()
    rc = 0
    for board in [b for b in args.boards.split(",") if b]:
        print("=== board %s ===" % board)
        try:
            rc += imprimer(scenario(session, board, args.tours, args.p_units, args.a_units))
        except MesureImpossible as e:
            print("  MESURE IMPOSSIBLE : %s" % e)
            rc += 1
    return 1 if rc else 0


if __name__ == "__main__":
    raise SystemExit(main())
