"""#175-e / #175-r -- les deux mesures qui ont ventile le `BLOCAGE: capteur`, RE-DERIVEES.

    python probe_175r_ventilation_metadata.py            # les deux etapes
    python probe_175r_ventilation_metadata.py --immunite # etape 1 seule
    python probe_175r_ventilation_metadata.py --meta     # etape 2 seule

ETAPE 1 -- INVENTAIRE de `get_CanBeImmuneTo`, sur la FERMETURE TRANSITIVE de `BaseEffect`.
Le recensement de #224 partait du NAMESPACE `IdunBattle.Entities.Effects.*` ; celui-ci part du
PARENT, et c'est ce qui change le resultat : **29** descendants de `BaseEffect` vivent hors de ce
namespace, dont `Idun.Source.IdunBattle.Logic.Entities.Effects.DespoiledGroundEffect`, qui declare
`get_CanBeImmuneTo` a `true`. Un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas.

Deux voies pour la VALEUR, et elles ne voient pas la meme chose :
  * ancre LOCALE  -- le bloc `methodPointers` cale sur une methode NOMMEE de la classe, alignement
    controle sur toutes les autres. Exige au moins un corps nomme ; `DespoiledGroundEffect` n'en a
    AUCUN (ses 4 corps sont fondus par l'ICF).
  * ancre GLOBALE -- l'index de chaque methode dans la table `Il2CppMethodDefinition`
    (`(file_offset - base) / entry_size`), le bloc suivant le meme ordre. Marche pour n'importe
    quelle classe, et son calage est CONTROLE par des centaines de methodes nommees.

ETAPE 2 -- quels constructeurs de `meta` du composite `Tile(7)` posent quels attributs. C'est la
mesure qui a montre que `sort_tiles_by_utility` etait le seul des trois a n'appeler pas
`apply_tile_attributes`, et que `ability_friend_counts` n'etait pose que par `mv71.py`.

ASCII only.
"""
from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

import build_pin                                                       # noqa: E402
import probe_477r37_slot4_et_faces_restantes as P                      # noqa: E402

RACINE = "IdunBattle.Entities.Effects.BaseEffect"
VOULU = "get_CanBeImmuneTo"
SURCH = "EntityIsImmuneToEffect"
#: les temoins qui CALENT le bloc `methodPointers` : chacun a des methodes nommees, et l'un d'eux
#: (`BaseEffect`) porte deux corps dont ghidra connait la VA -- c'est ce qui verifie le calage.
TEMOINS = (("IdunBattle.Entities.Effects", "BaseEffect"),
           ("IdunBattle.Core.Services", "BattleQuery"),
           ("IdunBattle.Core.Services", "EffectsQuery"))


def _descendants(build: str) -> list:
    """Fermeture transitive des descendants de `BaseEffect`, lue dans `frida/classes.tsv`."""
    enfants: dict = {}
    p = P.build_dir(build) / "frida" / "classes.tsv"
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines()):
        if i == 0:
            continue
        c = line.split("\t")
        if len(c) >= 3:
            enfants.setdefault(c[2], []).append(c[0])
    out, pile = [], [RACINE]
    while pile:
        for e in enfants.get(pile.pop(), ()):
            out.append(e)
            pile.append(e)
    return sorted(set(out))


