#!/usr/bin/env python
"""`#547-r13` -- QUEL effet SURVIT a un REVIVE (`IEffect` slot 2 `get_KeepOnRevive`).

    python probe_547r13_keep_on_revive.py             # derivation OFFLINE complete
    python probe_547r13_keep_on_revive.py --regenerer  # + ecrit l'entree versionnee
    python probe_547r13_keep_on_revive.py --runtime    # + 2e source, la vtable LIVE

## La question, et pourquoi elle n'est PAS celle de #1088

`IdunBattle.Operations.RemoveEffectsOperation$$Execute` porte DEUX clauses, et chacune est
gardee par un champ DIFFERENT de la struct d'options (12 octets, layout PROUVE par
`Core.Services.OperationProcessor$$RemoveEffects`, qui recopie exactement
`*(undefined8*)options` puis `*(undefined4*)(options + 8)`) :

    +0x00  Nullable<IdunBattle.Operations.KillUnitStep> step
    +0x08  <4 octets>  -- le gate de la SECONDE clause

    foreach (effectId in owner.EffectsComponent.ActiveEffectIds@+0x10) {
        effect = EffectsDatabase.GetEffect(effectEntity.EffectComponent.Type@+0x58)
        if (options.step.HasValue && effect.<IEffect slot 4> != options.step.Value) continue
        if (options.<+0x08>       && effect.<IEffect slot 2>)                       continue
        toRemove.Add(effectId)
    }

#1088 a derive le slot 4 (`get_RemoveOnDeathStep`). Ce module-ci derive le slot 2
(`get_KeepOnRevive`), l'autre moitie du meme `if`.

## Ce que la lecture des SEPT producteurs etablit (2026-08-18, build `t6dpr4k06g`)

`IOperationProcessor` slot 90 = `RemoveEffects` (arite 2, `metadata/ioperationprocessor_slots.tsv`).
CINQ fonctions l'invoquent ; deux autres `$$RemoveEffects` du binaire ne passent PAS par ce slot et
sont listees pour que l'inventaire soit clos :

    KillUnitOperation$$RemoveEffects(killed, step)        step = Nullable(step)   +0x08 = 0
    DestroyMachineOperation$$RemoveEffects(killed, step)  step = Nullable(step)   +0x08 = 0
    FleeOperation$$RemoveEffects(killed, step)            step = Nullable(step)   +0x08 = 0
    RemoveUnitOperation$$RemoveEffects(unit)              step = SANS valeur      +0x08 = 0
    ReviveUnitOperation$$RemoveEffects(unit)              step = SANS valeur      +0x08 = 1
    --- n'empruntent PAS le slot 90 (boucle inline, propre a chacun) ---
    ChangeUnitOwnerOperation$$RemoveEffects(unit)         lit `IEffect` slot 3 `get_KeepOnChangeOwner`
    RemoveMachineOperation$$RemoveEffects(machine)        AUCUN filtre : retire tout

⇒ `options.<+0x08>` vaut VRAI a **UN SEUL** producteur, le REVIVE. Le slot 2 `get_KeepOnRevive`
n'est donc lu NULLE PART sur le chemin de MORT : quelle que soit sa valeur, un effet porte par une
unite tuee est retire. C'est ce qui tranche la contradiction de `#547-r13` -- l'observation
(`effects=[]` sur trois cadavres) etait JUSTE, et la lecture qui faisait survivre
`LifewardsProtectingEffect` avait perdu le `options.<+0x08> &&` de la seconde clause.

⚠ `ReviveUnitOperation$$RemoveEffects` n'a AUCUNE xref CODE (deux entrees DATA de tables de
methodes) : son corps est le DOUBLON qu'IL2CPP a emis, et l'appel reel est INLINE dans
`IdunBattle.Operations.ReviveUnitOperation$$Execute` -- meme octet de garde de cctor
(`DAT_18363c645`), memes deux ecritures (`Nullable` a zero, champ `+0x08` a 1), meme slot 0x5a.
Conclure << mort >> d'une absence de xref aurait ete faux ; c'est la lecture du corps appelant qui
le dit.

## Pourquoi une derivation, et pas un grep

`get_KeepOnRevive` est un getter CONSTANT : IL2CPP DEDUPLIQUE son corps, donc il est absent de
`frida/methods.tsv` ET de `ghidra/functions.tsv`, et `IEffect` ne declare aucune methode dans le
dump -- l'ABSENCE n'y prouve rien (CLAUDE.md). Et le corps `b0 01 c3` (`mov al,1 ; ret`) est de
surcroit partage par des dizaines de classes de tout le binaire : << la table dit que cette classe
rend TRUE >> ne prouve rien non plus, un corps dedupliqué n'ayant qu'UN propriétaire dans la table
indexee par adresse. La machinerie de `probe_175r2_can_be_immune_to.py` repond exactement a cette
forme : DECLARATION lue dans le `global-metadata.dat` (complete, independante de l'ICF), VALEUR lue
aux OCTETS dans le bloc `methodPointers` du PE, avec controle d'alignement.

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

#: Le getter en cause, LU dans `data/symbols/<build>/metadata/interface_slots.tsv` (`IEffect 2`),
#: jamais ecrit de memoire.
GETTER = "get_KeepOnRevive"
#: Le slot voisin, qui gouverne l'AUTRE clause du meme `if` (derive par `probe_1088`).
GETTER_VOISIN = "get_RemoveOnDeathStep"                                  # `IEffect` slot 4
#: Le SEUL producteur du slot 90 qui arme le gate de ce getter (cf. l'en-tete).
PRODUCTEUR_ARME = "IdunBattle.Operations.ReviveUnitOperation$$Execute"
TSV_REL = ("metadata", "keep_on_revive.tsv")


def tsv_path(build: str | None = None) -> Path:
    return P175.build_dir(build).joinpath(*TSV_REL)


def deriver() -> dict | None:
    """`{classe: {declare, valeur_propre, valeur_effective, corps, herite_de, source}}` ou `None`.

    ⚠ On REPOSITIONNE le getter ET le decodeur du module reutilise, et on les REMET ensuite :
    `probe_175r2` est un module partage, le laisser dans un etat modifie ferait mesurer le mauvais
    slot -- ou le lire avec le mauvais decodeur -- au prochain appelant du meme process."""
    ancien_g, ancien_d = P175.GETTER, P175.DECODEUR
    try:
        P175.GETTER, P175.DECODEUR = GETTER, P175.decoder_booleen
        return P175.deriver()
    finally:
        P175.GETTER, P175.DECODEUR = ancien_g, ancien_d


def ecrire_tsv(table: dict) -> Path:
    """Ecrit l'entree versionnee : toutes les classes qui DECLARENT le getter, avec leur valeur.

    ⚠ On n'ecrit PAS que les << vrais >> : `not False` est vrai en Python, donc un filtre par
    troncature ferait disparaitre une surcharge a `False` -- exactement le piege que
    `probe_1088.ecrire_tsv` documente."""
    p = tsv_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    defaut = table.get(P175.BASE, {}).get("valeur_effective")
    lignes = [
        "# `%s` (`IEffect` slot 2) de la fermeture transitive de `%s` -- build %s."
        % (GETTER, P175.BASE, P175.build_pin.current_build()),
        "# LU par UNE SEULE clause du binaire : la seconde de",
        "# `IdunBattle.Operations.RemoveEffectsOperation$$Execute`, gardee par `options.<+0x08>`,",
        "# que SEUL `%s` arme (les trois producteurs de MORT" % PRODUCTEUR_ARME,
        "# et le despawn passent 0). Sur le chemin de MORT ce getter est donc INERTE.",
        "# DEFAUT de la base = %s. Sont listees les classes qui DECLARENT le getter (les autres"
        % defaut,
        "# heritent du defaut) -- y compris quand leur valeur EGALE le defaut.",
        "# Regenerer : python scripts/python/probe_547r13_keep_on_revive.py --regenerer",
        "#classe\tparent\tpropre\tcorps",
    ]
    for nom, r in sorted(table.items()):
        if not r.get("declare"):
            continue
        lignes.append("%s\t%s\t%s\t%s"
                      % (nom, r["parent"],
                         "" if r["valeur_propre"] is None else int(bool(r["valeur_propre"])),
                         r["corps"]))
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return p


def lire_tsv() -> dict:
    """`{classe: valeur_propre (bool)}` des DECLARANTES, depuis l'entree versionnee."""
    p = tsv_path()
    if not p.is_file():
        raise SystemExit(
            "ROUGE : l'entree versionnee est absente (%s).\n"
            "  La regenerer sur une machine ou le jeu est installe :\n"
            "  python scripts/python/probe_547r13_keep_on_revive.py --regenerer"
            % p.as_posix())
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        c = line.split("\t")
        if len(c) >= 3 and c[2] != "":
            out[c[0]] = bool(int(c[2]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regenerer", action="store_true")
    ap.add_argument("--runtime", action="store_true",
                    help="2e source : la VTABLE live (PARTIELLE -- classes deja initialisees)")
    a = ap.parse_args()

    print("== #547-r13 -- `IEffect` slot 2 `%s`, par classe d'effet" % GETTER)
    table = deriver()
    if table is None:
        print("REFUS : la derivation offline n'a pas pu conclure (rien n'est devine).")
        return 2

    defaut = table.get(P175.BASE, {}).get("valeur_effective")
    inconnu = sorted(k for k, v in table.items() if v.get("valeur_effective") is None)
    declarants = sorted(k for k, v in table.items() if v.get("declare"))

    print("[3] %d classes ; DEFAUT (`%s`) = %s"
          % (len(table), P175.BASE.rsplit(".", 1)[-1], defaut))
    print("[3] %d classe(s) DECLARENT le getter :" % len(declarants))
    for n in declarants:
        r = table[n]
        print("      %-76s = %s  %s" % (n, r["valeur_propre"], r["source"]))
    if inconnu:
        print("[3] %d classe(s) INDETERMINEE(S) (ni constante ni heritee) :" % len(inconnu))
        for n in inconnu[:10]:
            print("      %-76s %s" % (n, table[n]["source"]))

    repart: dict = {}
    for v in table.values():
        repart[v.get("valeur_effective")] = repart.get(v.get("valeur_effective"), 0) + 1
    print("[3] repartition des valeurs EFFECTIVES : %s"
          % ", ".join("%s=%d" % (k, n)
                      for k, n in sorted(repart.items(), key=lambda kv: (kv[0] is None, kv[0]))))

    # GARDE DE DOMAINE : un booleen ne prend que deux valeurs. Une troisieme voudrait dire que le
    # calage a derape ou que le decodeur ne lit pas ce qu'il croit. On le DIT au lieu de l'ecrire
    # dans une entree versionnee.
    hors = sorted(str(k) for k in repart if k is not None and k not in (True, False))
    if hors:
        print("      ROUGE : valeur(s) HORS du domaine booleen : %s" % ", ".join(hors))
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
            P175.GETTER, P175.DECODEUR = GETTER, P175.decoder_booleen
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
