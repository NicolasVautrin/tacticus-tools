"""#1078-r1 -- le volet MONO-ID `UnitsWithId` compare-t-il ce que le natif compare ?

`IdunBattle.Entities.Selectors.UnitsWithIdSelector$$Select` filtre sa source par
`IdunBattle.Entities.UnitExtensions$$HasUnitId(unit, id, state)` =
`UnitNamingConventions.GetUnitIdWithoutRarity(GetUnitId(unit)) == id`, ou
`IdunBattle.Entities.UnitExtensions$$GetUnitId` lit le champ **+0x10** du composant d'identite
(l'id de CONFIG) -- PAS la `VisualId`, qui vit a +0x20 et qui est le seul des deux qu'un canal
live publie. Le volet MULTI-ID (`selectors/units.py::UnitsWithIds`) etait passe par le foyer
`has_unit_id` des #1078 ; le volet MONO-ID (`selectors/geometry.py::UnitsWithId`) comparait
encore `visualId` directement -- alors que c'est LE MEME selecteur natif.

QUATRE etapes, toutes OFFLINE (aucun runner, aucun RPC) :
  0. le foyer est UNIQUE et l'import est de niveau MODULE (forme A) : `selectors/units.py`
     n'importe PAS `geometry`, donc il n'y a pas de cycle a differer -- c'est MESURE en
     chargeant `engine.entities.selectors.units` seul dans un process frais ;
  1. le noeud `UnitsWithId` APPELLE bien `has_unit_id` (et plus une egalite de `visualId`) ;
  2. RAYON DE SOUFFLE : les `unitId` LUS aux call-sites executables x tous les `visualId` que
     le gameconfig peut presenter -> le nombre de verdicts qui changent, et LEUR SENS ;
  3. NON-REGRESSION structurelle : pour chaque `unitId` de call-site, une unite SPAWNEE (dont
     le `visualId` porte l'id de CONFIG) reste matchee.

L'etape 2 est le cliquet qui compte : elle rougit si un futur call-site (ou un changement de
gameconfig) fait apparaitre un verdict `True -> False`, c'est-a-dire une unite que le port
cessait de compter. Un `False -> True` est, lui, attendu et NOMME.

Usage : python probe_1078r1_units_with_id_mono.py     (depuis scripts/python)
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gameconfig as GC                                                    # noqa: E402
from engine.entities.selectors.geometry import UnitsWithId                 # noqa: E402
from engine.entities.selectors.units import _config_ids_presenting, has_unit_id   # noqa: E402


#: Les `unitId` LUS aux call-sites EXECUTABLES du noeud mono-id -- (etiquette, id d'ability,
#: cle de constante). Le probe les RESOUT contre le gameconfig ; rien n'est fige ici.
SITES = (
    ("CultDemagogue / decoys",   "CultDemagogue",    "unitId"),
    ("CultDemagogue / neophytes", "CultDemagogue",   "unitId_2"),
    ("EcogSupport",              "EcogSupport",      "unitId"),
    ("GeminaeSuperia",           "GeminaeSuperia",   "unitId"),
    ("TheArdentBlade",           "TheArdentBlade",   "unitId"),
    ("SynapticLinchpin",         "SynapticLinchpin", "unitId"),
    ("SwornProtector",           "SwornProtector",   "unitId"),
    ("BookOfFate",               "BookOfFate",       "affectedUnitId"),
)

#: Les verdicts `False -> True` ATTENDUS, mesures le 2026-08-15 sur `t6dpr4k06g`. Chacun est un
#: summon dont le npc homonyme partage le `visualId` : la source de ces deux call-sites est
#: `DSLSelectors$$Children(owner)`, donc seul le summon peut s'y trouver.
ATTENDUS = {
    ("tyranNpc1Hormagaunt", "tyranSmnHormagaunt"),
    ("votanNpc1Ecog", "votanSmnEcog"),
}


def _const(ability_id: str, key: str):
    return ((GC.ability(ability_id) or {}).get("constants") or {}).get(key)


def etape0_import_isole() -> list:
    """L'arete `geometry -> units` est-elle GRATUITE (hissable en forme A) ou PORTEUSE ?

    ⚠ LE CRITERE « charger X seul et regarder si M atterrit dans `sys.modules` » EST DEGENERE
    POUR UNE ARETE INTRA-PAQUET, et le mesurer l'a montre : importer
    `engine.entities.selectors.units` fait bien atterrir `geometry`, mais par
    `engine/entities/selectors/__init__.py` (le BARIL du paquet, qui re-exporte les deux) --
    pas par une arete `units -> geometry`. Applique tel quel, le critere classerait PORTEUSE
    toute arete entre deux modules d'un meme paquet a baril, et ferait differer pour rien.

    Le critere qui discrimine, ici, est en DEUX volets :
      (a) chaque module s'importe SEUL dans un process frais (l'invariant 430/430) ;
      (b) `units.py` ne porte AUCUN import de `geometry` -- lu dans l'AST au niveau MODULE
          comme dans les corps de fonction, donc un differe compterait aussi.
    """
    import ast

    ko = []
    ici = os.path.dirname(os.path.abspath(__file__))
    for mod in ("engine.entities.selectors.geometry", "engine.entities.selectors.units"):
        r = subprocess.run([sys.executable, "-c", "import %s" % mod],
                           capture_output=True, text=True, cwd=ici)
        if r.returncode != 0:
            ko.append("etape0a : `%s` ne s'importe PAS seul (rc=%d) : %s"
                      % (mod, r.returncode, (r.stderr or "").strip()[-400:]))

    src = os.path.join(ici, "engine", "entities", "selectors", "units.py")
    with open(src, "r", encoding="utf-8") as fh:
        arbre = ast.parse(fh.read(), filename=src)
    fautifs = []
    for n in ast.walk(arbre):
        if isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[-1] == "geometry":
            fautifs.append(n.lineno)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[-1] == "geometry":
                    fautifs.append(n.lineno)
    if fautifs:
        ko.append("etape0b : `selectors/units.py` importe `geometry` (lignes %s) -> l'arete est "
                  "un CYCLE et l'import de module pose dans `geometry` doit etre reexamine"
                  % fautifs)
    print("[etape 0] arete `geometry -> units` GRATUITE (import de module legitime) : %s"
          % ("OK" if not ko else "KO"))
    return ko


def etape1_le_noeud_appelle_le_foyer() -> list:
    """Le noeud DELEGUE au foyer : on substitue `has_unit_id` et on verifie qu'il MORD.

    Forme B obligatoire cote test : `geometry` lie le nom au niveau module (forme A), donc on
    patche l'attribut DU MODULE `geometry`, pas celui de `units` -- c'est la seule ecriture qui
    morde, et c'est ce que ce probe verifie de bout en bout."""
    import engine.entities.selectors.geometry as geo

    vus = []

    def _espion(unit, cfg_id):
        vus.append((unit.get("visualId"), cfg_id))
        return True

    class _Src:
        def evaluate(self, ctx):
            return [{"id": 1, "visualId": "peu importe"}]

    original = geo.has_unit_id
    geo.has_unit_id = _espion
    try:
        out = UnitsWithId(_Src(), "unXYZ", mode=0).select(_Ctx())
    finally:
        geo.has_unit_id = original

    ko = []
    if not vus:
        ko.append("etape1 : `UnitsWithId.select` n'appelle PAS `has_unit_id` -- le volet mono-id "
                  "compare encore `visualId` en direct (c'est exactement #1078-r1)")
    if len(out) != 1:
        ko.append("etape1 : le noeud n'a pas garde l'unite que le predicat accepte (%r)" % (out,))
    print("[etape 1] le noeud delegue a `has_unit_id` : %s (%d appel(s))"
          % ("OK" if not ko else "KO", len(vus)))
    return ko