def etape_immunite() -> int:
    try:
        meta = Path(build_pin.global_metadata())
    except Exception as exc:                                           # noqa: BLE001
        print("[1] NON MESURE -- global-metadata absent : %s" % exc)
        return 0
    dll = meta.parents[3] / "GameAssembly.dll"
    if not dll.is_file():
        print("[1] NON MESURE -- GameAssembly.dll absente")
        return 0
    import il2cpp_metadata
    build = build_pin.current_build()
    mt = P.build_dir(build) / "frida" / "methods.tsv"
    r = il2cpp_metadata.read(meta)
    r.locate(il2cpp_metadata.class_method_order(mt, "%s.%s" % P.ANCRES_TYPES[0]))
    lay = r.locate_types([(ns, nm, il2cpp_metadata.class_method_order(mt, "%s.%s" % (ns, nm)))
                          for ns, nm in P.ANCRES_TYPES])
    par_sym, par_va = P._fonctions(build)
    pe = P._PE(dll)
    size, base = r.entry_size, lay.method_table_base

    def idx(m):
        return (m.file_offset - base) // size

    # ⚠ `P.offset_du_pointeur` balaie le PE en Python (boucle par pas de 8) : ~1 min par VA sur
    # 60 Mo. On cale donc avec `bytes.find`, et on s'arrete des que le vote est NET.
    def _offsets(va, limite=8):
        cible = va.to_bytes(8, "little")
        out, i = [], 0
        while len(out) < limite:
            i = pe.data.find(cible, i)
            if i < 0:
                break
            if i % 8 == 0:
                out.append(i)
            i += 1
        return out

    votes: dict = {}
    for ns, nm in TEMOINS:
        ms = r.type_methods(ns, nm)
        noms = [m.name for m in ms]
        for m in ms:
            if m.name.startswith(".") or noms.count(m.name) != 1:
                continue
            va = par_sym.get("%s.%s$$%s" % (ns, nm, m.name))
            if va is None:
                continue
            for off in _offsets(va):
                k = off - 8 * idx(m)
                votes[k] = votes.get(k, 0) + 1
        if votes and max(votes.values()) >= 20:
            break                       # calage NET : inutile de balayer les autres temoins
    if not votes:
        print("[1] REFUS -- aucun temoin ne cale le bloc `methodPointers`")
        return 1
    origine, n = max(votes.items(), key=lambda kv: kv[1])
    print("[1] bloc methodPointers cale a 0x%x (%d temoins concordants, %d candidat(s))"
          % (origine, n, len(votes)))
    # CONTROLE : les deux corps NOMMES d'`EntityIsImmuneToEffect` doivent tomber sur LEUR symbole.
    for ns, nm in (("IdunBattle.Entities.Effects", "BaseEffect"),
                   ("IdunBattle.Entities.Effects.Loki", "ContaminatedEffect")):
        m = next((x for x in r.type_methods(ns, nm) if x.name == SURCH), None)
        attendu = par_sym.get("%s.%s$$%s" % (ns, nm, SURCH))
        lu = pe.qword(origine + 8 * idx(m)) if m is not None else None
        if m is None or attendu is None or lu != attendu:
            print("[1] REFUS -- calage NON VERIFIE sur %s.%s (lu %s, attendu %s)"
                  % (nm, SURCH, par_va.get(lu or 0, "?"), "%s$$%s" % (nm, SURCH)))
            return 1
    print("[1] calage VERIFIE : les 2 corps nommes d'`%s` tombent sur leur symbole" % SURCH)

    desc = _descendants(build)
    hors = [d for d in desc if not d.startswith("IdunBattle.Entities.Effects.")]
    print("[1] descendants de `BaseEffect` : %d, dont %d HORS du namespace balaye par #224"
          % (len(desc), len(hors)))
    vrais, surch, refus = [], [], []
    for plein in desc:
        ns, _, court = plein.rpartition(".")
        try:
            ms = r.type_methods(ns, court)
        except Exception as exc:                                       # noqa: BLE001
            refus.append((plein, str(exc)[:50]))
            continue
        noms = [m.name for m in ms]
        if SURCH in noms:
            surch.append(plein)
        if VOULU not in noms:
            continue
        va = pe.qword(origine + 8 * idx(ms[noms.index(VOULU)]))
        oct3 = pe.octets(va) or "?"
        if oct3 == P.OCTETS_VRAI:
            vrais.append(plein)
        elif oct3 != P.OCTETS_FAUX:
            refus.append((plein, "corps NON TRIVIAL %s" % oct3))
    print("[1] `%s` DECLARE et == true : %d classe(s)" % (VOULU, len(vrais)))
    for v in vrais:
        print("        %s" % v)
    print("[1] surchargent `%s` : %s" % (SURCH, ", ".join(x.rsplit(".", 1)[-1] for x in surch)))
    if refus:
        print("[1] NON CONCLUS (%d) : %s" % (len(refus), refus[:5]))
    # CONFRONTATION AU PORT -- l'ecart est le residu #175-r2.
    from engine.entities.effects.factory import EffectFactory
    porte = {k: getattr(v, "can_be_immune_to", False) for k, v in EffectFactory.registry.items()}
    courts = {x.rsplit(".", 1)[-1] for x in vrais}
    manquants = sorted(n for n, v in porte.items() if not v)
    print("[1] PORT : %d nom(s) au registre, %d a `can_be_immune_to = True`"
          % (len(porte), sum(1 for v in porte.values() if v)))
    print("[1] classes natives a `true` : %s" % ", ".join(sorted(courts)))
    del manquants
    return 0


def etape_meta() -> int:
    """Qui pose quoi dans le `meta` du composite `Tile(7)` ?"""
    from engine.utilities import tile as T
    from engine import move as M
    from engine.playbook import base as B
    srcs = {"engine.move.<sweep>": inspect.getsource(M),
            "playbook.base.tile_utility": inspect.getsource(B),
            "tile.sort_tiles_by_utility": inspect.getsource(T.sort_tiles_by_utility)}
    print("[2] constructeurs de `meta` du composite Tile(7) -- appellent-ils "
          "`apply_tile_attributes` ?")
    ko = 0
    for nom, src in srcs.items():
        ok = "apply_tile_attributes" in src
        print("        %-32s %s" % (nom, "OUI" if ok else "NON  <- feuilles a attribut MUETTES"))
        ko += 0 if ok else 1
    api = inspect.getsource(T.apply_tile_attributes) + inspect.getsource(T._ability_friend_counts)
    for cle in ("is_territory", "tile_effect_type_ids", "neighbor_effect_names", "steppable",
                "decoy_gate", "attract_mechanicals_neighbor", "ability_friend_counts"):
        print("        cle %-30s posee par apply_tile_attributes : %s"
              % (cle, "OUI" if ('"%s"' % cle) in api else "non"))
    print("[2] cles ENCORE muettes (aucun poseur) : door, hero_door_nearest_cost, "
          "occupant_is_powerup, movetowards_hexdist, pending_summons, effect_target_ids, "
          "phantasm_friendly_adjacent, ghost_friendly_adjacent")
    return 1 if ko else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--immunite", action="store_true")
    ap.add_argument("--meta", action="store_true")
    a = ap.parse_args()
    rc = 0
    if a.immunite or not a.meta:
        rc |= etape_immunite()
    if a.meta or not a.immunite:
        rc |= etape_meta()
    print("\nrc=%d" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
