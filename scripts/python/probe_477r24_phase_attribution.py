#!/usr/bin/env python3
"""#477-r24 -- une PHASE native est-elle NOMMEE, et attribuee a l'operation qu'elle draine ?

LA QUESTION BINAIRE
-------------------
Le 1er argument d'`IdunBattle.Messages.InputMessageProcessor$$RunPhase` est un
`IdunBattle.Core.PhaseType`. Deux questions, dans cet ordre :
  (1) le depot l'ecrit-il par son MEMBRE NOMME, ou par un ordinal nu ?
  (2) quand une ligne nomme une phase ET une operation `Core.Services.OperationProcessor.<X>`,
      cette phase draine-t-elle REELLEMENT cette operation ?

POURQUOI CETTE SONDE EXISTE
---------------------------
`RunPhase(0xd)` -- un entier nu -- a ete mal attribue QUATRE fois :
  * trois crans du deroule #477 l'ont pris pour un `IdunBattle.Streams.GroupType`
    (`case-477r18r5` § 1, `case-477r19` § 1, `case-477r20` § 6). Les deux enums SE RECOUVRENT :
    `GroupType.User_PlaceUnit` vaut aussi 13 -- l'ordinal ne discrimine pas, le NOM si ;
  * `revive.py` et `damage.py` en ont fait, pendant trois tranches, la phase de
    `Core.Services.OperationProcessor$$ReviveUnit`. La lambda de cette phase est
    `<VerifyRemovedUnits>b__0` (les RETRAITS), et **aucun `PhaseType` ne nomme un revive**.
Aucun test ne cassait : l'erreur etait 100 % documentaire, donc structurellement invisible d'une
passe verte. C'est exactement le regime que cette sonde couvre.

LES TROIS ETAGES
----------------
  Etape 1  MIRROR + ORDINAUX FIGES. `engine/streams/phase_type.py` doit etre en bijection avec
           `data/symbols/<CURRENT>/frida/enums.tsv`, ET les ordinaux REELLEMENT ECRITS a un site
           du depot sont figes EN DUR ici. Le second cran n'est pas redondant : `probe_313`
           redevient VERT des qu'on regenere le mirror apres un renumerotage du build, alors que
           la valeur ecrite au site, elle, a change (CLAUDE.md, « FIGER l'ordinal ECRIT AU SITE »).
  Etape 2  NOMMAGE (invariant 0). Tout ordinal en position `RunPhase(<ord>` sous
           `scripts/python/**` doit porter un `PhaseType.<Membre>` sur la MEME ligne. C'est la
           parade a la racine : on ne peut plus ecrire une phase sans la nommer, donc plus
           l'attribuer de tete.
  Etape 3  ATTRIBUTION (invariant 0). Sur toute ligne portant une phase, tout jeton d'operation
           `Core.Services.OperationProcessor.<X>` trouve doit appartenir au drain MESURE de cette
           phase. Les jetons ne sont pas une liste : ils sont DERIVES des 149 methodes de
           `Core.Services.OperationProcessor` lues dans `frida/methods.tsv`.

CE QUE CETTE SONDE NE VOIT PAS -- DIT, PAS SOUS-ENTENDU
-------------------------------------------------------
  * la PROSE. « la phase du revive » en francais ne porte aucun jeton d'operation : l'etape 3 y
    est aveugle. C'est l'etape 2 qui couvre ce regime, indirectement -- un `PhaseType.<Membre>`
    ecrit en toutes lettres a cote du mot « revive » saute aux yeux d'un relecteur, la ou `0xd`
    ne disait rien a personne. Ce n'est pas une garde executable, et c'est nomme comme tel ;
  * les phases dont le DRAIN n'a pas ete lu au decompile. `DRAIN_MESURE` ne couvre que les deux
    phases de `VerifyDeaths` ; les autres sont imprimees sous `NON COUVERT`, jamais rendues
    vertes en silence ;
  * les fichiers hors `scripts/python/**` et `docs/rl/**`.

EXEMPTION AU SITE (comptee, imprimee, jamais silencieuse)
---------------------------------------------------------
Une ligne qui CITE une attribution refutee (« ce paragraphe disait X, c'est faux ») porte
legitimement une phase ET un jeton contradictoire. Elle le DECLARE avec le marqueur
`[phase-attribution:refute]`. Ce n'est ni une liste blanche de fichiers ni un motif devine :
c'est une declaration AU SITE, que la sonde COMPTE et IMPRIME -- si le compte enfle, ca se voit.

  --mutants   contre-epreuve : injecte des mutants et exige que CHAQUE etage MORDE. `a_mordu`
              est rendu SEPAREMENT du verdict (une contre-epreuve inerte passe pour mordante).

Sortie 0 = les trois etages passent ; 1 sinon. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

from symbols_layout import build_dir, current_build  # noqa: E402
from engine.streams.phase_type import PhaseType  # noqa: E402

PY = REPO / "scripts" / "python"
DOCS = REPO / "docs" / "rl"
CLE_ENUM = "IdunBattle.Core.PhaseType"
CLE_CLASSE = "Core.Services.OperationProcessor"
MARQUEUR_REFUTE = "[phase-attribution:refute]"

#: Les ordinaux REELLEMENT ECRITS a un site du depot, figes a la conversion (#477-r24). Ce n'est
#: pas une copie du mirror : c'est ce que la tranche a MESURE au decompile et inscrit dans les
#: docstrings. Un renumerotage du build les fait rougir meme si le mirror a ete regenere.
ORDINAUX_ECRITS = {
    0: "StartBattle",                        # `Visit(StartBattleMessage)` -- input_messages.py
    4: "AddUnit",                            # `Visit(AddUnitMessage)`     -- dispatch/phase.py
    5: "MoveUnit",                           # `Visit(MoveUnitMessage)`    -- damage.py, probe_429r1r3r1
    6: "ActiveAbility",                      # `Visit(ActiveAbilityMessage)` -- handler.py
    12: "ProcessDeaths",                     # `VerifyDeaths`, 1re phase
    13: "ProcessRemovals",                   # `VerifyDeaths`, 2e phase (inline `VerifyRemovedUnits`)
    14: "ProcessDamageEvents",               # `ProcessDamageEvents` -- dispatch/damage_events.py
    15: "ProcessPendingTriggeredAbilities",  # `ProcessPendingTriggeredAbilities`, un item par phase
}

#: LE DRAIN MESURE, phase par phase -- LU au decompile, jamais deduit du nom.
#:
#:   ProcessDeaths (0xc) : la lambda `<VerifyDeaths>b__0` teste si l'entite est une machine, puis
#:       appelle `KillUnit(killer, killed, options)` (slot a 3 arguments, apres
#:       `KillUnitOperationOptions.ForDefault()`) ou `DestroyMachine(killer, killed)` (2 arguments).
#:   ProcessRemovals (0xd) : la lambda `<VerifyRemovedUnits>b__0` copie la file dans une `List`,
#:       la `Clear()`, ouvre `GroupType.System_ProcessRemovals` puis, pour chaque entite non
#:       nulle, appelle le slot `0x55` avec DEUX arguments -- `UnregisterEntityFromTriggers`.
#:
#: ⚠ CE N'EST PAS `RemoveUnit`, ET LA CORRECTION VIENT DE #477-r24-r1. `#477-r19` avait lu ce
#: slot comme `RemoveUnit(unit, removeEffects, keepActive)` ; `#477-r24` avait soupconne l'erreur
#: sans pouvoir la trancher, et propose `RotateUnit`. Les deux sont faux : le slot `0x55` de
#: `Core.Services.IOperationProcessor` est `UnregisterEntityFromTriggers`, lu dans le champ
#: `slot` du metadata IL2CPP (`data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`),
#: et l'ARITE le confirme -- le site passe 2 arguments, `RemoveUnit` en prend 3 (slot 6),
#: `RotateUnit` est au slot 0x86. Consequence : cette phase n'invoque AUCUNE operation qui
#: emette du flux, ce qui explique le groupe TOUJOURS VIDE observe par `#477-r19` (son residu
#: `-r1`) sans avoir besoin des gardes de tete de `RemoveUnitOperation`.
#:
#: ⚠ `ReviveUnit` N'EST DANS AUCUN ENSEMBLE, ET C'EST LE RESULTAT DE LA TRANCHE :
#: `Core.Services.OperationProcessor$$ReviveUnit(killed)` n'a AUCUNE xref CODE, et son unique site
#: d'invocation est la branche `else` de la garde `pendingRevive.HasValue`, DANS
#: `IdunBattle.Operations.KillUnitOperation$$Execute`. Le revive n'a donc pas de phase du tout.
#: Ce point est CONFIRME par #477-r24-r1 : le slot y est ecrit `99` en DECIMAL par Ghidra
#: (d'ou son invisibilite a toute recherche sur `0x63`), et le slot 99 est bien `ReviveUnit`.
DRAIN_MESURE = {
    int(PhaseType.ProcessDeaths): {"KillUnit", "DestroyMachine"},
    int(PhaseType.ProcessRemovals): {"UnregisterEntityFromTriggers"},
}

#: `RunPhase(` puis, en sautant un eventuel `this,`, l'argument de phase.
RE_SITE = re.compile(r"RunPhase\s*\(\s*(?:this\s*,\s*)?(?P<arg>[^,)]*)")
RE_ORDINAL = re.compile(r"^\s*(0x[0-9a-fA-F]+|\d+)\s*$")
RE_MEMBRE = re.compile(r"PhaseType\.(?P<nom>[A-Za-z_][A-Za-z0-9_]*)")
RE_ORD_DANS_MEMBRE = re.compile(r"/\*\s*(0x[0-9a-fA-F]+|\d+)\s*\*/")


def enum_natif(build: str) -> dict:
    """{valeur: nom} depuis `data/symbols/<build>/frida/enums.tsv`."""
    p = build_dir(build) / "frida" / "enums.tsv"
    for ligne in p.open(encoding="utf-8"):
        if ligne.startswith(CLE_ENUM + "\t"):
            out = {}
            for paire in ligne.rstrip("\n").split("\t", 1)[1].split(","):
                v, _, n = paire.partition("=")
                if n:
                    out[int(v)] = n
            return out
    raise SystemExit("[477r24] ABSENT de enums.tsv : " + CLE_ENUM)


def noms_operations(build: str) -> set:
    """Les noms de methode de `Core.Services.OperationProcessor`, LUS dans `frida/methods.tsv`.

    C'est ce qui rend l'etape 3 DERIVEE plutot qu'une liste : on ne cherche pas `ReviveUnit` en
    dur, on cherche N'IMPORTE quelle operation et on la confronte au drain mesure."""
    p = build_dir(build) / "frida" / "methods.tsv"
    out = set()
    for ligne in p.open(encoding="utf-8"):
        champs = ligne.rstrip("\n").split("\t")
        if len(champs) > 2 and champs[2] == CLE_CLASSE:
            out.add(champs[1].rsplit(".", 1)[-1])
    return out


