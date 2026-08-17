"""#1030-r6 -- le COURT-CIRCUIT `get_ReturnsOnlyActors` de `SelectAllActors` est-il ATTEIGNABLE ?

Reponse MESUREE : NON. Ce fichier FIGE le verdict, et le fige des DEUX cotes :

  1. ETAGE PORT (jouable PARTOUT, aucune entree hors depot) -- `Enemies`/`Friends` appliquent le
     `selectionType` a CHAQUE element, sans condition. La contre-epreuve MUTE le noeud pour lui
     faire prendre le court-circuit et exige que le resultat CHANGE : une garde qu'aucune mutation
     ne fait rougir ne garde rien.
  2. ETAGE BINAIRE (SKIP si le jeu n'est pas installe) -- `get_ReturnsOnlyActors` n'a qu'UNE
     definition dans le `global-metadata.dat` (aucun override) et son corps vaut `32 c0 c3`
     (`xor al,al ; ret`). Delegue a `probe_1030r6_court_circuit_returns_only_actors.py`, qui porte
     la derivation de `g_MethodPointers` et ses deux controles (temoin non vide + verite terrain).

POURQUOI L'ETAGE 1 NE SUFFIT PAS, ET POURQUOI L'ETAGE 2 NON PLUS. L'etage 1 garde le COMPORTEMENT
du port ; il resterait vert si le natif changeait d'avis. L'etage 2 garde le NATIF ; il resterait
vert si le port se mettait a court-circuiter. C'est leur CONJONCTION qui tient le verdict.

⚠ ETAGE 2 SKIPPE => ce FICHIER reste vert par l'etage 1 (regle #455 : un fichier integralement
skippe est un faux vert ; celui-ci ne peut pas l'etre).

ASCII only dans les sorties (cp1252).
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # Le foyer garde : les deux noeuds qui appliquent le `selectionType` sans condition.
        "scripts/python/engine/entities/selectors/units.py",
        # Le predicat lui-meme et son derivateur de substrat.
        "scripts/python/engine/entities/unit_selection_type.py",
        # La derivation binaire, deleguee (metadata + g_MethodPointers + octets du corps).
        "scripts/python/probe_1030r6_court_circuit_returns_only_actors.py",
        # Les deux modules dont la derivation depend : le pin de build et le lecteur de metadata.
        "scripts/python/build_pin.py",
        "scripts/python/il2cpp_metadata.py",
        # L'entree versionnee que l'etage 2 confronte a `frida/methods.tsv` (ancrage de la grille).
        "data/symbols/CURRENT",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "Ce fichier fige un verdict de LECTURE que rien d'autre ne tient : le court-circuit de "
        "`IdunBattle.DSL.TargetsSelector$$SelectAllActors` est INATTEIGNABLE parce que "
        "`get_ReturnsOnlyActors` n'est surcharge NULLE PART et vaut FAUX. Aucun test de "
        "comportement ne peut rougir la-dessus : il porte sur une branche que le binaire ne prend "
        "jamais. `build: True` : l'etage 2 lit le `global-metadata.dat` et le `GameAssembly.dll` du "
        "hash COURANT -- un override neuf sur `get_ReturnsOnlyActors`, ou un corps de base qui "
        "passerait a `mov al,1`, rendrait le port sur-restrictif SANS qu'aucun autre garde le voie."
    ),
}

import sys                                                              # noqa: E402
from pathlib import Path                                                # noqa: E402

import pytest                                                           # noqa: E402

#: `.../scripts/python/tests/engine/<ce fichier>` -> quatre crans jusqu'a la RACINE du depot.
ROOT = Path(__file__).resolve().parents[4]
PY = ROOT / "scripts" / "python"
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

from engine.dsl.base import DslContext                                  # noqa: E402
from engine.entities.selectors.units import Enemies, Friends            # noqa: E402
from engine.entities.unit_flag import UnitFlag                          # noqa: E402
from engine.entities.unit_selection_type import UnitSelectionType       # noqa: E402


class _Fixe:
    """Source unit-domain FIGEE -- le regime que le court-circuit natif rendrait << tel quel >>.

    C'est le porteur du discriminant : un selecteur source qui ne rend QUE des acteurs est
    exactement celui dont `#1030-r6` (a) supposait qu'il ferait sauter le `selectionType`."""

    def __init__(self, unites):
        self.unites = list(unites)

    def evaluate(self, ctx):
        return list(self.unites)


