"""#271-r7 -- les slots d'`IdunBattle.AI.Utilities.IUtility`, LUS dans le `global-metadata.dat`.

    python scripts/python/probe_271r7_iutility_slots.py

POURQUOI CE PROBE EXISTE. La face REPAIR du dispatcher non-owner delegue a
`<utilitiesDatabase>.GetUtility(0x30 = UtilityType.RepairedAmount, 0).<slot 6>(case)`, et
`IUtility` ne figure PAS dans `data/symbols/<build>/metadata/interface_slots.tsv` : le canal
n'etait << pas etabli >>, d'ou le `BLOCAGE: etage` du residu. Ce probe l'etablit par la MEME
machinerie que `probe_477r25_slots_autres_interfaces.py` -- `il2cpp_metadata.locate_types` designe
la table par le TYPE (pas par des ancres de nom), donc aucune ambiguite d'interface.

TRI-ETAT : metadata absent ou desynchronise -> `PAS MESURE` (rc 99), jamais un zero ni un vert.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pin                                                            # noqa: E402
import il2cpp_metadata                                                      # noqa: E402
from probe_477r25_slots_autres_interfaces import ANCRES_TYPES               # noqa: E402
from symbols_layout import build_dir, current_build                         # noqa: E402

#: L'interface cherchee et le CONTROLE : les noms qu'on doit retrouver, et a quels slots.
#: Ils viennent de la DECLARATION Il2CppDumper (`sources_win`, dump d'un AUTRE build) -- ce probe
#: les CONFRONTE au metadata du build courant, il ne les recopie pas.
#: ⚠ MESURE du 2026-08-15 : `t6dpr4k06g` porte un slot **9** de PLUS (`CalculateMovementModifier`)
#: que le dump. Les slots 0..8 sont IDENTIQUES. Un slot AJOUTE en queue de table est donc traite
#: comme une information, pas comme un ecart -- c'est un ecart de BUILD, pas de lecture. Un slot
#: 0..8 qui DIVERGE, lui, fait rougir.
ATTENDU = {0: "Init", 1: "EvaluateAttackInSteps", 2: "EvaluateRepairInSteps",
           3: "EvaluateMovementInSteps", 4: "EvaluateUnitInSteps", 5: "EvaluateAttack",
           6: "EvaluateRepair", 7: "CalculateAttackModifier", 8: "EvaluateMovement"}

#: LE SLOT QUE CE RESIDU CHERCHE, et sa signature.
SLOT_CIBLE, NOM_CIBLE = 6, "EvaluateRepair"


def main() -> int:
    try:
        meta = Path(build_pin.global_metadata())
    except Exception as exc:                                                # noqa: BLE001
        print("PAS MESURE : global-metadata introuvable (%s)" % exc)
        return 99
    build = current_build()
    methods_tsv = build_dir(build) / "frida" / "methods.tsv"
    if not methods_tsv.is_file():
        print("PAS MESURE : %s absent" % methods_tsv)
        return 99
    reader = il2cpp_metadata.read(meta)
    reader.locate(il2cpp_metadata.class_method_order(methods_tsv, "%s.%s" % ANCRES_TYPES[0]))
    # MEME appel que `probe_477r25` : chaque ancre porte l'ORDRE de ses methodes, qui est ce qui
    # cale la grille `Il2CppTypeDefinition`.
    reader.locate_types([(ns, nm, il2cpp_metadata.class_method_order(methods_tsv, "%s.%s" % (ns, nm)))
                         for ns, nm in ANCRES_TYPES])
    methodes = reader.type_methods("IdunBattle.AI.Utilities", "IUtility")
    if not methodes:
        print("PAS MESURE : IUtility introuvable dans le metadata de %s" % build)
        return 99
    print("build %s -- IdunBattle.AI.Utilities.IUtility : %d methode(s)" % (build, len(methodes)))
    lus = {}
    for m in methodes:
        lus[m.slot] = m.name
        print("  slot %-3d %-28s param_count=%s" % (m.slot, m.name, m.param_count))
    ecarts = [(s, n, ATTENDU[s]) for s, n in sorted(lus.items())
              if s in ATTENDU and ATTENDU[s] != n]
    manquants = sorted(set(ATTENDU) - set(lus))
    ajoutes = sorted(s for s in lus if s not in ATTENDU)
    if ajoutes:
        print("\nSLOTS AJOUTES par ce build (ecart de BUILD, pas de lecture) : %r"
              % [(s, lus[s]) for s in ajoutes])
    if ecarts or manquants:
        print("\nECART sur les slots 0..8 : %r ; slots absents : %r" % (ecarts, manquants))
        return 1
    if lus.get(SLOT_CIBLE) != NOM_CIBLE:
        print("\nECART : slot %d = %r, attendu %r" % (SLOT_CIBLE, lus.get(SLOT_CIBLE), NOM_CIBLE))
        return 1
    print("\nCONCORDANT avec la declaration Il2CppDumper sur les %d slots communs." % len(ATTENDU))
    print("=> `IUtility` slot %d = `%s(UtilityAttackCase) -> Fix64` : le canal de la face REPAIR "
          "non-owner est ETABLI (le `BLOCAGE: etage` de #271-r7 est REFUTE)."
          % (SLOT_CIBLE, NOM_CIBLE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