def fichiers() -> list:
    """Le corpus balaye. ⚠ LA SONDE S'EXCLUT ELLE-MEME, et c'est NECESSAIRE, pas cosmetique :
    ses mutants SONT des attributions fausses ecrites en clair -- sans cette exclusion elle
    rougirait sur son propre materiel de contre-epreuve, ce qui la rendrait inutilisable. Les
    mutants sont injectes dans `engine/streams/phase_type.py`, jamais ici : l'exclusion ne peut
    donc pas rendre `--mutants` inerte."""
    moi = Path(__file__).resolve()
    out = [p for p in sorted(PY.rglob("*.py"))
           if "__pycache__" not in p.parts and p.resolve() != moi]
    out += sorted(DOCS.rglob("*.md"))
    return out


def sites(lignes, chemin):
    """Rend (no_ligne, texte, ordinal|None, membre|None) pour chaque `RunPhase(` porteur."""
    for i, texte in enumerate(lignes, start=1):
        for m in RE_SITE.finditer(texte):
            arg = m.group("arg")
            mo = RE_ORDINAL.match(arg)
            mb = RE_MEMBRE.search(arg)
            if mo is None and mb is None:
                continue                      # `RunPhase(type, action, ...)` : signature, pas un site
            ordv = int(mo.group(1), 0) if mo else None
            yield i, texte, ordv, (mb.group("nom") if mb else None)