def _u(uid, team, *, untargetable=False, alive=True, hp=100):
    return {"id": uid, "team": team, "player": team, "alive": alive, "hp": hp,
            "_untargetable": untargetable}


def _ctx(unites, caster):
    """`has_unit_flag` BRANCHE : sans lui le foyer degrade `targetable` en `None` = PAS MESURE, et
    la clause passe en VRAI -- le discriminant serait alors INERTE et le test vert pour rien."""
    return DslContext(
        units=list(unites), caster=caster,
        has_unit_flag=lambda u, f: bool(u.get("_untargetable")) and f == int(UnitFlag.Untargetable))


# ------------------------------------------------------------------------------------------------
# ETAGE 1 -- le PORT applique le `selectionType` par element, SANS condition (jouable partout)
# ------------------------------------------------------------------------------------------------

CASTER = _u(1, team=1)
ENNEMI_OK = _u(2, team=2)
ENNEMI_DEEP_STRIKE = _u(3, team=2, untargetable=True)
ALLIE_OK = _u(4, team=1)
ALLIE_DEEP_STRIKE = _u(5, team=1, untargetable=True)
TOUS = [CASTER, ENNEMI_OK, ENNEMI_DEEP_STRIKE, ALLIE_OK, ALLIE_DEEP_STRIKE]


def test_e1_enemies_ecarte_l_untargetable_meme_sur_une_source_deja_acteur():
    """`Enemies(<source unit-domain>, selectionType=OnlyAliveAndTargetable)` ECARTE l'unite
    `UnitFlag.Untargetable`. C'est le comportement du natif : le court-circuit qui aurait rendu la
    source TELLE QUELLE n'est jamais pris (`get_ReturnsOnlyActors` == false, etage 2)."""
    ctx = _ctx(TOUS, CASTER)
    src = _Fixe([ENNEMI_OK, ENNEMI_DEEP_STRIKE])
    got = Enemies(src, selection_type=int(UnitSelectionType.OnlyAliveAndTargetable)).evaluate(ctx)
    assert [u["id"] for u in got] == [2], [u["id"] for u in got]


def test_e1_friends_ecarte_l_untargetable_de_la_meme_facon():
    """MEME classe native (`UnitsByTeamSelector`, seul le flag `+0x28` differe) => MEME verdict.
    Le tester separement n'est pas une redondance : les deux `select` sont deux corps Python."""
    ctx = _ctx(TOUS, CASTER)
    src = _Fixe([ALLIE_OK, ALLIE_DEEP_STRIKE])
    got = Friends(src, selection_type=int(UnitSelectionType.OnlyAliveAndTargetable)).evaluate(ctx)
    assert [u["id"] for u in got] == [4], [u["id"] for u in got]


def test_e1_contre_epreuve_le_court_circuit_CHANGERAIT_le_resultat():
    """CONTRE-EPREUVE : on MUTE le noeud pour lui faire prendre le court-circuit (rendre la source
    telle quelle, sans `_selection_ok`) et on exige que le resultat CHANGE.

    Sans elle, les deux tests ci-dessus pourraient etre verts pour une raison ETRANGERE (source
    vide, `has_unit_flag` non branche, filtre applique ailleurs) : une garde qu'aucune mutation ne
    fait rougir ne garde rien."""
    ctx = _ctx(TOUS, CASTER)
    src = _Fixe([ENNEMI_OK, ENNEMI_DEEP_STRIKE])
    noeud = Enemies(src, selection_type=int(UnitSelectionType.OnlyAliveAndTargetable))
    avant = [u["id"] for u in noeud.evaluate(ctx)]

    ct = CASTER.get("team")
    court_circuit = [u for u in src.evaluate(ctx) if u.get("team") != ct]   # `return raw;`
    apres = [u["id"] for u in court_circuit]

    assert avant == [2], avant
    assert apres == [2, 3], apres
    assert avant != apres, "la mutation ne change RIEN : le discriminant est inerte"


