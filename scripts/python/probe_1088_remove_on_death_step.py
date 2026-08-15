#!/usr/bin/env python
"""`#1088` -- A QUELLE ETAPE DE LA MORT chaque classe d'effet quitte le porteur.

    python probe_1088_remove_on_death_step.py             # derivation OFFLINE complete
    python probe_1088_remove_on_death_step.py --regenerer  # + ecrit l'entree versionnee
    python probe_1088_remove_on_death_step.py --runtime    # + 2e source, la vtable LIVE

## La question

`IdunBattle.Operations.KillUnitOperation$$Execute` joue TROIS retraits d'effets et deux events,
dans cet ordre LU : `RemoveEffects(step 0)` -> `RemoveEffects(step 1)` -> `On(UnitDeath)` ->
`On(UnitDefeated)` -> `RemoveEffects(step 2)`.

`IdunBattle.Operations.RemoveEffectsOperation$$Execute` decide effet par effet :

    if (options.step.HasValue && effect.<IEffect slot 4> != options.step.Value)  -> NE PAS retirer
    if (options.keepOnRevive && effect.<IEffect slot 2>)                         -> NE PAS retirer
    sinon                                                                        -> retirer

Les deux slots sont NOMMES dans `data/symbols/<build>/metadata/interface_slots.tsv` (`IEffect 4
get_RemoveOnDeathStep`, `IEffect 2 get_KeepOnRevive`) -- jamais deduits d'un ordinal.
⚠ Le filtre par step est GARDE PAR `HasValue` : un appel sans step retire TOUT, quel que soit le
slot 4. Cette garde est load-bearing et ne se voit pas dans un resume << compare le slot 4 a
options.step >>.

## Pourquoi une derivation, et pas un grep

`get_RemoveOnDeathStep` est un getter CONSTANT : IL2CPP DEDUPLIQUE son corps, donc il est absent de
`frida/methods.tsv` ET de `ghidra/functions.tsv`, et `IEffect` ne declare aucune methode dans le
dump. L'ABSENCE n'y prouve rien (CLAUDE.md). La machinerie de `probe_175r2_can_be_immune_to.py`
repond exactement a cette forme de question -- DECLARATION lue dans le `global-metadata.dat`
(complete, independante de l'ICF), VALEUR lue dans le bloc `methodPointers` du PE, avec controle
d'alignement -- et ce module se contente d'y poser le NOM DU GETTER et le DECODEUR ENTIER.

## Ce que la derivation a RENVERSE (2026-08-15, build `t6dpr4k06g`)

Le port posait `BaseEffect.remove_on_kill_step = 0` (`PreUnitRemove`), en HYPOTHESE NOMMEE (#389-r2)
faute de pouvoir la lire. Elle est FAUSSE sur les deux plans :

  * le DEFAUT de `IdunBattle.Entities.Effects.BaseEffect` est **1** (`AfterUnitRemove`), corps
    `b8 01 00 00 00 c3`, 66 controles d'alignement locaux ;
  * **quatre** classes surchargent, et trois d'entre elles valent **2** (`AfterDeathTrigger`).

C'est ce qui explique la mesure live de `#911-r1` : `TauntedEffect` (l'effet
`27 Taunted_OnlySpecificTargets`) vaut **2**, donc il SURVIT aux steps 0 et 1 et est encore porte
quand `On(UnitDefeated)` part -- ce que le port, qui retirait tout au step 0, rendait impossible.

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import probe_175r2_can_be_immune_to as P175                              # noqa: E402

#: Le getter en cause, LU dans `data/symbols/<build>/metadata/interface_slots.tsv` (`IEffect 4`),
#: jamais ecrit de memoire.
GETTER = "get_RemoveOnDeathStep"
#: Le nom du slot voisin qui gouverne l'AUTRE clause du meme `if` (documentation, pas derive ici).
GETTER_VOISIN = "get_KeepOnRevive"                                       # `IEffect` slot 2
#: `IdunBattle.Operations.KillUnitStep` -- domaine COMPLET, relu dans `frida/enums.tsv` du build.
KILL_UNIT_STEP = {0: "PreUnitRemove", 1: "AfterUnitRemove", 2: "AfterDeathTrigger"}
#: La valeur que rend `IdunBattle.Entities.Effects.BaseEffect`, DERIVEE (jamais ecrite de memoire) ;
#: cette constante n'est la que pour rendre le test de non-regression lisible.
DEFAUT_ATTENDU = 1
TSV_REL = ("metadata", "remove_on_death_step.tsv")


def tsv_path(build: str | None = None) -> Path:
    return P175.build_dir(build).joinpath(*TSV_REL)


def deriver() -> dict | None:
    """`{classe: {declare, valeur_propre, valeur_effective, corps, herite_de, source}}` ou `None`.

    ⚠ On REPOSITIONNE le getter ET le decodeur du module reutilise, et on les REMET ensuite :
    `probe_175r2` est un module partage, le laisser dans un etat modifie ferait mesurer le mauvais
    slot -- ou le lire avec le mauvais decodeur -- au prochain appelant du meme process."""
    ancien_g, ancien_d = P175.GETTER, P175.DECODEUR
    try:
        P175.GETTER, P175.DECODEUR = GETTER, P175.decoder_entier
        return P175.deriver()
    finally:
        P175.GETTER, P175.DECODEUR = ancien_g, ancien_d


def ecrire_tsv(table: dict) -> Path:
    """Ecrit l'entree versionnee. On liste les classes dont la valeur DIFFERE du defaut, PLUS le
    defaut lui-meme -- pas seulement les << vrais >> : ici il n'y a pas de valeur privilegiee, et
    un filtre par troncature ferait disparaitre le `0` de `AttemptedPossession_PossessedEffect`
    (`not 0` est vrai en Python -- exactement le piege que `probe_175r2.ecrire_tsv` porte pour son
    booleen, et qu'il ne faut PAS recopier ici)."""
    p = tsv_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    defaut = table.get(P175.BASE, {}).get("valeur_effective")
    lignes = [
        "# `%s` (`IEffect` slot 4) de la fermeture transitive de `%s` -- build %s."
        % (GETTER, P175.BASE, P175.build_pin.current_build()),
        "# Domaine : `IdunBattle.Operations.KillUnitStep` = %s."
        % ", ".join("%d=%s" % kv for kv in sorted(KILL_UNIT_STEP.items())),
        "# DEFAUT de la base = %s. Sont listees les classes qui DECLARENT le getter (les autres"
        % defaut,
        "# heritent du defaut) -- y compris quand leur valeur EGALE le defaut.",
        "# Regenerer : python scripts/python/probe_1088_remove_on_death_step.py --regenerer",
        "#classe\tparent\tpropre\tcorps",
    ]
    for nom, r in sorted(table.items()):
        if not r.get("declare"):
            continue
        lignes.append("%s\t%s\t%s\t%s"
                      % (nom, r["parent"],
                         "" if r["valeur_propre"] is None else r["valeur_propre"], r["corps"]))
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return p


def lire_tsv() -> dict:
    """`{classe: valeur_propre}` des DECLARANTES, depuis l'entree versionnee."""
    p = tsv_path()
    if not p.is_file():
        raise SystemExit(
            "ROUGE : l'entree versionnee est absente (%s).\n"
            "  La regenerer sur une machine ou le jeu est installe :\n"
            "  python scripts/python/probe_1088_remove_on_death_step.py --regenerer"
            % p.as_posix())
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        c = line.split("\t")
        if len(c) >= 3 and c[2] != "":
            out[c[0]] = int(c[2])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regenerer", action="store_true")
    ap.add_argument("--runtime", action="store_true",
                    help="2e source : la VTABLE live (PARTIELLE -- classes deja initialisees)")
    a = ap.parse_args()

    print("== #1088 -- `IEffect` slot 4 `%s`, par classe d'effet" % GETTER)
    table = deriver()
    if table is None:
        print("REFUS : la derivation offline n'a pas pu conclure (rien n'est devine).")
        return 2

    defaut = table.get(P175.BASE, {}).get("valeur_effective")
    inconnu = sorted(k for k, v in table.items() if v.get("valeur_effective") is None)
    declarants = sorted(k for k, v in table.items() if v.get("declare"))

    print("[3] %d classes ; DEFAUT (`%s`) = %s (%s)"
          % (len(table), P175.BASE.rsplit(".", 1)[-1], defaut,
             KILL_UNIT_STEP.get(defaut, "HORS DOMAINE")))
    print("[3] %d classe(s) DECLARENT le getter :" % len(declarants))
    for n in declarants:
        r = table[n]
        print("      %-76s = %s (%s)  %s"
              % (n, r["valeur_propre"], KILL_UNIT_STEP.get(r["valeur_propre"], "HORS DOMAINE"),
                 r["source"]))
    if inconnu:
        print("[3] %d classe(s) INDETERMINEE(S) (ni constante ni heritee) :" % len(inconnu))
        for n in inconnu[:10]:
            print("      %-76s %s" % (n, table[n]["source"]))

    repart: dict = {}
    for v in table.values():
        repart[v.get("valeur_effective")] = repart.get(v.get("valeur_effective"), 0) + 1
    print("[3] repartition des valeurs EFFECTIVES : %s"
          % ", ".join("%s(%s)=%d" % (k, KILL_UNIT_STEP.get(k, "?"), n)
                      for k, n in sorted(repart.items(), key=lambda kv: (kv[0] is None, kv[0]))))

    # GARDE DE DOMAINE : une valeur hors `KillUnitStep` voudrait dire que le calage a derape ou que
    # l'enum a bouge. On le DIT au lieu de l'ecrire dans une entree versionnee.
    hors = sorted(str(k) for k in repart if k is not None and k not in KILL_UNIT_STEP)
    if hors:
        print("      ROUGE : valeur(s) HORS du domaine `KillUnitStep` : %s" % ", ".join(hors))
        return 1

    if a.regenerer:
        print("[4] ecrit : %s" % ecrire_tsv(table).as_posix())

    if a.runtime:
        # TEMOIN NON DEGENERE : on confronte les DECLARANTES **et** des classes qui heritent du
        # defaut. Un accord qui ne porterait que sur les surcharges ne prouverait rien contre un
        # lecteur qui rendrait la meme constante partout.
        temoins = [P175.BASE,
                   "IdunBattle.Entities.Effects.Loki.PinnedEffect",
                   "IdunBattle.Entities.Effects.Loki.StunnedEffect"]
        cibles = list(declarants) + [t for t in temoins if t not in declarants]
        ancien_g, ancien_d = P175.GETTER, P175.DECODEUR
        try:
            P175.GETTER, P175.DECODEUR = GETTER, P175.decoder_entier
            lus, refus = P175.runtime(cibles)
        finally:
            P175.GETTER, P175.DECODEUR = ancien_g, ancien_d
        print("[5] 2e SOURCE (vtable RUNTIME + octets du corps) : %d lue(s), %d refus"
              % (len(lus), len(refus)))
        desaccords = []
        for n, v in sorted(lus.items()):
            attendu = table[n]["valeur_effective"]
            if v != attendu:
                desaccords.append(n)
            print("      %-9s %-72s runtime=%s binaire=%s"
                  % ("ACCORD" if v == attendu else "DESACCORD", n, v, attendu))
        for n, why in refus:
            print("      REFUS     %-72s %s" % (n, why))
        if not lus:
            print("      AUCUNE classe lue au runtime -- la confrontation n'a rien mesure")
            return 1
        # NON-DEGENERESCENCE : l'accord doit porter sur AU MOINS DEUX valeurs distinctes, sinon il
        # est compatible avec un lecteur constant.
        if len(set(lus.values())) < 2:
            print("      ROUGE : le temoin runtime est DEGENERE (une seule valeur distincte : %s)"
                  % sorted(set(lus.values())))
            return 1
        if desaccords:
            print("      ROUGE : %d desaccord(s)" % len(desaccords))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