def etape1(ref: dict) -> list:
    """MIRROR bijectif + ordinaux ECRITS figes."""
    ecarts = []
    port = {int(m): m.name for m in PhaseType}
    for v, n in sorted(ref.items()):
        if port.get(v) != n:
            ecarts.append("mirror : %d = %r au jeu, %r au port" % (v, n, port.get(v)))
    for v in sorted(set(port) - set(ref)):
        ecarts.append("mirror : %d = %r au port, ABSENT du jeu" % (v, port[v]))
    for v, n in sorted(ORDINAUX_ECRITS.items()):
        if ref.get(v) != n:
            ecarts.append("ordinal ECRIT au site : %d devait nommer %r, le build dit %r"
                          % (v, n, ref.get(v)))
    return ecarts


def etape2(ref: dict, corpus: dict) -> list:
    """NOMMAGE : sous `scripts/python/**`, un ordinal de phase porte son membre sur la ligne."""
    ecarts = []
    for chemin, lignes in corpus.items():
        if not str(chemin).startswith(str(PY)):
            continue
        for no, texte, ordv, membre in sites(lignes, chemin):
            if ordv is not None and "PhaseType." not in texte:
                ecarts.append("%s:%d ordinal NU %s (attendu : PhaseType.%s /*%s*/) -> %s"
                              % (rel(chemin), no, hex(ordv), ref.get(ordv, "?"),
                                 hex(ordv), texte.strip()[:90]))
    return ecarts