def test_e1_le_selection_type_None_ne_filtre_pas():
    """TEMOIN NON DEGENERE : sans `selectionType`, l'unite `Untargetable` est RETENUE. Il etablit
    que l'ecart des tests ci-dessus vient bien du FILTRE et non de la source."""
    ctx = _ctx(TOUS, CASTER)
    got = Enemies(_Fixe([ENNEMI_OK, ENNEMI_DEEP_STRIKE])).evaluate(ctx)
    assert [u["id"] for u in got] == [2, 3], [u["id"] for u in got]


# ------------------------------------------------------------------------------------------------
# ETAGE 2 -- le BINAIRE : une seule definition, corps `return false` (SKIP si le jeu est absent)
# ------------------------------------------------------------------------------------------------

#: MEMO DE MODULE : la mesure re-derive la grille du metadata et relit les 60 Mo du DLL, soit
#: ~17 s. La partager entre les quatre etages fait passer le fichier de 72 s a ~20 s. Le memo
#: garde AUSSI le REFUS (le skip doit etre le meme pour les quatre, pas re-tente trois fois).
_MEMO: list = []


def _mesure():
    import probe_1030r6_court_circuit_returns_only_actors as P
    import il2cpp_metadata as MD
    if not _MEMO:
        try:
            _MEMO.append((P, P.mesurer()))
        except (P.Refus, MD.MetadataRefused, OSError) as exc:
            _MEMO.append(("SKIP", "%s: %s" % (type(exc).__name__, exc)))
    tete = _MEMO[0]
    if tete[0] == "SKIP":
        pytest.skip("mesure binaire impossible (%s)" % tete[1])
    return tete


def test_e2_get_ReturnsOnlyActors_n_est_surcharge_nulle_part():
    """UNE definition dans tout le metadata (slot 21, la virtuelle de `TargetsSelector`).

    TEMOIN NON VIDE assertionne : la MEME famille doit porter au moins une surcharge, sinon le
    compteur ne discrimine rien et le `1` ne vaut rien -- exactement la faute que le CLAUDE.md
    nomme (<< un test vide serait passe pour vert >>)."""
    P, m = _mesure()
    assert len(m["defs"][P.CIBLE]) == 1, [(e.slot, e.flags) for e in m["defs"][P.CIBLE]]
    surcharges = {n: len(m["defs"][n]) for n in P.FAMILLE if n != P.CIBLE}
    assert max(surcharges.values()) > 1, surcharges


def test_e2_le_corps_de_base_rend_FAUX_et_les_surcharges_rendent_VRAI():
    """Les octets, pas un nom : `32 c0 c3` contre `b0 01 c3`.

    Le second membre est le TEMOIN : sur un binaire ou tout rendrait `return 0`, la lecture ne
    discriminerait rien et ce test passerait pour vert."""
    P, m = _mesure()
    for _slot, _rid, _va, oct_ in m["corps"][P.CIBLE]:
        assert oct_ == P.FAUX, oct_.hex()
    vrais = [o for n in P.FAMILLE for _, _, _, o in m["corps"][n] if o == P.VRAI]
    assert vrais, "aucune surcharge triviale ne rend VRAI : la lecture d'octets ne discrimine rien"


def test_e2_la_derivation_retrouve_la_verite_terrain():
    """La table `g_MethodPointers` derivee doit retomber EXACTEMENT sur les deux seules
    `get_ReturnsOnly*` que `ghidra/functions.tsv` NOMME. Sans ce controle, une localisation fausse
    rendrait un corps quelconque -- donc un verdict quelconque."""
    _P, m = _mesure()
    for nom, (attendu, trouve) in m["terrain"].items():
        assert attendu, "verite terrain absente de la table : %s" % nom
        assert trouve, "la table derivee ne retrouve pas %s" % nom


def test_e2_aucun_invariant_ne_tombe():
    """Le verdict d'ensemble du probe, pour que ce fichier rougisse aussi sur un invariant que les
    trois tests ci-dessus n'auraient pas enumere."""
    P, m = _mesure()
    ko = P._verdicts(m)                                               # noqa: SLF001
    assert not ko, "\n".join(ko)
