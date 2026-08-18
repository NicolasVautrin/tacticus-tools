#!/usr/bin/env python
"""#552-r3 -- le slot 4 d'un playbook se lit dans la METADATA, pas dans les tables d'ADRESSES.

LA QUESTION
------------
    << `MindControlPlaybook` surcharge-t-il `ShouldEvaluate` (slot 4 d'`IPlaybook`) ? >>

La fiche `#552-r3` posait la mesure en LIVE : << lire le slot 4 de la vtable sur une instance
materialisee et le comparer a l'adresse de `BasePlaybook$$ShouldEvaluate` >>. C'etait la seule
voie connue, parce que les DEUX tables de symboles (`frida/methods.tsv`, `ghidra/functions.tsv`)
sont indexees par ADRESSE et qu'IL2CPP DEDUPLIQUE les corps : un `ShouldEvaluate` propre dont le
corps est identique a celui d'une autre classe n'y a PAS de ligne. C'est exactement ainsi que le
slot 4 de `VexillaMagnificaPlaybook` avait ete rate puis retrouve LIVE (#46).

LA VOIE QUI TRANCHE, ET POURQUOI ELLE EST IMMUNE A LA DEDUPLICATION
--------------------------------------------------------------------
`global-metadata.dat` ne decrit pas des CORPS, il decrit des DEFINITIONS. Le
`Il2CppTypeDefinition` d'une classe porte `methodStart` / `methodCount` : la liste des methodes
qu'elle DECLARE, que leur code soit partage avec dix autres classes ou non. La deduplication est
un phenomene du LINKER (ICF), posterieur ; elle ne peut rien effacer ici.

`il2cpp_metadata.MetadataReader.type_methods(namespace, nom)` rend cette liste. La reponse a la
question est donc BINAIRE et OFFLINE : `"ShouldEvaluate" in noms_declares(<classe>)`.

⚠ **ET UNE VOIE NEUVE NE VAUT QUE CE QUE VAUT SON TEMOIN.** Un critere qui rendrait `False`
partout donnerait la meme reponse pour `MindControl` -- et serait entierement faux. L'etage 1
confronte donc le critere a HUIT playbooks dont le verdict est deja etabli PAR AILLEURS, DANS LES
DEUX POLARITES, dont trois par une mesure LIVE independante :

    VexillaMagnifica   surcharge     LIVE #46 (slot 4 != BasePlaybook, corps folde HammerOfWrath)
    HammerOfWrath      surcharge     decompile : `!EnemyWillBeKilledWithNormalAttack`
    AlphaWarrior       surcharge     decompile : `GetStat(unit, 0xc = TurnsStarted) > 1`
    NovaCharge         surcharge     #1032-r1 : slot 4 `HasMinimumRemainingTurns(unit, 2)`
    EuphoricStrikes    AUCUNE        LIVE probe_974 : `pbGate(slot 4)` = True a `turnsStarted == 1`
    BlackRage          AUCUNE        decompile : la modulation est dans `GetUseProbability` (0.4)
    ItItches           AUCUNE        decompile : idem
    Waaagh             AUCUNE        #971-r2 : `p = 0.05 x ts x nB`, CONFRONTE live

L'etage 1 exige les huit ET la presence des DEUX polarites : un temoin unilateral ne discrimine
rien (c'est la lecon de `feedback_agreement_in_degenerate_regime_proves_nothing`).

CE QUE CE PROBE NE FAIT PAS
----------------------------
  * il ne lit pas le CORPS du `ShouldEvaluate` qu'il trouve -- il dit qu'il EXISTE, pas ce qu'il
    fait. Porter le corps reste une lecture au decompile ;
  * il ne dit rien de la vtable EFFECTIVE : une classe peut declarer `ShouldEvaluate` sans que ce
    soit le slot 4 d'`IPlaybook` (nom homonyme). Sur les huit temoins, l'appariement est verifie
    par leur verdict independant -- au-dela, c'est une BORNE SUPERIEURE de surcharge ;
  * l'etage 3 est un INVENTAIRE (`#552-r4`), jamais un rouge : il liste les playbooks PORTES ou le
    port et la metadata ne s'accordent pas sur les deux etages du gate. Beaucoup de ces ecarts
    sont des GAPS ASSUMES et documentes (une porte ALEATOIRE que le moteur deterministe ne
    modelise pas) -- les rendre rouges ferait desarmer le cliquet.

Tri-etat : 0 = mesure faite et conforme ; 1 = mesure faite et DIVERGENTE ; 2 = PAS MESURE
(metadata/tables indisponibles) -- jamais rabattu sur un vert.

Usage (100 % offline, aucun runner) :
    python scripts/python/probe_552r3_slot4_declare.py
    python scripts/python/probe_552r3_slot4_declare.py --inventaire   # l'etage 3 en entier
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pin                                                        # noqa: E402
import il2cpp_metadata                                                  # noqa: E402

REPO = HERE.parent.parent

EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/playbook/noncomparable/**/*.py",
                "scripts/python/il2cpp_metadata.py",
                "scripts/python/build_pin.py"),
    "build": True,
    "toujours": False,
    "raison": "Il lit les methodes DECLAREES par des types de `global-metadata.dat` et les "
              "confronte au registre `PLAYBOOKS`. Deux entrees seulement : le BUILD (la metadata "
              "est per-build, et un renumerotage de type change la grille de `locate_types`) et "
              "le paquet NonComparable (l'etage 2 nomme des classes portees, l'etage 3 parcourt "
              "le registre entier).",
}

#: CLASSES CONCRETES qui ancrent la grille des types (memes ancres que `probe_10015`).
ANCRES_TYPES = (
    ("Core.Services", "OperationProcessor"),
    ("IdunBattle.Core.Services", "BattleQuery"),
    ("IdunBattle.Core.Services", "AttackQuery"),
    ("IdunBattle.Core.Services", "MovementQuery"),
    ("IdunBattle.Core.Services", "DamageCalculations"),
    ("IdunBattle.Core", "MatchState"),
)

NS_LOKI = "IdunBattle.AI.Playbook.Loki"

#: `(classe, ShouldEvaluate attendu, GetUseProbability attendu, la SOURCE de l'attente)`.
#: Aucune de ces attentes ne vient de la metadata -- sinon le temoin serait circulaire.
TEMOINS = (
    ("VexillaMagnificaPlaybook", True, False,
     "LIVE #46 : slot 4 resolu a la vtable, != BasePlaybook (corps folde HammerOfWrath)"),
    ("HammerOfWrathPlaybook", True, False,
     "decompile : ShouldEvaluate = !EnemyWillBeKilledWithNormalAttack"),
    ("AlphaWarriorPlaybook", True, False,
     "decompile : ShouldEvaluate = GetStat(unit, 0xc = TurnsStarted) > 1 (corps COMDAT)"),
    ("NovaChargePlaybook", True, True,
     "#1032-r1 : slot 4 propre = HasMinimumRemainingTurns(unit, 2), + GetUseProbability"),
    ("EuphoricStrikesPlaybook", False, False,
     "LIVE probe_974 : pbGate(slot 4) = True alors que turnsStarted == 1 (regime discriminant)"),
    ("BlackRagePlaybook", False, True,
     "decompile : la modulation vit dans GetUseProbability (0.4), pas au slot 4"),
    ("ItItchesPlaybook", False, True,
     "decompile : GetUseProbability propre, slot 4 laisse a la base"),
    ("WaaaghPlaybook", False, True,
     "#971-r2 : GetUseProbability = 0.05 x turnsStarted x nBuffed, CONFRONTE live"),
)

#: Les DEUX verdicts que cette tranche etablit. `None` = << la question ouverte >>, et la reponse
#: attendue est ecrite ici parce qu'elle est DEJA celle que le port rend : le probe est la pour la
#: CONTREDIRE si la metadata dit autre chose.
VERDICTS = (
    ("MindControlPlaybook", 1164, False, False,
     "#552-r3 -- le port laisse le defaut de base (`BasePlaybook$$ShouldEvaluate` -> "
     "`GetUseProbability` = Fix64(1) -> True constant)"),
    ("RevealPlaybook", 1107, False, False,
     "#1033-r2 -- meme defaut, pose au moment du port"),
)


def _mesurer():
    """`(noms_par_classe, refus)`. `refus` non vide => PAS MESURE (jamais un dict vide silencieux)."""
    try:
        meta = build_pin.global_metadata()
    except Exception as exc:                                            # noqa: BLE001
        return None, "metadata introuvable : %s" % exc
    try:
        build = build_pin.versioned_build()
    except Exception as exc:                                            # noqa: BLE001
        return None, "build non epingle : %s" % exc
    methods_tsv = REPO / "data" / "symbols" / build / "frida" / "methods.tsv"
    if not methods_tsv.exists():
        return None, "table absente : %s" % methods_tsv.as_posix()
    try:
        reader = il2cpp_metadata.read(meta)
        reader.locate(il2cpp_metadata.class_method_order(methods_tsv,
                                                         "%s.%s" % ANCRES_TYPES[0]))
        reader.locate_types([(ns, nm,
                              il2cpp_metadata.class_method_order(methods_tsv, "%s.%s" % (ns, nm)))
                             for ns, nm in ANCRES_TYPES])
    except Exception as exc:                                            # noqa: BLE001
        return None, "grille de types non localisee : %s" % exc
    return reader, ""


def noms_declares(reader, plein: str) -> set | None:
    """Les methodes DECLAREES par le type `plein` (nom PLEIN). `None` = type introuvable."""
    ns, _, nm = plein.rpartition(".")
    try:
        tbl = reader.type_methods(ns, nm)
    except Exception:                                                   # noqa: BLE001
        return None
    return {m.name for m in tbl} or None


def _chaine_parents(build: str) -> dict:
    """`{type_plein: parent_plein}`, lu dans `frida/classes.tsv` (colonne 3)."""
    p = REPO / "data" / "symbols" / build / "frida" / "classes.tsv"
    out = {}
    if not p.exists():
        return out
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#!"):
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3 and c[0] and "<" not in c[0]:
                out.setdefault(c[0], c[2])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--inventaire", action="store_true",
                    help="imprime l'etage 3 en entier (l'inventaire #552-r4)")
    args = ap.parse_args(argv)

    reader, refus = _mesurer()
    if reader is None:
        print("[552r3] PAS MESURE -- %s" % refus)
        return EX_PAS_MESURE
    build = build_pin.versioned_build()
    print("[552r3] build epingle : %s" % build)

    ko = 0

    # -------------------------------------------------------------- ETAGE 1 : LE TEMOIN
    print("\n[552r3] ETAGE 1 -- le critere reproduit-il les verdicts DEJA etablis ?")
    avec = sans = 0
    for cls, att_se, att_gp, src in TEMOINS:
        noms = noms_declares(reader, "%s.%s" % (NS_LOKI, cls))
        if noms is None:
            print("   %-30s PAS MESURE (type introuvable dans la metadata)" % cls)
            return EX_PAS_MESURE
        se, gp = "ShouldEvaluate" in noms, "GetUseProbability" in noms
        bon = (se == att_se) and (gp == att_gp)
        avec += 1 if att_se else 0
        sans += 0 if att_se else 1
        print("   %-30s SE=%-5s GUP=%-5s  %s   (%s)"
              % (cls, se, gp, "OK" if bon else "DIVERGENCE", src))
        if not bon:
            ko += 1
    if avec < 3 or sans < 3:
        print("   ECHEC : le temoin est UNILATERAL (%d surchargeants, %d non) -- un critere qui "
              "rendrait toujours la meme reponse le passerait." % (avec, sans))
        ko += 1
    else:
        print("   temoin BILATERAL : %d surchargeants / %d non -- le critere discrimine." % (avec, sans))

    # -------------------------------------------------------------- ETAGE 2 : LES VERDICTS
    print("\n[552r3] ETAGE 2 -- le verdict des classes de la tranche")
    for cls, aid, att_se, att_gp, quoi in VERDICTS:
        noms = noms_declares(reader, "%s.%s" % (NS_LOKI, cls))
        if noms is None:
            print("   %-30s PAS MESURE" % cls)
            return EX_PAS_MESURE
        se, gp = "ShouldEvaluate" in noms, "GetUseProbability" in noms
        bon = (se == att_se) and (gp == att_gp)
        print("   %-30s (%d) declare %s" % (cls, aid, sorted(noms)))
        print("       ShouldEvaluate=%-5s GetUseProbability=%-5s -> %s"
              % (se, gp, "OK" if bon else "DIVERGENCE"))
        print("       %s" % quoi)
        if not bon:
            print("       => LE PORT DOIT CHANGER : le natif porte un etage que le port n'a pas.")
            ko += 1

    # -------------------------------------------------------------- ETAGE 3 : L'INVENTAIRE
    from engine.playbook.noncomparable import PLAYBOOKS
    from engine.playbook.noncomparable._base import NonComparablePlaybook
    parents = _chaine_parents(build)
    court = {}
    for full in parents:
        court.setdefault(full.rsplit(".", 1)[-1], []).append(full)
    ecarts, sans_natif = [], []
    for aid, pb in sorted(PLAYBOOKS.items()):
        cls = type(pb).__name__
        cands = [c for c in court.get(cls, []) if ".Playbook" in c]
        if not cands:
            sans_natif.append((aid, cls))
            continue
        chaine, cur, vus = [], cands[0], set()
        while cur and cur not in vus and cur != "System.Object":
            vus.add(cur)
            chaine.append(cur)
            cur = parents.get(cur)
        # `BasePlaybook` porte les DEFAUTS : les y trouver n'est pas une surcharge.
        nat_se = any("ShouldEvaluate" in (noms_declares(reader, c) or set())
                     for c in chaine if not c.endswith("BasePlaybook"))
        nat_gp = any("GetUseProbability" in (noms_declares(reader, c) or set())
                     for c in chaine if not c.endswith("BasePlaybook"))
        port_se = type(pb).should_evaluate is not NonComparablePlaybook.should_evaluate
        port_gp = type(pb).use_probability is not NonComparablePlaybook.use_probability
        if (nat_se, nat_gp) != (port_se, port_gp):
            ecarts.append((aid, cls, port_se, port_gp, nat_se, nat_gp))
    print("\n[552r3] ETAGE 3 -- INVENTAIRE `#552-r4` (jamais un rouge)")
    print("   playbooks portes : %d ; sans natif homonyme : %d ; ecarts port/natif : %d"
          % (len(PLAYBOOKS), len(sans_natif), len(ecarts)))
    montre = ecarts if args.inventaire else ecarts[:6]
    for aid, cls, pse, pgp, nse, ngp in montre:
        print("      %-5d %-34s port(SE=%-5s GUP=%-5s) natif(SE=%-5s GUP=%-5s)"
              % (aid, cls, pse, pgp, nse, ngp))
    if not args.inventaire and len(ecarts) > len(montre):
        print("      ... %d de plus (`--inventaire`)" % (len(ecarts) - len(montre)))
    print("   Beaucoup de ces ecarts sont des GAPS ASSUMES et documentes au site (porte "
          "ALEATOIRE non modelisee par un moteur deterministe). Les rendre rouges ferait "
          "desarmer le cliquet -- ils sont a LIRE un par un, c'est `#552-r4`.")

    print("\n[552r3] PORTEE DE LA MESURE -- ce que ce probe ne voit pas")
    print("   * le CORPS du `ShouldEvaluate` trouve (il dit qu'il existe, pas ce qu'il fait) ;")
    print("   * l'appariement declaration -> slot 4 d'`IPlaybook` (borne SUPERIEURE hors temoins) ;")
    print("   * les playbooks NON PORTES : ils ne sont dans aucun des trois etages.")
    print("\n[552r3] VERDICT : %s" % ("OK" if ko == 0 else "FAIL (%d)" % ko))
    return EX_VERT if ko == 0 else EX_ROUGE


if __name__ == "__main__":
    sys.exit(main())