def etape3(ref: dict, corpus: dict, ops: set):
    """ATTRIBUTION : une phase ne cite que les operations de son drain MESURE.

    Rend (ecarts, exemptions, non_couvertes)."""
    ecarts, exemptions, non_couvertes = [], [], {}
    ref_inv = {n: v for v, n in ref.items()}
    for chemin, lignes in corpus.items():
        for no, texte, ordv, membre in sites(lignes, chemin):
            phase = ordv if ordv is not None else ref_inv.get(membre)
            if phase is None:
                continue
            # concordance ordinal <-> membre quand les deux sont ecrits (`PhaseType.X /*0xd*/`)
            if membre is not None:
                mo = RE_ORD_DANS_MEMBRE.search(texte)
                if mo is not None and ref_inv.get(membre) != int(mo.group(1), 0):
                    ecarts.append("%s:%d CONCORDANCE : PhaseType.%s vaut %s, le site ecrit %s"
                                  % (rel(chemin), no, membre, ref_inv.get(membre), mo.group(1)))
            if phase not in DRAIN_MESURE:
                non_couvertes.setdefault(phase, 0)
                non_couvertes[phase] += 1
                continue
            # `<X>` comme mot entier, OU la forme `<X>Operation` (`ReviveUnitOperation$$Execute`) :
            # c'est sous ce second visage que la faute etait ecrite dans `case-haze-ord`.
            trouves = {x for x in ops
                       if re.search(r"(?<![A-Za-z0-9_])" + x + r"(?:Operation)?(?![A-Za-z0-9_])",
                                    texte)}
            hors = sorted(trouves - DRAIN_MESURE[phase])
            if not hors:
                continue
            if MARQUEUR_REFUTE in texte:
                exemptions.append("%s:%d cite %s pour la phase %s (declare refute)"
                                  % (rel(chemin), no, ",".join(hors), ref.get(phase, phase)))
                continue
            ecarts.append("%s:%d ATTRIBUTION : la phase %s ne draine PAS %s (drain mesure : %s)"
                          % (rel(chemin), no, ref.get(phase, phase), ",".join(hors),
                             ",".join(sorted(DRAIN_MESURE[phase]))))
    return ecarts, exemptions, non_couvertes