class _Ctx:
    """Contexte minimal : `UnitsWithId` ne lit que le predicat + `selection_ok_from_ctx`."""
    units = ()
    board = None
    has_effect = None
    has_trait = None
    get_stat = None


def etape2_rayon_de_souffle() -> list:
    """Tous les `visualId` presentables x les `unitId` des call-sites : qui change, et dans quel
    sens ? Un `True -> False` est un REFUS neuf : le probe rougit."""
    ids = []
    for label, ability, key in SITES:
        uid = _const(ability, key)
        if not uid:
            print("  [etape 2] AVERTISSEMENT : %s -> constante %r absente du gameconfig"
                  % (label, key))
            continue
        ids.append(uid)
    ids = sorted(set(ids))

    presentables = set()
    for _kind, cids in (GC.all_unit_ids() or {}).items():
        for cid in cids:
            u = GC.unit(cid) or {}
            presentables.add(u.get("visualId") or cid)

    ko = []
    if not ids or not presentables:
        ko.append("etape2 : GISEMENT VIDE (%d unitId, %d visualId) -- un ensemble vide passerait "
                  "pour un vert" % (len(ids), len(presentables)))
        print("[etape 2] RAYON DE SOUFFLE : KO (gisement vide)")
        return ko

    gagnes, perdus = [], []
    for v in sorted(presentables):
        cands = _config_ids_presenting(v)
        for c in ids:
            ancien = (v == c)
            nouveau = (c in cands) if cands else ancien
            if nouveau and not ancien:
                gagnes.append((v, c))
            elif ancien and not nouveau:
                perdus.append((v, c))

    print("[etape 2] RAYON DE SOUFFLE : %d unitId x %d visualId -> %d gagnes, %d perdus"
          % (len(ids), len(presentables), len(gagnes), len(perdus)))
    for v, c in gagnes:
        marque = "attendu" if (v, c) in ATTENDUS else "NOUVEAU"
        print("    + %-40s vs %-28s (%s)" % (v, c, marque))
    for v, c in perdus:
        print("    - %-40s vs %-28s (REFUS NEUF)" % (v, c))

    if perdus:
        ko.append("etape2 : %d verdict(s) True -> False -- le port cesserait de compter des unites "
                  "que la comparaison historique gardait : %s" % (len(perdus), perdus[:5]))
    inconnus = [p for p in gagnes if p not in ATTENDUS]
    if inconnus:
        ko.append("etape2 : %d verdict(s) False -> True NON RECENSES : %s -- les lire un par un "
                  "avant d'elargir ATTENDUS" % (len(inconnus), inconnus[:5]))
    return ko


