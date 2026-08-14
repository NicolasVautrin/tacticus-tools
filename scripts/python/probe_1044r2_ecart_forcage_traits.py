#!/usr/bin/env python
"""probe #1044-r2 -- CHIFFRER l'ecart entre le substrat de REPLI du port et le forcage natif.

Le residu nommait l'ecart sans le mesurer : `engine/entities/traits/unit_trait.py::unit_trait_names`
rend les traits du GAMECONFIG (+ le pseudo-trait de grande-alliance) et ne sait rien
d'`IdunBattle.Operations.AddUnitOperation$$AddUnitTypeTraits`. Ce repli n'est consulte que si
`ctx.traits_measured` est faux -- donc l'ecart est INVISIBLE tant que la mesure existe, exactement
le regime ou personne ne le verra se creuser.

LE FORCAGE, LU (`rnca9r7q6c`) -- les DEUX surcharges.

`AddUnitTypeTraits(this, unitComponent, unitOverrideType)` (3 args) ecrit exactement UN des trois
traits et RETIRE les deux autres, sur la collection `BaseUnitComponent+0x40` :

    Hero   (0) : Add(0x10 = 16 Hero)   Remove(0x7e6 = 2022 NPC)  Remove(2 Summon)
    NPC    (1) : Remove(16 Hero)       Add(2022 NPC)             Remove(2 Summon)
    Summon (2) : Remove(16 Hero)       Remove(2022 NPC)          Add(2 Summon)

Les trois ordinaux sont QUALIFIES sur le mirror `UnitTrait`, jamais deduits du contexte.

`AddUnitTypeTraits(this, unit, options, hasParent)` (4 args) choisit lequel :

    heroDeDroit = !hasParent && !Contains(coll, 2022 NPC) && !Contains(coll, 2 Summon)
    ov = options.<Nullable<UnitOverrideType> @+0x8>
    if (ov.HasValue && ov.Value == 2) -> Summon
    elif (ov.HasValue && ov.Value == 1) -> NPC
    elif ((ov.HasValue && ov.Value == 0) || heroDeDroit) -> Hero
    else -> RETURN 0, c'est-a-dire AUCUNE ecriture

⇒ EN REGIME SANS OVERRIDE -- le seul atteignable depuis la BC (`#1044-r1`) -- le forcage se REDUIT
a une seule regle : une unite SANS parent qui ne porte NI `NPC` NI `Summon` dans ses traits de
depart GAGNE `Hero` ; toute autre unite est laissee INTACTE (`return 0`). Les deux `Remove` de la
branche Hero sont alors des no-op par construction, puisque `heroDeDroit` exige deja leur absence.

CE QUE CE PROBE MESURE, sur les unites du seed BC (`data/seed-bc.json`) :

  [A] combien GAGNERAIENT `Hero` -- l'ecart reel, celui qui fait le verdict ;
  [B] combien PERDRAIENT `NPC` / `Summon` -- attendu STRUCTURELLEMENT nul en regime sans override,
      et c'est le controle : un non-zero voudrait dire que la lecture du natif est fausse ;
  [C] la part de l'ecart que le repli VOIT DEJA (l'unite a `Hero` dans son kit gameconfig) -- sans
      elle, [A] confondrait << le forcage ajoute Hero >> et << le port ignore Hero >>.

⚠ DEUX SUBSTRATS, ET ILS NE SONT PAS LE MEME. Le natif part de `BC.Units[].Traits` (ce que
`IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` pose dans `+0x40`) ; le repli part
du `traits` du GAMECONFIG. Les confondre est deja documente comme faux -- `entity_trait_names`
mesure 5 unites avec MOINS de traits que leur kit et 48 avec PLUS. Ce probe imprime donc les DEUX
lectures et ne collapse jamais l'une sur l'autre.

Usage (offline pur, aucun runner, aucune session Frida) :
    python probe_1044r2_ecart_forcage_traits.py [--detail]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from engine.entities.traits.unit_trait import UnitTrait          # noqa: E402

SEED_BC = PYDIR.parent.parent / "data" / "seed-bc.json"

#: Les trois traits que `AddUnitTypeTraits` arbitre. Ordinaux LUS au decompile puis QUALIFIES sur
#: le mirror -- `0x10`, `2`, `0x7e6`.
HERO = UnitTrait.Hero        # 0x10 = 16
SUMMON = UnitTrait.Summon    # 2
NPC = UnitTrait.NPC          # 0x7e6 = 2022


def add_unit_type_traits(traits: set, has_parent: bool, override=None) -> set | None:
    """Mirror 1:1 des DEUX surcharges. Rend le NOUVEL ensemble, ou `None` pour le `return 0` natif
    (aucune ecriture).

    ⚠ ON TRAVAILLE EN **NOMS**, et c'est une contrainte du SUBSTRAT, pas un choix de confort : le
    natif compare des ORDINAUX (`0x10`, `2`, `0x7e6`) sur la collection `BaseUnitComponent+0x40`,
    mais `BC.Units[].Traits` de la capture JSON porte des CHAINES (`"Imperial"`, ...). Le pont est
    le mirror `UnitTrait`, dont le nom de membre EST le nom gameconfig -- la meme equivalence sur
    laquelle repose deja tout `engine/entities/traits/unit_trait.py`. Comparer un ordinal a cette
    liste rendrait TOUJOURS faux, sans erreur : c'est exactement la classe de bug de #135."""
    if override is None:
        hero_de_droit = (not has_parent) and (NPC.name not in traits) and (SUMMON.name not in traits)
        if not hero_de_droit:
            return None                       # `return 0` : le natif n'ecrit RIEN
        override = int(HERO)
    out = set(traits)
    for t, pose in ((HERO, override == int(HERO)),
                    (NPC, override == int(NPC)),
                    (SUMMON, override == int(SUMMON))):
        out.add(t.name) if pose else out.discard(t.name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true", help="lister les unites de chaque categorie")
    a = ap.parse_args()

    if not SEED_BC.exists():
        print("[1044-r2] seed BC ABSENT : %s -- rien mesure (ce n'est PAS un zero)" % SEED_BC)
        return 2
    bc = json.loads(SEED_BC.read_text(encoding="utf-8"))
    units = bc.get("Units") or []
    if not units:
        print("[1044-r2] `BC.Units[]` VIDE -- rien mesure (ce n'est PAS un zero)")
        return 2

    import gameconfig as GC

    gagnent, perdent, deja_hero_kit, intactes, deja_hero_bc = [], [], [], [], []
    #: [D] LE POINT QUI DECIDE. Le forcage ne depend, en regime sans override, que d'une question :
    #: << l'unite porte-t-elle `NPC` ou `Summon` au depart ? >>. Le repli, lui, ne dispose PAS de
    #: `BC.Units[].Traits` -- il ne voit que le kit gameconfig. Porter le forcage cote repli
    #: reviendrait donc a repondre a cette question sur le KIT. On mesure ici si les deux substrats
    #: rendent le MEME verdict : c'est ce qui separe << portable >> de << borne a nommer >>.
    divergents = []
    for u in units:
        uid = str(u.get("Id") or "")
        vis = str(u.get("VisualId") or uid.split(":")[0])
        depart = {str(t) for t in (u.get("Traits") or []) if t is not None}
        # `hasParent` = l'unite est-elle INVOQUEE ? Aucune entree de `BC.Units[]` n'a de parent :
        # un summon n'existe qu'apres `SpawnUnitOperation`, il n'est pas dans la BC. On le pose donc
        # FAUX et on le DIT, plutot que de deviner un champ qui n'existe pas.
        apres = add_unit_type_traits(depart, has_parent=False)
        kit = {str(x) for x in ((GC.unit(vis) or {}).get("traits") or ())}
        # [D] le MEME forcage, evalue sur le substrat que le repli possede REELLEMENT (le kit).
        apres_kit = add_unit_type_traits(kit, has_parent=False)
        if (apres is None) != (apres_kit is None):
            divergents.append((uid, vis, "BC:%s kit:%s"
                               % ("ecrit" if apres else "return0",
                                  "ecrit" if apres_kit else "return0")))
        if apres is None:
            intactes.append((uid, vis))
            continue
        if HERO.name in depart:
            deja_hero_bc.append((uid, vis))        # forcage = no-op : `Hero` etait deja la
        else:
            (deja_hero_kit if HERO.name in kit else gagnent).append((uid, vis))
        perdus = {t for t in (NPC.name, SUMMON.name) if t in depart and t not in apres}
        if perdus:
            perdent.append((uid, vis, sorted(perdus)))

    n = len(units)
    print("[1044-r2] ECART DU SUBSTRAT DE REPLI -- forcage `AddUnitTypeTraits`, regime SANS override")
    print("   %d unite(s) dans `BC.Units[]` de %s" % (n, SEED_BC.name))
    print("   [A] GAGNENT `Hero` et le repli NE LE VOIT PAS (absent du kit gameconfig) : %d"
          % len(gagnent))
    print("   [C] gagnent `Hero` mais le repli le voit DEJA (present au kit)          : %d"
          % len(deja_hero_kit))
    print("   [B] PERDRAIENT `NPC` / `Summon`                                          : %d"
          % len(perdent))
    print("       (attendu STRUCTURELLEMENT 0 : `heroDeDroit` exige deja leur absence --")
    print("        un non-zero accuserait la LECTURE du natif, pas le port)")
    print("       deja `Hero` au depart, forcage = NO-OP                               : %d"
          % len(deja_hero_bc))
    print("   INTACTES (`return 0` natif, aucune ecriture)                             : %d"
          % len(intactes))
    somme = len(gagnent) + len(deja_hero_kit) + len(deja_hero_bc) + len(intactes)
    print("   PARTITION EXHAUSTIVE : %d + %d + %d + %d = %d / %d %s"
          % (len(gagnent), len(deja_hero_kit), len(deja_hero_bc), len(intactes), somme, n,
             "OK" if somme == n else "<< INCOMPLETE : une categorie manque >>"))
    print("   [D] LE POINT QUI DECIDE -- meme forcage evalue sur le KIT (le seul substrat que le")
    print("       repli possede) vs sur `BC.Units[].Traits` : %d verdict(s) DIVERGENT(S)"
          % len(divergents))
    if divergents:
        for row in divergents[:20]:
            print("       %s" % (row,))
        if len(divergents) > 20:
            print("       ... %d de plus" % (len(divergents) - 20))
    if a.detail:
        for lib, lot in (("[A] gagnent Hero, invisible du repli", gagnent),
                         ("[C] gagnent Hero, deja au kit", deja_hero_kit),
                         ("[B] perdent NPC/Summon", perdent)):
            print("   --- %s (%d) ---" % (lib, len(lot)))
            for row in lot[:40]:
                print("       %s" % (row,))
            if len(lot) > 40:
                print("       ... %d de plus" % (len(lot) - 40))
    print("   PORTEE : `hasParent` est pose FAUX pour toutes -- aucune entree de `BC.Units[]` n'est")
    print("   une unite INVOQUEE (un summon naquit de `SpawnUnitOperation`, apres la BC). Le regime")
    print("   `hasParent = true` n'est donc PAS mesure ici, et il n'est pas atteignable par ce")
    print("   substrat. L'axe OVERRIDE ne l'est pas davantage depuis la BC (residu #1044-r1).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