def rel(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("\\", "/")


def charger() -> dict:
    return {p: p.read_text(encoding="utf-8", errors="replace").splitlines() for p in fichiers()}


# ------------------------------------------------------------------ contre-epreuve par mutants

#: Chaque mutant est une LIGNE injectee dans un corpus de travail. `etage` = l'etage qui DOIT
#: mordre. Un mutant qui ne mord pas rend la contre-epreuve INERTE -- et c'est ce que trois
#: tranches de suite ont laisse passer, d'ou `a_mordu` rendu SEPAREMENT du verdict.
MUTANTS = [
    ("2 ordinal nu",
     "    `RunPhase(0xd)` draine la file des retraits.", 2),
    ("2 ordinal nu (autre phase)",
     "    `RunPhase(this, 0xf, action, 1, 0)` pour chaque item.", 2),
    ("3 la faute historique : la phase 0xd attribuee au revive",
     "    `RunPhase(PhaseType.ProcessRemovals /*0xd*/)` -> "
     "`Core.Services.OperationProcessor$$ReviveUnit`", 3),
    ("3 la meme faute ecrite par le MEMBRE seul",
     "    `RunPhase(PhaseType.ProcessRemovals)` -> `ReviveUnit` (l'operation du revive)", 3),
    ("3 une operation etrangere sur la phase des morts",
     "    `RunPhase(PhaseType.ProcessDeaths /*0xc*/)` -> `HealUnit`", 3),
    ("3 concordance ordinal <-> membre rompue",
     "    `RunPhase(PhaseType.ProcessDeaths /*0xd*/)` -> `KillUnit`", 3),
]


def contre_epreuve(ref: dict, ops: set) -> int:
    base = charger()
    cible = PY / "engine" / "streams" / "phase_type.py"
    echecs = 0
    print("\nCONTRE-EPREUVE PAR MUTANTS (a_mordu est rendu SEPAREMENT du verdict)")
    for nom, ligne, etage in MUTANTS:
        corpus = dict(base)
        corpus[cible] = list(base[cible]) + [ligne]
        if etage == 2:
            trouve = etape2(ref, corpus)
            temoin = etape2(ref, base)
        else:
            trouve, _, _ = etape3(ref, corpus, ops)
            temoin, _, _ = etape3(ref, base, ops)
        a_mordu = len(trouve) > len(temoin)
        print("  %-6s etage %d  %s" % ("MORD" if a_mordu else "INERTE", etage, nom))
        if not a_mordu:
            echecs += 1
    print("  -> %d mutant(s) INERTE(s) sur %d" % (echecs, len(MUTANTS)))
    return echecs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mutants", action="store_true",
                    help="joue la contre-epreuve (chaque etage doit MORDRE)")
    args = ap.parse_args()

    build = current_build()
    ref = enum_natif(build)
    ops = noms_operations(build)
    corpus = charger()

    print("[477r24] build=%s  %s = %d membre(s)  |  %s = %d methode(s)  |  corpus = %d fichier(s)"
          % (build, CLE_ENUM, len(ref), CLE_CLASSE, len(ops), len(corpus)))

    e1 = etape1(ref)
    print("\nETAPE 1 -- MIRROR + ORDINAUX ECRITS FIGES (%d ordinal(aux) figes)"
          % len(ORDINAUX_ECRITS))
    print("  %s  ecarts=%d" % ("OK" if not e1 else "ECHEC", len(e1)))
    for x in e1:
        print("    " + x)

    e2 = etape2(ref, corpus)
    total_sites = sum(1 for c, l in corpus.items() for _ in sites(l, c))
    print("\nETAPE 2 -- NOMMAGE (invariant 0 sous scripts/python/**)")
    print("  sites de phase dans tout le corpus : %d" % total_sites)
    print("  %s  ordinaux NUS=%d" % ("OK" if not e2 else "ECHEC", len(e2)))
    for x in e2:
        print("    " + x)

    e3, exempt, non_couv = etape3(ref, corpus, ops)
    print("\nETAPE 3 -- ATTRIBUTION (invariant 0, jetons DERIVES de methods.tsv)")
    print("  drain MESURE : " + " | ".join(
        "%s -> %s" % (ref.get(p, p), ",".join(sorted(o))) for p, o in sorted(DRAIN_MESURE.items())))
    if non_couv:
        print("  NON COUVERT (drain non lu au decompile, donc PAS declare vert) : " + ", ".join(
            "%s x%d" % (ref.get(p, p), n) for p, n in sorted(non_couv.items())))
    print("  EXEMPTIONS declarees au site %s : %d" % (MARQUEUR_REFUTE, len(exempt)))
    for x in exempt:
        print("    " + x)
    print("  %s  attributions FAUSSES=%d" % ("OK" if not e3 else "ECHEC", len(e3)))
    for x in e3:
        print("    " + x)

    rc = 1 if (e1 or e2 or e3) else 0
    if args.mutants:
        rc = 1 if (contre_epreuve(ref, ops) or rc) else 0

    print("\nVERDICT : " + ("OK -- phases nommees et attribuees au drain mesure"
                            if rc == 0 else "ECHEC"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