def etape3_spawn_reste_matche() -> list:
    """Une unite SPAWNEE porte l'id de CONFIG dans son `visualId` (`_spawn_config_grot`) : elle
    DOIT rester matchee par son propre `unitId`, sinon le cap de summons se ferme a jamais."""
    ko = []
    n = 0
    for label, ability, key in SITES:
        uid = _const(ability, key)
        if not uid:
            continue
        n += 1
        if not has_unit_id({"id": 1, "visualId": uid}, uid):
            ko.append("etape3 : %s -- une unite spawnee (visualId == %r) n'est plus matchee par "
                      "son propre unitId" % (label, uid))
    if n == 0:
        ko.append("etape3 : GISEMENT VIDE -- aucun unitId resolu")
    print("[etape 3] les spawns restent matches : %s (%d unitId)"
          % ("OK" if not ko else "KO", n))
    return ko


def main() -> int:
    ko = []
    ko += etape0_import_isole()
    ko += etape1_le_noeud_appelle_le_foyer()
    ko += etape2_rayon_de_souffle()
    ko += etape3_spawn_reste_matche()
    print("")
    if ko:
        print("RESULTAT : KO (%d)" % len(ko))
        for m in ko:
            print("  - %s" % m)
        return 1
    print("RESULTAT : OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
